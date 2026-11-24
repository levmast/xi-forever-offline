import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mode_icon_sets.py')).read().split("setA = [iron()")[0])
from PIL import ImageFont

def anvil(d, dy=0, col=(36, 38, 44), lit=(150, 154, 162)):
    a = [(170, 205), (345, 205), (345, 230), (305, 250), (290, 290), (330, 330), (182, 330), (222, 290), (207, 250), (150, 236)]
    a = [(x, y + dy) for x, y in a]
    d.polygon([(x, y + 6) for x, y in a], fill=INK); d.polygon(a, fill=col); d.line(a[:2], fill=lit, width=8)
    for ang in range(-60, 61, 30):
        r = math.radians(ang - 90); d.line([(258, 185 + dy), (258 + 46 * math.cos(r), 185 + dy + 46 * math.sin(r))], fill=(255, 180, 70), width=5)

def phoenix(d, dy=0):
    gold = (255, 210, 110)
    body = [(256, 160), (276, 230), (256, 330), (236, 230)]
    lw = [(246, 220), (130, 120), (150, 175), (118, 170), (160, 215), (132, 228), (210, 250)]
    rw = [(512 - x, y) for x, y in lw]
    tail = [(256, 300), (210, 400), (240, 380), (256, 420), (272, 380), (302, 400)]
    for p in (lw, rw, tail, body):
        d.polygon([(x + 4, y + 6 + dy) for x, y in p], fill=INK)
    for p, c in ((lw, (255, 140, 60)), (rw, (255, 140, 60)), (tail, (255, 90, 50)), (body, gold)):
        d.polygon([(x, y + dy) for x, y in p], fill=c)
    d.ellipse((242, 140 + dy, 270, 168 + dy), fill=gold)

def gemcrystal(d, dy=0, scale=1.0):
    cx, cy = 256, 255 + dy
    s = scale
    c = [(cx, cy - 150 * s), (cx + 62 * s, cy), (cx, cy + 150 * s), (cx - 62 * s, cy)]
    d.polygon([(x + 5, y + 7) for x, y in c], fill=INK)
    d.polygon([c[0], c[2], c[3]], fill=(176, 180, 204)); d.polygon([c[0], c[1], c[2]], fill=(236, 238, 250))
    d.line([(cx - 28 * s, cy - 80 * s), (cx - 4 * s, cy - 30 * s), (cx - 20 * s, cy), (cx + 6 * s, cy + 50 * s)], fill=(40, 30, 40), width=6)
    d.ellipse((cx - 18, cy - 18, cx + 18, cy + 18), fill=INK); d.ellipse((cx - 15, cy - 16, cx + 15, cy + 14), fill=(210, 20, 40)); d.ellipse((cx - 7, cy - 10, cx + 2, cy - 1), fill=(255, 150, 160))

def die_face(d, dy=0, phase=0):
    cx, cy, r = 256, 250 + dy, 120
    hexa = [(cx + r * math.cos(math.radians(90 + 60 * k)), cy - r * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
    hues = [(255, 90, 160), (255, 190, 80), (120, 230, 140), (80, 200, 255), (170, 120, 255), (255, 120, 90)]
    d.polygon([(x + 5, y + 7) for x, y in hexa], fill=INK)
    for k in range(6):
        d.polygon([(cx, cy), hexa[k], hexa[(k + 1) % 6]], fill=hues[(k + phase) % 6])
    d.polygon(hexa, outline=(255, 255, 255), width=7)
    for k in range(6):
        d.line([(cx, cy), hexa[k]], fill=(255, 255, 255), width=3)

# ---------- A2: matched shields (all four on the same shield)
def shield(top, bot, edge, emblem, laurel=False):
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = outlined(img, shield_poly(S / 2, 70, 340, 390), top, bot, edge)
    d = ImageDraw.Draw(img)
    for (x, y) in [(150, 120), (362, 120), (150, 300), (362, 300)]:
        d.ellipse((x - 11, y - 11, x + 11, y + 11), fill=(30, 30, 34)); d.ellipse((x - 8, y - 9, x + 4, y + 3), fill=edge[0])
    emblem(d); shine(img, m, 70); return img

def quartered_random():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = outlined(img, shield_poly(S / 2, 70, 340, 390), (90, 50, 160), (30, 10, 60), ((230, 200, 255), (130, 90, 210)))
    q = Image.new('RGBA', (S, S), (0, 0, 0, 0)); dq = ImageDraw.Draw(q)
    cols = [(255, 90, 160), (80, 200, 255), (255, 200, 80), (120, 230, 140)]
    dq.rectangle((0, 0, 256, 256), fill=cols[0] + (200,)); dq.rectangle((256, 0, 512, 256), fill=cols[1] + (200,))
    dq.rectangle((0, 256, 256, 512), fill=cols[2] + (200,)); dq.rectangle((256, 256, 512, 512), fill=cols[3] + (200,))
    inner = m.filter(ImageFilter.MinFilter(15))
    q.putalpha(ImageChops.multiply(q.split()[3], inner)); img.alpha_composite(q)
    d = ImageDraw.Draw(img)
    d.line([(256, 80), (256, 450)], fill=(255, 255, 255), width=8); d.line([(100, 256), (412, 256)], fill=(255, 255, 255), width=8)
    f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 190)
    d.ellipse((176, 176, 336, 336), fill=INK); d.ellipse((184, 180, 328, 324), fill=(40, 20, 70))
    d.text((262, 262), '?', font=f, fill=INK, anchor='mm'); d.text((256, 254), '?', font=f, fill=(255, 230, 140), anchor='mm')
    shine(img, m, 70); return img

setA2 = [shield((110, 114, 122), (46, 48, 54), ((210, 214, 222), (120, 124, 132)), anvil),
         shield((70, 120, 190), (16, 30, 66), ((200, 228, 255), (80, 128, 196)), phoenix),
         shield((130, 20, 30), (40, 4, 10), ((250, 250, 255), (170, 174, 196)), lambda d: gemcrystal(d, 10, 1.0)),
         quartered_random()]

# ---------- A3: crested shields (a kite shield, a crest on top, rank stars on a ribbon)
def kite():
    return [(256, 96), (400, 130), (392, 260), (256, 470), (120, 260), (112, 130)]

def star(d, x, y, r, col):
    pts = []
    for k in range(10):
        a = math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        pts.append((x + rr * math.cos(a), y - rr * math.sin(a)))
    d.polygon([(px + 3, py + 4) for px, py in pts], fill=INK); d.polygon(pts, fill=col)

def crested(top, bot, edge, emblem, crest, stars, star_col=(255, 214, 110), mark=None):
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    crest(d)
    m = outlined(img, kite(), top, bot, edge, width=12)
    d = ImageDraw.Draw(img)
    emblem(d)
    ribbon = [(120, 380), (392, 380), (372, 412), (392, 444), (120, 444), (140, 412)]
    d.polygon([(x + 4, y + 6) for x, y in ribbon], fill=INK); d.polygon(ribbon, fill=lin(bot, (0, 0, 0), 0.3)); d.polygon(ribbon, outline=edge[0], width=5)
    if mark:
        f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 52)
        d.text((256, 412), mark, font=f, fill=star_col, anchor='mm')
    else:
        for i in range(stars):
            star(d, 256 + (i - (stars - 1) / 2) * 56, 412, 24, star_col)
    shine(img, m, 60); return img

def horns(d):          # iron: two plain metal horns
    for s in (-1, 1):
        p = [(256 + s * 80, 120), (256 + s * 190, 30), (256 + s * 150, 120)]
        d.polygon([(x + 4, y + 6) for x, y in p], fill=INK); d.polygon(p, fill=(150, 154, 162))
def wings(d):          # steel: spread wings
    for s in (-1, 1):
        for i, r in enumerate((170, 140, 110)):
            p = [(256 + s * 60, 140), (256 + s * (60 + r), 40 + i * 28), (256 + s * (60 + r * 0.7), 150)]
            d.polygon([(x + 4, y + 6) for x, y in p], fill=INK); d.polygon(p, fill=lin((220, 236, 255), (90, 140, 210), i / 2))
def crown(d):          # silver: a silver crown
    p = [(160, 140), (176, 50), (216, 100), (256, 30), (296, 100), (336, 50), (352, 140)]
    d.polygon([(x + 4, y + 6) for x, y in p], fill=INK); d.polygon(p, fill=(236, 238, 250)); d.polygon(p, outline=(150, 154, 172), width=5)
    for x, y in ((176, 50), (256, 30), (336, 50)):
        d.ellipse((x - 12, y - 12, x + 12, y + 12), fill=(210, 20, 40))
def sparkle(d):        # random: scattered sparkles
    rnd = random.Random(4)
    for _ in range(9):
        x, y = rnd.uniform(120, 392), rnd.uniform(20, 120)
        r = rnd.uniform(10, 24); c = rnd.choice([(255, 90, 160), (255, 200, 80), (120, 230, 140), (80, 200, 255), (200, 150, 255)])
        d.polygon([(x, y - r), (x + r * 0.3, y), (x, y + r), (x - r * 0.3, y)], fill=c); d.polygon([(x - r, y), (x, y + r * 0.3), (x + r, y), (x, y - r * 0.3)], fill=c)

setA3 = [crested((110, 114, 122), (46, 48, 54), ((210, 214, 222), (120, 124, 132)), lambda d: anvil(d, -20), horns, 1),
         crested((70, 120, 190), (16, 30, 66), ((200, 228, 255), (80, 128, 196)), lambda d: phoenix(d, -30), wings, 2),
         crested((130, 20, 30), (40, 4, 10), ((250, 250, 255), (170, 174, 196)), lambda d: gemcrystal(d, -20, 0.8), crown, 3, (240, 240, 250)),
         crested((90, 50, 160), (30, 10, 60), ((230, 200, 255), (130, 90, 210)), lambda d: die_face(d, -20), sparkle, 0, (255, 230, 140), mark='?')]

setA = [iron(), steel(), silver(), random_icon()]
sets = [('A  First', setA), ('A2  Matched', setA2), ('A3  Crested', setA3)]
names = ['IRON', 'STEEL', 'SILVER', 'RANDOM']
fb = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
row_h = 220
sheet = Image.new('RGBA', (1240, 60 + row_h * len(sets) + 150), (26, 24, 30, 255)); dd = ImageDraw.Draw(sheet)
for i, n in enumerate(names):
    dd.text((330 + i * 230, 30), n, font=fb, fill=(240, 230, 200), anchor='mm')
for r, (title, icons) in enumerate(sets):
    y = 60 + r * row_h
    dd.text((20, y + 80), title, font=fb, fill=(230, 190, 100))
    for i, im in enumerate(icons):
        x = 250 + i * 230
        sheet.alpha_composite(im.resize((170, 170), Image.LANCZOS), (x, y + 10))
        sheet.alpha_composite(im.resize((40, 40), Image.LANCZOS), (x + 176, y + 90))
        sheet.alpha_composite(im.resize((24, 24), Image.LANCZOS), (x + 184, y + 140))
        im.resize((64, 64), Image.LANCZOS).save(f'{title.split()[0].lower()}_{names[i].lower()}.png')
# over names, in game size
y = 60 + row_h * len(sets)
dd.rectangle((0, y, 1240, y + 150), fill=(70, 90, 80))
for r, (title, icons) in enumerate(sets[1:]):
    for i, im in enumerate(icons):
        x = 60 + (r * 4 + i) * 145
        sheet.alpha_composite(im.resize((40, 40), Image.LANCZOS), (x + 30, y + 30))
        dd.text((x + 50, y + 92), ['Ironhide', 'Steely', 'Silvia', 'Randall'][i], font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 17), fill=(255, 255, 255), anchor='mm', stroke_width=2, stroke_fill=(0, 0, 0))
    dd.text((60 + r * 4 * 145 + 270, y + 128), title, font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 15), fill=(220, 220, 220), anchor='mm')
sheet.save('/tmp/icons/avars.png'); print('ok')
