-- The Squads menu 1.27: themes (Crimson for a new installation, an existing one keeps its look), the character's
-- shared theme, a top row and cards that fit, tooltips that never read a % as a format, Apply for one mate, the
-- "calling again" state, the Gambits button, and the Profile window's Gear view (slots as the slot picker, Equipment
-- and Look, the worn mark, the filter, the kept lists, "applies when called again"). SIMULATION: the real
-- servermenu.lua with a stand-in Ashita and an ImGui that lays controls out on a line (so it can tell when one lands
-- beyond the window's edge). Not a gameplay test; nothing is written outside a temporary folder.
--   luajit test_squad_menu_ui.lua [<another servermenu.lua, for the layout comparison only>]
--   (Lua 5.4: lua test_squad_menu_ui.lua)
local HERE = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local MENU = HERE .. '/../../addons-src/servermenu/servermenu.lua'
local OTHER = arg and arg[1]
io.stdout:setvbuf('no')
local passed, failed = 0, 0
local function check(c, label) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end
local function has(text, needle) return tostring(text):find(needle, 1, true) ~= nil end
local function near(a, b) return math.abs(a - b) < 1e-9 end
local function same(c, e) return type(c) == 'table' and near(c[1], e[1]) and near(c[2], e[2]) and near(c[3], e[3]) and near(c[4] or 1, e[4] or 1) end
local win = package.config:sub(1, 1) == '\\'
local function mkdir(p) if win then os.execute('mkdir "' .. p:gsub('/', '\\'):gsub('\\+$', '') .. '" 2>nul') else os.execute('mkdir -p "' .. p .. '"') end end
local function slurp(p) local f = io.open(p, 'rb') if not f then return nil end local s = f:read('*a') f:close() return (s:gsub('\r\n', '\n')) end
local function put(p, text) local f = assert(io.open(p, 'w')) f:write(text) f:close() end
local realPrint = print

-- ---------------------------------------------------------------- a world: one loaded servermenu and its stand-ins
local COL = { 'WindowBg', 'ChildBg', 'PopupBg', 'Border', 'Button', 'ButtonHovered', 'ButtonActive', 'FrameBg', 'FrameBgHovered', 'CheckMark',
              'Header', 'HeaderHovered', 'Separator', 'Text', 'PlotHistogram', 'TitleBg', 'TitleBgActive' }
local VAR = { 'WindowRounding', 'ChildRounding', 'FrameRounding', 'PopupRounding', 'WindowPadding', 'ItemSpacing', 'ItemInnerSpacing',
              'FramePadding', 'FrameBorderSize', 'Alpha', 'ButtonTextAlign', 'WindowBorderSize', 'WindowMinSize' }
local function world(opts)
    opts = opts or {}
    local W = { handlers = {}, clock = 100, sent = {}, clicks = {}, hover = false, who = opts.who or { 'Testcharone', 1 }, scale = 1,
                width = 620, over = {}, texts = {}, tips = {}, buttons = {}, setTooltip = {}, textWrapped = 0, colors = 0, vars = 0,
                pushed = {}, first = {}, cells = {}, combos = {}, wins = {}, winPos = {}, login = 2, zoning = 0, flags = {}, winColors = {}, sizes = {}, at = {}, look = {}, cstack = {}, rects = {}, begins = 0, ends = 0, inputs = {}, skipped = {}, content = {}, view = nil, items = {}, openCombo = nil, pick = nil, throwAt = nil, fullBinding = true, fontPushes = {}, fontPops = 0, fontScales = {} }
    if opts.dir then W.dir = opts.dir else W.dir = os.tmpname(); os.remove(W.dir) end   -- (opts.dir: an Ashita folder that is there already)
    mkdir(W.dir)
    if opts.cfg then mkdir(W.dir .. '/config/addons/servermenu'); put(W.dir .. '/config/addons/servermenu/settings.cfg', opts.cfg) end
    for _, p in ipairs(opts.prefs or {}) do assert(dofile(HERE .. '/../../addons-src/servermenu/xifo_ui.lua').write_pref(W.dir .. '/', p[1], p[2], mkdir)) end
    local L = { x = 0, endX = 0, same = false, w = 0, stack = {}, itemW = nil, inTip = false }
    local function textW(t) return #tostring(t or ''):gsub('##.*$', '') * 7 * W.scale end
    local function place(w, label)
        if not L.same then L.x = L.setX or 0 end; L.setX = nil   -- (a SetCursorPosX on a new line: the next control starts there)
        W.at[#W.at + 1] = { label = tostring(label), x = L.x, w = w }   -- (where each control and text starts, in drawing order)
        if L.w > 0 and not L.wrap and L.x + w > L.w + 0.5 then W.over[#W.over + 1] = string.format('%s (at %d, %d wide, in %d)', tostring(label), L.x, w, L.w) end
        L.endX, L.same = L.x + w, false
    end
    local im = setmetatable({}, { __index = function(t, k) local f = function() end rawset(t, k, f) return f end })
    function im.Begin(title, _, flags) W.begins = W.begins + 1; W.title = title
        W.flags[title] = flags or 0; W.wins[title] = (W.wins[title] or 0) + 1
        if W.nextPos and (W.nextPos[3] == 1 or W.winPos[title] == nil) then W.winPos[title] = { W.nextPos[1], W.nextPos[2] } end
        W.nextPos = nil
        W.winColors[title] = { TitleBg = W.cur('cTitleBg'), TitleBgActive = W.cur('cTitleBgActive'), WindowBg = W.cur('cWindowBg'), Text = W.cur('cText') }
        W.bgAlpha = W.bgAlpha or {}; W.bgAlpha[title] = W.nextBgAlpha; W.nextBgAlpha = nil
        W.winAlpha = W.winAlpha or {}; W.winAlpha[title] = W.pushed.vAlpha
        L = { x = 0, endX = 0, same = false, w = W.width * W.scale - 16 * W.scale, stack = {}, inTip = false }
        if title:find('servermenu_button', 1, true) then L.w = 0 end   -- (auto-sized: nothing can be cut off in it)
        return true end
    function im.End() W.ends = W.ends + 1 end
    function im.SetNextWindowBgAlpha(a) W.nextBgAlpha = a end
    function im.BeginChild(id, size)
        L.stack[#L.stack + 1] = { x = L.x, endX = L.endX, same = L.same, w = L.w }
        local w = (type(size) == 'table' and (size[1] or 0) > 0) and size[1] or L.w
        L.w, L.x, L.endX, L.same = w - 16 * W.scale, 0, 0, false
        W.childH = W.childH or {}; W.childH[id] = type(size) == 'table' and size[2] or 0
        W.childBg = W.childBg or {}; W.childBg[id] = W.cur('cChildBg')   -- (ImGui paints a child's background when it begins)
        -- a scrolling list (W.view = { top = <scrolled by>, h = <visible height> }): the children are stacked, and one
        -- that is wholly outside the visible part is not drawn; BeginChild says false for it, as ImGui does
        local card = id:find('^##sm_mate') ~= nil
        local top = L.listY or 0
        if card then L.listY = top + W.childH[id] + 4 * W.scale end
        W.childTop = W.childTop or {}; W.childTop[id] = top
        local visible = W.view == nil or not card or (top + W.childH[id] > W.view.top and top < W.view.top + W.view.h)
        L.child = { id = id, visible = visible }
        if not visible then W.skipped[id] = (W.skipped[id] or 0) + 1 end
        return visible end
    function im.EndChild() local s = table.remove(L.stack); L.x, L.endX, L.same, L.w = s.x, s.endX, false, s.w; L.child = nil; W.childEnds = (W.childEnds or 0) + 1 end
    function im.SameLine(off, sp) if off and off > 0 then L.x = off else L.x = L.endX + (sp or 8) end; L.same = true end
    function im.NewLine() L.same, L.endX = false, 0 end
    function im.GetContentRegionAvail() return { L.w - (L.same and L.x or (L.setX or 0)), 400 } end
    -- (1.34) the cursor's x, and setting it: on the current line (after SameLine) or for the next line's first control
    function im.GetCursorPosX() return L.same and L.x or (L.setX or 0) end
    function im.SetCursorPosX(x) if L.same then L.x = x else L.setX = x end end
    -- (1.34) the font: what the menu pushes (its size), pops, and any SetWindowFontScale
    function im.GetFont() return 'font' end
    function im.PushFont(_, size) W.fontPushes[#W.fontPushes + 1] = size end
    function im.PopFont() W.fontPops = W.fontPops + 1 end
    function im.SetWindowFontScale(v) W.fontScales[#W.fontScales + 1] = v end
    function im.GetWindowWidth() return W.width * W.scale end
    -- a window is where SetNextWindowPos put it: always with ImGuiCond_Always (1), else only the first time it is drawn
    function im.SetNextWindowPos(p, cond) W.nextPos = { p[1], p[2], cond } end
    function im.GetWindowPos() local p = W.winPos[W.title]; if p then return p[1], p[2] end return 18, 240 end
    function im.GetFontSize() return 13 * W.scale end   -- (inside a window the font is the scaled one)
    -- where the next control would go: under what was drawn (W.content[id], else 77); in a child that was not drawn
    -- nothing moved it from the padding
    function im.GetCursorPosY()
        if L.child and not L.child.visible then return 8 * W.scale end
        return (L.child and W.content[L.child.id]) or 77 end
    function im.CalcTextSize(t) return { textW(t), 13 } end
    function im.PushItemWidth(w) L.itemW = w end
    function im.PopItemWidth() L.itemW = nil end
    function im.Button(label, size)
        if W.throwAt and label:find(W.throwAt, 1, true) then W.throwAt = nil; error('a control failed', 0) end
        local w = (type(size) == 'table' and (size[1] or 0) > 0) and size[1] or (textW(label) + 8 * W.scale)
        place(w, label)
        W.buttons[#W.buttons + 1] = label
        L.last = label
        W.sizes[label] = { w, type(size) == 'table' and size[2] or 0 }
        W.look[label] = W.cur('cButton')
        if label:find('^##slot%d') then L.cell = label; W.cells[label] = {} end
        for key in pairs(W.clicks) do
            if label == key or label:sub(-#key) == key then W.clicks[key] = nil; return true end
        end
        return false end
    local function text(t, c)
        if L.inTip then W.tips[#W.tips + 1] = tostring(t); return end
        place(textW(t), t); W.texts[#W.texts + 1] = { text = tostring(t), color = c }
        -- (1.28) a gear slot's row is one button; its slot name and item name are drawn over it right after
        if L.cell then local cell = W.cells[L.cell]; cell[#cell + 1] = { text = tostring(t), color = c }; if #cell >= 2 then L.cell = nil end end
    end
    function im.Text(t) text(t) end
    function im.TextColored(c, t) text(t, c) end
    function im.SetTooltip(t) W.setTooltip[#W.setTooltip + 1] = t end
    function im.TextWrapped(t) W.textWrapped = W.textWrapped + 1; W.texts[#W.texts + 1] = { text = tostring(t) } end
    function im.Dummy(size) place(type(size) == 'table' and size[1] or 0, 'dummy') end
    function im.Image(_, size) place(size[1], 'image') end
    function im.ProgressBar(_, size) place(size[1], 'bar') end
    function im.BeginCombo(id, preview) place(L.itemW or 100, id); W.combos[id] = preview; return W.openCombo == id end
    function im.Selectable(label) return W.pick ~= nil and label:sub(1, #W.pick) == W.pick end
    function im.InputText(id, buf) place(L.itemW or 100, id); if W.inputs[id] then buf[1] = W.inputs[id] end return false end
    function im.IsItemHovered() return W.hover or (W.hoverOn ~= nil and L.last == W.hoverOn) end
    function im.Separator() W.at[#W.at + 1] = { label = 'separator', x = 0, w = 0 }; L.same = false end
    -- a control held with the mouse and moved (W.dragOn = its label, W.dragDelta = { dx, dy }): as Ashita reports it
    function im.IsItemActive() return W.dragOn ~= nil and L.last == W.dragOn end
    function im.IsMouseDragging() return W.dragOn ~= nil end
    function im.GetMouseDragDelta() local d = W.dragDelta or { 0, 0 }; return d[1], d[2] end
    function im.PushStyleColor(id, c) W.colors = W.colors + 1; W.pushed[id] = c; if W.first[id] == nil then W.first[id] = c end; W.cstack[#W.cstack + 1] = { id, c } end
    function im.PopStyleColor(n) W.colors = W.colors - (n or 1); for _ = 1, (n or 1) do table.remove(W.cstack) end end
    -- the colour in force for an id right now (the stack's top entry for it), e.g. a button's face when it is drawn
    function W.cur(id) for i = #W.cstack, 1, -1 do if W.cstack[i][1] == id then return W.cstack[i][2] end end end
    function im.PushStyleVar(id, v) W.vars = W.vars + 1; W.pushed['v' .. id] = v end
    function im.PopStyleVar(n) W.vars = W.vars - (n or 1) end
    function im.BeginPopupContextItem() return false end
    function im.MenuItem() return false end
    -- the draw list keeps the filled rectangles (a selected row's tint and its four thin bars); a colour stays the table it was
    function im.GetWindowDrawList() return setmetatable({ AddRectFilled = function(_, a, b, col) W.rects[#W.rects + 1] = { a[1], a[2], b[1], b[2], col } end }, { __index = function() return function() end end }) end
    function im.GetCursorScreenPos() return { 0, 0 } end
    function im.ColorConvertFloat4ToU32(c) return c end
    W.setBinding = function(full)
        W.fullBinding = full
        if full then
            function im.BeginTooltip() L.inTip = true; return true end
            function im.EndTooltip() L.inTip = false end
            function im.TextUnformatted(t) text(t) end
            -- (a wrapped text takes the lines it needs: it cannot run beyond the edge)
            function im.PushTextWrapPos() L.wrap = true end
            function im.PopTextWrapPos() L.wrap = false end
        else
            im.BeginTooltip, im.EndTooltip, im.TextUnformatted, im.PushTextWrapPos, im.PopTextWrapPos = false, false, false, false, false
        end
    end
    W.setBinding(true)
    package.loaded['imgui'], package.loaded['common'], package.loaded['xifo_ui'] = im, true, nil
    function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
    addon = {}
    local chat = {}
    function chat:QueueCommand(_, command) W.sent[#W.sent + 1] = command end
    function chat:IsInputOpen() return false end
    local party = {}
    function party:GetMemberName() return W.who and W.who[1] or '' end
    function party:GetMemberServerId() return W.who and W.who[2] or 0 end
    local rm = {}
    function rm:GetItemById(id) W.lookups = (W.lookups or 0) + 1; return { Name = { 'Haste Belt ' .. id }, Level = 40, Description = { 'DEF:3 Haste+4%' } } end
    function rm:GetItemByName() return nil end
    ashita = { events = { register = function(name, _, fn) W.handlers[name] = fn end }, time = { get_tick64 = function() return W.clock * 1000 end },
               fs = { create_directory = function(p) mkdir(p) end } }
    AshitaCore = { GetChatManager = function() return chat end, GetInstallPath = function() return W.dir .. '/' end,
                   GetMemoryManager = function() return { GetParty = function() return party end,
                       -- (the player: login status 2 = in the game, as Ashita's settings library asks; zoning while a zone loads)
                       GetPlayer = function() return { GetLoginStatus = function() return W.login end, GetIsZoning = function() return W.zoning end } end } end,
                   GetResourceManager = function() return rm end }
    for i, n in ipairs(COL) do rawset(_G, 'ImGuiCol_' .. n, 'c' .. n) end
    for i, n in ipairs(VAR) do rawset(_G, 'ImGuiStyleVar_' .. n, n) end
    for n, v in pairs({ ImGuiCond_FirstUseEver = 4, ImGuiCond_Always = 1, ImGuiCond_Appearing = 8, ImGuiWindowFlags_NoTitleBar = 1, ImGuiWindowFlags_NoCollapse = 32,
                        ImGuiWindowFlags_NoMove = 4, ImGuiWindowFlags_NoResize = 2, ImGuiWindowFlags_NoScrollbar = 8, ImGuiWindowFlags_AlwaysAutoResize = 64,
                        ImGuiWindowFlags_NoSavedSettings = 256, ImGuiWindowFlags_NoFocusOnAppearing = 4096, ImGuiWindowFlags_NoScrollWithMouse = 16,
                        ImGuiChildFlags_Borders = 1 }) do rawset(_G, n, v) end
    W.prints = {}
    print = function(...) W.prints[#W.prints + 1] = table.concat({ ... }, ' ') end
    assert(loadfile(opts.file or MENU))()
    W.handlers.load()
    print = realPrint
    function W.frame(dt)
        W.clock = W.clock + (dt or 0.05)
        W.over, W.texts, W.tips, W.buttons, W.items, W.first, W.cells, W.combos, W.sizes, W.at, W.look, W.rects, W.wins = {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}
        print = function(...) W.prints[#W.prints + 1] = table.concat({ ... }, ' ') end
        W.handlers.d3d_present()
        print = realPrint
    end
    function W.line(text) W.handlers.text_in({ message = text, blocked = false }) end
    function W.command(text) local e = { command = text, blocked = false }; W.handlers.command(e); return e.blocked end
    function W.text(needle) for _, e in ipairs(W.texts) do if has(e.text, needle) then return e end end end
    function W.button(needle) for _, b in ipairs(W.buttons) do if has(b, needle) then return b end end end
    -- the item named in a gear slot's row ("Empty" for none); W.cellHas: any row naming it
    function W.cell(id, needle) local c = W.cells[id]; return c ~= nil and c[2] ~= nil and has(c[2].text, needle) end
    function W.cellHas(needle) for _, c in pairs(W.cells) do if c[2] and has(c[2].text, needle) then return true end end return false end
    -- the mate the Profile's first row names, when a sheet is shown under it (the Stats / Gear tabs are only drawn then)
    function W.sel() return W.combos['##sheetmate'] end
    function W.shownMate() return W.button('##sheettabstats') and W.combos['##sheetmate'] or nil end
    function W.said(needle, from) local n = 0 for i = (from or 1), #W.sent do if has(W.sent[i], needle) then n = n + 1 end end return n end
    function W.click(key, wait) W.clicks[key] = true; W.frame(); for _ = 1, (wait or 3) do W.frame(2.5) end end
    function W.cfg() return slurp(W.dir .. '/config/addons/servermenu/settings.cfg') or '' end
    function W.close() if win then os.execute('rmdir /s /q "' .. W.dir:gsub('/', '\\') .. '" 2>nul') else os.execute('rm -rf "' .. W.dir .. '"') end end
    return W
end

-- the server's answer to !squad panel: six mates in every state the cards have
local function feed(W, o)
    o = o or {}
    local jobs = { { 'WAR', 'MNK' }, { 'WHM', 'BLM' }, { 'RDM', 'WHM' }, { 'BRD', 'WHM' }, { 'PLD', 'WAR' }, { 'BLM', 'RDM' } }
    local roles = { 'tank', 'damage', 'healer', 'support', 'auto', 'damage' }
    for i = 1, 6 do
        local out = not (o.away and o.away[i])
        W.line(string.format('squadpanel:%d|Mate%d|%s|75|%s|37|%s|balanced|%d|14', i, i, jobs[i][1], jobs[i][2], roles[i], out and 1 or 0))
        W.line(string.format('squadpanel:jl|%d|WAR:75,MNK:40,WHM:75,BLM:60,RDM:75,THF:30,PLD:75,BRD:75', i))
        local state = (o.state and o.state[i]) or (out and (i % 2 == 0 and 'set' or 'job') or 'off')
        W.line(string.format('squadpanel:rs|%d|%s|%s|%d|A rather long Rule Set name %d|%d|A rather long Rule Set name %d|0|%d|%s', i, state,
            state == 'pending' and 'edited' or '-', (state == 'set' or state == 'pending') and i or 0, i, i % 2 == 0 and i or 0, i, state == 'set' and 2 or 0, jobs[i][1]))
        W.line(string.format('squadpanel:opt|%d|0|1000|Raging_Axe|1|Raging_Axe,Rampage,Decimation,Steel_Cyclone', i))
        W.line(string.format('squadpanel:cd|%d|%d', i, (o.cdOf and o.cdOf[i]) or o.cd or 90))   -- (the call timer; 0 = can be called now)
    end
    W.line('squadpanel:camp|1|2|0|3'); W.line('squadpanel:campwant|-')
    for _, k in ipairs({ 'Goblin_Thug', 'Wild_Rabbit', 'Tunnel_Worm', 'Forest_Hare', 'Carrion_Crow' }) do W.line('squadpanel:campmob|' .. k .. '|10|12|4|1') end
    W.line('squadpanel:engage|0'); W.line('squadpanel:auto|0'); W.line('squadpanel:adv|0|1|-'); W.line('squadpanel:plvl|-6|2|0')
    for i = 1, 6 do W.line(string.format('squadpanel:delay|%d|0', i)) end
    W.line('squadpanel:beh|war|on|Warrior')
    for _, l in ipairs(o.extra or {}) do W.line(l) end   -- (1.35) more lines in the same answer (pos|...)
    if o.cap ~= false then W.line('squadpanel:cap|' .. (type(o.cap) == 'string' and o.cap or 'reapply1')) end
    W.line('squadpanel:end')
end
local function feedSheet(W, slot, o)
    o = o or {}
    local function s(t) W.line('squadsheet:' .. t) end
    if o.slotLine then s('slot|' .. slot) end   -- (a server of this milestone says whose sheet it is; an older one does not)
    s(string.format('hdr|%s|WAR|75|MNK|37|tank|balanced|Hume|15', o.name or ('Mate' .. slot)))
    for e, id in pairs(o.ls or {}) do s(string.format('ls|%d|slot|haste_belt|%d', e, id)) end
    for _, j in ipairs({ 'WAR', 'MNK', 'WHM', 'BLM' }) do s('job|' .. j .. '|75') end
    s('exp|WAR|75|1200|44000')
    if o.notCalled then
        -- (squad.lua: a mate that is not called has no vitals, stats, combat values or haste; a note instead)
        s('note|Not called right now, so there are no live stats. The gear below is what they wear as WAR.')
    else
        s('vital|HP|1500|1600'); s('vital|MP|0|0'); s('vital|TP|1200|3000')
        for _, k in ipairs({ 'STR', 'DEX', 'VIT', 'AGI', 'INT', 'MND', 'CHR' }) do s('stat|' .. k .. '|' .. ((o.statOf and o.statOf[k]) or 70)) end
        for _, k in ipairs({ 'Attack', 'Accuracy', 'Defense', 'Evasion', 'Ranged attack', 'Ranged accuracy' }) do s('combat|' .. k .. '|' .. ((o.combatOf and o.combatOf[k]) or 300)) end
        s('haste|gear|500')
    end
    for e = 0, 15 do if not (o.empty and o.empty[e]) then s(string.format('eq|%d|slot|haste_belt|%d', e, (o.worn and o.worn[e]) or (12000 + e))) end end
    s('end')
end

-- (1.36) the stand-ins alone, without running the checks below: for a test that puts this menu together with another
-- add-on (dev/ventures/test_venture_button.py: the real venture add-on, each in its own Lua state as in the game)
if rawget(_G, 'SQUAD_MENU_UI_LIB') then return { world = world, feed = feed, feedSheet = feedSheet } end

-- ================================================================= 1. the theme of a new and of an existing installation
section('1. Crimson for a new installation; an existing one keeps the look it has')
do
    local W = world()
    W.command('/menu squad'); feed(W); W.frame(); W.frame(1.2)
    check(same(W.pushed.cWindowBg, { 0.090, 0.068, 0.074, 0.96 }) and has(W.cfg(), 'theme=crimson'), 'no settings file (a new installation): Crimson, written as theme=crimson')
    check(not slurp(W.dir .. '/config/addons/xiforever/Testcharone_1/ui.cfg'), 'loading the menu makes no shared choice for the character')
    W.close()
    W = world({ cfg = 'button_locked=true\nbutton_wide=true\nscale=1\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame(1.2)
    check(same(W.pushed.cWindowBg, { 0.07, 0.08, 0.11, 0.96 }) and same(W.pushed.cFrameBg, { 0.14, 0.16, 0.21, 1 }) and same(W.text('Squad').color, { 0.89, 0.74, 0.40, 1 }),
          'a settings file from before themes: the menu\'s colours of 1.26, value for value (Squad)')
    check(has(W.cfg(), 'theme=squad') and has(W.cfg(), 'button_locked=true'), 'and that is written down as theme=squad; its other settings are kept')
    W.close()
    for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
        W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
        W.command('/menu squad'); feed(W); W.frame(); W.frame(1.2)
        check(has(W.cfg(), 'theme=' .. name) and not has(W.cfg():gsub('theme=' .. name, ''), 'theme='), 'a saved theme=' .. name .. ' stays ' .. name)
        W.close()
    end
    W = world({ cfg = 'theme=purple\nbutton_wide=true\n' })
    W.command('/menu squad'); W.frame(); W.frame(1.2)
    check(has(W.cfg(), 'theme=squad'), 'an unreadable theme in an existing file: that installation\'s look (Squad), not Crimson')
    W.close()
end

-- ================================================================= 2. what is pushed is popped; the shared metrics
section('2. every window pops what it pushed, in every theme, also when a control fails')
do
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W)
    local ok = true
    for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
        W.command('/menu theme ' .. name)
        for _, tab in ipairs({ 'squad', 'dualbox', 'auto' }) do
            W.command('/menu ' .. tab); W.frame()
            ok = ok and W.colors == 0 and W.vars == 0 and W.begins == W.ends
        end
        W.command('/menu squad'); W.command('/sq sheet 1'); feedSheet(W, 1); W.frame()
        ok = ok and W.colors == 0 and W.vars == 0 and W.begins == W.ends
        W.command('/sq gear 1'); W.frame()
        ok = ok and W.colors == 0 and W.vars == 0 and W.begins == W.ends
    end
    check(ok, 'menu, button, Profile (Stats and Gear) in Classic, Squad and Crimson: colours and style values back to 0 after every frame')
    check(W.pushedOk ~= false and W.pushed.vWindowPadding[1] == 8 and W.pushed.vFramePadding[1] == 4 and W.pushed.vFramePadding[2] == 3
        and W.pushed.vItemSpacing[1] == 6 and W.pushed.vItemSpacing[2] == 4 and W.pushed.vChildRounding == 5 and W.pushed.vFrameRounding == 4,
          'the windows use the Gambits editor\'s padding 8x8, frame 4x3, spacing 6x4, rounding 5 / 4')
    W.throwAt = 'Call all'
    W.frame()
    check(W.colors == 0 and W.vars == 0 and W.begins == W.ends, 'a control that fails inside the menu: the stacks are back to 0 and every Begin has its End')
    local told = false
    for _, p in ipairs(W.prints) do told = told or has(p, 'the menu hit a problem') end
    check(told, 'and the menu says so once and closes, as before')
    W.close()
end

-- ================================================================= 3. the character's shared theme
section('3. the shared theme: a pick is the character\'s, followed without a restart, never another character\'s')
do
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    local base = W.dir .. '/config/addons/xiforever/'
    W.command('/menu squad'); feed(W); W.frame()
    W.openCombo, W.pick = '##smtheme', 'Crimson'
    W.clicks['##options'] = true; W.frame(); W.frame()
    W.openCombo, W.pick = nil, nil
    W.frame(1.2)
    check(slurp(base .. 'Testcharone_1/ui.cfg') == 'theme=crimson\n' and same(W.pushed.cWindowBg, { 0.090, 0.068, 0.074, 0.96 }),
          'Options > Theme > Crimson: written for Testcharone_1 and in use at once')
    check(has(W.cfg(), 'theme=squad'), 'the installation-wide settings file still says squad (it is shared by every character)')
    put(base .. 'Testcharone_1/ui.cfg', 'theme=classic\n')   -- (Gambits picked Classic)
    W.frame(0.3)
    local early = same(W.pushed.cWindowBg, { 0.105, 0.095, 0.082, 0.96 })
    W.frame(1.0)
    check(not early and same(W.pushed.cWindowBg, { 0.105, 0.095, 0.082, 0.96 }), 'a choice made in Gambits is followed within a second, while the menu is open')
    W.who = { 'Other', 2 }
    W.frame(1.1)
    check(same(W.pushed.cWindowBg, { 0.07, 0.08, 0.11, 0.96 }) and not slurp(base .. 'Other_2/ui.cfg'),
          'another character logs in: this menu\'s own theme (Squad), and no file is made for it')
    check(W.command('/menu theme crimson') and slurp(base .. 'Other_2/ui.cfg') == 'theme=crimson\n' and slurp(base .. 'Testcharone_1/ui.cfg') == 'theme=classic\n',
          '/menu theme crimson on the second character: its own file; the first character\'s is untouched')
    -- no character for a moment (the game may report none while a zone loads): the look must not flip
    W.who = nil
    local flips, last = 0, nil
    for _ = 1, 12 do
        W.frame(2.0)
        local bg = W.pushed.cWindowBg
        if last ~= nil and not same(bg, last) then flips = flips + 1 end
        last = bg
    end
    check(flips == 0 and same(W.pushed.cWindowBg, { 0.090, 0.068, 0.074, 0.96 }), 'no character for 24 seconds: the theme stays the character\'s (Crimson) in every frame')
    W.who = { 'Other', 2 }
    W.frame(1.1)
    check(same(W.pushed.cWindowBg, { 0.090, 0.068, 0.074, 0.96 }), 'the character is back: still its theme')
    W.who = nil
    W.frame(1.1); W.frame(31)
    check(same(W.pushed.cWindowBg, { 0.07, 0.08, 0.11, 0.96 }), 'no character for more than 30 seconds: logged out, the menu\'s own theme')
    W.who = { 'Testcharone', 1 }
    W.frame(1.1)
    check(same(W.pushed.cWindowBg, { 0.105, 0.095, 0.082, 0.96 }), 'the first character again: its Classic')
    W.command('/menu'); W.frame()   -- (closed: only the Squads button is drawn)
    put(base .. 'Testcharone_1/ui.cfg', 'theme=crimson\n')
    W.frame(2.0)
    local soon = same(W.first.cButton, { 0.285, 0.130, 0.155, 0.95 })
    W.frame(4.0)
    check(not soon and same(W.first.cButton, { 0.285, 0.130, 0.155, 0.95 }), 'with the menu closed the Squads button follows too, looked at every five seconds')
    W.command('/menu theme purple')
    check(slurp(base .. 'Testcharone_1/ui.cfg') == 'theme=crimson\n', 'an unknown name changes nothing')
    W.close()
end

-- ================================================================= 4. nothing is cut off
section('4. the top row, the Camp row and the cards fit the window (widths 600 / 620 / 900, sizes 75 / 100 / 200 %)')
local function overflow(file, width, scale)
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\nscale=' .. scale .. '\n', file = file })
    W.width, W.scale = width, scale
    W.command('/menu squad'); feed(W)
    W.frame(); W.frame()
    local n, first = #W.over, W.over[1]
    W.close()
    return n, first
end
do
    local worst, where = 0, nil
    for _, width in ipairs({ 600, 620, 900 }) do
        for _, scale in ipairs({ 0.75, 1, 2 }) do
            local n, first = overflow(nil, width, scale)
            if n > worst then worst, where = n, string.format('%d px at %d %%: %s', width, scale * 100, tostring(first)) end
        end
    end
    check(worst == 0, 'six mates in every state, Camp row, Advanced, Forward to Gambits: no control beyond the edge' .. (where and (' (' .. where .. ')') or ''))
    if OTHER then
        local n, first = overflow(OTHER, 620, 1)
        io.write(string.format('  for comparison, %s at 620 px, 100 %%: %d control(s) beyond the edge, the first: %s\n', OTHER:match('[^/\\]+[/\\][^/\\]+$') or OTHER, n, tostring(first)))
        check(n > 0, 'the same measurement finds the cut-off controls in the other file (so it can find them)')
    end
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    check(W.childH['##sm_mate1'] == 77 + 8, 'a card is as high as its content was in the last frame (the stand-in says 77, plus the padding)')
    W.close()
end

-- ================================================================= 5. tooltips and wrapped lines
section('5. a % in a tooltip or a wrapped line is never a printf format')
do
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.command('/sq gear 1'); feedSheet(W, 1)
    W.hover = true
    W.frame(); W.frame()
    local item = false
    for _, t in ipairs(W.tips) do item = item or has(t, 'Haste+4%') end
    check(#W.setTooltip == 0 and W.textWrapped == 0 and item, 'everything hovered, the Gear view open: SetTooltip and TextWrapped are never called; the item\'s "Haste+4%" is drawn unformatted')
    W.command('/sq sheet 1'); W.frame()
    check(#W.setTooltip == 0 and W.textWrapped == 0, 'the Stats view too')
    W.setBinding(false)
    W.frame()
    local bare = false
    for _, t in ipairs(W.setTooltip) do bare = bare or t:gsub('%%%%', ''):find('%%') ~= nil end
    check(#W.setTooltip > 0 and not bare, 'a binding without TextUnformatted: SetTooltip gets every % doubled, never a bare one')
    W.close()
end

-- ================================================================= 6. Apply for one mate, the recall state, the Gambits button
local Ux2 = dofile(HERE .. '/../../addons-src/servermenu/xifo_ui.lua')
section('6. Apply for one mate; "Calling..."; the Gambits button')
do
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W, { state = { [2] = 'pending' } }); W.frame()
    check(W.button('Apply##applyone2') and not W.button('Apply##applyone1') and W.button('Apply now##apply') and W.text('Apply needed'),
          'the server reports mate 2 pending: Apply on its card only, and the banner with Apply now')
    local from = #W.sent + 1
    W.click('Apply##applyone2')
    check(W.said('/say !squad reapply 2', from) == 1 and W.said('/say !squad reapply', from) == 1, 'the server said reapply1: "!squad reapply 2", nothing squad-wide')
    feed(W, { away = { [2] = true }, state = { [2] = 'off' } }); W.frame()
    -- (1.29) one word, "Calling..."; the Call button is there, greyed; the Rules line says what is expected
    check(W.text('Calling...') and W.text('Next call: ') and not W.text('calling again') and not W.text('on its way') and same(W.look['Call##call2'], Ux2.menu('squad').c.busy),
          'mate 2 is away right after: "Calling...", not "Away"; its Rules line says what is expected at this call; Call is greyed')
    local others = 0
    for _, e in ipairs(W.texts) do if e.text == 'Calling...' then others = others + 1 end end
    check(others == 1, 'only that mate')
    W.frame(13); feed(W, { away = { [2] = true }, state = { [2] = 'off' } }); W.frame()
    check(not W.text('Calling...') and W.text('Away') and W.text('ready in'), 'twelve seconds later it is simply away again (the re-call did not happen)')
    W.close()
    -- an older server: no capability line
    W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W, { state = { [2] = 'pending' }, cap = false }); W.frame()
    W.hover = true; W.frame(); W.hover = false
    local tip = false
    for _, t in ipairs(W.tips) do tip = tip or has(t, 'can only call the whole squad again') end
    from = #W.sent + 1
    W.click('Apply##applyone2')
    check(tip and W.said('/say !squad reapply', from) == 1 and W.said('/say !squad reapply 2', from) == 0,
          'no reapply1: the card\'s Apply says it calls the whole squad, and sends the squad-wide line')
    W.close()
    -- a role change: with a Rules-status server the banner waits for the server's word
    W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame()
    W.clicks['##more1'], W.clicks['##more2'] = true, true; W.frame()   -- (1.28: Role, Mode and Range are behind Settings)
    W.openCombo, W.pick = '##role2', 'healer'; W.frame(); W.openCombo, W.pick = nil, nil; W.frame()
    check(not W.text('Changes take effect when your mates are called again.'), 'Role changed while a Rule Set runs: no banner of the menu\'s own (the Role changes nothing there)')
    W.openCombo, W.pick = '##range1', 'far'; W.frame(); W.openCombo, W.pick = nil, nil; W.frame()
    check(W.text('Changes take effect when your mates are called again.') and W.button('Apply##applyone1'), 'Range changed (the server does not report that): the banner, and Apply on that card')
    feed(W, { away = { [1] = true } }); W.frame()
    check(not W.button('Apply##applyone1') and not W.text('Changes take effect when your mates are called again.'), 'the mate was sent off: its next call applies it, the banner goes')
    -- the Gambits button
    check(not W.button('Gambits##gsq2'), 'Gambits is not loaded: no Gambits button')
    mkdir(W.dir .. '/config/addons/xiforever/Testcharone_1'); put(W.dir .. '/config/addons/xiforever/Testcharone_1/gambits.loaded', 'Gambits\n')
    W.frame(2.1)
    from = #W.sent + 1
    W.clicks['Gambits##gsq2'] = true; W.frame()
    check(W.button('Gambits##gsq2') and W.said('/gambits show 2', from) == 1, 'Gambits is loaded for this character: the button, and a click sends /gambits show 2')
    -- a moment without a character (a zone loads): the button stays
    W.who = nil
    W.frame(2.1); W.frame(2.1); W.frame(2.1)
    check(W.button('Gambits##gsq2') ~= nil, 'no character for a few seconds: the Gambits button is still there')
    W.who = { 'Testcharone', 1 }
    W.frame(2.1)
    -- a mark that another game process left behind (the game crashed with Gambits loaded)
    local Ux = dofile(HERE .. '/../../addons-src/servermenu/xifo_ui.lua')
    if Ux.process_id() then
        put(W.dir .. '/config/addons/xiforever/Testcharone_1/gambits.loaded', 'Gambits 0.3.4\npid=' .. string.format('%d', Ux.process_id() + 1) .. '\n')
        W.frame(2.1); W.frame(0.1)
        check(not W.button('Gambits##gsq2'), 'a mark from another game process (a crash left it): no Gambits button')
        put(W.dir .. '/config/addons/xiforever/Testcharone_1/gambits.loaded', Ux.presence_text('0.3.4'))
        W.frame(2.1); W.frame(0.1)
        check(W.button('Gambits##gsq2') ~= nil, 'the mark of this game process: the button is back')
    else
        io.write('  (no ffi in this Lua: the process id check is not run; 2 checks fewer)\n')
    end
    W.close()
end

-- ================================================================= 7. the Gear view
section('7. Profile > Gear: slots select, Equipment and Look, the worn mark, the filter, kept lists, Apply')
do
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame()
    W.click('Gear##gear1'); feedSheet(W, 1, { worn = { [5] = 13002 } }); W.frame()
    check(W.button('Stats##sheettabstats') and W.button('Gear##sheettabgear') and W.button('Equipment##gvgear1') and W.button('Look (lockstyle)##gvlook1'),
          'the Gear button of a card opens the profile on Gear: Stats | Gear, Equipment | Look')
    local cells = 0
    for _, b in ipairs(W.buttons) do if b:find('##slot1_%d+$') then cells = cells + 1 end end
    check(cells == 16 and W.cell('##slot1_5', 'Haste Belt 13002') and not W.button('##gp1_5'), 'the 16 worn slots are the slot picker (no second row of slot buttons)')
    local from = #W.sent + 1
    W.click('##slot1_5')
    check(W.said('/say !squad gearlist 1 5', from) == 1, 'a click on Body asks the server for its gear')
    for k = 1, 5 do W.line(string.format('squadpanel:gl|1|5|%d|%d|haste_belt', 13000 + k, 70 - k)) end
    W.line('squadpanel:gle|1|5|5'); W.frame()
    check(W.text('Gear: Body') and W.button('Lv68 Haste Belt 13002  (worn)##gpi1_13002_2') and W.button('Lv69 Haste Belt 13001##gpi1_13001_1'), 'the list, with the piece that is worn marked')
    local lookups = W.lookups
    W.frame(); W.frame(); W.frame()
    check(W.lookups == lookups, 'item names are asked from the game once, not every frame')
    W.click('##slot1_4'); W.line('squadpanel:gle|1|4|0'); W.frame()
    from = #W.sent + 1
    W.click('##slot1_5')
    check(W.said('gearlist', from) == 0 and W.button('##gpi1_13001_1'), 'back to Body: the list is still there, the server is not asked again')
    W.click('Reload##gpreload1')
    check(W.said('/say !squad gearlist 1 5', from) == 1, 'Reload asks again')
    for k = 1, 5 do W.line(string.format('squadpanel:gl|1|5|%d|%d|haste_belt', 13000 + k, 70 - k)) end
    W.line('squadpanel:gle|1|5|5'); W.frame()
    W.inputs['##sm_gearfilter'] = '13004'; W.frame(); W.frame()
    local shown = 0
    for _, b in ipairs(W.buttons) do if has(b, '##gpi1_') then shown = shown + 1 end end
    check(shown == 1 and W.button('##gpi1_13004_4'), 'the filter leaves the pieces whose name has the letters (1 of 5)')
    W.inputs['##sm_gearfilter'] = 'zzz'; W.frame(); W.frame()
    check(W.text('No piece in this list has "zzz"'), 'no match: said so')
    W.inputs['##sm_gearfilter'] = ''; W.frame(); W.frame()
    from = #W.sent + 1
    W.click('##gpi1_13002_2')
    check(W.said('equip', from) == 0, 'the worn piece is not put on a second time')
    W.click('##gpi1_13001_1')
    check(W.said('/say !squad equip 1 13001 body', from) == 1 and W.said('/say !squad sheet 1', from) >= 1 and W.said('/say !squad panel', from) >= 1,
          'a click puts the piece on (!squad equip), then the sheet and the squad list are read again')
    feedSheet(W, 1, { worn = { [5] = 13001 } }); feed(W); W.frame()
    check(W.text('Gear changed: Mate1 shows it when called again.') and W.button('Apply##gearapply1'), 'the Gear view says that it shows at the next call, with Apply next to it')
    W.command('/menu squad'); W.frame()
    check(W.button('Apply##applyone1') and W.text('Changes take effect when your mates are called again.'), 'and the Squad tab shows the same on that card and in the banner')
    from = #W.sent + 1
    W.click('Apply##gearapply1')
    check(W.said('/say !squad reapply 1', from) == 1, 'Apply in the Gear view: "!squad reapply 1"')
    feed(W); W.frame()
    check(not W.text('Gear changed:'), 'the line is gone once Apply was sent')
    -- Look (lockstyle)
    W.click('Look (lockstyle)##gvlook1')
    check(W.button('Lock current look##lsset1') and W.button('Lockstyle off##lsoff1') and W.text('Look: Body'), 'Look: its own view, with Lock current look and Lockstyle off')
    local plain = true
    for _, b in ipairs(W.buttons) do if b:find('##slot1_9$') or b:find('##slot1_15$') then plain = false end end
    check(plain, 'slots that do not show on a character (neck, back ...) cannot be picked in Look')
    from = #W.sent + 1
    W.click('##gpi1_13003_3')
    check(W.said('/say !squad lockstyle 1 13003 body', from) == 1 and W.said('equip', from) == 0, 'a click in Look only changes the look (!squad lockstyle), never the gear')
    W.click('Equipment##gvgear1')
    from = #W.sent + 1
    W.click('Take off##gpoff1')
    check(W.said('/say !squad unequip 1 body', from) == 1, 'Take off: !squad unequip')
    -- another mate, in the same window
    from = #W.sent + 1
    W.openCombo, W.pick = '##sheetmate', 'Mate3'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    feedSheet(W, 3); W.frame(); for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad sheet 3', from) >= 1 and W.said('/say !squad gearlist 3 5', from) == 1 and W.button('##slot3_5'),
          'the Mate list switches to Mate3 in the same window, still on Gear and on Body')
    W.close()
end

-- ================================================================= 8. cards that are scrolled out of view
section('8. a card that ImGui does not draw (scrolled out of view) keeps its height; the list does not jump')
do
    local function heights(W) local t, sum = {}, 0 for i = 1, 6 do t[i] = W.childH['##sm_mate' .. i]; sum = sum + t[i] end return t, sum end
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    -- the first frames with only the top of the list in view: mates 3 to 6 have never been drawn
    W.view = { top = 0, h = 150 }
    W.command('/menu squad'); feed(W); W.frame(); W.frame(); W.frame()
    local h = heights(W)
    check((W.skipped['##sm_mate6'] or 0) >= 2 and (W.skipped['##sm_mate1'] or 0) == 0, 'the stand-in reports the cards below the visible part as not drawn (BeginChild false), the first one as drawn')
    check(h[1] == 85 and h[6] >= 85 and h[4] >= 85, 'never drawn yet: such a card has its first-frame height, not the 16 pixels of an empty one (' .. tostring(h[6]) .. ')')
    check(W.colors == 0 and W.vars == 0 and W.begins == W.ends, 'and every stack is back to 0 (EndChild is still called for a card that was not drawn)')
    -- scroll down through the whole list and back up, a few pixels a frame: the six mates, the most a squad has
    W.view = nil; W.frame(); W.frame()
    local _, full = heights(W)
    local worst, jump, sumMin = 1e9, 0, 1e9
    local function sweep(from, to, step)
        for top = from, to, step do
            W.view = { top = top, h = 150 }
            local before = {}
            for i = 1, 6 do before[i] = W.childTop['##sm_mate' .. i] end
            W.frame()
            local t, sum = heights(W)
            for i = 1, 6 do
                worst = math.min(worst, t[i])
                -- a card in view may not move because of what happened to the cards above it
                local id = '##sm_mate' .. i
                local visible = W.childTop[id] + t[i] > top and W.childTop[id] < top + 150
                if visible and before[i] ~= nil then jump = math.max(jump, math.abs(W.childTop[id] - before[i])) end
            end
            sumMin = math.min(sumMin, sum)
        end
    end
    sweep(0, full, 7); sweep(full, 0, -7)
    check(worst == 85, 'scrolling through six mates and back: no card is ever lower than its content (lowest ' .. tostring(worst) .. ')')
    check(sumMin == full and jump == 0, string.format('the list keeps its length (%d) and no card in view moves (largest move %d px)', sumMin, jump))
    -- a card with more in it (More open, a wrapped row): its own height, kept while it is out of view, followed when it changes
    W.view = nil; W.content['##sm_mate2'] = 171; W.frame(); W.frame()
    check(W.childH['##sm_mate2'] == 179 and W.childH['##sm_mate3'] == 85, 'a card whose content is higher (171) is that high (179); the others are not')
    W.view = { top = 400, h = 150 }; W.frame(); W.frame(); W.frame()
    check((W.skipped['##sm_mate2'] or 0) > 0 and W.childH['##sm_mate2'] == 179, 'scrolled out of view it stays 179')
    W.content['##sm_mate2'] = 120   -- (its More part is closed, or the window was made wider, while it is out of view)
    W.frame(); W.frame()
    check(W.childH['##sm_mate2'] == 179, 'what changes while it is not drawn cannot be measured: the height it had is kept')
    W.view = { top = 0, h = 300 }; W.frame(); W.frame()
    check(W.childH['##sm_mate2'] == 128, 'back in view: measured again, one frame later it is as high as its content (128)')
    -- another size of the menu: the cards in view follow, the others keep a height that is not a collapsed one
    W.view = { top = 0, h = 150 }
    W.command('/menu scale 2'); W.scale = 2; W.frame(); W.frame()
    check(W.childH['##sm_mate1'] == 77 + 16 and W.childH['##sm_mate6'] >= 85, 'the size set to 200 %: the card in view is measured at that size, the ones out of view are not collapsed')
    W.close()
end

-- ================================================================= 9. the Profile window and a late answer
section('9. Profile: an answer for another mate is never shown, and no gear command can go to the wrong mate')
local function profileIsConsistent(W, slot)
    -- what is drawn: every cell and every piece belongs to `slot`, and the title names that mate
    for _, b in ipairs(W.buttons) do
        local n = b:match('##slot(%d+)_') or b:match('##gpi(%d+)_') or b:match('##sheetsw(%d+)') or b:match('##gvgear(%d+)') or b:match('##lsset(%d+)')
        if n and (tonumber(n) ~= slot or W.sel() ~= 'Mate' .. slot) then return false, b .. ' under "' .. tostring(W.sel()) .. '"' end
    end
    return true
end
for _, slotLine in ipairs({ false, true }) do
    local kind = slotLine and 'a server that says the slot' or 'an older server (the name only)'
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame()
    W.click('Gear##gear1'); feedSheet(W, 1, { worn = { [5] = 13002 }, slotLine = slotLine }); W.frame()
    W.click('##slot1_5')
    for k = 1, 3 do W.line(string.format('squadpanel:gl|1|5|%d|%d|haste_belt', 13000 + k, 70 - k)) end
    W.line('squadpanel:gle|1|5|3'); W.frame()
    check(W.cell('##slot1_5', 'Haste Belt 13002') and W.shownMate() == 'Mate1', kind .. ': Mate1 on Gear, Body selected')
    -- the reported case: Mate3 is picked, and the answer to an earlier "!squad sheet 1" arrives after that
    W.openCombo, W.pick = '##sheetmate', 'Mate3'; W.frame(); W.openCombo, W.pick = nil, nil
    feedSheet(W, 1, { worn = { [5] = 13002 }, slotLine = slotLine }); W.frame()
    local okNow, what = profileIsConsistent(W, 3)
    check(W.sel() == 'Mate3' and W.shownMate() == nil and not W.button('##slot3_5') and not W.cellHas('Haste Belt 13002') and okNow,
          kind .. ': Mate1\'s late answer is not shown under Mate3 (no title "Mate1", no gear cell for slot 3 with its gear)' .. (what and (': ' .. what) or ''))
    check(W.text('Asking the server...') ~= nil, kind .. ': the window says that it is asking')
    -- the picker's list for slot 3 arrives while the sheet is still unknown: nothing to click, nothing is sent
    for k = 1, 3 do W.line(string.format('squadpanel:gl|3|5|%d|%d|haste_belt', 13000 + k, 70 - k)) end
    W.line('squadpanel:gle|3|5|3'); W.frame()
    local from = #W.sent + 1
    W.click('##gpi3_13001_1'); W.click('Lock current look##lsset3'); W.click('##slot3_5')
    check(W.said('equip', from) == 0 and W.said('lockstyle', from) == 0 and W.said('unequip', from) == 0,
          kind .. ': while Mate3\'s sheet is not there, no equip / lockstyle / unequip line can be sent for slot 3')
    W.clicks = {}
    -- Mate3's own answer: now the window is Mate3's, and a click is for the mate that is shown
    feedSheet(W, 3, { worn = { [5] = 13003 }, slotLine = slotLine }); W.frame()
    check(W.shownMate() == 'Mate3' and W.cell('##slot3_5', 'Haste Belt 13003') and profileIsConsistent(W, 3), kind .. ': Mate3\'s answer is shown: its title, its gear')
    for k = 1, 3 do W.line(string.format('squadpanel:gl|3|5|%d|%d|haste_belt', 13000 + k, 70 - k)) end
    W.line('squadpanel:gle|3|5|3'); W.frame()
    from = #W.sent + 1
    W.click('##gpi3_13001_1')
    check(W.said('/say !squad equip 3 13001 body', from) == 1, kind .. ': and a piece clicked then goes to slot 3, the mate in the window')
    -- out of order: after Mate3's answer another late one for Mate1
    feedSheet(W, 3, { worn = { [5] = 13001 }, slotLine = slotLine }); feedSheet(W, 1, { worn = { [5] = 13002 }, slotLine = slotLine }); W.frame()
    check(W.shownMate() == 'Mate3' and W.cell('##slot3_5', 'Haste Belt 13001') and not W.cell('##slot3_5', 'Haste Belt 13002'), kind .. ': a late Mate1 answer after Mate3\'s changes nothing')
    -- two answers with no request in between (the late one, then the right one)
    W.openCombo, W.pick = '##sheetmate', 'Mate2'; W.frame(); W.openCombo, W.pick = nil, nil
    feedSheet(W, 3, { slotLine = slotLine }); feedSheet(W, 2, { worn = { [5] = 13005 }, slotLine = slotLine }); W.frame()
    check(W.shownMate() == 'Mate2' and W.cell('##slot2_5', 'Haste Belt 13005'), kind .. ': Mate3\'s late answer and then Mate2\'s, one after the other: Mate2\'s is read and shown')
    -- quick switching, the answers arriving late and in another order; every frame is looked at
    local bad = nil
    local function look(slot) local okFrame, w = profileIsConsistent(W, slot); if not okFrame then bad = bad or w end end
    -- (the Mate list is not there while a sheet is awaited, so the quick way is the cards' Gear buttons: /sq gear <slot>)
    for _, slot in ipairs({ 1, 4, 3 }) do
        W.command('/sq gear ' .. slot); W.frame(); look(slot); W.frame(); look(slot)
    end
    for _, late in ipairs({ 4, 1, 2 }) do feedSheet(W, late, { slotLine = slotLine }); W.frame(); look(3); W.frame(0.5); look(3) end
    check(bad == nil and not W.button('##slot3_5'), kind .. ': 1, 4, 3 picked quickly, answers for 4, 1 and 2 arrive: nothing of theirs is ever drawn' .. (bad and (' (' .. bad .. ')') or ''))
    feedSheet(W, 3, { slotLine = slotLine }); W.frame(); look(3)
    check(bad == nil and W.shownMate() == 'Mate3' and W.button('##slot3_5'), kind .. ': then Mate3\'s: shown')
    -- the Stats view and the spells window follow the same sheet
    W.click('Stats##sheettabstats')
    W.openCombo, W.pick = '##sheetmate', 'Mate5'; W.frame(); W.openCombo, W.pick = nil, nil
    feedSheet(W, 3, { slotLine = slotLine }); W.frame()
    local sw = false
    for _, b in ipairs(W.buttons) do sw = sw or b:find('##sheetsw', 1, true) ~= nil end
    check(not sw and W.sel() == 'Mate5' and W.shownMate() == nil, kind .. ': Stats view: no switch of Mate3 under Mate5 either')
    W.close()
end
do
    -- an older server and a sheet asked for before the squad list is there: whose it is cannot be told yet
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/sq gear 2'); feedSheet(W, 2); W.frame()
    check(not W.button('##slot2_5') and W.shownMate() == nil and W.sel() == nil, 'an older server, the squad list not read yet: the answer is kept back, not shown (it cannot be told whose it is)')
    feed(W); W.frame()
    check(W.button('##slot2_5') and W.shownMate() == 'Mate2', 'the squad list arrives and names slot 2 "Mate2": the answer that was kept is shown')
    W.close()
    W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/sq gear 2'); feedSheet(W, 2, { name = 'Somebody' }); W.frame(); feed(W); W.frame()
    check(not W.button('##slot2_5'), 'and one whose name is not that mate\'s is dropped')
    W.close()
    W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/sq gear 2'); feedSheet(W, 2, { slotLine = true }); W.frame()
    check(W.button('##slot2_5'), 'a server that says the slot: shown at once, with or without the squad list')
    W.close()
end

-- ================================================================= 10. Look: is a lockstyle on?
section('10. Look says whether a lockstyle is on, and what is waiting for the next call')
do
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame()
    W.click('Gear##gear1'); feedSheet(W, 1, { worn = { [5] = 13002 } }); W.frame()
    check(not W.text('Lockstyle:'), 'Equipment: no lockstyle line (it is about the look)')
    W.click('Look (lockstyle)##gvlook1')
    local off = W.text('Lockstyle: off (shows the gear it wears)')
    check(off and W.cell('##slot1_5', 'Haste Belt 13002') and not W.text('Lockstyle: on'), 'Look without a lockstyle: "Lockstyle: off (shows the gear it wears)", and the cells show the worn gear')
    feedSheet(W, 1, { worn = { [5] = 13002 }, ls = { [5] = 13009 } }); W.frame()
    local on = W.text('Lockstyle: on')
    check(on and W.text('(1 of 8 slots; the others show the gear it wears)') and W.cell('##slot1_5', 'Haste Belt 13009') and not W.text('Lockstyle: off'),
          'one slot locked: "Lockstyle: on (1 of 8 slots; the others show the gear it wears)", and Body shows the locked piece')
    check(on and off and not same(on.color, off.color or { 0, 0, 0, 0 }), 'on and off are not drawn in the same colour')
    local all = {}
    for _, e in ipairs({ 0, 1, 2, 4, 5, 6, 7, 8 }) do all[e] = 13100 + e end
    feedSheet(W, 1, { ls = all }); W.frame()
    check(W.text('Lockstyle: on') and W.text('(every slot that shows)'), 'all eight locked: "(every slot that shows)"')
    local from = #W.sent + 1
    W.click('Lockstyle off##lsoff1')
    feedSheet(W, 1, { worn = { [5] = 13002 } }); feed(W); W.frame()
    check(W.said('/say !squad lockstyle 1 off', from) == 1 and W.text('Lockstyle: off (shows the gear it wears)')
        and W.text('Gear changed: Mate1 shows it when called again.') and W.button('Apply##gearapply1'),
          'Lockstyle off: the line says off, and the change that waits for the next call is said with Apply next to it')
    W.click('Equipment##gvgear1')
    check(not W.text('Lockstyle:'), 'back on Equipment: no lockstyle line')
    W.close()
end

-- ================================================================= 11. (1.28) one look with the Gambits window
local Ux = dofile(HERE .. '/../../addons-src/servermenu/xifo_ui.lua')
local function round(n) return math.floor(n + 0.5) end
local function xs(W, needle, exact)   -- where the controls / texts with this label start, in drawing order
    local out = {}
    for _, e in ipairs(W.at) do if (exact and e.label == needle) or (not exact and has(e.label, needle)) then out[#out + 1] = e.x end end
    return out
end
local function allSame(list, n) if #list ~= n then return false end for _, v in ipairs(list) do if v ~= list[1] then return false end end return true end
local function order(W, ...)   -- the buttons appear in this order
    local at = 0
    for _, key in ipairs({ ... }) do
        local found = nil
        for i = at + 1, #W.buttons do if has(W.buttons[i], key) then found = i; break end end
        if not found then return false, key end
        at = found
    end
    return true
end

section('11a. title bars: ImGui\'s own, the theme\'s title colours, in the menu and the Profile alike')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.command('/sq gear 1'); feedSheet(W, 1); W.frame(); W.frame()
    local menu, sheet = 'Squads - XI: Forever Offline###sm_menu', 'Profile###sm_sheet'
    local pal = Ux.THEMES[name]
    check(W.flags[menu] ~= nil and W.flags[menu] % 2 == 0 and W.flags[sheet] ~= nil and W.flags[sheet] % 2 == 0,
          name .. ': both windows have a title bar (no NoTitleBar flag) and a fixed title; the Profile\'s is "Profile", not the mate\'s name')
    check(W.winColors[menu] and same(W.winColors[menu].TitleBg, pal.title or pal.header) and same(W.winColors[menu].TitleBgActive, pal.titleActive or pal.header)
        and same(W.winColors[sheet].TitleBg, W.winColors[menu].TitleBg) and same(W.winColors[sheet].TitleBgActive, W.winColors[menu].TitleBgActive),
          name .. ': the title colours are the palette\'s own (title / titleActive, else header), the same in both windows')
    check(not W.button('X##close') and not W.text('SQUADS') and W.button('Options##options'), name .. ': no heading and X button drawn by hand any more; Options is still there')
    W.close()
end

section('11b. tabs: the main ones one height, the choices inside a view smaller, plain buttons the usual height')
for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nscale=' .. scale .. '\n' })
    W.scale = scale
    W.command('/menu squad'); feed(W); W.command('/sq gear 1'); feedSheet(W, 1); W.frame(); W.frame()
    local main, small = round(Ux.SIZE.tab * scale), round(Ux.SIZE.tabCompact * scale)
    local function h(label) local s = W.sizes[label]; return s and s[2] end
    check(h('Squad##tabSquad') == main and h('Dualbox##tabDualbox') == main and h('Auto##tabAuto') == main and h('Stats##sheettabstats') == main and h('Gear##sheettabgear') == main,
          string.format('%d %%: Squad / Dualbox / Auto and Stats / Gear are all %d px high', scale * 100, main))
    check(h('Equipment##gvgear1') == small and h('Look (lockstyle)##gvlook1') == small and small < main, string.format('%d %%: Equipment / Look are the smaller kind (%d px)', scale * 100, small))
    check(h('Call all##callall') == 0 and h('Attack my target##sqattack') == 0 and h('Dismiss##dismiss1') == 0 and h('Gear##gear1') == 0,
          string.format('%d %%: plain buttons have ImGui\'s own frame height (no height of their own)', scale * 100))
    W.close()
end
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.command('/sq gear 1'); feedSheet(W, 1); W.frame(); W.frame()
    local m = Ux.menu(name)
    check(same(W.look['Squad##tabSquad'], m.c.sel) and not same(W.look['Dualbox##tabDualbox'] or { 0, 0, 0, 0 }, m.c.sel)
        and same(W.look['Gear##sheettabgear'], m.c.sel) and same(W.look['Equipment##gvgear1'], m.c.sel) and not same(W.look['Look (lockstyle)##gvlook1'] or { 0, 0, 0, 0 }, m.c.sel),
          name .. ': the selected tab of each row has the theme\'s tab colour, the others the button colour')
    W.close()
end
do
    local c = Ux.THEMES.crimson
    check(same(Ux.menu('crimson').c.sel, { 0.500, 0.165, 0.205, 1 }) and same(c.tabSel, { 0.500, 0.165, 0.205, 1 }), 'Crimson: that colour is its red (tabSel 0.500 0.165 0.205), unchanged')
end

section('11c. the commands in groups; Engage says what it does')
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    local ok, missing = order(W, 'callall', 'dismiss', 'refresh', 'sqattack', 'sqstop', '##engage', 'campset', 'autoequip', 'advanced')
    check(ok, 'Squad (Call all, Dismiss all, Refresh), Fight (Attack my target, Stop, Engage), Camp, Setup (Auto-equip, Advanced): in that order' .. (ok and '' or (' (missing ' .. tostring(missing) .. ')')))
    local col = round(Ux.SIZE.labelCol)
    local caps = true
    for _, cap in ipairs({ 'Squad', 'Fight', 'Camp' }) do local e = W.text(cap); caps = caps and e ~= nil and e.text == cap and same(e.color, Ux.menu('crimson').c.gold) end
    check(caps and xs(W, 'Call all##callall')[1] == col and xs(W, 'Attack my target##sqattack')[1] == col and xs(W, 'campset')[1] == col,
          'each group has its caption, and its first control starts in the same column (' .. col .. ' px)')
    check(W.button('Engage: after first hit##engage') and not W.text('they fight, you stay out of it'), 'Engage names the behaviour ("after first hit"); the explanation is no longer a line of its own')
    W.hover = true; W.frame(); W.hover = false
    local tipFight, tipEngage = false, false
    for _, t in ipairs(W.tips) do tipFight = tipFight or has(t, 'they fight, you stay out of it'); tipEngage = tipEngage or has(t, 'after your first hit') end
    check(tipFight and tipEngage, 'it is in the tooltips instead (Attack my target; Engage)')
    local from = #W.sent + 1
    W.click('##engage')
    check(W.said('/say !squad engage first', from) == 1 and W.button('Engage: when you engage##engage'),
          'a click sends the same "!squad engage first" as before; the button then says "when you engage" (1.29: its face is section 12c)')
    W.close()
end

section('11d. mate cards: the same first row on every card, everyday buttons on one row, settings folded away')
for _, width in ipairs({ 600, 620, 900 }) do
    for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
        local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nscale=' .. scale .. '\n' })
        W.width, W.scale = width, scale
        W.command('/menu squad'); feed(W, { away = { [3] = true, [6] = true }, state = { [2] = 'pending' } }); W.frame(); W.frame()
        local where = string.format('%d px, %d %%', width, scale * 100)
        local jobsX, statusX, actX = xs(W, ' 75 / '), {}, {}
        for _, e in ipairs(W.at) do
            if e.label == 'Out' or e.label == 'Away' then statusX[#statusX + 1] = e.x end
            if e.label:find('^Dismiss##dismiss%d') or e.label:find('^Call##call%d') or e.label:find('^ready in ') then actX[#actX + 1] = e.x end
        end
        check(allSame(jobsX, 6) and allSame(statusX, 6) and allSame(actX, 6) and jobsX[1] < statusX[1] and statusX[1] < actX[1],
              where .. ': on all six cards the jobs, the out / away word and Call / Dismiss (or its timer) start at the same three places')
        local alone = nil
        for i = 1, 6 do
            for _, key in ipairs({ 'Gear##gear' .. i, 'Profile##sheet' .. i, 'Food##food' .. i }) do if xs(W, key, true)[1] == 0 then alone = key end end
        end
        check(alone == nil and #W.over == 0, where .. ': Gear, Profile and Food stay on the row of Actions (none starts a line of its own), nothing beyond the edge' .. (alone and (' (' .. alone .. ')') or (W.over[1] and (' (' .. W.over[1] .. ')') or '')))
        W.close()
    end
end
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    check(W.combos['##role1'] == nil and W.combos['##mode1'] == nil and W.combos['##range1'] == nil and W.combos['##wswhen1'] == nil and W.combos['##job1'] == nil,
          'folded (the usual state): no Role, Mode, Range, weapon skill or Job list on the card')
    check(W.text('Role tank') and W.text('Mode balanced') and W.text('Range melee') and W.text('WS at 1000') and W.button('Settings >##more1'), 'what they are set to is said in a few muted words: Role tank, Mode balanced, Range melee, WS at 1000 ...')
    check(W.button('Actions ON##act1') and W.button('Gear##gear1') and W.button('Profile##sheet1') and W.button('Food##food1') and W.text('Rules') and W.button('Dismiss##dismiss1'),
          'the everyday things are there without unfolding: Actions, Gear, Profile, Food, the Rules line, Dismiss')
    local folded = W.childH['##sm_mate1']
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.combos['##role1'] == 'tank' and W.combos['##mode1'] == 'balanced' and W.combos['##range1'] == 'melee' and W.combos['##wswhen1'] == '1000' and W.combos['##job1'] == nil,
          'Settings unfolds Role, Mode, Range and WS at, with what they were set to (1.29: Job and Sub are behind Jobs, section 12b)')
    check(W.button('Settings v##more1') and same(W.look['Settings v##more1'], Ux.menu('crimson').c.sel) and W.combos['##role2'] == nil and #xs(W, 'Role tank') == 0, 'only that card; its button still says Settings, with the open mark, and is lit; the muted words are gone from it')
    local from = #W.sent + 1
    W.openCombo, W.pick = '##mode1', 'aggressive'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad mode 1 aggressive', from) == 1, 'a change made there sends what it always sent (!squad mode 1 aggressive)')
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.combos['##role1'] == nil and W.button('Settings >##more1'), 'a second click folds it again')
    -- the heights with the unfolded card out of view (the fixed card-height defect must not come back)
    W.clicks['##more2'] = true; W.frame()
    W.content['##sm_mate2'] = 190; W.frame(); W.frame()
    local tall = W.childH['##sm_mate2']
    W.view = { top = 600, h = 120 }; W.frame(); W.frame(); W.frame()
    check(tall == 198 and (W.skipped['##sm_mate2'] or 0) > 0 and W.childH['##sm_mate2'] == 198 and W.childH['##sm_mate1'] == folded,
          'an unfolded card scrolled out of view keeps its height (198), a folded one too (' .. tostring(folded) .. ')')
    W.close()
end

do
    -- an ImGui without child windows (the menu has a branch for it): the cards are drawn straight into the window
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    local im = package.loaded['imgui']
    rawset(im, 'BeginChild', false); rawset(im, 'EndChild', false)
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    local closed = false
    for _, p in ipairs(W.prints) do closed = closed or has(p, 'hit a problem') end
    check(not closed and W.button('Gear##gear6') ~= nil and W.colors == 0 and W.vars == 0, 'without BeginChild the six cards are still drawn and the menu stays open (1.27 closed itself here)')
    W.close()
end

section('11e. Rules line: the same place on every card; "skipped"')
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W, { away = { [5] = true } }); W.frame(); W.frame()
    local labels, texts = xs(W, 'Rules', true), {}
    for i, e in ipairs(W.at) do if e.label == 'Rules' and W.at[i + 1] then texts[#texts + 1] = W.at[i + 1].x end end
    check(allSame(labels, 6) and labels[1] == 0 and allSame(texts, 6) and texts[1] == round(52), 'six cards: "Rules" at the left edge, what runs right after it at the same place (52 px), called or not')
    local skipped = W.text('rules skipped)')
    check(skipped ~= nil and not W.text('left out') and same(skipped.color, Ux.menu('crimson').c.warn), 'a set with rules the mate cannot use: "(2 rules skipped)" in the warning colour (1.27: "left out")')
    W.hover = true; W.frame(); W.hover = false
    local why = false
    for _, t in ipairs(W.tips) do why = why or (has(t, 'cannot be used at this level or job') and has(t, 'Check, in the Gambits editor')) end
    check(why, 'the tooltip says what the count is (rules that cannot be used at this level or job) and where to see which')
    W.close()
end

section('11f. Profile: the mate row first; Gear rows as one strip each, in three groups')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    local m = Ux.menu(name)
    W.command('/menu squad'); feed(W); W.frame()
    W.click('Gear##gear1'); feedSheet(W, 1, { worn = { [5] = 13002 }, empty = { [9] = true, [14] = true } }); W.frame()
    W.command('/menu'); W.frame()   -- (the menu closed: only the Profile and the Squads button are drawn)
    local firstCombo = nil
    for _, e in ipairs(W.at) do if e.label:find('^##') and not e.label:find('sm_open') then firstCombo = e.label; break end end
    local named = 0
    for _, e in ipairs(W.texts) do if has(e.text, 'Mate1') then named = named + 1 end end
    check(firstCombo == '##sheetmate' and W.combos['##sheetmate'] == 'Mate1' and W.text('WAR 75 / MNK 37') and named == 0,
          name .. ': the first control is the mate list ("Mate1"), its jobs next to it; the name is written nowhere else in the window')
    local want = { 0, 1, 2, 3, 4, 5, 6, 7, 8, 15, 9, 10, 11, 12, 13, 14 }
    local got = {}
    for _, b in ipairs(W.buttons) do local e = b:match('^##slot1_(%d+)$'); if e then got[#got + 1] = tonumber(e) end end
    local sameOrder = #got == 16
    for i = 1, 16 do sameOrder = sameOrder and got[i] == want[i] end
    local caps, last = true, 0
    for _, cap in ipairs({ 'Weapons', 'Armor', 'Accessories' }) do
        local found = nil
        for i = last + 1, #W.texts do if W.texts[i].text == cap then found = i; break end end
        caps = caps and found ~= nil; last = found or last
    end
    check(sameOrder and caps, name .. ': weapons and ammunition, then armour, then accessories (captions in that order; slots 0 1 2 3 | 4 5 6 7 8 15 | 9 10 11 12 13 14)')
    local col2 = xs(W, '##slot1_12', true)[1]
    check(xs(W, '##slot1_11', true)[1] == 0 and col2 > 0 and xs(W, '##slot1_13', true)[1] == 0 and xs(W, '##slot1_14', true)[1] == col2 and xs(W, '##slot1_1', true)[1] == col2,
          name .. ': two columns; Ear 1 | Ear 2 on one row, Ring 1 | Ring 2 on one row')
    local body, neck = W.cells['##slot1_5'], W.cells['##slot1_9']
    check(body and body[1].text == 'Body' and body[2].text == 'Haste Belt 13002' and same(body[2].color, m.c.text) and same(body[1].color, m.c.text),
          name .. ': a row is one button with the slot\'s name and the item\'s name over it, each in its own colour')
    check(neck and neck[1].text == 'Neck' and neck[2].text == 'Empty' and same(neck[2].color, m.c.dim), name .. ': an empty slot says "Empty", in the colour for secondary text')
    -- selection: a frame (a tint and a thin line), and the worn piece in the list keeps its own mark
    local from = #W.sent + 1
    W.click('##slot1_5')
    check(W.said('/say !squad gearlist 1 5', from) == 1, name .. ': a click anywhere on the row selects the slot (the same !squad gearlist 1 5)')
    for k = 1, 3 do W.line(string.format('squadpanel:gl|1|5|%d|%d|haste_belt', 13000 + k, 70 - k)) end
    W.line('squadpanel:gle|1|5|3'); W.frame()
    local fill, lines = 0, 0
    for _, r in ipairs(W.rects) do
        if same(r[5], m.c.rowFill) then fill = fill + 1 end
        if same(r[5], m.c.rowLine) then lines = lines + 1 end
    end
    check(fill == 1 and lines == 4, name .. ': the selected row has the theme\'s row tint and a thin line around it (1 fill, 4 bars: ' .. fill .. ', ' .. lines .. '), no other row has')
    check(same(m.c.rowFill, { Ux.THEMES[name].rowSel[1], Ux.THEMES[name].rowSel[2], Ux.THEMES[name].rowSel[3], 0.42 }), name .. ': that tint is the palette\'s own rowSel, lighter')
    check(W.button('(worn)##gpi1_13002_2') and same(W.look['Lv68 Haste Belt 13002  (worn)##gpi1_13002_2'], m.c.on) and W.cell('##slot1_5', 'Haste Belt 13002'),
          name .. ': the piece that is worn is still marked in the list (green), and the selected row still reads its item')
    from = #W.sent + 1
    W.click('##gpi1_13001_1')
    check(W.said('/say !squad equip 1 13001 body', from) == 1, name .. ': equipping is the same command as before (!squad equip 1 13001 body)')
    W.close()
end
do
    -- nothing cut off in the Profile either, at its narrowest, its first size and its widest, 75 to 200 %
    local worst, where = 0, nil
    for _, width in ipairs({ 540, 580, 800 }) do
        for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
            local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nscale=' .. scale .. '\n' })
            W.width, W.scale = width, scale
            W.command('/menu squad'); feed(W); W.frame()
            W.click('Gear##gear1'); feedSheet(W, 1, { worn = { [5] = 13002 } }); W.frame()
            W.click('##slot1_5')
            for k = 1, 12 do W.line(string.format('squadpanel:gl|1|5|%d|%d|a_rather_long_item_name', 13000 + k, 70 - k)) end
            W.line('squadpanel:gle|1|5|12'); W.command('/menu'); W.frame(); W.frame()
            if #W.over > worst then worst, where = #W.over, string.format('%d px at %d %%: %s', width, scale * 100, tostring(W.over[1])) end
            W.close()
        end
    end
    check(worst == 0, 'Profile, Gear view with a list of 12 pieces, 540 / 580 / 800 px at 75 / 100 / 150 / 200 %: no control beyond the edge' .. (where and (' (' .. where .. ')') or ''))
    -- and the menu with every card unfolded
    worst, where = 0, nil
    for _, width in ipairs({ 600, 620, 900 }) do
        for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
            local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nscale=' .. scale .. '\n' })
            W.width, W.scale = width, scale
            W.command('/menu squad'); feed(W); W.frame()
            for i = 1, 6 do W.clicks['##more' .. i] = true end
            W.frame(); W.frame()
            if #W.over > worst then worst, where = #W.over, string.format('%d px at %d %%: %s', width, scale * 100, tostring(W.over[1])) end
            W.close()
        end
    end
    check(worst == 0, 'the menu with all six cards unfolded, 600 / 620 / 900 px at 75 / 100 / 150 / 200 %: no control beyond the edge' .. (where and (' (' .. where .. ')') or ''))
end

-- ================================================================= 12. (1.29) follow-up from the first DEV session
local function statusWords(W)   -- how many of the three status words are drawn, and where each card's Call / Dismiss starts
    local n, at = { Out = 0, Away = 0, ['Calling...'] = 0 }, {}
    for _, e in ipairs(W.at) do
        if n[e.label] ~= nil then n[e.label] = n[e.label] + 1 end
        local slot = e.label:match('^Dismiss##dismiss(%d)$') or e.label:match('^Call##call(%d)$')
        if slot then at[tonumber(slot)] = e.x end
    end
    return n, at
end

section('12a. Call: one status at a time (Away, Calling..., Out), Call and Dismiss in one place, the Rules line during the call')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    local m = Ux.menu(name)
    local away = { [3] = true, [4] = true }
    W.command('/menu squad'); feed(W, { away = away, cd = 0 }); W.frame(); W.frame()
    local n0, at0 = statusWords(W)
    check(n0.Out == 4 and n0.Away == 2 and n0['Calling...'] == 0 and W.button('Call##call4') and not W.text('on its way') and not W.text('calling again'),
          name .. ': four mates out, two away: six cards, one status word each (4 Out, 2 Away)')
    local h3, h1 = W.childH['##sm_mate4'], W.childH['##sm_mate1']
    local from = #W.sent + 1
    W.clicks['Call##call4'] = true; W.frame(); W.frame()
    local n1, at1 = statusWords(W)
    check(n1['Calling...'] == 1 and n1.Away == 1 and n1.Out == 4, name .. ': Call on mate 4: its card says "Calling..." at once, and only that card (mate 3 is still Away)')
    check(at1[4] == at0[4] and at1[4] == at1[1] and W.sizes['Call##call4'][1] == W.sizes['Dismiss##dismiss1'][1] and same(W.look['Call##call4'], m.c.busy)
        and W.childH['##sm_mate4'] == h3 and W.childH['##sm_mate1'] == h1,
          name .. ': the Call button stays where it was, as wide as Dismiss, greyed; no card changed its height')
    local expect, active = W.text('Next call: Gambits: A rather long Rule Set name 4'), W.text('Not called.  Next call: Default')
    check(expect ~= nil and same(expect.color, m.c.dim) and not W.text('Calling again...'),
          name .. ': its Rules line says what is expected ("Next call: Gambits: ..."), muted; not "Calling again..."')
    check(active ~= nil, name .. ': mate 3, not called, still says "Not called.  Next call: Default ... job rules"')
    W.clicks['Call##call4'] = true; W.frame(); for _ = 1, 2 do W.frame(2.5) end
    check(W.said('/say !squad call 4', from) == 1, name .. ': a second click on the greyed button sends nothing: one "!squad call 4"')
    -- the server says the mate is out
    feed(W, { away = { [3] = true }, cd = 0, state = { [4] = 'set' } }); W.frame()
    local n2, at2 = statusWords(W)
    -- (the menu asks again after a call, as it does since 1.26n; that answer is the one the Rules line is drawn from)
    local shownFirst = nil
    for i, e in ipairs(W.at) do if e.label == 'Rules' and W.at[i + 1] and shownFirst == nil and i > 1 then local k = 0; for j = 1, i do if W.at[j].label == 'Rules' then k = k + 1 end end if k == 4 then shownFirst = W.at[i + 1].label end end end
    W.frame(2.5); feed(W, { away = { [3] = true }, cd = 0, state = { [4] = 'set' } }); W.frame()
    local run = nil
    for _, e in ipairs(W.texts) do if e.text == 'Gambits: A rather long Rule Set name 4' then run = e end end
    check(n2.Out == 5 and n2['Calling...'] == 0 and n2.Away == 1 and at2[4] == at1[4] and W.button('Dismiss##dismiss4'),
          name .. ': the squad list says mate 4 is out: "Out", and Dismiss stands where Call stood')
    check(run ~= nil and same(run.color, m.c.good) and not W.text('Next call: Gambits: A rather long Rule Set name 4'),
          name .. ': its Rules line now says what it RUNS (green, the server\'s word); the expected line is gone (right after the first answer it said: ' .. tostring(shownFirst) .. ')')
    W.close()
end
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W, { away = { [3] = true, [4] = true }, cd = 0 }); W.frame()
    -- refused: the server answers with a call timer for that mate
    W.clicks['Call##call3'] = true; W.frame(); W.frame()
    check(statusWords(W)['Calling...'] == 1 and W.text('Next call: Default') ~= nil and W.text('Next call: Default').text:find('^Next call: Default %u+ job rules') ~= nil,
          'Call on mate 3, which has no Rule Set chosen: Calling..., and its Rules line says "Next call: Default ... job rules"')
    W.frame(1.5); feed(W, { away = { [3] = true, [4] = true }, cd = 0, cdOf = { [3] = 90 } }); W.frame()
    local n = statusWords(W)
    check(n['Calling...'] == 0 and n.Away == 2 and W.text('ready in') and not W.button('Call##call3'),
          'the squad list comes back with a call timer for it (the call was refused): Away again, with "ready in", at once')
    -- expired: no word from the server at all
    W.clicks['Call##call4'] = true; W.frame(); W.frame()
    check(statusWords(W)['Calling...'] == 1, 'Call on mate 4: Calling...')
    W.frame(6.0)
    check(statusWords(W)['Calling...'] == 1, 'six seconds later it still says Calling...')
    W.frame(6.5); W.frame()
    n = statusWords(W)
    check(n['Calling...'] == 0 and W.button('Call##call4') and not same(W.look['Call##call4'], Ux.menu('crimson').c.busy), 'after twelve seconds without the mate: Away, and Call can be pressed again')
    W.close()
    -- Call all, a typed call, and Dismiss all
    W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W, { away = { [2] = true, [5] = true, [6] = true }, cd = 0 }); W.frame()
    W.clicks['Call all##callall'] = true; W.frame(); W.frame()
    n = statusWords(W)
    check(n['Calling...'] == 3 and n.Away == 0 and n.Out == 3, 'Call all: the three mates that were away say Calling..., the three that are out stay Out')
    W.clicks['Dismiss all##dismiss'] = true; W.frame()
    feed(W, { away = { [1] = true, [2] = true, [3] = true, [4] = true, [5] = true, [6] = true }, cd = 0 }); W.frame(13); W.frame()
    check(statusWords(W).Away == 6, 'Dismiss all, and the list says nobody is out: six times Away')
    W.command('/say !squad call 2'); W.frame()
    check(statusWords(W)['Calling...'] == 1, 'a "!squad call 2" typed in chat: mate 2 says Calling... too')
    W.close()
end

section('12b. Jobs is a button of its own; Settings keeps its name; what is behind each')
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    mkdir(W.dir .. '/config/addons/xiforever/Testcharone_1'); put(W.dir .. '/config/addons/xiforever/Testcharone_1/gambits.loaded', 'Gambits\n')
    W.frame(2.1); W.frame()
    check(order(W, 'Actions ON##act1', 'Jobs >##jobs1', 'Gambits##gsq1', 'Gear##gear1', 'Profile##sheet1', 'Food##food1', 'Settings >##more1'),
          'the row of a folded card: Actions, Jobs, Gambits, Gear, Profile, Food, Settings')
    check(W.combos['##job1'] == nil and W.combos['##sub1'] == nil and W.combos['##role1'] == nil, 'folded: no Job, Sub or Role list')
    W.clicks['##jobs1'] = true; W.frame(); W.frame()
    check(W.button('Jobs v##jobs1') and same(W.look['Jobs v##jobs1'], Ux.menu('crimson').c.sel) and W.combos['##job1'] ~= nil and tostring(W.combos['##sub1']):find('^MNK') ~= nil
        and W.combos['##role1'] == nil and W.combos['##job2'] == nil and W.button('Settings >##more1'),
          'Jobs unfolds Job and Sub on that card only (its mark turns, the button is lit); Settings is still closed')
    check(not W.text('A job your character has not unlocked'), 'the unlocked-job help is no longer a line on the card')
    W.hover = true; W.frame(); W.hover = false
    local tip = false
    for _, t in ipairs(W.tips) do tip = tip or has(t, 'A job your character has not unlocked is refused by the server') end
    check(tip, 'it is the tooltip of the Job and Sub lists')
    local from = #W.sent + 1
    W.openCombo, W.pick = '##job1', 'WHM'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad job 1 WHM', from) == 1, 'a job picked there sends what it always sent (!squad job 1 WHM); the server decides')
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.button('Settings v##more1') and same(W.look['Settings v##more1'], Ux.menu('crimson').c.sel) and not W.button('Less##more1')
        and W.combos['##role1'] ~= nil and W.combos['##mode1'] ~= nil and W.combos['##range1'] ~= nil and W.combos['##wswhen1'] ~= nil and W.combos['##size1'] ~= nil,
          'Settings open: the button still says Settings (its mark turned); Role, Mode, Range, WS and Size are inside')
    W.clicks['##jobs1'] = true; W.frame(); W.frame()
    check(W.button('Jobs >##jobs1') and W.combos['##job1'] == nil and W.combos['##role1'] ~= nil, 'Jobs folded again: Job and Sub are gone, Settings stays open (the two are independent)')
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.button('Settings >##more1') and W.combos['##role1'] == nil, 'Settings folded again')
    W.close()
    -- nothing cut off with both open on every card
    local worst, where = 0, nil
    for _, width in ipairs({ 600, 620, 900 }) do
        for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
            W = world({ cfg = 'theme=crimson\nbutton_wide=true\nscale=' .. scale .. '\n' })
            W.width, W.scale = width, scale
            W.command('/menu squad'); feed(W, { away = { [3] = true }, cd = 0 }); W.frame()
            for i = 1, 6 do W.clicks['##more' .. i], W.clicks['##jobs' .. i] = true, true end
            W.clicks['Call##call3'] = true
            W.frame(); W.frame()
            local alone = nil
            for i = 1, 6 do
                for _, key in ipairs({ 'Jobs v##jobs' .. i, 'Gear##gear' .. i, 'Profile##sheet' .. i, 'Food##food' .. i }) do if xs(W, key, true)[1] == 0 then alone = key end end
            end
            if #W.over > worst or alone then worst, where = math.max(#W.over, 1), string.format('%d px at %d %%: %s', width, scale * 100, tostring(alone or W.over[1])) end
            W.close()
        end
    end
    check(worst == 0, 'six cards with Jobs and Settings open and one mate being called, 600 / 620 / 900 px at 75 / 100 / 150 / 200 %: nothing beyond the edge, no button alone on a line' .. (where and (' (' .. where .. ')') or ''))
end

section('12c. Engage is a plain button; the green stays for what is switched on')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    local m = Ux.menu(name)
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    local plain = W.look['Call all##callall']
    W.click('##engage')
    check(W.button('Engage: when you engage##engage') and same(W.look['Engage: when you engage##engage'], plain) and not same(plain, m.c.on)
        and same(W.look['Actions ON##act1'], m.c.on),
          name .. ': Engage in either setting has the face of an ordinary button (like Call all); Actions ON is the green one')
    W.close()
end

section('12d. Gear rows in the game\'s own terms: the cursor position as two numbers')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    local m = Ux.menu(name)
    local im = package.loaded['imgui']
    im.GetCursorScreenPos = function() return 40, 60 end   -- (Ashita: x, y; 1.28 only read a table and drew the rows the older way)
    W.command('/menu squad'); feed(W); W.frame()
    W.click('Gear##gear1'); feedSheet(W, 1, { worn = { [5] = 13002 }, empty = { [9] = true, [0] = true } }); W.frame()
    local body, neck, main = W.cells['##slot1_5'], W.cells['##slot1_9'], W.cells['##slot1_0']
    check(body ~= nil and not W.button('Body:  Haste Belt 13002') and body[1].text == 'Body' and body[2].text == 'Haste Belt 13002'
        and same(body[1].color, m.c.text) and same(body[2].color, m.c.text),
          name .. ': a worn slot: one strip, the slot\'s name and the item\'s name in the usual text colour')
    check(neck ~= nil and neck[1].text == 'Neck' and same(neck[1].color, m.c.text) and neck[2].text == 'Empty' and same(neck[2].color, m.c.dim) and not same(m.c.dim, m.c.text)
        and main ~= nil and main[2].text == 'Empty' and same(main[2].color, m.c.dim),
          name .. ': an empty slot: its name in the usual colour, "Empty" in the theme\'s colour for secondary text')
    local from = #W.sent + 1
    W.click('##slot1_9'); W.line('squadpanel:gle|1|9|0'); W.frame()
    local fill, bars = 0, 0
    for _, r in ipairs(W.rects) do
        if same(r[5], m.c.rowFill) then fill = fill + 1 end
        if same(r[5], m.c.rowLine) then bars = bars + 1 end
    end
    check(W.said('/say !squad gearlist 1 9', from) == 1 and fill == 1 and bars == 4 and W.cell('##slot1_9', 'Empty') and W.cell('##slot1_5', 'Haste Belt 13002'),
          name .. ': the empty row is clickable over its whole width and gets the selection frame; the other rows read as before')
    W.close()
end

-- ================================================================= 13. (1.30) Settings layout, Profile stats, the launcher
local function atOf(W, needle, exact)   -- the first entry of W.at with this label: its index, x and width
    for i, e in ipairs(W.at) do
        if (exact and e.label == needle) or (not exact and has(e.label, needle)) then return i, e.x, e.w end
    end
end

section('13a. a card\'s Settings: a thin line under the buttons, two columns, Size on its own row with "Save size"')
for _, width in ipairs({ 600, 620, 900 }) do
    for _, scale in ipairs({ 0.75, 1, 1.5, 2 }) do
        local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nscale=' .. scale .. '\n' })
        W.width, W.scale = width, scale
        W.command('/menu squad'); feed(W); W.frame()
        W.clicks['##more1'] = true; W.frame(); W.frame()
        local where = string.format('%d px, %d %%', width, scale * 100)
        local iBtn = atOf(W, 'Settings v##more1', true)
        local iSep = nil
        for i = (iBtn or 1), #W.at do if W.at[i].label == 'separator' then iSep = i; break end end
        local iRole, xRole = atOf(W, '##role1', true)
        local _, xMode = atOf(W, '##mode1', true)
        local _, xRange = atOf(W, '##range1', true)
        local iWhen, xWhen = atOf(W, '##wswhen1', true)
        local iWhich, xWhich = atOf(W, '##wswhich1', true)
        local _, xSize = atOf(W, '##size1', true)
        local _, xSave = atOf(W, 'Save size##setsize1', true)
        check(iBtn and iSep and iRole and iSep > iBtn and iSep < iRole, where .. ': the line is drawn after the buttons and before Role')
        check(xRole == xRange and xRole == xSize and xMode == xWhen and xMode > xRole and iWhich == iWhen + 1 and xWhich > xWhen and #W.over == 0,
              where .. ': Role, Range and Size start in one column, Mode and the weapon skill lists in the other; the two weapon skill lists stand together; nothing beyond the edge')
        check(xSave ~= nil and xSave > xSize and not W.button('Set for good'), where .. ': Size and "Save size" share a row of their own; "Set for good" is gone')
        -- (1.31) Jobs open as well: Sub stands where Mode and WS at stand, name under name and list under list
        W.clicks['##jobs1'] = true; W.frame(); W.frame()
        local function labelX(text)   -- where the last text with these words starts
            local x = nil
            for _, e in ipairs(W.at) do if e.label == text then x = e.x end end
            return x
        end
        local _, xJob = atOf(W, '##job1', true)
        local _, xSub = atOf(W, '##sub1', true)
        local _, xMode2 = atOf(W, '##mode1', true)
        local _, xWhen2 = atOf(W, '##wswhen1', true)
        check(xSub ~= nil and xSub == xMode2 and xSub == xWhen2 and xJob == xRole and #W.over == 0,
              where .. ': (1.31) the Sub list starts where the Mode and WS at lists start, Job where Role does; nothing beyond the edge')
        check(labelX('Sub') ~= nil and labelX('Sub') == labelX('Mode') and labelX('Sub') == labelX('WS at') and labelX('Sub') < xSub,
              where .. ': (1.31) the names Sub, Mode and WS at start at one place')
        local iSep2, iJob2, iRole2 = nil, atOf(W, '##job1', true), atOf(W, '##role1', true)
        for i = (iJob2 or 1), #W.at do if W.at[i].label == 'separator' then iSep2 = i; break end end
        check(iJob2 and iSep2 and iRole2 and iJob2 < iSep2 and iSep2 < iRole2, where .. ': (1.31) the line still stands between Jobs and Settings')
        W.close()
    end
end
do
    -- narrower than the menu can be made (its smallest width is 600): the second column goes to a new line, nothing is cut
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.width = 380
    W.command('/menu squad'); feed(W); W.frame()
    W.clicks['##more1'], W.clicks['##jobs1'] = true, true; W.frame(); W.frame()
    local _, xRole = atOf(W, '##role1', true)
    local _, xMode = atOf(W, '##mode1', true)
    local iWhen, xWhen = atOf(W, '##wswhen1', true)
    local iWhich = atOf(W, '##wswhich1', true)
    local cut = nil
    for _, o in ipairs(W.over) do if has(o, '##role1') or has(o, '##mode1') or has(o, '##range1') or has(o, '##wswhen1') or has(o, '##wswhich1') or has(o, '##size1') or has(o, 'setsize1') then cut = o end end
    do
        local _, xJobN = atOf(W, '##job1', true)
        local _, xSubN = atOf(W, '##sub1', true)
        local cutSub = nil
        for _, o in ipairs(W.over) do if has(o, '##sub1') or has(o, '##job1') then cutSub = o end end
        check(xSubN ~= nil and xSubN == xJobN and cutSub == nil, '(1.31) a 380 px window: Sub wraps under Job, in the first column; neither is cut' .. (cutSub and (' (' .. cutSub .. ')') or ''))
    end
    check(xMode == xRole and xWhen == xRole and iWhich == iWhen + 1 and cut == nil, 'a 380 px window: Mode and the weapon skill lists wrap under Role and Range, in the first column, still together; none is cut' .. (cut and (' (' .. cut .. ')') or ''))
    -- Jobs and Settings stay independent, and the commands are what they were
    check(W.combos['##job1'] ~= nil and W.combos['##role1'] ~= nil, 'Jobs and Settings open together')
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.combos['##job1'] ~= nil and W.combos['##role1'] == nil, 'Settings folded: Jobs stays open')
    W.clicks['##more1'] = true; W.frame(); W.frame()
    W.hover = true; W.frame(); W.hover = false
    local once = false
    for _, t in ipairs(W.tips) do once = once or (has(t, 'at every call from now on') and has(t, 'only ONCE')) end
    check(once, 'the tooltip of "Save size" says that it is kept for every later call and can be saved only once')
    local from = #W.sent + 1
    W.openCombo, W.pick = '##size1', 'large'; W.frame(); W.openCombo, W.pick = nil, nil
    W.clicks['Save size##setsize1'] = true; W.frame(); for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad size 1 large', from) == 1, '"Save size" sends what "Set for good" sent: !squad size 1 large (the server stores it, once)')
    check(not W.button('Save size##setsize1') and W.combos['##size1'] == nil, 'once a size is saved the row is gone (the server would refuse a second one)')
    W.close()
end

section('13b. Profile > Stats: Role / Mode / Race named, Actions, vitals, Attributes and Combat with numbers in line, "Live stats"')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    local m = Ux.menu(name)
    W.command('/menu squad'); feed(W); W.frame()
    W.click('Profile##sheet1'); feedSheet(W, 1, { slotLine = true, statOf = { STR = 7, DEX = 70, VIT = 700 }, combatOf = { Attack = 9, Accuracy = 1234 } }); W.frame()
    W.command('/menu'); W.frame()
    local function after(label) for i, e in ipairs(W.texts) do if e.text == label then return e, W.texts[i + 1] end end end
    local rl, rv = after('Role'); local ml, mv = after('Mode'); local cl, cv = after('Race')
    check(rl and same(rl.color, m.c.dim) and rv.text == 'tank' and same(rv.color, m.c.text) and ml and mv.text == 'balanced' and cl and cv.text == 'Hume',
          name .. ': "Role tank", "Mode balanced", "Race Hume": a muted name and its value, each named')
    check(W.text('Actions') and W.button('Melee: on##sheetsw1melee') and W.button('Ranged: on##sheetsw1ranged') and W.button('Job abilities: on##sheetsw1ja') and W.button('Magic: on##sheetsw1magic')
        and same(W.look['Job abilities: on##sheetsw1ja'], m.c.on),
          name .. ': Actions: Melee, Ranged, Job abilities (spelled out), Magic, each with its state in words and lit while on')
    local live = W.text('Live stats')
    local order, last = true, 0
    for _, want in ipairs({ 'Live stats', 'HP 1500 / 1600', 'MP 0 / 0', 'TP 1200', 'EXP  1,200 / 44,000', 'Attributes', 'Combat' }) do
        local found = nil
        for i = last + 1, #W.texts do if has(W.texts[i].text, want) then found = i; break end end
        order = order and found ~= nil; last = found or last
    end
    check(live and same(live.color, m.c.gold) and order, name .. ': "Live stats", then HP, MP, TP, then EXP, then Attributes and Combat, in that order')
    -- numbers end at the same place in their column
    local function endOf(value, nth)
        local k = 0
        for _, e in ipairs(W.at) do if e.label == value then k = k + 1; if k == (nth or 1) then return e.x + e.w end end end
    end
    local e7, e70, e700, e9, e1234 = endOf('7'), endOf('70'), endOf('700'), endOf('9'), endOf('1234')
    check(e7 and e7 == e70 and e70 == e700 and e9 and e9 == e1234 and e9 > e7, string.format('%s: STR 7, DEX 70 and VIT 700 end at the same place (%s); Attack 9 and Accuracy 1234 too (%s)', name, tostring(e7), tostring(e9)))
    check(#W.over == 0, name .. ': nothing beyond the edge' .. (W.over[1] and (' (' .. W.over[1] .. ')') or ''))
    -- a switch
    local from = #W.sent + 1
    W.clicks['##sheetsw1ja'] = true; W.frame(); W.frame()
    check(W.button('Job abilities: off##sheetsw1ja') and not same(W.look['Job abilities: off##sheetsw1ja'], m.c.on), name .. ': a click on Job abilities: it says "off" at once and is no longer lit')
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad sw 1 ja off', from) == 1, name .. ': and sends the same switch command as before (!squad sw 1 ja off)')
    W.close()
end
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W, { away = { [3] = true } }); W.frame()
    W.click('Profile##sheet1'); feedSheet(W, 1, { slotLine = true }); W.frame()
    check(W.text('Live stats') ~= nil, 'a mate that is out, a fresh sheet: "Live stats"')
    -- dismissed: the squad list says away while the last sheet is still the one read when it was out
    feed(W, { away = { [1] = true, [3] = true } }); W.frame()
    check(not W.text('Live stats') and W.text('Stats') and W.text('(the last reading: not live now)') and W.text('HP 1500 / 1600'),
          'the squad list says that mate is away now: the numbers are still shown, as "the last reading: not live now"')
    feedSheet(W, 1, { slotLine = true, notCalled = true }); W.frame()
    check(not W.text('Live stats') and not W.text('Attributes') and not W.text('HP 1500') and W.text('Not called right now') and W.text('EXP  1,200 / 44,000'),
          'its next sheet, not called: no vitals, no Attributes or Combat, the server\'s note; EXP (stored data) is still there')
    -- an uncalled mate, then a summoned one, then back: the label follows the mate that is shown
    W.command('/sq sheet 3'); feedSheet(W, 3, { slotLine = true, notCalled = true }); W.frame()
    check(W.sel() == 'Mate3' and not W.text('Live stats') and W.text('Stats'), 'an uncalled mate: "Stats", never "Live stats"')
    W.command('/sq sheet 2'); W.frame()
    feedSheet(W, 3, { slotLine = true, notCalled = true }); feedSheet(W, 1, { slotLine = true }); W.frame()
    check(not W.text('Live stats') and not W.text('HP 1500'), 'switched to mate 2, late answers for mates 3 and 1 arrive: no numbers and no "Live stats" from another mate')
    feedSheet(W, 2, { slotLine = true }); W.frame()
    check(W.sel() == 'Mate2' and W.text('Live stats') ~= nil, 'mate 2\'s own sheet (it is out): "Live stats"')
    -- no fresh reading for a while
    W.frame(6.5); W.frame(6.5)
    check(not W.text('Live stats') and W.text('(the last reading: not live now)'), 'no answer for 13 seconds: the same numbers are no longer called live')
    feedSheet(W, 2, { slotLine = true }); W.frame()
    check(W.text('Live stats') ~= nil, 'the next answer: live again')
    W.close()
end

section('13c. the launcher: one control, a Squads half and a Gambits half; only while the character is in the world')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local W = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\n' })
    local m = Ux.menu(name)
    feed(W); W.frame(); W.frame()
    local iS, xS = atOf(W, 'Squads##sm_open', true)
    local iG, xG = atOf(W, 'Gambits##sm_gsq', true)
    check(iS and iG and iG == iS + 2 and W.at[iS + 1].label == 'dummy' and W.at[iS + 1].w == 1 and xG > xS and W.wins['##servermenu_button'] == 1,
          name .. ': one small window with Squads, a 1 px divider and Gambits, in that order')
    check(W.sizes['Squads##sm_open'][2] == 20 and W.sizes['Gambits##sm_gsq'][2] == 20 and W.at[iS + 1].w == 1,
          name .. ': (1.31) both halves are 20 px high, about a menu button (19), no longer 30')
    check(W.sizes['Squads##sm_open'][1] == 54 and W.sizes['Gambits##sm_gsq'][1] == 60, name .. ': (1.31) less room beside the two full labels (54 and 60 px, were 62 and 68)')
    do
        -- one outline: the window is the button (face and border), the halves have neither
        local face = nil
        for _, item in ipairs(m.button) do if item[1] == 'ImGuiCol_Button' then face = item[2] end end
        local clear = W.look['Gambits##sm_gsq']
        check(same(W.winColors['##servermenu_button'].WindowBg, face) and type(clear) == 'table' and clear[4] == 0,
              name .. ': (1.31) the window has the launcher\'s button colour, a half that is neither lit nor under the mouse has no face of its own')
        check(W.pushed.vWindowBorderSize == 1 and W.pushed.vFrameBorderSize == 0 and type(W.pushed.vWindowMinSize) == 'table' and W.pushed.vWindowMinSize[2] == 1
              and type(W.pushed.vWindowPadding) == 'table',
              name .. ': (1.31) one border (the window\'s), none around a half, and the window may be as low as its buttons')
    end
    check(not same(W.look['Squads##sm_open'], m.c.sel) and not same(W.look['Gambits##sm_gsq'], m.c.sel) and W.wins['Squads - XI: Forever Offline###sm_menu'] == nil,
          name .. ': the menu is closed: neither half is lit')
    W.clicks['Squads##sm_open'] = true; W.frame(); W.frame()
    check(W.wins['Squads - XI: Forever Offline###sm_menu'] == 1 and same(W.look['Squads##sm_open'], m.c.sel) and not same(W.look['Gambits##sm_gsq'], m.c.sel),
          name .. ': a click on Squads opens the menu; the Squads half is lit while it is open, the Gambits half is not')
    W.clicks['Squads##sm_open'] = true; W.frame(); W.frame()
    check(W.wins['Squads - XI: Forever Offline###sm_menu'] == nil and not same(W.look['Squads##sm_open'], m.c.sel), name .. ': a second click closes it, and the half is no longer lit')
    W.close()
end
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nbutton_x=100\nbutton_y=200\n' })
    feed(W); W.frame()
    -- Gambits is not loaded: the half is there, a click sends nothing to the game
    local from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    local told = false
    for _, p in ipairs(W.prints) do told = told or has(p, 'Gambits is not loaded') end
    check(W.said('/gambits', from) == 0 and told, 'Gambits is not loaded: a click on the Gambits half sends no command (it says so in the log)')
    mkdir(W.dir .. '/config/addons/xiforever/Testcharone_1'); put(W.dir .. '/config/addons/xiforever/Testcharone_1/gambits.loaded', 'Gambits\n')
    W.frame(2.1); W.frame()
    from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    local exact = 0
    for i = from, #W.sent do if W.sent[i] == '/gambits show' then exact = exact + 1 end end
    check(exact == 1 and W.said('/gambits', from) == 1 and W.wins['Squads - XI: Forever Offline###sm_menu'] == nil,
          'Gambits is loaded: the Gambits half sends "/gambits show" (no slot: the editor opens on the mate it had last) and does not open the Squads menu')
    -- the Gambits button of a mate's card still names its mate
    W.clicks['Squads##sm_open'] = true; W.frame(); feed(W); W.frame(2.1); W.frame()
    from = #W.sent + 1
    W.clicks['Gambits##gsq4'] = true; W.frame(); W.frame()
    check(W.sent[#W.sent] == '/gambits show 4' and W.said('/gambits show 4', from) == 1, 'the Gambits button on mate 4\'s card still sends "/gambits show 4"')
    W.clicks['Squads##sm_open'] = true; W.frame(); W.frame()
    -- hover: each half on its own
    W.hoverOn = 'Gambits##sm_gsq'; W.frame()
    local tipG, tipS = false, false
    for _, t in ipairs(W.tips) do tipG = tipG or has(t, 'Rule Set editor'); tipS = tipS or has(t, 'Squads  (/menu)') end
    check(tipG and not tipS, 'the mouse over the Gambits half: its own tooltip, not the Squads half\'s')
    W.hoverOn = 'Squads##sm_open'; W.frame()
    tipG, tipS = false, false
    for _, t in ipairs(W.tips) do tipG = tipG or has(t, 'Rule Set editor'); tipS = tipS or has(t, 'Squads  (/menu)') end
    check(tipS and not tipG, 'and over the Squads half: the Squads tooltip only')
    W.hoverOn = nil
    -- dragging either half moves the control and opens nothing
    for _, half in ipairs({ 'Gambits##sm_gsq', 'Squads##sm_open' }) do
        local x0 = tonumber(W.cfg():match('button_x=(%-?%d+)')); local y0 = tonumber(W.cfg():match('button_y=(%-?%d+)'))
        from = #W.sent + 1
        W.dragOn, W.dragDelta = half, { 40, 15 }; W.frame(); W.dragDelta = { 90, 25 }; W.frame()
        W.dragOn = nil; W.clicks[half] = true; W.frame(); W.frame(1.2)   -- (the mouse is let go over the half: ImGui reports a click)
        local x1 = tonumber(W.cfg():match('button_x=(%-?%d+)')); local y1 = tonumber(W.cfg():match('button_y=(%-?%d+)'))
        check(x1 == x0 + 90 and y1 == y0 + 25 and W.said('/gambits', from) == 0 and W.wins['Squads - XI: Forever Offline###sm_menu'] == nil,
              string.format('dragging the %s half by 90, 25: the control moves there (%s, %s -> %s, %s), no window opens, nothing is sent', half:match('^%a+'), tostring(x0), tostring(y0), tostring(x1), tostring(y1)))
    end
    from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    check(W.said('/gambits show', from) == 1, 'a plain click right after a drag works again')
    W.close()
end
do
    -- only in the world: login status, zoning, logout; repeated
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.login, W.who = 0, nil
    W.frame()
    check(W.wins['##servermenu_button'] == nil and not W.button('Squads##sm_open') and W.begins == W.ends, 'the title screen (not logged in): no launcher window at all, so nothing to click')
    W.login = 1; W.frame()
    check(W.wins['##servermenu_button'] == nil, 'character selection (login status 1): still hidden')
    W.login, W.who, W.zoning = 2, { 'Testcharone', 1 }, 1
    W.frame()
    check(W.wins['##servermenu_button'] == nil, 'logged in, the first zone still loading: hidden')
    for round = 1, 3 do
        W.zoning = 0; W.frame()
        local shown = W.wins['##servermenu_button'] == 1 and W.button('Squads##sm_open') and W.button('Gambits##sm_gsq')
        W.zoning = 1; W.frame()
        local hidden = W.wins['##servermenu_button'] == nil
        check(shown and hidden, 'round ' .. round .. ': in the world it is there; while the next zone loads it is hidden')
    end
    W.zoning = 0; W.frame()
    local x = W.cfg():match('button_x=(%-?%d+)')
    W.login, W.who = 0, nil; W.frame()
    check(W.wins['##servermenu_button'] == nil, 'logged out: hidden again')
    W.login, W.who = 2, { 'Other', 2 }; W.frame()
    check(W.wins['##servermenu_button'] == 1 and W.cfg():match('button_x=(%-?%d+)') == x, 'another character in the world: back, at the saved place')
    W.command('/menu button'); W.frame()
    check(W.wins['##servermenu_button'] == 1, '/menu button (un-hide) does not change that')
    W.login = 0; W.who = nil
    check(W.command('/menu') == true, 'while it is hidden the /menu command still answers (the launcher is what is hidden, not the add-on)')
    W.close()
end

section('13d. (1.31) the launcher has the character\'s theme in its first frame in the world')
do
    local function face(name) for _, item in ipairs(Ux.menu(name).button) do if item[1] == 'ImGuiCol_Button' then return item[2] end end end
    local function shownIn(W) return W.winColors['##servermenu_button'] and W.winColors['##servermenu_button'].WindowBg end
    -- the add-on is loaded at the title screen with its own setting (Squad); the character chose Classic earlier
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n', who = false })
    W.login, W.who = 0, nil
    local idOne, idTwo = Ux.identity('Testcharone', 1), Ux.identity('Other', 2)
    check(Ux.write_pref(W.dir .. '/', idOne, 'classic', mkdir) == true and Ux.write_pref(W.dir .. '/', idTwo, 'crimson', mkdir) == true, 'two characters with a saved theme: Classic and Crimson (the menu\'s own setting is Squad)')
    for _ = 1, 3 do W.frame(0.4) end
    check(W.wins['##servermenu_button'] == nil, 'title screen: no launcher')
    W.login, W.who, W.zoning = 2, { 'Testcharone', 1 }, 1
    W.frame(0.2)
    W.zoning = 0
    W.winColors = {}
    W.frame(0.016)   -- (the very next frame: far less than the 5 seconds between two looks at the theme)
    check(W.wins['##servermenu_button'] == 1 and same(shownIn(W), face('classic')) and not same(face('classic'), face('squad')),
          'first login: the FIRST frame of the launcher is in the character\'s Classic, not in the menu\'s own Squad')
    -- zoning: the same theme in the first frame after it, each time
    local kept = true
    for _ = 1, 3 do
        W.zoning = 1; W.frame(0.5); W.zoning = 0; W.winColors = {}; W.frame(0.016)
        kept = kept and same(shownIn(W), face('classic'))
    end
    check(kept, 'zoning three times: Classic in the first frame after each')
    -- another character
    W.login, W.who = 0, nil; W.frame(0.3); W.frame(0.3)
    W.login, W.who = 2, { 'Other', 2 }; W.winColors = {}; W.frame(0.016)
    check(same(shownIn(W), face('crimson')), 'character switch: the first frame for the other character is in ITS Crimson, never in the previous one\'s Classic')
    -- a character without a saved theme: the menu's own setting, as before
    W.login, W.who = 0, nil; W.frame(0.3)
    W.login, W.who = 2, { 'Nopref', 3 }; W.winColors = {}; W.frame(0.016)
    check(same(shownIn(W), face('squad')), 'a character without a saved theme: the menu\'s own setting (Squad here), in the first frame')
    W.close()
    -- a new installation (no settings file), no saved theme: Crimson
    local N = world({})
    N.frame(0.016)
    check(same(shownIn(N), face('crimson')), 'a new installation, no saved theme: Crimson in the first frame')
    N.close()
    -- the add-on reloaded while in the world: the character's theme at once
    local R = world({ cfg = 'theme=squad\nbutton_wide=true\n', prefs = { { Ux.identity('Testcharone', 1), 'classic' } } })
    R.frame(0.016)
    check(same(shownIn(R), face('classic')), 'add-on reload in the world: the character\'s theme in the first frame')
    R.close()
end

local MENU = 'Squads - XI: Forever Offline###sm_menu'
local function colOf(list, id) for _, item in ipairs(list) do if item[1] == id then return item[2] end end end
local function near(a, b) return type(a) == 'number' and type(b) == 'number' and math.abs(a - b) < 1e-6 end

section('13e. (1.32) opacity: the menu value reaches the window, the cards and the panels once each; the button value only the launcher')
for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
    local m = Ux.menu(name)
    local base, text = colOf(m.window, 'ImGuiCol_ChildBg'), colOf(m.window, 'ImGuiCol_Text')
    for _, menuOp in ipairs({ 10, 50, 100 }) do
        for _, buttonOp in ipairs({ 10, 50, 100 }) do
            local W = world({ cfg = string.format('theme=%s\nbutton_wide=true\nmenu_opacity=%d\nbutton_opacity=%d\n', name, menuOp, buttonOp) })
            W.command('/menu squad'); feed(W); W.frame(); W.frame()
            local where = string.format('%s, menu %d %%, button %d %%', name, menuOp, buttonOp)
            local card, list = W.childBg['##sm_mate1'], W.childBg['##sm_squadlist']
            local winOk = (menuOp == 100 and W.bgAlpha[MENU] == nil) or near(W.bgAlpha[MENU], menuOp / 100)
            check(winOk and type(card) == 'table' and card[1] == base[1] and card[2] == base[2] and card[3] == base[3] and near(card[4], base[4] * menuOp / 100),
                  where .. ': the window background and a card both follow the menu value (the card: the theme\'s own colour, its alpha times the value)')
            check(type(list) == 'table' and list[4] == 0, where .. ': the list the cards scroll in has no background of its own (no second layer under the cards)')
            check(near(W.winAlpha['##servermenu_button'], buttonOp / 100), where .. ': the launcher follows the button value, whatever the menu value is')
            check(same(W.winColors[MENU].Text, text) and text[4] == 1 and W.colors == 0 and W.vars == 0,
                  where .. ': the text keeps its full colour; everything pushed is popped')
            W.close()
        end
    end
end
do
    -- changed while the menu is open: the next frame has it; the other value is untouched
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\nmenu_opacity=100\nbutton_opacity=100\n' })
    local base = colOf(Ux.menu('crimson').window, 'ImGuiCol_ChildBg')
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    W.command('/menu opacity menu 25'); W.frame()
    check(near(W.bgAlpha[MENU], 0.25) and near(W.childBg['##sm_mate1'][4], base[4] * 0.25) and near(W.winAlpha['##servermenu_button'], 1),
          'menu opacity 100 -> 25: window and cards at the next frame; the launcher stays at 100')
    W.command('/menu opacity 50'); W.frame()
    check(near(W.winAlpha['##servermenu_button'], 0.5) and near(W.bgAlpha[MENU], 0.25) and near(W.childBg['##sm_mate1'][4], base[4] * 0.25),
          'button opacity 100 -> 50: the launcher at the next frame; window and cards stay at 25')
    -- a bordered panel inside the menu (Advanced) follows too, and the Profile window is not the menu's
    W.clicks['##advanced'] = true; W.frame(); W.frame()
    local adv = W.childBg['##sm_advanced']
    check(adv == nil or near(adv[4], base[4] * 0.25), 'the Advanced panel, when shown, has the same background as a card')
    W.close()
end

section('13f. (1.32) a theme picked in either add-on is in the menu at its next frame')
do
    local function bg(name) return colOf(Ux.menu(name).window, 'ImGuiCol_WindowBg') end
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    local pref = W.dir .. '/config/addons/xiforever/Testcharone_1/ui.cfg'
    W.command('/menu squad'); feed(W); W.frame()
    -- picked here: Gambits is told
    local from = #W.sent + 1
    W.command('/menu theme crimson'); W.frame(0.016)
    check(W.said('/xifotheme', from) == 1 and slurp(pref) == 'theme=crimson\n' and same(W.winColors[MENU].WindowBg, bg('crimson')),
          'picked in the menu: saved for the character, in use at once, and one /xifotheme line tells Gambits')
    -- picked in Gambits: its line arrives; the very next frame has the theme (no wait for the next look)
    put(pref, 'theme=classic\n')
    W.frame(0.016)
    local before = same(W.winColors[MENU].WindowBg, bg('crimson'))
    local stopped = W.command('/xifotheme')
    W.frame(0.016)
    check(before and stopped == true and same(W.winColors[MENU].WindowBg, bg('classic')),
          'Gambits picked Classic and said so: the line is stopped (never sent to the game) and the next frame of the open menu is Classic')
    -- the line was stopped by Gambits first: still answered
    put(pref, 'theme=squad\n')
    local e = { command = '/xifotheme', blocked = true }
    W.handlers.command(e); W.frame(0.016)
    check(e.blocked == true and same(W.winColors[MENU].WindowBg, bg('squad')), 'the line already stopped by the other add-on is answered all the same')
    -- no file is read in a frame without the line: the old pace is kept
    put(pref, 'theme=crimson\n')
    W.frame(0.016); W.frame(0.016)
    check(same(W.winColors[MENU].WindowBg, bg('squad')), 'without the line nothing is read in every frame (the look once a second is what it was)')
    W.frame(1.2)
    check(same(W.winColors[MENU].WindowBg, bg('crimson')), 'and that look still follows a change nobody announced')
    -- the launcher follows the line too, with the menu closed
    W.clicks['Squads##sm_open'] = true; W.frame(); W.frame()
    put(pref, 'theme=classic\n'); W.command('/xifotheme'); W.winColors = {}; W.frame(0.016)
    check(W.winColors[MENU] == nil and same(W.winColors['##servermenu_button'].WindowBg, colOf(Ux.menu('classic').button, 'ImGuiCol_Button')),
          'menu closed: the launcher has the theme at the next frame after the line')
    -- a menu opened after a change nobody announced: its first frame has the theme
    put(pref, 'theme=crimson\n')
    W.winColors = {}
    W.command('/menu squad'); W.frame(0.016)
    check(W.winColors[MENU] ~= nil and same(W.winColors[MENU].WindowBg, bg('crimson')), 'a menu opened after the change: the new theme in its first frame')
    W.close()
    -- the title screen: no character, so nothing shared and no line
    local T = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    T.login, T.who = 0, nil
    local n = #T.sent + 1
    T.command('/menu theme classic'); T.frame()
    check(T.said('/xifotheme', n) == 0 and has(T.cfg(), 'theme=classic'), 'at the title screen a pick is the menu\'s own setting: nothing shared, no line')
    T.close()
    -- a new installation: Crimson, as before
    local N = world({})
    N.command('/menu squad'); feed(N); N.frame()
    check(same(N.winColors[MENU].WindowBg, bg('crimson')), 'a new installation without a saved theme: Crimson')
    N.close()
end

-- ================================================================= 14. (1.33) the camp's state, the pull settings, the camp bar
section('14. (1.33) Camp: state word, Next pull at, Healer MP, Move keeps the camp, the compact camp bar follows the server')
do
    local function feedCamp(W, st, caps)
        -- the usual answer, with the camp state line after the camp line (squad.lua SQUAD_CAMPX.line) and the camp capability
        feed(W, { cap = false })
        W.line('squadpanel:camp|1|2|0|3'); W.line('squadpanel:campst|' .. st)
        W.line('squadpanel:cap|' .. (caps or 'reapply1,campmove')); W.line('squadpanel:end')
    end
    local W = world()
    W.command('/menu squad'); feedCamp(W, '1|0|fighting|3|40|0'); W.frame(); W.frame(1.2)
    check(W.text('Fighting, 3 pulls') ~= nil, 'the Camp row says what the camp is doing: "Fighting, 3 pulls"')
    check(W.combos['##camppullat'] == '40%' and W.combos['##camphealermp'] == 'Default', 'Next pull at 40%, Healer MP Default')
    check(W.button('Camp bar') ~= nil, 'the Camp bar switch is offered')

    -- the settings send the commands the server knows
    local n = #W.sent + 1
    W.openCombo, W.pick = '##camppullat', '60%'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('!squad camp pullat 60', n) == 1, 'picking 60% sends !squad camp pullat 60')
    n = #W.sent + 1
    W.openCombo, W.pick = '##camppullat', 'Off'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('!squad camp pullat off', n) == 1, 'Off sends pullat off')
    n = #W.sent + 1
    W.openCombo, W.pick = '##camphealermp', '50%'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('!squad camp healermp 50', n) == 1, 'Healer MP 50% sends healermp 50')

    -- Move camp here: "camp move" on a server that can (cap campmove), the old "camp" otherwise
    n = #W.sent + 1
    W.click('Move camp here##campset')
    check(W.said('!squad camp move', n) == 1, 'Move camp here keeps the camp (camp move)')

    -- the camp bar: switched on, drawn on its own, follows a pushed change without a refresh
    n = #W.sent + 1
    W.click('Camp bar##campbar')
    check(has(W.cfg(), 'camp_compact=true'), 'the switch is kept in the settings')
    W.command('/menu'); W.frame() -- (the menu closed: the bar stays)
    check((W.wins['Camp###sm_campbar'] or 0) > 0, 'the camp bar is drawn with the menu closed')
    W.line('squadpanel:campst|1|1|paused|3|40|0'); W.frame()
    check(W.text('Paused') ~= nil and W.button('Resume') ~= nil, 'a pushed change (paused) shows at once: "Paused", Resume')
    n = #W.sent + 1
    W.click('Resume##barpause')
    check(W.said('!squad camp resume', n) == 1, 'Resume on the bar sends camp resume')
    W.line('squadpanel:campst|1|0|pulling|4|40|0'); W.frame()
    check(W.text('Pulling') ~= nil and W.button('Pause') ~= nil, 'the server\'s own pull shows as "Pulling"')
    n = #W.sent + 1
    W.click('Camp off##baroff')
    check(W.said('!squad camp off', n) == 1, 'Camp off on the bar')
    W.line('squadpanel:campst|0|0|off|4|40|0'); W.frame()
    check(W.button('Set camp here##barset') ~= nil, 'no camp: the bar offers Set camp here')
    check(W.begins == W.ends and W.colors == 0, 'every window ends and every colour is popped (' .. W.begins .. '/' .. W.ends .. ', ' .. W.colors .. ')')
    W.close()

    -- an older server: no campst, no settings, no bar; Move camp here is the old "camp"
    local O = world()
    O.command('/menu squad'); feed(O); O.frame(); O.frame(1.2)
    check(O.combos['##camppullat'] == nil and O.button('Camp bar') == nil, 'an older server: no pull settings and no camp bar switch')
    local m = #O.sent + 1
    O.click('Move camp here##campset')
    check(O.said('!squad camp', m) == 1 and O.said('camp move', m) == 0, 'an older server: Move camp here sends the old !squad camp')
    O.close()
end

-- ================================================================= 14b. (1.34) font, launcher toggle, shortcut option, Camp layout
section('14b. (1.34) text at the Size like Gambits; Gambits half opens AND closes; Show Gambits shortcut; Camp row wraps in place')
do
    -- item 4: the font is pushed at the scaled size (as the Gambits window does), not stretched with SetWindowFontScale
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\nscale=1.2\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame(1.2)
    local all12 = #W.fontPushes >= 2
    for _, size in ipairs(W.fontPushes) do all12 = all12 and math.abs(size - 13 * 1.2) < 1e-6 end
    check(all12 and #W.fontScales == 0, '120 %: every window\'s text is the game\'s font pushed at 15.6 px (13 x 1.2), no SetWindowFontScale (' .. #W.fontPushes .. ' pushes, ' .. #W.fontScales .. ' scales)')
    check(W.fontPops == #W.fontPushes and W.begins == W.ends, 'every pushed font is popped, in every window')
    check(W.sizes['Squads##sm_open'][1] == 65, 'sizes are what they were at 120 % (the Squads half 65 px = 54 x 1.2)')
    W.close()
    local W1 = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    W1.command('/menu squad'); feed(W1); W1.frame(); W1.frame(1.2)
    local ones = true
    for _, v in ipairs(W1.fontScales) do ones = ones and v == 1 end
    check(#W1.fontPushes == 0 and ones, '100 %: no font is pushed (SetWindowFontScale(1), as before, changes nothing)')
    W1.close()
end
do
    -- item 2: the Gambits half opens and closes the editor, lit by the editor's own word (gambits.open + "/xifogambits")
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    local m = Ux.menu('squad')
    local dir = W.dir .. '/config/addons/xiforever/Testcharone_1'
    mkdir(dir); put(dir .. '/gambits.loaded', Ux.presence_text('0.3.9'))
    feed(W); W.frame(2.1); W.frame()
    check(not same(W.look['Gambits##sm_gsq'], m.c.sel), 'the editor is closed: the Gambits half is not lit')
    local from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    check(W.sent[#W.sent] == '/gambits show' and W.said('/gambits', from) == 1 and same(W.look['Gambits##sm_gsq'], m.c.sel), 'a click opens it ("/gambits show") and the half is lit at once')
    put(dir .. '/gambits.open', Ux.presence_text('0.3.9'))
    check(W.command('/xifogambits') == true, 'the editor\'s line "/xifogambits" is stopped (never sent to the game)')
    W.frame(1.5); W.frame(1.5)
    check(same(W.look['Gambits##sm_gsq'], m.c.sel), 'Gambits says its window is shown: still lit, seconds later')
    from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    check(W.sent[#W.sent] == '/gambits hide' and W.said('/gambits', from) == 1, 'a second click closes it ("/gambits hide")')
    os.remove(dir .. '/gambits.open'); W.command('/xifogambits'); W.frame(1.5); W.frame()
    check(not same(W.look['Gambits##sm_gsq'], m.c.sel), 'closed: no longer lit')
    -- opened another way (a mate's Gambits button, /gambits): the editor's word lights the half; a click then closes it
    put(dir .. '/gambits.open', Ux.presence_text('0.3.9')); W.command('/xifogambits'); W.frame()
    check(same(W.look['Gambits##sm_gsq'], m.c.sel), 'opened elsewhere: the half follows at the next frame')
    from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    check(W.said('/gambits hide', from) == 1, 'and a click closes it')
    -- closed with its own X: the editor removes the file and says so
    os.remove(dir .. '/gambits.open'); W.command('/xifogambits'); W.frame(1.5); W.frame()
    from = #W.sent + 1
    W.clicks['Gambits##sm_gsq'] = true; W.frame(); W.frame()
    check(W.said('/gambits show', from) == 1, 'closed with its own X: the next click opens it again')
    -- a file another game process left (a crash) is not the editor's word
    os.remove(dir .. '/gambits.open'); W.frame(1.5)
    put(dir .. '/gambits.open', 'Gambits 0.3.9\npid=' .. string.format('%d', (Ux.process_id() or 1) + 1) .. '\n'); W.command('/xifogambits'); W.frame(1.5); W.frame()
    check(Ux.process_id() == nil or not same(W.look['Gambits##sm_gsq'], m.c.sel), 'a gambits.open left by another game process does not light the half')
    W.close()
end
do
    -- item 5: Show Gambits shortcut off: a Squads-only button at the same place; /gambits and the cards' buttons stay
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\nbutton_x=300\nbutton_y=180\nlauncher_gambits=false\n' })
    mkdir(W.dir .. '/config/addons/xiforever/Testcharone_1'); put(W.dir .. '/config/addons/xiforever/Testcharone_1/gambits.loaded', Ux.presence_text('0.3.9'))
    feed(W); W.frame(2.1); W.frame()
    local divider = false
    for _, a in ipairs(W.at) do divider = divider or (a.label == 'dummy' and a.w == 1) end
    check(W.button('Squads##sm_open') and not W.button('Gambits##sm_gsq') and not divider, 'off: the launcher is the Squads half alone (no divider, no Gambits half)')
    check(W.winPos['##servermenu_button'] and W.winPos['##servermenu_button'][1] == 300 and W.winPos['##servermenu_button'][2] == 180, 'at the saved place (300, 180)')
    W.clicks['Squads##sm_open'] = true; W.frame(); feed(W); W.frame(2.1); W.frame()
    check(W.button('Gambits##gsq4') ~= nil, 'the Gambits buttons on the mates\' cards stay')
    -- the Options row turns it on again (and writes the setting as the menu's other settings are written)
    local im = package.loaded['imgui']
    im.Checkbox = function(label, t) if W.clicks[label] then W.clicks[label] = nil; t[1] = not t[1]; return true end return false end
    W.clicks['Options##options'] = true; W.frame(); W.frame()
    W.clicks['Show Gambits shortcut##smgsqshortcut'] = true; W.frame(); W.frame(3)
    check(W.button('Gambits##sm_gsq') ~= nil and has(W.cfg(), 'launcher_gambits=true'), 'Options > Show Gambits shortcut: the Gambits half is back, and saved')
    W.close()
    local D = world({ cfg = 'theme=squad\nbutton_wide=true\n' })
    D.frame()
    check(D.button('Gambits##sm_gsq') ~= nil, 'the default (no setting): the combined Squads | Gambits launcher')
    D.close()
end
do
    -- item 7: an active Camp at a narrow width and at 120 %: every control inside the window, the kinds wrap under Anything
    for _, case in ipairs({ { w = 620, cfg = '' }, { w = 470, cfg = '' }, { w = 600, cfg = 'scale=1.2\n' } }) do
        local W = world({ cfg = 'theme=squad\nbutton_wide=true\n' .. case.cfg })
        W.width = case.w
        W.command('/menu squad'); feed(W, { cap = false })
        W.line('squadpanel:camp|1|2|1|0'); W.line('squadpanel:campst|1|1|paused|0|0|0'); W.line('squadpanel:campwant|-')
        for _, k in ipairs({ 'Wandering_Sapling', 'Goblin_Ambusher', 'Goblin_Tinkerer', 'Crane_Fly', 'Hill_Lizard', 'Forest_Hare' }) do W.line('squadpanel:campmob|' .. k .. '|15|22|2|1') end
        W.line('squadpanel:cap|reapply1,campmove'); W.line('squadpanel:end')
        W.frame(); W.frame(1.2)
        local tag = case.w .. ' px' .. (case.cfg ~= '' and ' at 120 %' or '')
        local campOver = {}
        for _, o in ipairs(W.over) do if o:find('camp') or o:find('Paused') or o:find('Pull') or o:find('Healer') or o:find('Next pull') then campOver[#campOver + 1] = o end end
        check(#campOver == 0, tag .. ': every Camp control is inside the window (' .. table.concat(campOver, '; ') .. ')')
        check(W.text('Paused, 0 pulls') ~= nil, tag .. ': the state is shown whole ("Paused, 0 pulls")')
        local anyX, kinds, aligned = nil, 0, true
        for _, a in ipairs(W.at) do
            if a.label == 'Anything##campany' then anyX = a.x end
            if anyX and a.label:find('##campkind', 1, true) then
                kinds = kinds + 1
                aligned = aligned and a.x >= anyX - 0.5
            end
        end
        check(anyX ~= nil and kinds == 6 and aligned, tag .. ': all 6 kinds are drawn, none starts left of "Anything" (wrapped ones line up under it)')
        local wrappedUnder = false
        for _, a in ipairs(W.at) do if a.label:find('##campkind', 1, true) and math.abs(a.x - anyX) < 0.5 then wrappedUnder = true end end
        check((case.w > 600 and case.cfg == '') or wrappedUnder, tag .. ': at this width some kinds wrap, and they start exactly under "Anything"')
        W.close()
    end
end

do
    -- (1.34) the Camp bar switch is read back after a reload (1.33 wrote camp_compact but did not read it)
    local W = world({ cfg = 'theme=squad\nbutton_wide=true\ncamp_compact=true\n' })
    feed(W, { cap = false })
    W.line('squadpanel:camp|1|2|0|1'); W.line('squadpanel:campst|1|0|idle|1|0|0'); W.line('squadpanel:end')
    W.frame(); W.frame()
    check((W.wins['Camp###sm_campbar'] or 0) > 0, 'a saved camp_compact=true shows the Camp bar after a reload')
    W.close()
end
-- ================================================================= 14c. (1.35) Position: where a mate stands in a fight
section('14c. (1.35) Position in a card\'s Settings: offered with cap matepos, sent at once, shown folded when not Normal')
do
    local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad'); feed(W); W.frame(); W.frame()
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.combos['##range1'] ~= nil and W.combos['##position1'] == nil, 'an older server (no matepos in cap): no Position row, Range as before')
    W.close()

    W = world({ cfg = 'theme=crimson\nbutton_wide=true\n' })
    W.command('/menu squad')
    feed(W, { cap = 'reapply1,campmove,matepos', extra = { 'squadpanel:pos|1|0', 'squadpanel:pos|2|2', 'squadpanel:pos|3|1' } })
    W.frame(); W.frame()
    check(W.combos['##position1'] == nil and #xs(W, 'TA partner') == 1 and #xs(W, 'Behind enemy') == 1 and #xs(W, 'Normal') == 0,
          'folded: a mate set to TA partner or Behind enemy says so in its muted words; Normal is not mentioned')
    W.clicks['##more1'] = true; W.frame(); W.frame()
    check(W.combos['##position1'] == 'Normal' and W.combos['##range1'] ~= nil, 'Settings unfolded: Position "Normal" under Range')
    check(#W.over == 0, 'the Position row fits the card (nothing beyond the edge)' .. (W.over[1] and (' (' .. W.over[1] .. ')') or ''))
    do
        local _, xLabel, wLabel = atOf(W, 'Position', true)
        local _, xPos = atOf(W, '##position1', true)
        local _, xRole = atOf(W, '##role1', true)
        local _, xRange = atOf(W, '##range1', true)
        check(xLabel and xPos and xLabel + wLabel < xPos, '"Position" ends before its list starts (1.35 first build: "Positio" was cut)'
            .. string.format(' (label %s+%s, list at %s)', tostring(xLabel), tostring(wLabel), tostring(xPos)))
        check(xPos == xRole and xPos == xRange, 'Role, Range and Position lists in one column')
    end
    local from = #W.sent + 1
    W.openCombo, W.pick = '##position1', 'Behind'; W.frame(); W.openCombo, W.pick = nil, nil
    W.frame()
    check(W.combos['##position1'] == 'Behind enemy', 'the choice shows at once')
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad position 1 behind', from) == 1, 'it sends !squad position 1 behind, once')
    check(W.said('/say !squad panel', from) >= 1, 'and asks for the panel again (the server\'s pos| line confirms it)')
    from = #W.sent + 1
    W.openCombo, W.pick = '##position1', 'TA'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('/say !squad position 1 ta', from) == 1, 'TA partner sends !squad position 1 ta')
    from = #W.sent + 1
    W.openCombo, W.pick = '##position1', 'TA'; W.frame(); W.openCombo, W.pick = nil, nil
    for _ = 1, 3 do W.frame(2.5) end
    check(W.said('!squad position', from) == 0, 'picking what is already chosen sends nothing')
    W.close()
end

-- ================================================================= 15. (1.36) the Ventures button
-- The add-on's side here is a stand-in: two small files written by hand, and its line "/xifoventure". The real add-on
-- with this menu, each in its own Lua state: dev/ventures/test_venture_button.py.
section('15. (1.36) Squad tab > Ventures: only with the add-on in Ashita; loads it, shows its window, shuts it; lit while shown')
do
    local BTN = 'Ventures##ventures'
    local m = Ux.menu('crimson')
    local function plant(W) mkdir(W.dir .. '/addons/venture'); put(W.dir .. '/addons/venture/venture.lua', '-- the venture add-on\n') end
    local function folder(W) local d = W.dir .. '/config/addons/xiforever/Testcharone_1'; mkdir(d); return d end
    local function exists(path) local f = io.open(path, 'r'); if f then f:close() end return f ~= nil end
    -- what the add-on does: its file is there or gone, and it says so
    local function mark(W, name, on, quiet, pid)
        local path = folder(W) .. '/' .. name
        if on then
            pid = pid or Ux.process_id()
            put(path, 'Ventures 1.1\n' .. (pid and ('pid=' .. string.format('%d', pid) .. '\n') or ''))
        else
            os.remove(path)
        end
        if not quiet then W.command('/xifoventure') end
    end
    local function start(o)
        local W = world({ cfg = 'theme=crimson\nbutton_wide=true\n', who = o and o.who })
        if not (o and o.bare) then plant(W) end
        W.command('/menu squad'); feed(W); W.frame(); W.frame()
        return W
    end
    local function press(W) W.clicks[BTN] = true; W.frame() end
    local function lit(W) return same(W.look[BTN], m.c.sel) end
    local function busy(W) return same(W.look[BTN], m.c.busy) end

    -- drawn only when the add-on is there
    local W = start({ bare = true })
    check(not W.button(BTN) and order(W, 'callall', 'dismiss', 'refresh', 'sqattack'), 'no venture add-on in Ashita\'s addons folder: no Ventures button, the row as it was')
    plant(W)
    for _ = 1, 3 do W.frame(4) end
    check(W.button(BTN) ~= nil, 'the add-on arrives (the launcher copied it): the button is there within ten seconds or so')
    W.close()

    W = start()
    do
        local ok, missing = order(W, 'callall', 'dismiss', 'refresh', 'ventures', 'sqattack')
        check(ok, 'the Squad row: Call all, Dismiss all, Refresh, Ventures' .. (ok and '' or (' (missing ' .. tostring(missing) .. ')')))
        local iR, xR, wR = atOf(W, 'Refresh##refresh', true)
        local iV, xV, wV = atOf(W, BTN, true)
        local iN, xN = atOf(W, '6 mates', true)
        check(iV == iR + 1 and xV == xR + wR + 6 and wV == 76 and iN == iV + 1 and xN == xV + wV + 12,
              'right after Refresh on the same line, 76 px wide, the mate count after it')
        check(#W.over == 0, 'nothing in the menu lands beyond the edge' .. (W.over[1] and (' (' .. W.over[1] .. ')') or ''))
        check(same(W.look[BTN], W.look['Refresh##refresh']) and not lit(W) and not busy(W), 'not loaded: a plain button like its neighbours')
        W.hover = true; W.frame(); W.hover = false
        local tip = false
        for _, t in ipairs(W.tips) do tip = tip or has(t, 'Send squad mates off to level') end
        check(tip and #W.setTooltip == 0, 'its tooltip says what Ventures is')
    end

    -- not loaded: the click loads the add-on; "/venture show" only once the add-on said it is there
    local from = #W.sent + 1
    press(W)
    check(W.sent[#W.sent] == '/addon load venture' and W.said('/addon load venture', from) == 1 and W.said('/venture', from) == 0,
          'a click when it is not loaded: "/addon load venture", and no "/venture" line yet (nobody would answer it)')
    W.frame()
    check(busy(W), 'the button waits (busy) while the add-on loads')
    press(W); press(W)
    check(W.said('/addon load venture', from) == 1 and W.said('/venture', from) == 0, 'clicks while it waits do nothing')
    for _ = 1, 10 do W.frame(0.3) end
    check(W.said('/venture', from) == 0 and busy(W), 'three seconds later, still no add-on: still waiting, still nothing sent')
    mark(W, 'venture.loaded', true)
    W.frame()
    check(W.sent[#W.sent] == '/venture show' and W.said('/venture show', from) == 1, 'the add-on says it is loaded: "/venture show" at the next frame')
    W.frame(); W.frame()
    check(busy(W) and W.said('/venture show', from) == 1, 'until its window is shown the button still waits; the line is not sent twice')
    mark(W, 'venture.open', true)
    W.frame()
    check(lit(W) and W.said('/addon load venture', from) == 1 and W.said('/venture', from) == 1, 'the window is shown: the button is lit; one load and one show in all')
    W.hover = true; W.frame(); W.hover = false
    do
        local tip = false
        for _, t in ipairs(W.tips) do tip = tip or has(t, 'Shut the Ventures window') end
        check(tip, 'lit: the tooltip says a click shuts the window')
    end
    for _ = 1, 4 do W.frame(1.5) end
    check(lit(W) and W.said('/venture', from) == 1, 'seconds later: still lit, nothing more sent')

    -- shown: the click shuts the window
    from = #W.sent + 1
    press(W)
    check(W.sent[#W.sent] == '/venture hide' and W.said('/venture', from) == 1, 'a click while the window is shown: "/venture hide"')
    mark(W, 'venture.open', false)
    W.frame(); W.frame()
    check(not lit(W) and not busy(W), 'the add-on says its window is shut: no longer lit')

    -- loaded, window shut: the click only shows the window
    from = #W.sent + 1
    press(W)
    check(W.sent[#W.sent] == '/venture show' and W.said('/addon load', from) == 0, 'loaded already: a click sends "/venture show" alone')
    -- ... and the add-on's files are looked at without its line too (four times a second while a click waits)
    mark(W, 'venture.open', true, true)
    W.frame(0.3); W.frame()
    check(lit(W), 'an answer without the line "/xifoventure" is seen within a third of a second')

    -- the window shut or shown some other way (/venture, its own X): the button follows
    mark(W, 'venture.open', false); W.frame()
    check(not lit(W), 'shut with its own X (the add-on says so): not lit at the next frame')
    mark(W, 'venture.open', true); W.frame()
    check(lit(W), 'opened with /venture: lit at the next frame')
    mark(W, 'venture.open', false, true); W.frame(1.2); W.frame()
    check(not lit(W), 'and without the line: within about a second')
    check(W.command('/xifoventure') == true, 'the add-on\'s line "/xifoventure" is stopped here too (never sent to the game)')

    -- the add-on unloaded (/addon unload venture removes both files): the next click loads it again
    mark(W, 'venture.loaded', false, true); W.frame(2.2); W.frame()
    from = #W.sent + 1
    press(W)
    check(W.sent[#W.sent] == '/addon load venture' and W.said('/venture', from) == 0, 'unloaded in the meantime: the next click loads it again')
    W.close()

    -- an add-on that never loads (a broken file): said once, and the button can be pressed again
    W = start()
    from = #W.sent + 1
    press(W)
    for _ = 1, 45 do W.frame(0.2) end
    check(busy(W) and #W.prints == 1, 'nine seconds without the add-on: still waiting, nothing said')
    for _ = 1, 10 do W.frame(0.2) end
    local told = false
    for _, line in ipairs(W.prints) do told = told or has(line, 'the Ventures add-on did not load') end
    check(told and not busy(W) and not lit(W) and W.said('/addon load venture', from) == 1 and W.said('/venture', from) == 0,
          'after ten seconds: the chat log says it did not load (once), the button is a plain button again, and no "/venture" line was ever sent')
    press(W)
    check(W.said('/addon load venture', from) == 2, 'and a click tries again')
    W.close()

    -- a file a closed game left behind, with this game's process id: "/venture show" goes unanswered
    W = start()
    mark(W, 'venture.loaded', true, true); W.frame(2.2)
    from = #W.sent + 1
    press(W)
    check(W.sent[#W.sent] == '/venture show', 'a venture.loaded that looks like this game\'s: the click trusts it ("/venture show")')
    for _ = 1, 100 do W.frame(0.019) end
    check(W.said('/addon load', from) == 0 and busy(W), '1.9 seconds and a hundred frames without an answer: still waiting')
    for _ = 1, 25 do W.frame(0.019) end   -- (the files are looked at four times a second: by 2.4 s at the latest)
    check(W.said('/addon load venture', from) == 1 and not exists(folder(W) .. '/venture.loaded'),
          'two seconds (and thirty frames) without an answer: the file was not this game\'s. It is removed and the add-on is loaded for real')
    mark(W, 'venture.loaded', true); W.frame()
    mark(W, 'venture.open', true); W.frame()
    check(lit(W) and W.said('/venture show', from) == 2 and W.said('/addon load venture', from) == 1 and #W.prints == 1,
          'the add-on loads and shows its window: lit, with one load and nothing said')
    W.close()

    -- ... but a game that stood still (a zone loading, the window minimised) is not an unanswered line
    W = start()
    mark(W, 'venture.loaded', true, true); W.frame(2.2)
    from = #W.sent + 1
    press(W)
    W.frame(30); W.frame(30)
    check(W.said('/addon load', from) == 0 and exists(folder(W) .. '/venture.loaded') and busy(W),
          'a minute passes in two frames (the game stood still): nothing is removed and nothing loaded, the click still waits')
    mark(W, 'venture.open', true); W.frame()
    check(lit(W) and W.said('/venture', from) == 1, 'the add-on answers at its next frame: lit')
    W.close()

    -- the add-on is loaded for real and still does not show its window: said, not tried for ever
    W = start()
    from = #W.sent + 1
    press(W)
    mark(W, 'venture.loaded', true); W.frame()
    for _ = 1, 120 do W.frame(0.02) end
    told = false
    for _, line in ipairs(W.prints) do told = told or has(line, 'the Ventures window did not open') end
    check(told and not busy(W) and W.said('/addon load venture', from) == 1 and W.said('/venture show', from) == 1,
          'loaded by this click, yet no window after two seconds: the chat log says so, and nothing is sent again')
    W.close()

    -- "/venture hide" unanswered: the open file was left behind too
    W = start()
    mark(W, 'venture.loaded', true, true); mark(W, 'venture.open', true, true); W.frame(2.2); W.frame()
    check(lit(W), '(both files there: the button is lit)')
    from = #W.sent + 1
    press(W)
    check(W.sent[#W.sent] == '/venture hide', 'a click: "/venture hide"')
    for _ = 1, 120 do W.frame(0.02) end
    check(not lit(W) and not busy(W) and not exists(folder(W) .. '/venture.open') and not exists(folder(W) .. '/venture.loaded') and #W.prints == 1,
          'nobody answers for two seconds: both files are removed, the button is plain again, nothing is said')
    press(W)
    check(W.sent[#W.sent] == '/addon load venture', 'and the next click loads the add-on')
    W.close()

    -- a file another game process left (its id is not this game's) is not the add-on's word
    W = start()
    local other = (Ux.process_id() or 1) + 1
    mark(W, 'venture.loaded', true, true, other); mark(W, 'venture.open', true, true, other); W.frame(2.2); W.frame()
    check(Ux.process_id() == nil or not lit(W), 'files with another process\'s id: not lit')
    from = #W.sent + 1
    press(W)
    check(Ux.process_id() == nil or (W.sent[#W.sent] == '/addon load venture' and W.said('/venture', from) == 0), 'and a click loads the add-on, no "/venture" line')
    W.close()

    -- nobody logged in: there is no character's folder to look in
    W = start({ who = { '', 0 } })
    from = #W.sent + 1
    press(W)
    told = false
    for _, line in ipairs(W.prints) do told = told or has(line, 'log in with a character first') end
    check(told and W.said('/addon load', from) == 0 and W.said('/venture', from) == 0 and not busy(W), 'at the title screen: the click only says to log in first')
    W.close()

    -- it fits, at every width and size, in every theme
    local worst, where = 0, nil
    for _, name in ipairs({ 'classic', 'squad', 'crimson' }) do
        for _, width in ipairs({ 600, 620, 900 }) do
            for _, scale in ipairs({ 0.75, 1, 2 }) do
                local V = world({ cfg = 'theme=' .. name .. '\nbutton_wide=true\nscale=' .. scale .. '\n' })
                V.width, V.scale = width, scale
                plant(V)
                V.command('/menu squad'); feed(V); V.frame(); V.frame()
                if not V.button(BTN) then worst, where = worst + 1, 'no button at ' .. width end
                if #V.over > worst then worst, where = #V.over, string.format('%s, %d px at %d %%: %s', name, width, scale * 100, tostring(V.over[1])) end
                if V.colors ~= 0 or V.vars ~= 0 or V.begins ~= V.ends then worst, where = worst + 1, 'something pushed was not popped' end
                V.close()
            end
        end
    end
    check(worst == 0, 'with the Ventures button: no control beyond the edge at 600 / 620 / 900 px and 75 / 100 / 200 %, in every theme; what is pushed is popped'
        .. (where and (' (' .. where .. ')') or ''))
end

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
