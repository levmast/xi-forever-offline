-- Gambits WAR/PLD/RDM/WS batch (2026-11-20): stand-in tests, no game, no server, no Ashita.
--   luajit test_gambits_ws_batch.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                    <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> [<server root>]
-- What runs for real (Lua, executed): squad_ws.lua (settings, precedence, apply), gambits_squad.lua (!gsq v5: wsg, wsl,
-- wss, wsa, catm "j"), squad_rulesets.lua (new conditions/target), the addon's squad_editor.lua (parsing, Weapon Skills
-- flows through the real transport and the real server module, templates), with stand-in players and mates.
-- What does NOT run here: the C++ (gambits_container.cpp, squad.cpp). Section 8 checks a Lua TABLE that states what the
-- C++ triggers are meant to do (a specification, not the C++ itself) and, with <server root>, reads the C++ source for
-- the enum values and the code shapes it relies on. Gameplay is proven only in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK, 'usage: test_gambits_ws_batch.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir [server-root]')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function readAll(p) local f = io.open(p, 'rb'); if not f then return nil end local s = f:read('*a'); f:close(); return s end

-- ---------------------------------------------------------------- the server bits the modules need
dofile(GAMBITS)
xi = rawget(_G, 'xi') or {}
xi.magic = { spellFamily = setmetatable({ NONE = 0, CURE = 1, CURAGA = 2, PROTECT = 10, SHELL = 11, REGEN = 40, DIA = 50, PARALYZE = 51 },
                                        { __index = function() return nil end }),
             spell = setmetatable({}, { __index = function(_, k) return type(k) == 'string' and 1 or nil end }) }
xi.effect = setmetatable({}, { __index = function(_, k) return type(k) == 'string' and string.match(k, '^[A-Z_]+$') and 1 or nil end })
xi.effectFlag = { DISPELABLE = 1 }
xi.objType = { PC = 1, TRUST = 2 }
xi.msg = { channel = { SYSTEM_3 = 121 } }
xi.weaponskill = { RAGING_AXE = 17, SPINNING_AXE = 18, RAMPAGE = 19, CALAMITY = 20, FAST_BLADE = 32, BURNING_BLADE = 33,
                   RED_LOTUS_BLADE = 34, VORPAL_BLADE = 40, TACHI_ENPI = 144 }
dofile(JA_ENUM)
SquadOwnerMerit = function() return 0 end

package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end
package.preload['modules/custom/lua/squad_ws'] = function() return dofile(LUA_DIR .. '/squad_ws.lua') end
package.preload['modules/custom/lua/squad_rulesets_data'] = function() return { format = 'xifo-ruleset-store', version = 1, sets = {} } end
local R = require('modules/custom/lua/squad_rulesets')
local W = require('modules/custom/lua/squad_ws')

-- the map server of the batch: its squad.cpp registers these (here stand-ins over a table of lists)
local WSLIST, applyCalls = {}, {}
local function engineOn()
    GetSquadWeaponSkillIds = function(trust) return WSLIST[trust:getID()] or {} end
    SquadApplyWeaponSkills = function(trust, wsId)
        applyCalls[#applyCalls + 1] = { trust:getID(), wsId }
        if wsId == 0 then return true end
        for _, e in ipairs(WSLIST[trust:getID()] or {}) do if e.id == wsId then return true end end
        return false
    end
end
local function engineOff() GetSquadWeaponSkillIds, SquadApplyWeaponSkills = nil, nil end
engineOn()

local function trustOf(squadId, job, opts)
    opts = opts or {}
    local t = { vars = { SQUAD_ID = squadId }, tpSettings = {}, id = 900 + squadId, job = job, tp = opts.tp or 0 }
    function t:getObjType() return xi.objType.TRUST end
    function t:getID() return self.id end
    function t:getLocalVar(k) return self.vars[k] or 0 end
    function t:setLocalVar(k, v) self.vars[k] = v end
    function t:getMainJob() return self.job end
    function t:getMainLvl() return opts.level or 75 end
    function t:getSubJob() return 0 end
    function t:getSubLvl() return 0 end
    function t:getPacketName() return 'Mate' .. squadId end
    function t:getTP() return self.tp end
    function t:isAlive() return true end
    function t:setTrustTPSkillSettings(a, b, c) self.tpSettings[#self.tpSettings + 1] = { a, b, c } end
    return t
end
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
    function p:hasJob() return true end
    return p
end
local function last(t) return t[#t] end

-- ================================================================= 1. the stored value
section('squad_ws.lua: one char var per mate and job; three states that never mix')
local all, roundTrips, odd = 0, 0, true
for control = 0, 1 do
    for mode = 1, 4 do
        for _, tp in ipairs(W.TPS) do
            for _, ws in ipairs({ 0, 1, 17, 225, W.MAX_WS }) do
                local v = W.encode({ control = control, mode = mode, tp = tp, ws = ws })
                local d = W.decode(v)
                all = all + 1
                odd = odd and v % 2 == 1 and v > 0 and v < 2147483647
                if d and d.control == control and d.mode == mode and d.tp == tp and d.ws == ws then roundTrips = roundTrips + 1 end
            end
        end
    end
end
check(roundTrips == all and all == 160, string.format('every control x mode x TP x weapon skill survives encode -> decode (%d of %d)', roundTrips, all))
check(odd, 'every stored value is odd (bit 0 = "a Gambits setting"), positive and fits a char var')
check(W.decode(0) == nil and W.decode(2) == nil and W.decode(-5) == nil, 'no var (0), or an even/negative value: no Gambits setting (legacy)')
local damaged = W.decode(1)
check(damaged and damaged.control == 0 and damaged.damaged, 'a damaged value reads as Squad default (never as Custom)')
for _, bad in ipairs({ { control = 2, mode = 1, tp = 1000, ws = 0 }, { control = 1, mode = 0, tp = 1000, ws = 0 }, { control = 1, mode = 5, tp = 1000, ws = 0 },
                       { control = 1, mode = 1, tp = 1200, ws = 0 }, { control = 1, mode = 1, tp = 1000, ws = -1 }, { control = 1, mode = 1, tp = 1000, ws = 4096 },
                       { control = 1, mode = 1, tp = 1000, ws = 1.5 } }) do
    local v, why = W.encode(bad)
    check(v == nil and why, 'refused: control ' .. tostring(bad.control) .. ' mode ' .. tostring(bad.mode) .. ' tp ' .. tostring(bad.tp) .. ' ws ' .. tostring(bad.ws))
end
check(W.varName(7, 1) == 'SQUAD_WSC_7_1', 'the var is SQUAD_WSC_<mate id>_<job id>')

-- ================================================================= 2. precedence
section('precedence: Custom > Squad default (chosen) > the !squad ws values > the automatic roles')
local p = playerOf()
p.cv.SQUAD_WSTP_7, p.cv.SQUAD_WS_7 = 1500, 17
local s = W.resolve(p, 7, 1)
check(s.source == 'legacy' and W.effectiveWs(s) == 17 and s.legacyTp == 1500, 'no Gambits setting: !squad ws (1500 TP, Raging Axe) applies as before')
p.cv.SQUAD_WSC_7_1 = W.encode({ control = 0, mode = 3, tp = 2000, ws = 18 })
s = W.resolve(p, 7, 1)
check(s.source == 'default' and W.effectiveWs(s) == 0 and s.mode == 3 and s.tp == 2000 and s.ws == 18,
      'Reset to Squad default: the automatic roles and every weapon skill, although !squad ws is still stored; the Custom choices are kept')
p.cv.SQUAD_WSC_7_1 = W.encode({ control = 1, mode = 2, tp = 1000, ws = 18 })
s = W.resolve(p, 7, 1)
check(s.source == 'custom' and W.effectiveWs(s) == 18 and s.mode == 2, 'Custom: its own mode and weapon skill')
check(W.resolve(p, 7, 7).source == 'legacy', 'per job: the WAR setting does not touch the same mate as PLD')
check(W.spawnWs(p, { id = 7, mjob = 1 }) == 18 and W.spawnWs(p, { id = 7, mjob = 7 }) == 17, 'the call narrows to the job\'s weapon skill (custom 18 / legacy 17)')
engineOff()
s = W.resolve(p, 7, 1)
check(s.source == 'default' and s.noEngine and W.effectiveWs(s) == 0, 'Custom on a map server without the batch: acts as Squad default (never a mate that cannot weapon skill)')
engineOn()

-- ================================================================= 3. applying
section('applying: local vars and engine triggers per mode; once-only warning; live apply')
local trig = { ai.tp.OPEN_AT_TP, ai.tp.CLOSE_ONLY, ai.tp.OPEN_CLOSE_AT_TP, ai.tp.AT_TP }
check(trig[1] == 5 and trig[2] == 6 and trig[3] == 7 and trig[4] == 8, 'gambits.lua has the four triggers 5-8')
local closeTps = { 0, 1000, 1000, 2000 }
for mode = 1, 4 do
    local pm = playerOf()
    pm.cv.SQUAD_WSC_3_1 = W.encode({ control = 1, mode = mode, tp = 2000, ws = 0 })
    local t = trustOf(3, 1)
    t:setLocalVar('SQUAD_WSTP', 1500)
    W.onSpawn(pm, t, { id = 3, mjob = 1 })
    local set = last(t.tpSettings)
    check(set and set[1] == trig[mode] and set[2] == ai.s.HIGHEST and set[3] == 2000 and t:getLocalVar('SQUAD_SC_ROLE') == 1000 + mode
          and t:getLocalVar('SQUAD_WSC') == pm.cv.SQUAD_WSC_3_1 and t:getLocalVar('SQUAD_WSTP') == 0 and t:getLocalVar('SQUAD_WSC_CLOSE_TP') == closeTps[mode],
          string.format('%s: trigger %s at 2000, role %d, closes from %d', W.MODE_NAMES[mode], tostring(set and set[1]), t:getLocalVar('SQUAD_SC_ROLE'),
                        t:getLocalVar('SQUAD_WSC_CLOSE_TP')))
end
local pd = playerOf()
pd.cv.SQUAD_WSTP_3, pd.cv.SQUAD_WSC_3_1 = 1500, W.encode({ control = 0, mode = 1, tp = 1000, ws = 0 })
local td = trustOf(3, 1)
td:setLocalVar('SQUAD_WSTP', 1500) -- (squad.lua sets the !squad ws value first, as before)
W.onSpawn(pd, td, { id = 3, mjob = 1 })
check(#td.tpSettings == 0 and td:getLocalVar('SQUAD_WSC') == 0 and td:getLocalVar('SQUAD_WSTP') == 0,
      'Squad default: no trigger of its own and no !squad ws timing - the automatic roles decide')
local pl = playerOf()
pl.cv.SQUAD_WSTP_3 = 1500
local tl = trustOf(3, 1)
W.onSpawn(pl, tl, { id = 3, mjob = 1 })
check(#tl.tpSettings == 0 and tl:getLocalVar('SQUAD_WSTP') == 1500 and tl:getLocalVar('SQUAD_WSC') == 0, 'no Gambits setting: exactly the !squad ws timing, as before')

-- an unusable chosen weapon skill: the saved choice is kept, Best is used, the player is told once per call
local pw = playerOf()
pw.cv.SQUAD_WSC_4_1 = W.encode({ control = 1, mode = 4, tp = 1000, ws = 19 })
local tw = trustOf(4, 1)
WSLIST[tw.id] = { { id = 17, name = 'Raging_Axe' }, { id = 18, name = 'Spinning_Axe' } }
W.onSpawn(pw, tw, { id = 4, mjob = 1 })
check(#pw.printed == 1 and pw.printed[1]:find('cannot use the chosen weapon skill', 1, true) and pw.printed[1]:find('choice is kept', 1, true),
      'Rampage not usable (skill/quest): told once - ' .. tostring(pw.printed[1]))
W.onSpawn(pw, tw, { id = 4, mjob = 1 })
check(#pw.printed == 1, 'not repeated on the next call while it stays unusable')
check(W.decode(pw.cv.SQUAD_WSC_4_1).ws == 19, 'the saved choice is NOT replaced by Best')
WSLIST[tw.id][3] = { id = 19, name = 'Rampage' }
W.onSpawn(pw, tw, { id = 4, mjob = 1 })
check(#pw.printed == 1 and W.isUsable(tw, 19) == true, 'usable again (skill up): no message, the choice works again without rebuilding anything')
WSLIST[tw.id][3] = nil
W.onSpawn(pw, tw, { id = 4, mjob = 1 })
check(#pw.printed == 2, 'unusable again later: told again (once)')

-- live apply
applyCalls = {}
local pa = playerOf()
local ta = trustOf(5, 1)
WSLIST[ta.id] = { { id = 17, name = 'Raging_Axe' } }
W.onSpawn(pa, ta, { id = 5, mjob = 1 })
check(W.applied(pa, { id = 5 }, ta) == true, 'after a call the mate runs the stored setting (applied)')
pa.cv.SQUAD_WSC_5_1 = W.encode({ control = 1, mode = 1, tp = 1500, ws = 17 })
check(W.applied(pa, { id = 5 }, ta) == false, 'a new saved setting is not applied yet')
W.liveApply(pa, { id = 5 }, ta)
check(applyCalls[#applyCalls][2] == 17 and last(ta.tpSettings)[1] == ai.tp.OPEN_AT_TP and W.applied(pa, { id = 5 }, ta) == true,
      'Apply: the weapon skill list is rebuilt for Raging Axe and the Open trigger is set, without a new call')
pa.cv.SQUAD_WSC_5_1 = W.encode({ control = 0, mode = 1, tp = 1500, ws = 17 })
W.liveApply(pa, { id = 5 }, ta)
local back = last(ta.tpSettings)
check(applyCalls[#applyCalls][2] == 0 and back[1] == ai.tp.ASAP and back[3] == 0 and ta:getLocalVar('SQUAD_SC_ROLE') == 0
      and ta:getLocalVar('SQUAD_WSC') == 0 and W.applied(pa, { id = 5 }, ta) == true,
      'Apply after Reset: every weapon skill, the engine default, role 0 (the automatic roles take it at their next run)')
check(W.applied(pa, { id = 5 }, nil) == nil, 'a mate that is not called: "applied" is not known')
check(W.legacyNote(pa, { id = 5, mjob = 1, name = 'Mate5', jobName = 'WAR' }):find('Squad default', 1, true)
      and W.legacyNote(playerOf(), { id = 5, mjob = 1, name = 'Mate5' }) == nil, '!squad ws: an extra note only when a Gambits setting comes first')

-- ================================================================= 4. the !gsq protocol, version 5
section('!gsq v5: hello, wsg, wsl, wss, wsa (140-byte lines), catm "j"')
local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local srv = playerOf()
local squad = { { slot = 1, id = 11, name = 'Rook', mjob = 1, sjob = 0, jobs = { [1] = { level = 75 } } },
                { slot = 2, id = 12, name = 'Dame', mjob = 7, sjob = 0, jobs = { [7] = { level = 75 } } },
                { slot = 3, id = 13, name = 'Vivi', mjob = 5, sjob = 0, jobs = { [5] = { level = 75 } } } }
GetSquad = function() return squad end
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end
local function F(line) return G.splitPlain(line, '|') end
local o = run('hello 1')
check(o[1] == 'GSQ|1|hello|11|32|120|64|live', 'hello: version 11 (capability words since 10) - ' .. tostring(o[1]))
o = run('wsg 2 1')
local f = F(o[1])
check(#o == 2 and f[3] == 'ws' and f[4] == '1' and f[5] == 'WAR' and f[6] == 'l' and f[13] == '0' and f[14] == '-' and f[15] == '-' and f[16] == '1'
      and o[2] == 'GSQ|2|end|1', 'wsg, not called, nothing stored: legacy, out 0, usable/applied unknown, engine 1 - ' .. tostring(o[1]))
check(run('wsg 3 9')[1]:match('^GSQ|3|err|missing'), 'wsg for an empty slot: missing')
for _, bad in ipairs({ 'wss 4 1 2 1 1000 0', 'wss 4 1 1 9 1000 0', 'wss 4 1 1 1 1234 0', 'wss 4 1 1 1 1000 -1', 'wss 4 1 1 1 1000 x', 'wss 4 1' }) do
    check(run(bad)[1]:match('^GSQ|4|err|badreq'), 'refused: ' .. bad)
end
check(run('wss 5 1 1 1 1000 999')[1]:match('^GSQ|5|err|badreq|unknown weapon skill'), 'an unknown weapon skill id is refused')
check(srv.cv.SQUAD_WSC_11_1 == nil, 'nothing stored by a refused request')
engineOff()
check(run('wss 6 1 1 1 1000 0')[1]:match('^GSQ|6|err|engine'), 'Custom on a map server without the batch: refused (engine)')
o = run('wss 7 1 0 3 1000 0')
check(F(o[1])[6] == 'd' and F(o[1])[16] == '0', 'Squad default can still be stored there (and eng = 0 is reported)')
engineOn()
o = run('wss 8 1 1 2 1000 17')
f = F(o[1])
check(srv.cv.SQUAD_WSC_11_1 == W.encode({ control = 1, mode = 2, tp = 1000, ws = 17 }) and f[6] == 'c' and f[7] == '1' and f[8] == '2' and f[10] == '17',
      'wss stores Custom Close with Raging Axe for the mate\'s job (WAR): ' .. tostring(o[1]))
-- a called mate: wsl and the usable check
local rook = trustOf(11, 1)
rook.id = 1011
WSLIST[1011] = { { id = 17, name = 'Raging Axe' }, { id = 18, name = 'Spinning Axe' }, { id = 144, name = 'Tachi: Enpi' } }
check(run('wsl 9 1')[1]:match('^GSQ|9|err|notout'), 'wsl for a mate that is not called: notout')
srv.party = { rook }
o = run('wsl 10 1')
check(o[1] == 'GSQ|10|wsl|17:Raging_Axe,18:Spinning_Axe,144:Tachi_Enpi' and o[2] == 'GSQ|10|end|1|3', 'wsl: ids and clean names ("Tachi: Enpi" -> Tachi_Enpi): ' .. table.concat(o, ' / '))
local many = {}
for i = 1, 40 do many[i] = { id = 100 + i, name = 'A_Very_Long_Weapon_Skill_Name_' .. i } end
WSLIST[1011] = many
o = run('wsl 11 1')
local entries, longest = 0, 0
for i = 1, #o - 1 do
    longest = math.max(longest, #o[i])
    for _ in (F(o[i])[4] .. ','):gmatch('[^,]+,') do entries = entries + 1 end
end
check(#o > 3 and longest <= 140 and entries == 40 and F(o[#o])[4] == tostring(#o - 1) and F(o[#o])[5] == '40',
      string.format('40 long names: %d lines of at most 140 bytes (%d), every entry once, end counts lines and entries', #o - 1, longest))
WSLIST[1011] = { { id = 17, name = 'Raging Axe' }, { id = 18, name = 'Spinning Axe' } }
check(run('wss 12 1 1 2 1000 20')[1]:match('^GSQ|12|err|notusable'), 'a NEW choice the called mate cannot use now: refused')
srv.cv.SQUAD_WSC_11_1 = W.encode({ control = 1, mode = 2, tp = 1000, ws = 19 }) -- (saved when it could use Rampage)
o = run('wsg 13 1')
check(F(o[1])[14] == '0', 'the saved weapon skill is not usable now: usable 0 (the editor warns) - ' .. o[1])
o = run('wss 14 1 0 2 1000 19')
check(F(o[1])[6] == 'd' and W.decode(srv.cv.SQUAD_WSC_11_1).ws == 19, 'Reset keeps the unusable saved choice (it is not a new choice)')
check(run('wsa 15 2')[1]:match('^GSQ|15|err|notout'), 'wsa for a mate that is not called: notout (applies when called)')
srv.cv.SQUAD_WSC_11_1 = W.encode({ control = 1, mode = 3, tp = 2000, ws = 18 })
o = run('wsa 16 1')
f = F(o[1])
check(f[6] == 'c' and f[13] == '1' and f[14] == '1' and f[15] == '1' and last(rook.tpSettings)[1] == ai.tp.OPEN_CLOSE_AT_TP,
      'wsa: applied now (Open + Close at 2000, Spinning Axe usable): ' .. o[1])
for _, line in ipairs(run('wsg 17 1')) do check(#line <= 140, 'wsg line fits 140 bytes (' .. #line .. ')') end
srv.party = {}

-- catm: the job ability condition only for an editor that reads it
do
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local a = assert(src:find('local function jobLevel%('))
    local b = assert(src:find('\nxi%.squad%.levelsFor = levelsFor', a))
    xi.squad = xi.squad or {}
    xi.squad.levelsFor = assert((loadstring or load)('local SUB_UNLOCK_LEVEL = ' .. src:match('local SUB_UNLOCK_LEVEL = (%d+)')
        .. '\n' .. src:sub(a, b) .. '\nreturn levelsFor', '=squad.lua levelsFor'))()
end
squadScrollsOn = function() return false end
GetSquadUnlocks = function() return {} end
local OLD_C = '^[A-Z][A-Z0-9_]*:[nre][:%d]*$' -- the c entry check of the v0.1.52 addon (it rejects a whole catalog otherwise)
local function catEntries(lines, kind)
    local out = {}
    for _, l in ipairs(lines) do local ff = F(l); if ff[3] == 'cat' and ff[5] == kind then for e in (ff[6] .. ','):gmatch('([^,]+),') do out[#out + 1] = e end end end
    return out
end
local plain, oldOk, hasJ = run('catm 18 2'), true, false
for _, e in ipairs(catEntries(plain, 'c')) do oldOk = oldOk and e:match(OLD_C) ~= nil; hasJ = hasJ or e:find(':j', 1, true) ~= nil end
check(oldOk and not hasJ, 'catm without "j" (an older addon): every condition entry is one it reads; no JA_ON_COOLDOWN')
local withJ = table.concat(catEntries(run('catm 19 2 j'), 'c'), ',') .. ','
check(withJ:find('JA_ON_COOLDOWN:j,', 1, true) and withJ:find('HAS_MP:n,', 1, true) and withJ:find('HAS_MP_MPP_LT:r:0:100,', 1, true),
      'catm with "j": JA_ON_COOLDOWN:j, HAS_MP:n, HAS_MP_MPP_LT:r:0:100')
check(table.concat(catEntries(plain, 't'), ','):find('PARTY_LOWEST_HPP', 1, true), 'the target PARTY_LOWEST_HPP is offered')
engineOff()
local noEng = run('catm 20 2 j')
check(not table.concat(catEntries(noEng, 't'), ','):find('PARTY_LOWEST_HPP', 1, true) and not table.concat(catEntries(noEng, 'c'), ','):find('HAS_MP', 1, true)
      and not table.concat(catEntries(noEng, 'c'), ','):find('JA_ON_COOLDOWN', 1, true), 'without the batch\'s map server none of them is offered')
engineOn()

-- ================================================================= 5. Rule Set checks
section('Rule Sets: the new target and conditions (with and without the batch\'s map server)')
local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end
local function rule(target, cond, cond2) return { id = 'r1', on = true, target = target, cond = cond, cond2 = cond2, action = { 'family', 'CURE' } } end
check(problems(rule('PARTY_LOWEST_HPP', { 'HPP_LT', 50 })) == '', 'PARTY_LOWEST_HPP is a valid target')
check(problems(rule('PARTY', { 'HAS_MP' })) == '' and problems(rule('PARTY', { 'HAS_MP_MPP_LT', 50 })) == '' and problems(rule('PARTY', { 'HAS_MP_MPP_GTE', 0 })) == '',
      'HAS_MP (no value), HAS_MP_MPP_LT / GTE (0-100) are valid')
check(problems(rule('PARTY', { 'HAS_MP', 5 })):find('takes no value', 1, true) and problems(rule('PARTY', { 'HAS_MP_MPP_LT', 150 })):find('0-100', 1, true),
      'and are checked like the others')
check(problems(rule('TARGET', { 'JA_ON_COOLDOWN', 'PROVOKE' })) == '', 'JA_ON_COOLDOWN with a job ability name is valid')
check(problems(rule('TARGET', { 'JA_ON_COOLDOWN', 'NOT_AN_ABILITY' })):find('unknown job ability', 1, true), 'an unknown job ability is refused')
check(problems(rule('TARGET', { 'JA_ON_COOLDOWN', 35 })):find('needs a job ability name', 1, true), 'a number (an id) is refused: names only')
check(problems(rule('TARGET', { 'SUB_ANIMATION', 1 })):find('cannot be used', 1, true) and problems(rule('TARGET', { 'VAL_URIEL_CHECK' })):find('cannot be used', 1, true),
      'SUB_ANIMATION and VAL_URIEL_CHECK stay refused')
engineOff()
check(problems(rule('PARTY_LOWEST_HPP', { 'HPP_LT', 50 })):find('needs the updated map server', 1, true)
      and problems(rule('PARTY', { 'HAS_MP' })):find('needs the updated map server', 1, true)
      and problems(rule('TARGET', { 'JA_ON_COOLDOWN', 'PROVOKE' })):find('needs the updated map server', 1, true),
      'on an older xi_map all three are refused (JA_ON_COOLDOWN would test the wrong thing or crash there)')
engineOn()
local wire = G.encodeRule({ id = 'r1', on = true, target = 'TARGET', cond = { 'JA_ON_COOLDOWN', 'PROVOKE' }, cond2 = { 'NOT_STATUS', 'FLASH' },
                            action = { 'spell', 'FLASH' } }, 1)
local backRule = G.decodeRule(wire, 1)
check(wire == '1,TARGET,JA_ON_COOLDOWN,PROVOKE,NOT_STATUS,FLASH,s,FLASH,' and backRule.cond[2] == 'PROVOKE', 'the codec carries JA_ON_COOLDOWN,PROVOKE: ' .. tostring(wire))

-- ================================================================= 6. the starter templates
section('starter templates: main job only, low levels, valid, never applied by themselves')
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local sent, clock = {}, 100
M.init({ now = function() return clock end, queue_command = function(l) sent[#sent + 1] = l end })
local S = M._S
S.server = { version = 5, maxRules = 32, maxLine = 120, maxChunks = 64 }
local spells = dofile(LUA_DIR .. '/squad_spell_jobs_data.lua')
local function spellLevel(name, job)
    for _, row in pairs(spells.spells) do if row[1] == name then return row[2][job] end end
    return nil
end
-- the lowest spell of each family the templates use (a family action uses the best tier the mate has)
local FAMILY_FIRST = { CURE = 'CURE', DIA = 'DIA', PARALYZE = 'PARALYZE', PROTECT = 'PROTECT' }
local JOBS = { WAR = 1, PLD = 7, RDM = 5, WHM = 3 }
local SLOTS = { WAR = 1, PLD = 2, RDM = 3, WHM = 4 }
local SIZES = { WAR = 3, PLD = 6, RDM = 3, WHM = 4 }
-- (beta polish) the agreed rules: name -> the level its job (or, for PLD's Provoke, WAR as the sub job) learns it
local EXPECT = { WAR = { PROVOKE = 5, DEFENDER = 25, BERSERK = 15 },
                 PLD = { SHIELD_BASH = 15, SENTINEL = 30, CURE = 5, PROVOKE = 5, FLASH = 37 },
                 RDM = { CURE = 3, DIA = 1, PARALYZE = 6 },
                 WHM = { CURE = 1, POISONA = 6, PROTECT = 7 } }
local SUB_EXCEPTION = { PLD = { PROVOKE = 1 } } -- (agreed: Basic Paladin's Provoke comes from /WAR)
squad[4] = { slot = 4, id = 14, name = 'Mira', mjob = 3, sjob = 0, jobs = { [3] = { level = 75 } } }
local templatesBefore = G.encodeRule ~= nil and M.encode_rule(M.TEMPLATES.WAR[1].rules[1])
for job, jobId in pairs(JOBS) do
    local t = M.templates_for(job)
    check(#t == 1 and #t[1].rules == SIZES[job], string.format('%s: one small template (%d rules): %s', job, SIZES[job], tostring(t[1] and t[1].name)))
    local catLines = run('catm 30 ' .. SLOTS[job] .. ' j')
    local items, endF = {}, nil
    for _, l in ipairs(catLines) do local ff = F(string.sub(l, 1, 150)); if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end end
    local cat = M.parse_catalog(items, endF)
    check(cat ~= nil and cat.conds.JA_ON_COOLDOWN and cat.conds.JA_ON_COOLDOWN.kind == 'j', job .. ': the v5 catalog parses (with the j kind)')
    sent = {}
    local d = M.new_from_template(job, 1, cat)
    check(d and d.num == 0 and d.dirty and d.job == job and #sent == 0 and S.draft == d, job .. ': only a new, unsaved draft - nothing sent, saved, assigned or applied')
    check(M.check_draft(d, cat) == nil, job .. ': passes the editor\'s checks - ' .. tostring(M.check_draft(d, cat)))
    local set = { format = 'xifo-ruleset', version = 1, num = 1, id = 'tpl.' .. job, name = d.name, job = job, rules = {} }
    for i, r in ipairs(d.rules) do
        set.rules[i] = G.decodeRule(M.encode_rule(r), i)
        local why = problems(set.rules[i])
        check(why == '', string.format('%s rule %d passes the server\'s Rule Set checks: %s', job, i, why))
        if r.kind == 'ja' then
            local info = R.jaInfo(r.name)
            local fromJob = (SUB_EXCEPTION[job] or {})[r.name] or jobId
            check(info and info.job == fromJob and info.level == EXPECT[job][r.name] and info.level <= 30,
                  string.format('%s: %s is a job %d ability of level %s', job, r.name, fromJob, tostring(info and info.level)))
        else
            local lvl = spellLevel(r.kind == 'family' and FAMILY_FIRST[r.name] or r.name, jobId)
            check(lvl == EXPECT[job][r.name], string.format('%s: %s is a %s spell from level %s', job, r.name, job, tostring(lvl)))
        end
    end
    local usable, dropped = R.usableRules(set, { job = jobId, level = 75, subJob = 0, subLevel = 0, owner = srv })
    local expectDropped = job == 'PLD' and 1 or 0
    check(#usable == #set.rules - expectDropped and #dropped == expectDropped,
          string.format('%s 75 with no sub job: %d of %d rules usable%s', job, #usable, #set.rules, expectDropped > 0 and ' (Provoke needs /WAR; the rest still work)' or ''))
    if job == 'PLD' then
        local withWar = R.usableRules(set, { job = jobId, level = 75, subJob = 1, subLevel = 37, owner = srv })
        check(#withWar == #set.rules, 'PLD 75 / WAR 37: all 6 rules usable, Provoke included')
        local p36 = R.usableRules(set, { job = jobId, level = 36, subJob = 0, subLevel = 0, owner = srv })
        local hasFlash = false
        for _, u in ipairs(p36) do hasFlash = hasFlash or (u.action and u.action[2] == 'FLASH') end
        check(#p36 >= 3, 'PLD 36: Shield Bash, Sentinel and both Cures still work (' .. #p36 .. ')')
    end
    local low = R.usableRules(set, { job = jobId, level = 5, subJob = 0, subLevel = 0, owner = srv })
    check(#low >= 1, job .. ' 5: the low-level rules still work (' .. #low .. ' of ' .. #set.rules .. ')')
end
-- the agreed rule shapes
local war = M.TEMPLATES.WAR[1].rules
check(war[2].cond == 'HAS_TOP_ENMITY' and war[2].arg2 == 'DEFENDER' and war[3].cond == 'NOT_HAS_TOP_ENMITY' and war[3].arg2 == 'BERSERK'
      and war[3].arg == nil, 'Basic Warrior: Defender with the enemy\'s attention, Berserk without it (no HP threshold)')
local pld = M.TEMPLATES.PLD[1].rules
check(pld[3].target == 'PARTY_LOWEST_HPP' and pld[3].arg == '60' and pld[6].target == 'SELF' and pld[6].arg == '75'
      and pld[4].name == 'PROVOKE' and pld[5].kind == 'spell' and pld[5].name == 'FLASH', 'Basic Paladin: party Cure 60 %, Provoke, Flash, self Cure 75 %')
local whm = M.TEMPLATES.WHM[1].rules
check(whm[1].kind == 'family' and whm[1].arg == '50' and whm[2].kind == 'spell' and whm[2].name == 'CURE' and whm[2].arg == '70'
      and whm[3].cond == 'STATUS' and whm[3].arg == 'POISON' and whm[3].name == 'POISONA' and whm[4].arg == 'PROTECT',
      'Basic White Mage: best Cure < 50 %, plain Cure (a specific spell, not the family) < 70 %, Poisona on Poison, Protect')
check(M.encode_rule(whm[2]):find(',s,CURE,', 1, true) ~= nil, 'Cure I stays the specific spell CURE on the wire (s), never the family (f)')
check(M.encode_rule(M.TEMPLATES.WAR[1].rules[1]) == templatesBefore and M.TEMPLATES.PLD[1].rules[1].name == 'SHIELD_BASH',
      'loading and editing a draft never changes the templates')
S.draft.rules[1].name = 'CHANGED'
check(M.TEMPLATES.RDM[1].rules[1].name == 'CURE', 'the draft is a copy')
local d2 = M.new_from_template('RDM', 1, { targets = { 'PARTY', 'TARGET', 'SELF' } })
check(d2.rules[1].target == 'PARTY', 'a server without PARTY_LOWEST_HPP: the template falls back to PARTY')
-- (job expansion) the other jobs have starters now (test_gambits_jobexp.lua); still none for SMN or PUP
check(#M.templates_for('SMN') == 0 and #M.templates_for('PUP') == 0 and M.new_from_template('SMN', 1) == nil, 'no template for SMN or PUP')

-- ================================================================= 6b. beta polish: the Rule Set editor's usability changes
section('beta polish: compact rule lines, labels, set names, one-click open, unsaved edits kept, Assign & Apply')
check(M.rule_short(war[1]) == 'Enemy: Not top enmity + No tank -> Provoke', 'compact line: ' .. M.rule_short(war[1]))
check(M.rule_summary(war[1]):find('Does not have the enemy\'s attention', 1, true), 'the full wording is kept (tooltip, selected rule)')
check(M.rule_short(whm[1]) == 'Lowest HP: HP < 50% -> Best of Cure' and M.rule_short(whm[3]) == 'Party: Has Poison -> Poisona'
      and M.rule_short(M.TEMPLATES.RDM[1].rules[3]) == 'Enemy: No Paralysis -> Best of Paralyze (wait 30 s)', 'compact lines for WHM and RDM')
local cd = { on = true, target = 'TARGET', cond = 'JA_ON_COOLDOWN', arg = 'PROVOKE', kind = 'spell', name = 'FLASH' }
check(M.cond_text('JA_ON_COOLDOWN', 'PROVOKE') == 'Provoke is on cooldown' and M.rule_short(cd) == 'Enemy: Provoke on cooldown -> Flash',
      'the cooldown condition reads "Provoke is on cooldown"')
local subjLabel
for _, sj in ipairs(M.SUBJECTS) do if sj.key == 'COOLDOWN' then subjLabel = sj.label end end
check(subjLabel == 'Ability on Cooldown' and M.SUBJECT_OF.JA_ON_COOLDOWN, 'the condition is offered as "Ability on Cooldown" (the id and wire format unchanged)')
S.sets = { { num = 3, job = 'WAR', name = 'Basic Warrior', flags = 'o', rules = 3 } }
check(M.set_label(3) == 'Basic Warrior' and M.set_label(9) == 'Rule Set #9' and M.set_label(0) == 'default job rules',
      'the active Rule Set by its saved name ("Rule Set #9" when not in the list)')
-- one click opens; unsaved edits are kept, never thrown away
local opened = {}
local realOpen = M.open_set
M.open_set = function(num, copy) opened[#opened + 1] = num end
S.draft = { num = 3, job = 'WAR', name = 'Basic Warrior', rules = { war[1] }, dirty = false }
M.select_set(5)
check(opened[1] == 5 and S.confirmOpen == nil, 'one click on another set opens it (nothing unsaved)')
S.draft = { num = 3, job = 'WAR', name = 'Basic Warrior', rules = { war[1] }, dirty = true }
S.restorable = nil
M.select_set(6)
check(#opened == 1 and S.confirmOpen == 6, 'with unsaved edits: asks first (nothing opened yet)')
M.confirm_open(false)
check(#opened == 1 and S.draft.dirty and S.confirmOpen == nil, '"Keep editing": nothing changes')
M.select_set(6); M.confirm_open(true)
check(opened[2] == 6 and S.restorable and S.restorable.name == 'Basic Warrior', '"Open it": the unsaved edits become the unsaved draft, then it opens')
S.draft = { num = 3, job = 'WAR', name = 'Basic Warrior', rules = { war[1] }, dirty = false }
M.select_set(3)
check(#opened == 2, 'clicking the set that is already open does nothing')
M.open_set = realOpen
-- New / Starter keep unsaved edits too
S.draft, S.restorable = { num = 0, job = 'WAR', name = 'Mine', rules = { war[1] }, dirty = true }, nil
M.new_from_template('WAR', 1, nil)
check(S.restorable and S.restorable.name == 'Mine' and S.draft.name == 'Basic Warrior', 'a Starter over unsaved edits keeps them as the unsaved draft')
-- switching mates never shows the previous mate's set
local loadedFor, catFor = {}, {}
local realLoadSets, realCat = M.load_sets, M.load_catalog_for
M.load_sets = function(job, done) loadedFor[#loadedFor + 1] = job; S.sets = { { num = 7, job = job, name = 'Basic Paladin', flags = 'o', rules = 6 } }; if done then done(S.sets) end end
M.load_catalog_for = function(m) catFor[#catFor + 1] = m.slot end
M.open_set = function(num) opened[#opened + 1] = num; S.draft = { num = num, job = 'PLD', name = 'Basic Paladin', rules = {}, dirty = false } end
S.mates = { { slot = 1, name = 'Rook', job = 'WAR', chosen = 3, out = true }, { slot = 2, name = 'Dame', job = 'PLD', chosen = 7, out = true },
            { slot = 3, name = 'Vivi', job = 'RDM', chosen = 0, out = false } }
S.mateSlot = 1
S.draft = { num = 3, job = 'WAR', name = 'Basic Warrior', rules = { war[1] }, dirty = false }
M.switch_mate(2)
check(S.mateSlot == 2 and loadedFor[#loadedFor] == 'PLD' and S.draft and S.draft.name == 'Basic Paladin' and opened[#opened] == 7,
      'another mate: its own assigned Rule Set opens (Basic Paladin), not the WAR\'s')
M.switch_mate(3)
check(S.draft == nil and S.mateSlot == 3, 'a mate without a Rule Set: an empty editor, nothing of the previous mate')
M.load_sets, M.load_catalog_for, M.open_set = realLoadSets, realCat, realOpen
-- Assign & Apply / Restore default job rules
local enq, reads, applied = {}, 0, 0
local realEnq, realRead, realApply = M.enqueue, M.read_mates, M.apply
M.enqueue = function(job) enq[#enq + 1] = job.lines[1]; if job.on_done then job.on_done() end return true end
local chosenNow = 0
M.read_mates = function(ok) reads = reads + 1; ok({ { slot = 1, name = 'Rook', job = 'WAR', chosen = chosenNow, out = true } }) end
M.apply = function() applied = applied + 1 return true end
S.sets = { { num = 3, job = 'WAR', name = 'Basic Warrior', flags = 'o', rules = 3 } }
S.draft = { num = 3, job = 'WAR', name = 'Basic Warrior', rules = { war[1] }, dirty = true }
check(M.assign_apply(1, 3) == false and #enq == 0 and S.message:find('Save first', 1, true), 'Assign & Apply refuses while that set has unsaved edits (nothing sent)')
S.draft.dirty = false
chosenNow = 3
M.assign_apply(1, 3)
check(enq[1] == '/say !squad ruleset 1 3' and S.pendingApply and S.message:find('Rook now uses Basic Warrior (server confirmed). Applying', 1, true),
      'Assign & Apply: assigned and confirmed by name - ' .. tostring(S.message))
M.tick()
check(applied == 1 and not S.pendingApply, 'then Apply (the existing !squad reapply path) starts by itself')
chosenNow = 0
M.assign(1, nil, true)
M.tick()
check(enq[#enq] == '/say !squad ruleset 1 off' and applied == 2 and S.message:find('default job rules', 1, true),
      'Restore default job rules: back to the job rules and applied in one press')
M.read_mates = function(ok) ok({ { slot = 1, name = 'Rook', job = 'WAR', chosen = 3, out = false } }) end
chosenNow = 3
M.assign(1, 3, true)
M.tick()
check(applied == 2 and S.message:find('not summoned: it applies when called', 1, true), 'a mate that is not summoned: assigned, applies when called (no reapply)')
M.enqueue, M.read_mates, M.apply = realEnq, realRead, realApply
local pldShield = M.TEMPLATES.PLD[1].rules[1]
check(pldShield.target == 'TARGET' and pldShield.cond == 'CASTING_MA' and pldShield.kind == 'ja' and M.ENEMY_CONDS.CASTING_MA,
      'Basic Paladin: Enemy -> Casting a spell -> Shield Bash (the existing CASTING_MA, no new condition), first rule')

-- ================================================================= 7. the editor's Weapon Skills flows (real transport, real server)
section('editor: Weapon Skills - load, save, reset, apply through the real transport and server')
local function pump(limit)
    for _ = 1, limit or 60 do
        clock = clock + 1.1
        M.tick()
        local line = table.remove(sent, 1)
        if line then
            local body = line:match('^/say !gsq (.+)$')
            if body then
                for _, reply in ipairs(run(body)) do M.on_reply(F(string.sub(reply, 1, 150))) end
            end
        end
        if not M.busy() and #sent == 0 then return true end
    end
    return false
end
sent = {}
check(M.parse_ws(F('GSQ|1|ws|1|WAR|c|1|3|2000|18|0|0|1|1|1|1')).mode == 3 and M.parse_ws(F('GSQ|1|ws|x')) == nil, 'parse_ws reads a ws line and refuses a broken one')
local pl2 = M.parse_wsl({ F('GSQ|1|wsl|17:Raging_Axe,18:Spinning_Axe'), F('GSQ|1|wsl|144:Tachi_Enpi') })
check(pl2 and #pl2 == 3 and pl2[3].label == 'Tachi Enpi' and M.parse_wsl({ F('GSQ|1|wsl|17:Raging_Axe,17:Raging_Axe') }) == nil,
      'parse_wsl: entries in order, readable labels; a repeated entry fails the list')
srv.cv = {}
srv.party = {}
M.ws_load(1)
check(pump() and S.ws.data and S.ws.data.source == 'l' and S.ws.edit.control == 0 and S.ws.list == nil, 'load (not called): the stored state (none yet), no list')
S.ws.edit = { control = 1, mode = 1, tp = 1500, ws = 0 }
check(M.ws_dirty(), 'an edit is "not saved"')
M.ws_save(1, S.ws.edit)
check(pump() and srv.cv.SQUAD_WSC_11_1 == W.encode({ control = 1, mode = 1, tp = 1500, ws = 0 }) and S.ws.data.source == 'c' and not M.ws_dirty()
      and S.message:find('saved (server confirmed)', 1, true), 'Save: stored on the server and confirmed - ' .. tostring(S.message))
M.ws_reset(1)
check(pump() and S.ws.data.source == 'd' and W.decode(srv.cv.SQUAD_WSC_11_1).mode == 1 and W.decode(srv.cv.SQUAD_WSC_11_1).tp == 1500,
      'Reset to Squad default: control 0 stored, mode and TP kept for later')
M.ws_apply(1)
check(pump() and S.messageWarn and S.message:find('apply when the mate is called', 1, true), 'Apply on a mate that is not called: says it applies when called')
srv.party = { rook }
WSLIST[1011] = { { id = 17, name = 'Raging Axe' }, { id = 18, name = 'Spinning Axe' } }
S.ws = nil
M.ws_load(1)
check(pump() and S.ws.data.out and S.ws.list and #S.ws.list == 2 and M.ws_name(18) == 'Spinning Axe', 'load (called): the list of the mate\'s weapon skills comes too')
S.ws.edit = { control = 1, mode = 4, tp = 2000, ws = 18 }
M.ws_save(1, S.ws.edit)
pump()
check(S.ws.data.applied == false and S.message:find('Press Apply', 1, true), 'saved for a called mate: "press Apply" (not in use yet): ' .. tostring(S.message) .. ' applied=' .. tostring(S.ws.data.applied))
M.ws_apply(1)
check(pump() and S.ws.data.applied == true and last(rook.tpSettings)[1] == ai.tp.AT_TP and last(rook.tpSettings)[3] == 2000,
      'Apply: in use now (Independent at 2000 with Spinning Axe), server confirmed')
srv.party = {}

-- the panel draws with a stand-in ImGui and keeps its stacks balanced
local g, depth = {}, 0
g.Text = function() end; g.TextColored = function() end; g.TextWrapped = function() end; g.SameLine = function() end; g.NewLine = function() end
g.Separator = function() end; g.SetNextItemWidth = function() end; g.AlignTextToFramePadding = function() end; g.SetCursorPosX = function() end
g.Button = function() return false end; g.IsItemHovered = function() return false end; g.SetTooltip = function() end
g.TextUnformatted = function() end; g.PushTextWrapPos = function() end; g.PopTextWrapPos = function() end -- (hotfix 2026-11-21)
g.BeginTooltip = function() return true end; g.EndTooltip = function() end
g.BeginCombo = function() return false end; g.EndCombo = function() end; g.Selectable = function() return false end
g.PushStyleColor = function() depth = depth + 1 end; g.PopStyleColor = function(n) depth = depth - (n or 1) end
g.GetContentRegionAvail = function() return { 600, 400 } end
M.init({ now = function() return clock end, imgui = g, s = function(px) return px end, queue_command = function(l) sent[#sent + 1] = l end })
S.mates = { { slot = 1, name = 'Rook', job = 'WAR', level = 75, out = true, chosen = 0 } }
local okDraw, err = pcall(M.ws_panel, S.mates[1])
check(okDraw and depth == 0, 'the Weapon Skills panel draws (Custom, list, warnings) with balanced colours: ' .. tostring(err))
S.ws.edit.mode = 2
okDraw = pcall(M.ws_panel, S.mates[1])
check(okDraw, 'Close mode draws without a TP selector')
S.server.version = 4
okDraw = pcall(M.ws_panel, S.mates[1])
check(okDraw and not M.ws_supported(), 'an older server (version 4): the panel only says it needs the update')
S.server.version = 5

-- (beta polish, final) the whole window: the Rule Set side has Assign & Apply and Restore default job rules, no separate
-- "Apply now"; the Weapon Skills side keeps its own live apply, now labelled "Apply WS settings now"
local buttons = {}
g.Button = function(label) buttons[#buttons + 1] = label return false end
g.BeginChild = function() return true end; g.EndChild = function() end; g.PushID = function() end; g.PopID = function() end
g.Checkbox = function() return false end; g.InputText = function() return false end; g.InputInt = function() return false end
-- (0.3.4) Assign & Apply is in the bar below the rules now (for the set that is open and not yet used by the mate)
S.mates, S.mateSlot = { { slot = 1, name = 'Rook', job = 'WAR', level = 75, out = true, chosen = 0 } }, 1
S.sets, S.selectedSet, S.cat = { { num = 3, job = 'WAR', name = 'Basic Warrior', flags = 'o', rules = 3, rev = '1' } }, 3, { targets = {}, conds = {}, condNames = {}, families = {}, jas = {}, spells = {}, unconfirmed = {} }
S.draft = { num = 3, job = 'WAR', name = 'Basic Warrior', flags = 'o', rev = '1', rules = {}, dirty = false }
S.wsOpen = false -- (0.3.1: Weapon Skills is a collapsible section of the same editor, not a second tab)
local okWin, errWin = pcall(M.draw)
local seen = table.concat(buttons, '|')
check(okWin and seen:find('Assign & Apply##gsq-assign', 1, true) and seen:find('Restore default job rules##gsq-off', 1, true)
      and not seen:find('Apply now##gsq-apply', 1, true), 'Rule Sets: Assign & Apply and Restore default job rules, no separate Apply now: ' .. tostring(errWin))
buttons = {}
S.wsOpen = true
okWin, errWin = pcall(M.draw)
check(okWin and table.concat(buttons, '|'):find('Apply WS settings now##gsq-ws-apply', 1, true), 'Weapon Skills: "Apply WS settings now" (live, no new call) is kept: ' .. tostring(errWin))
S.wsOpen = false

-- ================================================================= 8. the C++ triggers: specification table + source
section('C++ weapon skill triggers: what they are meant to do (a Lua specification table, NOT the C++ itself)')
-- sc: nil = no skillchain effect, 'young' = an effect that is not a closing window (< 3 s or a finished chain), 'window'
local function spec(trigger, tp, threshold, sc, closerReady, canClose)
    local forced = tp >= 3000
    local thr = math.max(1000, math.min(3000, threshold))
    local window = sc == 'window'
    local canOpen = sc == nil and tp >= thr and closerReady
    local fire, fallback = false, false
    if trigger == 'OPEN' then fire, fallback = forced or canOpen, true
    elseif trigger == 'CLOSE' then fire, fallback = forced or window, forced
    elseif trigger == 'OPEN_CLOSE' then
        if window then fire, fallback = true, forced else fire, fallback = forced or canOpen, true end
    elseif trigger == 'AT_TP' then fire, fallback = forced or tp >= thr, true end
    if not fire then return 'wait' end
    if sc ~= nil and canClose then return 'close' end
    return fallback and 'open' or 'wait'
end
local cases = {
    -- trigger, tp, threshold, sc, closer ready, has a closing WS, expected
    { 'OPEN', 1000, 1000, nil, true, false, 'open', 'Open at its threshold with a closer ready' },
    { 'OPEN', 1000, 1000, nil, false, false, 'wait', 'Open without a ready closer waits (mandatory)' },
    { 'OPEN', 1400, 1500, nil, true, false, 'wait', 'Open below its threshold waits' },
    { 'OPEN', 2000, 1000, 'window', true, true, 'wait', 'Open never closes and never opens over a window' },
    { 'OPEN', 1500, 1000, 'young', true, true, 'wait', 'Open does not open over a chain that is going' },
    { 'OPEN', 3000, 1000, nil, false, false, 'open', '3000 TP: Open goes without a closer' },
    { 'CLOSE', 1000, 3000, 'window', false, true, 'close', 'Close closes from 1000 TP (no threshold)' },
    { 'CLOSE', 1000, 1000, 'window', false, false, 'wait', 'Close without a closing weapon skill waits' },
    { 'CLOSE', 2500, 1000, nil, true, false, 'wait', 'Close never opens below 3000' },
    { 'CLOSE', 3000, 1000, nil, false, false, 'open', '3000 TP: Close releases (no window: the opening pick)' },
    { 'CLOSE', 3000, 1000, 'window', false, false, 'open', '3000 TP: window but nothing closes - still releases' },
    { 'CLOSE', 3000, 1000, 'window', false, true, 'close', '3000 TP: window and a closer - closes' },
    { 'OPEN_CLOSE', 1000, 2000, 'window', false, true, 'close', 'Open + Close closes from 1000 although its threshold is 2000 (no 1500 clamp)' },
    { 'OPEN_CLOSE', 1200, 2000, 'window', true, false, 'wait', 'Open + Close: a window it cannot close - waits, does not open over it' },
    { 'OPEN_CLOSE', 2000, 2000, nil, true, false, 'open', 'Open + Close opens at its threshold with a closer ready' },
    { 'OPEN_CLOSE', 1500, 2000, nil, true, false, 'wait', 'Open + Close below its threshold does not open' },
    { 'OPEN_CLOSE', 2000, 2000, nil, false, false, 'wait', 'Open + Close without a ready closer does not open' },
    { 'AT_TP', 1500, 1500, nil, false, false, 'open', 'Independent at its threshold without anyone ready' },
    { 'AT_TP', 1500, 1500, 'window', false, true, 'close', 'Independent closes an open window when it can' },
    { 'AT_TP', 1500, 1500, 'window', false, false, 'open', 'Independent still uses its skill when nothing closes (not Close-only)' },
    { 'AT_TP', 1400, 1500, nil, true, false, 'wait', 'Independent below its threshold waits' },
}
for _, c in ipairs(cases) do
    local got = spec(c[1], c[2], c[3], c[4], c[5], c[6])
    check(got == c[7], string.format('%s (%s/%d TP, threshold %d): %s, expected %s', c[8], c[1], c[2], c[3], got, c[7]))
end

if SERVER_ROOT then
    local H = readAll(SERVER_ROOT .. '/src/map/ai/helpers/gambits_container.h')
    local C = readAll(SERVER_ROOT .. '/src/map/ai/helpers/gambits_container.cpp')
    local SQ = readAll(SERVER_ROOT .. '/modules/custom/cpp/squad.cpp')
    check(H and C and SQ, 'the C++ sources are readable')
    -- every enum value the Lua side uses is the C++ value (gambits.lua and gambits_container.h must not drift)
    local function enumOf(name)
        local body = H:match('enum class ' .. name .. ' : uint16%s*{(.-)};')
        local t = {}
        for k, v in (body or ''):gmatch('([A-Z_]+)%s*=%s*(%d+)') do t[k] = tonumber(v) end
        return t
    end
    for cname, lua in pairs({ G_TARGET = ai.t, G_CONDITION = ai.c, G_TP_TRIGGER = ai.tp, G_SELECT = ai.s }) do
        local cpp, same, n = enumOf(cname), true, 0
        for k, v in pairs(cpp) do n = n + 1; same = same and lua[k] == v end
        for k, v in pairs(lua) do same = same and cpp[k] == v end
        check(same and n > 0, cname .. ': gambits.lua and gambits_container.h have the same names and values (' .. n .. ')')
    end
    check(C:find('if (tp_value <= 1500) // If the value provided by the script is missing or too low', 1, true)
          and C:find('case G_TP_TRIGGER::CLOSER_UNTIL_TP:', 1, true), 'source: CLOSER_UNTIL_TP keeps its 1500 clamp (legacy behaviour unchanged)')
    check(C:find('if (tp_trigger >= G_TP_TRIGGER::OPEN_AT_TP && tp_trigger <= G_TP_TRIGGER::AT_TP)', 1, true)
          and C:find('return TrySettingsTrustSkill(target);', 1, true), 'source: only the new triggers take the new path')
    check(C:find('const bool  forced    = tp >= 3000;', 1, true) and C:find('chosen_skill = tp_skills.back();', 1, true),
          'source: the 3000-TP release and the opening-pick fallback')
    check(C:find('other.tp_trigger == G_TP_TRIGGER::OPENER || other.tp_trigger == G_TP_TRIGGER::OPEN_AT_TP', 1, true)
          and C:find('PMember->health.tp < 1000', 1, true), 'source: openers are not counted as closers; a closer needs 1000 TP')
    local _, plainTrue = C:gsub('executedAnyAction = true;', '')
    check(plainTrue == 2, 'source: only the two cosmetic ANIM_STRING actions still count as executed without a result (' .. plainTrue .. ')')
    check(C:find('HasRecast(xi::RecastType::Ability, static_cast<xi::Recast>(PAbility->getID()), 0s)', 1, true)
          and C:find('predicate.condition_arg != 0 ? ability::GetAbility', 1, true), 'source: JA_ON_COOLDOWN tests the live recast and a missing ability is false')
    check(C:find('(validTargets & TARGET_ENEMY) == 0', 1, true) and C:find('target->objtype != TYPE_MOB', 1, true),
          'source: ally-only job abilities keep the rule\'s target; enemy abilities still go to the enemy')
    check(C:find('std::stable_sort(potentialTargets.begin(), potentialTargets.end()', 1, true), 'source: PARTY_LOWEST_HPP sorts by HP%, ties in party order')
    -- (beta polish) the weapon skill range: the same test CTrustEntity::OnWeaponSkillFinished applies after the TP is spent
    local TE = readAll(SERVER_ROOT .. '/src/map/entities/trust_entity.cpp') or ''
    check(TE:find('distance(loc.p, PBattleTarget->loc.p) <= PWeaponSkill->getRange() + PBattleTarget->modelHitboxSize + modelHitboxSize', 1, true)
          and C:find('return distance(POwner->loc.p, target->loc.p) <= PWeaponSkill->getRange() + target->modelHitboxSize + POwner->modelHitboxSize;', 1, true),
          'source: InWeaponSkillRange uses exactly the range test the trust applies when the weapon skill lands')
    local _, guards = C:gsub('InWeaponSkillRange%(PWeaponSkill, ', '')
    check(guards == 2 and C:find('if (wsTarget != POwner && !InWeaponSkillRange(PWeaponSkill, wsTarget))', 1, true)
          and C:find('if (!InWeaponSkillRange(PWeaponSkill, target))', 1, true),
          'source: both weapon skill paths (the automatic triggers and the four settings) wait out of range instead of spending TP')
    check(SQ:find('::lua.set_function("SquadApplyWeaponSkills", squadApplyWeaponSkills);', 1, true)
          and SQ:find('PTrust->GetLocalVar("SQUAD_ID") == 0', 1, true), 'source: SquadApplyWeaponSkills is registered and only touches called squad mates')
else
    io.write('  (no server root given: the C++ source checks were skipped)\n')
end

-- ================================================================= 9. hotfix 2026-11-21: the Party tank condition
section('hotfix: Party tank (PT_HAS_TANK / NOT_PT_HAS_TANK) in the condition builder, server meaning unchanged')
do -- (a block: keeps the main chunk's local variables below Lua's limit)
local hcat
do
    local items, endF = {}, nil
    for _, l in ipairs(run('catm 31 1 j')) do local ff = F(string.sub(l, 1, 150)); if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end end
    hcat = M.parse_catalog(items, endF)
end
check(hcat and hcat.conds.PT_HAS_TANK and hcat.conds.PT_HAS_TANK.kind == 'n' and hcat.conds.NOT_PT_HAS_TANK
      and hcat.conds.NOT_PT_HAS_TANK.kind == 'n', 'the server catalog reports both, without a value (as before the hotfix)')
local ptSubj = M.SUBJECT_OF.PT_HAS_TANK and M.SUBJECT_OF.PT_HAS_TANK.subj
check(ptSubj and ptSubj.key == 'PTTANK' and ptSubj.label == 'Party tank' and M.SUBJECT_OF.NOT_PT_HAS_TANK
      and M.SUBJECT_OF.NOT_PT_HAS_TANK.subj == ptSubj and M.SUBJECT_OF.PT_HAS_TANK.op == 1 and M.SUBJECT_OF.NOT_PT_HAS_TANK.op == 2,
      'one subject "Party tank" with "there is one" / "there is none"')
local function offers(slot, target)
    for _, sj in ipairs(M.subjects_for(slot, target, hcat)) do if sj.key == 'PTTANK' then return true end end
    return false
end
local everywhere = true
for _, t in ipairs({ 'SELF', 'PARTY', 'PARTY_LOWEST_HPP', 'TANK', 'CASTER', 'MELEE', 'RANGED', 'TOP_ENMITY', 'TARGET', 'MASTER' }) do
    everywhere = everywhere and offers(1, t) and offers(2, t)
end
check(everywhere, 'offered in the dropdown for both condition slots with every target (the engine ignores the target for it)')
local noPt = { conds = {} }
for k, v in pairs(hcat.conds) do if k ~= 'PT_HAS_TANK' and k ~= 'NOT_PT_HAS_TANK' then noPt.conds[k] = v end end
local hidden = true
for _, sj in ipairs(M.subjects_for(1, 'TARGET', noPt)) do hidden = hidden and sj.key ~= 'PTTANK' end
check(hidden, 'not offered when a server does not report it (the builder still follows the catalog)')
-- every condition a starter template uses can be chosen in the builder (the gap the hotfix closes)
local missing = {}
for job, list in pairs(M.TEMPLATES) do
    for _, t in ipairs(list) do
        for i, r in ipairs(t.rules) do
            for _, c in ipairs({ r.cond, r.cond2 }) do
                if c and not M.SUBJECT_OF[c] then missing[#missing + 1] = string.format('%s rule %d: %s', job, i, c) end
            end
        end
    end
end
check(#missing == 0, 'every condition of every starter template is in the builder: ' .. table.concat(missing, ', '))
-- choosing, switching, wording
local pr = { on = true, target = 'TARGET', cond = 'NOT_HAS_TOP_ENMITY', kind = 'ja', name = 'PROVOKE' }
M.set_condition(pr, 2, 'PT_HAS_TANK', hcat)
check(pr.cond2 == 'PT_HAS_TANK' and pr.arg2 == nil and M.check_draft({ name = 'Tank test', rules = { pr } }, hcat) == nil,
      'chosen as the second condition: no value, passes the editor checks')
M.set_condition(pr, 2, 'NOT_PT_HAS_TANK', hcat)
check(pr.cond2 == 'NOT_PT_HAS_TANK' and pr.arg2 == nil and pr.cond == 'NOT_HAS_TOP_ENMITY', 'switched to "there is none": the other condition is untouched')
check(M.cond_text('NOT_PT_HAS_TANK') == 'Party has no tank' and M.cond_text('PT_HAS_TANK') == 'Party has a tank'
      and M.rule_short(war[1]) == 'Enemy: Not top enmity + No tank -> Provoke', 'the existing wording is unchanged')
check(M.protected(war[1], hcat) == nil, 'the Basic Warrior Provoke rule is editable (not "kept")')
-- saved, loaded and reapplied exactly as before: the wire form and the server's Rule Set checks
local warWire = M.encode_rule(war[1])
check(warWire == '1,TARGET,NOT_HAS_TOP_ENMITY,,NOT_PT_HAS_TANK,,j,PROVOKE,', 'the wire form of the Basic Warrior rule is unchanged: ' .. warWire)
local warBack = G.decodeRule(warWire, 1)
check(warBack and warBack.cond2 and warBack.cond2[1] == 'NOT_PT_HAS_TANK' and problems(warBack) == '', 'the server reads it back and accepts it')
check(problems(rule('SELF', { 'PT_HAS_TANK' })) == '' and problems(rule('PARTY', { 'NOT_PT_HAS_TANK' })) == ''
      and problems(rule('SELF', { 'PT_HAS_TANK', 1 })):find('takes no value', 1, true), 'PT_HAS_TANK / NOT_PT_HAS_TANK stay valid conditions without a value')
check(ai.c.PT_HAS_TANK == 25 and ai.c.NOT_PT_HAS_TANK == 26, 'the engine ids are unchanged (25, 26)')
if SERVER_ROOT then
    local C2 = readAll(SERVER_ROOT .. '/src/map/ai/helpers/gambits_container.cpp') or ''
    check(C2:find('case G_CONDITION::NOT_PT_HAS_TANK:', 1, true) and C2:find('predicateResults.push_back(!PartyHasTank());', 1, true)
          and C2:find('jobType == xi::Job::NIN || jobType == xi::Job::PLD || jobType == xi::Job::RUN', 1, true),
          'source: the engine meaning is the official one (a NIN, PLD or RUN main job in the party), as the label says')
end
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
