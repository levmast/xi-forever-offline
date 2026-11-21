-- Tetra Master: card traders, buying, selling, the 200-card cap, monster and casket drops, with a pretend world.
-- Run from the SERVER folder (the shop file is written to modules/custom/lua/tetramaster_shops.lua there):
--   cd <server>; luajit <path>/test_shops_drops.lua
package.path = './?.lua;' .. package.path

local overrides = {}
package.preload['modules/module_utils'] = function()
    Module = { new = function(_, n) return { name = n, addOverride = function(_, path, fn) overrides[path] = fn end } end }
    return true
end

local npcs, nextNpc = {}, 17000000
local function newZone(id, name)
    local z = { id = id, name = name }
    function z:getID() return self.id end
    function z:getName() return self.name end
    function z:insertDynamicEntity(t)
        nextNpc = nextNpc + 1
        local n = { t = t, id = nextNpc, zoneId = self.id, status = 0 }
        function n:getID() return self.id end
        function n:getZoneID() return self.zoneId end
        function n:setStatus(s) self.status = s end
        npcs[n.id] = n
        return n
    end
    return z
end

local commands = {}
xi = {
    module = { registerCommand = function(name, c) commands[name] = c end },
    objType = { NPC = 2 }, status = { DISAPPEAR = 3, NORMAL = 0 },
    mobFamily = { GOBLIN = 58, BEHEMOTH = 39, TONBERRY = 71, SLIME = 8 },
    job = { MON = 23 },
}
GetNPCByID = function(id) return npcs[id] end

local SHOPS = 'modules/custom/lua/tetramaster_shops.lua'
os.remove(SHOPS)
require('modules/custom/lua/tetramaster')
local D = require('modules/custom/lua/tetramaster_data')

local failures, checks = 0, 0
local function check(ok, msg) checks = checks + 1; if not ok then failures = failures + 1; print('FAIL: ' .. msg) end end

local zone = newZone(230, 'Southern_San_dOria')
local function newPlayer()
    local p = { vars = {}, lv = {}, lines = {}, gil = 0, pos = { x = 10, y = 0, z = 20, rot = 64 }, dist = 2, job = 1, lvl = 50 }
    function p:getID() return 1 end
    function p:getCharVar(k) return self.vars[k] or 0 end
    function p:setCharVar(k, v) self.vars[k] = v end
    function p:getLocalVar(k) return self.lv[k] or 0 end
    function p:setLocalVar(k, v) self.lv[k] = v end
    function p:printToPlayer(t) self.lines[#self.lines + 1] = t end
    function p:addGil(n) self.gil = self.gil + n end
    function p:delGil(n) self.gil = self.gil - n end
    function p:getGil() return self.gil end
    function p:getPos() return self.pos end
    function p:getZone() return zone end
    function p:getZoneID() return zone:getID() end
    function p:checkDistance() return self.dist end
    function p:isPC() return true end
    function p:getMainJob() return self.job end
    function p:getMainLvl() return self.lvl end
    return p
end
local function has(p, pat) for _, l in ipairs(p.lines) do if l:find(pat) then return true end end return false end

local p = newPlayer()
-- placing a trader writes the file and spawns it
commands.tmshop.onTrigger(p, 'add', 'Lion_Springs_card_trader')
local f = io.open(SHOPS, 'r'); local txt = f and f:read('*a') or ''; if f then f:close() end
check(txt:find('Southern_San_dOria', 1, true) and txt:find('Lion Springs card trader', 1, true), 'shop file written')
local loaded = dofile(SHOPS)
check(#loaded == 1 and loaded[1].n == 1 and loaded[1].rot == 64, 'shop file reads back')
local npc = nil
for _, n in pairs(npcs) do npc = n end
check(npc ~= nil and npc.t.packetName == 'Lion Springs card trader', 'trader spawned')

-- buying needs talking to the trader first
p.gil = 100000
commands.tm.onTrigger(p, 'buy', '1')
check(p.vars.TM_N == nil, 'no buying before talking to the trader')
npc.t.onTrigger(p, npc)
check(has(p, '^tetramaster:shop|1|'), 'shop list sent')
local stockLines = 0
for _, l in ipairs(p.lines) do if l:find('^tetramaster:stock|') then stockLines = stockLines + 1 end end
check(stockLines == 30, 'shop shows 30 cards, got ' .. stockLines)
local first = D.shopStock(1)[1]
local before = p.gil
commands.tm.onTrigger(p, 'buy', '1')
check(p.vars.TM_N == 1 and before - p.gil == D.price(first), 'bought one card at its price')
check((p.vars.TM_A1 % 256) == first, 'the bought card is the one in the list')
-- too far away
p.dist = 20
commands.tm.onTrigger(p, 'buy', '1')
check(p.vars.TM_N == 1, 'no buying from across the room')
p.dist = 2
-- not enough gil
p.gil = 10
commands.tm.onTrigger(p, 'buy', '2')
check(p.vars.TM_N == 1, 'no buying without the gil')
p.gil = 10000000
-- fill to the cap
for k = 1, 210 do commands.tm.onTrigger(p, 'buy', tostring((k % 30) + 1)) end
check(p.vars.TM_N == D.MAX_CARDS, 'collection stops at ' .. D.MAX_CARDS .. ', has ' .. tostring(p.vars.TM_N))
-- selling: the last card moves into the sold card's place, the deck follows it
commands.tm.onTrigger(p, 'deck', '200', '2', '3', '4', '5')
local lastA = p.vars.TM_A200
local g0 = p.gil
commands.tm.onTrigger(p, 'sell', '1')
check(p.vars.TM_N == 199 and p.vars.TM_A1 == lastA and (p.vars.TM_A200 or 0) == 0, 'sell: last card moved into place')
check(p.vars.TM_D1 == 1, 'deck follows the moved card')
check(p.gil - g0 == D.SELL[D.tier(lastA % 256 == 0 and 1 or (p.vars.TM_A1 % 256))] or p.gil > g0, 'paid for the sale')
commands.tm.onTrigger(p, 'sell', '2')
check(p.vars.TM_D2 == 0, 'a sold deck card leaves the deck')

-- removing the trader
commands.tmshop.onTrigger(p, 'remove')
check(#dofile(SHOPS) == 0 and npc.status == 3, 'trader removed')

-- zone start spawns saved traders: write a file, load the module again
local f2 = io.open(SHOPS, 'w')
f2:write("return { { n = 4, zone = 'Bastok_Markets', x = 1, y = 2, z = 3, rot = 0, name = 'Card Trader' } }\n")
f2:close()
package.loaded['modules/custom/lua/tetramaster'] = nil
overrides = {}
require('modules/custom/lua/tetramaster')
local init = overrides['xi.zones.Bastok_Markets.Zone.onInitialize']
check(init ~= nil, 'zone start hook for the saved trader')
super = function() end
local count = 0
for _ in pairs(npcs) do count = count + 1 end
init(newZone(235, 'Bastok_Markets'))
local count2 = 0
for _ in pairs(npcs) do count2 = count2 + 1 end
check(count2 == count + 1, 'saved trader spawned at zone start')

-- monster drops
local death = overrides['xi.mob.onMobDeathEx']
local function mob(name, family, nm, level)
    local m = { lv = {} }
    function m:getName() return name end
    function m:getFamily() return family end
    function m:isNM() return nm end
    function m:getMainLvl() return level end
    function m:getMaster() return nil end
    function m:getLocalVar(k) return self.lv[k] or 0 end
    function m:setLocalVar(k, v) self.lv[k] = v end
    return m
end
math.randomseed(9)
local q = newPlayer()
local found = 0
for k = 1, 5000 do
    local mb = mob('Goblin_Thug', 58, false, 20)
    death(mb, q, true, false)
    death(mb, q, false, false) -- the same monster again (another party member): no second roll
end
local n = q.vars.TM_N or 0
check(n > 50 and n < 160, 'goblins: about 1 in 50 kills drops a card, got ' .. n .. ' in 5000')
local onlyGoblin = true
for i = 1, n do if q.vars['TM_A' .. i] % 256 ~= 1 then onlyGoblin = false end end
check(onlyGoblin, 'goblins only drop the Goblin card')
-- a family without cards drops nothing
local r = newPlayer()
for k = 1, 2000 do death(mob('Slime', 8, false, 20), r, true, false) end
check((r.vars.TM_N or 0) == 0, 'slimes drop no cards')
-- low-level Tonberries never drop the Rare+ ones; NMs can drop Epic but never Legendary
local t = newPlayer()
for k = 1, 3000 do death(mob('Tonberry_Stalker', 71, false, 20), t, true, false) end
for i = 1, (t.vars.TM_N or 0) do check(D.tier(t.vars['TM_A' .. i] % 256) <= 2, 'low-level drop tier') end
local u = newPlayer()
for k = 1, 400 do death(mob('Some_Tonberry_NM', 71, true, 60), u, true, false) end
local maxTier = 0
for i = 1, (u.vars.TM_N or 0) do maxTier = math.max(maxTier, D.tier(u.vars['TM_A' .. i] % 256)) end
check((u.vars.TM_N or 0) > 20 and maxTier <= 4, 'NM drops up to Epic, got ' .. tostring(u.vars.TM_N) .. ' cards, tier ' .. maxTier)
-- named fight
local v = newPlayer()
for k = 1, 300 do death(mob('King_Behemoth', 39, true, 85), v, true, false) end
local kb = 0
for i = 1, (v.vars.TM_N or 0) do if v.vars['TM_A' .. i] % 256 == 237 then kb = kb + 1 end end
check(kb > 8 and kb < 45 and kb == v.vars.TM_N, 'King Behemoth drops Behemoth King about 8%, got ' .. kb)
-- beastmaster pets and monstrosity players get nothing
local w = newPlayer(); w.job = 23
for k = 1, 500 do death(mob('Goblin_Thug', 58, false, 20), w, true, false) end
check((w.vars.TM_N or 0) == 0, 'no cards for monstrosity')

-- the launcher's sliders (settings/main.lua TM_*)
xi.settings = { main = { TM_CARD_DROP_RATE = 0 } }
local z = newPlayer()
for k = 1, 3000 do death(mob('Goblin_Thug', 58, false, 20), z, true, false) end
check((z.vars.TM_N or 0) == 0, 'card drops at 0x: none')
xi.settings.main.TM_CARD_DROP_RATE = 3
local y = newPlayer()
for k = 1, 3000 do death(mob('Goblin_Thug', 58, false, 20), y, true, false) end
check((y.vars.TM_N or 0) > 130 and (y.vars.TM_N or 0) < 200, 'card drops at 3x: about 180 in 3000, got ' .. tostring(y.vars.TM_N))
xi.settings.main.TM_CARD_DROP_RATE = nil

-- caskets
local open = overrides['xi.caskets.onTrigger']
local c = newPlayer(); c.lvl = 20
local got = 0
for k = 1, 1000 do
    local box = { lv = { ['[caskets]SPAWNSTATUS'] = 2 } }
    function box:getLocalVar(k2) return self.lv[k2] or 0 end
    function box:setLocalVar(k2, v2) self.lv[k2] = v2 end
    open(c, box)
    open(c, box) -- touching it again gives nothing more
end
got = c.vars.TM_N or 0
check(got > 100 and got < 200, 'caskets: about 15% give a card, got ' .. got .. ' in 1000')
local tiers = { 0, 0, 0, 0, 0 }
for i = 1, got do local id = c.vars['TM_A' .. i] % 256; tiers[D.tier(id)] = tiers[D.tier(id)] + 1 end
check(tiers[4] == 0 and tiers[5] == 0, 'no Epic or Legendary casket cards below level 50')
local closed = newPlayer()
for k = 1, 300 do
    local box = { lv = { ['[caskets]SPAWNSTATUS'] = 1 } }
    function box:getLocalVar(k2) return self.lv[k2] or 0 end
    function box:setLocalVar(k2, v2) self.lv[k2] = v2 end
    open(closed, box)
end
check((closed.vars.TM_N or 0) == 0, 'a closed casket gives nothing')
xi.settings = { main = { TM_CASKET_CARD_RATE = 0 } }
local nobox = newPlayer()
for k = 1, 500 do
    local box = { lv = { ['[caskets]SPAWNSTATUS'] = 2 } }
    function box:getLocalVar(k2) return self.lv[k2] or 0 end
    function box:setLocalVar(k2, v2) self.lv[k2] = v2 end
    open(nobox, box)
end
check((nobox.vars.TM_N or 0) == 0, 'casket cards at 0x: none')
xi.settings = nil

-- Luto Mewrilah in Upper Jeuno becomes the Jeuno card trader
super = function() return 'original' end
local lutoInit = overrides['xi.zones.Upper_Jeuno.Zone.onInitialize']
check(lutoInit ~= nil, 'Upper Jeuno hook')
local jeuno = newZone(244, 'Upper_Jeuno')
local luto = { id = 17776999, status = 3 }
function luto:getID() return self.id end
function luto:getZoneID() return 244 end
function luto:setStatus(st) self.status = st end
npcs[luto.id] = luto
function jeuno:queryEntitiesByName(name) if name == 'Luto_Mewrilah' then return { luto } end return {} end
lutoInit(jeuno)
check(luto.status == 0, 'Luto shown')
local otherCalls = 0
InteractionGlobal = { onTrigger = function() otherCalls = otherCalls + 1; return 7 end }
overrides['xi.server.onServerStart']()
overrides['xi.server.onServerStart']() -- wrapped only once
local jp = newPlayer()
jp.gil = 5000
function jp:getZoneID() return 244 end
local ret = InteractionGlobal.onTrigger(jp, luto, nil)
check(ret == 0 and has(jp, '^tetramaster:shop|100|Luto Mewrilah|') and has(jp, 'starrrter deck'), 'talking to Luto opens her shop')
-- first visit: a free starter deck of 5 different Common cards, made the deck
check(jp.vars.TM_N == 5 and jp.vars.TM_STARTER == 1, 'starter deck given once')
local names = {}
for i = 1, 5 do
    local id = jp.vars['TM_A' .. i] % 256
    check(D.tier(id) == 1 and not names[id], 'starter card ' .. i .. ' is a different Common card')
    names[id] = true
    check(jp.vars['TM_D' .. i] == i, 'starter card ' .. i .. ' is in the deck')
end
jp.lines = {}
InteractionGlobal.onTrigger(jp, luto, nil)
check(jp.vars.TM_N == 5 and has(jp, 'Tetrrra') and not has(jp, 'starrrter deck'), 'second visit: no second starter deck')
-- a full collection: no starter deck yet, and she will still give it later
local full = newPlayer(); function full:getZoneID() return 244 end
full.vars.TM_N = D.MAX_CARDS - 2
InteractionGlobal.onTrigger(full, luto, nil)
check(full.vars.TM_N == D.MAX_CARDS - 2 and (full.vars.TM_STARTER or 0) == 0, 'full collection: starter deck waits')
jp.vars = {}
local someone = { getID = function() return 1234 end }
check(InteractionGlobal.onTrigger(jp, someone, nil) == 7 and otherCalls == 1, 'other NPCs untouched')
commands.tm.onTrigger(jp, 'buy', '1')
check(jp.vars.TM_N == 1 and (jp.vars.TM_A1 % 256) == D.shopStock(100)[1], 'buying from Luto')
-- a zone without her: she is made at her spot
local jeuno2 = newZone(244, 'Upper_Jeuno')
function jeuno2:queryEntitiesByName() return {} end
local made = nil
local before2 = nextNpc
lutoInit(jeuno2)
check(nextNpc == before2 + 1 and npcs[nextNpc].t.packetName == 'Luto Mewrilah', 'Luto made when missing')

xi.settings = { main = {} }
lutoInit(jeuno) -- the zone's own Luto again
xi.settings.main.TM_PRICE_RATE = 2
local pp = newPlayer(); function pp:getZoneID() return 244 end
pp.gil = 100000
pp.vars.TM_STARTER = 1
InteractionGlobal.onTrigger(pp, luto, nil)
local listed = nil
for _, l in ipairs(pp.lines) do local pr = l:match('^tetramaster:stock|1|%d+|[^|]+|(%d+)|') if pr then listed = tonumber(pr) end end
commands.tm.onTrigger(pp, 'buy', '1')
check(listed == 2 * D.price(D.shopStock(100)[1]) and 100000 - pp.gil == listed, 'prices at 2x: listed and charged double')
xi.settings.main.TM_PRICE_RATE = nil
xi.settings = nil

os.remove(SHOPS)
print(string.format('shops and drops: casket tiers %d/%d/%d/%d/%d; %d checks, %d failed', tiers[1], tiers[2], tiers[3], tiers[4], tiers[5], checks, failures))
os.exit(failures == 0 and 0 or 1)
