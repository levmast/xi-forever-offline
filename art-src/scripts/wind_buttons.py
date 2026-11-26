"""The launcher's buttons in the Windurst look (a storybook of the Federation of Windurst), for the Windurst theme
(assets\\press\\windurst.json).

Usage:  python wind_buttons.py [OUTDIR] [--sheet FILE]
        OUTDIR defaults to  ..\\..\\assets\\press\\windurst-ui  (the folder windurst.json names as its "art").

One picture for every button in assets\\ui, under the same name and at exactly the same size (sizes are read from
assets\\ui; XIFO_UI overrides the folder), each also as _hover and _off, like chron_buttons.py.

Every button is a rounded plate of honey Star Tree wood with a band of green lacquer and a gold rule, little gold stars
in the corners, and a sunny storybook page inside. On the left, one of Windurst's people from the official colour concept
art (art-src\\newart) laid on the page like a picture-book cut-out; on the right, the label in Cherry Swash with a
gold-leaf first letter. Hover: the page warms in the sun, the stars light up and the page twinkles. Off: everything fades
to grey. Buttons that stop or leave something have a berry-red band.

The labels and the list of buttons come from chron_buttons.BUTTONS, so a new launcher button only needs its line there
(as the README asks); it gets a Windurst figure from POOL by itself, or a chosen one if it is given a line in FIG here."""
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

import chron_buttons as CB
import wind_lib as L

KIT = L.KIT
S = 4
size_of = CB.size_of
seed_of = CB.seed_of
off_of = CB.off_of

# name: [figures] (keys of wind_lib.FIGS). Buttons not listed take one from POOL.
FIG = {
    'play': ['shantotto'], 'stop': ['yagudo'], 'dualbox': ['taru', 'mithra-girl'], 'dualbox_small': ['bust-m1', 'mithra-head'],
    'hardcore': ['black-mage'], 'squad': ['taru-kids'], 'config': ['cardian'], 'tools': ['taru-mage'],
    'addons': ['apu'], 'settings': ['scholar'], 'exit': ['mithra-head'], 'update': ['ajido'], 'logs': ['old-mage'],
    'world': ['mithra'], 'rules': ['white-mage'], 'options': ['bust-f5'], 'system': ['mandragora'],
    'coop': ['taru', 'mithra-girl'], 'coop_on': ['bust-f3'], 'coop_host': ['shantotto'], 'coop_stop': ['yagudo'],
    'coop_cancel': ['yagudo'], 'coop_kick': ['black-mage'], 'coop_ban': ['yagudo'], 'coop_unban': ['white-mage'],
    'coop_visit': ['mithra'], 'coop_again': ['mithra'], 'coop_play': ['shantotto'], 'coop_home': ['bust-m4'],
    'coop_sendhome': ['ajido'], 'coop_test': ['cardian'], 'coop_forget': ['mandragora'],
}
POOL = ['bust-m1', 'bust-f3', 'bust-m4', 'bust-f5', 'bust-m8', 'mithra-head', 'bust-m0', 'bust-f0', 'cardian', 'mandragora']
CARDS = {'iron': 'taru-mage', 'steel': 'mithra', 'silver': 'yagudo', 'random': 'cardian'}   # the HARDCORE menu cards
BADGES = {                                           # name: colour of the pill (labels from chron_buttons.BADGES)
    'home': (52, 118, 62), 'visiting': (48, 92, 140), 'packed': (196, 128, 40), 'unreachable': (150, 46, 40),
    'playing': (52, 118, 62), 'resting': (100, 78, 150), 'leaving': (196, 128, 40), 'open': (52, 118, 62),
    'closed': (120, 112, 96), 'experimental': (150, 46, 40),
}


def figs_for(name):
    if name in FIG:
        return FIG[name]
    return [POOL[seed_of(name) % len(POOL)]]


# ------------------------------------------------------------------ the plate
def plate(W, H, name, hover=False, stopping=False, r=None):
    """Wood frame, lacquer band, gold rule, storybook page. Returns (img, inset of the page, radius, page mask)."""
    r = r if r is not None else int(H * 0.3)
    seed = seed_of(name)
    tone = (150, 92, 58) if stopping else L.HONEY
    img = L.masked(L.wood(W, H, seed, lit=1.0 if hover else 0.0, tone=tone), L.rounded((W, H), r))
    border = max(S * 3, int(H * 0.11))
    band = max(S * 2, int(border * 0.42))
    bm = L.ring((W, H), r, int(border * 0.32), band)
    img.alpha_composite(L.masked(L.lacquer(W, H, L.BERRY if stopping else L.GREEN, lit=1.0 if hover else 0.0, seed=seed), bm))
    page_m = L.rounded((W, H), r, border)
    img.alpha_composite(L.masked(L.page(W, H, seed, warm=1.0 if hover else 0.0), page_m))
    # the page sits under the wood: a soft shadow inside its edge
    inner = ImageChops.subtract(page_m, L.rounded((W, H), r, border + S * 2)).filter(ImageFilter.GaussianBlur(S * 1.5))
    sh = Image.new('RGBA', (W, H), (60, 40, 10, 0))
    sh.putalpha(ImageChops.multiply(inner, page_m).point(lambda x: int(x * 0.7)))
    img.alpha_composite(sh)
    gm = L.ring((W, H), r, border - max(S, int(border * 0.14)), max(S, border * 0.12))
    img.alpha_composite(L.masked(L.gold_fill(W, H, lit=hover), gm))
    return img, border, r, page_m


def corner_stars(img, r, border, hover):
    W, H = img.size
    k = r * 0.3 + border * 0.25
    s = max(S * 1.6, border * 0.5)
    places = [(k + border * 0.2, k + border * 0.2, s, 4), (W - k - border * 0.2, k + border * 0.2, s, 4),
              (k + border * 0.2, H - k - border * 0.2, s, 4), (W - k - border * 0.2, H - k - border * 0.2, s, 4)]
    img.alpha_composite(L.gold_star_layer((W, H), places, lit=hover))


def figure_strip(keys, crop_scale, fig_h, hover, edge):
    pieces = []
    for k in keys:
        f = L.figure(k)
        crop = min(1.0, L.FIGS[k][2] * crop_scale)
        f = f.crop((0, 0, f.width, max(8, int(f.height * crop))))
        f = L.fit_h(f, fig_h)
        st = L.sticker(f, edge)
        if hover:
            g = L.glow(st, L.GLOW.get(k, (255, 236, 160)), edge * 3, 1.3)
            lay = Image.new('RGBA', st.size, (0, 0, 0, 0))
            lay.alpha_composite(g)
            lay.alpha_composite(st)
            st = lay
        pieces.append(st)
    gap = -int(fig_h * 0.12)
    w = sum(p.width for p in pieces) + gap * (len(pieces) - 1)
    h = max(p.height for p in pieces)
    out = Image.new('RGBA', (max(1, w), h), (0, 0, 0, 0))
    x = 0
    for p in pieces:
        out.alpha_composite(p, (x, h - p.height))
        x += p.width + gap
    return out


def make_button(name, size=None, hover=False):
    text = CB.BUTTONS[name][0]
    w, h = size or size_of(name)
    W, H = w * S, h * S
    big = h >= 72
    img, border, r, page_m = plate(W, H, name, hover, name in CB.STOPPING)
    if hover:
        img.alpha_composite(L.sparkles((W, H), 7 if big else 4, seed_of(name), rmin=S * 1.5, rmax=S * (4 if big else 2.6),
                                       mask=page_m, alpha=230))
    # the figure: standing at the foot of the page, on the left, fading into the page on its right
    fig_h = int((H - border * 2) * (1.0 if big else 0.98))
    strip = figure_strip(figs_for(name), 1.3 if big else 1.0, fig_h, hover, max(S, H * 0.025))
    share = 0.42 if big else (0.21 if len(text) >= 12 else 0.25 if len(text) >= 7 else 0.3)
    if name.startswith('dualbox'):
        share = 0.46 if big else 0.42
    maxw = int(W * share)
    if strip.width > maxw:
        x0 = int((strip.width - maxw) * 0.5)
        strip = strip.crop((x0, 0, x0 + maxw, strip.height))
    xs = np.linspace(0, 1, strip.width, dtype=np.float32)[None, :]
    fade = 1 - L.smoothstep(0.82, 1.0, xs)
    al = np.asarray(strip.getchannel('A'), dtype=np.float32) * fade
    strip.putalpha(Image.fromarray(al.astype(np.uint8), 'L'))
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay.alpha_composite(strip, (border + int(r * 0.25), H - border - strip.height + int(S * 1.5)))
    lay.putalpha(ImageChops.multiply(lay.getchannel('A'), page_m))
    img.alpha_composite(lay)
    # the label
    x0 = border + int(r * 0.25) + strip.width * 0.9
    x1 = W - border - r * 0.45
    cap = H * (0.42 if big else 0.46)
    lab = L.fit(lambda z: L.storybook(text, z, lit=hover, tracking=0 if not big else None), int(x1 - x0), int((H - border * 2) * 0.9), cap)
    img.alpha_composite(lab, (int(x0 + (x1 - x0 - lab.width) / 2), int((H - lab.height) / 2)))
    corner_stars(img, r, border, hover)
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ wordmark, home, headers, badges, cards
def wordmark(W, H, sub=True, lit=False):
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    xi = L.gilt('XI', L.font(L.C.F_DECO_B, H * (0.6 if sub else 0.78)), lit=True)
    if xi.height > H * (0.56 if sub else 0.74):
        xi = L.fit_h(xi, int(H * (0.56 if sub else 0.74)))
    if xi.width > W * 0.9:
        xi = L.fit_w(xi, int(W * 0.9))
    y = int(H * 0.04) if sub else (H - xi.height) // 2
    out.alpha_composite(L.shadow_of(xi, H * 0.02, 160, (20, 40, 16)), ((W - xi.width) // 2 + 2, y + 3))
    out.alpha_composite(xi, ((W - xi.width) // 2, y))
    if sub:
        tag = L.gilt('FOREVER OFFLINE', L.font(L.F_SWASH, H * 0.15), tracking=H * 0.01)
        if tag.width > W * 0.9:
            tag = L.fit_w(tag, int(W * 0.9))
        ty = int(H * 0.7)
        out.alpha_composite(tag, ((W - tag.width) // 2, ty))
        y0 = ty - H * 0.06
        d = ImageDraw.Draw(out)
        d.line([W * 0.18, y0, W * 0.42, y0], fill=L.GOLD + (255,), width=max(1, int(H * 0.012)))
        d.line([W * 0.58, y0, W * 0.82, y0], fill=L.GOLD + (255,), width=max(1, int(H * 0.012)))
        out.alpha_composite(L.gold_star_layer((W, H), [(W / 2, y0, H * 0.045, 5)], lit=lit))
    return out


def make_home(size=None, hover=False, tile=False):
    w, h = size or size_of('logo_tile' if tile else 'home')
    W, H = w * S, h * S
    r = int(min(W, H) * (0.12 if tile else 0.3))
    img = L.masked(L.wood(W, H, 77 + tile, lit=1.0 if hover else 0.0), L.rounded((W, H), r))
    border = max(S * 3, int(min(W, H) * 0.07))
    inner = L.rounded((W, H), r, border)
    img.alpha_composite(L.masked(L.lacquer(W, H, L.GREEN_DEEP if not hover else L.GREEN, lit=1.0 if hover else 0.0), inner))
    img.alpha_composite(L.masked(L.gold_fill(W, H, lit=hover), L.ring((W, H), r, border, max(S, border * 0.18))))
    if tile:
        # the Star Tree's star, large and faint behind the mark, and a Tarutaru mage peeking in
        lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        st = Image.new('L', (W, H), 0)
        L.star(ImageDraw.Draw(st), W / 2, H * 0.46, H * 0.42, 60, 5, 0.42)
        lay.putalpha(ImageChops.multiply(st, inner))
        g = Image.new('RGBA', (W, H), L.GOLD_LIT + (0,))
        g.putalpha(lay.getchannel('A'))
        img.alpha_composite(g)
        img.alpha_composite(L.sparkles((W, H), 14, 5, rmin=S * 1.5, rmax=S * 4, mask=inner, alpha=150))
    else:
        img.alpha_composite(L.sparkles((W, H), 5 if hover else 3, 9, rmin=S, rmax=S * 2.5, mask=inner, alpha=160))
    mark = wordmark(int(W * 0.84), int(H * (0.8 if tile else 0.84)), sub=tile or H > 60 * S, lit=hover)
    img.alpha_composite(mark, ((W - mark.width) // 2, (H - mark.height) // 2))
    corner_stars(img, r, border, hover)
    return img.resize((w, h), Image.LANCZOS)


def make_header(name):
    w, h = size_of(name, (452, 44))
    W, H = w * S, h * S
    r = int(H * 0.5)
    img = L.masked(L.lacquer(W, H, L.GREEN, seed=seed_of(name)), L.rounded((W, H), r))
    img.alpha_composite(L.masked(L.gold_fill(W, H), L.ring((W, H), r, S, S * 1.6)))
    t = L.gilt(CB.HEADERS[name], L.font(L.F_SWASH, H * 0.5), tracking=H * 0.03)
    if t.width > W * 0.7:
        t = L.fit_w(t, int(W * 0.7))
    img.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    places = [((W - t.width) / 2 - H * 0.45, H / 2, H * 0.2, 4), ((W + t.width) / 2 + H * 0.45, H / 2, H * 0.2, 4)]
    img.alpha_composite(L.gold_star_layer((W, H), places))
    d = ImageDraw.Draw(img)
    for x0, x1 in ((W * 0.06, (W - t.width) / 2 - H * 0.8), ((W + t.width) / 2 + H * 0.8, W * 0.94)):
        if x1 > x0:
            d.line([x0, H / 2, x1, H / 2], fill=L.GOLD + (255,), width=max(1, int(S * 0.8)))
    return img.resize((w, h), Image.LANCZOS)


def make_badge(name):
    text = CB.BADGES[name][0]
    colour = BADGES[name]
    w, h = size_of('coop_badge_' + name, (96, 22))
    W, H = w * S, h * S
    m = L.rounded((W, H), H // 2)
    img = L.masked(L.lacquer(W, H, colour), m)
    img.alpha_composite(L.masked(L.gold_fill(W, H), L.ring((W, H), H // 2, 0, S * 1.5)))
    t = L.text_layer(text, L.font(L.F_SWASH, H * 0.58), (255, 246, 220, 255), tracking=H * 0.03)
    limit = W - S * 10
    if t.width > limit:
        t = t.resize((limit, int(t.height * max(0.8, limit / t.width))), Image.LANCZOS)
    img.alpha_composite(L.shadow_of(t, S, 200, (10, 30, 10)), ((W - t.width) // 2 + S // 2, (H - t.height) // 2 + S // 2))
    img.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    return img.resize((w, h), Image.LANCZOS)


def make_card(key, hover=False):
    """A HARDCORE menu card: a tall storybook page, the figure large, the mode's name in gold and green."""
    title, tagline, _ = CB.CARDS[key]
    w, h = CB.CARD
    W, H = w * S, h * S
    img, border, r, page_m = plate(W, H, 'card' + key, hover, stopping=(key == 'silver'), r=int(W * 0.12))
    if hover:
        img.alpha_composite(L.sparkles((W, H), 14, seed_of(key), rmin=S * 2, rmax=S * 5, mask=page_m, alpha=230))
    fk = CARDS[key]
    fig = figure_strip([fk], 1.0 / max(0.01, L.FIGS[fk][2]) * 0.8, int(H * 0.58), hover, S * 2.5)
    if fig.width > W - border * 2 - S * 6:
        fig = L.fit_w(fig, W - border * 2 - S * 6)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay.alpha_composite(fig, ((W - fig.width) // 2, int(H * 0.66) - fig.height))
    lay.putalpha(ImageChops.multiply(lay.getchannel('A'), page_m))
    img.alpha_composite(lay)
    y = int(H * 0.68)
    d = ImageDraw.Draw(img)
    d.line([W * 0.16, y, W * 0.84, y], fill=L.GOLD_DEEP + (255,), width=max(1, int(S * 0.9)))
    img.alpha_composite(L.gold_star_layer((W, H), [(W / 2, y, S * 3.2, 4)], lit=hover))
    t = L.fit(lambda z: L.storybook(title, z, lit=hover), W - 2 * border - S * 8, H * 0.12, H * 0.09)
    img.alpha_composite(t, ((W - t.width) // 2, int(H * 0.705)))
    room = W - 2 * (border + r * 0.4)
    longest = max((v[1] for v in CB.CARDS.values()), key=len)
    tsize = H * 0.05
    while L.ink(longest, L.font(L.F_HAND, tsize)).width > room and tsize > 8:
        tsize *= 0.95
    s = L.ink(tagline, L.font(L.F_HAND, tsize))
    img.alpha_composite(s, ((W - s.width) // 2, int(H * 0.845)))
    corner_stars(img, r, border, hover)
    return img.resize((w, h), Image.LANCZOS)


def build_all(out, only=None):
    os.makedirs(out, exist_ok=True)
    for name in CB.BUTTONS:
        if only and name not in only:
            continue
        if size_of(name) is None:
            continue
        normal = make_button(name)
        normal.save(os.path.join(out, name + '.png'))
        make_button(name, hover=True).save(os.path.join(out, name + '_hover.png'))
        off_of(normal).save(os.path.join(out, name + '_off.png'))
    if only:
        return
    home = make_home()
    home.save(os.path.join(out, 'home.png'))
    make_home(hover=True).save(os.path.join(out, 'home_hover.png'))
    off_of(home).save(os.path.join(out, 'home_off.png'))
    make_home(tile=True).save(os.path.join(out, 'logo_tile.png'))
    for name in CB.HEADERS:
        make_header(name).save(os.path.join(out, name + '.png'))
    for name in CB.BADGES:
        make_badge(name).save(os.path.join(out, 'coop_badge_' + name + '.png'))
    for key in CB.CARDS:
        card = make_card(key)
        card.save(os.path.join(out, 'hc_card_' + key + '.png'))
        make_card(key, hover=True).save(os.path.join(out, 'hc_card_' + key + '_hover.png'))
        off_of(card).save(os.path.join(out, 'hc_card_' + key + '_off.png'))


if __name__ == '__main__':
    args = list(sys.argv[1:])
    sheet_path = None
    if '--sheet' in args:
        i = args.index('--sheet')
        sheet_path = args[i + 1]
        del args[i:i + 2]
    only = None
    if '--only' in args:
        i = args.index('--only')
        only = args[i + 1].split(',')
        del args[i:i + 2]
    out_dir = args[0] if args else os.path.join(KIT, 'assets', 'press', 'windurst-ui')
    build_all(out_dir, only)
    if sheet_path:
        CB.contact_sheet(out_dir, sheet_path, bg=(30, 50, 32))
    print('ok:', len([n for n in os.listdir(out_dir) if n.endswith('.png')]), 'pictures in', out_dir)
