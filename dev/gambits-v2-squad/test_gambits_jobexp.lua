-- Gambits job expansion (2026-11-21): stand-in tests, no game, no server, no Ashita.
--   luajit test_gambits_jobexp.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                  <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> <server root>
-- What runs for real (Lua, executed): squad_jobs.lua (Rule Set analysis, Sneak/Trick Attack positioning, the weapon
-- skill hold's Lua side, song recipients, party roles, pet care), gambits_squad.lua (!gsq v6: MOD_LT, the new target,
-- content filters, catm "jm"), squad_rulesets.lua (MOD_LT checks), squad_ability_rules.lua (content), the addon's
-- squad_editor.lua (MOD_LT editing, advanced conditions, the job templates) - with the server's REAL enums
-- (effect, mod, magic, job_ability) and data tables, and stand-in entities.
-- What does NOT run here: the C++ (gambits_container.cpp, trust_controller.cpp, battle_entity.cpp). Section 9 holds
-- Lua SPECIFICATIONS of what the C++ is meant to do and reads the C++ source for the code shapes it relies on.
-- Gameplay is proven only in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER_ROOT,
       'usage: test_gambits_jobexp.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server-root')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function readAll(p) local f = io.open(p, 'rb'); if not f then return nil end local s = f:read('*a'); f:close(); return s end
local loadChunk = loadstring or load

-- ---------------------------------------------------------------- the server bits, from the server's own files
dofile(GAMBITS)
xi = rawget(_G, 'xi') or {}
dofile(SERVER_ROOT .. '/scripts/enum/effect.codegen.lua')
dofile(SERVER_ROOT .. '/scripts/enum/mod.codegen.lua')
dofile(SERVER_ROOT .. '/scripts/enum/magic.lua')
dofile(JA_ENUM)
xi.effectFlag = xi.effectFlag or { DISPELABLE = 1 }
xi.objType = { PC = 1, TRUST = 2 }
xi.msg = { channel = { SYSTEM_3 = 121 } }
xi.recast = { ABILITY = 1 }
xi.settings = { main = { RESTRICT_CONTENT = 1, ENABLE_COP = 1, ENABLE_ROTZ = 1, ENABLE_TOAU = 1, ENABLE_WOTG = 0, ENABLE_ABYSSEA = 0 } }
SquadOwnerMerit = function() return 0 end

-- the job expansion's map server (squad.cpp registers these); engineOff() is a v0.1.55 / batch xi_map
local function engine2On() SquadJobExpansionEngine = function() return 1 end end
local function engine2Off() SquadJobExpansionEngine = nil end
SquadApplyWeaponSkills = function() return true end
GetSquadWeaponSkillIds = function() return {} end
engine2On()

-- abilities of switched-off content are not loaded (ability.cpp): GetAbility gives nil. Wings of the Goddess here.
local WOTG_ABILITIES = { [xi.ja.YONIN] = true, [xi.ja.INNIN] = true, [xi.ja.SEKKANOKI] = true, [xi.ja.PIANISSIMO] = true,
                         [xi.ja.FOOTWORK] = true }
local function wotgOn() return xi.settings.main.ENABLE_WOTG == 1 or xi.settings.main.RESTRICT_CONTENT == 0 end
GetAbility = function(id)
    if WOTG_ABILITIES[id] and not wotgOn() then return nil end
    return { id = id }
end

-- GetSpell(id):getSpellFamily() from the real spell data (name -> family by the family names the server has)
local SPELL_FAMILY = {}
do
    local fam = xi.magic.spellFamily
    local byName = { VALOR_MINUET = 'VALOR_MINUET', VALOR_MINUET_II = 'VALOR_MINUET', ADVANCING_MARCH = 'MARCH', VICTORY_MARCH = 'MARCH',
                     MAGES_BALLAD = 'MAGES_BALLAD', MAGES_BALLAD_II = 'MAGES_BALLAD', KNIGHTS_MINNE = 'KNIGHTS_MINNE',
                     BATTLEFIELD_ELEGY = 'ELEGY', FOE_REQUIEM = 'FOE_REQUIEM', CURE = 'CURE' }
    for spellName, famName in pairs(byName) do
        SPELL_FAMILY[xi.magic.spell[spellName]] = fam[famName]
    end
end
GetSpell = function(id) return { getSpellFamily = function() return SPELL_FAMILY[id] or 0 end } end

package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end
package.preload['modules/custom/lua/squad_ws'] = function() return dofile(LUA_DIR .. '/squad_ws.lua') end
package.preload['modules/custom/lua/squad_rulesets_data'] = function() return { format = 'xifo-ruleset-store', version = 1, sets = {} } end
local R = require('modules/custom/lua/squad_rulesets')
local A = require('modules/custom/lua/squad_ability_rules')
local J = dofile(LUA_DIR .. '/squad_jobs.lua')

-- xi.squad.levelsFor from squad.lua itself (the catalog asks it for a mate's levels)
do
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local a = assert(src:find('local function jobLevel%('))
    local b = assert(src:find('\nxi%.squad%.levelsFor = levelsFor', a))
    xi.squad = xi.squad or {}
    xi.squad.levelsFor = assert(loadChunk('local SUB_UNLOCK_LEVEL = ' .. src:match('local SUB_UNLOCK_LEVEL = (%d+)')
        .. '\n' .. src:sub(a, b) .. '\nreturn levelsFor', '=squad.lua levelsFor'))()
end
squadScrollsOn = function() return false end
GetSquadUnlocks = function() return {} end

local function playerOf()
    local p = { cv = {}, lv = {}, printed = {}, party = {} }
    function p:getID() return 1 end
    function p:getCharVar(k) return self.cv[k] or 0 end
    function p:setCharVar(k, v) self.cv[k] = v end
    function p:getLocalVar(k) return self.lv[k] or 0 end
    function p:setLocalVar(k, v) self.lv[k] = v end
    function p:printToPlayer(text) self.printed[#self.printed + 1] = text end
    function p:getPartyWithTrusts() return self.party end
    function p:getMainLvl() return 75 end
    function p:getMainJob() return 1 end
    function p:hasJob() return true end
    function p:getObjType() return xi.objType.PC end
    return p
end

-- a stand-in battle entity (mate, enemy, pet)
local function ent(o)
    o = o or {}
    local e = { vars = {}, id = o.id or 1, job = o.job or 6, lvl = o.lvl or 75, tp = o.tp or 0, hpp = o.hpp or 100,
                effects = o.effects or {}, alive = o.alive ~= false, dist = o.dist or {}, behind = o.behind or false,
                target = o.target, master = o.master, recast = o.recast or {}, calls = {} }
    function e:getID() return self.id end
    function e:getLocalVar(k) return self.vars[k] or 0 end
    function e:setLocalVar(k, v) self.vars[k] = v end
    function e:getMainJob() return self.job end
    function e:getMainLvl() return self.lvl end
    function e:getSubJob() return self.sjob or 0 end
    function e:getSubLvl() return self.slvl or 0 end
    function e:isEngaged() return self.target ~= nil end
    function e:getTP() return self.tp end
    function e:getHPP() return self.hpp end
    function e:hasStatusEffect(id) return self.effects[id] == true end
    function e:getTarget() return self.target end
    function e:isAlive() return self.alive end
    function e:isBehind() return self.behind end
    function e:checkDistance(other) return self.dist[other:getID()] or 1 end
    function e:getMaster() return self.master end
    function e:hasRecast(_, id) return self.recast[id] == true end
    function e:petAttack(t) self.calls[#self.calls + 1] = { 'petAttack', t:getID() } end
    return e
end

local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local srv = playerOf()
-- one mate per job of the expansion, level 75, no sub job (slot = index)
local JOB_IDS = { MNK = 2, BLM = 4, THF = 6, DRK = 8, BST = 9, BRD = 10, RNG = 11, SAM = 12, NIN = 13, DRG = 14, BLU = 16, COR = 17 }
local JOB_ORDER = { 'MNK', 'BLM', 'THF', 'DRK', 'BST', 'BRD', 'RNG', 'SAM', 'NIN', 'DRG', 'BLU', 'COR' }
local squad = {}
for i, job in ipairs(JOB_ORDER) do
    squad[i] = { slot = i, id = 100 + i, name = 'Mate' .. job, mjob = JOB_IDS[job], sjob = 0, jobs = { [JOB_IDS[job]] = { level = 75 } } }
end
GetSquad = function() return squad end
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end
local function F(line) return G.splitPlain(line, '|') end
local function catEntries(lines, kind)
    local out = {}
    for _, l in ipairs(lines) do
        local ff = F(l)
        if ff[3] == 'cat' and ff[5] == kind then for e in (ff[6] .. ','):gmatch('([^,]+),') do out[#out + 1] = e end end
    end
    return out
end
local function has(list, entry) for _, e in ipairs(list) do if e == entry then return true end end return false end
local function hasPrefix(list, prefix) for _, e in ipairs(list) do if e:sub(1, #prefix) == prefix then return true end end return false end
local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end

-- ================================================================= 1. MOD_LT: the shadow count condition (server side)
section('MOD_LT: Utsusemi shadows / Blink images below a number (squad_rulesets.lua, gambits_squad.lua)')
do
    check(ai.c.MOD_LT == 43, 'gambits.lua has MOD_LT = 43 (the same value as gambits_container.h)')
    check(xi.mod.UTSUSEMI ~= nil and xi.mod.BLINK ~= nil and xi.mod.STONESKIN == nil,
          'the real mod enum has UTSUSEMI and BLINK; there is no STONESKIN mod (its HP left is the effect\'s power)')
    local function rule(cond) return { id = 'r1', on = true, target = 'SELF', cond = cond, action = { 'spell', 'UTSUSEMI_NI' } } end
    check(problems(rule({ 'MOD_LT', { mod = 'UTSUSEMI', below = 2 } })) == '', 'MOD_LT { UTSUSEMI, below 2 } is a valid condition')
    check(problems(rule({ 'MOD_LT', { mod = 'BLINK', below = 1 } })) == '', 'MOD_LT { BLINK, below 1 } is valid')
    check(problems(rule({ 'MOD_LT', { mod = 'UTSUSEMI', below = 9 } })) ~= '', 'below 9 shadows is refused (1-7)')
    check(problems(rule({ 'MOD_LT', { mod = 'STONESKIN', below = 100 } })):find('only UTSUSEMI, BLINK', 1, true),
          'STONESKIN is refused with the reason: ' .. problems(rule({ 'MOD_LT', { mod = 'STONESKIN', below = 100 } })))
    check(problems(rule({ 'MOD_LT', { mod = 'DEF', below = 1 } })) ~= '', 'any other mod (DEF) is refused: a whitelist')
    check(problems(rule({ 'MOD_LT', 2 })):find('needs', 1, true), 'a bare number is refused')
    check(R.modArg({ mod = 'UTSUSEMI', below = 2 }) == xi.mod.UTSUSEMI + 2 * 65536,
          'the engine argument is mod id + below * 65536 (gambits_container.cpp: arg & 0xFFFF, arg >> 16)')
    check(R.modArg({ mod = 'STONESKIN', below = 2 }) == nil and R.modArg(nil) == nil, 'no engine argument for anything else')
    engine2Off()
    check(problems(rule({ 'MOD_LT', { mod = 'UTSUSEMI', below = 2 } })):find('needs the updated map server', 1, true),
          'on a xi_map without the job expansion MOD_LT is refused (the engine would not know condition 43)')
    engine2On()
    local wire = G.encodeRule({ id = 'r1', on = true, target = 'SELF', cond = { 'MOD_LT', { mod = 'UTSUSEMI', below = 2 } },
                                action = { 'spell', 'UTSUSEMI_NI' } }, 1)
    local back = G.decodeRule(wire, 1)
    check(wire == '1,SELF,MOD_LT,UTSUSEMI.2,,,s,UTSUSEMI_NI,' and type(back.cond[2]) == 'table' and back.cond[2].mod == 'UTSUSEMI'
          and back.cond[2].below == 2, 'the codec carries MOD_LT as "UTSUSEMI.2" both ways: ' .. tostring(wire))
    check(G.encodeRule({ id = 'r1', on = true, target = 'SELF', cond = { 'MOD_LT', { mod = 'UTSUSEMI', below = 2, extra = 1 } },
                         action = { 'spell', 'UTSUSEMI_NI' } }, 1) == nil, 'an argument with any other key is not carried (no silent loss)')
end

-- ================================================================= 2. the catalog: target, flags, content
section('catalog v6: Check Self -> Act on Enemy, catm "jm", content switched off')
do
    local o = run('hello 1')
    check(o[1] == 'GSQ|1|hello|6|32|120|64', 'hello: version 6 - ' .. tostring(o[1]))
    local t = catEntries(run('catm 2 9 jm'), 't')
    check(has(t, 'TRIGGER_SELF_ACTION_TARGET') and t[#t] == 'TRIGGER_SELF_ACTION_TARGET', 'the target TRIGGER_SELF_ACTION_TARGET is offered (last)')
    local cJM = catEntries(run('catm 3 9 jm'), 'c')
    local cJ = catEntries(run('catm 4 9 j'), 'c')
    local cPlain = catEntries(run('catm 5 9'), 'c')
    check(has(cJM, 'MOD_LT:m') and has(cJM, 'JA_ON_COOLDOWN:j'), 'catm "jm" (this addon): MOD_LT:m and JA_ON_COOLDOWN:j')
    check(not hasPrefix(cJ, 'MOD_LT') and has(cJ, 'JA_ON_COOLDOWN:j'), 'catm "j" (Gambits 0.2.1): no MOD_LT, so its catalog check still passes')
    local OLD_C = '^[A-Z][A-Z0-9_]*:[nrej][:%d]*$' -- (Gambits 0.2.1's entry check: one unknown kind rejects the whole catalog)
    local oldOk = true
    for _, e in ipairs(cJ) do oldOk = oldOk and e:match(OLD_C) ~= nil end
    for _, e in ipairs(cPlain) do oldOk = oldOk and e:match('^[A-Z][A-Z0-9_]*:[nre][:%d]*$') ~= nil end
    check(oldOk, 'every condition entry sent to an older addon is one it reads')
    engine2Off()
    check(not hasPrefix(catEntries(run('catm 6 9 jm'), 'c'), 'MOD_LT'), 'without the job expansion\'s xi_map MOD_LT is not offered')
    engine2On()

    -- content: Wings of the Goddess off (RESTRICT_CONTENT 1, ENABLE_WOTG 0)
    check(G.contentEnabled(nil) and G.contentEnabled('') and G.contentEnabled('ROTZ') and not G.contentEnabled('WOTG'),
          'contentEnabled: no tag = on; ROTZ on; WOTG off')
    local nin = catEntries(run('catm 7 9 jm'), 'j') -- slot 9 = NIN
    check(not hasPrefix(nin, 'YONIN:') and not hasPrefix(nin, 'INNIN:'), 'NIN with WotG off: no Yonin / Innin offered')
    local sam = catEntries(run('catm 8 8 jm'), 'j') -- slot 8 = SAM
    check(not hasPrefix(sam, 'SEKKANOKI:') and hasPrefix(sam, 'HASSO:'), 'SAM with WotG off: no Sekkanoki; Hasso (ToAU, on) stays')
    local brd = catEntries(run('catm 9 6 jm'), 'j') -- slot 6 = BRD
    check(not hasPrefix(brd, 'PIANISSIMO:'), 'BRD with WotG off: no Pianissimo')
    local mnk = catEntries(run('catm 10 1 jm'), 'j')
    check(not hasPrefix(mnk, 'FOOTWORK:') and hasPrefix(mnk, 'CHAKRA:'), 'MNK with WotG off: no Footwork; Chakra stays')
    local fams = catEntries(run('catm 11 2 jm'), 'f')
    check(not has(fams, 'CURA') and not has(fams, 'ESUNA') and not has(fams, 'REPOSE') and has(fams, 'CURE') and has(fams, 'UTSUSEMI')
          and has(fams, 'VALOR_MINUET') and has(fams, 'DRAIN') and has(fams, 'ELEGY') and has(fams, 'FOE_REQUIEM'),
          'families: Cura/Esuna/Repose (WotG) left out; Cure, Utsusemi, Minuet, Drain, Elegy, Requiem offered')
    local okA, whyA = pcall(A.reason, { job = 13, level = 75, subJob = 0, subLevel = 0 }, xi.ja.YONIN, 'YONIN')
    check(okA and type(whyA) == 'string' and whyA:find('switched off', 1, true), 'U13: Yonin is refused for a NIN 75 with WotG off: ' .. tostring(whyA))
    xi.settings.main.ENABLE_WOTG = 1
    nin = catEntries(run('catm 12 9 jm'), 'j')
    fams = catEntries(run('catm 13 2 jm'), 'f')
    check(hasPrefix(nin, 'YONIN:') and hasPrefix(nin, 'INNIN:') and has(fams, 'CURA'), 'WotG on again: Yonin, Innin and Cura are back')
    xi.settings.main.ENABLE_WOTG = 0
    -- spells: Stun is a Rise of the Zilart spell (content tag ROTZ in sql/spell_list.sql)
    local drk = catEntries(run('catm 14 4 jm'), 's')
    check(hasPrefix(drk, 'STUN:'), 'DRK: Stun offered with RotZ on')
    xi.settings.main.ENABLE_ROTZ = 0
    drk = catEntries(run('catm 15 4 jm'), 's')
    check(not hasPrefix(drk, 'STUN:') and hasPrefix(drk, 'DRAIN:'), 'RotZ off: Stun left out, Drain (no tag) stays')
    xi.settings.main.ENABLE_ROTZ = 1
    local spells = dofile(LUA_DIR .. '/squad_spell_jobs_data.lua')
    local tagged, stunTag = 0, nil
    for id, row in pairs(spells.spells) do
        if row.ct then tagged = tagged + 1 end
        if row[1] == 'STUN' then stunTag = row.ct end
    end
    check(spells.version == 3 and tagged > 100 and stunTag == 'ROTZ', string.format('spell data v3 carries content tags (%d spells, Stun %s)', tagged, tostring(stunTag)))
end

-- ================================================================= 3. what a Rule Set asks for (J.analyse)
section('squad_jobs.analyse: SA/TA management, the weapon skill hold, songs by role')
do
    local function sv(r) return G.decodeRule(r, 1) end
    local mob = ent({ id = 501, job = 6 })
    J.analyse(mob, { sv('1,SELF,NOT_STATUS,SNEAK_ATTACK,,,j,SNEAK_ATTACK,') })
    check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 1 and mob:getLocalVar('SQUAD_SATA_WSHOLD') == 0,
          'a rule with Sneak Attack: managed by Gambits; no TP condition: no weapon skill hold')
    J.analyse(mob, { sv('1,SELF,TP_GTE,1000,NOT_STATUS,TRICK_ATTACK,j,TRICK_ATTACK,') })
    check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 1 and mob:getLocalVar('SQUAD_SATA_WSHOLD') == 1,
          'Trick Attack with TP at least 1000: managed, and the weapon skill may wait for it (opt-in by the rule)')
    J.analyse(mob, { sv('0,SELF,TP_GTE,1000,,,j,SNEAK_ATTACK,') })
    check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 0 and mob:getLocalVar('SQUAD_SATA_WSHOLD') == 0, 'a switched-off rule asks for nothing')
    mob:setLocalVar('SQUAD_SATA_REQ', 44); mob:setLocalVar('SQUAD_WS_HOLD_UNTIL', 99)
    J.analyse(mob, nil)
    check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 0 and mob:getLocalVar('SQUAD_SATA_REQ') == 0 and mob:getLocalVar('SQUAD_WS_HOLD_UNTIL') == 0,
          'no Rule Set (job rules): every var cleared - squadThiefTick decides on its own, as in v0.1.55')
    engine2Off()
    J.analyse(mob, { sv('1,SELF,TP_GTE,1000,,,j,SNEAK_ATTACK,') })
    check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 0, 'without the job expansion\'s xi_map nothing is set (the C++ that reads it is not there)')
    engine2On()

    local bard = ent({ id = 502, job = 10 })
    J.analyse(bard, { sv('1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,'), sv('1,CASTER,NOT_STATUS,BALLAD,,,f,MAGES_BALLAD,'),
                      sv('1,PARTY,NOT_STATUS,PAEON,,,f,ARMYS_PAEON,'), sv('1,TARGET,NOT_STATUS,ELEGY,,,f,ELEGY,') })
    check(bard:getLocalVar('SQUAD_SONG_ROLES') == 1, 'songs for roles: SQUAD_SONG_ROLES on (battle_entity.cpp filters the recipients)')
    local war, whm, pld, rng = ent({ id = 601, job = 1 }), ent({ id = 602, job = 3 }), ent({ id = 603, job = 7 }), ent({ id = 604, job = 11 })
    local minuet, ballad, paeon = xi.magic.spell.VALOR_MINUET, xi.magic.spell.MAGES_BALLAD, xi.magic.spell.ARMYS_PAEON
    check(J.songRecipient(bard, war, minuet) and not J.songRecipient(bard, whm, minuet) and J.songRecipient(bard, pld, minuet)
          and not J.songRecipient(bard, rng, minuet), 'Minuet for Melee: WAR and PLD (a melee job) get it, WHM and RNG do not')
    check(J.songRecipient(bard, whm, ballad) and not J.songRecipient(bard, war, ballad), 'Ballad for Mage: WHM yes, WAR no')
    check(J.songRecipient(bard, war, paeon) and J.songRecipient(bard, whm, paeon), 'Paeon for Party: everyone, as before')
    check(J.songRecipient(bard, war, xi.magic.spell.VICTORY_MARCH), 'a song the rules do not name (March): everyone, as before')
    rng:setLocalVar('SQUAD_ROLE', 2)
    whm:setLocalVar('SQUAD_ROLE', 2)
    check(J.songRecipient(bard, rng, minuet) and J.songRecipient(bard, whm, minuet) and not J.songRecipient(bard, whm, ballad),
          'party role override: an RNG and a WHM set to melee get Minuet; the WHM no longer counts as a mage')
    local plain = ent({ id = 503, job = 10 })
    J.analyse(plain, { sv('1,PARTY,NOT_STATUS,MINUET,,,f,VALOR_MINUET,') })
    check(plain:getLocalVar('SQUAD_SONG_ROLES') == 0 and J.songRecipient(plain, whm, minuet), 'a Bard singing for the party: no filtering at all')
    check(xi.squad.songRecipient(bard, war, minuet) == true and xi.squad.songRecipient(bard, nil, minuet) == true,
          'the global wrapper battle_entity.cpp calls: the same answer; a missing target never takes a song away')
    local broken = { getID = function() error('boom') end }
    check(xi.squad.songRecipient(broken, war, minuet) == true, 'an error inside never takes a song away')
end

-- ================================================================= 4. party roles (!squad partyrole)
section('party roles: !squad partyrole and the engine\'s role local var')
do
    local said = {}
    -- (2026-11-21) the REAL findMate from squad.lua (it compares mate.slot, a number, with its argument) and the real
    -- dispatch: chat arguments arrive as strings ('sssss'). The earlier stand-in compared strings and hid the bug.
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local fa = assert(src:find('local function findMate%(squad, slot%)'))
    local fb = assert(src:find('\nend\n', fa, true))
    local realFindMate = assert(loadChunk(src:sub(fa, fb + 4) .. '\nreturn findMate', '=squad.lua findMate'))()
    check(src:find("parameters = 'sssss'", 1, true) ~= nil, 'squad.lua\'s !squad takes string arguments (cmdprops sssss)')
    check(src:find('J.partyRoleCommand(player, squad, arg1, arg2, { say = say, findMate = findMate })', 1, true) ~= nil,
          'squad.lua passes the chat arguments and its own findMate to partyRoleCommand')
    check(realFindMate({ { slot = 2, name = 'X' } }, '2') == nil and realFindMate({ { slot = 2, name = 'X' } }, 2) ~= nil,
          'the real findMate finds slot 2 by the NUMBER 2, not by the string "2" (the cause of the bug)')
    local h = { say = function(_, text) said[#said + 1] = text end, findMate = realFindMate }
    local p = playerOf()
    -- slots as GetSquad gives them (numbers, not 1..n: a gap after a deleted mate)
    local sq = { { slot = 1, id = 11, name = 'Rook' }, { slot = 2, id = 12, name = 'Dame' }, { slot = 4, id = 14, name = 'Testwar' } }
    J.partyRoleCommand(p, sq, '1', 'tank', h)
    check(p.cv.SQUAD_PROLE_11 == 1 and said[#said]:find('Rook counts as tank', 1, true), 'slot "1" (a chat string) -> tank, stored per mate: ' .. said[#said])
    J.partyRoleCommand(p, sq, '4', 'mage', h)
    check(p.cv.SQUAD_PROLE_14 == 3 and said[#said]:find('Testwar counts as mage', 1, true), 'slot "4" after a gap -> Testwar, mage')
    J.partyRoleCommand(p, sq, 'Dame', 'melee', h)
    check(p.cv.SQUAD_PROLE_12 == 2 and said[#said]:find('Dame counts as melee', 1, true), 'a name: Dame -> melee')
    J.partyRoleCommand(p, sq, 'testWAR', 'ranged', h)
    check(p.cv.SQUAD_PROLE_14 == 4, 'a name in any case: testWAR -> Testwar, ranged')
    J.partyRoleCommand(p, sq, 'TESTWAR', 'MAGE', h)
    check(p.cv.SQUAD_PROLE_14 == 3, 'upper case name and role: TESTWAR MAGE -> mage')
    local before = { p.cv.SQUAD_PROLE_11, p.cv.SQUAD_PROLE_12, p.cv.SQUAD_PROLE_14 }
    local function unchanged() return p.cv.SQUAD_PROLE_11 == before[1] and p.cv.SQUAD_PROLE_12 == before[2] and p.cv.SQUAD_PROLE_14 == before[3] end
    J.partyRoleCommand(p, sq, '9', 'melee', h)
    check(unchanged() and said[#said - 1]:find('No squad mate 9 (see !squad list)', 1, true) and said[#said]:find('<slot|name|me>', 1, true),
          'an unknown slot is refused, with where to look and the usage; nothing stored')
    J.partyRoleCommand(p, sq, '3', 'melee', h)
    check(unchanged() and said[#said - 1]:find('No squad mate 3', 1, true), 'the gap slot 3 (no mate) is refused')
    J.partyRoleCommand(p, sq, 'Bob', 'melee', h)
    check(unchanged() and said[#said - 1]:find('No squad mate Bob', 1, true), 'an unknown name is refused')
    J.partyRoleCommand(p, sq, 'Test', 'melee', h)
    check(unchanged(), 'a partial name is not a match (exact name only, as the other !squad commands)')
    J.partyRoleCommand(p, sq, '2', 'healer', h)
    check(unchanged() and said[#said]:find('<slot|name|me> tank|melee|mage|ranged|auto', 1, true), 'an unknown role is refused with the usage')
    J.partyRoleCommand(p, sq, 'me', 'ranged', h)
    check(p.cv.SQUAD_PROLE_ME == 4 and p.lv.SQUAD_ROLE == 4 and unchanged(), 'me -> ranged, stored and live; the mates untouched')
    J.partyRoleCommand(p, sq, 'ME', 'auto', h)
    check(p.cv.SQUAD_PROLE_ME == 0 and p.lv.SQUAD_ROLE == 0, 'ME (any case) -> auto')
    J.partyRoleCommand(p, sq, 'me', 'ranged', h)
    J.partyRoleCommand(p, sq, nil, nil, h)
    local list = said[#said - 2]
    check(list:find('you ranged', 1, true) and list:find('[1] Rook tank', 1, true) and list:find('[2] Dame melee', 1, true)
          and list:find('[4] Testwar mage', 1, true), 'the list shows each mate\'s slot: ' .. list)
    check(said[#said - 1]:find('<slot|name|me>', 1, true) and said[#said - 1]:find('!squad list', 1, true) and #said[#said - 1] <= 140,
          'the usage explains <slot|name|me> and points to !squad list (fits a chat line): ' .. said[#said - 1])
    -- a role set by slot reaches the engine and a role-song Bard (BRD role-override test)
    local whmMate = ent({ id = 703, job = 3, master = p })
    whmMate:setLocalVar('SQUAD_ID', 14)
    J.partyRoleCommand(p, sq, '4', 'melee', h)
    J.applyRoles(whmMate)
    local bard = ent({ id = 704, job = 10 })
    J.analyse(bard, { G.decodeRule('1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,', 1), G.decodeRule('1,CASTER,NOT_STATUS,BALLAD,,,f,MAGES_BALLAD,', 2) })
    check(whmMate:getLocalVar('SQUAD_ROLE') == 2 and J.songRecipient(bard, whmMate, xi.magic.spell.VALOR_MINUET)
          and not J.songRecipient(bard, whmMate, xi.magic.spell.MAGES_BALLAD), 'a WHM mate set to melee by slot: gets Minuet, no Ballad')
    J.partyRoleCommand(p, sq, 'testwar', 'mage', h)
    J.applyRoles(whmMate)
    check(whmMate:getLocalVar('SQUAD_ROLE') == 3 and J.songRecipient(bard, whmMate, xi.magic.spell.MAGES_BALLAD)
          and not J.songRecipient(bard, whmMate, xi.magic.spell.VALOR_MINUET), 'set to mage by name: Ballad, no Minuet')
    J.partyRoleCommand(p, sq, '4', 'auto', h)
    J.partyRoleCommand(p, sq, '1', 'tank', h)
    local mob = ent({ id = 701, job = 1, master = p })
    mob:setLocalVar('SQUAD_ID', 11)
    J.applyRoles(mob)
    check(mob:getLocalVar('SQUAD_ROLE') == 1 and p.lv.SQUAD_ROLE == 4, 'applyRoles: the mate and you get the stored roles')
    J.partyRoleCommand(p, sq, '1', 'auto', h)
    J.applyRoles(mob)
    check(mob:getLocalVar('SQUAD_ROLE') == 0 and J.inRole(mob, 2) and not J.inRole(mob, 1), 'auto: back to the main job (WAR = melee, not tank)')
    local pld = ent({ id = 702, job = 7 })
    check(J.inRole(pld, 1) and J.inRole(pld, 2) and not J.inRole(pld, 3), 'a PLD by job: tank and melee (the engine\'s groups), not mage')
    pld:setLocalVar('SQUAD_ROLE', 3)
    check(J.inRole(pld, 3) and not J.inRole(pld, 1), 'a PLD set to mage: only mage')
end

-- ================================================================= 5. Sneak Attack / Trick Attack under the Rule Set
section('THF: Gambits decides SA/TA, the squad positions (J.thiefManaged)')
do
    local now = 1000
    local tank = ent({ id = 2, job = 7 })
    local enemy = ent({ id = 50, target = tank })
    local thf = ent({ id = 3, job = 6 })
    thf:setLocalVar('SQUAD_SATA_MANAGED', 1)
    local function ask(id, at) thf:setLocalVar('SQUAD_SATA_REQ', id); thf:setLocalVar('SQUAD_SATA_REQ_AT', at or now) end
    check(J.thiefManaged(thf, 75, enemy, now) == 0 and thf:getLocalVar('SQUAD_SATA_READY') == 0, 'no request: no flank, nothing ready')
    ask(J.SA)
    check(J.thiefManaged(thf, 75, enemy, now) == 1 and thf:getLocalVar('SQUAD_SATA_READY') == 0 and thf:getLocalVar('SQUAD_SATA_TGT') == 50,
          'Sneak Attack asked for: move behind the enemy (flank 1), not ready yet, the target remembered')
    thf.behind, thf.dist[50] = true, 2
    check(J.thiefManaged(thf, 75, enemy, now + 1) == 1 and thf:getLocalVar('SQUAD_SATA_READY') == J.SA, 'behind it within 4: ready (the engine may use it)')
    local other = ent({ id = 51, target = tank })
    J.thiefManaged(thf, 75, other, now + 2)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0 and thf:getLocalVar('SQUAD_SATA_READY') == 0, 'the target changed: the request is cancelled')
    ask(J.SA, now)
    thf:setLocalVar('SQUAD_SATA_TGT', 0)
    thf.behind = false
    J.thiefManaged(thf, 75, enemy, now + 9)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0 and thf:getLocalVar('SQUAD_SATA_BLOCK') == now + 9 + J.BACKOFF_SECS,
          'not in place after 8 s: cancelled, and new requests wait 10 s (no endless retries)')
    ask(J.SA, now + 10)
    J.thiefManaged(thf, 75, enemy, now + 10)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0, 'a request during the wait is cancelled at once')
    thf:setLocalVar('SQUAD_SATA_BLOCK', 0)
    enemy.target = thf
    ask(J.SA, now + 30)
    J.thiefManaged(thf, 75, enemy, now + 30)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0 and thf:getLocalVar('SQUAD_SATA_BLOCK') > 0, 'the THF has the enemy\'s attention: Sneak Attack cannot be placed - cancelled')
    enemy.target = tank
    thf:setLocalVar('SQUAD_SATA_BLOCK', 0)
    ask(J.SA, now + 40)
    J.thiefManaged(thf, 14, enemy, now + 40)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0, 'level 14 (Level Sync below 15): Sneak Attack cancelled')
    thf:setLocalVar('SQUAD_SATA_BLOCK', 0)
    ask(J.TA, now + 50)
    local f = J.thiefManaged(thf, 75, enemy, now + 50)
    check(f == 2 and thf:getLocalVar('SQUAD_SATA_READY') == 0, 'Trick Attack: move behind the tank (flank 2)')
    thf.dist[2], thf.dist[50] = 1, 3
    tank.dist[50] = 1; enemy.dist[2] = 1; enemy.dist[3] = 3
    J.thiefManaged(thf, 75, enemy, now + 51)
    check(thf:getLocalVar('SQUAD_SATA_READY') == J.TA, 'close behind the tank, the tank nearer the enemy: Trick Attack ready')
    enemy.target = nil
    thf:setLocalVar('SQUAD_SATA_BLOCK', 0)
    ask(J.TA, now + 60)
    J.thiefManaged(thf, 75, enemy, now + 60)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0, 'no one else holds the enemy (no TA partner): Trick Attack cancelled')
    enemy.target = tank
    thf:setLocalVar('SQUAD_SATA_BLOCK', 0)
    ask(J.SA, now + 70)
    thf.effects[xi.effect.SNEAK_ATTACK] = true
    check(J.thiefManaged(thf, 75, enemy, now + 70) == 1 and thf:getLocalVar('SQUAD_SATA_REQ') == 0,
          'Sneak Attack is on: keep the place behind until the hit uses it; the request is done')
    thf.effects[xi.effect.SNEAK_ATTACK] = nil
    ask(J.SA, now + 80)
    J.thiefManaged(thf, 75, nil, now + 80)
    check(thf:getLocalVar('SQUAD_SATA_REQ') == 0 and thf:getLocalVar('SQUAD_SATA_BLOCK') == 0, 'the enemy died / no target: cancelled, no wait')
    ask(J.SA, now + 85)
    thf.recast[J.SA] = true
    check(J.thiefManaged(thf, 75, enemy, now + 85) == 0 and thf:getLocalVar('SQUAD_SATA_REQ') == 0 and thf:getLocalVar('SQUAD_SATA_BLOCK') == 0,
          'Sneak Attack on recast (by ability id, as trusts keep it): no flank, the request is dropped without a wait')
    thf.recast[J.SA] = nil

    -- the weapon skill hold's Lua side (the hold itself is HoldWeaponSkill in gambits_container.cpp)
    thf:setLocalVar('SQUAD_SATA_WSHOLD', 1)
    thf.tp = 1500
    thf:setLocalVar('SQUAD_WS_HOLD_UNTIL', now + 100 + 8) -- (started at now + 100)
    J.thiefManaged(thf, 75, enemy, now + 103)
    check(thf:getLocalVar('SQUAD_WS_HOLD_UNTIL') == now + 108, 'the hold runs while the rules get their evaluation (3 s)')
    J.thiefManaged(thf, 75, enemy, now + 104)
    check(thf:getLocalVar('SQUAD_WS_HOLD_UNTIL') == 1, 'nothing asked for after 4 s: the hold ends early (the weapon skill may go)')
    thf:setLocalVar('SQUAD_WS_HOLD_UNTIL', now + 208)
    ask(J.SA, now + 204)
    J.thiefManaged(thf, 75, enemy, now + 205)
    check(thf:getLocalVar('SQUAD_WS_HOLD_UNTIL') == now + 208, 'a Sneak Attack is being prepared: the hold keeps its hard 8 s limit, no more')
    enemy.target = thf
    J.thiefManaged(thf, 75, enemy, now + 206)
    check(thf:getLocalVar('SQUAD_WS_HOLD_UNTIL') == 1, 'the THF took the enemy\'s attention: the hold ends at once')
    enemy.target = tank
    thf.tp = 200
    J.thiefManaged(thf, 75, enemy, now + 207)
    check(thf:getLocalVar('SQUAD_WS_HOLD_UNTIL') == 0, 'after the weapon skill (TP below 1000) the hold may start again')
end

-- ================================================================= 5b. squadThiefTick itself (squad.lua), unmanaged and managed
section('THF: squad.lua squadThiefTick - Sneak Attack recast by ability id (unmanaged), managed path unchanged')
do
    -- the real function from squad.lua (a global there; jobIds is a squad.lua local, given here)
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local a = assert(src:find('\nfunction squadThiefTick%(mob%)'))
    local b = assert(src:find('\nend\n', a, true))
    check(not src:sub(a, b):find('ABILITY, 64)', 1, true) and src:sub(a, b):find('hasRecast(xi.recast.ABILITY, xi.jobAbility.SNEAK_ATTACK)', 1, true),
          'squadThiefTick checks the Sneak Attack recast by ability id (44), not the recast id 64 a trust never has')
    check(not src:sub(a, b):find('ABILITY, 66)', 1, true) and src:sub(a, b):find('hasRecast(xi.recast.ABILITY, xi.jobAbility.TRICK_ATTACK)', 1, true),
          'squadThiefTick checks the Trick Attack recast by ability id (76), not the recast id 66 a trust never has')
    assert(loadChunk('local jobIds = { THF = 6 }\n' .. src:sub(a + 1, b + 4), '=squad.lua squadThiefTick'))()
    package.loaded['modules/custom/lua/squad_jobs'] = J
    local used = {}
    SquadUseAbility = function(_, mate, id) used[#used + 1] = { mate:getID(), id }; return 'ok' end
    local master = playerOf()
    local tank = ent({ id = 2, job = 7 })
    local enemy = ent({ id = 60, target = tank })
    local function thief(lvl)
        local t = ent({ id = 30, job = 6, lvl = lvl or 75, master = master, target = enemy })
        t.dist[60], t.dist[2] = 2, 5
        return t
    end
    local function flank(t) return t:getLocalVar('SQUAD_FLANK') end
    local SA, TA = xi.jobAbility.SNEAK_ATTACK, xi.jobAbility.TRICK_ATTACK
    check(SA == 44 and TA == 76, 'xi.jobAbility: Sneak Attack 44, Trick Attack 76 (the ids trust recasts are kept by)')

    -- unmanaged (no Rule Set with SA/TA): v0.1.55 behaviour, now with the right recast
    local t = thief()
    squadThiefTick(t)
    check(flank(t) == 1 and #used == 0, 'unmanaged, SA ready, not behind yet: flank 1 (move behind), no attempt yet')
    t.behind = true
    squadThiefTick(t)
    check(#used == 1 and used[1][2] == SA and flank(t) == 1, 'unmanaged, behind within 4: Sneak Attack used')
    used = {}
    t = thief(25) -- (no Trick Attack below 30)
    t.behind, t.recast[SA] = true, true
    squadThiefTick(t)
    check(flank(t) == 0 and #used == 0, 'REGRESSION: unmanaged, SA on recast: no Sneak Attack attempt and no flank (before: flank 1 and a try every 3 s)')
    t.vars.SQUAD_THF_T = 0
    for _ = 1, 3 do squadThiefTick(t) end
    check(flank(t) == 0 and #used == 0, 'and it stays so on later ticks')
    t.recast[64] = true -- (the recast id: never set for a trust; it must not matter)
    t.recast[SA] = nil
    squadThiefTick(t)
    check(flank(t) == 1 and #used == 1 and used[1][2] == SA, 'SA off recast again: flank 1 and Sneak Attack, whatever recast 64 says')
    used = {}
    t = thief(75)
    t.recast[SA] = true
    squadThiefTick(t)
    check(flank(t) == 2 and #used == 0, 'unmanaged, SA on recast at 75 with a tank: on to Trick Attack (flank 2 behind the tank), no SA attempt')
    -- Trick Attack on recast too (unmanaged): no TA attempt and no TA positioning behind the tank
    t.dist[2] = 1; enemy.dist[2] = 1; enemy.dist[30] = 3 -- (in the TA spot: it would be used if it were ready)
    t.vars.SQUAD_THF_T = 0
    t.recast[TA] = true
    squadThiefTick(t)
    check(flank(t) == 0 and #used == 0, 'REGRESSION: unmanaged, SA and TA on recast: no flank (before: flank 2 behind the tank) and no attempt')
    for _ = 1, 3 do squadThiefTick(t) end
    check(flank(t) == 0 and #used == 0, 'and it stays so on later ticks')
    t.recast[TA] = nil
    t.recast[66] = true -- (the recast id: never set for a trust; it must not matter)
    squadThiefTick(t)
    check(flank(t) == 2 and #used == 1 and used[1][2] == TA, 'TA off recast, in place behind the tank: Trick Attack used, whatever recast 66 says')
    used = {}
    t.recast[66], t.recast[SA] = nil, nil
    t.vars.SQUAD_THF_T = 0
    t.behind, t.dist[60] = true, 2
    squadThiefTick(t)
    check(flank(t) == 1 and #used == 1 and used[1][2] == SA, 'both ready: Sneak Attack first, as before (flank 1, used from behind)')
    used = {}
    local low = thief(29) -- (Trick Attack from 30)
    low.recast[SA] = true
    low.dist[2] = 1; enemy.dist[30] = 3
    squadThiefTick(low)
    check(flank(low) == 0 and #used == 0, 'level 29, SA on recast: no Trick Attack positioning (unchanged level rule)')
    t.recast[TA] = nil
    t.effects[xi.effect.SNEAK_ATTACK] = true
    t.recast[SA] = true
    squadThiefTick(t)
    check(flank(t) == 1, 'SA already on: keep the place behind (unchanged)')

    -- managed (the Rule Set uses SA/TA): J.thiefManaged decides; squadThiefTick never uses an ability itself
    used = {}
    t = thief(75)
    J.analyse(t, { G.decodeRule('1,SELF,TP_GTE,1000,NOT_STATUS,SNEAK_ATTACK,j,SNEAK_ATTACK,', 1) })
    check(t:getLocalVar('SQUAD_SATA_MANAGED') == 1 and t:getLocalVar('SQUAD_SATA_WSHOLD') == 1, 'managed: set up by the Rule Set (with the WS hold)')
    squadThiefTick(t)
    check(flank(t) == 0 and #used == 0, 'managed, nothing requested: no flank, no ability (the rule decides when)')
    t:setLocalVar('SQUAD_SATA_REQ', SA); t:setLocalVar('SQUAD_SATA_REQ_AT', os.time())
    squadThiefTick(t)
    check(flank(t) == 1 and t:getLocalVar('SQUAD_SATA_READY') == 0 and #used == 0, 'managed, SA requested: flank 1, not ready yet, no direct use')
    t.behind = true
    squadThiefTick(t)
    check(t:getLocalVar('SQUAD_SATA_READY') == SA and #used == 0, 'managed, in place: READY for the engine; squad.lua still uses nothing itself')
    t.recast[SA] = true
    squadThiefTick(t)
    check(flank(t) == 0 and t:getLocalVar('SQUAD_SATA_REQ') == 0 and t:getLocalVar('SQUAD_SATA_READY') == 0, 'managed, SA on recast: request dropped, no flank')
    -- the optional WS hold, through squadThiefTick
    t.recast[SA] = nil
    t.tp = 1500
    local now = os.time()
    t:setLocalVar('SQUAD_WS_HOLD_UNTIL', now + 8)
    squadThiefTick(t)
    check(t:getLocalVar('SQUAD_WS_HOLD_UNTIL') == now + 8, 'managed WS hold: still running at its start')
    t:setLocalVar('SQUAD_WS_HOLD_UNTIL', now + 3) -- (started 5 s ago, nothing requested)
    squadThiefTick(t)
    check(t:getLocalVar('SQUAD_WS_HOLD_UNTIL') == 1, 'managed WS hold: ends early when nothing is prepared after 4 s (unchanged)')
    t.tp = 200
    squadThiefTick(t)
    check(t:getLocalVar('SQUAD_WS_HOLD_UNTIL') == 0, 'managed WS hold: reset after the weapon skill (unchanged)')
    package.loaded['modules/custom/lua/squad_jobs'] = nil
    squadThiefTick = nil
end

-- ================================================================= 6. pets
section('pets: BST follows its master\'s target; DRG Spirit Link via the squad\'s own pet inspection')
do
    local enemy, other = ent({ id = 50 }), ent({ id = 51 })
    local bst = ent({ id = 10, job = 9 })
    local pet = ent({ id = 11, target = other })
    J.petCare(bst, pet, enemy, 100)
    check(#bst.calls == 1 and bst.calls[1][2] == 50, 'the jug pet fights another enemy: sent to the master\'s target')
    pet.target = enemy
    J.petCare(bst, pet, enemy, 101)
    check(#bst.calls == 1, 'already on it: nothing')
    pet.target = nil
    J.petCare(bst, pet, enemy, 102)
    check(#bst.calls == 1, 'an idle pet: left to SquadPetAttack (squad.lua petTick), as before')

    local used = {}
    SquadUseAbility = function(master, mate, id) used[#used + 1] = { mate:getID(), id }; return 'ok' end
    local p = playerOf()
    local drg = ent({ id = 20, job = 14, hpp = 80, master = p })
    local wyvern = ent({ id = 21, hpp = 30 })
    J.analyse(drg, nil)
    J.petCare(drg, wyvern, enemy, 200)
    check(#used == 1 and used[1][2] == xi.ja.SPIRIT_LINK and drg:getLocalVar('SQUAD_SLINK_NEXT') == 205,
          'wyvern at 30 %, DRG at 80 %: Spirit Link through squad.cpp\'s own ability path (its checks apply)')
    J.petCare(drg, wyvern, enemy, 203)
    check(#used == 1, 'at most one try every 5 s')
    drg.recast[xi.ja.SPIRIT_LINK] = true
    J.petCare(drg, wyvern, enemy, 206)
    check(#used == 1, 'Spirit Link on recast: not tried')
    drg.recast[xi.ja.SPIRIT_LINK] = nil
    drg.hpp = 50
    J.petCare(drg, wyvern, enemy, 212)
    check(#used == 1, 'the DRG below 60 %: it keeps its own HP')
    drg.hpp, wyvern.hpp = 90, 70
    J.petCare(drg, wyvern, enemy, 220)
    check(#used == 1, 'the wyvern at 70 %: nothing to do')
    wyvern.hpp = 20
    J.analyse(drg, { G.decodeRule('1,SELF,ALWAYS,,,,j,SPIRIT_LINK,', 1) })
    J.petCare(drg, wyvern, enemy, 230)
    check(#used == 1, 'the Rule Set uses Spirit Link itself: the rule decides, the squad does not')
    J.analyse(drg, nil)
    drg.lvl = 24
    J.petCare(drg, wyvern, enemy, 240)
    check(#used == 1, 'below level 25 (no Spirit Link yet): nothing')
    drg.lvl = 75
    engine2Off()
    J.petCare(drg, wyvern, enemy, 250)
    J.petCare(bst, ent({ id = 12, target = other }), enemy, 250)
    check(#used == 1 and #bst.calls == 1, 'without the job expansion\'s xi_map: pets exactly as before')
    engine2On()
end

-- ================================================================= 7. the editor: MOD_LT, advanced conditions, labels
section('editor: MOD_LT value, advanced conditions ("More conditions"), new target and action kinds')
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local sent, clock = {}, 100
M.init({ now = function() return clock end, queue_command = function(l) sent[#sent + 1] = l end })
local S = M._S
S.server = { version = 6, maxRules = 32, maxLine = 120, maxChunks = 64 }
local function catalogFor(slot, flags)
    local lines = run('catm 30 ' .. slot .. (flags and (' ' .. flags) or ''))
    local items, endF = {}, nil
    for _, l in ipairs(lines) do local ff = F(string.sub(l, 1, 150)); if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end end
    return M.parse_catalog(items, endF)
end
do
    local cat = catalogFor(9, 'jm')
    check(cat ~= nil and cat.conds.MOD_LT and cat.conds.MOD_LT.kind == 'm', 'the v6 catalog parses, MOD_LT with the kind m')
    check(M.mod_parse('UTSUSEMI.2') == 'UTSUSEMI' and select(2, M.mod_parse('BLINK.3')) == 3 and M.mod_parse('STONESKIN.5') == nil
          and M.mod_parse('UTSUSEMI') == nil and M.mod_parse('utsusemi.2') == nil, 'mod_parse: NAME.number, known names only')
    check(M.mod_problem('UTSUSEMI.2') == nil and M.mod_problem('UTSUSEMI.8') ~= nil and M.mod_problem('BLINK.0') ~= nil and M.mod_problem('X.1') ~= nil,
          'mod_problem: the ranges of the server (Utsusemi 1-7, Blink 1-3)')
    check(M.cond_text('MOD_LT', 'UTSUSEMI.2', cat) == 'Utsusemi shadows below 2' and M.cond_short('MOD_LT', 'BLINK.1', cat) == 'Images < 1',
          'readable: "' .. M.cond_text('MOD_LT', 'UTSUSEMI.2', cat) .. '", "' .. M.cond_short('MOD_LT', 'BLINK.1', cat) .. '"')
    local r = { on = true, target = 'SELF', cond = 'HPP_LT', arg = '50', kind = 'spell', name = 'UTSUSEMI_NI' }
    M.set_condition(r, 1, 'MOD_LT', cat)
    check(r.arg == 'UTSUSEMI.2', 'choosing Shadows starts at "Utsusemi shadows below 2"')
    local d = { name = 'Test', job = 'NIN', rules = { r } }
    check(M.check_draft(d, cat) == nil, 'the draft passes the editor\'s checks')
    r.arg = 'UTSUSEMI.9'
    check((M.check_draft(d, cat) or ''):find('1-7', 1, true), 'a number out of range is caught before the save: ' .. tostring(M.check_draft(d, cat)))
    r.arg = 'UTSUSEMI.2'
    check(M.decode_rule(M.encode_rule(r)).arg == 'UTSUSEMI.2', 'the editor codec keeps "UTSUSEMI.2"')

    local function keys(list) local out = {} for _, s in ipairs(list) do out[#out + 1] = s.key end return table.concat(out, ',') end
    local basic = keys(M.subjects_for(1, 'TARGET', cat, false))
    local more = keys(M.subjects_for(1, 'TARGET', cat, true))
    check(not basic:find('SKILLCHAIN', 1, true) and not basic:find('LEVEL', 1, true) and more:find('SKILLCHAIN', 1, true)
          and more:find('LEVEL', 1, true) and more:find('TIMER', 1, true) and more:find('RANDOM', 1, true),
          'advanced subjects only with "More conditions": ' .. more)
    check(basic:find('SHADOWS', 1, true) ~= nil, 'Shadows / images is a common subject (the Ninja template needs it)')
    check(not keys(M.subjects_for(1, 'SELF', cat, true)):find('SKILLCHAIN', 1, true), 'Skillchain only with the target Enemy')
    local old = catalogFor(9, 'j')
    check(not keys(M.subjects_for(1, 'SELF', old, true)):find('SHADOWS', 1, true), 'a catalog without MOD_LT: Shadows not offered')
    -- every server condition has a class; hidden ones are still shown in a saved rule
    local unclassified = {}
    for name in pairs(R.CONDITIONS) do
        if M.CONDITION_CLASS[name] == nil then unclassified[#unclassified + 1] = name end
    end
    table.sort(unclassified)
    check(#unclassified == 0, 'every Rule Set condition is common, advanced or hidden; unclassified: ' .. table.concat(unclassified, ','))
    check(M.CONDITION_CLASS.MOD_LT == 'common' and M.CONDITION_CLASS.MB_AVAILABLE == 'advanced' and M.CONDITION_CLASS.NO_SAMBA == 'hidden'
          and M.CONDITION_CLASS.CASTING_DEBUFF == 'hidden', 'MOD_LT common, MB_AVAILABLE advanced, NO_SAMBA / CASTING_DEBUFF hidden')
    local saved = { on = true, target = 'TARGET', cond = 'CASTING_DEBUFF', kind = 'spell', name = 'STUN' }
    check(M.protected(saved, cat) == nil and M.rule_summary(saved, cat) ~= '' and M.check_draft({ name = 'X', job = 'DRK', rules = { saved } }, cat) == nil,
          'a saved rule with a hidden condition is shown, editable and saved unchanged')
    check(M.target_label('TRIGGER_SELF_ACTION_TARGET') == 'Check Self -> Act on Enemy' and M.TARGET_SHORT.TRIGGER_SELF_ACTION_TARGET == 'Self->Enemy'
          and M.TARGET_HELP.TRIGGER_SELF_ACTION_TARGET:find('checked on the squad mate itself', 1, true), 'the new target\'s label, short name and help')
    local kinds = table.concat(M.NEW_KINDS, ',')
    check(kinds == 'family,spell,ja,ranged,nuke,burst' and M.KIND_HELP.burst and M.KIND_HELP.nuke and M.KIND_HELP.ranged,
          'new rules may use ranged, nuke and burst, each with its explanation')
    check(M.check_draft({ name = 'X', job = 'RNG', rules = { { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'ranged' } } }, cat) == nil,
          'a ranged rule passes the checks')
end

-- ================================================================= 8. the job templates against the server's tables
section('job templates: every name and level from the server\'s data; valid; never applied by themselves')
do
    local spells = dofile(LUA_DIR .. '/squad_spell_jobs_data.lua')
    local function spellLevel(name, job)
        for _, row in pairs(spells.spells) do if row[1] == name then return row[2][job], row.ct end end
        return nil
    end
    -- the first spell of each family the templates use (a family action uses the best tier the mate has)
    local FAMILY_FIRST = { CURE = 'CURE', BIO = 'BIO', VALOR_MINUET = 'VALOR_MINUET', MARCH = 'ADVANCING_MARCH', MAGES_BALLAD = 'MAGES_BALLAD',
                           KNIGHTS_MINNE = 'KNIGHTS_MINNE', ELEGY = 'BATTLEFIELD_ELEGY', FOE_REQUIEM = 'FOE_REQUIEM' }
    -- the levels each template's "about" text states ('sub' = only with a sub job, said so in the text)
    local EXPECT = {
        MNK = { CHAKRA = 35, DODGE = 15, FOCUS = 25, BOOST = 5 },
        BLM = { ASPIR = 25, BIO = 10 },
        THF = { SNEAK_ATTACK = 15, TRICK_ATTACK = 30, STEAL = 5 },
        DRK = { STUN = 37, DRAIN = 10, ASPIR = 20, LAST_RESORT = 15, BIO = 15 },
        BST = { CURE = 'sub', BERSERK = 'sub' },
        BRD = { VALOR_MINUET = 3, MARCH = 29, MAGES_BALLAD = 25, KNIGHTS_MINNE = 1, ELEGY = 39, FOE_REQUIEM = 7 },
        RNG = { SHARPSHOT = 1, BARRAGE = 30 },
        SAM = { HASSO = 25, SEIGAN = 35, THIRD_EYE = 15, MEDITATE = 30 },
        NIN = { UTSUSEMI_NI = 37, UTSUSEMI_ICHI = 12, PROVOKE = 'sub', KURAYAMI_ICHI = 19, HOJO_ICHI = 23 },
        DRG = { HIGH_JUMP = 35, JUMP = 10 },
        BLU = { HEALING_BREEZE = 16, POLLEN = 1, HEAD_BUTT = 12, COCOON = 8, METALLIC_BODY = 8, REFUELING = 48 },
        COR = { CHAOS_ROLL = 14, HUNTERS_ROLL = 11 },
    }
    local familyList = {}
    for _, f in ipairs(catEntries(run('catm 40 1 jm'), 'f')) do familyList[f] = true end
    for slot, job in ipairs(JOB_ORDER) do
        local jobId = JOB_IDS[job]
        local list = M.templates_for(job)
        check(#list >= 1, job .. ': has a starter template (' .. tostring(list[1] and list[1].name) .. ')')
        local cat = catalogFor(slot, 'jm')
        for ti, t in ipairs(list) do
            check(#t.name <= M.NAME_MAX and t.name:match('^[%w %-]+$') and type(t.about) == 'string' and #t.about > 40,
                  job .. ': "' .. t.name .. '" has a valid name and an explanation')
            sent = {}
            local d, why = M.new_from_template(job, ti, cat)
            check(d and #d.rules == #t.rules and d.num == 0 and d.dirty and #sent == 0,
                  job .. ' / ' .. t.name .. ': a new, unsaved draft with every rule (nothing sent, saved, assigned) - ' .. tostring(why))
            check(d and M.check_draft(d, cat) == nil, job .. ' / ' .. t.name .. ': passes the editor\'s checks - ' .. tostring(d and M.check_draft(d, cat)))
            local set = { format = 'xifo-ruleset', version = 1, num = 1, id = 'tpl.' .. job, name = t.name, job = job, rules = {} }
            for i, r in ipairs(t.rules) do
                set.rules[i] = G.decodeRule(M.encode_rule(r), i)
                local p = set.rules[i] and problems(set.rules[i]) or 'not decoded'
                check(p == '', string.format('%s rule %d passes the server\'s Rule Set checks: %s', t.name, i, p))
                for _, pair in ipairs({ { r.cond, r.arg }, { r.cond2, r.arg2 } }) do
                    if pair[1] == 'STATUS' or pair[1] == 'NOT_STATUS' then
                        check(xi.effect[pair[2]] ~= nil, string.format('%s rule %d: the effect %s exists', t.name, i, tostring(pair[2])))
                    end
                end
                local want = EXPECT[job][r.name or '']
                if r.kind == 'ja' then
                    local info = R.jaInfo(r.name)
                    if want == 'sub' then
                        check(info and info.job ~= jobId, string.format('%s: %s comes from a sub job (said so in the text)', t.name, r.name))
                    else
                        check(info and info.job == jobId and info.level == want,
                              string.format('%s: %s is a %s ability of level %s (expected %s)', t.name, r.name, job, tostring(info and info.level), tostring(want)))
                    end
                    check(r.name ~= 'YONIN' and r.name ~= 'INNIN' and r.name ~= 'SEKKANOKI' and r.name ~= 'PIANISSIMO',
                          t.name .. ': no Wings of the Goddess ability (may be switched off)')
                elseif r.kind == 'family' or r.kind == 'spell' then
                    if r.kind == 'family' then
                        check(familyList[r.name] and xi.magic.spellFamily[r.name] ~= nil, string.format('%s: the family %s is offered', t.name, r.name))
                    end
                    local lvl = spellLevel(r.kind == 'family' and FAMILY_FIRST[r.name] or r.name, jobId)
                    if want == 'sub' then
                        check(lvl == nil, string.format('%s: %s is not a %s spell (it comes from the sub job, said so)', t.name, r.name, job))
                    else
                        check(lvl == want, string.format('%s: %s is a %s spell from level %s (expected %s)', t.name, r.name, job, tostring(lvl), tostring(want)))
                    end
                end
            end
            local usable = R.usableRules(set, { job = jobId, level = 75, subJob = 0, subLevel = 0, owner = srv })
            check(#usable >= 1, string.format('%s 75 with no sub job: %d of %d rules usable', t.name, #usable, #set.rules))
            local mob = ent({ id = 800 + slot * 10 + ti, job = jobId })
            J.analyse(mob, set.rules)
            if job == 'THF' then
                check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 1 and mob:getLocalVar('SQUAD_SATA_WSHOLD') == (ti == 2 and 1 or 0),
                      t.name .. ': SA/TA managed; the weapon skill hold ' .. (ti == 2 and 'on (TP rules)' or 'off'))
            elseif job == 'BRD' then
                check(mob:getLocalVar('SQUAD_SONG_ROLES') == 1, t.name .. ': its songs go by role')
            else
                check(mob:getLocalVar('SQUAD_SATA_MANAGED') == 0 and mob:getLocalVar('SQUAD_SONG_ROLES') == 0, t.name .. ': no THF/BRD handling')
            end
        end
    end
    local function hasRanged(job) for _, r in ipairs(M.TEMPLATES[job][1].rules) do if r.kind == 'ranged' then return true end end return false end
    check(hasRanged('RNG') and hasRanged('COR'), 'RNG and COR keep an explicit ranged attack (a Rule Set replaces v0.1.55\'s automatic one)')
    local nin = M.TEMPLATES.NIN[1].rules
    check(nin[1].cond == 'MOD_LT' and nin[1].arg == 'UTSUSEMI.2' and nin[1].name == 'UTSUSEMI_NI' and nin[2].arg == 'UTSUSEMI.1'
          and nin[2].name == 'UTSUSEMI_ICHI' and nin[3].on == false and nin[3].name == 'PROVOKE',
          'Basic Ninja: Ni below 2 shadows, Ichi at none, Provoke there but switched off')
    local blm = M.TEMPLATES.BLM[1].rules
    check(blm[1].cond == 'MB_AVAILABLE' and blm[1].kind == 'burst' and blm[2].target == 'TRIGGER_SELF_ACTION_TARGET' and blm[4].kind == 'nuke',
          'Basic Black Mage: magic burst first, Aspir by its own MP, nuke last')
    check(#M.templates_for('SMN') == 0 and #M.templates_for('PUP') == 0, 'no SMN or PUP template (see the report)')

    -- an older server (no TRIGGER_SELF_ACTION_TARGET, no MOD_LT): the rules it cannot hold are left out, never changed
    local oldCat = catalogFor(9, 'j')
    oldCat.targets = { 'SELF', 'PARTY', 'TANK', 'CASTER', 'MELEE', 'RANGED', 'TOP_ENMITY', 'TARGET', 'MASTER' }
    local dn = M.new_from_template('NIN', 1, oldCat)
    check(dn and #dn.rules == 3 and dn.rules[1].name == 'PROVOKE' and S.message:find('2 rule', 1, true) and S.messageWarn,
          'NIN on an older server: the two Utsusemi rules are left out, and the player is told: ' .. tostring(S.message))
    local dd = M.new_from_template('DRG', 1, oldCat)
    check(dd == nil, 'DRG on an older server: every rule needs the new target - no draft, an explanation instead')
    check(M.TEMPLATES.NIN[1].rules[1].cond == 'MOD_LT', 'the template itself is never changed')
end

-- ================================================================= 9. the C++: specifications and source shapes
section('C++ (specification tables and source shapes, NOT the C++ itself)')
do
    -- resonanceOf (gambits_container.cpp): a tier 0 skillchain effect's power holds up to 3 properties, one nibble each;
    -- a tier > 0 effect (Light, Darkness, Light II, Darkness II ...) holds its skillchain TYPE. The old closer decode
    -- read nibbles from Darkness II's 16 and found Transfixion-like garbage, so no closer matched.
    local function resonanceOf(power, tier)
        if tier > 0 then return { power } end
        local out = {}
        for shift = 0, 8, 4 do
            local v = math.floor(power / (2 ^ shift)) % 16
            if v ~= 0 then out[#out + 1] = v end
        end
        return out
    end
    local DARKNESS_II = 16
    check(#resonanceOf(DARKNESS_II, 2) == 1 and resonanceOf(DARKNESS_II, 2)[1] == DARKNESS_II, 'Darkness II (tier 2): one property, Darkness II')
    local old = resonanceOf(DARKNESS_II, 0)
    check(#old == 1 and old[1] == 1, 'the old nibble decode of 16 gives property 1 (not Darkness II): the bug this fixes')
    local three = resonanceOf(1 + 2 * 16 + 3 * 256, 0)
    check(#three == 3 and three[1] == 1 and three[2] == 2 and three[3] == 3, 'tier 0: three nibbles, in order')

    -- BestBurstSpell: of the damage spells of the window's elements that are available, cast in time (cast + 0.5 s margin
    -- <= what is left of the window): the lowest resistance rank, then the highest id (the strongest tier), then the
    -- shorter cast. Nothing fits: no spell (the rule waits).
    local function best(cands, remaining)
        local pick
        for _, c in ipairs(cands) do
            if c.available and c.cast + 0.5 <= remaining then
                if pick == nil or c.rank < pick.rank or (c.rank == pick.rank and (c.id > pick.id or (c.id == pick.id and c.cast < pick.cast))) then
                    pick = c
                end
            end
        end
        return pick and pick.id or nil
    end
    local fire3 = { id = 146, rank = 0, cast = 3.0, available = true }
    local fire2 = { id = 145, rank = 0, cast = 2.5, available = true }
    local thunder3 = { id = 166, rank = -1, cast = 3.0, available = true }
    check(best({ fire2, fire3 }, 6) == 146, 'the highest tier when it fits')
    check(best({ fire2, fire3 }, 3.2) == 145, 'Fire III does not end in time (3.0 + 0.5 > 3.2): Fire II')
    check(best({ fire2, fire3, thunder3 }, 6) == 166, 'the element the enemy resists least wins')
    check(best({ fire2, fire3 }, 2.5) == nil, 'nothing ends in time: no spell')
    fire3.available = false
    check(best({ fire2, fire3 }, 6) == 145, 'Fire III on recast / not enough MP: Fire II')

    local src = SERVER_ROOT .. '/src/map'
    local gc = assert(readAll(src .. '/ai/helpers/gambits_container.cpp'), 'gambits_container.cpp')
    local gh = assert(readAll(src .. '/ai/helpers/gambits_container.h'), 'gambits_container.h')
    local tc = assert(readAll(src .. '/ai/controllers/trust_controller.cpp'), 'trust_controller.cpp')
    local be = assert(readAll(src .. '/entities/battle_entity.cpp'), 'battle_entity.cpp')
    local sc = assert(readAll(SERVER_ROOT .. '/modules/custom/cpp/squad.cpp'), 'squad.cpp')
    local function count(text, needle) local n, at = 0, 1 while true do local i = text:find(needle, at, true) if not i then return n end n, at = n + 1, i + 1 end end
    check(gh:find('MOD_LT%s*=%s*43') and gc:find('case G_CONDITION::MOD_LT', 1, true), 'MOD_LT = 43 in the header; the engine handles it')
    check(gc:find('MagicBurstReaction = std::chrono::seconds(1)', 1, true) and count(gc, 'GetStartTime() + MagicBurstReaction') == 2,
          'the magic burst reaction is 1 s (MB_AVAILABLE and the Lunge burst)')
    local scBlock = gc:match('case G_CONDITION::SC_AVAILABLE(.-)case G_CONDITION::NOT_SC_AVAILABLE') or ''
    check(scBlock:find('3s', 1, true) ~= nil and scBlock:find('MagicBurstReaction', 1, true) == nil, 'the weapon skill chaining window keeps 3 s')
    check(count(gc, 'resonanceProperties = resonanceOf(PSCEffect)') == 3, 'all three weapon skill closers decode with resonanceOf (native, Custom, close-only)')
    check(gc:find('BestBurstSpell(resolvedTarget)', 1, true) and gc:find('auto CGambitsContainer::BestBurstSpell', 1, true),
          'the magic burst spell is chosen by BestBurstSpell (one decider, in C++)')
    check(gc:find('SQUAD_SATA_MANAGED', 1, true) and gc:find('SQUAD_SATA_READY', 1, true) and gc:find('if (HoldWeaponSkill(target))', 1, true),
          'SA/TA wait for the squad\'s position; TryTrustSkill asks HoldWeaponSkill first')
    local req = gc:match('SQUAD_SATA_MANAGED"%) != 0 &&(.-)SetLocalVar%("SQUAD_SATA_REQ"') or ''
    check(req:find('HasRecast(xi::RecastType::Ability, static_cast<xi::Recast>(abilityId), 0s)', 1, true) ~= nil,
          'an SA/TA on recast is not requested at all (the thief does not move for it)')
    check(gc:find('GetTier() == 0 && PSCEffect->GetStartTime() + 3s < timer::now()', 1, true) and gc:find('health.tp >= 3000', 1, true),
          'the hold never gives up a closing window and never holds at 3000 TP')
    check(tc:find('songOnSelf', 1, true) and tc:find('HasStatusEffect(xi::StatusEffect::Pianissimo)', 1, true)
          and tc:find('(validTargets == TARGET_SELF || songOnSelf) ? EntityId(POwner) : target', 1, true),
          'trust_controller.cpp: a party song is sung on the Bard itself (not with Pianissimo)')
    check(be:find('xi.squad.songRecipient', 1, true) and be:find('SQUAD_SONG_ROLES', 1, true) and be:find('TYPE_TRUST', 1, true),
          'battle_entity.cpp: the recipients of a squad Bard\'s song are filtered only when its rules sing by role')
    check(sc:find('"SquadJobExpansionEngine"', 1, true), 'squad.cpp registers SquadJobExpansionEngine (the Lua side\'s gate)')
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
