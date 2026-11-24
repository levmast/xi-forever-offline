--[[
autora 1.0  (XI: Forever Offline, 2026-11-23; suggested by JØ)
Auto ranged attack. Three modes:
  Manual       nothing automatic: shoot with /ra yourself (the default)
  Auto         keeps shooting while you are engaged and have a ranged weapon or ammo on
  Until hate   like Auto, but holds fire while the monster is attacking you, and starts again when it turns to someone else

  /autora                 show or hide the small mode bar
  /autora manual | auto | hate
  /autora delay <sec>     the pause after each shot (default 0.5)
It only sends /ra <t>, the same command you could type. It waits for each shot to finish, holds while you move,
cast or use an item, and pauses a few seconds when the game says the target is out of range or out of sight.
]]

addon.name    = 'autora';
addon.author  = 'XI: Forever Offline';
addon.version = '1.0';
addon.desc    = 'Auto ranged attack: Manual, Auto, or Auto until the monster turns on you.';
addon.link    = '';

require('common');

local imgui;
do
    local ok, mod = pcall(require, 'imgui');
    if ok then imgui = mod; end
end

local MODES = { 'manual', 'auto', 'hate' };
local LABELS = { manual = 'Manual', auto = 'Auto', hate = 'Until hate' };
local S = {
    mode = 'manual',
    delay = 0.5,
    show = { true },
    busy = false, busyUntil = 0,    -- a shot (or a spell, an item) is under way
    nextAt = 0,                     -- earliest time for the next /ra
    pauseWhy = nil,
    hate = {},                      -- [monster id] = { me = true/false, t = time }
    lastPos = nil, movedAt = 0,
    warned = false,
    lastTick = -1,
};

local function now() return os.clock(); end

-- ---------------------------------------------------------------- settings (one small file)
local function settingsPath()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath(); end);
    if not ok or type(base) ~= 'string' then return nil; end
    return base .. 'config/addons/autora/settings.txt';
end

local function save()
    local path = settingsPath();
    if not path then return; end
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, (path:gsub('settings%.txt$', ''))); end
    local f = io.open(path, 'w');
    if f then
        f:write('mode=' .. S.mode .. '\ndelay=' .. S.delay .. '\nshow=' .. tostring(S.show[1]) .. '\n');
        f:close();
    end
end

local function load()
    local path = settingsPath();
    local f = path and io.open(path, 'r');
    if not f then return; end
    for line in f:lines() do
        local k, v = line:match('^(%w+)=(.*)$');
        if k == 'mode' and LABELS[v] then S.mode = v; end
        if k == 'delay' and tonumber(v) then S.delay = math.max(0, math.min(5, tonumber(v))); end
        if k == 'show' then S.show[1] = v ~= 'false'; end
    end
    f:close();
end

local function tell(text)
    print('\31\200[\31\05AutoRA\31\200]\30\01 ' .. text);
end

-- ---------------------------------------------------------------- the game
local function mem() return AshitaCore:GetMemoryManager(); end

local function myId()
    local ok, id = pcall(function() return mem():GetParty():GetMemberServerId(0); end);
    return ok and id or 0;
end

local function myIndex()
    local ok, idx = pcall(function() return mem():GetParty():GetMemberTargetIndex(0); end);
    return ok and idx or 0;
end

local function engaged()
    local ok, status = pcall(function() return mem():GetEntity():GetStatus(myIndex()); end);
    return ok and status == 1;
end

-- The monster you have targeted, as {index, id}, or nil
local function targetMob()
    local ok, idx = pcall(function()
        local t = mem():GetTarget();
        return t:GetIsSubTargetActive() == 1 and t:GetTargetIndex(1) or t:GetTargetIndex(0);
    end);
    if not ok or not idx or idx == 0 then return nil; end
    local ok2, id, flags, hpp = pcall(function()
        local e = mem():GetEntity();
        return e:GetServerId(idx), e:GetSpawnFlags(idx), e:GetHPPercent(idx);
    end);
    if not ok2 or not id or id == 0 then return nil; end
    if bit.band(flags or 0, 0x10) == 0 or (hpp or 0) <= 0 then return nil; end   -- monsters only, still alive
    return { index = idx, id = id };
end

local function rangedOn()
    local ok, on = pcall(function()
        local inv = mem():GetInventory();
        local function has(slot)
            local item = inv:GetEquippedItem(slot);
            return item ~= nil and item.Index ~= nil and item.Index ~= 0;
        end
        return has(2) or has(3);     -- ranged slot, ammo slot
    end);
    return ok and on;
end

local function moving()
    local ok, x, z = pcall(function()
        local e = mem():GetEntity();
        local i = myIndex();
        return e:GetLocalPositionX(i), e:GetLocalPositionY(i);
    end);
    if not ok or not x then return false; end
    local t = now();
    if S.lastPos and (math.abs(S.lastPos[1] - x) > 0.05 or math.abs(S.lastPos[2] - z) > 0.05) then S.movedAt = t; end
    S.lastPos = { x, z };
    return t - S.movedAt < 0.4;
end

local function shoot()
    AshitaCore:GetChatManager():QueueCommand(1, '/ra <t>');
    S.busy, S.busyUntil = true, now() + 6;
end

-- Holding fire in "Until hate": the monster's last action was on you (forgotten after 10 s without news)
local function hateOnMe(mob)
    local h = S.hate[mob.id];
    return h ~= nil and h.me and now() - h.t < 10;
end

local function tick()
    if S.mode == 'manual' then return; end
    local walking = moving();                -- sampled every tick, so a step just before a shot is seen
    local t = now();
    if S.busy and t < S.busyUntil then return; end
    S.busy = false;
    if t < S.nextAt or not engaged() then return; end
    local mob = targetMob();
    if not mob then return; end
    if not rangedOn() then
        if not S.warned then tell('No ranged weapon or ammo on: auto ranged attack is waiting.'); S.warned = true; end
        return;
    end
    S.warned = false;
    if walking then return; end
    if S.mode == 'hate' and hateOnMe(mob) then S.pauseWhy = 'it is attacking you'; return; end
    S.pauseWhy = nil;
    shoot();
end

-- ---------------------------------------------------------------- packets
local function uint(data, offset, bytes)
    if offset + bytes > #data then return nil; end
    local n = 0;
    for i = 0, bytes - 1 do n = n + data:byte(offset + i + 1) * 2 ^ (8 * i); end
    return n;
end

local function bits(data, start, count)
    if start + count > #data * 8 then return nil; end
    local n = 0;
    for i = 0, count - 1 do
        local b = start + i;
        n = n + (math.floor(data:byte(math.floor(b / 8) + 1) / 2 ^ (b % 8)) % 2) * 2 ^ i;
    end
    return n;
end

-- The parts of an action packet (0x028) this needs: who, what kind, and the first target of each
local function actionPacket(data)
    if type(data) ~= 'string' or #data < 24 then return nil; end
    local p = { actor = uint(data, 5, 4), category = bits(data, 82, 4), param = bits(data, 86, 16), targets = {} };
    local count = bits(data, 72, 10);
    if not count or count > 64 then return nil; end
    local pos = 150;
    for _ = 1, count do
        local id, actions = bits(data, pos, 32), bits(data, pos + 32, 4);
        if not id or not actions then return p; end
        table.insert(p.targets, id);
        pos = pos + 36;
        for _ = 1, actions do
            local additional = bits(data, pos + 85, 1);
            if additional == nil then return p; end
            pos = pos + 86 + (additional == 1 and 37 or 0);
            local spikes = bits(data, pos, 1);
            if spikes == nil then return p; end
            pos = pos + 1 + (spikes == 1 and 34 or 0);
        end
    end
    return p;
end

local INTERRUPTED = 28787;
-- "Out of range", "can't see", "too far away", "can't use that ranged weapon" and similar: pause instead of spamming
local PAUSE_MESSAGES = { [4] = true, [5] = true, [12] = true, [16] = true, [17] = true, [78] = true, [217] = true, [218] = true };

local function onAction(a)
    local me = myId();
    if a.actor == me then
        if a.category == 12 then                                       -- a shot starts (or was interrupted)
            if a.param == INTERRUPTED then S.busy = false; S.nextAt = now() + 1.5;
            else S.busy, S.busyUntil = true, now() + 6; end
        elseif a.category == 2 then                                    -- a shot landed
            S.busy = false; S.nextAt = now() + S.delay;
        elseif a.category == 8 or a.category == 9 then                 -- you began a spell or an item
            if a.param == INTERRUPTED then S.busy = false; S.nextAt = now() + 0.5;
            else S.busy, S.busyUntil = true, now() + 12; end
        elseif a.category == 4 or a.category == 5 then                 -- it finished
            S.busy = false; S.nextAt = now() + 1.0;
        end
        return;
    end
    -- a monster acting on someone: on you, or on someone else (the tank has it back)
    if a.targets[1] and (a.category == 1 or a.category == 7 or a.category == 11 or a.category == 8 or a.category == 4) then
        local onMe = false;
        for _, id in ipairs(a.targets) do if id == me then onMe = true; end end
        if a.category == 8 or a.category == 7 then
            if onMe then S.hate[a.actor] = { me = true, t = now() }; end    -- readying a move on you counts
        else
            S.hate[a.actor] = { me = onMe, t = now() };
        end
    end
end

ashita.events.register('packet_in', 'autora_packet_in', function (e)
    if e.id == 0x028 then
        local a = actionPacket(e.data);
        if a then pcall(onAction, a); end
    elseif e.id == 0x029 then
        local actor, message = uint(e.data, 4, 4), uint(e.data, 24, 2);
        if actor == myId() and message and PAUSE_MESSAGES[message % 32768] and S.mode ~= 'manual' then
            S.busy = false; S.nextAt = now() + 3;
        end
    elseif e.id == 0x00A or e.id == 0x00B then
        S.hate, S.busy = {}, false;
    end
end);

-- ---------------------------------------------------------------- the mode bar
local function setMode(mode)
    S.mode = mode;
    S.busy, S.nextAt = false, 0;
    save();
    tell('Mode: ' .. LABELS[mode] .. '.');
end

local function render()
    if not (imgui and imgui.Begin) or not S.show[1] then return; end
    local flags = bit.bor(rawget(_G, 'ImGuiWindowFlags_AlwaysAutoResize') or 64, rawget(_G, 'ImGuiWindowFlags_NoCollapse') or 32);
    if imgui.Begin('Auto RA', S.show, flags) then
        for i, mode in ipairs(MODES) do
            if i > 1 and imgui.SameLine then imgui.SameLine(); end
            local active = S.mode == mode;
            local pushed = 0;
            if active and imgui.PushStyleColor and rawget(_G, 'ImGuiCol_Button') then
                imgui.PushStyleColor(ImGuiCol_Button, { 0.20, 0.55, 0.25, 1 });
                pushed = 1;
            end
            if imgui.Button(LABELS[mode]) and not active then setMode(mode); end
            if pushed > 0 then imgui.PopStyleColor(pushed); end
        end
        if S.pauseWhy and S.mode == 'hate' then imgui.Text('Holding: ' .. S.pauseWhy); end
    end
    imgui.End();
end

ashita.events.register('load', 'autora_load', function () pcall(load); end);

ashita.events.register('d3d_present', 'autora_present', function ()
    local t = now();
    if t - S.lastTick >= 0.2 then
        S.lastTick = t;
        local ok, err = pcall(tick);
        if not ok and not S.errorShown then tell('problem: ' .. tostring(err)); S.errorShown = true; end
    end
    render();
end);

ashita.events.register('command', 'autora_command', function (e)
    local args = e.command:args();
    if #args == 0 then return; end
    local cmd = args[1]:lower();
    if cmd ~= '/autora' and cmd ~= '/ara' then return; end
    e.blocked = true;
    local sub = (args[2] or ''):lower();
    if sub == '' then S.show[1] = not S.show[1]; save();
    elseif sub == 'manual' or sub == 'off' then setMode('manual');
    elseif sub == 'auto' or sub == 'on' then setMode('auto');
    elseif sub == 'hate' or sub == 'safe' then setMode('hate');
    elseif sub == 'delay' and tonumber(args[3]) then
        S.delay = math.max(0, math.min(5, tonumber(args[3]))); save();
        tell('Pause after each shot: ' .. S.delay .. ' s.');
    else
        tell('/autora manual | auto | hate | delay <sec>   (/autora alone shows or hides the bar)');
    end
end);
