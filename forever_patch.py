"""Forever Patch (item 23867): its own item and look, made from the Eyepatch (11482), which stays as it was.

What it changes in the FINAL FANTASY XI folder (originals kept once in backups\\forever-patch):
  * Look: head model 517 (unused by any item) gets the Eyepatch's model with a new texture in the Forever Beta
    Shirt's colours: royal purple leather, gold straps and studs, a big glowing crystal in the middle of the patch
    (the Eyepatch's cross is covered), FOREVER above it and BETA below it in gold. Built from the player's own game files; no Square Enix art is stored in the kit.
  * Item: the empty armor slot 23867 in ROM\\286\\73.DAT gets name, description, the Eyepatch icon recoloured,
    and 5 charges / 15 hours like the Forever Beta Shirt.
The server side is modules\\custom\\lua\\forever_patch.lua + modules\\custom\\sql\\forever_patch.sql.
Not yet checked in game (2026-11-25): where the texture's parts land on the head.

    python forever_patch.py status | apply | restore | preview | server   (server: the item's rows into the running database)
"""
import argparse, json, os, shutil, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, KIT)
import forever_beta_shirt as fbs                     # shared: game files, DXT3 encoder, item record helpers

VERSION = 3                       # bump when the design changes, so installs rebuild
ITEM_ID, TEMPLATE_ID = 23867, 11482
NEW_MODEL = 517                   # a free head model (all 7 races have their own file; no item uses it)
SRC_FILES = {"HumeM": "ROM/218/124", "HumeF": "ROM/219/62", "ElvaanM": "ROM/219/65", "ElvaanF": "ROM/219/70",
             "Tarutaru": "ROM/219/73", "Mithra": "ROM/219/78", "Galka": "ROM/219/81"}     # the Eyepatch (head model 233)
TEMPLATE_FILE, TEMPLATE_FIRST = "ROM/118/109.DAT", 10240   # the English armor file
ITEM_FILE, ITEM_FIRST, RS = "ROM/286/73.DAT", 23040, 0x1400
RACES = fbs.RACES
BACKUP = os.path.join(KIT, "backups", "forever-patch")
STATE = os.path.join(BACKUP, "state.json")

ITEM = {
    "name": "Forever Patch", "log": "Forever Patch", "plural": "Forever Patches",
    "desc": "DEF:1 Fishing skill +1\nExperience point bonus: +75%\nMax. duration: 720 min.\nMaximum bonus: 4000",
    "flags": 0xFC40,              # as the shirt: CanUse + CanEquip, NoAuction, NoSale, NoDelivery, Ex, Rare
    "targets": 1, "charges": 5, "cast": 4, "delay": 15, "recast": 54000,
}


def model_files(g):
    t = fbs.file_table(g)
    return {race: t[70927 + r * 1536 + 0 * 256 + NEW_MODEL] for r, race in enumerate(RACES)}   # head models 320-575


def keep_original(g, rel):
    bk = os.path.join(BACKUP, *rel.split("/")) + ("" if rel.endswith(".DAT") else ".DAT")
    if not os.path.exists(bk):
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        shutil.copy2(fbs.gpath(g, rel), bk)
    return bk


# ------------------------------------------------------------------ texture
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat
import math

def crystal_sprite(w, h, scale=4):
    W, H = w * scale, h * scale
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    cx = W / 2; top, bot = H * 0.02, H * 0.98; ch = bot - top
    sy = top + ch * 0.30
    lo, li, ri, ro = cx - W * 0.48, cx - W * 0.17, cx + W * 0.17, cx + W * 0.48
    sh = [(lo, sy), (li, sy + ch * 0.03), (ri, sy + ch * 0.03), (ro, sy)]
    T, B = (cx, top), (cx, bot)
    for i, c in enumerate([(70, 130, 210), (185, 232, 255), (70, 130, 210)]):
        d.polygon([T, sh[i], sh[i + 1]], fill=c + (255,))
    for i, c in enumerate([(40, 85, 170), (125, 200, 250), (40, 85, 170)]):
        d.polygon([B, sh[i], sh[i + 1]], fill=c + (255,))
    lw = max(2, scale)
    for p in sh:
        d.line([T, p], fill=(225, 245, 255, 255), width=lw); d.line([B, p], fill=(150, 205, 250, 255), width=lw)
    d.line(sh, fill=(225, 245, 255, 255), width=lw)
    d.line([T, sh[0], B, sh[3], T], fill=(15, 25, 60, 255), width=lw * 2)
    sx, sp = cx, sy - ch * 0.08
    d.polygon([(sx, sp - ch * 0.07), (sx + W * 0.07, sp), (sx, sp + ch * 0.07), (sx - W * 0.07, sp)], fill=(255, 255, 255, 240))
    return L.resize((w, h), Image.LANCZOS)

def glow(sprite, radius, strength, colour=(150, 215, 255)):
    pad = radius * 3
    big = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), colour + (0,))
    a = Image.new("L", big.size, 0); a.paste(sprite.getchannel("A"), (pad, pad))
    big.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(min(255, v * strength))))
    big.alpha_composite(sprite, (pad, pad))
    return big

def put(canvas, sprite, cx, cy):
    x, y = int(round(cx - sprite.width / 2)), int(round(cy - sprite.height / 2))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0)); layer.paste(sprite, (x, y), sprite); canvas.alpha_composite(layer)

def masks(img):
    H, S, V = img.convert("RGB").convert("HSV").split()
    m = lambda ch, lo, hi: ch.point(lambda v: 255 if lo <= v <= hi else 0)
    mul = lambda *ms: ms[0] if len(ms) == 1 else ImageChops.multiply(ms[0], mul(*ms[1:]))
    metal = mul(m(S, 0, 60), m(V, 100, 255))
    brown = mul(m(H, 8, 40), m(S, 61, 255), m(V, 50, 255))
    red = mul(ImageChops.lighter(m(H, 0, 7), m(H, 235, 255)), m(S, 120, 255), m(V, 90, 255))
    teal = mul(m(H, 110, 160), m(S, 90, 255))
    leather = ImageChops.subtract(ImageChops.subtract(ImageChops.subtract(ImageChops.subtract(Image.new("L", img.size, 255), metal), brown), red), teal)
    return H, S, V, metal, brown, red, teal, leather

def recolor(img):
    """Leather -> royal purple, brown straps and grey metal -> gold, red stones -> crystal blue; the teal gem stays."""
    a = img.getchannel("A")
    H, S, V, metal, brown, red, teal, leather = masks(img)
    c = lambda v: Image.new("L", img.size, v)
    H2 = Image.composite(c(196), H, leather); S2 = Image.composite(c(150), S, leather)
    V2 = Image.composite(V.point(lambda v: min(255, int(v * 1.35 + 22))), V, leather)
    for mk, hue, sat, f, add in ((brown, 30, 165, 1.25, 25), (metal, 32, 120, 1.08, 10)):
        H2 = Image.composite(c(hue), H2, mk); S2 = Image.composite(c(sat), S2, mk)
        V2 = Image.composite(V.point(lambda v, f=f, add=add: min(255, int(v * f + add))), V2, mk)
    H2 = Image.composite(c(140), H2, red); S2 = Image.composite(c(140), S2, red)
    out = Image.merge("HSV", (H2, S2, V2)).convert("RGB"); out.putalpha(a)
    return out

def cross_box(img):
    """Bounding box of the metal ornament on the patch (rows 20-150, x 100-245)."""
    _, _, _, metal, *_ = masks(img)
    crop = metal.crop((100, 20, 245, 150))
    bb = crop.getbbox()
    return None if not bb else (bb[0] + 100, bb[1] + 20, bb[2] + 100, bb[3] + 20)

FONTS = [r"C:\Windows\Fonts\georgiab.ttf", r"C:\Windows\Fonts\timesbd.ttf", r"C:\Windows\Fonts\arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]

def strap_text(out, orig, segments):
    """Gold letters with a dark edge on the strap strip; brightness follows the leather underneath."""
    font_path = next((f for f in FONTS if os.path.exists(f)), None)
    fill = Image.new("L", out.size, 0); edge = Image.new("L", out.size, 0)
    df, de = ImageDraw.Draw(fill), ImageDraw.Draw(edge)
    for text, (x0, y0, x1, y1) in segments:
        pt = 30
        while pt > 7:
            font = ImageFont.truetype(font_path, pt)
            b = font.getbbox(text, stroke_width=2)
            if b[2] - b[0] <= x1 - x0 - 4 and b[3] - b[1] <= y1 - y0 - 2:
                break
            pt -= 1
        x = x0 + (x1 - x0 - (b[2] - b[0])) // 2 - b[0]; y = y0 + (y1 - y0 - (b[3] - b[1])) // 2 - b[1]
        de.text((x, y), text, font=font, fill=255, stroke_width=2, stroke_fill=255)
        df.text((x, y), text, font=font, fill=255)
    lum = orig.convert("L")
    gold = Image.merge("RGB", [lum.point(lambda v: min(255, int(190 + v * 0.8))), lum.point(lambda v: min(255, int(150 + v * 0.7))),
                               lum.point(lambda v: min(255, int(55 + v * 0.4)))])
    rgb = out.convert("RGB")
    rgb = Image.composite(Image.new("RGB", out.size, (24, 10, 30)), rgb, edge.point(lambda v: int(v * 0.9)))
    rgb = Image.composite(gold, rgb, fill)
    a = out.getchannel("A"); rgb = rgb.convert("RGBA"); rgb.putalpha(a)
    return rgb

def strap_rows(img):
    a = img.getchannel("A"); w, h = img.size
    rows = [y for y in range(180, h) if sum(1 for x in range(0, w, 4) if a.getpixel((x, y)) > 128) > 40]
    return (min(rows), max(rows)) if rows else (210, 245)

PATCH_CENTRE = {"default": (118, 98), "Mithra": (134, 112)}   # middle of the patch on the texture (2026-11-25, v2)


def patch_text(out, orig, cx, cy):
    """FOREVER above the crystal and BETA below it, gold with a dark edge, on the patch itself."""
    return strap_text(out, orig, [("FOREVER", (cx - 62, cy - 58, cx + 62, cy - 38)),
                                  ("BETA", (cx - 34, cy + 38, cx + 34, cy + 58))])


def design(img, race="default"):
    out = recolor(img)
    box = cross_box(img)
    if box:                                   # the old cross goes under the patch's own purple
        H, S, V, metal, *_ = masks(img)
        pm = metal.filter(ImageFilter.MaxFilter(5)).crop((0, 0) + img.size)
        ring = ImageChops.subtract(pm.filter(ImageFilter.MaxFilter(9)), pm)
        avg = ImageStat.Stat(out.convert("RGB"), ring).mean
        cover = Image.new("RGBA", img.size, tuple(int(v) for v in avg) + (255,))
        out = Image.composite(cover, out, pm.filter(ImageFilter.GaussianBlur(1.5)))
    cx, cy = PATCH_CENTRE.get(race, PATCH_CENTRE["default"])
    put(out, glow(crystal_sprite(44, 64), 5, 0.9), cx, cy)        # bigger, in the middle of the patch
    out = patch_text(out, img, cx, cy)
    # (v3, 2026-11-25, the user: no text on the strap; it shows by the ear and backwards on the other side)
    a = img.getchannel("A"); out = out.convert("RGB"); out.putalpha(a)
    return out


FONTS = [os.path.join(KIT, "assets", "forever-beta-shirt", "font.ttf")] + FONTS


def find_texture(d):
    o = 0
    while o + 16 <= len(d):
        v = struct.unpack_from("<I", d, o + 4)[0]; kind = v & 0x7F; size = ((v >> 7) & 0x7FFFF) * 16
        if kind == 0x20:
            w, h = struct.unpack_from("<ii", d, o + 37)
            if d[o + 73:o + 77][::-1] != b"DXT3":
                raise RuntimeError("the eyepatch texture is not DXT3")
            return o + 85, w, abs(h)
        if size <= 0:
            break
        o += size
    raise RuntimeError("no texture in the eyepatch model")


def build_model(src, race="default"):
    d = bytearray(src)
    off, w, h = find_texture(src)
    n = w * h
    img = Image.frombytes("RGBA", (w, h), bytes(src[off:off + n]), "bcn", (2,))
    new = design(img, race)
    enc = fbs.dxt3_encode(new)
    if len(enc) != n:
        raise RuntimeError("texture encoder size mismatch (%d of %d bytes)" % (len(enc), n))
    fbs.check_encoding(enc, new)
    d[off:off + n] = enc
    return bytes(d), new


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


def build_record(template):
    rec = bytearray(template)
    if struct.unpack_from("<I", rec, 0)[0] != TEMPLATE_ID or fbs.strings(rec)[0] != "Eyepatch":
        raise RuntimeError("the Eyepatch record is not where expected")
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


def record(data, item_id, first):
    i = item_id - first
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
        return fbs.strings(record(fbs.read(fbs.gpath(g, ITEM_FILE)), ITEM_ID, ITEM_FIRST))[0] == ITEM["name"]
    except (ValueError, struct.error):
        return False


def _apply_look(g, st, rebuild, log):
    done = []
    new_files = model_files(g)
    for race in RACES:
        sp, np_ = fbs.gpath(g, SRC_FILES[race]), fbs.gpath(g, new_files[race])
        if rebuild or fbs.sha(fbs.read(np_)) != st.get("models", {}).get(race):
            src = fbs.read(sp)
            keep_original(g, new_files[race])
            data, _ = build_model(src, race)
            fbs.write(np_, data)
            st.setdefault("models", {})[race] = fbs.sha(data); st.setdefault("eyepatch", {})[race] = fbs.sha(src)
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
        cur = record(data, ITEM_ID, ITEM_FIRST)
        if fbs.strings(cur)[0] not in (".", ITEM["name"]):
            raise RuntimeError("item slot %d is used by '%s'" % (ITEM_ID, fbs.strings(cur)[0]))
        rec = build_record(record(fbs.read(fbs.gpath(g, TEMPLATE_FILE)), TEMPLATE_ID, TEMPLATE_FIRST))
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
        return "Forever Patch: item %s; its look was skipped (%s)." % ("updated" if "item" in done else "in place", problem)
    if not done:
        return None
    return "Forever Patch: game files updated (%s)." % ", ".join(done)


def status(g):
    st = load_state(); out = []
    for race, p in model_files(g).items():
        cur = fbs.sha(fbs.read(fbs.gpath(g, p)))
        out.append("%-9s model %-14s %s" % (race, p, "ours" if cur == st.get("models", {}).get(race) else "NOT ours"))
    out.append("item %d in %s: %s" % (ITEM_ID, ITEM_FILE, "ours" if item_ok(g) else "missing"))
    return out


def restore(g):
    """Puts back the model files. The item file is shared with the shirt, so only our record is blanked."""
    out = []
    for rel in model_files(g).values():
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
    """Puts the item's rows (modules/custom/sql/forever_patch.sql) into the running database now, like dbtool would."""
    with open(os.path.join(KIT, "config.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    sql_path = os.path.join(cfg["server_dir"], "modules", "custom", "sql", "forever_patch.sql")
    with open(sql_path, encoding="utf-8") as f:
        body = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("--"))
    import mariadb
    conn = mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])
    cur = conn.cursor()
    for stmt in [x.strip() for x in body.split(";") if x.strip()]:
        cur.execute(stmt)
    conn.commit()
    cur.execute("SELECT b.name, e.MId, u.maxCharges FROM item_basic b JOIN item_equipment e ON e.itemId = b.itemid "
                "JOIN item_usable u ON u.itemid = b.itemid WHERE b.itemid = ?", (ITEM_ID,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError("the rows are not in the database after writing")
    return "Database: %s, model %d, %d charges." % row


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
        print((apply(g, force=a.force) or "Forever Patch: already in place.") if a.cmd == "apply" else ("\n".join(restore(g)) or "nothing to restore"))
        try:
            import launcher_setup
            launcher_setup.record_era_state(KIT, g)
        except Exception as problem:
            print("(could not record the era files' state: %s)" % problem)
    else:
        out = os.path.join(KIT, "logs", "forever-patch"); os.makedirs(out, exist_ok=True)
        for race, p in SRC_FILES.items():
            _, img = build_model(fbs.read(fbs.gpath(g, p)), race)
            img.save(os.path.join(out, race + ".png")); print("preview", race)


if __name__ == "__main__":
    main()
