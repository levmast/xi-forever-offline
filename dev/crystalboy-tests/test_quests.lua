local fails, n = 0, 0
local function ok(c, m) n = n + 1; if not c then fails = fails + 1; print('FAIL ' .. m) end end
local overrides, entries, commands = {}, {}, {}
package.preload['modules/module_utils'] = function()
  Module = {}; function Module:new() return { addOverride = function(_, k, f) overrides[k] = f end } end
end
package.preload['scripts/globals/npc_util'] = function() end
xi = { quest = { id = { jeuno = setmetatable({}, { __index = function(_, k) return k end }) } },
       item = setmetatable({}, { __index = function(_, k) return k end }),
       questStatus = { QUEST_AVAILABLE = 0, QUEST_ACCEPTED = 1, QUEST_COMPLETED = 2 },
       questLog = { JEUNO = 3 }, fameArea = { SANDORIA = 0, BASTOK = 1, WINDURST = 2, JEUNO = 3 }, zone = { LOWER_JEUNO = 245 },
       msg = { channel = { SAY = 0, NS_SAY = 9 } }, inv = { INVENTORY = 0 }, objType = { PC = 1, TRUST = 2 }, effect = { SIGNET = 253 },
       data = { fame = { rankPoints = { 0, 50, 125, 225, 325, 425, 613, 851, 1053 } } },
       module = { modifyInteractionEntry = function(f, fn) local q = { name = f:match('[^/]+$') }; q.qid = q.name:upper(); fn(q); entries[q.name] = q end,
                  registerCommand = function(name, c) commands[name] = c end } }
zones = { [245] = { text = { GIL_OBTAINED = 77 } } }
local tradeOK, given, confirmed = false, {}, 0
npcUtil = { tradeHasExactly = function(t, want) return tradeOK and (type(want) == 'table') end,
            giveItem = function(p, id) if p.full then return false end; given[#given + 1] = id; if type(id) == 'number' then p.bag[id] = true end; return true end,
            giveKeyItem = function(p, ki) p.kis[ki] = true end }
dofile(os.getenv('MOD'))
super = function() end
overrides['xi.server.onServerStart']()
local function P(name, fame)
  local p = { name = name or 'T', fame = fame or 1, qs = {}, said = {}, timers = 0, vars = {}, kis = {}, gil = 0, bag = {} }
  function p:getFameLevel() return self.fame end
  function p:getQuestStatus(log, id) return self.qs[id] or 0 end
  function p:hasCompletedQuest(log, id) return self.qs[id] == 2 end
  function p:confirmTrade() confirmed = confirmed + 1 end
  function p:printToPlayer(t, ch, nm) table.insert(self.said, { t, ch, nm }) end
  function p:timer(ms, fn) self.timers = self.timers + 1; fn(self) end
  function p:setFame(a, v) self['f' .. a] = v end
  function p:getName() return self.name end
  function p:getCharVar(v) return self.vars[v] or 0 end
  function p:setCharVar(v, x) self.vars[v] = x end
  function p:hasItem(id) return self.bag[id] == true end
  function p:addGil(g) self.gil = self.gil + g end
  function p:messageSpecial() end
  function p:getZoneID() return 245 end
  function p:hasKeyItem(k) return self.kis[k] == true end
  function p:delKeyItem(k) self.kis[k] = nil end
  function p:getObjType() return 1 end
  function p:hasStatusEffect(e) return self.signet and e == 253 end
  return p
end
local NOACT = {}
for _, q in pairs(entries) do
  q.noAction = function() return NOACT end
  q.begin = function(_, p) p.qs[q.qid] = 1 end
  q.complete = function(_, p) p.qs[q.qid] = 2; return true end
end
local PARTS = { 'The_Gobbiebag_Part_I', 'The_Gobbiebag_Part_II', 'The_Gobbiebag_Part_III', 'The_Gobbiebag_Part_IV', 'The_Gobbiebag_Part_V', 'The_Gobbiebag_Part_VI' }
-- what Bluffnix does now: exactly one section of one part may match
local function active(p)
  local hits = {}
  for k, f in ipairs(PARTS) do
    for si, sec in ipairs(entries[f].sections) do
      if sec.check(p, p.qs[entries[f].qid] or 0) then hits[#hits + 1] = { k, si, sec } end
    end
  end
  return hits
end
local function talkTo(p) p.said = {}; local h = active(p); ok(#h == 1, 'one thing at a time (' .. #h .. ')'); if h[1] then return h[1][3][245]['Bluffnix'].onTrigger(p), h[1] end end
local function trade(p) p.said = {}; local h = active(p); return h[1][3][245]['Bluffnix'].onTrade(p, nil, {}) end
local function said(p, pat) for _, l in ipairs(p.said) do if l[1]:find(pat) then return l end end end
local function lines(p) for _, l in ipairs(p.said) do ok(#l[1] <= 150, 'chat line fits') end end

ok(entries['The_Gobbiebag_Part_X'] ~= nil, 'all ten parts rebuilt')
local A = P('Alice', 2)
talkTo(A); ok(said(A, 'does not know you'), 'fame 2: Bluffnix does not know you')
A.fame = 3; local r = talkTo(A)
ok(r == NOACT and A.qs.THE_GOBBIEBAG_PART_I == 1 and said(A, 'crystal heart'), 'Part I starts at fame 3 with the story')
local l = said(A, 'Psst'); ok(l[3] == 'Bluffnix' and l[2] == 9, 'spoken by Bluffnix'); lines(A)
tradeOK = false; trade(A); ok(said(A, 'memory box waits'), 'wrong trade: reminder')
tradeOK = true; A.full = true; trade(A); ok(confirmed == 0 and A.qs.THE_GOBBIEBAG_PART_I == 1, 'full bag: nothing taken')
A.full = false; trade(A); ok(given[#given] == 8100 and A.qs.THE_GOBBIEBAG_PART_I == 2 and said(A, 'Crystal Boy'), 'Part I gives the Crystal Boy')
talkTo(A); ok(said(A, 'does not know you'), 'Part II needs fame 4')
A.fame = 4; talkTo(A); trade(A); ok(given[#given] == 8101 and A.qs.THE_GOBBIEBAG_PART_II == 2, 'Part II gives Jueno Recollection I')
-- fame 4: Part III (fame 5) not yet -> low fame takes the turn
talkTo(A); ok(said(A, 'does not know you'), 'Part III needs fame 5')
A.fame = 5
A.bag[8101] = nil; local _, h = talkTo(A); ok(h[1] == 3 and said(A, 'second part'), 'next part starts before the hint about the unfinished game')
lines(A)
trade(A); ok(given[#given] == 8102 and A.bag[8102], 'Part III gives Jueno Recollection II')
talkTo(A); ok(said(A, 'last part'), 'Part IV opens at fame 5'); trade(A); ok(given[#given] == 8103, 'Part IV gives Jueno Recollection III')
talkTo(A); ok(said(A, 'does not know you'), 'Part V needs fame 6'); A.fame = 6
talkTo(A); ok(said(A, 'fourth'), 'Part V story'); lines(A); trade(A); ok(given[#given] == 8104, 'Part V gives Jueno Recollection IV')
A.fame = 9
-- Part VI has no reward: closed. Now the Recollection hints: Mana first (no tablet in the bag)
talkTo(A); ok(said(A, 'Where is the Recollection'), 'Jueno Recollection I not in the bag: asks for it')
A.bag[8101] = true; talkTo(A); ok(said(A, 'Not to the end yet'), 'not finished yet')
-- finish Legend II via the claims file (title of 8103), claim works even though Mana is still pending
local dir = 'C:\\Ashita-v4beta-main\\config\\addons\\crystalboy\\claims\\Alice\\claims.lua'
local RT = os.getenv('T3') or 'SAGA2 DX'
local f = io.open(dir, 'w'); f:write('return {\n    [' .. string.format('%q', RT) .. '] = { delivered = false },\n}\n'); f:close()
talkTo(A); ok(A.gil == 20000 and A.kis[2841] and said(A, 'whole legend ends'), 'Jueno III handed in: 20,000 gil, Memory of Jueno III, its own story')
ok(A.vars['[CB]Done8103'] == 1, 'recorded once')
talkTo(A); ok(said(A, 'Not to the end yet') and A.gil == 20000, 'back to the Mana hint, nothing paid twice')
os.remove(dir)
-- GM finish for the others
local fc = commands['cbfinish']; ok(fc and fc.cmdprops.permission >= 1, 'GM-only finish command')
fc.onTrigger(A, '8101'); talkTo(A); ok(A.gil == 30000 and A.kis[1634], 'Jueno I: 10,000 gil and Memory of Jueno I')
A.bag[8102] = true; fc.onTrigger(A, '8102'); talkTo(A); ok(A.gil == 45000 and A.kis[2605], 'Jueno II: 15,000 gil')
fc.onTrigger(A, '8104'); A.full = true; talkTo(A); ok(said(A, 'too full') and A.gil == 45000, 'full bag: nothing given')
A.full = false; talkTo(A); ok(A.gil == 70000 and A.kis[2716], 'Jueno IV: 25,000 gil')
talkTo(A); ok(said(A, 'still thinks about that story'), 'all done: thank-you')
fc.onTrigger(A, '8104 reset'); ok(not A.kis[2716] and A.vars['[CB]Done8104'] == 0, '!cbfinish 8104 reset')
fc.onTrigger(A, '9999'); ok(said(A, '!cbfinish'), 'unknown id: usage')
-- exp bonus: one percent per memory key item, Signet only, players only
local calc = overrides['xi.experiencePoints.calculate']
super = function() return { exp = 300 } end
local E = P('E')
ok(calc(E, nil, {}).exp == 300, 'no memories: no bonus')
E.kis[1634], E.kis[2605], E.kis[2841] = true, true, true
ok(calc(E, nil, {}).exp == 300, 'without Signet: no bonus')
E.signet = true; ok(calc(E, nil, {}).exp == 309, 'three memories + Signet: +3%')
local M = P('M'); M.kis[1634] = true; M.signet = true; function M:getObjType() return 2 end
ok(calc(M, nil, {}).exp == 300, 'not for squad mates')
super = function() return nil end; ok(calc(E, nil, {}) == nil, 'no exp: untouched')
-- fame command
local c = commands['cbfame']; ok(c and c.cmdprops.permission >= 1, 'GM-only fame command')
local G = P('G'); c.onTrigger(G, 5); ok(G.f0 == 325 and G.f1 == 325 and G.f2 == 325, 'sets the three nations')
c.onTrigger(G, 12); ok(said(G, '!cbfame'), 'bad level: usage')
print(string.format('quests: %d checks, %d failed', n, fails))
