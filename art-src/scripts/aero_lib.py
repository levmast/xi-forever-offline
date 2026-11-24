"""Shared drawing for the Aero theme (aero_buttons.py, aero_banners.py): a mid-2000s Frutiger Aero desktop look.

Sky, water, grass, bubbles, glossy glass, lens light. Everything is drawn in code; the only pictures used are art from
art-src that no other part of the launcher or the website uses (see ART below). Lettering is Selawik (art-src\\fonts,
SIL Open Font License, Microsoft's open font in the style of the era). Needs Pillow + numpy."""
import math
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, '..'))
KIT = os.path.abspath(os.path.join(HERE, '..', '..'))
FONTS = os.path.join(SRC, 'fonts')
F_REG = os.path.join(FONTS, 'selawk.ttf')
F_SEMI = os.path.join(FONTS, 'selawksb.ttf')
F_BOLD = os.path.join(FONTS, 'selawkb.ttf')

# The art: none of these is used by the usual look, Vaporwave, 8-Bit, the hub banner, the hardcore cards or the website.
# name: (file, crop box as fractions, on white paper?)
ART = {
    'hume-f':      ('ff11-ca-hume-f.jpg',      (0.0, 0.0, 1.0, 1.0), True),
    'mini-mithra': ('ff11-ca-mini-mithra.jpg', (0.0, 0.0, 1.0, 1.0), True),
    'ferena':      ('ff11-ca-ferena.jpg',      (0.0, 0.0, 0.40, 1.0), True),
    'apu':         ('ff11-ca-apu-ajido.jpg',   (0.43, 0.0, 0.78, 0.66), True),
    'apu-red':     ('ff11-ca-apu-ajido.jpg',   (0.22, 0.64, 0.44, 1.0), True),
    'apu-blue':    ('ff11-ca-apu-ajido.jpg',   (0.72, 0.60, 0.96, 1.0), True),
    'aldo':        ('ff11-ca-aldo.jpg',        (0.0, 0.0, 1.0, 1.0), True),
    'hume-pres':   ('ff11-ca-hume-pres.jpg',   (0.0, 0.0, 0.64, 1.0), True),
    'behemoth':    ('ff11-behemoth.jpg',       (0.0, 0.0, 1.0, 0.58), 'holes'),
    'beach-1':     ('monster1.jpg',            (0.0, 0.0, 1.0, 1.0), False),
    'beach-2':     ('monster2.jpg',            (0.0, 0.0, 1.0, 1.0), False),
    'trion':       ('Trion.bmp',               (0.0, 0.0, 1.0, 1.0), False),
    'excenmille':  ('Excenmille.bmp',          (0.0, 0.0, 1.0, 1.0), False),
}


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def ramp(stops, t):
    """Colour along stops [(pos, (r, g, b)), ...] for an array t in 0..1 (returns float RGB)."""
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), dtype=np.float32)
    pos = [p for p, _ in stops]
    cols = [np.array(c, dtype=np.float32) for _, c in stops]
    for i in range(len(stops) - 1):
        a, b = pos[i], pos[i + 1]
        m = (t >= a) & (t <= b) if i == len(stops) - 2 else (t >= a) & (t < b)
        k = ((t - a) / max(b - a, 1e-6))[..., None]
        out = np.where(m[..., None], cols[i] * (1 - k) + cols[i + 1] * k, out)
    out = np.where((t < pos[0])[..., None], cols[0], out)
    return out


def to_img(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), 'RGB')


def font(path, size):
    return ImageFont.truetype(path, max(1, int(size)))


# ------------------------------------------------------------------ art
_CUT = {}


def _paper_mask(img, holes=False):
    """Mask of the drawing on its white paper: paper reached from the edges is cut away, white inside the figure stays
    (holes=True also cuts away large enclosed patches of paper, e.g. between a wing and a back)."""
    a = np.asarray(img.convert('RGB'), dtype=np.int16)
    whiteish = (a.min(axis=2) > 232) & ((a.max(axis=2) - a.min(axis=2)) < 22)
    m = Image.fromarray((whiteish * 255).astype(np.uint8), 'L').copy()
    w, h = m.size
    px = m.load()
    seeds = [(x, 0) for x in range(0, w, 3)] + [(x, h - 1) for x in range(0, w, 3)] + \
            [(0, y) for y in range(0, h, 3)] + [(w - 1, y) for y in range(0, h, 3)]
    for s in seeds:
        if px[s] == 255:
            ImageDraw.floodfill(m, s, 128)
    if holes:
        a2 = np.asarray(m)
        ys, xs = np.nonzero(a2[::4, ::4] == 255)
        for y, x in zip(ys * 4, xs * 4):
            if px[int(x), int(y)] != 255:
                continue
            ImageDraw.floodfill(m, (int(x), int(y)), 100)
            n = int((np.asarray(m) == 100).sum())
            mark = 128 if n > w * h * 0.002 else 60
            ImageDraw.floodfill(m, (int(x), int(y)), mark)
    bg = (np.asarray(m) == 128)
    fg = Image.fromarray(((~bg) * 255).astype(np.uint8), 'L')
    fg = fg.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    return fg


def art(name):
    """The piece of art as RGBA: drawings on white paper cut out, screenshots as they are."""
    if name not in _CUT:
        file, box, paper = ART[name]
        img = Image.open(os.path.join(SRC, file)).convert('RGB')
        w, h = img.size
        img = img.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        rgba = img.convert('RGBA')
        if paper:
            rgba.putalpha(_paper_mask(img, holes=(paper == 'holes')))
            bb = rgba.split()[3].point(lambda v: 255 if v > 20 else 0).getbbox()
            if bb:
                rgba = rgba.crop(bb)
        _CUT[name] = rgba
    return _CUT[name]


def fit_height(img, h):
    return img.resize((max(1, round(img.width * h / img.height)), max(1, int(h))), Image.LANCZOS)


def cover(img, w, h, ax=0.5, ay=0.5):
    """Scale to fill w x h and crop (ax, ay = where the crop sits)."""
    s = max(w / img.width, h / img.height)
    im = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x = int((im.width - w) * ax)
    y = int((im.height - h) * ay)
    return im.crop((x, y, x + w, y + h))


def glow_of(rgba, colour, radius, strength=1.0):
    """A soft halo the shape of rgba's alpha."""
    g = Image.new('RGBA', rgba.size, colour + (0,))
    g.putalpha(rgba.split()[3].filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * strength))))
    return g


# ------------------------------------------------------------------ shapes
def rounded_mask(size, radius, inset=0):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).rounded_rectangle([inset, inset, size[0] - 1 - inset, size[1] - 1 - inset], radius=max(0, radius - inset), fill=255)
    return m


def arr_of(mask):
    return np.asarray(mask, dtype=np.float32) / 255.0


# ------------------------------------------------------------------ backgrounds
SKY = [(0.0, (34, 120, 214)), (0.45, (84, 172, 240)), (0.78, (168, 222, 252)), (1.0, (226, 246, 255))]
AQUA = [(0.0, (120, 226, 240)), (0.35, (34, 176, 214)), (0.75, (10, 112, 168)), (1.0, (6, 70, 122))]
GRASS = [(0.0, (172, 230, 72)), (0.4, (104, 196, 44)), (1.0, (40, 128, 22))]


def sky(w, h, horizon=1.0, sun=(0.82, 0.18)):
    """A clear blue sky, lighter near the horizon, with a soft sun glow."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    arr = ramp(SKY, yy / (h * horizon))
    d = np.sqrt(((xx - sun[0] * w) / w) ** 2 + ((yy - sun[1] * h) / w) ** 2)
    arr = arr + (np.exp(-(d / 0.16) ** 2) * 120)[..., None] * np.array([1.0, 1.0, 0.92])
    return arr


def clouds(img, rng, count, area, scale=1.0, alpha=0.85):
    """Soft cumulus puffs within area=(x0, y0, x1, y1)."""
    layer = Image.new('L', img.size, 0)
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        cx = rng.uniform(area[0], area[2])
        cy = rng.uniform(area[1], area[3])
        base = rng.uniform(40, 90) * scale
        for k in range(rng.randint(5, 9)):
            r = base * rng.uniform(0.45, 1.0)
            ox = rng.uniform(-1.6, 1.6) * base
            oy = rng.uniform(-0.5, 0.2) * base
            d.ellipse([cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r * 0.85], fill=255)
    layer = layer.filter(ImageFilter.GaussianBlur(10 * scale))
    shade = layer.filter(ImageFilter.GaussianBlur(14 * scale))
    white = Image.new('RGBA', img.size, (255, 255, 255, 0))
    white.putalpha(layer.point(lambda v: int(v * alpha)))
    under = Image.new('RGBA', img.size, (150, 190, 225, 0))
    under.putalpha(ImageChops.subtract(shade, layer).point(lambda v: int(v * 0.5)))
    img.alpha_composite(under, (0, int(6 * scale)))
    img.alpha_composite(white)


def hills(img, y_frac, amp, rng, colours=GRASS, phase=None, sheen=True):
    """A rolling green hill (the kind every 2000s desktop had) whose top sits near y_frac of the height."""
    w, h = img.size
    phase = rng.uniform(0, 6.28) if phase is None else phase
    xs = np.arange(w, dtype=np.float32)
    top = h * y_frac - amp * np.sin(xs / w * math.pi * 1.15 + phase) - amp * 0.35 * np.sin(xs / w * math.pi * 3.1 + phase * 2)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    inside = smoothstep(-1.5, 1.5, yy - top[None, :])
    depth = np.clip((yy - top[None, :]) / max(1, h - top.min()), 0, 1)
    col = ramp(colours, depth)
    if sheen:   # light along the crest
        col = col + (np.exp(-((yy - top[None, :] - h * 0.02) / (h * 0.03)) ** 2) * 60)[..., None]
    rgba = np.dstack([np.clip(col, 0, 255), inside * 255]).astype(np.uint8)
    img.alpha_composite(Image.fromarray(rgba, 'RGBA'))
    return top


def bubbles(img, rng, count, area, rmin, rmax, alpha=1.0):
    """Glassy soap bubbles: a thin bright rim, a faint body, a specular dot."""
    for _ in range(count):
        r = rng.uniform(rmin, rmax)
        cx = rng.uniform(area[0], area[2])
        cy = rng.uniform(area[1], area[3])
        bubble(img, cx, cy, r, alpha)


def bubble(img, cx, cy, r, alpha=1.0, tint=(200, 245, 255)):
    s = int(r * 2 + 8)
    lay = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    d = np.sqrt((xx - s / 2) ** 2 + (yy - s / 2) ** 2) / r
    body = np.clip(1 - d, 0, 1)
    rim = np.exp(-((d - 0.94) / 0.07) ** 2)
    a = (0.10 * (d < 1) + 0.75 * rim + 0.18 * body ** 0.3 * (d < 1) * (yy > s / 2)) * alpha
    hx, hy = s / 2 - r * 0.38, s / 2 - r * 0.42
    spec = np.exp(-(((xx - hx) / (r * 0.22)) ** 2 + ((yy - hy) / (r * 0.14)) ** 2))
    a = np.clip(a + spec * 0.95 * alpha, 0, 1)
    col = np.ones((s, s, 3), dtype=np.float32) * np.array(tint, dtype=np.float32)
    col = col * (1 - spec[..., None]) + 255 * spec[..., None]
    lay = Image.fromarray(np.dstack([col, a * 255]).astype(np.uint8), 'RGBA')
    img.alpha_composite(lay, (int(cx - s / 2), int(cy - s / 2)))


def ribbons(img, rng, count, y_frac, spread, colours, alpha=0.55, thick=(0.04, 0.12)):
    """Soft glowing light ribbons sweeping across (the 'aurora' wallpaper waves of the era)."""
    w, h = img.size
    xs = np.arange(w, dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for i in range(count):
        ph = rng.uniform(0, 6.28)
        fq = rng.uniform(0.7, 1.5)
        cy = h * (y_frac + rng.uniform(-spread, spread))
        th = h * rng.uniform(*thick)
        centre = cy + h * 0.10 * np.sin(xs / w * math.pi * fq + ph)
        d = (yy - centre[None, :]) / th
        a = np.exp(-d ** 2) * (0.35 + 0.65 * np.exp(-((d - 0.6) / 0.25) ** 2))
        a = a * smoothstep(0, 0.25, xx / w) * smoothstep(0, 0.25, 1 - xx / w) * 0 + a   # full width
        col = np.ones((h, w, 3), dtype=np.float32) * np.array(colours[i % len(colours)], dtype=np.float32)
        lay = Image.fromarray(np.dstack([col, np.clip(a * alpha, 0, 1) * 255]).astype(np.uint8), 'RGBA')
        img.alpha_composite(lay)


def flare(img, x, y, r, strength=1.0):
    """Sun with a lens flare: a bright core, soft halo, a few rings along the line through the centre."""
    w, h = img.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2)
    a = np.clip(np.exp(-(d / r) ** 2) * 1.0 + np.exp(-(d / (r * 3.5)) ** 2) * 0.35, 0, 1) * strength
    # star streaks
    a = a + np.exp(-((yy - y) / (r * 0.06)) ** 2) * np.exp(-(np.abs(xx - x) / (r * 6))) * 0.5 * strength
    a = a + np.exp(-((xx - x) / (r * 0.05)) ** 2) * np.exp(-(np.abs(yy - y) / (r * 3))) * 0.3 * strength
    col = np.ones((h, w, 3), dtype=np.float32) * np.array([255, 252, 236], dtype=np.float32)
    img.alpha_composite(Image.fromarray(np.dstack([col, np.clip(a, 0, 1) * 255]).astype(np.uint8), 'RGBA'))
    cx, cy = w / 2, h / 2
    for k, (t, rr, col2) in enumerate(((0.55, 0.5, (180, 255, 210)), (0.95, 0.9, (150, 210, 255)), (1.35, 0.35, (255, 220, 160)), (1.7, 1.3, (170, 200, 255)))):
        fx, fy = x + (cx - x) * t * 2 * 0.6, y + (cy - y) * t * 2 * 0.6
        ring = Image.new('RGBA', img.size, col2 + (0,))
        m = Image.new('L', img.size, 0)
        ImageDraw.Draw(m).ellipse([fx - r * rr, fy - r * rr, fx + r * rr, fy + r * rr], fill=int(60 * strength))
        ring.putalpha(m.filter(ImageFilter.GaussianBlur(r * rr * 0.15)))
        img.alpha_composite(ring)


# ------------------------------------------------------------------ glass
def gloss(size, radius, top_alpha=0.62, cut=0.50, bottom_glow=(120, 230, 255), bottom_alpha=0.40):
    """The glossy glass highlight: a white sheen over the top half ending in a soft arc, and reflected light low down."""
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # arc: the sheen's lower edge bulges a little downward in the middle
    edge = h * cut + h * 0.06 * (1 - ((xx - w / 2) / (w / 2)) ** 2)
    sheen = (1 - smoothstep(edge - h * 0.03, edge + h * 0.01, yy)) * (top_alpha - (top_alpha - 0.12) * (yy / max(1, edge.max())))
    glow = np.exp(-(((xx - w / 2) / (w * 0.42)) ** 2 + ((yy - h * 1.02) / (h * 0.40)) ** 2)) * bottom_alpha
    white = np.dstack([np.full((h, w), 255, np.float32)] * 3)
    g = np.dstack([white, np.clip(sheen, 0, 1) * 255]).astype(np.uint8)
    lay = Image.fromarray(g, 'RGBA')
    glay = Image.new('RGBA', size, bottom_glow + (0,))
    glay.putalpha(Image.fromarray((np.clip(glow, 0, 1) * 255).astype(np.uint8), 'L'))
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    out.alpha_composite(glay)
    out.alpha_composite(lay)
    shape = rounded_mask(size, radius, inset=max(1, int(h * 0.04)))
    out.putalpha(ImageChops.multiply(out.split()[3], shape))
    return out


def outline(size, radius, outer=(10, 52, 104), inner=(255, 255, 255), outer_a=230, inner_a=170, width=1.0):
    """A dark outer line and a light inner line, the way glass buttons of the time were edged."""
    w, h = size
    lay = Image.new('RGBA', size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=outer + (outer_a,), width=max(1, int(width)))
    k = max(1, int(width))
    d.rounded_rectangle([k, k, w - 1 - k, h - 1 - k], radius=max(0, radius - k), outline=inner + (inner_a,), width=max(1, int(width)))
    return lay


def text_img(text, fnt, fill=(255, 255, 255), tracking=0):
    """Text as RGBA, tight to its ink."""
    bbox = fnt.getbbox(text)
    widths = [fnt.getlength(c) for c in text]
    w = int(sum(widths) + tracking * max(0, len(text) - 1) + fnt.size)
    hgt = int(bbox[3] + fnt.size * 0.4)
    img = Image.new('RGBA', (w, hgt), fill + (0,))
    d = ImageDraw.Draw(img)
    x = fnt.size * 0.2
    for c, cw in zip(text, widths):
        d.text((x, 0), c, font=fnt, fill=fill + (255,))
        x += cw + tracking
    bb = img.split()[3].getbbox()
    return img.crop(bb) if bb else img


def glass_text(text, fnt, fill=(255, 255, 255), shadow=(6, 44, 92), tracking=0, shadow_a=0.75, glow=(255, 255, 255), glow_a=0.0, pad=None):
    """Text with a soft drop shadow (and optional glow) as RGBA with room around it."""
    t = text_img(text, fnt, fill, tracking)
    pad = pad if pad is not None else max(3, fnt.size // 6)
    out = Image.new('RGBA', (t.width + pad * 2, t.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new('RGBA', t.size, shadow + (0,))
    sh.putalpha(t.split()[3].filter(ImageFilter.GaussianBlur(max(1, fnt.size / 22))).point(lambda v: int(v * shadow_a)))
    out.alpha_composite(sh, (pad, pad + max(1, fnt.size // 18)))
    if glow_a:
        out.alpha_composite(glow_of(t, glow, max(1, fnt.size / 8), glow_a), (pad, pad))
    out.alpha_composite(t, (pad, pad))
    return out


def shade_text(text, fnt, top=(255, 255, 255), bottom=(206, 236, 255), tracking=0):
    """Text filled with a soft vertical gradient (glossy lettering)."""
    t = text_img(text, fnt, (255, 255, 255), tracking)
    h = t.height
    grad = ramp([(0, top), (0.55, top), (1, bottom)], np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, t.width), np.float32))
    out = Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
    out.putalpha(t.split()[3])
    return out


def window(size, title, content=None, rng=None, active=True, scale=1.0):
    """A glass window of the era: a translucent frame with a sky-blue tint, title text with a glow, three caption buttons,
    and content (an RGBA or RGB picture) in the client area. Returns RGBA with a soft drop shadow round it."""
    w, h = size
    S = scale
    pad = int(28 * S)
    out = Image.new('RGBA', (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    # shadow
    sh = Image.new('L', out.size, 0)
    ImageDraw.Draw(sh).rounded_rectangle([pad - 2, pad + 6 * S, pad + w + 2, pad + h + 10 * S], radius=int(9 * S), fill=150)
    shadow = Image.new('RGBA', out.size, (4, 30, 60, 0))
    shadow.putalpha(sh.filter(ImageFilter.GaussianBlur(12 * S)))
    out.alpha_composite(shadow)
    frame_h = int(30 * S)
    border = int(8 * S)
    radius = int(8 * S)
    # frame: translucent blue glass with streaks
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = ramp([(0, (196, 228, 250)), (0.06, (128, 188, 232)), (1, (98, 160, 214))], yy / h)
    streak = (np.sin((xx * 0.9 + yy * 1.6) / (w * 0.06)) * 0.5 + 0.5) ** 6 * 26
    base = base + streak[..., None]
    a = np.full((h, w), 0.80 if active else 0.62, np.float32)
    fr = Image.fromarray(np.dstack([np.clip(base, 0, 255), a * 255]).astype(np.uint8), 'RGBA')
    fr.putalpha(ImageChops.multiply(fr.split()[3], rounded_mask((w, h), radius)))
    fr.alpha_composite(gloss((w, frame_h + border), radius, top_alpha=0.55, cut=0.55, bottom_alpha=0.0), (0, 0))
    fr.alpha_composite(outline((w, h), radius, outer=(20, 50, 80), outer_a=200, inner_a=150))
    # client area
    cx0, cy0, cx1, cy1 = border, frame_h, w - border, h - border
    cw, ch = cx1 - cx0, cy1 - cy0
    client = Image.new('RGBA', (cw, ch), (255, 255, 255, 255))
    if content is not None:
        c = cover(content.convert('RGBA'), cw, ch)
        client.alpha_composite(c)
    ImageDraw.Draw(client).rectangle([0, 0, cw - 1, ch - 1], outline=(70, 110, 150, 255))
    fr.alpha_composite(client, (cx0, cy0))
    # title
    tf = font(F_REG, 14 * S)
    tt = glass_text(title, tf, fill=(14, 30, 50), shadow=(255, 255, 255), shadow_a=0.0, glow=(255, 255, 255), glow_a=1.6, pad=int(6 * S))
    fr.alpha_composite(tt, (int(10 * S), int((frame_h - tt.height) / 2)))
    # caption buttons: minimize, maximize, close (the close one red)
    bw, bh = int(26 * S), int(18 * S)
    x = w - border - bw * 3 - int(14 * S)
    for i, kind in enumerate(('min', 'max', 'close')):
        bwk = int(bw * (1.6 if kind == 'close' else 1.0))
        top, bot = ((236, 150, 140), (196, 44, 28)) if kind == 'close' else ((226, 240, 252), (150, 186, 220))
        g = ramp([(0, top), (0.5, top), (0.52, bot), (1, bot)], (np.mgrid[0:bh, 0:bwk][0].astype(np.float32) / bh))
        bi = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), 'RGB').convert('RGBA')
        bi.putalpha(rounded_mask((bwk, bh), int(4 * S)))
        bi.alpha_composite(outline((bwk, bh), int(4 * S), outer=(40, 60, 90), inner_a=120))
        dd = ImageDraw.Draw(bi)
        cxm, cym = bwk / 2, bh / 2
        lw = max(1, int(2 * S))
        if kind == 'min':
            dd.line([cxm - 4 * S, cym + 3 * S, cxm + 4 * S, cym + 3 * S], fill=(30, 40, 60, 255), width=lw)
        elif kind == 'max':
            dd.rectangle([cxm - 4 * S, cym - 3 * S, cxm + 4 * S, cym + 4 * S], outline=(30, 40, 60, 255), width=lw)
        else:
            dd.line([cxm - 4 * S, cym - 4 * S, cxm + 4 * S, cym + 4 * S], fill=(255, 255, 255, 255), width=lw)
            dd.line([cxm - 4 * S, cym + 4 * S, cxm + 4 * S, cym - 4 * S], fill=(255, 255, 255, 255), width=lw)
        fr.alpha_composite(bi, (int(x), int((frame_h - bh) / 2 - 2 * S)))
        x += bwk + int(1 * S)
    out.alpha_composite(fr, (pad, pad))
    return out, pad
