--[[
squadpanel 0.14
A small window for your squad mates: click to set each mate's role, mode and on/off switches, call them, or dismiss them.
Press Sheet on a mate for a second window with their stats and their gear, like a character screen you can read.
And for your dualbox character: an AUTO button and his job profile (needs the followme addon, 0.8 or newer, in the second window).

  /sq  (or /squadpanel)     open or close the window
  /sq refresh               ask the server again
  /sq sheet [slot]          open the stat sheet, for that mate or the last one you looked at
The Dualbox block talks to the second window through two small files in config/addons/duo (status.cfg in, command.cfg out).
The rest only uses the squad commands you could type yourself: !squad panel, !squad sheet, !squad role, !squad mode, !squad call and !squad dismiss.
The lines the server sends back ("squadpanel:..." and "squadsheet:...") and the echo of the commands it sends are hidden from your chat log.
A role or mode applies when a mate is called, so "Apply now" dismisses the squad and calls them all again.
]]

addon.name    = 'squadpanel';
addon.author  = 'XI: Forever Offline';
addon.version = '0.14';
addon.desc    = 'Click to set the role, mode and switches of your squad mates, or read their stats and gear.';
addon.link    = '';

require('common');

local imgui;
do
    local ok, mod = pcall(require, 'imgui');
    if ok then imgui = mod; end
end

-- Item icons come from the game's own item bitmaps (the same source the equipment monitor uses).
-- Both modules are optional so the sheet still works as text if a future Ashita build moves them.
local ffi, d3d8;
do
    local ok, mod = pcall(require, 'ffi');
    if ok then ffi = mod; end
    local ok2, mod2 = pcall(require, 'd3d8');
    if ok2 then d3d8 = mod2; end
end

local ROLES = { 'auto', 'tank', 'damage', 'healer', 'support' };
local MODES = { 'balanced', 'aggressive', 'conserve' };

-- The coloured bar behind a mate's name, the same idea as Titan's recruit list.
local ROLE_COLORS =
{
    tank    = { 0.18, 0.38, 0.58, 1.00 },
    healer  = { 0.18, 0.44, 0.25, 1.00 },
    support = { 0.55, 0.42, 0.12, 1.00 },
    damage  = { 0.48, 0.19, 0.19, 1.00 },
    auto    = { 0.24, 0.24, 0.24, 1.00 },
};

local VITAL_COLORS =
{
    HP = { 0.22, 0.55, 0.28, 0.82 },
    MP = { 0.22, 0.38, 0.68, 0.82 },
    TP = { 0.68, 0.56, 0.16, 0.82 },
};

-- The sheet uses the same dark panel and gold headings as the server menu.
local C =
{
    gold  = { 0.89, 0.74, 0.40, 1.00 },
    text  = { 0.90, 0.92, 0.95, 1.00 },
    dim   = { 0.58, 0.61, 0.68, 1.00 },
    faint = { 0.46, 0.49, 0.55, 1.00 },
    panel = { 0.065, 0.075, 0.105, 0.97 },
    line  = { 0.30, 0.32, 0.40, 0.55 },
};

local ROLE_NAME = { tank = 'Tank', healer = 'Healer', support = 'Support', damage = 'DPS', auto = 'Auto' };

-- (0.14, role clarity) what a squad mate's Role really does, from the server's squad.lua behaviorFilter / ROLE_KEEPS /
-- EMERGENCY_HP (tank 40, damage 30) and MODE_HEAL_SHIFT (+15 / -15, kept between 15 and 90): the same words as the
-- server menu (servermenu.lua ROLE_HELP). Text only: the server decides.
local ROLE_INFO = {
    HELP = {
        auto    = 'Auto: the job\'s default rules, nothing filtered.',
        tank    = 'Tank: keeps Provoke, Sentinel, Flash and other debuffs, its own buffs and other job abilities.\n'
            .. 'Cures only targets below 40% HP (Aggressive 55%, Conserve 25%). No status removal (-na, Erase), '
            .. 'no buffs on others, no nukes or ranged attacks.',
        damage  = 'Damage: keeps attacks, nukes, ranged attacks, debuffs, its own buffs and job abilities other than '
            .. 'tank ones.\nCures only targets below 30% HP (Aggressive 45%, Conserve 15%). No status removal (-na, Erase), '
            .. 'no buffs on others, no Provoke or Sentinel.',
        healer  = 'Healer: keeps cures, status removal and buffs for the party.\n'
            .. 'No debuffs (Flash, Dia, Paralyze...), nukes, ranged attacks or job abilities (Convert and Chakra stay).',
        support = 'Support: keeps buffs for the party, debuffs, status removal, normal cures and ranged attacks.\n'
            .. 'No nukes and no job abilities (Convert and Chakra stay).',
    },
    MODE = {
        balanced   = 'Balanced: the normal pace, nothing changed.',
        aggressive = 'Aggressive: cures at 15% more HP (at most 90%), also on top of a Tank or Damage limit; '
            .. 'holds no MP back.',
        conserve   = 'Conserve: cures at 15% less HP (at least 15%) and keeps 40% MP before buffs, debuffs, nukes and '
            .. 'status removal.',
    },
    FOOTER = 'The Squad Role changes only the mate\'s default job rules, from its next call (Apply now). '
        .. 'A Gambits Rule Set replaces those rules and is not filtered by the Role. '
        .. 'Not the same as the Gambits party roles (Tank / Melee / Mage / Ranged).',
    -- the short legend under the mates
    LEGEND = 'tank: Provoke, Sentinel, debuffs, own buffs; cures only below 40% HP, no status removal, no buffs on others.   '
        .. 'damage: attacks, nukes, debuffs, own buffs; cures only below 30% HP, no status removal, no buffs on others.   '
        .. 'healer: cures, status removal, party buffs; no debuffs, nukes or job abilities.   '
        .. 'support: party buffs, debuffs, status removal, cures; no nukes or job abilities.   '
        .. 'auto: the job\'s default rules, nothing filtered.',
    MODE_LEGEND = 'aggressive: cures 15% HP earlier.   conserve: cures 15% HP later and keeps 40% MP for the rest.',
    NOTE_LEGEND = 'The Role filters only the default job rules (at the next call); a Gambits Rule Set is not filtered. '
        .. 'It is not the Gambits party role (Tank / Melee / Mage / Ranged). Hover a role for details.',
    -- jobs whose default rules heal or support others, and what a Tank / Damage Role takes from them: WHM cures, status
    -- removal and party buffs; RDM cures and buffs on you and the party; PLD its Cure
    CARE = { WHM = { cleanse = true, buffs = true }, RDM = { buffs = true }, PLD = {} },
    CAP = { tank = 40, damage = 30 },
    SHIFT = { aggressive = 15, conserve = -15 },
};

-- (0.14) the small gold note on a mate's row: only when a Tank or Damage Role takes healing or support away from a job
-- (main or sub) whose default rules have it. A PLD tank without a WHM/RDM sub job is the usual set-up: no note. The
-- panel does not know whether a Gambits Rule Set is assigned, so it speaks only of the default job rules.
-- Returns the tooltip, the Role's name and the job it is about, or nil.
function ROLE_INFO.note(mate)
    local role = mate and mate.role;
    local cap = ROLE_INFO.CAP[role or ''];
    if cap == nil then return nil; end
    local main, sub = ROLE_INFO.CARE[mate.main or ''], ROLE_INFO.CARE[mate.sub or ''];
    if main == nil and sub == nil then return nil; end
    if role == 'tank' and mate.main == 'PLD' and sub == nil then return nil; end
    local limit = math.max(15, math.min(90, cap + (ROLE_INFO.SHIFT[mate.mode or ''] or 0)));
    local parts = { string.format('cures only below %d%% HP', limit) };
    if (main and main.cleanse) or (sub and sub.cleanse) then parts[#parts + 1] = 'no status removal'; end
    if (main and main.buffs) or (sub and sub.buffs) then parts[#parts + 1] = 'no buffs on party members'; end
    local job = main and mate.main or mate.sub;
    local roleName = role:sub(1, 1):upper() .. role:sub(2);
    return string.format('Default healing is heavily restricted: Role %s %s.\n'
        .. 'This is a valid choice for an offensive %s; Auto gives the job\'s normal healing.\n'
        .. 'It applies only to the default job rules: a Gambits Rule Set replaces them and is not restricted.',
        roleName, table.concat(parts, ', '), job), roleName, job;
end

-- a tooltip for the item just drawn, wrapped at about 27 characters' width of the current font (~350 px at 13 px), as
-- the Squad menu's and the Gambits editor's tooltips, so it stays next to the mouse. Drawn with TextUnformatted: Ashita
-- hands SetTooltip's text to ImGui as a printf format, and these texts contain '%' ("below 30% HP"). Without
-- BeginTooltip / TextUnformatted: SetTooltip with '%' doubled.
local function hoverTip(text)
    if not (text and imgui.IsItemHovered and imgui.IsItemHovered()) then return; end
    if imgui.BeginTooltip and imgui.EndTooltip and imgui.TextUnformatted then
        if imgui.BeginTooltip() ~= false then
            local size = imgui.GetFontSize and imgui.GetFontSize() or nil;
            local wrapOk = imgui.PushTextWrapPos and imgui.PopTextWrapPos;
            if wrapOk then imgui.PushTextWrapPos((type(size) == 'number' and size > 0) and size * 27 or 350); end
            imgui.TextUnformatted(tostring(text));
            if wrapOk then imgui.PopTextWrapPos(); end
            imgui.EndTooltip();
        end
    elseif imgui.SetTooltip then
        imgui.SetTooltip((tostring(text):gsub('%%', '%%%%')));
    end
end

-- The server sends the switches as a bit mask (1 melee, 2 ranged, 4 ja, 8 magic); 15 is everything on.
local SWITCHES = { 'melee', 'ranged', 'ja', 'magic' };
local SW_BIT   = { melee = 1, ranged = 2, ja = 4, magic = 8 };

local function hasBit(mask, bit)
    return math.floor((tonumber(mask) or 0) / bit) % 2 == 1;
end

local SLOT_LABEL = { 'Main', 'Sub', 'Ranged', 'Ammo', 'Head', 'Body', 'Hands', 'Legs', 'Feet', 'Neck', 'Waist', 'Ear 1', 'Ear 2', 'Ring 1', 'Ring 2', 'Back' };
local SHEET_LEFT  = { 0, 2, 4, 6, 8, 9, 11, 13 };
local SHEET_RIGHT = { 1, 3, 5, 7, 10, 12, 14, 15 };

local S = {
    open = { false }, mates = {}, incoming = nil, waitUntil = 0, hideUntil = 0, lastAsk = -1000, lastSend = -1000,
    queue = {}, note = '', lastUpdate = nil,
    duo = nil, duoRead = -1000, duoSeq = 0,
    sheetOpen = { false }, sheet = nil, sheetIncoming = nil, sheetSlot = nil, lastSheetAsk = -1000,
};

-- itemId (or the item's name on an older server) -> { image = <D3D texture>, ptr = <number ImGui can draw> },
-- or false when it could not be loaded.
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

local function now()
    if ashita and ashita.time and type(ashita.time.get_tick64) == 'function' then
        local ok, n = pcall(ashita.time.get_tick64);
        if ok and type(n) == 'number' then return n / 1000; end
    end
    return os.clock();
end

local function say(text)
    print('[squadpanel] ' .. tostring(text));
end

local function strip(message)
    local text = tostring(message or ''):gsub('%z', ''):gsub('[\30\31].', ''):gsub('^%s+', ''):gsub('%s+$', '');
    return text;
end

-- ---------------------------------------------------------------- talking to the server
local function chatManager()
    local ok, chat = pcall(function() return AshitaCore:GetChatManager(); end);
    if ok then return chat; end
    return nil;
end

local function typing(chat)
    local ok, open = pcall(function() return chat:IsInputOpen(); end);
    return ok and (open == true or (type(open) == 'number' and open ~= 0));
end

-- Commands are queued and sent one at a time, a moment apart, and never while you are typing
local function enqueue(command, delay)
    S.queue[#S.queue + 1] = { at = now() + (delay or 0), command = command };
end

local function ask(delay)
    enqueue('/say !squad panel', delay or 0);
    S.waitUntil = now() + (delay or 0) + 5;
    S.lastAsk = now();
    S.incoming = nil;
end

local function askSheet(delay)
    if S.sheetSlot == nil then return; end
    enqueue(string.format('/say !squad sheet %d', S.sheetSlot), delay or 0);
    S.waitUntil = now() + (delay or 0) + 5;
    S.lastSheetAsk = now();
    S.sheetIncoming = {};
end

local function pump(t)
    local first = S.queue[1];
    if first == nil or first.at > t or t - S.lastSend < 0.6 then return; end
    local chat = chatManager();
    if chat == nil or typing(chat) then return; end
    table.remove(S.queue, 1);
    S.lastSend = t;
    S.hideUntil = t + 2.5;
    pcall(function() chat:QueueCommand(1, first.command); end);
end

-- ---------------------------------------------------------------- the dualbox character, through two small files
local function duoDir()
    local ok, base = pcall(function() return AshitaCore:GetInstallPath(); end);
    if not ok or type(base) ~= 'string' then return nil; end
    return base .. 'config/addons/duo/';
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

-- One command at a time: a new sequence number each time, so the other window knows it is new
local function sendDuo(fields)
    local dir = duoDir();
    if not dir then return false; end
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, dir); end
    local f = io.open(dir .. 'command.cfg', 'w');
    if not f then return false; end
    S.duoSeq = math.max(S.duoSeq + 1, os.time());
    f:write('seq=' .. S.duoSeq .. '\n');
    if fields.auto then f:write('auto=' .. fields.auto .. '\n'); end
    if fields.profile then f:write('profile=' .. fields.profile .. '\n'); end
    if fields.reset then f:write('reset=1\n'); end
    if fields.probe then f:write('probe=' .. fields.probe .. '\n'); end
    if fields.unclaimed then f:write('unclaimed=' .. fields.unclaimed .. '\n'); end
    f:close();
    return true;
end

-- ---------------------------------------------------------------- what the server sends back
local function parseMate(payload)
    local slot, name, mainJob, mainLevel, subJob, subLevel, role, mode, called, mask =
        payload:match('^(%d+)|([^|]+)|([^|]+)|(%d+)|([^|]+)|(%d+)|(%a+)|(%a+)|([01])|(%d+)$');
    if not slot then
        -- an older server: no switch mask on the end, so show everything as on
        slot, name, mainJob, mainLevel, subJob, subLevel, role, mode, called =
            payload:match('^(%d+)|([^|]+)|([^|]+)|(%d+)|([^|]+)|(%d+)|(%a+)|(%a+)|([01])$');
        mask = nil;
    end
    if not slot then return nil; end
    return { slot = tonumber(slot), name = name, main = mainJob, mainLevel = tonumber(mainLevel), sub = subJob, subLevel = tonumber(subLevel),
             role = role, mode = mode, out = called == '1', mask = mask and tonumber(mask) or 15 };
end

local function onLine(payload)
    if payload == 'end' then
        S.mates = S.incoming or {};
        S.incoming = nil;
        S.waitUntil = 0;
        S.lastUpdate = now();
        return;
    end
    local mate = parseMate(payload);
    if mate then
        S.incoming = S.incoming or {};
        S.incoming[#S.incoming + 1] = mate;
    end
end

-- The sheet arrives as one short line per value, so the server never has to send a long chat message.
local function onSheetLine(text)
    if text == 'end' then
        if S.sheetIncoming then S.sheet = S.sheetIncoming; end
        S.sheetIncoming = nil;
        return;
    end
    local data = S.sheetIncoming;
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
        if job then
            data.jobs = data.jobs or {};
            data.jobs[#data.jobs + 1] = { job, tonumber(level) };
        end
    elseif key == 'vital' then
        local label, cur, max = rest:match('^([^|]+)|(%d+)|(%d+)$');
        if label then
            data.vitals = data.vitals or {};
            data.vitals[#data.vitals + 1] = { label, tonumber(cur), tonumber(max) };
        end
    elseif key == 'stat' or key == 'combat' or key == 'haste' then
        local label, value = rest:match('^([^|]+)|(-?%d+)$');
        if label then
            local field = (key == 'stat') and 'stats' or key;   -- the window calls the seven main stats "stats"
            data[field] = data[field] or {};
            data[field][#data[field] + 1] = { label, tonumber(value) };
        end
    elseif key == 'eq' then
        -- Newer servers add the item id after the name, so the sheet can show the item's icon.
        local slot, name, id = rest:match('^(%d+)|[^|]*|([^|]*)|(%d+)$');
        if not slot then
            slot, name = rest:match('^(%d+)|[^|]*|(.*)$');   -- an older server: just the slot and the name
        end
        if slot then
            -- Another old layout put the id on the end of the name instead of in its own field.
            local embedded = name and name:match('|(%d+)$');
            if embedded ~= nil then
                if id == nil then id = embedded; end
                name = name:gsub('|%d+$', '');
            end
            data.eq = data.eq or {};
            data.eq[tonumber(slot)] = name;
            if id then
                data.eqId = data.eqId or {};
                data.eqId[tonumber(slot)] = tonumber(id);
            end
        end
    elseif key == 'note' then
        data.note = rest;
    end
end

local function openSheet(slot)
    S.sheetSlot = slot;
    S.sheetOpen[1] = true;
    S.sheet = nil;
    askSheet(0);
end

-- ---------------------------------------------------------------- what a click does
local function setBehavior(mate, kind, value)
    enqueue(string.format('/say !squad %s %d %s', kind, mate.slot, value));
    mate[kind] = value;
    S.note = 'A role or mode applies when the mate is called again: press "Apply now".';
    ask(1.5);
end

local function setSwitch(mate, name, on)
    enqueue(string.format('/say !squad sw %d %s %s', mate.slot, name, on and 'on' or 'off'));
    if on then
        mate.mask = mate.mask + SW_BIT[name];
    else
        mate.mask = mate.mask - SW_BIT[name];
    end
    S.note = 'Melee off applies at once. The other switches apply when the mate is called again.';
    ask(1.5);
end

local function applyNow()
    enqueue('/say !squad dismiss');
    enqueue('/say !squad call all', 2.5);
    ask(5);
    S.note = '';
end

-- ---------------------------------------------------------------- the window
local function colored(selected, id, label, width, rgba)
    local pushed = 0;
    local button = rawget(_G, 'ImGuiCol_Button');
    local hover = rawget(_G, 'ImGuiCol_ButtonHovered');
    local base = rgba or { 0.12, 0.42, 0.22, 1 };
    if selected and button ~= nil then
        imgui.PushStyleColor(button, { base[1], base[2], base[3], 1 });
        pushed = pushed + 1;
    end
    if selected and hover ~= nil then
        imgui.PushStyleColor(hover, { math.min(1, base[1] + 0.10), math.min(1, base[2] + 0.10), math.min(1, base[3] + 0.10), 1 });
        pushed = pushed + 1;
    end
    local textColor = rawget(_G, 'ImGuiCol_Text');
    if selected and textColor ~= nil then
        imgui.PushStyleColor(textColor, { 1, 1, 1, 1 });
        pushed = pushed + 1;
    end
    local clicked = imgui.Button(label .. '##' .. id, { width, 22 });
    if pushed > 0 then imgui.PopStyleColor(pushed); end
    return clicked;
end

local drawMateBar;   -- defined with the sheet drawing helpers, called by render

local function render()
    if not S.open[1] then return; end
    if not imgui then
        S.open[1] = false;
        say('ImGui is not available, so there is no window. The squad commands still work.');
        return;
    end
    imgui.SetNextWindowSize({ 660, 0 }, rawget(_G, 'ImGuiCond_FirstUseEver') or 4);
    local flags = (rawget(_G, 'ImGuiWindowFlags_NoCollapse') or 0) + (rawget(_G, 'ImGuiWindowFlags_AlwaysAutoResize') or 0);
    if imgui.Begin('Squad', S.open, flags) then
        imgui.Text('Dualbox');
        local duo = S.duo;
        if not duo then
            imgui.Text('   not running. Press DUALBOX in the launcher (the second window needs the followme addon, 0.8 or newer).');
        else
            imgui.Text(string.format('   %s   %s%s/%s%s   HP %s%%   MP %s%%', duo.name or '?', duo.job or '?', duo.level or '?', duo.sub or '?', duo.sublevel or '?',
                duo.hp or '?', duo.mp or '?'));
            local on = duo.auto == 'on';
            imgui.Text('   ');
            imgui.SameLine(0, 0);
            if colored(on, 'duoauto', on and 'AUTO: ON' or 'AUTO: OFF', 120) then
                if sendDuo({ auto = on and 'off' or 'on' }) then duo.auto = on and 'off' or 'on'; end
            end
            imgui.SameLine(0, 12);
            imgui.Text('Profile');
            for _, role in ipairs(ROLES) do
                imgui.SameLine(0, 4);
                if colored(duo.profile == role, 'duoprofile' .. role, role, 84) then
                    if sendDuo({ profile = role }) then duo.profile = role; end
                end
            end
            imgui.TextWrapped('   He is: ' .. tostring(duo.follow or ''));
            local line = {};
            if duo.master and duo.master ~= '' then line[#line + 1] = 'master ' .. duo.master; end
            if duo.gate and duo.gate ~= '' then line[#line + 1] = duo.gate; end
            if duo.last and duo.last ~= '' then line[#line + 1] = 'last: ' .. duo.last; end
            if #line > 0 then imgui.TextWrapped('   Gambits: ' .. table.concat(line, '   |   ')); end
            for _, key in ipairs({ 'why1', 'why2', 'why3' }) do
                if duo[key] and duo[key] ~= '' then imgui.TextWrapped('      not firing: ' .. duo[key]); end
            end
            if duo.actions and duo.actions ~= '' then
                imgui.TextWrapped('   Engine: ' .. duo.actions .. ((duo.buffs and duo.buffs ~= '') and ('   |   status data: ' .. duo.buffs) or ''));
            end
            if duo.fight1 and duo.fight1 ~= '' then
                local stamp = tonumber(duo.fightat);
                local age = stamp and math.max(0, os.time() - stamp) or nil;
                imgui.TextWrapped('   Last fight' .. (age and (' (' .. age .. ' s ago)') or '') .. ': ' .. duo.fight1);
                for i = 2, 10 do
                    local line = duo['fight' .. i];
                    if line and line ~= '' then imgui.TextWrapped('      ' .. line); end
                end
            end
            if duo.unclaimed == 'on' or duo.unclaimed == 'off' then
                local unclaimed = duo.unclaimed == 'on';
                imgui.Text('   ');
                imgui.SameLine(0, 0);
                if colored(unclaimed, 'duounclaimed', unclaimed and 'Unclaimed: ON' or 'Unclaimed: OFF', 140) then
                    if sendDuo({ unclaimed = unclaimed and 'off' or 'on' }) then duo.unclaimed = unclaimed and 'off' or 'on'; end
                end
                imgui.SameLine(0, 8);
                imgui.Text('on: he casts on the monster he is fighting even if the game does not show who claimed it');
            elseif duo.unclaimed == '?' then
                imgui.TextWrapped('   Unclaimed targets: the gambit engine\'s settings file was not found (yet), so this switch is not available.');
            end
            imgui.Text('   ');
            imgui.SameLine(0, 0);
            if imgui.Button('Check Dia##probe', { 120, 24 }) then sendDuo({ probe = 'Dia' }); end
            imgui.SameLine(0, 8);
            imgui.Text('press this during a fight: it tests, one by one, what he needs before he can cast');
            for i = 1, 18 do
                local line = duo['probe' .. i];
                if line and line ~= '' then imgui.TextWrapped('      ' .. line); end
            end
            if duo.sheet and duo.sheet ~= '' then
                local normal = duo.sheet == 'normal';
                imgui.TextWrapped('   His rows: ' .. tostring(duo.rows or '?') .. (normal and ' (the normal sheet)'
                    or (duo.sheet == 'japanese' and ' (hand-made, with Japanese names the engine can not find)' or ' (not the normal sheet)')));
                if not normal then
                    imgui.SameLine(0, 8);
                    if imgui.Button('Reset rows##resetrows', { 100, 24 }) then sendDuo({ reset = true }); end
                end
            end
        end
        imgui.Separator();
        imgui.Text('Squad');
        if imgui.Button('Refresh##refresh', { 90, 24 }) then ask(); end
        imgui.SameLine(0, 8);
        if imgui.Button('Apply now##apply', { 110, 24 }) then applyNow(); end
        imgui.SameLine(0, 8);
        if imgui.Button('Call all##callall', { 90, 24 }) then enqueue('/say !squad call all'); ask(3); end
        imgui.SameLine(0, 8);
        if imgui.Button('Dismiss##dismiss', { 90, 24 }) then enqueue('/say !squad dismiss'); ask(1.5); end
        if S.note ~= '' then imgui.TextWrapped(S.note); end
        imgui.Separator();

        if #S.mates == 0 then
            imgui.Text(now() < S.waitUntil and 'Asking the server...' or 'No squad mates yet, or no answer yet. Press Refresh.');
        end
        for _, mate in ipairs(S.mates) do
            local jobs = string.format('%s %d', mate.main, mate.mainLevel);
            if mate.sub ~= '-' then jobs = jobs .. string.format(' / %s %d', mate.sub, mate.subLevel); end
            drawMateBar(mate, jobs);
            if not mate.out then
                if imgui.Button('Call##call' .. mate.slot, { 56, 20 }) then enqueue('/say !squad call ' .. mate.slot); ask(3); end
                imgui.SameLine(0, 6);
            end
            if imgui.Button('Sheet##sheet' .. mate.slot, { 56, 20 }) then openSheet(mate.slot); end
            imgui.Text('Role  ');
            for _, role in ipairs(ROLES) do
                imgui.SameLine(0, 4);
                if colored(mate.role == role, 'role' .. mate.slot .. role, role, 84, ROLE_COLORS[role]) then setBehavior(mate, 'role', role); end
                hoverTip(ROLE_INFO.HELP[role] .. '\n\n' .. ROLE_INFO.FOOTER);
            end
            -- (0.14) a quiet gold note when the Role restricts this job's default healing (ROLE_INFO.note)
            local note, noteRole, noteJob = ROLE_INFO.note(mate);
            if note then
                imgui.SameLine(0, 10);
                if imgui.TextColored then imgui.TextColored(C.gold, '(i) ' .. noteJob .. ' - Role: ' .. noteRole);
                else imgui.Text('(i) ' .. noteJob .. ' - Role: ' .. noteRole); end
                hoverTip(note);
            end
            imgui.Text('Mode  ');
            for _, mode in ipairs(MODES) do
                imgui.SameLine(0, 4);
                if colored(mate.mode == mode, 'mode' .. mate.slot .. mode, mode, 104) then setBehavior(mate, 'mode', mode); end
                hoverTip(ROLE_INFO.MODE[mode]);
            end
            imgui.Text('On/off');
            for _, name in ipairs(SWITCHES) do
                imgui.SameLine(0, 4);
                local on = hasBit(mate.mask, SW_BIT[name]);
                if colored(on, 'sw' .. mate.slot .. name, name, 58) then setSwitch(mate, name, not on); end
            end
            imgui.Separator();
        end
        -- (the legend has '%': TextWrapped reads its text as a printf format, so it is drawn wrapped and unformatted)
        for _, line in ipairs({ ROLE_INFO.LEGEND, ROLE_INFO.MODE_LEGEND, ROLE_INFO.NOTE_LEGEND }) do
            if imgui.PushTextWrapPos and imgui.PopTextWrapPos and imgui.TextUnformatted then
                imgui.PushTextWrapPos(0); imgui.TextUnformatted(line); imgui.PopTextWrapPos();
            else
                imgui.TextWrapped((line:gsub('%%', '%%%%')));
            end
        end
        imgui.Separator();
        imgui.Text('squadpanel ' .. tostring(addon.version));
    end
    imgui.End();
end

-- ---------------------------------------------------------------- the sheet window
local function number(value)
    if type(value) == 'table' then value = value[1] or value.x; end
    return tonumber(value) or 0;
end

local function tint(rgba, text)
    if imgui and imgui.TextColored then
        imgui.TextColored(rgba, tostring(text));
    else
        imgui.Text(tostring(text));
    end
end

local function wrappedColored(rgba, text)
    local id = rawget(_G, 'ImGuiCol_Text');
    local pushed = 0;
    if id ~= nil and imgui and imgui.PushStyleColor then
        local ok = pcall(imgui.PushStyleColor, id, rgba);
        if ok then pushed = 1; end
    end
    imgui.TextWrapped(tostring(text));
    if pushed > 0 and imgui and imgui.PopStyleColor then pcall(imgui.PopStyleColor, 1); end
end

local function screenPos()
    if not (imgui and imgui.GetCursorScreenPos) then return nil; end
    local ok, x, y = pcall(imgui.GetCursorScreenPos);
    if not ok then return nil; end
    if type(x) == 'table' then return { number(x[1] or x.x), number(x[2] or x.y) }; end
    return { number(x), number(y) };
end

local function contentWidth()
    if not (imgui and imgui.GetContentRegionAvail) then return 0; end
    local ok, width = pcall(imgui.GetContentRegionAvail);
    if not ok then return 0; end
    return number(width);
end

local function windowDraw()
    if not (imgui and imgui.GetWindowDrawList) then return nil; end
    local ok, draw = pcall(imgui.GetWindowDrawList);
    if ok then return draw; end
    return nil;
end

local function fillColor(rgba)
    if imgui and imgui.ColorConvertFloat4ToU32 then
        local ok, value = pcall(imgui.ColorConvertFloat4ToU32, rgba);
        if ok and value then return tonumber(value) or 0xFFFFFFFF; end
    end
    return 0xFFFFFFFF;
end

local function fillRect(draw, x, y, width, height, rgba, rounding)
    if draw == nil or width <= 0 or height <= 0 then return false; end
    local ok = pcall(function ()
        draw:AddRectFilled({ x, y }, { x + width, y + height }, fillColor(rgba), rounding or 3);
    end);
    return ok;
end

local function seek(x, y)
    if imgui and imgui.SetCursorScreenPos then pcall(imgui.SetCursorScreenPos, { x, y }); end
end

local function newLine()
    if imgui and imgui.NewLine then imgui.NewLine(); else imgui.Text(''); end
end

local function textWidth(text)
    if not (imgui and imgui.CalcTextSize) then return nil; end
    local ok, a = pcall(imgui.CalcTextSize, tostring(text or ''));
    if not ok then return nil; end
    if type(a) == 'table' then return number(a[1] or a.x); end
    if type(a) == 'number' then return a; end
    return nil;
end

-- Keeps long item names from running into the next column.
local function fit(text, maxWidth)
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

local function pushColors(list)
    if not (imgui and imgui.PushStyleColor and imgui.PopStyleColor) then return 0; end
    local pushed = 0;
    for _, item in ipairs(list) do
        local id = rawget(_G, item[1]);
        if id ~= nil then
            local ok = pcall(imgui.PushStyleColor, id, item[2]);
            if ok then pushed = pushed + 1; end
        end
    end
    return pushed;
end

local function pushVars(list)
    if not (imgui and imgui.PushStyleVar and imgui.PopStyleVar) then return 0; end
    local pushed = 0;
    for _, item in ipairs(list) do
        local id = rawget(_G, item[1]);
        if id ~= nil then
            local ok = pcall(imgui.PushStyleVar, id, item[2]);
            if ok then pushed = pushed + 1; end
        end
    end
    return pushed;
end

-- The role-coloured recruit bar from the main window, like Titan's Current Recruits list.
drawMateBar = function (mate, jobs)
    local role = string.lower(tostring(mate.role or 'auto'));
    local rgba = ROLE_COLORS[role] or ROLE_COLORS.auto;
    local label = string.format('%d   %s   (%s)   - %s', mate.slot, mate.name, jobs, ROLE_NAME[role] or role);
    local status = mate.out and 'OUT' or 'AWAY';
    local pos, width, draw = screenPos(), contentWidth(), windowDraw();
    local height = 26;
    if pos and width > 120 and fillRect(draw, pos[1], pos[2], width, height, { rgba[1] * 0.88, rgba[2] * 0.88, rgba[3] * 0.88, 0.94 }, 4) then
        fillRect(draw, pos[1], pos[2], 3, height, rgba, 0);
        seek(pos[1] + 9, pos[2] + 5);
        local textId = rawget(_G, 'ImGuiCol_Text');
        local pushed = 0;
        if textId ~= nil and imgui.PushStyleColor then
            local ok = pcall(imgui.PushStyleColor, textId, { 1, 1, 1, 1 });
            if ok then pushed = 1; end
        end
        imgui.Text(fit(label, width - 92));
        if pushed > 0 and imgui.PopStyleColor then pcall(imgui.PopStyleColor, pushed); end
        local statusWidth = textWidth(status) or 28;
        imgui.SameLine(width - statusWidth - 10, 0);
        tint({ 1, 1, 1, 0.75 }, status);
        seek(pos[1], pos[2] + height + 4);
    else
        imgui.Text(label .. '   (' .. status .. ')');
    end
end

local function heading(text)
    tint(C.gold, text);
end

local function drawHeader(h)
    local role = string.lower(tostring(h.role or 'auto'));
    local rgba = ROLE_COLORS[role] or ROLE_COLORS.auto;
    local jobs = tostring(h.job or '?') .. ' ' .. tostring(h.main or 0);
    if h.sub ~= '-' and h.sub ~= '' and h.sub ~= nil then jobs = jobs .. ' / ' .. tostring(h.sub) .. ' ' .. tostring(h.subLevel); end

    local pos, width, draw = screenPos(), contentWidth(), windowDraw();
    local height = 32;
    if pos and width > 0 and fillRect(draw, pos[1], pos[2], width, height, { rgba[1] * 0.82, rgba[2] * 0.82, rgba[3] * 0.82, 0.96 }, 4) then
        fillRect(draw, pos[1], pos[2], 3, height, rgba, 0);
        seek(pos[1] + 10, pos[2] + 7);
        local textId = rawget(_G, 'ImGuiCol_Text');
        local pushed = 0;
        if textId ~= nil and imgui.PushStyleColor then
            local ok = pcall(imgui.PushStyleColor, textId, { 1, 1, 1, 1 });
            if ok then pushed = 1; end
        end
        imgui.Text(fit(h.name, width - 180));
        if pushed > 0 and imgui.PopStyleColor then pcall(imgui.PopStyleColor, pushed); end
        imgui.SameLine(0, 8);
        tint({ 1, 1, 1, 0.82 }, jobs);
        local roleText = string.upper(ROLE_NAME[role] or role);
        local roleWidth = textWidth(roleText) or (#roleText * 7);
        if width > 220 then
            imgui.SameLine(width - roleWidth - 10, 0);
            tint({ 1, 1, 1, 0.68 }, roleText);
        end
        seek(pos[1], pos[2] + height + 5);
    else
        tint(C.gold, tostring(h.name) .. '   (' .. jobs .. ')');
    end
end

-- One compact row of vitals, each with a thin bar under it.
local function drawVitalRow(vitals)
    if not vitals or #vitals == 0 then return; end
    local pos, width, draw = screenPos(), contentWidth(), windowDraw();
    local gap = 8;
    local segment = width > 0 and math.floor((width - gap * (#vitals - 1)) / #vitals) or 0;
    if pos and draw and segment > 40 then
        for i, vital in ipairs(vitals) do
            local x = pos[1] + (i - 1) * (segment + gap);
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
        tint(C.text, table.concat(parts, '     '));
    end
end

local ICON = 26;

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
            fillRect(windowDraw(), pos[1], pos[2], ICON, ICON, { 1, 1, 1, 0.05 }, 4);
            local draw = windowDraw();
            if draw and draw.AddRect then
                pcall(function () draw:AddRect({ pos[1], pos[2] }, { pos[1] + ICON, pos[2] + ICON }, fillColor({ 1, 1, 1, 0.10 }), 4, 0, 1); end);
            end
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
end

local function renderSheet()
    if not S.sheetOpen[1] or not imgui then return; end
    local d = S.sheet;
    local title = 'Squad sheet  v' .. tostring(addon.version) .. '###sq_sheet';
    if d and d.hdr then
        title = string.format('%s (%s %d)###sq_sheet', d.hdr.name, tostring(d.hdr.job), tonumber(d.hdr.main) or 0);
    end
    imgui.SetNextWindowSize({ 560, 620 }, rawget(_G, 'ImGuiCond_FirstUseEver') or 4);
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
    local flags = (rawget(_G, 'ImGuiWindowFlags_NoCollapse') or 0);
    if imgui.Begin(title, S.sheetOpen, flags) then
        if d == nil or d.hdr == nil then
            tint(C.dim, now() < S.waitUntil and 'Asking the server...' or 'No answer from the server. Press Sheet again.');
        else
            local h = d.hdr;
            local width = contentWidth();
            drawHeader(h);

            local bits = { tostring(h.role or 'auto') };
            if h.mode and h.mode ~= '' then bits[#bits + 1] = h.mode; end
            if h.race and h.race ~= '' and h.race ~= '?' then bits[#bits + 1] = h.race; end
            local left = table.concat(bits, '  \194\183  ');
            local switches = {};
            for _, name in ipairs(SWITCHES) do
                switches[#switches + 1] = name .. ' ' .. (hasBit(h.mask or 15, SW_BIT[name]) and 'on' or 'off');
            end
            local right = table.concat(switches, '  ');
            local leftWidth, rightWidth = textWidth(left), textWidth(right);
            if leftWidth and rightWidth and width > 0 and leftWidth + rightWidth + 24 <= width then
                tint(C.dim, left);
                imgui.SameLine(width - rightWidth, 0);
                tint(C.faint, right);
            else
                tint(C.dim, left);
                tint(C.faint, right);
            end
            imgui.Dummy({ 0, 4 });

            drawVitalRow(d.vitals);
            if d.note then
                wrappedColored(C.faint, d.note);
                imgui.Dummy({ 0, 2 });
            end

            if d.stats or d.combat then
                imgui.Separator();
                heading('Current calculated stats');
                imgui.Dummy({ 0, 2 });
                local rows = math.max(d.stats and #d.stats or 0, d.combat and #d.combat or 0);
                local rightX = math.floor(width * 0.50);
                for i = 1, rows do
                    local s = d.stats and d.stats[i];
                    local c = d.combat and d.combat[i];
                    if s then
                        tint(C.dim, s[1]);
                        imgui.SameLine(56, 0);
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
                imgui.SameLine(56, 0);
                tint(C.text, table.concat(parts, '     '));
                newLine();
            end

            if d.jobs and #d.jobs > 0 then
                local parts = {};
                for i, j in ipairs(d.jobs) do
                    if i > 8 then break; end
                    parts[#parts + 1] = j[1] .. ' ' .. tostring(j[2]);
                end
                wrappedColored(C.text, 'Jobs: ' .. table.concat(parts, ', '));
            end

            imgui.Separator();
            heading('Equipped items');
            imgui.Dummy({ 0, 2 });
            local gearWidth = contentWidth();
            if gearWidth <= 0 then gearWidth = width; end
            local column = math.floor(gearWidth / 2);
            local textMax = math.max(40, column - ICON - 18);
            local eq = d.eq or {};
            for i = 1, 8 do
                drawGear(SHEET_LEFT[i], eq[SHEET_LEFT[i]], d.eqId and d.eqId[SHEET_LEFT[i]], textMax);
                imgui.SameLine(column, 0);
                drawGear(SHEET_RIGHT[i], eq[SHEET_RIGHT[i]], d.eqId and d.eqId[SHEET_RIGHT[i]], textMax);
                imgui.Dummy({ 0, 4 });
                newLine();
            end

            imgui.Separator();
            wrappedColored(C.faint, 'The stats are read from your squad mate while they are out, so they already include their gear. '
                .. 'Gear shown for a mate who is away is what they wear as this job.');
            imgui.Dummy({ 0, 2 });
            tint(C.faint, 'squadpanel ' .. tostring(addon.version));
        end
    end
    imgui.End();
    if colors > 0 then imgui.PopStyleColor(colors); end
    if vars > 0 then imgui.PopStyleVar(vars); end
end

-- ---------------------------------------------------------------- events
ashita.events.register('load', 'squadpanel_load', function ()
    say('squadpanel ' .. tostring(addon.version) .. ' loaded. Type /sq to open the squad panel.');
end);

ashita.events.register('d3d_present', 'squadpanel_present', function ()
    local t = now();
    pump(t);
    if S.open[1] and #S.queue == 0 and t - S.lastAsk > 15 then ask(); end    -- keeps the window current while it is open
    if S.sheetOpen[1] and #S.queue == 0 and t - S.lastSheetAsk > 5 then askSheet(); end   -- hit points and TP move, so the sheet is asked again more often
    if S.open[1] and t - S.duoRead >= 1 then readDuo(); end
    render();
    renderSheet();
end);

ashita.events.register('text_in', 'squadpanel_text_in', function (e)
    if e.blocked then return; end
    local text = strip(e.message_modified or e.message);
    local at = text:find('squadpanel:', 1, true);
    if at then
        if now() < S.waitUntil + 3 then e.blocked = true; end                -- hidden only while the panel asked for it
        onLine(text:sub(at + 11));
        return;
    end
    local sheetAt = text:find('squadsheet:', 1, true);
    if sheetAt then
        if now() < S.waitUntil + 3 then e.blocked = true; end
        onSheetLine(text:sub(sheetAt + 11));
        return;
    end
    if now() < S.hideUntil and (text:match('^!squad') or text:match(':%s*!squad%s')) then e.blocked = true; end   -- the echo of the panel's own commands
end);

ashita.events.register('command', 'squadpanel_command', function (e)
    local args = e.command:args();
    if #args == 0 then return; end
    local first = args[1]:lower();
    if first ~= '/sq' and first ~= '/squadpanel' then return; end
    e.blocked = true;
    local sub = (args[2] or ''):lower();
    if sub == 'refresh' then
        S.open[1] = true;
        ask();
    elseif sub == 'sheet' then
        local slot = tonumber(args[3] or '') or S.sheetSlot or (S.mates[1] and S.mates[1].slot);
        if slot == nil then
            S.open[1] = true;
            ask();
            say('no squad mates known yet: opening the panel first');
        else
            openSheet(slot);
        end
    elseif sub == 'on' or sub == 'off' then
        S.open[1] = (sub == 'on');
        if S.open[1] then ask(); end
    else
        S.open[1] = not S.open[1];
        if S.open[1] then ask(); end
    end
end);
