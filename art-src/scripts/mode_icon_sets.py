import os
import math, random, sys
sys.argv=['x']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mode_icons.py')).read().split("icons = [('IRON'")[0])   # reuse helpers and set A
from PIL import Image, ImageDraw, ImageFilter, ImageFont
INK = (14, 10, 8)

def rot(pts, cx, cy, a):
    return [(cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a), cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a)) for x, y in pts]

# ---------------- set B: medallions (round seals with an emblem)
def medal(rim, face_top, face_bot, emblem):
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    d.ellipse((50, 56, 470, 476), fill=INK)
    d.ellipse((46, 46, 466, 466), fill=rim[0]); d.ellipse((62, 62, 450, 450), fill=rim[1])
    for k in range(24):                                   # notched rim
        a = 2 * math.pi * k / 24
        x, y = 256 + 200 * math.cos(a), 256 + 200 * math.sin(a)
        d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=rim[0])
    m = Image.new('L', (S, S), 0); ImageDraw.Draw(m).ellipse((92, 92, 420, 420), fill=255)
    img.alpha_composite(vgrad_mask((S, S), face_top, face_bot, m))
    emblem(ImageDraw.Draw(img)); shine(img, m, 70); return img

def em_hammer(d):
    head = [(170, 170), (330, 170), (330, 240), (170, 240)]
    for p in (rot(head, 256, 256, -0.5),):
        d.polygon([(x + 5, y + 7) for x, y in p], fill=INK); d.polygon(p, fill=(70, 72, 80))
    shaft = rot([(244, 230), (268, 230), (268, 400), (244, 400)], 256, 256, -0.5)
    d.polygon(shaft, fill=(120, 80, 46))
def em_swords(d):
    for a in (-0.7, 0.7):
        blade = rot([(248, 110), (264, 110), (264, 340), (256, 370), (248, 340)], 256, 256, a)
        guard = rot([(214, 340), (298, 340), (298, 356), (214, 356)], 256, 256, a)
        grip = rot([(250, 356), (262, 356), (262, 410), (250, 410)], 256, 256, a)
        d.polygon([(x + 4, y + 6) for x, y in blade], fill=INK)
        d.polygon(blade, fill=(220, 236, 255)); d.polygon(guard, fill=(255, 206, 110)); d.polygon(grip, fill=(90, 50, 30))
def em_moon(d):
    d.ellipse((150, 140, 362, 352), fill=(250, 250, 255)); d.ellipse((196, 120, 400, 324), fill=(60, 20, 30))
    d.ellipse((300, 300, 340, 340), fill=(220, 20, 40))
    for x, y in ((180, 380), (330, 170), (370, 380)):
        d.polygon([(x, y - 14), (x + 5, y), (x, y + 14), (x - 5, y)], fill=(255, 255, 255))
def em_question(d):
    f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 230)
    d.text((262, 262), '?', font=f, fill=INK, anchor='mm'); d.text((256, 256), '?', font=f, fill=(255, 220, 120), anchor='mm')

setB = [medal(((60, 62, 70), (150, 152, 160)), (110, 112, 120), (40, 42, 48), em_hammer),
        medal(((40, 70, 120), (150, 190, 240)), (50, 90, 160), (14, 28, 64), em_swords),
        medal(((150, 150, 170), (240, 240, 250)), (110, 24, 34), (40, 6, 12), em_moon),
        medal(((90, 40, 150), (210, 170, 255)), (100, 60, 180), (30, 10, 60), em_question)]

# ---------------- set C: cut gems
def gem(sides, top, bot, rim, core=None, rainbow=False, stretch=1.0):
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    cx, cy, r = 256, 256, 200
    outer = [(cx + r * math.cos(2 * math.pi * k / sides - math.pi / 2), cy + r * stretch * math.sin(2 * math.pi * k / sides - math.pi / 2)) for k in range(sides)]
    inner = [(cx + r * 0.52 * math.cos(2 * math.pi * k / sides - math.pi / 2), cy + r * 0.52 * stretch * math.sin(2 * math.pi * k / sides - math.pi / 2)) for k in range(sides)]
    d.polygon([(x + 6, y + 9) for x, y in outer], fill=INK)
    hues = [(255, 90, 160), (255, 190, 80), (120, 230, 140), (80, 200, 255), (170, 120, 255), (255, 120, 90), (255, 240, 120), (120, 255, 220)]
    for k in range(sides):
        a, b, c, e = outer[k], outer[(k + 1) % sides], inner[(k + 1) % sides], inner[k]
        t = (math.sin(2 * math.pi * k / sides) + 1) / 2
        col = hues[k % len(hues)] if rainbow else lin(top, bot, t)
        d.polygon([a, b, c, e], fill=col)
    d.polygon(inner, fill=lin(top, bot, 0.3) if not rainbow else (240, 240, 255))
    if core:
        d.ellipse((226, 226, 286, 286), fill=core); d.ellipse((238, 234, 254, 250), fill=(255, 200, 210))
    d.polygon(outer, outline=rim, width=8); d.polygon(inner, outline=rim, width=4)
    for k in range(sides):
        d.line([outer[k], inner[k]], fill=rim, width=3)
    return img
setC = [gem(8, (130, 132, 140), (30, 32, 38), (200, 204, 212)),
        gem(6, (120, 180, 255), (20, 50, 130), (210, 236, 255), stretch=1.1),
        gem(4, (255, 255, 255), (150, 154, 176), (255, 255, 255), core=(210, 20, 40), stretch=1.25),
        gem(8, (0, 0, 0), (0, 0, 0), (255, 255, 255), rainbow=True)]

# ---------------- set D: FFXI-style crystals with rank rings (1, 2, 3, ?)
def crystal(top, bot, rings, ring_col, glyph=None):
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for i in range(rings):
        r = 150 + i * 34
        d.ellipse((256 - r, 300 - r * 0.32, 256 + r, 300 + r * 0.32), outline=INK, width=12)
        d.ellipse((256 - r, 296 - r * 0.32, 256 + r, 296 + r * 0.32), outline=ring_col, width=7)
    shape = [(256, 40), (340, 250), (256, 470), (172, 250)]
    m = outlined(img, shape, top, bot, ((255, 255, 255), lin(bot, (0, 0, 0), 0.3)), width=10)
    d = ImageDraw.Draw(img)
    d.polygon([(256, 40), (256, 470), (172, 250)], fill=lin(top, bot, 0.55) + (255,))
    d.polygon([(256, 40), (340, 250), (256, 470)], fill=lin(top, (255, 255, 255), 0.25) + (255,))
    for i in range(rings):                                # front half of each ring over the crystal
        r = 150 + i * 34
        d.arc((256 - r, 296 - r * 0.32, 256 + r, 296 + r * 0.32), 0, 180, fill=ring_col, width=7)
    if glyph:
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 120)
        d.text((260, 250), glyph, font=f, fill=INK, anchor='mm'); d.text((256, 246), glyph, font=f, fill=(255, 255, 255), anchor='mm')
    shine(img, m, 60); return img
setD = [crystal((170, 174, 184), (60, 62, 70), 1, (200, 204, 212)),
        crystal((140, 200, 255), (30, 70, 160), 2, (160, 210, 255)),
        crystal((255, 255, 255), (170, 30, 50), 3, (240, 240, 250)),
        crystal((220, 170, 255), (80, 30, 160), 0, (220, 200, 255), glyph='?')]

# ---------------- set E: 8-bit sprites (helmet, sword, skull, die)
def pixel(rows, palette, frame):
    h, w = len(rows), len(rows[0]); px = 26
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    ox, oy = (S - w * px) // 2, (S - h * px) // 2
    d.rounded_rectangle((ox - 30, oy - 30, ox + w * px + 30, oy + h * px + 30), 26, fill=frame[0], outline=INK, width=10)
    d.rounded_rectangle((ox - 18, oy - 18, ox + w * px + 18, oy + h * px + 18), 18, outline=frame[1], width=6)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != '.':
                d.rectangle((ox + x * px, oy + y * px, ox + (x + 1) * px - 1, oy + (y + 1) * px - 1), fill=palette[ch])
    return img
helmet = ["....kkkkkk....", "..kkaaaaaakk..", ".kaaabbbbaaak.", ".kabbbbbbbbak.", "kabbbbbbbbbbak", "kabkkkkkkkkbak",
          "kabk.k..k.kbak", "kabkkkkkkkkbak", "kabbbbbbbbbbak", ".kabbbkkbbbak.", "..kkbbkkbbkk..", "....kkkkkk...."]
sword = ["...........kk.", "..........kak.", ".........kabk.", "........kabk..", ".......kabk...", "......kabk....",
         ".k..kkabk.....", ".kk.kabk......", "..kkcck.......", "..kccck.......", ".kdkkkk.......", "kddk..........", "kkk..........."]
skull = ["...kkkkkkkk...", "..kaaaaaaaak..", ".kaaaaaaaaaak.", ".kaakkaakkaak.", ".kaakrakkkaak.", ".kaaaakkaaaak.",
         "..kaaaaaaaak..", "...kakakakk...", "...kaaaaaak...", "....kkkkkk...."]
die = ["kkkkkkkkkkkk", "kabbbbbbbbak", "kbbkbbbbbbbk", "kbkkbbbbkkbk", "kbbbbbbbkkbk", "kbbbbkkbbbbk",
       "kbbbbkkbbbbk", "kbkkbbbbbbbk", "kbkkbbbbkkbk", "kbbbbbbbkkbk", "kabbbbbbbbak", "kkkkkkkkkkkk"]
setE = [pixel(helmet, {'k': (20, 20, 24), 'a': (210, 214, 222), 'b': (120, 124, 134)}, ((44, 46, 54), (160, 164, 172))),
        pixel(sword, {'k': (20, 20, 24), 'a': (240, 248, 255), 'b': (120, 170, 230), 'c': (255, 210, 90), 'd': (120, 70, 40)}, ((20, 40, 90), (120, 170, 240))),
        pixel(skull, {'k': (20, 20, 24), 'a': (240, 240, 248), 'r': (220, 20, 40)}, ((90, 14, 24), (240, 240, 250))),
        pixel(die, {'k': (20, 20, 24), 'a': (255, 220, 255), 'b': (190, 130, 255)}, ((50, 20, 90), (220, 170, 255)))]

setA = [iron(), steel(), silver(), random_icon()]
sets = [('A  Shields', setA), ('B  Medallions', setB), ('C  Gems', setC), ('D  Crystals', setD), ('E  8-bit', setE)]
names = ['IRON', 'STEEL', 'SILVER', 'RANDOM']
fb = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
fs = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 15)
row_h = 200
sheet = Image.new('RGBA', (1240, 60 + row_h * len(sets)), (26, 24, 30, 255)); dd = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    dd.text((330 + i * 230, 30), n, font=fb, fill=(240, 230, 200), anchor='mm')
for r, (title, icons) in enumerate(sets):
    y = 60 + r * row_h
    dd.text((20, y + 70), title, font=fb, fill=(230, 190, 100))
    for i, im in enumerate(icons):
        x = 250 + i * 230
        sheet.alpha_composite(im.resize((150, 150), Image.LANCZOS), (x, y + 10))
        sheet.alpha_composite(im.resize((40, 40), Image.LANCZOS), (x + 160, y + 80))
        sheet.alpha_composite(im.resize((24, 24), Image.LANCZOS), (x + 168, y + 130))
    for i, im in enumerate(icons):
        im.resize((64, 64), Image.LANCZOS).save(f'set{"ABCDE"[r]}_{names[i].lower()}.png')
sheet.save('/tmp/icons/sets.png')
print('ok')
