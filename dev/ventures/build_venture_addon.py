"""Makes the art of the in-game Ventures window (addons-src/venture/assets and art.lua) from the XIFO app's own art,
so the window draws the very pictures the app does. Run it again whenever the app's Ventures art changes:

    python dev/ventures/build_venture_addon.py [--app C:\\xifo-app] [--only bg,gm] [--check]

What it does to the app's files (the game draws them through Direct3D 8 with smooth scaling, a phone does not):
  * every picture sits in a canvas whose sides are powers of two (1024 x 512 ...), so Direct3D never resizes it
  * sprite sheets get a little empty space between frames where the canvas has room, and the see-through pixels next
    to a figure take the figure's colour (still see-through): no dark rim and no neighbour frame showing when scaled
  * the squad mates' big sheets (3 x) are stored at 1.25 x in 5 columns, 256 colours: about as big as the window
    draws them, a quarter of the memory in the game and half the download. (They stay ordinary 32-bit PNG files, the
    only kind the kit's add-ons have ever shown in the game; with a palette they would be a third the size, but nobody
    has seen Direct3D 8 read a see-through palette PNG here.)
  * backdrops keep their last row and column repeated into the spare space of the canvas

Needs Pillow, numpy and scipy. art.lua lists what exists and where each frame is; the add-on reads nothing else.
"""
import argparse
import os
import re
import shutil
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(KIT, "addons-src", "venture")
JOBS = ["WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN", "BLU", "COR", "PUP"]

# the app's grid (src/ventures/art.ts, gen_art.ts): the sizes below are in the files' own pixels
ZOOM = 4                         # the app's pixel art is drawn at 4 x
SCENE = (240, 126)
MOB, MOBT, PARTY = 32, 40, 32    # one frame, in grid pixels
GEN = {"fw": 144, "fh": 100, "cx": 56, "foot": 84, "tall": 56, "cols": 6, "rows": 2, "zoom": 3}
GEN_OUT = {"zoom": 1.25, "cols": 5, "rows": 3, "gutter": 2}
ALPHA_STEPS = 5                  # how many levels of see-through a mate sheet keeps (0, 64, 128, 191, 255)
BLEED = 3                        # how far a figure's colour runs into the see-through pixels around it
SOUNDS = ["depart", "home", "levelup", "select", "miss"]


def pot(n):
    p = 1
    while p < n:
        p *= 2
    return p


def bleed(im):
    """The see-through pixels within a few pixels of the picture take the nearest colour (and stay see-through);
    the rest is plain nothing. Smooth scaling then mixes the right colour at the edges."""
    a = np.array(im.convert("RGBA"))
    alpha = a[..., 3]
    solid = alpha > 0
    if not solid.any():
        a[...] = 0
        return Image.fromarray(a, "RGBA")
    dist, (iy, ix) = ndimage.distance_transform_edt(~solid, return_indices=True)
    near = (~solid) & (dist <= BLEED)
    a[near, :3] = a[iy[near], ix[near], :3]
    a[(~solid) & ~near] = 0
    return Image.fromarray(a, "RGBA")


def save(im, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, "PNG", optimize=True)


def scene(src, dst, see_through):
    """A backdrop (bg) or what stands in front of the party (fg): 960 x 504 in a 1024 x 512 canvas, its edges repeated."""
    im = Image.open(src).convert("RGBA")
    assert im.size == (SCENE[0] * ZOOM, SCENE[1] * ZOOM), (src, im.size)
    if see_through:
        im = bleed(im)
    w, h = im.size
    a = np.array(im)
    canvas = np.zeros((pot(h), pot(w), 4), np.uint8)
    canvas[:h, :w] = a
    canvas[:h, w:] = a[:, -1:, :]
    canvas[h:, :w] = a[-1:, :, :]
    canvas[h:, w:] = a[-1, -1]
    save(Image.fromarray(canvas, "RGBA"), dst)
    return canvas.shape[1], canvas.shape[0]


def strip(src, dst, frame, count, gutter):
    """A one-row sheet of `count` square frames (frame x frame grid pixels at 4 x), each frame cleaned on its own."""
    im = Image.open(src).convert("RGBA")
    f = frame * ZOOM
    assert im.size == (f * count, f), (src, im.size)
    cell = f + 2 * gutter
    canvas = Image.new("RGBA", (pot(cell * count), pot(f)), (0, 0, 0, 0))
    for i in range(count):
        canvas.paste(bleed(im.crop((i * f, 0, i * f + f, f))), (i * cell + gutter, 0))
    save(canvas, dst)
    return canvas.size


def mate_sheet(src, dst):
    """A squad mate's sheet: 12 frames at 3 x in 6 columns -> the same frames at 1.25 x in 5 columns, a gutter round each."""
    im = Image.open(src).convert("RGBA")
    z = GEN["zoom"]
    fw, fh = GEN["fw"] * z, GEN["fh"] * z
    assert im.size == (fw * GEN["cols"], fh * GEN["rows"]), (src, im.size)
    ow, oh = int(GEN["fw"] * GEN_OUT["zoom"]), int(GEN["fh"] * GEN_OUT["zoom"])
    g = GEN_OUT["gutter"]
    cw, ch = ow + 2 * g, oh + 2 * g
    canvas = Image.new("RGBA", (pot(cw * GEN_OUT["cols"]), pot(ch * GEN_OUT["rows"])), (0, 0, 0, 0))
    for i in range(GEN["cols"] * GEN["rows"]):
        x, y = (i % GEN["cols"]) * fw, (i // GEN["cols"]) * fh
        # (resized with the colours weighted by how solid they are: no dark rim from the see-through pixels)
        small = im.crop((x, y, x + fw, y + fh)).convert("RGBa").resize((ow, oh), Image.LANCZOS).convert("RGBA")
        canvas.paste(small, ((i % GEN_OUT["cols"]) * cw + g, (i // GEN_OUT["cols"]) * ch + g))
    save(bleed(fewer_colours(canvas)), dst)
    return canvas.size


def fewer_colours(im, colours=256):
    """The same picture with its colours brought down to 256 and five levels of see-through. The app's sheets have 255
    colours; shrinking them makes thousands of in-between ones, which only make the file big."""
    a = np.array(im)
    step = 255.0 / (ALPHA_STEPS - 1)
    a[..., 3] = np.round(np.round(a[..., 3] / step) * step).astype(np.uint8)
    solid = a[..., 3] > 0
    if not solid.any():
        return im
    rgb = a[..., :3].copy()
    rgb[~solid] = rgb[solid][0]                        # (nothing see-through may take a place in the palette)
    q = Image.fromarray(rgb, "RGB").quantize(colors=colours, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    a[..., :3] = np.array(q.convert("RGB"))
    a[~solid] = 0
    return Image.fromarray(a, "RGBA")


def lua_list(names):
    return "{ " + ", ".join("['%s'] = true" % n for n in sorted(names)) + " }"


def main():
    ap = argparse.ArgumentParser(description="Art for the in-game Ventures window, from the XIFO app's.")
    ap.add_argument("--app", default=os.path.join(KIT, "..", "xifo-app"), help="the xifo-app folder")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only", default="", help="a few of: bg,fg,m,mt,p,gm,snd (all when empty)")
    ap.add_argument("--check", action="store_true", help="say what is there and how big, change nothing")
    args = ap.parse_args()
    src = os.path.join(os.path.abspath(args.app), "assets")
    art = os.path.join(src, "ventures")
    if not os.path.isdir(art):
        sys.exit(f"No app art at {art}. Say where the app is: --app <the xifo-app folder>")
    out = os.path.join(args.out, "assets")
    only = {x for x in args.only.split(",") if x}
    want = lambda kind: not only or kind in only                      # noqa: E731

    def files(kind):
        return sorted(f[:-4] for f in os.listdir(os.path.join(art, kind)) if f.endswith(".png"))

    scenes = sorted(set(files("bg")) & set(files("fg")))
    mobs, named, party = files("m"), files("mt"), files("p")
    mates = [f for f in files("gm") if re.fullmatch(r"[A-Z]{3}_[1-8]", f)]
    jobs = [j for j in JOBS if all(f"{j}_{r}" in mates for r in range(1, 9))]
    if args.check:
        print(f"scenes {len(scenes)}, monsters {len(mobs)}, named monsters {len(named)}, party {len(party)}, jobs {len(jobs)}")
        total = 0
        for root, _, names in os.walk(out):
            total += sum(os.path.getsize(os.path.join(root, n)) for n in names)
        print(f"the add-on's art now: {total / 1e6:.1f} MB in {out}")
        return
    sizes = {}
    if want("bg"):
        for name in scenes:
            sizes["scene"] = scene(os.path.join(art, "bg", name + ".png"), os.path.join(out, "bg", name + ".png"), False)
    if want("fg"):
        for name in scenes:
            sizes["scene"] = scene(os.path.join(art, "fg", name + ".png"), os.path.join(out, "fg", name + ".png"), True)
    if want("m"):
        for name in mobs:
            sizes["mob"] = strip(os.path.join(art, "m", name + ".png"), os.path.join(out, "m", name + ".png"), MOB, 4, 0)
    if want("mt"):
        for name in named:
            sizes["mobt"] = strip(os.path.join(art, "mt", name + ".png"), os.path.join(out, "mt", name + ".png"), MOBT, 4, 2)
    if want("p"):
        for name in party:
            sizes["party"] = strip(os.path.join(art, "p", name + ".png"), os.path.join(out, "p", name + ".png"), PARTY, 10, 2)
    if want("gm"):
        for job in jobs:
            for race in range(1, 9):
                name = f"{job}_{race}"
                sizes["gen"] = mate_sheet(os.path.join(art, "gm", name + ".png"), os.path.join(out, "gm", name + ".png"))
    if want("snd"):
        os.makedirs(os.path.join(out, "snd"), exist_ok=True)
        for name in SOUNDS:
            shutil.copyfile(os.path.join(src, "sounds", "sfx", name + ".wav"), os.path.join(out, "snd", name + ".wav"))
        shutil.copyfile(os.path.join(src, "sounds", "bgm", "ventures.mp3"), os.path.join(out, "snd", "ventures.mp3"))

    # art.lua: what there is and where each frame sits (texels; the add-on turns them into texture coordinates)
    sw, sh = pot(SCENE[0] * ZOOM), pot(SCENE[1] * ZOOM)
    gz, gg = GEN_OUT["zoom"], GEN_OUT["gutter"]
    gw, gh = int(GEN["fw"] * gz), int(GEN["fh"] * gz)
    lines = [
        "-- Made by dev/ventures/build_venture_addon.py from the XIFO app's art (xifo-app/assets/ventures). Do not edit:",
        "-- run the script again. Sizes are in the files' own pixels; a frame's place is x = col * cw + ox, y = row * ch + oy.",
        "return {",
        f"    scene = {{ w = {sw}, h = {sh}, pw = {SCENE[0] * ZOOM}, ph = {SCENE[1] * ZOOM} }},",
        f"    mob   = {{ w = {pot(MOB * ZOOM * 4)}, h = {pot(MOB * ZOOM)}, fw = {MOB * ZOOM}, fh = {MOB * ZOOM}, cw = {MOB * ZOOM}, ch = {MOB * ZOOM}, "
        f"ox = 0, oy = 0, cols = 4, grid = {MOB} }},",
        f"    mobt  = {{ w = {pot((MOBT * ZOOM + 4) * 4)}, h = {pot(MOBT * ZOOM)}, fw = {MOBT * ZOOM}, fh = {MOBT * ZOOM}, cw = {MOBT * ZOOM + 4}, "
        f"ch = {MOBT * ZOOM}, ox = 2, oy = 0, cols = 4, grid = {MOBT} }},",
        f"    party = {{ w = {pot((PARTY * ZOOM + 4) * 10)}, h = {pot(PARTY * ZOOM)}, fw = {PARTY * ZOOM}, fh = {PARTY * ZOOM}, cw = {PARTY * ZOOM + 4}, "
        f"ch = {PARTY * ZOOM}, ox = 2, oy = 0, cols = 10, grid = {PARTY} }},",
        f"    gen   = {{ w = {pot((gw + 2 * gg) * GEN_OUT['cols'])}, h = {pot((gh + 2 * gg) * GEN_OUT['rows'])}, fw = {gw}, fh = {gh}, "
        f"cw = {gw + 2 * gg}, ch = {gh + 2 * gg}, ox = {gg}, oy = {gg}, cols = {GEN_OUT['cols']},",
        f"              FW = {GEN['fw']}, FH = {GEN['fh']}, CX = {GEN['cx']}, FOOT = {GEN['foot']}, TALL = {GEN['tall']} }},",
        f"    scenes = {lua_list(scenes)},",
        f"    mobs = {lua_list(mobs)},",
        f"    named = {lua_list(named)},",
        f"    party_count = {len(party)},",
        f"    jobs = {lua_list(jobs)},",
        "}",
        "",
    ]
    for kind, size in sizes.items():
        expect = {"scene": (sw, sh), "mob": (pot(MOB * ZOOM * 4), pot(MOB * ZOOM)), "mobt": (pot((MOBT * ZOOM + 4) * 4), pot(MOBT * ZOOM)),
                  "party": (pot((PARTY * ZOOM + 4) * 10), pot(PARTY * ZOOM)),
                  "gen": (pot((gw + 2 * gg) * GEN_OUT["cols"]), pot((gh + 2 * gg) * GEN_OUT["rows"]))}[kind]
        assert tuple(size) == expect, (kind, size, expect)
    with open(os.path.join(args.out, "art.lua"), "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines))
    total, count = 0, 0
    for root, _, names in os.walk(out):
        for n in names:
            total += os.path.getsize(os.path.join(root, n))
            count += 1
    print(f"{count} files, {total / 1e6:.1f} MB in {out}")
    print(f"scenes {len(scenes)}, monsters {len(mobs)}, named monsters {len(named)}, party {len(party)}, jobs {len(jobs)}")


if __name__ == "__main__":
    main()
