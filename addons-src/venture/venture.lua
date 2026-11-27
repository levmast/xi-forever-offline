--[[
venture 1.1  (XI: Forever Offline, 2026-11-26)

Ventures in the game: the XIFO app's Ventures screen in a window. Send squad mates off to level at a real exp camp
of the era while you play, watch them fight, call them home, read what happened.

This add-on is NOT started with the game. The Squads menu's Ventures button (servermenu 1.36, Squad tab) loads it and
shows its window; "/addon load venture" does the same by hand, and OPTIONS > Addons in the launcher starts it with
the game for those who want that.

  /venture              the window, open / shut          /venture show, /venture hide   (what the menu's button sends)
  /venture size N       how big the scene is drawn: 1.5, 2 (default), 2.5, 3 or 4
  /venture sound        the short sounds, on / off          /venture music   the Ventures tune, on / off (starts off)
  /venture volume N     how loud both are, 0-100 (default 40)

It works with no internet and with no app: the launcher plans the venture (the same code the hub runs) and hands the
exp, gil and items to the game when the mates are back. With the XIFO app paired, ventures sent here show in the app
and ventures sent from the app show here.

This add-on only draws and asks. It talks to the launcher through small files in Ashita's config\addons\venture:
  state.lua, camps.lua, v\<venture>.lua, alive.txt   written by the launcher (launcher_ventures.py)
  req\<id>.txt                                        written here: char|start|id|slots|camp|hours, char|recall|id,
                                                      char|seen|id, char|open
Nothing is sent to the game server, and nothing leaves the PC from here.

For the Squads menu's button it keeps two small files in the character's folder (config\addons\xiforever\<Name>_<Id>),
as Gambits does: venture.loaded while it is loaded, venture.open while its window is shown (see "the Squads menu").

The screen is the app's (xifo-app/src/VenturesScreen.tsx) and the scene is the app's (stage.lua); the pictures are
the app's own (dev/ventures/build_venture_addon.py makes assets\ and art.lua from them). The music stays the game's
unless you turn the tune on.
]]

addon.name    = 'venture';
addon.author  = 'XI: Forever Offline (pixel art: Kaza)';
addon.version = '1.1';
addon.desc    = 'Ventures: send squad mates off to level, in a window like the XIFO app.';
addon.link    = 'https://xiforever.com';

require('common');
local imgui = require('imgui');
local ffi = require('ffi');

-----------------------------------------------------------------------
-- paths and this add-on's other files
-----------------------------------------------------------------------
local HERE = (addon.path or debug.getinfo(1, 'S').source:sub(2):gsub('[^\\/]*$', ''));
if not HERE:match('[\\/]$') then HERE = HERE .. '\\'; end
local ASSETS = HERE .. 'assets\\';

local function part(name)
    local ok, mod = pcall(dofile, HERE .. name .. '.lua');
    if not ok or mod == nil then error('venture: ' .. name .. '.lua could not be loaded: ' .. tostring(mod), 0); end
    return mod;
end
local gfx = part('gfx');
local ART = part('art');
local Stage = part('stage')(gfx, ART, ASSETS);

local function configDir()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath(); end);
    if not ok or type(base) ~= 'string' or base == '' then return nil; end
    if not base:match('[\\/]$') then base = base .. '\\'; end
    return base .. 'config\\addons\\venture\\';
end

local function makeDir(path)
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, path); end
end

local function say(text)
    print('\31\200[\31\05Ventures\31\200]\30\01 ' .. text);
end

local function has(name) return type(imgui[name]) == 'function'; end
local function G(name) return rawget(_G, name); end

-----------------------------------------------------------------------
-- what the window knows
-----------------------------------------------------------------------
local V = {
    open = { false },
    cfg = { size = 2, sound = true, music = false, volume = 40 },
    state = nil,            -- what the launcher wrote last (state.lua)
    stateLine = nil,        -- its first line: a change means read it again
    readAt = 0, aliveAt = 0, alive = 0, askedAt = 0, startedAt = os.clock(),
    campsSeq = nil, camps = { here = {}, hub = nil, first = nil, hereList = {}, hubList = nil },
    timelines = {},         -- venture id -> { stamp, list }
    pending = {},           -- request id -> { what, vid, at }
    seenHere = {},          -- ventures whose report was opened in this session
    note = '', noteAt = 0,
    who = nil, whoPicked = false, me = nil,
    picked = {},            -- slot -> true
    campId = nil, hours = 2,
    report = nil, how = false, allPast = false, confirm = nil,
    resize = nil,           -- a size asked for with /venture size: applied once
    counter = 0,
};

-- seconds since 1970, with a fraction (the scene's fades want more than whole seconds)
local clock0, time0 = os.clock(), os.time();
local function now()
    local t = time0 + (os.clock() - clock0);
    if math.abs(t - os.time()) > 1.5 then clock0, time0 = os.clock(), os.time(); t = time0; end
    return t;
end

-----------------------------------------------------------------------
-- settings (config\addons\venture\settings.txt)
-----------------------------------------------------------------------
local SIZES = { 1.5, 2, 2.5, 3, 4 };

local function loadSettings()
    local dir = configDir();
    local f = dir and io.open(dir .. 'settings.txt', 'r');
    if not f then return; end
    for line in f:lines() do
        local k, v = line:match('^%s*(%w+)%s*=%s*(.-)%s*$');
        if k == 'size' then V.cfg.size = math.max(1.5, math.min(4, tonumber(v) or 2));
        elseif k == 'sound' then V.cfg.sound = (v ~= 'off');
        elseif k == 'music' then V.cfg.music = (v == 'on');
        elseif k == 'volume' then V.cfg.volume = math.max(0, math.min(100, tonumber(v) or 40));
        elseif k == 'hours' then V.hours = tonumber(v) or 2; end
    end
    f:close();
end

local function saveSettings()
    local dir = configDir();
    if not dir then return; end
    makeDir(dir);
    local f = io.open(dir .. 'settings.txt', 'w');
    if not f then return; end
    f:write(string.format('size = %s\nsound = %s\nmusic = %s\nvolume = %d\nhours = %d\n', tostring(V.cfg.size), V.cfg.sound and 'on' or 'off',
        V.cfg.music and 'on' or 'off', V.cfg.volume, V.hours));
    f:close();
end

-----------------------------------------------------------------------
-- sound (as Tetra Master does it: Windows plays a .wav at full volume whatever the game's own setting is, so each
-- sound is played from a copy at the chosen volume, made once in config\addons\venture\sound\<volume>\)
-----------------------------------------------------------------------
pcall(ffi.cdef, [[
    int __stdcall PlaySoundA(const char* pszSound, void* hmod, uint32_t fdwSound);
    uint32_t __stdcall mciSendStringA(const char* cmd, char* ret, uint32_t len, void* hwnd);
]]);
local okWinmm, winmm = pcall(ffi.load, 'winmm');

local function scaledWav(src, name, volume)
    if volume >= 100 then return src; end
    local dir = configDir();
    if not dir then return src; end
    dir = dir .. 'sound\\';
    makeDir(dir);
    dir = dir .. tostring(volume) .. '\\';
    local out = dir .. name;
    local f = io.open(out, 'rb');
    if f then f:close(); return out; end
    local inf = io.open(src, 'rb');
    if not inf then return src; end
    local data = inf:read('*a');
    inf:close();
    if #data < 44 or data:sub(1, 4) ~= 'RIFF' or data:sub(9, 12) ~= 'WAVE' then return src; end
    local buf = ffi.new('uint8_t[?]', #data);
    ffi.copy(buf, data, #data);
    local pos, bits = 12, 16;
    while pos + 8 <= #data do
        local id = data:sub(pos + 1, pos + 4);
        local size = buf[pos + 4] + buf[pos + 5] * 256 + buf[pos + 6] * 65536 + buf[pos + 7] * 16777216;
        if id == 'fmt ' then
            bits = buf[pos + 22] + buf[pos + 23] * 256;
        elseif id == 'data' then
            if bits ~= 16 then return src; end
            local n = math.floor(math.min(size, #data - pos - 8) / 2);
            local s = ffi.cast('int16_t*', buf + pos + 8);
            local k = volume / 100;
            for i = 0, n - 1 do s[i] = math.floor(s[i] * k); end
            makeDir(dir);
            local w = io.open(out, 'wb');
            if not w then return src; end
            w:write(ffi.string(buf, #data));
            w:close();
            return out;
        end
        pos = pos + 8 + size + (size % 2);
    end
    return src;
end

local function sfx(name, share)
    if not V.cfg.sound or not okWinmm then return; end
    local volume = math.floor(V.cfg.volume * (share or 0.8) / 5 + 0.5) * 5;      -- (in steps of 5: few copies)
    if volume <= 0 then return; end
    local ok, path = pcall(scaledWav, ASSETS .. 'snd\\' .. name .. '.wav', name .. '.wav', volume);
    if not ok then return; end
    pcall(function() winmm.PlaySoundA(path, nil, 0x00020003); end);                -- SND_ASYNC | SND_NODEFAULT | SND_FILENAME
end

local musicOpen = false;
local function music(on)
    if not okWinmm then return; end
    if on and not musicOpen then
        pcall(function()
            winmm.mciSendStringA('open "' .. ASSETS .. 'snd\\ventures.mp3" type mpegvideo alias venture_music', nil, 0, nil);
            winmm.mciSendStringA('setaudio venture_music volume to ' .. tostring(V.cfg.volume * 10), nil, 0, nil);
            winmm.mciSendStringA('play venture_music repeat', nil, 0, nil);
        end);
        musicOpen = true;
    elseif not on and musicOpen then
        pcall(function() winmm.mciSendStringA('close venture_music', nil, 0, nil); end);
        musicOpen = false;
    end
end

-----------------------------------------------------------------------
-- reading what the launcher wrote
-----------------------------------------------------------------------
local function myName()
    local ok, name = pcall(function() return AshitaCore:GetMemoryManager():GetParty():GetMemberName(0); end);
    if ok and type(name) == 'string' and name:match('^%a+$') then return name; end
    return nil;
end

-- a Lua file the launcher wrote: `return { ... }`, run with nothing in reach
local function loadData(path)
    local chunk = loadfile(path);
    if not chunk then return nil; end
    setfenv(chunk, {});
    local ok, value = pcall(chunk);
    if ok and type(value) == 'table' then return value; end
    return nil;
end

local function firstLine(path)
    local f = io.open(path, 'r');
    if not f then return nil; end
    local line = f:read('*l');
    f:close();
    return line;
end

local function setNote(text)
    V.note, V.noteAt = text or '', now();
end

local function answer(id, p, r)
    if r.error then
        setNote(tostring(r.error));
        if p.what == 'start' then sfx('miss', 0.5); end
        return;
    end
    if p.what == 'start' then
        sfx('depart');
        V.picked = {};
        setNote(r.note or '');
    end
end

local function readCamps(dir, seq)
    local data = loadData(dir .. 'camps.lua');
    if not data then return; end
    local function byId(list)
        if type(list) ~= 'table' then return nil; end
        local map = {};
        for _, c in ipairs(list) do map[c.id] = c; end
        return map;
    end
    V.camps = { here = byId(data['local']) or {}, hub = byId(data.hub), first = (data['local'] or {})[1],
                hereList = data['local'] or {}, hubList = data.hub };
    V.campsSeq = seq;
end

local function readState()
    local dir = configDir();
    if not dir then return; end
    local t = os.clock();
    if t - V.aliveAt >= 3 then
        V.aliveAt = t;
        local line = firstLine(dir .. 'alive.txt');
        V.alive = tonumber(line or '') or V.alive;
    end
    if t - V.readAt < 0.5 then return; end
    V.readAt = t;
    local line = firstLine(dir .. 'state.lua');
    if line == nil or line == V.stateLine then return; end
    local st = loadData(dir .. 'state.lua');
    if not st then return; end                       -- (caught while it was being swapped: the next look has it)
    V.state, V.stateLine = st, line;
    if st.campsSeq ~= V.campsSeq then readCamps(dir, st.campsSeq); end
    for id, p in pairs(V.pending) do
        local r = type(st.replies) == 'table' and st.replies[id] or nil;
        if r then
            V.pending[id] = nil;
            answer(id, p, r);
        end
    end
    -- timelines of ventures that are gone
    local live = {};
    for _, v in ipairs(st.ventures or {}) do live[v.id] = true; end
    for id in pairs(V.timelines) do
        if not live[id] then V.timelines[id] = nil; end
    end
end

-- the launcher is running (it says so every few seconds)
local function launcherUp()
    return os.time() - V.alive < 25;
end

-- one venture's timeline (the launcher keeps it in a file of its own)
local function timeline(v)
    if v.bare or not v.ev then return nil; end
    local have = V.timelines[v.id];
    if have and have.stamp == v.ev then return have.list; end
    if have and have.triedAt and os.clock() - have.triedAt < 1 and have.stampTried == v.ev then return have.list; end
    local dir = configDir();
    local list = dir and loadData(dir .. 'v\\' .. v.id .. '.lua') or nil;
    if list then
        V.timelines[v.id] = { stamp = v.ev, list = list };
        return list;
    end
    V.timelines[v.id] = { stamp = have and have.stamp, list = have and have.list, triedAt = os.clock(), stampTried = v.ev };
    return have and have.list or nil;
end

-----------------------------------------------------------------------
-- asking the launcher
-----------------------------------------------------------------------
local function ask(line, what, vid)
    local dir = configDir();
    if not dir then return nil; end
    makeDir(dir);
    makeDir(dir .. 'req\\');
    V.counter = V.counter + 1;
    local id = string.format('r%d_%d', os.time(), V.counter);
    local f = io.open(dir .. 'req\\' .. id .. '.part', 'w');
    if not f then return nil; end
    f:write(line .. '\n');
    f:close();
    if not os.rename(dir .. 'req\\' .. id .. '.part', dir .. 'req\\' .. id .. '.txt') then return nil; end
    if what then V.pending[id] = { what = what, vid = vid, at = os.clock() }; end
    return id;
end

local function busy(what, vid)
    for _, p in pairs(V.pending) do
        if p.what == what and (vid == nil or p.vid == vid) then return true; end
    end
    return false;
end

local function newVentureId()
    local s = 'v';
    for _ = 1, 20 do s = s .. string.format('%x', math.random(0, 15)); end
    return s;
end

-- "the window is showing": the launcher then looks every few seconds, not every half minute
local function keepFresh(char, soon)
    local t = os.clock();
    if t - V.askedAt < (soon and 4 or 20) then return; end
    V.askedAt = t;
    ask((char or V.me or 'x') .. '|open');
end

-----------------------------------------------------------------------
-- the app's look (its Dark Fantasy colours) and words
-----------------------------------------------------------------------
local TH = {
    ink = '#E9E2D0', dim = '#A89F8E', link = '#D9B66A', err = '#F08070', good = '#9BC78A',
    back = 'rgba(10,6,18,0.96)', winBg = 'rgba(14,9,24,0.94)', paneBg = 'rgba(5,3,10,0.6)', paneEdge = '#5A4626',
    rowLine = 'rgba(232,200,120,0.12)', rowPressed = 'rgba(138,106,46,0.28)', rowHover = 'rgba(138,106,46,0.12)', title = '#E8C878',
    btn = { '#3A2350', '#2A1A3E', '#1A0F28' }, btnEdge = '#8A6A2E', btnText = '#E8C878',
    primary = { '#E8C878', '#B8903E', '#7A5A1E' }, primaryEdge = '#F3DFA0', primaryText = '#1A0F06',
    off = { '#241A2E', '#18101F' }, offText = '#6E6478',
    on = '#B8903E', onEdge = '#F3DFA0', onText = '#1A0F06',
    barBg = 'rgba(0,0,0,0.5)', barFill = '#B8903E',
};
local RACE = { 'Hume', 'Hume', 'Elvaan', 'Elvaan', 'Tarutaru', 'Tarutaru', 'Mithra', 'Galka' };
local JOBS = Stage.JOBS;

local function n(v)
    local s = tostring(math.floor((tonumber(v) or 0) + 0.5));
    while true do
        local k;
        s, k = s:gsub('^(-?%d+)(%d%d%d)', '%1,%2');
        if k == 0 then return s; end
    end
end

local function clockText(sec)
    sec = math.max(0, math.floor(sec));
    local h, m, s = math.floor(sec / 3600), math.floor((sec % 3600) / 60), sec % 60;
    if h > 0 then return string.format('%dh %02dm', h, m); end
    return string.format('%d:%02d', m, s);
end

-- who is on a venture, short: "Volker & Ayame", "Volker, Ayame +4"
local function names(ms)
    if #ms <= 2 then
        local t = {};
        for _, m in ipairs(ms) do t[#t + 1] = m.name; end
        return table.concat(t, ' & ');
    end
    return string.format('%s, %s +%d', ms[1].name, ms[2].name, #ms - 2);
end

local function lineOf(e, camps)
    local cc = e.c and camps[e.c];
    local mob = (cc and e.m ~= nil and cc.mobs[e.m + 1]) and cc.mobs[e.m + 1].name or '';
    if e.k == 'arrive' then return 'Arrived at ' .. ((camps[e.camp or ''] or {}).title or 'camp') .. '.'; end
    if e.k == 'move' then return 'Moved on to ' .. ((camps[e.camp or ''] or {}).title or 'a new camp') .. '.'; end
    if e.k == 'rest' then return 'Resting up.'; end
    if e.k == 'party' then return 'Joined a party.'; end
    if e.k == 'kill' then
        if e.up and #e.up > 0 then return string.format('Defeated a %s and levelled up to %s!', mob, tostring(e.up[#e.up][2])); end
        if e.sc then return string.format('Skillchain: %s! Defeated a %s.', tostring(e.sc), mob); end
        if e.close then return string.format('Close call! Defeated a %s.', mob); end
        if e.link then return string.format('A %s linked. Defeated both.', mob); end
        return string.format('Defeated a %s (+%s exp).', mob, tostring(e.x));
    end
    return '';
end

-----------------------------------------------------------------------
-- laying out: text that wraps, sections, buttons. Sizes follow the game's font (13 px is 100 %).
-----------------------------------------------------------------------
local U = { k = 1, ids = 0 };

local function px(v) return math.floor(v * U.k + 0.5); end
local function body() return px(14); end
local function small() return px(12.5); end
local function tiny() return px(11); end
local function lineH(size) return math.floor(size * 1.34 + 0.5); end

local flows, flowCount = {}, 0;

-- spans { { text, colour, bold }, ... } set in lines no wider than w. Returns the lines (each a list of runs with
-- their x) and the height.
local function flow(spans, size, w, maxLines)
    local key = { size, w, maxLines or 0 };
    for _, s in ipairs(spans) do key[#key + 1] = s[1]; key[#key + 1] = s[3] and 'b' or '-'; end
    key = table.concat(key, '\1');
    local got = flows[key];
    if got then return got; end
    local space = gfx.width(' ', size);
    local lines, line, x = {}, {}, 0;
    local function push()
        lines[#lines + 1] = line;
        line, x = {}, 0;
    end
    local trail = false;                 -- the span before ended in a space
    for si, s in ipairs(spans) do
        local text = tostring(s[1] or '');
        local lead = trail or text:match('^%s') ~= nil;
        local first = true;
        trail = text:match('%s$') ~= nil;
        for word in text:gmatch('%S+') do
            local ww = gfx.width(word, size);
            local gap = ((not first) or lead) and x > 0 and space or 0;
            local bold = s[3] and 1 or 0;                -- (bold is the text once more a pixel to the right)
            if x > 0 and x + gap + ww + bold > w then
                push();
                gap = 0;
            end
            local last = line[#line];
            if last and last.span == si and gap > 0 then
                last.text = last.text .. ' ' .. word;
                last.w = last.w + gap + ww;
                x = x + gap + ww;
            else
                line[#line + 1] = { span = si, x = x + gap, text = word, w = ww + bold };
                x = x + gap + ww + bold;
            end
            first = false;
        end
    end
    if #line > 0 then push(); end
    if maxLines and #lines > maxLines then
        while #lines > maxLines do lines[#lines] = nil; end
        local l = lines[#lines];
        local r = l[#l];
        if r then r.text = gfx.fit(r.text .. ' ...', size, math.max(10, w - r.x), spans[r.span][3]); end
    end
    got = { lines = lines, h = #lines * lineH(size) };
    if flowCount > 400 then flows, flowCount = {}, 0; end
    flows[key] = got;
    flowCount = flowCount + 1;
    return got;
end

-- draws them at x, y; returns the height
local function para(x, y, w, spans, size, maxLines)
    local f = flow(spans, size, w, maxLines);
    if not gfx.dry then
        for i, line in ipairs(f.lines) do
            for _, r in ipairs(line) do
                local s = spans[r.span];
                gfx.text(x + r.x, y + (i - 1) * lineH(size), gfx.col(s[2] or TH.ink), r.text, size, s[3]);
            end
        end
    end
    return f.h;
end

-- something to click: an unseen button over a box (ImGui decides who gets the click, so windows on top still win)
local function hit(id, x, y, w, h)
    if gfx.dry then return false, false, false; end
    imgui.SetCursorScreenPos({ x, y });
    local clicked = imgui.InvisibleButton('##venture_' .. id, { math.max(1, w), math.max(1, h) });
    return clicked == true, imgui.IsItemHovered() == true, has('IsItemActive') and imgui.IsItemActive() == true;
end

-- the app's button: `kind` nil, 'primary' (the gold one), 'on' (a chosen one) or 'off' (cannot be pressed)
local function button(id, label, x, y, w, h, kind, size)
    size = size or px(12.5);
    label = label:upper();                         -- (the app's buttons are in Cinzel)
    w = w or (gfx.width(label, size) + px(18));
    h = h or px(26);
    local clicked, hover, held = false, false, false;
    if kind ~= 'off' then clicked, hover, held = hit(id, x, y, w, h); end
    if not gfx.dry then
        local fill = kind == 'primary' and TH.primary or (kind == 'off' and TH.off or (kind == 'on' and { TH.on, TH.on } or TH.btn));
        if held then
            local r = {};
            for i = #fill, 1, -1 do r[#r + 1] = fill[i]; end
            fill = r;
        end
        local edge = kind == 'primary' and TH.primaryEdge or (kind == 'on' and TH.onEdge or TH.btnEdge);
        gfx.rect(x, y, x + w, y + h, gfx.col(edge), 3);
        gfx.vgrad(x + 1, y + 1, x + w - 1, y + h - 1, fill);
        gfx.rect(x + 2, y + 2, x + w - 2, y + 1 + (h - 2) * 0.45, gfx.col('#FFFFFF', hover and 0.10 or 0.05));
        local col = kind == 'primary' and TH.primaryText or (kind == 'off' and TH.offText or (kind == 'on' and TH.onText or TH.btnText));
        local text = gfx.fit(label, size, w - 6);
        gfx.text(x + (w - gfx.width(text, size)) / 2, y + (h - size) / 2 - 1, gfx.col(col), text, size, kind == 'primary');
    end
    return clicked;
end

-- a darker inset inside a section, for lists: call before its rows with the height they will have
local function pane(x, y, w, h)
    if not gfx.dry and h > 0 then gfx.rect(x, y, x + w, y + h, gfx.col(TH.paneBg), 6); end
end

-- a small heading inside a section; `right`: a hint at its end
local function strip(x, y, w, title, right)
    local size = tiny();
    if not gfx.dry then
        gfx.text(x + px(4), y + px(7), gfx.col(TH.dim), title:upper(), size, true);
        if right then gfx.text(x + w - px(4) - gfx.width(right, size), y + px(7), gfx.col(TH.dim), right, size); end
    end
    return px(7) + lineH(size) + px(3);
end

-- a section: the app's card. `draw(bx, by, bw)` draws what is in it and returns its height. The card's own height is
-- known from the dry run of this frame (U.heights).
local function card(x, y, w, title, opts, draw)
    opts = opts or {};
    U.ids = U.ids + 1;
    local id = U.ids;
    local pad = opts.pad or px(10);
    local titleH = (title and title ~= '') and px(30) or 0;
    local h = U.heights[id] or 0;
    local over = false;
    if opts.click and not gfx.dry and h > 0 then
        local clicked, hover = hit('card' .. tostring(opts.key or id), x, y, w, h);
        over = hover;
        if clicked then opts.click(); end
    end
    if not gfx.dry and h > 0 then
        gfx.rect(x, y, x + w, y + h, gfx.col(TH.paneEdge), 8);
        gfx.rect(x + 1, y + 1, x + w - 1, y + h - 1, gfx.col('#0E0918'), 7);
        if over then gfx.rect(x + 1, y + 1, x + w - 1, y + h - 1, gfx.col(TH.rowHover), 7); end
        if titleH > 0 then
            local size = px(12.5);                 -- (the app's titles are in Cinzel, whose small letters are small capitals)
            title = title:upper();
            local room = w - px(24);
            if opts.right then
                local rw = gfx.width(opts.right, small());
                gfx.text(x + w - px(10) - rw, y + (titleH - small()) / 2, gfx.col(TH.dim), opts.right, small());
                room = room - rw - px(10);
            end
            if opts.close then room = room - px(26); end
            gfx.text(x + px(12), y + (titleH - size) / 2, gfx.col(TH.title), gfx.fit(title, size, room, true), size, true);
            gfx.rect(x + 1, y + titleH, x + w - 1, y + titleH + 1, gfx.col(TH.rowLine));
        end
    end
    if opts.close and titleH > 0 then
        local s = px(22);
        local bx, by = x + w - px(8) - s, y + (titleH - s) / 2;
        local clicked, hover = hit('close' .. tostring(id), bx, by, s, s);
        if not gfx.dry then
            local c = gfx.col(hover and TH.ink or TH.dim);
            for i = 0, px(9) do                              -- an x, drawn (no font has to have one)
                gfx.rect(bx + px(6) + i, by + px(6) + i, bx + px(6) + i + 2, by + px(6) + i + 2, c);
                gfx.rect(bx + s - px(6) - i - 2, by + px(6) + i, bx + s - px(6) - i, by + px(6) + i + 2, c);
            end
        end
        if clicked then opts.close(); end
    end
    local inner = draw(x + 1 + pad, y + 1 + titleH + (titleH > 0 and 1 or 0) + pad, w - 2 - 2 * pad) or 0;
    local total = 1 + titleH + (titleH > 0 and 1 or 0) + pad + inner + pad + 1;
    if gfx.dry then U.heights[id] = total; end
    return total;
end

-- the corners of a picture rounded off with the colour behind it
local function roundOff(x0, y0, x1, y1, r, colour)
    if gfx.dry then return; end
    local c = gfx.col(colour);
    for i = 0, r - 1 do
        local dy = r - i - 0.5;
        local cut = math.ceil(r - math.sqrt(math.max(0, r * r - dy * dy)));
        if cut > 0 then
            gfx.rect(x0, y0 + i, x0 + cut, y0 + i + 1, c);
            gfx.rect(x1 - cut, y0 + i, x1, y0 + i + 1, c);
            gfx.rect(x0, y1 - i - 1, x0 + cut, y1 - i, c);
            gfx.rect(x1 - cut, y1 - i - 1, x1, y1 - i, c);
        end
    end
end

-- a small middle dot between two pieces of text (drawn: every font has a square)
local function dotted(x, y, pieces, size, colour)
    local at = x;
    for i, text in ipairs(pieces) do
        if i > 1 then
            if not gfx.dry then
                local d = math.max(2, math.floor(size / 6));
                gfx.rect(at + px(5), y + size * 0.55 - d / 2, at + px(5) + d, y + size * 0.55 + d / 2, gfx.col(colour));
            end
            at = at + px(10) + math.max(2, math.floor(size / 6));
        end
        if not gfx.dry then gfx.text(at, y, gfx.col(colour), text, size); end
        at = at + gfx.width(text, size);
    end
    return at - x;
end

local function dottedWidth(pieces, size)
    local w = 0;
    for i, text in ipairs(pieces) do
        if i > 1 then w = w + px(10) + math.max(2, math.floor(size / 6)); end
        w = w + gfx.width(text, size);
    end
    return w;
end

-----------------------------------------------------------------------
-- the scene in the window
-----------------------------------------------------------------------
local function scene(x, y, w, v, o)
    local P = w / Stage.W;
    local h = Stage.H * P;
    if gfx.dry then return h; end
    o.tick = math.floor(os.clock() * 1000 / 120);
    o.unix = os.time();
    o.minFont = math.max(px(10), 0);
    Stage.draw(x, y, P, o);
    return h;
end

local function campsOf(v)
    if v and v.src == 'hub' and V.camps.hub then return V.camps.hub; end
    return V.camps.here;
end

-----------------------------------------------------------------------
-- the report of a venture that is back
-----------------------------------------------------------------------
local function openReport(v)
    local fresh = not (v.seen or V.seenHere[v.id]);
    if fresh then
        local up = false;
        if v.results and v.results.levels then
            for i, lv in ipairs(v.results.levels) do
                if v.mates[i] and lv > (v.mates[i].level or lv) then up = true; end
            end
        end
        sfx(up and 'levelup' or 'home');
        V.seenHere[v.id] = true;
        ask(v.char .. '|seen|' .. v.id, 'seen', v.id);
    else
        sfx('select', 0.5);
    end
    V.report = v.id;
end

local function report(x, y, w, v)
    local camps = campsOf(v);
    local events = timeline(v) or {};
    local total = v['end'] - v.start;
    local arrive, firstKill, best;
    for _, e in ipairs(events) do
        if e.k == 'arrive' and not arrive then arrive = e; end
        if e.k == 'kill' then
            firstKill = firstKill or e;
            if not best and (e.up or e.sc) then best = e; end
        end
    end
    best = best or firstKill;
    local stills = {
        { 'Setting off', math.max(1, ((arrive and arrive.t) or 60) / 2), 'road' },
        { 'At camp', firstKill and (firstKill.t - 5) or (total / 3), 'fight' },
        { (best and best.up) and 'Level up!' or ((best and best.sc) and tostring(best.sc) or 'The hunt'), best and (best.t - 2) or (total / 2), 'fight' },
        { 'Home again', total, 'home' },
    };
    return card(x, y, w, 'Report: ' .. names(v.mates), { close = function() V.report = nil; end }, function(bx, by, bw)
        local at = by;
        local gap = px(4);
        local cw = math.floor((bw - gap) / 2);
        local ch = 0;
        for i, s in ipairs(stills) do
            local sx = bx + ((i - 1) % 2) * (cw + gap);
            local sy = at + math.floor((i - 1) / 2) * (ch + gap);
            ch = scene(sx, sy, cw, v, { camps = camps, anyCamp = V.camps.first, events = events, sec = s[2], over = s[3] == 'home',
                mates = v.mates, party = v.party, still = s[3], label = s[1] });
        end
        at = at + 2 * ch + gap + px(8);

        -- what happened
        local story = v.story or {};
        local sh = px(8);
        for _, line in ipairs(story) do sh = sh + flow({ { line } }, body(), bw - px(16)).h + px(4); end
        sh = sh + px(4);
        pane(bx, at, bw, sh);
        local ty = at + px(8);
        for _, line in ipairs(story) do ty = ty + para(bx + px(8), ty, bw - px(16), { { line } }, body()) + px(4); end
        at = at + sh;

        at = at + strip(bx, at, bw, 'What they brought home');
        local res = v.results or { exp = {}, levels = {}, items = {} };
        local rows = {};
        for i, m in ipairs(v.mates) do
            local spans = { { m.name, nil, true }, { ': +' .. n(res.exp[i] or 0) .. ' exp' } };
            if (res.levels[i] or 0) > (m.level or 0) then
                spans[#spans + 1] = { string.format('  (level %d to %d)', m.level, res.levels[i]), TH.good };
            end
            rows[#rows + 1] = { spans = spans };
        end
        if (res.gil or 0) > 0 then rows[#rows + 1] = { spans = { { n(res.gil) .. ' gil' } } }; end
        for _, it in ipairs(res.items or {}) do
            rows[#rows + 1] = { item = it[1], spans = { { tostring(it[3] or ('item ' .. tostring(it[1]))) .. ((it[2] or 1) > 1 and (' x' .. tostring(it[2])) or '') } } };
        end
        local last = v.applied and 'Already in your game: exp and gil to the squad and you, items in your delivery box.'
            or 'Arrives in your game in a moment (the launcher hands it over while you play): exp and gil straight away, items in your delivery box.';
        local icon = px(20);
        local ph = px(8);
        for _, r in ipairs(rows) do
            ph = ph + math.max(r.item and (icon + px(2)) or 0, flow(r.spans, body(), bw - px(16) - (r.item and (icon + px(6)) or 0)).h);
        end
        ph = ph + px(6) + flow({ { last, TH.dim } }, small(), bw - px(16)).h + px(8);
        pane(bx, at, bw, ph);
        ty = at + px(8);
        for _, r in ipairs(rows) do
            local off = r.item and (icon + px(6)) or 0;
            if r.item and not gfx.dry then
                local tex = gfx.item(r.item);
                if tex then gfx.image(tex, bx + px(8), ty, bx + px(8) + icon, ty + icon); end
            end
            local hgt = para(bx + px(8) + off, ty + (r.item and math.max(0, (icon - lineH(body())) / 2) or 0), bw - px(16) - off, r.spans, body());
            ty = ty + math.max(r.item and (icon + px(2)) or 0, hgt);
        end
        ty = ty + px(6);
        para(bx + px(8), ty, bw - px(16), { { last, TH.dim } }, small());
        at = at + ph + px(8);

        if button('reportback', 'Back', bx, at, nil, nil) then V.report = nil; end
        at = at + px(26);
        return at - by;
    end);
end

-----------------------------------------------------------------------
-- the screen (the app's VenturesScreen)
-----------------------------------------------------------------------
local function screen(x, y, w)
    local st = V.state;
    local at = y;
    local gap = px(10);
    local t = now();

    -- the launcher has to be there: it plans the ventures and keeps their times
    if not st then
        return card(x, at, w, 'Ventures', nil, function(bx, by, bw)
            return para(bx, by, bw, { { launcherUp() and 'Reading your squads...' or
                'Waiting for the launcher. Ventures are planned by the XI: Forever Offline launcher: start the game with its PLAY button and this window fills in.' } }, body());
        end);
    end

    local roster = st.roster or {};
    local char;
    for _, r in ipairs(roster) do
        if r.name == V.who then char = r; end
    end
    char = char or roster[1];
    local partyFrom = st.partyFrom or 10;

    if V.note ~= '' then
        at = at + para(x + px(4), at, w - px(8), { { V.note, TH.err } }, body()) + px(6);
    end
    if not launcherUp() then
        at = at + para(x + px(4), at, w - px(8), { { 'The launcher is not running, so nothing can be sent or called home right now. The mates out there carry on.', TH.err } },
            small()) + px(6);
    elseif st.paired and not st.hub and st.canSend then
        local why = st.online and 'The hub does not take ventures from the game yet (it needs its update)' or 'The hub can\'t be reached';
        at = at + para(x + px(4), at, w - px(8), { { why .. ': a venture sent now stays on this PC and won\'t show in the app.', TH.dim } }, small()) + px(6);
    end

    -- which character (when there are several)
    if #roster > 1 then
        local cx, cy = x, at;
        for _, r in ipairs(roster) do
            local bw = gfx.width(r.name:upper(), px(12)) + px(18);
            if cx > x and cx + bw > x + w then cx, cy = x, cy + px(24) + px(6); end
            if button('who' .. r.name, r.name, cx, cy, bw, px(24), (char and char.name == r.name) and 'on' or nil, px(12)) then
                V.who, V.whoPicked, V.picked, V.confirm = r.name, true, {}, nil;
            end
            cx = cx + bw + px(6);
        end
        at = cy + px(24) + gap;
    end

    local mine, out, back = {}, {}, {};
    for _, v in ipairs(st.ventures or {}) do
        if char and v.char == char.name then
            mine[#mine + 1] = v;
            if v.bare or (t + (v.skew or 0)) < v['end'] then out[#out + 1] = v; else back[#back + 1] = v; end
        end
    end
    table.sort(back, function(a, b) return a['end'] > b['end']; end);
    local fresh, past, away = {}, {}, {};
    for _, v in ipairs(back) do
        if v.seen or V.seenHere[v.id] then past[#past + 1] = v; else fresh[#fresh + 1] = v; end
    end
    for _, v in ipairs(out) do
        for _, slot in ipairs(v.slots or {}) do away[slot] = true; end
    end

    local intro = { { 'Send squad mates out to level at the real exp camps of the era while you do something else. They earn ' },
        { n(st.expPerHour or 3000) .. ' exp an hour', nil, true },
        { ', plus whatever the camp drops. It all arrives in your game: exp and gil when you\'re logged in, items in your delivery box.' } };

    if #mine == 0 then
        at = at + card(x, at, w, 'Ventures', nil, function(bx, by, bw)
            local h = para(bx, by, bw, intro, body());
            if #roster == 0 then
                h = h + px(6) + para(bx, by + h + px(6), bw, { { 'No squads yet. Your squad mates show up here a few seconds after you log in (the launcher reads them).' } }, body());
            end
            return h;
        end) + gap;
    end

    -- back, not read yet
    for _, v in ipairs(fresh) do
        local camps = campsOf(v);
        local c = camps[v.camp];
        local events = timeline(v);
        -- (it ended this minute: the launcher has the rest in a moment, so it is asked to look now)
        if not v.results and (t + (v.skew or 0)) - v['end'] < 60 then keepFresh(v.char, true); end
        at = at + card(x, at, w, 'Back from ' .. (c and c.title or 'their venture'), { pad = 0, key = 'f' .. v.id, click = function() openReport(v); end },
            function(bx, by, bw)
                local h = scene(bx, by, bw, v, { camps = camps, anyCamp = V.camps.first, events = events or {}, sec = v['end'] - v.start, over = true,
                    mates = v.mates, party = v.party, label = c and c.title });
                local ux, uy, uw = bx + px(10), by + h + px(10), bw - px(20);
                if not gfx.dry then gfx.text(ux, uy, gfx.col(TH.ink), gfx.fit(names(v.mates), body(), uw, true), body(), true); end
                uy = uy + lineH(body());
                local res = v.results;
                local spans;
                if res then
                    local items = 0;
                    for _, it in ipairs(res.items or {}) do items = items + (it[2] or 0); end
                    spans = { { '+' .. n((res.exp or {})[1] or 0) .. ' exp' .. ((res.gil or 0) > 0 and (', ' .. n(res.gil) .. ' gil') or '') .. ', ' .. tostring(items) .. ' item(s).' },
                        { '  Read the report >', TH.link, true } };
                elseif v.src == 'hub' and st.paired and not st.online then
                    spans = { { 'Back. What they brought shows here once the hub can be reached.', TH.dim } };
                else
                    spans = { { 'Just back...', TH.dim } };
                end
                uy = uy + para(ux, uy, uw, spans, small());
                return (uy + px(10)) - by;
            end) + gap;
    end

    -- out now
    for _, v in ipairs(out) do
        if v.bare then
            local who = {};
            for _, slot in ipairs(v.slots or {}) do
                for _, m in ipairs(char.mates or {}) do
                    if m.slot == slot then who[#who + 1] = m; end
                end
            end
            at = at + card(x, at, w, (v.campTitle and v.campTitle ~= '') and v.campTitle or 'On a venture',
                { right = 'back in ' .. clockText(v['end'] - (t + (v.skew or 0))) }, function(bx, by, bw)
                    return para(bx, by, bw, { { #who > 0 and names(who) or 'Squad mates', nil, true },
                        { ' left from the XIFO app. The timer is right; the scene shows here when the hub has told the launcher more.', TH.dim } }, small());
                end) + gap;
        else
            local camps = campsOf(v);
            local events = timeline(v) or {};
            local tv = t + (v.skew or 0);
            local sec = tv - v.start;
            local s = Stage.stateAt(events, sec, false);
            local exp, kills, latest = 0, 0, '';
            for _, e in ipairs(events) do
                if e.t > sec then break; end
                if e.k == 'kill' then exp, kills = exp + (e.x or 0), kills + 1; end
            end
            do          -- the newest of the last four that says something
                local shown = {};
                for _, e in ipairs(events) do
                    if e.t > sec then break; end
                    shown[#shown + 1] = e;
                end
                for i = #shown, math.max(1, #shown - 3), -1 do
                    local line = lineOf(shown[i], camps);
                    if line ~= '' then latest = line; break; end
                end
            end
            local c = camps[s.camp];
            local label = s.phase == 'road' and 'On the road...' or (s.phase == 'rest' and 'Resting' or (c and c.spot));
            at = at + card(x, at, w, c and c.title or 'On the road', { pad = 0, right = 'back in ' .. clockText(v['end'] - tv) }, function(bx, by, bw)
                local h = scene(bx, by, bw, v, { camps = camps, anyCamp = V.camps.first, events = events, sec = sec, over = false,
                    mates = v.mates, party = v.party, label = label });
                if not gfx.dry then
                    gfx.rect(bx, by + h, bx + bw, by + h + px(4), gfx.col(TH.barBg));
                    gfx.rect(bx, by + h, bx + bw * math.min(1, sec / math.max(1, v['end'] - v.start)), by + h + px(4), gfx.col(TH.barFill));
                end
                local ux, uy, uw = bx + px(10), by + h + px(4) + px(10), bw - px(20);
                local tally = { tostring(kills) .. ' kills', '+' .. n(exp) .. ' exp' };
                local tw = dottedWidth(tally, small());
                if not gfx.dry then
                    gfx.text(ux, uy, gfx.col(TH.ink), gfx.fit(names(v.mates), body(), uw - tw - px(8), true), body(), true);
                    dotted(ux + uw - tw, uy + (body() - small()) / 2, tally, small(), TH.ink);
                end
                uy = uy + lineH(body()) + px(4);
                if V.confirm == v.id then
                    local yes, no = px(50), px(44);
                    local th = para(ux, uy, uw - yes - no - px(16), { { 'Call them home early? They come back now with what they have earned so far.' } }, small());
                    if button('yes' .. v.id, 'Yes', ux + uw - yes - no - px(6), uy, yes, px(24), 'primary', px(12)) then
                        V.confirm = nil;
                        ask(v.char .. '|recall|' .. v.id, 'recall', v.id);
                    end
                    if button('no' .. v.id, 'No', ux + uw - no, uy, no, px(24), nil, px(12)) then V.confirm = nil; end
                    uy = uy + math.max(th, px(24));
                else
                    local label2 = busy('recall', v.id) and 'Calling...' or 'Call home';
                    local cw = gfx.width('CALLING...', px(12)) + px(18);
                    local th = para(ux, uy + px(2), uw - cw - px(8), { { latest, TH.dim } }, small(), 2);
                    if button('home' .. v.id, label2, ux + uw - cw, uy, cw, px(24), (busy('recall', v.id) or not launcherUp()) and 'off' or nil, px(12)) then
                        V.confirm = v.id;
                    end
                    uy = uy + math.max(th + px(2), px(24));
                end
                return (uy + px(10)) - by;
            end) + gap;
        end
    end

    -- send some
    if char then
        local home, gone, chosen = {}, {}, {};
        for _, m in ipairs(char.mates or {}) do
            if away[m.slot] then gone[#gone + 1] = m; else home[#home + 1] = m; end
        end
        local low = nil;
        for _, m in ipairs(home) do
            if V.picked[m.slot] then
                chosen[#chosen + 1] = m;
                low = math.min(low or 999, m.level or 1);
            end
        end
        for slot in pairs(V.picked) do                  -- (a mate that left meanwhile is no longer picked)
            if away[slot] then V.picked[slot] = nil; end
        end
        local camps = (st.hub and V.camps.hub) or V.camps.here;
        local fits = {};
        if low then
            local all = (st.hub and V.camps.hubList) or V.camps.hereList;
            for _, c in ipairs(all) do
                if c.lo <= low and low <= c.hi and (c.solo == true) == (low < partyFrom) then fits[#fits + 1] = c; end
            end
            if #fits == 0 then
                for _, c in ipairs(all) do
                    if c.lo - 3 <= low and low <= c.hi + 3 and #fits < 4 then fits[#fits + 1] = c; end
                end
            end
        end
        local campOk = false;
        for _, c in ipairs(fits) do campOk = campOk or c.id == V.campId; end
        if #fits > 0 and not campOk then V.campId = fits[1].id; end

        at = at + card(x, at, w, 'Send ' .. char.name .. '\'s squad', nil, function(bx, by, bw)
            local y2 = by;
            if #home > 0 then
                y2 = y2 + strip(bx, y2, bw, 'Who goes', 'one, or several together');
                local rowH = px(30);
                pane(bx, y2, bw, rowH * #home);
                for i, m in ipairs(home) do
                    local ry = y2 + (i - 1) * rowH;
                    local on = V.picked[m.slot] == true;
                    local clicked, hover = hit('mate' .. tostring(m.slot), bx, ry, bw, rowH);
                    if clicked then
                        V.picked[m.slot] = (not on) or nil;
                        sfx('select', 0.5);
                    end
                    if not gfx.dry then
                        if on or hover then gfx.rect(bx, ry, bx + bw, ry + rowH, gfx.col(on and TH.rowPressed or TH.rowHover), (i == 1 or i == #home) and 6 or 0); end
                        if i < #home then gfx.rect(bx, ry + rowH - 1, bx + bw, ry + rowH, gfx.col(TH.rowLine)); end
                        local s = px(16);
                        local tx, ty = bx + px(10), ry + (rowH - s) / 2;
                        gfx.rect(tx, ty, tx + s, ty + s, gfx.col(on and TH.onEdge or TH.dim), 4);
                        gfx.rect(tx + 1.5, ty + 1.5, tx + s - 1.5, ty + s - 1.5, on and gfx.col(TH.on) or gfx.col('#0E0918'), 3);
                        if on then                      -- a tick, drawn
                            local c = gfx.col(TH.onText);
                            for k = 0, px(3) do gfx.rect(tx + px(3.5) + k, ty + px(7.5) + k, tx + px(3.5) + k + 2, ty + px(7.5) + k + 2, c); end
                            for k = 0, px(6) do gfx.rect(tx + px(6.5) + k, ty + px(10.5) - k, tx + px(6.5) + k + 2, ty + px(10.5) - k + 2, c); end
                        end
                        local info = { RACE[m.race] or '?', (JOBS[m.job] or '?') .. tostring(m.level) };
                        local iw = dottedWidth(info, small());
                        gfx.text(tx + s + px(10), ry + (rowH - body()) / 2, gfx.col(TH.ink), gfx.fit(m.name, body(), bw - s - iw - px(40), true), body(), true);
                        dotted(bx + bw - px(10) - iw, ry + (rowH - small()) / 2, info, small(), TH.ink);
                    end
                end
                y2 = y2 + rowH * #home + px(8);
            else
                y2 = y2 + para(bx, y2, bw, { { #(char.mates or {}) > 0 and 'Everyone is out on a venture.' or 'No squad mates on this character yet.' } }, body());
            end
            if #gone > 0 and #home > 0 then
                local list = {};
                for _, m in ipairs(gone) do list[#list + 1] = m.name; end
                y2 = y2 + para(bx, y2, bw, { { 'Away: ' .. table.concat(list, ', '), TH.dim } }, small()) + px(8);
            end
            if #chosen > 0 then
                local solo = low < partyFrom;
                y2 = y2 + strip(bx, y2, bw, solo and 'Where' or 'Which camp', solo and ('solo hunting below level ' .. tostring(partyFrom)) or nil);
                -- the camps: a round box, the camp and where it is, its monsters under it
                local heights, total = {}, 0;
                local tw = bw - px(46);
                for i, c in ipairs(fits) do
                    local mobs = {};
                    for _, m in ipairs(c.mobs or {}) do mobs[#mobs + 1] = m.name; end
                    c._mobs = table.concat(mobs, ', ');
                    heights[i] = px(8) + flow({ { c.title, nil, true }, { string.format(' (%s, Lv %d-%d)', c.spot, c.lo, c.hi) } }, body(), tw).h
                        + flow({ { c._mobs, TH.dim } }, small(), tw, 2).h + px(8);
                    total = total + heights[i];
                end
                pane(bx, y2, bw, total);
                local ry = y2;
                for i, c in ipairs(fits) do
                    local on = V.campId == c.id;
                    local clicked, hover = hit('camp' .. c.id, bx, ry, bw, heights[i]);
                    if clicked then
                        V.campId = c.id;
                        sfx('select', 0.5);
                    end
                    if not gfx.dry then
                        if on or hover then gfx.rect(bx, ry, bx + bw, ry + heights[i], gfx.col(on and TH.rowPressed or TH.rowHover), (i == 1 or i == #fits) and 6 or 0); end
                        if i < #fits then gfx.rect(bx, ry + heights[i] - 1, bx + bw, ry + heights[i], gfx.col(TH.rowLine)); end
                        local s = px(16);
                        local tx, ty = bx + px(10), ry + (heights[i] - s) / 2;
                        gfx.rect(tx, ty, tx + s, ty + s, gfx.col(on and TH.onEdge or TH.dim), s / 2);
                        gfx.rect(tx + 1.5, ty + 1.5, tx + s - 1.5, ty + s - 1.5, on and gfx.col(TH.on) or gfx.col('#0E0918'), s / 2);
                        if on then gfx.rect(tx + s / 2 - px(3), ty + s / 2 - px(3), tx + s / 2 + px(3), ty + s / 2 + px(3), gfx.col(TH.onText), px(3)); end
                    end
                    local ty2 = ry + px(8);
                    ty2 = ty2 + para(bx + px(36), ty2, tw, { { c.title, nil, true }, { string.format(' (%s, Lv %d-%d)', c.spot, c.lo, c.hi) } }, body());
                    para(bx + px(36), ty2, tw, { { c._mobs, TH.dim } }, small(), 2);
                    ry = ry + heights[i];
                end
                y2 = y2 + total + px(8);
                local pick = V.campId and camps[V.campId];
                if pick then
                    local sh = scene(bx, y2, bw, nil, { camps = camps, anyCamp = V.camps.first,
                        events = { { t = 0, k = 'arrive', camp = pick.id }, { t = 999999, k = 'kill', c = pick.id, m = 0 } }, sec = 10, over = false,
                        mates = chosen, party = {}, label = pick.title .. ': ' .. pick.spot });
                    roundOff(bx, y2, bx + bw, y2 + sh, px(6), '#0E0918');
                    y2 = y2 + sh + px(4);
                end
                y2 = y2 + strip(bx, y2, bw, 'How long');
                local hours = st.hours or { 1, 2, 4, 8, 12 };
                local okHours = false;
                for _, h in ipairs(hours) do okHours = okHours or h == V.hours; end
                if not okHours then V.hours = hours[math.min(2, #hours)]; end
                local hw = (bw - px(6) * (#hours - 1)) / #hours;
                for i, h in ipairs(hours) do
                    if button('hours' .. tostring(h), tostring(h) .. ' h', bx + (i - 1) * (hw + px(6)), y2, hw, px(24), V.hours == h and 'on' or nil, px(12)) then
                        V.hours = h;
                        saveSettings();
                    end
                end
                y2 = y2 + px(24) + px(8);
                y2 = y2 + para(bx, y2, bw, { { 'About ' .. n((st.expPerHour or 3000) * V.hours) .. ' exp for ' .. (#chosen > 1 and 'each of them' or chosen[1].name) .. '.'
                    .. (#chosen > 1 and ' They go as one party.' or ''), TH.dim } }, small()) + px(8);
                local sending = busy('start');
                local can = pick ~= nil and not sending and launcherUp() and st.canSend ~= false;
                if button('send', sending and 'Sending...' or 'Send them off', bx, y2, bw, px(30), can and 'primary' or 'off', px(13)) then
                    local slots = {};
                    for _, m in ipairs(chosen) do slots[#slots + 1] = tostring(m.slot); end
                    local vid = newVentureId();
                    setNote('');
                    if not ask(string.format('%s|start|%s|%s|%s|%d', char.name, vid, table.concat(slots, ','), pick.id, V.hours), 'start', vid) then
                        setNote('The request could not be written (Ashita\'s config folder).');
                    end
                end
                y2 = y2 + px(30);
            end
            return y2 - by;
        end) + gap;
    end

    -- the album
    if #past > 0 then
        at = at + card(x, at, w, 'Past ventures', { pad = 0 }, function(bx, by, bw)
            local y2 = by;
            local rowH = px(10) + lineH(body()) + lineH(small()) + px(8);
            local show = math.min(#past, V.allPast and 20 or 3);
            for i = 1, show do
                local v = past[i];
                local camps = campsOf(v);
                local clicked, hover = hit('past' .. v.id, bx, y2, bw, rowH);
                if clicked then openReport(v); end
                if not gfx.dry then
                    if hover then gfx.rect(bx, y2, bx + bw, y2 + rowH, gfx.col(TH.rowHover)); end
                    gfx.rect(bx, y2 + rowH - 1, bx + bw, y2 + rowH, gfx.col(TH.rowLine));
                    local room = bw - px(40);
                    local title = (camps[v.camp] or {}).title or tostring(v.camp);
                    local tw = math.min(gfx.width(title, body(), true), room * 0.6);
                    title = gfx.fit(title, body(), tw + 1, true);
                    gfx.text(bx + px(10), y2 + px(9), gfx.col(TH.ink), title, body(), true);
                    local d = math.max(2, math.floor(body() / 6));
                    local nx = bx + px(10) + gfx.width(title, body(), true) + px(5);
                    gfx.rect(nx, y2 + px(9) + body() * 0.55 - d / 2, nx + d, y2 + px(9) + body() * 0.55 + d / 2, gfx.col(TH.ink));
                    gfx.text(nx + d + px(5), y2 + px(9), gfx.col(TH.ink), gfx.fit(names(v.mates), body(), room - (nx + d + px(5) - bx), true), body(), true);
                    local info = { os.date('%b %d', v['end'] - (v.skew or 0)), tostring(v.hours) .. 'h' .. (v.recalled and ' (called home early)' or ''),
                        '+' .. n(((v.results or {}).exp or {})[1] or 0) .. ' exp' };
                    dotted(bx + px(10), y2 + px(9) + lineH(body()), info, small(), TH.dim);
                    gfx.text(bx + bw - px(18), y2 + (rowH - body()) / 2, gfx.col(TH.link), '>', body(), true);
                end
                y2 = y2 + rowH;
            end
            if #past > 3 and not V.allPast then
                local clicked, hover = hit('pastall', bx, y2, bw, px(30));
                if clicked then V.allPast = true; end
                if not gfx.dry then
                    if hover then gfx.rect(bx, y2, bx + bw, y2 + px(30), gfx.col(TH.rowHover)); end
                    gfx.text(bx + px(10), y2 + (px(30) - body()) / 2, gfx.col(TH.link), 'Show all ' .. tostring(math.min(20, #past)), body(), true);
                end
                y2 = y2 + px(30);
            end
            return y2 - by;
        end) + gap;
    end

    if #mine > 0 then
        at = at + card(x, at, w, '', nil, function(bx, by, bw)
            local label = 'How Ventures work';
            local lw = gfx.width(label, body(), true);
            local clicked = hit('how', bx, by, lw + px(20), lineH(body()));
            if clicked then V.how = not V.how; end
            if not gfx.dry then
                gfx.text(bx, by, gfx.col(TH.link), label, body(), true);
                local tx, ty, s = bx + lw + px(7), by + body() * 0.5, px(4);
                local drawn;
                if V.how then drawn = gfx.triangle(tx, ty + s * 0.6, tx + 2 * s, ty + s * 0.6, tx + s, ty - s * 0.6, gfx.col(TH.link));
                else drawn = gfx.triangle(tx, ty - s * 0.6, tx + 2 * s, ty - s * 0.6, tx + s, ty + s * 0.6, gfx.col(TH.link)); end
                if not drawn then gfx.text(tx, by, gfx.col(TH.link), V.how and '^' or 'v', body(), true); end
            end
            local h = lineH(body());
            if V.how then
                h = h + px(8) + para(bx, by + h + px(8), bw, intro, body());
                local more = st.paired and 'Ventures you send here show in the XIFO app too, and the app\'s show here.'
                    or 'This works with no internet and no app. Pair the XIFO app in the launcher and the same ventures show on your phone.';
                h = h + px(6) + para(bx, by + h + px(6), bw, { { more, TH.dim } }, small());
            end
            return h;
        end) + gap;
    end

    -- sound and size (the app keeps these in its Settings)
    do
        local size = px(11);
        local bx = x + px(2);
        local function chip(id, label)
            local bw = gfx.width(label:upper(), size) + px(14);
            local clicked = button(id, label, bx, at, bw, px(22), nil, size);
            bx = bx + bw + px(6);
            return clicked;
        end
        if chip('snd', 'Sound: ' .. (V.cfg.sound and 'on' or 'off')) then
            V.cfg.sound = not V.cfg.sound;
            saveSettings();
            sfx('select', 0.5);
        end
        if chip('mus', 'Tune: ' .. (V.cfg.music and 'on' or 'off')) then
            V.cfg.music = not V.cfg.music;
            saveSettings();
        end
        if chip('smaller', 'Smaller') then V.resize = -1; end
        if chip('bigger', 'Bigger') then V.resize = 1; end
        at = at + px(22) + px(4);
    end
    return at - y;
end

-----------------------------------------------------------------------
-- the window
-----------------------------------------------------------------------
local SCROLL = 14;      -- ImGui's scrollbar
local PAD = 8;

local function widthFor(size) return 240 * size + 2 + 2 * PAD + SCROLL + 14; end     -- (room for a wider scrollbar than usual)

local function sizeNear(size, step)
    local at = 1;
    for i, s in ipairs(SIZES) do
        if math.abs(s - size) < math.abs(SIZES[at] - size) then at = i; end
    end
    return SIZES[math.max(1, math.min(#SIZES, at + (step or 0)))];
end

local STYLE = {
    { 'ImGuiCol_WindowBg', TH.back }, { 'ImGuiCol_Border', TH.paneEdge }, { 'ImGuiCol_Text', TH.title },
    { 'ImGuiCol_TitleBg', '#120A1C' }, { 'ImGuiCol_TitleBgActive', '#1A0F28' }, { 'ImGuiCol_TitleBgCollapsed', '#120A1C' },
    { 'ImGuiCol_ScrollbarBg', 'rgba(5,3,10,0.6)' }, { 'ImGuiCol_ScrollbarGrab', '#3A2350' }, { 'ImGuiCol_ScrollbarGrabHovered', '#5A4626' },
    { 'ImGuiCol_ScrollbarGrabActive', '#8A6A2E' }, { 'ImGuiCol_ResizeGrip', 'rgba(138,106,46,0.35)' },
    { 'ImGuiCol_ResizeGripHovered', '#8A6A2E' }, { 'ImGuiCol_ResizeGripActive', '#E8C878' },
};

local function render()
    if not V.open[1] then
        music(false);
        return;
    end
    music(V.cfg.music);
    local cond = G('ImGuiCond_FirstUseEver') or 4;
    local w = widthFor(V.cfg.size);
    if V.resize then
        V.cfg.size = sizeNear(V.cfg.size, V.resize);
        V.resize = nil;
        saveSettings();
        w = widthFor(V.cfg.size);
        cond = G('ImGuiCond_Always') or 1;
    end
    imgui.SetNextWindowSize({ w, 640 }, cond);
    if has('SetNextWindowSizeConstraints') then imgui.SetNextWindowSizeConstraints({ widthFor(1.5), 260 }, { widthFor(4) + 40, 4000 }); end
    local colours, vars = 0, 0;
    for _, item in ipairs(STYLE) do
        local id = G(item[1]);
        if id ~= nil and pcall(imgui.PushStyleColor, id, gfx.parse(item[2])) then colours = colours + 1; end
    end
    if has('PushStyleVar') and G('ImGuiStyleVar_WindowPadding') ~= nil and pcall(imgui.PushStyleVar, G('ImGuiStyleVar_WindowPadding'), { PAD, PAD }) then vars = 1; end
    local flags = (G('ImGuiWindowFlags_AlwaysVerticalScrollbar') or 16384) + (G('ImGuiWindowFlags_NoCollapse') or 32);
    local shown = imgui.Begin('Ventures###xifo_venture', V.open, flags);
    local ok, err = pcall(function()
        if not shown then return; end
        gfx.sweep();
        gfx.begin(os.clock());
        U.k = math.max(0.8, math.min(2.5, gfx.base() / 13));
        local ax = gfx.pair(imgui.GetContentRegionAvail());
        local x0, y0 = gfx.pair(imgui.GetCursorScreenPos());
        -- the scene is drawn at one of the sizes that keep its pixels even; the sections are as wide as it
        local P = SIZES[1];
        for _, s in ipairs(SIZES) do
            if 240 * s + 2 <= ax + 0.5 then P = s; end
        end
        local cw = 240 * P + 2;
        local x = math.floor(x0 + math.max(0, (ax - cw) / 2));
        local function lay()
            U.ids = 0;
            local v = V.report and V.state and (function()
                for _, it in ipairs(V.state.ventures or {}) do
                    if it.id == V.report then return it; end
                end
            end)() or nil;
            if V.report and not v then V.report = nil; end
            if v then return report(x, y0, cw, v); end
            return screen(x, y0, cw);
        end
        gfx.dry = true;
        U.heights = {};
        lay();
        gfx.dry = false;
        local total = lay();
        imgui.SetCursorScreenPos({ x0, y0 });
        imgui.Dummy({ math.max(1, ax), math.max(1, total) });
    end);
    gfx.dry = false;
    pcall(gfx.finish);
    imgui.End();
    if vars > 0 then pcall(imgui.PopStyleVar, vars); end
    if colours > 0 then pcall(imgui.PopStyleColor, colours); end
    if not ok and V.lastError ~= err then
        V.lastError = err;
        say('the window ran into a problem: ' .. tostring(err));
    end
end

-----------------------------------------------------------------------
-- the Squads menu (servermenu 1.36): its Ventures button loads this add-on, shows the window and shuts it again.
-- So that the menu knows what is so without asking, two small files are kept in the character's folder, the one the
-- menu and Gambits share (config\addons\xiforever\<Name>_<ServerId>\), the way Gambits keeps gambits.loaded and
-- gambits.open:
--   venture.loaded   while this add-on is loaded for that character
--   venture.open     while its window is shown
-- Each holds the game process's id, so a file a crashed game left behind is not taken for this one's. Whenever one
-- of them changes the line "/xifoventure" is said: the menu reads the files again on that line (and every second or
-- two anyway). The line carries nothing, is never typed and never reaches the game: this add-on stops it itself, so
-- it is harmless with an older menu or with none.
-----------------------------------------------------------------------
local SIGNAL = '/xifoventure';

local function processId()
    if V.pid == nil then
        V.pid = false;
        pcall(ffi.cdef, 'unsigned long GetCurrentProcessId(void);');
        local ok, value = pcall(function() return tonumber(ffi.C.GetCurrentProcessId()); end);
        if ok and value and value > 0 then V.pid = value; end
    end
    return V.pid or nil;
end

-- <Name>_<ServerId>: how the menu and Gambits name a character's folder (xifo_ui.lua, U.identity). nil: nobody is logged in
local function identity()
    local ok, name, id = pcall(function()
        local party = AshitaCore:GetMemoryManager():GetParty();
        return party:GetMemberName(0), party:GetMemberServerId(0);
    end);
    if not ok then return nil; end
    name = tostring(name or ''):gsub('%z', ''):match('^%s*(.-)%s*$') or '';
    id = tonumber(id) or 0;
    if name == '' or id <= 0 then return nil; end
    return (name:gsub('[^%w_]', '_')) .. '_' .. string.format('%d', id);
end

-- that character's folder, and the folder it is in
local function markDir(id)
    if id == nil then return nil; end
    local ok, base = pcall(function() return AshitaCore:GetInstallPath(); end);
    if not ok or type(base) ~= 'string' or base == '' then return nil; end
    if not base:match('[\\/]$') then base = base .. '\\'; end
    return base .. 'config\\addons\\xiforever\\' .. id .. '\\', base .. 'config\\addons\\xiforever\\';
end

local function markText()
    local pid = processId();
    return 'Ventures ' .. tostring(addon.version) .. '\n' .. (pid and ('pid=' .. string.format('%d', pid) .. '\n') or '');
end

local function signal()
    pcall(function() AshitaCore:GetChatManager():QueueCommand(1, SIGNAL); end);
end

-- The character this add-on is loaded for. Another character logged in: the files move to that one's folder.
-- nil (the add-on is being unloaded): they are removed, and nothing is said (nobody here could stop the line then).
local function presence(id)
    if id == V.markId then return; end
    local old = markDir(V.markId);
    if old then
        os.remove(old .. 'venture.loaded');
        os.remove(old .. 'venture.open');
    end
    V.markId, V.openSaid = id, false;
    local dir, parent = markDir(id);
    if not dir then return; end
    makeDir(parent);
    makeDir(dir);
    os.remove(dir .. 'venture.open');      -- (one a crashed game left: the window's real state follows in this frame)
    local f = io.open(dir .. 'venture.loaded', 'w');
    if f then
        f:write(markText());
        f:close();
    end
    signal();
end

-- the window was shown or shut, however that happened (the menu's button, /venture, its own X): told once per change
local function announceOpen()
    local shown = V.open[1] == true;
    if shown == V.openSaid or V.markId == nil then return; end
    V.openSaid = shown;
    local dir = markDir(V.markId);
    if dir then
        if shown then
            local f = io.open(dir .. 'venture.open', 'w');
            if f then
                f:write(markText());
                f:close();
            end
        else
            os.remove(dir .. 'venture.open');
        end
    end
    signal();
end

-----------------------------------------------------------------------
-- events
-----------------------------------------------------------------------
ashita.events.register('load', 'venture_load', function()
    math.randomseed(os.time() + math.floor(os.clock() * 1000) + (tonumber(tostring({}):match('0x(%x+)') or '0', 16) or 0) % 100000);
    loadSettings();
    -- loaded by the menu's button, the character is in the game already: the menu hears of it now, not a second later
    local id = identity();
    if id then presence(id); end
end);

ashita.events.register('unload', 'venture_unload', function()
    music(false);
    gfx.release();
    presence(nil);
end);

ashita.events.register('command', 'venture_command', function(e)
    local args = e.command:args();
    if #args == 0 then return; end
    local cmd = args[1]:lower();
    if cmd == SIGNAL then      -- this add-on's own line to the Squads menu: never sent to the game
        e.blocked = true;
        return;
    end
    if cmd ~= '/venture' and cmd ~= '/ventures' then return; end
    e.blocked = true;
    local sub = (args[2] or ''):lower();
    if sub == '' or sub == 'toggle' then
        V.open[1] = not V.open[1];
    elseif sub == 'show' or sub == 'open' then       -- (1.1) what the Squads menu's Ventures button sends
        V.open[1] = true;
    elseif sub == 'hide' or sub == 'close' then
        V.open[1] = false;
    elseif sub == 'size' then
        local v = tonumber(args[3] or '');
        if v then
            V.cfg.size = sizeNear(v, 0);
            V.resize = 0;
            V.open[1] = true;
        end
        say('size ' .. tostring(V.cfg.size) .. ' (/venture size 1.5, 2, 2.5, 3 or 4)');
    elseif sub == 'sound' then
        V.cfg.sound = not V.cfg.sound;
        saveSettings();
        say('sounds ' .. (V.cfg.sound and 'on' or 'off'));
    elseif sub == 'music' or sub == 'tune' then
        V.cfg.music = not V.cfg.music;
        saveSettings();
        say('the Ventures tune is ' .. (V.cfg.music and 'on (while the window is open)' or 'off'));
    elseif sub == 'volume' then
        local v = tonumber(args[3] or '');
        if v then
            V.cfg.volume = math.max(0, math.min(100, math.floor(v)));
            saveSettings();
            if musicOpen then pcall(function() winmm.mciSendStringA('setaudio venture_music volume to ' .. tostring(V.cfg.volume * 10), nil, 0, nil); end); end
        end
        say('volume ' .. tostring(V.cfg.volume) .. ' (/venture volume 0-100)');
    else
        say('/venture (the window; also /venture show, /venture hide), /venture size <1.5-4>, /venture sound, /venture music, /venture volume <0-100>');
    end
end);

ashita.events.register('d3d_present', 'venture_present', function()
    -- who is playing: the window opens on that character's squad (until you pick another)
    local name = myName();
    if name and name ~= V.me then
        V.me = name;
        if not V.whoPicked then V.who = name; end
    end
    -- (1.1) for the Squads menu: whose folder the two small files are in, looked at once a second. A moment without a
    -- character (a zone loading, the title screen) changes nothing: the files stay where they are until someone else
    -- is logged in, or the add-on is unloaded.
    local tick = os.clock();
    if tick - (V.markAt or -10) >= 1 then
        V.markAt = tick;
        local id = identity();
        if id then presence(id); end
        -- venture.loaded is this add-on's word to the menu. Should it ever be gone while the add-on is loaded (someone
        -- tidied the folder, or the menu took it for a file an earlier game left), it is put back, and said again.
        local dir = markDir(V.markId);
        local f = dir and io.open(dir .. 'venture.loaded', 'r');
        if f then
            f:close();
        elseif dir then
            local mine = V.markId;
            V.markId = nil;
            presence(mine);
        end
    end
    if V.open[1] then
        pcall(readState);
        keepFresh(V.who or V.me);
        for id, p in pairs(V.pending) do
            if os.clock() - p.at > 15 then
                V.pending[id] = nil;
                if p.what ~= 'seen' then setNote('The launcher did not answer. Is it still open?'); end
            end
        end
        if V.note ~= '' and now() - V.noteAt > 20 then V.note = ''; end
        render();
    elseif musicOpen then
        music(false);
    end
    announceOpen();      -- (after the frame: the window's own X shuts it while it is drawn)
end);

-- (for the tests: the parts they look into)
return { V = V, gfx = gfx, Stage = Stage, screen = screen, render = render, readState = readState, flow = flow, n = n, clockText = clockText,
         names = names, lineOf = lineOf, identity = identity, SIGNAL = SIGNAL };
