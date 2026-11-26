-- The Squads menu's Rules line after a change (servermenu 1.26n, responsiveness M1-M3, 2026-11-24), in a time-stepped
-- SIMULATION: a stand-in Ashita/ImGui and a stand-in server that answers every "!squad panel" with the state of that
-- moment, and can drop a chat line or answer late. This is not a gameplay test: it checks the menu's own logic.
--   M1  the menu waits 2.2 s after another add-on's (or your) chat line before typing its own next line
--   M2  an ask without an answer for 3 s no longer holds back the next one; an answer is credited to the OLDEST ask
--       that can still be answered (lost asks kept 10 s), so a late answer never confirms a newer change
--   M3  after a change, asks at +2, +7, +11 s (at most three, a newer change replaces them, early stop once settled)
--   luajit test_squad_rules_refresh.lua          (Lua 5.4: lua test_squad_rules_refresh.lua)
local HERE = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local MENU = arg[1] or (HERE .. '/../../addons-src/servermenu/servermenu.lua')
io.stdout:setvbuf('no')
local passed, failed = 0, 0
local function check(c, label) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function has(t, n) return tostring(t):find(n, 1, true) ~= nil end
local realPrint = print

local function makeImgui(W)
    local im = setmetatable({}, { __index = function() return function() end end })
    local function ev(kind, text, color) W.events[#W.events + 1] = { kind = kind, text = tostring(text), color = color } end
    function im.BeginTooltip() W.inTip = true return true end
    function im.EndTooltip() W.inTip = false end
    function im.TextUnformatted(t) ev(W.inTip and 'tip' or 'text', t) end
    function im.Begin() return true end
    function im.BeginChild() return true end
    function im.Button() return false end
    function im.Text(t) ev('text', t) end
    function im.TextWrapped(t) ev('text', t) end
    function im.TextColored(c, t) ev('text', t, c) end
    function im.BeginCombo() return false end
    function im.IsItemHovered() return false end
    function im.GetFontSize() return 13 end
    function im.GetWindowWidth() return 620 end
    function im.GetContentRegionAvail() return { 600, 400 } end
    function im.GetCursorScreenPos() return { 0, 0 } end
    function im.GetWindowDrawList() return setmetatable({}, { __index = function() return function() end end }) end
    function im.CalcTextSize(t) return { #tostring(t) * 7, 13 } end
    function im.GetWindowPos() return 0, 0 end
    return im
end

-- ---------------------------------------------------------------- one simulated session
-- opts.truth(t) -> nil (mate away) or { state, live, liveName, sel, selName } ; opts.drop(ask) -> true to drop the line;
-- opts.delay(ask) -> answer delay (default 0.4 s); opts.rs = false: an older server without rs lines; opts.chan: the
-- server offers the addon channel packet (the menu then sends ! lines as packets)
local function session(opts)
    local W = { handlers = {}, events = {}, clock = 100, sent = {}, packets = {}, frames = {}, foreign = {} }
    local chat = {}
    function chat:QueueCommand(_, command)
        W.sent[#W.sent + 1] = { at = W.clock, command = command, how = 'typed' }
        W.handlers.command({ command = command, blocked = false })   -- (Ashita runs every add-on's command event)
    end
    function chat:IsInputOpen() return false end
    local pm = {}
    function pm.AddOutgoingPacket(_, id, bytes)
        local text = {}
        for i = 9, #bytes do if bytes[i] == 0 then break end text[#text + 1] = string.char(bytes[i]) end
        W.sent[#W.sent + 1] = { at = W.clock, command = '/say ' .. table.concat(text), how = 'packet' }
        return true
    end
    addon = {}
    ashita = { events = { register = function(n, _, fn) W.handlers[n] = fn end }, time = { get_tick64 = function() return W.clock * 1000 end },
               fs = { create_directory = function() end } }
    local dir = os.tmpname(); os.remove(dir)
    if package.config:sub(1, 1) == '\\' then os.execute('mkdir "' .. dir .. '" 2>nul') else os.execute('mkdir -p "' .. dir .. '"') end
-- (servermenu 1.27) an installation from before themes: its settings file has no theme line, so the menu keeps the
-- Squad look these checks were written for (a folder without a settings file is a new installation: Crimson)
do
    local cfgDir = dir .. '/config/addons/servermenu'
    if package.config:sub(1, 1) == '\\' then os.execute('mkdir "' .. cfgDir:gsub('/', '\\') .. '" 2>nul') else os.execute('mkdir -p "' .. cfgDir .. '"') end
    local f = assert(io.open(cfgDir .. '/settings.cfg', 'w')); f:write('scale=1\n'); f:close()
end
    AshitaCore = { GetChatManager = function() return chat end, GetInstallPath = function() return dir .. '/' end, GetPacketManager = function() return pm end,
                   GetMemoryManager = function() return setmetatable({}, { __index = function() return function() return setmetatable({}, { __index = function() return function() return '' end end }) end end }) end }
    function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
    package.loaded['common'] = true
    package.loaded['imgui'] = nil
    package.preload['imgui'] = function() return makeImgui(W) end
    package.preload['ffi'] = function() error('no ffi') end
    package.preload['d3d8'] = function() error('no d3d8') end
    print = function() end
    assert(loadfile(MENU))()
    W.handlers.load()

    local answers, seen, lastChatLine = {}, 0, -100
    local function line(text) W.handlers.text_in({ message = text, blocked = false }) end
    local function answer(at)
        local tr = opts.truth(at)
        line('squadpanel:5|Kyo|BLM|30|-|0|damage|balanced|' .. (tr and '1' or '0') .. '|15')
        if opts.rs ~= false then
            if tr == nil then
                line('squadpanel:rs|5|off|-|0|-|' .. (opts.sel and opts.sel(at) or '8|Basic Black Mage') .. '|0|0|-')
            else
                line(string.format('squadpanel:rs|5|%s|%s|%d|%s|%s|0|0|BLM', tr.state, tr.why or '-', tr.live or 0, tr.liveName or '-',
                    tr.selText or '8|Basic Black Mage'))
            end
        end
        if opts.chan then line('squadpanel:chan|1') end
        line('squadpanel:end')
    end
    -- the user's or Gambits' chat line at time t (a real chat line: it counts for the game's drop rule)
    function W.foreignAt(t, text) W.foreign[#W.foreign + 1] = { at = t, text = text } end
    function W.run(untilT)
        while W.clock < untilT do
            W.clock = W.clock + 0.05
            for _, f in ipairs(W.foreign) do
                if not f.done and W.clock >= f.at then
                    f.done = true
                    lastChatLine = W.clock
                    W.handlers.command({ command = f.text, blocked = false })
                    if f.text:match('^/say !squad panel') then answers[#answers + 1] = { at = W.clock + 0.4, sent = W.clock } end
                end
            end
            while seen < #W.sent do
                seen = seen + 1
                local s = W.sent[seen]
                if s.how == 'typed' then
                    s.gapBefore = s.at - lastChatLine
                    if opts.drop and opts.drop(s, lastChatLine) then s.dropped = true end
                    lastChatLine = s.at
                end
                if has(s.command, '!squad panel') and not s.dropped then
                    answers[#answers + 1] = { at = s.at + (opts.delay and opts.delay(s) or 0.4), sent = s.at }
                end
            end
            table.sort(answers, function(a, b) return a.at < b.at end)
            while answers[1] and W.clock >= answers[1].at do
                local a = table.remove(answers, 1)
                answer(a.sent + 0.1)   -- (the server reads the state when it handles the line)
            end
            W.events = {}
            W.handlers.d3d_present()
            local shown, green = nil, false
            for _, e in ipairs(W.events) do
                if e.kind == 'text' and (has(e.text, 'Checking') or has(e.text, 'Gambits:') or has(e.text, 'Default BLM')
                    or has(e.text, 'Not called') or has(e.text, 'Apply needed')) then
                    shown = (shown and (shown .. ' ') or '') .. e.text
                    if has(e.text, 'Gambits:') and e.color and e.color[2] > 0.8 then green = e.text:match('Gambits: (.+)$') end
                end
            end
            W.frames[#W.frames + 1] = { t = W.clock, shown = shown, green = green }
        end
    end
    function W.asks(from, to)
        local out = {}
        for _, s in ipairs(W.sent) do if has(s.command, '!squad panel') and s.at >= (from or 0) and s.at < (to or 1e9) then out[#out + 1] = s end end
        return out
    end
    -- the first frame at or after t showing fragment
    function W.firstShown(fragment, from)
        for _, f in ipairs(W.frames) do if f.t >= (from or 0) and f.shown and has(f.shown, fragment) then return f.t end end
        return nil
    end
    -- the first frame at or after t where the set is shown as running (green)
    function W.firstGreen(name, from)
        for _, f in ipairs(W.frames) do if f.t >= (from or 0) and f.green == name then return f.t end end
        return nil
    end
    -- frames that show a set as running (green) while the stand-in server did not run it (0.5 s answer grace)
    function W.falseGreen()
        local bad = {}
        for _, f in ipairs(W.frames) do
            if f.green then
                local a, b = opts.truth(f.t), opts.truth(f.t - 0.5)
                local ok = (a and a.state == 'set' and a.liveName == f.green) or (b and b.state == 'set' and b.liveName == f.green)
                if not ok then bad[#bad + 1] = string.format('%.1f %s', f.t, f.green) end
            end
        end
        return bad
    end
    function W.finish() print = realPrint end
    W.handlers.command({ command = '/sq', blocked = false })
    return W
end

-- the server's truth for one Assign & Apply: before T0 job rules; T0..T1 pending (chosen, not applied); T1..T1+back away;
-- then the set runs. back = nil: the mate never comes back (a failed re-call)
local function assignApply(T0, T1, back, name)
    name = name or 'Basic Black Mage'
    return function(t)
        if t < T0 then return { state = 'job', selText = '0|-' } end
        if t < T1 then return { state = 'pending', why = 'choice' } end
        if back == nil or t < T1 + back then return nil end
        return { state = 'set', live = 8, liveName = name }
    end
end
-- Gambits' lines for one Assign & Apply at T0 (from the map-server log: reapply 4.4-5.1 s after ruleset)
local function gambitsLines(W, T0, T1)
    W.foreignAt(T0, '/say !squad ruleset 5 8'); W.foreignAt(T0 + 1.0, '/say !gsq r 1'); W.foreignAt(T0 + 3.5, '/say !gsq r 2')
    W.foreignAt(T1, '/say !squad reapply'); W.foreignAt(T1 + 1.0, '/say !gsq r 3'); W.foreignAt(T1 + 6.0, '/say !gsq r 4')
end
local function minGap(W, from)
    local m = 1e9
    for _, s in ipairs(W.sent) do if s.how == 'typed' and s.at >= from and s.gapBefore then m = math.min(m, s.gapBefore) end end
    return m
end
local DROP_22 = function(s, last) return s.at - last < 2.2 end   -- the game drops a line typed < 2.2 s after another

-- ================================================================= 1. no message loss
section('1. Assign & Apply, nothing lost')
local T0, T1 = 110, 114.6
local W = session({ truth = assignApply(T0, T1, 4.0) })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(160)
local green = W.firstGreen('Basic Black Mage', T0)
check(green and green - T1 <= 10, string.format('green %.1f s after Apply (was about 17.5 s): %s', (green or 0) - T1, tostring(green)))
check(W.firstShown('Apply needed', T0) ~= nil, 'Apply needed is shown between Assign and Apply')
check(#W.falseGreen() == 0, 'never green before the server runs the set: ' .. table.concat(W.falseGreen(), '; '))
check(minGap(W, T0) >= 2.2 - 0.06, string.format('every typed menu line waited 2.2 s after the line before it (min %.2f s)', minGap(W, T0)))
local extra = #W.asks(T0, T1 + 12)
check(extra <= 5, 'asks between Assign and Apply + 12 s: ' .. extra .. ' (at most two plans of three, overlapping ones skipped)')
W.finish()

-- ================================================================= 2. the first ask after the change is lost
section('2. the first ask after a change is lost')
local dropped = 0
W = session({ truth = assignApply(T0, T1, 4.0), drop = function(s) if s.at > T1 and dropped == 0 and has(s.command, 'panel') then dropped = 1 return true end end })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(160)
green = W.firstGreen('Basic Black Mage', T0)
check(dropped == 1, 'one ask after Apply was dropped')
check(green and green - T1 <= 12, string.format('still green %.1f s after Apply', (green or 0) - T1))
check(#W.falseGreen() == 0, 'no false green')
W.finish()

-- the game's real drop rule (< 2.2 s after another line): M1 keeps the menu out of it
section('2b. the game drops lines typed < 2.2 s after another chat line')
W = session({ truth = assignApply(T0, T1, 4.0), drop = DROP_22 })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(160)
local lost = 0
for _, s in ipairs(W.sent) do if s.dropped then lost = lost + 1 end end
green = W.firstGreen('Basic Black Mage', T0)
check(lost == 0, 'no menu line dropped (M1): ' .. lost)
check(green and green - T1 <= 10, string.format('green %.1f s after Apply (the deployed menu: about 33 s)', (green or 0) - T1))
W.finish()

-- ================================================================= 3. an answer after the 3 s timeout
section('3. a late answer (after 3 s) to an ask sent BEFORE the change confirms nothing')
-- the menu asks at about 102 (opening); the change comes at 102.5; that ask is answered only at 107 with the OLD state
local early = nil
W = session({ truth = function(t) if t < 102.5 then return { state = 'job', selText = '0|-' } end return { state = 'set', live = 8, liveName = 'Basic Black Mage' } end,
              delay = function(s) if early == nil and has(s.command, 'panel') then early = s.at return 5.0 end return 0.4 end })
W.foreignAt(102.5, '/say !squad ruleset 5 8')
W.run(130)
check(early ~= nil and early < 102.5, string.format('the delayed ask was sent before the change (%.2f)', early or -1))
local firstNotChecking = nil
for _, f in ipairs(W.frames) do
    if f.t > 102.5 and f.shown and not has(f.shown, 'Checking') and not firstNotChecking then firstNotChecking = f end
end
check(firstNotChecking and firstNotChecking.t > early + 5.0, string.format('the late answer (at %.1f) did not end Checking; it ended at %.1f',
      (early or 0) + 5, firstNotChecking and firstNotChecking.t or -1))
check(firstNotChecking and has(firstNotChecking.shown, 'Gambits: Basic Black Mage'), 'what ended it was the fresh state: ' .. tostring(firstNotChecking and firstNotChecking.shown))
check(#W.falseGreen() == 0, 'no false green')
W.finish()

section('3b. an ask after the change answered late (5 s) still counts for that ask')
local n = 0
W = session({ truth = assignApply(T0, T1, 4.0), delay = function(s) if s.at > T1 + 5 and has(s.command, 'panel') then n = n + 1 if n == 1 then return 5.0 end end return 0.4 end })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(160)
check(#W.falseGreen() == 0, 'no false green with a late answer')
check(W.firstGreen('Basic Black Mage', T0) ~= nil, 'green in the end')
W.finish()

-- ================================================================= 4. rapid Gambits commands
section('4. several Gambits commands in two seconds: one plan, no flood')
W = session({ truth = function(t) if t < 110 then return { state = 'job', selText = '0|-' } end
                                  if t < 111.8 then return { state = 'pending', why = 'choice' } end
                                  return { state = 'pending', why = 'choice', selText = '9|Defensive Black Mage' } end })
W.run(109.95)
W.foreignAt(110.0, '/say !squad ruleset 5 8'); W.foreignAt(110.6, '/say !squad ruleset 5 9'); W.foreignAt(111.2, '/say !squad role 5 healer')
W.foreignAt(111.8, '/say !squad ruleset 5 9')
W.run(140)
local burst = W.asks(110, 125)
check(#burst >= 1 and #burst <= 3, 'asks in the 15 s after the last change: ' .. #burst)
check(burst[1] and burst[1].at >= 111.8 + 2.2 - 0.06, string.format('the first ask waits 2.2 s after the last Gambits line (%.2f)', burst[1] and burst[1].at or -1))
check(W.firstShown('Apply needed', 112) ~= nil and has(W.frames[#W.frames].shown, 'Apply needed'), 'ends on the latest choice: Apply needed')
W.finish()

-- ================================================================= 5. repeated Apply
section('5. Apply twice, 5 s apart')
W = session({ truth = function(t)
    if t < 110 then return { state = 'job', selText = '0|-' } end
    if t < 114.6 then return { state = 'pending', why = 'choice' } end
    if t < 118.6 then return nil end
    if t < 119.6 then return { state = 'set', live = 8, liveName = 'Basic Black Mage' } end
    if t < 123.6 then return nil end
    return { state = 'set', live = 8, liveName = 'Basic Black Mage' } end })
W.run(109.95); gambitsLines(W, 110, 114.6); W.foreignAt(119.6, '/say !squad reapply')
W.run(170)
check(#W.falseGreen() == 0, 'no false green across two re-calls: ' .. table.concat(W.falseGreen(), '; '))
local g2 = W.firstGreen('Basic Black Mage', 119.6)
check(g2 and g2 - 119.6 <= 10, string.format('green %.1f s after the second Apply', (g2 or 0) - 119.6))
W.finish()

-- ================================================================= 6. your own chat
section('6. chat lines you type: the menu waits 2.2 s after them, never changes them')
W = session({ truth = function() return { state = 'job', selText = '0|-' } end })
W.run(105)
W.foreignAt(105.0, '/say hello'); W.foreignAt(105.5, '/p hi'); W.foreignAt(106.0, '/l anyone?')
W.foreignAt(106.5, '/echo not a chat line')
W.run(150)
local after = W.asks(105, 150)
local firstAfter = nil
for _, s in ipairs(W.sent) do if s.at >= 105 and s.how == 'typed' then firstAfter = firstAfter or s end end
check(firstAfter == nil or firstAfter.at >= 106.0 + 2.2 - 0.06, string.format('first menu line after your chat: %.2f (>= 108.2)', firstAfter and firstAfter.at or -1))
W.finish()
section('6b. !squad panel you type yourself: its answer is not taken for a menu ask')
W = session({ truth = function(t) if t < 110.5 then return { state = 'job', selText = '0|-' } end return { state = 'pending', why = 'choice' } end })
W.run(110); W.foreignAt(110.0, '/say !squad panel'); W.foreignAt(110.5, '/say !squad ruleset 5 8'); W.run(140)
check(W.firstShown('Apply needed', 110.5) ~= nil, 'the change is confirmed by a fresh ask')
check(#W.falseGreen() == 0, 'no false green')
W.finish()

-- ================================================================= 7. a change while an ask is waiting
section('7. a change while a refresh is already on its way')
W = session({ truth = function(t) if t < 110.2 then return { state = 'job', selText = '0|-' } end return { state = 'pending', why = 'choice' } end,
              delay = function(s) return 1.5 end })
W.run(109.9)
W.command = function(c) W.handlers.command({ command = c, blocked = false }) end
W.command('/sq refresh')                      -- the menu asks now (answer in 1.5 s)
W.foreignAt(110.2, '/say !squad ruleset 5 8')
W.run(140)
local asks7 = W.asks(109, 125)
local dup = false
for i = 2, #asks7 do if asks7[i].at - asks7[i - 1].at < 2.2 - 0.06 then dup = true end end
check(not dup, 'no two asks closer than 2.2 s')
local fresh = W.firstShown('Apply needed', 110.2)
local preAnswer = asks7[1] and asks7[1].at < 110.2
check(preAnswer and fresh and fresh > asks7[1].at + 1.5 + 0.05, 'the answer to the ask sent before the change does not end Checking')
W.finish()

-- ================================================================= 8. no changes: the 15 s refresh only
section('8. no changes for 60 s: only the normal 15 s refresh')
W = session({ truth = function() return { state = 'set', live = 8, liveName = 'Basic Black Mage', selText = '8|Basic Black Mage' } end })
W.run(103)
local before8 = #W.asks(0, 103)
W.run(163)
local a8 = W.asks(103, 163)
check(#a8 == 4, '60 s, 4 asks (every 15 s): ' .. #a8)
for i = 2, #a8 do check(math.abs((a8[i].at - a8[i - 1].at) - 15) < 0.2, string.format('ask %d after %.2f s', i, a8[i].at - a8[i - 1].at)) end
W.finish()

-- ================================================================= 9. an older server
section('9. an older server (no rs lines): no Rules row, at most one extra ask')
W = session({ truth = assignApply(T0, T1, 4.0), rs = false })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(160)
local anyRules = false
for _, f in ipairs(W.frames) do if f.shown then anyRules = true end end
check(not anyRules, 'no Rules row ever')
check(#W.asks(T0, T1 + 15) <= 4, 'asks after the changes: ' .. #W.asks(T0, T1 + 15))
W.finish()

-- ================================================================= 10. delayed and failed Apply
section('10. a slow re-call (12 s) and a failed one: never a false green')
W = session({ truth = assignApply(T0, T1, 12.0) })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(170)
check(#W.falseGreen() == 0, 'slow re-call: no false green')
local g10 = W.firstGreen('Basic Black Mage', T0)
check(g10 and g10 >= T1 + 12.0, string.format('green only after the mate is back (%.1f >= %.1f)', g10 or -1, T1 + 12))
W.finish()
W = session({ truth = assignApply(T0, T1, nil) })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(170)
check(#W.falseGreen() == 0 and W.firstShown('Gambits:', T1) == nil or not has(W.frames[#W.frames].shown or '', 'Gambits: Basic Black Mage  '),
      'failed re-call: no green')
check(has(W.frames[#W.frames].shown or '', 'Not called'), 'failed re-call ends on "Not called": ' .. tostring(W.frames[#W.frames].shown))
check(#W.asks(T1, T1 + 14) <= 3, 'no more than three asks for the plan: ' .. #W.asks(T1, T1 + 14))
W.finish()

-- ================================================================= M1 without competition, and the packet path
section('M1: no extra wait without another line; packets never wait')
W = session({ truth = assignApply(T0, T1, 4.0) })
W.run(109.95); W.handlers.command({ command = '/sq refresh', blocked = false }); W.run(111)
local own = W.asks(109.9, 111)
check(own[1] and own[1].at - 109.95 < 0.3, string.format('a refresh with no other line goes at once (%.2f s)', own[1] and own[1].at - 109.95 or -1))
W.finish()
W = session({ truth = assignApply(T0, T1, 4.0), chan = true })
W.run(T0 - 0.05); gambitsLines(W, T0, T1); W.run(160)
local packets = 0
for _, s in ipairs(W.sent) do if s.how == 'packet' and s.at > T0 then packets = packets + 1 end end
check(packets > 0, 'with the addon channel the asks go as packets (' .. packets .. ')')
local gPacket = W.firstGreen('Basic Black Mage', T0)
check(gPacket and gPacket - T1 <= 9, string.format('packet path: green %.1f s after Apply', (gPacket or 0) - T1))
check(#W.falseGreen() == 0, 'packet path: no false green')
W.finish()

print = realPrint
io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
