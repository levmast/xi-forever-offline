#!/usr/bin/env python3
"""Builds the loot lists for the custom treasure caskets from YOUR database, so every item really exists on your server.

  python build_casket_loot.py            write modules/custom/lua/casket_loot_custom.lua
  python build_casket_loot.py report     show what would be written (also saved to casket-loot-report.txt)

Blue caskets:  everyday items (materials, food, medicines...), limited by the monster's level.
Brown caskets: weapons and armor suited to the monster's level.
Super casket:  every level 1 cosmetic piece: any era, any rarity, as long as its only stat is DEF.
Blue and brown caskets leave out items newer than the 75 era (same ceilings as the auction house simulator);
the super casket does not, because a costume from 2015 looks exactly as silly in a 75-era world.
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

ERA = {"other_max_id": 5800, "armor_min_id": 12000, "armor_max_id": 15999, "weapon_max_id": 18199, "equipment_max_level": 75}
BANDS = list(range(5, 80, 5))          # monster level bands: 5, 10, ... 75
BLUE_PRICE_CAP_BASE, BLUE_PRICE_CAP_PER_LEVEL = 60, 30      # vendor price an everyday item may have = base + level * per_level
BROWN_LEVEL_WINDOW = 16                                      # gear from (monster level - 16) up to the monster's level
MAX_POOL = 250
AMMO_SLOT = 8
COSMETIC_SLOTS = {16, 32, 64, 128, 256, 32768}               # head, body, hands, legs, feet, back
COSMETIC_DENY = {"tidal_talisman", "ramblers_cloak", "spelunkers_helm", "noble_poulaines", "talaria", "trainees_spectacles",
                 "eerie_cloak", "eerie_cloak_+1", "shapers_shawl", "drovers_mantle", "waders"}
# Hand-picked pieces that always go in the pool, whatever their stats or item ID say.
# The Poroggo set: level 1 all-jobs frog costumes. The +1s look identical; they are just the fancier record.
COSMETIC_ALWAYS = {
    23803, 23804,   # Poroggo Cassock / +1
    26514, 26515,   # Poroggo Fleece / +1
    26956, 26957,   # Poroggo Coat / +1
}
RARE, EX = 0x8000, 0x4000
GM_ONLY, CAN_EQUIP = 0x0002, 0x0800


def load_era():
    era = dict(ERA)
    path = os.path.join(HERE, "ah_sim.json")       # share the auction house's era ceilings if you tuned them
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            era.update({k: v for k, v in json.load(f).get("era", {}).items() if k in era})
    except (OSError, ValueError):
        pass
    return era


def connect():
    import mariadb
    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"]), cfg


def query(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def in_era(itemid, equipment, level, ilevel, su_level, era):
    if equipment:
        if level > era["equipment_max_level"] or ilevel > 0 or su_level > 0:
            return False
        return era["armor_min_id"] <= itemid <= era["armor_max_id"] or 16000 <= itemid <= era["weapon_max_id"]
    return itemid <= era["other_max_id"]


def build(conn, era):
    rows = query(conn, "SELECT b.itemid, b.name, b.BaseSell, b.flags, e.itemId, e.level, e.ilevel, e.su_level, e.slot "
                       "FROM item_basic b LEFT JOIN item_equipment e ON e.itemId = b.itemid WHERE b.aH > 0 AND b.BaseSell > 0")
    everyday, gear = [], []
    for itemid, name, sell, flags, eq_id, level, ilevel, su_level, slot in rows:
        itemid, sell, flags = int(itemid), int(sell), int(flags or 0)
        if flags & (RARE | EX):
            continue
        equipment = eq_id is not None
        level, ilevel, su_level, slot = int(level or 0), int(ilevel or 0), int(su_level or 0), int(slot or 0)
        if not in_era(itemid, equipment, level, ilevel, su_level, era):
            continue
        if equipment:
            if slot == 0 or slot == AMMO_SLOT:
                continue
            gear.append((itemid, name, sell, max(1, level)))
        else:
            everyday.append((itemid, name, sell))

    blue, brown = {}, {}
    for band in BANDS:
        cap = BLUE_PRICE_CAP_BASE + band * BLUE_PRICE_CAP_PER_LEVEL
        pool = [(i, n, 1000.0 / (s + 20)) for i, n, s in everyday if s <= cap]
        blue[band] = trim(pool)
        low = max(1, band - BROWN_LEVEL_WINDOW)
        pool = [(i, n, 1000.0 / ((s + 30) ** 0.7)) for i, n, s, lv in gear if low <= lv <= band]
        if len(pool) < 8:      # very low bands have little gear: widen the window downward
            pool = [(i, n, 1000.0 / ((s + 30) ** 0.7)) for i, n, s, lv in gear if lv <= band]
        brown[band] = trim(pool)

    # A costume is a level 1 equippable whose only stat line is DEF (many have none at all).
    # Rarity and item ID are deliberately ignored here: a Halloween frog suit from 2015 is still a costume.
    cos = query(conn, "SELECT b.itemid, b.name, e.slot, b.flags, b.BaseSell, "
                      "(SELECT COUNT(*) FROM item_mods m WHERE m.itemId = b.itemid AND m.modId <> 1) "
                      "FROM item_basic b JOIN item_equipment e ON e.itemId = b.itemid "
                      # (datadecay 2026-11-19: sapphire leggings, ruby robe showed nothing) MId 0 = the server has no
                      # model for the piece yet ("not implemented" in item_equipment), so it would be invisible
                      "WHERE e.level <= 1 AND e.MId > 0 AND (b.flags & ?) <> 0", (CAN_EQUIP,))
    pieces = {}
    for itemid, name, slot, flags, sell, stat_lines in cos:
        itemid, flags, sell, stat_lines = int(itemid), int(flags or 0), int(sell or 0), int(stat_lines)
        if int(slot) not in COSMETIC_SLOTS or name in COSMETIC_DENY:
            continue
        # Plain starter gear you can buy for a few gil is not a costume; real ones are rare/ex or unsellable.
        if not flags & (RARE | EX) and sell > 0 and itemid not in COSMETIC_ALWAYS:
            continue
        if itemid not in COSMETIC_ALWAYS and (stat_lines or flags & GM_ONLY or name.endswith("_+1")):
            continue
        pieces[itemid] = name
    missing = COSMETIC_ALWAYS - pieces.keys()
    if missing:
        raise SystemExit(f"These hand-picked cosmetic IDs are not level 1 equipment in the database: {sorted(missing)}")
    cosmetics = sorted(pieces.items())
    return blue, brown, cosmetics


def trim(pool):
    pool.sort(key=lambda e: -e[2])
    return [(i, n, max(1, int(round(w)))) for i, n, w in pool[:MAX_POOL]]


def write_lua(path, blue, brown, cosmetics):
    out = ["-- Generated by build_casket_loot.py from your database. Run the script again to rebuild it; do not edit by hand.",
           "return", "{"]
    for label, table in (("blue", blue), ("brown", brown)):
        out.append(f"    {label} =")
        out.append("    {")
        for band in BANDS:
            out.append(f"        [{band}] =")
            out.append("        {")
            line = "           "
            for i, _n, w in table[band]:
                piece = f" {{ {i}, {w} }},"
                if len(line) + len(piece) > 118:
                    out.append(line)
                    line = "           "
                line += piece
            out.append(line)
            out.append("        },")
        out.append("    },")
    out.append("    cosmetics =")
    out.append("    {")
    line = "       "
    for i, n in cosmetics:
        piece = f" {i},"
        if len(line) + len(piece) > 118:
            out.append(line)
            line = "       "
        line += piece
    out.append(line)
    out.append("    },")
    out.append("}")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")


def report(blue, brown, cosmetics):
    rnd = random.Random(1)
    lines = []
    for label, table in (("BLUE (everyday items)", blue), ("BROWN (weapons and armor)", brown)):
        lines.append(f"== {label}")
        for band in (5, 20, 40, 60, 75):
            pool = table[band]
            sample = ", ".join(n for _i, n, _w in rnd.sample(pool, min(8, len(pool)))) if pool else "(none)"
            lines.append(f"  monsters up to level {band}: {len(pool)} possible items, e.g. {sample}")
    lines.append(f"== SUPER casket cosmetics: {len(cosmetics)} pieces")
    lines.append("  " + ", ".join(n for _i, n in cosmetics))
    return "\n".join(lines)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    conn, cfg = connect()
    blue, brown, cosmetics = build(conn, load_era())
    text = report(blue, brown, cosmetics)
    print(text)
    with open(os.path.join(HERE, "casket-loot-report.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    if mode == "report":
        return
    if not cosmetics or not all(blue[b] and brown[b] for b in BANDS):
        raise SystemExit("Some loot lists came out empty, so nothing was written. Send casket-loot-report.txt to Claude.")
    path = os.path.join(cfg["server_dir"], "modules", "custom", "lua", "casket_loot_custom.lua")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_lua(path, blue, brown, cosmetics)
    print(f"\nWrote {path}")


if __name__ == "__main__":
    main()
