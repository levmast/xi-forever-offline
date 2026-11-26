-- Gambits v2 M2: stand-in tests for the in-game Rule Set editor (no game, no server, no Ashita).
--   luajit test_gambits_squad.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                 <server>/scripts/enum/job_ability.lua <kit>/addons-src/GambitsV2 <empty work folder>
-- Server side: squad_rulesets_store.lua (writing), gambits_squad.lua (!gsq, w and the streamed x), with the real
-- squad_rulesets.lua checks. Addon side: GambitsV2's squad_editor.lua (codec, packing, sending through transport.lua)
-- with a fake clock. The standalone addon (shell, transport, flows) has its own suite: test_gambitsv2_addon.lua.
-- Files are written only inside the work folder.
local LUA_DIR, GAMBITS, JA_ENUM, ADDON_DIR, WORK = arg[1], arg[2], arg[3], arg[4], arg[5]
assert(LUA_DIR and GAMBITS and JA_ENUM and ADDON_DIR and WORK, 'usage: test_gambits_squad.lua lua-dir gambits.lua job_ability.lua addon-dir work-dir')
package.path = ADDON_DIR .. '/?.lua;' .. package.path
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1; io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local JIT = rawget(_G, 'jit') ~= nil

-- ---------------------------------------------------------------- the server bits the modules need
dofile(GAMBITS)
xi = rawget(_G, 'xi') or {}
xi.magic = { spellFamily = setmetatable({ NONE = 0, CURE = 1, CURAGA = 2, PROTECT = 10, SHELL = 11, REGEN = 40 }, { __index = function() return nil end }),
             spell = setmetatable({}, { __index = function(_, k) return type(k) == 'string' and 1 or nil end }) }
xi.effect = setmetatable({}, { __index = function(_, k) return type(k) == 'string' and string.match(k, '^[A-Z_]+$') and 1 or nil end })
xi.objType = { PC = 1, TRUST = 2 }
dofile(JA_ENUM)
assert(xi.ja.DIVINE_SEAL == 74 and xi.ja.MARTYR == 153)
SquadOwnerMerit = function(owner, meritId) return (SQUAD_TEST_MERITS or {})[meritId] or 0 end

local DATA = 'modules/custom/lua/squad_rulesets_data'
local currentData = nil
package.preload[DATA] = function() if currentData == nil then error("module '" .. DATA .. "' not found") end return currentData end
package.preload['modules/custom/lua/squad_rulesets'] = function() return dofile(LUA_DIR .. '/squad_rulesets.lua') end
package.preload['modules/custom/lua/squad_ability_rules'] = function() return dofile(LUA_DIR .. '/squad_ability_rules.lua') end
package.preload['modules/custom/lua/squad_ja_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_ja_jobs_data.lua') end
package.preload['modules/custom/lua/squad_rulesets_store'] = function() return dofile(LUA_DIR .. '/squad_rulesets_store.lua') end
package.preload['modules/custom/lua/squad_spell_jobs_data'] = function() return dofile(LUA_DIR .. '/squad_spell_jobs_data.lua') end

local R = require('modules/custom/lua/squad_rulesets')
local St = require('modules/custom/lua/squad_rulesets_store')

local function deq(a, b)
    if type(a) ~= type(b) then return false end
    if type(a) ~= 'table' then return a == b end
    for k, v in pairs(a) do if not deq(v, b[k]) then return false end end
    for k in pairs(b) do if a[k] == nil then return false end end
    return true
end

local sep = package.config:sub(1, 1)
local function path(name) return WORK .. sep .. name end
local function readFile(p) local f = io.open(p, 'rb'); if not f then return nil end local t = f:read('*a'); f:close(); return t end
local function writeFile(p, t) local f = assert(io.open(p, 'wb')); f:write(t); f:close() end
local function exists(p) local f = io.open(p, 'rb'); if f then f:close(); return true end return false end
local function clean(p) for _, s in ipairs({ '', '.tmp', '.bak', '.old' }) do os.remove(p .. s) end end

-- the DEV store as it is today: one hand-written set
local MANUAL = {
    format = 'xifo-ruleset-store', version = 1,
    sets = {
        { format = 'xifo-ruleset', version = 1, num = 1, id = 'custom.whm.cure-basics', name = 'WHM - Cure basics', job = 'WHM',
          readonly = false, rules = {
            { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' } },
            { id = 'r2', on = true, target = 'PARTY', cond = { 'HPP_LT', 75 }, action = { 'spell', 'CURE_II' } } } },
    },
}
local function copy(t) return St.loadText('return ' .. St.valueText(t)) end

-- ---------------------------------------------------------------- serialising
section('serialising and revisions')
local text = St.serialize(MANUAL)
local back = St.loadText(text)
check(deq(back, MANUAL), 'a store survives serialise -> load unchanged')
check(St.serialize(back) == text, 'serialising is deterministic')
check(St.rev(MANUAL.sets[1]) == St.rev(back.sets[1]), 'the revision is the same for the same content')
local changed = copy(MANUAL.sets[1]); changed.rules[1].cond[2] = 41
check(St.rev(changed) ~= St.rev(MANUAL.sets[1]), 'any change gives a new revision')
local odd = copy(MANUAL); odd.sets[1].extra = { 'kept', n = 3, ['with space'] = true }; odd.note = 'store field'
check(deq(St.loadText(St.serialize(odd)), odd), 'unknown fields (set and store) survive')
check(not pcall(St.serialize, { sets = { function() end } }), 'a function cannot be saved')
local cyc = {}; cyc.me = cyc
check(not pcall(St.serialize, cyc), 'a table that contains itself cannot be saved')
local esc = copy(MANUAL); esc.sets[1].name = 'a "quoted"\nname\\x'
check(deq(St.loadText(St.serialize(esc)), esc), 'quotes, new lines and backslashes survive')
check(St.loadText('os.exit(1)') == nil and St.loadText('return io') == nil, 'the data file runs without server globals')

-- ---------------------------------------------------------------- reading
section('reading the raw store')
local P = path('squad_rulesets_data.lua')
clean(P)
local raw, how = St.readRaw(P)
check(raw ~= nil and how == 'new' and #raw.sets == 0, 'no file = an empty store')
writeFile(P, 'return { this is not lua')
check(St.readRaw(P) == nil, 'a broken file is refused')
check(St.save({ op = 'save', num = 0, job = 'WHM', name = 'x', rules = {} }, 1, R, P) == nil and readFile(P) == 'return { this is not lua',
      'a broken file is never overwritten by a save')
writeFile(P, 'return { format = "other", version = 1, sets = {} }')
check(St.readRaw(P) == nil, 'a file of another format is refused')

-- ---------------------------------------------------------------- ownership, numbers, revisions
section('editing: ownership, numbers, ids, revisions')
local CURE = { { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 50 }, action = { 'family', 'CURE' } } }
local r0 = copy(MANUAL)
local set, code = St.applyEdit(r0, { op = 'save', num = 0, job = 'WHM', name = 'Mine', rules = copy(CURE) }, 7, R, 1700000000)
check(set and set.num == 2 and set.owner == 7 and set.id == 'user.7.1700000000' and set.readonly == false, 'a new set: lowest free num, owner, id')
local r1 = copy(MANUAL); r1.sets[2] = { num = 2, id = 'broken', rules = 'oops' }
set = St.applyEdit(r1, { op = 'save', num = 0, job = 'WHM', name = 'Mine', rules = copy(CURE) }, 7, R, 1700000000)
check(set and set.num == 3, 'numbers used by sets that do not pass the checks are not given out')
check(r1.sets[2].id == 'broken' and r1.sets[2].rules == 'oops', 'a set that does not pass the checks is kept as it is')
local r2 = copy(MANUAL); r2.sets[2] = { num = 5, id = 'user.7.1700000000' }
set = St.applyEdit(r2, { op = 'save', num = 0, job = 'WHM', name = 'Mine', rules = copy(CURE) }, 7, R, 1700000000)
check(set and set.id == 'user.7.1700000000.2', 'ids are never given twice')
local _, c1 = St.applyEdit(copy(MANUAL), { op = 'save', num = 1, rev = St.rev(MANUAL.sets[1]), job = 'WHM', name = 'x', rules = copy(CURE) }, 7, R)
check(c1 == 'readonly', 'a hand-written set (no owner) cannot be changed in the editor')
local own = copy(MANUAL); own.sets[2] = { format = 'xifo-ruleset', version = 1, num = 2, id = 'user.8.1', owner = 8, name = 'Theirs', job = 'WHM',
                                          readonly = false, rules = copy(CURE) }
local _, c2 = St.applyEdit(copy(own), { op = 'save', num = 2, rev = St.rev(own.sets[2]), job = 'WHM', name = 'x', rules = copy(CURE) }, 7, R)
check(c2 == 'owner', 'another character\'s set cannot be changed')
local _, c3 = St.applyEdit(copy(own), { op = 'delete', num = 2, rev = St.rev(own.sets[2]) }, 7, R)
check(c3 == 'owner', 'another character\'s set cannot be deleted')
local ro = copy(own); ro.sets[2].readonly = true
local _, c4 = St.applyEdit(ro, { op = 'save', num = 2, rev = St.rev(ro.sets[2]), job = 'WHM', name = 'x', rules = copy(CURE) }, 8, R)
check(c4 == 'readonly', 'a read-only set cannot be changed, even by its owner')
local _, c5 = St.applyEdit(copy(own), { op = 'save', num = 2, rev = '123', job = 'WHM', name = 'x', rules = copy(CURE) }, 8, R)
check(c5 == 'stale', 'an edit from an older revision is refused (stale)')
local okEdit = copy(own)
local e6 = St.applyEdit(okEdit, { op = 'save', num = 2, rev = St.rev(own.sets[2]), job = 'WHM', name = 'Renamed', rules = copy(CURE) }, 8, R)
check(e6 and e6.num == 2 and e6.id == 'user.8.1' and e6.owner == 8 and e6.name == 'Renamed', 'the owner\'s edit keeps num, id and owner')
check(deq(okEdit.sets[1], MANUAL.sets[1]), 'editing one set leaves the hand-written set exactly as it was')
local bad = St.applyEdit(copy(MANUAL), { op = 'save', num = 0, job = 'WHM', name = 'Bad',
    rules = { { id = 'r1', on = true, target = 'NOWHERE', cond = { 'HPP_LT', 500 }, action = { 'family', 'CURE' } } } }, 7, R)
local _, c7, why7 = St.applyEdit(copy(MANUAL), { op = 'save', num = 0, job = 'WHM', name = 'Bad',
    rules = { { id = 'r1', on = true, target = 'NOWHERE', cond = { 'HPP_LT', 500 }, action = { 'family', 'CURE' } } } }, 7, R)
check(bad == nil and c7 == 'invalid' and why7:find('unknown target NOWHERE', 1, true) and why7:find('HPP_LT', 1, true), 'M1.1 checks refuse a bad set (target, argument range): ' .. tostring(why7))
local _, c8 = St.applyEdit(copy(MANUAL), { op = 'save', num = 0, job = 'WHM', name = 'Off',
    rules = { { id = 'r1', on = false, target = 'PARTY', cond = { 'HPP_LT', 50 }, action = { 'family', 'CURE' } } } }, 7, R)
check(c8 == 'invalid', 'a set with no rule switched on is refused')
local del = copy(own)
check(St.applyEdit(del, { op = 'delete', num = 2, rev = St.rev(own.sets[2]) }, 8, R) == true and #del.sets == 1 and del.sets[1].num == 1,
      'the owner can delete; other sets stay')

-- ---------------------------------------------------------------- writing and recovery (real files)
section('writing: replace, backup, failures and recovery (real files in the work folder)')
clean(P)
writeFile(P, St.serialize(MANUAL) .. '-- a hand comment\n')
local before = readFile(P)
local okW, howW = St.write(copy(own), P)
check(okW == true, 'write succeeds: ' .. tostring(howW))
check(St.readRaw(P) ~= nil and #St.readRaw(P).sets == 2, 'the new file reads back with both sets')
check(readFile(P .. '.bak') == before, 'the previous file is kept as .bak (with its comment)')
check(not exists(P .. '.tmp') and not exists(P .. '.old'), 'no .tmp or .old is left behind')
if sep == '\\' then
    -- what Windows really does: os.rename onto an existing file fails
    writeFile(path('a.txt'), 'A'); writeFile(path('b.txt'), 'B')
    local renamed = os.rename(path('a.txt'), path('b.txt'))
    check(not renamed and readFile(path('b.txt')) == 'B', 'Windows: os.rename cannot replace an existing file (so a one-step replace or the .old dance is needed)')
    os.remove(path('a.txt')); os.remove(path('b.txt'))
    if JIT then
        check(howW == 'MoveFileEx', 'Windows + LuaJIT: the file was replaced in one step with MoveFileExA (' .. tostring(howW) .. ')')
    else
        check(howW == 'rename via .old', 'Windows without ffi: the .old way was used (' .. tostring(howW) .. ')')
    end
end

-- the fallback way (as without ffi), on purpose
local fallback = {}
for k, v in pairs(St.fs) do fallback[k] = v end
fallback.replace = function() return nil end
writeFile(P, St.serialize(MANUAL))
local okF, howF = St.write(copy(own), P, fallback)
check(okF and howF == 'rename via .old' and #St.readRaw(P).sets == 2 and not exists(P .. '.old'), 'the rename-via-.old way works and cleans up')

local function failing(what)
    local fs = {}
    for k, v in pairs(fallback) do fs[k] = v end
    if what == 'tmp' then
        fs.write = function(p, t) if p:sub(-4) == '.tmp' then return false, 'disk full' end return fallback.write(p, t) end
    elseif what == 'bak' then
        fs.write = function(p, t) if p:sub(-4) == '.bak' then return false, 'no access' end return fallback.write(p, t) end
    elseif what == 'place' then
        fs.rename = function(a, b) if a:sub(-4) == '.tmp' then return false, 'locked' end return fallback.rename(a, b) end
    elseif what == 'aside' then
        fs.rename = function(a, b) if b:sub(-4) == '.old' then return false, 'locked' end return fallback.rename(a, b) end
    elseif what == 'readback' then
        fs.read = function(p) if p:sub(-4) == '.tmp' then return 'garbage' end return fallback.read(p) end
    end
    return fs
end
for _, what in ipairs({ 'tmp', 'bak', 'place', 'aside', 'readback' }) do
    writeFile(P, St.serialize(MANUAL)); os.remove(P .. '.tmp'); os.remove(P .. '.old')
    local known = readFile(P)
    local okX, whyX = St.write(copy(own), P, failing(what))
    check(okX == false and readFile(P) == known and not exists(P .. '.tmp') and not exists(P .. '.old'),
          'a failure (' .. what .. ') leaves the old file exactly as it was: ' .. tostring(whyX))
end

-- crash between the two renames of the fallback: the file is gone, .old is there
writeFile(P .. '.old', St.serialize(MANUAL)); os.remove(P); os.remove(P .. '.tmp')
local rec = St.recover(P)
check(exists(P) and not exists(P .. '.old') and deq(St.readRaw(P), MANUAL) and #rec == 1, 'recover: a missing file comes back from .old')
-- crash after writing .tmp, before anything else (file missing too)
os.remove(P); writeFile(P .. '.tmp', St.serialize(own))
St.recover(P)
check(exists(P) and #St.readRaw(P).sets == 2, 'recover: a good .tmp finishes the save when the file is missing')
-- left-overs next to a good file
writeFile(P .. '.tmp', 'half written'); writeFile(P .. '.old', 'old')
St.recover(P)
check(not exists(P .. '.tmp') and not exists(P .. '.old') and #St.readRaw(P).sets == 2, 'recover: left-over .tmp/.old next to a good file are removed')
-- a bad .tmp never replaces anything
os.remove(P); writeFile(P .. '.tmp', 'return { broken')
St.recover(P)
check(not exists(P), 'recover: a broken .tmp is not promoted')
os.remove(P .. '.tmp')

-- ---------------------------------------------------------------- compatibility with M1.1
section('compatibility: hand-written sets and selections after an editor save')
writeFile(P, St.serialize(MANUAL))
local saved = St.save({ op = 'save', num = 0, job = 'WHM', name = 'My cures', rules = copy(CURE) }, 1, R, P, nil, 1700000100)
check(saved and saved.num == 2, 'St.save writes a new set')
currentData = St.readRaw(P)
local loaded = R.load()
check(#loaded.problems == 0 and #loaded.list == 2, 'squad_rulesets.lua reads the written file without problems')
check(deq(loaded.byNum[1], MANUAL.sets[1]), 'the hand-written set reads back exactly as before')
check(R.idHash(loaded.byNum[1].id) == R.idHash('custom.whm.cure-basics'), 'a selection of set 1 (its id check number) is still valid')
local whmMate = { job = 3, level = 25, subJob = 0, subLevel = 0, owner = {} }
local usable, dropped = R.usableRules(loaded.byNum[2], whmMate)
check(#usable == 1 and #dropped == 0, 'the editor\'s set is used by the M1.1 engine like any other')
check(loaded.byNum[2].owner == 1, 'the owner field is kept and ignored by the M1.1 checks')

-- ---------------------------------------------------------------- the !gsq command
section('!gsq: requests, saves in parts, duplicates, retries, expiry')
St.PATH = P
local G = dofile(LUA_DIR .. '/gambits_squad.lua')
local out = {}
local player = { getID = function() return 1 end, printToPlayer = function(_, line) out[#out + 1] = line end,
                 getPartyWithTrusts = function() return {} end, getCharVar = function() return 0 end }
local function run(line) out = {}; G.handle(player, line); return out end
local function fields(line) return G.splitPlain(line, '|') end
-- version 3 answers: the rules of a get (segments joined), and the catalog's entries per kind
local function getRules(lines)
    local parts = {}
    for _, line in ipairs(lines) do
        local f = fields(line)
        if f[3] == 'rule' then
            local i, seg = tonumber(f[4]), tonumber(f[5]:match('^(%d+)/'))
            parts[i] = parts[i] or {}
            parts[i][seg] = f[6]
        end
    end
    local rules = {}
    for i, p in ipairs(parts) do rules[i] = table.concat(p) end
    return rules
end
local function catLists(lines)
    local lists = {}
    for _, line in ipairs(lines) do
        local f = fields(line)
        if f[3] == 'cat' then
            lists[f[5]] = lists[f[5]] or {}
            for _, e in ipairs(G.splitPlain(f[6], ',')) do lists[f[5]][#lists[f[5]] + 1] = e end
        end
    end
    return lists
end

local o = run('ping 5 77')
check(#o == 1 and o[1]:match('^GSQ|5|pong|77|%d+$'), 'ping answers with its id and the client value: ' .. tostring(o[1]))
o = run('hello 6')
check(o[1] == 'GSQ|6|hello|11|32|120|64|live', 'hello: version 11 (capability words: live, since 10), 32 rules, 120 bytes, 64 chunks: ' .. tostring(o[1]))
o = run('nonsense 7')
check(o[1]:match('^GSQ|7|err|badreq'), 'an unknown request is answered with an error')
o = run(string.rep('x', 200))
check(o[1]:match('err|toolong'), 'an over-long request is refused')

o = run('list 8 WHM')
check(#o == 3 and o[1]:match('^GSQ|8|set|1|WHM|2|m|') and o[2]:match('^GSQ|8|set|2|WHM|1|o|') and o[3] == 'GSQ|8|end|2',
      'list: the hand-written set (m) and your own (o), then end with the count')
player.getID = function() return 2 end
o = run('list 9 WHM')
check(#o == 2 and o[2] == 'GSQ|9|end|1', 'another character does not see your set in the list (only hand-written ones)')
player.getID = function() return 1 end

o = run('get 10 1')
check(o[1]:match('^GSQ|10|hdr|1|WHM|m|%d+|custom.whm.cure%-basics|WHM %- Cure basics$') and o[2] == 'GSQ|10|rule|1|1/1|1,PARTY,HPP_LT,40,,,f,CURE,'
      and o[3] == 'GSQ|10|rule|2|1/1|1,PARTY,HPP_LT,75,,,s,CURE_II,' and o[4] == 'GSQ|10|end|2',
      'get (version 3): header, both rules - the specific spell Cure II too - in one segment each, end')

o = run('cat 11 WHM')
local catKinds = {}
for kind, list in pairs(catLists(o)) do catKinds[kind] = table.concat(list, ',') .. ',' end
check(catKinds.t == 'SELF,PARTY,TANK,CASTER,MELEE,RANGED,TOP_ENMITY,TARGET,MASTER,TRIGGER_SELF_ACTION_TARGET,',
      'catalog: the targets the engine has, in the editor\'s order (version 6: Check Self -> Act on Enemy last)')
check(catKinds.c and catKinds.c:find('HPP_LT:r:0:100', 1, true) and catKinds.c:find('ALWAYS:n', 1, true) and catKinds.c:find('NOT_STATUS:e', 1, true)
      and catKinds.c:find('HPP_GTE:r:0:100', 1, true) and catKinds.c:find('STATUS:e', 1, true) and catKinds.c:find('READYING_WS:n', 1, true),
      'catalog: every condition with its argument kind and range (HPP_LT, HPP_GTE, STATUS, READYING_WS included)')
check(catKinds.f == 'CURE,CURAGA,REGEN,PROTECT,SHELL,', 'catalog: exactly the families the server knows (the test server knows five): ' .. tostring(catKinds.f))
check(catKinds.j and catKinds.j:find('DIVINE_SEAL:15', 1, true) and catKinds.j:find('MARTYR:75', 1, true) and not catKinds.j:find('PROVOKE', 1, true),
      'catalog: WHM job abilities with their level (no WAR ones)')
check(catKinds.s and catKinds.s:find('CURE_II:11,', 1, true) and catKinds.s:find('PARALYNA:9,', 1, true) and not catKinds.s:find('FIRE:', 1, true),
      'catalog: WHM spells with their level (Cure II 11, Paralyna 9; no BLM spells)')
local endF = fields(o[#o])
check(endF[3] == 'end' and tonumber(endF[4]) == #o - 1 and endF[5]:match('^%d+%.%d+%.%d+%.%d+%.%d+$') and tonumber(endF[6]),
      'catalog end: line count, counts per kind, check number: ' .. o[#o])
for _, line in ipairs(o) do check(#line <= 140, 'every catalog line fits 140 bytes (' .. #line .. ')') end

-- a save in two parts, as the addon packs it
local M = dofile(ADDON_DIR .. '/squad_editor.lua')
local draft = { num = 0, job = 'WHM', name = 'Mira cures', rules = {
    { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '50', kind = 'family', name = 'CURE' },
    { on = true, target = 'SELF', cond = 'ALWAYS', kind = 'ja', name = 'DIVINE_SEAL' },
    { on = false, target = 'MASTER', cond = 'HPP_LT', arg = '40', cond2 = 'MPP_GTE', arg2 = '10', kind = 'family', name = 'CURAGA', retry = '30' },
    { on = true, target = 'PARTY', cond = 'NOT_STATUS', arg = 'PROTECT', kind = 'family', name = 'PROTECT' },
    { on = true, target = 'SELF', cond = 'MPP_LT', arg = '20', kind = 'ja', name = 'DEVOTION' } } }
local lines = M.pack_save(draft, '424242')
check(lines and #lines >= 2, 'five rules pack into ' .. tostring(lines and #lines) .. ' lines')
for _, l in ipairs(lines or {}) do check(#l <= 120, 'every save line is at most 120 bytes (' .. #l .. ')') end
local saveCalls = 0
local realSave = G.save
G.save = function(edit, charId) saveCalls = saveCalls + 1; return realSave(edit, charId) end
local function body(l) return (l:gsub('^/say !gsq ', '')) end
o = run(body(lines[1]))
check(o[1] == 'GSQ|424242|ack|1|' .. #lines, 'part 1 is acknowledged')
o = run(body(lines[1]))
check(o[1] == 'GSQ|424242|ack|1|' .. #lines and saveCalls == 0, 'part 1 again (a retry) is acknowledged again; nothing written')
for i = 2, #lines do o = run(body(lines[i])) end
check(o[1]:match('^GSQ|424242|ok|3|%d+|user%.1%.%d+$') and saveCalls == 1, 'the last part saves once: ' .. tostring(o[1]))
local first = o[1]
o = run(body(lines[#lines]))
check(o[1] == first and saveCalls == 1, 'the last part again gets the same answer, without a second write')
currentData = St.readRaw(P)
local s3 = R.load().byNum[3]
check(s3 and s3.name == 'Mira cures' and #s3.rules == 5 and s3.rules[3].on == false and s3.rules[3].retry == 30
      and s3.rules[3].cond2[1] == 'MPP_GTE' and s3.rules[4].cond[2] == 'PROTECT' and s3.rules[2].action[2] == 'DIVINE_SEAL',
      'the saved set has exactly the rows of the editor (on/off, cond2, retry, effect names, job abilities)')
o = run('get 12 3')
local round = {}
for _, text in ipairs(getRules(o)) do round[#round + 1] = M.decode_rule(text) end
check(#round == 5 and round[3].retry == '30' and round[3].on == false and round[5].name == 'DEVOTION', 'get gives back the same rows to the editor')

-- incomplete: parts 1 and 3 of 3, never part 2
saveCalls = 0
local three = M.pack_save({ num = 0, job = 'WHM', name = 'Big', rules = (function() local t = {} for i = 1, 9 do t[i] = draft.rules[1] end return t end)() }, '777')
run(body(three[1]))
if three[3] then o = run(body(three[3])) end
check(#three >= 3 and o[1]:match('|ack|') and saveCalls == 0, 'an unfinished save writes nothing')
G.now = function() return os.time() + 200 end
o = run(body(three[2]))
check(o[1]:match('|ack|2|') and saveCalls == 0, 'after 120 s the unfinished save is gone; a late part starts over')
G.now = os.time
G._drafts[1] = nil

-- announced 2 rules, sent 1
o = run('w 888 1 1 0,-,WHM,2,Short;1,PARTY,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|888|err|incomplete'), 'fewer rules than announced is refused')
o = run('w 889 1 1 0,-,WHM,1,Bad;1,PARTY,HPP_LT,50,,,x,CURE,')
check(o[1]:match('^GSQ|889|err|badreq'), 'an unknown action kind is refused')
o = run('w 890 1 1 0,-,WHM,1,Bad;1,PARTY,HPP_LT,50,,,f,CURE ;')
check(o[1]:match('^GSQ|890|err|badreq'), 'save data with a space is refused (nothing after the data is ignored silently)')
o = run('w 890 1 1 0,-,WHM,1,Bad;1,PARTY,HPP_LT,50,,,f,CU"RE,')
check(o[1]:match('^GSQ|890|err|badreq'), 'a character that is not allowed is refused')
o = run('w 891 1 99 x')
check(o[1]:match('^GSQ|891|err|badreq'), 'more than 16 parts is refused')
o = run('w 892 1 1 0,-,WHM,1,Bad;1,NOWHERE,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|892|err|invalid|.*unknown target NOWHERE'), 'the M1.1 checks run on the server: ' .. tostring(o[1]))
o = run('w 893 1 1 1,' .. St.rev(MANUAL.sets[1]) .. ',WHM,1,Edit;1,PARTY,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|893|err|readonly'), 'saving over the hand-written set is refused (copy instead)')
o = run('w 894 1 1 3,12345,WHM,1,Edit;1,PARTY,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|894|err|stale'), 'a save from an old revision is refused as stale')
player.getID = function() return 2 end
o = run('w 895 1 1 3,' .. St.rev(s3) .. ',WHM,1,Edit;1,PARTY,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|895|err|owner'), 'another character cannot overwrite your set')
o = run('del 896 3 ' .. St.rev(s3))
check(o[1]:match('^GSQ|896|err|owner'), 'another character cannot delete your set')
player.getID = function() return 1 end
o = run('del 897 3 ' .. St.rev(s3))
check(o[1] == 'GSQ|897|ok|3|-|-', 'you can delete your own set')
o = run('del 897 3 ' .. St.rev(s3))
check(o[1] == 'GSQ|897|ok|3|-|-', 'a repeated delete gets the same answer')
currentData = St.readRaw(P)
check(R.load().byNum[3] == nil and deq(R.load().byNum[1], MANUAL.sets[1]), 'after the delete the hand-written set is unchanged')
G.save = realSave

-- ---------------------------------------------------------------- streamed saves (x): 32 rules of the longest valid kind
section('!gsq x: 32 maximum-length rules, interrupted and repeated transfers, size and memory limits')
-- the longest job ability any job's catalog offers, with its job
local longJob, longJa = 'WHM', 'DIVINE_SEAL'
for job in pairs(G.JOBS) do
    for _, v in ipairs(catLists(run('cat 40 ' .. job)).j or {}) do
        local name = v:match('^([%w_]+):')
        if name and #name > #longJa then longJob, longJa = job, name end
    end
end
io.write(string.format('   longest job ability: %s (%s, %d letters)\n', longJa, longJob, #longJa))
-- two conditions with the longest status effects (23 letters), the longest target, a wait of 3600 s
local longRule = { on = true, target = 'MASTER', cond = 'NOT_STATUS', arg = 'TRUST_AURA_MAGIC_ATTACK', cond2 = 'NOT_STATUS',
                   arg2 = 'GEO_MAGIC_EVASION_BOOST', kind = 'ja', name = longJa, retry = '3600' }
local longText = M.encode_rule(longRule)
check(#longText >= 100, 'a maximum-length rule is ' .. #longText .. ' bytes (more than one 120-byte line can carry after the prefix)')
local bigDraft = { num = 0, job = longJob, name = 'Longest rules set name x', rules = {} }
for i = 1, 32 do bigDraft.rules[i] = longRule end
check(M.pack_save(bigDraft, '5550001') == nil, 'the old w packing cannot carry it (the reason for x)')
local xl, xerr = M.pack_stream(bigDraft, '5550001')
local okLens = xl ~= nil
for _, l in ipairs(xl or {}) do okLens = okLens and #l <= 120 end
check(xl and okLens and #xl <= 64, string.format('x packs 32 maximum-length rules into %s lines of at most 120 bytes (limit 64) %s',
    tostring(xl and #xl), tostring(xerr or '')))
saveCalls = 0
G.save = function(edit, charId) saveCalls = saveCalls + 1; return realSave(edit, charId) end
for i = 1, #xl - 1 do
    o = run(body(xl[i]))
    if i == 1 then check(o[1] == 'GSQ|5550001|ack|1|' .. #xl, 'chunk 1 acknowledged') end
end
o = run(body(xl[3]))
check(o[1] == 'GSQ|5550001|ack|3|' .. #xl and saveCalls == 0, 'a repeated chunk (a retry) is acknowledged again; nothing written yet')
o = run(body(xl[#xl]))
check(o[1]:match('^GSQ|5550001|ok|%d+|%d+|user%.1%.%d+$') and saveCalls == 1, 'the last chunk saves once: ' .. tostring(o[1]))
local bigNum = tonumber(o[1]:match('|ok|(%d+)|'))
local bigFirst = o[1]
o = run(body(xl[#xl]))
check(o[1] == bigFirst and saveCalls == 1, 'the last chunk again: the same answer, no second write')
o = run(body(xl[2]))
check(o[1] == bigFirst and saveCalls == 1, 'any chunk of a finished save gets the finished answer')
currentData = St.readRaw(P)
local bigSet = R.load().byNum[bigNum]
check(bigSet and #bigSet.rules == 32 and bigSet.rules[32].cond2[2] == 'GEO_MAGIC_EVASION_BOOST' and bigSet.rules[1].retry == 3600
      and bigSet.rules[17].action[2] == longJa, 'all 32 rules are stored with both conditions, the effect names and the wait')
local back = getRules(run('get 41 ' .. bigNum))
local sameBack = #back == 32
for i = 1, #back do sameBack = sameBack and M.encode_rule(M.decode_rule(back[i])) == longText end
check(sameBack, 'get gives back exactly the encoding the editor sent (the read-back check after an unknown save relies on it)')

-- interrupted: every chunk but the last, then nothing for 2 minutes
saveCalls = 0
local xl2 = M.pack_stream(bigDraft, '5550002')
for i = 1, #xl2 - 1 do run(body(xl2[i])) end
check(G._drafts[1] and G._drafts[1].token == '5550002' and saveCalls == 0, 'an interrupted transfer writes nothing')
G.now = function() return os.time() + 121 end
o = run(body(xl2[#xl2]))
check(o[1] == 'GSQ|5550002|ack|' .. #xl2 .. '|' .. #xl2 and saveCalls == 0,
      'after 120 s without a chunk the transfer is gone: the last chunk alone is only acknowledged (the editor then checks the list)')
G.now = os.time
G._drafts[1] = nil

-- a chunk with other data under the same number, too long, too many, too big in total, w and x mixed
o = run('x 5550003 1 2 0,-,WHM,1,A;1,PARTY,HPP_LT,50,')
o = run('x 5550003 1 2 0,-,WHM,1,B;1,PARTY,HPP_LT,50,')
check(o[1]:match('^GSQ|5550003|err|badreq|chunk 1 arrived twice'), 'the same chunk with different data is refused (and the save dropped)')
o = run('x 5550004 1 2 ' .. string.rep('a', 111))
check(o[1]:match('^GSQ|5550004|err|badreq'), 'a chunk over 110 bytes is refused')
o = run('x 5550005 1 65 a')
check(o[1]:match('^GSQ|5550005|err|badreq'), 'more than 64 chunks is refused')
o = run('x 5550006 1 2 a b')
check(o[1]:match('^GSQ|5550006|err|badreq'), 'a chunk with a space is refused')
o = run('x 5550007 1 2 0,-,WHM,1,A"')
check(o[1]:match('^GSQ|5550007|err|badreq'), 'a chunk with a character that is not allowed is refused')
local refusedAt
for i = 1, 60 do
    o = run('x 5550008 ' .. i .. ' 60 ' .. string.rep('a', 110))
    if o[1]:match('|err|toolong|') then refusedAt = i; break end
end
check(refusedAt == 56 and G._drafts[1] == nil, 'a save over 6144 bytes is refused as soon as it gets there (chunk ' .. tostring(refusedAt) .. ') and dropped')
o = run('w 5550009 1 2 0,-,WHM,1,A')
o = run('x 5550009 2 2 ;1,PARTY,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|5550009|err|badreq|w and x'), 'w and x parts cannot be mixed in one save')
G._drafts[1] = nil

-- version 3: the most complex valid rule (the longest target, two 23-letter effects, the longest spell name, a wait, a
-- level and an explicit 24-character id) - 32 of them still fit one streamed save, and get sends each in segments of
-- at most 140 bytes
local longSpell = 'CURE'
do
    local ok, sp = pcall(dofile, LUA_DIR .. '/squad_spell_jobs_data.lua')
    if ok then for _, row in pairs(sp.spells) do if #row[1] > #longSpell then longSpell = row[1] end end end
end
local complex = {}
for i = 1, 32 do
    complex[i] = { on = i % 2 == 0, target = 'TOP_ENMITY', cond = 'NOT_STATUS', arg = 'TRUST_AURA_MAGIC_ATTACK', cond2 = 'NOT_STATUS',
                   arg2 = 'GEO_MAGIC_EVASION_BOOST', kind = 'spell', name = longSpell, retry = '3600', level = '75',
                   id = string.format('custom-rule-id-number-%02d', i) }
end
local cText = M.encode_rule(complex[1])
check(#cText >= 135, string.format('the most complex valid rule is %d bytes (spell %s, %d letters)', #cText, longSpell, #longSpell))
local cDraft = { num = 0, job = 'WHM', name = 'Most complex rules set x', rules = complex }
local cl, cerr = M.pack_stream(cDraft, '5550011')
local cOk, cBytes = cl ~= nil, 0
for _, l in ipairs(cl or {}) do cOk = cOk and #l <= 120; cBytes = cBytes + #(l:match('^/say !gsq x %d+ %d+ %d+ (.*)$') or '') end
check(cl and cOk and #cl <= 64 and cBytes <= 6144, string.format('32 of them: %s lines of at most 120 bytes (limit 64), %d bytes (limit 6144) %s',
    tostring(cl and #cl), cBytes, tostring(cerr or '')))
saveCalls = 0
G.save = function(edit, charId) saveCalls = saveCalls + 1; return realSave(edit, charId) end
for i = 1, #cl do o = run(body(cl[i])) end
check(o[1]:match('^GSQ|5550011|ok|') and saveCalls == 1, '32 most complex rules are saved once: ' .. tostring(o[1]))
local cNum = tonumber(o[1]:match('|ok|(%d+)|'))
currentData = St.readRaw(P)
local cSet = R.load().byNum[cNum]
check(cSet and cSet.rules[5].id == 'custom-rule-id-number-05' and cSet.rules[5].level == 75 and cSet.rules[5].action[1] == 'spell'
      and cSet.rules[5].action[2] == longSpell and cSet.rules[5].on == false and cSet.rules[6].on == true,
      'stored with their ids, levels, specific spells and on/off')
local cGet = run('get 42 ' .. cNum)
local cMax, cSegs = 0, 0
for _, line in ipairs(cGet) do cMax = math.max(cMax, #line); if line:match('|rule|%d+|2/') then cSegs = cSegs + 1 end end
local cBack = getRules(cGet)
local cSame = #cBack == 32
for i = 1, #cBack do cSame = cSame and cBack[i] == M.encode_rule(complex[i]) end
check(cMax <= 140 and cSegs == 32 and cSame, string.format('get sends each in 2 segments, longest line %d bytes, and they join to exactly the same rules', cMax))
G.save = realSave

-- the codec: every M1.1 rule form the wire can carry comes back exactly; anything else is "?" (never half)
local forms = {
    { id = 'r1', on = true, target = 'PARTY', cond = { 'HPP_LT', 40 }, action = { 'family', 'CURE' } },
    { id = 'r1', on = false, target = 'SELF', cond = { 'ALWAYS' }, action = { 'ja', 'DIVINE_SEAL' }, retry = 30 },
    { id = 'r1', on = true, target = 'TARGET', cond = { 'READYING_MS' }, cond2 = { 'TP_GTE', 1000 }, action = { 'spell', 'FLASH' } },
    { id = 'r1', on = true, target = 'TARGET', cond = { 'ALWAYS' }, action = { 'ranged' } },
    { id = 'r1', on = true, target = 'TARGET', cond = { 'MB_AVAILABLE' }, action = { 'burst' }, level = 40 },
    { id = 'my-nuke', on = true, target = 'TARGET', cond = { 'MPP_GTE', 50 }, action = { 'nuke' } },
}
for n, rule in ipairs(forms) do
    local text = G.encodeRule(rule, 1)
    local back2 = text and G.decodeRule(text, 1)
    check(text and deq(back2, rule), 'codec: form ' .. n .. ' comes back exactly (' .. tostring(text) .. ')')
end
local refused = {
    { 'a { main, sub } argument', { on = true, target = 'SELF', cond = { 'HPP_LT', { main = 40, sub = 30 } }, action = { 'family', 'CURE' } } },
    { 'a flag argument', { on = true, target = 'SELF', cond = { 'STATUS_FLAG', { flag = 'ERASABLE' } }, action = { 'family', 'ERASE' } } },
    { 'an unknown field', { on = true, target = 'SELF', cond = { 'ALWAYS' }, action = { 'family', 'CURE' }, note = 'x' } },
    { 'a fraction', { on = true, target = 'SELF', cond = { 'HPP_LT', 40.5 }, action = { 'family', 'CURE' } } },
    { 'an id over 24 characters', { id = string.rep('x', 25), on = true, target = 'SELF', cond = { 'ALWAYS' }, action = { 'family', 'CURE' } } },
    { 'a name on ranged', { on = true, target = 'TARGET', cond = { 'ALWAYS' }, action = { 'ranged', 'X' } } },
}
for _, case in ipairs(refused) do
    check(G.encodeRule(case[2], 1) == nil, 'codec: ' .. case[1] .. ' is sent as "?" (kept read-only, never half)')
end
check(G.decodeRule('1,PARTY,HPP_LT,40,,,f,CURE', 1) and G.decodeRule('1,PARTY,HPP_LT,40,,,f,CURE,', 1).retry == nil,
      'codec: the version 1/2 forms (8 and 9 fields) are still read')

-- every answer fits 140 bytes: the catalog of every job with every sub job, and the long sets
local longest, worst = 0, ''
for job in pairs(G.JOBS) do
    for _, subName in ipairs((function() local t = { '' } for s in pairs(G.JOBS) do t[#t + 1] = s end return t end)()) do
        for _, line in ipairs(run('cat 99999999 ' .. job .. (subName ~= '' and (' ' .. subName) or ''))) do
            if #line > longest then longest, worst = #line, line end
        end
    end
end
check(longest <= 140, string.format('every catalog line of 18 jobs x 19 sub job choices fits 140 bytes (longest %d)', longest))
for _, line in ipairs(run('list 99999999 WHM')) do check(#line <= 140, 'list line fits 140 bytes (' .. #line .. ')') end
local tooLong = run('chk 5 1 1')
check(#tooLong[1] <= 140, 'an error answer fits 140 bytes')
local cut = {}
G.reply({ printToPlayer = function(_, l) cut[#cut + 1] = l end }, '5', 'set', string.rep('y', 150))
check(cut[1] == 'GSQ|5|err|toolong|an answer did not fit one chat line', 'a data line that would not fit is never cut: it becomes an error')
G.reply({ printToPlayer = function(_, l) cut[#cut + 1] = l end }, '6', 'err', 'invalid', string.rep('z', 200))
check(#cut[2] <= 140 and cut[2]:match('^GSQ|6|err|invalid|z+%.%.%.$'), 'an error\'s reason text is shortened to fit')
-- memory: at most 64 unfinished saves at once (all characters); expired ones are swept
for id = 100, 163 do player.getID = function() return id end; run('x ' .. (6000000 + id) .. ' 1 2 a') end
local count = 0
for _ in pairs(G._drafts) do count = count + 1 end
player.getID = function() return 200 end
o = run('x 6000200 1 2 a')
check(count == 64 and o[1]:match('^GSQ|6000200|err|busy'), '64 unfinished saves in memory; a 65th is refused, not stored')
player.getID = function() return 100 end
o = run('x 6000100 2 2 b')
check(o[1]:match('^GSQ|6000100|') and not o[1]:match('|busy|'), 'a character with an unfinished save can still finish it')
G.now = function() return os.time() + 121 end
player.getID = function() return 200 end
o = run('x 6000201 1 2 a')
count = 0
for _ in pairs(G._drafts) do count = count + 1 end
check(o[1] == 'GSQ|6000201|ack|1|2' and count == 1, 'after 2 minutes the old drafts are swept and a new save starts (' .. count .. ' in memory)')
G.now = os.time
for k in pairs(G._drafts) do G._drafts[k] = nil end
for k in pairs(G._results) do G._results[k] = nil end
player.getID = function() return 1 end
G.save = realSave
-- the old way still works for an old editor: w is unchanged (16 parts)
o = run('w 5550010 1 1 0,-,WHM,1,Old;1,PARTY,HPP_LT,50,,,f,CURE,')
check(o[1]:match('^GSQ|5550010|ok|'), 'w (version 1 editors) still saves: ' .. tostring(o[1]))
currentData = St.readRaw(P)

-- ---------------------------------------------------------------- version 4: one mate's own catalog (catm), mates sub level
section('!gsq v4: mates with the real sub job level; catm = the U13 job abilities and trustutils spells of ONE mate')
-- the REAL levelsFor out of squad.lua (as squad.lua exports it), not a copy
do
    local src = assert(io.open(LUA_DIR .. '/squad.lua', 'rb')):read('*a')
    local a = assert(src:find('local function jobLevel%('))
    local b = assert(src:find('\nxi%.squad%.levelsFor = levelsFor', a), 'squad.lua must export xi.squad.levelsFor')
    xi.squad = xi.squad or {}
    xi.squad.levelsFor = assert((loadstring or load)('local SUB_UNLOCK_LEVEL = ' .. src:match('local SUB_UNLOCK_LEVEL = (%d+)')
        .. '\n' .. src:sub(a, b) .. '\nreturn levelsFor', '=squad.lua levelsFor'))()
end
SQUAD_TEST_SCROLLS, SQUAD_TEST_UNLOCKS, SQUAD_TEST_MERITS = false, {}, {}
squadScrollsOn = function() return SQUAD_TEST_SCROLLS end
GetSquadUnlocks = function() return SQUAD_TEST_UNLOCKS end
local squad = {}
GetSquad = function() return squad end
local playerLevel, playerSupport = 30, false
player.getMainLvl = function() return playerLevel end
player.hasJob = function() return playerSupport end
local function mateOf(slot, mjob, mlvl, sjob, jobs)
    local m = { slot = slot, id = 100 + slot, name = 'Mate' .. slot, mjob = mjob, sjob = sjob or 0, jobs = { [mjob] = { level = mlvl } } }
    for j, l in pairs(jobs or {}) do m.jobs[j] = { level = l } end
    return m
end
local function catm(slot)
    local lines = run('catm 70 ' .. slot)
    local items, endF = {}, nil
    for _, l in ipairs(lines) do
        local f = fields(string.sub(l, 1, 150)) -- (as the game delivers it)
        if f[3] == 'end' then endF = f else items[#items + 1] = f end
    end
    local c, why = M.parse_catalog(items, endF)
    local out = { cat = c, why = why, lines = lines, ja = {}, sp = {}, un = {} }
    for _, e in ipairs(c and c.jas or {}) do out.ja[e.name] = e end
    for _, e in ipairs(c and c.spells or {}) do out.sp[e.name] = e end
    for _, e in ipairs(c and c.unconfirmed or {}) do out.un[e.name] = e end
    return out
end
local function count(t) local n = 0 for _ in pairs(t) do n = n + 1 end return n end

-- Mira WHM25 / WAR (her own WAR level 30): sub level min(30, floor(25/2)) = 12
squad = { mateOf(1, 3, 25, 1, { [1] = 30 }) }
o = run('mates 71')
check(o[1] == 'GSQ|71|mate|1|101|Mate1|WHM|25|WAR|0|0|12|off|-|0|0|0', 'mates: WHM 25 / WAR 12 (field 12 = the sub job level; 13-17 = the live state, version 10): ' .. tostring(o[1]))
local mira = catm(1)
check(mira.cat and mira.cat.perMate, 'catm is a complete, verified one-mate catalog (6 kinds): ' .. tostring(mira.why))
check(mira.ja.PROVOKE and mira.ja.PROVOKE.sub and mira.ja.PROVOKE.level == 5, 'WHM25/WAR12: Provoke from the sub job (level 5)')
for _, no in ipairs({ 'BERSERK', 'DEFENDER', 'WARCRY', 'AGGRESSOR', 'RETALIATION', 'TOMAHAWK', 'WARRIORS_CHARGE', 'MIGHTY_STRIKES', 'RESTRAINT' }) do
    check(mira.ja[no] == nil, 'WHM25/WAR12: no ' .. no)
end
check(mira.ja.DIVINE_SEAL and mira.ja.BENEDICTION and not mira.ja.MARTYR and not mira.ja.DEVOTION and not mira.ja.AFFLATUS_SOLACE
      and not mira.ja.AFFLATUS_MISERY and not mira.ja.ASYLUM, 'WHM25 main: Divine Seal, Benediction; no Martyr, Devotion, Afflatus or Asylum')
check(count(mira.ja) == 3, 'exactly three job abilities: ' .. table.concat((function() local t = {} for k in pairs(mira.ja) do t[#t + 1] = k end table.sort(t) return t end)(), ', '))
check(mira.sp.CURE and mira.sp.CURE_II and mira.sp.CURE_III and not mira.sp.CURE_IV, 'spells up to level 25 (Cure III yes, Cure IV no)')
check(mira.sp.DIAGA_II == nil and mira.un.DIAGA_II == nil, 'Diaga II (no scroll item: a monster version) is not offered at all')
local trustIn = false
for name in pairs(mira.sp) do if name == 'SHANTOTTO' or name == 'KUPIPI' or name == 'NAJI' then trustIn = true end end
check(not trustIn, 'no Trust spells')
check(mira.sp.SILENA and mira.sp.SILENA.level == 19 and count(mira.un) == 0, 'spells from scrolls off: Silena (19) is had; nothing unconfirmed')
for _, l in ipairs(mira.lines) do check(#l <= 140, 'every catm line fits 140 bytes (' .. #l .. ')') end
-- the scroll option: from 18 only learned spells
SQUAD_TEST_SCROLLS = true
local scr = catm(1)
check(scr.sp.CURE_II and scr.sp.PROTECT and not scr.sp.SILENA and scr.un.SILENA and not scr.sp.CURE_III and scr.un.CURE_III,
      'spells from scrolls on: below 18 had (Cure II, Protect); Silena 19 and Cure III 21 only unconfirmed (not learned)')
SQUAD_TEST_UNLOCKS = { [60000 + 17] = true }  -- Silena (spell 17) learned
scr = catm(1)
check(scr.sp.SILENA and not scr.un.SILENA and scr.un.CURE_III, 'after the squad learned Silena (unlock 60017) it is had; Cure III still not')
SQUAD_TEST_SCROLLS, SQUAD_TEST_UNLOCKS = false, {}
-- sub level from the mate's own (lower) WAR level
squad = { mateOf(1, 3, 25, 1, { [1] = 8 }) }
check(run('mates 72')[1]:match('|WAR|0|0|8|off|%-|0|0|0$'), 'WHM25 with its own WAR at 8: sub level 8')
check(catm(1).ja.PROVOKE, 'Provoke (5) still from WAR 8')
squad = { mateOf(1, 3, 25, 1, { [1] = 4 }) }
check(catm(1).ja.PROVOKE == nil, 'WAR at 4: no Provoke (level 5)')
-- the sub job unlock (squad.lua SUB_UNLOCK_LEVEL 18)
squad = { mateOf(1, 3, 17, 1, { [1] = 10 }) }
playerLevel, playerSupport = 10, false
check(run('mates 73')[1]:match('|WHM|17|%-|0|0|%-|off|%-|0|0|0$'), 'WHM17, no unlock: no sub job (-) and no sub level')
check(catm(1).ja.PROVOKE == nil, 'and no WAR abilities')
playerLevel = 30
check(run('mates 74')[1]:match('|WHM|17|WAR|0|0|8|off|%-|0|0|0$'), 'WHM17 with a player of level 30 (support jobs): WAR 8 (min(10, 17/2))')
squad = { mateOf(1, 3, 17, 1, { [1] = 30 }) }
playerLevel = 10
check(run('mates 74')[1]:match('|WHM|17|WAR|0|0|8|off|%-|0|0|0$'), 'WHM17 whose own WAR is 30 (one of its jobs at 18+ unlocks it): WAR 8')
playerLevel = 10
squad = { mateOf(1, 3, 17, 4, { [4] = 20 }) }
check(run('mates 75')[1]:match('|WHM|17|BLM|0|0|8|off|%-|0|0|0$'), 'WHM17 whose own BLM is 20 (a job of 18+ unlocks it): BLM 8')
-- main-only and sub job abilities: RDM50 / WHM (own 40 -> sub 25)
squad = { mateOf(1, 5, 50, 3, { [3] = 40 }) }
local rdm = catm(1)
check(rdm.ja.COMPOSURE and rdm.ja.CONVERT and rdm.ja.CHAINSPELL, 'RDM50 main: Composure (main only, 50), Convert (40), Chainspell (two-hour)')
check(rdm.ja.DIVINE_SEAL and rdm.ja.DIVINE_SEAL.sub and not rdm.ja.AFFLATUS_SOLACE and not rdm.ja.BENEDICTION,
      'WHM25 as sub: Divine Seal yes; Afflatus (main only) and Benediction (two-hour) no')
check(rdm.sp.CURE_IV and rdm.sp.CURE_IV.level == 48 and not rdm.sp.CURE_IV.sub and rdm.sp.PARALYNA and rdm.sp.PARALYNA.sub
      and not rdm.sp.CURE_V, 'RDM50/WHM25 spells: Cure IV (RDM 48, main), Paralyna (WHM 9, sub only); no Cure V (WHM 61)')
-- merits: WHM75, Martyr (merit 2176) only with the owner's merit
squad = { mateOf(1, 3, 75) }
SQUAD_TEST_MERITS = {}
check(catm(1).ja.MARTYR == nil, 'WHM75 without the owner\'s Martyr merit: no Martyr')
SQUAD_TEST_MERITS = { [2176] = 1 }
local w75 = catm(1)
check(w75.ja.MARTYR and not w75.ja.DEVOTION and w75.ja.AFFLATUS_SOLACE, 'with merit 2176: Martyr (and still no Devotion); Afflatus as main 40+')
SQUAD_TEST_MERITS = {}
local savedMerit = SquadOwnerMerit
SquadOwnerMerit = nil
check(catm(1).ja.MARTYR == nil, 'without SquadOwnerMerit (server not rebuilt): merit abilities fail closed')
SquadOwnerMerit = savedMerit
-- PLD40 / WAR (own 30 -> 20)
squad = { mateOf(1, 7, 40, 1, { [1] = 30 }) }
local pld = catm(1)
check(pld.ja.PROVOKE and pld.ja.BERSERK and not pld.ja.DEFENDER and pld.ja.SENTINEL and pld.ja.COVER and not pld.ja.RAMPART,
      'PLD40/WAR20: Provoke, Berserk (15); no Defender (25); Sentinel (30), Cover (35); no Rampart (62)')
-- BLU spells are not confirmed (the set is chosen when called); a BLU-less mate never gets them
squad = { mateOf(1, 16, 30) }
local blu = catm(1)
check(next(blu.un) ~= nil and next(blu.sp) == nil, 'BLU30: blue magic only as unconfirmed (its set is chosen when it is called), none offered')
squad = { mateOf(1, 3, 30) }
check(next(catm(1).un) == nil, 'a WHM (no BLU main or sub) gets no blue magic at all')
-- Level Sync: the catalog uses the NORMAL levels (the player synced to 10 changes nothing)
squad = { mateOf(1, 3, 25, 1, { [1] = 30 }) }
playerLevel = 10
local synced = catm(1)
check(deq(synced.ja, mira.ja) and deq(synced.sp, mira.sp), 'Level Sync (player at 10): the same choices as WHM25/WAR12')
-- Check uses the live (synced) mate and says at which levels
local liveMate = { getObjType = function() return xi.objType.TRUST end, getLocalVar = function(_, k) return k == 'SQUAD_ID' and 101 or 0 end,
                   getMainJob = function() return 3 end, getMainLvl = function() return 10 end, getSubJob = function() return 1 end,
                   getSubLvl = function() return 5 end }
player.getPartyWithTrusts = function() return { liveMate } end
currentData = St.readRaw(P)
local anySet = next(R.load().byNum)
o = run('chk 76 1 ' .. tostring(anySet))
check(o[#o]:match('^GSQ|76|end|%d+|10|WAR|5$'), 'chk ends with the levels it checked at (the synced WHM 10 / WAR 5): ' .. tostring(o[#o]))
player.getPartyWithTrusts = function() return {} end
-- the old cat is unchanged for older editors (the whole job list)
local legacy = {}
for kind, list in pairs(catLists(run('cat 77 WHM WAR'))) do legacy[kind] = table.concat(list, ',') .. ',' end
check(legacy.j:find('MIGHTY_STRIKES:0s', 1, true) and legacy.j:find('BERSERK:15s', 1, true), 'legacy cat: unchanged (the whole WHM + WAR list)')
-- errors
check(run('catm 78')[1]:match('^GSQ|78|err|badreq'), 'catm without a slot: refused')
check(run('catm 79 9')[1]:match('^GSQ|79|err|missing'), 'catm for an empty slot: refused')
local realLF = xi.squad.levelsFor
xi.squad.levelsFor = nil
check(run('catm 80 1')[1]:match('^GSQ|80|err|server|.*levelsFor'), 'catm on a server whose squad.lua lacks xi.squad.levelsFor: refused, not guessed')
check(run('mates 81')[1]:match('|WAR|0|0|%-|off|%-|0|0|0$'), 'and mates then says the sub level is not known (-)')
xi.squad.levelsFor = realLF
-- every catm line of every job x sub job fits
local worst = 0
for j = 1, 18 do
    for sj = 0, 18 do
        squad = { mateOf(1, j, 75, sj ~= j and sj or 0, sj ~= 0 and { [sj] = 75 } or nil) }
        for _, l in ipairs(run('catm 99999999 1')) do worst = math.max(worst, #l) end
    end
end
check(worst <= 140, 'every catm line of 18 jobs x 19 sub job choices at level 75 fits 140 bytes (longest ' .. worst .. ')')
squad, playerLevel = {}, 30

-- ---------------------------------------------------------------- (version 7) party roles: prl / prs
section('!gsq v7: party roles - prl (you, your mates, the rest of the party read-only), prs (your own squad only, read back)')
do
    package.loaded['modules/custom/lua/squad_jobs'] = nil
    check(run('prl 300')[1]:match('^GSQ|300|err|server'), 'prl on a server without squad_jobs.lua: refused (err server), nothing guessed')
    check(run('prs 301 0 1')[1]:match('^GSQ|301|err|server'), 'prs on a server without squad_jobs.lua: refused, nothing written')
    package.preload['modules/custom/lua/squad_jobs'] = function() return dofile(LUA_DIR .. '/squad_jobs.lua') end
    local cv, lv = {}, {}
    local saved = { player.getCharVar, player.setCharVar, player.getLocalVar, player.setLocalVar, player.getMainJob, player.getName,
                    player.getObjType, player.getPartyWithTrusts }
    player.getCharVar = function(_, k) return cv[k] or 0 end
    player.setCharVar = function(_, k, v) cv[k] = (v ~= 0) and v or nil end
    player.getLocalVar = function(_, k) return lv[k] or 0 end
    player.setLocalVar = function(_, k, v) lv[k] = v end
    player.getMainJob = function() return 3 end -- you: WHM 30
    player.getName = function() return 'Testcharone' end
    player.getObjType = function() return xi.objType.PC end
    local function member(o)
        local e = { vars = { SQUAD_ID = o.squadId or 0, SQUAD_ROLE = o.role or 0 } }
        function e:getID() return o.id end
        function e:getObjType() return o.pc and xi.objType.PC or xi.objType.TRUST end
        function e:getMainJob() return o.job end
        function e:getMaster() return o.master end
        function e:getName() return o.name end
        function e:getPacketName() return o.name end
        function e:getLocalVar(k) return self.vars[k] or 0 end
        function e:setLocalVar(k, v) self.vars[k] = v end
        return e
    end
    -- your squad: Aldric WAR 20 (out), Lyra WHM 30 (out), Hild PLD 30 (not out)
    squad = { { slot = 1, id = 101, name = 'Aldric', mjob = 1, sjob = 0, jobs = { [1] = { level = 20 } } },
              { slot = 2, id = 102, name = 'Lyra', mjob = 3, sjob = 0, jobs = { [3] = { level = 30 } } },
              { slot = 3, id = 103, name = 'Hild', mjob = 7, sjob = 0, jobs = { [7] = { level = 30 } } } }
    local aldric = member({ id = 5001, squadId = 101, job = 1, master = player, name = 'Aldric' })
    local lyra = member({ id = 5002, squadId = 102, job = 3, master = player, name = 'Lyra' })
    -- a dualbox character (PLD) in the party, and ITS squad mate - with the same SQUAD_ID as Aldric (another master)
    local dual = member({ id = 2, pc = true, job = 7, name = 'Dualpld' })
    local dualMate = member({ id = 5003, squadId = 101, job = 1, master = dual, name = 'Dualwar' })
    local partyNow = { player, aldric, lyra, dual, dualMate }
    player.getPartyWithTrusts = function() return partyNow end

    local function prLines(lines)
        local pr, pm, endF = {}, {}, nil
        for _, l in ipairs(lines) do
            local f = fields(l)
            if f[3] == 'pr' then pr[tonumber(f[4])] = f elseif f[3] == 'pm' then pm[f[4]] = f elseif f[3] == 'end' then endF = f end
        end
        return pr, pm, endF
    end
    local o7 = run('prl 302')
    local pr, pm, endF = prLines(o7)
    check(o7[1] == 'GSQ|302|pr|0|Testcharone|WHM|30|0|C|1|0', 'prl: you first (who 0), WHM 30, auto, by job Mage (C), live 0: ' .. tostring(o7[1]))
    check(o7[2] == 'GSQ|302|pr|1|Aldric|WAR|20|0|M|1|0' and o7[3] == 'GSQ|302|pr|2|Lyra|WHM|30|0|C|1|0'
          and o7[4] == 'GSQ|302|pr|3|Hild|PLD|30|0|TM|0|-', 'prl: your mates in slot order; WAR = M only (not a Tank), PLD = TM (Tank and Melee), not out = live -: '
          .. tostring(o7[2]) .. ' / ' .. tostring(o7[4]))
    check(pm.Dualpld and pm.Dualpld[5] == 'PLD' and pm.Dualpld[6] == 'p' and pm.Dualpld[7] == 'TM'
          and pm.Dualwar and pm.Dualwar[6] == 't' and pm.Dualwar[7] == 'M', 'prl: the dualbox character (p, PLD = TM) and its mate (t) are listed read-only')
    check(endF and tonumber(endF[4]) == 6 and #o7 == 7, 'prl: end counts the pr and pm lines (4 + 2)')
    for _, l in ipairs(o7) do check(#l <= 140, 'prl line fits 140 bytes (' .. #l .. ')') end

    -- prs: Aldric (out) -> tank, at once, read back; the dualbox mate with the same SQUAD_ID is NOT touched
    local o8 = run('prs 303 1 1')
    check(o8[1] == 'GSQ|303|pr|1|Aldric|WAR|20|1|M|1|1' and o8[2] == 'GSQ|303|end|1', 'prs 1 1: Aldric tank, stored and live at once (read back): ' .. tostring(o8[1]))
    check(cv.SQUAD_PROLE_101 == 1 and aldric:getLocalVar('SQUAD_ROLE') == 1 and dualMate:getLocalVar('SQUAD_ROLE') == 0,
          'only YOUR Aldric got the role live; the dualbox character\'s mate with the same SQUAD_ID did not')
    check(table.concat(run('prs 304 1 1'), '|') == table.concat(o8, '|'):gsub('303', '304'), 'prs is idempotent: the same answer again')
    -- not out: stored only
    local o9 = run('prs 305 3 3')
    check(o9[1] == 'GSQ|305|pr|3|Hild|PLD|30|3|TM|0|-' and cv.SQUAD_PROLE_103 == 3, 'prs 3 3: Hild (not out) mage, stored; live - (applies when called)')
    -- you
    local o10 = run('prs 306 0 4')
    check(o10[1] == 'GSQ|306|pr|0|Testcharone|WHM|30|4|C|1|4' and cv.SQUAD_PROLE_ME == 4 and lv.SQUAD_ROLE == 4, 'prs 0 4: you ranged, stored and live')
    -- back to auto, for a mate that is out
    local o11 = run('prs 307 1 0')
    check(o11[1] == 'GSQ|307|pr|1|Aldric|WAR|20|0|M|1|0' and cv.SQUAD_PROLE_101 == nil and aldric:getLocalVar('SQUAD_ROLE') == 0,
          'prs 1 0: Aldric back to auto - the stored role cleared AND the live one 0 at once')
    -- bad input: nothing written
    local before = {}
    for k, v in pairs(cv) do before[k] = v end
    for i, req in ipairs({ 'prs 310 9 1', 'prs 311 1 5', 'prs 312 1 -1', 'prs 313 1 1.5', 'prs 314 1', 'prs 315 x 1', 'prs 316 1 1 extra',
                           'prs 317 4 1' }) do
        local ans = run(req)[1] or ''
        local want = (req == 'prs 310 9 1' or req == 'prs 317 4 1') and 'missing' or 'badreq'
        check(ans:match('^GSQ|31%d|err|' .. want), string.format('"%s": err %s - %s', req, want, ans))
    end
    check(deq(cv, before) and aldric:getLocalVar('SQUAD_ROLE') == 0, 'after every refused prs nothing was written')
    -- a slot of the dualbox character's squad is not yours: "prs 4" (no slot 4 in YOUR squad) was refused above
    -- the summary data: the dualbox mate's live role is reported as the engine sees it
    dualMate:setLocalVar('SQUAD_ROLE', 1)
    local _, pm2 = prLines(run('prl 318'))
    check(pm2.Dualwar and pm2.Dualwar[7] == 'T', 'prl: a party member with a role set on its own character counts as that (T), as the engine sees it')
    -- long names fit
    squad[1].name = 'Abcdefghijklmno'
    for _, l in ipairs(run('prl 319')) do check(#l <= 140, 'prl with a 15-character name fits 140 bytes (' .. #l .. ')') end
    squad[1].name = 'Aldric'
    -- the other requests do not know party roles: mates is unchanged
    check(run('mates 320')[1] == 'GSQ|320|mate|1|101|Aldric|WAR|20|-|0|1|-|unknown|-|0|0|0', 'mates fields 1-12 are unchanged by v7 (13-17: the live state, version 10): ' .. tostring(run('mates 320')[1]))
    player.getCharVar, player.setCharVar, player.getLocalVar, player.setLocalVar, player.getMainJob, player.getName, player.getObjType,
        player.getPartyWithTrusts = (table.unpack or unpack)(saved, 1, 8)
    squad = {}
end
-- ---------------------------------------------------------------- addon: packing, local checks, the send queue
section('addon: packing sizes, local checks, acknowledged sending with a fake clock')
local function rules(n) local t = {} for i = 1, n do t[i] = draft.rules[(i - 1) % #draft.rules + 1] end return t end
for _, n in ipairs({ 5, 15, 32 }) do
    local ls = M.pack_save({ num = 0, job = 'WHM', name = 'Size test', rules = rules(n) }, '1234567890')
    local okLen = true
    for _, l in ipairs(ls) do okLen = okLen and #l <= 120 end
    check(ls and okLen, string.format('%d rules -> %d lines, all at most 120 bytes', n, #ls))
    io.write(string.format('   %d rules: %d lines\n', n, #ls))
end
local cat = { conds = { HPP_LT = { kind = 'r', lo = 0, hi = 100 }, ALWAYS = { kind = 'n' }, NOT_STATUS = { kind = 'e' }, MPP_GTE = { kind = 'r', lo = 0, hi = 100 }, MPP_LT = { kind = 'r', lo = 0, hi = 100 } } }
check(M.check_draft(draft, cat) == nil, 'the example draft passes the local checks')
check(M.check_draft({ name = 'x', rules = { { on = true, target = 'PARTY', cond = 'HPP_LT', arg = '500', kind = 'family', name = 'CURE' } } }, cat):find('0%-100'),
      'a number out of range is caught before sending')
check(M.check_draft({ name = 'bad|name', rules = draft.rules }, cat) ~= nil, 'a name with a | is caught')
check(M.check_draft({ name = 'x', rules = { { on = false, target = 'PARTY', cond = 'ALWAYS', kind = 'family', name = 'CURE' } } }, cat) ~= nil,
      'no rule switched on is caught')

local clock, sent = 100, {}
M.init({ now = function() return clock end, queue_command = function(l) sent[#sent + 1] = { l, clock } end })
local S = M._S
local results2 = {}
local id1 = 'job1'
M.enqueue({ id = id1, lines = { 'L1', 'L2' }, on_line = function(f) if f[3] == 'ack' then return 'next' end end,
            on_done = function() results2[#results2 + 1] = 'done1' end, on_fail = function(w) results2[#results2 + 1] = 'fail1 ' .. w end })
M.enqueue({ id = 'job2', lines = { 'L3' }, on_line = function(f) if f[3] == 'pong' then return 'done' end end,
            on_done = function() results2[#results2 + 1] = 'done2' end, on_fail = function(w) results2[#results2 + 1] = 'fail2' end })
check(M.busy(), 'busy while requests wait')
M.tick()
check(#sent == 1 and sent[1][1] == 'L1', 'the first line goes out')
check(M.owns_command('L1') and not M.owns_command('/say hello'), 'the editor knows its own lines from player chat')
clock = clock + 0.05; M.tick()
check(#sent == 1, 'nothing more is sent before the answer')
M.on_reply({ 'GSQ', 'other', 'ack' }); clock = clock + 1.0; M.tick()
check(#sent == 1, 'an answer for another request is ignored')
M.on_reply({ 'GSQ', id1, 'ack', '1' }); M.tick()
check(#sent == 2 and sent[2][1] == 'L2' and sent[2][2] - sent[1][2] >= 1.0, 'the next line goes out after the answer, at least 1.0 s later')
M.on_reply({ 'GSQ', id1, 'ack', '2' })
M.tick()
clock = clock + 1.0; M.tick()
check(results2[1] == 'done1' and sent[3] and sent[3][1] == 'L3', 'job 1 done, job 2 starts')
clock = clock + 2.9; M.tick()
check(#sent == 3, 'no resend before the 3 s timeout')
clock = clock + 0.2; M.tick()
check(#sent == 4 and sent[4][1] == 'L3', 'without an answer the (idempotent) line is sent again after the timeout')
clock = clock + 3.1; M.tick()
check(#sent == 5, 'and a second time')
clock = clock + 3.1; M.tick()
check(results2[#results2] == 'fail2' and not M.busy(), 'after two resends the request fails and the queue is free')
check(M.text_in('GSQ|nobody|pong|1|2') == true and M.text_in('Hello there') == false, 'GSQ answers are hidden, chat is not')
check(M.enqueue({ id = 'x', lines = { string.rep('y', 121) }, on_fail = function() end }) == false, 'a line over 120 bytes is never queued')

-- a save through the real editor code: an answer to an earlier copy of part 1 must not move the save on
sent = {}
local saveDraft = { num = 0, job = 'WHM', name = 'Queue test', rules = rules(12) }
M._S.draft, M._S.cat = saveDraft, { conds = cat.conds }
M._S.server = { version = 2, maxChunks = 48 }
M.save(); clock = clock + 1.0; M.tick()
check(#sent == 0 and M._S.messageOk == false and M._S.message:find('needs the update', 1, true),
      'an older server (version 2) is not written to: the editor says it needs the update - ' .. tostring(M._S.message))
M._S.server = { version = 3, maxChunks = 64 }
M.save()
clock = clock + 1.0; M.tick()
local token = sent[1][1]:match('^/say !gsq x (%d+) 1 ')
local total = tonumber(sent[1][1]:match('^/say !gsq x %d+ 1 (%d+) '))
check(token and total and total >= 2, 'M.save (version 3 server) streams part 1 of ' .. tostring(total))
M.on_reply({ 'GSQ', token, 'ack', '1', tostring(total) }); clock = clock + 1.0; M.tick()
check(#sent == 2 and sent[2][1]:match(' 2 ' .. total .. ' '), 'after the answer to part 1 comes part 2')
M.on_reply({ 'GSQ', token, 'ack', '1', tostring(total) }); clock = clock + 1.0; M.tick()
check(#sent == 2, 'a late duplicate answer to part 1 does not move the save on')
for seq = 2, total - 1 do M.on_reply({ 'GSQ', token, 'ack', tostring(seq), tostring(total) }); clock = clock + 1.0; M.tick() end
M.on_reply({ 'GSQ', token, 'err', 'invalid', 'rule 3: unknown target' })
check(not M.busy() and M._S.draft == saveDraft and #saveDraft.rules == 12 and M._S.messageOk == false,
      'a refused save keeps every row of the draft and shows the error')

-- ---------------------------------------------------------------- addon: readable names, summaries, local list edits
section('addon: readable names and rule summaries (what players see)')
check(M.pretty('CURE_II') == 'Cure II' and M.pretty('DIVINE_SEAL') == 'Divine Seal' and M.pretty('CURE') == 'Cure', 'names read like the game: Cure II, Divine Seal')
check(M.target_label('PARTY') == 'Party member' and M.target_label('SELF') == 'Self' and M.target_label('TARGET') == 'Enemy (current target)'
      and M.target_label('MASTER'):find('Master', 1, true) and M.target_label('TANK') == 'Tank' and M.target_label('CASTER') == 'Mage'
      and M.target_label('MELEE') == 'Melee' and M.target_label('RANGED') == 'Ranged',
      'targets: Self, Party member, Tank, Mage, Melee, Ranged, Enemy (current target), Master')
for _, t in ipairs({ 'SELF', 'PARTY', 'TANK', 'CASTER', 'MELEE', 'RANGED', 'TOP_ENMITY', 'TARGET', 'MASTER' }) do
    check(M.TARGET_HELP[t] ~= nil, 'target ' .. t .. ' has a tooltip saying what the engine does')
end
for _, k in ipairs(M.NEW_KINDS) do check(k ~= 'ws' and M.KIND_LABELS[k], 'new rules offer ' .. M.KIND_LABELS[k] .. ' (no weapon skill)') end
check(M.kind_label('family') == 'Best of Family' and M.kind_label('ja') == 'Job Ability', 'actions: Best of Family, Job Ability')
check(M.cond_label('HPP_LT') == 'HP below' and M.cond_label('ALWAYS') == 'Always', 'conditions: HP below, Always')
check(M.cond_text('HPP_LT', '50') == 'HP below 50%' and M.cond_text('NOT_STATUS', 'PROTECT') == 'Missing effect Protect'
      and M.cond_text('TIMER', '30') == 'Every 30 s' and M.cond_text('ALWAYS') == 'Always', 'condition texts with their units')
check(M.rule_summary(draft.rules[1]) == 'Party member: HP below 50% -> Best of Cure', 'summary: ' .. M.rule_summary(draft.rules[1]))
check(M.rule_summary(draft.rules[3]) == 'Master (you): HP below 40% and MP at least 10% -> Best of Curaga (then waits 30 s)',
      'summary with a second condition and a wait: ' .. M.rule_summary(draft.rules[3]))
check(M.rule_summary(draft.rules[2]) == 'Self: Always -> Divine Seal', 'summary of a job ability: ' .. M.rule_summary(draft.rules[2]))
-- every condition the server offers has a readable label (no raw ids in the drop-downs)
local catLines = run('cat 30 WHM')
for _, line in ipairs(catLines) do
    local f = fields(line)
    if f[3] == 'cat' and f[4] == 'c' then
        for _, entry in ipairs(G.splitPlain(f[5], ',')) do
            local id = entry:match('^([%w_]+)')
            local label = M.cond_label(id)
            check(label ~= id and not label:find('_', 1, true), 'condition ' .. id .. ' is shown as "' .. label .. '"')
        end
    end
end
check(M.effect_id('Protect') == 'PROTECT' and M.effect_id(' shell ii ') == 'SHELL_II', 'typed effect names become the ids the server checks')

local d2 = { rules = { M.new_rule(), M.new_rule(), M.new_rule() } }
d2.rules[2].name, d2.rules[3].name = 'CURAGA', 'REGEN'
local sel = M.move_rule(d2, 3, -1)
check(sel == 2 and d2.rules[2].name == 'REGEN' and d2.dirty, 'Up moves the selected rule and keeps it selected')
check(M.move_rule(d2, 1, -1) == 1, 'Up on the first rule does nothing')
sel = M.add_rule(d2, 1)
check(sel == 2 and #d2.rules == 4 and d2.rules[2].name == 'CURE', 'Add puts a new rule below the selected one and selects it')
M.toggle_rule(d2, 2)
check(d2.rules[2].on == false, 'On / off switches only the selected rule')
sel = M.remove_rule(d2, 4)
check(sel == 3 and #d2.rules == 3, 'Remove keeps a valid selection')
d2.rules[1].arg = '61'
check(d2.rules[1].arg == '61' and d2.rules[2].arg == '50', 'editing one rule leaves the others as they are')

-- ---------------------------------------------------------------- addon: drawing with a stand-in ImGui (balance and no network)
section('addon: drawing the SQUAD tab with a stand-in ImGui (push/pop balance, no server traffic from local edits)')
for k, v in pairs({ ImGuiCol_Text = 0, ImGuiCol_Border = 5, ImGuiCol_Button = 21, ImGuiCol_ButtonHovered = 22,
                    ImGuiCol_Header = 24, ImGuiCol_HeaderHovered = 25, ImGuiChildFlags_Borders = 1 }) do rawset(_G, k, v) end
local function fakeImgui(opts)
    local g = { colors = 0, ids = 0, children = 0, combos = 0, disabled = 0, errors = {}, clicks = {}, texts = {} }
    local function err(e) g.errors[#g.errors + 1] = e end
    g.Text = function(t) g.texts[#g.texts + 1] = t end
    -- (hotfix 2026-11-21) as in Ashita: TextWrapped and SetTooltip take a printf format; a bare % in one is an error
    local function fmt(t) if tostring(t):gsub('%%%%', ''):find('%', 1, true) then err('format text with a bare %: ' .. t) end return t end
    g.TextWrapped = function(t) g.texts[#g.texts + 1] = fmt(t) end
    g.TextUnformatted = g.Text
    g.TextColored = function(_, t) g.texts[#g.texts + 1] = t end
    g.PushTextWrapPos, g.PopTextWrapPos = function() end, function() end
    g.BeginTooltip, g.EndTooltip = function() return true end, function() end
    g.SameLine = function() end
    g.SetNextItemWidth = function() end
    g.Separator = function() end
    g.SetTooltip = function(t) fmt(t) end
    g.IsItemHovered = function() return false end
    g.GetContentRegionAvail = function() return { 1000, 500 } end
    g.Button = function(label) if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    g.Selectable = function(label) if g.clicks[label] then g.clicks[label] = nil; return true end return false end
    -- (a number n: the n-th tick box with that label in the frame, e.g. the one of rule n's row)
    g.Checkbox = function(label, t)
        local c = g.clicks[label]
        if type(c) == 'number' and c > 1 then g.clicks[label] = c - 1; return false end
        if c then g.clicks[label] = nil; t[1] = not t[1]; return true end
        return false
    end
    g.InputText = function() return false end
    g.InputInt = function() return false end
    if not opts.noCombo then
        g.BeginCombo = function() return false end -- (closed: EndCombo must not be called)
        g.EndCombo = function() g.combos = g.combos - 1 end
    end
    g.PushStyleColor = function() g.colors = g.colors + 1 end
    g.PopStyleColor = function(n) g.colors = g.colors - (n or 1); if g.colors < 0 then err('PopStyleColor below zero') end end
    g.PushID = function() g.ids = g.ids + 1 end
    g.PopID = function() g.ids = g.ids - 1; if g.ids < 0 then err('PopID below zero') end end
    g.BeginChild = function() g.children = g.children + 1; return true end
    g.EndChild = function() g.children = g.children - 1; if g.children < 0 then err('EndChild below zero') end end
    if not opts.noDisabled then
        g.BeginDisabled = function() g.disabled = g.disabled + 1 end
        g.EndDisabled = function() g.disabled = g.disabled - 1 end
    end
    return g
end
local function balanced(g)
    local ok = g.colors == 0 and g.ids == 0 and g.children == 0 and g.combos == 0 and g.disabled == 0 and #g.errors == 0
    if not ok then
        io.write(string.format('   (colors %d, ids %d, children %d, combos %d, disabled %d, errors: %s)\n', g.colors, g.ids, g.children,
            g.combos, g.disabled, table.concat(g.errors, '; ')))
    end
    return ok
end

local sentLines = {}
local g = fakeImgui({})
M.init({ now = function() return clock end, imgui = g, s = function(px) return px * 2 end,
         queue_command = function(l) sentLines[#sentLines + 1] = l end })
local S2 = M._S
M.T.reset()
S2.server, S2.refreshing = nil, false
M.draw()
check(balanced(g) and M.busy(), 'first draw: asks the server (hello) and stays balanced')
M.T.reset()
S2.server = false
M.draw()
check(balanced(g), 'no server module: the notice draws balanced')
S2.server = { version = 1 }
S2.mates = { { slot = 1, id = 1, name = 'Mira', job = 'WHM', level = 25, chosen = 1, out = true } }
S2.mateSlot = 1
S2.sets = { { num = 1, job = 'WHM', rules = 2, flags = 'm', rev = '1', id = 'custom.whm.cure-basics', name = 'WHM - Cure basics' },
            { num = 2, job = 'WHM', rules = 3, flags = 'o', rev = '2', id = 'user.1.1', name = 'Mira test' } }
S2.selectedSet = 2
S2.draft, S2.cat = nil, nil
M.draw()
check(balanced(g), 'mate and sets, no Rule Set open: balanced')
S2.cat = { targets = { 'SELF', 'PARTY', 'MASTER', 'TARGET' }, condNames = { 'ALWAYS', 'HPP_LT', 'MPP_GTE', 'NOT_STATUS' },
           conds = cat.conds, families = { 'CURE', 'CURAGA', 'PROTECT' }, jas = { { name = 'DIVINE_SEAL', level = 15 } } }
S2.draft = { num = 2, rev = '2', job = 'WHM', name = 'Mira test', flags = 'o', rules = { M.new_rule(),
             { on = true, target = 'MASTER', cond = 'HPP_LT', arg = '40', cond2 = 'MPP_GTE', arg2 = '10', kind = 'family', name = 'CURAGA', retry = '30' },
             { on = false, target = 'SELF', cond = 'ALWAYS', kind = 'ja', name = 'DIVINE_SEAL' } } }
S2.sel = 2
S2.checks = { [3] = 'DIVINE_SEAL needs level 15' }
local beforeText = M.encode_rule(S2.draft.rules[2])
M.draw()
check(balanced(g), 'editing view with a selected rule (two conditions, a wait, a check note): balanced')
check(M.encode_rule(S2.draft.rules[2]) == beforeText and not S2.draft.dirty, 'just drawing changes nothing')
local shown = table.concat(g.texts, '\n')
check(shown:find('Selected rule 2', 1, true) and shown:find('Master (you): HP below 40% and MP at least 10% -> Best of Curaga', 1, true),
      'the selected rule\'s summary is shown')
check(not shown:find('HPP_LT', 1, true) and not shown:find('DIVINE_SEAL', 1, true), 'no raw ids in the visible texts')

-- clicks: local list edits never talk to the server
sentLines = {}
g.clicks['Down##gsq-down'] = true
M.draw(); M.tick()
check(S2.sel == 3 and S2.draft.rules[3].name == 'CURAGA' and #sentLines == 0, 'Down moves the selected rule; nothing is sent')
-- (0.3.5) a rule is switched on and off with the tick box of its row; the On / off button, which did the same, is gone
g.clicks['##on'] = 3
M.draw()
check(S2.draft.rules[3].on == false and S2.draft.rules[1].on ~= false and S2.draft.rules[2].on == false and S2.draft.rules[2].name == 'DIVINE_SEAL' and S2.draft.dirty,
      'the tick box of rule 3\'s row switches rule 3 off, and only that one (rule 1 stays on, rule 2 stays as it was)')
local toggleDrawn = false
for _, b in ipairs(g.buttons or {}) do if tostring(b):find('gsq-toggle', 1, true) then toggleDrawn = true end end
check(not toggleDrawn, 'there is no separate On / off button any more')
g.clicks['1. Party: HP < 50% -> Best of Cure##sel'] = true -- (beta polish: the compact rule line)
M.draw()
check(S2.sel == 1, 'clicking a rule in the list selects it')
g.clicks['Add rule##gsq-add'] = true
M.draw()
check(#S2.draft.rules == 4 and S2.sel == 2, 'Add rule adds below the selection and selects it')
g.clicks['Remove##gsq-remove'] = true
M.draw(); M.tick()
check(#S2.draft.rules == 3 and S2.sel == 2 and #sentLines == 0 and not M.busy(), 'Remove; still nothing sent, nothing queued')
check(balanced(g), 'balanced after the clicks')

-- read-only view: controls disabled, nothing can change
S2.draft.readonly, S2.draft.dirty = true, false
local frozen = St.valueText(S2.draft.rules)
g.clicks['Add rule##gsq-add'] = true
M.draw()
g.clicks['Add rule##gsq-add'] = nil
check(St.valueText(S2.draft.rules) == frozen and balanced(g), 'a read-only set cannot be changed (no Add, no edits) and draws balanced')

-- older bindings: no BeginCombo, no BeginDisabled
local g2 = fakeImgui({ noCombo = true, noDisabled = true })
M.init({ now = function() return clock end, imgui = g2, s = function(px) return px end, queue_command = function() end })
M.draw()
check(balanced(g2), 'without BeginCombo/BeginDisabled the tab still draws balanced')
S2.draft.readonly = false
local g3 = fakeImgui({})
g3.Button = function() error('boom') end
M.init({ now = function() return clock end, imgui = g3, s = function(px) return px end, queue_command = function() end })
check(not pcall(M.draw) and g3.colors == 0 and g3.children == 0 and g3.ids == 0 and g3.disabled == 0,
      'an error while drawing still closes every child, ID, disabled block and colour (ImGui stacks stay balanced)')
local g4 = fakeImgui({})
g4.Selectable = function() error('row boom') end
M.init({ now = function() return clock end, imgui = g4, s = function(px) return px end, queue_command = function() end })
check(not pcall(M.draw) and g4.colors == 0 and g4.children == 0 and g4.ids == 0, 'an error inside a rule row is also closed cleanly')

-- the Classic palette is FFXIPort 1.2.0\'s and matches Gambits\' own window
check(deq(M.THEMES.classic.window, { 0.105, 0.095, 0.082, 1 }) and deq(M.THEMES.classic.header, { 0.23, 0.18, 0.10, 1 })
      and deq(M.THEMES.classic.text, { 0.91, 0.89, 0.80, 1 }) and deq(M.THEMES.classic.tabSel, { 0.53, 0.42, 0.09, 1 }), 'Classic = FFXIPort 1.2.0 Classic = the Gambits window colours')
check(deq(M.THEMES.squad.window, { 0.067, 0.075, 0.106, 1 }) and deq(M.THEMES.crimson.button, { 0.285, 0.130, 0.155, 1 }),
      'Squad and Crimson keep their exact FFXIPort values')
check(M.theme == M.THEMES[M.DEFAULT_THEME] and M.DEFAULT_THEME == 'crimson', 'the default theme is in use (0.3.4: Crimson for a new installation)')


io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
