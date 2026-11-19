--[[
servermenu 1.6
One menu for XI: Forever Offline, opened from a small Squads button on the screen. It replaces the Squad panel (/sq still works).

  Squad        your squad mates: call, dismiss, role, mode, main and support job, and a Profile button per mate with
               their current stats, HP/MP/TP, haste, jobs and equipped items (the Titan-style profile screen);
               the Camp row (1.6): set camp, camp off, who pulls (you or a mate), pause/resume pulls
               (1.7) setting a camp tells the second window to stop following (followme 1.2), camp off to follow again
               (1.8) Pull: pick which kind of monster around the camp a mate puller goes for (or anything)
  Dualbox      your second character: AUTO on/off, job profile, HP/MP, what he is doing, and his Gambits section
               (the gambit rows, on/off, order and reset are his, not your squad's)
  Diagnostics  hidden from the tab row; /menu diagnostics still opens it when support asks for it

  The Squads button     click: open or close the menu. Drag it to move it. Right-click: lock it in place, or hide it.
  /menu              open or close the menu (also /smenu)
  /menu button       show the button again after hiding it      /menu resetbutton   put it back in its first place
  /menu scale <n>    size of our windows (0.75-3, 1 = normal; for 4K screens)
  /sq                open the menu on the Squad tab              /sq refresh         ask the server again
  /sq sheet [slot]   open a mate's profile window (also the Profile button on their row)
  /menu gambits      open the menu on Dualbox with its Gambits section showing

It is loaded in BOTH game windows. In the second window the Squad tab shows that character's own squad, and the
Dualbox tab shows the dualbox character himself (the same files, read from the same folder).

How it talks to the rest:
  - the squad: only the commands you could type yourself (!squad panel, role, mode, job, sub, call, dismiss); the server's
    "squadpanel:" answer lines and the echo of the menu's own commands are kept out of your chat log
  - the second window: two small files in config/addons/duo (status.cfg in, command.cfg out), read and written by the followme
    addon (0.9 or newer for the Gambits tab). Changes are sent one batch at a time and only after the last batch was carried out,
    so quick clicks are not lost.
  - his gambit sheet: read straight from the gambit engine's own file (both windows share the Ashita folder); it is never written
    here, every change goes through the engine's own commands in the second window.
Settings (button place, last tab): config/addons/servermenu/settings.cfg
]]

addon.name    = 'servermenu';
addon.author  = 'XI: Forever Offline';
addon.version = '1.21';
addon.desc    = 'The XI: Forever Offline menu: squad mates, and the dualbox character with his gambits.';
addon.link    = '';

require('common');

local imgui;
do
    local ok, mod = pcall(require, 'imgui');
    if ok then imgui = mod; end
end

-- The item icons come from the game's own item bitmaps, the same source the equipment monitor uses.
-- Both modules are optional so the sheet still works as text if a future Ashita build moves them.
local ffi, d3d8;
do
    local ok, mod = pcall(require, 'ffi');
    if ok then ffi = mod; end
    local ok2, mod2 = pcall(require, 'd3d8');
    if ok2 then d3d8 = mod2; end
end

-- ---------------------------------------------------------------- constants
local ROLES = { 'auto', 'tank', 'damage', 'healer', 'support' };
local MODES = { 'balanced', 'aggressive', 'conserve' };
local JOBS  = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU', 'COR', 'PUP' };

-- the stat sheet: the server sends the switches as a mask (1 melee, 2 ranged, 4 ja, 8 magic), 15 = all on
local SWITCHES = { 'melee', 'ranged', 'ja', 'magic' };
local SW_BIT   = { melee = 1, ranged = 2, ja = 4, magic = 8 };
local SLOT_LABEL = { 'Main', 'Sub', 'Ranged', 'Ammo', 'Head', 'Body', 'Hands', 'Legs', 'Feet', 'Neck', 'Waist', 'Ear 1', 'Ear 2', 'Ring 1', 'Ring 2', 'Back' };
local SHEET_LEFT  = { 0, 2, 4, 6, 8, 9, 11, 13 };
local SHEET_RIGHT = { 1, 3, 5, 7, 10, 12, 14, 15 };
local ICON = 26;

-- The role colour behind the name, the same idea as Titan's recruit list and the squad panel.
local ROLE_COLORS =
{
    tank    = { 0.18, 0.38, 0.58, 1.00 },
    healer  = { 0.18, 0.44, 0.25, 1.00 },
    support = { 0.55, 0.42, 0.12, 1.00 },
    damage  = { 0.48, 0.19, 0.19, 1.00 },
    auto    = { 0.24, 0.24, 0.24, 1.00 },
};
local ROLE_NAME = { tank = 'TANK', healer = 'HEALER', support = 'SUPPORT', damage = 'DPS', auto = 'AUTO' };
local VITAL_COLORS =
{
    HP = { 0.22, 0.55, 0.28, 0.82 },
    MP = { 0.22, 0.38, 0.68, 0.82 },
    TP = { 0.68, 0.56, 0.16, 0.82 },
    EXP = { 0.62, 0.36, 0.70, 0.82 },
};

local function hasBit(mask, bit)
    return math.floor((tonumber(mask) or 0) / bit) % 2 == 1;
end
local TABS  = { 'Squad', 'Dualbox', 'Auto' };

local ROLE_HELP = {
    auto    = 'the job\'s normal behaviour',
    tank    = 'Provoke, Flash, own buffs; heals only the badly hurt',
    damage  = 'attacks and nukes; heals only the badly hurt',
    healer  = 'cures, status removal, party buffs',
    support = 'buffs, weakening spells, cures',
};
local MODE_HELP = {
    balanced   = 'the normal pace',
    aggressive = 'heals earlier and holds nothing back',
    conserve   = 'heals later and keeps 40% MP in reserve',
};

local LAYERS = {
    emergency_survival     = { 'Survival',    { 0.90, 0.45, 0.40, 1 } },
    raise                  = { 'Raise',       { 0.95, 0.85, 0.55, 1 } },
    emergency_healing      = { 'Healing',     { 0.45, 0.85, 0.55, 1 } },
    status_removal         = { 'Status',      { 0.55, 0.80, 0.80, 1 } },
    critical_job_mechanics = { 'Job tools',   { 0.85, 0.65, 0.40, 1 } },
    job_specific_actions   = { 'Job attacks', { 0.85, 0.65, 0.40, 1 } },
    weapon_skill           = { 'Weapon skill',{ 0.90, 0.75, 0.45, 1 } },
    buff_maintenance       = { 'Buffs',       { 0.55, 0.70, 0.95, 1 } },
    debuffs                = { 'Debuffs',     { 0.75, 0.60, 0.95, 1 } },
    offensive_magic        = { 'Nukes',       { 0.95, 0.55, 0.75, 1 } },
};
local TARGETS = { self = 'self', enemy = 'enemy', lowest = 'lowest HP ally', ally = 'party', dead = 'KO\'d ally', status = 'afflicted ally', mp = 'low-MP ally' };

-- the look
local C = {
    gold   = { 0.89, 0.74, 0.40, 1 },
    text   = { 0.88, 0.89, 0.92, 1 },
    dim    = { 0.56, 0.59, 0.66, 1 },
    good   = { 0.42, 0.85, 0.52, 1 },
    bad    = { 0.95, 0.42, 0.40, 1 },
    warn   = { 0.96, 0.76, 0.36, 1 },
    hp     = { 0.30, 0.70, 0.38, 1 },
    mp     = { 0.30, 0.50, 0.90, 1 },
    on     = { 0.16, 0.48, 0.28, 1 },
    onHi   = { 0.22, 0.60, 0.36, 1 },
    sel    = { 0.55, 0.43, 0.18, 1 },
    selHi  = { 0.68, 0.54, 0.24, 1 },
    panel  = { 0.065, 0.075, 0.105, 0.97 },
    line   = { 0.30, 0.32, 0.40, 0.55 },
    faint  = { 0.46, 0.49, 0.55, 1 },
};

-- ---------------------------------------------------------------- state
local S = {
    open = { false }, tab = 'Squad',
    -- squad
    mates = {}, incoming = nil, waitUntil = 0, hideUntil = 0, lastAsk = -1000, lastSend = -1000, queue = {}, pendingApply = false, more = {},
    sheetOpen = { false }, sheetFresh = false, profile = nil, profileIncoming = nil, sheetSlot = nil, sheetWaitUntil = 0, lastSheetAsk = -1000,
    -- dualbox
    duoHold = false, duo = nil, duoRead = -1000, duoSeq = 0, duoPending = nil, duoSentSeq = nil, duoSentAt = -1000, duoGambits = false,
    -- gambits
    sheet = nil, sheetText = nil, sheetPath = nil, sheetRead = -1000, sheetHoldUntil = 0, rowOverride = {}, sheetError = nil,
    -- diagnostics
    spell = { 'Dia' },
    -- the button
    cfg = { button_x = '18', button_y = '240', button_locked = 'false', button_hidden = 'false', button_wide = 'false', tab = 'Squad', spell = 'Dia', scale = '1' },
    cfgDirty = false, cfgSavedAt = -1000, buttonPos = nil, dragging = false, dragFrom = nil, dragMoved = false,
};

local function now()
    if ashita and ashita.time and type(ashita.time.get_tick64) == 'function' then
        local ok, n = pcall(ashita.time.get_tick64);
        if ok and type(n) == 'number' then return n / 1000; end
    end
    return os.clock();
end

local function say(text) print('[servermenu] ' .. tostring(text)); end

local function strip(message)
    local text = tostring(message or ''):gsub('%z', ''):gsub('[\30\31].', ''):gsub('^%s+', ''):gsub('%s+$', '');
    return text;
end

local function installPath()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath(); end);
    if ok and type(base) == 'string' then
        if not base:match('[/\\]$') then base = base .. '/'; end
        return base;
    end
    return nil;
end

local function mkdir(dir)
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, dir); end
end

-- ---------------------------------------------------------------- settings
local function cfgPath()
    local base = installPath();
    return base and (base .. 'config/addons/servermenu/'), base and (base .. 'config/addons/servermenu/settings.cfg');
end

local function loadCfg()
    local _, path = cfgPath();
    local f = path and io.open(path, 'r');
    if not f then return false, false; end
    local hadWide = false;
    for line in f:lines() do
        local k, v = line:match('^%s*([%w_]+)%s*=%s*(.-)%s*$');
        if k then
            if k == 'button_wide' then hadWide = true; end
            if S.cfg[k] ~= nil then S.cfg[k] = v; end
        end
    end
    f:close();
    return hadWide, true;
end

local function saveCfg()
    local dir, path = cfgPath();
    if not path then return; end
    mkdir(dir);
    local f = io.open(path, 'w');
    if not f then return; end
    local keys = {};
    for k in pairs(S.cfg) do keys[#keys + 1] = k; end
    table.sort(keys);
    for _, k in ipairs(keys) do f:write(k .. '=' .. tostring(S.cfg[k]) .. '\n'); end
    f:close();
    S.cfgDirty, S.cfgSavedAt = false, now();
end

local function setCfg(key, value)
    value = tostring(value);
    if S.cfg[key] ~= value then S.cfg[key] = value; S.cfgDirty = true; end
end

-- ---------------------------------------------------------------- the squad: chat commands, one at a time
local function chatManager()
    local ok, chat = pcall(function() return AshitaCore:GetChatManager(); end);
    if ok then return chat; end
    return nil;
end

local function typing(chat)
    local ok, open = pcall(function() return chat:IsInputOpen(); end);
    return ok and (open == true or (type(open) == 'number' and open ~= 0));
end

local function enqueue(command, delay)
    S.queue[#S.queue + 1] = { at = now() + (delay or 0), command = command };
end

local function ask(delay)
    enqueue('/say !squad panel', delay or 0);
    S.waitUntil = now() + (delay or 0) + 5;
    S.lastAsk = now();
    S.incoming = nil;
end

local function pump(t)
    if t - S.lastSend < 0.6 then return; end
    local pick = nil;                                   -- the first command that is due (a later "ask again" does not hold up a click)
    for i, item in ipairs(S.queue) do if item.at <= t then pick = i; break; end end
    if not pick then return; end
    local chat = chatManager();
    if chat == nil or typing(chat) then return; end
    local first = table.remove(S.queue, pick);
    S.lastSend = t;
    S.hideUntil = t + 2.5;
    pcall(function() chat:QueueCommand(1, first.command); end);
end

-- squad.lua 1.13 added a tenth field, the melee/ranged/ja/magic mask (14 = all four on).
-- Older servers stop at the ninth, so the mask is optional here; without this every line was
-- rejected and the tab said "No squad mates yet" while the mates were standing right there.
local function parseMate(payload)
    local slot, name, mainJob, mainLevel, subJob, subLevel, role, mode, called, mask =
        payload:match('^(%d+)|([^|]+)|([^|]+)|(%d+)|([^|]+)|(%d+)|(%a+)|(%a+)|([01])|?(%d*)$');
    if not slot then return nil; end
    return { slot = tonumber(slot), name = name, main = mainJob, mainLevel = tonumber(mainLevel), sub = subJob, subLevel = tonumber(subLevel),
             role = role, mode = mode, out = called == '1', switches = tonumber(mask) };
end

-- squad.lua (camp and pull) adds: camp|<1 on, 0 off>|<puller slot, 0 = you>|<1 paused>|<pulls so far>
local function parseCamp(payload)
    local on, puller, paused, pulls = payload:match('^camp|([01])|(%d+)|([01])|(%d+)$');
    if not on then return nil; end
    return { on = on == '1', puller = tonumber(puller), paused = paused == '1', pulls = tonumber(pulls) };
end

local queueDuo -- (the second window's command batch, defined further down)

local function onLine(payload)
    -- (1.19) a Blue Mage mate's set blue magic: blu|slot|slots|points|used|auto, blus|slot|id|name|level|points|set, blue|slot
    local bs, bsl, bpt, bused, bauto = payload:match('^blu|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)$');
    if bs then
        S.blu = { slot = tonumber(bs), slots = tonumber(bsl), points = tonumber(bpt), used = tonumber(bused), auto = bauto == '1', list = {}, done = false };
        return;
    end
    local ks, kid, kname, klv, kpt, kset = payload:match('^blus|(%d+)|(%d+)|([^|]+)|(%d+)|(%d+)|(%d+)$');
    if ks then
        local b = S.blu;
        if b and b.slot == tonumber(ks) then
            b.list[#b.list + 1] = { id = tonumber(kid), name = kname:gsub('_', ' '), level = tonumber(klv), points = tonumber(kpt), set = kset == '1' };
        end
        return;
    end
    local es2 = payload:match('^blue|(%d+)$');
    if es2 then
        if S.blu and S.blu.slot == tonumber(es2) then S.blu.done = true; end
        S.waitUntil = 0;
        return;
    end
    -- (1.14) gear picker answers: gl|<mate slot>|<equip slot>|<item id>|<level>|<name> ... gle|<mate slot>|<equip slot>|<count>
    local gs, ge, gid, glv, gname = payload:match('^gl|(%d+)|(%d+)|(%d+)|(%d+)|(.+)$');
    if gs then
        local g = S.gear;
        if g and g.slot == tonumber(gs) and g.eq == tonumber(ge) then
            g.items[#g.items + 1] = { id = tonumber(gid), level = tonumber(glv), name = gname };
        end
        return;
    end
    local es, ee, ecount = payload:match('^gle|(%d+)|(%-?%d+)|(%d+)$');
    if es then
        local g = S.gear;
        if g and g.slot == tonumber(es) and g.eq == tonumber(ee) then g.done, g.total = true, tonumber(ecount); end
        S.waitUntil = 0;
        return;
    end
    if payload == 'end' then
        S.mates = S.incoming or {};
        S.incoming = nil;
        S.camp = S.incomingCamp;                -- (nil from a server without camps: the Camp row stays hidden)
        S.incomingCamp = nil;
        S.engage = S.incomingEngage;            -- (nil from an older server: the engage button and the Style row stay hidden)
        S.incomingEngage = nil;
        S.autoEquip = S.incomingAuto;           -- (1.15; nil from an older server: the Auto-equip button stays hidden)
        S.incomingAuto = nil;
        S.opts = S.incomingOpts or {};
        S.incomingOpts = nil;
        S.adv = S.incomingAdv;                  -- (nil from an older server: the Advanced button stays hidden)
        S.incomingAdv = nil;
        S.readyAt = S.incomingReady or {};      -- (1.12) [slot] = os.time() when that mate can be called again
        S.incomingReady = nil;
        -- the second window holds the camp too: no following while a camp is set
        local hold = S.camp ~= nil and S.camp.on == true;
        if hold ~= S.duoHold then
            S.duoHold = hold;
            queueDuo({ follow = hold and 'off' or 'on' });
        end
        S.waitUntil = 0;
        return;
    end
    local camp = parseCamp(payload);
    if camp then S.incomingCamp = camp; return; end
    -- (squad.lua for servermenu 1.17) campbots|<bot players in your party, comma list or ->|<the bot pulling or ->
    local cbNames, cbPuller = payload:match('^campbots|([^|]*)|([^|]*)$');
    if cbNames then
        if S.incomingCamp then
            S.incomingCamp.bots = {};
            if cbNames ~= '-' then for n in cbNames:gmatch('[^,]+') do S.incomingCamp.bots[#S.incomingCamp.bots + 1] = n; end end
            S.incomingCamp.botPuller = cbPuller ~= '-' and cbPuller or nil;
        end
        return;
    end
    -- (squad.lua for servermenu 1.10) engage|<1 first> and opt|<slot>|<size 0-3>|<ws TP, 0 chain>|<WS or ->|<range 0-3>|<usable WS or ->
    local engage = payload:match('^engage|([01])$');
    if engage then S.incomingEngage = engage == '1' and 'first' or 'normal'; return; end
    -- (squad.lua for servermenu 1.15) auto|<1 on> : auto-equip
    local auto = payload:match('^auto|([01])$');
    if auto then S.incomingAuto = auto == '1'; return; end
    -- (squad.lua for servermenu 1.11) adv|<follow 0-2>|<camp rest 1/0>|<order digits or -> and delay|<slot>|<seconds>
    local afollow, arest, aorder = payload:match('^adv|(%d)|([01])|([%d-]+)$');
    if afollow then
        S.incomingAdv = { follow = tonumber(afollow), rest = arest == '1', order = aorder ~= '-' and aorder or nil, delay = {} };
        return;
    end
    -- (squad.lua for servermenu 1.12) cd|<slot>|<seconds before the mate can be called again>
    local cslot, csecs = payload:match('^cd|(%d+)|(%d+)$');
    if cslot then
        S.incomingReady = S.incomingReady or {};
        S.incomingReady[tonumber(cslot)] = os.time() + tonumber(csecs);
        return;
    end
    -- (squad.lua for servermenu 1.14) plvl|<low>|<high>|<1 = your own window>: camp pull levels against yours
    local plo, phi, pown = payload:match('^plvl|(%-?%d+)|(%-?%d+)|([01])$');
    if plo then
        if S.incomingAdv then S.incomingAdv.pull = { low = tonumber(plo), high = tonumber(phi), own = pown == '1' }; end
        return;
    end
    local dslot, dsecs = payload:match('^delay|(%d+)|(%d+)$');
    if dslot then
        if S.incomingAdv then S.incomingAdv.delay[tonumber(dslot)] = tonumber(dsecs); end
        return;
    end
    local oslot, osize, otp, ows, orange, olist = payload:match('^opt|(%d+)|(%d+)|(%d+)|([^|]+)|(%d+)|(.*)$');
    if oslot then
        local list = {};
        for name in tostring(olist):gmatch('[^,]+') do
            if name ~= '-' then list[#list + 1] = (name:gsub('_', ' ')); end
        end
        S.incomingOpts = S.incomingOpts or {};
        S.incomingOpts[tonumber(oslot)] = { size = tonumber(osize), tp = tonumber(otp), ws = ows ~= '-' and (ows:gsub('_', ' ')) or nil,
                                            range = tonumber(orange), list = list };
        return;
    end
    -- (squad.lua with pull choices) campwant|<Monster_Name or -> and campmob|<Monster_Name>|<lowest lv>|<highest lv>|<how many>|<1 pullable>
    local want = payload:match('^campwant|(.+)$');
    if want and S.incomingCamp then
        S.incomingCamp.want = want ~= '-' and want or nil;
        S.incomingCamp.wants = {};
        for name in tostring(want):gmatch('[^,]+') do
            name = name:match('^%s*(.-)%s*$');
            if name ~= '' and name ~= '-' then S.incomingCamp.wants[name:lower():gsub('_', ' ')] = true; end
        end
        S.incomingCamp.kinds = S.incomingCamp.kinds or {};
        return;
    end
    local mname, mlo, mhi, mcount, mfits = payload:match('^campmob|([^|]+)|(%d+)|(%d+)|(%d+)|([01])$');
    if mname and S.incomingCamp then
        S.incomingCamp.kinds = S.incomingCamp.kinds or {};
        table.insert(S.incomingCamp.kinds, { name = mname, lo = tonumber(mlo), hi = tonumber(mhi), count = tonumber(mcount), fits = mfits == '1' });
        return;
    end
    local mate = parseMate(payload);
    if mate then
        S.incoming = S.incoming or {};
        S.incoming[#S.incoming + 1] = mate;
    end
end

-- ---------------------------------------------------------------- the stat sheet (one short line per value)
local function askSheet(delay)
    if S.sheetSlot == nil then return; end
    enqueue(string.format('/say !squad sheet %d', S.sheetSlot), delay or 0);
    S.sheetWaitUntil = now() + (delay or 0) + 5;
    S.lastSheetAsk = now();
    S.profileIncoming = {};
end

local function openSheet(slot)
    slot = tonumber(slot);
    if slot == nil then return; end
    S.sheetSlot = slot;
    S.sheetOpen[1] = true;
    S.sheetFresh = true;        -- next frame: put the window in the middle of the screen, in front
    S.profile = nil;
    askSheet(0);
end

local function onSheetLine(text)
    if text == 'end' then
        if S.profileIncoming and S.profileIncoming.hdr then S.profile = S.profileIncoming; end
        S.profileIncoming = nil;
        return;
    end
    local data = S.profileIncoming;
    if not data then return; end
    local key, rest = text:match('^(%a+)|(.*)$');
    if not key then return; end
    if key == 'hdr' then
        local name, job, main, sub, subLevel, role, mode, race, mask =
            rest:match('^(.-)|([^|]*)|(%d+)|([^|]*)|(%d+)|([^|]*)|([^|]*)|([^|]*)|(%d+)$');
        if name then
            data.hdr = { name = name, job = job, main = tonumber(main), sub = sub, subLevel = tonumber(subLevel),
                         role = role, mode = mode, race = race, mask = tonumber(mask) or 15 };
        end
    elseif key == 'job' then
        local job, level = rest:match('^([^|]+)|(%d+)$');
        if job then data.jobs = data.jobs or {}; data.jobs[#data.jobs + 1] = { job, tonumber(level) }; end
    elseif key == 'exp' then
        local job, level, cur, needed = rest:match('^([^|]*)|(%d+)|(%d+)|(%d+)$');
        if job then data.exp = { job = job, level = tonumber(level), cur = tonumber(cur), needed = tonumber(needed) }; end
    elseif key == 'vital' then
        local label, cur, max = rest:match('^([^|]+)|(%d+)|(%d+)$');
        if label then data.vitals = data.vitals or {}; data.vitals[#data.vitals + 1] = { label, tonumber(cur), tonumber(max) }; end
    elseif key == 'stat' or key == 'combat' or key == 'haste' then
        local label, value = rest:match('^([^|]+)|(-?%d+)$');
        if label then
            local field = (key == 'stat') and 'stats' or key;
            data[field] = data[field] or {};
            data[field][#data[field] + 1] = { label, tonumber(value) };
        end
    elseif key == 'eq' then
        -- The current server sends slot | label | name | id. Older answers had only slot | label | name,
        -- and some had the id stuck on the end of the name instead of in its own field.
        local slot, name, id = rest:match('^(%d+)|[^|]*|([^|]*)|(%d+)$');
        if not slot then
            slot, name = rest:match('^(%d+)|[^|]*|(.*)$');
            if slot then
                local embedded = name and name:match('|(%d+)$');
                if embedded ~= nil then
                    id = embedded;
                    name = name:gsub('|%d+$', '');
                end
            end
        end
        if slot then
            data.eq = data.eq or {};
            data.eq[tonumber(slot)] = name;
            if id ~= nil then
                data.eqId = data.eqId or {};
                data.eqId[tonumber(slot)] = tonumber(id);
            end
        end
    elseif key == 'ls' then
        -- (1.21) lockstyle: slot | label | name | id
        local slot, name, id = rest:match('^(%d+)|[^|]*|([^|]*)|(%d+)$');
        if slot then
            data.ls = data.ls or {};
            data.ls[tonumber(slot)] = { name = name, id = tonumber(id) };
        end
    elseif key == 'note' then
        data.note = rest;
    end
end

-- role, mode, job and sub apply when a mate is called, so they leave a "press Apply now" banner
local function changeMate(mate, kind, value)
    enqueue(string.format('/say !squad %s %d %s', kind, mate.slot, value));
    if kind == 'role' or kind == 'mode' then mate[kind] = value; end
    if kind == 'job' then mate.main = value; end
    if kind == 'sub' then mate.sub = (value == 'none') and '-' or value; end
    S.pendingApply = true;
    ask(1.5);
end

-- the Camp row: !squad camp / camp off / camp pause|resume / pull me|<slot>
local function campCommand(command)
    enqueue('/say !squad ' .. command);
    ask(1.5);
end

local function applyNow()
    enqueue('/say !squad reapply');
    ask(5);
    S.pendingApply = false;
end

-- ---------------------------------------------------------------- the second window, through two small files
local function duoDir()
    local base = installPath();
    return base and (base .. 'config/addons/duo/');
end

local function readDuo()
    S.duoRead = now();
    local dir = duoDir();
    local f = dir and io.open(dir .. 'status.cfg', 'r');
    if not f then S.duo = nil; return; end
    local values = {};
    for line in f:lines() do
        local k, v = line:match('^%s*([%w_]+)%s*=%s*(.-)%s*$');
        if k then values[k] = v; end
    end
    f:close();
    local stamp = tonumber(values.time);
    if stamp and math.abs(os.time() - stamp) <= 6 then S.duo = values; else S.duo = nil; end   -- an old file means that window is closed
end

-- "0.9" -> 0.009, "0.10" -> 0.010, "1.0" -> 1.0: compared part by part, so 0.10 counts as newer than 0.9
local function duoVersion()
    local major, minor = tostring(S.duo and S.duo.version or ''):match('^(%d+)%.(%d+)');
    if not major then return 0; end
    return tonumber(major) + tonumber(minor) / 1000;
end

-- Changes wait in one batch; the batch is written when the last one was carried out (status.cfg's ack), or after 4 seconds
queueDuo = function(fields)
    local p = S.duoPending or { ops = {} };
    for k, v in pairs(fields) do
        if k == 'ops' then
            for _, op in ipairs(v) do p.ops[#p.ops + 1] = op; end
        else
            p[k] = v;
        end
    end
    S.duoPending = p;
end

local function flushDuo(t)
    local p = S.duoPending;
    if not p then return; end
    if S.duoSentSeq then
        local acked = S.duo and tonumber(S.duo.ack) == S.duoSentSeq;
        if not acked and t - S.duoSentAt < 4 then return; end
    end
    local dir = duoDir();
    if not dir then return; end
    mkdir(dir);
    local f = io.open(dir .. 'command.cfg', 'wb');      -- binary: no \r\n, so the other window reads clean values
    if not f then return; end
    -- both game windows may run this menu: a random tail keeps their numbers from ever being the same
    S.duoSeq = math.max(S.duoSeq + 1, os.time() * 100 + math.random(0, 99));
    f:write('seq=' .. S.duoSeq .. '\n');
    for _, key in ipairs({ 'auto', 'profile', 'unclaimed', 'probe', 'follow' }) do
        if p[key] then f:write(key .. '=' .. p[key] .. '\n'); end
    end
    if p.reset then f:write('reset=1\n'); end
    if #p.ops > 0 then f:write('ops=' .. table.concat(p.ops, ',') .. '\n'); end
    f:close();
    S.duoSentSeq, S.duoSentAt, S.duoPending = S.duoSeq, t, nil;
end

-- ---------------------------------------------------------------- his gambit sheet (read only)
local function loadTable(text)
    local env = {};
    local chunk;
    local setfenv, loadstring = rawget(_G, 'setfenv'), rawget(_G, 'loadstring');
    if setfenv and loadstring then
        chunk = loadstring(text);
        if chunk then setfenv(chunk, env); end
    else
        chunk = load(text, 'sheet', 't', env);
    end
    if not chunk then return nil; end
    local ok, result = pcall(chunk);
    if ok and type(result) == 'table' then return result; end
    return nil;
end

-- The Gambits sheets folder: config/addons/Gambits, or the addon's earlier
-- config/addons/TitanGambits until Gambits has moved it on its next load.
local function gambitsFolder(base)
    for _, name in ipairs({ 'Gambits', 'TitanGambits' }) do
        local f = io.open(base .. 'config/addons/' .. name .. '/settings.lua', 'rb');
        if f then f:close(); return base .. 'config/addons/' .. name .. '/'; end
    end
    return base .. 'config/addons/Gambits/';
end

local function sheetPathFor(duo)
    if not duo then return nil; end
    if duo.sheetpath and duo.sheetpath ~= '' then return duo.sheetpath; end
    local base = installPath();
    if base and duo.job and duo.job:match('^%u%u%u$') then return gambitsFolder(base) .. 'jobs/' .. duo.job .. '.lua'; end
    return nil;
end

local function readSheet(t)
    S.sheetRead = t;
    if t < S.sheetHoldUntil then return; end
    local path = sheetPathFor(S.duo);
    if not path then S.sheet, S.sheetText, S.sheetError = nil, nil, 'no job yet'; return; end
    local f = io.open(path, 'rb');
    if not f then S.sheet, S.sheetText, S.sheetPath, S.sheetError = nil, nil, path, 'not found'; return; end
    local text = f:read('*a');
    f:close();
    if text == S.sheetText and path == S.sheetPath then return; end
    local data = loadTable(text);
    if not data or type(data.Rules) ~= 'table' then
        if not S.sheet then S.sheetError = 'could not be read'; end
        return;                                        -- half-written by the engine this instant: keep what was there
    end
    local rows = {};
    for i, r in ipairs(data.Rules) do
        if type(r) == 'table' then
            rows[#rows + 1] = { index = i, id = tostring(r.Id or ''), label = r.Label, action = r.Action, actions = r.Actions, layer = r.Layer,
                                target = r.Target, enabled = r.Enabled ~= false, empty = r.Empty == true };
        end
    end
    S.sheet = { job = data.Job, enabled = data.Enabled ~= false, rows = rows };
    S.sheetText, S.sheetPath, S.sheetError = text, path, nil;
    for id, o in pairs(S.rowOverride) do                -- the file now says what was asked: no need to pretend any more
        for _, row in ipairs(rows) do if row.id == id and row.enabled == o.enabled then S.rowOverride[id] = nil; end end
    end
end

local function rowEnabled(row)
    local o = S.rowOverride[row.id];
    if o and now() < o.untilAt then return o.enabled; end
    return row.enabled;
end

local function titleCase(text)
    return (text:gsub('[-_]', ' '):gsub('(%a)(%w*)', function(a, b) return a:upper() .. b; end));
end

local function rowName(row)
    local label = type(row.label) == 'string' and row.label or '';
    if label == '' or label == row.id or label:match('^[%l%d%-_]+$') then
        if type(row.action) == 'string' and row.action ~= '' then return row.action; end
        return titleCase(row.id ~= '' and row.id or label);
    end
    if #label > 38 then label = label:sub(1, 36) .. '..'; end
    return label;
end

local function setRow(row, on)
    if not row.id:match('^[%w%-_]+$') then return; end
    queueDuo({ ops = { (on and 'enable:' or 'disable:') .. row.id } });
    S.rowOverride[row.id] = { enabled = on, untilAt = now() + 8 };
end

local function moveRow(position, delta)
    local rows = S.sheet and S.sheet.rows;
    if not rows then return; end
    local other = position + delta;
    if other < 1 or other > #rows then return; end
    local a, b = rows[position], rows[other];
    queueDuo({ ops = { string.format('move:%d:%d', a.index, b.index) } });
    a.index, b.index = b.index, a.index;               -- show the new order at once
    rows[position], rows[other] = b, a;
    S.sheetHoldUntil = now() + 3;
end

-- ---------------------------------------------------------------- small ImGui helpers (every optional call is checked first)
local function has(name) return imgui ~= nil and type(imgui[name]) == 'function'; end

-- Sizes are laid out for the usual 13 px font. With a bigger game font (Ashita font scale, high-DPI setups) every fixed width
-- and height grows with it, so labels and card rows are not cut off (1.12).
-- (1.16) /menu scale <0.75-3>: our windows (the Squads button, the menu, the mate sheets) drawn bigger or smaller,
-- for 4K screens where the window and menu resolutions must match (Senna). Only our windows; XIUI has its own.
local function userScale()
    local v = tonumber(S.cfg.scale or '1') or 1;
    return math.max(0.75, math.min(3, v));
end

local function px(n)
    if type(n) ~= 'number' or n <= 0 then return n; end
    local us = userScale();
    local size = has('GetFontSize') and imgui.GetFontSize() or 13;
    if S.scaledNow and type(size) == 'number' then size = size / us; end   -- (inside our window the font is scaled already)
    local scale = (type(size) == 'number' and size > 0) and math.max(1, math.min(3, size / 13)) or 1;
    return math.floor(n * scale * us + 0.5);
end

local function scaleWindow()
    if has('SetWindowFontScale') then imgui.SetWindowFontScale(userScale()); S.scaledNow = true; end
end
local function G(name) return rawget(_G, name); end

local function colorText(color, text)
    if has('TextColored') then imgui.TextColored(color, text); else imgui.Text(text); end
end

local function dimText(text) colorText(C.dim, text); end

local function wrapped(text, color)
    if color and has('PushStyleColor') and G('ImGuiCol_Text') then
        imgui.PushStyleColor(G('ImGuiCol_Text'), color);
        imgui.TextWrapped(text);
        imgui.PopStyleColor(1);
    else
        imgui.TextWrapped(text);
    end
end

local function tooltip(text)
    if has('IsItemHovered') and imgui.IsItemHovered() and has('SetTooltip') then imgui.SetTooltip(text); end
end

local function pushColors(list)
    local n = 0;
    for _, pair in ipairs(list) do
        local id = G(pair[1]);
        if id ~= nil then imgui.PushStyleColor(id, pair[2]); n = n + 1; end
    end
    return n;
end

local function pushVars(list)
    local n = 0;
    if not has('PushStyleVar') then return 0; end
    for _, pair in ipairs(list) do
        local id = G(pair[1]);
        if id ~= nil then imgui.PushStyleVar(id, pair[2]); n = n + 1; end
    end
    return n;
end

-- a button that can look selected (gold) or switched on (green)
local function button(label, id, w, h, look)
    local n = 0;
    if look == 'selected' then n = pushColors({ { 'ImGuiCol_Button', C.sel }, { 'ImGuiCol_ButtonHovered', C.selHi }, { 'ImGuiCol_ButtonActive', C.selHi } });
    elseif look == 'on' then n = pushColors({ { 'ImGuiCol_Button', C.on }, { 'ImGuiCol_ButtonHovered', C.onHi }, { 'ImGuiCol_ButtonActive', C.onHi } }); end
    local clicked = imgui.Button(label .. '##' .. id, { px(w or 0), px(h or 0) });
    if n > 0 then imgui.PopStyleColor(n); end
    return clicked;
end

-- a drop-down list; falls back to a row of buttons when this ImGui has no combo boxes
local function combo(id, current, items, width, help)
    local chosen = nil;
    if has('BeginCombo') and has('Selectable') and has('EndCombo') then
        if has('PushItemWidth') then imgui.PushItemWidth(px(width)); end
        if imgui.BeginCombo('##' .. id, current or '?') then
            for _, item in ipairs(items) do
                if imgui.Selectable(item .. '##' .. id .. item, item == current) then chosen = item; end
                if help and help[item] then tooltip(help[item]); end
            end
            imgui.EndCombo();
        end
        if has('PopItemWidth') then imgui.PopItemWidth(); end
        if help and help[current] then tooltip(help[current]); end
    else
        for i, item in ipairs(items) do
            if i > 1 then imgui.SameLine(0, 3); end
            if button(item, id .. item, 0, 0, item == current and 'selected' or nil) then chosen = item; end
        end
    end
    if chosen == current then chosen = nil; end
    return chosen;
end

local function bar(fraction, color, overlay, width)
    fraction = math.max(0, math.min(1, fraction or 0));
    if has('ProgressBar') then
        local n = pushColors({ { 'ImGuiCol_PlotHistogram', color } });
        imgui.ProgressBar(fraction, { px(width), px(20) }, overlay);
        if n > 0 then imgui.PopStyleColor(n); end
    else
        imgui.Text(overlay);
    end
end

local function beginChild(id, w, h, border, noScroll)
    if not has('BeginChild') then return true, false; end
    local flags = border and (G('ImGuiChildFlags_Borders') or G('ImGuiChildFlags_Border') or true) or 0;
    if noScroll then
        local wflags = (G('ImGuiWindowFlags_NoScrollbar') or 0) + (G('ImGuiWindowFlags_NoScrollWithMouse') or 0);
        return imgui.BeginChild(id, { px(w), px(h) }, flags, wflags), true;
    end
    return imgui.BeginChild(id, { px(w), px(h) }, flags), true;
end

local function endChild(began) if began and has('EndChild') then imgui.EndChild(); end end

local function heading(text)
    colorText(C.gold, text);
end

local function gap(px)
    if has('Dummy') then imgui.Dummy({ 0, px or 4 }); end
end

-- ---------------------------------------------------------------- Squad tab
local function campRow()
    local camp = S.camp;
    if camp == nil then return; end
    gap(2);
    colorText(C.gold, 'Camp'); imgui.SameLine(0, 10);
    if button(camp.on and 'Move camp here' or 'Set camp here', 'campset', 124, 0, camp.on and 'on' or nil) then
        campCommand('camp'); camp.on = true;
    end
    tooltip('Your squad holds this spot and fights whatever comes within 20 yalms of it');
    if camp.on then
        imgui.SameLine(0, 6);
        if button('Camp off', 'campoff', 84, 0) then campCommand('camp off'); camp.on = false; end
        tooltip('They follow you again');
    end
    imgui.SameLine(0, 14);
    dimText('Puller'); imgui.SameLine(0, 8);
    local names, current = { 'You' }, 'You';
    local tips = { You = 'You pull: bring monsters back to camp and the squad joins in' };
    for _, mate in ipairs(S.mates) do
        if mate.out then
            names[#names + 1] = mate.name;
            if mate.slot == camp.puller then current = mate.name; end
        end
    end
    -- (1.17) the bot players in your party hold the camp too, and one of them can pull
    local botSet = {};
    for _, b in ipairs(camp.bots or {}) do
        names[#names + 1] = b; botSet[b] = true;
        tips[b] = b .. ' (bot player) pulls';
        if camp.botPuller == b then current = b; end
    end
    local pick = combo('camppuller', current, names, 110, tips);
    if pick then
        if pick == 'You' then
            campCommand('pull me'); camp.puller = 0; camp.botPuller = nil;
        elseif botSet[pick] then
            campCommand('pull ' .. pick); camp.puller = 0; camp.botPuller = pick;
        else
            for _, mate in ipairs(S.mates) do
                if mate.name == pick then campCommand('pull ' .. mate.slot); camp.puller = mate.slot; camp.botPuller = nil; end
            end
        end
        camp.on = true;
    end
    local someonePulls = camp.puller ~= 0 or camp.botPuller ~= nil;
    if camp.on and someonePulls then
        imgui.SameLine(0, 6);
        if button(camp.paused and 'Resume' or 'Pause', 'camppause', 72, 0, camp.paused and 'selected' or nil) then
            campCommand(camp.paused and 'camp resume' or 'camp pause'); camp.paused = not camp.paused;
        end
        tooltip(camp.paused and 'The puller goes back to pulling' or 'No new pulls (the squad still holds camp)');
    end
    if camp.on then
        imgui.SameLine(0, 12);
        dimText(camp.pulls == 1 and '1 pull' or (tostring(camp.pulls or 0) .. ' pulls'));
    end
    -- what the mate pulls: any number of kinds of monster around the camp, each one toggles
    if camp.on and someonePulls and camp.kinds then
        dimText('Pull'); imgui.SameLine(0, 8);
        local wants = camp.wants or {};
        local any = true;
        for _ in pairs(wants) do any = false; end
        if button('Anything', 'campany', 82, 0, any and 'selected' or nil) then
            campCommand('camp want any');
            camp.wants, camp.want = {}, nil;
        end
        tooltip('Whatever is a good level for you, nearest first');
        for _, k in ipairs(camp.kinds) do
            if k.fits then
                local key = k.name:lower():gsub('_', ' ');
                local label = string.format('%s lv%d%s x%d', (k.name:gsub('_', ' ')), k.lo, k.hi ~= k.lo and ('-' .. k.hi) or '', k.count);
                imgui.SameLine(0, 6);
                if button(label, 'campkind' .. k.name, 0, 0, wants[key] and 'selected' or nil) then
                    campCommand('camp want ' .. k.name);
                    wants[key] = (not wants[key]) and true or nil;
                    camp.wants = wants;
                    camp.want = next(wants) and 'picked' or nil;
                end
                tooltip(k.fits and 'Pick any number of kinds: click again to drop one' or 'Too strong for you');
            end
        end
    end
end

-- ---------------------------------------------------------------- the Style row (range, weapon skills) and body size
local RANGES = { 'auto', 'melee', 'mid', 'far' };
local RANGE_HELP = {
    auto  = 'The usual distance for its job (casters and ranged jobs stand back, the rest melee)',
    melee = 'Stands next to the monster',
    mid   = 'Stands about 6 yalms from the monster',
    far   = 'Stands about 12 yalms from the monster',
};
local WS_WHEN = { 'chain', '1000', '1500', '2000', '2500', '3000' };
local WS_WHEN_HELP = {
    chain  = 'Times its weapon skills to skillchain with the party (the default)',
    ['1000'] = 'Weapon skills as soon as it has 1000 TP',
    ['1500'] = 'Waits for 1500 TP',
    ['2000'] = 'Waits for 2000 TP',
    ['2500'] = 'Waits for 2500 TP',
    ['3000'] = 'Waits for 3000 TP (strongest hits, fewest of them)',
};
local SIZES = { 'small', 'medium', 'large' };

local function wsKey(name) return tostring(name or ''):lower():gsub('[^%w]', ''); end

-- !squad ws <slot> <when> <which>: the server wants both, so the part not being changed is sent as it is now
local function setWs(mate, opt, when, which)
    when = when or ((opt.tp or 0) > 0 and tostring(opt.tp) or 'chain');
    which = which or opt.ws or 'best';
    changeMate(mate, 'ws', when .. ' ' .. (which == 'best' and 'best' or which:gsub(' ', '_')));
    opt.tp = when == 'chain' and 0 or tonumber(when);
    opt.ws = which ~= 'best' and which or nil;
end

local function styleRow(mate, opt)
    dimText('Range'); imgui.SameLine(0, 8);
    local range = combo('range' .. mate.slot, RANGES[(opt.range or 0) + 1], RANGES, 90, RANGE_HELP);
    if range then
        changeMate(mate, 'range', range);
        for i, r in ipairs(RANGES) do if r == range then opt.range = i - 1; end end
    end
    imgui.SameLine(0, 18);
    dimText('WS at'); imgui.SameLine(0, 8);
    local when = combo('wswhen' .. mate.slot, (opt.tp or 0) > 0 and tostring(opt.tp) or 'chain', WS_WHEN, 80, WS_WHEN_HELP);
    if when then setWs(mate, opt, when, nil); end
    imgui.SameLine(0, 10);
    local items, current = { 'best' }, 'best';
    for _, name in ipairs(opt.list or {}) do
        items[#items + 1] = name;
        if opt.ws and wsKey(name) == wsKey(opt.ws) then current = name; end
    end
    if opt.ws and current == 'best' then items[#items + 1] = opt.ws; current = opt.ws; end
    local which = combo('wswhich' .. mate.slot, current, items, 150);
    if which then setWs(mate, opt, nil, which); end
    tooltip(#(opt.list or {}) > 0 and 'Which weapon skill it uses: "best" picks its strongest one'
        or 'Which weapon skill it uses. Call this mate to see the ones it can use now.');
end

-- body size: picked once, like at character creation
local function sizeRow(mate, opt)
    dimText('Size'); imgui.SameLine(0, 8);
    S.sizePick = S.sizePick or {};
    local pick = combo('size' .. mate.slot, S.sizePick[mate.slot] or 'medium', SIZES, 100);
    if pick then S.sizePick[mate.slot] = pick; end
    imgui.SameLine(0, 10);
    if button('Set for good', 'setsize' .. mate.slot, 100, 0) then
        changeMate(mate, 'size', S.sizePick[mate.slot] or 'medium');
        opt.size = ({ small = 1, medium = 2, large = 3 })[S.sizePick[mate.slot] or 'medium'];
    end
    tooltip('His body size. It can be set only once, so pick carefully.');
end

-- ---------------------------------------------------------------- Advanced (follow distance, camp rest, call order, engage delay)
local FOLLOWS = { 'close', 'normal', 'far' };
local FOLLOW_HELP = {
    close  = 'Mates stay right behind you',
    normal = 'The usual distance',
    far    = 'Mates follow from further back (handy in narrow tunnels and when you pull)',
};
local FOLLOW_OF = { [0] = 'normal', [1] = 'close', [2] = 'far' };
local DELAYS = { '0', '1', '2', '3', '4', '5', '6', '8', '10' };

-- the mates in "call all" order (the server's order digits; slots it doesn't list come after, in slot order)
local function orderedMates()
    local rank = {};
    local i = 0;
    for d in tostring((S.adv and S.adv.order) or ''):gmatch('%d') do
        i = i + 1;
        rank[tonumber(d)] = rank[tonumber(d)] or i;
    end
    local list = {};
    for k, mate in ipairs(S.mates) do list[k] = mate; end
    table.sort(list, function(a, b) return (rank[a.slot] or (100 + a.slot)) < (rank[b.slot] or (100 + b.slot)); end);
    return list;
end

local function advancedPanel()
    local adv = S.adv;
    local open, began = beginChild('##sm_advanced', 0, adv.pull and 118 or 92, true, true);
    if open then
        dimText('Follow'); imgui.SameLine(0, 8);
        local follow = combo('advfollow', FOLLOW_OF[adv.follow] or 'normal', FOLLOWS, 100, FOLLOW_HELP);
        if follow then
            enqueue('/say !squad follow ' .. follow);
            for k, v in pairs(FOLLOW_OF) do if v == follow then adv.follow = k; end end
            ask(1.5);
        end
        imgui.SameLine(0, 18);
        if button(adv.rest and 'Rest at camp: on' or 'Rest at camp: off', 'advrest', 140, 0, adv.rest and 'on' or nil) then
            enqueue('/say !squad camp rest ' .. (adv.rest and 'off' or 'on'));
            adv.rest = not adv.rest;
            ask(1.5);
        end
        tooltip('With a camp set, mates sit and rest between fights while the pull is out');

        if adv.pull then                         -- (1.14) the monster levels the camp puller goes for, against yours
            gap(2);
            dimText('Pull levels'); imgui.SameLine(0, 8);
            local lowItems, highItems = {}, {};
            for v = -30, 0 do lowItems[#lowItems + 1] = string.format('%+d', v); end
            for v = -10, 10 do highItems[#highItems + 1] = string.format('%+d', v); end
            local low = combo('advplow', string.format('%+d', adv.pull.low), lowItems, 60);
            imgui.SameLine(0, 6); dimText('to'); imgui.SameLine(0, 6);
            local high = combo('advphigh', string.format('%+d', adv.pull.high), highItems, 60);
            if low or high then
                local l, h = tonumber(low or adv.pull.low), tonumber(high or adv.pull.high);
                if l > h then if low then h = l; else l = h; end end
                enqueue(string.format('/say !squad camp levels %d %d', l, h));
                adv.pull.low, adv.pull.high, adv.pull.own = l, h, true;
                ask(1.5);
            end
            tooltip('Levels below / above yours the camp puller brings back (default -6 to +2)');
            imgui.SameLine(0, 10);
            if adv.pull.own and button('Default', 'advplreset', 64, 0) then
                enqueue('/say !squad camp levels reset');
                adv.pull.low, adv.pull.high, adv.pull.own = -6, 2, false;
                ask(1.5);
            end
        end

        gap(2);
        dimText('Call order'); imgui.SameLine(0, 8);
        local list = orderedMates();
        for i, mate in ipairs(list) do
            if i > 1 then
                imgui.SameLine(0, 4);
                if button('<', 'advup' .. mate.slot, 22, 0) then
                    list[i - 1], list[i] = list[i], list[i - 1];
                    local code = {};
                    for _, m in ipairs(list) do code[#code + 1] = tostring(m.slot); end
                    enqueue('/say !squad order ' .. table.concat(code, ','));
                    adv.order = table.concat(code, '');
                    ask(1.5);
                end
                tooltip('Move ' .. mate.name .. ' earlier');
                imgui.SameLine(0, 4);
            end
            colorText(C.text, mate.name);
        end
        imgui.SameLine(0, 12);
        if button('Reset', 'advorderreset', 56, 0) then
            enqueue('/say !squad order reset');
            adv.order = nil;
            ask(1.5);
        end
        tooltip('"Call all" brings them out in slot order again');
        dimText('Each mate\'s "Wait" (on its card) is how many seconds it holds back when a fight starts, so the tank gets hate first.');
    end
    endChild(began);
    gap(2);
end

local function squadTab()
    if button('Call all', 'callall', 92, 26) then enqueue('/say !squad call all'); ask(3); end
    tooltip('Bring every squad mate out, one after another');
    imgui.SameLine(0, 6);
    if button('Dismiss all', 'dismiss', 112, 26) then enqueue('/say !squad dismiss'); ask(1.5); end
    imgui.SameLine(0, 6);
    if button('Refresh', 'refresh', 80, 26) then ask(); end
    if S.engage then
        imgui.SameLine(0, 6);
        local first = S.engage == 'first';
        if button(first and 'Engage: first' or 'Engage: with you', 'engage', 136, 26, first and 'on' or nil) then
            enqueue('/say !squad engage ' .. (first and 'normal' or 'first'));
            S.engage = first and 'normal' or 'first';
            ask(1.5);
        end
        tooltip(first and 'Your mates attack a monster as soon as you or any of them is fighting it (click: wait for you)'
            or 'Your mates attack when you do (click: they may start the fight before you swing)');
    end
    if S.autoEquip ~= nil then
        imgui.SameLine(0, 6);
        local on = S.autoEquip == true;
        if button(on and 'Auto-equip: on' or 'Auto-equip: off', 'autoequip', 128, 26, on and 'on' or nil) then
            enqueue('/say !squad autoequip ' .. (on and 'off' or 'on'));
            S.autoEquip = not on;
            ask(1.5);
        end
        tooltip(on and 'Your mates wear the best gear you gave the squad, picked again each time they are called (click: choose by hand)'
            or 'Click: every mate puts on the best gear you gave the squad for its job and level. Turn it off again to fine-tune by hand.');
    end
    if S.adv then
        imgui.SameLine(0, 6);
        if button('Advanced', 'advanced', 92, 26, S.showAdvanced and 'selected' or nil) then S.showAdvanced = not S.showAdvanced; end
        tooltip('Follow distance, resting at camp, call order and each mate\'s wait before fighting');
    end
    imgui.SameLine(0, 14);
    dimText(#S.mates == 1 and '1 mate' or (#S.mates .. ' mates'));
    if S.adv and S.showAdvanced then
        gap(2);
        advancedPanel();
    end

    if S.pendingApply then
        gap(2);
        colorText(C.warn, 'Changes take effect when your mates are called again.');
        imgui.SameLine(0, 10);
        if button('Apply now', 'apply', 96, 0, 'selected') then applyNow(); end
        tooltip('Dismisses the squad and calls everyone again');
    end
    campRow();
    gap(4);

    local open, began = beginChild('##sm_squadlist', 0, -2, false);
    if open then
        if #S.mates == 0 then
            gap(20);
            dimText(now() < S.waitUntil and '   Asking the server...' or '   No squad mates yet (or no answer yet). Press Refresh.');
            dimText('   Make one in chat:  !squad new Bob WAR');
        end
        for _, mate in ipairs(S.mates) do
            local opt = S.opts and S.opts[mate.slot];
            local height = S.more[mate.slot] and 128 or 88;
            if opt then height = height + 26 + ((S.more[mate.slot] and opt.size == 0) and 26 or 0); end
            local waitSecs = S.showAdvanced and S.adv and S.adv.delay[mate.slot];
            if waitSecs then height = height + 26; end
            local cardOpen, cardBegan = beginChild('##sm_mate' .. mate.slot, 0, height, true, true);
            if cardOpen then
                colorText(C.gold, mate.name);
                imgui.SameLine(0, 10);
                local jobs = string.format('%s %d', mate.main, mate.mainLevel);
                if mate.sub ~= '-' then jobs = jobs .. string.format(' / %s %d', mate.sub, mate.subLevel); end
                colorText(C.text, jobs);
                imgui.SameLine(0, 12);
                colorText(mate.out and C.good or C.dim, mate.out and 'out' or 'away');
                imgui.SameLine(0, 12);
                local wait = S.readyAt and S.readyAt[mate.slot] and (S.readyAt[mate.slot] - os.time()) or 0;
                if not mate.out then
                    if wait > 0 then
                        colorText(C.dim, string.format('ready in %d:%02d', math.floor(wait / 60), wait % 60));
                        tooltip('The call timer: this mate can be called again then (the launcher\'s Rates tab sets how long)');
                    elseif button('Call', 'call' .. mate.slot, 56, 0) then enqueue('/say !squad call ' .. mate.slot); ask(3); end
                    imgui.SameLine(0, 6);
                else
                    -- (1.13) out: send just this one off, and how long before a dismiss and call works straight away
                    if button('Dismiss', 'dismiss' .. mate.slot, 70, 0) then enqueue('/say !squad dismiss ' .. mate.slot); ask(1.5); end
                    tooltip('Sends only this mate off; the others stay');
                    imgui.SameLine(0, 6);
                    if wait > 0 then
                        colorText(C.dim, string.format('recall in %d:%02d', math.floor(wait / 60), wait % 60));
                        tooltip('If you dismiss this mate now, the call timer lets you call them again after this');
                        imgui.SameLine(0, 6);
                    end
                end
                if button(S.more[mate.slot] and 'Less' or 'Jobs', 'more' .. mate.slot, 56, 0) then S.more[mate.slot] = not S.more[mate.slot]; end
                tooltip('Change this mate\'s main and support job');
                imgui.SameLine(0, 6);
                if button('Profile', 'sheet' .. mate.slot, 64, 0) then openSheet(mate.slot); end
                tooltip('Opens his profile window: stats, HP/MP/TP, haste, jobs and equipment');

                gap(2);
                dimText('Role'); imgui.SameLine(0, 8);
                local role = combo('role' .. mate.slot, mate.role, ROLES, 120, ROLE_HELP);
                if role then changeMate(mate, 'role', role); end
                imgui.SameLine(0, 18);
                dimText('Mode'); imgui.SameLine(0, 8);
                local mode = combo('mode' .. mate.slot, mate.mode, MODES, 120, MODE_HELP);
                if mode then changeMate(mate, 'mode', mode); end
                if opt then
                    gap(2);
                    styleRow(mate, opt);
                end
                if waitSecs then
                    gap(2);
                    dimText('Wait '); imgui.SameLine(0, 8);
                    local w = combo('wait' .. mate.slot, tostring(waitSecs), DELAYS, 70);
                    if w then
                        changeMate(mate, 'delay', w);
                        S.adv.delay[mate.slot] = tonumber(w);
                    end
                    imgui.SameLine(0, 8);
                    dimText('seconds before joining a fight');
                end

                if S.more[mate.slot] then
                    gap(2);
                    dimText('Job '); imgui.SameLine(0, 8);
                    local job = combo('job' .. mate.slot, mate.main, JOBS, 120);
                    if job then changeMate(mate, 'job', job); end
                    imgui.SameLine(0, 18);
                    dimText('Sub '); imgui.SameLine(0, 8);
                    local subs = { 'none' };
                    for _, j in ipairs(JOBS) do if j ~= mate.main then subs[#subs + 1] = j; end end
                    local sub = combo('sub' .. mate.slot, mate.sub == '-' and 'none' or mate.sub, subs, 120);
                    if sub then changeMate(mate, 'sub', sub); end
                    dimText('A job your character has not unlocked is refused by the server (it says so in chat).');
                    if opt and opt.size == 0 then
                        gap(2);
                        sizeRow(mate, opt);
                    end
                end
            end
            endChild(cardBegan);
            gap(2);
        end
    end
    endChild(began);
end

-- ---------------------------------------------------------------- Dualbox tab
local function notRunning()
    gap(30);
    colorText(C.text, '   Your second character is not running.');
    dimText('   Press DUALBOX in the launcher. The second window needs the followme addon (0.8 or newer).');
end

local gambitsPanel;
local fit;                       -- defined with the sheet helpers below; the gambit rows use it too

local function dualboxTab()
    local duo = S.duo;
    if not duo then notRunning(); return; end

    local open, began = beginChild('##sm_duocard', 0, 108, true, true);
    if open then
        colorText(C.gold, duo.name or '?');
        imgui.SameLine(0, 10);
        local jobs = string.format('%s %s', duo.job or '?', duo.level or '?');
        if duo.sub and duo.sub ~= 'NON' and duo.sub ~= '' then jobs = jobs .. string.format(' / %s %s', duo.sub, duo.sublevel or '?'); end
        colorText(C.text, jobs);
        imgui.SameLine(0, 12);
        dimText('TP ' .. tostring(duo.tp or '?'));
        gap(2);
        local hp, mp = tonumber(duo.hp) or 0, tonumber(duo.mp) or 0;
        bar(hp / 100, C.hp, 'HP ' .. hp .. '%', 250);
        imgui.SameLine(0, 10);
        bar(mp / 100, C.mp, 'MP ' .. mp .. '%', 250);
        gap(2);
        dimText('Doing: ' .. tostring(duo.follow or ''));
    end
    endChild(began);
    gap(6);

    local on = duo.auto == 'on';
    if button(on and 'AUTO  ON' or 'AUTO  OFF', 'duoauto', 130, 34, on and 'on' or nil) then
        queueDuo({ auto = on and 'off' or 'on' });
        duo.auto = on and 'off' or 'on';
    end
    tooltip('Follow, assist and attack with you, and run his gambits');
    imgui.SameLine(0, 16);
    if has('BeginGroup') then imgui.BeginGroup(); end
    dimText('Profile');
    for i, role in ipairs(ROLES) do
        if i > 1 then imgui.SameLine(0, 4); end
        if button(role, 'duoprofile' .. role, 74, 0, duo.profile == role and 'selected' or nil) then
            queueDuo({ profile = role });
            duo.profile = role;
        end
        tooltip(ROLE_HELP[role]);
    end
    if has('EndGroup') then imgui.EndGroup(); end
    gap(8);

    -- casting on unclaimed targets is always on (no switch): if it was ever turned off, it is turned back on
    if duo.unclaimed == 'off' and not S.unclaimedFixed then
        S.unclaimedFixed = true;
        queueDuo({ unclaimed = 'on' });
    end
    if has('Separator') then imgui.Separator(); end
    dimText('Gambit engine: ' .. ((duo.master and duo.master ~= '') and duo.master or '?') .. '     ' .. ((duo.gate and duo.gate ~= '') and duo.gate or ''));
    if duo.last and duo.last ~= '' then dimText('Last action: ' .. duo.last); end

    gap(6);
    if button(S.duoGambits and 'Hide gambits' or 'Gambits', 'duogambits', 120, 26, S.duoGambits and 'selected' or nil) then
        S.duoGambits = not S.duoGambits;
        if S.duoGambits then readSheet(now()); end
    end
    tooltip('His current job\'s gambit rows; this is the dualbox character, not your squad');
    imgui.SameLine(0, 10);
    dimText(S.duoGambits and ((S.sheet and (#S.sheet.rows .. ' rows')) or 'loading...') or '');
    if S.duoGambits then
        gap(6);
        gambitsPanel(170);
    end
end

-- ---------------------------------------------------------------- Gambits panel (inside Dualbox)
gambitsPanel = function(height)
    local duo = S.duo;
    if not duo then notRunning(); return; end
    local old = duoVersion() < 0.009;

    colorText(C.gold, (duo.name or '?') .. '  -  ' .. (duo.job or '?') .. ' gambits');
    imgui.SameLine(0, 14);
    dimText('profile');
    imgui.SameLine(0, 4);
    colorText(C.text, tostring(duo.profile or '?'));
    imgui.SameLine(0, 14);
    colorText(duo.master == 'ON' and C.good or C.dim, 'engine ' .. ((duo.master and duo.master ~= '') and duo.master or '?'));
    dimText('Tick a row to use it, untick to skip it. Order is priority: the first row that can act, acts.');
    if old then colorText(C.warn, 'The second window has an older followme addon: run install_servermenu.py to switch single rows here.'); end
    if duo.sheet == 'japanese' then
        colorText(C.bad, 'These rows were made while the game language was Japanese; the engine cannot find them. Press Reset rows.');
    end
    gap(4);

    local sheet = S.sheet;
    local open, began = beginChild('##sm_rows', 0, height or 240, true);
    if open then
        if not sheet then
            gap(16);
            dimText('   His gambit sheet ' .. (S.sheetError or 'is not loaded yet') .. '.');
            if S.sheetPath then dimText('   ' .. S.sheetPath); end
        else
            for position, row in ipairs(sheet.rows) do
                if not row.empty then
                    local enabled = rowEnabled(row);
                    dimText(string.format('%2d', position));
                    imgui.SameLine(0, 8);
                    local box = { enabled };
                    local name = rowName(row);
                    local label = fit(name, 246);
                    if has('Checkbox') then
                        if imgui.Checkbox(label .. '##row' .. row.id .. position, box) and not old then setRow(row, box[1]); end
                    else
                        if button((enabled and '[x] ' or '[ ] ') .. label, 'row' .. row.id .. position, 0, 0) and not old then setRow(row, not enabled); end
                    end
                    local help = name;
                    if type(row.actions) == 'table' and #row.actions > 0 then help = help .. '  -  ' .. table.concat(row.actions, ', '); end
                    tooltip(help);
                    local layer = LAYERS[row.layer or ''];
                    imgui.SameLine(px(330), 0);
                    colorText(layer and layer[2] or C.dim, layer and layer[1] or tostring(row.layer or ''));
                    imgui.SameLine(px(430), 0);
                    dimText(TARGETS[row.target or ''] or tostring(row.target or ''));
                    imgui.SameLine(px(530), 0);
                    if button('^', 'up' .. position, 22, 0) and not old then moveRow(position, -1); end
                    tooltip('Higher priority');
                    imgui.SameLine(0, 2);
                    if button('v', 'down' .. position, 22, 0) and not old then moveRow(position, 1); end
                    tooltip('Lower priority');
                end
            end
        end
    end
    endChild(began);

    if button('Reset rows', 'resetrows', 110, 26) then queueDuo({ reset = true }); end
    tooltip('Puts this job\'s rows back to the normal sheet (the engine keeps a .bak), then re-applies the profile');
    imgui.SameLine(0, 8);
    if button('Engine window', 'titanui', 120, 26) and not old then queueDuo({ ops = { 'titanui' } }); end
    tooltip('Shows or hides the gambit engine\'s own big window in the second game window');
    imgui.SameLine(0, 12);
    dimText(S.duoPending and 'sending...' or (S.sheet and (#S.sheet.rows .. ' rows') or ''));
end

-- ---------------------------------------------------------------- Diagnostics tab
local function resultLine(line)
    if line:sub(1, 5) == 'FAIL:' then wrapped('x  ' .. line:sub(7), C.bad);
    elseif line:sub(1, 3) == 'ok:' then wrapped('o  ' .. line:sub(5), C.good);
    elseif line:sub(1, 2) == '=>' then wrapped(line, C.gold);
    else wrapped(line, C.text); end
end

local function diagnosticsTab()
    local duo = S.duo;
    if not duo then notRunning(); return; end

    local open, began = beginChild('##sm_diag', 0, -2, false);
    if open then
        heading('What the engine says');
        wrapped('State: ' .. ((duo.gate and duo.gate ~= '') and duo.gate or 'not asked yet'), C.text);
        if duo.last and duo.last ~= '' then wrapped('Last action: ' .. duo.last, C.dim); end
        local any = false;
        for _, key in ipairs({ 'why1', 'why2', 'why3' }) do
            if duo[key] and duo[key] ~= '' then
                if not any then dimText('Not firing:'); any = true; end
                wrapped('   ' .. duo[key], C.warn);
            end
        end
        if duo.actions and duo.actions ~= '' then wrapped('Actions: ' .. duo.actions, C.dim); end
        if duo.buffs and duo.buffs ~= '' then wrapped('Status data from: ' .. duo.buffs, C.dim); end
        gap(8);

        heading('Can he cast it?');
        dimText('Press Check during a fight: it tests, one by one, what he needs before he can cast.');
        if has('InputText') then
            if has('PushItemWidth') then imgui.PushItemWidth(px(180)); end
            imgui.InputText('##sm_spell', S.spell, 32);
            if has('PopItemWidth') then imgui.PopItemWidth(); end
            imgui.SameLine(0, 6);
        end
        if button('Check', 'probe', 80, 0) then
            local spell = tostring(S.spell[1] or ''):gsub('[^%w%s\'%-]', ''):gsub('^%s+', ''):gsub('%s+$', '');
            if spell == '' then spell = 'Dia'; end
            setCfg('spell', spell);
            queueDuo({ probe = spell });
        end
        for i = 1, 18 do
            local line = duo['probe' .. i];
            if line and line ~= '' then resultLine(line); end
        end
        gap(8);

        local stamp = tonumber(duo.fightat);
        local age = stamp and math.max(0, os.time() - stamp) or nil;
        local title = 'Last fight' .. (age and (' (' .. age .. ' s ago)') or '') .. '##sm_lastfight';
        local show = true;
        if has('CollapsingHeader') then show = imgui.CollapsingHeader(title); else heading('Last fight'); end
        if show then
            if duo.fight1 and duo.fight1 ~= '' then
                for i = 1, 10 do
                    local line = duo['fight' .. i];
                    if line and line ~= '' then resultLine(line); end
                end
            else
                dimText('No fight recorded yet. It is taken automatically while he is engaged.');
            end
        end
    end
    endChild(began);
end

-- ---------------------------------------------------------------- my own auto (AutoBot, the addon the second window uses)
local function myAutoOn()
    return tostring(S.cfg.auto_me) == 'true';
end

-- AutoBot reads this file before it rests anyone. Written on every toggle and
-- forced to "off" at addon load, so resting is never on by accident.
local function auto_flag_character()
    local ok, name =
        pcall(function()
            return AshitaCore:GetMemoryManager():GetParty():GetMemberName(0)
        end)

    name = ok and tostring(name or '') or ''
    name = name:match('^%s*(.-)%s*$') or ''

    if name == '' then
        return 'default'
    end

    return (name:gsub('[^%w_]', '_'))
end

local function writeAutoFlag(on)
    pcall(function()
        local base = tostring(AshitaCore:GetInstallPath());

        if base:sub(-1) == '/' then
            base = base:sub(1, -2);
        end

        local value = on and 'on' or 'off';

        -- Write the character file and the fallback, so a moment where the
        -- character name cannot be read can never disagree with the button.
        for _, name in ipairs({ auto_flag_character(), 'default' }) do
            local file = io.open(base .. '/config/addons/AutoBot/auto_mode_' .. name .. '.flag', 'w');

            if file then
                file:write(value);
                file:close();
            end
        end
    end);
end


-- The menu is loaded at the character-select screen, where the party name cannot
-- be read: the load-time "off" then lands only in the default file and this
-- character's own file keeps an old "on" that AutoBot would believe. Once the
-- character exists, mirror the button into their own file too.
local auto_flag_synced = nil
local auto_flag_next_check = 0

local function syncAutoFlag()
    local now = os.clock()

    if now < auto_flag_next_check then
        return
    end

    auto_flag_next_check = now + 1.0

    local name = auto_flag_character()

    if name == 'default' then
        auto_flag_synced = nil
        return
    end

    if name == auto_flag_synced then
        return
    end

    auto_flag_synced = name

    local okBase, base = pcall(function()
        return tostring(AshitaCore:GetInstallPath())
    end)

    if not okBase or not base then
        return
    end

    if base:sub(-1) == '/' then
        base = base:sub(1, -2)
    end

    local probe = io.open(base .. '/config/addons/AutoBot/auto_mode_' .. name .. '.flag', 'r')

    -- A character that never pressed the button has no file and is not ours to
    -- switch off: the second window's job sheet keeps running.
    if not probe then
        return
    end

    probe:close()

    if not myAutoOn() then
        -- Gambits keeps its per-character master switch across sessions, and the
        -- startup script's /gambits off runs before a character exists, where it
        -- is refused. Send it again now that there is one.
        enqueue('/gambits off', 0.5)
        enqueue('/gambits off', 3.0)
    end

    writeAutoFlag(myAutoOn())
end

-- The job he is on right now. (Auto mode was written for MNK only: "/ab job MNK on" and the Weaponskill "Combo"
-- were sent whatever job you had changed to, so on any other job the job module and the Weaponskill were wrong.)
local AUTO_JOBS = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU', 'COR', 'PUP', 'DNC', 'SCH', 'GEO', 'RUN' };
local function myAutoJob()
    local ok, id = pcall(function ()
        return AshitaCore:GetMemoryManager():GetPlayer():GetMainJob();
    end);
    return (ok and AUTO_JOBS[tonumber(id) or 0]) or 'MNK';
end

local function setMyAuto(on)
    setCfg('auto_me', on and 'true' or 'false');
    writeAutoFlag(on);
    -- on: the job you are on now. off: the job auto was started on (you may have changed job since)
    local job = on and myAutoJob() or (S.autoJob or myAutoJob());
    S.autoJob = on and job or nil;
    if on then
        enqueue('/addon load autobot', 0.1);
        enqueue('/ab resume', 0.9);
        enqueue('/ab combat autoengage on', 1.1);
        enqueue('/ab combat approach on', 1.3);
        enqueue('/ab combat autoface on', 1.5);
        enqueue('/ab combat autotarget on', 1.7);
        -- Configured by command, not in the profile: AutoBot saves its own
        -- in-memory config on exit, so a hand-edited settings file is written
        -- back to its old values. These commands change memory and save it.
        -- Weaponskills belong to Gambits alone: its "Best Weapon Skill" row uses the strongest one you have learned
        -- for the weapon in your hand, on any job, and moves up as you learn more. AutoBot's own autows is one
        -- fixed skill (it was set to Combo here), so it is switched off instead of on.
        enqueue('/ab autows off', 2.0);
        enqueue('/ab hprest on', 2.4);
        enqueue('/ab job ' .. job .. ' on', 2.6);
        enqueue('/gambits on', 2.8);
        -- AutoBot's own addon load can still be finishing when the first pass
        -- runs, and a /ab sent to an addon that is not listening yet is simply
        -- lost. Send the two that matter again, later, then print what the
        -- modules actually believe so a silent miss is visible.
        enqueue('/ab autows off', 4.5);
        enqueue('/ab job ' .. job .. ' on', 4.8);
        enqueue('/ab hprest on', 5.0);
        enqueue('/ab autows status', 6.2);
        enqueue('/ab job ' .. job .. ' report', 6.6);
        ask(7.0);
    else
        enqueue('/gambits off');
        enqueue('/ab combat autotarget off', 0.2);
        enqueue('/ab combat autoengage off', 0.4);
        enqueue('/ab combat approach off', 0.6);
        enqueue('/ab combat autoface off', 0.8);
        enqueue('/ab autows off', 1.0);
        enqueue('/ab hprest off', 1.2);
        enqueue('/ab stopfollow', 1.4);
        enqueue('/ab job ' .. job .. ' off', 1.5);
        enqueue('/heal off', 1.6);
        enqueue('/addon unload autobot', 2.2);
        ask(2.8);
    end
end

local function autoTab()
    local on = myAutoOn();
    if button(on and 'MY AUTO  ON' or 'MY AUTO  OFF', 'myauto', 170, 34, on and 'on' or nil) then
        setMyAuto(not on);
    end
    tooltip('Gambits runs your job sheet: Weaponskills and abilities, the same sheet the second window uses');
    imgui.SameLine(0, 12);
    if button('Stop', 'myautostop', 80, 34) then
        setMyAuto(false);
    end
    tooltip('Gambits off, auto-attack off, stands you up if you were resting');
    gap(6);
    colorText(C.text, 'Same job sheet and rest rules as the second window.');
    dimText('On: attacks the target you picked, walks to it and faces it; Gambits then runs your job sheet.');
    dimText('While auto is on he rests below 35% HP or when party MP falls to 50%, and stands at 90%.');
    dimText('Your squad and the second window rest when you rest, so the healer only heals when you sit.');
    dimText('It does not follow anyone, so it never walks away from your camp.');
    gap(6);
    dimText('On loads AutoBot; off turns Gambits off, stands you up and unloads AutoBot entirely.');
    dimText('Nothing AutoBot owns - resting included - can run until you press the button.');
    gap(4);
    dimText('Your sheet: config/addons/Gambits/jobs/' .. myAutoJob() .. '.lua - the same file the second window reads.');
    dimText('Weaponskill: the best one you have learned for your weapon (the Best Weapon Skill row of your sheet).');
end

-- ---------------------------------------------------------------- the menu window
local TAB_DRAW = { Squad = squadTab, Dualbox = dualboxTab, Auto = autoTab, Diagnostics = diagnosticsTab };

local function setTab(name)
    if TAB_DRAW[name] then S.tab = name; setCfg('tab', name); end
end

local function setOpen(open)
    S.open[1] = open;
    if open then ask(); end
end

local function menuWindow()
    if not S.open[1] then return; end
    imgui.SetNextWindowSize({ px(620), px(560) }, G('ImGuiCond_FirstUseEver') or 4);
    if has('SetNextWindowSizeConstraints') then imgui.SetNextWindowSizeConstraints({ px(600), px(420) }, { px(1200), px(1000) }); end
    local vars = pushVars({ { 'ImGuiStyleVar_WindowRounding', 8 }, { 'ImGuiStyleVar_ChildRounding', 6 }, { 'ImGuiStyleVar_FrameRounding', 5 },
                            { 'ImGuiStyleVar_WindowPadding', { 14, 12 } }, { 'ImGuiStyleVar_ItemSpacing', { 8, 6 } }, { 'ImGuiStyleVar_FramePadding', { 8, 4 } } });
    local colors = pushColors({ { 'ImGuiCol_WindowBg', { 0.07, 0.08, 0.11, 0.96 } }, { 'ImGuiCol_ChildBg', { 0.10, 0.11, 0.15, 0.80 } },
                                { 'ImGuiCol_Border', { 0.32, 0.34, 0.42, 0.55 } }, { 'ImGuiCol_Button', { 0.17, 0.19, 0.25, 1 } },
                                { 'ImGuiCol_ButtonHovered', { 0.25, 0.28, 0.37, 1 } }, { 'ImGuiCol_ButtonActive', { 0.30, 0.34, 0.45, 1 } },
                                { 'ImGuiCol_FrameBg', { 0.14, 0.16, 0.21, 1 } }, { 'ImGuiCol_FrameBgHovered', { 0.20, 0.22, 0.29, 1 } },
                                { 'ImGuiCol_CheckMark', C.gold }, { 'ImGuiCol_Header', { 0.20, 0.22, 0.29, 1 } },
                                { 'ImGuiCol_HeaderHovered', { 0.26, 0.29, 0.38, 1 } }, { 'ImGuiCol_Separator', { 0.32, 0.34, 0.42, 0.55 } },
                                { 'ImGuiCol_Text', C.text } });
    local flags = (G('ImGuiWindowFlags_NoTitleBar') or 0) + (G('ImGuiWindowFlags_NoCollapse') or 0);
    if imgui.Begin('XI: Forever Offline##servermenu', S.open, flags) then
        scaleWindow();
        colorText(C.gold, 'SQUADS');
        imgui.SameLine(0, 8);
        dimText('XI: Forever Offline');
        if has('GetWindowWidth') then
            local w = imgui.GetWindowWidth();
            if type(w) == 'number' then imgui.SameLine(w - px(44), 0); else imgui.SameLine(0, 20); end
        else
            imgui.SameLine(0, 20);
        end
        if button('X', 'close', 26, 0) then S.open[1] = false; end
        tooltip('Close (the FFXI button or /menu opens it again)');
        gap(2);
        for i, name in ipairs(TABS) do
            if i > 1 then imgui.SameLine(0, 4); end
            if button(name, 'tab' .. name, 132, 30, S.tab == name and 'selected' or nil) then setTab(name); end
        end
        if has('Separator') then imgui.Separator(); end
        gap(2);
        local draw = TAB_DRAW[S.tab] or squadTab;
        draw();
    end
    S.scaledNow = false;
    imgui.End();
    if colors > 0 then imgui.PopStyleColor(colors); end
    if vars > 0 then imgui.PopStyleVar(vars); end
end

-- ---------------------------------------------------------------- the small FFXI button
local function xy(a, b)
    if type(a) == 'table' then return tonumber(a[1] or a.x), tonumber(a[2] or a.y); end
    return tonumber(a), tonumber(b);
end

local function buttonWindow()
    if S.cfg.button_hidden == 'true' then return; end
    local x, y = tonumber(S.cfg.button_x) or 18, tonumber(S.cfg.button_y) or 240;
    imgui.SetNextWindowPos({ x, y }, S.dragging and (G('ImGuiCond_Always') or 1) or (S.placeButton and (G('ImGuiCond_Always') or 1)) or (G('ImGuiCond_FirstUseEver') or 4));
    S.placeButton = false;
    local vars = pushVars({ { 'ImGuiStyleVar_WindowRounding', 7 }, { 'ImGuiStyleVar_WindowPadding', { 3, 3 } }, { 'ImGuiStyleVar_FrameRounding', 6 } });
    local colors = pushColors({ { 'ImGuiCol_WindowBg', { 0.05, 0.06, 0.09, 0.70 } }, { 'ImGuiCol_Border', { 0.89, 0.74, 0.40, 0.55 } },
                                { 'ImGuiCol_Button', { 0.13, 0.16, 0.26, 0.95 } }, { 'ImGuiCol_ButtonHovered', { 0.22, 0.27, 0.42, 1 } },
                                { 'ImGuiCol_ButtonActive', { 0.30, 0.36, 0.55, 1 } }, { 'ImGuiCol_Text', C.gold } });
    local flags = 0;
    for _, name in ipairs({ 'ImGuiWindowFlags_NoTitleBar', 'ImGuiWindowFlags_NoResize', 'ImGuiWindowFlags_NoScrollbar', 'ImGuiWindowFlags_NoCollapse',
                            'ImGuiWindowFlags_AlwaysAutoResize', 'ImGuiWindowFlags_NoSavedSettings', 'ImGuiWindowFlags_NoFocusOnAppearing' }) do
        flags = flags + (G(name) or 0);
    end
    if S.cfg.button_locked == 'true' then flags = flags + (G('ImGuiWindowFlags_NoMove') or 0); end
    if imgui.Begin('##servermenu_button', { true }, flags) then
        scaleWindow();
        local clicked = imgui.Button('Squads##sm_open', { px(76), px(30) });
        -- dragging the button moves it (unless locked); a drag is not a click
        if S.cfg.button_locked ~= 'true' and has('IsItemActive') and has('IsMouseDragging') and has('GetMouseDragDelta') then
            if imgui.IsItemActive() and imgui.IsMouseDragging(0, 3) then
                local dx, dy = xy(imgui.GetMouseDragDelta(0));
                if dx and dy then
                    if not S.dragging then S.dragging, S.dragFrom = true, { x, y }; end
                    setCfg('button_x', math.floor(S.dragFrom[1] + dx));
                    setCfg('button_y', math.floor(S.dragFrom[2] + dy));
                    S.dragMoved = true;
                end
            elseif S.dragging and not imgui.IsItemActive() then
                S.dragging = false;
            end
        end
        if clicked then
            if S.dragMoved then S.dragMoved = false; else setOpen(not S.open[1]); end
        elseif not S.dragging then
            S.dragMoved = false;
        end
        if not S.dragging then tooltip('Squads  (/menu)   drag to move, right-click for options'); end
        if has('BeginPopupContextItem') and imgui.BeginPopupContextItem('##sm_buttonmenu') then
            if has('MenuItem') then
                if imgui.MenuItem(S.cfg.button_locked == 'true' and 'Unlock position' or 'Lock position') then
                    setCfg('button_locked', S.cfg.button_locked == 'true' and 'false' or 'true');
                end
                if imgui.MenuItem('Hide button  (/menu button brings it back)') then
                    setCfg('button_hidden', 'true');
                    say('button hidden. /menu opens the menu, /menu button shows the button again.');
                end
            end
            imgui.EndPopup();
        end
        -- when ImGui moved the window by its edge, remember where it went
        if not S.dragging and has('GetWindowPos') then
            local wx, wy = xy(imgui.GetWindowPos());
            if wx and wy and (math.abs(wx - x) >= 1 or math.abs(wy - y) >= 1) then
                setCfg('button_x', math.floor(wx));
                setCfg('button_y', math.floor(wy));
            end
        end
    end
    S.scaledNow = false;
    imgui.End();
    if colors > 0 then imgui.PopStyleColor(colors); end
    if vars > 0 then imgui.PopStyleVar(vars); end
end

-- ---------------------------------------------------------------- the sheet window
local function number(value)
    if type(value) == 'table' then value = value[1] or value.x; end
    return tonumber(value) or 0;
end

local function contentWidth()
    if not (imgui and imgui.GetContentRegionAvail) then return 0; end
    local ok, value = pcall(imgui.GetContentRegionAvail);
    if not ok or value == nil then return 0; end
    return number(type(value) == 'table' and (value[1] or value.x) or value);
end

local function screenPos()
    if not (imgui and imgui.GetCursorScreenPos) then return nil; end
    local ok, value = pcall(imgui.GetCursorScreenPos);
    if not ok or value == nil then return nil; end
    if type(value) == 'table' then return { number(value[1] or value.x), number(value[2] or value.y) }; end
    return nil;
end

local function windowDraw()
    if not (imgui and imgui.GetWindowDrawList) then return nil; end
    local ok, draw = pcall(imgui.GetWindowDrawList);
    return ok and draw or nil;
end

local function fillColor(rgba)
    if type(rgba) ~= 'table' or not (imgui and imgui.ColorConvertFloat4ToU32) then return nil; end
    local ok, value = pcall(imgui.ColorConvertFloat4ToU32, rgba);
    return ok and value or nil;
end

local function fillRect(draw, x, y, width, height, rgba, rounding)
    if draw == nil or width <= 0 or height <= 0 then return false; end
    local color = fillColor(rgba);
    if color == nil then return false; end
    local ok = pcall(function () draw:AddRectFilled({ x, y }, { x + width, y + height }, color, rounding or 3); end);
    return ok;
end

local function seek(x, y)
    if imgui and imgui.SetCursorScreenPos then pcall(imgui.SetCursorScreenPos, { x, y }); end
end

local function textWidth(text)
    if not (imgui and imgui.CalcTextSize) then return nil; end
    local ok, value = pcall(imgui.CalcTextSize, tostring(text or ''));
    if not ok then return nil; end
    if type(value) == 'table' then return number(value[1] or value.x); end
    if type(value) == 'number' then return value; end
    return nil;
end

fit = function(text, maxWidth)
    text = tostring(text or '');
    if maxWidth == nil or maxWidth <= 0 then return ''; end
    local width = textWidth(text);
    if width == nil then
        local maxChars = math.max(4, math.floor(maxWidth / 6.5));
        if #text <= maxChars then return text; end
        return text:sub(1, maxChars - 3) .. '...';
    end
    if width <= maxWidth then return text; end
    for n = #text - 1, 1, -1 do
        local candidate = text:sub(1, n) .. '...';
        local candidateWidth = textWidth(candidate);
        if candidateWidth == nil or candidateWidth <= maxWidth then return candidate; end
    end
    return '...';
end

local function tint(rgba, text)
    if imgui and imgui.TextColored then
        imgui.TextColored(rgba, tostring(text));
    else
        imgui.Text(tostring(text));
    end
end

local function wrappedColored(rgba, text)
    local id = G('ImGuiCol_Text');
    local pushed = 0;
    if id ~= nil and imgui and imgui.PushStyleColor then
        local ok = pcall(imgui.PushStyleColor, id, rgba);
        if ok then pushed = 1; end
    end
    imgui.TextWrapped(tostring(text));
    if pushed > 0 and imgui and imgui.PopStyleColor then pcall(imgui.PopStyleColor, 1); end
end

local function newLine()
    if has('NewLine') then imgui.NewLine(); else imgui.Text(''); end
end

local itemIcons = {};
local itemIconTries = {};

local function itemIcon(itemId, itemName)
    -- Older server builds appended the item id to the name ("onion_dagger|15082").
    -- Read it from either place so the same icon lookup works on both.
    local name = itemName ~= nil and tostring(itemName) or nil;
    local embedded = name and name:match('|(%d+)$');
    if embedded ~= nil and (tonumber(itemId) or 0) <= 0 then
        itemId = tonumber(embedded);
    end
    if embedded ~= nil then name = name:gsub('|%d+$', ''); end

    local id = tonumber(itemId);
    if id ~= nil and id <= 0 then id = nil; end
    local key = id or (name ~= nil and name ~= '' and ('name:' .. name)) or nil;
    if key == nil or ffi == nil or d3d8 == nil then return nil; end
    local cached = itemIcons[key];
    if cached ~= nil and cached ~= false then return cached; end
    -- Do not hammer the game data every frame while a texture cannot be made; retry now and then.
    if cached == false and (os.time() - (itemIconTries[key] or 0)) < 10 then return nil; end

    local ok, texture = pcall(function ()
        local device = AshitaCore:GetDirect3DDevice();
        if d3d8 ~= nil and type(d3d8.get_device) == 'function' then
            local got, value = pcall(d3d8.get_device);
            if got and value ~= nil then device = value; end
        end
        if device == nil then return nil; end

        local resources = AshitaCore:GetResourceManager();
        local item = id and resources:GetItemById(id) or resources:GetItemByName(name, 0);
        if item == nil or item.Bitmap == nil or item.ImageSize == nil or item.ImageSize <= 0 then return nil; end

        local raw = ffi.new('IDirect3DTexture8*[1]');
        local result = ffi.C.D3DXCreateTextureFromFileInMemoryEx(
            ffi.cast('IDirect3DDevice8*', device), item.Bitmap, item.ImageSize,
            0xFFFFFFFF, 0xFFFFFFFF, 1, 0, ffi.C.D3DFMT_A8R8G8B8, ffi.C.D3DPOOL_MANAGED,
            ffi.C.D3DX_DEFAULT, ffi.C.D3DX_DEFAULT, 0xFF000000, nil, nil, raw);
        if result ~= 0 or raw[0] == nil then return nil; end

        local image = d3d8.gc_safe_release(ffi.cast('IDirect3DTexture8*', raw[0]));
        return { image = image, ptr = tonumber(ffi.cast('uint32_t', image)) };
    end);

    texture = ok and texture or nil;
    itemIcons[key] = texture or false;
    itemIconTries[key] = os.time();
    return texture;
end

local function emptySlot(name)
    return name == nil or name == '' or name == '-' or name == 'Empty';
end

local function itemDisplayName(itemId, name)
    local id = tonumber(itemId);
    if id and id > 0 and AshitaCore and type(AshitaCore.GetResourceManager) == 'function' then
        local ok, item = pcall(function () return AshitaCore:GetResourceManager():GetItemById(id); end);
        if ok and item and item.Name and item.Name[1] and item.Name[1] ~= '' then return tostring(item.Name[1]); end
    end
    local text = tostring(name or ''):gsub('|%d+$', ''):gsub('_', ' ');
    text = text:gsub('(%a)([%w]*)', function (first, rest) return first:upper() .. rest; end);
    return text;
end

-- (1.20, Bob) an item's stats for a tooltip: name, level and the game's own description text (the stats). From
-- Ashita's resources, so it shows whatever the game shows in its item help.
local statsCache = {};
local function itemStatsText(itemId, fallback)
    local id = tonumber(itemId);
    if id == nil or id <= 0 then return nil; end
    if statsCache[id] ~= nil then return statsCache[id] or nil; end
    local text = false;
    if AshitaCore and type(AshitaCore.GetResourceManager) == 'function' then
        local ok, item = pcall(function () return AshitaCore:GetResourceManager():GetItemById(id); end);
        if ok and item then
            local name = (item.Name and item.Name[1] and item.Name[1] ~= '') and tostring(item.Name[1]) or tostring(fallback or '');
            local lines = { name };
            local lv = tonumber(item.Level or 0) or 0;
            if lv > 0 then lines[#lines + 1] = 'Lv' .. lv; end
            local desc = item.Description and item.Description[1];
            if desc and desc ~= '' then lines[#lines + 1] = tostring(desc); end
            text = table.concat(lines, '\n');
        end
    end
    statsCache[id] = text;
    return text or nil;
end

local function drawGear(slot, name, itemId, textMax)
    local empty = emptySlot(name);
    local display = itemDisplayName(itemId, name);
    local icon = (not empty) and itemIcon(itemId, display) or nil;
    local shown = false;
    if icon ~= nil and imgui.Image ~= nil then
        shown = pcall(imgui.Image, icon.ptr, { ICON, ICON });
    end

    if not shown then
        local pos = screenPos();
        if pos then
            local draw = windowDraw();
            fillRect(draw, pos[1], pos[2], ICON, ICON, { 1, 1, 1, 0.05 }, 4);
        end
        imgui.Dummy({ ICON, ICON });
    end

    imgui.SameLine(0, 8);
    imgui.BeginGroup();
    tint(C.dim, SLOT_LABEL[slot + 1] or tostring(slot));
    if empty then
        tint(C.faint, 'Empty');
    else
        tint(C.text, fit(display, textMax));
    end
    imgui.EndGroup();
    if not empty then
        local stats = itemStatsText(itemId, display);
        if stats then tooltip(stats); end
    end
end

-- (1.19) Blue magic: a Blue Mage mate's set spells, like the Set Spells menu. Automatic until you click a spell;
-- "Fill automatically" hands it back. Changes apply when the mate is called again (Apply now).
local function askBlue(slot, delay)
    enqueue(string.format('/say !squad blu %d', slot), delay or 0);
    S.waitUntil = now() + (delay or 0) + 5;
end

local function bluePicker(slot, h)
    if slot == nil or h == nil or (h.job ~= 'BLU' and h.sub ~= 'BLU') then return; end
    if has('Separator') then imgui.Separator(); end
    colorText(C.gold, 'Blue magic');
    local b = S.blu;
    if b == nil or b.slot ~= slot then
        imgui.SameLine(0, 10);
        if button('Show', 'blushow' .. slot, 70, 0) then askBlue(slot); S.blu = { slot = slot, list = {}, done = false }; end
        tooltip('List the blue magic this mate knows and what is set (the mate has to be out)');
        return;
    end
    if not b.done then dimText('Looking... (the mate has to be out)'); return; end
    local setCount = 0;
    for _, k in ipairs(b.list) do if k.set then setCount = setCount + 1; end end
    dimText(string.format('%s  -  slots %d/%d, points %d/%d', b.auto and 'Automatic' or 'Your set', setCount, b.slots or 0, b.used or 0, b.points or 0));
    imgui.SameLine(0, 10);
    if button('Fill automatically', 'bluauto' .. slot, 0, 0, b.auto and 'selected' or nil) then
        enqueue(string.format('/say !squad blu %d auto', slot));
        S.pendingApply = true;
        askBlue(slot, 2);
        b.done = false;
    end
    tooltip('Let the mate pick its own set again');
    for k, item in ipairs(b.list) do
        if k > 1 and (k - 1) % 3 ~= 0 then imgui.SameLine(0, 6); end
        local label = string.format('%s (%d)', item.name, item.points);
        if button(label, 'blu' .. slot .. '_' .. item.id, px(150), 0, item.set and 'on' or nil) then
            enqueue(string.format('/say !squad blu %d %s %d', slot, item.set and 'unset' or 'set', item.id));
            S.pendingApply = true;
            askBlue(slot, 2);
            b.done = false;
        end
        tooltip(string.format('Lv%d, %d set points. Click to %s.', item.level, item.points, item.set and 'unset it' or 'set it'));
    end
    if #b.list == 0 then dimText('No blue magic known yet.'); end
    dimText('Changes apply when the mate is called again (Apply now).');
end

-- (1.14) Change gear: pick a slot, see the given gear this mate can wear there (from the server), click to put it on.
-- Works at home and in a friend's world (it only uses !squad commands).
local SLOT_KEY = { [0] = 'main', 'sub', 'range', 'ammo', 'head', 'body', 'hands', 'legs', 'feet', 'neck', 'waist', 'ear1', 'ear2', 'ring1', 'ring2', 'back' };
-- (1.21) lockstyle: the slots a look can be locked in (the ones you see on a character)
local LOOK_SLOTS = { [0] = true, [1] = true, [2] = true, [4] = true, [5] = true, [6] = true, [7] = true, [8] = true };
local function lockstyleRow(slot, d)
    colorText(C.gold, 'Lockstyle');
    imgui.SameLine(0, 8);
    local parts = {};
    for i = 0, 8 do
        local l = d and d.ls and d.ls[i];
        if l then parts[#parts + 1] = SLOT_KEY[i] .. ': ' .. tostring(l.name); end
    end
    dimText(#parts > 0 and table.concat(parts, ', ') or 'off (shows the gear it wears)');
    if button('Lock current look', 'lsset' .. slot, 0, 0) then
        enqueue(string.format('/say !squad lockstyle %d set', slot));
        askSheet(2);
    end
    tooltip('Keep the look it has now, whatever gear it wears later');
    imgui.SameLine(0, 6);
    if button('Lockstyle off', 'lsoff' .. slot, 0, 0) then
        enqueue(string.format('/say !squad lockstyle %d off', slot));
        askSheet(2);
    end
    tooltip('Show the gear it really wears');
    imgui.SameLine(0, 6);
    local looking = S.gearLook == true;
    if button(looking and 'Picking: look' or 'Picking: gear', 'lsmode' .. slot, 0, 0, looking and 'selected' or nil) then
        S.gearLook = not looking;
    end
    tooltip('Picking: gear = the items below are put on. Picking: look = they only change how the mate looks');
    gap(2);
end

local function gearPicker(slot)
    if slot == nil then return; end
    if has('Separator') then imgui.Separator(); end
    lockstyleRow(slot, S.profile);
    colorText(C.gold, S.gearLook and 'Choose the look' or 'Change gear');
    gap(2);
    local g = S.gear;
    if g == nil or g.slot ~= slot then g = { slot = slot, eq = nil, items = {}, done = false }; S.gear = g; end
    for i = 0, 15 do
        if i > 0 and i ~= 8 then imgui.SameLine(0, 3); end
        if button(SLOT_LABEL[i + 1], 'gp' .. slot .. '_' .. i, 0, 0, g.eq == i and 'selected' or nil) then
            g.eq, g.items, g.done, g.total = i, {}, false, nil;
            enqueue(string.format('/say !squad gearlist %d %d', slot, i));
            S.waitUntil = now() + 5;
        end
    end
    if g.eq == nil then
        dimText('Pick a slot to see the gear your squad has for it.');
        return;
    end
    gap(2);
    if not g.done then dimText('Looking...'); return; end
    local look = S.gearLook == true;
    if look and not LOOK_SLOTS[g.eq] then
        dimText('This slot does not show on a character: pick main, sub, range, head, body, hands, legs or feet.');
        return;
    end
    if button(look and 'Real gear' or 'Take off', 'gpoff' .. slot, 80, 0) then
        if look then
            enqueue(string.format('/say !squad lockstyle %d off %s', slot, SLOT_KEY[g.eq]));
        else
            enqueue(string.format('/say !squad unequip %d %s', slot, SLOT_KEY[g.eq]));
        end
        askSheet(2);
    end
    tooltip(look and 'Show the gear it really wears in this slot' or 'Leave this slot empty');
    if #g.items == 0 then
        imgui.SameLine(0, 10);
        dimText('Nothing for this slot yet: trade a piece to a mate (or !squad give) first.');
        return;
    end
    for k, item in ipairs(g.items) do
        if k > 1 and (k - 1) % 2 ~= 0 then imgui.SameLine(0, 6); end
        local label = string.format('Lv%d %s', item.level, itemDisplayName(item.id, item.name));
        if button(label, 'gpi' .. slot .. '_' .. item.id .. '_' .. k, 0, 0) then
            if look then
                enqueue(string.format('/say !squad lockstyle %d %d %s', slot, item.id, SLOT_KEY[g.eq]));
            else
                enqueue(string.format('/say !squad equip %d %d %s', slot, item.id, SLOT_KEY[g.eq]));
            end
            askSheet(2);
        end
        local stats = itemStatsText(item.id, item.name);
        tooltip((stats and (stats .. '\n\n') or '') .. (look and 'Click to look like this (only the look; call the mate again to see it)'
            or 'Click to put it on (call the mate again to see it on them)'));
    end
    if (g.total or 0) > #g.items then dimText(string.format('(%d more not shown)', g.total - #g.items)); end
end

local function drawHeader(h)
    local role = string.lower(tostring(h.role or 'auto'));
    local rgba = ROLE_COLORS[role] or ROLE_COLORS.auto;
    local jobs = tostring(h.job or '?') .. ' ' .. tostring(h.main or 0);
    if h.sub ~= '-' and h.sub ~= '' and h.sub ~= nil then
        if (tonumber(h.subLevel) or 0) > 0 then
            jobs = jobs .. ' / ' .. tostring(h.sub) .. ' ' .. tostring(h.subLevel);
        else
            jobs = jobs .. ' / ' .. tostring(h.sub) .. ' (locked)';   -- support jobs work once you have them yourself
        end
    end

    local pos, width, draw = screenPos(), contentWidth(), windowDraw();
    local height = px(32);
    if pos and width > 0 and fillRect(draw, pos[1], pos[2], width, height, { rgba[1] * 0.82, rgba[2] * 0.82, rgba[3] * 0.82, 0.96 }, 4) then
        fillRect(draw, pos[1], pos[2], 3, height, rgba, 0);
        seek(pos[1] + 10, pos[2] + px(7));
        tint({ 1, 1, 1, 1 }, fit(h.name, width - px(180)));
        imgui.SameLine(0, 8);
        tint({ 1, 1, 1, 0.82 }, jobs);
        local roleText = ROLE_NAME[role] or role;
        local roleWidth = textWidth(roleText) or (#roleText * 7);
        if width > 220 then
            imgui.SameLine(width - roleWidth - 10, 0);
            tint({ 1, 1, 1, 0.68 }, roleText);
        end
        seek(pos[1], pos[2] + height + 5);
    else
        colorText(C.gold, string.format('%s   (%s)', h.name, jobs));
    end
end

-- One compact row of vitals, each with a thin bar under it.
local function drawVitalRow(vitals)
    if not vitals or #vitals == 0 then return; end
    local pos, width, draw = screenPos(), contentWidth(), windowDraw();
    local gapPx = 8;
    local segment = width > 0 and math.floor((width - gapPx * (#vitals - 1)) / #vitals) or 0;
    if pos and draw and segment > 40 then
        for i, vital in ipairs(vitals) do
            local x = pos[1] + (i - 1) * (segment + gapPx);
            local label, current, maximum = tostring(vital[1]), tonumber(vital[2]) or 0, tonumber(vital[3]) or 0;
            local text = label == 'TP' and string.format('TP %d', current) or string.format('%s %d / %d', label, current, maximum);
            local rgba = VITAL_COLORS[label] or { 0.55, 0.58, 0.64, 0.85 };
            fillRect(draw, x, pos[2] + 18, segment, 4, { 0, 0, 0, 0.45 }, 2);
            local ratio = maximum > 0 and math.max(0, math.min(1, current / maximum)) or 0;
            if ratio > 0 then
                fillRect(draw, x, pos[2] + 18, math.max(2, segment * ratio), 4, { rgba[1], rgba[2], rgba[3], 0.90 }, 2);
            end
            seek(x, pos[2]);
            tint(C.text, text);
        end
        seek(pos[1], pos[2] + 26);
    else
        local parts = {};
        for _, vital in ipairs(vitals) do
            local label, current, maximum = tostring(vital[1]), tonumber(vital[2]) or 0, tonumber(vital[3]) or 0;
            parts[#parts + 1] = label == 'TP' and string.format('TP %d', current) or string.format('%s %d / %d', label, current, maximum);
        end
        colorText(C.text, table.concat(parts, '     '));
    end
end

-- 1.5: the mate's exp toward their next level on the main job (their own level, not the synced one).
local function commas(n)
    local s = tostring(math.floor(tonumber(n) or 0));
    while true do
        local done;
        s, done = s:gsub('^(-?%d+)(%d%d%d)', '%1,%2');
        if done == 0 then break; end
    end
    return s;
end

local function drawExpRow(x)
    if not x then return; end
    local text;
    if (x.needed or 0) <= 0 then
        text = string.format('EXP  %s %d  -  max level', tostring(x.job), x.level or 0);
    else
        text = string.format('EXP  %s / %s   (%s to %s %d)', commas(x.cur), commas(x.needed),
            commas(math.max(0, x.needed - x.cur)), tostring(x.job), (x.level or 0) + 1);
    end
    local pos, width, draw = screenPos(), contentWidth(), windowDraw();
    if pos and draw and width > 40 then
        local rgba = VITAL_COLORS.EXP;
        local ratio = (x.needed or 0) > 0 and math.max(0, math.min(1, (x.cur or 0) / x.needed)) or 1;
        fillRect(draw, pos[1], pos[2] + 18, width, 4, { 0, 0, 0, 0.45 }, 2);
        if ratio > 0 then
            fillRect(draw, pos[1], pos[2] + 18, math.max(2, width * ratio), 4, { rgba[1], rgba[2], rgba[3], 0.90 }, 2);
        end
        seek(pos[1], pos[2]);
        tint(C.text, text);
        seek(pos[1], pos[2] + 26);
    else
        colorText(C.text, text);
    end
end

local function toggleSheetSwitch(h, name)
    local slot = S.sheetSlot;
    if slot == nil or h == nil then return; end
    local mask = tonumber(h.mask) or 15;
    local on = hasBit(mask, SW_BIT[name]);
    enqueue(string.format('/say !squad sw %d %s %s', slot, name, on and 'off' or 'on'));
    h.mask = on and (mask - SW_BIT[name]) or (mask + SW_BIT[name]);
    askSheet(0.8);
end

local function renderSheet()
    if not imgui or not S.sheetOpen[1] then return; end
    if S.sheetFresh then
        -- Opened from the menu, the sheet used to appear wherever ImGui felt like it - often behind the menu,
        -- which looks like the button did nothing. Open it centred and focused.
        S.sheetFresh = false;
        if has('SetNextWindowPos') and has('GetMainViewport') then
            local ok, center = pcall(function() return imgui.GetMainViewport():GetCenter(); end);
            if ok and center then
                imgui.SetNextWindowPos({ center.x, center.y }, G('ImGuiCond_Appearing') or 8, { 0.5, 0.5 });
            end
        end
        if has('SetNextWindowFocus') then imgui.SetNextWindowFocus(); end
    end
    local d = S.profile;
    local title = 'Squad sheet  v' .. tostring(addon.version) .. '###sm_sheet';
    if d and d.hdr then
        title = string.format('%s (%s %d)###sm_sheet', d.hdr.name, tostring(d.hdr.job), tonumber(d.hdr.main) or 0);
    end
    if has('SetNextWindowSize') and G('ImGuiCond_FirstUseEver') then
        imgui.SetNextWindowSize({ px(580), px(660) }, G('ImGuiCond_FirstUseEver'));
    end
    if has('SetNextWindowSizeConstraints') then
        imgui.SetNextWindowSizeConstraints({ px(540), px(420) }, { px(800), px(900) });
    end
    local role = d and d.hdr and string.lower(tostring(d.hdr.role or 'auto')) or 'auto';
    local roleColor = ROLE_COLORS[role] or ROLE_COLORS.auto;
    local colors = pushColors({
        { 'ImGuiCol_WindowBg', C.panel }, { 'ImGuiCol_Border', C.line },
        { 'ImGuiCol_Separator', C.line }, { 'ImGuiCol_Text', C.text },
        { 'ImGuiCol_TitleBg', { roleColor[1] * 0.52, roleColor[2] * 0.52, roleColor[3] * 0.52, 1 } },
        { 'ImGuiCol_TitleBgActive', { roleColor[1] * 0.66, roleColor[2] * 0.66, roleColor[3] * 0.66, 1 } },
    });
    local vars = pushVars({
        { 'ImGuiStyleVar_WindowRounding', 6 }, { 'ImGuiStyleVar_ChildRounding', 5 }, { 'ImGuiStyleVar_FrameRounding', 4 },
        { 'ImGuiStyleVar_WindowPadding', { 12, 10 } }, { 'ImGuiStyleVar_ItemSpacing', { 8, 5 } }, { 'ImGuiStyleVar_FramePadding', { 6, 3 } },
    });
    local flags = (G('ImGuiWindowFlags_NoCollapse') or 0);
    if imgui.Begin(title, S.sheetOpen, flags) then
        scaleWindow();
        if d == nil or d.hdr == nil then
            dimText(now() < (S.sheetWaitUntil or 0) and 'Asking the server...' or 'No answer from the server. Press Sheet again.');
        else
            local h = d.hdr;
            local width = contentWidth();
            local statWidth = width > 0 and width or 440;
            drawHeader(h);

            local bits = { tostring(h.role or 'auto') };
            if h.mode and h.mode ~= '' then bits[#bits + 1] = h.mode; end
            if h.race and h.race ~= '' and h.race ~= '?' then bits[#bits + 1] = h.race; end
            local left = table.concat(bits, '  \194\183  ');
            tint(C.dim, left);
            for i, name in ipairs(SWITCHES) do
                imgui.SameLine(0, i == 1 and 12 or 4);
                local on = hasBit(h.mask or 15, SW_BIT[name]);
                if button(name, 'sheetsw' .. tostring(S.sheetSlot or 0) .. name, 0, 0, on and 'on' or nil) then
                    toggleSheetSwitch(h, name);
                end
                tooltip(name .. ': ' .. (on and 'on' or 'off'));
            end
            gap(4);

            drawVitalRow(d.vitals);
            drawExpRow(d.exp);
            if d.note then
                wrappedColored(C.faint, d.note);
                gap(2);
            end

            if d.stats or d.combat then
                if has('Separator') then imgui.Separator(); end
                colorText(C.gold, 'Current calculated stats');
                gap(2);
                local rows = math.max(d.stats and #d.stats or 0, d.combat and #d.combat or 0);
                local rightX = math.floor(statWidth * 0.50);
                for i = 1, rows do
                    local s = d.stats and d.stats[i];
                    local c = d.combat and d.combat[i];
                    if s then
                        tint(C.dim, s[1]);
                        imgui.SameLine(px(56), 0);
                        tint(C.text, tostring(s[2]));
                    else
                        imgui.Text(' ');
                    end
                    if c then
                        local labelWidth = textWidth(c[1]) or 100;
                        local valueX = rightX + math.max(110, labelWidth + 10);
                        imgui.SameLine(rightX, 0);
                        tint(C.dim, c[1]);
                        imgui.SameLine(valueX, 0);
                        tint(C.text, tostring(c[2]));
                    end
                    newLine();
                end
            end

            if d.haste and #d.haste > 0 then
                local parts = {};
                for _, v in ipairs(d.haste) do parts[#parts + 1] = string.format('%s %.2f%%', v[1], v[2] / 100); end
                tint(C.dim, 'Haste');
                imgui.SameLine(0, 12);
                tint(C.text, table.concat(parts, '     '));
                newLine();
            end

            if d.jobs and #d.jobs > 0 then
                local parts = {};
                for i, j in ipairs(d.jobs) do
                    if i > 8 then break; end
                    parts[#parts + 1] = j[1] .. ' ' .. tostring(j[2]);
                end
                wrapped('Jobs: ' .. table.concat(parts, ', '), C.text);
            end

            if has('Separator') then imgui.Separator(); end
            colorText(C.gold, 'Equipped items');
            gap(2);
            local gearWidth = contentWidth();
            if gearWidth <= 0 then gearWidth = statWidth; end
            local column = math.floor(gearWidth / 2);
            local textMax = math.max(40, column - ICON - 18);
            local eq = d.eq or {};
            for i = 1, 8 do
                drawGear(SHEET_LEFT[i], eq[SHEET_LEFT[i]], d.eqId and d.eqId[SHEET_LEFT[i]], textMax);
                imgui.SameLine(column, 0);
                drawGear(SHEET_RIGHT[i], eq[SHEET_RIGHT[i]], d.eqId and d.eqId[SHEET_RIGHT[i]], textMax);
                newLine();
            end

            gearPicker(S.sheetSlot);   -- (1.18: was `slot`, which is not set in this function, so the picker never showed)
            bluePicker(S.sheetSlot, d.hdr);

            if has('Separator') then imgui.Separator(); end
            wrappedColored(C.faint, 'The stats are read from your squad mate while they are out, so they already include their gear. '
                .. 'Gear shown for a mate who is away is what they wear as this job.');
            gap(2);
            tint(C.faint, 'servermenu ' .. tostring(addon.version));
        end
    end
    S.scaledNow = false;
    imgui.End();
    if colors > 0 then imgui.PopStyleColor(colors); end
    if vars > 0 then imgui.PopStyleVar(vars); end
end

local function render()
    if not imgui then return; end
    buttonWindow();
    menuWindow();
    renderSheet();
end

-- ---------------------------------------------------------------- events
ashita.events.register('load', 'servermenu_load', function ()
    local hadWide, hadCfg = loadCfg();
    -- auto mode always starts off at login (phoenixsolo sends the off switches), so the tab must say OFF
    if S.cfg.auto_me ~= 'false' then S.cfg.auto_me = 'false'; S.cfgDirty = true; end
    writeAutoFlag(false);
    -- 1.2: the button grew from 58 to 76 px. A spot saved by 1.1 moves left once, so its right edge stays where it was.
    if not hadWide then
        if hadCfg then S.cfg.button_x = tostring(math.max(0, (tonumber(S.cfg.button_x) or 18) - 18)); end
        S.cfg.button_wide = 'true';
        saveCfg();
    end
    S.tab = (S.cfg.tab == 'Squad' or S.cfg.tab == 'Dualbox' or S.cfg.tab == 'Auto') and S.cfg.tab or 'Squad';
    S.spell[1] = S.cfg.spell ~= '' and S.cfg.spell or 'Dia';
    if not imgui then say('ImGui is not available, so there is no menu. The squad commands still work.'); return; end
    say('servermenu ' .. tostring(addon.version) .. ' loaded. Click the Squads button, or type /menu.');
end);

ashita.events.register('d3d_present', 'servermenu_present', function ()
    syncAutoFlag()
    local t = now();
    pump(t);
    if S.open[1] and #S.queue == 0 and t - S.lastAsk > 15 and S.tab == 'Squad' then ask(); end   -- keeps the squad current while it is shown
    if S.sheetOpen[1] and #S.queue == 0 and t - S.lastSheetAsk > 5 then askSheet(); end          -- hit points and TP move
    if t - S.duoRead >= 1 then readDuo(); end
    flushDuo(t);
    if S.open[1] and S.tab == 'Dualbox' and S.duoGambits and t - S.sheetRead >= 1.5 then readSheet(t); end
    if S.cfgDirty and not S.dragging and t - S.cfgSavedAt > 1 then saveCfg(); end
    local ok, err = pcall(render);
    if not ok and not S.renderError then
        S.renderError = true;
        say('the menu hit a problem and was closed: ' .. tostring(err));
        S.open[1] = false;
    end
end);

ashita.events.register('text_in', 'servermenu_text_in', function (e)
    if e.blocked then return; end
    local text = strip(e.message_modified or e.message);
    local at = text:find('squadpanel:', 1, true);
    if at then
        if now() < S.waitUntil + 3 then e.blocked = true; end                -- hidden only while the menu asked for it
        onLine(text:sub(at + 11));
        return;
    end
    local sheetAt = text:find('squadsheet:', 1, true);
    if sheetAt then
        if now() < (S.sheetWaitUntil or 0) + 3 then e.blocked = true; end
        onSheetLine(text:sub(sheetAt + 11));
        return;
    end
    -- FFXI's own chat parser prints this generic line after an addon sends a /say command, even when the
    -- server ran it. Only while one of our commands is in flight, so a real failed command is still shown.
    if now() < S.hideUntil and text:match('^%.%.%.%s*A command error occurred%.$') then e.blocked = true; return; end
    if now() < S.hideUntil and (text:match('^!squad') or text:match(':%s*!squad%s')) then e.blocked = true; end   -- the echo of the menu's own commands
end);

ashita.events.register('command', 'servermenu_command', function (e)
    local args = e.command:args();
    if #args == 0 then return; end
    local first = args[1]:lower();
    local sub = (args[2] or ''):lower();
    if first == '/sq' or first == '/squadpanel' then
        e.blocked = true;
        setTab('Squad');
        if sub == 'sheet' then
            setOpen(true);
            local slot = tonumber(args[3] or '') or S.sheetSlot or (S.mates[1] and S.mates[1].slot);
            if slot then openSheet(slot) else S.sheetOpen[1] = true; say('no mate in the list yet; press Refresh first.'); end
        elseif sub == 'refresh' or sub == 'on' then setOpen(true);
        elseif sub == 'off' then S.open[1] = false;
        else setOpen(not S.open[1]); end
        return;
    end
    if first ~= '/menu' and first ~= '/smenu' and first ~= '/servermenu' then return; end
    e.blocked = true;
    if sub == 'button' then
        setCfg('button_hidden', 'false');
        say('the FFXI button is back.');
    elseif sub == 'resetbutton' then
        setCfg('button_x', 18); setCfg('button_y', 240); setCfg('button_hidden', 'false'); setCfg('button_locked', 'false');
        S.placeButton = true;
        say('the FFXI button is back in its first place.');
    elseif sub == 'scale' then
        local v = tonumber(args[3] or '');
        if v then
            v = math.max(0.75, math.min(3, v));
            setCfg('scale', v);
            say(string.format('menu size is now %.2f (1 = normal). /menu scale 1 to go back.', v));
        else
            say(string.format('/menu scale <0.75-3>   size of the Squads button, menu and mate sheets. Now: %.2f', userScale()));
        end
    elseif sub == 'gambits' then
        setTab('Dualbox');
        S.duoGambits = true;
        setOpen(true);
    elseif TAB_DRAW[sub:sub(1, 1):upper() .. sub:sub(2)] then
        setTab(sub:sub(1, 1):upper() .. sub:sub(2));
        setOpen(true);
    elseif sub == 'help' then
        say('/menu  open or close  |  /menu squad|dualbox  |  /menu gambits (dualbox)  |  /menu button  |  /menu resetbutton  |  /menu scale <0.75-3>  |  /sq');
    else
        setOpen(not S.open[1]);
    end
end);
