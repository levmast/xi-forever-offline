-- xifo_ui.lua (servermenu 1.27 / Gambits 0.3.4): the shared palettes, the ImGui helpers that cannot leave a stack
-- unbalanced or read a text as a printf format, and the character's shared theme choice. No game, no Ashita; the
-- files it writes are in a temporary folder.
--   luajit test_xifo_ui.lua          (Lua 5.4: lua test_xifo_ui.lua)
local HERE = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local KIT = HERE .. '/../..'
io.stdout:setvbuf('no')
local passed, failed = 0, 0
local function check(c, label) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function slurp(p) local f = io.open(p, 'rb') if not f then return nil end local s = f:read('*a') f:close() return (s:gsub('\r\n', '\n')) end
local function near(a, b) return math.abs(a - b) < 1e-9 end
local function same(c, e) return type(c) == 'table' and near(c[1], e[1]) and near(c[2], e[2]) and near(c[3], e[3]) and near(c[4] or 1, e[4] or 1) end

local A, B = KIT .. '/addons-src/servermenu/xifo_ui.lua', KIT .. '/addons-src/Gambits/xifo_ui.lua'
local U = dofile(A)

section('one file, two identical copies')
check(slurp(A) ~= nil and slurp(A) == slurp(B), 'addons-src/servermenu/xifo_ui.lua and addons-src/Gambits/xifo_ui.lua are the same text')

section('the palettes are the Gambits editor\'s, value for value (0.3.3)')
-- written down from squad_editor.lua 0.3.3 (M.THEMES): a change of any of these is a colour change
local OLD = {
    classic = { window = { 0.105, 0.095, 0.082 }, panel = { 0.105, 0.095, 0.082 }, header = { 0.23, 0.18, 0.10 }, button = { 0.24, 0.19, 0.10 },
                border = { 0.2875, 0.225, 0.125 }, text = { 0.91, 0.89, 0.80 }, gold = { 0.82, 0.63, 0.22 }, tabSel = { 0.53, 0.42, 0.09 },
                rowSel = { 0.53, 0.42, 0.09 }, muted = { 0.47, 0.44, 0.36 }, secondary = { 0.64, 0.60, 0.50 }, goGold = { 0.82, 0.62, 0.10 },
                goText = { 0.10, 0.08, 0.05 }, ok = { 0.55, 0.80, 0.45 }, bad = { 0.90, 0.35, 0.30 }, dot = { 0.86, 0.67, 0.22 } },
    squad = { window = { 0.067, 0.075, 0.106 }, panel = { 0.110, 0.118, 0.161 }, header = { 0.150, 0.165, 0.220 }, button = { 0.169, 0.188, 0.255 },
              border = { 0.300, 0.320, 0.400, 0.55 }, text = { 0.902, 0.922, 0.949 }, gold = { 0.890, 0.741, 0.400 }, tabSel = { 0.600, 0.470, 0.190 },
              rowSel = { 0.215, 0.255, 0.360 }, muted = { 0.459, 0.490, 0.549 }, secondary = { 0.580, 0.612, 0.678 }, goGold = { 0.780, 0.620, 0.260 },
              goText = { 0.075, 0.075, 0.095 }, ok = { 0.450, 0.780, 0.500 }, bad = { 0.900, 0.420, 0.400 }, dot = { 0.360, 0.560, 0.880 },
              title = { 0.080, 0.090, 0.125 }, titleActive = { 0.110, 0.125, 0.175 } },
    crimson = { window = { 0.090, 0.068, 0.074 }, panel = { 0.125, 0.090, 0.100 }, header = { 0.215, 0.110, 0.130 }, button = { 0.285, 0.130, 0.155 },
                border = { 0.420, 0.220, 0.250, 0.60 }, text = { 0.930, 0.895, 0.885 }, gold = { 0.900, 0.620, 0.580 }, tabSel = { 0.500, 0.165, 0.205 },
                rowSel = { 0.360, 0.140, 0.175 }, muted = { 0.560, 0.470, 0.480 }, secondary = { 0.700, 0.610, 0.610 }, goGold = { 0.640, 0.215, 0.255 },
                goText = { 0.985, 0.935, 0.925 }, ok = { 0.560, 0.800, 0.520 }, bad = { 0.990, 0.520, 0.440 }, dot = { 0.820, 0.270, 0.370 },
                title = { 0.250, 0.085, 0.105 }, titleActive = { 0.340, 0.115, 0.140 } },
}
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local bad = {}
    for key, want in pairs(OLD[name]) do if not same(U.THEMES[name][key], want) then bad[#bad + 1] = key end end
    check(#bad == 0, name .. ': every colour of 0.3.3 is unchanged' .. (#bad > 0 and (' (changed: ' .. table.concat(bad, ', ') .. ')') or ''))
end
check(U.THEMES.classic.rounding == nil and U.THEMES.squad.rounding.window == 6 and U.THEMES.squad.rounding.child == 5
    and U.THEMES.squad.rounding.frame == 4 and U.THEMES.crimson.frameBorder == 1, 'rounding and frame border as before (Classic has none)')
check(table.concat(U.THEME_ORDER, ' ') == 'classic squad crimson' and U.THEME_NAMES.crimson == 'Crimson', 'the three themes, in the same order')
check(U.DEFAULT == 'crimson', 'the default of a new installation is Crimson')
local c0, n0 = U.theme('nonsense')
check(n0 == 'crimson' and c0 == U.THEMES.crimson and select(2, U.theme('nonsense', 'classic')) == 'classic' and select(2, U.theme('squad')) == 'squad',
      'an unknown name: the fallback given, else the default; a known name is never replaced')

section('the added keys are made from each palette\'s own colours')
for _, name in ipairs({ 'classic', 'crimson' }) do
    local c = U.THEMES[name]
    check(same(c.on, U.times(c.ok, 0.55)) and same(c.onHi, U.times(c.ok, 0.70)) and same(c.warn, c.gold) and same(c.busy, U.times(c.button, 0.80)),
          name .. ': on / onHi from ok, warn = gold, busy from button')
end
check(same(U.THEMES.squad.on, { 0.16, 0.48, 0.28 }) and same(U.THEMES.squad.onHi, { 0.22, 0.60, 0.36 }) and same(U.THEMES.squad.warn, { 0.96, 0.76, 0.36 })
    and same(U.THEMES.squad.busy, { 0.22, 0.24, 0.28 }), 'squad: the Squads menu\'s own "on", "warning" and "waiting" colours')

section('the Squads menu in the Squad theme: its colours of 1.26, value for value')
do
    local m = U.menu('squad')
    local WANT = { gold = { 0.89, 0.74, 0.40 }, text = { 0.88, 0.89, 0.92 }, dim = { 0.56, 0.59, 0.66 }, good = { 0.42, 0.85, 0.52 }, bad = { 0.95, 0.42, 0.40 },
                   warn = { 0.96, 0.76, 0.36 }, hp = { 0.30, 0.70, 0.38 }, mp = { 0.30, 0.50, 0.90 }, on = { 0.16, 0.48, 0.28 }, onHi = { 0.22, 0.60, 0.36 },
                   sel = { 0.55, 0.43, 0.18 }, selHi = { 0.68, 0.54, 0.24 }, panel = { 0.065, 0.075, 0.105, 0.97 }, line = { 0.30, 0.32, 0.40, 0.55 },
                   faint = { 0.46, 0.49, 0.55 } }
    local bad = {}
    for k, want in pairs(WANT) do if not same(m.c[k], want) then bad[#bad + 1] = k end end
    check(#bad == 0, 'the 15 colours of the menu\'s old table C' .. (#bad > 0 and (' (changed: ' .. table.concat(bad, ', ') .. ')') or ''))
    local WIN = { ImGuiCol_WindowBg = { 0.07, 0.08, 0.11, 0.96 }, ImGuiCol_ChildBg = { 0.10, 0.11, 0.15, 0.80 }, ImGuiCol_Border = { 0.32, 0.34, 0.42, 0.55 },
                  ImGuiCol_Button = { 0.17, 0.19, 0.25 }, ImGuiCol_ButtonHovered = { 0.25, 0.28, 0.37 }, ImGuiCol_ButtonActive = { 0.30, 0.34, 0.45 },
                  ImGuiCol_FrameBg = { 0.14, 0.16, 0.21 }, ImGuiCol_FrameBgHovered = { 0.20, 0.22, 0.29 }, ImGuiCol_CheckMark = { 0.89, 0.74, 0.40 },
                  ImGuiCol_Header = { 0.20, 0.22, 0.29 }, ImGuiCol_HeaderHovered = { 0.26, 0.29, 0.38 }, ImGuiCol_Separator = { 0.32, 0.34, 0.42, 0.55 },
                  ImGuiCol_Text = { 0.88, 0.89, 0.92 } }
    -- (1.28) the menu has ImGui's own title bar now: three title colours were added to the list, from the Squad palette's
    -- own title / titleActive. The 13 colours of 1.26 are what they were.
    local TITLE = { ImGuiCol_TitleBg = U.THEMES.squad.title, ImGuiCol_TitleBgActive = U.THEMES.squad.titleActive, ImGuiCol_TitleBgCollapsed = U.THEMES.squad.title }
    -- (2026-11-25) and the four scrollbar colours, the palette's own (U.scrollbar_colors)
    local SCROLL = {}
    for _, pair in ipairs(U.scrollbar_colors(U.THEMES.squad)) do SCROLL[pair[1]] = pair[2] end
    local n, ok, titles, scrolls = 0, true, 0, 0
    for _, pair in ipairs(m.window) do
        if WIN[pair[1]] ~= nil then n = n + 1; ok = ok and same(pair[2], WIN[pair[1]])
        elseif TITLE[pair[1]] ~= nil then titles = titles + 1; ok = ok and same(pair[2], TITLE[pair[1]])
        elseif SCROLL[pair[1]] ~= nil then scrolls = scrolls + 1; ok = ok and same(pair[2], SCROLL[pair[1]])
        else ok = false end
    end
    check(ok and scrolls == 4, 'and the four scrollbar colours of the Squad palette (' .. scrolls .. ')')
    check(ok and n == 13, 'the 13 window colours menuWindow pushed (' .. n .. ')')
    check(ok and titles == 3, 'and the three title bar colours of 1.28, the Squad palette\'s own (' .. titles .. ')')
    local BTN = { ImGuiCol_WindowBg = { 0.05, 0.06, 0.09, 0.70 }, ImGuiCol_Border = { 0.89, 0.74, 0.40, 0.55 }, ImGuiCol_Button = { 0.13, 0.16, 0.26, 0.95 },
                  ImGuiCol_ButtonHovered = { 0.22, 0.27, 0.42 }, ImGuiCol_ButtonActive = { 0.30, 0.36, 0.55 }, ImGuiCol_Text = { 0.89, 0.74, 0.40 } }
    n, ok = 0, true
    for _, pair in ipairs(m.button) do n = n + 1; ok = ok and BTN[pair[1]] ~= nil and same(pair[2], BTN[pair[1]]) end
    check(ok and n == 6, 'the 6 colours of the Squads button')
    local cr = U.menu('crimson')
    check(same(cr.c.gold, U.THEMES.crimson.gold) and same(cr.c.dim, U.THEMES.crimson.secondary) and same(cr.c.good, U.THEMES.crimson.ok)
        and same(cr.c.hp, WANT.hp) and same(cr.c.mp, WANT.mp), 'Crimson fills the same roles from its palette; the HP and MP bar colours are data, the same in every theme')
    check(U.menu('crimson') == cr and U.menu('squad') == m, 'the tables are made once per theme, not every frame')
end

section('the shared metrics are the Gambits window\'s')
do
    local v = U.window_vars(U.THEMES.squad, function(n) return n * 2 end)
    local by = {}
    for _, pair in ipairs(v) do by[pair[1]] = pair[2] end
    check(by.ImGuiStyleVar_WindowPadding[1] == 16 and by.ImGuiStyleVar_FramePadding[1] == 8 and by.ImGuiStyleVar_FramePadding[2] == 6
        and by.ImGuiStyleVar_ItemSpacing[1] == 12 and by.ImGuiStyleVar_ItemSpacing[2] == 8 and by.ImGuiStyleVar_WindowRounding == 12
        and by.ImGuiStyleVar_ChildRounding == 10 and by.ImGuiStyleVar_FrameRounding == 8 and by.ImGuiStyleVar_FrameBorderSize == 1,
          'padding 8x8, frame 4x3, spacing 6x4, rounding 6/5/4 (here at 200 %), frame border 1')
    check(#U.window_vars(U.THEMES.classic) == 4, 'Classic pushes no rounding, as before')
    check(#U.window_colors(U.THEMES.crimson) == 25, 'the 22 window colours of the Gambits window and three more scrollbar colours (2026-11-25)')
end

section('(2026-11-25) scrollbars: one look in both add-ons, from the palette, in every theme')
do
    for _, name in ipairs(U.THEME_ORDER) do
        local c = U.THEMES[name]
        local want = {}
        for _, pair in ipairs(U.scrollbar_colors(c)) do want[pair[1]] = pair[2] end
        check(same(want.ImGuiCol_ScrollbarGrab, c.button) and same(want.ImGuiCol_ScrollbarGrabActive, c.tabSel)
            and want.ImGuiCol_ScrollbarGrabHovered[1] >= c.button[1] and want.ImGuiCol_ScrollbarBg[4] < 1,
            name .. ': grab = the button colour, brighter on hover, the accent while dragged; a faint track')
        local gm, mm = {}, {}
        for _, pair in ipairs(U.window_colors(c)) do gm[pair[1]] = pair[2] end
        for _, pair in ipairs(U.menu(name).window) do mm[pair[1]] = pair[2] end
        local okAll = true
        for k, v in pairs(want) do okAll = okAll and same(gm[k], v) and same(mm[k], v) end
        check(okAll, name .. ': the Gambits window and every Squads window push the same four scrollbar colours')
    end
end

-- ---------------------------------------------------------------- a counting ImGui
local function gui(full)
    local g = { colors = 0, vars = 0, maxColors = 0, setTooltip = {}, textWrapped = {}, unformatted = {}, hovered = true, lines = 0, avail = 100 }
    function g.PushStyleColor() g.colors = g.colors + 1; g.maxColors = math.max(g.maxColors, g.colors) end
    function g.PopStyleColor(n) g.colors = g.colors - (n or 1) end
    function g.PushStyleVar() g.vars = g.vars + 1 end
    function g.PopStyleVar(n) g.vars = g.vars - (n or 1) end
    function g.IsItemHovered() return g.hovered end
    function g.SetTooltip(t) g.setTooltip[#g.setTooltip + 1] = t end
    function g.TextWrapped(t) g.textWrapped[#g.textWrapped + 1] = t end
    function g.Text(t) end
    function g.SameLine() end
    function g.NewLine() g.lines = g.lines + 1 end
    function g.GetContentRegionAvail() return { g.avail, 50 } end
    if full then
        function g.BeginTooltip() return true end
        function g.EndTooltip() end
        function g.TextUnformatted(t) g.unformatted[#g.unformatted + 1] = t end
        function g.PushTextWrapPos(w) g.wrap = w end
        function g.PopTextWrapPos() end
        function g.GetFontSize() return 14 end
    end
    return g
end
for _, name in ipairs({ 'ImGuiCol_Text', 'ImGuiCol_Button', 'ImGuiStyleVar_FramePadding' }) do rawset(_G, name, 1) end

section('a text is never read as a printf format')
do
    local g = gui(true)
    local text = 'DEF:10 Haste+4%\nbelow 30% HP % that'
    check(U.tooltip(g, text) == true and #g.setTooltip == 0 and g.unformatted[1] == text and g.wrap == 14 * 27,
          'tooltip: TextUnformatted with the text as it is, wrapped at 27 em; SetTooltip is not called')
    U.wrapped(g, { 1, 0, 0, 1 }, text)
    check(#g.textWrapped == 0 and g.unformatted[2] == text and g.colors == 0, 'wrapped: TextUnformatted too; the colour is popped')
    g.hovered = false
    check(U.tooltip(g, text) == false and #g.unformatted == 2, 'not hovered: nothing is drawn')
    check(U.tooltip(g, nil) == false, 'no text: nothing')
    local old = gui(false)
    U.tooltip(old, text); U.wrapped(old, nil, text)
    check(old.setTooltip[1] == 'DEF:10 Haste+4%%\nbelow 30%% HP %% that' and old.textWrapped[1] == old.setTooltip[1],
          'a binding without TextUnformatted: every % is doubled (the player still sees one)')
end

section('what is pushed is popped, also when the drawing fails')
do
    local g = gui(true)
    local t = U.push(g, { { 'ImGuiCol_Text', { 1, 1, 1, 1 } }, { 'ImGuiCol_Button', { 1, 1, 1, 1 } }, { 'ImGuiCol_Unknown', { 1, 1, 1, 1 } }, { 'ImGuiCol_Text', nil } },
                     { { 'ImGuiStyleVar_FramePadding', { 1, 1 } } })
    check(g.colors == 2 and g.vars == 1 and t.colors == 2 and t.vars == 1, 'push: only the ids this ImGui has, with a value')
    U.pop(g, t); U.pop(g, t)
    check(g.colors == 0 and g.vars == 0, 'pop: exactly what was pushed, and a second pop does nothing')
    local ok, err = pcall(U.with, g, { { 'ImGuiCol_Text', { 1, 1, 1, 1 } } }, { { 'ImGuiStyleVar_FramePadding', { 1, 1 } } }, function() error('boom', 0) end)
    check(not ok and err == 'boom' and g.colors == 0 and g.vars == 0, 'U.with: the error is raised again after the stacks are back to 0')
    check(U.with(g, nil, nil, function(a) return a + 1 end, 4) == 5 and g.colors == 0, 'U.with returns the function\'s value')
end

section('a control that does not fit starts a new line')
do
    local g = gui(true)
    g.avail = 100
    check(U.same_if_fits(g, 90) == true and g.lines == 0, '90 px in 100: stays on the line')
    check(U.same_if_fits(g, 120) == false and g.lines == 1, '120 px in 100: a new line')
end

-- ---------------------------------------------------------------- the shared theme choice of one character
section('the shared theme choice: one small file per character, written only when a theme is picked')
local dir = os.tmpname(); os.remove(dir)
local win = package.config:sub(1, 1) == '\\'
local function mkdir(p) if win then os.execute('mkdir "' .. p:gsub('/', '\\'):gsub('\\+$', '') .. '" 2>nul') else os.execute('mkdir -p "' .. p .. '"') end end
mkdir(dir)
local install = dir .. '/'
local function exists(p) local f = io.open(p, 'r') if f then f:close() return true end return false end
check(U.identity('Testcharone', 1) == 'Testcharone_1' and U.identity(' Odd name ', 22) == 'Odd_name_22', 'the identity is <Name>_<ServerId>, as the settings library and autobox name it')
check(U.identity('', 5) == nil and U.identity('Name', 0) == nil and U.identity(nil, nil) == nil, 'no name or no id (the title screen): no identity')
check(U.pref_path(install, 'Testcharone_1') == install .. 'config/addons/xiforever/Testcharone_1/ui.cfg', 'config/addons/xiforever/<Name>_<ServerId>/ui.cfg')
check(U.pref_path(install, nil) == nil and U.read_pref(nil) == nil, 'no identity: no path, nothing read')

local who = 'Testcharone_1'
local A1 = U.follow.new(install, function() return who end)   -- (the Squads menu)
local B1 = U.follow.new(install, function() return who end)   -- (Gambits, in the same game window)
check(A1:poll(0) == nil and B1:poll(0) == nil and not exists(install .. 'config'), 'loading and looking: no choice, and nothing at all is written')
check(A1:pick('nonsense', mkdir) == false and not exists(install .. 'config'), 'an unknown theme is not written')
check(A1:pick('crimson', mkdir) == true and slurp(U.pref_path(install, who)) == 'theme=crimson\n', 'picking a theme writes theme=crimson for this character')
check(B1:poll(0.5) == nil and B1:poll(1.0) == 'crimson', 'the other add-on sees it at its next look (once a second), without a restart')
check(B1:pick('classic', mkdir) and A1:poll(2.1) == 'classic', 'and the other way round')
check(not exists(U.pref_path(install, who) .. '.tmp'), 'no temporary file is left')

who = 'Other_2'
check(A1:poll(2.2) == nil and not exists(U.pref_path(install, 'Other_2')), 'another character logs in: at once no shared choice (never the first one\'s), and no file is made for it')
check(A1:pick('squad', mkdir) and slurp(U.pref_path(install, 'Other_2')) == 'theme=squad\n' and slurp(U.pref_path(install, 'Testcharone_1')) == 'theme=classic\n',
      'its pick is its own file; the first character\'s file is untouched')
-- no character for a moment (the game may report none while a zone loads): not a logout
who = nil
local reads, realRead = 0, U.read_pref
U.read_pref = function(p) reads = reads + 1; return realRead(p) end
local held = true
for t = 3, 3 + U.GRACE - 1, 0.5 do
    local theme, id = A1:poll(t, true)
    held = held and theme == 'squad' and id == 'Other_2'
end
check(held and reads == 0, 'no character for up to ' .. U.GRACE .. ' s: the theme and the character stay what they were, at every look, and no file is read')
check(A1:pick('crimson', mkdir) == false and slurp(U.pref_path(install, 'Other_2')) == 'theme=squad\n', 'a pick in that time is not written: not for nobody, and not for the character that was there')
who = 'Other_2'
check(A1:poll(3 + U.GRACE - 0.4) == 'squad' and A1.goneAt == nil, 'the same character is back: nothing changed, and the wait is over')
who = nil
A1:poll(100)
who = 'Testcharone_1'
check(A1:poll(100.2) == 'classic', 'ANOTHER character after a moment without one: at once its own choice, never the one before')
who = nil
check(A1:poll(101) == 'classic' and select(2, A1:poll(101 + U.GRACE - 0.1)) == 'Testcharone_1', 'no character again: held')
local theme, id = A1:poll(101 + U.GRACE)
check(theme == nil and id == nil and A1:pick('crimson', mkdir) == false, 'after ' .. U.GRACE .. ' s without a character: logged out; no choice, and a pick is not written (there is no character to keep it for)')
check(A1:poll(101 + U.GRACE + 50) == nil, 'and it stays logged out (nothing is held for ever)')
U.read_pref = realRead
who = 'Testcharone_1'
check(A1:poll(200) == 'classic', 'back on the first character: its own choice again')

-- the "Gambits is loaded" mark: one that another game process left behind (a crash) does not count
do
    local mark = install .. 'config/addons/xiforever/Testcharone_1/gambits.loaded'
    local function write(text) local f = assert(io.open(mark, 'w')) f:write(text) f:close() end
    check(U.presence_valid(mark) == false and U.presence_valid(nil) == false, 'no mark: Gambits is not loaded')
    write(U.presence_text('0.3.4'))
    check(U.presence_valid(mark) == true and U.presence_text('0.3.4'):find('^Gambits 0%.3%.4\n') ~= nil, 'the mark Gambits writes in this game process: loaded')
    write('Gambits 0.3.4\n')
    check(U.presence_valid(mark) == true, 'a mark without a process id (cannot be told): taken as it is')
    local pid = U.process_id()
    if pid then
        check(U.presence_text('0.3.4') == 'Gambits 0.3.4\npid=' .. string.format('%d', pid) .. '\n', 'with LuaJIT the mark carries this process\'s id (' .. pid .. ')')
        write('Gambits 0.3.4\npid=' .. string.format('%d', pid + 1) .. '\n')
        check(U.presence_valid(mark) == false, 'a mark with another process\'s id (left by a game that crashed): not loaded')
    else
        io.write('  (this Lua has no ffi: the process id is not known, a mark is taken as it is; 2 checks not run)\n')
    end
    os.remove(mark)
end

-- two game windows (dualbox) on one Ashita folder, each its own character
local w1 = U.follow.new(install, function() return 'Testcharone_1' end)
local w2 = U.follow.new(install, function() return 'Other_2' end)
w1:pick('crimson', mkdir); w2:pick('classic', mkdir)
check(w1:poll(10, true) == 'crimson' and w2:poll(10, true) == 'classic', 'two windows, two characters: neither overwrites the other')

-- a damaged or foreign file
local function put(text) local f = assert(io.open(U.pref_path(install, 'Testcharone_1'), 'w')) f:write(text) f:close() end
put('theme=purple\n')
check(U.read_pref(U.pref_path(install, 'Testcharone_1')) == nil, 'an unknown theme in the file: no choice')
put('garbage\n\0\0')
check(w1:poll(20, true) == nil and slurp(U.pref_path(install, 'Testcharone_1')) == 'garbage\n\0\0', 'a damaged file: no choice, and looking does not rewrite it')
put('other=1\ntheme = squad \n')
check(w1:poll(21, true) == 'squad', 'other lines and spaces are tolerated')

if win then os.execute('rmdir /s /q "' .. dir:gsub('/', '\\') .. '" 2>nul') else os.execute('rm -rf "' .. dir .. '"') end
io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
