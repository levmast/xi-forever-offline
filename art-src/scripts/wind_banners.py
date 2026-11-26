"""The Windurst theme's banners: 1400 x 560 pages of a storybook of the Federation of Windurst, tagged __theme-windurst
so they show only while the Windurst theme is worn (see assets\\press\\README.txt).

Usage:  python wind_banners.py [OUTDIR] [--sheet FILE] [names...]
        OUTDIR defaults to  ..\\..\\assets\\press   (writes windurst_NN_<name>__theme-windurst.jpg)

Every banner is a storybook page in a rounded frame of Star Tree wood with a band of green lacquer and gold stars.
  01 title     : "Windurst, Federation of the Stars": the wordmark, Shantotto and Ajido-Marujido, a Windurst street.
  02 heroes    : "Heroes of the Federation": Shantotto, Ajido-Marujido, Apururu and Kupipi.
  03 onions    : "Star Onion Brigade": the Brigade's picture and a row of Tarutaru faces.
  04 peoples   : "Tarutaru and Mithra": the race concept art of Windurst's two peoples.
  05 magic     : "The Ministries of Magic": the mages of Windurst and a Cardian.
  06 starlight : "Starlight": the festival picture, a Mandragora and a sky full of stars.
  07 wilds     : "Sarutabaruta": a Mandragora, a Dhalmel and a Yagudo on the grassland.
Art: the official concept art in art-src\\newart and pictures in art-src\\FFXI_Art_Collection_Part2. Lettering: Cherry
Swash and Fondamento (SIL OFL 1.1), Cinzel Decorative for the XI. Pillow + numpy."""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import wind_lib as L

W, H = 1400, 560
NAMES = ['title', 'heroes', 'onions', 'peoples', 'magic', 'starlight', 'wilds']
STREET = 'coll:sqex-we-are-vanadiel/22.jpg'
KUPIPI = 'coll:existing-collection/Kupipi.jpg'
ONIONS = 'coll:existing-collection/Star_Onion_Brigade.jpg'
STARLIGHT = 'coll:existing-collection/Starlight_Celebration.jpg'


# ------------------------------------------------------------------ the page
def frame(seed, night=False):
    """Wood all round, a lacquer band, a gold rule and the storybook page. Returns (img, page box, page mask)."""
    r = 46
    img = L.masked(L.wood(W, H, seed, lit=0.4), L.rounded((W, H), r))
    out = Image.new('RGBA', (W, H), (0, 0, 0, 255))
    band = L.ring((W, H), r, 9, 10)
    img.alpha_composite(L.masked(L.lacquer(W, H, L.GREEN, lit=0.5, seed=seed), band))
    b = 26
    pm = L.rounded((W, H), r, b)
    if night:
        yy = np.mgrid[0:H, 0:W][0].astype(np.float32) / H
        top, bot = np.array((18, 30, 64), np.float32), np.array((40, 76, 70), np.float32)
        arr = top * (1 - yy[..., None]) + bot * yy[..., None]
        pg = L.to_img(arr * (0.95 + L.noise(W, H, 3, seed)[..., None] * 0.1)).convert('RGBA')
        pg.alpha_composite(L.sparkles((W, H), 120, seed, rmin=2, rmax=7, alpha=230))
    else:
        pg = L.page(W, H, seed)
        pg.alpha_composite(L.sparkles((W, H), 26, seed, colour=(255, 236, 160), rmin=3, rmax=8, alpha=120))
    img.alpha_composite(L.masked(pg, pm))
    inner = ImageChops.subtract(pm, L.rounded((W, H), r, b + 8)).filter(ImageFilter.GaussianBlur(6))
    sh = Image.new('RGBA', (W, H), (50, 34, 10, 0))
    sh.putalpha(ImageChops.multiply(inner, pm).point(lambda v: int(v * 0.6)))
    img.alpha_composite(sh)
    img.alpha_composite(L.masked(L.gold_fill(W, H), L.ring((W, H), r, b - 4, 3)))
    k = 30
    img.alpha_composite(L.gold_star_layer((W, H), [(k, k, 15, 4), (W - k, k, 15, 4), (k, H - k, 15, 4), (W - k, H - k, 15, 4)]))
    out.alpha_composite(img)
    return out, (b, b, W - b, H - b), pm


def heading(img, x, y, title, sub=None, body=None, width=520, size=60, colour=L.GREEN_INK, body_colour=(60, 70, 40),
            align='left', lit=False):
    t = L.fit(lambda z: L.storybook(title, z, lit=lit, colour=colour), width, size * 1.6, size)
    tx = x if align == 'left' else x + (width - t.width) // 2
    img.alpha_composite(t, (int(tx), int(y)))
    y += t.height + 8
    if sub:
        s = L.fit(lambda z: L.ink(sub, L.font(L.F_HAND, z), colour), width, size, size * 0.5)
        sx = x if align == 'left' else x + (width - s.width) // 2
        img.alpha_composite(s, (int(sx), int(y)))
        y += s.height + 4
        d = ImageDraw.Draw(img)
        x0, x1 = (x, x + min(width, s.width + 40)) if align == 'left' else (x + width * 0.2, x + width * 0.8)
        d.line([x0, y + 6, x1, y + 6], fill=L.GOLD_DEEP + (255,), width=2)
        img.alpha_composite(L.gold_star_layer(img.size, [((x0 + x1) / 2, y + 6, 8, 4)]))
        y += 22
    if body:
        f = L.font(L.F_HAND, size * 0.4)
        for line in wrap(body, f, width):
            b = L.ink(line, f, body_colour)
            bx = x if align == 'left' else x + (width - b.width) // 2
            img.alpha_composite(b, (int(bx), int(y)))
            y += int(size * 0.5)
    return y


def wrap(text, fnt, width):
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if probe.textlength(t, font=fnt) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def plate(img, box, name, ax=0.5, ay=0.5, caption=None):
    """A picture in a small wood-and-gold frame with rounded corners, laid on the page with a shadow."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = x1 - x0, y1 - y0
    r = 22
    fr = L.masked(L.wood(w, h, len(name), lit=0.3), L.rounded((w, h), r))
    fr.alpha_composite(L.masked(L.gold_fill(w, h), L.ring((w, h), r, 9, 3)))
    pic = L.cover(L.picture(name), w - 28, h - 28, ax, ay).convert('RGBA')
    fr.alpha_composite(L.masked(pic, L.rounded((w - 28, h - 28), r - 10)), (14, 14))
    img.alpha_composite(L.shadow_of(fr, 12, 150, (30, 40, 10)), (x0 + 6, y0 + 10))
    img.alpha_composite(fr, (x0, y0))
    if caption:
        cap(img, (x0 + x1) / 2, y1 + 14, caption)


def cap(img, cx, y, text, size=24, colour=L.GREEN_INK):
    t = L.ink(text, L.font(L.F_HAND, size), colour)
    img.alpha_composite(t, (int(cx - t.width / 2), int(y)))


def stick(img, key, h, x, base, crop=1.0, edge=5, caption=None, anchor='c', flip=False):
    """A figure cut-out with a white edge, standing with its feet at y = base. x is its centre (anchor 'c') or left ('l')."""
    f = L.figure(key)
    if crop < 1:
        f = f.crop((0, 0, f.width, int(f.height * crop)))
    if flip:
        f = f.transpose(Image.FLIP_LEFT_RIGHT)
    s = L.sticker(L.fit_h(f, h), edge)
    px = int(x - s.width / 2) if anchor == 'c' else int(x)
    img.alpha_composite(s, (px, int(base - s.height)))
    if caption:
        cap(img, px + s.width / 2, base + 2, caption)
    return px, px + s.width


def wordmark(img, x, y, h, lit=True):
    xi = L.gilt('XI', L.font(L.C.F_DECO_B, h), lit=lit)
    img.alpha_composite(L.shadow_of(xi, 4, 120, (20, 40, 16)), (x + 2, y + 3))
    img.alpha_composite(xi, (x, y))
    t = L.gilt('FOREVER OFFLINE', L.font(L.F_SWASH, h * 0.32), tracking=2)
    img.alpha_composite(t, (x + xi.width + 14, y + (xi.height - t.height) // 2))
    return xi.height


def finish(img, pm, box):
    """A soft sunny glow from the top-left over the whole page."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = np.exp(-(((xx - W * 0.15) / (W * 0.5)) ** 2 + ((yy - H * 0.05) / (H * 0.7)) ** 2))
    lay = Image.new('RGBA', (W, H), (255, 236, 170, 0))
    lay.putalpha(ImageChops.multiply(Image.fromarray((g * 50).astype(np.uint8), 'L'), pm))
    img.alpha_composite(lay)
    return img.convert('RGB')


# ------------------------------------------------------------------ the banners
def b_title(rng):
    img, box, pm = frame(11)
    plate(img, (720, 52, 1350, 508), STREET, 0.5, 0.5)
    wordmark(img, 64, 50, 58)
    heading(img, 64, 130, 'WINDURST', 'Federation of the Stars',
            'Home of the Tarutaru and the Mithra, ruled by the Star Sibyl from Heavens Tower, high in the branches '
            'of the Star Tree.', width=420, size=92)
    stick(img, 'ajido', 300, 720, 512, crop=0.98, edge=6, flip=True)
    stick(img, 'shantotto', 330, 600, 520, crop=0.95, edge=6)
    return finish(img, pm, box)


def b_heroes(rng):
    img, box, pm = frame(12)
    heading(img, 60, 46, 'HEROES OF THE FEDERATION', 'The names every Tarutaru child knows', width=760, size=54)
    base = 480
    stick(img, 'shantotto', 300, 160, base, crop=0.95, caption='Shantotto')
    stick(img, 'ajido', 300, 400, base, caption='Ajido-Marujido')
    stick(img, 'apu', 250, 620, base, caption='Apururu')
    plate(img, (800, 130, 1350, 450), KUPIPI, 0.5, 0.35, caption='Kupipi')
    return finish(img, pm, box)


def b_onions(rng):
    img, box, pm = frame(13)
    plate(img, (600, 46, 1350, 514), ONIONS, 0.5, 0.5)
    heading(img, 60, 60, 'STAR ONION BRIGADE', 'Windurst\'s youngest heroes',
            'A band of Tarutaru children with big ideas and no fear of anything (except getting caught).',
            width=500, size=54)
    x = 50
    for k in ['bust-m1', 'bust-f3', 'bust-m4', 'bust-f5', 'bust-m8']:
        a, b = stick(img, k, 120, x, 500, edge=4, anchor='l')
        x = b - 14
    return finish(img, pm, box)


def b_peoples(rng):
    img, box, pm = frame(14)
    heading(img, 0, 46, 'TARUTARU AND MITHRA', 'The two peoples of Windurst', width=W, size=58, align='center')
    base = 500
    stick(img, 'taru', 300, 200, base, caption='Tarutaru')
    stick(img, 'taru-mage', 300, 420, base)
    stick(img, 'taru-kids', 200, 610, base)
    stick(img, 'mithra-girl', 330, 860, base)
    stick(img, 'mithra', 340, 1050, base, caption='Mithra')
    stick(img, 'mithra-head', 200, 1230, base)
    return finish(img, pm, box)


def b_magic(rng):
    img, box, pm = frame(15)
    heading(img, 0, 44, 'THE MINISTRIES OF MAGIC', 'Five ministries, one Star Sibyl, and a great deal of spellwork',
            width=W, size=56, align='center')
    base = 504
    stick(img, 'black-mage', 300, 190, base, caption='Black Mage')
    stick(img, 'white-mage', 320, 420, base, caption='White Mage')
    stick(img, 'summoner', 230, 680, base, caption='Summoner')
    stick(img, 'scholar', 320, 920, base, caption='Scholar')
    stick(img, 'cardian', 280, 1180, base, caption='Cardian')
    return finish(img, pm, box)


def b_starlight(rng):
    img, box, pm = frame(16, night=True)
    plate(img, (50, 50, 760, 510), STARLIGHT, 0.5, 0.5)
    heading(img, 820, 80, 'STARLIGHT', 'The Starlight Celebration: gifts, lights and a little magic',
            'When winter comes, Windurst hangs its lights, and every Smilebringer has a present to give.', width=500, size=52, colour=(250, 236, 190), body_colour=(226, 230, 210))
    stick(img, 'mandragora', 170, 1240, 506, edge=5)
    return finish(img, pm, box)


def b_wilds(rng):
    img, box, pm = frame(17)
    # a low line of hills in the meadow
    hills = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(hills)
    pts = [(0, H)] + [(x, 380 + 30 * np.sin(x / 140.0) + 16 * np.sin(x / 47.0)) for x in range(0, W + 20, 20)] + [(W, H)]
    d.polygon(pts, fill=255)
    hl = Image.new('RGBA', (W, H), (150, 190, 100, 0))
    hl.putalpha(ImageChops.multiply(hills.filter(ImageFilter.GaussianBlur(3)), pm).point(lambda v: int(v * 0.55)))
    img.alpha_composite(hl)
    heading(img, 60, 50, 'SARUTABARUTA', 'The wilds outside the gates of Windurst',
            'Step out of the city gates and the grassland of Sarutabaruta rolls on to the horizon. Mind the Mandragora.',
            width=560, size=64)
    base = 508
    stick(img, 'dhalmel', 380, 820, base, caption='Dhalmel')
    stick(img, 'yagudo', 330, 1170, base, caption='Yagudo')
    stick(img, 'mandragora', 170, 560, base, caption='Mandragora')
    return finish(img, pm, box)


def build(out, names=None):
    names = names or NAMES
    paths = []
    for name in names:
        i = NAMES.index(name) + 1
        img = globals()['b_' + name](random.Random(i))
        path = os.path.join(out, f'windurst_{i:02d}_{name}__theme-windurst.jpg')
        img.save(path, quality=90, optimize=True)
        paths.append(path)
    return paths


if __name__ == '__main__':
    args = list(sys.argv[1:])
    sheet = None
    if '--sheet' in args:
        i = args.index('--sheet')
        sheet = args[i + 1]
        del args[i:i + 2]
    out = args[0] if args and args[0] not in NAMES else os.path.join(L.KIT, 'assets', 'press')
    names = [a for a in args if a in NAMES]
    paths = build(out, names)
    if sheet:
        ims = [Image.open(p).resize((700, 280)) for p in paths]
        s = Image.new('RGB', (1400, 290 * ((len(ims) + 1) // 2)), (30, 50, 32))
        for k, im in enumerate(ims):
            s.paste(im, ((k % 2) * 700, (k // 2) * 290))
        s.save(sheet)
    print('ok:', len(paths), 'banners in', out)
