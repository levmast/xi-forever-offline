"""Build launcher buttons (two styles) and banners from the FFXI gallery art.
Usage: python3 build.py OUTDIR
Writes OUTDIR/dark/ui/*.png, OUTDIR/parchment/ui/*.png, OUTDIR/press/*.png"""
import sys
from lib import *

OUT = sys.argv[1] if len(sys.argv) > 1 else 'out'

# name: (size, label, [(art, crop box), ...], dark theme (top, bottom), accent)
BUTTONS = {
    'play':     ((270, 96), 'PLAY',     [('warrior', (0.0, 0.0, 1.0, 0.92))],                     ((52, 96, 178), (14, 30, 74))),
    'stop':     ((270, 96), 'STOP',     [('dark-knight', (0.0, 0.0, 1.0, 0.95))],                 ((84, 86, 98), (22, 22, 28))),
    'dualbox':  ((325, 96), 'DUALBOX',  [('red-mage', (0.0, 0.0, 0.62, 0.5)), ('white-mage', (0.12, 0.0, 0.92, 0.45))], ((52, 96, 178), (14, 30, 74))),
    'home':     ((133, 56), None,       [],                                                       ((236, 240, 248), (190, 204, 228))),
    'squad':    ((134, 56), 'SQUAD',    [('job-art', (0.18, 0.0, 0.82, 0.42))],                   ((36, 58, 112), (12, 20, 46))),
    'config':   ((125, 56), 'CONFIG',   [('summoner', (0.38, 0.0, 0.84, 0.5))],                   ((46, 84, 150), (14, 28, 64))),
    'tools':    ((151, 56), 'TOOLS',    [('beastmaster', (0.0, 0.0, 0.8, 0.55))],                 ((132, 88, 44), (52, 32, 14))),
    'settings': ((189, 56), 'SETTINGS', [('black-mage', (0.15, 0.0, 0.9, 0.62))],                 ((132, 88, 44), (52, 32, 14))),
    'exit':     ((133, 56), 'EXIT',     [('ninja', (0.08, 0.0, 0.78, 0.42))],                     ((92, 46, 128), (30, 14, 46))),
    'update':   ((142, 56), 'UPDATE',   [('dragoon', (0.0, 0.0, 1.0, 0.4))],                      ((44, 112, 66), (14, 42, 24))),
    'logs':     ((130, 56), 'LOGS',     [('bard', (0.12, 0.0, 0.88, 0.55))],                      ((120, 78, 40), (46, 28, 12))),
    # the bottom bar of the newer look (2026-11-20): HOME, WORLD, RULES, SQUADS, OPTIONS, CO-OP, SYSTEM, EXIT
    'world':    ((126, 56), 'WORLD',    [('character-races', (0.04, 0.02, 0.31, 0.30))],          ((44, 112, 66), (14, 42, 24))),
    'rules':    ((120, 56), 'RULES',    [('summoner', (0.38, 0.0, 0.84, 0.5))],                   ((46, 84, 150), (14, 28, 64))),
    'options':  ((132, 56), 'OPTIONS',  [('beastmaster', (0.0, 0.0, 0.8, 0.55))],                 ((118, 48, 60), (44, 16, 24))),
    'system':   ((140, 56), 'SYSTEM',   [('black-mage', (0.15, 0.0, 0.9, 0.62))],                 ((132, 88, 44), (52, 32, 14))),
}

ANCHOR = {'play': 0.62, 'stop': 0.7, 'squad': 0.5, 'update': 0.3, 'tools': 0.35, 'options': 0.35}
ART_SHARE = {'options': 0.27}      # how much of a small button the art may take (0.36 unless named here): a long word needs the room
SUBTITLE = False
GOLD = ((252, 230, 158), (170, 120, 40))
INK = (52, 34, 18)


def art_strip(parts, h, bg):
    """The art pieces side by side, each scaled to height h, multiplied onto bg (RGB)."""
    pieces = [fit_h(crop_frac(load(f'ff11-{a}.jpg'), box), h) for a, box in parts]
    w = sum(p.width for p in pieces) - (len(pieces) - 1) * int(h * 0.12)
    strip = Image.new('RGB', (max(1, w), h), (255, 255, 255))
    x = 0
    for p in pieces:
        strip = ImageChops.multiply(strip, _place(p, strip.size, x))
        x += p.width - int(h * 0.12)
    return strip


def _place(p, size, x):
    canvas = Image.new('RGB', size, (255, 255, 255))
    canvas.paste(p, (x, 0))
    return canvas


def logo_layer(w, h, dark):
    """FINAL FANTASY XI crest and title (the ONLINE line removed) with our own OFFLINE line, as RGBA."""
    src = load('ff11-logo (1).jpg')
    top = src.crop((30, 0, 945, 503))
    lay = unwhite(top)
    if dark:
        a = np.asarray(lay).astype(np.float32)
        rgb = a[..., :3]
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        darkish = (sat < 40)
        rgb[darkish] = 255 - rgb[darkish] * 0.15
        lay = Image.fromarray(np.dstack([rgb, a[..., 3]]).astype(np.uint8), 'RGBA')
    sub_h = int(top.height * 0.16)
    full = Image.new('RGBA', (top.width, top.height + sub_h), (0, 0, 0, 0))
    full.alpha_composite(lay, (0, 0))
    d = ImageDraw.Draw(full)
    f = font(int(sub_h * 0.62))
    col = (240, 232, 210, 255) if dark else (24, 24, 30, 255)
    bar = (120, 150, 210, 255) if dark else (60, 86, 150, 255)
    tw = measure_spaced(d, 'OFFLINE', f, int(sub_h * 0.35))
    cy = top.height + sub_h * 0.45
    text_spaced(d, (full.width / 2, cy), 'OFFLINE', f, col, int(sub_h * 0.35), 'mm')
    bh = max(2, sub_h // 9)
    for x0, x1 in ((20, full.width / 2 - tw / 2 - 24), (full.width / 2 + tw / 2 + 24, full.width - 20)):
        d.rectangle((x0, cy - bh / 2, x1, cy + bh / 2), fill=bar)
    full.thumbnail((w, h), Image.LANCZOS)
    return full


def label(img, text, x0, x1, dark, big):
    d = ImageDraw.Draw(img)
    w, h = img.size
    avail = x1 - x0
    size = 50 if big else 24
    spacing = 2 if big else 1
    while size > 10:
        f = font(size)
        if measure_spaced(d, text, f, spacing) <= avail:
            break
        size -= 1
    cx = (x0 + x1) / 2
    cy = h * 0.5 + (2 if big else 1)
    fg = (255, 250, 236) if dark else INK
    sh = (0, 0, 0, 200) if dark else (255, 248, 228, 220)
    text_spaced(d, (cx, cy), text, f, fg, spacing, 'mm', shadow=(2, 2, sh) if big else (1, 1, sh))
    if not SUBTITLE:
        return
    # subtitle with small rules
    sf = font(11 if big else 7)
    sub = 'FINAL FANTASY XI'
    sy = h * (0.80 if big else 0.78)
    sw = measure_spaced(d, sub, sf, 1)
    subcol = (226, 206, 150) if dark else (120, 86, 40)
    if sw > avail - 2:
        return
    text_spaced(d, (cx, sy), sub, sf, subcol, 1, 'mm')
    rule = int(min(26 if big else 10, (avail - sw) / 2 - 4))
    if rule > 3:
        d.line((cx - sw / 2 - 4 - rule, sy, cx - sw / 2 - 4, sy), fill=subcol, width=1)
        d.line((cx + sw / 2 + 4, sy, cx + sw / 2 + 4 + rule, sy), fill=subcol, width=1)


def make_button(name, style):
    (w, h), text, parts, theme = BUTTONS[name]
    big = h >= 90
    dark = style == 'dark'
    c = 10 if big else 7
    if dark:
        bg = vgrad(w, h, theme[0], theme[1])
        glow, gm = radial(w, h, w * 0.62, h * 0.4, w * 0.45, tuple(min(255, int(v * 1.6) + 30) for v in theme[0]), 0.45)
        bg = Image.composite(glow, bg, gm)
    else:
        bg = parchment(w, h, seed=len(name))
    img = bg.convert('RGBA')
    if name == 'home':
        if dark:
            img = vgrad(w, h, (238, 242, 250), (196, 208, 230)).convert('RGBA')
        lay = logo_layer(w - 16, h - 10, dark=False)
        img.alpha_composite(lay, ((w - lay.width) // 2, (h - lay.height) // 2 + 1))
        return frame(img, c, GOLD if not dark else ((236, 242, 255), (80, 120, 196)), 3 if big else 2, ink=(20, 26, 48) if dark else INK)
    ah = h - 6
    strip = art_strip(parts, ah, None)
    maxw = int(w * (0.44 if big else ART_SHARE.get(name, 0.36)))
    if name == 'dualbox':
        maxw = int(w * 0.5)
    if strip.width > maxw:
        strip = cover(strip, maxw, ah, ANCHOR.get(name, 0.5), 0.0)
    pw = strip.width + int(h * 0.45)
    if dark:
        # a parchment cameo behind the art that fades into the dark button
        cam = parchment(pw, h, seed=7)
        cam.paste(ImageChops.multiply(cam.crop((4, 3, 4 + strip.width, 3 + ah)), strip), (4, 3))
        mask = hgrad_mask(pw, h, (strip.width * 0.72) / pw, 1.0)
        img.paste(cam, (0, 0), mask)
        # dark edge on the right of the cameo to separate the label
    else:
        region = img.convert('RGB').crop((4, 3, 4 + strip.width, 3 + ah))
        art = ImageChops.multiply(region, strip)
        # fade the art's right edge into the paper
        m = hgrad_mask(strip.width, ah, 0.78, 1.0)
        base = img.convert('RGB')
        base.paste(art, (4, 3), m)
        img = base.convert('RGBA')
    x0 = 4 + strip.width - (int(h * 0.1) if big else 2)
    label(img, text, x0, w - (14 if big else 7), dark, big)
    return frame(img, c, GOLD, 3 if big else 2, ink=INK if not dark else (16, 12, 8))


def logo_tile(style):
    w, h = 442, 186
    dark = style == 'dark'
    img = (vgrad(w, h, (238, 242, 250), (196, 208, 230)) if dark else parchment(w, h, 11)).convert('RGBA')
    lay = logo_layer(w - 50, h - 30, dark=False)
    img.alpha_composite(lay, ((w - lay.width) // 2, (h - lay.height) // 2 + 2))
    return frame(img, 14, GOLD if not dark else ((236, 242, 255), (80, 120, 196)), 4, ink=INK if not dark else (20, 26, 48))


def save_set(style):
    folder = os.path.join(OUT, style, 'ui')
    os.makedirs(folder, exist_ok=True)
    for name in BUTTONS:
        im = make_button(name, style)
        im.save(os.path.join(folder, f'{name}.png'))
        hv = hover_of(im)
        # hover: brighter, with a stronger frame
        hv = frame(hv, 10 if im.height >= 90 else 7, ((255, 244, 196), (230, 178, 70)), 3 if im.height >= 90 else 2, hover=True,
                   ink=INK if style == 'parchment' else (16, 12, 8)) if name != 'home' else hv
        hv.save(os.path.join(folder, f'{name}_hover.png'))
        grayscale_off(im).save(os.path.join(folder, f'{name}_off.png'))
    logo_tile(style).save(os.path.join(folder, 'logo_tile.png'))


if __name__ == '__main__':
    for s in ('dark', 'parchment'):
        save_set(s)
    print('ok')
