-- Gambits v2 on XI: Forever Offline v0.1.48: the integration of our server changes with v0.1.48's squad.lua
-- (camp/pulling, links, spacing, skillchain wait, bard songs, the !squad error wrapper and the print filter).
--   luajit test_squad_upstream_integration.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                     <server>/scripts/enum/job_ability.lua <v0.1.48 squad.lua, unchanged> <work folder>
--                                     [a COPY of a squad_rulesets_data.lua to load]
-- Lua 5.4 needs  -e "unpack = unpack or table.unpack"  (v0.1.48's wrapper uses the LuaJIT global; the server runs LuaJIT).
-- Nothing is written: the work folder is only read for the optional data copy.
local LUA, GAMBITS, JA_ENUM, ORIGINAL, WORK, DATAFILE = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA and GAMBITS and JA_ENUM and ORIGINAL, 'usage: test_squad_upstream_integration.lua <lua folder> gambits.lua job_ability.lua original-squad.lua <work> [data copy]')
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function readAll(path) local f = assert(io.open(path, 'rb')) local s = f:read('*a') f:close() return s end
local function has(text, needle) return text:find(needle, 1, true) ~= nil end

-- ---------------------------------------------------------------- captured print (installed before squad.lua wraps it)
local LOG = {}
print = function(...)
    local parts = {}
    for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end
    LOG[#LOG + 1] = table.concat(parts, '\t')
end
local function logHas(needle) for _, l in ipairs(LOG) do if has(l, needle) then return true end end return false end

-- ---------------------------------------------------------------- the server bits squad.lua needs (as test_squad_rulesets.lua)
dofile(GAMBITS)
local function registry(first, fixed, missing)
    local byId, nextId, t = {}, first, {}
    for name, id in pairs(fixed or {}) do t[name] = id; byId[id] = name end
    return setmetatable(t, { __index = function(self, name)
        if type(name) ~= 'string' or (missing and missing[name]) then return nil end
        local id = nextId
        nextId = nextId + 1
        rawset(self, name, id)
        byId[id] = name
        return id
    end }), byId
end
local spellIds = registry(1, nil, { NOT_A_SPELL = true })
local familyIds, familyName = registry(1, { NONE = 0 })
xi = { module = { registerCommand = function() end }, objType = { PC = 1, TRUST = 2, MOB = 3 },
       animation = { NONE = 0, ATTACK = 1, HEALING = 33 }, settings = { map = { EXP_RATE = 1 } } }
setmetatable(xi, { __index = function(t, k) local v = setmetatable({}, { __index = function() return 0 end }) rawset(t, k, v) return v end })
xi.mobMod = { TRUST_DISTANCE = 77 }
xi.trust = { movementType = { NO_MOVE = -1, NON_COMBAT = -2, MELEE = 0, MID_RANGE = 6, LONG_RANGE = 12 } }
xi.magic = { spellFamily = familyIds, spell = spellIds }
rawset(xi, 'jobAbility', nil)
dofile(JA_ENUM)
SquadOwnerMerit = function(owner, meritId) return (type(owner) == 'table' and owner.merits and owner.merits[meritId]) or 0 end
local effectIds, effectName = registry(1)
xi.effect = effectIds
xi.effectFlag = { ERASABLE = 1 }
xi.ecosystem = { UNDEAD = 19, VERMIN = 20 }
Module = { new = function() return { addOverride = function() end } end }
package.preload['modules/module_utils'] = function() return true end
package.preload['modules/custom/lua/squad_starter_gear'] = function() return dofile(LUA .. '/squad_starter_gear.lua') end
local W = { squad = {} }
GetSquad = function() return W.squad end
SetSquadEquip, UnlockSquadItem = function() end, function() end
GetSquadItemInfo = function() return { valid = false } end
BuildStarterGear = function() return {} end
GetSquadUnlocks = function() return {} end
local DATA = nil
package.preload['modules/custom/lua/squad_rulesets_data'] = function()
    if DATA == nil then error("module 'modules/custom/lua/squad_rulesets_data' not found") end
    return DATA
end
package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA .. '/squad_ja_jobs_data.lua') end

local WAR, WHM, BRD = 1, 3, 10
local nextEntityId = 100
local function entity(kind, opts)
    nextEntityId = nextEntityId + 1
    local e = { kind = kind, vars = {}, level = opts.level or 1, id = opts.id or nextEntityId, printed = {}, mobMods = {}, gambits = {},
                pos = opts.pos or { x = 0, y = 0, z = 0 }, tp = opts.tp or 0, tpSettings = {} }
    function e:getObjType() return self.kind end
    function e:getLocalVar(k) return self.vars[k] or 0 end
    function e:setLocalVar(k, v) self.vars[k] = v end
    function e:getMainLvl() return self.level end
    function e:getMainJob() return opts.job or 1 end
    function e:getSubJob() return opts.sub or 0 end
    function e:getSubLvl() return opts.subLevel or 0 end
    function e:getID() return self.id end
    function e:getName() return opts.name or 'Tester' end
    function e:getPacketName() return opts.name or 'Tester' end
    function e:getMaster() return self.master end
    function e:printToPlayer(text) self.printed[#self.printed + 1] = text end
    function e:isAlive() return true end
    function e:isEngaged() return self.engagedWith ~= nil end
    function e:getTarget() return self.engagedWith end
    function e:getPos() return self.pos end
    function e:getTP() return self.tp end
    function e:getMobMod(id) return self.mobMods[id] or 0 end
    function e:setMobMod(id, v) self.mobMods[id] = v end
    function e:setTrustTPSkillSettings(a, b, c) self.tpSettings[#self.tpSettings + 1] = { a, b, c } end
    function e:addGambit(target, condition, action, retry)
        self.gambits[#self.gambits + 1] = { target = target, condition = condition, action = action, retry = retry }
    end
    function e:setAutoAttackEnabled(on) self.autoAttack = on end
    return setmetatable(e, { __index = function() return function() return 0 end end })
end
local function player()
    local p = entity(xi.objType.PC, { level = 75, id = 4, name = 'Testcharone' })
    p.party = {}
    function p:getCharVar(k) return self.vars[k] or 0 end
    function p:setCharVar(k, v) self.vars[k] = v end
    function p:getPartyWithTrusts() return self.party end
    function p:getZoneID() return 116 end
    return p
end
local function spawnWith(H, master, mateId, job, level, sub, subLevel, party)
    local t = entity(xi.objType.TRUST, { level = level or 30, job = job, sub = sub, subLevel = subLevel, name = 'Mate' .. mateId })
    t.master = master
    t:setLocalVar('SQUAD_ID', mateId)
    if party then master.party = party(t) end
    H.squadSpawn(t)
    return t
end
local function serialize(v)
    if type(v) ~= 'table' then return tostring(v) end
    local parts = {}
    for i = 1, #v do parts[#parts + 1] = serialize(v[i]) end
    return '{' .. table.concat(parts, ',') .. '}'
end
local function list(t)
    local out = {}
    for _, g in ipairs(t.gambits) do out[#out + 1] = string.format('%s|%s|%s|%s', tostring(g.target), serialize(g.condition), serialize(g.action), tostring(g.retry)) end
    return table.concat(out, '\n')
end
local function families(t)
    local out = {}
    for _, g in ipairs(t.gambits) do
        if g.action[1] == ai.r.MA and g.action[2] == ai.s.HIGHEST and familyName[g.action[3]] then out[familyName[g.action[3]]] = true end
    end
    return out
end

-- ---------------------------------------------------------------- load v0.1.48 (unchanged) and the integrated squad.lua
__SQUAD_TEST = {}
assert(loadfile(ORIGINAL))()
local HO = __SQUAD_TEST.hooks
__SQUAD_TEST = {}
assert(loadfile(LUA .. '/squad.lua'))()
local H = __SQUAD_TEST.hooks
assert(H and H.squadSpawn and H.commandObj, 'integrated squad.lua without test hooks')
dofile(LUA .. '/squad_space.lua')
dofile(LUA .. '/squad_chain.lua')
local RS = require('modules/custom/lua/squad_rulesets')
local cmd = H.commandObj
local function store(sets) return { format = 'xifo-ruleset-store', version = 1, sets = sets } end
local function choose(p, mateId, jobId, num, id)
    p.vars['SQUAD_RS_' .. mateId .. '_' .. jobId] = num
    p.vars['SQUAD_RSH_' .. mateId .. '_' .. jobId] = num and RS.idHash(id) or nil
end

-- ================================================================= 1. the Gambits v2 hooks survived the integration
section('Gambits v2 hooks in the integrated source')
local SQ = readAll(LUA .. '/squad.lua')
check(has(SQ, 'xi.squad.levelsFor = levelsFor') and type(xi.squad.levelsFor) == 'function', 'levelsFor is exported (xi.squad.levelsFor)')
check(has(SQ, "if action == 'ruleset' or action == 'rulesets' then"), '!squad ruleset command branch is present')
check(has(SQ, 'abilityRules.allowGambit(mob, action[3])'), 'the U13 job ability gate in addGambit is present')
check(has(SQ, 'rulesets.forMob(mob)') and has(SQ, 'applyRules(mob, customSet.rules, false)'), 'the Rule Set branch in squadSpawn is present')
check(has(SQ, 'squadTeamTick(mobArg)') and has(SQ, 'SQUAD_PRINT_RAW') and has(SQ, "addListener('DEATH', 'SQUAD_DEATH_RETURN'"),
      'and v0.1.48\'s own additions are intact (team tick, print filter, death return)')
local INIT = readAll(LUA .. '/../../init.txt')
local iSquad, iGsq = INIT:find('custom/lua/squad.lua', 1, true), INIT:find('custom/lua/gambits_squad.lua', 1, true)
check(iSquad ~= nil and iGsq ~= nil and iGsq > iSquad, 'init.txt registers custom/lua/gambits_squad.lua after custom/lua/squad.lua')
check(has(INIT, 'custom/lua/squad_space.lua') and has(INIT, 'custom/lua/squad_chain.lua'), 'init.txt keeps v0.1.48\'s squad_space and squad_chain')
local CPP = readAll(LUA .. '/../cpp/squad.cpp')
check(has(CPP, 'SquadOwnerMerit') and has(CPP, 'squadMateMayUse'), 'squad.cpp has SquadOwnerMerit and the trySquadAbility check (U13)')
-- (D9, 2026-11-20) since 453366ef (v0.1.49) the ranged copy takes real shooting or throwing weapons only (not a bard's instrument)
check(has(CPP, 'skillType == xi::SkillType::Archery || skillType == xi::SkillType::Marksmanship || skillType == xi::SkillType::Throwing'),
      'squad.cpp copies the ranged weapon of real shooting or throwing weapons only')
local GSQ = readAll(LUA .. '/gambits_squad.lua')
check(GSQ:match('local VERSION%s*=%s*12%s') ~= nil, 'gambits_squad.lua is protocol v12 (capability words, live state; enemy family and counts; the long rule form)')

-- ================================================================= 2. default behaviour without a Rule Set = v0.1.48
section('default job behaviour without a Rule Set (v0.1.48 bard songs by party)')
local function partyOf(kinds)
    return function(self)
        local out = { self }
        for i, job in ipairs(kinds) do out[#out + 1] = entity(xi.objType.TRUST, { job = job, id = 900 + i }) end
        return out
    end
end
local kinds = {
    caster   = { { 3, 4, 4 }, { 'MAGES_BALLAD', 'VALOR_MINUET' } },
    nohealer = { { 1, 2 },    { 'KNIGHTS_MINNE', 'ARMYS_PAEON' } },
    melee    = { { 1, 3, 2 }, { 'VALOR_MINUET', 'MARCH' } },
}
W.squad = { { id = 21, slot = 1, name = 'Lyra', mjob = BRD, sjob = 0, jobs = {} } }
-- squadBardParty only looks at a real (userdata) master; LuaJIT's newproxy gives one that forwards to the mock
local newproxy = rawget(_G, 'newproxy')
local function asUserdata(tbl)
    if newproxy == nil then return tbl end
    local u = newproxy(true)
    getmetatable(u).__index = function(_, key)
        local v = tbl[key]
        if type(v) ~= 'function' then return v end
        return function(_, ...) return v(tbl, ...) end
    end
    return u
end
local function spawnBrd(Hx, level, partyKinds)
    local p = player()
    local t = entity(xi.objType.TRUST, { level = level, job = BRD, name = 'Lyra' })
    t.master = asUserdata(p)
    t:setLocalVar('SQUAD_ID', 21)
    p.party = partyOf(partyKinds)(t)
    Hx.squadSpawn(t)
    return t
end
for name, k in pairs(kinds) do
    local new = spawnBrd(H, 40, k[1])
    local old = spawnBrd(HO, 40, k[1])
    check(list(new) == list(old) and #new.gambits > 0, name .. ' party: the BRD gambits are exactly v0.1.48\'s (' .. #new.gambits .. ')')
    local f = families(new)
    if newproxy ~= nil then
        check(f[k[2][1]] and f[k[2][2]] and f.ELEGY and f.FOE_REQUIEM,
              name .. ' party: ' .. k[2][1] .. ' + ' .. k[2][2] .. ', Elegy and Requiem on the monster')
    else
        check(f.VALOR_MINUET and f.MARCH and f.ELEGY and f.FOE_REQUIEM,
              name .. ' party (no userdata in this Lua: the melee list): Minuet + March, Elegy, Requiem')
    end
end
if newproxy == nil then io.write('  (Lua 5.4 has no newproxy: the per-party song choice is covered by the LuaJIT run)\n') end
local lowBrd = spawnWith(H, player(), 21, BRD, 20, nil, nil, partyOf({ 3, 4 }))
check(not families(lowBrd).MAGES_BALLAD and not families(lowBrd).ELEGY, 'a level 20 BRD skips Ballad (25) and Elegy (39) as in v0.1.48')

-- ================================================================= 3. a Rule Set with v0.1.48 squad behaviour
section('a custom Rule Set replaces the v0.1.48 bard songs')
local brdSet = { format = 'xifo-ruleset', version = 1, num = 1, id = 'custom.brd.test', name = 'BRD test', job = 'BRD',
                 rules = { { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, action = { 'family', 'MAGES_BALLAD' } } } }
DATA = store({ brdSet })
local pr = player()
choose(pr, 21, BRD, 1, 'custom.brd.test')
local withSet = spawnWith(H, pr, 21, BRD, 40, nil, nil, partyOf({ 1, 2 }))
check(#withSet.gambits == 1 and familyName[withSet.gambits[1].action[3]] == 'MAGES_BALLAD',
      'BRD with a set: exactly the set\'s one rule, no party songs, no Elegy/Requiem (' .. #withSet.gambits .. ')')
check(withSet.mobMods[77] == xi.trust.movementType.MID_RANGE, 'the BRD stance still runs with a set (mid range)')

section('call, dismiss and call again (reapply): the same rules every time')
local again = spawnWith(H, pr, 21, BRD, 40, nil, nil, partyOf({ 1, 2 }))
check(list(again) == list(withSet), 'calling the mate again gives the same Rule Set gambits')
choose(pr, 21, BRD, nil)
local off = spawnWith(H, pr, 21, BRD, 40, nil, nil, partyOf({ 1, 2 }))
local plain = spawnWith(HO, player(), 21, BRD, 40, nil, nil, partyOf({ 1, 2 }))
check(list(off) == list(plain), 'choice cleared: the next call is v0.1.48\'s default bard again')
choose(pr, 21, BRD, 1, 'custom.brd.test')
check(list(spawnWith(H, pr, 21, BRD, 40, nil, nil, partyOf({ 1, 2 }))) == list(withSet), 'and chosen again: the set again')
DATA = nil
check(list(spawnWith(H, pr, 21, BRD, 40, nil, nil, partyOf({ 1, 2 }))) == list(plain), 'no data file: the default bard (fall back)')

section('U13 with v0.1.48: the job ability gate still applies to Rule Sets')
local whmSet = { format = 'xifo-ruleset', version = 1, num = 1, id = 'custom.whm.u13', name = 'WHM U13', job = 'WHM',
                 rules = { { id = 'r1', on = true, target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', 'BERSERK' } },
                           { id = 'r2', on = true, target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', 'DIVINE_SEAL' } } } }
DATA = store({ whmSet })
W.squad = { { id = 1, slot = 1, name = 'Mira', mjob = WHM, sjob = WAR, jobs = {} } }
local pw = player()
choose(pw, 1, WHM, 1, 'custom.whm.u13')
local mira = spawnWith(H, pw, 1, WHM, 25, WAR, 12, function(self) return { self } end)
local jas = {}
for _, g in ipairs(mira.gambits) do if g.action[1] == ai.r.JA then jas[g.action[3]] = true end end
check(not jas[xi.ja.BERSERK] and jas[xi.ja.DIVINE_SEAL], 'WHM25/WAR12 with a set: Berserk (WAR 15) left out, Divine Seal kept')
check(logHas('BERSERK'), 'and the reason is logged: ' .. tostring(LOG[#LOG]))

-- ================================================================= 4. v0.1.48's spacing and skillchain wait with a Rule Set
section('spacing (squad_space) and the skillchain wait (squad_chain) with a Rule Set')
local foe = entity(xi.objType.MOB, { name = 'Crawler', pos = { x = 0, y = 0, z = 0 } })
local function tick(m) m:setLocalVar('SQUAD_TEAM_T', 0); squadTeamTick(m) end
choose(pw, 1, WHM, 1, 'custom.whm.u13')
mira = spawnWith(H, pw, 1, WHM, 25, WAR, 12, function(self) return { self } end)
local before = list(mira)
foe.engagedWith = mira
mira.engagedWith, mira.pos = foe, { x = 3, y = 0, z = 0 }
tick(mira)
check(mira.mobMods[77] == 15 and mira:getLocalVar('SQUAD_SP_D') == 15, 'a Rule Set WHM in a fight is held at 15 yalms (v0.1.48 spacing)')
check(list(mira) == before, 'the spacing tick does not touch the Rule Set gambits')
pw.vars['SQUAD_RANGE_1'] = 1
local mira2 = spawnWith(H, pw, 1, WHM, 25, WAR, 12, function(self) return { self } end)
mira2.engagedWith = foe
local keep = mira2.mobMods[77]
tick(mira2)
check(mira2.mobMods[77] == keep, 'a range you set (!squad range) still wins over the spacing')
pw.vars['SQUAD_RANGE_1'] = nil
mira.engagedWith = nil
tick(mira)
check(mira:getLocalVar('SQUAD_SP_D') == 0, 'out of the fight the spacing lets go')

local opener = entity(xi.objType.TRUST, { job = WAR, level = 40, tp = 1200 })
local closer = entity(xi.objType.TRUST, { job = WAR, level = 40, tp = 300 })
local boss = player()
boss.party = { opener, closer }
opener.master, closer.master = boss, boss
opener:setLocalVar('SQUAD_SC_ROLE', 1); closer:setLocalVar('SQUAD_SC_ROLE', 2)
opener.engagedWith = foe
tick(opener)
local last = opener.tpSettings[#opener.tpSettings]
check(last and last[1] == ai.tp.CLOSER_UNTIL_TP and last[3] == 3000, 'the opener holds its TP while no closer has 1000')
closer.tp = 1000
tick(opener)
last = opener.tpSettings[#opener.tpSettings]
check(last and last[1] == ai.tp.OPENER and last[3] == 1000, 'and opens once a closer has 1000 TP')

-- (Gambits WAR/PLD/RDM/WS batch) Custom weapon skill mates and the automatic roles / the skillchain wait
section('Gambits weapon skill settings with the automatic roles (skillchainRoles) and the skillchain wait (squad_chain)')
package.preload['modules/custom/lua/squad_ws'] = function() return dofile(LUA .. '/squad_ws.lua') end
local WS = require('modules/custom/lua/squad_ws')
local opener2 = entity(xi.objType.TRUST, { job = WAR, level = 40, tp = 1200 })
local custom = entity(xi.objType.TRUST, { job = WAR, level = 40, tp = 300 })
local boss2 = player()
boss2.party = { opener2, custom }
opener2.master, custom.master = boss2, boss2
opener2:setLocalVar('SQUAD_ID', 31); custom:setLocalVar('SQUAD_ID', 32)
-- a Custom Close mate (as squad_ws.lua puts it on the mate)
custom:setLocalVar('SQUAD_WSC', 7); custom:setLocalVar('SQUAD_WSC_CLOSE_TP', 1000); custom:setLocalVar('SQUAD_SC_ROLE', 1002)
H.skillchainRoles(boss2)
check(custom:getLocalVar('SQUAD_SC_ROLE') == 1002 and #custom.tpSettings == 0, 'the automatic roles leave a Custom mate alone (role and trigger kept)')
check(opener2:getLocalVar('SQUAD_SC_ROLE') == 1, 'a lone default melee mate becomes the opener when a Custom mate closes (not "alone")')
custom:setLocalVar('SQUAD_WSC_CLOSE_TP', 0) -- (a Custom Open mate does not close)
opener2:setLocalVar('SQUAD_SC_ROLE', 0)
H.skillchainRoles(boss2)
check(opener2:getLocalVar('SQUAD_SC_ROLE') == 3, 'with only a Custom Open mate it stays "alone", as before')
custom:setLocalVar('SQUAD_WSC_CLOSE_TP', 1000)
opener2:setLocalVar('SQUAD_SC_ROLE', 1); opener2:setLocalVar('SQUAD_CH_MODE', 0)
opener2.engagedWith = foe
tick(opener2)
last = opener2.tpSettings[#opener2.tpSettings]
check(last and last[1] == ai.tp.CLOSER_UNTIL_TP and last[3] == 3000, 'the default opener holds while the Custom closer has no TP')
custom.tp = 1000
tick(opener2)
last = opener2.tpSettings[#opener2.tpSettings]
check(last and last[1] == ai.tp.OPENER, 'and opens for the Custom Close mate once it has 1000 TP (a recognised closer)')
custom:setLocalVar('SQUAD_WSC_CLOSE_TP', 2000) -- an Independent mate counts from its own threshold
opener2:setLocalVar('SQUAD_CH_MODE', 0)
tick(opener2)
last = opener2.tpSettings[#opener2.tpSettings]
check(last and last[1] == ai.tp.CLOSER_UNTIL_TP, 'an Independent mate (threshold 2000) with 1000 TP is not ready yet: the opener holds')
-- legacy and no setting: untouched
local legacyMate = entity(xi.objType.TRUST, { job = WAR, level = 40 })
legacyMate.master = boss2; legacyMate:setLocalVar('SQUAD_ID', 33); legacyMate:setLocalVar('SQUAD_WSTP', 1500)
boss2.party = { legacyMate }
H.skillchainRoles(boss2)
last = legacyMate.tpSettings[#legacyMate.tpSettings]
check(legacyMate:getLocalVar('SQUAD_SC_ROLE') == 115 and last[1] == ai.tp.CLOSER_UNTIL_TP and last[3] == 1500, '!squad ws (1500 TP) works exactly as before')
-- the call: squad_ws.onSpawn after the !squad ws timing
local pws = player()
pws.vars['SQUAD_WSC_32_1'] = WS.encode({ control = 1, mode = 1, tp = 1500, ws = 0 })
local called = entity(xi.objType.TRUST, { job = WAR, level = 40 })
called:setLocalVar('SQUAD_ID', 32)
WS.onSpawn(pws, called, { id = 32, mjob = WAR })
check(WS.engineReady() == false and called:getLocalVar('SQUAD_WSC') == 0, 'squad_ws on a server without the batch\'s xi_map: no Custom trigger (Squad default)')
SquadApplyWeaponSkills = function() return true end
WS.onSpawn(pws, called, { id = 32, mjob = WAR })
last = called.tpSettings[#called.tpSettings]
check(last and last[1] == ai.tp.OPEN_AT_TP and last[3] == 1500 and called:getLocalVar('SQUAD_SC_ROLE') == 1001, 'with it: Custom Open at 1500 is on the mate')
SquadApplyWeaponSkills = nil
-- the job ability argument of JA_ON_COOLDOWN
local jc = H.ruleCondition({ 'JA_ON_COOLDOWN', 'PROVOKE' }, false)
check(jc and jc[1] == ai.c.JA_ON_COOLDOWN and jc[2] == xi.ja.PROVOKE, 'JA_ON_COOLDOWN PROVOKE becomes the engine\'s { 37, Provoke id }')
check(H.ruleCondition({ 'JA_ON_COOLDOWN', 'NOT_AN_ABILITY' }, false) == nil, 'an unknown job ability: the rule is skipped (logged), never a 0 id')
check(H.ruleCondition({ 'HAS_MP_MPP_LT', 50 }, false)[1] == ai.c.HAS_MP_MPP_LT, 'HAS_MP_MPP_LT 50 is passed as it is')
-- (0.3.3, Bard song tiers) STATUS / NOT_STATUS { effect, tier } -> effect id + tier * 65536, only with the tier map server
do
    rawset(xi.effect, 'REQUIEM', 192); rawset(xi.effect, 'MARCH', 214); rawset(xi.effect, 'NOCTURNE', 223); rawset(xi.effect, 'HASTE', 33)
    SquadStatusTierEngine = function() return 1 end
    local tc = H.ruleCondition({ 'NOT_STATUS', { effect = 'MARCH', tier = 2 } }, false)
    check(tc and tc[1] == ai.c.NOT_STATUS and tc[2] == 214 + 2 * 65536, 'NOT_STATUS { MARCH, 2 } -> { 10, 214 + 2 * 65536 } (Victory March)')
    local sc = H.ruleCondition({ 'STATUS', { effect = 'MARCH', tier = 1 } }, false)
    check(sc and sc[1] == ai.c.STATUS and sc[2] == 214 + 65536, 'STATUS { MARCH, 1 } -> Advancing March')
    local pc2 = H.ruleCondition({ 'NOT_STATUS', 'MARCH' }, false)
    check(pc2 and pc2[2] == 214, 'a plain NOT_STATUS MARCH: the effect id alone, as before (any March)')
    check(H.ruleCondition({ 'NOT_STATUS', { effect = 'HASTE', tier = 1 } }, false) == nil, 'a tier on Haste: the rule is skipped (logged)')
    SquadStatusTierEngine = nil
    local skipped = H.ruleCondition({ 'NOT_STATUS', { effect = 'MARCH', tier = 2 } }, false)
    check(skipped == nil, 'without the tier map server: skipped, never sent as "any March"')
    check(logHas('NOT_STATUS with a song tier needs a song effect'), 'and logged: ' .. tostring(LOG[#LOG]))
end
check(has(SQ, 'wsSettings.spawnWs(player, mate)') and has(SQ, 'pcall(wsSettings.onSpawn, player, trust, mate)') and has(SQ, 'wsSettings.legacyNote'),
      'squad.lua: the call uses the weapon skill settings; !squad ws adds the note')

-- ================================================================= 5. camp and pulling commands (v0.1.48)
section('camp: set, Start, pause, links')
W.squad = { { id = 1, slot = 1, name = 'Mira', mjob = WHM, sjob = 0, jobs = {} } }
local pc = player()
local campMate = spawnWith(H, pc, 1, WHM, 30, nil, nil, function(self) return { self } end)
pc.pos = { x = 10, y = 5, z = 20 }
local firstLine = #pc.printed + 1
cmd.onTrigger(pc, 'camp', 'here')
local said = table.concat(pc.printed, '\n', firstLine)
check(has(said, 'Camp set here') and has(said, 'Nothing is pulled until you press Start'), 'a new camp waits for Start: ' .. said)
check(campMate:getLocalVar('SQUAD_CAMP') == 1, 'the camp is put on the mate')
cmd.onTrigger(pc, 'camp', 'start')
check(pc.printed[#pc.printed] == 'Pulling starts.', '!squad camp start: ' .. tostring(pc.printed[#pc.printed]))
cmd.onTrigger(pc, 'camp', 'pause')
check(has(pc.printed[#pc.printed] or '', 'Pulls paused'), '!squad camp pause')
cmd.onTrigger(pc, 'camp', 'links', '2')
check(SQUAD_LINK.max == 2 and has(pc.printed[#pc.printed] or '', 'up to 2 extra'), '!squad camp links 2')
cmd.onTrigger(pc, 'camp', 'links', '9')
check(SQUAD_LINK.max == 2, 'links above 5 are refused')
SQUAD_LINK.max = 0
cmd.onTrigger(pc, 'camp', 'off')
check(campMate:getLocalVar('SQUAD_CAMP') == 0, 'camp off lifts it from the mate')
local pool = { { id = 1, name = 'Bee', x = 0, z = 0 }, { id = 2, name = 'Bee', x = 15, z = 0 },
               { id = 3, name = 'Crab', x = 10, z = 0 }, { id = 4, name = 'Crab', x = 30, z = 0 } }
local bee = { getName = function() return 'Bee' end, getID = function() return 1 end }
check(squadLinkCount(pool, bee, { x = 0, z = 0 }) == 2, 'link count: a Bee 15 away (same kind, 20) and a Crab 10 away (near, 12); not the Crab at 30')

-- ================================================================= 6. the !squad error wrapper and the print filter
section('v0.1.48 !squad error wrapper and print filter with our command')
local realRs = package.loaded['modules/custom/lua/squad_rulesets']
package.loaded['modules/custom/lua/squad_rulesets'] = { command = function() error('boom in ruleset') end }
local okC = pcall(cmd.onTrigger, player(), 'ruleset')
package.loaded['modules/custom/lua/squad_rulesets'] = realRs
check(okC == false and logHas('[squad] COMMAND ERROR') and logHas('boom in ruleset'), 'an error in !squad ruleset is logged with its cause and still raised')
local pl = player()
W.squad = { { id = 1, slot = 1, name = 'Mira', mjob = WHM, sjob = 0, jobs = {} } }
DATA = store({ whmSet })
cmd.onTrigger(pl, 'ruleset')
check(has(pl.printed[1] or '', 'Rule Set 1: WHM U13'), '!squad ruleset still lists through the wrapper')
print('brace {test}')
check(LOG[#LOG] == 'brace test', 'the print filter drops braces only')

-- ================================================================= 7. existing Rule Set data loads unchanged
section('Rule Set data format')
local example = dofile((arg[0]:match('^(.*)[/\\][^/\\]*$') or '.') .. '/example_squad_rulesets_data.lua')
DATA = example
local st = RS.load()
check(#st.problems == 0 and #st.list == 1, 'the example data file loads (format xifo-ruleset-store v1)')
if DATAFILE then
    local before = readAll(DATAFILE)
    DATA = dofile(DATAFILE)
    st = RS.load()
    check(#st.problems == 0 and #st.list >= 1, string.format('the DEV data (copy) loads: %d set(s), %d problem(s)', #st.list, #st.problems))
    check(readAll(DATAFILE) == before, 'and is not changed by loading')
else
    io.write('  (no DEV data copy given: skipped)\n')
end
DATA = nil

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
