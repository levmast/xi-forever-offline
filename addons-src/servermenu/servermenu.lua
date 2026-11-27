--[[
servermenu 1.6
One menu for XI: Forever Offline, opened from a small Squads button on the screen. It replaces the Squad panel (/sq still works).

  Squad        your squad mates: call, dismiss, role, mode, main and support job, and a Profile button per mate with
               their current stats, HP/MP/TP, haste, jobs and equipped items (the Titan-style profile screen);
               the Camp row (1.6): set camp, camp off, who pulls (you or a mate), pause/resume pulls
               (1.7) setting a camp tells the second window to stop following (followme 1.2), camp off to follow again
               (1.8) Pull: pick which kind of monster around the camp a mate puller goes for (or anything)
               (1.36) the Ventures button: loads the venture add-on when it is not loaded (it is not started with the
               game) and shows its window, the XIFO app's Ventures screen; lit while that window is shown
  Dualbox      your second character: AUTO on/off, job profile, HP/MP, what he is doing, and his Gambits section
               (the gambit rows, on/off, order and reset are his, not your squad's)
  Diagnostics  hidden from the tab row; /menu diagnostics still opens it when support asks for it

  The Squads button     click: open or close the menu. Drag it to move it. Right-click: lock it in place, or hide it.
  /menu              open or close the menu (also /smenu)
  /menu button       show the button again after hiding it      /menu resetbutton   put it back in its first place
  /menu scale <n>    size of our windows (0.75-3, 1 = normal; for 4K screens)
  /menu opacity <10-100>        how see-through the Squads button is (also on its right-click menu; solid under the mouse)
  /menu opacity menu <10-100>   how see-through the menu's background is
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
addon.version = '1.37';   -- (1.37) a card's Settings has Rest in fights (below an MP %, the mate may sit out a fight and rest: !squad restfight, cap restfight), the Camp row has Pull range (!squad camp range, the server's value: camprange), the compact Camp bar keeps one width at the menu's Size so its buttons stay put, Healer MP's tip names you as a White Mage healer; (1.36) the Squad tab has a Ventures button: it loads the venture add-on (the XIFO app's Ventures screen as a window; the launcher copies it but does not start it with the game), shows its window and shuts it again; (1.35) a card's Settings has Position (Normal, Behind enemy, TA partner: where the mate stands in a fight, !squad position), when the server offers it (cap matepos); it takes effect at once; (1.34) every window's text drawn at its Size (the font pushed at the scaled size, as the Gambits window does: sharper at 120 %), themed scrollbars, the launcher's Gambits half opens AND closes the editor and is lit while it is shown, Options > Show Gambits shortcut, the Camp row's groups wrap whole and the monster kinds wrap under Anything; (1.33) the Camp row shows what the camp is doing (Ready, Pulling, Fighting, Paused), "Next pull at" an enemy HP % and "Healer MP" (squad.lua campst), Move camp here keeps the puller and Start / Pause (cap campmove), and an optional compact Camp bar (state, Start / Pause, Move here, Camp off) that follows the server's changes; (1.32) the menu's opacity reaches the cards and panels too, and no layer is laid over another; a theme picked here or in Gambits is in both windows at their next frame; (1.31) the launcher is as high as the menu's buttons, with one outline around both halves, and has the character's theme from its first frame; Sub stands in the second column, where Mode and WS at stand; (1.30) a card's Settings in two columns under a thin line, "Save size"; the Profile's Stats in groups (Role / Mode / Race, Actions, Attributes, Combat; numbers end in line; "Live stats" only when they are read from the mate that is out); the launcher is one control with a Squads half and a Gambits half, and is there only while the character is in the world; (1.29) Jobs is a button of its own on the card again (Job and Sub; the unlocked-job help is their tooltip), Settings keeps its name with a mark for open / closed, one call status at a time (Away, Calling..., Out) with Call and Dismiss in one place, the Rules line says what is expected while a mate is called, Engage is a plain button, the Gear rows are really drawn as one strip in the game (Ashita's cursor position is two numbers); (1.28) one look with the Gambits window: ImGui's own title bar and close button, the same tabs (a smaller kind for choices inside a view), row states and spacing; the commands in groups (Squad, Fight, Camp, Setup) and a clearer Engage button; compact mate cards with the same first row on every card and the rarely changed settings behind Settings; "rules skipped"; the Profile begins with the mate row, its Gear view has clickable slot rows in three groups; (1.27) themes (Classic, Squad, Crimson; Crimson for a new installation, an existing one keeps its look) shared with Gambits per character, Options row (Theme, Size, Opacity), a top row and cards that fit their content, Apply for one mate, the Profile's Stats and Gear views, tooltips that never read a % as a format; (1.26n) the Rules line: the rules a called mate really runs (Gambits Rule Set or default job rules), the selected set and Apply needed; (1.26m) each job's level in the Job and Sub lists (Dugahst); (1.26l) Spells and abilities window on the profile (Frost); (1.26k) the Auto-equip tip names "Squad gets all gear"; (1.26j) Attack my target / Stop; (1.26i) the menu opens again (opacity helper stood below the menu); (1.26h) a click right after a refresh is no longer dropped by the game; (1.26g) opacity, one gear button
addon.desc    = 'The XI: Forever Offline menu: squad mates, and the dualbox character with his gambits.';
addon.link    = '';

require('common');

local imgui;
do
    local ok, mod = pcall(require, 'imgui');
    if ok then imgui = mod; end
end

-- (1.27) xifo_ui.lua, next to this file: the palettes, the text helpers that never format, and the character's shared
-- theme choice (the same file is in the Gambits folder). Tried as a module first, then by this add-on's own folder,
-- then by the folder this file was loaded from.
local U;
do
    local ok, mod = pcall(require, 'xifo_ui');
    local tried = {};
    if not (ok and type(mod) == 'table') then
        local base = (type(addon) == 'table' and type(addon.path) == 'string') and addon.path or '';
        if base ~= '' and not base:match('[/\\]$') then base = base .. '/'; end
        local here = (debug and debug.getinfo and (debug.getinfo(1, 'S').source or '') or ''):match('^@(.*[/\\])') or '';
        for _, dir in ipairs({ base, here }) do
            if not (ok and type(mod) == 'table') and not tried[dir] then
                tried[dir] = true;
                ok, mod = pcall(dofile, dir .. 'xifo_ui.lua');
            end
        end
    end
    if not (ok and type(mod) == 'table') then error('servermenu: xifo_ui.lua could not be loaded: ' .. tostring(mod)); end
    U = mod;
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
local JOBS  = { 'WAR', 'MNK', 'WHM', 'BLM', 'RDM', 'THF', 'PLD', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'SMN', 'BLU', 'COR', 'PUP', 'DNC', 'SCH' };

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

-- (role clarity) what a squad mate's Role really does, from the server's squad.lua behaviorFilter / ROLE_KEEPS /
-- EMERGENCY_HP (tank 40, damage 30) and MODE_HEAL_SHIFT (+15 / -15, kept between 15 and 90). Text only: the server
-- decides. One table (ROLE_INFO) to keep this file's count of locals down.
local ROLE_HELP = {
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
};
local MODE_HELP = {
    balanced   = 'Balanced: the normal pace, nothing changed.',
    aggressive = 'Aggressive: cures at 15% more HP (at most 90%), also on top of a Tank or Damage limit; '
        .. 'holds no MP back.',
    conserve   = 'Conserve: cures at 15% less HP (at least 15%) and keeps 40% MP before buffs, debuffs, nukes and '
        .. 'status removal.',
};
local ROLE_INFO = {
    FOOTER = 'The Squad Role changes only the mate\'s default job rules, from its next call (Apply now). '
        .. 'A Gambits Rule Set replaces those rules and is not filtered by the Role. '
        .. 'Not the same as the Gambits party roles (Tank / Melee / Mage / Ranged).',
    TIPS = {},
    -- the Dualbox tab's profile buttons are the second character's gambit profiles (followme), not a squad Role
    DUO = {
        auto    = 'the job\'s normal behaviour',
        tank    = 'Provoke, Flash, own buffs; heals only the badly hurt',
        damage  = 'attacks and nukes; heals only the badly hurt',
        healer  = 'cures, status removal, party buffs',
        support = 'buffs, weakening spells, cures',
    },
    -- jobs whose default rules heal or support others, and what a Tank / Damage Role takes from them: WHM cures, status
    -- removal and party buffs; RDM cures and buffs on you and the party; PLD its Cure
    CARE = { WHM = { cleanse = true, buffs = true }, RDM = { buffs = true }, PLD = {} },
    CAP = { tank = 40, damage = 30 },
    SHIFT = { aggressive = 15, conserve = -15 },
};
for role, text in pairs(ROLE_HELP) do ROLE_INFO.TIPS[role] = text .. '\n\n' .. ROLE_INFO.FOOTER; end

-- (role clarity) the small gold note on a mate's row: only when a Tank or Damage Role takes healing or support away
-- from a job (main or sub) whose default rules have it. A PLD tank without a WHM/RDM sub job is the usual set-up: no
-- note. It speaks only of the default job rules; (1.26n) it is left out while the Rules line shows a Rule Set running.
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

-- (1.26n) the Rules line of a mate card: what the called mate really runs (the server's rs| line), what is chosen for
-- its next call, and whether Apply now is needed. Returns parts { { colour name, text }, ... } and the tooltip.
-- The server decides every state; nothing here guesses that a set runs.
ROLE_INFO.RS_STATES = { off = true, unknown = true, addon = true, set = true, job = true, fallback = true, pending = true };
ROLE_INFO.RS_WHY = {
    job    = 'The main job was changed since the call.',
    choice = 'Another Rule Set (or none) was chosen since the call.',
    edited = 'The running Rule Set was saved with changes since the call.',
    gone   = 'The running Rule Set is no longer saved: the next call uses the default job rules.',
    role   = 'The Role or Mode was changed since the call.',
};
ROLE_INFO.RS_FB = {
    [1] = 'the chosen Rule Set no longer exists or is not valid',
    [2] = 'the chosen Rule Set number now belongs to a different set',
    [3] = 'none of its rules can be used at this level and job',
    [4] = 'Squads has no job rules for this job: the trust\'s own rules run, and Rule Sets do not apply',
};
function ROLE_INFO.rules(mate, rs, stale, calling)
    local roleName = mate.role and (mate.role:sub(1, 1):upper() .. mate.role:sub(2)) or 'Auto';
    local function default(job) return 'Default ' .. job .. ' job rules' .. ((mate.role and mate.role ~= 'auto') and (' (' .. roleName .. ')') or ''); end
    local liveJob = (rs.job ~= nil and rs.job ~= '-' and rs.job ~= '') and rs.job or mate.main;
    local using;
    if rs.live > 0 then
        using = 'Gambits: ' .. ((rs.liveName ~= '?' and rs.liveName ~= '-') and rs.liveName or ('Rule Set ' .. rs.live .. ' (no longer saved)'));
    elseif rs.fb == 4 then
        using = liveJob .. ' trust\'s own rules';
    else
        using = default(liveJob);
    end
    local chosen, nextCall;
    if rs.sel > 0 and rs.selName ~= '?' and rs.selName ~= '-' then
        chosen = rs.selName; nextCall = 'Gambits: ' .. rs.selName;
    elseif rs.sel > 0 then
        chosen = 'Rule Set ' .. rs.sel .. ' (cannot be used)'; nextCall = default(mate.main);
    else
        chosen = 'None'; nextCall = default(mate.main);
    end
    local roleLine = 'Squad Role: ' .. roleName .. ((rs.state == 'set') and ' (not used while a Rule Set runs)'
        or ' (filters only the default job rules)');
    local function tip(status)
        return table.concat({ 'Currently using: ' .. using, 'Selected Rule Set: ' .. chosen, roleLine, status }, '\n');
    end
    if stale then
        return { { 'dim', 'Checking...' } }, 'A change was sent. Waiting for the server\'s answer before showing what this mate runs.';
    elseif rs.state == 'off' and calling then
        -- (1.29) being called: what it is expected to run, said as that. What it runs is shown once the server reports it.
        return { { 'dim', 'Next call: ' .. nextCall } },
            'Being called. Expected at this call: ' .. nextCall .. '\nSelected Rule Set: ' .. chosen .. '\n' .. roleLine
            .. '\nWhat it really runs is shown here once the server reports it.';
    elseif rs.state == 'off' then
        return { { 'dim', 'Not called.  Next call: ' .. nextCall } },
            'Selected Rule Set: ' .. chosen .. '\n' .. roleLine .. '\nNothing runs until the mate is called.';
    elseif rs.state == 'unknown' then
        return { { 'dim', 'Not reported' } }, 'This mate was called before the server could report its rules (or by an older call path). Apply now to see them.';
    elseif rs.state == 'addon' then
        return { { 'dim', 'Run by an add-on' } }, 'An installed add-on builds this mate\'s rules; Squads and Rule Sets do not.';
    elseif rs.state == 'set' then
        local parts = { { 'good', using } };
        if rs.dropped > 0 then
            -- (1.28) "skipped": the server's count of the set's rules that this mate cannot use at its level and job;
            -- they are not part of what runs (squad_rulesets.lua: dropped). Which ones: Check, in the Gambits editor.
            parts[#parts + 1] = { 'warn', string.format('  (%d rule%s skipped)', rs.dropped, rs.dropped == 1 and '' or 's') };
        end
        return parts, tip(rs.dropped > 0 and string.format('Active. %d rule%s of the set cannot be used at this level or job and %s skipped. Check, in the Gambits editor, shows which.',
            rs.dropped, rs.dropped == 1 and '' or 's', rs.dropped == 1 and 'is' or 'are') or 'Active: the selected Rule Set is running.');
    elseif rs.state == 'fallback' and rs.fb == 4 and rs.sel == 0 then
        return { { 'text', using } }, tip(ROLE_INFO.RS_FB[4] .. '.');
    elseif rs.state == 'fallback' then
        return { { 'warn', using }, { 'warn', '  Rule Set not used' } },
            tip('Fallback: ' .. (ROLE_INFO.RS_FB[rs.fb] or 'the chosen Rule Set could not be used') .. '.');
    elseif rs.state == 'pending' then
        return { { 'text', using }, { 'warn', '  Apply needed' } },
            tip((ROLE_INFO.RS_WHY[rs.why] or 'The settings changed since the call.') .. '\nNext call: ' .. nextCall .. '. Press Apply now.');
    end
    return { { 'text', using } }, tip('Default job rules: no Rule Set is selected for this job.');
end

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

-- the look (1.27): the colours of the theme in use, filled by X.applyTheme from xifo_ui (U.menu). The Squad theme is
-- this menu's look as it always was, value for value; Classic and Crimson fill the same roles from their palettes.
-- Names: gold text dim good bad warn hp mp on onHi sel selHi panel line faint busy go goHi goText.
local C = {};
-- (1.27) one table for what 1.27 adds, to keep this file's count of locals down
local X = { names = {}, gearCache = {} };
function X.applyTheme(name)
    local m = U.menu(name);
    for k, v in pairs(m.c) do C[k] = v; end
    X.menu, X.themeName = m, m.name;
    return m.name;
end
X.applyTheme('squad');   -- (until the settings are read at load)

-- ---------------------------------------------------------------- state
local S = {
    open = { false }, tab = 'Squad',
    -- squad
    mates = {}, incoming = nil, waitUntil = 0, hideUntil = 0, lastAsk = -1000, lastSend = -1000, queue = {}, pendingApply = false, more = {},
    actionsOpen = { false }, actionsFresh = false,
    sheetOpen = { false }, sheetFresh = false, profile = nil, profileIncoming = nil, sheetSlot = nil, sheetWaitUntil = 0, lastSheetAsk = -1000,
    -- dualbox
    duoHold = false, duo = nil, duoRead = -1000, duoSeq = 0, duoPending = nil, duoSentSeq = nil, duoSentAt = -1000, duoGambits = false,
    -- gambits
    sheet = nil, sheetText = nil, sheetPath = nil, sheetRead = -1000, sheetHoldUntil = 0, rowOverride = {}, sheetError = nil,
    -- diagnostics
    spell = { 'Dia' },
    -- the button
    cfg = { button_x = '18', button_y = '240', button_locked = 'false', button_hidden = 'false', button_wide = 'false', tab = 'Squad', spell = 'Dia', scale = '1',
            button_opacity = '100', menu_opacity = '100',     -- (1.26g, K-Andy) percent; /menu opacity
            -- (1.34) the launcher's Gambits half (Options > Show Gambits shortcut), and the compact Camp bar of 1.33 (which
            -- had no default here, so it was saved but not read back after a reload: only keys listed here are read)
            launcher_gambits = 'true', camp_compact = 'false',
            theme = '' },   -- (1.27) classic | squad | crimson; '' = not decided yet (see the load event)
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
    -- (1.26c) the timestamp addon (loaded first) puts [hh:mm:ss] in front of every line; without this the
    -- "A command error occurred" and !squad echo filters below never matched once timestamps were on
    text = text:gsub('^%[%d+:%d+:?%d*%]%s*', '');
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

-- (1.26h) the menu's own refreshes (the mate list, a mate's sheet, the Actions check): nobody waits for these
local function isRefresh(command)
    return command:find('^/say !squad panel') ~= nil or command:find('^/say !squad sheet') ~= nil or command == '/say !actions';
end

-- who: (1.26c) the character a command is meant for; it is dropped if someone else is logged in when it is due
local function enqueue(command, delay, who)
    if not isRefresh(command) then S.lastClick = now(); end
    S.queue[#S.queue + 1] = { at = now() + (delay or 0), command = command, who = who };
    ROLE_INFO.rsCommand(command, now() + (delay or 0));
end

-- (1.26d) one refresh is enough: a new ask replaces one still waiting in the queue, so five quick clicks
-- end in one panel refresh after the last of them instead of five refreshes 2.2 s apart in between
local function dropQueued(prefix)
    for i = #S.queue, 1, -1 do
        if S.queue[i].command:find(prefix, 1, true) == 1 then table.remove(S.queue, i); end
    end
end

local function ask(delay)
    dropQueued('/say !squad panel');
    enqueue('/say !squad panel', delay or 0);
    S.waitUntil = now() + (delay or 0) + 5;
    S.lastAsk = now();
    S.incoming = nil;
    S.incomingRs = nil;
end

-- (1.26n) the Rules line: what a called mate really runs, from the server's rs| line (squad_rulesets.lua R.panelLine).
-- A change this menu (or Gambits, through chat) sends makes that mate's line "Checking..." until an answer to a
-- !squad panel sent AFTER the change has come in, so an old answer never shows a set as running. slot nil = all mates.
-- (1.26n, responsiveness) After a change the menu asks again at +2, +7 and +11 s (RS_BURST: the server calls a mate
-- back 4 s after Apply, 1.5 s more per further mate), at most those three, and stops early once the answer shows the
-- change settled. A newer change replaces the plan. The normal 15 s refresh is unchanged.
ROLE_INFO.RS_BURST = { 2, 7, 11 };
ROLE_INFO.RS_TIMEOUT = 3;    -- s: an ask without an answer by then no longer holds back the next one (M2)
ROLE_INFO.RS_LOST = 10;      -- s: an ask without an answer by then is lost for good (the server answers in well under 1 s)
ROLE_INFO.RS_CHAT = { ['/say'] = true, ['/s'] = true, ['/party'] = true, ['/p'] = true, ['/linkshell'] = true, ['/l'] = true,
    ['/linkshell2'] = true, ['/l2'] = true, ['/tell'] = true, ['/t'] = true, ['/shout'] = true, ['/sh'] = true, ['/yell'] = true };
function ROLE_INFO.rsTouch(slot, at, verb)
    at = at or now();
    S.rsChangedAt = S.rsChangedAt or {};
    local key = slot or 'all';
    S.rsChangedAt[key] = math.max(S.rsChangedAt[key] or -1, at);
    -- the refresh plan for this change (an older plan is dropped), and which mates were out when it was made
    local out = {};
    for _, m in ipairs(S.mates or {}) do if m.out then out[m.slot] = true; end end
    local due = {};
    for _, d in ipairs(ROLE_INFO.RS_BURST) do due[#due + 1] = at + d; end
    S.rsBurst = { due = due, slot = slot, verb = verb, from = at, out = out };
    -- (1.27) when a mate (or the squad: 'all') was last sent for: a mate that is away right after that is being called
    -- again, not "not called", and what was waiting for its next call has been applied once it is back
    if verb == 'call' or verb == 'reapply' then
        X.recallAt = X.recallAt or {};
        X.recallVerb = X.recallVerb or {};   -- (1.29) a call the server refuses leaves a call timer; an Apply does not
        if slot then
            X.recallAt[slot], X.recallVerb[slot] = at, verb;
        else
            -- "call all" sends for everyone; Apply now (reapply) only for the mates that are out
            for _, m in ipairs(S.mates or {}) do
                if verb == 'call' or m.out then X.recallAt[m.slot], X.recallVerb[m.slot] = at, verb; end
            end
        end
    end
end

-- (1.27) the theme in use: the character's shared choice when one was made (in this menu or in Gambits), else this
-- menu's own setting. Looked at once a second while one of the menu's windows is shown, every five seconds otherwise
-- (the Squads button is always there), and at once when another character logs in. It only reads.
function X.syncTheme(t, force)
    if X.follow == nil then return; end
    local visible = S.open[1] or S.sheetOpen[1] or S.actionsOpen[1];
    if not force and t - (X.themeAt or -1000) < (visible and 1 or 5) then return; end
    X.themeAt = t;
    local shared = X.follow:poll(t, true);
    local want = shared or (U.valid(S.cfg.theme) and S.cfg.theme or U.DEFAULT);
    if want ~= X.themeName then X.applyTheme(want); end
end

-- (1.27) changes that wait for a mate's next call and that the server does not report itself (gear, sub job, range,
-- weapon skill, wait, blue magic; with an older server also Role, Mode and main job): [slot] = { at, gear }
function X.pendMate(slot, gear)
    X.pend = X.pend or {};
    local was = X.pend[slot];
    X.pend[slot] = { at = now(), gear = gear == true or (was ~= nil and was.gear == true) };
end
function X.recalledAt(slot)
    return (X.recallAt or {})[slot] or -1000;
end
-- a mate that is away within 12 s of being sent for (the server calls back 4 s after Apply, 1.5 s more per further mate)
function X.recalling(mate)
    return mate ~= nil and not mate.out and now() - X.recalledAt(mate.slot) < 12;
end
-- once per fresh mate list: a change waits only while its mate is out and has not been called again since
function X.settlePending()
    for slot, p in pairs(X.pend or {}) do
        local mate = nil;
        for _, m in ipairs(S.mates or {}) do if m.slot == slot then mate = m; end end
        local recalled = X.recalledAt(slot);
        if mate == nil or (not mate.out and not X.recalling(mate))
            or (mate.out and recalled > p.at and (S.rsAnswerFor or -1) > recalled + 4) then
            X.pend[slot] = nil;
        end
    end
end
-- does this mate have something that only its next call applies? (it must be out: an away mate gets it when called)
function X.pending(mate)
    if mate == nil or not mate.out then return false; end
    if X.pend and X.pend[mate.slot] then return true; end
    local rs = S.rs and S.rs[mate.slot];
    return rs ~= nil and rs.state == 'pending' and not ROLE_INFO.rsStale(mate.slot);
end
-- the squad commands that change what a mate runs or will run: from this menu (enqueue) or typed / sent by Gambits
ROLE_INFO.RS_VERBS = { call = true, dismiss = true, reapply = true, ruleset = true, job = true, sub = true, role = true, mode = true };
function ROLE_INFO.rsCommand(command, at)
    local verb, rest = tostring(command or ''):lower():match('^/say%s+!squad%s+(%a+)%s*(%S*)');
    if verb and ROLE_INFO.RS_VERBS[verb] then
        ROLE_INFO.rsTouch(tonumber(rest), at, verb);
        return true;
    end
    return false;
end
function ROLE_INFO.rsStale(slot)
    local at = S.rsChangedAt or {};
    local changed = math.max(at.all or -1, (slot and at[slot]) or -1);
    return changed >= 0 and changed >= (S.rsAnswerFor or -2);
end
-- every !squad panel sent (by this menu, or typed / sent by another add-on), oldest first (M2). An answer is credited
-- to the OLDEST ask that could still be answered, lost ones included until RS_LOST: the server answers in order, so
-- this never credits an answer to an ask newer than the one it answers. A lost ask can only make the Rules line wait
-- one more answer, never show a change as confirmed too early.
function ROLE_INFO.rsSent(t)
    S.rsAsks = S.rsAsks or {};
    while #S.rsAsks > 0 and t - S.rsAsks[1] > ROLE_INFO.RS_LOST do table.remove(S.rsAsks, 1); end
    S.rsAsks[#S.rsAsks + 1] = t;
end
function ROLE_INFO.rsAnswered()
    local asks, t = S.rsAsks or {}, now();
    while #asks > 0 and t - asks[1] > ROLE_INFO.RS_LOST do table.remove(asks, 1); end
    if #asks > 0 then S.rsAnswerFor = table.remove(asks, 1); end   -- (no ask on record: an answer nobody here asked for proves nothing new)
end
-- an ask still waiting for its answer (sent less than RS_TIMEOUT ago), or one in the queue
function ROLE_INFO.rsAskWaiting(t)
    for _, item in ipairs(S.queue) do if item.command:find('^/say !squad panel') then return true; end end
    local asks = S.rsAsks or {};
    return #asks > 0 and t - asks[#asks] < ROLE_INFO.RS_TIMEOUT;
end
-- the change the plan is for has settled in a fresh answer: a call or reapply once the mates are back, a dismiss once
-- the mate is away, anything else at the first fresh answer
function ROLE_INFO.rsSettled(b)
    if S.rs == nil then return true; end   -- (an older server: nothing to wait for)
    local function state(slot) return S.rs[slot] and S.rs[slot].state; end
    if b.verb == 'call' or b.verb == 'reapply' then
        local slots = b.slot and { [b.slot] = true } or b.out;
        -- (nobody known to be out when it was sent, e.g. from an answer taken during an earlier re-call: all three asks)
        if next(slots) == nil then return false; end
        for slot in pairs(slots) do
            local st = state(slot);
            if st == nil or st == 'off' or st == 'unknown' then return false; end
        end
    elseif b.verb == 'dismiss' then
        for _, m in ipairs(S.mates or {}) do if (b.slot == nil or m.slot == b.slot) and m.out then return false; end end
    end
    return true;
end
-- once per frame: the next planned ask when it is due, the Squad tab is shown, no ask is waiting and no answer is
-- coming in (an ask resets the half-read answer)
function ROLE_INFO.rsBurstTick(t)
    local b = S.rsBurst;
    if b == nil then return; end
    if not (S.open[1] and S.tab == 'Squad') then S.rsBurst = nil; return; end
    if S.rsAnswerFor and S.rsAnswerFor > b.from and ROLE_INFO.rsSettled(b) then S.rsBurst = nil; return; end
    if b.due[1] == nil then S.rsBurst = nil; return; end
    if t < b.due[1] or S.incoming ~= nil or S.incomingRs ~= nil then return; end
    table.remove(b.due, 1);
    if not ROLE_INFO.rsAskWaiting(t) then ask(); end
end
-- (M1) a chat line another add-on (or you) sent: the menu waits SAY_GAP after it before typing its own next line, or
-- the game may drop one of the two. Lines this menu sent itself are recognised and not counted.
function ROLE_INFO.rsOwnSay(command, t)
    S.ownSays = S.ownSays or {};
    S.ownSays[#S.ownSays + 1] = { text = command, at = t };
end
function ROLE_INFO.rsSeenSay(command, t)
    local own = S.ownSays or {};
    for i = #own, 1, -1 do
        if t - own[i].at > 5 then table.remove(own, i);
        elseif own[i].text == command then table.remove(own, i); return false; end
    end
    S.otherSayAt = t;
    return true;
end

-- Actions buttons: what you asked for (S.want[slot] = 'on' or 'off') is checked against what the server reports in every new mate list.
-- A command the game dropped is simply sent again (up to 4 tries per mate); a mate that matches is forgotten.
local function reconcileActions()
    if not S.want then return; end
    S.tries = S.tries or {};
    for _, mate in ipairs(S.mates or {}) do
        local w = S.want[mate.slot];
        if w and mate.switches ~= nil then
            local isOff = mate.switches == 0;
            if (w == 'off') == isOff then
                S.want[mate.slot] = nil; S.tries[mate.slot] = nil;
            elseif (S.tries[mate.slot] or 0) < 4 then
                S.tries[mate.slot] = (S.tries[mate.slot] or 0) + 1;
                enqueue(string.format('/say !squad sw %d all %s', mate.slot, w), 0);
                if w == 'on' and mate.out then
                    enqueue('/say !squad dismiss ' .. mate.slot, 2.5);
                    enqueue('/say !squad call ' .. mate.slot, 9);
                end
                S.actKick = now() + 2.5;
                ask(4);
            else
                S.want[mate.slot] = nil; S.tries[mate.slot] = nil;   -- gave up: the card shows the real state
            end
        end
    end
end

local function actionsWatchdog(t)
    if S.want and next(S.want) ~= nil and S.wantAt and t - S.wantAt > 40 then S.want = {}; S.tries = {}; end
end

-- The addon channel packet (id 0x1F0): [id][size][sync 2][version 1][reserved 3][text ... NUL][pad to 4]. The size byte is the dword count times two
-- plus the ninth bit of the id; the client fills the sync bytes. Only used when the server said chan|1.
local CHANNEL_ID, CHANNEL_MAX = 0x1F0, 120;
local function channelBytes(text)
    text = tostring(text or ''):gsub('%c', ' ');
    if #text > CHANNEL_MAX then text = text:sub(1, CHANNEL_MAX); end
    local size = math.ceil((8 + #text + 1) / 4) * 4;
    local b = {};
    for i = 1, size do b[i] = 0; end
    b[1], b[2] = CHANNEL_ID % 256, (math.floor(CHANNEL_ID / 256) % 2) + (size / 4) * 2;
    b[5] = 1;
    for i = 1, #text do b[8 + i] = text:byte(i); end
    return b;
end
local function channelSend(text)
    local bytes = channelBytes(text);
    if bytes[9] == 0 then return false; end   -- (nothing to say)
    local okM, pm = pcall(function() return AshitaCore:GetPacketManager(); end);
    if not okM or pm == nil then return false; end
    if pcall(pm.AddOutgoingPacket, pm, CHANNEL_ID, bytes) then return true; end
    return pcall(pm.AddOutgoingPacket, pm, CHANNEL_ID, #bytes, bytes) == true;
end

local SAY_GAP = 2.2;   -- seconds the game needs between two chat lines, or it drops the second and shows it as ">> /say ..."

local function pump(t)
    actionsWatchdog(t);
    if t - S.lastSend < 0.6 then return; end
    -- Actions clicks: one `!actions` check after the last click settles (the server also checks every 2 s on its own)
    if S.actKick and t >= S.actKick then
        local pending = false;
        for _, item in ipairs(S.queue) do if item.command:find('^/say !squad sw') then pending = true; break; end end
        if not pending then
            S.actKick = nil;
            S.queue[#S.queue + 1] = { at = t, command = '/say !actions' };
        end
    end
    -- the first command that is due; a click goes before any of the menu's own refreshes
    local pick, refresh = nil, nil;
    for i, item in ipairs(S.queue) do
        if item.at <= t then
            if not isRefresh(item.command) then pick = i; break; end
            refresh = refresh or i;
        end
    end
    pick = pick or refresh;
    if not pick then return; end
    -- (1.26h, Dugahst: "all the buttons randomly do it": the click showed up as ">> /say !squad camp start" and nothing
    -- happened) The game drops a chat line that follows another too closely, whatever the first one was. A click used
    -- to wait only after another click, so one that came right after a refresh of the menu was lost. Now every line
    -- the menu says waits its turn after the last one it said, refreshes included.
    if S.queue[pick].command:find('^/say ') and t - (S.lastSay or -1000) < SAY_GAP then return; end
    -- (1.26n, M1) the same wait after a chat line another add-on or you sent (Gambits' !gsq / !squad lines), but only for
    -- a line this menu will TYPE: one that goes as the addon channel packet is not a chat line and need not wait
    local typed = S.queue[pick].command:find('^/say ') and not (S.channel and S.queue[pick].command:find('^/say !'));
    if typed and t - (S.otherSayAt or -1000) < SAY_GAP then return; end
    local chat = chatManager();
    if chat == nil or typing(chat) then return; end
    local first = table.remove(S.queue, pick);
    if first.command:find('^/say !squad panel') then ROLE_INFO.rsSent(t); end
    if first.who then   -- (1.26c) meant for one character: not for whoever is logged in now, if that is someone else
        local ok, name = pcall(function() return AshitaCore:GetMemoryManager():GetParty():GetMemberName(0); end);
        name = (ok and tostring(name or '') or ''):match('^%s*(.-)%s*$') or '';
        if (name:gsub('[^%w_]', '_')) ~= first.who then return; end
    end
    S.lastSend = t;
    if first.command:find('^/say ') then S.lastSay = t; end
    -- the game drops chat lines sent close together: every Squads action (call, dismiss, switches, options) goes out 2.2 seconds after the one before, however fast you click
    -- (1.26h: that wait is SAY_GAP above, and it counts from any line the menu said)
    S.hideUntil = t + 6;   -- (1.25: was 2.5 s; a busy server answers later than that)
    -- (1.26c) every /autobox line this menu sends is counted, so the command event can tell ours from the player's
    -- even when the game runs a queued command later than the next one is sent
    if first.command:find('^/autobox ') then
        S.ownAutobox = S.ownAutobox or {};
        S.ownAutobox[#S.ownAutobox + 1] = { text = first.command, at = t };
    end
    -- the server handles the addon channel packet: a "!" line goes out as that packet, so it is not typed, not echoed, not a chat line
    if S.channel and first.command:find('^/say !') and channelSend(first.command:sub(6)) then return; end
    if first.command:find('^/say ') then ROLE_INFO.rsOwnSay(first.command, t); end   -- (M1: not counted as another add-on's line)
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
    -- the server handles the addon channel packet (packets/c2s/0x1f0_addon_channel.h): chan|<version>. An older server never says it.
    local chanVersion = payload:match('^chan|(%d+)$');
    if chanVersion then
        -- (only as the answer to a line this menu sent a moment ago: a player who types the words in chat changes nothing)
        if now() < S.hideUntil then S.incomingChannel = chanVersion == '1'; end
        return;
    end
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
        if g and g.slot == tonumber(es) and g.eq == tonumber(ee) then
            g.done, g.total = true, tonumber(ecount);
            X.gearCache[g.slot .. ':' .. g.eq] = { items = g.items, total = g.total, at = now() };   -- (1.27) kept two minutes
        end
        S.waitUntil = 0;
        return;
    end
    if payload == 'end' then
        S.channel = S.incomingChannel == true;   -- (an older server never says chan|1, so the menu keeps typing)
        S.incomingChannel = nil;
        -- (1.26n) the Rules lines of this answer (nil from an older server: no Rules line is drawn), and which ask it answers
        S.rs = S.incomingRs;
        S.incomingRs = nil;
        ROLE_INFO.rsAnswered();
        S.mates = S.incoming or {};
        X.caps = S.incomingCaps or {};          -- (1.27; nothing from an older server: one-mate Apply is not offered)
        S.incomingCaps = nil;
        X.settlePending();
        reconcileActions();
        S.incoming = nil;
        S.behs = S.incomingBeh;                 -- (nil from an older server: the Forward to Gambits button stays hidden)
        S.incomingBeh = nil;
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
    -- (1.27) cap|<words>: what this server can do beyond the first menus (squad.lua says reapply1 when "!squad reapply
    -- <slot>" re-calls one mate). The menu uses such a form only after it has read the word in the answer in use.
    local caps = payload:match('^cap|([%w_,]+)$');
    if caps then
        S.incomingCaps = {};
        for word in caps:gmatch('[%w_]+') do S.incomingCaps[word] = true; end
        return;
    end
    local camp = parseCamp(payload);
    if camp then S.incomingCamp = camp; return; end
    -- (1.33, community feedback F5-F7) campst|<camp 1/0>|<paused 1/0>|<state>|<pulls>|<next pull at enemy HP %>|<healer MP %>:
    -- in a panel answer, or by itself when the camp changed (squad.lua SQUAD_CAMPX.push); then it is applied at once
    local stOn, stPaused, stState, stPulls, stAt, stMp = payload:match('^campst|([01])|([01])|(%a+)|(%d+)|(%d+)|(%d+)$');
    if stOn then
        X.campSt({ on = stOn == '1', paused = stPaused == '1', state = stState, pulls = tonumber(stPulls), pullAt = tonumber(stAt),
                   healerMp = tonumber(stMp) });
        return;
    end
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
                                            range = tonumber(orange), list = list, pos = (S.incomingOpts[tonumber(oslot)] or {}).pos };
        return;
    end
    -- (1.35) pos|<slot>|<0 normal, 1 behind, 2 ta>: where the mate stands in a fight (!squad position); the server says it
    -- right after the mate's opt line, and offers the setting with cap|...,matepos
    local pslot, pmode = payload:match('^pos|(%d+)|(%d+)$');
    if pslot then
        S.incomingOpts = S.incomingOpts or {};
        local o = S.incomingOpts[tonumber(pslot)] or {};
        o.pos = tonumber(pmode);
        S.incomingOpts[tonumber(pslot)] = o;
        return;
    end
    -- (1.37, F18) rf|<slot>|<0 off, else MP %>[|<Wake to act rules of the mate that is out, -1 not out>]: Rest in fights
    -- (!squad restfight); offered with cap|...,restfight. The third field drives the "no Wake to act rule" warning.
    local rslot, rval, rwake = payload:match('^rf|(%d+)|(%d+)|?(%-?%d*)$');
    if rslot then
        S.incomingOpts = S.incomingOpts or {};
        local o = S.incomingOpts[tonumber(rslot)] or {};
        o.rf = tonumber(rval);
        o.rfWake = tonumber(rwake);
        S.incomingOpts[tonumber(rslot)] = o;
        return;
    end
    -- (1.37, F23) camprange|<yalms>|<1 set, 0 default>: the camp's pull search range (!squad camp range); in a panel answer or
    -- by itself after a change (squad.lua SQUAD_CAMPX.push)
    local crange, cown = payload:match('^camprange|(%d+)|([01])$');
    if crange then
        local target = S.incomingCamp or S.camp;
        if target then target.range, target.rangeOwn = tonumber(crange), cown == '1'; end
        X.lastRange = { range = tonumber(crange), own = cown == '1' };
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
    -- (Jon + Deed 2026-11-21) beh|<key>|<on|off|mixed>|<label>: the squad AI switches, for the Forward to Gambits button
    local bkey, bstate, blabel = payload:match('^beh|([%w_]+)|(%a+)|(.+)$');
    if bkey then
        S.incomingBeh = S.incomingBeh or {};
        table.insert(S.incomingBeh, { key = bkey, state = bstate, label = blabel });
        return;
    end
    -- (1.26n) rs|<slot>|<state>|<why>|<live num>|<live name>|<chosen num>|<chosen name>|<fallback>|<left out>|<job at the call>
    local rsSlot, rsState, rsWhy, rsLive, rsLiveName, rsSel, rsSelName, rsFb, rsDrop, rsJob =
        payload:match('^rs|(%d+)|(%a+)|([%a-]+)|(%d+)|([^|]*)|(%d+)|([^|]*)|(%d+)|(%d+)|([^|]*)$');
    if rsSlot then
        if ROLE_INFO.RS_STATES[rsState] then
            S.incomingRs = S.incomingRs or {};
            S.incomingRs[tonumber(rsSlot)] = { state = rsState, why = rsWhy, live = tonumber(rsLive), liveName = rsLiveName,
                sel = tonumber(rsSel), selName = rsSelName, fb = tonumber(rsFb), dropped = tonumber(rsDrop), job = rsJob };
        end
        return;
    end
    -- (1.26m, Dugahst) jl|<slot>|<JOB>:<level>,...: each job's own level, shown in the Job and Sub lists
    local jlSlot, jlList = payload:match('^jl|(%d+)|(.+)$');
    if jlSlot then
        S.jobLevels = S.jobLevels or {};
        local levels = {};
        for job, lv in jlList:gmatch('(%u+):(%d+)') do levels[job] = tonumber(lv); end
        S.jobLevels[tonumber(jlSlot)] = levels;
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
    dropQueued('/say !squad sheet');
    enqueue(string.format('/say !squad sheet %d', S.sheetSlot), delay or 0);
    S.sheetWaitUntil = now() + (delay or 0) + 5;
    S.lastSheetAsk = now();
    S.profileIncoming = {};
end

-- tab (1.27): 'stats' or 'gear'; nil keeps the view that was shown
local function openSheet(slot, tab)
    slot = tonumber(slot);
    if slot == nil then return; end
    if tab == 'stats' or tab == 'gear' then S.sheetTab = tab; end
    S.sheetSlot = slot;
    S.sheetOpen[1] = true;
    S.sheetFresh = true;        -- next frame: put the window in the middle of the screen, in front
    S.profile = nil;
    S.profileHeld = nil;
    askSheet(0);
end

-- (1.27) whose sheet an answer is. The window can go to another mate while the answer for the one before is still on
-- its way, and that answer must never be shown under the new mate (its gear cells would send commands for the new one).
-- A server that says the slot (squadsheet:slot|<n>, before hdr) is taken at its word. An older one names only the
-- mate, and a squad has no two mates of one name: the answer is this mate's when the name is the selected mate's.
-- true / false, or nil while the squad list has not said that slot's name yet.
function X.sheetIsFor(data, slot)
    if data.slot ~= nil then return data.slot == slot; end
    for _, m in ipairs(S.mates or {}) do
        if m.slot == slot then return data.hdr ~= nil and m.name == data.hdr.name; end
    end
    return nil;
end
-- the sheet the window may show: only one that is known to be the selected mate's (S.profile.forSlot says whose)
function X.sheetShown()
    local held = S.profileHeld;
    if held ~= nil then
        local mine = X.sheetIsFor(held, S.sheetSlot);
        if mine ~= nil then
            S.profileHeld = nil;
            if mine then held.forSlot = S.sheetSlot; S.profile = held; end
        end
    end
    local d = S.profile;
    if d ~= nil and d.forSlot ~= S.sheetSlot then return nil; end
    return d;
end

local function onSheetLine(text)
    if text == 'end' then
        local data = S.profileIncoming;
        S.profileIncoming = nil;
        if data and data.hdr then
            local mine = X.sheetIsFor(data, S.sheetSlot);
            if mine then
                data.forSlot, data.at = S.sheetSlot, now();
                S.profile, S.profileHeld = data, nil;
            elseif mine == nil then
                data.at = now();
                S.profileHeld = data;       -- (shown once the squad list says who is in that slot)
            end
        end
        return;
    end
    local key, rest = text:match('^(%a+)|(.*)$');
    if not key then return; end
    -- an answer starts at its slot line (or at hdr, from an older server): one that follows another without a
    -- request in between (the late answer for the mate before, then this mate's) is read too
    if key == 'slot' then
        S.profileIncoming = { slot = tonumber(rest) };
        return;
    end
    local data = S.profileIncoming;
    if key == 'hdr' and (data == nil or data.hdr ~= nil) then
        data = {};
        S.profileIncoming = data;
    end
    if not data then return; end
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
    elseif key == 'spell' or key == 'ability' then
        -- (1.26l, Frost) a called mate's spells (name | MP) and job abilities (name | level)
        local name, value = rest:match('^([^|]+)|(%d+)$');
        if name then
            local field = (key == 'spell') and 'spells' or 'abilities';
            data[field] = data[field] or {};
            data[field][#data[field] + 1] = { name, tonumber(value) or 0 };
        end
    end
end

-- "cure_ii" / "Cure II" / "provoke" -> "Cure II", "Provoke"
local ROMAN = { i = 'I', ii = 'II', iii = 'III', iv = 'IV', v = 'V', vi = 'VI' };
local function prettyName(text)
    local words = {};
    for word in tostring(text or ''):gsub('_', ' '):gmatch('%S+') do
        local lower = word:lower();
        words[#words + 1] = ROMAN[lower] or (lower:sub(1, 1):upper() .. lower:sub(2));
    end
    return table.concat(words, ' ');
end

-- role, mode, job and sub apply when a mate is called, so they leave a "press Apply now" banner
local function changeMate(mate, kind, value)
    enqueue(string.format('/say !squad %s %d %s', kind, mate.slot, value));
    if kind == 'role' or kind == 'mode' then mate[kind] = value; end
    if kind == 'job' then mate.main = value; end
    if kind == 'sub' then mate.sub = (value == 'none') and '-' or value; end
    -- (1.27) a server with the Rules line says itself what a Role, Mode or main job change leaves to apply (and that a
    -- Role changes nothing while a Rule Set runs); every other change is remembered here until that mate is called again
    if not (S.rs ~= nil and (kind == 'role' or kind == 'mode' or kind == 'job')) then X.pendMate(mate.slot); end
    if kind == 'job' or kind == 'sub' then X.dropGear(mate.slot); end
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
    X.pend = {};
    X.gearCache = {};
end

-- (1.27) Apply for ONE mate: "!squad reapply <slot>" when the server said it can (cap|reapply1), so the others stay
-- out and keep fighting. An older server would re-call everyone on that line, so there the squad-wide Apply is sent
-- and the button says so. Returns true when only this mate is re-called.
function X.applyMate(mate)
    if X.caps and X.caps.reapply1 then
        enqueue(string.format('/say !squad reapply %d', mate.slot));
        ask(5);
        if X.pend then X.pend[mate.slot] = nil; end
        X.dropGear(mate.slot);
        return true;
    end
    applyNow();
    return false;
end
function X.applyTip(mate)
    if X.caps and X.caps.reapply1 then
        return 'Sends only ' .. mate.name .. ' off and calls them again with the new settings (about 4 seconds). The others stay out.';
    end
    return 'This server can only call the whole squad again: every mate that is out leaves and comes back.';
end
-- the gear lists kept for one mate (or all): asked again after a job change, an Apply, or two minutes
function X.dropGear(slot)
    for key in pairs(X.gearCache) do
        if slot == nil or key:match('^(%d+):') == tostring(slot) then X.gearCache[key] = nil; end
    end
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
    -- (inside our window, or while our window's font is pushed, the font is scaled already)
    if (S.scaledNow or S.fontPushed) and type(size) == 'number' then size = size / us; end
    local scale = (type(size) == 'number' and size > 0) and math.max(1, math.min(3, size / 13)) or 1;
    return math.floor(n * scale * us + 0.5);
end

-- (1.34) The text of every window of this menu at its Size, the way the Gambits window does it: the game's font pushed
-- AT the scaled size (ImGui 1.92: PushFont(font, size) lays the letters out for that size), before the window begins and
-- popped after it ends. Until 1.33 the font was drawn at its own size and stretched by SetWindowFontScale, so at 120 %
-- the Squads menu's letters were softer than the Gambits window's at the same Size. SetWindowFontScale stays the fallback
-- for a binding without PushFont. Returns whether a font was pushed; X.popFont(pushed) closes it exactly.
function X.pushFont()
    local us = userScale();
    if us == 1 or S.fontPushed or not (has('PushFont') and has('GetFont') and has('GetFontSize')) then return false; end
    local ok = pcall(function () imgui.PushFont(imgui.GetFont(), imgui.GetFontSize() * us); end);
    S.fontPushed = ok;
    return ok;
end
function X.popFont(pushed)
    if pushed then pcall(imgui.PopFont); S.fontPushed = false; end
end

local function scaleWindow()
    if S.fontPushed then S.scaledNow = true; return; end   -- (1.34: the font is the scaled one already)
    if has('SetWindowFontScale') then imgui.SetWindowFontScale(userScale()); S.scaledNow = true; end
end
local function G(name) return rawget(_G, name); end

local function colorText(color, text)
    if has('TextColored') then imgui.TextColored(color, text); else imgui.Text(text); end
end

local function dimText(text) colorText(C.dim, text); end

-- (1.27) every wrapped line and every tooltip goes through xifo_ui: drawn with TextUnformatted, wrapped at about 27
-- characters' width of the current font. Ashita hands the text of SetTooltip and TextWrapped to ImGui as a printf
-- FORMAT, and these texts can hold a '%' ("below 30% HP", an item's "Haste+4%"), which then prints garbage or ends the
-- game. (1.26n drew only the Role and Mode tooltips this way; an item's description went to SetTooltip as it was.)
local function wrapped(text, color) U.wrapped(imgui, color, text); end

local function tooltip(text) if text ~= nil then U.tooltip(imgui, text, px(350)); end end

ROLE_INFO.WRAP_EM = U.TOOLTIP_WRAP_EM;
function ROLE_INFO.tip(text) if text ~= nil then U.tooltip(imgui, text, px(350)); end end

local function pushColors(list)
    local n = 0;
    for _, pair in ipairs(list) do
        local id = G(pair[1]);
        if id ~= nil then imgui.PushStyleColor(id, pair[2]); n = n + 1; end
    end
    return n;
end

-- a button that can look selected, switched on, be the main action of its view ('go') or wait for the server ('busy':
-- drawn, never clicked). (1.27) the colours are the theme's; what was pushed is popped also when the button fails.
local function button(label, id, w, h, look)
    local n = 0;
    if look == 'selected' then n = pushColors({ { 'ImGuiCol_Button', C.sel }, { 'ImGuiCol_ButtonHovered', C.selHi }, { 'ImGuiCol_ButtonActive', C.selHi } });
    elseif look == 'on' then n = pushColors({ { 'ImGuiCol_Button', C.on }, { 'ImGuiCol_ButtonHovered', C.onHi }, { 'ImGuiCol_ButtonActive', C.onHi } });
    elseif look == 'go' then n = pushColors({ { 'ImGuiCol_Button', C.go }, { 'ImGuiCol_ButtonHovered', C.goHi }, { 'ImGuiCol_ButtonActive', C.goHi }, { 'ImGuiCol_Text', C.goText } });
    elseif look == 'busy' then n = pushColors({ { 'ImGuiCol_Button', C.busy }, { 'ImGuiCol_ButtonHovered', C.busy }, { 'ImGuiCol_ButtonActive', C.busy } }); end
    local ok, clicked = pcall(imgui.Button, label .. '##' .. id, { px(w or 0), px(h or 0) });
    if n > 0 then imgui.PopStyleColor(n); end
    if not ok then error(clicked, 0); end
    return clicked == true and look ~= 'busy';
end

-- (1.27) the next control stays on this line when `w` pixels (as laid out for the usual font) still fit, else it
-- starts a new line: nothing is cut off at the window's edge any more (the top row needed 850 px in a 592 px window)
function X.fit(w, spacing)
    return U.same_if_fits(imgui, px(w), spacing or 6);
end
-- (1.34) the cursor's x in the window (Ashita hands back a number), or nil
function X.cursorX()
    if not has('GetCursorPosX') then return nil; end
    local ok, x = pcall(imgui.GetCursorPosX);
    return (ok and type(x) == 'number') and x or nil;
end
-- (1.34) the next control on this line when `w` PIXELS (measured: text widths, px() sizes) still fit, else on a new line
-- starting at `indentX` (the column the group belongs to), so a wrapped group lines up under its row, not at the edge
function X.fitAt(w, indentX, spacing)
    local stayed = U.same_if_fits(imgui, w, spacing or 6);
    if not stayed and indentX and has('SetCursorPosX') then pcall(imgui.SetCursorPosX, indentX); end
    return stayed;
end
-- (1.34) start a new line at `x` (after the previous line's last control)
function X.lineAt(x)
    if x and has('SetCursorPosX') then pcall(imgui.SetCursorPosX, x); end
end
-- (1.28) a tab: the same in every window of the menu. The main ones (Squad / Dualbox / Auto, Stats / Gear) are
-- U.SIZE.tab high; `compact` is the smaller kind for a choice inside a view (Equipment / Look). The selected one has
-- the theme's tab colour. As wide as its text plus the tab padding.
function X.tab(label, id, selected, compact)
    local h = px(compact and U.SIZE.tabCompact or U.SIZE.tab);
    local colors = selected and { { 'ImGuiCol_Button', C.sel }, { 'ImGuiCol_ButtonHovered', C.selHi }, { 'ImGuiCol_ButtonActive', C.selHi } } or nil;
    local token = U.push(imgui, colors, { { 'ImGuiStyleVar_FramePadding', { px(compact and U.SIZE.tabPadCompact or U.SIZE.tabPad), X.sv(3) } } });
    local ok, clicked = pcall(imgui.Button, label .. '##' .. id, { 0, h });
    U.pop(imgui, token);
    if not ok then error(clicked, 0); end
    return clicked == true;
end
-- (1.30) a second column in a card's Settings: the next group starts at X.COL.second when w pixels (at the usual size)
-- fit there, else on a new line. Returns true when it stayed on the row.
function X.column2(w)
    imgui.SameLine(px(X.COL.second), 0);
    local left = U.avail(imgui);
    if has('NewLine') and left ~= nil and left < px(w) then imgui.NewLine(); return false; end
    return true;
end
-- a gold caption in front of a row of controls, the controls starting at the same place in every row
function X.rowLabel(text)
    colorText(C.gold, text);
    imgui.SameLine(px(U.SIZE.labelCol), 0);
end
-- a little more room than between two rows: the next group of rows starts
function X.group()
    if has('Dummy') then imgui.Dummy({ 0, X.sv(U.SIZE.group - 4) }); end
end
-- the next control at the right edge of the row when `w` pixels (at the usual size) fit there, else on a new line
function X.right(w)
    local stayed = U.same_if_fits(imgui, px(w), 6);
    if stayed and has('GetCursorPosX') and has('SetCursorPosX') then
        local left = U.avail(imgui);
        local ok, x = pcall(imgui.GetCursorPosX);
        if left ~= nil and ok and type(x) == 'number' and left > px(w) then pcall(imgui.SetCursorPosX, x + left - px(w)); end
    end
    return stayed;
end
function X.textW(text)
    if has('CalcTextSize') then
        local ok, a = pcall(imgui.CalcTextSize, tostring(text or ''));
        if ok and type(a) == 'table' then return tonumber(a[1] or a.x) or 0; end
        if ok and type(a) == 'number' then return a; end
    end
    return #tostring(text or '') * 7;
end
-- style values grow with the menu's Size, like the Gambits window's
function X.sv(n)
    return math.max(1, math.floor(n * userScale() + 0.5));
end
-- the shared metrics for the theme and Size in use: the list is made once, not in every frame for every window
function X.vars()
    local key = tostring(X.themeName) .. ':' .. tostring(userScale());
    if X.varsKey ~= key then X.varsKey, X.varsList = key, U.window_vars(X.menu.palette, X.sv); end
    return X.varsList;
end
-- a window's colours: the theme's, then the ones given (kept per theme and name; extra is used when it is first made)
function X.windowColors(name, extra)
    local key = tostring(X.themeName) .. ':' .. name;
    X.colorLists = X.colorLists or {};
    if X.colorLists[key] == nil then
        local list = {};
        for _, pair in ipairs(X.menu.window) do list[#list + 1] = pair; end
        for _, pair in ipairs(extra()) do list[#list + 1] = pair; end
        X.colorLists[key] = list;
    end
    return X.colorLists[key];
end
-- a card whose height is what its content needed in the last frame (`guess`, in pixels, for the first one): rows can
-- wrap, a long Rule Set name fits, and nothing is clipped. No scroll bar of its own.
function X.card(id, guess)
    X.cardH = X.cardH or {};   -- (1.28: before the line below; an ImGui without BeginChild made X.cardEnd fail and the menu close)
    if not has('BeginChild') then return true, false; end
    local flags = G('ImGuiChildFlags_Borders') or G('ImGuiChildFlags_Border') or true;
    local wflags = (G('ImGuiWindowFlags_NoScrollbar') or 0) + (G('ImGuiWindowFlags_NoScrollWithMouse') or 0);
    return imgui.BeginChild(id, { 0, X.cardH[id] or guess }, flags, wflags), true;
end
-- `open` is what BeginChild said: false for a card that is scrolled out of view. Nothing was drawn in it then, so its
-- height is not measured: it keeps the one it had (a card of 16 pixels would make the list jump).
function X.cardEnd(id, began, open)
    if open and has('GetCursorPosY') then
        local ok, y = pcall(imgui.GetCursorPosY);
        if ok and type(y) == 'number' and y > 0 then X.cardH[id] = math.floor(y + X.sv(8) + 0.5); end
    end
    if began and has('EndChild') then imgui.EndChild(); end
end

-- a drop-down list; falls back to a row of buttons when this ImGui has no combo boxes
-- (1.26m) labels: what to show for an item ("WHM (34)"), the item itself is still what is returned
local function combo(id, current, items, width, help, tip, labels)
    local chosen = nil;
    tip = tip or tooltip;   -- (role clarity) the Role and Mode lists pass ROLE_INFO.tip (wrapped)
    labels = labels or {};
    if has('BeginCombo') and has('Selectable') and has('EndCombo') then
        if has('PushItemWidth') then imgui.PushItemWidth(px(width)); end
        if imgui.BeginCombo('##' .. id, labels[current] or current or '?') then
            for _, item in ipairs(items) do
                if imgui.Selectable((labels[item] or item) .. '##' .. id .. item, item == current) then chosen = item; end
                if help and help[item] then tip(help[item]); end
            end
            imgui.EndCombo();
        end
        if has('PopItemWidth') then imgui.PopItemWidth(); end
        if help and help[current] then tip(help[current]); end
    else
        for i, item in ipairs(items) do
            if i > 1 then imgui.SameLine(0, 3); end
            if button(labels[item] or item, id .. item, 0, 0, item == current and 'selected' or nil) then chosen = item; end
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
    -- (1.32) A child without a border only holds things (the list the cards scroll in): it has no background of its
    -- own. It had the panel colour like a card, so the cards stood on a second see-through layer: the list was darker
    -- than the rows above it, most of all at a low menu opacity. ImGui paints a child's background when it begins.
    local clear = (not border) and U.push(imgui, { { 'ImGuiCol_ChildBg', { 0, 0, 0, 0 } } }) or nil;
    local open;
    if noScroll then
        local wflags = (G('ImGuiWindowFlags_NoScrollbar') or 0) + (G('ImGuiWindowFlags_NoScrollWithMouse') or 0);
        open = imgui.BeginChild(id, { px(w), px(h) }, flags, wflags);
    else
        open = imgui.BeginChild(id, { px(w), px(h) }, flags);
    end
    if clear then U.pop(imgui, clear); end
    return open, true;
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
    X.rowLabel('Camp');
    if button(camp.on and 'Move camp here' or 'Set camp here', 'campset', 124, 0, camp.on and 'on' or nil) then
        X.campSetOrMove(camp);
    end
    tooltip(camp.on and X.caps and X.caps.campmove and 'The camp moves to where you stand; the puller, the picks and Start / Pause stay'
        or 'Your squad holds this spot and fights whatever comes within 20 yalms of it');
    if camp.on then
        imgui.SameLine(0, 6);
        if button('Camp off', 'campoff', 84, 0) then campCommand('camp off'); camp.on = false; end
        tooltip('They follow you again');
    end
    local contentX = px(U.SIZE.labelCol);   -- (1.34) where this row's controls start: a wrapped group goes back to here
    X.fitAt(X.textW('Puller') + X.sv(8) + px(110), contentX, 14);
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
        X.fitAt(px(72), contentX);
        -- (1.22) a new camp waits for Start before the first pull (squad.lua, from Jon Tanta's Squad Update)
        local fresh = camp.paused and (camp.pulls or 0) == 0;
        if button(camp.paused and (fresh and 'Start' or 'Resume') or 'Pause', 'camppause', 72, 0, camp.paused and 'selected' or nil) then
            campCommand(camp.paused and (fresh and 'camp start' or 'camp resume') or 'camp pause'); camp.paused = not camp.paused;
        end
        tooltip(camp.paused and (fresh and 'The puller starts pulling' or 'The puller goes back to pulling') or 'No new pulls (the squad still holds camp)');
    end
    if camp.on then
        -- (1.33) what the camp is doing now (campst), before the pull count; (1.34) measured, so it is never cut at the
        -- window's edge ("Paused, 0" was the end of "Paused, 0 pulls")
        local stateText = camp.state and X.CAMP_STATE[camp.state] or nil;
        local line = (stateText and (stateText .. ', ') or '') .. (camp.pulls == 1 and '1 pull' or (tostring(camp.pulls or 0) .. ' pulls'));
        X.fitAt(X.textW(line), contentX, 12);
        dimText(line);
    end
    X.campSettings(camp, someonePulls, contentX);
    -- what the mate pulls: any number of kinds of monster around the camp, each one toggles
    if camp.on and someonePulls and camp.kinds then
        X.lineAt(contentX);
        dimText('Pull'); imgui.SameLine(0, 8);
        local wants = camp.wants or {};
        local any = true;
        for _ in pairs(wants) do any = false; end
        local anyX = X.cursorX() or contentX;   -- (1.34) the kinds that do not fit this line start again under Anything
        if button('Anything', 'campany', 82, 0, any and 'selected' or nil) then
            campCommand('camp want any');
            camp.wants, camp.want = {}, nil;
        end
        tooltip('Whatever is a good level for you, nearest first');
        for _, k in ipairs(camp.kinds) do
            if k.fits then
                local key = k.name:lower():gsub('_', ' ');
                -- (1.24) the count is how many are up right now; none up = all defeated and waiting to come back
                local label = string.format('%s lv%d%s %s', (k.name:gsub('_', ' ')), k.lo, k.hi ~= k.lo and ('-' .. k.hi) or '', k.count > 0 and ('x' .. k.count) or '(none up)');
                X.fitAt(X.textW(label) + X.sv(12), anyX);
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

-- ---------------------------------------------------------------- (1.33) camp state, pull settings, the compact camp bar
-- Community feedback F5-F7 (2026-11-25). The server's campst line (squad.lua SQUAD_CAMPX) carries the camp's state and the two
-- pull settings, in each panel answer and by itself whenever the camp changes (a command, a click, the server's own pulls),
-- so the Camp row and the compact bar show what is true without a refresh. An older server sends no campst: no state word,
-- no pull settings, and the compact bar's toggle is not offered.
X.CAMP_STATE = { idle = 'Ready', pulling = 'Pulling', fighting = 'Fighting', paused = 'Paused', off = 'No camp' };
X.PULL_AT = { '0', '25', '40', '50', '60', '75' };
X.PULL_AT_LABEL = { ['0'] = 'Off', ['25'] = '25%', ['40'] = '40%', ['50'] = '50%', ['60'] = '60%', ['75'] = '75%' };
X.PULL_AT_HELP = {
    ['0'] = 'One monster at a time: the next pull starts after the fight (the default)',
    ['25'] = 'The puller fetches the next monster once this one is at 25% HP, if no link or pet is on the party and the puller is not the one it hits',
};
for _, k in ipairs({ '40', '50', '60', '75' }) do X.PULL_AT_HELP[k] = 'The same at ' .. k .. '% HP: earlier means more overlap'; end
X.HEALER_MP = { '0', '20', '30', '40', '50', '60', '80' };
X.HEALER_MP_LABEL = { ['0'] = 'Default', ['20'] = '20%', ['30'] = '30%', ['40'] = '40%', ['50'] = '50%', ['60'] = '60%', ['80'] = '80%' };
X.HEALER_MP_HELP = {
    ['0'] = 'Every mate with MP needs 30% MP before a pull (the default)',
};
for _, k in ipairs({ '20', '30', '40', '50', '60', '80' }) do
    X.HEALER_MP_HELP[k] = 'The healers need ' .. k .. '% MP, resting or not: you (or your second character) when your main job is '
        .. 'White Mage, and the mates with the Role Healer, else the White Mage mates. The other mates 30%. No healer: no change';
end

-- (1.37, F23) pull search range choices (!squad camp range 10-500; 60 = the server's default)
X.PULL_RANGES = { '30', '45', '60', '90', '120', '200' };
X.PULL_RANGE_LABEL = { ['30'] = '30 yalms', ['45'] = '45 yalms', ['60'] = '60 yalms', ['90'] = '90 yalms', ['120'] = '120 yalms',
                       ['200'] = '200 yalms' };
X.PULL_RANGE_HELP = { ['60'] = 'The default: your own area, not the far side of the zone' };

function X.campSt(st)
    local function apply(camp)
        camp.on, camp.paused, camp.pulls, camp.state = st.on, st.paused, st.pulls, st.state;
        camp.pullAt, camp.healerMp = st.pullAt, st.healerMp;
    end
    if S.incomingCamp then apply(S.incomingCamp); return; end
    if S.camp then
        apply(S.camp);
    elseif st.on then
        S.camp = { on = true, puller = 0 };
        apply(S.camp);
        ask(1);   -- (the puller and the kinds come with a full answer)
    end
end

-- Set camp here / Move camp here. A server that can move a camp (cap|campmove) keeps the puller, the picks and Start / Pause;
-- an older one sets a new camp, as before.
function X.campSetOrMove(camp)
    if camp.on and X.caps and X.caps.campmove then campCommand('camp move'); else campCommand('camp'); end
    camp.on = true;
end

function X.campSettings(camp, someonePulls, contentX)
    if not camp.on or camp.pullAt == nil then return; end   -- (an older server: no campst, nothing to show)
    contentX = contentX or px(U.SIZE.labelCol);
    X.lineAt(contentX);   -- (1.34) under the Camp row's controls, not at the window's edge
    local first = true;
    if someonePulls then
        -- (1.34) each label with its list is one group: it moves to the next line whole, back under the first one
        local at = tostring(camp.pullAt or 0);
        if X.PULL_AT_LABEL[at] == nil then X.PULL_AT_LABEL[at] = at .. '%'; end
        dimText('Next pull at'); imgui.SameLine(0, 6);
        local pick = combo('camppullat', at, X.PULL_AT, 70, X.PULL_AT_HELP, nil, X.PULL_AT_LABEL);
        if pick then campCommand('camp pullat ' .. (pick == '0' and 'off' or pick)); camp.pullAt = tonumber(pick); end
        tooltip('Enemy HP at which the puller fetches the next monster while the squad finishes this one');
        local mp = tostring(camp.healerMp or 0);
        if X.HEALER_MP_LABEL[mp] == nil then X.HEALER_MP_LABEL[mp] = mp .. '%'; end
        X.fitAt(X.textW('Healer MP') + X.sv(6) + px(80), contentX, 12);
        dimText('Healer MP'); imgui.SameLine(0, 6);
        local pickMp = combo('camphealermp', mp, X.HEALER_MP, 80, X.HEALER_MP_HELP, nil, X.HEALER_MP_LABEL);
        if pickMp then campCommand('camp healermp ' .. (pickMp == '0' and 'default' or pickMp)); camp.healerMp = tonumber(pickMp); end
        tooltip('MP the healers need before the next pull');
        first = false;
    end
    -- (1.37, F23) the pull search range: how far from the camp the puller looks for a monster (!squad camp range). The value
    -- shown is the server's (camprange line); a value set with the command shows as it is. Not the camp's fight reach.
    local range = camp.range or (X.lastRange and X.lastRange.range);
    if someonePulls and range ~= nil then
        local cur = tostring(range);
        if X.PULL_RANGE_LABEL[cur] == nil then X.PULL_RANGE_LABEL[cur] = cur .. ' yalms'; end
        local list = {};
        for _, v in ipairs(X.PULL_RANGES) do list[#list + 1] = v; end
        local listed = false;
        for _, v in ipairs(list) do listed = listed or v == cur; end
        if not listed then list[#list + 1] = cur; end   -- (a custom value from the command stays selectable)
        X.fitAt(X.textW('Pull range') + X.sv(6) + px(96), contentX, 12);
        dimText('Pull range'); imgui.SameLine(0, 6);
        local pickR = combo('camprange', cur, list, 96, X.PULL_RANGE_HELP, nil, X.PULL_RANGE_LABEL);
        if pickR and pickR ~= cur then campCommand('camp range ' .. pickR); camp.range = tonumber(pickR); end
        tooltip('How far from the camp the puller looks for a monster to pull (measured flat from the camp, not counting monsters '
            .. 'far above or below). The squad still fights only what comes within 20 yalms of the camp. 60 is the default.');
        first = false;
    end
    local compact = S.cfg.camp_compact == 'true';
    local barLabel = compact and 'Hide camp bar' or 'Camp bar';
    if not first then X.fitAt(X.textW(barLabel) + X.sv(12), contentX, 12); end
    if button(barLabel, 'campbar', 0, 0, compact and 'selected' or nil) then
        setCfg('camp_compact', compact and 'false' or 'true');
    end
    tooltip('A small window with the camp\'s state and its Start / Pause, Camp on / off and Move buttons, open while you play');
end

-- (1.37, F24) the compact camp bar keeps one width at the menu's Size: room for the widest state word and the widest row of
-- buttons any camp state shows, so the buttons stay where they are (and inside the screen) as the camp goes from Ready to
-- Pulling to Paused or No camp. textW / px / sv: the measures of the window's font and Size (testable without ImGui).
-- Returns the state column's width, the window's width, and where the buttons start (from the window's left edge).
X.CAMP_BAR_ROWS = {
    { { 'Start', 66 }, { 'Move here', 76 }, { 'Camp off', 70 } },   -- (Resume / Pause have the same width as Start)
    { { 'Move here', 76 }, { 'Camp off', 70 } },
    { { 'Set camp here', 104 } },
};
function X.campBarLayout(textW, pxF, svF)
    local stateW = 0;
    for _, label in pairs(X.CAMP_STATE) do stateW = math.max(stateW, textW(label)); end
    local rowW = 0;
    for _, row in ipairs(X.CAMP_BAR_ROWS) do
        local w = 0;
        for i, b in ipairs(row) do
            -- a button is as wide as asked, or its text and padding when that is wider (ImGui grows it)
            w = w + math.max(pxF(b[2]), textW(b[1]) + 2 * svF(4)) + (i > 1 and svF(4) or 0);
        end
        rowW = math.max(rowW, w);
    end
    local pad, gap = svF(8), svF(10);
    local buttonsX = pad + stateW + gap;
    return stateW, buttonsX + rowW + pad, buttonsX;
end

-- the compact camp bar: its own small window, shown while it is switched on and the server said what the camp is doing
function X.campBar()
    if S.cfg.camp_compact ~= 'true' or not X.inWorld() then return; end
    local camp = S.camp;
    if camp == nil or camp.pullAt == nil then return; end
    -- (the server tells the menu about changes for 30 minutes after the last panel answer: ask once in a while so the bar
    --  keeps following while the menu itself stays closed)
    if not S.open[1] and now() - (S.lastAsk or 0) > 600 then ask(0); end
    local flags = 0;
    for _, name in ipairs({ 'ImGuiWindowFlags_NoResize', 'ImGuiWindowFlags_NoScrollbar', 'ImGuiWindowFlags_NoCollapse',
                            'ImGuiWindowFlags_AlwaysAutoResize', 'ImGuiWindowFlags_NoFocusOnAppearing' }) do
        flags = flags + (G(name) or 0);
    end
    if has('SetNextWindowPos') then imgui.SetNextWindowPos({ 240, 240 }, G('ImGuiCond_FirstUseEver') or 4); end
    -- (1.37, F24) the width measured last frame at this Size (the first frame sizes itself, then it stays)
    local barKey = tostring(userScale());
    local barW = X.campBarW and X.campBarW[barKey];
    if barW and has('SetNextWindowSizeConstraints') then
        pcall(imgui.SetNextWindowSizeConstraints, { barW, 0 }, { barW, 4096 });
    end
    local token = U.push(imgui, X.menu.window, X.vars());   -- (the menu's theme and metrics; popped again below)
    local open = { true };
    local fontPushed = X.pushFont();   -- (1.34) the text at this Size, laid out for it (see X.pushFont)
    local shown = imgui.Begin('Camp###sm_campbar', open, flags);
    local ok, err = pcall(function ()
        if not shown then return; end
        scaleWindow();
        local _, totalW, buttonsX = X.campBarLayout(X.textW, px, X.sv);
        X.campBarW = X.campBarW or {};
        X.campBarW[barKey] = totalW;
        local state = camp.on and (camp.paused and 'paused' or camp.state or 'idle') or 'off';
        colorText(state == 'fighting' and C.warn or (state == 'pulling' and C.good or C.dim), X.CAMP_STATE[state] or state);
        imgui.SameLine(buttonsX, 0);   -- (1.37, F24) the buttons always start here, whatever the state word
        if camp.on then
            local someonePulls = camp.puller ~= 0 or camp.botPuller ~= nil;
            if someonePulls then
                local fresh = camp.paused and (camp.pulls or 0) == 0;
                if button(camp.paused and (fresh and 'Start' or 'Resume') or 'Pause', 'barpause', 66, 0, camp.paused and 'selected' or nil) then
                    campCommand(camp.paused and (fresh and 'camp start' or 'camp resume') or 'camp pause'); camp.paused = not camp.paused;
                end
                tooltip(camp.paused and 'The puller starts pulling' or 'No new pulls (the squad still holds camp)');
                imgui.SameLine(0, 4);
            end
            if button('Move here', 'barmove', 76, 0) then X.campSetOrMove(camp); end
            tooltip('The camp moves to where you stand');
            imgui.SameLine(0, 4);
            if button('Camp off', 'baroff', 70, 0) then campCommand('camp off'); camp.on = false; end
            tooltip('They follow you again');
        else
            if button('Set camp here', 'barset', 104, 0) then campCommand('camp'); camp.on = true; end
            tooltip('Your squad holds this spot and fights whatever comes within 20 yalms of it');
        end
    end);
    S.scaledNow = false;
    imgui.End();
    X.popFont(fontPushed);
    U.pop(imgui, token);
    if not open[1] then setCfg('camp_compact', 'false'); end
    if not ok then error(err, 0); end
end

-- ---------------------------------------------------------------- the Style row (range, weapon skills) and body size
local RANGES = { 'auto', 'melee', 'mid', 'far' };
local RANGE_HELP = {
    auto  = 'The usual distance for its job (casters and ranged jobs stand back, the rest melee)',
    melee = 'Stands next to the monster',
    mid   = 'Stands about 15 yalms from the monster',
    far   = 'Stands about 20 yalms from the monster',
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

-- (1.30) Range in the first column, the two weapon skill controls together in the second (under Role and Mode)
local function styleRow(mate, opt)
    dimText('Range'); imgui.SameLine(px(X.COL.setLabel), 0);
    local range = combo('range' .. mate.slot, RANGES[(opt.range or 0) + 1], RANGES, 120, RANGE_HELP);
    if range then
        changeMate(mate, 'range', range);
        for i, r in ipairs(RANGES) do if r == range then opt.range = i - 1; end end
    end
    local stayed = X.column2(290);
    dimText('WS at'); imgui.SameLine(px(stayed and X.COL.secondCtl or X.COL.setLabel), 0);
    local when = combo('wswhen' .. mate.slot, (opt.tp or 0) > 0 and tostring(opt.tp) or 'chain', WS_WHEN, 80, WS_WHEN_HELP);
    if when then setWs(mate, opt, when, nil); end
    imgui.SameLine(0, 6);
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

-- (1.35) Position: where the mate stands in a fight (!squad position <slot> normal | behind | ta). It takes effect at once,
-- also for a mate that is out, so it leaves no "Apply" behind. Offered when the server says cap|...,matepos.
X.POSITIONS = { 'normal', 'behind', 'ta' };
X.POSITION_LABEL = { normal = 'Normal', behind = 'Behind enemy', ta = 'TA partner' };
X.POSITION_HELP = {
    normal = 'Stands where its job usually stands',
    behind = 'Stands on the monster\'s back side: melee next to it, casters and ranged at their distance. Several mates '
        .. 'with this share the space behind it, each on its own spot. Out of breath and cone attacks, but some monsters '
        .. 'hit what is behind them (tails).',
    ta = 'Stands right behind the monster, turned towards you (up to 60 degrees to either side): when you are a Thief '
        .. 'anywhere behind the monster, this mate is in line for your Trick Attack (and takes the hate it moves). '
        .. 'One mate takes this spot; others set to it stand behind.',
};
-- (1.37, F18) Rest in fights: below this MP % the mate may sit out a fight (nothing attacking it) and rest; Off = as before.
-- It takes effect at once (!squad restfight <slot> off | <n>). Offered when the server says cap|...,restfight.
X.REST_FIGHT = { '0', '20', '30', '40', '50', '60' };
X.REST_FIGHT_LABEL = { ['0'] = 'Off', ['20'] = 'MP < 20%', ['30'] = 'MP < 30%', ['40'] = 'MP < 40%', ['50'] = 'MP < 50%', ['60'] = 'MP < 60%' };
X.REST_FIGHT_HELP = { ['0'] = 'Fights through, as before (the default)' };
for _, k in ipairs({ '20', '30', '40', '50', '60' }) do
    X.REST_FIGHT_HELP[k] = 'Below ' .. k .. '% MP, with nothing attacking it, it stays out of the fight and rests (first recovery '
        .. 'after 20 s, then every 10 s). Up again at ' .. math.min(100, tonumber(k) + 20) .. '% MP, when hit or moved, when you go '
        .. 'away, or when the fight ends. Only Gambits rules marked "Wake to act" run meanwhile (it stands up for one, then rests '
        .. 'again); with the default job rules, or none marked, it does nothing while it rests.';
end
function X.restFightRow(mate, opt)
    -- (the short label fits the Settings column, as wide as "Position"; the tooltip names it in full)
    dimText('Rest'); tooltip('Rest in fights: below this MP, with nothing attacking it, the mate sits out the fight and rests. '
        .. 'While it rests it only uses Gambits rules marked "Wake to act" (a Rule Set in Gambits): without one it does '
        .. 'nothing until it is up again, so a healer should have its Cure rules marked.');
    imgui.SameLine(px(X.COL.setLabel), 0);
    local current = tostring(opt.rf or 0);
    if X.REST_FIGHT_LABEL[current] == nil then X.REST_FIGHT_LABEL[current] = 'MP < ' .. current .. '%'; end
    local pick = combo('restfight' .. mate.slot, current, X.REST_FIGHT, 120, X.REST_FIGHT_HELP, nil, X.REST_FIGHT_LABEL);
    if pick then
        enqueue(string.format('/say !squad restfight %d %s', mate.slot, pick == '0' and 'off' or pick));
        opt.rf = tonumber(pick);
        ask(1.5);
    end
    -- (1.37) the mate that is out has no rule that may run while it rests: say so beside the setting (the server's count;
    -- nothing when the mate is not out or the server does not report it)
    if opt.rfWake == 0 then
        local rs = S.rs and S.rs[mate.slot];
        local onSet = rs ~= nil and rs.state == 'set';
        imgui.SameLine(0, 8);
        colorText((opt.rf or 0) > 0 and C.warn or C.dim, onSet and 'No Wake to act rule' or 'Default job rules: no Wake');
        tooltip((onSet and 'Its Gambits Rule Set has no rule marked "Wake to act".'
                or 'This mate runs its default job rules, which have no "Wake to act" rules.')
            .. ' While it rests in a fight it then only rests: no Cure, no buffs, nothing, until it is up again. To let it act, '
            .. 'give it a Rule Set in Gambits and mark the rules it may use while resting (e.g. its Cure rules) "Wake to act".');
    end
end

function X.positionRow(mate, opt)
    dimText('Position'); imgui.SameLine(px(X.COL.setLabel), 0);
    local current = X.POSITIONS[(opt.pos or 0) + 1] or 'normal';
    local pick = combo('position' .. mate.slot, current, X.POSITIONS, 120, X.POSITION_HELP, nil, X.POSITION_LABEL);
    if pick then
        enqueue(string.format('/say !squad position %d %s', mate.slot, pick));
        for i, p in ipairs(X.POSITIONS) do if p == pick then opt.pos = i - 1; end end
        ask(1.5);
    end
end

-- body size: picked once, like at character creation
local function sizeRow(mate, opt)
    dimText('Size'); imgui.SameLine(px(X.COL.setLabel), 0);
    S.sizePick = S.sizePick or {};
    local pick = combo('size' .. mate.slot, S.sizePick[mate.slot] or 'medium', SIZES, 120);
    if pick then S.sizePick[mate.slot] = pick; end
    imgui.SameLine(0, 8);
    -- (1.30) "Save size": !squad size stores it on the server (SQUAD_SIZE), and every later call uses it. Once: the
    -- server refuses a second change, and this row is only there while no size is stored.
    if button('Save size', 'setsize' .. mate.slot, 84, 0) then
        changeMate(mate, 'size', S.sizePick[mate.slot] or 'medium');
        opt.size = ({ small = 1, medium = 2, large = 3 })[S.sizePick[mate.slot] or 'medium'];
    end
    tooltip('Saves this body size for this mate: it has it at every call from now on. It can be saved only ONCE (the server keeps it for good), so pick carefully.');
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

-- (1.27) is the Gambits editor loaded for this character? It leaves a small file while it is (Gambits.lua); looked at
-- every two seconds. Without it the Gambits button is not drawn, so no unknown command is ever sent to the game.
function X.gambitsLoaded()
    local t = now();
    if X.gsqAt == nil or t - X.gsqAt > 2 then
        X.gsqAt = t;
        -- the character the theme follower holds (it keeps the character through a moment without one, as while a
        -- zone loads); a mark that another game process left behind (a crash) does not count
        local dir = U.pref_dir(installPath(), (X.follow and X.follow.id) or U.current_identity());
        X.gsqOn = dir ~= nil and U.presence_valid(dir .. 'gambits.loaded');
    end
    return X.gsqOn == true;
end
function X.openGambits(slot)
    local chat = chatManager();
    -- (1.30) without a slot (the launcher's Gambits half): the editor opens on the mate it had last
    if chat then pcall(function() chat:QueueCommand(1, slot and string.format('/gambits show %d', slot) or '/gambits show'); end); end
    X.gsqShownGuess = { value = true, at = now() };   -- (lit at once; the editor's own word follows in a frame or two)
end
function X.closeGambits()
    local chat = chatManager();
    if chat then pcall(function() chat:QueueCommand(1, '/gambits hide'); end); end
    X.gsqShownGuess = { value = false, at = now() };
end

-- (1.34) Is the Gambits window shown right now? Gambits 0.3.9 keeps a small file (gambits.open, beside gambits.loaded) while
-- its window is shown and says "/xifogambits" whenever that changes, however it changed (its X, /gambits, a card's
-- button, this launcher). The file is read again at once on that line, and once a second otherwise. For a second after a
-- click the click's own result is shown (the command is still on its way). An older Gambits has no such file: the half
-- then never shows lit and works as an open button, as before.
X.GAMBITS_SIGNAL = '/xifogambits';
function X.gambitsShown(force)
    local t = now();
    if force or X.gsqOpenAt == nil or t - X.gsqOpenAt > 1 then
        X.gsqOpenAt = t;
        local dir = U.pref_dir(installPath(), (X.follow and X.follow.id) or U.current_identity());
        X.gsqOpen = dir ~= nil and U.presence_valid(dir .. 'gambits.open');   -- (false without the file)
    end
    local guess = X.gsqShownGuess;
    if guess and t - guess.at < 1 then return guess.value; end
    return X.gsqOpen == true;
end

-- (1.34) Options > "Show Gambits shortcut" (setting launcher_gambits; on unless it was turned off)
function X.gambitsShortcut()
    return S.cfg.launcher_gambits ~= 'false';
end

-- (1.36) Ventures: the window of the add-on "venture" (the XIFO app's Ventures screen: send squad mates off to level at
-- an exp camp while you play). The launcher copies that add-on into Ashita but does not start it with the game, so it
-- costs nothing until someone wants it. The Squad tab's Ventures button is how it is asked for:
--   not loaded       "/addon load venture", and once the add-on says it is there, "/venture show"
--   loaded           "/venture show"
--   window shown     "/venture hide" (the button is lit while the window is shown)
-- Like Gambits, the add-on keeps two small files in this character's folder: venture.loaded while it is loaded and
-- venture.open while its window is shown, each with the game process's id, and it says "/xifoventure" whenever one of
-- them changes. The files are read again on that line, and every second or two otherwise. No "/venture" line is sent
-- before venture.loaded is there, so the game is never handed a command nobody answers.
-- A file can be left behind by a game that was closed without unloading its add-ons, and Windows can give a later
-- game the same process id. Then a line goes unanswered: after two seconds AND thirty frames without an answer (both
-- add-ons draw in every frame, so a paused game does not count) the files are taken for what they are, removed, and
-- the add-on is loaded for real. The add-on puts its files back within a second should they ever be removed while it
-- is loaded, so this cannot leave the button without its add-on.
-- The button is only drawn when the add-on is in Ashita's addons folder.
X.VENTURE_SIGNAL = '/xifoventure';
X.VENTURE_WAIT = 10;        -- s: how long a click waits for the add-on to be loaded
X.VENTURE_ANSWER = 2;       -- s (and X.VENTURE_FRAMES frames): a "/venture" line without an answer by then has no add-on behind it
X.VENTURE_FRAMES = 30;
function X.ventureDir()
    return U.pref_dir(installPath(), (X.follow and X.follow.id) or U.current_identity());
end
-- is the add-on in Ashita's addons folder? (looked at every ten seconds while the Squad tab is shown)
function X.ventureThere()
    local t = now();
    if X.vtThereAt == nil or t - X.vtThereAt > 10 then
        X.vtThereAt = t;
        local base = installPath();
        local f = base and io.open(base .. 'addons/venture/venture.lua', 'r') or nil;
        if f then f:close(); end
        X.vtThere = f ~= nil;
    end
    return X.vtThere == true;
end
-- one of the add-on's two files, as it is right now (a file another game process left does not count)
function X.ventureMark(name)
    local dir = X.ventureDir();
    return dir ~= nil and U.presence_valid(dir .. name);
end
function X.ventureLoaded(force)
    local t = now();
    if force or X.vtAt == nil or t - X.vtAt > 2 then
        X.vtAt, X.vtOn = t, X.ventureMark('venture.loaded');
    end
    return X.vtOn == true;
end
-- is its window shown? (once a second; at once on the add-on's line and while a click waits for its answer)
function X.ventureShown(force)
    local t = now();
    if force or X.vtOpenAt == nil or t - X.vtOpenAt > 1 then
        X.vtOpenAt, X.vtOpen = t, X.ventureMark('venture.open');
    end
    return X.vtOpen == true;
end
function X.ventureSend(command)
    local chat = chatManager();
    if chat then pcall(function() chat:QueueCommand(1, command); end); end
end
function X.ventureShow(w, t)
    X.ventureSend('/venture show');
    w.shows, w.showAt, w.showFrame = w.shows + 1, t, w.frames;
end
function X.ventureLoad(w, t)
    X.ventureSend('/addon load venture');
    w.loads, w.shows, w.from, w.fromFrame = w.loads + 1, 0, t, w.frames;
end
-- the two files were left by an earlier game: gone, so what is there from now on is the add-on's own word
function X.ventureForget()
    local dir = X.ventureDir();
    if dir then
        os.remove(dir .. 'venture.loaded');
        os.remove(dir .. 'venture.open');
    end
    X.vtOn, X.vtOpen = false, false;
end
-- The Ventures button was clicked. Until the add-on has answered (a frame or two; a second when it has to be loaded
-- first) the button is drawn as busy and takes no further click: X.vtWant is what the click is waiting for.
function X.ventureClick()
    local t = now();
    if X.ventureDir() == nil then
        say('Ventures: log in with a character first.');
        return;
    end
    local w = { from = t, fromFrame = 0, frames = 0, shows = 0, loads = 0 };
    X.vtWant = w;
    if X.ventureShown(true) then
        w.hide = true;
        X.ventureSend('/venture hide');
    elseif X.ventureLoaded(true) then
        X.ventureShow(w, t);
    else
        X.ventureLoad(w, t);
    end
end
-- every frame while a click is waiting for its answer (the files: four times a second, and at once on the add-on's line)
function X.ventureTick(t)
    local w = X.vtWant;
    if w == nil then return; end
    w.frames = w.frames + 1;
    if not w.heard and t - (w.lookAt or -1000) < 0.25 then return; end
    w.lookAt, w.heard = t, nil;
    if X.ventureDir() == nil then X.vtWant = nil; return; end   -- (logged out in the meantime)
    local open, loaded = X.ventureMark('venture.open'), X.ventureMark('venture.loaded');
    X.vtOpen, X.vtOpenAt, X.vtOn, X.vtAt = open, t, loaded, t;
    local unanswered = function (at, frame) return t - at > X.VENTURE_ANSWER and w.frames - frame > X.VENTURE_FRAMES; end
    if w.hide then
        if not open then
            X.vtWant = nil;                                   -- its window is shut
        elseif unanswered(w.from, w.fromFrame) then
            X.ventureForget();                                -- nobody answered "/venture hide": no add-on, no window
            X.vtWant = nil;
        end
        return;
    end
    if open then
        X.vtWant = nil;                                       -- its window is shown
    elseif loaded and w.shows == 0 then
        X.ventureShow(w, t);                                  -- it has just been loaded: now its window
    elseif loaded and unanswered(w.showAt, w.showFrame) then
        if w.loads == 0 then
            X.ventureForget();                                -- nobody answered "/venture show": load it for real
            X.ventureLoad(w, t);
        else
            X.vtWant = nil;
            say('the Ventures window did not open. In chat:  /addon reload venture');
        end
    elseif not loaded and t - w.from > X.VENTURE_WAIT and w.frames - w.fromFrame > X.VENTURE_FRAMES then
        X.vtWant = nil;
        say('the Ventures add-on did not load. In chat:  /addon load venture  (it says why)');
    end
end

-- (1.32) "/xifotheme": the character's theme was just chosen, look at it now. A line between the two add-ons, never
-- typed and never sent to the game: each of them answers it and stops it, so it is harmless when the other is not
-- loaded. It carries no theme: the saved choice stays the one source.
X.THEME_SIGNAL = '/xifotheme';
function X.themeSignal()
    local chat = chatManager();
    if chat then pcall(function() chat:QueueCommand(1, X.THEME_SIGNAL); end); end
end

-- (1.27) Theme, Size and Opacity, behind the Options button of the header (they were chat commands only)
function X.pickTheme(name)
    if not U.valid(name) then return false; end
    -- the character's shared choice (Gambits follows it); at the title screen there is no character: this menu's own setting
    local shared = X.follow and X.follow:pick(name, mkdir);
    if not shared then setCfg('theme', name); end
    X.applyTheme(name);
    -- (1.32) tell the other add-on now: it reads the character's choice once, at its next frame, instead of at its
    -- next look (up to a second later, five when its window is closed)
    if shared then X.themeSignal(); end
    return true;
end
-- (the value as the lists show it; opacityOf itself stands further down, with the windows)
function X.opacityText(key)
    return tostring(math.floor(math.max(10, math.min(100, tonumber(S.cfg[key] or '100') or 100)) + 0.5));
end
function X.optionsRow()
    dimText('Theme'); imgui.SameLine(0, 8);
    local theme = combo('smtheme', X.themeName, U.THEME_ORDER, 110, nil, nil, U.THEME_NAMES);
    if theme then X.pickTheme(theme); end
    tooltip('The colours of the Squads menu, the Profile and Spells windows and the Gambits editor, for this character.');
    X.fit(170, 16);
    dimText('Size'); imgui.SameLine(0, 8);
    local pct = math.floor(userScale() * 100 + 0.5);
    if button('-', 'smsizedown', 24, 0) and pct > 75 then setCfg('scale', math.max(0.75, (pct - 10) / 100)); end
    tooltip('Smaller (75-300 %)');
    imgui.SameLine(0, 4);
    if button(pct .. '%', 'smsizereset', 56, 0) then setCfg('scale', 1); end
    tooltip('Back to 100 %');
    imgui.SameLine(0, 4);
    if button('+', 'smsizeup', 24, 0) and pct < 300 then setCfg('scale', math.min(3, (pct + 10) / 100)); end
    tooltip('Larger (75-300 %)');
    X.fit(330, 16);
    dimText('Opacity'); imgui.SameLine(0, 8);
    local steps = { '100', '90', '75', '50', '25', '10' };
    dimText('button'); imgui.SameLine(0, 6);
    local ob = combo('smopbutton', X.opacityText('button_opacity'), steps, 64);
    if ob then setCfg('button_opacity', ob); end
    tooltip('How see-through the Squads button is (solid under the mouse)');
    imgui.SameLine(0, 10);
    dimText('menu'); imgui.SameLine(0, 6);
    local om = combo('smopmenu', X.opacityText('menu_opacity'), steps, 64);
    if om then setCfg('menu_opacity', om); end
    tooltip('How see-through the menu\'s background is');
    -- (1.34) the launcher's Gambits half: on by default; off leaves a Squads-only button at the same place
    X.fit(190, 16);
    local shortcut = X.gambitsShortcut();
    if has('Checkbox') then
        local box = { shortcut };
        if imgui.Checkbox('Show Gambits shortcut##smgsqshortcut', box) and box[1] ~= shortcut then setCfg('launcher_gambits', box[1] and 'true' or 'false'); end
    elseif button((shortcut and '[x] ' or '[ ] ') .. 'Show Gambits shortcut', 'smgsqshortcut', 0, 0, shortcut and 'selected' or nil) then
        setCfg('launcher_gambits', shortcut and 'false' or 'true');
    end
    tooltip('The Gambits half of the Squads | Gambits launcher. Off: a Squads button only, at the same place. /gambits and the Gambits buttons on the mates stay.');
    if has('Separator') then imgui.Separator(); end
end

-- (1.28) One mate's card. What is needed every day is always there, in the same place on every card:
--   row 1  name | jobs and levels | out / away | Call or Dismiss, the call timer next to it (muted), Apply when needed
--   row 2  Rules: what the mate runs, as the server reports it (only from a server that does)
--   row 3  Actions | Gambits | Gear | Profile | Food | Settings, then what the settings are, in a few muted words
-- Role, Mode, Range, the weapon skill choices and the jobs are behind Settings: they are changed rarely. Nothing
-- about them changed but the place. The card is as high as its content was in the last frame (X.card / X.cardEnd).
X.COL = { jobs = 110, status = 236, action = 322, label = 52, setLabel = 64, second = 200, secondCtl = 250 };   -- (1.35) setLabel: the Settings and Jobs rows' first column, wide enough for "Position"
-- (1.29) Calling. A mate is "being called" from the click on Call (or Call all, or an Apply that sends it off and
-- calls it again) until the server's squad list says it is out. The server has no state in between (its list says
-- out or not), so there is no "on its way" to show: exactly one word stands on the card, Away, Calling... or Out.
-- It ends without the mate when 12 seconds pass, or at once when the list comes back with a call timer for that mate
-- (the server refused the call: it says why in chat).
function X.markCalling(slot, delay)
    X.callAt = X.callAt or {};
    X.callAt[slot] = now() + (delay or 0);
end
function X.calling(mate, wait)
    if mate == nil or mate.out then return false; end
    local slot = mate.slot;
    -- sent for by this menu's button (X.callAt) or by any "!squad call" / "!squad reapply" line that passed (rsTouch)
    local at = math.max(X.recalledAt(slot), (X.callAt and X.callAt[slot]) or -1000);
    if now() - at >= 12 then return false; end
    local verb = X.recallVerb and X.recallVerb[slot];
    if verb ~= 'reapply' and (wait or 0) > 0 and now() - at > 1 then return false; end   -- (the server answered with a call timer: refused)
    return true;
end
-- where Call / Dismiss stand on every card: after the longest status word, whatever the font
function X.actionX()
    return math.max(px(X.COL.action), px(X.COL.status) + X.textW('Calling...') + X.sv(14));
end

function X.mateCard(mate)
    local slot = mate.slot;
    local opt = S.opts and S.opts[slot];
    local open = S.more[slot] == true;
    local jobsOpen = S.jobsOpen ~= nil and S.jobsOpen[slot] == true;
    local waitSecs = S.showAdvanced and S.adv and S.adv.delay[slot];
    local rs = S.rs and S.rs[slot];   -- (1.26n) the Rules line: only from a server that reports it
    -- the first frame's height; after that the card is as high as its content was
    local height = 62 + (rs and 23 or 0) + 20;
    if jobsOpen then height = height + 4 + 23; end
    if open then height = height + 4 + 23 + (opt and 23 or 0) + ((opt and opt.size == 0) and 23 or 0); end
    if waitSecs then height = height + 25; end
    local cardId = '##sm_mate' .. slot;
    local cardOpen, cardBegan = X.card(cardId, px(height));
    if cardOpen then
        local wait = S.readyAt and S.readyAt[slot] and (S.readyAt[slot] - os.time()) or 0;
        local calling = X.calling(mate, wait);
        -- ---- row 1
        local name = X.clip and X.clip(mate.name, px(X.COL.jobs - 8)) or mate.name;
        colorText(C.gold, name);
        if name ~= mate.name then tooltip(mate.name); end
        imgui.SameLine(px(X.COL.jobs), 0);
        local jobs = string.format('%s %d', mate.main, mate.mainLevel);
        if mate.sub ~= '-' then jobs = jobs .. string.format(' / %s %d', mate.sub, mate.subLevel); end
        colorText(C.text, jobs);
        imgui.SameLine(px(X.COL.status), 0);
        -- (1.29) one word: Out (the server's list says so), Calling... (sent for, not there yet), Away
        if mate.out then
            colorText(C.good, 'Out');
        elseif calling then
            colorText(C.warn, 'Calling...');
            tooltip('This mate was sent for and is not here yet. The word changes to Out when the server says it has come.');
        else
            colorText(C.dim, 'Away');
        end
        -- Call and Dismiss in the same place and of the same width, so the row does not move while a mate comes
        imgui.SameLine(X.actionX(), 0);
        if mate.out then
            -- (1.13) out: send just this one off, and how long before a dismiss and call works straight away
            if button('Dismiss', 'dismiss' .. slot, 70, 0) then
                enqueue('/say !squad dismiss ' .. slot); ask(1.5);
                if X.callAt then X.callAt[slot] = nil; end
            end
            tooltip('Sends only this mate off; the others stay');
            if wait > 0 then
                imgui.SameLine(0, 8);
                colorText(C.faint, string.format('recall in %d:%02d', math.floor(wait / 60), wait % 60));
                tooltip('If you dismiss this mate now, the call timer lets you call them again after this');
            end
        elseif calling then
            button('Call', 'call' .. slot, 70, 0, 'busy');   -- (there, greyed and not clickable: it was pressed)
            tooltip('Already called: waiting for the server to say that this mate is out.');
        elseif wait > 0 then
            colorText(C.faint, string.format('ready in %d:%02d', math.floor(wait / 60), wait % 60));
            tooltip('The call timer: this mate can be called again then (the launcher\'s Rates tab sets how long)');
        else
            if button('Call', 'call' .. slot, 70, 0) then
                enqueue('/say !squad call ' .. slot); ask(3);
                X.markCalling(slot);
            end
        end
        -- (1.27) Apply for this mate alone
        if X.pending(mate) then
            X.fit(64, 10);
            if button('Apply', 'applyone' .. slot, 64, 0, 'go') then X.applyMate(mate); end
            tooltip(X.applyTip(mate));
        end

        -- ---- row 2: Rules (1.26n: what this mate runs now, the server's report; the selected Rule Set; Apply needed)
        -- (1.29) while a mate is being called the line says what it is EXPECTED to run ("Next call: ..."), in the
        -- muted colour; what it runs ("Gambits: ...", green) is shown only on the server's word, once it is out
        local rsStale = rs ~= nil and ROLE_INFO.rsStale(slot);
        if rs then
            dimText('Rules'); imgui.SameLine(px(X.COL.label), 0);
            local expecting = calling and rs.state == 'off';
            local parts, rulesTip = ROLE_INFO.rules(mate, rs, rsStale and not expecting, expecting);
            local whole, width = {}, 0;
            for _, part in ipairs(parts) do whole[#whole + 1] = part[2]; width = width + X.textW(part[2]); end
            local left = U.avail(imgui);
            if left ~= nil and width > left then
                -- (1.27) a long Rule Set name: the whole line wraps instead of running out of the card
                wrapped(table.concat(whole), C[parts[#parts][1]] or C.text);
                ROLE_INFO.tip(rulesTip);
            else
                for i, part in ipairs(parts) do
                    if i > 1 then imgui.SameLine(0, 0); end
                    colorText(C[part[1]] or C.text, part[2]);
                    ROLE_INFO.tip(rulesTip);
                end
            end
        end

        -- ---- row 3: the everyday buttons
        -- one click: all four action switches (melee, ranged, abilities, magic) for this mate
        S.act = S.act or {};
        -- the state is the server's: all four switches off = OFF (the mate list carries the mask). Older servers: what you last clicked.
        local actOn;
        if mate.switches ~= nil then actOn = mate.switches ~= 0; else actOn = S.act[slot] ~= false; end
        -- while any Actions change is on its way (sent, not yet confirmed by the server) every Actions button is greyed out
        local busy = S.want ~= nil and next(S.want) ~= nil;
        if busy then
            button(S.want[slot] and 'Working...' or (actOn and 'Actions ON' or 'Actions OFF'), 'act' .. slot, 96, 0, 'busy');
        elseif button(actOn and 'Actions ON' or 'Actions OFF', 'act' .. slot, 96, 0, actOn and 'on' or nil) then
            S.want = S.want or {}; S.want[slot] = actOn and 'off' or 'on'; S.tries = S.tries or {}; S.tries[slot] = 0;
            S.wantAt = now();
            S.act[slot] = not actOn;
            enqueue(string.format('/say !squad sw %d all %s', slot, actOn and 'off' or 'on'));
            S.actKick = now() + 2.5;   -- one `!actions` check after the change settles (see pump)
            -- turning a mate ON: her spells and abilities only take the new switches when she is called, so send her off and call her
            -- again (each line waits its turn in the queue). Turning OFF needs no recall: the server stops her at once.
            if not actOn and mate.out then
                enqueue('/say !squad dismiss ' .. slot, 2.5);
                enqueue('/say !squad call ' .. slot, 9);
            end
            ask(4);
        end
        tooltip('OFF means off: the mate stops fighting, following, Sneak Attack, eating and casting. ON also sends this mate off and calls her again (about 12 seconds), because spells and abilities only take the switches at a call. The button shows the real state from the server.');
        -- (1.29) Jobs is a button of its own again: the main and the support job, right on the card
        X.fit(64);
        if button(jobsOpen and 'Jobs v' or 'Jobs >', 'jobs' .. slot, 64, 0, jobsOpen and 'selected' or nil) then
            S.jobsOpen = S.jobsOpen or {};
            S.jobsOpen[slot] = not jobsOpen;
        end
        tooltip('Change this mate\'s main and support job');
        -- (1.27) the way to its Rule Sets
        if rs and X.gambitsLoaded() then
            X.fit(72);
            if button('Gambits', 'gsq' .. slot, 72, 0) then X.openGambits(slot); end
            tooltip('Opens the Gambits editor on ' .. mate.name .. '\'s Rule Sets.');
        end
        X.fit(52);
        if button('Gear', 'gear' .. slot, 52, 0) then openSheet(slot, 'gear'); end
        tooltip('Opens his profile window on Gear: what he wears, change a piece, lockstyle');
        X.fit(64);
        if button('Profile', 'sheet' .. slot, 64, 0) then openSheet(slot, 'stats'); end
        tooltip('Opens his profile window: stats, HP/MP/TP, haste and jobs');
        -- (1.26f, the user) the food menu: the game's own menu opens, as for !squad food <slot>
        X.fit(52);
        if button('Food', 'food' .. slot, 52, 0) then enqueue('/say !squad food ' .. slot); end
        tooltip('Choose what this mate eats. The game opens a menu: "As it comes" (its own pick by job and level) or a food of your choice. A food is unlocked once for about what it costs on the auction house, then it is free for every mate.');
        -- (1.29) the button says Settings in both states; the mark after the word says whether they are open
        X.fit(88);
        if button(open and 'Settings v' or 'Settings >', 'more' .. slot, 88, 0, open and 'selected' or nil) then S.more[slot] = not open; end
        tooltip('Role, Mode, Range, weapon skills and body size');

        -- what the settings are, while they are folded away
        if not open then
            -- Role and Mode first, each with its own help under the mouse (the same texts as in their lists)
            local roleText, modeText = 'Role ' .. tostring(mate.role), '  \194\183  Mode ' .. tostring(mate.mode);
            U.same_if_fits(imgui, X.textW(roleText .. modeText) + X.sv(4), 12);
            colorText(C.faint, roleText);
            ROLE_INFO.tip(ROLE_INFO.TIPS[mate.role]);
            imgui.SameLine(0, 0);
            colorText(C.faint, modeText);
            ROLE_INFO.tip(MODE_HELP[mate.mode]);
            local bits = {};
            if opt then
                bits[#bits + 1] = 'Range ' .. (RANGES[(opt.range or 0) + 1] or 'auto');
                if X.caps and X.caps.matepos and (opt.pos or 0) > 0 then   -- (1.35) only when not Normal
                    bits[#bits + 1] = X.POSITION_LABEL[X.POSITIONS[opt.pos + 1] or 'normal'] or '';
                end
                bits[#bits + 1] = 'WS ' .. ((opt.tp or 0) > 0 and ('at ' .. opt.tp) or 'chain') .. (opt.ws and (', ' .. tostring(opt.ws):gsub('_', ' ')) or '');
            end
            if #bits > 0 then
                local summary = '  \194\183  ' .. table.concat(bits, '  \194\183  ');
                U.same_if_fits(imgui, X.textW(summary) + X.sv(4), 0);
                colorText(C.faint, summary);
                tooltip((X.caps and X.caps.matepos) and 'Settings opens these: Role, Mode, Range, Position and weapon skills.'
                    or 'Settings opens these: Role, Mode, Range and weapon skills.');
            end
        end
        -- (role clarity) a quiet gold note when the Role restricts this job's default healing (ROLE_INFO.note)
        local note, noteRole, noteJob = ROLE_INFO.note(mate);
        if note and not (rs and rs.state == 'set' and not rsStale) then   -- (1.26n: not while a Rule Set runs)
            local noteText = '(i) ' .. noteJob .. ' - Role: ' .. noteRole;
            U.same_if_fits(imgui, X.textW(noteText) + X.sv(4), 12);
            colorText(C.gold, noteText);
            ROLE_INFO.tip(note);
        end

        if waitSecs then
            dimText('Wait'); imgui.SameLine(px(X.COL.label), 0);
            local w = combo('wait' .. slot, tostring(waitSecs), DELAYS, 70);
            if w then
                changeMate(mate, 'delay', w);
                S.adv.delay[slot] = tonumber(w);
            end
            X.fit(210, 8);
            dimText('seconds before joining a fight');
        end

        -- ---- Jobs: the main and the support job (the server checks them, as it always did)
        if jobsOpen then
            X.group();
            local jobTip = 'A job your character has not unlocked is refused by the server (it says so in chat).';
            dimText('Job'); imgui.SameLine(px(X.COL.setLabel), 0);
            local jl = (S.jobLevels or {})[slot] or {};
            local jobLabels = {};
            for _, j in ipairs(JOBS) do if jl[j] then jobLabels[j] = string.format('%s (%d)', j, jl[j]); end end
            local job = combo('job' .. slot, mate.main, JOBS, 120, nil, nil, jobLabels);
            tooltip('This mate\'s main job. ' .. jobTip);
            if job then changeMate(mate, 'job', job); end
            -- (1.31) Sub in the second column: its name where Mode and WS at begin, its list where theirs begin
            local subStayed = X.column2(180);
            dimText('Sub'); imgui.SameLine(px(subStayed and X.COL.secondCtl or X.COL.setLabel), 0);
            local subs = { 'none' };
            for _, j in ipairs(JOBS) do if j ~= mate.main then subs[#subs + 1] = j; end end
            local sub = combo('sub' .. slot, mate.sub == '-' and 'none' or mate.sub, subs, 120, nil, nil, jobLabels);
            tooltip('This mate\'s support job. ' .. jobTip);
            if sub then changeMate(mate, 'sub', sub); end
        end

        -- ---- Settings: what is changed rarely. (1.30) a thin line under the buttons, then two columns: Role | Mode,
        -- Range | the weapon skill controls; Size and its button on a row of their own
        if open then
            if has('Separator') then imgui.Separator(); end
            dimText('Role'); imgui.SameLine(px(X.COL.setLabel), 0);
            local role = combo('role' .. mate.slot, mate.role, ROLES, 120, ROLE_INFO.TIPS, ROLE_INFO.tip);
            if role then changeMate(mate, 'role', role); end
            local stayed = X.column2(180);
            dimText('Mode'); imgui.SameLine(px(stayed and X.COL.secondCtl or X.COL.setLabel), 0);
            local mode = combo('mode' .. slot, mate.mode, MODES, 120, MODE_HELP, ROLE_INFO.tip);
            if mode then changeMate(mate, 'mode', mode); end
            if opt then styleRow(mate, opt); end
            if opt and X.caps and X.caps.matepos then X.positionRow(mate, opt); end
            if opt and X.caps and X.caps.restfight then X.restFightRow(mate, opt); end
            if opt and opt.size == 0 then sizeRow(mate, opt); end
        end
    end
    X.cardEnd(cardId, cardBegan, cardOpen);
end


local function squadTab()
    -- (1.28) the commands in groups, each with its caption in the same column: the squad as a whole, the fight, the
    -- camp, and what is set up once. Every button has the usual height (only the tabs are higher).
    X.rowLabel('Squad');
    if button('Call all', 'callall', 76, 0) then
        enqueue('/say !squad call all'); ask(3);
        local k = 0;
        for _, m in ipairs(S.mates) do
            local w = S.readyAt and S.readyAt[m.slot] and (S.readyAt[m.slot] - os.time()) or 0;
            if not m.out and w <= 0 then X.markCalling(m.slot, k * 1.5); k = k + 1; end   -- (the server brings them one after another)
        end
    end
    tooltip('Bring every squad mate out, one after another');
    X.fit(92);
    if button('Dismiss all', 'dismiss', 92, 0) then enqueue('/say !squad dismiss'); ask(1.5); X.callAt = nil; end
    X.fit(68);
    if button('Refresh', 'refresh', 68, 0) then ask(); X.dropGear(); end
    tooltip('Ask the server for your squad again');
    -- (1.36) Ventures: loads the venture add-on when it is not loaded, then shows its window; lit while it is shown
    if X.ventureThere() then
        X.fit(76);
        local waiting = X.vtWant ~= nil;
        local shown = not waiting and X.ventureShown();
        if button('Ventures', 'ventures', 76, 0, waiting and 'busy' or (shown and 'selected' or nil)) then X.ventureClick(); end
        tooltip(waiting and (X.vtWant.hide and 'Shutting the Ventures window...' or 'Opening the Ventures window...')
            or (shown and 'Shut the Ventures window. Mates that are away stay on their venture.'
            or 'Send squad mates off to level at an exp camp while you play, like in the XIFO app.\nOpens the Ventures window (its add-on is loaded the first time you click).'));
    end
    X.fit(60, 12);
    dimText(#S.mates == 1 and '1 mate' or (#S.mates .. ' mates'));

    -- (1.26j, Hasuko: "I'm a WHM. I shouldn't have to pull my weapon"; Yenkei) send the squad at your target while
    -- you stay out of the fight. The server reads your target itself, so nothing is drawn and nothing stands you up.
    X.rowLabel('Fight');
    if button('Attack my target', 'sqattack', 124, 0) then enqueue('/say !squad attack'); end
    tooltip('Your squad attacks the monster you have targeted: they fight, you stay out of it. You do not draw your weapon:\nstay back, sit and rest, heal. Bot players in your party go in too.\nIn a macro:  /say !squad attack');
    X.fit(52);
    if button('Stop', 'sqstop', 52, 0) then enqueue('/say !squad stop'); end
    tooltip('Calls your squad back from that fight.  In a macro:  /say !squad stop');
    if S.engage then
        -- (1.28) said as what it is (squad.lua: TrustEngageType 1 = as soon as you engage, 2 = after your first swing)
        X.fit(190, 12);
        local first = S.engage == 'first';
        if button(first and 'Engage: when you engage' or 'Engage: after first hit', 'engage', 178, 0) then
            enqueue('/say !squad engage ' .. (first and 'normal' or 'first'));
            S.engage = first and 'normal' or 'first';
            ask(1.5);
        end
        tooltip(first and 'When your mates join a fight: as soon as you engage (draw your weapon on a monster), without waiting for your first swing.\nClick: they wait for your first hit, like retail trusts.'
            or 'When your mates join a fight: after your first hit lands or misses, like retail trusts.\nClick: they join as soon as you engage, before your first swing.');
    end

    campRow();

    local setup = false;
    local function setupRow(w)
        if setup then X.fit(w); else X.rowLabel('Setup'); setup = true; end
    end
    if S.autoEquip ~= nil then
        setupRow(128);
        local on = S.autoEquip == true;
        if button(on and 'Auto-equip: on' or 'Auto-equip: off', 'autoequip', 128, 0, on and 'on' or nil) then
            enqueue('/say !squad autoequip ' .. (on and 'off' or 'on'));
            S.autoEquip = not on;
            ask(1.5);
        end
        -- (1.26g, FalconX51; the user: one button, lit while it is on) best gear once = on, then off again
        tooltip(on and 'Lit: your mates wear the best gear you gave the squad and pick again each time they are called.\nClick to switch it off: they keep what they wear now, and you can change any piece by hand.\nWith the launcher\'s "Squad gets all gear" on, the choice is from everything their jobs can wear.'
            or 'Click: every mate puts on the best gear you gave the squad for its job and level, and the button lights up.\nFor best gear just once, click it again: the gear stays and the choice is yours again.\nWith the launcher\'s "Squad gets all gear" on, the choice is from everything their jobs can wear.');
    end
    if S.adv then
        setupRow(84);
        if button('Advanced', 'advanced', 84, 0, S.showAdvanced and 'selected' or nil) then S.showAdvanced = not S.showAdvanced; end
        tooltip('Follow distance, resting at camp, call order and each mate\'s wait before fighting');
    end
    if S.behs and #S.behs > 0 then
        setupRow(160);
        local allOff = true;
        for _, b in ipairs(S.behs) do if b.state ~= 'off' then allOff = false; end end
        if button(allOff and 'Forwarded to Gambits' or 'Forward to Gambits', 'behall', 160, 0, allOff and 'on' or nil) then
            enqueue('/say !squad behave all ' .. (allOff and 'on' or 'off'));
            for _, b in ipairs(S.behs) do b.state = allOff and 'on' or 'off'; end
            ask(1.5);
        end
        tooltip(allOff and 'The built-in squad AI is off. Everything is set in Gambits. Click to take it back.'
            or 'Turns the built-in squad AI off for every job so each mate runs on what you set in Gambits.');
    end
    if S.adv and S.showAdvanced then
        gap(2);
        advancedPanel();
    end

    -- (1.27) the banner shows while a mate that is out has something only its next call applies: what the server
    -- reports (a Rule Set chosen or saved in Gambits, a Role or job change: the Rules line says "Apply needed") or a
    -- change this menu sent that the server does not report (gear, sub job, range...). It goes when the mate was called.
    local waiting = 0;
    for _, mate in ipairs(S.mates) do if X.pending(mate) then waiting = waiting + 1; end end
    if waiting > 0 then
        gap(2);
        colorText(C.warn, 'Changes take effect when your mates are called again.');
        X.fit(96, 10);
        if button('Apply now', 'apply', 96, 0, 'go') then applyNow(); end
        tooltip('Dismisses the squad and calls everyone again.'
            .. ((X.caps and X.caps.reapply1) and ' To call only one mate again, use Apply on its card.' or ''));
    end
    X.group();

    local open, began = beginChild('##sm_squadlist', 0, -2, false);
    if open then
        if #S.mates == 0 then
            gap(20);
            dimText(now() < S.waitUntil and '   Asking the server...' or '   No squad mates yet (or no answer yet). Press Refresh.');
            dimText('   Make one in chat:  !squad new Bob WAR');
        end
        for _, mate in ipairs(S.mates) do
            X.mateCard(mate);
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
        tooltip(ROLE_INFO.DUO[role]);
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

    if button('Reset rows', 'resetrows', 110, 0) then queueDuo({ reset = true }); end
    tooltip('Puts this job\'s rows back to the normal sheet (the engine keeps a .bak), then re-applies the profile');
    imgui.SameLine(0, 8);
    if button('Engine window', 'titanui', 120, 0) and not old then queueDuo({ ops = { 'titanui' } }); end
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

-- (1.23, 2026-11-19) the rules for your own character moved from the addon "Gambits" to "autobox" (the name Gambits
-- now belongs to the squad Rule Set editor). autobox is not loaded at start: AUTO loads it, and /autobox commands are
-- only sent while it is loaded (it keeps a flag file while it runs), so nobody sees a command error for it.
local function autoboxLoaded()
    local ok, found = pcall(function ()
        local base = AshitaCore:GetInstallPath();
        if not base:match('[/\\]$') then base = base .. '\\'; end
        local f = io.open(base .. 'config\\addons\\Gambits\\autobox_loaded.flag', 'r');
        if f then f:close(); return true; end
        return false;
    end);
    return ok and found == true;
end

-- (1.26c, 2026-11-21: Altair's Monk used Boost by itself while MY AUTO showed OFF) autobox keeps its own master switch per
-- character, across sessions, and MY AUTO switches it on. When the menu then wants it off again (MY AUTO off, Stop, or a new
-- session after the game was closed with MY AUTO on) while autobox is not running, no /autobox off could be sent: the switch
-- stayed on, and the next time autobox was loaded (by hand, for its Parser or EXP Watch) your rules ran while this menu said
-- OFF. That /autobox off is now kept, for that character only and across restarts, until autobox runs while that character
-- is logged in. It is dropped when you switch autobox yourself (/autobox on|off|toggle: your choice wins), when you switch
-- MY AUTO on, or when autobox's own saved switch for the character is already off.
-- autobox's flag file holds the time it was loaded; one older than this menu's own load is left over from an earlier game.
-- Known limit: both game windows share that flag file, so with the second window's autobox running the main window cannot
-- tell whether its own autobox runs.
local function autoboxStamp()
    local ok, stamp = pcall(function ()
        local base = AshitaCore:GetInstallPath();
        if not base:match('[/\\]$') then base = base .. '\\'; end
        local f = io.open(base .. 'config\\addons\\Gambits\\autobox_loaded.flag', 'r');
        if not f then return nil; end
        local text = f:read('*l');
        f:close();
        return tonumber(text);
    end);
    if not ok or not stamp then return nil; end
    if S.menuLoadedAt and stamp < S.menuLoadedAt - 30 then return nil; end   -- (the start script loads its addons within seconds)
    return stamp;
end

-- The kept /autobox off is one small file per character: config/addons/servermenu/autobox_off_owed_<name>.flag (a file of its
-- own, not settings.cfg: both game windows load this menu, and each rewrites the whole settings file).
-- owedAutoboxOff(name) -> is one kept;  owedAutoboxOff(name, true|false) -> keep it / drop it.
local function owedAutoboxOff(name, keep)
    local base = installPath();
    if not base or not name or name == '' or name == 'default' then return false; end
    local path = base .. 'config/addons/servermenu/autobox_off_owed_' .. name .. '.flag';
    if keep == nil then
        local f = io.open(path, 'r');
        if f then f:close(); return true; end
        return false;
    elseif keep then
        mkdir(base .. 'config/addons/servermenu/');
        local f = io.open(path, 'w');
        if f then f:write(tostring(os.time())); f:close(); end
        return true;
    end
    os.remove(path);
    return false;
end

-- autobox's own saved master switch for the character logged in now (its characters/<name>_<id>/switches.lua):
-- true, false, or nil when it cannot be read
local function savedAutoboxOn()
    local ok, on = pcall(function ()
        local party = AshitaCore:GetMemoryManager():GetParty();
        local stem = tostring(party:GetMemberName(0) or ''):gsub('[^%w_%-]', '_');
        local f = io.open(installPath() .. 'config/addons/Gambits/characters/' .. stem .. '_' .. tostring(party:GetMemberServerId(0)) .. '/switches.lua', 'r');
        if not f then return nil; end
        local value = f:read('*a'):match('Player%s*=%s*(%a+)');
        f:close();
        if value == 'true' then return true; elseif value == 'false' then return false; end
        return nil;
    end);
    if ok then return on; end
    return nil;
end

-- drops the /autobox off lines still waiting in the queue (you switched autobox yourself: your choice wins)
local function dropQueuedAutoboxOff()
    for i = #S.queue, 1, -1 do if S.queue[i].command == '/autobox off' then table.remove(S.queue, i); end end
end

-- the kept /autobox off for this character, sent once autobox runs (and a character exists: before that autobox refuses it)
local function sendOwedAutoboxOff(name)
    if myAutoOn() or not owedAutoboxOff(name) or not autoboxStamp() then return; end
    owedAutoboxOff(name, false);
    if savedAutoboxOn() == false then return; end   -- already off (switched some other way): nothing to send
    enqueue('/autobox off', 0.5, name);
    enqueue('/autobox off', 3.0, name);
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

    sendOwedAutoboxOff(name)

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

    local lastSession = probe:read('*l')   -- what MY AUTO was when this character's last session ended
    probe:close()

    if not myAutoOn() then
        -- Gambits keeps its per-character master switch across sessions, and the
        -- startup script's /autobox off runs before a character exists, where it
        -- is refused. Send it again now that there is one.
        if autoboxLoaded() then
            enqueue('/autobox off', 0.5, name)   -- (1.26c: for this character only)
            enqueue('/autobox off', 3.0, name)
        end
        -- (1.26c) the game was closed with MY AUTO on: keep the off for this character until autobox runs; if it runs
        -- now, the two lines above are that off
        if autoboxStamp() then
            owedAutoboxOff(name, false)
        elseif lastSession == 'on' then
            owedAutoboxOff(name, true)
        end
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
        owedAutoboxOff(auto_flag_character(), false);   -- (1.26c) MY AUTO on: nothing is kept back any more
        enqueue('/addon load autobot', 0.1);
        enqueue('/addon load autobox', 0.3);   -- (its rules; loading it twice only prints a notice)
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
        enqueue('/autobox on', 2.8);
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
        if autoboxLoaded() then enqueue('/autobox off', 0, auto_flag_character()); end   -- (1.26c: for this character only)
        if not autoboxStamp() then owedAutoboxOff(auto_flag_character(), true); end   -- (1.26c) autobox not running: send it when it is
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
    if open then
        X.syncTheme(now(), true);   -- (1.32) a menu that opens has the character's theme in its first frame
        ask();
    end
end

-- (1.26g, K-Andy) how see-through the Squads button and the menu's background are: 10-100 percent.
-- (1.26i) It has to stand ABOVE menuWindow: it stood below it, so the menu called a function that did not exist
-- yet and the Squads menu never opened (Hasuko: a red 'Missing PopStyleColor' box after the v0.3.0 patch).
local function opacityOf(key)
    local v = tonumber(S.cfg[key] or '100') or 100;
    return math.max(10, math.min(100, v)) / 100;
end

-- (1.32) the background of a card or panel in the menu at the menu's opacity: the theme's own colour, its alpha times
-- the opacity (one table per theme and value). Text, buttons, lists and the title bar are not made see-through.
function X.childBg(op)
    local key = tostring(X.themeName) .. ':' .. tostring(op);
    if X.childBgKey ~= key then
        local base = nil;
        for _, item in ipairs(X.menu.window) do if item[1] == 'ImGuiCol_ChildBg' then base = item[2]; end end
        X.childBgKey, X.childBgColor = key, base and { base[1], base[2], base[3], (base[4] or 1) * op } or nil;
    end
    return X.childBgColor;
end

local function menuWindow()
    if not S.open[1] then return; end
    imgui.SetNextWindowSize({ px(620), px(560) }, G('ImGuiCond_FirstUseEver') or 4);
    if has('SetNextWindowSizeConstraints') then imgui.SetNextWindowSizeConstraints({ px(600), px(420) }, { px(1200), px(1000) }); end
    -- (1.27) the theme's colours and the shared metrics (xifo_ui: the Gambits editor's padding, spacing and rounding).
    -- Whatever is pushed is popped again, also when something in the window fails (1.26g left 19 pushes open).
    local token = U.push(imgui, X.menu.window, X.vars());
    -- (1.28) ImGui's own title bar, as the Gambits window and the Profile have it: the same height, the same close
    -- button, the same colours from the theme. (Until 1.27 this window drew its own heading and an X button.) The
    -- window's ImGui name is new with it, so it opens once at its first-use place and size.
    local flags = (G('ImGuiWindowFlags_NoCollapse') or 0);
    -- the menu's opacity: the window's background, and (1.32) the cards and panels in it. Until 1.31 only the window's
    -- background followed it: at 10 % the cards kept their 80 %.
    local op = opacityOf('menu_opacity');
    local faded = nil;
    if has('SetNextWindowBgAlpha') and op < 1 then
        imgui.SetNextWindowBgAlpha(op);
        local bg = X.childBg(op);
        if bg then faded = U.push(imgui, { { 'ImGuiCol_ChildBg', bg } }); end
    end
    local fontPushed = X.pushFont();   -- (1.34) the text at this Size, laid out for it (see X.pushFont)
    local shown = imgui.Begin('Squads - XI: Forever Offline###sm_menu', S.open, flags);
    local ok, err = pcall(function ()
        if not shown then return; end
        scaleWindow();
        -- the main tabs, and Options at the right end of their row (Theme, Size, Opacity)
        for i, name in ipairs(TABS) do
            if i > 1 then imgui.SameLine(0, X.sv(4)); end
            if X.tab(name, 'tab' .. name, S.tab == name) then setTab(name); end
        end
        X.right(72);
        if button('Options', 'options', 72, U.SIZE.tab, S.showOptions and 'selected' or nil) then S.showOptions = not S.showOptions; end
        tooltip('Theme, size and opacity of the Squads windows');
        if S.showOptions then X.optionsRow(); end
        if has('Separator') then imgui.Separator(); end
        gap(2);
        local draw = TAB_DRAW[S.tab] or squadTab;
        draw();
    end);
    S.scaledNow = false;
    imgui.End();
    if faded then U.pop(imgui, faded); end
    X.popFont(fontPushed);
    U.pop(imgui, token);
    if not ok then error(err, 0); end
end

-- ---------------------------------------------------------------- the small FFXI button
local function xy(a, b)
    if type(a) == 'table' then return tonumber(a[1] or a.x), tonumber(a[2] or a.y); end
    return tonumber(a), tonumber(b);
end

-- (1.30) Is the character in the world? Logged in (Ashita's player: login status 2, as its settings library asks),
-- not between two zones, and with a name and server id. At the title screen, at character selection and while a zone
-- loads this is false. A binding without those calls: the name and id alone decide, as they do for the theme.
function X.inWorld()
    local ok, ready = pcall(function ()
        local player = AshitaCore:GetMemoryManager():GetPlayer();
        if player:GetLoginStatus() ~= 2 then return false; end
        if type(player.GetIsZoning) == 'function' then
            local z = player:GetIsZoning();
            if z == true or (type(z) == 'number' and z ~= 0) then return false; end
        end
        return U.current_identity() ~= nil;
    end);
    if not ok then return U.current_identity() ~= nil; end
    return ready == true;
end

-- the right-click menu of the launcher (on either half)
function X.launcherMenu(id)
    if has('BeginPopupContextItem') and imgui.BeginPopupContextItem(id) then
        if has('MenuItem') then
            if imgui.MenuItem(S.cfg.button_locked == 'true' and 'Unlock position' or 'Lock position') then
                setCfg('button_locked', S.cfg.button_locked == 'true' and 'false' or 'true');
            end
            for _, pct in ipairs({ 100, 75, 50, 25 }) do
                if imgui.MenuItem(string.format('Opacity %d%%%s', pct, tonumber(S.cfg.button_opacity or '100') == pct and '   (now)' or '')) then
                    setCfg('button_opacity', pct);
                end
            end
            if imgui.MenuItem(X.gambitsShortcut() and 'Hide Gambits shortcut' or 'Show Gambits shortcut') then   -- (1.34)
                setCfg('launcher_gambits', X.gambitsShortcut() and 'false' or 'true');
            end
            if imgui.MenuItem('Hide button  (/menu button brings it back)') then
                setCfg('button_hidden', 'true');
                say('button hidden. /menu opens the menu, /menu button shows the button again.');
            end
        end
        imgui.EndPopup();
    end
end

-- (1.30) The launcher: ONE small rounded control with two halves, "Squads" and "Gambits", and a thin line between
-- them. Each half is a button of its own: its own highlight under the mouse, its own click. Squads opens and closes
-- the menu and is lit while the menu is open. Gambits opens the Rule Set editor on the mate it had last (the
-- editor's own choice; "/gambits show", which this add-on has always sent with a slot from a mate's card). Either
-- half can be dragged to move the control (unless locked); a drag is never a click. The saved position is the
-- control's top left corner, as it was the Squads button's. Shown only while the character is in the world.
X.LAUNCHER_H = 20;   -- (1.31; a button of the menu is 19 high at the usual size: the text and 3 px above and below)
local function buttonWindow()
    if S.cfg.button_hidden == 'true' then return; end
    if not X.inWorld() then S.dragging, S.dragMoved, S.buttonHot, X.launcherFor = false, false, false, nil; return; end   -- (nothing is drawn: nothing can be clicked)
    -- (1.31) The first frame in the world, and the first frame of another character: the character's theme is read
    -- NOW. (While no window of the menu is open the theme is looked at every 5 seconds only, and at the title screen
    -- there was no character to read it for: the launcher stood in the earlier colours until the next look.)
    local who = U.current_identity();
    if who ~= nil and X.launcherFor ~= who then
        X.launcherFor = who;
        X.syncTheme(now(), true);
    end
    local x, y = tonumber(S.cfg.button_x) or 18, tonumber(S.cfg.button_y) or 240;
    imgui.SetNextWindowPos({ x, y }, S.dragging and (G('ImGuiCond_Always') or 1) or (S.placeButton and (G('ImGuiCond_Always') or 1)) or (G('ImGuiCond_FirstUseEver') or 4));
    S.placeButton = false;
    -- the whole control fades to its opacity; under the mouse (or while dragged) it is solid, so it is easy to find
    local fade = (S.buttonHot or S.dragging) and 1 or opacityOf('button_opacity');
    -- (1.31) the theme's colours, in ONE shape: the window itself is the button (its face is the launcher's button
    -- colour, its border the one outline, rounded); the two halves have no face and no border of their own, only a
    -- highlight under the mouse or when lit, so there is one outline with a thin line in the middle
    local face = nil;
    for _, item in ipairs(X.menu.button) do if item[1] == 'ImGuiCol_Button' then face = item[2]; end end
    local colors = {};
    for _, item in ipairs(X.menu.button) do colors[#colors + 1] = item; end
    if face then colors[#colors + 1] = { 'ImGuiCol_WindowBg', face }; end
    colors[#colors + 1] = { 'ImGuiCol_Button', { 0, 0, 0, 0 } };
    local token = U.push(imgui, colors, { { 'ImGuiStyleVar_WindowRounding', X.sv(6) }, { 'ImGuiStyleVar_WindowBorderSize', 1 },
                                          { 'ImGuiStyleVar_WindowPadding', { 1, 1 } }, { 'ImGuiStyleVar_WindowMinSize', { 1, 1 } },
                                          { 'ImGuiStyleVar_FrameRounding', X.sv(5) }, { 'ImGuiStyleVar_FrameBorderSize', 0 },
                                          { 'ImGuiStyleVar_ItemSpacing', { 0, 0 } }, { 'ImGuiStyleVar_Alpha', fade } });
    local flags = 0;
    for _, name in ipairs({ 'ImGuiWindowFlags_NoTitleBar', 'ImGuiWindowFlags_NoResize', 'ImGuiWindowFlags_NoScrollbar', 'ImGuiWindowFlags_NoCollapse',
                            'ImGuiWindowFlags_AlwaysAutoResize', 'ImGuiWindowFlags_NoSavedSettings', 'ImGuiWindowFlags_NoFocusOnAppearing' }) do
        flags = flags + (G(name) or 0);
    end
    if S.cfg.button_locked == 'true' then flags = flags + (G('ImGuiWindowFlags_NoMove') or 0); end
    local fontPushed = X.pushFont();   -- (1.34) the text at this Size, laid out for it (see X.pushFont)
    local shown = imgui.Begin('##servermenu_button', { true }, flags);
    local ok, err = pcall(function ()
        if not shown then return; end
        scaleWindow();
        local hot = false;
        -- one half: a button `w` wide (as laid out for the usual font) and X.LAUNCHER_H high: (1.31) about a menu button's height
        local function half(label, id, w, lit, muted, tip, onClick)
            local colors = nil;
            if lit then colors = { { 'ImGuiCol_Button', C.sel }, { 'ImGuiCol_ButtonHovered', C.selHi }, { 'ImGuiCol_ButtonActive', C.selHi } };
            elseif muted then colors = { { 'ImGuiCol_Text', C.faint } }; end
            local t2 = U.push(imgui, colors);
            local okB, clicked = pcall(imgui.Button, label .. '##' .. id, { px(w), px(X.LAUNCHER_H) });
            U.pop(imgui, t2);
            if not okB then error(clicked, 0); end
            if has('IsItemHovered') and imgui.IsItemHovered() then hot = true; end
            -- dragging this half moves the control (unless locked); a drag is not a click
            if S.cfg.button_locked ~= 'true' and has('IsItemActive') and has('IsMouseDragging') and has('GetMouseDragDelta') then
                if imgui.IsItemActive() and imgui.IsMouseDragging(0, 3) then
                    local dx, dy = xy(imgui.GetMouseDragDelta(0));
                    if dx and dy then
                        if not S.dragging then S.dragging, S.dragFrom = id, { x, y }; end
                        if S.dragging == id then
                            setCfg('button_x', math.floor(S.dragFrom[1] + dx));
                            setCfg('button_y', math.floor(S.dragFrom[2] + dy));
                            S.dragMoved = true;
                        end
                    end
                elseif S.dragging == id and not imgui.IsItemActive() then
                    S.dragging = false;
                end
            end
            if clicked == true then
                if S.dragMoved then S.dragMoved = false; else onClick(); end
            elseif not S.dragging then
                S.dragMoved = false;
            end
            if not S.dragging then tooltip(tip); end
            X.launcherMenu('##sm_buttonmenu_' .. id);
        end

        half('Squads', 'sm_open', 54, S.open[1] == true, false, 'Squads  (/menu)   drag to move, right-click for options', function ()
            setOpen(not S.open[1]);
        end);
        -- (1.34) Options > "Show Gambits shortcut" off: the Squads half alone, at the same saved place (the window sizes
        -- itself to what it holds, so the control is simply shorter). /gambits and the cards' Gambits buttons stay.
        if X.gambitsShortcut() then
            -- the thin line between the two halves
            imgui.SameLine(0, 0);
            local pos = U.cursor(imgui);   -- (xifo_ui's: the menu's own position helpers stand further down in this file)
            if pos then U.frame(imgui, pos[1], pos[2] + px(3), 1, px(X.LAUNCHER_H - 6), C.line, nil, 0); end
            if has('Dummy') then imgui.Dummy({ 1, px(X.LAUNCHER_H) }); end
            imgui.SameLine(0, 0);
            local loaded = X.gambitsLoaded();
            -- (1.34) Gambits opens AND closes its window, like the Squads half, and is lit while the window is really
            -- shown, however it was opened or closed (its X, /gambits, a card's button): the editor's own word
            local shownNow = loaded and X.gambitsShown();
            half('Gambits', 'sm_gsq', 60, shownNow, not loaded,
                loaded and (shownNow and 'Gambits: close the Rule Set editor   (drag to move)'
                    or 'Gambits: the Rule Set editor, on the squad mate it had last   (drag to move)')
                    or 'Gambits is not loaded for this character (/addon load gambits).', function ()
                if not loaded then say('Gambits is not loaded: /addon load gambits'); return; end
                if X.gambitsShown() then X.closeGambits(); else X.openGambits(); end
            end);
        end
        S.buttonHot = hot;
        -- when ImGui moved the window by its edge, remember where it went
        if not S.dragging and has('GetWindowPos') then
            local wx, wy = xy(imgui.GetWindowPos());
            if wx and wy and (math.abs(wx - x) >= 1 or math.abs(wy - y) >= 1) then
                setCfg('button_x', math.floor(wx));
                setCfg('button_y', math.floor(wy));
            end
        end
    end);
    S.scaledNow = false;
    imgui.End();
    X.popFont(fontPushed);
    U.pop(imgui, token);
    if not ok then error(err, 0); end
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
    -- (1.29) Ashita hands back two numbers (x, y); a table was all this read, so in the game there never was a position:
    -- the Gear rows of 1.28 were drawn the older way, and the Profile's band of 1.27 too
    local ok, value, second = pcall(imgui.GetCursorScreenPos);
    if not ok or value == nil then return nil; end
    if type(value) == 'table' then return { number(value[1] or value.x), number(value[2] or value.y) }; end
    if type(value) == 'number' and type(second) == 'number' then return { value, second }; end
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
X.clip = fit;   -- (1.28: the mate cards, which stand above this, cut a long name the same way)

local function tint(rgba, text)
    if imgui and imgui.TextColored then
        imgui.TextColored(rgba, tostring(text));
    else
        imgui.Text(tostring(text));
    end
end

local function wrappedColored(rgba, text) U.wrapped(imgui, rgba, text); end   -- (1.27: never read as a format)

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
    -- (1.27) an item's name is asked from the game once, not every frame for every piece shown (56 times a frame with
    -- a full gear list); a name the game could not give yet is asked again
    if id and id > 0 and X.names[id] then return X.names[id]; end
    if id and id > 0 and AshitaCore and type(AshitaCore.GetResourceManager) == 'function' then
        local ok, item = pcall(function () return AshitaCore:GetResourceManager():GetItemById(id); end);
        if ok and item and item.Name and item.Name[1] and item.Name[1] ~= '' then
            X.names[id] = tostring(item.Name[1]);
            return X.names[id];
        end
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

-- (1.27) one equipment slot of the Gear view: the item's icon, then one button "Slot:  Item name" that selects the
-- slot (lit while it is the selected one). `width` is in pixels. A slot that cannot be chosen (Look: a slot that does
-- not show on a character) is plain text. Returns true when it was clicked.
-- (1.28) The row is one clickable strip, `width` pixels wide: the icon's place (kept also when the slot is empty), the
-- slot's name in its own column, then the item's name ("Empty" muted). The selected slot has the theme's row frame
-- (a thin line and a light tint), which leaves the names as readable as they were. Returns true when it was clicked.
-- (Without the calls to place things on the screen the older drawing below is used.)
X.SLOT_COL = 50;
function X.slotCell(mateSlot, eq, name, itemId, width, selected, enabled)
    local empty = emptySlot(name);
    local display = empty and '' or itemDisplayName(itemId, name);
    local icon = (not empty) and itemIcon(itemId, display) or nil;
    local pos = screenPos();
    if pos and has('SetCursorScreenPos') and has('Dummy') then
        local rowH = math.max(ICON, px(20));
        local slotName = SLOT_LABEL[eq + 1] or tostring(eq);
        if selected then U.frame(imgui, pos[1], pos[2], width, rowH, C.rowFill, C.rowLine, 4); end
        local clicked = false;
        if enabled then
            -- the strip: a button without a face of its own (the frame above is the selection, the tint under the mouse its feedback)
            local token = U.push(imgui, { { 'ImGuiCol_Button', { 0, 0, 0, 0 } }, { 'ImGuiCol_ButtonHovered', C.hover }, { 'ImGuiCol_ButtonActive', C.rowFill } },
                                 { { 'ImGuiStyleVar_FrameBorderSize', 0 } });
            local ok, hit = pcall(imgui.Button, '##slot' .. tostring(mateSlot) .. '_' .. eq, { width, rowH });
            U.pop(imgui, token);
            if not ok then error(hit, 0); end
            clicked = hit == true;
        else
            imgui.Dummy({ width, rowH });
        end
        if not empty then
            local stats = itemStatsText(itemId, display);
            if stats then tooltip(stats); end
        elseif not enabled then
            tooltip('This slot does not show on a character.');
        end
        -- what the strip shows, drawn over it
        local iconY = pos[2] + math.floor((rowH - ICON) / 2);
        seek(pos[1], iconY);
        local drew = false;
        if icon ~= nil and imgui.Image ~= nil then drew = pcall(imgui.Image, icon.ptr, { ICON, ICON }); end
        if not drew then fillRect(windowDraw(), pos[1] + 2, iconY + 2, ICON - 4, ICON - 4, { 1, 1, 1, 0.05 }, 4); end
        local textY = pos[2] + math.max(0, math.floor((rowH - px(13)) / 2));
        local x = pos[1] + ICON + 6;
        seek(x, textY);
        tint(enabled and C.text or C.faint, slotName);   -- (1.29) the slot's name in the usual text colour
        seek(x + px(X.SLOT_COL), textY);
        -- "Empty" in the theme's colour for secondary text; an item's name in the usual one
        tint((not enabled) and C.faint or (empty and C.dim or C.text), empty and 'Empty' or fit(display, width - ICON - 6 - px(X.SLOT_COL) - 6));
        -- the row itself is the last thing drawn, so what follows (the other column, the next row) is placed from it
        seek(pos[1], pos[2]);
        imgui.Dummy({ width, rowH });
        return clicked;
    end
    local shown = false;
    if icon ~= nil and imgui.Image ~= nil then
        shown = pcall(imgui.Image, icon.ptr, { ICON, ICON });
    end

    if not shown then
        local pos = screenPos();
        if pos then fillRect(windowDraw(), pos[1], pos[2], ICON, ICON, { 1, 1, 1, 0.05 }, 4); end
        imgui.Dummy({ ICON, ICON });
    end

    imgui.SameLine(0, 6);
    local buttonW = math.max(60, width - ICON - 6);
    local text = fit((SLOT_LABEL[eq + 1] or tostring(eq)) .. ':  ' .. (empty and 'Empty' or display), buttonW - 14);
    local clicked = false;
    if enabled then
        local colors = selected and { { 'ImGuiCol_Button', C.sel }, { 'ImGuiCol_ButtonHovered', C.selHi }, { 'ImGuiCol_ButtonActive', C.selHi } } or nil;
        local token = U.push(imgui, colors, { { 'ImGuiStyleVar_ButtonTextAlign', { 0, 0.5 } } });
        local ok, hit = pcall(imgui.Button, text .. '##slot' .. tostring(mateSlot) .. '_' .. eq, { buttonW, ICON });
        U.pop(imgui, token);
        if not ok then error(hit, 0); end
        clicked = hit == true;
    else
        tint(C.faint, text);
    end

    if not empty then
        local stats = itemStatsText(itemId, display);
        if stats then tooltip(stats); end
    end

    return clicked;
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
        X.pendMate(slot);
        askBlue(slot, 2);
        b.done = false;
    end
    tooltip('Let the mate pick its own set again');
    for k, item in ipairs(b.list) do
        if k > 1 and (k - 1) % 3 ~= 0 then imgui.SameLine(0, 6); end
        local label = string.format('%s (%d)', item.name, item.points);
        if button(label, 'blu' .. slot .. '_' .. item.id, px(150), 0, item.set and 'on' or nil) then
            enqueue(string.format('/say !squad blu %d %s %d', slot, item.set and 'unset' or 'set', item.id));
            X.pendMate(slot);
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
-- (1.27) the Gear view of the profile window: the 16 slots are the slot picker (a click on what is worn lists the gear
-- for that slot), Equipment and Look (lockstyle) are two clearly named views instead of a "Picking:" switch, the piece
-- that is worn is marked, the list has a name filter and is kept for a while, and a change says that it shows at the
-- next call, with Apply next to it. What may be worn, what the squad owns, Auto-equip and lockstyle are the server's,
-- unchanged: the same !squad gearlist / equip / unequip / lockstyle lines as before.
local SLOT_KEY = { [0] = 'main', 'sub', 'range', 'ammo', 'head', 'body', 'hands', 'legs', 'feet', 'neck', 'waist', 'ear1', 'ear2', 'ring1', 'ring2', 'back' };
-- (1.21) lockstyle: the slots a look can be locked in (the ones you see on a character)
local LOOK_SLOTS = { [0] = true, [1] = true, [2] = true, [4] = true, [5] = true, [6] = true, [7] = true, [8] = true };

-- the gear list of one mate and slot: from the lists kept (two minutes; dropped after a job change, an Apply, Refresh
-- or Reload), else asked from the server
function X.askGear(slot, eq)
    local hit = X.gearCache[slot .. ':' .. eq];
    if hit and now() - hit.at < 120 then
        S.gear = { slot = slot, eq = eq, items = hit.items, done = true, total = hit.total };
        return false;
    end
    S.gear = { slot = slot, eq = eq, items = {}, done = false };
    enqueue(string.format('/say !squad gearlist %d %d', slot, eq));
    S.waitUntil = now() + 5;
    return true;
end

-- after a piece was put on, taken off or shown: the mate wears it at its next call, so say so (and offer Apply); the
-- sheet is read again, and the squad list too (putting a piece on by hand switches Auto-equip off on the server)
function X.gearChanged(slot)
    X.pendMate(slot, true);
    askSheet(2);
    ask(4.5);
end

-- the equipment slots as the Gear view shows them (slot numbers: 0 main, 1 sub, 2 ranged, 3 ammo, 4 head, 5 body,
-- 6 hands, 7 legs, 8 feet, 9 neck, 10 waist, 11 / 12 ears, 13 / 14 rings, 15 back)
X.GEAR_GROUPS = {
    { 'Weapons',     { { 0, 1 }, { 2, 3 } } },
    { 'Armor',       { { 4, 5 }, { 6, 7 }, { 8, 15 } } },
    { 'Accessories', { { 9, 10 }, { 11, 12 }, { 13, 14 } } },
};
function X.gearView(slot, d)
    local mate = nil;
    for _, m in ipairs(S.mates or {}) do if m.slot == slot then mate = m; end end
    local look = S.gearLook == true;
    local who = (mate and mate.name) or (d.hdr and d.hdr.name) or 'the mate';

    if X.pend and X.pend[slot] and X.pend[slot].gear then
        if mate and mate.out then
            colorText(C.warn, 'Gear changed: ' .. who .. ' shows it when called again.');
            X.fit(64, 10);
            if button('Apply', 'gearapply' .. slot, 64, 0, 'go') then X.applyMate(mate); end
            tooltip(X.applyTip(mate));
        else
            colorText(C.dim, 'Gear changed: ' .. who .. ' wears it at the next call.');
        end
        gap(2);
    end

    -- (1.28) the smaller kind of tab: a choice inside the Gear view
    if X.tab('Equipment', 'gvgear' .. slot, not look, true) then S.gearLook = false; end
    tooltip('What ' .. who .. ' wears. A click on a piece in the list puts it on.');
    imgui.SameLine(0, X.sv(4));
    if X.tab('Look (lockstyle)', 'gvlook' .. slot, look, true) then S.gearLook = true; end
    tooltip('How ' .. who .. ' looks, whatever it wears. A click on a piece in the list only changes the look.');
    if look then
        X.fit(140, 14);
        if button('Lock current look', 'lsset' .. slot, 140, 0) then
            enqueue(string.format('/say !squad lockstyle %d set', slot));
            X.gearChanged(slot);
        end
        tooltip('Keep the look it has now, whatever gear it wears later');
        X.fit(112);
        if button('Lockstyle off', 'lsoff' .. slot, 112, 0) then
            enqueue(string.format('/say !squad lockstyle %d off', slot));
            X.gearChanged(slot);
        end
        tooltip('Show the gear it really wears');
        -- whether a look is locked at all: without one the cells below show the gear that is worn, and nothing else said so
        local locked = 0;
        for e in pairs(LOOK_SLOTS) do if d.ls and d.ls[e] then locked = locked + 1; end end
        if locked == 0 then
            dimText('Lockstyle: off (shows the gear it wears)');
        else
            colorText(C.good, 'Lockstyle: on');
            imgui.SameLine(0, 8);
            dimText(locked >= 8 and '(every slot that shows)' or string.format('(%d of 8 slots; the others show the gear it wears)', locked));
        end
    end
    gap(2);

    -- the 16 slots, two columns: what is worn (Look: what is shown there). A click selects the slot.
    local width = contentWidth();
    if width <= 0 then width = px(540); end
    local column = math.floor(width / 2);
    local eq, ls = d.eq or {}, d.ls or {};
    -- (1.28) in three groups, two slots a row: weapons and ammunition, armour, accessories; the two ears next to
    -- each other, the two rings too. Only where a slot is drawn: its number, its commands and what is saved for it
    -- are what they were.
    for gi, group in ipairs(X.GEAR_GROUPS) do
        if gi > 1 then X.group(); end
        tint(C.faint, group[1]);
        for _, pair in ipairs(group[2]) do
            for side, e in ipairs(pair) do
                if side == 2 then imgui.SameLine(column, 0); end
                local name, id = eq[e], d.eqId and d.eqId[e];
                local enabled = (not look) or LOOK_SLOTS[e] == true;
                if look and ls[e] then name, id = ls[e].name, ls[e].id; end
                if X.slotCell(slot, e, name, id, column - 8, S.gearEq == e, enabled) then
                    S.gearEq = e;
                    X.askGear(slot, e);
                end
            end
        end
    end
    X.group();

    if has('Separator') then imgui.Separator(); end
    local e = S.gearEq;
    if e == nil then
        dimText('Click a slot above to see the gear your squad has for it.');
        return;
    end
    if look and not LOOK_SLOTS[e] then
        dimText('This slot does not show on a character: pick main, sub, range, head, body, hands, legs or feet.');
        return;
    end
    local g = S.gear;
    if g == nil or g.slot ~= slot or g.eq ~= e then
        X.askGear(slot, e);
        g = S.gear;
    end

    colorText(C.gold, (look and 'Look: ' or 'Gear: ') .. (SLOT_LABEL[e + 1] or tostring(e)));
    X.fit(84, 10);
    if button(look and 'Real gear' or 'Take off', 'gpoff' .. slot, 84, 0) then
        if look then
            enqueue(string.format('/say !squad lockstyle %d off %s', slot, SLOT_KEY[e]));
        else
            enqueue(string.format('/say !squad unequip %d %s', slot, SLOT_KEY[e]));
        end
        X.gearChanged(slot);
    end
    tooltip(look and 'Show the gear it really wears in this slot' or 'Leave this slot empty');
    S.gearFilter = S.gearFilter or { '' };
    if has('InputText') then
        X.fit(200, 14);
        dimText('Filter'); imgui.SameLine(0, 6);
        if has('PushItemWidth') then imgui.PushItemWidth(px(140)); end
        pcall(imgui.InputText, '##sm_gearfilter', S.gearFilter, 32);
        if has('PopItemWidth') then imgui.PopItemWidth(); end
        tooltip('Show only the pieces whose name has these letters.');
    end
    X.fit(64);
    if button('Reload', 'gpreload' .. slot, 64, 0) then
        X.gearCache[slot .. ':' .. e] = nil;
        X.askGear(slot, e);
        g = S.gear;
    end
    tooltip('Ask the server for this list again (after you gave the squad a new piece).');
    gap(2);
    if not g.done then dimText('Looking...'); return; end
    if #g.items == 0 then
        dimText('Nothing for this slot yet: trade a piece to a mate (or !squad give) first.');
        return;
    end

    local wornId = nil;
    if look then wornId = ls[e] and ls[e].id or nil; else wornId = d.eqId and d.eqId[e] or nil; end
    local needle = tostring(S.gearFilter[1] or ''):lower():gsub('^%s+', ''):gsub('%s+$', '');
    local drawn = 0;
    for k, item in ipairs(g.items) do
        local itemName = itemDisplayName(item.id, item.name);
        if needle == '' or itemName:lower():find(needle, 1, true) then
            local worn = wornId ~= nil and wornId ~= 0 and item.id == wornId;
            local label = string.format('Lv%d %s%s', item.level, itemName, worn and (look and '  (shown)' or '  (worn)') or '');
            if drawn > 0 then U.same_if_fits(imgui, X.textW(label) + X.sv(12), 6); end
            drawn = drawn + 1;
            if button(label, 'gpi' .. slot .. '_' .. item.id .. '_' .. k, 0, 0, worn and 'on' or nil) and not worn then
                if look then
                    enqueue(string.format('/say !squad lockstyle %d %d %s', slot, item.id, SLOT_KEY[e]));
                else
                    enqueue(string.format('/say !squad equip %d %d %s', slot, item.id, SLOT_KEY[e]));
                end
                X.gearChanged(slot);
            end
            local stats = itemStatsText(item.id, item.name);
            tooltip((stats and (stats .. '\n\n') or '') .. (worn and (look and 'This is the look shown in this slot now.' or who .. ' wears this now.')
                or (look and 'Click to look like this (only the look; it shows at the next call)' or 'Click to put it on (it shows at the next call)')));
        end
    end
    if drawn == 0 then dimText('No piece in this list has "' .. tostring(S.gearFilter[1]) .. '" in its name.'); end
    if (g.total or 0) > #g.items then dimText(string.format('(%d more not shown: the server lists the best 40)', g.total - #g.items)); end
end

-- "MNK 5 / WAR 2" from a sheet's header (a support job the player does not have yet: "(locked)")
function X.jobsOf(h)
    local jobs = tostring(h.job or '?') .. ' ' .. tostring(h.main or 0);
    if h.sub ~= '-' and h.sub ~= '' and h.sub ~= nil then
        if (tonumber(h.subLevel) or 0) > 0 then
            jobs = jobs .. ' / ' .. tostring(h.sub) .. ' ' .. tostring(h.subLevel);
        else
            jobs = jobs .. ' / ' .. tostring(h.sub) .. ' (locked)';   -- support jobs work once you have them yourself
        end
    end
    return jobs;
end

-- (until 1.27 the Profile began with this band; 1.28 has the mate row instead. Kept: nothing else changed here.)
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

-- (1.30) Are the numbers of this sheet LIVE? The server reads HP / MP / TP, the attributes, the combat values and
-- haste from the mate itself, and only while it is called (squad.lua, !squad sheet: for a mate that is away it sends
-- none of them and a note instead). So they are live when: the sheet has them, it is the selected mate's sheet (it
-- always is when it is shown: X.sheetShown), the squad list says that mate is out, and the reading is fresh (the
-- window asks again every 5 seconds; after 12 without an answer it no longer says so). EXP, jobs and gear are the
-- mate's stored data: they are the same whether it is called or not.
function X.sheetLive(d)
    if d == nil or d.vitals == nil or #d.vitals == 0 or d.forSlot ~= S.sheetSlot then return false; end
    if now() - (d.at or -1000) > 12 then return false; end
    for _, m in ipairs(S.mates or {}) do
        if m.slot == S.sheetSlot then return m.out == true; end
    end
    return false;
end

-- the four switches of a mate (squad.lua SQUAD_SW: what it is allowed to do), as the Profile names them
X.SW_LABEL = { melee = 'Melee', ranged = 'Ranged', ja = 'Job abilities', magic = 'Magic' };
X.SW_TIP = {
    melee  = 'Melee: attacking with its weapon.',
    ranged = 'Ranged: ranged attacks.',
    ja     = 'Job abilities: its job abilities (Provoke, Sneak Attack, Convert ...).',
    magic  = 'Magic: casting spells.',
};

-- (1.27) the Stats view of the profile window: what the window showed before its gear part
-- (1.30) in groups, with the names said: Role / Mode / Race, Actions, the vitals, Attributes and Combat
function X.statsView(d)
    local h = d.hdr;
    local width = contentWidth();
    local statWidth = width > 0 and width or 440;

    -- Role, Mode, Race: a muted name and its value, like on the mate's card
    local function pair(label, value, first)
        if not first then U.same_if_fits(imgui, X.textW(label .. '  ' .. value) + X.sv(8), 16); end
        dimText(label); imgui.SameLine(0, 6);
        colorText(C.text, value);
    end
    pair('Role', tostring(h.role or 'auto'), true);
    if h.mode and h.mode ~= '' then pair('Mode', tostring(h.mode)); end
    if h.race and h.race ~= '' and h.race ~= '?' then pair('Race', tostring(h.race)); end

    -- Actions: what this mate is allowed to do (the server's switches). Each one says its state; a click changes it.
    dimText('Actions'); imgui.SameLine(px(X.COL.label + 8), 0);
    for i, name in ipairs(SWITCHES) do
        local on = hasBit(h.mask or 15, SW_BIT[name]);
        local label = X.SW_LABEL[name] .. (on and ': on' or ': off');
        if i > 1 then U.same_if_fits(imgui, X.textW(label) + X.sv(12), 4); end
        if button(label, 'sheetsw' .. tostring(S.sheetSlot or 0) .. name, 0, 0, on and 'on' or nil) then
            toggleSheetSwitch(h, name);
        end
        tooltip(X.SW_TIP[name] .. ' Now: ' .. (on and 'allowed' or 'not allowed') .. '. Click to switch it ' .. (on and 'off.' or 'on.'));
    end
    X.group();

    -- the numbers. "Live stats" only when they are read from this mate while it is out (X.sheetLive)
    local live = X.sheetLive(d);
    colorText(C.gold, live and 'Live stats' or 'Stats');
    if live then
        tooltip('Read from this mate while it is out, every few seconds: HP, MP, TP, the attributes, the combat values and haste. They include its gear. EXP and jobs are its stored data.');
    elseif d.vitals and #d.vitals > 0 then
        imgui.SameLine(0, 10);
        dimText('(the last reading: not live now)');
    end
    drawVitalRow(d.vitals);      -- HP, MP and TP on one row
    drawExpRow(d.exp);           -- EXP below them
    if d.note then
        wrapped(d.note, C.faint);
        gap(2);
    end

    if d.stats or d.combat then
        if has('Separator') then imgui.Separator(); end
        local rows = math.max(d.stats and #d.stats or 0, d.combat and #d.combat or 0);
        local rightX = math.floor(statWidth * 0.50);
        -- every number ends at the same place in its column
        local aEnd, cEnd = px(96), rightX + px(190);
        local token = U.push(imgui, nil, { { 'ImGuiStyleVar_ItemSpacing', { X.sv(6), X.sv(8) } } });
        local ok, err = pcall(function ()
            colorText(C.gold, 'Attributes');
            imgui.SameLine(rightX, 0);
            colorText(C.gold, 'Combat');
            for i = 1, rows do
                local s = d.stats and d.stats[i];
                local c = d.combat and d.combat[i];
                if s then
                    tint(C.dim, s[1]);
                    local v = tostring(s[2]);
                    imgui.SameLine(math.max(px(40), aEnd - X.textW(v)), 0);
                    tint(C.text, v);
                else
                    imgui.Text(' ');
                end
                if c then
                    imgui.SameLine(rightX, 0);
                    tint(C.dim, c[1]);
                    local v = tostring(c[2]);
                    imgui.SameLine(math.max(rightX + px(110), cEnd - X.textW(v)), 0);
                    tint(C.text, v);
                end
            end
        end);
        U.pop(imgui, token);
        if not ok then error(err, 0); end
    end

    if d.haste and #d.haste > 0 then
        local parts = {};
        for _, v in ipairs(d.haste) do parts[#parts + 1] = string.format('%s %.2f%%', v[1], v[2] / 100); end
        tint(C.dim, 'Haste');
        imgui.SameLine(0, 12);
        tint(C.text, table.concat(parts, '     '));
    end

    if d.jobs and #d.jobs > 0 then
        local parts = {};
        for i, j in ipairs(d.jobs) do
            if i > 8 then break; end
            parts[#parts + 1] = j[1] .. ' ' .. tostring(j[2]);
        end
        wrapped('Jobs: ' .. table.concat(parts, ', '), C.text);
    end

    -- (1.26l, Frost) what this mate can cast and use, in a window of its own
    do
        local nSpells, nAbilities = d.spells and #d.spells or 0, d.abilities and #d.abilities or 0;
        local label = (nSpells + nAbilities > 0) and string.format('Spells and abilities (%d / %d)', nSpells, nAbilities)
            or 'Spells and abilities';
        if button(label, 'sheetactions', 0, 0, S.actionsOpen[1] and 'on' or nil) then
            S.actionsOpen[1] = not S.actionsOpen[1];
            S.actionsFresh = S.actionsOpen[1];
        end
        tooltip('The spells and job abilities this mate can use right now (its jobs and levels). Only while it is called.');
        gap(2);
    end

    bluePicker(S.sheetSlot, d.hdr);
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
    local d = X.sheetShown();
    -- (1.28) one fixed title, in the theme's title colours like the menu and the Gambits window; who the window is
    -- about is its first row (until 1.27 the title, a coloured band and the Mate list all said the name)
    local title = 'Profile###sm_sheet';
    if has('SetNextWindowSize') and G('ImGuiCond_FirstUseEver') then
        imgui.SetNextWindowSize({ px(580), px(660) }, G('ImGuiCond_FirstUseEver'));
    end
    if has('SetNextWindowSizeConstraints') then
        imgui.SetNextWindowSizeConstraints({ px(540), px(420) }, { px(800), px(900) });
    end
    local colors = X.windowColors('sheet', function ()
        return { { 'ImGuiCol_WindowBg', C.panel }, { 'ImGuiCol_Border', C.line }, { 'ImGuiCol_Separator', C.line }, { 'ImGuiCol_Text', C.text } };
    end);
    local token = U.push(imgui, colors, X.vars());
    local flags = (G('ImGuiWindowFlags_NoCollapse') or 0);
    local fontPushed = X.pushFont();   -- (1.34) the text at this Size, laid out for it (see X.pushFont)
    local shown = imgui.Begin(title, S.sheetOpen, flags);
    local ok, err = pcall(function ()
        if not shown then return; end
        scaleWindow();
        -- the first row, right below the title bar (the Gambits window has the same): the mate, as a list to pick
        -- another one from, then its jobs. The name in the list is the selected slot's; the jobs are the sheet's, and
        -- a sheet is only ever shown when it is that mate's (X.sheetShown).
        local names, bySlot, current = {}, {}, nil;
        for _, m in ipairs(S.mates or {}) do
            names[#names + 1] = m.name;
            bySlot[m.name] = m.slot;
            if m.slot == S.sheetSlot then current = m.name; end
        end
        if current then
            local pick = combo('sheetmate', current, names, 150);
            if pick and bySlot[pick] and bySlot[pick] ~= S.sheetSlot then
                -- nothing more in this frame: `d` is the sheet of the mate before, the slot is the new mate's
                openSheet(bySlot[pick], S.sheetTab);
                return;
            end
            tooltip('Another squad mate, in this window (the same view and slot stay selected).');
        elseif d and d.hdr then
            colorText(C.gold, tostring(d.hdr.name));
        else
            dimText('Squad mate ' .. tostring(S.sheetSlot or ''));
        end
        if d == nil or d.hdr == nil then
            X.fit(260, 12);
            dimText(now() < (S.sheetWaitUntil or 0) and 'Asking the server...' or 'No answer from the server. Press Sheet again.');
            return;
        end
        imgui.SameLine(0, 10);
        colorText(C.text, X.jobsOf(d.hdr));

        -- the two views: the main tabs of this window
        if X.tab('Stats', 'sheettabstats', S.sheetTab ~= 'gear') then S.sheetTab = 'stats'; end
        tooltip('Stats, HP/MP/TP, haste, jobs, spells and abilities');
        imgui.SameLine(0, X.sv(4));
        if X.tab('Gear', 'sheettabgear', S.sheetTab == 'gear') then S.sheetTab = 'gear'; end
        tooltip('What the mate wears, changing a piece, and its look (lockstyle)');
        if has('Separator') then imgui.Separator(); end
        gap(2);

        if S.sheetTab == 'gear' then
            X.gearView(S.sheetSlot, d);
        else
            X.statsView(d);
        end

        if has('Separator') then imgui.Separator(); end
        wrapped('The stats are read from your squad mate while they are out, so they already include their gear. '
            .. 'Gear shown for a mate who is away is what they wear as this job.', C.faint);
        gap(2);
        tint(C.faint, 'servermenu ' .. tostring(addon.version));
    end);
    S.scaledNow = false;
    imgui.End();
    X.popFont(fontPushed);
    U.pop(imgui, token);
    if not ok then error(err, 0); end
end

-- (1.26l, Frost) the Spells and abilities window, next to the profile; it follows the sheet that is open
local function renderActions()
    if not imgui or not S.actionsOpen[1] or not S.sheetOpen[1] then return; end
    local d = X.sheetShown();
    if S.actionsFresh then
        S.actionsFresh = false;
        if has('SetNextWindowFocus') then imgui.SetNextWindowFocus(); end
    end
    if has('SetNextWindowSize') and G('ImGuiCond_FirstUseEver') then
        imgui.SetNextWindowSize({ px(360), px(460) }, G('ImGuiCond_FirstUseEver'));
    end
    local title = 'Spells and abilities###sm_actions';
    if d and d.hdr then title = string.format('%s: spells and abilities###sm_actions', d.hdr.name); end
    -- (1.27) the theme's colours and the shared metrics, like the menu and the profile
    local colors = X.windowColors('actions', function ()
        return { { 'ImGuiCol_WindowBg', C.panel }, { 'ImGuiCol_Border', C.line }, { 'ImGuiCol_Text', C.text } };
    end);
    local token = U.push(imgui, colors, X.vars());
    local fontPushed = X.pushFont();   -- (1.34) the text at this Size, laid out for it (see X.pushFont)
    local shown = imgui.Begin(title, S.actionsOpen, G('ImGuiWindowFlags_NoCollapse') or 0);
    local ok, err = pcall(function ()
        if not shown then return; end
        scaleWindow();
        if d == nil or d.hdr == nil then
            dimText('Asking the server...');
        elseif not d.vitals then
            wrappedColored(C.faint, 'Call ' .. tostring(d.hdr.name) .. ' to see the spells and abilities they can use now.');
        else
            local width = contentWidth();
            local valueX = math.max(px(200), (width > 0 and width or px(330)) - px(70));
            colorText(C.gold, 'Spells');
            gap(2);
            if not d.spells or #d.spells == 0 then
                tint(C.faint, 'None at this job and level.');
                newLine();
            else
                for _, sp in ipairs(d.spells) do
                    tint(C.text, prettyName(sp[1]));
                    imgui.SameLine(valueX, 0);
                    tint(C.dim, sp[2] > 0 and (tostring(sp[2]) .. ' MP') or '');
                    newLine();
                end
            end
            gap(4);
            if has('Separator') then imgui.Separator(); end
            colorText(C.gold, 'Job abilities');
            gap(2);
            if not d.abilities or #d.abilities == 0 then
                tint(C.faint, 'None at this job and level.');
                newLine();
            else
                for _, ab in ipairs(d.abilities) do
                    tint(C.text, prettyName(ab[1]));
                    imgui.SameLine(valueX, 0);
                    tint(C.dim, 'Lv ' .. tostring(ab[2]));
                    newLine();
                end
            end
            gap(4);
            wrappedColored(C.faint, 'Ask for one in party chat, e.g. /p cure <me>, /p provoke. A mate you call again '
                .. 'after a level up or a job change shows the new list.');
        end
    end);
    S.scaledNow = false;
    imgui.End();
    X.popFont(fontPushed);
    U.pop(imgui, token);
    if not ok then error(err, 0); end
end

local function render()
    if not imgui then return; end
    buttonWindow();
    menuWindow();
    X.campBar();   -- (1.33) the compact camp bar, when switched on
    renderSheet();
    renderActions();
end

-- ---------------------------------------------------------------- events
ashita.events.register('load', 'servermenu_load', function ()
    S.menuLoadedAt = os.time();   -- (1.26c) an autobox flag older than this is left over from an earlier game
    local hadWide, hadCfg = loadCfg();
    -- (1.27) the theme. A settings file from before themes has no theme line: that installation keeps the look it has
    -- (Squad is this menu's look as it always was). No settings file at all is a new installation: Crimson. Either is
    -- then written down, and from then on only the player changes it. Nothing here touches the character's shared
    -- choice (xifo_ui: made only when a theme is picked), which wins while that character is logged in.
    if not U.valid(S.cfg.theme) then
        S.cfg.theme = hadCfg and 'squad' or U.DEFAULT;
        S.cfgDirty = true;
    end
    X.follow = U.follow.new(installPath());
    X.syncTheme(now(), true);
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
    ROLE_INFO.rsBurstTick(t);   -- (1.26n, M3) the few asks right after a change
    X.syncTheme(t);             -- (1.27) the character's theme, also when Gambits changed it a moment ago
    X.ventureTick(t);           -- (1.36) a click on Ventures that waits for the add-on to load or to answer
    -- (1.26d) no background refresh within 8 s of a click, so the next click is not stuck 2.2 s behind one
    local idle = t - (S.lastClick or -1000) > 8;
    if idle and S.open[1] and #S.queue == 0 and t - S.lastAsk > 15 and S.tab == 'Squad' then ask(); end   -- keeps the squad current while it is shown
    if idle and S.sheetOpen[1] and #S.queue == 0 and t - S.lastSheetAsk > 5 then askSheet(); end          -- hit points and TP move
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
        -- (1.25, Altair and Yumainai: a wall of squadpanel: lines in the chat log) these lines are only data for this
        -- menu. They used to be hidden for a few seconds after the menu asked; a second answer, or a slow one, got through.
        e.blocked = true;
        onLine(text:sub(at + 11));
        return;
    end
    local sheetAt = text:find('squadsheet:', 1, true);
    if sheetAt then
        e.blocked = true;
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
    -- (1.32) the theme was chosen a moment ago, here or in Gambits: read it once, now (also when Gambits stopped the line first)
    if first == X.THEME_SIGNAL then
        e.blocked = true;
        X.syncTheme(now(), true);
        return;
    end
    -- (1.34) the Gambits window was just shown or hidden (Gambits 0.3.9 says so, also when it stopped the line first):
    -- the launcher's Gambits half follows at its next frame
    if first == X.GAMBITS_SIGNAL then
        e.blocked = true;
        X.gsqShownGuess = nil;
        X.gambitsShown(true);
        return;
    end
    -- (1.36) the Ventures add-on was just loaded, or its window shown or shut (it says so, and stops the line itself
    -- too): the Ventures button follows at its next frame, and a click that waits for it goes on at once
    if first == X.VENTURE_SIGNAL then
        e.blocked = true;
        if X.vtWant then X.vtWant.heard = true; end
        X.ventureLoaded(true);
        X.ventureShown(true);
        return;
    end
    -- (1.26n) a chat line another add-on or you sent (never blocked or changed: it still runs as it is):
    --   M1: the menu waits SAY_GAP after it before typing its own next line;
    --   a !squad panel asked by someone else is counted, so its answer is not credited to one of the menu's asks (M2);
    --   a squad change (!squad ruleset / reapply / job ...): the Rules line waits for a fresh answer, asked at +2, +7, +11 s (M3)
    if ROLE_INFO.RS_CHAT[first] and ROLE_INFO.rsSeenSay(e.command, now()) and first == '/say' then
        if e.command:lower():match('^/say%s+!squad%s+panel') then ROLE_INFO.rsSent(now()); end
        if ROLE_INFO.rsCommand(e.command) then return; end
    end
    -- (1.26c) you switched autobox yourself (not a line this menu sent): your choice wins, the kept /autobox off is dropped
    if first == '/autobox' and (sub == 'on' or sub == 'off' or sub == 'toggle') then
        local t, own = now(), false;
        for i = #(S.ownAutobox or {}), 1, -1 do
            local o = S.ownAutobox[i];
            if t - o.at > 5 then table.remove(S.ownAutobox, i);                      -- (the game runs it within a frame or two)
            elseif not own and o.text == e.command then table.remove(S.ownAutobox, i); own = true; end
        end
        if not own then
            owedAutoboxOff(auto_flag_character(), false);
            dropQueuedAutoboxOff();
        end
        return;
    end
    if first == '/sq' or first == '/squadpanel' then
        e.blocked = true;
        setTab('Squad');
        if sub == 'sheet' or sub == 'gear' then   -- (1.27) /sq gear [slot]: the profile window on its Gear view
            setOpen(true);
            local slot = tonumber(args[3] or '') or S.sheetSlot or (S.mates[1] and S.mates[1].slot);
            if slot then openSheet(slot, sub == 'gear' and 'gear' or nil) else S.sheetOpen[1] = true; say('no mate in the list yet; press Refresh first.'); end
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
    elseif sub == 'opacity' then
        -- /menu opacity <10-100>: the Squads button.  /menu opacity menu <10-100>: the menu's background.
        local what, v = 'button_opacity', tonumber(args[3] or '');
        if string.lower(tostring(args[3] or '')) == 'menu' then what, v = 'menu_opacity', tonumber(args[4] or ''); end
        if string.lower(tostring(args[3] or '')) == 'button' then v = tonumber(args[4] or ''); end
        if v then
            v = math.floor(math.max(10, math.min(100, v)));
            setCfg(what, v);
            say(string.format('%s opacity is now %d%%.', what == 'menu_opacity' and 'menu background' or 'Squads button', v));
        else
            say(string.format('/menu opacity <10-100>   the Squads button (solid under the mouse). Now: %d%%   |   /menu opacity menu <10-100>   the menu\'s background. Now: %d%%',
                math.floor(opacityOf('button_opacity') * 100 + 0.5), math.floor(opacityOf('menu_opacity') * 100 + 0.5)));
        end
    elseif sub == 'theme' then
        -- (1.27) /menu theme classic | squad | crimson: this character's theme, here and in Gambits
        local name = string.lower(tostring(args[3] or ''));
        if X.pickTheme(name) then
            say('theme: ' .. U.THEME_NAMES[name] .. '.');
        else
            say('/menu theme classic | squad | crimson   Now: ' .. tostring(U.THEME_NAMES[X.themeName]));
        end
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
        say('/menu  open or close  |  /menu squad|dualbox  |  /menu gambits (dualbox)  |  /menu button  |  /menu resetbutton  |  /menu scale <0.75-3>  |  /menu opacity <10-100>  |  /menu theme classic|squad|crimson  |  /sq  |  /sq gear [slot]');
    else
        setOpen(not S.open[1]);
    end
end);
