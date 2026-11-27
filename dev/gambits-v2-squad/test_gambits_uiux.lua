-- Gambits 0.3.1 UI/UX batch: stand-in tests, no game, no Ashita.
--   luajit test_gambits_uiux.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> <server root>
-- A  job-aware spell / family lists: gambits_data.lua against the server's own enums and data, and the editor's views
--    against REAL catalogs made by the server's gambits_squad.lua (catm for the mate, cat for its jobs) - unsummoned
--    mates (the catalogs come from the squad data), saved rules kept, nothing changed on the wire
-- B  per-option tooltips: drawn only through the safe helper (BeginTooltip + TextUnformatted), never a format call
-- D  Weapon Skills as a collapsible section: open/closed, remembered, its summary, no tabs
-- C  layout (content-sized lists, the Save bar, in use / editing, Save first, the Starter dropdown, status line) and
--    the status effect selector (job effects, common effects, Custom...; saved names; typing; unknown names)
-- Gameplay and the real ImGui are proven only in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER_ROOT,
       'usage: test_gambits_uiux.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server-root')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function readAll(p) local f = io.open(p, 'rb'); if not f then return nil end local s = f:read('*a'); f:close(); return s end
local loadChunk = loadstring or load

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
GetSquadWeaponSkillIds = function() return {} end
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
-- the squad: none of them summoned (the catalogs are made from the squad data alone)
local JOB = { WAR = 1, WHM = 3, BLM = 4, RDM = 5, THF = 6, PLD = 7, BRD = 10, NIN = 13 }
local SQUAD = {
    { slot = 1, id = 101, name = 'Mira', mjob = JOB.RDM, sjob = 0, jobs = { [JOB.RDM] = { level = 28 } } },
    { slot = 2, id = 102, name = 'Lyra', mjob = JOB.RDM, sjob = JOB.WHM, jobs = { [JOB.RDM] = { level = 28 }, [JOB.WHM] = { level = 14 } } },
    { slot = 3, id = 103, name = 'Bard', mjob = JOB.BRD, sjob = 0, jobs = { [JOB.BRD] = { level = 28 } } },
    { slot = 4, id = 104, name = 'Rook', mjob = JOB.WAR, sjob = JOB.NIN, jobs = { [JOB.WAR] = { level = 30 }, [JOB.NIN] = { level = 15 } } },
    { slot = 5, id = 105, name = 'Vex', mjob = JOB.RDM, sjob = 0, jobs = { [JOB.RDM] = { level = 75 } } },
    { slot = 6, id = 106, name = 'Kit', mjob = JOB.THF, sjob = 0, jobs = { [JOB.THF] = { level = 40 } } },
}
GetSquad = function() return SQUAD end
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end

-- ---------------------------------------------------------------- the editor and its catalogs
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local DATA = dofile(ADDON_DIR .. '/gambits_data.lua')
local sent, clock, prefs = {}, 100, {}
local api = { now = function() return clock end, queue_command = function(l) sent[#sent + 1] = l end, addon_data = DATA,
              get_pref = function(k) return prefs[k] end, set_pref = function(k, v) prefs[k] = v end }
M.init(api)
local S = M._S
S.server = { version = 6, maxRules = 32, maxLine = 120, maxChunks = 64 }
local function parsed(lines)
    local items, endF = {}, nil
    for _, l in ipairs(lines) do
        local ff = G.splitPlain(string.sub(l, 1, 150), '|')
        if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end
    end
    return M.parse_catalog(items, endF)
end
local n = 0
local function catm(slot) n = n + 1; return assert(parsed(run('catm ' .. n .. ' ' .. slot .. ' jm')), 'catm ' .. slot) end
local function plan(job, sub) n = n + 1; return assert(parsed(run('cat ' .. n .. ' ' .. job .. (sub and (' ' .. sub) or ''))), 'cat ' .. job) end
local MATES = {
    { slot = 1, name = 'Mira', job = 'RDM', level = 28, chosen = 0, out = false },
    { slot = 2, name = 'Lyra', job = 'RDM', level = 28, sub = 'WHM', subLevel = 14, chosen = 0, out = false },
    { slot = 3, name = 'Bard', job = 'BRD', level = 28, chosen = 0, out = false },
    { slot = 4, name = 'Rook', job = 'WAR', level = 30, sub = 'NIN', subLevel = 15, chosen = 0, out = false },
    { slot = 5, name = 'Vex', job = 'RDM', level = 75, chosen = 0, out = false },
    { slot = 6, name = 'Kit', job = 'THF', level = 40, chosen = 0, out = false },
}
local CAT, PLAN = {}, {}
for i, m in ipairs(MATES) do CAT[i] = catm(m.slot); PLAN[i] = plan(m.job, m.sub) end
local function names(list) local out = {} for _, e in ipairs(list) do out[e.name] = e end return out end
local function count(t) local c = 0 for _ in pairs(t) do c = c + 1 end return c end

-- ================================================================= A1. the generated data against the server's own
section('A1: gambits_data.lua matches the server\'s enums and data (the generator\'s --check runs in run_tests.ps1)')
do
    check(DATA.format == 'xifo-gambits-addon-data' and DATA.version == 1, 'format and version')
    local same, total = true, 0
    for name, id in pairs(xi.effect) do total = total + 1; same = same and DATA.effects[name] == id end
    check(same and total == count(DATA.effects) and total > 600, string.format('effects: exactly xi.effect (%d names, the same ids)', total))
    local bad = {}
    for name, row in pairs(DATA.spells) do
        if xi.magic.spell[name] == nil then bad[#bad + 1] = name end
        if row[1] and xi.magic.spellFamily[row[1]] == nil then bad[#bad + 1] = name .. ':' .. row[1] end
        if row.e and xi.effect[row.e] == nil then bad[#bad + 1] = name .. ':' .. row.e end
    end
    check(#bad == 0, 'every spell, family and spell effect is a server name: ' .. table.concat(bad, ' '))
    -- q follows the server's own G.mateSpells rules, read from the server's squad_spell_jobs_data.lua
    local sj = dofile(LUA_DIR .. '/squad_spell_jobs_data.lua')
    local wrong, compared = {}, 0
    for _, row in pairs(sj.spells) do
        local d = DATA.spells[row[1]]
        if d then
            compared = compared + 1
            local want = (row.g == 8 or row.g == 5 or row.g == 7) and 'x' or (row.g == 3 and 'b') or (row.sc ~= true and 'x') or nil
            if d.q ~= want then wrong[#wrong + 1] = row[1] end
        end
    end
    check(#wrong == 0 and compared > 700, string.format('the squad spell flags (Trust/Summoning/Geomancy/no scroll, blue) agree with the server data for %d spells: %s', compared, table.concat(wrong, ' ')))
    local badJa = {}
    for ja, list in pairs(DATA.jaEffects) do
        if xi.jobAbility[ja] == nil then badJa[#badJa + 1] = ja end
        for _, e in ipairs(list) do if xi.effect[e] == nil then badJa[#badJa + 1] = ja .. ':' .. e end end
    end
    check(#badJa == 0 and count(DATA.jaEffects) > 150, 'every job ability and its effects are server names (' .. count(DATA.jaEffects) .. ' abilities): ' .. table.concat(badJa, ' '))
    check(DATA.spells.PARALYZE.e == 'PARALYSIS' and DATA.spells.PROTECT.e == 'PROTECT' and DATA.spells.HASTE.e == 'HASTE'
          and DATA.spells.UTSUSEMI_ICHI.e == 'COPY_IMAGE' and DATA.spells.CURE[1] == 'CURE' and DATA.spells.CURE.e == nil
          and DATA.spells.CARBUNCLE.q == 'x', 'spot checks: Paralyze -> Paralysis, Protect, Haste, Utsusemi -> Copy Image, Cure (no effect), Carbuncle never a squad spell')
    check(DATA.jaEffects.PROVOKE == nil and DATA.jaEffects.DEFENDER[1] == 'DEFENDER', 'Provoke adds no effect (nothing guessed from its name); Defender adds Defender')
    -- every effect a starter template checks is a server effect; a starter "missing X -> ability X" really gives X
    local starterBad = {}
    for job, list in pairs(M.TEMPLATES) do
        for _, t in ipairs(list) do
            for _, r in ipairs(t.rules) do
                for _, pair in ipairs({ { r.cond, r.arg }, { r.cond2, r.arg2 } }) do
                    if (pair[1] == 'STATUS' or pair[1] == 'NOT_STATUS') and pair[2] then
                        if DATA.effects[pair[2]] == nil then starterBad[#starterBad + 1] = job .. ':' .. pair[2] end
                        if r.kind == 'ja' and r.name == pair[2] then
                            local gives = false
                            for _, e in ipairs(DATA.jaEffects[r.name] or {}) do gives = gives or e == pair[2] end
                            if not gives then starterBad[#starterBad + 1] = job .. ':' .. r.name .. ' gives no ' .. pair[2] end
                        end
                    end
                end
            end
        end
    end
    check(#starterBad == 0, 'the starters\' effects are server effects, and "missing X -> ability X" abilities give X: ' .. table.concat(starterBad, ' '))
end

-- ================================================================= A2. the job-aware lists, from the server's catalogs
section('A2: spell families and spells by job and level (RDM 28, RDM 28/WHM 14, BRD 28, RDM 75), Show all')
do
    local rdm, rdmw, brd, vex = MATES[1], MATES[2], MATES[3], MATES[5]
    -- Show all = exactly the server's family list (same names, same count)
    local all = M.family_view(CAT[1], rdm, true, PLAN[1])
    local allSet = names(all)
    local same = #all == #CAT[1].families
    for _, f in ipairs(CAT[1].families) do same = same and allSet[f] ~= nil end
    check(same and #all > 60, string.format('Show all lists the complete server family list (%d of %d)', #all, #CAT[1].families))
    local rel = names(M.family_view(CAT[1], rdm, false, PLAN[1]))
    check(rel.CURE and rel.CURE.state == 'now' and rel.HASTE and rel.HASTE.state == 'later' and rel.HASTE.level == 48
          and rel.PHALANX and rel.REFRESH and rel.RAISE, 'RDM 28 Relevant: Cure now; Haste (Lv 48), Phalanx, Refresh, Raise later')
    check(rel.CURAGA == nil and rel.HOLY == nil and rel.BANISHGA == nil and allSet.CURAGA.state == 'other'
          and allSet.CURAGA.label:find('(not RDM)', 1, true), 'RDM 28 Relevant leaves out Curaga, Holy, Banishga; Show all marks Curaga "(not RDM)"')
    local songs = 0
    for name in pairs(rel) do if name:find('MINUET') or name:find('MARCH') or name:find('BALLAD') then songs = songs + 1 end end
    check(songs == 0 and rel.UTSUSEMI == nil, 'no songs and no ninjutsu for an RDM without a sub job')
    check(rel.HASTE.label == 'Haste  (Lv 48)' and rel.CURE.label == 'Cure', 'labels: "Haste  (Lv 48)" (dimmed in the list), "Cure"')
    local nRel = count(rel)
    check(nRel < #all and nRel >= 20, string.format('RDM 28: %d relevant of %d', nRel, #all))
    -- the sub job: WHM 14 adds its families up to the sub job cap (37 at 75), marked "sub"
    local relW = names(M.family_view(CAT[2], rdmw, false, PLAN[2]))
    check(relW.CURAGA and relW.CURAGA.sub and relW.CURAGA.state == 'later' and relW.CURAGA.label:find('(sub Lv', 1, true),
          'RDM 28/WHM 14: Curaga from the sub job, later: ' .. tostring(relW.CURAGA and relW.CURAGA.label))
    local allW = names(M.family_view(CAT[2], rdmw, true, PLAN[2]))
    check(allW.HOLY and allW.HOLY.state == 'beyond' and relW.HOLY == nil, 'Holy: only WHM above sub level 37 - shown with Show all only (beyond the cap)')
    check(M.sub_cap(rdmw) == 37 and M.sub_cap(rdm) == 0 and M.sub_cap({ sub = 'WHM', level = 30, subLevel = 20 }) == 50
          and M.sub_cap({ sub = 'WHM', level = 30, subLevel = 30 }) == 75, 'the sub job cap: 37 (half), 50 or 75 when the mate\'s levels show more, 0 without')
    local bardRel = names(M.family_view(CAT[3], brd, false, PLAN[3]))
    check(bardRel.CURE == nil and (bardRel.VALOR_MINUET or bardRel.MARCH or bardRel.MAGES_BALLAD) ~= nil and count(bardRel) <= 20,
          string.format('BRD 28: songs, no Cure; %d relevant families', count(bardRel)))
    if os.getenv('UIUX_STATS') then
        for i, m in ipairs(MATES) do
            local st = {}
            for _, e in ipairs(M.family_view(CAT[i], m, true, PLAN[i])) do st[e.state] = (st[e.state] or 0) + 1 end
            local sp = {}
            for _, e in ipairs(M.spell_view(CAT[i], m, true, PLAN[i])) do sp[e.state] = (sp[e.state] or 0) + 1 end
            local jobE = M.effect_choices(CAT[i], m, PLAN[i])
            io.write(string.format('STATS %s %s%d%s: families now %d, unconfirmed %d, later %d, beyond %d, other %d (of %d) | spells now %d, unconfirmed %d, later %d, beyond %d | job effects %d\n',
                m.name, m.job, m.level, m.sub and ('/' .. m.sub .. m.subLevel) or '', st.now or 0, st.unconfirmed or 0, st.later or 0,
                st.beyond or 0, st.other or 0, #CAT[i].families, sp.now or 0, sp.unconfirmed or 0, sp.later or 0, sp.beyond or 0, #jobE))
        end
    end
    local vexLater = 0
    for _, e in ipairs(M.family_view(CAT[5], vex, false, PLAN[5])) do if e.state == 'later' then vexLater = vexLater + 1 end end
    check(vexLater == 0, 'RDM 75: nothing is "later" any more')
    -- specific spells: now, later (to 75), the sub job to its cap; never another job's spells
    local sp = names(M.spell_view(CAT[1], rdm, false, PLAN[1]))
    check(sp.CURE and sp.CURE.state == 'now' and sp.HASTE and sp.HASTE.state == 'later' and sp.HASTE.level == 48
          and sp.PHALANX and sp.REFRESH and sp.CURAGA == nil, 'Specific Spell, RDM 28: Cure now, Haste/Phalanx/Refresh later, no Curaga')
    local spAll = names(M.spell_view(CAT[2], rdmw, true, PLAN[2]))
    local spRel = names(M.spell_view(CAT[2], rdmw, false, PLAN[2]))
    check(spAll.HOLY and spAll.HOLY.state == 'beyond' and spRel.HOLY == nil and spAll.FREEZE == nil,
          'Show all adds the sub job\'s spells above its cap (Holy), never another job\'s (Freeze)')
    check(spRel.SHANTOTTO == nil and spAll.SHANTOTTO == nil and spAll.CARBUNCLE == nil, 'no Trust or Summoning spells, even with Show all')
    -- no planning list yet (loading / failed / older server): nothing is filtered or marked
    local raw = M.family_view(CAT[1], rdm, false, nil)
    check(#raw == #CAT[1].families and raw[1].state == 'unknown', 'without the job list the family list is the server\'s, unfiltered')
    M.set_data(nil)
    local noData = M.family_view(CAT[1], rdm, false, PLAN[1])
    check(#noData == #CAT[1].families, 'without gambits_data.lua the family list is the server\'s, unfiltered')
    M.set_data(DATA)
end

section('A3: saved rules are kept exactly; notes say why; the wire is unchanged; the planning list is asked for once')
do
    local rdm = MATES[1]
    local rules = {
        { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'HOLY' },      -- not RDM
        { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'HASTE', kind = 'spell', name = 'HASTE' }, -- RDM 48
        { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURAGA' },     -- not RDM
        { on = true, target = 'SELF', cond = 'NOT_STATUS', arg = 'REFRESH', kind = 'family', name = 'REFRESH' }, -- RDM 41
        { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '40', kind = 'spell', name = 'FREEZE' },      -- BLM only
    }
    local before = {}
    for i, r in ipairs(rules) do before[i] = M.encode_rule(r) end
    check(M.action_note(rules[1], CAT[1], rdm, PLAN[1]):find('Not an RDM family', 1, true), 'Holy: "Not an RDM family ... kept as saved"')
    check(M.action_note(rules[2], CAT[1], rdm, PLAN[1]):find('Mira learns Haste at level 48', 1, true), 'Haste: "Mira learns Haste at level 48: this rule starts working then"')
    check(M.action_note(rules[4], CAT[1], rdm, PLAN[1]):find('first Refresh spell at level 41', 1, true), 'Refresh: the first Refresh spell at level 41')
    check(M.action_note(rules[5], CAT[1], rdm, PLAN[1]):find('not in Mira\'s spell list', 1, true), 'Freeze (another job): the existing "not in the spell list ... kept" note')
    check(M.action_note({ kind = 'family', name = 'CURE' }, CAT[1], rdm, PLAN[1]) == nil, 'no note for Cure (usable now)')
    check(M.action_note(rules[1], CAT[1], rdm, nil) == nil or not M.action_note(rules[1], CAT[1], rdm, nil):find('Not an', 1, true),
          'without the job list nothing is claimed about a family')
    local after = {}
    for i, r in ipairs(rules) do after[i] = M.encode_rule(r) end
    check(table.concat(before, '|') == table.concat(after, '|'), 'the views and notes change no rule')
    -- the codec is the wire format of before (STATUS / NOT_STATUS carry the effect id as it is)
    check(M.encode_rule(rules[2]) == '1,SELF,NOT_STATUS,HASTE,,,s,HASTE,' and M.encode_rule({ on = true, target = 'SELF', cond = 'HAS_TOP_ENMITY',
          cond2 = 'NOT_STATUS', arg2 = 'DEFENDER', kind = 'ja', name = 'DEFENDER' }) == '1,SELF,HAS_TOP_ENMITY,,NOT_STATUS,DEFENDER,j,DEFENDER,',
          'the rule codec is unchanged')
    -- the server's checks are unchanged: a saved unknown effect is still refused there, a known one accepted
    local function problems(cond) return table.concat(R.ruleProblems({ id = 'r1', on = true, target = 'SELF', cond = cond, action = { 'ja', 'DEFENDER' } }), ';') end
    check(problems({ 'NOT_STATUS', 'NOT_A_REAL_EFFECT' }):find('unknown status effect', 1, true) and problems({ 'NOT_STATUS', 'DEFENDER' }) == '',
          'server validation as before: unknown effect refused, Defender accepted')
    -- ensure_plan asks the server for the job list once (cat <n> RDM WHM), and only when nothing else is waiting
    S.plan = nil
    sent = {}
    M.ensure_plan(MATES[2])
    M.ensure_plan(MATES[2])
    for _ = 1, 5 do clock = clock + 1.5; M.tick() end
    local ids = {}
    for _, l in ipairs(sent) do local id = l:match('^/say !gsq cat (%S+) RDM WHM$'); if id then ids[id] = true end end
    check(count(ids) == 1 and S.plan and S.plan.key == 'RDM/WHM' and S.plan.loading,
          'one "!gsq cat <n> RDM WHM" request for RDM/WHM (the transport may resend the same line): ' .. table.concat(sent, ' | '))
    S.server.version = 3
    S.plan = nil
    M.ensure_plan(MATES[1])
    check(S.plan == nil, 'an older server (no per-mate catalog): no extra request; its catalog already is the job list')
    S.server.version = 6
    local old = { perMate = false, families = CAT[1].families, spells = PLAN[1].spells, jas = PLAN[1].jas }
    check(M.plan_for(old, MATES[1]) == old, 'older server: the job catalog itself is the planning list')
end

-- ---------------------------------------------------------------- a stand-in ImGui that logs what is drawn
local function fakeGui(opts)
    opts = opts or {}
    local g = { log = {}, tips = {}, texts = {}, formats = 0, errors = {}, depth = 0, colors = 0, ids = 0, dis = 0, tt = 0, wraps = 0,
                children = {}, clicks = {}, combos = opts.combos or {}, picks = {}, typed = {}, deact = {}, avail = opts.avail or { 1000, 560 },
                labels = {}, sizes = {} }
    g.wrapVals, g.wrappedTexts = {}, {}
    local function shown(t)
        g.texts[#g.texts + 1] = t
        if g.tt > 0 then g.tips[#g.tips + 1] = t
        else
            g.y = (g.y or 0) + 16 -- (text takes room in the window; tooltips do not)
            if g.wraps > 0 then g.wrappedTexts[#g.wrappedTexts + 1] = t end
        end
    end
    local function fmt(t) g.formats = g.formats + 1; return t end
    g.Text = function(t) shown(t) end
    g.TextUnformatted = function(t) shown(t) end
    g.TextColored = function(_, t) shown(t) end
    g.TextWrapped = function(t) shown(fmt(t)) end
    g.BulletText = function(t) shown(fmt(t)) end
    g.LabelText = function(_, t) shown(fmt(t)) end
    g.SetTooltip = function(t) g.tips[#g.tips + 1] = fmt(t) end
    g.SetItemTooltip = function(t) g.tips[#g.tips + 1] = fmt(t) end
    g.BeginTooltip = function() g.tt = g.tt + 1; return true end
    g.EndTooltip = function() g.tt = g.tt - 1 end
    g.PushTextWrapPos = function(v) g.wraps = g.wraps + 1; g.wrapVals[#g.wrapVals + 1] = { v = v, tip = g.tt > 0 } end
    if opts.fontSize then g.GetFontSize = function() return opts.fontSize end end
    g.PopTextWrapPos = function() g.wraps = g.wraps - 1 end
    g.SameLine, g.SetNextItemWidth, g.Separator, g.NewLine = function() end, function() end, function() end, function() end
    g.AlignTextToFramePadding, g.SetCursorPosX = function() end, function() end
    g.IsItemHovered = function() return opts.hover == true end
    g.GetContentRegionAvail = function() return { g.avail[1], g.avail[2] } end
    g.GetFrameHeightWithSpacing = function() return 24 end
    g.y = g.y or 0
    g.GetCursorPosY = function() return g.y end
    local function item(h) g.y = g.y + (h or 24) end
    g.Button = function(label) g.labels[#g.labels + 1] = label; item(); g.log[#g.log + 1] = 'button ' .. label
        if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    g.Selectable = function(label) g.labels[#g.labels + 1] = label; item()
        local want = g.picks[g.combo or ''] if want and label:find(want, 1, true) == 1 then g.picks[g.combo] = nil; return true end
        if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    g.Checkbox = function(label, t) g.labels[#g.labels + 1] = label; item(); if g.clicks[label] then g.clicks[label] = nil; t[1] = not t[1]; return true end return false end
    g.InputText = function(id, buf) item(); g.log[#g.log + 1] = 'input ' .. id
        if g.typed[id] ~= nil then buf[1] = g.typed[id]; g.typed[id] = nil; return true end return false end
    g.IsItemDeactivatedAfterEdit = (opts.noDeact ~= true) and function() local d = g.deact.now; g.deact.now = nil; return d == true end or nil
    g.InputInt = function() item(); return false end
    g.BeginCombo = function(id, preview) g.log[#g.log + 1] = 'combo ' .. id .. ' = ' .. tostring(preview); item()
        if g.combos[id] then g.combo = id; return true end return false end
    g.EndCombo = function() g.combo = nil end
    g.PushStyleColor = function() g.colors = g.colors + 1 end
    g.PopStyleColor = function(k) g.colors = g.colors - (k or 1) end
    g.PushStyleVar, g.PopStyleVar = function() end, function() end
    g.PushID = function() g.ids = g.ids + 1 end
    g.PopID = function() g.ids = g.ids - 1 end
    g.BeginChild = function(id, size) g.depth = g.depth + 1; g.children[#g.children + 1] = id; g.sizes[id] = { size[1], size[2] }
        g.log[#g.log + 1] = 'child ' .. id; return true end
    g.EndChild = function() g.depth = g.depth - 1; g.log[#g.log + 1] = 'endchild' end
    g.BeginDisabled = function() g.dis = g.dis + 1; g.log[#g.log + 1] = 'disabled' end
    g.EndDisabled = function() g.dis = g.dis - 1 end
    if opts.collapsing ~= false then
        g.SetNextItemOpen = function(v) g.nextOpen = v end
        g.CollapsingHeader = function(label) g.labels[#g.labels + 1] = label; item(); g.log[#g.log + 1] = 'header ' .. label
            local open = g.nextOpen == true
            if g.clicks.header then g.clicks.header = nil; open = not open end
            return open end
    end
    return g
end
local function balanced(g) return g.depth == 0 and g.colors == 0 and g.ids == 0 and g.dis == 0 and g.tt == 0 and g.wraps == 0 end
local function hasLabel(g, part) for _, l in ipairs(g.labels) do if l:find(part, 1, true) then return true end end return false end
local function hasText(g, part) for _, t in ipairs(g.texts) do if tostring(t):find(part, 1, true) then return true end end return false end
local function hasTip(g, part) for _, t in ipairs(g.tips) do if tostring(t):find(part, 1, true) then return true end end return false end
local function logHas(g, part) for _, l in ipairs(g.log) do if l:find(part, 1, true) then return true end end return false end
for _, name in ipairs({ 'ImGuiCol_Text', 'ImGuiCol_Border', 'ImGuiCol_Button', 'ImGuiCol_ButtonHovered', 'ImGuiCol_Header',
    'ImGuiCol_HeaderHovered', 'ImGuiChildFlags_Borders' }) do rawset(_G, name, 1) end

local function setup(g, mateIndex, draft, sScale)
    api.imgui = g
    api.s = function(px) return px * (sScale or 1) end
    M.init(api)
    S.server = { version = 6, maxRules = 32, maxLine = 120, maxChunks = 64 }
    S.mates = {}
    for i, m in ipairs(MATES) do S.mates[i] = m end
    local m = MATES[mateIndex]
    S.mateSlot = m.slot
    S.cat, S.catJob = CAT[mateIndex], M.catalog_key(m)
    S.plan = { key = M.plan_key(m), cat = PLAN[mateIndex] }
    S.sets = { { num = 3, job = m.job, name = 'Mage 28', flags = 'o', rules = draft and #draft.rules or 1, rev = '1' },
               { num = 5, job = m.job, name = 'Mage 75 plan', flags = 'o', rules = 2, rev = '1' } }
    S.draft, S.sel, S.selectedSet = draft, draft and 1 or nil, draft and draft.num or nil
    S.ws = { slot = m.slot, data = { slot = m.slot, source = 'd', mode = 1, tp = 1000, ws = 0, engine = true, out = false }, edit = { control = 0, mode = 1, tp = 1000, ws = 0 } }
    S.message, S.progress = nil, nil
    return m
end
local function rule(target, cond, arg, cond2, arg2, kind, name)
    return { on = true, target = target, cond = cond, arg = arg, cond2 = cond2, arg2 = arg2, kind = kind, name = name }
end

-- ================================================================= B. tooltips
section('B: per-option tooltips (Target, Condition, Action names, effects), only through BeginTooltip + TextUnformatted')
do
    local g = fakeGui({ hover = true, combos = { ['##gsq-target'] = true, ['##gsq-subj1'] = true, ['##gsq-subj2'] = true,
                                                 ['##gsq-name'] = true, ['##gsq-eff2'] = true, ['##gsq-kind'] = true } })
    local d = { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = {
        rule('PARTY_LOWEST_HPP', 'HPP_LT', '50', 'NOT_STATUS', 'PROTECT', 'family', 'CURE') } }
    setup(g, 1, d)
    local ok, err = pcall(M.draw)
    check(ok, 'the editor draws with every dropdown open and everything hovered: ' .. tostring(err))
    check(hasTip(g, M.TARGET_HELP.PARTY_LOWEST_HPP) and hasTip(g, M.TARGET_HELP.TANK), 'Target entries carry their help (Lowest HP, with its "%", and Tank)')
    check(hasTip(g, M.SUBJECT_HELP.MP) and hasTip(g, M.SUBJECT_HELP.STATUS) and hasTip(g, 'No second condition'), 'Condition subjects carry their help')
    check(hasTip(g, 'Best of Cure: the strongest spell of this family Mira knows') and hasTip(g, 'Learned later (RDM level 48)'),
          'family entries: what Best of does, the job\'s spells and levels, and "learned later"')
    check(hasTip(g, 'Protect: given by spell Protect') or hasTip(g, 'Protect: a common status effect'), 'effect entries carry their source')
    check(hasTip(g, M.KIND_HELP.burst), 'Action kinds keep their help')
    check(g.formats == 0, 'no text went to SetTooltip / SetItemTooltip / TextWrapped / BulletText / LabelText: ' .. g.formats)
    check(balanced(g), 'balanced (tooltips, colours, children, ids)')
    local keys = {}
    for _, subj in ipairs(M.SUBJECTS) do keys[#keys + 1] = M.SUBJECT_HELP[subj.key] and '' or subj.key end
    check(table.concat(keys) == '', 'every condition subject has a help text: ' .. table.concat(keys, ' '))
    -- the source itself: the format-reading calls appear only in the two documented fallbacks
    local src = readAll(ADDON_DIR .. '/squad_editor.lua')
    local _, nSet = src:gsub('g%.SetTooltip%(', '')
    local _, nWrap = src:gsub('g%.TextWrapped%(', '')
    local _, nItem = src:gsub('SetItemTooltip', '')
    local _, nBItem = src:gsub('BeginItemTooltip', '')
    check(nSet == 1 and nWrap == 1 and nItem == 0 and nBItem == 0,
          string.format('squad_editor.lua: SetTooltip %d and TextWrapped %d (the fallbacks only), SetItemTooltip %d, BeginItemTooltip %d', nSet, nWrap, nItem, nBItem))
end

-- ================================================================= D. Weapon Skills section
section('D: Weapon Skills is a collapsible section of the editor: closed (summary) / open (the same panel), remembered')
do
    local g = fakeGui()
    local d = { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = { rule('PARTY', 'HPP_LT', '50', nil, nil, 'family', 'CURE') } }
    prefs.ws_open = nil
    setup(g, 1, d)
    check(S.wsOpen == false, 'closed by default')
    M.draw()
    check(logHas(g, 'header Weapon Skills: Mira (RDM)##gsq-ws-section') and not hasLabel(g, 'Apply WS settings now##gsq-ws-apply'),
          'closed: the section header, not the panel')
    check(hasText(g, 'Squad default (automatic skillchains, every weapon skill).'), 'closed: one summary line (what is saved)')
    check(not hasLabel(g, '##gsq-view-'), 'no tab buttons any more')
    -- closed and not loaded yet: it asks the server for nothing (the same requests as the old tab)
    S.ws, sent = nil, {}
    M.draw()
    for _ = 1, 3 do clock = clock + 1.5; M.tick() end
    local wsg = false
    for _, l in ipairs(sent) do wsg = wsg or l:find('!gsq wsg', 1, true) ~= nil end
    check(not wsg and hasText(g, 'Open to see and change Mira\'s weapon skill settings.'), 'closed and not loaded: no wsg request, "Open to see ..."')
    g.labels = {}
    S.ws = { slot = 1, data = { slot = 1, source = 'd', mode = 1, tp = 1000, ws = 0, engine = true, out = false }, edit = { control = 0, mode = 1, tp = 1000, ws = 0 } }
    g.clicks.header = true
    M.draw()
    check(S.wsOpen == true and prefs.ws_open == true, 'clicking the header opens it, and the choice is saved in the settings')
    g.labels = {}
    M.draw()
    check(hasLabel(g, 'Apply WS settings now##gsq-ws-apply') and hasLabel(g, 'Save##gsq-ws-save') and hasLabel(g, 'Reset to Squad default##gsq-ws-reset'),
          'open: the same panel and buttons (own Save, Apply WS settings now, Reset)')
    check(balanced(g), 'balanced, open and closed')
    -- remembered: a new start reads it back
    M.init(api)
    check(S.wsOpen == true, 'the next start opens it again (settings)')
    -- a binding without CollapsingHeader: a toggle button
    local g2 = fakeGui({ collapsing = false })
    setup(g2, 1, d)
    S.wsOpen = false
    M.draw()
    check(hasLabel(g2, '[+] Weapon Skills: Mira##gsq-ws-section') and balanced(g2), 'without CollapsingHeader: a [+] toggle button')
    -- the summary line's texts
    check(M.ws_stored_text({ source = 'c', mode = 1, tp = 1000, ws = 0 }):find('^Custom: Open at 1000 TP') ~= nil
          and M.ws_stored_text({ source = 'n', legacyTp = 0, legacyWs = 0 }):find('No Gambits setting yet', 1, true), 'summary texts: Custom / no setting')
    S.ws.edit = { control = 1, mode = 1, tp = 1000, ws = 0 }
    check(M.ws_summary(MATES[1]):find('Unsaved weapon skill changes.', 1, true), 'unsaved WS changes show in the summary ("Unsaved weapon skill changes.")')
    -- an older server: no section at all
    local g3 = fakeGui()
    setup(g3, 1, d)
    S.server.version = 4
    M.draw()
    check(not logHas(g3, 'gsq-ws-section') and balanced(g3), 'a server without weapon skill settings (version 4): no section')
    prefs.ws_open = nil
end

-- ================================================================= C. layout
section('C: layout - content-sized lists (2 and 32 rules), the Save bar, in use / editing, Save first, Starters, status line')
do
    check(M.list_height(2, 24, 400, 1) == 2 * 24 + 10 and M.list_height(32, 24, 300, 1) == 300 and M.list_height(0, 24, 300, 3) == 3 * 24 + 10,
          'list_height: a short list is its rows, a long one stops at the limit, at least the minimum')
    local function draft(nRules)
        local rules = {}
        for i = 1, nRules do rules[i] = rule('PARTY', 'HPP_LT', tostring(10 + i), nil, nil, 'family', 'CURE') end
        return { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = rules, dirty = false }
    end
    for _, case in ipairs({ { 'classic', 1, { 1000, 560 } }, { 'squad', 0.7, { 700, 400 } }, { 'crimson', 2, { 1060, 580 } } }) do
        for _, nRules in ipairs({ 2, 32 }) do
            local g = fakeGui({ avail = case[3] })
            setup(g, 1, draft(nRules), case[2])
            M.set_theme(case[1])
            M.draw(); M.draw() -- (the second frame uses the first frame's measurements)
            local h = g.sizes['##gsq-rules'] and g.sizes['##gsq-rules'][2]
            -- (0.3.1 polish) the list's height is M.rule_list_height of this frame's measures: whole rows; 2 rules get
            -- 2 more rows of room (4) when there is space, 32 rules stop at the free space (at least 4) and scroll
            local want, rows = M.rule_list_height(nRules, 24, S.layout.bodyH, S.layout.restH)
            local ok = h == want and (h - 10 * case[2]) % 24 == 0
            if nRules == 2 then
                ok = ok and rows >= 2 and rows <= 4
            else
                ok = ok and rows >= 4 and rows < 32
            end
            check(ok and balanced(g), string.format('%s, scale %d %%, %dx%d, %d rules: rule list %s px, balanced', case[1], case[2] * 100,
                case[3][1], case[3][2], nRules, tostring(h)))
            -- the Save bar is outside (after) the scrolling body
            local bodyEnd, save = nil, nil
            local depthAt = 0
            for i, l in ipairs(g.log) do
                if l == 'child ##gsq-right-body' then depthAt = i end
                if l:find('##gsq-save', 1, true) or l:find('##gsq-assign', 1, true) or l:find('##gsq-apply', 1, true) then save = i end -- (0.3.4: any action of the bar)
            end
            local closes = 0
            for i = depthAt, (save or 0) do if g.log[i] == 'endchild' then closes = closes + 1 end end
            check(save and depthAt > 0 and closes >= 1 + (nRules > 0 and 1 or 0), 'the Save button comes after the scrolling body (always visible)')
        end
    end
    M.set_theme('classic')
    -- in use / editing, Save first
    local g = fakeGui()
    local d = draft(3)
    setup(g, 1, d)
    MATES[1].chosen = 3
    d.dirty = true
    M.draw()
    -- (0.3.5) "in use" was said from the choice alone. The row now says what the mate does with the set ("chosen" here:
    -- this stand-in server does not report what a mate runs; "active" only on the server's word, test_gambits_save_apply),
    -- and the heading's "in use by" became the status area's "<mate> runs" line.
    -- (0.3.6) the row is the set's name; chosen / editing / not saved are in the status area and the row's tooltip (section Q)
    check(hasLabel(g, '3  Mage 28##gsq-set-3') and hasLabel(g, '5  Mage 75 plan##gsq-set-5'),
          'the set list shows the names; nothing is squeezed in after them')
    check(hasText(g, 'Mira runs') and hasText(g, 'Editing') and not hasText(g, 'in use by Mira'), 'the status area says what is edited and what Mira runs; the heading no longer says "in use by"')
    check(hasLabel(g, 'Save *##gsq-save') and not hasLabel(g, 'Assign & Apply##gsq-assign'), '(0.3.4) with unsaved changes the bar offers Save, never an Assign & Apply of the older saved rules')
    sent = {}
    g.clicks['Assign & Apply##gsq-assign'] = true
    M.draw()
    for _ = 1, 3 do clock = clock + 1.5; M.tick() end
    local assigned = false
    for _, l in ipairs(sent) do assigned = assigned or l:find('!squad ruleset', 1, true) ~= nil end
    check(not assigned, 'and a click on it does nothing then')
    check(hasText(g, 'Unsaved changes') and hasText(g, 'Mira uses this Rule Set and is not summoned: the saved rules apply when it is called.'), 'the bar says what is not saved and when it applies')
    MATES[1].chosen = 0
    -- the Starter dropdown (THF has two), the single starter button (WAR)
    local gt = fakeGui()
    setup(gt, 6, nil)
    M.draw()
    check(logHas(gt, 'combo ##gsq-tpl = Starter...') and not hasLabel(gt, '##gsq-tpl1'), 'THF: one Starter dropdown for its two starters')
    local gw = fakeGui()
    setup(gw, 4, nil)
    M.draw()
    check(hasLabel(gw, 'Starter: Basic Warrior##gsq-tpl1'), 'WAR: the single starter stays a button')
    -- the status line: no room taken without a message; a message can be hidden
    local gs = fakeGui({ avail = { 1000, 560 } })
    setup(gs, 1, draft(2))
    M.draw()
    local quiet = gs.sizes['##gsq-left'][2]
    M.say('Saved as Rule Set 3.')
    M.draw()
    local talking = gs.sizes['##gsq-left'][2]
    check(quiet > talking, string.format('the panels use the status area while there is no message (%d px vs %d px)', quiet, talking))
    gs.clicks['x##gsq-dismiss'] = true
    M.draw()
    check(S.message == nil, 'the x hides the message')
end

-- ================================================================= C. the status effect selector
section('C: Has effect / Missing effect - one dropdown (job effects, common, Custom...), saved names kept, typing, unknown names')
do
    -- the lists
    local job, common = M.effect_choices(CAT[4], MATES[4], PLAN[4]) -- WAR 30 / NIN 15
    local jobSet = names(job)
    check(jobSet.DEFENDER and jobSet.BERSERK and jobSet.WARCRY and jobSet.COPY_IMAGE, 'WAR/NIN: Defender, Berserk, Warcry (WAR abilities) and Copy Image (Utsusemi, NIN sub)')
    local dup = false
    for _, c in ipairs(common) do dup = dup or jobSet[c] ~= nil end
    check(not dup and #common > 0, 'the common effects follow, without the ones already listed for the job')
    check(jobSet.HASTE == nil, 'nothing from other jobs (no Haste for WAR/NIN)')
    local thf = names((M.effect_choices(CAT[6], MATES[6], PLAN[6])))
    check(thf.SNEAK_ATTACK and thf.TRICK_ATTACK, 'THF: Sneak Attack and Trick Attack')
    -- draw helpers: the condition editor of the selected rule, with dropdowns opened on request
    local function frame(g, r, mateIndex)
        local d = { num = 3, job = MATES[mateIndex].job, name = 'Effects', flags = 'o', rules = { r }, dirty = false }
        if S.draft ~= d and not (S.draft and S.draft.rules[1] == r) then setup(g, mateIndex, d) end
        api.imgui = g
        M.draw()
        return d
    end
    -- Custom is always offered (any job, also without the data file)
    local g = fakeGui({ combos = { ['##gsq-eff2'] = true } })
    local r = rule('SELF', 'HAS_TOP_ENMITY', nil, 'NOT_STATUS', 'DEFENDER', 'ja', 'DEFENDER')
    frame(g, r, 4)
    check(hasLabel(g, 'Custom...##'), 'Custom... is the last entry (WAR)')
    check(hasLabel(g, 'Defender  (WAR)##') and r.arg2 == 'DEFENDER' and not logHas(g, 'input ##gsq-efftype2'),
          'a saved Defender is a job entry: no text field, value unchanged')
    api.addon_data = nil -- (setup's M.init reads it; and the file next to the addon is not found either)
    package.loaded['gambits_data'] = nil
    package.preload['gambits_data'] = function() error('gambits_data.lua is missing (test)') end
    local g0 = fakeGui({ combos = { ['##gsq-eff2'] = true } })
    frame(g0, rule('SELF', 'HAS_TOP_ENMITY', nil, 'NOT_STATUS', 'PROTECT', 'ja', 'DEFENDER'), 1)
    check(M.DATA == nil and hasLabel(g0, 'Custom...##') and hasLabel(g0, 'Protect##') and not hasText(g0, '(unknown effect)'),
          'without gambits_data.lua: the common effects and Custom..., nothing marked unknown')
    package.preload['gambits_data'] = nil
    api.addon_data = DATA
    M.set_data(DATA)
    -- every starter's effects stay exactly as they are when drawn for its job
    local changed = {}
    local jobIndex = { WAR = 4, THF = 6, RDM = 1, BRD = 3 }
    for job, list in pairs(M.TEMPLATES) do
        for _, t in ipairs(list) do
            for _, tr in ipairs(t.rules) do
                if tr.cond == 'STATUS' or tr.cond == 'NOT_STATUS' or tr.cond2 == 'STATUS' or tr.cond2 == 'NOT_STATUS' then
                    local copy = {}
                    for k, v in pairs(tr) do copy[k] = v end
                    local before = M.encode_rule(copy)
                    local gg = fakeGui()
                    S.draft = nil
                    frame(gg, copy, jobIndex[job] or 1)
                    frame(gg, copy, jobIndex[job] or 1)
                    if M.encode_rule(copy) ~= before then changed[#changed + 1] = job .. ':' .. before end
                end
            end
        end
    end
    check(#changed == 0, 'every starter rule with an effect is unchanged after drawing it (all jobs): ' .. table.concat(changed, ' '))
    -- a saved name outside the lists: Custom, kept, marked when the server has no such effect
    local gu = fakeGui()
    local ru = rule('SELF', 'NOT_STATUS', 'NOT_A_REAL_EFFECT', nil, nil, 'ja', 'DEFENDER')
    S.draft = nil
    frame(gu, ru, 4)
    frame(gu, ru, 4)
    check(ru.arg == 'NOT_A_REAL_EFFECT' and logHas(gu, 'combo ##gsq-eff1 = Custom: Not A Real Effect') and logHas(gu, 'input ##gsq-efftype1')
          and hasText(gu, '(unknown effect)'), 'a saved unknown name opens in Custom, unchanged, marked "(unknown effect)"')
    local gk = fakeGui()
    local rk = rule('SELF', 'NOT_STATUS', 'AUSPICE', nil, nil, 'ja', 'DEFENDER') -- (a real effect, not a WAR one, not common)
    S.draft = nil
    frame(gk, rk, 4)
    check(rk.arg == 'AUSPICE' and logHas(gk, 'Custom: Auspice') and not hasText(gk, '(unknown effect)'), 'a saved real effect of another job: Custom, kept, not marked unknown')
    -- typing in Custom: spaces, partial names, empty, Enter
    local gt = fakeGui()
    local rt = rule('SELF', 'NOT_STATUS', 'DEFENDER', nil, nil, 'ja', 'DEFENDER')
    S.draft = nil
    frame(gt, rt, 4)
    gt.picks = {}
    gt.combos['##gsq-eff1'] = true
    gt.picks['##gsq-eff1'] = 'Custom...'
    frame(gt, rt, 4)
    gt.combos['##gsq-eff1'] = nil
    frame(gt, rt, 4)
    check(logHas(gt, 'input ##gsq-efftype1') and rt.arg == 'DEFENDER', 'choosing Custom... shows the text field; the value is still Defender')
    gt.typed['##gsq-efftype1'] = 'sneak att'
    frame(gt, rt, 4)
    check(rt.arg == 'DEFENDER' and hasText(gt, '(Enter to use)'), 'a half-typed name ("sneak att") changes nothing yet')
    gt.typed['##gsq-efftype1'] = 'sneak attack'
    frame(gt, rt, 4)
    check(rt.arg == 'SNEAK_ATTACK', 'a known name with a space ("sneak attack") is used at once: SNEAK_ATTACK')
    gt.typed['##gsq-efftype1'] = ''
    frame(gt, rt, 4)
    check(rt.arg == 'SNEAK_ATTACK' and hasText(gt, '(keeps Sneak Attack)'), 'emptying the field keeps the value')
    gt.typed['##gsq-efftype1'] = '!!'
    frame(gt, rt, 4)
    check(rt.arg == 'SNEAK_ATTACK', 'text that is not a name keeps the value')
    gt.typed['##gsq-efftype1'] = 'my effect'
    gt.deact.now = true
    frame(gt, rt, 4)
    check(rt.arg == 'MY_EFFECT' and hasText(gt, '(unknown effect)'), 'Enter on an unknown name uses it as typed (MY_EFFECT), marked unknown - never silently')
    -- a binding that cannot tell when editing ends: as before (at once), still marked
    local gn = fakeGui({ noDeact = true })
    local rn = rule('SELF', 'NOT_STATUS', 'XYZ_NOT_REAL', nil, nil, 'ja', 'DEFENDER')
    S.draft = nil
    frame(gn, rn, 4)
    gn.typed['##gsq-efftype1'] = 'abc'
    frame(gn, rn, 4)
    check(rn.arg == 'ABC' and hasText(gn, '(unknown effect)'), 'without IsItemDeactivatedAfterEdit a typed name is used at once (the old behaviour), marked')
    -- picking a listed entry leaves Custom
    local gp = fakeGui()
    S.draft = nil
    frame(gp, rt, 4)
    gp.combos['##gsq-eff1'] = true
    gp.picks['##gsq-eff1'] = 'Berserk  (WAR)'
    frame(gp, rt, 4)
    gp.combos['##gsq-eff1'] = nil
    gp.log = {}
    frame(gp, rt, 4)
    check(rt.arg == 'BERSERK' and not logHas(gp, 'input ##gsq-efftype1'), 'choosing Berserk from the list: BERSERK, no text field')
    check(M.encode_rule(rt) == '1,SELF,NOT_STATUS,BERSERK,,,j,DEFENDER,', 'saved as before: ' .. M.encode_rule(rt))
    -- read-only sets: nothing changes
    local gr = fakeGui()
    local rr = rule('SELF', 'NOT_STATUS', 'DEFENDER', nil, nil, 'ja', 'DEFENDER')
    local dr = { num = 3, job = 'WAR', name = 'RO', flags = 'r', readonly = true, rules = { rr } }
    setup(gr, 4, dr)
    gr.typed['##gsq-efftype1'] = 'haste'
    M.draw()
    check(rr.arg == 'DEFENDER' and balanced(gr), 'a read-only set is never changed by the selector')
end

-- ================================================================= 0.3.1 polish
section('polish: rule list height (rules + room, free space, steady), tooltip wrapping, wrapped notes, WS "unsaved"')
do
    -- the height rule itself (rows of 24 px, s() = 1 here: pad 10)
    api.s = function(px) return px end
    M.init(api)
    local function rowsFor(n, spareRows) local _, r = M.rule_list_height(n, 24, 18 + 10 + spareRows * 24 + 100, 100); return r end
    check(rowsFor(1, 20) == 4 and rowsFor(2, 20) == 4 and rowsFor(3, 20) == 5 and rowsFor(6, 20) == 8 and rowsFor(8, 20) == 8,
          'short sets: their rules + 2 rows of room, at least 4, the room ends at 8 rows (1->4, 2->4, 3->5, 6->8, 8->8)')
    check(rowsFor(12, 20) == 12 and rowsFor(20, 20) == 20, 'longer sets grow with their rules while there is room (12, 20)')
    check(rowsFor(32, 15) == 15 and rowsFor(32, 2) == 4 and rowsFor(2, 1) == 2 and rowsFor(3, 2) == 3,
          '32 rules stop at the free space (15) and never below 4 rows; a short set never below its own rules')
    local h1 = M.rule_list_height(3, 24, 800, 200)
    check(h1 == 5 * 24 + 10, 'whole rows only: 3 rules = 5 rows + padding (' .. tostring(h1) .. ')')

    -- in the editor: Weapon Skills closed vs open, steady when another rule is selected
    local function draft(n, noteRule)
        local rules = {}
        for i = 1, n do rules[i] = rule('PARTY', 'HPP_LT', tostring(10 + i), nil, nil, 'family', 'CURE') end
        if noteRule then rules[noteRule] = rule('PARTY', 'HPP_LT', '50', nil, nil, 'family', 'HOLY') end -- (a gold note: a taller editor)
        return { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = rules }
    end
    local g = fakeGui({ avail = { 1000, 1400 } })
    setup(g, 1, draft(12))
    M.draw(); M.draw()
    check(g.sizes['##gsq-rules'][2] == 12 * 24 + 10, '12 rules with room: all 12 rows (' .. tostring(g.sizes['##gsq-rules'][2]) .. ' px)')
    g = fakeGui({ avail = { 1000, 900 } })
    setup(g, 1, draft(20))
    S.wsOpen = false
    M.draw(); M.draw(); M.draw()
    local closedH = g.sizes['##gsq-rules'][2]
    S.wsOpen = true
    M.draw(); M.draw(); M.draw()
    local openH = g.sizes['##gsq-rules'][2]
    local saveAfter = false -- (0.3.4: the bar shows the actions that fit; any of them counts)
    for _, l in ipairs(g.log) do saveAfter = saveAfter or l:find('##gsq-save', 1, true) ~= nil or l:find('##gsq-assign', 1, true) ~= nil or l:find('##gsq-apply', 1, true) ~= nil end
    check(closedH > 4 * 24 + 10 and openH < closedH and openH >= 4 * 24 + 10 and saveAfter,
          string.format('20 rules in 900 px: %d px with Weapon Skills closed, fewer with it open (%d px, >= 4 rows); the Save bar is drawn', closedH, openH))
    S.wsOpen = false
    M.draw(); M.draw()
    check(g.sizes['##gsq-rules'][2] == closedH, 'closing Weapon Skills gives the room back')
    local g2 = fakeGui({ avail = { 1000, 700 } })
    local dn = draft(20, 2)
    setup(g2, 1, dn)
    S.sel = 2
    M.draw(); M.draw()
    local withNote = g2.sizes['##gsq-rules'][2]
    S.sel = 1
    M.draw(); M.draw()
    local plain = g2.sizes['##gsq-rules'][2]
    S.sel = 2
    M.draw()
    check(plain == withNote and g2.sizes['##gsq-rules'][2] == withNote, string.format(
          'selecting rules with a taller and a shorter editor does not move the list (%d / %d px)', withNote, plain))
    check(balanced(g) and balanced(g2), 'balanced')

    -- tooltips wrap at GetFontSize() * 27, popped, text unformatted; long texts and "%" included
    local gt = fakeGui({ hover = true, fontSize = 14, combos = { ['##gsq-kind'] = true, ['##gsq-target'] = true } })
    local dt = { num = 3, job = 'RDM', name = 'Tips', flags = 'o', rules = { rule('PARTY_LOWEST_HPP', 'HPP_LT', '40', nil, nil, 'family', 'CURE') } }
    setup(gt, 1, dt)
    M.draw()
    local tipPushes, allWidth = 0, true
    for _, w in ipairs(gt.wrapVals) do if w.tip then tipPushes = tipPushes + 1; allWidth = allWidth and w.v == 14 * 27 end end
    check(tipPushes > 10 and allWidth, string.format('every tooltip pushes a wrap width of GetFontSize() * 27 = 378 (%d tooltips)', tipPushes))
    check(hasTip(gt, M.KIND_HELP.burst) and hasTip(gt, M.TARGET_HELP.PARTY_LOWEST_HPP), 'the long Magic Burst help and the Lowest HP help (with "%") are shown')
    check(gt.formats == 0 and balanced(gt), 'no format call, every wrap and tooltip popped')
    local g20 = fakeGui({ hover = true, fontSize = 28 })
    setup(g20, 1, dt, 2)
    M.draw()
    local w20 = true
    for _, w in ipairs(g20.wrapVals) do if w.tip then w20 = w20 and w.v == 28 * 27 end end
    check(w20 and balanced(g20), 'at Size 200 % (font 28) the width follows: 756')
    local gnf = fakeGui({ hover = true })
    setup(gnf, 1, dt)
    M.draw()
    local wnf = true
    for _, w in ipairs(gnf.wrapVals) do if w.tip then wnf = wnf and w.v == 380 end end
    check(wnf and gnf.formats == 0, 'a binding without GetFontSize: 380 px (scaled)')
    local src = readAll(ADDON_DIR .. '/squad_editor.lua')
    local tb = src:match('local function tooltip%(text%)(.-)\nend')
    check(tb and tb:find('PushTextWrapPos(wrap)', 1, true) and tb:find('TextUnformatted', 1, true) and not tb:find('SetItemTooltip', 1, true)
          and select(2, tb:gsub('g%.SetTooltip%(', '')) == 1, 'tooltip(): PushTextWrapPos + TextUnformatted; SetTooltip only in the %%-escaped fallback')

    -- long notes wrap (narrow panel): the WS introduction, the 3000 TP help, the closed summary, the empty states
    local function wrappedHas(gg, part) for _, t in ipairs(gg.wrappedTexts) do if tostring(t):find(part, 1, true) then return true end end return false end
    local gw = fakeGui({ avail = { 700, 500 } })
    setup(gw, 1, dt)
    S.wsOpen = true
    S.ws.edit = { control = 1, mode = 1, tp = 1000, ws = 0 }
    M.draw()
    check(wrappedHas(gw, 'Separate from Rule Sets') and wrappedHas(gw, M.WS_3000_HELP), 'Weapon Skills open: the introduction and the 3000 TP help are wrapped')
    S.wsOpen = false
    gw.wrappedTexts = {}
    M.draw()
    check(wrappedHas(gw, 'Squad default (automatic skillchains'), 'Weapon Skills closed: the summary line is wrapped')
    local ge = fakeGui({ avail = { 700, 500 } })
    setup(ge, 1, nil)
    S.sets = {}
    M.draw()
    check(wrappedHas(ge, 'Click a Rule Set to open it') and wrappedHas(ge, 'Rule Sets yet. Press New or choose a Starter.'), 'the empty states are wrapped')
    S.ws.edit = { control = 0, mode = 1, tp = 1000, ws = 0 }
    gw.wrappedTexts = {}
    setup(gw, 1, dt)
    S.wsOpen = true
    S.ws.edit = { control = 1, mode = 3, tp = 1000, ws = 0 }
    M.draw()
    check(wrappedHas(gw, '(opening only: closing is allowed from 1000 TP)') and balanced(gw) and balanced(ge), 'Open + Close: its note wraps too; balanced')
    S.wsOpen = false

    -- "Unsaved weapon skill changes" only for real edits
    local legacy = { slot = 1, source = 'l', mode = 1, tp = 1000, ws = 0, engine = true, out = false, legacyTp = 0, legacyWs = 0 }
    S.ws = { slot = 1, data = legacy, edit = M.ws_edit_from(legacy) }
    check(not M.ws_edited() and M.ws_dirty() and not M.ws_summary(MATES[1]):find('Unsaved', 1, true)
          and M.ws_summary(MATES[1]):find('No Gambits setting yet', 1, true),
          'no Gambits WS setting yet (source l), nothing edited: no "Unsaved" in the summary; the panel still shows Save * (ws_dirty unchanged)')
    S.ws.edit.tp = 2000
    check(M.ws_edited() and M.ws_summary(MATES[1]):find('Unsaved weapon skill changes.', 1, true), 'TP changed: "Unsaved weapon skill changes."')
    S.ws.edit.tp = 1000
    check(not M.ws_edited() and not M.ws_summary(MATES[1]):find('Unsaved', 1, true), 'changed back to the stored value: not edited any more')
    local custom = { slot = 1, source = 'c', mode = 4, tp = 2000, ws = 18, engine = true, out = true, applied = true }
    S.ws = { slot = 1, data = custom, edit = M.ws_edit_from(custom) }
    check(not M.ws_edited() and not M.ws_dirty() and not M.ws_summary(MATES[1]):find('Unsaved', 1, true), 'a saved Custom setting, unedited: nothing unsaved')
    S.ws.edit.control = 0
    check(M.ws_edited() and M.ws_dirty(), 'switched to Squad default in the editor: edited (and Save *)')
end

-- ================================================================= JA. job-aware Job Ability lists
section('JA: job abilities by job and level (main, sub job, ratios, merits), Show all, saved rules, older servers, themes')
do
    -- the generated jas table is exactly the server's U13 table (squad_ja_jobs_data.lua), by xi.jobAbility names
    local jd = dofile(LUA_DIR .. '/squad_ja_jobs_data.lua')
    local hadJob = xi.job
    dofile(SERVER_ROOT .. '/scripts/enum/job.codegen.lua') -- (xi.job: the job names, as the generator reads them)
    local jobName = {}
    for k, v in pairs(xi.job) do jobName[v] = k end
    xi.job = hadJob
    local wrong, compared = {}, 0
    for name, id in pairs(xi.jobAbility) do
        local row, d = jd.abilities[id], DATA.jas[name]
        if row and id < 512 and id ~= 55 then
            compared = compared + 1
            if d == nil or d[2] ~= row[2] or (jobName[row[1]] and d[1] ~= jobName[row[1]]) or (d.sp == true) ~= (row.sp == true or row[2] == 0)
                or (d.main == true) ~= (row.main == true) or (d.merit == true) ~= (row.merit ~= nil) then
                wrong[#wrong + 1] = name
            end
        elseif d ~= nil then
            wrong[#wrong + 1] = name .. '(extra)'
        end
    end
    check(#wrong == 0 and compared > 300, string.format('gambits_data jas = the server\'s squad_ja_jobs_data.lua for %d abilities (job, level, two-hour, main only, merit): %s',
          compared, table.concat(wrong, ' ')))

    local rdm, lyra, rook, kit = MATES[1], MATES[2], MATES[4], MATES[6]
    check(not rdm.out and not lyra.out and not rook.out and #CAT[2].jas > 0 and #CAT[4].jas > 0,
          'unsummoned mates: the server\'s per-mate catalogs (catm) come from the squad data alone')
    -- main job: now / later (to 75) / merit / beyond 75 (Show all)
    local war = names(M.ja_view(CAT[4], rook, false, PLAN[4]))
    local warAll = names(M.ja_view(CAT[4], rook, true, PLAN[4]))
    check(war.PROVOKE and war.PROVOKE.state == 'now' and war.BERSERK.state == 'now' and war.DEFENDER.state == 'now'
          and war.MIGHTY_STRIKES and war.MIGHTY_STRIKES.state == 'now', 'WAR 30: Provoke, Berserk, Defender and Mighty Strikes (two-hour, main job) now')
    check(war.WARCRY and war.WARCRY.state == 'later' and war.WARCRY.label == 'Warcry  (Lv 35)' and war.AGGRESSOR.state == 'later'
          and war.RETALIATION and war.RETALIATION.state == 'later', 'WAR 30: Warcry "(Lv 35)", Aggressor, Retaliation later (dimmed, with the level)')
    check(war.WARRIORS_CHARGE and war.WARRIORS_CHARGE.state == 'merit' and war.WARRIORS_CHARGE.label == 'Warriors Charge  (Lv 75, merit)'
          and war.TOMAHAWK and war.TOMAHAWK.state == 'merit', 'merit abilities the owner has not unlocked: "(Lv 75, merit)" ' .. tostring(war.WARRIORS_CHARGE and war.WARRIORS_CHARGE.label))
    check(war.RESTRAINT == nil and war.BLOOD_RAGE == nil and warAll.BLOOD_RAGE and warAll.BLOOD_RAGE.state == 'beyond'
          and warAll.BLOOD_RAGE.label == 'Blood Rage  (Lv 87, above 75)', 'above level 75 (Restraint 77, Blood Rage 87): hidden, Show all marks "(Lv 87, above 75)"')
    -- sub job NIN 15 (cap 37): two-hour and main-only never from the sub job, the rest above the cap
    check(war.MIJIN_GAKURE == nil and war.YONIN == nil and war.INNIN == nil and war.FUTAE == nil, 'NIN sub: Mijin Gakure, Yonin, Innin, Futae hidden by default')
    check(warAll.MIJIN_GAKURE and warAll.MIJIN_GAKURE.state == 'mainonly' and warAll.MIJIN_GAKURE.label == 'Mijin Gakure  (sub, two-hour: main job only)'
          and warAll.YONIN.state == 'mainonly' and warAll.YONIN.label == 'Yonin  (sub, main job only)' and warAll.FUTAE.state == 'beyond'
          and warAll.FUTAE.label:find('(sub Lv 77, above the sub job cap)', 1, true), 'Show all marks them: "(sub, two-hour: main job only)", "(sub, main job only)", "(sub Lv 77, above the sub job cap)"')
    local otherJob = false
    for _, e in ipairs(M.ja_view(CAT[4], rook, true, PLAN[4])) do
        local info = M.ja_info(e.name)
        otherJob = otherJob or (info.job ~= nil and info.job ~= 'WAR' and info.job ~= 'NIN')
    end
    check(not otherJob, 'never another job\'s ability, even with Show all (no server catalog lists them for this mate)')
    -- RDM 28 / WHM 14: the sub job's abilities to its cap, later at their sub level
    local ly = names(M.ja_view(CAT[2], lyra, false, PLAN[2]))
    local lyAll = names(M.ja_view(CAT[2], lyra, true, PLAN[2]))
    check(ly.CHAINSPELL and ly.CHAINSPELL.state == 'now' and ly.CONVERT and ly.CONVERT.state == 'later' and ly.COMPOSURE and ly.COMPOSURE.state == 'later',
          'RDM 28: Chainspell now; Convert (40) and Composure (50, main only: fine as the main job) later')
    check(ly.DIVINE_SEAL and ly.DIVINE_SEAL.state == 'later' and ly.DIVINE_SEAL.sub and ly.DIVINE_SEAL.label == 'Divine Seal  (sub Lv 15)',
          'WHM 14 sub: Divine Seal later, "(sub Lv 15)"')
    check(ly.BENEDICTION == nil and ly.AFFLATUS_SOLACE == nil and ly.MARTYR == nil and lyAll.BENEDICTION.state == 'mainonly'
          and lyAll.AFFLATUS_SOLACE.state == 'mainonly' and lyAll.MARTYR.state == 'beyond', 'WHM sub: Benediction, Afflatus Solace hidden (main job only), Martyr above the cap; all marked with Show all')
    local mi = names(M.ja_view(CAT[1], rdm, true, PLAN[1]))
    check(mi.DIVINE_SEAL == nil and mi.PROVOKE == nil, 'RDM without a sub job: no WHM or WAR ability, even with Show all')
    local th = names(M.ja_view(CAT[6], kit, false, PLAN[6]))
    check(th.STEAL.state == 'now' and th.MUG.state == 'now' and th.HIDE.state == 'later' and th.FEINT.state == 'merit' and th.DESPOIL == nil,
          'THF 40: Steal, Mug now; Hide later; Feint merit; Despoil (77) hidden')
    -- the order: now, then not confirmed, then later / merit by level, then the rest
    local order, rankOk, last = M.ja_view(CAT[4], rook, true, PLAN[4]), true, 0
    local rank = { now = 1, unconfirmed = 2, later = 3, merit = 3, beyond = 4, mainonly = 4 }
    for _, e in ipairs(order) do rankOk = rankOk and rank[e.state] >= last; last = rank[e.state] end
    check(rankOk, 'sorted: usable now first, then later and merit by level, then what may never work')

    -- subjob ratios (map.SUBJOB_RATIO via the server's own levelsFor): WAR 30 with WHM at its own level 30
    SQUAD[#SQUAD + 1] = { slot = 7, id = 107, name = 'Ria', mjob = JOB.WAR, sjob = JOB.WHM, jobs = { [JOB.WAR] = { level = 30 }, [JOB.WHM] = { level = 30 } } }
    local ratioSeen = {}
    for _, ratio in ipairs({ 0, 1, 2, 3 }) do
        xi.settings.map = { SUBJOB_RATIO = ratio }
        local ok, main, sub, sl = G.levels(SQUAD[#SQUAD], srv)
        local m = { slot = 7, name = 'Ria', job = 'WAR', level = main, sub = (ok and sub ~= 0) and 'WHM' or nil, subLevel = (ok and sub ~= 0) and sl or nil, out = false }
        local c, p = catm(7), plan('WAR', m.sub)
        local v, all = names(M.ja_view(c, m, false, p)), names(M.ja_view(c, m, true, p))
        ratioSeen[ratio] = { m = m, v = v, all = all }
    end
    xi.settings.map = nil
    table.remove(SQUAD)
    local r0, r1, r2, r3 = ratioSeen[0], ratioSeen[1], ratioSeen[2], ratioSeen[3]
    check(r0.m.sub == nil and r0.all.DIVINE_SEAL == nil and r0.all.BENEDICTION == nil, 'ratio 0 (no support job): no WHM ability at all, even with Show all')
    check(r1.m.subLevel == 15 and M.sub_cap(r1.m) == 37 and r1.v.DIVINE_SEAL and r1.v.DIVINE_SEAL.state == 'now' and r1.v.AFFLATUS_SOLACE == nil
          and r1.all.MARTYR.state == 'beyond', 'ratio 1 (half): sub 15, cap 37: Divine Seal now, Afflatus Solace hidden, Martyr above the cap')
    check(r2.m.subLevel == 20 and M.sub_cap(r2.m) == 50 and r2.v.DIVINE_SEAL.state == 'now' and r2.v.AFFLATUS_SOLACE == nil
          and r2.all.AFFLATUS_SOLACE.state == 'mainonly', 'ratio 2 (two thirds): sub 20, cap 50: Afflatus Solace (40) still hidden - main job only, not a level matter')
    check(r3.m.subLevel == 30 and M.sub_cap(r3.m) == 75 and r3.v.MARTYR and r3.v.MARTYR.state == 'merit' and r3.v.MARTYR.label == 'Martyr  (sub Lv 75, merit)'
          and r3.v.BENEDICTION == nil, 'ratio 3 (equal): cap 75: Martyr shown "(sub Lv 75, merit)"; Benediction still main job only')

    -- a merit the owner HAS unlocked: the server's catalog offers it, so it is usable now
    SQUAD[#SQUAD + 1] = { slot = 8, id = 108, name = 'Tor', mjob = JOB.WAR, sjob = 0, jobs = { [JOB.WAR] = { level = 75 } } }
    local tor = { slot = 8, name = 'Tor', job = 'WAR', level = 75, out = false }
    local merit0 = names(M.ja_view(catm(8), tor, false, plan('WAR')))
    SquadOwnerMerit = function() return 1 end
    local merit1 = names(M.ja_view(catm(8), tor, false, plan('WAR')))
    SquadOwnerMerit = function() return 0 end
    table.remove(SQUAD)
    check(merit0.WARRIORS_CHARGE.state == 'merit' and M.ja_tip(merit0.WARRIORS_CHARGE, tor):find('unlocked its merit.', 1, true)
          and merit1.WARRIORS_CHARGE.state == 'now' and M.ja_tip(merit1.WARRIORS_CHARGE, tor):find('its merit is unlocked', 1, true),
          'WAR 75: Warrior\'s Charge "merit" until the owner unlocks it, then usable now (the server\'s catalog decides)')

    -- tooltips: job and level, why, and that recast / status are decided in combat
    local tipNow = M.ja_tip(war.PROVOKE, rook)
    check(tipNow:find('Provoke: WAR level 5.', 1, true) and tipNow:find('can use it by job and level now', 1, true)
          and tipNow:find('Recast, status and other conditions are checked in combat', 1, true), 'a usable ability: its level; recast and status are combat matters')
    check(M.ja_tip(war.WARCRY, rook):find('Learned later (WAR level 35)', 1, true) and M.ja_tip(ly.DIVINE_SEAL, lyra):find('sub job WHM level 15', 1, true)
          and M.ja_tip(lyAll.BENEDICTION, lyra):find('A two-hour ability only works as the main job, never from the sub job (WHM)', 1, true)
          and M.ja_tip(lyAll.MARTYR, lyra):find('Above what a sub job reaches (WHM up to level 37)', 1, true)
          and M.ja_tip(warAll.BLOOD_RAGE, rook):find('above level 75', 1, true), 'tooltips for later, sub job, two-hour, above the sub job cap, above 75')
    check(M.entry_tip('ja', war.WARCRY, rook) == M.ja_tip(war.WARCRY, rook) and M.entry_tip('ja', { name = 'PROVOKE', level = 5 }, rook):find('WAR level 5', 1, true),
          'entry_tip uses the job ability tooltip (and the plain one for an entry without a state)')

    -- saved rules: kept exactly, marked, with notes
    local rules = {
        { rule('TARGET', 'ALWAYS', nil, nil, nil, 'ja', 'PROVOKE'), CAT[1], rdm, PLAN[1] },          -- another job's
        { rule('SELF', 'ALWAYS', nil, nil, nil, 'ja', 'CONVERT'), CAT[2], lyra, PLAN[2] },           -- later
        { rule('SELF', 'ALWAYS', nil, nil, nil, 'ja', 'AFFLATUS_SOLACE'), CAT[2], lyra, PLAN[2] },   -- sub, main only
        { rule('SELF', 'ALWAYS', nil, nil, nil, 'ja', 'BLOOD_RAGE'), CAT[4], rook, PLAN[4] },        -- above 75
        { rule('SELF', 'ALWAYS', nil, nil, nil, 'ja', 'WARRIORS_CHARGE'), CAT[4], rook, PLAN[4] },   -- merit
        { rule('SELF', 'ALWAYS', nil, nil, nil, 'ja', 'MIJIN_GAKURE'), CAT[4], rook, PLAN[4] },      -- sub two-hour
        { rule('SELF', 'ALWAYS', nil, nil, nil, 'ja', 'DEFENDER'), CAT[4], rook, PLAN[4] },          -- usable now
    }
    local before = {}
    for i, c in ipairs(rules) do before[i] = M.encode_rule(c[1]) end
    local function note(i) return M.action_note(rules[i][1], rules[i][2], rules[i][3], rules[i][4]) or '' end
    check(note(1):find('Provoke is a WAR job ability, not one of Mira\'s jobs', 1, true) and note(1):find('kept as saved', 1, true), 'Provoke for an RDM: "a WAR job ability ... kept as saved"')
    check(note(2):find('Lyra learns Convert at level 40', 1, true), 'Convert: "Lyra learns Convert at level 40: this rule starts working then"')
    check(note(3):find('works only as the main job, never from Lyra\'s sub job', 1, true), 'Afflatus Solace from the WHM sub job: main job only')
    check(note(4):find('at level 87, above level 75', 1, true) and note(5):find('merit ability', 1, true)
          and note(6):find('two-hour ability', 1, true) and note(7) == '', 'Blood Rage above 75, Warrior\'s Charge merit, Mijin Gakure two-hour; no note for Defender')
    local saved = M.ja_saved_entry('PROVOKE', CAT[1], rdm, PLAN[1])
    check(saved.state == 'other' and saved.label == 'Provoke  (WAR, not RDM)', 'a saved ability of another job is listed marked: ' .. tostring(saved.label))
    local savedHidden = M.ja_saved_entry('YONIN', CAT[4], rook, PLAN[4])
    check(savedHidden.state == 'mainonly' and savedHidden.label == 'Yonin  (sub, main job only)', 'a saved ability hidden by default keeps its own mark')
    -- one of its jobs, but not in the server's list (e.g. its expansion switched off): "not on this server"
    local planNo = { jas = {} }
    for _, j in ipairs(PLAN[2].jas) do if j.name ~= 'CONVERT' then planNo.jas[#planNo.jas + 1] = j end end
    local missing = M.ja_saved_entry('CONVERT', CAT[2], lyra, planNo)
    check(missing.state == 'missing' and missing.label == 'Convert  (not on this server)'
          and M.action_note(rules[2][1], CAT[2], lyra, planNo):find('not in this server\'s ability list', 1, true), 'an own-job ability the server does not list: "(not on this server)", note')
    local after = {}
    for i, c in ipairs(rules) do after[i] = M.encode_rule(c[1]) end
    check(table.concat(before, '|') == table.concat(after, '|') and before[1] == '1,TARGET,ALWAYS,,,,j,PROVOKE,', 'the views and notes change no rule; the wire is as before')

    -- older servers, loading, failed, no catalog, no data: the fallbacks
    local old = { perMate = false, families = CAT[2].families, spells = PLAN[2].spells, jas = PLAN[2].jas, targets = CAT[2].targets }
    local ov = names(M.ja_view(old, lyra, false))
    check(ov.CHAINSPELL.state == 'now' and ov.DIVINE_SEAL.state == 'now' and ov.CONVERT.state == 'later' and ov.BENEDICTION == nil,
          'older server (job catalog, no sub level): main to its level now, the sub job up to the main level now (the server decides), later marked, main-only hidden')
    check(M.action_note({ kind = 'ja', name = 'DIVINE_SEAL' }, old, lyra):find('uses this with its sub job', 1, true), 'older server: the sub job note of before')
    local nowCount = #M.ja_choices(CAT[2], lyra)
    S.plan = { key = M.plan_key(lyra), loading = true }
    local loading = M.ja_view(CAT[2], lyra, false)
    local allNow = #loading == nowCount
    for _, e in ipairs(loading) do allNow = allNow and e.state == 'now' end
    S.plan = { key = M.plan_key(lyra), error = 'timeout' }
    local failedView = M.ja_view(CAT[2], lyra, true)
    check(allNow and #failedView == nowCount, string.format('job list loading or failed: exactly the server\'s per-mate list, unmarked (%d)', nowCount))
    S.plan = nil
    check(#M.ja_view(nil, lyra, true) == 0 and M.ja_saved_entry('PROVOKE', nil, lyra).state == 'unknown'
          and M.action_note({ kind = 'ja', name = 'PROVOKE' }, nil, lyra):find('not in Lyra\'s job abilities now', 1, true),
          'no catalog at all: an empty list, a saved name unknown, the note of before')
    local noMate = M.ja_view(CAT[2], nil, false, PLAN[2])
    check(#noMate == nowCount, 'no mate selected: the catalog as it is')
    M.set_data(nil)
    local nd = names(M.ja_view(CAT[4], rook, true, PLAN[4]))
    check(nd.MIJIN_GAKURE.state == 'mainonly' and nd.YONIN.state == 'beyond' and nd.WARRIORS_CHARGE.state == 'later' and nd.PROVOKE.state == 'now',
          'without gambits_data.lua: level 0 is still two-hour (the server\'s rule); nothing else is guessed')
    M.set_data(DATA)

    -- the editor: the Job Ability dropdown with Show all off / on, the saved name, the cooldown condition, three themes
    local function jaDraft(name, cond, arg)
        return { num = 3, job = 'WAR', name = 'Tank 30', flags = 'o', rules = { rule('TARGET', cond or 'ALWAYS', arg, nil, nil, 'ja', name) } }
    end
    for _, theme in ipairs({ 'classic', 'squad', 'crimson' }) do
        local g = fakeGui({ hover = true, combos = { ['##gsq-name'] = true, ['##gsq-ja1'] = true } })
        local pushes = 0
        local push = g.PushStyleColor
        g.PushStyleColor = function(...) pushes = pushes + 1; return push(...) end
        local d = jaDraft('BLOOD_RAGE', 'JA_ON_COOLDOWN', 'PROVOKE')
        setup(g, 4, d)
        M.set_theme(theme)
        S.showAll = false
        local ok, err = pcall(M.draw)
        check(ok, theme .. ': draws with the Job Ability and cooldown dropdowns open: ' .. tostring(err))
        check(hasLabel(g, 'Warcry  (Lv 35)') and hasLabel(g, 'Warriors Charge  (Lv 75, merit)') and not hasLabel(g, 'Yonin')
              and hasLabel(g, 'Show all##gsq-showall'), theme .. ': later and merit entries listed, sub main-only hidden; Show all next to Job Ability')
        check(logHas(g, 'combo ##gsq-name = Blood Rage  (Lv 87, above 75)') and d.rules[1].name == 'BLOOD_RAGE',
              theme .. ': a saved ability hidden by default stays selected, marked')
        check(hasTip(g, 'Recast, status and other conditions are checked in combat') and hasTip(g, 'Job abilities: On adds'),
              theme .. ': entry tooltips and the Show all help')
        local st = M.state_colors()
        check(st.later == M.theme.secondary and st.merit == M.theme.secondary and st.mainonly == M.theme.muted and st.other == M.theme.muted and pushes > 0,
              theme .. ': later / merit dimmed, never-usable muted, in the theme\'s own colours')
        g.clicks['Show all##gsq-showall'] = true
        M.draw()
        g.labels = {}
        M.draw()
        check(S.showAll == true and prefs.show_all == true and hasLabel(g, 'Yonin  (sub, main job only)') and hasLabel(g, 'Mijin Gakure  (sub, two-hour: main job only)'),
              theme .. ': Show all (the same setting as for spells) adds the marked sub job abilities')
        check(g.formats == 0 and balanced(g) and M.encode_rule(d.rules[1]) == '1,TARGET,JA_ON_COOLDOWN,PROVOKE,,,j,BLOOD_RAGE,', theme .. ': no format call, balanced, the rule unchanged')
        S.showAll = false
        prefs.show_all = nil
    end
    M.set_theme('classic')
    -- the cooldown condition's saved ability of another job: kept, marked
    local gc = fakeGui({ combos = { ['##gsq-ja1'] = true } })
    local dc = { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = { rule('SELF', 'JA_ON_COOLDOWN', 'PROVOKE', nil, nil, 'ja', 'CHAINSPELL') } }
    setup(gc, 1, dc)
    M.draw()
    check(logHas(gc, 'combo ##gsq-ja1 = Provoke  (WAR, not RDM)') and dc.rules[1].arg == 'PROVOKE' and logHas(gc, 'combo ##gsq-name = Chainspell'),
          'JA_ON_COOLDOWN with another job\'s saved ability: kept, "(WAR, not RDM)"')
    -- "%" in names and tooltips: drawn as text, never a format
    local gp = fakeGui({ hover = true, combos = { ['##gsq-name'] = true } })
    local saveName = MATES[4].name
    MATES[4].name = '100%d %s Rook'
    setup(gp, 4, jaDraft('WARCRY'))
    local okp, errp = pcall(M.draw)
    MATES[4].name = saveName
    check(okp and gp.formats == 0 and hasTip(gp, '100%d %s Rook') and balanced(gp), 'a mate name with "%d %s": tooltips show it exactly, no format call: ' .. tostring(errp))
end

-- ================================================================= 0.3.2: the Party roles section (!gsq v7 prl / prs)
section('0.3.2 Party roles: server-confirmed only, Auto with several targets, the whole party in the summary, the Aldric case')
do
    -- the real server module answers: the editor's line goes out through the real transport, gambits_squad.lua answers
    package.preload['modules/custom/lua/squad_jobs'] = function() return dofile(LUA_DIR .. '/squad_jobs.lua') end
    local cv, lv = {}, {}
    srv.getCharVar = function(_, k) return cv[k] or 0 end
    srv.setCharVar = function(_, k, v) cv[k] = (v ~= 0) and v or nil end
    srv.getLocalVar = function(_, k) return lv[k] or 0 end
    srv.setLocalVar = function(_, k, v) lv[k] = v end
    srv.getMainJob = function() return 3 end
    srv.getMainLvl = function() return 30 end
    srv.getName = function() return 'Testcharone' end
    local function member(o)
        local e = { vars = { SQUAD_ID = o.squadId or 0, SQUAD_ROLE = o.role or 0 } }
        function e:getID() return o.id end
        function e:getObjType() return o.pc and xi.objType.PC or xi.objType.TRUST end
        function e:getMainJob() return o.job end
        function e:getMainLvl() return o.lvl or 30 end
        function e:getSubJob() return 0 end
        function e:getSubLvl() return 0 end
        function e:getMaster() return o.master end
        function e:getName() return o.name end
        function e:getPacketName() return o.name end
        function e:getLocalVar(k) return self.vars[k] or 0 end
        function e:setLocalVar(k, v) self.vars[k] = v end
        return e
    end
    -- the squad for this section: Aldric WAR 20 (out), Lyra WHM 30 (out, the healer), Hild PLD 30 (not summoned)
    local savedSquad = {}
    for i, m in ipairs(SQUAD) do savedSquad[i] = m end
    for i = #SQUAD, 1, -1 do SQUAD[i] = nil end
    SQUAD[1] = { slot = 7, id = 107, name = 'Aldric', mjob = JOB.WAR, sjob = 0, jobs = { [JOB.WAR] = { level = 20 } } }
    SQUAD[2] = { slot = 8, id = 108, name = 'Lyra', mjob = JOB.WHM, sjob = 0, jobs = { [JOB.WHM] = { level = 30 } } }
    SQUAD[3] = { slot = 9, id = 109, name = 'Hild', mjob = JOB.PLD, sjob = 0, jobs = { [JOB.PLD] = { level = 30 } } }
    local aldric = member({ id = 6001, squadId = 107, job = JOB.WAR, lvl = 20, master = srv, name = 'Aldric' })
    local lyra = member({ id = 6002, squadId = 108, job = JOB.WHM, master = srv, name = 'Lyra' })
    local dual = member({ id = 2, pc = true, job = JOB.PLD, name = 'Dualpld' })
    local partyNow = { srv, aldric, lyra }
    srv.getPartyWithTrusts = function() return partyNow end

    local drop, sentLog = false, {}
    local function serve(rounds)
        for _ = 1, rounds or 40 do
            clock = clock + 0.3
            M.tick()
            local pending = sent
            sent = {}
            for _, l in ipairs(pending) do
                sentLog[#sentLog + 1] = l
                local body = l:match('^/say !gsq (.*)$')
                if body then
                    M.text_in('Testcharone : !gsq ' .. body, 'Testcharone : !gsq ' .. body)
                    if not drop then
                        srv.printed = {}
                        G.handle(srv, body)
                        for _, ans in ipairs(srv.printed) do M.text_in(ans, ans) end
                    end
                end
            end

            if not M.busy() and #sent == 0 then
                break
            end
        end
    end
    local function sentCount(verb)
        local c = 0
        for _, l in ipairs(sentLog) do if l:find('^/say !gsq ' .. verb .. ' ') then c = c + 1 end end
        for _, l in ipairs(sent) do if l:find('^/say !gsq ' .. verb .. ' ') then c = c + 1 end end
        return c
    end
    local function fresh(opts, version)
        local g = fakeGui(opts)
        setup(g, 1, { num = 3, job = 'WHM', name = 'Healer', flags = 'o', rules = { rule('TANK', 'NOT_STATUS', 'REGEN', nil, nil, 'family', 'REGEN') } })
        S.server.version = version or 7
        S.roles, S.rolesGen = nil, 0
        sent, sentLog = {}, {}
        return g
    end

    -- K1: an older server: one update line, no dropdowns, no request
    local g1 = fresh({}, 6)
    S.rolesOpen = true
    M.draw(); M.draw()
    check(sentCount('prl') == 0 and hasText(g1, 'Party roles need the server update') and not logHas(g1, 'combo ##gsq-role-'),
          'K1 server version 6: the update line only; no dropdowns, no prl')
    check(not M.roles_set(7, 1) and sentCount('prs') == 0, 'K1 and roles_set does nothing (no prs sent)')
    -- K2: closed sends nothing; opening sends exactly one prl
    local g2 = fresh({}, 7)
    S.rolesOpen = false
    M.draw(); M.draw()
    check(sentCount('prl') == 0 and hasText(g2, 'Open this section to see who counts as'), 'K2 closed: nothing sent; the summary says to open it')
    S.rolesOpen = true
    M.draw(); M.draw()
    clock = clock + 0.3
    M.tick() -- (the transport sends on its tick)
    M.draw()
    check(sentCount('prl') == 1, 'K2 opened: exactly one prl (also after more frames while it is loading)')
    serve()
    M.draw()
    check(S.roles and S.roles.rows and #S.roles.rows == 4 and S.roles.byWho[0].name == 'Testcharone' and sentCount('prl') == 1,
          'K2 the answer: you + 3 mates; still one prl after the answer')
    -- K3 / K11: the rows; Auto shows every target of the job
    local g3 = fresh({ combos = { ['##gsq-role-7'] = true, ['##gsq-role-9'] = true }, hover = true }, 7)
    S.rolesOpen = true
    M.draw(); serve(); M.draw()
    check(logHas(g3, 'combo ##gsq-role-7 = Auto (Melee)') and logHas(g3, 'combo ##gsq-role-9 = Auto (Tank, Melee)'),
          'K3 Aldric WAR: "Auto (Melee)"; Hild PLD: "Auto (Tank, Melee)" (Auto can be more than one target)')
    check(hasText(g3, 'Hild') and hasText(g3, 'PLD 30  (not summoned)') and hasText(g3, 'applies when called') and hasText(g3, 'in effect'),
          'K3 a mate not out is marked "(not summoned)" / "applies when called"; the mates out "in effect"')
    check(hasTip(g3, 'Some jobs count for more than one target') and hasTip(g3, 'counts as Tank only, whatever its job: no longer Melee'),
          'K3 tooltips: Auto can mean several targets; an explicit role replaces the job ("no longer Melee")')
    check(M.roles_summary(S.roles):find('Tank: nobody', 1, true) and M.roles_summary(S.roles):find('Not summoned: Hild (Tank, Melee)', 1, true),
          'K11 the Aldric case before: "Tank: nobody" in the party now; Hild (not out) is listed apart, not counted')
    -- K4 / K11: choose Tank for Aldric: nothing changes before the answer; then the server's row
    local before = M.encode_rule(S.draft.rules[1])
    g3.picks['##gsq-role-7'] = 'Tank'
    M.draw()
    local pend = S.roles.byWho[7]
    check(pend.set == 0 and pend.pending ~= nil and pend.pending.role == 1, 'K4 picking Tank: the row still has the server value (Auto) and is pending; nothing confirmed yet')
    g3.log = {}
    M.draw()
    check(logHas(g3, 'combo ##gsq-role-7 = Auto (Melee)') and logHas(g3, 'disabled') and hasText(g3, 'saving...'),
          'K4 while pending: the dropdown still shows the server value, disabled, "saving..."')
    serve()
    local row = S.roles.byWho[7]
    check(sentCount('prs') == 1 and sentLog[#sentLog]:find('prs %d+ 7 1') and row.set == 1 and row.live == 1 and row.out and row.pending == nil,
          'K4 the server answer: Aldric tank, stored and live (one prs 7 1)')
    check(cv.SQUAD_PROLE_107 == 1 and aldric:getLocalVar('SQUAD_ROLE') == 1, 'K11 on the server: stored AND live on Aldric at once (no recall)')
    check(S.message:find('Aldric: Tank (server confirmed), in effect now.', 1, true), 'K4 the message comes from the answer: ' .. tostring(S.message))
    check(M.roles_summary(S.roles):find('Tank: Aldric (set)', 1, true) and not M.roles_summary(S.roles):find('Melee: Aldric', 1, true),
          'K11 after: "Tank: Aldric (set)", and Aldric no longer counts as Melee')
    check(M.encode_rule(S.draft.rules[1]) == before, 'K11 the healer\'s "Tank -> missing Regen -> Regen" rule is unchanged')
    -- K6: back to Auto for a summoned mate
    M.roles_set(7, 0)
    serve()
    row = S.roles.byWho[7]
    check(row.set == 0 and row.live == 0 and cv.SQUAD_PROLE_107 == nil and aldric:getLocalVar('SQUAD_ROLE') == 0
          and M.roles_summary(S.roles):find('Tank: nobody', 1, true), 'K6 Auto again: stored cleared, live 0 at once; "Tank: nobody" again')
    -- K5: a refused change and a lost answer: the old row stays, no success text
    local keepSquad = SQUAD[1]
    SQUAD[1] = nil
    SQUAD[1], SQUAD[2], SQUAD[3] = SQUAD[2], SQUAD[3], nil
    M.roles_set(7, 2)
    serve()
    row = S.roles.byWho[7]
    check(row.set == 0 and row.pending == nil and S.message:find('Party role NOT changed', 1, true) and not S.message:find('confirmed', 1, true),
          'K5 refused by the server (no such slot in your squad): the old row stays, "NOT changed", no success text')
    SQUAD[3], SQUAD[2], SQUAD[1] = SQUAD[2], SQUAD[1], keepSquad
    drop = true
    M.roles_set(7, 4)
    serve(400)
    drop = false
    row = S.roles.byWho[7]
    check(row.set == 0 and row.pending == nil and S.message:find('NOT changed', 1, true), 'K5 no answer at all (timeout): the old row stays, "NOT changed": ' .. tostring(S.message))
    -- out of order: an older list answer never overwrites a newer confirmed change; a change answer for an old row is ignored
    M.roles_load()
    local genAtLoad = S.rolesGen
    S.rolesGen = S.rolesGen + 1 -- (what a confirmed change does meanwhile)
    local rolesBefore = S.roles
    serve()
    check(S.roles == rolesBefore and S.roles.loading == nil and genAtLoad < S.rolesGen, 'an older prl answer is not used (a newer change came since)')
    M.roles_set(7, 3)
    S.roles.byWho[7].pending.token = {} -- (the list was reloaded meanwhile: the pending change belongs to an older row)
    serve()
    check(S.roles.byWho[7].set == 0, 'a prs answer for an older row does not overwrite the newer list')
    S.roles.byWho[7].pending = nil
    -- K7: the summary includes members the UI cannot edit (a dualbox PLD), so it never says "Tank: nobody" wrongly
    partyNow[#partyNow + 1] = dual
    S.roles = nil
    M.roles_load(); serve()
    local sum = M.roles_summary(S.roles)
    check(sum:find('Tank: Dualpld', 1, true) and not sum:find('Tank: nobody', 1, true) and sum:find('Includes 1 member of other characters', 1, true),
          'K7 a dualbox PLD in the party: "Tank: Dualpld", not "nobody"; the summary says it includes another character: ' .. sum)
    local g7 = fresh({}, 7)
    S.rolesOpen = true
    M.draw(); serve(); M.draw()
    check(hasText(g7, 'Other party members (set on their own character)') and hasText(g7, 'Dualpld  PLD  Tank, Melee') and not logHas(g7, 'combo ##gsq-role-Dualpld'),
          'K7 the open section lists the dualbox character read-only (no dropdown)')
    table.remove(partyNow)
    S.roles.stale = true
    check(M.roles_summary(S.roles):find('Open this section to update', 1, true) and not M.roles_summary(S.roles):find('Tank:', 1, true),
          'K7 after the squad changed: the summary asks to update, it shows no old counts')
    S.roles = { error = 'timeout' }
    check(M.roles_summary(S.roles):find('could not be loaded (timeout)', 1, true), 'K7 a failed load: the summary says so, no counts')
    -- a reload that fails while an older list is shown: tried once (no retry every frame), no old counts in the summary
    local g12 = fresh({}, 7)
    S.rolesOpen = true
    M.draw(); serve(); M.draw()
    S.roles.stale = true
    drop = true
    for _ = 1, 30 do M.draw(); clock = clock + 0.3; M.tick() end
    serve(400)
    for _ = 1, 30 do M.draw(); clock = clock + 0.3; M.tick() end
    drop = false
    local s12 = M.roles_summary(S.roles)
    check(sentCount('prl') <= 4 and S.roles.error ~= nil and S.roles.rows ~= nil and s12:find('could not be loaded', 1, true)
          and not s12:find('Tank:', 1, true) and hasText(g12, 'The last update failed'),
          string.format('K7 a failed reload: one request (resent by the transport at most, %d lines), no retry loop, the summary shows no old counts', sentCount('prl')))
    sent = {}
    local before12 = sentCount('prl')
    for _ = 1, 20 do M.draw(); clock = clock + 0.3; M.tick() end
    check(sentCount('prl') == before12, 'K7 after the failure: no new automatic prl')
    serve()
    -- K8: the open state is remembered (pref whitelist), and the rule list makes room for it
    local g8 = fresh({ collapsing = true }, 7)
    S.rolesOpen = false
    prefs.roles_open = nil
    g8.clicks.header = true
    M.roles_section()
    check(S.rolesOpen == true and prefs.roles_open == true, 'K8 clicking the header opens it and remembers roles_open')
    local gs = readAll(ADDON_DIR .. '/Gambits.lua')
    check(gs:find('roles_open = true }', 1, true) and gs:find("s.roles_open = s.roles_open == true", 1, true) and gs:find("addon.version = '0.4.0'", 1, true),
          'K8 Gambits.lua: roles_open whitelisted and cleaned; version 0.4.0')
    serve()
    -- K9: themes and sizes, open with every dropdown and tooltip, narrow window: balanced, no format calls
    for _, case in ipairs({ { 'classic', 1, { 1000, 560 } }, { 'squad', 0.7, { 700, 400 } }, { 'crimson', 2, { 1060, 580 } } }) do
        local g = fakeGui({ avail = case[3], hover = true, combos = { ['##gsq-role-0'] = true, ['##gsq-role-7'] = true } })
        setup(g, 1, { num = 3, job = 'WHM', name = 'Healer', flags = 'o', rules = { rule('TANK', 'NOT_STATUS', 'REGEN', nil, nil, 'family', 'REGEN') } }, case[2])
        S.server.version = 7
        M.set_theme(case[1])
        S.rolesOpen = true
        S.roles = nil
        M.draw(); serve(); M.draw(); M.draw()
        check(balanced(g) and g.formats == 0 and logHas(g, 'combo ##gsq-role-0 = Auto (Mage)'),
              string.format('K9 %s at %d %%, %dx%d: the section draws balanced, 0 format calls, your row "Auto (Mage)"', case[1], case[2] * 100, case[3][1], case[3][2]))
    end
    M.set_theme('classic')
    -- K10: the answers are checked strictly
    local function f(...) return { 'GSQ', '1', ... } end
    check(M.parse_roles({ f('pr', '0', 'You', 'WHM', '30', '0', 'C', '1', '0') }) ~= nil, 'K10 a good pr line is read')
    check(M.parse_roles({ f('pr', '0', 'You', 'WHM', '30', '0', 'X', '1', '0') }) == nil, 'K10 a bad target letter is refused')
    check(M.parse_roles({ f('pr', '0', 'You', 'WHM', '30', '9', 'C', '1', '0') }) == nil, 'K10 a role out of range is refused')
    check(M.parse_roles({ f('pr', '0', 'You', 'WHM', '30', '0', 'C', '1', '0'), f('pr', '0', 'You', 'WHM', '30', '0', 'C', '1', '0') }) == nil,
          'K10 the same who twice is refused')
    check(M.parse_roles({ f('pr', '0', 'You', 'WHM', '30', '0', 'C', '1') }) == nil and M.parse_roles({ f('pm', 'X', 'PLD', 'q', 'TM') }) == nil
          and M.parse_roles({ f('mate', '1') }) == nil, 'K10 a short line, a bad member kind or a foreign line is refused')
    -- restore
    for i = #SQUAD, 1, -1 do SQUAD[i] = nil end
    for i, m in ipairs(savedSquad) do SQUAD[i] = m end
    S.roles, S.rolesOpen = nil, false
end

-- ================================================================= P. (0.3.5) one look with the Squads menu and the Profile
section('P (0.3.5): mate row, divider, row states, status area (Editing / runs), rule controls, value widths')
do
    local U2 = M.UI
    -- ---- the states are made from the palette, in every theme; no palette value is touched
    for _, name in ipairs(M.THEME_ORDER) do
        local c = M.THEMES[name]
        local before = string.format('%.3f %.3f %.3f|%.3f %.3f %.3f|%.3f %.3f %.3f', c.tabSel[1], c.tabSel[2], c.tabSel[3], c.rowSel[1], c.rowSel[2], c.rowSel[3], c.ok[1], c.ok[2], c.ok[3])
        local st = U2.states(c)
        local after = string.format('%.3f %.3f %.3f|%.3f %.3f %.3f|%.3f %.3f %.3f', c.tabSel[1], c.tabSel[2], c.tabSel[3], c.rowSel[1], c.rowSel[2], c.rowSel[3], c.ok[1], c.ok[2], c.ok[3])
        check(before == after and st.tab == c.tabSel and st.active == c.ok and st.warn == c.warn and st.muted == c.muted
            and st.rowFill[1] == c.rowSel[1] and st.rowFill[4] < 0.5 and st.rowLine[1] >= c.tabSel[1] and U2.states(c) == st,
              name .. ': selected tab = tabSel, selected row = a light tint of rowSel with a brighter line, active = ok, warning = warn; the palette is untouched')
    end

    -- ---- the divider's place
    local function draft(nRules)
        local rules = {}
        for i = 1, nRules do rules[i] = rule('PARTY', 'HPP_LT', tostring(10 + i), nil, nil, 'family', 'CURE') end
        return { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = rules, dirty = false }
    end
    setup(fakeGui({ avail = { 1064, 560 } }), 1, draft(3))
    local w, lo, hi, bar
    S.leftW = nil
    w, lo, hi, bar = M.split_width(1064)
    check(w == 287 and lo == 200 and hi == 1064 - 420 - bar and bar == 6, 'a 1064 px body: the Rule Set column is 287 px (27 %; 0.3.4: 383), between 200 and what leaves the editor 420')
    check(M.split_width(704) == 220 and M.split_width(2000) == 300, 'the narrowest window (704 px body): 220 px; a very wide one: 300 px, the rest is the editor\'s')
    S.leftW = 900
    check(M.split_width(1064) == 1064 - 420 - 6, 'dragged too far right: stops where the editor still has 420 px')
    S.leftW = 20
    check(M.split_width(1064) == 200, 'dragged too far left: stops at 200 px')
    S.leftW = 260
    setup(fakeGui({ avail = { 2128, 560 } }), 1, draft(3), 2)
    check(M.split_width(2128) == 520, 'the place is kept at 100 %: at 200 % it is twice as wide (260 -> 520)')
    S.leftW = nil

    -- ---- what a set is to the mate, and what the mate runs: the server's word only
    local function mate(over) local m = { slot = 1, name = 'Mira', job = 'RDM', level = 28, chosen = 3, out = true } for k, v in pairs(over or {}) do m[k] = v end return m end
    local function live(state, num, dropped) return { state = state, num = num or 0, why = '-', fb = 0, dropped = dropped or 0 } end
    local g = fakeGui({ avail = { 1064, 560 } })
    local d = draft(3)
    setup(g, 1, d)
    local st = U2.states(M.theme)
    S.server.caps = { live = true }
    S.liveUnsure, S.liveFailed = nil, nil
    local mark, tone = M.set_mark(3, mate({ live = live('set', 3) }))
    check(mark == 'active' and tone == st.active, 'the server reports that the mate runs the set: "active", green')
    mark, tone = M.set_mark(3, mate({ live = live('job') }))
    check(mark == 'Apply needed' and tone == st.warn, 'chosen, the mate is out and runs something else: "Apply needed", the warning colour (never "active")')
    check(M.set_mark(3, mate({ out = false, live = live('off') })) == 'next call', 'chosen, the mate is not called: "next call"')
    check(M.set_mark(5, mate({ live = live('set', 3) })) == nil and M.set_mark(5, mate({ live = live('pending', 5) })) == 'still running',
          'another set: no mark; one the mate still runs from its last call although another is chosen: "still running"')
    S.liveUnsure = true
    check(M.set_mark(3, mate({ live = live('set', 3) })) == 'chosen', 'while what the mate runs is being checked: "chosen", not "active"')
    S.liveUnsure = nil
    S.server.caps = nil
    mark, tone = M.set_mark(3, mate({ live = live('set', 3) }))
    check(mark == 'chosen' and tone == nil, 'a server that does not report what runs: "chosen" from the choice, never "active"')
    S.server.caps = { live = true }
    local text, t2 = M.running_line(mate({ live = live('set', 5, 2) }), d)
    check(text:find('Mage 75 plan', 1, true) and text:find('not the set open here', 1, true) and text:find('2 rules skipped', 1, true) and t2 == 'ok',
          'editing set 3 while the mate runs set 5: the line names set 5 and says it is not the set open here: ' .. text)
    text = M.running_line(mate({ live = live('set', 3) }), d)
    check(text:find('Mage 28', 1, true) and not text:find('not the set open here', 1, true), 'the mate runs the set that is open: just its name')
    text, t2 = M.running_line(mate({ live = live('pending', 5) }), d)
    check(text:find('Apply needed', 1, true) and t2 == 'gold', 'pending: what still runs, and "Apply needed" for what is chosen: ' .. text)
    check(M.running_line(mate({ out = false, live = live('off') }), d):find('not called', 1, true) and M.running_line(mate({ live = live('job') }), d) == 'default job rules'
        and M.running_line(mate({ live = live('fallback') }), d):find('not used', 1, true), 'not called / default job rules / fallback are said as such')
    S.server.caps = nil
    check(M.running_line(mate({ live = live('set', 3) }), d):find('not reported by this server', 1, true), 'a server that does not report it: said so, with what is chosen')

    -- ---- drawn: the mate row, the divider, a row that is selected AND active, the status area, the rule controls
    S.server.caps = { live = true }
    MATES[1].chosen, MATES[1].out, MATES[1].live = 3, true, live('set', 3)
    S.selectedSet, S.sel = 3, 1
    d.dirty = false
    local pushed, bars, widths = {}, 0, {}
    g.PushStyleColor = function(_, c) g.colors = g.colors + 1; pushed[#pushed + 1] = c end
    g.SetNextItemWidth = function(wd) widths[#widths + 1] = wd end
    g.GetItemRectMin, g.GetItemRectMax = function() return { 10, 10 } end, function() return { 210, 28 } end
    g.ColorConvertFloat4ToU32 = function(c) return c end
    g.GetWindowDrawList = function() return { AddRectFilled = function(_, a, b, col) if col == st.rowLine then bars = bars + 1 end end } end
    M.draw()
    check(balanced(g), 'drawn with every new part: balanced')
    local firstCombo
    for _, l in ipairs(g.log) do if l:find('^combo ') then firstCombo = l; break end end
    check(firstCombo == 'combo ##gsq-mate = Mira' and hasText(g, 'RDM 28'), 'the first control is the mate list, showing the name only; its jobs and levels stand next to it')
    check(logHas(g, 'button ##gsq-split') and not hasText(g, 'Squad mate'), 'the divider is drawn between the two panels; the "Squad mate" caption is gone')
    local sawFill, sawGreen = false, false
    for _, c in ipairs(pushed) do sawFill = sawFill or c == st.rowFill; sawGreen = sawGreen or c == M.theme.ok end
    check(hasLabel(g, '3  Mage 28   (active)##gsq-set-3') and sawFill and sawGreen and bars == 8,
          'a set that is selected AND active: the row tint and line (selected), green text and the word "active" (' .. bars .. ' line bars: its row and the selected rule\'s)')
    check(hasText(g, 'Editing') and hasText(g, '"Mage 28"  (#3)') and hasText(g, 'Mira runs') and hasText(g, 'Active on Mira') and not hasText(g, 'in use by'),
          'the status area: Editing "Mage 28" (#3) with its state, and what Mira runs; the heading no longer says "in use by"')
    local lines = M.status_lines(d, M.mate())
    check(#lines == 2 and lines[1][1] == 'Editing' and lines[1][4] == 'Active on Mira' and lines[2][1] == 'Mira runs' and lines[2][3] == 'ok', 'M.status_lines: Editing (+ state), <mate> runs (the server\'s word)')
    check(M.footer_height(d) >= 2 * 18, 'the status area has room for its two lines (' .. tostring(M.footer_height(d)) .. ' px)')
    check(hasLabel(g, 'Add rule##gsq-add') and hasLabel(g, 'Up##gsq-up') and hasLabel(g, 'Down##gsq-down') and hasLabel(g, 'Remove##gsq-remove')
        and not hasLabel(g, 'Top##gsq-top') and not hasLabel(g, 'Bottom##gsq-bottom') and not hasLabel(g, 'On / off##gsq-toggle') and logHas(g, 'combo ##gsq-rulemore = More'),
          'next to the list: Add rule, Up, Down, Remove and More; no Top, Bottom or On / off button')
    if #d.rules >= 3 then
        local third = d.rules[3]
        S.sel = 3
        g.combos['##gsq-rulemore'], g.picks['##gsq-rulemore'] = true, 'Move to top'
        M.draw()
        g.combos['##gsq-rulemore'] = nil
        check(d.rules[1] == third and S.sel == 1 and d.dirty, 'More > Move to top: the selected rule is the first now (the same M.move_rule_end as the Top button was)')
        S.sel = 1
        g.combos['##gsq-rulemore'], g.picks['##gsq-rulemore'] = true, 'Move to bottom'
        M.draw()
        g.combos['##gsq-rulemore'] = nil
        check(d.rules[#d.rules] == third and S.sel == #d.rules, 'More > Move to bottom: it is the last')
    end
    -- value fields take the room there is, and keep their smallest width in a narrow panel
    local widest = 0
    for _, wd in ipairs(widths) do widest = math.max(widest, wd) end
    check(widest == 340, 'a wide window: the control with the rule\'s action name is 340 px (0.3.4: 260), up to its limit')
    widths = {}
    g.avail = { 300, 400 }
    M.draw()
    local narrowMax, kept = 0, false
    for _, wd in ipairs(widths) do narrowMax = math.max(narrowMax, wd); kept = kept or wd == 260 end
    check(kept and narrowMax <= 300 and balanced(g), 'a narrow panel (300 px): it keeps its smallest width, 260 px, and no control is asked to be wider than the panel (' .. narrowMax .. ')')
    MATES[1].chosen, MATES[1].out, MATES[1].live = 0, false, nil
    S.server.caps = nil
end

-- ================================================================= Q. (0.3.6) follow-up from the first DEV session
section('Q (0.3.6): the list row is the set\'s name; the Save buttons stay on the screen')
do
    local function draft(nRules)
        local rules = {}
        for i = 1, nRules do rules[i] = rule('PARTY', 'HPP_LT', tostring(10 + i), nil, nil, 'family', 'CURE') end
        return { num = 3, job = 'RDM', name = 'Mage 28', flags = 'o', rules = rules, dirty = false }
    end
    local function live(state, num) return { state = state, num = num or 0, why = '-', fb = 0, dropped = 0 } end

    -- ---- 7. the Rule Set list: the name, and "active" when the server says so; the rest is in the status area
    local g = fakeGui({ avail = { 1064, 560 } })
    local d = draft(3)
    setup(g, 1, d)
    S.server.caps = { live = true }
    MATES[1].chosen, MATES[1].out, MATES[1].live = 3, false, live('off')
    d.dirty = true
    M.draw()
    check(hasLabel(g, '3  Mage 28##gsq-set-3') and not hasLabel(g, 'next call') and not hasLabel(g, 'editing') and not hasLabel(g, 'chosen'),
          'a set chosen for a mate that is not called, open with unsaved changes: the row is "3  Mage 28", nothing after the name')
    check(hasText(g, 'Mira runs') and hasText(g, 'nothing: not called.  Next call: Mage 28') and hasText(g, 'Unsaved changes'),
          'the status area says it: "Mira runs  nothing: not called.  Next call: Mage 28", and "Unsaved changes" on the Editing line')
    local gh = fakeGui({ avail = { 1064, 560 }, hover = true })
    setup(gh, 1, d)
    S.server.caps = { live = true }
    M.draw()
    local tip = false
    for _, t in ipairs(gh.tips) do tip = tip or (tostring(t):find('Chosen for Mira: used when Mira is called', 1, true) ~= nil and tostring(t):find('with unsaved changes', 1, true) ~= nil) end
    check(tip, 'the row\'s tooltip still has the details (chosen for the next call; open in the editor, with unsaved changes)')
    MATES[1].out, MATES[1].live = true, live('set', 3)
    d.dirty = false
    local g2 = fakeGui({ avail = { 1064, 560 } })
    local pushed = {}
    g2.PushStyleColor = function(_, c) g2.colors = g2.colors + 1; pushed[#pushed + 1] = c end
    setup(g2, 1, d)
    S.server.caps = { live = true }
    M.draw()
    local green, fill = false, false
    for _, c in ipairs(pushed) do green = green or c == M.theme.ok; fill = fill or c == M.UI.states(M.theme).rowFill end
    check(hasLabel(g2, '3  Mage 28   (active)##gsq-set-3') and green and fill and hasLabel(g2, '5  Mage 75 plan##gsq-set-5'),
          'the set the server reports as running: "(active)" after the name, green, and the selection tint when it is selected; other rows are just names')
    MATES[1].live = live('job')
    local g3 = fakeGui({ avail = { 1064, 560 } })
    setup(g3, 1, d)
    S.server.caps = { live = true }
    M.draw()
    check(hasLabel(g3, '3  Mage 28##gsq-set-3') and not hasLabel(g3, 'Apply needed)') and hasText(g3, 'Apply needed'),
          'chosen but not running: the row is the name only; "Apply needed" is in the status area')

    -- ---- 8. the panels end where the screen ends
    local function drawn(scale, avail, screenH, cursorY, dirty)
        local gg = fakeGui({ avail = avail })
        gg.GetCursorScreenPos = function() return 0, cursorY end
        -- (the stand-in says the window's room everywhere; inside a panel ImGui says the PANEL's room, and the rules'
        -- height is worked out from that, so it is modelled here)
        local stack, realBegin, realEnd = {}, gg.BeginChild, gg.EndChild
        gg.BeginChild = function(id, size, ...)
            local r = realBegin(id, size, ...)
            stack[#stack + 1] = (type(size) == 'table' and (size[2] or 0) > 0) and size[2] or (stack[#stack] or avail[2])
            return r
        end
        gg.EndChild = function(...) table.remove(stack); return realEnd(...) end
        gg.GetContentRegionAvail = function() return { avail[1], stack[#stack] or avail[2] } end
        local dd = draft(12)
        dd.dirty = dirty ~= false
        api.display_h = screenH and function() return screenH end or nil
        setup(gg, 1, dd, scale)
        S.server.caps = { live = true }
        MATES[1].chosen, MATES[1].out, MATES[1].live = 3, true, live('set', 3)
        M.draw(); M.draw()
        local left = gg.sizes['##gsq-left'] and gg.sizes['##gsq-left'][2]
        local body = gg.sizes['##gsq-right-body'] and gg.sizes['##gsq-right-body'][2]
        return gg, left, body, M.footer_height(dd), dd
    end
    local gA, leftA = drawn(1, { 1064, 900 }, 2000, 100)
    check(leftA == 900 - 6, 'the window wholly on the screen: the panels have the window\'s height, as before (' .. tostring(leftA) .. ')')
    local gB, leftB, bodyB, footB = drawn(1, { 1064, 900 }, 700, 300)
    check(leftB == 700 - 300 - 6 - 10 and bodyB + footB <= leftB and balanced(gB),
          string.format('the window reaching 500 px below the screen\'s bottom: the panels end at the screen (%s px), and the rules (%s) plus the status area and buttons (%s) fit in that', tostring(leftB), tostring(bodyB), tostring(footB)))
    local after, save, apply = false, false, false
    for i, l in ipairs(gB.log) do
        if l == 'child ##gsq-right-body' then after = i end
        if after and l:find('##gsq-save', 1, true) and not l:find('apply', 1, true) then save = true end
        if after and l:find('##gsq-save-apply', 1, true) then apply = true end
    end
    check(save and apply, 'Save and Save & Apply are drawn below the scrolling rules, inside that height: reachable')
    local gC, leftC = drawn(1, { 1064, 900 }, nil, 300)
    check(leftC == 900 - 6, 'an ImGui that does not say the screen\'s size: the window\'s height is used, as before')
    for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
        local screenH, y = 1080, 1080 - math.floor(520 * scale)   -- (the window's content starts 520 px, scaled, above the bottom)
        local gS, leftS, bodyS, footS = drawn(scale, { math.floor(1064 * scale), math.floor(900 * scale) }, screenH, y)
        local room = math.floor(screenH - y - 6 * scale - 10 * scale)
        check(leftS == room and bodyS + footS <= leftS and balanced(gS),
              string.format('%d %%: the panels end at the screen\'s bottom (%s of %s px room), rules + status area + buttons fit', scale * 100, tostring(leftS), tostring(room)))
    end
    -- narrow: the smallest window (720 x 420 at 100 %), low on the screen
    local gN, leftN, bodyN, footN = drawn(1, { 704, 380 }, 768, 768 - 300)
    check(leftN == 768 - 468 - 16 and bodyN + footN <= leftN and hasLabel(gN, '##gsq-save-apply'),
          string.format('the smallest window, 300 px above the screen\'s bottom: panels %s px, Save & Apply still drawn inside', tostring(leftN)))
    -- the limit: when less than 240 px (at 100 %) of the window is on the screen the panels keep 240 px
    local gL, leftL = drawn(1, { 1064, 900 }, 700, 600)
    check(leftL == 240, 'a window that is almost off the screen (84 px of room): the panels keep their 240 px; the buttons cannot be kept on the screen then (' .. tostring(leftL) .. ')')
    api.display_h = nil
    setup(fakeGui({ avail = { 1064, 560 } }), 1, draft(3))
    check(M.panel_height(500, 6) == 500 and M.panel_height(100, 6) == 240, 'M.panel_height: the window\'s room when the screen is unknown; never less than 240 px')
    MATES[1].chosen, MATES[1].out, MATES[1].live = 0, false, nil
    S.server.caps = nil
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
