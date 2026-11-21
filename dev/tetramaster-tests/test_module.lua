-- Tetra Master: the !tm command with a pretend player (no game server needed).
--   luajit test_module.lua <path to server>
local serverPath = arg[1] or '../../../ffxi-local/server/'
package.path = serverPath .. '?.lua;' .. package.path
package.preload['modules/module_utils'] = function()
    Module = { new = function(_, name) return { name = name, addOverride = function() end } end }
    return true
end

local commands = {}
xi = { module = { registerCommand = function(name, c) commands[name] = c end } }
require('modules/custom/lua/tetramaster')

local failures, checks = 0, 0
local function check(ok, msg)
    checks = checks + 1
    if not ok then failures = failures + 1; print('FAIL: ' .. msg) end
end

local function newPlayer(id)
    local p = { vars = {}, lines = {}, gil = 0, id = id }
    function p:getID() return self.id end
    function p:getCharVar(k) return self.vars[k] or 0 end
    function p:setCharVar(k, v) self.vars[k] = v end
    function p:printToPlayer(t) self.lines[#self.lines + 1] = t end
    function p:addGil(n) self.gil = self.gil + n end
    return p
end

local function tm(p, ...)
    commands.tm.onTrigger(p, ...)
end

-- reads the lines the addon would see and keeps a board, like the addon does
local function parse(p, view)
    for _, line in ipairs(p.lines) do
        local body = line:match('^tetramaster:(.*)$')
        if body then
            local f = {}
            for part in (body .. '|'):gmatch('([^|]*)|') do f[#f + 1] = part end
            local k = f[1]
            if k == 'start' then
                view.cells, view.hand, view.over, view.choose, view.turn = {}, {}, false, nil, f[3]
            elseif k == 'block' then view.cells[f[2] .. ',' .. f[3]] = 'block'
            elseif k == 'cell' then view.cells[f[2] .. ',' .. f[3]] = f[4]
            elseif k == 'hand' then view.hand[tonumber(f[2])] = f[3]
            elseif k == 'place' then
                view.cells[f[3] .. ',' .. f[4]] = f[2]
                if f[2] == 'blue' then table.remove(view.hand, view.placed) end
            elseif k == 'capture' or k == 'combo' then view.cells[f[2] .. ',' .. f[3]] = f[4]
            elseif k == 'choose' then view.choose = f[2]
            elseif k == 'turn' or k == 'sync' then view.turn = f[2]; view.choose = (k == 'sync') and view.choose or nil
            elseif k == 'end' then view.over = true; view.result = { tonumber(f[2]), tonumber(f[3]), f[4], f[5], tonumber(f[6]) }
            elseif k == 'error' then view.error = f[2]
            end
        end
    end
    p.lines = {}
end

math.randomseed(42)
local wins, total = 0, 0
for game = 1, 300 do
    local p = newPlayer(game % 3 + 1)
    local view = {}
    local level = ({ 'easy', 'normal', 'hard' })[game % 3 + 1]
    if game % 3 == 0 then p = newPlayer(77); p.vars = {} end
    if (p.vars.TM_N or 0) < 5 then commands.tmgive.onTrigger(p, tostring(math.random(1, 250)), '5') end
    tm(p, 'play', level)
    parse(p, view)
    check(view.cells ~= nil, 'no start')
    local guard = 0
    while not view.over do
        guard = guard + 1
        if guard > 30 then check(false, 'game ' .. game .. ' stuck'); break end
        if view.choose then
            tm(p, 'pick', '1')
            view.choose = nil
        else
            check(view.turn == 'blue', 'expected your turn')
            local free
            for x = 1, 4 do for y = 1, 4 do
                if not free and view.cells[x .. ',' .. y] == nil then free = { x, y } end
            end end
            view.placed = math.random(1, #view.hand)
            tm(p, 'move', tostring(view.placed), tostring(free[1]), tostring(free[2]))
        end
        parse(p, view)
        check(view.error == nil, 'error: ' .. tostring(view.error))
        view.error = nil
    end
    if view.result then
        total = total + 1
        local b, r, winner, perfect, gil = unpack(view.result)
        check(b + r == 10, 'score adds up')
        check((winner == 'blue') == (gil > 0), 'gil only for a win')
        if winner == 'blue' then wins = wins + 1 end
        -- the addon's own board must agree with the score
        local nb, nr = 0, 0
        for _, v in pairs(view.cells) do if v == 'blue' then nb = nb + 1 elseif v == 'red' then nr = nr + 1 end end
        check(nb == b and nr == r, string.format('game %d: addon board %d-%d, server %d-%d', game, nb, nr, b, r))
    end
end

-- the launcher's gil slider: a win against the computer pays 2x
do
    xi.settings = { main = { TM_GIL_RATE = 2 } }
    local ok2 = true
    local base = { easy = 100, normal = 300, hard = 800 }
    for game = 1, 60 do
        local p = newPlayer(900 + game)
        commands.tmgive.onTrigger(p, '237', '5')       -- Behemoth King x5, to win often
        local level = ({ 'easy', 'normal', 'hard' })[game % 3 + 1]
        tm(p, 'play', level)
        local view = {}
        parse(p, view)
        local guard = 0
        while not view.over and guard < 40 do
            guard = guard + 1
            if view.choose then tm(p, 'pick', '1'); view.choose = nil
            else
                local free
                for x = 1, 4 do for y = 1, 4 do if not free and view.cells[x .. ',' .. y] == nil then free = { x, y } end end end
                view.placed = 1
                tm(p, 'move', '1', tostring(free[1]), tostring(free[2]))
            end
            parse(p, view)
        end
        if view.result and view.result[3] == 'blue' then
            local want = base[level] * (view.result[4] == '1' and 2 or 1) * 2
            if view.result[5] ~= want or p.gil ~= want then ok2 = false; print('gil', level, view.result[5], want) end
        end
    end
    check(ok2, 'gil at 2x')
    xi.settings = nil
end

-- starter hand, deck, bad moves, quit, GM give
do
    local p = newPlayer(500)
    tm(p, 'play', 'easy')
    check((p.vars.TM_N or 0) == 0, 'no free starter hand any more')
    local refused = false
    for _, l in ipairs(p.lines) do if l:find('Luto Mewrilah in Upper Jeuno') then refused = true end end
    check(refused, 'told to visit a card trader')
    for k = 1, 5 do commands.tmgive.onTrigger(p, tostring(k * 3), '1') end
    tm(p, 'play', 'easy')
    check(p.vars.TM_N == 5, 'five cards given')
    tm(p, 'move', '9', '1', '1'); parse(p, {})
    commands.tmgive.onTrigger(p, '67', '2')
    check(p.vars.TM_N == 7, 'gave 2 cards')
    tm(p, 'deck', '7', '6', '1', '2', '3')
    check(p.vars.TM_D1 == 7 and p.vars.TM_D2 == 6, 'deck saved')
    tm(p, 'deck', '7', '7', '1', '2', '3')
    check(p.vars.TM_D2 == 6, 'duplicate deck refused')
    tm(p, 'quit')
    local seen = false
    for _, l in ipairs(p.lines) do if l == 'tetramaster:quit' then seen = true end end
    check(seen, 'quit answered')
    p.lines = {}
    tm(p, 'cards')
    local n = 0
    for _, l in ipairs(p.lines) do if l:match('^tetramaster:card|') then n = n + 1 end end
    check(n == 7, 'cards listed: ' .. n)
end

print(string.format('module: %d games, you (random moves) won %d; %d checks, %d failed', total, wins, checks, failures))
os.exit(failures == 0 and 0 or 1)
