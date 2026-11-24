import math, random
from PIL import Image, ImageDraw, ImageFilter, ImageChops
S = 512   # drawn big, scaled down

def lin(c1, c2, t): return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

def vgrad_mask(size, top, bottom, mask):
    g = Image.new('RGBA', size)
    d = ImageDraw.Draw(g)
    for y in range(size[1]):
        d.line([(0, y), (size[0], y)], fill=lin(top, bottom, y / size[1]) + (255,))
    out = Image.new('RGBA', size, (0, 0, 0, 0)); out.paste(g, (0, 0), mask); return out

def shield_poly(cx, top, w, h):
    pts = []
    for i in range(41):
        t = i / 40
        x = cx - w / 2 + w * t
        pts.append((x, top + 18 * math.sin(math.pi * t) * -0.6))
    for i in range(41):
        t = i / 40
        ang = math.pi * t
        x = cx + (w / 2) * math.cos(ang)
        y = top + h * 0.45 + (h * 0.55) * math.sin(ang) ** 1.4
        pts.append((x, y))
    return pts

def outlined(img, poly, fill_top, fill_bot, edge, width=14, ink=(14, 10, 8)):
    m = Image.new('L', img.size, 0); ImageDraw.Draw(m).polygon(poly, fill=255)
    big = m.filter(ImageFilter.MaxFilter(width * 2 + 1))
    img.alpha_composite(vgrad_mask(img.size, ink, ink, big))
    mid = m.filter(ImageFilter.MaxFilter(width + 1))
    img.alpha_composite(vgrad_mask(img.size, edge[0], edge[1], mid))
    img.alpha_composite(vgrad_mask(img.size, fill_top, fill_bot, m))
    return m

def shine(img, mask, strength=90):
    hl = Image.new('L', img.size, 0); d = ImageDraw.Draw(hl)
    d.ellipse((S * 0.18, S * 0.02, S * 0.82, S * 0.42), fill=strength)
    hl = ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(30)), mask)
    white = Image.new('RGBA', img.size, (255, 255, 255, 0)); white.putalpha(hl); img.alpha_composite(white)

def iron():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = outlined(img, shield_poly(S / 2, 70, 340, 390), (110, 114, 122), (46, 48, 54), ((210, 214, 222), (120, 124, 132)))
    d = ImageDraw.Draw(img)
    for (x, y) in [(150, 120), (362, 120), (150, 300), (362, 300), (256, 420)]:     # rivets
        d.ellipse((x - 13, y - 13, x + 13, y + 13), fill=(30, 30, 34)); d.ellipse((x - 9, y - 11, x + 5, y + 3), fill=(190, 194, 202))
    ink, metal, lit = (14, 10, 8), (36, 38, 44), (150, 154, 162)
    anvil = [(170, 205), (345, 205), (345, 230), (305, 250), (290, 290), (330, 330), (182, 330), (222, 290), (207, 250), (150, 236)]
    d.polygon([(x, y + 6) for x, y in anvil], fill=ink); d.polygon(anvil, fill=metal); d.line(anvil[:2], fill=lit, width=8)
    d.line([(250, 150), (282, 190)], fill=(255, 196, 90), width=7)          # sparks
    for a in range(-60, 61, 30):
        r = math.radians(a - 90); d.line([(258, 185), (258 + 46 * math.cos(r), 185 + 46 * math.sin(r))], fill=(255, 180, 70), width=5)
    shine(img, m, 70); return img

def steel():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    m = outlined(img, shield_poly(S / 2, 70, 340, 390), (70, 120, 190), (16, 30, 66), ((200, 228, 255), (80, 128, 196)))
    d = ImageDraw.Draw(img)
    gold, ink = (255, 210, 110), (14, 10, 8)
    # a rising phoenix: body, two raised wings, a fan tail
    body = [(256, 160), (276, 230), (256, 330), (236, 230)]
    lw = [(246, 220), (130, 120), (150, 175), (118, 170), (160, 215), (132, 228), (210, 250)]
    rw = [(512 - x, y) for x, y in lw]
    tail = [(256, 300), (210, 400), (240, 380), (256, 420), (272, 380), (302, 400)]
    for p in (lw, rw, tail, body):
        d.polygon([(x + 4, y + 6) for x, y in p], fill=ink)
    for p, c in ((lw, (255, 140, 60)), (rw, (255, 140, 60)), (tail, (255, 90, 50)), (body, gold)):
        d.polygon(p, fill=c)
    d.ellipse((242, 140, 270, 168), fill=gold); d.polygon([(256, 128), (248, 146), (264, 146)], fill=(255, 240, 180))
    shine(img, m, 80); return img

def silver():
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (14, 10, 8)
    # laurel: two branches curving up from the bottom, round the crystal
    cx, cy, rr = 256, 262, 178
    for side in (-1, 1):
        for i in range(10):
            t = i / 9
            deg = (250 - 115 * t) if side < 0 else (290 + 115 * t)
            a = math.radians(deg)
            px, py = cx + rr * math.cos(a), cy - rr * math.sin(a)
            r = 34 - 12 * t
            tang = a + (math.pi / 2 if side > 0 else -math.pi / 2)
            out = 0.55 * side
            leaf = [(0, -r), (r * 0.42, 0), (0, r), (-r * 0.42, 0)]
            rot = -tang + out
            pts = [(px + x * math.cos(rot) - y * math.sin(rot), py + x * math.sin(rot) + y * math.cos(rot)) for x, y in leaf]
            d.polygon([(x + 5, y + 6) for x, y in pts], fill=ink)
            d.polygon(pts, fill=lin((250, 250, 255), (150, 154, 172), t))
        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), 110 if side < 0 else -65, 250 if side < 0 else 70, fill=(190, 194, 210), width=6)
    # the crystal (FFXI-style long octahedron), cracked
    crystal = [(256, 70), (330, 250), (256, 440), (182, 250)]
    m = outlined(img, crystal, (232, 236, 250), (120, 124, 150), ((255, 255, 255), (170, 174, 196)), width=12)
    d.polygon([(256, 70), (256, 440), (182, 250)], fill=(176, 180, 204, 255)); d.polygon([(256, 70), (330, 250), (256, 440)], fill=(226, 230, 246, 255))
    d.line([(256, 70), (256, 440)], fill=(140, 144, 168), width=4)
    d.line([(222, 150), (250, 205), (232, 250), (262, 300), (244, 350)], fill=(40, 30, 40), width=7)
    d.ellipse((236, 236, 276, 276), fill=ink); d.ellipse((240, 238, 272, 270), fill=(210, 20, 40)); d.ellipse((248, 244, 258, 254), fill=(255, 150, 160))
    shine(img, m, 60); return img

def random_icon(phase=0.0):
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (14, 10, 8)
    cx, cy, r = 256, 262, 200
    hexa = [(cx + r * math.cos(math.radians(90 + 60 * k)), cy - r * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
    d.polygon([(x + 6, y + 8) for x, y in hexa], fill=ink)
    hues = [(255, 90, 160), (255, 190, 80), (120, 230, 140), (80, 200, 255), (170, 120, 255), (255, 120, 90)]
    shift = int(phase * 6) % 6
    for k in range(6):
        a, b = hexa[k], hexa[(k + 1) % 6]
        c = hues[(k + shift) % 6]
        d.polygon([(cx, cy), a, b], fill=lin(c, (20, 10, 40), 0.25))
    d.polygon(hexa, outline=(255, 255, 255), width=10)
    for k in range(6):
        d.line([(cx, cy), hexa[k]], fill=(255, 255, 255, 180), width=4)
    for dx, dy in ((-60, -40), (60, -40), (0, 70)):            # pips
        d.ellipse((cx + dx - 18, cy + dy - 18, cx + dx + 18, cy + dy + 18), fill=(255, 255, 255)); d.ellipse((cx + dx - 11, cy + dy - 11, cx + dx + 11, cy + dy + 11), fill=(30, 20, 60))
    return img

icons = [('IRON', iron()), ('STEEL', steel()), ('SILVER', silver()), ('RANDOM', random_icon())]
for name, im in icons:
    im.resize((64, 64), Image.LANCZOS).save(f'hc_icon_{name.lower()}.png')
sheet = Image.new('RGBA', (4 * 300, 560), (26, 24, 30, 255))
from PIL import ImageFont
f = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 22)
dd = ImageDraw.Draw(sheet)
for i, (name, im) in enumerate(icons):
    x = i * 300
    sheet.alpha_composite(im.resize((220, 220), Image.LANCZOS), (x + 40, 20))
    dd.text((x + 150, 260), name, font=f, fill=(240, 230, 200), anchor='mm')
    sheet.alpha_composite(im.resize((48, 48), Image.LANCZOS), (x + 80, 300))
    sheet.alpha_composite(im.resize((24, 24), Image.LANCZOS), (x + 160, 312))
# in-game style strip: icon above a name
strip = Image.new('RGBA', (1200, 200), (70, 90, 80, 255))
scene = Image.open('/tmp/icons/bg.png') if False else None
sheet.alpha_composite(strip, (0, 360))
for i, (name, im) in enumerate(icons):
    x = 80 + i * 290
    sheet.alpha_composite(im.resize((40, 40), Image.LANCZOS), (x + 40, 395))
    dd.text((x + 60, 455), ['Ironhide', 'Steely', 'Silvia', 'Randall'][i], font=f, fill=(255, 255, 255), anchor='mm', stroke_width=2, stroke_fill=(0, 0, 0))
dd.text((600, 520), 'as they would sit over a name in game (40 px)', font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16), fill=(200, 200, 200), anchor='mm')
sheet.save('/tmp/icons/sheet.png')
