-- The Squads menu's Rules line (servermenu 1.26n, 2026-11-24): what a called squad mate really runs, from the server's
-- squadpanel:rs|... line (squad_rulesets.lua R.panelLine), the selected Rule Set and "Apply needed". The menu never
-- decides that a set runs: an old server (no rs line) draws no Rules line, and after a change the line says
-- "Checking..." until an answer to a !squad panel sent after that change arrives. Stand-in Ashita and ImGui; nothing is
-- written outside a temporary folder.
--   luajit test_squad_ruleset_status_ui.lua          (Lua 5.4: lua test_squad_ruleset_status_ui.lua)
local HERE = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local KIT = HERE .. '/../..'
io.stdout:setvbuf('no')
local passed, failed = 0, 0
local function check(cond, label) if cond then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(name) io.write('\n== ', name, '\n') end
local function has(text, needle) return tostring(text):find(needle, 1, true) ~= nil end
local realPrint = print
local SAID = {}

-- ---------------------------------------------------------------- a stand-in ImGui that records text and tooltips
local function makeImgui(W)
    local im = setmetatable({}, { __index = function() return function() end end })
    local function event(kind, text, color) W.events[#W.events + 1] = { kind = kind, text = tostring(text), color = color } end
    function im.GetFontSize() return 13 end
    function im.BeginTooltip() W.inTip = true return true end
    function im.EndTooltip() W.inTip = false end
    function im.TextUnformatted(t) event(W.inTip and 'tip' or 'text', t) end
    function im.Begin() W.balance = W.balance + 1 return true end
    function im.End() W.balance = W.balance - 1 end
    function im.BeginChild(id, size) W.children[#W.children + 1] = { id = tostring(id), h = type(size) == 'table' and size[2] or nil } return true end
    function im.Button(l) event('button', l) return false end
    function im.Text(t) event('text', t) end
    function im.TextWrapped(t) event('text', t) end
    function im.TextColored(c, t) event('text', t, c) end
    function im.BeginCombo(id, preview) event('combo', id .. '=' .. tostring(preview)) return false end
    function im.Selectable() return false end
    function im.Checkbox() return false end
    function im.InputText() return false end
    function im.CollapsingHeader() return false end
    function im.IsItemHovered() return true end
    function im.SetTooltip(t) event('tip', t) end
    function im.GetWindowWidth() return 620 end
    function im.GetContentRegionAvail() return { 600, 400 } end
    function im.GetCursorScreenPos() return { 0, 0 } end
    function im.GetWindowDrawList() return setmetatable({}, { __index = function() return function() end end }) end
    function im.ColorConvertFloat4ToU32() return 0 end
    function im.CalcTextSize(t) return { #tostring(t) * 7, 13 } end
    function im.GetWindowPos() return 0, 0 end
    return im
end

local function boot(path)
    local W = { handlers = {}, events = {}, sent = {}, balance = 0, clock = 100, children = {} }
    local chat = {}
    function chat:QueueCommand(_, command) W.sent[#W.sent + 1] = { at = W.clock, command = command } end
    function chat:IsInputOpen() return false end
    local dir = os.tmpname(); os.remove(dir)
    if package.config:sub(1, 1) == '\\' then os.execute('mkdir "' .. dir .. '" 2>nul') else os.execute('mkdir -p "' .. dir .. '"') end
-- (servermenu 1.27) an installation from before themes: its settings file has no theme line, so the menu keeps the
-- Squad look these checks were written for (a folder without a settings file is a new installation: Crimson)
do
    local cfgDir = dir .. '/config/addons/servermenu'
    if package.config:sub(1, 1) == '\\' then os.execute('mkdir "' .. cfgDir:gsub('/', '\\') .. '" 2>nul') else os.execute('mkdir -p "' .. cfgDir .. '"') end
    local f = assert(io.open(cfgDir .. '/settings.cfg', 'w')); f:write('scale=1\n'); f:close()
end
    addon = {}
    ashita = { events = { register = function(name, _, fn) W.handlers[name] = fn end }, time = { get_tick64 = function() return W.clock * 1000 end },
               fs = { create_directory = function() end } }
    AshitaCore = { GetChatManager = function() return chat end, GetInstallPath = function() return dir .. '/' end,
                   GetMemoryManager = function() return setmetatable({}, { __index = function() return function() return setmetatable({}, { __index = function() return function() return '' end end }) end end }) end }
    function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
    package.loaded['common'] = true
    package.loaded['imgui'] = nil
    package.preload['imgui'] = function() return makeImgui(W) end
    package.loaded['ffi'], package.loaded['d3d8'] = nil, nil
    package.preload['ffi'] = function() error('no ffi here') end
    package.preload['d3d8'] = function() error('no d3d8 here') end
    for name, v in pairs({ ImGuiCol_Button = 21, ImGuiCol_ButtonHovered = 22, ImGuiCol_ButtonActive = 23, ImGuiCol_Text = 0, ImGuiCol_WindowBg = 2,
                           ImGuiStyleVar_WindowRounding = 3, ImGuiCond_FirstUseEver = 4, ImGuiCond_Always = 1, ImGuiWindowFlags_NoTitleBar = 1,
                           ImGuiWindowFlags_NoMove = 4, ImGuiCol_PlotHistogram = 40 }) do rawset(_G, name, v) end
    print = function(...) local p = {} for i = 1, select('#', ...) do p[#p + 1] = tostring((select(i, ...))) end SAID[#SAID + 1] = table.concat(p, ' ') end
    assert(loadfile(path))()
    W.handlers.load()
    function W.frame() W.clock = W.clock + 0.25; W.events = {}; W.children = {}; W.handlers.d3d_present() end
    function W.frames(n) for _ = 1, n do W.frame() end end
    function W.command(text) local e = { command = text, blocked = false } W.handlers.command(e) return e end
    function W.line(text) local e = { message = text, blocked = false } W.handlers.text_in(e) return e end
    function W.text(fragment)
        for i, e in ipairs(W.events) do
            if e.kind == 'text' and has(e.text, fragment) then
                local nxt = W.events[i + 1]
                return e, nxt and nxt.kind == 'tip' and nxt.text or nil
            end
        end
        return nil
    end
    function W.count(fragment)
        local n = 0
        for _, e in ipairs(W.events) do if e.kind == 'text' and has(e.text, fragment) then n = n + 1 end end
        return n
    end
    function W.panelsSent()
        local n = 0
        for _, s in ipairs(W.sent) do if has(s.command, '!squad panel') then n = n + 1 end end
        return n
    end
    function W.cardHeight(slot)
        for _, c in ipairs(W.children) do if c.id == '##sm_mate' .. slot then return c.h end end
        return nil
    end
    return W
end

local MATES = {
    'squadpanel:1|Aldric|BLM|30|-|0|damage|balanced|1|15',
    'squadpanel:2|Mira|WHM|30|-|0|damage|balanced|1|15',
    'squadpanel:3|Kyo|BLM|30|-|0|damage|balanced|1|15',
    'squadpanel:4|Sera|BLM|30|-|0|auto|balanced|0|15',
}
-- the server's rs lines (squad_rulesets.lua R.panelLine): slot|state|why|live|live name|chosen|chosen name|fb|left out|job
local RS = {
    'squadpanel:rs|1|set|-|1|Basic Black Mage|1|Basic Black Mage|0|0|BLM',
    'squadpanel:rs|2|job|-|0|-|0|-|0|0|WHM',
    'squadpanel:rs|3|pending|choice|1|Basic Black Mage|2|Defensive Black Mage|0|0|BLM',
    'squadpanel:rs|4|off|-|0|-|1|Basic Black Mage|0|0|-',
}
local function answer(W, lines, extra)
    for _, l in ipairs(MATES) do W.line('[Hurami] : ' .. l) end
    for _, l in ipairs(lines or {}) do W.line('[Hurami] : ' .. l) end
    for _, l in ipairs(extra or {}) do W.line('[Hurami] : ' .. l) end
    W.line('[Hurami] : squadpanel:end')
    W.frame()
end
local GOOD, WARN = { 0.42, 0.85, 0.52, 1 }, { 0.96, 0.76, 0.36, 1 }
local function same(a, b) return a and b and a[1] == b[1] and a[2] == b[2] and a[3] == b[3] end

-- ================================================================= an older server: no Rules line
section('an older server (no rs lines): no Rules line, cards as before')
local W = boot(KIT .. '/addons-src/servermenu/servermenu.lua')
W.command('/sq'); W.frame()
answer(W, nil)
check(W.balance == 0, 'every Begin has its End')
check(W.count('Rules') == 0 and W.count('Gambits:') == 0 and W.count('Checking') == 0, 'no Rules line at all')
local oldHeight = W.cardHeight(1)
check(oldHeight == 82, 'the card has the height of one without a Rules row (1.28: 82): ' .. tostring(oldHeight))
check(W.text('(i) WHM - Role: Damage') ~= nil, 'the gold Role note is shown as before (WHM on Damage)')

-- ================================================================= the four example states
section('a server with the rs line: Active, Default, Apply needed, Not called')
answer(W, RS)
check(W.balance == 0, 'every Begin has its End')
check(W.cardHeight(1) == oldHeight + 23, 'the card is one row (1.28: 23) taller: ' .. tostring(W.cardHeight(1)))
check(W.count('Rules') == 4, 'one Rules line per mate (' .. W.count('Rules') .. ')')
local e1, tip1 = W.text('Gambits: Basic Black Mage')
check(e1 and same(e1.color, GOOD), 'Example A: "Gambits: Basic Black Mage" in green')
check(tip1 and has(tip1, 'Currently using: Gambits: Basic Black Mage') and has(tip1, 'Selected Rule Set: Basic Black Mage')
      and has(tip1, 'Squad Role: Damage (not used while a Rule Set runs)') and has(tip1, 'Active'), 'Example A tooltip: ' .. tostring(tip1))
local e2, tip2 = W.text('Default WHM job rules (Damage)')
check(e2 ~= nil and not same(e2.color, GOOD), 'Example D: "Default WHM job rules (Damage)", not green')
check(tip2 and has(tip2, 'Selected Rule Set: None') and has(tip2, 'filters only the default job rules'), 'Example D tooltip: ' .. tostring(tip2))
check(W.text('(i) WHM - Role: Damage') ~= nil, 'WHM on job rules: the gold Role note stays')
local e3, tip3 = W.text('  Apply needed')
check(e3 and same(e3.color, WARN), 'Example C: "Apply needed" in the warning colour')
check(tip3 and has(tip3, 'Currently using: Gambits: Basic Black Mage') and has(tip3, 'Selected Rule Set: Defensive Black Mage')
      and has(tip3, 'Next call: Gambits: Defensive Black Mage') and has(tip3, 'Another Rule Set'), 'Example C tooltip: ' .. tostring(tip3))
check(W.text('Not called.  Next call: Gambits: Basic Black Mage') ~= nil, 'a mate who is away: "Not called. Next call: ..."')
check(W.text('Changes take effect when your mates are called again.') ~= nil, 'the Apply now banner shows for a pending mate')
local greens = 0
for _, e in ipairs(W.events) do if e.kind == 'text' and same(e.color, GOOD) and has(e.text, 'Gambits:') then greens = greens + 1 end end
check(greens == 1, 'only the mate whose set really runs is green (' .. greens .. ')')

section('Example B: job rules running, a set chosen')
answer(W, { 'squadpanel:rs|1|pending|choice|0|-|1|Basic Black Mage|0|0|BLM' })
local eB, tipB = W.text('Default BLM job rules (Damage)')
check(eB ~= nil and W.text('  Apply needed') ~= nil, 'Default BLM job rules (Damage)  Apply needed')
check(tipB and has(tipB, 'Next call: Gambits: Basic Black Mage'), 'tooltip names the next call')
check(W.count('Rules') == 1, 'mates without an rs line in the answer get no Rules line (' .. W.count('Rules') .. ')')

section('Role note hidden while a set runs')
MATES[1] = 'squadpanel:1|Aldric|WHM|30|-|0|damage|balanced|1|15'
answer(W, { 'squadpanel:rs|1|set|-|3|WHM Cure|3|WHM Cure|0|0|WHM' })
check(W.text('(i) WHM - Role: Damage') ~= nil, 'mate 2 (job rules): its note stays')
check(W.count('(i) WHM - Role: Damage') == 1, 'mate 1 (WHM set running): no gold note (' .. W.count('(i) WHM - Role: Damage') .. ' notes)')
MATES[1] = 'squadpanel:1|Aldric|BLM|30|-|0|damage|balanced|1|15'

section('fallback, rules left out, unknown, add-on, trust rules')
answer(W, { 'squadpanel:rs|1|fallback|-|0|-|1|?|1|0|BLM', 'squadpanel:rs|2|set|-|3|WHM Cure|3|WHM Cure|0|2|WHM',
            'squadpanel:rs|3|unknown|-|0|-|1|Basic Black Mage|0|0|-', 'squadpanel:rs|4|addon|-|0|-|0|-|0|0|-' })
local eF, tipF = W.text('  Rule Set not used')
check(eF and same(eF.color, WARN) and tipF and has(tipF, 'Fallback: the chosen Rule Set no longer exists'), 'fallback (gone): warning + reason: ' .. tostring(tipF))
check(W.text('Default BLM job rules (Damage)') ~= nil, 'fallback shows what runs: Default BLM job rules')
local eD = W.text('(2 rules skipped)')   -- (1.28: "skipped"; 1.27 said "left out". The same count from the server.)
check(eD and same(eD.color, WARN), 'a set with rules the mate cannot use: "(2 rules skipped)"')
check(W.text('Not reported') ~= nil and W.text('Run by an add-on') ~= nil, 'unknown and add-on states are neutral texts')
answer(W, { 'squadpanel:rs|1|fallback|-|0|-|0|-|4|0|SCH' })
check(W.text('SCH trust\'s own rules') ~= nil and W.text('Rule Set not used') == nil, 'a job without Squads rules and no set: "SCH trust\'s own rules", no warning')
answer(W, { 'squadpanel:rs|1|fallback|-|0|-|2|Defensive Black Mage|3|1|BLM' })
local _, tipU = W.text('  Rule Set not used')
check(tipU and has(tipU, 'none of its rules can be used'), 'fallback (unusable): its reason')

section('malformed lines are ignored, never shown as active')
answer(W, { 'squadpanel:rs|1|active|-|1|Basic Black Mage|1|Basic Black Mage|0|0|BLM', 'squadpanel:rs|2|set|-|1|Short',
            'squadpanel:rs|x|set|-|1|A|1|A|0|0|BLM' })
check(W.count('Rules') == 0 and W.count('Gambits:') == 0, 'an unknown state, too few fields, a bad slot: no Rules line')
check(W.balance == 0, 'every Begin has its End')

-- ================================================================= stale answers
section('after a change: "Checking..." until an answer to a panel sent after it')
answer(W, RS)
W.sent = {}
local cmd = W.command('/say !squad ruleset 1 2')     -- (as Gambits sends it)
check(cmd.blocked == false, 'the command is not blocked (it still goes to the server)')
W.frame()
local eC = W.text('Checking...')
check(eC ~= nil and W.text('Gambits: Basic Black Mage') ~= nil, 'mate 1 says Checking..., mate 3 (another slot) is still shown')
check(W.count('Checking...') == 1, 'only the changed mate is checking')
answer(W, RS)                                         -- an answer that was on its way already (no panel sent since)
check(W.text('Checking...') ~= nil, 'an old answer does not end the check: still Checking...')
W.frames(30)                                           -- the menu asks again soon (about 2 s) and sends it
check(W.panelsSent() >= 1, 'a new !squad panel was sent after the change (' .. W.panelsSent() .. ')')
answer(W, { 'squadpanel:rs|1|pending|choice|1|Basic Black Mage|2|Defensive Black Mage|0|0|BLM' })
check(W.text('Checking...') == nil and W.text('  Apply needed') ~= nil, 'the fresh answer: Apply needed (the change seen), no Checking')

section('Apply now / reapply: every mate checks until the fresh answer')
answer(W, RS)
W.command('/say !squad reapply')
W.frame()
check(W.count('Checking...') == 4, 'reapply: all four mates say Checking... (' .. W.count('Checking...') .. ')')
check(W.text('Gambits: Basic Black Mage') == nil, 'no green "running" while checking')
W.frames(30)
answer(W, { 'squadpanel:rs|1|set|-|2|Defensive Black Mage|2|Defensive Black Mage|0|0|BLM' })
check(W.text('Gambits: Defensive Black Mage') ~= nil and W.count('Checking...') == 0, 'after the fresh answer: the new set runs')

section('the menu\'s own clicks (enqueue) and other commands')
answer(W, RS)
W.command('/say !squad role 3 healer')
W.frame()
check(W.count('Checking...') == 1, '!squad role 3: mate 3 checks')
W.frames(30); answer(W, RS)
W.command('/say !squad attack')
W.frame()
check(W.count('Checking...') == 0, '!squad attack: nothing to check')
W.command('/say hello')
W.frame()
check(W.count('Checking...') == 0, 'other chat: nothing to check')

section('no crash, version')
local crashed = false
for _, s in ipairs(SAID) do if has(s, 'hit a problem') then crashed = true end end
check(not crashed, 'the menu never hit a render error')
local src = io.open(KIT .. '/addons-src/servermenu/servermenu.lua', 'rb'):read('*a')
check(src:match("addon%.version = '([^']+)'") == '1.35', 'servermenu version 1.35')
print = realPrint
io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
