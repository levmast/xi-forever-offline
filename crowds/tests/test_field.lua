-- Stand-in combat world for crowds_field.lua (via crowds.lua). Run from a folder holding modules/custom/lua/*:
--   texlua test_field.lua .
local DIR = arg[1] or '.'
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
math.randomseed(tonumber(os.getenv('SEED') or '') or 4242)

local passes, failures = 0, 0
local function check(name, cond, detail)
    if cond then passes = passes + 1; print('ok   ' .. name)
    else failures = failures + 1; print('FAIL ' .. name .. (detail and ('  -- ' .. tostring(detail)) or '')) end
end

local NOW = 0
local realTime = os.time
os.time = function(t) if t then return realTime(t) end return 1800000000 + math.floor(NOW / 1000) end

xi = {
    objType = { NPC = 2, MOB = 1 }, status = { NORMAL = 0, DISAPPEAR = 3 },
    animationString = { STATUS_VISIBLE = 'deru', STATUS_DISAPPEAR = 'kesu' },
    emoteMode = { ALL = 0, MOTION = 2 }, emote = { WAVE = 8, BOW = 1, THINK = 32 },
    msg = { channel = { SAY = 0, SHOUT = 1, SYSTEM_3 = 29 } }, module = {}, player = {},
    allegiance = { MOB = 0, PLAYER = 1 }, zone = { GM_HOME = 210 }, mobMod = { NO_DROPS = 38 },
    roamFlag = { SCRIPTED = 256 }, mod = { HPP = 3, DEFP = 63, ACC = 25, ATTP = 62, MP = 5 },
}
local commands, overrides = {}, {}
xi.module.registerCommand = function(n, t) commands[n] = t end
Module = {}; Module.__index = Module
function Module:new(n) return setmetatable({ name = n }, Module) end
function Module:addOverride(path, fn) overrides[path] = fn end
package.preload['modules/module_utils'] = function() return true end
super = function() return nil end

-- world -----------------------------------------------------------------------------------------------
local timers, ents, nextId = {}, {}, 1000
local log = { casts = {}, ws = {}, says = {}, pulls = {}, deaths = 0, spawnedAllies = 0 }
local E = {}; E.__index = E
local function newEnt(t) nextId = nextId + 1; t.id = t.id or nextId; t.mods = {}; ents[t.id] = t; return setmetatable(t, E) end
function E:getID() return self.id end
function E:getPos() return { x = self.x, y = self.y or 0, z = self.z, rot = 0 } end
function E:getName() return self.name end
function E:getZoneID() return self.zone.id end
function E:getZone() return self.zone end
function E:timer(ms, fn) table.insert(timers, { at = NOW + ms, e = self, fn = fn }) end
function E:getAllegiance() return self.alleg end
function E:isAlive() return self.hp > 0 and not self.gone end
function E:isNM() return self.nm or false end
function E:isEngaged() return self.target ~= nil end
function E:getTarget() return self.target end
function E:getMainLvl() return self.lvl end
function E:getHP() return self.hp end
function E:getMaxHP() return self.maxhp end
function E:getHPP() return math.floor(self.hp * 100 / self.maxhp) end
function E:setHP(v) self.hp = math.max(0, math.min(self.maxhp, v)) end
function E:getMP() return self.mp or 0 end
function E:getMaxMP() return self.maxmp or 0 end
function E:setMP(v) self.mp = math.max(0, math.min(self.maxmp or 0, v)) end
function E:getTP() return self.tp or 0 end
function E:setTP(v) self.tp = v end
function E:addMod(m, v) self.mods[m] = (self.mods[m] or 0) + v end
function E:updateHealth()
    self.maxhp = math.floor(self.basehp * (100 + (self.mods[3] or 0)) / 100)
    self.maxmp = self.mods[5] or 0
end
function E:setMobMod() end
function E:setRoamFlags() end
function E:setSpawn() end
function E:spawn() end
function E:setAllegiance(a) self.alleg = a end
function E:setBaseSpeed() end
function E:setMagicCastingEnabled() end
function E:setMobAbilityEnabled() end
function E:setAnimation(a) self.anim = a end
function E:entityAnimationPacket() end
function E:addListener(ev, name, fn) self.listeners = self.listeners or {}; self.listeners[ev] = fn end
function E:pathTo(x, y, z) self.path = { x = x, z = z } end
function E:clearPath() self.path = nil end
function E:isFollowingPath() return self.path ~= nil end
function E:addEnmity(other, ce, ve)
    self.enmity = self.enmity or {}
    self.enmity[other.id] = (self.enmity[other.id] or 0) + (ce or 0) + (ve or 0)
    local best, bv
    for id, v in pairs(self.enmity) do
        local o = ents[id]
        if o and o:isAlive() and (not bv or v > bv) then best, bv = o, v end
    end
    self.target = best
end
function E:castSpell(id, target)
    table.insert(log.casts, { by = self, id = id, target = target, at = NOW })
    if self.mp then self.mp = math.max(0, self.mp - 10) end
    if target and target.alleg == self.alleg then
        if id <= 4 then target:setHP(target.hp + 40 * id) end
    elseif target then
        target:setHP(target.hp - 20)
        target:addEnmity(self, 50, 50)
    end
end
function E:useMobAbility(id, target)
    table.insert(log.ws, { by = self, id = id, at = NOW })
    if target then target:setHP(target.hp - 60) end
end
function E:printToPlayer(text, kind, name)
    table.insert(log.says, { text = text, kind = kind, name = name, at = NOW })
end
function E:getLocalVar(k) self.vars = self.vars or {}; return self.vars[k] or 0 end
function E:setLocalVar(k, v) self.vars = self.vars or {}; self.vars[k] = v end

local Z = {}; Z.__index = Z
local zones = {}
function Z:getID() return self.id end
function Z:getPlayers() local t = {} for _, p in pairs(self.players) do t[#t + 1] = p end return t end
function Z:getMobs() local t = {} for _, e in pairs(ents) do if e.kind == 'mob' and e.zone == self and not e.gone then t[#t + 1] = e end end return t end
function Z:isNavigablePoint(p) return math.abs(p.x) < 300 and math.abs(p.z) < 300 end
function Z:insertDynamicEntity(t)
    assert(t.objtype == xi.objType.MOB and t.allegiance == 1 and t.groupId == 1 and t.groupZoneId == 210)
    assert(#t.look == 42, 'look')
    log.spawnedAllies = log.spawnedAllies + 1
    return newEnt({ kind = 'mob', zone = self, x = t.x, z = t.z, alleg = 0, lvl = t.minLevel, basehp = 40 + t.minLevel * 14,
        hp = 1, maxhp = 1, name = t.packetName, ally = true })
end
function GetZone(id) return zones[id] end
function GetMobByID(id) local e = ents[id]; if e and not e.gone then return e end return nil end
function GetNPCByID() return nil end
function DespawnMob(id) local e = ents[id]; if e then e.gone = true end end
function DisallowRespawn() end

local function makeZone(id) zones[id] = setmetatable({ id = id, players = {} }, Z); return zones[id] end
local function enemy(zone, x, z, lvl, strong)
    local hp = (strong and 4000 or (60 + lvl * 16))
    return newEnt({ kind = 'mob', zone = zone, x = x, z = z, alleg = 0, lvl = lvl, hp = hp, maxhp = hp, basehp = hp,
        name = 'Snipper_' .. nextId, home = { x = x, z = z }, strong = strong })
end

-- combat: one step per second
local function combatStep()
    for _, e in pairs(ents) do
        if e.kind == 'mob' and e:isAlive() then
            -- move: path first, else chase the target
            local goal = e.path or (e.target and e.target:isAlive() and { x = e.target.x, z = e.target.z })
            if goal then
                local dx, dz = goal.x - e.x, goal.z - e.z
                local d = math.sqrt(dx * dx + dz * dz)
                local step = e.ally and 6 or 4
                if d <= step then
                    e.x, e.z = goal.x, goal.z
                    if e.path then e.path = nil end
                else
                    e.x, e.z = e.x + dx / d * step, e.z + dz / d * step
                end
            end
            -- melee
            local t = e.target
            if t and not t:isAlive() then e.target = nil; if e.enmity then e.enmity[t.id] = nil end; t = nil end
            if t and math.sqrt((t.x - e.x) ^ 2 + (t.z - e.z) ^ 2) <= 4 then
                local dmg = e.ally and (3 + e.lvl) or (e.strong and 80 or (2 + math.floor(e.lvl * 0.9)))
                t:setHP(t.hp - dmg)
                e.tp = (e.tp or 0) + 150
                if not t.ally then t:addEnmity(e, dmg, dmg) end
                if t.ally and not t.target and t.enmity == nil then end
                if t.hp <= 0 then
                    if t.listeners and t.listeners.DEATH then
                        log.deaths = log.deaths + 1
                        t.listeners.DEATH(t)
                    end
                    if not t.ally then t.respawnAt = NOW + 300000 end
                end
            end
        end
        -- enemy respawn
        if e.kind == 'mob' and not e.ally and e.hp <= 0 and e.respawnAt and NOW >= e.respawnAt then
            e.hp, e.target, e.enmity, e.x, e.z, e.respawnAt = e.maxhp, nil, nil, e.home.x, e.home.z, nil
        end
    end
end

local function advance(ms)
    local stop = NOW + ms
    local nextStep = math.floor(NOW / 1000) * 1000 + 1000
    while true do
        table.sort(timers, function(a, b) return a.at < b.at end)
        local t = timers[1]
        local at = math.min(t and t.at or math.huge, nextStep)
        if at > stop then break end
        if t and t.at <= nextStep then
            table.remove(timers, 1)
            NOW = t.at
            if not t.e.gone and (t.e.kind ~= 'mob' or t.e:isAlive() or t.e.kind == 'pc') then t.fn(t.e) end
        else
            NOW = nextStep
            combatStep()
            nextStep = nextStep + 1000
        end
    end
    NOW = stop
end

-- data: built from the real server files (sandbox copy), plus a test area
local function writeConfig(text) local f = assert(io.open(DIR .. '/modules/custom/lua/crowds_config.lua', 'w')); f:write(text); f:close() end
writeConfig("return { enabled = true, per_zone = 0, chat = false, field = true, field_parties = 1 }\n")
local data = require('modules/custom/lua/crowds_data')
data.field = data.field or {}
data.field[103] = 'Valkurm_Dunes'
local crowds = dofile(DIR .. '/modules/custom/lua/crowds.lua')
check('crowds.lua loads with the field module', commands.crowd ~= nil)

local valk = makeZone(103)
local player = newEnt({ kind = 'pc', zone = valk, x = 0, z = 0, name = 'Hurami', hp = 100, maxhp = 100 })
-- monsters: a field of level 12-18 crabs and bees, some near you
local nearYou = {}
for i = 1, 60 do
    local x, z = math.random(-250, 250), math.random(-250, 250)
    local m = enemy(valk, x, z, math.random(12, 18))
    if math.sqrt(x * x + z * z) < 40 then nearYou[m.id] = true end
end
for i = 1, 4 do local m = enemy(valk, math.random(-30, 30), math.random(-30, 30), 15); nearYou[m.id] = true end
valk.players[player.id] = player
overrides['xi.player.onGameIn'](player, false, true)
advance(10000)
local field = require('modules/custom/lua/crowds_field')
local zp = field.parties[103]
check('a party set up camp after you arrived', zp and #zp.list == 1, zp and #zp.list)
local party = zp and zp.list[1]
local camp = party and party.camp
check('camp is at least 50 yalms from you', camp and math.sqrt(camp.x ^ 2 + camp.z ^ 2) >= 50, camp and math.sqrt(camp.x ^ 2 + camp.z ^ 2))
local roles, jobs = {}, {}
for _, m in ipairs(party.members) do roles[m.role] = (roles[m.role] or 0) + 1; jobs[#jobs + 1] = m.job .. (m.puller and '*' or '') end
check('party: 5-6 members, a tank, a healer, a support, a puller (' .. table.concat(jobs, ' ') .. ', lvl ' .. party.lvl .. ')',
    #party.members >= 5 and roles.tank == 1 and roles.healer == 1 and roles.support == 1)
check('party level is a few levels under the monsters (Tough to IT)', party.lvl >= 6 and party.lvl <= 15, party.lvl)

-- 40 minutes of camping
local pulledNearYou, pulls, maxStates = 0, 0, {}
local watching = false
local origChoose = nil
local seenPulling = {}
for sec = 1, 40 * 60, 5 do
    advance(5000)
    if party.pullingId and not seenPulling[party.pullingId .. ':' .. (party.pullStart or 0)] then
        seenPulling[party.pullingId .. ':' .. (party.pullStart or 0)] = true
        pulls = pulls + 1
        local m = ents[party.pullingId]
        if not watching and m and math.sqrt((m.x - player.x) ^ 2 + (m.z - player.z) ^ 2) < 40 then pulledNearYou = pulledNearYou + 1 end
    end
    maxStates[party.state] = true
    if party.over then break end
    if sec > 10 * 60 and not watching then
        -- after 10 minutes, walk over and watch them from their camp
        watching = true
        player.x, player.z = party.camp.x + 3, party.camp.z
    end
    if watching then player.x, player.z = party.camp.x + 3, party.camp.z end
end
check(string.format('pulls happened (%d) and monsters died (%d kills)', pulls, party.kills), pulls >= 5 and party.kills >= 4)
check('never pulled a monster within 40 yalms of you (while you were away from their camp)', pulledNearYou == 0, pulledNearYou)
local cures, nukes, mb, sleeps = 0, 0, 0, 0
for _, c in ipairs(log.casts) do
    if c.id >= 1 and c.id <= 4 then cures = cures + 1 end
end
for _, s in ipairs(log.says) do
    if s.text:find('^MB ') then mb = mb + 1 end
end
local closes, opens = 0, 0
for _, s in ipairs(log.says) do
    if s.text:find('%-> %u%l+!$') then closes = closes + 1 end
    if s.text:find('SC open') then opens = opens + 1 end
end
check(string.format('healer cured hurt members (%d cures)', cures), cures >= 3)
check(string.format('weapon skills used (%d), skillchains closed (%d)', #log.ws, closes), #log.ws >= 4 and closes >= 1)
check(string.format('magic bursts (%d) only right after a closed skillchain (%d)', mb, closes), mb <= closes)
local said = {}
for i = 1, math.min(#log.says, 12) do said[#said + 1] = log.says[i].name .. ': ' .. log.says[i].text end
print('     party talk: ' .. table.concat(said, ' | '))
check(string.format('watching at their camp you hear party talk (%d lines)', #log.says), #log.says >= 10)
local heardFar = #log.says
player.x, player.z = party.camp.x + 200, party.camp.z
log.says = {}
advance(5 * 60000)
check('far from their camp: no party talk', #log.says == 0, #log.says)
player.x, player.z = 0, 0

-- an add: a second monster attacks a member while they fight -> it gets slept (or called) and fought next
local t0 = NOW
local added = false
for _ = 1, 900 do
    advance(1000)
    if party.state == 'fight' and party.target and not added then
        local a = enemy(valk, party.camp.x + 5, party.camp.z, party.lvl + 3)
        local victim
        for _, m in ipairs(party.members) do local e = GetMobByID(m.id); if e and e:isAlive() then victim = e end end
        a:addEnmity(victim, 10, 10)
        added = a
    end
    if added and party.adds[added.id] then break end
end
check('an add is noticed (slept or called "add!"), unless it already lost its target', added and (party.adds[added.id] ~= nil or not added:isAlive() or added.target == nil))
local sleptOrCalled = 0
for _, c in ipairs(log.casts) do if added and c.target == added then sleptOrCalled = sleptOrCalled + 1 end end
print('     casts on the add: ' .. sleptOrCalled)
advance(3 * 60000)

-- leaving the area: parties go home after 5 minutes
valk.players = {}
player.zone = makeZone(230)
advance(4 * 60000)
check('party still there 4 minutes after you left', #zp.list == 1 or party.over)
advance(3 * 60000)
check('party gone 5+ minutes after you left', #zp.list == 0)

-- coming back: a new party (after its wait)
valk.players[player.id] = player
player.zone = valk
overrides['xi.player.onGameIn'](player, false, true)
advance(15 * 60000)
check('coming back brings a party again', #zp.list == 1, #zp.list)

-- a wipe: an area of monsters far too strong
local hard = makeZone(104); data.field[104] = 'Jugner_Forest'
for i = 1, 40 do enemy(hard, math.random(-250, 250), math.random(-250, 250), 20, true) end
local p2 = newEnt({ kind = 'pc', zone = hard, x = 0, z = 0, name = 'Hurami', hp = 100, maxhp = 100 })
hard.players[p2.id] = p2
overrides['xi.player.onGameIn'](p2, false, true)
advance(10000)
local hp = field.parties[104]
local hparty = hp and hp.list[1]
local deathsBefore = log.deaths
advance(20 * 60000)
check(string.format('against monsters far too strong they die (%d deaths) and the party ends', log.deaths - deathsBefore),
    hparty and hparty.over and log.deaths - deathsBefore >= 2)
check('after a wipe a new party waits 6-12 minutes', hp.nextAt - os.time() <= 12 * 60 and (hparty and hparty.over))

-- a level 40s camp: PLD/NIN tanks, Flash/Utsusemi, Refresh/Haste or songs, Sleep on adds
local mid = makeZone(106); data.field[106] = 'Crawlers_Nest'
for i = 1, 60 do enemy(mid, math.random(-250, 250), math.random(-250, 250), math.random(44, 50)) end
local p4 = newEnt({ kind = 'pc', zone = mid, x = 0, z = 0, name = 'Hurami', hp = 100, maxhp = 100 })
mid.players[p4.id] = p4
log.casts = {}
overrides['xi.player.onGameIn'](p4, false, true)
advance(10000)
local mparty = field.parties[106] and field.parties[106].list[1]
local mj = {}
for _, m in ipairs(mparty.members) do mj[#mj + 1] = m.job .. (m.puller and '*' or '') end
print('     40s party: lvl ' .. mparty.lvl .. ' ' .. table.concat(mj, ' '))
local tankJob = mparty.members[1].job
check('40s tank is PLD, NIN or WAR', tankJob == 'PLD' or tankJob == 'NIN' or tankJob == 'WAR', tankJob)
local addMade = 0
for sec = 1, 30 * 60, 5 do
    advance(5000)
    p4.x, p4.z = mparty.camp.x + 3, mparty.camp.z
    if mparty.state == 'fight' and mparty.target and addMade < 3 and math.random() < 0.05 then
        local a = enemy(mid, mparty.camp.x + 6, mparty.camp.z, mparty.lvl + 2)
        for _, m in ipairs(mparty.members) do local e = GetMobByID(m.id); if e and e:isAlive() then a:addEnmity(e, 5, 5) break end end
        addMade = addMade + 1
    end
    if mparty.over then break end
end
local byId = {}
for _, c in ipairs(log.casts) do byId[c.id] = (byId[c.id] or 0) + 1 end
local spells = data.spells
local function n(name) return spells[name] and byId[spells[name][1]] or 0 end
local tankSpell = n('flash') + n('utsusemi_ichi') + n('utsusemi_ni')
check(string.format('tank uses Flash/Utsusemi (%d) when PLD/NIN', tankSpell), tankSpell > 0 or tankJob == 'WAR')
local supportSpells = n('refresh') + n('haste') + n('valor_minuet') + n('valor_minuet_ii') + n('valor_minuet_iii') + n('mages_ballad') + n('slow') + n('paralyze')
check(string.format('support refreshes/hastes/sings/debuffs (%d casts)', supportSpells), supportSpells > 0)
check(string.format('Dia on the monsters (%d)', n('dia') + n('dia_ii')), n('dia') + n('dia_ii') > 0)
local sleeps = n('sleep') + n('sleep_ii') + n('foe_lullaby')
print(string.format('     sleeps on adds: %d (adds made: %d), kills %d', sleeps, addMade, mparty.kills))
check('sleeps only go on adds (no sleep spam)', sleeps <= addMade + 4, sleeps .. ' / ' .. addMade)

-- switches
commands.crowd.onTrigger(player, 'field', 'off')
advance(10000)
check('!crowd field off sends every party home', #zp.list == 0 and #(field.parties[104].list) == 0)
commands.crowd.onTrigger(player, 'field', 'on')
advance(70000)
check('!crowd field on brings them back', #zp.list == 1, #zp.list)
player.said = nil
local msgs = {}
player.printToPlayer = function(self, text) msgs[#msgs + 1] = text end
commands.crowd.onTrigger(player, 'field')
check('!crowd field shows the party', msgs[#msgs] and msgs[#msgs]:find('lvl %d+') ~= nil, msgs[#msgs])

-- an area without field parties
local town = makeZone(245)
local p3 = newEnt({ kind = 'pc', zone = town, x = 0, z = 0, name = 'Hurami' })
p3.printToPlayer = function(self, text) msgs[#msgs + 1] = text end
commands.crowd.onTrigger(p3, 'field', 'test')
check('!crowd field test in a town says it is not a field area', msgs[#msgs]:find('not a field party area') ~= nil, msgs[#msgs])

putBack()
print(string.format('\n%d passed, %d failed', passes, failures))
os.exit(failures == 0 and 0 or 1)
