-- Spell requests to bot players in your party (bots.lua spellRequest, 2026-11-21).   texlua test_requests.lua <folder with bots.lua>
local DIR = arg[1] or '.'
local passes, failures = 0, 0
local function check(name, cond, detail)
    if cond then passes = passes + 1; print('ok   ' .. name)
    else failures = failures + 1; print('FAIL ' .. name .. (detail and ('  -- ' .. tostring(detail)) or '')) end
end

local timers = {}
xi = { objType = { PC = 1, MOB = 4, TRUST = 8 }, msg = { channel = { SYSTEM_3 = 29 } }, module = {}, player = {},
       recast = { MAGIC = 1, ABILITY = 2 }, magic = { spell = { CURE = 1, CURE_II = 2, PROTECT = 43, HASTE = 57 } } }
xi.module.registerCommand = function() end
Module = {}; Module.__index = Module
function Module:new(n) return setmetatable({}, Module) end
function Module:addOverride() end
package.preload['modules/module_utils'] = function() return true end
for _, f in ipairs({ 'bots_life', 'bots_hunt', 'bots_craft', 'bots_quests', 'bots_chat', 'bots_party', 'bots_jobs', 'bots_ls',
                     'bots_growth', 'bots_gear', 'bots_bcnm', 'bots_invite', 'bots_friends', 'bots_dialogue', 'bots_pets' }) do
    package.preload['modules/custom/lua/' .. f] = function() error('not in this test') end
end
package.preload['modules/custom/lua/bots_config'] = function() return { enabled = true, roster = 3, online = 2 } end

local E = {}; E.__index = E
local function ent(t) return setmetatable(t, E) end
function E:getID() return self.id end
function E:getName() return self.name end
function E:getPacketName() return self.name end
function E:getObjType() return self.kind end
function E:getZoneID() return 1 end
function E:isAlive() return true end
function E:isDead() return false end
function E:getMainJob() return self.mj end
function E:getSubJob() return self.sj or 0 end
function E:getMainLvl() return self.ml end
function E:getSubLvl() return self.sl or 0 end
function E:getMP() return self.mp or 100 end
function E:hasSpell(id) return self.spells and self.spells[id] or false end
function E:hasRecast(_, id) return self.recast and self.recast[id] or false end
function E:checkDistance() return 5 end
function E:timer(ms, fn) timers[#timers + 1] = { e = self, fn = fn } end
function E:getPartyWithTrusts() return self.members end
function E:getParty() return self.members end
local function run() local t = timers; timers = {}; for _, x in ipairs(t) do x.fn(x.e) end end

-- spells: id -> { [job] = level }, cost
local SPELLS = { [1] = { lv = { [3] = 1, [5] = 3 }, mp = 8 }, [2] = { lv = { [3] = 11, [5] = 14 }, mp = 24 },
                 [43] = { lv = { [3] = 7, [5] = 9 }, mp = 9 }, [57] = { lv = { [3] = 40 }, mp = 40 } }
function GetSpell(id) local s = SPELLS[id]; if not s then return nil end
    return { getLevel = function(_, job) return s.lv[job] or 0 end, getMPCost = function() return s.mp end } end

local bots, cast, said = {}, {}, {}
function BotIsBot(id) return bots[id] ~= nil end
function BotCast(id, spell, target) cast[#cast + 1] = { id = id, spell = spell, target = target:getName() } end
function BotChat(id, kind, text) said[#said + 1] = { id = id, text = text } end
BotPlayerOnline = function() return true end
GetServerVariable = function() return 0 end
SetServerVariable = function() end
GetPlayerByID = function() return nil end
local realPrint = print
print = function() end
local ok, err = pcall(dofile, DIR .. '/bots.lua')
print = realPrint
check('bots.lua loads', ok, err)

local you   = ent({ id = 1, name = 'Sunie', kind = 1, mj = 1, ml = 30 })
local whm   = ent({ id = 16000001, name = 'Belan', kind = 1, mj = 3, ml = 20, spells = { [1] = true, [2] = true, [43] = true } })
local war   = ent({ id = 16000002, name = 'Rodo', kind = 1, mj = 1, ml = 20, sj = 3, sl = 10, spells = { [1] = true, [43] = true, [2] = true } })
local mate  = ent({ id = 99, name = 'Kasumi', kind = 8 })
bots[whm.id], bots[war.id] = true, true
you.members = { you, whm, war, mate }

local function ask(text) cast, said = {}, {}; xi.bots.partyOrder(you, text); run(); return cast[1] end

local c = ask('protect')
check('"protect": a bot that can casts it on you', c and c.spell == 43 and c.target == 'Sunie', c and (c.id .. ' ' .. c.target))
c = ask('cure ii kasumi')
check('"cure ii kasumi": the two-word spell, on the squad mate', c and c.spell == 2 and c.target == 'Kasumi', c and c.target)
check('  ...cast by the WHM (the WAR/WHM is too low for Cure II as a support job)', c and c.id == whm.id, c and c.id)
c = ask('please cast cure on me')
check('filler words are skipped ("please cast cure on me")', c and c.spell == 1 and c.target == 'Sunie')
c = ask('Rodo cure ii')
check('a named bot that can\'t: no cast...', c == nil)
check('  ...and it says why', said[1] and said[1].id == war.id and said[1].text:find('job') ~= nil, said[1] and said[1].text)
c = ask('haste')
check('nobody can: no cast and nobody talks (general request)', c == nil and #said == 0)
whm.recast = { [43] = true }; war.recast = { [43] = true }
c = ask('protect')
check('on recast: not cast', c == nil)
whm.recast = nil; war.recast = nil
c = ask('thanks for the protect')
check('ordinary talk that mentions a spell is not a request', c == nil)
c = ask('follow')
check('orders still work as before (follow is not a spell)', c == nil)

print(string.format('%d passed, %d failed', passes, failures))
