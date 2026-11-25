"""The five 16x16 marks the game draws beside a name (2026-11-23): the four mode shields (the A2 set, from
assets/ui/hc_icon_*.png) and XI: Forever's own new-player "?" (crystal blue to violet, dark outline).

    python art-src/scripts/mode_marks_art.py     -> art-src/marks/*.png and client-patches/mode_marks.json

mode_marks.json holds each picture already compressed (DXT3, the game's format) with the cell of the game's icon
sheet it goes in ("ustats" in ROM/0/1.DAT, 128x64, 16x16 cells); launcher_client.py writes them at PLAY.
Cells: iron = the trial-account leaf (row 3, col 1), steel = the PlayOnline orb (0, 0), silver = the mentor globe
(2, 5), random = the "accepting party requests" goblet (0, 3), newplayer = the "?" (1, 1).
"""
import json, os, struct
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageChops

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CELLS = {"iron": (3, 1), "steel": (0, 0), "silver": (2, 5), "random": (0, 3), "newplayer": (1, 1)}
# (2026-11-24) the game's high-resolution copy "ustatshd" (256x256, 32x32 cells; the large nameplates draw from it, so
# the goblet kept showing): the same five marks, and its top-left 128x64 holds the 16x16 sheet again (CELLS)
HD_CELLS = {"iron": (2, 5), "steel": (1, 7), "silver": (3, 2), "random": (2, 2), "newplayer": (0, 7)}


def shield(name, size=16):
    im = Image.open(os.path.join(KIT, "assets", "ui", f"hc_icon_{name}.png")).convert("RGBA")
    im = im.crop(im.getbbox())
    side = max(im.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
    small = sq.resize((size * 2, size * 2), Image.LANCZOS).resize((size, size), Image.LANCZOS)
    return ImageEnhance.Contrast(ImageEnhance.Sharpness(small).enhance(1.8)).enhance(1.15)


def question_mark(size16=16):
    size = 96
    font = None
    for path in ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(path):
            font = ImageFont.truetype(path, 92)
            break
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    box = draw.textbbox((0, 0), "?", font=font)
    draw.text(((size - (box[2] - box[0])) // 2 - box[0], (size - (box[3] - box[1])) // 2 - box[1]), "?", font=font, fill=255)
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    im.paste((24, 12, 48, 255), (0, 0), mask.filter(ImageFilter.MaxFilter(13)))
    grad = Image.new("RGBA", (size, size))
    for y in range(size):
        t = y / size
        grad.paste((int(150 + 20 * t), int(235 - 125 * t), 255, 255), (0, y, size, y + 1))
    im.paste(grad, (0, 0), mask)
    shine = ImageChops.subtract(mask, mask.transform(mask.size, Image.AFFINE, (1, 0, 5, 0, 1, 5)))
    im.paste((245, 255, 255, 255), (0, 0), shine.point(lambda v: 255 if v > 128 else 0))
    return ImageEnhance.Sharpness(im.resize((size16 * 2, size16 * 2), Image.LANCZOS).resize((size16, size16), Image.LANCZOS)).enhance(1.5)


def dxt3_encode(img):
    """RGBA -> DXT3 blocks (the same approach as forever_beta_shirt.py: brightest / darkest visible pixel as ends)."""
    w, h = img.size
    px = img.convert("RGBA").tobytes()
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            pts = []
            for y in range(by, by + 4):
                o = (y * w + bx) * 4
                pts += [px[o + i * 4:o + i * 4 + 4] for i in range(4)]
            alpha = 0
            for i, p in enumerate(pts):
                alpha |= (p[3] >> 4) << (4 * i)
            seen = [p for p in pts if p[3] >= 32] or pts
            lum = [p[0] * 2 + p[1] * 5 + p[2] for p in seen]
            hi, lo = seen[lum.index(max(lum))], seen[lum.index(min(lum))]
            c0 = ((hi[0] >> 3) << 11) | ((hi[1] >> 2) << 5) | (hi[2] >> 3)
            c1 = ((lo[0] >> 3) << 11) | ((lo[1] >> 2) << 5) | (lo[2] >> 3)
            if c0 < c1:
                c0, c1 = c1, c0

            def rgb(c):
                r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
                return ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))

            e0, e1 = rgb(c0), rgb(c1)
            pal = [e0, e1, tuple((2 * x + y) // 3 for x, y in zip(e0, e1)), tuple((x + 2 * y) // 3 for x, y in zip(e0, e1))]
            idx = 0
            for i, p in enumerate(pts):
                dist = [(p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2 for q in pal]
                idx |= dist.index(min(dist)) << (2 * i)
            out += struct.pack("<QHHI", alpha, c0, c1, idx)
    return bytes(out)


def main():
    out_dir = os.path.join(KIT, "art-src", "marks")
    os.makedirs(out_dir, exist_ok=True)
    data = {"texture": "ustats", "file": "ROM/0/1.DAT", "size": [128, 64], "cells": []}
    for name, (row, col) in CELLS.items():
        img = question_mark() if name == "newplayer" else shield(name)
        img.save(os.path.join(out_dir, f"{name}16.png"))
        data["cells"].append({"name": name, "row": row, "col": col, "dxt3": dxt3_encode(img).hex()})
    data["hd"] = {"texture": "ustatshd", "size": [256, 256], "cells": []}
    for name, (row, col) in HD_CELLS.items():
        img = question_mark(32) if name == "newplayer" else shield(name, 32)
        img.save(os.path.join(out_dir, f"{name}32.png"))
        data["hd"]["cells"].append({"name": name, "row": row, "col": col, "dxt3": dxt3_encode(img).hex()})
    with open(os.path.join(KIT, "client-patches", "mode_marks.json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    print("written", len(data["cells"]), "marks")


if __name__ == "__main__":
    main()
