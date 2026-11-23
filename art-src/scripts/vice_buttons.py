"""The launcher's buttons in the XIFO Miami-sunset look, for the limited-time look (launcher_theme.py).

Usage:  python vice_buttons.py [OUTDIR] [--sheet FILE]
        OUTDIR defaults to  ..\\..\\assets\\press\\vaporwave-ui  (the folder vaporwave__until-DATE.json names as its "art").

One picture for every button in assets\\ui, under the same name and at exactly the same size (the sizes are read from
assets\\ui), each also as _hover and _off: PLAY, STOP, DUALBOX, the bottom bar, the Co-op page's buttons, headers and
badges, the wordmark tile. While the look is in date the launcher loads these instead; assets\\ui itself is not touched.

Every button is a small sunset: sky, a slatted sun, a strip of water, a neon rim, the label in the XIFO lettering, and a
figure cut out of the job art in art-src and lit like the banners. Needs Pillow + numpy and the fonts in art-src\\fonts
(Kanit-BlackItalic.ttf, Righteous-Regular.ttf). Builds on vice_banner.py and wave_banners.py from the same folder."""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import vice_banner as V
import wave_banners as Wv

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, '..', '..'))
UI = os.environ.get('XIFO_UI', os.path.join(KIT, 'assets', 'ui'))      # where the usual buttons are (their sizes are read from here)
F_LABEL = os.path.join(V.FONTS, 'Kanit-BlackItalic.ttf')
F_SMALL = os.path.join(V.FONTS, 'Righteous-Regular.ttf')
S = 4                                               # everything is drawn four times the size and scaled down

# name: (label, [(art, crop box as fractions)], scheme)      the art and crops are the ones the usual buttons use
BUTTONS = {
    'play':     ('PLAY',     [('warrior', (0.0, 0.0, 1.0, 0.92))], 'sunset'),
    'stop':     ('STOP',     [('dark-knight', (0.0, 0.0, 1.0, 0.95))], 'night'),
    'dualbox':  ('DUALBOX',  [('red-mage', (0.0, 0.0, 0.62, 0.5)), ('white-mage', (0.12, 0.0, 0.92, 0.45))], 'sunset'),
    'dualbox_small': ('DUALBOX', [('red-mage', (0.0, 0.0, 0.62, 0.5)), ('white-mage', (0.12, 0.0, 0.92, 0.45))], 'sunset'),
    'squad':    ('SQUADS',   [('job-art', (0.18, 0.0, 0.82, 0.42))], 'sunset'),
    'config':   ('CONFIG',   [('summoner', (0.38, 0.0, 0.84, 0.5))], 'sunset'),
    'tools':    ('TOOLS',    [('beastmaster', (0.0, 0.0, 0.8, 0.55))], 'sunset'),
    'addons':   ('ADDONS',   [('beastmaster', (0.0, 0.0, 0.8, 0.55))], 'sunset'),
    'settings': ('SETTINGS', [('black-mage', (0.15, 0.0, 0.9, 0.62))], 'sunset'),
    'exit':     ('EXIT',     [('ninja', (0.08, 0.0, 0.78, 0.42))], 'night'),
    'update':   ('UPDATE',   [('dragoon', (0.0, 0.0, 1.0, 0.4))], 'sunset'),
    'logs':     ('LOGS',     [('bard', (0.12, 0.0, 0.88, 0.55))], 'sunset'),
    'world':    ('WORLD',    [('character-races', (0.04, 0.02, 0.31, 0.30))], 'sunset'),
    'rules':    ('RULES',    [('summoner', (0.38, 0.0, 0.84, 0.5))], 'sunset'),
    'options':  ('OPTIONS',  [('beastmaster', (0.0, 0.0, 0.8, 0.55))], 'sunset'),
    'system':   ('SYSTEM',   [('black-mage', (0.15, 0.0, 0.9, 0.62))], 'sunset'),
    'coop':          ('CO-OP',           [('character-races', (0.0, 0.02, 1.0, 0.42))], 'sunset'),
    'coop_on':       ('TURN CO-OP ON',   [('character-races', (0.0, 0.02, 1.0, 0.42))], 'sunset'),
    'coop_host':     ('START HOSTING',   [('paladin', (0.25, 0.0, 1.0, 0.42))], 'sunset'),
    'coop_stop':     ('STOP HOSTING',    [('dark-knight', (0.42, 0.0, 1.0, 0.62))], 'night'),
    'coop_copy':     ('COPY INVITE',     [('bard', (0.05, 0.0, 0.85, 0.5))], 'sunset'),
    'coop_newcode':  ('NEW CODE',        [('black-mage', (0.15, 0.0, 0.9, 0.6))], 'sunset'),
    'coop_sendhome': ('SEND HOME',       [('dragoon', (0.1, 0.0, 0.9, 0.36))], 'night'),
    'coop_test':     ('TEST CONNECTION', [('summoner', (0.38, 0.0, 0.84, 0.5))], 'sunset'),
    'coop_visit':    ('VISIT',           [('ranger', (0.3, 0.0, 0.8, 0.4))], 'sunset'),
    'coop_play':     ('PLAY THERE',      [('warrior', (0.3, 0.0, 1.0, 0.75))], 'sunset'),
    'coop_home':     ('COME HOME',       [('white-mage', (0.1, 0.08, 0.8, 0.5))], 'sunset'),
    'coop_takeback': ('TAKE BACK',       [('samurai', (0.05, 0.0, 0.75, 0.42))], 'night'),
    'coop_retry':    ('TRY AGAIN',       [('monk', (0.1, 0.0, 0.9, 0.5))], 'sunset'),
    'coop_cancel':   ('CANCEL VISIT',    [('ninja', (0.08, 0.0, 0.78, 0.42))], 'night'),
    'coop_file':     ('LOAD FILE',       [('red-mage', (0.0, 0.0, 0.62, 0.45))], 'sunset'),
    'coop_save':     ('SAVE CHARACTER',  [('shantotto', (0.1, 0.02, 0.85, 0.5))], 'sunset'),
    'coop_load':     ('RESTORE',         [('thief', (0.2, 0.0, 0.85, 0.42))], 'sunset'),
    'coop_tailscale': ('GET TAILSCALE',  [('ca-mithra', (0.0, 0.0, 1.0, 0.5))], 'sunset'),
    'coop_carry_save':   ('SAVE FOR OTHER PC',  [('ca-children', (0.0, 0.0, 0.5, 0.75))], 'sunset'),
    'coop_carry_load':   ('LOAD FROM OTHER PC', [('ca-mini-taru', (0.30, 0.0, 0.52, 1.0))], 'sunset'),
    'coop_carry_folder': ('FOLDER...',          [('ca-children', (0.5, 0.0, 1.0, 0.75))], 'night'),
}
ANCHOR = {'play': 0.62, 'stop': 0.7, 'squad': 0.5, 'update': 0.3, 'tools': 0.35, 'addons': 0.35, 'options': 0.35,
          'coop': 0.5, 'coop_on': 0.5, 'coop_play': 0.55, 'coop_stop': 0.6}
HEADERS = {'coop_head_host': 'HOST MY WORLD', 'coop_head_visit': 'VISIT A FRIEND'}
BADGES = {                                           # name: (label, colour of the tube)
    'home':        ('HOME',          (70, 240, 180)),
    'visiting':    ('VISITING',      (90, 220, 255)),
    'packed':      ('ON THE WAY',    (255, 196, 96)),
    'unreachable': ('OUT OF REACH',  (255, 90, 130)),
    'playing':     ('PLAYING',       (70, 240, 180)),
    'resting':     ('IN YOUR WORLD', (170, 180, 255)),
    'leaving':     ('GOING HOME',    (255, 196, 96)),
    'open':        ('OPEN',          (70, 240, 180)),
    'closed':      ('CLOSED',        (170, 150, 210)),
    'experimental': ('EXPERIMENTAL', (255, 90, 130)),
}
SCHEMES = {
    'sunset': dict(sky=[(0, (30, 12, 80)), (0.42, (116, 28, 150)), (0.78, (236, 62, 140)), (1, (255, 150, 100))],
                   sun=[(0, (255, 242, 150)), (0.5, (255, 170, 100)), (1, (255, 84, 140))], halo=(255, 110, 150),
                   sea=[(0, (120, 36, 130)), (0.3, (60, 18, 100)), (1, (22, 8, 54))], glint=(255, 190, 140),
                   rim=(255, 64, 196), key=(1.0, 0.62, 0.44), fill=(0.10, 0.80, 0.92), wash=(1.0, 0.40, 0.52)),
    'night':  dict(sky=[(0, (6, 8, 40)), (0.48, (26, 22, 104)), (0.82, (88, 44, 170)), (1, (196, 70, 190))],
                   sun=[(0, (250, 236, 255)), (0.5, (236, 150, 240)), (1, (150, 90, 240))], halo=(170, 90, 240),
                   sea=[(0, (70, 34, 140)), (0.3, (30, 18, 90)), (1, (10, 6, 44))], glint=(150, 230, 255),
                   rim=(64, 226, 240), hover=(255, 190, 244), key=(0.9, 0.42, 0.90), fill=(0.10, 0.85, 0.95), wash=(0.7, 0.3, 0.9)),
}
FACE = [(0.0, (255, 252, 232)), (0.30, (255, 232, 160)), (0.60, (255, 160, 120)), (1.0, (255, 96, 170))]
FACE_NIGHT = [(0.0, (240, 255, 255)), (0.35, (150, 240, 250)), (0.70, (170, 150, 255)), (1.0, (230, 110, 230))]
INK = (20, 8, 52)


def size_of(name, fallback=None):
    """The size the launcher expects: that of the usual picture in assets\\ui."""
    path = os.path.join(UI, name + '.png')
    if os.path.exists(path):
        with Image.open(path) as im:
            return im.size
    return fallback


# ------------------------------------------------------------------ the figures
_SHEETS = {}


def sheet(art):
    """A whole art file as a cut-out (its white paper gone), at its own size."""
    if art not in _SHEETS:
        img = V.load(art)
        rgba = img.convert('RGBA')
        rgba.putalpha(V.solid_mask(img, hole_r=5))
        _SHEETS[art] = rgba
    return _SHEETS[art]


def figures(parts, height, scheme):
    """The pieces side by side at this height, lit for the scheme (RGBA)."""
    pieces = []
    for art, box in parts:
        im = sheet(art)
        w, h = im.size
        im = im.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        im = im.resize((max(1, round(im.width * height / im.height)), height), Image.LANCZOS)
        lit, _ = Wv.relight(im, Image.new('L', im.size, 0), +1, key=scheme['key'], fill=scheme['fill'], wash=scheme['wash'],
                            wash_k=0.16, fade=0.01, fade_k=0.0, bright=1.04, sat=1.25)
        pieces.append(lit)
    overlap = int(height * 0.12)
    width = sum(p.width for p in pieces) - (len(pieces) - 1) * overlap
    strip = Image.new('RGBA', (max(1, width), height), (0, 0, 0, 0))
    x = 0
    for p in pieces:
        strip.alpha_composite(p, (x, 0))
        x += p.width - overlap
    return strip


# ------------------------------------------------------------------ drawing
def rounded(size, inset, radius):
    m = Image.new('L', size, 0)
    ImageDraw.Draw(m).rounded_rectangle([inset, inset, size[0] - 1 - inset, size[1] - 1 - inset], radius=max(1, radius), fill=255)
    return m


def arr_of(mask):
    return np.asarray(mask, dtype=np.float32) / 255.0


def blur(mask, r):
    return mask.filter(ImageFilter.GaussianBlur(r))


def scene(w, h, scheme, sun_x, sun_r=None, darken_from=None):
    """The little sunset every button is painted on: (H, W, 3) float array at S times the size."""
    W, H = w * S, h * S
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    hz = H * 0.70
    out = V.ramp(scheme['sky'], np.clip(yy / hz, 0, 1))
    r = (sun_r or h * 0.40) * S
    cx, cy = sun_x * S, hz - r * 0.18
    d = np.hypot(xx - cx, yy - cy)
    out = V.add(out, np.exp(-(d / (r * 1.9)) ** 2)[..., None] * np.array(scheme['halo'], dtype=np.float32), 0.42)
    disc = 1 - V.smoothstep(r - S * 0.6, r + S * 0.6, d)
    v = np.clip((yy - (cy - r)) / (2 * r), 0, 1)
    slits = 4
    start = 0.50
    rel = np.clip((v - start) / (1 - start), 0, 1)
    period = 2 * r * (1 - start) / slits
    ph = (yy - (cy - r + 2 * r * start)) % period
    gap = (ph < period * (0.20 + 0.42 * rel)) & (v > start)
    disc = disc * (1 - gap)
    out = out * (1 - disc[..., None]) + V.ramp(scheme['sun'], v) * disc[..., None]
    # the water: darker, with the sun laid across it in short bars
    t = np.clip((yy - hz) / (H - hz), 0, 1)
    sea = V.ramp(scheme['sea'], t)
    rows = ((yy - hz) // max(1.0, S * 1.5)).astype(int)
    glint = np.exp(-((xx - cx) / (r * (0.5 + 1.2 * t))) ** 2) * ((rows % 2) == 0) * (1 - 0.55 * t)
    sea = V.add(sea, glint[..., None] * np.array(scheme['glint'], dtype=np.float32), 0.62)
    below = (yy >= hz)[..., None]
    out = np.where(below, sea, out)
    line = np.exp(-((yy - hz) / (S * 0.55)) ** 2)
    out = V.add(out, line[..., None] * np.array(scheme['glint'], dtype=np.float32), 0.75)
    if darken_from is not None:                       # a quieter stretch behind the label
        k = V.smoothstep(darken_from * S - W * 0.10, darken_from * S + W * 0.18, xx)[..., None] * 0.50
        out = out * (1 - k) + np.array([28, 10, 70], dtype=np.float32) * k
    return out


def label_layer(text, box_w, box_h, cap, big, face=FACE, squeeze=0.74):
    """The label in the XIFO lettering, as an RGBA layer box_w x box_h at S times the size, centred."""
    f = ImageFont.truetype(F_LABEL, 240)
    m = V.text_mask(text, f, tracking=6)
    target_h = cap * S
    sc = target_h / m.height
    tw = m.width * sc
    avail = box_w * S * 0.94
    sx = 1.0
    if tw > avail:                                    # first narrow the letters a little, then make them smaller
        sx = max(squeeze, avail / tw)
        if tw * sx > avail:
            sc *= avail / (tw * sx)
    m = m.resize((max(1, int(m.width * sc * sx)), max(1, int(m.height * sc))), Image.LANCZOS)
    pad = int(S * 6)
    M = Image.new('L', (m.width + pad * 2, m.height + pad * 2), 0)
    M.paste(m, (pad, pad))
    size = M.size
    depth = int(S * (3.2 if big else 1.8) * min(1.0, m.height / (cap * S) + 0.25))
    out_w = max(2, int(S * (2.4 if big else 1.5)))
    ext = Wv.extrude(M, max(1, depth), dx=0.7, dy=1.0)
    L = Image.new('RGBA', size, (0, 0, 0, 0))
    edge = ImageChops.lighter(ext, M).filter(ImageFilter.MaxFilter(out_w * 2 + 1)).filter(ImageFilter.GaussianBlur(S * 0.3))
    shadow = ImageChops.offset(edge, int(S * 0.8), int(S * 1.2)).filter(ImageFilter.GaussianBlur(S * 1.4))
    L.paste(Wv.solid(size, (8, 2, 30)), (0, 0), shadow.point(lambda v: int(v * 0.6)))
    L.paste(Wv.solid(size, INK), (0, 0), edge)
    e_img, _ = Wv.face_img(M, (pad, pad, pad + m.width, pad + m.height), [(0, (150, 44, 180)), (1, (70, 24, 130))])
    L.paste(e_img, (0, 0), ext)
    f_img, _ = Wv.face_img(M, (pad, pad, pad + m.width, pad + m.height), face)
    L.paste(f_img, (0, 0), M)
    bev = max(1, int(S * 0.5))
    bevel = ImageChops.subtract(M, ImageChops.offset(M, bev, bev + 1))
    L.paste(Wv.solid(size, (255, 255, 255)), (0, 0), bevel.point(lambda v: int(v * 0.8)))
    full = Image.new('RGBA', (box_w * S, box_h * S), (0, 0, 0, 0))
    Wv.paste(full, L, (box_w * S - size[0]) // 2, (box_h * S - size[1]) // 2 + int(S * 0.3))
    return full


def finish_button(arr, w, h, scheme, radius, hover=False, rim_w=None):
    """Rim, gloss and corners; returns the finished RGBA picture at its real size."""
    W, H = w * S, h * S
    rim_w = rim_w or (2.4 if h >= 90 else 1.7)
    outer = rounded((W, H), int(S * 0.8), int(radius * S))
    inner = rounded((W, H), int(S * (0.8 + rim_w)), int(max(1, radius - rim_w) * S))
    dark = rounded((W, H), int(S * (0.8 + rim_w + 0.9)), int(max(1, radius - rim_w - 0.9) * S))
    oa, ia, da = arr_of(outer), arr_of(inner), arr_of(dark)
    if hover:
        arr = np.clip(arr * 1.16 + 14, 0, 255)
    rim = np.array(scheme.get('hover', (190, 250, 255)) if hover else scheme['rim'], dtype=np.float32)
    # a soft light just inside the rim, and a gloss across the top
    inside_glow = (1 - arr_of(blur(dark, S * 2.2))) * da
    arr = V.add(arr, inside_glow[..., None] * rim, 0.55 if hover else 0.36)
    yy = np.arange(H, dtype=np.float32)[:, None] * np.ones((1, W), dtype=np.float32)
    gloss = np.clip(1 - yy / (H * 0.42), 0, 1) ** 2 * 0.10
    arr = arr + gloss[..., None] * 255
    ring_dark = np.clip(ia - da, 0, 1)[..., None]
    arr = arr * (1 - ring_dark) + np.array(INK, dtype=np.float32) * ring_dark
    ring = np.clip(oa - ia, 0, 1)[..., None]
    top = np.clip(1 - yy / (H * 0.9), 0, 1)[..., None]
    rimcol = rim * (0.80 + 0.20 * top) + 255 * 0.22 * top
    arr = arr * (1 - ring) + rimcol * ring
    img = V.to_img(arr).convert('RGBA')
    img.putalpha(outer)
    return img.resize((w, h), Image.LANCZOS)


def off_of(img):
    """Switched off: the same picture with the colour and the light taken out."""
    a = np.asarray(img, dtype=np.float32)
    rgb = a[..., :3]
    lum = (rgb * np.array([0.299, 0.587, 0.114])).sum(axis=2)[..., None]
    grey = lum * 0.86 + rgb * 0.14
    out = grey * 0.50 * np.array([0.92, 0.84, 1.10]) + np.array([14, 8, 30])
    return Image.fromarray(np.dstack([np.clip(out, 0, 255), a[..., 3]]).astype(np.uint8), 'RGBA')


def make_button(name, size=None, hover=False):
    text, parts, scheme_name = BUTTONS[name]
    w, h = size or size_of(name)
    scheme = SCHEMES[scheme_name]
    big = h >= 72
    radius = h * (0.20 if big else 0.22)
    pad = 3
    ah = h - pad * 2
    strip = figures(parts, ah * S, scheme)
    share = 0.42 if big else (0.27 if len(text) >= 12 else 0.30 if len(text) >= 7 else 0.36)
    if name.startswith('dualbox'):
        share = 0.47
    maxw = int(w * share) * S
    if strip.width > maxw:
        x0 = int((strip.width - maxw) * ANCHOR.get(name, 0.5))
        strip = strip.crop((x0, 0, x0 + maxw, strip.height))
    art_w = strip.width / S
    arr = scene(w, h, scheme, sun_x=pad + art_w * 0.52, sun_r=h * (0.40 if big else 0.42), darken_from=pad + art_w * 0.80)
    canvas = V.to_img(arr).convert('RGBA')
    # the figure fades out to the right, where the label starts
    fade = np.ones((strip.height, strip.width), dtype=np.float32)
    xs = np.linspace(0, 1, strip.width, dtype=np.float32)[None, :]
    fade = fade * (1 - V.smoothstep(0.80, 1.0, xs))
    fig = strip.copy()
    fig.putalpha(Image.fromarray((np.asarray(strip.split()[3], dtype=np.float32) * fade).astype(np.uint8), 'L'))
    halo = Image.new('RGBA', fig.size, (14, 4, 40, 0))
    halo.putalpha(fig.split()[3].filter(ImageFilter.GaussianBlur(S * 1.6)).point(lambda v: int(v * 0.55)))
    canvas.alpha_composite(halo, (pad * S, pad * S))
    canvas.alpha_composite(fig, (pad * S, pad * S))
    x0 = pad + art_w * (0.80 if big else 0.84)
    x1 = w - (h * 0.14 if big else 6)
    cap = h * (0.50 if big else 0.42)
    lab = label_layer(text, int(x1 - x0), h, cap, big, FACE_NIGHT if scheme_name == 'night' else FACE)
    canvas.alpha_composite(lab, (int(x0 * S), 0))
    return finish_button(np.asarray(canvas.convert('RGB'), dtype=np.float32), w, h, scheme, radius, hover)


def make_home(size=None, hover=False, tile=False):
    """The wordmark button: XI over FOREVER OFFLINE, on the sunset."""
    w, h = size or size_of('logo_tile' if tile else 'home')
    scheme = SCHEMES['sunset']
    arr = scene(w, h, scheme, sun_x=w / 2, sun_r=h * 0.46)
    canvas = V.to_img(arr).convert('RGBA')
    lab = label_layer('XI', int(w * 0.62), int(h * 0.74), h * 0.50, True)
    canvas.alpha_composite(lab, (int(w * 0.19 * S), int(h * 0.02 * S)))
    tag = Wv.text_img('FOREVER OFFLINE', int(h * 0.150 * S), F_SMALL, (255, 255, 255), tracking=int(h * 0.030 * S))
    if tag.width > w * S * 0.86:
        tag = tag.resize((int(w * S * 0.86), int(tag.height * w * S * 0.86 / tag.width)), Image.LANCZOS)
    tx, ty = (w * S - tag.width) // 2, int(h * S * 0.745)
    back = Image.new('RGBA', (tag.width + S * 8, tag.height + S * 4), (16, 6, 44, 0))
    back.putalpha(Image.new('L', back.size, 150).filter(ImageFilter.GaussianBlur(S)))
    canvas.alpha_composite(back, (tx - S * 4, ty - S * 2))
    glow = Image.new('RGBA', tag.size, (60, 230, 240, 0))
    glow.putalpha(tag.split()[3].filter(ImageFilter.GaussianBlur(S * 0.9)))
    canvas.alpha_composite(glow, (tx, ty))
    canvas.alpha_composite(tag, (tx, ty))
    return finish_button(np.asarray(canvas.convert('RGB'), dtype=np.float32), w, h, scheme, h * (0.10 if tile else 0.22), hover,
                         rim_w=3.2 if tile else None)


def make_header(name):
    w, h = size_of(name, (452, 44))
    W, H = w * S, h * S
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    arr = V.ramp([(0, (44, 16, 100)), (0.55, (120, 30, 150)), (1, (226, 60, 140))], yy / H)
    arr = arr * (0.55 + 0.45 * np.exp(-((xx - W / 2) / (W * 0.42)) ** 2))[..., None]
    canvas = V.to_img(arr).convert('RGBA')
    lab = label_layer(HEADERS[name], int(w * 0.62), h, h * 0.46, False)
    canvas.alpha_composite(lab, (int(w * 0.19 * S), 0))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(F_LABEL, 240)
    tw = min(w * 0.60, V.text_mask(HEADERS[name], f, tracking=6).width * (h * 0.46) / V.text_mask(HEADERS[name], f, tracking=6).height)
    for x0, x1 in ((16, w / 2 - tw / 2 - 14), (w / 2 + tw / 2 + 14, w - 16)):
        d.line([x0 * S, H / 2, x1 * S, H / 2], fill=(110, 240, 250, 255), width=int(S * 1.4))
        d.line([x0 * S, H / 2 + S * 3, x1 * S, H / 2 + S * 3], fill=(255, 90, 200, 255), width=int(S * 0.9))
    return finish_button(np.asarray(canvas.convert('RGB'), dtype=np.float32), w, h, SCHEMES['sunset'], h * 0.2)


def make_badge(name):
    text, colour = BADGES[name]
    w, h = size_of('coop_badge_' + name, (90, 22))
    W, H = w * S, h * S
    c = np.array(colour, dtype=np.float32)
    shape = rounded((W, H), int(S * 0.5), H // 2)
    inner = rounded((W, H), int(S * 2.0), H // 2)
    arr = np.ones((H, W, 3), dtype=np.float32) * (np.array([22, 10, 52], dtype=np.float32) * 0.80 + c * 0.14)
    ring = np.clip(arr_of(shape) - arr_of(inner), 0, 1)[..., None]
    arr = arr * (1 - ring) + c * ring
    img = V.to_img(arr).convert('RGBA')
    tag = Wv.text_img(text, int(11.5 * S), F_SMALL, tuple(int(v) for v in np.clip(c * 0.35 + 255 * 0.65, 0, 255)), tracking=int(0.8 * S))
    limit = int((w - 14) * S)
    if tag.width > limit:
        tag = tag.resize((limit, int(tag.height * max(0.82, limit / tag.width))), Image.LANCZOS)
    img.alpha_composite(tag, ((W - tag.width) // 2, (H - tag.height) // 2))
    img.putalpha(shape)
    return img.resize((w, h), Image.LANCZOS)


def build_all(out):
    os.makedirs(out, exist_ok=True)
    made = []
    for name in BUTTONS:
        if size_of(name) is None:
            continue
        normal = make_button(name)
        normal.save(os.path.join(out, name + '.png'))
        make_button(name, hover=True).save(os.path.join(out, name + '_hover.png'))
        off_of(normal).save(os.path.join(out, name + '_off.png'))
        made.append(name)
    home = make_home()
    home.save(os.path.join(out, 'home.png'))
    make_home(hover=True).save(os.path.join(out, 'home_hover.png'))
    off_of(home).save(os.path.join(out, 'home_off.png'))
    make_home(tile=True).save(os.path.join(out, 'logo_tile.png'))
    for name in HEADERS:
        make_header(name).save(os.path.join(out, name + '.png'))
    for name in BADGES:
        make_badge(name).save(os.path.join(out, 'coop_badge_' + name + '.png'))
    return made


def contact_sheet(out, path, bg=(18, 10, 36)):
    names = sorted(n for n in os.listdir(out) if n.endswith('.png'))
    ims = [(n, Image.open(os.path.join(out, n)).convert('RGBA')) for n in names]
    width, x, y, row_h, places = 1500, 10, 10, 0, []
    for n, im in ims:
        if x + im.width + 10 > width:
            x, y, row_h = 10, y + row_h + 10, 0
        places.append((n, im, x, y))
        x += im.width + 10
        row_h = max(row_h, im.height)
    sheet_im = Image.new('RGBA', (width, y + row_h + 10), bg + (255,))
    for n, im, px, py in places:
        sheet_im.alpha_composite(im, (px, py))
    sheet_im.convert('RGB').save(path)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:]]
    sheet_path = None
    if '--sheet' in args:
        i = args.index('--sheet')
        sheet_path = args[i + 1]
        del args[i:i + 2]
    out_dir = args[0] if args else os.path.join(KIT, 'assets', 'press', 'vaporwave-ui')
    done = build_all(out_dir)
    if sheet_path:
        contact_sheet(out_dir, sheet_path)
    print('ok:', len([n for n in os.listdir(out_dir) if n.endswith('.png')]), 'pictures in', out_dir)
