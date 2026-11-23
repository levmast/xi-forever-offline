"""The launcher's buttons for the 8-Bit theme (assets\\press\\8bit-ui): every button as a console-RPG menu window, drawn in
real pixels (one drawn pixel = 2 x 2 on screen), with a sprite from art-src\\8bit-sprites standing in it and the label in
a 5 x 7 pixel font that is defined below. Hover: the window lights up and the sprite cheers. Off: grey, and it kneels.

The sprites are the battle and map sprites of the "Records of Vana'diel" pack (see art-src\\8bit-sprites\\README.txt).
The window, the two fonts and everything else here is drawn by this script; nothing is copied from a game's interface.

Every picture gets exactly the size of the usual one in assets\\ui, under the same file name, so the theme's .json
("art": {"folder": "8bit-ui"}) is all the launcher needs. A new launcher button needs a line in BUTTONS, or it keeps its
usual picture while the theme is worn.

    python bit_buttons.py [OUTDIR] [--sheet FILE]        needs Pillow; about a second
"""
import os
import sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, '..', '..'))
UI = os.environ.get('XIFO_UI', os.path.join(KIT, 'assets', 'ui'))                     # the usual buttons: their sizes are read from here
SPRITES = os.environ.get('XIFO_SPRITES', os.path.join(KIT, 'art-src', '8bit-sprites'))
PX = 2                                                                                 # one drawn pixel is this many on screen

WHO = {'knight': 'P001', 'thief': 'P002', 'monk': 'P003', 'white': 'P005', 'black': 'P006'}   # P004 is left out (see the README there)

# name: (label, [(who, pose)], window)      window: 'blue', or 'red' for the buttons that stop or leave something
BUTTONS = {
    'play':     ('PLAY',     [('knight', 'Ready_00'), ('monk', 'Ready_00'), ('black', 'SkillReady_00')], 'blue'),
    'stop':     ('STOP',     [('white', 'Dying_00'), ('knight', 'Down_00')], 'red'),
    'dualbox':  ('DUALBOX',  [('thief', 'Ready_00'), ('monk', 'Ready_00')], 'blue'),
    'dualbox_small': ('DUALBOX', [('thief', 'Ready_00'), ('monk', 'Ready_00')], 'blue'),
    'squad':    ('SQUADS',   [('monk', 'Ready_00')], 'blue'),
    'config':   ('CONFIG',   [('black', 'SkillReady_00')], 'blue'),
    'tools':    ('TOOLS',    [('thief', 'SkillReady_00')], 'blue'),
    'addons':   ('ADDONS',   [('knight', 'SkillReady_00')], 'blue'),
    'settings': ('SETTINGS', [('black', 'Default_00')], 'blue'),
    'exit':     ('EXIT',     [('thief', 'Damage_00')], 'red'),
    'update':   ('UPDATE',   [('monk', 'RightAttack_00')], 'blue'),
    'logs':     ('LOGS',     [('white', 'SkillReady_00')], 'blue'),
    'world':    ('WORLD',    [('knight', 'Default_00')], 'blue'),
    'rules':    ('RULES',    [('white', 'SkillReady_00')], 'blue'),
    'options':  ('OPTIONS',  [('thief', 'Default_00')], 'blue'),
    'system':   ('SYSTEM',   [('black', 'Default_00')], 'blue'),
    'coop':          ('CO-OP',           [('white', 'Default_00')], 'blue'),
    'coop_on':       ('TURN CO-OP ON',   [('white', 'Ready_00')], 'blue'),
    'coop_host':     ('START HOSTING',   [('knight', 'Ready_00')], 'blue'),
    'coop_stop':     ('STOP HOSTING',    [('knight', 'Dying_00')], 'red'),
    'coop_copy':     ('COPY INVITE',     [('white', 'SkillReady_00')], 'blue'),
    'coop_newcode':  ('NEW CODE',        [('black', 'SkillReady_00')], 'blue'),
    'coop_sendhome': ('SEND HOME',       [('black', 'RightAttack_00')], 'red'),
    'coop_test':     ('TEST CONNECTION', [('thief', 'SkillReady_00')], 'blue'),
    'coop_visit':    ('VISIT',           [('monk', 'Default_00')], 'blue'),
    'coop_play':     ('PLAY THERE',      [('knight', 'RightAttack_00')], 'blue'),
    'coop_home':     ('COME HOME',       [('white', 'Default_00')], 'blue'),
    'coop_takeback': ('TAKE BACK',       [('monk', 'RightAttack_00')], 'red'),
    'coop_retry':    ('TRY AGAIN',       [('monk', 'Ready_00')], 'blue'),
    'coop_cancel':   ('CANCEL VISIT',    [('thief', 'Damage_00')], 'red'),
    'coop_file':     ('LOAD FILE',       [('thief', 'Default_00')], 'blue'),
    'coop_save':     ('SAVE CHARACTER',  [('black', 'Default_00')], 'blue'),
    'coop_load':     ('RESTORE',         [('white', 'Ready_00')], 'blue'),
    'coop_tailscale': ('GET TAILSCALE',  [('thief', 'Ready_00')], 'blue'),
    'coop_carry_save':   ('SAVE FOR OTHER PC',  [('knight', 'Default_00')], 'blue'),
    'coop_carry_load':   ('LOAD FROM OTHER PC', [('monk', 'Default_00')], 'blue'),
    'coop_carry_folder': ('FOLDER...',          [('black', 'Ready_00')], 'red'),
}
BIG = {'play': 3, 'stop': 3}                           # their label is this many times the usual size
HEADERS = {'coop_head_host': ('HOST MY WORLD', ['knight', 'white']), 'coop_head_visit': ('VISIT A FRIEND', ['thief', 'monk'])}
BADGES = {                                             # name: (label, colour)
    'home':        ('HOME',          (88, 248, 156)),
    'visiting':    ('VISITING',      (92, 216, 252)),
    'packed':      ('ON THE WAY',    (252, 208, 64)),
    'unreachable': ('OUT OF REACH',  (252, 92, 92)),
    'playing':     ('PLAYING',       (88, 248, 156)),
    'resting':     ('IN YOUR WORLD', (164, 176, 236)),
    'leaving':     ('GOING HOME',    (252, 208, 64)),
    'open':        ('OPEN',          (88, 248, 156)),
    'closed':      ('CLOSED',        (164, 176, 236)),
    'experimental': ('EXPERIMENTAL', (252, 92, 92)),
}

INK = (6, 8, 28)                                       # the outline round every window, and the shadow under the lettering
WHITE, YELLOW, GREY = (252, 252, 252), (252, 208, 64), (150, 154, 180)
WINDOWS = {                                            # (the bands of the fill from top to bottom, the frame)
    'blue':       ([(56, 84, 232), (40, 64, 208), (28, 46, 176), (20, 32, 144), (14, 22, 112)], WHITE),
    'blue_hover': ([(100, 140, 252), (72, 108, 244), (48, 82, 224), (32, 58, 192), (22, 38, 156)], YELLOW),
    'red':        ([(216, 60, 76), (184, 40, 60), (152, 28, 48), (120, 18, 40), (88, 12, 32)], WHITE),
    'red_hover':  ([(252, 108, 112), (228, 76, 88), (196, 52, 68), (160, 34, 52), (120, 20, 40)], YELLOW),
    'off':        ([(88, 92, 120), (72, 76, 104), (58, 62, 90), (46, 50, 76), (36, 40, 64)], (140, 144, 168)),
}
GOLD_RAMP = [(252, 252, 220), (252, 240, 144), (252, 216, 72), (252, 184, 40), (240, 144, 24), (216, 104, 16), (176, 72, 16)]

# ------------------------------------------------------------------ the two fonts
FONT = {
    'A': ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'B': ['####.', '#...#', '#...#', '####.', '#...#', '#...#', '####.'],
    'C': ['.###.', '#...#', '#....', '#....', '#....', '#...#', '.###.'],
    'D': ['####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'],
    'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
    'F': ['#####', '#....', '#....', '####.', '#....', '#....', '#....'],
    'G': ['.###.', '#...#', '#....', '#.###', '#...#', '#...#', '.###.'],
    'H': ['#...#', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'I': ['###', '.#.', '.#.', '.#.', '.#.', '.#.', '###'],
    'J': ['..###', '...#.', '...#.', '...#.', '...#.', '#..#.', '.##..'],
    'K': ['#...#', '#..#.', '#.#..', '##...', '#.#..', '#..#.', '#...#'],
    'L': ['#....', '#....', '#....', '#....', '#....', '#....', '#####'],
    'M': ['#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'],
    'N': ['#...#', '##..#', '#.#.#', '#..##', '#...#', '#...#', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
    'Q': ['.###.', '#...#', '#...#', '#...#', '#.#.#', '#..#.', '.##.#'],
    'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    'U': ['#...#', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'V': ['#...#', '#...#', '#...#', '#...#', '#...#', '.#.#.', '..#..'],
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'],
    'X': ['#...#', '#...#', '.#.#.', '..#..', '.#.#.', '#...#', '#...#'],
    'Y': ['#...#', '#...#', '.#.#.', '..#..', '..#..', '..#..', '..#..'],
    'Z': ['#####', '....#', '...#.', '..#..', '.#...', '#....', '#####'],
    '0': ['.###.', '#...#', '#..##', '#.#.#', '##..#', '#...#', '.###.'],
    '1': ['.#.', '##.', '.#.', '.#.', '.#.', '.#.', '###'],
    '2': ['.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'],
    '3': ['####.', '....#', '....#', '.###.', '....#', '....#', '####.'],
    '4': ['...#.', '..##.', '.#.#.', '#..#.', '#####', '...#.', '...#.'],
    '5': ['#####', '#....', '####.', '....#', '....#', '#...#', '.###.'],
    '6': ['.###.', '#....', '#....', '####.', '#...#', '#...#', '.###.'],
    '7': ['#####', '....#', '...#.', '..#..', '..#..', '..#..', '..#..'],
    '8': ['.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '.###.'],
    '9': ['.###.', '#...#', '#...#', '.####', '....#', '....#', '.###.'],
    '-': ['....', '....', '....', '####', '....', '....', '....'],
    '.': ['.', '.', '.', '.', '.', '.', '#'],
    ':': ['.', '.', '#', '.', '.', '#', '.'],
    "'": ['#', '#', '.', '.', '.', '.', '.'],
    '!': ['#', '#', '#', '#', '#', '.', '#'],
    '?': ['.###.', '#...#', '....#', '...#.', '..#..', '.....', '..#..'],
    '/': ['....#', '....#', '...#.', '..#..', '.#...', '#....', '#....'],
    '+': ['.....', '..#..', '..#..', '#####', '..#..', '..#..', '.....'],
    '>': ['#...', '##..', '###.', '####', '###.', '##..', '#...'],
    ' ': ['...'] * 7,
}
MICRO = {
    'A': ['.#.', '#.#', '###', '#.#', '#.#'], 'B': ['##.', '#.#', '##.', '#.#', '##.'], 'C': ['.##', '#..', '#..', '#..', '.##'],
    'D': ['##.', '#.#', '#.#', '#.#', '##.'], 'E': ['###', '#..', '##.', '#..', '###'], 'F': ['###', '#..', '##.', '#..', '#..'],
    'G': ['.##', '#..', '#.#', '#.#', '.##'], 'H': ['#.#', '#.#', '###', '#.#', '#.#'], 'I': ['###', '.#.', '.#.', '.#.', '###'],
    'J': ['..#', '..#', '..#', '#.#', '.#.'], 'K': ['#.#', '#.#', '##.', '#.#', '#.#'], 'L': ['#..', '#..', '#..', '#..', '###'],
    'M': ['#.#', '###', '###', '#.#', '#.#'], 'N': ['###', '#.#', '#.#', '#.#', '#.#'], 'O': ['###', '#.#', '#.#', '#.#', '###'],
    'P': ['###', '#.#', '###', '#..', '#..'], 'Q': ['###', '#.#', '#.#', '###', '..#'], 'R': ['##.', '#.#', '##.', '#.#', '#.#'],
    'S': ['.##', '#..', '.#.', '..#', '##.'], 'T': ['###', '.#.', '.#.', '.#.', '.#.'], 'U': ['#.#', '#.#', '#.#', '#.#', '###'],
    'V': ['#.#', '#.#', '#.#', '#.#', '.#.'], 'W': ['#.#', '#.#', '###', '###', '#.#'], 'X': ['#.#', '#.#', '.#.', '#.#', '#.#'],
    'Y': ['#.#', '#.#', '.#.', '.#.', '.#.'], 'Z': ['###', '..#', '.#.', '#..', '###'], '-': ['...', '...', '###', '...', '...'],
    '.': ['.', '.', '.', '.', '#'], ':': ['.', '#', '.', '#', '.'], ' ': ['..'] * 5,
}


def text_size(text, font=FONT, scale=1, gap=1):
    widths = [len(font[c][0]) for c in text]
    return (sum(widths) + gap * (len(text) - 1)) * scale, len(font['A']) * scale


def draw_text(img, x, y, text, colour, font=FONT, scale=1, gap=1, shadow=INK, ramp=None):
    """The text with its top left at (x, y). shadow: a second copy down and right (one pixel, two for large lettering), drawn
    first. ramp: a colour for each row of the letters from top to bottom, in place of the one colour (the gold lettering)."""
    px = img.load()
    w, h = img.size
    rows = len(font['A'])
    drop = min(scale, 2)
    for dx, dy, shade in (([(1, 1, shadow)] if shadow else []) + [(0, 0, None)]):
        cx = x
        for c in text:
            glyph = font[c]
            for r, line in enumerate(glyph):
                for k, bit in enumerate(line):
                    if bit != '#':
                        continue
                    if shade is not None:
                        paint = shade
                    elif ramp:
                        paint = None
                    else:
                        paint = colour
                    for sy in range(scale):
                        for sx in range(scale):
                            X, Y = cx + k * scale + sx + dx * drop, y + r * scale + sy + dy * drop
                            if 0 <= X < w and 0 <= Y < h:
                                if paint is None:
                                    px[X, Y] = ramp[min(len(ramp) - 1, (r * scale + sy) * len(ramp) // (rows * scale))] + (255,)
                                else:
                                    px[X, Y] = paint + (255,)
            cx += (len(glyph[0]) + gap) * scale
    return img


# ------------------------------------------------------------------ the window
def window(w, h, kind):
    """A menu window w x h drawn pixels: a dark outline with the corners cut, a one-pixel frame, and a fill in five bands with a
    dithered row where two bands meet."""
    bands, frame = WINDOWS[kind]
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    px = img.load()
    top, bottom = 2, h - 3
    span = max(1, bottom - top + 1)
    for y in range(h):
        for x in range(w):
            edge = min(x, y, w - 1 - x, h - 1 - y)
            corner = (x in (0, w - 1)) + (y in (0, h - 1))
            if edge == 0:
                if corner == 2:
                    continue                                    # the four corner pixels stay clear
                px[x, y] = INK + (255,)
            elif edge == 1:
                inner_corner = (x in (1, w - 2)) and (y in (1, h - 2))
                px[x, y] = (INK if inner_corner else frame) + (255,)
            else:
                position = (y - top) * len(bands) / span
                band = min(len(bands) - 1, int(position))
                colour = bands[band]
                if band + 1 < len(bands) and int((y + 1 - top) * len(bands) / span) > band and (x + y) % 2:
                    colour = bands[band + 1]                    # the last row of a band: every other pixel is already the next one
                if (x in (2, w - 3)) and (y in (2, h - 3)):
                    colour = frame                              # the frame's inner corners, rounded
                px[x, y] = colour + (255,)
    return img


# ------------------------------------------------------------------ the sprites
_SPRITES = {}


def sprite(who, pose, kind='battle'):
    key = (who, pose, kind)
    if key not in _SPRITES:
        path = os.path.join(SPRITES, kind, WHO[who], pose + '.png')
        img = Image.open(path).convert('RGBA')
        _SPRITES[key] = img.crop(img.getbbox())
    return _SPRITES[key]


def greyed(img):
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a:
                v = int((0.30 * r + 0.59 * g + 0.11 * b) * 0.72) + 12
                px[x, y] = (v, v, min(255, v + 14), a)
    return out


def posed(figures, state):
    """The figures for a state: as listed, cheering on hover (those that are down stay down), grey and kneeling when off."""
    out = []
    for who, pose in figures:
        if state == 'hover' and pose not in ('Down_00', 'Dying_00', 'Damage_00'):
            pose = 'Win_00'
        elif state == 'off' and pose != 'Down_00':
            pose = 'Dying_00'
        img = sprite(who, pose)
        out.append(greyed(img) if state == 'off' else img)
    return out


# ------------------------------------------------------------------ putting a button together
def size_of(name):
    path = os.path.join(UI, name + '.png')
    if not os.path.exists(path):
        return None
    with Image.open(path) as im:
        return im.size


def to_screen(art, size):
    """The drawn picture at PX times its size (hard pixels), centred on a clear picture of the size the launcher expects."""
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    big = art.resize((art.width * PX, art.height * PX), Image.NEAREST)
    out.paste(big, ((size[0] - big.width) // 2, (size[1] - big.height) // 2))
    return out


def make_button(name, state='normal'):
    label, figures, kind = BUTTONS[name]
    size = size_of(name)
    w, h = size[0] // PX, size[1] // PX
    style = 'off' if state == 'off' else kind + ('_hover' if state == 'hover' else '')
    art = window(w, h, style)
    scale = BIG.get(name, 2 if h >= 36 else 1)
    colour = GREY if state == 'off' else (252, 236, 144) if state == 'hover' else WHITE
    tw, th = text_size(label, scale=scale)
    room = w - 6                                           # inside the frame, a pixel of air each side
    people = posed(figures, state)
    gap = 2 if h < 36 else 4
    while people and sum(p.width for p in people) + (len(people) - 1) + gap + tw > room:
        people = people[:-1]                               # not enough room: one figure fewer
    cursor = state == 'hover' and sum(p.width for p in people) + (len(people) - 1) + gap + tw + 6 * scale <= room
    total = sum(p.width for p in people) + max(0, len(people) - 1) + (gap if people else 0) + tw + (6 * scale if cursor else 0)
    x = (w - total) // 2
    ty = (h - th) // 2
    floor = h - 2                                          # the figures stand on the frame; in a low window their feet are behind it
    if h >= 36:
        floor = min(h - 3, max(ty + th + 2, (h + 26) // 2))   # a tall window: figures and words share one line across the middle
    for person in people:
        top = floor - person.height
        if top < 1:                                        # taller than the window: from the head down, cut at the frame
            person = person.crop((0, 0, person.width, h - 3))
            top = 1
        art.alpha_composite(person, (x, top))
        x += person.width + 1
    if people:
        x += gap - 1
    if cursor:
        draw_text(art, x, ty, '>', YELLOW, scale=scale)
        x += 6 * scale
    draw_text(art, x, ty, label, colour, scale=scale, shadow=None if state == 'off' else INK)
    return to_screen(art, size)


def make_home(state='normal', name='home'):
    """The wordmark button: XI in gold lettering, FOREVER OFFLINE beside it in the small font."""
    size = size_of(name)
    w, h = size[0] // PX, size[1] // PX
    art = window(w, h, 'off' if state == 'off' else 'blue_hover' if state == 'hover' else 'blue')
    xi_w, xi_h = text_size('XI', scale=2)
    top_w, _ = text_size('FOREVER', MICRO)
    total = xi_w + 3 + top_w
    x = (w - total) // 2
    ramp = [GREY] if state == 'off' else GOLD_RAMP
    draw_text(art, x, (h - xi_h) // 2, 'XI', WHITE, scale=2, ramp=ramp, shadow=None if state == 'off' else INK)
    colour = GREY if state == 'off' else WHITE
    draw_text(art, x + xi_w + 3, h // 2 - 6, 'FOREVER', colour, MICRO, shadow=None if state == 'off' else INK)
    draw_text(art, x + xi_w + 3, h // 2 + 1, 'OFFLINE', colour, MICRO, shadow=None if state == 'off' else INK)
    return to_screen(art, size)


def make_tile():
    """The wordmark tile: a title screen. XI in tall gold lettering, FOREVER OFFLINE under it, the party in a row."""
    size = size_of('logo_tile')
    w, h = size[0] // PX, size[1] // PX
    art = window(w, h, 'blue')
    xi_w, xi_h = text_size('XI', scale=5)
    draw_text(art, (w - xi_w) // 2, 6, 'XI', WHITE, scale=5, ramp=GOLD_RAMP, shadow=INK)
    sub_w, sub_h = text_size('FOREVER OFFLINE', scale=1, gap=2)
    draw_text(art, (w - sub_w) // 2, 6 + xi_h + 5, 'FOREVER OFFLINE', WHITE, gap=2)
    party = [sprite(who, 'Ready_00') for who in ('thief', 'monk', 'knight', 'white', 'black')]
    total = sum(p.width for p in party) + 6 * (len(party) - 1)
    x = (w - total) // 2
    for person in party:
        art.alpha_composite(person, (x, h - 4 - person.height))
        x += person.width + 6
    return to_screen(art, size)


def make_header(name):
    """A strip heading a part of the Co-op page: two map sprites walking in, then the words."""
    label, walkers = HEADERS[name]
    size = size_of(name)
    w, h = size[0] // PX, size[1] // PX
    art = window(w, h, 'blue')
    x = 6
    for i, who in enumerate(walkers):
        person = sprite(who, 'WalkL_0%d' % (i % 2), 'map').transpose(Image.FLIP_LEFT_RIGHT)
        art.alpha_composite(person, (x, h - 3 - person.height))
        x += person.width + 2
    tw, th = text_size(label, scale=2)
    if x + 4 + tw > w - 6:
        tw, th = text_size(label)
        draw_text(art, x + 4, (h - th) // 2, label, WHITE)
    else:
        draw_text(art, x + 4, (h - th) // 2, label, WHITE, scale=2, ramp=GOLD_RAMP)
    return to_screen(art, size)


def make_badge(name):
    """A small tag: a dark plate with a frame and the words in the badge's colour, in the small font."""
    label, colour = BADGES[name]
    size = size_of('coop_badge_' + name)
    w, h = size[0] // PX, size[1] // PX
    art = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    px = art.load()
    for y in range(h):
        for x in range(w):
            edge = min(x, y, w - 1 - x, h - 1 - y)
            if edge == 0 and (x in (0, w - 1)) and (y in (0, h - 1)):
                continue
            px[x, y] = (colour if edge == 0 else (10, 14, 56)) + (255,)
    tw, th = text_size(label, MICRO)
    draw_text(art, (w - tw) // 2, (h - th) // 2, label, colour, MICRO, shadow=None)
    return to_screen(art, size)


def build_all(out):
    os.makedirs(out, exist_ok=True)
    made = []
    for name in BUTTONS:
        if size_of(name) is None:
            continue
        for state, ending in (('normal', ''), ('hover', '_hover'), ('off', '_off')):
            make_button(name, state).save(os.path.join(out, name + ending + '.png'))
        made.append(name)
    for state, ending in (('normal', ''), ('hover', '_hover'), ('off', '_off')):
        make_home(state).save(os.path.join(out, 'home' + ending + '.png'))
    make_tile().save(os.path.join(out, 'logo_tile.png'))
    for name in HEADERS:
        make_header(name).save(os.path.join(out, name + '.png'))
    for name in BADGES:
        make_badge(name).save(os.path.join(out, 'coop_badge_' + name + '.png'))
    return made


def contact_sheet(out, path, bg=(6, 8, 28)):
    names = sorted(n for n in os.listdir(out) if n.endswith('.png'))
    pictures = [(n, Image.open(os.path.join(out, n)).convert('RGBA')) for n in names]
    width, x, y, row_h, spots = 1400, 10, 10, 0, []
    for n, im in pictures:
        if x + im.width + 10 > width:
            x, y, row_h = 10, y + row_h + 10, 0
        spots.append((n, im, x, y))
        x += im.width + 10
        row_h = max(row_h, im.height)
    sheet = Image.new('RGB', (width, y + row_h + 10), bg)
    for n, im, x, y in spots:
        sheet.paste(im, (x, y), im)
    sheet.save(path)
    return len(pictures)


if __name__ == '__main__':
    args = sys.argv[1:]
    sheet = None
    if '--sheet' in args:                                   # --sheet FILE: taken out, so FILE is not read as the folder to write to
        at = args.index('--sheet')
        sheet = args[at + 1] if at + 1 < len(args) else None
        del args[at:at + 2]
    out = args[0] if args else os.path.join(KIT, 'assets', 'press', '8bit-ui')
    made = build_all(out)
    usual = sorted(n for n in os.listdir(UI) if n.endswith('.png'))
    missing = [n for n in usual if not os.path.exists(os.path.join(out, n))]
    wrong = []
    for n in sorted(os.listdir(out)):
        if n.endswith('.png') and os.path.exists(os.path.join(UI, n)):
            with Image.open(os.path.join(out, n)) as a, Image.open(os.path.join(UI, n)) as b:
                if a.size != b.size:
                    wrong.append(n)
    print(len([n for n in os.listdir(out) if n.endswith('.png')]), 'pictures in', out)
    print('kept as usual (no 8-bit picture):', ', '.join(missing) or 'none')
    print('wrong size:', ', '.join(wrong) or 'none')
    if sheet:
        print(contact_sheet(out, sheet), 'pictures on', sheet)
