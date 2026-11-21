-- Tetra Master tests (XI: Forever Offline). Run from this folder with LuaJIT:
--   luajit run_tests.lua <path to server> [path to Nalfey's TetraMaster source, for the parity test]
local serverPath = arg[1] or '../../../ffxi-local/server/'
local nalfeyPath = arg[2]
package.path = serverPath .. '?.lua;' .. package.path

local R = require('modules/custom/lua/tetramaster_rules')
local A = require('modules/custom/lua/tetramaster_ai')
local Cards = require('modules/custom/lua/tetramaster_cards')

local failures, checks = 0, 0
local function check(ok, msg)
    checks = checks + 1
    if not ok then
        failures = failures + 1
        print('FAIL: ' .. msg)
    end
end

-- A small seeded generator, so runs can be repeated: gen(seed)(lo, hi) like math.random(lo, hi).
local function gen(seed)
    local s = seed % 2147483647
    if s <= 0 then s = s + 2147483646 end
    return function(lo, hi)
        s = (s * 48271) % 2147483647
        return lo + (s % (hi - lo + 1))
    end
end

local function randomHand(rng)
    local hand = {}
    for i = 1, R.HAND_SIZE do
        hand[i] = R.newCard(rng, rng(1, Cards.COUNT))
    end
    return hand
end

local function playMatch(rng, blueLevel, redLevel)
    local m = R.newMatch({ rng = rng, hands = { blue = randomHand(rng), red = randomHand(rng) },
                           first = (rng(1, 2) == 1) and 'blue' or 'red' })
    local levels = { blue = blueLevel, red = redLevel }
    local guard = 0
    while not m.over do
        guard = guard + 1
        assert(guard < 100, 'match does not end')
        local side = m.turn
        local events, why
        if m.pending then
            events, why = R.chooseBattle(m, side, A.chooseBattle(m, side, levels[side]))
        else
            local mv = A.chooseMove(m, side, levels[side])
            events, why = R.place(m, side, mv.hand, mv.x, mv.y)
        end
        assert(events, why)
    end
    return m
end

-----------------------------------
-- 1. Card data
-----------------------------------
for id = 1, Cards.COUNT do
    local c = Cards.get(id)
    check(c ~= nil and c.name ~= '' and (c.type == 'P' or c.type == 'M' or c.type == 'X' or c.type == 'A')
          and c.attack >= 0 and c.attack <= 15, 'card ' .. id .. ' data')
end

-- 2. Hidden stats stay inside the printed digit; the shown code matches the card list
do
    local rng = gen(7)
    for n = 1, 2000 do
        local id = rng(1, Cards.COUNT)
        local c = R.newCard(rng, id)
        check(R.cardCode(c) == Cards.get(id).code, 'code of card ' .. id .. ' ' .. R.cardCode(c))
    end
end

-- 3. Battle odds formula against counting every roll
do
    for _, pair in ipairs({ { 0, 0 }, { 10, 5 }, { 31, 47 }, { 255, 128 }, { 100, 100 } }) do
        local ap, dp = pair[1], pair[2]
        local wins = 0
        for a = 0, ap do for d = 0, dp do if a > d then wins = wins + 1 end end end
        local exact = wins / ((ap + 1) * (dp + 1))
        check(math.abs(A.winChance(ap, dp) - exact) < 1e-12, 'winChance ' .. ap .. ' vs ' .. dp)
    end
end

-- 4. Whole matches at every level: always end, 10 cards on the board, rules hold
do
    local rng = gen(12345)
    for n = 1, 600 do
        local levels = A.LEVELS
        local m = playMatch(rng, levels[(n % 3) + 1], levels[((n + 1) % 3) + 1])
        local b, r = R.score(m)
        check(b + r == 10, 'match ' .. n .. ' has ' .. (b + r) .. ' cards on the board')
        local blocks = 0
        for x = 1, 4 do for y = 1, 4 do if m.cells[x][y] and m.cells[x][y].block then blocks = blocks + 1 end end end
        check(blocks <= 6, 'match ' .. n .. ' has ' .. blocks .. ' blocks')
        local winner, perfect = R.result(m)
        if winner ~= 'draw' then
            local loser = R.opposite(winner)
            local taken = R.loserCards(m)
            for _, c in ipairs(taken) do check(c.owner == loser, 'exchange card not the loser\'s') end
            check(not perfect or (winner == 'blue' and r == 0) or (winner == 'red' and b == 0), 'perfect flag')
        end
    end
end

-- 5. Bad moves are refused
do
    local rng = gen(99)
    local m = R.newMatch({ rng = rng, hands = { blue = randomHand(rng), red = randomHand(rng) }, first = 'blue' })
    local free = R.freeCells(m)[1]
    check(R.place(m, 'red', 1, free.x, free.y) == nil, 'red played on blue\'s turn')
    check(R.place(m, 'blue', 9, free.x, free.y) == nil, 'played a card not in the hand')
    check(R.place(m, 'blue', 1, 0, 3) == nil, 'played off the board')
    for x = 1, 4 do for y = 1, 4 do
        if m.cells[x][y] and m.cells[x][y].block then
            check(R.place(m, 'blue', 1, x, y) == nil, 'played on a blocked cell')
        end
    end end
end

-- 6. How strong the levels are (results printed, and normal/hard must beat easy clearly)
do
    local function rate(a, b, games, seed)
        local rng = gen(seed)
        local w, d = 0, 0
        for n = 1, games do
            local m = playMatch(rng, a, b)
            local winner = R.result(m)
            if winner == 'blue' then w = w + 1 elseif winner == 'draw' then d = d + 1 end
        end
        return w / games, d / games
    end
    local t0 = os.clock()
    local ne = rate('normal', 'easy', 1000, 1)
    local he = rate('hard', 'easy', 300, 2)
    local hn = rate('hard', 'normal', 300, 3)
    local ee = rate('easy', 'easy', 2000, 4)
    print(string.format('win rates: normal vs easy %.0f%%, hard vs easy %.0f%%, hard vs normal %.0f%%, easy vs easy %.0f%%  (%.1fs)',
        ne * 100, he * 100, hn * 100, ee * 100, os.clock() - t0))
    check(ne > 0.6, 'normal should beat easy most of the time')
    check(he > 0.6, 'hard should beat easy most of the time')
end

-- 7. How long the hard AI thinks on a full hand (worst case, first move)
do
    local rng = gen(5)
    local worst = 0
    for n = 1, 20 do
        local m = R.newMatch({ rng = rng, hands = { blue = randomHand(rng), red = randomHand(rng) }, first = 'blue' })
        local t0 = os.clock()
        A.chooseMove(m, 'blue', 'hard')
        worst = math.max(worst, os.clock() - t0)
    end
    print(string.format('hard AI, first move: up to %.0f ms', worst * 1000))
    check(worst < 1.0, 'hard AI too slow for the server (' .. worst .. ' s)')
end

-----------------------------------
-- 8. Parity with Nalfey's original code: the same match, move by move, with the same dice
-----------------------------------
if nalfeyPath then
    -- what his place_card.lua needs, without LOVE: animations finish at once
    play_sound = function() end
    play_capture_sound = function() end
    is_battle_anim_active = function() return false end
    is_capture_fx_active = function() return false end
    start_battle_animation = function(_, _, _, _, _, done) done() end
    start_capture_sequence = function(steps, done)
        for _, st in ipairs(steps) do st.card.side = st.new_side end
        if done then done() end
    end
    flush_pending_remote_messages = function() end
    dofile(nalfeyPath .. '/place_card.lua')

    local function theirCard(c, side)
        local arrows = {}
        for _, name in ipairs(R.arrowsToList(c.arrows)) do arrows[name] = true end
        return { side = side, type = c.type, arrows = arrows,
                 hidden_attack = c.atk, hidden_physical_defense = c.pdef, hidden_magical_defense = c.mdef }
    end

    local mismatches, compared = 0, 0
    local setup = gen(2026)
    for game = 1, 3000 do
        local m = R.newMatch({ rng = setup, hands = { blue = randomHand(setup), red = randomHand(setup) },
                               first = (setup(1, 2) == 1) and 'blue' or 'red' })
        card_grid = {}
        for x = 1, 4 do
            card_grid[x] = {}
            for y = 1, 4 do
                local c = m.cells[x][y]
                if c and c.block then card_grid[x][y] = { side = c.block == 2 and 'neutral2' or 'neutral' } end
            end
        end
        hands = { blue = { ai_controlled = true }, red = { ai_controlled = true } }

        local mover = gen(game * 31)
        while not m.over do
            local side = m.turn
            local mv = A.chooseMove(m, side, 'easy', mover)
            local card = m.hands[side][mv.hand]
            local theirs = theirCard(card, side)

            local seed = setup(1, 2000000000)
            m.rng = gen(seed)
            current_turn = side
            local events = R.place(m, side, mv.hand, mv.x, mv.y)
            while m.pending do
                -- his AI picks a battle with math.random(1, n); ours takes the same roll from the same stream
                R.chooseBattle(m, side, m.rng(1, #m.pending))
            end

            math.random = gen(seed)
            place_card(mv.x, mv.y, theirs, function() end)
            local guard = 0
            while placement.continue_after_battle do
                guard = guard + 1
                assert(guard < 20)
                process_placement_step()
            end

            compared = compared + 1
            local same = true
            for x = 1, 4 do for y = 1, 4 do
                local a, b = m.cells[x][y], card_grid[x][y]
                if (a == nil) ~= (b == nil) then same = false
                elseif a and a.side then
                    if a.side ~= b.side or a.type ~= b.type then same = false end
                end
            end end
            if not same then mismatches = mismatches + 1 end
        end
    end
    print(string.format('parity with Nalfey\'s code: %d moves compared, %d different', compared, mismatches))
    check(mismatches == 0, 'boards differ from Nalfey\'s code')
end

print(string.format('%d checks, %d failed', checks, failures))
os.exit(failures == 0 and 0 or 1)
