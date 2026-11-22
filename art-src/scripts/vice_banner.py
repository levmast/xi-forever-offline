"""The XIFO Miami-sunset banner for the launcher (assets\\press\\xifo_vice__once.jpg).
"__once" in the name makes it a one-time banner: the launcher shows it on one start only (load_once in
launcher_gui.pyw) and it never joins the rotation.

Usage:  python vice_banner.py OUTDIR      (writes xifo_vice__once.jpg and the 1840 x 736 master)

Everything but the four figures is drawn in code: sky, sun, water, skyline, palms, the XIFO
lettering and the neon sign. The figures are cut out of the job art in art-src (drawn on white
paper) and relit for the sunset. Needs Pillow + numpy and two open fonts (SIL OFL) in
art-src\\fonts:  Kanit-BlackItalic.ttf  and  Righteous-Regular.ttf  (github.com/google/fonts,
ofl/kanit and ofl/righteous). ART_SRC / XIFO_FONTS override the folders.

Design space is 1840 x 736, saved at 1400 x 560 (same 2.5 : 1 shape as the other press banners). To change who
is on it, edit LAYOUT (name, height, x, bottom, which side the sun is on, layer, options).
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ART = os.environ.get('ART_SRC', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = os.environ.get('XIFO_FONTS', os.path.join(ART, 'fonts'))
W, H = 1840, 736
HORIZON = int(H * 0.625)
SUN = (int(W * 0.5), HORIZON - 150, 262)         # x, y, radius (it sinks behind the horizon)
F_TITLE = os.path.join(FONTS, 'Kanit-BlackItalic.ttf')
F_TAG = os.path.join(FONTS, 'Righteous-Regular.ttf')


# ---------------------------------------------------------------- helpers
def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def ramp(stops, t):
    """stops: [(pos, (r,g,b)), ...]; t: array in 0..1 -> array (..., 3)."""
    t = np.asarray(t, dtype=np.float32)
    pos = np.array([s[0] for s in stops], dtype=np.float32)
    col = np.array([s[1] for s in stops], dtype=np.float32)
    out = np.zeros(t.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, pos, col[:, c])
    return out


def noise(w, h, cell_x, cell_y, rng, octaves=4):
    """Stretched value noise in 0..1."""
    acc = np.zeros((h, w), dtype=np.float32)
    amp, tot = 1.0, 0.0
    for _ in range(octaves):
        gw, gh = max(2, int(w / cell_x) + 2), max(2, int(h / cell_y) + 2)
        g = (rng.random((gh, gw)) * 255).astype(np.uint8)
        im = Image.fromarray(g, 'L').resize((w, h), Image.BICUBIC)
        acc += np.asarray(im, dtype=np.float32) / 255.0 * amp
        tot += amp
        amp *= 0.5
        cell_x *= 0.5
        cell_y *= 0.5
    return acc / tot


def to_img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')


def add(base, layer, k=1.0):
    return np.clip(base + layer * k, 0, 255)


def blur_arr(a, r):
    if a.ndim == 2:
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(r))
        return np.asarray(im, dtype=np.float32)
    return np.asarray(to_img(a).filter(ImageFilter.GaussianBlur(r)), dtype=np.float32)


# ---------------------------------------------------------------- sky
SKY = [
    (0.00, (30, 16, 78)),
    (0.20, (72, 30, 124)),
    (0.42, (150, 44, 146)),
    (0.60, (226, 66, 136)),
    (0.76, (252, 108, 112)),
    (0.90, (255, 160, 98)),
    (1.00, (255, 214, 140)),
]


def build_sky(rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    t = np.clip(yy / HORIZON, 0, 1)
    # the sky is warmer and brighter around the sun
    sx, sy, sr = SUN
    d = np.hypot((xx - sx) / 1.55, yy - sy) / (W * 0.42)
    warm = np.exp(-d * d * 3.2)
    sky = ramp(SKY, np.clip(t + warm * 0.16, 0, 1))

    # stars, high up only
    stars = np.zeros((H, W), dtype=np.float32)
    n = 260
    ys = (rng.random(n) ** 2.2 * HORIZON * 0.42).astype(int)
    xs = (rng.random(n) * W).astype(int)
    stars[ys, xs] = rng.random(n) * 200 + 55
    stars = np.maximum(stars, blur_arr(stars, 1.1) * 2.2)
    sky = add(sky, stars[..., None] * np.array([1.0, 0.92, 1.0]), 0.75)

    # cloud streaks
    n1 = noise(W, H, 420, 46, rng, 5)
    n2 = noise(W, H, 160, 20, rng, 4)
    cl = n1 * 0.68 + n2 * 0.32
    band = smoothstep(0.02, 0.22, t) * (1 - smoothstep(0.80, 0.97, t))
    dens = smoothstep(0.47, 0.68, cl) * band
    # under-lighting: brighter where the cloud thins out towards the bottom
    below = np.roll(cl, -9, axis=0)
    lit = np.clip((cl - below) * 9.0 + 0.45, 0, 1) * (0.35 + 0.65 * smoothstep(0.25, 0.95, t))
    lit = np.clip(lit + warm * 0.35, 0, 1)
    body = ramp([(0, (70, 34, 120)), (0.5, (150, 60, 150)), (1, (214, 84, 150))], t)
    glow = ramp([(0, (206, 96, 176)), (0.55, (255, 140, 150)), (1, (255, 206, 150))], t)
    ccol = body * (1 - lit[..., None]) + glow * lit[..., None]
    a = (dens * 0.92)[..., None]
    sky = sky * (1 - a) + ccol * a
    nosun = sky.copy()

    # sun: halo, then disc
    r = np.hypot(xx - sx, yy - sy)
    halo = np.exp(-(r / (sr * 2.3)) ** 2)[..., None] * np.array([255, 150, 96]) * 0.42
    sky = add(sky, halo)
    disc = 1 - smoothstep(sr - 2.0, sr + 2.0, r)
    v = np.clip((yy - (sy - sr)) / (2 * sr), 0, 1)
    dcol = ramp([(0, (255, 232, 150)), (0.30, (255, 196, 110)), (0.62, (255, 128, 104)), (1, (246, 70, 132))], v)
    # a few cloud bars drift across the lower sun
    bars = smoothstep(0.56, 0.66, np.roll(n1, 40, axis=1)) * smoothstep(sy - sr * 0.1, sy + sr * 0.6, yy)
    disc = disc * (1 - bars * 0.9)
    sky = sky * (1 - disc[..., None]) + dcol * disc[..., None]
    return sky, nosun


# ---------------------------------------------------------------- skyline + water
def build_ground(sky, nosun, rng):
    out = sky.copy()
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    sx, sy, sr = SUN

    # water: mirrored sky, darkened, with ripples
    depth = np.clip((yy - HORIZON) / (H - HORIZON), 0, 1)
    src_y = np.clip(HORIZON - (yy - HORIZON) * 1.9, 0, HORIZON - 1).astype(int)
    wob = (noise(W, H, 90, 6, rng, 3) - 0.5) * 26 * (0.3 + depth)
    src_x = np.clip(xx + wob, 0, W - 1).astype(int)
    refl = nosun[src_y, src_x]
    tint = ramp([(0, (150, 62, 132)), (0.35, (84, 34, 120)), (1, (26, 12, 60))], depth)
    k = (0.62 - 0.40 * depth)[..., None]
    water = refl * k + tint * (1 - k)
    # sun glitter path
    rip = noise(W, H, 60, 3.2, rng, 3)
    spread = 60 + depth * 330
    path = np.exp(-((xx - sx) / spread) ** 2) * smoothstep(0.52, 0.70, rip) * (1 - depth * 0.55)
    water = add(water, path[..., None] * np.array([255, 196, 130]), 0.95)
    # faint pink ripple lines everywhere
    rip2 = smoothstep(0.60, 0.74, noise(W, H, 110, 2.6, rng, 2)) * (0.25 + 0.5 * depth)
    water = add(water, rip2[..., None] * np.array([255, 120, 190]), 0.20)
    m = (yy >= HORIZON)[..., None]
    out = np.where(m, water, out)

    # far skyline: low, hazy
    sk = Image.new('L', (W, H), 0)
    lights = Image.new('RGB', (W, H), (0, 0, 0))
    d = ImageDraw.Draw(sk)
    dl = ImageDraw.Draw(lights)
    x = -10
    while x < W + 10:
        cluster = 0.5 + 0.5 * math.sin(x / 210.0 + 1.3) * math.sin(x / 71.0)
        near_sun = math.exp(-((x - sx) / 300.0) ** 2)
        bw = int(rng.integers(14, 46))
        bh = int(6 + rng.random() ** 2.2 * (26 + 78 * cluster) * (1 - 0.55 * near_sun))
        top = HORIZON - bh
        d.rectangle([x, top, x + bw, HORIZON + 1], fill=255)
        if bh > 44 and rng.random() < 0.5:          # stepped art-deco crown + mast
            d.rectangle([x + bw * 0.25, top - 8, x + bw * 0.75, top], fill=255)
            d.line([x + bw / 2, top - 8, x + bw / 2, top - 24], fill=255, width=2)
        for _ in range(int(bw * bh / 150)):
            lx, ly = x + rng.integers(2, max(3, bw - 2)), top + rng.integers(3, max(4, bh - 2))
            c = [(255, 214, 150), (255, 150, 200), (130, 240, 235)][int(rng.integers(0, 3))]
            dl.rectangle([lx, ly, lx + 1, ly + 1], fill=c)
        x += bw + int(rng.integers(0, 5))
    skm = np.asarray(sk, dtype=np.float32)[..., None] / 255.0
    haze = np.exp(-((xx - sx) / 520.0) ** 2)[..., None]
    scol = np.array([52, 20, 92]) * (1 - haze * 0.55) + np.array([196, 70, 120]) * haze * 0.55
    out = out * (1 - skm) + scol * skm
    la = np.asarray(lights, dtype=np.float32)
    out = add(out, la * skm, 0.9)
    out = add(out, blur_arr(la, 3) * skm, 1.2)
    # light streaks dropped into the water
    streak = np.zeros_like(la)
    col_light = la.max(axis=0)                     # per column
    for i in range(1, 46):
        y = HORIZON + i
        if y >= H:
            break
        streak[y] = col_light * (1 - i / 46.0) * (0.55 if (i % 3) else 0.2)
    out = add(out, blur_arr(streak, 1.2), 0.55)
    # warm line of light on the horizon
    hz = np.exp(-((yy - HORIZON) / 2.2) ** 2) * (0.25 + 0.75 * np.exp(-((xx - sx) / 620.0) ** 2))
    out = add(out, hz[..., None] * np.array([255, 190, 150]), 0.55)
    return out


# ---------------------------------------------------------------- palms
def bez(p0, p1, p2, t):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])


def bez_d(p0, p1, p2, t):
    return (2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0]),
            2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1]))


def frond(d, c, ang, length, droop, rng, s):
    a = math.radians(ang)
    ux, uy = math.cos(a), -math.sin(a)
    p0 = c
    p1 = (c[0] + ux * length * 0.50, c[1] + uy * length * 0.50 - length * 0.16)
    p2 = (c[0] + ux * length * 0.98, c[1] + uy * length * 0.98 + droop * length)
    n = int(length / (5.2 * s)) + 8
    prev = p0
    for i in range(n + 1):
        t = i / n
        p = bez(p0, p1, p2, t)
        dx, dy = bez_d(p0, p1, p2, t)
        m = math.hypot(dx, dy) or 1.0
        tx, ty = dx / m, dy / m
        nx, ny = -ty, tx
        d.line([prev, p], fill=255, width=max(2, int((5.0 - 3.6 * t) * s)))
        prev = p
        if t < 0.05:
            continue
        ll = length * 0.36 * (math.sin(math.pi * min(1.0, t * 1.06)) ** 0.55) * (1.0 - 0.25 * t)
        ll *= 0.82 + 0.36 * rng.random()
        for side in (-1, 1):
            vx = side * nx * 0.72 + tx * 0.62
            vy = side * ny * 0.72 + ty * 0.62 + 0.62          # gravity
            vm = math.hypot(vx, vy) or 1.0
            vx, vy = vx / vm, vy / vm
            bw = 2.1 * s
            tip = (p[0] + vx * ll, p[1] + vy * ll + ll * 0.10)
            mid = (p[0] + vx * ll * 0.5 + nx * side * 0.6, p[1] + vy * ll * 0.5)
            d.polygon([(p[0] - tx * bw, p[1] - ty * bw), (mid[0] - tx * bw * 0.7, mid[1] - ty * bw * 0.7), tip,
                       (mid[0] + tx * bw * 0.7, mid[1] + ty * bw * 0.7), (p[0] + tx * bw, p[1] + ty * bw)], fill=255)


def palm(d, base, crown, bend, size, rng, s):
    """base/crown in design px; s = supersample factor."""
    b = (base[0] * s, base[1] * s)
    c = (crown[0] * s, crown[1] * s)
    ctrl = ((b[0] + c[0]) / 2 + bend * s, (b[1] + c[1]) / 2)
    left, right = [], []
    n = 40
    for i in range(n + 1):
        t = i / n
        p = bez(b, ctrl, c, t)
        dx, dy = bez_d(b, ctrl, c, t)
        m = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / m, dx / m
        w = (size * 0.060 * (1 - t) + size * 0.030 * t) * s * (1.0 + 0.07 * math.sin(i * 2.4))
        left.append((p[0] + nx * w, p[1] + ny * w))
        right.append((p[0] - nx * w, p[1] - ny * w))
    d.polygon(left + right[::-1], fill=255)
    angs = [200, 176, 152, 128, 104, 82, 58, 34, 10, -14, 226, -40, 118, 66]
    for k, a in enumerate(angs):
        a += rng.uniform(-9, 9)
        side = abs(math.cos(math.radians(a)))
        L = size * (0.80 + 0.30 * rng.random()) * (0.86 + 0.14 * side) * s
        droop = 0.16 + 0.44 * side + (0.26 if a > 190 or a < -5 else 0) + rng.uniform(-0.05, 0.08)
        frond(d, c, a, L, droop, rng, s)
    for k in range(4):                                # coconuts
        ox, oy = rng.uniform(-0.07, 0.07) * size * s, rng.uniform(0.01, 0.08) * size * s
        r = size * 0.034 * s
        d.ellipse([c[0] + ox - r, c[1] + oy - r, c[0] + ox + r, c[1] + oy + r], fill=255)


PALMS = [
    # base, crown, bend, size
    ((-40, 760), (150, 150), -70, 250),
    ((236, 780), (330, 300), 34, 190),
    ((1900, 770), (1700, 132), 80, 262),
    ((1640, 790), (1530, 318), -30, 182),
    ((60, 800), (20, 392), -10, 150),
]


def build_palms(rng, palms=PALMS):
    s = 2
    m = Image.new('L', (W * s, H * s), 0)
    d = ImageDraw.Draw(m)
    for base, crown, bend, size in palms:
        palm(d, base, crown, bend, size, rng, s)
    return m.resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- lettering
FILL = [
    (0.00, (255, 250, 226)),
    (0.26, (255, 226, 150)),
    (0.52, (255, 150, 104)),
    (0.76, (250, 84, 140)),
    (1.00, (190, 44, 168)),
]


def text_mask(text, font, tracking=0):
    widths = [font.getbbox(ch) for ch in text]
    adv = [font.getlength(ch) for ch in text]
    total = int(sum(adv) + tracking * (len(text) - 1)) + 80
    asc, desc = font.getmetrics()
    im = Image.new('L', (total, asc + desc + 40), 0)
    d = ImageDraw.Draw(im)
    x = 30
    for ch, a in zip(text, adv):
        d.text((x, 10), ch, font=font, fill=255)
        x += a + tracking
    return im.crop(im.getbbox())


def dilate(mask, r):
    return mask.filter(ImageFilter.GaussianBlur(r * 0.5)).point(lambda v: 255 if v > 26 else 0) \
        .filter(ImageFilter.GaussianBlur(0.9))


def build_title(width=900):
    """Returns an RGBA layer (W x H) holding XIFO and the neon tag line, plus its bbox."""
    f = ImageFont.truetype(F_TITLE, 400)
    m = text_mask('XIFO', f, tracking=4)
    sc = width / m.width
    m = m.resize((width, int(m.height * sc)), Image.LANCZOS)
    tw, th = m.size
    pad = 90
    cw, ch = tw + pad * 2, th + pad * 2
    M = Image.new('L', (cw, ch), 0)
    M.paste(m, (pad, pad))

    layer = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))

    # extrusion, down and to the right
    depth = 20
    ext = Image.new('L', (cw, ch), 0)
    for i in range(1, depth + 1):
        ext = ImageChops.lighter(ext, ImageChops.offset(M, int(i * 0.75), i))
    edge = dilate(ImageChops.lighter(ext, M), 9)
    shadow = ImageChops.offset(edge, 10, 16).filter(ImageFilter.GaussianBlur(14))
    layer.paste(Image.new('RGBA', (cw, ch), (14, 4, 40, 255)), (0, 0), shadow.point(lambda v: int(v * 0.72)))
    layer.paste(Image.new('RGBA', (cw, ch), (26, 10, 58, 255)), (0, 0), edge)
    yy = np.linspace(0, 1, ch, dtype=np.float32)[:, None] * np.ones((1, cw), dtype=np.float32)
    t = np.clip((yy * ch - pad) / (th + depth), 0, 1)
    ecol = ramp([(0, (150, 40, 170)), (0.5, (96, 26, 140)), (1, (52, 16, 104))], t)
    layer.paste(to_img(ecol).convert('RGBA'), (0, 0), ext)

    # outline around the face, then the face itself
    layer.paste(Image.new('RGBA', (cw, ch), (26, 10, 58, 255)), (0, 0), dilate(M, 5))
    t = np.clip((yy * ch - pad) / th, 0, 1)
    face = ramp(FILL, t)
    layer.paste(to_img(face).convert('RGBA'), (0, 0), M)
    # bright top-left bevel and a soft sheen
    bevel = ImageChops.subtract(M, ImageChops.offset(M, 3, 4))
    layer.paste(Image.new('RGBA', (cw, ch), (255, 255, 240, 255)), (0, 0), bevel.point(lambda v: int(v * 0.85)))
    low = ImageChops.subtract(M, ImageChops.offset(M, -3, -4))
    layer.paste(Image.new('RGBA', (cw, ch), (120, 20, 130, 255)), (0, 0), low.point(lambda v: int(v * 0.55)))
    return layer, (pad, pad, pad + tw, pad + th)


def neon_text(text, size, color, tracking=10, core=(255, 255, 255)):
    f = ImageFont.truetype(F_TAG, size)
    m = text_mask(text, f, tracking=tracking)
    pad = 60
    cw, ch = m.width + pad * 2, m.height + pad * 2
    M = Image.new('L', (cw, ch), 0)
    M.paste(m, (pad, pad))
    return M, pad


def sign(img, text, cx, cy, size=46, tracking=13):
    """A small neon sign: dark plate, pink tube border, teal tube lettering."""
    M, pad = neon_text(text, size, None, tracking=tracking)
    tw, th = M.width - pad * 2, M.height - pad * 2
    pw, ph = tw + 92, th + 44
    x0, y0 = cx - pw // 2, cy - ph // 2
    s = 3
    plate = Image.new('L', (pw * s, ph * s), 0)
    ImageDraw.Draw(plate).rounded_rectangle([0, 0, pw * s - 1, ph * s - 1], radius=ph * s // 2, fill=255)
    tube = Image.new('L', (pw * s, ph * s), 0)
    ImageDraw.Draw(tube).rounded_rectangle([5 * s, 5 * s, pw * s - 1 - 5 * s, ph * s - 1 - 5 * s],
                                           radius=(ph - 10) * s // 2, outline=255, width=3 * s)
    plate = plate.resize((pw, ph), Image.LANCZOS)
    tube = tube.resize((pw, ph), Image.LANCZOS)

    full_p = Image.new('L', img.size, 0); full_p.paste(plate, (x0, y0))
    full_b = Image.new('L', img.size, 0); full_b.paste(tube, (x0, y0))
    full_t = Image.new('L', img.size, 0); full_t.paste(M, (cx - M.width // 2, cy - M.height // 2 - 1))

    arr = np.asarray(img.convert('RGB'), dtype=np.float32)
    sh = blur_arr(np.asarray(ImageChops.offset(full_p, 4, 8), dtype=np.float32), 9) / 255.0
    arr = arr * (1 - sh * 0.55)[..., None]
    pa = (np.asarray(full_p, dtype=np.float32) / 255.0)[..., None]
    arr = arr * (1 - pa * 0.93) + np.array([22, 8, 52], dtype=np.float32) * pa * 0.93
    pink = np.array([255, 60, 170], dtype=np.float32)
    teal = np.array([40, 236, 226], dtype=np.float32)
    for mask, col, corecol in ((full_b, pink, (255, 214, 238)), (full_t, teal, (228, 255, 250))):
        fa = np.asarray(mask, dtype=np.float32)
        arr = add(arr, (blur_arr(fa, 16) / 255.0)[..., None] * col, 0.95)
        arr = add(arr, (blur_arr(fa, 5) / 255.0)[..., None] * col, 0.95)
        f1 = (fa / 255.0)[..., None]
        arr = arr * (1 - f1) + np.array(corecol, dtype=np.float32) * f1
    return to_img(arr).convert('RGBA')


# ---------------------------------------------------------------- compose
def grade(arr, rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # bloom
    bright = np.clip(arr - 170, 0, 255) * 1.6
    arr = add(arr, blur_arr(bright, 18), 0.38)
    # vignette
    v = 1 - 0.34 * np.clip(np.hypot((xx - W / 2) / (W / 2), (yy - H / 2) / (H / 2)) - 0.45, 0, 1) ** 1.5
    arr = arr * v[..., None]
    # film grain
    g = rng.normal(0, 3.4, (H, W)).astype(np.float32)
    return np.clip(arr + g[..., None], 0, 255)


def build(seed=11, cutouts=None, title_width=840, title_xy=None, show_tag=True, back=None, front=None):
    """cutouts: list of (RGBA image, (x, y), z) with z 'back' (behind title) or 'front'."""
    rng = np.random.default_rng(seed)
    sky, nosun = build_sky(rng)
    bg = build_ground(sky, nosun, rng)
    palms = build_palms(rng)
    pm = np.asarray(palms, dtype=np.float32)[..., None] / 255.0
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    pcol = ramp([(0, (30, 10, 62)), (1, (14, 5, 34))], np.clip(yy / H, 0, 1))
    # light wraps round the fronds near the sun
    wrap = blur_arr(np.clip(bg - 150, 0, 255), 10) * 0.55
    bg = bg * (1 - pm) + (pcol + wrap * 0.35) * pm
    img = to_img(bg).convert('RGBA')

    for im, xy, z in (cutouts or []):
        if z == 'back':
            img.alpha_composite(im, xy)

    title, box = build_title(title_width)
    if title_xy is None:
        tx = (W - (box[2] - box[0])) // 2 - box[0]
        ty = int(H * 0.385) - (box[3] - box[1]) // 2 - box[1]
    else:
        tx, ty = title_xy[0] - box[0], title_xy[1] - box[1]
    a = title.split()[3]
    # a dark halo lifts the lettering off the sun, then a pink glow
    g = Image.new('RGBA', img.size, (0, 0, 0, 0))
    g.paste(Image.new('RGBA', title.size, (40, 8, 70, 255)), (tx, ty),
            a.filter(ImageFilter.GaussianBlur(22)).point(lambda v: int(min(255, v * 1.5) * 0.55)))
    img = Image.alpha_composite(img, g)
    g = Image.new('RGBA', img.size, (0, 0, 0, 0))
    g.paste(Image.new('RGBA', title.size, (255, 70, 170, 255)), (tx, ty),
            a.filter(ImageFilter.GaussianBlur(46)).point(lambda v: int(v * 0.30)))
    img = Image.alpha_composite(img, g)
    img.alpha_composite(title, (tx, ty))

    if show_tag:
        img = sign(img, 'XI: FOREVER OFFLINE', tx + (box[0] + box[2]) // 2 + 10, ty + box[3] + 62)

    for im, xy, z in (cutouts or []):
        if z == 'front':
            img.alpha_composite(im, xy)

    arr = grade(np.asarray(img.convert('RGB'), dtype=np.float32), rng)
    return to_img(arr)


# ---------------------------------------------------------------- figures from the art pack
def load(name):
    return Image.open(os.path.join(ART, f'ff11-{name}.jpg')).convert('RGB')


def paper_alpha(img, floor=0.05):
    a = np.asarray(img, dtype=np.float32) / 255.0
    al = (1.0 - a).max(axis=2)
    return np.clip((al - floor) / (1 - floor), 0, 1)


def solid_mask(img, thr=0.10, grow=9, skip=(), hole_r=6, keep=()):
    """Solid mask of a figure drawn on white: strokes closed up, enclosed holes filled.
    skip: boxes (fractions x0,y0,x1,y1) left out of the solid part (flames, magic swirls).
    hole_r: bare paper showing through between limbs (any patch that holds a disc of this
    radius) is cut out again; keep: boxes where bare paper is part of the figure."""
    al = paper_alpha(img)
    a = al > thr
    w, h = img.size
    for (x0, y0, x1, y1) in skip:
        a[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = False
    m = Image.fromarray((a * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(grow))
    pad = Image.new('L', (w + 2, h + 2), 0)
    pad.paste(m, (1, 1))
    ImageDraw.floodfill(pad, (0, 0), 128)
    inside = pad.crop((1, 1, w + 1, h + 1)).point(lambda v: 0 if v == 128 else 255)
    inside = inside.filter(ImageFilter.MinFilter(grow))
    # drop specks that are not part of the figure
    inside = inside.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    if hole_r:
        raw = np.asarray(img, dtype=np.float32) / 255.0
        bare = ((1.0 - raw).max(axis=2) < 0.045) & (np.asarray(inside) > 128)
        for (x0, y0, x1, y1) in keep:
            bare[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = False
        bare_im = Image.fromarray((bare * 255).astype(np.uint8), 'L')
        seeds = bare_im.filter(ImageFilter.MinFilter(hole_r * 2 + 1))
        for _ in range(140):                      # grow the seeds back, staying on bare paper
            nxt = ImageChops.darker(seeds.filter(ImageFilter.MaxFilter(3)), bare_im)
            if nxt.tobytes() == seeds.tobytes():
                break
            seeds = nxt
        holes = seeds.filter(ImageFilter.MaxFilter(3))
        inside = ImageChops.subtract(inside, holes)
    # pull the edge in a touch so no paper fringe is left
    return inside.filter(ImageFilter.GaussianBlur(1.3)).point(lambda v: max(0, min(255, int((v - 112) * 2.3))))


def cut(name, height, skip=(), fx=(), flip=False, crop=None, hole_r=6, keep=()):
    """Returns (RGBA figure, fx mask). fx: boxes whose strokes are kept as a glowing effect."""
    img = load(name)
    if crop:
        w, h = img.size
        img = img.crop((int(crop[0] * w), int(crop[1] * h), int(crop[2] * w), int(crop[3] * h)))
    w, h = img.size
    body = np.asarray(solid_mask(img, skip=tuple(skip) + tuple(fx), hole_r=hole_r, keep=keep), dtype=np.float32) / 255.0
    al = paper_alpha(img)
    fxm = np.zeros((h, w), dtype=np.float32)
    for (x0, y0, x1, y1) in fx:
        fxm[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)] = 1.0
    fxm = np.asarray(Image.fromarray((fxm * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(6)),
                     dtype=np.float32) / 255.0
    fx_alpha = al * fxm * (1 - body)
    rgba = np.dstack([np.asarray(img, dtype=np.float32), body * 255.0])
    fig = Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), 'RGBA')
    fxi = Image.fromarray(np.clip(fx_alpha * 255, 0, 255).astype(np.uint8), 'L')
    # trim to the figure (and its effect)
    both = ImageChops.lighter(fig.split()[3], fxi)
    box = both.point(lambda v: 255 if v > 24 else 0).getbbox()
    fig, fxi = fig.crop(box), fxi.crop(box)
    s = height / fig.height
    size = (max(1, round(fig.width * s)), height)
    fig, fxi = fig.resize(size, Image.LANCZOS), fxi.resize(size, Image.LANCZOS)
    if flip:
        fig, fxi = fig.transpose(Image.FLIP_LEFT_RIGHT), fxi.transpose(Image.FLIP_LEFT_RIGHT)
    return fig, fxi


def blur(a, r):
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, dtype=np.float32) / 255.0


def shift(a, dx, dy):
    out = np.zeros_like(a)
    h, w = a.shape
    xs0, xs1 = max(0, dx), min(w, w + dx)
    ys0, ys1 = max(0, dy), min(h, h + dy)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def light(fig, fxi, side, fx_color=(255, 170, 70), rim=1.0, dusk=1.0, fade=0.16, sat_boost=1.22, fx_gain=1.0):
    """Sunset lighting. side = +1 if the sun is to the figure's right, -1 if to its left."""
    a = np.asarray(fig, dtype=np.float32)
    rgb, al = a[..., :3] / 255.0, a[..., 3] / 255.0
    h, w = al.shape
    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(axis=2)

    # dusk grade: paper whites turn peach, shadows sink into violet, colours stay their own
    hi = np.array([1.00, 0.84, 0.80])
    lo = np.array([0.16, 0.05, 0.30])
    tone = lo + (hi - lo) * (lum[..., None] ** 0.9)
    base = rgb * np.array([1.0, 0.88, 0.90])
    base = base + ((1 - lum) ** 2)[..., None] * np.array([0.07, 0.00, 0.15])
    graded = base * (1 - 0.24 * dusk) + tone * (0.24 * dusk)
    graded = (graded - 0.5) * 1.14 + 0.5 - 0.035
    g2 = (graded * np.array([0.299, 0.587, 0.114])).sum(axis=2)[..., None]
    graded = g2 + (graded - g2) * sat_boost

    # warm rim on the sun side, cool neon fill on the far side
    d = int(max(4, h * 0.016))
    warm = np.clip(al - shift(al, -side * d, int(d * 0.55)), 0, 1)
    warm = np.clip(blur(warm, d * 0.45) * 1.9, 0, 1) * al
    cool = np.clip(al - shift(al, side * int(d * 0.8), -int(d * 0.2)), 0, 1)
    cool = np.clip(blur(cool, d * 0.4) * 1.5, 0, 1) * al
    # a broad wash of sunset light across the sun-facing half
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :] * np.ones((h, 1), dtype=np.float32)
    wash = (xx if side > 0 else 1 - xx) ** 1.6 * 0.22
    graded = graded + (np.array([1.0, 0.42, 0.42]) * wash[..., None]) * (0.35 + 0.65 * lum[..., None])
    graded = graded + np.array([1.0, 0.62, 0.42]) * (warm * 0.85 * rim)[..., None]
    graded = graded * (1 - cool * 0.35 * rim)[..., None] + np.array([0.10, 0.80, 0.92]) * (cool * 0.50 * rim)[..., None]

    # sink the feet into the dusk
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), dtype=np.float32)
    f = np.clip((yy - (1 - fade)) / fade, 0, 1) ** 1.3
    graded = graded * (1 - f[..., None] * 0.78) + np.array([0.09, 0.03, 0.18]) * f[..., None] * 0.78

    out = np.dstack([np.clip(graded, 0, 1), al])
    lit = Image.fromarray((out * 255).astype(np.uint8), 'RGBA')

    # effect layer (flames etc.): strokes become light
    fx = np.asarray(fxi, dtype=np.float32) / 255.0
    layer = Image.new('RGBA', fig.size, (0, 0, 0, 0))
    if fx.max() > 0.02:
        glow = (blur(fx, 14) * 1.6 + blur(fx, 5) * 0.8) * fx_gain
        core = np.clip(fx * 1.9 * fx_gain, 0, 1)
        c = np.array(fx_color, dtype=np.float32) / 255.0
        col = np.clip(c[None, None, :] * (0.55 + 0.45 * core[..., None]) + core[..., None] ** 2 * 0.55, 0, 1)
        la = np.clip(glow * 0.75 + core * 0.9, 0, 1)
        layer = Image.fromarray((np.dstack([col, la]) * 255).astype(np.uint8), 'RGBA')
    return lit, layer


def halo(fig, color=(18, 6, 44), r=16, k=0.62, offset=(0, 6)):
    """Soft dark halo that lifts a figure off the palms and the water."""
    a = fig.split()[3].filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(min(255, v * 1.35) * k))
    pad = r * 3
    out = Image.new('RGBA', (fig.width + pad * 2, fig.height + pad * 2), (0, 0, 0, 0))
    sh = Image.new('RGBA', fig.size, color + (255,))
    big = Image.new('L', out.size, 0)
    big.paste(fig.split()[3], (pad + offset[0], pad + offset[1]))
    big = big.filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(min(255, v * 1.35) * k))
    out.paste(Image.new('RGBA', out.size, color + (255,)), (0, 0), big)
    return out, pad


# ---------------------------------------------------------------- the scene
LAYOUT = [
    ('red-mage',   640,  150, 772, +1, 'back', dict(fx=[(0.50, 0.50, 1.0, 0.86), (0.62, 0.36, 1.0, 0.60)])),
    ('black-mage', 352,   16, 752, +1, 'back', dict(light=dict(dusk=0.6, sat_boost=1.3))),
    ('thief',      640, 1306, 772, -1, 'back', {}),
    ('shantotto',  300, 1262, 720, -1, 'back', dict(fx=[(0.55, 0.62, 1.0, 1.0)])),
]


def figures(layout):
    out = []
    for name, h, x, bottom, side, z, kw in layout:
        kw = dict(kw)
        lk = kw.pop('light', {})
        fig, fxi = cut(name, h, **kw)
        lit, fx = light(fig, fxi, side, **lk)
        glow, pad = halo(lit)
        y = bottom - h
        out.append((glow, (x - pad, y - pad), z))
        out.append((lit, (x, y), z))
        out.append((fx, (x, y), z))
    return out


def place(canvas_items):
    """Clip layers to the canvas (alpha_composite needs non-negative offsets)."""
    res = []
    for im, (x, y), z in canvas_items:
        full = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        sx, sy = max(0, -x), max(0, -y)
        part = im.crop((sx, sy, min(im.width, W - x), min(im.height, H - y)))
        if part.width > 0 and part.height > 0:
            full.paste(part, (max(0, x), max(0, y)))
        res.append((full, (0, 0), z))
    return res


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out/press'
    os.makedirs(out, exist_ok=True)
    big = build(cutouts=place(figures(LAYOUT)))
    big.save(os.path.join(out, 'xifo_vice_1840.png'))
    # the launcher's picture frame is up to 1056 x 422, so the one-time banner is kept a size above that
    once = big.resize((1400, 560), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=30, threshold=2))
    once.save(os.path.join(out, 'xifo_vice__once.jpg'), quality=93, subsampling=0)
    print('ok')
