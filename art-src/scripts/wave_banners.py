"""Four vaporwave XIFO banners for the launcher: grid sunset, neon night strip, pastel windows, VHS sunset road.

Usage:  python wave_banners.py OUTDIR [grid night dream vhs]     (all four when no names are given)

Builds on vice_banner.py (same folder) for the palms, the cut-outs and the neon sign plate. Everything but
the figures and the framed screenshots is drawn in code. Needs Pillow + numpy and, in art-src\\fonts,
Kanit-BlackItalic.ttf, Righteous-Regular.ttf and DotGothic16-Regular.ttf (all SIL OFL).
Design space is 1840 x 736; each banner is saved at 1400 x 560 as  xifo_wave_<name>.jpg.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import vice_banner as V

W, H = V.W, V.H
F_TITLE = os.path.join(V.FONTS, 'Kanit-BlackItalic.ttf')
F_TAG = os.path.join(V.FONTS, 'Righteous-Regular.ttf')
F_PIX = os.path.join(V.FONTS, 'DotGothic16-Regular.ttf')

# any file in art-src can be a figure: 'red-mage' is ff11-red-mage.jpg, a name with a dot is taken as it is
V.load = lambda name: Image.open(os.path.join(V.ART, name if '.' in name else f'ff11-{name}.jpg')).convert('RGB')

YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)


# ------------------------------------------------------------------ small helpers
def vgrad(stops, y0=0, y1=H):
    return V.ramp(stops, np.clip((YY - y0) / max(1.0, float(y1 - y0)), 0, 1))


def gblur(a, r):
    """a: float array 0..1 (H, W) -> blurred 0..1."""
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, dtype=np.float32) / 255.0


def mask_arr(im):
    return np.asarray(im, dtype=np.float32) / 255.0


def col(c):
    return np.array(c, dtype=np.float32)


def glow_add(arr, m, color, k=1.0, radii=((40, 0.45), (16, 0.8), (5, 1.0))):
    for r, s in radii:
        arr = V.add(arr, gblur(m, r)[..., None] * col(color), s * k)
    return arr


def neon(arr, m, color, core=(255, 255, 255), k=1.0, mix=0.75):
    """A glowing tube: m is the tube itself (0..1)."""
    arr = glow_add(arr, m, color, k)
    c = col(color) * (1 - mix) + col(core) * mix
    return arr * (1 - m[..., None]) + c * m[..., None]


def stars(arr, rng, n, ymax, k=0.8):
    s = np.zeros((H, W), dtype=np.float32)
    ys = (rng.random(n) ** 1.8 * ymax).astype(int)
    xs = (rng.random(n) * W).astype(int)
    s[ys, xs] = rng.random(n) * 0.8 + 0.2
    s = np.maximum(s, gblur(s, 1.1) * 2.4)
    return V.add(arr, s[..., None] * col((255, 240, 255)), k)


def retro_sun(arr, cx, cy, r, stops, horizon=None, slits=8, glow=(255, 80, 170), glow_k=0.5, start=0.44):
    d = np.hypot(XX - cx, YY - cy)
    disc = 1 - V.smoothstep(r - 1.5, r + 1.5, d)
    v = np.clip((YY - (cy - r)) / (2.0 * r), 0, 1)
    if slits:
        rel = np.clip((v - start) / (1 - start), 0, 1)
        period = 2.0 * r * (1 - start) / slits
        ph = ((YY - (cy - r + 2.0 * r * start)) % period)
        thick = period * (0.16 + 0.52 * rel)
        gap = np.clip((thick - ph) / 1.5, 0, 1) * np.clip(ph / 1.5 + 0.5, 0, 1) * (v > start)
        disc = disc * (1 - gap)
    if horizon is not None:
        disc = disc * (YY < horizon)
    halo = np.exp(-(d / (r * 1.85)) ** 2)
    if horizon is not None:
        halo = halo * (0.35 + 0.65 * (YY < horizon))
    arr = V.add(arr, halo[..., None] * col(glow), glow_k)
    return arr * (1 - disc[..., None]) + V.ramp(stops, v) * disc[..., None]


def floor_coords(horizon, vpx, cell_px, zscale=2.2, scroll=0.0):
    """Perspective ground: returns t (0 at the horizon, 1 at the bottom edge), world x and z in cells,
    and how many pixels one cell covers across and down at each point."""
    dy = np.maximum(YY - horizon, 0.5)
    depth = (H - horizon) / dy
    t = np.clip((YY - horizon) / (H - horizon), 0, 1)
    wx = (XX - vpx) * depth / cell_px
    wz = depth * zscale + scroll
    px_x = cell_px / depth
    px_z = (dy * dy) / (zscale * (H - horizon))
    return t, wx, wz, px_x, px_z


def grid_floor(arr, horizon, vpx, base, line, cell_px=None, k=1.0, lw=(1.3, 2.6), zscale=2.2, mask=None):
    cell_px = cell_px or W * 0.105
    t, wx, wz, px_x, px_z = floor_coords(horizon, vpx, cell_px, zscale)
    ground = V.ramp(base, t)
    below = (YY > horizon).astype(np.float32)
    if mask is not None:
        below = below * mask
    width = lw[0] + (lw[1] - lw[0]) * t
    lx = np.clip(1 - np.abs(wx - np.round(wx)) * px_x / width, 0, 1)
    lz = np.clip(1 - np.abs(wz - np.round(wz)) * px_z / width, 0, 1)
    g = np.maximum(lx, lz) * V.smoothstep(0.0, 0.16, t) * below
    arr = arr * (1 - below[..., None]) + ground * below[..., None]
    arr = glow_add(arr, g, line, k, radii=((14, 0.55), (4, 0.7)))
    return V.add(arr, g[..., None] * (col(line) * 0.6 + 100), k)


def ridge(rng, x0, x1, base_y, height, step=56, peak=None):
    """A low-poly ridge line as points; peak = x of the highest point."""
    n = max(3, int((x1 - x0) / step))
    xs = np.linspace(x0, x1, n + 1)
    xs[1:-1] += rng.uniform(-step * 0.3, step * 0.3, n - 1)
    peak = (x0 + x1) / 2 if peak is None else peak
    span = max(peak - x0, x1 - peak)
    env = np.clip(1 - np.abs(xs - peak) / span, 0, 1) ** 0.8
    hs = height * env * rng.uniform(0.45, 1.0, n + 1)
    hs[0] = hs[-1] = 0
    return [(float(x), float(base_y - h)) for x, h in zip(xs, hs)]


def mountain(arr, pts, base_y, fill, edge=None, mesh=None, edge_k=1.0):
    s = 2
    m = Image.new('L', (W * s, H * s), 0)
    d = ImageDraw.Draw(m)
    poly = [(x * s, y * s) for x, y in pts] + [(pts[-1][0] * s, base_y * s), (pts[0][0] * s, base_y * s)]
    d.polygon(poly, fill=255)
    ma = mask_arr(m.resize((W, H), Image.LANCZOS))
    fillc = V.ramp(fill, np.clip((YY - (base_y - 200)) / 200.0, 0, 1)) if isinstance(fill, list) else col(fill)
    arr = arr * (1 - ma[..., None]) + fillc * ma[..., None]
    if edge is not None:
        e = Image.new('L', (W * s, H * s), 0)
        de = ImageDraw.Draw(e)
        de.line([(x * s, y * s) for x, y in pts], fill=255, width=2 * s, joint='curve')
        if mesh:
            for i in range(1, len(pts) - 1):
                x, y = pts[i]
                for dx in (-mesh, mesh * 0.35, mesh * 1.3):
                    de.line([(x * s, y * s), ((x + dx) * s, base_y * s)], fill=150, width=s)
        ea = mask_arr(e.resize((W, H), Image.LANCZOS)) * (YY <= base_y)
        arr = glow_add(arr, ea, edge, edge_k, radii=((10, 0.5), (3, 0.8)))
        arr = V.add(arr, ea[..., None] * (col(edge) * 0.7 + 60), edge_k)
    return arr


def palms_mask(rng, palms):
    return mask_arr(V.build_palms(rng, palms))


def text_img(text, size, font=F_PIX, fill=(255, 255, 255), tracking=0):
    f = ImageFont.truetype(font, size)
    m = V.text_mask(text, f, tracking=tracking)
    out = Image.new('RGBA', m.size, tuple(fill) + (0,))
    out.putalpha(m)
    return out


def paste(canvas, im, x, y):
    """alpha-composite im on canvas at any offset (clipped)."""
    x, y = int(round(x)), int(round(y))
    sx, sy = max(0, -x), max(0, -y)
    part = im.crop((sx, sy, min(im.width, canvas.width - x), min(im.height, canvas.height - y)))
    if part.width > 0 and part.height > 0:
        canvas.alpha_composite(part, (max(0, x), max(0, y)))


def shadowed(canvas, im, x, y, off=(8, 10), r=10, k=0.5, color=(20, 6, 50)):
    a = im.split()[3]
    pad = r * 3
    sh = Image.new('L', (im.width + pad * 2, im.height + pad * 2), 0)
    sh.paste(a, (pad, pad))
    sh = sh.filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(v * k))
    layer = Image.new('RGBA', sh.size, tuple(color) + (0,))
    layer.putalpha(sh)
    paste(canvas, layer, x - pad + off[0], y - pad + off[1])
    paste(canvas, im, x, y)


def to_rgba(arr):
    return V.to_img(arr).convert('RGBA')


def to_arr(img):
    return np.asarray(img.convert('RGB'), dtype=np.float32)


# ------------------------------------------------------------------ figures
def cut2(name, height, thr=0.10, **kw):
    orig = V.solid_mask
    V.solid_mask = lambda img, **k: orig(img, thr=thr, **k)
    try:
        return V.cut(name, height, **kw)
    finally:
        V.solid_mask = orig


def relight(fig, fxi, side, key=(1.0, 0.55, 0.60), fill=(0.10, 0.80, 0.92), lo=(0.14, 0.05, 0.30), hi=(1.0, 0.86, 0.86),
            tint=(1.0, 0.90, 0.94), tone=0.22, wash=(1.0, 0.36, 0.56), wash_k=0.20, bright=1.0, sat=1.2, rim=1.0, fill_k=0.5,
            fade=0.16, fade_col=(0.07, 0.02, 0.16), fade_k=0.78, fx_color=(255, 170, 70)):
    a = np.asarray(fig, dtype=np.float32)
    rgb, al = a[..., :3] / 255.0, a[..., 3] / 255.0
    h, w = al.shape
    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(axis=2)
    tn = col(lo) + (col(hi) - col(lo)) * (lum[..., None] ** 0.9)
    base = rgb * col(tint) + ((1 - lum) ** 2)[..., None] * col(lo) * 0.45
    g = base * (1 - tone) + tn * tone
    g = ((g - 0.5) * 1.14 + 0.5 - 0.03) * bright
    g2 = (g * np.array([0.299, 0.587, 0.114])).sum(axis=2)[..., None]
    g = g2 + (g - g2) * sat
    d = int(max(4, h * 0.016))
    warm = np.clip(al - V.shift(al, -side * d, int(d * 0.55)), 0, 1)
    warm = np.clip(V.blur(warm, d * 0.45) * 1.9, 0, 1) * al
    cool = np.clip(al - V.shift(al, side * int(d * 0.8), -int(d * 0.2)), 0, 1)
    cool = np.clip(V.blur(cool, d * 0.4) * 1.5, 0, 1) * al
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :] * np.ones((h, 1), dtype=np.float32)
    ws = (xx if side > 0 else 1 - xx) ** 1.6 * wash_k
    g = g + (col(wash) * ws[..., None]) * (0.35 + 0.65 * lum[..., None])
    g = g + col(key) * (warm * 0.85 * rim)[..., None]
    g = g * (1 - cool * 0.35 * rim * fill_k * 2)[..., None] + col(fill) * (cool * fill_k * rim)[..., None]
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None] * np.ones((1, w), dtype=np.float32)
    f = np.clip((yy - (1 - fade)) / max(fade, 1e-3), 0, 1) ** 1.3 * fade_k
    g = g * (1 - f[..., None]) + col(fade_col) * f[..., None]
    lit = Image.fromarray((np.dstack([np.clip(g, 0, 1), al]) * 255).astype(np.uint8), 'RGBA')
    fx = np.asarray(fxi, dtype=np.float32) / 255.0
    layer = Image.new('RGBA', fig.size, (0, 0, 0, 0))
    if fx.max() > 0.02:
        glow = V.blur(fx, 14) * 1.6 + V.blur(fx, 5) * 0.8
        core = np.clip(fx * 1.9, 0, 1)
        c = col(fx_color) / 255.0
        cc = np.clip(c[None, None, :] * (0.55 + 0.45 * core[..., None]) + core[..., None] ** 2 * 0.55, 0, 1)
        layer = Image.fromarray((np.dstack([cc, np.clip(glow * 0.75 + core * 0.9, 0, 1)]) * 255).astype(np.uint8), 'RGBA')
    return lit, layer


def figure(canvas, name, h, x, bottom, side, cut=None, light=None, halo=None):
    fig, fxi = cut2(name, h, **(cut or {}))
    lit, fx = relight(fig, fxi, side, **(light or {}))
    glow, pad = V.halo(lit, **(halo or {}))
    y = bottom - h
    paste(canvas, glow, x - pad, y - pad)
    paste(canvas, lit, x, y)
    paste(canvas, fx, x, y)
    return lit.size


# ------------------------------------------------------------------ lettering
def letters(width, text='XIFO', tracking=4, pad=120):
    f = ImageFont.truetype(F_TITLE, 400)
    m = V.text_mask(text, f, tracking=tracking)
    m = m.resize((width, int(m.height * width / m.width)), Image.LANCZOS)
    M = Image.new('L', (m.width + pad * 2, m.height + pad * 2), 0)
    M.paste(m, (pad, pad))
    return M, (pad, pad, pad + m.width, pad + m.height)


def grow(M, px):
    return M.filter(ImageFilter.MaxFilter(px * 2 + 1)).filter(ImageFilter.GaussianBlur(0.9))


def shrink(M, px):
    return M.filter(ImageFilter.MinFilter(px * 2 + 1)).filter(ImageFilter.GaussianBlur(0.9))


def face_img(M, box, stops):
    cw, ch = M.size
    yy = np.arange(ch, dtype=np.float32)[:, None] * np.ones((1, cw), dtype=np.float32)
    t = np.clip((yy - box[1]) / (box[3] - box[1]), 0, 1)
    return V.to_img(V.ramp(stops, t)).convert('RGBA'), t


def solid(size, c):
    return Image.new('RGBA', size, tuple(c) + (255,))


def extrude(M, depth, dx=0.75, dy=1.0):
    ext = Image.new('L', M.size, 0)
    for i in range(1, depth + 1):
        ext = ImageChops.lighter(ext, ImageChops.offset(M, int(round(i * dx)), int(round(i * dy))))
    return ext


def sparkle(layer, x, y, r, color=(255, 255, 255)):
    s = 3
    sp = Image.new('L', (r * 2 * s, r * 2 * s), 0)
    d = ImageDraw.Draw(sp)
    c = r * s
    for ang in (0, 90):
        a = math.radians(ang)
        d.polygon([(c + math.cos(a) * c, c + math.sin(a) * c), (c + math.cos(a + 1.57) * c * 0.07, c + math.sin(a + 1.57) * c * 0.07),
                   (c - math.cos(a) * c, c - math.sin(a) * c), (c - math.cos(a + 1.57) * c * 0.07, c - math.sin(a + 1.57) * c * 0.07)], fill=255)
    d.ellipse([c - c * 0.16, c - c * 0.16, c + c * 0.16, c + c * 0.16], fill=255)
    sp = sp.resize((r * 2, r * 2), Image.LANCZOS)
    glow = sp.filter(ImageFilter.GaussianBlur(r * 0.12))
    for m, k in ((glow, 0.7), (sp, 1.0)):
        im = Image.new('RGBA', sp.size, tuple(color) + (0,))
        im.putalpha(m.point(lambda v: int(v * k)))
        paste(layer, im, x - r, y - r)


def title_chrome(width):
    """80s chrome: sky above a horizon line, sunset below."""
    M, box = letters(width)
    size = M.size
    L = Image.new('RGBA', size, (0, 0, 0, 0))
    ext = extrude(M, 14)
    edge = grow(ImageChops.lighter(ext, M), 11)
    L.paste(solid(size, (255, 70, 200)), (0, 0), grow(ImageChops.lighter(ext, M), 15))     # neon line round it all
    L.paste(solid(size, (14, 6, 46)), (0, 0), edge)
    e_img, _ = face_img(M, box, [(0, (70, 30, 150)), (1, (30, 10, 80))])
    L.paste(e_img, (0, 0), ext)
    L.paste(solid(size, (14, 6, 46)), (0, 0), grow(M, 5))
    cw, ch = size
    yy = np.arange(ch, dtype=np.float32)[:, None] * np.ones((1, cw), dtype=np.float32)
    t = np.clip((yy - box[1]) / (box[3] - box[1]), 0, 1)
    split = 0.53
    top = V.ramp([(0, (18, 20, 110)), (0.45, (40, 110, 230)), (0.85, (150, 220, 255)), (1, (245, 252, 255))], np.clip(t / split, 0, 1))
    bot = V.ramp([(0, (40, 6, 70)), (0.25, (150, 24, 150)), (0.7, (255, 110, 140)), (1, (255, 214, 150))], np.clip((t - split) / (1 - split), 0, 1))
    face = np.where((t < split)[..., None], top, bot)
    line = np.exp(-((t - split) * (box[3] - box[1]) / 2.2) ** 2)
    face = face * (1 - line[..., None]) + col((255, 255, 255)) * line[..., None]
    L.paste(V.to_img(face).convert('RGBA'), (0, 0), M)
    bevel = ImageChops.subtract(M, ImageChops.offset(M, 3, 4))
    L.paste(solid(size, (255, 255, 255)), (0, 0), bevel.point(lambda v: int(v * 0.9)))
    low = ImageChops.subtract(M, ImageChops.offset(M, -3, -4))
    L.paste(solid(size, (60, 10, 90)), (0, 0), low.point(lambda v: int(v * 0.5)))
    return L, box


def title_pastel(width):
    """Soft pink-to-aqua letters, white keyline, long flat shadow."""
    M, box = letters(width)
    size = M.size
    L = Image.new('RGBA', size, (0, 0, 0, 0))
    out = grow(M, 8)
    sh = extrude(out, 34, dx=1.0, dy=1.0)
    s_img, _ = face_img(M, box, [(0, (150, 90, 235)), (1, (70, 190, 225))])
    L.paste(s_img, (0, 0), sh)
    L.paste(solid(size, (80, 40, 150)), (0, 0), grow(M, 11))
    L.paste(solid(size, (255, 255, 255)), (0, 0), out)
    f_img, _ = face_img(M, box, [(0, (255, 120, 196)), (0.5, (196, 140, 255)), (1, (90, 228, 236))])
    L.paste(f_img, (0, 0), M)
    bevel = ImageChops.subtract(M, ImageChops.offset(M, 3, 5))
    L.paste(solid(size, (255, 255, 255)), (0, 0), bevel.point(lambda v: int(v * 0.8)))
    return L, box


def title_speed(width):
    """Teal-to-magenta block letters with racing stripes cut through them."""
    M, box = letters(width)
    size = M.size
    L = Image.new('RGBA', size, (0, 0, 0, 0))
    ext = extrude(M, 22)
    edge = grow(ImageChops.lighter(ext, M), 9)
    shadow = ImageChops.offset(edge, 10, 16).filter(ImageFilter.GaussianBlur(14))
    L.paste(solid(size, (8, 4, 36)), (0, 0), shadow.point(lambda v: int(v * 0.7)))
    L.paste(solid(size, (14, 8, 52)), (0, 0), edge)
    e_img, _ = face_img(M, box, [(0, (40, 70, 190)), (0.6, (60, 30, 150)), (1, (30, 14, 90))])
    L.paste(e_img, (0, 0), ext)
    L.paste(solid(size, (14, 8, 52)), (0, 0), grow(M, 5))
    f_img, t = face_img(M, box, [(0, (232, 255, 250)), (0.28, (90, 240, 232)), (0.52, (120, 150, 255)), (0.76, (255, 96, 200)), (1, (200, 40, 150))])
    L.paste(f_img, (0, 0), M)
    # stripes: thin at the middle of the letters, wider towards the foot
    cw, ch = size
    hgt = box[3] - box[1]
    st = Image.new('L', size, 0)
    d = ImageDraw.Draw(st)
    y = box[1] + hgt * 0.50
    for i in range(6):
        th = 3 + i * 2.2
        d.rectangle([0, y, cw, y + th], fill=255)
        y += th + hgt * 0.075 - i * 1.2
    L.paste(solid(size, (14, 8, 52)), (0, 0), ImageChops.multiply(st, M))
    bevel = ImageChops.subtract(M, ImageChops.offset(M, 3, 4))
    L.paste(solid(size, (255, 255, 255)), (0, 0), bevel.point(lambda v: int(v * 0.85)))
    return L, box


def put_title(canvas, layer, box, cx, top, glow=(255, 70, 190), glow_k=0.32, dark_k=0.5):
    x = int(cx - (box[0] + box[2]) / 2)
    y = int(top - box[1])
    a = layer.split()[3]
    for c, r, k in (((30, 6, 60), 22, dark_k), (glow, 46, glow_k)):
        g = Image.new('RGBA', layer.size, tuple(c) + (0,))
        g.putalpha(a.filter(ImageFilter.GaussianBlur(r)).point(lambda v: int(min(255, v * 1.4) * k)))
        paste(canvas, g, x, y)
    paste(canvas, layer, x, y)
    return x + box[0], y + box[1], x + box[2], y + box[3]


def spaced_line(canvas, text, cx, cy, size=40, tracking=22, color=(255, 255, 255), glow=None, shadow=(40, 10, 90), font=F_TAG):
    im = text_img(text, size, font, color, tracking)
    x, y = int(cx - im.width / 2), int(cy - im.height / 2)
    if shadow is not None:
        sh = text_img(text, size, font, shadow, tracking)
        paste(canvas, sh, x + 3, y + 3)
    if glow is not None:
        g = Image.new('RGBA', (im.width + 80, im.height + 80), tuple(glow) + (0,))
        a = Image.new('L', g.size, 0)
        a.paste(im.split()[3], (40, 40))
        g.putalpha(a.filter(ImageFilter.GaussianBlur(9)).point(lambda v: int(min(255, v * 1.6))))
        paste(canvas, g, x - 40, y - 40)
    paste(canvas, im, x, y)
    return im.size


# ------------------------------------------------------------------ retro desktop windows
def bevel_box(d, box, light=(255, 255, 255), dark=(96, 96, 110), w=2):
    x0, y0, x1, y1 = box
    for i in range(w):
        d.line([x0 + i, y1 - i, x0 + i, y0 + i, x1 - i, y0 + i], fill=light)
        d.line([x1 - i, y0 + i, x1 - i, y1 - i, x0 + i, y1 - i], fill=dark)


def window(content, title, w, bar=((255, 110, 190), (120, 96, 240)), body=(206, 204, 222), tsize=20):
    """A late-90s desktop window with a picture in it."""
    cw = w - 12
    chh = int(content.height * cw / content.width)
    pic = content.convert('RGB').resize((cw, chh), Image.LANCZOS)
    bar_h = 32
    win = Image.new('RGBA', (w, chh + bar_h + 14), tuple(body) + (255,))
    d = ImageDraw.Draw(win)
    bevel_box(d, (0, 0, w - 1, win.height - 1))
    grad = V.ramp([(0, bar[0]), (1, bar[1])], np.linspace(0, 1, w - 8, dtype=np.float32)[None, :] * np.ones((bar_h - 6, 1), dtype=np.float32))
    win.paste(V.to_img(grad), (4, 4))
    paste(win, text_img(title, tsize, F_PIX, (255, 255, 255)), 12, 4 + (bar_h - 6 - tsize) // 2 - 1)
    bx = w - 10
    for sym in ('x', 'o', '_'):
        bx -= 24
        d.rectangle([bx, 8, bx + 20, 8 + 18], fill=tuple(body))
        bevel_box(d, (bx, 8, bx + 20, 26), w=1)
        if sym == 'x':
            d.line([bx + 6, 13, bx + 14, 21], fill=(40, 30, 70), width=2)
            d.line([bx + 14, 13, bx + 6, 21], fill=(40, 30, 70), width=2)
        elif sym == 'o':
            d.rectangle([bx + 5, 12, bx + 15, 21], outline=(40, 30, 70), width=2)
        else:
            d.line([bx + 5, 21, bx + 14, 21], fill=(40, 30, 70), width=2)
    win.paste(pic, (6, bar_h + 4))
    bevel_box(d, (5, bar_h + 3, w - 6, bar_h + 4 + chh), light=(96, 96, 110), dark=(255, 255, 255), w=1)
    return win


def dialog(title, lines, w=470, button='OK', bar=((90, 220, 230), (120, 96, 240)), body=(206, 204, 222)):
    h = 74 + 30 * len(lines) + 52
    win = Image.new('RGBA', (w, h), tuple(body) + (255,))
    d = ImageDraw.Draw(win)
    bevel_box(d, (0, 0, w - 1, h - 1))
    grad = V.ramp([(0, bar[0]), (1, bar[1])], np.linspace(0, 1, w - 8, dtype=np.float32)[None, :] * np.ones((26, 1), dtype=np.float32))
    win.paste(V.to_img(grad), (4, 4))
    paste(win, text_img(title, 20, F_PIX, (255, 255, 255)), 12, 6)
    d.rectangle([w - 32, 8, w - 12, 26], fill=tuple(body))
    bevel_box(d, (w - 32, 8, w - 12, 26), w=1)
    d.line([w - 26, 13, w - 18, 21], fill=(40, 30, 70), width=2)
    d.line([w - 18, 13, w - 26, 21], fill=(40, 30, 70), width=2)
    # a little crystal for an icon
    cx, cy = 52, 44 + 15 * len(lines) + 8
    d.polygon([(cx, cy - 26), (cx + 17, cy - 6), (cx, cy + 26), (cx - 17, cy - 6)], fill=(110, 200, 255), outline=(40, 60, 150))
    d.polygon([(cx, cy - 26), (cx + 17, cy - 6), (cx, cy - 2)], fill=(200, 240, 255))
    d.line([(cx - 17, cy - 6), (cx + 17, cy - 6)], fill=(40, 60, 150))
    for i, ln in enumerate(lines):
        paste(win, text_img(ln, 22, F_PIX, (40, 30, 70)), 92, 44 + 30 * i)
    bw = 110
    bx, by = (w - bw) // 2, h - 46
    d.rectangle([bx, by, bx + bw, by + 30], fill=tuple(body))
    bevel_box(d, (bx, by, bx + bw, by + 30))
    b = text_img(button, 20, F_PIX, (40, 30, 70))
    paste(win, b, bx + (bw - b.width) // 2, by + 4)
    return win


def tilt(im, deg):
    return im.rotate(deg, resample=Image.BICUBIC, expand=True)


def shot(name, box=None, tint=None, k=0.22):
    """A screenshot from art-src, optionally cropped (fractions) and washed towards the palette."""
    im = Image.open(os.path.join(V.ART, name)).convert('RGB')
    if box:
        w, h = im.size
        im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    if tint:
        a = np.asarray(im, dtype=np.float32) / 255.0
        lum = (a * np.array([0.299, 0.587, 0.114])).sum(axis=2)[..., None]
        duo = col(tint[0]) / 255.0 + (col(tint[1]) / 255.0 - col(tint[0]) / 255.0) * lum
        a = a * (1 - k) + duo * k
        a = (a - 0.5) * 1.06 + 0.52
        im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), 'RGB')
    return im


# ------------------------------------------------------------------ finishing
def finish(arr, rng, bloom=0.34, vignette=0.34, grain=3.2, aberr=0):
    bright = np.clip(arr - 170, 0, 255) * 1.6
    arr = V.add(arr, V.blur_arr(bright, 18), bloom)
    if aberr:
        r = np.roll(arr[..., 0], -aberr, axis=1)
        b = np.roll(arr[..., 2], aberr, axis=1)
        arr = np.dstack([r, arr[..., 1], b])
    v = 1 - vignette * np.clip(np.hypot((XX - W / 2) / (W / 2), (YY - H / 2) / (H / 2)) - 0.45, 0, 1) ** 1.5
    arr = arr * v[..., None]
    return np.clip(arr + rng.normal(0, grain, (H, W)).astype(np.float32)[..., None], 0, 255)


# ------------------------------------------------------------------ 1. grid sunset
def figure_centered(canvas, name, h, cx, bottom, side, **kw):
    fig, _ = cut2(name, h, **(kw.get('cut') or {}))
    return figure(canvas, name, h, int(cx - fig.width / 2), bottom, side, **kw)


def scene_grid(seed=21):
    rng = np.random.default_rng(seed)
    hz = int(H * 0.615)
    arr = vgrad([(0, (8, 4, 36)), (0.30, (40, 10, 92)), (0.58, (124, 22, 140)), (0.80, (230, 54, 134)),
                 (0.93, (255, 120, 100)), (1, (255, 186, 120))], 0, hz)
    arr = stars(arr, rng, 420, hz * 0.62)
    arr = retro_sun(arr, W // 2, hz - 56, 266, [(0, (255, 242, 130)), (0.40, (255, 172, 90)), (0.70, (255, 84, 130)), (1, (222, 44, 170))],
                    horizon=hz, slits=11, start=0.30)
    fill = [(0, (64, 16, 112)), (1, (22, 6, 58))]
    arr = mountain(arr, ridge(rng, -60, 780, hz, 176, peak=260), hz, fill, edge=(255, 70, 214), mesh=44)
    arr = mountain(arr, ridge(rng, 1060, W + 60, hz, 196, peak=1570), hz, fill, edge=(70, 230, 255), mesh=44)
    arr = grid_floor(arr, hz, W / 2, [(0, (76, 14, 112)), (0.12, (30, 6, 62)), (1, (8, 2, 24))], (255, 56, 214), cell_px=W * 0.15, zscale=1.5)
    hl = np.exp(-((YY - hz) / 1.8) ** 2)
    arr = neon(arr, hl, (110, 236, 255), k=0.7, mix=0.6)
    pm = palms_mask(rng, [((30, 770), (150, 236), -46, 206), ((262, 780), (336, 372), 22, 150),
                          ((1812, 770), (1692, 236), 46, 206), ((1580, 780), (1506, 372), -22, 150)])
    arr = arr * (1 - pm[..., None]) + col((12, 4, 34)) * pm[..., None]
    canvas = to_rgba(arr)
    figure_centered(canvas, 'Nomura_illustration.png', 404, W / 2, H + 20, +1, cut=dict(crop=(0, 0, 1, 0.852)),
                    light=dict(bright=0.94, wash_k=0.10, key=(1.0, 0.60, 0.50), fill=(1.0, 0.45, 0.75), fade=0.20, fade_k=0.9),
                    halo=dict(r=18, k=0.7))
    layer, box = title_chrome(800)
    x0, y0, x1, y1 = put_title(canvas, layer, box, W / 2 - 6, 40, glow=(255, 60, 200), glow_k=0.42)
    sparkle(canvas, x0 + 26, y0 + 14, 46)
    sparkle(canvas, x1 - 40, y0 + 40, 30)
    spaced_line(canvas, 'XI : FOREVER OFFLINE', W / 2, y1 + 50, size=38, tracking=24, color=(214, 252, 255), glow=(40, 220, 240), shadow=(30, 6, 70))
    return V.to_img(finish(to_arr(canvas), rng))


SCENES = {'grid': scene_grid}


# ------------------------------------------------------------------ 2. neon night strip
CITY_SIGNS = ['JEUNO', 'BASTOK', 'WINDURST', "SAN D'ORIA", 'NORG', 'KAZHAM', 'SELBINA', 'MHAURA', 'RABAO']
NEON = {'pink': (255, 50, 170), 'teal': (40, 236, 226), 'gold': (255, 196, 70), 'violet': (170, 90, 255)}


def deco_strip(rng, hz, clear=(0, 0)):
    """A row of art-deco hotel fronts at night. Returns (picture, {neon colour: mask})."""
    s = 2
    pic = Image.new('RGBA', (W * s, H * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(pic)
    tubes = {k: Image.new('L', (W * s, H * s), 0) for k in NEON}
    td = {k: ImageDraw.Draw(v) for k, v in tubes.items()}
    bodies = [(60, 36, 112), (40, 60, 122), (90, 38, 108), (36, 72, 114), (72, 52, 132), (104, 46, 96)]
    names = list(CITY_SIGNS)
    rng.shuffle(names)
    x, i = -70, 0
    while x < W + 40:
        bw = int(rng.integers(196, 300))
        xc = x + bw / 2
        low = 1 - 0.50 * math.exp(-((xc - W / 2) / 470.0) ** 2)
        bh = int(rng.integers(190, 300) * low)
        top = hz - bh
        body = bodies[i % len(bodies)]
        trim, trim2 = [('pink', 'teal'), ('teal', 'gold'), ('gold', 'pink'), ('violet', 'teal')][i % 4]
        d.rectangle([x * s, top * s, (x + bw) * s, hz * s], fill=body + (255,))
        # lighter bands and the stepped crown
        for k in range(3):
            inset = 16 + k * 20
            d.rectangle([(x + inset) * s, (top - 10 * (k + 1)) * s, (x + bw - inset) * s, (top - 10 * k) * s],
                        fill=tuple(min(255, c + 14 * (k + 1)) for c in body) + (255,))
        fw, fh = int(rng.integers(30, 44)), int(rng.integers(44, 86) * low)
        d.rectangle([(xc - fw / 2) * s, (top - 30 - fh) * s, (xc + fw / 2) * s, (hz - 46) * s], fill=tuple(min(255, c + 30) for c in body) + (255,))
        for off in (-fw * 0.22, 0, fw * 0.22):
            td[trim].line([(xc + off) * s, (top - 26 - fh) * s, (xc + off) * s, (top + 40) * s], fill=255, width=2 * s)
        td[trim2].line([(xc - fw / 2 - 5) * s, (top - 30 - fh) * s, (xc + fw / 2 + 5) * s, (top - 30 - fh) * s], fill=255, width=3 * s)
        # floors: eyebrow ledges and windows
        floors = max(1, (bh - 70) // 46)
        for f in range(floors):
            fy = top + 20 + f * 46
            d.rectangle([x * s, (fy + 34) * s, (x + bw) * s, (fy + 38) * s], fill=tuple(min(255, c + 34) for c in body) + (255,))
            nwin = max(2, (bw - 60) // 34)
            for wv in range(nwin):
                wx = x + 18 + wv * (bw - 36) / nwin
                if abs(wx + 9 - xc) < fw / 2 + 8:
                    continue
                r = rng.random()
                c = (255, 214, 140) if r < 0.30 else (120, 240, 235) if r < 0.42 else (255, 130, 200) if r < 0.50 else (18, 10, 46)
                d.rectangle([wx * s, fy * s, (wx + 18) * s, (fy + 26) * s], fill=c + (255,))
        td[trim].line([(x + 2) * s, top * s, (x + bw - 2) * s, top * s], fill=255, width=3 * s)
        td[trim2].line([(x + 2) * s, (top + 12) * s, (x + bw - 2) * s, (top + 12) * s], fill=255, width=2 * s)
        # street level: a lit lobby under a striped awning
        d.rectangle([x * s, (hz - 46) * s, (x + bw) * s, hz * s], fill=(26, 14, 56, 255))
        d.rectangle([(x + 22) * s, (hz - 36) * s, (x + bw - 22) * s, hz * s], fill=(255, 196, 130, 255))
        for k in range(0, bw - 44, 22):
            d.rectangle([(x + 22 + k) * s, (hz - 36) * s, (x + 22 + k + 6) * s, hz * s], fill=(40, 20, 70, 255))
        for k in range(0, bw, 20):
            d.polygon([((x + k) * s, (hz - 58) * s), ((x + k + 20) * s, (hz - 58) * s), ((x + k + 20) * s, (hz - 46) * s), ((x + k) * s, (hz - 46) * s)],
                      fill=((255, 90, 180, 255) if (k // 20) % 2 else (246, 240, 255, 255)))
        td[trim2].line([x * s, (hz - 59) * s, (x + bw) * s, (hz - 59) * s], fill=255, width=2 * s)
        # the hotel's name in tube lettering on the roof
        name = names[i % len(names)]
        f = ImageFont.truetype(F_TAG, 30 * s)
        m = V.text_mask(name, f, tracking=5 * s)
        if m.width > (bw - 30) * s:
            m = m.resize(((bw - 30) * s, int(m.height * (bw - 30) * s / m.width)), Image.LANCZOS)
        sx, sy = int(xc * s - m.width / 2), int((top - 46 - fh) * s - m.height)
        if (sy > 300 * s or abs(xc - W / 2) > 560) and not (clear[0] < xc < clear[1]):
            col_name = trim2 if trim2 != 'violet' else 'pink'
            tubes[col_name].paste(ImageChops.lighter(tubes[col_name].crop((sx, sy, sx + m.width, sy + m.height)), m), (sx, sy))
            for px in (0.2, 0.8):
                d.line([(sx + m.width * px), sy + m.height, (sx + m.width * px), (top - 30 - fh) * s + 4], fill=(30, 16, 60, 255), width=2 * s)
        x += bw + int(rng.integers(0, 3))
        i += 1
    pic = pic.resize((W, H), Image.LANCZOS)
    return pic, {k: mask_arr(v.resize((W, H), Image.LANCZOS)) for k, v in tubes.items()}


def title_neon(arr, width, cx, top):
    """XIFO as a neon sign: a pink tube round each letter and a teal one inside it."""
    M, box = letters(width)
    full = Image.new('L', (W, H), 0)
    x, y = int(cx - (box[0] + box[2]) / 2), int(top - box[1])
    full.paste(M, (x, y))
    outer = mask_arr(ImageChops.subtract(grow(full, 4), shrink(full, 3)))
    inner = mask_arr(ImageChops.subtract(shrink(full, 15), shrink(full, 20)))
    back = mask_arr(grow(full, 4))
    arr = arr * (1 - gblur(back, 26)[..., None] * 0.55)
    arr = arr * (1 - back[..., None] * 0.80) + col((18, 6, 46)) * back[..., None] * 0.80
    arr = glow_add(arr, back, (255, 40, 170), 0.5, radii=((70, 0.55),))
    arr = neon(arr, inner, NEON['teal'], k=0.85, mix=0.70)
    arr = neon(arr, outer, NEON['pink'], core=(255, 236, 246), k=1.15, mix=0.80)
    return arr, (x + box[0], y + box[1], x + box[2], y + box[3])


def billboard(pic_name, crop, lines, w=250):
    """A roof billboard: a screenshot over two lines of tube lettering. Returns (RGBA, {colour: mask})."""
    im = shot(pic_name, crop, tint=((40, 10, 90), (255, 220, 230)), k=0.18)
    ph = int(w * 0.62)
    im = im.resize((w - 16, int(im.height * (w - 16) / im.width)), Image.LANCZOS).crop((0, 0, w - 16, ph))
    h = ph + 16 + 30 * len(lines) + 10
    bb = Image.new('RGBA', (w, h + 56), (0, 0, 0, 0))
    d = ImageDraw.Draw(bb)
    for px in (0.24, 0.76):
        d.rectangle([w * px - 4, h - 4, w * px + 4, h + 56], fill=(26, 14, 54, 255))
    d.rectangle([0, 0, w - 1, h - 1], fill=(16, 8, 40, 255), outline=(70, 50, 120, 255), width=3)
    bb.paste(im, (8, 8))
    tubes = {k: np.zeros((bb.height, bb.width), dtype=np.float32) for k in NEON}
    for i, (text, colour, size) in enumerate(lines):
        m = V.text_mask(text, ImageFont.truetype(F_TAG, size), tracking=3)
        if m.width > w - 24:
            m = m.resize((w - 24, int(m.height * (w - 24) / m.width)), Image.LANCZOS)
        lay = Image.new('L', bb.size, 0)
        lay.paste(m, ((w - m.width) // 2, ph + 16 + 30 * i + (24 - m.height) // 2))
        tubes[colour] = np.maximum(tubes[colour], mask_arr(lay))
    frame = Image.new('L', bb.size, 0)
    ImageDraw.Draw(frame).rectangle([3, 3, w - 4, h - 4], outline=255, width=3)
    tubes['violet'] = np.maximum(tubes['violet'], mask_arr(frame))
    return bb, tubes


def scene_night(seed=34):
    rng = np.random.default_rng(seed)
    hz = int(H * 0.705)
    arr = vgrad([(0, (5, 5, 30)), (0.40, (20, 10, 68)), (0.72, (74, 20, 118)), (0.92, (180, 44, 140)), (1, (236, 80, 150))], 0, hz)
    arr = stars(arr, rng, 520, hz * 0.7, k=0.9)
    # a thin moon
    mx, my, mr = 1548, 96, 44
    moon = (1 - V.smoothstep(mr - 1.5, mr + 1.5, np.hypot(XX - mx, YY - my))) * V.smoothstep(mr - 1.5, mr + 1.5, np.hypot(XX - mx - 20, YY - my + 10) + 6)
    arr = neon(arr, moon, (255, 220, 240), core=(255, 246, 232), k=0.5, mix=0.9)
    # far skyline
    far = Image.new('L', (W, H), 0)
    fd = ImageDraw.Draw(far)
    x = -20
    while x < W:
        bw = int(rng.integers(40, 110))
        bh = int(60 + rng.random() ** 1.6 * 230 * (1 - 0.55 * math.exp(-((x - W / 2) / 520.0) ** 2)))
        fd.rectangle([x, hz - bh, x + bw, hz], fill=255)
        x += bw + int(rng.integers(0, 14))
    fa = mask_arr(far)
    fcol = V.ramp([(0, (34, 14, 84)), (1, (110, 30, 120))], np.clip((YY - (hz - 300)) / 300.0, 0, 1))
    arr = arr * (1 - fa[..., None]) + fcol * fa[..., None]
    dots = (rng.random((H, W)) > 0.9972) * fa * (YY < hz - 8)
    arr = glow_add(arr, dots.astype(np.float32), (255, 210, 150), 1.0, radii=((2.2, 2.2),))
    # the strip itself
    strip, tubes = deco_strip(rng, hz, clear=(250, 600))
    canvas = to_rgba(arr)
    canvas.alpha_composite(strip)
    arr = to_arr(canvas)
    arr = arr * (1 - 0.30 * np.clip((hz - YY) / 380.0, 0, 1)[..., None] * mask_arr(strip.split()[3])[..., None])   # darker towards the roofs
    bb, btubes = billboard('Naja.bmp', (0.10, 0.02, 0.90, 0.62), [('NOW HIRING', 'gold', 24), ("SALAHEEM'S SENTINELS", 'pink', 18)], w=186)
    bx, by = 326, hz - 132 - bb.height + 56
    canvas = to_rgba(arr)
    paste(canvas, bb, bx, by)
    arr = to_arr(canvas)
    for k in tubes:                                   # no roof trim glowing through the billboard
        tubes[k][by:by + bb.height - 56, bx:bx + bb.width] = 0
    for k, m in btubes.items():
        full = np.zeros((H, W), dtype=np.float32)
        full[by:by + m.shape[0], bx:bx + m.shape[1]] = m[:H - by, :W - bx]
        tubes[k] = np.maximum(tubes[k], full)
    for k, m in tubes.items():
        arr = neon(arr, m, NEON[k], k=0.8, mix=0.62)
    # palms on the pavement, lit from below
    pm = palms_mask(rng, [((150, hz + 6), (196, 262), 26, 132), ((690, hz + 6), (664, 366), -14, 90), ((900, hz + 6), (916, 376), 8, 84),
                          ((1250, hz + 6), (1282, 344), 14, 98), ((1700, hz + 6), (1660, 250), -24, 136)])
    pcol = V.ramp([(0, (10, 5, 30)), (0.55, (40, 12, 70)), (1, (190, 50, 150))], np.clip((YY - 200) / (hz - 200.0), 0, 1))
    pcol = pcol * 0.75 + col((30, 150, 160)) * 0.25 * np.clip((YY - 300) / 200.0, 0, 1)[..., None]
    arr = arr * (1 - pm[..., None]) + pcol * pm[..., None]
    # pavement, then the wet road with the strip mirrored in it
    side = ((YY >= hz) & (YY < hz + 16)).astype(np.float32)
    arr = arr * (1 - side[..., None]) + col((92, 60, 130)) * side[..., None]
    rd = np.clip((YY - (hz + 16)) / (H - hz - 16.0), 0, 1)
    src_y = np.clip(hz - (YY - hz - 16) * 1.25, 0, H - 1).astype(int)
    wob = (V.noise(W, H, 70, 5, rng, 3) - 0.5) * 22 * (0.4 + rd)
    src_x = np.clip(XX + wob, 0, W - 1).astype(int)
    refl = arr[src_y, src_x]
    refl = np.asarray(V.to_img(refl).filter(ImageFilter.GaussianBlur(3)).filter(ImageFilter.BoxBlur(1)), dtype=np.float32)
    rip = V.smoothstep(0.38, 0.62, V.noise(W, H, 120, 3.0, rng, 3))
    road = col((10, 5, 28)) * (1 - 0.0 * rd[..., None]) + refl * (0.62 - 0.30 * rd)[..., None] * (0.55 + 0.45 * rip)[..., None]
    onroad = (YY >= hz + 16)[..., None]
    arr = np.where(onroad, road, arr)
    dash = ((np.abs(YY - (hz + 112)) < 5) & (((XX + 40) % 190) < 104)).astype(np.float32)
    arr = arr * (1 - dash[..., None] * 0.7) + col((255, 214, 120)) * dash[..., None] * 0.7
    kerb = np.exp(-((YY - (hz + 16)) / 1.6) ** 2)
    arr = V.add(arr, kerb[..., None] * col((255, 150, 220)), 0.5)
    arr, (x0, y0, x1, y1) = title_neon(arr, 770, W / 2 + 14, 50)
    canvas = to_rgba(arr)
    canvas = V.sign(canvas, 'XI: FOREVER OFFLINE', W // 2 + 4, y1 + 58, size=42, tracking=13)
    lk = dict(bright=1.12, lo=(0.10, 0.04, 0.26), hi=(1.0, 0.90, 1.0), tint=(0.96, 0.90, 1.0), tone=0.16, key=(1.0, 0.34, 0.70),
              fill=(0.08, 0.88, 0.95), fill_k=0.70, wash=(1.0, 0.24, 0.62), wash_k=0.16, fade=0.14, fade_col=(0.03, 0.01, 0.09), sat=1.2)
    figure(canvas, 'ninja', 610, 24, H + 26, +1, light=lk, halo=dict(r=18, k=0.75, color=(6, 2, 22)))
    figure(canvas, 'samurai', 620, 1396, H + 30, -1, cut=dict(fx=[(0.66, 0.30, 1.0, 0.80)]), light=dict(lk, fx_color=(255, 90, 200)),
           halo=dict(r=18, k=0.75, color=(6, 2, 22)))
    return V.to_img(finish(to_arr(canvas), rng, bloom=0.40, vignette=0.40))


SCENES['night'] = scene_night


# ------------------------------------------------------------------ 3. pastel windows
def shapes_layer(rng):
    s = 2
    L = Image.new('RGBA', (W * s, H * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)

    def tri(cx, cy, r, rot, c, w=5):
        pts = [(cx + r * math.cos(math.radians(rot + a)), cy + r * math.sin(math.radians(rot + a))) for a in (-90, 30, 150)]
        d.line([(x * s, y * s) for x, y in pts + pts[:1]], fill=c, width=w * s, joint='curve')

    tri(170, 150, 62, 12, (60, 214, 226, 255))
    tri(206, 176, 62, 12, (255, 255, 255, 255), w=3)
    tri(900, 96, 40, -20, (255, 236, 120, 255))
    tri(1790, 420, 52, 30, (120, 84, 236, 255))
    d.ellipse([(840 - 34) * s, (300 - 34) * s, (840 + 34) * s, (300 + 34) * s], outline=(255, 110, 190, 255), width=6 * s)
    d.ellipse([(60 - 22) * s, (330 - 22) * s, (60 + 22) * s, (330 + 22) * s], fill=(255, 236, 120, 255))
    for zx, zy, c in ((640, 50, (120, 84, 236, 255)), (940, 420, (60, 214, 226, 255))):
        pts = [((zx + i * 22) * s, (zy + (14 if i % 2 else -14)) * s) for i in range(7)]
        d.line(pts, fill=c, width=6 * s, joint='curve')
    for gx, gy in ((300, 40), (880, 180)):
        for i in range(5):
            for j in range(4):
                d.ellipse([(gx + i * 20 - 3) * s, (gy + j * 20 - 3) * s, (gx + i * 20 + 3) * s, (gy + j * 20 + 3) * s], fill=(255, 255, 255, 235))
    return L.resize((W, H), Image.LANCZOS)


def ground_shadow(canvas, cx, y, rx, ry=None, k=0.42, color=(120, 50, 170)):
    ry = ry or max(8, int(rx * 0.16))
    sh = Image.new('L', (rx * 2 + 80, ry * 2 + 80), 0)
    ImageDraw.Draw(sh).ellipse([40, 40, 40 + rx * 2, 40 + ry * 2], fill=255)
    sh = sh.filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * k))
    lay = Image.new('RGBA', sh.size, tuple(color) + (0,))
    lay.putalpha(sh)
    paste(canvas, lay, cx - rx - 40, y - ry - 40)


def scene_dream(seed=55):
    rng = np.random.default_rng(seed)
    hz = int(H * 0.655)
    arr = vgrad([(0, (104, 220, 232)), (0.42, (170, 190, 248)), (0.78, (255, 166, 214)), (1, (255, 216, 190))], 0, hz)
    cl = V.noise(W, H, 360, 110, rng, 5)
    puff = V.smoothstep(0.52, 0.74, cl) * V.smoothstep(0.02, 0.2, YY / hz) * (1 - V.smoothstep(0.62, 0.95, YY / hz))
    arr = arr * (1 - puff[..., None] * 0.62) + col((255, 244, 252)) * puff[..., None] * 0.62
    arr = retro_sun(arr, 934, hz - 40, 240, [(0, (255, 252, 206)), (0.5, (255, 196, 184)), (1, (255, 112, 190))], horizon=hz, slits=9,
                    glow=(255, 150, 200), glow_k=0.42, start=0.36)
    # checkerboard floor
    t, wx, wz, px_x, px_z = floor_coords(hz, W * 0.5, W * 0.085, zscale=1.9)
    chk = ((np.floor(wx) + np.floor(wz)) % 2).astype(np.float32)
    soft = V.smoothstep(0.02, 0.22, t)
    chk = 0.5 + (chk - 0.5) * soft
    tile = col((255, 104, 186)) * chk[..., None] + col((252, 238, 255)) * (1 - chk[..., None])
    haze = V.smoothstep(0.0, 0.5, t)[..., None]
    floor = tile * haze + col((255, 206, 214)) * (1 - haze)
    floor = floor * (0.82 + 0.18 * t[..., None])
    arr = np.where((YY > hz)[..., None], floor, arr)
    hl = np.exp(-((YY - hz) / 1.6) ** 2)
    arr = arr * (1 - hl[..., None] * 0.8) + col((255, 255, 255)) * hl[..., None] * 0.8
    pm = palms_mask(rng, [((-30, 800), (96, 220), -40, 200), ((1880, 800), (1774, 250), 40, 186)])
    pcol = V.ramp([(0, (38, 150, 172)), (1, (120, 70, 190))], np.clip(YY / H, 0, 1))
    arr = arr * (1 - pm[..., None]) + pcol * pm[..., None]
    canvas = to_rgba(arr)
    canvas.alpha_composite(shapes_layer(rng))
    duo = ((70, 20, 120), (255, 232, 240))
    w1 = tilt(window(shot('Chocobo_mount.png', (0.10, 0.04, 0.90, 0.96), duo), 'chocobo.avi', 384, bar=((90, 220, 230), (120, 96, 240))), 4)
    w2 = tilt(window(shot('VoraciousResurgence_png_jpgcopy.jpg', (0.20, 0.0, 0.84, 1.0), duo), 'kupo.bmp', 430), -4)
    w3 = tilt(window(shot('Star_Onion_Brigade.jpg', None, duo), 'star_onions.jpg', 372, bar=((255, 196, 90), (255, 110, 190))), 3)
    dg = tilt(dialog('vanadiel.exe', ['Connection lost?', 'No. You are FOREVER OFFLINE.']), -2)
    shadowed(canvas, w1, 1392, 36, color=(90, 40, 150))
    shadowed(canvas, w2, 1010, 120, color=(90, 40, 150))
    shadowed(canvas, w3, 1436, 318, color=(90, 40, 150))
    shadowed(canvas, dg, 1052, 470, color=(90, 40, 150))
    layer, box = title_pastel(700)
    x0, y0, x1, y1 = put_title(canvas, layer, box, 500, 64, glow=(255, 255, 255), glow_k=0.30, dark_k=0.0)
    spaced_line(canvas, 'XI : FOREVER OFFLINE', 508, y1 + 66, size=36, tracking=20, color=(96, 56, 200), shadow=(255, 255, 255))
    spaced_line(canvas, '永遠にオフライン', 508, y1 + 122, size=40, tracking=12, color=(236, 44, 156), shadow=(255, 255, 255), font=F_PIX)
    day = dict(bright=1.06, lo=(0.34, 0.20, 0.52), hi=(1.0, 0.98, 1.0), tint=(1.0, 0.97, 0.99), tone=0.10, key=(1.0, 0.86, 0.94),
               fill=(0.62, 0.90, 1.0), fill_k=0.30, wash=(1.0, 0.6, 0.8), wash_k=0.08, rim=0.6, fade=0.10, fade_k=0.0, sat=1.18)
    soft = dict(r=14, k=0.30, color=(150, 80, 200), offset=(0, 4))
    ground_shadow(canvas, 330, H - 26, 300)
    figure(canvas, '6ff391e31afa64410ba3031178c152f4.jpg', 300, 70, H - 6, +1, cut=dict(thr=0.36, hole_r=4), light=day, halo=soft)
    ground_shadow(canvas, 640, H - 30, 110)
    figure(canvas, 'ca-taru-m', 262, 520, H - 12, +1, cut=dict(crop=(0, 0, 0.57, 1)), light=day, halo=soft)
    return V.to_img(finish(to_arr(canvas), rng, bloom=0.16, vignette=0.14, grain=2.6, aberr=1))


SCENES['dream'] = scene_dream


# ------------------------------------------------------------------ 4. VHS sunset road
def vhs(arr, rng, date='MAY 16 2002'):
    r = np.roll(arr[..., 0], -3, axis=1)
    b = np.roll(arr[..., 2], 3, axis=1)
    arr = np.dstack([r, arr[..., 1], b])
    arr = arr * (1 - 0.06 * (0.5 + 0.5 * np.sin(YY * (2 * math.pi / 6.0))))[..., None]
    # a tracking band low on the picture, and head-switching noise along the bottom edge
    out = arr.copy()
    for y0, y1, amp in ((H - 112, H - 92, 34), (H - 12, H, 90)):
        for y in range(y0, y1):
            sh = int(amp * (rng.random() - 0.3) * math.sin(math.pi * (y - y0) / max(1, y1 - y0 - 1)) ) if amp < 60 else int(rng.integers(-amp, amp))
            out[y] = np.roll(arr[y], sh, axis=0)
        speck = (rng.random((y1 - y0, W)) > 0.93).astype(np.float32)
        speck = np.asarray(Image.fromarray((speck * 255).astype(np.uint8), 'L').filter(ImageFilter.BoxBlur(3)).resize((W, y1 - y0)), dtype=np.float32) / 255.0
        out[y0:y1] = np.clip(out[y0:y1] * 0.86 + speck[..., None] * 380, 0, 255)
    canvas = to_rgba(out)
    for text, x, y, size in (('PLAY', 70, 44, 46), ('SP', W - 150, 44, 46), ('PM 11:11', 70, H - 190, 40), (date, 70, H - 146, 40)):
        for dx, c in ((-3, (255, 60, 90, 150)), (3, (60, 220, 255, 150)), (0, (255, 255, 255, 240))):
            im = text_img(text, size, F_PIX, c[:3])
            im.putalpha(im.split()[3].point(lambda v, a=c[3]: int(v * a / 255)))
            paste(canvas, im, x + dx, y)
    d = ImageDraw.Draw(canvas)
    d.polygon([(196, 52), (196, 88), (228, 70)], fill=(255, 255, 255, 240))
    return to_arr(canvas)


def scene_vhs(seed=77):
    rng = np.random.default_rng(seed)
    hz = int(H * 0.60)
    vpx = W / 2
    arr = vgrad([(0, (12, 26, 84)), (0.28, (56, 46, 150)), (0.55, (186, 66, 170)), (0.80, (255, 122, 120)), (1, (255, 208, 138))], 0, hz)
    arr = stars(arr, rng, 240, hz * 0.4, k=0.7)
    cl = V.noise(W, H, 460, 34, rng, 4)
    streak = V.smoothstep(0.52, 0.70, cl) * V.smoothstep(0.05, 0.3, YY / hz) * (1 - V.smoothstep(0.75, 0.98, YY / hz))
    ccol = V.ramp([(0, (110, 70, 190)), (0.6, (255, 130, 170)), (1, (255, 200, 150))], np.clip(YY / hz, 0, 1))
    arr = arr * (1 - streak[..., None] * 0.6) + ccol * streak[..., None] * 0.6
    arr = retro_sun(arr, vpx, hz - 30, 214, [(0, (255, 246, 150)), (0.42, (255, 176, 96)), (0.72, (255, 90, 126)), (1, (226, 50, 164))],
                    horizon=hz, slits=10, start=0.34)
    far = [(0, (150, 70, 160)), (1, (96, 40, 128))]
    arr = mountain(arr, ridge(rng, -80, 700, hz, 120, peak=180, step=70), hz, far)
    arr = mountain(arr, ridge(rng, 1140, W + 80, hz, 134, peak=1640, step=70), hz, far)
    arr = grid_floor(arr, hz, vpx, [(0, (90, 30, 120)), (0.14, (44, 14, 80)), (1, (16, 6, 40))], (60, 220, 235), cell_px=W * 0.15, zscale=1.5, k=0.45)
    # the road
    t = np.clip((YY - hz) / (H - hz), 0, 1)
    half = 5 + (W * 0.285) * t
    dxr = np.abs(XX - vpx)
    road = np.clip((half - dxr) / 1.5, 0, 1) * (YY > hz)
    rcol = V.ramp([(0, (70, 40, 100)), (0.2, (40, 24, 70)), (1, (18, 10, 40))], t)
    arr = arr * (1 - road[..., None]) + rcol * road[..., None]
    edge = np.clip(1 - np.abs(dxr - half) / (1.2 + 3.2 * t), 0, 1) * (YY > hz)
    edge2 = np.clip(1 - np.abs(dxr - half * 0.90) / (0.8 + 1.6 * t), 0, 1) * (YY > hz)
    arr = neon(arr, edge, (255, 50, 180), k=0.8, mix=0.6)
    arr = V.add(arr, edge2[..., None] * col((255, 255, 255)), 0.55)
    _, _, wz, _, px_z = floor_coords(hz, vpx, W * 0.15, zscale=1.5)
    dash = (((wz * 0.9) % 1.0) < 0.42) * np.clip((half * 0.022 + 0.8 - dxr) / 1.2, 0, 1) * (YY > hz + 2)
    arr = arr * (1 - dash[..., None]) + col((255, 232, 150)) * dash[..., None]
    hl = np.exp(-((YY - hz) / 1.8) ** 2)
    arr = neon(arr, hl, (255, 190, 150), k=0.5, mix=0.7)
    # palms down both sides of the road, far to near
    plist = []
    for sc in (0.15, 0.22, 0.33, 0.50, 0.78):
        by = hz + (H - hz) * sc + 4
        size = 210 * sc + 16
        for sgn in (-1, 1):
            bx = vpx + sgn * ((W * 0.285) * sc + 150 * sc + 34)
            plist.append(((bx, by), (bx + sgn * size * 0.18, by - size * 2.25), sgn * size * 0.16, size))
    plist += [((-30, 800), (120, 150), -60, 246), ((W + 30, 800), (W - 120, 150), 60, 246)]
    pm = palms_mask(rng, plist)
    pc = V.ramp([(0, (26, 8, 60)), (1, (10, 4, 30))], np.clip(YY / H, 0, 1))
    arr = arr * (1 - pm[..., None]) + pc * pm[..., None]
    canvas = to_rgba(arr)
    sunset = dict(key=(1.0, 0.60, 0.42), fill=(0.10, 0.80, 0.92), wash=(1.0, 0.40, 0.50), wash_k=0.20)
    figure(canvas, 'e8ee4a5260c566bcfbff629b2ba1a6af.jpg', 560, 60, H + 22, +1, cut=dict(flip=True), light=sunset)
    figure(canvas, 'cb1de311739772c28493e186e603269e.jpg', 590, 1372, H + 22, -1, light=sunset)
    layer, box = title_speed(800)
    x0, y0, x1, y1 = put_title(canvas, layer, box, W / 2 - 8, 38, glow=(255, 60, 190), glow_k=0.36)
    spaced_line(canvas, 'XI : FOREVER OFFLINE', W / 2, y1 + 58, size=38, tracking=24, color=(255, 246, 214), glow=(255, 70, 170), shadow=(40, 8, 80))
    arr = finish(to_arr(canvas), rng, bloom=0.34, vignette=0.36, grain=5.0)
    return V.to_img(vhs(arr, rng))


SCENES['vhs'] = scene_vhs


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'out/wave'
    names = sys.argv[2:] or list(SCENES)
    os.makedirs(out, exist_ok=True)
    for name in names:
        big = SCENES[name]()
        if os.environ.get('XIFO_MASTER'):
            big.save(os.path.join(out, f'xifo_wave_{name}_1840.png'))
        small = big.resize((1400, 560), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=30, threshold=2))
        small.save(os.path.join(out, f'xifo_wave_{name}.jpg'), quality=93, subsampling=0)
        print('ok', name)
