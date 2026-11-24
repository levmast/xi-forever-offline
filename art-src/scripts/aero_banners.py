"""The Aero theme's banners: five 1400 x 560 desktop scenes of the mid-2000s, tagged __theme-aero so they show only while
the Aero theme is worn (see assets\\press\\README.txt).

Usage:  python aero_banners.py [OUTDIR] [--sheet FILE] [names...]
        OUTDIR defaults to  ..\\..\\assets\\press   (writes aero_NN_<name>__theme-aero.jpg)

  01 hills    : blue sky, rolling green hill, light ribbons, lens flare, bubbles; the glass wordmark; the Hume adventurer,
                the two Mithra and the lady in white standing on the hill.
  02 desktop  : a glass desktop: two picture windows with the beach screenshots, a gadget, a taskbar with a crystal orb.
  03 dive     : clear water, light shafts and bubbles; the Behemoth concept drawing in a glass window.
  04 royal    : sky and clouds, Trion and Excenmille in two glass windows, the Hume gentleman in front.
  05 install  : an install dialog of the time ("Time remaining: forever"), the Tarutaru family on the grass.

Only art no other part of the launcher or the website uses (aero_lib.ART). Lettering in Selawik. Pillow + numpy."""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import aero_lib as A

W, H = 1400, 560
NAMES = ['hills', 'desktop', 'dive', 'royal', 'install']


def base_sky(rng, horizon=1.0, sun=(0.84, 0.14)):
    return A.to_img(A.sky(W, H, horizon=horizon, sun=sun)).convert('RGBA')


def aurora(rng):
    """The wave wallpaper: deep blue to aqua with glowing ribbons."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    arr = A.ramp([(0, (6, 40, 110)), (0.5, (14, 110, 190)), (1, (40, 190, 214))], yy / H * 0.7 + xx / W * 0.3)
    img = A.to_img(arr).convert('RGBA')
    A.ribbons(img, rng, 5, 0.55, 0.18, [(140, 255, 200), (120, 220, 255), (200, 255, 160), (255, 255, 255)], alpha=0.50)
    A.bubbles(img, rng, 18, (0, 0, W, H), 6, 34, alpha=0.7)
    return img


def stand(img, name, h, x, foot_y, glow=True):
    fig = A.fit_height(A.art(name), h)
    shadow = Image.new('RGBA', (int(fig.width * 1.2), int(h * 0.08)), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([0, 0, shadow.width - 1, shadow.height - 1], fill=(20, 70, 20, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)), (int(x - fig.width * 0.1), int(foot_y - shadow.height * 0.6)))
    if glow:
        img.alpha_composite(A.glow_of(fig, (255, 255, 255), 7, 1.1), (int(x), int(foot_y - h)))
    img.alpha_composite(fig, (int(x), int(foot_y - h)))
    return fig.width


def wordmark(img, cx, y, size=1.0):
    """XI: FOREVER OFFLINE in glossy glass lettering, with a little reflection under it."""
    f = A.font(A.F_BOLD, 120 * size)
    t = A.shade_text('XI: FOREVER OFFLINE', f, top=(255, 255, 255), bottom=(176, 222, 255), tracking=2 * size)
    edge = A.glow_of(t, (8, 60, 130), 3 * size, 2.2)
    soft = A.glow_of(t, (255, 255, 255), 16 * size, 0.9)
    x = int(cx - t.width / 2)
    img.alpha_composite(soft, (x, y))
    img.alpha_composite(edge, (x, y + int(4 * size)))
    img.alpha_composite(t, (x, y))
    # gloss on the letters' top half
    sheen = Image.new('RGBA', t.size, (255, 255, 255, 0))
    m = t.split()[3].copy()
    cut = Image.new('L', t.size, 0)
    ImageDraw.Draw(cut).rectangle([0, 0, t.width, int(t.height * 0.48)], fill=120)
    sheen.putalpha(ImageChops.multiply(m, cut))
    img.alpha_composite(sheen, (x, y))
    # reflection
    ref = t.transpose(Image.FLIP_TOP_BOTTOM)
    ga = np.linspace(0.35, 0, ref.height, dtype=np.float32)[:, None]
    ra = (np.asarray(ref.split()[3], dtype=np.float32) * ga).astype(np.uint8)
    ref.putalpha(Image.fromarray(ra, 'L'))
    img.alpha_composite(ref, (x, y + t.height + int(6 * size)))
    return t.height


def tagline(img, text, cx, y, size=30, fill=(255, 255, 255), ink=(8, 60, 130)):
    f = A.font(A.F_SEMI, size)
    t = A.glass_text(text, f, fill=fill, shadow=ink, shadow_a=0.9, tracking=size * 0.08, glow=ink, glow_a=0.5)
    img.alpha_composite(t, (int(cx - t.width / 2), int(y)))


def hills(rng):
    img = base_sky(rng, sun=(0.86, 0.12))
    A.clouds(img, rng, 7, (0, 10, W, 220), scale=1.1)
    A.ribbons(img, rng, 3, 0.62, 0.06, [(255, 255, 255), (200, 255, 230), (180, 230, 255)], alpha=0.40)
    A.hills(img, 0.80, 34, random.Random(4), colours=[(0, (150, 220, 80)), (1, (60, 150, 40))], phase=2.2)
    A.hills(img, 0.86, 26, random.Random(9), phase=0.4)
    A.flare(img, W * 0.86, H * 0.12, 46, 1.0)
    A.bubbles(img, rng, 16, (0, 0, W, H * 0.8), 6, 30, alpha=0.85)
    stand(img, 'hume-f', 380, 70, 520)
    stand(img, 'mini-mithra', 300, 175, 530)
    stand(img, 'ferena', 360, 1150, 525)
    hh = wordmark(img, W * 0.55, 150, 0.82)
    tagline(img, 'THE CLASSIC ERA  ·  ON YOUR OWN DESKTOP', W * 0.55, 150 + hh + 70, 28)
    return img


def taskbar(img, label):
    bar_h = 54
    y = H - bar_h
    yy = np.mgrid[0:bar_h, 0:W][0].astype(np.float32)
    arr = A.ramp([(0, (120, 170, 210)), (0.5, (40, 80, 130)), (1, (14, 40, 80))], yy / bar_h)
    bar = A.to_img(arr).convert('RGBA')
    bar.putalpha(200)
    sheen = A.gloss((W, bar_h), 1, top_alpha=0.35, cut=0.5, bottom_alpha=0.0)
    bar.alpha_composite(sheen)
    ImageDraw.Draw(bar).line([0, 0, W, 0], fill=(220, 240, 255, 220), width=1)
    img.alpha_composite(bar, (0, y))
    # the orb: a glass sphere with a crystal in it (the project's, not anyone's logo)
    r = 30
    orb = Image.new('RGBA', (r * 2 + 8, r * 2 + 8), (0, 0, 0, 0))
    yy2, xx2 = np.mgrid[0:orb.height, 0:orb.width].astype(np.float32)
    d = np.sqrt((xx2 - orb.width / 2) ** 2 + (yy2 - orb.height / 2) ** 2) / r
    col = A.ramp([(0, (120, 240, 140)), (0.7, (30, 150, 60)), (1, (10, 70, 30))], d)
    a = (d < 1).astype(np.float32) * 255
    orb = Image.fromarray(np.dstack([col, a]).astype(np.uint8), 'RGBA')
    dd = ImageDraw.Draw(orb)
    cx, cy = orb.width / 2, orb.height / 2
    dd.polygon([(cx, cy - r * 0.62), (cx + r * 0.34, cy), (cx, cy + r * 0.62), (cx - r * 0.34, cy)], fill=(230, 255, 255, 235))
    dd.line([(cx, cy - r * 0.62), (cx, cy + r * 0.62)], fill=(120, 200, 230, 255), width=2)
    A.bubble(orb, cx, cy, r, 0.9, tint=(230, 255, 240))
    img.alpha_composite(A.glow_of(orb, (160, 255, 200), 8, 1.0), (14, y + bar_h // 2 - orb.height // 2 - 4))
    img.alpha_composite(orb, (14, y + bar_h // 2 - orb.height // 2 - 4))
    # one open program
    bw, bh = 260, 40
    btn = Image.new('RGBA', (bw, bh), (150, 200, 240, 110))
    btn.alpha_composite(A.gloss((bw, bh), 4, top_alpha=0.5, cut=0.5, bottom_glow=(150, 230, 255), bottom_alpha=0.5))
    btn.alpha_composite(A.outline((bw, bh), 4, outer=(10, 30, 60), inner_a=120))
    t = A.glass_text(label, A.font(A.F_REG, 17), fill=(255, 255, 255), shadow=(0, 20, 40), shadow_a=0.9)
    btn.alpha_composite(t, (14, (bh - t.height) // 2))
    btn.putalpha(ImageChops.multiply(btn.split()[3], A.rounded_mask((bw, bh), 4)))
    img.alpha_composite(btn, (96, y + 7))
    clock = A.glass_text('11:11 PM', A.font(A.F_REG, 18), fill=(255, 255, 255), shadow=(0, 20, 40), shadow_a=0.9)
    img.alpha_composite(clock, (W - clock.width - 20, y + (bar_h - clock.height) // 2))


def gadget(img, x, y):
    """A sidebar gadget: a glass tile with the world's status."""
    w, h = 220, 150
    g = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32)
    arr = A.ramp([(0, (60, 90, 130)), (1, (14, 30, 60))], yy / h)
    body = A.to_img(arr).convert('RGBA')
    body.putalpha(190)
    g.alpha_composite(body)
    g.alpha_composite(A.gloss((w, h), 12, top_alpha=0.35, cut=0.42, bottom_alpha=0.25))
    g.alpha_composite(A.outline((w, h), 12, outer=(10, 20, 40), inner_a=120))
    lines = [('Vana\'diel', 20, A.F_SEMI, (255, 255, 255)), ('Firesday  ·  Full moon', 15, A.F_REG, (200, 230, 255)),
             ('Players online: 1', 15, A.F_REG, (200, 230, 255)), ('Server: forever', 15, A.F_REG, (140, 255, 170))]
    yy0 = 16
    for text, sz, ff, col in lines:
        t = A.glass_text(text, A.font(ff, sz), fill=col, shadow=(0, 10, 30), shadow_a=0.9)
        g.alpha_composite(t, (14, yy0))
        yy0 += t.height + 2
    g.putalpha(ImageChops.multiply(g.split()[3], A.rounded_mask((w, h), 12)))
    img.alpha_composite(A.glow_of(g, (0, 20, 40), 10, 0.6), (x, y + 6))
    img.alpha_composite(g, (x, y))


def desktop(rng):
    img = aurora(rng)
    w1, p1 = A.window((560, 360), 'beach_morning.jpg - Picture Viewer', A.art('beach-1'), active=False)
    img.alpha_composite(w1, (120 - p1, 34 - p1))
    w2, p2 = A.window((560, 360), 'beach_stroll.jpg - Picture Viewer', A.art('beach-2'))
    img.alpha_composite(w2, (520 - p2, 96 - p2))
    gadget(img, 1140, 40)
    gadget_note(img, 1140, 210)
    taskbar(img, 'XI: Forever Offline')
    stand(img, 'apu-red', 170, 18, 500, glow=True)
    stand(img, 'apu-blue', 190, 1290, 500, glow=True)
    return img


def gadget_note(img, x, y):
    """A sticky note gadget."""
    w, h = 220, 170
    g = Image.new('RGBA', (w, h), (255, 246, 150, 255))
    yy = np.mgrid[0:h, 0:w][0].astype(np.float32)
    g = A.to_img(A.ramp([(0, (255, 250, 180)), (1, (250, 226, 110))], yy / h)).convert('RGBA')
    d = ImageDraw.Draw(g)
    f = A.font(A.F_REG, 18)
    for i, line in enumerate(['to do:', '- level my squad', '- Crystal Boy cart', '- never log out']):
        d.text((14, 12 + i * 34), line, font=f, fill=(70, 60, 30))
    img.alpha_composite(A.glow_of(g, (0, 20, 40), 8, 0.5), (x + 3, y + 6))
    img.alpha_composite(g, (x, y))


def dive(rng):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    arr = A.ramp([(0, (150, 240, 250)), (0.25, (40, 190, 226)), (0.7, (8, 110, 170)), (1, (4, 60, 116))], yy / H)
    img = A.to_img(arr).convert('RGBA')
    # caustic ripples on the surface
    rip = (np.sin(xx / 23 + np.sin(yy / 17) * 2) * np.sin(yy / 13 + np.sin(xx / 31) * 2)) ** 8
    rip = rip * np.exp(-yy / (H * 0.35)) * 120
    lay = Image.fromarray(np.dstack([np.full((H, W, 3), 255, np.float32), np.clip(rip, 0, 255)]).astype(np.uint8), 'RGBA')
    img.alpha_composite(lay)
    shafts = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(shafts)
    for _ in range(9):
        x = rng.uniform(-100, W)
        sw = rng.uniform(30, 90)
        d.polygon([(x, 0), (x + sw, 0), (x + sw * 3 + 160, H), (x + 160, H)], fill=int(rng.uniform(30, 70)))
    sl = Image.new('RGBA', (W, H), (230, 255, 255, 0))
    sl.putalpha(shafts.filter(ImageFilter.GaussianBlur(20)))
    img.alpha_composite(sl)
    A.bubbles(img, rng, 40, (0, 0, W, H), 4, 40, alpha=0.9)
    beh = A.art('behemoth')
    w1, p1 = A.window((600, 400), 'behemoth_concept.jpg - Picture Viewer', None)
    # the drawing on white inside the window
    canvas = Image.new('RGBA', (600 - 16, 400 - 38), (255, 255, 255, 255))
    fig = beh.resize((int(canvas.width * 0.95), int(beh.height * canvas.width * 0.95 / beh.width)), Image.LANCZOS)
    canvas.alpha_composite(fig, ((canvas.width - fig.width) // 2, max(0, canvas.height - fig.height - 10)))
    w1.alpha_composite(canvas, (p1 + 8, p1 + 30))
    img.alpha_composite(w1, (720 - p1, 60 - p1))
    hh = wordmark(img, 370, 150, 0.52)
    tagline(img, 'DIVE BACK IN', 370, 150 + hh + 46, 40)
    tagline(img, 'Same old monsters. Same old world. Yours alone.', 370, 150 + hh + 110, 22)
    return img


def royal(rng):
    img = base_sky(rng, sun=(0.12, 0.1))
    A.clouds(img, rng, 8, (0, 0, W, 300), scale=1.2)
    A.hills(img, 0.84, 22, random.Random(2), phase=1.0)
    A.flare(img, W * 0.12, H * 0.10, 40, 0.9)
    w1, p1 = A.window((470, 330), 'Prince Trion', A.cover(A.art('trion'), 470, 330, 0.5, 0.15))
    img.alpha_composite(w1, (300 - p1, 40 - p1))
    w2, p2 = A.window((470, 330), 'Excenmille', A.cover(A.art('excenmille'), 470, 330, 0.5, 0.2), active=False)
    img.alpha_composite(w2, (820 - p2, 110 - p2))
    stand(img, 'hume-pres', 330, 40, 540)
    A.bubbles(img, rng, 14, (0, 0, W, H), 6, 26, alpha=0.8)
    tagline(img, 'THE KINGDOM OF SAN D\'ORIA AWAITS', W * 0.58, 486, 30)
    return img


def install(rng):
    img = aurora(rng)
    A.hills(img, 0.86, 18, random.Random(7), phase=0.8)
    dw, dh = 640, 300
    w1, p1 = A.window((dw, dh), 'Setup - XI: Forever Offline', None)
    body = Image.new('RGBA', (dw - 16, dh - 38), (255, 255, 255, 255))
    yy = np.mgrid[0:body.height, 0:body.width][0].astype(np.float32)
    body = A.to_img(A.ramp([(0, (255, 255, 255)), (1, (232, 242, 250))], yy / body.height)).convert('RGBA')
    d = ImageDraw.Draw(body)
    d.text((24, 18), 'Installing Vana\'diel...', font=A.font(A.F_REG, 26), fill=(30, 60, 130))
    d.text((24, 64), 'Copying files: the whole classic era, your squad and every crystal.', font=A.font(A.F_REG, 16), fill=(40, 40, 40))
    # progress bar of the time: glossy green with a moving shine
    bx, by, bw, bh = 24, 110, body.width - 48, 26
    d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=(230, 230, 230), outline=(150, 160, 170))
    fill_w = int(bw * 0.78)
    gy = np.mgrid[0:bh - 2, 0:fill_w - 2][0].astype(np.float32)
    g = A.to_img(A.ramp([(0, (190, 255, 160)), (0.45, (80, 200, 60)), (0.5, (40, 170, 30)), (1, (90, 210, 70))], gy / (bh - 2))).convert('RGBA')
    gx = np.mgrid[0:bh - 2, 0:fill_w - 2][1].astype(np.float32)
    shine = np.exp(-((gx - fill_w * 0.6) / 60) ** 2) * 120
    g.alpha_composite(Image.fromarray(np.dstack([np.full(gx.shape + (3,), 255, np.float32), shine]).astype(np.uint8), 'RGBA'))
    body.alpha_composite(g, (bx + 1, by + 1))
    d.text((24, 150), 'Time remaining: forever', font=A.font(A.F_REG, 16), fill=(70, 70, 70))
    d.line([0, body.height - 62, body.width, body.height - 62], fill=(210, 220, 230), width=1)
    for i, (lab, prim) in enumerate((('Cancel', False), ('Play now', True))):
        bw2, bh2 = 120, 32
        x = body.width - (bw2 + 14) * (2 - i) - 10
        yb = body.height - 46
        top, bot = ((230, 244, 255), (150, 200, 240)) if prim else ((250, 250, 250), (214, 218, 224))
        bg = A.to_img(A.ramp([(0, top), (0.5, top), (0.52, bot), (1, bot)], np.mgrid[0:bh2, 0:bw2][0].astype(np.float32) / bh2)).convert('RGBA')
        bg.alpha_composite(A.outline((bw2, bh2), 4, outer=(60, 120, 190) if prim else (120, 120, 130), inner_a=200))
        tt = A.text_img(lab, A.font(A.F_REG, 16), (10, 20, 40))
        bg.alpha_composite(tt, ((bw2 - tt.width) // 2, (bh2 - tt.height) // 2))
        bg.putalpha(A.rounded_mask((bw2, bh2), 4))
        body.alpha_composite(bg, (x, yb))
    w1.alpha_composite(body, (p1 + 8, p1 + 30))
    img.alpha_composite(w1, (620 - p1, 90 - p1))
    stand(img, 'apu-red', 230, 90, 520)
    stand(img, 'apu', 300, 200, 530)
    stand(img, 'apu-blue', 250, 380, 524)
    hh = wordmark(img, 330, 40, 0.42)
    return img


MAKERS = {'hills': hills, 'desktop': desktop, 'dive': dive, 'royal': royal, 'install': install}


def build(out, names=None):
    os.makedirs(out, exist_ok=True)
    made = []
    for i, name in enumerate(NAMES, 1):
        if names and name not in names:
            continue
        img = MAKERS[name](random.Random(100 + i)).convert('RGB')
        path = os.path.join(out, f'aero_{i:02d}_{name}__theme-aero.jpg')
        img.save(path, quality=90, optimize=True)
        made.append(path)
    return made


if __name__ == '__main__':
    args = list(sys.argv[1:])
    sheet = None
    if '--sheet' in args:
        i = args.index('--sheet')
        sheet = args[i + 1]
        del args[i:i + 2]
    out = args[0] if args and args[0] not in NAMES else os.path.join(A.KIT, 'assets', 'press')
    names = [a for a in args if a in NAMES]
    made = build(out, names)
    if sheet:
        ims = [Image.open(p) for p in made]
        s = Image.new('RGB', (W // 2 * 2 + 10, (H // 2 + 10) * ((len(ims) + 1) // 2)), (220, 236, 248))
        for k, im in enumerate(ims):
            s.paste(im.resize((W // 2, H // 2)), ((k % 2) * (W // 2 + 10), (k // 2) * (H // 2 + 10)))
        s.save(sheet)
    print('ok:', len(made), 'banners in', out)
