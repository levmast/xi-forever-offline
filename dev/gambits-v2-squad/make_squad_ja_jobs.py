"""Gambits v2 M1.1: writes squad_ja_jobs_data.lua (job, level and job restrictions of every job ability) from the
server's sql/abilities.sql.

The trust engine does not check a job ability's job or level for a trust (ability_state.cpp CanUseAbility only checks
players), so squad_rulesets.lua checks Rule Set job abilities against this table, with the same rules charutils.cpp
BuildingCharAbilityTable uses for players:
  - sp   = level 0 (two-hour and similar): never learned from the sub job ("PAbility->getLevel() != 0")
  - main = addType has ADDTYPE_MAIN_ONLY (4, ability.h): never learned from the sub job, even at the level
           (Afflatus Solace/Misery, Composure, Yonin/Innin, Spirit Link, Call Wyvern, Velocity Shot, ...)
  - merit = meritModID, only when addType has ADDTYPE_MERIT (1): the merit that must be unlocked (charutils.cpp
           CheckAbilityAddtype: PMeritPoints->GetMerit(meritModID)->count > 0). Other rows' meritModID (e.g. Sic and
           Ready, 902) is not an unlock and is left out.

    python make_squad_ja_jobs.py <server>/sql/abilities.sql <out>/squad_ja_jobs_data.lua
    python make_squad_ja_jobs.py --check <server>/sql/abilities.sql <server>/modules/custom/lua/squad_ja_jobs_data.lua

--check exits 1 when the Lua file is not what the SQL file gives now (regenerate it then).
In a sparse server clone, get the SQL file with:  git -C <server> show HEAD:sql/abilities.sql > abilities.sql
"""
import re
import sys

FORMAT_VERSION = 3
ADDTYPE_MERIT = 1      # src/map/ability.h
ADDTYPE_MAIN_ONLY = 4  # src/map/ability.h

# abilityId, 'name', then the other columns of the CREATE TABLE in order:
COLUMNS = ["job", "level", "validTarget", "recastTime", "recastId", "message1", "message2", "animation", "animationTime",
           "castTime", "actionType", "range", "isAOE", "radius", "CE", "VE", "meritModID", "addType", "content_tag"]
ROW = re.compile(r"^INSERT INTO `abilities` VALUES \((\d+),'((?:[^'\\]|\\.)*)',(.*?)\);\s*(--.*)?$")


def parse(sql_text):
    """[(id, name, job, level, sp, main_only, merit_id or 0)], sorted by id. Raises ValueError on a row it cannot read."""
    rows = []
    for number, line in enumerate(sql_text.splitlines(), 1):
        line = line.strip()
        if not line.startswith("INSERT INTO `abilities` VALUES"):
            continue
        m = ROW.match(line)
        values = m.group(3).split(",") if m else []
        if len(values) != len(COLUMNS):
            raise ValueError(f"line {number}: expected {len(COLUMNS) + 2} columns: {line[:120]}")
        col = dict(zip(COLUMNS, values))
        job, level, add_type, merit_mod = int(col["job"]), int(col["level"]), int(col["addType"]), int(col["meritModID"])
        merit = merit_mod if add_type & ADDTYPE_MERIT else 0
        if add_type & ADDTYPE_MERIT and merit_mod <= 0:
            raise ValueError(f"line {number}: merit ability without a meritModID: {line[:120]}")
        rows.append((int(m.group(1)), m.group(2), job, level, level == 0, bool(add_type & ADDTYPE_MAIN_ONLY), merit))
    return sorted(rows)


def render(rows):
    out = [
        "-- Gambits v2 M1.1: the job, level and sub-job restrictions of each job ability, for squad_rulesets.lua.",
        "-- MADE BY dev/gambits-v2-squad/make_squad_ja_jobs.py FROM sql/abilities.sql - do not edit by hand, run the script again.",
        "-- [ability id (= xi.ja value)] = { job id, level, sp = true (level 0: never from the sub job),",
        "--                                  main = true (addType ADDTYPE_MAIN_ONLY: never from the sub job),",
        "--                                  merit = id (addType ADDTYPE_MERIT: the owner must have unlocked that merit) }",
        "return",
        "{",
        f"    version = {FORMAT_VERSION},",
        "    abilities =",
        "    {",
    ]
    for ability_id, name, job, level, sp, main_only, merit in rows:
        extra = (", sp = true" if sp else "") + (", main = true" if main_only else "") + (f", merit = {merit}" if merit else "")
        out.append(f"        [{ability_id}] = {{ {job}, {level}{extra} }}, -- {name}")
    out += ["    },", "}", ""]
    return "\n".join(out)


def main(argv):
    check = argv[:1] == ["--check"]
    args = argv[1:] if check else argv
    if len(args) != 2:
        print(__doc__)
        return 2
    with open(args[0], encoding="utf-8") as f:
        rows = parse(f.read())
    if not rows:
        print("no ability rows found in", args[0])
        return 2
    text = render(rows)
    if check:
        try:
            with open(args[1], encoding="utf-8", newline="") as f:
                current = f.read().replace("\r\n", "\n")
        except OSError:
            current = None
        if current != text:
            print(f"{args[1]} is out of date ({len(rows)} abilities in the SQL); run make_squad_ja_jobs.py again")
            return 1
        print(f"up to date ({len(rows)} abilities)")
        return 0
    with open(args[1], "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {args[1]} ({len(rows)} abilities, {sum(1 for r in rows if r[4])} level 0, "
          f"{sum(1 for r in rows if r[5])} main job only, {sum(1 for r in rows if r[6])} merit unlocked)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
