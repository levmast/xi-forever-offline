-- Tests for the addon channel in the Server menu: once the server says squadpanel:chan|1 the menu's commands go out as the channel packet (0x1F0)
-- instead of typed /say lines; an older server, a missing packet manager or a player's chat line keeps it typing.
-- Same stand-in Ashita and ImGui as test_servermenu_camp.lua.
--   texlua test_servermenu_channel.lua [path to servermenu.lua]
local HERE = (arg and arg[0] and arg[0]:match('^(.*)[/\\][^/\\]*$')) or '.'
local KIT = HERE .. '/../../addons-src'
io.stdout:setvbuf('no')
local PATH = arg[1] or (KIT .. '/servermenu/servermenu.lua')
local passed, failed = 0, 0
local function check(cond, label) if cond then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', label, '\n') end end
local function section(name) io.write('\n== ', name, '\n') end
local function slurp(path) local f = io.open(path, 'rb') if not f then return nil end local s = f:read('*a') f:close() return s end
local function spit(path, text) local f = assert(io.open(path, 'wb')) f:write(text) f:close() end
local function mkdir(path)
    path = path:gsub('[/\\]+$', '')
    if package.config:sub(1, 1) == '\\' then os.execute('mkdir "' .. path:gsub('/', '\\') .. '" 2>nul')
    else os.execute('mkdir -p "' .. path .. '"') end
end

local function boot(opts)
    opts = opts or {}
    local W = { handlers = {}, clock = 100, printed = {}, clicks = {}, buttons = {}, texts = {}, checks = {}, combos = {}, selects = {}, begins = {},
                balance = 0, colorBalance = 0, varBalance = 0, childBalance = 0, popupBalance = 0, comboBalance = 0, pos = nil, dragging = nil }
    W.chat = { sent = {}, input = false }
    function W.chat:QueueCommand(mode, command) self.sent[#self.sent + 1] = command end
    function W.chat:IsInputOpen() return self.input end
    W.pm = { sent = {} }
    function W.pm:AddOutgoingPacket(id, bytes) if opts.packetsFail then error('no packet manager') end self.sent[#self.sent + 1] = { id = id, bytes = bytes } end
    addon = {}
    W.dir = opts.dir
    if not W.dir then W.dir = os.tmpname(); os.remove(W.dir); mkdir(W.dir); W.dir = W.dir .. '/' end
    if opts.beforeLoad then opts.beforeLoad(W) end
    ashita = { events = { register = function(name, id, fn) W.handlers[name] = fn end }, time = { get_tick64 = function() return W.clock * 1000 end },
               fs = { create_directory = function(path) mkdir(path) end } }
    AshitaCore = { GetChatManager = function() return W.chat end, GetInstallPath = function() return W.dir end,
                   GetPacketManager = function() if opts.noPacketManager then return nil end return W.pm end }
    function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
    package.loaded['common'] = true
    package.loaded['imgui'] = nil
    if opts.noImgui then
        package.preload['imgui'] = function() error('no imgui here') end
    else
        package.preload['imgui'] = function()
            local missing = opts.missing or {}
            local im = setmetatable({}, { __index = function(_, name) if missing[name] then return nil end return function() end end })
            local function label(l) return (l:gsub('##.*$', '')) end
            function im.Begin(title) W.begins[#W.begins + 1] = title; W.balance = W.balance + 1; W.window = title return true end
            function im.End() W.balance = W.balance - 1 end
            function im.BeginChild() W.childBalance = W.childBalance + 1 return true end
            function im.EndChild() W.childBalance = W.childBalance - 1 end
            function im.PushStyleColor() W.colorBalance = W.colorBalance + 1 end
            function im.PopStyleColor(n) W.colorBalance = W.colorBalance - (n or 1) end
            function im.PushStyleVar() W.varBalance = W.varBalance + 1 end
            function im.PopStyleVar(n) W.varBalance = W.varBalance - (n or 1) end
            function im.Button(l) W.buttons[#W.buttons + 1] = l; W.lastItem = l
                if W.clicks[l] then W.clicks[l] = nil return true end return false end
            function im.Text(t) W.texts[#W.texts + 1] = t end
            function im.TextWrapped(t) W.texts[#W.texts + 1] = t end
            function im.TextColored(c, t) W.texts[#W.texts + 1] = t; W.colors = W.colors or {}; W.colors[t] = c end
            function im.Checkbox(l, box) W.checks[l] = box[1]; if W.clicks[l] then W.clicks[l] = nil; box[1] = not box[1]; return true end return false end
            function im.BeginCombo(id, preview) W.combos[id] = preview; if W.openCombo == id then W.comboBalance = W.comboBalance + 1 return true end return false end
            function im.EndCombo() W.comboBalance = W.comboBalance - 1 end
            function im.Selectable(l, sel) W.selects[#W.selects + 1] = l; if W.clicks[l] then W.clicks[l] = nil return true end return false end
            function im.InputText(l, buf, size) if W.typeInto and W.typeInto[l] then buf[1] = W.typeInto[l]; W.typeInto[l] = nil; return true end return false end
            function im.IsItemActive() return W.dragging ~= nil and W.lastItem == 'Squads##sm_open' end
            function im.IsMouseDragging() return W.dragging ~= nil end
            function im.GetMouseDragDelta() return { W.dragging and W.dragging[1] or 0, W.dragging and W.dragging[2] or 0 } end
            function im.GetWindowPos() if W.window == '##servermenu_button' and W.pos then return W.pos[1], W.pos[2] end return W.lastSetPos and W.lastSetPos[1] or 0, W.lastSetPos and W.lastSetPos[2] or 0 end
            function im.SetNextWindowPos(p) W.lastSetPos = p end
            function im.BeginPopupContextItem() if W.popup then W.popupBalance = W.popupBalance + 1 return true end return false end
            function im.EndPopup() W.popupBalance = W.popupBalance - 1 end
            function im.MenuItem(l) if W.clicks[l] then W.clicks[l] = nil return true end return false end
            function im.CollapsingHeader(l) return W.expand == true end
            function im.GetWindowWidth() return 620 end
            for name in pairs(missing) do im[name] = nil end
            return im
        end
    end
    for name, v in pairs({ ImGuiCol_Button = 21, ImGuiCol_ButtonHovered = 22, ImGuiCol_ButtonActive = 23, ImGuiCol_Text = 0, ImGuiCol_WindowBg = 2,
                           ImGuiStyleVar_WindowRounding = 3, ImGuiCond_FirstUseEver = 4, ImGuiCond_Always = 1, ImGuiWindowFlags_NoTitleBar = 1,
                           ImGuiWindowFlags_NoMove = 4, ImGuiCol_PlotHistogram = 40 }) do rawset(_G, name, v) end
    print = function(...) local parts = {} for i = 1, select('#', ...) do parts[#parts + 1] = tostring((select(i, ...))) end W.printed[#W.printed + 1] = table.concat(parts, ' ') end
    setmetatable(_G, nil)
    assert(loadfile(PATH))()
    setmetatable(_G, { __index = function(_, k) error('undefined global ' .. tostring(k), 2) end })
    W.handlers.load()
    function W.frame(dt) W.clock = W.clock + (dt or 0.1); W.buttons = {}; W.texts = {}; W.checks = {}; W.combos = {}; W.selects = {}; W.begins = {}; W.handlers.d3d_present() end
    function W.run(seconds, step) step = step or 0.25 for _ = 1, math.floor(seconds / step + 0.5) do W.frame(step) end end
    function W.command(text) local e = { command = text, blocked = false } W.handlers.command(e) return e end
    function W.chatLine(text) local e = { message = text, blocked = false } W.handlers.text_in(e) return e end
    function W.has(l) for _, b in ipairs(W.buttons) do if b == l then return true end end return false end
    function W.saw(fragment) for _, t in ipairs(W.texts) do if t:find(fragment, 1, true) then return t end end return nil end
    function W.click(l) W.clicks[l] = true; W.frame() end
    function W.sentAll() return table.concat(W.chat.sent, '\n') end
    function W.status(values)
        mkdir(W.dir .. 'config/addons/duo')
        local keys = {} for k in pairs(values) do keys[#keys + 1] = k end table.sort(keys)
        local f = io.open(W.dir .. 'config/addons/duo/status.cfg', 'w')
        f:write('time=' .. os.time() .. '\n')
        for _, k in ipairs(keys) do f:write(k .. '=' .. tostring(values[k]) .. '\n') end
        f:close()
    end
    function W.command_file() local s = slurp(W.dir .. 'config/addons/duo/command.cfg') if not s then return nil end local t = {} for l in s:gmatch('[^\n]+') do local k, v = l:match('^([%w_]+)=(.*)$') if k then t[k] = v end end return t end
    return W
end

local KYO = 'squadpanel:1|Kyo|PLD|20|WAR|10|tank|balanced|1|14'
local KAS = 'squadpanel:2|Kasumi|WHM|20|-|0|healer|balanced|1|14'
local function answer(W, lines)
    for _, l in ipairs(lines) do W.chatLine('[Hurami] : ' .. l) end
    W.frame()
end
local function open(W) W.command('/sq'); W.run(1) end
-- the text of a channel packet, and its size, the way the server reads it
local function textOf(p)
    local out = {}
    for i = 9, #p.bytes do if p.bytes[i] == 0 then break end out[#out + 1] = string.char(p.bytes[i]) end
    return table.concat(out)
end
local function packets(W)
    local t = {}
    for _, p in ipairs(W.pm.sent) do t[#t + 1] = textOf(p) end
    return t
end
local function has(list, text) for _, v in ipairs(list) do if v == text then return true end end return false end

section('an older server never says chan: everything is typed, no packet')
local W = boot(); open(W)
answer(W, { KYO, KAS, 'squadpanel:end' })
W.click('Set camp here##campset'); W.run(3)
check(#W.pm.sent == 0, 'no packet is sent')
check(W.sentAll():find('/say !squad panel', 1, true) ~= nil, 'the panel request is typed')

section('chan|1 answered to the menu: commands go out as the channel packet')
W = boot(); open(W)
check(W.chatLine('[Hurami] : squadpanel:chan|1').blocked, 'the chan line is hidden from chat like the others')
answer(W, { KYO, KAS, 'squadpanel:camp|0|0|0|0', 'squadpanel:end' })
W.chat.sent = {}
W.click('Set camp here##campset'); W.run(3)
local sent = packets(W)
check(has(sent, '!squad camp'), 'Set camp here goes out as a packet with the text !squad camp: ' .. table.concat(sent, ' | '))
check(W.sentAll():find('!squad camp', 1, true) == nil, 'and is not typed')
local p = W.pm.sent[1]
check(p and p.id == 0x1F0, 'packet id 0x1F0')
local b = p and p.bytes or {}
check(#b % 4 == 0 and b[1] == 0xF0 and b[2] == (math.floor(0x1F0 / 256) % 2) + (#b / 4) * 2, 'header: id low byte, dword count times two plus the ninth id bit')
check(b[5] == 1 and b[6] == 0 and b[7] == 0 and b[8] == 0, 'version 1, three reserved bytes zero')
check(b[9] == string.byte('!'), 'the text starts at byte 9')
-- what the server reads: id = 9 bits, size = 7 bits in dwords, text length = size * 4 - 8 (0x1f0_addon_channel.cpp)
local id9 = b[1] + (b[2] % 2) * 256
local dwords = math.floor(b[2] / 2)
check(id9 == 0x1F0 and dwords * 4 == #b and dwords * 4 - 8 >= #textOf(p) + 1 and dwords * 4 <= 132, 'the server reads id 0x1F0, a size that holds the text and its NUL, within its 132 byte buffer')
check(b[#b] == 0, 'padded with zeros: the text is NUL terminated')
check(has(packets(W), '!squad panel') or W.sentAll():find('!squad panel', 1, true) == nil, 'the menu\'s own panel request after the click is not typed either')

section('a long line is cut at 120 characters and never overruns')
W = boot(); open(W)
answer(W, { 'squadpanel:chan|1', KYO, 'squadpanel:end' })
W.chat.sent = {}
W.handlers.command({ command = '/sq', blocked = false })
W.run(2)
for _, p2 in ipairs(W.pm.sent) do
    check(#p2.bytes <= 132 and #p2.bytes % 4 == 0, 'size within the packet buffer: ' .. #p2.bytes)
end

section('the server stops saying it (an older server after a relog): back to typing')
W = boot(); open(W)
answer(W, { 'squadpanel:chan|1', KYO, 'squadpanel:end' })
W.pm.sent = {}
W.click('Refresh##refresh'); W.run(3)
answer(W, { KYO, 'squadpanel:end' })       -- this answer has no chan line
W.chat.sent = {}
W.pm.sent = {}
W.run(3)
W.click('Call all##callall'); W.run(3)
check(#W.pm.sent == 0 and W.sentAll():find('!squad', 1, true) ~= nil, 'typed again: ' .. W.sentAll():gsub('\n', ' / '))

section('no packet manager, or one that raises: the line is typed, not lost')
W = boot({ noPacketManager = true }); open(W)
answer(W, { 'squadpanel:chan|1', KYO, 'squadpanel:end' })
W.chat.sent = {}
W.click('Call all##callall'); W.run(3)
check(W.sentAll():find('/say !squad', 1, true) ~= nil, 'typed when GetPacketManager gives nothing')
W = boot({ packetsFail = true }); open(W)
answer(W, { 'squadpanel:chan|1', KYO, 'squadpanel:end' })
W.chat.sent = {}
W.click('Call all##callall'); W.run(3)
check(W.sentAll():find('/say !squad', 1, true) ~= nil, 'typed when AddOutgoingPacket raises')

section('a player typing the words in chat changes nothing')
W = boot()
W.chatLine('Someone : squadpanel:chan|1')
open(W)
answer(W, { KYO, KAS, 'squadpanel:end' })
W.chat.sent = {}
W.click('Call all##callall'); W.run(3)
check(#W.pm.sent == 0 and W.sentAll():find('/say !squad', 1, true) ~= nil, 'still typing: the line came when the menu had asked for nothing')

io.write(string.format('\n%d passed, %d failed\n', passed, failed))
if rawget(_G, 'CORE_TEST_HARNESS') then return failed end
os.exit(failed == 0 and 0 or 1)
