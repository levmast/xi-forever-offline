-- Gambits v2, milestone 1: stand-in tests for per-mate Rule Sets on the server (squad_rulesets.lua + the two hooks in
-- squad.lua). No server and no game: the server files are loaded read-only, with the real gambit constants.
--   luajit test_squad_rulesets.lua <server>/modules/custom/lua/squad.lua <server>/modules/custom/lua/squad_starter_gear.lua
--                                  <server>/scripts/globals/gambits.lua <server>/modules/custom/lua/squad_rulesets.lua
--                                  <squad.lua WITHOUT the hooks, e.g. from git show HEAD:...>
--                                  <server>/scripts/enum/job_ability.lua (git show HEAD:scripts/enum/job_ability.lua)
-- The 5th file: every built-in case is also compared gambit by gambit with the unchanged squad.lua.
-- The 6th file: the real ability ids (xi.ja), so the built-in rules meet the real job ability table (U13).
-- M1.1: squad_ja_jobs_data.lua is read from the folder of squad_rulesets.lua (the job ability table).
-- U13: squad_ability_rules.lua (the shared job ability rules) is read from the same folder.
-- Run it from an empty folder. Nothing is written: the chat bridge stays off while __SQUAD_TEST exists.
local SQUAD, GEAR, GAMBITS, RULESETS, ORIGINAL, JA_ENUM = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
local JA_FILE = (RULESETS or ''):gsub('squad_rulesets%.lua$', 'squad_ja_jobs_data.lua')
local ABILITY_RULES_FILE = (RULESETS or ''):gsub('squad_rulesets%.lua$', 'squad_ability_rules.lua')
assert(SQUAD and GEAR and GAMBITS and RULESETS and ORIGINAL and JA_ENUM,
       'usage: test_squad_rulesets.lua squad.lua squad_starter_gear.lua gambits.lua squad_rulesets.lua original-squad.lua job_ability.lua')
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end

-- ---------------------------------------------------------------- the server bits squad.lua needs
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

local spellIds, spellName = registry(1, nil, { NOT_A_SPELL = true })
local familyIds, familyName = registry(1, { NONE = 0 })
xi = { module = { registerCommand = function() end }, objType = { PC = 1, TRUST = 2, MOB = 3 },
       animation = { NONE = 0, ATTACK = 1, HEALING = 33 }, settings = { map = { EXP_RATE = 1 } } }
setmetatable(xi, { __index = function(t, k) local v = setmetatable({}, { __index = function() return 0 end }) rawset(t, k, v) return v end })
xi.mobMod = { TRUST_DISTANCE = 77 }
xi.trust = { movementType = { NO_MOVE = -1, NON_COMBAT = -2, MELEE = 0, MID_RANGE = 6, LONG_RANGE = 12 } }
xi.magic = { spellFamily = familyIds, spell = spellIds }
-- U13: the real ability ids (scripts/enum/job_ability.lua defines xi.jobAbility and xi.ja = xi.jobAbility), so built-in
-- rules meet the real ability table. The ids the tests name are checked against it below.
local JA = { PROVOKE = 35, BERSERK = 31, DIVINE_SEAL = 74, ELEMENTAL_SEAL = 75, MIGHTY_STRIKES = 16, BENEDICTION = 18,
             HEALING_BREATH = 640, AFFLATUS_SOLACE = 245, AFFLATUS_MISERY = 246, COMPOSURE = 247, YONIN = 248, INNIN = 249,
             SPIRIT_LINK = 80, CALL_WYVERN = 61, VELOCITY_SHOT = 224, HEALING_RUBY = 512, PET_COMMANDS = 55,
             WEAPON_BASH = 77, CONVERT = 83, MARTYR = 153, DEVOTION = 154, JUMP = 66, SIC = 72, READY = 251 }
rawset(xi, 'jobAbility', nil)
dofile(JA_ENUM)
assert(type(rawget(xi, 'ja')) == 'table' and xi.ja.PROVOKE == 35, 'job_ability.lua did not define xi.ja')
for name, id in pairs(JA) do assert(xi.ja[name] == id, 'test id for ' .. name .. ' differs from job_ability.lua') end
assert(xi.ja.NOT_AN_ABILITY == nil)
-- the owner's merits (squad.cpp SquadOwnerMerit in the real server): entity.merits[meritId] = upgrades
local function ownerMeritMock(owner, meritId) return (type(owner) == 'table' and owner.merits and owner.merits[meritId]) or 0 end
SquadOwnerMerit = ownerMeritMock
xi.effect = registry(1, nil, { HASTEE = true })
xi.effectFlag = { ERASABLE = 1 }
xi.ecosystem = { UNDEAD = 19, VERMIN = 20 }

Module = { new = function() return { addOverride = function() end } end }
package.preload['modules/module_utils'] = function() return true end
package.preload['modules/custom/lua/squad_starter_gear'] = function() return dofile(GEAR) end
local W = { squad = {} }
GetSquad = function() return W.squad end
SetSquadEquip = function() end
UnlockSquadItem = function() end
GetSquadItemInfo = function() return { valid = false } end
BuildStarterGear = function() return {} end
GetSquadUnlocks = function() return {} end

-- the Rule Set data file the module reads; DATA is swapped by the tests (nil = no file)
local DATA_MODULE = 'modules/custom/lua/squad_rulesets_data'
local DATA = nil
local function useData(value) DATA = value end
package.preload[DATA_MODULE] = function()
    if DATA == nil then error("module '" .. DATA_MODULE .. "' not found") end
    if type(DATA) == 'function' then return DATA() end
    return DATA
end
local RULESETS_MODULE = 'modules/custom/lua/squad_rulesets'
package.preload[RULESETS_MODULE] = function() return dofile(RULESETS) end
local ABILITY_RULES_MODULE = 'modules/custom/lua/squad_ability_rules'
package.preload[ABILITY_RULES_MODULE] = function() return dofile(ABILITY_RULES_FILE) end
-- the job ability table: the real generated file, unless a test swaps it (JA_DATA = 'missing' or any value to return)
local JA_DATA = nil
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function()
    if JA_DATA == 'missing' then error("module 'modules/custom/lua/squad_ja_jobs_data' not found") end
    if type(JA_DATA) == 'function' then return JA_DATA() end
    if JA_DATA ~= nil then return JA_DATA end
    return dofile(JA_FILE)
end

local WAR, WHM, BLM, RDM = 1, 3, 4, 5

local function entity(kind, opts)
    local e = { kind = kind, vars = {}, level = opts.level or 1, id = opts.id or 0, printed = {} }
    function e:getObjType() return self.kind end
    function e:getLocalVar(k) return self.vars[k] or 0 end
    function e:setLocalVar(k, v) self.vars[k] = v end
    function e:getMainLvl() return self.level end
    function e:getMainJob() return opts.job or 1 end
    function e:getSubJob() return opts.sub or 0 end
    function e:getSubLvl() return opts.subLevel or 0 end
    function e:getID() return self.id end
    function e:getName() return 'Tester' end
    function e:getMaster() return self.master end
    function e:printToPlayer(text) self.printed[#self.printed + 1] = text end
    return setmetatable(e, { __index = function() return function() return 0 end end })
end

local function player()
    local p = entity(xi.objType.PC, { level = 75, id = 4 })
    function p:getCharVar(k) return self.vars[k] or 0 end
    function p:setCharVar(k, v) self.vars[k] = v end
    return p
end

local function spawn(H, master, mateId, job, level, sub, subLevel)
    local t = entity(xi.objType.TRUST, { level = level or 30, job = job, sub = sub, subLevel = subLevel })
    t.master, t.gambits, t.mobMods = master, {}, {}
    function t:addGambit(target, condition, action, retry)
        self.gambits[#self.gambits + 1] = { target = target, condition = condition, action = action, retry = retry }
    end
    function t:getMobMod(id) return self.mobMods[id] or 0 end
    function t:setMobMod(id, v) self.mobMods[id] = v end
    function t:setAutoAttackEnabled(on) self.autoAttack = on end
    t:setLocalVar('SQUAD_ID', mateId)
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
    for _, g in ipairs(t.gambits) do
        out[#out + 1] = string.format('%s|%s|%s|%s', tostring(g.target), serialize(g.condition), serialize(g.action), tostring(g.retry))
    end
    return table.concat(out, '\n')
end

local function isCureRule(g, threshold, family)
    if g == nil then return false end
    local ok = g.target == ai.t.PARTY and g.condition[1] == ai.c.HPP_LT and g.condition[2] == threshold and g.action[1] == ai.r.MA
    if family then
        return ok and g.action[2] == ai.s.HIGHEST and familyName[g.action[3]] == 'CURE'
    end
    return ok and g.action[2] == ai.s.SPECIFIC and spellName[g.action[3]] == 'CURE_II'
end

-- ---------------------------------------------------------------- fixtures
local R1 = { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' } }
local R2 = { id = 'r2', on = true, target = 'PARTY', cond = { 'HPP_LT', 75 }, action = { 'spell', 'CURE_II' } }
local function whmSet(rules, extra)
    local set = { format = 'xifo-ruleset', version = 1, num = 1, id = 'custom.whm.cure-basics', name = 'WHM - Cure basics',
                  job = 'WHM', rules = rules or { R1, R2 } }
    for k, v in pairs(extra or {}) do set[k] = v end
    return set
end
local function store(sets) return { format = 'xifo-ruleset-store', version = 1, sets = sets } end
local function copy(t, changes)
    local out = {}
    for k, v in pairs(t) do out[k] = v end
    for k, v in pairs(changes or {}) do out[k] = v end
    return out
end

-- ---------------------------------------------------------------- load squad.lua (and the unchanged one, if given)
local HO = nil
if ORIGINAL then
    __SQUAD_TEST = {}
    assert(loadfile(ORIGINAL))()
    HO = __SQUAD_TEST.hooks
    PROFILE_OLD = xi.squad.profileFor -- the bot profiles of the unchanged squad.lua (U13 comparison)
end
__SQUAD_TEST = {}
assert(loadfile(SQUAD))()
local H = __SQUAD_TEST.hooks
PROFILE_NEW = xi.squad.profileFor
assert(H and H.squadSpawn and H.commandObj, 'squad.lua without test hooks')
local RS = require(RULESETS_MODULE)
local cmd = H.commandObj

-- ================================================================= tests
section('Rule Set validation and loading')
useData(store({ whmSet() }))
local st = RS.load()
check(#st.problems == 0 and st.byNum[1] ~= nil and st.byId['custom.whm.cure-basics'] ~= nil, 'a valid WHM set loads by number and by id')
useData(nil)
st = RS.load()
check(#st.list == 0 and #st.problems == 0, 'no data file: no sets and no problem (the normal case)')
useData(function() error('syntax error near x') end)
st = RS.load()
check(#st.list == 0 and #st.problems == 1 and st.problems[1]:find('could not be read', 1, true), 'a broken data file gives no sets and one clear problem')
useData({ format = 'something-else', version = 1, sets = {} })
st = RS.load()
check(#st.list == 0 and st.problems[1] and st.problems[1]:find('must return', 1, true), 'a file of another format is refused')

local bad = {
    { whmSet(nil, { format = 'xifo-ruleset', version = 2 }), 'format must be' },
    { whmSet(nil, { num = 0 }), 'num must be' },
    { whmSet(nil, { num = 1.5 }), 'num must be' },
    { whmSet(nil, { id = 'has space' }), 'id must be' },
    { whmSet(nil, { name = '' }), 'name is missing' },
    { whmSet(nil, { job = 'XYZ' }), 'job must be' },
    { whmSet({}), 'at least one rule' },
    { whmSet({ copy(R1, { target = 'party' }) }), 'target must be' },
    { whmSet({ copy(R1, { target = 'NOBODY' }) }), 'unknown target' },
    { whmSet({ copy(R1, { cond = { 'HPP_UNDER', 40 } }) }), 'unknown condition' },
    { whmSet({ copy(R1, { cond = 'HPP_LT 40' }) }), 'cond:' },
    { whmSet({ copy(R1, { cond2 = { 'MPP_GTE', 'lots' } }) }), 'cond2:' },
    { whmSet({ copy(R1, { action = { 'teleport', 'X' } }) }), 'action must be' },
    { whmSet({ copy(R1, { action = { 'spell' } }) }), 'needs a NAME' },
    { whmSet({ copy(R1, { retry = 9999 }) }), 'retry must be' },
    { whmSet({ copy(R1, { level = 99 }) }), 'level must be' },
    { whmSet({ copy(R1, { on = 'yes' }) }), 'on must be' },
    { whmSet({ R1, copy(R2, { id = 'r1' }) }), 'used twice' },
}
for i, case in ipairs(bad) do
    useData(store({ case[1] }))
    st = RS.load()
    check(#st.list == 0 and st.problems[1] ~= nil and st.problems[1]:find(case[2], 1, true) ~= nil,
          string.format('bad set %d is refused with "%s": %s', i, case[2], tostring(st.problems[1])))
end
local many = {}
for i = 1, RS.MAX_RULES + 1 do many[i] = copy(R1, { id = 'r' .. i }) end
useData(store({ whmSet(many) }))
check(RS.load().problems[1]:find('at most', 1, true) ~= nil, 'more than ' .. RS.MAX_RULES .. ' rules is refused')
useData(store({ whmSet(), whmSet(nil, { id = 'other' }) }))
st = RS.load()
check(#st.list == 1 and st.problems[1]:find('num 1 is used', 1, true), 'a second set with the same number is refused, the first stays usable')
useData(store({ whmSet(nil, { job = 'NOPE', num = 2, id = 'broken' }), whmSet() }))
st = RS.load()
check(#st.list == 1 and st.byNum[1] ~= nil and #st.problems == 1, 'one broken set does not stop the valid one')

local HERE = (arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local example = dofile(HERE .. '/example_squad_rulesets_data.lua')
useData(example)
st = RS.load()
check(#st.problems == 0 and #st.list == 1 and st.byNum[1].id == 'custom.whm.cure-basics',
      'the example data file (example_squad_rulesets_data.lua) is valid')

section('selection per mate and main job (!squad ruleset)')
local p = player()
W.squad = { { id = 1, slot = 1, name = 'Mira', mjob = WHM, sjob = 0, jobs = {} },
            { id = 7, slot = 2, name = 'Tess', mjob = WHM, sjob = 0, jobs = {} },
            { id = 9, slot = 3, name = 'Rook', mjob = RDM, sjob = 0, jobs = {} } }
useData(store({ whmSet(), whmSet(nil, { num = 2, id = 'custom.rdm.x', name = 'RDM test', job = 'RDM' }) }))
cmd.onTrigger(p, 'ruleset')
check(p.printed[1] and p.printed[1]:find('Rule Set 1: WHM - Cure basics (WHM, 2 rules)', 1, true), 'listing names each set: ' .. tostring(p.printed[1]))
cmd.onTrigger(p, 'ruleset', '1', '1')
check(p.vars.SQUAD_RS_1_3 == 1, 'slot 1 (mate id 1, WHM) stores SQUAD_RS_1_3 = 1')
check(p.vars.SQUAD_RSH_1_3 == RS.idHash('custom.whm.cure-basics'), 'and SQUAD_RSH_1_3 = the check number of its id (M1.1)')
check(p.printed[#p.printed]:find('now follows Rule Set 1', 1, true), 'and says so: ' .. p.printed[#p.printed])
cmd.onTrigger(p, 'ruleset', '2', '1')
check(p.vars.SQUAD_RS_7_3 == 1, 'slot 2 is mate id 7: the choice is keyed by mate id, not slot')
cmd.onTrigger(p, 'ruleset', '3', '1')
check(p.vars.SQUAD_RS_9_5 == nil and p.printed[#p.printed]:find('is for WHM', 1, true), 'a WHM set is refused for the RDM mate: ' .. p.printed[#p.printed])
cmd.onTrigger(p, 'ruleset', '1', '42')
check(p.printed[#p.printed]:find('no usable Rule Set', 1, true) and p.vars.SQUAD_RS_1_3 == 1, 'an unknown number changes nothing')
cmd.onTrigger(p, 'ruleset', '5', '1')
check(p.printed[#p.printed]:find('No squad mate in that slot', 1, true), 'an empty slot is reported')
cmd.onTrigger(p, 'ruleset', '1')
check(p.printed[#p.printed]:find('Rule Set 1, WHM - Cure basics', 1, true), 'asking shows the current choice')
cmd.onTrigger(p, 'ruleset', '2', 'off')
check(p.vars.SQUAD_RS_7_3 == 0, 'off clears the choice for that mate only')
check(p.vars.SQUAD_RS_1_3 == 1, 'and leaves the other mate as it was')

section('the WHM rules, in order, for the chosen mate only')
local mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == 2, 'mate 1 gets exactly the two Rule Set gambits (' .. #mate1.gambits .. ')')
check(isCureRule(mate1.gambits[1], 40, true), 'first: party member below 40% -> best Cure of the family')
check(isCureRule(mate1.gambits[2], 75, false), 'second: party member below 75% -> Cure II')
local mate7 = spawn(H, p, 7, WHM, 30)
local builtInWhm = #mate7.gambits
check(builtInWhm > 2, 'mate 7 (choice cleared) keeps the built-in WHM rules (' .. builtInWhm .. ' gambits)')

section('changes to the data file apply at the next call, without a restart')
useData(store({ whmSet({ R2, R1 }) }))
mate1 = spawn(H, p, 1, WHM, 30)
check(isCureRule(mate1.gambits[1], 75, false) and isCureRule(mate1.gambits[2], 40, true), 'Cure II moved to the top is first after calling the mate again')
useData(store({ whmSet({ copy(R1, { on = false }), R2 }) }))
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == 1 and isCureRule(mate1.gambits[1], 75, false), 'a rule switched off is left out')

section('invalid or unavailable actions')
useData(store({ whmSet({ copy(R1, { action = { 'spell', 'NOT_A_SPELL' } }), R2 }) }))
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == 1 and isCureRule(mate1.gambits[1], 75, false), 'a spell the server does not know drops only that rule')
useData(store({ whmSet({ R1, copy(R2, { level = 40 }) }) }))
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == 1 and isCureRule(mate1.gambits[1], 40, true), 'a rule above the mate\'s level (40 > 30) is left out')
useData(store({ whmSet(nil, { job = 'NOPE' }) }))
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == builtInWhm, 'the chosen set became invalid: the mate falls back to its built-in WHM rules')
useData(nil)
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == builtInWhm, 'the data file is gone: built-in WHM rules')
p.vars.SQUAD_RS_9_5 = 1
useData(store({ whmSet() }))
local rook = spawn(H, p, 9, RDM, 30)
local rookAlone = spawn(H, player(), 9, RDM, 30)
check(list(rook) == list(rookAlone), 'a WHM set stored under the RDM key (by hand) is ignored: built-in RDM rules')
p.vars.SQUAD_RS_9_5 = nil

section('main job only: the sub job does not switch or add rules')
useData(store({ whmSet() }))
local withSub = spawn(H, p, 1, WHM, 30, BLM, 15)
check(#withSub.gambits == 2, 'WHM/BLM with the set: only the two set rules, no BLM sub-job gambits (' .. #withSub.gambits .. ')')
local plainSub = spawn(H, p, 7, WHM, 30, BLM, 15)
check(#plainSub.gambits > builtInWhm, 'WHM/BLM without a set still gets its BLM sub-job gambits (' .. #plainSub.gambits .. ')')
local asRdm = spawn(H, p, 1, RDM, 30)
local rdmAlone = spawn(H, player(), 1, RDM, 30)
check(list(asRdm) == list(rdmAlone), 'the same mate as RDM (no RDM choice) uses the built-in RDM rules')

section('role and mode do not change a Rule Set')
p.vars.SQUAD_AI_1 = 32          -- healer + conserve
mate1 = spawn(H, p, 1, WHM, 30)
check(isCureRule(mate1.gambits[1], 40, true) and isCureRule(mate1.gambits[2], 75, false), 'healer/conserve: still 40% and 75%')
p.vars.SQUAD_AI_1 = 20          -- damage
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == 2 and isCureRule(mate1.gambits[1], 40, true), 'damage role: the Cure rule is neither dropped nor capped')
p.vars.SQUAD_AI_7 = 32
mate7 = spawn(H, p, 7, WHM, 30)
local cureThresholds = {}
for _, g in ipairs(mate7.gambits) do
    if g.action[2] == ai.s.HIGHEST and familyName[g.action[3]] == 'CURE' and g.condition[1] == ai.c.HPP_LT then
        cureThresholds[#cureThresholds + 1] = g.condition[2]
    end
end
check(cureThresholds[1] == 15 and cureThresholds[2] == 60, 'mate 7 without a set: healer/conserve still shifts its built-in Cures '
      .. '(25% -> 15%, the floor; 75% -> 60%): ' .. table.concat(cureThresholds, ', '))
p.vars.SQUAD_AI_1, p.vars.SQUAD_AI_7 = nil, nil

section('settings that still apply to a mate with a Rule Set')
p.vars.SQUAD_SW_1 = 7 + 1       -- magic off
mate1 = spawn(H, p, 1, WHM, 30)
check(#mate1.gambits == 0, 'the magic switch still turns off the set\'s spells (on/off switches are kept on purpose)')
p.vars.SQUAD_SW_1 = nil
p.vars.SQUAD_RANGE_1 = 3
mate1 = spawn(H, p, 1, WHM, 30)
check(mate1.mobMods[xi.mobMod.TRUST_DISTANCE] == xi.trust.movementType.LONG_RANGE, 'the chosen combat distance still applies')
p.vars.SQUAD_RANGE_1 = nil

section('bots keep using the job rules')
local botList = xi.squad.profileFor(WHM, 30, 0, 0)
check(#botList == builtInWhm, 'profileFor(WHM) lists the built-in WHM rules even though a mate has a set (' .. #botList .. ')')

-- ================================================================= M1.1
local function last(who) return tostring(who.printed[#who.printed]) end
local function loads(rules) useData(store({ whmSet(rules) })) return RS.load() end
local function condRule(cond) return { id = 'c', target = 'PARTY', cond = cond, action = { 'family', 'CURE' } } end
local function jaRule(name, extra) return copy({ id = 'j-' .. name, target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', name } }, extra) end
local function hasJa(t, id)
    for _, g in ipairs(t.gambits) do
        if g.action[1] == ai.r.JA and g.action[3] == id then return true end
    end
    return false
end
local builtInList = list(spawn(H, player(), 1, WHM, 30))

section('M1.1 condition arguments, as the engine reads them')
local goodConds = {
    { 'HPP_LT', 0 }, { 'HPP_LT', 100 }, { 'HPP_GTE', 50 }, { 'MPP_LT', 30 }, { 'MPP_GTE', 100 }, { 'HPP_LT', { main = 50, sub = 30 } },
    { 'TP_GTE', 1000 }, { 'TP_LT', 3000 }, { 'LVL_LT', 30 }, { 'HP_MISSING', 500 }, { 'RANDOM', 100 }, { 'TIMER', 0 }, { 'TIMER', 60 },
    { 'ALWAYS' }, { 'ALWAYS', 0 }, { 'PT_HAS_TANK' }, { 'STATUS', 'HASTE' }, { 'NOT_STATUS', 'PROTECT' },
    { 'STATUS_FLAG', { flag = 'ERASABLE' } }, { 'IS_ECOSYSTEM', { ecosystem = 'UNDEAD' } },
}
for _, c in ipairs(goodConds) do
    local s = loads({ condRule(c) })
    check(#s.problems == 0, 'accepted: ' .. serialize(c) .. ' ' .. tostring(s.problems[1]))
end
local badConds = {
    { { 'HPP_LT', 101 }, 'whole number 0-100' }, { { 'HPP_LT', -1 }, 'whole number 0-100' }, { { 'HPP_LT', 40.5 }, 'whole number 0-100' },
    { { 'HPP_LT' }, 'whole number 0-100' }, { { 'HPP_LT', 'HASTE' }, 'whole number 0-100' }, { { 'HPP_LT', { main = 150 } }, 'main needs' },
    { { 'TP_GTE', 3001 }, 'whole number 0-3000' }, { { 'RANDOM', 0 }, 'whole number 1-100' }, { { 'TIMER', 4000 }, '0-3600' },
    { { 'ALWAYS', 5 }, 'takes no value' }, { { 'PT_HAS_TANK', 'YES' }, 'takes no value' },
    { { 'STATUS', 5 }, 'status effect name' }, { { 'STATUS', 'HASTEE' }, 'unknown status effect HASTEE' },
    { { 'STATUS_FLAG', 'ERASABLE' }, 'needs { flag = NAME }' }, { { 'STATUS_FLAG', { flag = 'NOPE' } }, 'unknown effect flag NOPE' },
    { { 'IS_ECOSYSTEM', 'UNDEAD' }, 'needs { ecosystem = NAME }' }, { { 'IS_ECOSYSTEM', { ecosystem = 'NOPE' } }, 'unknown ecosystem NOPE' },
    { { 'JA_ON_COOLDOWN', 35 }, 'needs the updated map server' }, { { 'SUB_ANIMATION', 1 }, 'cannot be used in a Rule Set' },
    { { 'VAL_URIEL_CHECK' }, 'cannot be used in a Rule Set' },
}
for _, case in ipairs(badConds) do
    local s = loads({ condRule(case[1]) })
    check(#s.list == 0 and s.problems[1] ~= nil and s.problems[1]:find(case[2], 1, true) ~= nil,
          string.format('refused: %s with "%s": %s', serialize(case[1]), case[2], tostring(s.problems[1])))
end
local s2 = loads({ copy(R1, { cond2 = { 'MPP_GTE', 150 } }) })
check(s2.problems[1] and s2.problems[1]:find('cond2: MPP_GTE needs a whole number 0-100', 1, true), 'the second condition is checked the same way')
local covered, typos = 0, {}
for name in pairs(ai.c) do
    if RS.CONDITIONS[name] or RS.REFUSED_CONDITIONS[name] then covered = covered + 1 end
end
for name in pairs(RS.CONDITIONS) do if ai.c[name] == nil then typos[#typos + 1] = name end end
check(#typos == 0, 'every supported condition exists in gambits.lua: ' .. table.concat(typos, ', '))
local engineCount = 0
for _ in pairs(ai.c) do engineCount = engineCount + 1 end
check(covered == engineCount, string.format('every engine condition is either supported or refused with a reason (%d of %d)', covered, engineCount))
ai.c.BRAND_NEW = 99
s2 = loads({ condRule({ 'BRAND_NEW', 1 }) })
check(s2.problems[1] and s2.problems[1]:find('not supported in Rule Sets yet', 1, true), 'a condition the engine adds later fails clearly until it is described')
ai.c.BRAND_NEW = nil

section('M1.1 sets that cannot do anything are refused')
s2 = loads({ copy(R1, { on = false }), copy(R2, { on = false }) })
check(#s2.list == 0 and s2.problems[1]:find('no rule is switched on', 1, true), 'a set with every rule off is refused: ' .. tostring(s2.problems[1]))
s2 = loads({ copy(R1, { on = false }), R2 })
check(#s2.problems == 0, 'one rule on is enough')

section('M1.1 the choice follows the set by its id, never a reused number')
local A = whmSet(nil, { num = 3, id = 'custom.whm.a', name = 'WHM A' })
local B = whmSet({ R2 }, { num = 3, id = 'custom.whm.b', name = 'WHM B' })
useData(store({ A }))
local q = player()
cmd.onTrigger(q, 'ruleset', '1', '3')
check(q.vars.SQUAD_RS_1_3 == 3 and q.vars.SQUAD_RSH_1_3 == RS.idHash('custom.whm.a') and q.vars.SQUAD_RSH_1_3 > 0,
      'choosing stores the number and the id check number (SQUAD_RSH_1_3)')
check(last(q):find('[custom.whm.a]', 1, true), 'the reply names the set id: ' .. last(q))
check(RS.idHash('custom.whm.a') ~= RS.idHash('custom.whm.b') and RS.idHash('x') < 2147483647, 'check numbers differ per id and fit a char var')
useData(store({ copy(A, { num = 5 }) }))
local m = spawn(H, q, 1, WHM, 30)
check(#m.gambits == 2 and isCureRule(m.gambits[1], 40, true), 'the set got number 5: the mate still follows it by its id')
cmd.onTrigger(q, 'ruleset', '1')
check(last(q):find('Rule Set 5, WHM A', 1, true), 'and the status shows its new number: ' .. last(q))
useData(store({ B }))
local before = #q.printed
m = spawn(H, q, 1, WHM, 30)
check(list(m) == builtInList, 'number 3 now belongs to a different set: the mate does NOT follow it, built-in WHM rules')
check(#q.printed == before + 1 and last(q):find('now a different set', 1, true), 'and the player is told once: ' .. last(q))
cmd.onTrigger(q, 'ruleset', '1')
check(last(q):find('replaced by a different set', 1, true), 'the status explains it: ' .. last(q))
useData(store({ B, copy(A, { num = 5 }) }))
m = spawn(H, q, 1, WHM, 30)
check(#m.gambits == 2 and isCureRule(m.gambits[1], 40, true), 'with both present it follows A (number 5), not B (number 3)')
local savedHash = RS.idHash
RS.idHash = function() return 42 end
q.vars.SQUAD_RS_1_3, q.vars.SQUAD_RSH_1_3 = 9, 42    -- number 9 is gone; two sets now share the check number
useData(store({ B, whmSet(nil, { num = 7, id = 'custom.whm.c' }) }))
m = spawn(H, q, 1, WHM, 30)
check(list(m) == builtInList, 'two sets with the same check number (forced): neither is guessed, built-in rules')
RS.idHash = savedHash
local old = player()
old.vars.SQUAD_RS_1_3 = 1
useData(store({ whmSet() }))
m = spawn(H, old, 1, WHM, 30)
check(#m.gambits == 2, 'a choice made before M1.1 (no check number) still follows its number')
cmd.onTrigger(q, 'ruleset', '1', 'off')
check(q.vars.SQUAD_RS_1_3 == 0 and q.vars.SQUAD_RSH_1_3 == 0, 'off clears both char vars')

section('M1.1 an unusable set falls back to the job rules, with a message')
local f = player()
useData(store({ whmSet({ copy(R1, { level = 60 }) }) }))
cmd.onTrigger(f, 'ruleset', '1', '1')
before = #f.printed
m = spawn(H, f, 1, WHM, 30)
check(list(m) == builtInList, 'its only rule needs level 60 (mate 30): built-in WHM rules, gambit by gambit')
check(#f.printed == before + 1 and last(f):find('has no rule your WHM squad mate can use at level 30', 1, true), 'the player is told: ' .. last(f))
useData(store({ whmSet({ copy(R1, { action = { 'spell', 'NOT_A_SPELL' } }) }) }))
m = spawn(H, f, 1, WHM, 30)
check(list(m) == builtInList, 'its only rule names an unknown spell: built-in WHM rules')
useData(store({ whmSet({ copy(R1, { action = { 'spell', 'NOT_A_SPELL' } }), R2 }) }))
m = spawn(H, f, 1, WHM, 30)
check(#m.gambits == 1 and isCureRule(m.gambits[1], 75, false), 'one usable rule left: the set is kept with just that rule')
useData(store({ whmSet() }))
f.vars.SQUAD_SW_1 = 7 + 1       -- magic off
before = #f.printed
m = spawn(H, f, 1, WHM, 30)
check(#m.gambits == 0 and #f.printed == before, 'magic switched off (a player choice): no spells, NO fallback to the job rules, no message')
f.vars.SQUAD_SW_1 = nil
useData(store({ whmSet(nil, { job = 'NOPE' }) }))
before = #f.printed
m = spawn(H, f, 1, WHM, 30)
check(list(m) == builtInList and #f.printed == before + 1 and last(f):find('no longer usable', 1, true), 'the chosen set became invalid: built-in rules and a message: ' .. last(f))

section('M1.1 job abilities: main job or sub job, at their levels')
local function jaSpawn(rules, level, sub, subLevel)
    local who = player()
    useData(store({ whmSet(rules) }))
    who.vars.SQUAD_RS_1_3, who.vars.SQUAD_RSH_1_3 = 1, RS.idHash('custom.whm.cure-basics')
    return spawn(H, who, 1, WHM, level, sub, subLevel), who
end
m = jaSpawn({ R2, jaRule('DIVINE_SEAL') }, 30)
check(#m.gambits == 2 and hasJa(m, JA.DIVINE_SEAL), 'WHM 30: Divine Seal (WHM 15) is kept')
m = jaSpawn({ R2, jaRule('DIVINE_SEAL') }, 10)
check(#m.gambits == 1 and not hasJa(m, JA.DIVINE_SEAL), 'WHM 10: Divine Seal (needs 15) is left out, even without a level on the rule')
m = jaSpawn({ R2, jaRule('PROVOKE') }, 30, WAR, 15)
check(#m.gambits == 2 and hasJa(m, JA.PROVOKE), 'WHM/WAR 30/15: Provoke (WAR 5) works as a SUB JOB ability')
m = jaSpawn({ R2, jaRule('PROVOKE') }, 30, WAR, 4)
check(#m.gambits == 1 and not hasJa(m, JA.PROVOKE), 'WHM/WAR 30/4: Provoke needs sub level 5, left out')
m = jaSpawn({ R2, jaRule('PROVOKE') }, 30, BLM, 15)
check(#m.gambits == 1 and not hasJa(m, JA.PROVOKE), 'WHM/BLM: Provoke belongs to neither job, left out')
m = jaSpawn({ R2, jaRule('ELEMENTAL_SEAL') }, 30, BLM, 15)
check(#m.gambits == 2 and hasJa(m, JA.ELEMENTAL_SEAL), 'WHM/BLM 30/15: Elemental Seal (BLM 15) works as a sub job ability')
m = jaSpawn({ R2, jaRule('MIGHTY_STRIKES') }, 30, WAR, 15)
check(#m.gambits == 1 and not hasJa(m, JA.MIGHTY_STRIKES), 'WHM/WAR: Mighty Strikes (WAR two-hour) is never used from the sub job')
m = jaSpawn({ R2, jaRule('BENEDICTION') }, 30)
check(#m.gambits == 2 and hasJa(m, JA.BENEDICTION), 'WHM: its own two-hour (Benediction) is kept')
m = jaSpawn({ R2, jaRule('DIVINE_SEAL', { level = 40 }) }, 30)
check(#m.gambits == 1, 'the rule\'s own level still applies on top (40 > 30)')
local onlyBad, who = jaSpawn({ jaRule('PROVOKE') }, 30, BLM, 15)
check(list(onlyBad) == list(spawn(H, player(), 1, WHM, 30, BLM, 15)) and last(who):find('has no rule', 1, true), 'a set whose only rule is another job\'s ability falls back, with a message')
m = jaSpawn({ R2, jaRule('NOT_AN_ABILITY') }, 30)
check(#m.gambits == 1, 'an unknown job ability name is left out when called (as in M1)')
s2 = loads({ R2, jaRule('HEALING_BREATH') })
check(#s2.list == 0 and s2.problems[1]:find('belongs to no job', 1, true), 'a pet ability with no job (wyvern breath) is refused at load: ' .. tostring(s2.problems[1]))
s2 = loads({ R2, jaRule('PROVOKE') })
check(#s2.problems == 0, 'another job\'s ability is NOT refused at load: it may be the sub job (checked when called)')

section('M1.1 correction: job abilities fail closed without a usable table')
local function withTable(value)
    JA_DATA = value
    RS.reloadJaTable()
end
local function isCureII(g) return isCureRule(g, 75, false) end
local tableCases = {
    { 'missing', 'the table file is missing' },
    { function() error('syntax error') end, 'the table file is broken' },
    { 'garbage', 'the table is not a table' },
    { { version = 1, abilities = { [74] = { 3, 15 } } }, 'the table is the old version 1 (no main-job-only marks)' },
    { { version = 2, abilities = { [74] = { 3, 15 } } }, 'the table is the old version 2 (no merit ids)' },
    { { version = 4, abilities = { [74] = { 3, 15 } } }, 'the table has an unknown version' },
    { { version = 3 }, 'the table has no abilities list' },
    { { version = 3, abilities = {} }, 'the table is empty' },
}
for _, case in ipairs(tableCases) do
    withTable(case[1])
    m = jaSpawn({ R2, jaRule('DIVINE_SEAL') }, 30)
    check(#m.gambits == 1 and isCureII(m.gambits[1]) and not hasJa(m, JA.DIVINE_SEAL),
          case[2] .. ': spell + JA set keeps only the spell rule (' .. #m.gambits .. ' gambits)')
end
withTable('missing')
s2 = loads({ R2, jaRule('DIVINE_SEAL') })
check(#s2.problems == 0, 'without the table the set still loads (the JA is left out only when the mate is called)')
local onlyJa, jaWho = jaSpawn({ jaRule('DIVINE_SEAL') }, 30)
local builtInNoTable = list(spawn(H, player(), 1, WHM, 30))
check(list(onlyJa) == builtInNoTable and last(jaWho):find('has no rule', 1, true), 'without the table a JA-only set falls back to the job rules, with a message')
local whmNoTable = spawn(H, player(), 1, WHM, 30)
local anyJa = false
for _, g in ipairs(whmNoTable.gambits) do if g.action[1] == ai.r.JA then anyJa = true end end
check(not anyJa and #whmNoTable.gambits > 0, 'U13: without the table the BUILT-IN WHM rules keep their spells but use no job ability (fail closed)')
m = jaSpawn({ R2, jaRule('PROVOKE') }, 30, WAR, 15)
check(#m.gambits == 1 and not hasJa(m, JA.PROVOKE), 'without the table even a valid sub-job ability (Provoke on WHM/WAR) is not used')
withTable({ version = 3, abilities = { [35] = { 1, 5 } } })
m = jaSpawn({ R2, jaRule('DIVINE_SEAL'), jaRule('PROVOKE') }, 30, WAR, 15)
check(#m.gambits == 2 and hasJa(m, JA.PROVOKE) and not hasJa(m, JA.DIVINE_SEAL),
      'an incomplete table (no Divine Seal row): only that JA is left out, Provoke and the spell stay')
s2 = loads({ R2, jaRule('DIVINE_SEAL') })
check(#s2.problems == 0, 'an ability missing from the table does not refuse the whole set at load')
withTable({ version = 3, abilities = { [74] = 'WHM', [35] = { 1 } } })
m = jaSpawn({ R2, jaRule('DIVINE_SEAL'), jaRule('PROVOKE') }, 30, WAR, 15)
check(#m.gambits == 1 and isCureII(m.gambits[1]), 'broken rows (not { job, level }) are treated as missing: both JAs left out')
withTable({ version = 3, abilities = { [74] = { 3, 15, main = 'yes' }, [35] = { 1, 5, merit = 'x' } } })
m = jaSpawn({ R2, jaRule('DIVINE_SEAL'), jaRule('PROVOKE') }, 30, WAR, 15)
check(#m.gambits == 1 and isCureII(m.gambits[1]), 'rows with a broken main/merit mark are treated as missing (never as "no restriction")')
withTable(nil)
local savedJa = rawget(xi, 'ja')
rawset(xi, 'ja', nil)
m = jaSpawn({ R2, jaRule('DIVINE_SEAL') }, 30)
rawset(xi, 'ja', savedJa)
check(#m.gambits == 1 and isCureII(m.gambits[1]), 'without xi.ja (ability names unknown) the JA is left out too')
withTable(nil)
m = jaSpawn({ R2, jaRule('DIVINE_SEAL') }, 30)
check(#m.gambits == 2 and hasJa(m, JA.DIVINE_SEAL), 'after the table is back (reloadJaTable) the JA is used again')

section('M1.1 main-job-only abilities (ADDTYPE_MAIN_ONLY, as charutils.cpp applies it to players)')
-- sub levels above 37 do not occur at the level-75 cap; they are used here to show the mark, not the level, decides
local function jobSpawn(job, level, sub, subLevel, rules)
    local who = player()
    useData(store({ whmSet(rules, { job = ({ [WAR] = 'WAR', [WHM] = 'WHM', [RDM] = 'RDM', [13] = 'NIN', [14] = 'DRG', [11] = 'RNG' })[job] }) }))
    who.vars['SQUAD_RS_1_' .. job], who.vars['SQUAD_RSH_1_' .. job] = 1, RS.idHash('custom.whm.cure-basics')
    return spawn(H, who, 1, job, level, sub, subLevel), who
end
local NIN, DRG, RNG = 13, 14, 11
m = jobSpawn(WHM, 40, nil, nil, { R2, jaRule('AFFLATUS_SOLACE'), jaRule('AFFLATUS_MISERY') })
check(#m.gambits == 3 and hasJa(m, JA.AFFLATUS_SOLACE) and hasJa(m, JA.AFFLATUS_MISERY), 'WHM 40 main: Afflatus Solace and Misery are used')
m = jobSpawn(WAR, 90, WHM, 45, { jaRule('PROVOKE'), jaRule('AFFLATUS_SOLACE'), jaRule('AFFLATUS_MISERY') })
check(#m.gambits == 1 and hasJa(m, JA.PROVOKE) and not hasJa(m, JA.AFFLATUS_SOLACE) and not hasJa(m, JA.AFFLATUS_MISERY),
      'WAR/WHM with sub level 45 (>= 40): Afflatus Solace/Misery are NOT used from the sub job')
m = jobSpawn(WAR, 90, RDM, 50, { jaRule('PROVOKE'), jaRule('COMPOSURE'), jaRule('CONVERT') })
check(#m.gambits == 2 and hasJa(m, JA.CONVERT) and not hasJa(m, JA.COMPOSURE), 'WAR/RDM sub 50: Convert (RDM 40) yes, Composure (main only) no')
m = jobSpawn(RDM, 50, nil, nil, { R2, jaRule('COMPOSURE') })
check(#m.gambits == 2 and hasJa(m, JA.COMPOSURE), 'RDM 50 main: Composure is used')
m = jobSpawn(WAR, 90, NIN, 45, { jaRule('PROVOKE'), jaRule('YONIN'), jaRule('INNIN') })
check(#m.gambits == 1 and not hasJa(m, JA.YONIN) and not hasJa(m, JA.INNIN), 'WAR/NIN sub 45: Yonin and Innin are not used from the sub job')
m = jobSpawn(NIN, 40, nil, nil, { jaRule('YONIN') })
check(#m.gambits == 1 and hasJa(m, JA.YONIN), 'NIN 40 main: Yonin is used')
m = jobSpawn(WAR, 75, DRG, 37, { jaRule('PROVOKE'), jaRule('SPIRIT_LINK'), jaRule('CALL_WYVERN') })
check(#m.gambits == 1 and not hasJa(m, JA.SPIRIT_LINK) and not hasJa(m, JA.CALL_WYVERN),
      'WAR/DRG 75/37 (a real level-75 case, Spirit Link needs only 25): Spirit Link and Call Wyvern are not used from the sub job')
m = jobSpawn(DRG, 30, nil, nil, { jaRule('SPIRIT_LINK'), jaRule('CALL_WYVERN') })
check(#m.gambits == 2 and hasJa(m, JA.SPIRIT_LINK) and hasJa(m, JA.CALL_WYVERN), 'DRG 30 main: Spirit Link and Call Wyvern are used')
m = jobSpawn(WAR, 90, RNG, 45, { jaRule('PROVOKE'), jaRule('VELOCITY_SHOT') })
check(#m.gambits == 1 and not hasJa(m, JA.VELOCITY_SHOT), 'WAR/RNG sub 45: Velocity Shot is not used from the sub job')
m = jobSpawn(RNG, 45, nil, nil, { jaRule('VELOCITY_SHOT') })
check(#m.gambits == 1 and hasJa(m, JA.VELOCITY_SHOT), 'RNG 45 main: Velocity Shot is used')
m = jobSpawn(WHM, 30, WAR, 15, { R2, jaRule('PROVOKE'), jaRule('BERSERK') })
check(#m.gambits == 3 and hasJa(m, JA.PROVOKE) and hasJa(m, JA.BERSERK), 'WHM/WAR 30/15: normal sub-job abilities (Provoke 5, Berserk 15) still work')
m = jobSpawn(WHM, 30, 8, 20, { R2, jaRule('WEAPON_BASH') })
check(#m.gambits == 2 and hasJa(m, JA.WEAPON_BASH), 'WHM/DRK 30/20: Weapon Bash (DRK 20) works from the sub job')
local onlyMain, mainWho = jobSpawn(WAR, 90, WHM, 45, { jaRule('AFFLATUS_SOLACE') })
check(list(onlyMain) == list(spawn(H, player(), 1, WAR, 90, WHM, 45)) and last(mainWho):find('has no rule', 1, true),
      'a set whose only rule is a sub job\'s main-only ability falls back to the job rules, with a message')
withTable(nil)
s2 = loads({ R2, jaRule('AFFLATUS_SOLACE') })
check(#s2.problems == 0, 'a main-only ability is not refused at load (the mate may have that job as its main job)')
s2 = loads({ R2, jaRule('HEALING_RUBY') })
check(#s2.list == 0 and s2.problems[1]:find('pet ability', 1, true), 'a pet ability (Healing Ruby) is refused at load: ' .. tostring(s2.problems[1]))
s2 = loads({ R2, jaRule('PET_COMMANDS') })
check(#s2.list == 0 and s2.problems[1]:find('pet ability', 1, true), 'the pet command menu entry is refused at load')

-- ================================================================= U13: one set of job ability rules for every path
do -- (its own block: the main chunk would pass Lua's 200-local limit)
withTable(nil)
local function owner(opts)
    local o = player()
    o.merits = opts and opts.merits or {}
    if opts and opts.job then function o:getMainJob() return opts.job end end
    if opts and opts.level then o.level = opts.level end
    return o
end
local function setSpawn(who, rules, job, level, sub, subLevel)
    useData(store({ whmSet(rules) }))
    who.vars.SQUAD_RS_1_3, who.vars.SQUAD_RSH_1_3 = 1, RS.idHash('custom.whm.cure-basics')
    return spawn(H, who, 1, job or WHM, level or 75, sub, subLevel), who
end

section('U13 merit abilities need the OWNER\'s merit (Rule Sets)')
local MARTYR_MERIT, DEVOTION_MERIT = 2176, 2178
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { R2, jaRule('MARTYR') })
check(#m.gambits == 2 and hasJa(m, JA.MARTYR), 'WHM 75, owner has the Martyr merit: Martyr is used')
m = setSpawn(owner(), { R2, jaRule('MARTYR') })
check(#m.gambits == 1 and not hasJa(m, JA.MARTYR) and isCureII(m.gambits[1]), 'owner without the merit: Martyr is left out, the spell rule stays')
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 }, job = WAR, level = 30 }), { R2, jaRule('MARTYR') })
check(hasJa(m, JA.MARTYR), 'the owner is a WAR 30 right now: their WHM merit still counts (job and level of the owner do not matter)')
m = setSpawn(owner({ job = WHM, level = 75 }), { R2, jaRule('MARTYR') })
check(not hasJa(m, JA.MARTYR), 'the owner is a WHM 75 right now but has no merit: still left out')
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { R2, jaRule('MARTYR'), jaRule('DEVOTION') })
check(hasJa(m, JA.MARTYR) and not hasJa(m, JA.DEVOTION), 'Martyr unlocked, Devotion not: only Martyr (each merit on its own)')
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1, [DEVOTION_MERIT] = 3 } }), { R2, jaRule('MARTYR'), jaRule('DEVOTION') })
check(hasJa(m, JA.MARTYR) and hasJa(m, JA.DEVOTION), 'both unlocked (any number of upgrades): both used')
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { R2, jaRule('MARTYR') }, WHM, 74)
check(not hasJa(m, JA.MARTYR), 'the merit does not lift the level: a WHM 74 mate still cannot use Martyr (level 75)')
local mo, moWho = setSpawn(owner(), { jaRule('MARTYR') })
check(list(mo) == list(spawn(H, player(), 1, WHM, 75)) and last(moWho):find('has no rule', 1, true),
      'a set whose only rule is a locked merit ability falls back to the job rules, with a message')
local ordinary = setSpawn(owner(), { R2, jaRule('DIVINE_SEAL') })
check(hasJa(ordinary, JA.DIVINE_SEAL), 'an ordinary ability (Divine Seal) needs no merit and no merit check')

section('U13 fail closed without SquadOwnerMerit (server not rebuilt) or a broken one')
SquadOwnerMerit = nil
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { R2, jaRule('MARTYR'), jaRule('DIVINE_SEAL') })
check(not hasJa(m, JA.MARTYR) and hasJa(m, JA.DIVINE_SEAL) and #m.gambits == 2,
      'no SquadOwnerMerit: Martyr is left out even with the merit; Divine Seal and the spell stay')
mo, moWho = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { jaRule('MARTYR') })
check(list(mo) == list(spawn(H, player(), 1, WHM, 75)) and last(moWho):find('has no rule', 1, true), 'and a Martyr-only set falls back, with a message')
SquadOwnerMerit = function() error('boom') end
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { R2, jaRule('MARTYR') })
check(not hasJa(m, JA.MARTYR), 'a SquadOwnerMerit that fails: left out')
SquadOwnerMerit = function() return 'lots' end
m = setSpawn(owner({ merits = { [MARTYR_MERIT] = 1 } }), { R2, jaRule('MARTYR') })
check(not hasJa(m, JA.MARTYR), 'a SquadOwnerMerit that returns no number: left out')
SquadOwnerMerit = ownerMeritMock

section('U13 the same rules for launcher-edited job rules and built-in rules')
local launcherMartyr = { version = 1, jobs = { WHM = { ja = { { target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', 'MARTYR' } },
                                                              { target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', 'PROVOKE' } },
                                                              { target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', 'DIVINE_SEAL' } } } } } }
H.setRules(launcherMartyr)
local lo = owner()
m = spawn(H, lo, 1, WHM, 75)
check(not hasJa(m, JA.MARTYR) and hasJa(m, JA.DIVINE_SEAL), 'launcher rule MARTYR, owner without the merit: left out (same as a Rule Set); Divine Seal kept')
check(not hasJa(m, JA.PROVOKE), 'launcher rule PROVOKE on a plain WHM: left out (not its job) - a correction, it was added before')
lo.merits[MARTYR_MERIT] = 1
m = spawn(H, lo, 1, WHM, 75)
check(hasJa(m, JA.MARTYR), 'with the owner\'s merit the launcher rule MARTYR is used')
m = spawn(H, owner(), 1, WHM, 75, WAR, 37)
check(hasJa(m, JA.PROVOKE), 'launcher rule PROVOKE on WHM/WAR 75/37: used (sub job ability)')
H.setRules({ version = 1, jobs = {} })

section('U13 built-in rules for every job and level vs the unchanged squad.lua (only the documented corrections)')
local DRG = 14
local function multiset(t)
    local out = {}
    for _, g in ipairs(t.gambits) do
        local k = string.format('%s|%s|%s', tostring(g.target), serialize(g.condition), serialize(g.action))
        out[k] = (out[k] or 0) + 1
    end
    return out
end
local function expectedRemoval(g, job, level, sub, subLevel)
    if g.action[1] ~= ai.r.JA then return false end
    local id = g.action[3]
    if id == JA.JUMP then return (job == DRG and level < 10) or (sub == DRG and subLevel < 10 and job ~= DRG) end
    if id == JA.YONIN then return sub == 13 and job ~= 13 and subLevel >= 40 end
    return false
end
local combos, compared, unexpected, removedJump, removedYonin, errors = 0, 0, {}, 0, 0, 0
local levels = { 1, 5, 9, 10, 15, 20, 25, 30, 37, 40, 45, 50, 60, 75 }
for job = 1, 18 do
    for _, level in ipairs(levels) do
        for sub = 0, 18 do
            if sub ~= job then
                local subLevels = sub == 0 and { 0 } or { math.floor(level / 2) }
                if sub == 13 and level == 75 then subLevels[#subLevels + 1] = 45 end -- above the cap: shows the Yonin mark
                for _, subLevel in ipairs(subLevels) do
                    combos = combos + 1
                    local okNew, now = pcall(spawn, H, owner(), 1, job, level, sub ~= 0 and sub or nil, subLevel)
                    local okOld, was = pcall(spawn, HO, owner(), 1, job, level, sub ~= 0 and sub or nil, subLevel)
                    if okNew and okOld then
                        compared = compared + 1
                        local a, b = multiset(now), multiset(was)
                        for k, n in pairs(a) do
                            if (b[k] or 0) < n then unexpected[#unexpected + 1] = string.format('%d/%d %d/%d added %s', job, level, sub, subLevel, k) end
                        end
                        for _, g in ipairs(was.gambits) do
                            local k = string.format('%s|%s|%s', tostring(g.target), serialize(g.condition), serialize(g.action))
                            if (a[k] or 0) > 0 then
                                a[k] = a[k] - 1
                            elseif expectedRemoval(g, job, level, sub, subLevel) then
                                if g.action[3] == JA.JUMP then removedJump = removedJump + 1 else removedYonin = removedYonin + 1 end
                            else
                                unexpected[#unexpected + 1] = string.format('%d/%d %d/%d removed %s', job, level, sub, subLevel, k)
                            end
                        end
                    elseif okNew ~= okOld then
                        unexpected[#unexpected + 1] = string.format('%d/%d %d/%d: one version failed (%s / %s)', job, level, sub, subLevel, tostring(now), tostring(was))
                    else
                        errors = errors + 1
                    end
                end
            end
        end
    end
end
check(#unexpected == 0, string.format('built-in rules: %d combinations compared (%d of %d; %d fail in both versions), no change except the documented ones%s',
      compared, compared, combos, errors, #unexpected > 0 and (': ' .. table.concat(unexpected, ' ; ', 1, math.min(5, #unexpected))) or ''))
io.write(string.format('  (built-in sweep: %d combinations, %d compared, %d fail in both versions, Jump removed %d, Yonin removed %d)\n',
         combos, compared, errors, removedJump, removedYonin))
check(compared > 4000, 'the sweep really compared the built-in rules (' .. compared .. ' combinations)')
check(removedJump > 0, 'DRG Jump is removed below level 10 (main job, and DRG sub job below sub level 10): ' .. removedJump .. ' cases')
check(removedYonin > 0, 'Yonin is removed from a NIN sub job at sub level 45 (main-job-only): ' .. removedYonin .. ' case(s)')
local drg10 = spawn(H, owner(), 1, DRG, 10)
check(hasJa(drg10, JA.JUMP), 'DRG 10: Jump is used (the SQL level)')
local drg9 = spawn(H, owner(), 1, DRG, 9)
check(not hasJa(drg9, JA.JUMP) and hasJa(spawn(HO, owner(), 1, DRG, 9), JA.JUMP), 'DRG 9: Jump is no longer used (before: used from level 1)')
check(hasJa(spawn(H, owner(), 1, 13, 40), JA.YONIN), 'NIN 40 main: Yonin still used')

section('U13 bots are unchanged (xi.squad.profileFor has no player owner)')
local function profileList(fn, job, level, sub, subLevel)
    local out = {}
    for _, g in ipairs(fn(job, level, sub, subLevel)) do out[#out + 1] = string.format('%s|%s|%s', tostring(g.target), serialize(g.condition), serialize(g.action)) end
    return table.concat(out, '\n')
end
local botDiff, botCases = 0, 0
for job = 1, 18 do
    for _, level in ipairs({ 1, 9, 30, 50, 75 }) do
        for _, sub in ipairs({ 0, 1, 3, 13, 14 }) do
            if sub ~= job then
                botCases = botCases + 1
                local subLevel = sub == 0 and 0 or math.floor(level / 2)
                if profileList(PROFILE_NEW, job, level, sub, subLevel) ~= profileList(PROFILE_OLD, job, level, sub, subLevel) then botDiff = botDiff + 1 end
            end
        end
    end
end
io.write(string.format('  (bot profiles compared: %d, different: %d)\n', botCases, botDiff))
check(botDiff == 0, string.format('bot profiles identical to the unchanged squad.lua in all %d cases (DRG 1 still lists Jump: the server checks bots)', botCases))
H.setRules(launcherMartyr); HO.setRules(launcherMartyr)
check(profileList(PROFILE_NEW, WHM, 75, 0, 0) == profileList(PROFILE_OLD, WHM, 75, 0, 0) and profileList(PROFILE_NEW, WHM, 75, 0, 0):find(tostring(JA.MARTYR), 1, true),
      'a launcher rule MARTYR is still in a bot\'s profile as before (the server refuses it for a bot without merits)')
H.setRules({ version = 1, jobs = {} }); HO.setRules({ version = 1, jobs = {} })

section('U13 fail closed without squad_ability_rules.lua')
local savedAr = package.preload[ABILITY_RULES_MODULE]
local savedLoaded = package.loaded[ABILITY_RULES_MODULE]
package.preload[ABILITY_RULES_MODULE], package.loaded[ABILITY_RULES_MODULE] = nil, nil
local noRules = spawn(H, owner(), 1, WHM, 30)
anyJa = false
for _, g in ipairs(noRules.gambits) do if g.action[1] == ai.r.JA then anyJa = true end end
check(not anyJa and #noRules.gambits > 0, 'module missing: a player\'s squad mate uses no job abilities (spells stay)')
check(profileList(PROFILE_NEW, WHM, 30, 0, 0) == profileList(PROFILE_OLD, WHM, 30, 0, 0), 'module missing: bot profiles unchanged')
package.preload[ABILITY_RULES_MODULE], package.loaded[ABILITY_RULES_MODULE] = savedAr, savedLoaded
end

section('M1.1 the job ability table (squad_ja_jobs_data.lua from sql/abilities.sql)')
local jt = dofile(JA_FILE)
local n = 0
for _ in pairs(jt.abilities) do n = n + 1 end
check(jt.version == 3 and n >= 600, 'the table loads, version 3 (' .. n .. ' abilities)')
local mainOnly = {}
for id, row in pairs(jt.abilities) do if row.main then mainOnly[#mainOnly + 1] = id end end
check(#mainOnly == 13, 'thirteen abilities are marked main-job-only in sql/abilities.sql (' .. #mainOnly .. ')')
local want = { 'AFFLATUS_SOLACE', 'AFFLATUS_MISERY', 'COMPOSURE', 'YONIN', 'INNIN', 'SPIRIT_LINK', 'CALL_WYVERN', 'VELOCITY_SHOT' }
local missingMarks = {}
for _, name in ipairs(want) do if not jt.abilities[JA[name]].main then missingMarks[#missingMarks + 1] = name end end
check(#missingMarks == 0, 'the main-only examples are all marked: ' .. table.concat(missingMarks, ', '))
check(not jt.abilities[35].main and not jt.abilities[31].main and not jt.abilities[83].main, 'Provoke, Berserk and Convert are not main-only')
local meritRows = 0
for _, row in pairs(jt.abilities) do if row.merit then meritRows = meritRows + 1 end end
check(meritRows == 45, 'U13: 45 rows carry a merit id (ADDTYPE_MERIT; 29 of them squad jobs at level 75): ' .. meritRows)
check(jt.abilities[JA.MARTYR].merit == 2176 and jt.abilities[JA.DEVOTION].merit == 2178, 'U13: Martyr = merit 2176, Devotion = merit 2178')
check(jt.abilities[JA.SIC].merit == nil and jt.abilities[JA.READY].merit == nil, 'U13: Sic and Ready (meritModID 902, not ADDTYPE_MERIT) have no merit id')
check(jt.abilities[JA.PROVOKE].merit == nil and jt.abilities[JA.JUMP][2] == 10, 'U13: Provoke needs no merit; Jump is level 10 in the SQL')
check(jt.abilities[35][1] == 1 and jt.abilities[35][2] == 5, 'Provoke = WAR level 5')
check(jt.abilities[74][1] == 3 and jt.abilities[74][2] == 15, 'Divine Seal = WHM level 15')
check(jt.abilities[83][1] == 5 and jt.abilities[83][2] == 40, 'Convert = RDM level 40')
check(jt.abilities[16].sp and jt.abilities[18].sp and not jt.abilities[31].sp, 'two-hours are marked (Mighty Strikes, Benediction), Berserk is not')

section('nothing changes without a chosen set')
p.vars.SQUAD_RS_1_3 = nil
local cases = { { WHM, 30 }, { WHM, 30, BLM, 15 }, { RDM, 40 }, { WAR, 50, WHM, 25 }, { BLM, 60 } }
if HO then
    for _, c in ipairs(cases) do
        local now = spawn(H, p, 1, c[1], c[2], c[3], c[4])
        local before = spawn(HO, p, 1, c[1], c[2], c[3], c[4])
        check(list(now) == list(before) and #now.gambits > 0,
              string.format('job %d/%s: the same gambits as the unchanged squad.lua (%d)', c[1], tostring(c[3] or '-'), #now.gambits))
    end
    p.vars.SQUAD_AI_1 = 32
    check(list(spawn(H, p, 1, WHM, 30)) == list(spawn(HO, p, 1, WHM, 30)), 'healer/conserve without a set: identical to the unchanged squad.lua')
    p.vars.SQUAD_AI_1 = nil
else
    io.write('(skipped: pass the unchanged squad.lua as the 5th argument to compare)\n')
end
package.loaded[RULESETS_MODULE] = nil
local savedPreload = package.preload[RULESETS_MODULE]
package.preload[RULESETS_MODULE] = nil
p.vars.SQUAD_RS_1_3 = 1
local noModule = spawn(H, p, 1, WHM, 30)
check(#noModule.gambits == builtInWhm, 'without squad_rulesets.lua at all, even a stored choice falls back to the built-in rules')
package.preload[RULESETS_MODULE] = savedPreload

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
