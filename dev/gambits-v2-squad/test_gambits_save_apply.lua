-- Gambits 0.3.4: the action bar (Save / Save & Apply / Save, Assign & Apply / Assign / Apply), the live Rule Set state
-- from the server (protocol 10, capability "live"), Apply for one mate ("!squad reapply <slot>", capability reapply1)
-- with the squad-wide Apply as the honest fallback, and the Rule Set and catalog caches. SIMULATION: the real add-on
-- (Gambits.lua, transport.lua, squad_editor.lua) and the real server modules (gambits_squad.lua, squad_rulesets.lua,
-- squad_rulesets_store.lua) with the stand-in game client of test_gambitsv2_addon.lua; no game, no server, no Ashita.
--   luajit test_gambits_save_apply.lua <server>/modules/custom/lua <server>/scripts/globals/gambits.lua
--                                      <server>/scripts/enum/job_ability.lua <kit>/addons-src/Gambits <work folder>
--   Lua 5.4: lua -e "unpack = unpack or table.unpack" test_gambits_save_apply.lua ...
-- The stand-in game is not copied here: this file runs the set-up part of test_gambitsv2_addon.lua (everything up to
-- the add-on's load event) and continues from there, so there is one stand-in to keep right.
local here = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local f = assert(io.open(here .. '/test_gambitsv2_addon.lua', 'rb'))
local base = f:read('*a'):gsub('\r\n', '\n')
f:close()
local cut = assert(base:find('\nevents.load.gv2_load()\n', 1, true), 'test_gambitsv2_addon.lua: the load line was not found')
local prefix = base:sub(1, cut) .. 'events.load.gv2_load()\n'

local body = [==[
-- ================================================================= from here: this file's own checks
do
local BRAN = { slot = 2, id = 12, name = 'Bran', mjob = 3, sjob = 0, jobs = { [3] = { level = 25 } } }
local SQ = { MIRA, BRAN }
GetSquad = function() return SQ end
local S = Ed._S
local W = { single = true, ignore = {}, reapplyAll = 0, reapplyOne = 0 }

-- a called mate, with the marks squad.lua's spawn leaves on it (squad_rulesets.lua R.markLive: the real function)
local function called(mate)
    local vars = { SQUAD_ID = mate.id }
    local t = { getObjType = function() return xi.objType.TRUST end,
                getLocalVar = function(_, k) return vars[k] or 0 end, setLocalVar = function(_, k, v) vars[k] = v end }
    local set = R.resolve(player, mate.id, mate.mjob, R.load())
    R.markLive(t, player, mate.id, mate.mjob, set, 0, 0)
    t.vars = vars
    return t
end
local function out_of(id)
    for i, t in ipairs(game.party) do if t:getLocalVar('SQUAD_ID') == id then return i, t end end
end
local function call(mate) if not out_of(mate.id) then game.party[#game.party + 1] = called(mate) end end

-- the squad commands as this server answers them: W.single = it has "!squad reapply <slot>"
squad_command = function(text)
    local w = {}
    for word in text:gmatch('%S+') do w[#w + 1] = word end
    if w[1] == 'ruleset' then
        R.command(player, SQ, w[2], w[3], { say = function(p, t) p:printToPlayer(t) end,
            findMate = function(sq, slot) for _, m in ipairs(sq) do if m.slot == slot then return m end end end,
            jobNames = { [3] = 'WHM' } })
    elseif w[1] == 'reapply' then
        local slot = tonumber(w[2] or '')
        if slot and W.single then
            W.reapplyOne = W.reapplyOne + 1
            local mate = SQ[slot]
            local at = mate and out_of(mate.id)
            if W.ignore[slot] or not at then return end
            table.remove(game.party, at)
            game.timers = { at = clock + 4.0, fn = function() call(mate) end }
        else
            W.reapplyAll = W.reapplyAll + 1
            local back = {}
            for _, m in ipairs(SQ) do if out_of(m.id) then back[#back + 1] = m end end
            game.party = {}
            game.timers = { at = clock + 4.0, fn = function() for _, m in ipairs(back) do call(m) end end }
        end
    end
end

local function sends(pattern, from)
    local n = 0
    for i = (from or 1), #game.sends do
        if game.sends[i].decision ~= 'reject' and game.sends[i].line:find(pattern) then n = n + 1 end
    end
    return n
end
local function idle() return not Ed.busy() and S.apply == nil and not S.pendingApply and not S.afterSaveRun and S.progress == nil end
local function settle(limit) return run_until(idle, limit or 60) end
local function hello(single)
    W.single = single
    xi.squad.reapplySlot = single and true or nil
    SquadDismissMate = single and function() return true end or nil
    S.server, S.refreshing = nil, false
    Ed.refresh()
    settle()
end
local function ids(st) local t = {} for _, a in ipairs(st.actions) do t[#t + 1] = a.id end return table.concat(t, ',') end
local function mate(slot) for _, m in ipairs(S.mates) do if m.slot == slot then return m end end end
local function refresh_mates() local done = false; Ed.read_mates(function() done = true end, function() done = true end); run_until(function() return done end, 20) end

-- ---------------------------------------------------------------- 1. capabilities and the live state on the wire
section('1. the server says what it can do; the mates answer carries what each mate runs')
check(cmd('/gv2') == true, 'the window opens')
hello(true)
check(S.server and S.server.version == 12 and Ed.cap('live') and Ed.cap('reapply1'), 'hello: version 12, capabilities live and reapply1')
hello(false)
check(Ed.cap('live') and not Ed.cap('reapply1'), 'a squad.lua without the one-mate Apply: live only (reapply1 is not claimed)')
hello(true)
refresh_mates()
check(mate(1) and mate(1).live and mate(1).live.state == 'off' and mate(2).live.state == 'off', 'nobody is out: both mates report "off"')
do
    local old = Ed.cap
    local keep = S.server.caps
    S.server.caps = nil
    check(Ed.cap('live') == false and Ed.cap('reapply1') == false, 'an older server (no capability field): nothing newer is used')
    S.server.caps = keep
end

-- ---------------------------------------------------------------- 2. the bar: which actions fit (a table of states)
section('2. M.bar_state: only the actions that fit the open set and the selected mate')
do
    local function M8(over) local m = { slot = 1, name = 'Mira', job = 'WHM', chosen = 0, out = true } for k, v in pairs(over or {}) do m[k] = v end return m end
    local function D(over) local d = { num = 5, job = 'WHM', name = 'Set', flags = 'o', rules = {}, dirty = false } for k, v in pairs(over or {}) do d[k] = v end return d end
    local live = function(state, num, why, fb, dropped) return { state = state, num = num or 0, why = why or '-', fb = fb or 0, dropped = dropped or 0 } end
    local st
    st = Ed.bar_state(D({ dirty = true }), M8())
    check(ids(st) == 'save,save_assign' and st.actions[2].label == 'Save, Assign & Apply' and st.state == 'Unsaved changes', 'unsaved, another set chosen, mate out: Save | Save, Assign & Apply')
    st = Ed.bar_state(D({ dirty = true }), M8({ out = false }))
    check(ids(st) == 'save,save_assign' and st.actions[2].label == 'Save & Assign', 'unsaved, mate away: Save | Save & Assign (nothing to apply)')
    st = Ed.bar_state(D({ dirty = true, num = 0 }), M8())
    check(ids(st) == 'save,save_assign' and st.state == 'Not saved yet', 'a new set: Not saved yet, Save | Save, Assign & Apply')
    st = Ed.bar_state(D({ dirty = true }), M8({ chosen = 5 }))
    check(ids(st) == 'save,save_apply' and st.actions[2].label == 'Save & Apply', 'unsaved, this set is the mate\'s and the mate is out: Save | Save & Apply')
    st = Ed.bar_state(D({ dirty = true }), M8({ chosen = 5, out = false }))
    check(ids(st) == 'save' and st.note and st.note:find('not summoned', 1, true), 'unsaved, the mate\'s set, mate away: Save only, with "applies when it is called"')
    st = Ed.bar_state(D(), M8())
    check(ids(st) == 'assign' and st.actions[1].label == 'Assign & Apply' and st.state == 'Saved, not used by Mira', 'saved, not the mate\'s set, out: Assign & Apply')
    st = Ed.bar_state(D(), M8({ out = false }))
    check(ids(st) == 'assign' and st.actions[1].label == 'Assign', 'saved, not the mate\'s set, away: Assign')
    st = Ed.bar_state(D(), M8({ chosen = 5, out = false }))
    check(ids(st) == '' and st.state:find('applies when called', 1, true), 'saved, the mate\'s set, away: no button, "Selected ... (applies when called)"')
    st = Ed.bar_state(D(), M8({ chosen = 5, live = live('set', 5) }))
    check(ids(st) == '' and st.state == 'Active on Mira' and st.tone == 'ok', 'the server says it runs: "Active on Mira", no button')
    st = Ed.bar_state(D(), M8({ chosen = 5, live = live('set', 5, '-', 0, 2) }))
    check(st.state == 'Active on Mira' and st.note:find('2 rules', 1, true), 'active with rules left out: said in the note')
    st = Ed.bar_state(D(), M8({ chosen = 5, live = live('pending', 5, 'edited') }))
    check(ids(st) == 'apply' and st.state == 'Apply needed' and st.note:find('saved with changes', 1, true), 'the server says "pending, edited": Apply needed + Apply')
    st = Ed.bar_state(D(), M8({ chosen = 5, live = live('pending', 3, 'choice') }))
    check(ids(st) == 'apply' and st.state == 'Apply needed', 'chosen but another set still runs: Apply needed + Apply')
    st = Ed.bar_state(D(), M8({ chosen = 5, live = live('fallback', 0, '-', 3) }))
    check(st.state == 'Selected, but not used' and st.tone == 'bad' and st.note:find('none of its rules', 1, true), 'fallback: "Selected, but not used" with the server\'s reason')
    st = Ed.bar_state(D(), M8({ chosen = 5, live = live('addon') }))
    check(ids(st) == '' and st.state == 'Run by an add-on', 'an add-on runs the mate: no Apply is offered')
    st = Ed.bar_state(D(), M8({ chosen = 5 }))
    check(st.state == 'Selected for Mira' and st.state ~= 'Active on Mira' and ids(st) == 'apply' and not st.actions[1].primary,
          'an older server (no live state): never "Active"; Apply is there, not as the main action')
    S.needApply[1] = true
    st = Ed.bar_state(D(), M8({ chosen = 5 }))
    check(st.state == 'Apply needed' and st.actions[1].primary, 'an older server after this editor saved the running set: Apply needed')
    S.needApply[1] = nil
    st = Ed.bar_state(D({ dirty = true, job = 'BLM' }), M8({ chosen = 5 }))
    check(ids(st) == 'save' and st.note:find('cannot be used by Mira', 1, true), 'job mismatch: Save only, and why')
    st = Ed.bar_state(D({ job = 'BLM' }), M8())
    check(ids(st) == '', 'job mismatch, saved: nothing to assign')
    st = Ed.bar_state(D({ readonly = true }), M8())
    check(ids(st) == 'assign', 'a read-only set can still be assigned')
    hello(false)
    st = Ed.bar_state(D({ dirty = true }), M8({ chosen = 5 }))
    check(st.actions[2].tip:find('every mate that is out', 1, true), 'without reapply1 the tooltip says the whole squad is called again')
    hello(true)
    st = Ed.bar_state(D({ dirty = true }), M8({ chosen = 5 }))
    check(st.actions[2].tip:find('the other mates stay out', 1, true), 'with reapply1 it says the others stay out')
end

-- ---------------------------------------------------------------- 3. Save, Assign & Apply; then Save & Apply
section('3. Save, Assign & Apply for one mate; Save & Apply; two mates on one set')
call(MIRA); call(BRAN)
Ed.switch_mate(2); settle(); Ed.switch_mate(1); settle()
Ed.new_set('WHM')
S.draft.name = 'Apply test'
local from = #game.sends + 1
local bran0 = select(2, out_of(BRAN.id))
check(ids(Ed.bar_state(S.draft, Ed.mate())) == 'save,save_assign', 'a new set: the bar offers Save and Save, Assign & Apply')
Ed.bar_do('save_assign', S.draft, Ed.mate())
local okA = settle(90)
local NUM = S.draft.num
check(okA and NUM > 0 and not S.draft.dirty, 'saved (server confirmed): set ' .. tostring(NUM))
check(sends('!squad ruleset 1 ' .. NUM, from) == 1 and sends('!squad reapply 1$', from) == 1 and sends('!squad reapply$', from) == 0,
      'one assignment line and one "!squad reapply 1"; no squad-wide reapply')
check(W.reapplyOne == 1 and select(2, out_of(BRAN.id)) == bran0, 'Bran was not sent off (the same called mate as before)')
check(S.message and S.message:find('Applied: Mira now runs Apply test (server confirmed)', 1, true) and S.message:find('The other mates stayed out', 1, true),
      'the message comes from the server\'s own report: ' .. tostring(S.message))
check(mate(1).live.state == 'set' and mate(1).live.num == NUM and Ed.bar_state(S.draft, Ed.mate()).state == 'Active on Mira', 'the bar: Active on Mira')
-- one read of the squad between the assignment and the reapply line (the read-back), not two
do
    local a, r, reads = nil, nil, 0
    for i = from, #game.sends do
        local l = game.sends[i].line
        if l:find('!squad ruleset', 1, true) then a = i end
        if l:find('!squad reapply', 1, true) then r = i end
    end
    for i = (a or 1), (r or 0) do if game.sends[i].line:find('!gsq mates', 1, true) and game.sends[i].decision ~= 'reject' then reads = reads + 1 end end
    check(a and r and reads == 1, 'between the assignment and the reapply the squad is read once (was twice): ' .. reads)
end

-- Bran gets the same set by hand; then the set is edited and saved with Save & Apply for Mira
squad_command('ruleset 2 ' .. NUM)
do local at = out_of(BRAN.id); table.remove(game.party, at); call(BRAN) end
refresh_mates()
check(mate(2).chosen == NUM and mate(2).live.state == 'set', 'Bran runs the same set')
S.draft.rules[1].arg = '61'; S.draft.dirty = true
check(ids(Ed.bar_state(S.draft, Ed.mate())) == 'save,save_apply', 'edited, in use, out: Save | Save & Apply')
from = #game.sends + 1
local one0 = W.reapplyOne
Ed.bar_do('save_apply', S.draft, Ed.mate())
settle(90)
check(sends('!squad ruleset', from) == 0 and sends('!squad reapply 1$', from) == 1 and W.reapplyOne == one0 + 1,
      'Save & Apply: no assignment line (it is assigned already), one "!squad reapply 1"')
check(S.message:find('Applied: Mira now runs Apply test', 1, true) ~= nil, 'applied, server confirmed: ' .. tostring(S.message))
refresh_mates()
check(mate(1).live.state == 'set' and mate(2).live.state == 'pending' and mate(2).live.why == 'edited',
      'two mates on one set: Mira runs the new rules, Bran reports "pending, edited" (Apply needed)')
Ed.switch_mate(2); settle()
check(S.draft and S.draft.num == NUM and Ed.bar_state(S.draft, Ed.mate()).state == 'Apply needed' and ids(Ed.bar_state(S.draft, Ed.mate())) == 'apply',
      'on Bran the bar says Apply needed and offers Apply')
Ed.switch_mate(1); settle()

-- ---------------------------------------------------------------- 4. only the name changed
section('4. a rename: saved, nothing applied')
S.draft.name = 'Apply test renamed'; S.draft.dirty = true
from = #game.sends + 1
Ed.bar_do('save_apply', S.draft, Ed.mate())
settle(90)
check(not S.draft.dirty and sends('!squad reapply', from) == 0 and S.message:find('only the name changed', 1, true),
      'Save & Apply after a rename: saved, no reapply line: ' .. tostring(S.message))
refresh_mates()
check(mate(1).live.state == 'set', 'and the server reports no pending state for Mira (its check is made from the rules)')

-- ---------------------------------------------------------------- 5. a Save that fails, a lost answer, repeated clicks
section('5. failed Save, lost answer, repeated clicks: never an Apply without a confirmed Save, never two Applies')
do
    local realGs = Gs.save
    Gs.save = function() return nil, 'stale', 'the Rule Set changed since it was loaded; load it again' end
    S.draft.rules[1].arg = '62'; S.draft.dirty = true
    from = #game.sends + 1
    Ed.bar_do('save_apply', S.draft, Ed.mate())
    settle(90)
    check(S.draft.dirty and sends('!squad reapply', from) == 0 and S.afterSaveRun == nil and not S.messageOk,
          'a refused Save (stale): the rows are kept, nothing is applied: ' .. tostring(S.message))
    Gs.save = realGs
end
do
    -- the answer to the last part of the Save is lost: the editor looks on the server before it says anything
    game.policy = function(line)
        local tok, seq, tot = line:match('^/say !gsq [wx] (%d+) (%d+) (%d+) ')
        if tok and seq == tot and not game.dropTo then game.dropTo = tok end
        return 'auto'
    end
    from = #game.sends + 1
    Ed.bar_do('save_apply', S.draft, Ed.mate())
    run_until(function() return game.dropTo ~= nil end, 60)
    step(0.5); game.dropTo = nil; game.policy = nil
    settle(120)
    check(not S.draft.dirty and sends('!squad reapply 1$', from) == 1 and S.message:find('Applied: Mira now runs', 1, true),
          'a lost answer: confirmed by reading back, and only then applied, once: ' .. tostring(S.message))
end
do
    S.draft.rules[1].arg = '63'; S.draft.dirty = true
    from = #game.sends + 1
    local first = Ed.bar_do('save_apply', S.draft, Ed.mate())
    local second = Ed.bar_do('save_apply', S.draft, Ed.mate())
    local third = Ed.bar_do('apply', S.draft, Ed.mate())
    settle(90)
    check(first ~= false and second == false and third == false and sends('!squad reapply', from) == 1, 'three clicks in a row: one Save, one reapply')
    from = #game.sends + 1
    Ed.apply({ slot = 1 })
    run_until(function() return S.apply ~= nil end, 30)
    local again = Ed.apply({ slot = 1 })
    settle(90)
    check(again == false and sends('!squad reapply', from) == 1, 'Apply while an Apply is under way is refused: one reapply line')
end

-- ---------------------------------------------------------------- 6. a mate that is not out, a refusal, an add-on's mate
section('6. unsummoned mate, a re-call the server refuses, a mate an add-on owns')
do
    local at = out_of(MIRA.id); table.remove(game.party, at)
    refresh_mates()
    from = #game.sends + 1
    Ed.apply({ slot = 1 })
    settle(60)
    check(sends('!squad reapply', from) == 0 and S.message:find('Mira is not summoned', 1, true), 'Apply for a mate that is away: nothing sent: ' .. tostring(S.message))
    S.draft.rules[1].arg = '64'; S.draft.dirty = true
    check(ids(Ed.bar_state(S.draft, Ed.mate())) == 'save', 'and the bar offers Save only for it')
    Ed.bar_do('save', S.draft, Ed.mate()); settle(60)
    call(MIRA); refresh_mates()
end
do
    W.ignore[1] = true -- (the server refuses: "already being called again", or the line is refused for another reason)
    from = #game.sends + 1
    Ed.apply({ slot = 1 })
    settle(90)
    check(sends('!squad reapply 1$', from) == 1 and S.messageWarn and S.message:find('Apply NOT confirmed: Mira did not leave', 1, true),
          'a re-call the server did not do is not reported as applied: ' .. tostring(S.message))
    select(2, out_of(MIRA.id)).vars.ADDON_OWNED = 1
    Ed.apply({ slot = 1 })
    settle(90)
    check(S.message:find('an add-on owns Mira', 1, true) ~= nil, 'a mate an add-on owns: said so, not applied: ' .. tostring(S.message))
    refresh_mates()
    check(Ed.bar_state(S.draft, Ed.mate()).state == 'Run by an add-on' and ids(Ed.bar_state(S.draft, Ed.mate())) == '', 'the bar offers no Apply for it')
    select(2, out_of(MIRA.id)).vars.ADDON_OWNED = nil
    W.ignore[1] = nil
end

-- ---------------------------------------------------------------- 7. an older server, and a server that calls everyone
section('7. squad-wide Apply on an older server; never "only this mate" when the others left too')
hello(false)
refresh_mates()
from = #game.sends + 1
local all0 = W.reapplyAll
Ed.apply({ slot = 1 })
settle(120)
check(sends('!squad reapply$', from) == 1 and sends('!squad reapply %d', from) == 0 and W.reapplyAll == all0 + 1, 'no reapply1: the squad-wide line is sent')
check(S.message:find('every mate that was out was called again', 1, true) and not S.message:find('stayed out', 1, true),
      'and the message says that the whole squad was called again: ' .. tostring(S.message))
hello(true)
W.single = false -- (it claims the one-mate form but calls everyone: an older squad.lua behind a newer gambits_squad.lua)
refresh_mates()
from = #game.sends + 1
Ed.apply({ slot = 1 })
settle(120)
check(sends('!squad reapply 1$', from) == 1 and S.message:find('the whole squad was called again', 1, true) and not S.message:find('stayed out', 1, true),
      'the others left too: the message says so: ' .. tostring(S.message))
hello(true)

-- ---------------------------------------------------------------- 8. caches
section('8. a set opened before and a mate seen before are not asked for again')
do
    refresh_mates()
    Ed.load_sets('WHM'); settle()
    S.draft.dirty = false
    from = #game.sends + 1
    Ed.select_set(1); settle()
    Ed.select_set(NUM); settle()
    local first = sends('!gsq get', from)
    Ed.select_set(1); settle()
    Ed.select_set(NUM); settle()
    check(first >= 1 and sends('!gsq get', from) == first and S.draft.num == NUM, 'reopening two sets: no further "get" (' .. first .. ' before, ' .. sends('!gsq get', from) .. ' after)')
    S.draft.rules[1].arg = '65'; S.draft.dirty = true
    Ed.bar_do('save', S.draft, Ed.mate()); settle(60)
    from = #game.sends + 1
    Ed.select_set(1); settle()
    Ed.select_set(NUM); settle()
    check(sends('!gsq get', from) == 1 and S.draft.rules[1].arg == '65', 'after a Save its revision changed: it is read again, with the saved rule')
    from = #game.sends + 1
    Ed.switch_mate(2); settle(); Ed.switch_mate(1); settle(); Ed.switch_mate(2); settle(); Ed.switch_mate(1); settle()
    check(sends('!gsq catm', from) == 0, 'the choices of both mates were kept: no "catm" on switching back and forth')
    MIRA.jobs[3].level = 26
    refresh_mates()
    from = #game.sends + 1
    Ed.load_catalog_for(Ed.mate()); settle()
    check(sends('!gsq catm', from) == 1, 'a level up is another key: asked again')
    MIRA.jobs[3].level = 25
end

-- ---------------------------------------------------------------- 9. /gambits show <slot>, rule to the top / bottom
section('9. /gambits show <slot>; a rule to the top or the bottom')
check(cmd('/gambits show 2') == true and S.mateSlot == 2 and GV.open[1] == true, '/gambits show 2: the window on Bran')
settle()
check(cmd('/gambits show 1') == true and S.mateSlot == 1, '/gambits show 1: back on Mira')
settle()
do
    local d = { num = 0, job = 'WHM', name = 'Order', flags = 'o', dirty = false, rules = { { n = 1 }, { n = 2 }, { n = 3 }, { n = 4 } } }
    local at = Ed.move_rule_end(d, 3, true)
    check(at == 1 and d.rules[1].n == 3 and d.rules[2].n == 1 and d.rules[4].n == 4 and d.dirty, 'rule 3 to the top: 3 1 2 4')
    at = Ed.move_rule_end(d, 1, false)
    check(at == 4 and d.rules[4].n == 3 and d.rules[1].n == 1, 'and to the bottom: 1 2 4 3')
    d.dirty = false
    check(Ed.move_rule_end(d, 4, false) == 4 and not d.dirty, 'already there: nothing changes')
    d.readonly = true
    check(Ed.move_rule_end(d, 1, false) == 1 and d.rules[1].n == 1, 'a read-only set is not reordered')
end

-- ---------------------------------------------------------------- 10. is "Active" still true?
section('10. the live state after a change outside the editor, a reopened window, another mate: checked, never assumed')
do
    local function bar() return Ed.bar_state(S.draft, Ed.mate()) end
    local function reads(from) return sends('!gsq mates', from) end
    -- the Squads menu's answer from the server, as the server writes it (squad_rulesets.lua R.panelLine: the real function)
    local function panel(mate)
        local line = R.panelLine(player, mate, select(2, out_of(mate.id)), R.load())
        deliver('squadpanel:' .. line)
    end
    local function recall(mate) local at = out_of(mate.id); if at then table.remove(game.party, at) end call(mate) end
    hello(true)
    check(GV.open[1] == true, 'the window is open')
    squad_command('ruleset 1 ' .. NUM); recall(MIRA); squad_command('ruleset 2 ' .. NUM); recall(BRAN)
    Ed.switch_mate(1); settle(); refresh_mates(); Ed.select_set(NUM); settle()
    S.draft.dirty = false
    run_until(function() return false end, 2)
    check(S.shownAt ~= nil and bar().state == 'Active on Mira' and not S.liveUnsure, 'the start: the editor is drawn, Mira runs the set, the bar says Active on Mira')

    -- (a) nothing happens for a minute: no polling
    local from = #game.sends + 1
    panel(MIRA); panel(BRAN)
    run_until(function() return false end, 60)
    check(reads(from) == 0 and bar().state == 'Active on Mira', 'a minute with the window open, the menu\'s answer passing by unchanged: not one mates request (no polling)')

    -- (b) the Rule Set is changed in the Squads menu (the server now has "none" chosen for Mira; she still runs the set)
    squad_command('ruleset 1 0')
    check(bar().state == 'Active on Mira', '(the editor cannot know yet: nothing has told it)')
    from = #game.sends + 1
    panel(MIRA)
    run_until(function() return S.liveUnsure == true end, 5)
    local checking = bar()
    check(checking.state == 'Checking what Mira runs...' and ids(checking) == '' and checking.tone == 'note',
          'the menu\'s answer from the server shows a change: the bar says "Checking what Mira runs..." and offers no action; never Active')
    settle(30); run_until(function() return not S.liveUnsure end, 30)
    check(reads(from) == 1 and not S.liveUnsure, 'ONE mates request follows')
    check(bar().state ~= 'Active on Mira' and bar().state == 'Saved, not used by Mira' and mate(1).chosen == 0,
          'and the bar is the server\'s word: the set is no longer Mira\'s (' .. tostring(bar().state) .. ')')
    from = #game.sends + 1
    panel(MIRA); panel(MIRA); panel(BRAN)
    run_until(function() return false end, 20)
    check(reads(from) == 0, 'the same answer again (the menu asks often): no further request')

    -- (c) chosen again in the menu and the mate called again there
    squad_command('ruleset 1 ' .. NUM)
    from = #game.sends + 1
    panel(MIRA)
    run_until(function() return S.liveUnsure == true end, 5); settle(30); run_until(function() return not S.liveUnsure end, 30)
    check(reads(from) == 1 and bar().state == 'Active on Mira', 'chosen again in the menu while she still runs it: one request, and Active again because the SERVER says she runs it')
    -- another set is chosen in the menu and she is called with it; then this set is chosen again, without a call
    squad_command('ruleset 1 1'); recall(MIRA)
    from = #game.sends + 1
    panel(MIRA)
    run_until(function() return S.liveUnsure == true end, 5); settle(30); run_until(function() return not S.liveUnsure end, 30)
    check(reads(from) == 1 and bar().state == 'Saved, not used by Mira', 'the menu gave her another set and called her: one request, this set is not hers (' .. tostring(bar().state) .. ')')
    squad_command('ruleset 1 ' .. NUM)
    from = #game.sends + 1
    panel(MIRA)
    run_until(function() return S.liveUnsure == true end, 5); settle(30); run_until(function() return not S.liveUnsure end, 30)
    check(reads(from) == 1 and bar().state == 'Apply needed' and mate(1).live.state == 'pending',
          'this set chosen again in the menu, not called yet: one request, "Apply needed" and not Active (' .. tostring(bar().state) .. ')')
    recall(MIRA)
    from = #game.sends + 1
    panel(MIRA)
    run_until(function() return S.liveUnsure == true end, 5); settle(30); run_until(function() return not S.liveUnsure end, 30)
    check(reads(from) == 1 and bar().state == 'Active on Mira', 'called again from the menu: one request, and only now "Active on Mira"')

    -- (d) the window is closed, the set is taken away by a line typed in chat (nothing passes by), the window is opened
    cmd('/gv2')
    check(GV.open[1] == false, 'the window is closed')
    squad_command('ruleset 1 0')
    from = #game.sends + 1
    run_until(function() return false end, 30)
    check(reads(from) == 0, 'closed for 30 seconds: nothing is asked')
    cmd('/gv2')
    step(0.05)
    check(GV.open[1] == true and bar().state == 'Checking what Mira runs...', 'opened again: the first frame says "Checking", not the "Active" of before')
    settle(30); run_until(function() return not S.liveUnsure end, 30)
    check(reads(from) == 1 and bar().state == 'Saved, not used by Mira', 'one request, then the server\'s word (' .. tostring(bar().state) .. ')')
    from = #game.sends + 1
    run_until(function() return false end, 20)
    check(reads(from) == 0, 'and nothing more while it stays open')
    squad_command('ruleset 1 ' .. NUM); recall(MIRA); refresh_mates()

    -- (e) another mate is looked at later
    run_until(function() return false end, 6)
    squad_command('ruleset 2 0')   -- (Bran's set is taken away outside the editor)
    from = #game.sends + 1
    Ed.switch_mate(2)
    check(S.liveUnsure == true, 'another mate, more than 5 seconds after the last answer: not sure until asked')
    settle(60); run_until(function() return not S.liveUnsure end, 30)
    Ed.select_set(NUM); settle(); S.draft.dirty = false
    check(reads(from) == 1 and mate(2).chosen == 0 and bar().state == 'Saved, not used by Bran', 'one request; Bran\'s state is the server\'s (' .. tostring(bar().state) .. ')')
    from = #game.sends + 1
    Ed.switch_mate(1); settle(60)
    check(reads(from) == 0 and not S.liveUnsure, 'back to Mira within 5 seconds of an answer: not asked again')
    Ed.select_set(NUM); settle(); S.draft.dirty = false

    -- (f) the selected Rule Set changes: the state is the server's live set against the set that is open, no request
    from = #game.sends + 1
    check(bar().state == 'Active on Mira', 'the set Mira runs is open: Active on Mira')
    Ed.select_set(1); settle(); S.draft.dirty = false
    check(S.draft.num == 1 and bar().state ~= 'Active on Mira' and reads(from) == 0, 'another set is opened: not Active (' .. tostring(bar().state) .. '), and nothing had to be asked')
    Ed.select_set(NUM); settle(); S.draft.dirty = false

    -- (g) unsaved changes: the editing actions do not wait for the check
    Ed.live_recheck()
    S.draft.dirty = true
    check(ids(bar()) == 'save,save_apply', 'with unsaved changes the bar offers Save / Save & Apply as before, also while it is checking')
    S.draft.dirty = false
    settle(30); run_until(function() return not S.liveUnsure end, 30)

    -- (h) the request gets no answer: "Not confirmed", not Active, and it is not asked for ever
    game.policy = function(line) if line:find('!gsq mates', 1, true) then return 'lost' end return 'auto' end
    Ed.live_recheck()
    from = #game.sends + 1
    run_until(function() return S.liveFailed == true end, 60)
    local failed1 = bar()
    local asked = reads(from)
    run_until(function() return false end, 60)
    check(failed1.state == 'Not confirmed' and failed1.note:find('did not answer', 1, true) and ids(failed1) == '' and reads(from) == asked,
          'no answer: "Not confirmed" (never Active), and after the transport\'s own tries (' .. asked .. ' lines) nothing more is sent')
    game.policy = nil
    refresh_mates()
    check(bar().state == 'Active on Mira' and not S.liveFailed, 'Refresh: asked again, Active on Mira')

    -- (i) an Apply of the editor's own is not disturbed, and ends with a state that is confirmed
    S.draft.rules[1].arg = '66'; S.draft.dirty = true
    from = #game.sends + 1
    Ed.bar_do('save_apply', S.draft, Ed.mate())
    run_until(function() return S.apply ~= nil end, 60)
    panel(MIRA)   -- (the menu sees the mate leave and come back)
    settle(120)
    panel(MIRA)
    run_until(function() return false end, 15)
    check(sends('!squad reapply 1$', from) == 1 and S.message:find('Applied: Mira now runs', 1, true) and bar().state == 'Active on Mira' and not S.liveUnsure,
          'Save & Apply with the menu\'s answers passing by: one reapply, applied, and the bar ends on a confirmed "Active on Mira"')

    -- (j) an older server (no live state): nothing is checked, nothing is claimed
    do
        local keep = S.server.caps
        S.server.caps = { reapply1 = true }
        for _, m in ipairs(S.mates) do m.live = nil end
        from = #game.sends + 1
        cmd('/gv2'); run_until(function() return false end, 5); cmd('/gv2'); run_until(function() return false end, 10)
        panel(MIRA); Ed.switch_mate(2); settle(60); Ed.switch_mate(1); settle(60)
        Ed.select_set(NUM); settle(); S.draft.dirty = false
        check(reads(from) == 0 and not S.liveUnsure and bar().state == 'Selected for Mira',
              'a server that does not report what runs: reopening, the menu\'s lines and a mate switch ask nothing; the bar says "Selected for Mira", never Active or Checking')
        S.server.caps = keep
        refresh_mates()
    end
end
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
]==]

local chunk, err = (loadstring or load)(prefix .. body, '=test_gambits_save_apply')
assert(chunk, err)
chunk()
