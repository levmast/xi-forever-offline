-- Stand-in world for crowds.lua: fake zone, NPCs with timers, players and a clock. Run: texlua test_crowds.lua <dir with crowds.lua>
local DIR = arg[1] or '..'
package.path = DIR .. '/?.lua;' .. package.path
-- These tests write the real crowd files in <dir> (settings, marked spots, the AI pool): keep them and put them back at the end
local KEEP = {}
for _, name in ipairs({ 'crowds_config.lua', 'crowds_spots_user.lua', 'crowds_chat_ai.lua' }) do
    local f = io.open(DIR .. '/modules/custom/lua/' .. name, 'rb')
    KEEP[name] = f and f:read('a') or false
    if f then f:close() end
end
local function putBack()
    for name, text in pairs(KEEP) do
        local path = DIR .. '/modules/custom/lua/' .. name
        if text then
            local f = io.open(path, 'wb')
            if f then f:write(text); f:close() end
        else
            os.remove(path)
        end
    end
end

local failures, passes = 0, 0
local function check(name, cond, detail)
    if cond then
        passes = passes + 1
        print('ok   ' .. name)
    else
        failures = failures + 1
        print('FAIL ' .. name .. (detail and ('  -- ' .. tostring(detail)) or ''))
    end
end

-- clock -------------------------------------------------------------------------------------------
local NOW = 0 -- ms
local realTime = os.time
os.time = function(t)
    if t then
        return realTime(t)
    end
    return 1800000000 + math.floor(NOW / 1000)
end

-- server API stand-ins ---------------------------------------------------------------------------
xi = {
    objType = { NPC = 2 },
    status = { NORMAL = 0, DISAPPEAR = 3 },
    animationString = { STATUS_VISIBLE = 'deru', STATUS_DISAPPEAR = 'kesu' },
    emoteMode = { ALL = 0, TEXT = 1, MOTION = 2 },
    emote = { POINT = 0, BOW = 1, LAUGH = 4, NO = 6, YES = 7, WAVE = 8, CHEER = 12, CLAP = 13, SMILE = 15, SIGH = 19, GRIN = 30, THINK = 32, DOUBT = 34, HUH = 37, JOY = 11 },
    msg = { channel = { SAY = 0, SHOUT = 1, SYSTEM_3 = 29 } },
    module = {},
    player = {},
}
local commands = {}
xi.module.registerCommand = function(name, t) commands[name] = t end

local overrides = {}
Module = {}
Module.__index = Module
function Module:new(name)
    return setmetatable({ name = name }, Module)
end
function Module:addOverride(path, fn)
    overrides[path] = fn
end
package.preload['modules/module_utils'] = function() return true end

local timers = {}         -- { at, entity, fn }
local entities = {}       -- [id] = entity (all ever made)
local stats = { inserts = 0, timerFires = 0, emotes = 0, paths = 0, timerBeforeAi = 0, emoteText = 0 }
local nextId = 0x700

local Entity = {}
Entity.__index = Entity
function Entity:getID() return self.id end
function Entity:getZoneID() return self.zone.id end
function Entity:getZone() return self.zone end
function Entity:getPos() return { x = self.x, y = self.y, z = self.z, rot = self.rot } end
function Entity:timer(ms, fn)
    if self.kind == 'npc' and not self.ai then
        stats.timerBeforeAi = stats.timerBeforeAi + 1
    end
    table.insert(timers, { at = NOW + ms, entity = self, fn = fn, gen = self.aiGen })
end
function Entity:printToPlayer(text, kind, name)
    self.said = self.said or {}; table.insert(self.said, text)
    self.heard = self.heard or {}; table.insert(self.heard, { text = text, kind = kind, name = name, at = NOW })
end
function Entity:getName() return self.name or 'Hurami' end
function Entity:getLocalVar(k) self.vars = self.vars or {}; return self.vars[k] or 0 end
function Entity:setLocalVar(k, v) self.vars = self.vars or {}; self.vars[k] = v end

local Npc = setmetatable({}, { __index = Entity })
Npc.__index = Npc
function Npc:initNpcAi() self.ai = true; self.aiGen = (self.aiGen or 0) + 1 end
function Npc:setStatus(s)
    self.status = s
    if s == xi.status.DISAPPEAR then
        self.zone.npcs[self.id] = nil -- releaseIdOnDisappear: gone (its timers go with it)
        self.dead = true
    end
end
function Npc:setAnimation(a) self.anim = a end
function Npc:getAnimation() return self.anim or 0 end
function Npc:setRotation(r) assert(r >= 0 and r <= 255, 'rotation out of range ' .. r); self.rot = r end
function Npc:lookAt(p) assert(type(p) == 'table' and p.x, 'lookAt wants a position') end
function Npc:sendEmote(target, e, mode)
    assert(target ~= nil, 'emote without target')
    assert(type(e) == 'number', 'emote id')
    stats.emotes = stats.emotes + 1
    if mode == xi.emoteMode.ALL then stats.emoteText = stats.emoteText + 1 end
end
function Npc:entityAnimationPacket(s) self.lastAnim = s end
function Npc:pathTo(x, y, z)
    assert(self.ai, 'pathTo before initNpcAi')
    stats.paths = stats.paths + 1
    local d = math.sqrt((x - self.x) ^ 2 + (z - self.z) ^ 2)
    stats.walkTotal = (stats.walkTotal or 0) + 1
    if d <= 80 then stats.walkNear = (stats.walkNear or 0) + 1 end
    self.path = { x = x, y = y, z = z, left = math.random(2, 8) } -- arrives after a few seconds
end
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
function Zone:insertDynamicEntity(t)
    stats.inserts = stats.inserts + 1
    assert(t.objtype == xi.objType.NPC)
    assert(type(t.look) == 'string' and #t.look == 42 and t.look:match('^0x%x+$'), 'look ' .. tostring(t.look))
    assert(t.name and t.name:match('^[%w_]+$'), 'internal name ' .. tostring(t.name))
    assert(t.releaseIdOnDisappear == true)
    nextId = nextId + 1
    local e = setmetatable({ kind = 'npc', id = 17719000 + nextId, zone = self, x = t.x, y = t.y, z = t.z, rot = t.rotation,
        look = t.look, packetName = t.packetName, onTrigger = t.onTrigger, flags = t.entityFlags }, Npc)
    self.npcs[e.id] = e
    entities[e.id] = e
    return e
end

local zones = {}
local function makeZone(id)
    zones[id] = setmetatable({ id = id, npcs = {}, players = {} }, Zone)
    return zones[id]
end
function GetZone(id) return zones[id] end
function GetNPCByID(id)
    for _, z in pairs(zones) do
        if z.npcs[id] then return z.npcs[id] end
    end
    return nil
end

local function makePlayer(zone, x, z)
    local p = setmetatable({ kind = 'pc', id = 1, zone = zone, x = x or 0, y = 0, z = z or 0, rot = 0 }, Entity)
    return p
end

-- run the clock: walking NPCs arrive, timers fire in order
local function advance(ms)
    local stop = NOW + ms
    while true do
        table.sort(timers, function(a, b) return a.at < b.at end)
        local t = timers[1]
        if not t or t.at > stop then break end
        table.remove(timers, 1)
        -- walking: one second of movement per elapsed second
        local step = t.at - NOW
        NOW = t.at
        for _, z in pairs(zones) do
            for _, n in pairs(z.npcs) do
                if n.path then
                    n.path.left = n.path.left - step / 1000
                    if n.path.left <= 0 then
                        n.x, n.y, n.z = n.path.x, n.path.y, n.path.z
                        n.path = nil
                    end
                end
            end
        end
        if not t.entity.dead and (t.entity.kind ~= 'npc' or t.gen == t.entity.aiGen) then
            stats.timerFires = stats.timerFires + 1
            t.fn(t.entity)
        end
    end
    NOW = stop
end

local function zoneIn(player, zone)
    zone.players[player.id] = player
    player.zone = zone
    overrides['xi.player.onGameIn'](player, false, true)
end
local function zoneOut(player)
    player.zone.players[player.id] = nil
end

-- data: real generated file if present, else a small one ----------------------------------------
local function liveBots(zone)
    local n = 0
    for _, e in pairs(zone.npcs) do
        if e.packetName then n = n + 1 end
    end
    return n
end

-- config written like the launcher does
local function writeConfig(text)
    local f = assert(io.open(DIR .. '/modules/custom/lua/crowds_config.lua', 'w'))
    f:write(text)
    f:close()
end

-- The module reads files by server-relative path: run from DIR
os.remove(DIR .. '/modules/custom/lua/crowds_spots_user.lua')
writeConfig('return { enabled = true, per_zone = 15 }\n')
super = function() return 'super-result' end

local crowdsModule = dofile(DIR .. '/modules/custom/lua/crowds.lua')
check('module loads and registers onGameIn', overrides['xi.player.onGameIn'] ~= nil)
check('!crowd command registered with permission 0', commands.crowd and commands.crowd.cmdprops.permission == 0)

local data = require('modules/custom/lua/crowds_data')
check('data has Southern San d\'Oria (230)', data.zones[230] and #data.zones[230].spots > 30, data.zones[230] and #data.zones[230].spots)
local outfitCount = 0
for _, job in ipairs(data.jobs) do
    for _, list in pairs(data.outfits[job]) do
        for _, look in ipairs(list) do
            outfitCount = outfitCount + 1
            assert(#look == 32 and look:match('^%x+$'), 'bad outfit ' .. look)
        end
    end
end
check('every outfit is 32 hex digits (' .. outfitCount .. ')', outfitCount > 1000)

-- 1. entering the area makes a crowd ---------------------------------------------------------------
local sandy = makeZone(230)
local other = makeZone(999)
local hurami = makePlayer(sandy, 0, 0)
local ret = overrides['xi.player.onGameIn'](hurami, false, true)
check('onGameIn returns the original result', ret == 'super-result')
sandy.players[1] = hurami
advance(3500)
check('15 bots after entering', liveBots(sandy) == 15, liveBots(sandy))
check('no timer was queued before initNpcAi', stats.timerBeforeAi == 0, stats.timerBeforeAi)

-- looks: decode like the server's stringToLook (byte-swapped groups)
local function decode(look)
    local hex = look:sub(3)
    local v = {}
    for i = 0, 9 do
        local g = hex:sub(i * 4 + 1, i * 4 + 4)
        local swapped = tonumber(g:sub(3, 4) .. g:sub(1, 2), 16)
        v[#v + 1] = swapped
    end
    return { size = v[1], face = v[2] & 0xFF, race = v[2] >> 8, head = v[3], body = v[4], main = v[8] }
end
local goodLooks, names, nameOk = true, {}, true
for _, e in pairs(sandy.npcs) do
    local d = decode(e.look)
    if d.size ~= 1 or d.race < 1 or d.race > 8 or d.face > 15 then goodLooks = false end
    if d.body ~= 0 and (d.body & 0xF000) ~= 0x2000 then goodLooks = false end
    if names[e.packetName] or not e.packetName:match('^%u%a+$') or #e.packetName < 3 or #e.packetName > 15 then nameOk = false end
    names[e.packetName] = true
    if e.flags ~= 27 then goodLooks = false end
end
check('looks decode to equipped model, race 1-8, face 0-15, slot nibbles right', goodLooks)
check('names unique, letters only, 3-15 long', nameOk)
-- the garrison look from the server's own data decodes the same way (race 3, face 12)
local g = decode('0x01000C030010262000303A403A5008611B700000')
check('decoder agrees with a garrison look (race 3 face 12 body 0x2026)', g.race == 3 and g.face == 12 and g.body == 0x2026)

-- 2. one hour of town life --------------------------------------------------------------------------
local maxCount, minCount, spotClash = 0, 99, false
local firesBefore = stats.timerFires
local kindsSeen = {}
for minute = 1, 60 do
    advance(60000)
    local c = liveBots(sandy)
    maxCount = math.max(maxCount, c)
    minCount = math.min(minCount, c)
end
local fires = stats.timerFires - firesBefore
check('crowd stays at 15 (min ' .. minCount .. ', max ' .. maxCount .. ')', maxCount <= 15 and minCount >= 13)
check('bots walked (' .. stats.paths .. ' paths)', stats.paths > 30)
check('bots emoted (' .. stats.emotes .. ')', stats.emotes > 10)
check('emotes are motion-only by default', stats.emoteText == 0, stats.emoteText)
local perSecond = fires / 3600
check(string.format('light: %.2f bot decisions per second for 15 bots', perSecond), perSecond < 4)
check('turnover happened (' .. (stats.inserts - 15) .. ' new arrivals in an hour)', stats.inserts > 15 and stats.inserts < 80)

-- no two bots on one spot
local taken = {}
for _, e in pairs(sandy.npcs) do
    if e.packetName and not e.path then
        local key = string.format('%.2f,%.2f', e.x, e.z)
        if taken[key] then spotClash = true end
        taken[key] = true
    end
end
check('no two standing bots on the same spot', not spotClash)

-- 3. talking to one ----------------------------------------------------------------------------------
local anyBot
for _, e in pairs(sandy.npcs) do anyBot = e break end
local textBefore = stats.emoteText
anyBot.onTrigger(hurami, anyBot)
check('touching a bot makes it wave/bow at you (with chat text)', stats.emoteText == textBefore + 1)

-- 4. commands ----------------------------------------------------------------------------------------
commands.crowd.onTrigger(hurami, 'count', '5')
advance(40000)
check('!crowd count 5 -> 5 bots within 40 s', liveBots(sandy) == 5, liveBots(sandy))
commands.crowd.onTrigger(hurami, 'count', '25')
check('!crowd count 25 -> 25 at once', liveBots(sandy) == 25, liveBots(sandy))
commands.crowd.onTrigger(hurami, 'count', '99')
check('!crowd count 99 is capped at 40 (or the free spots)', liveBots(sandy) <= 40)
commands.crowd.onTrigger(hurami, 'off')
check('!crowd off removes everyone', liveBots(sandy) == 0)
commands.crowd.onTrigger(hurami, 'count', '15')
check('no spawning while off', liveBots(sandy) == 0)
commands.crowd.onTrigger(hurami, 'on')
check('!crowd on brings them back', liveBots(sandy) == 15, liveBots(sandy))
hurami.said = {}
commands.crowd.onTrigger(hurami)
check('!crowd status answers', hurami.said[1] and hurami.said[1]:find('ON, size 15') ~= nil, hurami.said[1])

-- mark / reload / unmark
hurami.x, hurami.y, hurami.z, hurami.rot = 1.5, 1.7, -20, 64
local spotsBefore = #data.zones[230].spots
commands.crowd.onTrigger(hurami, 'mark', 'rest')
local f = io.open(DIR .. '/modules/custom/lua/crowds_spots_user.lua')
local saved = f and f:read('a'); if f then f:close() end
check('!crowd mark writes the spots file', saved and saved:find("kind = 'rest', x = 1.500") ~= nil)
hurami.said = {}
commands.crowd.onTrigger(hurami, 'reload')
commands.crowd.onTrigger(hurami)
check('reload uses the marked spot', hurami.said[2] and hurami.said[2]:find((spotsBefore + 1) .. ' spots (1 marked', 1, true) ~= nil, hurami.said[2])
commands.crowd.onTrigger(hurami, 'unmark')
f = io.open(DIR .. '/modules/custom/lua/crowds_spots_user.lua'); saved = f:read('a'); f:close()
check('!crowd unmark removes it', not saved:find("kind = 'rest'"))
commands.crowd.onTrigger(hurami, 'mark', 'sofa')
check('bad mark kind is refused', hurami.said[#hurami.said]:find('Usage') ~= nil)

-- 5. leaving the area ----------------------------------------------------------------------------------
zoneOut(hurami)
advance(4 * 60000)
check('crowd still there 4 minutes after you left', liveBots(sandy) == 15, liveBots(sandy))
advance(2 * 60000)
check('crowd removed after 5 minutes empty', liveBots(sandy) == 0, liveBots(sandy))
local pending = 0
for _, t in ipairs(timers) do if not t.entity.dead and t.entity.kind == 'npc' then pending = pending + 1 end end
check('no timers left running for removed bots', pending == 0, pending)
zoneIn(hurami, sandy)
advance(3500)
check('coming back makes a new crowd', liveBots(sandy) == 15, liveBots(sandy))

-- 6. an area without crowd data ------------------------------------------------------------------------
local p2 = makePlayer(other)
zoneIn(p2, other)
advance(5000)
check('no crowd in an area without data', liveBots(other) == 0)

-- 7. launcher switch off ---------------------------------------------------------------------------------
writeConfig('return { enabled = false, per_zone = 15 }\n')
commands.crowd.onTrigger(hurami, 'reload')
check('launcher off + reload -> nobody', liveBots(sandy) == 0)
writeConfig('return { enabled = true, per_zone = 8 }\n')
commands.crowd.onTrigger(hurami, 'reload')
check('launcher size 8 + reload -> 8', liveBots(sandy) == 8, liveBots(sandy))
os.remove(DIR .. '/modules/custom/lua/crowds_config.lua')
commands.crowd.onTrigger(hurami, 'reload')
check('no config file -> defaults (on, 30)', liveBots(sandy) == 30, liveBots(sandy))

-- 8. long soak with leave/return --------------------------------------------------------------------------
local okSoak, err = pcall(function()
    for i = 1, 6 do
        advance(20 * 60000)
        if i % 2 == 0 then zoneOut(hurami) else zoneIn(hurami, sandy) end
    end
end)
check('2-hour soak with leaving and returning runs without errors', okSoak, err)

-- 9. other kinds of area: a smaller town and an outpost get a share of the crowd size -------------------
zoneIn(hurami, sandy) -- the soak ended with you away
writeConfig('return { enabled = true, per_zone = 30 }\n')
commands.crowd.onTrigger(hurami, 'reload')
check('town at size 30 -> 30', liveBots(sandy) == 30, liveBots(sandy))
local selbina, valkurm = makeZone(248), makeZone(103)
local p3 = setmetatable({ kind = 'pc', id = 3, zone = selbina, x = 0, y = 0, z = 0, rot = 0 }, getmetatable(hurami))
local p4 = setmetatable({ kind = 'pc', id = 4, zone = valkurm, x = 0, y = 0, z = 0, rot = 0 }, getmetatable(hurami))
zoneIn(p3, selbina)
zoneIn(p4, valkurm)
advance(4000)
check('small town (Selbina) -> 60% = 18', liveBots(selbina) == 18, liveBots(selbina))
check('outpost (Valkurm Dunes) -> 25% = 8', liveBots(valkurm) == 8, liveBots(valkurm))
local farWalks = 0
local okAreas, errAreas = pcall(function() advance(30 * 60000) end)
check('30 minutes in three areas at once without errors', okAreas, errAreas)
check('areas keep their sizes', liveBots(sandy) == 30 and liveBots(selbina) == 18 and liveBots(valkurm) == 8,
    liveBots(sandy) .. '/' .. liveBots(selbina) .. '/' .. liveBots(valkurm))
check(string.format('most walks go to a nearby spot (%d of %d within 80 yalms)', stats.walkNear, stats.walkTotal),
    stats.walkNear / stats.walkTotal > 0.8)
-- every area in the data loads and spawns
local allOk, bad = true, ''
for zid in pairs(data.zones) do
    if not zones[zid] then
        local z = makeZone(zid)
        local pp = setmetatable({ kind = 'pc', id = 100 + zid, zone = z, x = 0, y = 0, z = 0, rot = 0 }, getmetatable(hurami))
        zoneIn(pp, z)
    end
end
advance(5000)
for zid in pairs(data.zones) do
    if liveBots(zones[zid]) < 1 then allOk = false; bad = bad .. ' ' .. zid end
end
check('every area in the data gets its crowd (' .. #(function() local t = {} for k in pairs(data.zones) do t[#t + 1] = k end return t end)() .. ' areas)', allOk, bad)

-- 10. chat (phase 2) -------------------------------------------------------------------------------
local function heardOf(p, kind)
    local out = {}
    for _, h in ipairs(p.heard or {}) do
        if h.kind == kind then out[#out + 1] = h end
    end
    return out
end
local function lineOk(h)
    return h.text and #h.text > 0 and #h.text <= 110 and not h.text:find('[{}]') and not h.text:find('[^\32-\126]')
        and h.name and h.name:match('^%a+%d*$')
end
-- a quiet world: only Jeuno with one player in the middle of the crowd
for _, p in pairs(zones) do p.players = {} end
local jeuno = makeZone(245)
local pj = setmetatable({ kind = 'pc', id = 50, name = 'Hurami', zone = jeuno, x = 0, y = 0, z = 0, rot = 0 }, getmetatable(hurami))
writeConfig("return { enabled = true, per_zone = 30, chat = true, chat_amount = 'normal', chat_ai = false }\n")
commands.crowd.onTrigger(pj, 'reload')
zoneIn(pj, jeuno)
advance(4000)
-- stand next to a resting bot so say chat can be heard
local anyJ
for _, e in pairs(jeuno.npcs) do if e.packetName then anyJ = e break end end
pj.x, pj.z = anyJ.x + 2, anyJ.z
pj.heard = {}
advance(30 * 60000)
local shouts, says = heardOf(pj, 1), heardOf(pj, 0)
check(string.format('Jeuno, normal: %d shouts in 30 min (about one per 30-45 s)', #shouts), #shouts >= 30 and #shouts <= 75)
local allOk, badLine = true, nil
for _, h in ipairs(shouts) do if not lineOk(h) then allOk = false; badLine = h.text .. ' / ' .. tostring(h.name) end end
for _, h in ipairs(says) do if not lineOk(h) then allOk = false; badLine = h.text .. ' / ' .. tostring(h.name) end end
check('every line: filled in, ASCII, short, has a speaker name', allOk, badLine)
check(string.format('say chatter heard while standing near bots (%d)', #says), #says >= 5)
-- LFP shouts from bots you can see carry that bot's own job, and advanced jobs are 30+
local byName = {}
for _, bot in pairs(crowdsModule.crowds[245].bots) do byName[bot.name] = bot end
local lfpChecked, lfpOk, lfpBad = 0, true, nil
for _, h in ipairs(shouts) do
    local bot = byName[h.name]
    if bot and h.text:find('LFP') and not h.text:find('merits') then
        lfpChecked = lfpChecked + 1
        if not h.text:find(bot.job, 1, true) then lfpOk = false; lfpBad = h.text .. ' from ' .. bot.job end
        local lvl = tonumber(h.text:match(bot.job .. ' ?(%d+)'))
        if lvl and ({ WAR = 1, MNK = 1, WHM = 1, BLM = 1, RDM = 1, THF = 1 })[bot.job] == nil and lvl < 30 then lfpOk = false; lfpBad = h.text end
    end
end
check(string.format('LFP shouts name the speaker\'s own job and a fitting level (%d checked)', lfpChecked), lfpOk and lfpChecked > 0, lfpBad)
local everInJeuno = {}
for _, e in pairs(entities) do if e.zone == jeuno and e.packetName then everInJeuno[e.packetName] = true end end
local ghosts = 0
for _, h in ipairs(shouts) do if not everInJeuno[h.name] then ghosts = ghosts + 1 end end
check(string.format('some Jeuno shouts come from people elsewhere in town (%d of %d)', ghosts, #shouts), ghosts > 0 and ghosts < #shouts * 0.45)
local sample = {}
for i = 1, math.min(6, #shouts) do sample[#sample + 1] = shouts[i].name .. ': ' .. shouts[i].text end
print('     sample: ' .. table.concat(sample, ' | '))

-- far away: no say, shouts still
pj.x, pj.z = 4000, 4000
pj.heard = {}
advance(10 * 60000)
check('far from everyone: no say chatter, shouts still heard', #heardOf(pj, 0) == 0 and #heardOf(pj, 1) > 5, #heardOf(pj, 0) .. '/' .. #heardOf(pj, 1))

-- amount
commands.crowd.onTrigger(pj, 'chat', 'busy')
pj.heard = {}
advance(30 * 60000)
local busy = #heardOf(pj, 1)
commands.crowd.onTrigger(pj, 'chat', 'quiet')
pj.heard = {}
advance(30 * 60000)
local quiet = #heardOf(pj, 1)
check(string.format('busy %d > normal %d > quiet %d shouts per 30 min', busy, #shouts, quiet), busy > #shouts and #shouts > quiet)
commands.crowd.onTrigger(pj, 'chat', 'off')
pj.heard = {}
advance(10 * 60000)
check('!crowd chat off: silence', #heardOf(pj, 1) == 0 and #heardOf(pj, 0) == 0)
commands.crowd.onTrigger(pj, 'chat', 'normal')

-- a nation city: fewer shouts
local bastok = makeZone(235)
local pb = setmetatable({ kind = 'pc', id = 51, name = 'Hurami', zone = bastok, x = 4000, y = 0, z = 4000, rot = 0 }, getmetatable(hurami))
zoneIn(pb, bastok)
advance(4000)
pb.heard = {}
advance(30 * 60000)
local bs = #heardOf(pb, 1)
check(string.format('Bastok Markets: %d shouts in 30 min (one per 1-2 min)', bs), bs >= 12 and bs <= 35)

-- an outpost: no shouts, camp chatter when close
local valk = zones[103]
local pv = setmetatable({ kind = 'pc', id = 52, name = 'Hurami', zone = valk, x = 0, y = 0, z = 0, rot = 0 }, getmetatable(hurami))
zoneIn(pv, valk)
advance(4000)
local anyV
for _, e in pairs(valk.npcs) do if e.packetName then anyV = e break end end
pv.x, pv.z = anyV.x + 1, anyV.z
pv.heard = {}
advance(30 * 60000)
check(string.format('outpost: no shouts (%d), camp chatter nearby (%d)', #heardOf(pv, 1), #heardOf(pv, 0)), #heardOf(pv, 1) == 0 and #heardOf(pv, 0) >= 5)

-- touching a bot: it may answer in say
for _, e in pairs(jeuno.npcs) do if e.packetName and crowdsModule.crowds[245].bots[e.id] then anyJ = e break end end
pj.x, pj.z = anyJ.x + 2, anyJ.z
local answered = 0
for _ = 1, 20 do
    pj.heard = {}
    anyJ.onTrigger(pj, anyJ)
    if #heardOf(pj, 0) > 0 then answered = answered + 1 end
end
check(string.format('touching a bot: it answers in say most times (%d/20)', answered), answered >= 6 and answered <= 20)

-- AI pool mixed in when on
local f = assert(io.open(DIR .. '/modules/custom/lua/crowds_chat_ai.lua', 'w'))
f:write("return { say = { 'AILINE say one', 'AILINE say two' }, pairs = { { 'AILINE a', 'AILINE b' } }, outpost = { 'AILINE camp' }, react = { 'AILINE hi' }, shout = { 'AILINE shout' } }\n")
f:close()
commands.crowd.onTrigger(pj, 'chat', 'aion')
pj.said = {}
commands.crowd.onTrigger(pj, 'chat', 'test')
check('!crowd chat test: shouts and a say, and reports the AI pool', pj.said[#pj.said]:find('say 2, pairs 1, outpost 1, react 1, shout 1') ~= nil, pj.said[#pj.said])
pj.heard = {}
advance(30 * 60000)
local aiSeen, tplSeen = 0, 0
for _, h in ipairs(heardOf(pj, 0)) do if h.text:find('AILINE') then aiSeen = aiSeen + 1 else tplSeen = tplSeen + 1 end end
check(string.format('AI chatter on: say mixes AI (%d) and template (%d) lines', aiSeen, tplSeen), aiSeen > 0 and tplSeen > 0)
commands.crowd.onTrigger(pj, 'chat', 'aioff')
pj.heard = {}
advance(30 * 60000)
aiSeen = 0
for _, h in ipairs(pj.heard) do if h.text:find('AILINE') then aiSeen = aiSeen + 1 end end
check('AI chatter off: no AI lines', aiSeen == 0, aiSeen)
os.remove(DIR .. '/modules/custom/lua/crowds_chat_ai.lua')
local okNoPool = pcall(function() commands.crowd.onTrigger(pj, 'chat', 'aion'); advance(10 * 60000) end)
check('no AI pool file: chat goes on with templates', okNoPool and #heardOf(pj, 1) > 0)

-- bot players living in an area take some of the crowd's places (bots.lua), and do not count as you
pj.said = {}
xi.bots = { countInZone = function() return 6 end }
commands.crowd.onTrigger(pj)
local withBots = tonumber((pj.said[#pj.said] or ''):match('crowd of (%d+)'))
xi.bots = nil
pj.said = {}
commands.crowd.onTrigger(pj)
local without = tonumber((pj.said[#pj.said] or ''):match('crowd of (%d+)'))
check('6 bots in the area: the crowd is 6 smaller', withBots and without and withBots == without - 6, tostring(withBots) .. ' vs ' .. tostring(without))
BotIsBot = function(id) return id == pj:getID() end
local onlyReal = xi.crowds.realPlayers({ getPlayers = function() return { pj } end })
BotIsBot = nil
check('a bot is not a "player" for the crowds', #onlyReal == 0)
xi.crowds.sayLine({ name = 'Aldric', job = 'WAR', lvl = 1 }, 230)
check('bots can use the crowds\' names and small talk', type(xi.crowds.makeName(1, {})) == 'string' and type(xi.crowds.sayLine({ name = 'Aldric', job = 'WAR', lvl = 1 }, 230)) == 'string')

-- the town chatter spoken by bot players instead of crowd NPCs
local spoken = {}
local function fakeBot(name, job, lvl, x, z)
    return { getName = function() return name end, getMainJob = function() return job end, getMainLvl = function() return lvl end,
             getPos = function() return { x = x, y = 0, z = z } end, isAlive = function() return true end,
             timer = function(self, ms, fn) fn(self) end }
end
local hp = pj:getPos()
local speakers = { fakeBot('Botone', 1, 12, hp.x + 2, hp.z), fakeBot('Bottwo', 3, 14, hp.x + 3, hp.z + 1) }
for _ = 1, 400 do
    advance(1000)
    xi.crowds.botChatter(pj:getZoneID(), speakers, { pj }, function(b, kind, text) spoken[#spoken + 1] = { b:getName(), kind, text } end)
end
local shouts, says = 0, 0
for _, sp in ipairs(spoken) do if sp[2] == 1 then shouts = shouts + 1 else says = says + 1 end end
check('bots shout in town (LFP / selling ...) with their own name', shouts >= 2, shouts)
check('bots near you say small talk', says >= 2, says)
local lvlOk = true
for _, sp in ipairs(spoken) do if sp[1] == 'Botone' and sp[3]:find('WAR') and sp[3]:find('75') then lvlOk = false end end
check('their shouts use their own job and level', lvlOk)

putBack()
print(string.format('\n%d passed, %d failed', passes, failures))
os.exit(failures == 0 and 0 or 1)
