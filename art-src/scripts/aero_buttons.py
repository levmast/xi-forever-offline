"""The launcher's buttons in the Aero look (a mid-2000s Frutiger Aero desktop), for the Aero theme (assets\\press\\aero.json).

Usage:  python aero_buttons.py [OUTDIR] [--sheet FILE]
        OUTDIR defaults to  ..\\..\\assets\\press\\aero-ui  (the folder aero.json names as its "art").

One picture for every button in assets\\ui, under the same name and at exactly the same size (sizes are read from
assets\\ui), each also as _hover and _off: PLAY, STOP, DUALBOX, HARDCORE, the bottom bar, the Co-op page's buttons,
headers and badges, the wordmark tile and the HARDCORE menu's four cards. assets\\ui itself is never touched.

Every button is a pane of glossy glass over a little desktop wallpaper: blue sky and a green hill, or clear water with
bubbles, a figure from art-src cut off its paper and lit with a white glow, and the label in Selawik. All art here is art
no other part of the launcher or the website uses (aero_lib.ART). Needs Pillow + numpy and the Selawik fonts."""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

import aero_lib as A

HERE = A.HERE
KIT = A.KIT
UI = os.environ.get('XIFO_UI', os.path.join(KIT, 'assets', 'ui'))
S = 4                                               # drawn four times the size, then scaled down

# name: (label, [art names], scheme)       sky = sky and a green hill, aqua = water and bubbles, leaf = all green
BUTTONS = {
    'play':     ('PLAY',     ['hume-f'], 'sky'),
    'stop':     ('STOP',     ['behemoth'], 'aqua'),
    'dualbox':  ('DUALBOX',  ['hume-f', 'mini-mithra'], 'sky'),
    'dualbox_small': ('DUALBOX', ['hume-f', 'mini-mithra'], 'sky'),
    'hardcore': ('HARDCORE', ['behemoth'], 'aqua'),
    'squad':    ('SQUADS',   ['apu-red', 'apu', 'apu-blue'], 'leaf'),
    'config':   ('CONFIG',   ['hume-pres'], 'sky'),
    'tools':    ('TOOLS',    ['aldo'], 'sky'),
    'addons':   ('ADDONS',   ['apu-blue'], 'sky'),
    'settings': ('SETTINGS', ['ferena'], 'sky'),
    'exit':     ('EXIT',     ['behemoth'], 'aqua'),
    'update':   ('UPDATE',   ['apu'], 'leaf'),
    'logs':     ('LOGS',     ['aldo'], 'sky'),
    'world':    ('WORLD',    ['aldo'], 'leaf'),
    'rules':    ('RULES',    ['hume-pres'], 'sky'),
    'options':  ('OPTIONS',  ['ferena'], 'sky'),
    'system':   ('SYSTEM',   ['apu-blue'], 'sky'),
    'coop':          ('CO-OP',           ['mini-mithra'], 'leaf'),
    'coop_on':       ('TURN CO-OP ON',   ['mini-mithra'], 'leaf'),
    'coop_host':     ('START HOSTING',   ['hume-pres'], 'leaf'),
    'coop_stop':     ('STOP HOSTING',    ['behemoth'], 'aqua'),
    'coop_copy':     ('COPY INVITE',     ['ferena'], 'sky'),
    'coop_copylink': ('COPY LINK',       ['ferena'], 'sky'),
    'coop_newcode':  ('NEW CODE',        ['apu-blue'], 'sky'),
    'coop_sendhome': ('SEND HOME',       ['aldo'], 'aqua'),
    'coop_test':     ('TEST CONNECTION', ['apu'], 'sky'),
    'coop_visit':    ('VISIT',           ['hume-f'], 'leaf'),
    'coop_again':    ('VISIT AGAIN',     ['hume-f'], 'leaf'),
    'coop_play':     ('PLAY THERE',      ['hume-f'], 'sky'),
    'coop_home':     ('COME HOME',       ['mini-mithra'], 'sky'),
    'coop_takeback': ('TAKE BACK',       ['aldo'], 'aqua'),
    'coop_retry':    ('TRY AGAIN',       ['apu-red'], 'sky'),
    'coop_cancel':   ('CANCEL VISIT',    ['behemoth'], 'aqua'),
    'coop_file':     ('LOAD FILE',       ['apu-red'], 'sky'),
    'coop_save':     ('SAVE CHARACTER',  ['ferena'], 'leaf'),
    'coop_load':     ('RESTORE',         ['apu'], 'sky'),
    'coop_tailscale': ('GET TAILSCALE',  ['mini-mithra'], 'sky'),
    'coop_carry_save':   ('SAVE FOR OTHER PC',  ['apu-red'], 'sky'),
    'coop_carry_load':   ('LOAD FROM OTHER PC', ['apu-blue'], 'sky'),
    'coop_carry_folder': ('FOLDER...',          ['aldo'], 'sky'),
    'coop_places':   ('PLACES',          ['aldo'], 'leaf'),
    'coop_password': ('PASSWORD',        ['hume-pres'], 'sky'),
    'coop_kick':     ('KICK',            ['behemoth'], 'aqua'),
    'coop_ban':      ('BAN',             ['behemoth'], 'aqua'),
    'coop_unban':    ('LIFT BAN',        ['ferena'], 'leaf'),
    'coop_forget':   ('FORGET',          ['aldo'], 'aqua'),
}
HEADERS = {'coop_head_host': 'HOST MY WORLD', 'coop_head_visit': 'VISIT A FRIEND'}
BADGES = {                                           # name: (label, colour of the pill)
    'home':        ('HOME',          (52, 170, 60)),
    'visiting':    ('VISITING',      (26, 130, 214)),
    'packed':      ('ON THE WAY',    (226, 140, 20)),
    'unreachable': ('OUT OF REACH',  (204, 52, 52)),
    'playing':     ('PLAYING',       (52, 170, 60)),
    'resting':     ('IN YOUR WORLD', (100, 110, 200)),
    'leaving':     ('GOING HOME',    (226, 140, 20)),
    'open':        ('OPEN',          (52, 170, 60)),
    'closed':      ('CLOSED',        (120, 136, 150)),
    'experimental': ('EXPERIMENTAL', (204, 52, 52)),
}
CARDS = {   # the HARDCORE menu: key: (title, tagline, art, scheme)
    'iron':   ('IRON',   'You earn everything',   'excenmille', 'sky'),
    'steel':  ('STEEL',  'Fall, and start again', 'trion',      'aqua'),
    'silver': ('SILVER', 'Death is final',        'behemoth',   'storm'),
    'random': ('RANDOM', 'Fate decides',          'apu-group',  'leaf'),
}
CARD = (232, 330)


def size_of(name, fallback=None):
    path = os.path.join(UI, name + '.png')
    if os.path.exists(path):
        with Image.open(path) as im:
            return im.size
    return fallback


def seed_of(name):
    return random.Random(sum(ord(c) * (i + 7) for i, c in enumerate(name)))


# ------------------------------------------------------------------ wallpaper behind the glass
def wallpaper(W, H, scheme, rng, hover=False):
    """The little scene behind a button's glass, at W x H (already scaled up)."""
    if scheme == 'aqua':
        yy = np.mgrid[0:H, 0:W][0].astype(np.float32)
        arr = A.ramp(A.AQUA, yy / H)
        img = A.to_img(arr).convert('RGBA')
        # light shafts from the surface
        shafts = Image.new('L', (W, H), 0)
        d = ImageDraw.Draw(shafts)
        for _ in range(5):
            x = rng.uniform(0, W)
            sw = rng.uniform(0.03, 0.08) * W
            d.polygon([(x, 0), (x + sw, 0), (x + sw * 2.5 - W * 0.12, H), (x - W * 0.12, H)], fill=60)
        lay = Image.new('RGBA', (W, H), (220, 250, 255, 0))
        lay.putalpha(shafts.filter(ImageFilter.GaussianBlur(H * 0.06)))
        img.alpha_composite(lay)
        A.bubbles(img, rng, 9, (0, H * 0.1, W, H), H * 0.04, H * 0.11, alpha=0.9)
    elif scheme == 'leaf':
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        arr = A.ramp([(0, (150, 222, 80)), (0.5, (78, 176, 38)), (1, (26, 108, 20))], yy / H)
        arr = arr + (np.exp(-(((xx - W * 0.75) / (W * 0.35)) ** 2 + ((yy - H * 0.1) / (H * 0.6)) ** 2)) * 50)[..., None]
        img = A.to_img(arr).convert('RGBA')
        A.ribbons(img, rng, 2, 0.62, 0.12, [(230, 255, 180), (200, 255, 230)], alpha=0.45, thick=(0.05, 0.10))
        A.bubbles(img, rng, 5, (W * 0.25, 0, W, H), H * 0.04, H * 0.09, alpha=0.7)
    elif scheme == 'storm':
        yy = np.mgrid[0:H, 0:W][0].astype(np.float32)
        arr = A.ramp([(0, (40, 60, 92)), (0.5, (86, 112, 150)), (1, (150, 176, 206))], yy / H)
        img = A.to_img(arr).convert('RGBA')
        A.clouds(img, rng, 4, (0, -H * 0.05, W, H * 0.4), scale=H / 330 * 1.2, alpha=0.45)
    else:   # sky
        img = A.to_img(A.sky(W, H, horizon=1.05, sun=(0.86, 0.1))).convert('RGBA')
        A.clouds(img, rng, 3, (W * 0.35, -H * 0.05, W, H * 0.35), scale=H / 220, alpha=0.75)
        A.hills(img, 0.80, H * 0.06, rng)
    if hover:
        img = ImageEnhance.Brightness(img).enhance(1.14)
        img = ImageEnhance.Color(img).enhance(1.12)
    return img


INK = {'sky': (8, 52, 112), 'aqua': (4, 58, 92), 'leaf': (16, 78, 14), 'storm': (14, 24, 44)}
EDGE = {'sky': (12, 66, 140), 'aqua': (6, 76, 120), 'leaf': (26, 96, 22), 'storm': (20, 34, 60)}


def finish(img, w, h, scheme, radius, hover=False):
    """Glass over the picture, the edges, the corners rounded off, scaled down to w x h."""
    W, H = img.size
    img.alpha_composite(A.gloss((W, H), radius * S, top_alpha=0.66 if hover else 0.58, cut=0.48,
                                bottom_glow=(170, 255, 255) if hover else (130, 230, 255), bottom_alpha=0.55 if hover else 0.35))
    if hover:   # the hover glow of the time: a bright cyan light inside the rim
        rim = A.rounded_mask((W, H), radius * S)
        inner = A.rounded_mask((W, H), radius * S, inset=int(S * 4))
        ring = ImageChops.subtract(rim, inner).filter(ImageFilter.GaussianBlur(S * 2.5))
        lay = Image.new('RGBA', (W, H), (150, 245, 255, 0))
        lay.putalpha(ring.point(lambda v: int(v * 0.9)))
        img.alpha_composite(lay)
    img.alpha_composite(A.outline((W, H), radius * S, outer=EDGE[scheme], inner=(255, 255, 255),
                                  outer_a=235, inner_a=200 if hover else 150, width=S * 1.1))
    img.putalpha(ImageChops.multiply(img.split()[3], A.rounded_mask((W, H), radius * S)))
    return img.resize((w, h), Image.LANCZOS)


def off_of(img):
    """Switched off: frosted grey glass."""
    a = np.asarray(img, dtype=np.float32)
    rgb = a[..., :3]
    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(axis=2)[..., None]
    out = lum * 0.55 + 120 * np.array([0.88, 0.94, 1.0])
    return Image.fromarray(np.dstack([np.clip(out, 0, 255), a[..., 3]]).astype(np.uint8), 'RGBA')


def strip_of(names, height):
    """The figures side by side at this height (RGBA)."""
    pieces = [A.fit_height(A.art(n), height) for n in names]
    gap = int(height * -0.04)
    w = sum(p.width for p in pieces) + gap * (len(pieces) - 1)
    out = Image.new('RGBA', (max(1, w), height), (0, 0, 0, 0))
    x = 0
    for p in pieces:
        out.alpha_composite(p, (x, 0))
        x += p.width + gap
    return out


def label(text, box_w, box_h, cap, scheme):
    """The label fitted into box_w x box_h (scaled up), white with a soft shadow in the scheme's ink."""
    size = cap
    for _ in range(40):
        f = A.font(A.F_BOLD, size)
        t = A.glass_text(text, f, fill=(255, 255, 255), shadow=INK[scheme], shadow_a=0.85, tracking=size * 0.02,
                         glow=INK[scheme], glow_a=0.55)
        if t.width <= box_w and t.height <= box_h * 1.05:
            return t
        size *= 0.94
    return t


def make_button(name, size=None, hover=False):
    text, parts, scheme = BUTTONS[name]
    w, h = size or size_of(name)
    W, H = w * S, h * S
    rng = seed_of(name)
    big = h >= 72
    radius = int(h * (0.24 if big else 0.28))
    img = wallpaper(W, H, scheme, rng, hover)
    # the figure(s): standing on the left, a white glow round them, fading into the glass towards the label
    fig_h = int(H * (1.18 if parts[0] in ('behemoth',) else 1.06))
    strip = strip_of(parts, fig_h)
    share = 0.40 if big else (0.25 if len(text) >= 12 else 0.30 if len(text) >= 7 else 0.36)
    if name.startswith('dualbox'):
        share = 0.44
    maxw = int(W * share)
    if strip.width > maxw:
        anchor = 0.5 if parts[0] != 'behemoth' else 0.55
        x0 = int((strip.width - maxw) * anchor)
        strip = strip.crop((x0, 0, x0 + maxw, strip.height))
    xs = np.linspace(0, 1, strip.width, dtype=np.float32)[None, :]
    fade = 1 - A.smoothstep(0.82, 1.0, xs)
    al = np.asarray(strip.split()[3], dtype=np.float32) * fade
    strip.putalpha(Image.fromarray(al.astype(np.uint8), 'L'))
    top = int(H * 0.08) if parts[0] != 'behemoth' else -int(H * 0.06)
    img.alpha_composite(A.glow_of(strip, (255, 255, 255), S * 2.2, 1.3), (S * 3, top))
    img.alpha_composite(strip, (S * 3, top))
    x0 = S * 3 + strip.width * 0.86
    x1 = W - (H * 0.16 if big else S * 7)
    cap = H * (0.46 if big else 0.40)
    lab = label(text, int(x1 - x0), H * 0.8, cap, scheme)
    img.alpha_composite(lab, (int(x0 + (x1 - x0 - lab.width) / 2), int((H - lab.height) / 2 - H * 0.01)))
    return finish(img, w, h, scheme, radius, hover)


def wordmark(W, H, sub=True):
    """'XI' in glossy glass lettering, with FOREVER OFFLINE under it."""
    out = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    big = A.font(A.F_BOLD, H * (0.66 if sub else 0.8))
    xi = A.shade_text('XI', big, top=(255, 255, 255), bottom=(190, 230, 255), tracking=-H * 0.02)
    if xi.height > H * 0.50:
        xi = xi.resize((int(xi.width * H * 0.50 / xi.height), int(H * 0.50)), Image.LANCZOS)
    sh = A.glow_of(xi, (6, 50, 110), max(2, H * 0.03), 1.1)
    y = int(H * (0.12 if sub else 0.08))
    out.alpha_composite(sh, ((W - xi.width) // 2, y + int(H * 0.025)))
    out.alpha_composite(xi, ((W - xi.width) // 2, y))
    if sub:
        f = A.font(A.F_BOLD, H * 0.17)
        tag = A.glass_text('FOREVER OFFLINE', f, fill=(255, 255, 255), shadow=(6, 50, 110), tracking=H * 0.02, shadow_a=0.9)
        if tag.width > W * 0.9:
            tag = tag.resize((int(W * 0.9), int(tag.height * W * 0.9 / tag.width)), Image.LANCZOS)
        out.alpha_composite(tag, ((W - tag.width) // 2, int(H * 0.70)))
    return out


def make_home(size=None, hover=False, tile=False):
    w, h = size or size_of('logo_tile' if tile else 'home')
    W, H = w * S, h * S
    rng = seed_of('home' + str(tile))
    img = wallpaper(W, H, 'sky', rng, hover)
    if tile:
        A.bubbles(img, rng, 10, (0, 0, W, H), H * 0.03, H * 0.09, alpha=0.8)
        A.flare(img, W * 0.86, H * 0.12, H * 0.08, 0.8)
    img.alpha_composite(wordmark(W, H))
    return finish(img, w, h, 'sky', int(h * (0.12 if tile else 0.28)), hover)


def make_header(name):
    w, h = size_of(name, (452, 44))
    W, H = w * S, h * S
    rng = seed_of(name)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    arr = A.ramp([(0, (250, 253, 255)), (0.5, (226, 242, 252)), (1, (196, 226, 246))], yy / H)
    img = A.to_img(arr).convert('RGBA')
    A.ribbons(img, rng, 2, 0.6, 0.1, [(120, 200, 255), (150, 230, 160)], alpha=0.35, thick=(0.15, 0.3))
    f = A.font(A.F_SEMI, H * 0.50)
    t = A.glass_text(HEADERS[name], f, fill=(12, 70, 140), shadow=(255, 255, 255), shadow_a=1.0, tracking=H * 0.06)
    img.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    d = ImageDraw.Draw(img)
    for x0, x1 in ((W * 0.04, (W - t.width) / 2 - S * 6), ((W + t.width) / 2 + S * 6, W * 0.96)):
        for k, col in enumerate(((120, 190, 240, 255), (255, 255, 255, 255))):
            d.line([x0, H / 2 + k * S, x1, H / 2 + k * S], fill=col, width=int(S * 1.0))
    img.alpha_composite(A.gloss((W, H), int(h * 0.3) * S, top_alpha=0.5, cut=0.5, bottom_alpha=0.0))
    img.alpha_composite(A.outline((W, H), int(h * 0.3) * S, outer=(110, 160, 205), outer_a=255, width=S))
    img.putalpha(ImageChops.multiply(img.split()[3], A.rounded_mask((W, H), int(h * 0.3) * S)))
    return img.resize((w, h), Image.LANCZOS)


def make_badge(name):
    text, colour = BADGES[name]
    w, h = size_of('coop_badge_' + name, (90, 22))
    W, H = w * S, h * S
    c = np.array(colour, dtype=np.float32)
    yy = np.mgrid[0:H, 0:W][0].astype(np.float32)
    arr = A.ramp([(0, tuple(np.clip(c * 0.6 + 255 * 0.4, 0, 255))), (0.5, tuple(c)), (1, tuple(c * 0.7))], yy / H)
    img = A.to_img(arr).convert('RGBA')
    f = A.font(A.F_BOLD, H * 0.58)
    t = A.glass_text(text, f, fill=(255, 255, 255), shadow=tuple(int(v * 0.45) for v in colour), shadow_a=0.9, tracking=H * 0.03)
    limit = W - S * 8
    if t.width > limit:
        t = t.resize((limit, int(t.height * max(0.8, limit / t.width))), Image.LANCZOS)
    img.alpha_composite(t, ((W - t.width) // 2, (H - t.height) // 2))
    img.alpha_composite(A.gloss((W, H), H // 2, top_alpha=0.55, cut=0.5, bottom_alpha=0.0))
    img.alpha_composite(A.outline((W, H), H // 2, outer=tuple(int(v * 0.5) for v in colour), outer_a=255, inner_a=140, width=S))
    img.putalpha(ImageChops.multiply(img.split()[3], A.rounded_mask((W, H), H // 2)))
    return img.resize((w, h), Image.LANCZOS)


def make_card(key, hover=False):
    """A HARDCORE menu card: a tall pane of glass over its picture, the mode's name and line at the bottom."""
    title, tagline, art, scheme = CARDS[key]
    w, h = CARD
    W, H = w * S, h * S
    rng = seed_of('card' + key)
    img = wallpaper(W, H, scheme, rng, hover)
    if art in ('excenmille', 'trion'):          # in-game screenshots fill the top of the card
        pic = A.cover(A.art(art), W - S * 12, int(H * 0.66), 0.5, 0.25)
        m = Image.new('L', pic.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, pic.width - 1, pic.height - 1], radius=S * 10, fill=255)
        fadev = (1 - A.smoothstep(0.75, 1.0, np.linspace(0, 1, pic.height, dtype=np.float32)))[:, None] * np.ones((1, pic.width))
        m = Image.fromarray((np.asarray(m, dtype=np.float32) * fadev).astype(np.uint8), 'L')
        pic.putalpha(m)
        img.alpha_composite(pic, (S * 6, S * 6))
    else:
        if art == 'apu-group':
            strip = strip_of(['apu-red', 'apu', 'apu-blue'], int(H * 0.52))
            strip = A.fit_height(strip, int(H * 0.52)) if strip.width <= W else strip.resize((W - S * 8, int(strip.height * (W - S * 8) / strip.width)), Image.LANCZOS)
            pos = ((W - strip.width) // 2, int(H * 0.62) - strip.height)
        else:
            strip = A.art(art)
            strip = strip.resize((int(W * 1.15), int(strip.height * W * 1.15 / strip.width)), Image.LANCZOS)
            pos = (int(-W * 0.10), int(H * 0.66) - strip.height)
        img.alpha_composite(A.glow_of(strip, (255, 255, 255), S * 4, 1.2), pos)
        img.alpha_composite(strip, pos)
    # the title panel: frosted glass across the bottom third
    panel_y = int(H * 0.64)
    frost = img.crop((0, panel_y, W, H)).filter(ImageFilter.GaussianBlur(S * 6))
    veil = Image.new('RGBA', frost.size, (240, 250, 255, 120))
    frost.alpha_composite(veil)
    img.alpha_composite(frost, (0, panel_y))
    ImageDraw.Draw(img).line([S * 6, panel_y, W - S * 6, panel_y], fill=(255, 255, 255, 230), width=S)
    tf = A.font(A.F_BOLD, H * 0.11)
    t = A.glass_text(title, tf, fill=(255, 255, 255), shadow=INK[scheme], shadow_a=0.9, tracking=H * 0.012, glow=INK[scheme], glow_a=0.6)
    img.alpha_composite(t, ((W - t.width) // 2, int(H * 0.69)))
    sf = A.font(A.F_SEMI, H * 0.042)
    s = A.glass_text(tagline.upper(), sf, fill=INK[scheme], shadow=(255, 255, 255), shadow_a=0.9, tracking=H * 0.004)
    img.alpha_composite(s, ((W - s.width) // 2, int(H * 0.86)))
    return finish(img, w, h, scheme, 14, hover)


def build_all(out):
    os.makedirs(out, exist_ok=True)
    for name in BUTTONS:
        if size_of(name) is None:
            continue
        normal = make_button(name)
        normal.save(os.path.join(out, name + '.png'))
        make_button(name, hover=True).save(os.path.join(out, name + '_hover.png'))
        off_of(normal).save(os.path.join(out, name + '_off.png'))
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


def contact_sheet(out, path, bg=(214, 236, 249)):
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
    out_dir = args[0] if args else os.path.join(KIT, 'assets', 'press', 'aero-ui')
    build_all(out_dir)
    if sheet_path:
        contact_sheet(out_dir, sheet_path)
    print('ok:', len([n for n in os.listdir(out_dir) if n.endswith('.png')]), 'pictures in', out_dir)
