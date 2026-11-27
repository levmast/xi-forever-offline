--[[
venture/gfx - what the Ventures window draws with: colours, text at any size, boxes, pictures cut to a box, and the
pictures themselves (PNG files turned into textures, kept only while they are used).

Only calls the kit's other add-ons already make: GetWindowDrawList, AddRectFilled, AddImage, AddText, GetColorU32,
CalcTextSize, GetFontSize, PushFont/PopFont (SetWindowFontScale when this ImGui cannot push a font at a size).
Text goes to the draw list as it is, never through a printf format (a '%' in a name must not end the game).

With M.dry set nothing is drawn: the window lays itself out once that way to learn how tall each section is.
]]
local imgui = require('imgui');
local ffi = require('ffi');

local d3d8;
do
    local ok, mod = pcall(require, 'd3d8');
    if ok then d3d8 = mod; end
end

local M = { dry = false, list = nil, clipBox = nil, now = 0 };

local function has(name) return type(imgui[name]) == 'function'; end

-- a point from ImGui: some bindings give two numbers, some one table
local function pair(a, b)
    if type(a) == 'table' then return tonumber(a[1] or a.x) or 0, tonumber(a[2] or a.y) or 0; end
    return tonumber(a) or 0, tonumber(b) or 0;
end
M.pair = pair;

-----------------------------------------------------------------------
-- colours: '#RRGGBB', 'rgba(r,g,b,a)' or { r, g, b, a } (0-1)
-----------------------------------------------------------------------
local parsed = {};

local function parse(c)
    if type(c) == 'table' then return c; end
    local t = parsed[c];
    if t then return t; end
    local r, g, b = c:match('^#(%x%x)(%x%x)(%x%x)$');
    if r then
        t = { tonumber(r, 16) / 255, tonumber(g, 16) / 255, tonumber(b, 16) / 255, 1 };
    else
        local a;
        r, g, b, a = c:match('^rgba?%(%s*([%d.]+)%s*,%s*([%d.]+)%s*,%s*([%d.]+)%s*,?%s*([%d.]*)%s*%)$');
        t = r and { tonumber(r) / 255, tonumber(g) / 255, tonumber(b) / 255, tonumber(a) or 1 } or { 1, 0, 1, 1 };
    end
    parsed[c] = t;
    return t;
end
M.parse = parse;

local function pack(r, g, b, a)
    local function byte(v) return math.floor(math.max(0, math.min(1, v)) * 255 + 0.5); end
    return byte(r) + byte(g) * 256 + byte(b) * 65536 + byte(a) * 16777216;
end

local u32cache = {};

-- the colour as the draw list wants it; `alpha` (0-1) fades it
function M.col(c, alpha)
    if alpha == nil and type(c) == 'string' then
        local v = u32cache[c];
        if v then return v; end
    end
    local t = parse(c);
    local a = (t[4] or 1) * (alpha or 1);
    local v;
    if has('GetColorU32') then
        local ok, got = pcall(imgui.GetColorU32, { t[1], t[2], t[3], a });
        if ok and type(got) == 'number' then v = got; end
    end
    if v == nil and has('ColorConvertFloat4ToU32') then
        local ok, got = pcall(imgui.ColorConvertFloat4ToU32, { t[1], t[2], t[3], a });
        if ok and type(got) == 'number' then v = got; end
    end
    if v == nil then v = pack(t[1], t[2], t[3], a); end
    if alpha == nil and type(c) == 'string' then u32cache[c] = v; end
    return v;
end

-- a colour between two (t 0-1), as a table
function M.mix(c1, c2, t)
    local a, b = parse(c1), parse(c2);
    return { a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t, (a[4] or 1) + ((b[4] or 1) - (a[4] or 1)) * t };
end

-----------------------------------------------------------------------
-- a frame of the window
-----------------------------------------------------------------------
local F = { size = 13, font = nil, cur = 13, pushed = false, mode = 'none', ratio = 1 };
local widths, widthCount = {}, 0;

-- Can this ImGui push a font AT a size (1.92: PushFont(font, size))? Asked once, with two sizes: when the second comes
-- out half as big again as the first it can, and what it adds on top (a font scale set for the whole of Ashita) is
-- F.ratio. An older ImGui takes the font and leaves the size: the text is stretched instead (SetWindowFontScale).
local function probe()
    M.sizedFonts = false;
    if not (has('PushFont') and has('PopFont') and has('GetFontSize')) or F.font == nil then return; end
    local function at(size)
        local got = nil;
        if pcall(imgui.PushFont, F.font, size) then
            got = tonumber(imgui.GetFontSize());
            pcall(imgui.PopFont);
        end
        return got;
    end
    local a, b = at(20), at(30);
    if a and b and a > 0 and math.abs(b / a - 1.5) < 0.03 then
        M.sizedFonts = true;
        F.ratio = a / 20;
    end
end

function M.begin(clock)
    M.now = clock or os.clock();
    M.list = has('GetWindowDrawList') and imgui.GetWindowDrawList() or nil;
    M.clipBox = nil;
    local size = has('GetFontSize') and tonumber(imgui.GetFontSize()) or 13;
    if size ~= F.size then widths, widthCount = {}, 0; end          -- (another font size: every width is new)
    F.size, F.cur, F.pushed = size, size, false;
    F.font = has('GetFont') and imgui.GetFont() or nil;
    if M.sizedFonts == nil then probe(); end
    if M.sizedFonts and F.font ~= nil then
        F.mode = 'push';
    elseif has('SetWindowFontScale') then
        F.mode = 'scale';
    else
        F.mode = 'none';
    end
end

function M.finish()
    if F.pushed then pcall(imgui.PopFont); F.pushed = false; end
    if F.mode == 'scale' and F.cur ~= F.size then pcall(imgui.SetWindowFontScale, 1); end
    F.cur = F.size;
    M.clipBox = nil;
end

M.base = function() return F.size; end

-- what is written next is `px` high
function M.font(px)
    px = math.max(6, math.floor(px + 0.5));
    if px == F.cur then return; end
    if F.mode == 'push' then
        if F.pushed then pcall(imgui.PopFont); F.pushed = false; end
        if px ~= F.size then
            if pcall(imgui.PushFont, F.font, px / F.ratio) then
                F.pushed = true;
            else
                M.sizedFonts = false;
                F.mode = has('SetWindowFontScale') and 'scale' or 'none';
            end
        end
    end
    if F.mode == 'scale' then pcall(imgui.SetWindowFontScale, px / F.size); end
    if F.mode == 'none' then px = F.size; end
    F.cur = px;
end

function M.width(text, px, bold)
    px = math.max(6, math.floor(px + 0.5));
    if F.mode == 'none' then px = F.size; end
    local per = widths[px];
    if per == nil then per = {}; widths[px] = per; end
    local w = per[text];
    if w == nil then
        M.font(px);
        w = pair(imgui.CalcTextSize(text));
        if widthCount > 6000 then widths, widthCount = { [px] = {} }, 0; per = widths[px]; end
        per[text] = w;
        widthCount = widthCount + 1;
    end
    return w + (bold and 1 or 0);
end

-- text at x, y (its top left); bold is the same text once more a pixel to the right
function M.text(x, y, col, text, px, bold)
    if M.dry or M.list == nil or text == nil or text == '' then return; end
    M.font(px);
    x, y = math.floor(x + 0.5), math.floor(y + 0.5);
    M.list:AddText({ x, y }, col, text);
    if bold then M.list:AddText({ x + 1, y }, col, text); end
end

-- text with a one-pixel shadow under it (the scene's numbers and labels)
function M.shadowed(x, y, col, shadow, text, px, bold)
    if M.dry then return; end
    M.text(x + 1, y + 1, shadow, text, px, bold);
    M.text(x, y, col, text, px, bold);
end

-- the text cut to fit `maxw`, with dots when something was left out
function M.fit(text, px, maxw, bold)
    if M.width(text, px, bold) <= maxw then return text; end
    local n = #text;
    while n > 1 and M.width(text:sub(1, n) .. '...', px, bold) > maxw do n = n - 1; end
    return text:sub(1, n) .. '...';
end

-----------------------------------------------------------------------
-- boxes and pictures (both cut to M.clipBox when one is set)
-----------------------------------------------------------------------
function M.clip(x0, y0, x1, y1) M.clipBox = x0 and { x0, y0, x1, y1 } or nil; end

function M.rect(x0, y0, x1, y1, col, round)
    if M.dry or M.list == nil then return; end
    local c = M.clipBox;
    if c then
        if x0 < c[1] then x0 = c[1]; round = 0; end
        if y0 < c[2] then y0 = c[2]; round = 0; end
        if x1 > c[3] then x1 = c[3]; round = 0; end
        if y1 > c[4] then y1 = c[4]; round = 0; end
    end
    if x1 <= x0 or y1 <= y0 then return; end
    M.list:AddRectFilled({ x0, y0 }, { x1, y1 }, col, round or 0);
end

-- a line round a box, `t` thick, inside it (four bars: every binding has AddRectFilled)
function M.frame(x0, y0, x1, y1, col, t)
    t = t or 1;
    M.rect(x0, y0, x1, y0 + t, col);
    M.rect(x0, y1 - t, x1, y1, col);
    M.rect(x0, y0 + t, x0 + t, y1 - t, col);
    M.rect(x1 - t, y0 + t, x1, y1 - t, col);
end

-- a box filled from the first colour at the top to the last at the bottom (colours as for M.col; alpha fades all)
function M.vgrad(x0, y0, x1, y1, stops, alpha, bands)
    if M.dry or y1 <= y0 then return; end
    local h = y1 - y0;
    bands = math.max(1, math.min(bands or math.ceil(h / 2), 64));
    local n = #stops;
    for i = 0, bands - 1 do
        local t = (i + 0.5) / bands * (n - 1);
        local k = math.min(n - 2, math.floor(t));
        local c = n == 1 and parse(stops[1]) or M.mix(stops[k + 1], stops[k + 2], t - k);
        M.rect(x0, y0 + h * i / bands, x1, y0 + h * (i + 1) / bands, M.col(c, alpha));
    end
end

local WHITE;

-- a picture (or a part of it: u, v 0-1) in a box
function M.image(tex, x0, y0, x1, y1, u0, v0, u1, v1, col)
    if M.dry or M.list == nil or not tex then return; end
    local w, h = x1 - x0, y1 - y0;
    if w <= 0 or h <= 0 then return; end
    u0, v0, u1, v1 = u0 or 0, v0 or 0, u1 or 1, v1 or 1;
    local c = M.clipBox;
    if c then
        if x1 <= c[1] or x0 >= c[3] or y1 <= c[2] or y0 >= c[4] then return; end
        local du, dv = (u1 - u0) / w, (v1 - v0) / h;
        if x0 < c[1] then u0 = u0 + du * (c[1] - x0); x0 = c[1]; end
        if y0 < c[2] then v0 = v0 + dv * (c[2] - y0); y0 = c[2]; end
        if x1 > c[3] then u1 = u1 - du * (x1 - c[3]); x1 = c[3]; end
        if y1 > c[4] then v1 = v1 - dv * (y1 - c[4]); y1 = c[4]; end
    end
    if WHITE == nil then WHITE = M.col('#FFFFFF'); end
    M.list:AddImage(tex.ptr, { x0, y0 }, { x1, y1 }, { u0, v0 }, { u1, v1 }, col or WHITE);
end

-- frame `index` of a sheet (art.lua's layout `L`) in a box; half a texel is kept off every edge so a neighbour
-- frame never shows when the picture is scaled
function M.sprite(tex, L, index, x0, y0, x1, y1, col)
    if not tex then return; end
    local fx = (index % L.cols) * L.cw + L.ox;
    local fy = math.floor(index / L.cols) * L.ch + L.oy;
    M.image(tex, x0, y0, x1, y1, (fx + 0.5) / L.w, (fy + 0.5) / L.h, (fx + L.fw - 0.5) / L.w, (fy + L.fh - 0.5) / L.h, col);
end

function M.triangle(ax, ay, bx, by, cx, cy, col)
    if M.dry or M.list == nil then return false; end
    return (pcall(function() M.list:AddTriangleFilled({ ax, ay }, { bx, by }, { cx, cy }, col); end));
end

-----------------------------------------------------------------------
-- pictures: a PNG file becomes a texture the first time it is drawn, and is let go when nothing drew it for a while
-----------------------------------------------------------------------
local device;
local function getDevice()
    if device == nil and d3d8 ~= nil and type(d3d8.get_device) == 'function' then
        local ok, value = pcall(d3d8.get_device);
        if ok then device = value; end
    end
    return device;
end

-- (the same call as hcicons and the Squads menu make; the files are 32-bit PNG on power-of-two canvases, which
-- Direct3D takes as they are)
local function fromMemory(data, size, key)
    local dev = getDevice() or AshitaCore:GetDirect3DDevice();
    if dev == nil or data == nil or size == nil or size <= 0 then return nil; end
    local raw = ffi.new('IDirect3DTexture8*[1]');
    local result = ffi.C.D3DXCreateTextureFromFileInMemoryEx(ffi.cast('IDirect3DDevice8*', dev), data, size,
        0xFFFFFFFF, 0xFFFFFFFF, 1, 0, ffi.C.D3DFMT_A8R8G8B8, ffi.C.D3DPOOL_MANAGED,
        ffi.C.D3DX_DEFAULT, ffi.C.D3DX_DEFAULT, key or 0x00000000, nil, nil, raw);
    if result ~= 0 or raw[0] == nil then return nil; end
    local image = d3d8.gc_safe_release(ffi.cast('IDirect3DTexture8*', raw[0]));
    return { image = image, ptr = tonumber(ffi.cast('uint32_t', image)) };
end

-- (tests put their own loaders here)
function M.loadFile(path)
    local handle = io.open(path, 'rb');
    if handle == nil then return nil; end
    local data = handle:read('*a');
    handle:close();
    if data == nil or #data == 0 then return nil; end
    return fromMemory(data, #data);
end

-- an item's own icon, from the game's files (as the Squads menu shows gear)
function M.loadItem(id)
    local item = AshitaCore:GetResourceManager():GetItemById(id);
    if item == nil or item.Bitmap == nil or item.ImageSize == nil or item.ImageSize <= 0 then return nil; end
    return fromMemory(item.Bitmap, item.ImageSize, 0xFF000000);
end

local TEX, texCount = {}, 0;
M.KEEP = 25;          -- seconds a picture stays after it was last drawn
M.RETRY = 15;         -- seconds before a picture that would not load is tried again
M.loads = 0;          -- pictures made in this frame (a few a frame at most: no stutter when a big venture opens)
M.MAX_LOADS = 2;

local function get(key, loader, arg)
    local t = TEX[key];
    if t == nil or (t.ptr == nil and M.now - t.at > M.RETRY) then
        if M.dry then return nil; end
        if M.loads >= M.MAX_LOADS then return nil; end      -- (a later frame makes it)
        M.loads = M.loads + 1;
        local ok, value = pcall(loader, arg);
        if t == nil then texCount = texCount + 1; end
        t = (ok and type(value) == 'table' and value.ptr ~= nil) and value or {};
        t.at = M.now;
        TEX[key] = t;
    end
    if t.ptr == nil then return nil; end
    t.at = M.now;
    return t;
end

function M.tex(path) return get(path, M.loadFile, path); end
function M.item(id) return get('item:' .. tostring(id), M.loadItem, id); end

-- once in a while: let go of what nothing drew lately
function M.sweep()
    M.loads = 0;
    if M.now - (M.sweptAt or 0) < 5 then return; end
    M.sweptAt = M.now;
    for key, t in pairs(TEX) do
        if t.ptr ~= nil and M.now - t.at > M.KEEP then
            TEX[key] = nil;
            texCount = texCount - 1;
        end
    end
end

function M.release()
    TEX, texCount = {}, 0;
end

function M.count() return texCount; end

return M;
