"""Database layer for the launcher's Squad tab (no GUI code here, so it can be tested on its own).

Works with any DB-API connection that uses '?' placeholders (the `mariadb` package, or sqlite3 in tests).
"""

import json
import os
import re

RACES = ["Hume M", "Hume F", "Elvaan M", "Elvaan F", "Tarutaru M", "Tarutaru F", "Mithra", "Galka"]  # ids 1-8
JOBS = ["WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN",
        "BLU", "COR", "PUP", "DNC", "SCH"]  # ids 1-20 (16-18: the Aht Urhgan jobs, squad.lua v1.17; 19-20: Wings of the Goddess, 2026-11-22)
MAX_SLOTS = 6
MAX_LEVEL = 75

# Bot players are real characters too, on accounts reserved from this id up
# (see crowds/bots/bots.cpp, BotAccBase). The Squad tab only lists humans.
BOT_ACCOUNT_BASE = 21000000

# A mate's role and mode (see squad.lua, "Roles and modes"). They are kept on the player as the variable SQUAD_AI_<mate id> = role * 10 + mode,
# the same number the server's !squad role / !squad mode commands write. Change them here with the game closed (the server keeps player
# variables in memory while someone is logged in), or in the game with the commands or the Squad panel.
ROLES = ["auto", "tank", "damage", "healer", "support"]
MODES = ["balanced", "aggressive", "conserve"]

# (role clarity) what each role and mode really does, from the server's squad.lua behaviorFilter / ROLE_KEEPS /
# EMERGENCY_HP (tank 40, damage 30) and MODE_HEAL_SHIFT (+15 / -15, kept between 15 and 90). The same words as the
# in-game Squad menu and Squad panel. Text only: the server decides.
ROLE_HELP = {
    "tank": "Provoke, Sentinel, debuffs, own buffs; cures only below 40% HP, no status removal, no buffs on others; no nukes",
    "damage": "attacks, nukes, debuffs, own buffs; cures only below 30% HP, no status removal, no buffs on others",
    "healer": "cures, status removal, party buffs; no debuffs, nukes or job abilities",
    "support": "party buffs, debuffs, status removal, cures; no nukes or job abilities",
    "auto": "the job's default rules, nothing filtered",
}
MODE_HELP = {
    "aggressive": "cures 15% HP earlier (also on top of a Tank or Damage limit); holds no MP back",
    "conserve": "cures 15% HP later and keeps 40% MP before buffs, debuffs, nukes and status removal",
}
ROLE_FOOTER = ("The role changes only the mate's default job rules. A Gambits Rule Set replaces those rules and is not "
               "filtered by the role. It is not the Gambits party role (Tank / Melee / Mage / Ranged).")


def behavior_help_text():
    """The Behavior page's legend: one line per role, then the modes."""
    lines = [f"{role}: {ROLE_HELP[role]}." for role in ("tank", "damage", "healer", "support", "auto")]
    lines.append("")
    lines += [f"{mode}: {MODE_HELP[mode]}." for mode in ("aggressive", "conserve")]
    return "\n".join(lines)

# WAR MNK WHM BLM RDM THF are available from the start; the other jobs are "advanced" and must be unlocked
# on the character first (the game keeps that as a bit per job id in char_jobs.unlocked).
STARTER_JOBS = {1, 2, 3, 4, 5, 6}

# ----- greetings -----
# The lines a mate says when called, when they level up, when they fall and on a weaponskill. The launcher edits
# them here and writes them for the server as Lua; the server reads that file when it starts.
GREETING_EVENTS = ("spawn", "levelup", "death", "weaponskill")
GREETING_LABELS = {"spawn": "When called", "levelup": "Level up", "death": "Knocked out", "weaponskill": "Weaponskill"}
GREETING_HELP = ("One line per greeting; one is picked at random. {master}, {zone} and {job} are filled in when the "
                 "mate speaks. Leave a box empty to use the mate's built-in voice lines for that moment.")
GREETINGS_MARKER = "-- Written by the XI: Forever Offline launcher (Squad tab > Greetings). It is rewritten when you save there."


def load_json(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def clean_greeting_lines(lines, limit=12):
    """One line per entry, no newlines, no blanks, and short enough for party chat."""
    out = []
    for line in lines or []:
        text = str(line).replace("\r", " ").replace("\n", " ").strip()
        if text:
            out.append(text[:160])
    return out[:limit]


def greeting_data(default_path, user_path):
    """Every mate's effective lines: the user's entries where given (even an empty list), else the built-in ones."""
    defaults = load_json(default_path)
    user = load_json(user_path)
    data = {}
    for name in sorted(set(defaults) | set(user)):
        built_in = defaults.get(name) if isinstance(defaults.get(name), dict) else {}
        edited = user.get(name) if isinstance(user.get(name), dict) else {}
        row = {}
        for event in GREETING_EVENTS:
            lines = edited[event] if event in edited else built_in.get(event)
            row[event] = clean_greeting_lines(lines)
        data[name] = row
    return data


def _write_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def save_greetings(user_path, name, lines_by_event):
    """Stores one mate's greetings as the user's own. A missing event keeps the built-in lines."""
    user = load_json(user_path)
    row = user.get(name) if isinstance(user.get(name), dict) else {}
    for event in GREETING_EVENTS:
        row[event] = clean_greeting_lines(lines_by_event.get(event))
    user[name] = row
    _write_json(user_path, user)
    return user


def clear_greetings(user_path, name):
    """Drops the user's lines for one mate, so the built-in ones are used again."""
    user = load_json(user_path)
    if name in user:
        del user[name]
        _write_json(user_path, user)
    return user


def rename_greetings(user_path, old, new):
    """Keeps a mate's own lines when the launcher renames them."""
    user = load_json(user_path)
    if old in user and new not in user:
        user[new] = user.pop(old)
        _write_json(user_path, user)
    return user


def write_greetings_lua(lua_path, data):
    """Writes the server's data file. Mates or moments with no lines are left out, so the voice lines are used."""
    import launcher_rules as lr
    clean = {}
    for name, row in data.items():
        events = {}
        for event in GREETING_EVENTS:
            lines = clean_greeting_lines((row or {}).get(event))
            if lines:
                events[event] = lines
        if events:
            clean[name] = events
    lr.write_lua(lua_path, clean, GREETINGS_MARKER)
    return clean


# (slot index, label) in a friendly display order
EQUIP_SLOTS = [
    (0, "Main"), (1, "Sub"), (2, "Range"), (3, "Ammo"),
    (4, "Head"), (9, "Neck"), (11, "Ear 1"), (12, "Ear 2"),
    (5, "Body"), (6, "Hands"), (13, "Ring 1"), (14, "Ring 2"),
    (15, "Back"), (10, "Waist"), (7, "Legs"), (8, "Feet"),
]


def connect(cfg):
    import mariadb  # installed with the server's Python requirements

    return mariadb.connect(
        host=cfg.get("db_host", "127.0.0.1"),
        port=int(cfg.get("db_port", 3306)),
        user=cfg["db_user"],
        password=cfg["db_pass"],
        database=cfg["db_name"],
        # The launcher keeps this connection open. Without autocommit, a plain
        # SELECT leaves a transaction open that holds a lock on the tables it read,
        # and database updates (like re-creating triggers) wait on it forever.
        autocommit=True,
    )


def _all(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def _run(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()


def pretty(item_name):
    return item_name.replace("_", " ").title() if item_name else ""


def list_characters(conn):
    """Only human characters; bot players are chars on reserved accounts too."""
    rows = _all(
        conn,
        "SELECT charid, charname FROM chars "
        "WHERE accid > 0 AND accid < ? ORDER BY charname",
        (BOT_ACCOUNT_BASE,),
    )
    try:        # co-op: a friend's character visiting this world is not one of yours (launcher_passport.py)
        guests = {int(r[0]) for r in _all(conn, "SELECT charid FROM coop_guest WHERE state <> 'gone'")}
    except Exception:       # (this database has never been used for co-op)
        guests = set()
    try:        # ...and one of yours that is away in a friend's world took its squad along: nothing to edit until it is home
        away = {int(r[0]) for r in _all(conn, "SELECT charid FROM coop_away WHERE state = 'away'")}
    except Exception:
        away = set()
    return [(int(r[0]), r[1]) for r in rows if int(r[0]) not in guests and int(r[0]) not in away]


def owner_has_support_jobs(conn, charid):
    """True when this character has support jobs (the quest done, or main level 18): squad.lua levelsFor then gives
    every mate its sub job from level 1 (FalconX51, 2026-11-22: the launcher only showed the sub from level 18)."""
    try:
        rows = _all(conn, "SELECT unlocked FROM char_jobs WHERE charid = ?", (charid,))
        if rows and int(rows[0][0] or 0) & 1:
            return True
        return char_level(conn, charid) >= SUB_UNLOCK_LEVEL
    except Exception:
        return False


def get_squad(conn, charid):
    mates = {}
    for r in _all(conn, "SELECT id, slot, name, race, face, mjob, sjob FROM squad_mate WHERE charid = ? ORDER BY slot", (charid,)):
        mates[int(r[0])] = {"id": int(r[0]), "slot": int(r[1]), "name": r[2], "race": int(r[3]), "face": int(r[4]),
                            "mjob": int(r[5]), "sjob": int(r[6]), "jobs": {}, "equip": {}}
    if not mates:
        return []
    owner_sub = owner_has_support_jobs(conn, charid)
    for mate in mates.values():
        mate["owner_sub"] = owner_sub
    for r in _all(conn, "SELECT squad_id, job, level, exp FROM squad_job WHERE squad_id IN (SELECT id FROM squad_mate WHERE charid = ?)", (charid,)):
        if int(r[0]) in mates:
            mates[int(r[0])]["jobs"][int(r[1])] = (int(r[2]), int(r[3]))
    for r in _all(conn, "SELECT e.squad_id, e.job, e.slot, e.itemid, i.name FROM squad_equip e "
                        "LEFT JOIN item_equipment i ON i.itemId = e.itemid "
                        "WHERE e.squad_id IN (SELECT id FROM squad_mate WHERE charid = ?)", (charid,)):
        if int(r[0]) in mates:
            mates[int(r[0])]["equip"].setdefault(int(r[1]), {})[int(r[2])] = (int(r[3]), r[4])
    return sorted(mates.values(), key=lambda m: m["slot"])


def job_level(mate, job):
    return mate["jobs"].get(job, (1, 0))[0]


# (2026-11-21, Bob Roberts) the server's map.SUBJOB_RATIO, as squad.lua uses it: 0 none, 1 half, 2 two thirds, 3 equal
SUBJOB_RATIO = 1


def read_subjob_ratio(server_dir):
    """Reads SUBJOB_RATIO from the server's settings/map.lua (1, half, if it can't be read)."""
    global SUBJOB_RATIO
    try:
        with open(os.path.join(server_dir, "settings", "map.lua"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"^\s*SUBJOB_RATIO\s*=\s*(\d+)", f.read(), re.M)
        SUBJOB_RATIO = int(m.group(1)) if m else 1
    except (OSError, TypeError, ValueError):
        SUBJOB_RATIO = 1
    return SUBJOB_RATIO


SUB_UNLOCK_LEVEL = 18       # squad.lua SUB_UNLOCK_LEVEL


def effective_levels(mate):
    """Main level, sub job and sub level, using the same rules as the game side (squad.lua levelsFor)."""
    main = job_level(mate, mate["mjob"])
    sub, sub_level = 0, 0
    ratio = SUBJOB_RATIO
    cap = main if ratio == 3 else main * 2 // 3 if ratio == 2 else 0 if ratio == 0 else main // 2
    if ratio != 0 and cap < 1:
        cap = 1         # a level 1 main job has a level 1 support job
    # the sub works once the mate's main job, or any of its jobs, is 18, or once its owner has support jobs
    unlocked = (main >= SUB_UNLOCK_LEVEL or bool(mate.get("owner_sub"))
                or any(level >= SUB_UNLOCK_LEVEL for level, _exp in mate.get("jobs", {}).values()))
    if mate["sjob"] and mate["sjob"] != mate["mjob"] and unlocked and cap > 0:
        sub = mate["sjob"]
        sub_level = max(1, min(job_level(mate, sub), cap))
    return main, sub, sub_level


def describe(mate):
    main, sub, sub_level = effective_levels(mate)
    text = f"{mate['slot']}. {mate['name']}  {JOBS[mate['mjob'] - 1]}{main}"
    if sub:
        text += f"/{JOBS[sub - 1]}{sub_level}"
    return text


def unlocked_jobs(conn, charid):
    """Job ids (1-15) this character may use: the starter jobs plus any advanced job they have unlocked."""
    rows = _all(conn, "SELECT unlocked FROM char_jobs WHERE charid = ?", (charid,))
    mask = int(rows[0][0]) if rows else 0
    return STARTER_JOBS | {j for j in range(7, 19) if (mask >> j) & 1}


def _require_unlocked(conn, charid, jobs, already=()):
    allowed = unlocked_jobs(conn, charid) | set(already)
    for job in jobs:
        if job and job not in allowed:
            raise ValueError(f"{JOBS[job - 1]} is an advanced job that has not been unlocked on this character yet.")


def create_mate(conn, charid, name, job, level):
    _require_unlocked(conn, charid, [job])
    taken = {int(r[0]) for r in _all(conn, "SELECT slot FROM squad_mate WHERE charid = ?", (charid,))}
    slot = next((s for s in range(1, MAX_SLOTS + 1) if s not in taken), None)
    if slot is None:
        raise ValueError(f"Your squad is full ({MAX_SLOTS}). Delete one first.")
    _run(conn, "INSERT INTO squad_mate (charid, slot, name, race, face, nation, mjob, sjob, template) VALUES (?, ?, ?, 1, 0, 0, ?, 0, 0)",
         (charid, slot, name, job))
    mate_id = int(_all(conn, "SELECT id FROM squad_mate WHERE charid = ? AND slot = ?", (charid, slot))[0][0])
    set_job_level(conn, mate_id, job, level, 0)
    return mate_id


NEW_MATE_MAX_LEVEL = 12      # same as squad.lua: a new mate may start at up to this level, never above the character


def char_level(conn, charid):
    rows = _all(conn, "SELECT mlvl FROM char_stats WHERE charid = ?", (charid,))
    return int(rows[0][0]) if rows and rows[0][0] is not None else 1


def new_mate_max_level(conn, charid):
    return max(1, min(NEW_MATE_MAX_LEVEL, char_level(conn, charid)))


def delete_mate(conn, mate_id):
    _run(conn, "DELETE FROM char_vars WHERE varname = ?", (look_var(mate_id),))
    for table in ("squad_equip", "squad_job"):
        _run(conn, f"DELETE FROM {table} WHERE squad_id = ?", (mate_id,))
    _run(conn, "DELETE FROM squad_mate WHERE id = ?", (mate_id,))


def rename_mate(conn, mate_id, name):
    _run(conn, "UPDATE squad_mate SET name = ? WHERE id = ?", (name, mate_id))


def look_var(mate_id):
    # the same character variable squad.lua sets on !squad look: a mate's look is picked once
    return f"SQUAD_LOOK_{int(mate_id)}"


def look_locked(conn, charid, mate_id):
    rows = _all(conn, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (charid, look_var(mate_id)))
    return bool(rows) and int(rows[0][0]) == 1


def lock_look(conn, charid, mate_id):
    _run(conn, "REPLACE INTO char_vars (charid, varname, value) VALUES (?, ?, 1)", (charid, look_var(mate_id)))


def set_look(conn, mate_id, race, face):
    _run(conn, "UPDATE squad_mate SET race = ?, face = ? WHERE id = ?", (race, face, mate_id))


def set_jobs(conn, charid, mate_id, mjob, sjob):
    if sjob == mjob:
        sjob = 0
    current = _all(conn, "SELECT mjob, sjob FROM squad_mate WHERE id = ?", (mate_id,))
    already = {int(current[0][0]), int(current[0][1])} if current else set()
    _require_unlocked(conn, charid, [mjob, sjob], already)
    _run(conn, "UPDATE squad_mate SET mjob = ?, sjob = ? WHERE id = ?", (mjob, sjob, mate_id))


def set_job_level(conn, mate_id, job, level, exp=0):
    level = max(1, min(MAX_LEVEL, int(level)))
    _run(conn, "REPLACE INTO squad_job (squad_id, job, level, exp) VALUES (?, ?, ?, ?)", (mate_id, job, level, exp))


def set_equip(conn, mate_id, job, slot, item_id):
    if not item_id:
        _run(conn, "DELETE FROM squad_equip WHERE squad_id = ? AND job = ? AND slot = ?", (mate_id, job, slot))
    else:
        _run(conn, "REPLACE INTO squad_equip (squad_id, job, slot, itemid) VALUES (?, ?, ?, ?)", (mate_id, job, slot, item_id))


def unlocked_count(conn, charid):
    # (itemid 60000+ = spells the squad learned from scrolls, not gear)
    return int(_all(conn, "SELECT COUNT(*) FROM squad_unlock WHERE charid = ? AND itemid < 60000", (charid,))[0][0])


# ----- item stats (Bob's suggestion, 2026-11-18): what a piece of gear gives, from the game database -----
# The modifier ids are named in the server's scripts/enum/mod.codegen.lua (DEF = 1, HP = 2, ... STR = 8 ...).
MOD_LABELS = {
    "DEF": "DEF", "HP": "HP", "MP": "MP", "STR": "STR", "DEX": "DEX", "VIT": "VIT", "AGI": "AGI", "INT": "INT",
    "MND": "MND", "CHR": "CHR", "ATT": "Attack", "RATT": "Ranged Attack", "ACC": "Accuracy", "RACC": "Ranged Accuracy",
    "EVA": "Evasion", "MATT": "Magic Atk. Bonus", "MACC": "Magic Accuracy", "MDEF": "Magic Def. Bonus",
    "MEVA": "Magic Evasion", "ENMITY": "Enmity", "HPP": "HP%", "MPP": "MP%", "STORETP": "Store TP",
    "DOUBLE_ATTACK": "Double Attack", "CRITHITRATE": "Critical hit rate", "REGEN": "Regen", "REFRESH": "Refresh",
    "FASTCAST": "Fast Cast", "CURE_POTENCY": "Cure potency", "HASTE_GEAR": "Haste", "SUBTLE_BLOW": "Subtle Blow",
}
PERCENT_HUNDREDTHS = {"HASTE_GEAR"}   # stored in 1/100 %
_mod_names = {}


def load_mod_names(server_dir):
    """{mod id: 'NAME'} from the server's mod enum (read once per server folder)."""
    if server_dir in _mod_names:
        return _mod_names[server_dir]
    names = {}
    path = os.path.join(server_dir or "", "scripts", "enum", "mod.codegen.lua")
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(-?\d+)\s*,", line)
                if m:
                    names.setdefault(int(m.group(2)), m.group(1))
    except OSError:
        pass
    _mod_names[server_dir] = names
    return names


def item_stats(conn, item_id, server_dir=""):
    """Lines describing an item: level and jobs, weapon damage and delay, and its stats (DEF:12, STR+2, Haste+3% ...)."""
    lines = []
    eq = _all(conn, "SELECT level, jobs FROM item_equipment WHERE itemId = ?", (item_id,))
    if eq:
        level, jobs = int(eq[0][0]), int(eq[0][1])
        names = [JOBS[i] for i in range(len(JOBS)) if (jobs >> i) & 1]
        job_text = "All jobs" if len(names) >= 15 else " ".join(names)
        lines.append(f"Lv{level}  {job_text}".rstrip())
    wpn = _all(conn, "SELECT dmg, delay FROM item_weapon WHERE itemId = ?", (item_id,))
    if wpn and int(wpn[0][0]) > 0:
        lines.append(f"DMG:{int(wpn[0][0])}  Delay:{int(wpn[0][1])}")
    names = load_mod_names(server_dir)
    stats = []
    for mod_id, value in _all(conn, "SELECT modId, value FROM item_mods WHERE itemId = ? ORDER BY modId", (item_id,)):
        name = names.get(int(mod_id), f"mod {mod_id}")
        label = MOD_LABELS.get(name, name.replace("_", " ").title())
        value = int(value)
        if name in PERCENT_HUNDREDTHS:
            stats.append(f"{label}{'+' if value >= 0 else ''}{value / 100:g}%")
        elif name == "DEF":
            stats.append(f"DEF:{value}")
        else:
            stats.append(f"{label}{'+' if value >= 0 else ''}{value}")
    if stats:
        lines.append(" ".join(stats))
    return lines


SEARCH_LIMIT = 600


def search_items(conn, slot, job, max_level, text, charid=None, require_unlock=False, limit=SEARCH_LIMIT):
    """Equipment that fits `slot`. job/max_level filter to what that job can wear at that level (pass 0 to skip).
    Highest level first. (2026-11-22, Gilder: a level 21 Warrior's Main list stopped at level 12. The list was the
    first 300 from level 1 up, and a Warrior can hold so many kinds of weapon that 300 ran out at level 12; a Monk's
    shorter list reached further.) The cut now falls on the low levels, which matter least."""
    sql = "SELECT i.itemId, i.name, i.level FROM item_equipment i WHERE (i.slot & ?) <> 0"
    params = [1 << slot]
    if job:
        sql += " AND ((i.jobs >> ?) & 1) = 1"
        params.append(job - 1)
    if max_level:
        sql += " AND i.level <= ?"
        params.append(max_level)
    if text:
        sql += " AND i.name LIKE ?"
        params.append("%" + text.strip().replace(" ", "_").replace("%", "") + "%")
    if require_unlock:
        sql += " AND i.itemId IN (SELECT itemid FROM squad_unlock WHERE charid = ?)"
        params.append(charid)
    sql += " ORDER BY i.level DESC, i.name LIMIT ?"
    params.append(limit)
    return [(int(r[0]), r[1], int(r[2])) for r in _all(conn, sql, tuple(params))]


# ----- roles and modes -----
def behavior_var(mate_id):
    return f"SQUAD_AI_{int(mate_id)}"


def encode_behavior(role, mode):
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    return ROLES.index(role) * 10 + MODES.index(mode)


def decode_behavior(code):
    """The server's rule: anything it does not understand means auto / balanced."""
    try:
        code = int(code or 0)
    except (TypeError, ValueError):
        code = 0
    role_index, mode_index = divmod(code, 10)
    return (ROLES[role_index] if 0 <= role_index < len(ROLES) else "auto", MODES[mode_index] if 0 <= mode_index < len(MODES) else "balanced")


def get_behavior(conn, charid, mate_id):
    rows = _all(conn, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (int(charid), behavior_var(mate_id)))
    return decode_behavior(rows[0][0]) if rows else ("auto", "balanced")


def set_behavior(conn, charid, mate_id, role, mode):
    """Stores a mate's role and mode. auto + balanced is the default, so it removes the variable (the server does the same for a zero)."""
    code = encode_behavior(role, mode)
    name = behavior_var(mate_id)
    if code == 0:
        _run(conn, "DELETE FROM char_vars WHERE charid = ? AND varname = ?", (int(charid), name))
        return code
    cur = conn.cursor()
    cur.execute("SELECT * FROM char_vars LIMIT 0")
    columns = [d[0] for d in cur.description]
    missing = [c for c in ("charid", "varname", "value") if c not in columns]
    if missing:
        cur.close()
        raise RuntimeError("the char_vars table has no " + ", ".join(missing) + " column, so this game's variables are stored differently")
    cur.execute("UPDATE char_vars SET value = ? WHERE charid = ? AND varname = ?", (code, int(charid), name))
    if cur.rowcount == 0:
        values = {"charid": int(charid), "varname": name, "value": code}
        if "expiry" in columns:
            values["expiry"] = 0                       # never expires
        names = list(values)
        cur.execute(f"INSERT INTO char_vars ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})", [values[n] for n in names])
    conn.commit()
    cur.close()
    return code
