--[[
followme 1.1
Keeps THIS character following a chosen player, and fighting what that player fights, using only the game's own commands:
  /follow <leader>   when the leader is more than a few yalms away
  /assist <leader>   when the leader is fighting a monster and this character is not targeting it (so the gambit engine has its target)
  /attack <t>        to engage that monster
  /attack off        some seconds after the leader has stopped fighting, if this character is still engaged
It never moves the character itself and never starts a fight the leader is not already in.

Commands (/followme or /fm):
  on | off          switch it all on or off (saved)
  leader <Name>     who to follow and assist (saved)
  distance <n>      send /follow when farther than n yalms (default 5)
  follow on|off     follow off = hold this spot (camp), still fighting with the leader; not saved
  assist on|off     assist the leader's target (default on)
  engage on|off     also engage it with /attack (default on)
  status            what it is doing, and why
  debug             print a message each time it decides something

DUALBOX REMOTE CONTROL (0.3): the Squad panel in your main window can switch this character to Auto and pick his job profile. The two game
windows talk through two small files in config/addons/duo: this addon writes status.cfg every second (name, job, HP, MP, what it is doing, and the
gambit engine's own "why" line) and reads command.cfg, which the panel writes.
  /fm auto on|off          follow + assist + attack, AND the gambit engine's master switch (/autobox on|off)
  /fm profile <role>       auto | tank | damage | healer | support: switches the gambit rows of his current job on or off to match
                           (it uses the engine's own /autobox enable|disable, and re-applies when his job changes)
  /fm unclaimed on|off     lets the gambit engine act on the monster he is fighting even when the game does not show who claimed it
                           (the engine's own AllowUnclaimedTargets setting; on by default, and kept as you set it)
  (automatic)              while he is engaged with a target, the probe runs several times a second (it only READS the game); the last such
                           snapshot is kept for the panel, so a fight that is over in two seconds can still be examined.
  Why this addon asks the gambit engine so little: the engine treats ANY command it did not send itself as you typing in chat, and
  pauses for 1.25 seconds. Every question asked is a pause. So it is not asked during a fight (unless fight_ask is turned on in
  followme.cfg), only about every ten seconds when nothing is going on, and never while the leader is fighting.
  /fm probe [spell]        checks, one by one, everything the gambit engine needs before it can cast that spell (default Dia), with the
                           real value of each: his spell list, buffs, recast, MP, position, target and claim. Use it during a fight.
  /fm reset                puts his current job's rows back to the normal sheet (the engine keeps a .bak), then re-applies the profile
HOLDING CAMP (1.2): when you set a camp in the Server menu, this character stops following (the menu sends follow=off through
command.cfg; camp off sends follow=on). He still rests and fights alongside the leader, he just stays where he is. /fm follow on|off does
the same by hand. It is not saved: zoning or reloading the addon puts following back on.
SERVER MENU (0.9): the Server menu in your main window (it replaces the Squad panel) can also switch single gambit rows on or off, move a row up
or down, and show or hide the gambit engine's own window. The command file may carry several of these at once (ops=enable:dia,move:3:1,...),
and status.cfg now says which command was last carried out (ack=) and where his job's gambit sheet is (sheetpath=), so no click is lost.
  /fm row <id> on|off      switches one row of his current job's sheet (the engine's /autobox enable|disable)
  /fm move <from> <to>     moves a row (the engine's /autobox move)
RESTING WITH THE LEADER (1.1): when the leader rests (/heal), this character rests too (/heal on), and when the leader gets up, so
does he (/heal off; only if this addon sat him down). While he rests the gambit engine is paused (/autobox pause), so a cure or a buff
does not stand him up again, and it is resumed when he gets up. rest_with_leader=false in followme.cfg turns this off.
HEALING THE WHOLE PARTY (1.0): the engine's everyday cure row (maintenance-cure) waits until someone is missing at least 40 HP.
A low-level character never has 40 HP to lose, so it never fired and only the emergency cure (below 45%) was left. This addon lowers
that one number in his job sheet to cure_min_missing (default 10, in followme.cfg) and asks the engine to reload. It heals every
party member it can see: you, him, and your squad mates (they are Trusts in the party list).
While he is engaged he now holds still (unless the leader goes far away): the gambit engine will not act on a character who is moving.

Settings are shared by every character: config/addons/followme/followme.cfg  (lines like  leader=Hurami)
It waits after zoning, leaves a resting, dead or event state alone, and never repeats a command more often than every few seconds.
The leader must be in the same party and the same zone.
]]

addon.name    = 'followme';
addon.author  = 'XI: Forever Offline';
addon.version = '1.3';
addon.desc    = 'Keeps this character following and fighting alongside a chosen player, with the game\'s own commands.';
addon.link    = '';

require('common');

local DEFAULTS = { enabled = 'true', leader = '', distance = '5', recheck = '4', maxrange = '45', settle = '6', pause_engaged = 'false',
                   assist = 'true', engage = 'true', engage_range = '25', assist_every = '3', attack_every = '3', disengage_delay = '8',
                   profile = 'auto', gate_every = '4', poll_every = '10', fight_ask = 'false', fight_ask_after = '4', follow_engaged = 'false', engaged_range = '15', unclaimed = 'true', cure_min_missing = '10', rest_with_leader = 'true' };
local cfg = {};
local S = { lastSend = -1000, zone = 0, settleUntil = 0, reason = 'starting', debug = false, lastTick = -1000, sent = 0, lastPrinted = '',
            lastAssist = -1000, lastAttack = -1000, lastOff = -1000, leaderFoughtAt = -1000, assists = 0, attacks = 0,
            queue = {}, lastQueued = -1000, lastSeq = nil, lastWrite = -1000, statusUntil = 0, hideUntil = 0, lastStatusAsk = -1000, askedOnce = false,
            titanSeen = false, gate = '', last = '', job = nil, applyAt = nil, summary = nil, lastOwnAsk = -1000, userUntil = 0, lastSentCmd = '', lastSentAt = -1000,
            probe = nil, lastPos = nil, stillSince = nil, engaged = false, fight = nil, engagedSince = nil, lastFightProbe = -1000, lastFightAsk = -1000, unclaimed = '?', lastUnclaimedCheck = -1000,
            hold = false, restTries = 0, lastRest = -1000, restedByUs = false, restPaused = false, master = '', buffs = '', actions = '', profilePath = '', why = {}, whyNew = {}, whyUntil = 0, rows = nil, sheet = '', lastSheetRead = -1000 };

local function call(obj, name, ...)
    if obj == nil then return nil; end
    local f = obj[name];
    if type(f) ~= 'function' then return nil; end
    local ok, result = pcall(f, obj, ...);
    if ok then return result; end
    return nil;
end

local function truth(v) return v == true or (type(v) == 'number' and v ~= 0); end

local function now()
    if ashita and ashita.time and type(ashita.time.get_tick64) == 'function' then
        local ok, n = pcall(ashita.time.get_tick64);
        if ok and type(n) == 'number' then return n / 1000; end
    end
    return os.clock();
end

local function say(text)
    print('[followme] ' .. tostring(text));
end

local function num(key)
    return tonumber(cfg[key]) or tonumber(DEFAULTS[key]);
end

local function flag(key)
    return tostring(cfg[key]):lower() == 'true';
end

-- ---------------------------------------------------------------- settings file
local function cfg_dir()
    local base = call(AshitaCore, 'GetInstallPath');
    if type(base) ~= 'string' then return nil; end
    return base .. 'config/addons/followme/';
end

local function load_cfg()
    cfg = {};
    for k, v in pairs(DEFAULTS) do cfg[k] = v; end
    local dir = cfg_dir();
    if not dir then return; end
    local f = io.open(dir .. 'followme.cfg', 'r');
    if not f then return; end
    for line in f:lines() do
        local k, v = line:match('^%s*([%w_]+)%s*=%s*(.-)%s*$');
        if k and DEFAULTS[k] ~= nil then cfg[k] = v; end
    end
    f:close();
end

local function save_cfg()
    local dir = cfg_dir();
    if not dir then return false; end
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, dir); end
    local f = io.open(dir .. 'followme.cfg', 'w');
    if not f then return false; end
    local keys = {};
    for k in pairs(DEFAULTS) do keys[#keys + 1] = k; end
    table.sort(keys);
    for _, k in ipairs(keys) do f:write(k .. '=' .. tostring(cfg[k]) .. '\n'); end
    f:close();
    return true;
end

-- ---------------------------------------------------------------- the decision, once a second
local function position(ent, index)
    if not index or index == 0 then return nil; end
    local x = call(ent, 'GetLocalPositionX', index);
    local y = call(ent, 'GetLocalPositionY', index);
    local z = call(ent, 'GetLocalPositionZ', index);
    if type(x) ~= 'number' or type(y) ~= 'number' or type(z) ~= 'number' then return nil; end
    return { x = x, y = y, z = z };
end

local function is_monster(ent, index)
    local flags = call(ent, 'GetSpawnFlags', index);
    return type(flags) == 'number' and math.floor(flags / 16) % 2 == 1;
end

local function is_alive(ent, index)
    local hpp = call(ent, 'GetHPPercent', index);
    return type(hpp) == 'number' and hpp > 0;
end

local function send(command)
    S.lastSentCmd, S.lastSentAt = tostring(command):lower(), now();
    AshitaCore:GetChatManager():QueueCommand(1, command);
end

-- ---------------------------------------------------------------- job profiles
local JOBS = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU', 'COR', 'PUP', 'DNC', 'SCH', 'GEO', 'RUN' };
local ROLES = { auto = true, tank = true, damage = true, healer = true, support = true };

-- The default gambit rows of each job, as the gambit engine builds them: { rule id, layer, target }
local SHEETS =
{
    WAR = { { 'defender-emergency', 'emergency_survival', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'aggressor', 'buff_maintenance', 'self' }, { 'warcry', 'buff_maintenance', 'self' }, { 'warriors-charge', 'buff_maintenance', 'self' } },
    MNK = { { 'mantra', 'emergency_survival', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'dodge', 'buff_maintenance', 'self' }, { 'focus', 'buff_maintenance', 'self' }, { 'boost', 'buff_maintenance', 'self' }, { 'chi-blast', 'job_specific_actions', 'enemy' } },
    WHM = { { 'emergency-cursna', 'emergency_survival', 'status' }, { 'raise', 'raise', 'dead' }, { 'emergency-cure', 'emergency_healing', 'lowest' }, { 'maintenance-cure', 'emergency_healing', 'lowest' }, { 'remove-petrification', 'status_removal', 'status' }, { 'remove-silence', 'status_removal', 'status' }, { 'erase', 'status_removal', 'status' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'divine-seal', 'buff_maintenance', 'self' }, { 'haste-party', 'buff_maintenance', 'ally' }, { 'regen-party', 'buff_maintenance', 'lowest' } },
    BLM = { { 'drain', 'emergency_healing', 'enemy' }, { 'stun', 'critical_job_mechanics', 'enemy' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'blink', 'buff_maintenance', 'self' }, { 'stoneskin', 'buff_maintenance', 'self' }, { 'aspir', 'debuffs', 'enemy' }, { 'elemental-nuke', 'offensive_magic', 'enemy' } },
    RDM = { { 'raise', 'raise', 'dead' }, { 'emergency-cure', 'emergency_healing', 'lowest' }, { 'maintenance-cure', 'emergency_healing', 'lowest' }, { 'erase', 'status_removal', 'status' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'refresh-party', 'buff_maintenance', 'mp' }, { 'haste-party', 'buff_maintenance', 'ally' }, { 'phalanx', 'buff_maintenance', 'self' }, { 'dia', 'debuffs', 'enemy' }, { 'poison-blind', 'debuffs', 'enemy' }, { 'slow', 'debuffs', 'enemy' }, { 'paralyze', 'debuffs', 'enemy' }, { 'dispel', 'debuffs', 'enemy' }, { 'rdm-nuke', 'offensive_magic', 'enemy' } },
    THF = { { 'sneak-attack', 'critical_job_mechanics', 'self' }, { 'trick-attack', 'critical_job_mechanics', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'feint', 'buff_maintenance', 'self' }, { 'assassins-charge', 'buff_maintenance', 'self' } },
    PLD = { { 'sentinel', 'emergency_survival', 'self' }, { 'rampart', 'emergency_survival', 'self' }, { 'emergency-cure', 'emergency_healing', 'lowest' }, { 'maintenance-cure', 'emergency_healing', 'lowest' }, { 'flash', 'critical_job_mechanics', 'enemy' }, { 'provoke', 'critical_job_mechanics', 'enemy' }, { 'shield-bash', 'critical_job_mechanics', 'enemy' }, { 'chivalry', 'critical_job_mechanics', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' } },
    DRK = { { 'drain', 'emergency_healing', 'enemy' }, { 'stun', 'critical_job_mechanics', 'enemy' }, { 'weapon-bash', 'critical_job_mechanics', 'enemy' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'last-resort', 'buff_maintenance', 'self' }, { 'aspir', 'debuffs', 'enemy' } },
    BST = { { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'fight', 'job_specific_actions', 'enemy' } },
    BRD = { { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'song-slot-1', 'buff_maintenance', 'self' }, { 'song-slot-2', 'buff_maintenance', 'self' }, { 'elegy', 'debuffs', 'enemy' }, { 'requiem', 'debuffs', 'enemy' }, { 'finale', 'debuffs', 'enemy' } },
    RNG = { { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'ranged-weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'sharpshot', 'buff_maintenance', 'self' }, { 'barrage', 'buff_maintenance', 'self' }, { 'ranged-attack', 'job_specific_actions', 'enemy' } },
    SAM = { { 'blade-bash', 'critical_job_mechanics', 'enemy' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'hasso', 'buff_maintenance', 'self' }, { 'third-eye', 'buff_maintenance', 'self' }, { 'sekkanoki', 'buff_maintenance', 'self' } },
    NIN = { { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'kurayami', 'debuffs', 'enemy' }, { 'hojo', 'debuffs', 'enemy' }, { 'jubaku', 'debuffs', 'enemy' } },
    DRG = { { 'spirit-link', 'emergency_survival', 'self' }, { 'call-wyvern', 'critical_job_mechanics', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'jump', 'job_specific_actions', 'enemy' }, { 'high-jump', 'job_specific_actions', 'enemy' } },
    SMN = { { 'healing-ruby', 'emergency_healing', 'lowest' }, { 'summon-avatar', 'critical_job_mechanics', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'avatar-ward', 'buff_maintenance', 'self' }, { 'avatar-assault', 'job_specific_actions', 'enemy' }, { 'avatar-rage', 'job_specific_actions', 'enemy' } },
    BLU = { { 'blue-heal', 'emergency_healing', 'self' }, { 'head-butt', 'critical_job_mechanics', 'enemy' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'cocoon', 'buff_maintenance', 'self' }, { 'metallic-body', 'buff_maintenance', 'self' }, { 'refueling', 'buff_maintenance', 'self' }, { 'blue-physical', 'offensive_magic', 'enemy' } },
    COR = { { 'fold', 'critical_job_mechanics', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'ranged-weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'roll-slot-1', 'buff_maintenance', 'self' }, { 'roll-slot-2', 'buff_maintenance', 'self' } },
    PUP = { { 'activate', 'critical_job_mechanics', 'self' }, { 'weapon-skill', 'weapon_skill', 'enemy' }, { 'sub-berserk', 'buff_maintenance', 'self' }, { 'maneuver-1', 'buff_maintenance', 'self' }, { 'maneuver-2', 'buff_maintenance', 'self' }, { 'maneuver-3', 'buff_maintenance', 'self' }, { 'deploy', 'job_specific_actions', 'enemy' } },
}

-- Which rows a role keeps ON. The engine's rows come in layers, so a role switches whole layers: auto keeps everything.
--   tank     survival and job tools (Provoke, Flash...), weapon skills, weakening spells, its own buffs; cures only when badly hurt; no nukes
--   damage   weapon skills, job attacks, nukes, weakening spells, its own buffs; cures only when badly hurt
--   healer   cures, raise, status removal and buffs; no nukes, weapon skills or weakening spells
--   support  cures, status removal, buffs and weakening spells; no nukes
local function wanted(role, rule)
    if role == 'auto' or not ROLES[role] then return true; end
    local layer, id = rule[2], rule[1];
    if id == 'drain' then return role == 'damage'; end
    if layer == 'emergency_healing' then
        if role == 'tank' or role == 'damage' then return id ~= 'maintenance-cure'; end
        return true;
    elseif layer == 'status_removal' then
        return role == 'healer' or role == 'support';
    elseif layer == 'weapon_skill' then
        return role ~= 'healer';
    elseif layer == 'critical_job_mechanics' or layer == 'job_specific_actions' then
        return role == 'tank' or role == 'damage';
    elseif layer == 'buff_maintenance' then
        if role == 'tank' or role == 'damage' then return rule[3] == 'self'; end
        return true;
    elseif layer == 'debuffs' then
        return role ~= 'healer';
    elseif layer == 'offensive_magic' then
        return role == 'damage';
    end
    return true;   -- emergency_survival and raise stay on for every role
end


-- ---------------------------------------------------------------- acting on a monster nobody has visibly claimed
-- The engine only acts on a monster claimed by someone in the party. It has a setting for the other case (AllowUnclaimedTargets);
-- it lives in the engine's settings.lua, which the engine re-reads by itself when it changes.
-- The Gambits sheets folder: config/addons/Gambits, or the addon's earlier
-- config/addons/TitanGambits until Gambits has moved it on its next load.
local function gambitsFolder(base)
    for _, name in ipairs({ 'Gambits', 'TitanGambits' }) do
        local f = io.open(base .. 'config/addons/' .. name .. '/settings.lua', 'rb');
        if f then f:close(); return base .. 'config/addons/' .. name .. '/'; end
    end
    return base .. 'config/addons/Gambits/';
end

local function titanRoot()
    local fromProfile = S.profilePath ~= '' and S.profilePath:match('^(.*[/\\])jobs[/\\]');
    if fromProfile then return fromProfile; end
    local base = call(AshitaCore, 'GetInstallPath');
    if type(base) == 'string' then return gambitsFolder(base); end
    return nil;
end

local function readUnclaimed()                                -- true or false, or nil when the engine's settings file cannot be read
    local root = titanRoot();
    local f = root and io.open(root .. 'settings.lua', 'rb');
    if not f then return nil; end
    local text = f:read('*a');
    f:close();
    local v = text:match('AllowUnclaimedTargets%s*=%s*(%a+)');
    if v == 'true' then return true; elseif v == 'false' then return false; end
    return nil;
end

local function writeUnclaimed(on)                             -- changes that one word and nothing else
    local root = titanRoot();
    local path = root and (root .. 'settings.lua');
    local f = path and io.open(path, 'rb');
    if not f then return false; end
    local text = f:read('*a');
    f:close();
    local changed, n = text:gsub('(AllowUnclaimedTargets%s*=%s*)%a+', '%1' .. (on and 'true' or 'false'), 1);
    if n ~= 1 then return false; end
    if changed == text then return true; end
    local g = io.open(path, 'wb');
    if not g then return false; end
    g:write(changed);
    g:close();
    return true;
end

local function setUnclaimed(on)
    cfg.unclaimed = on and 'true' or 'false';
    save_cfg();
    S.lastUnclaimedCheck = -1000;                             -- look at once
end

-- Commands for the gambit engine go through a queue, a moment apart, so they never arrive all at once
local function enqueue(command)
    S.queue[#S.queue + 1] = command;
end

local function pump(t)
    if #S.queue == 0 or t - S.lastQueued < 0.35 then return; end
    S.lastQueued = t;
    send(table.remove(S.queue, 1));
end

local function applyProfile()
    local role, sheet = cfg.profile, SHEETS[S.job or ''];
    if not sheet then
        say('no preset for ' .. tostring(S.job) .. ', so the profile was not applied');
        return;
    end
    for _, rule in ipairs(sheet) do
        enqueue('/autobox ' .. (wanted(role, rule) and 'enable ' or 'disable ') .. rule[1]);
    end
    S.hideUntil = now() + #S.queue * 0.35 + 3;      -- the engine prints "Rule updated." for each; keep them out of the chat log
    say(string.format('profile %s applied to %s (%d rows)', role, S.job, #sheet));
end

local function setAuto(on)
    cfg.enabled = on and 'true' or 'false';
    save_cfg();
    enqueue('/autobox ' .. (on and 'on' or 'off'));
    S.hideUntil = now() + 3;
end

-- stop following (holding camp) or follow again. Holding also stops a /follow that is still running.
local function setHold(on)
    S.hold = on and true or false;
    if S.hold then
        pcall(function()
            local follow = AshitaCore:GetMemoryManager():GetAutoFollow();
            if follow then
                follow:SetIsAutoRunning(0);
                follow:SetFollowTargetIndex(0);
                follow:SetFollowTargetServerId(0);
            end
        end);
    end
    say(S.hold and 'holding camp: not following (follow on to follow again)' or 'following again');
end

local function setProfile(role)
    cfg.profile = role;
    save_cfg();
    S.applyAt = now();
end

-- ---------------------------------------------------------------- the files the panel talks through
local function duoDir()
    local base = call(AshitaCore, 'GetInstallPath');
    if type(base) ~= 'string' then return nil; end
    return base .. 'config/addons/duo/';
end

local function readKeyValues(path)
    local f = io.open(path, 'r');
    if not f then return nil; end
    local out = {};
    for line in f:lines() do
        local k, v = line:match('^%s*([%w_]+)%s*=%s*(.-)%s*$');
        if k then out[k] = v; end
    end
    f:close();
    return out;
end

local STATUS_ORDER = { 'time', 'version', 'name', 'job', 'level', 'sub', 'sublevel', 'hp', 'mp', 'tp', 'auto', 'profile', 'follow', 'hold', 'gate', 'last',
                       'master', 'buffs', 'actions', 'why1', 'why2', 'why3', 'rows', 'sheet', 'ack', 'sheetpath',
                       'unclaimed', 'fightat', 'fight1', 'fight2', 'fight3', 'fight4', 'fight5', 'fight6', 'fight7', 'fight8', 'fight9', 'fight10',
                       'probe1', 'probe2', 'probe3', 'probe4', 'probe5', 'probe6', 'probe7', 'probe8', 'probe9', 'probe10', 'probe11', 'probe12', 'probe13', 'probe14', 'probe15', 'probe16', 'probe17', 'probe18' };

local function writeStatus(values)
    local dir = duoDir();
    if not dir then return; end
    if ashita and ashita.fs and ashita.fs.create_directory then pcall(ashita.fs.create_directory, dir); end
    local f = io.open(dir .. 'status.cfg', 'w');
    if not f then return; end
    for _, key in ipairs(STATUS_ORDER) do
        if values[key] ~= nil then f:write(key .. '=' .. (tostring(values[key]):gsub('[\r\n]', ' ')) .. '\n'); end
    end
    f:close();
end

local function snapshot(mem)
    local party, player = mem:GetParty(), mem:GetPlayer();
    if not truth(call(party, 'GetMemberIsActive', 0)) then return nil; end
    local job = call(player, 'GetMainJob');
    if type(job) ~= 'number' or job == 0 then return nil; end
    return {
        name = call(party, 'GetMemberName', 0) or '', job = JOBS[job] or '?', level = call(player, 'GetMainJobLevel') or 0,
        sub = JOBS[call(player, 'GetSubJob') or 0] or 'NON', sublevel = call(player, 'GetSubJobLevel') or 0,
        hp = call(party, 'GetMemberHPPercent', 0) or 0, mp = call(party, 'GetMemberMPPercent', 0) or 0, tp = call(party, 'GetMemberTP', 0) or 0,
    };
end


-- ---------------------------------------------------------------- the live probe
-- Every condition the gambit engine checks before it casts a spell, read from the live game with the same calls it uses.
local function field(t, k)
    local ok, v = pcall(function() return t[k]; end);
    if ok then return v; end
    return nil;
end

local function buffIds(raw)                                  -- the ids in a buff list, read the way the engine reads it; nil when there is no usable list
    if raw == nil then return nil; end
    local ids, readable = {}, false;
    local function add(v)
        if type(v) == 'number' then
            readable = true;
            if v >= 0 and v < 1023 and v ~= 255 then ids[v] = true; end
        end
    end
    if type(raw) == 'table' then
        for _, v in pairs(raw) do add(v); end
        readable = true;                                     -- a table is a list, even an empty one
    else
        local zeroBased = false;
        for i = 0, 31 do local v = field(raw, i); if v ~= nil then zeroBased = true; add(v); end end
        if not zeroBased then
            for i = 1, 32 do local v = field(raw, i); if v ~= nil then add(v); end end
        end
    end
    return readable and ids or nil;
end

-- His own buffs, from the same places the engine looks, in the same order. Returns the ids and where they came from.
local function ownBuffs(player, party, serverId, index)
    local ids = buffIds(call(player, 'GetBuffs'));
    if ids then return ids, 'GetBuffs'; end
    local raw = call(player, 'GetRawStructure');
    ids = raw and buffIds(field(raw, 'Buffs'));
    if ids then return ids, 'raw player structure'; end
    for slot = 0, 4 do
        if call(party, 'GetStatusIconsServerId', slot) == serverId and call(party, 'GetStatusIconsTargetIndex', slot) == index then
            ids = buffIds(call(party, 'GetStatusIcons', slot));
            if ids then return ids, 'party status memory'; end
        end
    end
    ids = buffIds(call(player, 'GetStatusIcons'));
    if ids then return ids, 'GetStatusIcons'; end
    ids = raw and buffIds(field(raw, 'StatusIcons'));
    if ids then return ids, 'raw status icons'; end
    return nil, 'nothing';
end

local function probe(spellName)
    spellName = (spellName and spellName ~= '') and spellName or 'Dia';
    local out = {};
    local function add(ok, text) out[#out + 1] = (ok and 'ok: ' or 'FAIL: ') .. text; end
    local mem = AshitaCore:GetMemoryManager();
    local party, ent, player, targetMem, recast = mem:GetParty(), mem:GetEntity(), mem:GetPlayer(), mem:GetTarget(), mem:GetRecast();
    local resources = AshitaCore:GetResourceManager();
    local myIndex = call(party, 'GetMemberTargetIndex', 0);
    local t = now();

    -- the spell, looked up by name the way the engine does it
    local spell = call(resources, 'GetSpellByName', spellName, 0);
    if not spell then
        local sample = call(resources, 'GetSpellById', 23);
        local names = sample and field(sample, 'Name');
        add(false, string.format("no spell is called '%s' here (spell 23 is called '%s': names are read in the Ashita language of the boot file)", spellName, tostring(names and field(names, 1) or '?')));
    else
        add(true, string.format("'%s' found: spell %s, costs %s MP", spellName, tostring(spell.Index), tostring(spell.ManaCost)));
        add(truth(call(player, 'HasSpellData')), 'the game has received his spell list (HasSpellData)');
        add(truth(call(player, 'HasSpell', spell.Index)), 'he has learned ' .. spellName .. ' (HasSpell)');
        local main, sub = call(player, 'GetMainJob') or 0, call(player, 'GetSubJob') or 0;
        local mainLevel, subLevel = call(player, 'GetMainJobLevel') or 0, call(player, 'GetSubJobLevel') or 0;
        local required = field(spell, 'LevelRequired');
        local needMain, needSub = required and field(required, main + 1), required and field(required, sub + 1);
        local levelOk = (type(needMain) == 'number' and needMain > 0 and needMain <= mainLevel) or (sub > 0 and type(needSub) == 'number' and needSub > 0 and needSub <= subLevel);
        add(levelOk, string.format('his level allows it (main job level %s, needs %s)', tostring(mainLevel), tostring(needMain)));
        local timer = call(recast, 'GetSpellTimer', spell.Index);
        add(type(timer) == 'number' and timer == 0, 'its recast is ready (timer ' .. tostring(timer) .. ')');
        local mp, cost = call(party, 'GetMemberMP', 0), tonumber(spell.ManaCost) or 0;
        add(type(mp) == 'number' and mp >= cost, string.format('he has the MP (%s, needs %s; MP is at %s%%)', tostring(mp), tostring(cost), tostring(call(party, 'GetMemberMPPercent', 0))));
        add(math.floor((tonumber(spell.Targets) or 0) / 32) % 2 == 1, 'the spell can target an enemy');
    end

    -- his own buffs: the engine refuses every spell when it cannot read them (it cannot rule out Silence)
    local ids, source = ownBuffs(player, party, call(party, 'GetMemberServerId', 0), myIndex);
    if ids == nil then
        add(false, 'his own buffs cannot be read (no source gives them): the engine then refuses every action');
    else
        local n = 0; for _ in pairs(ids) do n = n + 1; end
        add(true, string.format('his own buffs can be read (from %s: %d active)', source, n));
        add(not (ids[6] or ids[29]), 'he is not silenced or muted');
    end

    -- is he standing still, can the game tell where he is, is he free to act
    local pos = myIndex and position(ent, myIndex);
    if not pos then
        add(false, 'his position cannot be read: the engine then thinks he is always moving');
    else
        local still = S.stillSince and (t - S.stillSince) or nil;
        add(still ~= nil and still >= 1, still and string.format('he has been standing still for %.0f seconds (the engine needs a moment)', still) or 'standing still: not measured yet, try again in a second');
    end
    add(not truth(call(AshitaCore:GetChatManager(), 'IsInputOpen')), 'the chat input line is not open');
    local status = myIndex and call(ent, 'GetStatus', myIndex);
    add(status == 0 or status == 1, 'his status allows acting (' .. tostring(status) .. ': 0 idle, 1 engaged)');

    -- the target: the client's current target, a monster, claimed by someone in the party
    local ti = call(targetMem, 'GetTargetIndex', 0) or 0;
    if ti == 0 then
        add(false, 'he has no target selected (the engine only acts on the client\'s current target)');
    else
        local flags, hpp, name = call(ent, 'GetSpawnFlags', ti), call(ent, 'GetHPPercent', ti), call(ent, 'GetName', ti);
        add(type(flags) == 'number' and math.floor(flags / 16) % 2 == 1 and (hpp or 0) > 0, string.format("his target '%s' is a living monster (HP %s%%)", tostring(name), tostring(hpp)));
        local claim = call(ent, 'GetClaimStatus', ti) or 0;
        local claimant;
        for i = 0, 17 do
            if truth(call(party, 'GetMemberIsActive', i)) and claim ~= 0 and call(party, 'GetMemberServerId', i) == claim then claimant = call(party, 'GetMemberName', i); end
        end
        local tstatus = call(ent, 'GetStatus', ti);
        local ids = {};
        for i = 0, 17 do
            if truth(call(party, 'GetMemberIsActive', i)) then ids[#ids + 1] = tostring(call(party, 'GetMemberServerId', i)); end
        end
        if claimant then
            add(true, 'the target is claimed by ' .. tostring(claimant) .. ', who is in his party');
        elseif claim ~= 0 then
            add(false, 'the target is claimed by someone who is not in his party (claim ' .. tostring(claim) .. '; party ids ' .. table.concat(ids, ', ') .. '): the engine never acts on a monster someone else has claimed, whatever the unclaimed setting is');
        elseif S.unclaimed == 'on' then
            local fighting = status == 1 or tstatus == 1;
            add(fighting, "the target is not claimed, but 'cast on unclaimed targets' is ON" .. (fighting and ' and he is engaged, so the engine will act' or ', and he is not engaged yet and the monster is not fighting: engage it first'));
        else
            add(false, 'the target is not claimed by anyone yet: hit it first, then he can act (or turn on cast on unclaimed targets)');
        end

        local target = position(ent, ti);
        if pos and target then
            local d = math.sqrt((pos.x - target.x) ^ 2 + (pos.y - target.y) ^ 2 + (pos.z - target.z) ^ 2);
            add(d <= 20, string.format('the target is %.1f yalms away (spells reach about 20)', d));
        end
    end

    local first;
    for _, line in ipairs(out) do if line:sub(1, 5) == 'FAIL:' then first = line; break; end end
    out[#out + 1] = first and ('=> first problem: ' .. first:sub(7)) or '=> every check passed: the engine should be able to cast it right now';
    return out;
end

-- ---------------------------------------------------------------- a snapshot taken during every fight
-- A fight can be over in two seconds, long before anyone can press a button. While he is engaged with a target, the probe runs
-- several times a second and the engine is asked for its state right away; the last snapshot stays until the next fight.
local function watchFight(t)
    if t - S.lastFightProbe < 0.4 then return; end
    S.lastFightProbe = t;
    local mem = AshitaCore:GetMemoryManager();
    if mem == nil then return; end
    local party, ent, targetMem = mem:GetParty(), mem:GetEntity(), mem:GetTarget();
    local me = call(party, 'GetMemberTargetIndex', 0);
    local status = me and call(ent, 'GetStatus', me);
    S.engaged = status == 1;
    if status ~= 1 then S.engagedSince = nil; return; end
    if (call(targetMem, 'GetTargetIndex', 0) or 0) == 0 then return; end          -- engaged but nothing selected: nothing to learn
    if not S.engagedSince then
        S.engagedSince = t;
        S.fight = { gate = '', last = '', why = {}, probe = {}, seconds = 0, at = os.time() };
        S.lastFightAsk = -1000;
    end
    S.fight.probe = probe('Dia');
    S.fight.seconds = t - S.engagedSince;
    S.fight.at = os.time();
    if flag('fight_ask') and flag('enabled') and S.titanSeen and t - S.engagedSince >= num('fight_ask_after') and t - S.lastFightAsk >= 6
        and #S.queue == 0 and t >= S.userUntil then
        S.lastFightAsk, S.lastStatusAsk, S.lastOwnAsk = t, t, t;
        S.statusUntil, S.whyUntil = t + 3, t + 4;
        enqueue('/autobox status');
        enqueue('/autobox why');
    end
end

-- The snapshot as a few lines for the panel: how long, the verdict, each failed check, then what the engine itself said
local function fightLines()
    local f = S.fight;
    if not f then return {}; end
    local lines = { string.format('he was engaged for about %.0f seconds; this is what was true during it:', f.seconds) };
    local last = f.probe[#f.probe];
    if last then lines[#lines + 1] = last; end
    local shown = 0;
    for _, line in ipairs(f.probe) do
        if line:sub(1, 5) == 'FAIL:' and shown < 4 then lines[#lines + 1] = line; shown = shown + 1; end
    end
    if f.gate ~= '' then lines[#lines + 1] = 'the engine said: ' .. f.gate .. ((f.last ~= '') and ('   |   last: ' .. f.last) or ''); end
    for _, reason in ipairs(f.why) do lines[#lines + 1] = 'not firing: ' .. reason; end
    return lines;
end

local function resetSheet()
    enqueue('/autobox reset confirm');
    S.hideUntil = now() + 8;
    S.applyAt = now() + 3;                              -- then the chosen profile goes back on top
    say('his rows for ' .. tostring(S.job) .. ' are being reset to the normal sheet');
end

-- What is saved for his current job: how many rows, and are they the normal ones? (the engine tells us the file's path)
-- The maintenance-cure row's MinMissingHP, lowered to cure_min_missing when it is higher. Only the number in that one row changes.
local function tuneCures(text)
    local want = num('cure_min_missing');
    if not want or want < 0 then return text, 0; end
    local changed = 0;
    local at = text:find('Id = "maintenance%-cure",');
    while at do
        local stop = text:find('}', at, true) or #text;                 -- the end of that row (the engine writes keys A-Z: Id, Label, Layer, MinMissingHP...)
        local s, e, value = text:find('MinMissingHP = (%d+),', at);
        if s and s < stop and tonumber(value) > want then
            text = text:sub(1, s - 1) .. 'MinMissingHP = ' .. math.floor(want) .. ',' .. text:sub(e + 1);
            changed = changed + 1;
        end
        at = text:find('Id = "maintenance%-cure",', at + 1);
    end
    return text, changed;
end

local function inspectSheet(t)
    S.lastSheetRead = t;
    local f = S.profilePath ~= '' and io.open(S.profilePath, 'r');
    if not f then S.rows, S.sheet = nil, ''; return; end
    local text = f:read('*a');
    f:close();
    local tuned, changed = tuneCures(text);
    if changed > 0 then
        local g = io.open(S.profilePath, 'w');
        if g then
            g:write(tuned);
            g:close();
            text = tuned;
            enqueue('/autobox reload');
            S.hideUntil = now() + 4;
            say('his everyday cure now starts when anyone is missing ' .. cfg.cure_min_missing .. ' HP (it was 40, too much for a low level party)');
        end
    end
    local ids, n = {}, 0;
    for id in text:gmatch('Id = "([^"]*)"') do ids[id] = true; n = n + 1; end
    S.rows = n;
    local normal = SHEETS[S.job or ''];
    if text:find('[\128-\255]') then
        S.sheet = 'japanese';                          -- an action picked while the game's addon language was Japanese: it can not be found by name
    elseif normal and n == #normal then
        S.sheet = 'normal';
        for _, rule in ipairs(normal) do if not ids[rule[1]] then S.sheet = 'custom'; end end
    else
        S.sheet = 'custom';
    end
end

-- Single rows, from the menu: enable:<id>, disable:<id>, move:<from>:<to>, titanui (the engine's own window on/off). Ids are the engine's own
-- (letters, digits, - and _ only), so nothing else can reach the chat line.
local function rowCommand(kind, a, b)
    if (kind == 'enable' or kind == 'disable') and a and a:match('^[%w%-_]+$') then
        enqueue('/autobox ' .. kind .. ' ' .. a);
        return true;
    elseif kind == 'move' and tonumber(a) and tonumber(b) then
        enqueue(string.format('/autobox move %d %d', math.floor(tonumber(a)), math.floor(tonumber(b))));
        return true;
    end
    return false;
end

local function runOps(text)
    local n = 0;
    for op in tostring(text):gmatch('[^,]+') do
        local kind, a, b = op:match('^%s*(%a+):?([^:]*):?([^:]*)%s*$');
        if kind == 'titanui' then
            enqueue('/autobox ui');
            n = n + 1;
        elseif kind and rowCommand(kind, a ~= '' and a or nil, b ~= '' and b or nil) then
            n = n + 1;
        end
    end
    if n > 0 then
        S.hideUntil = now() + #S.queue * 0.35 + 3;     -- "Rule updated." / "Priority updated." stay out of the chat log
        S.lastSheetRead = -1000;
    end
    return n;
end

local function pollCommand()
    local dir = duoDir();
    local c = dir and readKeyValues(dir .. 'command.cfg');
    local seq = c and tonumber(c.seq);
    if S.lastSeq == nil then S.lastSeq = seq or 0; return; end   -- a command that was waiting when this window started is old news (no file: nothing was waiting)
    if not seq or seq == S.lastSeq then return; end
    S.lastSeq = seq;
    if c.auto == 'on' or c.auto == 'off' then setAuto(c.auto == 'on'); end
    if (c.follow == 'on' and S.hold) or (c.follow == 'off' and not S.hold) then setHold(c.follow == 'off'); end
    if c.profile and ROLES[c.profile] then setProfile(c.profile); end
    if c.reset == '1' then resetSheet(); end
    if c.unclaimed == 'on' or c.unclaimed == 'off' then setUnclaimed(c.unclaimed == 'on'); end
    if c.probe and c.probe ~= '' then S.probe = probe(c.probe); end
    if c.ops and c.ops ~= '' then runOps(c.ops); end
end

-- Once a second: apply what is waiting, answer the panel, and keep the status file current
local function housekeeping(t)
    local mem = AshitaCore:GetMemoryManager();
    if mem == nil then return; end
    pollCommand();
    local snap = snapshot(mem);
    if snap then
        if snap.job ~= S.job then                              -- first sight of the character, or he changed job
            local first = S.job == nil;
            S.job = snap.job;
            if cfg.profile ~= 'auto' or not first then S.applyAt = t + 8; end
        end
        if S.applyAt and t >= S.applyAt then
            S.applyAt = nil;
            applyProfile();
        end
        if flag('enabled') and (S.titanSeen or not S.askedOnce) and t - S.lastStatusAsk >= num('poll_every') and #S.queue == 0 and t >= S.userUntil
            and not S.engaged and t - S.leaderFoughtAt > 15 then
            S.lastStatusAsk, S.askedOnce = t, true;
            S.statusUntil = t + 3;
            S.whyUntil = t + 4;
            S.lastOwnAsk = t;
            enqueue('/autobox status');
            enqueue('/autobox why');                       -- the engine's reason for each row that did not fire
        end
        if t - S.lastSheetRead >= 10 then inspectSheet(t); end
        if t - S.lastUnclaimedCheck >= 10 then
            S.lastUnclaimedCheck = t;
            local actual, want = readUnclaimed(), flag('unclaimed');
            if actual ~= nil and actual ~= want and writeUnclaimed(want) then actual = readUnclaimed(); end
            S.unclaimed = (actual == nil) and '?' or (actual and 'on' or 'off');
        end
        local myIndex = call(mem:GetParty(), 'GetMemberTargetIndex', 0);
        local here = myIndex and position(mem:GetEntity(), myIndex);
        if here and (not S.lastPos or math.abs(here.x - S.lastPos.x) + math.abs(here.y - S.lastPos.y) + math.abs(here.z - S.lastPos.z) > 0.2) then
            S.lastPos, S.stillSince = here, t;
        end
        local fl = fightLines();
        writeStatus({ time = os.time(), version = addon.version, name = snap.name, job = snap.job, level = snap.level, sub = snap.sub,
                      sublevel = snap.sublevel, hp = snap.hp, mp = snap.mp, tp = snap.tp, auto = flag('enabled') and 'on' or 'off', hold = S.hold and 1 or 0,
                      profile = cfg.profile, follow = S.reason, gate = S.gate, last = S.last, master = S.master, buffs = S.buffs, actions = S.actions,
                      why1 = S.why[1], why2 = S.why[2], why3 = S.why[3], rows = S.rows, sheet = S.sheet, ack = S.lastSeq, sheetpath = S.profilePath, unclaimed = S.unclaimed, fightat = S.fight and S.fight.at,
                      fight1 = fl[1], fight2 = fl[2], fight3 = fl[3], fight4 = fl[4], fight5 = fl[5], fight6 = fl[6], fight7 = fl[7], fight8 = fl[8], fight9 = fl[9], fight10 = fl[10],
                      probe1 = S.probe and S.probe[1], probe2 = S.probe and S.probe[2], probe3 = S.probe and S.probe[3], probe4 = S.probe and S.probe[4],
                      probe5 = S.probe and S.probe[5], probe6 = S.probe and S.probe[6], probe7 = S.probe and S.probe[7], probe8 = S.probe and S.probe[8],
                      probe9 = S.probe and S.probe[9], probe10 = S.probe and S.probe[10], probe11 = S.probe and S.probe[11], probe12 = S.probe and S.probe[12],
                      probe13 = S.probe and S.probe[13], probe14 = S.probe and S.probe[14], probe15 = S.probe and S.probe[15], probe16 = S.probe and S.probe[16],
                      probe17 = S.probe and S.probe[17], probe18 = S.probe and S.probe[18] });
    end
end

-- Fighting alongside the leader. Returns a reason when it sent a command this second, otherwise nil.
local function fight(t, mem, ent, myIndex, myStatus, leaderIndex)
    if not flag('assist') then return nil; end
    local leaderStatus = call(ent, 'GetStatus', leaderIndex);
    local foe = nil;
    if leaderStatus == 1 then
        local candidate = call(ent, 'GetTargetedIndex', leaderIndex);
        if type(candidate) == 'number' and candidate > 0 and is_monster(ent, candidate) and is_alive(ent, candidate) then foe = candidate; end
    end

    if foe then
        S.leaderFoughtAt = t;
        local myTarget = call(mem:GetTarget(), 'GetTargetIndex', 0) or 0;
        if myTarget ~= foe then
            if t - S.lastAssist < num('assist_every') then return nil; end
            S.lastAssist = t;
            S.assists = S.assists + 1;
            send('/assist ' .. cfg.leader);
            return 'sent /assist ' .. cfg.leader;
        end
        if flag('engage') and myStatus ~= 1 then
            local mine, theirs = position(ent, myIndex), position(ent, foe);
            local dist = (mine and theirs) and math.sqrt((mine.x - theirs.x) ^ 2 + (mine.y - theirs.y) ^ 2 + (mine.z - theirs.z) ^ 2) or nil;
            if dist and dist <= num('engage_range') and t - S.lastAttack >= num('attack_every') then
                S.lastAttack = t;
                S.attacks = S.attacks + 1;
                send('/attack <t>');
                return string.format('sent /attack (%.0f yalms from the enemy)', dist);
            end
        end
        return nil;
    end

    -- the leader is not fighting: stop fighting too, after a short delay
    if flag('engage') and myStatus == 1 and t - S.leaderFoughtAt > num('disengage_delay') and t - S.lastOff >= 5 then
        S.lastOff = t;
        send('/attack off');
        return 'sent /attack off (the leader stopped fighting)';
    end
    return nil;
end

-- Pausing the gambit engine is the only thing that keeps a cure or a buff from
-- standing him up mid-rest. A pause nobody lifts is also how he stops healing:
-- /autobox pause 3600 outlives a reload, a zone, or a leader who never gets up.
-- So the pause is held in short slices instead of one long one: if the resume is
-- ever lost, the engine turns itself back on within half a minute.
local GAMBIT_PAUSE_SECONDS = 30;
local GAMBIT_PAUSE_REFRESH = 15;

local function holdGambitsPaused(t)
    if S.restPauseAt and (t - S.restPauseAt) < GAMBIT_PAUSE_REFRESH then return; end
    S.restPauseAt = t;
    S.restPaused = true;
    enqueue('/autobox pause ' .. GAMBIT_PAUSE_SECONDS);
    S.hideUntil = now() + 3;
end

local function decide(t)
    if not flag('enabled') then return 'off'; end
    if cfg.leader == nil or cfg.leader == '' then return 'no leader set (use /fm leader <Name>)'; end
    local mem = AshitaCore:GetMemoryManager();
    if mem == nil then return 'game data not ready'; end
    local party, ent, player = mem:GetParty(), mem:GetEntity(), mem:GetPlayer();
    if party == nil or ent == nil then return 'game data not ready'; end

    if not truth(call(party, 'GetMemberIsActive', 0)) then return 'not in the world yet'; end
    local myIndex, myZone = call(party, 'GetMemberTargetIndex', 0), call(party, 'GetMemberZone', 0);
    if not myIndex or myIndex == 0 or not myZone or myZone == 0 then return 'not in the world yet'; end

    if truth(call(player, 'GetIsZoning')) then S.settleUntil = t + num('settle'); return 'zoning'; end
    if myZone ~= S.zone then
        if S.hold and S.zone ~= 0 then S.hold = false; say('zoned: following again'); end
        S.zone = myZone; S.settleUntil = t + num('settle');
    end
    if t < S.settleUntil then return 'settling after zoning'; end

    -- find the leader in the party
    local want, slot, leaderIndex, leaderZone = cfg.leader:lower(), nil, nil, nil;
    for i = 0, 17 do
        if truth(call(party, 'GetMemberIsActive', i)) then
            local name = call(party, 'GetMemberName', i);
            if type(name) == 'string' and name:lower() == want then
                slot, leaderIndex, leaderZone = i, call(party, 'GetMemberTargetIndex', i), call(party, 'GetMemberZone', i);
                break;
            end
        end
    end
    if not slot then return 'leader is not in my party'; end
    if slot == 0 then return 'I am the leader'; end
    if leaderZone ~= myZone then return 'leader is in another zone'; end

    local status = call(ent, 'GetStatus', myIndex);

    -- rest when the leader rests, get up when the leader gets up (33 = resting)
    if flag('rest_with_leader') then
        local leaderStatus = call(ent, 'GetStatus', leaderIndex);
        if leaderStatus == 33 then
            S.sawLeaderRest = true;
            if status == 33 then
                holdGambitsPaused(t);
                return 'resting with the leader';
            end
            if status == 0 then
                if S.restTries < 3 and t - S.lastRest >= 6 then
                    S.lastRest, S.restTries, S.restedByUs = t, S.restTries + 1, true;
                    holdGambitsPaused(t);
                    send('/heal on');
                    return 'the leader is resting: sent /heal on';
                end
                return 'the leader is resting';
            end
        else
            S.restTries = 0;
            if status == 33 and S.restedByUs then
                if t - S.lastRest >= 3 then
                    S.lastRest = t;
                    send('/heal off');
                end
                return 'the leader got up: getting up';
            end
            if status ~= 33 then S.restedByUs = false; end
            if S.restPaused and status ~= 33 then
                S.restPaused, S.restPauseAt = false, nil;
                enqueue('/autobox resume');
                S.hideUntil = now() + 3;
            end
        end
    end

    -- leave a rest, a death or an event alone (idle and engaged are fine)
    if type(status) == 'number' and status ~= 0 and status ~= 1 then
        return 'busy (status ' .. tostring(status) .. ')';
    end

    -- fight what the leader fights
    local acted = fight(t, mem, ent, myIndex, status, leaderIndex);
    if acted then return acted; end
    if status == 1 and flag('pause_engaged') then return 'engaged (pause_engaged is on)'; end
    if S.hold then return 'holding camp (not following)'; end

    local mine, theirs = position(ent, myIndex), position(ent, leaderIndex);
    if not mine or not theirs then return 'positions not available'; end
    local dist = math.sqrt((mine.x - theirs.x) ^ 2 + (mine.y - theirs.y) ^ 2 + (mine.z - theirs.z) ^ 2);
    if dist <= num('distance') then return string.format('close enough (%.1f yalms)', dist); end
    -- standing and fighting: the gambit engine will not act on a character who is running, so he stays put while the leader is near
    if status == 1 and not flag('follow_engaged') and dist <= num('engaged_range') then
        return string.format('engaged, holding still (%.1f yalms from the leader)', dist);
    end
    if dist > num('maxrange') then return string.format('too far for /follow (%.0f yalms)', dist); end
    if t - S.lastSend < num('recheck') then return 'waiting between /follow commands'; end

    S.lastSend = t;
    S.sent = S.sent + 1;
    send('/follow ' .. cfg.leader);
    return string.format('sent /follow %s (%.1f yalms away)', cfg.leader, dist);
end

local function tick(t)
    S.sawLeaderRest = false;
    local reason = decide(t);
    S.reason = reason;
    -- the gambit engine was paused for a rest that is over in some other way (leader zoned, left, ...): resume it
    if S.restPaused and not S.sawLeaderRest then
        local mem = AshitaCore:GetMemoryManager();
        local me = mem and call(mem:GetParty(), 'GetMemberTargetIndex', 0);
        if not me or call(mem:GetEntity(), 'GetStatus', me) ~= 33 then
            S.restPaused, S.restedByUs, S.restPauseAt = false, false, nil;
            enqueue('/autobox resume');
            S.hideUntil = now() + 3;
        end
    end
    housekeeping(t);
    if S.debug and reason ~= S.lastPrinted then
        S.lastPrinted = reason;
        say(reason);
    end
end

-- ---------------------------------------------------------------- events
ashita.events.register('load', 'followme_load', function ()
    load_cfg();
    say(string.format('loaded. Following "%s" (%s). /fm status for details.', cfg.leader ~= '' and cfg.leader or 'nobody yet', flag('enabled') and 'on' or 'off'));
end);

ashita.events.register('d3d_present', 'followme_present', function ()
    local t = now();
    pump(t);
    pcall(watchFight, t);
    if t - S.lastTick < 1.0 then return; end
    S.lastTick = t;
    local ok, err = pcall(tick, t);
    if not ok then S.reason = 'error: ' .. tostring(err); end
end);

ashita.events.register('text_in', 'followme_text_in', function (e)
    if e.blocked then return; end
    local text = tostring(e.message_modified or e.message or ''):gsub('%z', ''):gsub('[\30\31].', '');
    local rest = text:match('%[Gambits%]%s*(.*)$') or text:match('%[Titan Gambits%]%s*(.*)$');
    if not rest then return; end
    S.titanSeen = true;
    local t = now();
    local hide = false;

    -- /autobox status: master switch, state and last attempt, where the status comes from, the job file, and the action counts
    local master = rest:match('Gambits (%u+) %| Job');
    if master then S.master = master; hide = true; end
    local state, last = rest:match('^State: (.-) %| Last attempt: (.*)$');
    if state then
        S.gate, S.last, hide = state, last, true;
        if S.engagedSince and S.fight then S.fight.gate, S.fight.last = state, last; end
    end
    local source = rest:match('^Status source: (.-) %|') or rest:match('^Status source: (.*)$');
    if source then S.buffs, hide = source, true; end
    local path = rest:match('^Profile: (.+)$');
    if path then S.profilePath, hide = path, true; end
    local a1, a2, a3, a4, a5, a6 = rest:match('^Actions this session: submitted (%d+), outgoing observed (%d+), server accepted (%d+), rejected (%d+), completed (%d+), uncertain (%d+)');
    if a1 then S.actions, hide = string.format('submitted %s, accepted %s, rejected %s, completed %s', a1, a3, a4, a5), true; end
    if rest:find('^Status probes: ') then hide = true; end
    hide = hide and t < S.statusUntil and t >= S.userUntil;

    -- /autobox why: the gate, then one reason per row that did not fire
    if t < S.whyUntil and t >= S.userUntil then
        if rest:find('^Gate: ') then
            S.whyNew = {};
            S.why = S.whyNew;
            if S.engagedSince and S.fight then S.fight.why = S.whyNew; end
            hide = true;
        else
            local id, reason = rest:match('^([%w%-_]+): (.+)$');
            if id and id ~= 'State' and id ~= 'Gate' and id ~= 'Profile' then
                if #S.whyNew < 3 then S.whyNew[#S.whyNew + 1] = id .. ': ' .. reason:sub(1, 90); end
                hide = true;
            elseif rest:find('^Showing %d+%-%d+ of %d+') then
                hide = true;
            end
        end
    end
    if hide then e.blocked = true; return; end

    -- "Rule updated." while a profile is being applied
    if t < S.hideUntil and (rest:find('Rule updated.', 1, true) or rest:find('Priority updated.', 1, true) or rest:find('Rule not found', 1, true) or rest:find('profile reset', 1, true)
        or rest:find('Current job preset reset', 1, true) or rest:find('Configuration reloaded.', 1, true) or rest == 'Paused.' or rest == 'Pause cleared.') then
        e.blocked = true;
    end
end);

ashita.events.register('command', 'followme_command', function (e)
    -- a /autobox status or /autobox why typed by the person (ours are sent a moment after we record them): show them the answer
    local typed = tostring(e.command or ''):lower():gsub('^%s+', '');
    if typed:find('^/autobox%s+status') or typed:find('^/autobox%s+why') then
        local ours = typed == S.lastSentCmd and now() - S.lastSentAt < 1.5;      -- the command we sent a moment ago, coming back through the same event
        if not ours then S.userUntil = now() + 4; end
    end
    local args = e.command:args();
    if #args == 0 then return; end
    local first = args[1]:lower();
    if first ~= '/followme' and first ~= '/fm' then return; end
    e.blocked = true;

    local sub = (args[2] or 'status'):lower();
    if sub == 'on' or sub == 'off' then
        cfg.enabled = (sub == 'on') and 'true' or 'false';
        save_cfg();
        say('following is now ' .. sub);
    elseif sub == 'leader' and args[3] then
        cfg.leader = args[3];
        S.lastSend = -1000;
        save_cfg();
        say('leader is now ' .. cfg.leader);
    elseif sub == 'distance' and tonumber(args[3]) then
        cfg.distance = tostring(tonumber(args[3]));
        save_cfg();
        say('will send /follow when farther than ' .. cfg.distance .. ' yalms');
    elseif sub == 'unclaimed' and (args[3] == 'on' or args[3] == 'off') then
        setUnclaimed(args[3] == 'on');
        say('casting on unclaimed targets is now ' .. args[3] .. ' (set in the gambit engine\'s settings within ten seconds)');
    elseif sub == 'probe' then
        local name = table.concat(args, ' ', 3);
        S.probe = probe(name);
        for _, line in ipairs(S.probe) do say(line); end
    elseif sub == 'reset' then
        resetSheet();
    elseif sub == 'row' and args[3] and (args[4] == 'on' or args[4] == 'off') then
        if rowCommand(args[4] == 'on' and 'enable' or 'disable', args[3]) then say('row ' .. args[3] .. ' ' .. args[4]); else say('that is not a row id'); end
    elseif sub == 'move' and tonumber(args[3]) and tonumber(args[4]) then
        rowCommand('move', args[3], args[4]);
        say('moving row ' .. args[3] .. ' to ' .. args[4]);
    elseif sub == 'follow' and (args[3] == 'on' or args[3] == 'off') then
        setHold(args[3] == 'off');
    elseif sub == 'auto' and (args[3] == 'on' or args[3] == 'off') then
        setAuto(args[3] == 'on');
        say('auto is now ' .. args[3] .. ' (following, assisting, attacking, and the gambit master switch)');
    elseif sub == 'profile' and args[3] and ROLES[args[3]:lower()] then
        setProfile(args[3]:lower());
        say('profile is now ' .. cfg.profile .. ' (applied in a moment to ' .. tostring(S.job) .. ')');
    elseif (sub == 'assist' or sub == 'engage') and (args[3] == 'on' or args[3] == 'off') then
        cfg[sub] = (args[3] == 'on') and 'true' or 'false';
        save_cfg();
        say(sub .. ' is now ' .. args[3]);
    elseif sub == 'debug' then
        S.debug = not S.debug;
        S.lastPrinted = '';
        say('debug messages ' .. (S.debug and 'on' or 'off'));
    elseif sub == 'status' then
        say(string.format('%s | leader "%s" | distance %s | assist %s | engage %s', flag('enabled') and 'ON' or 'OFF', cfg.leader, cfg.distance, flag('assist') and 'on' or 'off', flag('engage') and 'on' or 'off'));
        say(string.format('sent so far: /follow %d, /assist %d, /attack %d', S.sent, S.assists, S.attacks));
        say(string.format('profile %s | job %s | gambits: %s %s', cfg.profile, tostring(S.job), S.master ~= '' and S.master or '?', S.gate ~= '' and S.gate or 'not asked yet'));
        say(string.format('rows: %s (%s) | status data: %s | %s', tostring(S.rows or '?'), S.sheet ~= '' and S.sheet or 'not read yet', S.buffs ~= '' and S.buffs or '?', S.actions ~= '' and S.actions or 'no action counts yet'));
        for _, line in ipairs(S.why) do say('why not: ' .. line); end
        say('right now: ' .. tostring(S.reason));
    else
        say('commands: /fm on | off | auto on|off | profile <auto|tank|damage|healer|support> | probe [spell] | unclaimed on|off | reset | row <id> on|off | move <from> <to> | leader <Name> | distance <n> | assist on|off | engage on|off | status | debug');
    end
end);
