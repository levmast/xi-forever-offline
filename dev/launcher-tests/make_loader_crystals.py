"""Draws assets/ui/loader_crystals.png, the launcher's loading animation (launcher_widgets.CrystalLoader):
8 rows (fire, ice, wind, earth, lightning, water, light, dark) and a 9th, green (the game has started), 10 glow levels, then the same 10 with a glint.
Supersampled 4x and scaled down for smooth edges.   python dev/launcher-tests/make_loader_crystals.py"""
# prototype of the sprite renderer (goes into launcher_widgets)
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
ELEMENTS = (("fire", (226, 72, 48)), ("ice", (120, 206, 240)), ("wind", (76, 196, 108)), ("earth", (214, 168, 70)),
            ("lightning", (176, 110, 232)), ("water", (60, 124, 230)), ("light", (236, 236, 246)), ("dark", (110, 66, 160)))
def mix(c, d, t): return tuple(int(a * (1 - t) + b * t) for a, b in zip(c, d))
def crystal(color, w, h, level, glint=0.0, bg=(10, 17, 24), ss=4):
    W, H = w * ss, h * ss
    im = Image.new("RGBA", (W, H), bg + (255,))
    cx, cy = W / 2, H / 2
    hw, hh = W * 0.26, H * 0.40
    P = lambda x, y: (cx + x * hw, cy + y * hh)
    top, bot = P(0, -1), P(0, 1)
    ul, ur, ll, lr = P(-1, -0.30), P(1, -0.30), P(-1, 0.30), P(1, 0.30)
    c = P(-0.18, -0.05)
    bright = 0.35 + 0.65 * level
    base = mix((0, 0, 0), color, bright)
    hi = mix(base, (255, 255, 255), 0.45 + 0.3 * glint)
    # glow behind
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    G = lambda x, y: (cx + x * hw * 1.55, cy + y * hh * 1.18)
    gd.polygon([G(0, -1), G(1, -0.3), G(1, 0.3), G(0, 1), G(-1, 0.3), G(-1, -0.3)], fill=color + (int(40 + 200 * level ** 1.4),))
    glow = glow.filter(ImageFilter.GaussianBlur(ss * 4.5))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    facets = [((top, ul, c), 0.55), ((top, c, ur), 0.25), ((ul, ll, c), 0.35), ((c, lr, ur), -0.15),
              ((ll, bot, c), 0.05), ((c, bot, lr), -0.35)]
    for pts, shade in facets:
        col = mix(base, (255, 255, 255), shade) if shade > 0 else mix(base, (0, 0, 0), -shade)
        d.polygon(pts, fill=col + (255,))
    edge = mix(base, (255, 255, 255), 0.55) + (200,)
    for a, b in ((top, ul), (ul, ll), (ll, bot), (top, c), (c, bot), (ul, c), (ll, c), (top, ur), (ur, lr), (lr, bot), (c, ur), (c, lr)):
        d.line([a, b], fill=edge, width=max(1, ss // 2))
    # specular streak on the upper-left facet
    d.line([P(-0.62, -0.42), P(-0.25, -0.78)], fill=hi + (230,), width=ss)
    if glint > 0.05:
        star = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(star)
        sx, sy = P(-0.25, -0.55); r = ss * 7 * glint
        sd.line([(sx - r, sy), (sx + r, sy)], fill=(255, 255, 255, int(255 * glint)), width=ss)
        sd.line([(sx, sy - r), (sx, sy + r)], fill=(255, 255, 255, int(255 * glint)), width=ss)
        im.alpha_composite(star.filter(ImageFilter.GaussianBlur(ss * 0.6)))
    return im.resize((w, h), Image.LANCZOS).convert("RGB")
if __name__ == "__main__":
    import os
    kit = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    CW, CH, L = 32, 50, 10
    ROWS = ELEMENTS + (("ready", (70, 220, 110)),)      # the last row: every crystal turns this green when the game starts
    sheet = Image.new("RGB", (CW * L * 2, CH * len(ROWS)), (10, 17, 24))
    for r, (_name, col) in enumerate(ROWS):
        for l in range(L):
            sheet.paste(crystal(col, CW, CH, l / (L - 1), 0.0), (l * CW, r * CH))
            sheet.paste(crystal(col, CW, CH, l / (L - 1), 1.0), ((L + l) * CW, r * CH))
    out = os.path.join(kit, "assets", "ui", "loader_crystals.png")
    sheet.save(out, optimize=True)
    print("wrote", out, sheet.size)
