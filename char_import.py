#!/usr/bin/env python3
"""Character transfer: bring a character from retail or another private server into your XI: Forever Offline world.

The character is read on the other game by the VanaDreams team's charcapture add-on (used with their permission):
/capture writes Ashita/config/charcapture/<Name>.json there. This file puts that snapshot onto a character you have
already made here (make it in the lobby first, then log out), like this:

  python char_import.py preview <snapshot.json> [--max-level 75]      what would come across, changes nothing
  python char_import.py import  <snapshot.json> <character here> [--max-level 75]
  python char_import.py install-capture <other Ashita folder>          put charcapture into that Ashita's addons

What comes across: job levels (capped at this world's level cap; jobs after Treasures of Aht Urhgan are left out),
main and support job, combat and crafting skills, spells, key items, gil, every bag with augments, the gear you wore,
race, face and size, nation, rank and title. Not: quests, missions, fame, merits, linkshells, mog house layout.
The character's own jobs, skills, spells, key items and bags here are REPLACED. A backup of the character is written
to backups/ first (and the launcher's Characters page can put it back).
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

JOBS = ("war", "mnk", "whm", "blm", "rdm", "thf", "pld", "drk", "bst", "brd", "rng", "sam", "nin", "drg", "smn", "blu",
        "cor", "pup", "dnc", "sch", "geo", "run")
ERA_LAST_JOB = 18                 # PUP; DNC, SCH (Wings of the Goddess) and later are left out
GENKAI_STEPS = (50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 99)
CRAFT_BASE = 48                   # Ashita's craft index 0 (fishing) = the server's skill 48
CRAFT_CAP = 100
COMBAT_CAP = {75: 276, 99: 424}   # the best (A+) cap at the level cap; skills from a higher-level world come down to it
# containers: the game's ids (LandSandBoat uses the same); the char_storage column that sizes each, None = not used
CONTAINERS = {0: "inventory", 1: "safe", 9: "safe", 4: "locker", 5: "satchel", 6: "sack", 7: "case", 8: "wardrobe",
              10: "wardrobe2", 11: "wardrobe3", 12: "wardrobe4", 13: "wardrobe5", 14: "wardrobe6", 15: "wardrobe7",
              16: "wardrobe8"}
FILL_ORDER = (0, 1, 9, 4, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16)
KEY_TABLES, KEY_TABLE_BITS = 8, 512
TITLE_BYTES = 143

# charcapture, pinned to the commit Hurami was given permission for
CAPTURE_REPO, CAPTURE_REF = "VanaDreams/vanadreams-launcher", "24bf06c9c77b60a50568a2feb4e6ae1f747ad951"


class ImportError_(Exception):
    pass


# ---------------------------------------------------------------- the snapshot
def load_snapshot(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            snap = json.load(handle)
    except (OSError, ValueError) as e:
        raise ImportError_(f"Could not read {path}: {e}")
    if not isinstance(snap, dict) or snap.get("addon") != "charcapture" or "character" not in snap or "jobs" not in snap:
        raise ImportError_("That file is not a charcapture snapshot (made with /capture).")
    return snap


def server_max_level(server_dir, default=75):
    """The world's level cap: MAX_LEVEL in server/settings/main.lua (the launcher's), else the default file."""
    for name in ("settings/main.lua", "settings/default/main.lua"):
        try:
            with open(os.path.join(server_dir or "", name), "r", encoding="utf-8") as handle:
                found = re.search(r"^\s*MAX_LEVEL\s*=\s*(\d+)", handle.read(), re.M)
            if found:
                return min(int(found.group(1)), 99)
        except OSError:
            continue
    return default


def _known(cur, sql, ids):
    ids = sorted(set(int(i) for i in ids))
    if not ids:
        return set()
    found = set()
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        cur.execute(sql.format(",".join("?" * len(chunk))), chunk)
        found.update(int(r[0]) for r in cur.fetchall())
    return found


def plan(conn, snap, charid, max_level=75):
    """Works out exactly what will be written for this character. Changes nothing."""
    cur = conn.cursor()
    report = {"kept": [], "left_out": []}
    jobs = snap.get("jobs") or {}
    levels = {}
    for key, value in (jobs.get("levels") or {}).items():
        job, level = int(key), int(value or 0)
        if 1 <= job <= len(JOBS) and level > 0:
            if job > ERA_LAST_JOB:
                report["left_out"].append(f"{JOBS[job - 1].upper()} {level} (after Treasures of Aht Urhgan)")
            else:
                levels[job] = min(level, max_level)
    if not levels:
        raise ImportError_("The snapshot has no job levels this world can use.")
    capped = [f"{JOBS[j - 1].upper()} {jobs['levels'][str(j)]}" for j in levels if int(jobs["levels"][str(j)]) > max_level]
    if capped:
        report["left_out"].append(f"levels above {max_level}, capped at {max_level}: " + ", ".join(capped))
    main = int(jobs.get("main") or 0)
    if main not in levels:
        main = max(levels, key=lambda j: levels[j])
    sub = int(jobs.get("sub") or 0)
    if sub not in levels or sub == main:
        sub = 0
    top = max(levels.values())
    genkai = next(step for step in GENKAI_STEPS if step >= min(top, max_level))
    unlocked = 0
    for job in levels:
        unlocked |= 1 << job
    if sub or int(jobs.get("sub_level") or 0) > 0:
        unlocked |= 1                          # the support job itself is unlocked
    report["kept"].append("jobs: " + ", ".join(f"{JOBS[j - 1].upper()} {levels[j]}" for j in sorted(levels)))

    # skills: combat skills are the character's, not the job's, so the best reading of each wins
    skills = {}
    sk = snap.get("skills") or {}
    readings = [sk.get("combat") or {}] + [r.get("combat") or {} for r in (sk.get("by_job") or {}).values()]
    for reading in readings:
        for key, value in reading.items():
            sid, val = int(key), int((value or {}).get("skill") or 0)
            if 0 < sid < CRAFT_BASE and val > 0:
                cap = COMBAT_CAP[75] if max_level <= 75 else COMBAT_CAP[99]
                skills[sid] = (min(cap, max(skills.get(sid, (0, 0))[0], val)), 0)
    for key, value in (sk.get("craft") or {}).items():
        index, val = int(key), int((value or {}).get("skill") or 0)
        if 0 <= index <= 9 and val > 0:
            skills[CRAFT_BASE + index] = (min(val, CRAFT_CAP), int((value or {}).get("rank") or 0))
    report["kept"].append(f"{len(skills)} skills")

    spell_ids = [int(s) for s in snap.get("spells") or []]
    spells = sorted(_known(cur, "SELECT spellid FROM spell_list WHERE spellid IN ({})", spell_ids))
    if len(spells) < len(set(spell_ids)):
        report["left_out"].append(f"{len(set(spell_ids)) - len(spells)} spells this server doesn't have")
    report["kept"].append(f"{len(spells)} spells")

    keys = [int(k) for k in snap.get("key_items") or [] if 0 <= int(k) < KEY_TABLES * KEY_TABLE_BITS]
    report["kept"].append(f"{len(keys)} key items")

    # bags: every item this server knows, gear only up to the level cap
    raw = []
    for key, items in (snap.get("inventory") or {}).items():
        for item in items or []:
            if int(item.get("id") or 0) not in (0, 65535):
                raw.append((int(key), int(item.get("slot") or 0), int(item["id"]), max(1, int(item.get("count") or 1)),
                            item.get("extra") or ""))
    item_ids = {r[2] for r in raw}
    known = _known(cur, "SELECT itemid FROM item_basic WHERE itemid IN ({})", item_ids)
    too_high = set()
    if item_ids:
        ids = sorted(item_ids)
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            cur.execute("SELECT itemId FROM item_equipment WHERE level > ? AND itemId IN ({})".format(",".join("?" * len(chunk))),
                        [max_level] + chunk)
            too_high.update(int(r[0]) for r in cur.fetchall())
    unknown = [r for r in raw if r[2] not in known]
    above = [r for r in raw if r[2] in known and r[2] in too_high]
    if unknown:
        report["left_out"].append(f"{len(unknown)} items this server doesn't have")
    if above:
        report["left_out"].append(f"{len(above)} pieces of gear above level {max_level}")
    wanted = [r for r in raw if r[2] in known and r[2] not in too_high]

    cur.execute("SELECT * FROM char_storage WHERE charid = ?", (charid,))
    row = cur.fetchone()
    if row is None:
        raise ImportError_("That character has no bag sizes yet: log in with it once, then log out and import again.")
    names = [d[0] for d in cur.description]
    sizes = {}
    for container, column in CONTAINERS.items():
        size = int(row[names.index(column)]) if column in names else 0
        sizes[container] = min(size, 80)
    used = {c: set() for c in CONTAINERS}
    used[0].add(0)                              # inventory slot 0 is gil
    placed, homeless, moved = [], [], {}
    for container, slot, itemid, count, extra in sorted(wanted, key=lambda r: (r[0], r[1])):
        if container in CONTAINERS and 1 <= slot <= sizes[container] and slot not in used[container]:
            target = (container, slot)
        else:
            target = None
            for c in FILL_ORDER:
                free = next((s for s in range(1, sizes[c] + 1) if s not in used[c]), None)
                if free is not None:
                    target = (c, free)
                    break
        if target is None:
            homeless.append(itemid)
            continue
        used[target[0]].add(target[1])
        moved[(container, slot)] = target
        placed.append((target[0], target[1], itemid, count, extra))
    if homeless:
        report["left_out"].append(f"{len(homeless)} items with no room in your bags here")
    report["kept"].append(f"{len(placed)} items")
    gil = max(0, int(snap.get("gil") or 0))
    report["kept"].append(f"{gil:,} gil")

    equip = []
    for key, worn in (snap.get("equipment") or {}).items():
        where = moved.get((int(worn.get("container") or 0), int(worn.get("slot") or 0)))
        if where is not None:
            equip.append((int(key), where[0], where[1]))

    char = snap.get("character") or {}
    look = snap.get("look") or {}
    title = int(char.get("title") or 0)
    nation = int(char.get("nation") or 0) if int(char.get("nation") or 0) in (0, 1, 2) else 0
    rank = max(1, min(10, int(char.get("rank") or 1)))
    report["kept"].append(f"nation {('San d''Oria', 'Bastok', 'Windurst')[nation]}, rank {rank}")
    report["left_out"].append("quests, missions, fame, merits, linkshells and the mog house layout (never carried)")
    return {"charid": charid, "levels": levels, "main": main, "sub": sub, "genkai": genkai, "unlocked": unlocked,
            "skills": skills, "spells": spells, "keys": keys, "items": placed, "gil": gil, "equip": equip,
            "race": _in_range(char.get("race"), 1, 8), "face": _in_range(char.get("face"), 0, 15),
            "size": _in_range(char.get("size"), 0, 2), "look": look, "title": title, "nation": nation, "rank": rank, "rank_points": int(char.get("rank_points") or 0),
            "report": report, "name": char.get("name") or "?"}


def _in_range(value, low, high):
    """(2026-11-22, delukard, MrDink, Bigbadbill: a CatsEye export had size -1 and the import stopped) the value when it is a
    whole number from low to high, else None (the new character keeps its own)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if low <= v <= high else None


def _set_bits(blob, ids, offset_for):
    data = bytearray(blob)
    for i in ids:
        at = offset_for(i)
        if at is not None and at[0] < len(data):
            data[at[0]] |= 1 << at[1]
    return bytes(data)


def apply(conn, p):
    """Writes the plan in one transaction. The caller makes the backup first."""
    cur = conn.cursor()
    charid = p["charid"]
    try:
        conn.autocommit = False
    except Exception:
        pass
    try:
        cols = ", ".join(f"{JOBS[j - 1]} = ?" for j in sorted(p["levels"]))
        reset = ", ".join(f"{name} = 0" for index, name in enumerate(JOBS, start=1) if index not in p["levels"] and index > 6)
        cur.execute(f"UPDATE char_jobs SET unlocked = unlocked | ?, genkai = ?, {cols}{', ' + reset if reset else ''} WHERE charid = ?",
                    [p["unlocked"], p["genkai"]] + [p["levels"][j] for j in sorted(p["levels"])] + [charid])
        cur.execute("UPDATE char_stats SET mjob = ?, sjob = ?, mlvl = ?, slvl = ?, title = ? WHERE charid = ?",
                    (p["main"], p["sub"], p["levels"][p["main"]], p["levels"].get(p["sub"], 0), p["title"], charid))
        cur.execute("UPDATE char_exp SET " + ", ".join(f"{j} = 0" for j in JOBS) + " WHERE charid = ?", (charid,))
        cur.execute("DELETE FROM char_skills WHERE charid = ?", (charid,))
        for sid, (value, rank) in sorted(p["skills"].items()):
            cur.execute("INSERT INTO char_skills (charid, skillid, value, rank) VALUES (?, ?, ?, ?)", (charid, sid, value * 10, rank))
        cur.execute("DELETE FROM char_spells WHERE charid = ?", (charid,))
        for spell in p["spells"]:
            cur.execute("INSERT INTO char_spells (charid, spellid) VALUES (?, ?)", (charid, spell))
        cur.execute("SELECT keyitems, titles FROM chars WHERE charid = ?", (charid,))
        keyblob, titleblob = cur.fetchone()
        size = KEY_TABLES * KEY_TABLE_BITS // 8 * 2
        keyblob = bytes(keyblob or b"").ljust(size, b"\0")
        # each table: 64 bytes of "have it" bits, then 64 bytes of "seen it" bits; the imported ones are both
        keyblob = _set_bits(keyblob, p["keys"], lambda k: ((k // KEY_TABLE_BITS) * 128 + (k % KEY_TABLE_BITS) // 8, k % 8))
        keyblob = _set_bits(keyblob, p["keys"], lambda k: ((k // KEY_TABLE_BITS) * 128 + 64 + (k % KEY_TABLE_BITS) // 8, k % 8))
        titleblob = bytes(titleblob or b"").ljust(TITLE_BYTES, b"\0")
        if p["title"]:
            titleblob = _set_bits(titleblob, [p["title"]], lambda t: (t // 8, t % 8))
        cur.execute("UPDATE chars SET keyitems = ?, titles = ?, nation = ? WHERE charid = ?", (keyblob, titleblob, p["nation"], charid))
        nation_col = ("rank_sandoria", "rank_bastok", "rank_windurst")[p["nation"]]
        cur.execute(f"UPDATE char_profile SET {nation_col} = ?, rank_points = ? WHERE charid = ?", (p["rank"], p["rank_points"], charid))
        if p["race"]:
            look = p["look"]
            gear = [_in_range(look.get(k), 0, 65535) or 0 for k in ("head", "body", "hands", "legs", "feet", "main", "sub", "ranged")]
            cur.execute("UPDATE char_look SET race = ?, face = COALESCE(?, face), size = COALESCE(?, size), head = ?, body = ?, "
                        "hands = ?, legs = ?, feet = ?, main = ?, sub = ?, ranged = ? WHERE charid = ?",
                        (p["race"], p["face"], p["size"], *gear, charid))
        cur.execute("DELETE FROM char_equip WHERE charid = ?", (charid,))
        cur.execute("DELETE FROM char_inventory WHERE charid = ?", (charid,))
        cur.execute("INSERT INTO char_inventory (charid, location, slot, itemId, quantity) VALUES (?, 0, 0, 65535, ?)", (charid, p["gil"]))
        for container, slot, itemid, count, extra in p["items"]:
            try:
                blob = bytes.fromhex(extra)[:24] if extra else b""
            except ValueError:
                blob = b""
            cur.execute("INSERT INTO char_inventory (charid, location, slot, itemId, quantity, extra) VALUES (?, ?, ?, ?, ?, ?)",
                        (charid, container, slot, itemid, count, blob.ljust(24, b"\0")))
        for equipslot, container, slot in p["equip"]:
            cur.execute("INSERT INTO char_equip (charid, slotid, equipslotid, containerid) VALUES (?, ?, ?, ?)",
                        (charid, slot, equipslot, container))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def find_character(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT charid FROM chars WHERE LOWER(charname) = LOWER(?)", (name,))
    row = cur.fetchone()
    if row is None:
        raise ImportError_(f"There is no character called {name} in this world. Make it in the lobby first, then log out.")
    charid = int(row[0])
    cur.execute("SELECT 1 FROM accounts_sessions WHERE charid = ? LIMIT 1", (charid,))
    if cur.fetchone():
        raise ImportError_(f"{name} is logged in. Log out (or press STOP), then import.")
    return charid


def backup_first(conn, charid, name):
    """The same character backup the Characters page makes, so Restore can put it back."""
    import launcher_passport as pp
    data = pp.backup_character(conn, charid)
    folder = os.path.join(HERE, "backups")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}-before-import-{time.strftime('%Y%m%d-%H%M%S')}.zip")
    with open(path, "wb") as handle:
        handle.write(data if isinstance(data, (bytes, bytearray)) else pp.pack(data))
    return path


def describe(p):
    lines = [f"From the snapshot of {p['name']}:"]
    lines += ["  + " + line for line in p["report"]["kept"]]
    lines += ["  - " + line for line in p["report"]["left_out"]]
    return "\n".join(lines)


# ---------------------------------------------------------------- the capture add-on for the other game
def install_capture(other_ashita, log=print):
    """Downloads charcapture (VanaDreams, pinned) into another Ashita folder's addons."""
    import io
    import shutil
    import zipfile
    import launcher_thirdparty as tp
    if not os.path.isdir(os.path.join(other_ashita, "addons")):
        raise ImportError_(f"{other_ashita} has no addons folder: pick the Ashita folder of the game you're leaving.")
    url = f"https://codeload.github.com/{CAPTURE_REPO}/zip/{CAPTURE_REF}"
    log("Downloading charcapture from the VanaDreams GitHub...")
    data = tp._get(url, timeout=120)
    if hasattr(data, "read"):
        data = data.read()
    target = os.path.join(other_ashita, "addons", "charcapture")
    os.makedirs(target, exist_ok=True)
    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.namelist():
            parts = member.split("/", 1)
            if len(parts) == 2 and parts[1].startswith("addons/charcapture/") and not member.endswith("/"):
                rel = parts[1][len("addons/charcapture/"):]
                dest = os.path.join(target, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with archive.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                count += 1
    if not count:
        raise ImportError_("The download had no charcapture folder.")
    log(f"charcapture installed in {target} ({count} files). In that game: /addon load charcapture, then /capture.")
    return target


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "install-capture" and len(argv) >= 3:
        install_capture(argv[2])
        return 0
    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8") as handle:
        cfg = json.load(handle)
    max_level = server_max_level(cfg.get("server_dir"))
    if "--max-level" in argv:
        max_level = int(argv[argv.index("--max-level") + 1])
    import setup_dualbox as sd
    snap = load_snapshot(argv[2])
    conn = sd.connect(cfg)
    try:
        if cmd == "preview":
            cur = conn.cursor()
            cur.execute("SELECT charid FROM chars ORDER BY charid LIMIT 1")
            any_char = cur.fetchone()
            p = plan(conn, snap, int(any_char[0]) if any_char else 0, max_level)
            print(describe(p))
            return 0
        if cmd == "import" and len(argv) >= 4:
            charid = find_character(conn, argv[3])
            p = plan(conn, snap, charid, max_level)
            print(describe(p))
            path = backup_first(conn, charid, argv[3])
            print(f"Backed up {argv[3]} to {path}")
            apply(conn, p)
            print(f"Done: {p['name']} is now {argv[3]} in this world.")
            return 0
    except ImportError_ as e:
        print(str(e))
        return 2
    finally:
        conn.close()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
