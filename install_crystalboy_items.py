"""Crystal Boy items: the Crystal Boy and its cartridges as real FFXI items.

  python install_crystalboy_items.py            install or update (close the game first)
  python install_crystalboy_items.py --status   show what is installed
  python install_crystalboy_items.py --restore  put the original item file back and remove the server rows
  python install_crystalboy_items.py --dat-only / --server-only

What it does
  1. Client: writes each item (name, log names, description, icon) into an EMPTY slot of the English
     usable-item file ROM\\118\\107.DAT. The original file is copied once to
     C:\\FFXISOLO\\backups\\crystalboy-dat\\ before anything is written. Only slots named "." (unused) or
     slots that already hold one of our items are touched.
  2. Server: writes modules\\custom\\sql\\crystalboy_items.sql (item_basic + item_usable rows), lists it in
     modules\\init.txt (so dbtool puts the rows back after a server update) and applies it to the database.

There are no item scripts on purpose: the Crystal Boy addon catches "Use" before it reaches the server,
so the items are never used up. Without the addon the server answers "Unable to use item" and keeps them.

If you ever reinstall the era item files (install-era-dats.ps1) or restore the original game files,
run this again: those replace ROM\\118\\107.DAT.
"""
import argparse, json, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = HERE
ASSETS = os.path.join(HERE, "assets", "crystalboy")
BACKUP_DIR = os.path.join(KIT, "backups", "crystalboy-dat")
DAT_REL = os.path.join("ROM", "118", "107.DAT")   # English usable items, ids 4096-8191
FIRST_ID = 4096
TEMPLATE_ID = 4198                                # Page from the Dragon Chronicles: a usable Rare/Ex item
FLAGS = 0xF640                                    # CanUse, CanTradeNPC, NoAuction, NoSale, NoDelivery, Ex, Rare
SQL_REL = os.path.join("modules", "custom", "sql", "crystalboy_items.sql")
INIT_LINE = "custom/sql/crystalboy_items.sql"
PROBE = None                                      # --probe copy|oldicon|oldtext (crash tests)

ITEMS = [
    {
        "id": 8100, "key": "crystal_boy", "name": "Crystal Boy",
        "log": "Crystal Boy", "plural": "Crystal Boys", "article": 0,
        "desc": "A goblin-mended mechanism with a\ncrystal heart. It plays the old\nadventures kept in Recollections.",
        "icon": "crystalboy.png",
    },
    {
        "id": 8101, "key": "ffa_cartridge", "name": "Jueno Recollection I",
        "log": "Recollection of Jueno I", "plural": "Recollections of Jueno I", "article": 0,
        "desc": "A crystal tablet that remembers the\nfirst part of the Legend of Jueno.\nUse it with a Crystal Boy.",
        "icon": "cart_ffa.png",
        "old_names": ("FF Adventure", "Mana Recollection"),
    },
    {
        "id": 8102, "key": "tower_recollection", "name": "Jueno Recollection II",
        "log": "Recollection of Jueno II", "plural": "Recollections of Jueno II", "article": 0,
        "desc": "A crystal tablet that remembers the\nsecond part of the Legend of Jueno.\nUse it with a Crystal Boy.",
        "icon": "cart_ffl1.png",
        "old_names": ("Tower Recollection",),
    },
    {
        "id": 8103, "key": "magi_recollection", "name": "Jueno Recollection III",
        "log": "Recollection of Jueno III", "plural": "Recollections of Jueno III", "article": 0,
        "desc": "A crystal tablet that remembers the\nlast part of the Legend of Jueno.\nUse it with a Crystal Boy.",
        "icon": "cart_ffl2.png",
        "old_names": ("Magi Recollection",),
    },
    {
        "id": 8104, "key": "time_recollection", "name": "Jueno Recollection IV",
        "log": "Recollection of Jueno IV", "plural": "Recollections of Jueno IV", "article": 0,
        "desc": "A crystal tablet that remembers the\nfourth part of the Legend of Jueno.\nUse it with a Crystal Boy.",
        "icon": "cart_ffl3.png",
        "title": "SEIKEN DENSETSU",   # ROM header title (the addon matches the ROM by this)
        "old_names": ("Time Recollection", "Dungeon Recollection"),
    },
    # The event's games (Horro's Visit, crystalboy-games). Same treatment as the Jueno cartridges.
    {
        "id": 8105, "key": "dragonland1", "name": "Dragonland I",
        "log": "Recollection of Dragonland I", "plural": "Recollections of Dragonland I", "article": 0,
        "desc": "A crystal tablet that remembers the\nfirst part of Dragonland.\nUse it with a Crystal Boy.",
        "icon": "cart_ffa.png",
    },
    {
        "id": 8106, "key": "dragonland2", "name": "Dragonland II",
        "log": "Recollection of Dragonland II", "plural": "Recollections of Dragonland II", "article": 0,
        "desc": "A crystal tablet that remembers the\nsecond part of Dragonland.\nUse it with a Crystal Boy.",
        "icon": "cart_ffl1.png",
    },
    {
        "id": 8107, "key": "dragonland3", "name": "Dragonland III",
        "log": "Recollection of Dragonland III", "plural": "Recollections of Dragonland III", "article": 0,
        "desc": "A crystal tablet that remembers the\nthird part of Dragonland.\nUse it with a Crystal Boy.",
        "icon": "cart_ffl2.png",
    },
    {
        "id": 8108, "key": "dragonland4", "name": "Dragonland IV",
        "log": "Recollection of Dragonland IV", "plural": "Recollections of Dragonland IV", "article": 0,
        "desc": "A crystal tablet that remembers the\nfourth part of Dragonland.\nUse it with a Crystal Boy.",
        "icon": "cart_ffl3.png",
    },
    {
        "id": 8109, "key": "dragonland5", "name": "Dragonland V",
        "log": "Recollection of Dragonland V", "plural": "Recollections of Dragonland V", "article": 0,
        "desc": "A crystal tablet that remembers the\nlast part of Dragonland.\nUse it with a Crystal Boy.",
        "icon": "cart_ffa.png",
    },
]


# ---------------------------------------------------------------- DAT records
def rot_dec(b):
    return bytes(((x >> 5) | (x << 3)) & 0xFF for x in b)


def rot_enc(b):
    return bytes(((x << 5) | (x >> 3)) & 0xFF for x in b)


def kit_config():
    with open(os.path.join(KIT, "config.json"), encoding="utf-8-sig") as f:
        return json.load(f)


def record_size(path):
    size = os.path.getsize(path)
    if size % 4096:
        raise RuntimeError("%s is not an item file (size %d)" % (path, size))
    return size // 4096


def read_record(data, rs, item_id):
    i = item_id - FIRST_ID
    return bytearray(rot_dec(data[i * rs:(i + 1) * rs]))


def strings(rec):
    """The record's string table: list of (kind, value). kind 0 = text, 1 = number."""
    count = struct.unpack_from("<I", rec, 0x1C)[0]
    if not 0 < count < 16:
        raise ValueError("bad string count")
    out = []
    for k in range(count):
        off, kind = struct.unpack_from("<II", rec, 0x20 + k * 8)
        p = 0x1C + off
        if kind == 1:
            out.append((1, struct.unpack_from("<I", rec, p)[0]))
        else:
            t = p + 0x1C
            out.append((0, bytes(rec[t:rec.index(b"\0", t)]).decode("latin-1")))
    return out


def item_name(rec):
    try:
        return strings(rec)[0][1]
    except (ValueError, struct.error):
        return None


def check_layout(rec):
    """The template must look exactly like the layout this tool writes."""
    if struct.unpack_from("<I", rec, 0)[0] != TEMPLATE_ID:
        return "the template record has the wrong id"
    if item_name(rec) != "Dragon Chronicles":
        return "the template record's name is not 'Dragon Chronicles' (not the English file?)"
    size, mark = struct.unpack_from("<IB", rec, 0x280)
    if size != 0x839 or mark != 0x91:
        return "the icon is not where expected"
    if struct.unpack_from("<IiiHHIIiiII", rec, 0x295) != (40, 32, 32, 1, 8, 0, 0, 0, 0, 0, 32):
        return "the icon is not a 32x32 8-bit picture"
    return None


def icon_block(png_path, item_id):
    """32x32 picture -> FFXI icon block (size, 0x91, two 8-char tags, BMP header, BGRA palette, bottom-up pixels)."""
    from PIL import Image  # pip install pillow
    img = Image.open(png_path).convert("RGBA").resize((32, 32))
    rgb = Image.new("RGB", img.size, (0, 0, 0))
    rgb.paste(img, mask=img.split()[3])
    q = rgb.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:255 * 3]
    alpha = img.split()[3]
    pixels = bytearray()
    for y in range(31, -1, -1):
        for x in range(32):
            a = alpha.getpixel((x, y))
            pixels.append(0 if a < 64 else q.getpixel((x, y)) + 1)
    palette = bytearray(b"\0\0\0\0")
    for i in range(255):
        r, g, b = pal[i * 3:i * 3 + 3] if i * 3 + 2 < len(pal) else (0, 0, 0)
        palette += bytes((b, g, r, 0x80))
    palette = palette[:1024].ljust(1024, b"\0")
    # every icon in the game files carries 32 in the last header field (biClrImportant); 0 crashes the item menu
    header = struct.pack("<IiiHHIIiiII", 40, 32, 32, 1, 8, 0, 0, 0, 0, 0, 32)
    # the two 8-character tags name the picture's category and entry; the game only knows its own
    # categories (item, icon, recepi, weapon, armor), and an unknown one ("menu") crashes the Items menu
    tag = ("item%04d" % item_id).encode("ascii")[:8]
    body = b"\x91" + b"item    " + tag + header + bytes(palette) + bytes(pixels)
    assert len(body) == 0x839
    return struct.pack("<I", len(body)) + body


def build_record(template, rs, item):
    rec = bytearray(rs)
    rec[0:0x1C] = template[0:0x1C]
    struct.pack_into("<I", rec, 0x00, item["id"])
    struct.pack_into("<H", rec, 0x04, FLAGS)
    struct.pack_into("<H", rec, 0x08, 1)          # stack
    struct.pack_into("<H", rec, 0x10, 4)          # use time (as the empty slots have)
    entries = [(0, item["name"]), (1, item["article"]), (0, item["log"]), (0, item["plural"]), (0, item["desc"])]
    table = bytearray()
    heads = []
    base = 4 + 8 * len(entries)
    for kind, value in entries:
        heads.append((base + len(table), kind))
        if kind == 1:
            table += struct.pack("<I", value)
        else:
            text = value.encode("latin-1") + b"\0"
            text += b"\0" * (-len(text) % 4)
            table += struct.pack("<I", 1) + b"\0" * 24 + text
    blob = struct.pack("<I", len(entries)) + b"".join(struct.pack("<II", o, k) for o, k in heads) + table
    if 0x1C + len(blob) > 0x280:
        raise ValueError("%s: the texts are too long" % item["name"])
    rec[0x1C:0x1C + len(blob)] = blob
    icon = icon_block(os.path.join(ASSETS, item["icon"]), item["id"])
    rec[0x280:0x280 + len(icon)] = icon
    rec[rs - 1] = template[rs - 1]                 # end marker (0xFF)
    return rec


def dat_install(client, dry=False):
    path = os.path.join(client, DAT_REL)
    if not os.path.isfile(path):
        raise RuntimeError("Item file not found: " + path)
    rs = record_size(path)
    with open(path, "rb") as f:
        data = bytearray(f.read())
    template = read_record(data, rs, TEMPLATE_ID)
    problem = check_layout(template)
    if problem:
        raise RuntimeError("Not changing %s: %s." % (path, problem))
    ours = {it["name"] for it in ITEMS}
    for it in ITEMS:
        cur = item_name(read_record(data, rs, it["id"]))
        if cur not in (".", it["name"], "Dragon Chronicles") + tuple(it.get("old_names", ())):
            raise RuntimeError("Slot %d is already used by '%s'. Nothing was changed." % (it["id"], cur))
    if dry:
        return "would write %d items into %s" % (len(ITEMS), path)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    original = os.path.join(BACKUP_DIR, "ROM_118_107.DAT.original")
    if not os.path.exists(original):
        shutil.copy2(path, original)
        print("  Backed up the original to " + original)
    for it in ITEMS:
        i = it["id"] - FIRST_ID
        rec = build_record(template, rs, it)
        if PROBE == "copy":        # test: an exact copy of Page from the Dragon Chronicles, only the id changed
            rec = bytearray(template)
            struct.pack_into("<I", rec, 0, it["id"])
        elif PROBE == "oldicon":   # test: our texts, the Dragon Chronicles picture
            rec[0x280:0x280 + 0x839 + 4] = template[0x280:0x280 + 0x839 + 4]
        elif PROBE == "oldtext":   # test: Dragon Chronicles texts, our picture
            rec[0x1C:0x280] = template[0x1C:0x280]
        data[i * rs:(i + 1) * rs] = rot_enc(rec)
    tmp = path + ".crystalboy-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    # read back
    with open(path, "rb") as f:
        check = f.read()
    for it in ITEMS:
        if PROBE in ("copy", "oldtext"):
            continue
        if item_name(read_record(check, rs, it["id"])) != it["name"]:
            raise RuntimeError("Read-back check failed for %s" % it["name"])
    return "wrote %s into %s" % (", ".join("%s (%d)" % (it["name"], it["id"]) for it in ITEMS), path)


def dat_restore(client):
    path = os.path.join(client, DAT_REL)
    original = os.path.join(BACKUP_DIR, "ROM_118_107.DAT.original")
    if not os.path.exists(original):
        return "no backup found, nothing to restore"
    shutil.copy2(original, path)
    return "restored " + path


def dat_status(client):
    path = os.path.join(client, DAT_REL)
    rs = record_size(path)
    with open(path, "rb") as f:
        data = f.read()
    return ["  %5d  %-14s  %s" % (it["id"], it["name"], item_name(read_record(data, rs, it["id"])) or "?") for it in ITEMS]


# ---------------------------------------------------------------- server
# ---------------------------------------------------------------- key items (ROM\175\35.DAT, English key items)
# A "d_msg" file: 0x40-byte header, then fixed 0x2BC-byte entries, every byte XOR 0xFF. Each entry is a small
# table: [id, category, "", "", name, plural, description] (texts with the same 0x1C header as item texts).
# Key item 1634 exists in the game file with empty texts and is not used by the server: it becomes ours.
KI_REL = os.path.join("ROM", "175", "35.DAT")
KEY_ITEMS = [
    {
        "id": 1634, "category": 2, "name": "Memory of Jueno I", "plural": "Memories of Jueno I",
        "replaces": ("Memory of the Mana Tree",),
        "desc": "\nA memory the Recollection of Jueno I\nleft behind. While Signet is active,\nexperience from monsters is raised by 1%.",
    },
    {
        "id": 2605, "category": 2, "name": "Memory of Jueno II", "plural": "Memories of Jueno II",
        "replaces": ("Memory of the Tower",),
        "desc": "\nA memory the Recollection of Jueno II\nleft behind. While Signet is active,\nexperience from monsters is raised by 1%.",
    },
    {
        # the game file has a placeholder here; the server never uses this id
        "id": 2841, "category": 2, "name": "Memory of Jueno III", "plural": "Memories of Jueno III",
        "replaces": ("\x81Q", "Memory of the Magi"),
        "desc": "\nA memory the Recollection of Jueno III\nleft behind. While Signet is active,\nexperience from monsters is raised by 1%.",
    },
    {
        # a Rhapsodies-era "cheer" the server never gives on this 75-era server
        "id": 2716, "category": 2, "name": "Memory of Jueno IV", "plural": "Memories of Jueno IV",
        "replaces": ("Cheer: Lamb", "Memory of Time", "Memory of the Dungeon"),
        "desc": "\nA memory the Recollection of Jueno IV\nleft behind. While Signet is active,\nexperience from monsters is raised by 1%.",
    },
]
KI_ENTRY = 0x2BC


def ki_parse(e):
    count = struct.unpack_from("<I", e, 0)[0]
    out = []
    for k in range(count):
        off, kind = struct.unpack_from("<II", e, 4 + 8 * k)
        if kind == 1:
            out.append(struct.unpack_from("<I", e, off)[0])
        else:
            t = off + 0x1C
            out.append(bytes(e[t:e.index(b"\0", t)]).decode("latin-1"))
    return out


def ki_build(fields):
    heads, table = [], bytearray()
    base = 4 + 8 * len(fields)
    for v in fields:
        heads.append((base + len(table), 1 if isinstance(v, int) else 0))
        if isinstance(v, int):
            table += struct.pack("<I", v)
        else:
            text = v.encode("latin-1") + b"\0"
            text += b"\0" * (-len(text) % 4)
            table += struct.pack("<I", 1) + b"\0" * 24 + text
    blob = struct.pack("<I", len(fields)) + b"".join(struct.pack("<II", o, k) for o, k in heads) + table
    if len(blob) > KI_ENTRY:
        raise ValueError("key item texts are too long")
    return bytes(blob.ljust(KI_ENTRY, b"\0"))


def ki_entries(data):
    if data[:5] != b"d_msg" or struct.unpack_from("<I", data, 0x20)[0] != KI_ENTRY:
        raise RuntimeError("the key item file is not in the expected format")
    body = bytes(c ^ 0xFF for c in data[0x40:])
    n = len(body) // KI_ENTRY
    return {ki_parse(body[j * KI_ENTRY:(j + 1) * KI_ENTRY])[0]: j for j in range(n)}, body


def ki_install(client):
    path = os.path.join(client, KI_REL)
    with open(path, "rb") as f:
        data = bytearray(f.read())
    index, body = ki_entries(data)
    # check: rebuilding a real key item from its own fields gives the same bytes (the layout is understood)
    j = index.get(8)
    if j is None or ki_build(ki_parse(body[j * KI_ENTRY:(j + 1) * KI_ENTRY])) != body[j * KI_ENTRY:(j + 1) * KI_ENTRY]:
        raise RuntimeError("the key item layout is not the expected one; nothing was changed")
    for ki in KEY_ITEMS:
        if ki["id"] not in index:
            raise RuntimeError("key item %d is not in the game file" % ki["id"])
        cur = ki_parse(body[index[ki["id"]] * KI_ENTRY:(index[ki["id"]] + 1) * KI_ENTRY])
        if cur[4] not in ("", ki["name"]) + tuple(ki.get("replaces", ())):
            raise RuntimeError("key item %d is already used by '%s'; nothing was changed" % (ki["id"], cur[4]))
    os.makedirs(BACKUP_DIR, exist_ok=True)
    original = os.path.join(BACKUP_DIR, "ROM_175_35.DAT.original")
    if not os.path.exists(original):
        shutil.copy2(path, original)
    for ki in KEY_ITEMS:
        j = index[ki["id"]]
        entry = ki_build([ki["id"], ki["category"], "", "", ki["name"], ki["plural"], ki["desc"]])
        start = 0x40 + j * KI_ENTRY
        data[start:start + KI_ENTRY] = bytes(c ^ 0xFF for c in entry)
    tmp = path + ".crystalboy-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    with open(path, "rb") as f:
        index2, body2 = ki_entries(f.read())
    for ki in KEY_ITEMS:
        j = index2[ki["id"]]
        if ki_parse(body2[j * KI_ENTRY:(j + 1) * KI_ENTRY])[4] != ki["name"]:
            raise RuntimeError("read-back check failed for key item %d" % ki["id"])
    return "key item %s" % ", ".join("%s (%d)" % (k["name"], k["id"]) for k in KEY_ITEMS)


# ---------------------------------------------------------------- Anniversary Ring: no longer Rare, so rewards can stack
RING_REL = os.path.join("ROM", "118", "109.DAT")   # English armor, ids 10240+
RING_ID, RING_FIRST = 15793, 10240


def ring_install(client, rare=False):
    path = os.path.join(client, RING_REL)
    size = os.path.getsize(path)
    rs = 0x1400 if size % 0x1400 == 0 else 0xC00
    with open(path, "rb") as f:
        data = bytearray(f.read())
    i = RING_ID - RING_FIRST
    rec = bytearray(rot_dec(data[i * rs:(i + 1) * rs]))
    rid, flags = struct.unpack_from("<IH", rec, 0)
    if rid != RING_ID or (flags & 0x7FFF) != 0x7C40:
        raise RuntimeError("the Anniversary Ring record is not the expected one (id %d, flags %04X)" % (rid, flags))
    want = (flags | 0x8000) if rare else (flags & 0x7FFF)
    if want == flags:
        return "Anniversary Ring already %s" % ("Rare" if rare else "not Rare")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    original = os.path.join(BACKUP_DIR, "ROM_118_109.DAT.original")
    if not os.path.exists(original):
        shutil.copy2(path, original)
    struct.pack_into("<H", rec, 4, want)
    data[i * rs:(i + 1) * rs] = rot_enc(rec)
    tmp = path + ".crystalboy-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return "Anniversary Ring is now %s" % ("Rare" if rare else "not Rare (you can hold several)")


def sql_text():
    lines = ["-- Crystal Boy items (written by install_crystalboy_items.py). Listed in modules/init.txt so dbtool",
             "-- puts them back after a server update. Flags: CanUse, CanTradeNPC, NoAuction, NoSale, NoDelivery, Ex, Rare.",
             "-- No item scripts: the Crystal Boy addon handles 'Use' in the game window, so nothing is used up.", ""]
    for it in ITEMS:
        lines.append("REPLACE INTO `item_basic` (`itemid`,`subid`,`name`,`sortname`,`name_jp`,`type`,`stackSize`,`flags`,`aH`,`BaseSell`) "
                     "VALUES (%d,0,'%s','%s','%s',5,1,%d,0,0);" % (it["id"], it["key"], it["key"], it["name"], FLAGS))
        lines.append("REPLACE INTO `item_usable` (`itemid`,`name`,`validTargets`,`activation`,`animation`,`animationTime`,`maxCharges`,`useDelay`,`reuseDelay`,`aoe`) "
                     "VALUES (%d,'%s',1,0,0,0,0,0,0,0);" % (it["id"], it["key"]))
    lines.append("")
    lines.append("-- Anniversary Ring: not Rare, so Recollection rewards can give more than one")
    lines.append("UPDATE `item_basic` SET `flags` = `flags` & ~32768 WHERE `itemid` = %d;" % RING_ID)
    return "\n".join(lines) + "\n"


def server_install(server, cfg, apply_db=True, connect=None):
    sql_path = os.path.join(server, SQL_REL)
    os.makedirs(os.path.dirname(sql_path), exist_ok=True)
    text = sql_text()
    with open(sql_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    init = os.path.join(server, "modules", "init.txt")
    with open(init, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if not any(l.strip() == INIT_LINE for l in lines):
        shutil.copy2(init, init + ".before-crystalboy-items")
        with open(init, "a", encoding="utf-8", newline="") as f:
            f.write("\n# Crystal Boy items\n" + INIT_LINE + "\n")
    if not apply_db:
        return "wrote " + sql_path
    conn = (connect or _connect)(cfg)
    cur = conn.cursor()
    body = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))
    for stmt in [s.strip() for s in body.split(";")]:
        if stmt:
            cur.execute(stmt)
    conn.commit()
    ids = [it["id"] for it in ITEMS]
    cur.execute("SELECT COUNT(*) FROM item_basic WHERE itemid IN (%s)" % ",".join("?" * len(ids)), ids)
    n = cur.fetchone()[0]
    conn.close()
    if n != len(ITEMS):
        raise RuntimeError("the database has %d of %d items after writing" % (n, len(ITEMS)))
    return "database rows written (%d items)" % n


def server_remove(server, cfg, connect=None):
    init = os.path.join(server, "modules", "init.txt")
    with open(init, encoding="utf-8") as f:
        lines = f.read().splitlines()
    keep = [l for l in lines if l.strip() not in (INIT_LINE, "# Crystal Boy items")]
    if keep != lines:
        with open(init, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(keep) + "\n")
    conn = (connect or _connect)(cfg)
    cur = conn.cursor()
    ids = [it["id"] for it in ITEMS]
    marks = ",".join("?" * len(ids))
    cur.execute("SELECT COUNT(*) FROM char_inventory WHERE itemId IN (%s)" % marks, ids)
    held = cur.fetchone()[0]
    if held:
        conn.close()
        return "kept the server rows: %d of these items are still in characters' bags (drop them first)" % held
    cur.execute("DELETE FROM item_usable WHERE itemid IN (%s)" % marks, ids)
    cur.execute("DELETE FROM item_basic WHERE itemid IN (%s)" % marks, ids)
    conn.commit()
    conn.close()
    return "server rows removed"


def _connect(cfg):
    import mariadb
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])


def game_running():
    if os.name != "nt":
        return False
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq pol.exe"], capture_output=True, text=True).stdout
        return "pol.exe" in out.lower()
    except OSError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Crystal Boy items")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--restore", action="store_true")
    ap.add_argument("--dat-only", action="store_true")
    ap.add_argument("--server-only", action="store_true")
    ap.add_argument("--client", help="game folder (default: config.json ffxi_client_dir)")
    ap.add_argument("--server", help="server folder (default: config.json server_dir)")
    ap.add_argument("--probe", choices=["copy", "oldicon", "oldtext"], help="crash tests (write a variant record)")
    a = ap.parse_args(argv)
    global PROBE
    PROBE = a.probe
    cfg = kit_config()
    client = a.client or cfg.get("ffxi_client_dir", r"C:\Program Files (x86)\PlayOnline\SquareEnix\FINAL FANTASY XI")
    server = a.server or cfg.get("server_dir", r"C:\ffxi-local\server")

    if a.status:
        print("Client item file (%s):" % os.path.join(client, DAT_REL))
        for line in dat_status(client):
            print(line)
        try:
            with open(os.path.join(client, KI_REL), "rb") as f:
                index, body = ki_entries(f.read())
            for ki in KEY_ITEMS:
                j = index[ki["id"]]
                print("  key item %d: %r" % (ki["id"], ki_parse(body[j * KI_ENTRY:(j + 1) * KI_ENTRY])[4]))
        except (OSError, RuntimeError, KeyError) as ex:
            print("  key items: %s" % ex)
        print("Server rows file: %s" % ("present" if os.path.exists(os.path.join(server, SQL_REL)) else "missing"))
        return 0

    if (not a.server_only) and game_running():
        print("Please close the game first (the item file is read when the game starts).")
        return 1

    try:
        if a.restore:
            if not a.server_only:
                print("1. " + dat_restore(client))
                for name, rel in (("key item file", KI_REL), ("armor file", RING_REL)):
                    orig = os.path.join(BACKUP_DIR, os.path.basename(os.path.dirname(rel)).join(["ROM_", "_"]) + os.path.basename(rel) + ".original")
                    if os.path.exists(orig):
                        shutil.copy2(orig, os.path.join(client, rel))
                        print("   restored the " + name)
            if not a.dat_only:
                print("2. " + server_remove(server, cfg))
            print("Done. Restart the server (launcher STOP, then PLAY).")
            return 0
        if not a.server_only:
            print("1. Client item file")
            print("  " + dat_install(client))
            if not PROBE:
                print("  " + ki_install(client))
                print("  " + ring_install(client))
        if not a.dat_only:
            print("2. Server")
            print("  " + server_install(server, cfg))
    except RuntimeError as ex:
        print("Stopped: %s" % ex)
        return 1
    print("\nDone. Restart the server (launcher STOP, then PLAY), then start the game.")
    print("Test on the GM character: !additem %d (Crystal Boy), !additem 8101-8104 (Recollections)." % ITEMS[0]["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
