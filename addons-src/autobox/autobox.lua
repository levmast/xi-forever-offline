--[[
Gambits 2.2.207
A standalone Ashita v4 player-gambit engine (originally made for TitanXI under another name), with 18 editable job presets.
Scope: level 1-75 defaults, main/subjob checks, learned spells/abilities and merits.

INSTALL: addons/autobox/autobox.lua; /addon load autobox (the sheets live in config/addons/Gambits, as before)
2026-11-19: this addon was called Gambits. The name Gambits now belongs to the squad Rule Set editor (Gambits v2);
this one keeps your own character's rules under the name autobox, with the command /autobox. Its data folder is unchanged.
UI: /autobox       STOP: /autobox off

Actor switches: config/addons/Gambits/characters/<name_id>/switches.lua
Player job rules: config/addons/Gambits/jobs/<JOB>.lua
Generated Recruit actions: server AI only; old local Recruit sheets are removed on addon load.
Party names: display only; only player job rules execute.
Rules execute in array order. Gates are mandatory. First EXECUTABLE rule wins.
Only standard bag-to-inventory item moves are packet queued; no movement automation or automatic pulling. Generated recruits auto-engage their leader's battle target; their other actions are server controlled.

A queued command is an attempt, not evidence that a buff, debuff or heal landed.
Unknown target status, BLU sets, positioning and advanced pet state are NOT invented.
See Gambits_README.md for adapters, supported boundaries and test details.

Interface references consulted, implementation below is original:
https://github.com/AshitaXI/Ashita-v4beta/tree/main/addons/libs/annotations
https://github.com/ThornyFFXI/LuAshitacast
https://github.com/Windower/Lua/blob/dev/addons/libs/packets/fields.lua
]]

require('common');
local bit = require('bit');
addon.name = 'autobox';
addon.author = 'XI: Forever Offline';
addon.version = '2.2.210';
addon.desc = 'Autobox: rules for your own character (and the dualbox one), Parser, EXP Watch, Enemy Info. Formerly Gambits.';
addon.link = '';

local G = {};
_G.Gambits = G;
local E = {};
local S = {
    settings = nil, profile = nil, guestProfiles = {}, guestProfileText = {}, identity = nil, signature = nil,
    lastPoll = -10, lastTick = -10, lastPosition = nil, stationarySince = nil,
    zoneUntil = 0, lockUntil = 0, manualUntil = 0, pauseUntil = 0, userChatUntil = 0, nextBackgroundBridgeAt = 0,
    -- S.pending is the player-only compatibility view. Trust plans are actor-scoped.
    pending = nil, pendingByActor = {}, actorLocks = {}, outgoingIntent = nil, uncertain = {},
    timers = {}, control = {}, controlState = {}, controlActors = {}, controlPending = {}, bridgeSubmitted = {}, bridgeTraceLines = {}, buffs = {}, casts = {}, failures = {},
    availability = nil, logs = {}, why = {}, lastDecision = 'None', teamLoad = nil,
    actionStats = {submitted=0,outgoing=0,accepted=0,rejected=0,completed=0,uncertain=0},
    recastByActor = {}, recastRequest = nil, recastPollAt = -10,
    statusSnapshots = {}, statusRequest = nil, statusPollAt = -10,
    recruitStances = {},
    recruitCooldown = nil, recruitStatusNextAt = 0, recruitStatusRequestedAt = 0,
    recruitCommands = {},
    recruitJobMask = 0, recruitJobActor = nil,
    recruitSlotPending = {},
    recruitSlotConfirmed = {'tank','support','dps','dps','dps'},
    recruitSlotRoles = {'tank','support','dps','dps','dps'},
    optimizePending = nil, optimizeCommandAt = nil, sortPending = nil, sortCommandAt = nil,
    recastTotals = {}, recastLast = {}, itemTransfer = nil, itemCatalog = nil,
    lastBlock = 'Starting', cache = {}, buffNames = {}, providers = {},
    profilePath = nil, settingsText = nil, profileText = nil,
    switchPath = nil, switchText = nil, switches = nil, switchError = nil,
    configError = nil, profileError = nil, historyTime = 0,
    ui = { open = {false}, selected = 1, drag = nil, tab = 'Rules', edits = {}, pendingRecruitSlots = {}, sheetFlashUntil = 0, message = nil, messageUntil = 0,
        helpText = nil, helpLastText = nil, helpChangedAt = 0 },
    watch = { tab = 'GAMBITS', damage = {}, exp = {}, roster = {}, actor = nil,
        enemy = nil, enemyRequestAt = 0, enemyCache = {} },
};
local JOBS = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST',
               'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU', 'COR', 'PUP',
               'DNC', 'SCH', 'GEO', 'RUN' };
local JOB_IDS = {};
for id, name in ipairs(JOBS) do JOB_IDS[name] = id; end
local LAYERS = { 'emergency_survival', 'raise', 'emergency_healing', 'status_removal',
    'critical_job_mechanics', 'weapon_skill', 'buff_maintenance',
    'job_specific_actions', 'debuffs', 'offensive_magic', 'utility' };
local DEFAULT_GAMBIT_VIEW_ROWS = 13;
local MIN_GAMBIT_VIEW_ROWS = 5;
local DEFAULT = {
    Enabled = true, Debug = false, StationaryDelaySeconds = 0.35,
    ActionLockSeconds = 0.75, TickSeconds = 0.15, SettingsPollSeconds = 0.50,
    ZoneDelaySeconds = 4.0, MovementEpsilon = 0.015, ManualPauseSeconds = 2.0,
    HealAlliance = false, RaiseInCombat = false,
    AllowUnclaimedTargets = false, AllowSpecialAbilities = false,
    AllowConsumables = false, AllowAreaDamage = false, PauseWhileInvisible = true,
    PartyBuffMaxAge = 300, TargetRange = 20, MPReserve = 10,
    MaxDefaultLevel = 75, AbilityIdOffset = 0, PetCommandIdOffset = 0,
    UiScalePercent = 100,
    VisibleGambitRows = DEFAULT_GAMBIT_VIEW_ROWS,
    MouseCapture = true,
    UseServerBridge = false, TrustServerBridge = true, FallbackVisibleCommands = true,
    RequireVerifiedTrustCapabilities = false, -- Compatibility fallback; see patch notes before enabling.
};
local WS = {
    -- Strongest/preferred first. E.prepare skips anything not actually learned/available.
    [1] = {'Asuran Fists','Dragon Kick','Howling Fist','Raging Fists','Backhand Blow','One Inch Punch','Shoulder Tackle','Combo'},
    [2] = {'Mandalic Stab','Mercy Stroke','Evisceration','Shark Bite','Dancing Edge','Viper Bite','Shadowstitch','Wasp Sting'},
    [3] = {'Death Blossom','Atonement','Knights of Round','Savage Blade','Swift Blade','Vorpal Blade','Spirits Within','Red Lotus Blade','Burning Blade','Fast Blade'},
    [4] = {'Scourge','Ground Strike','Spinning Slash','Sickle Moon','Frostbite','Freezebite','Power Slash','Hard Slash'},
    [5] = {'Primal Rend','Onslaught','Rampage','Mistral Axe','Calamity','Raging Axe'},
    [6] = {"King's Justice",'Metatron Torment','Steel Cyclone','Raging Rush','Full Break','Keen Edge','Sturmwind','Shield Break'},
    [7] = {'Insurgency','Catastrophe','Spiral Hell','Cross Reaper','Guillotine','Vorpal Scythe','Nightmare Scythe','Shadow of Death','Slice'},
    [8] = {'Drakesbane','Geirskogul','Wheeling Thrust','Penta Thrust','Skewer','Raiden Thrust','Leg Sweep','Thunder Thrust','Double Thrust'},
    [9] = {'Blade: Kamu','Blade: Metsu','Blade: Ku','Blade: Ten','Blade: Jin','Blade: Chi','Blade: Teki','Blade: Retsu','Blade: Rin'},
    [10] = {'Tachi: Rana','Tachi: Kaiten','Tachi: Kasha','Tachi: Gekko','Tachi: Yukikaze','Tachi: Koki','Tachi: Jinpu','Tachi: Hobaku','Tachi: Enpi'},
    [11] = {'Mystic Boon','Randgrith','Black Halo','Hexa Strike','Judgment','True Strike','Skullbreaker','Brainshaker','Seraph Strike','Shining Strike'},
    [12] = {'Garland of Bliss','Vidohunir','Gate of Tartarus','Retribution','Spirit Taker','Full Swing','Shell Crusher','Heavy Swing'},
    [25] = {'Namas Arrow','Empyreal Arrow','Sidewinder','Arching Arrow','Piercing Arrow','Flaming Arrow'},
    [26] = {'Wildfire','Leaden Salute','Trueflight','Coronach','Detonator','Slug Shot','Sniper Shot','Split Shot','Hot Shot'},
};-- Wildfire is not part of the default level-75 list. It remains usable as a custom rule.
table.remove(WS[26], 1);
local SPECIAL = {
    ['Mighty Strikes']=true, ['Hundred Fists']=true, Benediction=true, Manafont=true,
    Chainspell=true, ['Perfect Dodge']=true, Invincible=true, ['Blood Weapon']=true,
    Familiar=true, ['Soul Voice']=true, ['Eagle Eye Shot']=true, ['Meikyo Shisui']=true,
    Mijin=true, ['Mijin Gakure']=true, ['Call Wyvern']=false, ['Spirit Surge']=true,
    ['Astral Flow']=true, ['Azure Lore']=true, ['Wild Card']=true, Overdrive=true,
};
local JOB_ABILITY_CATALOG, JOB_WS_CATALOG, TRUST_PICKER, TRUST_PICKER_BY_KEY, TRUST_PICKER_BY_NAME;
local TOOLS = {
    Utsusemi='Shihei', Katon='Uchitake', Hyoton='Tsurara', Huton='Kawahori-ogi',
    Doton='Makibishi', Raiton='Hiraishin', Suiton='Mizu-deppo',
    Kurayami='Sairui-ran', Hojo='Kaginawa', Dokumori='Kodoku', Jubaku='Jusatsu',
    Monomi='Sanjaku-tenugui', Tonko='Shinobi-tabi',
};

function E.call(obj, method, ...)
    if obj == nil then return nil; end
    local ok, fn = pcall(function() return obj[method]; end);
    -- Some Ashita SDK builds expose bound methods as callable userdata rather than
    -- plain Lua functions. Let pcall determine callability instead of rejecting
    -- those bindings solely because type(fn) is not "function".
    if not ok or fn == nil then return nil; end
    local success, value = pcall(fn, obj, ...);
    if success then return value; end
    return nil;
end
function E.number(value, fallback)
    local n = tonumber(value);
    if n == nil or n ~= n or n == math.huge or n == -math.huge then return fallback; end
    return n;
end
function E.clamp(value,minValue,maxValue)
    value=E.number(value,minValue) or minValue;
    if value<minValue then return minValue; end
    if value>maxValue then return maxValue; end
    return value;
end
function E.truth(v) return v == true or (type(v) == 'number' and v ~= 0); end
function E.now()
    if ashita and ashita.time and type(ashita.time.get_tick64) == 'function' then
        local ok, n = pcall(ashita.time.get_tick64);
        if ok and type(n) == 'number' then return n / 1000; end
    end
    return os.clock(); -- Compatibility/test fallback; Ashita v4 uses uptime above.
end
function E.clone(v, seen)
    if type(v) ~= 'table' then return v; end
    seen = seen or {};
    if seen[v] then return seen[v]; end
    local r = {}; seen[v] = r;
    for k, value in pairs(v) do r[E.clone(k, seen)] = E.clone(value, seen); end
    return r;
end
function E.lower(v) return tostring(v or ''):gsub('%z.*', ''):lower(); end
function E.contains(list, value)
    for _, v in ipairs(list or {}) do if v == value then return true; end end
    return false;
end
function E.log(text, force, silent)
    local message = tostring(text);
    table.insert(S.logs, 1, {time = os.date('%H:%M:%S'), text = message});
    if #S.logs > 100 then table.remove(S.logs); end
    if not silent and (force or (S.settings and S.settings.Debug)) then print('[Gambits] ' .. message); end
end
function E.provider(name, ...)
    local f = S.providers[name];
    if type(f) ~= 'function' then return nil; end
    local ok, value = pcall(f, ...);
    if ok then return value; end
    E.log('Provider ' .. name .. ' failed: ' .. tostring(value));
    return nil;
end
function E.root()
    local base = E.call(AshitaCore, 'GetInstallPath');
    if type(base) ~= 'string' or base == '' then return nil; end
    if not base:match('[/\\]$') then base = base .. '/'; end
    -- Personal Gambit data intentionally lives outside the launcher-synced addon
    -- code folder so Gambits.lua updates cannot overwrite player sheets.
    if S.rootCache and S.rootCache.base == base then return S.rootCache.path; end
    local new = base .. 'config/addons/Gambits';
    local path = E.migrate_root(base, new) or (new .. '/');
    S.rootCache = { base = base, path = path };
    return path;
end
-- One-time move of the sheets from the addon's earlier settings folder
-- (config/addons/TitanGambits) to config/addons/Gambits. The whole folder is
-- renamed in one step, so every sheet, switch file and backup comes along.
-- If the rename cannot happen, keep using the old folder so nothing is lost.
function E.migrate_root(base, new)
    local old = base .. 'config/addons/TitanGambits';
    local function has(dir) local f = io.open(dir .. '/settings.lua', 'rb'); if f then f:close(); return true; end return false; end
    if has(new) or not has(old) then return nil; end
    local ok, err = os.rename(old, new);
    if ok then
        S.rootMigrated = 'Moved your Gambit sheets from config/addons/TitanGambits to config/addons/Gambits.';
        return nil;
    end
    S.rootMigrated = 'Could not move config/addons/TitanGambits to config/addons/Gambits (' .. tostring(err) .. '); still using the old folder. Close anything using it and reload Gambits.';
    return old .. '/';
end
-- (2026-11-19) the server menu (servermenu) only sends /autobox commands while this addon is loaded: it looks for this
-- flag file. Written at load, removed at unload.
function E.loaded_flag(on)
    pcall(function()
        local base = AshitaCore:GetInstallPath();
        if type(base) ~= 'string' or base == '' then return; end
        if not base:match('[/\\]$') then base = base .. '/'; end
        local path = base .. 'config/addons/Gambits/autobox_loaded.flag';
        if on then
            local f = io.open(path, 'w');
            if f then f:write(tostring(os.time())); f:close(); end
        else
            os.remove(path);
        end
    end);
end
function E.personal_path_guard(path)
    local p=tostring(path or ''):gsub('\\','/'):lower();
    local inConfig = p:find('/config/addons/gambits/',1,true) or p:find('/config/addons/titangambits/',1,true);
    if not inConfig and (p:find('/addons/gambits/',1,true) or p:find('/addons/titangambits/',1,true) or p:find('/addons/autobox/',1,true)) then
        return false,'Refusing to save Gambits player data inside the launcher-synced addon folder.';
    end
    if not inConfig then
        return false,'Refusing to save Gambits player data outside config/addons/Gambits.';
    end
    return true;
end
function E.mkdir(path)
    if not path then return false; end
    if ashita and ashita.fs and ashita.fs.create_directory then
        local ok = pcall(ashita.fs.create_directory, path);
        return ok;
    end
    return false;
end
function E.readfile(path)
    if not path then return nil; end
    local f = io.open(path, 'rb'); if not f then return nil; end
    local txt = f:read(1024 * 1024 + 1); f:close();
    if txt and #txt > 1024 * 1024 then return nil, 'File exceeds 1 MB limit'; end
    return txt;
end
function E.serialize(v, depth, seen)
    depth = depth or 0; seen = seen or {};
    if depth > 20 then error('Configuration is too deeply nested'); end
    local t = type(v);
    if t == 'string' then return string.format('%q', v); end
    if t == 'boolean' then return v and 'true' or 'false'; end
    if t == 'number' then
        if E.number(v) == nil then error('Invalid numeric value'); end
        return string.format('%.12g', v);
    end
    if t ~= 'table' then error('Configuration must contain only data'); end
    if seen[v] then error('Cyclic configuration'); end
    seen[v] = true;
    local parts = {'{\n'}; local keys = {};
    for k in pairs(v) do
        if type(k) ~= 'number' and type(k) ~= 'string' then error('Invalid table key'); end
        keys[#keys + 1] = k;
    end
    table.sort(keys, function(a,b)
        if type(a) ~= type(b) then return type(a) == 'number'; end
        return a < b;
    end);
    local reserved={['and']=true,['break']=true,['do']=true,['else']=true,['elseif']=true,['end']=true,
        ['false']=true,['for']=true,['function']=true,['if']=true,['in']=true,['local']=true,['nil']=true,
        ['not']=true,['or']=true,['repeat']=true,['return']=true,['then']=true,['true']=true,['until']=true,['while']=true,['goto']=true};
    for _, k in ipairs(keys) do
        local label;
        if type(k)=='string' and k:match('^[%a_][%w_]*$') and not reserved[k] then label=k;
        else label='[' .. E.serialize(k) .. ']'; end
        parts[#parts+1] = string.rep('    ', depth+1) .. label .. ' = '
            .. E.serialize(v[k], depth+1, seen) .. ',\n';
    end
    parts[#parts+1] = string.rep('    ', depth) .. '}'; seen[v] = nil;
    return table.concat(parts);
end
function E.parse(txt, label)
    if type(txt) ~= 'string' then return nil, 'Missing configuration'; end
    local fn, err;
    if setfenv then
        fn, err = loadstring(txt, '@' .. (label or 'gambits-config'));
        if fn then setfenv(fn, {}); end
    else
        fn, err = load(txt, '@' .. (label or 'gambits-config'), 't', {});
    end
    if not fn then return nil, err; end
    -- A config is a returned table, not an unrestricted addon script.
    local oldHook, oldMask, oldCount;
    if debug and debug.sethook and debug.gethook then
        oldHook, oldMask, oldCount = debug.gethook();
        debug.sethook(function() error('Configuration instruction limit exceeded'); end, '', 100000);
    end
    local ok, value = pcall(fn);
    if debug and debug.sethook and debug.gethook then debug.sethook(oldHook, oldMask, oldCount); end
    if not ok or type(value) ~= 'table' then return nil, tostring(value or 'Expected return { ... }'); end
    local valid, why = pcall(E.serialize, value);
    if not valid then return nil, why; end
    return value;
end
function E.writefile(path, value, comment)
    local safe, safetyError=E.personal_path_guard(path);
    if not safe then return false,safetyError; end
    local ok, serialized = pcall(E.serialize, value);
    if not ok then return false, serialized; end
    local data = '-- ' .. (comment or 'Player Gambits configuration.') .. '\nreturn ' .. serialized .. '\n';
    local tmp, bak = path .. '.tmp', path .. '.bak';
    local f, err = io.open(tmp, 'wb'); if not f then return false, err; end
    local wrote, why = f:write(data); local closed = f:close();
    if not wrote or not closed then os.remove(tmp); return false, why or 'Close failed'; end
    local original = E.readfile(path);
    if original then
        os.remove(bak);
        local moved, moveError = os.rename(path, bak);
        if not moved then os.remove(tmp); return false, moveError; end
    end
    local replaced, replaceError = os.rename(tmp, path);
    if not replaced then
        if original then os.rename(bak, path); end
        os.remove(tmp); return false, replaceError;
    end
    return true, data;
end
function E.settings_validate(data)
    local out = E.clone(data or {});
    for k,v in pairs(DEFAULT) do if out[k] == nil then out[k] = v; end end
    for k,v in pairs(DEFAULT) do
        if type(v) == 'boolean' and type(out[k]) ~= 'boolean' then return nil, k .. ' must be boolean'; end
        if type(v) == 'number' and E.number(out[k]) == nil then return nil, k .. ' must be finite'; end
    end
    local limits = {
        StationaryDelaySeconds={0.10,5}, ActionLockSeconds={0.5,10}, TickSeconds={0.1,2},
        SettingsPollSeconds={0.25,10}, ZoneDelaySeconds={2,30}, MovementEpsilon={0.001,0.05},
        ManualPauseSeconds={1,30}, PartyBuffMaxAge={10,3600}, TargetRange={1,30},
        MPReserve={0,10000}, MaxDefaultLevel={1,99}, AbilityIdOffset={-512,0}, PetCommandIdOffset={-512,0},
        UiScalePercent={70,200}, VisibleGambitRows={MIN_GAMBIT_VIEW_ROWS,99},
    };
    for k, range in pairs(limits) do
        out[k] = math.max(range[1], math.min(range[2], out[k]));
    end
    return out;
end
function E.settings_load(force)
    local root = E.root(); if not root then S.configError = 'No Ashita install path'; return false; end
    local path = root .. 'settings.lua';
    local txt, readError = E.readfile(path);
    if not txt and not readError then
        -- Startup only: a missing existing file during launcher replacement is not an OFF/ON request.
        if S.settingsText then S.configError = 'Shared settings temporarily unavailable'; return false; end
        E.mkdir(root);
        local ok, data = E.writefile(path, DEFAULT, 'Shared Gambits options. Individual master switches live under characters.');
        if not ok then S.configError = tostring(data); return false; end
        txt = data;
    end
    if not force and txt == S.settingsText and not S.configError then return true; end
    local parsed, err = E.parse(txt, path);
    if parsed then parsed, err = E.settings_validate(parsed); end
    if not parsed then
        S.configError = readError or err; E.log('Shared configuration rejected: ' .. tostring(S.configError));
        return false;
    end
    S.settings = parsed; S.settingsText = txt; S.configError = nil; return true;
end
function E.settings_change(key, value)
    if not E.settings_load(true) then return false, S.configError; end
    local data = E.clone(S.settings); data[key] = value;
    local checked, err = E.settings_validate(data); if not checked then return false, err; end
    local ok, txt = E.writefile(E.root() .. 'settings.lua', checked,
        'Shared Gambits options. Individual master switches live under characters.');
    if ok then
        S.settings = checked; S.settingsText = txt;
    else E.log('Save failed: ' .. tostring(txt), true); end
    return ok, txt;
end
function E.position(entity, index)
    if not index or index == 0 then return nil; end
    local x = E.call(entity, 'GetLocalPositionX', index);
    local y = E.call(entity, 'GetLocalPositionY', index);
    local z = E.call(entity, 'GetLocalPositionZ', index);
    if E.number(x) == nil or E.number(y) == nil or E.number(z) == nil then return nil; end
    return {x=x,y=y,z=z};
end
function E.distance(a,b)
    if not a or not b then return nil; end
    return math.sqrt((a.x-b.x)^2 + (a.y-b.y)^2 + (a.z-b.z)^2);
end
function E.sample_motion(ctx)
    if not ctx.position then
        S.lastPosition = nil; S.stationarySince = nil; ctx.moving = true; ctx.stationarySeconds = 0;
        return;
    end
    local epsilon = (S.settings or DEFAULT).MovementEpsilon;
    local dist = E.distance(ctx.position, S.lastPosition);
    -- Anchor is not advanced for sub-epsilon movement, so slow movement accumulates.
    if not dist or dist > epsilon then
        S.lastPosition = E.clone(ctx.position); S.stationarySince = ctx.now; ctx.moving = true;
    else ctx.moving = false; end
    ctx.stationarySeconds = ctx.now - (S.stationarySince or ctx.now);
end
function E.buffname(id)
    if S.buffNames[id] then return S.buffNames[id]; end
    local resources = E.call(AshitaCore, 'GetResourceManager');
    local name = E.call(resources, 'GetString', 'buffs.names', id);
    if type(name) == 'string' then S.buffNames[id] = E.lower(name); return S.buffNames[id]; end
    return '';
end
function E.buffset(list)
    if list == nil then return nil; end
    local set = {};
    local readable = false;
    local function add(id)
        id = E.number(id);
        if id ~= nil then
            readable = true;
            if id >= 0 and id < 1023 and id ~= 255 and id ~= 1023 then
                set[id] = (set[id] or 0) + 1;
                local name = E.buffname(id);
                if name ~= '' then set[name] = (set[name] or 0) + 1; end
            end
        end
    end
    if type(list) == 'table' then
        for _, id in pairs(list) do add(id); end
        readable = true;
    else
        local zeroBased = false;
        for i=0,31 do
            local ok, id = pcall(function() return list[i]; end);
            if ok and id ~= nil then zeroBased = true; add(id); end
        end
        if not zeroBased then
            for i=1,32 do
                local ok, id = pcall(function() return list[i]; end);
                if ok and id ~= nil then add(id); end
            end
        end
    end
    return readable and set or nil;
end

function E.describe_sequence(value)
    if value == nil then return 'nil'; end
    local kind = type(value);
    local ok, count = pcall(function() return #value; end);
    if ok and type(count) == 'number' then return kind .. '[' .. tostring(count) .. ']'; end
    return kind;
end

function E.status_icon_ids(icons, bitmask)
    if icons == nil then return nil; end
    local values = {};
    local zeroBased = false;
    local okZero, firstZero = pcall(function() return icons[0]; end);
    if okZero and firstZero ~= nil then zeroBased = true; end
    for i=0,31 do
        local key = zeroBased and i or i + 1;
        local ok, value = pcall(function() return icons[key]; end);
        if ok and value ~= nil then values[i + 1] = E.number(value); end
    end
    if next(values) == nil then return nil; end

    -- Party status memory stores the low byte for each icon plus a packed
    -- two-bit high value. Recombine those values when the SDK exposes the mask.
    local mask = E.number(bitmask);
    local ids = {};
    for i=1,32 do
        local low = values[i];
        if low ~= nil then
            local high = mask and math.floor(mask / 4 ^ (i - 1)) % 4 or 0;
            ids[#ids + 1] = low + high * 256;
        end
    end
    return ids;
end

function E.party_buffset(ctx, member)
    local party = ctx.partyMemory;
    if party == nil or member == nil then return nil; end
    for slot=0,4 do
        local serverId = E.number(E.call(party, 'GetStatusIconsServerId', slot));
        local targetIndex = E.number(E.call(party, 'GetStatusIconsTargetIndex', slot));
        if serverId == member.id and targetIndex == member.entityIndex then
            local icons = E.call(party, 'GetStatusIcons', slot);
            local mask = E.call(party, 'GetStatusIconsBitMask', slot);
            local ids = E.status_icon_ids(icons, mask);
            local set = E.buffset(ids);
            if set ~= nil then return set; end
        end
    end
    return nil;
end

function E.self_buffset(ctx, member)
    local probes = {};
    local directValue = E.call(ctx.player,'GetBuffs');
    probes[#probes + 1] = 'GetBuffs=' .. E.describe_sequence(directValue);
    local direct = E.buffset(directValue);
    if direct ~= nil then S.buffProbe=table.concat(probes,', '); return direct,'GetBuffs'; end

    local raw = E.call(ctx.player,'GetRawStructure');
    probes[#probes + 1] = 'Raw=' .. E.describe_sequence(raw);
    if raw ~= nil then
        local ok, value = pcall(function() return raw.Buffs; end);
        local set = ok and E.buffset(value) or nil;
        if set ~= nil then S.buffProbe=table.concat(probes,', '); return set,'Raw.Buffs'; end
    end

    -- IParty retains the latest 0x076 status-icon update in memory. Reading it
    -- here also covers addons loaded after that packet was originally received,
    -- and its high-bit mask preserves status IDs above 255.
    local partySet = E.party_buffset(ctx, member);
    probes[#probes + 1] = 'Party=' .. (partySet and 'ready' or 'nil');
    if partySet ~= nil then S.buffProbe=table.concat(probes,', '); return partySet,'Party status memory'; end

    local packet = member and S.buffs[member.id];
    if packet and packet.entityIndex == member.entityIndex and ctx.now - packet.time <= ctx.settings.PartyBuffMaxAge then
        local set = E.buffset(packet.ids);
        if set ~= nil then S.buffProbe=table.concat(probes,', '); return set,'Packet 0x076'; end
    end
    probes[#probes + 1] = 'Packet=nil';

    -- GetStatusIcons and Raw.StatusIcons contain low-byte icon data on some
    -- builds. They are still useful as final compatibility fallbacks when the
    -- combined buff list and party high-bit mask are unavailable.
    local iconValue = E.call(ctx.player,'GetStatusIcons');
    probes[#probes + 1] = 'GetStatusIcons=' .. E.describe_sequence(iconValue);
    local icons = E.buffset(iconValue);
    if icons ~= nil then S.buffProbe=table.concat(probes,', '); return icons,'GetStatusIcons'; end
    if raw ~= nil then
        local ok, value = pcall(function() return raw.StatusIcons; end);
        local set = ok and E.buffset(value) or nil;
        if set ~= nil then S.buffProbe=table.concat(probes,', '); return set,'Raw.StatusIcons'; end
    end
    S.buffProbe=table.concat(probes,', ');
    return nil,'Unavailable';
end
function E.hasbuff(target, name)
    if not target or target.buffs == nil then return nil; end
    if type(name) == 'table' then
        for _, n in ipairs(name) do if E.hasbuff(target, n) then return true; end end
        return false;
    end
    if name == 'Utsusemi' then name='Copy Image*'; end
    if name == 'Copy Image*' then
        for k,v in pairs(target.buffs) do
            if type(k) == 'string' and k:find('copy image',1,true) == 1 and v > 0 then return true; end
        end
        for _, n in ipairs({66,444,445,446}) do if target.buffs[n] then return true; end end
        return false;
    end
    for _, alias in ipairs(E.status_aliases(name)) do
        local k = type(alias) == 'number' and alias or E.lower(alias);
        if (target.buffs[k] or 0) > 0 then return true; end
    end
    return false;
end
function E.status_count(target, name)
    if not target or type(target.buffs)~='table' then return nil; end
    if name and tostring(name)~='' then
        local numericTotal=0;
        local namedMax=0;
        local seen={};
        for _,alias in ipairs(E.status_aliases(name)) do
            local key=type(alias)=='number' and alias or E.lower(alias);
            if not seen[key] then
                seen[key]=true;
                local count=E.number(target.buffs[key],0) or 0;
                if type(key)=='number' then numericTotal=numericTotal+count;
                else namedMax=math.max(namedMax,count); end
            end
        end
        -- Numeric keys are observed instances. Names are aliases, not new stacks.
        return math.max(numericTotal,namedMax);
    end
    local total=0;
    for key,count in pairs(target.buffs) do
        if type(key)=='number' and type(count)=='number' and count>0 then total=total+count; end
    end
    return total;
end
function E.role_name(member)
    local main=member and member.mainJob;
    local sub=member and member.subJob;
    if E.contains({'PLD','RUN','NIN'},main) or (main=='WAR' and sub=='NIN') then return 'tank'; end
    if E.contains({'WHM','SCH'},main) then return 'healer'; end
    if E.contains({'BLM','SMN'},main) then return 'caster'; end
    if E.contains({'BRD','COR','GEO'},main) then return 'support'; end
    if E.contains({'RNG'},main) then return 'ranged'; end
    return 'melee';
end
-- Player Target picker roles follow Titan's generated Recruit pool membership.
-- Keep this separate from the older, more granular role labels used by saved rules.
local PARTY_TARGET_POOLS={
    party_pool_tank={WAR=true,PLD=true,NIN=true,RUN=true},
    party_pool_support={WHM=true,RDM=true,BRD=true,DNC=true,GEO=true,SMN=true,SCH=true,COR=true},
    party_pool_dps={BLM=true,THF=true,MNK=true,SAM=true,DRK=true,DRG=true,BLU=true,BST=true,RNG=true,PUP=true},
};
function E.member_matches_target_role(member,target)
    if PARTY_TARGET_POOLS[target] then return PARTY_TARGET_POOLS[target][member and member.mainJob] == true; end
    if target=='party_tank' or target=='alliance_tank' then return E.role_name(member)=='tank'; end
    if target=='party_healer' or target=='alliance_healer' then return E.role_name(member)=='healer'; end
    if target=='party_melee' then return E.role_name(member)=='melee'; end
    if target=='party_ranged' then return E.role_name(member)=='ranged'; end
    if target=='party_caster' then return E.role_name(member)=='caster'; end
    if target=='party_support' then return E.role_name(member)=='support'; end
    return true;
end
function E.equipped(ctx, slot)
    local eq = E.call(ctx.inventory, 'GetEquippedItem', slot);
    local encoded = eq and E.number(eq.Index);
    if not encoded or encoded == 0 then return nil; end
    local item = E.call(ctx.inventory, 'GetContainerItem', math.floor(encoded / 256) % 256, encoded % 256);
    if not item or not item.Id or item.Id == 0 then return nil; end
    local res = E.call(ctx.resources, 'GetItemById', item.Id);
    return {id=item.Id, count=item.Count or 0, resource=res,
        name=res and res.Name and res.Name[1] or '', skill=res and res.Skill or 0};
end
local PLAYER_ITEM_BAGS={0,3,5,6,7}; -- Inventory, temporary, satchel, sack, case.
-- Match the server-side !sort managed set. These are container IDs, not item counts.
local MANAGED_INVENTORY_BAGS={0,5,6,7,8,10,11,12,13,14,15,16};
function E.inventory_usage(inventory)
    if not inventory then return nil; end
    local occupied,capacity=0,0;
    for _,bag in ipairs(MANAGED_INVENTORY_BAGS) do
        local used=E.call(inventory,'GetContainerCount',bag);
        local maximum=E.call(inventory,'GetContainerCountMax',bag);
        if type(used)~='number' or type(maximum)~='number' or maximum<=0 or maximum>120
            or used<0 or used>maximum then return nil; end
        -- GetContainerCount counts occupied item slots; a stack contributes one.
        occupied=occupied+used;
        capacity=capacity+maximum;
    end
    return occupied,capacity;
end
function E.player_item_location(ctx,name)
    local res=E.call(ctx.resources,'GetItemByName',name,0);
    if not res or not res.Id or res.Type~=7 then return nil; end
    for _,bag in ipairs(PLAYER_ITEM_BAGS) do
        local count=E.call(ctx.inventory,'GetContainerCountMax',bag);
        if type(count)=='number' then
            for slot=1,math.min(count,120) do
                local item=E.call(ctx.inventory,'GetContainerItem',bag,slot);
                if item and item.Id==res.Id and (item.Count or 0)>0 then
                    return {bag=bag,slot=slot,count=item.Count,id=res.Id};
                end
            end
        end
    end
    return nil;
end
function E.free_inventory_slot(ctx)
    local count=E.call(ctx.inventory,'GetContainerCountMax',0);
    if type(count)~='number' then return nil; end
    for slot=1,math.min(count,120) do
        local item=E.call(ctx.inventory,'GetContainerItem',0,slot);
        if not item or not item.Id or item.Id==0 then return slot; end
    end
    return nil;
end
function E.itemcount(ctx, name, inventoryOnly)
    ctx.itemCounts = ctx.itemCounts or {};
    local key=(inventoryOnly and 'usable:' or 'all:')..tostring(name);
    if ctx.itemCounts[key] ~= nil then return ctx.itemCounts[key]; end
    local res = E.call(ctx.resources, 'GetItemByName', name, 0);
    if not res or not res.Id then ctx.itemCounts[key] = 0; return 0; end
    local total = 0;
    for _,bag in ipairs(inventoryOnly and {0,3} or PLAYER_ITEM_BAGS) do
        local count = E.call(ctx.inventory, 'GetContainerCountMax', bag);
        if type(count) == 'number' then
            for i=1,math.min(count,100) do
                local item = E.call(ctx.inventory, 'GetContainerItem',bag,i);
                if item and item.Id == res.Id then total=total+(item.Count or 0); end
            end
        end
    end
    ctx.itemCounts[key] = total; return total;
end
function E.apply_status_snapshot(ctx,target)
    if not ctx or not target then return false; end
    local snapshot=S.statusSnapshots[target.id];
    if not snapshot or snapshot.zone~=ctx.zone or snapshot.entityIndex~=target.entityIndex
        or ctx.now-snapshot.receivedAt>3 then return false; end
    target.buffs=E.buffset(snapshot.ids);
    target.buffSource='Server status snapshot';
    target.buffObservedAt=snapshot.receivedAt;
    target.dispellable=snapshot.dispellable;
    target.mpMax=snapshot.mpMax;
    return target.buffs~=nil;
end

function E.request_status_snapshot(ctx,target)
    if not ctx or ctx.generatedRecruit or not ctx.self or not target or not target.id or not target.entityIndex then return false; end
    -- Offline build: there is no server helper to ask. For a monster, record that none of the effects the engine could apply are on it
    -- and that it has nothing to dispel; the row's own per-target cooldown stops the same spell being cast again straight away.
    if target.isMonster then
        S.statusSnapshots[target.id]={zone=ctx.zone,entityIndex=target.entityIndex,receivedAt=E.now(),ids={},dispellable=false,mpMax=0};
        return true;
    end
    local now=E.now();
    if S.statusRequest and now-S.statusRequest.sentAt<3 then return false; end
    if now-(S.statusPollAt or -10)<1.1 then return false; end
    local nonce=math.random(1,999999999);
    local command='/say !gambit status '..math.floor(target.id)..' '..nonce;
    local sent=E.send_bridge_command(command,true,{origin='status_request',actorId=ctx.self.id,
        targetId=target.id,targetIndex=target.entityIndex});
    if sent then
        S.statusPollAt=now;
        S.statusRequest={nonce=nonce,targetId=target.id,targetIndex=target.entityIndex,
            zone=ctx.zone,ownerId=ctx.self.id,sentAt=now};
    end
    return sent;
end

function E.member(ctx, index)
    if not E.truth(E.call(ctx.partyMemory,'GetMemberIsActive',index)) then return nil; end
    local m = {index=index, id=E.call(ctx.partyMemory,'GetMemberServerId',index),
        name=E.call(ctx.partyMemory,'GetMemberName',index),
        entityIndex=E.call(ctx.partyMemory,'GetMemberTargetIndex',index),
        zone=E.call(ctx.partyMemory,'GetMemberZone',index),
        hp=E.call(ctx.partyMemory,'GetMemberHP',index), mp=E.call(ctx.partyMemory,'GetMemberMP',index),
        hpp=E.call(ctx.partyMemory,'GetMemberHPPercent',index), mpp=E.call(ctx.partyMemory,'GetMemberMPPercent',index),
        tp=E.call(ctx.partyMemory,'GetMemberTP',index),
        mainJob=JOBS[E.call(ctx.partyMemory,'GetMemberMainJob',index)],
        mainLevel=E.call(ctx.partyMemory,'GetMemberMainJobLevel',index),
        subJob=JOBS[E.call(ctx.partyMemory,'GetMemberSubJob',index)],
        subLevel=E.call(ctx.partyMemory,'GetMemberSubJobLevel',index),
    };
    if not m.id or m.id == 0 or not m.entityIndex or m.entityIndex == 0 or type(m.name) ~= 'string' then return nil; end
    if E.call(ctx.entityMemory,'GetServerId',m.entityIndex) ~= m.id then return nil; end
    m.targetIndex=m.entityIndex;
    m.position=E.position(ctx.entityMemory,m.entityIndex); m.distance=E.distance(ctx.position,m.position);
    m.status=E.call(ctx.entityMemory,'GetStatus',m.entityIndex);
    if E.number(m.hp) == nil or E.number(m.hpp) == nil then return nil; end
    m.alive=m.hp>0 and m.hpp>0; m.dead=m.hp==0 and m.hpp==0 and (m.status==2 or m.status==3);
    if m.mpp and m.mpp>0 and m.mp then m.mpMax=math.floor(m.mp*100/m.mpp+0.5); end
    if m.hpp>0 then m.hpMax=math.floor(m.hp*100/m.hpp+0.5); m.missingHP=math.max(0,m.hpMax-m.hp); end
    if index==0 then
        m.buffs,m.buffSource=E.self_buffset(ctx,m);
        m.hpMax=E.call(ctx.player,'GetHPMax'); m.mpMax=E.call(ctx.player,'GetMPMax');
        if m.hpMax then m.missingHP=math.max(0,m.hpMax-m.hp); end
    else
        local supplied=E.provider('AllyBuffs',ctx,m);
        local packet=S.buffs[m.id];
        local memory=E.party_buffset(ctx,m);
        if type(supplied)=='table' then m.buffs=E.buffset(supplied);
        elseif memory~=nil then m.buffs=memory;
        elseif packet and packet.entityIndex==m.entityIndex and ctx.now-packet.time<=ctx.settings.PartyBuffMaxAge then
            m.buffs=E.buffset(packet.ids);
        end
    end
    E.apply_status_snapshot(ctx,m);
    return m;
end
function E.context(event, profileJob)
    local ctx={now=E.now(), event=event, profileJob=profileJob, settings=S.settings or DEFAULT, party={}, claims={}};
    local mem=E.call(AshitaCore,'GetMemoryManager');
    ctx.player=E.call(mem,'GetPlayer'); ctx.partyMemory=E.call(mem,'GetParty');
    ctx.entityMemory=E.call(mem,'GetEntity'); ctx.recastMemory=E.call(mem,'GetRecast');
    ctx.inventory=E.call(mem,'GetInventory'); ctx.resources=E.call(AshitaCore,'GetResourceManager');
    ctx.targetMemory=E.call(mem,'GetTarget');
    ctx.mainJobId=E.call(ctx.player,'GetMainJob') or 0; ctx.subJobId=E.call(ctx.player,'GetSubJob') or 0;
    ctx.mainJob=JOBS[ctx.mainJobId] or 'UNKNOWN'; ctx.subJob=JOBS[ctx.subJobId] or 'NONE';
    ctx.mainLevel=E.call(ctx.player,'GetMainJobLevel') or 0; ctx.subLevel=E.call(ctx.player,'GetSubJobLevel') or 0;
    ctx.playerIndex=E.call(ctx.partyMemory,'GetMemberTargetIndex',0);
    ctx.position=E.position(ctx.entityMemory,ctx.playerIndex);
    ctx.zone=E.call(ctx.partyMemory,'GetMemberZone',0);
    for i=0,17 do
        local m=E.member(ctx,i);
        if m and m.zone==ctx.zone then
            ctx.party[#ctx.party+1]=m; ctx.claims[m.id]=true;
            if i==0 then ctx.self=m; end
            local petIndex=E.call(ctx.entityMemory,'GetPetTargetIndex',m.entityIndex);
            local petId=petIndex and petIndex>0 and E.call(ctx.entityMemory,'GetServerId',petIndex);
            if petId and petId>0 then ctx.claims[petId]=true; end
        end
    end
    if ctx.self then
        ctx.requester=ctx.self;
        ctx.hpp=ctx.self.hpp; ctx.mpp=ctx.self.mpp; ctx.tp=ctx.self.tp;
        ctx.hpMax=ctx.self.hpMax; ctx.mpMax=ctx.self.mpMax; ctx.status=ctx.self.status;
        ctx.engaged=ctx.status==1;
    end
    ctx.partyLeaderServerId=E.number(E.call(ctx.partyMemory,'GetAlliancePartyLeaderServerId1'));
    ctx.targetIndex=E.call(ctx.targetMemory,'GetTargetIndex',0) or 0;
    if ctx.targetIndex>0 then
        local id=E.call(ctx.entityMemory,'GetServerId',ctx.targetIndex);
        local flags=E.call(ctx.entityMemory,'GetSpawnFlags',ctx.targetIndex);
        if id and id>0 and type(flags)=='number' then
            local target={id=id, entityIndex=ctx.targetIndex,
                name=E.call(ctx.entityMemory,'GetName',ctx.targetIndex),
                hpp=E.call(ctx.entityMemory,'GetHPPercent',ctx.targetIndex),
                claim=E.call(ctx.entityMemory,'GetClaimStatus',ctx.targetIndex),
                status=E.call(ctx.entityMemory,'GetStatus',ctx.targetIndex),
                isMonster=math.floor(flags/16)%2==1,
                position=E.position(ctx.entityMemory,ctx.targetIndex)};
            target.distance=E.distance(ctx.position,target.position);
            target.alive=type(target.hpp)=='number' and target.hpp>0;
            E.apply_status_snapshot(ctx,target);
            ctx.target=target; ctx.targetHpp=target.hpp;
        end
    end
    ctx.playerTarget=ctx.target;
    if ctx.self and ctx.self.status==1 then
        local battleIndex=E.number(E.call(ctx.entityMemory,'GetTargetedIndex',ctx.self.entityIndex));
        local battle=battleIndex and battleIndex>0 and E.entity_target(ctx,battleIndex);
        if battle and battle.isMonster then ctx.ownerBattleTarget=battle; end
    end
    local petIndex=ctx.playerIndex and E.call(ctx.entityMemory,'GetPetTargetIndex',ctx.playerIndex);
    if petIndex and petIndex>0 then
        local id=E.call(ctx.entityMemory,'GetServerId',petIndex);
        local hpp=E.call(ctx.entityMemory,'GetHPPercent',petIndex);
        if id and id>0 and type(hpp)=='number' and hpp>0 then
            ctx.pet={id=id,entityIndex=petIndex,name=E.call(ctx.entityMemory,'GetName',petIndex),hpp=hpp,
                status=E.call(ctx.entityMemory,'GetStatus',petIndex),
                tp=E.call(ctx.player,'GetPetTP'),mpp=E.call(ctx.player,'GetPetMPPercent'),
                position=E.position(ctx.entityMemory,petIndex)};
            ctx.pet.distance=E.distance(ctx.position,ctx.pet.position);
        end
    end
    ctx.weapon=E.equipped(ctx,0); ctx.ranged=E.equipped(ctx,2); ctx.ammo=E.equipped(ctx,3);
    local mainSlot=E.call(ctx.inventory,'GetEquippedItem',0);
    if not ctx.weapon and mainSlot and mainSlot.Index==0 then ctx.weapon={id=0,skill=1,name='Unarmed'}; end
    if E.candidates then
        ctx.lowestHp=E.candidates(ctx,{Target='lowest'},ctx.settings.TargetRange)[1];
        ctx.lowestMp=E.candidates(ctx,{Target='mp'},ctx.settings.TargetRange)[1];
    end
    return ctx;
end
function E.local_party_leader_server_id(ctx)
    if not ctx then return nil; end
    local leader=E.number(ctx.partyLeaderServerId);
    if leader and leader>0 then return leader; end
    leader=E.number(E.call(ctx.partyMemory,'GetAlliancePartyLeaderServerId1'));
    if leader and leader>0 then return leader; end
    return nil;
end
function E.is_local_party_leader(ctx)
    if not ctx or not ctx.self or not ctx.self.id then return false,'Party leader data is unavailable'; end
    local leader=E.local_party_leader_server_id(ctx);
    if not leader or leader<=0 then return true,nil; end
    if leader==ctx.self.id then return true,nil; end
    return false,'Only the party leader can control Trust Gambits.';
end
function E.trust_control_allowed(ctx)
    return E.is_local_party_leader(ctx);
end
function E.actor_context(ctx, actor)
    if not ctx or not actor or not actor.id then return nil; end
    -- Context handles and configuration are read-only here. Copy only actor-
    -- relative records that receive new distances; cloning every resource,
    -- cache and setting for each party member costs work on every engine tick.
    local nextCtx={};
    for key,value in pairs(ctx) do nextCtx[key]=value; end
    nextCtx.party={};
    for i,member in ipairs(ctx.party or {}) do nextCtx.party[i]=E.clone(member); end
    nextCtx.requester=ctx.requester or ctx.self;
    nextCtx.playerTarget=E.clone(ctx.playerTarget or ctx.target);
    nextCtx.ownerBattleTarget=E.clone(ctx.ownerBattleTarget);
    nextCtx._trustCapabilitiesRead=nil; nextCtx._trustCapabilities=nil;
    nextCtx.actor=actor;
    nextCtx.self=actor;
    nextCtx.hpp=actor.hpp; nextCtx.mpp=actor.mpp; nextCtx.tp=actor.tp;
    nextCtx.hpMax=actor.hpMax; nextCtx.mpMax=actor.mpMax; nextCtx.status=actor.status;
    nextCtx.mainJob=actor.mainJob or nextCtx.mainJob; nextCtx.subJob=actor.subJob or nextCtx.subJob;
    nextCtx.mainLevel=actor.mainLevel or nextCtx.mainLevel; nextCtx.subLevel=actor.subLevel or nextCtx.subLevel;
    nextCtx.engaged=actor.status==1;
    nextCtx.guestBridge=true;
    nextCtx.generatedRecruit=E.is_generated_recruit(actor);
    if nextCtx.generatedRecruit then
        -- Trust party rows can report level zero before job data settles.
        -- The factory creates recruits at the owner's current level.
        if not E.number(actor.mainLevel) or actor.mainLevel<1 then
            nextCtx.mainLevel=math.min(E.number(nextCtx.requester and nextCtx.requester.mainLevel) or 0,75);
        end
        nextCtx.subLevel=0;
    end
    nextCtx.mainJobId=JOB_IDS[nextCtx.mainJob] or 0;
    nextCtx.subJobId=JOB_IDS[nextCtx.subJob] or 0;
    nextCtx.catalogActorName=actor.name;
    nextCtx.position=actor.position;
    nextCtx.weapon=nil; nextCtx.ranged=nil; nextCtx.ammo=nil; nextCtx.inventory=nil; nextCtx.pet=nil;
    for _,member in ipairs(nextCtx.party or {}) do
        member.distance=E.distance(actor.position,member.position);
        if member.id==actor.id then nextCtx.self=member; nextCtx.actor=member; end
    end
    if actor.status==1 then
        local battleIndex=E.number(E.call(ctx.entityMemory,'GetTargetedIndex',actor.entityIndex));
        local battle=battleIndex and battleIndex>0 and E.entity_target(nextCtx,battleIndex);
        if battle and battle.isMonster then nextCtx.recruitBattleTarget=battle; end
    end
    nextCtx.target=nextCtx.recruitBattleTarget or nextCtx.ownerBattleTarget
        or (nextCtx.playerTarget and nextCtx.playerTarget.isMonster and nextCtx.playerTarget or nil);
    if nextCtx.target then nextCtx.target.distance=E.distance(actor.position,nextCtx.target.position); end
    return nextCtx;
end

-- Ordered, data-only rules. A failed check never consumes the action slot.
function E.enemy_safe(ctx, target)
    local t=target or ctx.target;
    if not t or not t.isMonster or not t.alive or not t.distance then return false; end
    local owner=ctx.requester;
    local selected=ctx.ownerBattleTarget or ctx.playerTarget;
    local ownerEngagedTarget=ctx.generatedRecruit and owner and owner.status==1 and selected
        and selected.id==t.id and selected.entityIndex==t.entityIndex;
    -- Engagement precedes the first melee hit and therefore precedes claim.
    -- Only the owner's selected enemy gets this narrow pre-claim exception;
    -- the server also checks the owner's actual battle target.
    if (t.claim==nil or t.claim==0) and ownerEngagedTarget then return true; end
    if not ctx.settings.AllowUnclaimedTargets and not ctx.claims[t.claim] then return false; end
    if t.claim and t.claim~=0 and not ctx.claims[t.claim] then return false; end
    -- An explicit recruit rule can act on a party-claimed enemy even while
    -- the recruit is idle. Owner combat status is not a reliable prerequisite
    -- for the first Attack request; the claim check above prevents pulls.
    return ctx.engaged or (ctx.generatedRecruit and t.claim and t.claim~=0 and ctx.claims[t.claim]) or t.status==1;
end
function E.incombat(ctx) return ctx.engaged or E.enemy_safe(ctx); end

function E.actor_id(ctx)
    return ctx and (ctx.actor or ctx.self) and (ctx.actor or ctx.self).id;
end

function E.pending_for(actorId)
    if actorId==nil then return S.pending; end
    return S.pendingByActor[actorId];
end

function E.actor_busy(ctx)
    local actorId=E.actor_id(ctx);
    local pending=E.pending_for(actorId);
    if pending and pending.zone==ctx.zone and ctx.now<(pending.deadline or 0) then return 'Waiting for actor action completion'; end
    local lock=S.actorLocks[actorId];
    if lock and lock.zone==ctx.zone and ctx.now<lock.untilTime then return 'Actor action lock'; end
    if not ctx.guestBridge and ctx.now<S.lockUntil then return 'Player action lock'; end
    return nil;
end

function E.set_actor_lock(ctx,untilTime)
    local actorId=E.actor_id(ctx);
    if not actorId then return; end
    local previous=S.actorLocks[actorId];
    local old=previous and previous.zone==ctx.zone and previous.untilTime or 0;
    S.actorLocks[actorId]={zone=ctx.zone,untilTime=math.max(old,untilTime)};
    if not ctx.guestBridge then S.lockUntil=math.max(S.lockUntil,untilTime); end
end

function E.register_pending(plan)
    S.pendingByActor[plan.actorId]=plan;
    if plan.actorId==plan.playerId then S.pending=plan; end
end

function E.clear_pending(plan)
    if not plan then return; end
    if S.pendingByActor[plan.actorId]==plan then S.pendingByActor[plan.actorId]=nil; end
    if S.pending==plan then S.pending=nil; end
    if S.outgoingIntent==plan then S.outgoingIntent=nil; end
end

function E.release_guest_control(ctx)
    -- Best effort only. Server lease expiry/ownership validation remains authoritative.
    if not ctx or not ctx.self or not ctx.entityMemory then return false; end
    local sent=false;
    for key,record in pairs(S.controlActors) do
        if S.controlState[key]==true and record.zone==ctx.zone and record.playerId==ctx.self.id
            and E.call(ctx.entityMemory,'GetServerId',record.entityIndex)==record.id then
            if E.submit_guest_control(ctx,record,false,true) then sent=true; end
        end
    end
    return sent;
end

function E.guest_gate(ctx)
    if not ctx or not ctx.self or not ctx.self.alive then return 'Trust is not alive'; end
    if ctx.status~=0 and ctx.status~=1 then return 'Trust state does not allow actions'; end
    if E.hasbuff(ctx.self,{2,7,10,14,17,19,28,'Sleep','Petrification','Stun','Charm','Terror'})==true then return 'Trust incapacitated'; end
    return E.actor_busy(ctx);
end

function E.gate(ctx,bypassEnabled,sharedOnly)
    if S.configError then return 'Shared settings error: '..tostring(S.configError); end
    if not sharedOnly and S.profileError and not S.profile then return 'Job settings error: '..tostring(S.profileError); end
    if not E.actor_switch_load(ctx,false) then return 'Character switches error: '..tostring(S.switchError); end
    if not sharedOnly and not bypassEnabled and not E.actor_enabled(ctx,ctx.self) then return 'Player Gambits are OFF'; end
    if not sharedOnly and (not S.profile or S.profile.Enabled==false) then return 'Job profile is OFF or unavailable'; end
    if not ctx.player or not ctx.entityMemory or not ctx.partyMemory or not ctx.resources then return 'Client data unavailable'; end
    if not ctx.self or not ctx.self.alive or ctx.mainLevel<1 or not ctx.zone or ctx.zone==0 then return 'No live player'; end
    if E.player_chat_active() then return 'Player chat active'; end
    if E.truth(E.call(ctx.player,'GetIsZoning')) then return 'Zoning'; end
    if ctx.now<S.zoneUntil then return 'Zone/job-change settling delay'; end
    if ctx.status~=0 and ctx.status~=1 then return 'Player is resting, dead, in an event, or otherwise unavailable'; end
    local mount=E.call(ctx.entityMemory,'GetMountId',ctx.playerIndex);
    if mount and mount~=0 then return 'Mounted'; end
    if ctx.now<S.pauseUntil then return 'Manual pause'; end
    -- Player movement, casting, and action locks do not lock every owned Trust.
    if sharedOnly then return nil; end
    if ctx.self.buffs==nil then return 'Self status data unavailable'; end
    if E.hasbuff(ctx.self,{2,7,10,14,17,19,28,'Sleep','Petrification','Stun','Charm','Terror'}) then return 'Incapacitated'; end
    if ctx.moving or (ctx.stationarySeconds or 0)<ctx.settings.StationaryDelaySeconds then return 'Waiting until stationary'; end
    if ctx.now<S.manualUntil then return 'Manual action in progress'; end
    if S.manualAction and ctx.now<S.manualAction.deadline then return 'Observed manual action is still in progress'; end
    return E.actor_busy(ctx);
end
function E.stealth_action_block(ctx,kind,target)
    if not ctx or not ctx.settings or not ctx.settings.PauseWhileInvisible then return nil; end
    local requester=ctx.requester or ctx.self;
    if E.hasbuff(requester,{'Invisible','Sneak',69,71})~=true then return nil; end
    if ctx.guestBridge and kind=='spell' and target and not target.isMonster then return nil; end
    return 'Stealth protection';
end
function E.resource(ctx, kind, name)
    if kind=='item' and ctx and ctx.generatedRecruit then
        local ids={['Echo Drops']=4151,Antidote=4148,['Eye Drops']=4150,Remedy=4155,['Holy Water']=4154,
            Potion=4112,['Hi-Potion']=4116,['X-Potion']=4120,Ether=4128,['Hi-Ether']=4132,
            ['Pro-Ether']=4140,Elixir=4145,['Hi-Elixir']=4144,['Meat Mithkabob']=4381,
            ['Sole Sushi']=5149,['Boiled Crab']=4456,['Tavnazian Taco']=5174,
            ['Apple Pie']=4413,['Marron Glace']=4502,['Yagudo Drink']=4558,
            ['Persikos au Lait']=4303};
        return ids[name] and {Id=ids[name],Name={name}} or nil;
    end
    local key=kind .. ':' .. name;
    if S.cache[key] then return S.cache[key]; end
    local res;
    if kind=='spell' then res=E.call(ctx.resources,'GetSpellByName',name,0);
    elseif kind=='item' then res=E.call(ctx.resources,'GetItemByName',name,0);
    else res=E.call(ctx.resources,'GetAbilityByName',name,0); end
    if res then S.cache[key]=res; end
    return res;
end
function E.player_level_cap(ctx)
    local level=E.number(ctx and ctx.requester and ctx.requester.mainLevel);
    if not level or level<1 then level=E.number(ctx and ctx.self and ctx.self.mainLevel); end
    if not level or level<1 then level=E.number(ctx and ctx.mainLevel); end
    if not level or level<1 then level=E.number(E.call(ctx and ctx.player,'GetMainJobLevel')); end
    return math.min(level or 0,75);
end
function E.main_level_cap(ctx)
    return math.min(E.number(ctx and ctx.mainLevel) or 0,E.player_level_cap(ctx),75);
end
function E.sub_level_cap(ctx)
    return math.min(E.number(ctx and ctx.subLevel) or 0,E.player_level_cap(ctx),37);
end

function E.trust_capabilities(ctx)
    if not ctx or not (ctx.guestBridge or ctx.catalogActorKind=='guest') then return nil; end
    if ctx.generatedRecruit then return nil; end
    if ctx._trustCapabilitiesRead then return ctx._trustCapabilities; end
    ctx._trustCapabilitiesRead=true;
    local data=E.provider('TrustCapabilities',ctx);
    if data==nil then return nil; end
    local name=ctx.catalogActorName or (ctx.actor and ctx.actor.name) or (ctx.self and ctx.self.name);
    local expected=E.trust_picker_entry_by_name(name);
    local supplied=type(data)=='table' and E.trust_picker_entry_by_name(data.TrustKey) or nil;
    if type(data)~='table' or type(data.Actions)~='table' or not expected or supplied~=expected then
        ctx._trustCapabilities={Invalid=true};
    else ctx._trustCapabilities=data; end
    return ctx._trustCapabilities;
end

function E.generated_recruit_ranged_allowed(ctx)
    return ctx and ctx.generatedRecruit and E.contains({'THF','RNG','COR'},ctx.mainJob) or false;
end

function E.trust_permission(ctx,kind,name)
    -- Generated recruits are authorized by the server's job profile and action
    -- validator. Named Trust capability lists cannot identify randomized names.
    if ctx and ctx.generatedRecruit then return nil,'Server validates generated recruit actions'; end
    local data=E.trust_capabilities(ctx);
    if not data then
        if (ctx.settings or DEFAULT).RequireVerifiedTrustCapabilities then return false,'Verified Trust capability data unavailable'; end
        return nil,'Using unverified legacy job catalog';
    end
    if data.Invalid then return false,'Trust capability identity/schema mismatch'; end
    for _,entry in ipairs(data.Actions) do
        if type(entry)=='table' and entry.Type==kind and entry.Action==name then
            local level=E.number(entry.MinLevel);
            if entry.Verified~=true or entry.Implemented~=true or not level or level<1 or level>75 or level~=math.floor(level) then
                return false,'Trust action unlock/implementation is unverified or above cap';
            end
            if level>E.main_level_cap(ctx) then return false,'Trust action is not unlocked at current level'; end
            local maximum=entry.MaxLevel==nil and 75 or E.number(entry.MaxLevel);
            if not maximum or maximum<level or maximum>75 or maximum~=math.floor(maximum) then return false,'Invalid Trust action level range'; end
            if ctx.mainLevel>maximum then return false,'Trust action outside its permitted level range'; end
            return true;
        end
    end
    return false,'Action not in this Trust capability list';
end

function E.spell_level(ctx,res)
    if ctx and (ctx.guestBridge or ctx.catalogActorKind=='guest') then
        local allowed,why=E.trust_permission(ctx,'spell',res and res.Name and res.Name[1]);
        if allowed~=nil then return allowed,why; end
    end
    local ok,required=pcall(function() return res and res.LevelRequired; end);
    if not ok or required==nil then return false,'Spell level data unavailable'; end
    local function at(index)
        local readable,value=pcall(function() return required[index]; end);
        return readable and E.number(value) or nil;
    end
    -- Ashita normally labels this field as a Lua table, but some SDK bindings
    -- expose the same 1-based array as userdata/cdata. Index it by capability.
    local main=at(ctx.mainJobId+1);
    local sub=at(ctx.subJobId+1);
    local available=(main and main>0 and main<=E.main_level_cap(ctx))
        or (ctx.subJobId>0 and sub and sub>0 and sub<=E.sub_level_cap(ctx)) or false;
    if available then return true; end
    return false,string.format('Spell level mismatch: %s %s requires %s; %s %s requires %s',
        ctx.mainJob,tostring(ctx.mainLevel),tostring(main or 'n/a'),
        ctx.subJob,tostring(ctx.subLevel),tostring(sub or 'n/a'));
end
function E.catalog_ability_entry(name,job)
    for _,entry in ipairs(JOB_ABILITY_CATALOG[job] or {}) do
        if entry[1]==name then return entry; end
    end
    return nil;
end
function E.job_ability_level_ok(ctx,name)
    if not E.safe_name(name) then return false,'Invalid ability name'; end
    local main=E.catalog_ability_entry(name,ctx.mainJob);
    if main then
        local level=main[2] or 1;
        if level<=E.main_level_cap(ctx) then return true; end
        return false,string.format('%s requires %s level %s; current action cap is %s',name,tostring(ctx.mainJob),tostring(level),tostring(E.main_level_cap(ctx)));
    end
    local sub=E.catalog_ability_entry(name,ctx.subJob);
    if sub then
        local level=sub[2] or 1;
        if sub[3]==true then return false,name..' is main-job only and cannot be used from subjob'; end
        if level<=E.sub_level_cap(ctx) then return true; end
        return false,string.format('%s requires %s level %s; current subjob action cap is %s',name,tostring(ctx.subJob),tostring(level),tostring(E.sub_level_cap(ctx)));
    end
    if SPECIAL[name] then return false,name..' is a main-job special ability and cannot be used from subjob'; end
    return nil;
end
function E.ability_level_allowed(ctx,res,kind)
    if kind~='ability' then return true; end
    local name=res and res.Name and res.Name[1];
    local ok,why=E.job_ability_level_ok(ctx,name);
    if ok==nil then return true; end
    return ok,why;
end
function E.ability_known(ctx,res,kind)
    local id=E.number(res.Id) or E.number(res.Index);
    if not id then return false; end
    if (ctx.guestBridge or ctx.catalogActorKind=='guest') and kind=='ability' then
        return E.guest_ability_available(ctx,res);
    end
    if (ctx.guestBridge or ctx.catalogActorKind=='guest') and kind=='ws' then
        return E.guest_weapon_skill_available(ctx,res);
    end
    local levelOk=E.ability_level_allowed(ctx,res,kind);
    if levelOk==false then return false; end
    local override=E.provider('AbilityAvailable',ctx,res,kind);
    if override~=nil then return override==true; end
    if kind=='ws' then return E.truth(E.call(ctx.player,'HasWeaponSkill',id)); end
    if not E.truth(E.call(ctx.player,'HasAbilityData')) then return false; end
    local native=id>=512 and id-512 or id;
    if S.availability then
        local bitmap=kind=='pet' and S.availability.pet or S.availability.ability;
        if bitmap then return bitmap[native]==true; end
    end
    -- SDK builds normally accept resource IDs, as in the supplied v1.10 engine.
    -- For a build using native IDs, set the relevant offset to -512; never try both.
    local offset=kind=='pet' and ctx.settings.PetCommandIdOffset or ctx.settings.AbilityIdOffset;
    return E.truth(E.call(ctx.player,kind=='pet' and 'HasPetCommand' or 'HasAbility',id+offset));
end
function E.ability_ready(ctx,res)
    if ctx and ctx.guestBridge then return true; end
    local group=E.number(res.RecastTimerId);
    if group==nil or not ctx.recastMemory then return false; end
    local scanned=false;
    for slot=0,31 do
        local id=E.call(ctx.recastMemory,'GetAbilityTimerId',slot);
        local timer=E.call(ctx.recastMemory,'GetAbilityTimer',slot);
        if id==nil or timer==nil then return false; end
        scanned=true;
        if id==group and (group~=0 or slot==0) then return timer<=0; end
    end
    -- A loaded ability with no entry in the active recast-slot list is ready.
    return scanned and group~=0;
end
function E.rule_job(ctx,rule)
    if rule.Job then
        local level;
        if ctx.mainJob==rule.Job then level=ctx.mainLevel;
        elseif not rule.MainOnly and ctx.subJob==rule.Job then level=ctx.subLevel; end
        if not level or level<(rule.MinLevel or 1) then return false; end
    end
    if rule.Jobs and not E.contains(rule.Jobs,ctx.mainJob) and not E.contains(rule.Jobs,ctx.subJob) then return false; end
    return true;
end
function E.slot_available(ctx,rule,key,capacity)
    local slot=rule[key];
    if slot==nil then return true; end
    if type(slot)~='number' or slot<1 or slot~=math.floor(slot) or slot>capacity then
        return false,'Requested '..key..' exceeds established capacity';
    end
    -- Only the first enabled rule owns a slot. Optional alternatives cannot cycle buffs.
    for _,other in ipairs(ctx.activeRules or (S.profile and S.profile.Rules) or {}) do
        if other.Enabled~=false and other[key]==slot and E.rule_job(ctx,other) then
            if other.Id==rule.Id then return true; end
            return false,key..' already assigned to an earlier enabled rule';
        end
    end
    return true;
end
function E.compare_value(actual,op,expected)
    if op==nil or op=='any' then return true; end
    if op=='present' or op=='yes' or op=='has' or op=='ready' then return actual==true; end
    if op=='missing' or op=='no' or op=='not' or op=='not-ready' then return actual==false; end
    local a=E.number(actual); local b=E.number(expected);
    if a==nil or b==nil then return false; end
    if op=='<' then return a<b; elseif op=='<=' then return a<=b; elseif op=='=' or op=='==' then return a==b;
    elseif op=='!=' or op=='~=' then return a~=b; elseif op=='>=' then return a>=b; elseif op=='>' then return a>b; end
    return false;
end
function E.provider_compare(name,ctx,rule,target)
    local value=E.provider(name,ctx,rule,target);
    if value==nil then value=E.observed_property(ctx,rule,target); end
    if value==nil then return false,'UNKNOWN: '..name..' provider/state unavailable'; end
    local op=rule.Operator or 'yes';
    -- Existing predicate providers may return a boolean for a named equality test.
    if type(value)=='boolean' then
        if op=='=' or op=='==' then return value,name..' condition'; end
        if op=='!=' or op=='~=' then return not value,name..' condition'; end
        return E.compare_value(value,op,rule.Value),name..' condition';
    end
    if E.property_kind(rule.Property)=='text' then
        local expected=rule.TextValue or rule.ValueText;
        if type(value)~='string' or type(expected)~='string' or expected=='' then
            return false,'UNKNOWN: '..name..' text value unavailable';
        end
        local matches=E.lower(value)==E.lower(expected);
        if op=='!=' or op=='~=' or op=='not' then matches=not matches; end
        return matches,name..' condition';
    end
    return E.compare_value(value,op,rule.Value),name..' condition';
end
local REQUIRED_PROPERTY_PROVIDER={
    readying_tp_move='EnemyTPMove',specific_tp_move='EnemyTPMove',sp_ability='EnemySPAbility',
    status_remaining='StatusRemaining',enemy_count='EnemyCountNearby',
    skillchain='SkillchainWindow',skillchain_property='SkillchainProperty',
    skillchain_level='SkillchainLevel',can_open_skillchain='CanOpenSkillchain',
    can_close_skillchain='CanCloseSkillchain',magic_burst_window='MagicBurstWindow',
    magic_burst_element='MagicBurstElement',top_enmity='TopEnmity',
    position='PositionSafe',behind='PositionSafe',in_front='PositionSafe',
    weakest_element='ElementalCondition',resists_element='ElementalCondition',
    immune_element='ElementalCondition',absorbs_element='ElementalCondition',
    element='ElementalCondition',family='EnemyFamily',nm_state='NMState',
    matching_allies='MatchingAllies',matching_alliance='MatchingAllies',
    difficulty='DifficultyCondition',day='DayCondition',weather='WeatherCondition',
    ability_recast='AbilityRecastReady',spell_recast='SpellRecastReady',
    rune_count='RuneCondition',rune_element='RuneCondition',
    finishing_moves='DancerCondition',daze_level='DancerCondition',samba='DancerCondition',
    stratagem_charges='ScholarCondition',arts='ScholarCondition',addendum='ScholarCondition',
    sublimation_ready='ScholarCondition',song_remaining='BardCondition',
    roll='CorsairCondition',roll_value='CorsairCondition',lucky_number='CorsairCondition',
    quick_draw_charges='CorsairCondition',automaton_hp='PuppetmasterCondition',
    automaton_mp='PuppetmasterCondition',automaton_tp='PuppetmasterCondition',
    avatar_present='SummonerCondition',blood_pact_ready='SummonerCondition',
    ready_charges='BeastmasterCondition',bst_pet_hp='BeastmasterCondition',bst_pet_tp='BeastmasterCondition',
    wyvern_hp='WyvernCondition',luopan_present='GeomancerCondition',luopan_hp='GeomancerCondition',
    indi_active='GeomancerCondition',geo_active='GeomancerCondition',
}
function E.missing_property_provider(property,ctx)
    local name=REQUIRED_PROPERTY_PROVIDER[property];
    if name and type(S.providers[name])~='function' then return name; end
    return nil;
end
function E.property_supported(property,ctx)
    if type(property)~='string' then return false; end
    if E.missing_property_provider(property,ctx) then return false; end
    if ctx and (ctx.guestBridge or ctx.catalogActorKind=='guest') and
        (property:match('^pet_') or E.contains({'item_count','ammo_remaining','weapon_type'},property)) then return false; end
    return E.contains({'always','hp_pct','hp_amount','mp_pct','mp_amount','tp','alive','dead','engaged','in_battle','idle',
        'distance','melee_range','ranged_range','has_mp','casting','casting_magic','specific_spell',
        'status_count','party_count','job','role','level','role_present','job_present','healer_present','tank_present',
        'item_count','ammo_remaining','weapon_type','pet_present','pet_missing','pet_idle','pet_engaged',
        'pet_hp_pct','pet_mp_pct','pet_tp','shadows','preferred_ranged_distance','outside_melee_range',
        'has_hate','targeting','targeting_actor','song_missing','active_song','song_count',
        'roll_missing','active_roll','bust','bust_count','roll_count','maneuver_count','maneuver_element',
        'readying_tp_move','specific_tp_move','sp_ability','enemy_dispellable','weakest_element',
        'resists_element','immune_element','absorbs_element','top_enmity','status_remaining','enemy_count',
        'skillchain','skillchain_property','skillchain_level','can_open_skillchain','can_close_skillchain',
        'magic_burst_window','magic_burst_element','element','family','nm_state','matching_allies','matching_alliance',
        'difficulty','day','weather','ability_recast','spell_recast','position','behind','in_front',
        'rune_count','rune_element','finishing_moves','daze_level','samba','stratagem_charges','arts','addendum',
        'sublimation_ready','song_remaining','roll','roll_value','lucky_number','quick_draw_charges',
        'automaton_hp','automaton_mp','automaton_tp','avatar_present','blood_pact_ready','ready_charges',
        'bst_pet_hp','bst_pet_tp','wyvern_hp','luopan_present','luopan_hp','indi_active','geo_active',
        'removable_ailment'},property);
end
function E.property_kind(property)
    if E.contains({'hp_pct','hp_amount','mp_pct','mp_amount','tp','distance','status_count','party_count','level',
        'item_count','ammo_remaining','pet_hp_pct','pet_mp_pct','pet_tp','shadows','preferred_ranged_distance',
        'song_count','roll_count','bust_count','maneuver_count','status_remaining','song_remaining',
        'matching_allies','matching_alliance','enemy_count','skillchain_level','finishing_moves','daze_level',
        'rune_count','stratagem_charges','roll_value','quick_draw_charges','automaton_hp','automaton_mp',
        'automaton_tp','ready_charges','bst_pet_hp','bst_pet_tp','wyvern_hp','luopan_hp'},property) then return 'number'; end
    if E.contains({'job','role','weapon_type','targeting','skillchain_property','magic_burst_element',
        'weakest_element','element','family','nm_state','rune_element','arts','addendum','samba',
        'difficulty','day','weather','roll'},property) then return 'text'; end
    return 'boolean';
end
function E.operator_supported(property,op)
    if property=='always' then return op=='any'; end
    local kind=E.property_kind(property);
    if kind=='number' then return E.contains({'<','<=','=','==','!=','~=','>=','>'},op); end
    if kind=='text' then return E.contains({'=','==','!=','~=','not'},op); end
    if E.contains({'specific_spell','maneuver_element','active_song','song_missing','active_roll','roll_missing'},property)
        and (op=='=' or op=='==') then return true; end
    return E.contains({'yes','no','present','missing','has','not','ready','not-ready'},op);
end
function E.observed_property(ctx,rule,target)
    local property=rule.Property;
    local t=target or ctx.self;
    if property=='has_hate' or property=='targeting_actor' or property=='targeting' then
        local enemy=(t and t.isMonster) and t or ctx.target;
        local index=enemy and E.number(E.call(ctx.entityMemory,'GetTargetedIndex',enemy.entityIndex));
        if not index or index<=0 then return nil; end
        local wanted=property=='targeting' and E.lower(rule.TextValue or '') or 'self';
        if wanted=='self' then return index==ctx.self.entityIndex; end
        if wanted=='player' then return index==(ctx.requester or ctx.self).entityIndex; end
        for _,m in ipairs(ctx.party or {}) do
            if m.entityIndex==index then return E.role_name(m)==wanted; end
        end
        return false;
    end
    if not t or not t.buffs then return nil; end
    if property=='active_song' or property=='song_missing' or property=='active_roll' or property=='roll_missing' then
        local present=E.hasbuff(t,rule.TextValue or '');
        if property=='song_missing' or property=='roll_missing' then return present==false; end
        return present;
    end
    if property=='bust' then return E.hasbuff(t,'Bust'); end
    if property=='bust_count' then return E.status_count(t,'Bust'); end
    local families;
    if property=='song_count' then families={'Requiem','Lullaby','Elegy','Paeon','Ballad','Minne','Minuet','Madrigal','Prelude','Mambo','Aubade','Pastoral','Hum','Fantasia','Operetta','Capriccio','Serenade','Round','Gavotte','Fugue','Rhapsody','Aria','March','Etude','Carol','Threnody','Hymnus','Mazurka','Sirvente','Dirge','Scherzo'};
    elseif property=='maneuver_count' then families={'Fire Maneuver','Ice Maneuver','Wind Maneuver','Earth Maneuver','Thunder Maneuver','Water Maneuver','Light Maneuver','Dark Maneuver'};
    elseif property=='maneuver_element' then return E.hasbuff(t,(rule.TextValue or '')..' Maneuver');
    elseif property=='roll_count' then
        local total=0;
        for key,count in pairs(t.buffs) do
            if type(key)=='string' and key:match(' roll$') then total=total+count; end
        end
        return total;
    end
    if families then
        local total=0;
        for _,name in ipairs(families) do total=total+(E.status_count(t,name) or 0); end
        return total;
    end
    return nil;
end
function E.property_condition(ctx,rule,target)
    local property=rule.Property;
    if not property or property=='always' then return true; end
    if not E.property_supported(property,ctx) then return false,'Condition unavailable: '..tostring(property); end
    local op=rule.Operator or 'yes';
    if not E.operator_supported(property,op) then return false,'Invalid condition operator'; end
    local value=rule.Value;
    local t=target or ctx.self;
    if property=='hp_pct' then return E.compare_value(t and t.hpp,op,value or 40),'HP condition'; end
    if property=='hp_amount' then return E.compare_value(t and t.hp,op,value or 100),'HP amount condition'; end
    if property=='mp_pct' then return E.compare_value(t and t.mpp,op,value or 30),'MP condition'; end
    if property=='mp_amount' then return E.compare_value(t and t.mp,op,value or 100),'MP amount condition'; end
    if property=='tp' then return E.compare_value(t and t.tp,op,value or 1000),'TP condition'; end
    if property=='alive' then return E.compare_value(t and t.alive==true,op,nil),'Alive condition'; end
    if property=='dead' then return E.compare_value(t and t.dead==true,op,nil),'Dead condition'; end
    if property=='in_battle' then return E.compare_value(E.incombat(ctx)==true,op,nil),'Battle condition'; end
    if property=='engaged' or property=='idle' then
        if not t or t.status==nil then return false,'Engagement state unknown'; end
        return E.compare_value(t.status==(property=='engaged' and 1 or 0),op,nil),'Engagement condition';
    end
    if property=='distance' then return E.compare_value(t and t.distance,op,value or 10),'Distance condition'; end
    if property=='melee_range' or property=='ranged_range' then
        if not t or t.distance==nil then return false,'Distance unknown'; end
        return E.compare_value(t.distance<=(property=='melee_range' and 3.5 or 20),op,nil),'Range condition';
    end
    if property=='has_mp' then
        local mageJobs={'WHM','BLM','RDM','PLD','DRK','SMN','BLU'};
        local known;
        if t and E.number(t.mpMax)~=nil then known=t.mpMax>0;
        elseif t and E.number(t.mp)~=nil and t.mp>0 then known=true;
        elseif t and (t.mainJob or t.subJob) then
            known=E.contains(mageJobs,t.mainJob) or E.contains(mageJobs,t.subJob);
        else known=E.provider('HasMPPool',ctx,t); end
        if known==nil then return false,'MP pool unknown'; end
        return E.compare_value(known==true,op,nil),'MP pool condition';
    end
    if property=='casting' or property=='casting_magic' then
        local cast=t and S.casts[t.id];
        local supplied=E.provider('EnemyCasting',ctx,t);
        local actual=supplied;
        if cast and cast.untilTime>ctx.now then actual=true; end
        if actual==nil then return false,'UNKNOWN: casting state unavailable'; end
        return E.compare_value(actual==true,op,nil),'Casting condition';
    end
    if property=='specific_spell' then
        local cast=t and S.casts[t.id];
        local supplied=E.provider('EnemyCastingSpell',ctx,rule,t);
        local wanted=tostring(rule.TextValue or rule.ValueText or ''):lower();
        local matches=supplied;
        if cast and cast.untilTime>ctx.now and wanted~='' and cast.name then matches=tostring(cast.name):lower()==wanted; end
        if matches==nil then return false,'UNKNOWN: specific spell state unavailable'; end
        if op=='=' or op=='==' then return matches,'Specific spell condition'; end
        return E.compare_value(matches,op,nil),'Specific spell condition';
    end
    if property=='readying_tp_move' or property=='specific_tp_move' then return E.provider_compare('EnemyTPMove',ctx,rule,t); end
    if property=='sp_ability' then return E.provider_compare('EnemySPAbility',ctx,rule,t); end
    if property=='enemy_dispellable' then
        if t and t.dispellable~=nil then
            return E.compare_value(t.dispellable==true,op,nil),'Verified dispellable enhancement';
        end
        if ctx.generatedRecruit and t and t.isMonster and E.provider('EnemyDispellableBuff',ctx,rule,t)==nil then
            -- The server checks the actual status immediately before casting.
            -- Client entity data does not expose a reliable dispellable flag.
            return E.compare_value(true,op,nil),'Server-checked dispellable buff';
        end
        return E.provider_compare('EnemyDispellableBuff',ctx,rule,t);
    end
    if property=='removable_ailment' then
        local statuses=E.removal_statuses(rule.SelectedAction or rule.Action);
        if statuses then
            local present=E.hasbuff(t,statuses);
            if present==nil then return false,'UNKNOWN: recipient ailments unavailable'; end
            return E.compare_value(present,op,nil),'Removable ailment condition';
        end
        return E.provider_compare('RemovableAilment',ctx,rule,t);
    end
    if property=='weakest_element' or property=='resists_element' or property=='immune_element' or property=='absorbs_element' then
        return E.provider_compare('ElementalCondition',ctx,rule,t);
    end
    if property=='has_hate' then return E.provider_compare('HasHate',ctx,rule,t); end
    if property=='top_enmity' then return E.provider_compare('TopEnmity',ctx,rule,t); end
    if property=='targeting' then return E.provider_compare('TargetingRole',ctx,rule,t); end
    if property=='targeting_actor' then return E.provider_compare('TargetingActor',ctx,rule,t); end
    if property=='status_remaining' then return E.provider_compare('StatusRemaining',ctx,rule,t); end
    if property=='status_count' then return E.compare_value(E.status_count(t,rule.TextValue or rule.ValueText),op,value or 1),'Status count condition'; end
    if property=='party_count' then
        local count=0; local includeAlliance=tostring(rule.Target or ''):find('alliance',1,true)~=nil;
        for _,m in ipairs(ctx.party or {}) do
            if (m.index<6 or includeAlliance) and m.zone==ctx.zone and m.alive then count=count+1; end
        end
        return E.compare_value(count,op,value or 2),'Party count condition';
    end
    if property=='enemy_count' then return E.provider_compare('EnemyCountNearby',ctx,rule,t); end
    if property=='skillchain' then return E.provider_compare('SkillchainWindow',ctx,rule,t); end
    if property=='skillchain_property' then return E.provider_compare('SkillchainProperty',ctx,rule,t); end
    if property=='skillchain_level' then return E.provider_compare('SkillchainLevel',ctx,rule,t); end
    if property=='can_open_skillchain' then return E.provider_compare('CanOpenSkillchain',ctx,rule,t); end
    if property=='can_close_skillchain' then return E.provider_compare('CanCloseSkillchain',ctx,rule,t); end
    if property=='magic_burst_window' then return E.provider_compare('MagicBurstWindow',ctx,rule,t); end
    if property=='magic_burst_element' then return E.provider_compare('MagicBurstElement',ctx,rule,t); end
    if property=='element' then return E.provider_compare('ElementalCondition',ctx,rule,t); end
    if property=='family' then return E.provider_compare('EnemyFamily',ctx,rule,t); end
    if property=='nm_state' then return E.provider_compare('NMState',ctx,rule,t); end
    if property=='job' then
        local wanted=E.lower(rule.TextValue or rule.ValueText or '');
        local actualMain=E.lower(t and t.mainJob or '');
        local actualSub=E.lower(t and t.subJob or '');
        local matches=wanted~='' and (actualMain==wanted or actualSub==wanted);
        if op=='!=' or op=='~=' or op=='not' then return not matches,'Job condition'; end
        return matches,'Job condition';
    end
    if property=='role' then
        local wanted=E.lower(rule.TextValue or rule.ValueText or '');
        local matches=wanted~='' and E.role_name(t)==wanted;
        if op=='!=' or op=='~=' or op=='not' then return not matches,'Role condition'; end
        return matches,'Role condition';
    end
    if property=='level' then return E.compare_value(t and t.mainLevel,op,value or 1),'Level condition'; end
    if property=='matching_allies' or property=='matching_alliance' then return E.provider_compare('MatchingAllies',ctx,rule,t); end
    if property=='role_present' then
        local wanted=E.lower(rule.TextValue or rule.ValueText or '');
        local includeAlliance=property=='matching_alliance' or tostring(rule.Target or ''):find('alliance',1,true)~=nil;
        for _,m in ipairs(ctx.party or {}) do
            if (m.index<6 or includeAlliance) and m.zone==ctx.zone and m.alive and E.role_name(m)==wanted then return E.compare_value(true,op,nil),'Role present condition'; end
        end
        return E.compare_value(false,op,nil),'Role present condition';
    end
    if property=='job_present' then
        local wanted=E.lower(rule.TextValue or rule.ValueText or '');
        local includeAlliance=tostring(rule.Target or ''):find('alliance',1,true)~=nil;
        for _,m in ipairs(ctx.party or {}) do
            if (m.index<6 or includeAlliance) and m.zone==ctx.zone and m.alive and (E.lower(m.mainJob)==wanted or E.lower(m.subJob)==wanted) then
                return E.compare_value(true,op,nil),'Job present condition';
            end
        end
        return E.compare_value(false,op,nil),'Job present condition';
    end
    if property=='healer_present' or property=='tank_present' then
        local wanted=property=='healer_present' and 'healer' or 'tank';
        local includeAlliance=tostring(rule.Target or ''):find('alliance',1,true)~=nil;
        for _,m in ipairs(ctx.party or {}) do
            if (m.index<6 or includeAlliance) and m.zone==ctx.zone and m.alive and E.role_name(m)==wanted then return E.compare_value(true,op,nil),wanted .. ' present condition'; end
        end
        return E.compare_value(false,op,nil),wanted .. ' present condition';
    end
    if property=='difficulty' then return E.provider_compare('DifficultyCondition',ctx,rule,t); end
    if property=='day' then return E.provider_compare('DayCondition',ctx,rule,t); end
    if property=='weather' then return E.provider_compare('WeatherCondition',ctx,rule,t); end
    if property=='ability_recast' then return E.provider_compare('AbilityRecastReady',ctx,rule,t); end
    if property=='spell_recast' then return E.provider_compare('SpellRecastReady',ctx,rule,t); end
    if property=='item_count' then return E.compare_value(E.itemcount(ctx,rule.TextValue or rule.ValueText or rule.RequiredItem or ''),op,value or 1),'Item count condition'; end
    if property=='ammo_remaining' then return E.compare_value((ctx.ammo and ctx.ammo.count) or 0,op,value or 1),'Ammo count condition'; end
    if property=='position' or property=='behind' or property=='in_front' then return E.provider_compare('PositionSafe',ctx,rule,t); end
    if property=='weapon_type' then
        local wanted=E.lower(rule.TextValue or rule.ValueText or '');
        local names={'Hand-to-Hand','Dagger','Sword','Great Sword','Axe','Great Axe','Scythe','Polearm','Katana','Great Katana','Club','Staff'};
        local actual=ctx.weapon and names[ctx.weapon.skill];
        if not actual then return false,'Weapon category unavailable'; end
        local matches=E.lower(actual)==wanted;
        return (op=='!=' or op=='not') and not matches or ((op=='=' or op=='yes') and matches),'Weapon type condition';
    end
    if property=='pet_present' then return E.compare_value(ctx.pet~=nil,op,nil),'Pet present condition'; end
    if property=='pet_missing' then return E.compare_value(ctx.pet==nil,op,nil),'Pet missing condition'; end
    if property=='pet_idle' then return E.compare_value(ctx.pet~=nil and ctx.pet.status==0,op,nil),'Pet idle condition'; end
    if property=='pet_engaged' then return E.compare_value(ctx.pet~=nil and ctx.pet.status==1,op,nil),'Pet engaged condition'; end
    if property=='pet_hp_pct' then return E.compare_value(ctx.pet and ctx.pet.hpp,op,value or 40),'Pet HP condition'; end
    if property=='pet_mp_pct' then return E.compare_value(ctx.pet and ctx.pet.mpp,op,value or 40),'Pet MP condition'; end
    if property=='pet_tp' then return E.compare_value(ctx.pet and ctx.pet.tp,op,value or 1000),'Pet TP condition'; end
    if property=='shadows' then
        if not t or not t.buffs then return false,'Shadow status unavailable'; end
        local count=0;
        for _,entry in ipairs({{66,'copy image',1},{444,'copy image (2)',2},{445,'copy image (3)',3},{446,'copy image (4)',4}}) do
            if (t.buffs[entry[1]] or 0)>0 or (t.buffs[entry[2]] or 0)>0 then count=math.max(count,entry[3]); end
        end
        return E.compare_value(count,op,value or 2),'Shadow count condition';
    end
    if property=='rune_count' or property=='rune_element' then return E.provider_compare('RuneCondition',ctx,rule,t); end
    if property=='finishing_moves' or property=='daze_level' or property=='samba' then return E.provider_compare('DancerCondition',ctx,rule,t); end
    if property=='stratagem_charges' or property=='arts' or property=='addendum' or property=='sublimation_ready' then return E.provider_compare('ScholarCondition',ctx,rule,t); end
    if property=='preferred_ranged_distance' then return E.compare_value(t and t.distance,op,value or 15),'Preferred ranged distance condition'; end
    if property=='outside_melee_range' then
        if not t or t.distance==nil then return false,'Distance unknown'; end
        return E.compare_value(t.distance>3.5,op,nil),'Outside melee range condition';
    end
    if property=='active_song' or property=='song_missing' or property=='song_count' or property=='song_remaining' then return E.provider_compare('BardCondition',ctx,rule,t); end
    if property=='roll' or property=='active_roll' or property=='roll_missing' or property=='roll_value' or property=='lucky_number' or property=='bust' or property=='roll_count' or property=='bust_count' or property=='quick_draw_charges' then return E.provider_compare('CorsairCondition',ctx,rule,t); end
    if property=='maneuver_count' or property=='maneuver_element' or property=='automaton_hp' or property=='automaton_mp' or property=='automaton_tp' then return E.provider_compare('PuppetmasterCondition',ctx,rule,t); end
    if property=='avatar_present' or property=='blood_pact_ready' then return E.provider_compare('SummonerCondition',ctx,rule,t); end
    if property=='ready_charges' or property=='bst_pet_hp' or property=='bst_pet_tp' then return E.provider_compare('BeastmasterCondition',ctx,rule,t); end
    if property=='wyvern_hp' then return E.provider_compare('WyvernCondition',ctx,rule,t); end
    if property=='luopan_present' or property=='luopan_hp' or property=='indi_active' or property=='geo_active' then return E.provider_compare('GeomancerCondition',ctx,rule,t); end
    return false,'Unknown property condition';
end
function E.condition_clause_active(rule)
    if type(rule)~='table' then return false; end
    if rule.Property~=nil and rule.Property~='always' then return true; end
    for _,key in ipairs({'SelfHPBelow','SelfHPAbove','SelfMPBelow','SelfMPAbove','SelfTPBelow','SelfTPAbove',
        'TargetHPBelow','TargetHPAbove','TargetMPBelow','TargetMPAbove','MinMissingHP','TP',
        'MissingBuff','MissingBuffBinding','MissingBuffExpireThreshold','Status','RequiresBuff','ForbidBuff','Pet','PetHPBelow','PetTPAbove',
        'Mechanic','Family','Range','ManaTarget','TwoHanded','RequireProvider',
        'RequiredItem','AmmoContains'}) do
        if rule[key]~=nil then return true; end
    end
    if rule.Combat~=nil and rule.Combat~='any' then return true; end
    return false;
end
function E.condition_clause(ctx,rule,target)
    if rule.MissingBuffBinding=='action' and not rule.MissingBuff then
        return false,'Selected action has no maintainable status effect';
    end
    if rule.CheckTarget and rule.CheckTarget~='' then
        local checkRule=E.clone(rule);
        checkRule.Target=rule.CheckTarget;
        checkRule.TargetName=rule.CheckTargetName or rule.TargetName;
        checkRule.CheckTarget=nil;
        checkRule.SubjectOnly=true;
        local candidates=E.candidates(ctx,checkRule,math.huge);
        if rule.CheckTarget=='status' and rule.Status then
            for _,candidate in ipairs(candidates or {}) do
                local probe=E.clone(rule); probe.CheckTarget=nil; probe.SubjectOnly=nil;
                local ok=E.condition_clause(ctx,probe,candidate);
                if ok then return true; end
            end
            return false,'No party member satisfies the status condition';
        end
        target=candidates and candidates[1] or nil;
        if not target then return false,'Condition subject unavailable'; end
    end
    if rule.Range~=nil and (not target or not target.distance or target.distance>rule.Range) then
        return false,'Distance exceeds condition range';
    end
    local combat=E.incombat(ctx);
    if rule.Combat=='combat' and not combat then return false,'Combat only'; end
    if rule.Combat=='idle' and combat then return false,'Out of combat only'; end
    if rule.TP~=nil and (type(ctx.tp)~='number' or ctx.tp<rule.TP) then return false,'TP condition'; end
    local propertyOk,propertyWhy=E.property_condition(ctx,rule,target);
    if not propertyOk then return false,propertyWhy; end
    local checks={
        {'SelfHPBelow',ctx.hpp,'max'},{'SelfHPAbove',ctx.hpp,'min'},
        {'SelfMPBelow',ctx.mpp,'max'},{'SelfMPAbove',ctx.mpp,'min'},
        {'SelfTPBelow',ctx.tp,'max'},{'SelfTPAbove',ctx.tp,'min'},
        {'TargetHPBelow',target and target.hpp,'max'},
        {'TargetHPAbove',target and target.hpp,'min'},
        {'TargetMPBelow',target and target.mpp,'max'},
        {'TargetMPAbove',target and target.mpp,'min'},
    };
    for _,c in ipairs(checks) do
        local limit=rule[c[1]];
        if limit~=nil then
            if type(c[2])~='number' then return false,'Required target statistic unavailable'; end
            if c[3]=='max' and c[2]>=limit then return false,c[1] .. ' condition'; end
            if c[3]=='min' and (c[2]<limit or (c[1]~='SelfTPAbove' and c[2]==limit)) then return false,c[1] .. ' condition'; end
        end
    end
    if rule.MinMissingHP and (not target or not target.missingHP or target.missingHP<rule.MinMissingHP) then
        return false,'Not enough missing HP';
    end
    if rule.RequiresBuff and E.hasbuff(ctx.self,rule.RequiresBuff)~=true then return false,'Required self buff absent or unknown'; end
    if rule.ForbidBuff and E.hasbuff(ctx.self,rule.ForbidBuff)~=false then return false,'Conflicting self buff present or unknown'; end
    if rule.Status and E.hasbuff(target,rule.Status)~=true then return false,'Target status absent or unknown'; end
    if rule.MissingBuff and rule.MissingBuffExpireThreshold then
        local present=E.hasbuff(target,rule.MissingBuff);
        if present==false then
            -- Missing satisfies missing-or-expiring.
        elseif present==true then
            local remaining=E.provider('StatusRemaining',ctx,{Property='status_remaining',Operator='<',Value=rule.MissingBuffExpireThreshold,TextValue=E.join(rule.MissingBuff)},target);
            if remaining==nil then return false,'Buff present; remaining duration unknown'; end
            if remaining~=true and not (type(remaining)=='number' and remaining<=rule.MissingBuffExpireThreshold) then return false,'Buff not expiring'; end
        else
            return false,'Buff status unknown';
        end
    elseif rule.MissingBuff and E.hasbuff(target,rule.MissingBuff)~=false then
        local unknownRefresh=ctx.generatedRecruit and rule.SelectedAction=='Refresh' and target
            and target.id~=ctx.self.id and E.hasbuff(target,rule.MissingBuff)==nil;
        local unknownThiefAbility=ctx.generatedRecruit and ctx.mainJob=='THF' and target
            and ctx.self and target.id==ctx.self.id and E.hasbuff(target,rule.MissingBuff)==nil
            and ((rule.SelectedAction=='Sneak Attack' and rule.MissingBuff=='Sneak Attack')
                or (rule.SelectedAction=='Trick Attack' and rule.MissingBuff=='Trick Attack'));
        if not unknownRefresh and not unknownThiefAbility then return false,'Buff present or target status unknown'; end
        -- The server checks THF ability recasts and Trick Attack tank eligibility.
        -- Missing party status telemetry must not suppress those default rows.
    end
    if rule.ManaTarget then
        local mageJobs={'WHM','BLM','RDM','PLD','DRK','SMN','BLU'};
        local known=target and ((target.mp and target.mp>0) or (target.mpMax and target.mpMax>0)
            or E.contains(mageJobs,target.mainJob) or E.contains(mageJobs,target.subJob));
        if not known and E.provider('HasMPPool',ctx,target)~=true then return false,'Target MP pool not established'; end
    end
    if rule.Pet then
        if rule.Pet=='missing' and ctx.pet then return false,'Pet already present'; end
        if rule.Pet~='missing' and not ctx.pet then return false,'No living pet'; end
        if rule.Pet=='idle' and ctx.pet.status~=0 then return false,'Pet is not idle'; end
        if rule.PetHPBelow and (not ctx.pet or ctx.pet.hpp>rule.PetHPBelow) then return false,'Pet HP condition'; end
        if rule.PetTPAbove and (not ctx.pet or not ctx.pet.tp or ctx.pet.tp<rule.PetTPAbove) then return false,'Pet TP condition'; end
    end
    if rule.TwoHanded then
        if not ctx.weapon or not E.contains({4,6,7,8,10,12},ctx.weapon.skill) then return false,'Requires a two-handed weapon'; end
    end
    if rule.Mechanic=='interrupt' then
        local cast=ctx.target and S.casts[ctx.target.id];
        local supplied=E.provider('EnemyCasting',ctx,ctx.target);
        if supplied~=true and (not cast or cast.untilTime<=ctx.now) then return false,'No observed enemy cast'; end
    elseif rule.Mechanic=='convert' then
        if not ctx.self.mp or ctx.self.mp<math.max(150,ctx.hpMax*0.20) then return false,'Convert would leave too little HP'; end
        if E.provider('SafeConvert',ctx)~=true then return false,'Convert needs explicit SafeConvert provider approval'; end
    elseif rule.Mechanic=='behind' or rule.Mechanic=='trick_position' then
        local recruitThief=ctx.generatedRecruit and ctx.mainJob=='THF' and
            ((rule.Mechanic=='behind' and rule.SelectedAction=='Sneak Attack') or
             (rule.Mechanic=='trick_position' and rule.SelectedAction=='Trick Attack'));
        if not recruitThief and E.provider('PositionSafe',ctx,rule)~=true then return false,'Position has not been verified'; end
    elseif rule.Mechanic=='double_up' then
        local total=E.provider('RollTotal',ctx,rule);
        if type(total)~='number' or total<1 or total>(rule.MaximumRollTotal or 5) then return false,'Safe roll total not established'; end
    elseif rule.Mechanic=='enemy_mp' then
        if E.provider('EnemyHasMP',ctx,ctx.target)~=true then return false,'Enemy MP pool not established'; end
    elseif rule.Mechanic=='dispel' then
        local observed=target and target.dispellable;
        if observed==nil then observed=E.provider('EnemyDispellableBuff',ctx,rule,target); end
        if observed~=true and not (ctx.generatedRecruit and observed==nil and target and target.isMonster) then
            return false,'No verified dispellable buff';
        end
    elseif rule.Mechanic=='maneuver' then
        if E.hasbuff(ctx.self,'Overload')~=false then return false,'Overloaded or unknown status'; end
        local total=0;
        for k,v in pairs(ctx.self.buffs or {}) do
            if type(k)=='string' and k:find(' maneuver',1,true) then total=total+v; end
        end
        if total>=3 then return false,'Three maneuvers already active'; end
    elseif rule.Mechanic~=nil then return false,'Unknown mechanic';
    end
    if rule.RequiredItem and E.itemcount(ctx,rule.RequiredItem)<1 then return false,'Required item missing: ' .. rule.RequiredItem; end
    if rule.AmmoContains then
        if not ctx.ammo or not E.lower(ctx.ammo.name):find(E.lower(rule.AmmoContains),1,true) then return false,'Required equipped ammo is missing'; end
    end
    if rule.RequireProvider and E.provider(rule.RequireProvider,ctx,rule,target)~=true then return false,'Adapter condition not satisfied'; end
    return true;
end
function E.condition(ctx,rule,target)
    if rule.SongSlot then
        local instrument=ctx.ranged and E.contains({41,42},ctx.ranged.skill);
        local capacity=instrument and 2 or 1;
        local ok,why=E.slot_available(ctx,rule,'SongSlot',capacity);
        if not ok then return false,why; end
    end
    if rule.RollSlot then
        local ok,why=E.slot_available(ctx,rule,'RollSlot',ctx.mainJob=='COR' and 2 or 1);
        if not ok then return false,why; end
    end
    if not E.rule_job(ctx,rule) then return false,'Wrong job or effective level'; end
    local combat=E.incombat(ctx);
    if (E.contains({'dead','dead_ally','dead_party','dead_alliance'},rule.Target) or E.rule_is_raise(rule))
        and combat and not ctx.settings.RaiseInCombat then return false,'Raising in combat is disabled'; end
    local ok,why=E.condition_clause(ctx,rule,target);
    if not ok then return false,why; end
    if E.condition_clause_active(rule.Condition2) then
        local second=E.clone(rule.Condition2);
        second.Target=second.Target or rule.Target;
        second.SelectedAction=rule.SelectedAction; second.SelectedKind=rule.SelectedKind;
        ok,why=E.condition_clause(ctx,second,target);
        if not ok then return false,'Condition #2: '..tostring(why); end
    end
    return true;
end
function E.range(ctx,kind,res,rule)
    local api;
    if kind=='spell' then api=E.call(ctx.resources,'GetSpellRange',res and res.Index,false);
    elseif kind=='ability' or kind=='pet' or kind=='ws' then api=E.call(ctx.resources,'GetAbilityRange',res and res.Id,false); end
    local range;
    if type(api)=='number' and api>0 and api<=50 then range=api;
    elseif kind=='spell' or kind=='ranged' or (kind=='attack' and ctx.generatedRecruit) then range=20;
    elseif kind=='ws' then range=(rule.Ranged or E.ranged_ws(res and res.Name and res.Name[1])) and 20 or 3.5;
    else range=3.5; end
    -- A behavioral distance can narrow range, never extend a known engine limit.
    if E.number(rule.Range) then range=math.min(range,rule.Range); end
    return range;
end

function E.ranged_ws(name)
    return E.contains(WS[25],name) or E.contains(WS[26],name);
end
function E.area_damage_spell(kind,res,target)
    return kind=='spell' and target and target.isMonster
        and E.number(res and res.AreaRange,0)>0;
end

function E.entity_target(ctx,index)
    if not index or index<=0 then return nil; end
    if ctx.target and ctx.target.entityIndex==index then return ctx.target; end
    local id=E.number(E.call(ctx.entityMemory,'GetServerId',index));
    local flags=E.number(E.call(ctx.entityMemory,'GetSpawnFlags',index));
    if not id or id<=0 or not flags then return nil; end
    local target={id=id,entityIndex=index,zone=ctx.zone,name=E.call(ctx.entityMemory,'GetName',index),
        hpp=E.number(E.call(ctx.entityMemory,'GetHPPercent',index)),status=E.call(ctx.entityMemory,'GetStatus',index),
        claim=E.call(ctx.entityMemory,'GetClaimStatus',index),isMonster=math.floor(flags/16)%2==1,
        position=E.position(ctx.entityMemory,index)};
    target.alive=target.hpp~=nil and target.hpp>0;
    target.distance=E.distance(ctx.position,target.position);
    return target;
end

function E.rule_is_raise(rule)
    if not rule or rule.Type~='spell' then return false; end
    local function raises(name)
        return type(name)=='string' and (name=='Raise' or name=='Raise II' or name=='Raise III' or name=='Arise');
    end
    if raises(rule.Action) then return true; end
    if type(rule.Actions)=='table' and #rule.Actions>0 then
        for _,name in ipairs(rule.Actions) do if not raises(name) then return false; end end
        return true;
    end
    return false;
end
function E.candidates(ctx,rule,range)
    local original=rule.Target or 'self';
    range=range==math.huge and math.huge or (E.number(range,ctx.settings.TargetRange) or 20);
    local provided=E.provider('TargetSelector',ctx,rule,range);
    if type(provided)=='table' then return provided; end -- Empty is an authoritative empty set.
    if not E.target_supported(original) then return {}; end
    local aliases={party_any='ally',alliance_any='ally',party_lowest_hp='lowest',alliance_lowest_hp='lowest',
        party_lowest_mp='mp',alliance_lowest_mp='mp',statused_ally='status',debuffed_ally='status',
        lowest_hp_eligible_ally='lowest',eligible_lowest_hp='lowest',ally_with_removable_ailment='status',
        removable_ailment_ally='status',dead_ally='dead',dead_party='dead',dead_alliance='dead',
        current_target='enemy',foe='enemy',current_enemy_victim='target_of_target'};
    local target=aliases[original] or original;
    local function in_range(m)
        return m and (m.zone==nil or m.zone==ctx.zone) and (rule.SubjectOnly or (E.number(m.distance)~=nil and m.distance<=range));
    end
    local function stable(a,b)
        if (a.distance or math.huge)~=(b.distance or math.huge) then return (a.distance or math.huge)<(b.distance or math.huge); end
        if (a.id or 0)~=(b.id or 0) then return (a.id or 0)<(b.id or 0); end
        return (a.index or 99)<(b.index or 99);
    end
    if target=='self' then return ctx.self and {ctx.self} or {}; end
    if target=='player' or target=='owner' or target=='master' then
        local requester=ctx.requester or ctx.self;
        for _,m in ipairs(ctx.party or {}) do
            if requester and m.id==requester.id and (m.alive or rule.SubjectOnly) and in_range(m) then return {m}; end
        end
        return {};
    end
    if target=='pet' then return ctx.pet and in_range(ctx.pet) and {ctx.pet} or {}; end
    if E.contains({'party_pet','automaton','wyvern','avatar','luopan'},target) then
        -- Ownership and pet kind are not established by this file. Supply a selector adapter.
        return {};
    end
    if target=='party_leader' then
        local leader=E.local_party_leader_server_id(ctx);
        for _,m in ipairs(ctx.party or {}) do
            if m.id==leader and (m.alive or rule.SubjectOnly) and in_range(m) then return {m}; end
        end
        return {};
    end
    if target=='target_of_target' then
        local enemy=ctx.target;
        if not E.enemy_safe(ctx,enemy) then return {}; end
        local index=E.number(E.call(ctx.entityMemory,'GetTargetedIndex',enemy.entityIndex));
        for _,m in ipairs(ctx.party or {}) do
            if index and m.entityIndex==index and m.alive and in_range(m) then return {m}; end
        end
        return {};
    end
    if target=='enemy' or target=='player_target' then
        local enemy=target=='player_target' and (ctx.playerTarget or ctx.target) or ctx.target;
        if rule.SubjectOnly then return enemy and enemy.isMonster and {enemy} or {}; end
        return E.enemy_safe(ctx,enemy) and in_range(enemy) and {enemy} or {};
    end
    if target=='leader_target' or target=='tank_target' then
        local members=E.candidates(ctx,{Target=target=='leader_target' and 'party_leader' or 'party_tank'},math.huge);
        local member=members[1];
        local index=member and E.number(E.call(ctx.entityMemory,'GetTargetedIndex',member.entityIndex));
        local enemy=index and E.entity_target(ctx,index);
        return E.enemy_safe(ctx,enemy) and in_range(enemy) and {enemy} or {};
    end
    if E.contains({'nearest_foe','lowest_hp_foe','highest_hp_foe','add','eligible_add_threatening_party',
        'foe_targeting_self','foe_targeting_player','foe_targeting_tank','foe_targeting_healer',
        'nm','boss','beastman','undead','arcana','dragon'},target) then
        -- Do not pretend that the current target is a complete nearby-monster scan.
        local foes=E.provider('EnemyCandidates',ctx,rule,range);
        if type(foes)~='table' then return {}; end
        local out={};
        for _,foe in ipairs(foes) do
            local valid=E.enemy_safe(ctx,foe) and in_range(foe);
            local victimIndex=valid and E.number(E.call(ctx.entityMemory,'GetTargetedIndex',foe.entityIndex));
            local victim;
            for _,m in ipairs(ctx.party or {}) do if m.entityIndex==victimIndex then victim=m; break; end end
            if target=='add' or target=='eligible_add_threatening_party' then
                valid=valid and (not ctx.target or foe.id~=ctx.target.id) and victim~=nil;
            elseif target:match('^foe_targeting_') then
                local role=target:sub(15);
                if role=='self' then valid=valid and victimIndex==ctx.self.entityIndex;
                elseif role=='player' then valid=valid and victimIndex==(ctx.requester or ctx.self).entityIndex;
                else valid=valid and victim~=nil and E.role_name(victim)==role; end
            elseif E.contains({'nm','boss','beastman','undead','arcana','dragon'},target) then
                valid=valid and E.provider('EnemySelectorMatch',ctx,target,foe)==true;
            end
            if valid then out[#out+1]=foe; end
        end
        table.sort(out,function(a,b)
            if target=='lowest_hp_foe' and a.hpp~=b.hpp then return (a.hpp or 101)<(b.hpp or 101); end
            if target=='highest_hp_foe' and a.hpp~=b.hpp then return (a.hpp or -1)>(b.hpp or -1); end
            return stable(a,b);
        end);
        return out;
    end
    local allyTargets={'ally','lowest','mp','status','dead','party_member','alliance_member',
        'party_pool_tank','party_pool_support','party_pool_dps','party_tank','party_healer','party_melee','party_ranged',
        'party_caster','party_support','alliance_tank','alliance_healer','specific_party','specific_alliance','specific_trust',
        'highest_tp','lowest_tp','party_highest_tp','party_lowest_tp','closest_ally','furthest_ally','greatest_missing_hp_ally'};
    if not E.contains(allyTargets,target) then return {}; end
    local out={};
    -- A self-centered party spell cannot cover the other alliance parties.
    local includeAlliance=original~='party_any' and
        (ctx.settings.HealAlliance or original:find('alliance',1,true)~=nil);
    for _,m in ipairs(ctx.party or {}) do
        local wantsDead=target=='dead' or (rule.Property=='dead' and not rule.CheckTarget)
            or (not rule.SubjectOnly and E.rule_is_raise(rule));
        local inRequestedGroup=(target=='party_member' and m.index and m.index>0 and m.index<6)
            or (target=='alliance_member' and m.index and m.index>=6)
            or (PARTY_TARGET_POOLS[target] and m.index and m.index<6)
            or (target~='party_member' and target~='alliance_member' and not PARTY_TARGET_POOLS[target]
                and ((m.index or 99)<6 or includeAlliance));
        if inRequestedGroup and in_range(m)
            and (rule.SubjectOnly or (wantsDead and m.dead) or (not wantsDead and m.alive)) then
            local specific=target=='specific_party' or target=='specific_alliance' or target=='specific_trust';
            local named=not specific or (E.lower(rule.TargetName)~='' and E.lower(m.name)==E.lower(rule.TargetName));
            if target=='specific_trust' then
                local wanted=E.trust_picker_entry_by_name(rule.TargetName);
                local actual=E.trust_picker_entry_by_name(m.name);
                named=(named or (wanted~=nil and actual==wanted)) and (E.is_known_guest_name(m.name) or E.is_generated_recruit(m));
            end
            if named and E.member_matches_target_role(m,target) then out[#out+1]=m; end
        end
    end
    table.sort(out,function(a,b)
        if target=='highest_tp' or target=='party_highest_tp' then
            if (a.tp or -1)~=(b.tp or -1) then return (a.tp or -1)>(b.tp or -1); end
        elseif target=='lowest_tp' or target=='party_lowest_tp' then
            if (a.tp or math.huge)~=(b.tp or math.huge) then return (a.tp or math.huge)<(b.tp or math.huge); end
        elseif target=='closest_ally' then return stable(a,b);
        elseif target=='furthest_ally' then
            if a.distance~=b.distance then return a.distance>b.distance; end
        elseif target=='greatest_missing_hp_ally' then
            if (a.missingHP or -1)~=(b.missingHP or -1) then return (a.missingHP or -1)>(b.missingHP or -1); end
        elseif target=='mp' then
            if (a.mpp or math.huge)~=(b.mpp or math.huge) then return (a.mpp or math.huge)<(b.mpp or math.huge); end
        end
        if (a.hpp or 101)~=(b.hpp or 101) then return (a.hpp or 101)<(b.hpp or 101); end
        if (a.missingHP or -1)~=(b.missingHP or -1) then return (a.missingHP or -1)>(b.missingHP or -1); end
        return stable(a,b);
    end);
    -- Keep all ranked candidates so action legality can reject one without abandoning this row.
    return out;
end
function E.target_supported(target)
    return E.contains({'self','player','owner','master','ally','party_any','alliance_any',
        'party_member','alliance_member','party_pool_tank','party_pool_support','party_pool_dps','party_tank','party_healer',
        'party_melee','party_ranged','party_caster','party_support','alliance_tank','alliance_healer',
        'lowest','mp','party_lowest_hp','party_lowest_mp','alliance_lowest_hp','alliance_lowest_mp',
        'lowest_hp_eligible_ally','eligible_lowest_hp','greatest_missing_hp_ally','ally_with_removable_ailment','removable_ailment_ally',
        'highest_tp','lowest_tp','party_highest_tp','party_lowest_tp','closest_ally','furthest_ally',
        'specific_party','specific_alliance','specific_trust','status','statused_ally','debuffed_ally','dead','dead_ally','dead_party','dead_alliance',
        'pet','enemy','foe','current_target','player_target','party_leader','leader_target','tank_target','nearest_foe','lowest_hp_foe',
        'highest_hp_foe','add','eligible_add_threatening_party','foe_targeting_self','foe_targeting_player','foe_targeting_tank',
        'foe_targeting_healer','target_of_target','current_enemy_victim','party_pet','automaton','wyvern','avatar','luopan',
        'nm','boss','beastman','undead','arcana','dragon'},target);
end


function E.recipient_allowed(ctx,kind,res,target)
    if not target then return false,'Recipient unavailable'; end
    if kind=='attack' or kind=='ranged' then
        return E.enemy_safe(ctx,target),'Attack requires a safe enemy recipient';
    end
    if res and (kind~='item' or not ctx.generatedRecruit) and type(res.Targets)=='number' and res.Targets>0 then
        local flags=res.Targets;
        local function has(mask) return math.floor(flags/mask)%2==1; end
        local isSelf=ctx.self and target.id==ctx.self.id;
        local isPet=ctx.pet and target.id==ctx.pet.id;
        if isSelf and not has(1) then return false,'Action cannot target self'; end
        if target.isMonster and not has(32) then return false,'Action cannot target an enemy'; end
        if target.hpp==0 and not target.isMonster and not has(128) then return false,'Action cannot target a dead ally'; end
        if not isSelf and not isPet and not target.isMonster then
            if target.index and target.index>=6 and not (has(2) or has(8)) then return false,'Action does not support alliance targets'; end
            if target.index and target.index<6 and not (has(2) or has(4) or has(8)) then return false,'Action does not support allied targets'; end
        end
    end
    return true;
end

local RECRUIT_FOOD_ITEMS={['Meat Mithkabob']=true,['Sole Sushi']=true,['Boiled Crab']=true,
    ['Tavnazian Taco']=true,['Apple Pie']=true,['Marron Glace']=true};
function E.guest_action_allowed(ctx,rule,kind,name,res,target)
    if kind=='ws' and ctx.generatedRecruit and E.recruit_stance_mode(ctx.self and ctx.self.id,ctx.self and ctx.self.name)=='P' then
        return false,'Passive Recruit does not use melee weapon skills';
    end
    local recipient,recipientWhy=E.recipient_allowed(ctx,kind,res,target);
    if not recipient then return false,recipientWhy; end
    if kind=='item' then
        if not ctx.generatedRecruit or not ctx.self or target.id~=ctx.self.id or not res or not res.Id then
            return false,'Recruit supplies are self only';
        end
        if RECRUIT_FOOD_ITEMS[name] then return false,'Recruit food Gambits are unavailable'; end
        return true;
    end
    if kind=='pet' then return false,'Guest pet execution is unavailable'; end
    local permission,permissionWhy=E.trust_permission(ctx,kind,name);
    if permission==false then return false,permissionWhy; end
    if (rule.AreaDamage or E.area_damage_spell(kind,res,target)) and not ctx.settings.AllowAreaDamage then
        return false,'Area damage is disabled globally'; end
    if rule.Special and not ctx.settings.AllowSpecialAbilities then return false,'Special ability rule is disabled globally'; end
    if SPECIAL[name] and not ctx.settings.AllowSpecialAbilities then return false,'Special abilities are disabled'; end
    if kind=='spell' then
        if E.is_trust_spell(res,name) then return false,'Trust summon spells are not Gambit actions'; end
        local ok,why=E.spell_level(ctx,res);
        if not ok then return false,why; end
        if E.hasbuff(ctx.self,{'Silence','Mute',6,29})==true then return false,'Silenced'; end
        if ctx.generatedRecruit then
            local affordable,why=E.spell_mp_policy(ctx,rule,res);
            if affordable==false then return false,why; end
            -- Unknown effective cost stays eligible for final server validation.
        end
    elseif kind=='ability' or kind=='ws' then
        if not E.ability_known(ctx,res,kind) then return false,'Action outside this Trust arsenal or level'; end
        if E.hasbuff(ctx.self,{'Amnesia',16})==true then return false,'Amnesia'; end
        if kind=='ws' and (ctx.tp or 0)<(rule.TP or 1000) then return false,'Insufficient TP'; end
    elseif kind=='ranged' then
        if ctx.generatedRecruit then
            if not E.generated_recruit_ranged_allowed(ctx) then return false,'Recruit job has no ranged arsenal'; end
        elseif permission~=true and not E.contains({'RNG','COR'},ctx.mainJob) then return false,'Trust has no ranged arsenal'; end
    elseif kind~='attack' then return false,'Unsupported Trust action'; end
    if target and target.isMonster and not E.enemy_safe(ctx,target) then return false,'Unsafe enemy'; end
    -- Trust recasts, MP cost modifiers, equipment and final legality belong to xi_map.
    return true;
end
function E.allowed_action(ctx,rule,kind,name,res,target)
    if kind=='item' then return false,'Player consumable Gambits are unavailable'; end
    if kind=='attack' then
        if not target or not target.isMonster then return false,'Attack requires an enemy target'; end
        return true;
    end
    if E.contains({'Ready','Pet commands','Blood Pact: Rage','Blood Pact: Ward'},name) then
        return false,'Menu entry is not an executable action; choose a specific pet move';
    end
    if SPECIAL[name] and not ctx.settings.AllowSpecialAbilities then return false,'Special abilities are disabled'; end
    if rule.Special and not ctx.settings.AllowSpecialAbilities then return false,'Special ability rule is disabled globally'; end
    -- Selecting an explicit item row is the player's opt-in to spending that item.
    -- The legacy global switch still gates implicit consumable policies.
    if rule.Consumable and kind~='item' and not ctx.settings.AllowConsumables then return false,'Consumable rules are disabled globally'; end
    if (rule.AreaDamage or E.area_damage_spell(kind,res,target)) and not ctx.settings.AllowAreaDamage then
        return false,'Area damage is disabled globally'; end
    if res and kind~='ranged' and type(res.Targets)=='number' and res.Targets>0 then
        local flags=res.Targets;
        local function has(mask) return math.floor(flags/mask)%2==1; end
        if target==ctx.self and not has(1) then return false,'Action cannot target self'; end
        if target.isMonster and not has(32) then return false,'Action cannot target an enemy'; end
        if target.hpp==0 and not target.isMonster and not has(128) then return false,'Action cannot target a dead ally'; end
        if target~=ctx.self and target~=ctx.pet and not target.isMonster then
            if target.index and target.index>=6 and not (has(2) or has(8)) then return false,'Action does not support alliance targets'; end
            if target.index and target.index<6 and not (has(2) or has(4) or has(8)) then return false,'Action does not support allied targets'; end
        end
    end
    if kind=='spell' then
        if E.hasbuff(ctx.self,{'Silence','Mute',6,29})~=false then return false,'Silenced or status unknown'; end
        if not res or not res.Index then return false,'Spell resource missing'; end
        if E.is_trust_spell(res,name) then return false,'Trust summon spells are not Gambit actions'; end
        if not E.truth(E.call(ctx.player,'HasSpellData')) or not E.truth(E.call(ctx.player,'HasSpell',res.Index)) then
            return false,'Spell not learned or data not loaded';
        end
        local levelOk,levelWhy=E.spell_level(ctx,res);
        if not levelOk then return false,levelWhy or 'Spell not available at current main/sub level or configured cap'; end
        local timer=E.call(ctx.recastMemory,'GetSpellTimer',res.Index);
        if type(timer)~='number' or timer>0 then return false,'Spell recast not ready/known'; end
        local cost=E.spell_mp_cost(ctx,res,rule);
        if cost==nil or not ctx.self.mp then return false,'MP cost/current MP unavailable'; end
        local reserve=rule.Emergency and 0 or (rule.MPReserve or ctx.settings.MPReserve);
        if ctx.self.mp<cost+(cost>0 and reserve or 0) then return false,'Insufficient MP after reserve'; end
        if res.Skill==43 or rule.BlueMagic then
            local set=E.provider('BlueSet',ctx);
            if type(set)~='table' then set=S.profile and S.profile.BlueSet or {}; end
            if not E.contains(set,name) and set[name]~=true and set[res.Index]~=true then return false,'BLU spell is not in the declared/verified equipped set'; end
            if ctx.now<(S.blueSetUntil or 0) then return false,'Blue-set change lockout'; end
        end
        local family=name:match('^(%a+):');
        if family and TOOLS[family] and E.itemcount(ctx,TOOLS[family],true)<1 then return false,'Missing ninja tool: ' .. TOOLS[family]; end
        if target~=ctx.self and (res.Targets or 0)>0 then
            local flags=res.Targets;
            if target.isMonster and math.floor(flags/32)%2~=1 then return false,'Spell does not permit enemy targets'; end
            if target.hpp==0 and not target.isMonster and math.floor(flags/128)%2~=1 then return false,'Spell does not permit dead targets'; end
            if flags==1 then return false,'Self-only spell'; end
        end
    elseif kind=='ability' or kind=='pet' or kind=='ws' then
        if E.hasbuff(ctx.self,{'Amnesia',16})~=false then return false,'Amnesia or status unknown'; end
        local levelOk,levelWhy=E.ability_level_allowed(ctx,res,kind);
        if not levelOk then return false,levelWhy or 'Ability unavailable at current main/sub level or era cap'; end
        if not res or not E.ability_known(ctx,res,kind) then return false,'Ability/WS unavailable or not learned'; end
        if kind~='ws' and not E.ability_ready(ctx,res) then return false,'Ability recast not ready/known'; end
        if kind=='ws' then
            if not ctx.tp or ctx.tp<(rule.TP or 1000) then return false,'Insufficient TP'; end
            if target.isMonster and not (rule.Ranged or E.ranged_ws(name)) and not ctx.engaged then
                return false,'Melee weapon skills require engagement'; end
        end
        if kind=='pet' then
            if not ctx.pet then return false,'No pet'; end
            local mp=E.number(res.ManaCost,0);
            if not ctx.self.mp or ctx.self.mp<mp+(rule.Emergency and 0 or ctx.settings.MPReserve) then return false,'Insufficient pact MP'; end
        end
    elseif kind=='item' then
        local location=E.player_item_location(ctx,name);
        if not location then return false,'Consumable missing from accessible bags'; end
        if location.bag~=0 and location.bag~=3 and not E.free_inventory_slot(ctx) then
            return false,'Inventory full; move the consumable from its bag';
        end
    elseif kind=='ranged' then
        if not ctx.ranged or not ctx.ammo or ctx.ammo.count<1 then return false,'Ranged weapon/ammo unavailable'; end
    else return false,'Unsupported action type'; end
    if rule.Ranged or kind=='ranged' or (kind=='ws' and E.ranged_ws(name)) then
        if not ctx.ranged or not ctx.ammo or ctx.ammo.count<1 then return false,'Ranged weapon/ammo unavailable'; end
    end
    if rule.Family then
        local w=rule.Ranged and ctx.ranged or ctx.weapon;
        if not w or w.skill~=rule.Family then return false,'Wrong equipped weapon family'; end
    end
    return true;
end
function E.action_resource_available(ctx,rule,kind,name)
    if not ctx or not rule or rule.Empty==true then return true; end
    if ctx.guestBridge or ctx.catalogActorKind=='guest' then
        if kind=='none' then return true; end
        if kind=='attack' or kind=='ranged' then
            local permission,why=E.trust_permission(ctx,kind,name);
            if permission~=nil then return permission,why; end
            if kind=='ranged' and ctx.generatedRecruit and not E.generated_recruit_ranged_allowed(ctx) then
                return false,'Recruit job has no ranged arsenal';
            end
            return kind=='attack' or E.generated_recruit_ranged_allowed(ctx) or E.contains({'RNG','COR'},ctx.mainJob),'Trust ranged arsenal unavailable';
        end
        if kind=='item' then
            return ctx.generatedRecruit and E.resource(ctx,kind,name)~=nil,'Recruit supply unavailable';
        end
        if kind=='pet' then return false,'Guest pet execution unavailable'; end
        if not E.safe_name(name) then return false,'Invalid action name'; end
        local res=E.resource(ctx,kind,name);
        if not res then return false,'Action resource unavailable'; end
        if kind=='spell' then return E.spell_level(ctx,res); end
        return E.ability_known(ctx,res,kind),'Trust action unavailable';
    end
    if kind=='none' then return true; end
    if kind=='attack' then return true; end
    if kind=='ranged' then
        if ctx.ranged and ctx.ammo and ctx.ammo.count and ctx.ammo.count>0 then return true; end
        return false,'Ranged attack needs a ranged weapon and ammo';
    end
    if not E.safe_name(name) then return false,'Invalid action name'; end
    local res=E.resource(ctx,kind,name);
    if not res then return false,name..' is not available for this character'; end
    if kind=='spell' then
        if not E.truth(E.call(ctx.player,'HasSpellData')) or not E.truth(E.call(ctx.player,'HasSpell',res.Index)) then
            return false,'Current job does not have '..name;
        end
        local levelOk,levelWhy=E.spell_level(ctx,res);
        if not levelOk then return false,levelWhy or ('Current job cannot cast '..name); end
        return true;
    end
    if kind=='ability' or kind=='pet' or kind=='ws' then
        local levelOk,levelWhy=E.ability_level_allowed(ctx,res,kind);
        if not levelOk then return false,levelWhy or ('Current job cannot use '..name); end
        if not E.ability_known(ctx,res,kind) then
            return false,'Current job does not have '..name;
        end
        if kind=='ws' and rule.Family then
            local w=rule.Ranged and ctx.ranged or ctx.weapon;
            if not w or w.skill~=rule.Family then return false,name..' requires a different equipped weapon'; end
        end
        return true;
    end
    if kind=='item' then return res.Type==7,'Only consumable items are supported'; end
    return false,'Unsupported action type';
end
function E.rule_action_unavailable(ctx,rule)
    if not rule or rule.Empty==true then return nil; end
    local kind=rule.Type;
    local names;
    if kind=='ws_auto' then
        kind='ws';
        if ctx.guestBridge or ctx.catalogActorKind=='guest' then
            names=E.guest_ws_names(ctx);
            if not names or #names==0 then return 'No generic job weapon skills are configured for '..tostring(ctx.mainJob or 'this Trust'); end
        else
            local w=rule.Ranged and ctx.ranged or ctx.weapon;
            if not w or not WS[w.skill] then return 'No supported weapon skill family is equipped'; end
            names=(S.profile and S.profile.WeaponSkills and S.profile.WeaponSkills[w.skill]) or WS[w.skill];
        end
    elseif kind=='cure' then
        kind='spell'; names=rule.Actions or {'Cure V','Cure IV','Cure III','Cure II','Cure'};
    elseif kind=='attack' then
        names={'Attack'};
    elseif kind=='ranged' then
        names={'Ranged Attack'};
    else
        names=rule.Actions or {rule.Action};
    end
    local last='No configured action';
    for _,name in ipairs(names or {}) do
        local ok,why=E.action_resource_available(ctx,rule,kind,name);
        if ok then return nil; end
        last=why or last;
    end
    return last;
end
function E.set_message(text,seconds)
    S.ui.message=tostring(text or '');
    S.ui.messageUntil=E.now()+(seconds or 4);
end
function E.top_message_text()
    if S.ui.message and E.now()<(S.ui.messageUntil or 0) then return S.ui.message; end
    return E.job_combo_label();
end
function E.target_token(ctx,rule,target)
    if target==nil then return nil; end
    if target==ctx.self then return '<me>'; end
    if target==ctx.pet then return '<pet>'; end
    if target.isMonster then return ctx.target and ctx.target.id==target.id and '<t>' or nil; end
    -- FFXI Offline: squad mates/Trusts (entity index 0x700 and up) are only accepted by the game as the current target:
    -- <pN> and their name both give "A command error occurred". E.submit targets them for that one command (see below).
    if target.entityIndex and target.entityIndex>=0x700 then return '<t>'; end
    if target.index and target.index>=0 and target.index<=5 then
        for _,member in ipairs(ctx.party or {}) do
            if member.index==target.index and member.id==target.id
                and member.entityIndex==target.entityIndex then
                return '<p'..target.index..'>';
            end
        end
    end
    -- Squad mates/Trusts: the party list can show a shortened name ("Kasu" for Kasumi), which /ma cannot find.
    -- Use the party slot of whoever has this server id, else the entity's real name.
    for _,member in ipairs(ctx.party or {}) do
        if target.id and member.id==target.id and member.index and member.index>=1 and member.index<=5 then
            return '<p'..member.index..'>';
        end
    end
    local name=target.name;
    if target.entityIndex and target.entityIndex>0 then
        local real=E.call(ctx.entityMemory,'GetName',target.entityIndex);
        if type(real)=='string' and real~='' then name=real; end
    end
    if type(name)~='string' or not name:match('^[%a][%a%d_%-]*$') then return nil; end
    return '"' .. name .. '"';
end
function E.bridge_action(ctx,kind,res)
    if kind=='attack' then
        return 'attack',0;
    elseif kind=='spell' then
        local id=E.number(res and (res.Index or res.Id));
        return id and 'spell' or nil,id;
    elseif kind=='ability' then
        local id=E.number(res and res.Id);
        if id and id>=512 then id=id-512; end
        return id and 'ability' or nil,id;
    elseif kind=='pet' then
        local id=E.number(res and res.Id);
        if id and id>=512 then id=id-512; end
        return id and 'petability' or nil,id;
    elseif kind=='ws' then
        local id=E.number(res and res.Id);
        return id and 'ws' or nil,id;
    elseif kind=='ranged' then
        return 'ranged',0;
    elseif kind=='item' and ctx and ctx.generatedRecruit then
        local id=E.number(res and res.Id);
        return id and 'item' or nil,id;
    end
    return nil,nil;
end
function E.bridge_entity_identifier(entity, fallback)
    local id=E.number(entity and entity.id) or E.number(fallback and fallback.id);
    local index=E.number(entity and (entity.entityIndex or entity.targetIndex)) or E.number(fallback and (fallback.entityIndex or fallback.targetIndex));
    if id and id>0 and id>65535 then return id; end
    if index and index>0 then return index; end
    return id;
end
function E.bridge_command(ctx,plan)
    if not ctx or not plan or not plan.targetId then return nil,'Bridge plan missing IDs'; end
    local actorId=E.bridge_entity_identifier(ctx.actor or ctx.self,{id=plan.actorId});
    if not actorId or actorId<=0 then return nil,'Bridge actor unavailable'; end
    local targetId=E.bridge_entity_identifier(plan.target,{id=plan.targetId,entityIndex=plan.targetIndex});
    if not targetId or targetId<=0 then return nil,'Bridge target unavailable'; end
    local actionType,actionId=E.bridge_action(ctx,plan.kind,plan.resource);
    if not actionType or actionId==nil then return nil,'Bridge action ID unavailable'; end
    return string.format('/say !gambit act %u %s %u %u',actorId,actionType,actionId,targetId);
end
function E.bridge_control_command(actor,state)
    local actorId=E.bridge_entity_identifier(actor);
    if not actorId or actorId<=0 then return nil; end
    return string.format('/say !gambit control %u %s',actorId,state and 'on' or 'off');
end
function E.bridge_release_command(actor)
    local actorId=E.bridge_entity_identifier(actor);
    if not actorId or actorId<=0 then return nil; end
    return string.format('/say !gambit release %u debug',actorId);
end
function E.bridge_spawn_command(trustKey)
    trustKey=tostring(trustKey or ''):upper();
    trustKey=trustKey:gsub('[^A-Z0-9_]+','_'):gsub('^_+',''):gsub('_+$','');
    if not TRUST_PICKER_BY_KEY or not TRUST_PICKER_BY_KEY[trustKey] then return nil; end
    return string.format('/say !gambit spawn %s debug',trustKey);
end
function E.player_chat_active(chat)
    chat=chat or E.call(AshitaCore,'GetChatManager');
    local inputOpen=E.call(chat,'IsInputOpen');
    return inputOpen==true or (type(inputOpen)=='number' and inputOpen~=0) or E.now()<(S.userChatUntil or 0);
end
function E.bridge_trace(stage,command,meta)
    local clean=tostring(command or ''):gsub('[\r\n]',' '):sub(1,180);
    meta=meta or {};
    local line=string.format('%s tick=%.3f stage=%s mode=%s origin=%s actor=%s/%s target=%s/%s command=%s',
        os.date('%Y-%m-%d %H:%M:%S'),E.now(),tostring(stage),tostring(meta.mode or '-'),
        tostring(meta.origin or '-'),tostring(meta.actorId or '-'),tostring(meta.actorIndex or '-'),
        tostring(meta.targetId or '-'),tostring(meta.targetIndex or '-'),clean);
    local lines=S.bridgeTraceLines;
    lines[#lines+1]=line;
    if #lines>256 then table.remove(lines,1); end
    local root=E.root();
    if root then
        local file=io.open(root..'bridge-trace.log','w');
        if file then file:write(table.concat(lines,'\n'),'\n'); file:close(); end
    end
end
function E.bridge_meta(command,background,meta)
    meta=meta or {};
    meta.mode=1;
    meta.origin=meta.origin or ((debug and debug.getinfo and debug.getinfo(3,'n') or {}).name) or 'unknown';
    local op,actor,_,_,target=command:match('!gambit%s+(%S+)%s+(%d+)%s+(%S+)%s+(%S+)%s+(%d+)');
    if not op then op,actor=command:match('!gambit%s+(%S+)%s+(%d+)'); end
    meta.actorId=meta.actorId or tonumber(actor);
    if op=='act' then meta.targetId=meta.targetId or tonumber(target); end
    return meta;
end
function E.send_bridge_command(command,background,meta)
    -- Offline build: only the buff check (!gambit status, answered by the server module gambit_status.lua) is sent.
    if not (meta and meta.origin=='status_request') then return false,'Offline build: there is no online server to send this to.'; end
    local chat=E.call(AshitaCore,'GetChatManager');
    if not chat or type(command)~='string' or (not command:match('^!gambit ') and not command:match('^/say%s+!gambit ')) then return false,'Chat manager unavailable'; end
    if E.player_chat_active(chat) then return false,'Player chat active'; end
    local now=E.now();
    -- Control keepalives and status polls may serve five Recruits at once.
    -- Send one background command at a time; combat actions remain immediate.
    if background and now<(S.nextBackgroundBridgeAt or 0) then return false,'Background bridge pacing'; end
    -- Bridge requests are ordinary game /say commands. Queue them on the
    -- game-command path used by player actions; the immediate Ashita parser
    -- can also surface a client-side command error after a successful send.
    if command:match('^!gambit ') then command='/say '..command; end
    meta=E.bridge_meta(command,background,meta);
    E.bridge_trace('queue_attempt',command,meta);
    local ok,err=pcall(function() chat:QueueCommand(1,command); end);
    if not ok then E.bridge_trace('queue_exception',command,meta); return false,err; end
    S.bridgeQuietUntil=now+1.25;
    if background then S.nextBackgroundBridgeAt=now+0.75; end
    S.bridgeSubmitted[#S.bridgeSubmitted+1]={command=command,time=now,meta=meta};
    while #S.bridgeSubmitted>32 do table.remove(S.bridgeSubmitted,1); end
    E.bridge_trace('submitted_unconfirmed',command,meta);
    return true,'Chat command submitted';
end
function E.is_command_error_message(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','')
    text=text:gsub('^%s+',''):gsub('%s+$','')
    -- The client prefixes this one generic parser line with literal dots.
    return text:match('^%.%.%.%s*A command error occurred%.$')~=nil
end
function E.recruit_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local at=text:find('TRCR2|',1,true) or text:find('TRCR|',1,true);
    if not at then return false; end
    local actor,remaining,roleCodes,jobMask=text:sub(at):match('^TRCR2|(%d+)|(%d+)|([A-Z,]+)|(%d+)%s*$');
    if not actor then actor,remaining,roleCodes=text:sub(at):match('^TRCR|(%d+)|(%d+)|([A-Z,]+)'); end
    if not actor then actor,remaining,roleCodes=text:sub(at):match('^TRCR|(%d+)|(%d+)|([TSD]+)'); end
    if not actor then actor,remaining=text:sub(at):match('^TRCR|(%d+)|(%d+)'); end
    if actor and remaining then
        local ctx=E.context('recruit-status');
        if ctx.self and ctx.self.id==tonumber(actor) then
            local mask=tonumber(jobMask);
            S.recruitJobMask=(mask and mask>=0 and mask<=4194303 and mask%1==0) and mask or 0;
            S.recruitJobActor=tonumber(actor);
            S.recruitCooldown={seconds=math.min(900,tonumber(remaining)),at=E.now()};
            S.recruitStatusNextAt=E.now()+60;
            if roleCodes then
                local roles={T='tank',S='support',D='dps'};
                local parts={};
                if roleCodes:find(',',1,true) then
                    for code in roleCodes:gmatch('[^,]+') do parts[#parts+1]=code; end
                else
                    for slot=1,#roleCodes do parts[slot]=roleCodes:sub(slot,slot); end
                end
                if #parts~=5 then return true; end
                for slot=1,5 do
                    local code=parts[slot];
                    local confirmed=roles[code] or (E.contains(E.recruit_slot_choices(),code) and code) or ({'tank','support','dps','dps','dps'})[slot];
                    S.recruitSlotConfirmed[slot]=confirmed;
                    local pending=S.recruitSlotPending[slot];
                    if pending and not E.contains(E.recruit_slot_choices(),pending.role) then
                        S.recruitSlotPending[slot]=nil; pending=nil;
                    end
                    if not pending then
                        S.recruitSlotRoles[slot]=confirmed;
                    elseif pending.sentRole==confirmed then
                        pending.sentRole=nil; pending.sentAt=nil;
                        -- A receipt for an older choice must not shorten the latest click delay.
                        pending.dueAt=math.max(pending.dueAt or 0,E.now());
                    end
                    if pending and not pending.sentAt and confirmed==pending.role then
                        S.recruitSlotPending[slot]=nil;
                    end
                end
            end
        end
    end
    return true;
end
function E.queue_recruit_slot_role(slot,role)
    if type(slot)~='number' or slot<1 or slot>5 or slot%1~=0 or
        not E.contains(E.recruit_slot_choices(),role) then return false,'Invalid Recruit pool'; end
    local now=E.now();
    local pending=S.recruitSlotPending[slot] or {};
    pending.role=role;
    pending.at=now;
    -- Commit only after this slot has had three seconds without another click.
    pending.dueAt=now+3;
    S.recruitSlotPending[slot]=pending;
    S.recruitStatusNextAt=now+5;
    return true;
end
function E.flush_recruit_slot_roles()
    -- User operations take priority over background reservation synchronization.
    if S.sortPending or S.optimizePending then return; end
    local entries=E.party_slot_entries();
    if not entries[1] or entries[1].name=='vacant' then return; end
    local now=E.now();
    for slot=1,5 do
        local pending=S.recruitSlotPending[slot];
        -- Preserve the desired pool, but never retry against an occupied slot.
        if pending and entries[slot+1] and entries[slot+1].name=='vacant' then
            if pending.sentAt and now-pending.sentAt>=5 then
                pending.sentAt=nil; pending.sentRole=nil;
            end
            if not pending.sentAt and now>=(pending.dueAt or 0) then
                if pending.role==S.recruitSlotConfirmed[slot] then
                    S.recruitSlotPending[slot]=nil;
                else
                    local chat=E.call(AshitaCore,'GetChatManager');
                    if chat and not E.player_chat_active(chat) then
                        local command=string.format('/say !recruit slot%d=%s',slot,pending.role);
                        local ok=pcall(function() chat:QueueCommand(1,command); end);
                        if ok then
                            pending.sentRole=pending.role;
                            pending.sentAt=now;
                            S.recruitCommands[command]=now;
                            S.recruitStatusNextAt=now+5;
                        end
                    end
                end
            end
        end
    end
end
function E.queue_recruit(action)
    do return false,'There are no Recruits on this server.'; end
    if action~='status' and E.recruit_party_full() then return false,'Your party is already full.'; end
    local chat=E.call(AshitaCore,'GetChatManager');
    if not chat then return false,'Chat manager unavailable'; end
    if E.player_chat_active(chat) then return false,'Player chat active'; end
    local command=action=='status' and '/say !recruit status' or '/say !recruit';
    local now=E.now();
    if S.recruitCommands[command] and now-S.recruitCommands[command]<3 then return false,'Request already pending'; end
    S.recruitCommands[command]=now;
    local ok,err=pcall(function() chat:QueueCommand(1,command); end);
    if not ok then S.recruitCommands[command]=nil; return false,err; end
    S.recruitStatusRequestedAt=now;
    S.recruitStatusNextAt=now+5;
    return true;
end
function E.queue_optimize()
    do return false,'Optimize is an online-server feature and is not available here.'; end
    if S.optimizePending then return false,'Optimization is already in progress.'; end
    local chat=E.call(AshitaCore,'GetChatManager');
    if not chat then return false,'Chat manager unavailable'; end
    local now=E.now();
    S.optimizePending={at=now}; S.optimizeCommandAt=now;
    local ok,err=pcall(function() chat:QueueCommand(1,'/say !optimize'); end);
    if not ok then S.optimizePending=nil; S.optimizeCommandAt=nil; return false,tostring(err); end
    return true;
end
function E.optimize_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local result=text:match('(Optimize complete:[^\r\n]*)') or text:match('(Optimize cancelled:[^\r\n]*)');
    if not result then return false; end
    S.optimizePending=nil; S.optimizeCommandAt=nil;
    E.set_message(result,8);
    return true;
end
function E.optimize_timeout()
    if S.optimizePending and E.now()-(S.optimizePending.at or 0)>20 then
        S.optimizePending=nil; S.optimizeCommandAt=nil;
        E.set_message('Optimize request was not confirmed by the server.',5);
    end
end
function E.optimize_display(width,imgui)
    local pending=S.optimizePending~=nil;
    if pending and imgui.BeginDisabled and imgui.EndDisabled then imgui.BeginDisabled(true); end
    local clicked=E.help_button(pending and 'OPTIMIZING...' or 'OPTIMIZE',{width,E.ui_button_h()},
        'Equip a balanced set for your current main job from Inventory and Wardrobes.');
    if pending and imgui.BeginDisabled and imgui.EndDisabled then imgui.EndDisabled(); end
    if clicked and not pending then
        local ok,reason=E.queue_optimize();
        if not ok then E.set_message(tostring(reason),5); end
    end
end
function E.queue_sort()
    do return false,'Sorting is an online-server feature and is not available here.'; end
    if S.sortPending then return false,'Sorting is already in progress.'; end
    local chat=E.call(AshitaCore,'GetChatManager');
    if not chat then return false,'Chat manager unavailable'; end
    local now=E.now();
    local command='/say !sort';
    S.sortPending={at=now};
    S.sortCommandAt=now;
    local ok,err=pcall(function() chat:QueueCommand(1,command); end);
    if not ok then S.sortPending=nil; S.sortCommandAt=nil; return false,tostring(err); end
    return true;
end
function E.sort_response(message)
    if not S.sortPending then return false; end
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local result=text:match('(Sort complete:[^\r\n]*)') or text:match('(Sort cancelled:[^\r\n]*)');
    if not result then return false; end
    S.sortPending=nil;
    S.sortCommandAt=nil;
    E.set_message(result,5);
    return true;
end
function E.sort_timeout()
    if S.sortPending and E.now()-(S.sortPending.at or 0)>20 then
        S.sortPending=nil;
        S.sortCommandAt=nil;
        E.set_message('Sort request was not confirmed by the server.',5);
    end
end
function E.recruit_party_full()
    local mem=E.call(AshitaCore,'GetMemoryManager');
    local party=E.call(mem,'GetParty');
    if not party then return false; end
    local occupied=0;
    for slot=0,5 do
        if E.truth(E.call(party,'GetMemberIsActive',slot)) then occupied=occupied+1; end
    end
    return occupied>=6;
end
function E.recruit_button_label()
    local snapshot=S.recruitCooldown;
    if not snapshot then return 'RECRUIT --:--##manual_recruit'; end
    local seconds=math.max(0,math.ceil(snapshot.seconds-(E.now()-snapshot.at)));
    return string.format('RECRUIT %d:%02d##manual_recruit',math.floor(seconds/60),seconds%60);
end
function E.is_hidden_bridge_chat_message(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('^%s+',''):gsub('%s+$','');
    text=text:gsub('[\030\031].',''):gsub('^%s*>>%s*','');
    if text:match('^!gambit%s+') or text:match('^!join%s*$') or text:match('^!recruit[%s]*') then return true; end
    if text:match('^/say%s+!gambit%s+') or text:match('^/say%s+!recruit[%s]*') then return true; end
    if text:match(':%s*!gambit%s+') or text:match(':%s*!join%s*$') or text:match(':%s*!recruit[%s]*') then return true; end
    return false;
end
function E.safe_name(name)
    return type(name)=='string' and #name>0 and #name<100 and not name:find('[%c";<>]');
end
function E.is_trust_spell_id(id)
    id=E.number(id);
    return id~=nil and id>=896 and id<=1050;
end
function E.is_trust_spell_name(name)
    if type(name)~='string' or name=='' then return false; end
    if TRUST_PICKER_BY_NAME and TRUST_PICKER_BY_NAME[name] then return true; end
    local normalized=name:upper():gsub('[^A-Z0-9_]+','_'):gsub('^_+',''):gsub('_+$','');
    return TRUST_PICKER_BY_KEY and TRUST_PICKER_BY_KEY[normalized]~=nil;
end
function E.trust_name_key(name)
    name=tostring(name or ''):upper();
    name=name:gsub('%(UC%)','UC');
    return name:gsub('[^A-Z0-9]+','');
end
function E.is_trust_spell(res,name,id)
    if E.is_trust_spell_id(id or (res and (res.Index or res.Id))) then return true; end
    local spellName=name;
    if (not spellName or spellName=='') and res and res.Name then spellName=res.Name[1]; end
    return E.is_trust_spell_name(spellName);
end
function E.timerkey(ctx,rule,target,name)
    if ctx.generatedRecruit and ctx.mainJob=='RDM' and rule.Type=='spell'
        and (name=='Dia II' or name=='Dia') then
        -- Dia tiers share one status effect. Key by enemy identity, not tier or
        -- recruit, so a second RDM does not immediately overwrite the first.
        return 'recruit-dia:'..tostring(ctx.zone)..':'..tostring(target.id)..':'..tostring(target.entityIndex);
    end
    return E.rule_timerkey(ctx,rule) .. ':' .. tostring(target.id) .. ':' .. name;
end
function E.rule_timerkey(ctx,rule)
    return 'rule:'..tostring(ctx.zone)..':'..tostring((ctx.actor or ctx.self).id)..':'..rule.Id;
end

function E.removal_statuses(name)
    local statuses={Poisona={'Poison'},Paralyna={'Paralyze'},Blindna={'Blind'},Silena={'Silence'},
        Stona={'Petrification'},Viruna={'Disease','Plague'},Cursna={'Curse','Doom',20,30},
        Erase={'Slow','Elegy','Bind','Weight','Dia','Bio','Burn','Frost','Choke','Rasp','Shock','Drown',13,194,11,12,128,129,130,131,132,133}};
    return statuses[name]; -- Retains the supplied mapping; retail coverage is not expanded here.
end

-- These are usefulness checks only. The server item scripts still decide whether
-- a Recruit may use an item and apply its actual effect.
local SMART_ITEM_AILMENTS={
    ['Antidote']={'Poison'}, ['Echo Drops']={'Silence'}, ['Eye Drops']={'Blind'},
    ['Remedy']={'Poison','Paralyze','Blind','Silence','Disease'},
    ['Holy Water']={'Doom','Curse',20,30},
};
local SMART_ITEM_FOOD={['Meat Mithkabob']=true,['Sole Sushi']=true,['Boiled Crab']=true,
    ['Tavnazian Taco']=true,['Apple Pie']=true,['Marron Glace']=true};
local SMART_ITEM_HP={['Potion']=true,['Hi-Potion']=true,['X-Potion']=true};
local SMART_ITEM_MP={['Ether']=true,['Hi-Ether']=true,['Pro-Ether']=true};
local SMART_ITEM_ELIXIR={['Elixir']=true,['Hi-Elixir']=true};
function E.smart_item_useful(name,target)
    if SMART_ITEM_AILMENTS[name] then
        if E.hasbuff(target,SMART_ITEM_AILMENTS[name])~=true then return false,'No applicable ailment'; end
    elseif SMART_ITEM_FOOD[name] then
        if E.hasbuff(target,'Food')~=false then return false,'Food active or status unknown'; end
    elseif name=='Yagudo Drink' or name=='Persikos au Lait' then
        local effect=(name=='Yagudo Drink') and 'Refresh' or 'Regen';
        if E.hasbuff(target,effect)~=false then return false,effect..' active or status unknown'; end
    elseif SMART_ITEM_HP[name] then
        if type(target.hpp)~='number' or target.hpp>=100 then return false,'HP full or unknown'; end
    elseif SMART_ITEM_MP[name] then
        if type(target.mpp)~='number' or target.mpp>=100 then return false,'MP full or unknown'; end
    elseif SMART_ITEM_ELIXIR[name] then
        if type(target.hpp)~='number' or type(target.mpp)~='number'
            or (target.hpp>=100 and target.mpp>=100) then return false,'HP and MP full or unknown'; end
    end
    return true;
end

function E.action_policy_check(ctx,rule,kind,name,res,target)
    local candidate=E.clone(rule);
    candidate.Type=kind; candidate.Action=name; candidate.Actions=nil;
    candidate.SelectedAction=name; candidate.SelectedKind=kind;
    if ctx.generatedRecruit and ctx.mainJob=='THF' and kind=='ability' and name=='Trick Attack' then
        local tankAvailable=false;
        for _,member in ipairs(ctx.party or {}) do
            if member.index and member.index<6 and member.id~=ctx.self.id and member.alive and member.zone==ctx.zone and
                E.contains({'PLD','NIN','WAR','RUN'},member.mainJob) then
                tankAvailable=true;
                break;
            end
        end
        if not tankAvailable then return false,'No eligible PLD, NIN, WAR or RUN tank'; end
    end
    if kind=='item' then
        local useful,why=E.smart_item_useful(name,target);
        if not useful then return false,why; end
    end
    if kind=='spell' and (name=='Cure' or name:match('^Cure [IVX]+$')
        or name=='Curaga' or name:match('^Curaga [IVX]+$')) then
        local missing=E.number(target and target.missingHP);
        if missing==nil then return false,'Recipient missing HP is unknown'; end
        if missing<=0 then return false,'Recipient is at full health'; end
    end
    if kind=='spell' and E.smart_spell_effect(name)=='Refresh' then
        local mpMax=E.number(target and target.mpMax);
        local mp=E.number(target and target.mp);
        if not mpMax or mpMax<=0 or mp==nil then return false,'Refresh recipient has no verified MP pool'; end
    end
    if kind=='spell' and (name=='Dispel' or name=='Magic Finale' or name=='Finale') and not ctx.generatedRecruit then
        local observed=target and target.dispellable;
        if observed==nil then observed=E.provider('EnemyDispellableBuff',ctx,candidate,target); end
        if observed~=true then
            return false,'No verified dispellable enemy enhancement';
        end
    end
    if kind=='spell' and rule.ActionPolicy~='Maintain Selected Effect' and rule.SmartActionLabel~='Maintain Selected Effect' then
        local effect=E.smart_spell_effect(name);
        if effect then
            local present=E.hasbuff(target,effect);
            -- Enemy status icons are not always exposed by the client. Keep
            -- existing debuff behavior when that target cannot be inspected.
            local serverCheckedRefresh=ctx.generatedRecruit and name=='Refresh' and present==nil
                and target and target.id~=ctx.self.id;
            if present==true or (present==nil and not serverCheckedRefresh) then
                return false,'Spell effect present or status unknown';
            end
        end
    end
    if type(rule.MissingBuffByAction)=='table' and rule.MissingBuffByAction[name]~=nil then
        local effect=rule.MissingBuffByAction[name];
        if E.hasbuff(target,effect)~=false then return false,'Action effect present or status unknown'; end
    end
    local removalTarget=E.contains({'ally_with_removable_ailment','removable_ailment_ally'},rule.Target);
    if rule.SmartStatusRemoval or removalTarget or (kind=='spell' and E.removal_statuses(name)~=nil) then
        local known=E.removal_statuses(name);
        local present=known and E.hasbuff(target,known);
        if known==nil then present=E.provider('RemovableAilment',ctx,candidate,target); end
        if present~=true then return false,'No verified ailment removable by '..tostring(name); end
    end
    local policy=rule.ActionPolicy or rule.SmartActionLabel;
    if rule.ActionPolicy and not E.contains({'Maintain Selected Effect','Cure Sufficient For Goal','Best Permitted Waltz','Preferred Samba',
        'Interrupt With Permitted Action','Open Skillchain','Close Skillchain','Magic Burst'},rule.ActionPolicy) then
        return false,'Unsupported action policy';
    end
    if policy=='Maintain Selected Effect' then
        if not rule.MaintainEffect then return false,'Choose which effect to maintain in Actions'; end
        if E.action_status_name(name)~=rule.MaintainEffect then return false,'Different maintained effect'; end
        local present=E.hasbuff(target,rule.MaintainEffect);
        if present==false then return true; end
        if present==nil then return false,'UNKNOWN: maintained status unavailable'; end
        local refresh=E.number(rule.MaintainRefreshSeconds,0) or 0;
        if refresh<=0 then return false,'Maintained effect is already present'; end
        local remaining=E.provider('StatusRemaining',ctx,{Property='status_remaining',TextValue=rule.MaintainEffect},target);
        if type(remaining)~='number' then return false,'UNKNOWN: maintained effect duration unavailable'; end
        if remaining>refresh then return false,'Maintained effect is not expiring'; end
        if E.provider('BuffRefreshAllowed',ctx,candidate,target,res)~=true then return false,'Effect refresh/overwrite is not verified'; end
        return true;
    end
    if E.contains({'Cure Sufficient For Goal','Best Permitted Waltz','Preferred Samba','Interrupt With Permitted Action',
        'Open Skillchain','Close Skillchain','Magic Burst'},policy) then
        -- A broad burst-window flag is not proof that THIS spell can burst or arrive in time.
        -- Supply candidate-specific mechanics through a provider; do not invent them in the client.
        candidate.ActionPolicy=policy;
        local approved=E.provider('SmartActionPolicy',ctx,candidate,target,res);
        if approved==nil then return false,'UNKNOWN: '..policy..' needs a SmartActionPolicy provider'; end
        if approved~=true then return false,policy..' policy rejected this candidate'; end
    end
    return true;
end

-- Conservative Cure estimates use Titan's Cure I-V spell minimums and level
-- milestones. Actual potency still belongs to the server and can change with
-- skill, MND, gear, weather or buffs. This selector is opt-in for Recruit defaults.
local CURE_ESTIMATES={
    Cure={{1,20},{10,30},{30,40},{50,45},{75,50}},
    ['Cure II']={{11,60},{30,90},{50,110},{75,120}},
    ['Cure III']={{21,130},{30,170},{50,230},{75,270}},
    ['Cure IV']={{41,270},{50,340},{75,470}},
    ['Cure V']={{61,450},{75,650}},
};
function E.cure_estimated_hp(name,level,job)
    local milestones=CURE_ESTIMATES[name];
    if not milestones then return nil; end
    local value=milestones[1][2];
    for i=2,#milestones do
        local low,high=milestones[i-1],milestones[i];
        if level<=high[1] then
            value=low[2]+(high[2]-low[2])*math.max(0,level-low[1])/(high[1]-low[1]);
            break;
        end
        value=high[2];
    end
    if job=='RDM' then value=value*0.9; end
    return math.floor(value);
end
function E.spell_mp_cost(ctx,res,rule)
    local supplied=E.provider('EffectiveSpellCost',ctx,res,rule);
    if type(supplied)=='number' and supplied>=0 then return supplied; end
    -- Manafont is a verified zero-cost exemption; other unverified modifiers
    -- remain subject to the server's final legality check.
    if E.hasbuff(ctx.self,{'Manafont',47})==true then return 0; end
    return E.number(res and res.ManaCost);
end
function E.spell_mp_policy(ctx,rule,res)
    local mp=E.number(ctx.self and ctx.self.mp);
    local cost=E.spell_mp_cost(ctx,res,rule);
    if not mp or not cost then return nil,'Recruit MP/cost unknown'; end
    local reserve=rule.Emergency and 0 or E.number(rule.MPReserve,ctx.settings and ctx.settings.MPReserve or 0);
    if mp<cost+(cost>0 and reserve or 0) then return false,'Insufficient MP after reserve'; end
    return true;
end
function E.rank_cure_actions(ctx,rule,target,actions)
    local missing=E.number(target and target.missingHP);
    local hpMax=E.number(target and target.hpMax);
    local hpPct=E.number(target and target.hpp);
    local currentMP=E.number(ctx and ctx.self and ctx.self.mp);
    if not missing or not hpMax or not hpPct or not currentMP or missing<=0 then return {}; end
    local goal=math.min(missing,math.max(1,math.ceil(hpMax*(E.number(rule.CureGoalHP,85)-hpPct)/100)));
    local reserve=rule.Emergency and 0 or E.number(rule.MPReserve,(ctx.settings and ctx.settings.MPReserve) or 0);
    local options={};
    for _,action in ipairs(actions or {}) do
        local cost=E.spell_mp_cost(ctx,action.resource,rule);
        local estimate=E.cure_estimated_hp(action.name,E.number(ctx.mainLevel,1),ctx.mainJob);
        if cost and estimate and currentMP>=cost+reserve then
            local healed=math.min(missing,estimate);
            options[#options+1]={action=action,cost=cost,healed=healed,sufficient=healed>=goal};
        end
    end
    table.sort(options,function(a,b)
        if a.sufficient~=b.sufficient then return a.sufficient; end
        if a.sufficient then
            if a.cost~=b.cost then return a.cost<b.cost; end
            return a.healed<b.healed;
        end
        if a.healed~=b.healed then return a.healed>b.healed; end
        return a.cost<b.cost;
    end);
    if not rule.Emergency and options[1] and not options[1].sufficient and options[1].healed<goal*0.35 then return {}; end
    local ranked={};
    for _,option in ipairs(options) do ranked[#ranked+1]=option.action; end
    return ranked;
end

function E.prepare_candidate(ctx,sourceRule,rule,kind,name,res,target)
    local maxRange=math.min(ctx.settings.TargetRange,E.range(ctx,kind,res,rule));
    if target.id~=ctx.self.id and (not E.number(target.distance) or target.distance>maxRange) then return nil,'Recipient out of action range'; end
    local effect=kind=='spell' and E.smart_spell_effect(name) or nil;
    local dispelAction=kind=='spell' and (name=='Dispel' or name=='Magic Finale' or name=='Finale');
    local needsStatus=rule.Status~=nil or rule.MissingBuff~=nil or rule.SmartStatusRemoval
        or rule.Property=='enemy_dispellable'
        or (rule.Condition2 and (rule.Condition2.Status~=nil or rule.Condition2.MissingBuff~=nil
            or rule.Condition2.Property=='enemy_dispellable'))
        or effect~=nil or dispelAction;
    local needsMpCapacity=kind=='spell' and (name=='Refresh' or name=='Refresh II' or name=='Refresh III')
        and E.number(target.mpMax)==nil;
    if (needsStatus or needsMpCapacity) and (target.buffs==nil
        or (dispelAction and target.dispellable==nil) or needsMpCapacity)
        and not ctx.generatedRecruit then
        E.apply_status_snapshot(ctx,target);
        needsMpCapacity=kind=='spell' and (name=='Refresh' or name=='Refresh II' or name=='Refresh III')
            and E.number(target.mpMax)==nil;
        if target.buffs==nil or (dispelAction and target.dispellable==nil) or needsMpCapacity then
            E.request_status_snapshot(ctx,target);
            return nil,'Waiting for verified target status';
        end
    end
    local selected=E.clone(rule); selected.SelectedAction=name; selected.SelectedKind=kind;
    local matches,why=E.condition(ctx,selected,target);
    if not matches then return nil,why; end
    local key=E.timerkey(ctx,rule,target,name);
    if S.uncertain[key] then return nil,'Previous action outcome unconfirmed; await observed result or zone reset'; end
    if ctx.now<(S.timers[key] or 0) then return nil,'Per-target attempt cooldown'; end
    if sourceRule.Type=='cure' and not sourceRule.CureEfficiency and sourceRule.SmartActionLabel~='Cure Sufficient For Goal' then
        -- Retain existing tier thresholds as policy hints, not potency guarantees.
        local minimum={['Cure V']=520,['Cure IV']=300,['Cure III']=130,['Cure II']=55,Cure=1};
        if (target.missingHP or 0)<(minimum[name] or 1) and not ((target.hpp or 100)<=25 and name=='Cure III') then
            return nil,'Lower cure tier is sufficient';
        end
    end
    matches,why=E.action_policy_check(ctx,rule,kind,name,res,target);
    if not matches then return nil,why; end
    local recast=E.recast_known_block(ctx,kind,res);
    if recast then return nil,recast; end
    local actionTarget=E.action_cast_target(ctx,kind,name,res,target);
    if not actionTarget then return nil,'Action recipient unavailable'; end
    if ctx.guestBridge then matches,why=E.guest_action_allowed(ctx,rule,kind,name,res,actionTarget);
    else matches,why=E.allowed_action(ctx,rule,kind,name,res,actionTarget); end
    if not matches then return nil,why; end
    local stealth=E.stealth_action_block(ctx,kind,actionTarget);
    if stealth then return nil,stealth; end
    local useBridge=(ctx.guestBridge and ctx.settings.TrustServerBridge~=false) or ctx.settings.UseServerBridge;
    local actor=ctx.actor or ctx.self;
    local requester=ctx.requester or ctx.self;
    local command,bridgeReason;
    if useBridge and (kind~='item' or ctx.generatedRecruit) then
        command,bridgeReason=E.bridge_command(ctx,{actorId=actor.id,kind=kind,resource=res,
            target=actionTarget,targetId=actionTarget.id,targetIndex=actionTarget.entityIndex});
    end
    if not command and not ctx.guestBridge and ctx.settings.FallbackVisibleCommands then
        local token=E.target_token(ctx,rule,actionTarget);
        local prefix=({spell='/ma',ability='/ja',pet='/pet',ws='/ws',item='/item'})[kind];
        if token and kind=='ranged' then command='/ra '..token;
        elseif token and prefix then command=prefix..' "'..name..'" '..token;
        elseif token and kind=='attack' then command='/attack '..token; end
    end
    if not command then return nil,bridgeReason or 'Invalid or unavailable target token'; end
    local cast=kind=='spell' and E.number(res.CastTime,4)*0.25 or (kind=='item' and 3 or 0);
    return {rule=E.clone(rule),sourceRuleText=E.serialize(sourceRule),kind=kind,name=name,resource=res,
        target=actionTarget,conditionTarget=target,conditionTargetId=target.id,conditionTargetIndex=target.entityIndex,
        command=command,targetId=actionTarget.id,targetIndex=actionTarget.entityIndex,key=key,time=ctx.now,cast=cast,
        actorId=actor.id,actorIndex=actor.entityIndex,playerId=requester.id,zone=ctx.zone};
end

function E.prepare(ctx,rule)
    if rule.Empty==true then return nil,'Empty slot'; end
    if rule.Enabled==false then return nil,'Disabled'; end
    if ctx.now<(S.timers[E.rule_timerkey(ctx,rule)] or 0) then return nil,'Rule cooldown'; end
    local rejected={};
    local function remember(target,action,why)
        if ctx.guestBridge or #rejected>=16 then return; end
        rejected[#rejected+1]={target=(target and target.name) or tostring(target and target.id or 'Unknown'),
            action=action,reason=why or 'Action unavailable'};
    end
    local function save_preview(selected)
        if not ctx.guestBridge then
            S.candidateWhy=S.candidateWhy or {};
            S.candidateWhy[rule.Id]={at=ctx.now,rejected=rejected,
                selected=selected and {target=selected.target and selected.target.name or tostring(selected.targetId),
                    action=selected.name} or nil};
        end
        return selected;
    end
    local kind=rule.Type;
    local names;
    local effective=rule;
    if kind=='none' then
        for _,target in ipairs(E.candidates(ctx,rule,ctx.settings.TargetRange)) do
            if E.condition(ctx,rule,target) then return {hold=true,rule=rule}; end
        end
        return nil,'Hold condition not met';
    elseif kind=='attack' then names={'Attack'};
    elseif kind=='ws_auto' then
        effective=E.clone(rule); effective.Type='ws';
        if ctx.guestBridge or ctx.catalogActorKind=='guest' then
            names=E.guest_ws_names(ctx); effective.Family=nil;
            if ctx.generatedRecruit then
                -- Best Weapon Skill is a melee finisher. Do not spend TP on a
                -- lower-tier long-range skill while a better skill is waiting
                -- for the recruit to close with its target.
                effective.Range=math.min(E.number(rule.Range) or 3.5,3.5);
            end
            if not names or #names==0 then return nil,'No permitted Trust weapon skills available'; end
        else
            local weapon=rule.Ranged and ctx.ranged or ctx.weapon;
            if not weapon or not WS[weapon.skill] then return nil,'Unsupported or unequipped weapon'; end
            effective.Family=weapon.skill;
            names=(S.profile.WeaponSkills or {})[weapon.skill] or WS[weapon.skill];
        end
        kind='ws';
    elseif kind=='cure' then kind='spell'; names=rule.Actions or {'Cure V','Cure IV','Cure III','Cure II','Cure'};
    elseif kind=='ranged' then names={'Ranged Attack'};
    else names=rule.Actions or {rule.Action}; end
    local actions={};
    local lastReason='No actions configured';
    for _,name in ipairs(names) do
        if E.safe_name(name) then
            local res=(kind=='ranged' or kind=='attack') and {} or E.resource(ctx,kind,name);
            if res then
                local range=math.min(ctx.settings.TargetRange,E.range(ctx,kind,res,effective));
                actions[#actions+1]={name=name,resource=res,range=range};
            else lastReason='Resource not found: '..name; end
        else lastReason='Invalid action name'; end
    end
    if #actions==0 then return nil,lastReason; end
    local pools={};
    local function pool(range)
        if pools[range]==nil then pools[range]=E.candidates(ctx,effective,range); end
        return pools[range];
    end
    -- Status-removal policies explicitly prioritize the configured removal-action order.
    -- Every other selector ranks the recipient first, then chooses its usable action/tier.
    if rule.SmartStatusRemoval then
        for _,action in ipairs(actions) do
            for _,target in ipairs(pool(action.range)) do
                local plan,why=E.prepare_candidate(ctx,rule,effective,kind,action.name,action.resource,target);
                if plan then return save_preview(plan); end
                remember(target,action.name,why);
                lastReason=why or lastReason;
            end
        end
    else
        local targets=pool(ctx.settings.TargetRange);
        if #targets==0 then save_preview(nil); return nil,'No eligible target; selector may require a provider'; end
        for _,target in ipairs(targets) do
            local targetActions=(rule.Type=='cure' and rule.CureEfficiency)
                and E.rank_cure_actions(ctx,rule,target,actions) or actions;
            for _,action in ipairs(targetActions) do
                -- Re-resolve with this action's actual range. Custom target providers also
                -- must return this candidate at the narrower range before it can be selected.
                local inActionSet=false;
                for _,eligible in ipairs(pool(action.range)) do
                    if eligible.id==target.id and eligible.entityIndex==target.entityIndex then inActionSet=true; break; end
                end
                if inActionSet then
                    local plan,why=E.prepare_candidate(ctx,rule,effective,kind,action.name,action.resource,target);
                    if plan then return save_preview(plan); end
                    remember(target,action.name,why);
                    lastReason=why or lastReason;
                end
            end
        end
    end
    save_preview(nil);
    return nil,lastReason;
end
function E.resource_time_seconds(res,field,default)
    if field~='CastTime' and field~='RecastDelay' then return default; end
    local ok,value=pcall(function() return res and res[field] end);
    if not ok then E.log('SDK spell field unavailable: '..field); return default; end
    value=E.number(value);
    if value==nil then return default; end
    return value*0.25; -- Installed ISpell annotations use quarter-second units.
end
function E.plan_attempt_delay(plan)
    local delay=math.max(1,plan.rule.PerTargetCooldown or plan.rule.Cooldown or 2);
    if plan.kind=='spell' and plan.resource and E.self_centered_party_spell(plan.name) then
        local cast=E.resource_time_seconds(plan.resource,'CastTime',0);
        delay=math.max(delay,cast+3);
    end
    -- RecastDelay is the unmodified base recast. Live timer data, when known,
    -- gates readiness separately; adding the base here would double the wait.
    return math.min(300,delay);
end
function E.mark_attempt(ctx,plan)
    S.timers[E.rule_timerkey(ctx,plan.rule)]=ctx.now+math.max(1,plan.rule.Cooldown or 2);
    S.timers[plan.key]=ctx.now+(plan.attemptDelay or E.plan_attempt_delay(plan));
    S.lastDecision=plan.rule.Id .. ': ' .. plan.name .. ' -> ' .. (plan.target.name or tostring(plan.target.id));
end
function E.mark_recruit_dia_observed(plan,now)
    if not plan.generatedRecruit or plan.kind~='spell' or (plan.name~='Dia II' and plan.name~='Dia') then return; end
    local duration=plan.name=='Dia II' and 120 or 60;
    S.timers[plan.key]=math.max(S.timers[plan.key] or 0,now+duration-5);
end

function E.preflight_plan(live,plan)
    if not live or not live.self or live.self.id~=plan.playerId or live.zone~=plan.zone then return nil,'Requester/zone changed'; end
    local block=E.gate(live,false,true);
    if block then return nil,block; end
    local ctx=live;
    if plan.actorId~=plan.playerId then
        local actor;
        for _,m in ipairs(live.party or {}) do if m.id==plan.actorId then actor=m; break; end end
        if not actor or not E.is_controllable_guest_member(live,actor) then return nil,'Trust no longer controllable'; end
        if not E.actor_enabled(live,actor) then return nil,'Trust Gambits are OFF'; end
        if plan.actorIndex and actor.entityIndex~=plan.actorIndex then return nil,'Trust entity changed'; end
        if E.is_generated_recruit(actor) and S.controlState['guest-control:'..tostring(actor.id)]~=true then
            return nil,'Recruit action control has no server receipt yet';
        end
        ctx=E.actor_context(live,actor);
        if not ctx or (ctx.status~=0 and ctx.status~=1) then return nil,'Trust action state changed'; end
    else
        if not E.actor_enabled(live,live.self) then return nil,'Player Gambits are OFF'; end
        E.sample_motion(live);
        if live.moving or (live.stationarySeconds or 0)<live.settings.StationaryDelaySeconds then return nil,'Player moved'; end
        if live.now<S.manualUntil then return nil,'Manual action in progress'; end
    end
    if E.hasbuff(ctx.self,{2,7,10,14,17,19,28,'Sleep','Petrification','Stun','Charm','Terror'})==true then return nil,'Actor incapacitated'; end
    if E.call(ctx.entityMemory,'GetServerId',plan.actorIndex or ctx.self.entityIndex)~=plan.actorId then return nil,'Actor identity changed'; end
    if E.call(ctx.entityMemory,'GetServerId',plan.targetIndex)~=plan.targetId then return nil,'Target identity changed'; end
    if plan.sourceRuleText then
        local profile=plan.actorId==plan.playerId and S.profile or E.guest_profile_load(live,ctx.self,false);
        local active=false;
        if profile and profile.Enabled~=false then
            ctx.activeRules=profile.Rules;
            for _,rule in ipairs(profile.Rules or {}) do
                if rule.Id==plan.rule.Id and rule.Enabled~=false and E.serialize(rule)==plan.sourceRuleText then active=true; break; end
            end
        end
        if not active then return nil,'Rule/profile changed after selection'; end
    end
    local range=math.min(ctx.settings.TargetRange,E.range(ctx,plan.kind,plan.resource,plan.rule));
    local current;
    for _,target in ipairs(E.candidates(ctx,plan.rule,range)) do
        if target.id==(plan.conditionTargetId or plan.targetId)
            and (not plan.conditionTargetIndex or target.entityIndex==plan.conditionTargetIndex) then current=target; break; end
    end
    if not current then return nil,'Condition target no longer eligible'; end
    if current.id~=ctx.self.id and (not E.number(current.distance) or current.distance>range) then return nil,'Recipient moved out of action range'; end
    local actionTarget=E.action_cast_target(ctx,plan.kind,plan.name,plan.resource,current);
    if not actionTarget or actionTarget.id~=plan.targetId then return nil,'Action recipient changed'; end
    local queuedPartyToken=plan.command and plan.command:match('(<p%d+>)$');
    if queuedPartyToken and E.target_token(ctx,plan.rule,actionTarget)~=queuedPartyToken then
        return nil,'Party slot changed before action dispatch';
    end
    local selected=E.clone(plan.rule); selected.SelectedAction=plan.name; selected.SelectedKind=plan.kind;
    local ok,why=E.condition(ctx,selected,current);
    if not ok then return nil,why; end
    if E.action_policy_check then
        ok,why=E.action_policy_check(ctx,plan.rule,plan.kind,plan.name,plan.resource,current);
        if not ok then return nil,why; end
    end
    if ctx.guestBridge then ok,why=E.guest_action_allowed(ctx,plan.rule,plan.kind,plan.name,plan.resource,actionTarget);
    else ok,why=E.allowed_action(ctx,plan.rule,plan.kind,plan.name,plan.resource,actionTarget); end
    if not ok then return nil,why; end
    local stealth=E.stealth_action_block(ctx,plan.kind,actionTarget);
    if stealth then return nil,stealth; end
    plan.target=actionTarget;
    return ctx;
end

function E.issue(ctx,plan)
    if plan.kind=='item' and plan.actorId==plan.playerId then return false; end
    if plan.hold then return true; end
    if E.actor_busy(ctx) then return false; end
    local live=E.context('pre-queue');
    local valid,why=E.preflight_plan(live,plan);
    if not valid then E.log('Preflight rejected: '..tostring(why)); return false; end
    if plan.kind=='item' and plan.actorId==plan.playerId then
        local location=E.player_item_location(valid,plan.name);
        if not location then return false; end
        local transfer=S.itemTransfer;
        if transfer and transfer.playerId==plan.playerId and transfer.zone==plan.zone then
            local arrived=E.player_item_location(valid,transfer.name);
            if arrived and arrived.bag==0 then S.itemTransfer=nil;
            elseif valid.now<transfer.deadline then return false;
            else
                S.itemTransfer=nil;
                S.timers[transfer.key]=valid.now+5;
                E.log('Item transfer was not confirmed: '..transfer.name);
                return false;
            end
        end
        if location.bag~=0 and location.bag~=3 then
            if not E.free_inventory_slot(valid) then return false; end
            -- LSB only accepts item-use from inventory or temporary items. Move
            -- one owned consumable by the ordinary validated 0x029 item packet,
            -- then let a later tick revalidate and issue the normal /item command.
            local packet={0x29,0x06,0,0,1,0,0,0,location.bag,0,location.slot,0xFF};
            local manager=E.call(AshitaCore,'GetPacketManager');
            if not manager then return false; end
            local moved=pcall(function() manager:AddOutgoingPacket(0x029,packet); end);
            if not moved then return false; end
            S.itemTransfer={playerId=plan.playerId,zone=plan.zone,id=location.id,name=plan.name,key=plan.key,deadline=valid.now+3};
            E.set_actor_lock(valid,valid.now+0.5);
            return true;
        end
    end
    local timed,attemptDelay=pcall(E.plan_attempt_delay,plan);
    if not timed then E.log('Attempt timing rejected before queue: '..tostring(attemptDelay)); return false; end
    plan.attemptDelay=attemptDelay;
    plan.actorIndex=valid.self.entityIndex;
    plan.deadline=valid.now+math.max((plan.kind=='pet' or plan.kind=='ranged') and 8 or 4,(plan.cast or 0)+4);
    plan.generatedRecruit=valid.generatedRecruit==true;
    if plan.generatedRecruit and (plan.kind=='ability' or plan.kind=='ws' or plan.kind=='item') then
        -- Instant recruit actions can lack a matching client completion packet.
        -- Keep their queue slot briefly; server recast and rule timers still gate retries.
        plan.deadline=valid.now+math.max(4,(plan.cast or 0)+4);
    end
    plan.petId=ctx.pet and ctx.pet.id;
    plan.waitForPet=plan.kind=='pet' and (plan.resource.RecastTimerId==173 or plan.resource.RecastTimerId==174);
    plan.serverBridge=plan.command:match('^/say !gambit act ')~=nil or plan.command:match('^!gambit act ')~=nil;
    if plan.serverBridge then
        plan.requestNonce=math.random(1,999999999);
        plan.requestKind,plan.requestActionId=plan.command:match('!gambit act %d+ (%w+) (%d+)');
        plan.requestActionId=tonumber(plan.requestActionId);
        plan.command=plan.command..' '..plan.requestNonce;
        plan.delivery='submitted';
    end
    local ok,err;
    if plan.kind~='attack' then E.register_pending(plan); end
    if plan.serverBridge then
        ok,err=E.send_bridge_command(plan.command,false,{origin='submit_plan',actorId=plan.actorId,actorIndex=plan.actorIndex,targetId=plan.targetId,targetIndex=plan.targetIndex});
        -- ParseCommand returning without an exception only proves invocation.
        -- The matching outgoing speech packet marks this request observed.
        plan.submitted=ok;
    else
        local chat=E.call(AshitaCore,'GetChatManager');
        if not chat then E.clear_pending(plan); E.log('Chat manager unavailable'); return false; end
        S.outgoingIntent=plan;
        -- FFXI Offline: a command for a squad mate/Trust ends in <t>; target that mate first, then put the old target back
        local trustIndex=E.number(plan.targetIndex);
        if plan.command:sub(-3)=='<t>' and trustIndex and trustIndex>=0x700 and not (plan.target and plan.target.isMonster) then
            local tm=E.call(E.call(AshitaCore,'GetMemoryManager'),'GetTarget');
            local before=tm and E.number(E.call(tm,'GetTargetIndex',0)) or 0;
            if tm then pcall(function() tm:SetTarget(trustIndex,true); end); end
            if tm and before and before>0 and before~=trustIndex and ashita and ashita.tasks and ashita.tasks.once then
                ashita.tasks.once(1.5,function()
                    if E.number(E.call(tm,'GetTargetIndex',0))==trustIndex then pcall(function() tm:SetTarget(before,true); end); end
                end);
            end
        end
        ok,err=pcall(function() chat:QueueCommand(1,plan.command); end);
    end
    if not ok then E.clear_pending(plan); E.log('Queue failed: '..tostring(err)); return false; end
    S.actionStats.submitted=S.actionStats.submitted+1;
    E.mark_attempt(valid,plan);
    -- xi_map already throttles each actor to one request per 500 ms.
    E.set_actor_lock(valid,valid.now+(valid.generatedRecruit and 0.55 or valid.settings.ActionLockSeconds));
    E.log('ATTEMPT: '..S.lastDecision..' [actor '..tostring(plan.actorId)..']');
    return true;
end
function E.action_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local at=text:find('TGAX|',1,true);
    if not at then return false; end
    local nonce,actor,kind,actionId,target,state,reason=text:sub(at):match('^TGAX|(%d+)|(%d+)|([%w_]+)|(%d+)|(%d+)|([AR])|([%w_]+)');
    local p=actor and E.pending_for(tonumber(actor));
    if not p then
        for key,uncertain in pairs(S.uncertain) do
            if uncertain.nonce==tonumber(nonce) and uncertain.actorId==tonumber(actor)
                and uncertain.targetId==tonumber(target) and uncertain.requestKind==kind
                and uncertain.requestActionId==tonumber(actionId) and state=='R' then
                S.uncertain[key]=nil;
                S.timers[key]=E.now()+2;
                E.bridge_trace('late_server_rejection','',{origin='action_response',actorId=actor,targetId=target});
                return true;
            end
        end
    end
    if not p or p.requestNonce~=tonumber(nonce) or p.targetId~=tonumber(target)
        or p.requestKind~=kind or p.requestActionId~=tonumber(actionId) then
        E.bridge_trace('stale_action_receipt','',{origin='action_response',actorId=actor,targetId=target});
        return true;
    end
    local ctx=E.context('action-receipt');
    if not ctx or not ctx.self or ctx.self.id~=p.playerId or ctx.zone~=p.zone
        or E.call(ctx.entityMemory,'GetServerId',p.actorIndex)~=p.actorId
        or E.call(ctx.entityMemory,'GetServerId',p.targetIndex)~=p.targetId then
        E.release('Action receipt had stale identity',false,p.actorId);
        return true;
    end
    S.actionStats[state=='A' and 'accepted' or 'rejected']=S.actionStats[state=='A' and 'accepted' or 'rejected']+1;
    p.delivery=state=='A' and 'accepted' or 'rejected';
    p.sent=true; -- A server receipt proves delivery even if the speech callback was missed.
    p.serverReason=reason;
    E.bridge_trace(state=='A' and 'server_action_accepted' or 'server_action_rejected',p.command,
        {origin='action_response',actorId=p.actorId,actorIndex=p.actorIndex,targetId=p.targetId,targetIndex=p.targetIndex});
    if state=='R' then E.release('Server rejected action: '..reason,true,p.actorId,reason); end
    return true;
end
function E.status_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local at=text:find('TGST|',1,true);
    if not at then return false; end
    local nonce,targetId,zone,flag,mpMax,payload=text:sub(at):match('^TGST|(%d+)|(%d+)|(%d+)|([01!])|(%d+)|([%d,!%-]+)');
    local request=S.statusRequest;
    if not nonce or not request or tonumber(nonce)~=request.nonce
        or tonumber(targetId)~=request.targetId then return true; end
    S.statusRequest=nil;
    local ctx=E.context('status-receipt');
    if not ctx or not ctx.self or ctx.self.id~=request.ownerId or ctx.zone~=request.zone
        or tonumber(zone)~=request.zone or flag=='!' or payload=='!' then return true; end
    if E.call(ctx.entityMemory,'GetServerId',request.targetIndex)~=request.targetId then return true; end
    local ids={};
    if payload~='-' then
        if not payload:match('^%d+[,%d]*$') then return true; end
        for number in payload:gmatch('%d+') do
            local id=tonumber(number);
            if not id or id>=1023 or #ids>=32 then return true; end
            ids[#ids+1]=id;
        end
    end
    local maximum=tonumber(mpMax);
    if not maximum or maximum>99999 then return true; end
    S.statusSnapshots[request.targetId]={zone=request.zone,entityIndex=request.targetIndex,
        receivedAt=E.now(),ids=ids,dispellable=flag=='1',mpMax=maximum};
    return true;
end
function E.control_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[].','');
    local at=text:find('TGRA|',1,true);
    if not at then return false; end
    local actor,nonce,accepted=text:sub(at):match('^TGRA|(%d+)|(%d+)|([01])');
    local key=actor and 'guest-control:'..actor;
    local pending=key and S.controlPending[key];
    if pending and pending.nonce==tonumber(nonce) then
        local ctx=E.context('control-receipt');
        local current;
        for _,member in ipairs((ctx and ctx.party) or {}) do
            if member.id==pending.record.id then current=member; break; end
        end
        if not ctx or not ctx.self or ctx.zone~=pending.record.zone or ctx.self.id~=pending.record.playerId
            or not current or current.name~=pending.record.name or current.entityIndex~=pending.record.entityIndex then
            E.bridge_trace('stale_receipt',pending.command,pending.meta);
            S.controlPending[key]=nil;
            return true;
        end
        E.bridge_trace(accepted=='1' and 'server_accepted' or 'server_rejected',pending.command,pending.meta);
        if accepted=='1' then
            S.controlState[key]=pending.enabled;
            S.control[key]=E.now()+20;
            S.controlActors[key]=pending.record;
        else S.control[key]=E.now()+3; end
        S.controlPending[key]=nil;
    end
    return true;
end
function E.submit_guest_control(ctx,actor,enabled,background)
    local key='guest-control:'..tostring(actor.id);
    local now=ctx.now or E.now();
    local pending=S.controlPending[key];
    if pending and now-pending.at<4 then return false; end
    if pending then E.bridge_trace('receipt_timeout',pending.command,pending.meta); S.controlPending[key]=nil; end
    local command=E.bridge_control_command(actor,enabled);
    if not command then return false; end
    local nonce=math.random(1,999999);
    command=command..' '..nonce;
    local meta={origin='refresh_guest_control',actorId=actor.id,actorIndex=actor.entityIndex};
    if not E.send_bridge_command(command,background,meta) then return false; end
    S.controlPending[key]={nonce=nonce,enabled=enabled,at=now,command=command,meta=meta,
        record={id=actor.id,entityIndex=actor.entityIndex,zone=ctx.zone,playerId=ctx.self.id,name=actor.name}};
    return true;
end
function E.refresh_guest_control(ctx)
    if not ctx or not ctx.settings or not ctx.self or not ctx.party then return false; end
    local enabled=ctx.settings.TrustServerBridge~=false and E.trust_control_allowed(ctx)==true
        and E.gate(ctx,false,true)==nil;
    local now=ctx.now or E.now();
    local sent=false;
    local present={};
    for _,actor in ipairs(ctx.party) do
        if E.is_generated_recruit(actor) and actor.id then
            local key='guest-control:'..tostring(actor.id);
            S.controlActors[key]=nil; S.controlState[key]=nil;
            S.controlPending[key]=nil; S.control[key]=nil;
        elseif E.is_controllable_guest_member(ctx,actor) then
            local key='guest-control:'..tostring(actor.id);
            present[key]=true;
            local old=S.controlActors[key];
            if old and (old.name~=actor.name or old.entityIndex~=actor.entityIndex or old.zone~=ctx.zone) then
                S.controlActors[key]=nil; S.controlState[key]=nil; S.controlPending[key]=nil; S.control[key]=nil;
            end
            local desired=enabled and E.actor_enabled(ctx,actor) and E.guest_actor_has_enabled_gambits(ctx,actor)==true or false;
            if now>=(S.control[key] or 0) or S.controlState[key]~=desired then
                if E.submit_guest_control(ctx,actor,desired,true) then sent=true; end
            end
        end
    end
    for key,record in pairs(S.controlActors) do
        if not present[key] and S.controlState[key]==true and record.zone==ctx.zone and record.playerId==ctx.self.id
            and E.call(ctx.entityMemory,'GetServerId',record.entityIndex)==record.id then
            if E.submit_guest_control(ctx,record,false,true) then sent=true; end
        end
    end
    return sent;
end
function E.release(reason,failed,actorId,serverReason)
    local plan=E.pending_for(actorId);
    if not plan then return; end
    local now=E.now();
    if failed then
        -- Server refusal is scoped to this action/target. A missing effect,
        -- recast or transient busy actor must not disable the other actions
        -- and targets in the row. Live recast snapshots provide the longer gate.
        local retry=3;
        if serverReason=='throttled' or serverReason=='recruit_item_busy' then retry=0.75;
        elseif serverReason=='interrupted' then retry=1.5;
        elseif serverReason=='medicated' or serverReason=='message_111' then retry=10;
        elseif serverReason=='observed_result' then retry=4;
        elseif serverReason and (serverReason:find('already_present',1,true)
            or serverReason:find('effect_present',1,true)) then retry=5;
        elseif serverReason then retry=2; end
        S.timers[plan.key]=now+retry;
        local rowKey=E.rule_timerkey({zone=plan.zone,actor={id=plan.actorId}},plan.rule);
        S.timers[rowKey]=math.min(S.timers[rowKey] or now,now);
        S.failures[plan.key]={count=1,time=now,reason=serverReason or 'observed_failure'};
    else S.failures[plan.key]=nil; end
    E.clear_pending(plan);
    local ctx={zone=plan.zone,actor={id=plan.actorId},guestBridge=plan.actorId~=plan.playerId};
    local recovery=(plan.generatedRecruit and not failed) and 0.15 or (S.settings or DEFAULT).ActionLockSeconds;
    E.set_actor_lock(ctx,now+recovery);
    E.log(tostring(reason)..': '..tostring(plan.name)..' [actor '..tostring(plan.actorId)..']');
end

-- Default profiles. Array order is persisted and can be edited/dragged in game.
-- The presets are level-agnostic. Action ladders are strongest/preferred first and E.prepare
-- skips anything that is unlearned, above the effective main/sub level, on recast, unaffordable,
-- incompatible with the current pet/weapon, or otherwise unsafe. The same profile therefore
-- remains valid from level 1 through the configured level cap without per-level variants.
G.Definitions={};
function E.rule(list,id,layer,kind,action,target,options)
    local r={Id=id,Label=id,Layer=layer,Type=kind,Action=action,Target=target or 'self',
        Enabled=true,Cooldown=2,PerTargetCooldown=3,Combat='any'};
    for k,v in pairs(options or {}) do r[k]=E.clone(v); end
    if type(action)=='table' then r.Action=nil; r.Actions=E.clone(action); end
    list[#list+1]=r; return r;
end
function E.common_rules(job)
    local a={}; local r=E.rule;
    r(a,'emergency-cursna','emergency_survival','spell','Cursna','status',
        {Status={'Doom',15},Emergency=true,Cooldown=3,PerTargetCooldown=4});
    r(a,'raise','raise','spell',{'Raise III','Raise II','Raise'},'dead',
        {SelfMPAbove=30,Cooldown=5,PerTargetCooldown=45,Label='Best learned Raise tier'});
    r(a,'emergency-cure','emergency_healing','cure',nil,'lowest',
        {TargetHPBelow=45,Emergency=true,Cooldown=2,PerTargetCooldown=2,
         Label='Dynamic Cure tier based on learned spells and missing HP'});
    for _,entry in ipairs({
        {'petrification','Stona',{'Petrification',7}},
        {'silence','Silena',{'Silence',6}},
        {'paralysis','Paralyna',{'Paralysis',4}},
        {'curse','Cursna',{'Curse',9}},
        {'disease','Viruna',{'Disease','Plague',8,31}},
        {'poison','Poisona',{'Poison',3}},
        {'blindness','Blindna',{'Blindness',5}},
    }) do
        r(a,'remove-'..entry[1],'status_removal','spell',entry[2],'status',
            {Status=entry[3],Cooldown=2,PerTargetCooldown=5});
    end
    r(a,'erase','status_removal','spell','Erase','status',
        {Status={'Slow','Elegy','Bind','Weight','Burn','Frost','Choke','Rasp','Shock','Drown'},Cooldown=3,PerTargetCooldown=6});
    r(a,'maintenance-cure','emergency_healing','cure',nil,'lowest',
        {TargetHPBelow=70,MinMissingHP=40,SelfMPAbove=25,Cooldown=3,PerTargetCooldown=3,
         Label='Dynamic maintenance Cure tier'});
    r(a,'weapon-skill','weapon_skill','ws_auto',nil,'enemy',
        {TP=1000,Combat='combat',Cooldown=3,PerTargetCooldown=3,
         Label='Best available WS for the currently equipped melee weapon'});
    r(a,'ranged-weapon-skill','weapon_skill','ws_auto',nil,'enemy',
        {TP=1000,Combat='combat',Ranged=true,Enabled=job=='RNG' or job=='COR',Cooldown=3,
         Label='Best available WS for the currently equipped ranged weapon'});
    r(a,'protect-self','buff_maintenance','spell',{'Protect V','Protect IV','Protect III','Protect II','Protect'},'self',
        {MissingBuff={'Protect',40},SelfMPAbove=35,Combat='any',PerTargetCooldown=30,
         Label='Best learned Protect tier'});
    r(a,'shell-self','buff_maintenance','spell',{'Shell V','Shell IV','Shell III','Shell II','Shell'},'self',
        {MissingBuff={'Shell',41},SelfMPAbove=35,Combat='any',PerTargetCooldown=30,
         Label='Best learned Shell tier'});
    r(a,'refresh-self','buff_maintenance','spell','Refresh','self',
        {MissingBuff={'Refresh',43},SelfMPAbove=15,TargetMPBelow=85,Combat='any',PerTargetCooldown=12});
    r(a,'reraise-self','buff_maintenance','spell',{'Reraise III','Reraise II','Reraise'},'self',
        {MissingBuff={'Reraise',113},SelfMPAbove=55,Combat='any',PerTargetCooldown=30,
         Label='Best learned Reraise tier'});
    r(a,'utsusemi','buff_maintenance','spell',{'Utsusemi: Ni','Utsusemi: Ichi'},'self',
        {MissingBuff='Copy Image*',Combat='any',PerTargetCooldown=8,
         Label='Best learned Utsusemi tier'});
    r(a,'blink','buff_maintenance','spell','Blink','self',
        {MissingBuff={'Blink',36},ForbidBuff='Copy Image*',Combat='any',SelfMPAbove=65,PerTargetCooldown=15,
         Enabled=job=='WHM' or job=='RDM' or job=='BLM'});
    r(a,'stoneskin','buff_maintenance','spell','Stoneskin','self',
        {MissingBuff={'Stoneskin',37},Combat='any',SelfMPAbove=60,PerTargetCooldown=15,
         Enabled=job=='WHM' or job=='RDM' or job=='BLM'});
    r(a,'aquaveil','buff_maintenance','spell','Aquaveil','self',
        {MissingBuff='Aquaveil',Combat='any',SelfMPAbove=60,PerTargetCooldown=20,
         Enabled=job=='WHM' or job=='RDM' or job=='BLM'});
    -- Subjob-capable helpers. No hard-coded level gate: HasAbility/HasSpell plus the live
    -- main/sub level decides whether each action exists on this character right now.
    r(a,'sub-chakra','emergency_survival','ability','Chakra','self',
        {Job='MNK',SelfHPBelow=65,Cooldown=5});
    r(a,'sub-meditate','critical_job_mechanics','ability','Meditate','self',
        {Job='SAM',SelfTPBelow=900,Combat='combat',Cooldown=8});
    r(a,'sub-hasso','buff_maintenance','ability','Hasso','self',
        {Job='SAM',TwoHanded=true,ForbidBuff='Seigan',MissingBuff='Hasso',Combat='combat',
         Enabled=job~='SAM',Cooldown=8});
    r(a,'sub-third-eye','emergency_survival','ability','Third Eye','self',
        {Job='SAM',TwoHanded=true,SelfHPBelow=70,MissingBuff='Third Eye',Combat='combat',
         Enabled=job~='SAM',Cooldown=8});
    r(a,'sub-berserk','buff_maintenance','ability','Berserk','self',
        {Job='WAR',SelfHPAbove=70,ForbidBuff='Defender',MissingBuff='Berserk',Combat='combat',
         Enabled=not E.contains({'PLD','WHM','BLM','SMN','BRD'},job),Cooldown=8});
    r(a,'echo-drops','emergency_survival','item','Echo Drops','self',
        {Status={'Silence',6},Enabled=false,Consumable=true,Cooldown=8,Label='Optional consumable: Echo Drops'});
    r(a,'holy-water','emergency_survival','item','Holy Water','self',
        {Status={'Doom',15},Enabled=false,Consumable=true,Cooldown=4,Label='Optional consumable: Holy Water'});
    r(a,'ether','utility','item','Ether','self',
        {SelfMPBelow=15,Enabled=false,Consumable=true,Cooldown=30});
    return a;
end
function E.buff(a,id,name,buff,options)
    local o={MissingBuff=buff or name,Combat='combat',Cooldown=5,PerTargetCooldown=10};
    for k,v in pairs(options or {}) do o[k]=v; end
    return E.rule(a,id,'buff_maintenance','ability',name,'self',o);
end
function E.spellbuff(a,id,name,buff,target,options)
    local o={MissingBuff=buff,Combat='any',SelfMPAbove=40,PerTargetCooldown=15};
    for k,v in pairs(options or {}) do o[k]=v; end
    return E.rule(a,id,'buff_maintenance','spell',name,target or 'self',o);
end
function E.debuff(a,id,name,options)
    local o={Combat='combat',SelfMPAbove=30,Cooldown=5,PerTargetCooldown=45};
    for k,v in pairs(options or {}) do o[k]=v; end
    return E.rule(a,id,'debuffs','spell',name,'enemy',o);
end
function E.interrupt(a,id,kind,name,options)
    local o={Mechanic='interrupt',Combat='combat',Cooldown=3,PerTargetCooldown=3};
    for k,v in pairs(options or {}) do o[k]=v; end
    return E.rule(a,id,'critical_job_mechanics',kind,name,'enemy',o);
end
function E.special(a,name,options)
    local o={Special=true,Enabled=false,Combat='combat',Cooldown=30,SelfHPBelow=20};
    for k,v in pairs(options or {}) do o[k]=v; end
    return E.rule(a,'special-'..E.lower(name):gsub('[^%w]+','-'),'emergency_survival','ability',name,'self',o);
end

function G.Definitions.WAR(a)
    E.rule(a,'defender-emergency','emergency_survival','ability','Defender','self',
        {SelfHPBelow=35,Combat='combat',MissingBuff='Defender',ForbidBuff='Berserk',Cooldown=8});
    E.buff(a,'aggressor','Aggressor','Aggressor',{SelfHPAbove=60});
    E.buff(a,'warcry','Warcry','Warcry',{SelfHPAbove=60});
    E.rule(a,'provoke','critical_job_mechanics','ability','Provoke','enemy',
        {Enabled=false,Combat='combat',Range=15,Cooldown=30,Label='Optional tank Provoke'});
    E.rule(a,'tomahawk','job_specific_actions','ability','Tomahawk','enemy',
        {Enabled=false,Consumable=true,RequiredItem='Thr. Tomahawk',Combat='combat',Range=15,Cooldown=10,MainOnly=true,Job='WAR'});
    E.buff(a,'warriors-charge',"Warrior's Charge", "Warrior's Charge",{MainOnly=true,Job='WAR',SelfTPAbove=1000});
    E.special(a,'Mighty Strikes');
end
function G.Definitions.MNK(a)
    E.buff(a,'dodge','Dodge','Dodge',{SelfHPBelow=60});
    E.buff(a,'focus','Focus','Focus');
    E.buff(a,'boost','Boost','Boost',{SelfTPAbove=1000,Cooldown=15});
    E.buff(a,'counterstance','Counterstance','Counterstance',{Enabled=false,SelfHPAbove=80});
    E.rule(a,'chi-blast','job_specific_actions','ability','Chi Blast','enemy',
        {Combat='combat',Range=15,Cooldown=10});
    E.rule(a,'mantra','emergency_survival','ability','Mantra','self',
        {SelfHPBelow=50,Combat='combat',MainOnly=true,Job='MNK',MissingBuff='Mantra',Cooldown=10});
    E.buff(a,'formless-strikes','Formless Strikes','Formless Strikes',{Enabled=false,Job='MNK',MainOnly=true});
    E.special(a,'Hundred Fists');
end
function G.Definitions.WHM(a)
    E.buff(a,'divine-seal','Divine Seal','Divine Seal',{SelfHPBelow=35,Emergency=true});
    E.spellbuff(a,'protect-party',{'Protectra V','Protectra IV','Protectra III','Protectra II','Protectra'},'Protect','self',
        {Enabled=false,Label='Optional best learned Protectra tier'});
    E.spellbuff(a,'shell-party',{'Shellra V','Shellra IV','Shellra III','Shellra II','Shellra'},'Shell','self',
        {Enabled=false,Label='Optional best learned Shellra tier'});
    E.spellbuff(a,'haste-party','Haste','Haste','ally',{SelfMPAbove=50,PerTargetCooldown=15});
    E.spellbuff(a,'regen-party',{'Regen III','Regen II','Regen'},'Regen','lowest',
        {TargetHPBelow=90,MinMissingHP=100,SelfMPAbove=45,Label='Best learned Regen tier'});
    E.spellbuff(a,'barfire-party','Barfira','Barfire','self',
        {Enabled=false,SelfMPAbove=30,Label='Optional elemental barspell example; duplicate/edit for other elements'});
    E.rule(a,'devotion','utility','ability','Devotion','mp',
        {Enabled=false,SelfHPAbove=80,TargetMPBelow=35,MainOnly=true,Job='WHM',Range=10,Cooldown=10,
         RequireProvider='DevotionTargetSafe'});
    E.rule(a,'martyr','emergency_healing','ability','Martyr','lowest',
        {Enabled=false,SelfHPAbove=85,TargetHPBelow=25,MainOnly=true,Job='WHM',Range=10,Cooldown=10,
         RequireProvider='MartyrTargetSafe'});
    E.buff(a,'afflatus-solace','Afflatus Solace','Afflatus Solace',{Enabled=false});
    E.special(a,'Benediction');
end
function G.Definitions.BLM(a)
    E.interrupt(a,'stun','spell','Stun',{Range=20});
    E.rule(a,'drain','emergency_healing','spell','Drain','enemy',
        {SelfHPBelow=65,Combat='combat',Cooldown=8,PerTargetCooldown=10});
    E.debuff(a,'aspir','Aspir',{Mechanic='enemy_mp',SelfMPBelow=60,PerTargetCooldown=15});
    E.debuff(a,'sleep',{'Sleep II','Sleep'},{Enabled=false,PerTargetCooldown=25,Label='Optional best learned Sleep tier'});
    E.debuff(a,'bio',{'Bio II','Bio'},{Enabled=false,PerTargetCooldown=45,Label='Optional best learned Bio tier'});
    for _,entry in ipairs({
        {'burn','Burn'},{'frost','Frost'},{'choke','Choke'},{'rasp','Rasp'},{'shock','Shock'},{'drown','Drown'}
    }) do E.debuff(a,'elemental-'..entry[1],entry[2],{Enabled=false,PerTargetCooldown=60}); end
    E.rule(a,'elemental-nuke','offensive_magic','spell',
        {'Thunder IV','Blizzard IV','Fire IV','Aero IV','Water IV','Stone IV',
         'Thunder III','Blizzard III','Fire III','Aero III','Water III','Stone III',
         'Thunder II','Blizzard II','Fire II','Aero II','Water II','Stone II',
         'Thunder','Blizzard','Fire','Aero','Water','Stone'},'enemy',
        {SelfMPAbove=40,Combat='combat',Cooldown=5,PerTargetCooldown=5,
         Label='Strongest/preferred learned elemental spell through level 75'});
    E.rule(a,'ancient-magic','offensive_magic','spell',
        {'Burst','Freeze','Flare','Tornado','Quake','Flood'},'enemy',
        {Enabled=false,SelfMPAbove=85,Combat='combat',Cooldown=30,PerTargetCooldown=30});
    E.buff(a,'elemental-seal','Elemental Seal','Elemental Seal',{Enabled=false});
    E.special(a,'Manafont',{SelfHPBelow=100,SelfMPBelow=10});
end
function G.Definitions.RDM(a)
    E.rule(a,'convert','critical_job_mechanics','ability','Convert','self',
        {Enabled=false,Mechanic='convert',SelfHPAbove=85,SelfMPBelow=15,Combat='idle',Cooldown=15});
    E.spellbuff(a,'refresh-party','Refresh','Refresh','mp',{TargetMPBelow=80,ManaTarget=true,SelfMPAbove=40});
    E.spellbuff(a,'haste-party','Haste','Haste','ally',{SelfMPAbove=45});
    E.spellbuff(a,'phalanx','Phalanx','Phalanx');
    E.spellbuff(a,'phalanx-ii','Phalanx II','Phalanx','ally',{Enabled=false,SelfMPAbove=65});
    E.spellbuff(a,'enspell',{'Enthunder','Enblizzard','Enfire','Enaero','Enwater','Enstone'},
        {'Enthunder','Enblizzard','Enfire','Enaero','Enwater','Enstone'},'self',
        {Enabled=false,SelfMPAbove=60,Label='Best available preferred Enspell'});
    E.debuff(a,'dia',{'Dia III','Dia II','Dia'},{PerTargetCooldown=45});
    E.debuff(a,'poison-blind',{'Poison II','Poison','Blind II','Blind'},
        {PerTargetCooldown=60,Label='Maintain missing Poison and Blind effects'});
    E.debuff(a,'slow',{'Slow II','Slow'},{PerTargetCooldown=90});
    E.debuff(a,'paralyze',{'Paralyze II','Paralyze'},{PerTargetCooldown=60});
    E.debuff(a,'gravity','Gravity',{Enabled=false,PerTargetCooldown=60});
    E.debuff(a,'sleep',{'Sleep II','Sleep'},{Enabled=false,PerTargetCooldown=25});
    E.debuff(a,'dispel','Dispel',{Mechanic='dispel',PerTargetCooldown=8});
    E.rule(a,'rdm-nuke','offensive_magic','spell',
        {'Thunder III','Blizzard III','Fire III','Aero III','Water III','Stone III',
         'Thunder II','Blizzard II','Fire II','Aero II','Water II','Stone II',
         'Thunder','Blizzard','Fire','Aero','Water','Stone'},'enemy',
        {Enabled=true,SelfMPAbove=45,Combat='combat',Cooldown=6,PerTargetCooldown=6,
         Label='Strongest/preferred learned RDM elemental spell through level 75'});
    E.buff(a,'composure','Composure','Composure',{Enabled=false});
    E.special(a,'Chainspell');
end
function G.Definitions.THF(a)
    E.rule(a,'sneak-attack','critical_job_mechanics','ability','Sneak Attack','self',
        {Mechanic='behind',SelfTPAbove=1000,Combat='combat',MissingBuff='Sneak Attack',Cooldown=5,
         Label='Sneak Attack, requires PositionSafe adapter'});
    E.rule(a,'trick-attack','critical_job_mechanics','ability','Trick Attack','self',
        {Mechanic='trick_position',SelfTPAbove=1000,Combat='combat',MissingBuff='Trick Attack',Cooldown=5,
         Label='Trick Attack, requires PositionSafe adapter'});
    E.buff(a,'feint','Feint','Feint',{Job='THF',MainOnly=true});
    E.buff(a,'assassins-charge',"Assassin's Charge","Assassin's Charge",{Job='THF',MainOnly=true,SelfTPAbove=1000});
    E.rule(a,'steal','utility','ability','Steal','enemy',{Enabled=false,Combat='combat',Range=3,Cooldown=10});
    E.rule(a,'mug','utility','ability','Mug','enemy',{Enabled=false,Combat='combat',Range=3,Cooldown=10});
    E.rule(a,'flee','utility','ability','Flee','self',{Enabled=false,SelfHPBelow=20,Combat='combat',Cooldown=10});
    E.special(a,'Perfect Dodge');
end
function G.Definitions.PLD(a)
    E.rule(a,'sentinel','emergency_survival','ability','Sentinel','self',
        {SelfHPBelow=50,Combat='combat',MissingBuff='Sentinel',Cooldown=8});
    E.rule(a,'rampart','emergency_survival','ability','Rampart','self',
        {SelfHPBelow=65,Combat='combat',MissingBuff='Rampart',Cooldown=8});
    E.rule(a,'flash','critical_job_mechanics','spell','Flash','enemy',
        {Combat='combat',Range=20,Cooldown=10,PerTargetCooldown=12});
    E.rule(a,'provoke','critical_job_mechanics','ability','Provoke','enemy',
        {Job='WAR',Combat='combat',Range=15,Cooldown=30});
    E.interrupt(a,'shield-bash','ability','Shield Bash',{Range=3});
    E.rule(a,'chivalry','critical_job_mechanics','ability','Chivalry','self',
        {SelfMPBelow=30,SelfTPAbove=1000,MainOnly=true,Job='PLD',Cooldown=10});
    E.buff(a,'fealty','Fealty','Fealty',{Enabled=false,Job='PLD',MainOnly=true});
    E.rule(a,'cover','emergency_survival','ability','Cover','ally',
        {Enabled=false,Combat='combat',Range=3,RequireProvider='CoverPositionSafe'});
    E.special(a,'Invincible');
end
function G.Definitions.DRK(a)
    E.interrupt(a,'stun','spell','Stun',{Range=20});
    E.interrupt(a,'weapon-bash','ability','Weapon Bash',{Range=3,TwoHanded=true});
    E.buff(a,'last-resort','Last Resort','Last Resort',{SelfHPAbove=70});
    E.rule(a,'drain','emergency_healing','spell',{'Drain II','Drain'},'enemy',
        {SelfHPBelow=70,Combat='combat',Cooldown=8,PerTargetCooldown=10});
    E.debuff(a,'aspir','Aspir',{Mechanic='enemy_mp',SelfMPBelow=60,PerTargetCooldown=15});
    E.debuff(a,'absorb-tp','Absorb-TP',{Enabled=false,SelfTPBelow=700,PerTargetCooldown=30});
    E.debuff(a,'absorb-stat',{'Absorb-STR','Absorb-DEX','Absorb-VIT','Absorb-AGI','Absorb-INT','Absorb-MND','Absorb-CHR'},
        {Enabled=false,PerTargetCooldown=60,Label='Preferred available Absorb-stat spell'});
    E.debuff(a,'bio',{'Bio II','Bio'},{Enabled=false,PerTargetCooldown=45});
    E.buff(a,'souleater','Souleater','Souleater',{Enabled=false,SelfHPAbove=95});
    E.buff(a,'dark-seal','Dark Seal','Dark Seal',{Enabled=false,MainOnly=true,Job='DRK'});
    E.buff(a,'diabolic-eye','Diabolic Eye','Diabolic Eye',{Enabled=false,MainOnly=true,Job='DRK',SelfHPAbove=90});
    E.special(a,'Blood Weapon');
end
function G.Definitions.BST(a)
    E.rule(a,'call-beast','critical_job_mechanics','ability','Call Beast','self',
        {Pet='missing',Enabled=false,Consumable=true,Combat='combat',RequireProvider='JugEquipped',Cooldown=15});
    E.rule(a,'charm','critical_job_mechanics','ability','Charm','enemy',
        {Enabled=false,Pet='missing',Range=15,RequireProvider='CharmTargetSafe',Cooldown=15,
         Label='Optional Charm, requires explicit safe-target provider'});
    E.rule(a,'reward','emergency_survival','ability','Reward','self',
        {Pet='present',PetHPBelow=45,Enabled=false,Consumable=true,AmmoContains='Pet Food',Cooldown=10});
    E.rule(a,'fight','job_specific_actions','pet','Fight','enemy',
        {Pet='idle',Combat='combat',Range=20,Cooldown=5});
    E.rule(a,'sic','job_specific_actions','pet','Sic','enemy',
        {Pet='present',PetTPAbove=1000,Combat='combat',Range=20,Cooldown=10,Enabled=false,
         RequireProvider='PetAreaActionSafe',Label='Optional Sic, requires pet/AoE safety approval'});
    E.rule(a,'ready-rabbit-foot-kick','job_specific_actions','pet','Foot Kick','enemy',
        {Pet='present',Combat='combat',Range=20,Cooldown=10,Enabled=false,RequireProvider='ReadyActionSafe'});
    E.rule(a,'feral-howl','debuffs','ability','Feral Howl','enemy',{Enabled=false,Combat='combat',Range=15,MainOnly=true,Job='BST'});
    E.rule(a,'killer-instinct','buff_maintenance','ability','Killer Instinct','self',
        {Enabled=false,Pet='present',Combat='combat',Job='BST',MainOnly=true,Cooldown=15});
    E.special(a,'Familiar');
end

local SONG_BUFFS={
    ['Honor March']='March',['Victory March']='March',['Advancing March']='March',
    ['Valor Minuet V']='Minuet',['Valor Minuet IV']='Minuet',['Valor Minuet III']='Minuet',['Valor Minuet II']='Minuet',['Valor Minuet']='Minuet',
    ['Blade Madrigal']='Madrigal',['Sword Madrigal']='Madrigal',
    ['Hunters Prelude']='Prelude',['Archers Prelude']='Prelude',
    ['Dragonfoe Mambo']='Mambo',['Sheepfoe Mambo']='Mambo',
    ["Mage's Ballad III"]='Ballad',["Mage's Ballad II"]='Ballad',["Mage's Ballad"]='Ballad',
    ["Army's Paeon VI"]='Paeon',["Army's Paeon V"]='Paeon',["Army's Paeon IV"]='Paeon',["Army's Paeon III"]='Paeon',["Army's Paeon II"]='Paeon',["Army's Paeon"]='Paeon',
    ["Knight's Minne V"]='Minne',["Knight's Minne IV"]='Minne',["Knight's Minne III"]='Minne',["Knight's Minne II"]='Minne',["Knight's Minne"]='Minne',
    ['Sinewy Etude']='Etude',['Dextrous Etude']='Etude',['Vivacious Etude']='Etude',['Quick Etude']='Etude',
    ['Learned Etude']='Etude',['Spirited Etude']='Etude',['Enchanting Etude']='Etude',
    ['Herculean Etude']='Etude',['Uncanny Etude']='Etude',['Vital Etude']='Etude',['Swift Etude']='Etude',
    ['Sage Etude']='Etude',['Logical Etude']='Etude',['Bewitching Etude']='Etude',
    ['Fire Carol']='Carol',['Ice Carol']='Carol',['Wind Carol']='Carol',['Earth Carol']='Carol',
    ['Lightning Carol']='Carol',['Water Carol']='Carol',['Light Carol']='Carol',['Dark Carol']='Carol',
    ['Goddesss Hymnus']='Hymnus',["Goddess's Hymnus"]='Hymnus',
    ['Chocobo Mazurka']='Mazurka',['Raptor Mazurka']='Mazurka',
    ['Foe Sirvente']='Sirvente',['Adventurers Dirge']='Dirge',
    ["Sentinel's Scherzo"]='Scherzo',['Warding Round']='Round',
    ['Foe Requiem VII']='Requiem',['Foe Requiem VI']='Requiem',['Foe Requiem V']='Requiem',['Foe Requiem IV']='Requiem',['Foe Requiem III']='Requiem',['Foe Requiem II']='Requiem',['Foe Requiem']='Requiem',
    ['Carnage Elegy']='Elegy',['Battlefield Elegy']='Elegy',
    ['Foe Lullaby II']='Lullaby',['Foe Lullaby']='Lullaby',['Horde Lullaby II']='Lullaby',['Horde Lullaby']='Lullaby',
};
local SONG_LADDER={
    'Victory March','Advancing March','Valor Minuet IV','Valor Minuet III','Valor Minuet II','Valor Minuet',
    'Blade Madrigal','Sword Madrigal',"Mage's Ballad II","Mage's Ballad",
    'Hunters Prelude','Archers Prelude','Dragonfoe Mambo','Sheepfoe Mambo',
    "Army's Paeon V","Army's Paeon IV","Army's Paeon III","Army's Paeon II","Army's Paeon",
    "Knight's Minne IV","Knight's Minne III","Knight's Minne II","Knight's Minne",
    'Sinewy Etude','Dextrous Etude','Vivacious Etude','Quick Etude','Learned Etude','Spirited Etude','Enchanting Etude',
    'Herculean Etude','Uncanny Etude','Vital Etude','Swift Etude','Sage Etude','Logical Etude','Bewitching Etude',
    'Fire Carol','Ice Carol','Wind Carol','Earth Carol','Lightning Carol','Water Carol','Light Carol','Dark Carol',
    'Goddesss Hymnus',"Goddess's Hymnus",'Chocobo Mazurka','Raptor Mazurka','Foe Sirvente','Adventurers Dirge',
};
local BARD_SONG_CATALOG={
    'Victory March','Advancing March','Valor Minuet IV','Valor Minuet III','Valor Minuet II','Valor Minuet',
    'Blade Madrigal','Sword Madrigal','Hunters Prelude','Archers Prelude','Dragonfoe Mambo','Sheepfoe Mambo',
    "Mage's Ballad II","Mage's Ballad","Army's Paeon V","Army's Paeon IV","Army's Paeon III","Army's Paeon II","Army's Paeon",
    "Knight's Minne IV","Knight's Minne III","Knight's Minne II","Knight's Minne",
    'Sinewy Etude','Dextrous Etude','Vivacious Etude','Quick Etude','Learned Etude','Spirited Etude','Enchanting Etude',
    'Herculean Etude','Uncanny Etude','Vital Etude','Swift Etude','Sage Etude','Logical Etude','Bewitching Etude',
    'Fire Carol','Ice Carol','Wind Carol','Earth Carol','Lightning Carol','Water Carol','Light Carol','Dark Carol',
    'Fire Threnody','Ice Threnody','Wind Threnody','Earth Threnody','Lightning Threnody','Water Threnody','Light Threnody','Dark Threnody',
    'Foe Requiem VI','Foe Requiem V','Foe Requiem IV','Foe Requiem III','Foe Requiem II','Foe Requiem',
    'Carnage Elegy','Battlefield Elegy','Magic Finale','Foe Lullaby II','Foe Lullaby','Horde Lullaby',
    'Goddesss Hymnus',"Goddess's Hymnus",'Chocobo Mazurka','Raptor Mazurka','Foe Sirvente','Adventurers Dirge',
};
function G.Definitions.BRD(a)
    -- Each slot walks the same strongest/preferred ladder but skips a family already active,
    -- so low-level BRDs use whatever songs they actually know instead of waiting for March.
    E.rule(a,'song-slot-1','buff_maintenance','spell',SONG_LADDER,'self',
        {SongSlot=1,Cooldown=4,PerTargetCooldown=30,MissingBuffByAction=SONG_BUFFS,
         Label='Dynamic song slot 1: strongest/preferred learned missing song'});
    E.rule(a,'song-slot-2','buff_maintenance','spell',SONG_LADDER,'self',
        {SongSlot=2,Cooldown=4,PerTargetCooldown=30,MissingBuffByAction=SONG_BUFFS,
         Label='Dynamic song slot 2: next strongest/preferred learned missing song'});
    E.debuff(a,'elegy',{'Carnage Elegy','Battlefield Elegy'},{SelfMPAbove=0,PerTargetCooldown=100});
    E.debuff(a,'requiem',{'Foe Requiem VI','Foe Requiem V','Foe Requiem IV','Foe Requiem III','Foe Requiem II','Foe Requiem'},
        {SelfMPAbove=0,PerTargetCooldown=60});
    E.debuff(a,'finale','Magic Finale',{Mechanic='dispel',SelfMPAbove=0,PerTargetCooldown=8});
    E.debuff(a,'lullaby',{'Foe Lullaby II','Foe Lullaby'},{Enabled=false,SelfMPAbove=0,PerTargetCooldown=25});
    E.buff(a,'nightingale','Nightingale','Nightingale',{Enabled=false,MainOnly=true,Job='BRD'});
    E.buff(a,'troubadour','Troubadour','Troubadour',{Enabled=false,MainOnly=true,Job='BRD'});
    E.special(a,'Soul Voice');
    -- Zero means no MP gate in these authored defaults, not a strict >0 rule.
    for _,row in ipairs(a) do if row.SelfMPAbove==0 then row.SelfMPAbove=nil; end end
end
function G.Definitions.RNG(a)
    E.buff(a,'sharpshot','Sharpshot','Sharpshot');
    E.buff(a,'barrage','Barrage','Barrage',{Ranged=true,SelfTPBelow=1000});
    E.rule(a,'ranged-attack','job_specific_actions','ranged',nil,'enemy',
        {Combat='combat',Ranged=true,Cooldown=5,PerTargetCooldown=5,Range=20});
    E.buff(a,'unlimited-shot','Unlimited Shot','Unlimited Shot',{Enabled=false,Ranged=true});
    E.buff(a,'flashy-shot','Flashy Shot','Flashy Shot',{Enabled=false,MainOnly=true,Job='RNG',Ranged=true});
    E.rule(a,'stealth-shot','buff_maintenance','ability','Stealth Shot','self',
        {Enabled=false,MainOnly=true,Job='RNG',Combat='combat',Cooldown=10});
    E.rule(a,'eagle-eye-shot','emergency_survival','ability','Eagle Eye Shot','enemy',
        {Special=true,Enabled=false,Combat='combat',Ranged=true,Range=20,Cooldown=30});
end
function G.Definitions.SAM(a)
    E.buff(a,'hasso','Hasso','Hasso',{SelfHPAbove=60,TwoHanded=true,ForbidBuff='Seigan'});
    E.buff(a,'seigan','Seigan','Seigan',{Enabled=false,SelfHPBelow=45,TwoHanded=true,ForbidBuff='Hasso'});
    E.buff(a,'third-eye','Third Eye','Third Eye',{SelfHPBelow=70,TwoHanded=true});
    E.buff(a,'sekkanoki','Sekkanoki','Sekkanoki',{SelfTPAbove=2000});
    E.interrupt(a,'blade-bash','ability','Blade Bash',{Range=3,Job='SAM',MainOnly=true});
    E.rule(a,'shikikoyo','utility','ability','Shikikoyo','ally',
        {Enabled=false,SelfTPAbove=2000,Job='SAM',MainOnly=true,Range=5,Cooldown=15,
         RequireProvider='ShikikoyoTargetSafe'});
    E.special(a,'Meikyo Shisui');
end
function G.Definitions.NIN(a)
    E.debuff(a,'kurayami',{'Kurayami: Ni','Kurayami: Ichi'},{SelfMPAbove=0,PerTargetCooldown=75});
    E.debuff(a,'hojo',{'Hojo: Ni','Hojo: Ichi'},{SelfMPAbove=0,PerTargetCooldown=75});
    E.debuff(a,'jubaku','Jubaku: Ichi',{SelfMPAbove=0,PerTargetCooldown=60});
    E.debuff(a,'dokumori','Dokumori: Ichi',{Enabled=false,SelfMPAbove=0,PerTargetCooldown=60});
    E.rule(a,'elemental-ninjutsu','offensive_magic','spell',
        {'Raiton: San','Hyoton: San','Katon: San','Huton: San','Doton: San','Suiton: San',
         'Raiton: Ni','Hyoton: Ni','Katon: Ni','Huton: Ni','Doton: Ni','Suiton: Ni',
         'Raiton: Ichi','Hyoton: Ichi','Katon: Ichi','Huton: Ichi','Doton: Ichi','Suiton: Ichi'},'enemy',
        {Enabled=false,Combat='combat',SelfMPAbove=0,Cooldown=6,PerTargetCooldown=6,
         Label='Strongest/preferred learned elemental ninjutsu through level 75'});
    E.spellbuff(a,'tonko',{'Tonko: Ni','Tonko: Ichi'},'Invisible','self',{Enabled=false,SelfMPAbove=0});
    E.spellbuff(a,'monomi','Monomi: Ichi','Sneak','self',{Enabled=false,SelfMPAbove=0});
    E.buff(a,'sange','Sange','Sange',{Enabled=false,Consumable=true,Job='NIN',MainOnly=true,RequireProvider='ThrowingAmmoSafe'});
    E.rule(a,'mijin-gakure','emergency_survival','ability','Mijin Gakure','enemy',
        {Enabled=false,Special=true,SelfHPBelow=5,Combat='combat',Cooldown=60,
         Label='Mijin Gakure: intentionally disabled, self-sacrifice'});
    -- Zero means no MP gate in these authored defaults, not a strict >0 rule.
    for _,row in ipairs(a) do if row.SelfMPAbove==0 then row.SelfMPAbove=nil; end end
end
function G.Definitions.DRG(a)
    E.rule(a,'call-wyvern','critical_job_mechanics','ability','Call Wyvern','self',
        {Pet='missing',Combat='combat',Cooldown=15});
    E.rule(a,'spirit-link','emergency_survival','ability','Spirit Link','self',
        {Pet='present',PetHPBelow=40,SelfHPAbove=80,Cooldown=10});
    E.rule(a,'jump','job_specific_actions','ability','Jump','enemy',{Combat='combat',Range=3.5,Cooldown=5});
    E.rule(a,'high-jump','job_specific_actions','ability','High Jump','enemy',{Combat='combat',Range=3.5,Cooldown=5});
    E.rule(a,'super-jump','emergency_survival','ability','Super Jump','enemy',
        {Enabled=false,SelfHPBelow=25,Combat='combat',Range=3.5,Cooldown=10});
    E.rule(a,'angon','debuffs','ability','Angon','enemy',
        {Enabled=false,Consumable=true,RequiredItem='Angon',Combat='combat',Range=10,Cooldown=10,
         MainOnly=true,Job='DRG'});
    E.buff(a,'deep-breathing','Deep Breathing','Deep Breathing',
        {Enabled=false,Pet='present',MainOnly=true,Job='DRG'});
    E.special(a,'Spirit Surge');
end
function G.Definitions.SMN(a)
    E.rule(a,'summon-avatar','critical_job_mechanics','spell',
        {'Fenrir','Diabolos','Garuda','Ifrit','Shiva','Ramuh','Titan','Leviathan','Carbuncle'},'self',
        {Pet='missing',SelfMPAbove=50,Combat='combat',Cooldown=15,
         Label='Preferred unlocked avatar with Carbuncle fallback'});
    E.rule(a,'avatar-assault','job_specific_actions','pet','Assault','enemy',
        {Pet='idle',Combat='combat',Range=20,Cooldown=5});
    E.rule(a,'healing-ruby','emergency_healing','pet',{'Healing Ruby II','Healing Ruby'},'lowest',
        {Pet='present',TargetHPBelow=50,Emergency=true,Range=15,Cooldown=10,PerTargetCooldown=10});
    E.rule(a,'avatar-ward','buff_maintenance','pet',
        {'Hastega','Aerial Armor','Earthen Ward','Shining Ruby'},'self',
        {Pet='present',Combat='combat',Cooldown=10,PerTargetCooldown=30,RequireProvider='AvatarWardNeeded',
         Label='Best available configured avatar ward; provider decides when a ward is needed'});
    E.rule(a,'avatar-rage','job_specific_actions','pet',
        {'Predator Claws','Rush','Spinning Dive','Chaotic Strike','Flaming Crush','Mountain Buster',
         'Eclipse Bite','Double Punch','Meteorite','Poison Nails'},'enemy',
        {Pet='present',Combat='combat',SelfMPAbove=35,Range=20,Cooldown=8,PerTargetCooldown=8,
         Label='Best available pact for the currently summoned avatar'});
    E.rule(a,'release-avatar','utility','pet','Release','self',
        {Enabled=false,Pet='present',SelfMPBelow=10,Combat='idle',Cooldown=15});
    E.special(a,'Astral Flow');
end
function G.Definitions.BLU(a)
    E.rule(a,'blue-heal','emergency_healing','spell',
        {'Magic Fruit','Wild Carrot','Healing Breeze','Pollen'},'self',
        {BlueMagic=true,SelfHPBelow=50,Emergency=true,Cooldown=3,
         Label='Best available equipped Blue Magic self-heal'});
    E.spellbuff(a,'cocoon','Cocoon','Defense Boost','self',{BlueMagic=true});
    E.spellbuff(a,'metallic-body','Metallic Body','Stoneskin','self',{BlueMagic=true});
    E.spellbuff(a,'refueling','Refueling','Haste','self',{BlueMagic=true});
    E.interrupt(a,'head-butt','spell','Head Butt',{BlueMagic=true,Range=3});
    E.rule(a,'blue-physical','offensive_magic','spell',
        {'Disseverment','Hysteric Barrage','Frenetic Rip','Vertical Cleave','Death Scissors','Sickle Slash',
         'Jet Stream','Bludgeon','Head Butt','Sprout Smack','Power Attack','Foot Kick'},'enemy',
        {BlueMagic=true,Combat='combat',Range=3,SelfMPAbove=45,Cooldown=6,PerTargetCooldown=6,
         Label='Strongest/preferred equipped single-target Blue Magic attack through level 75'});
    E.rule(a,'healing-breeze','emergency_healing','spell','Healing Breeze','self',
        {Enabled=false,BlueMagic=true,SelfHPBelow=60,Cooldown=8});
    E.buff(a,'chain-affinity','Chain Affinity','Chain Affinity',{Enabled=false,SelfTPAbove=1000});
    E.buff(a,'burst-affinity','Burst Affinity','Burst Affinity',{Enabled=false,RequireProvider='MagicBurstWindow'});
    E.buff(a,'convergence','Convergence','Convergence',{Enabled=false,Job='BLU',MainOnly=true});
    E.buff(a,'diffusion','Diffusion','Diffusion',{Enabled=false,Job='BLU',MainOnly=true});
    E.special(a,'Azure Lore');
end

local ROLL_LADDER={
    "Chaos Roll","Hunter's Roll","Samurai Roll","Fighter's Roll","Rogue's Roll","Evoker's Roll","Healer's Roll","Wizard's Roll","Warlock's Roll",
    "Monk's Roll","Gallant's Roll","Beast Roll","Choral Roll","Ninja Roll","Drachen Roll","Magus's Roll","Corsair's Roll","Puppet Roll",
    "Dancer's Roll","Scholar's Roll","Bolter's Roll","Caster's Roll","Courser's Roll","Blitzer's Roll","Tactician's Roll",
    "Allies' Roll","Miser's Roll","Companion's Roll","Avenger's Roll","Naturalist's Roll","Runeist's Roll",
};
local ROLL_BUFFS={}; for _,name in ipairs(ROLL_LADDER) do ROLL_BUFFS[name]=name; end
function G.Definitions.COR(a)
    E.rule(a,'roll-slot-1','buff_maintenance','ability',ROLL_LADDER,'self',
        {RollSlot=1,Cooldown=10,PerTargetCooldown=30,MissingBuffByAction=ROLL_BUFFS,
         Label='Dynamic roll slot 1: best available preferred missing roll'});
    E.rule(a,'roll-slot-2','buff_maintenance','ability',ROLL_LADDER,'self',
        {RollSlot=2,Cooldown=10,PerTargetCooldown=30,MissingBuffByAction=ROLL_BUFFS,
         Label='Dynamic roll slot 2: next available preferred missing roll'});
    E.rule(a,'double-up','critical_job_mechanics','ability','Double-Up','self',
        {Enabled=false,Mechanic='double_up',MaximumRollTotal=5,RequiresBuff='Double-Up Chance',Combat='combat',Cooldown=3});
    E.rule(a,'quick-draw','job_specific_actions','ability',
        {'Light Shot','Dark Shot','Fire Shot','Ice Shot','Wind Shot','Earth Shot','Thunder Shot','Water Shot'},'enemy',
        {Enabled=false,Consumable=true,Combat='combat',Range=15,Cooldown=10,RequireProvider='QuickDrawSafe',
         Label='Preferred available Quick Draw shot; adapter must approve target/use'});
    E.rule(a,'ranged-attack','job_specific_actions','ranged',nil,'enemy',
        {Enabled=false,Combat='combat',Ranged=true,Range=20,Cooldown=5});
    E.rule(a,'fold','critical_job_mechanics','ability','Fold','self',
        {Status='Bust',Job='COR',MainOnly=true,Cooldown=10});
    E.buff(a,'snake-eye','Snake Eye','Snake Eye',{Enabled=false,Job='COR',MainOnly=true,RequiresBuff='Double-Up Chance'});
    E.rule(a,'random-deal','utility','ability','Random Deal','self',
        {Enabled=false,Combat='combat',Cooldown=15,RequireProvider='RandomDealNeeded'});
    E.special(a,'Wild Card');
end
function G.Definitions.PUP(a)
    E.rule(a,'activate','critical_job_mechanics','ability','Activate','self',
        {Pet='missing',Combat='combat',Cooldown=15});
    E.rule(a,'deploy','job_specific_actions','pet','Deploy','enemy',
        {Pet='idle',Combat='combat',Range=15,Cooldown=5});
    E.rule(a,'repair','emergency_survival','ability','Repair','self',
        {Enabled=false,Consumable=true,Pet='present',PetHPBelow=40,AmmoContains='Automat. Oil',Cooldown=15});
    for i,name in ipairs({'Light Maneuver','Fire Maneuver','Wind Maneuver'}) do
        E.rule(a,'maneuver-'..i,'buff_maintenance','pet',name,'self',
            {Pet='present',MissingBuff=name,Mechanic='maneuver',Combat='combat',Cooldown=25,PerTargetCooldown=25,
             RequireProvider='ManeuverHeatSafe',Label=name .. ', requires heat-safety adapter'});
    end
    E.rule(a,'deactivate','utility','ability','Deactivate','self',
        {Enabled=false,Pet='present',Combat='idle',Cooldown=30,RequireProvider='DeactivateSafe'});
    E.rule(a,'role-reversal','emergency_survival','ability','Role Reversal','self',
        {Enabled=false,Pet='present',PetHPBelow=25,SelfHPAbove=85,MainOnly=true,Job='PUP',Cooldown=10});
    E.rule(a,'ventriloquy','utility','ability','Ventriloquy','enemy',
        {Enabled=false,Pet='present',Combat='combat',MainOnly=true,Job='PUP',Range=10,Cooldown=10,
         RequireProvider='VentriloquySafe'});
    E.special(a,'Overdrive');
end

local MAX_GAMBIT_ROWS = 14;
function E.default_profile(job)
    local common=E.common_rules(job);
    local jobRules={};
    if G.Definitions[job] then G.Definitions[job](jobRules); end
    -- The old shared pool contains many optional subjob and status rules.
    -- Keep only a small job-relevant foundation so a 14-row sheet still
    -- exposes the main job's own mechanics.
    local wanted={['weapon-skill']=true};
    if job=='RNG' or job=='COR' then wanted['ranged-weapon-skill']=true; end
    if E.contains({'WHM','SCH'},job) then
        for _,id in ipairs({'emergency-cursna','raise','emergency-cure','maintenance-cure',
            'remove-petrification','remove-silence','erase'}) do wanted[id]=true; end
    elseif job=='RDM' then
        for _,id in ipairs({'raise','emergency-cure','maintenance-cure','erase'}) do wanted[id]=true; end
    elseif job=='PLD' then
        wanted['emergency-cure']=true; wanted['maintenance-cure']=true;
    elseif job=='BLM' then
        wanted['blink']=true; wanted['stoneskin']=true;
    end
    if E.contains({'WAR','MNK','THF','DRK','BST','RNG','SAM','NIN','DRG','COR','PUP','DNC','RUN'},job) then
        wanted['sub-berserk']=true;
    end
    local rules={};
    for _,rule in ipairs(common) do
        if wanted[rule.Id] and rule.Enabled~=false then rules[#rules+1]=rule; end
    end
    for _,rule in ipairs(jobRules) do
        if #rules>=MAX_GAMBIT_ROWS then break; end
        if rule.Enabled~=false then rules[#rules+1]=rule; end
    end
    local rank={}; for i,layer in ipairs(LAYERS) do rank[layer]=i; end
    for i,r in ipairs(rules) do r._order=i; end
    table.sort(rules,function(a,b)
        local ar,br=rank[a.Layer] or 99,rank[b.Layer] or 99;
        if ar~=br then return ar<br; end
        return a._order<b._order;
    end);
    for _,r in ipairs(rules) do r._order=nil; end
    return {Version=4,Job=job,Enabled=true,Rules=rules,WeaponSkills={},BlueSet={}};
end
function E.profile_validate(profile,job)
    if type(profile)~='table' or type(profile.Rules)~='table' then return nil,'Profile must contain Rules = { ... }'; end
    local ruleCount=0;
    for key in pairs(profile.Rules) do
        if type(key)~='number' or key<1 or key~=math.floor(key) then return nil,'Rules must be a consecutive array'; end
        ruleCount=ruleCount+1;
    end
    if ruleCount>MAX_GAMBIT_ROWS then return nil,'Gambit sheets are limited to 14 rows'; end
    if ruleCount~=#profile.Rules then return nil,'Rules must be a consecutive array'; end
    if profile.Job and profile.Job~=job then return nil,'Profile job does not match current main job'; end
    if profile.Enabled~=nil and type(profile.Enabled)~='boolean' then return nil,'Enabled must be boolean'; end
    local used={};
    local types={spell=true,ability=true,pet=true,ws=true,ws_auto=true,item=true,ranged=true,cure=true,attack=true,none=true};
    local targets={self=true,owner=true,player=true,master=true,enemy=true,foe=true,ally=true,lowest=true,mp=true,dead=true,status=true,pet=true,
        party_member=true,alliance_member=true,party_pool_tank=true,party_pool_support=true,party_pool_dps=true,
        party_any=true,party_leader=true,party_tank=true,party_healer=true,party_melee=true,party_ranged=true,party_caster=true,party_support=true,
        highest_tp=true,lowest_tp=true,closest_ally=true,furthest_ally=true,alliance_any=true,alliance_tank=true,alliance_healer=true,
        alliance_lowest_hp=true,alliance_lowest_mp=true,specific_party=true,specific_alliance=true,dead_party=true,dead_alliance=true,
        lowest_hp_eligible_ally=true,eligible_lowest_hp=true,greatest_missing_hp_ally=true,ally_with_removable_ailment=true,
        removable_ailment_ally=true,specific_trust=true,current_enemy_victim=true,eligible_add_threatening_party=true,
        statused_ally=true,debuffed_ally=true,party_pet=true,automaton=true,wyvern=true,avatar=true,luopan=true,current_target=true,
        player_target=true,leader_target=true,tank_target=true,nearest_foe=true,lowest_hp_foe=true,highest_hp_foe=true,add=true,
        foe_targeting_self=true,foe_targeting_player=true,foe_targeting_healer=true,foe_targeting_tank=true,target_of_target=true,
        nm=true,boss=true,beastman=true,undead=true,arcana=true,dragon=true};
    local operators={['<']=true,['<=']=true,['=']=true,['==']=true,['!=']=true,['~=']=true,['>=']=true,['>']=true,
        present=true,missing=true,yes=true,no=true,has=true,['not']=true,ready=true,['not-ready']=true,any=true,
        weak=true,resist=true,immune=true,absorb=true,behind=true,front=true,beside=true};
    local validateCondition=function(c,label,id)
        if c.CheckTarget~=nil and (type(c.CheckTarget)~='string' or not E.target_supported(c.CheckTarget)) then return 'Invalid condition subject in '..id..' '..label; end
        if c.CheckTargetName~=nil and type(c.CheckTargetName)~='string' then return 'Invalid condition subject name in '..id..' '..label; end
        if c.MissingBuffBinding~=nil and c.MissingBuffBinding~='action' then return 'Invalid missing-status binding in '..id..' '..label; end
        if c.SubjectLabel~=nil and type(c.SubjectLabel)~='string' then return 'Invalid subject label in '..id..' '..label; end
        if c.Property~=nil and (type(c.Property)~='string' or c.Property=='') then return 'Invalid Property in '..id..' '..label; end
        if c.Operator~=nil and not operators[c.Operator] then return 'Invalid Operator in '..id..' '..label; end
        if c.TextValue~=nil and type(c.TextValue)~='string' then return 'Invalid TextValue in '..id..' '..label; end
        if c.ValueText~=nil and type(c.ValueText)~='string' then return 'Invalid ValueText in '..id..' '..label; end
        if c.Value~=nil and type(c.Value)~='number' and type(c.Value)~='string' then return 'Invalid Value in '..id..' '..label; end
        if c.Mechanic~=nil and not E.contains({'interrupt','convert','behind','trick_position','double_up','enemy_mp','dispel','maneuver'},c.Mechanic) then
            return 'Unknown mechanic in '..id..' '..label;
        end
        for _,key in ipairs({'SelfHPBelow','SelfHPAbove','SelfMPBelow','SelfMPAbove','TargetHPBelow','TargetHPAbove','TargetMPBelow','TargetMPAbove'}) do
            if c[key]~=nil and (type(c[key])~='number' or c[key]<0 or c[key]>100) then return 'Invalid percentage '..key..' in '..id..' '..label; end
        end
        for _,key in ipairs({'Range','TP','SelfTPAbove','SelfTPBelow','MinMissingHP','PetHPBelow','PetTPAbove','MissingBuffExpireThreshold'}) do
            if c[key]~=nil and (type(c[key])~='number' or c[key]<0) then return 'Invalid number '..key..' in '..id..' '..label; end
        end
        if c.Range and (c.Range<0.1 or c.Range>30) then return 'Range must be 0.1-30 in '..id..' '..label; end
        if c.Combat~=nil and not E.contains({'any','combat','idle'},c.Combat) then return 'Invalid Combat mode in '..id..' '..label; end
        return nil;
    end;
    for i,r in ipairs(profile.Rules) do
        if type(r)~='table' or type(r.Id)~='string' or not r.Id:match('^[%w_%-]+$') then return nil,'Rule '..i..' needs an alphanumeric Id'; end
        if used[r.Id] then return nil,'Duplicate rule Id: '..r.Id; end
        used[r.Id]=true;
        if r.Empty~=true then
            if not types[r.Type] then return nil,'Unknown action type in '..r.Id; end
            if not targets[r.Target or 'self'] then return nil,'Unknown target in '..r.Id; end
            local conditionErr=validateCondition(r,'Condition #1',r.Id);
            if conditionErr then return nil,conditionErr; end
            if r.Condition2~=nil then
                if type(r.Condition2)~='table' then return nil,'Condition #2 must be a table in '..r.Id; end
                conditionErr=validateCondition(r.Condition2,'Condition #2',r.Id);
                if conditionErr then return nil,conditionErr; end
            end
            for _,key in ipairs({'SongSlot','RollSlot'}) do
                if r[key]~=nil and (type(r[key])~='number' or r[key]<1 or r[key]>2 or r[key]~=math.floor(r[key])) then
                    return nil,key..' must be 1 or 2 in '..r.Id;
                end
            end
            if r.Enabled~=nil and type(r.Enabled)~='boolean' then return nil,'Enabled must be boolean in '..r.Id; end
            if r.CureEfficiency~=nil and (type(r.CureEfficiency)~='boolean' or r.Type~='cure') then return nil,'Invalid Cure efficiency option in '..r.Id; end
            if r.CureGoalHP~=nil and (r.Type~='cure' or type(r.CureGoalHP)~='number' or r.CureGoalHP<1 or r.CureGoalHP>100) then return nil,'Invalid Cure HP goal in '..r.Id; end
            if r.MainOnly and not r.Job then return nil,'MainOnly requires a Job in '..r.Id; end
            if r.Action~=nil and not E.safe_name(r.Action) then return nil,'Invalid action name in '..r.Id; end
            if r.Actions~=nil then
                if type(r.Actions)~='table' then return nil,'Actions must be an array in '..r.Id; end
                local actionCount=0;
                for key in pairs(r.Actions) do
                    if type(key)~='number' or key<1 or key~=math.floor(key) then return nil,'Actions must be a consecutive array in '..r.Id; end
                    actionCount=actionCount+1;
                end
                if actionCount~=#r.Actions then return nil,'Actions must be a consecutive array in '..r.Id; end
                for _,name in ipairs(r.Actions) do if not E.safe_name(name) then return nil,'Invalid action in '..r.Id; end end
            end
            if r.MissingBuffByAction~=nil then
                if type(r.MissingBuffByAction)~='table' then return nil,'MissingBuffByAction must be a table in '..r.Id; end
                for action,buff in pairs(r.MissingBuffByAction) do
                    if not E.safe_name(action) then return nil,'Invalid MissingBuffByAction action in '..r.Id; end
                    if type(buff)~='string' and type(buff)~='number' and type(buff)~='table' then
                        return nil,'Invalid MissingBuffByAction buff in '..r.Id;
                    end
                end
            end
            for _,key in ipairs({'Cooldown','PerTargetCooldown','MinLevel','MPReserve','FailureBackoff'}) do
                if r[key]~=nil and (type(r[key])~='number' or r[key]<0) then return nil,'Invalid number '..key..' in '..r.Id; end
            end
        end
    end
    profile.Job=job; profile.BlueSet=profile.BlueSet or {}; profile.WeaponSkills=profile.WeaponSkills or {};
    if type(profile.BlueSet)~='table' or type(profile.WeaponSkills)~='table' then return nil,'BlueSet and WeaponSkills must be tables'; end
    return profile;
end
function E.profile_load(ctx,force)
    if not ctx.self or ctx.mainJob=='UNKNOWN' then return false; end
    local identity=ctx.self.name:gsub('[^%w_%-]','_') .. '_' .. tostring(ctx.self.id);
    local base=E.root() .. 'jobs/';
    local path=base .. ctx.mainJob .. '.lua';
    local changed=path~=S.profilePath;
    if S.identity~=identity then
        S.identity=identity;
        S.guestProfiles={}; S.guestProfileText={};
        S.ui.edits={};
    end
    if changed then
        E.mkdir(base);
        S.profilePath=path; S.profileText=nil; S.profile=nil; S.profileError=nil;
        S.ui.selected=1; S.ui.edits={};
    end
    local txt,readError=E.readfile(path);
    if not txt and not readError then
        if S.profileText then S.profileError='Profile temporarily unavailable'; return false; end
        local legacyPath=E.root() .. 'characters/' .. identity .. '/' .. ctx.mainJob .. '.lua';
        local legacyText,legacyError=E.readfile(legacyPath);
        if legacyError then S.profileError=legacyError; return false; end
        local profile;
        if legacyText then
            local err;
            profile,err=E.parse(legacyText,legacyPath);
            if not profile then S.profileError='Legacy job sheet rejected: '..tostring(err); return false; end
            E.log('Imported this character\'s '..ctx.mainJob..' sheet into the shared local job folder. The original remains unchanged.',true);
        else profile=E.default_profile(ctx.mainJob); end
        local ok,data=E.writefile(path,profile,'Ordered rules. Top-to-bottom priority; launcher Enabled is separate.');
        if not ok then S.profileError=tostring(data); return false; end
        txt=data;
    end
    if not changed and not force and txt==S.profileText and not S.profileError then return true; end
    local value,err=E.parse(txt,path);
    if value and type(value.Rules)=='table' and #value.Rules>MAX_GAMBIT_ROWS then
        local originalCount=#value.Rules;
        local backed,backupError=E.backup_profile_text(path,txt);
        if not backed then S.profileError='14-row backup failed: '..tostring(backupError); return false; end
        for i=originalCount,MAX_GAMBIT_ROWS+1,-1 do value.Rules[i]=nil; end
        local ok,newText=E.writefile(path,value,'Gambits. Maximum 14 ordered rows.');
        if not ok then S.profileError='14-row migration failed: '..tostring(newText); return false; end
        txt=newText;
        E.log('This job sheet had '..originalCount..' rows. Kept rows 1-14; the original was backed up beside the sheet.',true);
    end
    if value then value,err=E.profile_validate(value,ctx.mainJob); end
    if not value then
        S.profileError=readError or err; E.log('Job configuration rejected: '..tostring(S.profileError)); return false;
    end
    S.profile=value; S.profileText=txt; S.profileError=nil; S.ui.edits={};
    if E.number(value.Version,0)<4 and (S.lastProfileVersionWarning~=path or force) then
        E.log('This saved job profile predates preset v4. Use /autobox reset confirm once for this job to install the complete dynamic action ladders.',true);
        S.lastProfileVersionWarning=path;
    end
    return true;
end
-- Master switches are owned by the player character, independent of shared job rules.
-- Trust keys include their name and job, so two members of the same job can differ.
function E.actor_switch_path(identity)
    return E.root() .. 'characters/' .. identity .. '/switches.lua';
end
function E.actor_switch_key(actor)
    if not actor or not actor.name then return nil; end
    return (E.is_generated_recruit(actor) and 'recruit:' or 'trust:')
        .. E.safe_file_stem(actor.name) .. ':' .. tostring(actor.mainJob or 'UNKNOWN');
end
-- (2.2.210, 2026-11-20: "Kurami wasn't curing as much") Is this window the Dualbox character? The follow addon, which
-- only runs in the second window, writes that character's name to config/addons/duo/status.cfg every second.
-- 2.2.208 switched every character's own gambits off until "/autobox on", and that caught the Dualbox character too:
-- its rule sheet (cures, buffs) stopped running and only the follow addon's basic support was left.
function E.is_dualbox(name)
    if type(name)~='string' or name=='' then return false; end
    local base=E.call(AshitaCore,'GetInstallPath');
    if type(base)~='string' or base=='' then return false; end
    if not base:match('[/\\]$') then base=base..'/'; end
    local txt=E.readfile(base..'config/addons/duo/status.cfg');
    if type(txt)~='string' then return false; end
    local who=txt:match('name=([^\r\n]+)');
    return who~=nil and who:lower()==name:lower();
end
function E.actor_switch_load(ctx,force)
    if not ctx or not ctx.self or not ctx.self.name or not ctx.self.id then return false,'No player character'; end
    local identity=E.safe_file_stem(ctx.self.name)..'_'..tostring(ctx.self.id);
    local path=E.actor_switch_path(identity);
    if S.switchPath==path and S.switches and not force then return true; end
    local txt,readError=E.readfile(path);
    if not txt and not readError then
        if S.switchPath==path and S.switchText then S.switchError='Switch file temporarily unavailable'; return false,S.switchError; end
        E.mkdir(E.root()..'characters/'); E.mkdir(E.root()..'characters/'..identity..'/');
        local initial=(S.settings or DEFAULT).Enabled~=false;
        -- your own gambits start OFF (/autobox on); the Dualbox character's start ON, nobody is at its keyboard
        local ok,data=E.writefile(path,{Version=3,Player=E.is_dualbox(ctx.self.name),GuestDefault=initial,Guests={}},
            'Local master switches for this player and owned Trusts.');
        if not ok then S.switchError=tostring(data); return false,S.switchError; end
        txt=data;
    end
    if S.switchPath==path and S.switches and txt==S.switchText and not S.switchError then return true; end
    local value,err=E.parse(txt,path);
    if value and (type(value.Player)~='boolean' or type(value.GuestDefault)~='boolean' or type(value.Guests)~='table') then
        value=nil; err='Invalid character master switches';
    end
    if value then
        for key,enabled in pairs(value.Guests) do
            if type(key)~='string' or type(enabled)~='boolean' then value=nil; err='Invalid Trust master switch'; break; end
        end
    end
    if value and value.Version~=2 and value.Version~=3 then   -- 2.2.208: the player's own gambits are off unless switched on (once per character)
        value.Player=false; value.Version=2;
        local ok,data=E.writefile(path,value,'Local master switches for this player and owned Trusts.');
        if ok then txt=data; E.log('Your own gambits are now off unless you turn them on: /autobox on',true); end
    end
    if value and value.Version==2 then   -- 2.2.210: once per character, the Dualbox character gets its gambits back
        value.Version=3;
        local dual=E.is_dualbox(ctx.self.name);
        if dual and value.Player==false then value.Player=true; end
        local ok,data=E.writefile(path,value,'Local master switches for this player and owned Trusts.');
        if ok then
            txt=data;
            if dual then E.log('Dualbox character: its own gambits are switched back on (/autobox off turns them off).',true); end
        end
    end
    if not value then S.switchError=readError or err; return false,S.switchError; end
    S.switchPath=path; S.switchText=txt; S.switches=value; S.switchError=nil;
    return true;
end
function E.actor_enabled(ctx,actor)
    if not E.actor_switch_load(ctx,false) then return false; end
    if not actor or actor.id==ctx.self.id then return S.switches.Player==true; end
    local key=E.actor_switch_key(actor);
    local saved=key and S.switches.Guests[key];
    if saved~=nil then return saved==true; end
    return S.switches.GuestDefault==true;
end
function E.actor_switch_set(ctx,actor,enabled)
    local loaded,err=E.actor_switch_load(ctx,false);
    if not loaded then return false,err; end
    if E.readfile(S.switchPath)~=S.switchText then
        E.actor_switch_load(ctx,true);
        return false,'Character switches changed externally. Try again.';
    end
    local updated=E.clone(S.switches);
    if not actor or actor.id==ctx.self.id then updated.Player=enabled==true;
    else
        local key=E.actor_switch_key(actor);
        if not key then return false,'Trust identity unavailable'; end
        updated.Guests[key]=enabled==true;
    end
    local ok,txt=E.writefile(S.switchPath,updated,'Local master switches for this player and owned Trusts.');
    if not ok then return false,txt; end
    S.switches=updated; S.switchText=txt;
    local actorId=actor and actor.id or ctx.self.id;
    if not enabled then
        local pending=S.pendingByActor[actorId];
        if pending then pending.canceled=true; E.clear_pending(pending); end
    end
    return true;
end

function E.safe_file_stem(name)
    name=tostring(name or 'Guest'):gsub('[^%w_%-]','_');
    if name=='' then name='Guest'; end
    return name;
end
function E.guest_profile_key(actor)
    if E.is_generated_recruit(actor) and actor.mainJob and JOB_IDS[actor.mainJob] then
        return 'recruit-' .. actor.mainJob;
    end
    return E.safe_file_stem(actor and actor.name);
end
-- Remove legacy per-job Recruit sheets from this launcher's personal config.
-- The launcher only updates addon code, so cleanup must happen on each client.
-- Never traverse jobs/ or characters/: those hold player and named Trust data.
function E.remove_recruit_sheets()
    local root=E.root();
    if not root then return false,'Ashita install path unavailable'; end
    local base=root..'recruits/';
    local removed=0;
    local function remove_name(name)
        if type(name)~='string' then return; end
        name=name:gsub('\\','/'):match('([^/]+)$');
        local job,suffix=name:match('^([A-Z]+)%.lua(.*)$');
        if not job or not JOB_IDS[job] or JOB_IDS[job]>18 or
            (suffix~='' and suffix~='.bak' and not suffix:match('^%.pre%-migration%-[%d%-]+$')) then return; end
        local path=base..name;
        local safe=E.personal_path_guard(path);
        if not safe then return; end
        local file=io.open(path,'rb');
        if not file then return; end
        file:close();
        local ok,err=os.remove(path);
        if ok then removed=removed+1;
        else E.log('Recruit sheet cleanup failed for '..name..': '..tostring(err),true); end
    end
    for i=1,18 do
        local job=JOBS[i];
        remove_name(job..'.lua');
        remove_name(job..'.lua.bak');
    end
    if ashita and ashita.fs and type(ashita.fs.get_directory)=='function' then
        local ok,entries=pcall(ashita.fs.get_directory,base,'*',false);
        if ok and type(entries)=='table' then
            for key,value in pairs(entries) do
                if type(value)=='string' then remove_name(value);
                elseif type(value)=='table' then remove_name(value.name or value.Name or value.path or value.Path);
                elseif type(key)=='string' then remove_name(key); end
            end
        end
    end
    for key,slot in pairs(S.guestProfiles) do
        if slot.generatedJob then S.guestProfiles[key]=nil; end
    end
    if removed>0 then E.log('Removed '..removed..' obsolete Recruit Gambit sheet(s) from this launcher.',true); end
    return true,removed;
end
-- Highest tier first, then the stronger elemental spells within that tier.
-- The client checks level and observed MP; server recast validation remains final.
local HIGHEST_AVAILABLE_NUKES={
    'Thunder IV','Blizzard IV','Fire IV','Aero IV','Water IV','Stone IV',
    'Thunder III','Blizzard III','Fire III','Aero III','Water III','Stone III',
    'Thunder II','Blizzard II','Fire II','Aero II','Water II','Stone II',
    'Thunder','Blizzard','Fire','Aero','Water','Stone',
};
function E.guest_default_profile(actor)
    -- Named Trusts may still use their own sheets. Generated Recruit
    -- actions belong exclusively to the server and have no client defaults.
    return {Version=4,RangedPolicyVersion=1,Guest=actor and actor.name or 'Guest Trust',Enabled=true,Locked=true,Rules={}};
end
function E.guest_authored_default_profile(actor)
    return E.guest_default_profile(actor);
end
function E.guest_profile_validate(profile,actor)
    if type(profile)~='table' or type(profile.Rules)~='table' then return nil,'Guest profile must contain Rules = { ... }'; end
    if E.is_generated_recruit(actor) then
        for _,rule in ipairs(profile.Rules) do
            if rule.Type=='attack' then return nil,'Generated recruits attack automatically with their leader'; end
        end
    end
    profile.Job='GUEST';
    local valid,err=E.profile_validate(profile,'GUEST');
    if not valid then return nil,err; end
    valid.Guest=valid.Guest or (actor and actor.name) or 'Guest Trust';
    if E.is_generated_recruit(actor) then
        valid.Guest='Recruit '..actor.mainJob;
        valid.RangedPolicyVersion=1;
    end
    valid.Locked=true;
    return valid;
end

function E.recruit_ranged_policy_rules(actor,rules,policyVersion)
    local retained={}; local changed=false;
    local generated=E.is_generated_recruit(actor);
    local authorized=generated and E.contains({'THF','RNG','COR'},actor.mainJob);
    for _,rule in ipairs(rules or {}) do
        if generated and rule.Type=='ranged' and not authorized then
            changed=true;
        elseif generated and rule.Type=='ranged' and authorized and
            E.number(policyVersion,0)<1 and rule.Enabled~=false then
            local disabled=E.clone(rule);
            disabled.Enabled=false;
            retained[#retained+1]=disabled;
            changed=true;
        else
            retained[#retained+1]=rule;
        end
    end
    return retained,changed;
end
function E.recruit_whm_area_buff_rules(actor,rules)
    if not E.is_generated_recruit(actor) or actor.mainJob~='WHM' then return rules,false; end
    local migrated={}; local changed=false;
    for _,rule in ipairs(rules or {}) do
        local family=rule.Id=='recruit-whm-protectra' and 'Protectra'
            or (rule.Id=='recruit-whm-shellra' and 'Shellra' or nil);
        local first=type(rule.Actions)=='table' and rule.Actions[1] or rule.Action;
        if family and rule.Type=='spell' and rule.Target=='self' and
            type(first)=='string' and first:match('^'..family) then
            local updated=E.clone(rule);
            updated.Target='party_any';
            updated.Range=math.min(E.number(rule.Range,10) or 10,10);
            migrated[#migrated+1]=updated;
            changed=true;
        else
            migrated[#migrated+1]=rule;
        end
    end
    return migrated,changed;
end
function E.backup_profile_text(path,text)
    local safe,why=E.personal_path_guard(path);
    if not safe then return false,why; end
    if type(text)~='string' then return false,'Original profile text unavailable'; end
    local base=path..'.pre-migration-'..os.date('%Y%m%d-%H%M%S');
    local backup=base;
    local counter=0;
    while E.readfile(backup)~=nil do
        counter=counter+1;
        if counter>1000 then return false,'No unused backup name'; end
        backup=base..'-'..counter;
    end
    local file,err=io.open(backup,'wb');
    if not file then return false,err; end
    local wrote,writeError=file:write(text);
    local closed=file:close();
    if not wrote or not closed then os.remove(backup); return false,writeError or 'Backup close failed'; end
    return true,backup;
end

function E.guest_profile_load(ctx,actor,force)
    if not ctx or not ctx.self or not actor or not actor.name or not S.identity then return nil,'No requester or Guest actor'; end
    local generated=E.is_generated_recruit(actor);
    if generated then
        E.remove_recruit_sheets();
        return {Version=4,Guest='Recruit '..tostring(actor.mainJob),Enabled=false,Locked=true,Rules={}};
    end
    local key=E.guest_profile_key(actor);
    local base=generated and (E.root() .. 'recruits/') or (E.root() .. 'characters/' .. S.identity .. '/guests/');
    local path=base .. (generated and actor.mainJob or key) .. '.lua';
    if not force and S.guestProfiles[key] and S.guestProfiles[key].path==path then return S.guestProfiles[key].profile; end
    E.mkdir(base);
    local txt,readError=E.readfile(path);
    if not txt and not readError then
        local profile=E.guest_default_profile(actor);
        if generated then
            local legacyPath=E.root() .. 'characters/' .. S.identity .. '/guests/' .. E.safe_file_stem(actor.name) .. '.lua';
            local legacyText,legacyError=E.readfile(legacyPath);
            if legacyError then return nil,legacyError; end
            if legacyText then
                local err;
                profile,err=E.parse(legacyText,legacyPath);
                if not profile then return nil,'Legacy Recruit sheet rejected: '..tostring(err); end
                E.log('Imported '..actor.mainJob..' Recruit rules into the shared local job sheet. The named original remains unchanged.',true);
            end
        end
        if generated then profile.Guest='Recruit '..actor.mainJob; end
        local ok,data=E.writefile(path,profile,'Guest Trust Gambits. Generated recruits start with editable job rules.');
        if not ok then return nil,tostring(data); end
        txt=data;
    end
    local value,err=E.parse(txt,path);
    if value and type(value.Rules)=='table' then
        local retained={}; local removed=false;
        for _,rule in ipairs(value.Rules) do
            if E.is_generated_recruit(actor) and rule.Type=='attack' then removed=true;
            else retained[#retained+1]=rule; end
        end
        local rangedChanged;
        retained,rangedChanged=E.recruit_ranged_policy_rules(actor,retained,value.RangedPolicyVersion);
        removed=removed or rangedChanged;
        local whmBuffChanged;
        retained,whmBuffChanged=E.recruit_whm_area_buff_rules(actor,retained);
        removed=removed or whmBuffChanged;
        local originalCount=#retained;
        local overLimit=originalCount>MAX_GAMBIT_ROWS;
        if removed or overLimit or (E.is_generated_recruit(actor) and E.number(value.Version,0)<4) then
            for i=#retained,MAX_GAMBIT_ROWS+1,-1 do retained[i]=nil; end
            value.Rules=retained; value.Version=4; value.RangedPolicyVersion=1;
            local backed,backupError=E.backup_profile_text(path,txt);
            if not backed then return nil,'Migration backup failed: '..tostring(backupError); end
            local ok,newText=E.writefile(path,value,'Guest Trust Gambits. Maximum 14 ordered rows.');
            if not ok then return nil,tostring(newText); end
            txt=newText;
            if overLimit then E.log('This Trust sheet had '..originalCount..' rows. Kept rows 1-14; the original was backed up beside the sheet.',true); end
        end
    end
    if value then value,err=E.guest_profile_validate(value,actor); end
    if not value then return nil,readError or err; end
    if E.number(value.Version,0)<3 then
        value.Version=3;
        local backed,backupError=E.backup_profile_text(path,txt);
        if not backed then return nil,'Migration backup failed: '..tostring(backupError); end
        local ok,newText=E.writefile(path,value,'Guest Trust Gambits. Legacy rules preserved during migration.');
        if ok then txt=newText; else return nil,tostring(newText); end
    end
    S.guestProfiles[key]={path=path,profile=value,generatedJob=generated and actor.mainJob or nil};
    S.guestProfileText[path]=txt;
    return value;
end
function E.guest_profile_save(key)
    local slot=S.guestProfiles[key];
    if not slot or not slot.profile or not slot.path then return false,'No valid Guest profile'; end
    local disk=E.readfile(slot.path);
    if disk~=S.guestProfileText[slot.path] then return false,'Guest profile changed externally. Use /autobox reload before saving.'; end
    local valid,err=E.guest_profile_validate(E.clone(slot.profile),
        {name=slot.profile.Guest or key,mainJob=slot.generatedJob,generatedRecruit=slot.generatedJob~=nil});
    if not valid then return false,err; end
    local ok,txt=E.writefile(slot.path,valid,'Guest Trust Gambits. Configurable personality sheet.');
    if ok then
        slot.profile=valid; S.guestProfileText[slot.path]=txt;
        if slot.generatedJob then
            -- Reset action control after a sheet edit. Native melee follows
            -- the leader independently of the editable action rules.
            local ctx=E.context('generated-recruit-rule-edit');
            for _,actor in ipairs((ctx and ctx.party) or {}) do
                if actor.mainJob==slot.generatedJob and E.is_generated_recruit(actor) then
                    E.submit_guest_control(ctx,actor,false,true);
                end
            end
        end
        return true;
    end
    E.log('Guest profile save failed: '..tostring(txt),true); return false,txt;
end
function E.profile_has_enabled_gambits(profile)
    if not profile or profile.Enabled==false or type(profile.Rules)~='table' then return false; end
    for _,rule in ipairs(profile.Rules) do
        if rule and rule.Empty~=true and rule.Enabled~=false then return true; end
    end
    return false;
end
function E.guest_actor_has_enabled_gambits(ctx,actor)
    local profile=E.guest_profile_load(ctx,actor,false);
    return E.profile_has_enabled_gambits(profile);
end
function E.guest_apply_defaults()
    local key=E.active_guest_key();
    if not key then return false,'Select a Guest Trust first.'; end
    local slot=S.guestProfiles[key];
    if not slot or not slot.profile or not slot.path then return false,'No valid Guest profile'; end
    local actor={name=slot.profile.Guest or S.ui.selectedActorName or key,
        mainJob=slot.generatedJob,generatedRecruit=slot.generatedJob~=nil};
    local original=slot.profile;
    slot.profile=E.guest_default_profile(actor);
    local ok,err=E.guest_profile_save(key);
    if ok then S.ui.selected=1; S.ui.edits={}; E.flash_sheet(); return true; end
    slot.profile=original;
    return false,err;
end
function E.profile_save()
    if not S.profile or not S.profilePath or S.profileError then return false,'No valid current job profile'; end
    -- Reject an unseen external edit rather than overwriting it with an old UI snapshot.
    local disk=E.readfile(S.profilePath);
    if disk~=S.profileText then return false,'Profile changed externally. Use /autobox reload before saving.'; end
    local valid,err=E.profile_validate(E.clone(S.profile),S.profile.Job);
    if not valid then return false,err; end
    local ok,txt=E.writefile(S.profilePath,valid,'Ordered rules. Array order is execution priority.');
    if ok then S.profile=valid; S.profileText=txt; return true; end
    E.log('Profile save failed: '..tostring(txt),true); return false,txt;
end

-- Packet observation only. All offsets below are zero-based, including the header.
function E.u8(data,offset)
    if type(data)~='string' or offset<0 or offset>=#data then return nil; end
    return data:byte(offset+1);
end
function E.uint(data,offset,bytes)
    if type(data)~='string' or offset<0 or offset+bytes>#data then return nil; end
    local n=0;
    for i=0,bytes-1 do n=n+data:byte(offset+i+1)*2^(8*i); end
    return n;
end
function E.bits(data,start,count)
    if type(data)~='string' or start<0 or count<0 or count>32 or start+count>#data*8 then return nil; end
    local n=0;
    for i=0,count-1 do
        local b=start+i;
        n=n+(math.floor(data:byte(math.floor(b/8)+1)/2^(b%8))%2)*2^i;
    end
    return n;
end
function E.action_packet(data)
    if type(data)~='string' or #data<19 then return nil; end
    local p={actor=E.uint(data,5,4),category=E.bits(data,82,4),param=E.bits(data,86,16),targets={}};
    local count=E.bits(data,72,10); if not count or count>64 then return nil; end
    local pos=150;
    for i=1,count do
        local id=E.bits(data,pos,32); local actions=E.bits(data,pos+32,4); pos=pos+36;
        if not id or not actions then return nil; end
        local target={id=id,actions={}};
        for j=1,actions do
            local action={param=E.bits(data,pos+27,17),message=E.bits(data,pos+44,10)};
            local additional=E.bits(data,pos+85,1);
            if not action.param or not action.message or additional==nil then return nil; end
            pos=pos+86;
            if additional==1 then
                action.addParam=E.bits(data,pos+10,17);
                action.addMessage=E.bits(data,pos+27,10);
                pos=pos+37;
            end
            local spikes=E.bits(data,pos,1); if spikes==nil then return nil; end
            pos=pos+1;
            if spikes==1 then
                action.spikesParam=E.bits(data,pos+10,14);
                action.spikesMessage=E.bits(data,pos+24,10);
                pos=pos+34;
            end
            if pos>#data*8 then return nil; end
            target.actions[#target.actions+1]=action;
        end
        p.targets[#p.targets+1]=target;
    end
    return p;
end
-- The utility panes observe native packets. They never submit combat actions.
local WATCH_WINDOW_SECONDS = 3600;
-- One damage bucket per actor per second bounds a full alliance to about
-- 18 * 3600 entries, even when many hits arrive during the same second.
local WATCH_EVENT_LIMIT = 72000;
local DIRECT_DAMAGE_MESSAGE = {
    [1]=true,[2]=true,[67]=true,[77]=true,[110]=true,[157]=true,
    [185]=true,[187]=true,[197]=true,[227]=true,[252]=true,
    [264]=true,[274]=true,[281]=true,[317]=true,[352]=true,[353]=true,
};
local ADDITIONAL_DAMAGE_MESSAGE = {[161]=true,[163]=true,[229]=true};
function E.watch_queue(kind)
    local watch=S.watch;
    if not watch[kind] or not watch[kind].events then
        watch[kind]={events={},head=1,totals={},buckets={}};
    end
    return watch[kind];
end
function E.watch_prune(kind,now)
    local q=E.watch_queue(kind);
    while q.head<=#q.events and (q.events[q.head].at<=now-WATCH_WINDOW_SECONDS
        or #q.events-q.head+1>WATCH_EVENT_LIMIT) do
        local expired=q.events[q.head];
        if kind=='damage' and expired and q.totals then
            q.totals[expired.actor]=(q.totals[expired.actor] or 0)-expired.amount;
            if q.totals[expired.actor]<=0 then q.totals[expired.actor]=nil; end
            q.buckets[tostring(expired.actor)..':'..tostring(expired.second)]=nil;
        end
        q.events[q.head]=false;
        q.head=q.head+1;
    end
    if q.head>1024 and q.head>#q.events/2 then
        local compact={};
        for i=q.head,#q.events do compact[#compact+1]=q.events[i]; end
        q.events=compact; q.head=1;
    end
end
function E.watch_add(kind,event)
    local q=E.watch_queue(kind);
    event.at=E.now();
    if kind=='damage' then
        event.second=math.floor(event.at);
        local key=tostring(event.actor)..':'..tostring(event.second);
        local bucket=q.buckets[key];
        if bucket then
            bucket.amount=bucket.amount+event.amount;
        else
            q.buckets[key]=event;
            q.events[#q.events+1]=event;
        end
        q.totals=q.totals or {};
        q.totals[event.actor]=(q.totals[event.actor] or 0)+event.amount;
    else
        q.events[#q.events+1]=event;
    end
    E.watch_prune(kind,event.at);
end
function E.watch_roster(ctx)
    if not ctx or not ctx.self then return; end
    if S.watch.actor and S.watch.actor~=ctx.self.id then
        S.watch.damage={}; S.watch.exp={}; S.watch.expDisplay=nil; S.watch.enemyCache={}; S.watch.enemy=nil;
    end
    S.watch.actor=ctx.self.id;
    local roster={};
    for _,member in ipairs(ctx.party or {}) do
        if member.id and member.name and member.mainJob and
            (member.index==0 or E.is_generated_recruit(member) or not E.is_known_guest_name(member.name)) then
            roster[member.id]={name=member.name,job=member.mainJob,
                role=E.member_matches_target_role(member,'party_pool_tank') and 'tank'
                    or (E.member_matches_target_role(member,'party_pool_support') and 'support' or 'dps'),
                recruit=E.is_generated_recruit(member)};
        end
    end
    S.watch.roster=roster;
end
function E.watch_enemy_target(targetId,entityMemory)
    if not targetId or targetId<=0 or not entityMemory then return false; end
    local index=targetId%4096;
    if index>0x8ff or E.call(entityMemory,'GetServerId',index)~=targetId then return false; end
    local flags=E.call(entityMemory,'GetSpawnFlags',index);
    return type(flags)=='number' and math.floor(flags/16)%2==1;
end
function E.watch_action(action)
    local actor=S.watch.roster[action.actor];
    if not actor then return; end
    local mem=E.call(AshitaCore,'GetMemoryManager');
    local entities=E.call(mem,'GetEntity');
    for _,target in ipairs(action.targets or {}) do
        if E.watch_enemy_target(target.id,entities) then
            for _,result in ipairs(target.actions or {}) do
                local damage=0;
                if DIRECT_DAMAGE_MESSAGE[result.message] then damage=damage+(result.param or 0); end
                if ADDITIONAL_DAMAGE_MESSAGE[result.addMessage] then damage=damage+(result.addParam or 0); end
                if damage>0 then E.watch_add('damage',{actor=action.actor,amount=damage}); end
            end
        end
    end
end
function E.watch_exp_packet(data)
    if type(data)~='string' or #data<26 then return; end
    local target=E.uint(data,8,4);
    if not S.watch.actor or target~=S.watch.actor then return; end
    local amount=E.uint(data,16,4);
    local sourceCode=E.uint(data,20,4);
    local message=E.uint(data,24,2);
    if not amount or amount<=0 or amount>1000000 then return; end
    if message==8 or message==253 or message==371 or message==372 then
        local source=(message==253 or message==372) and 'monster' or
            (({[1]='fov',[2]='gov',[3]='other'})[sourceCode] or 'monster');
        E.watch_add('exp',{source=source,amount=amount,limit=(message==371 or message==372),
            chain=(message==253 or message==372)});
    end
end
function E.watch_enemy_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local nonce,id,zone,index,pool,drop,family,level=text:match('TGEN|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)');
    if nonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(id) and enemy.nonce==tonumber(nonce) and enemy.zone==tonumber(zone) then
            enemy.index=tonumber(index); enemy.pool=tonumber(pool);
            enemy.drop=tonumber(drop); enemy.family=tonumber(family); enemy.level=tonumber(level);
        end
        return true;
    end
    local missingNonce,missingId=text:match('TGEN|(%d+)|(%d+)|!');
    if missingNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(missingId) and enemy.nonce==tonumber(missingNonce) then enemy.unavailable=true; end
        return true;
    end
    local metaNonce,metaId,minLevel,maxLevel,respawn,detection,aggro,link,trueDetection,scentDisabled,dynamicDrops,noDrops=
        text:match('TGEM|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)');
    if metaNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(metaId) and enemy.nonce==tonumber(metaNonce) then
            enemy.minLevel=tonumber(minLevel); enemy.maxLevel=tonumber(maxLevel);
            enemy.respawn=tonumber(respawn); enemy.detection=tonumber(detection);
            enemy.aggro=aggro=='1'; enemy.link=link=='1';
            enemy.trueDetection=trueDetection=='1'; enemy.scentDisabled=scentDisabled=='1';
            enemy.dynamicDrops=dynamicDrops=='1';
            enemy.noDrops=noDrops=='1';
        end
        return true;
    end
    local slotNonce,slotId,memberId,chance=text:match('TGPS|(%d+)|(%d+)|(%d+)|(%d+)');
    if slotNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(slotId) and enemy.nonce==tonumber(slotNonce) then
            enemy.slots=enemy.slots or {};
            enemy.slots[#enemy.slots+1]={id=tonumber(memberId),chance=tonumber(chance)};
        end
        return true;
    end
    local lootNonce,lootId,itemId,dropType,itemRate,fixed,group,groupRate,groupFixed=
        text:match('TGLT|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)');
    if lootNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(lootId) and enemy.nonce==tonumber(lootNonce) then
            enemy.drops=enemy.drops or {};
            enemy.drops[#enemy.drops+1]={itemId=tonumber(itemId),dropType=tonumber(dropType),
                itemRate=tonumber(itemRate),fixed=fixed=='1',group=tonumber(group),
                groupRate=tonumber(groupRate),groupFixed=groupFixed=='1'};
        end
        return true;
    end
    local rateNonce,rateId,rowIndex,rates=text:match('TGLR|(%d+)|(%d+)|(%d+)|([%d,]+)');
    if rateNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(rateId) and enemy.nonce==tonumber(rateNonce) then
            local row=enemy.drops and enemy.drops[tonumber(rowIndex)];
            if row then
                row.thRates={};
                for value in rates:gmatch('%d+') do row.thRates[#row.thRates+1]=tonumber(value); end
                if #row.thRates~=15 then row.thRates=nil; end
            end
        end
        return true;
    end
    local endNonce,endId,count=text:match('TGLEND|(%d+)|(%d+)|(%d+)');
    if endNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(endId) and enemy.nonce==tonumber(endNonce) then
            enemy.lootCount=tonumber(count); enemy.complete=true;
            S.watch.enemyCache[tostring(enemy.zone)..':'..tostring(enemy.id)]={
                index=enemy.index,pool=enemy.pool,drop=enemy.drop,family=enemy.family,
                level=enemy.level,minLevel=enemy.minLevel,maxLevel=enemy.maxLevel,
                respawn=enemy.respawn,detection=enemy.detection,aggro=enemy.aggro,
                link=enemy.link,trueDetection=enemy.trueDetection,scentDisabled=enemy.scentDisabled,
                dynamicDrops=enemy.dynamicDrops,noDrops=enemy.noDrops,slots=enemy.slots,drops=enemy.drops,
                lootCount=enemy.lootCount,complete=true};
        end
        return true;
    end
    local liveNonce,liveId,hp,maxHp,mp,maxMp,th=text:match('TGEL|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)|(%d+)');
    if liveNonce then
        local enemy=S.watch.enemy;
        if enemy and enemy.id==tonumber(liveId) and enemy.nonce==tonumber(liveNonce) then
            enemy.hp=tonumber(hp); enemy.maxHp=tonumber(maxHp);
            enemy.mp=tonumber(mp); enemy.maxMp=tonumber(maxMp);
            enemy.th=tonumber(th); enemy.liveAt=E.now();
        end
        return true;
    end
    return false;
end
function E.watch_enemy_poll(ctx,now)
    if S.watch.tab~='ENEMY INFO' then return; end
    local target=ctx and ctx.target;
    if not target or not target.isMonster or not ctx.self then S.watch.enemy=nil; return; end
    local enemy=S.watch.enemy;
    if not enemy or enemy.id~=target.id or enemy.zone~=ctx.zone then
        local cached=S.watch.enemyCache[tostring(ctx.zone)..':'..tostring(target.id)] or {};
        enemy={id=target.id,zone=ctx.zone,name=target.name,index=target.entityIndex,
            nonce=math.random(1,999999999),staticRequested=false,liveAt=0,drops={},slots={}};
        for key,value in pairs(cached) do enemy[key]=value; end
        S.watch.enemy=enemy;
    end
    enemy.name=target.name;
    enemy.hpp=target.hpp;
    if enemy.staticRequested and not enemy.complete and now-(enemy.staticRequestedAt or now)>5 then
        enemy.staticRequested=false; enemy.drops={}; enemy.slots={};
    end
    if not enemy.complete and not enemy.staticRequested and now-(S.watch.enemyRequestAt or 0)>=1 then
        if E.send_bridge_command(string.format('!gambit enemy %u %u',enemy.id,enemy.nonce),true,
            {origin='enemy_info',targetId=enemy.id}) then
            enemy.staticRequested=true; enemy.staticRequestedAt=now; S.watch.enemyRequestAt=now;
        end
    elseif enemy.complete and now-(enemy.liveAt or 0)>=3 and now-(enemy.liveRequestedAt or 0)>=3 then
        if E.send_bridge_command(string.format('!gambit enemy-live %u %u',enemy.id,enemy.nonce),true,
            {origin='enemy_info_live',targetId=enemy.id}) then enemy.liveRequestedAt=now; end
    end
end
function E.party_packet(data)
    if type(data)~='string' or #data<4+5*48 then return false; end
    local now=E.now();
    for i=0,4 do
        local base=4+i*48;
        local id=E.uint(data,base,4); local index=E.uint(data,base+4,2);
        if id and id>0 and index and index>0 then
            local ids={};
            for j=0,31 do
                local high=math.floor(E.u8(data,base+8+math.floor(j/4))/2^((j%4)*2))%4;
                local buff=E.u8(data,base+16+j)+high*256;
                if buff~=255 and buff~=1023 then ids[#ids+1]=buff; end
            end
            S.buffs[id]={ids=ids,entityIndex=index,time=now};
        end
    end
    return true;
end
function E.availability_packet(data)
    if type(data)~='string' or #data<0xC4 then return false; end
    local sets={ws={},ability={},pet={}};
    for _,entry in ipairs({{'ws',4},{'ability',0x44},{'pet',0x84}}) do
        for id=0,511 do
            if math.floor(E.u8(data,entry[2]+math.floor(id/8))/2^(id%8))%2==1 then sets[entry[1]][id]=true; end
        end
    end
    S.availability=sets; return true;
end
function E.reset_runtime(reason)
    S.pending=nil; S.pendingByActor={}; S.actorLocks={}; S.outgoingIntent=nil; S.itemTransfer=nil; S.uncertain={};
    S.control={}; S.controlState={}; S.controlActors={}; S.controlPending={}; S.bridgeSubmitted={}; S.lastBridgeSpeech=nil;
    S.timers={}; S.buffs={}; S.casts={}; S.failures={};
    S.recastByActor={}; S.recastRequest=nil; S.recastPollAt=-10;
    S.statusSnapshots={}; S.statusRequest=nil; S.statusPollAt=-10; S.candidateWhy={};
    S.recruitStances={};
    S.recruitCooldown=nil; S.recruitStatusNextAt=0; S.recruitStatusRequestedAt=0; S.recruitCommands={};
    S.recruitJobMask=0; S.recruitJobActor=nil;
    S.recruitSlotPending={};
    S.recruitSlotConfirmed={'tank','support','dps','dps','dps'};
    S.recruitSlotRoles={'tank','support','dps','dps','dps'};
    S.sortPending=nil; S.sortCommandAt=nil;
    S.optimizePending=nil; S.optimizeCommandAt=nil;
    S.recastTotals={}; S.recastLast={};
    S.guestProfiles={}; S.guestProfileText={}; S.catalog=nil; S.ui.edits={};
    S.availability=nil; S.teamLoad=nil; S.lastPosition=nil; S.stationarySince=nil; S.lastTick=-10;
    S.lockUntil=0; S.manualUntil=0; S.manualAction=nil; S.nextBackgroundBridgeAt=0; S.zoneUntil=E.now()+(S.settings or DEFAULT).ZoneDelaySeconds;
    S.lastBlock=reason or 'State reset';
end
function E.packet_in(e)
    local id=e.id; local data=e.data; local now=E.now();
    if id==0x00A or id==0x00B then E.reset_runtime('Zone transition'); return; end
    if id==0x02D then E.watch_exp_packet(data); return; end
    if (id==0x061 or id==0x01B) and now-(S.recruitStatusRequestedAt or 0)>=10 then S.recruitStatusNextAt=0; end
    if id==0x076 then E.party_packet(data); return; end
    if id==0x0AC then E.availability_packet(data); return; end
    if id==0x029 then
        if type(data)~='string' or #data<26 then return; end
        local actor=E.uint(data,4,4); local target=E.uint(data,8,4);
        local p=E.pending_for(actor);
        local message=E.uint(data,24,2)%32768;
        -- Known execution failures; unrelated EXP/chat/combat messages are ignored.
        local errors={ [4]=true,[5]=true,[12]=true,[16]=true,[17]=true,[18]=true,[29]=true,
            [34]=true,[35]=true,[36]=true,[40]=true,[47]=true,[48]=true,[49]=true,[55]=true,[56]=true,
            [71]=true,[72]=true,[78]=true,[84]=true,[87]=true,[88]=true,[89]=true,[90]=true,[91]=true,[92]=true,[94]=true,[111]=true };
        local pendingActor=p and (p.actorId or p.playerId);
        if p and p.sent and actor==pendingActor and (target==0 or target==pendingActor or target==p.targetId) and errors[message] then
            E.release('Server rejected/interrupted action (message '..message..')',true,actor,'message_'..message);
        end
        return;
    end
    if id~=0x028 then return; end
    local action=E.action_packet(data); if not action then return; end
    E.watch_action(action);
    -- A late native result can reconcile a request whose receipt/completion
    -- deadline expired. Match actor, category, action and target before release.
    local expectedCategory={ability=6,ws=3,item=5};
    for key,uncertain in pairs(S.uncertain) do
        local actionId=uncertain.kind=='ability' and (uncertain.actionId-512) or uncertain.actionId;
        if uncertain.actorId==action.actor and expectedCategory[uncertain.kind]==action.category
            and (action.param==actionId or action.param==uncertain.actionId) then
            for _,target in ipairs(action.targets or {}) do
                if target.id==uncertain.targetId then
                    S.uncertain[key]=nil;
                    E.log('Late Recruit action result reconciled: '..tostring(uncertain.name));
                    break;
                end
            end
        end
    end
    if action.category==8 then
        if action.param==28787 then S.casts[action.actor]=nil;
        else
            local first=action.targets[1] and action.targets[1].actions[1];
            local resource=first and E.call(E.call(AshitaCore,'GetResourceManager'),'GetSpellById',first.param);
            local duration=resource and E.number(resource.CastTime,8)*0.25 or 2;
            S.casts[action.actor]={untilTime=now+math.min(20,duration+0.3),id=first and first.param,
                name=resource and resource.Name and resource.Name[1]};
        end
    elseif action.category==4 then S.casts[action.actor]=nil; end
    local p=E.pending_for(action.actor);
    if not p then
        for _,candidate in pairs(S.pendingByActor) do
            if candidate.waitForPet and candidate.petId==action.actor then p=candidate; break; end
        end
    end
    if S.manualAction and action.actor==S.manualAction.playerId then
        local expected={spell=4,ws=3,item=5,ranged=2,ability=6};
        if action.category==expected[S.manualAction.kind]
            or ((action.category==8 or action.category==12) and action.param==28787) then
            S.manualAction=nil;
            S.manualUntil=math.min(S.manualUntil,now+(S.settings or DEFAULT).ManualPauseSeconds);
        end
    end
    if not p or not p.sent then return; end
    if action.actor~=(p.actorId or p.playerId) then
        if p.waitForPet and action.actor==p.petId and (action.category==11 or action.category==13) then
            local native=(p.resource.Id or 512)-512;
            if action.param==native or action.param==native+256 or action.param==p.resource.Id then
                E.release('Observed pet action completion',false,p.actorId);
            end
        end
        return;
    end
    if (action.category==8 or action.category==12) and action.param==28787 then
        E.release('Observed interruption',true,p.actorId,'interrupted'); return;
    end
    local expected={spell=4,ws=3,item=5,ranged=2,ability=6,pet=6};
    local matches=action.category==expected[p.kind];
    if matches and p.kind=='spell' then matches=action.param==p.resource.Index; end
    if matches and p.kind=='ws' then matches=action.param==p.resource.Id; end
    if matches and p.kind=='item' then matches=action.param==p.resource.Id; end
    if matches and (p.kind=='ability' or p.kind=='pet') then
        matches=action.param==(p.resource.Id-512) or action.param==p.resource.Id;
    end
    if matches then
        local foundTarget=false;
        for _,target in ipairs(action.targets or {}) do if target.id==p.targetId then foundTarget=true; break; end end
        if not foundTarget then return; end
    end
    if matches and p.waitForPet then p.acknowledged=true; p.deadline=math.max(p.deadline,now+8); return; end
    if matches then
        local failed=false;
        for _,t in ipairs(action.targets) do
            if t.id==p.targetId then
                for _,a in ipairs(t.actions) do
                    if E.contains({4,5,16,29,34,35,47,48,49,75,84,85,86,114},a.message) then failed=true; end
                end
            end
        end
        if not failed then E.mark_recruit_dia_observed(p,now); end
        if not failed then S.actionStats.completed=S.actionStats.completed+1; end
        E.release(failed and 'Observed unsuccessful action result' or 'Observed action completion',failed,p.actorId,failed and 'observed_result' or nil);
    end
end
function E.packet_out(e)
    if e.blocked then return; end
    local now=E.now(); local data=e.data;
    if e.id==0x037 then
        if S.pending and S.pending.kind=='item' then S.pending.sent=true;
        else S.manualUntil=math.max(S.manualUntil,now+5); end
        return;
    end
    if e.id==0x0B5 then
        -- Speech text begins at packet offset 0x06. Observe only the exact
        -- pending /say bridge request; an API call alone is not delivery.
        local speech=type(data)=='string' and #data>=7 and data:sub(7):match('^[^%z]*');
        if speech and speech:match('^!gambit%s+') then
            local full='/say '..speech;
            local matched=false;
            for _,entry in ipairs(S.bridgeSubmitted) do
                if entry.command==full and now-entry.time<5 then
                    E.bridge_trace('outgoing_speech',full,entry.meta); matched=true; break;
                end
            end
            if matched then S.lastBridgeSpeech={command=full,time=now};
            else E.bridge_trace('outgoing_unmatched',full,E.bridge_meta(full,false,{origin='packet_out'})); end
            for _,plan in pairs(S.pendingByActor) do
                if plan.serverBridge and plan.command=='/say '..speech and now-(plan.time or now)<3 then
                    if not plan.outgoingObserved then S.actionStats.outgoing=S.actionStats.outgoing+1; end
                    plan.outgoingObserved=true;
                    plan.sent=true; plan.delivery='outgoing';
                    break;
                end
            end
        end
        return;
    end
    if e.id~=0x01A or type(data)~='string' or #data<14 then return; end
    local category=E.uint(data,10,2); local actionId=E.uint(data,12,2); local targetId=E.uint(data,4,4);
    local kinds={[3]='spell',[7]='ws',[9]='ability',[16]='ranged'};
    local kind=kinds[category]; if not kind then return; end
    local p=S.pending; local own=false;
    if p and (p.kind==kind or (p.kind=='pet' and kind=='ability')) then
        local id=p.kind=='spell' and p.resource.Index or p.resource.Id;
        if (kind=='ability') and id then id=id-512; end
        own=(kind=='ranged' or id==actionId) and p.targetId==targetId and now-p.time<3;
    end
    if own then p.sent=true; S.outgoingIntent=nil; return; end
    if S.pending then E.release('Manual action superseded pending attempt',false); end
    local duration=3;
    if kind=='spell' then
        local res=E.call(E.call(AshitaCore,'GetResourceManager'),'GetSpellById',actionId);
        duration=(res and E.number(res.CastTime,8)*0.25 or 5)+1;
    elseif kind=='ranged' then duration=5; end
    S.manualUntil=math.max(S.manualUntil,now+duration+(S.settings or DEFAULT).ManualPauseSeconds);
    local playerId=E.call(E.call(E.call(AshitaCore,'GetMemoryManager'),'GetParty'),'GetMemberServerId',0);
    S.manualAction={kind=kind,playerId=playerId,deadline=now+math.min(90,duration*3+5)};
end
function E.prune(now)
    if now-S.historyTime<30 then return; end
    S.historyTime=now;
    local count=0;
    for key,value in pairs(S.timers) do
        if value<now-60 then S.timers[key]=nil; else count=count+1; end
    end
    if count>5000 then S.timers={}; E.log('Pruned unusually large timer cache'); end
    for id,b in pairs(S.buffs) do if now-b.time>3600 then S.buffs[id]=nil; end end
    for id,c in pairs(S.casts) do if c.untilTime<now then S.casts[id]=nil; end end
    for key,f in pairs(S.failures) do if now-f.time>600 then S.failures[key]=nil; end end
end
function E.evaluate_rules(ctx,rules,label)
    ctx.activeRules=rules;
    for i,rule in ipairs(rules or {}) do
        if i>MAX_GAMBIT_ROWS then break; end
        if rule.Empty~=true and not (ctx.generatedRecruit and rule.Type=='attack') then
            local ok,plan,reason=pcall(E.prepare,ctx,rule);
            if not ok then E.log((label or 'Rule')..' '..tostring(rule.Id)..' failed safely: '..tostring(plan)); reason='Rule error'; plan=nil; end
            if plan then
                if E.issue(ctx,plan) then return true; end
                reason='Live target changed or queue failed';
            end
            if rule.Enabled~=false then S.why[#S.why+1]={index=i,id=(label and (label..':'..rule.Id) or rule.Id),reason=reason or 'Not executable'}; end
        end
    end
    return false;
end
function E.evaluate_guest_profiles(ctx)
    if not ctx.settings or ctx.settings.TrustServerBridge==false then return false; end
    local leaderOk,leaderReason=E.trust_control_allowed(ctx);
    if not leaderOk then
        if ctx.settings.Debug then E.log(leaderReason or 'Trust Gambits disabled: not party leader.'); end
        return false;
    end
    local acted=false;
    for _,actor in ipairs(ctx.party or {}) do
        if E.is_controllable_guest_member(ctx,actor) and not E.is_generated_recruit(actor) and E.actor_enabled(ctx,actor) then
            local profile,err=E.guest_profile_load(ctx,actor,false);
            if E.profile_has_enabled_gambits(profile) then
                local actorCtx=E.actor_context(ctx,actor);
                if actorCtx and not E.guest_gate(actorCtx) and E.evaluate_rules(actorCtx,profile.Rules,actor.name or 'Guest') then acted=true; end
            elseif err and ctx.settings.Debug then
                E.log('Guest profile unavailable for '..tostring(actor.name)..': '..tostring(err));
            end
        end
    end
    return acted;
end
function E.pump(event,profileJob)
    local now=E.now();
    if now-S.lastTick<(S.settings or DEFAULT).TickSeconds then return false; end
    S.lastTick=now;
    E.sort_timeout();
    E.optimize_timeout();
    local poll=now-S.lastPoll>=(S.settings or DEFAULT).SettingsPollSeconds;
    if poll then S.lastPoll=now; E.settings_load(false); end
    local ctx=E.context(event,profileJob);
    E.watch_roster(ctx);
    E.watch_prune('damage',now);
    E.watch_prune('exp',now);
    E.watch_enemy_poll(ctx,now);
    if poll and ctx.self then E.actor_switch_load(ctx,true); end
    local signature=ctx.self and table.concat({ctx.self.id,ctx.zone or 0,ctx.mainJobId,ctx.subJobId,ctx.mainLevel,ctx.subLevel},':');
    if signature and signature~=S.signature then
        S.signature=signature; E.reset_runtime('Character/job/level changed');
        S.lastTick=now; poll=true;
    end
    E.sample_motion(ctx);
    if ctx.self and (poll or not S.profile) then E.profile_load(ctx,false); end
    for actorId,plan in pairs(S.pendingByActor) do
        if now>=(plan.deadline or 0) then
            if plan.serverBridge and not plan.sent then
                S.actionStats.uncertain=S.actionStats.uncertain+1;
                S.uncertain[plan.key]={actorId=plan.actorId,targetId=plan.targetId,kind=plan.kind,
                    actionId=plan.resource and plan.resource.Id,requestKind=plan.requestKind,
                    requestActionId=plan.requestActionId,nonce=plan.requestNonce,name=plan.name,at=now};
                E.release('No outgoing bridge packet or receipt observed',true,actorId);
            elseif plan.generatedRecruit and (plan.kind=='ability' or plan.kind=='ws' or plan.kind=='item') then
                S.actionStats.uncertain=S.actionStats.uncertain+1;
                S.uncertain[plan.key]={actorId=plan.actorId,targetId=plan.targetId,kind=plan.kind,
                    actionId=plan.resource and plan.resource.Id,requestKind=plan.requestKind,
                    requestActionId=plan.requestActionId,nonce=plan.requestNonce,name=plan.name,at=now};
                E.release('Recruit action result unobserved after '..tostring(plan.delivery or 'submission'),false,actorId);
            else E.release('No matching completion before timeout',true,actorId); end
        elseif ctx.zone~=plan.zone or E.call(ctx.entityMemory,'GetServerId',plan.actorIndex)~=actorId then
            E.release('Actor left or changed identity',true,actorId);
        end
    end
    E.prune(now);
    -- Only the player's Gambit sheet executes. Trust actions belong to server AI.
    local block=E.gate(ctx,false,true);
    S.lastBlock=block or 'Ready';
    if block then return false; end
    if E.process_team_load(ctx) then
        S.lastBlock='Loading saved team';
        return true;
    end
    S.why={};
    local acted=false;
    local playerBlock=E.gate(ctx);
    if not playerBlock and E.evaluate_rules(ctx,S.profile.Rules,nil) then acted=true; end
    if playerBlock and not acted then S.lastBlock=playerBlock; return false; end
    if acted then return true; end
    S.lastBlock='No executable rule'; return false;
end

-- Public compatibility entry points. Pre-action callbacks do not inject another action.
function E.selected_switch_actor(ctx)
    return ctx and ctx.self or nil;
end
function G.IsEnabled()
    E.settings_load(false);
    local ctx=E.context('switch-state');
    if S.configError or not ctx or not ctx.self then return false; end
    return E.actor_enabled(ctx,ctx.self);
end
function G.SetEnabled(enabled)
    local ctx=E.context('switch-change');
    if not ctx or not ctx.self then return false,'No player character'; end
    return E.actor_switch_set(ctx,ctx.self,enabled==true);
end
function G.Context(event,job) local c=E.context(event,job); E.sample_motion(c); return c; end
function G.Evaluate(event,job) return E.pump(event or 'external',job); end
function G.HandleDefault(job) return G.Evaluate('HandleDefault',job); end
function E.preaction()
    if not S.pending then S.manualUntil=math.max(S.manualUntil,E.now()+(S.settings or DEFAULT).ManualPauseSeconds); end
    return false;
end
function G.HandlePrecast(job) return E.preaction(); end
function G.HandleAbility(job) return E.preaction(); end
function G.HandleWeaponskill(job) return E.preaction(); end
function G.HandlePreshot(job) return E.preaction(); end
function G.RegisterProvider(name,fn)
    assert(type(name)=='string' and (type(fn)=='function' or fn==nil),'Provider requires name and function/nil');
    S.providers[name]=fn;
    S.catalog=nil; -- Provider capabilities may change what the editor can safely offer.
end
function E.active_guest_key()
    if S.ui.roleTab~='partyguest' then return nil; end
    local name=S.ui.selectedActorName or S.ui.trustPlaceholder;
    if not name or name=='' or name=='vacant' then return nil; end
    local ctx=E.context('guest-key');
    local actor=E.selected_guest_member(ctx);
    return E.guest_profile_key(actor or {name=name});
end
function E.ensure_guest_ui_profile()
    local ctx=E.context('guest-ui-profile');
    local actor=E.selected_guest_member(ctx) or
        {name=S.ui.selectedActorName or S.ui.trustPlaceholder or 'Guest Trust', id=S.ui.selectedActorId or 0};
    if S.ui.roleTab~='partyguest' then return nil,nil; end
    local key=E.guest_profile_key(actor);
    local profile,err=E.guest_profile_load(ctx,actor,false);
    return profile,key,err;
end
function E.active_profile()
    -- The editor and public rule APIs always address the player's job sheet.
    return S.profile,'player',nil;
end
function G.GetRules()
    local profile=E.active_profile();
    return profile and E.clone(profile.Rules) or {};
end
function G.SetRules(rules)
    local profile,kind,key=E.active_profile();
    if kind=='readonly' then return false,'This actor is read-only'; end
    if kind=='guest' then
        if not profile then return false,'No current Guest profile'; end
        local original=E.clone(profile);
        profile.Rules=E.compact_rules(rules);
        local ok,err=E.guest_profile_save(key);
        if not ok then
            for k in pairs(profile) do profile[k]=nil; end
            for k,v in pairs(original) do profile[k]=v; end
            if S.guestProfiles[key] then S.guestProfiles[key].profile=profile; end
        end
        return ok,err;
    end
    if not S.profile then return false,'No current profile'; end
    local original=E.clone(S.profile);
    S.profile.Rules=E.compact_rules(rules);
    local ok,err=E.profile_save(); if not ok then S.profile=original; end
    return ok,err;
end
function G.NotifyBlueSetChange(names)
    if type(names)~='table' or not S.profile then return false; end
    S.profile.BlueSet=E.clone(names); S.blueSetUntil=E.now()+60;
    return E.profile_save();
end
function G.PrintStatus(job)
    local ctx=E.context('status',job);
    E.log(string.format('v%s | Gambits %s | Job %s %s/%s %s | %s',
        tostring(addon.version),G.IsEnabled() and 'ON' or 'OFF',ctx.mainJob,ctx.mainLevel,ctx.subJob,ctx.subLevel,
        'LIVE'),true);
    local buffSource=(ctx.self and ctx.self.buffSource) or 'Unavailable';
    local profileVersion=(S.profile and E.number(S.profile.Version,0)) or 0;
    E.log('State: '..S.lastBlock..' | Last attempt: '..S.lastDecision,true);
    E.log('Status source: '..buffSource..' | Profile preset v'..tostring(profileVersion),true);
    if buffSource=='Unavailable' and S.buffProbe then E.log('Status probes: '..S.buffProbe,true); end
    if S.profilePath then E.log('Profile: '..S.profilePath,true); end
    if S.configError or S.profileError or S.switchError then E.log(tostring(S.configError or S.profileError or S.switchError),true); end
    local stats=S.actionStats;
    E.log(string.format('Actions this session: submitted %d, outgoing observed %d, server accepted %d, rejected %d, completed %d, uncertain %d',
        stats.submitted,stats.outgoing,stats.accepted,stats.rejected,stats.completed,stats.uncertain),true);
    for actorId,plan in pairs(S.pendingByActor) do
        E.log(string.format('Pending actor %s: %s, %.1fs, %s',tostring(actorId),tostring(plan.name),
            E.now()-(plan.time or E.now()),tostring(plan.delivery or 'queued')),true);
    end
end
function E.move(from,to)
    if not E.active_profile() then return false,'No current profile'; end
    local rules=G.GetRules();
    from=tonumber(from); to=tonumber(to);
    if not from or not to or from%1~=0 or to%1~=0 or from<1 or to<1 or from>#rules or to>#rules then return false,'Invalid row numbers'; end
    if rules[from] and rules[from].Empty==true then return false,'Cannot move an empty row'; end
    local r=table.remove(rules,from); table.insert(rules,to,r);
    local ok,err=G.SetRules(rules);
    if ok then S.ui.selected=to; S.ui.edits={}; S.ui.flashRow=to; S.ui.flashUntil=E.now()+0.65; end
    return ok,err;
end
function E.command(args)
    local sub=E.lower(args[1]);
    if sub=='' or sub=='ui' then S.ui.open[1]=not S.ui.open[1]; return true; end
    if sub=='on' or sub=='off' or sub=='toggle' then
        local enabled=sub=='on' or (sub=='toggle' and not G.IsEnabled());
        local ok,err=G.SetEnabled(enabled);
        E.log(ok and ('Master '..(enabled and 'ON' or 'OFF')) or tostring(err),true);
        return true;
    end
    if sub=='status' then G.PrintStatus(); return true; end
    if sub=='capabilities' then
        for _,name in ipairs({'EnemyHasMP','EnemyDispellableBuff','TrustCapabilities','SmartActionPolicy',
            'SkillchainWindow','MagicBurstWindow','StatusRemaining','PositionSafe'}) do
            E.log(name..': '..(type(S.providers[name])=='function' and 'adapter ready' or 'adapter unavailable'),true);
        end
        E.log('Generated Recruit Dispel uses a server-side effect check when EnemyDispellableBuff is unavailable.',true);
        return true;
    end
    if sub=='debug' then
        if args[2]~='on' and args[2]~='off' then E.log('Use /autobox '..sub..' on|off',true); return true; end
        local ok,err=E.settings_change('Debug',args[2]=='on');
        E.log(ok and (sub..' '..args[2]) or tostring(err),true); return true;
    end
    if sub=='mouse' then
        if args[2]~='on' and args[2]~='off' then E.log('Use /autobox mouse on|off. Off leaves the window visible but click-through.',true); return true; end
        local capture=args[2]=='on';
        local ok,err=E.settings_change('MouseCapture',capture);
        E.log(ok and ('Mouse capture '..(capture and 'ON' or 'OFF; use /autobox mouse on to edit the window')) or tostring(err),true);
        return true;
    end
    if sub=='pause' then
        S.pauseUntil=E.now()+math.max(1,math.min(86400,tonumber(args[2]) or 60)); E.log('Paused.',true); return true;
    end
    if sub=='resume' then S.pauseUntil=0; E.log('Pause cleared.',true); return true; end
    if sub=='reload' then
        E.settings_load(true); E.profile_load(E.context('reload'),true);
        S.guestProfiles={}; S.guestProfileText={}; S.catalog=nil;
        S.cache={}; S.ui.edits={}; E.log((S.configError or S.profileError) and 'Reload failed; see status.' or 'Configuration reloaded.',true); return true;
    end
    if sub=='save' then local ok,err=E.profile_save(); E.log(ok and 'Profile saved.' or tostring(err),true); return true; end
    if sub=='list' then
        for i,r in ipairs(G.GetRules()) do E.log(string.format('%d. [%s] %s',i,r.Enabled~=false and 'ON' or 'OFF',r.Id),true); end
        return true;
    end
    if sub=='why' then
        E.log('Gate: '..S.lastBlock,true);
        local query=E.lower(args[2]);
        local matches={};
        if query~='' and tonumber(query)==nil and query~='all' then
            for _,x in ipairs(S.why) do
                if E.lower(x.id):find(query,1,true) then matches[#matches+1]=x; end
            end
            if #matches==0 then E.log('No enabled rule matches "'..query..'".',true); return true; end
        else
            matches=S.why;
        end
        local page=math.max(1,math.floor(tonumber(query) or 1));
        local pageSize=query=='all' and #matches or 12;
        local first=query=='all' and 1 or (page-1)*pageSize+1;
        local last=math.min(#matches,first+pageSize-1);
        if first>#matches then
            E.log('No diagnostic page '..tostring(page)..'. '..tostring(#matches)..' enabled rules were evaluated.',true,true);
            return true;
        end
        for i=first,last do local x=matches[i]; E.log(x.id..': '..x.reason,true); end
        if query=='' and #matches>pageSize then
            E.log('Showing 1-'..tostring(last)..' of '..tostring(#matches)..'. Use /autobox why 2 or /autobox why <rule-id>.',true);
        elseif tonumber(query) and last<#matches then
            E.log('Showing '..tostring(first)..'-'..tostring(last)..' of '..tostring(#matches)..'. Use /autobox why '..tostring(page+1)..' for more.',true);
        end
        return true;
    end
    if sub=='enable' or sub=='disable' then
        local rules=G.GetRules(); local found=false;
        for i,r in ipairs(rules) do
            if r.Id==args[2] or i==tonumber(args[2]) then r.Enabled=sub=='enable'; found=true; break; end
        end
        local ok,err=false,'Rule not found'; if found then ok,err=G.SetRules(rules); end
        E.log(ok and 'Rule updated.' or tostring(err),true); return true;
    end
    if sub=='move' then local ok,err=E.move(args[2],args[3]); E.log(ok and 'Priority updated.' or tostring(err),true); return true; end
    if sub=='reset' then
        if args[2]~='confirm' then E.log('To replace ONLY this job profile, use /autobox reset confirm. A .bak is retained.',true); return true; end
        if not S.profile then E.log('No current profile.',true); return true; end
        local original=S.profile; S.profile=E.default_profile(S.profile.Job);
        local ok,err=E.profile_save(); if not ok then S.profile=original; end
        E.log(ok and 'Current job preset reset.' or tostring(err),true); return true;
    end
    if sub=='catalog' then S.ui.tab='Catalog'; S.ui.open[1]=true; return true; end
    E.log('Commands: /autobox [ui|on|off|toggle|status|capabilities|reload|save|why [page|rule-id|all]|list|catalog]',true);
    E.log('Options: debug on|off; mouse on|off; pause [seconds]; resume; enable|disable ID; move FROM TO; reset confirm',true);
    return true;
end
function E.open_utility_shortcut(command)
    local tab=({['/parser']='PARSER',['/exp']='EXP WATCH',['/info']='ENEMY INFO'})[E.lower(command)];
    if not tab then return false; end
    S.watch.tab=tab;
    S.ui.open[1]=true;
    return true;
end
function G.HandleCommand(args,job)
    if not args or #args==0 then return false; end
    local words={}; for i=1,#args do words[i]=tostring(args[i]); end
    if E.open_utility_shortcut(words[1]) then return true; end
    if E.contains({'/autobox','autobox'},E.lower(words[1])) then
        table.remove(words,1);
    end
    return E.command(words);
end
function E.command_event(e)
    if type(e.command)~='string' then return; end
    local line=e.command:gsub('^%s+',''):gsub('%s+$','');
    if line:match('^/say%s+!gambit%s+') or line:match('^!gambit%s+') then
        E.bridge_trace(e.blocked and 'command_preblocked' or 'command_seen',line,
            E.bridge_meta(line,false,{origin='command_event'}));
    end
    if e.blocked then return; end
    local first=E.lower(line:match('^(%S+)'));
    if S.recruitCommands and S.recruitCommands[line] and E.now()-S.recruitCommands[line]<5 then
        S.recruitCommands[line]=nil;
        return;
    end
    if line=='/say !optimize' and S.optimizeCommandAt and E.now()-S.optimizeCommandAt<5 then
        S.optimizeCommandAt=nil;
        return;
    end
    if line=='/say !sort' and S.sortCommandAt and E.now()-S.sortCommandAt<5 then
        S.sortCommandAt=nil;
        return;
    end
    local p=S.outgoingIntent;
    -- This exact queued command belongs to the pending plan. Do not turn it
    -- into player chat or a manual action before its live preflight.
    if p and line==p.command then
        local ctx=E.context('command-consumption');
        local valid,why=E.preflight_plan(ctx,p);
        if not valid or p.canceled then
            e.blocked=true;
            if E.pending_for(p.actorId) then E.release('Queued action canceled: '..tostring(why or 'disabled'),false,p.actorId);
            else E.clear_pending(p); end
        elseif p.kind=='attack' then
            S.outgoingIntent=nil;
        end
        return;
    end
    if first~='!gambit' and not line:match('^/say%s+!gambit%s+') then
        S.userChatUntil=E.now()+1.25;
    end
    if E.open_utility_shortcut(first) then e.blocked=true; return; end
    if E.contains({'/autobox'},first) then
        e.blocked=true;
        local words={}; for word in line:gmatch('%S+') do words[#words+1]=word; end
        table.remove(words,1); E.command(words); return;
    end
    if E.contains({'/ma','/magic','/ja','/jobability','/ws','/weaponskill','/pet','/ra','/range','/item'},first) then
        S.manualUntil=math.max(S.manualUntil,E.now()+(S.settings or DEFAULT).ManualPauseSeconds);
    end
end

-- Optional ImGui editor. The engine and slash commands also work without ImGui.
local imgui;
do
    local ok,mod=pcall(require,'imgui');
    if ok then imgui=mod; end
end
function E.notify_save(ok,err)
    if not ok then E.log('Change not saved: '..tostring(err),true); end
end
function E.catalog_add(out,seen,kind,action,id,extra)
    if not action or not E.safe_name(action) then return; end
    if kind=='spell' and (E.is_trust_spell_id(id) or E.is_trust_spell_name(action)) then return; end
    local key=tostring(kind)..':'..tostring(action);
    if seen[key] then return; end
    seen[key]=true;
    local entry={Type=kind,Action=action,Id=id or 0,MP=0,Targets=0};
    if type(extra)=='table' then for k,v in pairs(extra) do entry[k]=v; end end
    out[#out+1]=entry;
end
function E.catalog_add_rule_actions(out,seen,ctx,rule)
    if type(rule)~='table' or rule.Empty==true or not E.rule_job(ctx,rule) then return; end
    local kind=rule.Type;
    local actions=rule.Actions or (rule.Action and {rule.Action}) or {};
    if kind=='cure' then
        kind='spell';
        if #actions==0 then actions={'Cure VI','Cure V','Cure IV','Cure III','Cure II','Cure'}; end
    elseif kind=='ws_auto' then
        E.catalog_add(out,seen,'ws_auto','Best Weapon Skill',0);
        return;
    elseif kind=='ranged' then
        if not ctx.generatedRecruit or E.generated_recruit_ranged_allowed(ctx) then
            E.catalog_add(out,seen,'ranged','Ranged Attack',0);
        end
        return;
    elseif kind=='attack' then
        E.catalog_add(out,seen,'attack','Attack',0);
        return;
    end

    if kind~='spell' and kind~='ability' and kind~='pet' and kind~='ws' and kind~='item' then return; end
    for _,action in ipairs(actions) do
        local res=E.resource(ctx,kind,action);
        if kind=='spell' then
            if res and not E.is_trust_spell(res,action) and E.spell_level(ctx,res) then
                E.catalog_add(out,seen,kind,action,res.Index,{MP=res.ManaCost or 0,BlueMagic=res.Skill==43,Targets=res.Targets or 0});
            end
        elseif kind=='item' then
            E.catalog_add(out,seen,kind,action,res and (res.Id or res.Index) or 0,{Targets=res and res.Targets or 0});
        else
            if res and E.ability_known(ctx,res,kind) then
                E.catalog_add(out,seen,kind,action,res.Id or res.Index or 0,{Targets=res.Targets or 0});
            end
        end
    end
end
function E.catalog_add_guest_job_abilities(out,seen,ctx)
    for _,side in ipairs({
        {job=ctx.mainJob,level=math.min(E.number(ctx.mainLevel) or 0,75),sub=false},
        {job=ctx.subJob,level=math.min(E.number(ctx.subLevel) or 0,37),sub=true},
    }) do
        for _,entry in ipairs(JOB_ABILITY_CATALOG[side.job] or {}) do
            local name,level,mainOnly=entry[1],entry[2] or 1,entry[3] == true;
            if level<=side.level and not (side.sub and mainOnly) then
                local res=E.resource(ctx,'ability',name);
                if res then E.catalog_add(out,seen,'ability',name,res.Id or res.Index or 0,{Targets=res.Targets or 0}); end
            end
        end
    end
end
function E.catalog_add_guest_weapon_skills(out,seen,ctx)
    for _,action in ipairs(E.guest_ws_names(ctx) or {}) do
        local res=E.resource(ctx,'ws',action);
        if res then E.catalog_add(out,seen,'ws',action,res.Id or res.Index,{Targets=res.Targets or 0}); end
    end
end
function E.catalog_add_bard_songs(out,seen,ctx,actorKind)
    if ctx.mainJob~='BRD' and ctx.subJob~='BRD' then return; end
    for _,name in ipairs(BARD_SONG_CATALOG or {}) do
        local res=E.resource(ctx,'spell',name);
        if res and not E.is_trust_spell(res,name) and E.spell_level(ctx,res) then
            local id=res.Index or res.Id or 0;
            local available=false;
            if actorKind=='guest' then
                available=true;
            elseif E.truth(E.call(ctx.player,'HasSpell',id)) then
                available=true;
            end
            if available then
                E.catalog_add(out,seen,'spell',name,id,{MP=res.ManaCost or 0,Targets=res.Targets or 0});
            end
        end
    end
end
function E.catalog()
    local ctx,actorKind=E.editor_catalog_context(); local out={}; local seen={};
    if not ctx.player or not ctx.resources then return {}; end
    if actorKind=='guest' then
        local capabilities=E.trust_capabilities(ctx);
        if capabilities then
            for _,entry in ipairs(capabilities.Actions or {}) do
                if type(entry)=='table' and E.contains({'spell','ability','ws','ranged'},entry.Type)
                    and E.trust_permission(ctx,entry.Type,entry.Action)==true then
                    local res=entry.Type=='ranged' and {} or E.resource(ctx,entry.Type,entry.Action);
                    if res then E.catalog_add(out,seen,entry.Type,entry.Action,res.Index or res.Id or 0,{MP=res.ManaCost or 0,Targets=res.Targets or 0}); end
                end
            end
            table.sort(out,function(a,b) if a.Type~=b.Type then return a.Type<b.Type; end return a.Action<b.Action; end);
            S.catalog=out; return out;
        end
        if ctx.settings.RequireVerifiedTrustCapabilities and not ctx.generatedRecruit then S.catalog=out; return out; end
        for id=0,2047 do
            local res=E.call(ctx.resources,'GetSpellById',id);
            if res and res.Name and E.safe_name(res.Name[1]) and not E.is_trust_spell(res,res.Name[1],id) and E.spell_level(ctx,res) then
                E.catalog_add(out,seen,'spell',res.Name[1],id,{MP=res.ManaCost or 0,BlueMagic=res.Skill==43,Targets=res.Targets or 0});
            end
        end
        local mainProfile=G.Definitions[ctx.mainJob] and E.default_profile(ctx.mainJob) or nil;
        local subProfile=G.Definitions[ctx.subJob] and E.default_profile(ctx.subJob) or nil;
        for _,profile in ipairs({mainProfile,subProfile}) do
            for _,rule in ipairs((profile and profile.Rules) or {}) do
                E.catalog_add_rule_actions(out,seen,ctx,rule);
            end
        end
        E.catalog_add_bard_songs(out,seen,ctx,actorKind);
        E.catalog_add_guest_job_abilities(out,seen,ctx);
        E.catalog_add_guest_weapon_skills(out,seen,ctx);
        if E.generated_recruit_ranged_allowed(ctx) then
            E.catalog_add(out,seen,'ranged','Ranged Attack',0);
        end
    else
        for id=0,2047 do
            local res=E.call(ctx.resources,'GetSpellById',id);
            if res and res.Name and E.safe_name(res.Name[1]) and E.spell_level(ctx,res)
                and not E.is_trust_spell(res,res.Name[1],id)
                and E.truth(E.call(ctx.player,'HasSpell',id)) then
                E.catalog_add(out,seen,'spell',res.Name[1],id,{MP=res.ManaCost or 0,BlueMagic=res.Skill==43,Targets=res.Targets or 0});
            end
        end
        for id=0,1535 do
            local res=E.call(ctx.resources,'GetAbilityById',id);
            if res and res.Name and E.safe_name(res.Name[1]) then
                local kind;
                if id<512 and E.ability_known(ctx,res,'ws') then kind='ws';
                elseif id>=512 then
                    if E.ability_known(ctx,res,'ability') then kind='ability';
                    elseif E.ability_known(ctx,res,'pet') then kind='pet'; end
                end
                if kind then E.catalog_add(out,seen,kind,res.Name[1],id,{MP=res.ManaCost or 0,Targets=res.Targets or 0}); end
            end
        end
        E.catalog_add_bard_songs(out,seen,ctx,actorKind);
    end
    table.sort(out,function(a,b) if a.Type~=b.Type then return a.Type<b.Type; end return a.Action<b.Action; end);
    if actorKind=='guest' and ctx.catalogActorId and not ctx.generatedRecruit
        and not E.trust_capabilities(ctx) and not ctx.settings.RequireVerifiedTrustCapabilities
        and S.lastLegacyTrustCatalogWarning~=ctx.catalogActorName then
        E.log('Trust actions use an unverified legacy job catalog for '..tostring(ctx.catalogActorName)..'. Verified Trust unlocks require a TrustCapabilities provider.',true);
        S.lastLegacyTrustCatalogWarning=ctx.catalogActorName;
    end
    S.catalog=out; return out;
end
function E.catalog_has_action(catalog,kind,action,actions)
    for _,entry in ipairs(catalog or {}) do
        if kind=='ws_auto' and (entry.Type=='ws_auto' or entry.Type=='ws') then return true; end
        if entry.Type==kind then
            if action~=nil and entry.Action==action then return true; end
            if type(actions)=='table' and E.contains(actions,entry.Action) then return true; end
            if action==nil and actions==nil then return true; end
        end
    end
    return false;
end
function E.trust_action_option_allowed(ctx,opt,catalog)
    if not ctx then return false; end
    if ctx.catalogActorKind~='guest' then return opt and opt[2]~='item'; end
    local kind=opt and opt[2];
    local action=opt and opt[3];
    local actions=opt and opt[4];
    if kind=='ranged' and ctx.generatedRecruit then
        return E.generated_recruit_ranged_allowed(ctx);
    end
    if kind=='item' then return ctx.generatedRecruit and not RECRUIT_FOOD_ITEMS[action] and E.resource(ctx,kind,action)~=nil; end
    if kind=='pet' then return false; end
    if kind=='none' or kind=='attack' then return true; end
    if kind=='cure' then return E.catalog_has_action(catalog,'spell',nil,actions or {'Cure VI','Cure V','Cure IV','Cure III','Cure II','Cure'}); end
    if kind=='ws_auto' then return E.catalog_has_action(catalog,'ws_auto',nil,nil); end
    return E.catalog_has_action(catalog,kind,action,actions);
end
function E.empty_slot(position,used)
    local n=1;
    local base='empty-slot-'..tostring(position or 'x')..'-';
    while used and used[base..n] do n=n+1; end
    return {Id=base..n,Empty=true,Enabled=false};
end
function E.compact_rules(rules)
    local out={};
    for _,r in ipairs(rules or {}) do
        if type(r)=='table' and r.Empty~=true then out[#out+1]=E.clone(r); end
    end
    return out;
end
function E.trim_empty_tail(rules)
    while #rules>0 and rules[#rules] and rules[#rules].Empty==true do table.remove(rules); end
end
function E.real_rule_count(rules)
    local count=0;
    for _,r in ipairs(rules or {}) do if r and r.Empty~=true then count=count+1; end end
    return count;
end
function E.gambit_row_count(rules)
    local count=math.min(#rules,MAX_GAMBIT_ROWS);
    return count+(count<MAX_GAMBIT_ROWS and 1 or 0);
end
function E.gambit_row_is_add(rules,i)
    return #rules<MAX_GAMBIT_ROWS and i==#rules+1;
end
function E.new_rule_template(rule)
    if type(rule)~='table' or rule.Empty==true then return nil; end
    local out=E.clone(rule);
    out.Id=nil;
    out.Empty=nil;
    return out;
end
function E.remember_new_rule_template(rule)
    local profile=E.active_profile();
    local template=E.new_rule_template(rule);
    if profile and template then profile.LastNewRuleTemplate=template; end
end
function E.new_rule(entry,position)
    local profile,kind=E.active_profile();
    if not profile then return false; end
    local generated=kind=='guest' and type(profile.Guest)=='string'
        and profile.Guest:match('^Recruit ')~=nil;
    local rules=E.compact_rules(G.GetRules());
    if #rules>=MAX_GAMBIT_ROWS then E.notify_save(false,'Gambit sheets are limited to 14 rows'); return false; end
    local i=1; local used={};
    for _,r in ipairs(rules) do used[r.Id]=true; end
    while used['custom-'..i] do i=i+1; end
    local flags=entry and entry.Targets or 0;
    local target=math.floor(flags/32)%2==1 and 'enemy' or 'self';
    local requested=E.number(position);
    local insertAt;
    if requested then
        insertAt=math.max(1,math.min(requested,#rules+1));
    else
        insertAt=#rules+1;
    end
    local rule;
    if generated and ((entry and entry.Type=='attack') or (not entry and
        (type(profile.LastNewRuleTemplate)~='table' or
        profile.LastNewRuleTemplate.Type=='attack' or profile.LastNewRuleTemplate.Type=='none'))) then
        rule={Id='custom-'..i,Label='New Gambit',Enabled=false,
            Type='none',Action='Do Nothing',Target='self',Combat='any',Layer='utility'};
    elseif entry and not (generated and entry.Type=='attack') then
        rule={Id='custom-'..i,Label=entry.Action or 'Attack',Enabled=false,
            Type=entry.Type or 'attack',Action=entry.Action or 'Attack',
            Target=target,Property=nil,Operator=nil,
            Combat='combat',Cooldown=5,PerTargetCooldown=10,
            BlueMagic=entry.BlueMagic or false,Layer='utility'};
    elseif type(profile.LastNewRuleTemplate)=='table' and
        not (generated and (profile.LastNewRuleTemplate.Type=='attack' or
            profile.LastNewRuleTemplate.Type=='none')) then
        rule=E.clone(profile.LastNewRuleTemplate);
        rule.Id='custom-'..i;
        rule.Empty=nil;
        rule.Type=rule.Type or 'attack';
        rule.Action=rule.Action or (rule.Type=='attack' and 'Attack' or nil);
        rule.Target=rule.Target or 'enemy';
        rule.Combat=rule.Combat or 'combat';
        rule.Cooldown=rule.Cooldown or 5;
        rule.PerTargetCooldown=rule.PerTargetCooldown or 10;
        rule.Layer=rule.Layer or 'utility';
    else
        rule={Id='custom-'..i,Label='Attack',Enabled=true,
            Type='attack',Action='Attack',
            Target='enemy',Property='in_battle',Operator='yes',
            Combat='combat',Cooldown=5,PerTargetCooldown=10,
            BlueMagic=false,Layer='utility'};
    end
    table.insert(rules,insertAt,rule);
    local previousTemplate=profile.LastNewRuleTemplate;
    if rule.Type~='none' then E.remember_new_rule_template(rule); end
    local ok,err=G.SetRules(rules);
    if ok then
        S.ui.selected=insertAt; S.ui.edits={}; S.ui.tab='Gambits';
    else
        profile.LastNewRuleTemplate=previousTemplate;
        E.notify_save(ok,err);
    end
    return ok;
end
function E.buffer(key,value)
    if not S.ui.edits[key] then S.ui.edits[key]={value==nil and '' or tostring(value)}; end
    return S.ui.edits[key];
end
function E.join(value)
    if type(value)~='table' then return value==nil and '' or tostring(value); end
    local parts={}; for _,v in ipairs(value) do parts[#parts+1]=tostring(v); end
    return table.concat(parts,', ');
end
function E.split(value)
    local out={};
    for word in tostring(value):gmatch('[^,]+') do
        word=word:gsub('^%s+',''):gsub('%s+$','');
        if word~='' then out[#out+1]=word; end
    end
    return out;
end
function E.rule_action_text(rule)
    if not rule then return ''; end
    if rule.SmartActionLabel then return tostring(rule.SmartActionLabel); end
    if type(rule.Actions)=='table' and #rule.Actions>0 then return tostring(rule.Actions[1]); end
    if rule.Action then return tostring(rule.Action); end
    if rule.Type=='attack' then return 'Attack'; end
    if rule.Type=='ranged' then return 'Ranged Attack'; end
    if rule.Type=='ws_auto' then return 'Best Weapon Skill'; end
    return tostring(rule.Type or 'Action');
end
function E.rule_target_text(rule)
    local target=(rule and rule.Target) or 'self';
    local names={self='Self',owner='Owner',player='Player',master='Master',enemy='Enemy',foe='Current Target',ally='Any Party Member',
        party_member='Party Member',alliance_member='Ally Member',party_pool_tank='Any Tank (Party)',
        party_pool_support='Any Support (Party)',party_pool_dps='Any DPS (Party)',
        party_any='Any Party Member',party_leader='Party Leader',party_tank='Tank',party_healer='Healer',party_melee='Melee',
        party_ranged='Ranged',party_caster='Caster',party_support='Support',lowest='Lowest HP',mp='Lowest MP',
        lowest_hp_eligible_ally='Lowest HP Eligible Ally',eligible_lowest_hp='Lowest HP Eligible Ally',
        greatest_missing_hp_ally='Greatest Missing HP Ally',ally_with_removable_ailment='Ally With Removable Ailment',
        removable_ailment_ally='Ally With Removable Ailment',
        highest_tp='Highest TP',lowest_tp='Lowest TP',closest_ally='Closest Ally',furthest_ally='Furthest Ally',
        alliance_any='Alliance',alliance_tank='Alliance Tank',alliance_healer='Alliance Healer',
        alliance_lowest_hp='Alliance Lowest HP',alliance_lowest_mp='Alliance Lowest MP',specific_party='Party Member',
        specific_alliance='Alliance Member',specific_trust='Specific Trust',dead='KO Ally',dead_party='KO Party',dead_alliance='KO Alliance',
        status='Status Ally',statused_ally='Status Ally',debuffed_ally='Debuffed Ally',pet='Pet',party_pet='Party Pet',
        automaton='Automaton',wyvern='Wyvern',avatar='Avatar',luopan='Luopan',current_target='Current Target',
        player_target='Player Target',leader_target='Leader Target',tank_target='Tank Target',nearest_foe='Nearest Foe',
        lowest_hp_foe='Lowest HP Foe',highest_hp_foe='Highest HP Foe',add='Add',foe_targeting_self='Foe -> Self',
        foe_targeting_player='Foe -> Player',foe_targeting_healer='Foe -> Healer',foe_targeting_tank='Foe -> Tank',
        target_of_target='Target Of Target',current_enemy_victim='Current Enemy Victim',eligible_add_threatening_party='Eligible Add Threatening Party',
        nm='NM',boss='Boss',beastman='Beastman',undead='Undead',arcana='Arcana',dragon='Dragon'};
    return names[target] or tostring(target);
end
function E.status_condition_display(value)
    if type(value)=='number' then return 'selected ailment'; end
    if type(value)~='table' then return tostring(value); end
    local names={};
    for _,entry in ipairs(value) do
        if type(entry)=='string' then names[#names+1]=entry; end
    end
    if #names>0 then return table.concat(names,', '); end
    return 'selected ailments';
end
function E.rule_status_text(rule)
    if not rule then return 'Always'; end
    if rule.Property and rule.Property~='always' then
        local labels={hp_pct='Target: HP',hp_amount='Target: HP Amount',mp_pct='Target: MP',mp_amount='Target: MP Amount',tp='Target: TP',alive='Target: Alive',dead='Target: Dead',
            engaged='Target: Engaged',idle='Target: Idle',in_battle='In Battle',casting='Target: Casting',casting_magic='Target: Casting Magic',
            specific_spell='Target: Specific Spell',readying_tp_move='Enemy: Readying TP Move',specific_tp_move='Enemy: Specific TP Move',
            has_hate='Self: Has Hate',top_enmity='Self: Top Enmity',targeting='Enemy: Targeting',targeting_actor='Enemy: Targeting This Actor',
            distance='Target: Distance',melee_range='Target: Melee Range',ranged_range='Target: Ranged Range',preferred_ranged_distance='Target: Preferred Ranged Distance',
            outside_melee_range='Target: Outside Melee Range',has_mp='Target: Has MP',status_remaining='Target: Buff Remaining',status_count='Target: Status Count',
            party_count='Party: Count',matching_allies='Party: Matching Allies',matching_alliance='Alliance: Matching Members',
            role_present='Party: Role Present',job_present='Party: Job Present',healer_present='Party: Healer Present',tank_present='Party: Tank Present',
            enemy_count='Enemy: Count',skillchain='Battle: Skillchain Window',skillchain_property='Battle: Skillchain Property',
            skillchain_level='Battle: Skillchain Level',can_open_skillchain='Self: Can Open Skillchain',can_close_skillchain='Self: Can Close Skillchain',
            magic_burst_window='Battle: Magic Burst Window',magic_burst_element='Battle: Magic Burst Element',
            element='Enemy: Element',weakest_element='Enemy: Weakest Element',resists_element='Enemy: Resists Element',immune_element='Enemy: Immune Element',
            absorbs_element='Enemy: Absorbs Element',enemy_dispellable='Enemy: Dispellable Buff',family='Enemy: Family',
            nm_state='Enemy: NM State',job='Target: Job',role='Target: Role',level='Target: Level',difficulty='Enemy: Difficulty',day='World: Day',weather='World: Weather',
            ability_recast='Ability Recast',spell_recast='Spell Recast',item_count='Item Count',ammo_remaining='Ammo',
            position='Position',pet_present='Pet Present',pet_missing='Pet Missing',pet_idle='Pet Idle',pet_engaged='Pet Engaged',
            pet_hp_pct='Pet HP',pet_mp_pct='Pet MP',pet_tp='Pet TP',shadows='Shadows',rune_count='Rune Count',
            rune_element='Rune Element',finishing_moves='Finishing Moves',daze_level='Daze Level',samba='Samba',
            stratagem_charges='Stratagem Charges',arts='Arts',addendum='Addendum',active_song='Active Song',
            song_count='Song Count',song_remaining='Song Remaining',roll='Roll',active_roll='Active Roll',
            roll_value='Roll Value',lucky_number='Lucky Number',bust='Bust',roll_count='Roll Count',bust_count='Bust Count',
            quick_draw_charges='Quick Draw',maneuver_count='Maneuver Count',maneuver_element='Maneuver Element',
            automaton_hp='Automaton HP',automaton_mp='Automaton MP',automaton_tp='Automaton TP',avatar_present='Avatar Present',
            blood_pact_ready='Blood Pact Ready',ready_charges='Ready Charges',bst_pet_hp='Pet HP',bst_pet_tp='Pet TP',
            wyvern_hp='Wyvern HP',luopan_present='Luopan Present',luopan_hp='Luopan HP',indi_active='Indi Active',geo_active='Geo Active'};
        return labels[rule.Property] or tostring(rule.Property);
    end
    local parts={};
    if rule.MissingBuff then
        if rule.MissingBuffExpireThreshold then
            parts[#parts+1]='Missing/Expiring Status: '..E.join(rule.MissingBuff);
        else
            parts[#parts+1]='Missing Status: '..E.join(rule.MissingBuff);
        end
    end
    if rule.Status then parts[#parts+1]='Has Status: '..E.status_condition_display(rule.Status); end
    if rule.RequiresBuff then parts[#parts+1]='Has Status: '..E.join(rule.RequiresBuff); end
    if rule.ForbidBuff then parts[#parts+1]='Missing Status: '..E.join(rule.ForbidBuff); end
    if #parts==0 then return 'Always'; end
    return table.concat(parts,' + ');
end
function E.rule_condition_display_text(rule)
    if rule and rule.MissingBuffBinding=='action' and not rule.MissingBuff then
        return 'Missing Action Effect (unavailable)';
    end
    if rule and rule.SubjectLabel and rule.SubjectLabel~='' then
        local clone=E.clone(rule);
        clone.SubjectLabel=nil;
        local text=E.rule_condition_display_text(clone);
        for _,prefix in ipairs({'Target','Self','Actor','Enemy','Master','Player','Tank','Healer','Party','Alliance','Pet','Battle'}) do
            text=text:gsub('^'..prefix..':%s*','');
        end
        return tostring(rule.SubjectLabel)..': '..text;
    end
    if rule and rule.Property and rule.Property~='always' then
        return tostring(E.rule_status_text(rule))..' '..tostring(E.rule_condition_text(rule));
    end
    local status=E.rule_status_text(rule);
    if status and status~='Always' then return status; end
    return E.rule_condition_text(rule);
end
function E.rule_condition_text(rule)
    if not rule then return 'Always'; end
    if rule.Property and rule.Property~='always' then
        local op=rule.Operator or 'yes';
        if op=='any' then return 'Any'; end
        if op=='present' then return 'Present'; end
        if op=='missing' then return 'Missing'; end
        if op=='yes' then return 'Yes'; end
        if op=='no' then return 'No'; end
        if op=='has' then return 'Has'; end
        if op=='not' then return 'Does Not Have'; end
        if op=='ready' then return 'Ready'; end
        if op=='not-ready' then return 'Not Ready'; end
        local value=rule.TextValue or rule.ValueText or rule.Value;
        if value~=nil then return tostring(op)..' '..tostring(value); end
        return tostring(op);
    end
    local parts={};
    local add=function(label,value,suffix)
        if value~=nil then parts[#parts+1]=label..' '..tostring(value)..(suffix or ''); end
    end;
    add('Self HP <',rule.SelfHPBelow,'%'); add('Self HP >',rule.SelfHPAbove,'%');
    add('Self MP <',rule.SelfMPBelow,'%'); add('Self MP >',rule.SelfMPAbove,'%');
    add('Self TP <',rule.SelfTPBelow,''); add('Self TP >=',rule.SelfTPAbove,'');
    add('Target HP <',rule.TargetHPBelow,'%'); add('Target HP >',rule.TargetHPAbove,'%');
    add('Target MP <',rule.TargetMPBelow,'%'); add('Target MP >',rule.TargetMPAbove,'%');
    add('Missing HP >=',rule.MinMissingHP,'');
    add('TP >=',rule.TP,'');
    add('Pet HP <',rule.PetHPBelow,'%'); add('Pet TP >=',rule.PetTPAbove,'');
    add('Distance <=',rule.Range,'');
    if rule.Pet then parts[#parts+1]='Pet '..tostring(rule.Pet); end
    if rule.Mechanic then parts[#parts+1]=tostring(rule.Mechanic); end
    if #parts==0 then return rule.Combat=='idle' and 'Idle' or (rule.Combat=='combat' and 'In Battle' or 'Always'); end
    return table.concat(parts,' + ');
end
function E.condition_slot(rule,slot,create)
    if slot==2 then
        if create and type(rule.Condition2)~='table' then rule.Condition2={}; end
        return rule.Condition2;
    end
    return rule;
end
function E.condition_slot_text(rule,slot)
    local condition=E.condition_slot(rule,slot,false);
    if slot==2 and not E.condition_clause_active(condition) then return 'Any'; end
    return E.rule_condition_display_text(condition or {});
end
function E.condition_slot_help(rule,index,slot)
    return 'Row '..tostring(index)..' condition #'..tostring(slot)..': '..E.condition_slot_text(rule,slot)..'.';
end
function E.rule_summary_text(rule,index)
    if not rule or rule.Empty==true then return 'Row '..tostring(index or '')..' is empty.'; end
    local enabled=(rule.Enabled~=false) and 'ON' or 'OFF';
    local conditionText=E.rule_condition_display_text(rule);
    if E.condition_clause_active(rule.Condition2) then conditionText=conditionText..' + '..E.rule_condition_display_text(rule.Condition2); end
    return 'Row '..tostring(index or '?')..' '..enabled..': '..conditionText..' -> '..E.rule_action_text(rule)..'.';
end
function E.rule_target_help(rule,index)
    return 'Row '..tostring(index)..' target: '..E.rule_target_text(rule)..'.';
end
function E.rule_condition_help(rule,index)
    return E.condition_slot_help(rule,index,1);
end
function E.rule_action_help(rule,index)
    local action=E.rule_action_text(rule);
    local help='Row '..tostring(index)..' action: '..action..'.';
    if rule and rule.Type=='spell' then
        local effect=E.smart_spell_effect(action);
        if effect=='Refresh' then return help..' Automatically skips recipients without a verified MP pool or already covered by Refresh.'; end
        if effect then return help..' Automatically skips recipients with this effect; unknown status waits for verification.'; end
        if action=='Dispel' or action=='Magic Finale' then return help..' Requires a verified dispellable enemy enhancement.'; end
        if E.removal_statuses(action) then return help..' Requires an ailment this spell can remove.'; end
        if action=='Raise' or action=='Raise II' or action=='Raise III' or action=='Arise' then
            return help..' Searches fallen eligible members; the combat Raise setting still applies.';
        end
        if action=='Cure' or action:match('^Cure [IVX]+$') then return help..' Skips full-health recipients.'; end
    end
    return help;
end
function E.rule_enabled_help(rule,index,effectiveEnabled)
    if effectiveEnabled then return 'Row '..tostring(index)..' is ON.'; end
    if rule and rule.Enabled==false then return 'Row '..tostring(index)..' is OFF.'; end
    return 'Master Gambits are OFF.';
end
local TRUST_JOBS = {
    ['Abenzio']='WAR/NONE',
    ['Iron Eater']='WAR/NONE', ['Zazarg']='MNK/NONE', ['Kupipi']='WHM/NONE', ['Robel-Akbel']='BLM/NONE',
    ['Rainemard']='RDM/NONE', ['Nanaa Mihgo']='THF/NONE', ['Valaineral']='PLD/NONE', ['Zeid']='DRK/NONE',
    ['Lhu Mhakaracca']='BST/NONE', ['Joachim']='BRD/NONE', ['Semih Lafihna']='RNG/NONE',
    ['Ayame']='SAM/NONE', ['Gessho']='NIN/NONE', ['Shikaree Z']='DRG/NONE', ['Karaha-Baruha']='SMN/NONE',
    ['Arciela']='RDM/NONE', ['Arciela II']='RDM/NONE', ['Qultada']='COR/NONE', ['Nashmeira']='PUP/NONE',
    ['Lilisette']='DNC/NONE', ['Lilisette II']='DNC/NONE', ['Adelheid']='SCH/NONE',
    ['Sylvie']='GEO/NONE', ['Sylvie (UC)']='GEO/NONE', ['Amchuchu']='RUN/NONE',
    ['Zeid II']='DRK/NONE', ['Halver']='PLD/WAR',
    ['Ark Angel EV']='PLD/WHM', ['ArkEV']='PLD/WHM', ['Ark Angel HM']='NIN/WAR',
    ['ArkHM']='NIN/WAR', ['August']='PLD/WAR', ['Curilla']='PLD/WAR', ['Gessho']='NIN/WAR',
    ['Mnejing']='PLD/PLD', ['Rahal']='PLD/WAR', ['Rughadjeen']='PLD/WAR', ['Trion']='PLD/WAR',
    ['Ferreous Coffin']='WHM/WAR',
    ['Ygnas']='WHM/RDM', ['Apururu (UC)']='WHM/RDM', ['Cherukiki']='WHM/BLM', ['Kupipi']='WHM/BLM',
    ['Monberaux']='WHM/RDM', ['Yoran-Oran (UC)']='WHM/BLM', ['Margret']='RNG/THF',
    ['Elivira']='RNG/WAR', ['Najelith']='RNG/WAR', ['Tenzen II']='RNG/SAM',
    ['Ark Angel TT']='BLM/DRK', ['ArkTT']='BLM/DRK', ['Shantotto']='BLM/WHM', ['Shantotto II']='BLM/WHM',
    ['Domina Shantotto']='BLM/WHM', ['Ajido-Marujido']='BLM/RDM', ['Ajido-Maujido']='BLM/RDM', ['Gadalar']='BLM/WHM',
    ['Kayeel-Payeel']='BLM/WHM', ['Kukki-Chebukki']='BLM/WHM',
    ['Ullegore']='BLM/DRK',
    ['Ulmia']='BRD/WHM', ['Koru-Moru']='RDM/WHM', ['King of Hearts']='RDM/WHM',
};
for name, combo in pairs({
    ['Iron Eater']='WAR/NONE', ['Zazarg']='MNK/NONE', ['Kupipi']='WHM/NONE', ['Robel-Akbel']='BLM/NONE',
    ['Rainemard']='RDM/NONE', ['Nanaa Mihgo']='THF/NONE', ['Valaineral']='PLD/NONE', ['Zeid']='DRK/NONE',
    ['Lhu Mhakaracca']='BST/NONE', ['Joachim']='BRD/NONE', ['Semih Lafihna']='RNG/NONE',
    ['Ayame']='SAM/NONE', ['Gessho']='NIN/NONE', ['Shikaree Z']='DRG/NONE', ['Karaha-Baruha']='SMN/NONE',
    ['Arciela']='RDM/NONE', ['Arciela II']='RDM/NONE', ['Qultada']='COR/NONE', ['Nashmeira']='PUP/NONE',
    ['Lilisette']='DNC/NONE', ['Lilisette II']='DNC/NONE', ['Adelheid']='SCH/NONE',
    ['Sylvie']='GEO/NONE', ['Sylvie (UC)']='GEO/NONE', ['Amchuchu']='RUN/NONE',
}) do TRUST_JOBS[name]=combo; end
local TRUST_ROLES = {
    ['Amchuchu']='tanks', ['Ark Angel EV']='tanks', ['ArkEV']='tanks', ['Ark Angel HM']='tanks', ['ArkHM']='tanks',
    ['August']='tanks', ['Curilla']='tanks', ['Gessho']='tanks', ['Mnejing']='tanks', ['Rahal']='tanks',
    ['Rughadjeen']='tanks', ['Trion']='tanks', ['Valaineral']='tanks',
    ['Ayame']='melee', ['Iron Eater']='melee', ['Lhu Mhakaracca']='melee', ['Lilisette']='melee',
    ['Lilisette II']='melee', ['Nanaa Mihgo']='melee', ['Nashmeira']='melee', ['Shikaree Z']='melee',
    ['Zazarg']='melee', ['Zeid']='melee', ['Zeid II']='melee',
    ['Elivira']='ranged', ['Makki-Chebukki']='ranged', ['Margret']='ranged', ['Najelith']='ranged',
    ['Semih Lafihna']='ranged', ['Tenzen II']='ranged',
    ['Adelheid']='casters', ['Ajido-Marujido']='casters', ['Ark Angel TT']='casters', ['ArkTT']='casters',
    ['Domina Shantotto']='casters', ['Gadalar']='casters', ['Ingrid']='casters', ['Kayeel-Payeel']='casters',
    ['Kukki-Chebukki']='casters', ['Leonoyne']='casters', ['Mumor II']='casters', ['Ovjang']='casters',
    ['Robel-Akbel']='casters', ['Rosulatia']='casters', ['Shantotto']='casters', ['Shantotto II']='casters',
    ['Ullegore']='casters',
    ['Apururu (UC)']='healers', ['Cherukiki']='healers', ['Ferreous Coffin']='healers', ['Karaha-Baruha']='casters',
    ['Kupipi']='healers', ['Mihli Aliapoh']='healers', ['Monberaux']='healers', ['Pieuje (UC)']='healers',
    ['Ygnas']='healers', ['Yoran-Oran (UC)']='healers',
    ['Arciela']='support', ['Arciela II']='support', ['Brygid']='support', ['Cornelia']='support',
    ['Joachim']='support', ['King of Hearts']='support', ['Koru-Moru']='support', ['Kupofried']='support',
    ['Kuyin Hathdenna']='support', ['Moogle']='support', ['Qultada']='support', ['Sakura']='support',
    ['Star Sibyl']='support', ['Sylvie']='support', ['Sylvie (UC)']='support', ['Ulmia']='support',
};
TRUST_PICKER = {
    {key='AAEV',name='AAEV',job='PLD/WHM',label='PLD/WHM - AAEV'},
    {key='AAGK',name='AAGK',job='SAM/DRG',label='SAM/DRG - AAGK'},
    {key='AAHM',name='AAHM',job='WAR/NIN',label='WAR/NIN - AAHM'},
    {key='AAMR',name='AAMR',job='BST/THF',label='BST/THF - AAMR'},
    {key='AATT',name='AATT',job='BLM/DRK',label='BLM/DRK - AATT'},
    {key='ABENZIO',name='Abenzio',job='MNK/NONE',label='MNK/NONE - Abenzio'},
    {key='ABQUHBAH',name='Abquhbah',job='WAR/NONE',label='WAR/NONE - Abquhbah'},
    {key='ADELHEID',name='Adelheid',job='SCH/BLM',label='SCH/BLM - Adelheid'},
    {key='AJIDO_MARUJIDO',name='Ajido-Marujido',job='BLM/RDM',label='BLM/RDM - Ajido-Marujido'},
    {key='ALDO',name='Aldo',job='THF/NONE',label='THF/NONE - Aldo'},
    {key='ALDO_UC',name='Aldo UC',job='THF/NONE',label='THF/NONE - Aldo UC'},
    {key='AMCHUCHU',name='Amchuchu',job='RUN/WAR',label='RUN/WAR - Amchuchu'},
    {key='APURURU_UC',name='Apururu UC',job='WHM/RDM',label='WHM/RDM - Apururu UC'},
    {key='ARCIELA',name='Arciela',job='RDM/NONE',label='RDM/NONE - Arciela'},
    {key='ARCIELA_II',name='Arciela II',job='RDM/NONE',label='RDM/NONE - Arciela II'},
    {key='AREUHAT',name='Areuhat',job='WAR/PLD',label='WAR/PLD - Areuhat'},
    {key='AUGUST',name='August',job='PLD/WAR',label='PLD/WAR - August'},
    {key='AYAME',name='Ayame',job='SAM/NONE',label='SAM/NONE - Ayame'},
    {key='AYAME_UC',name='Ayame UC',job='SAM/NONE',label='SAM/NONE - Ayame UC'},
    {key='BABBAN',name='Babban',job='MNK/NONE',label='MNK/NONE - Babban'},
    {key='BALAMOR',name='Balamor',job='DRK/NONE',label='DRK/NONE - Balamor'},
    {key='BRYGID',name='Brygid',job='GEO/NONE',label='GEO/NONE - Brygid'},
    {key='CHACHAROON',name='Chacharoon',job='THF/NONE',label='THF/NONE - Chacharoon'},
    {key='CHERUKIKI',name='Cherukiki',job='WHM/NONE',label='WHM/NONE - Cherukiki'},
    {key='CID',name='Cid',job='WAR/NONE',label='WAR/NONE - Cid'},
    {key='CORNELIA',name='Cornelia',job='GEO/BRD',label='GEO/BRD - Cornelia'},
    {key='CURILLA',name='Curilla',job='PLD/NONE',label='PLD/NONE - Curilla'},
    {key='DOMINA_SHANTOTTO',name='D Shantotto',job='BLM/DRK',label='BLM/DRK - D Shantotto'},
    {key='DARRCUILN',name='Darrcuiln',job='WAR/NONE',label='WAR/NONE - Darrcuiln'},
    {key='ELIVIRA',name='Elivira',job='RNG/WAR',label='RNG/WAR - Elivira'},
    {key='EXCENMILLE',name='Excenmille',job='PLD/NONE',label='PLD/NONE - Excenmille'},
    {key='EXCENMILLE_S',name='Excenmille S',job='WAR/NONE',label='WAR/NONE - Excenmille S'},
    {key='FABLINIX',name='Fablinix',job='THF/RDM',label='THF/RDM - Fablinix'},
    {key='FERREOUS_COFFIN',name='Ferreous Coffin',job='WHM/WAR',label='WHM/WAR - Ferreous Coffin'},
    {key='FLAVIRIA_UC',name='Flaviria UC',job='DRG/WAR',label='DRG/WAR - Flaviria UC'},
    {key='GADALAR',name='Gadalar',job='BLM/NONE',label='BLM/NONE - Gadalar'},
    {key='GESSHO',name='Gessho',job='NIN/WAR',label='NIN/WAR - Gessho'},
    {key='GILGAMESH',name='Gilgamesh',job='SAM/NONE',label='SAM/NONE - Gilgamesh'},
    {key='HALVER',name='Halver',job='PLD/WAR',label='PLD/WAR - Halver'},
    {key='INGRID',name='Ingrid',job='WHM/NONE',label='WHM/NONE - Ingrid'},
    {key='INGRID_II',name='Ingrid II',job='WHM/NONE',label='WHM/NONE - Ingrid II'},
    {key='INVINCIBLE_SHIELD_UC',name='Invincible Shield UC',job='WAR/MNK',label='WAR/MNK - Invincible Shield UC'},
    {key='IROHA',name='Iroha',job='SAM/BLM',label='SAM/BLM - Iroha'},
    {key='IROHA_II',name='Iroha II',job='SAM/WHM',label='SAM/WHM - Iroha II'},
    {key='IRON_EATER',name='Iron Eater',job='WAR/NONE',label='WAR/NONE - Iron Eater'},
    {key='JAKOH_UC',name='Jakoh Wahcondalo UC',job='THF/WAR',label='THF/WAR - Jakoh Wahcondalo UC'},
    {key='JOACHIM',name='Joachim',job='BRD/WHM',label='BRD/WHM - Joachim'},
    {key='KARAHA_BARUHA',name='Karaha-Baruha',job='WHM/SMN',label='WHM/SMN - Karaha-Baruha'},
    {key='KAYEEL_PAYEEL',name='Kayeel-Payeel',job='BLM/SMN',label='BLM/SMN - Kayeel-Payeel'},
    {key='KING_OF_HEARTS',name='King of Hearts',job='RDM/WHM',label='RDM/WHM - King of Hearts'},
    {key='KLARA',name='Klara',job='WAR/NONE',label='WAR/NONE - Klara'},
    {key='KORU_MORU',name='Koru-Moru',job='RDM/NONE',label='RDM/NONE - Koru-Moru'},
    {key='KUKKI_CHEBUKKI',name='Kukki-Chebukki',job='BLM/NONE',label='BLM/NONE - Kukki-Chebukki'},
    {key='KUPIPI',name='Kupipi',job='WHM/NONE',label='WHM/NONE - Kupipi'},
    {key='KUPOFRIED',name='Kupofried',job='GEO/NONE',label='GEO/NONE - Kupofried'},
    {key='KUYIN_HATHDENNA',name='Kuyin Hathdenna',job='GEO/NONE',label='GEO/NONE - Kuyin Hathdenna'},
    {key='LEHKO_HABHOKA',name='Lehko Habhoka',job='THF/BLM',label='THF/BLM - Lehko Habhoka'},
    {key='LEONOYNE',name='Leonoyne',job='BLM/DRK',label='BLM/DRK - Leonoyne'},
    {key='LHE_LHANGAVO',name='Lhe Lhangavo',job='MNK/WAR',label='MNK/WAR - Lhe Lhangavo'},
    {key='LHU_MHAKARACCA',name='Lhu Mhakaracca',job='BST/WAR',label='BST/WAR - Lhu Mhakaracca'},
    {key='LILISETTE',name='Lilisette',job='DNC/NONE',label='DNC/NONE - Lilisette'},
    {key='LILISETTE_II',name='Lilisette II',job='DNC/NONE',label='DNC/NONE - Lilisette II'},
    {key='LION',name='Lion',job='THF/NIN',label='THF/NIN - Lion'},
    {key='LION_II',name='Lion II',job='THF/NIN',label='THF/NIN - Lion II'},
    {key='LUZAF',name='Luzaf',job='COR/NIN',label='COR/NIN - Luzaf'},
    {key='MAAT',name='Maat',job='MNK/NONE',label='MNK/NONE - Maat'},
    {key='MAAT_UC',name='Maat UC',job='MNK/WAR',label='MNK/WAR - Maat UC'},
    {key='MAKKI_CHEBUKKI',name='Makki-Chebukki',job='RNG/NONE',label='RNG/NONE - Makki-Chebukki'},
    {key='MARGRET',name='Margret',job='RNG/NONE',label='RNG/NONE - Margret'},
    {key='MATSUI_P',name='Matsui-P',job='NIN/BLM',label='NIN/BLM - Matsui-P'},
    {key='MAXIMILIAN',name='Maximilian',job='THF/WAR',label='THF/WAR - Maximilian'},
    {key='MAYAKOV',name='Mayakov',job='DNC/NONE',label='DNC/NONE - Mayakov'},
    {key='MIHLI_ALIAPOH',name='Mihli Aliapoh',job='WHM/NONE',label='WHM/NONE - Mihli Aliapoh'},
    {key='MILDAURION',name='Mildaurion',job='PLD/WAR',label='PLD/WAR - Mildaurion'},
    {key='MNEJING',name='Mnejing',job='PLD/NONE',label='PLD/NONE - Mnejing'},
    {key='MONBERAUX',name='Monberaux',job='PLD/RUN',label='PLD/RUN - Monberaux'},
    {key='MOOGLE',name='Moogle',job='GEO/NONE',label='GEO/NONE - Moogle'},
    {key='MORIMAR',name='Morimar',job='BST/NONE',label='BST/NONE - Morimar'},
    {key='MUMOR',name='Mumor',job='DNC/WAR',label='DNC/WAR - Mumor'},
    {key='MUMOR_II',name='Mumor II',job='BLM/NONE',label='BLM/NONE - Mumor II'},
    {key='NAJA_SALAHEEM',name='Naja Salaheem',job='MNK/WAR',label='MNK/WAR - Naja Salaheem'},
    {key='NAJA_UC',name='Naja Salaheem UC',job='THF/WAR',label='THF/WAR - Naja Salaheem UC'},
    {key='NAJELITH',name='Najelith',job='RNG/NONE',label='RNG/NONE - Najelith'},
    {key='NAJI',name='Naji',job='WAR/NONE',label='WAR/NONE - Naji'},
    {key='NANAA_MIHGO',name='Nanaa Mihgo',job='THF/NONE',label='THF/NONE - Nanaa Mihgo'},
    {key='NASHMEIRA',name='Nashmeira',job='PUP/WHM',label='PUP/WHM - Nashmeira'},
    {key='NASHMEIRA_II',name='Nashmeira II',job='WHM/PUP',label='WHM/PUP - Nashmeira II'},
    {key='NOILLURIE',name='Noillurie',job='SAM/PLD',label='SAM/PLD - Noillurie'},
    {key='OVJANG',name='Ovjang',job='RDM/NONE',label='RDM/NONE - Ovjang'},
    {key='PIEUJE_UC',name='Pieuje UC',job='WHM/NONE',label='WHM/NONE - Pieuje UC'},
    {key='PRISHE',name='Prishe',job='MNK/WHM',label='MNK/WHM - Prishe'},
    {key='PRISHE_II',name='Prishe II',job='WHM/MNK',label='WHM/MNK - Prishe II'},
    {key='QULTADA',name='Qultada',job='COR/NONE',label='COR/NONE - Qultada'},
    {key='RAHAL',name='Rahal',job='PLD/WAR',label='PLD/WAR - Rahal'},
    {key='RAINEMARD',name='Rainemard',job='RDM/NONE',label='RDM/NONE - Rainemard'},
    {key='ROBEL_AKBEL',name='Robel-Akbel',job='BLM/SMN',label='BLM/SMN - Robel-Akbel'},
    {key='ROMAA_MIHGO',name='Romaa Mihgo',job='THF/WAR',label='THF/WAR - Romaa Mihgo'},
    {key='RONGELOUTS',name='Rongelouts',job='WAR/NONE',label='WAR/NONE - Rongelouts'},
    {key='ROSULATIA',name='Rosulatia',job='BLM/NONE',label='BLM/NONE - Rosulatia'},
    {key='RUGHADJEEN',name='Rughadjeen',job='PLD/NONE',label='PLD/NONE - Rughadjeen'},
    {key='SAKURA',name='Sakura',job='GEO/NONE',label='GEO/NONE - Sakura'},
    {key='SELHTEUS',name='Selh\'teus',job='PLD/NONE',label='PLD/NONE - Selh\'teus'},
    {key='SEMIH_LAFIHNA',name='Semih Lafihna',job='RNG/WAR',label='RNG/WAR - Semih Lafihna'},
    {key='SHANTOTTO',name='Shantotto',job='BLM/NONE',label='BLM/NONE - Shantotto'},
    {key='SHANTOTTO_II',name='Shantotto II',job='BLM/NONE',label='BLM/NONE - Shantotto II'},
    {key='SHIKAREE_Z',name='Shikaree Z',job='DRG/WHM',label='DRG/WHM - Shikaree Z'},
    {key='STAR_SIBYL',name='Star Sibyl',job='GEO/NONE',label='GEO/NONE - Star Sibyl'},
    {key='SYLVIE_UC',name='Sylvie UC',job='GEO/WHM',label='GEO/WHM - Sylvie UC'},
    {key='TENZEN',name='Tenzen',job='SAM/NONE',label='SAM/NONE - Tenzen'},
    {key='TENZEN_II',name='Tenzen II',job='SAM/RNG',label='SAM/RNG - Tenzen II'},
    {key='TEODOR',name='Teodor',job='BLM/THF',label='BLM/THF - Teodor'},
    {key='TRION',name='Trion',job='PLD/WAR',label='PLD/WAR - Trion'},
    {key='UKA_TOTLIHN',name='Uka Totlihn',job='DNC/WAR',label='DNC/WAR - Uka Totlihn'},
    {key='ULLEGORE',name='Ullegore',job='BLM/NONE',label='BLM/NONE - Ullegore'},
    {key='ULMIA',name='Ulmia',job='BRD/NONE',label='BRD/NONE - Ulmia'},
    {key='VALAINERAL',name='Valaineral',job='PLD/WAR',label='PLD/WAR - Valaineral'},
    {key='VOLKER',name='Volker',job='WAR/NONE',label='WAR/NONE - Volker'},
    {key='YGNAS',name='Ygnas',job='WHM/NONE',label='WHM/NONE - Ygnas'},
    {key='YORAN_ORAN_UC',name='Yoran-Oran UC',job='WHM/NONE',label='WHM/NONE - Yoran-Oran UC'},
    {key='ZAZARG',name='Zazarg',job='MNK/WAR',label='MNK/WAR - Zazarg'},
    {key='ZEID',name='Zeid',job='DRK/NONE',label='DRK/NONE - Zeid'},
    {key='ZEID_II',name='Zeid II',job='DRK/WAR',label='DRK/WAR - Zeid II'},
};
TRUST_PICKER_BY_KEY = {};
TRUST_PICKER_BY_NAME = {};
local TRUST_BARE_UC_ALIASES = {
    ARKEV='AAEV',
    ARKGK='AAGK',
    ARKHM='AAHM',
    ARKMR='AAMR',
    ARKTT='AATT',
    APURURU='APURURU_UC',
    FLAVIRIA='FLAVIRIA_UC',
    INVINCIBLESHLD='INVINCIBLE_SHIELD_UC',
    INVINCIBLESHIELD='INVINCIBLE_SHIELD_UC',
    JAKOHWAHCONDALO='JAKOH_UC',
    PIEUJE='PIEUJE_UC',
    YORANORAN='YORAN_ORAN_UC',
};
local TRUST_JOBS_BY_NAME_KEY = {};
local TRUST_ROLES_BY_NAME_KEY = {};
local function register_trust_picker_alias(alias,entry)
    if not alias or alias=='' or not entry then return; end
    local normalized=E.trust_name_key(alias);
    local current=TRUST_PICKER_BY_NAME[normalized];
    if current and current~=entry then return; end
    TRUST_PICKER_BY_NAME[alias]=entry;
    TRUST_PICKER_BY_NAME[normalized]=entry;
end
for _,entry in ipairs(TRUST_PICKER) do
    TRUST_PICKER_BY_KEY[entry.key]=entry;
    register_trust_picker_alias(entry.name,entry);
    register_trust_picker_alias(entry.label,entry);
    register_trust_picker_alias(entry.key,entry);
    if entry.name:find(' UC',1,true) then
        register_trust_picker_alias(entry.name:gsub(' UC',' (UC)'),entry);
    end
end
for alias,key in pairs(TRUST_BARE_UC_ALIASES) do
    register_trust_picker_alias(alias,TRUST_PICKER_BY_KEY[key]);
end
function E.trust_alias_key(name)
    local key=E.trust_name_key(name);
    local aliases={
        ARKEV='AAEV', ARKGK='AAGK', ARKHM='AAHM', ARKMR='AAMR', ARKTT='AATT',
        ARKANGELEV='AAEV', ARKANGELGK='AAGK', ARKANGELHM='AAHM', ARKANGELMR='AAMR', ARKANGELTT='AATT',
    };
    return aliases[key] or key;
end
for name,combo in pairs(TRUST_JOBS) do
    TRUST_JOBS_BY_NAME_KEY[E.trust_name_key(name)]=combo;
end
for name,role in pairs(TRUST_ROLES) do
    TRUST_ROLES_BY_NAME_KEY[E.trust_name_key(name)]=role;
end
-- Party recognition and job sheets still need this registry without a summon UI.
function E.trust_picker_entry_by_name(name)
    if type(name)~='string' or name=='' then return nil; end
    return TRUST_PICKER_BY_NAME[name] or TRUST_PICKER_BY_NAME[E.trust_name_key(name)] or TRUST_PICKER_BY_NAME[E.trust_alias_key(name)];
end
local ROLE_JOB_FALLBACK = {
    tanks='PLD/WAR', melee='WAR/WAR', ranged='RNG/WAR', casters='BLM/WHM', healers='WHM/RDM', support='BRD/WHM',
};
JOB_ABILITY_CATALOG = {
    WAR={
        {'Mighty Strikes',1,true}, {'Provoke',5,false}, {'Berserk',15,false}, {'Defender',25,false},
        {'Warcry',35,false}, {'Aggressor',45,true}, {'Retaliation',60,true}, {"Warrior's Charge",75,true},
    },
    MNK={
        {'Hundred Fists',1,true}, {'Boost',5,false}, {'Dodge',15,false}, {'Focus',25,false},
        {'Chakra',35,false}, {'Chi Blast',41,true}, {'Counterstance',45,true}, {'Footwork',65,true},
        {'Formless Strikes',75,true}, {'Mantra',75,true},
    },
    WHM={
        {'Benediction',1,true}, {'Divine Seal',15,false}, {'Afflatus Solace',40,true}, {'Afflatus Misery',40,true},
        {'Martyr',75,true}, {'Devotion',75,true},
    },
    BLM={
        {'Manafont',1,true}, {'Elemental Seal',15,false}, {'Mana Wall',76,true},
    },
    RDM={
        {'Chainspell',1,true}, {'Convert',40,true}, {'Composure',50,true},
    },
    THF={
        {'Perfect Dodge',1,true}, {'Steal',5,false}, {'Sneak Attack',15,false}, {'Flee',25,false},
        {'Trick Attack',30,false}, {'Mug',35,true}, {'Hide',45,true}, {'Accomplice',65,true},
        {'Feint',75,true}, {"Assassin's Charge",75,true},
    },
    PLD={
        {'Invincible',1,true}, {'Holy Circle',5,false}, {'Shield Bash',15,false}, {'Sentinel',30,false},
        {'Cover',35,true}, {'Rampart',62,true}, {'Fealty',75,true}, {'Chivalry',75,true},
        {'Divine Emblem',75,true}, {'Majesty',75,true}, {'Palisade',75,true},
    },
    DRK={
        {'Blood Weapon',1,true}, {'Arcane Circle',5,false}, {'Last Resort',15,false}, {'Weapon Bash',20,false},
        {'Souleater',30,true}, {'Nether Void',45,true}, {'Dark Seal',75,true}, {'Diabolic Eye',75,true},
    },
    BST={
        {'Familiar',1,true}, {'Charm',1,false}, {'Gauge',10,false}, {'Reward',12,false},
        {'Call Beast',23,true}, {'Tame',30,false}, {'Sic',25,true}, {'Ready',25,true},
        {'Feral Howl',75,true}, {'Killer Instinct',75,true},
    },
    BRD={
        {'Soul Voice',1,true}, {'Pianissimo',20,true}, {'Nightingale',75,true}, {'Troubadour',75,true},
    },
    RNG={
        {'Eagle Eye Shot',1,true}, {'Sharpshot',1,false}, {'Scavenge',10,false}, {'Camouflage',20,false},
        {'Barrage',30,false}, {'Shadowbind',40,true}, {'Velocity Shot',45,true}, {'Unlimited Shot',51,true},
        {'Double Shot',79,true}, {'Decoy Shot',95,true}, {'Flashy Shot',75,true}, {'Stealth Shot',75,true},
    },
    SAM={
        {'Meikyo Shisui',1,true}, {'Warding Circle',5,false}, {'Third Eye',15,false}, {'Hasso',25,false},
        {'Meditate',30,true}, {'Seigan',35,true}, {'Sekkanoki',40,true}, {'Blade Bash',75,true},
        {'Shikikoyo',75,true},
    },
    NIN={
        {'Mijin Gakure',1,true}, {'Mijin',1,true}, {'Yonin',40,true}, {'Innin',40,true},
        {'Sange',75,true},
    },
    DRG={
        {'Spirit Surge',1,true}, {'Call Wyvern',1,true}, {'Ancient Circle',5,false}, {'Jump',10,false},
        {'High Jump',35,false}, {'Super Jump',50,true}, {'Spirit Link',25,true}, {'Angon',75,true},
        {'Deep Breathing',75,true},
    },
    SMN={
        {'Astral Flow',1,true}, {'Elemental Siphon',50,true}, {'Mana Cede',75,true},
    },
    BLU={
        {'Azure Lore',1,true}, {'Chain Affinity',40,true}, {'Burst Affinity',40,true},
        {'Convergence',75,true}, {'Diffusion',75,true}, {'Enchainment',75,true}, {'Assimilation',75,true},
    },
    COR={
        {'Wild Card',1,true}, {'Phantom Roll',5,true}, {'Double-Up',5,true},
        {"Corsair's Roll",5,true}, {'Ninja Roll',8,true}, {"Hunter's Roll",11,true}, {'Chaos Roll',14,true},
        {"Magus's Roll",17,true}, {"Healer's Roll",20,true}, {'Choral Roll',23,true}, {'Puppet Roll',26,true},
        {"Monk's Roll",31,true}, {'Beast Roll',34,true}, {'Samurai Roll',37,true}, {"Evoker's Roll",40,true},
        {'Quick Draw',40,true}, {"Rogue's Roll",43,true}, {"Warlock's Roll",46,true}, {"Fighter's Roll",49,true},
        {'Random Deal',50,true}, {'Drachen Roll',52,true}, {"Gallant's Roll",55,true}, {"Wizard's Roll",58,true},
        {"Dancer's Roll",61,true}, {"Scholar's Roll",64,true}, {'Snake Eye',75,true}, {'Fold',75,true},
        {"Bolter's Roll",76,true}, {"Caster's Roll",79,true}, {"Courser's Roll",81,true}, {"Blitzer's Roll",83,true},
        {"Tactician's Roll",86,true}, {'Triple Shot',87,true}, {"Allies' Roll",89,true}, {"Miser's Roll",92,true},
        {"Companion's Roll",95,true}, {"Avenger's Roll",97,true}, {"Naturalist's Roll",98,true}, {"Runeist's Roll",99,true},
    },
    PUP={
        {'Overdrive',1,true}, {'Activate',1,true}, {'Repair',15,true}, {'Deploy',1,true},
        {'Deactivate',1,true}, {'Retrieve',10,true}, {'Maintenance',30,true}, {'Role Reversal',75,true},
        {'Ventriloquy',75,true},
    },
    DNC={
        {'Trance',1,true}, {'Drain Samba',5,false}, {'Quickstep',20,false}, {'Box Step',30,false},
        {'Curing Waltz',15,false}, {'Animated Flourish',20,false}, {'Desperate Flourish',30,false},
        {'Violent Flourish',45,true}, {'Reverse Flourish',40,true}, {'No Foot Rise',75,true},
    },
    SCH={
        {'Tabula Rasa',1,true}, {'Light Arts',10,false}, {'Dark Arts',10,false}, {'Addendum: White',10,false},
        {'Addendum: Black',30,false}, {'Penury',10,false}, {'Parsimony',10,false}, {'Celerity',25,true},
        {'Alacrity',25,true}, {'Accession',40,true}, {'Manifestation',40,true}, {'Sublimation',35,true},
    },
    GEO={
        {'Bolster',1,true}, {'Full Circle',5,false}, {'Life Cycle',50,true}, {'Blaze of Glory',60,true},
        {'Dematerialize',75,true}, {'Ecliptic Attrition',75,true}, {'Lasting Emanation',75,true},
    },
    RUN={
        {'Elemental Sforzo',1,true}, {'Vallation',10,false}, {'Swordplay',20,false}, {'Lunge',25,false},
        {'Pflug',40,true}, {'Valiance',50,true}, {'Gambit',70,true}, {'Rayke',75,true},
        {'Battuta',75,true},
    },
};
local WS_CATALOG = {
    h2h={'Combo','Shoulder Tackle','One Inch Punch','Backhand Blow','Raging Fists','Spinning Attack','Howling Fist','Dragon Kick','Asuran Fists'},
    dagger={'Wasp Sting','Gust Slash','Shadowstitch','Viper Bite','Cyclone','Energy Steal','Energy Drain','Dancing Edge','Shark Bite','Evisceration'},
    sword={'Fast Blade','Burning Blade','Red Lotus Blade','Flat Blade','Shining Blade','Seraph Blade','Circle Blade','Spirits Within','Vorpal Blade','Swift Blade','Savage Blade'},
    great_sword={'Hard Slash','Power Slash','Frostbite','Freezebite','Shockwave','Crescent Moon','Sickle Moon','Spinning Slash','Ground Strike'},
    axe={'Raging Axe','Smash Axe','Gale Axe','Avalanche Axe','Spinning Axe','Rampage','Calamity','Mistral Axe','Decimation'},
    great_katana={'Tachi: Enpi','Tachi: Hobaku','Tachi: Goten','Tachi: Kagero','Tachi: Jinpu','Tachi: Koki','Tachi: Yukikaze','Tachi: Gekko','Tachi: Kasha'},
    katana={'Blade: Rin','Blade: Retsu','Blade: Teki','Blade: To','Blade: Chi','Blade: Ei','Blade: Jin','Blade: Ten','Blade: Ku'},
    scythe={'Slice','Dark Harvest','Shadow of Death','Nightmare Scythe','Spinning Scythe','Vorpal Scythe','Guillotine','Cross Reaper','Spiral Hell'},
    polearm={'Double Thrust','Thunder Thrust','Raiden Thrust','Leg Sweep','Penta Thrust','Vorpal Thrust','Skewer','Wheeling Thrust','Impulse Drive'},
    archery={'Flaming Arrow','Piercing Arrow','Dulling Arrow','Sidewinder','Blast Arrow','Arching Arrow','Empyreal Arrow','Refulgent Arrow'},
    marksmanship={'Hot Shot','Split Shot','Sniper Shot','Slug Shot','Blast Shot','Heavy Shot','Detonator'},
    club={'Shining Strike','Seraph Strike','Brainshaker','Starlight','Moonlight','Skullbreaker','True Strike','Judgment','Hexa Strike','Black Halo'},
    staff={'Heavy Swing','Rock Crusher','Earth Crusher','Starburst','Sunburst','Shell Crusher','Full Swing','Spirit Taker','Retribution'},
    great_axe={'Shield Break','Iron Tempest','Sturmwind','Armor Break','Keen Edge','Weapon Break','Raging Rush','Full Break','Steel Cyclone'},
};
JOB_WS_CATALOG = {
    WAR={'great_axe','axe','sword'},
    MNK={'h2h','staff','club'},
    WHM={'club','staff'},
    BLM={'staff','club'},
    RDM={'sword','dagger','club','staff'},
    THF={'dagger','sword','h2h'},
    PLD={'sword','club'},
    DRK={'great_sword','scythe','sword'},
    BST={'axe','sword','scythe'},
    BRD={'dagger','sword','club'},
    RNG={'archery','marksmanship','dagger','sword'},
    SAM={'great_katana','polearm','archery'},
    NIN={'katana','dagger','sword'},
    DRG={'polearm','staff'},
    SMN={'staff','club'},
    BLU={'sword','club'},
    COR={'marksmanship','sword','dagger'},
    PUP={'h2h','dagger','club'},
    DNC={'dagger','h2h','sword'},
    SCH={'staff','club'},
    GEO={'club','staff'},
    RUN={'great_sword','sword','axe'},
};
function E.job_weapon_skill_names(job)
    local out={}; local seen={};
    for _,family in ipairs(JOB_WS_CATALOG[job] or {}) do
        for _,name in ipairs(WS_CATALOG[family] or {}) do
            if not seen[name] then seen[name]=true; out[#out+1]=name; end
        end
    end
    return out;
end
local RECRUIT_WS_FAMILY={WAR='great_axe',MNK='h2h',WHM='club',BLM='staff',RDM='sword',THF='dagger'};
-- Minimum recruit level for normal, unlocked skills; derived from sql/weapon_skills.sql,
-- sql/skill_ranks.sql and sql/skill_caps.sql. The server still validates each request.
local RECRUIT_WS_MIN_LEVEL={
    WAR={['Shield Break']=1,['Iron Tempest']=13,['Sturmwind']=23,['Armor Break']=33,['Keen Edge']=49,['Weapon Break']=55,['Raging Rush']=60,['Full Break']=65},
    MNK={['Combo']=1,['Shoulder Tackle']=13,['One Inch Punch']=24,['Backhand Blow']=33,['Raging Fists']=41,['Spinning Attack']=49,['Howling Fist']=60,['Dragon Kick']=65},
    WHM={['Shining Strike']=1,['Seraph Strike']=14,['Brainshaker']=24,['Starlight']=34,['Moonlight']=43,['Skullbreaker']=51,['True Strike']=56,['Judgment']=62,['Hexa Strike']=67},
    BLM={['Heavy Swing']=1,['Rock Crusher']=14,['Starburst']=34,['Shell Crusher']=56,['Full Swing']=62,['Spirit Taker']=68},
    RDM={['Fast Blade']=1,['Burning Blade']=10,['Red Lotus Blade']=17,['Flat Blade']=26,['Shining Blade']=34,['Seraph Blade']=43,['Circle Blade']=51,['Spirits Within']=56,['Vorpal Blade']=62},
    THF={['Wasp Sting']=1,['Viper Bite']=33,['Shadowstitch']=23,['Gust Slash']=13,['Cyclone']=41,['Energy Steal']=49,['Energy Drain']=55,['Dancing Edge']=60,['Shark Bite']=65},
};
function E.generated_recruit_ws_allowed(ctx,action)
    local family=ctx.generatedRecruit and RECRUIT_WS_FAMILY[ctx.mainJob];
    return not family or E.contains(WS_CATALOG[family],action);
end
E.generated_war_ws_allowed=E.generated_recruit_ws_allowed;
function E.generated_recruit_ws_learned(ctx,action)
    if not ctx.generatedRecruit then return true; end
    local minimum=(RECRUIT_WS_MIN_LEVEL[ctx.mainJob] or {})[action];
    return minimum~=nil and E.main_level_cap(ctx)>=minimum;
end
function E.guest_ws_names(ctx)
    local capabilities=E.trust_capabilities(ctx);
    if capabilities then
        local selected={};
        for ordinal,entry in ipairs(capabilities.Actions or {}) do
            if type(entry)=='table' and entry.Type=='ws' and E.generated_recruit_ws_allowed(ctx,entry.Action) and E.generated_recruit_ws_learned(ctx,entry.Action) and E.trust_permission(ctx,'ws',entry.Action)==true then
                selected[#selected+1]={name=entry.Action,priority=E.number(entry.Priority,ordinal) or ordinal,ordinal=ordinal};
            end
        end
        table.sort(selected,function(a,b) if a.priority~=b.priority then return a.priority<b.priority; end return a.ordinal<b.ordinal; end);
        local out={}; for _,entry in ipairs(selected) do out[#out+1]=entry.name; end
        return out;
    end
    if (ctx.settings or DEFAULT).RequireVerifiedTrustCapabilities and not ctx.generatedRecruit then return {}; end
    -- Preserve legacy candidates, but use the same preferred-first ladders as players.
    -- This ordering is a policy, NOT evidence of Trust identity or unlock levels.
    local familyIds={h2h=1,dagger=2,sword=3,great_sword=4,axe=5,great_axe=6,scythe=7,
        polearm=8,katana=9,great_katana=10,club=11,staff=12,archery=25,marksmanship=26};
    local out,seen={},{};
    for _,family in ipairs((ctx.generatedRecruit and RECRUIT_WS_FAMILY[ctx.mainJob]) and {RECRUIT_WS_FAMILY[ctx.mainJob]} or (JOB_WS_CATALOG[ctx.mainJob] or {})) do
        local allowed=WS_CATALOG[family] or {};
        for _,name in ipairs(WS[familyIds[family]] or {}) do
            if E.contains(allowed,name) and E.generated_recruit_ws_learned(ctx,name) and not seen[name] then out[#out+1]=name; seen[name]=true; end
        end
        for _,name in ipairs(allowed) do if E.generated_recruit_ws_learned(ctx,name) and not seen[name] then out[#out+1]=name; seen[name]=true; end end
    end
    return out;
end
function E.guest_ability_available(ctx,res)
    local name=res and res.Name and res.Name[1];
    if not name then return false; end
    local permitted=E.trust_permission(ctx,'ability',name);
    if permitted~=nil then return permitted; end
    for _,side in ipairs({
        {job=ctx.mainJob,level=math.min(E.number(ctx.mainLevel) or 0,75),sub=false},
        {job=ctx.subJob,level=math.min(E.number(ctx.subLevel) or 0,37),sub=true},
    }) do
        for _,entry in ipairs(JOB_ABILITY_CATALOG[side.job] or {}) do
            if entry[1]==name and (entry[2] or 1)<=side.level and not (side.sub and entry[3]==true) then return true; end
        end
    end
    return false;
end
function E.guest_weapon_skill_available(ctx,res)
    local action=res and res.Name and res.Name[1];
    if not action or not E.generated_recruit_ws_allowed(ctx,action) then return false; end
    local permitted=E.trust_permission(ctx,'ws',action);
    if permitted~=nil then return permitted; end
    for _,known in ipairs(E.guest_ws_names(ctx) or {}) do
        if known==action then return true; end
    end
    return false;
end
function E.trust_role(name)
    if TRUST_ROLES[name or ''] then return TRUST_ROLES[name or '']; end
    local role=TRUST_ROLES_BY_NAME_KEY[E.trust_name_key(name)];
    if role then return role; end
    local entry=E.trust_picker_entry_by_name and E.trust_picker_entry_by_name(name) or nil;
    if entry and entry.role then return entry.role; end
    return 'melee';
end
function E.trust_combo(name, sourceRole)
    if TRUST_JOBS[name or ''] then return TRUST_JOBS[name or '']; end
    local combo=TRUST_JOBS_BY_NAME_KEY[E.trust_name_key(name)];
    if combo then return combo; end
    local entry=E.trust_picker_entry_by_name and E.trust_picker_entry_by_name(name) or nil;
    if entry and entry.job then return entry.job; end
    return ROLE_JOB_FALLBACK[sourceRole or E.trust_role(name)] or 'WAR/WAR';
end
function E.is_known_guest_name(name)
    if TRUST_JOBS[name or ''] ~= nil or TRUST_ROLES[name or ''] ~= nil then return true; end
    local key=E.trust_name_key(name);
    if TRUST_JOBS_BY_NAME_KEY[key] ~= nil or TRUST_ROLES_BY_NAME_KEY[key] ~= nil then return true; end
    return E.trust_picker_entry_by_name(name) ~= nil;
end
function E.is_generated_recruit(member)
    if not member then return false; end
    if member.generatedRecruit==true then return true; end
    local index=E.number(member.entityIndex);
    -- In Titan's party rows, 0x700..0x8ff is the dynamic entity range used
    -- by spawned Trusts; player character target IDs stay below this range.
    return index~=nil and index>=0x700 and index<=0x8ff
        and not E.is_known_guest_name(member.name)
        and member.mainJob~=nil and member.mainJob~='NONE';
end
function E.guest_member_readiness(ctx, member)
    if not ctx or not member then return false,'Party member data is unavailable'; end
    if not E.is_known_guest_name(member.name) and not E.is_generated_recruit(member) then return false,'Party member is not a recognized Trust'; end
    if not member.alive then return false,'Trust is dead or not active yet'; end
    if not member.index or member.index < 1 or member.index > 5 then return false,'Trust is outside the editable party slots'; end
    if not member.id or member.id <= 0 then return false,'Trust server ID is not ready yet'; end
    if not member.entityIndex or member.entityIndex <= 0 then return false,'Trust target index is not ready yet'; end
    if member.zone ~= ctx.zone then return false,'Trust is in another zone or still zoning'; end
    return true,nil;
end
function E.is_controllable_guest_member(ctx, member)
    local ok=E.guest_member_readiness(ctx,member);
    if ok~=true then return false; end
    local leaderOk=E.trust_control_allowed(ctx);
    return leaderOk==true;
end
function E.is_real_party_member(ctx, member)
    if not ctx or not member or not member.alive then return false; end
    if not member.index or member.index < 1 or member.index > 5 then return false; end
    if member.zone ~= ctx.zone then return false; end
    return not E.is_known_guest_name(member.name) and not E.is_generated_recruit(member);
end
function E.party_member_classification(ctx, member)
    if not ctx or not member then return {isTrust=false,isHuman=false}; end
    local known=E.is_known_guest_name(member.name) or E.is_generated_recruit(member);
    local ready,reason=E.guest_member_readiness(ctx,member);
    if known and ready then
        local leaderOk,leaderReason=E.trust_control_allowed(ctx);
        if not leaderOk then
            return {isTrust=false, isTrustUnavailable=true, isHuman=false, readyReason=leaderReason or 'Only the party leader can control Trust Gambits.'};
        end
    end
    local human=E.is_real_party_member(ctx,member);
    return {isTrust=ready, isTrustUnavailable=known and not ready, isHuman=human, readyReason=reason};
end
function E.party_slot_memory_entry(ctx,index)
    if not ctx or not ctx.partyMemory or not E.truth(E.call(ctx.partyMemory,'GetMemberIsActive',index)) then return nil; end
    local name=E.call(ctx.partyMemory,'GetMemberName',index);
    if type(name)~='string' or name=='' then return nil; end
    local zone=E.call(ctx.partyMemory,'GetMemberZone',index);
    if zone~=ctx.zone then return nil; end
    local generated=E.is_generated_recruit({name=name,
        entityIndex=E.call(ctx.partyMemory,'GetMemberTargetIndex',index),
        mainJob=JOBS[E.call(ctx.partyMemory,'GetMemberMainJob',index)]});
    local known=E.is_known_guest_name(name) or generated;
    return {
        name=name,
        id=E.call(ctx.partyMemory,'GetMemberServerId',index),
        partyIndex=index,
        entityIndex=E.call(ctx.partyMemory,'GetMemberTargetIndex',index),
        mainJob=JOBS[E.call(ctx.partyMemory,'GetMemberMainJob',index)],
        subJob=JOBS[E.call(ctx.partyMemory,'GetMemberSubJob',index)],
        pendingMemory=true,
        isGeneratedRecruit=generated,
        isTrustUnavailable=known,
        isHuman=not known,
        readyReason=known and 'Trust party memory is still resolving' or nil,
    };
end
function E.pending_recruit_slot_entry(slotIndex)
    local pending=S.ui.pendingRecruitSlots and S.ui.pendingRecruitSlots[slotIndex] or nil;
    if not pending or E.now()>(pending.expiresAt or 0) then
        if S.ui.pendingRecruitSlots then S.ui.pendingRecruitSlots[slotIndex]=nil; end
        return nil;
    end
    local name=pending.trust;
    if not E.is_known_guest_name(name) then return nil; end
    local main,sub=E.split_job_combo(E.trust_combo(name,'partyguest'));
    return {
        name=name,
        id=nil,
        partyIndex=slotIndex-1,
        mainJob=main,
        subJob=sub,
        pendingRecruit=true,
    };
end
function E.pending_recruit_resolve(slots)
    if type(S.ui.pendingRecruitSlots)~='table' then S.ui.pendingRecruitSlots={}; return; end
    local now=E.now();
    for slotIndex,pending in pairs(S.ui.pendingRecruitSlots) do
        local slot=slots and slots[slotIndex] or nil;
        if not pending or now>(pending.expiresAt or 0) or (slot and slot.name and slot.name~='vacant' and not slot.pendingRecruit) then
            S.ui.pendingRecruitSlots[slotIndex]=nil;
        end
    end
end
function E.split_job_combo(combo)
    local main, sub = tostring(combo or 'WAR/WAR'):match('^([^/]+)/?(.*)$');
    main = main and main ~= '' and main or 'WAR';
    sub = sub and sub ~= '' and sub or 'NONE';
    return main, sub;
end
function E.selected_guest_member(ctx)
    if not ctx then return nil; end
    local selectedId = S.ui.selectedActorId;
    local selectedName = S.ui.selectedActorName;
    for _, member in ipairs(ctx.party or {}) do
        if E.is_controllable_guest_member(ctx,member) then
            if selectedId then
                if member.id == selectedId and (not selectedName or member.name == selectedName) then return member; end
            elseif selectedName and member.name == selectedName then
                return member;
            end
        end
    end
    return nil;
end
function E.default_guest_rules(actor)
    do return {}; end
    local name=actor and actor.name or 'Guest Trust';
    local combo=(actor and actor.mainJob and (tostring(actor.mainJob)..'/'..tostring(actor.subJob or 'NONE'))) or E.trust_combo(name,S.ui.guestSourceRole or S.ui.roleTab);
    local main,sub=E.split_job_combo(combo);
    local hasJob=function(job) return main==job or sub==job; end
    local r={};
    local add=function(id,kind,action,target,options)
        local stem=E.safe_file_stem and E.safe_file_stem(name) or tostring(name or 'guest'):lower():gsub('[^%w]+','-');
        local opts=options or {};
        opts.Label=opts.Label or ('Generic '..tostring(main)..'/'..tostring(sub)..' action');
        return E.rule(r,stem..'-'..id,'guest_personality',kind,action,target,opts);
    end
    local addAttack=function()
        add('attack','attack','Attack','enemy',{Property='in_battle',Operator='yes',Combat='combat',Cooldown=2});
    end
    local addWS=function(id,extra)
        local opts={TP=1000,Combat='combat',Cooldown=3,PerTargetCooldown=3};
        for k,v in pairs(extra or {}) do opts[k]=v; end
        add(id or 'weapon-skill','ws_auto',nil,'enemy',opts);
    end
    local addCures=function()
        add('guest-raise','spell',{'Raise III','Raise II','Raise'},'dead',{Combat='any',SelfMPAbove=25,Cooldown=5,PerTargetCooldown=45});
        add('guest-emergency-cure','cure',nil,'lowest',{TargetHPBelow=35,Emergency=true,Cooldown=2,PerTargetCooldown=2});
        add('guest-status-doom','spell','Cursna','status',{Status={'Doom',15},Cooldown=3,PerTargetCooldown=4});
        add('guest-status-stona','spell','Stona','status',{Status={'Petrification',7},Cooldown=3,PerTargetCooldown=5});
        add('guest-status-silena','spell','Silena','status',{Status={'Silence',6},Cooldown=3,PerTargetCooldown=5});
        add('guest-status-paralyna','spell','Paralyna','status',{Status={'Paralysis',4},Cooldown=3,PerTargetCooldown=5});
        add('guest-erase','spell','Erase','status',{Status={'Slow','Elegy','Bind','Weight'},Cooldown=3,PerTargetCooldown=6});
        add('guest-maintenance-cure','cure',nil,'lowest',{TargetHPBelow=70,MinMissingHP=40,SelfMPAbove=20,Cooldown=3,PerTargetCooldown=3});
    end
    local addTankCore=function()
        if hasJob('PLD') then
            add('guest-flash','spell','Flash','enemy',{Combat='combat',Cooldown=5,PerTargetCooldown=20});
            add('guest-shield-bash-cast','ability','Shield Bash','enemy',{Property='casting',Operator='yes',Combat='combat',Cooldown=8});
            add('guest-sentinel','ability','Sentinel','self',{SelfHPBelow=55,Combat='combat',MissingBuff='Sentinel',Cooldown=10});
            add('guest-rampart','ability','Rampart','self',{SelfHPBelow=70,Combat='combat',MissingBuff='Rampart',Cooldown=10});
        end
        if hasJob('RUN') then
            add('guest-vallation','ability','Vallation','self',{SelfHPBelow=70,Combat='combat',Cooldown=10});
            add('guest-pflug','ability','Pflug','self',{SelfHPBelow=65,Combat='combat',Cooldown=15});
        end
        if hasJob('WAR') or hasJob('PLD') or hasJob('NIN') then
            add('guest-provoke','ability','Provoke','enemy',{Combat='combat',Cooldown=8,PerTargetCooldown=15});
        end
        if hasJob('WAR') or hasJob('PLD') then
            add('guest-defender','ability','Defender','self',{SelfHPBelow=70,Combat='combat',MissingBuff='Defender',Cooldown=10});
        end
    end
    local addRangedCore=function()
        add('guest-ranged-attack','ranged','Ranged Attack','enemy',{Property='in_battle',Operator='yes',Combat='combat',Range=20,Cooldown=4});
        add('guest-ranged-ws','ws_auto',nil,'enemy',{TP=1000,Combat='combat',Ranged=true,Cooldown=3,PerTargetCooldown=3});
        if hasJob('RNG') then
            add('guest-sharpshot','ability','Sharpshot','self',{Combat='combat',MissingBuff='Sharpshot',Cooldown=10});
            add('guest-barrage','ability','Barrage','self',{Combat='combat',SelfTPBelow=1000,Cooldown=10});
            add('guest-shadowbind','ability','Shadowbind','enemy',{Combat='combat',Cooldown=10,PerTargetCooldown=30});
        end
        if hasJob('COR') then
            add('guest-phantom-roll','ability','Phantom Roll','party_any',{Combat='any',Cooldown=10,PerTargetCooldown=30});
            add('guest-double-up','ability','Double-Up','self',{Combat='any',Cooldown=8});
            add('guest-quick-draw','ability','Quick Draw','enemy',{Combat='combat',Cooldown=8,PerTargetCooldown=15});
        end
    end
    local addCasterCore=function()
        local nukeActions={'Thunder IV','Blizzard IV','Fire IV','Aero IV','Water IV','Stone IV','Thunder III','Blizzard III','Fire III','Aero III','Water III','Stone III','Thunder II','Blizzard II','Fire II','Aero II','Water II','Stone II'};
        add('guest-stun-cast','spell','Stun','enemy',{Property='casting',Operator='yes',Combat='combat',Cooldown=3,PerTargetCooldown=6});
        add('guest-stun-tp','spell','Stun','enemy',{Property='readying_tp_move',Operator='yes',Combat='combat',Cooldown=3,PerTargetCooldown=6});
        add('guest-sleep-add','spell',{'Sleep II','Sleep'},'enemy',{Property='add',Operator='yes',Combat='combat',SelfMPAbove=25,Cooldown=8,PerTargetCooldown=30});
        add('guest-dispel','spell','Dispel','enemy',{Property='enemy_dispellable',Operator='yes',Combat='combat',SelfMPAbove=20,Cooldown=8,PerTargetCooldown=15});
        add('guest-drain','spell','Drain','enemy',{SelfHPBelow=75,Combat='combat',Cooldown=8,PerTargetCooldown=20});
        add('guest-aspir','spell','Aspir','enemy',{SelfMPBelow=60,ManaTarget=true,Combat='combat',Cooldown=10,PerTargetCooldown=30});
        add('guest-elemental-seal','ability','Elemental Seal','self',{Combat='combat',SelfMPAbove=25,Cooldown=30});
        add('guest-elemental-nuke','spell',nukeActions,'enemy',{Combat='combat',SelfMPAbove=10,Cooldown=3,PerTargetCooldown=3});
    end
    if hasJob('WHM') or hasJob('RDM') or hasJob('PLD') or hasJob('SCH') then addCures(); end
    if hasJob('PLD') or hasJob('RUN') or hasJob('NIN') then addTankCore(); end
    if hasJob('RNG') or hasJob('COR') then addRangedCore(); end
    if hasJob('BLM') or hasJob('RDM') or hasJob('SCH') or hasJob('DRK') then addCasterCore(); end
    if hasJob('BRD') then
        add('guest-pianissimo','ability','Pianissimo','self',{Combat='any',Cooldown=10});
        add('guest-march','spell',{'Victory March','Advancing March'},'party_melee',{MissingBuff='March',Combat='any',SelfMPAbove=10,Cooldown=10,PerTargetCooldown=30});
        add('guest-ballad','spell',{'Mage\'s Ballad III','Mage\'s Ballad II','Mage\'s Ballad'},'mp',{TargetMPBelow=80,Combat='any',SelfMPAbove=10,Cooldown=10,PerTargetCooldown=30});
        add('guest-elegy','spell',{'Carnage Elegy','Battlefield Elegy'},'enemy',{Combat='combat',SelfMPAbove=10,Cooldown=8,PerTargetCooldown=30});
    end
    if hasJob('RDM') then
        add('guest-refresh','spell','Refresh','mp',{MissingBuff='Refresh',TargetMPBelow=80,SelfMPAbove=20,Combat='any',PerTargetCooldown=15});
        add('guest-haste','spell','Haste','party_melee',{MissingBuff='Haste',SelfMPAbove=35,Combat='any',PerTargetCooldown=15});
        add('guest-convert','ability','Convert','self',{SelfMPBelow=15,SelfHPAbove=70,Combat='combat',Cooldown=60});
    end
    if hasJob('WAR') then
        add('guest-berserk','ability','Berserk','self',{SelfHPAbove=70,Combat='combat',MissingBuff='Berserk',Cooldown=8});
        add('guest-warcry','ability','Warcry','self',{Combat='combat',Cooldown=15});
        add('guest-aggressor','ability','Aggressor','self',{Combat='combat',MissingBuff='Aggressor',Cooldown=12});
    end
    if hasJob('MNK') then
        add('guest-boost','ability','Boost','self',{Combat='combat',Cooldown=10});
        add('guest-focus','ability','Focus','self',{Combat='combat',MissingBuff='Focus',Cooldown=10});
    end
    if hasJob('SAM') then
        add('guest-hasso','ability','Hasso','self',{Combat='any',MissingBuff='Hasso',Cooldown=8});
        add('guest-meditate','ability','Meditate','self',{SelfTPBelow=1000,Combat='combat',Cooldown=10});
        add('guest-third-eye','ability','Third Eye','self',{Property='has_hate',Operator='yes',Combat='combat',Cooldown=8});
    end
    if hasJob('THF') then
        add('guest-sneak-attack','ability','Sneak Attack','self',{Combat='combat',Cooldown=10});
        add('guest-trick-attack','ability','Trick Attack','self',{Combat='combat',Cooldown=10});
    end
    if hasJob('DNC') then
        add('guest-curing-waltz','ability','Curing Waltz','lowest',{TargetHPBelow=55,Combat='any',Cooldown=3,PerTargetCooldown=4});
        add('guest-violent-flourish','ability','Violent Flourish','enemy',{Property='casting',Operator='yes',Combat='combat',Cooldown=8});
    end
    addWS('guest-weapon-skill');
    addAttack();
    return r;
end
function E.flash_sheet()
    S.ui.sheetFlashUntil=E.now()+0.35;
end
function E.job_combo_label()
    local ctx=E.context('ui-job-label');
    if S.ui.roleTab=='partyguest' then
        local selectedId=S.ui.selectedActorId;
        for _,m in ipairs((ctx and ctx.party) or {}) do
            if selectedId and E.is_controllable_guest_member(ctx,m) and m.id==selectedId and m.mainJob then
                return string.upper(tostring(m.name or S.ui.selectedActorName or 'Guest')..' - '..tostring(m.mainJob or 'UNK')..'/'..tostring(m.subJob or 'NONE'));
            end
        end
        local name=S.ui.selectedActorName or S.ui.trustPlaceholder or 'Guest';
        local combo=E.trust_combo(name,S.ui.guestSourceRole or S.ui.roleTab);
        return string.upper(tostring(name)..' - '..combo);
    end
    if S.ui.roleTab=='partyhuman' then
        local name=S.ui.selectedActorName or 'Party Member';
        local selectedId=S.ui.selectedActorId;
        for _,m in ipairs((ctx and ctx.party) or {}) do
            if selectedId and m.id==selectedId and m.mainJob then
                return string.upper(tostring(m.name or name)..' - '..tostring(m.mainJob or 'UNK')..'/'..tostring(m.subJob or 'NONE'));
            end
        end
        return string.upper(tostring(name)..' - GAMBITS DISABLED');
    end
    if S.ui.roleTab=='partyguest_unavailable' then
        local name=S.ui.selectedActorName or S.ui.trustPlaceholder or 'Trust';
        return string.upper(tostring(name)..' - TRUST GAMBITS DISABLED');
    end
    if ctx and ctx.mainJob then
        return string.upper(tostring((ctx.self and ctx.self.name) or S.identity or 'Player')..' - '..tostring(ctx.mainJob)..'/'..tostring(ctx.subJob or 'NONE'));
    end
    return 'PLAYER - UNKNOWN/NONE';
end
function E.editor_catalog_context()
    local ctx=E.context('catalog');
    if S.ui.roleTab=='partyhuman' then return ctx,'disabled'; end
    if S.ui.roleTab~='partyguest' and not S.ui.selectedActorName then return ctx,'player'; end

    local member=E.selected_guest_member(ctx);
    local combo=member and member.mainJob and (tostring(member.mainJob)..'/'..tostring(member.subJob or 'NONE'))
        or E.trust_combo(S.ui.selectedActorName or S.ui.trustPlaceholder,S.ui.guestSourceRole or S.ui.roleTab);
    local main,sub=E.split_job_combo(combo);
    local mainLevel=E.player_level_cap(ctx);
    local subLevel=(sub and sub~='NONE') and math.min(mainLevel,37) or 0;

    ctx.catalogActorKind='guest';
    ctx.generatedRecruit=E.is_generated_recruit(member);
    ctx.catalogActorId=member and member.id or nil;
    ctx.catalogActorIndex=member and member.entityIndex or nil;
    ctx.catalogActorName=(member and member.name) or S.ui.selectedActorName or S.ui.trustPlaceholder or 'Guest Trust';
    ctx.mainJob=main;
    ctx.subJob=sub;
    ctx.mainJobId=JOB_IDS[main] or 0;
    ctx.subJobId=JOB_IDS[sub] or 0;
    ctx.mainLevel=mainLevel;
    ctx.subLevel=subLevel;
    return ctx,'guest';
end
function E.profile_button_label()
    local ctx=E.context('ui-profile');
    if ctx and ctx.self and ctx.self.name then return ctx.self.name; end
    return S.identity or 'Character';
end
function E.party_slot_entries()
    local ctx=E.context('ui-party');
    local byPartyIndex={};
    for _,m in ipairs((ctx and ctx.party) or {}) do
        byPartyIndex[m.index]=m;
    end
    local out={};
    for i=1,6 do
        local m=byPartyIndex[i-1];
        local memoryFallback=nil;
        if i>1 and not m then
            memoryFallback=E.party_slot_memory_entry(ctx,i-1);
        end
        if m then
            local classification=E.party_member_classification(ctx,m);
            out[i]={name=(m.name and m.name~='') and m.name or 'vacant', id=m.id, partyIndex=m.index, alive=m.alive,
                mainJob=m.mainJob, subJob=m.subJob, isTrust=classification.isTrust,
                isGeneratedRecruit=E.is_generated_recruit(m),
                isTrustUnavailable=classification.isTrustUnavailable, isHuman=classification.isHuman,
                readyReason=classification.readyReason};
        else
            out[i]=memoryFallback or {name='vacant'};
        end
    end
    E.pending_recruit_resolve(out);
    return out;
end
function E.party_slot_labels()
    local entries=E.party_slot_entries();
    local out={}; for i,entry in ipairs(entries) do out[i]=entry.name; end
    return out;
end
function E.select_main_sheet()
    local changed=S.ui.roleTab~='main' or S.ui.selectedActorName~=nil;
    S.ui.roleTab='main';
    S.ui.selectedActorName=nil;
    S.ui.selectedActorId=nil;
    S.ui.selectedActorPartyIndex=nil;
    S.ui.selectedActorReason=nil;
    S.ui.trustPlaceholder=nil;
    if changed then S.ui.edits={}; S.catalog=nil; E.flash_sheet(); end
end
function E.select_guest_sheet(name,source,actorId,partyIndex)
    E.select_main_sheet();
end
function E.select_human_party_member(name,actorId,partyIndex)
    E.select_main_sheet();
end
function E.select_unavailable_guest_member(name,actorId,partyIndex,reason)
    E.select_main_sheet();
end
function E.ui_scale()
    local percent=E.number((S.settings or DEFAULT).UiScalePercent,DEFAULT.UiScalePercent) or DEFAULT.UiScalePercent;
    percent=math.max(70,math.min(200,math.floor((percent+5)/10)*10));
    return percent/100,percent;
end
function E.s(value)
    local scale=E.ui_scale();
    return math.max(1,math.floor((value or 0)*scale+0.5));
end
function E.ui_button_h()
    return E.s(22);
end
function E.ui_row_h()
    return E.s(28);
end
function E.ui_icon_w()
    return E.s(26);
end
function E.ui_outer_border()
    return E.s(8);
end
function E.ui_window_size()
    return E.s(1080),E.s(619);
end
function E.visible_gambit_rows()
    return MAX_GAMBIT_ROWS;
end
function E.push_scaled_ui_style()
    if not imgui or not imgui.PushStyleVar then return 0; end
    local pushed=0;
    local function push(name,value)
        local id=rawget(_G,name);
        if id==nil then return; end
        local ok=pcall(imgui.PushStyleVar,id,value);
        if ok then pushed=pushed+1; end
    end
    push('ImGuiStyleVar_WindowPadding',{E.s(8),E.s(8)});
    push('ImGuiStyleVar_FramePadding',{E.s(4),E.s(3)});
    push('ImGuiStyleVar_ItemSpacing',{E.s(6),E.s(4)});
    push('ImGuiStyleVar_ItemInnerSpacing',{E.s(4),E.s(4)});
    return pushed;
end
function E.push_resolution_ui_font(scale)
    scale=E.number(scale,1) or 1;
    if scale<=0 then scale=1; end
    if imgui and imgui.GetFont and imgui.GetFontSize and imgui.PushFont then
        local ok,font=pcall(imgui.GetFont);
        local okSize,size=pcall(imgui.GetFontSize);
        if ok and okSize and font and type(size)=='number' and size>0 then
            local pushed=pcall(imgui.PushFont,font,size*scale);
            if pushed then return {mode='pushfont'}; end
        end
    end
    if imgui and imgui.SetWindowFontScale then
        return {mode='window',scale=scale};
    end
    return nil;
end
function E.apply_resolution_ui_font(state)
    if state and state.mode=='window' and imgui and imgui.SetWindowFontScale then
        imgui.SetWindowFontScale(state.scale or 1);
    end
end
function E.pop_resolution_ui_font(state)
    if not state then return; end
    if state.mode=='pushfont' and imgui and imgui.PopFont then
        pcall(imgui.PopFont);
    elseif state.mode=='window' and imgui and imgui.SetWindowFontScale then
        imgui.SetWindowFontScale(1.0);
    end
end
function E.ui_scale_change(delta)
    local _,percent=E.ui_scale();
    local nextPercent=math.max(70,math.min(200,percent+(delta or 0)));
    return E.settings_change('UiScalePercent',nextPercent);
end
function E.display_height()
    if imgui and imgui.GetIO then
        local ok,io=pcall(imgui.GetIO);
        local size=ok and io and io.DisplaySize or nil;
        if type(size)=='table' then return E.number(size[2] or size.y,0) or 0; end
    end
    return 0;
end
function E.max_visible_gambit_rows(windowH)
    local maxRows=99;
    if imgui and imgui.GetWindowPos then
        local ok,pos=pcall(imgui.GetWindowPos);
        local screenH=E.display_height();
        local y=ok and type(pos)=='table' and E.number(pos[2] or pos.y,0) or 0;
        if screenH and screenH>0 then
            local current=E.visible_gambit_rows();
            local base=(windowH or 0)-(E.ui_row_h()*current);
            local fit=math.floor(((screenH-y-E.s(6))-base)/E.ui_row_h());
            maxRows=math.max(MIN_GAMBIT_VIEW_ROWS,math.min(99,fit));
        end
    end
    return maxRows;
end
function E.draw_resize_triangle(draw,p1,p2,p3,hovered)
    if not draw or not draw.AddTriangleFilled then return; end
    local color=hovered and 0xFFFFD447 or 0xFF8A6A14;
    pcall(function() draw:AddTriangleFilled(p1,p2,p3,color); end);
end
function E.resize_handle_button(id,pos,size,windowH)
    if not (imgui and imgui.SetCursorScreenPos and imgui.InvisibleButton) then return false,false; end
    imgui.SetCursorScreenPos(pos);
    imgui.InvisibleButton(id,size);
    local hovered=(imgui.IsItemHovered and imgui.IsItemHovered()) or false;
    local active=(imgui.IsItemActive and imgui.IsItemActive()) or false;
    if (hovered or active) and imgui.SetMouseCursor then
        local cursor=rawget(_G,'ImGuiMouseCursor_ResizeNS');
        if cursor~=nil then pcall(imgui.SetMouseCursor,cursor); end
    end
    if active and imgui.GetMouseDragDelta then
        if S.ui.resizeActive~=id then
            S.ui.resizeActive=id;
            S.ui.resizeStartRows=E.visible_gambit_rows();
            S.ui.resizeLastSavedRows=nil;
        end
        local delta=imgui.GetMouseDragDelta(0);
        local dy=type(delta)=='table' and E.number(delta[2] or delta.y,0) or 0;
        local rows=math.floor((S.ui.resizeStartRows or E.visible_gambit_rows())+(dy/E.ui_row_h())+0.5);
        rows=math.floor(E.clamp(rows,MIN_GAMBIT_VIEW_ROWS,E.max_visible_gambit_rows(windowH))+0.5);
        local settings=S.settings or DEFAULT;
        settings.VisibleGambitRows=rows;
    end
    return hovered,active;
end
function E.ui_vertical_resize_handle(windowW,windowH)
    if not (imgui and imgui.GetWindowPos) then return; end
    local ok,pos=pcall(imgui.GetWindowPos);
    if not ok or type(pos)~='table' then return; end
    local x=E.number(pos[1] or pos.x,0) or 0;
    local y=E.number(pos[2] or pos.y,0) or 0;
    local bottom=y+(windowH or E.s(560));
    local right=x+(windowW or E.s(890));
    local handleW,handleH=E.s(58),E.s(18);
    local leftPos={x+E.s(2),bottom-handleH-E.s(2)};
    local rightPos={right-handleW-E.s(2),bottom-handleH-E.s(2)};
    local leftHover,leftActive=E.resize_handle_button('##gambit-resize-left',leftPos,{handleW,handleH},windowH);
    local rightHover,rightActive=E.resize_handle_button('##gambit-resize-right',rightPos,{handleW,handleH},windowH);
    local draw=imgui.GetWindowDrawList and imgui.GetWindowDrawList() or nil;
    local tri=E.s(13);
    local pad=E.s(7);
    E.draw_resize_triangle(draw,{x+pad,bottom-pad},{x+pad+tri,bottom-pad},{x+pad,bottom-pad-tri},leftHover or leftActive);
    E.draw_resize_triangle(draw,{right-pad,bottom-pad},{right-pad-tri,bottom-pad},{right-pad,bottom-pad-tri},rightHover or rightActive);
    if S.ui.resizeActive and imgui.IsMouseReleased and imgui.IsMouseReleased(0) then
        local rows=E.visible_gambit_rows();
        E.settings_change('VisibleGambitRows',rows);
        S.ui.resizeActive=nil;
        S.ui.resizeStartRows=nil;
        if imgui.ResetMouseDragDelta then imgui.ResetMouseDragDelta(0); end
    end
end
function E.ui_scale_controls()
    local _,percent=E.ui_scale();
    local btnW=E.s(24);
    local percentW=E.s(44);
    local gap=E.s(3);
    local closePad=E.s(46);
    local winW=imgui.GetWindowWidth and E.number(imgui.GetWindowWidth(),E.s(848)) or E.s(848);
    local startX=math.max(E.s(300),winW-closePad-percentW-gap-btnW-gap-btnW);
    local oldX=imgui.GetCursorPosX and imgui.GetCursorPosX() or nil;
    local oldY=imgui.GetCursorPosY and E.number(imgui.GetCursorPosY()) or nil;
    if imgui.SetCursorPosY then imgui.SetCursorPosY(E.s(3)); end
    if imgui.SetCursorPosX then imgui.SetCursorPosX(startX); end
    if E.help_button('-##ui-title-scale-down',{btnW,E.s(18)},'Shrink the Gambits window controls and text by 10%.') then E.notify_save(E.ui_scale_change(-10)); end
    imgui.SameLine();
    imgui.Text(tostring(percent)..'%');
    imgui.SameLine();
    if E.help_button('+##ui-title-scale-up',{btnW,E.s(18)},'Enlarge the Gambits window controls and text by 10%.') then E.notify_save(E.ui_scale_change(10)); end
    if oldY and imgui.SetCursorPosY then imgui.SetCursorPosY(oldY); end
    if oldX and imgui.SetCursorPosX then imgui.SetCursorPosX(oldX); end
end
function E.trust_summon_block_reason(ctx)
    return 'Recruit Trusts at world anchors. Manual summoning is disabled.';
end
function E.request_trust_spawn(trustKey,slotIndex,ctx)
    trustKey=tostring(trustKey or ''):upper();
    local entry=TRUST_PICKER_BY_KEY and TRUST_PICKER_BY_KEY[trustKey] or nil;
    if not entry then return false,'Unknown Trust'; end
    ctx=ctx or E.context('trust-spawn');
    local leaderOk,leaderReason=E.trust_control_allowed(ctx);
    if not leaderOk then
        local msg=leaderReason or 'Only the party leader can control Trust Gambits.';
        E.set_message(msg,5);
        return false,msg;
    end
    local blocked=E.trust_summon_block_reason(ctx);
    if blocked then E.set_message(blocked,5); return false,blocked; end
    local command=E.bridge_spawn_command(trustKey);
    if not command then return false,'Unknown Trust'; end
    local ok,err=E.send_bridge_command(command);
    if ok then
        S.ui.pendingRecruit={trust=entry.name,key=entry.key,expiresAt=E.now()+12};
        if slotIndex then
            S.ui.pendingRecruitSlots=S.ui.pendingRecruitSlots or {};
            S.ui.pendingRecruitSlots[slotIndex]={trust=entry.name,key=entry.key,expiresAt=E.now()+12};
        end
        E.select_guest_sheet(entry.name,'partyguest',nil,nil);
        E.set_message('Summoning '..entry.name..'.',4);
        return true,'Trust request sent';
    end
    return false,err;
end
function E.release_selected_trust()
    if S.ui.roleTab~='partyguest' then return false,'Open a Trust sheet before using RELEASE.'; end
    local ctx=E.context('release-trust');
    local leaderOk,leaderReason=E.trust_control_allowed(ctx);
    if not leaderOk then return false,leaderReason or 'Only the party leader can control Trust Gambits.'; end
    local actor=E.selected_guest_member(ctx);
    if not actor then return false,'The currently viewed Trust is not active in your party.'; end
    local command=E.bridge_release_command(actor);
    if not command then return false,'Selected Trust cannot be released yet.'; end
    local ok,err=E.send_bridge_command(command);
    if ok then
        if actor.id then S.recruitStances[E.number(actor.id)]=nil; end
        E.set_message('Releasing '..tostring(actor.name or S.ui.selectedActorName or 'Trust')..'.',4);
        return true,'Trust release request sent';
    end
    return false,err or 'Trust release request failed';
end
function E.team_path()
    local root=E.root();
    if not root then return nil,'No Ashita install path'; end
    return root .. 'teams/default.lua';
end
function E.team_entry_from_name(name)
    return E.trust_picker_entry_by_name(name);
end
function E.team_current_entries()
    local out={};
    local slots=E.party_slot_entries();
    for i=2,6 do
        local entry=slots[i];
        if entry and entry.name and entry.name~='vacant' then
            local trust=E.team_entry_from_name(entry.name);
            if trust then
                out[#out+1]={key=trust.key,name=trust.name,label=trust.label or trust.name,slot=i};
            end
        end
    end
    return out;
end
function E.save_team()
    local path,err=E.team_path();
    if not path then return false,err; end
    local team=E.team_current_entries();
    if #team==0 then return false,'No Trusts in party slots 2-6 to save.'; end
    E.mkdir(E.root() .. 'teams/');
    local value={Version=1,SavedAt=os.date('%Y-%m-%d %H:%M:%S'),Trusts=team};
    local ok,txt=E.writefile(path,value,'Gambits saved Trust team. LOAD TEAM summons these Trusts left to right.');
    if ok then
        S.savedTeam=value;
        E.set_message('Saved team: '..tostring(#team)..' Trust'..(#team==1 and '' or 's')..'.',4);
    end
    return ok,txt;
end
function E.load_saved_team()
    local path,err=E.team_path();
    if not path then return nil,err; end
    local txt,readErr=E.readfile(path);
    if not txt then return nil,readErr or 'No saved team yet. Use SAVE TEAM first.'; end
    local data,parseErr=E.parse(txt,path);
    if type(data)~='table' or type(data.Trusts)~='table' then return nil,parseErr or 'Saved team file is invalid.'; end
    S.savedTeam=data;
    return data;
end
function E.load_team()
    local team,err=E.load_saved_team();
    if not team then return false,err; end
    local ctx=E.context('load-team');
    local blocked=E.trust_summon_block_reason(ctx);
    if blocked then E.set_message(blocked,5); return false,blocked; end
    local slots=E.party_slot_entries();
    local present={}; local vacancies=0;
    for i=2,6 do
        local entry=slots[i];
        if entry and entry.name and entry.name~='vacant' then
            local trust=E.team_entry_from_name(entry.name);
            if trust then present[trust.key]=true; end
        else
            vacancies=vacancies+1;
        end
    end
    if vacancies<=0 then return false,'No vacant Trust party slots.'; end
    local queue={};
    for _,saved in ipairs(team.Trusts or {}) do
        if #queue>=vacancies then break; end
        local key=tostring(saved.key or ''):upper();
        local entry=TRUST_PICKER_BY_KEY and TRUST_PICKER_BY_KEY[key] or nil;
        if entry and not present[key] then
            present[key]=true;
            queue[#queue+1]={key=key,name=entry.name,slot=saved.slot or (#queue+2)};
        end
    end
    if #queue>0 then
        S.teamLoad={queue=queue,index=1,nextAt=0,lastSentAt=0,sent=0,total=#queue};
        E.set_message('Loading team: queued '..tostring(#queue)..' Trust'..(#queue==1 and '' or 's')..' in saved order.',5);
        return true,'Team summon queue started';
    end
    return false,'Saved team Trusts are already present or unavailable.';
end
function E.team_load_state(ctx)
    local slots=E.party_slot_entries();
    local present={}; local vacancies=0;
    for i=2,6 do
        local slot=slots[i];
        if slot and slot.name and slot.name~='vacant' then
            local trust=E.team_entry_from_name(slot.name);
            if trust then present[trust.key]=true; end
        else
            vacancies=vacancies+1;
        end
    end
    return present,vacancies;
end
function E.process_team_load(ctx)
    local load=S.teamLoad;
    if type(load)~='table' then return false; end
    local now=E.now();
    if now<(load.nextAt or 0) then return true; end
    local blocked=E.trust_summon_block_reason(ctx);
    if blocked then
        S.teamLoad=nil;
        E.set_message('LOAD TEAM stopped: '..blocked,5);
        return false;
    end
    local present,vacancies=E.team_load_state(ctx);
    if vacancies<=0 then
        S.teamLoad=nil;
        E.set_message('LOAD TEAM stopped: party is full.',5);
        return false;
    end
    while load.index<=#load.queue do
        local item=load.queue[load.index];
        load.index=load.index+1;
        local key=tostring(item and item.key or ''):upper();
        local entry=TRUST_PICKER_BY_KEY and TRUST_PICKER_BY_KEY[key] or nil;
        if entry and not present[key] then
            local ok,err=E.request_trust_spawn(key,item.slot,ctx);
            if ok then
                load.sent=(load.sent or 0)+1;
                load.lastSentAt=now;
                load.nextAt=now+3.0;
                E.set_message('Loading team: '..tostring(load.sent)..'/'..tostring(load.total or #load.queue)..' sent, waiting for party slot.',4);
                return true;
            end
            load.nextAt=now+1.0;
            E.log('LOAD TEAM skipped '..tostring(entry.name or key)..': '..tostring(err or 'request failed'),true);
            return true;
        end
    end
    local sent=load.sent or 0;
    S.teamLoad=nil;
    E.set_message('LOAD TEAM finished: sent '..tostring(sent)..' Trust summon request'..(sent==1 and '' or 's')..'.',5);
    return false;
end
function E.trust_spawn_picker(slotIndex)
    local pickerId=tostring(slotIndex or 'top');
    local popup='trust-spawn-picker-'..pickerId;
    if E.popup_begin(popup) then
        local filter=E.buffer('trust-spawn-filter-'..pickerId,'');
        E.help_search_input_text('Filter##trust-spawn-filter-input-'..pickerId,filter,80,'Filter Trusts by job or name.');
        if E.picker_child_begin('##trust-spawn-scroll-'..pickerId,360,420) then
            local needle=E.lower(filter[1] or '');
            for _,entry in ipairs(TRUST_PICKER or {}) do
                local label=entry.label or entry.name;
                if needle=='' or E.lower(label):find(needle,1,true) then
                    if E.help_selectable(label..'##trust-spawn-'..entry.key..'-'..pickerId,false,'Summon '..tostring(label)..' if Trust rules allow.') then
                        E.notify_save(E.request_trust_spawn(entry.key,nil));
                        E.popup_close();
                    end
                end
            end
        end
        E.picker_child_end();
        E.popup_end();
    end
end
function E.push_recruit_slot_colors(role,vacant)
    local pool=JOB_IDS[role] and 'job' or E.recruit_role_pool(role);
    local colors={
        tank={vacant={0.08,0.15,0.24,1},occupied={0.15,0.27,0.43,1}},
        support={vacant={0.08,0.17,0.11,1},occupied={0.14,0.31,0.19,1}},
        dps={vacant={0.21,0.09,0.09,1},occupied={0.38,0.15,0.14,1}},
        job={vacant={0.36,0.29,0.06,1},occupied={0.53,0.42,0.09,1}},
    };
    local palette=colors[pool] or colors.dps;
    local base=vacant and palette.vacant or palette.occupied;
    local pushed=0;
    local buttonId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    local textId=rawget(_G,'ImGuiCol_Text');
    if buttonId~=nil then imgui.PushStyleColor(buttonId,base); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{base[1]*1.25,base[2]*1.25,base[3]*1.25,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{base[1]*1.40,base[2]*1.40,base[3]*1.40,1}); pushed=pushed+1; end
    if vacant and textId~=nil then
        imgui.PushStyleColor(textId,pool=='job' and {0.96,0.85,0.43,1} or {0.58,0.58,0.58,1});
        pushed=pushed+1;
    end
    return pushed;
end
function E.recruit_role_pool(role)
    if role=='tank' or role=='support' or role=='dps' then return role; end
    local job=JOB_IDS[role];
    if job==1 or job==7 or job==13 or job==22 then return 'tank'; end
    if job==3 or job==5 or job==10 or job==15 or job==17 or job==19 or job==20 or job==21 then return 'support'; end
    return 'dps';
end
function E.recruit_slot_choices()
    local choices={'tank','support','dps'};
    local ctx=E.context('recruit-job-choices');
    if not ctx.self or ctx.self.id~=S.recruitJobActor then return choices; end
    local mask=S.recruitJobMask or 0;
    for id,job in ipairs(JOBS) do
        if bit.band(mask,bit.lshift(1,id-1))~=0 then choices[#choices+1]=job; end
    end
    return choices;
end
function E.next_recruit_slot_choice(role)
    local choices=E.recruit_slot_choices();
    for i,choice in ipairs(choices) do
        if choice==role then return choices[(i%#choices)+1]; end
    end
    return choices[1];
end
function E.recruit_slot_label(role)
    local names={WAR='WARRIOR',MNK='MONK',WHM='WHITE MAGE',BLM='BLACK MAGE',RDM='RED MAGE',
        THF='THIEF',PLD='PALADIN',DRK='DARK KNIGHT',BST='BEASTMASTER',BRD='BARD',RNG='RANGER',
        SAM='SAMURAI',NIN='NINJA',DRG='DRAGOON',SMN='SUMMONER',BLU='BLUE MAGE',COR='CORSAIR',
        PUP='PUPPETMASTER',DNC='DANCER',SCH='SCHOLAR',GEO='GEOMANCER',RUN='RUNE FENCER'};
    return names[role] or ('vacant | '..role:upper());
end
function E.ui_party_slots()
    local slots=E.party_slot_entries();
    local windowW=select(1,E.ui_window_size());
    local availW=math.max(E.s(792),(windowW or E.s(1080))-(E.ui_outer_border()*2));
    local gap=E.s(8);
    local slotW=math.floor((availW-(gap*(#slots-1)))/#slots);
    local lastSlotW=availW-(slotW*(#slots-1))-(gap*(#slots-1));
    local rowX=imgui.GetCursorPosX();
    for i,entry in ipairs(slots) do
        if i>1 then imgui.SameLine(); imgui.SetCursorPosX(rowX+((slotW+gap)*(i-1))); end
        local name=tostring(entry.name or 'vacant');
        local width=(i==#slots) and lastSlotW or slotW;
        local slot=i-1;
        local role=(S.recruitSlotRoles or {})[slot] or ({'tank','support','dps','dps','dps'})[slot];
        if i>1 and name=='vacant' then
            local pushed=E.push_recruit_slot_colors(role,true);
            if E.help_button(E.recruit_slot_label(role)..'##party-slot-'..i,{width,E.ui_button_h()},
                'Click to cycle pools and this character\'s level-75 jobs. Selection saves after three seconds.') then
                local nextRole=E.next_recruit_slot_choice(role);
                local ok,why=E.queue_recruit_slot_role(slot,nextRole);
                if ok then S.recruitSlotRoles[slot]=nextRole;
                else E.set_message(tostring(why),4); end
            end
            if pushed>0 then imgui.PopStyleColor(pushed); end
        elseif imgui.BeginDisabled and imgui.EndDisabled then
            local recruit=i>1 and entry.isGeneratedRecruit==true;
            local pushed=recruit and E.push_recruit_slot_colors(role,false) or 0;
            imgui.BeginDisabled(true);
            E.help_button(name..'##party-slot-'..i,{width,E.ui_button_h()},'Party member name only. Gambits edit your character.');
            imgui.EndDisabled();
            if pushed>0 then imgui.PopStyleColor(pushed); end
        else
            imgui.Text(name);
        end
    end
end
function E.small_disabled_arrow(label)
    local pushed=0;
    if rawget(_G,'ImGuiStyleVar_Alpha') and imgui.PushStyleVar then
        imgui.PushStyleVar(rawget(_G,'ImGuiStyleVar_Alpha'),0.35); pushed=1;
    end
    E.help_button(label,{E.ui_icon_w(),E.ui_button_h()},'Row cannot move farther.');
    if pushed>0 and imgui.PopStyleVar then imgui.PopStyleVar(pushed); end
end
function E.ui_column_header(label,id,w,helpText)
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    if colorId~=nil then imgui.PushStyleColor(colorId,{0.16,0.13,0.08,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.16,0.13,0.08,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{0.16,0.13,0.08,1}); pushed=pushed+1; end
    E.help_button(tostring(label or '')..'##gambit-header-'..tostring(id),{w,E.ui_button_h()},helpText or 'Gambit table column.');
    if pushed>0 then imgui.PopStyleColor(pushed); end
end
function E.ui_grid_columns(rowW,numW,arrowW,onW,targetW,cond1W,cond2W,actionW,deleteW,gap)
    gap=gap or 8;
    local x=0;
    local cols={};
    cols.num={x=x,w=numW}; x=x+numW+gap;
    cols.move={x=x,w=arrowW}; x=x+arrowW+gap;
    cols.on={x=x,w=onW}; x=x+onW+gap;
    cols.target={x=x,w=targetW}; x=x+targetW+gap;
    cols.condition1={x=x,w=cond1W}; x=x+cond1W+gap;
    cols.condition2={x=x,w=cond2W}; x=x+cond2W+gap;
    cols.action={x=x,w=actionW}; x=x+actionW+gap;
    cols.delete={x=x,w=deleteW};
    cols.total=math.max(rowW,x+deleteW);
    cols.gap=gap;
    return cols;
end
function E.ui_grid_cell(rowX,col)
    imgui.SameLine();
    imgui.SetCursorPosX(rowX+col.x);
end
function E.push_add_gambit_colors()
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    local textId=rawget(_G,'ImGuiCol_Text');
    if colorId~=nil then imgui.PushStyleColor(colorId,{0.48,0.36,0.08,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.95,0.74,0.16,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{1.0,0.84,0.28,1}); pushed=pushed+1; end
    if textId~=nil then imgui.PushStyleColor(textId,{0.08,0.06,0.02,1}); pushed=pushed+1; end
    return pushed;
end
function E.push_release_button_colors()
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    if colorId~=nil then imgui.PushStyleColor(colorId,{0.46,0.10,0.08,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.68,0.14,0.10,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{0.88,0.20,0.14,1}); pushed=pushed+1; end
    return pushed;
end
function E.push_move_flash_colors()
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    local textId=rawget(_G,'ImGuiCol_Text');
    if colorId~=nil then imgui.PushStyleColor(colorId,{0.12,0.52,0.24,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.18,0.68,0.34,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{0.24,0.82,0.44,1}); pushed=pushed+1; end
    if textId~=nil then imgui.PushStyleColor(textId,{0.94,1.0,0.88,1}); pushed=pushed+1; end
    return pushed;
end
function E.push_sheet_flash_colors()
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    local textId=rawget(_G,'ImGuiCol_Text');
    if colorId~=nil then imgui.PushStyleColor(colorId,{0.82,0.62,0.10,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.95,0.74,0.16,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{1.0,0.84,0.28,1}); pushed=pushed+1; end
    if textId~=nil then imgui.PushStyleColor(textId,{0.08,0.06,0.02,1}); pushed=pushed+1; end
    return pushed;
end
function E.push_dimmed_row_colors()
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    local textId=rawget(_G,'ImGuiCol_Text');
    if colorId~=nil then imgui.PushStyleColor(colorId,{0.13,0.11,0.08,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.18,0.15,0.10,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{0.22,0.18,0.12,1}); pushed=pushed+1; end
    if textId~=nil then imgui.PushStyleColor(textId,{0.47,0.44,0.36,1}); pushed=pushed+1; end
    return pushed;
end
function E.push_onoff_button_colors(enabled)
    local pushed=0;
    local colorId=rawget(_G,'ImGuiCol_Button');
    local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
    local activeId=rawget(_G,'ImGuiCol_ButtonActive');
    if enabled then
        if colorId~=nil then imgui.PushStyleColor(colorId,{0.12,0.42,0.22,1}); pushed=pushed+1; end
        if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.18,0.60,0.32,1}); pushed=pushed+1; end
        if activeId~=nil then imgui.PushStyleColor(activeId,{0.30,0.76,0.46,1}); pushed=pushed+1; end
    else
        if colorId~=nil then imgui.PushStyleColor(colorId,{0.48,0.12,0.10,1}); pushed=pushed+1; end
        if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.66,0.18,0.14,1}); pushed=pushed+1; end
        if activeId~=nil then imgui.PushStyleColor(activeId,{0.82,0.24,0.18,1}); pushed=pushed+1; end
    end
    return pushed;
end
function E.ui_centered_text(text)
    text=tostring(text or '');
    if imgui.GetContentRegionAvail and imgui.CalcTextSize and imgui.GetCursorPosX and imgui.SetCursorPosX then
        local avail=imgui.GetContentRegionAvail();
        local textSize=imgui.CalcTextSize(text);
        local availW=type(avail)=='table' and E.number(avail[1] or avail.x,0) or 0;
        local textW=type(textSize)=='table' and E.number(textSize[1] or textSize.x,0) or 0;
        if availW>textW and textW>0 then
            imgui.SetCursorPosX(imgui.GetCursorPosX()+math.floor((availW-textW)*0.5));
            imgui.Text(text);
            return;
        end
    end
    imgui.TextWrapped(text);
end
function E.picker_section_header(title,first)
    title=tostring(title or '');
    if not first then imgui.Separator(); end
    local textId=rawget(_G,'ImGuiCol_Text');
    local pushed=0;
    local oldY=imgui.GetCursorPosY and imgui.GetCursorPosY() or nil;
    if imgui.GetWindowDrawList and imgui.GetCursorScreenPos and imgui.GetContentRegionAvail then
        local draw=imgui.GetWindowDrawList();
        local pos=imgui.GetCursorScreenPos();
        local avail=imgui.GetContentRegionAvail();
        local availW=type(avail)=='table' and E.number(avail[1] or avail.x,0) or 0;
        local h=E.s(20);
        if draw and draw.AddRectFilled and type(pos)=='table' and availW>0 then
            local x=E.number(pos[1] or pos.x,0) or 0;
            local y=E.number(pos[2] or pos.y,0) or 0;
            pcall(function() draw:AddRectFilled({x,y},{x+availW,y+h},0xCC1E180F); end);
        end
        if imgui.SetCursorPosY and oldY then imgui.SetCursorPosY(oldY+E.s(2)); end
        local oldX=imgui.GetCursorPosX and E.number(imgui.GetCursorPosX()) or nil;
        if oldX and imgui.SetCursorPosX then imgui.SetCursorPosX(oldX+E.s(6)); end
        if textId~=nil then imgui.PushStyleColor(textId,{0.82,0.63,0.22,1}); pushed=pushed+1; end
        imgui.Text(title);
        if pushed>0 then imgui.PopStyleColor(pushed); end
        if imgui.SetCursorPosY and oldY then imgui.SetCursorPosY(oldY+h+E.s(2)); end
        return;
    end
    if textId~=nil then imgui.PushStyleColor(textId,{0.82,0.63,0.22,1}); pushed=pushed+1; end
    imgui.Text(title);
    if pushed>0 then imgui.PopStyleColor(pushed); end
end
function E.default_help_text()
    return 'Top rows act first. First valid ON row fires. Scroll for more.';
end
function E.fit_help_text(text,width)
    text=tostring(text or E.default_help_text()):gsub('%s+',' ');
    width=E.number(width,0) or 0;
    -- Store complete help; fit only after the child exposes its actual width.
    if width<=0 or not imgui.CalcTextSize then return text; end
    local function measured(value)
        local size=imgui.CalcTextSize(value);
        if type(size)=='table' then return E.number(size[1] or size.x,0) or 0; end
        return E.number(size,0) or 0;
    end
    if measured(text)<=width then return text; end
    local suffix='...';
    if measured(suffix)>width then return ''; end
    local low,high=0,#text;
    while low<high do
        local mid=math.floor((low+high+1)/2);
        if measured(text:sub(1,mid)..suffix)<=width then low=mid; else high=mid-1; end
    end
    -- Never split a multibyte character at the truncation boundary.
    while low>0 do
        local nextByte=text:byte(low+1);
        if not nextByte or nextByte<128 or nextByte>=192 then break; end
        low=low-1;
    end
    return text:sub(1,low)..suffix;
end
function E.set_hover_help(text)
    if not text or text=='' then return; end
    S.ui.helpText=E.fit_help_text(text);
    S.ui.helpSeen=true;
end
function E.hover_help(text)
    if not imgui or not imgui.IsItemHovered then return; end
    local ok,hovered=pcall(imgui.IsItemHovered);
    if ok and hovered then E.set_hover_help(text); end
end
function E.item_hovered()
    if not imgui or not imgui.IsItemHovered then return false; end
    local ok,hovered=pcall(imgui.IsItemHovered);
    return ok and hovered==true;
end
function E.help_button(label,size,helpText)
    local clicked;
    if size~=nil then clicked=imgui.Button(label,size); else clicked=imgui.Button(label); end
    E.hover_help(helpText);
    return clicked;
end
function E.help_selectable(label,selected,helpText)
    local picked=imgui.Selectable(label,selected);
    E.hover_help(helpText);
    return picked;
end
function E.help_input_text(label,buffer,size,helpText)
    local changed=imgui.InputText(label,buffer,size);
    E.hover_help(helpText);
    return changed;
end
function E.help_search_input_text(label,buffer,size,helpText)
    local pushed=0;
    local frameId=rawget(_G,'ImGuiCol_FrameBg');
    local hoverId=rawget(_G,'ImGuiCol_FrameBgHovered');
    local activeId=rawget(_G,'ImGuiCol_FrameBgActive');
    local textId=rawget(_G,'ImGuiCol_Text');
    if frameId~=nil then imgui.PushStyleColor(frameId,{0.18,0.24,0.27,1}); pushed=pushed+1; end
    if hoverId~=nil then imgui.PushStyleColor(hoverId,{0.23,0.33,0.37,1}); pushed=pushed+1; end
    if activeId~=nil then imgui.PushStyleColor(activeId,{0.28,0.43,0.48,1}); pushed=pushed+1; end
    if textId~=nil then imgui.PushStyleColor(textId,{0.98,0.96,0.84,1}); pushed=pushed+1; end
    local changed=imgui.InputText(label,buffer,size);
    if pushed>0 then imgui.PopStyleColor(pushed); end
    E.hover_help(helpText);
    return changed;
end
function E.help_checkbox(label,buffer,helpText)
    local changed=imgui.Checkbox(label,buffer);
    E.hover_help(helpText);
    return changed;
end
function E.ui_help_line(width)
    local alert=S.ui.message and E.now()<(S.ui.messageUntil or 0) and S.ui.message or nil;
    local text=E.fit_help_text(alert or S.ui.helpText or E.default_help_text());
    local lineW=E.number(width,0) or 0;
    if lineW<=0 and imgui.GetContentRegionAvail then
        local avail=imgui.GetContentRegionAvail();
        if type(avail)=='table' then lineW=E.number(avail[1] or avail.x,0) or 0; end
    end
    local textInsetY=E.s(3);
    local lineH=E.ui_button_h()+(textInsetY*2);
    local childFlags=rawget(_G,'ImGuiChildFlags_Borders') or 0;
    local windowFlags=(rawget(_G,'ImGuiWindowFlags_NoScrollbar') or 0)+(rawget(_G,'ImGuiWindowFlags_NoScrollWithMouse') or 0);
    local opened=false;
    if windowFlags~=0 then
        local ok,value=pcall(imgui.BeginChild,'##gambit-help-marquee',{lineW,lineH},childFlags,windowFlags);
        opened=ok and value;
        if not ok then opened=imgui.BeginChild('##gambit-help-marquee',{lineW,lineH},childFlags); end
    else
        opened=imgui.BeginChild('##gambit-help-marquee',{lineW,lineH},childFlags);
    end
    if opened then
        if imgui.SetCursorPosY and imgui.GetCursorPosY then
            imgui.SetCursorPosY(imgui.GetCursorPosY()+textInsetY);
        end
        local available=imgui.GetContentRegionAvail and imgui.GetContentRegionAvail() or nil;
        local availableW=type(available)=='table' and E.number(available[1] or available.x,0) or E.number(available,0);
        imgui.Text(E.fit_help_text(text,availableW));
    end
    imgui.EndChild();
end
function E.ui_top_job_label(text)
    text=tostring(text or '');
    if imgui.CalcTextSize and imgui.GetWindowWidth and imgui.GetCursorPosX and imgui.SetCursorPosX then
        local textSize=imgui.CalcTextSize(text);
        local textW=type(textSize)=='table' and E.number(textSize[1] or textSize.x,0) or 0;
        local winW=E.number(imgui.GetWindowWidth(),E.s(848));
        local currentX=E.number(imgui.GetCursorPosX(),0);
        local centeredX=math.floor((winW-textW)*0.5);
        if textW>0 and centeredX>currentX then imgui.SetCursorPosX(centeredX); end
        imgui.Text(text);
        return;
    end
    E.ui_centered_text(text);
end
function E.inventory_color(progress)
    if progress>=0.98 then return 0xAAD24646; end
    if progress>=0.90 then return 0xAAE68620; end
    if progress>=0.75 then return 0xAAD8BE27; end
    if progress>=0.50 then return 0xAA36C75A; end
    return 0xAA3B7FC4;
end
function E.inventory_display(buttonWidth)
    local memory=E.call(AshitaCore,'GetMemoryManager');
    local occupied,capacity=E.inventory_usage(E.call(memory,'GetInventory'));
    local sorting=S.sortPending~=nil;
    local label=sorting and 'Sorting...' or (occupied and
        string.format('%d / %d Inventory',occupied,capacity) or '-- / -- Inventory');
    local disabled=sorting or occupied==nil;
    if disabled and imgui.BeginDisabled and imgui.EndDisabled then imgui.BeginDisabled(true); end
    local clicked=imgui.Button(label..'###managed-inventory',{buttonWidth or E.s(202),E.ui_button_h()});
    if disabled and imgui.BeginDisabled and imgui.EndDisabled then imgui.EndDisabled(); end
    local draw=imgui.GetWindowDrawList and imgui.GetWindowDrawList();
    if occupied and capacity>0 and draw and draw.AddRectFilled and imgui.GetItemRectMin and imgui.GetItemRectMax then
        pcall(function()
            local x,y=imgui.GetItemRectMin();
            local right,bottom=imgui.GetItemRectMax();
            if not x or not y or not right or not bottom or right<=x or bottom<=y then return; end
            local progress=occupied/capacity;
            if progress>0 then
                draw:AddRectFilled({x+1,y+1},{x+1+(right-x-2)*progress,bottom-1},E.inventory_color(progress));
            end
            if draw.AddText and imgui.CalcTextSize then
                local tw,th=imgui.CalcTextSize(label);
                tw,th=tw or 0,th or 0;
                draw:AddText({x+(right-x-tw)/2,y+(bottom-y-th)/2},0xFFF2E6D0,label);
            end
        end);
    end
    E.hover_help('SORT INVENTORY');
    if clicked and not disabled then
        local ok,reason=E.queue_sort();
        if not ok then E.set_message(tostring(reason),5); end
    end
end
function E.ui_available(defaultHeight)
    if imgui.GetContentRegionAvail then
        local avail,height=imgui.GetContentRegionAvail();
        if type(avail)=='table' then
            return E.number(avail[1] or avail.x,0),E.number(avail[2] or avail.y,defaultHeight or 420);
        elseif type(avail)=='number' then
            return E.number(avail,0),E.number(height,defaultHeight or 420);
        end
    end
    return 0,defaultHeight or 420;
end
function E.tab_label(tab)
    return tab=='Rules' and 'Gambits' or tab;
end
function E.normalize_tab()
    if S.ui.tab=='Rules' then S.ui.tab='Gambits'; end
    if S.ui.tab=='Catalog' then S.ui.tab='Presets'; end
    if S.ui.roleTab~='main' then E.select_main_sheet(); end
end
function E.profile_rules()
    local profile=E.active_profile();
    return profile and profile.Rules or {};
end
function E.update_rule(index,fn)
    local rules=G.GetRules(); local rule=rules[index];
    if not rule then return false,'No selected Gambit row'; end
    fn(rule,rules);
    local profile=E.active_profile();
    local previousTemplate=profile and profile.LastNewRuleTemplate;
    if rule.Type~='none' then E.remember_new_rule_template(rule); end
    local ok,err=G.SetRules(rules);
    if not ok and profile then profile.LastNewRuleTemplate=previousTemplate; end
    return ok,err;
end
function E.reset_condition(rule)
    for _,key in ipairs({'SelfHPBelow','SelfHPAbove','SelfMPBelow','SelfMPAbove','SelfTPBelow','SelfTPAbove',
        'TargetHPBelow','TargetHPAbove','TargetMPBelow','TargetMPAbove','MinMissingHP','TP',
        'Pet','PetHPBelow','PetTPAbove','Mechanic','Combat','Range','ManaTarget',
        'TwoHanded','RequireProvider','CheckTarget','CheckTargetName','SubjectLabel','MissingBuffExpireThreshold'}) do
        rule[key]=nil;
    end
end
function E.reset_status(rule)
    for _,key in ipairs({'MissingBuff','MissingBuffExpireThreshold','MissingBuffBinding','Status','RequiresBuff','ForbidBuff'}) do rule[key]=nil; end
end
function E.reset_property(rule)
    for _,key in ipairs({'Property','Operator','Value','TextValue','ValueText'}) do rule[key]=nil; end
end
function E.set_property(rule,property,operator,value,textValue)
    E.reset_condition(rule);
    E.reset_status(rule);
    E.reset_property(rule);
    if not property or property=='always' then rule.Combat='any'; return; end
    rule.Property=property;
    rule.Operator=operator or 'yes';
    rule.Value=value;
    rule.TextValue=textValue;
    if property=='casting' or property=='casting_magic' or property=='specific_spell' or property=='readying_tp_move'
        or property=='specific_tp_move' or property=='skillchain' or property=='skillchain_property'
        or property=='skillchain_level' or property=='can_open_skillchain' or property=='can_close_skillchain'
        or property=='magic_burst_window' or property=='magic_burst_element' or property=='enemy_dispellable'
        or property=='weakest_element' or property=='resists_element' or property=='immune_element'
        or property=='absorbs_element' or property=='sp_ability' or property=='behind' or property=='in_front'
        or property=='nm_state' or property=='family' then rule.Combat='combat'; end
end
function E.set_operator(rule,operator,value,textValue)
    rule.Operator=operator or rule.Operator or 'yes';
    if value~=nil then rule.Value=value; end
    if textValue~=nil then rule.TextValue=textValue; end
end
function E.action_status_name(name)
    if not name or name=='' then return nil; end
    local effect=E.smart_spell_effect(name) or E.status_alias_name(name);
    if effect then return effect; end
    for _,alias in ipairs(E.status_aliases(name)) do
        if type(alias)=='number' then return name; end
    end
    return nil;
end
local INDI_STATUS_ALIASES = {
    ['Indi-Regen']='Colure Active',
    ['Indi-Poison']='Colure Active',
    ['Indi-Refresh']='Colure Active',
    ['Indi-Haste']='Colure Active',
    ['Indi-STR']='Colure Active',
    ['Indi-DEX']='Colure Active',
    ['Indi-VIT']='Colure Active',
    ['Indi-AGI']='Colure Active',
    ['Indi-INT']='Colure Active',
    ['Indi-MND']='Colure Active',
    ['Indi-CHR']='Colure Active',
    ['Indi-Fury']='Colure Active',
    ['Indi-Barrier']='Colure Active',
    ['Indi-Acumen']='Colure Active',
    ['Indi-Fend']='Colure Active',
    ['Indi-Precision']='Colure Active',
    ['Indi-Voidance']='Colure Active',
    ['Indi-Focus']='Colure Active',
    ['Indi-Attunement']='Colure Active',
    ['Indi-Wilt']='Colure Active',
    ['Indi-Frailty']='Colure Active',
    ['Indi-Fade']='Colure Active',
    ['Indi-Malaise']='Colure Active',
    ['Indi-Slip']='Colure Active',
    ['Indi-Torpor']='Colure Active',
    ['Indi-Vex']='Colure Active',
    ['Indi-Languor']='Colure Active',
    ['Indi-Slow']='Colure Active',
    ['Indi-Paralysis']='Colure Active',
    ['Indi-Gravity']='Colure Active',
};
function E.is_indi_spell_name(name)
    return type(name)=='string' and INDI_STATUS_ALIASES[name]~=nil;
end
function E.status_alias_name(name)
    if not name or name=='' or type(name)=='number' then return name; end
    if INDI_STATUS_ALIASES[name]~=nil then return INDI_STATUS_ALIASES[name]; end
    local map={
        ['Haste II']='Haste',
        ['Hastega']='Haste',['Hastega II']='Haste',
        ['Protect V']='Protect',['Protect IV']='Protect',['Protect III']='Protect',['Protect II']='Protect',
        ['Protectra V']='Protect',['Protectra IV']='Protect',['Protectra III']='Protect',['Protectra II']='Protect',['Protectra']='Protect',
        ['Shell V']='Shell',['Shell IV']='Shell',['Shell III']='Shell',['Shell II']='Shell',
        ['Shellra V']='Shell',['Shellra IV']='Shell',['Shellra III']='Shell',['Shellra II']='Shell',['Shellra']='Shell',
        ['Regen V']='Regen',['Regen IV']='Regen',['Regen III']='Regen',['Regen II']='Regen',
        ['Refresh III']='Refresh',['Refresh II']='Refresh',
        Gravity='Weight', Utsusemi='Copy Image*',
        ['Phalanx II']='Phalanx',
        ['Barfira']='Barfire',['Barstonra']='Barstone',['Barwatera']='Barwater',
        ['Baraera']='Baraero',['Barblizzara']='Barblizzard',['Barthundra']='Barthunder',
        ['Barpoisonra']='Barpoison',['Barparalyzra']='Barparalyze',['Barblindra']='Barblind',
        ['Barsilencera']='Barsilence',['Barpetra']='Barpetrify',['Barsleepra']='Barsleep',
        ['Barvira']='Barvirus',['Baramnesra']='Baramnesia',
    };
    return map[name] or (SONG_BUFFS and SONG_BUFFS[name]);
end
-- Only spells with a persistent, identifiable status receive an implicit
-- missing-effect check. Direct damage, cures, dispels and other utility spells
-- keep their normal conditions. This map is also used by plain Any rules.
local ENSPELL_EFFECTS={'Enfire','Enblizzard','Enaero','Enstone','Enthunder','Enwater'};
local SMART_SPELL_EFFECTS={
        Haste='Haste', Refresh='Refresh', Regen='Regen', Protect='Protect', Shell='Shell',
        Phalanx='Phalanx', Stoneskin='Stoneskin', Aquaveil='Aquaveil', Blink='Blink',
        Sneak='Sneak', Invisible='Invisible', Deodorize='Deodorize', Reraise='Reraise',
        Cocoon='Defense Boost', ['Metallic Body']='Stoneskin', Refueling='Haste',
        ['Tonko: Ichi']='Invisible', ['Tonko: Ni']='Invisible', ['Monomi: Ichi']='Sneak',
        Slow='Slow', Paralyze='Paralyze', Blind='Blind', Poison='Poison',
        Dia='Dia', Bio='Bio', Gravity='Weight', Bind='Bind', Silence='Silence',
        Addle='Addle', Sleep='Sleep', Stun='Stun', Flash='Flash',
        Burn='Burn', Frost='Frost', Choke='Choke', Rasp='Rasp', Shock='Shock', Drown='Drown',
        ['Utsusemi: Ichi']='Copy Image*', ['Utsusemi: Ni']='Copy Image*',
        Enfire=ENSPELL_EFFECTS, Enblizzard=ENSPELL_EFFECTS, Enaero=ENSPELL_EFFECTS,
        Enstone=ENSPELL_EFFECTS, Enthunder=ENSPELL_EFFECTS, Enwater=ENSPELL_EFFECTS,
        ['Carnage Elegy']='Elegy', ['Battlefield Elegy']='Elegy',
        ['Foe Requiem']='Requiem', ['Foe Lullaby']='Lullaby', ['Horde Lullaby']='Lullaby',
        ['Kurayami: Ichi']='Blind', ['Kurayami: Ni']='Blind',
        ['Hojo: Ichi']='Slow', ['Hojo: Ni']='Slow', ['Jubaku: Ichi']='Paralyze',
        ['Dokumori: Ichi']='Poison',
};
function E.smart_spell_effect(name)
    if type(name)~='string' then return nil; end
    if SMART_SPELL_EFFECTS[name] then return SMART_SPELL_EFFECTS[name]; end
    if SONG_BUFFS and SONG_BUFFS[name] then return SONG_BUFFS[name]; end
    if name:match('^Foe Requiem [IVX]+$') then return 'Requiem'; end
    if name:match('^Foe Lullaby [IVX]+$') then return 'Lullaby'; end
    if name=='Haste II' or name=='Hastega' or name=='Hastega II' then return 'Haste'; end
    for _,family in ipairs({'Protect','Shell','Regen','Refresh','Dia','Bio','Poison','Slow','Paralyze','Blind','Sleep','Reraise'}) do
        if name:match('^'..family..' [IVX]+$') then return family; end
    end
    for _,family in ipairs({'Protectra','Shellra','Diaga'}) do
        if name==family or name:match('^'..family..' [IVX]+$') then
            return ({Protectra='Protect',Shellra='Shell',Diaga='Dia'})[family];
        end
    end
    if name=='Phalanx II' then return 'Phalanx'; end
    local bar=E.status_alias_name(name);
    if bar and name:match('^Bar') then return bar; end
    if ({Barfire=true,Barblizzard=true,Baraero=true,Barstone=true,Barthunder=true,Barwater=true,
        Barpoison=true,Barparalyze=true,Barblind=true,Barsilence=true,Barpetrify=true,
        Barsleep=true,Barvirus=true,Baramnesia=true})[name] then return name; end
    return nil;
end
local STATUS_ID_ALIASES={
    -- IDs already used by the authored status-removal rules in this file.
    ['Poison']={3}, ['Paralyze']={4}, ['Paralysis']={4}, ['Blind']={5}, ['Blindness']={5},
    ['Silence']={6}, ['Petrification']={7}, ['Disease']={8}, ['Curse']={9,20}, ['Doom']={15}, ['Plague']={31},
    ['Amnesia']={16}, ['Terror']={28}, ['Charm']={14,17},
    ['Haste']={33}, ['Protect']={40}, ['Shell']={41}, ['Regen']={42}, ['Refresh']={43}, ['Food']={251},
    ['Blink']={36}, ['Stoneskin']={37}, ['Aquaveil']={39}, ['Phalanx']={116},
    ['Sneak']={71}, ['Invisible']={69}, ['Reraise']={113}, ['Defense Boost']={93},
    ['Slow']={13}, ['Dia']={134}, ['Bio']={135}, ['Bind']={11}, ['Weight']={12},
    ['Addle']={21}, ['Sleep']={2,19},
    ['Stun']={10}, ['Flash']={156}, ['Burn']={128}, ['Frost']={129},
    ['Choke']={130}, ['Rasp']={131}, ['Shock']={132}, ['Drown']={133},
    ['Enfire']={94}, ['Enblizzard']={95}, ['Enaero']={96}, ['Enstone']={97},
    ['Enthunder']={98}, ['Enwater']={99}, ['Elegy']={194}, ['Requiem']={192},
    ['Lullaby']={193},
    ['Deodorize']={70}, ['Barpoison']={107}, ['Barparalyze']={108},
    ['Barblind']={109}, ['Barsilence']={110}, ['Barpetrify']={111},
    ['Barsleep']={106}, ['Barvirus']={112}, ['Baramnesia']={286},
    ['Berserk']={56}, ['Defender']={57}, ['Aggressor']={58}, ['Warcry']={68}, ['Retaliation']={405},
    ['Boost']={45}, ['Focus']={59}, ['Dodge']={60}, ['Counterstance']={61},
    ['Hasso']={353}, ['Seigan']={354}, ['Third Eye']={67},
    ['Sentinel']={62}, ['Rampart']={623}, ['Cover']={114}, ['Souleater']={63},
    ['Last Resort']={64}, ['Meditate']={801}, ['Sekkanoki']={408},
    ['Yonin']={420}, ['Innin']={421}, ['Afflatus Solace']={417}, ['Afflatus Misery']={418},
    ['Composure']={419}, ['Sublimation']={187,188}, ['Overload']={299},
    ['Sneak Attack']={65}, ['Trick Attack']={87}, ['Flee']={32}, ['Elemental Seal']={79},
    ['Barfire']={100}, ['Barblizzard']={101}, ['Baraero']={102}, ['Barstone']={103}, ['Barthunder']={104}, ['Barwater']={105},
    ['Ballad']={196}, ['Minuet']={198}, ['Madrigal']={200}, ['Prelude']={201}, ['Mambo']={202}, ['Aubade']={203},
    ['Pastoral']={204}, ['Hum']={205}, ['Fantasia']={206}, ['Operetta']={207}, ['Capriccio']={208}, ['Serenade']={209},
    ['Round']={210}, ['Gavotte']={211}, ['Fugue']={212}, ['Rhapsody']={213}, ['March']={214}, ['Etude']={215},
    ['Carol']={216}, ['Threnody']={217}, ['Hymnus']={218}, ['Mazurka']={219}, ['Sirvente']={220}, ['Dirge']={221},
    ['Scherzo']={222}, ['Colure Active']={612},
};
function E.status_aliases(name)
    if type(name)=='table' then return name; end
    local aliases={name};
    local mapped=E.status_alias_name(name);
    if mapped~=nil and mapped~=name then aliases[#aliases+1]=mapped; end
    local seen={};
    local aliasCount=#aliases;
    for i=1,aliasCount do
        local alias=aliases[i];
        local ids=STATUS_ID_ALIASES[alias] or STATUS_ID_ALIASES[type(alias)=='string' and (alias:sub(1,1):upper()..alias:sub(2):lower()) or alias];
        if type(ids)=='table' then
            for _,id in ipairs(ids) do
                if not seen[id] then aliases[#aliases+1]=id; seen[id]=true; end
            end
        end
    end
    return aliases;
end
function E.self_centered_party_spell(name)
    if not name or name=='' then return false; end
    if SONG_BUFFS and SONG_BUFFS[name]~=nil then return true; end
    if E.is_indi_spell_name(name) then return true; end
    if name=='Hastega' or name=='Hastega II' then return true; end
    if tostring(name):match('^Protectra') or tostring(name):match('^Shellra') then return true; end
    return E.status_alias_name(name)~=nil and tostring(name):match('^Bar')~=nil and tostring(name):match('ra$')~=nil;
end
function E.action_cast_target(ctx,kind,name,res,conditionTarget)
    if kind=='spell' and ctx and ctx.self and conditionTarget~=ctx.self
        and res and res.Targets==1 and E.self_centered_party_spell(name) then
        return ctx.self,'Self-centered party spell';
    end
    return conditionTarget,nil;
end
function E.find_live_target(ctx,id)
    if not ctx or not id then return nil; end
    if ctx.self and ctx.self.id==id then return ctx.self; end
    if ctx.pet and ctx.pet.id==id then return ctx.pet; end
    if ctx.target and ctx.target.id==id then return ctx.target; end
    for _,m in ipairs(ctx.party or {}) do if m.id==id then return m; end end
    return nil;
end
function E.rule_action_missing_status(rule)
    if not rule then return nil; end
    local smart={
        ['Best Haste']='Haste',
        ['Best Protect']='Protect',
        ['Best Shell']='Shell',
        ['Best Regen']='Regen',
        ['Best Refresh']='Refresh',
        ['Maintain Selected Effect']=rule.MaintainEffect,
    };
    if rule.SmartActionLabel and smart[rule.SmartActionLabel] then return smart[rule.SmartActionLabel]; end
    if type(rule.Actions)=='table' and #rule.Actions>0 then return E.action_status_name(rule.Actions[1]); end
    return E.action_status_name(rule.Action);
end
function E.sync_missing_status_to_action(rule)
    if not rule then return; end
    for _,condition in ipairs({rule,rule.Condition2}) do
        if type(condition)=='table' and condition.MissingBuffBinding=='action' then
            condition.MissingBuff=E.rule_action_missing_status(rule);
        end
    end
end
function E.set_status(rule,kind,value,parentRule)
    E.reset_condition(rule);
    E.reset_property(rule);
    E.reset_status(rule);
    if kind=='always' then return;
    elseif kind=='target-missing' then rule.MissingBuff=(value=='__ACTION__') and E.rule_action_missing_status(parentRule or rule) or (value or 'Haste'); rule.MissingBuffBinding=(value=='__ACTION__') and 'action' or nil; rule.Combat='any';
    elseif kind=='target-missing-expiring' then rule.MissingBuff=value or 'Haste'; rule.MissingBuffExpireThreshold=30; rule.Combat='any';
    elseif kind=='target-has' then rule.Status=value or 'Poison';
    elseif kind=='self-has' then rule.RequiresBuff=value or 'Haste';
    elseif kind=='self-missing' then rule.ForbidBuff=value or 'Haste';
    elseif kind=='party-has' then rule.CheckTarget='status'; rule.SubjectLabel='Party'; rule.Status=value or 'Poison';
    elseif kind=='target-debuff' then rule.Status=value or {'Poison','Paralyze','Blind','Silence','Slow','Elegy','Bind','Weight','Sleep','Doom'};
    elseif kind=='target-no-buff' then rule.MissingBuff=value or {'Haste','Protect','Shell','Refresh','Regen','Sneak','Invisible'};
    end
end
function E.set_condition(rule,kind,value)
    E.reset_condition(rule);
    E.reset_status(rule);
    E.reset_property(rule);
    if kind=='always' then rule.Combat='any';
    elseif kind=='combat' then rule.Combat='combat';
    elseif kind=='idle' then rule.Combat='idle';
    elseif kind=='self-hp-lt' then rule.SelfHPBelow=value or 50;
    elseif kind=='self-hp-gt' then rule.SelfHPAbove=value or 80;
    elseif kind=='self-mp-lt' then rule.SelfMPBelow=value or 30;
    elseif kind=='self-mp-gt' then rule.SelfMPAbove=value or 30;
    elseif kind=='self-tp-ge' then rule.SelfTPAbove=value or 1000;
    elseif kind=='self-tp-lt' then rule.SelfTPBelow=value or 1000;
    elseif kind=='target-hp-lt' then rule.TargetHPBelow=value or 50;
    elseif kind=='target-hp-gt' then rule.TargetHPAbove=value or 80;
    elseif kind=='target-mp-lt' then rule.TargetMPBelow=value or 30;
    elseif kind=='target-mp-gt' then rule.TargetMPAbove=value or 80;
    elseif kind=='missing-hp' then rule.MinMissingHP=value or 100;
    elseif kind=='tp-ge' then rule.TP=value or 1000;
    elseif kind=='dead' then rule.Property='dead'; rule.Operator='yes'; rule.Combat='any';
    elseif kind=='pet-present' then rule.Pet='present';
    elseif kind=='pet-missing' then rule.Pet='missing';
    elseif kind=='pet-idle' then rule.Pet='idle';
    elseif kind=='pet-hp-lt' then rule.Pet='present'; rule.PetHPBelow=value or 40;
    elseif kind=='pet-tp-ge' then rule.Pet='present'; rule.PetTPAbove=value or 1000;
    elseif kind=='interrupt' then rule.Mechanic='interrupt'; rule.Combat='combat';
    elseif kind=='maneuver' then rule.Mechanic='maneuver'; rule.Combat='combat';
    elseif kind=='distance' then rule.Property='distance'; rule.Operator='<='; rule.Value=value or 15;
    elseif kind=='mana-target' then rule.ManaTarget=true;
    elseif kind=='two-handed' then rule.TwoHanded=true;
    end
end
function E.condition_slot_after_edit(rule,slot)
    if slot==2 and not E.condition_clause_active(rule.Condition2) then rule.Condition2=nil; end
end
function E.edit_condition_slot(index,slot,fn)
    return E.update_rule(index,function(r)
        local condition=E.condition_slot(r,slot,true);
        fn(condition,r);
        E.condition_slot_after_edit(r,slot);
    end);
end
function E.popup_open(name)
    if imgui.OpenPopup then imgui.OpenPopup(name); return true; end
    S.ui.popup=name; return true;
end
function E.popup_window_pair(first,second)
    if type(first)=='table' then
        return E.number(first[1] or first.x),E.number(first[2] or first.y);
    end
    return E.number(first),E.number(second);
end
function E.popup_begin(name)
    if imgui.BeginPopup then
        -- All pickers use the main Gambits window as their anchor. Ashita's
        -- GetWindowPos/GetWindowSize return two numbers, not a table.
        if imgui.IsPopupOpen and imgui.IsPopupOpen(name) and imgui.SetNextWindowPos then
            local bounds=S.ui.editorBounds;
            local x,y,width,height;
            if bounds then
                x,y,width,height=bounds.x,bounds.y,bounds.width,bounds.height;
            elseif imgui.GetWindowPos and imgui.GetWindowSize then
                x,y=E.popup_window_pair(imgui.GetWindowPos());
                width,height=E.popup_window_pair(imgui.GetWindowSize());
            end
            if x and y and width and height and width>0 and height>0 then
                -- The tall Condition picker can be remeasured after its first
                -- frame. Keep it anchored while open so it cannot jump to
                -- ImGui's fallback popup position on subsequent frames.
                local condition=name:sub(1,17)=='condition-picker-'
                    and (rawget(_G,'ImGuiCond_Always') or 1)
                    or (rawget(_G,'ImGuiCond_Appearing') or 8);
                imgui.SetNextWindowPos({x+width/2,y+height/2},condition,{0.5,0.5});
            end
        end
        return imgui.BeginPopup(name);
    end
    return S.ui.popup==name;
end
function E.popup_end()
    if imgui.EndPopup then imgui.EndPopup(); end
end
function E.popup_close()
    if imgui.CloseCurrentPopup then imgui.CloseCurrentPopup(); end
    S.ui.popup=nil;
end

function E.picker_child_begin(name,w,h)
    local flags=rawget(_G,'ImGuiChildFlags_Borders') or 0;
    return imgui.BeginChild(name,{E.s(w or 420),E.s(h or 320)},flags);
end
function E.picker_child_end()
    imgui.EndChild();
end
function E.picker_search_text(key,index,label,helpText)
    local filter=E.buffer(tostring(key)..'-picker-filter-'..tostring(index),'');
    E.help_search_input_text((label or 'Search')..'##'..tostring(key)..'-picker-filter-input-'..tostring(index),filter,96,helpText or 'Type to filter this picker.');
    return E.lower(filter[1] or '');
end
function E.picker_matches(needle,...)
    if not needle or needle=='' then return true; end
    for i=1,select('#',...) do
        local value=select(i,...);
        if value~=nil and E.lower(tostring(value)):find(needle,1,true) then return true; end
    end
    return false;
end
function E.segment_button(text,id,w,selected,helpText)
    local label=tostring(text or '')..'##'..id;
    return E.help_button(label,{w,E.ui_button_h()},helpText);
end
function E.target_picker(index,rule)
    local name='target-picker-'..tostring(index);
    if E.popup_begin(name) then
        local needle=E.picker_search_text('target',index,'Search','Search targets by name, such as tank, lowest, pet, leader, or current target.');
        if E.picker_child_begin('##target-picker-scroll-'..index,360,260) then
            E.picker_section_header('Target Options',true);
            local targets={{'self','Self'},{'enemy','Enemy'},{'party_member','Party Member'},
                {'alliance_member','Ally Member'},{'party_pool_tank','Any Tank (Party)'},
                {'party_pool_support','Any Support (Party)'},{'party_pool_dps','Any DPS (Party)'}};
            for _,opt in ipairs(targets) do
                if E.target_supported(opt[1]) and E.picker_matches(needle,opt[1],opt[2]) and E.help_selectable(opt[2]..'##target-'..opt[2]..index,false,'Target: '..tostring(opt[2])..'.') then
                    E.notify_save(E.update_rule(index,function(r) r.Target=opt[1]; end));
                    E.popup_close();
                end
            end
        end
        E.picker_child_end();
        E.popup_end();
    end
end
function E.condition_value_controls(index,rule,slot)
    slot=slot or 1;
    local pickerKey=tostring(index)..'-'..tostring(slot);
    if rule.Property and rule.Property~='always' then
        local numeric=E.property_kind(rule.Property)=='number';
        local initial=numeric and rule.Value or (rule.TextValue or rule.Value or '');
        local buffer=E.buffer('property-value-'..pickerKey,initial);
        E.help_input_text('Value##property-value-input-'..pickerKey,buffer,64,'Condition threshold or named value.');
        if E.help_button('Set##property-value-set-'..pickerKey,nil,'Save condition value.') then
            local number=E.number(buffer[1]);
            if numeric and number==nil then E.set_message('A finite numeric threshold is required.',4);
            else
                E.notify_save(E.edit_condition_slot(index,slot,function(c)
                    if numeric then c.Value=number; else c.TextValue=buffer[1]; end
                end));
                E.popup_close();
            end
        end
        if numeric and E.contains({'status_remaining','status_count','song_remaining','item_count'},rule.Property) then
            local text=E.buffer('property-name-'..pickerKey,rule.TextValue or rule.ValueText or '');
            E.help_input_text('Name##property-name-input-'..pickerKey,text,64,'Named status, song or item.');
            if E.help_button('Set Name##property-name-set-'..pickerKey,nil,'Save name without changing the threshold.') then
                E.notify_save(E.edit_condition_slot(index,slot,function(c) c.TextValue=text[1]; end)); E.popup_close();
            end
        end
    end
    local numeric={{'SelfHPBelow','Self HP <','%'},{'SelfHPAbove','Self HP >','%'},{'SelfMPBelow','Self MP <','%'},
        {'SelfMPAbove','Self MP >','%'},{'SelfTPAbove','Self TP >=',''},{'SelfTPBelow','Self TP <',''},
        {'TargetHPBelow','Target HP <','%'},{'TargetHPAbove','Target HP >','%'},{'TargetMPBelow','Target MP <','%'},
        {'TargetMPAbove','Target MP >','%'},{'TP','TP >=',''},{'MinMissingHP','Missing HP >=',''},
        {'PetHPBelow','Pet HP <','%'},{'PetTPAbove','Pet TP >=',''},{'Range','Distance <=',''},
        {'MissingBuffExpireThreshold','Buff expires <=','s'}};
    for _,entry in ipairs(numeric) do
        local key,label,suffix=entry[1],entry[2],entry[3];
        if rule[key]~=nil then
            local b=E.buffer('cond-value-'..pickerKey..'-'..key,rule[key]);
            E.help_input_text(label,b,16,'Numeric threshold.'); imgui.SameLine();
            if E.help_button('Set'..suffix..'##cond-set-'..pickerKey..key,nil,'Save threshold.') then
                local n=E.number(b[1]);
                if n then E.notify_save(E.edit_condition_slot(index,slot,function(c) c[key]=n; end)); E.popup_close(); end
            end
        end
    end
end
function E.status_value_controls(index,rule,slot)
    slot=slot or 1;
    local pickerKey=tostring(index)..'-'..tostring(slot);
    for _,entry in ipairs({{'MissingBuff','Target Missing Status/Buff'},{'Status','Target Has Status'},{'RequiresBuff','Self Has Status/Buff'},{'ForbidBuff','Self Missing Status/Buff'}}) do
        local key,label=entry[1],entry[2];
        if rule[key]~=nil then
            local b=E.buffer('status-value-'..pickerKey..'-'..key,E.join(rule[key]));
            E.help_input_text(label,b,64,'Status names, comma separated.'); imgui.SameLine();
            if E.help_button('Set##status-set-'..pickerKey..key,nil,'Save statuses.') then
                local values={};
                for value in b[1]:gmatch('[^,]+') do
                    value=value:match('^%s*(.-)%s*$');
                    if value~='' then values[#values+1]=tonumber(value) or value; end
                end
                E.notify_save(E.edit_condition_slot(index,slot,function(c) c[key]=#values==1 and values[1] or values; if key=='MissingBuff' then c.MissingBuffBinding=nil; end end)); E.popup_close();
            end
        end
    end
end
local QUICK_STATUSES={'Poison','Paralyze','Blind','Silence','Slow','Elegy','Bind','Weight','Sleep','Petrification','Stun','Doom','Curse','Disease','Plague','Burn','Frost','Choke','Rasp','Shock','Drown','Dia','Bio','Gravity','Addle','Amnesia','Terror','Charm','Haste','Protect','Shell','Refresh','Regen','Sneak','Invisible','Blink','Utsusemi','Phalanx','Stoneskin','Aquaveil','Reraise','Berserk','Defender','Aggressor','Focus','Dodge','Warcry','Boost','Counterstance','Sentinel','Rampart','Cover','Souleater','Last Resort','Meditate','Sekkanoki','Hasso','Seigan','Third Eye','Yonin','Innin','Afflatus Solace','Afflatus Misery','Composure','Sublimation','Overload'};
function E.status_picker(index,rule)
    local name='status-picker-'..tostring(index);
    if E.popup_begin(name) then
        local conditionCtx=E.editor_catalog_context();
        if E.picker_child_begin('##status-picker-scroll-'..index,420,340) then
            local properties={
                {'always','Always','any',nil},{'hp_pct','HP %','<',40},{'hp_amount','HP Amount','<',500},
                {'mp_pct','MP %','<',30},{'mp_amount','MP Amount','<',100},{'tp','TP','>=',1000},
                {'alive','Alive','yes',nil},{'dead','Dead','yes',nil},{'engaged','Engaged','yes',nil},
                {'idle','Idle','yes',nil},{'in_battle','In Battle','yes',nil},{'casting','Casting','yes',nil},
                {'casting_magic','Casting Magic','yes',nil},{'specific_spell','Casting Specific Spell','yes',nil,'Fire'},
                {'readying_tp_move','Readying TP Move','yes',nil},{'specific_tp_move','Readying Specific TP Move','yes',nil,'Goblin Rush'},
                {'has_hate','Has Hate','yes',nil},{'top_enmity','Top Enmity','yes',nil},{'targeting_actor','Foe Targeting This Actor','yes',nil},
                {'distance','Distance','<=',10},{'melee_range','In Melee Range','yes',nil},{'ranged_range','In Ranged Range','yes',nil},
                {'preferred_ranged_distance','Preferred Ranged Distance','>=',15},{'outside_melee_range','Outside Melee Range','yes',nil},
                {'has_mp','Has MP','yes',nil},{'status_remaining','Buff Remaining','<',30},{'status_count','Status Count','>=',1},
                {'party_count','Party Count','>=',2},{'matching_allies','Matching Allies','>=',2},{'matching_alliance','Matching Alliance Members','>=',2},
                {'role_present','Role Present','yes',nil,'healer'},{'job_present','Job Present','yes',nil,'WHM'},
                {'healer_present','Healer Present','yes',nil},{'tank_present','Tank Present','yes',nil},
                {'job','Job','=',nil,'WHM'},{'role','Role','=',nil,'healer'},{'level','Level','>=',1},
                {'item_count','Item Count','>=',1,'Echo Drops'},
                {'ammo_remaining','Ammo Remaining','>=',1},{'pet_present','Pet Present','yes',nil},
                {'pet_missing','Pet Missing','yes',nil},{'pet_idle','Pet Idle','yes',nil},{'pet_engaged','Pet Engaged','yes',nil},
                {'pet_hp_pct','Pet HP %','<',40},{'pet_mp_pct','Pet MP %','<',40},{'pet_tp','Pet TP','>=',1000},
                {'shadows','Shadows','<',2},
                {'skillchain','Skillchain Window Active','yes',nil},{'skillchain_property','Skillchain Property','=',nil,'Light'},
                {'skillchain_level','Skillchain Level','>=',2},{'can_open_skillchain','Can Open Skillchain','yes',nil},
                {'can_close_skillchain','Can Close Skillchain','yes',nil},{'magic_burst_window','Magic Burst Window','yes',nil},
                {'magic_burst_element','Magic Burst Element','=',nil,'Fire'},
                {'enemy_dispellable','Enemy Has Dispellable Buff','yes',nil},
                {'weakest_element','Weakest Element','=',nil,'Fire'},{'resists_element','Resists Element','yes',nil,'Fire'},
                {'immune_element','Immune Element','yes',nil,'Fire'},{'absorbs_element','Absorbs Element','yes',nil,'Fire'},
                {'active_song','Active Song','yes',nil,'March'},{'song_count','Song Count','>=',1},{'song_remaining','Song Remaining','<',30},
                {'active_roll','Active Roll','yes',nil,'Chaos Roll'},{'roll_value','Roll Value','>=',1},
                {'lucky_number','Lucky Number','yes',nil},{'bust','Bust','yes',nil},{'roll_count','Roll Count','>=',1},
            };
            E.picker_section_header('Property',true);
            for _,opt in ipairs(properties) do
                if E.property_supported(opt[1],conditionCtx) and E.help_selectable(opt[2]..'##property-'..opt[1]..index,false,'Condition: '..tostring(opt[2])..'.') then
                    E.notify_save(E.update_rule(index,function(r) E.set_property(r,opt[1],opt[3],opt[4],opt[5]); end));
                    E.popup_close();
                end
            end
            E.picker_section_header('Status / Buff');
            local opts={
                {'always','Always',nil},
                {'target-has','Target Has Status/Buff','Poison'},
                {'target-missing','Target Missing Status/Buff','__ACTION__'},
                {'self-has','Self Has Status/Buff','Haste'},
                {'self-missing','Self Missing Status/Buff','Haste'},
                {'party-has','Party/Alliance Member Has Status','Poison'},
                {'target-debuff','Target Has Any Common Debuff',nil},
                {'target-no-buff','Target Missing All Listed Buffs',nil},
            };
            for _,opt in ipairs(opts) do
                if E.help_selectable(opt[2]..'##status-'..opt[1]..index,false,'Status check: '..tostring(opt[2])..'.') then
                    E.notify_save(E.update_rule(index,function(r) E.set_status(r,opt[1],opt[3]); end));
                    E.popup_close();
                end
            end
            imgui.Separator();
            local statuses=QUICK_STATUSES;
            E.picker_section_header('Quick Status',true);
            for _,status in ipairs(statuses) do
                if E.help_selectable(status..'##status-quick-'..status..index,false,'Check target for '..tostring(status)..'.') then
                    E.notify_save(E.update_rule(index,function(r) E.set_status(r,'target-has',status); end));
                    E.popup_close();
                end
                if E.help_selectable('Missing '..status..'##status-quick-missing-'..status..index,false,'Check that the selected target lacks '..tostring(status)..'.') then
                    E.notify_save(E.update_rule(index,function(r) E.set_status(r,'target-missing',status); end));
                    E.popup_close();
                end
            end
            imgui.Separator();
            E.status_value_controls(index,rule);
        end
        E.picker_child_end();
        E.popup_end();
    end
end
function E.condition_threshold_option(index,label,kind,value,target,slot)
    slot=slot or 1;
    if not E.picker_matches(S.ui.conditionPickerNeedle,label,kind,target) then return false; end
    if E.help_selectable(label..'##cond-threshold-'..kind..'-'..tostring(value)..'-'..tostring(target or 'same')..'-'..index..'-'..slot,false,'Condition: '..tostring(label)..'.') then
        E.notify_save(E.edit_condition_slot(index,slot,function(c,r)
            E.set_condition(c,kind,value);
            if target then c.CheckTarget=target; c.SubjectLabel=target:find('alliance',1,true) and 'Alliance' or 'Party'; end
        end));
        E.popup_close();
        return true;
    end
    return false;
end
function E.condition_threshold_group(index,title,entries,slot)
    slot=slot or 1;
    E.picker_section_header(title);
    for _,entry in ipairs(entries) do
        local labelPrefix,kind,target=entry[1],entry[2],entry[3];
        for value=0,100,10 do
            if E.condition_threshold_option(index,labelPrefix..' '..tostring(value)..'%',kind,value,target,slot) then
                return true;
            end
        end
    end
    return false;
end
function E.condition_picker(index,rule,slot)
    slot=slot or 1;
    local pickerKey=tostring(index)..'-'..tostring(slot);
    local current=E.condition_slot(rule,slot,false) or {};
    local name='condition-picker-'..pickerKey;
    if E.popup_begin(name) then
        local conditionCtx=E.editor_catalog_context();
        local needle=E.picker_search_text('condition',pickerKey,'Search','Search conditions by name.');
        S.ui.conditionPickerNeedle=needle;
        if imgui.TextWrapped then imgui.TextWrapped('Search to find advanced conditions. Conditions needing an unavailable adapter remain hidden; /autobox capabilities shows adapters.'); end
        if E.picker_child_begin('##condition-picker-scroll-'..pickerKey,460,360) then
            local chooseProperty=function(label,property,op,value,textValue)
                if not E.property_supported(property,conditionCtx) then return false; end
                if not E.picker_matches(needle,label,property,op,value,textValue) then return false; end
                if E.help_selectable(label..'##condition-property-'..property..'-'..tostring(op)..'-'..tostring(value)..'-'..tostring(textValue)..'-'..pickerKey,false,'Condition: '..tostring(label)..'.') then
                    E.notify_save(E.edit_condition_slot(index,slot,function(c) E.set_property(c,property,op,value,textValue); end));
                    E.popup_close();
                    return true;
                end
                return false;
            end;
            local chooseStatus=function(label,kind,value)
                if not E.picker_matches(needle,label,kind,value) then return false; end
                if E.help_selectable(label..'##condition-status-'..kind..'-'..tostring(value)..'-'..pickerKey,false,'Status condition: '..tostring(label)..'.') then
                    E.notify_save(E.edit_condition_slot(index,slot,function(c,r) E.set_status(c,kind,value,r); end));
                    E.popup_close();
                    return true;
                end
                return false;
            end;
            local chooseLegacy=function(label,kind,value)
                if not E.picker_matches(needle,label,kind,value) then return false; end
                if E.help_selectable(label..'##condition-legacy-'..kind..'-'..tostring(value)..'-'..pickerKey,false,'Condition: '..tostring(label)..'.') then
                    E.notify_save(E.edit_condition_slot(index,slot,function(c) E.set_condition(c,kind,value); end));
                    E.popup_close();
                    return true;
                end
                return false;
            end;
            local chooseSubjectProperty=function(label,subjectLabel,checkTarget,property,op,value,textValue)
                if not E.property_supported(property,conditionCtx) then return false; end
                if not E.picker_matches(needle,label,subjectLabel,checkTarget,property,op,value,textValue) then return false; end
                if E.help_selectable(label..'##condition-subject-'..tostring(checkTarget)..'-'..property..'-'..tostring(op)..'-'..tostring(value)..'-'..tostring(textValue)..'-'..pickerKey,false,'Condition: '..tostring(label)..'.') then
                    E.notify_save(E.edit_condition_slot(index,slot,function(c)
                        E.set_property(c,property,op,value,textValue);
                        c.CheckTarget=checkTarget;
                        c.SubjectLabel=subjectLabel;
                    end));
                    E.popup_close();
                    return true;
                end
                return false;
            end;

            E.picker_section_header('General',true);
            chooseProperty('Always','always','any',nil);
            chooseProperty('In Battle','in_battle','yes',nil);
            chooseProperty('Engaged','engaged','yes',nil);
            chooseProperty('Idle','idle','yes',nil);
            chooseProperty('Alive','alive','yes',nil);
            chooseProperty('Dead','dead','yes',nil);

            E.picker_section_header('Selected Target HP / MP / TP');
            for _,entry in ipairs({
                {'Target HP %','hp_pct','<',40},{'Target MP %','mp_pct','<',30},
                {'Target TP','tp','>=',1000},{'Has MP','has_mp','yes',nil},{'No MP','has_mp','no',nil},
            }) do chooseProperty(entry[1],entry[2],entry[3],entry[4]); end
            chooseLegacy('Missing HP >= X','missing-hp',100);

            E.picker_section_header('Status / Buff');
            chooseStatus('Has Status: X','target-has','Poison');
            if E.rule_action_missing_status(rule) then
                chooseStatus('Missing Action Effect','target-missing','__ACTION__');
            end
            chooseStatus('Missing Food','target-missing','Food');
            chooseStatus('Has Any Debuff','target-debuff',nil);
            -- Keep every positive/inverse favorite searchable without dumping
            -- 132 nearly identical choices into the default condition menu.
            if needle~='' then
                E.picker_section_header('Matching Status Effects');
                for _,status in ipairs(QUICK_STATUSES) do
                    chooseStatus('Has '..status,'target-has',status);
                    chooseStatus('Missing '..status,'target-missing',status);
                end
            end
            chooseProperty('Has Dispellable Buff','enemy_dispellable','yes',nil);
            chooseProperty('Status Remaining <= X seconds','status_remaining','<=',30,'Haste');

            -- Keep the everyday menu short. Every advanced condition remains
            -- reachable by typing its name in Search; saved rows are untouched.
            if needle~='' then
            E.picker_section_header('Casting / Enemy Actions');
            chooseProperty('Casting Spell','casting','yes',nil);
            chooseProperty('Casting Specific Spell: X','specific_spell','yes',nil,'Fire');
            chooseProperty('Readying TP Move','readying_tp_move','yes',nil);
            chooseProperty('Readying Specific TP Move: X','specific_tp_move','yes',nil,'Goblin Rush');
            chooseProperty('Using SP Ability','sp_ability','yes',nil);

            E.picker_section_header('Range / Position');
            chooseProperty('Distance <= X','distance','<=',15);
            chooseProperty('Distance >= X','distance','>=',15);
            chooseProperty('In Melee Range','melee_range','yes',nil);
            chooseProperty('In Ranged Range','ranged_range','yes',nil);
            chooseProperty('Behind Target','behind','yes',nil);
            chooseProperty('In Front Of Target','in_front','yes',nil);

            E.picker_section_header('Enmity');
            chooseProperty('Has Hate','has_hate','yes',nil);
            chooseProperty('Top Enmity','top_enmity','yes',nil);
            chooseProperty('Targeting Self','targeting','=',nil,'self');
            chooseProperty('Targeting Player','targeting','=',nil,'player');
            chooseProperty('Targeting Tank','targeting','=',nil,'tank');
            chooseProperty('Targeting Healer','targeting','=',nil,'healer');

            E.picker_section_header('Skillchain / Magic Burst');
            chooseProperty('Skillchain Active','skillchain','yes',nil);
            for _,prop in ipairs({'Liquefaction','Induration','Detonation','Scission','Impaction','Reverberation','Transfixion','Compression','Fusion','Fragmentation','Distortion','Gravitation','Light','Darkness'}) do
                chooseProperty('Skillchain: '..prop,'skillchain_property','=',nil,prop);
            end
            chooseProperty('Magic Burst Available','magic_burst_window','yes',nil);
            for _,element in ipairs({'Fire','Ice','Wind','Earth','Lightning','Water','Light','Dark'}) do
                chooseProperty('Magic Burst: '..element,'magic_burst_element','=',nil,element);
            end

            E.picker_section_header('Monster / Element');
            chooseProperty('NM','nm_state','=',nil,'NM');
            chooseProperty('Boss','nm_state','=',nil,'Boss');
            for _,family in ipairs({'Beastman','Undead','Arcana','Dragon','Beast','Lizard','Vermin','Plantoid','Aquan','Amorph','Bird','Demon','Elemental'}) do
                chooseProperty('Family: '..family,'family','=',nil,family);
            end
            for _,element in ipairs({'Fire','Ice','Wind','Earth','Lightning','Water','Light','Dark'}) do
                chooseProperty('Weak To: '..element,'weakest_element','=',nil,element);
                chooseProperty('Resistant To: '..element,'resists_element','yes',nil,element);
                chooseProperty('Immune To: '..element,'immune_element','yes',nil,element);
                chooseProperty('Absorbs: '..element,'absorbs_element','yes',nil,element);
            end

            E.picker_section_header('Party / Role');
            chooseProperty('Party Members Matching >= X','matching_allies','>=',2);
            chooseProperty('Alliance Members Matching >= X','matching_alliance','>=',2);
            chooseProperty('Job = X','job','=',nil,'WHM');
            for _,role in ipairs({'Tank','Healer','Melee','Ranged','Caster','Support'}) do chooseProperty('Role = '..role,'role','=',nil,E.lower(role)); end
            chooseProperty('Level >= X','level','>=',1);
            chooseProperty('Level <= X','level','<=',75);

            E.picker_section_header('Inventory / Equipment');
            chooseProperty('Item Count >= X','item_count','>=',1,'Echo Drops');
            chooseProperty('Ammo Remaining >= X','ammo_remaining','>=',1);
            chooseProperty('Equipped Weapon Type = X','weapon_type','=',nil,'Sword');
            chooseLegacy('Equipped Weapon Is Two-Handed','two-handed',nil);

            E.picker_section_header('Pets');
            for _,entry in ipairs({
                {'Pet Present','pet_present','yes',nil},{'Pet Missing','pet_missing','yes',nil},{'Pet Idle','pet_idle','yes',nil},
                {'Pet Engaged','pet_engaged','yes',nil},{'Pet HP < X%','pet_hp_pct','<',40},{'Pet MP < X%','pet_mp_pct','<',40},{'Pet TP >= X','pet_tp','>=',1000},
            }) do chooseProperty(entry[1],entry[2],entry[3],entry[4]); end

            E.picker_section_header('Job-Specific');
            chooseProperty('Shadows < X','shadows','<',2);
            chooseProperty('Shadows = X','shadows','=',2);
            for _,element in ipairs({'Fire','Ice','Wind','Earth','Thunder','Water','Light','Dark'}) do chooseProperty('Maneuver: '..element,'maneuver_element','=',nil,element); end
            chooseProperty('Maneuver Count < X','maneuver_count','<',3);
            chooseStatus('Overload','target-has','Overload');
            chooseProperty('Finishing Moves >= X','finishing_moves','>=',1);
            chooseProperty('Stratagem Charges >= X','stratagem_charges','>=',1);
            chooseProperty('Light Arts Active','arts','=',nil,'Light Arts');
            chooseProperty('Dark Arts Active','arts','=',nil,'Dark Arts');
            chooseProperty('Addendum: White Active','addendum','=',nil,'White');
            chooseProperty('Addendum: Black Active','addendum','=',nil,'Black');
            chooseProperty('Sublimation Ready','sublimation_ready','yes',nil);
            chooseProperty('Rune Count < X','rune_count','<',3);
            chooseProperty('Rune Element = X','rune_element','=',nil,'Fire');
            chooseProperty('Song Missing: X','song_missing','yes',nil,'March');
            chooseProperty('Song Remaining < X seconds','song_remaining','<',30);
            chooseProperty('Roll Missing: X','roll_missing','yes',nil,'Chaos Roll');
            chooseProperty('Roll Value = X','roll_value','=',11);
            chooseProperty('Bust Present','bust','yes',nil);
            chooseProperty('Quick Draw Charges >= X','quick_draw_charges','>=',1);
            end

            do
                imgui.Separator();
                if current.Property and current.Property~='always' then
                    local ops={{'<','< X',40},{'<=','<= X',40},{'=','= X',40},{'!=','!= X',40},{'>=','>= X',1000},{'>','> X',40},
                        {'present','Present',nil},{'missing','Missing',nil},{'yes','Yes',nil},{'no','No',nil},{'has','Has',nil},
                        {'not','Does Not Have',nil},{'ready','Ready',nil},{'not-ready','Not Ready',nil},{'any','Any',nil}};
                    E.picker_section_header('Current Condition Operator',true);
                    for _,opt in ipairs(ops) do
                        if E.operator_supported(current.Property,opt[1]) and E.help_selectable(opt[2]..'##operator-'..opt[1]..pickerKey,false,'Operator: '..tostring(opt[2])..'.') then
                            E.notify_save(E.edit_condition_slot(index,slot,function(c) E.set_operator(c,opt[1]); end));
                            E.popup_close();
                        end
                    end
                    imgui.Separator();
                end
                E.condition_value_controls(index,current,slot);
                E.status_value_controls(index,current,slot);
            end
        end
        E.picker_child_end();
        S.ui.conditionPickerNeedle=nil;
        E.popup_end();
    end
end
function E.reset_action_metadata(rule)
    for _,key in ipairs({'SmartActionLabel','ActionPolicy','MaintainEffect','MaintainRefreshSeconds','SmartStatusRemoval','Ranged','Family','BlueMagic','Special','Consumable','RequiredItem','AmmoContains','MissingBuffByAction','CureEfficiency','CureGoalHP','Mechanic','ManaTarget','Range'}) do
        rule[key]=nil;
    end
end
function E.picker_id_part(value)
    return tostring(value or ''):gsub('[^%w_%-]+','_');
end
function E.action_entry_id(entry,index,ordinal)
    return table.concat({
        'action-entry',
        E.picker_id_part(entry and entry.Type),
        E.picker_id_part(entry and entry.Id),
        E.picker_id_part(entry and entry.Action),
        tostring(index or 0),
        tostring(ordinal or 0),
    },'-');
end
function E.apply_action_entry(index,entry)
    if type(entry)~='table' then return false; end
    local ok,err=E.update_rule(index,function(r)
        E.reset_action_metadata(r);
        r.Type=entry.Type;
        r.Action=entry.Action;
        r.Actions=nil;
        if entry.Type=='item' then r.Target='self'; r.Consumable=true; end
        r.SmartStatusRemoval=nil;
        r.BlueMagic=entry.BlueMagic or false;
        E.sync_missing_status_to_action(r);
    end);
    if not ok then E.notify_save(ok,err); return false,err; end
    S.ui.selected=index;
    S.ui.flashRow=index;
    S.ui.flashUntil=E.now()+0.65;
    S.ui.edits={};
    E.log('Action set: '..tostring(entry.Type)..' | '..tostring(entry.Action),true);
    E.popup_close();
    return true;
end
-- The server owns each generated Recruit's stance. Query it when the sheet is
-- selected; an acknowledgement changes the button only for the matching actor.
function E.recruit_stance_mode(actorId,actorName)
    local stance=actorId and S.recruitStances[E.number(actorId)];
    return stance and stance.name==actorName and stance.mode or nil;
end
function E.recruit_stance_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local at=text:find('TGRS|',1,true);
    if not at then return false; end
    local actor,nonce,mode=text:sub(at):match('^TGRS|(%d+)|(%d+)|([AP!])');
    local stance=actor and S.recruitStances[tonumber(actor)];
    if stance and tonumber(nonce)==stance.nonce then
        E.bridge_trace('server_stance_reply',stance.command,
            {origin='recruit_stance_response',actorId=tonumber(actor),actorIndex=stance.actorIndex,mode=1});
        stance.command=nil;
        stance.nonce=nil;
        stance.mode=(mode=='A' or mode=='P') and mode or nil;
    end
    return true; -- Hide even delayed or stale private bridge replies.
end
function E.recruit_stance_request(ctx,requested)
    local actorId=E.number(ctx and ctx.catalogActorId);
    if not ctx or not ctx.generatedRecruit or not actorId or actorId<=0 then return false; end
    local stance=S.recruitStances[actorId];
    if not stance or stance.name~=ctx.catalogActorName then
        stance={name=ctx.catalogActorName,mode=nil,nonce=nil,pollAt=-10};
        S.recruitStances[actorId]=stance;
    end
    local now=E.now();
    if not requested and now-stance.pollAt<8 then return true; end
    local nonce=math.random(1,999999);
    local mode=requested or 'query';
    local command='/say !gambit stance '..math.floor(actorId)..' '..mode..' '..nonce;
    local sent=E.send_bridge_command(command,not requested,
        {origin='recruit_stance_request',actorId=actorId,actorIndex=ctx.catalogActorIndex});
    if sent then
        stance.command=command; stance.actorIndex=ctx.catalogActorIndex;
        stance.nonce=nonce;
        stance.pollAt=now;
        -- The displayed mode changes only after the matching server reply.
    end
    return sent;
end

-- TGRC replies contain only active server timers. A complete snapshot makes
-- absent spell IDs and ability groups ready; partial or stale replies do not.
function E.recast_cache(ctx)
    local actor=ctx and (ctx.actor or ctx.self);
    local actorId=E.number(ctx and ctx.catalogActorId) or E.number(actor and actor.id);
    local cached=actorId and S.recastByActor[actorId];
    if not cached or not ctx then return nil; end
    local index=E.number(ctx.catalogActorIndex) or E.number(actor and actor.entityIndex);
    local name=ctx.catalogActorName or (actor and actor.name);
    local owner=ctx.requester or (ctx.guestBridge and nil) or ctx.self;
    if cached.actorIndex~=index or cached.actorName~=name or cached.zone~=ctx.zone
        or cached.ownerId~=(owner and owner.id) then return nil; end
    if E.now()-cached.receivedAt>8 then return nil; end
    return cached;
end
function E.recast_known_block(ctx,kind,res)
    if not ctx or not ctx.generatedRecruit or (kind~='spell' and kind~='ability') then return nil; end
    local snapshot=E.recast_cache(ctx);
    if not snapshot then return nil; end -- Unknown is neither ready nor failed.
    local id=kind=='spell' and E.number(res and res.Index) or E.number(res and res.RecastTimerId);
    if not id then return nil; end
    local timer=snapshot.timers[(kind=='spell' and 'm:' or 'a:')..math.floor(id)];
    if not timer then return nil; end -- A complete active-timer snapshot has no timer.
    local remaining=timer.remaining/1000-(E.now()-snapshot.receivedAt);
    if remaining>0 then return string.format('Server recast %.1fs remaining',remaining); end
    return nil;
end
function E.recast_response(message)
    local text=tostring(message or ''):gsub('%z',''):gsub('[\030\031].','');
    local at=text:find('TGRC|',1,true);
    if not at then return false; end
    local actor,nonce,part,last,payload=text:sub(at):match('^TGRC|(%d+)|(%d+)|(%d+)|([01])|(.+)$');
    local request=S.recastRequest;
    if not actor or not request or tonumber(actor)~=request.actorId or tonumber(nonce)~=request.nonce then return false; end
    E.bridge_trace('server_recast_reply',request.command,{origin='recast_response',
        actorId=request.actorId,actorIndex=request.actorIndex,mode=1});
    if tonumber(part)~=request.nextPart or request.nextPart>40 or #payload>150 then
        S.recastRequest=nil; return true;
    end
    if payload=='!' then S.recastRequest=nil; return true; end
    if payload~='-' then
        local count=0;
        if payload:sub(-1)~=';' then S.recastRequest=nil; return true; end
        for entry in payload:gmatch('([^;]+);') do
            local kind,id,remaining,total=entry:match('^([ma]),(%d+),(%d+),(%d+)$');
            if not kind then S.recastRequest=nil; return true; end
            local rem,full=tonumber(remaining),tonumber(total);
            if not rem or not full or rem<=0 or full<=0 or rem>604800000 or full>604800000 then
                S.recastRequest=nil; return true;
            end
            request.timers[kind..':'..id]={remaining=rem,total=full};
            count=count+1;
        end
        if count==0 then S.recastRequest=nil; return true; end
    end
    request.nextPart=request.nextPart+1;
    if last=='1' then
        S.recastByActor[request.actorId]={actorId=request.actorId,actorIndex=request.actorIndex,
            actorName=request.actorName,zone=request.zone,ownerId=request.ownerId,
            timers=request.timers,receivedAt=E.now()};
        S.recastRequest=nil;
    end
    return true;
end
function E.recast_request(ctx)
    local actor=ctx and (ctx.actor or ctx.self);
    local actorId=E.number(ctx and ctx.catalogActorId) or E.number(actor and actor.id);
    if not ctx or not ctx.generatedRecruit or not actorId or actorId<=0 then return false; end
    local now=E.now();
    if S.recastRequest and now-S.recastRequest.sentAt<3 then return false; end
    if S.recastRequest then S.recastRequest=nil; end
    local cached=E.recast_cache(ctx);
    if cached and now-cached.receivedAt<5 then return false; end
    if now-(S.recastPollAt or -10)<0.75 then return false; end
    local actorIndex=E.number(ctx.catalogActorIndex) or E.number(actor and actor.entityIndex);
    local actorName=ctx.catalogActorName or (actor and actor.name);
    local owner=ctx.requester or (ctx.guestBridge and nil) or ctx.self;
    local nonce=math.random(1,999999);
    local command='/say !gambit recasts '..math.floor(actorId)..' '..nonce;
    local sent=E.send_bridge_command(command,true,
        {origin='recast_request',actorId=actorId,actorIndex=actorIndex});
    if sent then
        S.recastPollAt=now;
        S.recastRequest={actorId=actorId,actorIndex=actorIndex,actorName=actorName,
            zone=ctx.zone,ownerId=owner and owner.id,sentAt=now,
            command=command,nonce=nonce,nextPart=1,timers={}};
    end
    return sent;
end
function E.refresh_recruit_recasts(ctx)
    if not ctx or not ctx.party then return false; end
    if S.recastRequest then
        if E.now()-S.recastRequest.sentAt<3 then return false; end
        S.recastRequest=nil;
    end
    if E.now()-(S.recastPollAt or -10)<0.75 then return false; end
    for _,actor in ipairs(ctx.party) do
        if E.is_generated_recruit(actor) and E.is_controllable_guest_member(ctx,actor)
            and E.actor_enabled(ctx,actor) then
            local cached=S.recastByActor[actor.id];
            local fresh=cached and cached.actorIndex==actor.entityIndex and cached.actorName==actor.name
                and cached.zone==ctx.zone and cached.ownerId==(ctx.self and ctx.self.id)
                and E.now()-cached.receivedAt<5;
            if not fresh then
                local view=E.actor_context(ctx,actor);
                return view and E.recast_request(view) or false;
            end
        end
    end
    return false;
end
function E.recast_view(ctx)
    if ctx.generatedRecruit then
        E.recast_request(ctx);
        local snapshot=E.recast_cache(ctx);
        return {actorId=ctx.catalogActorId or (ctx.self and ctx.self.id),server=true,snapshot=snapshot};
    end
    if ctx.catalogActorKind=='guest' then return {unsupported=true}; end
    local slots,complete={},true;
    if not ctx.recastMemory then complete=false;
    else
        for slot=0,31 do
            local id=E.call(ctx.recastMemory,'GetAbilityTimerId',slot);
            local timer=E.call(ctx.recastMemory,'GetAbilityTimer',slot);
            if type(id)~='number' or type(timer)~='number' then complete=false; break; end
            if id~=0 or slot==0 then slots[id]=timer; end
        end
    end
    return {actorId=ctx.self and ctx.self.id,slots=slots,complete=complete};
end
function E.recast_entry_progress(ctx,view,entry)
    if entry.Type=='ws' or entry.Type=='ws_auto' then
        if not ctx or ctx.catalogActorKind=='guest' then return nil,'Player TP unavailable'; end
        local tp=ctx.self and ctx.self.tp;
        if type(tp)~='number' then return nil,'Player TP unavailable'; end
        return E.clamp(tp/1000,0,1),string.format('%d/1000%s',math.floor(math.max(0,tp)),tp>=1000 and ' (ready)' or '');
    end
    if entry.Type~='spell' and entry.Type~='ability' and entry.Type~='pet' then
        return nil,'No recast timer for this action';
    end
    -- Smart actions have a candidate list instead of one fixed resource. Their
    -- current choice cannot be represented by one timer, and nil must never
    -- reach E.resource while the ImGui child/style stack is open.
    if type(entry.Action)~='string' or entry.Action=='' then
        return nil,'Dynamic action has no single recast timer';
    end
    local res=E.resource(ctx,entry.Type,entry.Action);
    local id=entry.Type=='spell' and E.number(res and res.Index) or E.number(res and res.RecastTimerId);
    if not id then return nil,'Recast timer unavailable'; end
    local remaining,total;
    if view.server then
        local snapshot=view.snapshot;
        if not snapshot then return nil,'Waiting for Recruit recast data'; end
        local key=(entry.Type=='spell' and 'm:' or 'a:')..math.floor(id);
        local timer=snapshot.timers[key];
        if timer then
            remaining=math.max(0,(timer.remaining/1000)-(E.now()-snapshot.receivedAt));
            total=timer.total/1000;
        else remaining=0; end
    elseif view.complete then
        if entry.Type=='spell' then remaining=E.call(ctx.recastMemory,'GetSpellTimer',id);
        else remaining=view.slots[id] or 0; end
        if type(remaining)~='number' then return nil,'Recast timer unavailable'; end
        local key=tostring(view.actorId)..':'..entry.Type..':'..math.floor(id);
        local previous=S.recastLast[key] or 0;
        if remaining>0 and (not S.recastTotals[key] or remaining>previous+1) then
            S.recastTotals[key]=remaining;
        end
        S.recastLast[key]=remaining;
        total=S.recastTotals[key];
    else return nil,'Recast timer unavailable'; end
    if remaining<=0 then return 1,'Ready'; end
    total=math.max(E.number(total,remaining) or remaining,remaining);
    return E.clamp(1-remaining/total,0,1),string.format('%.1fs remaining',remaining);
end
function E.recast_action_button(ctx,view,rule,id,width,selected,helpText)
    local ok,progress,readiness=pcall(E.recast_entry_progress,ctx,view,rule);
    if not ok then progress=nil; readiness='Recast timer unavailable'; end
    local label=E.rule_action_text(rule);
    local meter=(rule.Type=='ws' or rule.Type=='ws_auto') and 'TP' or 'Recast';
    local help=helpText..' '..meter..': '..readiness..'.';
    if progress==nil or not imgui.GetWindowDrawList or not imgui.GetItemRectMin or not imgui.GetItemRectMax then
        return E.segment_button(label,id,width,selected,help);
    end
    local draw=imgui.GetWindowDrawList();
    if not draw or not draw.AddRectFilled then
        return E.segment_button(label,id,width,selected,help);
    end
    local clicked=imgui.Button(label..'##'..id,{width,E.ui_button_h()});
    -- Ashita's ImGui rectangle and text-size getters return two numbers.
    -- Draw over the native button so its full area is the recast bar.
    pcall(function()
        local x,y=imgui.GetItemRectMin();
        local right,bottom=imgui.GetItemRectMax();
        if not x or not y or not right or not bottom or right<=x or bottom<=y then return; end
        draw:AddRectFilled({x+1,y+1},{x+1+(right-x-2)*progress,bottom-1},0xAA36C75A);
        if draw.AddText and imgui.CalcTextSize then
            local tw,th=imgui.CalcTextSize(label);
            tw,th=tw or 0,th or 0;
            draw:AddText({x+(right-x-tw)/2,y+(bottom-y-th)/2},0xFFF2E6D0,label);
        end
    end);
    E.hover_help(help);
    return clicked;
end
function E.action_picker(index,rule)
    local name='action-picker-'..tostring(index);
    if E.popup_begin(name) then
        local needle=E.picker_search_text('action',index,'Search','Search actions by name or type.');
        if E.picker_child_begin('##action-picker-scroll-'..index,520,380) then
            local pickerCtx=E.editor_catalog_context();
            local pickerCatalog=S.catalog or E.catalog();
            E.picker_section_header('Core Actions',true);
            if not pickerCtx.generatedRecruit and E.picker_matches(needle,'Attack','attack') and E.help_selectable('Attack##action-attack-'..index,false,'Attack the selected enemy.') then
                E.notify_save(E.update_rule(index,function(r) E.reset_action_metadata(r); r.Type='attack'; r.Action='Attack'; r.Actions=nil; r.SmartStatusRemoval=nil; E.sync_missing_status_to_action(r); end)); E.popup_close();
            end
            if E.picker_matches(needle,'Do Nothing','Hold Action','none') and E.help_selectable('Do Nothing / Hold Action##action-none-'..index,false,'Do nothing when this row matches.') then
                E.notify_save(E.update_rule(index,function(r) E.reset_action_metadata(r); r.Type='none'; r.Action='Do Nothing'; r.Actions=nil; r.SmartStatusRemoval=nil; E.sync_missing_status_to_action(r); end)); E.popup_close();
            end
            if E.picker_matches(needle,'Ranged Attack','ranged') and E.trust_action_option_allowed(pickerCtx,{'Ranged Attack','ranged',nil,nil},pickerCatalog) and E.help_selectable('Ranged Attack##action-ranged-'..index,false,'Use a ranged attack.') then
                E.notify_save(E.update_rule(index,function(r) E.reset_action_metadata(r); r.Type='ranged'; r.Action=nil; r.Actions=nil; r.SmartStatusRemoval=nil; r.Ranged=true; E.sync_missing_status_to_action(r); end)); E.popup_close();
            end
            if E.picker_matches(needle,'Best Weapon Skill','ws_auto','weapon skill') and E.trust_action_option_allowed(pickerCtx,{'Best Weapon Skill','ws_auto',nil,nil},pickerCatalog) and E.help_selectable('Best Weapon Skill##action-best-ws-'..index,false,'Use the best usable weapon skill.') then
                E.notify_save(E.update_rule(index,function(r) E.reset_action_metadata(r); r.Type='ws_auto'; r.Action=nil; r.Actions=nil; r.SmartStatusRemoval=nil; E.sync_missing_status_to_action(r); end)); E.popup_close();
            end
            E.picker_section_header('Smart Actions');
            local smart={
                {'Best Cure','cure',nil,{'Cure VI','Cure V','Cure IV','Cure III','Cure II','Cure'}},
                {'Efficient Cure','cure',nil,{'Cure IV','Cure III','Cure II','Cure'}},
                {'Cure Sufficient For Goal','cure',nil,{'Cure V','Cure IV','Cure III','Cure II','Cure'}},
                {'Best Curaga','spell',nil,{'Curaga V','Curaga IV','Curaga III','Curaga II','Curaga'}},
                {'Best Raise','spell',nil,{'Arise','Raise III','Raise II','Raise'}},
                {'Best Haste','spell',nil,{'Haste II','Haste'}},
                {'Best Protect','spell',nil,{'Protect V','Protect IV','Protect III','Protect II','Protect'}},
                {'Best Shell','spell',nil,{'Shell V','Shell IV','Shell III','Shell II','Shell'}},
                {'Best Regen','spell',nil,{'Regen V','Regen IV','Regen III','Regen II','Regen'}},
                {'Best Refresh','spell',nil,{'Refresh III','Refresh II','Refresh'}},
                {'Best Status Removal Spell','spell',nil,{'Cursna','Stona','Viruna','Silena','Paralyna','Poisona','Blindna','Erase'}},
                {'Remove Highest Priority Removable Ailment','spell',nil,{'Cursna','Stona','Viruna','Silena','Paralyna','Poisona','Blindna','Erase'}},
                {'Maintain Selected Effect','spell',nil,{'Haste II','Haste','Protect V','Protect IV','Protect III','Protect II','Protect','Shell V','Shell IV','Shell III','Shell II','Shell','Regen V','Regen IV','Regen III','Regen II','Regen','Refresh III','Refresh II','Refresh'}},
                {'Best Permitted Waltz','ability',nil,{'Curing Waltz IV','Curing Waltz III','Curing Waltz II','Curing Waltz','Healing Waltz'}},
                {'Preferred Samba','ability',nil,{'Haste Samba','Aspir Samba II','Aspir Samba','Drain Samba II','Drain Samba'}},
                {'Interrupt With Permitted Action','spell',nil,{'Stun'}},
                {'Open Skillchain','ws_auto',nil,nil,true},
                {'Close Skillchain','ws_auto',nil,nil,true},
                {'Magic Burst','spell',nil,{'Fire IV','Blizzard IV','Aero IV','Stone IV','Thunder IV','Water IV','Fire III','Blizzard III','Aero III','Stone III','Thunder III','Water III','Fire II','Blizzard II','Aero II','Stone II','Thunder II','Water II','Fire','Blizzard','Aero','Stone','Thunder','Water'}},
                {'Highest Available Nuke','spell',nil,HIGHEST_AVAILABLE_NUKES},
                {'Low-Tier Nuke','spell',nil,{'Fire','Blizzard','Aero','Stone','Thunder','Water'}},
                {'Hold All Actions','none','Do Nothing',nil},
            };
            for _,opt in ipairs(smart) do
                local visible=E.picker_matches(needle,opt[1],opt[2],opt[3],E.join(opt[4]))
                    and E.trust_action_option_allowed(pickerCtx,opt,pickerCatalog);
                local needsPolicy=E.contains({'Cure Sufficient For Goal','Best Permitted Waltz','Preferred Samba',
                    'Interrupt With Permitted Action','Open Skillchain','Close Skillchain','Magic Burst'},opt[1]);
                if visible and needsPolicy and type(S.providers.SmartActionPolicy)~='function' then
                    if imgui.TextDisabled then imgui.TextDisabled(opt[1]..' (adapter unavailable)'); end
                elseif visible and E.help_selectable(opt[1]..'##action-smart-'..opt[1]..index,false,'Smart action: '..tostring(opt[1])..'. Advanced policies require verified provider data.') then
                    E.notify_save(E.update_rule(index,function(r)
                        E.reset_action_metadata(r);
                        r.Type=opt[2]; r.Action=opt[3]; r.Actions=opt[4] and E.clone(opt[4]) or nil;
                        r.SmartActionLabel=((opt[4] or opt[5]) and opt[1]) or nil;
                        r.SmartStatusRemoval=opt[1]=='Best Status Removal Spell' or opt[1]=='Remove Highest Priority Removable Ailment';
                        if opt[1]=='Efficient Cure' then r.CureEfficiency=true; r.CureGoalHP=85; end
                        if opt[1]=='Maintain Selected Effect' then
                            r.ActionPolicy=opt[1];
                            r.MaintainEffect='Haste'; -- Visible and editable in this existing popup.
                            r.MaintainRefreshSeconds=0;
                        elseif E.contains({'Cure Sufficient For Goal','Best Permitted Waltz','Preferred Samba',
                            'Interrupt With Permitted Action','Open Skillchain','Close Skillchain','Magic Burst'},opt[1]) then
                            r.ActionPolicy=opt[1];
                        end
                        E.sync_missing_status_to_action(r);
                    end)); E.popup_close();
                end
            end
            if rule.SmartActionLabel=='Maintain Selected Effect' then
                E.picker_section_header('Effect to Maintain');
                for _,effect in ipairs({'Haste','Protect','Shell','Regen','Refresh'}) do
                    if E.help_selectable(effect..'##maintain-effect-'..index,rule.MaintainEffect==effect,'Maintain only '..effect..'.') then
                        E.notify_save(E.update_rule(index,function(r) r.MaintainEffect=effect; end)); E.popup_close();
                    end
                end
            end
            if pickerCtx.generatedRecruit then
                for _,group in ipairs({
                    {'Medicine',{'Echo Drops','Antidote','Eye Drops','Remedy','Holy Water','Potion','Hi-Potion','X-Potion','Ether','Hi-Ether','Pro-Ether','Elixir','Hi-Elixir'}},
                    {'Drink',{'Yagudo Drink','Persikos au Lait'}},
                }) do
                    E.picker_section_header(group[1]);
                    for _,itemName in ipairs(group[2]) do
                        if E.picker_matches(needle,itemName,group[1],'item')
                            and E.help_selectable(itemName..'##recruit-supply-'..index,false,'Unlimited Recruit supply; self only. Item rules still apply.') then
                            E.notify_save(E.update_rule(index,function(r)
                                E.reset_action_metadata(r); r.Type='item'; r.Action=itemName; r.Actions=nil;
                                r.Target='self'; r.Consumable=true; E.sync_missing_status_to_action(r);
                            end)); E.popup_close();
                        end
                    end
                end
            end
            E.picker_section_header('Known Actions');
            if E.help_button('Scan selected actor actions##action-scan-'..index,nil,'Refresh this actor action list.') then E.catalog(); end
            for ordinal,entry in ipairs(pickerCatalog) do
                local label=entry.Type..' | '..entry.Action;
                if E.picker_matches(needle,label,entry.Type,entry.Action) then
                    if E.help_selectable(label..'##'..E.action_entry_id(entry,index,ordinal),false,
                        'Action: '..tostring(entry.Action)..'.') then
                        if E.apply_action_entry(index,entry) then break; end
                    end
                end
            end
        end
        E.picker_child_end();
        E.popup_end();
    end
end
function E.handle_drag(index,rule)
    local rules=E.profile_rules();
    if imgui.BeginDragDropSource and imgui.SetDragDropPayload and imgui.EndDragDropSource then
        if imgui.BeginDragDropSource(0) then
            S.ui.drag=index;
            imgui.Text('Move '..E.rule_action_text(rule));
            imgui.SetDragDropPayload('GAMBIT_ROW',tostring(index));
            imgui.EndDragDropSource();
        end
    elseif imgui.IsItemActive and imgui.GetMouseDragDelta and imgui.ResetMouseDragDelta and imgui.IsItemActive() then
        S.ui.drag=index;
        local delta=imgui.GetMouseDragDelta(0);
        local dy=type(delta)=='table' and (delta[2] or delta.y) or 0;
        if dy and math.abs(dy)>24 then
            local to=math.max(1,math.min(#rules,index+(dy>0 and 1 or -1)));
            if to~=index then E.notify_save(E.move(index,to)); end
            imgui.ResetMouseDragDelta(0);
        end
    elseif S.ui.drag==index then
        S.ui.drag=nil;
    end
end
function E.handle_drop_target(index)
    if imgui.BeginDragDropTarget and imgui.AcceptDragDropPayload and imgui.EndDragDropTarget then
        if imgui.BeginDragDropTarget() then
            local payload=imgui.AcceptDragDropPayload('GAMBIT_ROW');
            if payload then
                local from=tonumber(type(payload)=='table' and (payload.Data or payload.data) or payload);
                if from and from~=index then E.notify_save(E.move(from,index)); end
                S.ui.drag=nil;
            end
            imgui.EndDragDropTarget();
        end
    end
end
function E.ui_rules()
    if not S.profile then imgui.Text('A live character is required to load a job profile.'); return; end
    E.normalize_tab();
    S.ui.roleTab=S.ui.roleTab or 'main';
    -- The shared party row is rendered above every tab.
    local childFlags=rawget(_G,'ImGuiChildFlags_Borders') or 0;
    local windowW=select(1,E.ui_window_size());
    local listW=math.max(E.s(1046),(windowW or E.s(1080))-(E.ui_outer_border()*2));
    local rowW=math.max(E.s(940),listW-E.s(24));
    local activeProfile,activeKind=E.active_profile();
    if not activeProfile then imgui.Text('A live character is required to load this Gambit sheet.'); return; end
    local recastCtx=E.editor_catalog_context();
    local recastView=E.recast_view(recastCtx);
    E.ui_help_line(rowW);
    imgui.Separator();
    local numW=E.s(30); local arrowW=E.s(54); local onW=E.s(64); local targetW=E.s(148); local deleteW=E.s(32); local cellGap=E.s(8);
    local rowGaps=cellGap*7;
    local flexW=math.max(E.s(650),rowW-numW-arrowW-onW-targetW-deleteW-rowGaps);
    local actionW=math.max(E.s(170),math.floor(flexW*0.24));
    local condW=math.max(E.s(230),math.floor((flexW-actionW)*0.5));
    local cond2W=math.max(E.s(230),flexW-actionW-condW);
    local cols=E.ui_grid_columns(rowW,numW,arrowW,onW,targetW,condW,cond2W,actionW,deleteW,cellGap);
    local rowHeight=E.ui_row_h();
    local visibleRows=E.visible_gambit_rows();
    local gridInset=E.ui_outer_border();
    local headerX=imgui.GetCursorPosX()+gridInset;
    imgui.SetCursorPosX(headerX+cols.num.x); E.ui_column_header('# ', 'number', cols.num.w,'Lower rows wait for higher rows.');
    E.ui_grid_cell(headerX,cols.move); E.ui_column_header('MOVE', 'arrows', cols.move.w,'Change row priority.');
    E.ui_grid_cell(headerX,cols.on); E.ui_column_header('ON/OFF', 'on', cols.on.w,'Toggle this row.');
    E.ui_grid_cell(headerX,cols.target); E.ui_column_header('TARGET', 'target', cols.target.w,'Recipient of this row action and subject of selected-target conditions.');
    E.ui_grid_cell(headerX,cols.condition1); E.ui_column_header('CONDITION #1', 'condition1', cols.condition1.w,'Primary condition for this row.');
    E.ui_grid_cell(headerX,cols.condition2); E.ui_column_header('CONDITION #2', 'condition2', cols.condition2.w,'Optional second condition. If set, both conditions must pass.');
    E.ui_grid_cell(headerX,cols.action); E.ui_column_header('ACTIONS', 'actions', cols.action.w,'What this row does.');
    local listHeight=(rowHeight*visibleRows)+E.s(18);
    local listOpen=false;
    local listWindowFlags=(rawget(_G,'ImGuiWindowFlags_NoScrollbar') or 0)+(rawget(_G,'ImGuiWindowFlags_NoScrollWithMouse') or 0);
    if listWindowFlags~=0 then
        local ok,value=pcall(imgui.BeginChild,'##gambit-list',{listW,listHeight},childFlags,listWindowFlags);
        if ok then listOpen=value; else listOpen=imgui.BeginChild('##gambit-list',{listW,listHeight},childFlags); end
    else
        listOpen=imgui.BeginChild('##gambit-list',{listW,listHeight},childFlags);
    end
    if listOpen then
        local recruitTab=S.ui.roleTab=='partyguest' and E.editor_catalog_context().generatedRecruit;
        local masterOn=not recruitTab and G.IsEnabled();
        local rules=activeProfile.Rules or {};
        local rowCount=E.gambit_row_count(rules);
        local moveHoverRow=S.ui.moveHoverRow;
        S.ui.moveHoverRow=nil;
        for i=1,rowCount do
            local rowX=imgui.GetCursorPosX();
            local r=rules[i];
            local rowEmpty=E.gambit_row_is_add(rules,i);
            local sheetFlash=(not rowEmpty) and E.now()<(S.ui.sheetFlashUntil or 0);
            local rowFlash=(not rowEmpty) and ((S.ui.flashRow==i and E.now()<(S.ui.flashUntil or 0)) or sheetFlash);
            local rowMoveHover=(not rowEmpty) and moveHoverRow==i;
            local rowHighlighted=rowFlash or rowMoveHover;
            local rowFlashColors=0;
            if rowMoveHover then rowFlashColors=E.push_add_gambit_colors();
            elseif sheetFlash then rowFlashColors=E.push_sheet_flash_colors();
            elseif rowFlash then rowFlashColors=E.push_move_flash_colors(); end
            imgui.SetCursorPosX(rowX+cols.num.x);
            if rowHighlighted then E.help_button(tostring(i)..'##row-number-'..i,{cols.num.w,E.ui_button_h()},E.rule_summary_text(r,i)); else E.ui_column_header(tostring(i), 'row-number-'..i, cols.num.w,E.rule_summary_text(r,i)); end
            if rowEmpty then
                local emptyAddColors=E.push_add_gambit_colors();
                E.ui_grid_cell(rowX,cols.move);
                if E.help_button('+ ADD NEW GAMBIT##empty-add-bottom',{cols.total-cols.move.x,E.ui_button_h()},'Add a Gambit at the bottom of the stack.') then E.new_rule(nil,#rules+1); end
                if emptyAddColors>0 then imgui.PopStyleColor(emptyAddColors); end
            else
            local selected=S.ui.selected==i;
            local pushed=0;
            local rowBreak=false;
            if selected and rawget(_G,'ImGuiCol_Header')~=nil then imgui.PushStyleColor(rawget(_G,'ImGuiCol_Header'),{0.78,0.64,0.30,0.32}); pushed=pushed+1; end
            if S.ui.drag==i and rawget(_G,'ImGuiCol_Button')~=nil then imgui.PushStyleColor(rawget(_G,'ImGuiCol_Button'),{0.78,0.64,0.30,0.50}); pushed=pushed+1; end
            local savedEnabled=(r.Enabled~=false);
            local effectiveEnabled=masterOn and savedEnabled;
            local dimColors=0;
            if not effectiveEnabled and not rowHighlighted then dimColors=E.push_dimmed_row_colors(); end
            E.ui_grid_cell(rowX,cols.move);
            if i==1 then E.small_disabled_arrow('^##up-'..r.Id); else
                if E.help_button('^##up-'..r.Id,{E.ui_icon_w(),E.ui_button_h()},'Move row '..tostring(i)..' up.') then E.notify_save(E.move(i,i-1)); rowBreak=true; end
                if E.item_hovered() then S.ui.moveHoverRow=i; end
            end
            imgui.SameLine(); imgui.SetCursorPosX(rowX+cols.move.x+E.s(28));
            if i==#rules then E.small_disabled_arrow('v##down-'..r.Id); else
                if E.help_button('v##down-'..r.Id,{E.ui_icon_w(),E.ui_button_h()},'Move row '..tostring(i)..' down.') then E.notify_save(E.move(i,i+1)); rowBreak=true; end
                if E.item_hovered() then S.ui.moveHoverRow=i; end
            end
            if dimColors>0 then imgui.PopStyleColor(dimColors); dimColors=0; end
            E.ui_grid_cell(rowX,cols.on);
            local enabledText=effectiveEnabled and 'ON' or 'OFF';
            local onOffColors=E.push_onoff_button_colors(effectiveEnabled);
            if E.segment_button(enabledText,'enable-cell-'..r.Id,cols.on.w,selected,E.rule_enabled_help(r,i,effectiveEnabled)) then
                E.notify_save(E.update_rule(i,function(row) row.Enabled=not (row.Enabled~=false); end));
                S.ui.selected=i;
            end
            if onOffColors>0 then imgui.PopStyleColor(onOffColors); end
            E.ui_grid_cell(rowX,cols.target);
            if not effectiveEnabled and not rowHighlighted then dimColors=E.push_dimmed_row_colors(); end
            if E.segment_button(E.rule_target_text(r),'target-cell-'..r.Id,cols.target.w,selected,E.rule_target_help(r,i)) then S.ui.selected=i; E.popup_open('target-picker-'..i); end
            E.target_picker(i,r);
            E.ui_grid_cell(rowX,cols.condition1);
            if E.segment_button(E.condition_slot_text(r,1),'condition1-cell-'..r.Id,cols.condition1.w,selected,E.condition_slot_help(r,i,1)) then S.ui.selected=i; E.popup_open('condition-picker-'..i..'-1'); end
            E.condition_picker(i,r,1);
            E.ui_grid_cell(rowX,cols.condition2);
            if E.segment_button(E.condition_slot_text(r,2),'condition2-cell-'..r.Id,cols.condition2.w,selected,E.condition_slot_help(r,i,2)) then S.ui.selected=i; E.popup_open('condition-picker-'..i..'-2'); end
            E.condition_picker(i,r,2);
            E.ui_grid_cell(rowX,cols.action);
            if E.recast_action_button(recastCtx,recastView,r,'action-cell-'..r.Id,cols.action.w,selected,E.rule_action_help(r,i)) then S.ui.selected=i; E.popup_open('action-picker-'..i); end
            E.action_picker(i,r);
            if dimColors>0 then imgui.PopStyleColor(dimColors); dimColors=0; end
            E.ui_grid_cell(rowX,cols.delete);
            local pushedDeleteColors=0;
            if not rowHighlighted then
                local deleteColorId=rawget(_G,'ImGuiCol_Button');
                local deleteHoverId=rawget(_G,'ImGuiCol_ButtonHovered');
                local deleteActiveId=rawget(_G,'ImGuiCol_ButtonActive');
                if deleteColorId~=nil then imgui.PushStyleColor(deleteColorId,{0.46,0.10,0.08,1}); pushedDeleteColors=pushedDeleteColors+1; end
                if deleteHoverId~=nil then imgui.PushStyleColor(deleteHoverId,{0.68,0.14,0.10,1}); pushedDeleteColors=pushedDeleteColors+1; end
                if deleteActiveId~=nil then imgui.PushStyleColor(deleteActiveId,{0.88,0.20,0.14,1}); pushedDeleteColors=pushedDeleteColors+1; end
            end
            if E.help_button('X##delete-'..r.Id,{E.ui_icon_w(),E.ui_button_h()},'Delete row '..tostring(i)..'.') then
                local updated=E.compact_rules(G.GetRules());
                table.remove(updated,i);
                E.notify_save(G.SetRules(updated)); S.ui.selected=math.max(1,math.min(i,#updated)); S.ui.edits={}; rowBreak=true;
            end
            if pushedDeleteColors>0 then imgui.PopStyleColor(pushedDeleteColors); end
            if pushed>0 then imgui.PopStyleColor(pushed); end
            if rowFlashColors>0 then imgui.PopStyleColor(rowFlashColors); end
            if rowBreak then break; end
            end
        end
        if imgui.Dummy then imgui.Dummy({rowW,E.s(6)}); end
    end
    imgui.EndChild();
end
function E.ui_settings()
    imgui.Text('Shared options affect clients using this same Ashita config directory. Master switches are per character and Trust.');
    for _,key in ipairs({'Debug','UseServerBridge','FallbackVisibleCommands','HealAlliance','RaiseInCombat','AllowUnclaimedTargets',
        'AllowSpecialAbilities','AllowConsumables','AllowAreaDamage','PauseWhileInvisible'}) do
        local box={(S.settings or DEFAULT)[key]==true};
        if E.help_checkbox(key,box,'Toggle setting: '..tostring(key)..'.') then E.notify_save(E.settings_change(key,box[1])); end
    end
    for _,key in ipairs({'StationaryDelaySeconds','ActionLockSeconds','TickSeconds','ManualPauseSeconds',
        'ZoneDelaySeconds','MPReserve','PartyBuffMaxAge','MaxDefaultLevel','AbilityIdOffset','PetCommandIdOffset'}) do
        local b=E.buffer('setting-'..key,(S.settings or DEFAULT)[key]);
        E.help_input_text(key,b,32,'Edit '..tostring(key)..'.'); imgui.SameLine();
        if E.help_button('Apply##'..key,nil,'Apply '..tostring(key)..'.') then
            local n=E.number(b[1]);
            if n then E.notify_save(E.settings_change(key,n)); else E.log(key..' must be numeric.',true); end
        end
    end
    if S.profile then
        imgui.Separator(); imgui.Text('BLU equipped-set declaration for this main-job profile:');
        local b=E.buffer('blue-set',E.join(S.profile.BlueSet));
        E.help_input_text('Equipped spell names, comma-separated',b,2048,'Your equipped Blue Magic spells.');
        if E.help_button('Confirm BLU set and start 60-second set-change lock',nil,'Save BLU spells and start lockout.') then
            E.notify_save(G.NotifyBlueSetChange(E.split(b[1])));
        end
        imgui.Text('Keep this declaration synchronized with actual equipped spells, or install a BlueSet provider.');
    end
end
function E.ui_catalog()
    imgui.Text('Client-known actions. Passive traits are not castable actions.');
    imgui.Text('Spells are filtered by the configured level cap. New rules start disabled.');
    if E.help_button('Scan current character actions',nil,'Refresh current action list.') then E.catalog(); end
    local search=E.buffer('catalog-search',''); E.help_input_text('Filter',search,128,'Filter actions by name.');
    if imgui.BeginChild('##catalog-list',{0,E.s(480)},rawget(_G,'ImGuiChildFlags_Borders') or 0) then
        for _,v in ipairs(S.catalog or {}) do
            if E.lower(v.Action):find(E.lower(search[1]),1,true) then
                if E.help_selectable(string.format('%s | %s | MP %d##catalog-%s-%d',v.Type,v.Action,v.MP,v.Type,v.Id),false,'Add disabled row: '..tostring(v.Action)..'.') then
                    E.new_rule(v); break;
                end
            end
        end
    end
    imgui.EndChild();
end
function E.ui_presets()
    imgui.TextWrapped('Presets are saved character/job Gambit sheets. Use Add or duplicate rows from the Gambits tab for now; import/export stays file based.');
    if E.help_button('Scan current character actions',nil,'Refresh action list.') then E.catalog(); end
    imgui.SameLine();
    if E.help_button('Add selected action as disabled row',nil,'Add first listed action.') then
        local first=(S.catalog or E.catalog())[1];
        if first then E.new_rule(first); end
    end
    local search=E.buffer('preset-action-search',''); E.help_input_text('Action search',search,128,'Filter preset actions.');
    local _,h=E.ui_available(E.s(420));
    if imgui.BeginChild('##preset-action-list',{0,math.max(E.s(200),h)},rawget(_G,'ImGuiChildFlags_Borders') or 0) then
        for _,v in ipairs(S.catalog or {}) do
            if E.lower(v.Action):find(E.lower(search[1]),1,true) then
                if E.help_selectable(string.format('%s | %s | MP %d##preset-action-%s-%d',v.Type,v.Action,v.MP,v.Type,v.Id),false,'Add disabled preset: '..tostring(v.Action)..'.') then
                    E.new_rule(v); break;
                end
            end
        end
    end
    imgui.EndChild();
end
function E.ui_diagnostics()
    imgui.TextWrapped('Gate: '..S.lastBlock);
    imgui.TextWrapped('Last selected attempt: '..S.lastDecision);
    if S.configError or S.profileError or S.switchError then imgui.TextWrapped('Configuration error: '..tostring(S.configError or S.profileError or S.switchError)); end
    if S.profilePath then imgui.TextWrapped('Profile: '..S.profilePath); end
    for actorId,plan in pairs(S.pendingByActor) do
        imgui.Text('Pending '..tostring(actorId)..': '..tostring(plan.name)..(plan.sent and ' (outgoing observed)' or ' (submitted, unobserved)'));
    end
    imgui.Text('Failed or unverified rules do not consume a successful action slot.');
    if imgui.BeginChild('##diagnostics',{0,E.s(500)},rawget(_G,'ImGuiChildFlags_Borders') or 0) then
        for _,w in ipairs(S.why) do imgui.TextWrapped(string.format('%02d %s: %s',w.index,w.id,w.reason)); end
        imgui.Separator();
        for _,l in ipairs(S.logs) do imgui.TextWrapped(l.time..'  '..l.text); end
    end
    imgui.EndChild();
end
function E.watch_tab_bar()
    local tabs={'GAMBITS','PARSER','EXP WATCH','ENEMY INFO'};
    local available=E.ui_available();
    local gap=E.s(6);
    local width=math.floor((available-3*gap)/4);
    for i,tab in ipairs(tabs) do
        if i>1 then imgui.SameLine(0,gap); end
        local active=tab==S.watch.tab;
        local pushed=0;
        local color=rawget(_G,'ImGuiCol_Button');
        if active and color~=nil then
            imgui.PushStyleColor(color,{0.53,0.42,0.09,1}); pushed=1;
        end
        if imgui.Button(tab..'##utility-tab-'..i,{width,E.ui_button_h()}) then S.watch.tab=tab; end
        if pushed>0 then imgui.PopStyleColor(pushed); end
    end
end
function E.watch_damage_rows(now)
    local q=E.watch_queue('damage');
    local totals=q.totals or {}; local total=0;
    local rows={};
    for id,amount in pairs(totals) do
        if S.watch.roster[id] then
            rows[#rows+1]={id=id,amount=amount,actor=S.watch.roster[id]};
            total=total+amount;
        end
    end
    table.sort(rows,function(a,b)
        return a.amount==b.amount and a.actor.name<b.actor.name or a.amount>b.amount;
    end);
    local first=q.events[q.head];
    return rows,total,math.min(WATCH_WINDOW_SECONDS,math.max(1,now-((first and first.at) or now)));
end
function E.ui_parser()
    local rows,total=E.watch_damage_rows(E.now());
    imgui.Text('PARTY / ALLIANCE DAMAGE - ROLLING 60 MINUTES');
    imgui.Text(string.format('%d damage in the last 60 minutes across %d tracked members',total,#rows));
    imgui.Separator();
    if imgui.BeginChild('##watch-parser-rows',{0,E.s(475)},rawget(_G,'ImGuiChildFlags_Borders') or 0) then
        if #rows==0 then imgui.TextWrapped('Damage from current party or alliance members and Recruits will appear here.'); end
        for _,row in ipairs(rows) do
            local actor=row.actor;
            local share=total>0 and row.amount*100/total or 0;
            local hourly=row.amount;
            local label=string.format('%s  %s  %s  |  %s damage  |  %.1f%%  |  %s/hr##watch-%u',
                actor.job,actor.name,actor.recruit and 'Recruit' or 'Adventurer',
                tostring(row.amount),share,tostring(hourly),row.id);
            local pushed=E.push_recruit_slot_colors(actor.role,false);
            imgui.Button(label,{E.ui_available()-E.s(8),E.ui_row_h()});
            if pushed>0 then imgui.PopStyleColor(pushed); end
        end
    end
    imgui.EndChild();
end
function E.exp_watch_snapshot(now)
    local previous=S.watch.expDisplay;
    if previous and now-previous.at<15 then return previous; end
    local q=E.watch_queue('exp');
    local totals={monster=0,fov=0,gov=0,other=0};
    local counts={monster=0,fov=0,gov=0,other=0};
    local limit=0; local chains=0; local first=nil;
    for i=q.head,#q.events do
        local event=q.events[i];
        if event then
            totals[event.source]=(totals[event.source] or 0)+event.amount;
            counts[event.source]=(counts[event.source] or 0)+1;
            if event.limit then limit=limit+event.amount; end
            if event.chain then chains=chains+1; end
            first=first and math.min(first,event.at) or event.at;
        end
    end
    local total=totals.monster+totals.fov+totals.gov+totals.other;
    -- An early burst is too short a sample for a useful per-hour projection.
    local elapsed=math.min(WATCH_WINDOW_SECONDS,math.max(300,now-(first or now)));
    local snapshot={at=now,totals=totals,counts=counts,limit=limit,chains=chains,total=total,
        rate=math.floor(total*3600/elapsed+0.5)};
    S.watch.expDisplay=snapshot;
    return snapshot;
end
function E.ui_exp_watch()
    local snapshot=E.exp_watch_snapshot(E.now());
    local totals=snapshot.totals; local counts=snapshot.counts;
    imgui.Text('EXP WATCH - ROLLING 60 MINUTES (15s REFRESH)');
    imgui.Separator();
    imgui.Text(string.format('EXP / LIMIT EARNED: %d',snapshot.total));
    imgui.Text(string.format('CURRENT RATE: %d / HOUR',snapshot.rate));
    imgui.Text(string.format('MONSTER: %d  |  EXP PRODUCING KILLS: %d  |  AVG: %.1f',
        totals.monster,counts.monster,counts.monster>0 and totals.monster/counts.monster or 0));
    imgui.Text(string.format('FIELDS OF VALOR: %d  |  PAGES: %d  |  AVG: %.1f',
        totals.fov,counts.fov,counts.fov>0 and totals.fov/counts.fov or 0));
    imgui.Text(string.format('GROUNDS OF VALOR: %d  |  PAGES: %d  |  AVG: %.1f',
        totals.gov,counts.gov,counts.gov>0 and totals.gov/counts.gov or 0));
    if totals.other>0 then imgui.Text(string.format('OTHER SCRIPTED EXP: %d  |  AWARDS: %d',totals.other,counts.other)); end
    imgui.Separator();
    imgui.Text(string.format('CHAINED AWARDS: %d  |  LIMIT POINTS INCLUDED: %d',snapshot.chains,snapshot.limit));
end
function E.ui_enemy_info()
    local enemy=S.watch.enemy;
    imgui.Text('ENEMY INFO - CURRENT TARGET');
    imgui.Separator();
    if not enemy then imgui.TextWrapped('Target a monster to inspect it.'); return; end
    if enemy.unavailable then imgui.TextWrapped('The server could not verify this target.'); return; end
    if imgui.BeginChild('##watch-enemy-fields',{0,E.s(475)},rawget(_G,'ImGuiChildFlags_Borders') or 0) then
        imgui.Text(string.format('%s  |  Server ID %u  |  Zone %s',
            tostring(enemy.name or 'Monster'),enemy.id,tostring(enemy.zone or '?')));
        imgui.Text(string.format('Entity index: %s  |  Pool: %s  |  Drop table: %s  |  Family: %s',
            tostring(enemy.index or '?'),tostring(enemy.pool or '?'),tostring(enemy.drop or '?'),tostring(enemy.family or '?')));
        local hpPercent=enemy.hp and enemy.maxHp and enemy.maxHp>0 and
            math.floor(enemy.hp*100/enemy.maxHp+0.5) or enemy.hpp;
        imgui.Text(string.format('Level: %s  |  HP: %s / %s (%s%%)  |  MP: %s / %s',
            tostring(enemy.level or '?'),tostring(enemy.hp or '?'),tostring(enemy.maxHp or '?'),
            tostring(hpPercent or '?'),tostring(enemy.mp or '?'),tostring(enemy.maxMp or '?')));
        imgui.Text(string.format('Treasure Hunter on target: %s',tostring(enemy.th or '?')));
        imgui.Separator();
        if enemy.complete then
            imgui.Text(string.format('Configured level range: %s-%s  |  Base respawn: %s seconds',
                tostring(enemy.minLevel or '?'),tostring(enemy.maxLevel or '?'),tostring(enemy.respawn or '?')));
            local mask=enemy.detection or 0;
            local senses={{1,'Sight'},{2,'Sound'},{256,'Smell'},{32,'Magic'},{4,'Low HP'},{64,'Ability'}};
            local active={};
            for _,sense in ipairs(senses) do
                if bit.band(mask,sense[1])~=0 then active[#active+1]=sense[2]; end
            end
            imgui.TextWrapped('Detection: '..(#active>0 and table.concat(active,', ') or 'none configured'));
            imgui.Text(string.format('Aggro: %s  |  Links: %s  |  True detection: %s',
                enemy.aggro and 'Yes' or 'No',enemy.link and 'Yes' or 'No',
                enemy.trueDetection and 'Yes' or 'No'));
            if enemy.scentDisabled then imgui.Text('Scent tracking disabled'); end
            imgui.Separator();
            imgui.Text('SHARED SPAWN SLOT / PLACEHOLDER CANDIDATES');
            if not enemy.slots or #enemy.slots==0 then imgui.Text('No shared slot configured.'); end
            for _,entry in ipairs(enemy.slots or {}) do
                imgui.Text(string.format('Mob ID %u  |  configured chance %u%%',entry.id,entry.chance));
            end
            imgui.Separator();
            imgui.Text(string.format('CONFIGURED LOOT  |  %d rows',enemy.lootCount or 0));
            if not enemy.drops or #enemy.drops==0 then imgui.Text('No static loot rows.'); end
            for _,row in ipairs(enemy.drops or {}) do
                if not row.name then
                    local resources=E.call(AshitaCore,'GetResourceManager');
                    local item=E.call(resources,'GetItemById',row.itemId);
                    row.name=item and item.Name and item.Name[1] or ('Item '..row.itemId);
                end
                local kind=({[0]='Drop',[2]='Steal',[4]='Despoil'})[row.dropType] or ('Type '..row.dropType);
                if row.group and row.group>0 then
                    imgui.TextWrapped(string.format('%s (%u)  |  %s  |  group %d: %.1f%% roll, weight %d%s',
                        row.name,row.itemId,kind,row.group,(row.groupRate or 0)/10,
                        row.itemRate or 0,row.groupFixed and ' fixed' or ''));
                else
                    imgui.TextWrapped(string.format('%s (%u)  |  %s  |  base %.1f%%%s',
                        row.name,row.itemId,kind,(row.itemRate or 0)/10,
                        row.fixed and ' fixed' or ''));
                end
                if row.thRates then
                    local current=math.max(0,math.min(14,enemy.th or 0));
                    imgui.Text(string.format('TH0 %.2f%%  TH1 %.2f%%  TH2 %.2f%%  TH3 %.2f%%  TH4 %.2f%%',
                        row.thRates[1]/100,row.thRates[2]/100,row.thRates[3]/100,
                        row.thRates[4]/100,row.thRates[5]/100));
                    if current>4 then
                        imgui.Text(string.format('Current TH%d %.2f%%',current,row.thRates[current+1]/100));
                    end
                end
            end
            if (enemy.lootCount or 0)>#(enemy.drops or {}) then
                imgui.TextWrapped('Additional configured loot rows are omitted from the bridge display.');
            end
            if enemy.noDrops then
                imgui.TextWrapped('Drops are disabled for this mob. Configured rows above cannot drop.');
            elseif enemy.dynamicDrops then
                imgui.TextWrapped('This mob has scripted drop changes. TH rates above apply to the configured static rows only; scripted drops may differ.');
            else
                imgui.TextWrapped('TH probabilities use the server\'s formula, group weights and configured drop multiplier. Special or scripted reward paths may differ.');
            end
        else
            imgui.TextWrapped('Loading verified detection, spawn and loot metadata...');
        end
    end
    imgui.EndChild();
end
function E.render()
    if not S.ui.open[1] then return; end
    if not imgui then
        S.ui.open[1]=false; E.log('ImGui is unavailable. Slash commands and file editing remain available.',true); return;
    end
    S.ui.helpSeen=false;
    local pushed=0;
    local solidBg={0.105,0.095,0.082,1.0};
    for _,v in ipairs({{'ImGuiCol_WindowBg',solidBg}, {'ImGuiCol_ChildBg',solidBg}, {'ImGuiCol_PopupBg',solidBg}, {'ImGuiCol_FrameBg',solidBg},
        {'ImGuiCol_Header',{0.23,0.18,0.10,1}}, {'ImGuiCol_Button',{0.24,0.19,0.10,1}},
        {'ImGuiCol_Text',{0.91,0.89,0.80,1}}}) do
        local color=rawget(_G,v[1]);
        if color~=nil then imgui.PushStyleColor(color,v[2]); pushed=pushed+1; end
    end
    local uiScale=E.ui_scale();
    local fontPushed=E.push_resolution_ui_font(uiScale);
    local stylePushed=E.push_scaled_ui_style();
    local windowW,windowH=E.ui_window_size();
    imgui.SetNextWindowSize({windowW,windowH},rawget(_G,'ImGuiCond_Always') or 1);
    local windowFlags=rawget(_G,'ImGuiWindowFlags_NoResize') or 0;
    local noCollapse=rawget(_G,'ImGuiWindowFlags_NoCollapse') or 0;
    local noScrollbar=rawget(_G,'ImGuiWindowFlags_NoScrollbar') or 0;
    local noScrollMouse=rawget(_G,'ImGuiWindowFlags_NoScrollWithMouse') or 0;
    local noMouseInputs=rawget(_G,'ImGuiWindowFlags_NoMouseInputs') or 0;
    windowFlags=windowFlags+noCollapse+noScrollbar+noScrollMouse;
    if (S.settings or DEFAULT).MouseCapture==false then windowFlags=windowFlags+noMouseInputs; end
    local shown=imgui.Begin('AUTOBOX v'..tostring(addon.version)..(((S.settings or DEFAULT).MouseCapture==false) and ' | MOUSE PASS' or ''),S.ui.open,windowFlags);
    if shown then
        S.ui.editorBounds=nil;
        if imgui.GetWindowPos and imgui.GetWindowSize then
            local x,y=E.popup_window_pair(imgui.GetWindowPos());
            local width,height=E.popup_window_pair(imgui.GetWindowSize());
            if x and y and width and height and width>0 and height>0 then
                S.ui.editorBounds={x=x,y=y,width=width,height=height};
            end
        end
        E.apply_resolution_ui_font(fontPushed);
        E.watch_tab_bar();
        imgui.Separator();
        E.ui_scale_controls();
        local topWidth=E.ui_available();
        if not topWidth or topWidth<=0 then topWidth=windowW-E.s(16); end
        local topGap=E.s(6);
        local controlWidth=math.floor((topWidth-3*topGap)/4);
        local lastWidth=topWidth-3*topGap-3*controlWidth;
        local masterOn=G.IsEnabled();
        local masterColors=0;
        local buttonId=rawget(_G,'ImGuiCol_Button');
        local hoverId=rawget(_G,'ImGuiCol_ButtonHovered');
        local activeId=rawget(_G,'ImGuiCol_ButtonActive');
        if buttonId~=nil then imgui.PushStyleColor(buttonId,masterOn and {0.12,0.42,0.22,1} or {0.48,0.12,0.10,1}); masterColors=masterColors+1; end
        if hoverId~=nil then imgui.PushStyleColor(hoverId,masterOn and {0.18,0.60,0.32,1} or {0.66,0.18,0.14,1}); masterColors=masterColors+1; end
        if activeId~=nil then imgui.PushStyleColor(activeId,masterOn and {0.30,0.76,0.46,1} or {0.82,0.24,0.18,1}); masterColors=masterColors+1; end
        if E.help_button(masterOn and 'GAMBITS ON' or 'GAMBITS OFF',{controlWidth,E.ui_button_h()},
            masterOn and 'Gambits enabled. Click to pause.' or 'Gambits paused. Click to enable.') then E.notify_save(G.SetEnabled(not masterOn)); end
        if masterColors>0 then imgui.PopStyleColor(masterColors); end
        imgui.SameLine(0,topGap);
        E.inventory_display(topWidth-controlWidth-topGap);
        imgui.Separator();
        if S.watch.tab=='GAMBITS' then
        E.normalize_tab();
        E.ui_rules();
        -- The fixed 14-row sheet needs no vertical resize control.
        elseif S.watch.tab=='PARSER' then E.ui_parser();
        elseif S.watch.tab=='EXP WATCH' then E.ui_exp_watch();
        elseif S.watch.tab=='ENEMY INFO' then E.ui_enemy_info(); end
    end
    imgui.End();
    if not S.ui.helpSeen then S.ui.helpText=nil; end
    if stylePushed>0 and imgui.PopStyleVar then imgui.PopStyleVar(stylePushed); end
    E.pop_resolution_ui_font(fontPushed);
    if pushed>0 then imgui.PopStyleColor(pushed); end
end
function E.traceback(err)
    local trace=debug and debug.traceback and debug.traceback(tostring(err),2) or tostring(err);
    return tostring(trace):sub(1,1600);
end
function E.report_error(domain,err)
    S.errorCounts=S.errorCounts or {};
    S.errorAt=S.errorAt or {};
    S.errorCounts[domain]=(S.errorCounts[domain] or 0)+1;
    local now=E.now();
    if now-(S.errorAt[domain] or -10)>=5 then
        E.log(domain..' error #'..S.errorCounts[domain]..': '..E.traceback(err),true);
        S.errorAt[domain]=now;
    end
end
function E.guarded(name,fn)
    return function(...)
        local args={...};
        local count=select('#',...);
        local ok,err=xpcall(function() return fn((unpack or table.unpack)(args,1,count)); end,E.traceback);
        if not ok then
            E.report_error(name,err);
            S.lastBlock=name..' execution error; automatic execution paused';
            S.pauseUntil=math.max(S.pauseUntil,E.now()+5);
        end
    end;
end
function E.render_isolated()
    if not imgui or not S.ui.open[1] then return; end
    -- Track only ImGui stack calls made by this window. On a UI exception,
    -- unwind in reverse order before closing the editor for this session.
    local specs={
        Begin={'End',true}, BeginChild={'EndChild',true}, BeginPopup={'EndPopup',false},
        BeginDisabled={'EndDisabled',true},
        BeginDragDropSource={'EndDragDropSource',false}, BeginDragDropTarget={'EndDragDropTarget',false},
        PushStyleColor={'PopStyleColor',true}, PushStyleVar={'PopStyleVar',true}, PushFont={'PopFont',true},
    };
    local ends={End=true,EndChild=true,EndPopup=true,EndDisabled=true,EndDragDropSource=true,
        EndDragDropTarget=true,PopStyleColor=true,PopStyleVar=true,PopFont=true};
    local original,stack={},{};
    local function pack(...) return {n=select('#',...),...}; end
    for name in pairs(specs) do original[name]=imgui[name]; end
    for name in pairs(ends) do original[name]=imgui[name]; end
    local function pop(which,count)
        for _=1,(count or 1) do
            for i=#stack,1,-1 do
                if stack[i]==which then table.remove(stack,i); break; end
            end
        end
    end
    local wrapOk=true;
    for name,spec in pairs(specs) do
        if type(original[name])=='function' then
            local method=name; local close=spec[1]; local unconditional=spec[2];
            local ok=pcall(function()
                imgui[method]=function(...)
                    local result=pack(original[method](...));
                    if unconditional or result[1] then stack[#stack+1]=close; end
                    return (unpack or table.unpack)(result,1,result.n);
                end;
            end);
            if not ok then wrapOk=false; break; end
        end
    end
    if wrapOk then
        for name in pairs(ends) do
            if type(original[name])=='function' then
                local method=name;
                local ok=pcall(function()
                    imgui[method]=function(...)
                        local count=(method=='PopStyleColor' or method=='PopStyleVar') and tonumber((...)) or 1;
                        local result=pack(original[method](...));
                        pop(method,count);
                        return (unpack or table.unpack)(result,1,result.n);
                    end;
                end);
                if not ok then wrapOk=false; break; end
            end
        end
    end
    local ok,err;
    if wrapOk then ok,err=xpcall(E.render,E.traceback);
    else ok=false; err='ImGui stack wrappers are unavailable'; end
    for name,fn in pairs(original) do pcall(function() imgui[name]=fn; end); end
    if not ok then
        for i=#stack,1,-1 do
            local close=original[stack[i]];
            if type(close)=='function' then pcall(close); end
        end
        S.ui.open[1]=false;
        E.report_error('render',err);
    end
end

ashita.events.register('load','gambits_load',E.guarded('load',function()
    E.settings_load(true);
    E.remove_recruit_sheets();
    E.reset_runtime('Startup');
    if S.rootMigrated then E.log(S.rootMigrated,true); end
    E.log('Loaded '..tostring(addon.version)..' (formerly Gambits). /autobox opens it; your sheets are still under config/addons/Gambits.',true);
    E.loaded_flag(true);
end));
ashita.events.register('unload','gambits_unload',function()
    E.loaded_flag(false);
    -- Do not rewrite the launcher switch. Release only leases this instance recorded.
    pcall(function() E.release_guest_control(E.context('unload')); end);
    S.pending=nil; S.pendingByActor={}; S.actorLocks={}; S.outgoingIntent=nil;
end);
ashita.events.register('command','gambits_command',E.guarded('command',E.command_event));
ashita.events.register('text_in','gambits_text_in',E.guarded('text_in',function(e)
    if e.blocked then return; end
    local incoming=tostring(e.message_modified or e.message or '');
    if E.watch_enemy_response(incoming) then e.blocked=true; return; end
    E.sort_response(incoming);
    E.optimize_response(incoming);
    if E.is_command_error_message(incoming) or E.is_command_error_message(e.message) then
        local speech=S.lastBridgeSpeech;
        if speech and E.now()-speech.time<=1.25 then
            E.bridge_trace('client_command_error_hidden',speech.command,{origin='text_in'});
            S.lastBridgeSpeech=nil;
            e.blocked=true;
            return;
        end
    end
    if E.action_response(incoming) then e.blocked=true; return; end
    if E.status_response(incoming) then e.blocked=true; return; end
    if E.recruit_response(incoming) then e.blocked=true; return; end
    if E.control_response(incoming) then e.blocked=true; return; end
    if E.recruit_stance_response(e.message_modified or e.message) then e.blocked=true; return; end
    if E.recast_response(e.message_modified or e.message) then e.blocked=true; return; end
    if E.is_hidden_bridge_chat_message(e.message_modified or e.message) then e.blocked=true; end
end));
-- text_out blocks transmission, not just display. Hide echoes only in text_in.
ashita.events.register('packet_in','gambits_packet_in',E.guarded('packet_in',E.packet_in));
ashita.events.register('packet_out','gambits_packet_out',E.guarded('packet_out',E.packet_out));
ashita.events.register('d3d_present','gambits_present',function()
    E.guarded('engine',function() E.pump('d3d_present'); end)();
    E.render_isolated();
end);

-- Test access is opt-in before loading the module; it is absent in normal operation.
if rawget(_G,'GAMBITS_TEST') then G._test={E=E,S=S,DEFAULT=DEFAULT,JOBS=JOBS,WS=WS}; end
return G;
