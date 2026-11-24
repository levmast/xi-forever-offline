-- Stand-in test for the open-world part of the server's co-op script (modules/custom/late/coop.lua): the KICK line and
-- the wording for a world that is open to everyone. No game server needed, and no waiting (the clock is a stand-in too).
-- Run from an empty scratch folder:
--     luajit <kit>/dev/coop-tests/test_openworld_server.lua <server>/modules/custom/late/coop.lua
-- or, without a luajit program:  python run_lua.py test_openworld_server.lua <...>/coop.lua
local path = arg[1] or 'modules/custom/late/coop.lua'
local realPrint = print                         -- the script's own print lines are collected instead (see start)
local checks, failed = 0, 0
local function check(ok, what)
    checks = checks + 1
    if not ok then
        failed = failed + 1
        realPrint('FAIL: ' .. what)
    end
end

os.execute('mkdir -p modules/custom/lua 2>/dev/null || mkdir modules\\custom\\lua 2>NUL')
local function write(name, text)
    local f = assert(io.open('modules/custom/lua/' .. name, 'w'))
    f:write(text)
    f:close()
end

-- stand-ins for the server
local clock = 1700000000
os.time = function() return clock end
package.loaded['modules/module_utils'] = true
local overrides, printed, timers, area, online, bots
Module = { new = function(_, name) return { name = name, addOverride = function(_, target, fn) overrides[target] = fn end } end }
super = function() return 'super-result' end
BotIsBot = function(id) return bots[id] == true end
GetPlayerByID = function(id) return online[id] end

local function newPlayer(id, name, guest)
    local p = { id = id, name = name, heard = {}, left = 0 }
    function p:getID() return self.id end
    function p:getName() return self.name end
    function p:getObjType() return xi.objType.PC end
    function p:getCharVar(var) return (var == 'COOP_GUEST' and guest) and 1 or 0 end
    function p:printToPlayer(text) table.insert(self.heard, text) end
    function p:printToArea(text) table.insert(area, text) end
    function p:timer(ms, fn) table.insert(timers, { fn = fn, who = self }) end
    function p:getParty() return { self } end
    function p:leaveGame()
        if self.broken then error('leaveGame failed') end
        self.left = self.left + 1
    end
    return p
end

local function runTimers()                      -- fires every waiting timer once (new ones wait for the next call)
    local due = timers
    timers = {}
    for _, t in ipairs(due) do t.fn(t.who) end
end

local function look(seconds)                    -- lets the script's next look at the launcher's file happen
    clock = clock + (seconds or 5)
    runTimers()
end

-- Starts the script from nothing with this coop_config.lua, as a server start does. Returns its log in hook.
local function start(configText)
    write('coop_config.lua', configText)
    write('coop_in.txt', '')
    overrides, printed, timers, area, online, bots = {}, {}, {}, {}, {}, {}
    xi = { objType = { PC = 1 }, msg = { channel = { SYSTEM_3 = 29 }, area = { SYSTEM = 0 } } }
    print = function(...) table.insert(printed, table.concat({ ... }, ' ')) end
    assert(loadfile(path))()
    return overrides['xi.player.onGameIn']
end

local function logged(text)
    for _, line in ipairs(printed) do
        if line:find(text, 1, true) then return true end
    end
    return false
end

local function enter(onGameIn, player)
    online[player:getID()] = player
    onGameIn(player, false, false)
end

-----------------------------------
-- between friends: as before
-----------------------------------
local onGameIn = start("return { hosting = true, world = 'Hurami\\'s world' }\n")
check(logged("[coop] ready (hosting Hurami's world)"), 'a friends world starts as "hosting": ' .. tostring(printed[#printed]))
local owner, guest = newPlayer(1, 'Hurami', false), newPlayer(2, 'Visitor', true)
check(xi.coop.blockGuest(guest, 'something', 'x') and guest.heard[#guest.heard] == "Visitors cannot use that command in a friend's world.",
    'between friends a visitor is told "a friend\'s world": ' .. tostring(guest.heard[#guest.heard]))

-----------------------------------
-- an open world: the wording
-----------------------------------
onGameIn = start("return { hosting = true, open = true, world = 'The Hub' }\n")
check(logged('[coop] ready (open world The Hub)'), 'an open world says so when it starts: ' .. tostring(printed[#printed]))
owner, guest = newPlayer(1, 'Hurami', false), newPlayer(2, 'Visitor', true)
check(xi.coop.blockGuest(guest, 'something', 'x') and guest.heard[#guest.heard] == 'Visitors cannot use that command in this world.',
    'in an open world a visitor is not told "a friend\'s world": ' .. tostring(guest.heard[#guest.heard]))
check(xi.coop.blockGuest(guest, 'bots', 'off') and guest.heard[#guest.heard]:find('Only the owner of this world', 1, true),
    'the owner\'s commands keep their own line')
check(not xi.coop.blockGuest(owner, 'something', 'x'), 'the owner is never stopped')

onGameIn = start("return { hosting = true, open = 'yes', world = 'Odd' }\n")
check(logged('[coop] ready (hosting Odd)'), 'only open = true opens a world (anything else is a friends world)')

-----------------------------------
-- KICK: a visitor is logged out, once
-----------------------------------
onGameIn = start("return { hosting = true, open = true, world = 'The Hub' }\n")
owner, guest = newPlayer(1, 'Hurami', false), newPlayer(2, 'Visitor', true)
local other, bot = newPlayer(3, 'Second', true), newPlayer(16000001, 'Botty', false)
bots[16000001] = true
enter(onGameIn, owner)
enter(onGameIn, guest)
enter(onGameIn, other)
enter(onGameIn, bot)
look()                                          -- the welcome lines, and a first look at the empty file
check(guest.left == 0 and other.left == 0, 'nobody is logged out without a line')
guest.heard = {}

write('coop_in.txt', string.format('%d|1|KICK|2\n', clock))
look()
check(guest.left == 1, 'the visitor the line names is logged out (' .. guest.left .. ')')
check(guest.heard[1] == 'The host of this world has logged you out.', 'and is told why first: ' .. tostring(guest.heard[1]))
check(other.left == 0 and owner.left == 0, 'nobody else is')
check(logged('[coop] Visitor (2) was logged out by the host'), 'the server log says who')
look()
look()
check(guest.left == 1, 'one line logs out once, also when the visitor is still (or again) in the world')

-- the owner's own characters, bots and unknown numbers
write('coop_in.txt', string.format('%d|2|KICK|1\n%d|3|KICK|16000001\n%d|4|KICK|999\n', clock, clock, clock))
look()
check(owner.left == 0, 'a line naming the owner\'s character logs nobody out')
check(bot.left == 0, 'nor a bot player')
check(logged('[coop] character 1 is not a visitor: left alone'), 'and the log says it was left alone')
check(#area == 0, 'a KICK line is not shown to players')

-- lines that are not a character number
write('coop_in.txt', string.format('%d|5|KICK|\n%d|6|KICK|3 or 1=1\n%d|7|KICK|Second\n%d|8|KICK|33333333333\n%d|9|KICK|-3\n', clock, clock, clock, clock, clock))
look()
check(other.left == 0, 'a KICK line without a plain character number does nothing')
check(not logged('could not read') and not logged('could not log a visitor out'), '... and is no error either')

-- an old line (from an earlier session)
write('coop_in.txt', string.format('%d|10|KICK|3\n', clock - 600))
look()
check(other.left == 0, 'an old KICK line is ignored')

-- a visitor between two areas is logged out when it arrives
online[3] = nil
write('coop_in.txt', string.format('%d|11|KICK|3\n', clock))
look()
check(other.left == 0, 'a visitor that is between two areas cannot be logged out yet')
look()
online[3] = other
look()
check(other.left == 1, '... and is logged out as soon as it is back (' .. other.left .. ')')

-- ... but not after the line got old
local late = newPlayer(4, 'Late', true)
write('coop_in.txt', string.format('%d|12|KICK|4\n', clock))
look()
clock = clock + 120
enter(onGameIn, late)
look()
look()
check(late.left == 0, 'a request that waited longer than a line stays fresh is dropped')

-- a failure while logging out does not stop the script, and is not repeated
local stuck = newPlayer(5, 'Stuck', true)
stuck.broken = true
enter(onGameIn, stuck)
local asked = clock
write('coop_in.txt', string.format('%d|13|KICK|5\n', asked))
look()
check(logged('[coop] could not log a visitor out'), 'a failed log out is written to the server log')
local lines = #printed
write('coop_in.txt', string.format('%d|13|KICK|5\n%d|14|SAY|This world closes in a minute.\n', asked, clock))
look()
check(#area == 1 and area[1] == 'This world closes in a minute.', 'the launcher\'s other lines still arrive afterwards')
look()
local again = 0
for i = lines + 1, #printed do
    if printed[i]:find('could not log a visitor out', 1, true) then again = again + 1 end
end
check(again == 0, 'the failed log out is not tried over and over (' .. again .. ')')

-- BOTS lines still work next to the new kind
local botsOnline
xi.bots = { setOnline = function(n) botsOnline = n return true end }
write('coop_in.txt', string.format('%d|15|BOTS|40\n', clock))
look()
check(botsOnline == '40', 'a BOTS line still changes the bots online')

print = realPrint
print(string.format('%d checks, %d failed', checks, failed))
os.exit(failed == 0 and 0 or 1)
