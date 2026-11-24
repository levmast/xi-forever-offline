-- Gambits picker list cache (squad_editor.lua cached_view): stand-in tests, no game, no Ashita.
--   luajit test_gambits_view_cache.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                      <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> <server root>
--                                      [a folder with an EARLIER squad_editor.lua, to compare against]
-- The lists the pickers show (spell_choices, ja_choices, spell_view, family_view, ja_view, effect_choices) are kept
-- between frames. Every list here is compared, entry by entry and in order, with a reference that is never cached:
-- a second copy of the editor whose cache is emptied before each call, or - with the seventh argument - the editor of
-- an earlier version without the cache. REAL catalogs made by the server's gambits_squad.lua, as test_gambits_uiux.lua.
-- What the game does with the real ImGui is proven only in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT, BASE_DIR = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6], arg[7]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER_ROOT,
       'usage: test_gambits_view_cache.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server-root [earlier addon-dir]')
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
local JOB = { WAR = 1, WHM = 3, BLM = 4, RDM = 5, THF = 6, PLD = 7, BRD = 10, NIN = 13 }
local SQUAD = {
    { slot = 1, id = 101, name = 'Mira', mjob = JOB.RDM, sjob = 0, jobs = { [JOB.RDM] = { level = 28 } } },
    { slot = 2, id = 102, name = 'Lyra', mjob = JOB.RDM, sjob = JOB.WHM, jobs = { [JOB.RDM] = { level = 28 }, [JOB.WHM] = { level = 14 } } },
    { slot = 3, id = 103, name = 'Bard', mjob = JOB.BRD, sjob = JOB.WHM, jobs = { [JOB.BRD] = { level = 75 }, [JOB.WHM] = { level = 37 } } },
    { slot = 4, id = 104, name = 'Rook', mjob = JOB.WAR, sjob = JOB.NIN, jobs = { [JOB.WAR] = { level = 30 }, [JOB.NIN] = { level = 15 } } },
    { slot = 5, id = 105, name = 'Vex', mjob = JOB.RDM, sjob = JOB.WHM, jobs = { [JOB.RDM] = { level = 75 }, [JOB.WHM] = { level = 37 } } },
    { slot = 6, id = 106, name = 'Kit', mjob = JOB.THF, sjob = 0, jobs = { [JOB.THF] = { level = 40 } } },
}
GetSquad = function() return SQUAD end
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end

-- ---------------------------------------------------------------- the editor (cached) and the reference (never cached)
local DATA = dofile(ADDON_DIR .. '/gambits_data.lua')
local clock = 100
local function editor(dir)
    local m = dofile(dir .. '/squad_editor.lua')
    local prefs = {}
    m.init({ now = function() return clock end, queue_command = function() end, addon_data = DATA,
             get_pref = function(k) return prefs[k] end, set_pref = function(k, v) prefs[k] = v end })
    m._S.server = { version = 6, maxRules = 32, maxLine = 120, maxChunks = 64 }
    return m
end
local M = editor(ADDON_DIR)
local REF = editor(BASE_DIR or ADDON_DIR)
io.write(BASE_DIR and ('reference: the editor in ' .. BASE_DIR .. '\n') or 'reference: this editor with its cache emptied before every call\n')
check(type(M.clear_view_cache) == 'function', 'the editor has clear_view_cache')
local function ref(fn, ...)
    if REF.clear_view_cache then REF.clear_view_cache() end
    return REF[fn](...)
end
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
    { slot = 3, name = 'Bard', job = 'BRD', level = 75, sub = 'WHM', subLevel = 37, chosen = 0, out = false },
    { slot = 4, name = 'Rook', job = 'WAR', level = 30, sub = 'NIN', subLevel = 15, chosen = 0, out = false },
    { slot = 5, name = 'Vex', job = 'RDM', level = 75, sub = 'WHM', subLevel = 37, chosen = 0, out = false },
    { slot = 6, name = 'Kit', job = 'THF', level = 40, chosen = 0, out = false },
}
local CAT, PLAN = {}, {}
for i, m in ipairs(MATES) do CAT[i] = catm(m.slot); PLAN[i] = plan(m.job, m.sub) end

-- the same values in the same order, all the way down (tables are compared by content, never by identity)
local function same(a, b, depth)
    depth = depth or 0
    if type(a) ~= type(b) then return false end
    if type(a) ~= 'table' then return a == b end
    if depth > 8 then return true end
    for k, v in pairs(a) do if not same(v, b[k], depth + 1) then return false end end
    for k in pairs(b) do if a[k] == nil then return false end end
    return true
end
local function copy(a, depth)
    depth = depth or 0
    if type(a) ~= 'table' or depth > 8 then return a end
    local out = {}
    for k, v in pairs(a) do out[k] = copy(v, depth + 1) end
    return out
end
local function labels(list) local out = {} for i, e in ipairs(list) do out[i] = e.label or e.name or e end return table.concat(out, '|') end
local function has(list, name) for _, e in ipairs(list) do if e.name == name then return e end end return nil end

-- every list of one mate, both Show all settings: equal to the reference; a second call gives the very same table
local VIEWS = { 'spell_view', 'family_view', 'ja_view' }
local function compare_all(what, cat, mate, pl)
    local bad, kept = {}, true
    for _, fn in ipairs({ 'spell_choices', 'ja_choices' }) do
        local a = M[fn](cat, mate)
        if not same(a, ref(fn, cat, mate)) then bad[#bad + 1] = fn end
        kept = kept and rawequal(a, M[fn](cat, mate))
    end
    for _, fn in ipairs(VIEWS) do
        for _, all in ipairs({ false, true }) do
            local a = M[fn](cat, mate, all, pl)
            if not same(a, ref(fn, cat, mate, all, pl)) then bad[#bad + 1] = fn .. (all and ' (Show all)' or '') end
            kept = kept and rawequal(a, M[fn](cat, mate, all, pl))
        end
    end
    local job, common = M.effect_choices(cat, mate, pl)
    local rjob, rcommon = ref('effect_choices', cat, mate, pl)
    if not (same(job, rjob) and same(common, rcommon)) then bad[#bad + 1] = 'effect_choices' end
    local job2, common2 = M.effect_choices(cat, mate, pl)
    kept = kept and rawequal(job, job2) and rawequal(common, common2)
    check(#bad == 0, what .. ': every list equals the reference, entry by entry and in order: ' .. table.concat(bad, ', '))
    check(kept, what .. ': a second call with nothing changed returns the kept lists')
end

-- ================================================================= 1. contents and order
section('1: contents, order and filtering are those of the uncached lists (six mates, Show all on and off)')
for i, m in ipairs(MATES) do
    compare_all(string.format('%s %s%d%s', m.name, m.job, m.level, m.sub and ('/' .. m.sub .. m.subLevel) or ''), CAT[i], m, PLAN[i])
end
do
    local vex = MATES[5]
    check(#M.spell_view(CAT[5], vex, false, PLAN[5]) > 100 and #M.family_view(CAT[5], vex, true, PLAN[5]) > 50,
          'the lists are real ones (RDM75/WHM37: over 100 spells, over 50 families)')
    compare_all('no mate', CAT[5], nil, PLAN[5])
    compare_all('no catalog', nil, vex, nil)
    compare_all('no planning list', CAT[5], vex, nil)
end

-- ================================================================= 2. jobs and levels
section('2: a change of job, sub job or level gives new lists; the same values in another table do not')
do
    local lyra = copy(MATES[2])
    local before = M.spell_view(CAT[2], lyra, false, PLAN[2])
    local beforeLabels = labels(before)
    local twin = copy(lyra)
    check(rawequal(before, M.spell_view(CAT[2], twin, false, PLAN[2])), 'another mate table with the same job, sub job and levels: the kept list')
    -- the main level, changed in place (older servers filter by it in the editor: an old-style catalog)
    local old = copy(CAT[2]); old.perMate = false
    local at28 = M.spell_choices(old, lyra)
    local at28n = #at28
    lyra.level = 10
    local at10 = M.spell_choices(old, lyra)
    check(not rawequal(at28, at10) and #at10 < at28n and same(at10, ref('spell_choices', old, lyra)),
          string.format('main level 28 -> 10 changed in place: a new, shorter list (%d -> %d), equal to the reference', at28n, #at10))
    compare_all('older catalog at level 10', old, lyra, old)
    lyra.level = 28
    -- the sub job level: the sub job cap moves from 37 to 75 when the sub level reaches the main level
    local jaHalf = labels(M.ja_view(CAT[2], lyra, false, PLAN[2]))
    local spHalf = labels(M.spell_view(CAT[2], lyra, false, PLAN[2]))
    check(spHalf == beforeLabels, 'back at the first values: the first contents again')
    lyra.subLevel = 28
    compare_all('sub level 14 -> 28', CAT[2], lyra, PLAN[2])
    local spFull = labels(M.spell_view(CAT[2], lyra, false, PLAN[2]))
    check(spFull ~= spHalf and M.sub_cap(lyra) == 75, 'sub level = main level: the sub job cap is 75 and the spell list changes')
    lyra.subLevel = 14
    -- the sub job removed, then another one
    lyra.sub, lyra.subLevel = nil, nil
    compare_all('sub job removed', CAT[2], lyra, PLAN[2])
    check(labels(M.ja_view(CAT[2], lyra, false, PLAN[2])) ~= jaHalf or labels(M.spell_view(CAT[2], lyra, false, PLAN[2])) ~= spHalf,
          'without the sub job the lists differ')
    lyra.sub, lyra.subLevel = 'BLM', 14
    compare_all('another sub job (labels and blue magic rules use it)', CAT[2], lyra, PLAN[2])
    -- another main job with the same catalog tables: the labels name the job
    local other = copy(MATES[2]); other.job = 'WHM'
    compare_all('another main job', CAT[2], other, PLAN[2])
    -- a level-up as the game does it: new mate values, a new per-mate catalog from the server
    SQUAD[1].jobs[JOB.RDM].level = 40
    local up = copy(MATES[1]); up.level = 40
    local cat40 = catm(1)
    local sp28, sp40 = M.spell_view(CAT[1], MATES[1], false, PLAN[1]), M.spell_view(cat40, up, false, PLAN[1])
    local now28, now40 = 0, 0
    for _, e in ipairs(sp28) do if e.state == 'now' then now28 = now28 + 1 end end
    for _, e in ipairs(sp40) do if e.state == 'now' then now40 = now40 + 1 end end
    check(now40 > now28 and same(sp40, ref('spell_view', cat40, up, false, PLAN[1])),
          string.format('RDM 28 -> 40 with its new catalog: more spells usable now (%d -> %d), equal to the reference', now28, now40))
    compare_all('RDM 40 after the level-up', cat40, up, PLAN[1])
    SQUAD[1].jobs[JOB.RDM].level = 28
end

-- ================================================================= 3. Show all
section('3: Show all on and off are two lists, both kept, each equal to the reference')
do
    local m, c, p = MATES[4], CAT[4], PLAN[4] -- WAR 30 / NIN 15
    local fit, all = M.ja_view(c, m, false, p), M.ja_view(c, m, true, p)
    check(not rawequal(fit, all) and #all > #fit, string.format('job abilities: Show all is longer (%d -> %d)', #fit, #all))
    local okFlip = true
    for _ = 1, 5 do
        okFlip = okFlip and rawequal(fit, M.ja_view(c, m, false, p)) and rawequal(all, M.ja_view(c, m, true, p))
    end
    check(okFlip, 'switching Show all back and forth keeps both lists (nothing is made again)')
    check(same(fit, ref('ja_view', c, m, false, p)) and same(all, ref('ja_view', c, m, true, p)), 'both equal the reference')
    check(rawequal(M.ja_view(c, m, 1, p), all) and rawequal(M.ja_view(c, m, nil, p), fit), 'any true value is Show all, nil is off')
    local famFit, famAll = M.family_view(CAT[5], MATES[5], false, PLAN[5]), M.family_view(CAT[5], MATES[5], true, PLAN[5])
    local other = 0
    for _, e in ipairs(famAll) do if e.state == 'other' then other = other + 1 end end
    local leaked = false
    for _, e in ipairs(famFit) do leaked = leaked or e.state == 'other' or e.state == 'beyond' end
    check(other > 0 and not leaked, string.format('families: %d "not RDM" families only with Show all, none without', other))
end

-- ================================================================= 4. catalog reloads
section('4: a catalog or planning list sent again gives new lists; one changed in place too')
do
    local m = MATES[5]
    local first = M.spell_view(CAT[5], m, false, PLAN[5])
    local again = catm(5) -- (the server answers again: a new table with the same contents)
    local second = M.spell_view(again, m, false, PLAN[5])
    check(not rawequal(first, second) and same(first, second), 'the same catalog loaded again: a new list with the same contents')
    local planAgain = plan('RDM', 'WHM')
    check(not rawequal(second, M.spell_view(again, m, false, planAgain)), 'the planning list loaded again: a new list')
    -- a catalog with other contents (another mate's) in the same call
    local otherCat = M.spell_view(CAT[2], m, false, PLAN[5])
    check(same(otherCat, ref('spell_view', CAT[2], m, false, PLAN[5])) and labels(otherCat) ~= labels(first),
          'another catalog: its own contents, not the kept ones')
    -- changed in place (nothing in the editor does this; the list lengths are compared in case something does)
    local grown = copy(CAT[5])
    local a = M.spell_view(grown, m, false, PLAN[5])
    grown.spells[#grown.spells + 1] = { name = 'ZZ_TEST_SPELL', level = 1 }
    local b = M.spell_view(grown, m, false, PLAN[5])
    check(not rawequal(a, b) and has(b, 'ZZ_TEST_SPELL') and same(b, ref('spell_view', grown, m, false, PLAN[5])),
          'a spell added to the catalog table in place: it is in the list')
    local ja0 = M.ja_view(grown, m, false, PLAN[5])
    grown.jas[#grown.jas + 1] = { name = 'ZZ_TEST_JA', level = 1 }
    check(has(M.ja_view(grown, m, false, PLAN[5]), 'ZZ_TEST_JA') and not has(ja0, 'ZZ_TEST_JA'), 'a job ability added in place: it is in the list')
    local fam0 = #M.family_view(grown, m, true, PLAN[5])
    grown.families[#grown.families + 1] = 'ZZ_TEST_FAMILY'
    check(#M.family_view(grown, m, true, PLAN[5]) == fam0 + 1, 'a family added in place: it is in the list')
    local planGrown = copy(PLAN[5])
    local p0 = M.spell_view(CAT[5], m, false, planGrown)
    planGrown.spells[#planGrown.spells + 1] = { name = 'ZZ_PLAN_SPELL', level = 70 }
    check(not has(p0, 'ZZ_PLAN_SPELL') and has(M.spell_view(CAT[5], m, false, planGrown), 'ZZ_PLAN_SPELL'), 'a spell added to the planning list in place: it is in the list')
    -- the planning list the editor keeps itself (S.plan): not asked yet, loading, failed, ready
    local lyra = MATES[2]
    for _, ed in ipairs({ M, REF }) do ed._S.plan = nil end
    local none = M.ja_view(CAT[2], lyra, false)
    check(same(none, ref('ja_view', CAT[2], lyra, false)), 'no planning list yet: the server\'s list as it is')
    for _, ed in ipairs({ M, REF }) do ed._S.plan = { key = M.plan_key(lyra), loading = true } end
    check(same(M.ja_view(CAT[2], lyra, false), ref('ja_view', CAT[2], lyra, false)), 'loading: unchanged')
    for _, ed in ipairs({ M, REF }) do ed._S.plan = { key = M.plan_key(lyra), cat = PLAN[2] } end
    local ready = M.ja_view(CAT[2], lyra, false)
    check(not rawequal(none, ready) and #ready > #none and same(ready, ref('ja_view', CAT[2], lyra, false))
          and rawequal(ready, M.ja_view(CAT[2], lyra, false, PLAN[2])),
          string.format('the planning list arrives: the list is made again with what is learned later (%d -> %d)', #none, #ready))
    for _, ed in ipairs({ M, REF }) do ed._S.plan = { key = M.plan_key(lyra), error = 'no answer' } end
    check(same(M.ja_view(CAT[2], lyra, false), none), 'failed: the unfiltered list again')
    for _, ed in ipairs({ M, REF }) do ed._S.plan = nil end
end

-- ================================================================= 5. the addon data, Trust spells, the level cap
section('5: the addon data (set_data), the Trust spell list and the planning level are part of what a list is made from')
do
    local m, c, p = MATES[5], CAT[5], PLAN[5]
    local withData = M.family_view(c, m, false, p)
    local effWith = M.effect_choices(c, m, p)
    M.set_data(nil); REF.set_data(nil)
    local noData = M.family_view(c, m, false, p)
    check(not rawequal(withData, noData) and noData[1].state == 'unknown' and same(noData, ref('family_view', c, m, false, p)),
          'without the addon data: the server\'s family list, unmarked')
    check(#M.effect_choices(c, m, p) == 0 and #effWith > 0, 'without the addon data: no job effects (they were ' .. #effWith .. ')')
    M.set_data(DATA); REF.set_data(DATA)
    check(same(M.family_view(c, m, false, p), withData), 'with the data again: the first contents')
    compare_all('after set_data', c, m, p)
    -- the Trust spell list
    local keep, keepRef = M.TRUSTS, REF.TRUSTS
    local some = M.spell_view(c, m, false, p)[1].name
    M.TRUSTS = { [some] = true }; REF.TRUSTS = M.TRUSTS
    check(not has(M.spell_view(c, m, false, p), some) and not has(M.spell_choices(c, m), some), 'a name in the Trust list leaves the spell lists (' .. some .. ')')
    compare_all('another Trust list', c, m, p)
    M.TRUSTS, REF.TRUSTS = keep, keepRef
    check(has(M.spell_view(c, m, false, p), some) ~= nil, 'the first Trust list again: it is back')
    -- the planning level
    local lyra = MATES[2]
    local j75 = labels(M.ja_view(CAT[2], lyra, true, PLAN[2]))
    M.PLAN_LEVEL, REF.PLAN_LEVEL = 50, 50
    compare_all('planning level 50', CAT[2], lyra, PLAN[2])
    check(labels(M.ja_view(CAT[2], lyra, true, PLAN[2])) ~= j75, 'planning level 50: other marks than at 75')
    M.PLAN_LEVEL, REF.PLAN_LEVEL = 75, 75
    check(labels(M.ja_view(CAT[2], lyra, true, PLAN[2])) == j75, 'planning level 75 again: the first contents')
    -- init (the addon is loaded again) empties everything
    local before = M.spell_view(c, m, false, p)
    M.clear_view_cache()
    check(not rawequal(before, M.spell_view(c, m, false, p)) and same(before, M.spell_view(c, m, false, p)), 'clear_view_cache: made again, the same contents')
end

-- ================================================================= 6. switching mates and Rule Sets
section('6: switching between squad mates and between rules never shows another mate\'s or rule\'s list')
do
    local okSwitch = true
    for round = 1, 3 do
        for i, m in ipairs(MATES) do
            for _, all in ipairs({ false, true }) do
                okSwitch = okSwitch and same(M.spell_view(CAT[i], m, all, PLAN[i]), ref('spell_view', CAT[i], m, all, PLAN[i]))
                    and same(M.family_view(CAT[i], m, all, PLAN[i]), ref('family_view', CAT[i], m, all, PLAN[i]))
                    and same(M.ja_view(CAT[i], m, all, PLAN[i]), ref('ja_view', CAT[i], m, all, PLAN[i]))
            end
            local job, common = M.effect_choices(CAT[i], m, PLAN[i])
            local rjob, rcommon = ref('effect_choices', CAT[i], m, PLAN[i])
            okSwitch = okSwitch and same(job, rjob) and same(common, rcommon)
        end
    end
    check(okSwitch, 'three rounds over six mates, every list and both Show all settings: always the mate\'s own lists')
    -- the same catalogs, mates with the same jobs and levels but another name: the tooltips and notes use the name asked for
    local vex, twin = MATES[5], copy(MATES[5]); twin.name = 'Twin'
    local e = M.spell_view(CAT[5], vex, false, PLAN[5])[1]
    check(rawequal(M.spell_view(CAT[5], twin, false, PLAN[5])[1], e), 'the same jobs and levels under another name: the kept list (no name is in it)')
    local later
    for _, x in ipairs(M.ja_view(CAT[2], MATES[2], true, PLAN[2])) do if x.state == 'later' then later = x; break end end
    local t1, t2 = M.entry_tip('ja', e, vex), M.entry_tip('ja', e, twin)
    check(M.ja_tip(later, MATES[2]) == REF.ja_tip(later, MATES[2]) and t1 == REF.entry_tip('ja', e, vex) and t2 == REF.entry_tip('ja', e, twin),
          'tooltips are made for the mate asked for, as before')
    -- rules: notes and saved entries are made per rule, from the kept lists, and equal the reference's
    local rules = {
        { kind = 'spell', name = 'CURE_IV' }, { kind = 'spell', name = 'CURE_V' }, { kind = 'spell', name = 'FIRE_IV' }, { kind = 'spell', name = 'ZZ_NOT_A_SPELL' },
        { kind = 'family', name = 'CURE' }, { kind = 'family', name = 'NINJUTSU_SHADOW' }, { kind = 'family', name = 'ZZ_NOT_A_FAMILY' },
        { kind = 'ja', name = 'PROVOKE' }, { kind = 'ja', name = 'CONVERT' }, { kind = 'ja', name = 'BENEDICTION' }, { kind = 'ja', name = 'ZZ_NOT_A_JA' },
        { kind = 'attack' }, { kind = 'ranged' },
    }
    local okNotes, okSaved, notes = true, true, 0
    for i, m in ipairs(MATES) do
        for _, r in ipairs(rules) do
            local a, b = M.action_note(r, CAT[i], m, PLAN[i]), REF.action_note(r, CAT[i], m, PLAN[i])
            okNotes = okNotes and a == b
            notes = notes + (a and 1 or 0)
            if r.kind == 'ja' then
                okSaved = okSaved and same(M.ja_saved_entry(r.name, CAT[i], m, PLAN[i]), REF.ja_saved_entry(r.name, CAT[i], m, PLAN[i]))
            end
        end
    end
    check(okNotes and notes > 20, string.format('action notes for %d rules on six mates equal the reference (%d with a note)', #rules, notes))
    check(okSaved, 'saved job abilities outside the list: the same entry as the reference')
    -- nothing a rule holds is kept: the same rule table with another name gets another note at once
    local r = { kind = 'spell', name = 'CURE' }
    local n1 = M.action_note(r, CAT[1], MATES[1], PLAN[1])
    r.name = 'CURE_V'
    local n2 = M.action_note(r, CAT[1], MATES[1], PLAN[1])
    check(n1 ~= n2 and n2 == REF.action_note(r, CAT[1], MATES[1], PLAN[1]), 'a rule changed in place: its note follows at once')
end

-- ================================================================= 7. the kept lists are not changed by their users
section('7: the kept lists are read, never changed (they are shared between frames)')
do
    M.clear_view_cache()
    local snap = {}
    for i, m in ipairs(MATES) do
        if i == 5 then
            for _, fn in ipairs(VIEWS) do
                for _, all in ipairs({ false, true }) do
                    local list = M[fn](CAT[i], m, all, PLAN[i])
                    snap[#snap + 1] = { fn = fn, all = all, list = list, was = copy(list) }
                end
            end
        end
    end
    local m, c, p = MATES[5], CAT[5], PLAN[5]
    local job, common = M.effect_choices(c, m, p)
    local jobWas, commonWas = copy(job), copy(common)
    -- everything that reads them: notes, saved entries, tooltips, the other lists
    for _, r in ipairs({ { kind = 'spell', name = 'CURE_V' }, { kind = 'family', name = 'CURE' }, { kind = 'ja', name = 'BENEDICTION' }, { kind = 'ja', name = 'CONVERT' } }) do
        M.action_note(r, c, m, p)
        M.ja_saved_entry(r.name, c, m, p)
    end
    for _, s in ipairs(snap) do
        for _, e in ipairs(s.list) do M.entry_tip(s.fn == 'family_view' and 'family' or (s.fn == 'ja_view' and 'ja' or 'spell'), e, m) end
    end
    for _, e in ipairs(job) do M.effect_tip(e.name, e, m) end
    M.family_view(c, m, true, p); M.effect_choices(c, m, p); M.spell_choices(c, m); M.ja_choices(c, m)
    local okSnap = true
    for _, s in ipairs(snap) do
        okSnap = okSnap and rawequal(s.list, M[s.fn](c, m, s.all, p)) and same(s.list, s.was)
    end
    check(okSnap and same(job, jobWas) and same(common, commonWas), 'after notes, saved entries and tooltips: every kept list is as it was made')
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
