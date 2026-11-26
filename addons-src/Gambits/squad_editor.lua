--[[
GambitsV2 Squad editor: an in-game editor for your squad mates' Rule Sets (Gambits v2, milestone 2).

Everything you change here stays in this window until you press Save: editing, ordering and switching rules never talks
to the server. The server (!gsq, gambits_squad.lua) is asked only to Load, Save, Check and Delete; choosing a Rule Set
for a mate and applying it use the squad commands you could type yourself (!squad ruleset <slot> <num>, !squad reapply).
The server checks every set (it decides what a mate may use) and writes squad_rulesets_data.lua; nothing is stored by the
game client except an unsaved draft (config/addons/GambitsV2/squad_draft.lua).

Nothing is reported as done because a line was queued:
  Save / Delete  only on the server's ok; when the outcome is unknown (no answer, zoning, a lost save), the editor reads
                 the set list back before it says anything, and never writes again on its own
  Assign         confirmed by reading the mate's chosen set back from the server
  Apply          confirmed by reading back that the mates left and came back; otherwise "not confirmed"
Transport: transport.lua (one line at a time, >= 1 s apart, refused lines detected and sent again).
Saves: up to 32 rules of any valid length (server version 2 streams a save in up to 48 chunks; version 1 servers take
what fits in 16 lines).
]]

local M = {}
M.VERSION      = '2.0.0'
M.MAX_LINE     = 120     -- bytes, the whole /say line
M.MAX_RULES    = 32      -- the server's limit (hello) - the only limit players see
M.MAX_PARTS    = 16      -- version 1 servers (w)
M.MAX_CHUNKS   = 64      -- version 3 servers (x): 32 of the most complex valid rules need about 49
M.MAX_STREAM   = 6144    -- bytes of one save (the server's limit)
M.ROWS_SHOWN   = 14
M.NAME_MAX     = 24
M.APPLY_RECALL = 4.0     -- squad.lua: RECALL_WAIT_MS 4000, then CALL_GAP_MS 1500 per further mate
M.APPLY_GAP    = 1.5

local api = {}          -- given by GambitsV2.lua: now, input_open, queue_command, log, root, writefile, imgui, s ...
local T                 -- transport.lua
local S = {
    nonce = 0, server = nil, pings = {}, mates = {}, sets = {}, cat = nil, catJob = nil,
    mateSlot = nil, draft = nil, message = nil, messageOk = true, messageWarn = false, progress = nil, checks = {},
    confirmDelete = nil, apply = nil,
    -- (0.3.4) needApply[slot]: this editor saved a change to the set that mate runs and has not seen it called again
    -- (only used when the server does not report the live state); setCache / catCache: see M.open_set, M.load_catalog_for
    needApply = {}, setCache = {}, catCache = {},
}
M._S = S

function M.init(a)
    api = a or {}
    T = api.transport or T
    if T == nil then
        local ok, mod = pcall(require, 'transport')
        T = ok and mod or nil
    end

    assert(T, 'transport.lua is missing')
    -- the Trust-summoning spells (trust_spells.lua, generated): never offered as a Specific Spell
    M.TRUSTS = api.trust_spells
    if type(M.TRUSTS) ~= 'table' then
        local okT, mod = pcall(require, 'trust_spells')
        M.TRUSTS = okT and type(mod) == 'table' and mod or {}
    end

    -- (0.3.1) spell families, status effects and what gives them (gambits_data.lua, generated from the server's data):
    -- only for what the pickers show; without it nothing is filtered
    local data = api.addon_data
    if type(data) ~= 'table' then
        local okD, mod = pcall(require, 'gambits_data')
        data = okD and type(mod) == 'table' and mod or nil
    end

    M.set_data(data)
    -- (0.3.1) remembered view choices (the addon's settings): Show all spells/families, the Weapon Skills section open
    S.showAll = api.get_pref ~= nil and api.get_pref('show_all') == true
    S.wsOpen = api.get_pref ~= nil and api.get_pref('ws_open') == true
    S.rolesOpen = api.get_pref ~= nil and api.get_pref('roles_open') == true -- (0.3.2) the Party roles section open

    T.init({ now = api.now, queue_command = api.queue_command, input_open = api.input_open, log = api.log,
             config = api.transport_config })
    M.T = T
    M.load_draft()
end

local function now()
    return api.now and api.now() or os.clock()
end

-- ok: true (green), false (red, also logged), 'warn' (gold: not confirmed / wait)
local function say(text, ok)
    S.message, S.messageOk, S.messageWarn = text, ok ~= false, ok == 'warn'
    if api.log then
        api.log(text, ok == false)
    end
end
M.say = say

-- ---------------------------------------------------------------- rule codec (the same as gambits_squad.lua)
local KIND_CODE = { family = 'f', ja = 'j', spell = 's', ranged = 'r', nuke = 'n', burst = 'b',
                   waltz = 'w', samba = 'd', storm = 'e', helix = 'h' }
local CODE_KIND = { f = 'family', j = 'ja', s = 'spell', r = 'ranged', n = 'nuke', b = 'burst',
                   w = 'waltz', d = 'samba', e = 'storm', h = 'helix' }
-- (WotG, 2026-11-22) the DNC/SCH actions, which need a version 8 server (gambits_squad.lua)
M.WOTG_KINDS    = { waltz = true, samba = true, storm = true, helix = true }
M.NAMED_KINDS   = { family = true, ja = true, spell = true }   -- kinds with a name (ranged, nuke, burst have none)
M.MIN_SERVER    = 3                                             -- the wire format this editor writes (gambits_squad.lua)

local function split(text, sep)
    local out, start = {}, 1
    while true do
        local at = string.find(text, sep, start, true)
        if not at then
            out[#out + 1] = string.sub(text, start)
            return out
        end

        out[#out + 1] = string.sub(text, start, at - 1)
        start = at + #sep
    end
end
M.split = split

-- an editor row { on, target, cond, arg, cond2, arg2, kind, name, retry, level, id } <->
-- "1,PARTY,HPP_LT,50,,,f,CURE,[,LEVEL[,ID]]" (the same as gambits_squad.lua version 3; LEVEL and ID only when set;
-- ID only for a rule whose id is not "r<position>")
-- (0.3.3, server version 9) a role target's included / excluded roles ride in the TARGET field: "MELEE-TANK" (melee, not
-- tanks), "TANK.CASTER" (tanks or mages). In the row: r.rolesIn / r.rolesOut, role names joined by "." in M.ROLE_ORDER.
M.ROLE_ORDER  = { 'TANK', 'MELEE', 'CASTER', 'RANGED' }
M.ROLE_TARGET = { TANK = true, MELEE = true, CASTER = true, RANGED = true }
M.ROLE_SERVER = 9

function M.target_token(r)
    local text = r.target == nil and '' or tostring(r.target)
    for role in string.gmatch(r.rolesIn or '', '[^%.]+') do
        text = text .. '.' .. role
    end

    for role in string.gmatch(r.rolesOut or '', '[^%.]+') do
        text = text .. '-' .. role
    end

    return text
end

-- "MELEE-TANK" -> 'MELEE', nil, 'TANK' (nil target for a malformed field)
function M.parse_target(token)
    local parts = split(token or '', '-')
    local head = split(parts[1], '.')
    if head[1] == '' and #head == 1 and #parts == 1 then
        return nil, nil, nil, true -- (an empty target: as before)
    end

    for i, name in ipairs(head) do
        if not string.match(name, '^[A-Z][A-Z_]*$') then
            return nil
        end
    end

    for i = 2, #parts do
        if not string.match(parts[i], '^[A-Z][A-Z_]*$') then
            return nil
        end
    end

    local inc, exc = {}, {}
    for i = 2, #head do inc[#inc + 1] = head[i] end
    for i = 2, #parts do exc[#exc + 1] = parts[i] end
    return head[1], #inc > 0 and table.concat(inc, '.') or nil, #exc > 0 and table.concat(exc, '.') or nil
end

function M.role_set(text)
    local t = {}
    for role in string.gmatch(text or '', '[^%.]+') do
        t[role] = true
    end

    return t
end

-- turns one role on or off in r.rolesIn ('in') or r.rolesOut ('out'); a role is in one list at most, never the target's
-- own role; the lists stay in M.ROLE_ORDER
function M.set_role(r, which, role, on)
    local inc, exc = M.role_set(r.rolesIn), M.role_set(r.rolesOut)
    local mine, other = which == 'in' and inc or exc, which == 'in' and exc or inc
    if role == r.target then
        on = false
    end

    mine[role] = on or nil
    if on then
        other[role] = nil
    end

    local function text(set)
        local out = {}
        for _, name in ipairs(M.ROLE_ORDER) do
            if set[name] then out[#out + 1] = name end
        end

        return #out > 0 and table.concat(out, '.') or nil
    end

    r.rolesIn, r.rolesOut = text(inc), text(exc)
end

-- (0.3.3) one role's state in a rule: 'target' (the target's own role), 'out', 'in' or 'none'. A role in BOTH lists
-- (hand-made data) is 'out': the engine gives exclusion the precedence. Reading never changes the rule.
function M.role_state(r, role)
    if role == r.target then
        return 'target'
    elseif M.role_set(r.rolesOut)[role] then
        return 'out'
    elseif M.role_set(r.rolesIn)[role] then
        return 'in'
    end

    return 'none'
end

-- sets one role to 'none', 'in' or 'out' (never both; the target's own role is never changed)
function M.set_role_state(r, role, state)
    if role == r.target then
        return
    end

    M.set_role(r, 'in', role, state == 'in')
    M.set_role(r, 'out', role, state == 'out')
end

-- true when a role is in both lists, or the target's own role is in one of them (data the editor never makes itself)
function M.roles_conflict(r)
    local inc, exc = M.role_set(r.rolesIn), M.role_set(r.rolesOut)
    if r.target and (inc[r.target] or exc[r.target]) then
        return true
    end

    for role in pairs(exc) do
        if inc[role] then
            return true
        end
    end

    return false
end

-- the rule's roles as the engine reads them: a role in both lists only Excluded, the target's own role in neither list
-- (it always counts); the lists in M.ROLE_ORDER. Changes the rule; returns true when something changed.
function M.normalize_roles(r)
    if r.rolesIn == nil and r.rolesOut == nil then
        return false
    end

    local before = (r.rolesIn or '') .. '|' .. (r.rolesOut or '')
    local inc, exc = M.role_set(r.rolesIn), M.role_set(r.rolesOut)
    local function text(set, drop)
        local out = {}
        for _, name in ipairs(M.ROLE_ORDER) do
            if set[name] and not drop[name] and name ~= r.target then out[#out + 1] = name end
        end

        return #out > 0 and table.concat(out, '.') or nil
    end

    r.rolesIn, r.rolesOut = text(inc, exc), text(exc, {})
    return (r.rolesIn or '') .. '|' .. (r.rolesOut or '') ~= before
end

-- a normalised copy (for the editor's display and checks without touching the rule)
function M.normalized_copy(r)
    local c = {}
    for k, v in pairs(r) do c[k] = v end
    M.normalize_roles(c)
    return c
end
-- after the target changed: no role filter for a target without roles; the new target's own role leaves the lists
function M.fit_roles(r)
    if not M.ROLE_TARGET[r.target or ''] then
        r.rolesIn, r.rolesOut = nil, nil
    elseif r.rolesIn or r.rolesOut then
        M.set_role(r, 'in', r.target, false)
        M.set_role(r, 'out', r.target, false)
    end
end

-- why a rule's role filter is wrong, or nil
function M.role_problem(r)
    if r.rolesIn == nil and r.rolesOut == nil then
        return nil
    end

    if not M.ROLE_TARGET[r.target or ''] then
        return 'include / exclude roles only work with the targets Tank, Melee, Mage or Ranged'
    end

    local seen = { [r.target] = true }
    for _, text in ipairs({ r.rolesIn or '', r.rolesOut or '' }) do
        for role in string.gmatch(text, '[^%.]+') do
            if not M.ROLE_TARGET[role] then
                return 'unknown role ' .. role
            end

            if seen[role] then
                return 'a role is either included or excluded, and never the target\'s own role (' .. M.target_label(role) .. ')'
            end

            seen[role] = true
        end
    end

    if not (S.server and (S.server.version or 0) >= M.ROLE_SERVER) then
        return 'include / exclude roles need the server update (gambits_squad.lua version ' .. M.ROLE_SERVER .. ')'
    end

    return nil
end

function M.encode_rule(r)
    local function s(v)
        return v == nil and '' or tostring(v)
    end

    local fields = { r.on == false and '0' or '1', M.target_token(r), s(r.cond), s(r.arg), s(r.cond2), s(r.arg2),
        KIND_CODE[r.kind] or s(r.kind), s(r.name), s(r.retry) }
    if r.level ~= nil or r.id ~= nil then
        fields[#fields + 1] = s(r.level)
    end

    if r.id ~= nil then
        fields[#fields + 1] = s(r.id)
    end

    return table.concat(fields, ',')
end

-- nil for "?" (a rule the server could not send exactly) or anything malformed
function M.decode_rule(text)
    local f = split(text or '', ',')
    if #f < 8 or #f > 11 then
        return nil
    end

    for _, field in ipairs(f) do
        if not string.match(field, '^[%w_%-%.]*$') then
            return nil
        end
    end

    local function v(x)
        return x ~= nil and x ~= '' and x or nil
    end

    local kind = CODE_KIND[f[7]]
    if kind == nil or (f[1] ~= '1' and f[1] ~= '0') or f[3] == '' then
        return nil
    end

    if (M.NAMED_KINDS[kind] and f[8] == '') or (not M.NAMED_KINDS[kind] and f[8] ~= '') then
        return nil
    end

    local target, rolesIn, rolesOut, empty = M.parse_target(f[2])
    if target == nil and not empty then
        return nil
    end

    return { on = f[1] ~= '0', target = target, rolesIn = rolesIn, rolesOut = rolesOut, cond = v(f[3]), arg = v(f[4]),
             cond2 = v(f[5]), arg2 = v(f[6]), kind = kind, name = v(f[8]), retry = v(f[9]), level = v(f[10]), id = v(f[11]) }
end

function M.name_code(name)
    return (string.gsub(name or '', ' ', '_'))
end

-- conditions that describe what the ENEMY is doing: only meaningful with the target Enemy (the engine reads them on the
-- rule's target)
M.ENEMY_CONDS = { CASTING_MA = true, READYING_WS = true, READYING_MS = true, READYING_JA = true }

-- (job expansion) the modifiers MOD_LT can name (the same list as squad_rulesets.lua R.MODS): name -> low, high, label.
-- Each one counts down as it absorbs a hit: Utsusemi shadows, Blink images.
M.MODS = {
    UTSUSEMI  = { 1, 7, 'Utsusemi shadows' },
    BLINK     = { 1, 3, 'Blink images' },
}
M.MOD_ORDER = { 'UTSUSEMI', 'BLINK' }

-- "UTSUSEMI.2" -> 'UTSUSEMI', 2 (nil for anything else)
function M.mod_parse(arg)
    local name, n = string.match(tostring(arg or ''), '^([A-Z]+)%.(%d+)$')
    if name == nil or M.MODS[name] == nil then
        return nil
    end

    return name, tonumber(n)
end

-- (Bard song tiers, server version 8) Has / Missing effect may name ONE song of a song type: the argument "MARCH.2" is
-- the effect MARCH at tier 2 = Victory March; a plain "MARCH" is any March, as before. The songs of each type in tier
-- order (index = tier), the same as the server's enhancing_song.lua songPTable (the tests compare them). Etudes, Carols
-- and Mazurkas are left out: their songs share one tier, so a tier cannot tell them apart.
M.SONG_TIERS = {
    MARCH    = { 'ADVANCING_MARCH', 'VICTORY_MARCH', 'HONOR_MARCH' },
    MINUET   = { 'VALOR_MINUET', 'VALOR_MINUET_II', 'VALOR_MINUET_III', 'VALOR_MINUET_IV', 'VALOR_MINUET_V' },
    MADRIGAL = { 'SWORD_MADRIGAL', 'BLADE_MADRIGAL' },
    BALLAD   = { 'MAGES_BALLAD', 'MAGES_BALLAD_II', 'MAGES_BALLAD_III' },
    MINNE    = { 'KNIGHTS_MINNE', 'KNIGHTS_MINNE_II', 'KNIGHTS_MINNE_III', 'KNIGHTS_MINNE_IV', 'KNIGHTS_MINNE_V' },
    PAEON    = { 'ARMYS_PAEON', 'ARMYS_PAEON_II', 'ARMYS_PAEON_III', 'ARMYS_PAEON_IV', 'ARMYS_PAEON_V', 'ARMYS_PAEON_VI' },
    PRELUDE  = { 'HUNTERS_PRELUDE', 'ARCHERS_PRELUDE' },
    MAMBO    = { 'SHEEPFOE_MAMBO', 'DRAGONFOE_MAMBO' },
    OPERETTA = { 'SCOPS_OPERETTA', 'PUPPETS_OPERETTA' },
}
M.TIER_SERVER = 8

-- "MARCH.2" -> 'MARCH', 2;  "MARCH" -> 'MARCH', nil;  anything else -> arg, nil
function M.tier_parse(arg)
    local base, n = string.match(tostring(arg or ''), '^([A-Z][A-Z0-9_]*)%.(%d+)$')
    if base == nil then
        return arg, nil
    end

    return base, tonumber(n)
end

-- the song a tiered argument names ("MARCH.2" -> 'VICTORY_MARCH'), or nil
function M.tier_song(arg)
    local base, tier = M.tier_parse(arg)
    local songs = tier and M.SONG_TIERS[base or '']
    return songs and songs[tier] or nil
end

-- why a tiered effect argument is wrong, or nil (a plain effect name: nil)
function M.tier_problem(arg)
    local base, tier = M.tier_parse(arg)
    if tier == nil then
        return nil
    end

    local songs = M.SONG_TIERS[base or '']
    if songs == nil then
        return 'only song types (March, Minuet ...) can name one song'
    elseif songs[tier] == nil then
        return string.format('%s has songs 1-%d', M.pretty(base), #songs)
    elseif not (S.server and (S.server.version or 0) >= M.TIER_SERVER) then
        return 'one song of a type needs the server update (gambits_squad.lua version ' .. M.TIER_SERVER .. ')'
    end

    return nil
end

-- why a MOD_LT value is wrong, or nil
function M.mod_problem(arg)
    local name, n = M.mod_parse(arg)
    if name == nil then
        return 'needs Utsusemi shadows or Blink images and a number'
    end

    local m = M.MODS[name]
    if n < m[1] or n > m[2] then
        return string.format('needs a number %d-%d for %s', m[1], m[2], m[3])
    end

    return nil
end

-- (community feedback F1/F2, server version 11) the enemy family and count conditions. The values travel as text, exactly as
-- the server's gambits_squad.lua G.decodeCount reads them:
--   ENEMY_FAMILY  "GOBLIN"                                   the enemy is a Goblin (the rule may be for yourself or the party)
--   PARTY_COUNT   "AT_LEAST.2" or "AT_LEAST.2.ASLEEP"        party members (with that status) near the mate
--   ENEMY_COUNT   "AT_LEAST.3.30.10"                         monsters fighting the party within 10 yalms of the enemy,
--                                                             above 30% HP
M.COUNT_SERVER = 11
M.FAMILY_ORDER = {
    'GOBLIN', 'ORC', 'QUADAV', 'YAGUDO', 'SAHAGIN', 'TONBERRY', 'ANTICA', 'GIGAS', 'BUGBEAR', 'LAMIAE', 'MAMOOL_JA', 'TROLL',
    'DEMON', 'AHRIMAN', 'IMP', 'SKELETON', 'GHOST', 'CORSE', 'HOUND', 'DOOMED', 'QUTRUB', 'SHADOW', 'BAT', 'FLOCK_BAT', 'BIRD',
    'COCKATRICE', 'BEE', 'BEETLE', 'CRAWLER', 'SPIDER', 'SCORPION', 'FLY', 'ANTLION', 'WORM', 'SLIME', 'FLAN', 'LEECH',
    'CRAB', 'PUGIL', 'FROG', 'SEA_MONK', 'URAGNITE', 'BOMB', 'CLUSTER', 'GOLEM', 'DOLL', 'EVIL_WEAPON', 'MAGIC_POT',
    'BEHEMOTH', 'BUFFALO', 'COEURL', 'DHALMEL', 'MANTICORE', 'RABBIT', 'RAM', 'SHEEP', 'TIGER', 'OPO_OPO', 'LIZARD', 'RAPTOR',
    'EFT', 'ADAMANTOISE', 'BUGARD', 'MANDRAGORA', 'FUNGUAR', 'SAPLING', 'TREANT', 'CACTAUR', 'MORBOL', 'DRAGON', 'WYVERN',
    'HYDRA', 'PUK', 'ELEMENTAL', 'HIPPOGRYPH',
}
M.COUNT_CMPS = { 'AT_LEAST', 'EXACTLY', 'AT_MOST', 'MORE_THAN', 'FEWER_THAN' }
M.COUNT_CMP_LABEL = { AT_LEAST = 'at least', EXACTLY = 'exactly', AT_MOST = 'at most', MORE_THAN = 'more than', FEWER_THAN = 'fewer than' }
M.COUNT_CMP_SHORT = { AT_LEAST = '>= ', EXACTLY = '= ', AT_MOST = '<= ', MORE_THAN = '> ', FEWER_THAN = '< ' }
M.PCOUNT_STATUS = { '', 'ASLEEP', 'PETRIFICATION', 'POISON', 'PARALYSIS', 'SILENCE', 'BLINDNESS', 'DISEASE', 'CURSE_I', 'DOOM' }
M.PARTY_COUNT_MAX, M.ENEMY_COUNT_MAX = 18, 30

-- "AT_LEAST.2.ASLEEP" -> 'AT_LEAST', 2, 'ASLEEP' (status nil = every member); nil for anything else
function M.pcount_parse(arg)
    local cmp, n, status = string.match(tostring(arg or ''), '^([A-Z_]+)%.(%d+)%.?([A-Z0-9_]*)$')
    if cmp == nil or M.COUNT_CMP_LABEL[cmp] == nil then
        return nil
    end

    return cmp, tonumber(n), status ~= '' and status or nil
end

-- "AT_LEAST.3.30.10" -> 'AT_LEAST', 3, 30, 10 (hp 0 and radius 10 when left out); nil for anything else
function M.ecount_parse(arg)
    local text = tostring(arg or '')
    local cmp, n, hp, radius = string.match(text, '^([A-Z_]+)%.(%d+)%.(%d+)%.(%d+)$')
    if cmp == nil then
        cmp, n, hp = string.match(text, '^([A-Z_]+)%.(%d+)%.(%d+)$')
    end

    if cmp == nil then
        cmp, n = string.match(text, '^([A-Z_]+)%.(%d+)$')
    end

    if cmp == nil or M.COUNT_CMP_LABEL[cmp] == nil then
        return nil
    end

    return cmp, tonumber(n), tonumber(hp or '0'), tonumber(radius or '10')
end

function M.count_problem(kind, arg)
    if kind == 'y' then
        return string.match(tostring(arg or ''), '^[A-Z][A-Z0-9_]*$') == nil and 'needs a monster family' or nil
    elseif kind == 'p' then
        local cmp, n, status = M.pcount_parse(arg)
        if cmp == nil then
            return 'needs a comparison and a number'
        elseif n > M.PARTY_COUNT_MAX then
            return string.format('needs a number 0-%d', M.PARTY_COUNT_MAX)
        elseif status ~= nil and status ~= 'ASLEEP' and not string.match(status, '^[A-Z][A-Z0-9_]*$') then
            return 'needs a status effect'
        end
    elseif kind == 'q' then
        local cmp, n, hp, radius = M.ecount_parse(arg)
        if cmp == nil then
            return 'needs a comparison and a number'
        elseif n > M.ENEMY_COUNT_MAX then
            return string.format('needs a number 0-%d', M.ENEMY_COUNT_MAX)
        elseif hp > 99 then
            return 'the HP must be 0-99%'
        elseif radius < 1 or radius > 30 then
            return 'the reach must be 1-30 yalms'
        end
    end

    return nil
end

-- "Party members asleep: at least 2", "Enemies above 30% HP within 10 yalms of the enemy: at least 3", "Enemy is a Goblin"
function M.count_text(id, arg)
    if id == 'ENEMY_FAMILY' then
        return 'Enemy is ' .. (arg and arg ~= '' and M.pretty(arg) or '?')
    elseif id == 'PARTY_COUNT' then
        local cmp, n, status = M.pcount_parse(arg)
        if cmp == nil then
            return 'Party members: ?'
        end

        return string.format('Party members%s: %s %d', status == 'ASLEEP' and ' asleep' or (status and (' with ' .. M.pretty(status)) or ''),
            M.COUNT_CMP_LABEL[cmp], n)
    elseif id == 'ENEMY_COUNT' then
        local cmp, n, hp, radius = M.ecount_parse(arg)
        if cmp == nil then
            return 'Enemies: ?'
        end

        return string.format('Enemies%s within %d yalms: %s %d', hp > 0 and string.format(' above %d%% HP', hp) or '', radius,
            M.COUNT_CMP_LABEL[cmp], n)
    end

    return nil
end

function M.count_short(id, arg)
    if id == 'ENEMY_FAMILY' then
        return (arg and arg ~= '' and M.pretty(arg) or '?')
    elseif id == 'PARTY_COUNT' then
        local cmp, n, status = M.pcount_parse(arg)
        return string.format('%s %s%s', status == 'ASLEEP' and 'Asleep' or (status and M.pretty(status) or 'Members'),
            cmp and M.COUNT_CMP_SHORT[cmp] or '? ', tostring(n or '?'))
    elseif id == 'ENEMY_COUNT' then
        local cmp, n, hp = M.ecount_parse(arg)
        return string.format('Enemies%s %s%s', hp and hp > 0 and string.format(' >%d%%', hp) or '', cmp and M.COUNT_CMP_SHORT[cmp] or '? ',
            tostring(n or '?'))
    end

    return nil
end

-- a row the editor may not change: "?" from the server (kept exactly as it is), or a condition the server's catalog
-- does not describe (its value cannot be checked here). Returns why, or nil.
function M.protected(r, cat)
    if r.opaque then
        return 'it uses options this editor cannot show'
    end

    if cat and cat.conds then
        if r.cond and cat.conds[r.cond] == nil then
            return 'the server did not describe the condition ' .. r.cond
        end

        if r.cond2 and cat.conds[r.cond2] == nil then
            return 'the server did not describe the condition ' .. r.cond2
        end
    end

    return nil
end

-- Local checks before a save (the server checks again and decides): nil, or why
function M.check_draft(d, cat)
    if d == nil then
        return 'nothing to save'
    end

    local name = d.name or ''
    if name == '' or #name > M.NAME_MAX or not string.match(name, '^[%w %-]+$') then
        return 'the name must be 1-' .. M.NAME_MAX .. ' letters, digits, spaces or -'
    end

    if #d.rules == 0 then
        return 'add at least one rule'
    end

    if #d.rules > M.MAX_RULES then
        return 'at most ' .. M.MAX_RULES .. ' rules'
    end

    local on = 0
    for i, r in ipairs(d.rules) do
        if r.opaque then
            return 'rule ' .. i .. ' uses options this editor cannot show; saving here could lose them'
        end

        if r.on ~= false then
            on = on + 1
        end

        if not r.target or not r.cond or not r.kind then
            return 'rule ' .. i .. ' needs a target, a condition and an action'
        end

        if KIND_CODE[r.kind] == nil then
            return 'rule ' .. i .. ': unknown action ' .. tostring(r.kind)
        end

        local roleWhy = M.role_problem(r) -- (0.3.3) include / exclude roles
        if roleWhy then
            return 'rule ' .. i .. ': ' .. roleWhy
        end

        if M.NAMED_KINDS[r.kind] and (r.name == nil or r.name == '') then
            return 'rule ' .. i .. ': choose the ' .. (r.kind == 'spell' and 'spell' or r.kind == 'ja' and 'job ability' or 'spell family')
        end

        if not M.NAMED_KINDS[r.kind] and r.name ~= nil then
            return 'rule ' .. i .. ': ' .. r.kind .. ' takes no name'
        end

        for _, pair in ipairs({ { r.cond, r.arg }, { r.cond2, r.arg2 } }) do
            local c = pair[1] and cat and cat.conds[pair[1]]
            if pair[1] and cat and c == nil then
                return 'rule ' .. i .. ': unknown condition ' .. pair[1]
            end

            if c and c.kind == 'r' then
                local n = tonumber(pair[2] or '')
                if n == nil or n ~= math.floor(n) or n < c.lo or n > c.hi then
                    return string.format('rule %d: %s needs a whole number %d-%d', i, M.cond_label(pair[1]), c.lo, c.hi)
                end
            elseif c and c.kind == 'e' then
                if not pair[2] or not string.match(pair[2], '^[A-Z][A-Z0-9_]*$') and not string.match(pair[2], '^[A-Z][A-Z0-9_]*%.%d+$') then
                    return string.format('rule %d: %s needs a status effect', i, M.cond_label(pair[1]))
                end

                local why = M.tier_problem(pair[2]) -- (Bard song tiers) "MARCH.2"
                if why then
                    return string.format('rule %d: %s: %s', i, M.cond_label(pair[1]), why)
                end
            elseif c and c.kind == 'j' then
                if not pair[2] or not string.match(pair[2], '^[A-Z][A-Z0-9_]*$') then
                    return string.format('rule %d: %s needs a job ability', i, M.cond_label(pair[1]))
                end
            elseif c and c.kind == 'm' then
                local why = M.mod_problem(pair[2])
                if why then
                    return string.format('rule %d: %s %s', i, M.cond_label(pair[1]), why)
                end
            elseif c and (c.kind == 'y' or c.kind == 'p' or c.kind == 'q') then
                local why = M.count_problem(c.kind, pair[2]) -- (F1/F2, server version 11)
                if why then
                    return string.format('rule %d: %s %s', i, M.cond_label(pair[1]), why)
                end
            elseif c and c.kind == 'n' and pair[2] ~= nil and pair[2] ~= '' then
                return string.format('rule %d: %s takes no value', i, M.cond_label(pair[1]))
            end

            if pair[1] and M.ENEMY_CONDS[pair[1]] and r.target ~= 'TARGET' then
                return string.format('rule %d: "%s" needs the target Enemy', i, M.cond_label(pair[1]))
            end
        end

        if r.retry ~= nil and r.retry ~= '' then
            local n = tonumber(r.retry)
            if n == nil or n < 0 or n > 3600 or n ~= math.floor(n) then
                return 'rule ' .. i .. ': the wait must be 0-3600 seconds'
            end
        end

        if r.level ~= nil then
            local n = tonumber(r.level)
            if n == nil or n < 0 or n > 75 or n ~= math.floor(n) then
                return 'rule ' .. i .. ': the level must be 0-75'
            end
        end
    end

    if on == 0 then
        return 'switch on at least one rule'
    end

    return nil
end
local function save_items(d)
    local items = { table.concat({ tostring(d.num or 0), d.rev or '-', d.job, tostring(#d.rules), M.name_code(d.name) }, ',') }
    for _, r in ipairs(d.rules) do
        items[#items + 1] = M.encode_rule(r)
    end

    return items
end

-- Version 1 servers: "/say !gsq w <token> <seq> <total> <items joined by ;>", each line ends on a rule boundary.
-- Item 1 is the header "num,rev,JOB,rules,name". Returns lines | nil, why
function M.pack_save(d, token)
    local items = save_items(d)
    for total = 1, M.MAX_PARTS do
        local lines, ok = {}, true
        local i = 1
        while i <= #items do
            local seq = #lines + 1
            local prefix = string.format('/say !gsq w %s %d %d ', token, seq, total)
            local data = items[i]
            if #prefix + #data > M.MAX_LINE then
                return nil, 'rule ' .. (i - 1) .. ' is too long for this server version (it needs the server update)'
            end

            i = i + 1
            while i <= #items and #prefix + #data + 1 + #items[i] <= M.MAX_LINE do
                data = data .. ';' .. items[i]
                i = i + 1
            end

            lines[#lines + 1] = prefix .. data
            if #lines > total then
                ok = false
                break
            end
        end

        if ok and #lines == total then
            return lines
        end
    end

    return nil, 'the Rule Set is too large for this server version (it needs the server update for up to ' .. M.MAX_RULES .. ' rules)'
end

-- Version 2 servers: the same text as one stream, cut into chunks at any byte:
-- "/say !gsq x <token> <seq> <total> <chunk>". 32 rules of the longest valid kind fit. Returns lines | nil, why
function M.pack_stream(d, token, maxChunks)
    maxChunks = maxChunks or M.MAX_CHUNKS
    local text = table.concat(save_items(d), ';')
    if not string.match(text, '^[%w_%-%.,;]+$') then
        return nil, 'a rule has a character that cannot be sent'
    end

    if #text > M.MAX_STREAM then
        return nil, 'the Rule Set is larger than ' .. M.MAX_STREAM .. ' bytes'
    end

    local widest = string.format('/say !gsq x %s %d %d ', token, maxChunks, maxChunks)
    local size = M.MAX_LINE - #widest
    local chunks = {}
    for at = 1, #text, size do
        chunks[#chunks + 1] = string.sub(text, at, at + size - 1)
    end

    if #chunks > maxChunks then
        return nil, 'the Rule Set is too large to send'
    end

    local lines = {}
    for seq, chunk in ipairs(chunks) do
        lines[seq] = string.format('/say !gsq x %s %d %d %s', token, seq, #chunks, chunk)
    end

    return lines
end

-- the packing the connected server understands. This editor writes the version 3 rule format (spells, ranged, nuke,
-- burst, rule levels and ids), so an older server is refused here instead of misreading a rule.
function M.pack(d, token)
    local v = S.server and S.server.version or 1
    if v < M.MIN_SERVER then
        return nil, 'the server needs the update (gambits_squad.lua version ' .. M.MIN_SERVER .. ') to save from this editor'
    end

    if v < 8 then
        for i, r in ipairs(d and d.rules or {}) do
            if M.WOTG_KINDS[r.kind] then
                return nil, 'rule ' .. i .. ': ' .. tostring(r.kind) .. ' needs the server update (gambits_squad.lua version 8)'
            end
        end
    end

    return M.pack_stream(d, token, S.server.maxChunks)
end

-- ---------------------------------------------------------------- transport (transport.lua)
local function next_id()
    S.nonce = S.nonce + 1
    return tostring((os.time() % 100000) * 1000 + (S.nonce % 1000))
end
M.next_id = next_id

function M.enqueue(job)
    return T.enqueue(job)
end

function M.busy()
    return T.busy()
end

function M.owns_command(line)
    return T.owns(line)
end

function M.on_reply(fields)
    return T.on_reply(fields)
end

-- text_in: message = e.message_modified, original = e.message. true = hide this line
function M.text_in(message, original)
    M.panel_seen(original or message)
    return T.text_in(original, message)
end

local function busy_say()
    say('Wait a moment: the editor is still talking to the server.', 'warn')
    return false
end

-- ---------------------------------------------------------------- requests
-- a read request answered by item lines and an end line: GSQ|n|<kind>|...  GSQ|n|end|count
local function read_request(words, on_items, on_fail, what)
    local id = next_id()
    local items = {}
    local job
    job = {
        id = id,
        lines = { '/say !gsq ' .. words[1] .. ' ' .. id .. (words[2] and (' ' .. table.concat(words, ' ', 2)) or '') },
        on_retry = function() items = {} end,
        on_line = function(f)
            if f[3] == 'err' then
                job.error = (f[5] or f[4] or 'error')
                job.code = f[4] -- (the server's error code: callers can tell "not out" from a real problem)
                return 'fail'
            elseif f[3] == 'end' then
                -- the server counts the set / rule / mate / chk lines only (not hdr, nor prob notes; a rule sent in
                -- segments counts once). The catalog has its own, stricter check (M.parse_catalog).
                local counted = 0
                for _, it in ipairs(items) do
                    if it[3] ~= 'hdr' and it[3] ~= 'prob' and not (it[3] == 'rule' and string.match(it[5] or '', '^%d+/%d+$')
                        and not string.match(it[5], '^1/')) then
                        counted = counted + 1
                    end
                end

                if what ~= 'cat' and tonumber(f[4]) ~= counted then
                    job.error = 'the answer was incomplete'
                    return 'fail'
                end

                local okItems, why = on_items(items, f)
                if okItems == false then
                    job.error = why or 'the answer was not usable'
                    return 'fail'
                end

                return 'done'
            elseif f[3] == 'hello' or f[3] == 'pong' then
                on_items({ f })
                return 'done'
            end

            items[#items + 1] = f
            return nil
        end,
        on_fail = on_fail,
    }
    return M.enqueue(job)
end
M.read_request = read_request

function M.ping(count, gap)
    if M.busy() then
        return busy_say()
    end

    count = math.max(1, math.min(100, math.floor(tonumber(count) or 10)))
    S.pings, S.pingBase, S.pingOldGap = {}, T.stats(), nil
    if gap then
        S.pingOldGap = T.get_interval()
        T.set_interval(gap)
    end

    local function one(i)
        local job
        job = {
            id = next_id(),
            on_line = function(f, cur)
                if f[3] == 'pong' then
                    local t = now()
                    S.pings[#S.pings + 1] = { rtt = t - cur.sentAt, wall = t - cur.firstSentAt }
                    return 'done'
                end
            end,
            on_done = function()
                if i < count then
                    one(i + 1)
                else
                    M.ping_summary(count)
                end
            end,
            on_fail = function(why)
                M.ping_summary(count, why)
            end,
        }
        job.lines = { '/say !gsq ping ' .. job.id .. ' ' .. i }
        M.enqueue(job)
    end

    say(string.format('Ping: measuring %d round trips at %.2f s between lines...', count, T.get_interval()), 'warn')
    one(1)
    return true
end

function M.ping_summary(count, why)
    local n, lo, hi, sum, wall = #S.pings, math.huge, 0, 0, 0
    for _, p in ipairs(S.pings) do
        lo, hi, sum, wall = math.min(lo, p.rtt), math.max(hi, p.rtt), sum + p.rtt, wall + p.wall
    end

    local st, base = T.stats(), S.pingBase or { rejected = 0, resent = 0 }
    local refusals, resends, interval = st.rejected - base.rejected, st.resent - base.resent, st.interval
    if S.pingOldGap then
        T.set_interval(S.pingOldGap)
        S.pingOldGap = nil
    end

    if n == 0 then
        say('Ping: no answers' .. (why and (' (' .. why .. ')') or ''), false)
        return nil
    end

    local text = string.format('Ping: %d/%d answered; round trip min %.0f, avg %.0f, max %.0f ms; per request avg %.0f ms '
        .. '(with resends); refused by the game %d, sent again %d; interval %.2f s', n, count or n, lo * 1000, sum / n * 1000,
        hi * 1000, wall / n * 1000, refusals, resends, interval)
    if why then
        text = text .. ' - stopped: ' .. why
    end

    say(text, (why == nil and refusals == 0) and true or 'warn')
    return text
end

function M.refresh()
    read_request({ 'hello' }, function(items)
        local f = items[1]
        local version = tonumber(f[4]) or 1
        if version < M.MIN_SERVER then
            -- an older server sends the old catalog and cannot carry every rule form: nothing here would be safe
            S.server, S.serverWhy = false, string.format('the server has gambits_squad.lua version %d; this editor needs version %d',
                version, M.MIN_SERVER)
            say('The Squad editor needs the server update: ' .. S.serverWhy .. '.', false)
            return
        end

        -- (0.3.4) what the server says it can do beyond the protocol number (version 10: the 8th field, words with
        -- commas): live = the mates answer carries what each mate really runs; reapply1 = "!squad reapply <slot>"
        -- re-calls one mate. Nothing from an older server: neither is used.
        local caps = {}
        for word in string.gmatch(tostring(f[8] or ''), '[%w_]+') do
            caps[word] = true
        end

        S.server = { version = version, maxRules = tonumber(f[5]) or M.MAX_RULES, maxLine = tonumber(f[6]) or 120,
                     maxChunks = tonumber(f[7]) or M.MAX_CHUNKS, caps = caps }
        M.MAX_RULES = math.min(S.server.maxRules, 32)
        M.load_mates()
    end, function(why)
        S.server = false
        say('The Squad editor needs the server update (!gsq): ' .. why, false)
    end)
end

local function parse_mates(items)
    local mates = {}
    for _, f in ipairs(items) do
        mates[#mates + 1] = { slot = tonumber(f[4]), id = tonumber(f[5]), name = f[6], job = f[7], level = tonumber(f[8]),
                              sub = f[9] ~= '-' and f[9] or nil, chosen = tonumber(f[10]) or 0, out = f[11] == '1',
                              subLevel = tonumber(f[12] or '') } -- (version 4: the sub job's level; nil = not known)
        -- (0.3.4, server capability "live") what this mate really runs, as the server reports it (fields 13-17:
        -- state | why | number of the set running | fallback reason | rules left out). nil = an older server: the
        -- editor then never says that a set runs.
        if M.LIVE_STATES[f[13] or ''] then
            mates[#mates].live = { state = f[13], why = f[14] or '-', num = tonumber(f[15]) or 0, fb = tonumber(f[16]) or 0,
                                   dropped = tonumber(f[17]) or 0 }
        end
    end

    return mates
end
M.LIVE_STATES = { off = true, unknown = true, addon = true, set = true, job = true, fallback = true, pending = true }
M.LIVE_WHY = {
    job    = 'the main job was changed since the call',
    choice = 'another Rule Set (or none) was chosen since the call',
    edited = 'the running Rule Set was saved with changes since the call',
    gone   = 'the running Rule Set is no longer saved',
    role   = 'the Role or Mode was changed since the call',
}
M.LIVE_FB = {
    [1] = 'the chosen Rule Set no longer exists or is not valid',
    [2] = 'the chosen Rule Set number now belongs to a different set',
    [3] = 'none of its rules can be used at this level and job',
    [4] = 'Squads has no job rules for this job: Rule Sets do not apply',
}

function M.cap(word)
    return S.server and S.server.caps ~= nil and S.server.caps[word] == true or false
end

-- reads the squad back (no follow-up loads): on_mates(mates)
function M.read_mates(on_mates, on_fail)
    return read_request({ 'mates' }, function(items)
        S.mates = parse_mates(items)
        S.liveUnsure, S.liveFailed, S.liveAt = nil, nil, now() -- (what each mate runs is the server's word of this moment)
        for _, m in ipairs(S.mates) do
            if not m.out then
                S.needApply[m.slot] = nil -- (0.3.4: away: its next call applies whatever was saved)
            end
        end

        if S.roles and S.roles.rows then
            S.roles.stale = true -- (0.3.2: who is out may have changed: the party roles are loaded again when shown)
        end

        on_mates(S.mates)
    end, on_fail)
end

function M.load_mates()
    M.read_mates(function()
        -- (0.3.4) "/gambits show <slot>" (the Squads menu's Gambits button): that mate, once the squad is known
        if S.wantSlot ~= nil then
            local want = S.wantSlot
            S.wantSlot = nil
            for _, m in ipairs(S.mates) do
                if m.slot == want and S.mateSlot == nil then
                    S.mateSlot = want -- (the first load: nothing is open yet)
                end
            end
        end

        if S.mateSlot == nil and S.mates[1] then
            S.mateSlot = S.mates[1].slot
        end

        local m = M.mate()
        if m then
            M.load_sets(m.job)
            if S.catJob ~= M.catalog_key(m) then
                M.load_catalog_for(m)
            end
        end
    end, function(why) say('Could not load your squad: ' .. why, false) end)
end

local function mate_by_slot(mates, slot)
    for _, m in ipairs(mates) do
        if m.slot == slot then
            return m
        end
    end

    return nil
end

function M.mate()
    return mate_by_slot(S.mates, S.mateSlot)
end

local function parse_sets(items)
    local sets = {}
    for _, f in ipairs(items) do
        if f[3] == 'set' then
            sets[#sets + 1] = { num = tonumber(f[4]), job = f[5], rules = tonumber(f[6]), flags = f[7], rev = f[8], id = f[9],
                                name = f[10] or '' }
        end
    end

    return sets
end

function M.load_sets(job, done)
    S.progress = 'Loading Rule Sets...'
    read_request({ 'list', job }, function(items)
        S.sets = parse_sets(items)
        S.progress = nil
        if done then
            done(S.sets)
        end
    end, function(why)
        S.progress = nil
        say('Could not load the Rule Sets: ' .. why, false)
    end)
end

-- The catalog check, the same as gambits_squad.lua G.check (Lua 5.1 and 5.4 give the same number)
function M.check(text, h)
    h = h or 7
    for i = 1, #text do
        h = (h * 31 + string.byte(text, i)) % 1000000007
    end

    return h
end

M.CAT_KINDS  = { 't', 'c', 'f', 'j', 's' }
M.CATM_KINDS = { 't', 'c', 'f', 'j', 's', 'u' } -- (version 4, one mate's catalog: u = allowed by job and level, not confirmed)
local CAT_ENTRY = {
    t = '^[A-Z][A-Z_]*$',
    c = '^[A-Z][A-Z0-9_]*:[nrejmypq][:%d]*$', -- (j: a job ability argument, server version 5 when asked for with catm "j";
                                           --  m: a modifier and a number, MOD_LT, server version 6 with catm "jm";
                                           --  y / p / q: an enemy family, a party count, an enemy count, server version 11
                                           --  with catm "jmf")
    f = '^[A-Z][A-Z0-9_]*$',
    j = '^[A-Z][A-Z0-9_]*:%d+s?$',
    s = '^[A-Z][A-Z0-9_]*:%d+s?$',
    u = '^[A-Z][A-Z0-9_]*:%d+s?$',
}

-- Builds the catalog from the answer lines "cat|seq|kind|entries" and the end line "end|lines|t.c.f.j.s|check".
-- Every line must be there exactly once, in order, kinds in order, every entry well formed and not repeated, the counts
-- and the check equal: else nil, why (the old catalog stays, nothing is guessed).
function M.parse_catalog(items, endFields)
    local total = tonumber(endFields and endFields[4] or '')
    local counts = split(endFields and endFields[5] or '', '.')
    local wantCheck = tonumber(endFields and endFields[6] or '')
    local kinds = #counts == #M.CATM_KINDS and M.CATM_KINDS or M.CAT_KINDS
    if total == nil or #counts ~= #kinds or wantCheck == nil then
        return nil, 'the end of the list was not readable'
    end

    local bySeq = {}
    for _, f in ipairs(items) do
        local seq = tonumber(f[4] or '')
        if f[3] ~= 'cat' or seq == nil or seq < 1 or seq > total or seq ~= math.floor(seq) or #f ~= 6 then
            return nil, 'a line of the list was not readable'
        end

        if bySeq[seq] then
            return nil, 'line ' .. seq .. ' of the list came twice'
        end

        bySeq[seq] = f
    end

    local order = {}
    for i, k in ipairs(kinds) do
        order[k] = i
    end

    local lists = { t = {}, c = {}, f = {}, j = {}, s = {}, u = {} }
    local seen = { t = {}, c = {}, f = {}, j = {}, s = {}, u = {} }
    local check, lastKind = 7, 0
    for seq = 1, total do
        local f = bySeq[seq]
        if f == nil then
            return nil, 'line ' .. seq .. ' of ' .. total .. ' of the list is missing'
        end

        local kind = f[5]
        if order[kind] == nil or order[kind] < lastKind then
            return nil, 'the list came in the wrong order'
        end

        lastKind = order[kind]
        for _, entry in ipairs(split(f[6], ',')) do
            if not string.match(entry, CAT_ENTRY[kind]) then
                return nil, 'an entry of the list was cut or changed (' .. entry .. ')'
            end

            if seen[kind][entry] then
                return nil, 'an entry of the list came twice (' .. entry .. ')'
            end

            seen[kind][entry] = true
            lists[kind][#lists[kind] + 1] = entry
            check = M.check(kind .. ':' .. entry .. '\n', check)
        end
    end

    for i, k in ipairs(kinds) do
        if #lists[k] ~= tonumber(counts[i]) then
            return nil, string.format('the list has %d %s entries, the server sent %s', #lists[k], k, tostring(counts[i]))
        end
    end

    if check ~= wantCheck then
        return nil, 'the list does not match what the server sent'
    end

    -- perMate: the server's own list for one mate (catm): its abilities and spells are already exactly the mate's
    local cat = { targets = lists.t, conds = {}, condNames = {}, families = lists.f, jas = {}, spells = {}, unconfirmed = {},
                  perMate = kinds == M.CATM_KINDS }
    for _, v in ipairs(lists.c) do
        local p = split(v, ':')
        local spec = { kind = p[2], lo = tonumber(p[3]), hi = tonumber(p[4]) }
        if (spec.kind == 'r' and (spec.lo == nil or spec.hi == nil or #p ~= 4)) or (spec.kind ~= 'r' and #p ~= 2) then
            return nil, 'a condition of the list was not readable (' .. v .. ')'
        end

        cat.conds[p[1]] = spec
        cat.condNames[#cat.condNames + 1] = p[1]
    end

    for _, pair in ipairs({ { lists.j, cat.jas }, { lists.s, cat.spells }, { lists.u, cat.unconfirmed } }) do
        for _, v in ipairs(pair[1]) do
            local name, lvl, sub = v:match('^([%w_]+):(%d+)(s?)$')
            pair[2][#pair[2] + 1] = { name = name, level = tonumber(lvl), sub = sub == 's' }
        end
    end

    return cat
end

-- what the loaded catalog was made for (a new key means it must be loaded again)
function M.catalog_key(m)
    if S.server and (S.server.version or 0) >= 4 then
        return string.format('m%d:%s%d/%s%s', m.slot or 0, m.job or '?', m.level or 0, m.sub or '-', tostring(m.subLevel or '-'))
    end

    return (m.job or '?') .. (m.sub or '')
end

-- (version 4) the catalog of ONE squad mate, made by the server with the same rules a call uses; older servers: the job's
function M.load_catalog_for(m)
    if not (S.server and (S.server.version or 0) >= 4) then
        return M.load_catalog(m.job, m.sub)
    end

    local key = M.catalog_key(m)
    -- (0.3.4) the choices of a mate that was looked at before are used again without asking (the key holds the mate,
    -- its jobs and their levels, so a job change or a level up asks again; Refresh forgets them all)
    S.catCache = S.catCache or {}
    if S.catCache[key] then
        S.cat, S.catJob, S.catError = S.catCache[key], key, nil
        return
    end

    -- (version 5) "j": this editor reads conditions with a job ability argument (JA_ON_COOLDOWN)
    -- (version 6, job expansion) "jm": modifier arguments too (MOD_LT)
    -- (version 11, community feedback) "jmf": enemy family and count arguments too (ENEMY_FAMILY, PARTY_COUNT, ENEMY_COUNT)
    local words = { 'catm', tostring(m.slot) }
    if (S.server.version or 0) >= M.COUNT_SERVER then
        words[3] = 'jmf'
    elseif (S.server.version or 0) >= 6 then
        words[3] = 'jm'
    elseif (S.server.version or 0) >= 5 then
        words[3] = 'j'
    end

    read_request(words, function(items, endFields)
        local cat, why = M.parse_catalog(items, endFields)
        if cat == nil or not cat.perMate then
            why = why or 'the list was not made for this squad mate'
            S.catError = why
            say('The choices from the server were incomplete (' .. why .. '). Press Refresh.', false)
            return false, why
        end

        S.cat, S.catJob, S.catError = cat, key, nil
        S.catCache[key] = cat
        return true
    end, function(why)
        S.catError = why
        say('Could not load the choices for ' .. tostring(m.name) .. ': ' .. why, false)
    end, 'cat')
end

function M.load_catalog(job, sub)
    read_request({ 'cat', job, sub }, function(items, endFields)
        local cat, why = M.parse_catalog(items, endFields)
        if cat == nil then
            S.catError = why
            say('The choices from the server were incomplete (' .. why .. '). Press Refresh.', false)
            return false, why
        end

        S.cat, S.catJob, S.catError = cat, job .. (sub or ''), nil
        return true
    end, function(why)
        S.catError = why
        say('Could not load the choices for ' .. tostring(job) .. ': ' .. why, false)
    end, 'cat')
end

-- one set as the server has it: on_set(hdr, rule texts) - rules reassembled from their segments; every rule 1..count
-- exactly once, every segment in order ("?" stays "?")
local function fetch_set(num, on_set, on_fail)
    return read_request({ 'get', tostring(num) }, function(items, endFields)
        local hdr, parts = nil, {}
        for _, f in ipairs(items) do
            if f[3] == 'hdr' then
                hdr = { num = tonumber(f[4]), job = f[5], flags = f[6], rev = f[7], id = f[8], name = f[9] or '' }
            elseif f[3] == 'rule' then
                local i = tonumber(f[4] or '')
                local seg, segs = string.match(f[5] or '', '^(%d+)/(%d+)$')
                seg, segs = tonumber(seg), tonumber(segs)
                if i == nil or seg == nil or #f ~= 6 then
                    return false, 'a rule line was not readable'
                end

                local p = parts[i] or { segs = segs, have = {} }
                if p.segs ~= segs or p.have[seg] or seg < 1 or seg > segs then
                    return false, 'rule ' .. i .. ' came in broken pieces'
                end

                p.have[seg] = f[6]
                parts[i] = p
            end
        end

        local count, rules = tonumber(endFields and endFields[4] or ''), {}
        for i = 1, count or 0 do
            local p = parts[i]
            if p == nil then
                return false, 'rule ' .. i .. ' is missing'
            end

            local pieces = {}
            for seg = 1, p.segs do
                if p.have[seg] == nil then
                    return false, 'a piece of rule ' .. i .. ' is missing'
                end

                pieces[seg] = p.have[seg]
            end

            rules[i] = table.concat(pieces)
        end

        if hdr == nil or count == nil then
            return false, 'the Rule Set header is missing'
        end

        on_set(hdr, rules)
        return true
    end, on_fail)
end
M.fetch_set = fetch_set

-- Loads a set into the editor (as it is, or as a new copy). A rule the server could not send exactly ("?") is kept as
-- a visible, protected row: the set is then read-only, and a copy is refused (it would lose that rule).
function M.open_set(num, copy)
    local function install(hdr, texts)
        local d = { num = 0, rev = nil, job = nil, name = '', rules = {}, flags = '', dirty = copy and true or false }
        d.num, d.job, d.flags, d.rev, d.id, d.name = hdr.num, hdr.job, hdr.flags, hdr.rev, hdr.id, hdr.name
        local opaque = {}
        for i, text in ipairs(texts) do
            local r = M.decode_rule(text)
            if r == nil then
                r = { opaque = true, text = text, on = true }
                d.uneditable = true
                opaque[#opaque + 1] = i
            end

            d.rules[i] = r
        end

        S.progress = nil
        if copy and #opaque > 0 then
            say(string.format('Not copied: rule %s uses options this editor cannot show, and a copy would lose %s. '
                .. 'Open shows the set read-only.', table.concat(opaque, ', '), #opaque == 1 and 'it' or 'them'), false)
            return
        end

        if copy or not string.find(d.flags or '', 'o', 1, true) or string.find(d.flags or '', 'r', 1, true) or d.uneditable then
            d.readonly = not copy
        end

        -- (0.3.4) the rules as the server has them, to tell a later rename from a change of the rules
        d.savedRules = (not copy) and M.encodings(d.rules) or nil
        if copy then
            d.num, d.rev, d.id, d.flags, d.readonly = 0, nil, nil, 'o', false
            d.name = string.sub('Copy of ' .. d.name, 1, M.NAME_MAX)
        end

        local kept = S.draft ~= d and M.keep_unsaved() -- (beta polish: unsaved edits become the unsaved draft, never lost)
        S.draft, S.checks = d, {}
        say(copy and 'Copied into a new, unsaved Rule Set.' or ('Opened "' .. tostring(d.name) .. '" (Rule Set ' .. num .. ').'
            .. (kept and ' Your earlier unsaved changes are kept as the unsaved draft.' or '')
            .. (#opaque > 0 and (' Rule ' .. table.concat(opaque, ', ') .. ' uses options this editor cannot show: read-only.') or '')))
    end

    -- (0.3.4) a set that was opened before is shown at once, without asking the server again, while the server's list
    -- still names the same revision and id for it (the list is read again after every Save, Delete, Refresh and change
    -- of mate; a set changed elsewhere in between is still refused at Save by its revision, as before).
    S.setCache = S.setCache or {}
    local listed = nil
    for _, set in ipairs(S.sets) do
        if set.num == num then
            listed = set
        end
    end

    local hit = S.setCache[num]
    if hit and listed and listed.rev ~= nil and hit.hdr.rev == listed.rev and hit.hdr.id == listed.id then
        install(hit.hdr, hit.texts)
        return
    end

    S.progress = 'Loading Rule Set ' .. num .. '...'
    fetch_set(num, function(hdr, texts)
        S.setCache[num] = { hdr = hdr, texts = texts }
        install(hdr, texts)
    end, function(why)
        S.progress = nil
        say('Could not load the Rule Set: ' .. why, false)
    end)
end
-- ---------------------------------------------------------------- (beta polish) opening and switching without losing edits
-- Unsaved edits are never thrown away: before another set or another mate replaces them, they become the "unsaved draft"
-- (also written to squad_draft.lua), which "Restore unsaved draft" brings back. Returns true when it kept something.
function M.keep_unsaved()
    local d = S.draft
    if d and d.dirty and not d.readonly and not d.uneditable then
        M.save_draft_file()
        S.restorable = d
        return true
    end

    return false
end

-- One click on a Rule Set: select AND open it. With unsaved edits of another set open, ask first (M.confirm_open).
function M.select_set(num)
    S.selectedSet = num
    local d = S.draft
    if d and d.num == num and not d.copy then
        return -- (already open)
    end

    if d and d.dirty and not d.readonly and not d.uneditable then
        S.confirmOpen = num
        return
    end

    S.confirmOpen = nil
    M.open_set(num, false)
    S.sel = 1
end

-- the answer to "unsaved changes": true = keep them as the unsaved draft and open the set, false = keep editing
function M.confirm_open(open)
    local num = S.confirmOpen
    S.confirmOpen = nil
    if num == nil or not open then
        return
    end

    M.keep_unsaved()
    M.open_set(num, false)
    S.sel = 1
end

-- Another squad mate: the editor shows that mate's assigned Rule Set (or nothing), never the previous mate's
function M.switch_mate(slot)
    if slot == S.mateSlot then
        return
    end

    local kept = M.keep_unsaved()
    S.mateSlot, S.selectedSet, S.draft, S.sel, S.checks, S.confirmOpen, S.confirmDelete, S.ws = slot, nil, nil, nil, {}, nil, nil, nil
    local m = M.mate()
    if m then
        -- what this mate runs was read a while ago (it may have been changed in the Squads menu since): asked again,
        -- before its sets, and the bar says "Checking" until the answer is there
        if M.live_recheck(5) then
            M.live_read()
        end

        M.load_sets(m.job, function()
            m = M.mate() or m -- (the row of the answer above, when there was one)
            if m.chosen and m.chosen > 0 and S.draft == nil and S.mateSlot == m.slot then
                S.selectedSet = m.chosen
                M.open_set(m.chosen, false)
                S.sel = 1
            end
        end)
        M.load_catalog_for(m)
    end

    if kept then
        say('Your unsaved changes were kept as the unsaved draft ("Restore unsaved draft" brings them back).', 'warn')
    end
end

-- (0.3.4) "/gambits show <slot>": the window on that squad mate. With the squad known it is the same as picking the
-- mate in the list (unsaved edits are kept as the unsaved draft); before the first answer it is remembered.
function M.want_mate(slot)
    slot = tonumber(slot)
    if slot == nil then
        return false
    end

    for _, m in ipairs(S.mates) do
        if m.slot == slot then
            M.switch_mate(slot)
            return true
        end
    end

    S.wantSlot = slot
    return true
end

function M.new_set(job)
    M.keep_unsaved() -- (beta polish: earlier unsaved edits become the unsaved draft, never lost)
    S.draft = { num = 0, rev = nil, job = job, name = 'New ' .. job .. ' set', flags = 'o', dirty = true,
                rules = { { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' } } }
    S.checks = {}
    say('New Rule Set (not saved yet).')
end

-- ---------------------------------------------------------------- starter templates (Gambits WAR/PLD/RDM batch)
-- Small examples to learn the editor with: mainly the main job's own low-level abilities and spells, a few rules each.
-- One agreed exception: Basic Paladin's Provoke needs /WAR (without it that one rule is left out when the PLD is called). A template only fills a NEW, unsaved Rule Set in the editor: nothing is saved, assigned or applied, no saved
-- set is changed and the built-in job rules stay as they are. Assigned to a mate, a Rule Set replaces that mate's usual
-- job-action rules while it is assigned ("Use job rules" goes back to them).
M.TEMPLATES = {
    WAR = { {
        name = 'Basic Warrior',
        about = 'Provoke when the enemy attacks someone else and there is no tank (level 5); Defender while the WAR has the '
            .. 'enemy\'s attention (level 25), Berserk while it does not (level 15). Defender and Berserk cancel each other, so '
            .. 'the WAR switches only when the enemy\'s attention moves, and their recasts (3 and 5 minutes) keep it slow.',
        rules = {
            { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_PT_HAS_TANK', kind = 'ja', name = 'PROVOKE' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'DEFENDER', kind = 'ja', name = 'DEFENDER' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BERSERK', kind = 'ja', name = 'BERSERK' },
        },
    } },
    PLD = { {
        name = 'Basic Paladin',
        about = 'Shield Bash an enemy that is casting (level 15, needs a shield); Sentinel when HP is low (30); Cure the party '
            .. 'member with the lowest HP below 60 % (5, the PLD included); Provoke (only with /WAR) and Flash (37) when the '
            .. 'enemy attacks someone else; Cure itself below 75 %. Rules the PLD cannot use yet (no /WAR, too low) are left '
            .. 'out when it is called; the others still work.',
        rules = {
            { on = true, target = 'TARGET', cond = 'CASTING_MA', kind = 'ja', name = 'SHIELD_BASH' },
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '40', cond2 = 'NOT_STATUS', arg2 = 'SENTINEL', kind = 'ja', name = 'SENTINEL' },
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '60', kind = 'family', name = 'CURE' },
            { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'ja', name = 'PROVOKE' },
            { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'spell', name = 'FLASH' },
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '75', kind = 'family', name = 'CURE' },
        },
    } },
    WHM = { {
        name = 'Basic White Mage',
        about = 'Cure the party member with the lowest HP: the best Cure below 50 %, plain Cure (cheap) below 70 % (level 1); '
            .. 'Poisona a poisoned party member (6); Protect a party member without it (7, the best Protect it knows).',
        rules = {
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '70', kind = 'spell', name = 'CURE' },
            { on = true, target = 'PARTY', cond = 'STATUS', arg = 'POISON', kind = 'spell', name = 'POISONA' },
            { on = true, target = 'PARTY', cond = 'NOT_STATUS', arg = 'PROTECT', kind = 'family', name = 'PROTECT' },
        },
    } },
    RDM = { {
        name = 'Basic Red Mage',
        about = 'Cure the party member with the lowest HP when below half (level 3), Dia on an enemy without it (level 1), '
            .. 'Paralyze on an enemy without it, then wait 30 s (level 6).',
        rules = {
            { on = true, target = 'PARTY_LOWEST_HPP', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'DIA', kind = 'family', name = 'DIA' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'PARALYSIS', kind = 'family', name = 'PARALYZE', retry = '30' },
        },
    } },

    -- ------------------------------------------------------------ (job expansion 2026-11-21) the other jobs
    -- Levels from sql/abilities.sql and sql/spell_list.sql (v0.1.55); test_gambits_jobexp.lua checks every name and level
    -- against the server's tables. Rules a mate cannot use yet (level, sub job, expansion switched off) are left out by
    -- the server when it is called; the others still work.
    MNK = { {
        name = 'Basic Monk',
        about = 'Chakra when HP is below 40 % (level 35); Dodge while the MNK has the enemy\'s attention (15); Focus when it '
            .. 'is not on (25); Boost while it has not got the enemy\'s attention, at most every 30 s (5).',
        rules = {
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '40', kind = 'ja', name = 'CHAKRA' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'DODGE', kind = 'ja', name = 'DODGE' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'FOCUS', kind = 'ja', name = 'FOCUS' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BOOST', kind = 'ja', name = 'BOOST',
              retry = '30' },
        },
    } },
    BLM = { {
        name = 'Basic Black Mage',
        about = 'Magic burst: when a skillchain opens a burst window, the best spell that fits it (element, the enemy\'s '
            .. 'resistance, MP, recast, a cast that ends in time). Aspir the enemy when MP is below 30 % (level 25); Bio an '
            .. 'enemy without it (10, every 60 s at most); else nuke with the element the enemy is weakest to while MP is at '
            .. 'least 50 % and the BLM does not have the enemy\'s attention.',
        rules = {
            { on = true, target = 'TARGET', cond = 'MB_AVAILABLE', kind = 'burst' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'MPP_LT', arg = '30', kind = 'spell', name = 'ASPIR' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'BIO', kind = 'family', name = 'BIO', retry = '60' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'MPP_GTE', arg = '50', cond2 = 'NOT_HAS_TOP_ENMITY', kind = 'nuke' },
        },
    } },
    THF = { {
        name = 'Basic Thief',
        about = 'Sneak Attack (level 15) and Trick Attack (30) whenever they are ready: the squad moves the THF behind the '
            .. 'enemy (Sneak Attack) or behind the tank (Trick Attack) first, and gives up after 8 s (then waits 10 s). Steal '
            .. 'from the enemy (5). The weapon skill does not wait for them.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'SNEAK_ATTACK', kind = 'ja', name = 'SNEAK_ATTACK' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'TRICK_ATTACK', kind = 'ja', name = 'TRICK_ATTACK' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ja', name = 'STEAL' },
        },
    }, {
        name = 'Thief SATA Weapon Skill',
        about = 'Sneak Attack (level 15) and Trick Attack (30) once the THF has 1000 TP, for the weapon skill: the weapon '
            .. 'skill waits up to 8 s for the THF to get into place (never at 3000 TP, never while it has the enemy\'s '
            .. 'attention, never when it could close a skillchain). Steal from the enemy (5).',
        rules = {
            { on = true, target = 'SELF', cond = 'TP_GTE', arg = '1000', cond2 = 'NOT_STATUS', arg2 = 'SNEAK_ATTACK', kind = 'ja',
              name = 'SNEAK_ATTACK' },
            { on = true, target = 'SELF', cond = 'TP_GTE', arg = '1000', cond2 = 'NOT_STATUS', arg2 = 'TRICK_ATTACK', kind = 'ja',
              name = 'TRICK_ATTACK' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ja', name = 'STEAL' },
        },
    } },
    DRK = { {
        name = 'Basic Dark Knight',
        about = 'Stun an enemy that is casting (level 37, Rise of the Zilart); Drain the enemy when HP is below 50 % (10) '
            .. 'and Aspir it when MP is below 30 % (20) - checked on the DRK, cast on the enemy; Last Resort while the DRK '
            .. 'does not have the enemy\'s attention (15); Bio an enemy without it (15, every 60 s at most).',
        rules = {
            { on = true, target = 'TARGET', cond = 'CASTING_MA', kind = 'spell', name = 'STUN' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'HPP_LT', arg = '50', kind = 'spell', name = 'DRAIN' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'MPP_LT', arg = '30', kind = 'spell', name = 'ASPIR' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'LAST_RESORT', kind = 'ja',
              name = 'LAST_RESORT' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'BIO', kind = 'family', name = 'BIO', retry = '60' },
        },
    } },
    BST = { {
        name = 'Basic Beastmaster',
        about = 'The jug pet is the squad\'s: called by level, it fights what the BST fights and is tended below 50 % HP. '
            .. 'These rules are for the BST itself and depend on its sub job: Cure itself below 50 % (/WHM or /RDM), '
            .. 'Berserk while it does not have the enemy\'s attention (/WAR 15). Without such a sub job they are left out.',
        rules = {
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BERSERK', kind = 'ja', name = 'BERSERK' },
        },
    } },
    BRD = { {
        name = 'Basic Bard',
        about = 'Songs by party role (each song reaches only that role; you can change who is what with !squad partyrole): '
            .. 'Valor Minuet (level 3) and March (29) for the melee but not the tank, Mage\'s Ballad (25) for the mages who '
            .. 'are not melee, Knight\'s Minne (1) for the tank. Elegy (39) on an enemy without it, Foe Requiem (7) every '
            .. '60 s at most. A Bard gives at most two songs to one member, so no one is given more: a Paladin (Tank and '
            .. 'Melee on Auto) gets Minne, a Blue Mage (Melee and Mage) Minuet and March.',
        rules = {
            -- (0.3.3) Exclude Tank / Exclude Melee: no member is given more songs than its two slots (no recast loop)
            { on = true, target = 'MELEE', rolesOut = 'TANK', cond = 'NOT_STATUS', arg = 'MINUET', kind = 'family', name = 'VALOR_MINUET' },
            { on = true, target = 'MELEE', rolesOut = 'TANK', cond = 'NOT_STATUS', arg = 'MARCH', kind = 'family', name = 'MARCH' },
            { on = true, target = 'CASTER', rolesOut = 'MELEE', cond = 'NOT_STATUS', arg = 'BALLAD', kind = 'family', name = 'MAGES_BALLAD' },
            { on = true, target = 'TANK', cond = 'NOT_STATUS', arg = 'MINNE', kind = 'family', name = 'KNIGHTS_MINNE' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'ELEGY', kind = 'family', name = 'ELEGY' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'REQUIEM', kind = 'family', name = 'FOE_REQUIEM', retry = '60' },
        },
    } },
    RNG = { {
        name = 'Basic Ranger',
        about = 'Sharpshot (level 1) and Barrage (30) while the RNG does not have the enemy\'s attention, then ranged attacks. '
            .. 'A Rule Set replaces the squad\'s automatic ranged attacks, so the ranged attack rule must stay in it.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'SHARPSHOT', kind = 'ja', name = 'SHARPSHOT' },
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'BARRAGE', kind = 'ja', name = 'BARRAGE' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ranged' },
        },
    } },
    SAM = { {
        name = 'Basic Samurai',
        about = 'Hasso while the SAM does not have the enemy\'s attention (level 25), Seigan and Third Eye while it has '
            .. '(35 and 15); Meditate below 1000 TP (30) for the next weapon skill (the squad\'s weapon skill settings decide '
            .. 'which one). Hasso and Seigan cancel each other.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'HASSO', kind = 'ja', name = 'HASSO' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'SEIGAN', kind = 'ja', name = 'SEIGAN' },
            { on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY', cond2 = 'NOT_STATUS', arg2 = 'THIRD_EYE', kind = 'ja', name = 'THIRD_EYE' },
            { on = true, target = 'SELF', cond = 'TP_LT', arg = '1000', kind = 'ja', name = 'MEDITATE' },
        },
    } },
    NIN = { {
        name = 'Basic Ninja',
        about = 'Utsusemi: Ni (level 37) when fewer than 2 shadows are left, Ichi (12) when none are left. Kurayami (19) '
            .. 'and Hojo (23) on an enemy without Blind or Slow, every 60 s at most. Provoke (with /WAR) is switched off: '
            .. 'switch it on when this NIN tanks.',
        rules = {
            { on = true, target = 'SELF', cond = 'MOD_LT', arg = 'UTSUSEMI.2', kind = 'spell', name = 'UTSUSEMI_NI' },
            { on = true, target = 'SELF', cond = 'MOD_LT', arg = 'UTSUSEMI.1', kind = 'spell', name = 'UTSUSEMI_ICHI' },
            { on = false, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'ja', name = 'PROVOKE' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'BLINDNESS', kind = 'spell', name = 'KURAYAMI_ICHI', retry = '60' },
            { on = true, target = 'TARGET', cond = 'NOT_STATUS', arg = 'SLOW', kind = 'spell', name = 'HOJO_ICHI', retry = '60' },
        },
    } },
    DRG = { {
        name = 'Basic Dragoon',
        about = 'High Jump while the DRG has the enemy\'s attention (level 35, it sheds some), Jump (10) and High Jump '
            .. 'below 1000 TP for TP - checked on the DRG, used on the enemy. The wyvern is the squad\'s: Spirit Link (25) '
            .. 'gives it HP when it is badly hurt, unless this Rule Set uses Spirit Link itself.',
        rules = {
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'HAS_TOP_ENMITY', kind = 'ja', name = 'HIGH_JUMP' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'TP_LT', arg = '1000', kind = 'ja', name = 'JUMP' },
            { on = true, target = 'TRIGGER_SELF_ACTION_TARGET', cond = 'TP_LT', arg = '1000', kind = 'ja', name = 'HIGH_JUMP' },
        },
    } },
    BLU = { {
        name = 'Basic Blue Mage',
        about = 'Healing Breeze below 40 % HP (level 16), Pollen below 60 % (1); Cocoon (8), Metallic Body (8) and '
            .. 'Refueling (48) when they are not on; Head Butt an enemy that is casting (12). The squad\'s blue magic rules '
            .. 'decide which spells a BLU has.',
        rules = {
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '40', kind = 'spell', name = 'HEALING_BREEZE' },
            { on = true, target = 'SELF', cond = 'HPP_LT', arg = '60', kind = 'spell', name = 'POLLEN' },
            { on = true, target = 'TARGET', cond = 'CASTING_MA', kind = 'spell', name = 'HEAD_BUTT' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'DEFENSE_BOOST', kind = 'spell', name = 'COCOON' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'STONESKIN', kind = 'spell', name = 'METALLIC_BODY' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'HASTE', kind = 'spell', name = 'REFUELING' },
        },
    } },
    COR = { {
        name = 'Basic Corsair',
        about = 'Two rolls for the party: Chaos Roll (level 14, attack) and Hunter\'s Roll (11, accuracy) when they are not '
            .. 'on, then ranged attacks. Double-Up is not used. A Rule Set replaces the squad\'s automatic ranged attacks, so '
            .. 'the ranged attack rule must stay in it.',
        rules = {
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'CHAOS_ROLL', kind = 'ja', name = 'CHAOS_ROLL' },
            { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'HUNTERS_ROLL', kind = 'ja', name = 'HUNTERS_ROLL' },
            { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ranged' },
        },
    } },
}
-- (job expansion) no Summoner template: an avatar is the squad's (called by level, Blood Pacts on its own); a Rule Set
-- has no pet target to give it orders. PUP is not covered yet.

function M.templates_for(job)
    return M.TEMPLATES[job or ''] or {}
end

-- A new, unsaved Rule Set from a template (a copy: the template itself never changes). A target the server does not offer
-- (an older server without PARTY_LOWEST_HPP) becomes PARTY; a rule with another target or condition it does not offer
-- is left out. Returns the draft, or nil + why.
function M.new_from_template(job, index, cat)
    local t = M.templates_for(job)[index or 1]
    if t == nil then
        return nil, 'no template for ' .. tostring(job)
    end

    local offered = {}
    for _, target in ipairs(cat and cat.targets or {}) do
        offered[target] = true
    end

    -- (job expansion) a rule whose target or condition this server does not offer at all (an older server: no
    -- "Check Self -> Act on Enemy", no shadow count) is left out of the copy; Party member, lowest HP becomes Party member
    local function usable(copy)
        if cat and not offered[copy.target] then
            if copy.target ~= 'PARTY_LOWEST_HPP' then
                return false
            end

            copy.target = 'PARTY'
        end

        for _, c in ipairs({ copy.cond, copy.cond2 }) do
            if cat and cat.conds and cat.conds[c] == nil then
                return false
            end
        end

        -- (0.3.3) role filters need server version 9: on an older server the rule is kept without them (as before)
        if (copy.rolesIn or copy.rolesOut) and not (S.server and (S.server.version or 0) >= M.ROLE_SERVER) then
            copy.rolesIn, copy.rolesOut = nil, nil
        end

        return true
    end

    local rules, skipped = {}, 0
    for _, r in ipairs(t.rules) do
        local copy = {}
        for k, v in pairs(r) do
            copy[k] = v
        end

        if usable(copy) then
            rules[#rules + 1] = copy
        else
            skipped = skipped + 1
        end
    end

    if #rules == 0 then
        return nil, 'this server cannot use the template "' .. t.name .. '" (update the server)'
    end

    M.keep_unsaved() -- (beta polish: earlier unsaved edits become the unsaved draft, never lost)
    S.draft = { num = 0, rev = nil, job = job, name = t.name, flags = 'o', dirty = true, rules = rules, template = t.name }
    S.checks = {}
    say(string.format('"%s" loaded as a new Rule Set (not saved). Change it as you like, then Save; assigning it replaces '
        .. 'the mate\'s usual job rules while it is assigned.%s', t.name,
        skipped > 0 and string.format(' %d rule(s) left out: this server does not offer them yet.', skipped) or ''), skipped > 0 and 'warn' or nil)
    return S.draft
end

-- ---------------------------------------------------------------- (0.3.3) Rule Set import / export
-- Sharing a Rule Set: Export gives a SHARE CODE (share_code.lua: "GS1" + letters and digits, e.g. GS1Bq3...), Copy puts
-- it on the clipboard, and the other player pastes it into Import. The code holds the whole set (job, name, every rule
-- with its order, on/off, conditions, song tiers, role filters, action, wait, level and id) and a check number; it is
-- data only (read bit by bit, never run). Import makes a NEW, unsaved Rule Set in the editor - it never replaces a set,
-- never saves, assigns or applies anything; Save then checks it on the server as any other set.
-- Older shared text (GRS1|job|name|count|rules|check, the first 0.3.3 test builds) is still read the same way.
-- Spaces, line breaks and ` (Discord code blocks) around or inside a code or text are ignored.
M.IO_TAG, M.IO_VERSION = 'GRS', 1
M.IO_MAX_TEXT = 16384
M.IO_JOBS = { WAR = true, MNK = true, WHM = true, BLM = true, RDM = true, THF = true, PLD = true, DRK = true, BST = true,
              BRD = true, RNG = true, SAM = true, NIN = true, DRG = true, SMN = true, BLU = true, COR = true, PUP = true }

-- share_code.lua (given by the shell, else required next to this file); nil when it is missing
function M.share()
    if M.SC == nil then
        local SC = api.share_code
        if type(SC) ~= 'table' then
            local ok, mod = pcall(require, 'share_code')
            SC = ok and type(mod) == 'table' and mod or nil
        end

        M.SC = SC or false
    end

    return M.SC or nil
end

-- the rules of a draft as Save sends them, or nil + why (a rule the editor cannot show exactly is never shared)
local function shareable_texts(d)
    if d == nil or type(d.rules) ~= 'table' or #d.rules == 0 then
        return nil, 'open a Rule Set with at least one rule first'
    end

    if not M.IO_JOBS[d.job or ''] then
        return nil, 'the Rule Set has no known job'
    end

    local name = d.name or ''
    if name == '' or #name > M.NAME_MAX or not string.match(name, '^[%w %-]+$') then
        return nil, 'the name must be 1-' .. M.NAME_MAX .. ' letters, digits, spaces or -'
    end

    local texts = {}
    for i, r in ipairs(d.rules) do
        if r.opaque then
            return nil, 'rule ' .. i .. ' uses options this editor cannot show, so it cannot be shared exactly'
        end

        local text = M.encode_rule(r)
        if M.decode_rule(text) == nil then
            return nil, 'rule ' .. i .. ' is not complete'
        end

        texts[i] = text
    end

    return texts
end

-- a Rule Set (the editor's draft) -> its share code, or nil + why
function M.export_code(d)
    local texts, why = shareable_texts(d)
    if texts == nil then
        return nil, why
    end

    local SC = M.share()
    if SC == nil then
        return nil, 'share_code.lua is missing from the addon folder'
    end

    local rows = {}
    for i, t in ipairs(texts) do
        rows[i] = M.decode_rule(t) -- (exactly what the code will give back)
    end

    return SC.encode({ job = d.job, name = d.name, rules = rows })
end

-- the older text format (GRS1|...), kept so the editor can still write it for its own tests and comparisons
function M.export_text(d)
    local texts, why = shareable_texts(d)
    if texts == nil then
        return nil, why
    end

    local body = table.concat({ M.IO_TAG .. M.IO_VERSION, d.job, M.name_code(d.name), tostring(#texts), table.concat(texts, ';') }, '|')
    return body .. '|' .. tostring(M.check(body))
end

-- a name no Rule Set of that job in the loaded list has: "Name", else "Name 2", "Name 3" ... (true when renamed)
local function import_name(name, job)
    local taken = {}
    for _, set in ipairs(S.sets or {}) do
        if set.job == job or set.job == nil then
            taken[string.lower(set.name or '')] = true
        end
    end

    if not taken[string.lower(name)] then
        return name, false
    end

    for n = 2, 99 do
        local suffix = ' ' .. n
        local candidate = string.sub(name, 1, M.NAME_MAX - #suffix) .. suffix
        if not taken[string.lower(candidate)] then
            return candidate, true
        end
    end

    return name, false
end

-- the older GRS1 text -> job, name (with spaces), rule texts, or nil + why
local function read_grs1(clean)
    local at = string.find(clean, M.IO_TAG .. '%d+|')
    if at == nil then
        return nil, 'this is not a Gambits share code (it starts with GS1)'
    end

    clean = string.sub(clean, at)
    local version = tonumber(string.match(clean, '^' .. M.IO_TAG .. '(%d+)|'))
    if version ~= M.IO_VERSION then
        return nil, string.format('this Rule Set was shared in format %s; this Gambits reads format %d (update Gambits)',
            tostring(version), M.IO_VERSION)
    end

    if not string.match(clean, '^[%w_%-%.,;|]+$') then
        return nil, 'the text has characters a shared Rule Set never has (it was changed on the way)'
    end

    local f = M.split(clean, '|')
    if #f ~= 6 then
        return nil, 'the text is incomplete or has extra parts (' .. #f .. ' parts, 6 expected): copy all of it again'
    end

    local body = table.concat({ f[1], f[2], f[3], f[4], f[5] }, '|')
    if not string.match(f[6], '^%d+$') or tonumber(f[6]) ~= M.check(body) then
        return nil, 'the check number does not match: the text was cut or changed on the way (copy all of it again)'
    end

    local name = f[3]
    if #name > M.NAME_MAX or not string.match(name, '^[%w_%-]+$') then
        return nil, 'the name must be 1-' .. M.NAME_MAX .. ' letters, digits, spaces or -'
    end

    local texts = f[5] ~= '' and M.split(f[5], ';') or {}
    if tonumber(f[4]) == nil or tonumber(f[4]) ~= #texts then
        return nil, string.format('the text says %s rules but has %d', tostring(f[4]), #texts)
    end

    return f[2], (string.gsub(name, '_', ' ')), texts
end

-- a share code (or older GRS1 text) -> { draft = <a new unsaved set>, warnings = { ... } }, or nil + { problems }
-- cat (optional): the loaded catalog; its checks are used only when it is for the imported set's job
function M.parse_import(text, cat, catJob)
    local problems = {}
    local function fail(why)
        problems[#problems + 1] = why
        return nil, problems
    end

    if type(text) ~= 'string' or string.match(text, '^[%s`]*$') then
        return fail('nothing to import: paste a share code first')
    end

    if #text > M.IO_MAX_TEXT then
        return fail('the text is longer than ' .. M.IO_MAX_TEXT .. ' characters: that is not one Rule Set')
    end

    local clean = string.gsub(text, '[%s`]', '')
    local job, name, texts
    local SC = M.share()
    if SC and SC.looks_like(clean) then
        local set, why = SC.decode(clean)
        if set == nil then
            return fail(why)
        end

        job, name, texts = set.job, set.name, {}
        for i, row in ipairs(set.rules) do
            texts[i] = M.encode_rule(row)
        end
    elseif string.find(clean, M.IO_TAG .. '%d+|') then
        local why
        job, name, texts = read_grs1(clean)
        if job == nil then
            return fail(name)
        end
    elseif string.match(clean, '^GS%d') and not SC then
        return fail('share_code.lua is missing from the addon folder: this Gambits cannot read share codes')
    else
        return fail('this is not a Gambits share code (it starts with GS1)')
    end

    if not M.IO_JOBS[job or ''] then
        return fail('unknown job ' .. tostring(job))
    end

    if name == '' or #name > M.NAME_MAX or not string.match(name, '^[%w %-]+$') then
        return fail('the name must be 1-' .. M.NAME_MAX .. ' letters, digits, spaces or -')
    end

    if #texts == 0 or #texts > M.MAX_RULES then
        return fail('a Rule Set has 1-' .. M.MAX_RULES .. ' rules (this one has ' .. #texts .. ')')
    end

    local rules, ids = {}, {}
    for i, t in ipairs(texts) do
        local r = M.decode_rule(t)
        if r ~= nil then
            M.normalize_roles(r) -- (0.3.3) Include + Exclude of one role -> Exclude (what the engine does with it)
        end

        if r == nil then
            problems[#problems + 1] = 'rule ' .. i .. ' is not readable'
        else
            if r.id ~= nil then
                if ids[r.id] then
                    problems[#problems + 1] = 'rule ' .. i .. ' has the same id as rule ' .. ids[r.id]
                end

                ids[r.id] = i
            end

            -- (Bard song tiers) "MARCH.2" is checked here too: without a catalog check_draft cannot tell its kind
            for _, pair in ipairs({ { r.cond, r.arg }, { r.cond2, r.arg2 } }) do
                local tierWhy = (pair[1] == 'STATUS' or pair[1] == 'NOT_STATUS') and M.tier_problem(pair[2]) or nil
                if tierWhy then
                    problems[#problems + 1] = string.format('rule %d: %s: %s', i, M.cond_label(pair[1]), tierWhy)
                end
            end

            rules[i] = r
        end
    end

    if #problems > 0 then
        return nil, problems
    end

    local d = { num = 0, rev = nil, job = job, name = name, flags = 'o', dirty = true, rules = rules, imported = true }
    local why = M.check_draft(d, (cat and catJob == job) and cat or nil)
    if why then
        return fail(why)
    end

    local warnings = {}
    local renamed
    d.name, renamed = import_name(d.name, job)
    if renamed then
        warnings[#warnings + 1] = string.format('A %s Rule Set called "%s" exists: the import is named "%s".', job, name, d.name)
    end

    if not (cat and catJob == job) then
        warnings[#warnings + 1] = 'Checked for its form only: the choices of a ' .. job .. ' squad mate are not loaded. Save checks it on '
            .. 'the server; Check shows what a mate would leave out.'
    end

    return { draft = d, warnings = warnings }
end

-- puts a parsed import into the editor as a new, unsaved Rule Set (nothing saved, assigned or applied)
function M.import_apply(result)
    if type(result) ~= 'table' or type(result.draft) ~= 'table' then
        return false
    end

    local kept = M.keep_unsaved() -- (unsaved edits become the unsaved draft, never lost)
    S.draft, S.checks, S.sel = result.draft, {}, 1
    say(string.format('Imported "%s" (%s, %d rules) as a new Rule Set - not saved. Look it over, then Save; it is not assigned '
        .. 'to anyone.%s', result.draft.name, result.draft.job, #result.draft.rules,
        kept and ' Your earlier unsaved changes are kept as the unsaved draft.' or ''))
    return true
end

-- Export: the share code of the Rule Set open in the editor (as shown), kept for the Export box; nil + why
function M.export_current()
    local code, why = M.export_code(S.draft)
    S.io = S.io or {}
    if code == nil then
        S.io.code = nil
        say('Not exported: ' .. why, false)
        return nil
    end

    S.io.code, S.io.codeFor = code, S.draft
    say(string.format('Share code for "%s" ready (%d characters)%s. Press Copy Share Code, then paste it into Discord or a '
        .. 'message.', tostring(S.draft.name), #code, S.draft.dirty and ', with your unsaved changes as shown' or ''))
    return code
end

-- Copy Share Code: true when the clipboard took it
function M.copy_code(code)
    local g = api.imgui
    local ok = code ~= nil and g ~= nil and type(g.SetClipboardText) == 'function' and pcall(g.SetClipboardText, code)
    if ok then
        say('Share code copied to the clipboard.')
    else
        say('The clipboard could not be used: select the code in the box and copy it with Ctrl+C.', 'warn')
    end

    return ok == true
end

local function encodings(rules)
    local out = {}
    for i, r in ipairs(rules) do
        out[i] = M.encode_rule(r)
    end

    return out
end

M.encodings = encodings

local function same_list(a, b)
    if #a ~= #b then
        return false
    end

    for i = 1, #a do
        if a[i] ~= b[i] then
            return false
        end
    end

    return true
end

-- the server's rule texts in the editor's own encoding (so the comparison does not depend on spelling details)
local function normal(texts)
    local out = {}
    for i, text in ipairs(texts) do
        local r = M.decode_rule(text)
        out[i] = r and M.encode_rule(r) or ('?' .. tostring(text))
    end

    return out
end

-- the draft as it was when Save was pressed
local function snapshot(d)
    local known = {}
    for _, set in ipairs(S.sets) do
        known[set.num] = true
    end

    return { num = d.num or 0, job = d.job, name = d.name, rules = encodings(d.rules), known = known }
end

-- the server has (or wrote) the snapshot as set num: update the draft
local function saved(d, snap, num, rev, id)
    -- (0.3.4) did this Save change the RULES, or only the name? A mate that runs the set keeps running the same rules
    -- after a rename, so there is nothing to apply then (the server's own check is made from the rules only).
    d.rulesChanged = d.savedRules == nil or not same_list(d.savedRules, snap.rules)
    d.savedRules = snap.rules
    if S.setCache then
        S.setCache[num] = nil -- (its revision changed: read again when it is opened next)
    end

    d.num, d.rev, d.id, d.flags = num, rev, id, 'o'
    d.dirty = not same_list(encodings(d.rules), snap.rules) or d.name ~= snap.name
    if not d.dirty then
        M.delete_draft_file()
    end

    -- (0.3.4) every mate that is out and has this set chosen keeps running the rules of its last call: remembered here
    -- for a server that does not report it (one that does says "Apply needed" itself). And what was asked to follow
    -- this Save (Save & Apply, Save, Assign & Apply) runs from M.tick once the editor is free.
    if d.rulesChanged then
        for _, mate in ipairs(S.mates) do
            if mate.out and mate.chosen == num then
                S.needApply[mate.slot] = true
            end
        end
    end

    local follow = S.afterSave
    S.afterSave = nil
    if follow and not d.dirty then
        S.afterSaveRun = { kind = follow.kind, slot = follow.slot, num = num, rulesChanged = d.rulesChanged }
    end

    local m = M.mate()
    if m then
        M.load_sets(m.job)
    end
end

-- The outcome of a save is not known (no answer, a zone change, the server lost the unfinished save, or "stale"):
-- read the set list back and decide from what the server has. Never writes.
function M.verify_save(d, snap, why)
    S.progress = 'Not sure the save went through (' .. why .. '): checking on the server...'
    local function unresolved(w)
        S.progress = nil
        M.save_draft_file()
        say('Save NOT confirmed: ' .. why .. '; the check failed too (' .. tostring(w) .. '). Your rows are kept. '
            .. 'Press Refresh and look at the list before you save again.', 'warn')
    end

    read_request({ 'list', snap.job }, function(items)
        local cands = {}
        for _, set in ipairs(parse_sets(items)) do
            if snap.num > 0 then
                if set.num == snap.num then
                    cands[#cands + 1] = set.num
                end
            elseif not snap.known[set.num] and set.name == snap.name and set.rules == #snap.rules
                and string.find(set.flags or '', 'o', 1, true) then
                cands[#cands + 1] = set.num
            end
        end

        table.sort(cands, function(a, b) return a > b end)
        local function try(i)
            if cands[i] == nil then
                S.progress = nil
                M.save_draft_file()
                say('Not saved (checked on the server: ' .. why .. '). Your rows are kept; press Save to try again.', false)
                return
            end

            fetch_set(cands[i], function(hdr, texts)
                if hdr and hdr.name == snap.name and same_list(normal(texts), snap.rules) then
                    S.progress = nil
                    saved(d, snap, hdr.num, hdr.rev, hdr.id)
                    say(string.format('Saved as Rule Set %d (confirmed by reading it back from the server).', hdr.num))
                else
                    try(i + 1)
                end
            end, unresolved)
        end

        try(1)
    end, unresolved)
end

-- after (0.3.4): what follows once the server confirmed the Save: { kind = 'apply', slot } (Save & Apply: the mate
-- that runs this set is called again) or { kind = 'assign', slot } (Save, Assign & Apply). nil: Save only. A Save
-- that fails, or whose rows changed again meanwhile, is followed by nothing.
function M.save(after)
    if M.busy() or S.apply ~= nil then
        return busy_say()
    end

    S.afterSave = after
    local d = S.draft
    -- (0.3.3) a role saved as both Include and Exclude is saved as Exclude, the way it is shown and the engine reads it
    for _, r in ipairs(d and not d.readonly and d.rules or {}) do
        if not r.opaque then
            M.normalize_roles(r)
        end
    end

    local why = M.check_draft(d, S.cat)
    if why then
        say('Not saved: ' .. why, false)
        return false
    end

    if d.readonly then
        say('This Rule Set cannot be changed here. Use Copy to make your own.', false)
        return false
    end

    local token = next_id()
    local lines, perr = M.pack(d, token)
    if not lines then
        say('Not saved: ' .. perr, false)
        return false
    end

    local snap = snapshot(d)
    local job
    job = {
        id = token, lines = lines,
        on_line = function(f, cur)
            if f[3] == 'ack' then
                if tonumber(f[4]) ~= cur.index then
                    return nil -- an answer to an earlier copy of another part: ignore it
                end

                if cur.index == #lines and #lines > 1 then
                    job.lost = true -- the last part, only acknowledged: the server lost the earlier parts
                    job.error = 'the server lost the unfinished save'
                    return 'fail'
                end

                S.progress = string.format('Saving... %s/%d', f[4], #lines)
                return 'next'
            elseif f[3] == 'ok' then
                job.result = { tonumber(f[4]), f[5], f[6] }
                return 'done'
            elseif f[3] == 'err' then
                job.code = f[4]
                job.error = f[5] or f[4] or 'error'
                return 'fail'
            end
        end,
        on_done = function()
            S.progress = nil
            saved(d, snap, job.result[1], job.result[2], job.result[3])
            if S.afterSaveRun then
                say(string.format('Saved as Rule Set %d (server confirmed). %s', job.result[1],
                    S.afterSaveRun.kind == 'assign' and 'Assigning...' or 'Applying...'))
            else
                say(string.format('Saved as Rule Set %d (server confirmed). A mate that runs it keeps its earlier rules until it '
                    .. 'is called again (Apply).', job.result[1]))
            end
        end,
        on_fail = function(failWhy, kind)
            if kind == 'unknown' or job.lost or job.code == 'stale' then
                M.verify_save(d, snap, failWhy) -- it may have been written: look before saying anything
                return
            end

            S.progress = nil
            M.save_draft_file()
            say('Not saved: ' .. failWhy .. '. Your rows are kept.', false)
        end,
    }
    S.progress = string.format('Saving... 0/%d', #lines)
    return M.enqueue(job)
end

function M.delete_set(num, rev)
    if M.busy() then
        return busy_say()
    end

    local token = next_id()
    local job
    local function deleted()
        S.setCache[num] = nil
        say('Rule Set ' .. num .. ' deleted (server confirmed). A mate that used it goes back to its job rules.')
        if S.draft and S.draft.num == num then
            S.draft = nil
        end

        local m = M.mate()
        if m then
            M.load_sets(m.job)
        end
    end

    job = {
        id = token, lines = { string.format('/say !gsq del %s %d %s', token, num, rev or '-') },
        on_line = function(f)
            if f[3] == 'ok' then
                return 'done'
            elseif f[3] == 'err' then
                job.error = f[5] or f[4]
                return 'fail'
            end
        end,
        on_done = deleted,
        on_fail = function(why, kind)
            if kind ~= 'unknown' then
                say('Not deleted: ' .. why, false)
                return
            end

            local job2 = S.sets[1] and S.sets[1].job or (M.mate() and M.mate().job)
            S.progress = 'Not sure the delete went through: checking on the server...'
            read_request({ 'list', job2 }, function(items)
                S.progress = nil
                for _, set in ipairs(parse_sets(items)) do
                    if set.num == num then
                        say('Not deleted (checked on the server: ' .. why .. ').', false)
                        return
                    end
                end

                deleted()
            end, function(w)
                S.progress = nil
                say('Delete NOT confirmed: ' .. why .. '; the check failed too (' .. tostring(w) .. '). Press Refresh.', 'warn')
            end)
        end,
    }
    return M.enqueue(job)
end

function M.check_set(slot, num)
    S.checks = {}
    read_request({ 'chk', tostring(slot), tostring(num) }, function(items, endFields)
        for _, f in ipairs(items) do
            if f[3] == 'chk' then
                S.checks[tonumber(f[4]) or 0] = f[5]
            end
        end

        local n = 0
        for _ in pairs(S.checks) do
            n = n + 1
        end

        -- (version 4) the levels it was checked at: the summoned mate's current ones, Level Sync included
        local m = M.mate()
        local at = ''
        local lvl, sub, subLvl = tonumber(endFields and endFields[5] or ''), endFields and endFields[6], tonumber(endFields and endFields[7] or '')
        if lvl then
            at = string.format(' (checked at %s\'s current level: %s %d%s%s)', m and m.name or 'the mate', m and m.job or '', lvl,
                (sub and sub ~= '-') and string.format(' / %s %d', sub, subLvl or 0) or '',
                (m and m.level and lvl < m.level) and ', Level Sync' or '')
        end

        say((n == 0 and 'Check: the mate can use every rule now.' or ('Check: ' .. n .. ' rule(s) left out for this mate now (see the rows).')) .. at)
    end, function(why, kind, job)
        if job and job.code == 'notout' then
            -- the server checks with the mate's current levels and sub job, so it must be summoned; the set was not judged
            local m = M.mate()
            local who = m and m.name or 'the squad mate'
            say(string.format('Summon %s before checking this Rule Set. (Check uses %s\'s current level and sub job; '
                .. 'this is not a problem in the set.)', who, who), 'warn')
            return
        end

        say('Check: ' .. why, false)
    end)
end

-- (beta polish) the name of a Rule Set by its number, from the server's list for the mate's job (S.sets, read with
-- "list"); "Rule Set #n" when it is not in that list (another job's set, not loaded yet)
function M.set_label(num)
    if num == nil or num == 0 then
        return 'default job rules'
    end

    for _, set in ipairs(S.sets or {}) do
        if set.num == num and set.name and set.name ~= '' then
            return set.name
        end
    end

    return 'Rule Set #' .. tostring(num)
end

-- Assign: "!squad ruleset <slot> <num|off>" (no GSQ answer; setting a value twice is harmless), confirmed only by
-- reading the mate's chosen set back from the server. thenApply (beta polish, "Assign & Apply" / "Restore default job
-- rules"): once confirmed, and only when the mate is summoned, the existing Apply (!squad reapply) runs by itself.
function M.assign(slot, num, thenApply)
    if M.busy() then
        return busy_say()
    end

    local want, rounds = num or 0, 0
    local what = num and M.set_label(num) or 'its default job rules'
    local assign_round
    local function readback()
        S.progress = 'Assigning: reading it back from the server...'
        M.read_mates(function(mates)
            local m = mate_by_slot(mates, slot)
            if m and m.chosen == want then
                S.progress = nil
                if thenApply and m.out then
                    -- (M.tick starts Apply once the queue is free; 0.3.4: for this mate, with the squad as it was just
                    -- read, so it is not asked for a second time)
                    S.pendingApply = { slot = slot, mates = mates }
                    say(string.format('%s now uses %s (server confirmed). Applying...', m.name, what))
                elseif thenApply then
                    say(string.format('%s now uses %s (server confirmed). %s is not summoned: it applies when called.', m.name, what, m.name))
                else
                    say(string.format('%s now uses %s (server confirmed). It applies when %s is called again.', m.name, what, m.name))
                end
            elseif rounds < 2 then
                assign_round()
            else
                S.progress = nil
                say(string.format('Not assigned: the server still shows %s for slot %d.', m and (m.chosen > 0 and ('Rule Set ' .. m.chosen)
                    or 'the job rules') or 'no mate', slot), false)
            end
        end, function(why)
            S.progress = nil
            say('Assign NOT confirmed: ' .. why .. '. Press Refresh to see what the mate uses.', 'warn')
        end)
    end

    assign_round = function()
        rounds = rounds + 1
        S.progress = 'Assigning ' .. what .. '...'
        M.enqueue({
            id = 'assign', noreply = true, idempotent = true,
            lines = { string.format('/say !squad ruleset %d %s', slot, num and tostring(num) or 'off') },
            on_done = readback,
            on_fail = function(why, kind)
                if kind == 'unknown' then
                    readback() -- the server may have it anyway: look
                else
                    S.progress = nil
                    say('Not assigned: ' .. why, false)
                end
            end,
        })
    end

    assign_round()
    return true
end

-- (beta polish) Assign & Apply: the selected SAVED Rule Set. An unsaved edit of that same set is not what would be
-- assigned, so it is refused with a message instead of being saved or ignored silently.
function M.assign_apply(slot, num)
    local d = S.draft
    if num ~= nil and d and d.dirty and not d.readonly and d.num == num then
        say(string.format('%s has unsaved changes. Save first: Assign & Apply uses the saved Rule Set.', M.set_label(num)), 'warn')
        return false
    end

    return M.assign(slot, num, true)
end

-- Apply: "!squad reapply" sends the mates that are out away and calls them again (it must not run twice, so it is sent
-- again only when the game client refused it). Confirmed by reading back that they left and came back.
-- (0.3.4) opts.slot: the mate the Apply is for. When the server said it can (capability reapply1) only that mate is
--   re-called with "!squad reapply <slot>" and the others stay out; an older server gets the squad-wide line, and the
--   messages then say that the whole squad was called again. opts.mates: the squad as it was read a moment ago (the
--   read-back of Assign), so it is not asked for a second time.
-- Nothing is reported as applied before the server's own answer shows it.
function M.apply(opts)
    opts = opts or {}
    if M.busy() or S.apply ~= nil then
        return busy_say()
    end

    local function start(mates)
        local out = {}
        for _, m in ipairs(mates) do
            if m.out then
                out[#out + 1] = m
            end
        end

        local one = opts.slot and mate_by_slot(mates, opts.slot) or nil
        if opts.slot ~= nil and (one == nil or not one.out) then
            S.progress = nil
            say(string.format('%s is not summoned: nothing to apply now. The Rule Set applies when it is called.',
                one and one.name or 'That squad mate'), 'warn')
            return
        end

        if #out == 0 then
            S.progress = nil
            say('No squad mate is out. Call one first; the assignment applies when it is called.', false)
            return
        end

        local single = one ~= nil and M.cap('reapply1')
        local gone, others = out, {}
        if single then
            gone = { one }
            for _, m in ipairs(out) do
                if m.slot ~= one.slot then
                    others[#others + 1] = m
                end
            end
        end

        S.progress = single and ('Applying: sending ' .. one.name .. ' off...') or 'Applying: sending the squad off...'
        M.enqueue({
            id = 'apply', noreply = true, idempotent = false,
            lines = { single and string.format('/say !squad reapply %d', one.slot) or '/say !squad reapply' },
            on_done = function()
                local t = now()
                S.apply = { phase = 1, at = t + 1.0, out = gone, others = others, single = single, target = one, sentAt = t, tries = 0,
                            back = t + M.APPLY_RECALL + M.APPLY_GAP * (#gone - 1) + 2.0 }
            end,
            on_fail = function(why, kind)
                S.progress = nil
                if kind == 'rejected' then
                    say('Not applied: ' .. why .. '.', false)
                else
                    say('Apply NOT confirmed: ' .. why .. '. Press Refresh to see where your mates are before you try again.', 'warn')
                end
            end,
        })
    end

    if opts.mates then
        start(opts.mates)
        return true
    end

    S.progress = 'Applying: checking which mates are out...'
    M.read_mates(start, function(why)
        S.progress = nil
        say('Not applied: could not read your squad (' .. why .. ').', false)
    end)
    return true
end

local function names(list)
    local out = {}
    for _, m in ipairs(list) do
        out[#out + 1] = m.name
    end

    return table.concat(out, ', ')
end

-- (0.3.4) what the server reports for a mate that came back: text, ok (true: runs as chosen; 'warn': look at it)
function M.live_result(cur)
    local live = cur and cur.live
    if live == nil then
        return nil
    end

    if live.state == 'set' then
        return string.format('%s now runs %s (server confirmed)%s.', cur.name, M.set_label(live.num),
            live.dropped > 0 and string.format('; %d of its rules cannot be used at this level or job and are left out', live.dropped) or ''), true
    elseif live.state == 'job' then
        return string.format('%s now runs its default job rules (server confirmed).', cur.name), true
    elseif live.state == 'fallback' then
        return string.format('%s is back on its default job rules: %s.', cur.name, M.LIVE_FB[live.fb] or 'the chosen Rule Set could not be used'), 'warn'
    elseif live.state == 'pending' then
        return string.format('%s is back, but the server still reports Apply needed (%s).', cur.name, M.LIVE_WHY[live.why] or 'the settings changed'), 'warn'
    elseif live.state == 'addon' then
        return string.format('An add-on runs %s: Squads and Rule Sets do not.', cur.name), 'warn'
    end

    return nil
end

-- (0.3.4) Is what the editor knows about the mates still true? The live state is the server's, read with the mates
-- answer; it gets old when the window was closed for a while, when another mate is looked at later, and when
-- something is changed outside the editor (the Squads menu, a line typed in chat). There is no polling: the state is
-- marked "not sure" on those occasions, the bar says "Checking" instead of a state it cannot stand for, and ONE mates
-- request is sent when the editor is shown and free.
--   M.live_recheck(olderThan): marks it; with a number only when the last answer is older than that many seconds.
--   Returns true when it was marked. A server without the "live" capability is never asked (the editor claims
--   nothing about it anyway).
function M.live_recheck(olderThan)
    if not S.server or not M.cap('live') then
        return false
    end

    if olderThan ~= nil and S.liveAt ~= nil and now() - S.liveAt < olderThan then
        return false
    end

    S.liveUnsure, S.liveFailed = true, nil
    return true
end

function M.live_read()
    if S.liveReading then
        return
    end

    S.liveReading = true
    M.read_mates(function()
        S.liveReading = false
    end, function()
        -- no answer: not asked again by itself (Refresh, or the next occasion, asks); the bar says "Not confirmed"
        S.liveReading, S.liveUnsure, S.liveFailed = false, nil, true
    end)
end

local function live_tick()
    if not S.liveUnsure or S.liveReading or S.apply ~= nil or S.pendingApply or S.afterSaveRun or T.busy() then
        return
    end

    if S.shownAt == nil or now() - S.shownAt > 1.0 then
        return -- (the editor is not on screen: asked when it is shown again)
    end

    M.live_read()
end

-- The Squads menu's own answer from the server passes by in the chat stream ("squadpanel:rs|<slot>|<state>|<why>|
-- <live set>|<name>|<chosen set>|..."): the server's word on what each mate runs, asked for by the menu after every
-- change made there. It is only used to NOTICE a change: when a mate's line is not what it was the last time (or, the
-- first time, not what the editor knows), the editor asks its own question again. Nothing is taken over from the line.
function M.panel_seen(text)
    if type(text) ~= 'string' or not S.server then
        return
    end

    local at = string.find(text, 'squadpanel:rs|', 1, true)
    if at == nil then
        return
    end

    local slot, state, num, chosen = string.match(string.sub(text, at + 14), '^(%d+)|(%a+)|[^|]*|(%d+)|[^|]*|(%d+)|')
    slot = tonumber(slot)
    if slot == nil then
        return
    end

    S.panelRs = S.panelRs or {}
    local sig = state .. '|' .. num .. '|' .. chosen
    local before = S.panelRs[slot]
    S.panelRs[slot] = sig
    if before == sig then
        return
    end

    if before == nil then
        local m = mate_by_slot(S.mates, slot)
        if m ~= nil and m.live ~= nil and m.live.state == state and m.live.num == tonumber(num) and (m.chosen or 0) == tonumber(chosen) then
            return
        end
    end

    M.live_recheck()
end

-- the two Apply read-backs (sent off, then back); run from M.tick
local function apply_tick()
    local a = S.apply
    if a == nil or a.reading or now() < a.at or T.busy() then
        return
    end

    a.reading = true
    M.read_mates(function(mates)
        a.reading = false
        local still, missing = {}, {}
        for _, m in ipairs(a.out) do
            local cur = mate_by_slot(mates, m.slot)
            if cur and cur.out then
                still[#still + 1] = m
            else
                missing[#missing + 1] = m
            end
        end

        if a.phase == 1 then
            -- (0.3.4) one mate was asked for: did any of the others leave too? Then the server called the whole squad
            -- again (or they were sent off by hand), and the editor must not say that only one mate was re-called.
            for _, m in ipairs(a.others or {}) do
                local cur = mate_by_slot(mates, m.slot)
                if not (cur and cur.out) then
                    a.wide = true
                end
            end

            if #still == 0 then
                a.phase, a.at = 2, a.back
                S.progress = 'Applying: calling ' .. names(a.out) .. ' again...'
            else
                S.apply, S.progress = nil, nil
                local cur = a.target and mate_by_slot(mates, a.target.slot)
                if cur and cur.live and cur.live.state == 'addon' then
                    say(string.format('Not applied: an add-on owns %s, so Squads does not call it again.', cur.name), 'warn')
                else
                    say('Apply NOT confirmed: ' .. names(still) .. ' did not leave. Press Refresh before you try again.', 'warn')
                end
            end
        elseif #missing == 0 then
            S.apply, S.progress = nil, nil
            for _, m in ipairs(a.out) do
                S.needApply[m.slot] = nil
            end

            local scope = ''
            if a.single and not a.wide then
                scope = #a.others > 0 and ' The other mates stayed out.' or ''
            elseif a.single and a.wide then
                scope = ' The other mates left as well: the whole squad was called again.'
            elseif a.target and #a.out > 1 then
                -- an older server: there is only the squad-wide Apply, and the message says what it did
                scope = string.format(' This server cannot call one mate alone: every mate that was out was called again (%s).', names(a.out))
            end

            local text, ok = M.live_result(a.target and mate_by_slot(mates, a.target.slot) or nil)
            if text then
                say('Applied: ' .. text .. scope, ok == true and true or 'warn')
            else
                say('Applied: ' .. names(a.out) .. ' called again with the chosen Rule Sets (server confirmed).' .. scope)
            end
        elseif a.tries < 2 then
            a.tries, a.at = a.tries + 1, now() + 3.0
        else
            S.apply, S.progress = nil, nil
            say('Apply NOT confirmed: ' .. names(missing) .. ' sent off but not back yet. Press Refresh in a moment.', 'warn')
        end
    end, function(why)
        S.apply, S.progress = nil, nil
        say('Apply NOT confirmed: ' .. why .. '. Press Refresh.', 'warn')
    end)
end

-- (0.3.4) what follows a Save that was started with "Save & Apply" or "Save, Assign & Apply": run from M.tick once
-- the Save is confirmed and the editor is free. p = { kind, slot, num, rulesChanged }
function M.run_after_save(p)
    local m = mate_by_slot(S.mates, p.slot)
    if m == nil then
        return
    end

    if p.kind == 'assign' then
        M.assign(p.slot, p.num, true)
    elseif p.kind == 'apply' then
        if not p.rulesChanged then
            -- only the name changed: the mate runs the same rules, the server reports nothing to apply
            S.needApply[p.slot] = nil
            say(string.format('Saved (only the name changed: %s runs the same rules, nothing to apply).', m.name))
            return
        end

        M.apply({ slot = p.slot })
    end
end

function M.tick()
    T.tick()
    apply_tick()
    live_tick()
    if S.pendingApply and not T.busy() and S.apply == nil then
        local p = S.pendingApply
        S.pendingApply = nil
        M.apply(type(p) == 'table' and p or nil)
    end

    if S.afterSaveRun and not T.busy() and S.apply == nil and not S.pendingApply then
        local p = S.afterSaveRun
        S.afterSaveRun = nil
        M.run_after_save(p)
    end
end

-- ---------------------------------------------------------------- weapon skill settings (server version 5, squad_ws.lua)
-- Per squad mate and main job, separate from Rule Sets. Save stores (server confirmed), Apply puts the stored setting on
-- the called mate now, Reset stores "Squad default" (the automatic skillchains; the stored choices are kept for later).
M.WS_MODES = { 'Open', 'Close', 'Open + Close', 'Independent' }
M.WS_MODE_HELP = {
    'Opens skillchains: uses its weapon skill at your TP threshold, but only when another party member (you included) has '
        .. '1000 TP to close it, and never over a skillchain that is already going. It does not close.',
    'Closes skillchains: waits for an open skillchain and closes it from 1000 TP with a weapon skill that chains. '
        .. 'No threshold.',
    'Both: closes an open skillchain from 1000 TP; otherwise opens like Open, at your TP threshold.',
    'On its own: uses its weapon skill at your TP threshold without waiting for anyone. When a skillchain is open it '
        .. 'closes it if it can.',
}
M.WS_TPS = { 1000, 1500, 2000, 3000 }
M.WS_BEST_HELP = 'Best available: when a skillchain is open, the weapon skill that forms the best chain; otherwise the last '
    .. 'one of the mate\'s list (the server\'s order). It is not a damage calculation.'
M.WS_3000_HELP = 'At 3000 TP the mate always uses a weapon skill (in every mode), so TP is never held for ever.'

function M.ws_supported()
    return S.server and (S.server.version or 0) >= 5 or false
end

-- GSQ|n|ws|slot|JOB|src|ctl|mode|tp|ws|ltp|lws|out|usable|applied|eng
function M.parse_ws(f)
    if f == nil or f[3] ~= 'ws' or #f < 16 then
        return nil
    end

    local function tri(v) -- '1' true, '0' false, anything else nil (not known)
        if v == '1' then
            return true
        elseif v == '0' then
            return false
        end

        return nil
    end

    local d = { slot = tonumber(f[4]), job = f[5], source = f[6], control = tonumber(f[7]), mode = tonumber(f[8]),
                tp = tonumber(f[9]), ws = tonumber(f[10]), legacyTp = tonumber(f[11]) or 0, legacyWs = tonumber(f[12]) or 0,
                out = f[13] == '1', usable = tri(f[14]), applied = tri(f[15]), engine = f[16] == '1' }
    if d.slot == nil or d.mode == nil or d.tp == nil or d.ws == nil or (d.source ~= 'c' and d.source ~= 'd' and d.source ~= 'l') then
        return nil
    end

    return d
end

-- wsl lines "id:Name,..." -> { { id, name, label } ... } in the server's order, or nil + why
function M.parse_wsl(items)
    local list, seen = {}, {}
    for _, f in ipairs(items) do
        if f[3] ~= 'wsl' then
            return nil, 'a line of the weapon skill list was not readable'
        end

        for _, entry in ipairs(split(f[4] or '', ',')) do
            local id, name = string.match(entry, '^(%d+):([%w_]+)$')
            if id == nil or seen[id] then
                return nil, 'the weapon skill list was cut or changed (' .. entry .. ')'
            end

            seen[id] = true
            list[#list + 1] = { id = tonumber(id), name = name, label = (name:gsub('_', ' ')) }
        end
    end

    return list
end

-- the editable copy of a stored setting (Custom only when the server says Custom is in use)
local function ws_edit_from(d)
    return { control = d.source == 'c' and 1 or 0, mode = d.mode, tp = d.tp, ws = d.ws }
end
M.ws_edit_from = ws_edit_from

function M.ws_dirty()
    local w = S.ws
    if not (w and w.data and w.edit) then
        return false
    end

    local saved = ws_edit_from(w.data)
    return w.data.source == 'l' or saved.control ~= w.edit.control or saved.mode ~= w.edit.mode or saved.tp ~= w.edit.tp
        or saved.ws ~= w.edit.ws
end

-- (0.3.1 polish) whether the player has really changed the weapon skill settings in the editor: the edit differs from
-- what the server has stored. Unlike ws_dirty (the panel's "Save *"), a mate with no Gambits setting yet (source 'l')
-- is NOT edited; a change put back to the stored values is not edited either.
function M.ws_edited()
    local w = S.ws
    if not (w and w.data and w.edit) then
        return false
    end

    local saved = ws_edit_from(w.data)
    return saved.control ~= w.edit.control or saved.mode ~= w.edit.mode or saved.tp ~= w.edit.tp or saved.ws ~= w.edit.ws
end

function M.ws_name(id)
    if id == nil or id == 0 then
        return 'Best available'
    end

    return (S.wsNames and S.wsNames[id]) or ('weapon skill ' .. id)
end

local function ws_got(slot, items, keepEdit)
    local d = M.parse_ws(items[1])
    if d == nil or d.slot ~= slot then
        return false, 'the answer was not readable'
    end

    S.ws = S.ws and S.ws.slot == slot and S.ws or { slot = slot }
    S.ws.data = d
    if not keepEdit or S.ws.edit == nil then
        S.ws.edit = ws_edit_from(d)
    end

    return true, d
end

function M.ws_load(slot)
    S.ws = { slot = slot, loading = true }
    read_request({ 'wsg', tostring(slot) }, function(items)
        local ok, d = ws_got(slot, items)
        if not ok then
            return false, d
        end

        S.ws.loading = false
        if d.out then
            M.ws_list(slot)
        end

        return true
    end, function(why)
        S.ws = { slot = slot, error = why }
        say('Could not load the weapon skill settings: ' .. why, false)
    end)
end

function M.ws_list(slot)
    read_request({ 'wsl', tostring(slot) }, function(items)
        local list, why = M.parse_wsl(items)
        if list == nil then
            return false, why
        end

        if S.ws and S.ws.slot == slot then
            S.ws.list = list
        end

        S.wsNames = S.wsNames or {}
        for _, e in ipairs(list) do
            S.wsNames[e.id] = e.label
        end

        return true
    end, function(why, kind, job)
        if S.ws and S.ws.slot == slot then
            S.ws.list, S.ws.listWhy = nil, (job and job.code == 'notout') and 'notout' or why
        end
    end)
end

-- Save: the edit as the stored setting for the mate's job (server confirmed)
function M.ws_save(slot, edit)
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Saving the weapon skill settings...'
    read_request({ 'wss', tostring(slot), tostring(edit.control), tostring(edit.mode), tostring(edit.tp), tostring(edit.ws) },
        function(items)
            S.progress = nil
            local ok, d = ws_got(slot, items)
            if not ok then
                return false, d
            end

            say(string.format('Weapon skill settings saved (server confirmed): %s. %s', d.source == 'c' and 'Custom' or 'Squad default',
                d.out and (d.applied and 'In use now.' or 'Press Apply WS settings now to use them.') or 'They apply when the mate is called.'))
            return true
        end, function(why)
            S.progress = nil
            say('Weapon skill settings NOT saved: ' .. why, false)
        end)
    return true
end

-- Reset to Squad default: stores control 0 and keeps the other choices for later
function M.ws_reset(slot)
    local w = S.ws
    if not (w and w.data) then
        return false
    end

    w.edit = ws_edit_from(w.data)
    w.edit.control = 0
    return M.ws_save(slot, w.edit)
end

-- Apply: the stored setting on the called mate now
function M.ws_apply(slot)
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Applying the weapon skill settings...'
    read_request({ 'wsa', tostring(slot) }, function(items)
        S.progress = nil
        local ok, d = ws_got(slot, items, true)
        if not ok then
            return false, d
        end

        say(d.applied and 'Weapon skill settings in use now (server confirmed).' or 'Applied, but the server does not confirm it yet. Press Refresh.',
            d.applied and true or 'warn')
        return true
    end, function(why, kind, job)
        S.progress = nil
        if job and job.code == 'notout' then
            say('Not summoned: the saved weapon skill settings apply when the mate is called.', 'warn')
        else
            say('Weapon skill settings NOT applied: ' .. why, false)
        end
    end)
    return true
end

-- ---------------------------------------------------------------- unsaved draft
local function draft_path()
    local root = api.root and api.root()
    return root and (root .. 'squad_draft.lua') or nil
end

function M.save_draft_file()
    local path = draft_path()
    if path and api.writefile and S.draft then
        api.writefile(path, S.draft, 'GambitsV2: a Squad Rule Set that was not saved on the server yet.')
    end
end

function M.load_draft()
    local path = draft_path()
    if not path then
        return
    end

    local chunk = loadfile(path)
    if chunk then
        local ok, d = pcall(chunk)
        if ok and type(d) == 'table' and type(d.rules) == 'table' then
            S.restorable = d
        end
    end
end

function M.delete_draft_file()
    local path = draft_path()
    if path then
        os.remove(path)
    end

    S.restorable = nil
end

-- unloading: keep unsaved edits for the next session
function M.on_unload()
    if S.draft and S.draft.dirty and not S.draft.readonly then
        M.save_draft_file()
    end
end

-- ---------------------------------------------------------------- readable names (what players see; the data keeps the ids)
-- Wording follows the Gambits v2 WHM prototype (dev/gambits-v2-prototype/rule_model.py) and the launcher's rule editor
-- (launcher_rules.py). Anything without an entry is shown as a tidied name ("SOME_NAME" -> "Some Name").
M.TARGET_LABELS = { SELF = 'Self', PARTY = 'Party member', PARTY_LOWEST_HPP = 'Party member, lowest HP', TANK = 'Tank',
                    CASTER = 'Mage', MELEE = 'Melee', RANGED = 'Ranged', TOP_ENMITY = 'Ally with aggro',
                    TARGET = 'Enemy (current target)', MASTER = 'Master (you)',
                    TRIGGER_SELF_ACTION_TARGET = 'Check Self -> Act on Enemy' }
-- what each target really means in the engine (gambits_container.cpp), shown as a tooltip
M.TARGET_HELP = {
    SELF = 'The squad mate itself.',
    PARTY = 'The first party member, in party order, that matches the conditions.',
    PARTY_LOWEST_HPP = 'The party member with the lowest HP % that matches the conditions (alive, within 15 yalms; '
        .. 'equal HP % keeps party order). Good for healing.',
    TANK = 'A party member whose main job is PLD or RUN, or one given the role tank with !squad partyrole.',
    CASTER = 'A party member whose main job is WHM, BLM, RDM, BRD, SMN, BLU, SCH, GEO or RUN, or one given the role mage '
        .. 'with !squad partyrole.',
    MELEE = 'A party member whose main job is a melee job (WAR MNK THF PLD DRK BST SAM NIN DRG BLU PUP DNC RUN), or one '
        .. 'given the role melee with !squad partyrole.',
    RANGED = 'A party member whose main job is RNG or COR, or one given the role ranged with !squad partyrole.',
    TOP_ENMITY = 'The party member the enemy is attacking (highest enmity).',
    TARGET = 'The enemy the squad mate is fighting.',
    MASTER = 'You, the player.',
    TRIGGER_SELF_ACTION_TARGET = 'The conditions are checked on the squad mate itself, the action goes to the enemy. '
        .. 'E.g. "MP below 50 %" -> Aspir the enemy, or "HP below 50 %" -> Drain the enemy.',
}
-- (role clarity) the four role targets are Gambits Party Roles, never the Squad menu's Role. Text only: who a target
-- means is unchanged (the server's party roles decide).
M.PARTY_ROLE_NOTE = '\n\nGambits Party Role: decides who this target is. Not the Squad menu\'s Squad Role, which only '
    .. 'filters default job rules (a Rule Set replaces those and is not filtered).'
for _, key in ipairs({ 'TANK', 'CASTER', 'MELEE', 'RANGED' }) do
    M.TARGET_HELP[key] = M.TARGET_HELP[key] .. M.PARTY_ROLE_NOTE
end
-- (role clarity) the set panel's "uses: default job rules": the editor does not know a mate's Squad Role, so this
-- only says how the two relate
M.DEFAULT_RULES_HELP = 'Default job rules: the job\'s built-in rules, filtered by the Squad Role and Mode (Squad menu; '
    .. 'e.g. Damage cures only below 30% HP). An assigned Rule Set replaces them and is not filtered.'
M.KIND_LABELS   = { family = 'Best of Family', spell = 'Specific Spell', ja = 'Job Ability', ranged = 'Ranged attack',
                    nuke = 'Best nuke (weakness)', burst = 'Magic burst', waltz = 'Best Curing Waltz',
                    samba = 'Best Samba', storm = 'Storm of the day', helix = 'Helix of the day' }
-- (job expansion) offered for new rules: ranged (RNG/COR), nuke (the best nuke for the enemy's weakness) and burst (the
-- best spell for the open magic burst window) too
M.NEW_KINDS     = { 'family', 'spell', 'ja', 'ranged', 'nuke', 'burst', 'waltz', 'samba', 'storm', 'helix' }
M.KIND_HELP     = {
    family = 'The best spell of a family the mate knows (e.g. Cure -> Cure IV).',
    spell  = 'One exact spell.',
    ja     = 'One job ability.',
    ranged = 'A ranged attack (needs a ranged weapon and ammunition).',
    nuke   = 'The strongest elemental nuke of the element the enemy is weakest to.',
    burst  = 'The best spell for the open magic burst: an element of the skillchain, the enemy\'s weakest resistance, '
        .. 'enough MP, not on recast, and a cast that ends before the window closes. Use it with "A magic burst is possible".',
    waltz  = 'DNC: the strongest Curing Waltz the mate\'s level and TP allow. Use it with "HP below" on a party target.',
    samba  = 'DNC: Haste Samba when the party has a healer (level 66+), else the best Drain Samba. Use it with "No samba '
        .. 'active" on Self.',
    storm  = 'SCH: the storm of the day\'s element (Firestorm on Firesday...). Use it with "No storm active" on Self.',
    helix  = 'SCH: the helix of the day\'s element on the enemy. Pair it with the storm.',
}

-- The condition builder (Target -> Conditions -> Action): a subject, a comparison and a value. Each pair is one engine
-- condition; nothing here is emulated. Conditions outside it (level, random, timer, ...) stay as they are in existing
-- rules and are shown with their own names.
M.SUBJECTS = {
    { key = 'ALWAYS',  label = 'Always',      ops = { { 'always', 'ALWAYS' } } },
    { key = 'HP',      label = 'HP',          ops = { { 'below', 'HPP_LT' }, { 'at least', 'HPP_GTE' } }, unit = '%', default = 50 },
    { key = 'MP',      label = 'MP',          ops = { { 'below', 'MPP_LT' }, { 'at least', 'MPP_GTE' } }, unit = '%', default = 50 },
    -- (server version 5) MP of characters that have MP: false for a target without MP (a Warrior), unlike MP above
    { key = 'MPUSER',  label = 'MP (mages)',  ops = { { 'below', 'HAS_MP_MPP_LT' }, { 'at least', 'HAS_MP_MPP_GTE' } }, unit = '%',
      default = 50 },
    { key = 'HASMP',   label = 'Uses MP',     ops = { { 'yes (has an MP pool)', 'HAS_MP' } } },
    { key = 'TP',      label = 'TP',          ops = { { 'below', 'TP_LT' }, { 'at least', 'TP_GTE' } }, unit = 'TP', default = 1000 },
    { key = 'MISSING', label = 'Missing HP',  ops = { { 'at least', 'HP_MISSING' } }, unit = 'HP', default = 500 },
    { key = 'AGGRO',   label = 'Aggro',       ops = { { 'has it (the mate itself)', 'HAS_TOP_ENMITY' },
                                                      { 'does not have it', 'NOT_HAS_TOP_ENMITY' } } },
    -- (hotfix 2026-11-21) the engine's party tank test (a party member whose main job is NIN, PLD or RUN; the rule's
    -- target does not matter). The Basic Warrior starter uses NOT_PT_HAS_TANK, which the builder could not offer.
    { key = 'PTTANK',  label = 'Party tank',  ops = { { 'there is one (NIN, PLD or RUN)', 'PT_HAS_TANK' },
                                                      { 'there is none', 'NOT_PT_HAS_TANK' } } },
    { key = 'STATUS',  label = 'Status',      ops = { { 'has', 'STATUS' }, { 'is missing', 'NOT_STATUS' } } },
    { key = 'ENEMY',   label = 'Enemy',       ops = { { 'is casting a spell', 'CASTING_MA' }, { 'is readying a weapon skill', 'READYING_WS' },
                                                      { 'is readying a special move', 'READYING_MS' },
                                                      { 'is readying a job ability', 'READYING_JA' } }, enemyOnly = true },
    -- (server version 5) the mate's own recast of a job ability is running (whatever the rule's target is)
    { key = 'COOLDOWN', label = 'Ability on Cooldown', ops = { { 'is on cooldown (the mate\'s)', 'JA_ON_COOLDOWN' } } },
    -- (job expansion, server version 6) Utsusemi shadows / Blink images left below a number (MOD_LT): Utsusemi again
    -- before the last shadow goes
    { key = 'SHADOWS', label = 'Shadows / images', ops = { { 'below', 'MOD_LT' } }, default = 'UTSUSEMI.2' },
    -- (community feedback F1/F2, server version 11) the enemy's family, and counts: offered only when the server's catalog
    -- describes them (catm "jmf")
    { key = 'FAMILY',  label = 'Enemy family',  ops = { { 'is', 'ENEMY_FAMILY' } }, default = 'GOBLIN' },
    { key = 'PCOUNT',  label = 'Party members', ops = { { 'count', 'PARTY_COUNT' } }, default = 'AT_LEAST.2.ASLEEP' },
    { key = 'ECOUNT',  label = 'Enemies',       ops = { { 'count', 'ENEMY_COUNT' } }, default = 'AT_LEAST.3.0.10' },
    -- (job expansion) the advanced conditions: offered only with "More conditions" ticked (a saved rule with one is
    -- always shown)
    { key = 'SKILLCHAIN', label = 'Skillchain', ops = { { 'a magic burst is possible', 'MB_AVAILABLE' },
                                                        { 'a skillchain is open', 'SC_AVAILABLE' },
                                                        { 'no skillchain is open', 'NOT_SC_AVAILABLE' } },
      enemyOnly = true, advanced = true },
    { key = 'LEVEL',   label = 'Level',       ops = { { 'below', 'LVL_LT' }, { 'at least', 'LVL_GTE' } }, unit = '', default = 30,
      advanced = true },
    { key = 'TIMER',   label = 'Timer',       ops = { { 'every', 'TIMER' } }, unit = 's', default = 60, advanced = true },
    { key = 'RANDOM',  label = 'Random',      ops = { { 'chance', 'RANDOM' } }, unit = '%', default = 50, advanced = true },
}

-- (job expansion) how the conditions are offered: common (always in the builder), advanced (with "More conditions"),
-- hidden (never offered: other jobs' conditions or engine internals; a saved rule with one is still shown and kept)
M.CONDITION_CLASS = {}
for _, subj in ipairs(M.SUBJECTS) do
    for _, op in ipairs(subj.ops) do
        M.CONDITION_CLASS[op[2]] = subj.advanced and 'advanced' or 'common'
    end
end
for _, id in ipairs({ 'CASTING_DEBUFF', 'CASTING_ELEMENT_MA', 'CAST_ELE_MA_SELF', 'CASTING_ELE_MA_AOE', 'NEED_ELE_BAREFFECT',
                      'NO_SAMBA', 'NO_STORM', 'NO_MAX_RUNE', 'HAS_RUNES', 'LUNGE_MB_AVAILABLE', 'STATUS_FLAG', 'IS_ECOSYSTEM' }) do
    M.CONDITION_CLASS[id] = 'hidden'
end
M.SUBJECT_OF = {}   -- condition id -> subject, op index
for _, subj in ipairs(M.SUBJECTS) do
    for i, op in ipairs(subj.ops) do
        M.SUBJECT_OF[op[2]] = { subj = subj, op = i }
    end
end

-- (0.3.1) what each subject checks (the engine's conditions in gambits_container.cpp), as a tooltip per dropdown entry
M.SUBJECT_HELP = {
    ALWAYS     = 'No condition: the rule is used whenever it is reached and its action is possible.',
    HP         = 'The target\'s HP in percent of its maximum HP.',
    MP         = 'The target\'s MP in percent. A target without MP (a Warrior) counts as 0 %, so "MP below" matches it; '
        .. 'MP (mages) does not.',
    MPUSER     = 'MP in percent, only for targets that have MP: a target without MP (a Warrior) never matches.',
    HASMP      = 'True when the target has MP at all (maximum MP above 0).',
    TP         = 'The target\'s TP (0-3000).',
    MISSING    = 'How many HP the target is missing: maximum HP minus current HP.',
    AGGRO      = 'Whether the target is the one the enemy is attacking (it has the enemy\'s top enmity).',
    PTTANK     = 'Whether the party has a tank (a member whose main job is NIN, PLD or RUN). The rule\'s target does not matter.',
    STATUS     = 'Whether the target has a status effect (a buff or a debuff), e.g. Protect missing -> Protect.',
    ENEMY      = 'What the enemy is doing now (target Enemy only): casting a spell, or readying a weapon skill, special move '
        .. 'or job ability.',
    COOLDOWN   = 'True while the squad mate cannot use the job ability yet because of its recast, whatever the rule\'s target is.',
    SHADOWS    = 'How many Utsusemi shadows or Blink images the target has left.',
    FAMILY     = 'The kind of monster the squad mate is fighting (Goblin, Orc, Bat ...). It looks at the enemy whatever the rule\'s '
        .. 'target is, so "Self" or "Party" rules can use it: Enemy family is Goblin -> Barfira.',
    PCOUNT     = 'How many party members (you, the party and the mates, within 20 yalms of this mate) match: all of them, the ones '
        .. 'asleep, or the ones with a status. E.g. at least 2 asleep -> Curaga, otherwise -> Cure.',
    ECOUNT     = 'How many monsters fighting the party are within reach of the mate\'s enemy, above an HP %. Monsters only '
        .. 'standing nearby do not count. E.g. at least 3 above 30% -> Stonega, otherwise -> Stone.',
    SKILLCHAIN = 'The enemy\'s skillchain state (target Enemy only): an open skillchain, or a magic burst window now.',
    LEVEL      = 'The target\'s level.',
    TIMER      = 'True the first time, then once every so many seconds.',
    RANDOM     = 'True with this chance (in percent) each time the rule is checked.',
}

-- Status effects offered first in the picker (any other effect can be typed; the server checks the name)
M.COMMON_EFFECTS = { 'PROTECT', 'SHELL', 'REGEN', 'HASTE', 'STONESKIN', 'BLINK', 'AQUAVEIL', 'REFRESH', 'RERAISE',
                     'POISON', 'PARALYSIS', 'BLINDNESS', 'SILENCE', 'PETRIFICATION', 'DISEASE', 'PLAGUE', 'CURSE_I',
                     'SLEEP_I', 'SLOW', 'WEIGHT', 'BIND', 'BIO', 'DIA', 'DOOM' }

-- condition id -> { label, unit } ; unit: '%', 'HP', 's' (seconds), '' (a plain number), 'effect', nil (no value)
M.COND_LABELS = {
    ALWAYS             = { 'Always' },
    HPP_LT             = { 'HP below', '%' },
    HPP_GTE            = { 'HP at least', '%' },
    MPP_LT             = { 'MP below', '%' },
    MPP_GTE            = { 'MP at least', '%' },
    TP_LT              = { 'TP below', '' },
    CASTING_DEBUFF     = { 'Casting a debuff' },
    CASTING_ELEMENT_MA = { 'Casting elemental magic' },
    CAST_ELE_MA_SELF   = { 'Casting elemental magic on itself' },
    CASTING_ELE_MA_AOE = { 'Casting area elemental magic' },
    NEED_ELE_BAREFFECT = { 'Needs an element bar-spell' },
    NO_SAMBA           = { 'No samba active' },
    NO_STORM           = { 'No storm active' },
    NO_MAX_RUNE        = { 'Runes not at maximum' },
    HAS_RUNES          = { 'Has runes' },
    TP_GTE             = { 'TP at least', '' },
    LVL_LT             = { 'Level below', '' },
    LVL_GTE            = { 'Level at least', '' },
    HP_MISSING         = { 'HP missing at least', 'HP' },
    RANDOM             = { 'Random chance', '%' },
    TIMER              = { 'Every', 's' },
    STATUS             = { 'Has effect', 'effect' },
    NOT_STATUS         = { 'Missing effect', 'effect' },
    HAS_TOP_ENMITY     = { 'Has the enemy\'s attention' },
    NOT_HAS_TOP_ENMITY = { 'Does not have the enemy\'s attention' },
    PT_HAS_TANK        = { 'Party has a tank' },
    NOT_PT_HAS_TANK    = { 'Party has no tank' },
    SC_AVAILABLE       = { 'A skillchain is open' },
    NOT_SC_AVAILABLE   = { 'No skillchain is open' },
    MB_AVAILABLE       = { 'A magic burst is possible' },
    LUNGE_MB_AVAILABLE = { 'A Lunge burst is possible' },
    READYING_WS        = { 'Readying a weapon skill' },
    READYING_MS        = { 'Readying a special move' },
    READYING_JA        = { 'Readying a job ability' },
    CASTING_MA         = { 'Casting a spell' },
    HAS_MP             = { 'Uses MP' },
    HAS_MP_MPP_LT      = { 'MP (mages) below', '%' },
    HAS_MP_MPP_GTE     = { 'MP (mages) at least', '%' },
    JA_ON_COOLDOWN     = { 'On cooldown:', 'ja' },
    MOD_LT             = { 'Below:', 'mod' },
    ENEMY_FAMILY       = { 'Enemy is', 'family' },   -- (F1/F2, server version 11)
    PARTY_COUNT        = { 'Party members', 'pcount' },
    ENEMY_COUNT        = { 'Enemies', 'ecount' },
}

local ROMAN = { I = true, II = true, III = true, IV = true, V = true, VI = true }

-- "CURE_II" -> "Cure II", "DIVINE_SEAL" -> "Divine Seal"
function M.pretty(name)
    if name == nil or name == '' then
        return ''
    end

    local words = {}
    for word in tostring(name):gmatch('[^_]+') do
        local upper = word:upper()
        words[#words + 1] = ROMAN[upper] and upper or (upper:sub(1, 1) .. upper:sub(2):lower())
    end

    return table.concat(words, ' ')
end

function M.target_label(id)
    return M.TARGET_LABELS[id or ''] or M.pretty(id)
end

function M.kind_label(id)
    return M.KIND_LABELS[id or ''] or M.pretty(id)
end

function M.cond_label(id)
    local l = M.COND_LABELS[id or '']
    return l and l[1] or M.pretty(id)
end

function M.cond_unit(id, cat)
    local l = M.COND_LABELS[id or '']
    if l then
        return l[2]
    end

    local c = cat and cat.conds and cat.conds[id or '']
    return c and (c.kind == 'e' and 'effect' or c.kind == 'j' and 'ja' or c.kind == 'm' and 'mod' or c.kind == 'r' and ''
        or c.kind == 'y' and 'family' or c.kind == 'p' and 'pcount' or c.kind == 'q' and 'ecount' or nil) or nil
end

-- "UTSUSEMI.2" -> "Utsusemi shadows below 2"
function M.mod_text(arg)
    local name, n = M.mod_parse(arg)
    if name == nil then
        return '? below ?'
    end

    return M.MODS[name][3] .. ' below ' .. tostring(n)
end

-- "HP below 50%", "Missing effect Protect", "Always"
function M.cond_text(id, arg, cat)
    if id == nil then
        return ''
    end

    local unit = M.cond_unit(id, cat)
    local label = M.cond_label(id)
    if id == 'JA_ON_COOLDOWN' then
        return (arg and arg ~= '' and M.pretty(arg) or '?') .. ' is on cooldown' -- "Provoke is on cooldown"
    elseif unit == 'mod' then
        return M.mod_text(arg)
    elseif unit == 'family' or unit == 'pcount' or unit == 'ecount' then
        return M.count_text(id, arg) -- (F1/F2)
    elseif unit == nil then
        return label
    elseif unit == 'effect' and M.tier_song(arg) then
        return label .. ' ' .. M.pretty(M.tier_song(arg)) -- (Bard song tiers) "Missing effect Victory March"
    elseif unit == 'effect' or unit == 'ja' then
        return label .. ' ' .. (arg and arg ~= '' and M.pretty(arg) or '?')
    elseif unit == 's' then
        return label .. ' ' .. tostring(arg or '?') .. ' s'
    elseif unit == 'HP' then
        return label .. ' ' .. tostring(arg or '?') .. ' HP'
    end

    return label .. ' ' .. tostring(arg or '?') .. unit
end

function M.action_text(r)
    if r == nil or r.kind == nil then
        return '(no action)'
    end

    if not M.NAMED_KINDS[r.kind] then
        return M.kind_label(r.kind)
    end

    if r.name == nil or r.name == '' then
        return M.kind_label(r.kind) .. ': ?'
    end

    return r.kind == 'family' and ('Best of ' .. M.pretty(r.name)) or M.pretty(r.name)
end

-- (beta polish) the compact rule line of the rule list: "Enemy: Not top enmity + No tank -> Provoke". The full wording
-- (M.rule_summary) stays in the tooltip and under the selected rule.
M.TARGET_SHORT = { SELF = 'Self', PARTY = 'Party', PARTY_LOWEST_HPP = 'Lowest HP', TANK = 'Tank', CASTER = 'Mage', MELEE = 'Melee',
                   RANGED = 'Ranged', TOP_ENMITY = 'Aggro ally', TARGET = 'Enemy', MASTER = 'You',
                   TRIGGER_SELF_ACTION_TARGET = 'Self->Enemy' }
M.COND_SHORT = {
    ALWAYS = 'Always', HAS_TOP_ENMITY = 'Top enmity', NOT_HAS_TOP_ENMITY = 'Not top enmity', PT_HAS_TANK = 'Tank in party',
    NOT_PT_HAS_TANK = 'No tank', SC_AVAILABLE = 'Skillchain open', NOT_SC_AVAILABLE = 'No skillchain', MB_AVAILABLE = 'Burst window',
    CASTING_MA = 'Casting', CASTING_DEBUFF = 'Casting a debuff', READYING_WS = 'Readying WS', READYING_MS = 'Readying move',
    READYING_JA = 'Readying JA', HAS_MP = 'Uses MP',
}
M.COND_SHORT_VALUE = { -- id -> prefix, suffix
    HPP_LT = { 'HP < ', '%' }, HPP_GTE = { 'HP >= ', '%' }, MPP_LT = { 'MP < ', '%' }, MPP_GTE = { 'MP >= ', '%' },
    HAS_MP_MPP_LT = { 'Mage MP < ', '%' }, HAS_MP_MPP_GTE = { 'Mage MP >= ', '%' }, TP_LT = { 'TP < ', '' }, TP_GTE = { 'TP >= ', '' },
    HP_MISSING = { 'Missing ', ' HP' }, LVL_LT = { 'Lv < ', '' }, LVL_GTE = { 'Lv >= ', '' }, RANDOM = { '', '% chance' },
    TIMER = { 'Every ', ' s' },
}

-- (0.3.3) a role target with filters, as players read it: "Melee, not Tank", "Tank or Mage"; nil without filters
M.ROLE_LABEL = { TANK = 'Tank', MELEE = 'Melee', CASTER = 'Mage', RANGED = 'Ranged' }
function M.roles_text(r)
    if r == nil or (r.rolesIn == nil and r.rolesOut == nil) or not M.ROLE_TARGET[r.target or ''] then
        return nil
    end

    local inc, exc = { M.ROLE_LABEL[r.target] }, {}
    for role in string.gmatch(r.rolesIn or '', '[^%.]+') do inc[#inc + 1] = M.ROLE_LABEL[role] or M.pretty(role) end
    for role in string.gmatch(r.rolesOut or '', '[^%.]+') do exc[#exc + 1] = M.ROLE_LABEL[role] or M.pretty(role) end
    local text = table.concat(inc, ' or ')
    if #exc > 0 then
        text = text .. ', not ' .. table.concat(exc, ' or ')
    end

    return text
end

function M.cond_short(id, arg, cat)
    if id == nil then
        return ''
    elseif M.COND_SHORT[id] then
        return M.COND_SHORT[id]
    elseif M.COND_SHORT_VALUE[id] then
        return M.COND_SHORT_VALUE[id][1] .. tostring(arg or '?') .. M.COND_SHORT_VALUE[id][2]
    elseif id == 'STATUS' then
        return 'Has ' .. (arg and M.pretty(M.tier_song(arg) or arg) or '?')
    elseif id == 'NOT_STATUS' then
        return 'No ' .. (arg and M.pretty(M.tier_song(arg) or arg) or '?')
    elseif id == 'JA_ON_COOLDOWN' then
        return (arg and M.pretty(arg) or '?') .. ' on cooldown'
    elseif id == 'MOD_LT' then
        local name, n = M.mod_parse(arg)
        local short = { UTSUSEMI = 'Shadows', BLINK = 'Images' }
        return (name and short[name] or '?') .. ' < ' .. tostring(n or '?')
    elseif id == 'ENEMY_FAMILY' or id == 'PARTY_COUNT' or id == 'ENEMY_COUNT' then
        return M.count_short(id, arg) -- (F1/F2)
    end

    return M.cond_text(id, arg, cat)
end

function M.rule_short(r, cat)
    if r == nil then
        return ''
    elseif r.opaque then
        return '(kept unchanged, read-only)'
    end

    local when = M.cond_short(r.cond, r.arg, cat)
    if r.cond2 then
        when = when .. ' + ' .. M.cond_short(r.cond2, r.arg2, cat)
    end

    local text = string.format('%s: %s -> %s', M.roles_text(r) or M.TARGET_SHORT[r.target or ''] or M.target_label(r.target), when ~= '' and when or '?',
        M.action_text(r))
    if r.retry and tonumber(r.retry) and tonumber(r.retry) > 0 then
        text = text .. string.format(' (wait %s s)', r.retry)
    end

    if r.level ~= nil then
        text = text .. string.format(' (Lv %s+)', r.level)
    end

    return text
end

-- One line for the rule list: "Party member: HP below 50% -> Best of Cure"
function M.rule_summary(r, cat)
    if r == nil then
        return ''
    end

    if r.opaque then
        return '(uses options this editor cannot show - kept unchanged, read-only)'
    end

    local when = M.cond_text(r.cond, r.arg, cat)
    if r.cond2 then
        when = when .. ' and ' .. M.cond_text(r.cond2, r.arg2, cat)
    end

    local text = string.format('%s: %s -> %s', M.roles_text(r) or M.target_label(r.target), when ~= '' and when or '(no condition)', M.action_text(r))
    if r.retry and r.retry ~= '' and tonumber(r.retry) and tonumber(r.retry) > 0 then
        text = text .. string.format(' (then waits %s s)', r.retry)
    end

    if r.level ~= nil then
        text = text .. string.format(' (from level %s)', r.level)
    end

    return text
end

-- A server reason with ids in it ("MARTYR needs level 75") as players read it ("Martyr needs level 75")
function M.readable(text)
    return (tostring(text or ''):gsub('%f[%w_]([A-Z][A-Z0-9_]+)%f[^%w_]', function(word)
        if #word >= 4 or word:find('_', 1, true) then
            return M.pretty(word)
        end
    end))
end

-- "Protect" / "protect" / "PROTECT" -> "PROTECT" (the id the server checks)
function M.effect_id(text)
    return (tostring(text or ''):upper():gsub('[^A-Z0-9]+', '_'):gsub('^_+', ''):gsub('_+$', ''))
end

-- ---------------------------------------------------------------- rule list operations (local, no server)
function M.new_rule()
    return { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' }
end

-- Each returns the new selected index
function M.add_rule(d, sel)
    if #d.rules >= M.MAX_RULES then
        return sel
    end

    local at = math.min((sel or #d.rules) + 1, #d.rules + 1)
    table.insert(d.rules, at, M.new_rule())
    d.dirty = true
    return at
end

function M.remove_rule(d, sel)
    if sel == nil or d.rules[sel] == nil then
        return sel
    end

    table.remove(d.rules, sel)
    d.dirty = true
    if #d.rules == 0 then
        return nil
    end

    return math.min(sel, #d.rules)
end

-- (0.3.4) the selected rule to the first or the last place; returns its new place
function M.move_rule_end(d, sel, toTop)
    local r = sel and d.rules[sel]
    if r == nil or d.readonly or d.uneditable then
        return sel
    end

    local at = toTop and 1 or #d.rules
    if at ~= sel then
        table.remove(d.rules, sel)
        table.insert(d.rules, at, r)
        d.dirty = true
    end

    return at
end

function M.move_rule(d, sel, delta)
    local to = (sel or 0) + delta
    if sel == nil or d.rules[sel] == nil or d.rules[to] == nil then
        return sel
    end

    d.rules[sel], d.rules[to] = d.rules[to], d.rules[sel]
    d.dirty = true
    return to
end

function M.toggle_rule(d, sel)
    local r = sel and d.rules[sel]
    if r then
        r.on = r.on == false
        d.dirty = true
    end

    return sel
end

-- ---------------------------------------------------------------- theme
-- The colours of FFXIPort 1.2.0 (ffxiport/ui/theme.lua, Copyright (C) 2026 wildthing, GPL-3.0-only; the same author's
-- palettes, reused here, value for value, with its rounding and frame border). GambitsV2 owns its whole window, so the
-- theme applies to all of it (GambitsV2.lua pushes the window colours from M.theme). Classic is the default.
-- (0.3.4) The palettes are in xifo_ui.lua now, value for value, so the Squads menu draws with the same ones (its copy
-- of that file is identical). Crimson is the default of a NEW installation; an existing one keeps what it saved
-- (Gambits.lua sets M.DEFAULT_THEME from the installation's own settings before anything is drawn).
local U
do
    local ok, mod = pcall(require, 'xifo_ui')
    if not (ok and type(mod) == 'table') then
        local here = (debug and debug.getinfo and (debug.getinfo(1, 'S').source or '') or ''):match('^@(.*[/\\])') or ''
        ok, mod = pcall(dofile, here .. 'xifo_ui.lua')
    end

    if not (ok and type(mod) == 'table') then
        error('Gambits: xifo_ui.lua could not be loaded: ' .. tostring(mod))
    end

    U = mod
end
M.UI = U

local times = U.times

M.THEMES = U.THEMES
M.THEME_ORDER = U.THEME_ORDER
M.THEME_NAMES = U.THEME_NAMES
M.DEFAULT_THEME = U.DEFAULT
M.theme, M.themeName = M.THEMES[M.DEFAULT_THEME], M.DEFAULT_THEME
M.times = times

-- selects a theme by name (anything unknown: this installation's default); returns the name used
function M.set_theme(name)
    name = M.THEMES[name or ''] and name or (M.THEMES[M.DEFAULT_THEME or ''] and M.DEFAULT_THEME or U.DEFAULT)
    M.theme, M.themeName = M.THEMES[name], name
    return name
end

-- ---------------------------------------------------------------- UI (ImGui, drawn inside the GambitsV2 window)
local function imgui()
    return api.imgui
end

local function s(px)
    return api.s and api.s(px) or px
end

-- Pushes colours, runs fn, pops exactly what was pushed (also when fn fails), then re-raises the error
local function with_colors(list, fn, ...)
    local g = imgui()
    local pushed = 0
    for _, item in ipairs(list) do
        local id = rawget(_G, item[1])
        if id ~= nil and item[2] ~= nil and g.PushStyleColor then
            g.PushStyleColor(id, item[2])
            pushed = pushed + 1
        end
    end

    local ok, err = pcall(fn, ...)
    if pushed > 0 and g.PopStyleColor then
        g.PopStyleColor(pushed)
    end

    if not ok then
        error(err, 0)
    end
end
M.with_colors = with_colors

-- Runs fn between open() and close(); close() always runs (an error must not leave ImGui's stacks unbalanced)
local function scoped(open, close, fn, ...)
    local ok, err = pcall(fn, ...)
    close()
    if not ok then
        error(err, 0)
    end
end

local function child(id, size, fn)
    local g = imgui()
    local shown = g.BeginChild(id, size, rawget(_G, 'ImGuiChildFlags_Borders') or 1)
    scoped(nil, function() g.EndChild() end, function()
        if shown then
            fn()
        end
    end)
end

local function colored(color, text)
    local g = imgui()
    if g.TextColored then
        g.TextColored(color, text)
    else
        g.Text(text)
    end
end

local function heading(text)
    colored(M.theme.gold, text)
end

local function note(text)
    colored(M.theme.secondary, text)
end

local function button(label, w)
    return imgui().Button(label, { w or 0, 0 })
end

local function same(spacing)
    imgui().SameLine(0, spacing or s(6))
end

local function width(w)
    local g = imgui()
    if g.SetNextItemWidth then
        g.SetNextItemWidth(w)
    end
end

local function available()
    local g = imgui()
    if api.available then
        local w = api.available()
        if type(w) == 'number' and w > 0 then
            return w
        end
    end

    if g.GetContentRegionAvail then
        local a, b = g.GetContentRegionAvail()
        if type(a) == 'table' then
            return tonumber(a[1] or a.x) or s(600)
        elseif type(a) == 'number' then
            return a
        end
    end

    return s(600)
end

-- (0.3.9) the width of a text in the current font, in pixels. Ashita's CalcTextSize hands back two numbers (x, y); a
-- table is read too. Without the call: 7 px a character at this Size.
local function text_w(text)
    local g = imgui()
    if g.CalcTextSize then
        local ok, a = pcall(g.CalcTextSize, tostring(text or ''))
        if ok and type(a) == 'table' then
            return tonumber(a[1] or a.x) or 0
        elseif ok and type(a) == 'number' then
            return a
        end
    end

    return #tostring(text or '') * s(7)
end
M.text_w = text_w

-- (0.3.5) the width for the control that holds a rule's value: at least `min`, and what is left of the row up to `max`
-- (default 340), so a long choice can be read while its list is closed. `keep`: room to leave for what follows it.
local function fill_w(min, keep, max)
    return math.floor(math.max(min, math.min(available() - (keep or s(4)), max or s(340))))
end

-- (0.3.5) the states every XI: Forever Offline window draws the same way (xifo_ui U.states): a selected row has a
-- light tint and a thin line around it, so a row can be selected AND say something else with its text colour
local function row_colors(selected)
    if not selected then
        return {}
    end

    local st = M.UI.states(M.theme)
    return { { 'ImGuiCol_Header', st.rowFill }, { 'ImGuiCol_HeaderHovered', st.rowFill }, { 'ImGuiCol_HeaderActive', st.rowFill } }
end

-- the line around the row that was just drawn (when this ImGui can say where it is)
local function row_outline(selected)
    if selected then
        M.UI.outline_item(imgui(), M.UI.states(M.theme).rowLine)
    end
end

-- controls of the smaller kind (xifo_ui U.SIZE.tabCompact): secondary actions next to a list
local function compact(fn)
    local g = imgui()
    local id = rawget(_G, 'ImGuiStyleVar_FramePadding')
    local pushed = false
    if id ~= nil and g.PushStyleVar and g.PopStyleVar then
        pushed = pcall(g.PushStyleVar, id, { s(M.UI.SIZE.tabPadCompact), s(2) })
    end

    local ok, err = pcall(fn)
    if pushed then
        g.PopStyleVar(1)
    end

    if not ok then
        error(err, 0)
    end
end

-- (hotfix 2026-11-21) Ashita's Lua bindings hand the text of imgui.SetTooltip and imgui.TextWrapped to ImGui as a
-- printf FORMAT (addons.dll passes the Lua string as the only argument of IGuiManager::SetTooltip(fmt, ...) and
-- TextWrapped(fmt, ...)). A '%' in such a text is read as a conversion: "40% and" printed garbage (% a), and the Lowest
-- HP help ("HP % that") is an invalid format, on which the C runtime ends the game (0xC0000409). TextUnformatted never
-- formats, so tooltips and wrapped lines are drawn with it; the text the player sees is unchanged.
local function format_safe(text)
    return (tostring(text or ''):gsub('%%', '%%%%')) -- (only for a binding without TextUnformatted: '%%' shows one '%')
end

-- (0.3.1 polish) the wrap width of tooltips: 27 times the current font size (the font Gambits pushes for its Size
-- setting), or 380 px (scaled) where the binding cannot tell the font size
M.TOOLTIP_WRAP_EM = 27
function M.tooltip_wrap_width()
    local g = imgui()
    if g.GetFontSize then
        local ok, size = pcall(g.GetFontSize)
        if ok and type(size) == 'number' and size > 0 then
            return size * M.TOOLTIP_WRAP_EM
        end
    end

    return s(380)
end

local function tooltip(text)
    local g = imgui()
    if not (g.IsItemHovered and g.IsItemHovered()) then
        return
    end

    if g.BeginTooltip and g.EndTooltip and g.TextUnformatted then
        if g.BeginTooltip() ~= false then -- (true when shown; nil from a binding that returns nothing)
            -- (0.3.1 polish) long texts wrap at about 27 characters' width of the tooltip's own font (~380 px at 100 %;
            -- it follows the window's Size setting), as Ashita's own imgui.ShowHelp does. Still TextUnformatted only.
            local wrap = g.PushTextWrapPos and g.PopTextWrapPos and M.tooltip_wrap_width() or nil
            if wrap then
                g.PushTextWrapPos(wrap)
            end

            scoped(nil, function()
                if wrap then
                    g.PopTextWrapPos()
                end

                g.EndTooltip()
            end, function() g.TextUnformatted(tostring(text or '')) end)
        end
    elseif g.SetTooltip then
        g.SetTooltip(format_safe(text))
    end
end

-- the height left in the current window or panel
local function available_h()
    local g = imgui()
    if g.GetContentRegionAvail then
        local a, b = g.GetContentRegionAvail()
        if type(a) == 'table' then
            return tonumber(a[2] or a.y) or s(400)
        elseif type(b) == 'number' then
            return b
        end
    end

    return s(400)
end
M.available_h = available_h

-- coloured text that wraps at the panel's edge (status lines, warnings: never cut off)
-- (hotfix 2026-11-21) drawn unformatted: see tooltip() above. PushTextWrapPos(0) + TextUnformatted is what TextWrapped
-- does inside ImGui, without reading the text as a format.
local function wrapped(color, text)
    local g = imgui()
    if g.PushTextWrapPos and g.PopTextWrapPos and g.TextUnformatted then
        with_colors({ { 'ImGuiCol_Text', color } }, function()
            g.PushTextWrapPos(0)
            scoped(nil, function() g.PopTextWrapPos() end, function() g.TextUnformatted(tostring(text or '')) end)
        end)
    elseif g.TextWrapped then
        with_colors({ { 'ImGuiCol_Text', color } }, function() g.TextWrapped(format_safe(text)) end)
    else
        colored(color, text)
    end
end

-- continue the line when `w` pixels still fit, else start a new one (narrow windows, large scales; FFXIPort's pattern)
local function same_if_fits(w, indent)
    local g = imgui()
    g.SameLine(0, s(6))
    if g.NewLine and available() < w then
        g.NewLine()
        if indent and g.SetCursorPosX then
            g.SetCursorPosX(indent)
        end
    end
end
M.same_if_fits = same_if_fits

-- a label for a control on the same line, vertically centred on it
local function label_text(text)
    local g = imgui()
    if g.AlignTextToFramePadding then
        g.AlignTextToFramePadding()
    end

    g.Text(text)
end

-- a drop-down of ids shown by their readable names: returns the chosen id (tipOf: an optional tooltip per entry;
-- (0.3.1) colorOf: an optional text colour per entry, e.g. dimmed for a spell learned later)
-- (0.3.5) previewOf: what the closed list shows for the current value, when that is shorter than its entry
local function combo(id, current, values, labelOf, tipOf, colorOf, previewOf)
    local g = imgui()
    local function label(v)
        if v == nil then
            return '(none)'
        end

        return labelOf and labelOf(v) or tostring(v)
    end

    if not g.BeginCombo then
        -- older ImGui bindings: a button that steps through the choices
        if g.Button(label(current) .. id, { 0, 0 }) and #values > 0 then
            local at = 0
            for i, v in ipairs(values) do
                if v == current then
                    at = i
                end
            end

            current = values[at % #values + 1]
        end

        return current
    end

    if g.BeginCombo(id, previewOf and previewOf(current) or label(current)) then
        for i, v in ipairs(values) do
            local color = colorOf and colorOf(v)
            local picked = false
            with_colors(color and { { 'ImGuiCol_Text', color } } or {}, function()
                picked = g.Selectable(label(v) .. '##' .. tostring(i), v == current)
            end)
            if picked then
                current = v
            end

            local tip = tipOf and tipOf(v)
            if tip then
                tooltip(tip)
            end
        end

        g.EndCombo()
    end

    return current
end

local function text_field(id, value, size)
    local buf = { value or '' }
    imgui().InputText(id, buf, size or 32)
    return buf[1]
end

-- a whole number field that keeps exactly what the player typed: nothing is clamped or replaced; the value changes
-- only when the player changes it (a value out of range is shown in red and blocks Save, M.check_draft)
local function int_input(id, value)
    local g = imgui()
    if g.InputInt then
        local buf = { tonumber(value) or 0 }
        if g.InputInt(id, buf) then
            local n = tonumber(buf[1])
            if n ~= nil then
                return string.format('%d', math.floor(n))
            end
        end

        return value
    end

    local typed = text_field(id, value or '', 8)
    if typed ~= (value or '') and string.match(typed, '^%-?%d*$') then
        return typed
    end

    return value
end

-- (0.3.9) the width a whole-number field needs to show `digits` digits WITH its - / + buttons, at this Size and font:
-- the digits, the frame's padding on both sides, and the two square step buttons (each a frame high) with their gaps.
-- (0.3.8 gave the Enemies condition's fields a fixed 60 px: at 120 % the buttons took all of it and the value was gone.)
function M.int_field_w(digits)
    local g = imgui()
    local frameH = nil
    if g.GetFrameHeight then
        local ok, h = pcall(g.GetFrameHeight)
        frameH = ok and type(h) == 'number' and h or nil
    end

    frameH = frameH or s(19)
    return math.floor(text_w(string.rep('0', math.max(1, digits or 2))) + s(8) + 2 * (frameH + s(4)) + s(6) + 0.5)
end

-- (0.3.9) a whole-number field with the words around it ("above HP %" [ 30 - + ], "within" [ 10 - + ] "yalms") as ONE
-- group: it moves to the next line together, at `indent`, when it does not fit the rest of this one, so a label is never
-- parted from its field or its unit, and the field is always wide enough for its value. Returns what int_input returns.
local function num_group(id, before, value, digits, after, indent, tip)
    local fieldW = M.int_field_w(digits)
    local total = (before and (text_w(before) + s(4)) or 0) + fieldW + (after and (s(4) + text_w(after)) or 0)
    same_if_fits(total, indent)
    if before then
        label_text(before)
        same(s(4))
    end

    width(fieldW)
    local v = int_input(id, value)
    if tip then
        tooltip(tip)
    end

    if after then
        same(s(4))
        label_text(after)
    end

    return v
end
M.num_group_width = function(before, digits, after)
    return (before and (text_w(before) + s(4)) or 0) + M.int_field_w(digits) + (after and (s(4) + text_w(after)) or 0)
end

-- ---------------------------------------------------------------- edits without ImGui (the window calls these; tests too)
local function cond_keys(slot)
    if slot == 2 then
        return 'cond2', 'arg2'
    end

    return 'cond', 'arg'
end

-- Sets condition slot 1 or 2 (cond nil clears slot 2). Changing only the comparison (HP below -> HP at least) keeps the
-- value exactly; another subject starts from its default value (a status effect is left to choose).
function M.set_condition(r, slot, cond, cat)
    local ck, ak = cond_keys(slot)
    if cond == nil then
        if slot == 2 then
            r.cond2, r.arg2 = nil, nil
        end

        return
    end

    local old = r[ck]
    if old == cond then
        return
    end

    r[ck] = cond
    local so, sn = old and M.SUBJECT_OF[old], M.SUBJECT_OF[cond]
    if so and sn and so.subj == sn.subj then
        return
    end

    local spec = cat and cat.conds and cat.conds[cond]
    if spec and spec.kind == 'r' then
        local v = sn and sn.subj.default or spec.lo
        r[ak] = string.format('%d', math.max(spec.lo, math.min(spec.hi, v)))
    elseif spec and spec.kind == 'm' then
        r[ak] = (sn and sn.subj.default) or 'UTSUSEMI.2' -- (job expansion) MOD_LT: "MODIFIER.number"
    elseif spec and (spec.kind == 'y' or spec.kind == 'p' or spec.kind == 'q') then
        -- (F1/F2) "GOBLIN", "AT_LEAST.2.ASLEEP", "AT_LEAST.3.0.10"
        r[ak] = (sn and sn.subj.default) or ({ y = 'GOBLIN', p = 'AT_LEAST.2', q = 'AT_LEAST.3.0.10' })[spec.kind]
    else
        r[ak] = nil
    end
end

-- Sets the action kind (and name); another kind clears the name, a kind without a name has none
function M.set_action(r, kind, name)
    if kind ~= r.kind then
        r.kind, r.name = kind, nil
    end

    if M.NAMED_KINDS[kind] then
        r.name = name or r.name
    else
        r.name = nil
    end
end

-- the subjects the builder offers for a slot: only those whose engine conditions the server's catalog reports
-- (job expansion) advanced = true also offers the advanced subjects (skillchain, level, timer, random)
function M.subjects_for(slot, target, cat, advanced)
    local out = {}
    for _, subj in ipairs(M.SUBJECTS) do
        local reported = true
        for _, op in ipairs(subj.ops) do
            reported = reported and cat and cat.conds and cat.conds[op[2]] ~= nil
        end

        if reported and not (subj.key == 'ALWAYS' and slot == 2) and not (subj.enemyOnly and target ~= 'TARGET')
            and (advanced or not subj.advanced) then
            out[#out + 1] = subj
        end
    end

    return out
end

-- (0.3.1) the value of Has effect / Missing effect: ONE dropdown - the effects the mate's jobs give, the common ones,
-- and "Custom..." last. Only Custom shows a text field. The rule keeps exactly the effect id it had (r.arg / r.arg2);
-- the field has its own text (spaces and half-typed names stay as typed) and writes the id only when it is a name the
-- server knows, or - for any other name - when the player presses Enter or leaves the field. An empty or unreadable
-- text never changes the saved value. A saved name outside the lists opens in Custom, unchanged.
function M.effect_selector(r, slot, cat, labelW)
    local g = imgui()
    local _, ak = cond_keys(slot)
    local mate = M.mate()
    M.ensure_plan(mate)
    local jobList, common = M.effect_choices(cat, mate)
    local values, jobOf, commonSet = {}, {}, {}
    for _, e in ipairs(jobList) do
        values[#values + 1] = e.name
        jobOf[e.name] = e
    end

    for _, n in ipairs(common) do
        values[#values + 1] = n
        commonSet[n] = true
    end

    values[#values + 1] = M.CUSTOM_EFFECT
    S.effCustom = S.effCustom or {}
    local st = S.effCustom[slot]
    -- (Bard song tiers) "MARCH.2": the dropdown shows the effect MARCH, the song picker after it the tier
    local full = r[ak]
    local cur, curTier = M.tier_parse(full)
    if st == nil or st.rule ~= r then
        st = { rule = r, custom = false, value = full }
        S.effCustom[slot] = st
    end

    if st.value ~= full then
        st.value, st.text, st.pending, st.custom = full, nil, nil, false -- (changed elsewhere: another subject, a reload)
    end

    if cur ~= nil and jobOf[cur] == nil and not commonSet[cur] then
        st.custom = true -- (a saved name outside the lists: shown in Custom, kept exactly)
    end

    local jobName = mate and mate.job or 'job'
    same_if_fits(s(200), labelW)
    width(fill_w(s(200)))
    local shown = st.custom and M.CUSTOM_EFFECT or cur
    local picked = combo('##gsq-eff' .. slot, shown, values, function(v)
        if v == M.CUSTOM_EFFECT then
            return (st.custom and cur) and ('Custom: ' .. M.pretty(cur)) or 'Custom...'
        elseif jobOf[v] then
            return M.pretty(v) .. '  (' .. jobName .. ')'
        end

        return M.pretty(v)
    end, function(v) return M.effect_tip(v, jobOf[v], mate) end)
    tooltip(st.custom and M.effect_tip(M.CUSTOM_EFFECT) or M.effect_tip(cur, jobOf[cur or ''], mate) or 'Choose a status effect.')
    if picked ~= shown then
        if picked == M.CUSTOM_EFFECT then
            st.custom, st.text, st.pending = true, cur and M.pretty(cur) or '', nil
        else
            r[ak], st.custom, st.text, st.pending, st.value = picked, false, nil, nil, picked
            cur, curTier = picked, nil
        end
    end

    M.song_tier_picker(r, ak, st, cur, curTier, slot, labelW)
    if not st.custom then
        return
    end

    same_if_fits(s(170), labelW)
    width(s(170))
    if st.text == nil then
        st.text = cur and M.pretty(cur) or ''
    end

    local typed = text_field('##gsq-efftype' .. slot, st.text, 40)
    local committed = false
    if typed ~= st.text then
        st.text = typed
        local id = M.effect_id(typed)
        st.pending = nil
        if string.match(id, '^[A-Z][A-Z0-9_]*$') then
            if M.effect_known(id) == true or not g.IsItemDeactivatedAfterEdit then
                -- (a known name at once; a binding that cannot tell when editing ends: at once too, as before)
                r[ak], st.value, committed = id, id, true
                cur = id
            elseif id ~= cur then
                st.pending = id
            end
        end
    end

    if not committed and st.pending and g.IsItemDeactivatedAfterEdit and g.IsItemDeactivatedAfterEdit() then
        r[ak], st.value, cur, st.pending = st.pending, st.pending, st.pending, nil
    end

    tooltip(M.effect_tip(M.CUSTOM_EFFECT))
    local id = M.effect_id(st.text)
    if st.pending then
        same()
        colored(M.theme.gold, '(Enter to use)')
        tooltip(string.format('%s is not a status effect name the editor knows. Press Enter (or leave the field) to use it anyway; '
            .. 'the rule keeps %s until then.', M.pretty(st.pending), cur and M.pretty(cur) or 'no effect'))
    elseif cur and M.effect_known(cur) == false then
        same()
        colored(M.theme.bad, '(unknown effect)')
        tooltip(string.format('The server has no status effect called %s. The rule keeps it exactly as saved, but the server '
            .. 'refuses to save a Rule Set with it: choose or type another one.', cur))
    elseif cur and (id == '' or not string.match(id, '^[A-Z][A-Z0-9_]*$')) then
        same()
        note('(keeps ' .. M.pretty(cur) .. ')')
        tooltip('The field is empty or not a name: the rule keeps ' .. M.pretty(cur) .. '.')
    end
end

-- (0.3.3) false for a song no squad mate can ever have on this server (gambits_data.lua q = 'x': Trust / Summoning /
-- Geomancy groups, no scroll, or not in the spell list at all - Honor March); without the data: offered, as before
function M.song_offered(name)
    local row = M.DATA and M.DATA.spells and M.DATA.spells[name]
    return not (row and row.q == 'x')
end

-- (0.3.3) the song picker's entries for a song type: 0 (Any) and the tiers of the songs this server has (a song the data
-- marks as never a squad mate's spell, e.g. Honor March, is left out); a saved tier stays listed, unchanged
function M.tier_choices(base, tier)
    local values = { 0 }
    for i, name in ipairs(M.SONG_TIERS[base or ''] or {}) do
        if M.song_offered(name) or i == tier then
            values[#values + 1] = i
        end
    end

    return values
end

-- (Bard song tiers) after a song type (March, Minuet ...): "Any March" (as before) or one song of it. Only with a
-- server that carries tiers (version 8); a saved tier on an older server stays as it is and is flagged.
function M.song_tier_picker(r, ak, st, base, tier, slot, labelW)
    local songs = M.SONG_TIERS[base or '']
    if songs == nil then
        return
    end

    if not (S.server and (S.server.version or 0) >= M.TIER_SERVER) then
        if tier then
            same()
            colored(M.theme.bad, '(' .. M.tier_problem(r[ak]) .. ')')
        end

        return
    end

    local values = M.tier_choices(base, tier)
    same_if_fits(s(190), labelW)
    width(s(190))
    local shown = (tier and songs[tier]) and tier or 0
    local picked = combo('##gsq-tier' .. slot, shown, values, function(v)
        return v == 0 and ('Any ' .. M.pretty(base)) or M.pretty(songs[v])
    end, function(v)
        if v == 0 then
            return 'Any song of this type counts, whoever sang it (as before).'
        end

        return M.pretty(songs[v]) .. ' only. Other ' .. M.pretty(base) .. ' songs do not count, so two rules can keep two '
            .. M.pretty(base) .. ' songs up (e.g. Victory March and Advancing March).'
    end)
    tooltip('Which song counts: Any, or one song of this type.')
    if picked ~= shown then
        local value = picked == 0 and base or string.format('%s.%d', base, picked)
        r[ak], st.value = value, value
    end

    local why = M.tier_problem(r[ak])
    if why then
        same()
        colored(M.theme.bad, '(' .. why .. ')')
    end
end

-- one condition slot: subject, comparison, value
local function condition_editor(r, slot, cat, labelW)
    local g = imgui()
    local ck, ak = cond_keys(slot)
    local cond = r[ck]
    local info = cond and M.SUBJECT_OF[cond]
    local subjects = M.subjects_for(slot, r.target, cat, S.moreConds == true)
    local keys, byKey = {}, {}
    if slot == 2 then
        keys[1] = 'NONE'
    end

    for _, subj in ipairs(subjects) do
        keys[#keys + 1] = subj.key
        byKey[subj.key] = subj
    end

    local current = cond == nil and 'NONE' or (info and info.subj.key) or 'OTHER'
    if info and byKey[current] == nil then
        byKey[current] = info.subj -- (an Enemy condition with another target: shown, flagged by the check)
    end

    width(s(170)) -- (0.3.5: was 130; "Target's status effect" and the like are read whole)
    local picked = combo('##gsq-subj' .. slot, current, keys, function(v)
        if v == 'NONE' then
            return '(nothing else)'
        elseif v == 'OTHER' then
            return M.cond_label(cond)
        end

        return byKey[v] and byKey[v].label or v
    end, function(v)
        if v == 'NONE' then
            return 'No second condition: the first one alone decides.'
        end

        return M.SUBJECT_HELP[v or '']
    end)
    tooltip(M.SUBJECT_HELP[current or ''] or 'What the rule checks.')
    if picked ~= current then
        if picked == 'NONE' then
            M.set_condition(r, 2, nil, cat)
        elseif byKey[picked] then
            M.set_condition(r, slot, byKey[picked].ops[1][2], cat)
        end

        cond = r[ck]
        info = cond and M.SUBJECT_OF[cond]
    end

    if cond == nil then
        return
    end

    if info and #info.subj.ops > 1 then
        same_if_fits(s(190), labelW)
        width(s(190))
        local idx = {}
        for i = 1, #info.subj.ops do
            idx[i] = i
        end

        local op = combo('##gsq-op' .. slot, info.op, idx, function(i) return info.subj.ops[i][1] end)
        if op ~= info.op then
            M.set_condition(r, slot, info.subj.ops[op][2], cat)
            cond = r[ck]
        end
    end

    local spec = cat.conds[cond]
    if spec and spec.kind == 'r' then
        -- (0.3.9) the field as wide as its largest value needs, with its unit, as one group
        local unit = M.cond_unit(cond, cat)
        r[ak] = num_group('##gsq-val' .. slot, nil, r[ak], #tostring(spec.hi), (unit and unit ~= '' and unit ~= 'effect') and unit or nil, labelW,
            string.format('A whole number, %d to %d. Kept exactly as you type it.', spec.lo, spec.hi))

        local n = tonumber(r[ak] or '')
        if n == nil or n < spec.lo or n > spec.hi or n ~= math.floor(n) then
            same()
            colored(M.theme.bad, string.format('(%d-%d)', spec.lo, spec.hi))
        end
    elseif spec and spec.kind == 'e' then
        M.effect_selector(r, slot, cat, labelW)
    elseif spec and spec.kind == 'j' then
        -- (server version 5) JA_ON_COOLDOWN: one of the mate's own job abilities
        same_if_fits(s(220), labelW)
        width(fill_w(s(220)))
        -- (0.3.1) the same job-aware list as the Job Ability action (and its Show all); a saved name stays, marked
        local mate = M.mate()
        M.ensure_plan(mate)
        local names, info = {}, {}
        for _, e in ipairs(M.ja_view(cat, mate, S.showAll == true)) do
            names[#names + 1] = e.name
            info[e.name] = e
        end

        if r[ak] and info[r[ak]] == nil then
            local e = M.ja_saved_entry(r[ak], cat, mate)
            names[#names + 1] = e.name
            info[e.name] = e
        end

        local dim = M.state_colors()
        local chosen = combo('##gsq-ja' .. slot, r[ak], names, function(v)
            return v and (info[v] and info[v].label or M.pretty(v)) or '(choose)'
        end, function(v) return M.entry_tip('ja', info[v or ''], mate) end,
        function(v) local it = info[v or '']; return it and dim[it.state] or nil end)
        if chosen ~= r[ak] then
            r[ak] = chosen
        end

        tooltip('True while the squad mate\'s own recast of this job ability is running (e.g. Flash while Provoke is not ready).')
    elseif spec and spec.kind == 'm' then
        -- (job expansion, server version 6) MOD_LT: which count, and the number it must be below ("UTSUSEMI.2")
        local name, n = M.mod_parse(r[ak])
        same_if_fits(s(170), labelW)
        width(s(170))
        local chosen = combo('##gsq-mod' .. slot, name, M.MOD_ORDER, function(v) return v and M.MODS[v][3] or '(choose)' end,
            function(v) return M.MODS[v or ''] and string.format('%s left on the target (%d-%d).', M.MODS[v][3], M.MODS[v][1], M.MODS[v][2]) end)
        local typed = num_group('##gsq-modn' .. slot, nil, tostring(n or 2), 2, nil, labelW,
            'True while the target has fewer than this many left (Utsusemi shadows or Blink images). '
            .. 'E.g. Utsusemi shadows below 2: cast Utsusemi again before the last shadow is gone.')
        r[ak] = string.format('%s.%s', chosen or 'UTSUSEMI', typed ~= nil and typed ~= '' and typed or '2')
        local why = M.mod_problem(r[ak])
        if why then
            same()
            colored(M.theme.bad, '(' .. why .. ')')
        end
    elseif spec and spec.kind == 'y' then
        -- (F1, server version 11) ENEMY_FAMILY: one monster family; a saved name outside the list stays
        local names = {}
        for _, n in ipairs(M.FAMILY_ORDER) do names[#names + 1] = n end
        local inList = false
        for _, n in ipairs(names) do inList = inList or n == r[ak] end
        if r[ak] and not inList then names[#names + 1] = r[ak] end
        local famW = math.max(s(150), text_w('Adamantoise') + s(34))   -- (0.3.9) the longest name in the list, and the arrow
        same_if_fits(famW, labelW)
        width(famW)
        r[ak] = combo('##gsq-fam' .. slot, r[ak], names, function(v) return v and M.pretty(v) or '(choose)' end) or r[ak]
        tooltip('The enemy the squad mate fights is this kind of monster. Works with any target: Self, Party, Enemy ...')
    elseif spec and (spec.kind == 'p' or spec.kind == 'q') then
        -- (F2, server version 11) PARTY_COUNT / ENEMY_COUNT: comparison, number, and the filter
        local cmp, n, a, b
        if spec.kind == 'p' then
            cmp, n, a = M.pcount_parse(r[ak])
        else
            cmp, n, a, b = M.ecount_parse(r[ak])
        end

        -- (0.3.9) each part a group that wraps whole, to the value column: the comparison with its count, then (Party
        -- members) the filter, or (Enemies) "above HP %" with its field and "within" with its field and "yalms". Every field
        -- is as wide as its largest value needs (count 2 digits, HP 2, reach 2) with its - / + buttons.
        local cmpW = math.max(s(96), text_w('fewer than') + s(34))
        same_if_fits(cmpW + s(6) + M.int_field_w(2), labelW)
        width(cmpW)
        cmp = combo('##gsq-cmp' .. slot, cmp or 'AT_LEAST', M.COUNT_CMPS, function(v) return M.COUNT_CMP_LABEL[v or ''] or '?' end) or 'AT_LEAST'
        same(s(6))
        width(M.int_field_w(2))
        local typed = tonumber(int_input('##gsq-cnt' .. slot, tostring(n or 2))) or n or 2
        tooltip(spec.kind == 'p' and string.format('How many members (0-%d).', M.PARTY_COUNT_MAX) or string.format('How many monsters (0-%d).', M.ENEMY_COUNT_MAX))
        if spec.kind == 'p' then
            local statusW = math.max(s(130), text_w('with Petrification') + s(34))
            same_if_fits(statusW, labelW)
            width(statusW)
            local status = combo('##gsq-pst' .. slot, a or '', M.PCOUNT_STATUS, function(v)
                return (v == nil or v == '') and 'any member' or (v == 'ASLEEP' and 'asleep' or ('with ' .. M.pretty(v)))
            end)
            r[ak] = string.format('%s.%d%s', cmp, typed, (status and status ~= '') and ('.' .. status) or '')
            tooltip('Counted: living party members within 20 yalms of this mate, the mate included. "asleep" = Sleep, Sleep II or Lullaby.')
        else
            local hp = tonumber(num_group('##gsq-ehp' .. slot, 'above HP %', tostring(a or 0), 2, nil, labelW,
                'Only monsters above this HP % count (0: any HP).')) or a or 0
            local radius = tonumber(num_group('##gsq-erad' .. slot, 'within', tostring(b or 10), 2, 'yalms', labelW,
                'Counted: monsters fighting the party (their target is one of you, or they have enmity on one of you) within '
                .. 'this many yalms of the mate\'s enemy, the enemy included (1-30). Monsters only standing nearby are not counted.')) or b or 10
            r[ak] = string.format('%s.%d.%d.%d', cmp, typed, hp, radius)
        end

        local why = M.count_problem(spec.kind, r[ak])
        if why then
            same()
            colored(M.theme.bad, '(' .. why .. ')')
        end
    end

    if M.ENEMY_CONDS[cond] and r.target ~= 'TARGET' then
        same_if_fits(s(180), labelW)
        colored(M.theme.bad, '(needs the target Enemy)')
    end
end

-- A readable tooltip for a spell or job ability choice: its level, and whether it comes from the sub job
local function choice_tip(e, mate)
    if e == nil then
        return nil
    end

    local who = mate and mate.name or 'The mate'
    if e.sub then
        return string.format('%s: from the sub job%s, level %d.', M.pretty(e.name), mate and mate.sub and (' (' .. mate.sub .. ')') or '',
            e.level or 0)
    end

    return string.format('%s: %s level %d.%s', M.pretty(e.name), mate and mate.job or 'main job', e.level or 0,
        e.confirmed == false and (' Not confirmed for ' .. who .. ' (not learned yet, or blue magic).') or '')
end
M.choice_tip = choice_tip

-- The Specific Spell choices for a mate, one alphabetical list without duplicates, names only (levels in the tooltip).
-- Version 4 server (catm): exactly the spells the server says the mate has (its main and sub job at their levels, the
-- same rules a call uses), Trust spells left out once more. Older server (cat): the job's spells without Trust spells,
-- main-job ones up to the mate's level; the sub job's level is not known then, so its spells are kept up to the main
-- level and the server decides. Returns { { name, level, sub, label } ... }.
function M.spell_choices(cat, mate)
    local out, seen = {}, {}
    local exact = cat and cat.perMate == true
    local maxLevel = (not exact) and mate and tonumber(mate.level) or nil
    for _, sp in ipairs(cat and cat.spells or {}) do
        local name = sp.name
        if name and not (M.TRUSTS and M.TRUSTS[name]) and (maxLevel == nil or (sp.level or 0) <= maxLevel) then
            local prev = seen[name]
            if prev == nil or (prev.sub and not sp.sub) then
                local entry = { name = name, level = sp.level or 0, sub = sp.sub == true, label = M.pretty(name) }
                if prev then
                    for i, e in ipairs(out) do
                        if e == prev then
                            out[i] = entry
                        end
                    end
                else
                    out[#out + 1] = entry
                end

                seen[name] = entry
            end
        end
    end

    table.sort(out, function(a, b)
        if a.label ~= b.label then
            return a.label < b.label
        end

        return a.name < b.name
    end)
    return out
end

-- The Job Ability choices: version 4 (catm) = exactly the abilities the server's U13 rules allow the mate; older
-- servers = the job's list as it comes. Names only, one alphabetical list.
function M.ja_choices(cat, mate)
    local out, seen = {}, {}
    for _, ja in ipairs(cat and cat.jas or {}) do
        if ja.name and not seen[ja.name] then
            seen[ja.name] = true
            out[#out + 1] = { name = ja.name, level = ja.level or 0, sub = ja.sub == true, label = M.pretty(ja.name) }
        end
    end

    table.sort(out, function(a, b) return a.label < b.label end)
    return out
end

local function in_list(list, name)
    for _, e in ipairs(list) do
        if e.name == name then
            return e
        end
    end

    return nil
end

-- ---------------------------------------------------------------- (0.3.1) job-aware choices: presentation only
-- What the Action and Status pickers offer. Nothing here changes a rule, what is sent, or what the server accepts: the
-- server checks every name on Save and the game decides what a mate casts. A saved name a list leaves out stays
-- selected and unchanged, with a note. Each entry has a state:
--   now          the mate has it now (the server's per-mate catalog, catm)
--   unconfirmed  its jobs and levels allow it, the server cannot confirm it (a scroll not learned, blue magic)
--   later        its main job learns it by level 75, or its sub job by the sub job's cap: prepared now, works then
--   beyond       only its sub job learns it, above what the sub job reaches (shown with Show all)
--   other        no spell of the mate's jobs (families; shown with Show all, marked "(not RDM)")
--   unknown      the job data is not here (an old server, or the list is loading or failed): shown as before
M.PLAN_LEVEL = 75
M.CUSTOM_EFFECT = '__custom__'

-- (performance) the lists below are kept until what they are made from changes: see cached_view further down
local VIEW_CACHE = {}

function M.clear_view_cache()
    VIEW_CACHE = {}
end

-- gambits_data.lua: spells[NAME] = { FAMILY or false, e = effect, q = 'x'/'b' }, effects[NAME] = id, jaEffects[NAME]
function M.set_data(d)
    M.clear_view_cache()
    M.DATA = type(d) == 'table' and type(d.spells) == 'table' and type(d.effects) == 'table' and d or nil
    M.FAMILY_SPELLS = {}
    for name, row in pairs(M.DATA and M.DATA.spells or {}) do
        local fam = type(row) == 'table' and row[1] or nil
        if fam then
            M.FAMILY_SPELLS[fam] = M.FAMILY_SPELLS[fam] or {}
            table.insert(M.FAMILY_SPELLS[fam], name)
        end
    end

    for _, list in pairs(M.FAMILY_SPELLS) do
        table.sort(list)
    end
end

-- The sub job level a mate's sub job reaches at main level 75: half (37), unless the mate's current levels show this
-- server gives more (map.SUBJOB_RATIO: two thirds = 50, the main level = 75). No sub job: 0.
function M.sub_cap(m)
    if m == nil or m.sub == nil then
        return 0
    end

    local main, sl = tonumber(m.level) or 0, tonumber(m.subLevel)
    if sl and main > 1 then
        if sl >= main then
            return M.PLAN_LEVEL
        elseif sl > math.floor(main / 2) then
            return math.floor(M.PLAN_LEVEL * 2 / 3)
        end
    end

    return math.floor(M.PLAN_LEVEL / 2)
end

function M.plan_key(m)
    return m and ((m.job or '?') .. '/' .. (m.sub or '-')) or nil
end

-- The planning list for a mate's jobs: the server's own job catalog (cat <job> <sub>: that job's spells and abilities
-- up to level 75, by the server's content settings). With an older server the editor's catalog already is that list.
function M.plan_for(cat, m)
    if cat and cat.perMate == false then
        return cat
    end

    local p = S.plan
    if m and p and p.key == M.plan_key(m) then
        return p.cat
    end

    return nil
end

-- 'ready', 'loading', 'failed' or nil (not asked yet / not possible)
function M.plan_state(cat, m)
    if M.plan_for(cat, m) then
        return 'ready'
    end

    local p = S.plan
    if m and p and p.key == M.plan_key(m) then
        return p.loading and 'loading' or (p.error and 'failed') or nil
    end

    return nil
end

-- asks the server for the planning list once per job / sub job (only when nothing else is waiting)
function M.ensure_plan(m)
    if m == nil or not (S.server and (S.server.version or 0) >= 4) or M.busy() then
        return
    end

    local key = M.plan_key(m)
    if S.plan and S.plan.key == key then
        return
    end

    S.plan = { key = key, loading = true }
    read_request({ 'cat', m.job, m.sub }, function(items, endFields)
        local cat, why = M.parse_catalog(items, endFields)
        if S.plan and S.plan.key == key then
            S.plan = cat and { key = key, cat = cat } or { key = key, error = why }
        end

        return true -- (a planning list that cannot be read only means: nothing is filtered)
    end, function(why)
        if S.plan and S.plan.key == key then
            S.plan = { key = key, error = why }
        end
    end, 'cat')
end

-- false for a spell never in a squad mate's spell list (gambits_data q = 'x': Trust, Summoning, Geomancy, a monster's
-- version), and for blue magic unless the mate is a Blue Mage (the same rules as gambits_squad.lua G.mateSpells)
local function squad_spell(name, mate)
    local row = M.DATA and M.DATA.spells[name]
    if row == nil then
        return true
    elseif row.q == 'x' then
        return false
    elseif row.q == 'b' then
        return mate ~= nil and (mate.job == 'BLU' or mate.sub == 'BLU')
    end

    return true
end

-- (job abilities also: merit = its job and level allow it, the owner's merit is needed; mainonly = from the sub job, a
-- two-hour or main-job-only ability, never usable there)
local STATE_RANK = { now = 1, unconfirmed = 2, unknown = 2, later = 3, merit = 3, beyond = 4, mainonly = 4, other = 5, missing = 5 }

function M.view_label(e, mate)
    local name = M.pretty(e.name)
    if e.state == 'unconfirmed' then
        return name .. '  (not confirmed)'
    elseif e.state == 'later' then
        return string.format('%s  (%sLv %d)', name, e.sub and 'sub ' or '', e.level or 0)
    elseif e.state == 'merit' then
        return string.format('%s  (%sLv %d, merit)', name, e.sub and 'sub ' or '', e.level or 0)
    elseif e.state == 'mainonly' then
        return string.format('%s  (sub, %s)', name, e.twoHour and 'two-hour: main job only' or 'main job only')
    elseif e.state == 'beyond' and not e.sub then
        return string.format('%s  (Lv %d, above %d)', name, e.level or 0, M.PLAN_LEVEL)
    elseif e.state == 'beyond' then
        return string.format('%s  (sub Lv %d, above the sub job cap)', name, e.level or 0)
    elseif e.state == 'other' then
        return string.format('%s  (%snot %s)', name, e.job and (e.job .. ', ') or '', mate and mate.job or 'this job')
    elseif e.state == 'missing' then
        return name .. '  (not on this server)'
    end

    return name
end

local function view_sort(list)
    table.sort(list, function(a, b)
        local ra, rb = STATE_RANK[a.state] or 9, STATE_RANK[b.state] or 9
        if ra ~= rb then
            return ra < rb
        end

        if ra >= 3 and (a.level or 0) ~= (b.level or 0) then
            return (a.level or 0) < (b.level or 0)
        end

        if a.order and b.order then
            return a.order < b.order
        end

        return a.label < b.label
    end)
    return list
end

-- The Specific Spell choices with planning: what the mate has now, then what its jobs learn later (to level 75; the
-- sub job to its cap), marked by level. showAll adds the sub job's spells above its cap. Returns entries
-- { name, label, level, sub, state }.
function M.spell_view(cat, mate, showAll, plan)
    plan = plan or M.plan_for(cat, mate)
    local out, seen = {}, {}
    local exact = cat and cat.perMate == true
    for _, e in ipairs(M.spell_choices(cat, mate)) do
        seen[e.name] = true
        out[#out + 1] = { name = e.name, level = e.level, sub = e.sub, state = 'now' }
    end

    for _, u in ipairs(exact and cat.unconfirmed or {}) do
        if u.name and not seen[u.name] and not (M.TRUSTS and M.TRUSTS[u.name]) then
            seen[u.name] = true
            out[#out + 1] = { name = u.name, level = u.level, sub = u.sub, state = 'unconfirmed' }
        end
    end

    local cap = M.sub_cap(mate)
    for _, sp in ipairs(plan and plan.spells or {}) do
        local n = sp.name
        if n and not seen[n] and not (M.TRUSTS and M.TRUSTS[n]) and squad_spell(n, mate) and not (sp.sub and mate and mate.sub == nil) then
            seen[n] = true
            out[#out + 1] = { name = n, level = sp.level or 0, sub = sp.sub == true,
                              state = (sp.sub and (sp.level or 0) > cap) and 'beyond' or 'later' }
        end
    end

    local shown = {}
    for _, e in ipairs(out) do
        if showAll or e.state ~= 'beyond' then
            e.label = M.view_label(e, mate)
            shown[#shown + 1] = e
        end
    end

    return view_sort(shown)
end

-- The Best of Family choices: the server's family list (complete with showAll), each with the state of its best spell
-- for this mate. Without the job data (or while it loads) the list is the server's, unmarked (state 'unknown').
-- Entries { name, label, state, level, sub, members = { spell entries }, order }.
function M.family_view(cat, mate, showAll, plan)
    plan = plan or M.plan_for(cat, mate)
    local filter = M.DATA ~= nil and plan ~= nil
    local byName = {}
    if filter then
        for _, e in ipairs(M.spell_view(cat, mate, true, plan)) do
            byName[e.name] = e
        end
    end

    local out = {}
    for i, fam in ipairs(cat and cat.families or {}) do
        local e = { name = fam, order = i, members = {}, state = 'unknown' }
        if filter then
            local best
            for _, sp in ipairs(M.FAMILY_SPELLS[fam] or {}) do
                local s = byName[sp]
                if s then
                    e.members[#e.members + 1] = s
                    if best == nil or STATE_RANK[s.state] < STATE_RANK[best.state]
                        or (STATE_RANK[s.state] == STATE_RANK[best.state] and (s.level or 0) < (best.level or 0)) then
                        best = s
                    end
                end
            end

            table.sort(e.members, function(a, b)
                if (a.level or 0) ~= (b.level or 0) then
                    return (a.level or 0) < (b.level or 0)
                end

                return a.name < b.name
            end)
            e.state = best and best.state or 'other'
            e.level, e.sub = best and best.level, best and best.sub
        end

        if showAll or (e.state ~= 'beyond' and e.state ~= 'other') then
            e.label = M.view_label(e, mate)
            out[#out + 1] = e
        end
    end

    return view_sort(out)
end

-- (0.3.1) one job ability's job, level and sub job / merit restrictions: gambits_data jas (made from the server's
-- squad_ja_jobs_data.lua, the table the U13 rules use). {} when the data is not here (then only level 0 = two-hour is
-- known, as the server's own rule says).
function M.ja_info(name)
    local row = M.DATA and type(M.DATA.jas) == 'table' and M.DATA.jas[name or ''] or nil
    if type(row) ~= 'table' then
        return {}
    end

    return { job = row[1], level = row[2], twoHour = row.sp == true or row[2] == 0, mainOnly = row.main == true,
             merit = row.merit == true }
end

-- The Job Ability choices with planning, by the same rules as the spells: what the mate may use now (the server's
-- per-mate catalog, catm: the U13 rules), then what its jobs learn later (the server's job catalog, cat <job> <sub>), the
-- sub job to its cap. Merit abilities the owner has not unlocked are marked "merit". showAll adds the sub job's two-hour
-- and main-job-only abilities, the sub job's abilities above its cap and abilities above level 75. Runtime limits
-- (recast, status, pets, ...) are never part of this list: the server checks them in combat.
-- Older servers (no per-mate catalog): the job catalog with the mate's main level, the sub job up to the main level (its
-- own level is not known then; the server decides). No mate, or no catalog: the server's list as it is (state 'now').
-- Returns entries { name, label, level, sub, state, twoHour, merit, job }.
function M.ja_view(cat, mate, showAll, plan)
    plan = plan or M.plan_for(cat, mate)
    local out, seen = {}, {}
    local exact = cat and cat.perMate == true
    if exact or mate == nil or plan == nil then
        for _, e in ipairs(M.ja_choices(cat, mate)) do
            seen[e.name] = true
            local info = M.ja_info(e.name)
            out[#out + 1] = { name = e.name, level = e.level, sub = e.sub, state = 'now', merit = info.merit, job = info.job }
        end
    end

    local cap, level = M.sub_cap(mate), mate and tonumber(mate.level) or 0
    for _, ja in ipairs((mate and plan and plan.jas) or {}) do
        local n = ja.name
        if n and not seen[n] and not (ja.sub and mate.sub == nil) then
            seen[n] = true
            local info = M.ja_info(n)
            local lv = ja.level or 0
            local twoHour = info.twoHour == true or lv == 0
            local state
            if ja.sub then
                if twoHour or info.mainOnly then
                    state = 'mainonly'
                elseif lv > cap then
                    state = 'beyond'
                elseif info.merit then
                    state = 'merit'
                elseif lv <= (exact and (tonumber(mate.subLevel) or 0) or level) then
                    state = exact and 'unconfirmed' or 'now'
                else
                    state = 'later'
                end
            elseif lv > M.PLAN_LEVEL then
                state = 'beyond'
            elseif info.merit then
                state = 'merit'
            elseif lv <= level then
                state = exact and 'unconfirmed' or 'now'
            else
                state = 'later'
            end

            out[#out + 1] = { name = n, level = lv, sub = ja.sub == true, state = state, twoHour = twoHour, merit = info.merit,
                              job = info.job }
        end
    end

    local shown = {}
    for _, e in ipairs(out) do
        if showAll or (e.state ~= 'beyond' and e.state ~= 'mainonly') then
            e.label = M.view_label(e, mate)
            shown[#shown + 1] = e
        end
    end

    return view_sort(shown)
end

-- A saved job ability the view leaves out, so it stays selected and marked: its own entry from the complete view (a
-- hidden sub job / above-cap one), else "other" (not an ability of the mate's jobs, with its job when the data has it).
function M.ja_saved_entry(name, cat, mate, plan)
    if name == nil then
        return nil
    end

    plan = plan or M.plan_for(cat, mate)
    for _, e in ipairs(M.ja_view(cat, mate, true, plan)) do
        if e.name == name then
            return e
        end
    end

    local info = M.ja_info(name)
    local e = { name = name, level = info.level, state = 'other', job = info.job, merit = info.merit }
    if mate == nil or plan == nil then
        e.state = 'unknown' -- (nothing can be said without the job list)
    elseif info.job and (info.job == mate.job or info.job == mate.sub) then
        e.state = 'missing' -- (one of its jobs, but not in the server's list: its expansion switched off, or not loaded)
    end

    e.label = (e.state == 'other' or e.state == 'missing') and M.view_label(e, mate) or M.pretty(name)
    return e
end

-- the tooltip of a job ability entry: its job and level, and why it is (not yet) usable - job, level and merit only;
-- recast and status are decided in combat (plain text: drawn with tooltip(), never as a format)
function M.ja_tip(e, mate)
    if e == nil then
        return nil
    end

    local who = mate and mate.name or 'The mate'
    local job = mate and mate.job or 'its job'
    local sub = mate and mate.sub or 'sub job'
    local name = M.pretty(e.name)
    local lines = {}
    if e.state == 'other' then
        lines[1] = e.job and string.format('%s: a %s job ability (level %d), not one of %s\'s jobs (%s%s).', name, e.job,
            e.level or 0, who, job, mate and mate.sub and ('/' .. sub) or '')
            or string.format('%s: not a job ability of %s\'s jobs on this server.', name, who)
        lines[2] = 'A rule with it never fires for ' .. who .. '. It is kept as saved.'
        return table.concat(lines, '\n')
    elseif e.state == 'missing' then
        return string.format('%s: a %s job ability, but not in this server\'s ability list (its expansion switched off?). A '
            .. 'rule with it does not fire now. It is kept as saved.', name, e.job or job)
    elseif e.state == 'unknown' then
        return M.choice_tip(e, mate)
    end

    lines[1] = name .. (e.sub and string.format(': from the sub job (%s), level %d.', sub, e.level or 0)
        or string.format(': %s level %d.', job, e.level or 0))
    if e.state == 'now' then
        lines[2] = string.format('%s can use it by job and level now.', who)
    elseif e.state == 'unconfirmed' then
        lines[2] = string.format('%s\'s job and level allow it, but the server does not offer it now (its ability rules). The '
            .. 'server decides when %s is called.', who, who)
    elseif e.state == 'later' then
        lines[2] = string.format('Learned later (%s level %d). You can prepare it now: the rule starts working then.',
            e.sub and ('sub job ' .. sub) or job, e.level or 0)
    elseif e.state == 'merit' then
        lines[2] = 'A merit ability: it works only once the squad\'s owner (you) has unlocked its merit'
            .. ((e.level or 0) > (mate and tonumber(e.sub and mate.subLevel or mate.level) or 0)
                and string.format(', and from %slevel %d.', e.sub and 'sub job ' or '', e.level or 0) or '.')
    elseif e.state == 'mainonly' then
        lines[2] = string.format('%s only works as the main job, never from the sub job (%s): a rule with it never fires for %s.',
            e.twoHour and 'A two-hour ability' or 'It', sub, who)
    elseif e.state == 'beyond' and e.sub then
        lines[2] = string.format('Above what a sub job reaches (%s up to level %d), so it may never be usable.', sub, M.sub_cap(mate))
    elseif e.state == 'beyond' then
        lines[2] = string.format('Learned above level %d, so it may never be usable.', M.PLAN_LEVEL)
    end

    if e.merit and e.state == 'now' then
        lines[#lines + 1] = 'A merit ability (its merit is unlocked).'
    end

    lines[#lines + 1] = 'Recast, status and other conditions are checked in combat, not in this list.'
    return table.concat(lines, '\n')
end

-- the state of one saved name in the views (nil: not in the server's list at all)
local function view_entry(list, name)
    for _, e in ipairs(list) do
        if e.name == name then
            return e
        end
    end

    return nil
end

-- true / false: whether the server's status effect table has this name; nil: the data is not here (nothing is checked)
function M.effect_known(name)
    if not (M.DATA and M.DATA.effects) or name == nil then
        return nil
    end

    return M.DATA.effects[name] ~= nil
end

-- The status effects for "Has effect / Missing effect": the effects the mate's jobs give (the server's ability
-- scripts and spell data: gambits_data jaEffects / spells.e) for its abilities and spells now and later, then the
-- common ones. Returns job entries { name, sources = { { from, kind, level, sub, state } } } and common names.
function M.effect_choices(cat, mate, plan)
    plan = plan or M.plan_for(cat, mate)
    local job, byName = {}, {}
    local function add(effect, from, kind, level, sub, state)
        if effect == nil or M.effect_known(effect) ~= true then
            return
        end

        local e = byName[effect]
        if e == nil then
            e = { name = effect, sources = {} }
            byName[effect] = e
            job[#job + 1] = e
        end

        e.sources[#e.sources + 1] = { from = from, kind = kind, level = level or 0, sub = sub == true, state = state }
    end

    if M.DATA then
        local cap, seenJa = M.sub_cap(mate), {}
        for _, pass in ipairs({ { cat and cat.jas or {}, 'now' }, { plan and plan.jas or {}, 'later' } }) do
            for _, ja in ipairs(pass[1]) do
                if ja.name and not seenJa[ja.name] and not (ja.sub and (mate == nil or mate.sub == nil or (ja.level or 0) > cap)) then
                    seenJa[ja.name] = true
                    for _, eff in ipairs(M.DATA.jaEffects and M.DATA.jaEffects[ja.name] or {}) do
                        add(eff, ja.name, 'ja', ja.level, ja.sub, pass[2])
                    end
                end
            end
        end

        -- (0.3.3) the server's spell data gives songs no effect: a song the mate sings gives its song type (M.SONG_TIERS),
        -- so a Bard finds March, Minuet ... in this list (and then chooses one song of it)
        local songType = {}
        for effect, songs in pairs(M.SONG_TIERS) do
            for _, name in ipairs(songs) do
                songType[name] = effect
            end
        end

        for _, sp in ipairs(M.spell_view(cat, mate, false, plan)) do
            local row = M.DATA.spells[sp.name]
            if row and row.e then
                add(row.e, sp.name, 'spell', sp.level, sp.sub, sp.state)
            elseif songType[sp.name] then
                add(songType[sp.name], sp.name, 'spell', sp.level, sp.sub, sp.state)
            end
        end
    end

    table.sort(job, function(a, b) return M.pretty(a.name) < M.pretty(b.name) end)
    local common = {}
    for _, name in ipairs(M.COMMON_EFFECTS) do
        if byName[name] == nil then
            common[#common + 1] = name
        end
    end

    return job, common
end

-- (performance) The editor draws every frame, and the lists above were made again each time: for a rule with a spell
-- and two status conditions that was about 2 ms and 700 KB of garbage per frame. They are now made once and kept until
-- something they are made from changes. A list is the same as long as these are the same:
--   the catalog and the planning list (new tables whenever the server sends them again; their lengths are compared too,
--   in case one is changed in place), the mate's job, sub job and both levels, Show all, the addon data (M.DATA), the
--   Trust spell list (M.TRUSTS) and M.PLAN_LEVEL.
-- One result is kept per list and Show all setting, so another mate, Rule Set job or catalog simply replaces it. The
-- lists are shared between frames: callers read them and never change them. Nothing a rule holds is cached here.
local function list_len(t)
    return type(t) == 'table' and #t or -1
end

local VIEW_FIELDS = 15

local function view_key(k, cat, mate, plan)
    k[1], k[2], k[3], k[4], k[5] = cat or false, plan or false, M.DATA or false, M.TRUSTS or false, M.PLAN_LEVEL or false
    k[6], k[7] = mate and mate.job or false, mate and mate.sub or false
    k[8], k[9] = mate and mate.level or false, mate and mate.subLevel or false
    k[10], k[11], k[12] = list_len(cat and cat.spells), list_len(cat and cat.jas), list_len(cat and cat.families)
    k[13], k[14], k[15] = list_len(cat and cat.unconfirmed), list_len(plan and plan.spells), list_len(plan and plan.jas)
    return k
end

local VIEW_PROBE = {}

-- build(cat, mate, showAll, plan) -> up to two results; kind: a name of its own for each list
local function cached_view(kind, build)
    local slotAll, slotFit = kind .. '+', kind .. '-'
    return function(cat, mate, showAll, plan)
        plan = plan or M.plan_for(cat, mate)
        showAll = showAll and true or false
        local slot = showAll and slotAll or slotFit
        local probe = view_key(VIEW_PROBE, cat, mate, plan)
        local c = VIEW_CACHE[slot]
        if c then
            local same = true
            for i = 1, VIEW_FIELDS do
                if c.key[i] ~= probe[i] then
                    same = false
                    break
                end
            end

            if same then
                return c.a, c.b
            end
        end

        local a, b = build(cat, mate, showAll, plan)
        VIEW_CACHE[slot] = { key = view_key({}, cat, mate, plan), a = a, b = b }
        return a, b
    end
end

M.spell_choices = (function(build)
    local view = cached_view('spell_choices', function(cat, mate) return build(cat, mate) end)
    return function(cat, mate) return view(cat, mate) end
end)(M.spell_choices)
M.ja_choices = (function(build)
    local view = cached_view('ja_choices', function(cat, mate) return build(cat, mate) end)
    return function(cat, mate) return view(cat, mate) end
end)(M.ja_choices)
M.spell_view = cached_view('spell_view', M.spell_view)
M.family_view = cached_view('family_view', M.family_view)
M.ja_view = cached_view('ja_view', M.ja_view)
M.effect_choices = (function(build)
    local view = cached_view('effect_choices', function(cat, mate, _, plan) return build(cat, mate, plan) end)
    return function(cat, mate, plan) return view(cat, mate, false, plan) end
end)(M.effect_choices)

-- tooltips for the entries above (plain text: drawn with tooltip(), never as a format)
function M.entry_tip(kind, e, mate)
    if e == nil then
        return nil
    end

    local who = mate and mate.name or 'The mate'
    local job = mate and mate.job or 'its job'
    local sub = mate and mate.sub or 'sub job'
    if kind == 'ja' then
        return e.state and M.ja_tip(e, mate) or M.choice_tip(e, mate)
    end

    local lines = {}
    if kind == 'family' then
        lines[1] = string.format('Best of %s: the strongest spell of this family %s knows, with enough MP and not on recast.',
            M.pretty(e.name), who)
        if #(e.members or {}) > 0 then
            local parts = {}
            for i, m in ipairs(e.members) do
                if i > 10 then
                    parts[#parts + 1] = '...'
                    break
                end

                parts[#parts + 1] = string.format('%s %s%d', M.pretty(m.name), m.sub and ('(' .. sub .. ') ') or '', m.level or 0)
            end

            lines[#lines + 1] = job .. (mate and mate.sub and ('/' .. sub) or '') .. ': ' .. table.concat(parts, ', ')
        end
    else
        lines[1] = M.pretty(e.name) .. (e.sub and string.format(': from the sub job (%s), level %d.', sub, e.level or 0)
            or string.format(': %s level %d.', job, e.level or 0))
    end

    if e.state == 'now' then
        lines[#lines + 1] = kind == 'family' and ('Usable now.') or nil
    elseif e.state == 'unconfirmed' then
        lines[#lines + 1] = string.format('%s\'s jobs and levels allow it, but it is not confirmed (not learned yet, or blue magic set when called).', who)
    elseif e.state == 'later' then
        lines[#lines + 1] = string.format('Learned later (%s level %d). You can prepare it now: the rule starts working then.',
            e.sub and ('sub job ' .. sub) or job, e.level or 0)
    elseif e.state == 'beyond' then
        lines[#lines + 1] = string.format('Only the sub job (%s) learns it, at sub level %d: above what a sub job reaches, so it may never be usable.',
            sub, e.level or 0)
    elseif e.state == 'other' then
        lines[#lines + 1] = string.format('No %s spell in this family (main or sub job): this rule would never fire for %s.', job, who)
    end

    return table.concat(lines, '\n')
end

function M.effect_tip(name, jobEntry, mate)
    if name == M.CUSTOM_EFFECT then
        return 'Type any status effect name (spaces are fine). A name the server knows is used at once; another one when you '
            .. 'press Enter or leave the field, and it is marked if the server has no such effect.'
    elseif name == nil then
        return nil
    end

    if jobEntry then
        local parts = {}
        for i, src in ipairs(jobEntry.sources) do
            if i > 3 then
                break
            end

            parts[#parts + 1] = string.format('%s %s (%s%s%d)', src.kind == 'ja' and 'ability' or 'spell', M.pretty(src.from),
                src.sub and ((mate and mate.sub or 'sub') .. ' ') or ((mate and mate.job or '') .. ' '), src.state == 'later' and 'from level ' or 'level ', src.level or 0)
        end

        return M.pretty(name) .. ': given by ' .. table.concat(parts, ', ') .. '.'
    end

    return M.pretty(name) .. ': a common status effect.'
end

-- Why a saved spell or job ability is not among the mate's choices now (nil when it is): it is kept as it is, never
-- changed; the server decides when the mate is called. (0.3.1) Also for spell families, and with the planning list a
-- spell or family learned later says when it starts working.
function M.action_note(r, cat, mate, plan)
    if r.kind == 'family' and r.name then
        return M.family_note(r, cat, mate, plan)
    end

    if r.name == nil or (r.kind ~= 'spell' and r.kind ~= 'ja') then
        return nil
    end

    local who = mate and mate.name or 'the mate'
    if r.kind == 'ja' then
        local note = M.ja_note(r, cat, mate, plan)
        if note ~= false then
            return note
        end
    end

    local list = r.kind == 'spell' and M.spell_choices(cat, mate) or M.ja_choices(cat, mate)
    local e = in_list(list, r.name)
    if e then
        if e.sub and not (cat and cat.perMate) then
            return string.format('%s uses this with its sub job: the server checks the sub job\'s level.', who:gsub('^%l', string.upper))
        end

        return nil
    end

    if r.kind == 'spell' and M.TRUSTS and M.TRUSTS[r.name] then
        return M.pretty(r.name) .. ' is a Trust spell, not a squad action. It is kept as saved; the server decides.'
    end

    plan = plan or M.plan_for(cat, mate)
    local planned = r.kind == 'spell' and plan and view_entry(M.spell_view(cat, mate, true, plan), r.name)
    if planned and planned.state == 'later' then
        return string.format('%s learns %s at %slevel %d: this rule starts working then. It is kept as saved.', who,
            M.pretty(r.name), planned.sub and 'sub job ' or '', planned.level or 0)
    elseif planned and planned.state == 'beyond' then
        return string.format('Only %s\'s sub job learns %s, at sub level %d, above what a sub job reaches: this rule may never '
            .. 'fire. It is kept as saved.', who, M.pretty(r.name), planned.level or 0)
    end

    for _, u in ipairs(cat and cat.unconfirmed or {}) do
        if r.kind == 'spell' and u.name == r.name then
            return string.format('%s\'s jobs and levels allow %s, but it is not confirmed (not learned yet, or blue magic). '
                .. 'It is kept as saved; the server decides when %s is called.', who, M.pretty(r.name), who)
        end
    end

    return string.format('%s is not in %s\'s %s now (job, level%s). It is kept as saved; the server decides when %s is called.',
        M.pretty(r.name), who, r.kind == 'spell' and 'spell list' or 'job abilities',
        r.kind == 'ja' and ', main job only or merit' or '', who)
end

-- (0.3.1) a saved job ability this mate cannot use (yet), by the job-aware view: when it starts working, or why it never
-- does. nil when it is usable now; false when the view knows nothing about it (no mate or job list: the note of before).
function M.ja_note(r, cat, mate, plan)
    plan = plan or M.plan_for(cat, mate)
    if mate == nil or plan == nil then
        return false
    end

    local e = M.ja_saved_entry(r.name, cat, mate, plan)
    local who, name = mate.name or 'the mate', M.pretty(r.name)
    if e == nil or e.state == 'unknown' then
        return false
    elseif e.state == 'now' then
        if e.sub and not (cat and cat.perMate) then
            return string.format('%s uses this with its sub job: the server checks the sub job\'s level.', (who:gsub('^%l', string.upper)))
        end

        return nil
    elseif e.state == 'later' then
        return string.format('%s learns %s at %slevel %d: this rule starts working then. It is kept as saved.', who, name,
            e.sub and 'sub job ' or '', e.level or 0)
    elseif e.state == 'merit' then
        return string.format('%s is a merit ability: it works once the squad\'s owner has unlocked its merit%s. It is kept as saved.',
            name, (e.level or 0) > (tonumber(e.sub and mate.subLevel or mate.level) or 0)
                and string.format(' and %s reaches %slevel %d', who, e.sub and 'sub job ' or '', e.level or 0) or '')
    elseif e.state == 'mainonly' then
        return string.format('%s %s only as the main job, never from %s\'s sub job: this rule never fires. It is kept as saved.',
            name, e.twoHour and 'is a two-hour ability and works' or 'works', who)
    elseif e.state == 'beyond' and e.sub then
        return string.format('Only %s\'s sub job learns %s, at sub level %d, above what a sub job reaches: this rule may never '
            .. 'fire. It is kept as saved.', who, name, e.level or 0)
    elseif e.state == 'beyond' then
        return string.format('%s learns %s at level %d, above level %d: this rule may never fire. It is kept as saved.', who,
            name, e.level or 0, M.PLAN_LEVEL)
    elseif e.state == 'unconfirmed' then
        return string.format('%s\'s job and level allow %s, but the server does not offer it now. It is kept as saved; the '
            .. 'server decides when %s is called.', who, name, who)
    end

    if e.state == 'missing' then
        return string.format('%s is not in this server\'s ability list for %s now (its expansion switched off?). It is kept as '
            .. 'saved; the server decides when %s is called.', name, e.job or mate.job or 'its job', who)
    elseif e.job then
        return string.format('%s is a %s job ability, not one of %s\'s jobs: this rule never fires for %s. It is kept as saved.',
            name, e.job, who, who)
    end

    return string.format('%s is not a job ability of %s\'s jobs on this server: this rule never fires for %s. It is kept as '
        .. 'saved; the server decides when %s is called.', name, who, who, who)
end

-- (0.3.1) a saved spell family this mate cannot use (yet): when it starts working, or that it never does. nil when it
-- is usable now, or when the job data is not here (nothing is guessed then).
function M.family_note(r, cat, mate, plan)
    local who = mate and mate.name or 'the mate'
    local listed = false
    for _, f in ipairs(cat and cat.families or {}) do
        listed = listed or f == r.name
    end

    if cat and cat.families and #cat.families > 0 and not listed then
        return string.format('Best of %s is not in the server\'s family list now (content switched off?). It is kept as saved; '
            .. 'the server decides when %s is called.', M.pretty(r.name), who)
    end

    plan = plan or M.plan_for(cat, mate)
    if M.DATA == nil or plan == nil then
        return nil
    end

    local e = view_entry(M.family_view(cat, mate, true, plan), r.name)
    if e == nil or e.state == 'now' or e.state == 'unknown' then
        return nil
    elseif e.state == 'unconfirmed' then
        return string.format('%s\'s jobs allow %s spells, but none is confirmed yet (not learned, or blue magic). It is kept as saved.',
            who, M.pretty(r.name))
    elseif e.state == 'later' then
        return string.format('%s learns the first %s spell at %slevel %d: this rule starts working then. It is kept as saved.',
            who, M.pretty(r.name), e.sub and 'sub job ' or '', e.level or 0)
    elseif e.state == 'beyond' then
        return string.format('Only %s\'s sub job has %s spells, from sub level %d, above what a sub job reaches: this rule may '
            .. 'never fire. It is kept as saved.', who, M.pretty(r.name), e.level or 0)
    end

    return string.format('Not a%s %s family: no %s spell for %s or its sub job, so this rule never fires for %s. It is kept as saved.',
        -- ("an RDM", "a WHM": job names are said as letters)
        (mate and mate.job and mate.job:match('^[AEFHILMNORSX]')) and 'n' or '', mate and mate.job or 'job', M.pretty(r.name),
        mate and mate.job or 'its job', who)
end

-- (kept for the earlier callers and tests)
function M.spell_note(r, cat, mate)
    if r.kind ~= 'spell' then
        return nil
    end

    return M.action_note(r, cat, mate)
end

-- the action's name: spell family, specific spell or job ability, from the server's catalog (names only; details in
-- the tooltip)
local function name_picker(r, cat)
    if not M.NAMED_KINDS[r.kind] then
        return
    end

    local g = imgui()
    local mate = M.mate()
    same_if_fits(s(260), s(100))
    width(fill_w(s(260), s(110))) -- (0.3.5: as wide as the row allows, with room for Show all)
    -- (0.3.1) families and spells by the mate's jobs: usable now first, then what it learns later (to level 75, marked
    -- with its level); Show all adds the rest of the server's list. Presentation only: the server checks on Save.
    -- (0.3.1) job abilities the same way: now, later (marked with the level), merit; Show all adds the sub job's two-hour /
    -- main-job-only ones and those above the caps
    M.ensure_plan(mate)
    local entries
    if r.kind == 'ja' then
        entries = M.ja_view(cat, mate, S.showAll == true)
    else
        entries = r.kind == 'family' and M.family_view(cat, mate, S.showAll == true) or M.spell_view(cat, mate, S.showAll == true)
    end

    local names, info = {}, {}
    for _, e in ipairs(entries) do
        names[#names + 1] = e.name
        info[e.name] = e
    end

    local listed = #names
    if r.kind == 'ja' and r.name and info[r.name] == nil then
        -- (a saved ability the list leaves out: shown at the end, marked, still selected)
        local e = M.ja_saved_entry(r.name, cat, mate)
        names[#names + 1] = e.name
        info[e.name] = e
    end

    local dim = M.state_colors()
    -- (a saved name that is not in the list stays selected and unchanged until the player picks another one)
    r.name = combo('##gsq-name', r.name, names, function(v)
        local it = info[v or '']
        return it and it.label or (v and M.pretty(v) or '(choose)')
    end, function(v) return M.entry_tip(r.kind, info[v or ''], mate) end,
    function(v) local it = info[v or '']; return it and dim[it.state] or nil end)
    tooltip(M.entry_tip(r.kind, info[r.name or ''], mate) or (r.name and M.pretty(r.name)) or 'Choose one.')
    same_if_fits(s(100), s(100))
    local all = { S.showAll == true }
    if g.Checkbox('Show all##gsq-showall', all) then
        S.showAll = all[1] == true
        if api.set_pref then
            api.set_pref('show_all', S.showAll)
        end
    end

    local state = M.plan_state(cat, mate)
    tooltip('Off: what ' .. (mate and mate.name or 'the mate') .. '\'s jobs can use, now or later (up to level 75; the sub job up to '
        .. 'its level cap). On: the whole list the server offers, with what does not fit marked. Only the list changes: '
        .. 'saved rules stay exactly as they are, and the server checks every rule when you save.'
        .. (r.kind == 'ja' and ('\nJob abilities: On adds the sub job\'s two-hour and main-job-only abilities and those above '
            .. 'the level caps, marked. Recast and status are checked in combat, not here.') or '')
        .. (state == 'failed' and '\nThe job levels could not be loaded: the list is not filtered.' or ''))
    if state == 'loading' or (state == nil and S.server and (S.server.version or 0) >= 4) then
        same()
        note('(loading job levels...)')
    elseif listed == 0 and not S.showAll then
        same()
        note('(none for ' .. (mate and mate.job or 'this job') .. ')')
        tooltip('No ' .. (r.kind == 'family' and 'spell family' or r.kind == 'ja' and 'job ability' or 'spell') .. ' of '
            .. (mate and mate.job or 'this job') .. (mate and mate.sub and ('/' .. mate.sub) or '') .. ' up to level 75. Show all '
            .. 'lists the rest.')
    end
end

-- the list colours by state: dimmed for later / not confirmed / merit, muted for what may never work
function M.state_colors()
    return { later = M.theme.secondary, unconfirmed = M.theme.secondary, merit = M.theme.secondary, beyond = M.theme.muted,
             mainonly = M.theme.muted, other = M.theme.muted, missing = M.theme.muted }
end
-- The selected rule: Target -> Conditions -> Action (edits go straight into the draft; nothing is sent)
local function rule_editor(d, r, cat, readonly)
    local g = imgui()
    local labelW = s(100)
    local function label(text)
        -- the label, vertically centred on its control, then the control at a fixed x position (one aligned column)
        label_text(text)
        g.SameLine(labelW)
    end

    local why = M.protected(r, cat)
    if why then
        wrapped(M.theme.bad, 'This rule cannot be changed here: ' .. why .. '. It is kept exactly as it is.')
        wrapped(M.theme.secondary, 'You can still switch it on or off and move it.')
        return
    end

    local disabled = readonly and g.BeginDisabled ~= nil
    if disabled then
        g.BeginDisabled(true)
    end

    local before = M.encode_rule(r)
    scoped(nil, function() if disabled then g.EndDisabled() end end, function()

    label('Target')
    width(s(210))
    local targets = {}
    for _, t in ipairs(cat.targets) do
        targets[#targets + 1] = t
    end

    local oldTarget = r.target
    r.target = combo('##gsq-target', r.target, targets, M.target_label, function(v) return M.TARGET_HELP[v or ''] end)
    tooltip(M.TARGET_HELP[r.target or ''] or 'Who the rule is about.')
    if r.target ~= oldTarget then
        M.fit_roles(r)
    end

    -- (0.3.3) a role target: for each other role ONE choice - ignored, Include (also counts) or Exclude (never counts);
    -- the target's own role always counts. A role saved as both (hand-made data) shows as Exclude, the way the engine
    -- reads it, and is saved as Exclude (M.normalize_roles).
    if M.ROLE_TARGET[r.target or ''] and S.server and (S.server.version or 0) >= M.ROLE_SERVER then
        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        colored(M.theme.secondary, 'Roles')
        tooltip('For each other role: ignore it, Include it (its members also count) or Exclude it (its members never count, '
            .. 'even with an included role). E.g. Melee, Tank: Exclude = melee members, but not a Paladin on Auto (Tank and Melee).')
        local states = { 'none', 'in', 'out' }
        local stateLabel = { none = '-', ['in'] = 'Include', out = 'Exclude' }
        for _, role in ipairs(M.ROLE_ORDER) do
            same_if_fits(s(118), labelW)
            if role == r.target then
                colored(M.theme.ok, M.ROLE_LABEL[role] .. ': target')
                tooltip('The target itself: ' .. M.ROLE_LABEL[role] .. ' always counts and cannot be excluded.')
            else
                width(s(118))
                local cur = M.role_state(r, role)
                local picked = combo('##gsq-role-' .. role, cur, states, function(v) return M.ROLE_LABEL[role] .. ': ' .. stateLabel[v] end,
                    function(v)
                        return v == 'in' and ('Also ' .. M.ROLE_LABEL[role] .. ' members.') or v == 'out' and ('Never '
                            .. M.ROLE_LABEL[role] .. ' members.') or (M.ROLE_LABEL[role] .. ' does not matter.')
                    end)
                if picked ~= cur then
                    M.set_role_state(r, role, picked)
                end
            end
        end

        if M.roles_conflict(r) then
            wrapped(M.theme.gold, 'A role was saved as both Include and Exclude: it counts as Exclude, and is saved that way.')
        end

        local why = M.role_problem(M.normalized_copy(r))
        if why then
            wrapped(M.theme.bad, why)
        elseif M.roles_text(r) then
            wrapped(M.theme.secondary, 'Counts: ' .. M.roles_text(M.normalized_copy(r)) .. '.')
        end
    elseif r.rolesIn or r.rolesOut then
        wrapped(M.theme.bad, M.role_problem(r) or 'This rule has role filters this server cannot use.')
    end
    label('Condition')
    condition_editor(r, 1, cat, labelW)
    label('And')
    condition_editor(r, 2, cat, labelW)
    if g.SetCursorPosX then
        g.SetCursorPosX(labelW)
    end

    -- (job expansion) the advanced conditions (skillchain, level, timer, random) only when asked for
    local more = { S.moreConds == true }
    if g.Checkbox('More conditions##gsq-more', more) then
        S.moreConds = more[1]
    end

    tooltip('Also offer the advanced conditions: skillchain and magic burst windows (target Enemy), level, timer and random.')

    label('Action')
    width(s(160))
    local kinds = {}
    for _, k in ipairs(M.NEW_KINDS) do
        kinds[#kinds + 1] = k
    end

    local kind = combo('##gsq-kind', r.kind, kinds, M.kind_label, function(v) return M.KIND_HELP[v or ''] end)
    if kind ~= r.kind then
        M.set_action(r, kind)
    end

    tooltip(M.KIND_HELP[r.kind or ''] or 'What the squad mate does.')

    name_picker(r, cat)
    local spellNote = M.action_note(r, cat, M.mate())
    if spellNote then
        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        wrapped(M.theme.gold, spellNote)
    end

    label('Then wait')
    local hasRetry = { r.retry ~= nil and r.retry ~= '' }
    if g.Checkbox('##gsq-retry-on', hasRetry) then
        r.retry = hasRetry[1] and '30' or nil
    end

    tooltip('After the action, this rule is skipped for this many seconds.')
    if r.retry ~= nil and r.retry ~= '' then
        same()
        width(s(110))
        r.retry = int_input('##gsq-retry', r.retry)
        same(s(3))
        g.Text('seconds before repeating')
    else
        same()
        note('no wait')
    end

    if r.level ~= nil then
        label('From level')
        note(tostring(r.level) .. ' (kept from the saved rule)')
    end
    end)

    if readonly then
        -- (without BeginDisabled the controls still move; nothing may change)
        local back = M.decode_rule(before)
        for k in pairs(r) do
            r[k] = nil
        end

        for k, v in pairs(back) do
            r[k] = v
        end
    elseif M.encode_rule(r) ~= before then
        d.dirty, S.checks = true, {}
    end
end
-- The rule list: order, on/off, a readable line per rule, the selected one highlighted
local function rule_list(d, cat, readonly, height)
    local g = imgui()
    child('##gsq-rules', { 0, height }, function()
        if #d.rules == 0 then
            note('No rules yet. Press Add rule.')
        end

        for i, r in ipairs(d.rules) do
            g.PushID('gsq-rule-' .. i)
            scoped(nil, function() g.PopID() end, function()
            if r.opaque then
                colored(M.theme.bad, '[kept]')
                tooltip('This rule uses options this editor cannot show. It is kept exactly as it is.')
            else
                local on = { r.on ~= false }
                if g.Checkbox('##on', on) and not readonly then
                    r.on = on[1]
                    d.dirty = true
                end

                tooltip(r.on ~= false and 'On: the mate uses this rule.' or 'Off: skipped.')
            end

            same()
            local text = string.format('%d. %s', i, M.rule_short(r, cat)) -- (compact; the full wording is the tooltip)
            local full = string.format('%d. %s', i, M.rule_summary(r, cat))
            local selected = S.sel == i
            local list = row_colors(selected)
            list[#list + 1] = { 'ImGuiCol_Text', r.on == false and M.theme.muted or nil }
            with_colors(list, function()
                if g.Selectable(text .. '##sel', selected) then
                    S.sel = i
                end
            end)
            row_outline(selected)

            tooltip(full) -- (the full wording, also when the panel is too narrow for the line)
            if S.checks[i] then
                wrapped(M.theme.bad, 'Rule ' .. i .. ' is left out for this mate now: ' .. M.readable(S.checks[i]))
            end
            end)
        end
    end)
end

-- (0.3.1) layout helpers: one row's height, the cursor (to measure what a block took last frame), a child without border
local function row_h()
    local g = imgui()
    if g.GetFrameHeightWithSpacing then
        local h = g.GetFrameHeightWithSpacing()
        if type(h) == 'number' and h > 0 then
            return h
        end
    end

    return s(24)
end

local function cursor_y()
    local g = imgui()
    if g.GetCursorPosY then
        local y = g.GetCursorPosY()
        if type(y) == 'number' then
            return y
        end
    end

    return nil
end

local function plain_child(id, size, fn)
    local g = imgui()
    local shown = g.BeginChild(id, size, rawget(_G, 'ImGuiChildFlags_None') or 0)
    scoped(nil, function() g.EndChild() end, function()
        if shown then
            fn()
        end
    end)
end

S.layout = S.layout or {}

-- a list's height from its rows: just its rows for a short list (at least minRows), at most `maxH` (then it scrolls
-- in its own child)
function M.list_height(rows, rowH, maxH, minRows)
    local want = math.max(rows, minRows or 1, 1) * rowH + s(10)
    return math.floor(math.min(want, maxH))
end

-- (0.3.1 polish) the rule list's height, in whole rows: its rules plus a little room to add more (2 rows, up to 8 in all;
-- at least 4), so a short set gets a usable list without many empty rows and a longer one grows with its rules - as far
-- as the free space goes (the right side minus what the editor below needs, `rest`). With more rules than that it
-- scrolls in its own child (32 rules), never below 4 rows (or its rules, when fewer); the outer side scrolls then.
function M.rule_list_height(nRules, rowH, bodyH, rest)
    local pad = s(10)
    local spareRows = math.floor((bodyH - rest - s(8) - pad) / rowH)
    local rows = math.max(nRules, math.min(8, math.max(4, nRules + 2)))
    rows = math.min(rows, math.max(spareRows, math.min(math.max(nRules, 1), 4)))
    return math.floor(math.max(rows, 1) * rowH + pad), rows
end

-- (0.3.3) Export: the open Rule Set's share code, read-only, with one Copy button. Import: paste a code, Preview, Import
-- as New Rule Set. No files: a code is pasted and copied like any text.
function M.code_for_draft(d)
    S.io = S.io or {}
    local key = d and table.concat({ tostring(d.job), tostring(d.name), table.concat(encodings(d.rules or {}), ';') }, '|') or ''
    if S.io.codeKey ~= key then
        S.io.codeKey = key
        S.io.code, S.io.codeWhy = M.export_code(d)
    end

    return S.io.code, S.io.codeWhy
end

local function io_panel(mate)
    local g = imgui()
    S.io = S.io or {}
    local io_ = S.io
    local w = math.max(s(200), available() - s(4))
    local readOnly = rawget(_G, 'ImGuiInputTextFlags_ReadOnly') or 0
    g.Separator()
    if S.ioOpen == 'export' then
        heading('Export')
        local d = S.draft
        if d == nil then
            wrapped(M.theme.secondary, 'Open a Rule Set first (click one above, or make a new one).')
        else
            wrapped(nil, string.format('"%s"  -  %s, %d rules%s', tostring(d.name), tostring(d.job), #d.rules,
                d.dirty and '  (with your unsaved changes, as shown)' or ''))
            local code, why = M.code_for_draft(d)
            if code == nil then
                wrapped(M.theme.bad, 'No share code: ' .. tostring(why))
            else
                local buf = { code }
                if g.InputTextMultiline then
                    g.InputTextMultiline('##gsq-io-code', buf, #code + 1, { w, s(48) }, readOnly)
                else
                    width(w)
                    g.InputText('##gsq-io-code', buf, #code + 1, readOnly)
                end

                tooltip('The whole Rule Set as one code (' .. #code .. ' characters). Anyone with Gambits can import it.')
                local clicked = false
                with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                              { 'ImGuiCol_Text', M.theme.goText } }, function()
                    clicked = button('Copy Share Code##gsq-io-copy', s(150))
                end)
                if clicked then
                    M.copy_code(code)
                end

                tooltip('Copies the code. Paste it into Discord or a message; the other player pastes it into Import.')
            end
        end
    else
        heading('Import')
        wrapped(M.theme.secondary, 'Paste a share code (Ctrl+V), then Preview Import.')
        local buf = { io_.text or '' }
        if g.InputTextMultiline then
            g.InputTextMultiline('##gsq-io-text', buf, M.IO_MAX_TEXT + 1, { w, s(60) })
        else
            width(w)
            g.InputText('##gsq-io-text', buf, M.IO_MAX_TEXT + 1)
        end

        if buf[1] ~= io_.text then
            io_.text, io_.preview, io_.problems = buf[1], nil, nil
        end

        if button('Preview Import##gsq-io-preview') then
            local catJob = mate and S.cat and mate.job or nil
            io_.preview, io_.problems = M.parse_import(io_.text, S.cat, catJob)
            if io_.preview then io_.problems = nil end
        end

        tooltip('Reads the code (data only) and shows the Rule Set. Nothing changes yet.')
        if io_.preview then
            same_if_fits(s(190))
            if button('Import as New Rule Set##gsq-io-import') then
                M.import_apply(io_.preview)
                io_.preview, io_.text = nil, ''
            end

            tooltip('Opens it in the editor as a NEW Rule Set, not saved and not assigned. Your saved sets are not changed.')
        end

        if io_.problems then
            for _, why in ipairs(io_.problems) do
                wrapped(M.theme.bad, 'Not imported: ' .. tostring(why))
            end
        elseif io_.preview then
            local d = io_.preview.draft
            wrapped(M.theme.ok, string.format('"%s"  -  %s, %d rules', d.name, d.job, #d.rules))
            if mate and d.job ~= mate.job then
                wrapped(M.theme.gold, string.format('This is a %s Rule Set: after Save it is listed for %s squad mates, not for %s (%s).',
                    d.job, d.job, mate.name, mate.job))
            end

            for i, r in ipairs(d.rules) do
                wrapped(r.on == false and M.theme.secondary or nil, string.format('%d. %s%s', i, M.rule_summary(r, S.cat),
                    r.on == false and '  (off)' or ''))
            end

            for _, w2 in ipairs(io_.preview.warnings or {}) do
                wrapped(M.theme.gold, w2)
            end
        end
    end

    if button('Close##gsq-io-close') then
        S.ioOpen = nil
        S.io = { text = '' }
    end
end
-- (0.3.5) What a Rule Set is to the selected mate, for its row in the list: a word, a text colour, a tooltip line.
--   active       the SERVER reports that the mate runs it now (green). Never said from the choice alone.
--   Apply needed chosen for the mate, the mate is out and does not run it (the theme's warning colour)
--   next call    chosen for the mate, which is not called
--   chosen       chosen, on a server that does not report what a mate runs, or while that is being checked
function M.set_mark(num, mate)
    local st = M.UI.states(M.theme)
    local live = M.cap('live') and mate.live or nil
    local sure = live ~= nil and not S.liveUnsure and not S.liveFailed
    if sure and live.state == 'set' and live.num == num then
        return 'active', st.active, string.format('Active: the server reports that %s runs this set now.', mate.name)
    end

    if num ~= mate.chosen then
        if sure and live.state == 'pending' and live.num == num then
            return 'still running', st.warn, string.format('%s still runs this set from its last call; another one is chosen. Apply calls %s again.', mate.name, mate.name)
        end

        return nil
    end

    if not sure then
        return 'chosen', nil, string.format('Chosen for %s.%s', mate.name, live == nil and ' This server does not report what a mate runs.' or ' What it runs is being checked.')
    elseif not mate.out or live.state == 'off' then
        return 'next call', st.secondary, string.format('Chosen for %s: used when %s is called.', mate.name, mate.name)
    elseif live.state == 'addon' then
        return 'chosen', nil, string.format('Chosen for %s, but an add-on runs %s.', mate.name, mate.name)
    end

    return 'Apply needed', st.warn, string.format('Chosen for %s, which does not run it now. Apply calls %s again.', mate.name, mate.name)
end

-- (0.3.5) The second line of the status area: what the selected mate RUNS, in the server's words. text, tone.
function M.running_line(m, d)
    local live = M.cap('live') and m.live or nil
    local function name(num)
        return num > 0 and M.set_label(num) or 'default job rules'
    end

    if live == nil then
        return 'not reported by this server' .. (m.chosen > 0 and ('  (chosen: ' .. name(m.chosen) .. ')') or ''), 'note'
    elseif S.liveUnsure then
        return 'checking...', 'note'
    elseif S.liveFailed then
        return 'not confirmed: the server did not answer', 'gold'
    elseif live.state == 'off' or not m.out then
        return 'nothing: not called.  Next call: ' .. name(m.chosen), 'note'
    elseif live.state == 'set' then
        local other = d ~= nil and d.num ~= live.num
        return name(live.num) .. (live.dropped > 0 and string.format('  (%d rule%s skipped)', live.dropped, live.dropped == 1 and '' or 's') or '')
            .. (other and '   - not the set open here' or ''), 'ok'
    elseif live.state == 'job' then
        return 'default job rules', 'text'
    elseif live.state == 'fallback' then
        return 'default job rules  (the chosen Rule Set is not used)', 'bad'
    elseif live.state == 'pending' then
        return name(live.num) .. '   - Apply needed for: ' .. name(m.chosen), 'gold'
    elseif live.state == 'addon' then
        return 'rules of an add-on (not Squads, not Rule Sets)', 'note'
    end

    return 'not reported for this call', 'note'
end

local function sets_panel(mate, panelH)
    local g = imgui()
    heading(mate.job .. ' Rule Sets')
    -- (0.3.1) as high as its rows (at least 3), at most half the panel; "in use" (green) and "editing" (highlight) differ
    -- (0.3.5) with room, the list shows more sets: up to what the panel has left above the buttons below it
    local listH = M.list_height(#S.sets, row_h(), math.max(s(80), (panelH or s(400)) * 0.5, (panelH or s(400)) - s(250)), 3)
    child('##gsq-sets', { 0, listH }, function()
        if #S.sets == 0 then
            wrapped(M.theme.secondary, 'No ' .. mate.job .. ' Rule Sets yet. Press New or choose a Starter.')
        end

        for _, set in ipairs(S.sets) do
            local mine = string.find(set.flags, 'o', 1, true) ~= nil
            local ro = string.find(set.flags, 'r', 1, true) ~= nil
            local editing = S.draft ~= nil and S.draft.num == set.num
            -- (0.3.5) three things a row can say at once: SELECTED (the frame), what the MATE does with it (the text
            -- colour and a word), and that it is open in the editor. "active" is the server's word (M.set_mark).
            local mark, tone, markTip = M.set_mark(set.num, mate)
            -- (0.3.6) the row is the set's name. Only "active" is said on it (green: the server reports that the mate runs
            -- it); what is chosen for the next call, Apply needed and unsaved changes are in the status area below the
            -- rules and in this row's tooltip, not squeezed in after the name
            local active = mark == 'active'
            local label = string.format('%d  %s%s', set.num, set.name, active and '   (active)' or '')
            local selected = S.selectedSet == set.num
            local list = row_colors(selected)
            if active and tone then
                list[#list + 1] = { 'ImGuiCol_Text', tone }
            end

            with_colors(list, function()
                if g.Selectable(label .. '##gsq-set-' .. set.num, selected) then
                    M.select_set(set.num) -- (one click selects and opens it)
                end
            end)
            row_outline(selected)

            tooltip(string.format('Rule Set %d: %s\n%d rules, %s%s%s%s', set.num, set.name, set.rules,
                mine and 'yours' or 'written by hand (copy it to change it)', ro and ', read-only' or '',
                markTip and ('\n' .. markTip) or '', editing and ('\nOpen in the editor' .. (S.draft.dirty and ', with unsaved changes.' or '.')) or ''))
        end
    end)

    local sel
    for _, set in ipairs(S.sets) do
        if set.num == S.selectedSet then
            sel = set
        end
    end

    if button('New##gsq-new') then
        M.new_set(mate.job)
        S.sel = 1
    end

    tooltip('A new ' .. mate.job .. ' Rule Set (saved only when you press Save).')
    local starterNote = '\n\nOptional: it only fills a new, unsaved Rule Set to look at and change. Saving, assigning and '
        .. 'applying stay your choice. Once assigned, a Rule Set replaces ' .. mate.name .. '\'s usual job rules; the built-in '
        .. 'rules are never changed and "Restore default job rules" goes back to them.'
    local function use_template(i)
        local made, why = M.new_from_template(mate.job, i, S.cat)
        if made == nil then
            say(why, false)
        end

        S.sel = 1
    end

    local tpls = M.templates_for(mate.job)
    if #tpls == 1 then
        same_if_fits(s(150))
        if button('Starter: ' .. tpls[1].name .. '##gsq-tpl1') then
            use_template(1)
        end

        tooltip(tpls[1].about .. starterNote)
    elseif #tpls > 1 then
        -- (0.3.1) several starters for a job (THF): one dropdown, each entry's description as its tooltip
        same_if_fits(s(190))
        width(s(190))
        local idx = {}
        for i = 1, #tpls do
            idx[i] = i
        end

        local pick = combo('##gsq-tpl', 0, idx, function(i) return tpls[i] and ('Starter: ' .. tpls[i].name) or 'Starter...' end,
            function(i) return tpls[i] and tpls[i].about end)
        if pick ~= 0 and tpls[pick] then
            use_template(pick)
        end

        tooltip('A starting point for a new ' .. mate.job .. ' Rule Set (' .. #tpls .. ' to choose from).' .. starterNote)
    elseif mate.job == 'SMN' and M.cap('smn') and M.SMN_STARTERS[1] then
        -- (F13) a Summoner's starter: avatar settings and pact rules (a Rule Set has no pet actions), shown in the Summoner
        -- section below as an unsaved starter. Saving it is your choice; Rule Sets and assignments are never touched.
        same_if_fits(s(170))
        if button('Starter: ' .. M.SMN_STARTERS[1].name .. '##gsq-tpl-smn') then
            M.smn_use_starter(mate, 1)
        end

        tooltip(M.SMN_STARTERS[1].about .. '\n\nOptional: it opens in the Summoner section below as an unsaved starter to look '
            .. 'at and change. Saving puts its settings and pact rules on ' .. mate.name .. ' (replacing ' .. mate.name
            .. '\'s pact rules); Rule Sets and their assignments are not changed.')
    end

    same_if_fits(s(70))
    if button('Export##gsq-io-export') then
        S.ioOpen = S.ioOpen ~= 'export' and 'export' or nil
    end

    tooltip('A share code for the Rule Set open in the editor, to copy into Discord or a message.')
    same_if_fits(s(70))
    if button('Import##gsq-io-import-open') then
        S.ioOpen = S.ioOpen ~= 'import' and 'import' or nil
    end

    tooltip('Paste a share code someone gave you: it becomes a new Rule Set (not saved, not assigned).')
    if S.ioOpen then
        io_panel(mate)
    end

    if S.confirmOpen then
        wrapped(M.theme.gold, string.format('"%s" has unsaved changes. Open %s anyway? Your changes are kept as the unsaved draft.',
            S.draft and S.draft.name or '?', M.set_label(S.confirmOpen)))
        if button('Open it##gsq-confirm-open') then M.confirm_open(true) end
        same_if_fits(s(110))
        if button('Keep editing##gsq-confirm-keep') then M.confirm_open(false) end
    end

    if sel then
        same_if_fits(s(60))
        if button('Copy##gsq-copy') then
            M.open_set(sel.num, true)
            S.sel = 1
        end

        tooltip('A new set of your own with the same rules.')
        if string.find(sel.flags, 'o', 1, true) and not string.find(sel.flags, 'r', 1, true) then
            same_if_fits(s(110))
            if S.confirmDelete == sel.num then
                with_colors({ { 'ImGuiCol_Button', M.theme.bad }, { 'ImGuiCol_ButtonHovered', times(M.theme.bad, 1.15) } }, function()
                    if button('Really delete?##gsq-del2') then
                        S.confirmDelete = nil
                        M.delete_set(sel.num, sel.rev)
                    end
                end)
            elseif button('Delete##gsq-del') then
                S.confirmDelete = sel.num
            end
        end
    end

    g.Separator()
    -- (0.3.4) Save, Assign and Apply are in one place now: the bar below the rules, which shows the ones that fit the
    -- open set and this mate. Here: what the mate would leave out, and the way back to its default job rules.
    heading('Check and reset')
    if sel then
        local checkLabel = mate.out and 'Check' or ('Check (' .. mate.name .. ' not summoned)')
        if button(checkLabel .. '##gsq-check') then M.check_set(mate.slot, sel.num) end
        tooltip('Which rules ' .. mate.name .. ' would leave out now, and why. The server checks with ' .. mate.name
            .. '\'s current level and sub job, so ' .. mate.name .. ' must be called (out).'
            .. (mate.out and '' or ('\nThe last Refresh showed ' .. mate.name .. ' not summoned: summon ' .. mate.name .. ', press Refresh, then Check.'))
            .. ' Check never summons anyone.')
    end

    if button('Restore default job rules##gsq-off') then M.assign(mate.slot, nil, true) end
    tooltip(mate.name .. ' stops using its Rule Set and goes back to the usual ' .. mate.job .. ' job rules (applied at once '
        .. 'when summoned). Your saved Rule Sets are kept. The Squad Role and Mode (Squad menu) filter those job rules again.')
    -- (the separate "Apply now" button is gone; 0.3.4: Assign, Apply and their Save forms are in the bar below the rules)
    local r = S.restorable
    if r and r.job == mate.job and not (S.draft and S.draft.dirty) then
        if button('Restore unsaved draft##gsq-restore') then
            S.draft, S.restorable, S.sel = r, nil, 1
        end

        tooltip('Your unsaved changes to "' .. tostring(r.name) .. '".')
    end
end

local function editor_panel()
    local g = imgui()
    local d = S.draft
    if d == nil then
        heading('Rules')
        wrapped(M.theme.secondary, 'Click a Rule Set to open it, or press New or a Starter. Edits stay here until you press Save.')
        return
    end

    if S.cat == nil then
        if S.catError then
            colored(M.theme.bad, 'The choices from the server were incomplete (' .. S.catError .. '). Press Refresh.')
        else
            note('Loading the choices from the server...')
        end

        return
    end

    local readonly = d.readonly == true
    if S.sel == nil or d.rules[S.sel] == nil then
        S.sel = #d.rules > 0 and 1 or nil
    end

    -- (beta polish) always say what is being edited, by name, and for which job
    local title = (d.name and d.name ~= '' and ('"' .. d.name .. '"') or 'New Rule Set') .. ' (' .. tostring(d.job) .. (d.num > 0 and (', #' .. d.num) or ', new') .. ')'
    -- (0.3.5) what is edited, here; whether it is saved, used or running is said once, in the status area above the
    -- Save buttons (it stood here too, as "- not saved" and "in use by", from the selection alone)
    heading(readonly and ('Viewing ' .. title .. ' - read-only: Copy it to change it') or ('Editing ' .. title))
    local m = M.mate()
    if m and d.job ~= m.job then
        wrapped(M.theme.gold, string.format('This is a %s Rule Set; %s is %s now.', tostring(d.job), m.name, m.job))
    end
    same_if_fits(s(100))
    colored(#d.rules >= M.MAX_RULES and M.theme.gold or M.theme.secondary, string.format('%d of %d rules', #d.rules, M.MAX_RULES))
    if not readonly then
        same_if_fits(s(180))
        width(math.max(s(180), math.min(s(320), available() - s(4))))
        local name = text_field('##gsq-setname', d.name, M.NAME_MAX + 1)
        if name ~= d.name then
            d.name, d.dirty = name, true
        end

        tooltip('The name of this Rule Set (letters, digits, spaces, -).')
    end

    if d.uneditable then
        wrapped(M.theme.bad, 'Rules marked [kept] use options this editor cannot show. They are kept exactly as they are, '
            .. 'so this set is read-only here.')
    end

    -- (0.3.1) the list follows its rules and the free space (M.rule_list_height); the rest of the editor is the
    -- largest height measured for this set, Weapon Skills state and panel size, so the list does not jump when another
    -- rule is selected
    local bodyH = S.layout.bodyH or s(420)
    local rest = S.layout.restH or s(240)
    local rulesH = M.rule_list_height(#d.rules, row_h(), bodyH, rest)
    rule_list(d, S.cat, readonly, rulesH)
    local afterList = cursor_y()
    if not readonly then
        -- (0.3.5) next to the list, in the smaller size: what is used all the time. A rule is switched on and off with
        -- the tick box of its row (the On / off button did the same and is gone). Top and Bottom are in More.
        compact(function()
            if button('Add rule##gsq-add') then S.sel = M.add_rule(d, S.sel) end
            tooltip('A new rule after the selected one.')
            same_if_fits(s(40))
            if button('Up##gsq-up') then S.sel = M.move_rule(d, S.sel, -1) end
            tooltip('The selected rule one place up: it is tried earlier.')
            same_if_fits(s(50))
            if button('Down##gsq-down') then S.sel = M.move_rule(d, S.sel, 1) end
            tooltip('The selected rule one place down: it is tried later.')
            same_if_fits(s(70))
            if button('Remove##gsq-remove') then
                S.sel, S.checks = M.remove_rule(d, S.sel), {}
            end
            tooltip('Takes the selected rule out of this Rule Set (saved only when you press Save).')
            -- (0.3.4) a rule's place is its priority: the two ends in one step instead of up to 31
            same_if_fits(s(80))
            width(s(80))
            local more = combo('##gsq-rulemore', 0, { 1, 2 }, function(v)
                return v == 1 and 'Move to top' or v == 2 and 'Move to bottom' or 'More'
            end, function(v)
                return v == 1 and 'The selected rule becomes the first: it is tried first.' or v == 2 and 'The selected rule becomes the last: it is tried last.' or nil
            end)
            tooltip('More for the selected rule: move it to the top or to the bottom.')
            if more == 1 or more == 2 then
                S.sel, S.checks = M.move_rule_end(d, S.sel, more == 1), {}
            end
        end)
    end

    g.Separator()
    local r = S.sel and d.rules[S.sel]
    if r then
        heading(string.format('Selected rule %d: Target -> Conditions -> Action', S.sel))
        rule_editor(d, r, S.cat, readonly)
        wrapped(M.theme.secondary, M.rule_summary(r, S.cat))
    end

    return afterList
end

-- (0.3.1) the Save bar: always visible below the right side's scrolling content (also with 32 rules or the Weapon
-- Skills section open)
-- (0.3.4) It is the one place for everything that stores or uses the Rule Set open in the editor. M.bar_state says,
-- for that set and the selected mate, which state line to show and which actions fit: never two ways to do the same
-- thing, and at most one that calls a mate again. What a mate RUNS comes from the server (the mates answer, server
-- capability "live"); a server that does not report it never makes the editor say "Active".
--   returns { state = text, tone = 'ok' | 'gold' | 'bad' | 'note', note = text or nil,
--             actions = { { id = 'save' | 'save_apply' | 'save_assign' | 'assign' | 'apply', label, tip, primary } ... } }
function M.bar_state(d, m)
    local out = { actions = {} }
    local function act(id, label, tip, primary)
        out.actions[#out.actions + 1] = { id = id, label = label, tip = tip, primary = primary == true }
    end

    if d == nil or m == nil then
        return out
    end

    local editable = not d.readonly and not d.uneditable
    local isSaved = (d.num or 0) > 0
    local inUse = isSaved and m.chosen == d.num
    local jobOk = d.job == m.job
    local live = m.live
    -- what an Apply does on this server: one mate when the server said it can, else every mate that is out
    local reach = M.cap('reapply1') and string.format('calls %s out again (about 4 seconds); the other mates stay out', m.name)
        or 'calls every mate that is out again (this server cannot call one mate alone)'

    if d.dirty and editable then
        out.state, out.tone = isSaved and 'Unsaved changes' or 'Not saved yet', 'gold'
        act('save', 'Save', 'Send this Rule Set to the server, which checks and stores it. No mate is touched.', false)
        if not jobOk then
            out.note = string.format('This is a %s Rule Set: it cannot be used by %s (%s).', tostring(d.job), m.name, m.job)
        elseif inUse and m.out then
            act('save_apply', 'Save & Apply', string.format('Saves, then %s, so that %s runs the saved rules. '
                .. 'If only the name changed there is nothing to apply.', reach, m.name), true)
        elseif inUse then
            out.note = string.format('%s uses this Rule Set and is not summoned: the saved rules apply when it is called.', m.name)
        elseif m.out then
            act('save_assign', 'Save, Assign & Apply', string.format('Saves, assigns this Rule Set to %s, then %s.', m.name, reach), true)
        else
            act('save_assign', 'Save & Assign', string.format('Saves and assigns this Rule Set to %s. %s is not summoned: '
                .. 'it applies when called.', m.name, m.name), true)
        end

        return out
    end

    if not isSaved then
        out.state, out.tone = 'Not saved yet', 'gold'
        return out
    end

    if not jobOk then
        out.state, out.tone = 'Saved', 'note'
        out.note = string.format('This is a %s Rule Set: it cannot be used by %s (%s).', tostring(d.job), m.name, m.job)
        return out
    end

    -- what the mate runs (and whether it is out, and which set is chosen) is not known for sure right now: no state
    -- is claimed and nothing that calls a mate is offered until the server has answered
    if S.liveUnsure and M.cap('live') then
        out.state, out.tone = string.format('Checking what %s runs...', m.name), 'note'
        return out
    end

    if S.liveFailed and M.cap('live') then
        out.state, out.tone = 'Not confirmed', 'gold'
        out.note = string.format('The server did not answer when asked what %s runs. Refresh asks again.', m.name)
        return out
    end

    if not inUse then
        out.state, out.tone = 'Saved, not used by ' .. m.name, 'note'
        if m.out then
            act('assign', 'Assign & Apply', string.format('Assigns this Rule Set to %s, then %s.', m.name, reach), true)
        else
            act('assign', 'Assign', string.format('Assigns this Rule Set to %s. %s is not summoned: it applies when called.',
                m.name, m.name), true)
        end

        return out
    end

    -- saved, and the set chosen for this mate
    if not m.out then
        out.state, out.tone = string.format('Selected for %s (applies when called)', m.name), 'note'
        return out
    end

    local applyTip = 'Apply: ' .. reach .. '.'
    if live == nil then
        -- an older server does not say what the mate runs: "Apply needed" only after a Save this editor made itself
        if S.needApply[m.slot] then
            out.state, out.tone = 'Apply needed', 'gold'
            out.note = string.format('%s runs the rules of its last call until it is called again.', m.name)
            act('apply', 'Apply', applyTip, true)
        else
            out.state, out.tone = 'Selected for ' .. m.name, 'note'
            out.note = 'This server does not report what a mate runs. After a change, Apply calls it again.'
            act('apply', 'Apply', applyTip, false)
        end
    elseif live.state == 'set' and live.num == d.num then
        out.state, out.tone = 'Active on ' .. m.name, 'ok'
        if live.dropped > 0 then
            out.note = string.format('%d rule%s cannot be used at %s\'s level or job and %s left out (Check shows which).',
                live.dropped, live.dropped == 1 and '' or 's', m.name, live.dropped == 1 and 'is' or 'are')
        end
    elseif live.state == 'addon' then
        out.state, out.tone = 'Run by an add-on', 'note'
        out.note = string.format('An add-on runs %s: Squads and Rule Sets do not.', m.name)
    elseif live.state == 'fallback' then
        out.state, out.tone = 'Selected, but not used', 'bad'
        out.note = string.format('%s runs its default job rules: %s.', m.name, M.LIVE_FB[live.fb] or 'the Rule Set could not be used')
        act('apply', 'Apply', applyTip, false)
    else
        out.state, out.tone = 'Apply needed', 'gold'
        out.note = string.format('%s runs the rules of its last call: %s.', m.name,
            live.state == 'pending' and (M.LIVE_WHY[live.why] or 'the settings changed since') or 'it was called before this Rule Set was chosen')
        act('apply', 'Apply', applyTip, true)
    end

    return out
end

-- one action of the bar. Returns what the editor function returned (false: refused, e.g. while it talks to the server).
function M.bar_do(id, d, m)
    if d == nil or m == nil then
        return false
    end

    if id == 'save' then
        return M.save()
    elseif id == 'save_apply' then
        return M.save({ kind = 'apply', slot = m.slot })
    elseif id == 'save_assign' then
        return M.save({ kind = 'assign', slot = m.slot })
    elseif id == 'assign' then
        return M.assign_apply(m.slot, d.num)
    elseif id == 'apply' then
        return M.apply({ slot = m.slot })
    end

    return false
end

M.BAR_IDS = { save = 'gsq-save', save_apply = 'gsq-save-apply', save_assign = 'gsq-save-assign', assign = 'gsq-assign', apply = 'gsq-apply' }

-- (0.3.5) The status area, always in view under the rules, above the buttons it belongs to:
--   Editing    which Rule Set is open, and its state for this mate (M.bar_state: unsaved, saved, Apply needed, Active...)
--   <Mate> runs  what the mate runs now, as the SERVER reports it (M.running_line); it can be another set than the open one
-- M.status_lines returns the two lines as { label, text, tone, extra, extraTone } for the window and for the tests.
function M.status_lines(d, m, st)
    st = st or M.bar_state(d, m)
    local what = (d.name and d.name ~= '' and ('"' .. d.name .. '"') or 'New Rule Set') .. (d.num > 0 and ('  (#' .. d.num .. ')') or '  (new)')
    local runs, tone = M.running_line(m, d)
    return {
        { 'Editing', what, 'text', st.state, st.tone },
        { m.name .. ' runs', runs, tone },
    }
end

-- (0.3.9) where the values of the status lines start: after the widest label and a gap, at least 96 px at this Size
function M.status_label_w(lines)
    local w = s(96)
    for _, line in ipairs(lines) do
        w = math.max(w, math.floor(text_w(line[1]) + s(10) + 0.5))
    end

    return w
end

local function save_bar(d)
    local g = imgui()
    g.Separator()
    local m = M.mate()
    local busy = M.busy() or S.apply ~= nil
    local st = M.bar_state(d, m)
    local tones = { ok = M.theme.ok, gold = M.theme.warn or M.theme.gold, bad = M.theme.bad, note = M.theme.secondary, text = M.theme.text }
    -- (0.3.9) the label column is as wide as its longest label ("Sturgeon runs" at 120 % did not fit 96 px and the
    -- value was drawn over it); a value that does not fit the rest of the line wraps there, under itself
    local lines = M.status_lines(d, m, st)
    local labelW = M.status_label_w(lines)
    for i, line in ipairs(lines) do
        colored(M.theme.muted, line[1])
        g.SameLine(labelW)
        if text_w(line[2]) > available() then
            wrapped(tones[line[3]] or M.theme.text, line[2])
        else
            colored(tones[line[3]] or M.theme.text, line[2])
        end
        if i == 2 then
            tooltip(M.DEFAULT_RULES_HELP) -- (what "default job rules" are, and that the Squad Role filters only those)
        end

        if line[4] then
            same_if_fits(s(150))
            colored(tones[line[5]] or M.theme.secondary, line[4])
        end
    end

    for i, a in ipairs(st.actions) do
        if i > 1 then
            same_if_fits(s(170))
        end

        local label = busy and 'Wait...' or ((a.id == 'save' and d.dirty) and 'Save *' or a.label)
        local clicked = false
        local function draw()
            clicked = button(label .. '##' .. M.BAR_IDS[a.id], a.id == 'save' and s(110) or nil)
        end

        if a.primary or a.id == 'save' then
            with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                          { 'ImGuiCol_Text', M.theme.goText } }, draw)
        else
            draw()
        end

        tooltip(busy and 'The editor is talking to the server; this is possible again in a moment.' or a.tip)
        if clicked and not busy then
            M.bar_do(a.id, d, m)
        end
    end

    -- (the state itself is on the Editing line above; 0.3.4 had it after the buttons)
    if st.note then
        wrapped(M.theme.secondary, st.note)
    end
end

-- (0.3.9) for the tests only, as M._S: the two parts whose layout they check (a condition's row, the status lines)
M._draw = { condition_editor = condition_editor, save_bar = save_bar }

-- the bar is there for every set that is open with the server's choices loaded (0.3.4: also a read-only one, which can
-- still be assigned and applied)
local function editor_footer_shown(d)
    return d ~= nil and S.cat ~= nil and M.mate() ~= nil
end

-- the height the bar needs: its row, and one more line when it has a note
function M.footer_height(d)
    if not editor_footer_shown(d) then
        return 0
    end

    local st = M.bar_state(d, M.mate())
    local g = imgui()
    local row = g.GetFrameHeightWithSpacing and g.GetFrameHeightWithSpacing() or s(24)
    row = type(row) == 'number' and row or s(24)
    local line = g.GetTextLineHeightWithSpacing and g.GetTextLineHeightWithSpacing() or s(18)
    line = type(line) == 'number' and line or s(18)
    -- (0.3.5) the two status lines, then the buttons' row when there are buttons, and one more line for a note
    return math.floor(2 * line + (#st.actions > 0 and row or 0) + (st.note and line or 0) + s(14))
end

function M.ws_stored_text(d)
    if d.source == 'c' then
        return string.format('Custom: %s%s, %s.', M.WS_MODES[d.mode] or '?', d.mode == 2 and '' or (' at ' .. d.tp .. ' TP'), M.ws_name(d.ws))
    elseif d.source == 'd' then
        return 'Squad default (automatic skillchains, every weapon skill).'
    end

    local stored = 'No Gambits setting yet: the squad\'s own behaviour'
    if (d.legacyTp or 0) > 0 or (d.legacyWs or 0) > 0 then
        return stored .. string.format(' with your !squad ws choice (%s, %s).', d.legacyTp > 0 and (d.legacyTp .. ' TP') or 'skillchains',
            M.ws_name(d.legacyWs))
    end

    return stored .. ' (automatic skillchains).'
end

-- (0.3.1) the collapsed Weapon Skills section's one line. It asks the server for nothing: the settings are loaded when
-- the section is opened (as the tab was), so the editor sends exactly what it sent before; once loaded for this mate
-- the line says what is saved.
function M.ws_summary(mate)
    local w = S.ws
    if w == nil or w.slot ~= mate.slot then
        return 'Open to see and change ' .. mate.name .. '\'s weapon skill settings.'
    elseif w.loading and w.data == nil then
        return 'Loading...'
    elseif w.error then
        return 'Could not load them: open this section to try again.'
    elseif w.data == nil then
        return 'Loading...'
    end

    local text = M.ws_stored_text(w.data)
    if M.ws_edited() then
        text = text .. ' Unsaved weapon skill changes.'
    elseif w.data.out and w.data.applied == false then
        text = text .. ' Saved, not in use yet.'
    end

    return text
end

-- The Weapon Skills section (server version 5): one squad mate, its current main job. (0.3.1) inSection: drawn inside
-- the main editor's collapsible section (its header names it)
local function ws_panel(mate, inSection)
    local g = imgui()
    if not inSection then
        heading('Weapon Skills: ' .. mate.name .. ' (' .. mate.job .. ')')
    end

    wrapped(M.theme.secondary, 'Separate from Rule Sets: a Rule Set never changes these, and these never change a Rule Set.')
    if not M.ws_supported() then
        wrapped(M.theme.gold, 'This needs the server update (gambits_squad.lua version 5).')
        return
    end

    local w = S.ws
    if w == nil or w.slot ~= mate.slot then
        if not M.busy() then
            M.ws_load(mate.slot)
        end

        note('Loading...')
        return
    end

    if w.error then
        colored(M.theme.bad, 'Could not load them: ' .. M.readable(w.error))
        if button('Try again##gsq-ws-retry') then S.ws = nil end
        return
    end

    local d, e = w.data, w.edit
    if d == nil or e == nil then
        note('Loading...')
        return
    end

    -- what is stored now
    wrapped(M.theme.secondary, 'Saved: ' .. M.ws_stored_text(d))
    if not d.engine then
        wrapped(M.theme.gold, 'Custom needs the updated map server (xi_map); only Squad default can be used here.')
    end

    if d.usable == false then
        wrapped(M.theme.bad, string.format('%s cannot use %s now (weapon, skill level or quest): it uses Best available until it '
            .. 'can. Your choice is kept.', mate.name, M.ws_name(d.ws)))
    end

    if not d.out then
        wrapped(M.theme.secondary, mate.name .. ' is not summoned: saved settings apply when called. Summon ' .. mate.name
            .. ' and press Refresh to choose a specific weapon skill.')
    elseif d.applied == false then
        wrapped(M.theme.gold, 'Saved but not in use yet: press Apply WS settings now.')
    end

    g.Separator()
    local labelW = s(110)
    local function label(text)
        label_text(text)
        g.SameLine(labelW)
    end

    label('Control')
    width(s(200))
    local control = combo('##gsq-ws-ctl', e.control, { 0, 1 }, function(v) return v == 1 and 'Custom' or 'Squad default' end,
        function(v) return v == 1 and 'Your own mode, TP and weapon skill.' or 'The automatic party skillchains (as without Gambits).' end)
    if control ~= e.control and (control == 0 or d.engine) then
        e.control = control
    end

    if e.control == 1 then
        label('Mode')
        width(s(200))
        e.mode = combo('##gsq-ws-mode', e.mode, { 1, 2, 3, 4 }, function(v) return M.WS_MODES[v] or '?' end,
            function(v) return M.WS_MODE_HELP[v] end)
        tooltip(M.WS_MODE_HELP[e.mode] or '')
        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        wrapped(M.theme.secondary, M.WS_MODE_HELP[e.mode] or '')
        if e.mode ~= 2 then
            label(e.mode == 4 and 'TP' or 'TP to open')
            width(s(120))
            e.tp = combo('##gsq-ws-tp', e.tp, M.WS_TPS, function(v) return tostring(v) end)
            if e.mode == 3 then
                same_if_fits(s(300), labelW)
                wrapped(M.theme.secondary, '(opening only: closing is allowed from 1000 TP)')
            end
        end

        label('Weapon skill')
        width(s(240))
        local ids = { 0 }
        local inList = e.ws == 0
        for _, it in ipairs(w.list or {}) do
            ids[#ids + 1] = it.id
            inList = inList or it.id == e.ws
        end

        if not inList then
            ids[#ids + 1] = e.ws -- (the saved choice stays selectable, even when not in the list now)
        end

        e.ws = combo('##gsq-ws-ws', e.ws, ids, M.ws_name, function(v) return v == 0 and M.WS_BEST_HELP or nil end)
        tooltip(e.ws == 0 and M.WS_BEST_HELP or ('Only ' .. M.ws_name(e.ws) .. ' (when the mate can use it; otherwise Best available).'))
        if w.list == nil then
            same_if_fits(s(170), labelW)
            note(d.out and '(loading the list...)' or '(summon to see the list)')
        elseif not inList then
            same_if_fits(s(120), labelW)
            colored(M.theme.bad, '(not usable now)')
        end

        if g.SetCursorPosX then
            g.SetCursorPosX(labelW)
        end

        wrapped(M.theme.secondary, M.WS_3000_HELP)
    end

    g.Separator()
    local dirty = M.ws_dirty()
    with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                  { 'ImGuiCol_Text', M.theme.goText } }, function()
        if button((dirty and 'Save *' or 'Save') .. '##gsq-ws-save', s(90)) then
            M.ws_save(mate.slot, e)
        end
    end)
    tooltip('Store these settings for ' .. mate.name .. ' as ' .. mate.job .. ' (the server checks them).')
    same_if_fits(s(100))
    if button('Apply WS settings now##gsq-ws-apply') then M.ws_apply(mate.slot) end
    tooltip('Use the saved settings on ' .. mate.name .. ' now, without calling again (' .. mate.name .. ' must be summoned).')
    same_if_fits(s(170))
    if button('Reset to Squad default##gsq-ws-reset') then M.ws_reset(mate.slot) end
    tooltip('Back to the automatic skillchains for ' .. mate.job .. '. Your Custom choices are kept for later. Then Apply WS settings now.')
    same_if_fits(s(70))
    if button('Refresh##gsq-ws-refresh') then S.ws = nil end
end
M.ws_panel = ws_panel

-- (0.3.1) Weapon Skills as a collapsible section below the rule editor (was a second tab): the same panel, settings,
-- requests and buttons; collapsed it shows one summary line. Its open state is remembered (addon settings).
local function ws_section(mate)
    if not M.ws_supported() then
        return
    end

    local g = imgui()
    g.Separator()
    local open = S.wsOpen == true
    if g.CollapsingHeader then
        if g.SetNextItemOpen then
            g.SetNextItemOpen(open)
        end

        local shown = g.CollapsingHeader('Weapon Skills: ' .. mate.name .. ' (' .. mate.job .. ')##gsq-ws-section')
        open = shown == true
    elseif button((open and '[-] ' or '[+] ') .. 'Weapon Skills: ' .. mate.name .. '##gsq-ws-section') then
        open = not open -- (a binding without CollapsingHeader)
    end

    tooltip('The weapon skill settings of ' .. mate.name .. ' as ' .. mate.job .. ': separate from Rule Sets, with their own '
        .. 'Save. Click to ' .. (open and 'close' or 'open') .. ' this section.')
    if open ~= (S.wsOpen == true) then
        S.wsOpen = open
        if api.set_pref then
            api.set_pref('ws_open', open)
        end
    end

    if open then
        ws_panel(mate, true)
        M.wx_block(mate)
    else
        wrapped(M.theme.secondary, M.ws_summary(mate))
    end
end
M.ws_section = ws_section

-- ---------------------------------------------------------------- (F12, server capability "wsset") the WS gear set
-- One optional set per mate and main job, armor and accessories only: the server puts it on right before a weapon
-- skill and takes it off when the damage is done. The server checks every piece (given to the squad, job, level, slot,
-- a Rare item once) and says why a piece is left out. Requests: wxg (load), wxs (one piece), wxc (clear), wxl (choices).
M.WX_SLOTS = { 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15 }
M.WX_SLOT_NAMES = { [4] = 'Head', [5] = 'Body', [6] = 'Hands', [7] = 'Legs', [8] = 'Feet', [9] = 'Neck', [10] = 'Waist',
                    [11] = 'Ear 1', [12] = 'Ear 2', [13] = 'Ring 1', [14] = 'Ring 2', [15] = 'Back' }

-- GSQ|n|wx|slot|JOB|pieces|out|eng|active, then GSQ|n|wxp|eqslot|itemId|ok|Name|why ... -> d, or nil + why
function M.parse_wx(items)
    local f = items[1]
    if f == nil or f[3] ~= 'wx' or #f < 9 then
        return nil, 'the answer was not readable'
    end

    local d = { slot = tonumber(f[4]), job = f[5], count = tonumber(f[6]) or 0, out = f[7] == '1', engine = f[8] == '1',
                active = f[9] == '1', pieces = {} }
    for i = 2, #items do
        local p = items[i]
        local eq = tonumber(p[4] or '')
        if p[3] ~= 'wxp' or eq == nil or M.WX_SLOT_NAMES[eq] == nil then
            return nil, 'a line of the WS set was not readable'
        end

        d.pieces[eq] = { id = tonumber(p[5]) or 0, ok = p[6] == '1', name = (string.gsub(p[7] or '?', '_', ' ')),
                         why = (p[8] ~= nil and p[8] ~= '-') and p[8] or nil }
    end

    if d.slot == nil then
        return nil, 'the answer was not readable'
    end

    return d
end

-- GSQ|n|wxl|id:level:Name,... lines -> { { id, level, name } ... }, or nil + why
function M.parse_wxl(items)
    local list = {}
    for _, f in ipairs(items) do
        if f[3] ~= 'wxl' then
            return nil, 'a line of the item list was not readable'
        end

        for _, entry in ipairs(split(f[4] or '', ',')) do
            local id, level, name = string.match(entry, '^(%d+):(%d+):([%w_]+)$')
            if id == nil then
                return nil, 'the item list was cut or changed (' .. entry .. ')'
            end

            list[#list + 1] = { id = tonumber(id), level = tonumber(level), name = (string.gsub(name, '_', ' ')) }
        end
    end

    return list
end

local function wx_request(words, slot, done, failWhat)
    read_request(words, function(items)
        local d, why = M.parse_wx(items)
        if d == nil or d.slot ~= slot then
            return false, why or 'the answer was for another mate'
        end

        S.wx = S.wx and S.wx.slot == slot and S.wx or { slot = slot }
        S.wx.data, S.wx.loading, S.wx.error = d, false, nil
        if done then
            done(d)
        end

        return true
    end, function(why)
        if S.wx and S.wx.slot == slot then
            S.wx.loading = false
            if failWhat == nil then
                S.wx.error = why
            end
        end

        say((failWhat or 'Could not load the WS gear set') .. ': ' .. why, false)
    end)
end

function M.wx_load(slot)
    S.wx = { slot = slot, loading = true, eq = S.wx and S.wx.slot == slot and S.wx.eq or 4 }
    wx_request({ 'wxg', tostring(slot) }, slot)
end

function M.wx_list(slot, eq)
    read_request({ 'wxl', tostring(slot), tostring(eq) }, function(items)
        local list, why = M.parse_wxl(items)
        if list == nil then
            return false, why
        end

        if S.wx and S.wx.slot == slot then
            S.wx.choices, S.wx.choicesFor = list, eq
        end

        return true
    end, function(why)
        say('Could not load the item list: ' .. why, false)
    end)
end

-- store one piece (itemId 0 = none): the server checks it and answers with the whole set
function M.wx_set(slot, eq, itemId)
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Saving the WS gear set...'
    wx_request({ 'wxs', tostring(slot), tostring(eq), tostring(itemId) }, slot, function(d)
        S.progress = nil
        say(string.format('WS gear set saved (server checked): %d piece%s.%s', d.count, d.count == 1 and '' or 's',
            d.out and ' In use from the next weapon skill.' or ' It applies when the mate is called.'))
    end, 'WS gear set NOT saved')
    return true
end

function M.wx_clear(slot)
    if M.busy() then
        return busy_say()
    end

    wx_request({ 'wxc', tostring(slot) }, slot, function()
        say('WS gear set cleared: the normal outfit for weapon skills too.')
    end, 'WS gear set NOT cleared')
    return true
end

function M.wx_summary(d)
    if d == nil then
        return 'Loading...'
    elseif d.count == 0 then
        return 'No WS gear set: weapon skills use the normal outfit.'
    end

    local bad = 0
    for _, p in pairs(d.pieces) do
        bad = bad + (p.ok and 0 or 1)
    end

    return string.format('%d piece%s for weapon skills%s.', d.count, d.count == 1 and '' or 's',
        bad > 0 and string.format(' (%d left out now)', bad) or '')
end

-- the WS gear set block inside the Weapon Skills section
function M.wx_block(mate)
    if not M.cap('wsset') then
        return
    end

    local g = imgui()
    g.Separator()
    heading('WS gear set: ' .. mate.name .. ' (' .. mate.job .. ')')
    wrapped(M.theme.secondary, 'Armor and accessories worn only for the weapon skill itself: on right before it, off again when '
        .. 'its damage is done. Weapons and the look never change. Pieces follow the same rules as !squad equip.')
    local x = S.wx
    if x == nil or x.slot ~= mate.slot then
        if not M.busy() then
            M.wx_load(mate.slot)
        end

        note('Loading...')
        return
    end

    if x.error then
        colored(M.theme.bad, 'Could not load it: ' .. M.readable(x.error))
        if button('Try again##gsq-wx-retry') then S.wx = nil end
        return
    end

    local d = x.data
    if d == nil then
        note('Loading...')
        return
    end

    wrapped(M.theme.secondary, M.wx_summary(d))
    if not d.engine then
        wrapped(M.theme.gold, 'This needs the updated map server (xi_map) to be used in a fight.')
    end

    for _, eq in ipairs(M.WX_SLOTS) do
        local p = d.pieces[eq]
        if p then
            colored(p.ok and M.theme.text or M.theme.bad, string.format('%-7s %s', M.WX_SLOT_NAMES[eq], p.name))
            if not p.ok and p.why then
                tooltip('Left out now: ' .. p.why .. '. That slot keeps the normal gear.')
            end

            same_if_fits(s(80))
            if button('Remove##gsq-wx-del-' .. eq) then M.wx_set(mate.slot, eq, 0) end
        end
    end

    label_text('Slot')
    g.SameLine(s(60))
    width(s(110))
    local eq = combo('##gsq-wx-eq', x.eq or 4, M.WX_SLOTS, function(v) return M.WX_SLOT_NAMES[v] end)
    if eq ~= x.eq then
        x.eq, x.choices, x.pick = eq, nil, nil
    end

    same_if_fits(s(260))
    if x.choices == nil or x.choicesFor ~= x.eq then
        if button('Show items##gsq-wx-list') then M.wx_list(mate.slot, x.eq) end
        tooltip('The items ' .. mate.name .. ' may wear there (given to your squad, or all gear with "Squad gets all gear").')
    else
        local ids = {}
        local names = {}
        for _, it in ipairs(x.choices) do
            ids[#ids + 1] = it.id
            names[it.id] = string.format('%s (Lv%d)', it.name, it.level or 0)
        end

        width(s(240))
        x.pick = combo('##gsq-wx-item', x.pick or ids[1], ids, function(v) return names[v] or tostring(v) end)
        same_if_fits(s(80))
        if x.pick and button('Put in set##gsq-wx-put') then M.wx_set(mate.slot, x.eq, x.pick) end
        if #ids == 0 then
            note('(nothing ' .. mate.name .. ' can wear there)')
        end
    end

    if d.count > 0 then
        if button('Clear the WS gear set##gsq-wx-clear') then M.wx_clear(mate.slot) end
        tooltip('Weapon skills use the normal outfit again.')
        same_if_fits(s(80))
    end

    if button('Refresh##gsq-wx-refresh') then S.wx = nil end
end

-- ---------------------------------------------------------------- (F13, server capability "smn") the Summoner section
-- Per SMN mate: the avatar setting, how it behaves (normal attacks, Rage, Ward, between pulls, support out of combat,
-- whether rules may switch the avatar) and ordered pact rules ("use PACT on TARGET when COND"). The server owns what the
-- mate may do and what it pays (summon MP, perpetuation, the player's Blood Pact check). Requests: smg (load), sms
-- (settings), smr (one rule), smd (delete), smm (move), smp (the pact list).
M.SMN_AVATARS = { [0] = 'Auto (weakness)', 'Carbuncle', 'Ifrit', 'Titan', 'Leviathan', 'Garuda', 'Shiva', 'Ramuh', 'Fenrir', 'Keep current' }
M.SMN_MODES = { [0] = 'Auto (job default)', 'Off', 'Rules only' }
M.SMN_BETWEEN = { [0] = 'Keep it out', 'Release it', 'Release when MP < 50%' }
M.SMN_TARGETS = { 'SELF', 'MASTER', 'PARTY', 'ENEMY' }
M.SMN_TARGET_NAMES = { SELF = 'Itself', MASTER = 'You', PARTY = 'A party member', ENEMY = 'The enemy' }
M.SMN_CONDS = { 'ALWAYS', 'NOT_STATUS', 'STATUS', 'HPP_LT', 'HPP_GTE', 'MY_MPP_GTE', 'MY_MPP_LT' }
M.SMN_COND_NAMES = { ALWAYS = 'Always', NOT_STATUS = 'Lacks status', STATUS = 'Has status', HPP_LT = 'HP % below',
                     HPP_GTE = 'HP % at least', MY_MPP_GTE = 'My MP % at least', MY_MPP_LT = 'My MP % below' }
M.SMN_WHENS = { 'COMBAT', 'IDLE', 'ANY' }
M.SMN_WHEN_NAMES = { COMBAT = 'In combat', IDLE = 'Out of combat', ANY = 'Both' }
M.SMN_HELP = {
    avatar = 'Auto: the avatar the enemy is weakest to (switches when a new fight starts). Keep current: never switches by itself. '
        .. 'A pact rule may still switch to the avatar it needs, unless you turn that off below.',
    engage = 'Whether the avatar fights the mate\'s target with normal attacks. Rage, its timer and MP never stop them.',
    rage = 'Auto: the strongest Rage for the level whenever it is ready (with the MP left over after protected rules). '
        .. 'Rules only: only your Rage rules. A kind of pact you have rules for never uses the job default.',
    ward = 'Auto: the job default wards (heals first, then debuffs, then buffs you lack). Rules only: only your Ward rules.',
    between = 'What happens to the avatar a few seconds after a fight. It is always released before the mate rests.',
    idle = 'Out-of-combat support: rules set to Out of combat or Both may call an avatar and use its pact between fights.',
    switch = 'Whether a pact rule may switch to the avatar it needs (only when the summon, the pact and the upkeep while it '
        .. 'waits are affordable).',
    protect = 'Protected: the mate keeps this pact\'s MP for it; the default Rage is not used when it would dip below.',
}

function M.parse_smn(items)
    local f = items[1]
    if f == nil or f[3] ~= 'smn' or #f < 18 then
        return nil, 'the answer was not readable'
    end

    local d = { slot = tonumber(f[4]), job = f[5], avatar = tonumber(f[6]) or 0, engage = f[7] == '1', rage = tonumber(f[8]) or 0,
                ward = tonumber(f[9]) or 0, between = tonumber(f[10]) or 0, idle = f[11] == '1', ruleSwitch = f[12] == '1',
                out = f[13] == '1', current = f[14] ~= '-' and f[14] or nil, intent = f[15] ~= '-' and f[15] or nil,
                mp = tonumber(f[16]), maxmp = tonumber(f[17]), engine = f[18] == '1', rules = {} }
    for i = 2, #items do
        local r = items[i]
        if r[3] ~= 'smr' or #r < 11 then
            return nil, 'a rule line was not readable'
        end

        d.rules[#d.rules + 1] = { on = r[5] == '1', pact = r[6], target = r[7], cond = r[8], arg = r[9], when = r[10], protect = r[11] == '1' }
    end

    if d.slot == nil then
        return nil, 'the answer was not readable'
    end

    return d
end

function M.parse_smp(items)
    local list = {}
    for _, f in ipairs(items) do
        if f[3] ~= 'smp' then
            return nil, 'a line of the pact list was not readable'
        end

        for _, entry in ipairs(split(f[4] or '', ',')) do
            local name, avatar, level, kind, aim, effect, usable = string.match(entry, '^([%w_]+):([%w_]+):(%d+):(%a+):(%a+):([%w_%-]+):([01])$')
            if name == nil then
                return nil, 'the pact list was cut or changed (' .. entry .. ')'
            end

            list[#list + 1] = { name = name, avatar = avatar, level = tonumber(level), kind = kind, aim = aim,
                                effect = effect ~= '-' and effect or nil, usable = usable == '1' }
        end
    end

    return list
end

-- the rule as one readable line
function M.smn_rule_text(r)
    local cond = M.SMN_COND_NAMES[r.cond] or r.cond
    if r.cond ~= 'ALWAYS' then
        cond = cond .. ' ' .. tostring(r.arg)
    end

    return string.format('%s on %s when %s (%s)%s', M.pretty(r.pact or '?'), M.SMN_TARGET_NAMES[r.target] or r.target, cond,
        M.SMN_WHEN_NAMES[r.when] or r.when, r.protect and ', protected' or '')
end

local function smn_request(words, slot, done, failWhat)
    read_request(words, function(items)
        local d, why = M.parse_smn(items)
        if d == nil or d.slot ~= slot then
            return false, why or 'the answer was for another mate'
        end

        S.smn = S.smn and S.smn.slot == slot and S.smn or { slot = slot }
        S.smn.data, S.smn.loading, S.smn.error = d, false, nil
        S.smn.edit = { avatar = d.avatar, engage = d.engage, rage = d.rage, ward = d.ward, between = d.between, idle = d.idle,
                       ruleSwitch = d.ruleSwitch }
        if done then
            done(d)
        end

        return true
    end, function(why, kind, job)
        if S.smn and S.smn.slot == slot then
            S.smn.loading = false
            if failWhat == nil then
                S.smn.error = (job and job.code == 'notsmn') and 'notsmn' or why
            end
        end

        if not (job and job.code == 'notsmn') then
            say((failWhat or 'Could not load the Summoner settings') .. ': ' .. why, false)
        end
    end)
end

function M.smn_load(slot)
    S.smn = { slot = slot, loading = true }
    smn_request({ 'smg', tostring(slot) }, slot)
    read_request({ 'smp', tostring(slot) }, function(items)
        local list, why = M.parse_smp(items)
        if list == nil then
            return false, why
        end

        if S.smn and S.smn.slot == slot then
            S.smn.pacts = list
        end

        return true
    end, function() end)
end

function M.smn_save_settings(slot, e)
    if M.busy() then
        return busy_say()
    end

    S.progress = 'Saving the Summoner settings...'
    smn_request({ 'sms', tostring(slot), tostring(e.avatar), e.engage and '1' or '0', tostring(e.rage), tostring(e.ward),
        tostring(e.between), e.idle and '1' or '0', e.ruleSwitch and '1' or '0' }, slot, function(d)
        S.progress = nil
        say('Summoner settings saved (server confirmed).' .. (d.out and ' In use now.' or ' They apply when the mate is called.'))
    end, 'Summoner settings NOT saved')
    return true
end

-- rule n = the position (count + 1 adds one)
function M.smn_save_rule(slot, n, r)
    if M.busy() then
        return busy_say()
    end

    local arg = (r.cond == 'ALWAYS') and '0' or tostring(r.arg or '')
    if arg == '' then
        say('The condition needs a value (a status such as HASTE, or a percentage).', false)
        return false
    end

    smn_request({ 'smr', tostring(slot), tostring(n), r.on == false and '0' or '1', r.pact, r.target, r.cond, arg, r.when,
        r.protect and '1' or '0' }, slot, function()
        say(string.format('Pact rule %d saved (server checked).', n))
    end, 'Pact rule NOT saved')
    return true
end

function M.smn_delete_rule(slot, n)
    if M.busy() then
        return busy_say()
    end

    smn_request({ 'smd', tostring(slot), tostring(n) }, slot, function() say('Pact rule removed.') end, 'Pact rule NOT removed')
    return true
end

function M.smn_move_rule(slot, n, dir)
    if M.busy() then
        return busy_say()
    end

    smn_request({ 'smm', tostring(slot), tostring(n), tostring(dir) }, slot, nil, 'Pact rule NOT moved')
    return true
end

-- the example: "use Hastega when you lack Haste" (in a fight and out of it; its MP is protected)
function M.smn_hastega_example()
    return { on = true, pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'ANY', protect = true }
end

-- (F13) the Summoner starter: the job's template, the same idea as the Rule Set starters (M.TEMPLATES), but made of the
-- Summoner section's settings and pact rules, because a Rule Set has no pet actions. Using it only fills an unsaved
-- starter in the Summoner section; "Save starter" puts it on the mate. Nothing else is changed.
M.SMN_STARTERS = { {
    name = 'Basic Summoner',
    about = 'Garuda for support. Normal avatar attacks on (the avatar keeps fighting when Rage is skipped). '
        .. 'Rule 1 (Ward): Hastega on you when you lack Haste, its MP protected - needs level 48 for Hastega, and Garuda '
        .. '(level 10; with spells from scrolls, Garuda\'s pact). Below level 48 the rule waits and the mate uses rule 2. '
        .. 'Rule 2 (Rage): Claw on the enemy only while the mate has at least 60% MP, so MP is kept for support. '
        .. 'Garuda is called and switched to by the pact rules, which check the summon cost, the pact cost and the Blood '
        .. 'Pact timer. The avatar is released before the mate rests (always). Avatar: Keep current (no switching for '
        .. 'weakness). Rage and Ward: Rules only.',
    settings = { avatar = 9, engage = true, rage = 2, ward = 2, between = 0, idle = false, ruleSwitch = true },
    rules = {
        { on = true, pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'COMBAT', protect = true },
        { on = true, pact = 'CLAW', target = 'ENEMY', cond = 'MY_MPP_GTE', arg = '60', when = 'COMBAT', protect = false },
    },
} }

local function copyStarter(t)
    local out = { name = t.name, about = t.about, settings = {}, rules = {} }
    for k, v in pairs(t.settings) do out.settings[k] = v end
    for i, r in ipairs(t.rules) do
        local c = {}
        for k, v in pairs(r) do c[k] = v end
        out.rules[i] = c
    end

    return out
end

-- open the starter (a copy) in the mate's Summoner section, not saved
function M.smn_use_starter(mate, index)
    local t = M.SMN_STARTERS[index or 1]
    if t == nil then
        return nil, 'no Summoner starter'
    end

    if S.smn == nil or S.smn.slot ~= mate.slot then
        S.smn = nil -- (the section loads the mate's own settings first, then shows the starter beside them)
        S.smnStarterFor = { slot = mate.slot, starter = copyStarter(t) }
    else
        S.smn.starter = copyStarter(t)
    end

    S.smnOpen = true
    say(t.name .. ' starter opened in the Summoner section (not saved yet).')
    return true
end

-- the !gsq requests that put a starter on a mate as ONE change (server capability "smn1"): begin, the settings, every
-- rule (each checked when it arrives, nothing written), then the commit, which checks it all and only then replaces the
-- mate's settings and pact rules. A refused part changes nothing.
function M.smn_starter_requests(slot, starter)
    local e = starter.settings
    local out = { { 'smb', tostring(slot) },
                  { 'smbs', tostring(slot), tostring(e.avatar), e.engage and '1' or '0', tostring(e.rage), tostring(e.ward),
                    tostring(e.between), e.idle and '1' or '0', e.ruleSwitch and '1' or '0' } }
    for i, r in ipairs(starter.rules) do
        out[#out + 1] = { 'smbr', tostring(slot), tostring(i), r.on == false and '0' or '1', r.pact, r.target, r.cond,
                          r.cond == 'ALWAYS' and '0' or tostring(r.arg or ''), r.when, r.protect and '1' or '0' }
    end

    out[#out + 1] = { 'smbc', tostring(slot), tostring(#starter.rules) }
    return out
end

-- Save starter: the parts one after the other; the commit's answer is the mate's new state. On any refusal the open
-- save is dropped (smba) and the mate keeps what it had.
function M.smn_apply_starter(slot, starter)
    if M.busy() then
        return busy_say()
    end

    if not M.cap('smn1') then
        say('Saving a starter needs the updated server (it is saved as one change there).', false)
        return false
    end

    local list = M.smn_starter_requests(slot, starter)
    local function fail(i, why)
        read_request({ 'smba', tostring(slot) }, function() return true end, function() end)
        say(string.format('%s NOT saved: %s. Nothing was changed.', starter.name, M.readable(why or '?')), false)
    end

    local function step(i)
        local words = list[i]
        if i == #list then
            smn_request(words, slot, function()
                if S.smn then
                    S.smn.starter = nil
                end

                say(starter.name .. ' saved for this mate (server confirmed): its settings and ' .. #starter.rules .. ' pact rules.')
            end, starter.name .. ' NOT saved (nothing was changed)')
            return
        end

        read_request(words, function(items)
            local f = items[1]
            if f == nil or f[3] ~= 'smb' then
                return false, 'the answer was not readable'
            end

            step(i + 1)
            return true
        end, function(why) fail(i, why) end)
    end

    step(1)
    return true
end

function M.smn_dirty()
    local m = S.smn
    if not (m and m.data and m.edit) then
        return false
    end

    local d, e = m.data, m.edit
    return d.avatar ~= e.avatar or d.engage ~= e.engage or d.rage ~= e.rage or d.ward ~= e.ward or d.between ~= e.between
        or d.idle ~= e.idle or d.ruleSwitch ~= e.ruleSwitch
end

local function onoff(id, value, help)
    local v = combo(id, value and 1 or 0, { 1, 0 }, function(x) return x == 1 and 'On' or 'Off' end)
    tooltip(help or '')
    return v == 1
end

-- the fields of one pact rule (r is changed in place); pacts = the server's pact list
local function smn_rule_fields(r, pacts, idPrefix)
    local g = imgui()
    local labelW = s(150)
    local function label(text)
        label_text(text)
        g.SameLine(labelW)
    end

    local names, labels = {}, {}
    for _, p in ipairs(pacts or {}) do
        names[#names + 1] = p.name
        labels[p.name] = string.format('%s (%s %s, Lv%d)%s', M.pretty(p.name), M.pretty(p.avatar), p.kind, p.level, p.usable and '' or ' - not yet')
    end
    if #names == 0 then
        names = { r.pact }
    end

    label('Pact')
    width(s(260))
    r.pact = combo('##' .. idPrefix .. '-pact', r.pact, names, function(v) return labels[v] or M.pretty(v) end)
    label('Target')
    width(s(180))
    r.target = combo('##' .. idPrefix .. '-tgt', r.target, M.SMN_TARGETS, function(v) return M.SMN_TARGET_NAMES[v] end)
    label('When the target')
    width(s(180))
    r.cond = combo('##' .. idPrefix .. '-cond', r.cond, M.SMN_CONDS, function(v) return M.SMN_COND_NAMES[v] end)
    if r.cond ~= 'ALWAYS' then
        same_if_fits(s(140))
        width(s(130))
        r.arg = text_field('##' .. idPrefix .. '-arg', tostring(r.arg or ''), 24)
        tooltip((r.cond == 'NOT_STATUS' or r.cond == 'STATUS') and 'A status effect name, such as HASTE or PROTECT.' or 'A percentage, 0-100.')
    end
    label('Use it')
    width(s(180))
    r.when = combo('##' .. idPrefix .. '-when', r.when, M.SMN_WHENS, function(v) return M.SMN_WHEN_NAMES[v] end)
    label('Protect its MP')
    width(s(90))
    local p = combo('##' .. idPrefix .. '-prot', r.protect and 1 or 0, { 1, 0 }, function(x) return x == 1 and 'On' or 'Off' end)
    tooltip(M.SMN_HELP.protect)
    r.protect = p == 1
    label('Rule')
    width(s(90))
    local on = combo('##' .. idPrefix .. '-on', r.on ~= false and 1 or 0, { 1, 0 }, function(x) return x == 1 and 'On' or 'Off' end)
    tooltip('A rule that is off is kept but not used.')
    r.on = on == 1
end

-- (F13) the Summoner starter, open and not saved: its settings and rules can be changed here, then saved on the mate
function M.smn_starter_panel(mate, m)
    local g = imgui()
    local st = m.starter
    heading('Starter: ' .. st.name .. ' (not saved yet)')
    wrapped(M.theme.secondary, st.about)
    local e = st.settings
    local labelW = s(150)
    local function label(text)
        label_text(text)
        g.SameLine(labelW)
    end

    local function onoffS(id, value, help)
        local v = combo(id, value and 1 or 0, { 1, 0 }, function(x) return x == 1 and 'On' or 'Off' end)
        tooltip(help or '')
        return v == 1
    end

    label('Avatar')
    width(s(180))
    e.avatar = combo('##gsq-smst-av', e.avatar, { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 }, function(v) return M.SMN_AVATARS[v] end)
    tooltip(M.SMN_HELP.avatar)
    label('Normal attacks')
    width(s(90))
    e.engage = onoffS('##gsq-smst-eng', e.engage, M.SMN_HELP.engage)
    label('Rage')
    width(s(180))
    e.rage = combo('##gsq-smst-rage', e.rage, { 0, 1, 2 }, function(v) return M.SMN_MODES[v] end)
    tooltip(M.SMN_HELP.rage)
    label('Ward')
    width(s(180))
    e.ward = combo('##gsq-smst-ward', e.ward, { 0, 1, 2 }, function(v) return M.SMN_MODES[v] end)
    tooltip(M.SMN_HELP.ward)
    label('Between pulls')
    width(s(180))
    e.between = combo('##gsq-smst-btw', e.between, { 0, 1, 2 }, function(v) return M.SMN_BETWEEN[v] end)
    tooltip(M.SMN_HELP.between)
    label('Support out of combat')
    width(s(90))
    e.idle = onoffS('##gsq-smst-idle', e.idle, M.SMN_HELP.idle)
    label('Rules may switch')
    width(s(90))
    e.ruleSwitch = onoffS('##gsq-smst-sw', e.ruleSwitch, M.SMN_HELP.switch)

    g.Separator()
    heading('Starter pact rules (in order)')
    for i, r in ipairs(st.rules) do
        colored(r.on and M.theme.text or M.theme.secondary, string.format('%d. %s%s', i, r.on and '' or '(off) ', M.smn_rule_text(r)))
        same_if_fits(s(80))
        if button('Edit##gsq-smst-ed' .. i) then
            st.editing = i
        end
    end

    if st.editing and st.rules[st.editing] then
        g.Separator()
        heading('Starter rule ' .. st.editing)
        smn_rule_fields(st.rules[st.editing], m.pacts, 'gsq-smst-r')
        if button('Done##gsq-smst-done') then st.editing = nil end
    end

    g.Separator()
    with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                  { 'ImGuiCol_Text', M.theme.goText } }, function()
        if button('Save starter for ' .. mate.name .. '##gsq-smst-save') then
            M.smn_apply_starter(mate.slot, st)
        end
    end)
    local old = m.data and #m.data.rules or 0
    tooltip(string.format('Puts these settings and %d pact rules on %s%s. Rule Sets and their assignments are not changed.',
        #st.rules, mate.name, old > 0 and string.format(' (replacing its %d pact rule%s)', old, old == 1 and '' or 's') or ''))
    same_if_fits(s(80))
    if button('Discard starter##gsq-smst-drop') then m.starter = nil end
    tooltip('Close the starter without saving: ' .. mate.name .. ' keeps its own settings and rules.')
end

local function smn_panel(mate)
    local g = imgui()
    local m = S.smn
    if m == nil or m.slot ~= mate.slot then
        if not M.busy() then
            M.smn_load(mate.slot)
        end

        note('Loading...')
        return
    end

    if m.error == 'notsmn' then
        note(mate.name .. ' is not a Summoner now.')
        return
    elseif m.error then
        colored(M.theme.bad, 'Could not load them: ' .. M.readable(m.error))
        if button('Try again##gsq-smn-retry') then S.smn = nil end
        return
    end

    local d, e = m.data, m.edit
    if d == nil or e == nil then
        note('Loading...')
        return
    end

    if S.smnStarterFor and S.smnStarterFor.slot == mate.slot then
        m.starter, S.smnStarterFor = S.smnStarterFor.starter, nil
    end

    if not d.engine then
        wrapped(M.theme.gold, 'The map server here does not charge avatar upkeep yet (xi_map update needed); the rest works.')
    end

    if m.starter then
        return M.smn_starter_panel(mate, m)
    end

    if d.out then
        wrapped(M.theme.secondary, string.format('Now: %s%s. MP %s/%s.', d.current and M.pretty(d.current) or 'no avatar',
            d.intent and (', on its way to ' .. M.pretty(d.intent)) or '', tostring(d.mp or '?'), tostring(d.maxmp or '?')))
    else
        wrapped(M.theme.secondary, mate.name .. ' is not summoned: the settings and rules apply when called.')
    end

    local labelW = s(150)
    local function label(text)
        label_text(text)
        g.SameLine(labelW)
    end

    label('Avatar')
    width(s(180))
    e.avatar = combo('##gsq-smn-av', e.avatar, { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 }, function(v) return M.SMN_AVATARS[v] end)
    tooltip(M.SMN_HELP.avatar)
    label('Normal attacks')
    width(s(90))
    e.engage = onoff('##gsq-smn-eng', e.engage, M.SMN_HELP.engage)
    label('Rage')
    width(s(180))
    e.rage = combo('##gsq-smn-rage', e.rage, { 0, 1, 2 }, function(v) return M.SMN_MODES[v] end)
    tooltip(M.SMN_HELP.rage)
    label('Ward')
    width(s(180))
    e.ward = combo('##gsq-smn-ward', e.ward, { 0, 1, 2 }, function(v) return M.SMN_MODES[v] end)
    tooltip(M.SMN_HELP.ward)
    label('Between pulls')
    width(s(180))
    e.between = combo('##gsq-smn-btw', e.between, { 0, 1, 2 }, function(v) return M.SMN_BETWEEN[v] end)
    tooltip(M.SMN_HELP.between)
    label('Support out of combat')
    width(s(90))
    e.idle = onoff('##gsq-smn-idle', e.idle, M.SMN_HELP.idle)
    label('Rules may switch')
    width(s(90))
    e.ruleSwitch = onoff('##gsq-smn-sw', e.ruleSwitch, M.SMN_HELP.switch)

    local dirty = M.smn_dirty()
    with_colors({ { 'ImGuiCol_Button', M.theme.goGold }, { 'ImGuiCol_ButtonHovered', times(M.theme.goGold, 1.15) },
                  { 'ImGuiCol_Text', M.theme.goText } }, function()
        if button((dirty and 'Save settings *' or 'Save settings') .. '##gsq-smn-save') then
            M.smn_save_settings(mate.slot, e)
        end
    end)
    tooltip('Store these for ' .. mate.name .. ' (the server checks them). An out mate uses them at once.')

    g.Separator()
    heading('Pact rules (in order: the first one that fits is used)')
    if #d.rules == 0 then
        note('No pact rules: the job default (the settings above) decides.')
    end

    for i, r in ipairs(d.rules) do
        colored(r.on and M.theme.text or M.theme.secondary, string.format('%d. %s%s', i, r.on and '' or '(off) ', M.smn_rule_text(r)))
        same_if_fits(s(220))
        if button('Edit##gsq-smn-ed' .. i) then
            m.draft = { n = i, on = r.on, pact = r.pact, target = r.target, cond = r.cond, arg = r.arg, when = r.when, protect = r.protect }
        end
        g.SameLine(0, s(4))
        if i > 1 and button('Up##gsq-smn-up' .. i) then M.smn_move_rule(mate.slot, i, -1) end
        g.SameLine(0, s(4))
        if i < #d.rules and button('Down##gsq-smn-dn' .. i) then M.smn_move_rule(mate.slot, i, 1) end
        g.SameLine(0, s(4))
        if button('Delete##gsq-smn-del' .. i) then M.smn_delete_rule(mate.slot, i) end
    end

    local r = m.draft
    if r == nil then
        if #d.rules < 8 and button('New pact rule##gsq-smn-new') then
            m.draft = { n = #d.rules + 1, on = true, pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'COMBAT', protect = false }
        end
        same_if_fits(s(260))
        if #d.rules < 8 and button('Add example: Hastega when you lack Haste##gsq-smn-ex') then
            M.smn_save_rule(mate.slot, #d.rules + 1, M.smn_hastega_example())
        end
        tooltip('Garuda is called only if needed and affordable (summon + Hastega + upkeep while it waits); it is not used if you '
            .. 'get Haste from someone else first; only one Summoner goes for it; in a fight Garuda keeps attacking afterwards.')
        return
    end

    g.Separator()
    heading(r.n > #d.rules and 'New pact rule' or ('Rule ' .. r.n))
    local names, labels = {}, {}
    for _, p in ipairs(m.pacts or {}) do
        names[#names + 1] = p.name
        labels[p.name] = string.format('%s (%s %s, Lv%d)%s', M.pretty(p.name), M.pretty(p.avatar), p.kind, p.level, p.usable and '' or ' - not yet')
    end
    if #names == 0 then
        names = { r.pact }
    end

    label('Pact')
    width(s(260))
    r.pact = combo('##gsq-smn-pact', r.pact, names, function(v) return labels[v] or M.pretty(v) end)
    label('Target')
    width(s(180))
    r.target = combo('##gsq-smn-tgt', r.target, M.SMN_TARGETS, function(v) return M.SMN_TARGET_NAMES[v] end)
    label('When the target')
    width(s(180))
    r.cond = combo('##gsq-smn-cond', r.cond, M.SMN_CONDS, function(v) return M.SMN_COND_NAMES[v] end)
    if r.cond ~= 'ALWAYS' then
        same_if_fits(s(140))
        width(s(130))
        r.arg = text_field('##gsq-smn-arg', tostring(r.arg or ''), 24)
        tooltip((r.cond == 'NOT_STATUS' or r.cond == 'STATUS') and 'A status effect name, such as HASTE or PROTECT.' or 'A percentage, 0-100.')
    end
    label('Use it')
    width(s(180))
    r.when = combo('##gsq-smn-when', r.when, M.SMN_WHENS, function(v) return M.SMN_WHEN_NAMES[v] end)
    label('Protect its MP')
    width(s(90))
    r.protect = onoff('##gsq-smn-prot', r.protect, M.SMN_HELP.protect)
    label('Rule')
    width(s(90))
    r.on = onoff('##gsq-smn-on', r.on ~= false, 'A rule that is off is kept but not used.')

    if button('Save rule##gsq-smn-rsave') then
        if M.smn_save_rule(mate.slot, r.n, r) then
            m.draft = nil
        end
    end
    same_if_fits(s(80))
    if button('Cancel##gsq-smn-rcancel') then m.draft = nil end
end
M.smn_panel = smn_panel

local function smn_section(mate)
    if not M.cap('smn') or mate.job ~= 'SMN' then
        return
    end

    local g = imgui()
    g.Separator()
    local open = S.smnOpen == true
    if g.CollapsingHeader then
        if g.SetNextItemOpen then
            g.SetNextItemOpen(open)
        end

        open = g.CollapsingHeader('Summoner: ' .. mate.name .. '##gsq-smn-section') == true
    elseif button((open and '[-] ' or '[+] ') .. 'Summoner: ' .. mate.name .. '##gsq-smn-section') then
        open = not open
    end

    tooltip('How ' .. mate.name .. ' uses avatars and Blood Pacts: settings and pact rules, separate from Rule Sets.')
    S.smnOpen = open -- (for this session; not a saved setting, so the settings file stays as it was)

    if open then
        smn_panel(mate)
    else
        local m = S.smn
        if m and m.slot == mate.slot and m.data then
            wrapped(M.theme.secondary, string.format('Avatar: %s. %d pact rule%s.', M.SMN_AVATARS[m.data.avatar] or '?', #m.data.rules,
                #m.data.rules == 1 and '' or 's'))
        else
            wrapped(M.theme.secondary, 'Open to see and change ' .. mate.name .. '\'s avatar settings and pact rules.')
        end
    end
end
M.smn_section = smn_section

-- ---------------------------------------------------------------- (0.3.2) party roles (!gsq version 7: prl, prs)
-- Who the Rule Sets' Tank / Melee / Mage / Ranged targets (and a Bard's role songs) mean: the server's party roles
-- (!squad partyrole), NOT the Squad menu's Role. The server is the authority: a row shows only what an answer said, a
-- change is shown only once the server confirms it, and an older answer never overwrites a newer one (S.rolesGen).
M.ROLES_SERVER = 7
M.ROLE_NAMES   = { [0] = 'Auto', 'Tank', 'Melee', 'Mage', 'Ranged' }
M.ROLE_LETTER  = { 'T', 'M', 'C', 'R' }
M.LETTER_NAME  = { T = 'Tank', M = 'Melee', C = 'Mage', R = 'Ranged' }
M.ROLE_VALUES  = { 0, 1, 2, 3, 4 }
M.ROLES_HELP   = 'Gambits Party Roles: who the Tank, Melee, Mage (CASTER) and Ranged targets, and a Bard\'s role songs, '
    .. 'reach. Not the Squad menu\'s Squad Role (Auto / Tank / Damage / Healer / Support), which only filters default '
    .. 'job rules, never a Rule Set, and does not make a mate a Tank target.'
M.ROLES_AUTO_HELP = 'Auto = by main job. Some jobs count for more than one target: a PLD is Tank and Melee, a RUN is Tank, '
    .. 'Melee and Mage. Tank = PLD or RUN; Melee = WAR MNK THF PLD DRK BST SAM NIN DRG BLU PUP DNC RUN; Mage = WHM BLM RDM '
    .. 'BRD SMN BLU SCH GEO RUN; Ranged = RNG or COR.'
M.ROLES_UNSUPPORTED = 'Party roles need the server update (gambits_squad.lua version 7). Meanwhile: !squad partyrole '
    .. '<slot> <tank|melee|mage|ranged|auto>, then call the mate again.'

function M.roles_supported()
    return S.server ~= nil and S.server ~= false and (S.server.version or 0) >= M.ROLES_SERVER
end

-- "Tank, Melee" from "TM" ("none" for no letter)
function M.role_words(letters)
    local words = {}
    for c in string.gmatch(letters or '', '[TMCR]') do
        words[#words + 1] = M.LETTER_NAME[c]
    end

    return #words > 0 and table.concat(words, ', ') or 'none'
end

-- what a row counts as: an explicit role is exactly that target, auto is what its job gives
function M.role_effective(role, auto)
    return M.ROLE_LETTER[tonumber(role) or 0] or (auto or '')
end

-- the answer lines of prl / prs, checked strictly: nil and why for anything malformed (nothing half shown)
function M.parse_roles(items)
    local rows, byWho, party = {}, {}, {}
    for _, f in ipairs(items or {}) do
        if f[3] == 'pr' then
            local who, level, set = tonumber(f[4] or ''), tonumber(f[7] or ''), tonumber(f[8] or '')
            local live = f[11] == '-' and nil or tonumber(f[11] or '')
            if #f ~= 11 or who == nil or who < 0 or who ~= math.floor(who) or (f[5] or '') == '' or not string.match(f[6] or '', '^[%u%-]+$')
                or level == nil or set == nil or M.ROLE_NAMES[set] == nil or not string.match(f[9] or '', '^[TMCR]*$')
                or (f[10] ~= '0' and f[10] ~= '1') or (f[11] ~= '-' and (live == nil or M.ROLE_NAMES[live] == nil)) then
                return nil, 'a party role line was not readable'
            end

            if byWho[who] then
                return nil, 'a party role line came twice'
            end

            local row = { who = who, name = f[5], job = f[6], level = level, set = set, auto = f[9], out = f[10] == '1', live = live }
            byWho[who] = row
            rows[#rows + 1] = row
        elseif f[3] == 'pm' then
            if #f ~= 7 or (f[4] or '') == '' or not string.match(f[5] or '', '^[%u%-]+$') or (f[6] ~= 'p' and f[6] ~= 't')
                or not string.match(f[7] or '', '^[TMCR]*$') then
                return nil, 'a party member line was not readable'
            end

            party[#party + 1] = { name = f[4], job = f[5], kind = f[6], targets = f[7] }
        else
            return nil, 'the answer had an unexpected line'
        end
    end

    table.sort(rows, function(a, b) return a.who < b.who end)
    return { rows = rows, byWho = byWho, party = party }
end

-- loads the list (only when the section is open; one request at a time)
function M.roles_load()
    if not M.roles_supported() or M.busy() then
        return false
    end

    S.rolesGen = (S.rolesGen or 0) + 1
    local gen = S.rolesGen
    S.roles = S.roles or {}
    S.roles.loading, S.roles.error = gen, nil
    read_request({ 'prl' }, function(items)
        local data, why = M.parse_roles(items)
        if data == nil or data.byWho[0] == nil then
            return false, why or 'the answer had no line for you'
        end

        if gen ~= S.rolesGen then
            -- an older answer: a newer list request or a confirmed change came since; it must not overwrite them
            if S.roles and S.roles.loading == gen then
                S.roles.loading = nil
            end

            return true
        end

        S.roles = data
        return true
    end, function(why)
        if S.roles and S.roles.loading == gen then
            -- (no automatic retry every frame: "Update" or Refresh asks again; the summary says the update failed)
            S.roles.loading, S.roles.stale = nil, nil
            S.roles.error = why
        end
    end)
    return true
end

-- changes one role on the server: who 0 = you, else a squad slot. The row shows the change only when the server's answer
-- (read back) says so; on any failure it keeps what the server had.
function M.roles_set(who, role)
    if not M.roles_supported() then
        return false
    end

    if M.busy() then
        return busy_say()
    end

    role = tonumber(role)
    local r = S.roles
    local row = r and r.byWho and r.byWho[who]
    if row == nil or row.pending or role == nil or M.ROLE_NAMES[role] == nil or role ~= math.floor(role) then
        return false
    end

    S.rolesGen = (S.rolesGen or 0) + 1 -- (a list answer asked for before this change is older: it is not used)
    local token = {}
    row.pending = { role = role, token = token }
    local label = row.who == 0 and 'You' or row.name
    read_request({ 'prs', tostring(who), tostring(role) }, function(items)
        local data, why = M.parse_roles(items)
        if data == nil or #data.rows ~= 1 or data.rows[1].who ~= who or #data.party ~= 0 then
            return false, why or 'the answer was not for this change'
        end

        local cur = S.roles and S.roles.byWho and S.roles.byWho[who]
        if cur == nil or cur.pending == nil or cur.pending.token ~= token then
            return true -- (the list was loaded again meanwhile: that newer state stays)
        end

        local new = data.rows[1]
        for i, it in ipairs(S.roles.rows) do
            if it == cur then
                S.roles.rows[i] = new
            end
        end

        S.roles.byWho[who] = new
        if new.set ~= role then
            say(string.format('Party role NOT changed: the server still has %s as %s.', label, M.ROLE_NAMES[new.set]), false)
        else
            local what = role == 0 and ('Auto (' .. M.role_words(new.auto) .. ')') or M.ROLE_NAMES[role]
            say(string.format('%s: %s (server confirmed)%s', label, what, (new.out and new.live == new.set) and ', in effect now.'
                or ', from the next call.'))
        end

        return true
    end, function(why)
        local cur = S.roles and S.roles.byWho and S.roles.byWho[who]
        if cur and cur.pending and cur.pending.token == token then
            cur.pending = nil
        end

        say('Party role NOT changed: ' .. tostring(why) .. '. The list shows what the server has.', false)
    end)
    return true
end

-- the one-line summary: from EVERYONE the server reported in your party (your mates that are out, and the other members:
-- dualbox characters, other players, their trusts), never from your own list alone
function M.roles_summary(r)
    if not M.roles_supported() then
        return M.ROLES_UNSUPPORTED
    elseif r and r.error then
        -- (never counts from an older list once an update failed)
        return 'Party roles could not be loaded (' .. r.error .. '). Open this section and press Update to try again.'
    elseif r == nil or r.rows == nil then
        return 'Open this section to see who counts as Tank, Melee, Mage and Ranged in your party.'
    elseif r.stale then
        return 'Party roles: your squad changed since the last update. Open this section to update the list.'
    end

    local names = { T = {}, M = {}, C = {}, R = {} }
    local notOut = {}
    for _, row in ipairs(r.rows) do
        local label = row.who == 0 and 'You' or row.name
        if row.out then
            local letters = M.role_effective(row.live ~= nil and row.live or row.set, row.auto)
            for c in string.gmatch(letters, '[TMCR]') do
                table.insert(names[c], label .. ((row.live or row.set) ~= 0 and ' (set)' or ''))
            end
        else
            notOut[#notOut + 1] = string.format('%s (%s)', label, M.role_words(M.role_effective(row.set, row.auto)))
        end
    end

    for _, pm in ipairs(r.party or {}) do
        for c in string.gmatch(pm.targets, '[TMCR]') do
            table.insert(names[c], pm.name)
        end
    end

    local parts = {}
    for _, c in ipairs(M.ROLE_LETTER) do
        parts[#parts + 1] = M.LETTER_NAME[c] .. ': ' .. (#names[c] > 0 and table.concat(names[c], ', ') or 'nobody')
    end

    local text = 'In your party at the last update - ' .. table.concat(parts, '; ') .. '.'
    if #(r.party or {}) > 0 then
        text = text .. string.format(' (Includes %d member%s of other characters, read-only.)', #r.party, #r.party == 1 and '' or 's')
    end

    if #notOut > 0 then
        text = text .. ' Not summoned: ' .. table.concat(notOut, ', ') .. '.'
    end

    return text
end

local function role_status(row)
    if row.pending then
        note('saving...')
        tooltip('Waiting for the server to confirm the change.')
    elseif row.out and row.live == row.set then
        colored(M.theme.ok, 'in effect')
        tooltip('The server confirmed it; ' .. (row.who == 0 and 'your' or (row.name .. '\'s')) .. ' role is used from the next rule check.')
    elseif not row.out then
        note('applies when called')
        tooltip('Saved on the server; ' .. row.name .. ' gets it when called.')
    else
        colored(M.theme.gold, 'applies when called again')
        tooltip('Saved on the server, but ' .. row.name .. ' is out with another role: call it again (or use Assign & Apply).')
    end
end

local function role_row(row)
    local g = imgui()
    local who = row.who == 0 and ('You (' .. row.name .. ')') or row.name
    label_text(who)
    if row.who == 0 then
        tooltip('Your own role for your mates\' rules (e.g. Tank if you tank yourself).')
    end

    same_if_fits(s(120))
    note(string.format('%s %d%s', row.job, row.level, row.out and '' or '  (not summoned)'))
    same_if_fits(s(180))
    width(s(170))
    local disable = (row.pending ~= nil or M.busy()) and g.BeginDisabled ~= nil
    if disable then
        g.BeginDisabled(true)
    end

    local picked
    scoped(nil, function() if disable then g.EndDisabled() end end, function()
        picked = combo('##gsq-role-' .. row.who, row.set, M.ROLE_VALUES, function(v)
            if v == 0 then
                return 'Auto (' .. M.role_words(row.auto) .. ')'
            end

            return M.ROLE_NAMES[v] or '?'
        end, function(v)
            if v == 0 then
                return M.ROLES_AUTO_HELP
            end

            local others = string.gsub(row.auto or '', M.ROLE_LETTER[v] or '', '')
            return string.format('%s counts as %s only, whatever its job%s, for Rule Set targets and role songs. Kept until you '
                .. 'choose Auto, also when its job changes.', row.who == 0 and 'You' or row.name, M.ROLE_NAMES[v],
                others ~= '' and (': no longer ' .. M.role_words(others)) or '')
        end, function(v) return v == 0 and M.theme.secondary or nil end)
    end)
    tooltip(row.set == 0 and M.ROLES_AUTO_HELP or (M.ROLE_NAMES[row.set] .. ' was chosen for ' .. (row.who == 0 and 'you' or row.name)
        .. '. Choose Auto to follow the main job again.'))
    if picked ~= nil and picked ~= row.set and not row.pending and not disable then
        M.roles_set(row.who, picked)
    end

    same_if_fits(s(130))
    role_status(row)
    if row.set ~= 0 then
        same_if_fits(s(140))
        note('(by job: ' .. M.role_words(row.auto) .. ')')
    end
end

local function roles_section()
    local g = imgui()
    g.Separator()
    local open = S.rolesOpen == true
    local label = 'Party roles (who Tank / Melee / Mage / Ranged mean)##gsq-roles-section'
    if g.CollapsingHeader then
        if g.SetNextItemOpen then
            g.SetNextItemOpen(open)
        end

        open = g.CollapsingHeader(label) == true
    elseif button((open and '[-] ' or '[+] ') .. label) then
        open = not open
    end

    tooltip(M.ROLES_HELP .. ' Click to ' .. (open and 'close' or 'open') .. ' this section.')
    if open ~= (S.rolesOpen == true) then
        S.rolesOpen = open
        if api.set_pref then
            api.set_pref('roles_open', open)
        end
    end

    if not open then
        wrapped(M.theme.secondary, M.roles_summary(S.roles))
        return
    end

    if not M.roles_supported() then
        wrapped(M.theme.secondary, M.ROLES_UNSUPPORTED)
        return
    end

    local r = S.roles
    if r == nil or (r.stale and not r.loading) then
        M.roles_load()
        r = S.roles
    end

    if r == nil or r.rows == nil then
        if r and r.error then
            wrapped(M.theme.bad, 'Could not load the party roles: ' .. r.error)
            if button('Try again##gsq-roles-retry') then
                S.roles = nil
            end
        else
            note('(loading party roles...)')
        end

        return
    end

    wrapped(M.theme.secondary, M.roles_summary(r))
    tooltip('Counted as the engine sees it now: the role, else the main job. A Rule Set target also needs the member alive, '
        .. 'in the zone and in range.')
    for _, row in ipairs(r.rows) do
        g.PushID('gsq-role-row-' .. row.who)
        scoped(nil, function() g.PopID() end, function() role_row(row) end)
    end

    if #r.party > 0 then
        heading('Other party members (set on their own character)')
        tooltip('A dualbox character sets its own role with !squad partyrole me <role> on that character.')
        for _, pm in ipairs(r.party) do
            note(string.format('%s  %s  %s', pm.name, pm.job, M.role_words(pm.targets)))
        end
    end

    if r.error then
        wrapped(M.theme.bad, 'The last update failed: ' .. r.error)
    end

    if button('Update##gsq-roles-update') then
        S.roles.stale, S.roles.error = true, nil
    end

    tooltip('Ask the server again who counts as what (after calling or dismissing mates, or a role set in chat).')
end
M.roles_section = roles_section

-- (0.3.1) the right side: the editor and the Weapon Skills section scroll together; the Save bar stays below them
local function right_panel(mate)
    local d = S.draft
    local footerH = M.footer_height(d) -- (0.3.4: the bar's row, and its note line when it has one)
    local bodyH = math.max(s(140), available_h() - footerH)
    S.layout.bodyH = bodyH
    plain_child('##gsq-right-body', { 0, bodyH }, function()
        local afterList = editor_panel()
        ws_section(mate)
        smn_section(mate) -- (F13) a Summoner's avatar settings and pact rules
        roles_section() -- (0.3.2) the whole party, not only this mate
        local bottom = cursor_y()
        if afterList and bottom then
            -- what the editor needs below its rule list (next frame's limit): the largest seen while the same set, the
            -- same Weapon Skills state and the same panel height are shown; anything else starts measuring again
            local key = tostring(d) .. '|' .. tostring(S.wsOpen == true) .. '|' .. tostring(S.rolesOpen == true) .. '|'
                .. tostring(S.smnOpen == true) .. '|' .. tostring(math.floor(bodyH / row_h()))
            local measured = math.max(0, bottom - afterList)
            if S.layout.restKey ~= key then
                S.layout.restKey, S.layout.restH = key, measured
            else
                S.layout.restH = math.max(S.layout.restH or 0, measured)
            end
        end
    end)
    if footerH > 0 then
        save_bar(d)
    end
end

-- (0.3.5) the width of the Rule Set column in a body `total` pixels wide: where the player dragged the divider to
-- (S.leftW, at 100 %), else about 27 % of the window (220 to 300 px at 100 %). Never less than 200 px, and never so
-- much that the editor has less than 420 px. Returns the width, its limits and the divider's own width.
function M.split_width(total)
    local splitW = s(6)
    local minL = s(200)
    local maxL = math.max(minL, total - s(420) - splitW)
    local want = S.leftW and (S.leftW * s(1000) / 1000) or math.max(s(220), math.min(total * 0.27, s(300)))
    return math.floor(math.max(minL, math.min(maxL, want))), minL, maxL, splitW
end

-- (0.3.6) The height of the two panels. Usually what the window has left. When the window reaches below the bottom of
-- the game's screen (it was dragged down, or it is taller than the screen at a large Size), the panels end at the
-- screen's bottom instead: the status area and the Save buttons, which are the last thing in the right panel, stay
-- where they can be seen and clicked, and the rules above them scroll. Never less than 240 px (at 100 %): with a
-- window that is almost off the screen the buttons cannot be kept on it.
-- api.display_h: the height of the game's screen in pixels (Gambits.lua); nil when this ImGui cannot tell.
function M.panel_height(windowRoom, statusH)
    local h = windowRoom
    local screen = api.display_h and api.display_h() or nil
    local pos = U.cursor(imgui())
    if type(screen) == 'number' and screen > 0 and pos ~= nil then
        h = math.min(h, screen - pos[2] - (statusH or 0) - s(10))
    end

    return math.floor(math.max(s(240), h))
end

function M.draw()
    local g = imgui()
    if g == nil then
        return
    end

    if S.server == nil and not S.refreshing then
        S.refreshing = true
        M.refresh()
    end

    -- shown again after it was closed (or hidden behind another tab): what the mates run may have changed meanwhile
    local shownNow = now()
    if S.shownAt ~= nil and shownNow - S.shownAt > 1.5 then
        M.live_recheck()
    end

    S.shownAt = shownNow

    if S.server == false then
        heading('Squad Rule Sets')
        wrapped(nil, 'The Squad editor needs the server update with !gsq (gambits_squad.lua version ' .. M.MIN_SERVER .. ')'
            .. (S.serverWhy and (': ' .. S.serverWhy) or '') .. '.')
        if button('Try again##gsq-retry') then
            S.server = nil
            S.refreshing = false
        end

        return
    end

    -- the header: squad mate, Refresh, Ping, theme and size (controls move to a new line when the window is narrow)
    -- (0.3.5) the first row, right below the title bar, as in the Profile window: the mate as a list to pick another
    -- one from (its name; the open list says slot, jobs and whether it is summoned), then its jobs and levels
    width(s(150))
    local labels, names, jobsOf, slots = {}, {}, {}, {}
    for _, m in ipairs(S.mates) do
        jobsOf[m.slot] = string.format('%s %d%s', m.job, m.level, m.sub and (' / ' .. m.sub .. (m.subLevel and (' ' .. m.subLevel) or '')) or '')
        labels[m.slot] = string.format('%d  %s  %s%s', m.slot, m.name, jobsOf[m.slot], m.out and '' or '  (not summoned)')
        names[m.slot] = m.name
        slots[#slots + 1] = m.slot
    end

    local picked = combo('##gsq-mate', S.mateSlot, slots, function(v) return labels[v] or tostring(v) end, nil, nil,
        function(v) return names[v] or (v and tostring(v)) or '(none)' end)
    tooltip('The squad mate whose Rule Sets these are. Pick another one here.')
    if picked ~= S.mateSlot then
        M.switch_mate(picked) -- (beta polish: the new mate's own Rule Set, never the previous mate's; unsaved edits kept)
    end

    do
        local cur = M.mate()
        if cur then
            same(s(10))
            label_text(jobsOf[cur.slot] or '')
            if not cur.out then
                same(s(8))
                note('not summoned')
            end
        end
    end

    same_if_fits(s(70))
    if button('Refresh##gsq-refresh') then
        S.ws = nil -- (the Weapon Skills section loads again too)
        S.roles = nil -- (0.3.2: and the party roles, when their section is open)
        S.setCache, S.catCache = {}, {} -- (0.3.4: and everything kept from earlier answers)
        M.load_mates()
    end
    tooltip('Ask the server again for your squad and its Rule Sets.')
    -- (0.3.4) the rarely used controls (Ping, Theme, Size) are behind Options, as in the Squads menu
    same_if_fits(s(70))
    if button((S.showOptions and 'Options <' or 'Options >') .. '##gsq-options') then S.showOptions = not S.showOptions end
    tooltip('Theme, size and the connection test.')
    if S.showOptions then
    same_if_fits(s(50))
    if button('Ping##gsq-ping') then M.ping(10) end
    tooltip('Measure 10 round trips to the server (and whether the game refused any line).')
    same_if_fits(s(170))
    label_text('Theme')
    same()
    width(s(110))
    local theme = combo('##gsq-theme', M.themeName, M.THEME_ORDER, function(v) return M.THEME_NAMES[v] or v end)
    if theme ~= M.themeName then
        M.set_theme(theme)
        if api.on_theme then
            api.on_theme(theme)
        end
    end
    tooltip('The colours of this window and of the Squads menu, the Profile and the Spells window, for this character.')
    end

    if S.showOptions and api.get_scale and api.set_scale then
        local scale = api.get_scale()
        same_if_fits(s(150))
        label_text('Size')
        same()
        if button('-##gsq-scale-down') and scale > 70 then api.set_scale(scale - 10) end
        tooltip('Smaller text and controls (70-200 %).')
        same(s(4))
        if button(string.format('%d%%##gsq-scale-reset', scale)) then api.set_scale(100) end
        tooltip('Back to 100 %.')
        same(s(4))
        if button('+##gsq-scale-up') and scale < 200 then api.set_scale(scale + 10) end
        tooltip('Larger text and controls (70-200 %).')
    end

    -- the two panels take the room that is left; (0.3.1) a status area (about three lines, wrapped, never cut) only while
    -- there is something to say
    local mate = M.mate()
    local statusH = (S.progress or S.message) and s(58) or s(6)
    if mate == nil then
        wrapped(M.theme.secondary, #S.mates == 0 and 'No squad mates yet. Make one with !squad new <name> <job>.' or 'Loading your squad...')
    else
        local total = available()
        local panelH = M.panel_height(available_h() - statusH, statusH)
        -- (0.3.5) the Rule Set column is narrower (about a quarter of the window; 0.3.4: 36 %), so the rule editor has
        -- the room, and the line between the two can be dragged. Its place is kept while the add-on is loaded.
        local leftW, minL, maxL, splitW = M.split_width(total)
        local st = U.states(M.theme)
        with_colors({ { 'ImGuiCol_Border', M.theme.border } }, function()
            child('##gsq-left', { leftW, panelH }, function() sets_panel(mate, panelH) end)
            g.SameLine(0, 0)
            local newW = U.splitter(g, '##gsq-split', splitW, panelH, leftW, minL, maxL,
                { { 'ImGuiCol_Button', { 0, 0, 0, 0 } }, { 'ImGuiCol_ButtonHovered', st.hover }, { 'ImGuiCol_ButtonActive', st.rowFill } })
            tooltip('Drag to make the Rule Set list wider or narrower.')
            if newW ~= leftW then
                S.leftW = newW / (s(1000) / 1000) -- (kept at 100 %: it follows the Size setting)
            end

            g.SameLine(0, 0)
            -- (0.3.1) one editor: the Rule Set, then Weapon Skills as a collapsible section (no tabs), Save always visible
            child('##gsq-right', { 0, panelH }, function() right_panel(mate) end)
        end)
    end

    if S.progress then
        wrapped(M.theme.secondary, S.progress)
    elseif S.message then
        if button('x##gsq-dismiss') then
            S.message = nil
        else
            tooltip('Hide this message.')
            same()
            wrapped(S.messageWarn and M.theme.gold or (S.messageOk and M.theme.ok or M.theme.bad), M.readable(S.message))
        end
    end
end
return M
