"""The Chronicle theme's banners: 1400 x 560 spreads of an old illustrated chronicle of Vana'diel, tagged
__theme-chronicle so they show only while the Chronicle theme is worn (see assets\\press\\README.txt).

Usage:  python chron_banners.py [OUTDIR] [--sheet FILE] [names...]
        OUTDIR defaults to  ..\\..\\assets\\press   (writes chronicle_NN_<name>__theme-chronicle.jpg)

Every banner is an open book on a tooled-leather cover: two vellum pages, the gutter shadow between them, gold edges.
  01 title    : the wordmark as an illuminated title page; the Warrior, White Mage and Black Mage sketches facing it.
  02 bahamut  : "Bahamut, the Wyrm King": the Bahamut concept painting as a colour plate.
  03 pacts    : "The Pacts of the Summoner": Ifrit, Shiva, Garuda, Titan, Ramuh and Leviathan in six small plates.
  04 bestiary : "A Bestiary of the Wilds": the Behemoth and the Khimaira.
  05 peoples  : "The Peoples of the Middle Lands": the five race sheets in a row.
  06 chocobo  : "Of Chocobos and the Open Road": the chocobo study beside the Ranger sketch.
  07 dragon   : "Here Be Dragons": the dragon concept as a colour plate.
All art from art-src\\newart (official concept art and pencil sketches). Lettering: Cinzel, Cinzel Decorative, IM FELL
English (SIL OFL 1.1). Pillow + numpy."""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import chron_lib as C

W, H = 1400, 560
NAMES = ['title', 'bahamut', 'pacts', 'bestiary', 'peoples', 'chocobo', 'dragon']


# ------------------------------------------------------------------ the open book
def book(seed):
    """Leather all round, two vellum pages with a gutter. Returns (img, left page box, right page box)."""
    img = C.leather(W, H, seed, lit=0.3)
    m = 22
    gx = W // 2
    pages = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(pages)
    # pages bow up a little at the outer corners
    d.rounded_rectangle((m, m + 4, gx - 2, H - m - 4), radius=10, fill=255)
    d.rounded_rectangle((gx + 2, m + 4, W - m, H - m - 4), radius=10, fill=255)
    # page stack edges (gold) under the pages
    stack = Image.new('L', (W, H), 0)
    ImageDraw.Draw(stack).rounded_rectangle((m - 6, m, W - m + 6, H - m), radius=12, fill=255)
    img.alpha_composite(C.shadow_of(C.masked(Image.new('RGBA', (W, H), (0, 0, 0, 255)), stack), 10, 200), (0, 6))
    img.alpha_composite(C.masked(C.gold_fill(W, H, seed=seed), stack))
    v = C.vellum(W, H, seed, burn=0.55)
    img.alpha_composite(C.masked(v, pages))
    # gutter shadow and page curl light
    xx = np.mgrid[0:H, 0:W][1].astype(np.float32)
    dx = np.abs(xx - gx) / (W * 0.5)
    g = np.exp(-(dx / 0.05) ** 2) * 150 + np.exp(-(dx / 0.16) ** 2) * 45
    sh = Image.new('RGBA', (W, H), (60, 32, 10, 0))
    sh.putalpha(ImageChops.multiply(C.to_img(g).convert('L'), pages))
    img.alpha_composite(sh)
    hi = np.exp(-((dx - 0.09) / 0.05) ** 2) * 30
    lay = Image.new('RGBA', (W, H), (255, 246, 220, 0))
    lay.putalpha(ImageChops.multiply(C.to_img(hi).convert('L'), pages))
    img.alpha_composite(lay)
    return img, (m + 40, m + 34, gx - 50, H - m - 34), (gx + 50, m + 34, W - m - 40, H - m - 34)


def page_rules(img, box):
    """A thin double rule round the text block, like a printed page."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rectangle((x0 - 14, y0 - 14, x1 + 14, y1 + 14), outline=C.SEPIA + (120,), width=1)
    d.rectangle((x0 - 10, y0 - 10, x1 + 10, y1 + 10), outline=C.SEPIA + (90,), width=1)


def heading(img, box, title, sub=None, body=None, top=None, size=48):
    """An illuminated heading centred in the box, a fleuron rule, a subtitle in IM FELL italic, a short body."""
    x0, y0, x1, y1 = box
    bw = x1 - x0
    t = C.fit(lambda s: C.illuminated(title, s, tracking=s * 0.05), bw, 120, size)
    y = top if top is not None else y0 + 20
    img.alpha_composite(t, (x0 + (bw - t.width) // 2, y))
    y += t.height + 16
    C.rule(img, x0 + bw * 0.2, x1 - bw * 0.2, y, C.SEPIA + (255,), 1.6)
    y += 18
    if sub:
        s = C.ink_text(sub, C.font(C.F_FELL_I, 26), C.SEPIA)
        if s.width > bw:
            s = C.fit_w(s, bw)
        img.alpha_composite(s, (x0 + (bw - s.width) // 2, y))
        y += s.height + 14
    if body:
        f = C.font(C.F_FELL, 22)
        for line in body:
            s = C.ink_text(line, f, C.INK, impress=False)
            img.alpha_composite(s, (x0 + (bw - s.width) // 2, y))
            y += 31
    return y


def plate(img, box, art, label=None, mount=(244, 232, 200), pad=14, ax=0.5, ay=0.5, contain=True):
    """A colour plate: a cream mount with a thin gold rule, the art inside, a small caption under it."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cap_h = 30 if label else 0
    mnt = Image.new('RGBA', (w, h), mount + (255,))
    mnt.alpha_composite(C.masked(C.vellum(w, h, w + h, burn=0.25), Image.new('L', (w, h), 120)))
    d = ImageDraw.Draw(mnt)
    d.rectangle((4, 4, w - 5, h - 5), outline=C.GOLD_DEEP + (255,), width=2)
    d.rectangle((8, 8, w - 9, h - 9), outline=C.GOLD + (200,), width=1)
    iw, ih = w - pad * 2, h - pad * 2 - cap_h
    if contain:
        # printed into the page: the art's white paper disappears (multiply), its colours sit in the vellum
        a = art.convert('RGB')
        s = min(iw / a.width, ih / a.height)
        a = a.resize((max(1, int(a.width * s)), max(1, int(a.height * s))), Image.LANCZOS)
        px, py = pad + (iw - a.width) // 2, pad + (ih - a.height) // 2
        region = mnt.crop((px, py, px + a.width, py + a.height)).convert('RGB')
        printed = ImageChops.multiply(region, a).convert('RGBA')
        mnt.alpha_composite(printed, (px, py))
    else:
        mnt.alpha_composite(C.cover(art.convert('RGBA'), iw, ih, ax, ay), (pad, pad))
    if label:
        t = C.ink_text(label, C.font(C.F_FELL_I, 20), C.SEPIA, impress=False)
        if t.width > w - 20:
            t = C.fit_w(t, w - 20)
        mnt.alpha_composite(t, ((w - t.width) // 2, h - pad - cap_h + 4))
    img.alpha_composite(C.shadow_of(mnt, 8, 150), (x0 + 4, y0 + 6))
    img.alpha_composite(mnt, (x0, y0))


def sketch_on(img, name, box, crop=1.0, wash=None, strength=1.1, ax=0.5):
    """A pencil sketch printed straight onto the page (multiply), fitted into box."""
    x0, y0, x1, y1 = box
    ink = C.sketch(name)
    ink = ink.crop((0, 0, ink.width, int(ink.height * crop)))
    s = min((x1 - x0) / ink.width, (y1 - y0) / ink.height)
    ink = ink.resize((max(1, int(ink.width * s)), max(1, int(ink.height * s))), Image.LANCZOS)
    px = x0 + int((x1 - x0 - ink.width) * ax)
    py = y1 - ink.height
    if wash:
        img.alpha_composite(C.wash_layer(ink, wash, 0.45, seed=len(name)), (px, py))
    img.alpha_composite(C.ink_layer(ink, C.SEPIA, strength), (px, py))


def drop_corner_ornaments(img, box):
    x0, y0, x1, y1 = box
    lay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    C.corner_ornaments(lay, 0, 0, C.GOLD_DEEP + (255,), 3)
    # corner_ornaments draws at the image corners; place a page-sized one instead
    page = Image.new('RGBA', (x1 - x0 + 28, y1 - y0 + 28), (0, 0, 0, 0))
    C.corner_ornaments(page, 22, 0, C.GOLD_DEEP + (220,), 3)
    img.alpha_composite(page, (x0 - 14, y0 - 14))


def art(name):
    return Image.open(os.path.join(C.NEW, name)).convert('RGB')


# ------------------------------------------------------------------ the spreads
def b_title(rng):
    img, L, R = book(11)
    for b in (L, R):
        drop_corner_ornaments(img, b)
    x0, y0, x1, y1 = L
    # the wordmark as an illuminated title page
    xi = C.text_layer('XI', C.font(C.F_DECO_B, 150), C.CRIMSON + (255,), 6, stroke=4, stroke_fill=C.GOLD + (255,))
    img.alpha_composite(C.glow(xi, C.GOLD_LIT, 10, 0.6), (x0 + (x1 - x0 - xi.width) // 2, y0 + 12))
    img.alpha_composite(xi, (x0 + (x1 - x0 - xi.width) // 2, y0 + 12))
    y = y0 + 12 + xi.height + 18
    t = C.fit(lambda s: C.ink_text('FOREVER OFFLINE', C.font(C.F_BLACK, s), C.INK, s * 0.12), x1 - x0 - 40, 60, 46)
    img.alpha_composite(t, (x0 + (x1 - x0 - t.width) // 2, y))
    y += t.height + 22
    C.rule(img, x0 + 90, x1 - 90, y, C.SEPIA + (255,), 1.6)
    y += 20
    for line, f, col in (('Being a True Chronicle of Vana’diel', C.F_FELL_I, C.SEPIA),
                         ('in the Age of the Crystal War’s Ending,', C.F_FELL_I, C.SEPIA),
                         ('set down for those who would return.', C.F_FELL_I, C.SEPIA)):
        s = C.ink_text(line, C.font(f, 25), col, impress=False)
        img.alpha_composite(s, (x0 + (x1 - x0 - s.width) // 2, y))
        y += 32
    # right page: three sketches facing the title
    rx0, ry0, rx1, ry1 = R
    third = (rx1 - rx0) / 3
    sketch_on(img, 'warrior', (rx0, ry0 + 20, int(rx0 + third * 1.15), ry1), wash=(176, 60, 40))
    sketch_on(img, 'white-mage', (int(rx0 + third * 0.95), ry0 + 60, int(rx0 + third * 2.05), ry1), wash=(200, 180, 140))
    sketch_on(img, 'black-mage', (int(rx0 + third * 1.85), ry0 + 30, rx1, ry1), wash=(60, 70, 120))
    return img


def b_bahamut(rng):
    img, L, R = book(23)
    drop_corner_ornaments(img, L)
    heading(img, L, 'BAHAMUT', 'the Wyrm King, Lord of the Wyrms',
            ['Since the age of the Zilart he has kept', 'his long watch from the Riverne', 'and judged the deeds of the five races.',
             'Few have stood before him.', 'Fewer still have walked away.'], size=60)
    rx0, ry0, rx1, ry1 = R
    plate(img, (rx0 + 10, ry0 - 12, rx1 - 10, ry1 + 12), art('ff11-bahamut.jpg'), 'Plate I. Bahamut, from the concept studies')
    return img


def b_pacts(rng):
    img, L, R = book(31)
    drop_corner_ornaments(img, L)
    heading(img, L, 'THE PACTS', 'of the Summoner, and the Avatars bound by them',
            ['Fire and ice, wind and earth, thunder and water:', 'each answers only to one', 'who has proven worthy at its shrine.',
             'Carry their names well.'], size=60)
    rx0, ry0, rx1, ry1 = R
    names = [('ff11-ifrit.jpg', 'Ifrit'), ('ff11-shiva.jpg', 'Shiva'), ('ff11-garuda.jpg', 'Garuda'),
             ('ff11-titan.jpg', 'Titan'), ('ff11-ramuh.jpg', 'Ramuh'), ('ff11-leviathan.jpg', 'Leviathan')]
    cw = (rx1 - rx0 - 20) // 3
    ch = (ry1 - ry0 + 20) // 2
    for i, (f, n) in enumerate(names):
        cx = rx0 + (i % 3) * (cw + 10)
        cy = ry0 - 10 + (i // 3) * (ch + 4)
        plate(img, (cx, cy, cx + cw, cy + ch - 4), art(f), n, pad=10)
    return img


def b_bestiary(rng):
    img, L, R = book(47)
    lx0, ly0, lx1, ly1 = L
    plate(img, (lx0 - 10, ly0 - 12, lx1 + 10, ly1 + 12), art('ff11-behemoth.jpg'), 'Behemoth. Of the Behemoth’s Dominion')
    rx0, ry0, rx1, ry1 = R
    y = heading(img, (rx0, ry0, rx1, ry0 + 160), 'A BESTIARY', 'of the Wilds beyond the City Gates', size=56)
    plate(img, (rx0 + 60, y + 4, rx1 - 60, ry1 + 12), art('ff11-khimaira.jpg'), 'Khimaira. Approach with a full party.')
    return img


def b_peoples(rng):
    img, L, R = book(59)
    lx0, ly0, lx1, ly1 = L
    y = heading(img, (lx0, ly0, lx1, ly0 + 140), 'THE PEOPLES', 'of the Middle Lands', size=52)
    left = [('ff11-hume-race.jpg', 'Hume'), ('ff11-elvaan-race.jpg', 'Elvaan')]
    right = [('ff11-tarutaru-race.jpg', 'Tarutaru'), ('ff11-mithra-race.jpg', 'Mithra'), ('ff11-galka-race.jpg', 'Galka')]
    gap = 16
    cw = (lx1 - lx0 + 20 - gap) // 2
    for i, (f, n) in enumerate(left):
        cx = lx0 - 10 + i * (cw + gap)
        plate(img, (cx, y + 2, cx + cw, ly1 + 14), art(f), n, pad=10)
    rx0, ry0, rx1, ry1 = R
    cw = (rx1 - rx0 + 20 - gap * 2) // 3
    for i, (f, n) in enumerate(right):
        cx = rx0 - 10 + i * (cw + gap)
        plate(img, (cx, ry0 - 12, cx + cw, ry1 + 14), art(f), n, pad=10)
    return img


def b_chocobo(rng):
    img, L, R = book(67)
    drop_corner_ornaments(img, R)
    lx0, ly0, lx1, ly1 = L
    plate(img, (lx0 - 10, ly0 - 12, lx1 + 10, ly1 + 12), art('ff11-chocobo.jpg'), 'A chocobo study, with saddle and tack')
    rx0, ry0, rx1, ry1 = R
    heading(img, (rx0, ry0, rx1 - 170, ry1), 'CHOCOBOS', 'and the Open Road',
            ['Hire one at the stables,', 'mind the time it has,', 'and the whole of the Middle Lands', 'is an afternoon away.'],
            size=50)
    sketch_on(img, 'ranger', (rx1 - 230, ry0 + 40, rx1 + 10, ry1), wash=(80, 120, 60), ax=1.0)
    return img


def b_dragon(rng):
    img, L, R = book(83)
    drop_corner_ornaments(img, L)
    lx0, ly0, lx1, ly1 = L
    heading(img, L, 'HERE BE', None, None, top=ly0 + 40, size=58)
    t = C.fit(lambda s: C.illuminated('DRAGONS', s, tracking=s * 0.05), lx1 - lx0 - 40, 120, 72)
    img.alpha_composite(t, (lx0 + (lx1 - lx0 - t.width) // 2, ly0 + 142))
    f = C.font(C.F_FELL_I, 25)
    y = ly0 + 142 + t.height + 28
    for line in ('Where the old maps end, the wyrms begin.', 'Bring a Dragoon, and bring a healer.'):
        s = C.ink_text(line, f, C.SEPIA, impress=False)
        img.alpha_composite(s, (lx0 + (lx1 - lx0 - s.width) // 2, y))
        y += 34
    rx0, ry0, rx1, ry1 = R
    plate(img, (rx0 + 10, ry0 - 12, rx1 - 10, ry1 + 12), art('ff11-dragon.jpg'), 'Plate II. A dragon, from the concept studies')
    return img


DRAW = {'title': b_title, 'bahamut': b_bahamut, 'pacts': b_pacts, 'bestiary': b_bestiary, 'peoples': b_peoples,
        'chocobo': b_chocobo, 'dragon': b_dragon}


def build(out, names=None):
    os.makedirs(out, exist_ok=True)
    paths = []
    for i, name in enumerate(NAMES, 1):
        if names and name not in names:
            continue
        img = DRAW[name](random.Random(i)).convert('RGB')
        path = os.path.join(out, f'chronicle_{i:02d}_{name}__theme-chronicle.jpg')
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
    out = args[0] if args and not args[0] in NAMES else os.path.join(C.KIT, 'assets', 'press')
    names = [a for a in args if a in NAMES] or None
    paths = build(out, names)
    if sheet:
        ims = [Image.open(p).resize((700, 280), Image.LANCZOS) for p in paths]
        s = Image.new('RGB', (1420, ((len(ims) + 1) // 2) * 290 + 10), (30, 18, 10))
        for k, im in enumerate(ims):
            s.paste(im, (10 + (k % 2) * 705, 10 + (k // 2) * 290))
        s.save(sheet)
    print('ok:', len(paths), 'banners in', out)
