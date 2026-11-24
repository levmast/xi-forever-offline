--[[
hcicons 1.4  (XI: Forever Offline, 2026-11-23)
Shows the mode's icon beside the name of every Iron, Steel, Silver and Randomized character near you, where the
game's own bazaar and seeking-party icons sit, always on (the shields in this add-on's icons folder: iron.png,
steel.png, silver.png, random.png). The one you target gets a frame in its mode's colour; Random's shield slowly
shifts colour; past 35 yalms they fade out. "/hcicons style float" shows bigger glowing icons over the heads instead.
Without the pictures it falls back to a text badge.
The launcher keeps it loaded at every PLAY (the icons are part of the game modes, like the server's rules).

How it knows: when you arrive in an area it asks the server (the command !hcicons, which only this add-on sends), and the
server answers with one hidden line naming the hardcore characters there ("[HC-ICONS] Name=1,Other=3"). When a hardcore
character arrives later, the server sends another. Those lines are never shown in the chat log.

  /hcicons            on / off (for this session)
  /hcicons list       the hardcore characters this add-on knows about here
  /hcicons style plate | float    beside the name (default) or floating over the head
  /hcicons size N     the name-plate icon's size in px (default 18)
  /hcicons nudge N    move the name-plate icon up (negative) or down in px, to line it up with the name
  /hcicons height N   how far above the feet the name sits, in yalms (default 2.4; negative if it shows at the feet)

Party list (1.4): a small column of icons, one row per party member, that you put beside your party list (the game's
own or XIUI's; they sit in different places, so you place it once). It only shows when someone in the party has a mode.
  /hcicons party        on / off
  /hcicons party move   the column follows the mouse; click where it goes (it is kept)
  /hcicons party row N  the height of one party row in px (default 20), to match your party list
  /hcicons party size N the icons' size in px (default 16)
  /hcicons party flip   you at the bottom instead of the top (or back)

Nothing is sent anywhere but your own world's server.
]]

addon.name    = 'hcicons';
addon.author  = 'XI: Forever Offline';
addon.version = '1.4';
addon.desc    = 'Icons over the heads of Iron, Steel, Silver and Randomized characters.';
addon.link    = 'https://xiforever.com';

require('common');
local ffi = require('ffi');

local imgui, d3d8;
do
    local ok, mod = pcall(require, 'imgui');
    if ok then imgui = mod; end
    ok, mod = pcall(require, 'd3d8');
    if ok then d3d8 = mod; end
end

local MARK = '[HC-ICONS]';
local MODES = {
    [1] = { text = 'IRON',   fill = { 0.42, 0.44, 0.50, 0.92 }, edge = { 0.86, 0.88, 0.92, 1.0 } },
    [2] = { text = 'STEEL',  fill = { 0.16, 0.30, 0.52, 0.92 }, edge = { 0.60, 0.76, 0.96, 1.0 } },
    [3] = { text = 'SILVER', fill = { 0.46, 0.06, 0.08, 0.92 }, edge = { 0.94, 0.94, 0.98, 1.0 } },
    [4] = { text = 'RANDOM', fill = { 0.30, 0.16, 0.56, 0.92 }, edge = { 0.86, 0.76, 1.00, 1.0 } },
};
local FILES = { [1] = 'iron', [2] = 'steel', [3] = 'silver', [4] = 'random' };
local ICON_SIZE = 34;

local S = { on = true, known = {}, ask_at = 0, height = 2.4, warned = false, range = 45,
            style = 'plate',      -- 'plate': a small icon right beside the name, where the bazaar / seek-party icons sit
                                  -- 'float': a bigger glowing icon over the head
            plate = 18,           -- the icon's size in plate style (px)
            charw = 7.0,          -- about how wide one letter of the name plate is (px), to find the name's left edge
            plate_dy = 0,         -- move the plate icon up (-) or down (+) in px
            party = 1, party_x = -1, party_y = -1, party_row = 20, party_size = 16, party_up = 0,
            party_moving = false };

local function mem() return AshitaCore:GetMemoryManager(); end

-- your placement (style, size, nudge, height) is kept in config/addons/hcicons/settings.txt
local KEEP = { 'style', 'plate', 'plate_dy', 'height', 'charw', 'party', 'party_x', 'party_y', 'party_row', 'party_size', 'party_up' };
local function settings_path()
    return AshitaCore:GetInstallPath() .. '\\config\\addons\\hcicons\\settings.txt';
end
local function load_settings()
    pcall(function()
        local handle = io.open(settings_path(), 'r');
        if handle == nil then return; end
        for line in handle:lines() do
            local k, v = line:match('^(%w+)=(.+)$');
            for _, key in ipairs(KEEP) do
                if k == key then S[key] = tonumber(v) or v; end
            end
        end
        handle:close();
    end);
end
local function save_settings()
    pcall(function()
        ashita.fs.create_directory(AshitaCore:GetInstallPath() .. '\\config\\addons\\hcicons');
        local handle = io.open(settings_path(), 'w');
        if handle == nil then return; end
        for _, key in ipairs(KEEP) do handle:write(key .. '=' .. tostring(S[key]) .. '\n'); end
        handle:close();
    end);
end

local function say(text)
    print('\31\200[hcicons]\31\130 ' .. text);
end

local function ask_soon(seconds)
    S.ask_at = os.clock() + (seconds or 4);
end

-----------------------------------------------------------------------
-- the server's hidden lines
-----------------------------------------------------------------------
local function read_line(text)
    local start = text:find(MARK, 1, true);
    if not start then return false; end
    local body = text:sub(start + #MARK):gsub('^%s+', '');
    local reset = body:sub(1, 1) == '!';            -- "!..." = the whole list for this area
    if reset then
        S.known = {};
        body = body:sub(2);
    end
    for name, mode in body:gmatch('([A-Za-z]+)=(%d)') do
        mode = tonumber(mode);
        S.known[name:lower()] = (mode and mode >= 1 and mode <= 4) and mode or nil;
    end
    return true;
end

ashita.events.register('text_in', 'hcicons_text_in', function(e)
    local text = e.message_modified or e.message or '';
    if text:find(MARK, 1, true) then
        pcall(read_line, text);
        e.blocked = true;
    end
end);

ashita.events.register('packet_in', 'hcicons_packet_in', function(e)
    if e.id == 0x00A then                           -- arrived in an area: ask what hardcore characters are here
        S.known = {};
        ask_soon(5);
    end
end);

ashita.events.register('load', 'hcicons_load', function()
    load_settings();
    ask_soon(3);
end);

-----------------------------------------------------------------------
-- where a point of the world is on the screen
-----------------------------------------------------------------------
local device;
local function get_device()
    if device == nil and d3d8 ~= nil and type(d3d8.get_device) == 'function' then
        local ok, value = pcall(d3d8.get_device);
        if ok then device = value; end
    end
    return device;
end

local function pick(a, b)                           -- (hr, value) or (value) from a d3d8 call
    if type(a) == 'number' and b ~= nil then return b; end
    return a;
end

local function project(x, y, z)
    local dev = get_device();
    if dev == nil then return nil; end
    local view = pick(dev:GetTransform(ffi.C.D3DTS_VIEW));
    local proj = pick(dev:GetTransform(ffi.C.D3DTS_PROJECTION));
    local vp = pick(dev:GetViewport());
    if view == nil or proj == nil or vp == nil then return nil; end
    -- world -> view
    local vx = x * view._11 + y * view._21 + z * view._31 + view._41;
    local vy = x * view._12 + y * view._22 + z * view._32 + view._42;
    local vz = x * view._13 + y * view._23 + z * view._33 + view._43;
    -- view -> clip
    local cx = vx * proj._11 + vy * proj._21 + vz * proj._31 + proj._41;
    local cy = vx * proj._12 + vy * proj._22 + vz * proj._32 + proj._42;
    local cw = vx * proj._14 + vy * proj._24 + vz * proj._34 + proj._44;
    if cw <= 0.1 then return nil; end               -- behind the camera
    local sx = vp.X + (cx / cw + 1) * 0.5 * vp.Width;
    local sy = vp.Y + (1 - cy / cw) * 0.5 * vp.Height;
    return sx, sy;
end

-----------------------------------------------------------------------
-- the icons (pictures in the icons folder, loaded once)
-----------------------------------------------------------------------
local textures, tried = {}, {};

local function texture(mode)
    if textures[mode] ~= nil or tried[mode] then return textures[mode]; end
    tried[mode] = true;
    local ok, value = pcall(function()
        local path = string.format('%s\\icons\\%s.png', addon.path, FILES[mode]);
        local handle = io.open(path, 'rb');
        if handle == nil then return nil; end
        local data = handle:read('*a');
        handle:close();
        local dev = get_device() or AshitaCore:GetDirect3DDevice();
        if dev == nil or data == nil or #data == 0 then return nil; end
        local raw = ffi.new('IDirect3DTexture8*[1]');
        local result = ffi.C.D3DXCreateTextureFromFileInMemoryEx(ffi.cast('IDirect3DDevice8*', dev), data, #data,
            0xFFFFFFFF, 0xFFFFFFFF, 1, 0, ffi.C.D3DFMT_A8R8G8B8, ffi.C.D3DPOOL_MANAGED,
            ffi.C.D3DX_DEFAULT, ffi.C.D3DX_DEFAULT, 0x00000000, nil, nil, raw);
        if result ~= 0 or raw[0] == nil then return nil; end
        local image = d3d8.gc_safe_release(ffi.cast('IDirect3DTexture8*', raw[0]));
        return { image = image, ptr = tonumber(ffi.cast('uint32_t', image)) };
    end);
    textures[mode] = ok and value or nil;
    return textures[mode];
end

-----------------------------------------------------------------------
-- drawing
-----------------------------------------------------------------------
local function colour(c)
    return imgui.GetColorU32(c);
end

-- Random's icon slowly shifts colour, the way its die would roll
local function random_tint()
    local t = os.clock() * 0.8;
    return { 0.80 + 0.20 * math.sin(t), 0.80 + 0.20 * math.sin(t + 2.1), 0.80 + 0.20 * math.sin(t + 4.2), 1.0 };
end

-- the icon: a soft glow in the mode's colour, a shadow, the shield, a slow float. Closer = bigger; far away it fades.
local GLOW = { [1] = { 0.80, 0.82, 0.88 }, [2] = { 0.45, 0.70, 1.00 }, [3] = { 1.00, 0.30, 0.32 }, [4] = { 0.85, 0.60, 1.00 } };

local function icon(list, x, y, mode, size, alpha, targeted)
    local tex = texture(mode);
    if tex == nil then return false; end
    local bob = math.sin(os.clock() * 2.0 + x * 0.01) * 2;
    local half = size / 2;
    local top = y - size + bob;
    local g = GLOW[mode];
    local glow = (targeted and 0.55 or 0.30) * alpha;
    list:AddCircleFilled({ x, top + half }, half * (targeted and 1.15 or 0.95), colour({ g[1], g[2], g[3], glow * 0.5 }), 24);
    list:AddCircleFilled({ x, top + half }, half * 0.70, colour({ g[1], g[2], g[3], glow }), 24);
    list:AddImage(tex.ptr, { x - half + 2, top + 3 }, { x + half + 2, top + size + 3 }, { 0, 0 }, { 1, 1 }, colour({ 0, 0, 0, 0.55 * alpha }));
    local tint = mode == 4 and random_tint() or { 1, 1, 1, 1 };
    tint[4] = alpha;
    list:AddImage(tex.ptr, { x - half, top }, { x + half, top + size }, { 0, 0 }, { 1, 1 }, colour(tint));
    if targeted then                                 -- the one you target: its mode's name under the icon
        local text = MODES[mode].text;
        local tw = imgui.CalcTextSize(text);
        list:AddText({ x - tw / 2 + 1, top + size + 3 }, colour({ 0, 0, 0, 0.8 * alpha }), text);
        list:AddText({ x - tw / 2, top + size + 2 }, colour({ g[1], g[2], g[3], alpha }), text);
    end
    return true;
end

local function badge(list, x, y, mode)
    local m = MODES[mode];
    local tw = imgui.CalcTextSize(m.text);
    local w, h = tw + 12, 18;
    local x1, y1 = x - w / 2, y - h;
    list:AddRectFilled({ x1, y1 }, { x1 + w, y1 + h }, colour(m.fill), 3);
    list:AddRect({ x1, y1 }, { x1 + w, y1 + h }, colour(m.edge), 3, 0, 1.5);
    list:AddText({ x1 + 6, y1 + 2 }, colour({ 1, 1, 1, 1 }), m.text);
end

-- plate style: like the game's own name-plate icons (bazaar, seeking party): small, steady, just left of the name
local function plate_icon(list, x, y, mode, alpha, name, targeted)
    local tex = texture(mode);
    if tex == nil then return false; end
    local size = S.plate;
    local nameHalf = #name * S.charw / 2;
    local x2 = x - nameHalf - 3;                     -- right edge of the icon, a little left of the name
    local top = y - size / 2 + S.plate_dy;
    list:AddImage(tex.ptr, { x2 - size + 1, top + 1 }, { x2 + 1, top + size + 1 }, { 0, 0 }, { 1, 1 }, colour({ 0, 0, 0, 0.6 * alpha }));
    local tint = mode == 4 and random_tint() or { 1, 1, 1, 1 };
    tint[4] = alpha;
    list:AddImage(tex.ptr, { x2 - size, top }, { x2, top + size }, { 0, 0 }, { 1, 1 }, colour(tint));
    if targeted then
        local g = GLOW[mode];
        list:AddRect({ x2 - size - 2, top - 2 }, { x2 + 2, top + size + 2 }, colour({ g[1], g[2], g[3], 0.9 * alpha }), 3, 0, 1.5);
    end
    return true;
end

local function my_index()
    local ok, index = pcall(function() return mem():GetParty():GetMemberTargetIndex(0); end);
    return ok and index or nil;
end

local function target_index()
    local ok, index = pcall(function()
        local tgt = mem():GetTarget();
        return tgt:GetIsSubTargetActive() == 1 and tgt:GetTargetIndex(1) or tgt:GetTargetIndex(0);
    end);
    return ok and index or nil;
end

-----------------------------------------------------------------------
-- party list column (1.4)
-----------------------------------------------------------------------
local function party_rows()
    local rows, any = {}, false;
    local party = mem():GetParty();
    for i = 0, 5 do
        if party:GetMemberIsActive(i) == 1 then
            local name = party:GetMemberName(i) or '';
            local mode = S.known[name:lower()] or 0;
            if mode > 0 then any = true; end
            rows[#rows + 1] = mode;
        end
    end
    return rows, any;
end

local function screen_size()
    local ok, w, h = pcall(function()
        local io = imgui.GetIO();
        return io.DisplaySize.x, io.DisplaySize.y;
    end);
    if ok and w and h and w > 0 then return w, h; end
    return 1280, 720;
end

local function draw_party(list)
    if S.party == 0 then return; end
    local rows, any = party_rows();
    if not any and not S.party_moving then return; end
    if #rows == 0 then rows = { 0 }; end
    local W, H = screen_size();
    local row, size = S.party_row, S.party_size;
    local x, y = S.party_x, S.party_y;
    if S.party_moving then
        local mx, my = 0, 0;
        pcall(function()
            local pos = imgui.GetMousePos();
            if type(pos) == 'table' then mx, my = pos[1] or pos.x, pos[2] or pos.y; else mx, my = imgui.GetMousePos(); end
        end);
        x, y = mx - size / 2, my - row / 2;
        if imgui.IsMouseClicked(0) then
            S.party_x, S.party_y, S.party_moving = math.floor(x), math.floor(y), false;
            save_settings();
            say('The party column stays here. /hcicons party row N lines the rows up with your party list.');
        end
    end
    if x < 0 or y < 0 then                           -- not placed yet: beside the right edge, above the chat corner
        x = W - 200;
        y = H - 60 - #rows * row;
    end
    for n = 1, #rows do
        local mode = rows[S.party_up == 1 and (#rows - n + 1) or n];
        local top = y + (n - 1) * row + (row - size) / 2;
        if mode > 0 then
            local tex = texture(mode);
            if tex ~= nil then
                local tint = mode == 4 and random_tint() or { 1, 1, 1, 1 };
                list:AddImage(tex.ptr, { x + 1, top + 1 }, { x + size + 1, top + size + 1 }, { 0, 0 }, { 1, 1 }, colour({ 0, 0, 0, 0.6 }));
                list:AddImage(tex.ptr, { x, top }, { x + size, top + size }, { 0, 0 }, { 1, 1 }, colour(tint));
            else
                list:AddText({ x, top }, colour(MODES[mode].edge), MODES[mode].text:sub(1, 2));
            end
        end
        if S.party_moving then
            list:AddRect({ x - 2, y + (n - 1) * row }, { x + size + 2, y + n * row }, colour({ 1, 1, 1, 0.6 }), 2, 0, 1);
        end
    end
    if S.party_moving then
        list:AddText({ x + size + 6, y }, colour({ 1, 1, 1, 1 }), 'click to place');
    end
end

ashita.events.register('d3d_present', 'hcicons_present', function()
    if S.ask_at > 0 and os.clock() >= S.ask_at then
        S.ask_at = 0;
        AshitaCore:GetChatManager():QueueCommand(1, '!hcicons');
    end
    if not S.on or imgui == nil or (next(S.known) == nil and not S.party_moving) then return; end
    local ok, problem = pcall(function()
        local ent = mem():GetEntity();
        local list = imgui.GetForegroundDrawList and imgui.GetForegroundDrawList() or imgui.GetBackgroundDrawList();
        local partyOk, partyProblem = pcall(draw_party, list);
        if not partyOk and not S.party_warned then
            S.party_warned = true;
            say('Could not draw the party column (' .. tostring(partyProblem) .. ').');
        end
        local me = my_index();
        local mx, my = 0, 0;
        if me then mx, my = ent:GetLocalPositionX(me), ent:GetLocalPositionY(me); end
        local target = target_index();
        for index = 0x400, 0x6FF do
            local name = ent:GetName(index);
            if name ~= nil and name ~= '' then
                local mode = S.known[name:lower()];
                if mode ~= nil and ent:GetRenderFlags0(index) ~= 0 then
                    -- FFXI's world: x, height (negative is up), y
                    local x = ent:GetLocalPositionX(index);
                    local y = ent:GetLocalPositionY(index);
                    local z = ent:GetLocalPositionZ(index);
                    local dist = math.sqrt((x - mx) ^ 2 + (y - my) ^ 2);
                    if dist <= S.range then
                        local size = math.floor(44 - math.min(dist, 30) * 0.7);           -- 44 px close, 23 px at 30 yalms
                        local alpha = dist <= S.range - 10 and 1.0 or math.max(0.15, (S.range - dist) / 10);
                        local sx, sy = project(x, z - S.height, y);
                        if sx ~= nil then
                            local drawn = false;
                            local done, result;
                            if S.style == 'plate' then
                                done, result = pcall(plate_icon, list, sx, sy, mode, alpha, name, index == target);
                            else
                                done, result = pcall(icon, list, sx, sy, mode, size, alpha, index == target);
                            end
                            drawn = done and result;
                            if not drawn then badge(list, sx, sy, mode); end
                        end
                    end
                end
            end
        end
    end);
    if not ok and not S.warned then
        S.warned = true;
        say('Could not draw the icons here (' .. tostring(problem) .. '). /hcicons list still shows who is hardcore.');
    end
end);

ashita.events.register('command', 'hcicons_command', function(e)
    local args = e.command:args();
    if #args == 0 or args[1]:lower() ~= '/hcicons' then return; end
    e.blocked = true;
    local what = (args[2] or ''):lower();
    if what == 'list' then
        local names = {};
        for name, mode in pairs(S.known) do names[#names + 1] = name .. ' (' .. MODES[mode].text .. ')'; end
        say(#names > 0 and table.concat(names, ', ') or 'No hardcore characters here.');
    elseif what == 'style' and (args[3] == 'plate' or args[3] == 'float') then
        S.style = args[3];
        say(S.style == 'plate' and 'Icons sit beside the name, like the bazaar icon.' or 'Icons float over the head.');
        save_settings();
    elseif what == 'size' and tonumber(args[3]) then
        S.plate = math.max(10, math.min(40, tonumber(args[3])));
        say('Name-plate icons are now ' .. S.plate .. ' px.');
        save_settings();
    elseif what == 'nudge' and tonumber(args[3]) then
        S.plate_dy = tonumber(args[3]);
        say('Name-plate icons moved ' .. S.plate_dy .. ' px.');
        save_settings();
    elseif what == 'party' then
        local sub = (args[3] or ''):lower();
        if sub == 'move' then
            S.party, S.party_moving = 1, true;
            say('Move the mouse to where the party column goes and click.');
        elseif sub == 'row' and tonumber(args[4]) then
            S.party_row = math.max(8, math.min(60, tonumber(args[4])));
            say('Party rows are now ' .. S.party_row .. ' px apart.');
        elseif sub == 'size' and tonumber(args[4]) then
            S.party_size = math.max(8, math.min(40, tonumber(args[4])));
            say('Party icons are now ' .. S.party_size .. ' px.');
        elseif sub == 'flip' then
            S.party_up = S.party_up == 1 and 0 or 1;
            say(S.party_up == 1 and 'You are now the bottom row.' or 'You are now the top row.');
        else
            S.party = S.party == 1 and 0 or 1;
            say(S.party == 1 and 'Party column on.' or 'Party column off.');
        end
        save_settings();
    elseif what == 'height' and tonumber(args[3]) then
        S.height = tonumber(args[3]);
        say('The name plate is now taken as ' .. S.height .. ' yalms above the feet.');
        save_settings();
    else
        S.on = not S.on;
        say(S.on and 'Badges on.' or 'Badges off.');
        if S.on then ask_soon(0.5); end
    end
end);
