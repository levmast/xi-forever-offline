"""Forever Track Pants (item 23868, internal name forever_jeans): beta testers' legs, made from the Track Pants (27325,
sneakers built in), which stay as they were.

What it changes in the FINAL FANTASY XI folder (originals kept once in backups\\forever-jeans):
  * Look: legs model 517 (the legs of a free set; the Forever Patch uses that set's head) gets the Denim Pants' model
    (legs model 479) with a new texture in the Forever Beta Shirt's colours: the denim turns royal purple, the
    stitching turns gold, the waistband, cuffs and a side stripe turn black, and a small glowing crystal sits on each knee and on the back pocket. Built from the player's own game files; no Square Enix art is stored in the kit.
  * Item: the empty armor slot 23868 in ROM\\286\\73.DAT gets name, description and the Denim Pants icon recoloured,
    and the Warp Ring's use (one charge that never runs out, 8 seconds after equipping, 10 minutes between uses).
The server side is modules\\custom\\lua\\forever_jeans.lua + modules\\custom\\sql\\forever_jeans.sql.
Stats: DEF:1, Fishing skill +1. Use: Warp (to your home point), like the Warp Ring.

    python forever_jeans.py status | apply | restore | preview | server   (server: the item's rows into the running database)
    preview writes logs\\forever-jeans\\<race>_before.png and <race>_after.png (changes nothing).
"""
import argparse, json, os, shutil, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import forever_beta_shirt as fbs                     # shared: game files, DXT3 encoder, item record helpers

VERSION = 3                       # bump when the design changes, so installs rebuild (2: black accents, 3: Track Pants)
ITEM_ID = 23868
TEMPLATES = [(27325, "Track Pants"), (25911, "Denim Pants")]   # the first one the item file holds (its icon, and the
                                  # client then knows the feet slot is blocked); the Denim Pants are sure to be there
SLOT = 3                          # head 0, body 1, hands 2, legs 3, feet 4
SRC_MODEL, NEW_MODEL = 579, 517   # Track Pants' legs model (sneakers built in) -> our legs model (a free one)
ITEM_FILE, ITEM_FIRST, RS = "ROM/286/73.DAT", 23040, 0x1400
RACES = fbs.RACES
BACKUP = os.path.join(KIT, "backups", "forever-jeans")
STATE = os.path.join(BACKUP, "state.json")

ITEM = {
    "name": "Forever Track Pants", "log": "pair of Forever Track Pants", "plural": "pairs of Forever Track Pants",
    "desc": "DEF:1 Fishing skill +2\nCannot equip footgear\nEnchantment: Teleport (Home Point)",
    "flags": 0xFC40,              # as the shirt: CanUse + CanEquip, NoAuction, NoSale, NoDelivery, Ex, Rare
    "targets": 1, "charges": 1, "cast": 8, "delay": 8, "recast": 600,     # the Warp Ring's
}

def file_id(r, model):
    """The game file number of a race's model (dev\\model-ids\\ft.py): armor models sit in blocks per race and slot."""
    if 256 <= model < 320:
        return 63067 + r * 448 + SLOT * 64 + model
    if 320 <= model < 576:
        return 70927 + r * 1536 + SLOT * 256 + model
    if 576 <= model < 608:
        return 98211 + r * 160 + SLOT * 32 + model
    raise ValueError("model %d is outside the known blocks" % model)


def model_files(g, model):
    t = fbs.file_table(g)
    return {race: t[file_id(r, model)] for r, race in enumerate(RACES)}


def shared_with(g, path):
    """How many model numbers use this game file (a placeholder file is shared by many; ours must not be)."""
    return sum(1 for p in fbs.file_table(g).values() if p == path)


def keep_original(g, rel):
    bk = os.path.join(BACKUP, *rel.split("/")) + ("" if rel.endswith(".DAT") else ".DAT")
    if not os.path.exists(bk):
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        shutil.copy2(fbs.gpath(g, rel), bk)
    return bk


# ------------------------------------------------------------------ texture
from PIL import Image, ImageChops, ImageFilter


def masks(img):
    H, S, V = img.convert("RGB").convert("HSV").split()
    m = lambda ch, lo, hi: ch.point(lambda v: 255 if lo <= v <= hi else 0)
    mul = lambda *ms: ms[0] if len(ms) == 1 else ImageChops.multiply(ms[0], mul(*ms[1:]))
    denim = mul(m(H, 115, 190), m(S, 30, 255))                    # the blue cloth
    # the stitching: thin lines lighter than the cloth round them (seams, the pocket's edge), inside the denim only
    local = V.filter(ImageFilter.BoxBlur(3))
    seam = mul(ImageChops.subtract(V, local).point(lambda v: 255 if v > 16 else 0), denim)
    # keep lines, drop the cloth's speckles: a stitch pixel has at least two stitch pixels next to it
    seam = mul(seam, seam.filter(ImageFilter.BoxBlur(1)).point(lambda v: 255 if v >= 255 * 3 // 9 else 0))
    return H, S, V, denim, seam


def denim_box(denim):
    """The main block of denim: the rows that are mostly denim (Galka's waist strip above it is left out)."""
    w, h = denim.size
    px = denim.load()
    rows = [y for y in range(h) if sum(1 for x in range(w) if px[x, y]) > w * 0.6]
    if not rows:
        return denim.getbbox()
    return (0, rows[0], w, rows[-1] + 1)


def recolor(img):
    """Denim -> royal purple; its stitching -> gold. Anything else (Galka's waist cloth, skin) keeps its colours."""
    a = img.getchannel("A")
    H, S, V, denim, seam = masks(img)
    c = lambda v: Image.new("L", img.size, v)
    H2 = Image.composite(c(196), H, denim)
    S2 = Image.composite(S.point(lambda v: min(255, v * 13 // 10 + 25)), S, denim)
    V2 = Image.composite(V.point(lambda v: min(255, v * 95 // 100 + 8)), V, denim)
    H2 = Image.composite(c(32), H2, seam); S2 = Image.composite(c(170), S2, seam)
    V2 = Image.composite(V.point(lambda v: min(255, int(v * 1.15 + 30))), V2, seam)
    out = Image.merge("HSV", (H2, S2, V2)).convert("RGB"); out.putalpha(a)
    return out


# Where the crystals go, as fractions of the denim's area on the texture (it is 128 x 128, Tarutaru 128 x 64, Galka's
# starts lower): the left half is the front of the leg, the right half the back with the patch pocket. Each leg shows
# the same pixels. (2026-11-25, v1: placed from the texture, not yet checked in game.) Text is left out: at this size
# letters would be 5 pixels tall, and one leg would show them backwards.
CRYSTALS = [(0.26, 0.60, 1.0),          # the knee
            (0.76, 0.13, 0.75)]         # the back pocket


# Black accents (the user, 2026-11-25: the boots will be black too), as fractions of the denim block: the waistband,
# the cuffs and a stripe down the side seam (the line between the front and back halves). The gold stitching stays on top.
BLACK = (22, 16, 30)
BANDS = {"waist": (0.0, 0.075), "cuff": (0.90, 1.0)}
STRIPE = (0.5, 0.035)             # centre and half-width of the side stripe


def blacken(out, img, denim, seam, box):
    from PIL import ImageDraw
    w, h = img.size
    x0, y0, x1, y1 = box; bw, bh = x1 - x0, y1 - y0
    area = Image.new("L", img.size, 0); d = ImageDraw.Draw(area)
    for a, b in BANDS.values():
        d.rectangle((x0, y0 + bh * a, x1, y0 + bh * b), fill=255)
    cx, half = x0 + bw * STRIPE[0], bw * STRIPE[1]
    # the stripe follows the seam itself: the column of strongest stitching near the middle
    cols = [sum(1 for y in range(y0, y1) if seam.getpixel((x, y))) for x in range(int(cx - bw * 0.08), int(cx + bw * 0.08))]
    if cols and max(cols) > bh * 0.3:
        cx = int(cx - bw * 0.08) + cols.index(max(cols)) + 0.5
    d.rectangle((cx - half, y0, cx + half, y1), fill=255)
    area = ImageChops.multiply(area, denim)
    shade = img.convert("L").point(lambda v: v)              # keep the cloth's folds in the black
    blk = Image.merge("RGB", [shade.point(lambda v, c=c: min(255, int(c + v * 0.18))) for c in BLACK])
    rgb = Image.composite(blk, out.convert("RGB"), area)
    gold = out.convert("RGB")                                 # the stitching again, on top
    rgb = Image.composite(gold, rgb, seam)
    res = rgb.convert("RGBA"); res.putalpha(img.getchannel("A"))
    return res


def design(img, race):
    out = recolor(img)
    _, _, _, denim, seam = masks(img)
    box = denim_box(denim)
    if box:
        out = blacken(out, img, denim, seam, box)
        import forever_patch as fp
        bw, bh = box[2] - box[0], box[3] - box[1]
        for fx, fy, size in CRYSTALS:
            w = max(6, int(bw * 0.075 * size)); h = max(9, int(w * 1.45 * (bh / bw if bh < bw * 0.75 else 1)))
            fp.put(out, fp.glow(fp.crystal_sprite(w, h), 2, 0.8), box[0] + bw * fx, box[1] + bh * fy)
    a = img.getchannel("A"); out = out.convert("RGB"); out.putalpha(a)
    return out


def textures(d):
    """Every DXT3 texture in a model file: [(offset of the pixels, width, height)]."""
    out, o = [], 0
    while o + 16 <= len(d):
        v = struct.unpack_from("<I", d, o + 4)[0]; kind = v & 0x7F; size = ((v >> 7) & 0x7FFFF) * 16
        if kind == 0x20 and d[o + 73:o + 77][::-1] == b"DXT3":
            w, h = struct.unpack_from("<ii", d, o + 37)
            out.append((o + 85, w, abs(h)))
        if size <= 0:
            break
        o += size
    if not out:
        raise RuntimeError("no DXT3 texture in the Denim Pants model")
    return out


def build_model(src, race):
    d = bytearray(src)
    before, after = [], []
    for off, w, h in textures(src):
        n = w * h
        img = Image.frombytes("RGBA", (w, h), bytes(src[off:off + n]), "bcn", (2,))
        new = design(img, race)
        enc = fbs.dxt3_encode(new)
        if len(enc) != n:
            raise RuntimeError("texture encoder size mismatch (%d of %d bytes)" % (len(enc), n))
        fbs.check_encoding(enc, new)
        d[off:off + n] = enc
        before.append(img); after.append(new)
    return bytes(d), before, after


# ------------------------------------------------------------------ item record
def icon_recolor(block):
    block = bytearray(block)
    pal_at = 4 + 1 + 16 + 40
    pal = block[pal_at:pal_at + 1024]
    px = Image.new("RGBA", (256, 1))
    px.putdata([(pal[i * 4 + 2], pal[i * 4 + 1], pal[i * 4], 255) for i in range(256)])
    raw = recolor(px).convert("RGB").tobytes()
    for i, (r, g, b) in enumerate(zip(raw[0::3], raw[1::3], raw[2::3])):
        if i == 0:
            continue
        block[pal_at + i * 4:pal_at + i * 4 + 3] = bytes((b, g, r))
    return bytes(block)


def template(data):
    """The first of TEMPLATES that the item file holds, as (id, record)."""
    for tid, name in TEMPLATES:
        try:
            rec = record(data, tid)
            if struct.unpack_from("<I", rec, 0)[0] == tid and fbs.strings(rec)[0] == name:
                return tid, rec
        except (RuntimeError, ValueError, struct.error):
            pass
    raise RuntimeError("neither the Track Pants nor the Denim Pants record is where expected")


def build_record(template):
    rec = bytearray(template)
    struct.pack_into("<I", rec, 0x00, ITEM_ID)
    struct.pack_into("<I", rec, 0x04, ITEM["flags"])
    struct.pack_into("<H", rec, 0x0E, ITEM["targets"])
    rec[0x20] = ITEM["charges"]; rec[0x21] = ITEM["cast"]
    struct.pack_into("<H", rec, 0x22, ITEM["delay"]); struct.pack_into("<I", rec, 0x24, ITEM["recast"])
    entries = [(0, ITEM["name"]), (1, 0), (0, ITEM["log"]), (0, ITEM["plural"]), (0, ITEM["desc"])]
    table = bytearray(); heads = []; base = 4 + 8 * len(entries)
    for kind, value in entries:
        heads.append((base + len(table), kind))
        if kind == 1:
            table += struct.pack("<I", value)
        else:
            text = value.encode("latin-1") + b"\0"; text += b"\0" * (-len(text) % 4)
            table += struct.pack("<I", 1) + b"\0" * 24 + text
    blob = struct.pack("<I", len(entries)) + b"".join(struct.pack("<II", o, k) for o, k in heads) + table
    if 0x30 + len(blob) > 0x280:
        raise ValueError("texts too long")
    rec[0x30:0x280] = b"\0" * (0x280 - 0x30)
    rec[0x30:0x30 + len(blob)] = blob
    size = struct.unpack_from("<I", rec, 0x280)[0]
    if size != 0x839 or rec[0x284:0x28D] != b"\x91armor   ":
        raise RuntimeError("the icon is not where expected")
    icon = bytearray(icon_recolor(rec[0x280:0x280 + 4 + size])); icon[13:21] = ("%05d   " % ITEM_ID).encode("ascii")
    rec[0x280:0x280 + len(icon)] = icon
    return bytes(rec)


def record(data, item_id):
    i = item_id - ITEM_FIRST
    if i < 0 or (i + 1) * RS > len(data):
        raise RuntimeError("item %d is not in %s" % (item_id, ITEM_FILE))
    return bytearray(fbs.rot_dec(data[i * RS:(i + 1) * RS]))


# ------------------------------------------------------------------ apply / status / restore
def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(BACKUP, exist_ok=True)
    with open(STATE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(STATE + ".tmp", STATE)


def item_ok(g):
    try:
        return fbs.strings(record(fbs.read(fbs.gpath(g, ITEM_FILE)), ITEM_ID))[0] == ITEM["name"]
    except (ValueError, struct.error, RuntimeError):
        return False


def _apply_look(g, st, rebuild, log):
    done = []
    src_files, new_files = model_files(g, SRC_MODEL), model_files(g, NEW_MODEL)
    for race in RACES:
        if shared_with(g, new_files[race]) != 1:
            raise RuntimeError("legs model %d's file for %s is shared with other models; not changed" % (NEW_MODEL, race))
        sp, np_ = fbs.gpath(g, src_files[race]), fbs.gpath(g, new_files[race])
        if rebuild or fbs.sha(fbs.read(np_)) != st.get("models", {}).get(race):
            src = fbs.read(sp)
            keep_original(g, new_files[race])
            data, _, _ = build_model(src, race)
            fbs.write(np_, data)
            st.setdefault("models", {})[race] = fbs.sha(data); st.setdefault("denim", {})[race] = fbs.sha(src)
            done.append(race)
    return done


def apply(g, log=print, force=False):
    """Writes only what is missing. Returns a message, or None when everything was already in place."""
    st = load_state(); done = []; problem = None
    rebuild = force or st.get("version") != VERSION
    try:
        done += _apply_look(g, st, rebuild, log)
    except PermissionError:
        raise
    except Exception as e:                   # the item still gets its name; the look is tried again at the next PLAY
        problem = e; st["version"] = None
    save_state(st)
    if rebuild or not item_ok(g):
        path = fbs.gpath(g, ITEM_FILE)
        keep_original(g, ITEM_FILE)
        data = bytearray(fbs.read(path))
        cur = record(data, ITEM_ID)
        if fbs.strings(cur)[0] not in (".", ITEM["name"]):
            raise RuntimeError("item slot %d is used by '%s'" % (ITEM_ID, fbs.strings(cur)[0]))
        rec = build_record(template(data)[1])
        i = ITEM_ID - ITEM_FIRST
        data[i * RS:(i + 1) * RS] = fbs.rot_enc(rec)
        try:
            fbs.write(path, bytes(data))
        except PermissionError:
            raise RuntimeError("the item file is in use: close FINAL FANTASY XI and run this again")
        if not item_ok(g):
            raise RuntimeError("read-back check of the item failed")
        done.append("item")
    if problem is None:
        st["version"] = VERSION
    save_state(st)
    if problem is not None:
        return "Forever Track Pants: item %s; their look was skipped (%s)." % ("updated" if "item" in done else "in place", problem)
    if not done:
        return None
    return "Forever Track Pants: game files updated (%s)." % ", ".join(done)


def status(g):
    st = load_state(); out = []
    data = fbs.read(fbs.gpath(g, ITEM_FILE))
    try:
        tid, rec = template(data)
        out.append("item record made from %d: %s" % (tid, fbs.strings(rec)[0]))
    except Exception as e:
        out.append("template: NOT FOUND (%s)" % e)
    try:
        out.append("item slot %d: '%s' (%s)" % (ITEM_ID, fbs.strings(record(data, ITEM_ID))[0],
                                                 "ours" if item_ok(g) else "free" if fbs.strings(record(data, ITEM_ID))[0] == "." else "USED BY ANOTHER ITEM"))
    except Exception as e:
        out.append("item slot %d: unreadable (%s)" % (ITEM_ID, e))
    src = model_files(g, SRC_MODEL)
    for race, p in model_files(g, NEW_MODEL).items():
        cur = fbs.sha(fbs.read(fbs.gpath(g, p)))
        n = shared_with(g, p)
        out.append("%-9s track %-14s -> ours %-14s %s%s" % (race, src[race], p,
                   "ours" if cur == st.get("models", {}).get(race) else "not written yet",
                   "" if n == 1 else "  (SHARED by %d models!)" % n))
    return out


def restore(g):
    """Puts back the model files. The item file is shared with the shirt and the patch, so only our record is blanked."""
    out = []
    for rel in model_files(g, NEW_MODEL).values():
        bk = os.path.join(BACKUP, *rel.split("/")) + ".DAT"
        if os.path.exists(bk):
            shutil.copy2(bk, fbs.gpath(g, rel)); out.append("restored " + rel)
    bk = os.path.join(BACKUP, *ITEM_FILE.split("/"))
    if os.path.exists(bk):
        orig = fbs.read(bk); path = fbs.gpath(g, ITEM_FILE); data = bytearray(fbs.read(path))
        i = ITEM_ID - ITEM_FIRST
        data[i * RS:(i + 1) * RS] = orig[i * RS:(i + 1) * RS]
        fbs.write(path, bytes(data)); out.append("item %d blanked" % ITEM_ID)
    if os.path.exists(STATE):
        os.replace(STATE, STATE + ".restored")
    return out


def server_db(log=print):
    """Puts the item's rows (modules/custom/sql/forever_jeans.sql) into the running database now, like dbtool would."""
    with open(os.path.join(KIT, "config.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    sql_path = os.path.join(cfg["server_dir"], "modules", "custom", "sql", "forever_jeans.sql")
    with open(sql_path, encoding="utf-8") as f:
        body = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("--"))
    import mariadb
    conn = mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])
    cur = conn.cursor()
    for stmt in [x.strip() for x in body.split(";") if x.strip()]:
        cur.execute(stmt)
    conn.commit()
    cur.execute("SELECT b.name, e.MId, u.reuseDelay FROM item_basic b JOIN item_equipment e ON e.itemId = b.itemid "
                "JOIN item_usable u ON u.itemid = b.itemid WHERE b.itemid = ?", (ITEM_ID,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError("the rows are not in the database after writing")
    return "Database: %s, model %d, %d s between warps." % row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "apply", "restore", "preview", "server"])
    ap.add_argument("--game"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "server":
        print(server_db()); return
    g = fbs.game_dir(a.game)
    if a.cmd == "status":
        print("\n".join(status(g)))
    elif a.cmd in ("apply", "restore"):
        print((apply(g, force=a.force) or "Forever Track Pants: already in place.") if a.cmd == "apply" else ("\n".join(restore(g)) or "nothing to restore"))
        try:
            import launcher_setup
            launcher_setup.record_era_state(KIT, g)
        except Exception as problem:
            print("(could not record the era files' state: %s)" % problem)
    else:
        out = os.path.join(KIT, "logs", "forever-jeans"); os.makedirs(out, exist_ok=True)
        for race, p in model_files(g, SRC_MODEL).items():
            _, before, after = build_model(fbs.read(fbs.gpath(g, p)), race)
            for k, (b, a_) in enumerate(zip(before, after)):
                tag = "" if k == 0 else "_%d" % k
                b.save(os.path.join(out, "%s%s_before.png" % (race, tag))); a_.save(os.path.join(out, "%s%s_after.png" % (race, tag)))
            print("preview", race, [im.size for im in before])


if __name__ == "__main__":
    main()
