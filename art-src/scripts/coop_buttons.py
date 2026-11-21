"""The CO-OP page's art for the launcher: its bottom-bar button, the page's buttons, the two headers and the status
badges. Same look as the other buttons (build.py's dark style: a parchment cameo of official job art fading into a
coloured button, a gold chamfered frame, the label in Caladea Bold), so they sit beside PLAY, UPDATE and ADDONS.
Usage: python coop_buttons.py OUTDIR   ->  OUTDIR/ui/coop*.png (each button also as _hover and _off)
       python coop_buttons.py OUTDIR --sheet   also writes OUTDIR/coop-sheet.png (everything on one picture)"""
import os
import sys

sys.argv, _args = sys.argv[:1], sys.argv[1:]          # build.py reads its own output folder from the command line
import build
from lib import *

BLUE, GREEN, BROWN = ((52, 96, 178), (14, 30, 74)), ((44, 112, 66), (14, 42, 24)), ((132, 88, 44), (52, 32, 14))
GREY, PURPLE, RED = ((84, 86, 98), (22, 22, 28)), ((92, 46, 128), (30, 14, 46)), ((158, 46, 40), (58, 12, 12))
TEAL, STEEL = ((30, 124, 130), (8, 44, 52)), ((46, 84, 150), (14, 28, 64))
H = 48                                                 # the page's buttons are a little lower than the bottom bar's (56)

# name: (size, label, [(art, crop box)], colours)
BUTTONS = {
    'coop':          ((138, 56), 'CO-OP',           [('character-races', (0.0, 0.02, 1.0, 0.42))],  TEAL),
    'coop_on':       ((236, H),  'TURN CO-OP ON',   [('character-races', (0.0, 0.02, 1.0, 0.42))],  TEAL),
    'coop_host':     ((226, H),  'START HOSTING',   [('paladin', (0.25, 0.0, 1.0, 0.42))],          GREEN),
    'coop_stop':     ((216, H),  'STOP HOSTING',    [('dark-knight', (0.42, 0.0, 1.0, 0.62))],      GREY),
    'coop_copy':     ((196, H),  'COPY INVITE',     [('bard', (0.05, 0.0, 0.85, 0.5))],             BROWN),
    'coop_newcode':  ((168, H),  'NEW CODE',        [('black-mage', (0.15, 0.0, 0.9, 0.6))],        BROWN),
    'coop_sendhome': ((178, H),  'SEND HOME',       [('dragoon', (0.1, 0.0, 0.9, 0.36))],           STEEL),
    'coop_test':     ((244, H),  'TEST CONNECTION', [('summoner', (0.38, 0.0, 0.84, 0.5))],         STEEL),
    'coop_visit':    ((140, H),  'VISIT',           [('ranger', (0.3, 0.0, 0.8, 0.4))],             BLUE),
    'coop_play':     ((190, H),  'PLAY THERE',      [('warrior', (0.3, 0.0, 1.0, 0.75))],           BLUE),
    'coop_home':     ((186, H),  'COME HOME',       [('white-mage', (0.1, 0.08, 0.8, 0.5))],        GREEN),
    'coop_takeback': ((176, H),  'TAKE BACK',       [('samurai', (0.05, 0.0, 0.75, 0.42))],         RED),
    'coop_retry':    ((166, H),  'TRY AGAIN',       [('monk', (0.1, 0.0, 0.9, 0.5))],               BLUE),
    'coop_cancel':   ((196, H),  'CANCEL VISIT',    [('ninja', (0.08, 0.0, 0.78, 0.42))],           PURPLE),
    'coop_file':     ((176, H),  'LOAD FILE',       [('red-mage', (0.0, 0.0, 0.62, 0.45))],         BROWN),
    'coop_save':     ((226, H),  'SAVE CHARACTER',  [('shantotto', (0.1, 0.02, 0.85, 0.5))],        BROWN),
    'coop_load':     ((160, H),  'RESTORE',         [('thief', (0.2, 0.0, 0.85, 0.42))],            BROWN),
    'coop_tailscale': ((226, H), 'GET TAILSCALE',   [('ca-mithra', (0.0, 0.0, 1.0, 0.5))],          TEAL),
    # Play on another PC (2026-11-20): shorter words on the pictures so the two fit side by side
    'coop_carry_save':   ((252, H), 'SAVE FOR OTHER PC',  [('ca-children', (0.0, 0.0, 0.5, 0.75))],       BROWN),
    'coop_carry_load':   ((264, H), 'LOAD FROM OTHER PC', [('ca-mini-taru', (0.30, 0.0, 0.52, 1.0))],       BROWN),
    'coop_carry_folder': ((150, H), 'FOLDER...',          [('ca-children', (0.5, 0.0, 1.0, 0.75))],       STEEL),
}
ANCHOR = {'coop': 0.5, 'coop_on': 0.5, 'coop_play': 0.55, 'coop_stop': 0.6}
HEADERS = {'coop_head_host': 'HOST MY WORLD', 'coop_head_visit': 'VISIT A FRIEND'}
BADGES = {                                             # name: (label, colour)
    'home':        ('HOME',         (44, 128, 74)),
    'visiting':    ('VISITING',     (52, 96, 178)),
    'packed':      ('ON THE WAY',   (176, 124, 36)),
    'unreachable': ('OUT OF REACH', (158, 46, 40)),
    'playing':     ('PLAYING',      (44, 128, 74)),
    'resting':     ('IN YOUR WORLD', (70, 96, 140)),
    'leaving':     ('GOING HOME',   (176, 124, 36)),
    'open':        ('OPEN',         (44, 128, 74)),
    'closed':      ('CLOSED',       (84, 86, 98)),
    'experimental': ('EXPERIMENTAL', (158, 46, 40)),
}


def button(name):
    build.BUTTONS[name] = BUTTONS[name]
    if name in ANCHOR:
        build.ANCHOR[name] = ANCHOR[name]
    return build.make_button(name, 'dark')


def hover(img):
    big = img.height >= 90
    return frame(hover_of(img), 10 if big else 7, ((255, 244, 196), (230, 178, 70)), 3 if big else 2, hover=True, ink=(16, 12, 8))


def header(text, w=452, h=44):
    """A parchment strip with the heading in dark ink between two short rules, in the gold frame."""
    img = parchment(w, h, seed=len(text)).convert('RGBA')
    d = ImageDraw.Draw(img)
    f = font(22)
    tw = measure_spaced(d, text, f, 3)
    text_spaced(d, (w / 2, h / 2 + 1), text, f, build.INK, 3, 'mm', shadow=(1, 1, (255, 248, 228, 220)))
    for x0, x1 in ((22, w / 2 - tw / 2 - 16), (w / 2 + tw / 2 + 16, w - 22)):
        d.line((x0, h / 2 + 1, x1, h / 2 + 1), fill=(120, 86, 40, 255), width=2)
        d.polygon([(x0 - 4, h / 2 + 1), (x0, h / 2 - 3), (x0 + 4, h / 2 + 1), (x0, h / 2 + 5)] if x0 < w / 2 else
                  [(x1 - 4, h / 2 + 1), (x1, h / 2 - 3), (x1 + 4, h / 2 + 1), (x1, h / 2 + 5)], fill=(120, 86, 40, 255))
    return frame(img, 7, build.GOLD, 2, ink=build.INK)


def badge(text, colour, h=22):
    """A small coloured tag with a light rim: what a character or the world is doing right now."""
    f = font(12)
    probe = ImageDraw.Draw(Image.new('RGBA', (4, 4)))
    w = int(measure_spaced(probe, text, f, 1)) + 22
    S = 3
    big = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    dark = tuple(int(v * 0.45) for v in colour)
    light = tuple(min(255, int(v * 1.5) + 40) for v in colour)
    d.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=h * S // 2, fill=dark + (255,))
    d.rounded_rectangle((S, S, w * S - 1 - S, h * S - 1 - S), radius=h * S // 2 - S, fill=colour + (255,), outline=light + (255,), width=S)
    img = big.resize((w, h), Image.LANCZOS)
    text_spaced(ImageDraw.Draw(img), (w / 2, h / 2), text, f, (255, 250, 236), 1, 'mm', shadow=(1, 1, (0, 0, 0, 170)))
    return img


def build_all(out):
    folder = os.path.join(out, 'ui')
    os.makedirs(folder, exist_ok=True)
    made = {}
    for name in BUTTONS:
        img = button(name)
        made[name] = img
        img.save(os.path.join(folder, f'{name}.png'))
        hover(img).save(os.path.join(folder, f'{name}_hover.png'))
        grayscale_off(img).save(os.path.join(folder, f'{name}_off.png'))
    for name, text in HEADERS.items():
        made[name] = header(text)
        made[name].save(os.path.join(folder, f'{name}.png'))
    for name, (text, colour) in BADGES.items():
        made['coop_badge_' + name] = badge(text, colour)
        made['coop_badge_' + name].save(os.path.join(folder, f'coop_badge_{name}.png'))
    return made


def sheet(made, out):
    """Everything on the launcher's background colour, to look it over before it goes in."""
    w, pad = 980, 18
    rows, row, x = [], [], pad
    for name in list(BUTTONS) + list(HEADERS) + ['coop_badge_' + b for b in BADGES]:
        img = made[name]
        if x + img.width + pad > w and row:
            rows.append(row)
            row, x = [], pad
        row.append(img)
        x += img.width + pad
    rows.append(row)
    height = pad + sum(max(i.height for i in r) + pad for r in rows)
    page = Image.new('RGBA', (w, height), (10, 17, 24, 255))
    y = pad
    for r in rows:
        x = pad
        for img in r:
            page.alpha_composite(img, (x, y))
            x += img.width + pad
        y += max(i.height for i in r) + pad
    page.convert('RGB').save(os.path.join(out, 'coop-sheet.png'))


if __name__ == '__main__':
    out = _args[0] if _args and not _args[0].startswith('--') else 'out'
    made = build_all(out)
    if '--sheet' in _args:
        sheet(made, out)
    print('ok', len(made))
