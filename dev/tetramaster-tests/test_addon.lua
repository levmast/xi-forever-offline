-- Tetra Master: the addon and the !tm command together, without the game: a pretend Ashita and imgui,
-- clicks on the board, and the server module answering. Checks the board the addon shows against the server.
--   luajit test_addon.lua <path to server> <path to the tetramaster addon folder>
local serverPath, addonPath = arg[1], arg[2]
package.path = serverPath .. '?.lua;' .. package.path

-- the server, with a pretend player
package.preload['modules/module_utils'] = function() Module = { new = function(_, n) return { name = n, addOverride = function() end } end } return true end
local commands = {}
xi = { module = { registerCommand = function(name, c) commands[name] = c end } }
require('modules/custom/lua/tetramaster')

local handlers = {}
local clock = 0
local mouse, clicked, rclick = { 0, 0 }, false, false
local queued = {}

local player = { vars = {}, gil = 0 }
function player:getID() return 1 end
function player:getCharVar(k) return self.vars[k] or 0 end
function player:setCharVar(k, v) self.vars[k] = v end
function player:addGil(n) self.gil = self.gil + n end
local serverLines = {}
function player:printToPlayer(t) serverLines[#serverLines + 1] = t end

-- pretend Ashita
function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t + 1] = w end return t end
addon = { path = addonPath }
ashita = {
    events = { register = function(ev, name, fn) handlers[ev] = fn end },
    time = { get_tick64 = function() return clock * 1000 end },
    fs = { create_directory = function() end },
}
AshitaCore = {
    GetInstallPath = function() return '/tmp/tm-ashita/' end,
    GetChatManager = function() return {
        IsInputOpen = function() return false end,
        QueueCommand = function(_, _, cmd) queued[#queued + 1] = cmd end,
    } end,
}
package.preload['common'] = function() return true end
package.preload['d3d8'] = function() return { get_device = function() return nil end } end
local draws = 0
local imgui = setmetatable({}, { __index = function() return function() return false end end })
imgui.Begin = function() return true end
-- like Ashita: positions come back as two numbers, and indexing a number is an error (Ashita's sugar library)
imgui.GetCursorScreenPos = function() return 10, 20 end
imgui.GetMousePos = function() return mouse[1], mouse[2] end
debug.setmetatable(0, { __index = function(_, k) error('Math namespace does not contain a definition for: ' .. tostring(k)) end })
imgui.IsWindowHovered = function() return true end
imgui.IsMouseClicked = function(b) if b == 0 then return clicked end return rclick end
imgui.Image = function() draws = draws + 1 end
package.preload['imgui'] = function() return imgui end
ImGuiCond_Always, ImGuiCond_FirstUseEver, ImGuiWindowFlags_NoResize, ImGuiWindowFlags_NoScrollbar, ImGuiWindowFlags_NoScrollWithMouse = 1, 2, 4, 8, 16

TETRAMASTER_TEST = {}
local printed = {}
local realPrint = print
print = function(...) printed[#printed + 1] = table.concat({ ... }, ' ') end
dofile(addonPath .. 'tetramaster.lua')
handlers.load()
print = realPrint

local failures, checks = 0, 0
local function check(ok, msg) checks = checks + 1; if not ok then failures = failures + 1; print('FAIL: ' .. msg) end end

local function frame()
    clock = clock + 0.05
    handlers.d3d_present()
    clicked, rclick = false, false
    -- commands the addon sent reach the server
    for _, cmd in ipairs(queued) do
        local a = cmd:args()
        check(a[1] == '/say' and a[2] == '!tm', 'odd command ' .. cmd)
        commands.tm.onTrigger(player, a[3], a[4], a[5], a[6], a[7], a[8])
    end
    queued = {}
    -- the server's lines reach the addon (they must all be hidden)
    for _, line in ipairs(serverLines) do
        local e = { message = line, blocked = false }
        handlers.text_in(e)
        if line:match('^tetramaster:') then check(e.blocked, 'line not hidden: ' .. line) end
    end
    serverLines = {}
end

local S = 2
local function clickAt(x, y) mouse = { 10 + x * S, 20 + y * S }; clicked = true; frame() end

local G = TETRAMASTER_TEST.G
for k = 1, 5 do commands.tmgive.onTrigger(player, tostring(40 + k), '1') end
local games, wins = 0, 0
local errs = 0
math.randomseed(3)
for game = 1, 60 do
    handlers.command({ command = '/tm play ' .. ({ 'easy', 'normal', 'hard' })[game % 3 + 1], blocked = false })
    local guard = 0
    while G.phase == 'over' or G.phase == 'menu' do frame(); guard = guard + 1; assert(guard < 200, 'match did not start') end
    guard = 0
    while G.phase ~= 'over' do
        guard = guard + 1
        if guard > 4000 then check(false, 'game ' .. game .. ' never ended (phase ' .. G.phase .. ')'); break end
        if G.choose and G.turn == 'blue' and not G.busy and G.anim == nil and #G.queue == 0 then
            local o = G.choose[math.random(1, #G.choose)]
            clickAt(73 + (o.x - 1) * 42 + 20, 9 + (o.y - 1) * 52 + 20)
        elseif G.phase == 'play' and G.turn == 'blue' and not G.busy and G.anim == nil and #G.queue == 0 and #G.hand > 0 then
            local step = (#G.hand == 5) and 42 or 51
            local i = math.random(1, #G.hand)
            if G.selected ~= i then clickAt(275, 8 + (i - 1) * step + 20) end
            local x, y = math.random(1, 4), math.random(1, 4)
            clickAt(73 + (x - 1) * 42 + 20, 9 + (y - 1) * 52 + 20)
        else
            frame()
        end
    end
    for k = 1, 5 do frame() end
    games = games + 1
    local res = G.result
    check(res ~= nil, 'no result')
    if res then
        local b, r = 0, 0
        for _, c in pairs(G.cells) do if c.side == 'blue' then b = b + 1 elseif c.side == 'red' then r = r + 1 end end
        check(b == res.b and r == res.r, string.format('game %d: board shows %d-%d, server says %d-%d', game, b, r, res.b, res.r))
        check(#G.hand == 0 and G.ohand == 0, 'hands empty at the end')
        if res.winner == 'blue' then wins = wins + 1 end
    end
end

for _, p in ipairs(printed) do if p:find('error') then errs = errs + 1; print('addon said: ' .. p) end end
check(errs == 0, 'the addon printed errors')
-- reopening the board mid-match brings the same match back
handlers.command({ command = '/tm play normal', blocked = false })
for k = 1, 60 do frame() end
local before = 0
for _ in pairs(G.cells) do before = before + 1 end
handlers.command({ command = '/tm', blocked = false }) -- close
handlers.command({ command = '/tm', blocked = false }) -- open again: asks the server for the match
for k = 1, 60 do frame() end
local after = 0
for _ in pairs(G.cells) do after = after + 1 end
check(before == after and G.phase == 'play', 'match restored after reopening')
-- the shop window: lines from a trader open it, and its Buy button sends !tm buy
handlers.command({ command = '/tm quit', blocked = false })
for k = 1, 30 do frame() end
G.phase = 'menu'
local feed = { 'tetramaster:shop|2|Lion Springs card trader|5000', 'tetramaster:sellprices|30|80|300|1000|3000' }
for i = 1, 30 do feed[#feed + 1] = string.format('tetramaster:stock|%d|%d|0P00|150|1', i, i) end
feed[#feed + 1] = 'tetramaster:stockend'
for _, l in ipairs(feed) do serverLines[#serverLines + 1] = l end
frame()
check(G.shop ~= nil and #G.shop.stock == 30 and G.gil == 5000 and G.sellPrices[5] == 3000, 'shop opened from the trader lines')
imgui.BeginTabBar = function() return true end
imgui.BeginTabItem = function(label) return label == 'Buy' end
local sentBuy = false
imgui.Button = function(label) return label == 'Buy##b3' end
local realQC = AshitaCore.GetChatManager
AshitaCore.GetChatManager = function()
    return { IsInputOpen = function() return false end, QueueCommand = function(_, _, cmd) if cmd == '/say !tm buy 3' then sentBuy = true end end }
end
for k = 1, 40 do clock = clock + 0.1; handlers.d3d_present() end
AshitaCore.GetChatManager = realQC
imgui.Button = function() return false end
check(sentBuy, 'Buy button sends !tm buy 3')
serverLines[#serverLines + 1] = 'tetramaster:found|1|255|0P00'
frame()
check(G.note:find('found a card'), 'found-card note shown')

print(string.format('addon: %d games played by clicking, won %d, %d gil; %d checks, %d failed', games, wins, player.gil, checks, failures))
os.exit(failures == 0 and 0 or 1)
