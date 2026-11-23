"""The Play page's pictures for the 8-Bit theme (assets\\press\\8bit_*__center__theme-8bit.png): twelve console title
screens whose characters are all real sprites, the ones in art-src\\8bit-sprites.

Each picture is a small scene drawn here in pixels (a sky in dithered bands, ridges, a town, trees, a strip of ground), with
the sprites standing, fighting, cheering or resting in it, and XI: Forever Offline in a blue menu window, in the lettering
and the window of bit_buttons.py. The one picture that is not drawn from nothing is the map: banners.py's map of Vana'diel,
cut down to 264 x 106 pixels and a small set of its own colours, with the party walking across it.
One drawn pixel is 4 x 4 in the file (1056 x 424), which is the size the Play page shows on most screens, so the pixels stay
sharp there. A sprite shown large is the same sprite at three times its size, pixel for pixel.

__theme-8bit in a file's name is what makes the launcher show it only while the 8-Bit theme is worn, in place of the usual
banners (press_names in launcher_gui.pyw).

    python bit_banners.py [OUTDIR] [--sheet FILE]        needs Pillow and numpy; a few seconds
"""
import os
import random
import sys

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bit_buttons as BB                                  # the window, the two pixel fonts, the sprites

_args, sys.argv = sys.argv, sys.argv[:1]                  # banners.py takes its output folder from the command line when it is loaded
import banners as B
sys.argv = _args

KIT = os.path.abspath(os.path.join(HERE, '..', '..'))
W, H, PX = 264, 106, 4                                    # drawn size, and how many file pixels one drawn pixel is
TAG = '__center__theme-8bit'
INK, WHITE, FRAME = BB.INK, BB.WHITE, (216, 220, 252)
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) + 0.5) / 16.0 - 0.5

LEFT, RIGHT = (11, 14, 109, 78), (W - 11 - 109, 14, 109, 78)        # where the wordmark window goes (x, y, width, height), in drawn pixels
PARTY = ('thief', 'monk', 'knight', 'white', 'black')
NIGHT = [(8, 10, 44), (12, 16, 64), (18, 26, 92), (30, 38, 124), (52, 52, 152), (88, 68, 168), (136, 88, 168)]
DAY = [(48, 112, 232), (72, 136, 240), (100, 160, 248), (132, 184, 252), (168, 208, 252), (204, 228, 252)]
DUSK = [(36, 24, 96), (76, 36, 124), (132, 52, 132), (196, 76, 116), (236, 116, 92), (252, 168, 88), (252, 216, 128)]
DAWN = [(60, 72, 168), (104, 104, 200), (164, 132, 208), (224, 160, 192), (252, 196, 168), (252, 228, 176)]
CAVE = [(10, 8, 24), (16, 12, 36), (24, 18, 50), (34, 24, 64), (44, 32, 78)]
GRASS = [(64, 168, 72), (44, 132, 60), (30, 100, 52), (22, 76, 44)]
SAND = [(236, 200, 120), (212, 168, 96), (180, 136, 80), (148, 108, 68)]
SNOW = [(244, 248, 252), (212, 224, 244), (176, 196, 232), (140, 164, 212)]
STONE = [(96, 92, 120), (76, 72, 100), (58, 54, 82), (44, 40, 66)]


def bare(draw):
    """One of banners.py's pictures without its wordmark, tag line and gold rule (920 x 368)."""
    keep = B.logo_layer, B.tagline, B.edge
    B.logo_layer = lambda w, h, dark: Image.new('RGBA', (w, h), (0, 0, 0, 0))
    B.tagline = lambda *a, **k: None
    B.edge = lambda img, dark=False: img
    try:
        return draw().convert('RGB')
    finally:
        B.logo_layer, B.tagline, B.edge = keep


def pixelate(img, colours=44, spread=26.0):
    """A painting as console pixel art: W x H pixels, `colours` colours picked from the picture itself, and an ordered dither
    (the same 4 x 4 pattern everywhere) where one of them alone would band."""
    small = img.resize((W, H), Image.LANCZOS)
    small = ImageEnhance.Color(small).enhance(1.3)
    small = ImageEnhance.Contrast(small).enhance(1.12)
    small = small.filter(ImageFilter.UnsharpMask(radius=1, percent=110, threshold=2))
    palette_img = small.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    palette = np.array(palette_img.getpalette()[:colours * 3], dtype=np.float32).reshape(-1, 3)
    used = sorted(set(np.asarray(palette_img).ravel().tolist()))
    palette = palette[used]
    pixels = np.asarray(small, dtype=np.float32)
    pattern = np.tile(BAYER, (H // 4 + 1, W // 4 + 1))[:H, :W, None] * spread
    shifted = np.clip(pixels + pattern, 0, 255).reshape(-1, 1, 3)
    nearest = ((shifted - palette[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
    return Image.fromarray(palette[nearest].reshape(H, W, 3).astype(np.uint8), 'RGB').convert('RGBA')


def wordmark(art, box):
    """XI in gold-banded letters, FOREVER OFFLINE and the era line, in a blue menu window at box (x, y, width, height)."""
    x, y, w, h = box
    art.alpha_composite(BB.window(w, h, 'blue'), (x, y))
    xi_w, xi_h = BB.text_size('XI', scale=4)
    name_w, name_h = BB.text_size('FOREVER OFFLINE')
    era_w, era_h = BB.text_size('THE CLASSIC ERA', BB.MICRO)
    top = y + (h - (xi_h + 5 + name_h + 6 + era_h)) // 2
    BB.draw_text(art, x + (w - xi_w) // 2, top, 'XI', WHITE, scale=4, ramp=BB.GOLD_RAMP)
    BB.draw_text(art, x + (w - name_w) // 2, top + xi_h + 5, 'FOREVER OFFLINE', WHITE)
    line_y = top + xi_h + 5 + name_h + 6 + era_h // 2
    px = art.load()
    for lx in list(range(x + 6, x + (w - era_w) // 2 - 3)) + list(range(x + (w + era_w) // 2 + 3, x + w - 6)):
        px[lx, line_y] = (164, 176, 236, 255)             # a thin rule either side of the era line
    BB.draw_text(art, x + (w - era_w) // 2, top + xi_h + 5 + name_h + 6, 'THE CLASSIC ERA', (252, 236, 144), BB.MICRO)
    return art


def framed(art):
    """A dark line round the picture and a pale one inside it, corners cut, like the windows."""
    px = art.load()
    for yy in range(H):
        for xx in range(W):
            edge = min(xx, yy, W - 1 - xx, H - 1 - yy)
            if edge == 0:
                px[xx, yy] = INK + (255,)
            elif edge == 1:
                corner = (xx in (1, W - 2)) and (yy in (1, H - 2))
                px[xx, yy] = (INK if corner else FRAME) + (255,)
    return art


def bands(art, y0, y1, colours):
    """Rows y0 .. y1 filled with these colours from top to bottom, every other pixel of a band's last row already the next one."""
    px = art.load()
    span = max(1, y1 - y0 + 1)
    for yy in range(y0, y1 + 1):
        band = min(len(colours) - 1, (yy - y0) * len(colours) // span)
        last = band + 1 < len(colours) and (yy + 1 - y0) * len(colours) // span > band
        for xx in range(W):
            px[xx, yy] = (colours[band + 1] if last and (xx + yy) % 2 else colours[band]) + (255,)


# ------------------------------------------------------------------ scenery
def canvas(sky, horizon, ground):
    art = Image.new('RGBA', (W, H), INK + (255,))
    bands(art, 0, horizon - 1, sky)
    bands(art, horizon, H - 1, ground)
    return art


def stars(art, count, depth, seed=11):
    px, rng = art.load(), random.Random(seed)
    for _ in range(count):                                 # thinning out towards the horizon
        px[rng.randrange(3, W - 3), int(rng.random() ** 1.6 * depth) + 3] = rng.choice([(252, 252, 252), (252, 236, 144), (164, 176, 236)]) + (255,)


def ridge(art, colour, base, swing, seed, floor):
    """A line of hills from one side to the other, filled down to the ground."""
    px, rng, height = art.load(), random.Random(seed), base
    for xx in range(W):
        if xx % 2 == 0:
            height = max(base - swing, min(base + swing, height + rng.choice((-1, -1, 0, 0, 1, 1))))
        for yy in range(height, floor):
            px[xx, yy] = colour + (255,)


def disc(art, cx, cy, radius, colours):
    """A sun or a moon: a round disc in bands from top to bottom."""
    px = art.load()
    for yy in range(cy - radius, cy + radius + 1):
        for xx in range(cx - radius, cx + radius + 1):
            if (xx - cx) ** 2 + (yy - cy) ** 2 <= radius * radius and 0 <= xx < W and 0 <= yy < H:
                px[xx, yy] = colours[min(len(colours) - 1, (yy - cy + radius) * len(colours) // (2 * radius + 1))] + (255,)


def clouds(art, seed, top, bottom, colour=(252, 252, 252), shade=(196, 212, 244)):
    px, rng = art.load(), random.Random(seed)
    for _ in range(5):
        cx, cy, width = rng.randrange(10, W - 10), rng.randrange(top, bottom), rng.randrange(14, 30)
        for row, cut in enumerate((8, 3, 0, 4)):
            for xx in range(cx - (width - cut) // 2, cx + (width - cut) // 2):
                if 0 <= xx < W:
                    px[xx, cy + row] = (shade if row == 3 else colour) + (255,)


def town(art, colour, floor, seed, lit=(252, 216, 96)):
    """A skyline of houses and towers with a few lit windows, standing on the ground line."""
    px, rng, xx = art.load(), random.Random(seed), 0
    while xx < W:
        width, height = rng.randrange(7, 15), rng.randrange(8, 26)
        for x2 in range(xx, min(W, xx + width)):
            top = floor - height - (2 if height > 18 and (x2 - xx) % 4 < 2 else 0)        # battlements on the tall ones
            for yy in range(top, floor):
                px[x2, yy] = colour + (255,)
        for _ in range(height // 7):
            wx, wy = xx + rng.randrange(1, max(2, width - 2)), floor - rng.randrange(3, max(4, height - 2))
            if wx < W - 1:
                px[wx, wy] = px[wx, wy + 1] = lit + (255,)
        xx += width + rng.randrange(0, 4)


def pines(art, colour, floor, seed, gap=9):
    px, rng = art.load(), random.Random(seed)
    for cx in range(4, W, gap):
        cx += rng.randrange(-2, 3)
        height = rng.randrange(10, 20)
        for row in range(height):
            half = 1 + row * 4 // height
            for xx in range(cx - half, cx + half + 1):
                if 0 <= xx < W:
                    px[xx, floor - height + row] = colour + (255,)


def spikes(art, colour, seed):
    """Stalactites hanging from the top of a cave."""
    px, rng, xx = art.load(), random.Random(seed), 2
    while xx < W - 2:
        width, length = rng.randrange(3, 9), rng.randrange(5, 22)
        for x2 in range(xx, min(W - 2, xx + width)):
            reach = length - abs((x2 - xx) - width // 2) * length // max(1, width // 2 + 1)
            for yy in range(2, 2 + max(1, reach)):
                px[x2, yy] = colour + (255,)
        xx += width + rng.randrange(1, 6)


def tufts(art, floor, colour, seed=5):
    px, rng = art.load(), random.Random(seed)
    for xx in range(2, W - 2, 3):
        if rng.random() < 0.6:
            px[xx, floor - 1] = colour + (255,)


def twinkles(art, cx, cy, reach, seed, colours=((252, 252, 252), (252, 236, 144), (92, 216, 252))):
    """Small plus-shaped sparks scattered round a point."""
    px, rng = art.load(), random.Random(seed)
    for _ in range(14):
        sx, sy, colour = cx + rng.randrange(-reach, reach + 1), cy + rng.randrange(-reach, reach + 1), rng.choice(colours)
        for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)) if rng.random() < 0.5 else ((0, 0),):
            if 2 <= sx + dx < W - 2 and 2 <= sy + dy < H - 2:
                px[sx + dx, sy + dy] = colour + (255,)


FIRE = ['...y...', '..yy...', '..yoy..', '.yooy..', '.yoroy.', 'yorrroy', 'yorrroy', '.orrro.', 'bbbbbbb', '.b.b.b.']
FIRE_INK = {'y': (252, 236, 144), 'o': (252, 168, 64), 'r': (232, 80, 48), 'b': (96, 60, 36)}


def campfire(art, x, floor):
    px = art.load()
    for row, line in enumerate(FIRE):
        for col, mark in enumerate(line):
            if mark != '.':
                px[x + col, floor - len(FIRE) + row] = FIRE_INK[mark] + (255,)


# ------------------------------------------------------------------ the sprites in a scene
def large(img, times=3):
    return img.resize((img.width * times, img.height * times), Image.NEAREST)


def stand(art, img, x, floor):
    art.alpha_composite(img, (x, floor - img.height))


def row(art, people, centre, floor, gap):
    """Sprites side by side, centred on a point, feet on one line."""
    x = centre - (sum(p.width for p in people) + gap * (len(people) - 1)) // 2
    for person in people:
        stand(art, person, x, floor)
        x += person.width + gap


def hero(sky, horizon, ground, who, pose, side, scenery=None, sparks=None):
    """One of the party at three times the size, on the side away from the wordmark."""
    art = canvas(sky, horizon, ground)
    if scenery:
        scenery(art)
    figure = large(BB.sprite(who, pose))
    centre = W - 64 if side == 'right' else 64
    stand(art, figure, centre - figure.width // 2, H - 6)
    if sparks:
        twinkles(art, centre, H - 6 - figure.height // 2, 34, sparks)
    return wordmark(art, LEFT if side == 'right' else RIGHT)


# ------------------------------------------------------------------ the twelve pictures
def title_screen():
    """Night, two ridges, grass: the name across the top and the party in a row under it."""
    art = canvas(NIGHT, 92, GRASS)
    stars(art, 70, 58)
    ridge(art, (26, 30, 96), 70, 11, 3, 92)
    ridge(art, (12, 14, 56), 80, 8, 7, 92)
    tufts(art, 92, GRASS[0])
    xi_w, xi_h = BB.text_size('XI', scale=5)
    BB.draw_text(art, (W - xi_w) // 2, 7, 'XI', WHITE, scale=5, ramp=BB.GOLD_RAMP)
    name_w, name_h = BB.text_size('FOREVER OFFLINE', scale=2)
    BB.draw_text(art, (W - name_w) // 2, 7 + xi_h + 5, 'FOREVER OFFLINE', WHITE, scale=2)
    row(art, [BB.sprite(who, 'Ready_00') for who in PARTY], W // 2, 96, 10)
    return art


def party_day():
    """A bright day outside a town: the party ready on the right."""
    art = canvas(DAY, 88, GRASS)
    clouds(art, 4, 6, 40)
    town(art, (88, 108, 176), 88, 21)
    tufts(art, 88, GRASS[0])
    row(art, [BB.sprite(who, 'Ready_00') for who in PARTY], 190, 98, 3)
    return wordmark(art, (7, 14, 109, 78))


def battle():
    """In a cave, drawn up the way a console battle is: one below the other down the right, weapons out."""
    art = canvas(CAVE, 40, STONE)
    spikes(art, (30, 22, 56), 9)
    poses = ('RightAttack_00', 'Ready_00', 'RightAttack_01', 'SkillReady_00', 'SkillReady_01')
    for i, (who, pose) in enumerate(zip(('knight', 'thief', 'monk', 'white', 'black'), poses)):
        stand(art, BB.sprite(who, pose), 166 + i * 14, 54 + i * 12)
    twinkles(art, 236, 80, 12, 2)
    return wordmark(art, LEFT)


def world_map():
    """The map of Vana'diel as a console world map, with the party walking across it."""
    art = pixelate(bare(lambda: B.map_banner()))
    walkers = [BB.sprite(who, 'WalkL_0%d' % (i % 2), 'map') for i, who in enumerate(PARTY)]
    for i, person in enumerate(walkers[:3]):
        stand(art, person, 14 + i * 16, 96 - i * 3)
    for i, person in enumerate(walkers[3:]):
        stand(art, person.transpose(Image.FLIP_LEFT_RIGHT), 212 + i * 17, 26 + i * 4)
    return wordmark(art, ((W - 135) // 2, (H - 80) // 2, 135, 80))


def victory():
    """Sunrise, and everybody cheering."""
    art = canvas(DAWN, 90, GRASS)
    disc(art, 196, 84, 22, [(252, 252, 220), (252, 240, 144), (252, 216, 72), (252, 184, 40)])
    bands(art, 90, H - 1, GRASS)
    ridge(art, (92, 96, 168), 82, 6, 13, 90)
    tufts(art, 90, GRASS[0])
    row(art, [BB.sprite(who, 'Win_00') for who in PARTY], 190, 99, 3)
    twinkles(art, 190, 52, 40, 6)
    return wordmark(art, LEFT)


def camp():
    """Night in the woods: the party resting round a fire."""
    art = canvas(NIGHT, 90, GRASS[1:] + [(16, 56, 36)])
    stars(art, 50, 50, seed=4)
    disc(art, 222, 22, 9, [(252, 252, 236), (236, 240, 252), (204, 212, 244)])
    pines(art, (10, 28, 40), 90, 8)
    left, right = [BB.sprite(who, 'Dying_00') for who in ('knight', 'white')], [BB.sprite(who, 'Dying_00').transpose(Image.FLIP_LEFT_RIGHT) for who in ('black', 'monk')]
    row(art, left, 165, 99, 2)
    campfire(art, 189, 99)
    row(art, right, 221, 99, 2)
    stand(art, BB.sprite('thief', 'Ready_00'), 132, 97)                       # one keeps watch
    return wordmark(art, (7, 14, 109, 78))


def march():
    """Dusk on the road: the party on its way, small, with a long way still to go."""
    art = canvas(DUSK, 84, SAND)
    disc(art, 60, 70, 16, [(252, 240, 176), (252, 208, 112), (252, 168, 88), (240, 124, 88)])
    bands(art, 84, H - 1, SAND)
    ridge(art, (92, 44, 108), 72, 9, 17, 84)
    ridge(art, (56, 28, 84), 79, 5, 23, 84)
    walkers = [BB.sprite(who, 'WalkL_0%d' % (i % 2), 'map') for i, who in enumerate(PARTY)]
    row(art, walkers, 74, 98, 6)
    return wordmark(art, RIGHT)


PICTURES = {                                               # name: how it is drawn
    '00_title': title_screen,
    '01_party': party_day,
    '02_battle': battle,
    '03_world_map': world_map,
    '04_victory': victory,
    '05_black_mage': lambda: hero(NIGHT, 94, STONE, 'black', 'SkillReady_00', 'right', lambda a: (stars(a, 60, 60, seed=2), town(a, (20, 22, 72), 94, 5)), sparks=3),
    '06_monk': lambda: hero(DUSK, 94, SAND, 'monk', 'RightAttack_00', 'left', lambda a: (ridge(a, (92, 44, 108), 80, 9, 31, 94), ridge(a, (56, 28, 84), 88, 5, 37, 94))),
    '07_knight': lambda: hero(DAY, 94, GRASS, 'knight', 'Ready_00', 'right', lambda a: (clouds(a, 9, 6, 44), town(a, (88, 108, 176), 94, 33), tufts(a, 94, GRASS[0]))),
    '08_thief': lambda: hero(DAWN, 94, SAND, 'thief', 'Ready_00', 'left', lambda a: (disc(a, 150, 86, 20, [(252, 252, 220), (252, 240, 144), (252, 216, 72)]), bands(a, 94, H - 1, SAND), ridge(a, (132, 96, 152), 86, 6, 41, 94))),
    '09_white_mage': lambda: hero(DAY, 94, SNOW, 'white', 'SkillReady_00', 'right', lambda a: (clouds(a, 14, 6, 40), pines(a, (40, 84, 96), 94, 12, gap=11)), sparks=8),
    '10_camp': camp,
    '11_march': march,
}


def to_file(art):
    return art.convert('RGB').resize((W * PX, H * PX), Image.NEAREST)


def build_all(out):
    os.makedirs(out, exist_ok=True)
    made = []
    for name, draw in PICTURES.items():
        path = os.path.join(out, '8bit_' + name + TAG + '.png')
        to_file(framed(draw())).save(path, optimize=True)
        made.append(path)
    return made


def contact_sheet(paths, target):
    pictures = [Image.open(p).convert('RGB') for p in paths]
    small = [p.resize((p.width // 2, p.height // 2), Image.NEAREST) for p in pictures]
    cols = 3
    rows = (len(small) + cols - 1) // cols
    cw, ch = small[0].size
    sheet = Image.new('RGB', (cols * (cw + 8) + 8, rows * (ch + 8) + 8), (6, 8, 28))
    for i, p in enumerate(small):
        sheet.paste(p, (8 + (i % cols) * (cw + 8), 8 + (i // cols) * (ch + 8)))
    sheet.save(target)


if __name__ == '__main__':
    args = sys.argv[1:]
    sheet = None
    if '--sheet' in args:
        at = args.index('--sheet')
        sheet = args[at + 1] if at + 1 < len(args) else None
        del args[at:at + 2]
    out = args[0] if args else os.path.join(KIT, 'assets', 'press')
    made = build_all(out)
    print(len(made), 'pictures in', out, '|', sum(os.path.getsize(p) for p in made) // 1024, 'KB')
    if sheet:
        contact_sheet(made, sheet)
        print('sheet:', sheet)
