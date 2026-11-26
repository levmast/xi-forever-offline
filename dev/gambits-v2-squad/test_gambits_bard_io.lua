-- Gambits 0.3.3: Bard song tiers (STATUS / NOT_STATUS for one song of a song type, song roles per song) and Rule Set
-- import / export, with their interaction. Stand-in tests, no game, no Ashita.
--   luajit test_gambits_bard_io.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                   <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> <server root>
-- A  the song data: the editor's song tiers against the server's enhancing_song.lua; the C++ and the engine marker
-- B  squad_rulesets.lua: { effect = NAME, tier = n } accepted / refused, packed for the engine (R.effectArg)
-- C  gambits_squad.lua (version 8): the rule codec carries "EFFECT.tier" both ways; every older form is unchanged
-- D  squad_jobs.lua: role songs per song (Victory March -> Tank, Advancing March -> Melee stay apart); families as before
-- E  the editor: tier parsing, labels, the local checks (server 7 vs 8), the real BRD catalog from the real server
-- F  import / export: the format, every refusal (cut, changed, newer format, broken rule, too many, duplicates), names
-- G  the round trip Export -> Import -> Save (real server, real store, files in the work folder) -> Reopen -> Apply,
--    tier conditions unchanged at every step; sets without tiers unchanged too
-- Gameplay and the real ImGui are proven only in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER_ROOT,
       'usage: test_gambits_bard_io.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server-root')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function readAll(p) local f = io.open(p, 'rb'); if not f then return nil end local s = f:read('*a'); f:close(); return s end
local function deq(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= 'table' then return a == b end
    for k, v in pairs(a) do if not deq(v, b[k]) then return false end end
    for k in pairs(b) do if a[k] == nil then return false end end
    return true
end
local loadChunk = loadstring or load
local sep = package.config:sub(1, 1)

-- ---------------------------------------------------------------- the server side, from the server's own files
dofile(GAMBITS)
xi = rawget(_G, 'xi') or {}
dofile(SERVER_ROOT .. '/scripts/enum/effect.codegen.lua')
dofile(SERVER_ROOT .. '/scripts/enum/mod.codegen.lua')
dofile(SERVER_ROOT .. '/scripts/enum/magic.lua')
dofile(JA_ENUM)
xi.effectFlag = xi.effectFlag or { DISPELABLE = 1 }
xi.objType = { PC = 1, TRUST = 2 }
xi.settings = { main = { RESTRICT_CONTENT = 1, ENABLE_COP = 1, ENABLE_ROTZ = 1, ENABLE_TOAU = 1, ENABLE_WOTG = 1, ENABLE_ABYSSEA = 1,
                         ENABLE_SOA = 1 } }
SquadOwnerMerit = function() return 0 end
SquadJobExpansionEngine = function() return 1 end
SquadApplyWeaponSkills = function() return true end
local function tierOn() SquadStatusTierEngine = function() return 1 end end
local function tierOff() SquadStatusTierEngine = nil end
local function roleOn() SquadRoleFilterEngine = function() return 1 end end
local function roleOff() SquadRoleFilterEngine = nil end
roleOn()
tierOn()
GetSquadWeaponSkillIds = function() return {} end
GetAbility = function(id) return { id = id } end
-- the song families (sql/spell_list.sql: Advancing and Victory March both family 113 MARCH, every Minuet 108 ...)
local FAM = xi.magic.spellFamily
local SPELL_FAMILY = {}
for name, id in pairs(xi.magic.spell) do
    if name:find('MARCH$') then SPELL_FAMILY[id] = FAM.MARCH
    elseif name:find('^VALOR_MINUET') then SPELL_FAMILY[id] = FAM.VALOR_MINUET
    elseif name:find('^MAGES_BALLAD') then SPELL_FAMILY[id] = FAM.MAGES_BALLAD
    elseif name:find('^ARMYS_PAEON') then SPELL_FAMILY[id] = FAM.ARMYS_PAEON
    elseif name:find('^KNIGHTS_MINNE') then SPELL_FAMILY[id] = FAM.KNIGHTS_MINNE end
end
GetSpell = function(id) return { getSpellFamily = function() return SPELL_FAMILY[id] or 0 end } end

local P = WORK .. sep .. 'bard_io_rulesets_data.lua'
os.remove(P)
local St
package.preload['modules/custom/lua/squad_rulesets_data'] = function()
    local raw = St and St.readRaw(P)
    if raw == nil then error("module 'modules/custom/lua/squad_rulesets_data' not found") end
    return raw
end
package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end
package.preload['modules/custom/lua/squad_ws'] = function() return dofile(LUA_DIR .. '/squad_ws.lua') end
local R = require('modules/custom/lua/squad_rulesets')
St = require('modules/custom/lua/squad_rulesets_store')
St.PATH = P
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
local srv = { printed = {} }
function srv:getID() return 1 end
function srv:getCharVar() return 0 end
function srv:setCharVar() end
function srv:getLocalVar() return 0 end
function srv:setLocalVar() end
function srv:printToPlayer(text) self.printed[#self.printed + 1] = text end
function srv:getPartyWithTrusts() return {} end
function srv:getObjType() return xi.objType.PC end
local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local JOB = { WAR = 1, WHM = 3, BRD = 10 }
local SQUAD = {
    { slot = 1, id = 101, name = 'Lute', mjob = JOB.BRD, sjob = JOB.WHM, jobs = { [JOB.BRD] = { level = 60 }, [JOB.WHM] = { level = 30 } } },
    { slot = 2, id = 102, name = 'Rook', mjob = JOB.WAR, sjob = 0, jobs = { [JOB.WAR] = { level = 60 } } },
}
GetSquad = function() return SQUAD end
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end
local function F(line) return G.splitPlain(line, '|') end

-- ---------------------------------------------------------------- the editor
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local DATA = dofile(ADDON_DIR .. '/gambits_data.lua')
local clock, sent, prefs, clip, written = 100, {}, {}, nil, {}
local gui = { SetClipboardText = function(t) clip = t end, GetClipboardText = function() return clip end }
local api = { now = function() return clock end, queue_command = function(l) sent[#sent + 1] = l end, addon_data = DATA,
              get_pref = function(k) return prefs[k] end, set_pref = function(k, v) prefs[k] = v end,
              root = function() return WORK .. sep end, imgui = gui }
M.init(api)
local S = M._S
S.server = { version = 9, maxRules = 32, maxLine = 120, maxChunks = 64 }
local function parsed(lines)
    local items, endF = {}, nil
    for _, l in ipairs(lines) do
        local ff = F(string.sub(l, 1, 150))
        if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end
    end
    return M.parse_catalog(items, endF)
end
local nreq = 0
local function catm(slot) nreq = nreq + 1; return assert(parsed(run('catm ' .. nreq .. ' ' .. slot .. ' jm')), 'catm ' .. slot) end
local MATE = { slot = 1, name = 'Lute', job = 'BRD', level = 60, sub = 'WHM', subLevel = 30, chosen = 0, out = false }
S.mates, S.mateSlot = { MATE }, 1
local CAT = catm(1)
S.cat, S.catJob = CAT, M.catalog_key(MATE)

local function row(t) local r = { on = true }; for k, v in pairs(t) do r[k] = v end; return r end
local function encs(rules) local out = {} for i, r in ipairs(rules) do out[i] = M.encode_rule(r) end return out end

-- ================================================================= A. the song data and the engine
section('A: song tiers = the server\'s enhancing_song.lua; the C++ reads tiers; the marker')
do
    local song = assert(readAll(SERVER_ROOT .. '/scripts/globals/spells/enhancing_song.lua'))
    local byEffect, rows = {}, 0
    for spell, tier, effect in song:gmatch('%[xi%.magic%.spell%.([A-Z_]+)%s*%]%s*=%s*{%s*(%d+),%s*xi%.effect%.([A-Z_]+)') do
        rows = rows + 1
        byEffect[effect] = byEffect[effect] or {}
        byEffect[effect][tonumber(tier)] = byEffect[effect][tonumber(tier)] or {}
        table.insert(byEffect[effect][tonumber(tier)], spell)
    end
    check(rows > 60, 'enhancing_song.lua songPTable read (' .. rows .. ' songs)')
    local wrong = {}
    for effect, songs in pairs(M.SONG_TIERS) do
        if xi.effect[effect] == nil then wrong[#wrong + 1] = effect .. ' not an effect' end
        if not R.isSongEffect(effect) then wrong[#wrong + 1] = effect .. ' not a song effect' end
        for tier, name in ipairs(songs) do
            local server = byEffect[effect] and byEffect[effect][tier]
            if not (server and #server == 1 and server[1] == name) then
                wrong[#wrong + 1] = string.format('%s tier %d: editor %s, server %s', effect, tier, name, server and table.concat(server, '/') or '-')
            end
            if xi.magic.spell[name] == nil then wrong[#wrong + 1] = name .. ' not a spell' end
        end
        local n = 0
        for _ in pairs(byEffect[effect] or {}) do n = n + 1 end
        if n ~= #songs then wrong[#wrong + 1] = effect .. ': server has ' .. n .. ' tiers' end
    end
    check(#wrong == 0, 'every song type the editor offers: the same songs at the same tiers as the server: ' .. table.concat(wrong, '; '))
    -- the types left out are exactly those whose songs share a tier (Etude, Carol) or that have a single song
    local leftOut = {}
    for effect, tiers in pairs(byEffect) do
        if M.SONG_TIERS[effect] == nil then
            local shared = false
            for _, list in pairs(tiers) do shared = shared or #list > 1 end
            local n = 0
            for _ in pairs(tiers) do n = n + 1 end
            if not shared and n > 1 then leftOut[#leftOut + 1] = effect end
        end
    end
    check(#leftOut == 0, 'no song type with tiers that tell its songs apart is left out: ' .. table.concat(leftOut, ' '))
    check(byEffect.ETUDE and #byEffect.ETUDE[1] == 7 and #byEffect.CAROL[1] == 8 and #byEffect.MAZURKA[1] == 2 and M.SONG_TIERS.ETUDE == nil
          and M.SONG_TIERS.CAROL == nil and M.SONG_TIERS.MAZURKA == nil,
          'Etudes (7 at tier 1), Carols (8) and Mazurkas (2) share a tier: not offered (the separate overwrite issue is untouched)')
    check(xi.effect.REQUIEM == R.SONG_EFFECT_FIRST and xi.effect.NOCTURNE == R.SONG_EFFECT_LAST, 'the song effect range = REQUIEM..NOCTURNE (ApplyBardEffect)')

    local gc = assert(readAll(SERVER_ROOT .. '/src/map/ai/helpers/gambits_container.cpp'))
    local helper = gc:match('auto HasStatusEffectTier%(.-\n}\n')
    check(helper and helper:find('arg & 0xFFFF', 1, true) and helper:find('arg >> 16', 1, true)
          and helper:find('if (tier == 0)', 1, true) and helper:find('HasStatusEffect(effect)', 1, true)
          and helper:find('GetTier() == tier', 1, true) and helper:find('isDeleted()', 1, true),
          'gambits_container.cpp: tier 0 = HasStatusEffect(effect) as before; else the effect at exactly that tier')
    check(gc:find('predicateResults.push_back(HasStatusEffectTier(triggerTarget, predicate.condition_arg));', 1, true)
          and gc:find('predicateResults.push_back(!HasStatusEffectTier(triggerTarget, predicate.condition_arg));', 1, true)
          and not gc:find('HasStatusEffect(static_cast<xi::StatusEffect>(predicate.condition_arg))', 1, true),
          'STATUS and NOT_STATUS both use it (and nothing else reads their argument the old way)')
    local sq = assert(readAll(SERVER_ROOT .. '/modules/custom/cpp/squad.cpp'))
    check(sq:find('::lua.set_function("SquadStatusTierEngine"', 1, true), 'squad.cpp registers SquadStatusTierEngine')
    local sec = assert(readAll(SERVER_ROOT .. '/src/map/status_effect_container.cpp'))
    check(sec:find('ExistingStatusEffect->GetTier() == PStatusEffect->GetTier() && ExistingStatusEffect->GetStatusID() == PStatusEffect->GetStatusID()', 1, true),
          'ApplyBardEffect (unchanged): only the same effect AND tier overwrites, so two Marches of different tiers coexist')
end

-- ================================================================= B. squad_rulesets.lua
section('B: Rule Set checks for { effect = NAME, tier = n }')
do
    local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end
    local function r(cond) return { id = 'r1', on = true, target = 'SELF', cond = cond, action = { 'spell', 'VICTORY_MARCH' } } end
    check(problems(r({ 'NOT_STATUS', { effect = 'MARCH', tier = 2 } })) == '', 'NOT_STATUS { MARCH, 2 } accepted')
    check(problems(r({ 'STATUS', { effect = 'MINUET', tier = 5 } })) == '', 'STATUS { MINUET, 5 } accepted')
    check(problems(r({ 'NOT_STATUS', 'MARCH' })) == '', 'a plain NOT_STATUS MARCH: accepted, as before')
    check(problems(r({ 'NOT_STATUS', { effect = 'HASTE', tier = 1 } })):find('only song effects', 1, true), 'a tier on Haste: refused')
    check(problems(r({ 'NOT_STATUS', { effect = 'MARCH', tier = 0 } })):find('tier', 1, true)
          and problems(r({ 'NOT_STATUS', { effect = 'MARCH', tier = 8 } })):find('tier', 1, true)
          and problems(r({ 'NOT_STATUS', { effect = 'MARCH', tier = 1.5 } })):find('tier', 1, true), 'tier 0, 8 and 1.5: refused')
    check(problems(r({ 'NOT_STATUS', { effect = 'MARCH', tier = 2, power = 9 } })):find('unknown field', 1, true), 'an extra field: refused')
    check(problems(r({ 'NOT_STATUS', { effect = 'NOT_AN_EFFECT', tier = 1 } })):find('unknown status effect', 1, true), 'an unknown effect: refused')
    check(problems(r({ 'NOT_STATUS', { tier = 1 } })) ~= '', 'no effect name: refused')
    check(problems(r({ 'HPP_LT', { effect = 'MARCH', tier = 1 } })) ~= '', 'the table form only for STATUS / NOT_STATUS')
    tierOff()
    check(problems(r({ 'NOT_STATUS', { effect = 'MARCH', tier = 2 } })):find('updated map server', 1, true)
          and problems(r({ 'NOT_STATUS', 'MARCH' })) == '', 'without the map server that reads tiers: a tier is refused (never treated as "any"); plain names still fine')
    tierOn()
    check(R.effectArg({ effect = 'MARCH', tier = 2 }) == xi.effect.MARCH + 2 * 65536 and R.effectArg({ effect = 'MARCH', tier = 1 }) == xi.effect.MARCH + 65536,
          'packed for the engine: effect id + tier * 65536 (Victory March = ' .. tostring(R.effectArg({ effect = 'MARCH', tier = 2 })) .. ')')
    check(R.effectArg({ effect = 'HASTE', tier = 1 }) == nil and R.effectArg({ effect = 'MARCH', tier = 9 }) == nil and R.effectArg('MARCH') == nil,
          'R.effectArg packs only valid song tiers')
    check(xi.effect.NOCTURNE + 7 * 65536 < 2 ^ 32, 'the largest packed argument fits the engine\'s uint32')
    local sl = assert(readAll(LUA_DIR .. '/squad.lua'))
    check(sl:find("(spec[1] == 'STATUS' or spec[1] == 'NOT_STATUS') and type(spec[2]) == 'table'", 1, true)
          and sl:find('with a song tier needs a song effect, tier 1-7 and the updated map server - rule skipped', 1, true)
          and sl:find('R.tierReady and R.tierReady() and R.effectArg and R.effectArg(spec[2])', 1, true),
          'squad.lua ruleCondition packs a tier through R.effectArg, only with the tier map server (else the rule is skipped)')
end

-- ================================================================= C. the wire codec (gambits_squad.lua version 8)
section('C: the rule codec carries EFFECT.tier; every older form is unchanged')
do
    local hello = F(run('hello 1')[1])
    check(hello[3] == 'hello' and hello[4] == '11', 'hello: protocol version 11 (10: capability words; 11: enemy family and counts)')
    local r = assert(G.decodeRule('1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1))
    check(deq(r.cond, { 'NOT_STATUS', { effect = 'MARCH', tier = 2 } }), '"MARCH.2" -> { effect = MARCH, tier = 2 }')
    check(G.encodeRule(r, 1) == '1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 'and back, byte for byte')
    local r2 = assert(G.decodeRule('0,TANK,STATUS,PAEON.6,NOT_STATUS,MINUET.4,s,VALOR_MINUET_IV,30,50,minuet-4', 3))
    check(deq(r2.cond, { 'STATUS', { effect = 'PAEON', tier = 6 } }) and deq(r2.cond2, { 'NOT_STATUS', { effect = 'MINUET', tier = 4 } })
          and r2.retry == 30 and r2.level == 50 and r2.id == 'minuet-4' and r2.on == false, 'both conditions, retry, level, id, off')
    check(G.encodeRule(r2, 3) == '0,TANK,STATUS,PAEON.6,NOT_STATUS,MINUET.4,s,VALOR_MINUET_IV,30,50,minuet-4', 'and back')
    local plain = assert(G.decodeRule('1,PARTY,NOT_STATUS,PROTECT,,,f,PROTECT,', 1))
    check(plain.cond[2] == 'PROTECT' and G.encodeRule(plain, 1) == '1,PARTY,NOT_STATUS,PROTECT,,,f,PROTECT,', 'a plain effect: unchanged')
    local mod = assert(G.decodeRule('1,SELF,MOD_LT,UTSUSEMI.2,,,f,UTSUSEMI,', 1))
    check(deq(mod.cond, { 'MOD_LT', { mod = 'UTSUSEMI', below = 2 } }) and G.encodeRule(mod, 1) == '1,SELF,MOD_LT,UTSUSEMI.2,,,f,UTSUSEMI,', 'MOD_LT: unchanged')
    local hp = assert(G.decodeRule('1,PARTY,HPP_LT,50,,,f,CURE,', 1))
    check(hp.cond[2] == 50 and G.encodeRule(hp, 1) == '1,PARTY,HPP_LT,50,,,f,CURE,', 'numbers: unchanged')
    check(G.decodeRule('1,SELF,NOT_STATUS,MARCH.x,,,s,VICTORY_MARCH,', 1) == nil and G.decodeRule('1,SELF,NOT_STATUS,MARCH.2.1,,,s,VICTORY_MARCH,', 1) == nil,
          'a broken tier ("MARCH.x", "MARCH.2.1") is refused by the codec, never guessed')
    local dot = G.decodeRule('1,SELF,NOT_STATUS,.2,,,s,VICTORY_MARCH,', 1) -- (the codec reads ".2" as the number 0.2, as always)
    check(dot == nil or #R.ruleProblems(dot) > 0, '".2" never becomes a tier: the Rule Set check refuses it')
    check(G.encodeRule({ id = 'r1', on = true, target = 'SELF', cond = { 'NOT_STATUS', { effect = 'MARCH', tier = 2, x = 1 } }, action = { 'spell', 'VICTORY_MARCH' } }, 1) == nil,
          'a tier table with anything else in it is not carried ("?", read-only in the editor)')
end

-- ================================================================= D. song roles per song (squad_jobs.lua)
section('D: songs for party roles: a rule naming one song keeps its roles for that song')
do
    local J = dofile(LUA_DIR .. '/squad_jobs.lua')
    local function ent(o)
        local e = { vars = {}, id = o.id, job = o.job }
        function e:getID() return self.id end
        function e:getLocalVar(k) return self.vars[k] or 0 end
        function e:setLocalVar(k, v) self.vars[k] = v end
        function e:getMainJob() return self.job end
        return e
    end
    local sp = xi.magic.spell
    local bard = ent({ id = 900, job = 10 })
    local pld, war, whm = ent({ id = 901, job = 7 }), ent({ id = 902, job = 1 }), ent({ id = 903, job = 3 })
    pld:setLocalVar('SQUAD_ROLE', 1) -- (a PLD set to Tank only)
    J.analyse(bard, { G.decodeRule('1,TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1), G.decodeRule('1,MELEE,NOT_STATUS,MARCH.1,,,s,ADVANCING_MARCH,', 2) })
    check(bard:getLocalVar('SQUAD_SONG_ROLES') == 1, 'role songs: on')
    check(J.songRecipient(bard, pld, sp.VICTORY_MARCH) and not J.songRecipient(bard, war, sp.VICTORY_MARCH),
          'Victory March -> Tank: the tank gets it, the melee WAR does not')
    check(J.songRecipient(bard, war, sp.ADVANCING_MARCH) and not J.songRecipient(bard, pld, sp.ADVANCING_MARCH),
          'Advancing March -> Melee: the WAR gets it, the tank does not (before: both songs reached both roles)')
    check(not J.songRecipient(bard, whm, sp.VICTORY_MARCH) and not J.songRecipient(bard, whm, sp.ADVANCING_MARCH), 'the mage gets neither')
    check(J.songRecipient(bard, whm, sp.VALOR_MINUET) and J.songRecipient(bard, whm, sp.HONOR_MARCH),
          'songs the rules do not name (Minuet, Honor March): everyone, as before')
    -- a family rule and a specific rule of the same family: a member of either rule's roles gets the specific song
    J.analyse(bard, { G.decodeRule('1,CASTER,NOT_STATUS,MARCH,,,f,MARCH,', 1), G.decodeRule('1,TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 2) })
    check(J.songRecipient(bard, whm, sp.VICTORY_MARCH) and J.songRecipient(bard, pld, sp.VICTORY_MARCH) and not J.songRecipient(bard, war, sp.VICTORY_MARCH),
          'family March -> Mage + Victory March -> Tank: Victory reaches mage and tank (never taken away by a split), not melee')
    check(J.songRecipient(bard, whm, sp.ADVANCING_MARCH) and not J.songRecipient(bard, pld, sp.ADVANCING_MARCH),
          'Advancing March (only the family rule): mage only')
    -- families only: exactly as before
    J.analyse(bard, { G.decodeRule('1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,', 1), G.decodeRule('1,PARTY,NOT_STATUS,PAEON,,,f,ARMYS_PAEON,', 2) })
    check(J.songRecipient(bard, war, sp.VALOR_MINUET_IV) and not J.songRecipient(bard, whm, sp.VALOR_MINUET) and J.songRecipient(bard, whm, sp.ARMYS_PAEON_II),
          'family rules: Minuet -> Melee, Paeon -> Party, as before')
    -- a song for SELF/PARTY named by one rule: everyone
    J.analyse(bard, { G.decodeRule('1,PARTY,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1), G.decodeRule('1,TANK,NOT_STATUS,MARCH.1,,,s,ADVANCING_MARCH,', 2) })
    check(J.songRecipient(bard, whm, sp.VICTORY_MARCH) and not J.songRecipient(bard, whm, sp.ADVANCING_MARCH) and J.songRecipient(bard, pld, sp.ADVANCING_MARCH),
          'Victory March for the Party (everyone) + Advancing March for the Tank only')
    local plain = ent({ id = 904, job = 10 })
    J.analyse(plain, { G.decodeRule('1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1), G.decodeRule('1,SELF,NOT_STATUS,MARCH.1,,,s,ADVANCING_MARCH,', 2) })
    check(plain:getLocalVar('SQUAD_SONG_ROLES') == 0 and J.songRecipient(plain, war, sp.VICTORY_MARCH),
          'two Marches for Self (the usual AoE): no role filter at all - ordinary AoE behaviour unchanged')
end

-- ================================================================= E. the editor
section('E: the editor: tiers, labels, local checks, the real BRD catalog')
do
    check(CAT.conds.NOT_STATUS and CAT.conds.NOT_STATUS.kind == 'e' and CAT.conds.STATUS.kind == 'e', 'the real BRD catalog offers Has / Missing effect (kind e)')
    local a, t = M.tier_parse('MARCH.2')
    check(a == 'MARCH' and t == 2 and M.tier_parse('MARCH') == 'MARCH' and select(2, M.tier_parse('MARCH')) == nil, 'tier_parse')
    check(M.tier_song('MARCH.2') == 'VICTORY_MARCH' and M.tier_song('MARCH.1') == 'ADVANCING_MARCH' and M.tier_song('PAEON.6') == 'ARMYS_PAEON_VI'
          and M.tier_song('MARCH') == nil and M.tier_song('MARCH.9') == nil, 'tier_song')
    check(M.cond_text('NOT_STATUS', 'MARCH.2', CAT):find('Victory March', 1, true) and M.cond_short('NOT_STATUS', 'MARCH.2', CAT) == 'No Victory March'
          and M.cond_short('STATUS', 'MARCH', CAT) == 'Has March', 'labels: "No Victory March"; a plain effect as before')
    check(M.tier_problem('MARCH.2') == nil and M.tier_problem('MARCH') == nil and M.tier_problem('MARCH.4'):find('1-3', 1, true)
          and M.tier_problem('HASTE.1'):find('only song types', 1, true), 'tier_problem with server 8')
    local d = { num = 0, job = 'BRD', name = 'Two Marches', rules = { row({ target = 'SELF', cond = 'NOT_STATUS', arg = 'MARCH.2', kind = 'spell', name = 'VICTORY_MARCH' }) } }
    check(M.check_draft(d, CAT) == nil, 'check_draft (real catalog): a tier rule passes with server 8')
    S.server.version = 7
    check((M.check_draft(d, CAT) or ''):find('server update', 1, true), 'with a version 7 server it is refused before sending (an older server cannot keep it)')
    S.server.version = 9
    d.rules[1].arg = 'MARCH.7'
    check((M.check_draft(d, CAT) or ''):find('1-3', 1, true), 'a tier the type does not have: refused')
    d.rules[1].arg = 'MARCH'
    check(M.check_draft(d, CAT) == nil, 'a plain effect: as before')
    check(M.encode_rule(row({ target = 'SELF', cond = 'NOT_STATUS', arg = 'MARCH.2', kind = 'spell', name = 'VICTORY_MARCH' })) == '1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,'
          and M.decode_rule('1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,').arg == 'MARCH.2', 'the editor\'s codec keeps "MARCH.2" as it is')
    local src = assert(readAll(ADDON_DIR .. '/squad_editor.lua'))
    check(src:find('M.song_tier_picker(r, ak, st, cur, curTier, slot, labelW)', 1, true), 'the effect selector shows the song picker after a song type')
    local jobList = M.effect_choices(CAT, MATE)
    local listed = {}
    for _, e in ipairs(jobList) do listed[e.name] = e end
    check(listed.MARCH and listed.MINUET and listed.BALLAD and listed.PAEON and listed.MADRIGAL,
          'a BRD 60 finds its song types (March, Minuet, Ballad, Paeon, Madrigal) in the effect list, from the songs it sings')
    local sources = {}
    for _, src2 in ipairs(listed.MARCH and listed.MARCH.sources or {}) do sources[src2.from] = true end
    check(sources.ADVANCING_MARCH and sources.VICTORY_MARCH, 'March comes from Advancing and Victory March (its tooltip names them)')
    local warList = M.effect_choices(catm(2), { slot = 2, name = 'Rook', job = 'WAR', level = 60 })
    local warHas = false
    for _, e in ipairs(warList) do warHas = warHas or M.SONG_TIERS[e.name] ~= nil end
    check(not warHas, 'a WAR gets no song types in its list')
end

-- ================================================================= F. import / export
section('F: import / export: format, refusals, names, data only')
local function bardSet()
    return { num = 4, rev = 'x', job = 'BRD', name = 'Two Marches', flags = 'o', dirty = false, rules = {
        row({ target = 'SELF', cond = 'NOT_STATUS', arg = 'MARCH.2', kind = 'spell', name = 'VICTORY_MARCH', id = 'march-hi' }),
        row({ target = 'SELF', cond = 'NOT_STATUS', arg = 'MARCH.1', kind = 'spell', name = 'ADVANCING_MARCH' }),
        row({ target = 'MELEE', cond = 'NOT_STATUS', arg = 'MINUET', kind = 'family', name = 'VALOR_MINUET', retry = '30' }),
        row({ on = false, target = 'TANK', cond = 'NOT_STATUS', arg = 'MINUET.4', cond2 = 'MPP_GTE', arg2 = '20', kind = 'spell', name = 'VALOR_MINUET_IV', level = '50' }),
        row({ target = 'TARGET', cond = 'NOT_STATUS', arg = 'ELEGY', kind = 'family', name = 'ELEGY' }),
    } }
end
local TEXT
do
    local d = bardSet()
    local text = assert(M.export_text(d))
    TEXT = text
    local f = M.split(text, '|')
    check(#f == 6 and f[1] == 'GRS1' and f[2] == 'BRD' and f[3] == 'Two_Marches' and f[4] == '5', 'GRS1|BRD|Two_Marches|5|...|check: ' .. text:sub(1, 60))
    check(f[5] == table.concat(encs(d.rules), ';'), 'the rules exactly as a Save sends them (order, off, ids, retry, level, both conditions, tiers)')
    check(not text:find('[%s`]') and #text < 400, 'one line, no spaces (Discord-friendly), ' .. #text .. ' characters')
    local res, probs = M.parse_import(text, CAT, 'BRD')
    check(res and deq(encs(res.draft.rules), encs(d.rules)) and res.draft.job == 'BRD' and res.draft.name == 'Two Marches',
          'import gives back the same rules, job and name: ' .. table.concat(probs or {}, '; '))
    check(res.draft.num == 0 and res.draft.rev == nil and res.draft.flags == 'o' and res.draft.dirty == true and res.draft.readonly == nil,
          'as a NEW, unsaved, editable set (no number, no revision: it can never replace a saved set)')
    -- Discord: code blocks, inline code, line breaks, spaces around
    local pasted = '```\n' .. text:sub(1, 50) .. '\n' .. text:sub(51) .. '\n```'
    check(M.parse_import(pasted, CAT, 'BRD') ~= nil and M.parse_import('  `' .. text .. '`  ', CAT, 'BRD') ~= nil
          and M.parse_import('Here is my bard set: ' .. text, CAT, 'BRD') ~= nil, 'a code block, inline code, a wrapped line and text before it are fine')
    local function refused(t, part, label, part2)
        local r2, p2 = M.parse_import(t, CAT, 'BRD')
        local all = table.concat(p2 or {}, '; ')
        check(r2 == nil and (all:find(part, 1, true) ~= nil or (part2 ~= nil and all:find(part2, 1, true) ~= nil)), label .. ': ' .. all)
    end
    refused(text:sub(1, #text - 40), 'check number', 'cut in the rules', 'incomplete')
    refused(text:sub(1, #text - 3), 'check number', 'cut in the check number')
    refused(text:gsub('VICTORY_MARCH', 'VICTORYMARCH', 1), 'check number', 'changed (Discord ate an underscore)')
    refused((text:gsub('MARCH%.2', 'MARCH.3', 1)), 'check number', 'a tier changed by hand')
    refused('GRS2' .. text:sub(5), 'format 2', 'a newer format')
    refused('hello', 'not a Gambits share code', 'not a Rule Set')
    refused('', 'nothing to import', 'empty')
    refused(string.rep('x', M.IO_MAX_TEXT + 1), 'longer than', 'too long')
    refused('GRS1|BRD|x|1|os.exit(1)|1', 'characters', 'Lua in it: refused by its characters (it is never run)')
    local function signed(body) return body .. '|' .. M.check(body) end
    refused(signed('GRS1|BRD|Bad|1|1,SELF,NOT_STATUS,MARCH.2,,,s,'), 'not readable', 'a broken rule (no spell name)')
    refused(signed('GRS1|BRD|Bad|2|1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,'), 'says 2 rules but has 1', 'a wrong rule count')
    refused(signed('GRS1|XYZ|Bad|1|1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,'), 'unknown job', 'an unknown job')
    refused(signed('GRS1|BRD|Bad|1|1,SELF,NOT_STATUS,HASTE.2,,,s,VICTORY_MARCH,'), 'only song types', 'a tier on a non-song effect')
    refused(signed('GRS1|BRD|Bad|2|1,SELF,ALWAYS,,,,s,VICTORY_MARCH,,,a;1,SELF,ALWAYS,,,,s,ADVANCING_MARCH,,,a'), 'same id', 'two rules with one id')
    local many = {}
    for i = 1, 33 do many[i] = '1,SELF,ALWAYS,,,,s,VICTORY_MARCH,' end
    refused(signed('GRS1|BRD|Big|33|' .. table.concat(many, ';')), '1-32 rules', '33 rules')
    refused(signed('GRS1|BRD|Off|1|0,SELF,ALWAYS,,,,s,VICTORY_MARCH,'), 'switch on at least one rule', 'every rule off')
    S.server.version = 7
    refused(text, 'server update', 'a tier set on a version 7 server')
    S.server.version = 9
    -- names: a set of that job with the same name exists -> "Two Marches 2"; other jobs' sets do not count
    S.sets = { { num = 4, job = 'BRD', name = 'Two Marches', flags = 'o' }, { num = 5, job = 'BRD', name = 'Two Marches 2', flags = 'o' } }
    local res2 = M.parse_import(text, CAT, 'BRD')
    check(res2.draft.name == 'Two Marches 3' and table.concat(res2.warnings, ' '):find('is named "Two Marches 3"', 1, true), 'a taken name gets a number: ' .. res2.draft.name)
    S.sets = { { num = 7, job = 'WHM', name = 'Two Marches', flags = 'o' } }
    check(M.parse_import(text, CAT, 'BRD').draft.name == 'Two Marches', 'another job\'s set of the same name: not a clash')
    S.sets = {}
    local long = bardSet(); long.name = 'Bard songs for my squad'
    S.sets = { { num = 1, job = 'BRD', name = 'Bard songs for my squad', flags = 'o' } }
    local res3 = M.parse_import(assert(M.export_text(long)), CAT, 'BRD')
    check(#res3.draft.name <= M.NAME_MAX and res3.draft.name == 'Bard songs for my squa 2', 'a long name keeps within 24 characters: ' .. res3.draft.name)
    S.sets = {}
    -- another job's set: imported for that job, said so; checked for its form only (no catalog of that job)
    local war = assert(M.export_text({ job = 'WAR', name = 'War basic', rules = { row({ target = 'SELF', cond = 'NOT_STATUS', arg = 'BERSERK', kind = 'ja', name = 'BERSERK' }) } }))
    local rw = M.parse_import(war, CAT, 'BRD')
    check(rw and rw.draft.job == 'WAR' and table.concat(rw.warnings, ' '):find('form only', 1, true), 'a WAR set while a BRD is chosen: imported as WAR, checked for its form only')
    -- export refusals
    local op = bardSet(); op.rules[2] = { opaque = true, text = '?', on = true }
    check(M.export_text(op) == nil and select(2, M.export_text(op)):find('cannot be shared exactly', 1, true), 'a [kept] rule: not exported (it would be lost)')
    check(M.export_text(nil) == nil and M.export_text({ job = 'BRD', name = 'x', rules = {} }) == nil, 'nothing open / no rules: not exported')
    -- data only: the import code never loads or runs anything
    local src = assert(readAll(ADDON_DIR .. '/squad_editor.lua'))
    local io0 = src:find('(0.3.3) Rule Set import / export', 1, true)
    local io1 = src:find('function M.export_current', io0, true)
    local ioSrc = src:sub(io0, io1)
    local _, requires = ioSrc:gsub('\n%s*%-%-[^\n]*', ''):gsub('require', '')
    check(io0 and io1 and not ioSrc:find('loadstring') and not ioSrc:find('load(', 1, true) and not ioSrc:find('dofile')
          and not ioSrc:find('loadfile') and requires == 1 and ioSrc:find("pcall(require, 'share_code')", 1, true),
          'the import / export code never loads or runs text: no load, loadstring, loadfile, dofile; only require of share_code.lua')
    -- import_apply: the editor gets it; nothing is sent, saved, assigned or applied; earlier edits are kept
    S.draft = { num = 3, job = 'BRD', name = 'Mine', flags = 'o', dirty = true, rules = { row({ target = 'SELF', cond = 'ALWAYS', kind = 'spell', name = 'VICTORY_MARCH' }) } }
    sent = {}
    local before = S.draft
    check(M.import_apply(M.parse_import(text, CAT, 'BRD')) and S.draft ~= before and S.draft.num == 0 and S.restorable == before,
          'Import: the editor shows it as a new set; your unsaved edits become the unsaved draft')
    check(#sent == 0 and S.apply == nil and not M.busy(), 'nothing is sent: no save, no assign, no apply')
    -- Export / Copy: the code of the open set; Copy puts it on the clipboard; no files are written any more
    S.draft = bardSet()
    local code = M.export_current()
    check(code ~= nil and code:sub(1, 3) == 'GS1' and S.io.code == code, 'Export: the open set\'s share code (GS1...)')
    check(M.copy_code(code) and clip == code, 'Copy Share Code: the clipboard holds the code')
    check(readAll(WORK .. sep .. 'ruleset_export.txt') == nil and M.read_import_file == nil and M.write_export_file == nil,
          'no ruleset_export.txt / ruleset_import.txt: the file functions are gone')
    local noClip = gui.SetClipboardText
    gui.SetClipboardText = nil
    check(M.copy_code(code) == false and S.messageWarn, 'no clipboard: says to copy it from the box (Ctrl+C), nothing breaks')
    gui.SetClipboardText = noClip
end

-- ================================================================= G. the round trip, against the real server
section('G: Export -> Import -> Save -> Reopen -> Apply, tiers unchanged throughout')
local function serverSave(d)
    local lines = assert(M.pack(d, M.next_id()))
    local last
    for _, l in ipairs(lines) do
        local out = run(assert(l:match('^/say !gsq (.*)$')))
        last = out[#out]
    end
    return F(last or '')
end
local function serverGet(num)
    local rules, parts = {}, {}
    for _, line in ipairs(run('get 9 ' .. num)) do
        local f = F(line)
        if f[3] == 'rule' then
            local i, seg = tonumber(f[4]), tonumber(f[5]:match('^(%d+)/'))
            parts[i] = parts[i] or {}
            parts[i][seg] = f[6]
        end
    end
    for i, p in ipairs(parts) do rules[i] = table.concat(p) end
    return rules
end
do
    local original = bardSet()
    local want = encs(original.rules)
    -- 1. Export -> Import
    local res = assert(M.parse_import(assert(M.export_text(original)), CAT, 'BRD'))
    M.import_apply(res)
    check(deq(encs(S.draft.rules), want), 'after Import: the rules are exactly the exported ones')
    -- 2. Save (the editor's own packing, the server's own x stream, store and checks)
    local ok = serverSave(S.draft)
    check(ok[3] == 'ok' and tonumber(ok[4]) ~= nil, 'Save: the server accepts and writes it: ' .. table.concat(ok, '|'))
    local num = tonumber(ok[4])
    local raw = St.readRaw(P)
    local stored
    for _, s in ipairs(raw.sets) do if s.num == num then stored = s end end
    check(stored and stored.job == 'BRD' and stored.name == 'Two Marches' and stored.owner == 1 and #stored.rules == 5, 'stored as a new BRD set of yours')
    check(deq(stored.rules[1].cond, { 'NOT_STATUS', { effect = 'MARCH', tier = 2 } }) and deq(stored.rules[2].cond, { 'NOT_STATUS', { effect = 'MARCH', tier = 1 } })
          and stored.rules[3].cond[2] == 'MINUET' and deq(stored.rules[4].cond, { 'NOT_STATUS', { effect = 'MINUET', tier = 4 } })
          and deq(stored.rules[4].cond2, { 'MPP_GTE', 20 }) and stored.rules[4].on == false and stored.rules[4].level == 50
          and stored.rules[3].retry == 30 and stored.rules[1].id == 'march-hi', 'the data file holds the tiers as tables, the plain Minuet as a name, every other field')
    -- 3. Reopen: the server sends the same rule texts
    local back = serverGet(num)
    check(deq(back, want), 'Reopen (get): the server sends exactly the exported rules: ' .. table.concat(back, ' ; '))
    local reopened = {}
    for i, t in ipairs(back) do reopened[i] = assert(M.decode_rule(t)) end
    check(M.export_text({ job = 'BRD', name = 'Two Marches', rules = reopened }) == M.export_text(original), 'export after reopening = the first export, byte for byte')
    -- 4. Apply: the Rule Set as squad.lua reads it at a call, and the engine arguments
    local loaded = R.load()
    local set = loaded.byNum[num]
    check(#loaded.problems == 0 and set ~= nil, 'squad_rulesets.lua loads the written file without problems')
    local mate = { job = 10, level = 60, subJob = 3, subLevel = 30, owner = {} }
    local usable = R.usableRules(set, mate)
    local kept = {}
    for _, r in ipairs(usable) do kept[#kept + 1] = r.id end
    check(#usable >= 4, 'a BRD 60/WHM 30 keeps its song rules at the call: ' .. table.concat(kept, ' '))
    check(R.effectArg(set.rules[1].cond[2]) == xi.effect.MARCH + 2 * 65536 and R.effectArg(set.rules[2].cond[2]) == xi.effect.MARCH + 65536
          and R.effectArg(set.rules[4].cond[2]) == xi.effect.MINUET + 4 * 65536, 'the engine gets Victory March = MARCH | 2 << 16, Advancing = MARCH | 1 << 16, Minuet IV')
    -- 5. a set without tiers: the same round trip, unchanged
    local old = { job = 'BRD', name = 'Plain songs', rules = { row({ target = 'SELF', cond = 'NOT_STATUS', arg = 'MARCH', kind = 'family', name = 'MARCH' }),
        row({ target = 'MELEE', cond = 'NOT_STATUS', arg = 'MINUET', kind = 'family', name = 'VALOR_MINUET' }) } }
    local wantOld = encs(old.rules)
    M.import_apply(assert(M.parse_import(assert(M.export_text(old)), CAT, 'BRD')))
    local ok2 = serverSave(S.draft)
    local num2 = tonumber(ok2[4])
    check(ok2[3] == 'ok' and deq(serverGet(num2), wantOld), 'a set without tiers: Export -> Import -> Save -> Reopen unchanged')
    local plainSet = R.load().byNum[num2]
    check(plainSet.rules[1].cond[2] == 'MARCH' and plainSet.rules[2].cond[2] == 'MINUET', 'stored with plain effect names, as every earlier set')
    -- 6. the earlier set is still there, unchanged (an import never replaces)
    local again = R.load().byNum[num]
    check(again and deq(again.rules, stored.rules), 'the first imported set is unchanged by the second import')
    -- 7. a tier set on a map server without tiers: the save is refused with the reason, nothing written
    tierOff()
    local before = readAll(P)
    M.import_apply(assert(M.parse_import(TEXT, CAT, 'BRD')))
    local no = serverSave(S.draft)
    check(no[3] == 'err' and readAll(P) == before, 'no tier map server: the save is refused (' .. tostring(no[5]) .. '), the file unchanged')
    tierOn()
end

-- ================================================================= H. Bard role targeting: include / exclude roles
section('H: include / exclude roles (Rule Sets, codec, song recipients, editor)')
do
    -- the Rule Set checks
    local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end
    local function r(t) local x = { id = 'r1', on = true, target = 'MELEE', cond = { 'NOT_STATUS', 'MARCH' }, action = { 'spell', 'VICTORY_MARCH' } }
        for k, v in pairs(t) do x[k] = v end return x end
    check(problems(r({ exclude = { 'TANK' } })) == '', 'Melee, exclude Tank: accepted')
    check(problems(r({ target = 'TANK', include = { 'CASTER' } })) == '', 'Tank, include Mage (Caster): accepted')
    check(problems(r({ include = { 'RANGED' }, exclude = { 'TANK', 'CASTER' } })) == '', 'Melee or Ranged, not Tank or Mage: accepted')
    check(problems(r({})) == '', 'no filter: as before')
    check(problems(r({ target = 'SELF', exclude = { 'TANK' } })):find('only work with the targets', 1, true), 'a filter on Self: refused')
    check(problems(r({ exclude = { 'MELEE' } })):find('named twice', 1, true), 'excluding the target\'s own role: refused (contradictory)')
    check(problems(r({ include = { 'TANK' }, exclude = { 'TANK' } })):find('named twice', 1, true), 'the same role included and excluded: refused')
    check(problems(r({ include = { 'HEALER' } })):find('unknown role', 1, true), 'an unknown role: refused')
    check(problems(r({ include = {} })):find('list of 1-3', 1, true) and problems(r({ include = 'TANK' })):find('list of 1-3', 1, true),
          'an empty list or a plain text: refused')
    check(problems(r({ include = { 'TANK', x = 'CASTER' } })) ~= '', 'a list with other keys: refused')
    roleOff()
    check(problems(r({ exclude = { 'TANK' } })):find('updated map server', 1, true) and problems(r({})) == '',
          'without the role map server: a filter is refused (never ignored); a rule without one is fine')
    roleOn()
    local base = ai.t.MELEE
    check(R.roleMasks(r({ exclude = { 'TANK' } }), base) == base + 1 * 4096 and R.roleMasks(r({ target = 'TANK', include = { 'CASTER' } }), ai.t.TANK) == ai.t.TANK + 4 * 256
          and R.roleMasks(r({}), base) == base, 'packed for the engine: target | include << 8 | exclude << 12 (bits tank 1, melee 2, caster 4, ranged 8)')
    check(R.roleMasks(r({ include = { 'MELEE', 'CASTER', 'RANGED' }, exclude = { 'TANK' } }), 0) < 65536, 'the largest packed target fits the engine\'s uint16')
    local sl = assert(readAll(LUA_DIR .. '/squad.lua'))
    check(sl:find('R.roleFilterProblem(rule) == nil and R.roleMasks(rule, target)', 1, true)
          and sl:find('the role filter of a %s rule needs valid roles and the updated map server - rule skipped', 1, true),
          'squad.lua applyRules packs the filter, only when valid and with the role map server (else the rule is skipped)')
    -- the wire: "MELEE-TANK", "TANK.CASTER"
    local w1 = assert(G.decodeRule('1,MELEE-TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1))
    check(w1.target == 'MELEE' and deq(w1.exclude, { 'TANK' }) and w1.include == nil, '"MELEE-TANK" -> MELEE, exclude TANK')
    check(G.encodeRule(w1, 1) == '1,MELEE-TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 'and back, byte for byte')
    local w2 = assert(G.decodeRule('1,TANK.CASTER,NOT_STATUS,BALLAD,,,f,MAGES_BALLAD,', 1))
    check(w2.target == 'TANK' and deq(w2.include, { 'CASTER' }) and G.encodeRule(w2, 1) == '1,TANK.CASTER,NOT_STATUS,BALLAD,,,f,MAGES_BALLAD,', '"TANK.CASTER" both ways')
    local w3 = assert(G.decodeRule('1,MELEE.RANGED-TANK-CASTER,ALWAYS,,,,f,MARCH,', 1))
    check(deq(w3.include, { 'RANGED' }) and deq(w3.exclude, { 'TANK', 'CASTER' }) and G.encodeRule(w3, 1) == '1,MELEE.RANGED-TANK-CASTER,ALWAYS,,,,f,MARCH,', 'several roles both ways')
    check(G.decodeRule('1,MELEE-,ALWAYS,,,,f,MARCH,', 1) == nil and G.decodeRule('1,.TANK,ALWAYS,,,,f,MARCH,', 1) == nil
          and G.decodeRule('1,MELEE-tank,ALWAYS,,,,f,MARCH,', 1) == nil, 'a malformed target ("MELEE-", ".TANK", lower case) is refused')
    local plain = assert(G.decodeRule('1,PARTY_LOWEST_HPP,HPP_LT,50,,,f,CURE,', 1))
    check(plain.target == 'PARTY_LOWEST_HPP' and plain.include == nil and G.encodeRule(plain, 1) == '1,PARTY_LOWEST_HPP,HPP_LT,50,,,f,CURE,', 'targets with _ : unchanged')
    -- the store keeps them (serialised deterministically)
    local stored = St.loadText(St.serialize({ format = 'xifo-ruleset-store', version = 1, sets = { { format = 'xifo-ruleset', version = 1,
        num = 1, id = 'x', name = 'x', job = 'BRD', rules = { w1, w3 } } } }))
    check(deq(stored.sets[1].rules[1].exclude, { 'TANK' }) and deq(stored.sets[1].rules[2].include, { 'RANGED' }), 'the data file keeps include / exclude')

    -- song recipients: the confirmed loop (PLD on Auto is Tank AND Melee) and its fix
    local J = dofile(LUA_DIR .. '/squad_jobs.lua')
    local function ent(o)
        local e = { vars = {}, id = o.id, job = o.job }
        function e:getID() return self.id end
        function e:getLocalVar(k) return self.vars[k] or 0 end
        function e:setLocalVar(k, v) self.vars[k] = v end
        function e:getMainJob() return self.job end
        return e
    end
    local sp = xi.magic.spell
    local bard = ent({ id = 950, job = 10 })
    local pld, war, rng, whm = ent({ id = 951, job = 7 }), ent({ id = 952, job = 1 }), ent({ id = 953, job = 11 }), ent({ id = 954, job = 3 })
    local function songsFor(member, list)
        local n = 0
        for _, s in ipairs(list or { sp.ADVANCING_MARCH, sp.VICTORY_MARCH, sp.KNIGHTS_MINNE, sp.MAGES_BALLAD }) do
            if J.songRecipient(bard, member, s) then n = n + 1 end
        end
        return n
    end
    J.analyse(bard, { G.decodeRule('1,MELEE,NOT_STATUS,MARCH.1,,,s,ADVANCING_MARCH,', 1), G.decodeRule('1,MELEE,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 2),
                      G.decodeRule('1,TANK,NOT_STATUS,MINNE,,,s,KNIGHTS_MINNE,', 3) })
    check(J.inRole(pld, 1) and J.inRole(pld, 2) and songsFor(pld, { sp.ADVANCING_MARCH, sp.VICTORY_MARCH, sp.KNIGHTS_MINNE }) == 3,
          'the reported problem: a PLD on Auto is Tank and Melee and gets all 3 songs (2 slots: the endless recast)')
    J.analyse(bard, { G.decodeRule('1,MELEE-TANK,NOT_STATUS,MARCH.1,,,s,ADVANCING_MARCH,', 1), G.decodeRule('1,MELEE-TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 2),
                      G.decodeRule('1,TANK,NOT_STATUS,MINNE,,,s,KNIGHTS_MINNE,', 3), G.decodeRule('1,TANK.CASTER,NOT_STATUS,BALLAD,,,s,MAGES_BALLAD,', 4) })
    check(not J.songRecipient(bard, pld, sp.ADVANCING_MARCH) and not J.songRecipient(bard, pld, sp.VICTORY_MARCH)
          and J.songRecipient(bard, pld, sp.KNIGHTS_MINNE) and J.songRecipient(bard, pld, sp.MAGES_BALLAD) and songsFor(pld) == 2,
          'the expected set: the PLD gets Minne and Ballad (2 songs), no March')
    check(J.songRecipient(bard, war, sp.ADVANCING_MARCH) and J.songRecipient(bard, war, sp.VICTORY_MARCH) and not J.songRecipient(bard, war, sp.KNIGHTS_MINNE)
          and songsFor(war) == 2, 'a WAR (melee only) gets both Marches, no Minne / Ballad')
    check(J.songRecipient(bard, whm, sp.MAGES_BALLAD) and songsFor(whm) == 1, 'a WHM (mage) gets Ballad only: Tank OR Mage')
    check(songsFor(rng) == 0, 'a RNG gets none of them')
    pld:setLocalVar('SQUAD_ROLE', 2) -- (set to Melee only by !squad partyrole: no longer a tank)
    check(J.songRecipient(bard, pld, sp.ADVANCING_MARCH) and not J.songRecipient(bard, pld, sp.KNIGHTS_MINNE),
          'a PLD set to Melee (manual role): the Marches again, no Minne - manual roles are respected')
    pld:setLocalVar('SQUAD_ROLE', 0)
    war:setLocalVar('SQUAD_ROLE', 1) -- (a WAR set to Tank)
    check(not J.songRecipient(bard, war, sp.ADVANCING_MARCH) and J.songRecipient(bard, war, sp.KNIGHTS_MINNE), 'a WAR set to Tank: Minne, no March')
    war:setLocalVar('SQUAD_ROLE', 0)
    -- a member matching several included roles counts once; old single-role rules exactly as before
    J.analyse(bard, { G.decodeRule('1,MELEE.TANK,NOT_STATUS,MARCH,,,f,MARCH,', 1) })
    check(J.songRecipient(bard, pld, sp.VICTORY_MARCH) and J.songRecipient(bard, war, sp.VICTORY_MARCH) and not J.songRecipient(bard, whm, sp.VICTORY_MARCH),
          'Melee or Tank: the PLD (both) gets it once, the WAR too, not the mage')
    J.analyse(bard, { G.decodeRule('1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,', 1), G.decodeRule('1,CASTER,NOT_STATUS,BALLAD,,,f,MAGES_BALLAD,', 2) })
    check(J.songRecipient(bard, pld, sp.VALOR_MINUET) and J.songRecipient(bard, war, sp.VALOR_MINUET) and not J.songRecipient(bard, whm, sp.VALOR_MINUET)
          and J.songRecipient(bard, whm, sp.MAGES_BALLAD), 'old single-role rules (no filters): exactly as before (the PLD still counts as Melee)')
    J.analyse(bard, { G.decodeRule('1,SELF,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1) })
    check(bard:getLocalVar('SQUAD_SONG_ROLES') == 0, 'songs for Self: no role filter at all (ordinary AoE unchanged)')

    -- the editor
    local er = row({ target = 'MELEE', cond = 'NOT_STATUS', arg = 'MARCH.2', kind = 'spell', name = 'VICTORY_MARCH' })
    M.set_role(er, 'out', 'TANK', true)
    check(er.rolesOut == 'TANK' and M.encode_rule(er) == '1,MELEE-TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 'editor: exclude Tank -> "MELEE-TANK"')
    M.set_role(er, 'in', 'TANK', true)
    check(er.rolesIn == 'TANK' and er.rolesOut == nil, 'including a role takes it out of Exclude (never both)')
    M.set_role(er, 'in', 'RANGED', true); M.set_role(er, 'in', 'CASTER', true)
    check(er.rolesIn == 'TANK.CASTER.RANGED', 'the lists keep the fixed order Tank, Melee, Mage, Ranged')
    M.set_role(er, 'out', 'MELEE', true)
    check(er.rolesOut == nil, 'the target\'s own role can never be excluded')
    er.rolesIn, er.rolesOut = 'CASTER', 'TANK'
    er.target = 'CASTER'; M.fit_roles(er)
    check(er.rolesIn == nil and er.rolesOut == 'TANK', 'a new target: its own role leaves the lists')
    er.target = 'SELF'; M.fit_roles(er)
    check(er.rolesIn == nil and er.rolesOut == nil, 'a target without roles: the filters are cleared')
    local dr = M.decode_rule('1,MELEE.RANGED-TANK,NOT_STATUS,MARCH,,,f,MARCH,')
    check(dr.target == 'MELEE' and dr.rolesIn == 'RANGED' and dr.rolesOut == 'TANK' and M.encode_rule(dr) == '1,MELEE.RANGED-TANK,NOT_STATUS,MARCH,,,f,MARCH,',
          'editor decode / encode both ways')
    check(M.roles_text(dr) == 'Melee or Ranged, not Tank' and M.rule_short(dr, CAT):find('^Melee or Ranged, not Tank:') ~= nil
          and M.roles_text(M.decode_rule('1,TANK.CASTER,ALWAYS,,,,f,MAGES_BALLAD,')) == 'Tank or Mage', 'labels: "Melee or Ranged, not Tank", "Tank or Mage"')
    check(M.decode_rule('1,MELEE-,ALWAYS,,,,f,MARCH,') == nil and M.decode_rule('1,,ALWAYS,,,,f,MARCH,') ~= nil, 'editor: a malformed target is refused; an empty one as before')
    local d = { num = 0, job = 'BRD', name = 'Roles', rules = { dr } }
    check(M.check_draft(d, CAT) == nil, 'check_draft: a role filter passes with server 9: ' .. tostring(M.check_draft(d, CAT)))
    S.server.version = 8
    check((M.check_draft(d, CAT) or ''):find('server update', 1, true), 'with a version 8 server it is refused before sending')
    S.server.version = 9
    dr.rolesOut = 'MELEE'
    check((M.check_draft(d, CAT) or ''):find('either included or excluded', 1, true), 'a contradictory filter typed by hand: refused with the reason')
    local src = assert(readAll(ADDON_DIR .. '/squad_editor.lua'))
    check(src:find("combo('##gsq-role-' .. role, cur, states", 1, true) and not src:find('g.Checkbox(M.ROLE_LABEL[role]', 1, true), 'the rule editor shows one role choice (- / Include / Exclude) per role')
end

-- ================================================================= I. share codes (share_code.lua)
section('I: share codes: format, lengths, round trips, refusals, legacy GRS1')
local SC = assert(M.share(), 'share_code.lua')
local function fullSet()
    local d = bardSet()
    d.rules[1].rolesOut = 'TANK'
    d.rules[2].rolesOut = 'TANK'
    d.rules[1].target, d.rules[2].target = 'MELEE', 'MELEE'
    d.rules[#d.rules + 1] = row({ target = 'TANK', rolesIn = 'CASTER', cond = 'NOT_STATUS', arg = 'BALLAD', kind = 'family', name = 'MAGES_BALLAD' })
    d.rules[#d.rules + 1] = row({ target = 'SELF', cond = 'MOD_LT', arg = 'UTSUSEMI.2', kind = 'family', name = 'UTSUSEMI', id = 'shadows-low' })
    d.rules[#d.rules + 1] = row({ target = 'TARGET', cond = 'MB_AVAILABLE', kind = 'burst' })
    d.rules[#d.rules + 1] = row({ target = 'SELF', cond = 'JA_ON_COOLDOWN', arg = 'PROVOKE', kind = 'ja', name = 'PROVOKE', retry = '0' })
    d.name = 'Bard - songs x2'
    return d
end
do
    local src = assert(readAll(ADDON_DIR .. '/share_code.lua'))
    check(not src:find('loadstring') and not src:find('load(', 1, true) and not src:find('dofile') and not src:find('require')
          and not src:find('loadfile') and not src:find('io%.') and not src:find('os%.'), 'share_code.lua: no load, require, dofile, io or os')
    -- lengths (Basic Bard and a large set): the code against the old text
    local basic = { job = 'BRD', name = 'Basic Bard', rules = {} }
    for i, t in ipairs(M.TEMPLATES.BRD[1].rules) do basic.rules[i] = row(t) end
    local big = { job = 'BRD', name = 'Big set', rules = {} }
    for i = 1, 32 do local t = fullSet().rules[(i - 1) % 9 + 1]; local c = row(t); c.id = nil; big.rules[i] = c end
    local lens = {}
    for _, d in ipairs({ basic, fullSet(), big }) do
        local code = assert(M.export_code(d))
        local old = assert(M.export_text(d))
        lens[#lens + 1] = string.format('%s %d rules: code %d / text %d', d.name, #d.rules, #code, #old)
        check(#code < #old * 0.7, d.name .. ': the code is much shorter than the text (' .. #code .. ' vs ' .. #old .. ')')
        check(string.match(code, '^GS1[1-9A-HJ-NP-Za-km-z]+$') ~= nil, d.name .. ': only letters and digits (Base58: no 0 O I l, nothing chat formats)')
        local res = assert(M.parse_import(code, CAT, 'BRD'))
        check(deq(encs(res.draft.rules), encs(d.rules)) and res.draft.name == d.name and res.draft.job == d.job,
              d.name .. ': code -> import gives back every rule, the name and the job exactly')
    end
    io.write('    lengths: ' .. table.concat(lens, '; ') .. '\n')
    -- every field survives (tiers, roles, off, retry 0 and 30, level, ids, cond2, MOD_LT, burst without a name)
    local full = fullSet()
    local back = assert(SC.decode(assert(M.export_code(full))))
    local all = true
    for i, r in ipairs(full.rules) do all = all and M.encode_rule(back.rules[i]) == M.encode_rule(r) end
    check(all and #back.rules == #full.rules and back.rules[1].rolesOut == 'TANK' and back.rules[6].rolesIn == 'CASTER'
          and back.rules[1].arg == 'MARCH.2' and back.rules[4].on == false and back.rules[4].level == '50' and back.rules[9].retry == '0'
          and back.rules[7].id == 'shadows-low' and back.rules[8].name == nil, 'every field of every rule survives the code')
    check(SC.encode({ job = 'BRD', name = 'x', rules = full.rules }) == SC.encode({ job = 'BRD', name = 'x', rules = full.rules }), 'deterministic: the same set always gives the same code')
    check(back.name == 'Bard - songs x2', 'the name keeps its spaces and -')
    -- every job and odd text (escaped characters) round-trip
    local jobsOk = true
    for _, job in ipairs(SC.JOBS) do
        local c = SC.encode({ job = job, name = 'yz Zy', rules = { row({ target = 'SELF', cond = 'ALWAYS', kind = 'ranged', id = 'zzy' }) } })
        local b = SC.decode(c)
        jobsOk = jobsOk and b and b.job == job and b.name == 'yz Zy' and b.rules[1].id == 'zzy'
    end
    check(jobsOk, 'all 22 jobs, and letters outside the 6-bit set (y, z) round-trip')
    -- refusals
    local code = assert(M.export_code(full))
    local function refused(t, part, label)
        local r2, p2 = M.parse_import(t, CAT, 'BRD')
        local why = table.concat(p2 or {}, '; ')
        check(r2 == nil and why:find(part, 1, true) ~= nil, label .. ': ' .. why)
    end
    local flip = code:sub(1, 20) .. (code:sub(21, 21) == 'a' and 'b' or 'a') .. code:sub(22)
    refused(flip, 'check number', 'one character changed')
    refused(code:sub(1, #code - 5), 'check number', 'cut at the end')
    refused(code:sub(1, 10), 'check number', 'only the start')
    refused('GS1', 'too short', 'the prefix alone')
    refused(code:gsub('^GS1', 'GS2'), 'newer Gambits', 'an unknown format version (GS2)')
    refused(code:sub(1, 30) .. '0' .. code:sub(31), 'never has', 'a character outside Base58 (0)')
    refused('GS1' .. string.rep('z', SC.MAX_CODE), 'longer than any Rule Set code', 'oversized')
    refused('hello there', 'not a Gambits share code', 'random text')
    refused('', 'nothing to import', 'empty')
    local junk = SC.base58({ 1, 2, 3, 4, 5, 6, 7, 8, 9 })
    refused('GS1' .. junk, 'check number', 'random bytes')
    -- a payload with a valid check number but data left over / names that are not in it
    local function signed(bytes)
        local h = SC.check(bytes)
        local b = {}
        for i, v in ipairs(bytes) do b[i] = v end
        for i = 3, 0, -1 do b[#b + 1] = math.floor(h / 256 ^ i) % 256 end
        return 'GS1' .. SC.base58(b)
    end
    local okBytes = SC.unbase58(code:sub(4))
    local payload = {}
    for i = 1, #okBytes - 4 do payload[i] = okBytes[i] end
    payload[#payload + 1] = 255
    refused(signed(payload), 'left over', 'valid check number but data left over')
    refused(signed({ 0x48, 0x00 }), 'ends too early', 'valid check number but cut inside the set')
    -- spaces, line breaks and Discord code blocks around and inside
    check(M.parse_import('```\n' .. code:sub(1, 40) .. '\n' .. code:sub(41) .. '\n```', CAT, 'BRD') ~= nil
          and M.parse_import('  `' .. code .. '`  ', CAT, 'BRD') ~= nil, 'a code block, inline code and a wrapped line are fine')
    -- the older GRS1 text still imports, to the same rules
    local legacy = assert(M.export_text(full))
    local fromLegacy, fromCode = assert(M.parse_import(legacy, CAT, 'BRD')), assert(M.parse_import(code, CAT, 'BRD'))
    check(deq(encs(fromLegacy.draft.rules), encs(fromCode.draft.rules)) and fromLegacy.draft.name == fromCode.draft.name,
          'legacy GRS1 text imports to exactly the same Rule Set as the code')
    -- names, nothing assigned
    S.sets = { { num = 4, job = 'BRD', name = 'Bard - songs x2', flags = 'o' } }
    local res = assert(M.parse_import(code, CAT, 'BRD'))
    check(res.draft.name == 'Bard - songs x2 2' and res.draft.num == 0 and res.draft.rev == nil, 'a taken name gets a number; always a new set')
    S.sets = {}
    sent = {}
    M.import_apply(res)
    check(#sent == 0 and S.draft.num == 0 and S.draft.dirty and not M.busy(), 'Import as New Rule Set: nothing sent, saved, assigned or applied')
    -- the Export box: the code follows the open set (also unsaved edits), Copy puts it on the clipboard
    S.draft = fullSet()
    local c1 = M.code_for_draft(S.draft)
    S.draft.rules[3].retry = '45'
    local c2 = M.code_for_draft(S.draft)
    check(c1 ~= c2 and c2 == M.export_code(S.draft) and M.copy_code(c2) and clip == c2, 'Export box: the code follows the open set; Copy Share Code copies it')
    -- paste from the clipboard into Import (what Ctrl+V gives the field)
    clip = '```' .. c2 .. '```'
    check(M.parse_import(gui.GetClipboardText(), CAT, 'BRD') ~= nil, 'pasted from the clipboard (with a code block): imports')
    local ui = assert(readAll(ADDON_DIR .. '/squad_editor.lua'))
    check(ui:find("button('Copy Share Code##gsq-io-copy'", 1, true) and ui:find("button('Preview Import##gsq-io-preview')", 1, true)
          and ui:find("button('Import as New Rule Set##gsq-io-import')", 1, true) and not ui:find('ruleset_import.txt', 1, true)
          and not ui:find('Read file', 1, true), 'the UI: Export (code + Copy Share Code), Import (paste, Preview Import, Import as New Rule Set); no files')
end

-- ================================================================= J. the round trip with codes, tiers and roles
section('J: Export -> Copy -> Import -> Preview -> Save -> Reopen -> Assign & Apply (code; tiers + roles)')
do
    local original = fullSet()
    original.name = 'Bard roles'
    local want = encs(original.rules)
    S.draft = original
    local code = assert(M.export_current())
    assert(M.copy_code(code))
    local pasted = gui.GetClipboardText()
    local preview = assert(M.parse_import(pasted, CAT, 'BRD'))
    check(deq(encs(preview.draft.rules), want), 'Preview: exactly the exported rules')
    M.import_apply(preview)
    local ok = serverSave(S.draft)
    check(ok[3] == 'ok', 'Save: the server (version 9) accepts it: ' .. table.concat(ok, '|'))
    local num = tonumber(ok[4])
    local back = serverGet(num)
    check(deq(back, want), 'Reopen: the server sends exactly the exported rules: ' .. table.concat(back, ' ; '))
    local set = R.load().byNum[num]
    check(set and deq(set.rules[1].exclude, { 'TANK' }) and deq(set.rules[6].include, { 'CASTER' }) and deq(set.rules[1].cond[2], { effect = 'MARCH', tier = 2 }),
          'stored with the role filters and the tiers')
    local mate = { job = 10, level = 60, subJob = 3, subLevel = 30, owner = {} }
    local usable = R.usableRules(set, mate)
    check(#usable >= 6, 'Assign & Apply: a BRD 60/WHM 30 keeps its rules at the call (' .. #usable .. ')')
    check(R.roleMasks(set.rules[1], ai.t.MELEE) == ai.t.MELEE + 4096 and R.roleMasks(set.rules[6], ai.t.TANK) == ai.t.TANK + 4 * 256,
          'the engine gets Melee-not-Tank and Tank-or-Mage packed in the target')
    local reopened = {}
    for i, t in ipairs(back) do reopened[i] = assert(M.decode_rule(t)) end
    check(M.export_code({ job = 'BRD', name = 'Bard roles', rules = reopened }) == code, 'the code after reopening = the first code, byte for byte')
    roleOff()
    local before = readAll(P)
    M.import_apply(assert(M.parse_import(code, CAT, 'BRD')))
    local no = serverSave(S.draft)
    check(no[3] == 'err' and readAll(P) == before, 'no role map server: the save is refused (' .. tostring(no[5]) .. '), the file unchanged')
    roleOn()
end

-- ================================================================= K. the Basic Bard starter: never more songs than slots
section('K: Basic Bard starter: Exclude Tank / Exclude Melee, at most 2 songs for every job on Auto')
do
    local tpl = M.TEMPLATES.BRD[1]
    local byName = {}
    for _, r in ipairs(tpl.rules) do byName[r.name] = r end
    check(byName.VALOR_MINUET.target == 'MELEE' and byName.VALOR_MINUET.rolesOut == 'TANK' and byName.MARCH.rolesOut == 'TANK'
          and byName.MAGES_BALLAD.target == 'CASTER' and byName.MAGES_BALLAD.rolesOut == 'MELEE' and byName.KNIGHTS_MINNE.rolesOut == nil
          and byName.KNIGHTS_MINNE.rolesIn == nil, 'Minuet and March: Melee, exclude Tank; Ballad: Mage, exclude Melee; Minne: Tank (unchanged)')
    -- through the real codec and the real song recipients, for all 22 jobs on Auto
    local J = dofile(LUA_DIR .. '/squad_jobs.lua')
    local rules = {}
    for i, r in ipairs(tpl.rules) do rules[i] = assert(G.decodeRule(M.encode_rule(row(r)), i)) end
    local bard = { vars = {}, getID = function() return 990 end }
    function bard:getLocalVar(k) return self.vars[k] or 0 end
    function bard:setLocalVar(k, v) self.vars[k] = v end
    J.analyse(bard, rules)
    local sp = xi.magic.spell
    local songs = { sp.VALOR_MINUET, sp.ADVANCING_MARCH, sp.MAGES_BALLAD, sp.KNIGHTS_MINNE }
    local counts, worst = {}, 0
    for jobId, job in ipairs(SC.JOBS) do
        local m = { vars = {} }
        function m:getLocalVar(k) return self.vars[k] or 0 end
        function m:getMainJob() return jobId end
        local n = 0
        for _, s in ipairs(songs) do if J.songRecipient(bard, m, s) then n = n + 1 end end
        counts[job] = n
        worst = math.max(worst, n)
    end
    local list = {}
    for _, job in ipairs(SC.JOBS) do list[#list + 1] = job .. '=' .. counts[job] end
    check(worst <= 2, 'no job on Auto gets more than 2 of the starter\'s songs (the slots): ' .. table.concat(list, ' '))
    check(counts.PLD == 1 and counts.WAR == 2 and counts.WHM == 1 and counts.BLU == 2 and counts.RUN == 1 and counts.RNG == 0,
          'PLD (Tank+Melee) 1: Minne; WAR (Melee) 2: Minuet + March; WHM (Mage) 1: Ballad; BLU (Melee+Mage) 2; RUN 1')
    -- before the fix the same check finds the loop (control)
    local old = {}
    for i, r in ipairs(tpl.rules) do local c = row(r); c.rolesOut = nil; old[i] = assert(G.decodeRule(M.encode_rule(c), i)) end
    J.analyse(bard, old)
    local pldOld = { vars = {}, getLocalVar = function() return 0 end, getMainJob = function() return 7 end }
    local n = 0
    for _, s in ipairs(songs) do if J.songRecipient(bard, pldOld, s) then n = n + 1 end end
    check(n == 3, 'control: the old starter gave an Auto PLD 3 songs (the loop)')
    -- a new starter: with server 9 the filters are in the draft; nothing is saved, assigned or sent
    sent = {}
    S.server.version = 9
    local d = assert(M.new_from_template('BRD', 1, CAT))
    check(d.num == 0 and d.dirty and d.rules[1].rolesOut == 'TANK' and d.rules[3].rolesOut == 'MELEE' and #sent == 0,
          'a new Basic Bard (server 9): the filters are in the new unsaved draft; nothing sent')
    check(M.check_draft(d, CAT) == nil, 'and it passes the local checks')
    local ok = serverSave(d)
    check(ok[3] == 'ok', 'and the server saves it: ' .. table.concat(ok, '|'))
    S.server.version = 8
    local d8 = assert(M.new_from_template('BRD', 1, CAT))
    check(d8.rules[1].rolesOut == nil and d8.rules[3].rolesOut == nil and M.check_draft(d8, CAT) == nil,
          'with a version 8 server the starter comes without filters (as before) and still passes')
    S.server.version = 9
    check(tpl.rules[1].rolesOut == 'TANK', 'making a starter never changes the template itself')
    -- saved sets are not touched: the template only fills NEW drafts
    local src = assert(readAll(ADDON_DIR .. '/squad_editor.lua'))
    check(src:find("rolesOut = 'TANK', cond = 'NOT_STATUS', arg = 'MINUET'", 1, true) ~= nil and not src:find('TEMPLATES%.BRD%[1%]%.rules%s*='),
          'the correction is in the template table only (nothing rewrites saved sets)')
end
-- ================================================================= L. role filters for every job, not only Bard
section('L: Include / Exclude for every job and action with a role target (WHM Haste, RDM Refresh); never Self / Enemy')
do
    local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end
    local haste = assert(G.decodeRule('1,MELEE-TANK,NOT_STATUS,HASTE,,,s,HASTE,', 1))
    local refresh = assert(G.decodeRule('1,TANK.CASTER,NOT_STATUS,REFRESH,,,s,REFRESH,', 1))
    local protect = assert(G.decodeRule('1,RANGED.MELEE-TANK,NOT_STATUS,PROTECT,,,f,PROTECT,', 1))
    check(problems(haste) == '' and problems(refresh) == '' and problems(protect) == '',
          'WHM Haste (Melee, not Tank), RDM Refresh (Tank or Mage), Protect (Ranged or Melee, not Tank): accepted, no job check')
    check(R.roleMasks(haste, ai.t.MELEE) == ai.t.MELEE + 4096 and R.roleMasks(refresh, ai.t.TANK) == ai.t.TANK + 4 * 256,
          'packed for the engine exactly as for songs (the engine branch does not look at the caster\'s job)')
    check(problems(assert(G.decodeRule('1,SELF-TANK,NOT_STATUS,HASTE,,,s,HASTE,', 1))):find('only work with the targets', 1, true)
          and problems(assert(G.decodeRule('1,TARGET-TANK,NOT_STATUS,DIA,,,f,DIA,', 1))):find('only work with the targets', 1, true)
          and problems(assert(G.decodeRule('1,PARTY.TANK,HPP_LT,50,,,f,CURE,', 1))):find('only work with the targets', 1, true),
          'Self, Enemy (TARGET) and Party with roles: refused (the engine refuses them too)')
    -- the editor: the checkboxes depend on the target only, never on the mate's job
    local src = assert(readAll(ADDON_DIR .. '/squad_editor.lua'))
    check(src:find("if M.ROLE_TARGET[r.target or ''] and S.server and (S.server.version or 0) >= M.ROLE_SERVER then", 1, true) ~= nil,
          'the editor shows Include / Exclude for Tank / Melee / Mage / Ranged targets, whatever the job')
    for _, t in ipairs({ 'SELF', 'TARGET', 'PARTY', 'MASTER', 'PARTY_LOWEST_HPP' }) do
        local r = row({ target = t, rolesOut = 'TANK', cond = 'ALWAYS', kind = 'spell', name = 'HASTE' })
        check(M.role_problem(r) ~= nil, 'editor: no role filter with the target ' .. t)
    end
    local d = { num = 0, job = 'WHM', name = 'WHM haste', rules = { M.decode_rule('1,MELEE-TANK,NOT_STATUS,HASTE,,,s,HASTE,'),
        M.decode_rule('1,TANK.CASTER,NOT_STATUS,PROTECT,,,f,PROTECT,') } }
    check(M.check_draft(d, nil) == nil, 'a WHM set with role filters passes the editor\'s checks')
    local code = assert(M.export_code(d))
    local back = assert(M.parse_import(code, nil, nil))
    check(deq(encs(back.draft.rules), encs(d.rules)) and back.draft.job == 'WHM', 'and round-trips through a share code')
    -- non-song rules are not touched by the song recipient filter (single-target spells: the engine picks the target)
    local J = dofile(LUA_DIR .. '/squad_jobs.lua')
    local whm = { vars = {}, getID = function() return 991 end }
    function whm:getLocalVar(k) return self.vars[k] or 0 end
    function whm:setLocalVar(k, v) self.vars[k] = v end
    J.analyse(whm, { haste, refresh })
    check(whm:getLocalVar('SQUAD_SONG_ROLES') == 0, 'a WHM / RDM with role-filtered buffs: no song filter (it is only for songs, unchanged)')
    -- old rules without filters: identical wire and engine argument
    local old = assert(G.decodeRule('1,MELEE,NOT_STATUS,HASTE,,,s,HASTE,', 1))
    check(old.include == nil and old.exclude == nil and R.roleMasks(old, ai.t.MELEE) == ai.t.MELEE and G.encodeRule(old, 1) == '1,MELEE,NOT_STATUS,HASTE,,,s,HASTE,',
          'a rule without filters: the plain target, byte for byte')
end
-- ================================================================= M. role filters choose candidates only; spells are cast as always
section('M: role filters pick WHO; the spell (single target or AoE song), MP, recast and effects are unchanged')
do
    -- the generic filter lives in target selection; the Bard AoE recipient filter is separate and unchanged
    local be = assert(readAll(SERVER_ROOT .. '/src/map/entities/battle_entity.cpp'))
    check(be:find('objtype == TYPE_TRUST && PSpell->getSpellGroup() == SPELLGROUP_SONG && aoeType == SPELLAOE_RADIAL && GetLocalVar("SQUAD_SONG_ROLES") != 0', 1, true) ~= nil,
          'battle_entity.cpp: the recipient filter still applies only to a squad trust\'s radial SONGS (unchanged file)')
    local gc = assert(readAll(SERVER_ROOT .. '/src/map/ai/helpers/gambits_container.cpp'))
    local branch = gc:match('else if %(RoleBit%(targetType%) != 0 && %(gambit%.role_include != 0 || gambit%.role_exclude != 0%)%).-\n        else if %(targetType == G_TARGET::TANK%)')
    check(branch and branch:find('potentialTargets.push_back(PMember)', 1, true) and not branch:find('Cast', 1, true)
          and not branch:find('spell', 1, true) and not branch:find('PSpell', 1, true), 'the engine\'s role branch only adds candidates (no cast, no spell)')
    local sl = assert(readAll(LUA_DIR .. '/squad.lua'))
    check(sl:find('addGambit(mob, target, condition, ruleAction(rule.action), rule.retry)', 1, true) ~= nil,
          'squad.lua: the action (ruleAction) and the wait are passed exactly as before; only the target number carries the roles')
    -- non-song rules never turn the song filter on; songs keep reaching several members in one cast
    local J = dofile(LUA_DIR .. '/squad_jobs.lua')
    local function caster(id, job)
        local e = { vars = {}, id = id, job = job }
        function e:getID() return self.id end
        function e:getLocalVar(k) return self.vars[k] or 0 end
        function e:setLocalVar(k, v) self.vars[k] = v end
        function e:getMainJob() return self.job end
        return e
    end
    local rdm, whm, brd = caster(970, 5), caster(971, 3), caster(972, 10)
    J.analyse(rdm, { G.decodeRule('1,TANK.CASTER,NOT_STATUS,REFRESH,,,s,REFRESH,', 1), G.decodeRule('1,MELEE-TANK,NOT_STATUS,HASTE,,,s,HASTE,', 2) })
    J.analyse(whm, { G.decodeRule('1,MELEE-TANK,NOT_STATUS,HASTE,,,s,HASTE,', 1), G.decodeRule('1,TANK.RANGED,NOT_STATUS,PROTECT,,,f,PROTECT,', 2) })
    check(rdm:getLocalVar('SQUAD_SONG_ROLES') == 0 and whm:getLocalVar('SQUAD_SONG_ROLES') == 0 and J.songs[970] == nil and J.songs[971] == nil,
          'RDM Refresh / Haste and WHM Haste / Protect with role filters: no song filter at all - their spells stay single target, cast as always')
    J.analyse(brd, { G.decodeRule('1,MELEE-TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,', 1) })
    local war1, war2, pld = caster(980, 1), caster(981, 1), caster(982, 7)
    check(brd:getLocalVar('SQUAD_SONG_ROLES') == 1 and J.songRecipient(brd, war1, xi.magic.spell.VICTORY_MARCH)
          and J.songRecipient(brd, war2, xi.magic.spell.VICTORY_MARCH) and not J.songRecipient(brd, pld, xi.magic.spell.VICTORY_MARCH),
          'a Bard song for Melee-not-Tank: still one AoE cast that reaches every melee member around (two WARs), not the tank')
end
-- ================================================================= N. one choice per role: Include and Exclude never both
section('N: role choices are exclusive (Include <-> Exclude, clear, conflicting data, save and reopen)')
do
    local r = row({ target = 'MELEE', cond = 'NOT_STATUS', arg = 'MARCH.2', kind = 'spell', name = 'VICTORY_MARCH' })
    for _, role in ipairs(M.ROLE_ORDER) do
        check(M.role_state(r, role) == (role == 'MELEE' and 'target' or 'none'), 'a new rule: ' .. role .. ' is ' .. M.role_state(r, role))
    end
    M.set_role_state(r, 'TANK', 'in')
    check(M.role_state(r, 'TANK') == 'in' and r.rolesIn == 'TANK' and r.rolesOut == nil, 'Include Tank')
    M.set_role_state(r, 'TANK', 'out')
    check(M.role_state(r, 'TANK') == 'out' and r.rolesIn == nil and r.rolesOut == 'TANK', 'Include -> Exclude: Include is cleared')
    M.set_role_state(r, 'TANK', 'in')
    check(M.role_state(r, 'TANK') == 'in' and r.rolesIn == 'TANK' and r.rolesOut == nil, 'Exclude -> Include: Exclude is cleared')
    M.set_role_state(r, 'TANK', 'none')
    check(M.role_state(r, 'TANK') == 'none' and r.rolesIn == nil and r.rolesOut == nil and M.encode_rule(r) == '1,MELEE,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,',
          'cleared: the role is ignored, the rule is a plain Melee rule again (byte for byte)')
    M.set_role_state(r, 'MELEE', 'out')
    check(M.role_state(r, 'MELEE') == 'target' and r.rolesOut == nil, 'the target\'s own role cannot be excluded')
    M.set_role_state(r, 'CASTER', 'in'); M.set_role_state(r, 'TANK', 'out')
    check(r.rolesIn == 'CASTER' and r.rolesOut == 'TANK' and M.check_draft({ num = 0, job = 'BRD', name = 'x', rules = { r } }, CAT) == nil,
          'several roles, each with one choice: valid, nothing extra required')
    -- data with a role in both lists (hand-made text): shown as Exclude, not changed by looking, saved as Exclude
    local both = assert(M.decode_rule('1,MELEE.TANK.CASTER-TANK,NOT_STATUS,MARCH,,,f,MARCH,'))
    check(M.roles_conflict(both) and M.role_state(both, 'TANK') == 'out' and M.role_state(both, 'CASTER') == 'in', 'conflicting data: Tank shows as Exclude (the engine\'s precedence), Mage Include')
    check(both.rolesIn == 'TANK.CASTER' and both.rolesOut == 'TANK', 'looking at it (and the normalised display copy) never changes the rule')
    check(M.roles_text(M.normalized_copy(both)) == 'Melee or Mage, not Tank', 'the summary shows the effective roles')
    S.server.version = 9
    S.draft = { num = 0, job = 'BRD', name = 'Conflict fix', flags = 'o', dirty = true, rules = { both } }
    sent = {}
    M.save()
    check(both.rolesIn == 'CASTER' and both.rolesOut == 'TANK' and M.busy(), 'Save normalises it to Exclude Tank / Include Mage (what it did and showed) and queues the save')
    -- save through the real server and reopen
    local okSave = serverSave({ num = 0, job = 'BRD', name = 'Roles edited', rules = { r, both } })
    check(okSave[3] == 'ok', 'saved on the server: ' .. table.concat(okSave, '|'))
    local back = serverGet(tonumber(okSave[4]))
    check(back[1] == '1,MELEE.CASTER-TANK,NOT_STATUS,MARCH.2,,,s,VICTORY_MARCH,' and back[2] == '1,MELEE.CASTER-TANK,NOT_STATUS,MARCH,,,f,MARCH,',
          'reopened: exactly the edited choices: ' .. table.concat(back, ' ; '))
    local re = assert(M.decode_rule(back[1]))
    check(M.role_state(re, 'CASTER') == 'in' and M.role_state(re, 'TANK') == 'out' and M.role_state(re, 'RANGED') == 'none', 'and each role shows its one choice again')
    -- imported data with a conflict arrives as Exclude; codes / GRS1 of normal sets unchanged
    local SCm = assert(M.share())
    local code = SCm.encode({ job = 'BRD', name = 'Hand made', rules = { { on = true, target = 'MELEE', rolesIn = 'TANK', rolesOut = 'TANK', cond = 'ALWAYS', kind = 'family', name = 'MARCH' } } })
    local imp = assert(M.parse_import(code, CAT, 'BRD'))
    check(imp.draft.rules[1].rolesIn == nil and imp.draft.rules[1].rolesOut == 'TANK', 'an imported code with Tank in both: imported as Exclude Tank')
    -- rules without filters: untouched everywhere
    local plain = assert(M.decode_rule('1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,'))
    check(not M.normalize_roles(plain) and plain.rolesIn == nil and plain.rolesOut == nil and M.encode_rule(plain) == '1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,'
          and not M.roles_conflict(plain), 'a rule without role choices: nothing to normalise, byte for byte the same')
    local ok2 = serverSave({ num = 0, job = 'BRD', name = 'Plain again', rules = { plain } })
    check(ok2[3] == 'ok' and serverGet(tonumber(ok2[4]))[1] == '1,MELEE,NOT_STATUS,MINUET,,,f,VALOR_MINUET,', 'and it saves and reopens unchanged')
end
-- ================================================================= O. only songs the server has in the song picker
section('O: Honor March (not in the spell list, no scroll) is not offered; saved tiers and March I / II unchanged')
do
    local sl = assert(readAll(SERVER_ROOT .. '/sql/spell_list.sql'))
    check(not sl:find("'honor_march'", 1, true) and sl:find("VALUES (417,'moogle_rhapsody',", 1, true) ~= nil,
          'the server has no Honor March spell (id 417 is moogle_rhapsody; no row named honor_march)')
    local item = assert(readAll(SERVER_ROOT .. '/sql/item_basic.sql'))
    check(not item:find('honor_march', 1, true), 'and no Honor March scroll')
    check(DATA.spells.HONOR_MARCH.q == 'x' and not M.song_offered('HONOR_MARCH') and M.song_offered('VICTORY_MARCH')
          and M.song_offered('ADVANCING_MARCH'), 'the addon data marks it as never a squad mate\'s spell: not offered')
    check(deq(M.tier_choices('MARCH'), { 0, 1, 2 }), 'March picker: Any, Advancing March, Victory March (no Honor March)')
    check(deq(M.tier_choices('MARCH', 3), { 0, 1, 2, 3 }), 'a rule saved with MARCH.3 keeps showing it (nothing changed silently)')
    check(M.tier_problem('MARCH.3') == nil and M.tier_song('MARCH.3') == 'HONOR_MARCH' and M.tier_song('MARCH.2') == 'VICTORY_MARCH',
          'the tier numbering is unchanged (tier 2 = Victory March, as the server\'s songPTable)')
    local others = true
    for effect, songs in pairs(M.SONG_TIERS) do
        if effect ~= 'MARCH' then others = others and #M.tier_choices(effect) == #songs + 1 end
    end
    check(others, 'every other song type: all its songs offered (each exists on the server, with a scroll)')
end
io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
