#!/usr/bin/env python3
"""Item stacks: today's game or the 75 era (the launcher's "Modern item stacks" switch).

Phoenix puts stack sizes back to what they were in the era: most things that stack to 12 today were single items
(sheepskin, goblin helms...), and a few 99-stacks were 12 or 1. That needs two things to agree: the server's item table
and the game's own item files, which is why the list lives in the server's
modules/phoenix/sql/pxi_item_basic.sql under "DAT Stack size updates" ("retail 12 -> 1").

This tool reads that list (so it follows Phoenix when the list changes) and sets both sides to one mode:
  modern  the stack sizes of today's game (12 / 99)          <- the default
  era     Phoenix's era stack sizes

  python stack_mode.py db modern|era      the server's item table (the launcher runs this before the servers start)
  python stack_mode.py dats modern|era    the game's item files (the launcher does this with its other game-file changes)
  python stack_mode.py status             what both sides say now

Only the stack size of the listed items is touched. The game files are changed in place, in the player's own game
folder (two bytes per item); the originals are kept once in <kit>\\backups\\stacking-dat.
"""
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_REL = os.path.join("modules", "phoenix", "sql", "pxi_item_basic.sql")
SECTION = "-- DAT Stack size updates"
LINE = re.compile(r"UPDATE `item_basic` SET `stackSize` = (\d+) WHERE `itemid` = (\d+);[^\n]*\(retail (\d+) -> (\d+)\)")
# the game's English item files: (path under the game folder, first item id)
DATS = ((os.path.join("ROM", "118", "106.DAT"), 0), (os.path.join("ROM", "118", "107.DAT"), 4096),
        (os.path.join("ROM", "118", "110.DAT"), 8192), (os.path.join("ROM", "118", "109.DAT"), 10240),
        (os.path.join("ROM", "118", "108.DAT"), 16384))


def overrides(server_dir):
    """[(item id, era stack, modern stack)] from Phoenix's list. Empty when the file or the section is not there."""
    try:
        with open(os.path.join(server_dir, SQL_REL), encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError:
        return []
    at = text.find(SECTION)
    if at < 0:
        return []
    rows = []
    for era, item, retail, era_again in LINE.findall(text[at:]):
        if era == era_again and 1 <= int(era) <= 99 and 1 <= int(retail) <= 99:
            rows.append((int(item), int(era), int(retail)))
    return rows


def _rot_dec(data):
    return bytes(((x >> 5) | (x << 3)) & 0xFF for x in data)


def _rot_enc(data):
    return bytes(((x << 5) | (x >> 3)) & 0xFF for x in data)


def _layout(size):
    """(record size, offset of the stack size) of an item file, or None when it is not one."""
    if size and size % 0x1400 == 0:
        return 0x1400, 8          # id (4), flags (4), stack (2)
    if size and size % 0xC00 == 0:
        return 0xC00, 6           # id (4), flags (2), stack (2)
    return None


def apply_dats(game, rows, modern, backup_dir=None, write=True):
    """Sets the listed items' stack size in the game's item files. Returns (changed, already right, left alone).
    An item whose record is not the expected one (another id, or a stack size that is neither value) is left alone."""
    changed = right = skipped = 0
    for rel, first in DATS:
        path = os.path.join(game, rel)
        if not os.path.isfile(path):
            continue
        layout = _layout(os.path.getsize(path))
        if layout is None:
            continue
        size, at = layout
        with open(path, "rb") as handle:
            data = bytearray(handle.read())
        count, dirty = len(data) // size, False
        for item, era, retail in rows:
            index = item - first
            if not 0 <= index < count:
                continue
            start = index * size
            head = bytearray(_rot_dec(data[start:start + 16]))
            want = retail if modern else era
            have = struct.unpack_from("<H", head, at)[0]
            if struct.unpack_from("<I", head, 0)[0] != item or have not in (era, retail):
                skipped += 1
            elif have == want:
                right += 1
            else:
                struct.pack_into("<H", head, at, want)
                data[start:start + 16] = _rot_enc(head)
                changed, dirty = changed + 1, True
        if dirty and write:
            if backup_dir:
                keep = os.path.join(backup_dir, rel.replace(os.sep, "_") + ".original")
                if not os.path.exists(keep):
                    os.makedirs(backup_dir, exist_ok=True)
                    with open(path, "rb") as source, open(keep, "wb") as target:
                        target.write(source.read())
            tmp = path + ".stacks-tmp"
            with open(tmp, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
    return changed, right, skipped


def apply_db(conn, rows, modern):
    """Sets the listed items' stackSize in item_basic. Returns how many rows changed."""
    cur = conn.cursor()
    cur.execute("SELECT itemid, stackSize FROM item_basic")
    now = {int(i): int(s) for i, s in cur.fetchall()}
    todo = [((retail if modern else era), item) for item, era, retail in rows
            if item in now and now[item] != (retail if modern else era)]
    if todo:
        cur.executemany("UPDATE item_basic SET stackSize = ? WHERE itemid = ?", todo)
        conn.commit()
    cur.close()
    return len(todo)


def _config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as handle:
        return json.load(handle)


def _connect(cfg):
    import mariadb
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)), user=cfg["db_user"],
                           password=cfg["db_pass"], database=cfg["db_name"])


def main(argv):
    mode = argv[1] if len(argv) > 1 else "status"
    cfg = _config()
    rows = overrides(cfg["server_dir"])
    if not rows:
        print("item stacks: Phoenix's stack list was not found - nothing changed")
        return 0
    if mode in ("db", "dats"):
        if len(argv) < 3 or argv[2] not in ("modern", "era"):
            raise SystemExit(__doc__)
        modern = argv[2] == "modern"
        name = "today's stack sizes" if modern else "the era's stack sizes"
        if mode == "db":
            conn = _connect(cfg)
            try:
                changed = apply_db(conn, rows, modern)
            finally:
                conn.close()
            print(f"item stacks: {changed} item(s) set to {name} on the server" if changed else f"item stacks: the server already has {name}")
        else:
            changed, right, skipped = apply_dats(cfg.get("ffxi_client_dir", ""), rows, modern, os.path.join(HERE, "backups", "stacking-dat"))
            print(f"item stacks: {changed} changed, {right} already right, {skipped} left alone in the game files ({name})")
    elif mode == "status":
        game = cfg.get("ffxi_client_dir", "")
        as_modern = apply_dats(game, rows, True, write=False)
        print(f"{len(rows)} items in Phoenix's list. Game files: {as_modern[1]} at today's size, {as_modern[0]} at the era's, {as_modern[2]} unexpected.")
        try:
            conn = _connect(cfg)
            cur = conn.cursor()
            cur.execute("SELECT itemid, stackSize FROM item_basic")
            now = {int(i): int(s) for i, s in cur.fetchall()}
            conn.close()
            print("Server: %d at today's size, %d at the era's." % (sum(1 for i, e, r in rows if now.get(i) == r),
                                                                   sum(1 for i, e, r in rows if now.get(i) == e)))
        except Exception as problem:
            print(f"Server: not checked ({problem})")
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
