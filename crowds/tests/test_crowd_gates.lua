-- Stand-in checks for the 2026-11-21 crowd additions (crowds.lua): coming and going through the gates, the warp at the
-- Home Point, stopping for each other on the road, the stuck watchdog, and the switches (extras.lua).
-- Run from the server folder (or a copy):  texlua test_crowd_gates.lua .
local DIR = arg[1] or '.'
package.path = DIR .. '/?.lua;' .. package.path
local LUA = DIR .. '/modules/custom/lua/'

local KEEP = {}
for _, name in ipairs({ 'crowds_config.lua', 'crowds_spots_user.lua', 'extras_config.lua' }) do
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

local NOW = 0
local realTime = os.time
os.time = function(t)
    if t then return realTime(t) end
    return 1800000000 + math.floor(NOW / 1000)
end
math.randomseed(20261121)

local function world()
    -- a fresh stand-in world and a fresh crowds.lua
    local timers, zones, commands, overrides = {}, {}, {}, {}
    local log = { spawns = {}, gone = {}, emotes = 0, visible = 0 }
    xi = {
        objType = { NPC = 2 },
        status = { NORMAL = 0, DISAPPEAR = 3 },
        animationString = { STATUS_VISIBLE = 'deru', STATUS_DISAPPEAR = 'kesu' },
        emoteMode = { ALL = 0, TEXT = 1, MOTION = 2 },
        emote = { POINT = 0, BOW = 1, LAUGH = 4, NO = 6, YES = 7, WAVE = 8, CHEER = 12, CLAP = 13, SMILE = 15, SIGH = 19, GRIN = 30, THINK = 32, DOUBT = 34, HUH = 37, JOY = 11 },
        msg = { channel = { SAY = 0, SHOUT = 1, SYSTEM_3 = 29 } },
        module = { registerCommand = function(name, t) commands[name] = t end },
        player = {},
    }
    Module = {}
    Module.__index = Module
    function Module:new(name) return setmetatable({ name = name }, Module) end
    function Module:addOverride(path, fn) overrides[path] = fn end
    for name in pairs(package.loaded) do
        if name:find('modules/custom/lua/', 1, true) then package.loaded[name] = nil end
    end
    package.preload['modules/module_utils'] = function() return true end
    package.loaded['modules/module_utils'] = nil
    -- no chat, no field parties, no nav guard in this test: only the crowd itself
    package.preload['modules/custom/lua/crowds_chat'] = function() error('off for this test') end
    package.preload['modules/custom/lua/crowds_field'] = function() error('off for this test') end
    package.preload['modules/custom/lua/nav_guard'] = function() error('off for this test') end

    local Entity = {}
    Entity.__index = Entity
    function Entity:getID() return self.id end
    function Entity:getZoneID() return self.zone.id end
    function Entity:getZone() return self.zone end
    function Entity:getPos() return { x = self.x, y = self.y, z = self.z, rot = self.rot } end
    function Entity:timer(ms, fn) table.insert(timers, { at = NOW + ms, entity = self, fn = fn, gen = self.aiGen }) end
    function Entity:printToPlayer(text) self.said = self.said or {}; table.insert(self.said, text) end
    function Entity:getName() return 'Hurami' end
    function Entity:getLocalVar(k) self.vars = self.vars or {}; return self.vars[k] or 0 end
    function Entity:setLocalVar(k, v) self.vars = self.vars or {}; self.vars[k] = v end
    local Npc = setmetatable({}, { __index = Entity })
    Npc.__index = Npc
    function Npc:initNpcAi() self.ai = true; self.aiGen = (self.aiGen or 0) + 1 end
    function Npc:hideName() end
    function Npc:updateToEntireZone() end
    function Npc:setStatus(s)
        self.status = s
        if s == xi.status.DISAPPEAR then
            self.zone.npcs[self.id] = nil
            self.dead = true
            table.insert(log.gone, { x = self.x, z = self.z, effect = self.lastAnim == 'kesu', at = NOW, stoodSince = self.stoodSince })
        end
    end
    function Npc:setAnimation(a) self.anim = a end
    function Npc:getAnimation() return self.anim or 0 end
    function Npc:setRotation(r) assert(r >= 0 and r <= 255, 'rotation ' .. tostring(r)); self.rot = r end
    function Npc:lookAt(p) assert(type(p) == 'table' and p.x, 'lookAt wants a position'); self.looked = (self.looked or 0) + 1 end
    function Npc:sendEmote(target, e) assert(target ~= nil and type(e) == 'number'); log.emotes = log.emotes + 1; self.emoted = (self.emoted or 0) + 1 end
    function Npc:entityAnimationPacket(s) self.lastAnim = s; if s == 'deru' then log.visible = log.visible + 1 end end
    function Npc:pathTo(x, y, z) assert(self.ai, 'pathTo before initNpcAi'); self.path = { x = x, y = y, z = z }; self.paths = (self.paths or 0) + 1 end
    function Npc:isFollowingPath() return self.path ~= nil end
    function Npc:clearPath() self.path = nil end

    local Zone = {}
    Zone.__index = Zone
    function Zone:getID() return self.id end
    function Zone:getMobs() return {} end
    function Zone:isNavigablePoint() return true end
    function Zone:getPlayers()
        local out = {}
        for _, p in pairs(self.players) do out[#out + 1] = p end
        return out
    end
    local nextId = 0
    function Zone:insertDynamicEntity(t)
        nextId = nextId + 1
        local e = setmetatable({ kind = 'npc', id = 17719000 + nextId, zone = self, x = t.x, y = t.y, z = t.z, rot = t.rotation,
            packetName = t.packetName, stoodSince = NOW }, Npc)
        self.npcs[e.id] = e
        table.insert(log.spawns, { x = t.x, z = t.z, npc = e, at = NOW })
        return e
    end
    function GetZone(id) return zones[id] end
    function GetNPCByID(id)
        for _, z in pairs(zones) do
            if z.npcs[id] then return z.npcs[id] end
        end
    end
    BotIsBot = nil

    local W = { log = log, zones = zones, commands = commands, blocked = {} }
    function W.zone(id)
        zones[id] = zones[id] or setmetatable({ id = id, npcs = {}, players = {} }, Zone)
        return zones[id]
    end
    function W.player(zone, x, z)
        local p = setmetatable({ kind = 'pc', id = 1, zone = zone, x = x or 0, y = 0, z = z or 0, rot = 0 }, Entity)
        zone.players[p.id] = p
        overrides['xi.player.onGameIn'](p, false, true)
        return p
    end
    local SPEED = 4 -- yalms a second
    function W.advance(ms)
        local stop = NOW + ms
        while NOW < stop do
            local stepTo = math.min(stop, NOW + 500)
            table.sort(timers, function(a, b) return a.at < b.at end)
            while timers[1] and timers[1].at <= stepTo do
                local t = table.remove(timers, 1)
                if not t.entity.dead and (t.entity.kind ~= 'npc' or t.gen == t.entity.aiGen) then
                    local before = NOW
                    NOW = math.max(NOW, t.at)
                    t.fn(t.entity)
                    NOW = math.max(before, NOW)
                end
                table.sort(timers, function(a, b) return a.at < b.at end)
            end
            local dt = (stepTo - NOW) / 1000
            for _, z in pairs(zones) do
                for _, n in pairs(z.npcs) do
                    if n.path and not W.blocked[n.id] then
                        local dx, dz = n.path.x - n.x, n.path.z - n.z
                        local d = math.sqrt(dx * dx + dz * dz)
                        if d <= SPEED * dt then
                            n.x, n.y, n.z = n.path.x, n.path.y, n.path.z
                            n.path = nil
                            n.stoodSince = stepTo
                        else
                            n.x, n.z = n.x + dx / d * SPEED * dt, n.z + dz / d * SPEED * dt
                        end
                    end
                end
            end
            NOW = stepTo
        end
    end
    function W.config(text)
        local f = assert(io.open(LUA .. 'crowds_config.lua', 'w'))
        f:write(text)
        f:close()
    end
    function W.extras(text)
        if text then
            local f = assert(io.open(LUA .. 'extras_config.lua', 'w'))
            f:write(text)
            f:close()
        else
            os.remove(LUA .. 'extras_config.lua')
        end
    end
    function W.load()
        super = function() return 'super-result' end
        W.module = dofile(LUA .. 'crowds.lua')
        return W.module
    end
    function W.count(zone)
        local n = 0
        for _ in pairs(zone.npcs) do n = n + 1 end
        return n
    end
    return W
end

local function near(a, list, range)
    for _, p in ipairs(list) do
        if (a.x - p.x) ^ 2 + (a.z - p.z) ^ 2 <= range * range then return true end
    end
    return false
end

local ok, err = pcall(function()
    local gates = dofile(LUA .. 'gates_data.lua')
    check('gates data: Southern San d\'Oria has its three gates and a Mog House door', (function()
        local to = {}
        for _, g in ipairs(gates.gates[230] or {}) do to[g.to] = true end
        return to[100] and to[101] and to[231] and to[230]
    end)())
    local exits, arrivals = {}, {}
    for _, g in ipairs(gates.gates[230]) do exits[#exits + 1] = { x = g.px, z = g.pz } end
    for _, list in pairs(gates.gates) do
        for _, g in ipairs(list) do
            if g.to == 230 then arrivals[#arrivals + 1] = { x = g.ax, z = g.az } end
        end
    end
    check('gates data: arrivals into Southern San d\'Oria (' .. #arrivals .. ')', #arrivals >= 4)

    -- 1) on: a few hours in Southern San d'Oria with a high turnover
    local W = world()
    os.remove(LUA .. 'crowds_spots_user.lua')
    W.config('return { enabled = true, per_zone = 20, chat = false, field = false, turnover = 0.15 }\n')
    W.extras(nil)
    W.load()
    check('!extras is registered', W.commands.extras ~= nil and W.commands.extras.cmdprops.permission == 0)
    local zone = W.zone(230)
    W.player(zone, 0, 0)
    W.advance(5000)
    local start = W.count(zone)
    check('the crowd is there (' .. start .. ')', start == 20)
    local firstFill = #W.log.spawns
    local maxCount = 0
    for _ = 1, 3 * 60 do
        W.advance(60000)
        maxCount = math.max(maxCount, W.count(zone))
    end
    check('never more than the crowd size (most at once: ' .. maxCount .. ')', maxCount <= 20)
    check('still a full crowd after three hours (' .. W.count(zone) .. ')', W.count(zone) >= 17)

    local atGate, byCrystal = 0, 0
    for i = firstFill + 1, #W.log.spawns do
        if near(W.log.spawns[i], arrivals, 0.5) then atGate = atGate + 1 else byCrystal = byCrystal + 1 end
    end
    check(string.format('newcomers: %d came in through a gate, %d by the Home Point', atGate, byCrystal), atGate > 10 and byCrystal > 5)
    check('the first crowd is standing on its spots, nobody at a gate', (function()
        for i = 1, firstFill do
            if near(W.log.spawns[i], arrivals, 0.5) then return false end
        end
        return true
    end)())

    local viaGate, viaGateEffect, warped, warpWait, faded = 0, 0, 0, 0, 0
    for _, g in ipairs(W.log.gone) do
        if near(g, exits, 4.01) then
            viaGate = viaGate + 1
            if g.effect then viaGateEffect = viaGateEffect + 1 end
        elseif g.effect then
            faded = faded + 1
        end
    end
    check(string.format('leavers: %d walked out through a gate (no fade effect: %d with one)', viaGate, viaGateEffect), viaGate > 10 and viaGateEffect == 0)
    check('others still leave where they stand or by the crystal (' .. faded .. ')', faded > 5)
    check('nobody was left walking for ever: every leaver is gone or on its way', (function()
        for _, bot in pairs(W.module.crowds[230].bots) do
            if bot.kind == 'leaving' and os.time() - (bot.walkStarted or 0) > 200 then return false end
        end
        return true
    end)())

    -- 2) the warp: someone sent to the crystal stands 3-5 s before going
    do
        local W2 = world()
        W2.config('return { enabled = true, per_zone = 12, chat = false, field = false, turnover = 0.2 }\n')
        W2.load()
        local z = W2.zone(230)
        W2.player(z, 0, 0)
        W2.advance(5000)
        local warps, early = 0, 0
        local seen = {}
        for _ = 1, 4 * 60 * 2 do
            W2.advance(500)
            for id, bot in pairs(W2.module.crowds[230].bots) do
                if bot.kind == 'warping' and not seen[bot] then
                    seen[bot] = NOW
                end
            end
            for bot, at in pairs(seen) do
                if bot.gone and at then
                    warps = warps + 1
                    if NOW - at < 2500 then early = early + 1 end
                    seen[bot] = false
                end
            end
        end
        check(string.format('warps at the Home Point: %d, each after a moment of standing (%d too early)', warps, early), warps >= 3 and early == 0)
    end

    -- 3) meeting on the road
    do
        local W3 = world()
        W3.config('return { enabled = true, per_zone = 30, chat = false, field = false, turnover = 0 }\n')
        W3.load()
        local z = W3.zone(230)
        W3.player(z, 0, 0)
        W3.advance(5000)
        local inMeet, meetings, resumed, moving = {}, 0, 0, 0
        for _ = 1, 90 * 60 * 2 do
            W3.advance(500)
            for id, bot in pairs(W3.module.crowds[230].bots) do
                if bot.kind == 'meet' and not inMeet[bot] then
                    inMeet[bot] = true
                    meetings = meetings + 1
                    if GetNPCByID(id).path ~= nil then moving = moving + 1 end -- it must have stopped
                elseif inMeet[bot] and bot.kind ~= 'meet' then
                    inMeet[bot] = nil
                    if bot.kind == 'walk' or bot.kind == 'idle' or bot.kind == 'rest' or bot.kind == 'ah' then resumed = resumed + 1 end
                end
            end
        end
        local n = meetings
        local still = 0
        for _ in pairs(inMeet) do still = still + 1 end
        check(string.format('walkers stopped for each other (%d times, always two at a time), standing still while they did', n), n >= 2 and n % 2 == 0 and moving == 0, n .. ' / moving ' .. moving)
        check('each went on its way afterwards (' .. resumed .. ' of ' .. (n - still) .. ')', resumed == n - still)
        check('they greeted (emotes: ' .. W3.log.emotes .. ')', W3.log.emotes >= n)
    end

    -- 4) the watchdog: a walker caught on something stops after about ten seconds
    do
        local W4 = world()
        W4.config('return { enabled = true, per_zone = 10, chat = false, field = false, turnover = 0 }\n')
        W4.load()
        local z = W4.zone(230)
        W4.player(z, 0, 0)
        W4.advance(5000)
        local caught, since
        for _ = 1, 30 * 60 * 2 do
            W4.advance(500)
            if not caught then
                for id, bot in pairs(W4.module.crowds[230].bots) do
                    if bot.kind == 'walk' and GetNPCByID(id).path then
                        caught, since = { id = id, bot = bot }, NOW
                        W4.blocked[id] = true
                        break
                    end
                end
            elseif caught.bot.kind ~= 'walk' then
                break
            end
        end
        local took = caught and (NOW - since) / 1000 or -1
        check(string.format('a walker caught on something gave up after %.0f s (not two minutes)', took), caught ~= nil and took >= 6 and took <= 20, took)
        check('and it stands there with no spot held', caught and caught.bot.spot == nil and caught.bot.kind == 'idle')
    end

    -- 5) switched off: as before
    do
        local W5 = world()
        W5.config('return { enabled = true, per_zone = 20, chat = false, field = false, turnover = 0.15 }\n')
        W5.extras('return {\n    crowd_gates = false,\n    crowd_meet = false,\n}\n')
        W5.load()
        local z = W5.zone(230)
        W5.player(z, 0, 0)
        W5.advance(5000)
        local first = #W5.log.spawns
        local kinds = {}
        for _ = 1, 2 * 60 * 6 do
            W5.advance(10000)
            for _, bot in pairs(W5.module.crowds[230].bots) do kinds[bot.kind or '?'] = true end
        end
        local gateArrivals, gateExits, noEffect = 0, 0, 0
        for i = first + 1, #W5.log.spawns do
            if near(W5.log.spawns[i], arrivals, 0.5) then gateArrivals = gateArrivals + 1 end
        end
        for _, g in ipairs(W5.log.gone) do
            if not g.effect then noEffect = noEffect + 1 end
        end
        check('off: no newcomer at a gate (' .. gateArrivals .. '), every leaver fades as before (' .. noEffect .. ' without)', gateArrivals == 0 and noEffect == 0)
        check('off: nobody leaving by walking, warping or meeting', not kinds.leaving and not kinds.warping and not kinds.meet)
        check('off: turnover still happens (' .. (#W5.log.spawns - first) .. ' newcomers)', #W5.log.spawns - first > 10)
        check('off: every newcomer still gets the arriving effect', W5.log.visible == #W5.log.spawns - first, W5.log.visible)
    end

    -- 6) !extras: switching and keeping the choice
    do
        local W6 = world()
        W6.config('return { enabled = true, per_zone = 5, chat = false, field = false }\n')
        W6.extras(nil)
        W6.load()
        local z = W6.zone(230)
        local p = W6.player(z, 0, 0)
        W6.commands.extras.onTrigger(p, 'crowd_gates', 'off')
        check('!extras crowd_gates off: off now', xi.extras.on('crowd_gates') == false and xi.extras.on('crowd_meet') == true)
        local f = io.open(LUA .. 'extras_config.lua', 'r')
        local text = f and f:read('*a') or ''
        if f then f:close() end
        check('... and written down for the next PLAY', text:find('crowd_gates = false', 1, true) ~= nil and text:find('crowd_meet = true', 1, true) ~= nil)
        W6.commands.extras.onTrigger(p, 'all', 'on')
        check('!extras all on: everything on again', xi.extras.on('crowd_gates') and xi.extras.on('bot_social') and xi.extras.on('bot_gates'))
        W6.commands.extras.onTrigger(p, 'nonsense', 'off')
        check('an unknown name is refused', p.said[#p.said]:find('No such switch', 1, true) ~= nil)
        W6.commands.extras.onTrigger(p)
        check('!extras lists the six switches', #p.said >= 9)
    end

    -- 7) every crowd area: an hour each, no errors, never over the size
    do
        local W7 = world()
        W7.config('return { enabled = true, per_zone = 30, chat = false, field = false, turnover = 0.1 }\n')
        W7.extras(nil)
        W7.load()
        local data = require('modules/custom/lua/crowds_data')
        local areas, withGates, over = 0, 0, 0
        for zoneId in pairs(data.zones) do
            areas = areas + 1
            local z = W7.zone(zoneId)
            local p = W7.player(z, 0, 0)
            for _ = 1, 20 do
                W7.advance(60000)
                if W7.count(z) > 40 then over = over + 1 end
            end
            local c = W7.module.crowds[zoneId]
            if c and c.gates and (#c.gates.exits > 0 or #c.gates.arrivals > 0) then withGates = withGates + 1 end
            z.players[p.id] = nil
        end
        check(string.format('all %d crowd areas ran 20 minutes each without an error (%d have gates)', areas, withGates), areas >= 41 and withGates >= 30 and over == 0)
    end
end)

putBack()
if not ok then
    print('ERROR ' .. tostring(err))
    failures = failures + 1
end
print(string.format('%d passed, %d failed', passes, failures))
os.exit(failures == 0 and 0 or 1)
