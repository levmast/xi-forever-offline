"""Gambits 0.3.1: writes the addon's gambits_data.lua (spell families, status effects, which status effect each spell
and job ability gives) from the server's own data files. The editor uses it ONLY for what it shows (the job-aware
family and spell lists, the status effect selector, tooltips); it never changes a rule, and the server still checks
every name when a Rule Set is saved.

Sources (all read from a server checkout):
  sql/spell_list.sql                spell id, name, group, family, status_effect (a number or an @EFFECT_ variable)
  scripts/enum/magic.lua            xi.magic.spell (spell names) and xi.magic.spellFamily (family names)
  sql/item_basic.sql                whether a spell's scroll exists (item 4608 + spell id)
  data/status_effects.yaml          the status effects: key -> id (xi.effect's names are the keys in upper case)
  sql/abilities.sql                 job ability id and name
  scripts/enum/job_ability.lua      xi.jobAbility (ability id -> names, as the catalog sends them)
  scripts/actions/abilities/*.lua   + scripts/globals/job_utils/*.lua: the effects an ability adds (addStatusEffect),
                                    and job_utils parameter tables ([xi.jobAbility.X] = { effect = xi.effect.Y })
  scripts/globals/spells/*.lua      the spell parameter tables (enfeebling/enhancing spells and songs, ninjutsu):
                                    a spell's effect when spell_list.status_effect has none

What each part means:
  spells[NAME]    = { FAMILY or false, e = EFFECT (spell_list.status_effect), q = 'x' never in a squad mate's spell
                      list (Trust, Summoning, Geomancy, or no scroll: a monster's version) / 'b' blue magic }
                    q follows gambits_squad.lua G.mateSpells (the trustutils.cpp rules) exactly.
  effects[NAME]   = id (every status effect of data/status_effects.yaml)
  jaEffects[NAME] = { EFFECT, ... } the effects the ability's server script adds with addStatusEffect(xi.effect.X),
                    directly or in the xi.job_utils function (and the local helpers of that file) it calls. Abilities
                    whose script adds no effect that way are not listed (nothing is guessed from names).
  jas[NAME]       = { 'JOB', level, sp = true, main = true, merit = true } (0.3.1, job abilities): exactly the rows of
                    the server's modules/custom/lua/squad_ja_jobs_data.lua, the table its U13 rules (squad_ability_rules.lua
                    A.reason) use - sp: a two-hour (never from the sub job), main: ADDTYPE_MAIN_ONLY (never from the sub
                    job), merit: the squad's owner must have unlocked its merit. Pet abilities (id >= 512) and the pet
                    command menu (55) are left out, as the server does. Job names from scripts/enum/job.codegen.lua.

    python make_gambits_addon_data.py <server checkout> <kit>/addons-src/Gambits/gambits_data.lua
    python make_gambits_addon_data.py --check <server checkout> <kit>/addons-src/Gambits/gambits_data.lua
--check exits 1 when the Lua file is not what the server files give now.
"""
import os
import re
import sys

FORMAT_VERSION = 1
SPELL_COLUMNS = 27  # spell_list: spellid .. status_effect_tier
SCROLL_BASE = 4608
GROUP_BLUE, GROUP_SUMMONING, GROUP_GEOMANCY, GROUP_TRUST = 3, 5, 7, 8


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def sql_values(line):
    """the fields of one `INSERT INTO ... VALUES (...);` line (quotes and a trailing -- comment handled)."""
    start = line.index("VALUES (") + len("VALUES (")
    fields, cur, i, quoted = [], [], start, False
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == "\\" and i + 1 < len(line):
                cur.append(line[i:i + 2])
                i += 2
                continue
            if ch == "'":
                quoted = False
            cur.append(ch)
        elif ch == "'":
            quoted = True
            cur.append(ch)
        elif ch == ",":
            fields.append("".join(cur).strip())
            cur = []
        elif ch == ")":
            fields.append("".join(cur).strip())
            return fields
        else:
            cur.append(ch)
        i += 1
    raise ValueError("unterminated row: " + line[:100])


def unquote(v):
    return None if v == "NULL" else (v[1:-1] if v.startswith("'") else v)


def parse_effects(yaml_text):
    """{NAME: id} from data/status_effects.yaml (top-level keys under status_effects, each with an id)."""
    at = yaml_text.find("\nstatus_effects:")
    if at < 0:
        raise ValueError("status_effects: not found in status_effects.yaml")
    body = yaml_text[at:]
    out = {}
    for key, sid in re.findall(r"^  ([a-z0-9_]+):\s*\n    id:\s*(\d+)\s*$", body, re.M):
        out[key.upper()] = int(sid)
    keys = re.findall(r"^  ([a-z0-9_]+):\s*$", body, re.M)
    if not out or len(keys) != len(out):
        raise ValueError(f"status_effects.yaml: {len(keys)} effects but {len(out)} with an id")
    return out


def parse_enum_table(lua_text, table):
    """{id: [names in file order]} of one `<table> = { NAME = id, ... }` block."""
    start = lua_text.find(table + " =")
    if start < 0:
        raise ValueError(table + " not found")
    body = lua_text[start:]
    end = body.find("\n}")
    out = {}
    for name, value in re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*,", body[:end], re.M):
        out.setdefault(int(value), []).append(name)
    if not out:
        raise ValueError(table + " is empty")
    return out


def parse_spells(sql_text, effects):
    """[(id, name-in-sql, group, family id, effect name or None, scroll id)] for every active row."""
    effect_ids = {v: k for k, v in effects.items()}
    variables = {name: int(v) for name, v in re.findall(r"^SET @(EFFECT_[A-Z0-9_]+)\s*=\s*(\d+);", sql_text, re.M)}
    rows = []
    for number, line in enumerate(sql_text.splitlines(), 1):
        line = line.strip()
        if not line.startswith("INSERT INTO `spell_list` VALUES"):
            continue
        f = sql_values(line)
        if len(f) != SPELL_COLUMNS:
            raise ValueError(f"spell_list.sql line {number}: {len(f)} columns, expected {SPELL_COLUMNS}")
        sid, group, family, raw = int(f[0]), int(f[3]), int(f[4]), f[25]
        effect = None
        if raw != "NULL":
            if raw.startswith("@"):
                if raw[1:] not in variables:
                    raise ValueError(f"spell_list.sql line {number}: unknown variable {raw}")
                eid = variables[raw[1:]]
            else:
                eid = int(raw)
            if eid not in effect_ids:
                raise ValueError(f"spell_list.sql line {number}: status effect {eid} is not in status_effects.yaml")
            effect = effect_ids[eid]
        rows.append((sid, group, family, effect))
    if not rows:
        raise ValueError("no spell rows")
    return rows


SPELL_TABLE_FILES = ("enfeebling_spell.lua", "enfeebling_song.lua", "enhancing_spell.lua", "enhancing_song.lua",
                     "enhancing_ninjutsu.lua")  # (absorb_spell.lua names two effects per row, the caster's and the
                                                # target's: left out rather than picking one)
SPELL_TABLE_ROW = re.compile(r"^\s*\[xi\.magic\.spell\.([A-Z0-9_]+)\s*\]\s*=\s*\{(.*)\}\s*,?\s*(?:--.*)?$")
FIRST_EFFECT = re.compile(r"xi\.effect\.([A-Z0-9_]+)")


def parse_spell_tables(spells_dir):
    """{spell NAME: effect NAME} from the server's spell parameter tables (scripts/globals/spells/*.lua: one row
    `[xi.magic.spell.X] = { ..., xi.effect.Y, ... }` per spell, the row's first effect; commented-out rows skipped)."""
    out = {}
    for fn in SPELL_TABLE_FILES:
        path = os.path.join(spells_dir, fn)
        if not os.path.isfile(path):
            continue
        for line in read(path).splitlines():
            m = SPELL_TABLE_ROW.match(line)
            if m:
                e = FIRST_EFFECT.search(m.group(2))
                if e:
                    out.setdefault(m.group(1), e.group(1))
    return out


def parse_items(sql_text):
    return {int(m) for m in re.findall(r"^INSERT INTO `item_basic` VALUES \((\d+),", sql_text, re.M)}


def parse_abilities(sql_text):
    """[(id, script name)] of sql/abilities.sql."""
    out = []
    for line in sql_text.splitlines():
        line = line.strip()
        if line.startswith("INSERT INTO `abilities` VALUES"):
            f = sql_values(line)
            out.append((int(f[0]), unquote(f[1])))
    if not out:
        raise ValueError("no ability rows")
    return out


EFFECT_ADD = re.compile(r"addStatusEffect\(\s*xi\.effect\.([A-Z0-9_]+)")
JOB_UTILS_CALL = re.compile(r"xi\.job_utils\.([a-z_]+)\.([A-Za-z0-9_]+)\s*\(")
LOCAL_CALL = re.compile(r"(?<![\w.:])([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def function_bodies(lua_text, module):
    """{xi.job_utils.<module>.fn: body, local fn: body} of a job_utils file (bodies end at a line 'end' in column 0)."""
    out = {}
    pattern = re.compile(r"^(?:xi\.job_utils\.%s\.([A-Za-z0-9_]+)\s*=\s*function|local function ([A-Za-z0-9_]+))\s*\(" % module, re.M)
    for m in pattern.finditer(lua_text):
        end = lua_text.find("\nend", m.end())
        body = lua_text[m.end(): end if end >= 0 else len(lua_text)]
        if m.group(1):
            out["xi.job_utils.%s.%s" % (module, m.group(1))] = body
        else:
            out["local:%s:%s" % (module, m.group(2))] = body
    return out


ABILITY_TABLE_ENTRY = re.compile(r"\[xi\.jobAbility\.([A-Z0-9_]+)\s*\]\s*=\s*\{(.*?)\n\s*\},?", re.S)
TABLE_EFFECT = re.compile(r"^\s*effect\s*=\s*xi\.effect\.([A-Z0-9_]+)", re.M)


def ability_tables(lua_text):
    """{ABILITY: effect} from job_utils parameter tables: `[xi.jobAbility.X] = { ... effect = xi.effect.Y, ... }`
    (e.g. corsair.lua's Phantom Rolls, whose effect the shared roll function adds from this table)."""
    out = {}
    for m in ABILITY_TABLE_ENTRY.finditer(lua_text):
        e = TABLE_EFFECT.search(m.group(2))
        if e:
            out.setdefault(m.group(1), e.group(1))
    return out


def ability_effects(script_text, utils, known, depth=0, seen=None):
    """the effects a script text adds, following xi.job_utils calls and that file's local helpers (at most 4 levels)."""
    seen = seen if seen is not None else set()
    found = [e for e in EFFECT_ADD.findall(script_text)]
    if depth >= 4:
        return found
    for module, fn in JOB_UTILS_CALL.findall(script_text):
        key = "xi.job_utils.%s.%s" % (module, fn)
        if key in utils and key not in seen:
            seen.add(key)
            found += ability_effects(utils[key], utils, known, depth + 1, seen)
            for local in LOCAL_CALL.findall(utils[key]):
                lk = "local:%s:%s" % (module, local)
                if lk in utils and lk not in seen:
                    seen.add(lk)
                    found += ability_effects(utils[lk], utils, known, depth + 1, seen)
    return found


JA_ROW = re.compile(r"^\s*\[(\d+)\]\s*=\s*\{\s*(\d+)\s*,\s*(\d+)\s*((?:,\s*[a-z]+\s*=\s*[a-z0-9]+\s*)*)\}\s*,", re.M)
JA_FLAG = re.compile(r"([a-z]+)\s*=\s*([a-z0-9]+)")
FIRST_PET_ABILITY, PET_COMMANDS = 512, 55  # (squad_ability_rules.lua A.FIRST_PET_ABILITY, A.PET_COMMANDS)


def parse_ja_jobs(lua_text, ja_names, job_names):
    """{NAME: (JOB, level, sp, main, merit)} from squad_ja_jobs_data.lua (version 3), for every name of the ability."""
    if not re.search(r"^\s*version\s*=\s*3\s*,", lua_text, re.M):
        raise ValueError("squad_ja_jobs_data.lua is not a version 3 ability table")
    out = {}
    for m in JA_ROW.finditer(lua_text):
        aid, job, level = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if aid >= FIRST_PET_ABILITY or aid == PET_COMMANDS or aid not in ja_names:
            continue
        flags = dict(JA_FLAG.findall(m.group(4) or ""))
        unknown = set(flags) - {"sp", "main", "merit"}
        if unknown or job not in job_names:
            raise ValueError(f"squad_ja_jobs_data.lua row {aid}: unknown flag {unknown} or job {job}")
        row = (job_names[job][0], level, flags.get("sp") == "true" or level == 0, flags.get("main") == "true",
               "merit" in flags)
        for name in ja_names[aid]:
            out[name] = row
    if len(out) < 300:
        raise ValueError(f"squad_ja_jobs_data.lua: only {len(out)} abilities read")
    return out


def build(server):
    p = lambda *parts: os.path.join(server, *parts)
    effects = parse_effects(read(p("data", "status_effects.yaml")))
    magic = read(p("scripts", "enum", "magic.lua"))
    spell_names = parse_enum_table(magic, "xi.magic.spell")
    family_names = parse_enum_table(magic, "xi.magic.spellFamily")
    items = parse_items(read(p("sql", "item_basic.sql")))
    tables = parse_spell_tables(p("scripts", "globals", "spells"))
    spells = {}
    for sid, group, family, effect in parse_spells(read(p("sql", "spell_list.sql")), effects):
        if sid not in spell_names:
            continue
        fam = family_names.get(family, [None])[0] if family else None
        if family and fam is None:
            raise ValueError(f"spell {sid}: family {family} is not in xi.magic.spellFamily")
        if group in (GROUP_TRUST, GROUP_SUMMONING, GROUP_GEOMANCY):
            q = "x"
        elif group == GROUP_BLUE:
            q = "b"
        elif (SCROLL_BASE + sid) not in items:
            q = "x"
        else:
            q = None
        name = spell_names[sid][0]
        if effect is None and tables.get(name) in effects:
            effect = tables[name]  # (spell_list.status_effect first; else the spell's parameter table)
        spells[name] = (fam if fam != "NONE" else None, effect, q)

    ja_names = parse_enum_table(read(p("scripts", "enum", "job_ability.lua")), "xi.jobAbility")
    utils, tables = {}, {}
    udir = p("scripts", "globals", "job_utils")
    for fn in sorted(os.listdir(udir)):
        if fn.endswith(".lua"):
            text = read(os.path.join(udir, fn))
            utils.update(function_bodies(text, fn[:-4]))
            for ja, e in ability_tables(text).items():
                tables.setdefault(ja, e)
    adir = p("scripts", "actions", "abilities")
    ja_effects = {}
    for aid, name in parse_abilities(read(p("sql", "abilities.sql"))):
        path = os.path.join(adir, (name or "") + ".lua")
        if aid not in ja_names or not os.path.isfile(path):
            continue
        found = []
        listed = [tables[ja] for ja in ja_names[aid] if ja in tables]
        for e in listed[:1] + ability_effects(read(path), utils, effects):
            if e not in effects:
                continue  # (a name the server's effect table does not have, e.g. libra.lua's LIBRA: no rule can use it)
            if e not in found:
                found.append(e)
        if found:
            for ja in ja_names[aid]:
                ja_effects[ja] = found
    job_names = parse_enum_table(read(p("scripts", "enum", "job.codegen.lua")), "xi.job")
    jas = parse_ja_jobs(read(p("modules", "custom", "lua", "squad_ja_jobs_data.lua")), ja_names, job_names)
    return spells, effects, ja_effects, jas


def lua_str(s):
    return "'" + s + "'"


def render(spells, effects, ja_effects, jas):
    lines = [
        "-- Gambits: spell families, status effects, the effect each spell / job ability gives, and each job ability's",
        "-- job, level and sub job / merit restrictions, for the editor's lists and tooltips only (the server checks every",
        "-- name on Save, and decides what a squad mate uses).",
        "-- MADE BY dev/gambits-v2-squad/make_gambits_addon_data.py FROM the server's sql/spell_list.sql, sql/item_basic.sql,",
        "-- sql/abilities.sql, scripts/enum/magic.lua, scripts/enum/job_ability.lua, scripts/enum/job.codegen.lua,",
        "-- data/status_effects.yaml, modules/custom/lua/squad_ja_jobs_data.lua and the job ability scripts - do not edit",
        "-- by hand, run the script again.",
        "-- spells[NAME] = { FAMILY or false, e = status effect, q = 'x' never a squad mate's spell / 'b' blue magic }",
        "-- effects[NAME] = id; jaEffects[NAME] = { effects the ability's script adds }",
        "-- jas[NAME] = { JOB, level, sp = two-hour, main = main job only, merit = needs the owner's merit }",
        "return",
        "{",
        "    format  = 'xifo-gambits-addon-data',",
        f"    version = {FORMAT_VERSION},",
        "    spells  =",
        "    {",
    ]
    for name in sorted(spells):
        fam, effect, q = spells[name]
        extra = (f", e = {lua_str(effect)}" if effect else "") + (f", q = {lua_str(q)}" if q else "")
        lines.append(f"        {name} = {{ {lua_str(fam) if fam else 'false'}{extra} }},")
    lines += ["    },", "    effects =", "    {"]
    for name in sorted(effects, key=lambda n: (effects[n], n)):
        lines.append(f"        {name} = {effects[name]},")
    lines += ["    },", "    jaEffects =", "    {"]
    for name in sorted(ja_effects):
        lines.append(f"        {name} = {{ {', '.join(lua_str(e) for e in ja_effects[name])} }},")
    lines += ["    },", "    jas =", "    {"]
    for name in sorted(jas):
        job, level, sp, main, merit = jas[name]
        extra = (", sp = true" if sp else "") + (", main = true" if main else "") + (", merit = true" if merit else "")
        lines.append(f"        {name} = {{ {lua_str(job)}, {level}{extra} }},")
    lines += ["    },", "}", ""]
    return "\n".join(lines)


def main(argv):
    check = len(argv) > 1 and argv[1] == "--check"
    args = argv[2:] if check else argv[1:]
    if len(args) != 2:
        print(__doc__)
        return 2
    server, out = args
    text = render(*build(server))
    if check:
        try:
            current = read(out)
        except OSError:
            current = None
        if current != text:
            print(f"{out} is out of date - run make_gambits_addon_data.py again")
            return 1
        print(f"{out} is up to date")
        return 0
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    spells, effects, ja, jas = build(server)
    print(f"wrote {out}: {len(spells)} spells, {len(effects)} effects, {len(ja)} job abilities with effects, "
          f"{len(jas)} job ability names with their job and level")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
