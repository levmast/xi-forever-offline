"""Forever Beta Shirt (item 25725): its own item and look, made from the Maat Unity Shirt, which stays as it was.

What it changes in the FINAL FANTASY XI folder (originals kept once in backups\\forever-beta-shirt):
  * Look: body model 399 (unused by any item) gets the Maat Unity Shirt's model with a new texture:
    "Crystal Night" recolour (royal purple cloth, gold scrollwork, black side panels), a crystal on the chest, a
    bigger crystal on the back and FOREVER / BETA in gold on the side panels. Built from the player's own game files; no Square Enix art is stored in the kit.
  * Item: the empty armor slot 25725 in ROM\\286\\73.DAT (English armor, era pack) gets name, description, icon
    (the Maat shirt icon, recoloured) and 5 charges / 15 hours like the Chariot Band.
The server side is modules\\custom\\lua\\forever_beta_shirt.lua + modules\\custom\\sql\\forever_beta_shirt.sql.

Texture map (found with a numbered grid in game, 2026-11-21, Elvaan F): in the order the file stores it the picture is
upright on the body (collar rows first; tex.py's flipped view shows it upside down); the chest centre is the left edge (x = 0), the spine is the right edge (x = 511), and
each half of the body shows the same pixels mirrored. So anything drawn there must be left-right symmetric (text
would read backwards on one side). Tarutaru's map is assumed from the shared layout (not checked in game).

    python forever_beta_shirt.py status
    python forever_beta_shirt.py apply        (checks first; only writes what is missing; restart the game after)
    python forever_beta_shirt.py restore
    python forever_beta_shirt.py server       (puts the item's rows into the database now; needs the database running)
    python forever_beta_shirt.py preview      (logs\\forever-beta-shirt\\*.png, changes nothing)
"""
import argparse, hashlib, io, json, os, shutil, struct, sys

KIT = os.path.dirname(os.path.abspath(__file__))
GAME_GUESSES = [r"C:\Program Files (x86)\PlayOnline\SquareEnix\FINAL FANTASY XI",
                r"C:\Program Files\PlayOnline\SquareEnix\FINAL FANTASY XI",
                os.path.expanduser("~/mnt/FINAL FANTASY XI")]
VERSION = 3                       # bump when the design or encoder changes, so installs rebuild (2: own DXT3 encoder, 3: no ring, side text)
ITEM_ID, TEMPLATE_ID = 25725, 25738
SRC_MODEL, NEW_MODEL = 428, 399   # Maat Unity Shirt's body model -> our model number
ITEM_FILE, ITEM_FIRST, RS = "ROM/286/73.DAT", 23040, 0x1400
RACES = ["HumeM", "HumeF", "ElvaanM", "ElvaanF", "Tarutaru", "Mithra", "Galka"]
BACKUP = os.path.join(KIT, "backups", "forever-beta-shirt")
STATE = os.path.join(BACKUP, "state.json")

ITEM = {
    "name": "Forever Beta Shirt", "log": "Forever Beta shirt", "plural": "Forever Beta shirts",
    "desc": "DEF:1\nExperience point bonus: +75%\nMax. duration: 720 min.\nMaximum bonus: 4000",
    "flags": 0xFC40,              # as the Chariot Band: CanUse + CanEquip, NoAuction, NoSale, NoDelivery, Ex, Rare
    "targets": 1, "charges": 5, "cast": 4, "delay": 15, "recast": 54000,
}


# ------------------------------------------------------------------ game files
def game_dir(arg=None):
    for g in ([arg] if arg else []) + GAME_GUESSES:
        if g and os.path.exists(os.path.join(g, "FTABLE.DAT")):
            return g
    raise RuntimeError("FINAL FANTASY XI folder not found")


def file_table(g):
    id2p = {}
    def load(vt, ft, n):
        v = open(vt, "rb").read(); f = open(ft, "rb").read()
        for i, b in enumerate(v):
            if b == n:
                x = struct.unpack_from("<H", f, 2 * i)[0]
                id2p[i] = ("ROM" if n == 1 else "ROM%d" % n) + "/%d/%d" % (x >> 7, x & 127)
    load(os.path.join(g, "VTABLE.DAT"), os.path.join(g, "FTABLE.DAT"), 1)
    for n in range(2, 10):
        vt = os.path.join(g, "ROM%d" % n, "VTABLE%d.DAT" % n)
        if os.path.exists(vt):
            load(vt, os.path.join(g, "ROM%d" % n, "FTABLE%d.DAT" % n), n)
    return id2p


def model_files(g, model):
    t = file_table(g)
    return {race: t[70927 + r * 1536 + 1 * 256 + model] for r, race in enumerate(RACES)}   # body models 320-575


def gpath(g, rel):
    return os.path.join(g, *rel.split("/")) + ("" if rel.endswith(".DAT") else ".DAT")


def sha(b):
    return hashlib.sha256(b).hexdigest()


def read(p):
    with open(p, "rb") as f:
        return f.read()


def write(p, data):
    tmp = p + ".fbs-tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
    except PermissionError:                 # a folder that lets us change files but not create them: write in place
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        with open(p, "wb") as f:
            f.write(data)


def keep_original(g, rel):
    """Copies the game file to the backup once; returns the backup path."""
    bk = os.path.join(BACKUP, *rel.split("/")) + ("" if rel.endswith(".DAT") else ".DAT")
    if not os.path.exists(bk):
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        shutil.copy2(gpath(g, rel), bk)
    return bk


# ------------------------------------------------------------------ texture
def find_texture(d):
    o = 0
    while o + 16 <= len(d):
        v = struct.unpack_from("<I", d, o + 4)[0]; kind = v & 0x7F; size = ((v >> 7) & 0x7FFFF) * 16
        if kind == 0x20:
            w, h = struct.unpack_from("<ii", d, o + 37)
            if d[o + 73:o + 77][::-1] != b"DXT3":
                raise RuntimeError("the shirt texture is not DXT3")
            return o + 85, w, abs(h)
        if size <= 0:
            break
        o += size
    raise RuntimeError("no texture in the shirt model")


def recolor(img):
    """'Crystal Night': blue cloth -> royal purple, olive panels -> charcoal, pale-blue scrollwork -> gold.
    Skin, leather and the yellow orb keep their colours (their hues are outside these ranges). Pillow only
    (player installs have no numpy)."""
    from PIL import Image, ImageChops
    a = img.getchannel("A")
    H, S, V = img.convert("RGB").convert("HSV").split()
    r, _g, b = img.convert("RGB").split()
    m = lambda ch, lo, hi: ch.point(lambda v: 255 if lo <= v <= hi else 0)
    both = lambda *ms: ms[0] if len(ms) == 1 else ImageChops.multiply(ms[0], both(*ms[1:]))
    orn = both(m(V, 151, 255), ImageChops.subtract(b, r).point(lambda v: 255 if v > 8 else 0), m(S, 0, 109))
    blue = both(m(H, 120, 180), m(S, 35, 255), ImageChops.invert(orn))
    olive = both(m(H, 50, 85), m(S, 12, 95), m(V, 0, 149))
    const = lambda v: Image.new("L", img.size, v)
    H2 = Image.composite(const(196), H, blue)
    S2 = Image.composite(S.point(lambda v: min(255, v * 13 // 10 + 20)), S, blue)
    V2 = Image.composite(V.point(lambda v: v * 85 // 100), V, blue)
    H2 = Image.composite(const(190), H2, olive); S2 = Image.composite(const(25), S2, olive)
    V2 = Image.composite(V.point(lambda v: v * 45 // 100), V2, olive)
    H2 = Image.composite(const(30), H2, orn); S2 = Image.composite(const(150), S2, orn)
    V2 = Image.composite(V.point(lambda v: min(255, v * 105 // 100)), V2, orn)
    out = Image.merge("HSV", (H2, S2, V2)).convert("RGB")
    out.putalpha(a)
    return out


def crystal_sprite(w, h, scale=4):
    """An original faceted crystal (hexagonal bipyramid), point up, as an RGBA picture of w x h."""
    from PIL import Image, ImageDraw
    W, H = w * scale, h * scale
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    cx = W / 2; top, bot = H * 0.02, H * 0.98; ch = bot - top
    sy = top + ch * 0.30
    lo, li, ri, ro = cx - W * 0.48, cx - W * 0.17, cx + W * 0.17, cx + W * 0.48
    sh = [(lo, sy), (li, sy + ch * 0.03), (ri, sy + ch * 0.03), (ro, sy)]
    T, B = (cx, top), (cx, bot)
    for i, c in enumerate([(70, 130, 210), (185, 232, 255), (70, 130, 210)]):      # symmetric shading
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


def put(canvas, sprite, cx, cy):
    """Pastes sprite (alpha-blended) centred on (cx, cy); parts outside the canvas are cut off."""
    from PIL import Image
    x, y = int(round(cx - sprite.width / 2)), int(round(cy - sprite.height / 2))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(sprite, (x, y), sprite)
    canvas.alpha_composite(layer)


def glow(sprite, radius, strength, colour=(150, 215, 255)):
    from PIL import Image, ImageFilter
    pad = radius * 3
    big = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), colour + (0,))
    a = Image.new("L", big.size, 0); a.paste(sprite.getchannel("A"), (pad, pad))
    big.putalpha(a.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: int(min(255, v * strength))))
    big.alpha_composite(sprite, (pad, pad))
    return big


def crest(w, h):
    """Back crest: a gold ring (an ellipse, wider on the texture because the back is stretched 0.75 tall) with a crystal."""
    from PIL import Image, ImageDraw
    s = 4; W, H = w * s, h * s
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
    d.ellipse([s * 4, s * 4, W - s * 4, H - s * 4], outline=(70, 45, 10, 255), width=s * 9)
    d.ellipse([s * 6, s * 6, W - s * 6, H - s * 6], outline=(235, 190, 80, 255), width=s * 5)
    d.ellipse([s * 7, s * 7, W - s * 7, H - s * 7], outline=(255, 235, 160, 255), width=s * 1)
    for k in range(8):                                   # small studs on the ring, symmetric
        import math
        t = math.pi / 2 + k * math.pi / 4
        px, py = W / 2 + (W / 2 - s * 8.5) * math.cos(t), H / 2 + (H / 2 - s * 8.5) * math.sin(t)
        d.ellipse([px - s * 5, py - s * 5, px + s * 5, py + s * 5], fill=(255, 225, 120, 255), outline=(70, 45, 10, 255), width=s * 2)
    L = L.resize((w, h), Image.LANCZOS)
    c = crystal_sprite(int(w * 0.36), int(h * 0.80))
    L.alpha_composite(glow(c, 4, 0.6), (int((w - c.width) / 2) - 12, int((h - c.height) / 2) - 12))
    return L


TEXT = ("FOREVER", "BETA")
PANEL = (150, 330, 362, 540)      # the side panel in stored order on the 512x1024 textures (upright on the body)
FONTS = [os.path.join(KIT, "assets", "forever-beta-shirt", "font.ttf"), r"C:\Windows\Fonts\georgiab.ttf",
         r"C:\Windows\Fonts\timesbd.ttf", r"C:\Windows\Fonts\arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"]


def side_text(out, orig, h):
    """Gold text with a dark outline on the side panel; brightness follows the cloth's folds."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    font_path = next((f for f in FONTS if os.path.exists(f)), None)
    x0, y0, x1, y1 = PANEL; bw, bh = x1 - x0, y1 - y0
    pt = 80
    while True:
        font = ImageFont.truetype(font_path, pt) if font_path else ImageFont.load_default()
        boxes = [font.getbbox(t, stroke_width=4) for t in TEXT]
        ws = [b[2] - b[0] for b in boxes]; hs = [b[3] - b[1] for b in boxes]; gap = pt // 4
        if (max(ws) <= bw - 16 and sum(hs) + gap <= bh - 30) or pt <= 12 or not font_path:
            break
        pt -= 2
    fill = Image.new("L", (512, 1024), 0); edge = Image.new("L", (512, 1024), 0)
    df, de = ImageDraw.Draw(fill), ImageDraw.Draw(edge)
    y = y0 + (bh - (sum(hs) + gap)) // 2
    for t, b, tw, th in zip(TEXT, boxes, ws, hs):
        x = x0 + (bw - tw) // 2 - b[0]
        de.text((x, y - b[1]), t, font=font, fill=255, stroke_width=4, stroke_fill=255)
        df.text((x, y - b[1]), t, font=font, fill=255)
        y += th + gap
    fill = fill.filter(ImageFilter.GaussianBlur(0.5)); edge = edge.filter(ImageFilter.GaussianBlur(0.8))
    if h != 1024:                 # Tarutaru: the same rows at 0.46 height (y_taru = 2.56 + 0.46 y)
        def squash(m):
            c = Image.new("L", (512, h), 0); c.paste(m.resize((512, int(1024 * 0.46)), Image.LANCZOS), (0, 3)); return c
        fill, edge = squash(fill), squash(edge)
    lum = orig.convert("L")
    gold = Image.merge("RGB", [lum.point(lambda v: min(255, int(150 + v * 1.1))),
                               lum.point(lambda v: min(255, int(115 + v * 1.0))),
                               lum.point(lambda v: min(255, int(40 + v * 0.6)))])
    dark = Image.new("RGB", out.size, (20, 12, 4))
    rgb = out.convert("RGB")
    rgb = Image.composite(dark, rgb, edge.point(lambda v: int(v * 0.9)))
    rgb = Image.composite(gold, rgb, fill)
    out.paste(rgb.convert("RGBA"), (0, 0))


def design(img):
    """img: the texture in stored order (upright on the body: collar at the top). Returns the new picture."""
    from PIL import Image
    out = recolor(img).convert("RGBA")
    w, h = out.size
    if h == 1024:
        Y = lambda y: y; sy = 1.0
    else:   # Tarutaru: same body rows at about half height (calibrated on the side panel; not checked in game)
        Y = lambda y: int(512 - (250 + ((1024 - y) - 460) * 0.46)); sy = 0.46
    # chest: crystal centred on the chest line (x = 0; the other half is the mirror), about rows 10.5-13.5
    c = glow(crystal_sprite(70, int(200 * sy)), 5, 0.7)
    put(out, c, 0, Y(256))
    # back: the same crystal, bigger, centred on the spine (x = 511), upper back (the gold ring was taken off)
    put(out, glow(crystal_sprite(86, int(240 * sy)), 4, 0.6), w, Y(290))
    # side panels: "FOREVER / BETA" in gold. The panel is mirrored too, so it reads normally on one side only.
    side_text(out, img, h)
    a = img.getchannel("A")
    out = out.convert("RGB"); out.putalpha(a)
    return out


def dxt3_encode(img):
    """RGBA picture -> raw DXT3 blocks, written here so every machine gives the same bytes (Pillow's DDS writer
    differs between versions; on one PC it did not compress at all and the shirt came out scrambled).
    Per 4x4 block: 4-bit alpha, then colour end points = the brightest and darkest pixel, 4 colours, nearest index."""
    w, h = img.size
    px = img.convert("RGBA").tobytes()
    out = bytearray()
    pack = struct.pack
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            pts = []
            for y in range(by, by + 4):
                o = (y * w + bx) * 4
                pts += [px[o + i * 4:o + i * 4 + 4] for i in range(4)]
            alpha = 0
            for i, p in enumerate(pts):
                alpha |= (p[3] >> 4) << (4 * i)
            lum = [p[0] * 2 + p[1] * 5 + p[2] for p in pts]
            hi, lo = pts[lum.index(max(lum))], pts[lum.index(min(lum))]
            c0 = ((hi[0] >> 3) << 11) | ((hi[1] >> 2) << 5) | (hi[2] >> 3)
            c1 = ((lo[0] >> 3) << 11) | ((lo[1] >> 2) << 5) | (lo[2] >> 3)
            if c0 < c1:
                c0, c1 = c1, c0
            def rgb(c):
                r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
                return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))
            e0, e1 = rgb(c0), rgb(c1)
            pal = [e0, e1, tuple((2 * x + y) // 3 for x, y in zip(e0, e1)), tuple((x + 2 * y) // 3 for x, y in zip(e0, e1))]
            idx = 0
            if c0 != c1:
                for i, p in enumerate(pts):
                    best, bk = 1 << 30, 0
                    for k, q in enumerate(pal):
                        d = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2
                        if d < best:
                            best, bk = d, k
                    idx |= bk << (2 * i)
            out += pack("<QHHI", alpha, c0, c1, idx)
    return bytes(out)


def check_encoding(enc, img):
    """Decodes the blocks again and compares with the picture: a broken encoding is never written to the game."""
    from PIL import Image, ImageChops, ImageStat
    back = Image.frombytes("RGBA", img.size, enc, "bcn", (2,))
    diff = ImageStat.Stat(ImageChops.difference(back.convert("RGB"), img.convert("RGB"))).mean
    if max(diff) > 8:
        raise RuntimeError("the shirt texture did not encode correctly (average error %.1f); nothing was written" % max(diff))


def build_model(src):
    """Maat shirt model file -> our model file (same mesh, new texture)."""
    from PIL import Image
    d = bytearray(src)
    off, w, h = find_texture(src)
    n = w * h
    stored = Image.frombytes("RGBA", (w, h), bytes(src[off:off + n]), "bcn", (2,))
    upright = stored                                   # the stored order is upright on the body (collar first)
    new = design(upright)
    enc = dxt3_encode(new)
    if len(enc) != n:
        raise RuntimeError("texture encoder size mismatch (%d of %d bytes)" % (len(enc), n))
    check_encoding(enc, new)
    d[off:off + n] = enc
    return bytes(d), new


# ------------------------------------------------------------------ item record
def rot_dec(b):
    return bytes(((x >> 5) | (x << 3)) & 0xFF for x in b)


def rot_enc(b):
    return bytes(((x << 5) | (x >> 3)) & 0xFF for x in b)


def record(data, item_id):
    i = item_id - ITEM_FIRST
    return bytearray(rot_dec(data[i * RS:(i + 1) * RS]))


def strings(rec, base=0x30):
    count = struct.unpack_from("<I", rec, base)[0]
    if not 0 < count < 16:
        raise ValueError("bad string table")
    out = []
    for k in range(count):
        off, kind = struct.unpack_from("<II", rec, base + 4 + 8 * k)
        p = base + off
        out.append(struct.unpack_from("<I", rec, p)[0] if kind == 1 else bytes(rec[p + 0x1C:rec.index(b"\0", p + 0x1C)]).decode("latin-1"))
    return out


def icon_recolor(block):
    """Recolours the palette of a 32x32 8-bit icon block the same way as the shirt."""
    from PIL import Image
    block = bytearray(block)
    pal_at = 4 + 1 + 16 + 40
    pal = block[pal_at:pal_at + 1024]
    px = Image.new("RGBA", (256, 1))
    px.putdata([(pal[i * 4 + 2], pal[i * 4 + 1], pal[i * 4], 255) for i in range(256)])
    rc = recolor(px).convert("RGB")
    raw = rc.tobytes()
    for i, (r, g, b) in enumerate(zip(raw[0::3], raw[1::3], raw[2::3])):
        if i == 0:
            continue                                     # index 0 = transparent
        block[pal_at + i * 4:pal_at + i * 4 + 3] = bytes((b, g, r))
    return bytes(block)


def build_record(template):
    rec = bytearray(template)
    if struct.unpack_from("<I", rec, 0)[0] != TEMPLATE_ID or strings(rec)[0] != "Maat Unity Shirt":
        raise RuntimeError("the Maat Unity Shirt record is not where expected")
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
    icon = icon_recolor(rec[0x280:0x280 + 4 + size])
    icon = bytearray(icon); icon[13:21] = ("%05d   " % ITEM_ID).encode("ascii")
    rec[0x280:0x280 + len(icon)] = icon
    return bytes(rec)


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
    data = read(gpath(g, ITEM_FILE))
    try:
        return strings(record(data, ITEM_ID))[0] == ITEM["name"]
    except (ValueError, struct.error):
        return False


def _apply_look(g, st, rebuild, log):
    """The shirt's look (body model 399, all races). Returns the races written."""
    done = []
    src_files, new_files = model_files(g, SRC_MODEL), model_files(g, NEW_MODEL)
    for race in RACES:
        sp, np_ = gpath(g, src_files[race]), gpath(g, new_files[race])
        if rebuild or sha(read(np_)) != st.get("models", {}).get(race):
            src = read(sp)
            if sha(src) != st.get("maat", {}).get(race) and st.get("maat", {}).get(race):
                log("Forever Beta Shirt: the Maat shirt model for %s changed (game update?), rebuilding from it." % race)
            keep_original(g, new_files[race])
            data, _ = build_model(src)
            write(np_, data)
            st.setdefault("models", {})[race] = sha(data); st.setdefault("maat", {})[race] = sha(src)
            done.append(race)
    return done


def apply(g, log=print, force=False):
    """Writes only what is missing. Returns a message, or None when everything was already in place."""
    st = load_state(); done = []; problem = None
    rebuild = force or st.get("version") != VERSION
    # (2026-11-22, Ricc, FalconX51, PTgamerguy, Egon: the shirt arrived with no name) the item entry no longer depends on
    # the look: the look needs more of Pillow than the launcher exe of v0.1.58 carried, and a look that could not be built
    # used to stop the item entry too
    try:
        look_done = _apply_look(g, st, rebuild, log)
    except PermissionError:
        raise
    except Exception as e:                   # the item still gets its name; the look is tried again at the next PLAY
        look_done, problem = [], e
        st["version"] = None                 # (so the next PLAY retries the look)
    done += look_done
    save_state(st)                          # models are kept even if the item file is locked (game running)
    if rebuild or not item_ok(g):
        path = gpath(g, ITEM_FILE)
        keep_original(g, ITEM_FILE)
        data = bytearray(read(path))
        cur = record(data, ITEM_ID)
        if strings(cur)[0] not in (".", ITEM["name"]):
            raise RuntimeError("item slot %d is used by '%s'" % (ITEM_ID, strings(cur)[0]))
        rec = build_record(record(data, TEMPLATE_ID))
        i = ITEM_ID - ITEM_FIRST
        data[i * RS:(i + 1) * RS] = rot_enc(rec)
        try:
            write(path, bytes(data))
        except PermissionError:
            raise RuntimeError("the item file is in use: close FINAL FANTASY XI and run this again")
        if not item_ok(g):
            raise RuntimeError("read-back check of the item failed")
        done.append("item")
    if problem is None:
        st["version"] = VERSION
    save_state(st)
    if problem is not None:
        return "Forever Beta Shirt: item %s; its look was skipped (%s)." % (
            "updated" if "item" in done else "in place", problem)
    if not done:
        return None
    return "Forever Beta Shirt: game files updated (%s)." % ", ".join(done)


def status(g):
    st = load_state(); out = []
    for race, p in model_files(g, NEW_MODEL).items():
        cur = sha(read(gpath(g, p)))
        out.append("%-9s model %-14s %s" % (race, p, "ours" if cur == st.get("models", {}).get(race) else "NOT ours"))
    out.append("item %d in %s: %s" % (ITEM_ID, ITEM_FILE, "ours" if item_ok(g) else "missing"))
    return out


def restore(g):
    out = []
    rels = list(model_files(g, NEW_MODEL).values()) + [ITEM_FILE]
    for rel in rels:
        bk = os.path.join(BACKUP, *rel.split("/")) + ("" if rel.endswith(".DAT") else ".DAT")
        if os.path.exists(bk):
            shutil.copy2(bk, gpath(g, rel)); out.append("restored " + rel)
    if os.path.exists(STATE):
        os.replace(STATE, STATE + ".restored")
    return out


def server_db(log=print):
    """Puts the item's rows (modules/custom/sql/forever_beta_shirt.sql) into the running database now, like dbtool would."""
    with open(os.path.join(KIT, "config.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    sql_path = os.path.join(cfg["server_dir"], "modules", "custom", "sql", "forever_beta_shirt.sql")
    with open(sql_path, encoding="utf-8") as f:
        body = "\n".join(l for l in f.read().splitlines() if not l.strip().startswith("--"))
    import mariadb
    conn = mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])
    cur = conn.cursor()
    for stmt in [s.strip() for s in body.split(";") if s.strip()]:
        cur.execute(stmt)
    conn.commit()
    cur.execute("SELECT b.name, e.MId, u.maxCharges, u.reuseDelay FROM item_basic b JOIN item_equipment e ON e.itemId = b.itemid "
                "JOIN item_usable u ON u.itemid = b.itemid WHERE b.itemid = ?", (ITEM_ID,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise RuntimeError("the rows are not in the database after writing")
    return "Database: %s, model %d, %d charges, %d h between uses." % (row[0], row[1], row[2], row[3] // 3600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "apply", "restore", "preview", "server"])
    ap.add_argument("--game"); ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    g = game_dir(a.game) if a.cmd != "server" else None
    if a.cmd == "status":
        print("\n".join(status(g)))
    elif a.cmd in ("apply", "restore"):
        if a.cmd == "apply":
            print(apply(g, force=a.force) or "Forever Beta Shirt: already in place.")
        else:
            print("\n".join(restore(g)) or "nothing to restore")
        try:                    # the next PLAY must not take this change for a game update (launcher_setup.check_era_dats)
            sys.path.insert(0, KIT)
            import launcher_setup
            launcher_setup.record_era_state(KIT, g)
        except Exception as problem:
            print("(could not record the era files' state: %s)" % problem)
    elif a.cmd == "server":
        print(server_db())
    else:
        out = os.path.join(KIT, "logs", "forever-beta-shirt"); os.makedirs(out, exist_ok=True)
        for race, p in model_files(g, SRC_MODEL).items():
            _, img = build_model(read(gpath(g, p)))
            img.save(os.path.join(out, race + ".png")); print("preview", race)


if __name__ == "__main__":
    main()
