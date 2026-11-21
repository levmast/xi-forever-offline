"""Gambits v2: writes squad_spell_jobs_data.lua (which jobs learn each spell, and at which level) from the server's
sql/spell_list.sql and scripts/enum/magic.lua.

gambits_squad.lua uses it for the Squad editor's Specific Spell choices (catalog 's'): the spells the mate's main job
(and sub job) learn, with their levels. The server's eligibility checks are unchanged (squad_rulesets.lua checks spell
names; the game decides what a mate can cast).

spell_list.sql: `jobs` binary(22) = one byte per job, byte j-1 = the level job j learns the spell at (0 = never).
magic.lua: xi.magic.spell = { NAME = id, ... } (the names squad.lua's rules use). Only spells in both, learnable by some
job, are written.

Version 2 adds, per spell, its spell_list group (g) and whether its scroll item exists (sc: item 4608 + spell id in
sql/item_basic.sql), so gambits_squad.lua's per-mate catalog (catm) can apply the same rules trustutils.cpp uses when it
builds a squad mate's spell list: no Trust (8), Summoning (5) or Geomancy (7) spells, blue magic (3) only for a Blue Mage,
and other spells only when they come on a scroll (a spell without one is a monster's version).

    python make_squad_spell_jobs.py <spell_list.sql> <magic.lua> <item_basic.sql> <out>/squad_spell_jobs_data.lua
    python make_squad_spell_jobs.py --check <spell_list.sql> <magic.lua> <item_basic.sql> <server>/modules/custom/lua/squad_spell_jobs_data.lua
    python make_squad_spell_jobs.py --trusts <spell_list.sql> <magic.lua> <kit>/addons-src/GambitsV2/trust_spells.lua
    python make_squad_spell_jobs.py --check-trusts <spell_list.sql> <magic.lua> <kit>/addons-src/GambitsV2/trust_spells.lua

--trusts writes the names of the Trust-summoning spells (spell_list group 8) for the GambitsV2 editor, which leaves them
out of its Specific Spell choices (every job "learns" them at level 1, so they are in every job's catalog). The server
file is not changed by it.

--check exits 1 when the Lua file is not what the source files give now (regenerate it then).
In a sparse server clone: git -C <server> show HEAD:sql/spell_list.sql > spell_list.sql (and the same for magic.lua).
"""
import re
import sys

FORMAT_VERSION = 3  # 3 (job expansion): ct = the spell's content_tag (an expansion), only when it has one
JOBS = 22  # bytes in spell_list.jobs
# the row's last three columns: content_tag, status_effect, status_effect_tier
CONTENT = re.compile(r",(NULL|'([A-Z0-9_]+)'),(NULL|\d+),(\d+)\);\s*$")
SCROLL_BASE = 4608  # a spell's scroll is item 4608 + spell id (trustutils.cpp: 0x1200 + id)
ITEM_ROW = re.compile(r"^INSERT INTO `item_basic` VALUES \((\d+),")


def parse_items(sql_text):
    """the set of item ids in item_basic.sql"""
    out = set()
    for line in sql_text.splitlines():
        m = ITEM_ROW.match(line.strip())
        if m:
            out.add(int(m.group(1)))
    if not out:
        raise ValueError("no item rows found in item_basic.sql")
    return out
ROW = re.compile(r"^INSERT INTO `spell_list` VALUES \((\d+),'((?:[^'\\]|\\.)*)',0x([0-9A-Fa-f]{44}),(\d+),")
TRUST_GROUP = 8  # spell_list.group of the Trust-summoning spells (SPELLGROUP_TRUST)


def parse_groups(sql_text):
    """{id: group} for every active row."""
    out = {}
    for line in sql_text.splitlines():
        m = ROW.match(line.strip())
        if m:
            out[int(m.group(1))] = int(m.group(4))
    return out


def parse_content(sql_text):
    """{id: content tag} for every active row that has one (e.g. 'WOTG')."""
    out = {}
    for line in sql_text.splitlines():
        line = line.strip()
        m = ROW.match(line)
        if m:
            c = CONTENT.search(line)
            if c and c.group(2):
                out[int(m.group(1))] = c.group(2)
    return out


def render_trusts(groups, names):
    trusts = sorted(names[sid] for sid, group in groups.items() if group == TRUST_GROUP and sid in names)
    lines = [
        "-- GambitsV2: the Trust-summoning spells (spell_list group 8). The editor leaves them out of its Specific Spell choices.",
        "-- MADE BY dev/gambits-v2-squad/make_squad_spell_jobs.py --trusts FROM sql/spell_list.sql AND scripts/enum/magic.lua -",
        "-- do not edit by hand, run the script again.",
        "return",
        "{",
    ]
    lines += [f"    {name} = true," for name in trusts]
    lines += ["}", ""]
    return "\n".join(lines)


def parse_spells(sql_text):
    """{id: {job: level}} for every active row (commented-out rows are skipped)."""
    out = {}
    for number, line in enumerate(sql_text.splitlines(), 1):
        line = line.strip()
        if not line.startswith("INSERT INTO `spell_list` VALUES"):
            continue
        m = ROW.match(line)
        if not m:
            raise ValueError(f"line {number}: cannot read the row: {line[:120]}")
        raw = bytes.fromhex(m.group(3))
        levels = {job: raw[job - 1] for job in range(1, JOBS + 1) if raw[job - 1] > 0}
        sid = int(m.group(1))
        if sid in out:
            raise ValueError(f"line {number}: spell id {sid} twice")
        out[sid] = levels
    return out


def parse_enum(lua_text):
    """{id: NAME} from the xi.magic.spell table of magic.lua (the first name of an id wins)."""
    start = lua_text.find("xi.magic.spell =")
    if start < 0:
        raise ValueError("xi.magic.spell not found in magic.lua")
    body = lua_text[start:]
    end = body.find("\n}")
    if end < 0:
        raise ValueError("the end of xi.magic.spell was not found")
    names = {}
    for name, value in re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*,", body[:end], re.M):
        names.setdefault(int(value), name)
    if not names:
        raise ValueError("xi.magic.spell is empty")
    return names


def render(spells, names, groups, items, content=None):
    content = content or {}
    lines = [
        "-- Gambits v2: which jobs learn each spell, and at which level, for gambits_squad.lua (the Squad editor's spells).",
        "-- MADE BY dev/gambits-v2-squad/make_squad_spell_jobs.py FROM sql/spell_list.sql, scripts/enum/magic.lua AND",
        "-- sql/item_basic.sql - do not edit by hand, run the script again.",
        "-- [spell id] = { 'NAME' (xi.magic.spell), { [job id] = level, ... }, g = spell group, sc = its scroll item exists",
        "--                [, ct = its content tag (an expansion: left out of the editor while the server has it off)] }",
        "return",
        "{",
        "    format  = 'xifo-squad-spell-jobs',",
        f"    version = {FORMAT_VERSION},",
        "    spells  =",
        "    {",
    ]
    for sid in sorted(spells):
        levels = spells[sid]
        if not levels or sid not in names:
            continue
        jobs = ", ".join(f"[{job}] = {level}" for job, level in sorted(levels.items()))
        scroll = "true" if (SCROLL_BASE + sid) in items else "false"
        tag = f", ct = '{content[sid]}'" if sid in content else ""
        lines.append(f"        [{sid}] = {{ '{names[sid]}', {{ {jobs} }}, g = {groups.get(sid, 0)}, sc = {scroll}{tag} }},")
    lines += ["    },", "}", ""]
    return "\n".join(lines)


def main(argv):
    mode = argv[1] if len(argv) > 1 and argv[1].startswith("--") else ""
    if mode not in ("", "--check", "--trusts", "--check-trusts"):
        print(__doc__)
        return 2
    check = mode in ("--check", "--check-trusts")
    trusts = mode in ("--trusts", "--check-trusts")
    args = argv[2:] if mode else argv[1:]
    if len(args) != (3 if trusts else 4):
        print(__doc__)
        return 2
    out = args[-1]
    with open(args[0], encoding="utf-8", errors="replace") as f:
        sql = f.read()
    with open(args[1], encoding="utf-8", errors="replace") as f:
        names = parse_enum(f.read())
    if trusts:
        text = render_trusts(parse_groups(sql), names)
    else:
        with open(args[2], encoding="utf-8", errors="replace") as f:
            items = parse_items(f.read())
        text = render(parse_spells(sql), names, parse_groups(sql), items, parse_content(sql))
    if check:
        try:
            with open(out, encoding="utf-8") as f:
                current = f.read()
        except OSError:
            current = None
        if current != text:
            print(f"{out} is out of date - run make_squad_spell_jobs.py {'--trusts ' if trusts else ''}again")
            return 1
        print(f"{out} is up to date")
        return 0
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    count = text.count(" = true,") if trusts else text.count("\n        [")
    print(f"wrote {out}: {count} {'trust spells' if trusts else 'spells'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
