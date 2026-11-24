-- Tests for the low-level shout fix (crowds_chat.lua) and real bazaar trades (bots_trade.lua).
-- Run from the server folder:  texlua <kit>\crowds\bots\test_trade.lua
package.path = './?.lua;' .. package.path
local pass, fail = 0, 0
local function check(name, ok, info)
    if ok then
        pass = pass + 1
        print('ok   ' .. name)
    else
        fail = fail + 1
        print('FAIL ' .. name .. (info and ('  -- ' .. tostring(info)) or ''))
    end
end

xi = { settings = { main = { AH_PRICE_RATE = 1 } } }
local clock = 1000000
os.time = function() return clock end

-----------------------------------
-- fake world
-----------------------------------
local bazaar = {}   -- [charId] = { [itemId] = { price, qty } }
local bags = {}     -- [charId] = { [itemId] = qty }
local told, moved, said = {}, {}, {}
local function newEnt(id, name, lvl, x, zone)
    local e = { id = id, name = name, lvl = lvl, gil = 200000, x = x or 0, z = 0, zone = zone or 245, timers = {} }
    function e:getID() return self.id end
    function e:getName() return self.name end
    function e:getMainLvl() return self.lvl end
    function e:getMainJob() return 1 end
    function e:getGil() return self.gil end
    function e:getFreeSlotsCount() return 20 end
    function e:addItem(i, q) bags[self.id] = bags[self.id] or {}; bags[self.id][i] = (bags[self.id][i] or 0) + (q or 1) end
    function e:getPos() return { x = self.x, y = 0, z = self.z } end
    function e:getZoneID() return self.zone end
    function e:getZone() return { getName = function() return 'Lower_Jeuno' end } end
    function e:timer(ms, fn) fn(self) end
    function e:isAlive() return true end
    return e
end

local ents = {}
BotIsOnline = function(id) return ents[id] ~= nil end
BotTell = function(id, to, text) told[#told + 1] = { id = id, to = to, text = text } end
BotMoveTo = function(id, x, y, z) moved[#moved + 1] = id; local e = ents[id]; e.x, e.z = x, z end
BotBazaarSet = function(id, item, price)
    local have = bags[id] and bags[id][item]
    if not have then return false end
    bazaar[id] = bazaar[id] or {}
    if price == 0 then bazaar[id][item] = nil else bazaar[id][item] = { price, have } end
    return true
end
BotBazaarItems = function(id)
    local out = {}
    for item, v in pairs(bazaar[id] or {}) do out[#out + 1] = { id = item, price = v[1], qty = v[2] } end
    return out
end
BotBazaarBuy = function(id, seller, item, maxPrice, qty)
    local v = bazaar[seller] and bazaar[seller][item]
    if not v or v[1] > maxPrice then return 0 end
    bazaar[seller][item] = nil
    ents[id].gil = ents[id].gil - v[1]
    ents[seller].gil = ents[seller].gil + v[1]
    return v[1]
end
GetPlayerByName = function(n) for _, e in pairs(ents) do if e.name == n then return e end end end

-- stand-in bots_craft: fair prices, and what each bot could sell
local PRICES = { [13656] = 400000, [4112] = 300, [1132] = 9000, [705] = 150 }
package.loaded['modules/custom/lua/bots_craft'] = {
    priceOf = function(id) return PRICES[id] end,
    sellables = function(bot)
        local out = {}
        for item, q in pairs(bags[bot:getID()] or {}) do
            if not (bazaar[bot:getID()] and bazaar[bot:getID()][item]) then out[#out + 1] = { id = item, qty = q } end
        end
        return out
    end,
}
package.loaded['modules/custom/lua/bots_trade_names'] = { [13656] = 'Errant Cape', [4112] = 'Potion', [1132] = 'Raxa', [705] = 'Arrowwood Lumber' }
package.loaded['modules/custom/lua/crowds_data'] = { sell = { { 'Raxa', 9000, 1 }, { 'Potion', 300, 1 } } }

local trade = dofile('modules/custom/lua/bots_trade.lua')
package.loaded['modules/custom/lua/bots_trade'] = trade
check('trade module sees the bazaar functions', trade.available())

-----------------------------------
-- 1. shouts that fit the speaker's level
-----------------------------------
local chat = dofile('modules/custom/lua/crowds_chat.lua')
chat.setup({ cfg = { chat = true, chatAmount = 'normal', chatAi = false }, data = { sell = { { 'Potion', 300, 1 } }, zones = {} },
    dist2 = function(a, b, c, d) return (a - c) ^ 2 + (b - d) ^ 2 end })

local bad, sample = 0, nil
for lvl = 1, 11 do
    for _ = 1, 60 do
        for _, g in ipairs({ 'lfp', 'lfp_heal', 'lfm', 'help', 'endgame', 'ai', 'selling', 'buying' }) do
            local line = chat.shoutLine({ name = 'Tester', job = 'WAR', lvl = lvl }, 245, g)
            if chat.oddFor(line, lvl) or line:lower():find('lfp') or line:lower():find('lfm') then
                bad = bad + 1
                sample = sample or (lvl .. ': ' .. line)
            end
        end
    end
end
check('bots under 12: no LFP / LFM / party ranges (5280 shouts)', bad == 0, sample)

local subs, s2 = 0, nil
for _ = 1, 400 do
    local line = chat.shoutLine({ name = 'Tester', job = 'WAR', lvl = 14 }, 245, 'lfp')
    if line:find('/%u%u%u') then subs = subs + 1; s2 = s2 or line end
end
check('level 14 LFP never names a subjob', subs == 0, s2)

local lowRange, s3 = 0, nil
for _ = 1, 400 do
    local line = chat.shoutLine({ name = 'Tester', job = 'WAR', lvl = 13 }, 245, 'lfm')
    for a in line:gmatch('(%d+)%-%d+') do if tonumber(a) < 10 then lowRange = lowRange + 1; s3 = s3 or line end end
end
check('LFM ranges never start below 10', lowRange == 0, s3)

check('"lfp 1-5" is odd at level 3', chat.oddFor('lfp 1-5', 3))
check('"LFM 23-26 Qufim" fits level 24', not chat.oddFor('LFM 23-26 Qufim need WHM', 24))
check('"help with CoP 3-5" fits level 50', not chat.oddFor('help with CoP 3-5 /t', 50))
check('"LFM 52-55" is odd for a level 20', chat.oddFor('LFM 52-55 Kuftal', 20))

-----------------------------------
-- 2. selling: the item is really in the bazaar
-----------------------------------
local seller = newEnt(1, 'Seller', 60, 0); ents[1] = seller
seller:addItem(13656, 1)
local line = trade.newOffer(seller, 'selling', 245, trade.cap('jeuno'))
check('selling shout names the real item', line and line:find('Errant Cape') ~= nil, line)
local b = bazaar[1] and bazaar[1][13656]
check('the cape is priced in its bazaar near the fair price', b and b[1] >= 360000 and b[1] <= 440000, b and b[1])
check('the shout carries that price', line and line:find(trade.priceText(b[1]), 1, true) ~= nil, line)
check('one offer per bot', trade.newOffer(seller, 'selling', 245, 4) == nil)

-- cap: Jeuno 4 at once
local made = 1
for i = 2, 8 do
    local e = newEnt(i, 'Bot' .. i, 40, 50); ents[i] = e
    e:addItem(4112, 12)
    if trade.newOffer(e, 'selling', 245, trade.cap('jeuno')) then made = made + 1 end
end
check('Jeuno holds 4 offers at once', made == 4, made)
check('small towns hold 1, outposts 0', trade.cap('small') == 1 and trade.cap('outpost') == 0)

-- tells
told = {}
local you = newEnt(100, 'Hurami', 50, 30); ents[100] = you
check('a tell about the offer is answered', trade.onTell(seller, 'Hurami', 'how much for the cape?'))
check('...with the bazaar and price', told[1] and told[1].text:find('bazaar') and told[1].text:find(trade.priceText(b[1]), 1, true), told[1] and told[1].text)
check('an unrelated tell is left to the normal chat', not trade.onTell(seller, 'Hurami', 'lol nice'))

-- you buy it from the bazaar: the offer ends, it thanks you
said = {}
local speak = function(e, kind, text) said[#said + 1] = { e = e:getName(), kind = kind, text = text } end
BotBazaarBuy(100, 1, 13656, 10000000, 1)
bags[1][13656] = nil
clock = clock + 20
trade.tick(245, { seller }, { you }, speak)
check('sold: the offer is gone', trade.list()[1] == nil)
check('sold: it says thanks', said[1] and said[1].text:find('ty') ~= nil, said[1] and said[1].text)

-----------------------------------
-- 3. buying from your bazaar
-----------------------------------
trade._reset()
local buyer = newEnt(10, 'Buyer', 40, 80, 246); ents[10] = buyer
local bl = trade.newOffer(buyer, 'buying', 246, trade.cap('city'))
local o = trade.list()[10]
check('WTB shout for an item it can afford', bl and o and bl:find(o.name, 1, true), bl)
-- you list it too dear: it does not come
you.zone = 246
you:addItem(o.item, 1)
BotBazaarSet(100, o.item, o.price + 5000)
told = {}
clock = clock + 20
trade.tick(246, { buyer }, { you }, speak)
check('too dear: it does not walk over', o.target == nil)
trade.onTell(buyer, 'Hurami', 'i have one')
check('...and says what it can pay', told[#told] and told[#told].text:find('too much'), told[#told] and told[#told].text)
-- at its price
BotBazaarSet(100, o.item, o.price)
clock = clock + 20
trade.tick(246, { buyer }, { you }, speak)
check('your bazaar at its price: it heads over', o.target == 100)
local gilBefore = you.gil
for _ = 1, 30 do
    clock = clock + 2
    trade.tick(246, { buyer }, { you }, speak)
    if not trade.list()[10] then break end
end
check('it bought it: you got the gil', you.gil == gilBefore + o.price, you.gil - gilBefore)
check('...and it thanked you by tell', told[#told] and (told[#told].text:find('ty') or told[#told].text:find('thank')), told[#told] and told[#told].text)

-----------------------------------
-- 4. offers end
-----------------------------------
trade._reset()
local s4 = newEnt(20, 'Late', 50, 0); ents[20] = s4
s4:addItem(1132, 1)
trade.newOffer(s4, 'selling', 245, 4)
clock = clock + 21 * 60
trade.tick(245, { s4 }, { you }, speak)
check('after its time: offer over and the bazaar price taken down', trade.list()[20] == nil and not (bazaar[20] and bazaar[20][1132]))

trade._reset()
s4:addItem(1132, 1)
trade.newOffer(s4, 'selling', 245, 4)
clock = clock + 30
trade.tick(245, {}, { you }, speak) -- it left the area
check('it left the area: offer over, bazaar cleared', trade.list()[20] == nil and not (bazaar[20] and bazaar[20][1132]))

-- leftover price (logout / restart): taken down
trade._reset()
bazaar[20] = { [1132] = { 9000, 1 } }
clock = clock + 500
trade.tick(245, { s4 }, { you }, speak)
clock = clock + 30
trade.tick(245, { s4 }, { you }, speak)
check('a price left in a bazaar from before is taken down', not bazaar[20][1132])

-- without the rebuilt xi_map.exe: no selling/buying shouts at all
local keep = BotBazaarSet
BotBazaarSet = nil
trade._reset()
check('old xi_map.exe: no offers (and no fake shouts)', trade.newOffer(s4, 'selling', 245, 4) == nil and not trade.available())
BotBazaarSet = keep

print(string.format('\n%d passed, %d failed', pass, fail))
