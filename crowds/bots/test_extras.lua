-- Stand-in checks for the 2026-11-21 bot additions: bots_social.lua, bots_memory.lua, bots_story.lua, bots_gates.lua,
-- through bots_extras.lua (the way bots.lua uses them), plus bots_hunt.lua's H.start and bots_life.lua's goHome.
-- Run from the server folder (or a copy):  texlua test_extras.lua .
local DIR = arg[1] or '.'
package.path = DIR .. '/?.lua;' .. package.path
local LUA = DIR .. '/modules/custom/lua/'

local KEEP = {}
for _, name in ipairs({ 'extras_config.lua', 'bots_story.txt', 'bots_config.lua' }) do
    local f = io.open(LUA .. name, 'rb')
    KEEP[name] = f and f:read('*a') or false
    if f then f:close() end
end
local function putBack()
    for name, text in pairs(KEEP) do
        if text then
            local f = io.open(LUA .. name, 'wb')
            if f then f:write(text); f:close() end
        else
            os.remove(LUA .. name)
        end
    end
end

local passes, failures = 0, 0
local function check(name, cond, detail)
    if cond then
        passes = passes + 1
        print('ok   ' .. name)
    else
        failures = failures + 1
        print('FAIL ' .. name .. (detail and ('  -- ' .. tostring(detail)) or ''))
    end
end

local NOW = 0 -- ms
local realTime = os.time
os.time = function(t)
    if t then return realTime(t) end
    return 1800000000 + math.floor(NOW / 1000)
end
math.randomseed(1121)

-- the world ----------------------------------------------------------------------------------------
local timers, zones, byName, emotes, moves, bots = {}, {}, {}, {}, {}, {}
local moving = {}
xi = {
    objType = { PC = 1, NPC = 2 },
    emoteMode = { ALL = 0, TEXT = 1, MOTION = 2 },
    emote = { POINT = 0, BOW = 1, SALUTE = 2, LAUGH = 4, NO = 6, YES = 7, WAVE = 8, GOODBYE = 9, JOY = 11, CHEER = 12, CLAP = 13, PRAISE = 14,
        SMILE = 15, SIGH = 19, PANIC = 29, GRIN = 30, THINK = 32, DOUBT = 34, HUH = 37, HURRAY = 43 },
    msg = { channel = { SYSTEM_3 = 29 } },
    module = { registerCommand = function() end },
    allegiance = { MOB = 0 },
    bots = {},
}
local EMOTE_NAME = {}
for k, v in pairs(xi.emote) do EMOTE_NAME[v] = k end

local Zone = {}
Zone.__index = Zone
function Zone:getID() return self.id end
function Zone:getName() return 'Zone_' .. self.id end
function Zone:isNavigablePoint() return true end
function Zone:getPlayers()
    local out = {}
    for _, p in pairs(byName) do
        if rawget(p, 'zoneId') == self.id then out[#out + 1] = p end
    end
    table.sort(out, function(a, b) return a.id < b.id end)
    return out
end
function Zone:getMobs() return self.mobs or {} end
function GetZone(id)
    zones[id] = zones[id] or setmetatable({ id = id }, Zone)
    return zones[id]
end
function GetPlayerByName(name)
    local p = byName[name]
    if p and not rawget(p, 'zoning') then return p end
end

local Char = {}
Char.__index = function(t, k)
    local v = rawget(Char, k)
    if v ~= nil then return v end
    return function() return nil end -- anything else the code asks of a character: a no-op
end
function Char:getID() return rawget(self, 'id') end
function Char:getName() return rawget(self, 'name') end
function Char:getObjType() return xi.objType.PC end
function Char:getZoneID() return rawget(self, 'zoneId') end
function Char:getZone() return GetZone(rawget(self, 'zoneId')) end
function Char:getPos() return { x = rawget(self, 'x'), y = rawget(self, 'y'), z = rawget(self, 'z'), rot = 0 } end
function Char:getMainLvl() return rawget(self, 'lvl') end
function Char:getMainJob() return rawget(self, 'job') end
function Char:getNation() return rawget(self, 'nation') or 0 end
function Char:getHPP() return rawget(self, 'hpp') or 100 end
function Char:isDead() return rawget(self, 'dead') == true end
function Char:isEngaged() return rawget(self, 'engaged') == true end
function Char:getParty() return rawget(self, 'party') or { self } end
function Char:getPartySize() return #(rawget(self, 'party') or { self }) end
function Char:getCharVar(k) return rawget(self, 'vars')[k] or 0 end
function Char:setCharVar(k, v) rawget(self, 'vars')[k] = v end
function Char:hasSpell() return true end
function Char:getEquipID() return 1 end
function Char:timer(ms, fn) table.insert(timers, { at = NOW + ms, who = self, fn = fn }) end
function Char:setPos(x, y, z, rot, zoneId)
    self.x, self.y, self.z = x, y, z
    if zoneId then self.zoneId = zoneId end
    self.setPosCalls = (rawget(self, 'setPosCalls') or 0) + 1
    self.lastSetPos = { x = x, y = y, z = z, zone = zoneId }
end

local nextId = 16000000
local function make(name, isBot, zoneId, x, z, lvl, job)
    nextId = nextId + 1
    local c = setmetatable({ id = nextId, name = name, zoneId = zoneId, x = x, y = 0, z = z, lvl = lvl or 10, job = job or 1, vars = {} }, Char)
    byName[name] = c
    if isBot then bots[c.id] = true end
    return c
end
function BotIsBot(id) return bots[id] == true end
function BotEmote(id, target, which, mode)
    table.insert(emotes, { id = id, target = target and target.id or nil, name = EMOTE_NAME[which], at = NOW, mode = mode })
    return true
end
function BotMoveTo(id, x, y, z) table.insert(moves, { id = id, x = x, y = y, z = z, at = NOW }); moving[id] = true; return true end
function BotIsMoving(id) return moving[id] == true end
function BotHeal() end
function BotAttackOff() end
function BotStop() end
function BotLeaveParty() end

local function advance(ms)
    local stop = NOW + ms
    while true do
        table.sort(timers, function(a, b) return a.at < b.at end)
        local t = timers[1]
        if not t or t.at > stop then break end
        table.remove(timers, 1)
        NOW = t.at
        t.fn(t.who)
    end
    NOW = stop
end
local function emotesOf(c, since)
    local out = {}
    for _, e in ipairs(emotes) do
        if e.id == c.id and e.at >= (since or 0) then out[#out + 1] = e end
    end
    return out
end
local function names(list)
    local out = {}
    for _, e in ipairs(list) do out[#out + 1] = e.name end
    return table.concat(out, ',')
end
local function writeExtras(text)
    if text then
        local f = assert(io.open(LUA .. 'extras_config.lua', 'w'))
        f:write(text)
        f:close()
    else
        os.remove(LUA .. 'extras_config.lua')
    end
    if xi.extras then xi.extras.reload() end
end

local ok, err = pcall(function()
    os.remove(LUA .. 'bots_story.txt')
    writeExtras(nil)
    local state = {}
    local X = dofile(LUA .. 'bots_extras.lua')
    X.setup(state)
    check('bots_extras.lua loads its four parts', X.parts.social and X.parts.memory and X.parts.story and X.parts.gates)
    local function tickAll(list, seconds)
        for _ = 1, seconds do
            for _, c in ipairs(list) do
                state[c.id] = state[c.id] or {}
                X.tick(c, state[c.id])
            end
            advance(1000)
        end
    end

    ---------------------------------------------------------------------------------------------
    -- social
    ---------------------------------------------------------------------------------------------
    local a = make('Aldric', true, 103, 0, 0, 12)
    local b = make('Brina', true, 103, 5, 0, 12)
    local far = make('Corwyn', true, 103, 90, 0, 12)
    a.party, b.party, far.party = { a, b, far }, { a, b, far }, { a, b, far }
    state[a.id], state[b.id], state[far.id] = {}, {}, {}
    local mark = NOW
    X.onLevel(a, state[a.id])
    advance(5000)
    check('level up: it shows its joy (' .. names(emotesOf(a, mark)) .. ')', #emotesOf(a, mark) == 1 and (emotesOf(a, mark)[1].name == 'JOY' or emotesOf(a, mark)[1].name == 'HURRAY'))
    local cheered = 0
    for _ = 1, 40 do
        advance(30000)
        local m = NOW
        X.onLevel(a, state[a.id])
        advance(5000)
        if #emotesOf(b, m) == 1 and emotesOf(b, m)[1].target == a.id then cheered = cheered + 1 end
    end
    check('level up: a party member next to it cheers it most times (' .. cheered .. ' of 40)', cheered >= 20 and cheered <= 36)
    check('level up: one too far away does not', #emotesOf(far) == 0)

    -- your party
    local you = make('Hurami', false, 103, 2, 2, 12)
    local d = make('Daven', true, 103, 3, 3, 12)
    state[d.id] = {}
    tickAll({ d }, 5)
    check('alone: nothing to bow to', #emotesOf(d) == 0 or emotesOf(d)[1].name == 'WAVE')
    emotes = {}
    advance(40000)
    d.party, you.party = { you, d }, { you, d }
    state[d.id].soc.waved = { Hurami = os.time() + 99999 } -- (not the passing wave in this check)
    tickAll({ d }, 8)
    local e = emotesOf(d)
    check('joins your party: one greeting, at you (' .. names(e) .. ')', #e == 1 and e[1].target == you.id and (e[1].name == 'BOW' or e[1].name == 'WAVE' or e[1].name == 'SALUTE'))
    -- you change area: nobody of your name is in the world for a while, and the party list is without you
    emotes = {}
    tickAll({ d }, 30)
    d.party = { d }
    you.zoning = true
    tickAll({ d }, 25)
    you.zoning = nil
    tickAll({ d }, 3) -- (you are there again, the list catches up a moment later)
    d.party = { you, d }
    tickAll({ d }, 30)
    check('you change area (the list loses you for a few seconds): no goodbye and no second greeting', #emotesOf(d) == 0, names(emotesOf(d)))
    -- you level up
    local cheers = 0
    for _ = 1, 30 do
        emotes = {}
        advance(30000)
        you.lvl = you.lvl + 1
        tickAll({ d }, 8)
        if #emotesOf(d) == 1 and emotesOf(d)[1].target == you.id then cheers = cheers + 1 end
    end
    check('you level up: it cheers you more often than not (' .. cheers .. ' of 30)', cheers >= 10 and cheers <= 27)
    emotes = {}
    advance(30000)
    you.lvl = 40
    tickAll({ d }, 8)
    check('a jump of many levels (a level sync ending) is not a level up', #emotesOf(d) == 0)
    -- the party ends
    emotes = {}
    tickAll({ d }, 30)
    d.party, you.party = { d }, { you }
    tickAll({ d }, 20)
    e = emotesOf(d)
    check('your party is over: a goodbye at you (' .. names(e) .. ')', #e == 1 and e[1].target == you.id)

    -- a fight
    local f = make('Fenric', true, 104, 0, 0, 20)
    state[f.id] = {}
    f.engaged, f.hpp = true, 60
    emotes = {}
    tickAll({ f }, 60)
    check('fighting at 60% HP: no emote at all', #emotesOf(f) == 0)
    f.hpp = 15
    tickAll({ f }, 60)
    check('under 20%: one /panic, not one a second', #emotesOf(f) == 1 and emotesOf(f)[1].name == 'PANIC', names(emotesOf(f)))
    xi.bots.isCasting = function() return true end
    emotes = {}
    advance(200000)
    tickAll({ f }, 30)
    check('never while it is casting', #emotesOf(f) == 0)
    xi.bots.isCasting = nil
    f.engaged, f.dead = false, true
    emotes = {}
    tickAll({ f }, 20)
    check('dead: silent', #emotesOf(f) == 0)
    f.dead, f.hpp = false, 100
    tickAll({ f }, 10)
    check('back on its feet: a /sigh', #emotesOf(f) == 1 and emotesOf(f)[1].name == 'SIGH', names(emotesOf(f)))

    -- you walk past
    local g = make('Gerta', true, 105, 0, 0, 20)
    state[g.id] = {}
    local walker = make('Kurami', false, 105, 3, 3, 20)
    local waves = 0
    for _ = 1, 40 do
        emotes = {}
        state[g.id].soc = nil
        advance(60000)
        tickAll({ g }, 8)
        if #emotesOf(g) == 1 and emotesOf(g)[1].name ~= nil and emotesOf(g)[1].target == walker.id then waves = waves + 1 end
    end
    check('you walk past a bot out of town: a wave now and then (' .. waves .. ' of 40)', waves >= 6 and waves <= 24)
    emotes = {}
    state[g.id].soc = nil
    tickAll({ g }, 600)
    check('... and at most once in half an hour for the same player', #emotesOf(g) <= 1, #emotesOf(g))

    -- town talk
    local t1 = make('Tobin', true, 230, 0, 0, 10)
    local t2 = make('Ulla', true, 230, 3, 0, 10)
    local t3 = make('Resting', true, 230, 1, 1, 10)
    state[t1.id] = { life = { phase = 'there', kind = 'idle' } }
    state[t2.id] = { life = { phase = 'there', kind = 'ah' } }
    state[t3.id] = { life = { phase = 'there', kind = 'rest' } }
    emotes = {}
    tickAll({ t1, t2, t3 }, 3600)
    local pairsOk, minGap, restEmotes = 0, 1e9, #emotesOf(t3)
    for i, e1 in ipairs(emotes) do
        local e2 = emotes[i + 1]
        if e2 and e1.id ~= e2.id and e1.target == e2.id and e2.target == e1.id and e2.at - e1.at <= 3500 then pairsOk = pairsOk + 1 end
    end
    for _, c in ipairs({ t1, t2 }) do
        local list = emotesOf(c)
        for i = 2, #list do minGap = math.min(minGap, list[i].at - list[i - 1].at) end
    end
    check(string.format('in town: two bots at their spots trade emotes, turned to each other (%d exchanges in an hour)', pairsOk), pairsOk >= 5 and pairsOk <= 60, #emotes)
    check('a resting bot is left alone', restEmotes == 0)
    check(string.format('nobody spams: at least 20 s between two emotes of one bot (shortest: %.0f s)', minGap / 1000), minGap >= 20000)

    -- switched off
    writeExtras('return {\n    bot_social = false,\n}\n')
    emotes = {}
    tickAll({ t1, t2, g, f }, 1800)
    X.onLevel(a, state[a.id])
    advance(10000)
    check('!extras bot_social off: not one emote', #emotes == 0, #emotes)
    writeExtras(nil)

    ---------------------------------------------------------------------------------------------
    -- memory
    ---------------------------------------------------------------------------------------------
    local M = X.parts.memory
    local h = make('Hale', true, 103, 100, 100, 15)
    local hst = { hunt = { zone = 103, camp = { x = 100, y = 0, z = 100 } } }
    check('no deaths: no danger', M.danger(h, 103) == 0)
    X.onDeath(h, hst)
    check('one death out hunting: wary (1.0), still goes there', math.abs(M.danger(h, 103) - 1) < 0.01 and X.chooseArea(h, 103, function() return 104 end) == 103)
    check('... but not to the same camp within the hour', X.campOk(h, 103, { x = 120, y = 0, z = 110 }) == false and X.campOk(h, 103, { x = 300, y = 0, z = 300 }) == true and X.campOk(h, 104, { x = 100, y = 0, z = 100 }) == true)
    X.onDeath(h, hst)
    check('two deaths: it picks the other area', M.danger(h, 103) >= 1.99 and X.chooseArea(h, 103, function() return 104 end) == 104)
    check('nowhere else to go: it still goes (the least bad)', X.chooseArea(h, 103, function() return 103 end) == 103)
    local other = make('Other', true, 103, 0, 0, 15)
    check('another bot is not affected', M.danger(other, 103) == 0)
    advance(24 * 3600 * 1000)
    check(string.format('a day later it counts half (%.2f) and it goes back', M.danger(h, 103)), math.abs(M.danger(h, 103) - 1) < 0.02 and X.chooseArea(h, 103, function() return 104 end) == 103)
    check('the camp is fine again after an hour', X.campOk(h, 103, { x = 100, y = 0, z = 100 }) == true)
    X.onDeath(h, hst)
    X.onDeath(h, hst)
    h.lvl = 18
    check(string.format('three levels on, it counts for less (%.2f)', M.danger(h, 103)), M.danger(h, 103) > 0.5 and M.danger(h, 103) < 2)
    h.lvl = 20
    check('five levels on: outgrown', M.danger(h, 103) == 0)
    local w = make('Wyn', true, 103, 0, 0, 15)
    X.onDeath(w, {})
    X.onDeath(w, {})
    check('deaths with you (not out hunting) are not held against the area', M.danger(w, 103) == 0)
    -- kept on the bot: a fresh module (a restart) still knows
    h.lvl = 15
    package.loaded['modules/custom/lua/bots_memory'] = nil
    local M2 = dofile(LUA .. 'bots_memory.lua')
    check('after a restart the area is still remembered (kept on the bot)', M2.danger(h, 103) > 1.5)
    writeExtras('return {\n    bot_memory = false,\n}\n')
    local before = M.danger(other, 103)
    X.onDeath(other, { hunt = { zone = 103 } })
    check('!extras bot_memory off: nothing remembered, no steering', M.danger(other, 103) == before and X.chooseArea(h, 103, function() return 104 end) == 103 and X.campOk(h, 103, { x = 100, y = 0, z = 100 }) == true)
    writeExtras(nil)

    ---------------------------------------------------------------------------------------------
    -- story
    ---------------------------------------------------------------------------------------------
    local s = make('Sorrel', true, 230, 0, 0, 5)
    X.onDiary(s, 'hit level 6 on WAR', false)
    X.onDiary(s, 'bought a spell scroll', false)
    X.onDiary(s, 'hit level 10 on WAR', true)
    X.onDiary(s, 'got killed in Valkurm Dunes', false)
    X.onDiary(s, 'got killed in Valkurm Dunes', false)
    advance(3600 * 1000)
    X.onDiary(s, 'got killed in Valkurm Dunes', false)
    X.onDiary(s, 'made nation rank 2', true)
    X.onDiary(s, 'joined the linkshell AzureWolves', false)
    local lines = X.storyLines('Sorrel', 12)
    check('story keeps what matters (' .. #lines .. ' of 8): every 5th level, rank, linkshell, a death per half hour', #lines == 5, table.concat(lines, ' / '))
    check('newest first, with how long ago', lines[1]:find('joined the linkshell', 1, true) ~= nil and lines[#lines]:find('hit level 10', 1, true) ~= nil and lines[#lines]:find('ago', 1, true) ~= nil, lines[1])
    for i = 1, 60 do
        advance(60000)
        X.onDiary(s, 'finished the quest number ' .. i, false)
    end
    check('at most 40 kept per bot', #X.parts.story.of('Sorrel') == 40)
    local s2 = make('Tamsin', true, 230, 0, 0, 5)
    X.onDiary(s2, 'won the pact with Shiva!', true)
    -- a restart: the module is loaded again and reads the file
    package.loaded['modules/custom/lua/bots_story'] = nil
    X.parts.story.reload()
    local fresh = {}
    X.onBrain(s, fresh)
    check('after a restart its diary holds its last five again', fresh.events and #fresh.events == 5 and fresh.events[5].text == 'finished the quest number 60', fresh.events and #fresh.events)
    check('... with their real times', fresh.events[1].t < fresh.events[5].t and fresh.events[5].t <= os.time())
    local again = { events = { { t = 1, text = 'something newer' } }, storyBack = nil }
    X.onBrain(s, again)
    check('a diary that already has something is left alone', #again.events == 1)
    check('the other bot has its own story', #X.storyLines('Tamsin', 12) == 1 and #X.storyLines('Nobody', 12) == 0)
    local f2 = io.open(LUA .. 'bots_story.txt', 'r')
    local n = 0
    for _ in f2:lines() do n = n + 1 end
    f2:close()
    check('the file was tidied at the restart (' .. n .. ' lines for 41 kept)', n == 41 or n == 66)
    writeExtras('return {\n    bot_story = false,\n}\n')
    X.onDiary(s2, 'made nation rank 5', true)
    local off = {}
    X.onBrain(s2, off)
    check('!extras bot_story off: nothing written, nothing put back', #X.storyLines('Tamsin', 12) == 1 and off.events == nil)
    writeExtras(nil)

    ---------------------------------------------------------------------------------------------
    -- gates
    ---------------------------------------------------------------------------------------------
    local G = X.parts.gates
    local gd = dofile(LUA .. 'gates_data.lua')
    local route = G.route(230, 103)
    check('the way from Southern San d\'Oria to Valkurm Dunes: ' .. (route and table.concat(route, ' > ') or 'none'), route and route[1] == 230 and route[#route] == 103 and #route == 4 and (route[2] == 100 or route[2] == 101) and route[3] == 102)
    local exit = G.exitTowards(230, 103, { x = 0, y = 0, z = 0 })
    local isGate = false
    for _, gt in ipairs(gd.gates[230]) do
        if gt.to == route[2] and math.abs((gt.px or gt.x) - exit.x) < 0.01 and math.abs((gt.pz or gt.z) - exit.z) < 0.01 then isGate = true end
    end
    check('it leaves by the gate on that side', isGate)
    local arr = G.arrivalFrom(103, 230)
    local isArrival = false
    for _, src in ipairs({ 100, 101 }) do
        for _, gt in ipairs(gd.gates[src]) do
            if gt.to == 230 and math.abs(gt.ax - arr.x) < 0.01 and math.abs(gt.az - arr.z) < 0.01 then isArrival = true end
        end
    end
    check('coming home from Valkurm it arrives at a Ronfaure gate of Southern San d\'Oria', isArrival)
    check('no way (an area with no zone lines to it): nil', G.route(230, 999) == nil and G.exitTowards(230, 999) == nil and G.arrivalFrom(999, 230) == nil)
    check('the same area: nothing to do', G.route(230, 230) == nil)

    local r = make('Rowan', true, 230, 0, 0, 14)
    local rst = { hunt = { zone = 103, camp = { x = 1, y = 2, z = 3 } }, life = { phase = 'there' } }
    local went = 0
    local function go(bot) went = went + 1; bot:setPos(1, 2, 3, 0, 103) end
    moves = {}
    check('leaving: it starts for the gate', X.leave(r, rst, 103, go) == true and #moves == 1 and math.abs(moves[1].x - exit.x) < 0.01 and went == 0)
    check('... and it counts as busy meanwhile (its hunt stays set, so no bot party or errand picks it up)', rst.hunt ~= nil and rst.trip and rst.trip.hunt == rst.hunt)
    check('on the way: nothing yet', X.tripThink(r, rst) == nil and went == 0)
    r.x, r.z = exit.x + 1, exit.z + 1
    check('at the gate: it leaves for its camp', X.tripThink(r, rst) == 'zoning' and went == 1 and r.zoneId == 103 and rst.trip == nil and rst.hunt and rst.hunt.zone == 103 and rst.life == nil)
    do
        local cx, sx = make('Taken', true, 230, 0, 0, 14), { hunt = { zone = 103, camp = { x = 1, y = 2, z = 3 } } }
        went = 0
        X.leave(cx, sx, 103, go)
        sx.hunt = { zone = 104, leaderOf = true } -- something else gave it another hunt meanwhile
        check('its hunt was replaced on the way: the trip is dropped, the new hunt is kept', X.tripThink(cx, sx) == nil and sx.trip == nil and sx.hunt and sx.hunt.zone == 104 and went == 0)
        local cy, sy = make('Invited', true, 230, 0, 0, 14), { hunt = { zone = 103, camp = { x = 1, y = 2, z = 3 } } }
        X.leave(cy, sy, 103, go)
        X.tripCancel(sy)
        check('cancelled (you invited it): trip and hunt are off', sy.trip == nil and sy.hunt == nil and went == 0)
    end

    local function fresh2(name)
        local c = make(name, true, 230, 0, 0, 14)
        local st = { hunt = { zone = 103, camp = { x = 1, y = 2, z = 3 } } }
        return c, st
    end
    local c1, st1 = fresh2('Slow')
    went = 0
    X.leave(c1, st1, 103, go)
    advance(99000)
    check('not there after 99 s: still walking', X.tripThink(c1, st1) == nil and went == 0)
    advance(2000)
    check('100 s: it leaves from where it is (as it always did)', X.tripThink(c1, st1) == 'zoning' and went == 1)

    local c2, st2 = fresh2('Stuck')
    went = 0
    X.leave(c2, st2, 103, go)
    local tries = 0
    for _ = 1, 20 do
        moving[c2.id] = false -- its walk keeps stopping short
        advance(1000)
        tries = tries + 1
        if X.tripThink(c2, st2) == 'zoning' then break end
    end
    check('a walk that keeps stopping short: started again a few times, then it leaves (' .. tries .. ' s)', went == 1 and tries >= 5 and tries <= 10)

    local c3, st3 = fresh2('Dies')
    went = 0
    X.leave(c3, st3, 103, go)
    c3.dead = true
    check('it dies on the way: the trip and its hunt are forgotten, no jump to the camp', X.tripThink(c3, st3) == nil and st3.trip == nil and st3.hunt == nil and went == 0)

    local c4, st4 = fresh2('Old')
    went = 0
    X.leave(c4, st4, 103, go)
    advance(500000)
    check('a trip from long ago (it logged out on the way) is dropped', X.tripThink(c4, st4) == nil and st4.trip == nil and st4.hunt == nil and went == 0)

    local c5, st5 = fresh2('Fights')
    went = 0
    X.leave(c5, st5, 103, go)
    c5.engaged = true
    advance(200000)
    check('fighting: the trip waits', X.tripThink(c5, st5) == nil and went == 0 and st5.trip ~= nil)

    local c6, st6 = fresh2('NoWay')
    went = 0
    check('no way to the area: it does not walk (false: the old way)', X.leave(c6, st6, 999, go) == false and st6.trip == nil and st6.hunt ~= nil)

    check('coming home: an arrival point at the town gate', (function()
        local c = make('Homer', true, 103, 0, 0, 14)
        local at = X.homeArrival(c, 230)
        return type(at) == 'table' and at.x ~= nil and at.rot ~= nil
    end)())
    check('already in that town: nil (on its spot)', X.homeArrival(r and make('InTown', true, 230, 0, 0, 14), 230) == nil)

    writeExtras('return {\n    bot_gates = false,\n}\n')
    local c7, st7 = fresh2('Off')
    went = 0
    check('!extras bot_gates off: no walk, no gate arrival', X.leave(c7, st7, 103, go) == false and st7.hunt ~= nil and X.homeArrival(make('Off2', true, 103, 0, 0, 14), 230) == nil)
    writeExtras(nil)
    local c8, st8 = fresh2('MidWay')
    went = 0
    X.leave(c8, st8, 103, go)
    writeExtras('return {\n    bot_gates = false,\n}\n')
    check('switched off while one is on its way: it goes at once', X.tripThink(c8, st8) == 'zoning' and went == 1)
    writeExtras(nil)

    ---------------------------------------------------------------------------------------------
    -- bots_hunt.lua and bots_life.lua use them as intended
    ---------------------------------------------------------------------------------------------
    xi.bots.extras = X
    package.preload['modules/custom/lua/nav_guard'] = function() error('off') end
    local Mob = {}
    Mob.__index = function(t, k) return rawget(Mob, k) or function() return nil end end
    function Mob:getMainLvl() return self.lvl end
    function Mob:getAllegiance() return 0 end
    function Mob:isAlive() return true end
    function Mob:isNM() return false end
    function Mob:getPos() return { x = self.x, y = 0, z = self.z } end
    for _, z in ipairs({ 100, 101, 102, 103, 104, 106, 107 }) do
        GetZone(z).mobs = {}
        for i = 1, 30 do
            table.insert(GetZone(z).mobs, setmetatable({ lvl = (z >= 102 and z <= 104) and (10 + i % 6) or (1 + i % 5), x = 200 + i * 20, z = 300 + i * 10 }, Mob))
        end
    end
    local H = dofile(LUA .. 'bots_hunt.lua')
    H.setup(state)

    local hb = make('Hunter', true, 230, 0, 0, 5)
    hb.nation = 0
    local hs = {}
    moves = {}
    local zoned = H.start(hb, hs)
    check('H.start with the gates on: it walks to a gate first (not zoning yet)', zoned == false and hs.trip ~= nil and hs.hunt ~= nil and hb.zoneId == 230 and #moves == 1, tostring(zoned))
    local dest = hs.hunt.zone
    check('... towards one of its level\'s areas (' .. dest .. ')', dest == 100 or dest == 101)
    hb.x, hb.z = hs.trip.gate.x, hs.trip.gate.z
    check('... and from the gate it lands on its camp there', X.tripThink(hb, hs) == 'zoning' and hb.zoneId == dest and hs.hunt and hs.hunt.camp and math.abs(hb.x - hs.hunt.camp.x) < 0.01)

    writeExtras('return {\n    bot_gates = false,\n    bot_memory = false,\n}\n')
    local hb2 = make('HunterOld', true, 230, 0, 0, 5)
    local hs2 = {}
    check('H.start with everything off: straight to its camp, as before', H.start(hb2, hs2) == true and hs2.trip == nil and hs2.hunt ~= nil and (hb2.zoneId == 100 or hb2.zoneId == 101) and hb2.setPosCalls == 1)
    writeExtras(nil)

    -- memory steers H.start: a level 5 San d'Orian has West (100) and East Ronfaure (101)
    local hb3 = make('Wary', true, 230, 0, 0, 5)
    hb3.zoneId = 100
    X.onDeath(hb3, { hunt = { zone = 100 } })
    X.onDeath(hb3, { hunt = { zone = 100 } })
    hb3.zoneId = 230
    local east, total = 0, 60
    writeExtras('return {\n    bot_gates = false,\n}\n')
    for _ = 1, total do
        hb3.zoneId = 230
        local st = {}
        H.start(hb3, st)
        if st.hunt and st.hunt.zone == 101 then east = east + 1 end
    end
    check(string.format('died twice in West Ronfaure: it hunts in East Ronfaure instead (%d of %d)', east, total), east >= total - 2)
    writeExtras('return {\n    bot_gates = false,\n    bot_memory = false,\n}\n')
    east = 0
    for _ = 1, total do
        hb3.zoneId = 230
        local st = {}
        H.start(hb3, st)
        if st.hunt and st.hunt.zone == 101 then east = east + 1 end
    end
    check(string.format('memory off: both areas again, as before (%d of %d east)', east, total), east >= 15 and east <= 45)
    writeExtras(nil)

    -- bots_life.lua goHome
    local cfgF = assert(io.open(LUA .. 'bots_config.lua', 'w'))
    cfgF:write("return { enabled = true, roster = 10, online = 5 }\n")
    cfgF:close()
    xi.crowds = { zoneSpots = function(zoneId) return { { kind = 'rest', x = 11, y = 0, z = 22, rot = 5 }, { kind = 'idle', x = 12, y = 0, z = 23, rot = 6 } } end, makeName = function() return 'X' end }
    local okL, L = pcall(dofile, LUA .. 'bots_life.lua')
    if okL and type(L) == 'table' and L.goHome then
        local hm = make('Homing', true, 103, 0, 0, 14)
        hm.nation = 0
        local gateHits, spotHits = 0, 0
        for _ = 1, 30 do
            hm.zoneId, hm.lastSetPos = 103, nil
            if L.goHome(hm) and hm.lastSetPos then
                local p = hm.lastSetPos
                if math.abs(p.x - 11) < 2 or math.abs(p.x - 12) < 2 then spotHits = spotHits + 1 else gateHits = gateHits + 1 end
            end
        end
        check(string.format('goHome from Valkurm: it arrives at a town gate (%d of 30; %d on a spot)', gateHits, spotHits), gateHits >= 28, gateHits)
        writeExtras('return {\n    bot_gates = false,\n}\n')
        gateHits, spotHits = 0, 0
        for _ = 1, 30 do
            hm.zoneId, hm.lastSetPos = 103, nil
            if L.goHome(hm) and hm.lastSetPos then
                local p = hm.lastSetPos
                if math.abs(p.x - 11) < 2 or math.abs(p.x - 12) < 2 then spotHits = spotHits + 1 else gateHits = gateHits + 1 end
            end
        end
        check(string.format('gates off: on its town spot, as before (%d of 30)', spotHits), spotHits == 30, spotHits)
        writeExtras(nil)
    else
        check('bots_life.lua loads in this stand-in', false, tostring(L))
    end
end)

putBack()
if not ok then
    print('ERROR ' .. tostring(err))
    failures = failures + 1
end
print(string.format('%d passed, %d failed', passes, failures))
os.exit(failures == 0 and 0 or 1)
