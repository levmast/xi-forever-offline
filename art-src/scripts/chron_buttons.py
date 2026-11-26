"""The launcher's buttons in the Chronicle look (an old illustrated chronicle of Vana'diel), for the Chronicle theme
(assets\\press\\chronicle.json).

Usage:  python chron_buttons.py [OUTDIR] [--sheet FILE]
        OUTDIR defaults to  ..\\..\\assets\\press\\chronicle-ui  (the folder chronicle.json names as its "art").

One picture for every button in assets\\ui, under the same name and at exactly the same size (sizes are read from
assets\\ui; XIFO_UI overrides the folder), each also as _hover and _off, like aero_buttons.py.

Every button is a plate of aged vellum in a tooled-leather frame with a gold-leaf rule and fleurons in the corners. On the
left, one of the official pencil sketches (art-src\\newart\\ff11-*-sketch) laid into the vellum in sepia ink; on the
right, the label in Cinzel with an illuminated red capital. Hover: candlelight, the gold brightens, and the sketch is
painted in with a watercolour wash. Off: the page fades to ash grey.
**A new launcher button needs a line in BUTTONS here too** (as in aero_buttons.py, vice_buttons.py, bit_buttons.py)."""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

import chron_lib as C

KIT = C.KIT
UI = os.environ.get('XIFO_UI', os.path.join(KIT, 'assets', 'ui'))
S = 4

# name: (label, [sketches], crop)   crop = how much of the figure from the top (1.0 = whole figure)
BUTTONS = {
    'play':     ('PLAY',     ['warrior'], 0.62),
    'stop':     ('STOP',     ['paladin'], 0.42),
    'dualbox':  ('DUALBOX',  ['red-mage', 'white-mage'], 0.55),
    'dualbox_small': ('DUALBOX', ['red-mage', 'white-mage'], 0.5),
    'hardcore': ('HARDCORE', ['dark-knight'], 0.62),
    'squad':    ('SQUADS',   ['thief', 'monk'], 0.6),
    'config':   ('CONFIG',   ['summoner'], 0.5),
    'tools':    ('TOOLS',    ['cid'], 0.45),
    'addons':   ('ADDONS',   ['puppetmaster'], 0.6),
    'settings': ('SETTINGS', ['black-mage'], 0.6),
    'exit':     ('EXIT',     ['ranger'], 0.55),
    'update':   ('UPDATE',   ['dragoon'], 0.55),
    'logs':     ('LOGS',     ['bard'], 0.5),
    'world':    ('WORLD',    ['beastmaster'], 0.55),
    'rules':    ('RULES',    ['samurai'], 0.42),
    'options':  ('OPTIONS',  ['blue-mage'], 0.5),
    'system':   ('SYSTEM',   ['corsair'], 0.55),
    'coop':          ('CO-OP',           ['thief', 'bard'], 0.55),
    'coop_on':       ('TURN CO-OP ON',   ['bard'], 0.5),
    'coop_host':     ('START HOSTING',   ['kam-lanaut'], 0.42),
    'coop_stop':     ('STOP HOSTING',    ['paladin'], 0.42),
    'coop_copy':     ('COPY INVITE',     ['white-mage'], 0.55),
    'coop_copylink': ('COPY LINK',       ['white-mage'], 0.55),
    'coop_newcode':  ('NEW CODE',        ['black-mage'], 0.6),
    'coop_sendhome': ('SEND HOME',       ['eald-narche'], 0.4),
    'coop_test':     ('TEST CONNECTION', ['cid'], 0.45),
    'coop_visit':    ('VISIT',           ['ranger'], 0.55),
    'coop_again':    ('VISIT AGAIN',     ['ranger'], 0.55),
    'coop_play':     ('PLAY THERE',      ['warrior'], 0.62),
    'coop_home':     ('COME HOME',       ['monk'], 0.55),
    'coop_takeback': ('TAKE BACK',       ['thief'], 0.6),
    'coop_retry':    ('TRY AGAIN',       ['red-mage'], 0.55),
    'coop_cancel':   ('CANCEL VISIT',    ['dark-knight'], 0.62),
    'coop_file':     ('LOAD FILE',       ['summoner'], 0.5),
    'coop_save':     ('SAVE CHARACTER',  ['bard'], 0.5),
    'coop_load':     ('RESTORE',         ['white-mage'], 0.55),
    'coop_tailscale': ('GET TAILSCALE',  ['corsair'], 0.55),
    'coop_carry_save':   ('SAVE FOR OTHER PC',  ['dragoon'], 0.55),
    'coop_carry_load':   ('LOAD FROM OTHER PC', ['beastmaster'], 0.55),
    'coop_carry_folder': ('FOLDER...',          ['cid'], 0.45),
    'coop_places':   ('PLACES',          ['beastmaster'], 0.55),
    'coop_password': ('PASSWORD',        ['ninja'], 0.55),
    'coop_kick':     ('KICK',            ['monk'], 0.55),
    'coop_ban':      ('BAN',             ['dark-knight'], 0.62),
    'coop_unban':    ('LIFT BAN',        ['white-mage'], 0.55),
    'coop_forget':   ('FORGET',          ['ninja'], 0.55),
}
# buttons that stop or leave something get a darker, oxblood frame
STOPPING = {'stop', 'exit', 'coop_stop', 'coop_cancel', 'coop_kick', 'coop_ban', 'coop_forget', 'hardcore'}
HEADERS = {'coop_head_host': 'HOST MY WORLD', 'coop_head_visit': 'VISIT A FRIEND'}
BADGES = {                                           # name: (label, colour of the wax)
    'home':        ('HOME',          (62, 110, 52)),
    'visiting':    ('VISITING',      (44, 78, 130)),
    'packed':      ('ON THE WAY',    (170, 104, 30)),
    'unreachable': ('OUT OF REACH',  (150, 34, 28)),
    'playing':     ('PLAYING',       (62, 110, 52)),
    'resting':     ('IN YOUR WORLD', (90, 70, 130)),
    'leaving':     ('GOING HOME',    (170, 104, 30)),
    'open':        ('OPEN',          (62, 110, 52)),
    'closed':      ('CLOSED',        (110, 100, 90)),
    'experimental': ('EXPERIMENTAL', (150, 34, 28)),
}
CARDS = {   # the HARDCORE menu: key: (title, tagline, sketch)
    'iron':   ('IRON',   'You earn everything',   'paladin'),
    'steel':  ('STEEL',  'Fall, and start again', 'samurai'),
    'silver': ('SILVER', 'Death is final',        'hydra'),
    'random': ('RANDOM', 'Fate decides',          'corsair'),
}
CARD = (232, 330)

# Sizes used only when assets\ui is not there (previews in the cloud workspace).
GUESS = {'play': (250, 84), 'stop': (250, 84), 'dualbox': (250, 84), 'hardcore': (250, 84), 'dualbox_small': (150, 44),
         'home': (150, 48), 'logo_tile': (220, 220)}


def size_of(name, fallback=None):
    path = os.path.join(UI, name + '.png')
    if os.path.exists(path):
        with Image.open(path) as im:
            return im.size
    if os.path.isdir(UI):
        return fallback
    if name in GUESS:
        return GUESS[name]
    if name.startswith('coop_head'):
        return (452, 44)
    if name.startswith('coop_badge'):
        return (96, 22)
    if name.startswith('coop'):
        return (176, 40)
    return fallback or (132, 44)


def seed_of(name):
    return sum(ord(c) * (i + 7) for i, c in enumerate(name)) % 10007


# ------------------------------------------------------------------ the plate
def plate(W, H, name, hover=False, stopping=False):
    """Leather frame, gold rule, vellum field. Returns (img, field_box, notch, field_mask)."""
    c = int(H * 0.16)
    seed = seed_of(name)
    tone = (70, 22, 18) if stopping else C.LEATHER
    img = C.masked(C.leather(W, H, seed, lit=1.0 if hover else 0.0, tone=tone), C.notched_mask((W, H), c))
    border = max(S * 3, int(H * 0.085))
    field_m = C.notched_mask((W, H), c, border)
    v = C.vellum(W, H, seed, warm=0.9 if hover else 0.0, burn=0.8)
    img.alpha_composite(C.masked(v, field_m))
    # the vellum sits a little under the leather: shadow inside the edge
    inner = ImageChops.subtract(field_m, C.notched_mask((W, H), c, border + S * 2)).filter(ImageFilter.GaussianBlur(S * 1.5))
    sh = Image.new('RGBA', (W, H), (40, 20, 6, 0))
    sh.putalpha(ImageChops.multiply(inner, field_m).point(lambda x: int(x * 0.8)))
    img.alpha_composite(sh)
    C.gold_line(img, (W, H), c, int(border * 0.38), max(S, border * 0.22), lit=hover)
    return img, border, c, field_m


def candle(img, field_m, strength=1.0):
    """Hover: warm candlelight pooled on the page."""
    W, H = img.size
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    g = np.exp(-(((xx - W * 0.3) / (W * 0.55)) ** 2 + ((yy - H * 0.35) / (H * 0.9)) ** 2))
    lay = Image.new('RGBA', (W, H), (255, 200, 110, 0))
    a = (g * 70 * strength).astype(np.uint8)
    lay.putalpha(ImageChops.multiply(Image.fromarray(a, 'L'), field_m))
    img.alpha_composite(lay)


def figures(parts, crop, fig_h, hover, seed):
    """The sketches side by side (cropped from the top), as sepia ink, with a wash when hovered. RGBA."""
    pieces = []
    for p in parts:
        ink = C.sketch(p)
        ink = ink.crop((0, 0, ink.width, max(8, int(ink.height * crop))))
        ink = C.fit_h(ink, fig_h)
        if fig_h < 70 * S:                      # small buttons: thicken the pencil so it survives the scale-down
            ink = ImageChops.lighter(ink, ink.filter(ImageFilter.MaxFilter(3)).point(lambda v: int(v * 0.8)))
        lay = Image.new('RGBA', ink.size, (0, 0, 0, 0))
        if hover:
            lay.alpha_composite(C.wash_layer(ink, C.WASH.get(p, (150, 90, 50)), alpha=0.62, seed=seed))
        lay.alpha_composite(C.ink_layer(ink, C.SEPIA if not hover else (70, 36, 16), 1.15))
        pieces.append(lay)
    gap = -int(fig_h * 0.08)
    w = sum(p.width for p in pieces) + gap * (len(pieces) - 1)
    out = Image.new('RGBA', (max(1, w), fig_h), (0, 0, 0, 0))
    x = 0
    for p in pieces:
        out.alpha_composite(p, (x, 0))
        x += p.width + gap
    return out


def make_button(name, size=None, hover=False):
    text, parts, crop = BUTTONS[name]
    w, h = size or size_of(name)
    W, H = w * S, h * S
    big = h >= 72
    img, border, c, field_m = plate(W, H, name, hover, name in STOPPING)
    if hover:
        candle(img, field_m)
    # the sketch: bottom of the field, fading out to the right into the page
    fig_h = int((H - border * 2) * (1.02 if big else 1.0))
    strip = figures(parts, crop, fig_h, hover, seed_of(name))
    share = 0.42 if big else (0.24 if len(text) >= 12 else 0.30 if len(text) >= 7 else 0.36)
    if name.startswith('dualbox'):
        share = 0.46 if big else 0.42
    maxw = int(W * share)
    if strip.width > maxw:
        x0 = int((strip.width - maxw) * 0.5)
        strip = strip.crop((x0, 0, x0 + maxw, strip.height))
    xs = np.linspace(0, 1, strip.width, dtype=np.float32)[None, :]
    fade = (1 - C.smoothstep(0.78, 1.0, xs)) * C.smoothstep(0.0, 0.06, xs)
    al = np.asarray(strip.getchannel('A'), dtype=np.float32) * fade
    strip.putalpha(Image.fromarray(al.astype(np.uint8), 'L'))
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay.alpha_composite(strip, (border + int(c * 0.35), H - border - strip.height))
    lay.putalpha(ImageChops.multiply(lay.getchannel('A'), field_m))
    img.alpha_composite(lay)
    # the label
    x0 = border + int(c * 0.35) + strip.width * 0.84
    x1 = W - border - c * 0.55
    cap = H * (0.40 if big else 0.42)
    lab = C.fit(lambda s: C.illuminated(text, s, lit=hover), int(x1 - x0), int((H - border * 2) * 0.86), cap)
    img.alpha_composite(lab, (int(x0 + (x1 - x0 - lab.width) / 2), int((H - lab.height) / 2 + H * 0.01)))
    C.corner_ornaments(img, c, int(border * 0.38), (C.GOLD_LIT if hover else C.GOLD) + (255,), max(S, H * 0.022), lit=hover)
    return img.resize((w, h), Image.LANCZOS)


def off_of(img):
    """Switched off: the page fades to ash, the gold to pewter."""
    a = np.asarray(img, dtype=np.float32)
    lum = (a[..., :3] * np.array([0.299, 0.587, 0.114])).sum(axis=2)[..., None]
    out = lum * 0.62 + np.array([96, 92, 86]) * 0.42
    return Image.fromarray(np.dstack([np.clip(out, 0, 255), a[..., 3]]).astype(np.uint8), 'RGBA')


# ------------------------------------------------------------------ wordmark, home, headers, badges, cards
def wordmark(W, H, sub=True):
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    xi = C.gilt_text('XI', C.font(C.F_DECO_B, H * (0.56 if sub else 0.72)), lit=True, tracking=H * 0.02)
    if xi.height > H * (0.52 if sub else 0.7):
        xi = C.fit_h(xi, int(H * (0.52 if sub else 0.7)))
    y = int(H * 0.08) if sub else (H - xi.height) // 2
    out.alpha_composite(C.shadow_of(xi, H * 0.02, 200), ((W - xi.width) // 2 + 2, y + 3))
    out.alpha_composite(xi, ((W - xi.width) // 2, y))
    if sub:
        tag = C.gilt_text('FOREVER OFFLINE', C.font(C.F_BOLD, H * 0.15), tracking=H * 0.02)
        if tag.width > W * 0.88:
            tag = C.fit_w(tag, int(W * 0.88))
        ty = int(H * 0.68)
        out.alpha_composite(tag, ((W - tag.width) // 2, ty))
        C.rule(out, W * 0.2, W * 0.8, ty - H * 0.05, C.GOLD + (255,), max(1, H * 0.012))
    return out


def make_home(size=None, hover=False, tile=False):
    w, h = size or size_of('logo_tile' if tile else 'home')
    W, H = w * S, h * S
    c = int(min(W, H) * (0.08 if tile else 0.16))
    img = C.masked(C.leather(W, H, 77 + tile, lit=1.0 if hover else 0.0), C.notched_mask((W, H), c))
    border = max(S * 3, int(min(W, H) * 0.06))
    C.gold_line(img, (W, H), c, border, max(S, border * 0.3), lit=hover)
    C.gold_line(img, (W, H), c, int(border * 1.7), max(S // 2, border * 0.12), lit=hover)
    if tile:
        # a faint sketch tooled into the leather behind the mark
        ink = C.fit_h(C.sketch('paladin'), int(H * 0.9))
        lay = Image.new('RGBA', ink.size, (0, 0, 0, 0))
        lay.alpha_composite(C.ink_layer(ink, (150, 110, 50), 0.35))
        img.alpha_composite(lay, ((W - ink.width) // 2, int(H * 0.05)))
    mark = wordmark(int(W * 0.84), int(H * (0.8 if tile else 0.84)), sub=tile or H > 60 * S)
    img.alpha_composite(mark, ((W - mark.width) // 2, (H - mark.height) // 2))
    C.corner_ornaments(img, c, border, (C.GOLD_LIT if hover else C.GOLD) + (255,), max(S, min(W, H) * 0.02), lit=hover)
    return img.resize((w, h), Image.LANCZOS)


def make_header(name):
    w, h = size_of(name, (452, 44))
    W, H = w * S, h * S
    c = int(H * 0.2)
    img = C.masked(C.vellum(W, H, seed_of(name), burn=0.6), C.notched_mask((W, H), c))
    C.gold_line(img, (W, H), c, S, S * 1.4)
    t = C.illuminated(HEADERS[name], H * 0.44, tracking=H * 0.05)
    img.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    for x0, x1 in ((W * 0.05, (W - t.width) / 2 - S * 8), ((W + t.width) / 2 + S * 8, W * 0.95)):
        C.rule(img, x0, x1, H / 2, C.SEPIA + (255,), S * 0.8)
    return img.resize((w, h), Image.LANCZOS)


def make_badge(name):
    text, colour = BADGES[name]
    w, h = size_of('coop_badge_' + name, (96, 22))
    W, H = w * S, h * S
    m = Image.new('L', (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, W - 1, H - 1), radius=H // 2, fill=255)
    c = np.array(colour, dtype=np.float32)
    yy = np.mgrid[0:H, 0:W][0].astype(np.float32) / H
    arr = c * (1.18 - yy[..., None] * 0.42) * (0.92 + C.noise(W, H, 2, 3)[..., None] * 0.16)
    img = C.masked(C.to_img(arr).convert('RGBA'), m)
    rim = ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(S * 2 + 1)))
    img.alpha_composite(C.masked(C.gold_fill(W, H), rim))
    t = C.text_layer(text, C.font(C.F_BOLD, H * 0.56), (250, 238, 210, 255), tracking=H * 0.04)
    limit = W - S * 10
    if t.width > limit:
        t = t.resize((limit, int(t.height * max(0.8, limit / t.width))), Image.LANCZOS)
    img.alpha_composite(C.shadow_of(t, S, 200), ((W - t.width) // 2 + S // 2, (H - t.height) // 2 + S // 2))
    img.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    return img.resize((w, h), Image.LANCZOS)


def make_card(key, hover=False):
    """A HARDCORE menu card: a full-page plate, the sketch large, the mode's name in an illuminated title."""
    title, tagline, sk = CARDS[key]
    w, h = CARD
    W, H = w * S, h * S
    img, border, c, field_m = plate(W, H, 'card' + key, hover, stopping=(key == 'silver'))
    if hover:
        candle(img, field_m, 1.2)
    ink = C.sketch(sk)
    ink = ink.crop((0, 0, ink.width, int(ink.height * (0.75 if sk != 'hydra' else 1.0))))
    fig = figures([sk], 0.75 if sk != 'hydra' else 1.0, int(H * 0.6), hover, seed_of(key))
    if fig.width > W - border * 2:
        fig = C.fit_w(fig, W - border * 2 - S * 4)
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay.alpha_composite(fig, ((W - fig.width) // 2, int(H * 0.66) - fig.height))
    lay.putalpha(ImageChops.multiply(lay.getchannel('A'), field_m))
    img.alpha_composite(lay)
    y = int(H * 0.68)
    C.rule(img, W * 0.14, W * 0.86, y, C.SEPIA + (255,), S * 0.9)
    room = W - 2 * (border + c)
    t = C.fit(lambda z: C.illuminated(title, z, lit=hover, tracking=H * 0.01), W - 2 * border - S * 8, H * 0.12, H * 0.085)
    img.alpha_composite(t, ((W - t.width) // 2, int(H * 0.715)))
    longest = max((v[1] for v in CARDS.values()), key=len)     # one size for every card's line
    tsize = H * 0.05
    while C.ink_text(longest, C.font(C.F_FELL_I, tsize), C.SEPIA).width > room and tsize > 8:
        tsize *= 0.95
    s = C.ink_text(tagline, C.font(C.F_FELL_I, tsize), C.SEPIA)
    img.alpha_composite(s, ((W - s.width) // 2, int(H * 0.845)))
    C.corner_ornaments(img, c, int(border * 0.38), (C.GOLD_LIT if hover else C.GOLD) + (255,), S * 2.4, lit=hover)
    return img.resize((w, h), Image.LANCZOS)


def build_all(out, only=None):
    os.makedirs(out, exist_ok=True)
    for name in BUTTONS:
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
    for name in HEADERS:
        make_header(name).save(os.path.join(out, name + '.png'))
    for name in BADGES:
        make_badge(name).save(os.path.join(out, 'coop_badge_' + name + '.png'))
    for key in CARDS:
        card = make_card(key)
        card.save(os.path.join(out, 'hc_card_' + key + '.png'))
        make_card(key, hover=True).save(os.path.join(out, 'hc_card_' + key + '_hover.png'))
        off_of(card).save(os.path.join(out, 'hc_card_' + key + '_off.png'))


def contact_sheet(out, path, bg=(40, 24, 16)):
    names = sorted(n for n in os.listdir(out) if n.endswith('.png'))
    ims = [(n, Image.open(os.path.join(out, n)).convert('RGBA')) for n in names]
    width, x, y, row_h, places = 1500, 10, 10, 0, []
    for n, im in ims:
        if x + im.width + 10 > width:
            x, y, row_h = 10, y + row_h + 10, 0
        places.append((n, im, x, y))
        x += im.width + 10
        row_h = max(row_h, im.height)
    sheet = Image.new('RGBA', (width, y + row_h + 10), bg + (255,))
    for n, im, px, py in places:
        sheet.alpha_composite(im, (px, py))
    sheet.convert('RGB').save(path)


if __name__ == '__main__':
    args = list(sys.argv[1:])
    sheet_path = None
    if '--sheet' in args:
        i = args.index('--sheet')
        sheet_path = args[i + 1]
        del args[i:i + 2]
    out_dir = args[0] if args else os.path.join(KIT, 'assets', 'press', 'chronicle-ui')
    build_all(out_dir)
    if sheet_path:
        contact_sheet(out_dir, sheet_path)
    print('ok:', len([n for n in os.listdir(out_dir) if n.endswith('.png')]), 'pictures in', out_dir)
