"""Shared drawing for the Windurst theme (wind_buttons.py, wind_banners.py): the launcher as a storybook of the Federation
of Windurst. Rounded frames of honey-coloured Star Tree wood with a band of green lacquer (the green of the Windurstian
flag), gold stars and sparkles, a sunny cream page with a meadow wash at its foot, and the official colour concept art
of Windurst's people laid onto the page like stickers in a picture book: Tarutaru, Mithra, Shantotto, Ajido-Marujido,
Apururu, the Cardians, the mages of the five ministries, and the beasts of Sarutabaruta.

Lettering: Cherry Swash (Natalia Kasatkina) and Fondamento (Astigmatic), both SIL OFL 1.1, in art-src\\fonts. Only used
inside the pictures. Uses chron_lib.py for the shared helpers. Needs Pillow + numpy."""
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import chron_lib as C

SRC, KIT, NEW, FONTS = C.SRC, C.KIT, C.NEW, C.FONTS
COLL = os.path.join(SRC, 'FFXI_Art_Collection_Part2')
F_SWASH = os.path.join(FONTS, 'CherrySwash-Bold.ttf')
F_HAND = os.path.join(FONTS, 'Fondamento-Regular.ttf')
font, fit_h, fit_w, cover, masked, smoothstep, noise, to_img, glow, shadow_of, text_layer, fit = (
    C.font, C.fit_h, C.fit_w, C.cover, C.masked, C.smoothstep, C.noise, C.to_img, C.glow, C.shadow_of, C.text_layer, C.fit)

# palette
HONEY = (186, 128, 64)
WOOD_DARK = (96, 58, 28)
GREEN = (52, 118, 62)
GREEN_DEEP = (24, 66, 36)
GREEN_INK = (26, 72, 38)
CREAM = (252, 244, 216)
MEADOW = (196, 222, 150)
SKY = (222, 236, 238)
GOLD = (234, 192, 84)
GOLD_LIT = (255, 230, 140)
GOLD_DEEP = (150, 106, 30)
BERRY = (150, 46, 40)                  # the frame band of buttons that stop or leave something

# The figures: key -> (file, crop box as fractions of the picture or None, how much of the figure from the top to show
# on a small button). Paths are in art-src\newart unless they start with "coll:" (art-src\FFXI_Art_Collection_Part2).
FIGS = {
    'shantotto':   ('ff11-shantotto.jpg', None, 0.42),
    'ajido':       ('ff11-ajido.jpg', None, 0.5),
    'apu':         ('ff11-ca-apu-ajido.jpg', (0.41, 0.0, 0.76, 0.62), 0.55),
    'taru':        ('ff11-ca-taru-m.jpg', (0.0, 0.0, 0.56, 1.0), 0.5),
    'taru-mage':   ('ff11-ca-tarutaru.jpg', (0.0, 0.0, 0.5, 1.0), 0.45),
    'taru-kids':   ('ff11-ca-tarutaru.jpg', (0.48, 0.15, 1.0, 1.0), 0.62),
    'taru-race':   ('ff11-tarutaru-race.jpg', (0.0, 0.0, 1.0, 0.47), 0.7),
    'mithra':      ('ff11-ca-mithra.jpg', None, 0.36),
    'mithra-girl': ('ff11-ca-mini-mithra.jpg', (0.0, 0.0, 0.68, 1.0), 0.45),
    'mithra-race': ('ff11-mithra-race.jpg', (0.0, 0.0, 1.0, 1.0), 0.45),
    'cardian':     ('ff11-cardian.jpg', (0.0, 0.0, 0.56, 1.0), 0.6),
    'mandragora':  ('ff11-mandragora.jpg', (0.3, 0.0, 0.7, 1.0), 0.7),
    'black-mage':  ('ff11-black-mage.jpg', None, 0.55),
    'white-mage':  ('ff11-white-mage.jpg', None, 0.42),
    'summoner':    ('ff11-summoner.jpg', None, 0.75),
    'scholar':     ('ff11-scholar-concept.jpg', (0.0, 0.0, 0.5, 1.0), 0.42),
    'old-mage':    ('ff11-ca-black-mage.jpg', None, 0.42),
    'yagudo':      ('ff11-yagudo.jpg', (0.3, 0.0, 1.0, 1.0), 0.55),
    'dhalmel':     ('ff11-dhalmel.jpg', (0.3, 0.0, 0.76, 1.0), 0.5),
    'bust-m1':     ('ff11-tarum1.jpg', None, 1.0),
    'bust-m4':     ('ff11-tarum4.jpg', None, 1.0),
    'bust-m8':     ('ff11-tarum8.jpg', None, 1.0),
    'bust-f3':     ('ff11-taruf3.jpg', None, 1.0),
    'bust-f5':     ('ff11-taruf5.jpg', None, 1.0),
    'bust-m0':     ('ff11-tarum0.jpg', None, 1.0),
    'bust-f0':     ('ff11-taruf0.jpg', None, 1.0),
    'mithra-head': ('ff11-mithra0.jpg', None, 1.0),
}
# a soft colour per figure for the hover glow behind it
GLOW = {'shantotto': (250, 214, 120), 'ajido': (255, 170, 90), 'black-mage': (150, 160, 255), 'white-mage': (255, 255, 220),
        'summoner': (200, 170, 255), 'yagudo': (200, 120, 255), 'cardian': (255, 200, 120), 'mandragora': (200, 255, 150)}
_CACHE = {}


def path_of(name):
    return os.path.join(COLL, name[5:]) if name.startswith('coll:') else os.path.join(NEW, name)


def figure(key):
    """The figure as an RGBA cut-out (the white paper around it made transparent), cropped to the drawing."""
    if key not in _CACHE:
        f, box, _ = FIGS[key]
        im = Image.open(path_of(f)).convert('RGB')
        if box:
            w, h = im.size
            im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        _CACHE[key] = C.paper_cut(im)
    return _CACHE[key]


def picture(name):
    key = 'p:' + name
    if key not in _CACHE:
        _CACHE[key] = Image.open(path_of(name)).convert('RGB')
    return _CACHE[key]


def sticker(fig, edge, colour=(255, 252, 238)):
    """A cut-out with a soft white edge round it, as if cut from a picture book and laid on the page."""
    pad = int(edge * 2) + 2
    out = Image.new('RGBA', (fig.width + pad * 2, fig.height + pad * 2), (0, 0, 0, 0))
    a = Image.new('L', out.size, 0)
    a.paste(fig.getchannel('A'), (pad, pad))
    rim = a.filter(ImageFilter.MaxFilter(max(3, int(edge) | 1))).filter(ImageFilter.GaussianBlur(max(1, edge * 0.35)))
    lay = Image.new('RGBA', out.size, colour + (0,))
    lay.putalpha(rim)
    out.alpha_composite(shadow_of(lay, edge * 0.8, 90, (40, 50, 20)), (int(edge * 0.4), int(edge * 0.6)))
    out.alpha_composite(lay)
    out.alpha_composite(fig, (pad, pad))
    return out


# ------------------------------------------------------------------ surfaces
def streak_noise(w, h, sx, sy, seed):
    """Noise stretched along x (wood grain)."""
    rng = np.random.default_rng(seed)
    n = rng.random((max(2, int(h / sy)), max(2, int(w / sx)))).astype(np.float32)
    return np.asarray(Image.fromarray((n * 255).astype(np.uint8), 'L').resize((w, h), Image.BICUBIC), dtype=np.float32) / 255


def wood(w, h, seed=5, lit=0.0, tone=HONEY):
    """Honey-coloured Star Tree wood: long grain, darker rings, a soft sheen."""
    n = streak_noise(w, h, max(4, w / 6), max(1.5, h / 40), seed)
    m = streak_noise(w, h, max(6, w / 3), max(3, h / 8), seed + 1)
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32) / max(1, h)
    rings = 0.5 + 0.5 * np.sin((yy * 9 + m * 3.2) * np.pi * 2)
    grain = n * 0.55 + rings * 0.45
    sheen = np.exp(-((yy - 0.3) / 0.3) ** 2) * (0.18 + lit * 0.2)
    c = np.array(tone, dtype=np.float32)
    d = np.array(WOOD_DARK, dtype=np.float32) * (np.array(tone, dtype=np.float32) / np.array(HONEY, dtype=np.float32))
    t = np.clip(grain * 0.75, 0, 1)[..., None]
    arr = c * (1 - t) + d * t
    arr = arr * (0.92 + sheen[..., None]) + noise(w, h, 1.5, seed + 2)[..., None] * 10
    return to_img(arr).convert('RGBA')


def lacquer(w, h, colour=GREEN, lit=0.0, seed=3):
    """Green lacquer: a smooth vertical ramp with a bright lip on top."""
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32) / max(1, h - 1)
    c = np.array(colour, dtype=np.float32)
    shade = 1.28 - yy * 0.55 + np.exp(-((yy - 0.18) / 0.12) ** 2) * (0.25 + lit * 0.2)
    arr = c * shade[..., None] * (0.97 + noise(w, h, 3, seed)[..., None] * 0.06)
    return to_img(arr).convert('RGBA')


def gold_fill(w, h, lit=False, seed=9):
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32) / max(1, h - 1)
    stops = [(0, GOLD_LIT if lit else (250, 220, 130)), (0.4, (255, 240, 170) if lit else GOLD),
             (0.65, GOLD_DEEP), (1, (220, 170, 70) if lit else (190, 140, 50))]
    out = np.zeros((h, w, 3), dtype=np.float32)
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        m = (yy >= t0) & (yy <= t1)
        f = ((yy - t0) / max(1e-6, t1 - t0))[..., None]
        out = np.where(m[..., None], np.array(c0) * (1 - f) + np.array(c1) * f, out)
    out = out * (0.93 + noise(w, h, 1.6, seed)[..., None] * 0.14)
    return to_img(out).convert('RGBA')


def page(w, h, seed=3, warm=0.0, meadow=1.0):
    """The storybook page: sunny cream, a meadow-green wash rising from the foot, a faint paper tooth."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    y = yy / max(1, h - 1)
    base = np.array(CREAM, dtype=np.float32)
    top = np.array(SKY, dtype=np.float32)
    grass = np.array(MEADOW, dtype=np.float32)
    wob = noise(w, h, max(6, w / 10), seed) * 0.18
    g = smoothstep(0.5, 1.05, y + wob)[..., None] * 0.75 * meadow
    s = (1 - smoothstep(0.0, 0.45, y + wob * 0.5))[..., None] * 0.35
    arr = base * (1 - g - s) + grass * g + top * s
    arr = arr * (0.96 + noise(w, h, 2.0, seed + 1)[..., None] * 0.06)
    if warm:
        cx, cy = w * 0.28, h * 0.3
        glowm = np.exp(-(((xx - cx) / (w * 0.6)) ** 2 + ((yy - cy) / (h * 0.9)) ** 2))[..., None]
        arr = arr + np.array([30, 24, -4], dtype=np.float32) * glowm * warm
    return to_img(arr).convert('RGBA')


def rounded(size, r, inset=0):
    w, h = size
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).rounded_rectangle((inset, inset, w - 1 - inset, h - 1 - inset), radius=max(0, r - inset * 0.7), fill=255)
    return m


def ring(size, r, inset, width):
    return ImageChops.subtract(rounded(size, r, inset), rounded(size, r, inset + max(1, int(width))))


def star_points(cx, cy, r, n=4, inner=0.38, rot=-90):
    pts = []
    for i in range(n * 2):
        a = np.radians(rot + i * 180 / n)
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * np.cos(a), cy + rr * np.sin(a)))
    return pts


def star(draw, cx, cy, r, fill, n=4, inner=0.38, rot=-90):
    draw.polygon(star_points(cx, cy, r, n, inner, rot), fill=fill)


def gold_star_layer(size, places, lit=False):
    """Gold-leaf stars at the given (x, y, radius, points) places, as one RGBA layer with a dark edge."""
    m = Image.new('L', size, 0)
    d = ImageDraw.Draw(m)
    for x, y, r, n in places:
        star(d, x, y, r, 255, n, 0.42 if n == 5 else 0.34)
    g = masked(gold_fill(*size, lit=lit), m)
    edge = Image.new('RGBA', size, (60, 36, 12, 0))
    edge.putalpha(m.filter(ImageFilter.MaxFilter(3)))
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    if lit:
        out.alpha_composite(glow(g, GOLD_LIT, max(2, max(p[2] for p in places) * 0.9), 1.4))
    out.alpha_composite(edge)
    out.alpha_composite(g)
    return out


def sparkles(size, count, seed, colour=(255, 246, 200), rmin=2, rmax=6, mask=None, alpha=200):
    """Little four-pointed twinkles scattered over an area."""
    w, h = size
    lay = Image.new('RGBA', size, (0, 0, 0, 0))
    m = Image.new('L', size, 0)
    d = ImageDraw.Draw(m)
    rng = random.Random(seed)
    for _ in range(count):
        x, y, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(rmin, rmax)
        star(d, x, y, r, int(alpha * rng.uniform(0.5, 1.0)), 4, 0.22)
        d.ellipse((x - r * 0.25, y - r * 0.25, x + r * 0.25, y + r * 0.25), fill=alpha)
    if mask is not None:
        m = ImageChops.multiply(m, mask)
    lay.putalpha(m)
    g = Image.new('RGBA', size, colour + (0,))
    g.putalpha(m.filter(ImageFilter.GaussianBlur(max(1, rmax * 0.4))))
    out = Image.new('RGBA', size, colour + (0,))
    out.alpha_composite(g)
    lay2 = Image.new('RGBA', size, colour + (0,))
    lay2.putalpha(m)
    out.alpha_composite(lay2)
    return out


# ------------------------------------------------------------------ lettering
def storybook(text, size, lit=False, colour=GREEN_INK, cap_colour=GOLD, tracking=None, fnt=None):
    """The label: Cherry Swash in deep green, pressed into the page, the first letter gold-leaf with a green edge."""
    tracking = size * 0.03 if tracking is None else tracking
    f = font(fnt or F_SWASH, size)
    first, rest = text[0], text[1:]
    capf = font(fnt or F_SWASH, size * 1.18)
    cm = text_layer(first, capf, (255, 255, 255, 255)).getchannel('A')
    pad = max(2, int(size * 0.08))
    cap = Image.new('RGBA', (cm.width + pad * 2, cm.height + pad * 2), (0, 0, 0, 0))
    mm = Image.new('L', cap.size, 0)
    mm.paste(cm, (pad, pad))
    edge = Image.new('RGBA', cap.size, GREEN_DEEP + (0,))
    edge.putalpha(mm.filter(ImageFilter.MaxFilter(max(3, int(size * 0.09) | 1))))
    if lit:
        cap.alpha_composite(glow(edge, GOLD_LIT, size * 0.15, 1.2))
    cap.alpha_composite(edge)
    cap.alpha_composite(masked(gold_fill(*cap.size, lit=lit, seed=len(text)), mm))
    body = None
    if rest.strip():
        t = text_layer(rest.strip(), f, colour + (255,), tracking)
        body = Image.new('RGBA', (t.width + 3, t.height + 3), (0, 0, 0, 0))
        hi = Image.new('RGBA', t.size, (255, 255, 240, 0))
        hi.putalpha(t.getchannel('A').point(lambda v: int(v * 0.7)))
        body.alpha_composite(hi, (1, 2))
        body.alpha_composite(t, (1, 1))
    gap = int(size * (0.3 if rest.startswith(' ') else 0.03))
    W = cap.width + (gap + body.width if body else 0)
    H = max(cap.height, body.height if body else 0) + 2
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    out.alpha_composite(cap, (0, H - cap.height))
    if body:
        out.alpha_composite(body, (cap.width + gap, H - body.height - int(size * 0.04) - pad // 2))
    return out


def gilt(text, fnt, lit=False, tracking=0, edge=GREEN_DEEP):
    """Gold-leaf lettering with a deep green edge (for wood and lacquer)."""
    mask = text_layer(text, fnt, (255, 255, 255, 255), tracking).getchannel('A')
    pad = max(2, int(fnt.size * 0.1))
    W, H = mask.width + pad * 2, mask.height + pad * 2
    m = Image.new('L', (W, H), 0)
    m.paste(mask, (pad, pad))
    e = Image.new('RGBA', (W, H), edge + (0,))
    e.putalpha(m.filter(ImageFilter.MaxFilter(max(3, int(fnt.size * 0.07) | 1))))
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if lit:
        out.alpha_composite(glow(e, GOLD_LIT, fnt.size * 0.12, 1.0))
    out.alpha_composite(e)
    out.alpha_composite(masked(gold_fill(W, H, lit=lit, seed=len(text)), m))
    return out


def ink(text, fnt, fill=GREEN_INK, tracking=0):
    t = text_layer(text, fnt, fill + (255,), tracking)
    out = Image.new('RGBA', (t.width + 3, t.height + 3), (0, 0, 0, 0))
    hi = Image.new('RGBA', t.size, (255, 255, 240, 0))
    hi.putalpha(t.getchannel('A').point(lambda v: int(v * 0.6)))
    out.alpha_composite(hi, (1, 2))
    out.alpha_composite(t, (1, 1))
    return out
