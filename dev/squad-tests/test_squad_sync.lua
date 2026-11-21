-- Stand-in tests for squad.lua v1.7: level sync to the player, and random starter outfits.   texlua test_squad_sync.lua [squad.lua] [squad_starter_gear.lua]
local SQUAD = arg[1] or 'squad.lua'
local GEAR  = arg[2] or 'squad_starter_gear.lua'
local passed, failed = 0, 0
local function check(c, l) if c then passed = passed + 1 else failed = failed + 1 io.write('FAIL: ', l, '\n') end end
local function section(n) io.write('\n== ', n, '\n') end

local W = {}
local function reset()
    W.spawned, W.equip, W.unlocked, W.timers, W.printed, W.cleared, W.clock = {}, {}, {}, {}, {}, 0, 1000
    W.items = {}       -- item id -> level
    W.squad = {}
end
reset()

-- the server bits squad.lua uses
xi = { module = { registerCommand = function() end }, objType = { PC = 1, TRUST = 2, MOB = 3 }, animation = { NONE = 0, ATTACK = 1, HEALING = 33 }, settings = { map = { EXP_RATE = 1 } }, effect = {}, zone = {}, job = {} }
setmetatable(xi, { __index = function(t, k) local v = setmetatable({}, { __index = function() return 0 end }) rawset(t, k, v) return v end })
OVERRIDES = {}
super = function() return 'base' end
Module = { new = function(self, name) return { addOverride = function(_, k, fn) OVERRIDES[k] = fn end } end }
package.preload['modules/module_utils'] = function() return true end
package.preload['modules/custom/lua/squad_starter_gear'] = function() return dofile(GEAR) end
os.time = function() return W.clock end

GetSquad = function(charId) return W.squad end
SetSquadEquip = function(id, job, slot, item) W.equip[#W.equip + 1] = { id, job, slot, item } end
UnlockSquadItem = function(charId, item) W.unlocked[item] = true end
GetSquadItemInfo = function(item) return { valid = true, level = W.items[item] or 1, name = 'item' .. item, jobs = 0xFFFFFF, slot = 0 } end
BuildStarterGear = function(job) return { [0] = 1 } end
GetSquadUnlocks = function() return {} end

local function entity(kind, opts)
    local e = { anim = 0, hp = 50, maxhp = 100, mp = 10, maxmp = 100, alive = true, kind = kind, vars = {}, level = opts.level or 1, engaged = false, listeners = {}, party = {}, id = opts.id or 0, name = opts.name }
    function e:getObjType() return self.kind end
    function e:getLocalVar(k) return self.vars[k] or 0 end
    function e:setLocalVar(k, v) self.vars[k] = v end
    function e:getMainLvl() return self.level end
    function e:isEngaged() return self.engaged end
    function e:isAlive() return self.alive end
    function e:getAnimation() return self.anim end
    function e:setAnimation(a) self.anim = a end
    function e:getHP() return self.hp end
    function e:getMaxHP() return self.maxhp end
    function e:addHP(n) self.hp = math.min(self.maxhp, self.hp + n) end
    function e:getMP() return self.mp end
    function e:getMaxMP() return self.maxmp end
    function e:addMP(n) self.mp = math.min(self.maxmp, self.mp + n) end
    function e:getID() return self.id end
    function e:getName() return self.name or 'Hurami' end
    function e:printToPlayer(m) W.printed[#W.printed + 1] = m end
    function e:getPartyWithTrusts() local t = { self } for _, x in ipairs(self.party) do t[#t + 1] = x end return t end
    function e:reloadParty() W.reloads = (W.reloads or 0) + 1 end
    function e:clearTrusts() W.cleared = W.cleared + 1; self.party = {} end
    function e:timer(ms, fn) W.timers[#W.timers + 1] = { fn = fn, who = self } end
    function e:getMaster() return self.master end
    function e:renameEntity() end
    function e:addListener(ev, id, fn) self.listeners[ev] = fn end
    function e:getZoneID() return 1 end
    function e:getMainJob() return opts.job or 1 end
    function e:hasJob() return true end
    function e:getFreeSlotsCount() return 10 end
    return setmetatable(e, { __index = function(_, k) return function() return 0 end end })
end

SpawnSquadMate = function(player, spec)
    local t = entity(xi.objType.TRUST, { level = spec.mlevel })
    t.spec, t.master = spec, player
    player.party[#player.party + 1] = t
    W.spawned[#W.spawned + 1] = t
    return t
end

__SQUAD_TEST = {}
assert(loadfile(SQUAD))()
local cmd = __SQUAD_TEST.hooks.commandObj
local function runTimers() local list = W.timers W.timers = {} for _, t in ipairs(list) do t.fn(t.who) end end
local function tick(t) t.listeners.TICK(t, 400) end

local function mate(id, slot, job, level, equip)
    return { id = id, slot = slot, name = 'Mate' .. id, mjob = job, sjob = 0, race = 1, face = 0, template = 0,
             jobs = { [job] = { level = level, exp = 0 } }, equip = equip or {} }
end

section('a mate never comes out above your level')
local player = entity(xi.objType.PC, { level = 10, id = 4 })
W.items[100] = 70; W.items[101] = 5
W.squad = { mate(1, 1, 1, 75, { [1] = { [255] = 1, [0] = 100, [4] = 101 } }) }
cmd.onTrigger(player, 'call', '1')
local t = W.spawned[1]
check(t and t.spec.mlevel == 10, 'a level 75 Warrior comes out at your level 10: ' .. tostring(t and t.spec.mlevel))
check(t.spec.equip[0] == nil and t.spec.equip[4] == 101, 'gear above level 10 is left off while synced (like the game\'s Level Sync), the rest is worn')
check((W.reloads or 0) >= 1, 'the party list is sent again after the rename (the last mate kept its template name)')
check(t:getLocalVar('SQUAD_CAP') == 10 and t:getLocalVar('SQUAD_OWN') == 75, 'it remembers the level it was synced to and its own level')

reset(); player = entity(xi.objType.PC, { level = 60, id = 4 }); W.items[100] = 70
W.squad = { mate(1, 1, 1, 40, { [1] = { [255] = 1, [0] = 100 } }) }
cmd.onTrigger(player, 'call', '1')
check(W.spawned[1].spec.mlevel == 40, 'a mate below your level keeps its own level (40 with you at 60)')
check(W.spawned[1].spec.equip[0] == 100, 'and wears all of its gear (not synced)')

reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
local sub = mate(1, 1, 1, 75); sub.sjob = 2; sub.jobs[2] = { level = 37, exp = 0 }
W.squad = { sub }
cmd.onTrigger(player, 'call', '1')
check(W.spawned[1].spec.mlevel == 30 and W.spawned[1].spec.slevel == 15, 'the support job follows the synced level: 30/15')
reset(); player = entity(xi.objType.PC, { level = 12, id = 4 })
W.squad = { sub }
cmd.onTrigger(player, 'call', '1')
check(W.spawned[1].spec.sjob == 0, 'below level 18 there is no support job, as for a real level 12 character')

section('your level changes: the squad follows')
reset(); player = entity(xi.objType.PC, { level = 10, id = 4 })
W.squad = { mate(1, 1, 1, 75), mate(2, 2, 3, 75) }
cmd.onTrigger(player, 'call', 'all'); runTimers()
check(#W.spawned == 2 and W.spawned[2].spec.mlevel == 10, 'both come out at 10')
local a = W.spawned[1]
tick(a); check(W.cleared == 0, 'nothing happens while your level is the same')
player.level = 11
player.engaged = true; tick(a); check(W.cleared == 0, 'you leveled to 11 while fighting: nobody is pulled out of the fight')
player.engaged = false; a.engaged = true; tick(a); check(W.cleared == 0, 'nor while a mate is still fighting')
a.engaged = false; W.clock = W.clock + 10; tick(a)
check(W.cleared == 1, 'once nobody is fighting, the squad is called again')
check(W.printed[#W.printed]:find('matches your level %(11%)') ~= nil, 'and you are told: ' .. tostring(W.printed[#W.printed]))
runTimers()
check(#W.spawned == 4 and W.spawned[3].spec.mlevel == 11 and W.spawned[4].spec.mlevel == 11, 'both are back, at 11')
tick(W.spawned[3]); tick(W.spawned[4]); check(W.cleared == 1, 'and it does not repeat')
-- the game's own Level Sync lowers your level: same thing
player.level = 5; W.clock = W.clock + 10; tick(W.spawned[3]); runTimers()
check(W.cleared == 2 and W.spawned[#W.spawned].spec.mlevel == 5, 'the game\'s Level Sync (your level 5) brings them down too')
player.level = 9; tick(W.spawned[#W.spawned]); check(W.cleared == 2, 'not more often than every few seconds')
-- a mate below both levels: no reason to call anyone again
reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
W.squad = { mate(1, 1, 1, 12) }
cmd.onTrigger(player, 'call', '1')
player.level = 31; W.clock = W.clock + 10; tick(W.spawned[1])
check(W.cleared == 0 and W.spawned[1]:getLocalVar('SQUAD_CAP') == 31, 'a level 12 mate with you going 30 -> 31 is left alone')
-- an ordinary Trust (no squad id) next to the squad is not counted as a mate to call again
reset(); player = entity(xi.objType.PC, { level = 20, id = 4 })
W.squad = { mate(1, 1, 1, 75) }
cmd.onTrigger(player, 'call', '1')
player.party[#player.party + 1] = entity(xi.objType.TRUST, { level = 20 })
player.level = 22; W.clock = W.clock + 10; tick(W.spawned[1]); runTimers()
check(W.cleared == 1 and #W.spawned == 2, 'only squad mates are called back (one mate, one new spawn)')

section('a mate levels up while out: back at the new level after the fight')
reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
W.squad = { mate(1, 1, 1, 20) }
cmd.onTrigger(player, 'call', '1')
local lv = W.spawned[1]
lv.getPacketName = function() return 'Mate1' end
lv.engaged = true; lv:setLocalVar('SQUAD_RELEVEL', 21); W.squad[1].jobs[1].level = 21
W.clock = W.clock + 10; tick(lv); check(W.cleared == 0, 'not while the mate is fighting')
lv.engaged = false; W.clock = W.clock + 10; tick(lv); check(W.cleared == 1, 'once the fight is over, called again')
check(W.printed[#W.printed]:find('Mate1 comes back at level 21') ~= nil, 'told: ' .. tostring(W.printed[#W.printed]))
runTimers(); check(W.spawned[#W.spawned].spec.mlevel == 21, 'back at 21')
reset(); player = entity(xi.objType.PC, { level = 20, id = 4 })
W.squad = { mate(1, 1, 1, 20) }
cmd.onTrigger(player, 'call', '1')
local cap = W.spawned[1]; cap:setLocalVar('SQUAD_RELEVEL', 21); W.clock = W.clock + 10; tick(cap)
check(W.cleared == 0 and cap:getLocalVar('SQUAD_RELEVEL') == 0, 'synced to your level 20: nothing would change, no re-call')

section('zoning: the mates who were out come back, no call timer')
reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
player.inMogHouse = function(self) return self.mh == true end
W.squad = { mate(1, 1, 1, 30), mate(2, 2, 3, 30), mate(3, 3, 4, 30) }
cmd.onTrigger(player, 'call', '1'); cmd.onTrigger(player, 'call', '2'); runTimers()
tick(W.spawned[1]); tick(W.spawned[2])
local calledVar = player.vars and player.vars['SQUAD_CALLED_1']
player.party = {} -- (zoning took them away)
local gameIn = OVERRIDES['xi.player.onGameIn']
check(gameIn ~= nil, 'squad.lua hooks your arrival in an area')
W.clock = W.clock + 20; local n0 = #W.spawned
check(gameIn(player, false, true) == 'base', 'the game\'s own arrival still runs')
runTimers()
check(#W.spawned == n0 + 2, 'the two mates who were out come back (not the third): ' .. (#W.spawned - n0))
-- through the Mog House: they wait for the next area
tick(W.spawned[#W.spawned]); tick(W.spawned[#W.spawned - 1]); player.party = {}
player.mh = true; n0 = #W.spawned; gameIn(player, false, true); runTimers()
check(#W.spawned == n0, 'not inside your Mog House')
player.mh = false; W.clock = W.clock + 600; gameIn(player, false, true); runTimers()
check(#W.spawned == n0 + 2, 'back out of the Mog House (even minutes later), they come back')
-- dismissed: they stay away
tick(W.spawned[#W.spawned]); cmd.onTrigger(player, 'dismiss'); n0 = #W.spawned
W.clock = W.clock + 5; gameIn(player, false, true); runTimers()
check(#W.spawned == n0, 'dismissed mates do not come back after zoning')
check(gameIn(player, true, false) == 'base', 'a fresh log in calls nobody')

section('dismissing one mate')
reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
W.squad = { mate(1, 1, 1, 30), mate(2, 2, 3, 30) }
cmd.onTrigger(player, 'call', 'all'); runTimers()
local gone = {}
SquadDismissMate = function(t) gone[#gone + 1] = t
    for i, x in ipairs(player.party) do if x == t then table.remove(player.party, i) break end end
    return true end
cmd.onTrigger(player, 'dismiss', '2')
check(#gone == 1 and gone[1] == W.spawned[2] and W.cleared == 0, 'only mate 2 leaves; nobody else is touched')
check(W.printed[#W.printed]:find('Mate2 has been dismissed') ~= nil, 'told: ' .. tostring(W.printed[#W.printed]))
cmd.onTrigger(player, 'dismiss', '2'); check(W.printed[#W.printed]:find('not out') ~= nil, 'a mate who is away: told so')
SquadDismissMate = nil; cmd.onTrigger(player, 'dismiss', '1')
check(W.printed[#W.printed]:find('UPDATE') ~= nil and #player.party == 1, 'an older server: told to update, nobody dismissed')
cmd.onTrigger(player, 'dismiss'); check(W.cleared == 1, '!squad dismiss alone still sends everyone off')

section('giving gear: one-of-a-kind items (squad_copy_items) stay with you')
reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
bit = bit or require('bit')
xi.itemFlag = { RARE = 0x8000 }
local deleted = {}
package.loaded['modules/custom/lua/squad_copy_items'] = { [500] = 'Test Ring' }
FindSquadItem = function(name) return tonumber(name) or 0 end
player.hasItem = function() return true end
player.delItem = function(_, id) deleted[#deleted + 1] = id end
player.delItemAt = function(_, id) deleted[#deleted + 1] = id; return true end
cmd.onTrigger(player, 'give', '500')
check(W.unlocked[500] and #deleted == 0, '!squad give: a one-of-a-kind item is unlocked and you keep it')
check(W.printed[#W.printed]:find('one of a kind') ~= nil, 'and you are told: ' .. tostring(W.printed[#W.printed]))
cmd.onTrigger(player, 'give', '501')
check(W.unlocked[501] and deleted[1] == 501, '!squad give: an ordinary item is taken as before')
local trust = entity(xi.objType.TRUST, { level = 30 }); trust.master = player; trust.getPacketName = function() return 'Mate1' end
trust.checkDistance = nil; player.checkDistance = function() return 1 end
W.unlocked = {}; deleted = {}
xi.squad.onTrade(player, trust, { { itemId = 500, slot = 3 }, { itemId = 502, slot = 4 } })
check(W.unlocked[500] and W.unlocked[502] and #deleted == 1 and deleted[1] == 502, 'trading: the one-of-a-kind piece stays with you, the ordinary one is taken')

section('giving gear: the launcher switch "you keep the item" (squad_config keep_gear)')
local KEEP = { call_cooldown_min = 5, spell_scrolls = false, keep_gear = true }
package.preload['modules/custom/lua/squad_config'] = function() return KEEP end
W.unlocked = {}; deleted = {}
cmd.onTrigger(player, 'give', '501')
check(W.unlocked[501] and #deleted == 0, 'switch on, !squad give: unlocked and nothing is taken')
check(W.printed[#W.printed]:find('you keep yours') ~= nil, 'and you are told: ' .. tostring(W.printed[#W.printed]))
xi.squad.onTrade(player, trust, { { itemId = 502, slot = 4 }, { itemId = 503, slot = 5 } })
check(W.unlocked[502] and W.unlocked[503] and #deleted == 0, 'switch on, trading: both unlocked, nothing is taken')
KEEP = { call_cooldown_min = 5, spell_scrolls = false, keep_gear = false }
W.unlocked = {}; deleted = {}
xi.squad.onTrade(player, trust, { { itemId = 504, slot = 4 } })
check(W.unlocked[504] and deleted[1] == 504, 'switch off: the piece is taken as before')
KEEP = { call_cooldown_min = 5, spell_scrolls = false }
W.unlocked = {}; deleted = {}
cmd.onTrigger(player, 'give', '505')
check(W.unlocked[505] and deleted[1] == 505, 'an older config file without the key: taken as before')
package.preload['modules/custom/lua/squad_config'] = nil; package.loaded['modules/custom/lua/squad_config'] = nil

section('resting with you')
reset(); player = entity(xi.objType.PC, { level = 30, id = 4 })
W.squad = { mate(1, 1, 3, 30), mate(2, 2, 1, 30) }
cmd.onTrigger(player, 'call', 'all'); runTimers()
local r1, r2 = W.spawned[1], W.spawned[2]
check(r1.listeners.TICK ~= nil, 'mates listen to every AI tick (COMBAT_TICK alone only fires while you fight)')
tick(r1); check(r1.anim == 0, 'standing while you stand')
player.anim = 33; tick(r1); tick(r2)
check(r1.anim == 33 and r2.anim == 33, 'you rest (/heal): both sit down')
local hp0 = r1.hp; W.clock = W.clock + 5; tick(r1); check(r1.hp == hp0, 'nothing in the first seconds, like the game')
W.clock = W.clock + 6; tick(r1); check(r1.hp == 60 and r1.mp == 20, 'after ten seconds: 10% of max HP and MP back (50 -> 60, 10 -> 20)')
tick(r1); check(r1.hp == 60, 'not every tick: every ten seconds')
for _ = 1, 10 do W.clock = W.clock + 10; tick(r1) end
check(r1.hp == 100 and r1.mp == 100, 'resting long enough: full HP and MP, never above')
r2.engaged = true; W.clock = W.clock + 10; local h2 = r2.hp; tick(r2)
check(r2.anim == 0 and r2.hp == h2, 'a mate pulled into a fight stands up and does not recover by resting')
r2.engaged = false
player.anim = 0; tick(r1); tick(r2)
check(r1.anim == 0 and r2.anim == 0, 'you stand up: they stand up')
r1.anim = 1; tick(r1); check(r1.anim == 1, 'a mate in another pose (fighting) is not touched when you are not resting')
player.anim = 33; player.engaged = true; r1.anim = 0; tick(r1); check(r1.anim == 0, 'you resting while engaged (cannot happen in the game, but) does not seat them')
player.engaged = false; r1.alive = false; tick(r1); check(r1.anim == 0, 'a KO\'d mate is left alone')

section('random starter outfits')
local gear = dofile(GEAR)
local function outfitFor(level, id)
    reset(); player = entity(xi.objType.PC, { level = 75, id = 4 })
    local m = mate(id or 1, 1, 1, level)
    W.squad = { m }
    cmd.onTrigger(player, 'call', '1')
    return W.spawned[1].spec.equip
end
local seen, allOk = {}, true
for i = 1, 40 do
    local e = outfitFor(1, i)
    if e[0] ~= gear[1][0] then allOk = false end
    seen[e[5]] = true
    for slot, item in pairs(e) do
        if slot >= 4 and slot <= 8 then
            local ok = false
            for _, entry in ipairs(gear.pools[1][slot]) do if entry[1] == item and entry[2] <= 1 then ok = true end end
            if not ok then allOk = false end
        end
    end
end
local kinds = 0 for _ in pairs(seen) do kinds = kinds + 1 end
check(allOk, 'every Warrior starts with the Onion Sword, and each armor piece is a plain level 1 piece a Warrior can wear')
check(kinds >= 2, 'level 1 mates do not all look alike: ' .. kinds .. ' different bodies over 40 new mates')
local hi, okLevels = 0, true
for i = 1, 40 do
    local e = outfitFor(30, i)
    for slot, item in pairs(e) do
        if slot >= 4 and slot <= 8 then
            for _, entry in ipairs(gear.pools[1][slot]) do if entry[1] == item then hi = math.max(hi, entry[2]) if entry[2] > 10 then okLevels = false end end end
        end
    end
end
check(okLevels and hi > 1, 'a mate who starts at level 30 gets starter pieces up to level 10 (highest drawn: ' .. hi .. ')')
local m2 = outfitFor(1, 1); local marks = 0 for _, e in ipairs(W.equip) do if e[3] == 255 then marks = marks + 1 end end
check(marks == 1, 'the outfit is saved once (the marker row), so it does not change on later calls')
-- no pools in the gear file (an old file): the fixed set as before
package.loaded['modules/custom/lua/squad_starter_gear'] = nil

io.write(string.format('\npassed %d, failed %d\n', passed, failed))
os.exit(failed == 0 and 0 or 1)
