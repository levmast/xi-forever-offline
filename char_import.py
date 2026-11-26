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
race, face and size, nation, rank and title; quests and missions (every log: current and finished, Assault and
Campaign included), currencies (conquest points, seals, tabs, assault points...), merits and merit points.
Not: fame, linkshells, mog house layout, or a quest's own progress inside it (the game never sends those).
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
LINKSHELL_ITEMS = frozenset((513, 514, 515))   # Linkshell, Pearlsack, Linkpearl

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


# ---------------------------------------------------------------- quests and missions (2026-11-24, Hasuko)
# The capture keeps the game's own quest/mission log packets (0x056), keyed by their "port" in hex. They map straight
# onto the server's blobs (chars.quests / missions / assault / campaign, src/common/mmo.h):
#   quests:   11 areas x (32 bytes current + 32 bytes finished)
#   missions: 15 logs x (uint16 current, statusUpper, statusLower, 64 x bool finished)
#   assault:  uint16 current, 128 x bool;  campaign: uint16 current, 512 x bool
QUEST_AREAS = 11
QUEST_OFFER = {0x50: 0, 0x58: 1, 0x60: 2, 0x68: 3, 0x70: 4, 0x78: 5, 0x80: 6, 0x88: 7, 0xE0: 8, 0xF0: 9, 0x100: 10}
QUEST_DONE = {0x90: 0, 0x98: 1, 0xA0: 2, 0xA8: 3, 0xB0: 4, 0xB8: 5, 0xC0: 6, 0xC8: 7, 0xE8: 8, 0xF8: 9, 0x108: 10}
MISSION_LOGS, MISSION_SIZE = 15, 70          # Sandoria 0 Bastok 1 Windurst 2 Zilart 3 ToAU 4 WoTG 5 CoP 6 ... RoV 13
LOG_NAMES = ("San d'Oria", "Bastok", "Windurst", "Rise of the Zilart", "Treasures of Aht Urhgan", "Wings of the Goddess",
             "Chains of Promathia")


def _packets(snap):
    out = {}
    for key, value in (snap.get("quest_mission_packets") or {}).items():
        try:
            data = bytes.fromhex(value)
            out[int(key, 16)] = data.ljust(32, b"\0")[:32]
        except (TypeError, ValueError):
            continue
    return out


def _bits(data, count):
    return [bool(data[i // 8] >> (i % 8) & 1) for i in range(count)]


def story(snap):
    """The character's quest, mission, assault and campaign logs as the server's four blobs, or None when the snapshot
    has no quest/mission packets (an older charcapture)."""
    import struct
    packets = _packets(snap)
    if not packets:
        return None
    quests = bytearray(QUEST_AREAS * 64)
    seen_q = 0
    for port, area in QUEST_OFFER.items():
        if port in packets:
            data = packets[port][:16] if area == 6 else packets[port]   # Aht Urhgan: bytes 16-31 are the mission logs
            quests[area * 64:area * 64 + len(data)] = data
            seen_q += 1
    for port, area in QUEST_DONE.items():
        if port in packets:
            data = packets[port][:16] if area == 6 else packets[port]   # Aht Urhgan: bytes 16-31 are Assaults done
            quests[area * 64 + 32:area * 64 + 32 + len(data)] = data
            seen_q += 1

    current = [0xFFFF if i < 3 else 0 for i in range(MISSION_LOGS)]
    upper, lower = [0] * MISSION_LOGS, [0] * MISSION_LOGS
    done = [[False] * 64 for _ in range(MISSION_LOGS)]
    main = packets.get(0xFFFF)
    if main:
        nation, nation_mission, zilart, cop, cop2 = struct.unpack_from("<IIIII", main, 0)
        addons, _tales = struct.unpack_from("<HH", main, 20)
        if nation in (0, 1, 2):
            current[nation] = nation_mission & 0xFFFF
        current[3], current[6] = zilart & 0xFFFF, cop & 0xFFFF
        upper[6], lower[6] = (cop2 >> 16) & 0xFFFF, cop2 & 0xFFFF
        current[9], current[10], current[11] = addons & 0xF, (addons >> 4) & 0xF, (addons >> 8) & 0xF
    if 0xD0 in packets:                                    # finished nation and Zilart missions: 2 words per log
        bits = _bits(packets[0xD0], 256)
        for log in range(4):
            done[log] = bits[log * 64:log * 64 + 64]
    if 0xD8 in packets:                                    # finished ToAU (words 0-1) and WoTG (words 2-3)
        bits = _bits(packets[0xD8], 128)
        done[4], done[5] = bits[0:64], bits[64:128]
    assault_current, campaign_current = 0, 0
    if 0x80 in packets:                                    # Aht Urhgan quests in progress also carry these
        assault_current, current[4], current[5], campaign_current = struct.unpack_from("<IIII", packets[0x80], 16)
        current[4], current[5] = current[4] & 0xFFFF, current[5] & 0xFFFF
    missions = bytearray()
    for log in range(MISSION_LOGS):
        missions += struct.pack("<HHH", current[log], upper[log], lower[log]) + bytes(done[log])
    assault = struct.pack("<H", assault_current & 0xFFFF) + bytes(_bits(packets[0xC0][16:], 128) if 0xC0 in packets else [0] * 128)
    campaign_bits = (_bits(packets[0x30], 256) if 0x30 in packets else [False] * 256) + \
                    (_bits(packets[0x38], 256) if 0x38 in packets else [False] * 256)
    campaign = struct.pack("<H", campaign_current & 0xFFFF) + bytes(campaign_bits)
    finished = sum(bin(b).count("1") for area in range(QUEST_AREAS) for b in quests[area * 64 + 32:area * 64 + 64]
                   if area != 6) + sum(bin(b).count("1") for b in quests[6 * 64 + 32:6 * 64 + 48])
    missions_done = {LOG_NAMES[log]: sum(done[log]) for log in range(7) if any(done[log])}
    return {"quests": bytes(quests), "missions": bytes(missions), "assault": bytes(assault), "campaign": bytes(campaign),
            "quests_done": finished, "missions_done": missions_done, "logs_seen": seen_q}


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
    # (2026-11-24, Hasuko) a linkshell, pearl or pearlsack belongs to a linkshell of the other game: here it is only a
    # broken item that can't even be thrown away safely, so it stays behind
    shells = [r for r in wanted if r[2] in LINKSHELL_ITEMS]
    if shells:
        wanted = [r for r in wanted if r[2] not in LINKSHELL_ITEMS]
        report["left_out"].append(f"{len(shells)} linkshell(s) and pearls (they belong to the other game's linkshells)")

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
    # quests and missions, currencies, merits (2026-11-24, Hasuko: they stayed as the character here had them)
    logs = story(snap)
    if logs:
        report["kept"].append(f"quests and missions: {logs['quests_done']} quests finished"
                              + "".join(f", {n} {c}" for n, c in logs["missions_done"].items()))
    else:
        report["left_out"].append("quests and missions (this snapshot is from an older charcapture: /capture again)")
    try:
        cur.execute("SHOW COLUMNS FROM char_points")
        point_cols = {str(r[0]) for r in cur.fetchall()} - {"charid"}
    except Exception:
        point_cols = set()
    points = {k: max(0, int(v or 0)) for k, v in (snap.get("currencies") or {}).items()
              if k in point_cols and isinstance(v, (int, float))}
    if any(points.values()):
        report["kept"].append(f"{sum(1 for v in points.values() if v)} currencies (conquest points, seals, tabs...)")
    merit_upgrades = {}
    for key, value in (snap.get("merit_upgrades") or {}).items():
        try:
            if int(value) > 0:
                merit_upgrades[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    merit_points = max(0, int(((jobs.get("merits") or {}).get("points")) or 0))
    limit_points = max(0, int(jobs.get("limit_points") or 0)) if not isinstance(jobs.get("limit_points"), dict) else 0
    if merit_upgrades or merit_points:
        report["kept"].append(f"merits: {sum(merit_upgrades.values())} upgrades, {merit_points} unspent points")
    report["left_out"].append("fame, linkshells and the mog house layout (the game never sends them)")
    return {"story": logs, "points": points, "merit_upgrades": merit_upgrades, "merit_points": merit_points,
            "limit_points": limit_points,
            "charid": charid, "levels": levels, "main": main, "sub": sub, "genkai": genkai, "unlocked": unlocked,
            "skills": skills, "spells": spells, "keys": keys, "items": placed, "gil": gil, "equip": equip,
            "race": int(char.get("race") or 0), "face": int(char.get("face") or 0), "size": _size(char.get("size")),
            "look": look, "title": title, "nation": nation, "rank": rank, "rank_points": int(char.get("rank_points") or 0),
            "report": report, "name": char.get("name") or "?"}


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
            cur.execute("UPDATE char_look SET race = ?, face = ?, size = ?, head = ?, body = ?, hands = ?, legs = ?, feet = ?, "
                        "main = ?, sub = ?, ranged = ? WHERE charid = ?",
                        (p["race"], p["face"], p["size"], *(int(look.get(k) or 0) for k in ("head", "body", "hands", "legs", "feet",
                                                                                           "main", "sub", "ranged")), charid))
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
        # quests and missions REPLACE the character's own logs (the old ones were the ones it had made here)
        logs = p.get("story")
        if logs:
            cur.execute("UPDATE chars SET quests = ?, missions = ?, assault = ?, campaign = ? WHERE charid = ?",
                        (logs["quests"], logs["missions"], logs["assault"], logs["campaign"], charid))
        if p.get("points"):
            cur.execute("SELECT 1 FROM char_points WHERE charid = ?", (charid,))
            if cur.fetchone() is None:
                cur.execute("INSERT INTO char_points (charid) VALUES (?)", (charid,))
            cols = sorted(p["points"])
            cur.execute("UPDATE char_points SET " + ", ".join(f"`{c}` = ?" for c in cols) + " WHERE charid = ?",
                        [p["points"][c] for c in cols] + [charid])
        if p.get("merit_upgrades") is not None and (p.get("merit_upgrades") or p.get("merit_points")):
            cur.execute("DELETE FROM char_merit WHERE charid = ?", (charid,))
            for merit, count in sorted(p["merit_upgrades"].items()):
                cur.execute("INSERT INTO char_merit (charid, meritid, upgrades) VALUES (?, ?, ?)", (charid, merit, count))
            cur.execute("UPDATE char_exp SET merits = ?, limits = ? WHERE charid = ?",
                        (min(p.get("merit_points", 0), 255), min(p.get("limit_points", 0), 65535), charid))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _size(value):
    """(2026-11-24, Jker_s81) The game's sizes are 0-2; another server's capture with anything else stopped the import
    ("Out of range value for column 'size'"): then the middle size."""
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return 1
    return size if 0 <= size <= 2 else 1


def find_character(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT charid FROM chars WHERE LOWER(charname) = LOWER(?)", (name,))
    row = cur.fetchone()
    if row is None:
        raise ImportError_(f"There is no character called {name} in this world. Make it in the lobby first, then log out.")
    charid = int(row[0])
    cur.execute("SELECT 1 FROM accounts_sessions WHERE charid = ? LIMIT 1", (charid,))
    if cur.fetchone():
        # (2026-11-24, Hasuko) a crash or a killed server leaves the login row behind, and then the character is
        # "logged in" forever. With the map server not running nobody can be logged in: clear the leftover row.
        if not map_server_running():
            cur.execute("DELETE FROM accounts_sessions WHERE charid = ?", (charid,))
            conn.commit()
        else:
            raise ImportError_(f"{name} is logged in. Log out (or press STOP), then import.")
    return charid


def map_server_running():
    """True when xi_map runs, or when that can not be checked (then the login row is trusted)."""
    try:
        import launcher_core
        return launcher_core.is_running("xi_map")
    except Exception:
        return True


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
