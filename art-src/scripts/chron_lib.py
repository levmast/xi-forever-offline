"""Shared drawing for the Chronicle theme (chron_buttons.py, chron_banners.py): the launcher as an old illustrated
chronicle of Vana'diel. Tooled leather and gold-leaf frames, aged vellum, the official pencil sketches (sepia line art
from art-src\\newart) laid into the vellum like plates in a bestiary, illuminated drop capitals.

Lettering: Cinzel and Cinzel Decorative (Natanael Gama) and IM FELL English (Igino Marini), all SIL OFL 1.1,
in art-src\\fonts. Only used inside the pictures. Needs Pillow + numpy."""
import math
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get('ART_SRC', os.path.abspath(os.path.join(HERE, '..')))
KIT = os.path.abspath(os.path.join(SRC, '..'))
NEW = os.path.join(SRC, 'newart')
FONTS = os.path.join(SRC, 'fonts')
F_BOLD = os.path.join(FONTS, 'Cinzel-Bold.ttf')
F_BLACK = os.path.join(FONTS, 'Cinzel-Black.ttf')
F_REG = os.path.join(FONTS, 'Cinzel-Regular.ttf')
F_DECO = os.path.join(FONTS, 'CinzelDecorative-Bold.ttf')
F_DECO_B = os.path.join(FONTS, 'CinzelDecorative-Black.ttf')
F_FELL = os.path.join(FONTS, 'IMFeENrm28P.ttf')
F_FELL_I = os.path.join(FONTS, 'IMFeENit28P.ttf')

# palette
VELLUM = (236, 218, 172)
VELLUM_DARK = (196, 160, 104)
INK = (58, 34, 18)
SEPIA = (92, 56, 28)
CRIMSON = (150, 34, 28)
LEATHER = (58, 30, 20)
LEATHER_DARK = (28, 14, 9)
GOLD = (214, 166, 72)
GOLD_LIT = (250, 222, 140)
GOLD_DEEP = (126, 88, 30)

# The sketches: name -> file in newart (all pencil / sepia line art on white)
SKETCH = {n: 'ff11-%s-sketch.png' % n for n in (
    'bard', 'beastmaster', 'black-mage', 'blue-mage', 'cid', 'corsair', 'dark-knight', 'dragoon', 'eald-narche',
    'kam-lanaut', 'lion', 'monk', 'ninja', 'paladin', 'puppetmaster', 'ranger', 'red-mage', 'samurai', 'summoner',
    'thief', 'warrior', 'white-mage')}
SKETCH.update({'hydra': 'ff11-hydra-sketch.jpg', 'yagudo': 'ff11-yagudo-sketch.jpg', 'gulool': 'ff11-gulool-ja-ja-sketch.jpg'})
# a wash colour per sketch for the hover (the plate is "painted in")
WASH = {
    'warrior': (176, 60, 40), 'paladin': (90, 120, 170), 'dark-knight': (70, 50, 90), 'red-mage': (180, 40, 40),
    'white-mage': (200, 190, 160), 'black-mage': (60, 70, 120), 'monk': (190, 120, 50), 'thief': (60, 110, 160),
    'bard': (90, 140, 70), 'ranger': (80, 120, 60), 'samurai': (150, 50, 50), 'ninja': (60, 60, 90),
    'dragoon': (70, 90, 150), 'summoner': (110, 80, 160), 'beastmaster': (150, 110, 60), 'blue-mage': (50, 110, 170),
    'corsair': (170, 60, 50), 'puppetmaster': (150, 70, 120), 'cid': (140, 100, 60), 'hydra': (90, 70, 110),
    'yagudo': (110, 120, 70), 'gulool': (120, 70, 60), 'lion': (180, 100, 60), 'kam-lanaut': (200, 170, 90),
    'eald-narche': (120, 110, 160),
}
_CACHE = {}


def font(path, size):
    return ImageFont.truetype(path, max(4, int(size)))


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


# ------------------------------------------------------------------ the sketches
def sketch(name):
    """The sketch as an 'ink' layer: L image, 0 = paper, 255 = darkest line, cropped to the drawing."""
    if name not in _CACHE:
        im = Image.open(os.path.join(NEW, SKETCH[name])).convert('L')
        a = 255 - np.asarray(im, dtype=np.float32)
        a = np.clip((a - 12) * 1.25, 0, 255)                          # paper to clean 0, lines a touch darker
        ink = Image.fromarray(a.astype(np.uint8), 'L')
        # crop to the main mass of the drawing (ignores stray guide lines and notes): where the lines are dense
        k = max(3, int(min(ink.size) * 0.03))
        dens = np.asarray(ink.filter(ImageFilter.BoxBlur(k)), dtype=np.float32)
        rows = np.nonzero(dens.max(axis=1) > dens.max() * 0.22)[0]
        cols = np.nonzero(dens.max(axis=0) > dens.max() * 0.22)[0]
        if len(rows) and len(cols):
            pad = k
            bb = (max(0, cols[0] - pad), max(0, rows[0] - pad), min(ink.width, cols[-1] + pad), min(ink.height, rows[-1] + pad))
        else:
            bb = ink.point(lambda v: 255 if v > 40 else 0).getbbox()
        _CACHE[name] = ink.crop(bb) if bb else ink
    return _CACHE[name]


def ink_layer(ink, colour=SEPIA, strength=1.0):
    """An RGBA layer of the line art in sepia ink."""
    lay = Image.new('RGBA', ink.size, colour + (0,))
    lay.putalpha(ink.point(lambda v: int(min(255, v * strength))))
    return lay


def wash_layer(ink, colour, alpha=0.55, seed=1):
    """Watercolour wash under the drawing: the drawing's area dilated and blurred, uneven like a brush."""
    w, h = ink.size
    k = max(3, int(min(w, h) * 0.035) | 1)
    area = ink.point(lambda v: 255 if v > 30 else 0).filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MaxFilter(k))
    area = area.filter(ImageFilter.GaussianBlur(k * 0.9))
    rng = np.random.default_rng(seed)
    blot = rng.random((max(2, h // 24), max(2, w // 24))).astype(np.float32)
    blot = Image.fromarray((blot * 255).astype(np.uint8), 'L').resize((w, h), Image.BICUBIC).filter(ImageFilter.GaussianBlur(k))
    a = np.asarray(area, dtype=np.float32) / 255 * (0.55 + 0.45 * np.asarray(blot, dtype=np.float32) / 255)
    lay = Image.new('RGBA', (w, h), colour + (0,))
    lay.putalpha(Image.fromarray((a * 255 * alpha).astype(np.uint8), 'L'))
    return lay


def fit_h(img, h):
    return img.resize((max(1, round(img.width * h / img.height)), max(1, int(h))), Image.LANCZOS)


def fit_w(img, w):
    return img.resize((max(1, int(w)), max(1, round(img.height * w / img.width))), Image.LANCZOS)


def cover(img, w, h, ax=0.5, ay=0.5):
    s = max(w / img.width, h / img.height)
    r = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x = int((r.width - w) * ax)
    y = int((r.height - h) * ay)
    return r.crop((x, y, x + w, y + h))


def paper_cut(img, thr=232):
    """Colour art on white paper: the white reached from the edges made transparent."""
    rgb = img.convert('RGB')
    a = np.asarray(rgb, dtype=np.int16)
    white = (a.min(axis=2) > thr) & ((a.max(axis=2) - a.min(axis=2)) < 24)
    m = Image.fromarray((white * 255).astype(np.uint8), 'L').copy()   # a copy: newer Pillow may share the array's read-only memory
    w, h = m.size
    px = m.load()
    for s in [(x, 0) for x in range(0, w, 3)] + [(x, h - 1) for x in range(0, w, 3)] + \
             [(0, y) for y in range(0, h, 3)] + [(w - 1, y) for y in range(0, h, 3)]:
        if px[s] == 255:
            ImageDraw.floodfill(m, s, 128)
    fg = Image.fromarray(((np.asarray(m) != 128) * 255).astype(np.uint8), 'L')
    fg = fg.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = rgb.convert('RGBA')
    out.putalpha(fg)
    bb = fg.point(lambda v: 255 if v > 20 else 0).getbbox()
    return out.crop(bb) if bb else out


def colour_art(name):
    key = 'c:' + name
    if key not in _CACHE:
        _CACHE[key] = paper_cut(Image.open(os.path.join(NEW, name)))
    return _CACHE[key]


# ------------------------------------------------------------------ surfaces
def noise(w, h, scale, seed):
    rng = np.random.default_rng(seed)
    sw, sh = max(2, int(w / scale)), max(2, int(h / scale))
    n = rng.random((sh, sw)).astype(np.float32)
    return np.asarray(Image.fromarray((n * 255).astype(np.uint8), 'L').resize((w, h), Image.BICUBIC), dtype=np.float32) / 255


def vellum(w, h, seed=3, warm=0.0, burn=1.0):
    """Aged vellum: mottled, fibres, darker and browner towards the edges, a stain or two."""
    base = np.array(VELLUM, dtype=np.float32)
    dark = np.array(VELLUM_DARK, dtype=np.float32)
    m = noise(w, h, max(8, min(w, h) / 3), seed) * 0.55 + noise(w, h, max(4, min(w, h) / 12), seed + 1) * 0.3 + \
        noise(w, h, 2.5, seed + 2) * 0.15
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ex = np.minimum(xx, w - 1 - xx) / max(1, w)
    ey = np.minimum(yy, h - 1 - yy) / max(1, h)
    edge = 1 - smoothstep(0.0, 0.22, np.minimum(ex * (w / max(w, h)) * 2.2, ey * (h / max(w, h)) * 2.2) * 2.0)
    t = np.clip(m * 0.45 + edge * 0.75 * burn, 0, 1)[..., None]
    arr = base * (1 - t) + dark * t
    arr = arr * (1 - 0.18 * (edge[..., None] ** 2) * burn)
    if warm:
        arr = arr + np.array([22, 12, -6], dtype=np.float32) * warm
    rng = random.Random(seed)
    img = to_img(arr).convert('RGBA')
    st = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(st)
    for _ in range(2):
        r = rng.uniform(0.08, 0.2) * min(w, h) * 1.5
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        d.ellipse((cx - r, cy - r * 0.7, cx + r, cy + r * 0.7), outline=26, width=max(1, int(r * 0.08)))
        d.ellipse((cx - r * 0.9, cy - r * 0.6, cx + r * 0.9, cy + r * 0.6), fill=10)
    st = st.filter(ImageFilter.GaussianBlur(max(1, min(w, h) * 0.01)))
    lay = Image.new('RGBA', (w, h), (120, 80, 30, 0))
    lay.putalpha(st)
    img.alpha_composite(lay)
    return img


def leather(w, h, seed=5, lit=0.0, tone=LEATHER):
    """Dark tooled leather: grain, a soft sheen across the middle."""
    g = noise(w, h, 2.0, seed) * 0.5 + noise(w, h, max(3, min(w, h) / 10), seed + 1) * 0.5
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32) / max(1, h)
    sheen = np.exp(-((yy - 0.35) / 0.35) ** 2) * (0.25 + lit * 0.25)
    c = np.array(tone, dtype=np.float32)
    arr = c[None, None, :] * (0.72 + g[..., None] * 0.45 + sheen[..., None])
    return to_img(arr).convert('RGBA')


def gold_fill(w, h, lit=False, seed=9):
    """Gold leaf: a vertical metallic ramp with a little crackle."""
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32) / max(1, h - 1)
    stops = [(0, GOLD_LIT if lit else (238, 200, 110)), (0.38, (255, 236, 170) if lit else GOLD),
             (0.62, GOLD_DEEP), (1, (200, 150, 60) if lit else (170, 124, 48))]
    out = np.zeros((h, w, 3), dtype=np.float32)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (yy >= t0) & (yy <= t1)
        f = ((yy - t0) / max(1e-6, t1 - t0))[..., None]
        out = np.where(m[..., None], np.array(c0) * (1 - f) + np.array(c1) * f, out)
    out = out * (0.9 + noise(w, h, 1.6, seed)[..., None] * 0.2)
    return to_img(out).convert('RGBA')


def masked(fill, mask):
    out = fill.copy()
    out.putalpha(ImageChops.multiply(out.getchannel('A'), mask))
    return out


def notched_mask(size, c, inset=0):
    """A plate with its corners cut in (the inward quarter-circle notch of old book frames)."""
    w, h = size
    m = Image.new('L', size, 0)
    d = ImageDraw.Draw(m)
    d.rectangle((inset, inset, w - 1 - inset, h - 1 - inset), fill=255)
    r = c - inset * 0.6
    if r > 1:
        for cx, cy in ((inset, inset), (w - 1 - inset, inset), (inset, h - 1 - inset), (w - 1 - inset, h - 1 - inset)):
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
    return m


def ring(size, c, outer_inset, width):
    a = notched_mask(size, c, outer_inset)
    b = notched_mask(size, c, outer_inset + width)
    return ImageChops.subtract(a, b)


def gold_line(img, size, c, inset, width, lit=False):
    m = ring(size, c, inset, max(1, int(width)))
    g = gold_fill(*size, lit=lit)
    img.alpha_composite(masked(g, m))


def corner_ornaments(img, c, inset, colour, scale, lit=False):
    """Small gold fleurons in the four notches: a diamond with two curls."""
    w, h = img.size
    lay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    s = scale
    for sx, sy, cx, cy in ((1, 1, inset, inset), (-1, 1, w - 1 - inset, inset), (1, -1, inset, h - 1 - inset),
                           (-1, -1, w - 1 - inset, h - 1 - inset)):
        px, py = cx + sx * c * 0.62, cy + sy * c * 0.62
        d.polygon([(px, py - s * 1.6), (px + s * 1.6, py), (px, py + s * 1.6), (px - s * 1.6, py)], fill=colour)
        for k in (0, 1):
            ox, oy = (sx * s * 2.6, 0) if k == 0 else (0, sy * s * 2.6)
            d.arc((px + ox - s * 1.2, py + oy - s * 1.2, px + ox + s * 1.2, py + oy + s * 1.2), 0, 360, fill=colour,
                  width=max(1, int(s * 0.5)))
    if lit:
        img.alpha_composite(glow(lay, GOLD_LIT, s * 2.5, 0.9))
    img.alpha_composite(lay)


def glow(rgba, colour, radius, strength=1.0):
    a = rgba.getchannel('A').filter(ImageFilter.GaussianBlur(max(1, radius)))
    a = a.point(lambda v: int(min(255, v * strength)))
    g = Image.new('RGBA', rgba.size, colour + (0,))
    g.putalpha(a)
    return g


def shadow_of(rgba, radius, opacity=150, colour=(20, 10, 4)):
    a = rgba.getchannel('A').filter(ImageFilter.GaussianBlur(max(1, radius))).point(lambda v: int(v * opacity / 255))
    s = Image.new('RGBA', rgba.size, colour + (0,))
    s.putalpha(a)
    return s


# ------------------------------------------------------------------ lettering
def text_layer(text, fnt, fill, tracking=0, stroke=0, stroke_fill=None):
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    widths = [probe.textlength(ch, font=fnt) for ch in text]
    asc, desc = fnt.getmetrics()
    W = int(sum(widths) + tracking * max(0, len(text) - 1) + stroke * 2 + 4)
    H = int(asc + desc + stroke * 2 + 4)
    lay = Image.new('RGBA', (max(1, W), H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    x = stroke + 2
    for ch, cw in zip(text, widths):
        d.text((x, stroke + 2), ch, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
        x += cw + tracking
    bb = lay.getchannel('A').getbbox()
    return lay.crop(bb) if bb else lay


def gilt_text(text, fnt, lit=False, tracking=0, emboss=True):
    """Gold-leaf lettering with a dark tooled edge (for leather)."""
    mask = text_layer(text, fnt, (255, 255, 255, 255), tracking).getchannel('A')
    pad = max(2, int(fnt.size * 0.08))
    W, H = mask.width + pad * 2, mask.height + pad * 2
    m = Image.new('L', (W, H), 0)
    m.paste(mask, (pad, pad))
    g = masked(gold_fill(W, H, lit=lit, seed=len(text)), m)
    edge = Image.new('RGBA', (W, H), LEATHER_DARK + (0,))
    edge.putalpha(m.filter(ImageFilter.MaxFilter(3)))
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.alpha_composite(edge)
    if emboss:
        hi = Image.new('RGBA', (W, H), (255, 246, 210, 0))
        hi.putalpha(m.point(lambda v: v // 3))
        out.alpha_composite(hi, (0, -1))
    out.alpha_composite(g)
    return out


def ink_text(text, fnt, fill=INK, tracking=0, impress=True):
    """Ink lettering on vellum: pressed slightly into the page."""
    t = text_layer(text, fnt, fill + (255,), tracking)
    if not impress:
        return t
    W, H = t.width + 4, t.height + 4
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    hi = Image.new('RGBA', t.size, (255, 248, 222, 0))
    hi.putalpha(t.getchannel('A').point(lambda v: int(v * 0.55)))
    out.alpha_composite(hi, (2, 3))
    out.alpha_composite(t, (2, 2))
    return out


def illuminated(text, size, lit=False, colour=INK, cap_colour=CRIMSON, tracking=None, plain_font=F_BOLD):
    """The label: an illuminated first capital (red with a gold rim) and the rest in Cinzel ink."""
    tracking = size * 0.04 if tracking is None else tracking
    cap_f = font(F_DECO_B, size * 1.32)
    rest_f = font(plain_font, size)
    first, rest = text[0], text[1:]
    cap = text_layer(first, cap_f, cap_colour + (255,), 0, stroke=max(1, int(size * 0.05)),
                     stroke_fill=(GOLD_LIT if lit else GOLD) + (255,))
    body = ink_text(rest.strip(), rest_f, colour, tracking) if rest.strip() else None
    gap = int(size * (0.34 if rest.startswith(' ') else 0.06))
    W = cap.width + (gap + body.width if body else 0)
    H = max(cap.height, body.height if body else 0) + 2
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if lit:
        out.alpha_composite(glow(cap, GOLD_LIT, size * 0.12, 1.0), (0, H - cap.height))
    out.alpha_composite(cap, (0, H - cap.height))
    if body:
        # baseline: the body's bottom sits on the capital's bottom
        out.alpha_composite(body, (cap.width + gap, H - body.height - int(size * 0.02)))
    return out


def fit(layer_fn, box_w, box_h, start):
    size = start
    for _ in range(50):
        t = layer_fn(size)
        if t.width <= box_w and t.height <= box_h:
            return t
        size *= 0.94
    return t


def rule(img, x0, x1, y, colour, width, diamond=True):
    d = ImageDraw.Draw(img)
    d.line([x0, y, x1, y], fill=colour, width=max(1, int(width)))
    if diamond:
        cx = (x0 + x1) / 2
        s = width * 3
        d.polygon([(cx, y - s), (cx + s, y), (cx, y + s), (cx - s, y)], fill=colour)
