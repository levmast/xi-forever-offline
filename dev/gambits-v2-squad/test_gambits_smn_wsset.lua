-- F12 (WS gear set) + F13 (player-like Summoner): stand-in tests, no game, no server, no Ashita.
--   luajit test_gambits_smn_wsset.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                     <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work> <server>
-- Server side: squad_summoner.lua (paid summons, switches, the player's Blood Pact check from the REAL
-- scripts/globals/job_utils/summoner.lua, retries, rest, manual orders, reservations, the planner) and squad_wsset.lua
-- (storage and the equip rules), both through gambits_squad.lua's new requests too. Addon side: squad_editor.lua's
-- parsers and the Summoner / WS gear set sections drawn with a stand-in ImGui. Nothing is written outside the work folder.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER, 'usage: test_gambits_smn_wsset.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end

-- ---------------------------------------------------------------- the server world
dofile(GAMBITS)
xi = rawget(_G, 'xi') or {}
dofile(JA_ENUM)
xi.objType = { PC = 1, TRUST = 2 }
xi.job = { SMN = 15, WAR = 1, WHM = 3 }
xi.petId = { CARBUNCLE = 8, FENRIR = 9, IFRIT = 10, TITAN = 11, LEVIATHAN = 12, GARUDA = 13, SHIVA = 14, RAMUH = 15 }
xi.effect = { HASTE = 33, PROTECT = 40, ASTRAL_FLOW = 55, APOGEE = 583, AVATARS_FAVOR = 431, SHINING_RUBY = 154, BLINK = 36,
              STONESKIN = 37, WARCRY = 68, SLOW = 13, ICE_SPIKES = 35, ENTHUNDER = 96, SHOCK_SPIKES = 38, ACCURACY_DOWN = 146,
              ACCURACY_BOOST = 45 }
xi.mod = { REFRESH = 369, PERPETUATION_REDUCTION = 346, BP_DELAY = 357, BP_DELAY_II = 541, BLOOD_BOON = 913 }
xi.addType = { ADDTYPE_ASTRAL_FLOW = 2 }
xi.msg = { basic = { PET_CANNOT_DO_ACTION = 574, UNABLE_TO_USE_JA2 = 649 } }
xi.action = { category = { SLEEP = 30, STUN = 31, PET_MOBABILITY_FINISH = 13 } }
xi.animation = { NONE = 0, HEALING = 33 }
xi.zoneMisc = { PET = 4 }
xi.recast = { ABILITY = 1 }
xi.recastID = { BLOOD_PACT_RAGE = 173, BLOOD_PACT_WARD = 174 }
xi.settings = { map = { BLOOD_PACT_SHARED_TIMER = false } }
xi.magic = { spell = { CARBUNCLE = 296, FENRIR = 297, IFRIT = 298, TITAN = 299, LEVIATHAN = 300, GARUDA = 301, SHIVA = 302, RAMUH = 303 } }
math.randomInt = function(a, b) return b end -- (Blood Boon: no reduction unless the mod is set)

local clock = 1000
GetSystemTime = function() return clock end
local SPELL_MP = { [296] = 5, [297] = 15, [298] = 7, [299] = 7, [300] = 7, [301] = 7, [302] = 7, [303] = 7 }
GetSpell = function(id) return { getMPCost = function() return SPELL_MP[id] end } end
local AF = { [xi.jobAbility.AERIAL_BLAST] = true, [xi.jobAbility.INFERNO or -1] = true, [xi.jobAbility.SEARING_LIGHT or -1] = true }
GetAbility = function(id)
    return { getID = function() return id end, getRecast = function() return 60 end, getRecastID = function() return 174 end,
             getAddType = function() return AF[id] and 2 or 0 end }
end

-- the REAL Blood Pact check, cost and deduction (scripts/globals/job_utils/summoner.lua)
package.loaded['scripts/globals/ability'] = true
dofile(SERVER .. '/scripts/globals/job_utils/summoner.lua')
check(type(xi.job_utils.summoner.getBaseMPCost) == 'function', 'job_utils/summoner.lua exports getBaseMPCost (F13)')

-- entities
local function newPet(petId)
    local p = { petId = petId, alive = true, mobAbility = true, used = {}, action = 0 }
    function p:getPetID() return self.petId end
    function p:isAlive() return self.alive end
    function p:getCurrentAction() return self.action end
    function p:setMobAbilityEnabled(b) self.mobAbility = b end
    function p:usePetAbility(id, aim) self.used[#self.used + 1] = { id = id, aim = aim } end
    function p:getMainLvl() return 75 end
    function p:getID() return 9000 + petId end
    function p:addListener(ev, name, fn) self.listeners = self.listeners or {}; self.listeners[ev] = fn end
    return p
end

local function newEntity(t)
    local e = t or {}
    e.lv = e.lv or {}
    e.cv = e.cv or {}
    e.effects = e.effects or {}
    e.mods = e.mods or {}
    e.hpp = e.hpp or 100
    function e:getID() return self.id end
    function e:getLocalVar(k) return self.lv[k] or 0 end
    function e:setLocalVar(k, v) self.lv[k] = v end
    function e:getCharVar(k) return self.cv[k] or 0 end
    function e:setCharVar(k, v) self.cv[k] = v end
    function e:hasStatusEffect(id) return self.effects[id] == true end
    function e:addStatusEffect(id) self.effects[id] = true; return true end
    function e:getHPP() return self.hpp end
    function e:isAlive() return self.dead ~= true end
    function e:getPacketName() return self.name or '?' end
    function e:getName() return self.name or '?' end
    function e:getMod(id) return self.mods[id] or 0 end
    function e:isMob() return self.mob == true end
    function e:isNM() return false end
    function e:addBaseEnmity() end
    function e:checkDistance() return 5 end
    function e:isEngaged() return self.engaged == true end
    function e:getObjType() return self.objType or 2 end
    return e
end

local function newMate(id, name, master)
    local m = newEntity({ id = id, name = name, mp = 600, maxmp = 600, lvl = 75, anim = 0, master = master, misc = true,
                          lv = { SQUAD_ID = id }, objType = 2, recasts = {} })
    function m:getMP() return self.mp end
    function m:getMaxMP() return self.maxmp end
    function m:delMP(n) local before = self.mp; self.mp = math.max(0, self.mp - math.floor(n)); return before - self.mp end
    function m:addMP(n) self.mp = math.min(self.maxmp, self.mp + n) end
    function m:getMainLvl() return self.lvl end
    function m:getMainJob() return 15 end
    function m:getPet() return self.pet end
    function m:hasPet() return self.pet ~= nil end
    function m:despawnPet() self.released = (self.released or 0) + 1; self.pet = nil end
    function m:getAnimation() return self.anim end
    function m:canUseMisc() return self.misc end
    function m:getMaster() return self.master end
    function m:getTarget() return self.target end
    function m:addRecast(_, id, t) self.recasts[id] = t end
    function m:resetRecast() end
    return m
end

local master = newEntity({ id = 1, name = 'You', objType = 1 })
master.printed = {}
function master:printToPlayer(line) self.printed[#self.printed + 1] = line end
master.party = {}
function master:getPartyWithTrusts() return self.party end
function master:isEngaged() return false end

local enemy = newEntity({ id = 500, name = 'Goblin', mob = true })

SquadHasPet = function(m) return m.pet ~= nil and m.pet.alive end
SquadSpawnPet = function(m, petId)
    if m.failSpawn or m.pet ~= nil then return false end
    m.pet = newPet(petId)
    m.summons = (m.summons or 0) + 1
    return true
end
local attacks = 0
SquadPetAttack = function() attacks = attacks + 1 end

local S = dofile(LUA_DIR .. '/squad_summoner.lua')
local function reset(m)
    S.state[m:getID()] = nil
    m.lv = { SQUAD_ID = m.lv.SQUAD_ID }
    m.pet, m.released, m.summons, m.mp, m.anim, m.misc, m.failSpawn = nil, 0, 0, m.maxmp, 0, true, nil
end
local function pactGoesOff(m)
    -- what the game does when the queued pet ability finishes on its primary target: the real onUseBloodPact, then the
    -- squad.lua override's S.onPactDone
    local u = m.pet.used[#m.pet.used]
    local action = { getPrimaryTargetID = function() return u.aim:getID() end }
    local petskill = { getID = function() return u.id end, getAddType = function() return AF[u.id] and 2 or 0 end }
    xi.job_utils.summoner.onUseBloodPact(u.aim, m.pet, petskill, m, action)
    S.onPactDone(m, u.id, clock)
end

local function hastegas(m) local k = 0; for _, u in ipairs(m.pet and m.pet.used or {}) do if u.id == xi.jobAbility.HASTEGA then k = k + 1 end end return k end
local mira = newMate(101, 'Mira', master)
local ayame = newMate(102, 'Ayame', master)
master.party = { master, mira, ayame }

-- ---------------------------------------------------------------- settings and rules codec
section('F13 settings and pact rules: stored values')
local def = S.unpackSettings(0)
check(def.engage and def.rage == 0 and def.ward == 0 and def.between == 0 and not def.idle and def.ruleSwitch and not def.stored,
    'no var = the defaults (the behaviour before F13)')
local packed = S.packSettings({ engage = false, rage = 2, ward = 1, between = 2, idle = true, ruleSwitch = false })
local back = S.unpackSettings(packed)
check(not back.engage and back.rage == 2 and back.ward == 1 and back.between == 2 and back.idle and not back.ruleSwitch and back.stored,
    'settings round trip')
check(S.packSettings({ rage = 3 }) == nil, 'an out of range mode is refused')
local hv = S.encodeRule(S.decodeRule(S.encodeRule({ on = true, pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'ANY', protect = true })))
local hr = S.decodeRule(hv)
check(hr.pact == 'HASTEGA' and hr.target == 'MASTER' and hr.cond == 'NOT_STATUS' and hr.arg == 'HASTE' and hr.argId == 33 and hr.when == 'ANY' and hr.protect,
    'a rule round trip (effect by name)')
check(S.encodeRule({ pact = 'PREDATOR_CLAWS', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE' }) == nil, 'a Rage pact must go on the enemy')
check(S.encodeRule({ pact = 'PREDATOR_CLAWS', target = 'ENEMY', cond = 'ALWAYS', when = 'IDLE' }) == nil, 'a Rage pact is for a fight only')
check(S.encodeRule({ pact = 'NOPE', target = 'ENEMY', cond = 'ALWAYS' }) == nil, 'an unknown pact is refused')
check(S.encodeRule({ pact = 'HASTEGA', target = 'MASTER', cond = 'HPP_LT', arg = 101 }) == nil, 'a percentage above 100 is refused')
local n = #S.PACT_LIST
check(n <= 127 and S.pactIndex('HASTEGA') ~= nil, 'every pact fits the 7-bit index')
check(S.setRule(master, 101, 1, { pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'ANY' }) == true
    and S.setRule(master, 101, 3, { pact = 'CLAW', target = 'ENEMY', cond = 'ALWAYS' }) == false, 'rules are added in order (no gaps)')
S.setRule(master, 101, 2, { pact = 'CLAW', target = 'ENEMY', cond = 'ALWAYS' })
check(#S.getRules(master, 101) == 2 and S.moveRule(master, 101, 2, -1) and S.getRules(master, 101)[1].pact == 'CLAW', 'move a rule up')
check(S.deleteRule(master, 101, 1) and #S.getRules(master, 101) == 1 and S.getRules(master, 101)[1].pact == 'HASTEGA', 'delete a rule; the rest move up')
S.deleteRule(master, 101, 1)

-- ---------------------------------------------------------------- summons
section('F13 summons: paid, eligibility before release, no repeat summon')
reset(mira)
mira.mp = 7
check(S.summon(mira, 'GARUDA', clock, nil, 0) == true and mira.mp == 0 and mira.pet.petId == 13, 'exactly enough MP: summoned, 7 MP charged')
check(mira.pet.mobAbility == false, 'the avatar\'s own monster TP moves are turned off')
reset(mira)
mira.mp = 6
local okS, why = S.summon(mira, 'GARUDA', clock, nil, 0)
check(not okS and mira.mp == 6 and mira.pet == nil and why:find('MP'), 'one MP short: no summon, nothing charged')
reset(mira)
mira.failSpawn = true
check(not S.summon(mira, 'GARUDA', clock, nil, 0) and mira.mp == 600, 'a failed summon charges nothing')
reset(mira)
mira.misc = false
check(not S.summon(mira, 'GARUDA', clock, nil, 0) and mira.mp == 600, 'a zone without pets: refused')
reset(mira)
mira.anim = xi.animation.HEALING
check(not S.summon(mira, 'GARUDA', clock, nil, 0), 'resting: refused')
reset(mira)
mira.lvl = 59
check(not S.summon(mira, 'FENRIR', clock, nil, 0), 'Fenrir below level 60: refused')
mira.lvl = 75
reset(mira)
S.summon(mira, 'IFRIT', clock, nil, 0)
mira.mp = 6
local okW = S.switchTo(mira, 'GARUDA', clock, nil, 'test', 0)
check(not okW and mira.pet.petId == 10 and (mira.released or 0) == 0, 'a switch it cannot pay for never releases the current avatar')
mira.mp = 600
check(S.switchTo(mira, 'GARUDA', clock, nil, 'test', 0) and mira.pet.petId == 13 and mira.released == 1 and mira.mp == 593, 'a paid switch')
local before = mira.summons
check(S.switchTo(mira, 'GARUDA', clock, nil, 'test', 0) and mira.summons == before and mira.released == 1, 'switching to the avatar that is out does nothing')
local msg = S.setChoice(master, 101, 'Mira', 5, mira, nil, true)
check(msg:find('already') and mira.released == 1 and mira.summons == before, 'naming the avatar that is out (chat order) does not release it')

-- ---------------------------------------------------------------- Blood Pact boundaries (the player's check)
section('F13 Blood Pacts: exactly enough MP, one short, Astral Flow, retries, recast')
reset(mira)
master.cv = {}
S.setSettings(master, 101, { ward = 1 }) -- (Ward off here: only Rage and Astral Flow are looked at)
S.summon(mira, 'GARUDA', clock, nil, 0)
enemy.dead = false
mira.target = enemy
mira.mp = 164 -- Predator Claws' base cost
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
local used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.PREDATOR_CLAWS and used.aim == enemy, 'exactly 164 MP: Predator Claws is dispatched')
pactGoesOff(mira)
check(mira.mp == 0, 'the real onUseBloodPact charges the full 164 MP')
check(mira:getLocalVar('SQUAD_BP_NEXT') == clock + 60, 'the recast (60 s) starts only when it went off')
reset(mira)
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.mp = 163
clock = clock + 1
local usedBefore = #mira.pet.used
S.combatTick(mira, master, enemy, clock, nil, nil)
check(#mira.pet.used == usedBefore and mira.mp == 163, 'one MP short: no Predator Claws, nothing spent (before F13 it fired from 98 MP)')
check(mira:getLocalVar('SQUAD_BP_NEXT') == clock + 5, 'a refused Rage tries again after 5 s, not 60')
check(attacks > 0, 'the avatar is still sent at the enemy (normal attacks never wait for Rage)')
-- a pact that was dispatched but never went off: no MP, a short bounded retry
reset(mira)
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.mp = 600
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
local mpAfterDispatch = mira.mp
check(mira:getLocalVar('SQUAD_BP_NEXT') == clock + S.PENDING_SECONDS, 'while on its way: only a short hold, not the recast')
clock = clock + S.PENDING_SECONDS
S.combatTick(mira, master, enemy, clock, nil, nil)
check(mira.mp == mpAfterDispatch and mira:getLocalVar('SQUAD_BP_NEXT') == clock + 5, 'it did not go off: no MP lost, again in 5 s')
-- BP Delay gear shortens the recast, at most 30 s (15 + 15)
mira.mods[xi.mod.BP_DELAY] = 20
mira.mods[xi.mod.BP_DELAY_II] = 20
check(S.recastOf(mira, xi.jobAbility.HASTEGA) == 30, 'BP Delay I and II: 15 + 15 at most')
mira.mods[xi.mod.BP_DELAY] = 5
mira.mods[xi.mod.BP_DELAY_II] = 0
check(S.recastOf(mira, xi.jobAbility.HASTEGA) == 55, 'BP Delay 5: a 55 s recast')
mira.mods = {}
-- Astral Flow: the player's rule (Astral Flow on, MP >= level x 2 = 150)
reset(mira)
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.lv.SQUAD_BP_NEXT, mira.lv.SQUAD_WARD_NEXT = clock + 100, clock + 100
mira.effects[xi.effect.ASTRAL_FLOW] = true
mira.mp = 149
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
check(#mira.pet.used == 0 and mira:getLocalVar('SMN_AF_USED') == 0, 'Astral Flow with 149 MP: no Aerial Blast')
mira.mp = 150
S.combatTick(mira, master, enemy, clock, nil, nil)
used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.AERIAL_BLAST and mira:getLocalVar('SMN_AF_USED') == 1, 'Astral Flow with 150 MP: Aerial Blast')
mira.effects[xi.effect.ASTRAL_FLOW] = nil
reset(mira)
S.summon(mira, 'GARUDA', clock, nil, 0)
check(S.chooseWard(mira, mira.pet, master, enemy, 75, 'GARUDA', clock, false) ~= 'AERIAL_BLAST', 'no Aerial Blast without Astral Flow')

-- ---------------------------------------------------------------- (r4) waiting for the avatar
section('F13 r4: a pact waits while the avatar is busy or out of reach (no attempt lost)')
check(S.pactReach('CLAW') == 3 and S.pactReach('ROCK_THROW') == 12 and S.pactReach('HASTEGA') == 20 and S.pactReach('AERIAL_BLAST') == 5,
    'the reach of a pact (pet_skills.sql distances)')
reset(mira)
master.cv = {}
S.setSettings(master, 101, { ward = 1 })
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.mp = 600
mira.pet.action = 13 -- (still finishing another pact)
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
check(#mira.pet.used == 0 and S.state[mira:getID()].sent == nil, 'the avatar is busy: no pact sent, nothing counted as on its way')
check(mira:getLocalVar('SQUAD_BP_NEXT') == clock + 1, 'busy: looked at again on the next tick, not after 5 s')
mira.pet.action = 1
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.PREDATOR_CLAWS, 'ready again (attacking): the Rage pact is sent')
reset(mira)
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.mp = 600
local far = 10
function mira.pet:checkDistance() return far end
attacks = 0
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
check(#mira.pet.used == 0 and S.state[mira:getID()].sent == nil, 'the avatar is 10 yalms from the enemy (reach 3): Predator Claws waits')
check(attacks >= 1, 'the avatar is sent in at the enemy')
far = 3.5
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.PREDATOR_CLAWS and used.aim == enemy, 'in reach (3.5 yalms, the margin): the pact is sent')
reset(mira)
master.lv, master.effects = {}, {}
S.setSettings(master, 101, {})
S.setRule(master, 101, 1, { pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'ANY', protect = true })
S.summon(mira, 'GARUDA', clock, nil, 0)
function mira.pet:checkDistance() return 10 end
mira.lv.SQUAD_WARD_NEXT, mira.lv.SQUAD_BP_NEXT = 0, clock + 100
mira.mp = 600
clock = clock + 100
S.combatTick(mira, master, enemy, clock, nil, nil)
used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.HASTEGA and used.aim == master, 'Hastega on you 10 yalms from the avatar (reach 20): sent at once')
S.deleteRule(master, 101, 1)
master.cv, master.lv, master.effects = {}, {}, {}

-- ---------------------------------------------------------------- (B8, 2026-11-27) the avatar choice
section('B8: a fixed avatar stays fixed; a rule may borrow another and it comes back; no silent random pick; Auto')
do
    local IX = {}
    for i, n in ipairs(S.AVATARS) do IX[n] = i end
    local function choose(idx) master.cv[S.choiceVar(101)] = idx end
    local function petName(m) return m.pet and S.nameOfPet(m.pet.petId) or nil end
    local defaultGaruda = function() return xi.petId.GARUDA end -- (what the random default pick may say)

    -- fixed Shiva, no rules: Shiva, never the default pick
    reset(mira)
    master.cv, master.printed = {}, {}
    choose(IX.SHIVA)
    clock = clock + 100
    S.combatTick(mira, master, enemy, clock, nil, defaultGaruda)
    check(petName(mira) == 'SHIVA', 'fixed Shiva: Shiva is summoned (the default pick would have been Garuda)')

    -- Rules may switch OFF: a Garuda rule never moves it
    reset(mira)
    master.cv = {}
    choose(IX.SHIVA)
    S.setSettings(master, 101, { ruleSwitch = false })
    S.setRule(master, 101, 1, { pact = 'CLAW', target = 'ENEMY', cond = 'ALWAYS', when = 'COMBAT' })
    mira.mp = 600
    for t = 1, 3 do S.combatTick(mira, master, enemy, clock + t, nil, defaultGaruda) end
    check(petName(mira) == 'SHIVA' and (mira.released or 0) == 0, 'rules may not switch: Shiva stays, the Claw rule waits')

    -- Rules may switch ON: the rule borrows Garuda, it stays while the rule still fits, then Shiva comes back
    reset(mira)
    master.cv = {}
    choose(IX.SHIVA)
    S.setSettings(master, 101, { ruleSwitch = true })
    S.setRule(master, 101, 1, { pact = 'CLAW', target = 'ENEMY', cond = 'MY_MPP_GTE', arg = '50', when = 'COMBAT' })
    mira.mp = 600
    clock = clock + 100
    S.combatTick(mira, master, enemy, clock, nil, defaultGaruda) -- (no avatar: the Claw intent calls Garuda itself)
    check(petName(mira) == 'GARUDA', 'the Claw rule calls Garuda for its pact')
    S.combatTick(mira, master, enemy, clock + 1, nil, nil)
    local used = mira.pet.used[#mira.pet.used]
    check(used and used.id == xi.jobAbility.CLAW, 'Claw is sent')
    pactGoesOff(mira)
    S.combatTick(mira, master, enemy, clock + S.SWAP_SECONDS + 2, nil, nil)
    check(petName(mira) == 'GARUDA', 'MP still above 50%: the Claw rule still fits, Garuda stays (no switching back and forth)')
    mira.mp = 200 -- (33%: the rule no longer fits)
    S.combatTick(mira, master, enemy, clock + S.SWAP_SECONDS + 3, nil, nil)
    check(petName(mira) == 'SHIVA', 'the rule is done and no longer fits: back to Shiva (paid)')
    local swapAt = mira:getLocalVar('SMN_SWAP_NEXT')
    check(swapAt > clock, 'the switch back starts the switch hold too')

    -- the switch hold: no switch back inside it
    reset(mira)
    choose(IX.SHIVA)
    S.summon(mira, 'GARUDA', clock, nil, 0)
    mira.lv.SMN_SWAP_NEXT = clock + 30
    S.combatTick(mira, master, enemy, clock + 1, nil, nil)
    check(petName(mira) == 'GARUDA', 'inside the switch hold: no switch back yet')

    -- a manual order wins: while it holds, nothing switches back
    reset(mira)
    choose(IX.SHIVA)
    S.summon(mira, 'GARUDA', clock, nil, 0)
    mira.lv.SMN_MANUAL_UNTIL = clock + 300
    S.combatTick(mira, master, enemy, clock + 1, nil, nil)
    check(petName(mira) == 'GARUDA', 'a manual order holds: no switch back')

    -- not enough MP for the switch back: it waits
    reset(mira)
    S.deleteRule(master, 101, 1)
    choose(IX.SHIVA)
    S.summon(mira, 'GARUDA', clock, nil, 0)
    mira.mp = 5
    S.combatTick(mira, master, enemy, clock + 1, nil, nil)
    check(petName(mira) == 'GARUDA', 'MP for Shiva missing: Garuda is not released for nothing')

    -- a fixed choice it cannot call: no random substitute, said once (not every tick)
    reset(mira)
    master.cv, master.printed = {}, {}
    choose(IX.FENRIR)
    mira.lvl = 50
    for t = 1, 3 do S.combatTick(mira, master, enemy, clock + 10 * t, nil, defaultGaruda) end
    local said = 0
    for _, line in ipairs(master.printed) do if line:find('cannot call Fenrir', 1, true) then said = said + 1 end end
    check(mira.pet == nil, 'Fenrir at level 50: no avatar (not the default pick, Garuda)')
    check(said == 1 and master.printed[1]:find('level 60', 1, true), 'said once, with the reason: ' .. tostring(master.printed[1]))
    mira.lvl = 75
    S.combatTick(mira, master, enemy, clock + 100, nil, defaultGaruda)
    check(petName(mira) == 'FENRIR', 'once it can: Fenrir')

    -- Auto (weakness): the first summon of a fight is the weakest element's avatar; neutral: the default pick
    local savedCombat, savedElement = xi.combat, xi.element
    xi.element = { FIRE = 1, ICE = 2, WIND = 3, EARTH = 4, THUNDER = 5, WATER = 6, LIGHT = 7, DARK = 8 }
    xi.combat = { damage = { magicalElementSDT = function(t, el) return (t.sdt or {})[el] or 1 end } }
    reset(mira)
    master.cv = {}
    choose(0)
    enemy.sdt = { [xi.element.WIND] = 1.5 }
    S.combatTick(mira, master, enemy, clock + 200, nil, function() return xi.petId.IFRIT end)
    check(petName(mira) == 'GARUDA' and mira.summons == 1, 'Auto, a wind-weak enemy: Garuda is the first summon (one summon, no switch after)')
    reset(mira)
    choose(0)
    enemy.sdt = nil
    S.combatTick(mira, master, enemy, clock + 300, nil, function() return xi.petId.IFRIT end)
    check(petName(mira) == 'IFRIT', 'Auto, nothing stands out: the default pick (here Ifrit), as before')
    enemy.sdt, xi.combat, xi.element = nil, savedCombat, savedElement
    master.cv, master.lv, master.effects, master.printed = {}, {}, {}, {}
end

-- ---------------------------------------------------------------- normal attacks
section('F13 normal attacks: on by default, off when set, never gated by MP or Rage')
reset(mira)
master.cv = {}
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.mp = 10
attacks = 0
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
check(attacks == 1, 'low MP, Rage unaffordable: the avatar still engages')
S.setSettings(master, 101, { engage = false })
attacks = 0
S.combatTick(mira, master, enemy, clock + 1, nil, nil)
check(attacks == 0, 'normal attacks off: the avatar is not sent')
master.cv = {}

-- ---------------------------------------------------------------- rest and between pulls
section('F13 rest: released before resting, none called while resting; between pulls')
reset(mira)
S.summon(mira, 'IFRIT', clock, nil, 0)
S.onRest(mira)
check(mira.pet == nil and mira.released == 1, 'the avatar is released when the mate starts resting')
mira.anim = xi.animation.HEALING
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
check(mira.pet == nil, 'no summon while it rests')
reset(mira)
S.setSettings(master, 101, { between = 1 })
S.summon(mira, 'IFRIT', clock, nil, 0)
mira.lv.SMN_FIGHT_AT = clock
S.idleTick(mira, master, clock + 3, nil, nil)
check(mira.pet ~= nil, 'release between pulls waits a few seconds after the fight')
S.idleTick(mira, master, clock + S.IDLE_RELEASE + 1, nil, nil)
check(mira.pet == nil, 'release between pulls: released when the fight is over')
reset(mira)
S.setSettings(master, 101, { between = 0 })
S.summon(mira, 'IFRIT', clock, nil, 0)
mira.lv.SMN_FIGHT_AT = clock
S.idleTick(mira, master, clock + 30, nil, nil)
check(mira.pet ~= nil, 'keep it out (the default): stays out between pulls')
-- (r2, DEV) a fight-only intent still pending when the fight ends must not block the release
reset(mira)
master.cv = {}
S.setSettings(master, 101, { between = 1 })
S.setRule(master, 101, 1, { pact = 'CLAW', target = 'ENEMY', cond = 'ALWAYS', when = 'COMBAT' })
S.summon(mira, 'GARUDA', clock, nil, 0)
mira.lv.SQUAD_BP_NEXT = clock + 30 -- (Claw not ready: the intent waits)
S.combatTick(mira, master, enemy, clock, nil, nil)
check(S.state[mira:getID()].intent ~= nil, 'in the fight: an intent for Claw is waiting')
S.idleTick(mira, master, clock + S.IDLE_RELEASE + 1, nil, nil)
check(S.state[mira:getID()].intent == nil and mira.pet == nil, 'after the fight: the Claw intent ends and the avatar is released between pulls')
check(mira.pet == nil and #(master.printed or {}) >= 0, '(release logged)')
S.deleteRule(master, 101, 1)
master.cv = {}
-- (r2 diagnostics) the summon puts listeners on the avatar for the pact steps
reset(mira)
S.summon(mira, 'GARUDA', clock, nil, 0)
check(mira.pet.listeners and mira.pet.listeners.WEAPONSKILL_BEFORE_USE and mira.pet.listeners.WEAPONSKILL_STATE_ENTER, 'the pact-step diagnostics are on the avatar')
master.cv = {}

-- support out of combat: only with the map server that charges upkeep, and only when it is turned on
reset(mira)
master.cv, master.lv, master.effects = {}, {}, {}
S.setRule(master, 101, 1, { pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'ANY' })
S.setSettings(master, 101, { idle = true })
clock = clock + 100
S.idleTick(mira, master, clock, nil, nil)
check(mira.pet == nil, 'support out of combat on an older map server (no upkeep charged): nothing is called')
SquadSmnEngine = function() return 1 end
S.idleTick(mira, master, clock + 1, nil, nil)
check(mira.pet and mira.pet.petId == 13 and hastegas(mira) == 1, 'support out of combat: Garuda is called and Hastega goes before the pull')
S.setSettings(master, 101, { idle = false })
reset(mira)
S.idleTick(mira, master, clock + 2, nil, nil)
check(mira.pet == nil, 'support out of combat off (the default): nothing happens between fights')
S.deleteRule(master, 101, 1)
master.cv = {}

-- ---------------------------------------------------------------- manual orders
section('F13 manual orders: an order wins for a while; release; auto with a hold')
reset(mira)
S.summon(mira, 'IFRIT', clock, nil, 0)
S.setRule(master, 101, 1, { pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'COMBAT' })
mira.lv.SQUAD_WARD_NEXT = 0
S.setChoice(master, 101, 'Mira', 2, mira, nil, true) -- "Mira Ifrit"
clock = clock + 1
S.combatTick(mira, master, enemy, clock, nil, nil)
check(mira.pet.petId == 10, 'during a manual order a rule that needs Garuda does not switch away from Ifrit')
S.orderRelease(master, mira)
check(mira.pet == nil and mira:getLocalVar('SMN_RELEASED_UNTIL') == clock + S.RELEASE_SECONDS, '"release": the avatar leaves for a minute')
S.combatTick(mira, master, enemy, clock + 10, nil, nil)
check(mira.pet == nil, 'no summon during the release')
S.setChoice(master, 101, 'Mira', nil, mira, nil, true) -- "Mira auto"
check(mira:getLocalVar('SMN_MANUAL_UNTIL') == 0 and mira:getLocalVar('SMN_SWAP_NEXT') > clock, 'auto: the order ends, with a hold so nothing switches at once')
master.cv = {}

-- ---------------------------------------------------------------- the Hastega example
section('F13 the example: "use Hastega when you lack Haste"')
reset(mira)
master.cv, master.lv, master.effects = {}, {}, {}
S.summon(mira, 'IFRIT', clock, nil, 0)
S.setRule(master, 101, 1, { pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'ANY', protect = true })
mira.lv.SQUAD_WARD_NEXT = 0
mira.mp = 600
clock = clock + 100
S.combatTick(mira, master, enemy, clock, nil, nil)
check(mira.pet and mira.pet.petId == 13 and mira.mp == 593, 'Garuda is called (paid) for Hastega')
used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.HASTEGA and used.aim == master, 'Hastega is dispatched on you as soon as Garuda is out and Ward is ready')
check(master:getLocalVar('SMN_RSV_33') == 101, 'Haste is reserved for Mira while it is on its way')
pactGoesOff(mira)
check(mira.mp == 593 - 129 and S.state[mira:getID()].intent == nil and master:getLocalVar('SMN_RSV_33') == 0,
    'it went off: 129 MP, the intent is done, the reservation is free')
attacks = 0
S.combatTick(mira, master, enemy, clock + 1, nil, nil)
check(mira.pet.petId == 13 and attacks == 1, 'Garuda stays and keeps attacking after the pact')
-- Haste from someone else first: the pending pact is cancelled
reset(mira)
master.lv, master.effects = {}, {}
S.summon(mira, 'IFRIT', clock, nil, 0)
mira.mp = 600
clock = clock + 100
mira.lv.SQUAD_WARD_NEXT = clock + 20 -- Ward in 20 s
S.combatTick(mira, master, enemy, clock, nil, nil)
local st = S.state[mira:getID()]
check(st.intent and st.intent.name == 'HASTEGA' and mira.pet.petId == 13, 'Ward in 20 s, MP covers summon + pact + upkeep: Garuda now, waits for Ward')
master.effects[33] = true -- a WHM's Haste lands
S.combatTick(mira, master, enemy, clock + 1, nil, nil)
check(st.intent == nil and hastegas(mira) == 0 and master:getLocalVar('SMN_RSV_33') == 0, 'Haste from another source: no Hastega, the reservation is freed')
-- not affordable: Ifrit stays
reset(mira)
master.lv, master.effects = {}, {}
S.summon(mira, 'IFRIT', clock, nil, 0)
mira.lv.SQUAD_WARD_NEXT = 0
mira.mp = 130 -- summon 7 + Hastega 129 = 136
clock = clock + 100
S.combatTick(mira, master, enemy, clock, nil, nil)
check(mira.pet.petId == 10 and mira.released == 0, 'cannot pay summon + Hastega: Ifrit is not released')
check(S.state[mira:getID()].intent == nil, 'the intent is given up (no switch on credit)')
-- protected MP: the default Rage does not dip into it
reset(mira)
master.lv, master.effects = {}, {}
master.effects[33] = true
S.summon(mira, 'IFRIT', clock, nil, 0)
mira.mp = 200 -- Flaming Crush 164 would leave 36 < Hastega's 129
clock = clock + 100
S.combatTick(mira, master, enemy, clock, nil, nil)
check(#mira.pet.used == 0, 'a protected Hastega rule keeps its 129 MP: no Flaming Crush that would dip below it')
mira.mp = 300
S.combatTick(mira, master, enemy, clock + 10, nil, nil)
used = mira.pet.used[#mira.pet.used]
check(used and used.id == xi.jobAbility.FLAMING_CRUSH, 'with MP to spare the default Rage still goes (no fixed reserve)')
master.cv = {}

-- ---------------------------------------------------------------- several Summoners
section('F13 several SMN mates: one Hastega attempt for one unmet buff')
reset(mira); reset(ayame)
master.cv, master.lv, master.effects = {}, {}, {}
for _, m in ipairs({ mira, ayame }) do
    S.setRule(master, m:getID(), 1, { pact = 'HASTEGA', target = 'MASTER', cond = 'NOT_STATUS', arg = 'HASTE', when = 'COMBAT' })
    S.summon(m, 'GARUDA', clock, nil, 0)
    m.lv.SQUAD_WARD_NEXT = 0
end
clock = clock + 100
S.combatTick(mira, master, enemy, clock, nil, nil)
S.combatTick(ayame, master, enemy, clock, nil, nil)
check(hastegas(mira) == 1 and hastegas(ayame) == 0, 'only the first Summoner goes for Hastega; the second sees the reservation')
-- the first one's pact never goes off: the reservation is freed, the second may take it
clock = clock + S.PENDING_SECONDS
S.combatTick(mira, master, enemy, clock, nil, nil)
check(master:getLocalVar('SMN_RSV_33') == 0 or master:getLocalVar('SMN_RSV_33') == 101, 'a pact that did not go frees its dispatch hold')
S.state[mira:getID()] = nil -- (Mira is knocked out: its intent is gone)
master.lv.SMN_RSVT_33 = clock - 1 -- (the reservation expires)
S.combatTick(ayame, master, enemy, clock + 1, nil, nil)
check(hastegas(ayame) == 1, 'after the reservation expires the second Summoner takes it')
for _, m in ipairs({ mira, ayame }) do S.deleteRule(master, m:getID(), 1) end
master.cv = {}

-- ---------------------------------------------------------------- the built-in default still works
section('F13 a mate without settings or rules: the job default, with costs')
reset(mira)
master.cv, master.lv, master.effects = {}, {}, {}
clock = clock + 100
master.hpp = 30
S.combatTick(mira, master, enemy, clock, nil, function() return xi.petId.CARBUNCLE end)
check(mira.pet ~= nil and mira.pet.petId == 8 and mira.mp == 600 - 5, 'no avatar in a fight: the default pick is summoned and paid')
used = mira.pet.used[#mira.pet.used]
check(used and (used.id == xi.jobAbility.HEALING_RUBY_II or used.id == xi.jobAbility.HEALING_RUBY), 'the job default heals you when you are low')
master.hpp = 100

-- ---------------------------------------------------------------- F12 squad_wsset.lua
section('F12 the WS gear set: storage and the equip rules')
local ITEMS = {
    [1001] = { valid = true, name = 'Ogre Mask', level = 50, jobs = 1, slot = 2 ^ 4 },          -- WAR head
    [1002] = { valid = true, name = 'Byakkos Haidate', level = 75, jobs = 1, slot = 2 ^ 7 },    -- WAR legs, Lv75
    [1003] = { valid = true, name = 'Rare Ring', level = 1, jobs = 1, slot = 2 ^ 13 + 2 ^ 14 }, -- ring1/ring2
    [1004] = { valid = true, name = 'Mage Hat', level = 10, jobs = 4, slot = 2 ^ 4 },          -- WHM only
    [1005] = { valid = true, name = 'Great Sword', level = 1, jobs = 1, slot = 1 },             -- main
    [1006] = { valid = true, name = 'Given Belt', level = 1, jobs = 1, slot = 2 ^ 10 },
}
local RARE = { [1003] = true }
GetSquadItemInfo = function(id) return ITEMS[id] or { valid = false } end
local unlocks = { [1001] = true, [1002] = true, [1003] = true, [1004] = true, [1005] = true }
GetSquadUnlocks = function() return unlocks end
squadAllGear = function() return false end
squadGearConflict = function(worn, slot, itemId, info)
    if RARE[itemId] then
        for s = 0, 15 do if s ~= slot and worn[s] == itemId then return info.name .. ' is Rare: it is already worn in another slot' end end
    end
end
local pushed = nil
SquadSetWsSet = function(_, set) pushed = set; return 0 end
SquadWsSetEngine = function() return 1 end
xi.squad = { requireUnlock = true }
local Wx = dofile(LUA_DIR .. '/squad_wsset.lua')
local war = { id = 201, name = 'Dag', mjob = 1, equip = { [1] = { [0] = 1005, [13] = 1003 } } }
local p2 = newEntity({ id = 2, objType = 1 })
check(Wx.setPiece(p2, war, 1, 4, 1001, 75) == true and Wx.get(p2, 201, 1)[4] == 1001, 'a head piece is stored (one char var per slot)')
local okP, whyP = Wx.setPiece(p2, war, 1, 0, 1005, 75)
check(not okP and whyP:find('armor'), 'a weapon slot is refused')
okP, whyP = Wx.setPiece(p2, war, 1, 4, 1004, 75)
check(not okP and whyP:find('job'), 'another job\'s item is refused')
okP, whyP = Wx.setPiece(p2, war, 1, 7, 1002, 60)
check(not okP and whyP:find('level 75'), 'an item above the mate\'s level is refused')
okP, whyP = Wx.setPiece(p2, war, 1, 10, 1006, 75)
check(not okP and whyP:find('given'), 'gear not given to the squad is refused')
okP, whyP = Wx.setPiece(p2, war, 1, 14, 1003, 75)
check(not okP and whyP:find('Rare'), 'a Rare ring the outfit already wears in ring1 is refused for ring2')
okP, whyP = Wx.setPiece(p2, war, 1, 5, 1001, 75)
check(not okP and whyP:find('slot'), 'an item in a slot it does not fit is refused')
check(Wx.setPiece(p2, war, 1, 7, 1002, 75) == true, 'Lv75 legs for a level 75 mate')
-- the call: Level Sync to 60 leaves the Lv75 legs out, the head stays
local trust = newEntity({ id = 7001, name = 'Dag', objType = 2 })
function trust:getMainJob() return 1 end
function trust:getMainLvl() return 60 end
p2.printed = {}
function p2:printToPlayer(l) self.printed[#self.printed + 1] = l end
pushed = nil
Wx.onSpawn(p2, trust, war, { [0] = 1005, [13] = 1003 }, 60)
check(pushed and pushed[4] == 1001 and pushed[7] == nil, 'Level Sync 60: the Lv75 legs are left out, the head is used')
check(#p2.printed == 1 and p2.printed[1]:find('legs') ~= nil, 'the player is told once which piece is left out and why: ' .. tostring(p2.printed[1]) .. ' #' .. #p2.printed)
pushed = nil
Wx.onSpawn(p2, trust, war, { [0] = 1005, [13] = 1003 }, 75)
check(pushed and pushed[4] == 1001 and pushed[7] == 1002, 'at level 75 both pieces are used')
Wx.clear(p2, 201, 1)
check(Wx.count(Wx.get(p2, 201, 1)) == 0, 'clear: no set')
pushed = nil
Wx.liveApply(p2, war, trust)
check(pushed and next(pushed) == nil, 'a cleared set on a called mate: an empty set is handed to the map server')
local choices = Wx.choices(p2, 1, 4, 75, 40)
check(#choices == 1 and choices[1].id == 1001, 'the head choices: given gear the job can wear at its level')

-- ---------------------------------------------------------------- the !gsq requests and the editor's parsers
section('F12/F13 !gsq requests <-> the editor')
package.preload['modules/custom/lua/squad_summoner'] = function() return S end
package.preload['modules/custom/lua/squad_wsset'] = function() return Wx end
package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end
local St = require('modules/custom/lua/squad_rulesets_store')
St.PATH = WORK .. package.config:sub(1, 1) .. 'squad_rulesets_data_f12f13.lua'
local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local out = {}
local gp = newEntity({ id = 3, objType = 1 })
function gp:printToPlayer(line) out[#out + 1] = line end
local smnOut = newMate(301, 'Kiri', gp)
gp.party = { gp, smnOut }
function gp:getPartyWithTrusts() return self.party end
GetSquad = function()
    return { { id = 301, slot = 1, name = 'Kiri', mjob = 15, sjob = 0, jobs = { [15] = { level = 75 } }, equip = {} },
             { id = 201, slot = 2, name = 'Dag', mjob = 1, sjob = 0, jobs = { [1] = { level = 75 } }, equip = war.equip } }
end
xi.squad.levelsFor = function(mate) return mate.jobs[mate.mjob].level, 0, 0 end
local function run(line) out = {}; G.handle(gp, line); return out end
local function fields(line) return G.splitPlain(line, '|') end
local caps = fields(run('hello 1')[1])
check((caps[8] or ''):find('smn') and (caps[8] or ''):find('wsset'), 'hello carries the capabilities smn and wsset')

local Ed = dofile(ADDON_DIR .. '/squad_editor.lua')
local function items(lines)
    local list = {}
    for _, l in ipairs(lines) do
        local f = fields(l)
        if f[3] ~= 'end' then list[#list + 1] = f end
    end
    return list, fields(lines[#lines])
end
local lines = run('smg 2 1')
local its, endF = items(lines)
local d = Ed.parse_smn(its)
check(d and d.slot == 1 and d.avatar == 0 and d.engage and d.out and tonumber(endF[4]) == #its, 'smg: the editor reads the settings; end counts every line')
for _, l in ipairs(lines) do check(#l <= 140, 'every answer line fits one chat line') end
lines = run('sms 3 1 5 1 0 2 1 1 1')
its = items(lines)
d = Ed.parse_smn(its)
check(d and d.avatar == 5 and d.ward == 2 and d.between == 1 and d.idle, 'sms: settings saved and read back')
check(smnOut.pet and smnOut.pet.petId == 13, 'a called mate takes the Gambits avatar setting at once (paid)')
lines = run('smr 4 1 1 1 HASTEGA MASTER NOT_STATUS HASTE ANY 1')
its = items(lines)
d = Ed.parse_smn(its)
check(d and #d.rules == 1 and d.rules[1].pact == 'HASTEGA' and d.rules[1].arg == 'HASTE' and d.rules[1].protect, 'smr: the rule is saved and read back')
check(Ed.smn_rule_text(d.rules[1]):find('Hastega') ~= nil, 'the editor shows the rule as a readable line')
lines = run('smr 5 1 2 1 PREDATOR_CLAWS MASTER ALWAYS 0 COMBAT 0')
check(fields(lines[1])[3] == 'err', 'smr: a Rage pact on you is refused by the server')
lines = run('smg 6 2')
check(fields(lines[1])[3] == 'err' and fields(lines[1])[4] == 'notsmn', 'smg: a mate that is not a Summoner is refused')
lines = run('smp 7 1')
its = items(lines)
local cat = Ed.parse_smp(its)
local hasHastega = false
for _, e in ipairs(cat or {}) do hasHastega = hasHastega or (e.name == 'HASTEGA' and e.avatar == 'GARUDA' and e.usable) end
check(cat and hasHastega, 'smp: the pact list the editor offers (Hastega usable at 75)')
for _, l in ipairs(lines) do check(#l <= 140, 'every pact list line fits one chat line') end
lines = run('smd 8 1 1')
d = Ed.parse_smn((items(lines)))
check(d and #d.rules == 0, 'smd: the rule is removed')

lines = run('wxs 9 2 4 1001')
its, endF = items(lines)
local wx = Ed.parse_wx(its)
check(wx and wx.count == 1 and wx.pieces[4] and wx.pieces[4].id == 1001 and wx.pieces[4].ok and tonumber(endF[4]) == #its, 'wxs: a piece saved; the editor reads the set')
lines = run('wxs 10 2 0 1005')
check(fields(lines[1])[3] == 'err', 'wxs: a weapon slot is refused by the server')
lines = run('wxl 11 2 4')
local list = Ed.parse_wxl((items(lines)))
check(list and #list == 1 and list[1].id == 1001 and list[1].name == 'Ogre Mask', 'wxl: the items the slot may take')
lines = run('wxc 12 2')
wx = Ed.parse_wx((items(lines)))
check(wx and wx.count == 0, 'wxc: the set is cleared')

-- ---------------------------------------------------------------- drawing
section('F12/F13 the editor sections draw balanced (stand-in ImGui)')
for k, v in pairs({ ImGuiCol_Text = 0, ImGuiCol_Border = 5, ImGuiCol_Button = 21, ImGuiCol_ButtonHovered = 22,
                    ImGuiCol_Header = 24, ImGuiCol_HeaderHovered = 25, ImGuiChildFlags_Borders = 1 }) do rawset(_G, k, v) end
local function fakeImgui()
    local g = { colors = 0, combos = 0, errors = {}, clicks = {}, texts = {} }
    g.Text = function(t) g.texts[#g.texts + 1] = t end
    g.TextUnformatted = g.Text
    g.TextColored = function(_, t) g.texts[#g.texts + 1] = t end
    g.PushTextWrapPos, g.PopTextWrapPos = function() end, function() end
    g.BeginTooltip, g.EndTooltip = function() return true end, function() end
    g.SameLine, g.SetNextItemWidth, g.Separator, g.NewLine, g.SetCursorPosX, g.AlignTextToFramePadding =
        function() end, function() end, function() end, function() end, function() end, function() end
    g.IsItemHovered = function() return true end
    g.GetContentRegionAvail = function() return { 1000, 500 } end
    g.Button = function(label) if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    g.Selectable = function() return false end
    g.InputText = function() return false end
    g.BeginCombo = function() return false end
    g.EndCombo = function() end
    g.PushStyleColor = function() g.colors = g.colors + 1 end
    g.PopStyleColor = function(k) g.colors = g.colors - (k or 1) end
    g.CollapsingHeader = function() return true end
    g.SetNextItemOpen = function() end
    return g
end
local g = fakeImgui()
local sent = {}
Ed.init({ now = function() return clock end, imgui = g, s = function(px) return px end, queue_command = function(l) sent[#sent + 1] = l end })
local ES = Ed._S
ES.server = { version = 10, caps = { smn = true, wsset = true } }
ES.smn = { slot = 1, data = Ed.parse_smn((items(run('smg 13 1')))), pacts = cat }
ES.smn.edit = { avatar = 5, engage = true, rage = 0, ward = 2, between = 1, idle = true, ruleSwitch = true }
local mate = { slot = 1, id = 301, name = 'Kiri', job = 'SMN', level = 75, out = true }
local okDraw, errDraw = pcall(Ed.smn_section, mate)
check(okDraw and g.colors == 0, 'the Summoner section draws balanced' .. (okDraw and '' or (': ' .. tostring(errDraw))))
local shown = table.concat(g.texts, '\n')
check(shown:find('Pact rules') ~= nil and shown:find('Now:') ~= nil, 'it shows the live state and the rules heading')
ES.smn.draft = Ed.smn_hastega_example()
ES.smn.draft.n = 1
okDraw, errDraw = pcall(Ed.smn_panel, mate)
check(okDraw and g.colors == 0, 'the rule editor draws balanced' .. (okDraw and '' or (': ' .. tostring(errDraw))))
ES.wx = { slot = 2, data = Ed.parse_wx((items(run('wxs 14 2 4 1001')))), eq = 4, choices = list, choicesFor = 4 }
okDraw, errDraw = pcall(Ed.wx_block, { slot = 2, id = 201, name = 'Dag', job = 'WAR', level = 75, out = false })
check(okDraw and g.colors == 0, 'the WS gear set block draws balanced' .. (okDraw and '' or (': ' .. tostring(errDraw))))
ES.server = { version = 10, caps = {} }
g.texts = {}
Ed.smn_section(mate)
Ed.wx_block(mate)
check(#g.texts == 0, 'an older server (no capabilities): neither section is drawn')

-- ---------------------------------------------------------------- the Basic Summoner starter
section('F13 the Basic Summoner starter: loads, can be edited and saved, rule order, nothing else changed')
local starter = Ed.SMN_STARTERS[1]
check(starter and starter.name == 'Basic Summoner', 'the SMN starter exists')
check(#Ed.templates_for('SMN') == 0, 'the Rule Set templates are unchanged (a Rule Set has no pet actions)')
check(starter.settings.engage == true and starter.settings.avatar == nil and starter.settings.rage == 2 and starter.settings.ward == 2
    and starter.settings.between == 0 and starter.settings.idle == false and starter.settings.ruleSwitch == true,
    'its settings: normal attacks on, the mate\'s own avatar choice (B8: kept), Rage and Ward rules only, keep out between pulls, no idle support, rules may switch')
check(#starter.rules == 2 and starter.rules[1].pact == 'HASTEGA' and starter.rules[1].target == 'MASTER' and starter.rules[1].cond == 'NOT_STATUS'
    and starter.rules[1].arg == 'HASTE' and starter.rules[1].protect and starter.rules[2].pact == 'CLAW' and starter.rules[2].target == 'ENEMY'
    and starter.rules[2].cond == 'MY_MPP_GTE' and starter.rules[2].arg == '60', 'its rules: 1 Hastega on you when you lack Haste (protected), 2 Claw while MP >= 60%')
check(starter.about:find('48') and starter.about:find('Garuda') and starter.about:find('rest'), 'its text names the level / pact needs and rest')
-- open it (the template flow): an unsaved starter in the Summoner section, drawn beside the mate's own data
-- (B8) smn2: the server keeps the mate's avatar for "-"
ES.server = { version = 10, caps = { smn = true, wsset = true, smn1 = true, smn2 = true } }
gp.cv['SQUAD_RS_301_15'] = 4 -- (a Rule Set assignment that must stay)
ES.smn = { slot = 1, data = Ed.parse_smn((items(run('smg 20 1')))), pacts = cat }
ES.smn.edit = {}
check(Ed.smn_use_starter(mate, 1) == true and ES.smn.starter ~= nil and ES.smn.starter ~= starter, 'using it opens a copy, not saved')
g.texts = {}
okDraw, errDraw = pcall(Ed.smn_section, mate)
shown = table.concat(g.texts, '\n')
check(okDraw and g.colors == 0, 'the starter draws balanced' .. (okDraw and '' or (': ' .. tostring(errDraw))))
local p1, p2s = shown:find('1%. Hastega'), shown:find('2%. Claw')
check(shown:find('Starter: Basic Summoner') ~= nil and p1 and p2s and p1 < p2s, 'it shows the expected rule order: 1 Hastega, 2 Claw')
-- edit it before saving (the threshold 60 -> 70)
ES.smn.starter.rules[2].arg = '70'
check(starter.rules[2].arg == '60', 'editing the starter never changes the template')
-- save it: the same requests the Save starter button sends, through the real server side
-- the mate has its own settings and rules first (Ifrit, one Healing Ruby rule)
run('sms 21 1 2 1 0 0 0 0 1')
run('smr 22 1 1 1 HEALING_RUBY MASTER HPP_LT 50 COMBAT 0')
local mineBefore = Ed.parse_smn((items(run('smg 23 1'))))
check(mineBefore and mineBefore.avatar == 2 and #mineBefore.rules == 1 and mineBefore.rules[1].pact == 'HEALING_RUBY', 'the mate has its own settings and one rule before')
local function sameAsBefore(label)
    local now = Ed.parse_smn((items(run('smg 24 1'))))
    check(now and now.avatar == 2 and now.rage == 0 and now.ward == 0 and #now.rules == 1 and now.rules[1].pact == 'HEALING_RUBY'
        and now.rules[1].cond == 'HPP_LT', label)
end
-- a refused part: rule 2 made invalid (a Rage pact on you): the server refuses it, the open save is dropped
local bad = Ed.smn_use_starter and { name = 'x', settings = ES.smn.starter.settings, rules = { ES.smn.starter.rules[1],
    { on = true, pact = 'CLAW', target = 'MASTER', cond = 'ALWAYS', arg = '0', when = 'COMBAT', protect = false } } }
local refused = false
for _, words in ipairs(Ed.smn_starter_requests(1, bad)) do
    local ans = run(words[1] .. ' 25 ' .. table.concat(words, ' ', 2))
    if fields(ans[1])[3] == 'err' then
        refused = true
        run('smba 26 1')
        break
    end
end
check(refused, 'a starter with a bad rule is refused by the server')
sameAsBefore('a refused save keeps the previous settings and rules exactly (no partial replacement)')
-- a commit with a missing part (count 3, two rules staged): nothing changes either
run('smb 27 1')
run('smbs 27 1 9 1 2 2 0 0 1')
run('smbr 27 1 1 1 HASTEGA MASTER NOT_STATUS HASTE COMBAT 1')
run('smbr 27 1 2 1 CLAW ENEMY MY_MPP_GTE 60 COMBAT 0')
local cAns = run('smbc 28 1 3')
check(fields(cAns[1])[3] == 'err', 'a commit with a rule missing is refused')
sameAsBefore('... and the previous settings and rules are kept')
-- a commit without a begin (or after it expired): refused, nothing changes
check(fields(run('smbc 29 1 2')[1])[3] == 'err', 'a commit with nothing open is refused')
sameAsBefore('... still unchanged')
local reqs = Ed.smn_starter_requests(1, ES.smn.starter)
local lastOk = true
for _, words in ipairs(reqs) do
    local ans = run(words[1] .. ' 30 ' .. table.concat(words, ' ', 2))
    lastOk = lastOk and fields(ans[1])[3] ~= 'err'
end
check(lastOk, 'the server accepts every request of the starter (' .. #reqs .. ' requests)')
d = Ed.parse_smn((items(run('smg 31 1'))))
check(d and d.avatar == 2 and d.engage and d.rage == 2 and d.ward == 2 and d.between == 0 and not d.idle and d.ruleSwitch,
    'saved: the settings read back as the starter, and (B8) the mate keeps its own avatar choice (Ifrit), not Keep current')
check(reqs[2] and reqs[2][1] == 'smbs' and reqs[2][3] == '-', '(B8) the starter sends the avatar as "-" (keep the mate\'s) unless one was picked')
-- (B8) an avatar picked in the draft is sent and saved
local picked = { name = 'p', settings = { avatar = 5, engage = true, rage = 2, ward = 2, between = 0, idle = false, ruleSwitch = true },
                 rules = ES.smn.starter and ES.smn.starter.rules or reqs, avatarPicked = true }
check(Ed.smn_starter_requests(1, picked)[2][3] == '5', '(B8) an avatar picked in the draft is sent as itself')
ES.server.caps.smn2 = nil
check(Ed.smn_starter_requests(1, { settings = { avatar = nil }, rules = {} }, 2)[2][3] == '2',
    '(B8) an older server (no smn2) gets the mate\'s loaded avatar instead of "-"')
ES.server.caps.smn2 = true
-- (the planner checks below are about Keep current: set it, as a player would)
gp.cv[S.choiceVar(301)] = 9
check(d and #d.rules == 2 and d.rules[1].pact == 'HASTEGA' and d.rules[1].protect and d.rules[2].pact == 'CLAW'
    and d.rules[2].cond == 'MY_MPP_GTE' and d.rules[2].arg == '70', 'saved: the rules in order, with the edit (Claw from 70% MP)')
check(gp.cv['SQUAD_RS_301_15'] == 4, 'the mate\'s Rule Set assignment is untouched')
-- what it does (the server planner): below level 48 the Hastega rule waits and Claw goes only with the MP threshold met
local kiri = smnOut
S.state[kiri:getID()] = nil
kiri.lvl, kiri.lv = 40, { SQUAD_ID = 301 }
kiri.pet = nil
kiri.mp, kiri.maxmp = 300, 600 -- 50% < 70%
clock = clock + 100
S.combatTick(kiri, gp, enemy, clock, nil, function() return xi.petId.CARBUNCLE end)
local claws = 0
for _, u in ipairs(kiri.pet and kiri.pet.used or {}) do if u.id == xi.jobAbility.CLAW then claws = claws + 1 end end
check(kiri.pet and kiri.pet.petId == 13 and hastegas(kiri) == 0 and claws == 0,
    'level 40, no avatar out, Keep current, MP 50%: the fight summon brings Garuda (the avatar of rule 2, not the default pick), no Hastega (Lv48), no Claw (below 70%)')
kiri.mp = 500 -- 83%
S.combatTick(kiri, gp, enemy, clock + 1, nil, nil)
claws = 0
for _, u in ipairs(kiri.pet.used) do if u.id == xi.jobAbility.CLAW then claws = claws + 1 end end
check(claws == 1, 'MP above the threshold: Claw')
-- Claw never gets around Garuda's own needs: no pact with Garuda (spells from scrolls) or below Garuda's level 10
for _, case in ipairs({ { lvl = 40, has = function(name) return name ~= 'GARUDA' end, why = 'no pact with Garuda' },
                        { lvl = 9, has = nil, why = 'level 9 (Garuda needs 10)' } }) do
    S.state[kiri:getID()] = nil
    kiri.lvl, kiri.lv, kiri.pet = case.lvl, { SQUAD_ID = 301 }, nil
    kiri.mp = 500
    clock = clock + 100
    S.combatTick(kiri, gp, enemy, clock, case.has, function() return xi.petId.CARBUNCLE end)
    S.combatTick(kiri, gp, enemy, clock + 1, case.has, nil)
    claws = 0
    for _, u in ipairs(kiri.pet and kiri.pet.used or {}) do if u.id == xi.jobAbility.CLAW then claws = claws + 1 end end
    check(kiri.pet and kiri.pet.petId == 8 and claws == 0, case.why .. ': no Garuda and no Claw (the default Carbuncle comes instead)')
end
kiri.lvl = 75

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
