-- Gambits feedback batch B7-F24 (2026-11-27): F22 more conditions with subjects, F10 the burst tier cap, F20 ERASABLE, F21 the
-- target ENEMY_ADD, F18 Wake to act, and the editor's examples. Stand-in tests, no game, no server, no Ashita.
--   luajit test_gambits_feedback_b7.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                       <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder> <server root>
--                                       [<base kit>/addons-src/Gambits]
-- What runs for real: squad_rulesets.lua (checks), gambits_squad.lua v12 (the codec, catm "jmfs", caps), squad.lua's rule
-- builder (ruleCondition / ruleAction / applyRules: what the engine is given), the editor (squad_editor.lua: rows, codec, checks,
-- texts, examples) and share_code.lua (format 1 unchanged, format 2). The optional last argument is an older Gambits folder:
-- its share_code.lua must refuse a format 2 code, and must write the same format 1 code as the new one.
-- What does NOT run here: the C++ (subjects in CheckTrigger, ERASABLE, ENEMY_ADD, the tier cap, WAKE): squad_feedback_b7_tests.cpp
-- tests their rules, the engine is checked in game.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK, SERVER_ROOT, OLD_ADDON = arg[1], arg[2], arg[3], arg[4], arg[5], arg[6], arg[7]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK and SERVER_ROOT,
       'usage: test_gambits_feedback_b7.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir server-root [old-addon-dir]')
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
xi.effectFlag = xi.effectFlag or { DISPELABLE = 1, ERASABLE = 2 }
xi.mobFamily = { GOBLIN = 58 }
xi.objType = { PC = 1, TRUST = 2 }
xi.msg = { channel = { SYSTEM_3 = 121 } }
xi.settings = { main = { RESTRICT_CONTENT = 1, ENABLE_COP = 1, ENABLE_ROTZ = 1, ENABLE_TOAU = 1, ENABLE_WOTG = 0 } }
SquadOwnerMerit = function() return 0 end
SquadJobExpansionEngine = function() return 1 end
SquadRoleFilterEngine = function() return 1 end
SquadApplyWeaponSkills = function() return true end
SquadStatusTierEngine = function() return 1 end
SquadFeedbackEngine = function() return 1 end
local function engineOn() SquadCondSubjectEngine = function() return 1 end end
local function engineOff() SquadCondSubjectEngine = nil end
engineOn()
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

-- squad.lua's rule builder: ruleArg .. applyRules, as the file has them, with stand-ins for what they call
local gambits = {}
local builder
do
    local src = assert(readAll(LUA_DIR .. '/squad.lua'))
    local a = assert(src:find('local function ruleArg%('))
    local b = assert(src:find('\n%-%- Runs one part', a))
    local function cond(id, arg) return { id, type(arg) == 'string' and xi.effect[arg] or (arg or 0) } end
    local function both(x, y) if x == nil or y == nil then return nil end return { x, y } end
    local env = setmetatable({
        cond = cond, both = both, profileLevel = 75,
        spell = function(name) return xi.magic.spell[name] and { ai.r.MA, ai.s.SPECIFIC, xi.magic.spell[name] } or nil end,
        family = function(name) return { ai.r.MA, ai.s.HIGHEST, xi.magic.spellFamily[name] or 0 } end,
        addGambit = function(mob, target, condition, action, retry)
            if condition == nil or action == nil then
                return -- (as squad.lua's addGambit: a rule without both is never added)
            end

            gambits[#gambits + 1] = { target = target, condition = condition, action = action, retry = retry }
        end,
    }, { __index = _G })
    local text = src:sub(a, b) .. '\nreturn { ruleCondition = ruleCondition, ruleAction = ruleAction, applyRules = applyRules }'
    local chunk
    if setfenv then
        chunk = assert(loadChunk(text, '=squad.lua rules'))
        setfenv(chunk, env)
    else
        chunk = assert(load(text, '=squad.lua rules', 't', env))
    end
    builder = chunk()
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
GetSquad = function() return { { slot = 1, id = 101, name = 'Heala', mjob = 5, sjob = 0, jobs = { [5] = { level = 75 } } } } end

local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local function run(line) srv.printed = {}; G.handle(srv, line); return srv.printed end
local function F(line) return G.splitPlain(line, '|') end
local function problems(rule) return table.concat(R.ruleProblems(rule), '; ') end
local function has(text, part) return text ~= nil and string.find(text, part, 1, true) ~= nil end

-- ================================================================= the engine's numbers
section('gambits.lua: the new numbers (as gambits_container.h)')
check(ai.c.ERASABLE == 47 and ai.c.WAKE == 48, 'ERASABLE 47, WAKE 48')
check(ai.t.ENEMY_ADD == 15, 'the target ENEMY_ADD 15')
check(ai.SUBJECT_STEP == 0x1000 and ai.subject.SELF == 1 and ai.subject.ENEMY == 2, 'a subject: condition + subject * 0x1000 (1 self, 2 enemy)')

-- ================================================================= F22 / F10 / F18 / F20 / F21: the Rule Set checks
section('squad_rulesets.lua: conds, subjects, burstcap, wake, ERASABLE, ENEMY_ADD')
do
    local function r(t) t.id, t.on = t.id or 'r1', true; return t end
    local selfMp = { 'MPP_GTE', 30, of = 'SELF' }
    check(problems(r({ target = 'TARGET', conds = { { 'MB_AVAILABLE' }, selfMp }, action = { 'burst' } })) == '',
        'a burst rule with "Self: MP at least 30%" is valid')
    check(problems(r({ target = 'PARTY', conds = { { 'HPP_LT', 50 }, { 'HPP_LT', 80, of = 'ENEMY' }, { 'MPP_GTE', 20, of = 'SELF' },
        { 'NOT_STATUS', 'SLEEP_I' } }, action = { 'family', 'CURE' } })) == '', 'four conditions on three subjects are valid')
    check(has(problems(r({ target = 'PARTY', conds = { { 'ALWAYS' }, { 'ALWAYS' }, { 'ALWAYS' }, { 'ALWAYS' }, { 'ALWAYS' } },
        action = { 'family', 'CURE' } })), 'list of 1-4'), 'five conditions are refused')
    check(has(problems(r({ target = 'PARTY', cond = { 'HPP_LT', 50 }, conds = { { 'HPP_LT', 50 } }, action = { 'family', 'CURE' } })),
        'one or the other'), 'cond and conds together are refused')
    check(has(problems(r({ target = 'PARTY', conds = { { 'PARTY_COUNT', { cmp = 'AT_LEAST', count = 2 }, of = 'SELF' } },
        action = { 'family', 'CURAGA' } })), 'does not read a subject'), 'a subject on a condition that reads none is refused')
    check(has(problems(r({ target = 'PARTY', conds = { { 'HPP_LT', 50, of = 'BOSS' } }, action = { 'family', 'CURE' } })),
        'TARGET, SELF or ENEMY'), 'an unknown subject is refused')
    check(has(problems(r({ target = 'PARTY', conds = { { 'HPP_LT', 50, extra = 1 } }, action = { 'family', 'CURE' } })),
        'only'), 'a condition with another key is refused')
    check(has(problems(r({ target = 'TARGET', cond = { 'MB_AVAILABLE' }, cond2 = selfMp, action = { 'burst' } })), 'goes in conds'),
        'a subject in the old cond2 is refused (cond / cond2 always meant the target)')
    check(problems(r({ target = 'TARGET', conds = { { 'MB_AVAILABLE' } }, action = { 'burstcap', 3 } })) == '', 'burstcap 3 is valid')
    check(has(problems(r({ target = 'TARGET', cond = { 'MB_AVAILABLE' }, action = { 'burstcap', 7 } })), 'highest tier'), 'burstcap 7 is refused')
    check(problems(r({ target = 'PARTY', cond = { 'ERASABLE' }, action = { 'spell', 'ERASE' } })) == '', 'ERASABLE -> Erase is valid')
    check(problems(r({ target = 'ENEMY_ADD', cond = { 'ALWAYS' }, action = { 'family', 'SLEEP' } })) == '', 'ENEMY_ADD -> Sleep is valid')
    check(problems(r({ target = 'PARTY_LOWEST_HPP', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' }, wake = true })) == '',
        'Wake to act is valid')
    check(has(problems(r({ target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' }, wake = 'yes' })), 'true or false'),
        'wake must be a boolean')

    engineOff()
    local why = problems(r({ target = 'TARGET', conds = { { 'MB_AVAILABLE' }, selfMp }, action = { 'burst' } }))
    check(has(why, 'updated map server'), 'an older xi_map: a subject is refused (never run without it): ' .. why)
    check(has(problems(r({ target = 'PARTY', cond = { 'ERASABLE' }, action = { 'spell', 'ERASE' } })), 'updated map server'), '... and ERASABLE')
    check(has(problems(r({ target = 'ENEMY_ADD', cond = { 'ALWAYS' }, action = { 'family', 'SLEEP' } })), 'updated map server'), '... and ENEMY_ADD')
    check(has(problems(r({ target = 'TARGET', cond = { 'MB_AVAILABLE' }, action = { 'burstcap', 3 } })), 'updated map server'), '... and burstcap')
    check(has(problems(r({ target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' }, wake = true })), 'updated map server'), '... and wake')
    check(problems(r({ target = 'PARTY', conds = { { 'HPP_LT', 50 }, { 'MPP_GTE', 10 }, { 'NOT_STATUS', 'SLEEP_I' } }, action = { 'family', 'CURE' } })) == '',
        'three conditions about the target need no new engine (the engine already ANDs any number)')
    engineOn()

    -- the shape: cond / cond2 when it fits, conds when it must
    local rule = R.setConds({ id = 'r1', target = 'PARTY', action = { 'family', 'CURE' } }, { { 'HPP_LT', 50 }, { 'MPP_GTE', 10 } })
    check(rule.cond[1] == 'HPP_LT' and rule.cond2[1] == 'MPP_GTE' and rule.conds == nil, 'two conditions about the target are written as cond / cond2')
    rule = R.setConds({ id = 'r1', target = 'TARGET', action = { 'burst' } }, { { 'MB_AVAILABLE' }, { 'MPP_GTE', 30, of = 'SELF' } })
    check(rule.cond == nil and #rule.conds == 2 and rule.conds[2].of == 'SELF', 'a subject is written as conds')
    check(#R.condList({ cond = { 'HPP_LT', 5 }, cond2 = { 'ALWAYS' } }) == 2 and #R.condList({ conds = { { 'ALWAYS' } } }) == 1, 'condList reads both shapes')
    check(R.subjectId(ai.c.MPP_GTE, 'SELF') == 4 + 0x1000 and R.subjectId(ai.c.HPP_LT, nil) == 1, 'the engine id of a subject')
end

-- ================================================================= the rules the engine gets (squad.lua)
section('squad.lua: what the engine is given')
do
    -- (a stand-in mate: applyRules counts its Wake to act rules in a local var for the Squads menu)
    local lastMob
    local function build(rule)
        gambits = {}
        lastMob = { vars = {} }
        function lastMob:getLocalVar(k) return self.vars[k] or 0 end
        function lastMob:setLocalVar(k, v) self.vars[k] = v end
        builder.applyRules(lastMob, { rule }, false)
        return gambits[1]
    end

    local old = build({ on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, cond2 = { 'MPP_GTE', 10 }, action = { 'family', 'CURE' } })
    check(old and type(old.condition[1]) == 'table' and old.condition[1][1] == ai.c.HPP_LT and old.condition[2][1] == ai.c.MPP_GTE
        and #old.condition == 2, 'an old cond / cond2 rule: the same two conditions as before, about the target')
    local one = build({ on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, action = { 'family', 'CURE' } })
    check(one and one.condition[1] == ai.c.HPP_LT and one.condition[2] == 50, 'one condition: the single { id, arg } form, as before')

    local burst = build({ on = true, target = 'TARGET', conds = { { 'MB_AVAILABLE' }, { 'MPP_GTE', 30, of = 'SELF' } }, action = { 'burstcap', 5 } })
    check(burst and burst.condition[2][1] == ai.c.MPP_GTE + 0x1000 and burst.condition[2][2] == 30, 'Self: MP at least 30% -> MPP_GTE + 0x1000')
    check(burst and burst.action[1] == ai.r.MA and burst.action[2] == ai.s.MB_ELEMENT and burst.action[3] == 5, 'burstcap 5 -> MB_ELEMENT with argument 5')
    local plain = build({ on = true, target = 'TARGET', cond = { 'MB_AVAILABLE' }, action = { 'burst' } })
    check(plain and plain.action[3] == 0, 'a plain burst keeps argument 0 (no cap, as before)')

    local four = build({ on = true, target = 'PARTY', conds = { { 'HPP_LT', 50 }, { 'HPP_LT', 80, of = 'ENEMY' }, { 'MPP_GTE', 20, of = 'SELF' },
        { 'NOT_STATUS', 'SLEEP_I' } }, action = { 'family', 'CURE' } })
    check(four and #four.condition == 4 and four.condition[2][1] == ai.c.HPP_LT + 0x2000 and four.condition[4][1] == ai.c.NOT_STATUS,
        'four conditions, each on its subject, all given to the engine')

    local wake = build({ on = true, target = 'PARTY_LOWEST_HPP', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' }, wake = true })
    check(wake and #wake.condition == 2 and wake.condition[2][1] == ai.c.WAKE, 'Wake to act adds the WAKE marker')
    check(lastMob.vars.SQUAD_WAKE_RULES == 1, 'and counts it for the Squads menu (SQUAD_WAKE_RULES 1)')
    build({ on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, action = { 'family', 'CURE' } })
    check((lastMob.vars.SQUAD_WAKE_RULES or 0) == 0, 'a rule without Wake to act is not counted')

    local add = build({ on = true, target = 'ENEMY_ADD', cond = { 'ALWAYS' }, action = { 'family', 'SLEEP' } })
    check(add and add.target == ai.t.ENEMY_ADD, 'ENEMY_ADD reaches the engine as target 15')

    engineOff()
    check(build({ on = true, target = 'TARGET', conds = { { 'MB_AVAILABLE' }, { 'MPP_GTE', 30, of = 'SELF' } }, action = { 'burst' } }) == nil,
        'an older xi_map: a rule with a subject is left out (it never runs without its condition)')
    check(build({ on = true, target = 'TARGET', cond = { 'MB_AVAILABLE' }, action = { 'burstcap', 3 } }) == nil, '... and a tier cap')
    local w2 = build({ on = true, target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' }, wake = true })
    check(w2 and w2.condition[1] == ai.c.HPP_LT, '... a wake rule runs as a plain rule there (no marker an older engine would read as false)')
    engineOn()

    -- the corrected RDM default: the burst's MP check reads the Red Mage's MP
    local src = readAll(LUA_DIR .. '/squad.lua')
    local rdm = src:match('jobs%[jobIds%.RDM%] =(.-)\njobs%[') or ''
    check(rdm:find('ai.c.MPP_GTE + ai.SUBJECT_STEP * ai.subject.SELF', 1, true) and rdm:find('both(cond(selfMp, 30), cond(ai.c.MB_AVAILABLE, 0))', 1, true),
        'the default RDM burst checks Self MP 30% (with the new engine; the old rule otherwise)')
    check(not rdm:find("family('DISTRACT')", 1, true), 'B7: the default RDM rules no longer ask for Distract')
end

-- ================================================================= the wire (gambits_squad.lua v12)
section('!gsq v12: the long rule form, catm "jmfs", caps')
do
    check(F(run('hello 1')[1])[4] == '12', 'hello: version 12')
    local short = G.encodeRule({ id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, cond2 = { 'MPP_GTE', 10 }, action = { 'family', 'CURE' } }, 1)
    check(short == '1,PARTY,HPP_LT,50,MPP_GTE,10,f,CURE,', 'a rule without new options is written exactly as before: ' .. tostring(short))

    local long = { id = 'r1', on = true, target = 'TARGET', conds = { { 'MB_AVAILABLE' }, { 'MPP_GTE', 30, of = 'SELF' }, { 'HPP_LT', 80, of = 'ENEMY' } },
                   action = { 'burstcap', 5 }, wake = true }
    local wire = G.encodeRule(long, 1)
    check(wire == '1,TARGET,MB_AVAILABLE,,MPP_GTE.S,30,c,5,,,,HPP_LT.E,80,,,w', 'the long form, 16 fields: ' .. tostring(wire))
    local back = wire and G.decodeRule(wire, 1)
    check(back and back.conds and #back.conds == 3 and back.conds[2].of == 'SELF' and back.conds[3].of == 'ENEMY' and back.conds[3][2] == 80
        and back.action[1] == 'burstcap' and back.action[2] == 5 and back.wake == true and problems(back) == '',
        'and back: three conditions, their subjects, the cap and Wake to act, valid')
    check(G.encodeRule(back, 1) == wire, 'encode(decode(x)) == x')
    local plainBack = G.decodeRule('1,PARTY,HPP_LT,50,MPP_GTE,10,f,CURE,,,,,,,,', 1)
    check(plainBack and plainBack.cond and plainBack.conds == nil, '16 fields with nothing new: back to cond / cond2')

    local function refused(text, part, label)
        local r, why = G.decodeRule(text, 1)
        check(r == nil and has(why, part), label .. ': ' .. tostring(why))
    end
    refused('1,PARTY,HPP_LT,50,,,f,CURE,,,,MPP_GTE', 'fields', '12 fields are refused')
    refused('1,PARTY,HPP_LT,50,,,f,CURE,,,,,,,,x', 'unknown flags', 'unknown flags are refused')
    refused('1,PARTY,HPP_LT,50,,,f,CURE,,,,MPP_GTE,10,,,', 'in order', 'a third condition after an empty second is refused')
    refused('1,PARTY,HPP_LT,50,,,f,CURE,,,,,10,,,', 'without a condition', 'a value without a condition is refused')
    refused('1,TARGET,MB_AVAILABLE,,,,c,X,', 'number', 'a burst cap that is not a number is refused')
    local sneaky = G.decodeRule('1,TARGET,MPP_GTE.S,30,,,n,,', 1)
    check(sneaky ~= nil and has(problems(sneaky), 'NAME'), 'a subject in the short form is not read as one: the check refuses the name')

    local function cEntries(lines)
        local out = {}
        for _, l in ipairs(lines) do
            local ff = F(l)
            if ff[3] == 'cat' and (ff[5] == 'c' or ff[5] == 't') then for e in (ff[6] .. ','):gmatch('([^,]+),') do out[e] = true end end
        end
        return out
    end
    local s, f = cEntries(run('catm 2 1 jmfs')), cEntries(run('catm 3 1 jmf'))
    check(s['ERASABLE:n'] and s['ENEMY_ADD'], 'catm "jmfs" offers ERASABLE and ENEMY_ADD')
    check(not f['ERASABLE:n'] and not f['ENEMY_ADD'], 'catm "jmf" (an older editor) does not')
    check(has(G.caps(), 'subj'), 'caps say subj')
    engineOff()
    local off = cEntries(run('catm 4 1 jmfs'))
    check(not off['ERASABLE:n'] and not off['ENEMY_ADD'] and not has(G.caps(), 'subj'), 'an older xi_map: neither offered, no subj')
    engineOn()
end

-- ================================================================= the editor
section('editor: four conditions with subjects, the tier cap, wake, examples')
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local clock = 100
M.init({ now = function() return clock end, queue_command = function() end })
local S = M._S
local function catalogFor(flags)
    local lines = run('catm 30 1' .. (flags and (' ' .. flags) or ''))
    local items, endF = {}, nil
    for _, l in ipairs(lines) do local ff = F(string.sub(l, 1, 150)); if ff[3] == 'end' then endF = ff else items[#items + 1] = ff end end
    return M.parse_catalog(items, endF)
end
do
    S.server = { version = 12, maxRules = 32, maxLine = 120, maxChunks = 64, caps = { live = true, subj = true } }
    local cat = catalogFor('jmfs')
    check(cat ~= nil and cat.conds.ERASABLE ~= nil, 'the v12 catalog parses (ERASABLE)')
    check(M.f22_ready(), 'the editor sees the server can run the long form')

    local row = { on = true, target = 'TARGET', cond = 'MB_AVAILABLE', cond2 = 'MPP_GTE', arg2 = '30', of2 = 'SELF',
                  cond3 = 'HPP_LT', arg3 = '80', of3 = 'ENEMY', kind = 'burstcap', name = '5', wake = true }
    local wire = M.encode_rule(row)
    check(wire == '1,TARGET,MB_AVAILABLE,,MPP_GTE.S,30,c,5,,,,HPP_LT.E,80,,,w', 'the editor writes the same 16 fields as the server: ' .. wire)
    local srvRule = G.decodeRule(wire, 1)
    check(srvRule and problems(srvRule) == '', 'the server reads it and finds it valid')
    local back = M.decode_rule(G.encodeRule(srvRule, 1))
    check(back and back.of2 == 'SELF' and back.of3 == 'ENEMY' and back.cond3 == 'HPP_LT' and back.arg3 == '80' and back.wake == true
        and back.kind == 'burstcap' and back.name == '5', 'and the editor reads the server\'s answer back as it was')
    check(M.check_draft({ name = 'X', job = 'RDM', rules = { row } }, cat) == nil, 'the editor\'s check: valid')
    local plain = { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' }
    check(M.encode_rule(plain) == '1,PARTY,HPP_LT,50,,,f,CURE,', 'a plain row is written as before')
    check(not M.needs_long(plain) and M.needs_long(row), 'needs_long: only rows with new options')

    S.server = { version = 11, maxRules = 32, maxLine = 120, maxChunks = 64, caps = { live = true } }
    check(has(M.check_draft({ name = 'X', job = 'RDM', rules = { row } }, cat), 'server update'),
        'an older server: such a row is refused by the editor\'s check (never sent half)')
    check(M.check_draft({ name = 'X', job = 'RDM', rules = { plain } }, cat) == nil, '... a plain row is still fine')
    S.server = { version = 12, maxRules = 32, maxLine = 120, maxChunks = 64, caps = { live = true, subj = true } }

    -- slots: clearing one moves the later ones up
    local four = { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', cond2 = 'MPP_GTE', arg2 = '10', of2 = 'SELF',
                   cond3 = 'HPP_LT', arg3 = '80', of3 = 'ENEMY', cond4 = 'NOT_STATUS', arg4 = 'SLEEP_I', kind = 'family', name = 'CURE' }
    M.set_condition(four, 2, nil, cat)
    check(four.cond2 == 'HPP_LT' and four.of2 == 'ENEMY' and four.cond3 == 'NOT_STATUS' and four.cond4 == nil and four.of4 == nil,
        'removing condition 2: 3 and 4 move up, nothing is left behind')
    check(#M.cond_pairs(four) == 3, 'three conditions now')
    check(has(M.rule_summary(four, cat), 'its enemy: '), 'the summary says whose condition it is: ' .. M.rule_summary(four, cat))
    check(has(M.rule_short(row, cat), 'Self MP') and has(M.action_text(row), 'at most V'), 'the short line: ' .. M.rule_short(row, cat))

    local keys = {}
    for _, subj in ipairs(M.subjects_for(2, 'PARTY', cat, true, 'SELF')) do keys[subj.key] = true end
    check(keys.MP and not keys.PCOUNT and not keys.PTTANK, 'Self: MP is offered, a count or the party tank is not (they read nobody)')
    keys = {}
    for _, subj in ipairs(M.subjects_for(2, 'PARTY', cat, true, 'ENEMY')) do keys[subj.key] = true end
    check(keys.ENEMY and keys.SKILLCHAIN, 'Its enemy: the enemy-only conditions are offered with any target')

    local exKeys = {}
    for _, ex in ipairs(M.examples_for(cat)) do exKeys[ex.key] = true end
    check(exKeys.acid and exKeys.erase and exKeys.burst and exKeys.sleep and exKeys.lullaby and exKeys.wake, 'every example is offered here')
    local d = { name = 'X', job = 'RDM', rules = { plain } }
    local at = M.add_example(d, 1, 'burst')
    check(at == 2 and #d.rules == 3 and d.rules[2].kind == 'burstcap' and d.rules[2].name == '5' and d.rules[2].of2 == 'SELF'
        and d.rules[3].name == '2' and d.dirty, 'the burst example adds its two rules after the selected one (high cap first)')
    check(M.check_draft(d, cat) == nil, 'and they pass the check')
    at = M.add_example(d, 3, 'acid')
    check(d.rules[4].kind == 'ranged' and d.rules[4].cond == 'NOT_STATUS' and d.rules[4].arg == 'DEFENSE_DOWN', 'Acid Bolts: ranged while Defense Down is missing')
    check(M.check_draft(d, cat) == nil, 'the Acid Bolts example is valid')
    local wakeEx = { name = 'X', job = 'WHM', rules = {} }
    M.add_example(wakeEx, nil, 'wake')
    check(wakeEx.rules[1].wake == true and M.check_draft(wakeEx, cat) == nil, 'the wake example is valid')

    local oldCat = catalogFor('jmf')
    exKeys = {}
    S.server = { version = 11, maxRules = 32, maxLine = 120, maxChunks = 64, caps = { live = true } }
    for _, ex in ipairs(M.examples_for(oldCat)) do exKeys[ex.key] = true end
    check(exKeys.acid and not exKeys.erase and not exKeys.burst and not exKeys.sleep and not exKeys.wake,
        'an older server: only the example it can run (Acid Bolts)')
    S.server = { version = 12, maxRules = 32, maxLine = 120, maxChunks = 64, caps = { live = true, subj = true } }
end

-- ================================================================= share codes
section('share codes: format 1 unchanged, format 2 for the new options')
do
    local C = dofile(ADDON_DIR .. '/share_code.lua')
    local plainSet = { job = 'WHM', name = 'Plain', rules = { { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', cond2 = 'MPP_GTE', arg2 = '10',
        kind = 'family', name = 'CURE' } } }
    local code = C.encode(plainSet)
    check(code and code:sub(1, 3) == 'GS1', 'a set without new options is still a format 1 code: ' .. tostring(code and code:sub(1, 8)))
    if OLD_ADDON then
        local OldC = dofile(OLD_ADDON .. '/share_code.lua')
        check(OldC.encode(plainSet) == code, 'the older Gambits writes the same format 1 code, byte for byte')
        local d = OldC.decode(code)
        check(d and d.rules[1].cond2 == 'MPP_GTE', 'and reads the new one\'s format 1 code')
    end

    local newSet = { job = 'RDM', name = 'Burst', rules = {
        { on = true, target = 'TARGET', cond = 'MB_AVAILABLE', cond2 = 'MPP_GTE', arg2 = '50', of2 = 'SELF', kind = 'burstcap', name = '5' },
        { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', cond2 = 'HPP_LT', arg2 = '80', of2 = 'ENEMY', cond3 = 'MPP_GTE', arg3 = '20',
          of3 = 'SELF', cond4 = 'NOT_STATUS', arg4 = 'SLEEP_I', kind = 'family', name = 'CURE', wake = true },
        { on = true, target = 'ENEMY_ADD', cond = 'ALWAYS', kind = 'family', name = 'SLEEP' } } }
    local code2, why = C.encode(newSet)
    check(code2 and code2:sub(1, 3) == 'GS2', 'new options: a format 2 code ' .. tostring(why or ''))
    local back = code2 and C.decode(code2)
    local r1, r2, r3 = back and back.rules[1], back and back.rules[2], back and back.rules[3]
    check(r1 and r1.kind == 'burstcap' and r1.name == '5' and r1.of2 == 'SELF', 'round trip: the burst cap and Self MP')
    check(r2 and r2.of2 == 'ENEMY' and r2.cond3 == 'MPP_GTE' and r2.of3 == 'SELF' and r2.cond4 == 'NOT_STATUS' and r2.arg4 == 'SLEEP_I' and r2.wake == true
        and r2.of1 == nil, 'round trip: four conditions with their subjects and Wake to act')
    check(r3 and r3.target == 'ENEMY_ADD', 'round trip: ENEMY_ADD')
    if OLD_ADDON then
        local OldC = dofile(OLD_ADDON .. '/share_code.lua')
        local d, owhy = OldC.decode(code2)
        check(d == nil and has(owhy, 'newer Gambits'), 'an older Gambits refuses the format 2 code with "update Gambits": ' .. tostring(owhy))
    end
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
