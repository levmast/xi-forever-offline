"""The in-game Ventures window without the game: runs the add-on's own Lua (addons-src/venture) under LuaJIT with
stand-ins for Ashita and ImGui, records what it draws, and paints that with Pillow using the add-on's own pictures.
The tests use it (test_venture_addon.py), and it can paint the window to a PNG to look at:

    python dev/ventures/venture_window.py out.png [--kit <a kit with ventures>] [--size 2] [--click "Send them off"]

Needs lupa (with LuaJIT) and Pillow; numpy for the pictures. Pictures are sampled the way Direct3D does (the four
nearest texels, no mip levels), so what looks rough here looks rough in the game.
"""
import os
import sys

try:
    from lupa import luajit21 as lupa
except Exception:                                    # pragma: no cover
    import lupa

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
ADDON = os.path.join(KIT, "addons-src", "venture")
FONTS = [os.path.join(KIT, "..", "xifo-app", "assets", "fonts", "selawk.ttf"), "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:\\Windows\\Fonts\\segoeui.ttf", "C:\\Windows\\Fonts\\arial.ttf"]

BOOT = r"""
local py = ...
local sep = package.config:sub(1, 1)
local function fix(p) if sep == '/' then return (tostring(p):gsub('\\', '/')) end return p end
-- (the add-on writes Windows paths; on another system the stand-ins turn the slashes)
local io_open, load_file, do_file, os_rename, os_remove = io.open, loadfile, dofile, os.rename, os.remove
io.open = function(p, m) return io_open(fix(p), m) end
os.remove = function(p) return os_remove(fix(p)) end
loadfile = function(p) return load_file(fix(p)) end
dofile = function(p) return do_file(fix(p)) end
os.rename = function(a, b)
    local ok, err = os_rename(fix(a), fix(b))
    if ok then py.touch(fix(b)) end          -- (the file is as old as the stand-in clock says)
    return ok, err
end
os.time = function(t) if t then return py.real_time(t) end return math.floor(py.clock()) end
os.clock = function() return py.clock() - py.started() end

addon = { path = py.addon_path }
HANDLERS = {}
ashita = {
    events = { register = function(event, name, fn) HANDLERS[event] = fn end },
    fs = { create_directory = function(p) py.mkdir(fix(p)) return true end },
}
local party = { GetMemberName = function(self, i) return py.me() end, GetMemberServerId = function(self, i) return py.me_id() end }
local memory = { GetParty = function() return party end }
local resources = { GetItemById = function() return nil end }
-- what the add-on hands to Ashita's chat manager (its line to the Squads menu): kept, in order
QUEUED = {}
local chat = { QueueCommand = function(self, mode, command) QUEUED[#QUEUED + 1] = tostring(command) end }
AshitaCore = {
    GetInstallPath = function() return py.ashita_path end,
    GetMemoryManager = function() return memory end,
    GetResourceManager = function() return resources end,
    GetChatManager = function() return chat end,
    GetDirect3DDevice = function() return nil end,
}
package.preload['common'] = function()
    string.args = function(s)
        local t = {}
        for w in tostring(s):gmatch('%S+') do t[#t + 1] = w end
        return t
    end
    return true
end
package.preload['d3d8'] = function() return { get_device = function() return nil end, gc_safe_release = function(x) return x end } end

-- ImGui: only what the add-on calls. Every draw call lands in FRAME.
FRAME = {}
local list = {}
function list:AddRectFilled(a, b, col, round) FRAME[#FRAME + 1] = { 'rect', a[1], a[2], b[1], b[2], col, round or 0 } end
function list:AddImage(ptr, a, b, ua, ub, col) FRAME[#FRAME + 1] = { 'image', ptr, a[1], a[2], b[1], b[2], ua[1], ua[2], ub[1], ub[2], col } end
function list:AddText(pos, col, text) FRAME[#FRAME + 1] = { 'text', pos[1], pos[2], col, text, fontSize() } end
function list:AddTriangleFilled(a, b, c, col) FRAME[#FRAME + 1] = { 'tri', a[1], a[2], b[1], b[2], c[1], c[2], col } end

-- the letters' size: (a pushed size, else the base) x a scale for all of Ashita x the window's own scale
IM = { base = 13, pushed = nil, global = 1, wscale = 1, stack = {}, cursor = { 8, 8 }, avail = { 500, 600 }, mouse = { -1, -1 }, click = false,
       taken = false, hovered = false, pushedColours = 0, pushedVars = 0, sized = true, content = { 0, 0 }, items = {}, begun = 0 }
function fontSize() return (IM.pushed or IM.base) * IM.global * IM.wscale end
local g = {}
function g.GetWindowDrawList() return list end
function g.GetColorU32(c)
    local function b(v) return math.floor(math.max(0, math.min(1, v)) * 255 + 0.5) end
    return b(c[1]) + b(c[2]) * 256 + b(c[3]) * 65536 + b(c[4] or 1) * 16777216
end
function g.GetFontSize() return fontSize() end
function g.GetFont() return 'font' end
function g.PushFont(font, size)
    IM.stack[#IM.stack + 1] = IM.pushed or false
    if IM.sized and size then IM.pushed = size end
end
function g.PopFont() IM.pushed = table.remove(IM.stack) or nil end
function g.SetWindowFontScale(s) IM.wscale = s end
function g.CalcTextSize(text) return py.measure(text, fontSize()), fontSize() end
function g.SetNextWindowSize() end
function g.SetNextWindowSizeConstraints() end
function g.PushStyleColor() IM.pushedColours = IM.pushedColours + 1 end
function g.PopStyleColor(n) IM.pushedColours = IM.pushedColours - (n or 1) end
function g.PushStyleVar() IM.pushedVars = IM.pushedVars + 1 end
function g.PopStyleVar(n) IM.pushedVars = IM.pushedVars - (n or 1) end
function g.Begin(title, open, flags)
    IM.begun = IM.begun + 1
    IM.title = title
    if IM.close then open[1] = false IM.close = false end      -- (the window's own X was clicked)
    return true
end
function g.End() IM.begun = IM.begun - 1 end
function g.GetContentRegionAvail() return IM.avail[1], IM.avail[2] end
function g.GetCursorScreenPos() return IM.cursor[1], IM.cursor[2] end
function g.SetCursorScreenPos(p) IM.cursor = { p[1], p[2] } end
function g.InvisibleButton(id, size)
    local x, y, w, h = IM.cursor[1], IM.cursor[2], size[1], size[2]
    IM.items[#IM.items + 1] = { id, x, y, w, h }
    local inside = IM.mouse[1] >= x and IM.mouse[1] < x + w and IM.mouse[2] >= y and IM.mouse[2] < y + h and not IM.taken
    IM.hovered = inside
    if inside then IM.taken = true end
    return inside and IM.click
end
function g.IsItemHovered() return IM.hovered end
function g.IsItemActive() return false end
function g.Dummy(size) IM.content = { size[1], size[2] } end
package.preload['imgui'] = function() return g end
ImGuiCond_FirstUseEver, ImGuiCond_Always = 4, 1
ImGuiWindowFlags_AlwaysVerticalScrollbar, ImGuiWindowFlags_NoCollapse = 16384, 32
ImGuiStyleVar_WindowPadding = 2
for i, name in ipairs({ 'WindowBg', 'Border', 'Text', 'TitleBg', 'TitleBgActive', 'TitleBgCollapsed', 'ScrollbarBg', 'ScrollbarGrab',
                        'ScrollbarGrabHovered', 'ScrollbarGrabActive', 'ResizeGrip', 'ResizeGripHovered', 'ResizeGripActive' }) do
    _G['ImGuiCol_' .. name] = i
end
PRINTED = {}
print = function(...)
    local t = {}
    for i = 1, select('#', ...) do t[#t + 1] = tostring((select(i, ...))) end
    PRINTED[#PRINTED + 1] = (table.concat(t, ' '):gsub('[%z\1-\31\127-\255]', ''))      -- (without the chat log's colour codes)
end
"""


class Py:
    """What the Lua stand-ins ask Python for."""

    def __init__(self, win):
        self.win = win
        self.addon_path = win.addon.rstrip("/\\") + os.sep
        self.ashita_path = win.ashita.rstrip("/\\") + os.sep

    def clock(self):
        return self.win.time

    def started(self):
        return self.win.started

    def real_time(self, t):
        return 0

    def me(self):
        return self.win.me

    def me_id(self):
        return self.win.me_id if self.win.me else 0

    def mkdir(self, path):
        os.makedirs(path, exist_ok=True)

    def touch(self, path):
        os.utime(path, (self.win.time, self.win.time))

    def measure(self, text, size):
        return self.win.measure(str(text), float(size))


class Window:
    def __init__(self, ashita, addon=ADDON, time=1_800_000_000.0, me="Hurami", font=13, sized_fonts=True, width=514, font_scale=1.0,
                 me_id=7):
        from PIL import ImageFont
        self.ashita, self.addon, self.time, self.started, self.me, self.me_id = ashita, addon, float(time), float(time) - 100.0, me, me_id
        self.font_path = next((f for f in FONTS if os.path.exists(f)), None)
        self._fonts, self._images, self._ImageFont = {}, {}, ImageFont
        probe = ImageFont.truetype(self.font_path, 100) if self.font_path else None
        self._ratio = (sum(probe.getmetrics()) / 100.0) if probe else 1.2          # line height over em size
        self.textures = {}                        # ptr -> path
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("BOOT = ...", None)
        self.lua.eval("function(src, py) return assert(loadstring(src))(py) end")(BOOT, Py(self))
        self.im = self.lua.globals().IM
        self.im.base = font
        self.im["global"] = font_scale
        self.im.sized = sized_fonts
        self.set_width(width)
        self.mod = self.lua.eval("function(p) return dofile(p) end")(os.path.join(addon, "venture.lua"))
        gfx = self.mod.gfx
        # pictures: a number for each file (the painter opens the file); nothing for a file that is not there
        gfx.loadFile = self._load
        gfx.loadItem = lambda item_id: None
        gfx.MAX_LOADS = 10_000
        self.handlers = self.lua.globals().HANDLERS
        self.handlers["load"]()
        self.cmds, self.items, self.content = [], [], (0, 0)

    def set_width(self, width):
        self.width = width
        self.im.avail = self.lua.table(width - 16 - 14, 100000)

    def _load(self, path):
        path = str(path).replace("\\", os.sep)
        if not os.path.exists(path):
            return None
        ptr = len(self.textures) + 1000
        self.textures[ptr] = path
        return self.lua.table_from({"ptr": ptr})

    def font(self, size):
        size = round(float(size), 2)
        if size not in self._fonts:
            self._fonts[size] = self._ImageFont.truetype(self.font_path, max(1, size / self._ratio)) if self.font_path else self._ImageFont.load_default()
        return self._fonts[size]

    def measure(self, text, size):
        return float(self.font(size).getlength(text))

    # ------------------------------------------------------------------ driving it
    def command(self, text):
        e = self.lua.table_from({"command": text, "blocked": False})
        self.handlers["command"](e)
        return bool(e.blocked)

    def frame(self, click=None, advance=0.0):
        """One frame. click: (x, y), or the text on something to press (the item under that text's start gets it)."""
        self.time += advance
        point = None
        if isinstance(click, str):
            point = self.find(click)
            if point is None:
                raise AssertionError(f"no text {click!r} in the window")
            point = (point[0] + 3, point[1] + 3)
        elif click:
            point = click
        self.lua.execute("FRAME = {}; IM.items = {}; IM.taken = false; IM.hovered = false; IM.cursor = { 8, 8 }")
        self.im.mouse = self.lua.table(*(point or (-1, -1)))
        self.im.click = bool(point)
        self.handlers["d3d_present"]()
        g = self.lua.globals()
        self.cmds = [tuple(c.values()) for c in g.FRAME.values()]
        self.items = [tuple(i.values()) for i in g.IM["items"].values()]
        self.content = tuple(g.IM["content"].values())
        assert self.im.begun == 0 and self.im.pushedColours == 0 and self.im.pushedVars == 0, "ImGui stacks left open"
        assert len(self.lua.eval("IM.stack")) == 0, "a font was left pushed"
        assert self.im.wscale == 1, "the window's font scale was left changed"
        return self.cmds

    def texts(self):
        return [c[4] for c in self.cmds if c[0] == "text"]

    def has(self, part):
        return any(part in t for t in self.texts())

    def find(self, part):
        for c in self.cmds:
            if c[0] == "text" and part in c[4]:
                return (c[1], c[2])
        return None

    def printed(self):
        return list(self.lua.globals().PRINTED.values())

    def queued(self, clear=False):
        """The lines the add-on handed to Ashita's chat manager (its "/xifoventure" to the Squads menu)."""
        out = list(self.lua.globals().QUEUED.values())
        if clear:
            self.lua.execute("QUEUED = {}")
        return out

    def unload(self):
        self.handlers["unload"]()

    def click_x(self):
        """The window's own X: ImGui shuts it while it is drawn, in the next frame."""
        self.im.close = True

    def marks(self, who=None):
        """Which of the add-on's two files for the Squads menu are in a character's folder (<Name>_<Id>)."""
        folder = os.path.join(self.ashita, "config", "addons", "xiforever", who or f"{self.me}_{self.me_id}")
        return sorted(n for n in ("venture.loaded", "venture.open") if os.path.exists(os.path.join(folder, n)))

    def images(self):
        return [os.path.relpath(self.textures[c[1]], os.path.join(self.addon, "assets")).replace(os.sep, "/") for c in self.cmds if c[0] == "image"]

    # ------------------------------------------------------------------ painting it
    def paint(self, cmds=None, back=(10, 6, 18, 255), height=None):
        import numpy as np
        from PIL import Image, ImageDraw
        cmds = self.cmds if cmds is None else cmds
        h = int(height or (self.content[1] + 16))
        canvas = Image.new("RGBA", (self.width, max(1, h)), back)

        def colour(v):
            v = int(v)
            return (v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >> 24) & 255)

        def over(layer, x, y):
            x, y = int(x), int(y)
            box = (max(0, x), max(0, y), min(canvas.width, x + layer.width), min(canvas.height, y + layer.height))
            if box[2] <= box[0] or box[3] <= box[1]:
                return
            part = layer.crop((box[0] - x, box[1] - y, box[2] - x, box[3] - y))
            canvas.alpha_composite(part, (box[0], box[1]))

        for c in cmds:
            if c[0] == "rect":
                _, x0, y0, x1, y1, col, rnd = c
                x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
                if x1 <= x0 or y1 <= y0:
                    continue
                layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
                d = ImageDraw.Draw(layer)
                r = int(min(rnd, (x1 - x0) / 2, (y1 - y0) / 2))
                if r >= 1:
                    d.rounded_rectangle((0, 0, x1 - x0 - 1, y1 - y0 - 1), r, fill=colour(col))
                else:
                    d.rectangle((0, 0, x1 - x0, y1 - y0), fill=colour(col))
                over(layer, x0, y0)
            elif c[0] == "image":
                _, ptr, x0, y0, x1, y1, u0, v0, u1, v1, col = c
                path = self.textures.get(int(ptr))
                if path is None:
                    continue
                if path not in self._images:
                    self._images[path] = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32)
                tex = self._images[path]
                th, tw = tex.shape[:2]
                px0, py0, px1, py1 = int(np.floor(x0)), int(np.floor(y0)), int(np.ceil(x1)), int(np.ceil(y1))
                if px1 <= px0 or py1 <= py0:
                    continue
                # each screen pixel's middle -> a place in the texture -> the four texels round it (what Direct3D does)
                xs = (np.arange(px0, px1) + 0.5 - x0) / (x1 - x0)
                ys = (np.arange(py0, py1) + 0.5 - y0) / (y1 - y0)
                inx, iny = (xs >= 0) & (xs <= 1), (ys >= 0) & (ys <= 1)
                tx = (u0 + (u1 - u0) * xs) * tw - 0.5
                ty = (v0 + (v1 - v0) * ys) * th - 0.5
                ix, iy = np.floor(tx).astype(int), np.floor(ty).astype(int)
                fx, fy = (tx - ix)[None, :, None], (ty - iy)[:, None, None]
                ix0, ix1 = np.clip(ix, 0, tw - 1), np.clip(ix + 1, 0, tw - 1)
                iy0, iy1 = np.clip(iy, 0, th - 1), np.clip(iy + 1, 0, th - 1)
                top = tex[iy0][:, ix0] * (1 - fx) + tex[iy0][:, ix1] * fx
                bot = tex[iy1][:, ix0] * (1 - fx) + tex[iy1][:, ix1] * fx
                out = top * (1 - fy) + bot * fy
                out = out * (np.array(colour(col), dtype=np.float32) / 255.0)
                out[~iny, :, 3] = 0
                out[:, ~inx, 3] = 0
                over(Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGBA"), px0, py0)
            elif c[0] == "text":
                _, x, y, col, text, size = c
                font = self.font(size)
                w = int(font.getlength(str(text))) + 4
                layer = Image.new("RGBA", (max(1, w), int(size * 1.5) + 4), (0, 0, 0, 0))
                ImageDraw.Draw(layer).text((0, 0), str(text), font=font, fill=colour(col))
                over(layer, round(x), round(y))
            elif c[0] == "tri":
                _, ax, ay, bx, by, cx, cy, col = c
                layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                ImageDraw.Draw(layer).polygon([(ax, ay), (bx, by), (cx, cy)], fill=colour(col))
                canvas.alpha_composite(layer)
        return canvas


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Paint the in-game Ventures window to a PNG.")
    ap.add_argument("out")
    ap.add_argument("--ashita", required=True, help="a folder with config/addons/venture/state.lua in it")
    ap.add_argument("--size", type=float, default=2)
    ap.add_argument("--time", type=float, default=1_800_000_000)
    ap.add_argument("--me", default="Hurami")
    ap.add_argument("--click", action="append", default=[])
    args = ap.parse_args(argv)
    w = Window(args.ashita, time=args.time, me=args.me, width=int(240 * args.size + 2 + 16 + 14 + 14))
    w.command("/venture")
    w.frame(advance=1)
    for text in args.click:
        w.frame(click=text)
        w.frame(advance=1)
    w.frame()
    w.paint().convert("RGB").save(args.out)
    print(args.out, w.content, len(w.cmds), "draw calls")


if __name__ == "__main__":
    main(sys.argv[1:])
