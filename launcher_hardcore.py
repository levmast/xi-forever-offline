"""HARDCORE (2026-11-23, the user): Iron, Steel and Silver characters, and the menu that makes and plays them.

What the server does is in the server's modules/custom/late/hardcore.lua (rules, deaths, milestones, announcements) and
modules/custom/cpp/hardcore.cpp + src/map/utils/hardcoreutils.h (the rates, the auction house, trades, the delivery box,
parties). This file is the launcher's part:

  * the three rate profiles (hardcore_profiles.json in the kit folder, the user's Ironman / Steel / Silver builds)
  * at every PLAY: modules/custom/lua/hardcore_profiles.lua (the character rates of each mode, which follow the character
    anywhere) and hardcore_world.lua (this world's hardcore switches); with PLAY HARDCORE also the mode's world rules for
    that session (rates.json, your own rules, is not changed)
  * hardcore_pending.lua: a name and a mode; the character with that name becomes hardcore the first time it logs in,
    if it has not gained a level yet
  * the Hardcore menu (the HARDCORE button beside DUALBOX): a card per hardcore character, the mode pick screen,
    step down, the host's "hardcore visitors only" switch, sharing milestones online
  * a fallen Silver character is deleted 7 days after its death (the same way the game deletes one: accid 0)
  * the announcer: the server's hardcore_out.txt lines go to the relay on the hub server (chat.xiforever.com, the same
    one Stinkshell uses, as kind "hardcore"); an open world (the hub) shows the other worlds' lines from hardcore_in.txt

No tkinter needed for the parts above the "the menu" line (tests: dev/launcher-tests/test_hardcore.py).
"""
import datetime
import json
import os
import re
import threading
import time
import urllib.request

KIT_FILE = "hardcore_profiles.json"
SETTINGS_FILE = "hardcore.json"
STATE_FILE = "hardcore_state.json"
RELAY = "https://chat.xiforever.com"

MODES = {1: "Iron", 2: "Steel", 3: "Silver", 4: "Randomized"}
KEYS = {1: "iron", 2: "steel", 3: "silver", 4: "random"}
HARDCORE = (1, 2, 3)                 # 4 = Randomized is not hardcore (auction house, trades, normal deaths)
LOCK_DAYS = 7
NAME_RE = re.compile(r"^[A-Za-z]{3,15}$")
JOB_COLUMNS = ("war", "mnk", "whm", "blm", "rdm", "thf", "pld", "drk", "bst", "brd", "rng", "sam", "nin", "drg", "smn",
               "blu", "cor", "pup", "dnc", "sch", "geo", "run")
JOB_NAMES = [c.upper() for c in JOB_COLUMNS]

# the rates that belong to the character (they go with it to co-op worlds and the hub); the server reads these
CHAR_KEYS = ("map.EXP_RATE", "map.DROP_RATE_MULTIPLIER", "map.MOB_GIL_MULTIPLIER", "map.ALL_MOBS_GIL_BONUS",
             "map.SKILLUP_CHANCE_MULTIPLIER", "map.BLUE_LEARN_MULTIPLIER", "map.CRAFT_CHANCE_MULTIPLIER",
             "map.CRAFT_HQ_CHANCE_MULTIPLIER", "map.FISHING_SKILL_MULTIPLIER", "main.GIL_RATE", "main.TABS_RATE",
             "main.BOOK_EXP_RATE", "main.CASKET_DROP_RATE", "main.HOMEPOINT_TELEPORT", "main.ENABLE_SURVIVAL_GUIDE",
             "main.TM_CARD_DROP_RATE", "main.TM_CASKET_CARD_RATE", "main.TM_GIL_RATE", "main.TM_PRICE_RATE",
             "main.DIG_SKILL_RATE")
# never taken from a hardcore profile: the player's own choices for their world (the user: bots are a separate choice)
OWN_CHOICES = ("bots", "bots_roster", "bots_online", "bots_growth", "bots_pass_loot", "bot_social", "bot_memory", "bot_story",
               "bot_gates", "crowds", "crowds_per_zone", "crowds_chat", "crowds_chat_amount", "crowds_chat_ai", "crowds_field",
               "crowds_field_parties", "crowd_gates", "crowd_meet", "events", "event_harvest", "event_starlight",
               "event_egg_hunt", "event_horro")
# the user's rules, whatever a profile file says: Steel and Silver never teleport
FIXED = {2: {"main.HOMEPOINT_TELEPORT": 0, "main.ENABLE_SURVIVAL_GUIDE": 0},
         3: {"main.HOMEPOINT_TELEPORT": 0, "main.ENABLE_SURVIVAL_GUIDE": 0}}

RULES = {
    1: ["Rates locked to the Iron profile (1x experience)", "No auction house, bazaars, trades or deliveries from other characters",
        "Parties with anyone, bot players too", "A cosmetic reward every 10 levels", "Can step down to a regular character"],
    2: ["Rates locked to the Steel profile (2x experience)", "No auction house, trades or Home Point / Survival Guide teleports",
        "Knocked out: the job you are on goes back to level 1", "Parties only with Iron, Steel and Silver characters (squad mates, no bots)",
        "2 cosmetic rewards every 10 levels", "Can step down to Iron"],
    3: ["Rates locked to the Silver profile (3.5x experience)", "No auction house, trades or Home Point / Survival Guide teleports",
        "Knocked out: the character is gone for good (deleted after 7 days)", "Parties only with Iron, Steel and Silver characters (squad mates, no bots)",
        "3 cosmetic rewards every 10 levels", "Can step down to Iron"],
    4: ["Rates locked to the Randomized profile (2.5x experience)", "You pick only the name: race, face, size and nation are rolled",
        "One random job to start, another at 18, 33 and 65 (of the 18 era jobs); only those can be played",
        "Job quests still unlock jobs for your squad mates", "Drops, chests, caskets and battlefield crates are random but fit",
        "Its own auction house (stock rotates, prices swing 20% more); trading, normal deaths, any party"],
}


# ---------------------------------------------------------------- profiles and settings
def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def _write_json(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
    os.replace(tmp, path)


def profiles(kit):
    """{1: rates, 2: rates, 3: rates} from hardcore_profiles.json (the user's three builds)."""
    data = _read_json(os.path.join(kit, KIT_FILE), {})
    out = {}
    for mode, key in KEYS.items():
        block = data.get(key, {})
        rates = block.get("rates", block) if isinstance(block, dict) else {}
        rates = dict(rates) if isinstance(rates, dict) else {}
        rates.update(FIXED.get(mode, {}))
        out[mode] = rates
    return out


def settings(kit):
    value = _read_json(os.path.join(kit, SETTINGS_FILE), {})
    value.setdefault("hardcore_only", False)
    value.setdefault("share", True)
    value.setdefault("pending", [])
    return value


def save_settings(kit, value):
    _write_json(os.path.join(kit, SETTINGS_FILE), value)


def session_rates(kit, rates, mode):
    """The rates PLAY HARDCORE starts the world with: yours, with the mode's profile over them (your bot and crowd choices
    stay). rates.json is not changed."""
    if mode not in MODES:
        return rates
    out = dict(rates)
    for key, value in profiles(kit)[mode].items():
        if key not in OWN_CHOICES:
            out[key] = value
    if mode in HARDCORE:
        out["ah_sim"] = False                 # nobody here may use the auction house anyway (Randomized may: it keeps it)
    return out


def _lua_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return ("%g" % number) if number == number else None


def profiles_lua(kit):
    lines = ["-- Written by the XI: Forever Offline launcher (HARDCORE) at every PLAY, from hardcore_profiles.json. Do not edit.",
             "-- The character rates of each hardcore mode (1 = Iron, 2 = Steel, 3 = Silver); custom/late/hardcore.lua reads it.",
             "return {"]
    for mode, rates in profiles(kit).items():
        parts = []
        for key in CHAR_KEYS:
            if key in rates:
                value = _lua_value(rates[key])
                if value is not None:
                    parts.append(f"['{key}'] = {value}")
        lines.append(f"    [{mode}] = {{ " + ", ".join(parts) + " },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def _lua_string(text):
    return "'" + str(text).replace("\\", "").replace("'", "\\'").replace("\n", " ") + "'"


def world_lua(kit, is_open=False, world_name=""):
    s = settings(kit)
    return ("-- Written by the XI: Forever Offline launcher (HARDCORE menu) at every PLAY. Do not edit.\n"
            f"return {{ hardcore_only = {_lua_value(bool(s['hardcore_only']))}, hub = {_lua_value(bool(is_open))}, "
            f"share = {_lua_value(bool(s['share']))}, world = {_lua_string(world_name)} }}\n")


def pending_lua(kit):
    entries = [e for e in settings(kit)["pending"] if isinstance(e, dict) and NAME_RE.match(str(e.get("name", "")))
               and e.get("mode") in MODES]
    body = ", ".join(f"{{ name = {_lua_string(e['name'])}, mode = {int(e['mode'])} }}" for e in entries)
    return ("-- Written by the XI: Forever Offline launcher (HARDCORE menu). These characters become hardcore the first time they\n"
            "-- log in, if they have not gained a level yet. Do not edit.\n"
            f"return {{ {body} }}\n")


def _module_dir(server_dir):
    return os.path.join(server_dir, "modules", "custom", "lua")


def write_server_files(kit, server_dir, is_open=False, world_name=""):
    """hardcore_profiles.lua, hardcore_world.lua and hardcore_pending.lua for the server. Returns a list of problems."""
    problems = []
    if not server_dir:
        return ["no server folder"]
    folder = _module_dir(server_dir)
    for name, text in (("hardcore_profiles.lua", profiles_lua(kit)), ("hardcore_world.lua", world_lua(kit, is_open, world_name)),
                       ("hardcore_pending.lua", pending_lua(kit))):
        try:
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except OSError as problem:
            problems.append(f"{name}: {problem}")
    return problems


def add_pending(kit, server_dir, name, mode, charid=None):
    s = settings(kit)
    s["pending"] = [e for e in s["pending"] if isinstance(e, dict) and str(e.get("name", "")).lower() != name.lower()]
    entry = {"name": name, "mode": int(mode), "at": int(time.time())}
    if charid:
        entry["charid"] = int(charid)
    s["pending"].append(entry)
    save_settings(kit, s)
    if server_dir:
        with open(os.path.join(_module_dir(server_dir), "hardcore_pending.lua"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(pending_lua(kit))


def forget_pending(kit, names):
    names = {n.lower() for n in names}
    s = settings(kit)
    before = len(s["pending"])
    s["pending"] = [e for e in s["pending"] if isinstance(e, dict) and str(e.get("name", "")).lower() not in names]
    if len(s["pending"]) != before:
        save_settings(kit, s)


# ---------------------------------------------------------------- the database (launcher_passport's connection)
def _all(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def prune_pending(kit, conn, bot_base=21000000):
    """(2026-11-24) Drops waiting entries whose character was deleted, so a deleted character doesn't stay on the
    Hardcore list as "waiting for its first log in" (Kandra), and a new character that later takes the same name isn't
    turned hardcore by an old entry. An entry's character is remembered (charid) the first time it is seen.
    - Randomized (mode 4): the launcher makes the character before the entry is added, so no character = deleted.
    - Iron / Steel / Silver: the player may not have made the character yet (it is made on the game's creation
      screen), so the entry is only dropped once its character was seen and is now gone (or the name is someone else's).
    A character counts while its chars row has a player account (0 < accid < bot_base). Returns the names dropped."""
    s = settings(kit)
    cur = conn.cursor()
    try:
        keep, dropped, changed = [], [], False
        for e in s["pending"]:
            if not isinstance(e, dict):
                changed = True
                continue
            name = str(e.get("name", ""))
            rows = _all(cur, "SELECT charid FROM chars WHERE charname LIKE ? AND accid > 0 AND accid < ? LIMIT 1", (name, bot_base))
            now_id = int(rows[0][0]) if rows else None
            seen = e.get("charid")
            if now_id is None:
                if int(e.get("mode", 0)) == 4 or seen:
                    dropped.append(name)
                    changed = True
                    continue
            elif seen and int(seen) != now_id:
                dropped.append(name)
                changed = True
                continue
            elif not seen:
                e["charid"] = now_id
                changed = True
            keep.append(e)
        if changed:
            s["pending"] = keep
            save_settings(kit, s)
        return dropped
    finally:
        cur.close()
        conn.rollback()


def _columns(cur, table):
    try:
        return [r[0] for r in _all(cur, f"SHOW COLUMNS FROM `{table}`")]
    except Exception:
        return []


def survival_text(seconds):
    seconds = max(0, int(seconds or 0))
    days, hours, minutes = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def characters(conn, bot_base=21000000, now=None):
    """The hardcore characters of this world: [{charid, name, mode, job, level, start, dead, deaths, resets, milestones,
    online, left (seconds until a fallen Silver is deleted)}], newest first."""
    now = now or time.time()
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT c.charid, c.charname, v.varname, v.value FROM chars c JOIN char_vars v ON v.charid = c.charid "
                         "WHERE v.varname LIKE ? AND c.accid > 0 AND c.accid < ?", ("[HC]%", bot_base))
        found = {}
        for charid, name, var, value in rows:
            entry = found.setdefault(int(charid), {"charid": int(charid), "name": str(name), "vars": {}})
            entry["vars"][str(var)] = int(value)
        jobs = [c for c in JOB_COLUMNS if c in _columns(cur, "char_jobs")]
        out = []
        for charid, entry in found.items():
            v = entry["vars"]
            mode = v.get("[HC]Mode", 0)
            if mode not in MODES:
                continue
            mjob, level = 0, 1
            stats = _all(cur, "SELECT mjob FROM char_stats WHERE charid = ?", (charid,))
            if stats:
                mjob = int(stats[0][0] or 0)
            if jobs and 1 <= mjob <= len(JOB_COLUMNS) and JOB_COLUMNS[mjob - 1] in jobs:
                got = _all(cur, f"SELECT `{JOB_COLUMNS[mjob - 1]}` FROM char_jobs WHERE charid = ?", (charid,))
                if got:
                    level = int(got[0][0] or 1)
            online = bool(_all(cur, "SELECT 1 FROM accounts_sessions WHERE charid = ? LIMIT 1", (charid,)))
            dead = v.get("[HC]Dead", 0)
            milestones = {JOB_NAMES[int(k[6:]) - 1]: val for k, val in v.items()
                          if k.startswith("[HC]MS") and k[6:].isdigit() and 1 <= int(k[6:]) <= len(JOB_NAMES) and val > 0}
            out.append({"charid": charid, "name": entry["name"], "mode": mode, "job": JOB_NAMES[mjob - 1] if 1 <= mjob <= len(JOB_NAMES) else "",
                        "level": level, "start": v.get("[HC]Start", 0), "dead": dead, "deaths": v.get("[HC]Deaths", 0),
                        "resets": v.get("[HC]Resets", 0), "milestones": milestones, "online": online,
                        "left": max(0, LOCK_DAYS * 86400 - (now - dead)) if (mode == 3 and dead) else None})
        out.sort(key=lambda e: -e["start"])
        return out
    finally:
        cur.close()
        conn.rollback()


# ---------------------------------------------------------------- Randomized: the launcher makes the character
# (2026-11-23, the user) A Randomized character skips the game's character creation: the player types only the name, and
# the launcher writes the new character the way the login server does (login_helpers.cpp saveCharacter; the chars
# insert trigger adds the rest) with a random race, face, size and nation, and one of the nation's three starting
# cities, as the login server picks it. "[HC]Looks" = 1 tells the server the looks are already rolled; the job is
# rolled at the first login, as before. The pending list makes it Randomized at that login.
NATIONS = {0: "San d'Oria", 1: "Bastok", 2: "Windurst"}
START_ZONES = {0: (230, 231, 232), 1: (234, 235, 236), 2: (238, 240, 241)}
RACES = {1: "Hume", 2: "Hume", 3: "Elvaan", 4: "Elvaan", 5: "Tarutaru", 6: "Tarutaru", 7: "Mithra", 8: "Galka"}
CHAR_ID_LIMIT = 16000000           # bot characters start here (login_helpers.cpp)


class CreateError(Exception):
    """Why a character could not be made, in words for the player."""


def roll_randomized(rng=None):
    import random
    rng = rng or random.SystemRandom()
    nation = rng.randrange(3)
    return {"race": rng.randint(1, 8), "face": rng.randint(0, 15), "size": rng.randint(0, 2), "nation": nation,
            "zone": rng.choice(START_ZONES[nation])}


def _opening_cutscene(server_dir):
    """main.NEW_CHARACTER_CUTSCENE from the server's settings (settings/main.lua over settings/default/main.lua)."""
    for rel in (("settings", "main.lua"), ("settings", "default", "main.lua")):
        try:
            with open(os.path.join(server_dir or "", *rel), encoding="utf-8") as handle:
                match = re.search(r"NEW_CHARACTER_CUTSCENE\s*=\s*(\w+)", handle.read())
            if match:
                return match.group(1) not in ("0", "false")
        except OSError:
            continue
    return False


def create_randomized(conn, login, name, server_dir=None, rng=None):
    """Makes the character `name` on the game account `login`; returns (charid, roll). Raises CreateError."""
    if not NAME_RE.match(name or ""):
        raise CreateError("A character name is 3 to 15 letters (A-Z), no spaces.")
    name = name[0].upper() + name[1:].lower()
    cur = conn.cursor()
    try:
        row = _all(cur, "SELECT id, content_ids FROM accounts WHERE login = ?", (login,))
        if not row:
            raise CreateError(f"The game account '{login}' is not in this world's database.")
        accid, slots = int(row[0][0]), int(row[0][1] or 16)
        # (2026-11-24, datadecay) a character deleted in the game stays in the table under its name (accid = 0): free
        # the name the way free_names.py does (Del<id><name>), as making a character in the game already does
        for row in _all(cur, "SELECT charid FROM chars WHERE charname LIKE ? AND accid = 0", (name,)):
            cur.execute("UPDATE chars SET charname = ? WHERE charid = ? AND accid = 0",
                        (("Del" + str(int(row[0])) + name)[:15], int(row[0])))
        if _all(cur, "SELECT 1 FROM chars WHERE charname LIKE ? LIMIT 1", (name,)):
            raise CreateError(f"The name {name} is already taken in this world.")
        count = int(_all(cur, "SELECT COUNT(*) FROM chars WHERE accid = ?", (accid,))[0][0])
        if count >= slots:
            raise CreateError(f"Your account already has {count} characters, the most it can hold.")
        charid = int(_all(cur, "SELECT COALESCE(MAX(charid), 0) FROM chars WHERE charid < ?", (CHAR_ID_LIMIT,))[0][0]) + 1
        roll = roll_randomized(rng)
        cur.execute("INSERT INTO chars(charid, accid, charname, pos_zone, nation) VALUES(?, ?, ?, ?, ?)",
                    (charid, accid, name, roll["zone"], roll["nation"]))
        cur.execute("INSERT INTO char_look(charid, face, race, size) VALUES(?, ?, ?, ?)",
                    (charid, roll["face"], roll["race"], roll["size"]))
        cur.execute("INSERT INTO char_stats(charid, mjob) VALUES(?, ?)", (charid, 1))
        for table, keep in (("char_exp", "charid"), ("char_flags", "disconnecting"), ("char_jobs", "charid"),
                            ("char_points", "charid"), ("char_unlocks", "charid"), ("char_profile", "charid"),
                            ("char_storage", "charid")):
            cur.execute(f"INSERT INTO {table}(charid) VALUES(?) ON DUPLICATE KEY UPDATE {keep} = {keep}", (charid,))
        cur.execute("DELETE FROM char_inventory WHERE charid = ?", (charid,))
        cur.execute("INSERT INTO char_inventory(charid) VALUES(?)", (charid,))
        if _opening_cutscene(server_dir):
            cur.execute("INSERT INTO char_vars(charid, varname, value) VALUES(?, ?, ?)", (charid, "HQuest[newCharacterCS]notSeen", 1))
        cur.execute("INSERT INTO char_vars(charid, varname, value) VALUES(?, ?, ?) ON DUPLICATE KEY UPDATE value = VALUES(value)",
                    (charid, "[HC]Looks", 1))
        conn.commit()
        return charid, roll
    except CreateError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def eligible(conn, bot_base=21000000):
    """[(charid, name)] of this world's own characters that could still become hardcore: no job above level 1, not one
    already, not a visitor."""
    cur = conn.cursor()
    try:
        jobs = [c for c in JOB_COLUMNS if c in _columns(cur, "char_jobs")]
        if not jobs:
            return []
        top = "GREATEST(" + ", ".join(f"j.`{c}`" for c in jobs) + ")" if len(jobs) > 1 else f"j.`{jobs[0]}`"
        guest = " AND c.charid NOT IN (SELECT charid FROM coop_guest WHERE state <> 'gone')" if _columns(cur, "coop_guest") else ""
        rows = _all(cur, f"SELECT c.charid, c.charname FROM chars c JOIN char_jobs j ON j.charid = c.charid "
                         f"WHERE c.accid > 0 AND c.accid < ? AND {top} <= 1{guest} AND c.charid NOT IN "
                         f"(SELECT charid FROM char_vars WHERE varname = ? AND value > 0) ORDER BY c.charname",
                    (bot_base, "[HC]Mode"))
        return [(int(r[0]), str(r[1])) for r in rows]
    finally:
        cur.close()
        conn.rollback()


def step_down(conn, charid):
    """Silver / Steel -> Iron, Iron -> a regular character. The character must be logged out. Returns the new mode."""
    cur = conn.cursor()
    try:
        if _all(cur, "SELECT 1 FROM accounts_sessions WHERE charid = ? LIMIT 1", (charid,)):
            raise RuntimeError("Log that character out first.")
        got = _all(cur, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (charid, "[HC]Mode"))
        mode = int(got[0][0]) if got else 0
        dead = _all(cur, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (charid, "[HC]Dead"))
        if mode == 3 and dead and int(dead[0][0]) > 0:
            raise RuntimeError("A fallen Silver character can't step down.")
        if mode in (2, 3):
            cur.execute("UPDATE char_vars SET value = 1 WHERE charid = ? AND varname = ?", (charid, "[HC]Mode"))
            cur.execute("DELETE FROM char_vars WHERE charid = ? AND varname = ?", (charid, "[HC]Reset"))
            new = 1
        elif mode == 1:
            cur.execute("DELETE FROM char_vars WHERE charid = ? AND varname = ?", (charid, "[HC]Mode"))
            new = 0
        elif mode == 4:
            raise RuntimeError("A Randomized character stays Randomized.")
        else:
            raise RuntimeError("That character is not hardcore.")
        conn.commit()
        return new
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def restore(conn, charid):
    """The dev PC only: a Silver character that fell to a bug is alive again."""
    cur = conn.cursor()
    try:
        cur.execute("UPDATE char_vars SET value = 0 WHERE charid = ? AND varname = ?", (charid, "[HC]Dead"))
        conn.commit()
    finally:
        cur.close()


def expire_fallen(conn, bot_base=21000000, now=None):
    """Silver characters that fell 7 or more days ago are deleted the way the game deletes one (taken off the account;
    the login server frees the name). Returns their names."""
    now = int(now or time.time())
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT c.charid, c.charname FROM chars c JOIN char_vars m ON m.charid = c.charid AND m.varname = ? AND m.value = 3 "
                         "JOIN char_vars d ON d.charid = c.charid AND d.varname = ? AND d.value > 0 AND d.value <= ? "
                         "WHERE c.accid > 0 AND c.accid < ?", ("[HC]Mode", "[HC]Dead", now - LOCK_DAYS * 86400, bot_base))
        gone = []
        has_original = "original_accid" in _columns(cur, "chars")
        for charid, name in rows:
            if _all(cur, "SELECT 1 FROM accounts_sessions WHERE charid = ? LIMIT 1", (charid,)):
                continue
            if has_original:
                cur.execute("UPDATE chars SET original_accid = accid, accid = 0 WHERE charid = ?", (charid,))
            else:
                cur.execute("UPDATE chars SET accid = 0 WHERE charid = ?", (charid,))
            gone.append(str(name))
        conn.commit()
        return gone
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------- the announcer (hub and Stinkshell)
def parse_out_line(line):
    parts = line.rstrip("\n").split("|")
    if len(parts) < 8:
        return None
    try:
        when, level = int(parts[0]), int(parts[5])
    except ValueError:
        return None
    return {"t": when, "kind": parts[1], "name": parts[2], "mode": parts[3], "job": parts[4], "level": level,
            "extra": parts[6], "world": parts[7]}


class Announcer:
    """Sends this world's hardcore lines to the relay, and (an open world) shows the other worlds' lines. One thread,
    a look every 15 seconds; nothing goes online while sharing is off."""

    def __init__(self, kit, server_dir, key, is_open=lambda: False, url=RELAY, opener=None, log=None):
        self.kit, self.server_dir, self.key, self.is_open = kit, server_dir, key, is_open
        self.url, self.opener, self.log = url.rstrip("/"), opener, log or (lambda text: None)
        self.stop_flag = threading.Event()
        self.mine = {}                                     # names this world sent lately -> time (not shown twice here)

    def call(self, method, path, body=None):
        if self.opener:
            return self.opener(method, path, body)
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method,
                                         headers={"X-Stink-Key": self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read(200000) or b"{}")

    def state(self):
        return _read_json(os.path.join(self.kit, STATE_FILE), {})

    def save_state(self, value):
        try:
            _write_json(os.path.join(self.kit, STATE_FILE), value)
        except OSError:
            pass

    def send_new(self):
        path = os.path.join(_module_dir(self.server_dir), "hardcore_out.txt")
        try:
            size = os.path.getsize(path)
        except OSError:
            return 0
        st = self.state()
        offset = int(st.get("out_offset", 0))
        if offset > size:                                   # the file was emptied or replaced
            offset = 0
        if offset == size:
            return 0
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            text = handle.read()
            offset = handle.tell()
        sent = 0
        if settings(self.kit)["share"]:
            for line in text.splitlines():
                entry = parse_out_line(line)
                if not entry or time.time() - entry["t"] > 3 * 86400:
                    continue
                try:
                    answer = self.call("POST", "/announce", {k: entry[k] for k in ("kind", "name", "mode", "job", "level", "extra", "world")})
                except Exception as problem:
                    self.log(f"Hardcore: could not reach the hub to share {entry['name']}'s news ({problem}); trying again later.")
                    return sent                              # keep the offset: try again next time
                if answer.get("ok"):
                    sent += 1
                    self.mine[entry["name"].lower()] = time.time()
        st["out_offset"] = offset
        self.save_state(st)
        return sent

    def fetch_others(self):
        if not self.is_open():
            return 0
        st = self.state()
        since = int(st.get("in_seq", 0))
        try:
            answer = self.call("GET", f"/announcements?since={since}")
        except Exception:
            return 0
        lines = answer.get("lines") or []
        now = time.time()
        fresh = []
        for line in lines:
            text = str(line.get("text", ""))
            name = text.split(" ", 1)[0].lower()
            if since and text and now - self.mine.get(name, 0) > 600:   # (the first look only notes where the room is)
                fresh.append((int(line.get("seq", 0)), text))
        st["in_seq"] = int(answer.get("seq", since))
        self.save_state(st)
        if fresh:
            path = os.path.join(_module_dir(self.server_dir), "hardcore_in.txt")
            try:
                with open(path, "a", encoding="utf-8", newline="\n") as handle:
                    for seq, text in fresh:
                        handle.write("%d|%s\n" % (seq, text.replace("|", " ")))
            except OSError:
                pass
        return len(fresh)

    def run(self):
        while not self.stop_flag.wait(15):
            try:
                self.send_new()
                self.fetch_others()
            except Exception:
                pass

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="hardcore-announcer").start()

    def stop(self):
        self.stop_flag.set()
