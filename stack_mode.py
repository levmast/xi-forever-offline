"""Item stacks: today's stack sizes ("modern", 12 / 99) or Phoenix's era sizes, on the server and in the game files.

  python stack_mode.py db modern|era      the server's item table (item_basic.stackSize)
  python stack_mode.py dats modern|era    the game's English item files (ROM\\118\\106-110.DAT)
  python stack_mode.py status             how many of the listed items are modern / era in each place

The list is Phoenix's own: every `UPDATE item_basic SET stackSize = <era> WHERE itemid = <id>; -- ... (retail <modern>
-> <era>)` line in the server's modules/phoenix/sql/pxi_item_basic.sql. A server update imports the era values again,
so the launcher runs "db" before the servers start on every PLAY (launcher_gui.run_stack_mode), and
launcher_client.item_stacks does the game files with the other game-file changes. Server and game files must agree:
the game shows and splits stacks by its own files, the server decides what really stacks.

Game files: each item record is rotated 5 bits per byte; the stack size is the 16-bit value at 0x08. A record is only
changed when its id is the expected one, and the original file is copied once to backups\\stacking-dat first.
"""
import json
import os
import re
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PXI_REL = os.path.join("modules", "phoenix", "sql", "pxi_item_basic.sql")
LINE = re.compile(r"UPDATE\s+`item_basic`\s+SET\s+`stackSize`\s*=\s*(\d+)\s+WHERE\s+`itemid`\s*=\s*(\d+)\s*;"
                  r".*\(retail\s+(\d+)\s*->\s*(\d+)\)", re.IGNORECASE)
# English item files: (file, first item id, number of records)
DAT_FILES = (
    (os.path.join("ROM", "118", "106.DAT"), 0, 4096),       # general items
    (os.path.join("ROM", "118", "107.DAT"), 4096, 4096),    # usable items
    (os.path.join("ROM", "118", "110.DAT"), 8192, 2048),    # automaton items
    (os.path.join("ROM", "118", "109.DAT"), 10240, 6144),   # armor
    (os.path.join("ROM", "118", "108.DAT"), 16384, 6656),   # weapons
)
STACK_AT = 0x08


def overrides(server):
    """[(itemid, era, modern)] from Phoenix's era list, or [] when the server has no such file."""
    path = os.path.join(server, PXI_REL)
    if not os.path.isfile(path):
        return []
    rows = {}
    with open(path, encoding="utf-8-sig", errors="replace") as handle:
        for line in handle:
            if line.lstrip().startswith("--"):
                continue
            found = LINE.search(line)
            if found:
                era, item, modern, era_note = (int(x) for x in found.groups())
                if modern > 0 and era > 0 and modern != era:
                    rows[item] = (item, era, modern)
    return sorted(rows.values())


def _rot_dec(b):
    return bytes(((x >> 5) | (x << 3)) & 0xFF for x in b)


def _rot_enc(b):
    return bytes(((x << 5) | (x >> 3)) & 0xFF for x in b)


def _dat_for(item):
    for rel, first, count in DAT_FILES:
        if first <= item < first + count:
            return rel, first, count
    return None


def apply_dats(game, rows, modern, backup_dir):
    """Sets each listed item's stack size in the game files. Returns (changed, already right, skipped)."""
    changed = right = skipped = 0
    by_file = {}
    for item, era, mod in rows:
        where = _dat_for(item)
        if where is None:
            skipped += 1
            continue
        by_file.setdefault(where, []).append((item, mod if modern else era))
    for (rel, first, count), items in sorted(by_file.items()):
        path = os.path.join(game, rel)
        if not os.path.isfile(path):
            skipped += len(items)
            continue
        size = os.path.getsize(path)
        if size % count:
            skipped += len(items)
            continue
        rs = size // count
        with open(path, "rb") as handle:
            data = bytearray(handle.read())
        dirty = False
        for item, want in items:
            at = (item - first) * rs
            rec = bytearray(_rot_dec(data[at:at + rs]))
            if struct.unpack_from("<I", rec, 0)[0] != item:
                skipped += 1                       # not the record we expect: leave it alone
                continue
            if struct.unpack_from("<H", rec, STACK_AT)[0] == want:
                right += 1
                continue
            struct.pack_into("<H", rec, STACK_AT, want)
            data[at:at + rs] = _rot_enc(rec)
            changed += 1
            dirty = True
        if dirty:
            os.makedirs(backup_dir, exist_ok=True)
            original = os.path.join(backup_dir, rel.replace(os.sep, "_") + ".original")
            if not os.path.exists(original):
                shutil.copy2(path, original)
            tmp = path + ".stack-tmp"
            with open(tmp, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
    return changed, right, skipped


def _config():
    with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as handle:
        return json.load(handle)


def _connect(cfg):
    import mariadb
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"], autocommit=True)


def apply_db(conn, rows, modern):
    """Sets each listed item's stackSize in item_basic. Returns the number of rows changed."""
    cur = conn.cursor()
    changed = 0
    for item, era, mod in rows:
        want = mod if modern else era
        cur.execute("UPDATE item_basic SET stackSize = ? WHERE itemid = ? AND stackSize <> ?", (want, item, want))
        changed += cur.rowcount or 0
    cur.close()
    return changed


def db_counts(conn, rows):
    cur = conn.cursor()
    modern = era = other = 0
    for item, e, m in rows:
        cur.execute("SELECT stackSize FROM item_basic WHERE itemid = ?", (item,))
        got = cur.fetchone()
        value = got[0] if got else None
        if value == m:
            modern += 1
        elif value == e:
            era += 1
        else:
            other += 1
    cur.close()
    return modern, era, other


def dat_counts(game, rows):
    modern = era = other = 0
    for item, e, m in rows:
        where = _dat_for(item)
        path = os.path.join(game, where[0]) if where else None
        if not path or not os.path.isfile(path):
            other += 1
            continue
        rel, first, count = where
        rs = os.path.getsize(path) // count
        with open(path, "rb") as handle:
            handle.seek((item - first) * rs)
            rec = _rot_dec(handle.read(rs))
        value = struct.unpack_from("<H", rec, STACK_AT)[0] if struct.unpack_from("<I", rec, 0)[0] == item else None
        if value == m:
            modern += 1
        elif value == e:
            era += 1
        else:
            other += 1
    return modern, era, other


def main(argv):
    if not argv or argv[0] not in ("db", "dats", "status") or (argv[0] != "status" and (len(argv) < 2 or argv[1] not in ("modern", "era"))):
        print(__doc__.strip().splitlines()[0])
        print("usage: stack_mode.py db modern|era | dats modern|era | status")
        return 2
    cfg = _config()
    rows = overrides(cfg["server_dir"])
    if not rows:
        print("item stacks: no era list found in the server folder - nothing to do")
        return 0
    if argv[0] == "status":
        conn = _connect(cfg)
        print("server: %d modern, %d era, %d other" % db_counts(conn, rows))
        conn.close()
        print("game files: %d modern, %d era, %d other" % dat_counts(cfg["ffxi_client_dir"], rows))
        return 0
    modern = argv[1] == "modern"
    label = "as in today's game (12 / 99)" if modern else "as in the era"
    if argv[0] == "db":
        conn = _connect(cfg)
        changed = apply_db(conn, rows, modern)
        conn.close()
        print("item stacks: %d item(s) on the server now stack %s" % (changed, label) if changed
              else "item stacks on the server already %s" % ("modern" if modern else "era"))
        return 0
    changed, right, skipped = apply_dats(cfg["ffxi_client_dir"], rows, modern,
                                         os.path.join(HERE, "backups", "stacking-dat"))
    print("item stacks: %d changed in the game files (%s)%s" % (changed, label, (", %d left alone" % skipped) if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
