-- Gambits community feedback milestone (2026-11-25): F1 enemy family, F2 counts. Stand-in tests, no game, no server, no Ashita.
--   luajit test_gambits_feedback.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                    <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> <server root>
-- What runs for real: the editor (squad_editor.lua: catalog kinds y/p/q, values, checks, texts, its codec), the server's !gsq
-- (gambits_squad.lua v11: catm "jmf", G.decodeCount / encodeCount), squad_rulesets.lua (checks, engine arguments) and
-- squad.lua's ruleCondition (the packed argument the engine gets), with the server's real enums. The saved rule goes editor ->
-- wire -> server check -> engine argument and back to the editor. What does NOT run here: the C++ (gambits_container.cpp
-- ENEMY_FAMILY / PARTY_COUNT / ENEMY_COUNT; the count rule is tested in squad_threat_tests.cpp). Gameplay is proven only in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER_ROOT,
       'usage: test_gambits_feedback.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server-root')
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
-- xi.mobFamily is generated from data/ecosystems.yaml at build time; the families of the yaml are read here the same way
do
    local yaml = assert(readAll(SERVER_ROOT .. '/data/ecosystems.yaml'), 'data/ecosystems.yaml')
    xi.mobFamily = {}
    local pending = nil
    for line in (yaml .. '\n'):gmatch('([^\n]*)\n') do
        local fam = line:match('^      ([a-z0-9_]+):%s*$')
        local id = line:match('^        id:%s*(%d+)')
        if fam then pending = fam
        elseif id and pending then xi.mobFamily[pending:upper()] = tonumber(id); pending = nil
        else pending = nil end
    end
end
xi.effectFlag = xi.effectFlag or { DISPELABLE = 1 }
xi.objType = { PC = 1, TRUST = 2 }
xi.msg = { channel = { SYSTEM_3 = 121 } }
xi.settings = { main = { RESTRICT_CONTENT = 1, ENABLE_COP = 1, ENABLE_ROTZ = 1, ENABLE_TOAU = 1, ENABLE_WOTG = 0 } }
SquadOwnerMerit = function() return 0 end
SquadJobExpansionEngine = function() return 1 end
SquadRoleFilterEngine = function() return 1 end
SquadApplyWeaponSkills = function() return true end
SquadStatusTierEngine = function() return 1 end
local function engine3On() SquadFeedbackEngine = function() return 1 end end
local function engine3Off() SquadFeedbackEngine = nil end
engine3On()
GetAbility = function(id) return { id = id } end
GetSpell = function() return { getSpellFamily = function() return 0 end } end

package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end
package.preload['modules/custom/lua/squad_ws'] = function() return dofile(LUA_DIR .. '/squad_ws.lua') end
package.preload['modules/custom/lua/squad_rulesets_data'] = function() return { format = 'xifo-ruleset-store', version = 1, sets = {} } end
local R = require('modules/custom/lua/squad_rulesets')

do -- xi.squad.levelsFor from squad.lua itself (the catalog asks it for a mate's levels)
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local a = assert(src:find('local function jobLevel%('))
    local b = assert(src:find('\nxi%.squad%.levelsFor = levelsFor', a))
    xi.squad = xi.squad or {}
    xi.squad.levelsFor = assert(loadChunk('local SUB_UNLOCK_LEVEL = ' .. src:match('local SUB_UNLOCK_LEVEL = (%d+)')
        .. '\n' .. src:sub(a, b) .. '\nreturn levelsFor', '=squad.lua levelsFor'))()
end
-- squad.lua's ruleCondition: the function that turns a Rule Set condition into the engine's (id, argument)
local ruleCondition
do
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local a = assert(src:find('local function ruleArg%('))
    local b = assert(src:find('\nlocal function ruleAction%(', a))
    local function cond(id, arg) return { id, arg } end
    local env = setmetatable({ cond = cond }, { __index = _G })
    local chunk = assert(loadChunk(src:sub(a, b) .. '\nreturn ruleCondition', '=squad.lua ruleCondition'))
    if setfenv then setfenv(chunk, env) else chunk = assert(load(src:sub(a, b) .. '\nreturn ruleCondition', '=squad.lua ruleCondition', 't', env)) end
    ruleCondition = chunk()
end
squadScrollsOn = function() return false end
GetSquadUnlocks = function() return {} end

local srv = { cv = {}, lv = {}, printed = {}, party = {} }
function srv:getID() return 1 end
function srv:getCharVar(k) return self.cv[k] or 0 end
function srv:setCharVar(k, v) self.cv[k] = v end
function srv:getLocalVar(k) return self.lv[k] or 0 end
function srv:setLocalVar(k, v) self.lv[k] = v end
function srv:printToPlayer(text) self.printed[#self.printed + 1] = text end
function srv:getPartyWithTrusts() return self.party end
function srv:getMainLvl() return 75 end
function srv:getMainJob() return 1 end
function srv:hasJob() return true end
function srv:getObjType() return xi.objType.PC end
GetSquad = function() return { { slot = 1, id = 101, name = 'Heala', mjob = 3, sjob = 0, jobs = { [3] = { level = 75 } } } } end

local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end
local function F(line) return G.splitPlain(line, '|') end
local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end
local function rule(cond, target, action) return { id = 'r1', on = true, target = target or 'PARTY', cond = cond, action = action or { 'family', 'CURE' } } end

-- ================================================================= server: checks and engine arguments
section('server: ENEMY_FAMILY, PARTY_COUNT, ENEMY_COUNT (squad_rulesets.lua, gambits.lua, squad.lua)')
do
    check(ai.c.ENEMY_FAMILY == 44 and ai.c.PARTY_COUNT == 45 and ai.c.ENEMY_COUNT == 46, 'gambits.lua: 44, 45, 46 (as gambits_container.h)')
    check(xi.mobFamily.GOBLIN == 58 and xi.mobFamily.ORC == 63, 'the families of data/ecosystems.yaml: Goblin 58, Orc 63')

    check(problems(rule({ 'ENEMY_FAMILY', { family = 'GOBLIN' } }, 'SELF', { 'spell', 'BARFIRA' })) == '', 'Goblin -> Barfira (target Self) is valid')
    check(problems(rule({ 'ENEMY_FAMILY', { family = 'GOBLINZ' } })):find('unknown monster family', 1, true), 'an unknown family is refused')
    check(problems(rule({ 'ENEMY_FAMILY', 58 })):find('needs { family', 1, true), 'a bare number is refused')
    check(problems(rule({ 'IS_ECOSYSTEM', { ecosystem = 'BEASTMEN' } }, 'TARGET', { 'spell', 'DIA' })) == '', 'the ecosystem condition is unchanged')
    check(R.familyArg({ family = 'GOBLIN' }) == 58, 'engine argument: the family id')

    check(problems(rule({ 'PARTY_COUNT', { status = 'ASLEEP', cmp = 'AT_LEAST', count = 2 } }, 'PARTY', { 'family', 'CURAGA' })) == '',
        '2 or more asleep -> Curaga is valid')
    check(problems(rule({ 'PARTY_COUNT', { status = 'PETRIFICATION', cmp = 'EXACTLY', count = 1 } })) == '', 'a status effect name is valid')
    check(problems(rule({ 'PARTY_COUNT', { cmp = 'AT_MOST', count = 0 } })) == '', 'every member, count 0 is valid')
    check(problems(rule({ 'PARTY_COUNT', { cmp = 'AT_LEAST', count = 19 } })) ~= '', 'count 19 is refused (0-18)')
    check(problems(rule({ 'PARTY_COUNT', { cmp = 'SOME', count = 1 } })):find('cmp must be', 1, true), 'an unknown comparison is refused')
    check(problems(rule({ 'PARTY_COUNT', { status = 'NOPE', count = 1 } })):find('unknown status effect', 1, true), 'an unknown status is refused')
    check(problems(rule({ 'PARTY_COUNT', { count = 1, radius = 5 } })):find('unknown field radius', 1, true), 'a field of the other count is refused')
    check(R.partyCountArg({ status = 'ASLEEP', cmp = 'AT_LEAST', count = 2 }) == 0xFFFE + 2 * 65536, 'asleep, at least 2: 0xFFFE | 2 << 16 | 0 << 24')
    check(R.partyCountArg({ status = 'PETRIFICATION', cmp = 'FEWER_THAN', count = 3 }) == xi.effect.PETRIFICATION + 3 * 65536 + 4 * 16777216,
        'petrified, fewer than 3: effect | 3 << 16 | 4 << 24')

    check(problems(rule({ 'ENEMY_COUNT', { hp_above = 30, cmp = 'AT_LEAST', count = 3 } }, 'TARGET', { 'family', 'STONEGA' })) == '',
        '3 or more above 30% -> Stonega is valid')
    check(problems(rule({ 'ENEMY_COUNT', { hp_above = 100, count = 3 } })) ~= '', 'hp_above 100 is refused (0-99)')
    check(problems(rule({ 'ENEMY_COUNT', { radius = 31, count = 3 } })) ~= '', 'radius 31 is refused (1-30)')
    check(R.enemyCountArg({ hp_above = 30, cmp = 'AT_LEAST', count = 3 }) == 30 + 10 * 256 + 3 * 65536, 'the default radius is 10')
    check(R.enemyCountArg({ hp_above = 0, radius = 15, cmp = 'MORE_THAN', count = 1 }) == 15 * 256 + 65536 + 3 * 16777216, 'radius, comparison')

    check(table.concat(ruleCondition({ 'ENEMY_FAMILY', { family = 'GOBLIN' } }), ',') == '44,58', 'squad.lua gives the engine 44 / 58')
    check(table.concat(ruleCondition({ 'PARTY_COUNT', { status = 'ASLEEP', cmp = 'AT_LEAST', count = 2 } }), ',') == '45,' .. (0xFFFE + 2 * 65536),
        'squad.lua gives the engine the packed PARTY_COUNT')

    engine3Off()
    check(problems(rule({ 'ENEMY_FAMILY', { family = 'GOBLIN' } })):find('needs the updated map server', 1, true),
        'an older xi_map: the new conditions are refused, never sent to an engine that does not know them')
    check(ruleCondition({ 'ENEMY_FAMILY', { family = 'GOBLIN' } }) == nil, 'and squad.lua skips such a rule')
    engine3On()
end

-- ================================================================= wire
section('!gsq v11: the catalog and the codec')
do
    check(F(run('hello 1')[1])[4] == '12', 'hello: version 12')
    local function cEntries(lines)
        local out = {}
        for _, l in ipairs(lines) do local ff = F(l); if ff[3] == 'cat' and ff[5] == 'c' then for e in (ff[6] .. ','):gmatch('([^,]+),') do out[e] = true end end end
        return out
    end
    local jmf, jm = cEntries(run('catm 2 1 jmf')), cEntries(run('catm 3 1 jm'))
    check(jmf['ENEMY_FAMILY:y'] and jmf['PARTY_COUNT:p'] and jmf['ENEMY_COUNT:q'], 'catm "jmf" describes the three (y, p, q)')
    check(not jm['ENEMY_FAMILY:y'] and not jm['PARTY_COUNT:p'], 'catm "jm" (an older editor) does not: its check would refuse the whole list')
    engine3Off()
    check(not cEntries(run('catm 4 1 jmf'))['ENEMY_FAMILY:y'], 'an older xi_map: not offered')
    engine3On()

    for _, case in ipairs({
        { cond = { 'ENEMY_FAMILY', { family = 'GOBLIN' } }, text = 'GOBLIN' },
        { cond = { 'PARTY_COUNT', { cmp = 'AT_LEAST', count = 2, status = 'ASLEEP' } }, text = 'AT_LEAST.2.ASLEEP' },
        { cond = { 'PARTY_COUNT', { cmp = 'EXACTLY', count = 0 } }, text = 'EXACTLY.0' },
        { cond = { 'ENEMY_COUNT', { cmp = 'AT_LEAST', count = 3, hp_above = 30, radius = 10 } }, text = 'AT_LEAST.3.30.10' },
        { cond = { 'ENEMY_COUNT', { cmp = 'AT_LEAST', count = 3, hp_above = 30 } }, text = 'AT_LEAST.3.30' },
    }) do
        local wire = G.encodeRule({ id = 'r1', on = true, target = 'PARTY', cond = case.cond, action = { 'family', 'CURAGA' } }, 1)
        local back = wire and G.decodeRule(wire, 1)
        local same = back ~= nil and back.cond[1] == case.cond[1]
        for k, v in pairs(case.cond[2]) do same = same and back.cond[2][k] == v end
        for k in pairs(back and back.cond[2] or {}) do same = same and case.cond[2][k] ~= nil end
        check(wire ~= nil and wire:find(',' .. case.text .. ',', 1, true) ~= nil and same, case.cond[1] .. ' round trip as "' .. case.text .. '": ' .. tostring(wire))
    end
    check(G.encodeRule({ id = 'r1', on = true, target = 'PARTY', cond = { 'PARTY_COUNT', { cmp = 'AT_LEAST', count = 2, extra = 1 } },
        action = { 'family', 'CURAGA' } }, 1) == nil, 'a value with any other key is not carried (no silent loss)')
    local bad = G.decodeRule('1,PARTY,PARTY_COUNT,TWO,,,f,CURAGA,', 1)
    check(bad ~= nil and problems(bad) ~= '', 'an unreadable value reaches the check and is refused there: ' .. (bad and problems(bad) or '?'))
end

-- ================================================================= editor
section('editor: the three conditions, end to end')
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local sent, clock = {}, 100
M.init({ now = function() return clock end, queue_command = function(l) sent[#sent + 1] = l end })
local S = M._S
S.server = { version = 11, maxRules = 32, maxLine = 120, maxChunks = 64 }
local function catalogFor(flags)
    local lines = run('catm 30 1' .. (flags and (' ' .. flags) or ''))
    local items, endF = {}, nil
    for _, l in ipairs(lines) do local ff = F(string.sub(l, 1, 150)); if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end end
    return M.parse_catalog(items, endF)
end
do
    check(M.COUNT_SERVER == 11, 'the editor asks catm "jmf" from server version 11')
    local cat = catalogFor('jmf')
    check(cat ~= nil and cat.conds.ENEMY_FAMILY.kind == 'y' and cat.conds.PARTY_COUNT.kind == 'p' and cat.conds.ENEMY_COUNT.kind == 'q',
        'the v11 catalog parses with the kinds y, p, q')
    local keys = {}
    for _, s in ipairs(M.subjects_for(1, 'SELF', cat, false)) do keys[s.key] = true end
    check(keys.FAMILY and keys.PCOUNT and keys.ECOUNT, 'Enemy family, Party members and Enemies are offered (any target)')
    local old = catalogFor('jm')
    keys = {}
    for _, s in ipairs(M.subjects_for(1, 'SELF', old, true)) do keys[s.key] = true end
    check(not keys.FAMILY and not keys.PCOUNT, 'a catalog without them: not offered')

    -- Goblin -> Barfira, built the way the window builds it
    local r = { on = true, target = 'SELF', cond = 'HPP_LT', arg = '50', kind = 'spell', name = 'BARFIRA' }
    M.set_condition(r, 1, 'ENEMY_FAMILY', cat)
    check(r.arg == 'GOBLIN', 'choosing Enemy family starts at Goblin')
    check(M.cond_text('ENEMY_FAMILY', 'GOBLIN', cat) == 'Enemy is Goblin' and M.cond_short('ENEMY_FAMILY', 'MAMOOL_JA', cat) == 'Mamool Ja',
        'readable: ' .. M.cond_text('ENEMY_FAMILY', 'GOBLIN', cat))

    -- Cure vs Curaga
    local cg = { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURAGA' }
    M.set_condition(cg, 2, 'PARTY_COUNT', cat)
    check(cg.arg2 == 'AT_LEAST.2.ASLEEP', 'Party members starts at "at least 2 asleep"')
    check(M.cond_text('PARTY_COUNT', 'AT_LEAST.2.ASLEEP', cat) == 'Party members asleep: at least 2', M.cond_text('PARTY_COUNT', 'AT_LEAST.2.ASLEEP', cat))
    check(M.cond_short('PARTY_COUNT', 'FEWER_THAN.2.ASLEEP', cat) == 'Asleep < 2', M.cond_short('PARTY_COUNT', 'FEWER_THAN.2.ASLEEP', cat))

    -- Stone vs Stonega
    local sg = { on = true, target = 'TARGET', cond = 'ALWAYS', kind = 'family', name = 'STONEGA' }
    M.set_condition(sg, 1, 'ENEMY_COUNT', cat)
    check(sg.arg == 'AT_LEAST.3.0.10', 'Enemies starts at "at least 3 within 10 yalms"')
    sg.arg = 'AT_LEAST.3.30.10'
    check(M.cond_text('ENEMY_COUNT', sg.arg, cat) == 'Enemies above 30% HP within 10 yalms: at least 3', M.cond_text('ENEMY_COUNT', sg.arg, cat))

    local d = { name = 'Feedback', job = 'WHM', rules = { r, cg, sg } }
    check(M.check_draft(d, cat) == nil, 'the draft passes the editor\'s checks: ' .. tostring(M.check_draft(d, cat)))
    sg.arg = 'AT_LEAST.3.30.40'
    check((M.check_draft(d, cat) or ''):find('1-30', 1, true), 'a reach out of range is caught before the save')
    sg.arg = 'AT_LEAST.31.30.10'
    check((M.check_draft(d, cat) or ''):find('0-30', 1, true), 'a count out of range is caught before the save')
    sg.arg = 'AT_LEAST.3.30.10'
    cg.arg2 = 'SOME.2'
    check(M.check_draft(d, cat) ~= nil, 'an unknown comparison is caught')
    cg.arg2 = 'AT_LEAST.2.ASLEEP'

    -- the whole round trip: editor -> wire -> server check -> engine argument -> editor
    for i, row in ipairs(d.rules) do
        local wire = M.encode_rule(row)
        local srvRule = G.decodeRule(wire, i)
        check(srvRule ~= nil and problems(srvRule) == '', 'rule ' .. i .. ' passes the server check: ' .. (srvRule and problems(srvRule) or tostring(wire)))
        local engineCond = srvRule and ruleCondition(srvRule.cond2 or srvRule.cond)
        check(engineCond ~= nil and type(engineCond[2]) == 'number', 'rule ' .. i .. ' reaches the engine as a number')
        local back = M.decode_rule(G.encodeRule(srvRule, i))
        check(back.arg == row.arg and back.arg2 == row.arg2 and back.cond == row.cond and back.cond2 == row.cond2,
            'rule ' .. i .. ' comes back to the editor unchanged')
    end

    -- the share code carries them as text (its fixed vocabulary is unchanged)
    local okC, C = pcall(dofile, ADDON_DIR .. '/share_code.lua')
    if okC and type(C) == 'table' and C.encode and C.decode then
        local code = C.encode({ job = 'WHM', name = 'Feedback', rules = d.rules })
        local set = code and C.decode(code)
        check(set ~= nil and set.rules[2].cond2 == 'PARTY_COUNT' and set.rules[2].arg2 == 'AT_LEAST.2.ASLEEP' and set.rules[1].arg == 'GOBLIN',
            'a share code keeps the new conditions')
    end
end

-- ================================================================= layout (0.3.9)
-- A stand-in ImGui that lays controls out on lines: where each control starts (x), how wide it is, on which line, and
-- whether it runs past the window's edge. Text is 7 px a character at 100 %, a frame 19 px high, as the game's font.
local function layoutGui(winW, scale)
    local g = { items = {}, over = {}, x = 0, endX = 0, same = false, setX = false, line = 0, nextW = false, wrap = false, W = winW }
    local cw = 7 * scale
    local function tw(t) return #(tostring(t):gsub('##.*$', '')) * cw end
    local function place(kind, label, w)
        local x
        if g.same then x = g.x else x = g.setX or 0; g.line = g.line + 1 end
        g.setX, g.same = false, false
        if kind == 'text' and g.wrap then w = math.min(w, winW - x) end
        g.items[#g.items + 1] = { kind = kind, label = tostring(label), x = x, w = w, line = g.line }
        if x + w > winW + 0.5 then g.over[#g.over + 1] = string.format('%s %s at %d, %d wide (window %d)', kind, tostring(label), x, w, winW) end
        g.endX = x + w
    end
    g.SameLine = function(off, sp) if off and off > 0 then g.x = off else g.x = g.endX + (sp or 8) end; g.same = true end
    g.NewLine = function() g.same, g.setX = false, false end
    g.SetCursorPosX = function(x) if g.same then g.x = x else g.setX = x end end
    g.GetCursorPosX = function() return g.same and g.x or (g.setX or 0) end
    g.GetContentRegionAvail = function() return { winW - (g.same and g.x or (g.setX or 0)), 400 } end
    g.CalcTextSize = function(t) return { tw(t), 13 * scale } end
    g.GetFrameHeight = function() return 19 * scale end
    g.GetFrameHeightWithSpacing = function() return 23 * scale end
    g.GetTextLineHeightWithSpacing = function() return 17 * scale end
    g.SetNextItemWidth = function(w) g.nextW = w end
    g.InputInt = function(id) place('int', id, g.nextW or 100); g.nextW = false; return false end
    g.InputText = function(id) place('input', id, g.nextW or 100); g.nextW = false; return false end
    g.BeginCombo = function(id) place('combo', id, g.nextW or 100); g.nextW = false; return false end
    g.Text = function(t) place('text', t, tw(t)) end
    g.TextColored = function(_, t) place('text', t, tw(t)) end
    g.TextUnformatted = function(t) place('text', t, tw(t)) end
    g.TextWrapped = function(t) g.wrap = true; place('text', t, tw(t)); g.wrap = false end
    g.PushTextWrapPos = function() g.wrap = true end
    g.PopTextWrapPos = function() g.wrap = false end
    g.Button = function(label, size) place('button', label, (type(size) == 'table' and (size[1] or 0) > 0) and size[1] or (tw(label) + 8 * scale)); return false end
    g.Checkbox = function(label) place('check', label, tw(label) + 24 * scale); return false end
    g.Separator = function() g.same, g.setX = false, false end
    g.IsItemHovered = function() return false end
    g.BeginTooltip = function() return false end
    return setmetatable(g, { __index = function() return function() end end })
end

local function onLine(g, line) local out = {} for _, it in ipairs(g.items) do if it.line == line then out[#out + 1] = it end end return out end
local function find(g, kind, label) for i, it in ipairs(g.items) do if it.kind == kind and it.label:find(label, 1, true) then return it, i end end end

section('(0.3.9) condition values: readable and editable at narrow widths and higher Sizes')
do
    local cat = catalogFor('jmf')
    for _, case in ipairs({ { w = 900, scale = 1.0 }, { w = 640, scale = 1.2 }, { w = 470, scale = 1.2 }, { w = 470, scale = 1.5 } }) do
        local g = layoutGui(case.w, case.scale)
        M.init({ now = function() return clock end, queue_command = function() end, imgui = g, s = function(px) return math.max(1, math.floor(px * case.scale + 0.5)) end })
        S.server = { version = 11, maxRules = 32, maxLine = 120, maxChunks = 64 }
        local sc = function(px) return math.max(1, math.floor(px * case.scale + 0.5)) end
        local labelW = sc(90)
        local tag = string.format('%d px at %d %%', case.w, case.scale * 100)
        local digits = 2 * 7 * case.scale -- (two digits)
        local function fieldOk(it) return it and (it.w - 2 * (19 * case.scale + sc(4)) - sc(8)) >= digits end

        -- Enemies: comparison + count, "above HP %" [field], "within" [field] "yalms"
        local r = { on = true, target = 'TARGET', cond = 'ENEMY_COUNT', arg = 'AT_LEAST.3.30.10', kind = 'family', name = 'STONEGA' }
        M._draw.condition_editor(r, 1, cat, labelW)
        check(#g.over == 0, 'Enemies, ' .. tag .. ': nothing runs past the window\'s edge (' .. table.concat(g.over, '; ') .. ')')
        local cnt = find(g, 'int', '##gsq-cnt1')
        local hp, hpI = find(g, 'int', '##gsq-ehp1')
        local rad, radI = find(g, 'int', '##gsq-erad1')
        check(fieldOk(cnt) and fieldOk(hp) and fieldOk(rad), 'Enemies, ' .. tag .. ': every number field shows two digits beside its - / + buttons')
        local hpLabel = g.items[hpI - 1]
        local within, yalms = g.items[radI - 1], g.items[radI + 1]
        check(hpLabel.label == 'above HP %' and hpLabel.line == hp.line and within.label == 'within' and within.line == rad.line
            and yalms and yalms.label == 'yalms' and yalms.line == rad.line,
            'Enemies, ' .. tag .. ': "above HP %" stays with its field, "within" and "yalms" with theirs')
        local cmp = find(g, 'combo', '##gsq-cmp1')
        check(cmp.line == cnt.line, 'Enemies, ' .. tag .. ': the comparison and its count stay together')
        local firstLine = find(g, 'combo', '##gsq-subj1') or g.items[1]
        local wrappedOk = true
        for line = firstLine.line + 1, g.line do
            local its = onLine(g, line)
            if its[1] and its[1].x ~= labelW then wrappedOk = false end
        end
        check(wrappedOk, 'Enemies, ' .. tag .. ': a group that wraps starts at the value column (' .. labelW .. ')')
        check(r.arg == 'AT_LEAST.3.30.10', 'Enemies, ' .. tag .. ': drawing it does not change the value')

        -- Party members: comparison + count, then the filter
        g.items, g.over, g.line, g.same, g.setX = {}, {}, 0, false, false
        local p = { on = true, target = 'PARTY', cond = 'PARTY_COUNT', arg = 'AT_LEAST.2.ASLEEP', kind = 'family', name = 'CURAGA' }
        M._draw.condition_editor(p, 1, cat, labelW)
        check(#g.over == 0 and fieldOk(find(g, 'int', '##gsq-cnt1')), 'Party members, ' .. tag .. ': nothing past the edge, the count readable')
        check(find(g, 'combo', '##gsq-pst1').w >= #'with Petrification' * 7 * case.scale, 'Party members, ' .. tag .. ': the filter list as wide as its longest choice')
        check(p.arg == 'AT_LEAST.2.ASLEEP', 'Party members, ' .. tag .. ': value unchanged')

        -- Enemy family
        g.items, g.over, g.line, g.same, g.setX = {}, {}, 0, false, false
        local f = { on = true, target = 'SELF', cond = 'ENEMY_FAMILY', arg = 'GOBLIN', kind = 'spell', name = 'BARFIRA' }
        M._draw.condition_editor(f, 1, cat, labelW)
        check(#g.over == 0 and find(g, 'combo', '##gsq-fam1').w >= #'Adamantoise' * 7 * case.scale, 'Enemy family, ' .. tag .. ': the list as wide as its longest name')

        -- a plain number condition (HP below) keeps its unit with its field
        g.items, g.over, g.line, g.same, g.setX = {}, {}, 0, false, false
        local h = { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' }
        M._draw.condition_editor(h, 1, cat, labelW)
        local val, valI = find(g, 'int', '##gsq-val1')
        check(#g.over == 0 and fieldOk(val) and g.items[valI + 1].label == '%' and g.items[valI + 1].line == val.line, 'HP below, ' .. tag .. ': the field readable, "%" beside it')
    end
end

section('(0.3.9) the status line: "<mate> runs" never overlaps its value; the Rule Set name stays green')
do
    for _, case in ipairs({ { name = 'Sturgeon', set = 'MNK-WAR', w = 900, scale = 1.2 }, { name = 'Bartholomewsen', set = 'A rather long Rule Set name', w = 900, scale = 1.2 },
                            { name = 'Bartholomewsen', set = 'A rather long Rule Set name for narrow windows', w = 380, scale = 1.5 } }) do
        local g = layoutGui(case.w, case.scale)
        local greens = {}
        g.TextColored = function(col, t)
            if col == M.theme.ok then greens[#greens + 1] = t end
            local x = g.same and g.x or (g.setX or 0)
            if not g.same then g.line = g.line + 1 end
            g.setX, g.same = false, false
            local w = #tostring(t) * 7 * case.scale
            if g.wrap then w = math.min(w, case.w - x) end
            g.items[#g.items + 1] = { kind = 'text', label = tostring(t), x = x, w = w, line = g.line }
            g.endX = x + w
        end
        -- a wrapped value is drawn with the Text colour pushed (the game's ImGuiCol_Text id), then TextUnformatted
        rawset(_G, 'ImGuiCol_Text', rawget(_G, 'ImGuiCol_Text') or 0)
        local colStack = {}
        g.PushStyleColor = function(id, col) if id == ImGuiCol_Text then colStack[#colStack + 1] = col end end
        g.PopStyleColor = function(n) for _ = 1, (n or 1) do table.remove(colStack) end end
        local plainText = g.TextUnformatted
        g.TextUnformatted = function(t) if colStack[#colStack] == M.theme.ok then greens[#greens + 1] = t end plainText(t) end
        M.init({ now = function() return clock end, queue_command = function() end, imgui = g, s = function(px) return math.max(1, math.floor(px * case.scale + 0.5)) end })
        S.server = { version = 11, maxRules = 32, maxLine = 120, maxChunks = 64, caps = { live = true } }
        S.mates = { { slot = 1, name = case.name, job = 'MNK', level = 29, chosen = 5, out = true, live = { state = 'set', num = 5, dropped = 0 } } }
        S.mateSlot = 1
        S.sets = { { num = 5, job = 'MNK', name = case.set, flags = 'o' } }
        local d = { num = 5, job = 'MNK', name = case.set, rules = {}, flags = 'o' }
        M._draw.save_bar(d)
        local label = find(g, 'text', case.name .. ' runs')
        local value = nil
        for _, it in ipairs(g.items) do if label and it.line == label.line and it.x > label.x and it ~= label then value = value or it end end
        local tag = string.format('"%s" / "%s", %d px at %d %%', case.name, case.set, case.w, case.scale * 100)
        check(label and value and value.x >= label.x + label.w, tag .. ': the value starts after the label (' .. tostring(label and (label.x + label.w)) .. ' <= ' .. tostring(value and value.x) .. ')')
        check(value and value.x + value.w <= case.w + 0.5, tag .. ': the value stays inside the window (wrapped when needed)')
        local named = false
        for _, t in ipairs(greens) do named = named or t:find(case.set, 1, true) ~= nil end
        check(named, tag .. ': the running Rule Set\'s name is drawn in the theme\'s green')
    end
end

io.write(string.format('\n%d passed, %d failed\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
