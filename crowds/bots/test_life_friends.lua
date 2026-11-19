-- Stand-in checks for the two bots_life.lua hooks bots_friends.lua uses: friends never retire (L.keep), and while
-- you are on they get log in slots (L.preferLogin).   Run in an empty folder: luajit test_life_friends.lua <folder with bots_life.lua>
-- (bots_life writes modules/custom/lua/bots_retired.lua under the current folder)
local DIR = arg[1] or '.'
local passes, failures = 0, 0
local function check(name, cond, detail)
    if cond then passes = passes + 1; print('ok   ' .. name)
    else failures = failures + 1; print('FAIL ' .. name .. (detail and ('  -- ' .. tostring(detail)) or '')) end
end

os.execute('mkdir -p modules/custom/lua 2>/dev/null || mkdir modules\\custom\\lua')
local T = 1800000000
os.time = function() return T end
xi = { crowds = { zoneSpots = function() return { { x = 1, y = 0, z = 1 } } end } }
package.preload['modules/custom/lua/bots_config'] = function() return { enabled = true, roster = 1100, online = 0 } end

local vars = {}
GetServerVariable = function(k) return vars[k] or 0 end
SetServerVariable = function(k, v) vars[k] = v end
BotPlayerOnline = function() return true end
local list = {}
local logins = {}
BotList = function() return list end
BotLogin = function(id) logins[#logins + 1] = id; list[id].online = true; return true end
BotPlace = function() return true end
BotHeal, BotLogout, BotCreate = function() end, function() end, function() return 0 end
GetPlayerByID = function() return nil end
GetZone = function() return nil end

local L = dofile(DIR .. '/bots_life.lua')
L.loadConfig()

-- 1100 offline bots; a day passes: about 7 stop playing. Run it many days; the friend never retires.
for id = 1, 1100 do list[id] = { name = 'B' .. id, online = false, zone = 230 } end
local FRIENDS = {}
for id = 1, 50 do FRIENDS[id] = true end
L.keep = function(id) return FRIENDS[id] == true end
local retiredFriend, retiredOthers = false, 0
for day = 1, 40 do
    vars['[Bots]TurnoverDay'] = math.floor(T / 86400) - 1
    vars['[Bots]Population'] = 1100
    T = T + 86400
    L.tick()
end
local f = io.open('modules/custom/lua/bots_retired.lua')
local text = f and f:read('*a') or ''
if f then f:close() end
for id in text:gmatch('%[(%d+)%] = true') do
    if FRIENDS[tonumber(id)] then retiredFriend = true else retiredOthers = retiredOthers + 1 end
end
check('bots stop playing as before (40 days)', retiredOthers > 100, retiredOthers)
check('bot friends never do (50 of them)', not retiredFriend)

-- log in slots: with preferLogin the friend gets the slot
package.loaded['modules/custom/lua/bots_config'] = nil
package.preload['modules/custom/lua/bots_config'] = function() return { enabled = true, roster = 1100, online = 50 } end
L.loadConfig()
L.keep = nil
local asked = 0
L.preferLogin = function(offline) asked = asked + 1; return 900 end
for _ = 1, 30 do T = T + 5; L.tick() end
local friendIn = false
for _, id in ipairs(logins) do friendIn = friendIn or id == 900 end
check('preferLogin is asked for log in slots', asked > 0, asked)
check('... and the friend it names logs in', friendIn)
L.preferLogin = function() error('boom') end
local before = #logins
list[900].online = false
for _ = 1, 30 do T = T + 5; L.tick() end
check('a failing preferLogin does not stop log ins', #logins > before)
L.preferLogin = function() return 123456789 end -- (not a bot any more)
before = #logins
for _ = 1, 30 do T = T + 5; L.tick() end
local bad = false
for i = before + 1, #logins do bad = bad or logins[i] == 123456789 end
check('an unknown id from preferLogin is ignored', #logins > before and not bad)

os.remove('modules/custom/lua/bots_retired.lua')
print(string.format('\n%d passed, %d failed', passes, failures))
os.exit(failures == 0 and 0 or 1)
