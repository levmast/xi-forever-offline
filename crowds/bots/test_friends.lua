-- Stand-in checks for bots_friends.lua (bot players on your friend list). The C++ functions are faked here.
-- Run: luajit test_friends.lua <folder with bots_friends.lua>
local DIR = arg[1] or '.'
local passes, failures = 0, 0
local out = print
local function check(name, cond, detail)
    if cond then passes = passes + 1; out('ok   ' .. name)
    else failures = failures + 1; out('FAIL ' .. name .. (detail and ('  -- ' .. tostring(detail)) or '')) end
end

local T = 1800000000
os.time = function() return T end
local realRandom = math.random
local forced = nil -- a number: math.random() returns it (math.random(a, b) still picks a)
math.random = function(a, b)
    if forced ~= nil then
        if a == nil then return forced end
        return a
    end
    if a == nil then return realRandom() end
    return realRandom(a, b)
end

xi = { objType = { PC = 1, MOB = 4 } }

-- entities
local E = {}; E.__index = E
local ents, byName, timers = {}, {}, {}
local function ent(t)
    t.vars = t.vars or {}; t.kind = t.kind or 1; t.zone = t.zone or 100; t.lvl = t.lvl or 10; t.job = t.job or 1
    ents[t.id] = t; byName[t.name] = t
    return setmetatable(t, E)
end
function E:getID() return self.id end
function E:getName() return self.name end
function E:getObjType() return self.kind end
function E:getZoneID() return self.zone end
function E:isDead() return self.dead or false end
function E:isAlive() return not self.dead end
function E:isEngaged() return self.engaged or false end
function E:getMainLvl() return self.lvl end
function E:getMainJob() return self.job end
function E:getParty() return self.party or { self } end
function E:getPartySize() return #(self.party or { self }) end
function E:getPartyWithTrusts() local t = {} for _, m in ipairs(self:getParty()) do t[#t + 1] = m end for _ = 1, (self.trusts or 0) do t[#t + 1] = {} end return t end
function E:getCharVar(k) return self.vars[k] or 0 end
function E:setCharVar(k, v) self.vars[k] = v end
function E:timer(ms, fn) table.insert(timers, { at = T * 1000 + ms, e = self, fn = fn }) end

local function advance(sec)
    local stop = (T + sec) * 1000
    while true do
        table.sort(timers, function(a, b) return a.at < b.at end)
        local t = timers[1]
        if not t or t.at > stop then break end
        table.remove(timers, 1); T = math.floor(t.at / 1000); t.fn(t.e)
    end
    T = T + 0 -- (stays at the last timer, then moves on)
    T = math.floor(stop / 1000)
end

-- fake C++ API
local botIds = {}
local tells, joins = {}, {}
local friendRows = {}
function BotIsBot(id) return botIds[id] == true end
function BotIsOnline(id) return ents[id] ~= nil and not ents[id].offline end
function GetPlayerByID(id) local e = ents[id]; if e and not e.offline then return e end return nil end
function GetPlayerByName(n) local e = byName[n]; if e and not e.offline then return e end return nil end
function BotTell(id, to, text) tells[#tells + 1] = { from = ents[id].name, to = to, text = text } return true end
function BotList() local t = {} for id in pairs(botIds) do t[id] = { name = ents[id].name, online = not ents[id].offline } end return t end
function BotFriendList()
    local out = {}
    for _, r in ipairs(friendRows) do out[#out + 1] = r end
    return out
end
local function friendRow(bot, player, mutual, asked)
    friendRows[#friendRows + 1] = { bot = bot.id, acc = 1, name = player.name, mutual = mutual, asked = asked or false, listed = mutual }
end
local function clearTells() for i = #tells, 1, -1 do tells[i] = nil end end
local function tellsTo(name) local n = 0 for _, t in ipairs(tells) do if t.to == name then n = n + 1 end end return n end
local function anyText(pattern) for _, t in ipairs(tells) do if t.text:find(pattern) then return t end end return nil end

local printed = {}
local realPrint = print
print = function(...) local t = {} for i = 1, select('#', ...) do t[#t + 1] = tostring((select(i, ...))) end printed[#printed + 1] = table.concat(t, ' ') end
local ok, F = pcall(dofile, DIR .. '/bots_friends.lua')
print = realPrint
check('bots_friends.lua loads', ok and type(F) == 'table', F)
if not ok then os.exit(1) end

local state = {}
local life = {}
local persona = {}
F.setup({ state = state, join = function(bot, from) joins[#joins + 1] = { bot.name, from }; return true end,
    dialogue = { persona = function(b) return persona[b:getName()] end }, life = life })
check('setup gives bots_life its two hooks', life.keep == F.isFriendBot and life.preferLogin == F.pickLogin)

-- names with each nature
local easy, most, picky
for i = 1, 400 do
    local n = 'Bot' .. i
    local e = { getName = function() return n end }
    local k = F._nature(e)
    if k == 1 and not easy then easy = n elseif k == 2 and not most then most = n elseif k == 3 and not picky then picky = n end
end
check('the three natures all happen', easy and most and picky, tostring(easy) .. ' ' .. tostring(most) .. ' ' .. tostring(picky))
local counts = { 0, 0, 0 }
for i = 1, 3000 do counts[F._nature({ getName = function() return 'N' .. i .. 'x' end })] = counts[F._nature({ getName = function() return 'N' .. i .. 'x' end })] + 1 end
check('about a third easygoing, a few picky', counts[1] > 700 and counts[1] < 1100 and counts[3] > 300 and counts[3] < 600, table.concat(counts, '/'))

local hurami = ent({ id = 1, name = 'Hurami', lvl = 14, job = 3 })
local function bot(id, name, t)
    t = t or {}; t.id = id; t.name = name
    botIds[id] = true
    return ent(t)
end
local bEasy = bot(21000101, easy)
local bMost = bot(21000102, most)
local bPicky = bot(21000103, picky)
print = function() end

-- 1. requests
F._reset()
check('an easygoing bot accepts a stranger', F.onRequest(bEasy, 'Hurami') == true)
advance(20)
check('... and says so by tell', tellsTo('Hurami') == 1, #tells)
check('... and is marked a friend for its chat', bEasy:getCharVar('[Bot]Friend') == 1)
clearTells()
check('most bots: a stranger\'s request waits (nil)', F.onRequest(bMost, 'Hurami') == nil)
check('... and is not turned down', F.onRequest(bMost, 'Hurami') ~= false)
advance(30)
check('... it says "not yet" once, not on every sweep', tellsTo('Hurami') == 1, #tells)
F.onRequest(bMost, 'Hurami'); advance(30)
check('... still once after more sweeps the same day', tellsTo('Hurami') == 1)
clearTells()

-- 2. partying earns points; then it accepts by itself
hurami.party = { hurami, bMost }; bMost.party = hurami.party
bMost.engaged = true
local st = {}
for _ = 1, 125 do F.notice(bMost, st); T = T + 1 end
check('two minutes fighting together: 4 points', bMost:getCharVar('[BotF]Hurami') == 4, bMost:getCharVar('[BotF]Hurami'))
bMost.dead = true; F.notice(bMost, st); bMost.dead = false; F.notice(bMost, st)
check('raised with you: +3', bMost:getCharVar('[BotF]Hurami') == 7, bMost:getCharVar('[BotF]Hurami'))
check('the waiting request is accepted now', F.onRequest(bMost, 'Hurami') == true)
advance(30)
check('... with a "grew on me" kind of line', #tells == 1 and (tells[1].text:find('grew') or tells[1].text:find('good partying') or tells[1].text:find('finally') or tells[1].text:find('enjoyed') or tells[1].text:find('at last') or tells[1].text:find('good adventuring')), tells[1] and tells[1].text)
clearTells()
hurami.party = nil; bMost.party = nil; bMost.engaged = false

-- 3. a good long party: it asks you to add it when the party ends
F._reset(); friendRows = {}
bPicky.vars['[BotF]Hurami'] = 0
hurami.party = { hurami, bPicky }; bPicky.party = hurami.party
local st2 = {}
for _ = 1, 26 * 60 + 2 do F.notice(bPicky, st2); T = T + 1 end
check('26 minutes partying: 26 points', bPicky:getCharVar('[BotF]Hurami') == 26, bPicky:getCharVar('[BotF]Hurami'))
check('no offer while still in the party', #tells == 0)
hurami.party = nil; bPicky.party = nil
F.notice(bPicky, st2); advance(30)
check('party over: it asks you to add it', #tells == 1 and tells[1].from == picky, tells[1] and tells[1].text)
check('... and a request from you is then accepted (even a picky bot)', F.onRequest(bPicky, 'Hurami') == true)
advance(30)
clearTells()
F.notice(bPicky, st2); advance(30)
check('it does not ask twice', #tells == 0)

-- 4. tells
F._reset(); friendRows = {}; clearTells()
local bMost2 = bot(21000104, most .. 'b')
check('"can I add you?" to a bot that does not know you: handled', F.onTell(bMost2, 'Hurami', 'hey can i add you?') == true)
advance(10)
local notYetText = tells[1] and tells[1].text or ''
check('... "let\'s party first"', notYetText:find('party') ~= nil, notYetText)
clearTells()
check('"wanna be friends?" to an easygoing one: handled', F.onTell(bEasy, 'Hurami', 'wanna be friends?') == true)
advance(10)
local yesText = tells[1] and tells[1].text:lower() or ''
check('... "sure, send a request" and the request will be accepted', (yesText:find('request') or yesText:find('add me')) and bEasy:getCharVar('[BotFO]Hurami') > 0, yesText)
clearTells()
friendRow(bEasy, hurami, true)
F._reset()
check('already friends: "we\'re already friends"', F.onTell(bEasy, 'Hurami', 'add me?') == true)
advance(10)
check('... said', tells[1] and tells[1].text:find('already') ~= nil, tells[1] and tells[1].text)
clearTells()
check('an ordinary tell is left to the others (not handled)', F.onTell(bMost2, 'Hurami', 'what are you up to') == false)
check('my friend is late: not a friend question', F.onTell(bMost2, 'Hurami', 'my friend is late lol') == false)
local before = bMost2:getCharVar('[BotF]Hurami')
F.onTell(bMost2, 'Hurami', 'hi again')
check('chatting gives a point at most every 5 minutes', bMost2:getCharVar('[BotF]Hurami') == before)
T = T + 301; F.onTell(bMost2, 'Hurami', 'still there?')
check('... and again after 5 minutes', bMost2:getCharVar('[BotF]Hurami') == before + 1)

-- 5. polite personalities type the polite line
F._reset(); clearTells()
persona[easy] = { reg = 'polite' }
local bPolite = bEasy
bPolite.vars['[BotFR]Kurami'] = 0
F.onRequest(bPolite, 'Kurami'); advance(20)
check('a polite bot answers in its polite voice', tells[1] and tells[1].text:sub(1, 1):match('%u') ~= nil, tells[1] and tells[1].text)
persona[easy] = nil
clearTells()

-- 6. the friend list: [Bot]Friend follows it, friends kept from retiring
F._reset(); friendRows = {}
friendRow(bEasy, hurami, true)
friendRow(bMost, hurami, false, true)
F.tick({ hurami })
check('a mutual friend counts as a friend bot (never retires)', F.isFriendBot(bEasy.id) == true)
check('a request still waiting does not', F.isFriendBot(bMost.id) == false)
bMost.vars['[Bot]Friend'] = 1
friendRows = {}
T = T + 20; F.tick({ hurami })
check('taken off the list: [Bot]Friend goes back to 0', bEasy:getCharVar('[Bot]Friend') == 0)

-- 7. cheers: real level ups only
F._reset(); friendRows = {}; clearTells()
friendRow(bEasy, hurami, true); friendRow(bMost, hurami, true)
hurami.lvl, hurami.job = 14, 3
F.tick({ hurami })
forced = 0
hurami.lvl = 15; T = T + 1; F.tick({ hurami }); advance(120)
forced = nil
check('you reach 15: a friend cheers (one)', #tells == 1 and tells[1].to == 'Hurami', #tells)
clearTells(); forced = 0
hurami.lvl = 16; T = T + 1; F.tick({ hurami }); advance(120)
check('16: no cheer (every 5th level, and from 70)', #tells == 0)
hurami.job, hurami.lvl = 1, 20; T = T + 200; F.tick({ hurami }); advance(120)
check('a job change to a higher job is not a level up', #tells == 0)
hurami.job, hurami.lvl = 3, 10; T = T + 200; F.tick({ hurami }); hurami.lvl = 16; T = T + 1; F.tick({ hurami }); hurami.lvl = 20; T = T + 1; F.tick({ hurami }); advance(120)
check('the end of a level sync is not a level up', #tells == 0)
hurami.lvl = 19; T = T + 1; F.tick({ hurami }); hurami.lvl = 20; T = T + 1; F.tick({ hurami }); advance(120)
check('back to a level already reached: no cheer', #tells == 0)
forced = nil

-- 8. offers to help
F._reset(); clearTells(); friendRows = {}
friendRow(bMost, hurami, true)
hurami.party = nil; bMost.party = nil; bMost.lvl = 16; hurami.lvl = 16
hurami.engaged = true
forced = 0
F.tick({ hurami }); advance(20)
forced = nil
check('you fight alone, a friend near your level is free: it offers to help', #tells == 1 and tells[1].from == most, tells[1] and tells[1].text)
check('"sure" by tell: it joins you', F.onTell(bMost, 'Hurami', 'sure!') == true and #joins == 1 and joins[1][2] == 'Hurami')
clearTells()
T = T + 3600; forced = 0; F.tick({ hurami }); advance(20); forced = nil
check('another hour later it may offer again', #tells == 1)
clearTells()
check('"no thanks": it says np and does not join', F.onTell(bMost, 'Hurami', 'no thanks, im good') == true and #joins == 1)
advance(10)
check('... np said', #tells == 1, #tells)
clearTells()
T = T + 3600; hurami.trusts = 5; forced = 0; F.tick({ hurami }); advance(20); forced = nil
check('no room in your party (squad out): no offer', #tells == 0)
hurami.trusts = 0
T = T + 3600; bMost.lvl = 30; forced = 0; F.tick({ hurami }); advance(20); forced = nil
check('a friend far from your level does not offer', #tells == 0)
bMost.lvl = 16
T = T + 3600; state[bMost.id] = { bf = {} }; forced = 0; F.tick({ hurami }); advance(20); forced = nil
check('a friend busy in a battlefield does not offer', #tells == 0)
state[bMost.id] = nil
T = T + 3600; hurami.engaged = false; forced = 0; F.tick({ hurami }); advance(20); forced = nil
check('not while you are not fighting', #tells == 0)
hurami.engaged = false

-- 9. hellos
F._reset(); clearTells(); friendRows = {}
friendRow(bEasy, hurami, true)
bEasy.vars['[BotFH]'] = 0; bEasy.vars['[BotFS]'] = 0
forced = 0
F.onLogin(bEasy); advance(70)
check('a friend logging in says hi', #tells == 1 and tells[1].to == 'Hurami', #tells)
clearTells()
F.onLogin(bEasy); advance(70)
check('... not again for a few hours', #tells == 0)
T = T + 4 * 86400; F._reset(); friendRow(bEasy, hurami, true)
F.onLogin(bEasy); advance(70)
check('days later: "long time no see" kind of hello', #tells == 1 and (tells[1].text:find('long time') or tells[1].text:find('stranger') or tells[1].text:find('while')), tells[1] and tells[1].text)
clearTells()
T = T + 100
F.onPlayerLogin(hurami); advance(100)
check('you log in: a friend online says hi', #tells == 1, #tells)
clearTells()
F.onPlayerLogin(hurami); advance(100)
check('... not on every log in', #tells == 0)
forced = nil

-- 10. its own milestones
F._reset(); clearTells(); friendRows = {}
friendRow(bMost, hurami, true)
local st3 = {}
bMost.lvl, bMost.job = 29, 3; F.notice(bMost, st3)
forced = 0
bMost.lvl = 30; F.notice(bMost, st3); advance(30)
forced = nil
check('a friend reaching 30 tells you', #tells == 1 and tells[1].text:find('30') ~= nil, tells[1] and tells[1].text)
clearTells()

-- 11. logging in more while you play
F._reset(); friendRows = {}
friendRow(bMost, hurami, true)
bMost.offline = true
forced = 0
local picked = F.pickLogin({ 21000999, bMost.id })
check('a friend of yours (offline) gets the login slot', picked == bMost.id, picked)
check('... not again right away (it just played)', F.pickLogin({ bMost.id }) == nil)
T = T + 3600
hurami.offline = true
check('nobody of its friends on: no preference', F.pickLogin({ bMost.id }) == nil)
hurami.offline = false
forced = nil
bMost.offline = false

-- 12. !bots friends
F._reset(); friendRows = {}
friendRow(bEasy, hurami, true)
friendRow(bPicky, hurami, false, true)
bMost.vars['[BotF]Hurami'] = 9
local lines = F.report(hurami)
check('!bots friends lists friends, waiting requests and bots who know you', #lines == 3 and lines[1]:find(easy) and lines[2]:find(picky) and lines[3]:find(most .. ' 9'), table.concat(lines, ' || '))

-- 13. the game's own requests and mail (bots.cpp: BotFriendRequest, BotSendMessage)
local requests, mails = {}, {}
local requestAnswer = { true, 'sent' }
function BotFriendRequest(id, name) requests[#requests + 1] = { ents[id].name, name }; return requestAnswer[1], requestAnswer[2] end
function BotSendMessage(id, name, text) mails[#mails + 1] = { from = id, to = name, text = text }; return true end
F._reset(); friendRows = {}; clearTells()
local bOffer = bot(21000105, most .. 'c')
bOffer.vars['[BotF]Hurami'] = 30
hurami.party = { hurami, bOffer }; bOffer.party = hurami.party
local st5 = {}
F.notice(bOffer, st5)
hurami.party = nil; bOffer.party = nil
forced = 0
F.notice(bOffer, st5); advance(60)
forced = nil
check('party over: it sends you a real friend request', #requests == 1 and requests[1][2] == 'Hurami', #requests)
check('... and says so by tell (sometimes)', #tells == 1 and tells[1].text:lower():find('request') ~= nil, tells[1] and tells[1].text)
clearTells()
F.notice(bOffer, st5); advance(60)
check('... once', #requests == 1)

F._reset(); clearTells(); requests = {}
local bAsk = bot(21000106, easy .. 'd')
check('"can I add you?" to an easygoing bot: handled', F.onTell(bAsk, 'Hurami', 'can i add you?') == true)
advance(10)
check('... it sends you the request itself', #requests == 1 and requests[1][1] == bAsk.name)
check('... "sure! sent you one"', tells[1] and tells[1].text:lower():find('sent') ~= nil, tells[1] and tells[1].text)
clearTells(); requests = {}
requestAnswer = { false, 'asked' }
local bAsk2 = bot(21000107, easy .. 'e')
check('you already sent it a request: handled without a word (it accepts on its own)', F.onTell(bAsk2, 'Hurami', 'add me?') == true)
advance(10)
check('... no tell', #tells == 0)
requestAnswer = { false, 'mailbox' }
local bAsk3 = bot(21000108, easy .. 'f')
F.onTell(bAsk3, 'Hurami', 'can i add you?'); advance(10)
check('could not send one: "send me a request" instead', tells[1] and tells[1].text:lower():find('send me') ~= nil, tells[1] and tells[1].text)
requestAnswer = { true, 'sent' }
clearTells()

-- your answers
F._reset(); clearTells()
forced = 0
F.onReply(bOffer, 'Hurami', true); advance(20)
forced = nil
check('you accept its request: it thanks you', #tells == 1 and tells[1].text:lower():find('t') ~= nil and bOffer:getCharVar('[Bot]Friend') == 1, tells[1] and tells[1].text)
clearTells(); requests = {}
F.onReply(bOffer, 'Hurami', false)
T = T + 8 * 86400
hurami.party = { hurami, bOffer }; bOffer.party = hurami.party; F.notice(bOffer, st5); hurami.party = nil; bOffer.party = nil; F.notice(bOffer, st5); advance(60)
check('you turn it down: no new request a week later', #requests == 0)
T = T + 25 * 86400
hurami.party = { hurami, bOffer }; bOffer.party = hurami.party; F.notice(bOffer, st5); hurami.party = nil; bOffer.party = nil; F.notice(bOffer, st5); advance(60)
check('... but after a month it may ask again', #requests == 1)
check('turned down, but then you send one yourself: accepted', F.onRequest(bOffer, 'Hurami') == true)
advance(20); clearTells()

-- mail
F._reset(); friendRows = {}; mails = {}
friendRow(bEasy, hurami, true)
hurami.offline = true
F.onMessage(bEasy, 'Hurami', 'hey how are you'); advance(130)
check('your message while you are off: a friend writes back', #mails == 1 and mails[1].to == 'Hurami', #mails)
mails = {}
F.onMessage(bMost2, 'Hurami', 'hi'); advance(130)
check('... not a bot that is not your friend (only friends could mail)', #mails == 0)
local st6 = {}
bEasy.lvl, bEasy.job = 39, 4; F.notice(bEasy, st6)
forced = 0; bEasy.lvl = 40; F.notice(bEasy, st6); forced = nil
check('a friend reaching 40 while you are off: a message for later', #mails == 1 and mails[1].text:find('40') ~= nil, mails[1] and mails[1].text)
hurami.offline = false
mails = {}

F._reset(); friendRows = {}; mails = {}
friendRow(bEasy, hurami, true); friendRow(bMost, hurami, true); friendRow(bPicky, hurami, true)
hurami.vars['[BotF]Seen'] = T - 3 * 86400
forced = 0
F.onPlayerLogin(hurami)
forced = nil
check('back after 3 days away: friends left you mail (at most 2)', #mails == 2, #mails)
check('... and your last time on is noted', hurami:getCharVar('[BotF]Seen') == T)
mails = {}
T = T + 3600
forced = 0; F.onPlayerLogin(hurami); forced = nil
check('back after an hour: no mail', #mails == 0)
hurami.vars['[BotF]Seen'] = 0
forced = 0; F.onPlayerLogin(hurami); forced = nil
check('the very first time: no mail', #mails == 0)

F._reset(); friendRows = {}
friendRow(bEasy, hurami, true)
hurami.vars['[BotF]Seen'] = 0; bEasy.vars['[BotFS]Hurami'] = 0
F.tick({ hurami })
check('while you play: your time on and the friends you were on with are noted', hurami:getCharVar('[BotF]Seen') == T and bEasy:getCharVar('[BotFS]Hurami') == T)
BotFriendRequest, BotSendMessage = nil, nil

-- every line has both voices and fills its {names}
local bad = {}
for which, list in pairs(F._lines) do
    for i, l in ipairs(list) do
        if type(l[1]) ~= 'string' or type(l[2]) ~= 'string' or #l[1] > 100 or #l[2] > 100 then bad[#bad + 1] = which .. i end
    end
end
check('every line has a casual and a polite version, short enough for a tell', #bad == 0, table.concat(bad, ' '))

print = realPrint
print(string.format('\n%d passed, %d failed', passes, failures))
os.exit(failures == 0 and 0 or 1)
