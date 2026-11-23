"""(Hasuko, 2026-11-22) "I'm a WHM. I shouldn't have to pull my weapon. I should be as far back as possible and/or
resting during pulls, standing up to heal, and back to resting." Yenkei: "I was hoping to get a squad attack button
too."

!squad attack sends the squad at the monster you have targeted without you engaging, also while you sit and rest;
!squad stop calls it back. The Squads menu has the two buttons (servermenu 1.26j). The order is three local vars on
the player (SQUAD_ATTACK_TARGET / _ZONE / _SEEN) that trust_controller.cpp reads in OrderedTarget().

The Lua is run as written (the order function, the command and the rest tick are cut out of squad.lua and run with
stand-in players, monsters and mates); the C++ can only be read here, so those checks are on its text.
Run: python test_attack_order.py [server folder]      (default C:\\ffxi-local\\server; needs lupa)
"""
import os
import re
import sys
from lupa import luajit21 as lupa

SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


def read(*parts):
    with open(os.path.join(*parts), encoding='utf-8') as handle:
        return handle.read().replace('\r\n', '\n')


squad = read(SERVER, 'modules', 'custom', 'lua', 'squad.lua')
cpp = read(SERVER, 'src', 'map', 'ai', 'controllers', 'trust_controller.cpp')
hdr = read(SERVER, 'src', 'map', 'ai', 'controllers', 'trust_controller.h')
menu = read(KIT, 'addons-src', 'servermenu', 'servermenu.lua')

# ---------------------------------------------------------------- the pieces of squad.lua, run as written
order_src = squad[squad.index('-- your camp, if it is in the zone you are in'):squad.index('restTick = function(mob)')]
rest_src = squad[squad.index('restTick = function(mob)'):squad.index('-- Called from each mate\'s tick: when your level no longer matches')]
cmd_at = squad.index("    if action == 'attack' or action == 'stop' then")
cmd_src = squad[cmd_at:squad.index("    if action == 'pose' and player:getGMLevel() > 0 then", cmd_at)]
check('the order function, the rest tick and the command are found in squad.lua', all((order_src, rest_src, cmd_src)))

lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute(r'''
xi = { squad = {}, objType = { PC = 1, MOB = 4, TRUST = 128, NPC = 2 }, allegiance = { MOB = 0, PLAYER = 1 },
       animation = { NONE = 0, HEALING = 33, ATTACK = 1 } }
said, camps, out, clock = {}, {}, {}, 1000
os.time = function() return clock end
function say(player, text) said[#said + 1] = text end
function squadTrusts(player) return out end
REST_FIRST_SEC, REST_EVERY_SEC, REST_HP_PERCENT, REST_MP_PERCENT = 20, 10, 10, 10

local function entity(t)
    t.vars = t.vars or {}
    function t:getLocalVar(k) return self.vars[k] or 0 end
    function t:setLocalVar(k, v) self.vars[k] = v end
    function t:getID() return self.id end
    function t:getObjType() return self.objType end
    function t:getZoneID() return self.zone or 100 end
    function t:isEngaged() return self.engaged == true end
    function t:isAlive() return self.alive ~= false end
    function t:getAnimation() return self.animation or 0 end
    function t:setAnimation(a) self.animation = a end
    function t:getPos() return { x = self.x or 0, y = 0, z = self.z or 0 } end
    function t:getName() return self.name end
    function t:getTargID() return self.targid end
    function t:getAllegiance() return self.allegiance or 0 end
    function t:getCursorTarget() return self.cursor end
    function t:checkDistance(o) return math.sqrt(((self.x or 0) - (o.x or 0)) ^ 2 + ((self.z or 0) - (o.z or 0)) ^ 2) end
    function t:disengage() self.engaged = false; self.letGo = true end
    function t:getMaster() return self.master end
    function t:getHP() return self.hp or 100 end
    function t:getMaxHP() return 100 end
    function t:getMP() return self.mp or 50 end
    function t:getMaxMP() return 50 end
    function t:getMainLvl() return 30 end
    function t:addHP() end
    function t:addMP() end
    function t:getCharVar() return 0 end
    return t
end
function newPlayer() return entity({ id = 1, objType = 1, name = 'Hasuko' }) end
function newMob(t) t.objType = t.objType or 4; t.targid = t.targid or 321; t.name = t.name or 'Wild_Rabbit'; return entity(t) end
function newMate(t) t.objType = 128; return entity(t) end
function last() return said[#said] or '' end
local restTick
''' + order_src + '''
''' + rest_src + '''
_G.restTick = restTick
function command(player, action, arg1)
''' + cmd_src + '''
    return 'fell through'
end
''')
ev = lua.eval
run = lua.execute

# nothing targeted, or not a monster
run("p = newPlayer(); out = { newMate({ id = 11 }) }; r = xi.squad.attackOrder(p, false)")
check('nothing targeted: not sent, and it says to target a monster first', ev("r == false and last():find('Target a monster first', 1, true) ~= nil"))
check('...and no order is written', ev("p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))
run("p.cursor = newMob({ objType = 1, name = 'Gilder' }); r = xi.squad.attackOrder(p, false)")
check('another player targeted: not sent', ev("r == false and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))
run("p.cursor = newMob({ objType = 2, name = 'Moogle' }); r = xi.squad.attackOrder(p, false)")
check('an NPC targeted: not sent', ev("r == false and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))
run("p.cursor = newMob({ allegiance = 1, name = 'Charmed_Pet' }); r = xi.squad.attackOrder(p, false)")
check('a monster on the players\' side: not sent', ev("r == false and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))
run("p.cursor = newMob({ alive = false }); r = xi.squad.attackOrder(p, false)")
check('a dead one: not sent, and the name is shown without the underscore', ev("r == false and last() == 'The Wild Rabbit is already dead.'"))
run("p.cursor = newMob({ x = 10 }); out = {}; r = xi.squad.attackOrder(p, false)")
check('no mate out: not sent, call them first', ev("r == false and last():find('Call them first', 1, true) ~= nil and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))
run("out = { newMate({ id = 11 }) }; p.cursor = newMob({ x = 55 }); r = xi.squad.attackOrder(p, false)")
check('55 yalms away: too far', ev("r == false and last():find('too far away (55 yalms; up to 50)', 1, true) ~= nil and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))

# the order
run("p = newPlayer(); p.animation = 33; a = newMate({ id = 11, animation = 33 }); b = newMate({ id = 12 }); out = { a, b };"
    "p.cursor = newMob({ x = 18, targid = 777 }); said = {}; r = xi.squad.attackOrder(p, false)")
check('a live monster 18 yalms away, the player sitting: sent', ev("r == true"))
check('the three local vars are written (targid, zone, time)',
      ev("p:getLocalVar('SQUAD_ATTACK_TARGET') == 777 and p:getLocalVar('SQUAD_ATTACK_ZONE') == 100 and p:getLocalVar('SQUAD_ATTACK_SEEN') == 1000"))
check('a mate that sat with the player stands up', ev("a:getAnimation() == 0"))
check('the player is left sitting', ev("p:getAnimation() == 33"))
check('it says so and names !squad stop', ev("last():find('Your squad attacks the Wild Rabbit', 1, true) ~= nil and last():find('!squad stop', 1, true) ~= nil"))
check('nothing engages the player', ev("p:isEngaged() == false"))

# at a camp: only within its reach
run("p = newPlayer(); out = { newMate({ id = 11 }) }; camps[1] = { zone = 100, x = 0, y = 0, z = 0 }; p.cursor = newMob({ x = 25 }); r = xi.squad.attackOrder(p, false)")
check('at a camp, a monster 25 yalms from it: not sent, and why',
      ev("r == false and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0 and last():find('only fights within 20 yalms', 1, true) ~= nil and last():find('!squad camp off', 1, true) ~= nil"))
run("p.cursor = newMob({ x = 15 }); r = xi.squad.attackOrder(p, false)")
check('at a camp, 15 yalms from it: sent', ev("r == true and p:getLocalVar('SQUAD_ATTACK_TARGET') == 321"))
run("camps[1] = { zone = 200, x = 0, y = 0, z = 0 }; p.vars = {}; p.cursor = newMob({ x = 25 }); r = xi.squad.attackOrder(p, false)")
check('a camp left behind in another zone does not count', ev("r == true"))
run("camps = {}")

# stop
run("p = newPlayer(); a = newMate({ id = 11, engaged = true }); b = newMate({ id = 12 }); out = { a, b }; p.cursor = newMob({ x = 5 });"
    "xi.squad.attackOrder(p, false); r = xi.squad.attackOrder(p, true)")
check('stop: the order is gone', ev("r == false and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0"))
check('stop: a mate in that fight lets go', ev("a.letGo == true and b.letGo == nil"))
check('stop: it says they break off', ev("last() == 'Your squad breaks off.'"))
run("r = xi.squad.attackOrder(p, true)")
check('stop with no order: says so and how to give one', ev("last():find('no attack order', 1, true) ~= nil"))
run("p = newPlayer(); p.engaged = true; a = newMate({ id = 11, engaged = true }); out = { a }; xi.squad.attackOrder(p, true)")
check('stop while you fight yourself: your mates stay in your fight', ev("a.letGo == nil"))
run("p = newPlayer(); camps[1] = { zone = 100, x = 0, y = 0, z = 0 }; a = newMate({ id = 11, engaged = true }); out = { a }; xi.squad.attackOrder(p, true); camps = {}")
check('stop at a camp: the camp\'s own fight goes on', ev("a.letGo == nil"))

# the command
run("xi.bots = { partyOrder = function(player, word) botWord = word end };"
    "p = newPlayer(); out = { newMate({ id = 11 }) }; p.cursor = newMob({ x = 5 }); botWord = nil; r = command(p, 'attack', nil)")
check('!squad attack gives the order and ends the command', ev("r == nil and p:getLocalVar('SQUAD_ATTACK_TARGET') == 321"))
check('...and bot players in the party get "attack"', ev("botWord == 'attack'"))
run("botWord = nil; r = command(p, 'stop', nil)")
check('!squad stop takes it back, and the bots get "stop"', ev("r == nil and p:getLocalVar('SQUAD_ATTACK_TARGET') == 0 and botWord == 'stop'"))
run("p.cursor = newMob({ x = 5 }); command(p, 'attack', nil); botWord = nil; command(p, 'attack', 'off')")
check('!squad attack off is the same as stop', ev("p:getLocalVar('SQUAD_ATTACK_TARGET') == 0 and botWord == 'stop'"))
run("p.cursor = nil; botWord = nil; command(p, 'attack', nil)")
check('an order that was refused is not passed on to the bots', ev("botWord == nil"))
run("xi.bots = nil; p.cursor = newMob({ x = 5 }); ok = pcall(command, p, 'attack', nil)")
check('without the bots module the command still works', ev("ok == true and p:getLocalVar('SQUAD_ATTACK_TARGET') == 321"))
run("r = command(p, 'engage', nil)")
check('other actions are not swallowed', ev("r == 'fell through'"))

# the rest tick: sent in while the player rests, so not sitting with him
run("m = newPlayer(); m.animation = 33; mate = newMate({ id = 11, master = m }); restTick(mate)")
check('no order, the player sits: an idle mate sits with him (as before)', ev("mate:getAnimation() == 33"))
run("m.vars.SQUAD_ATTACK_TARGET = 321; restTick(mate)")
check('with an order: that mate stands up', ev("mate:getAnimation() == 0"))
run("restTick(mate)")
check('...and stays up (waiting out its engage delay)', ev("mate:getAnimation() == 0"))
run("m.vars.SQUAD_ATTACK_TARGET = 0; restTick(mate)")
check('the order over, the player still resting: it sits again', ev("mate:getAnimation() == 33"))

check('!squad help lists attack and stop', "say(player, '!squad attack   - your squad attacks the monster you have targeted" in squad and '!squad stop' in squad)
check('no other !squad action is called attack or stop',
      len(re.findall(r"if action == 'attack'", squad)) == 1 and len(re.findall(r"if action == 'stop'", squad)) == 0)

# ---------------------------------------------------------------- trust_controller.cpp (read only)
check('the header declares OrderedTarget', 'auto OrderedTarget() -> CBattleEntity*;' in hdr)
fn_at = cpp.index('auto CTrustController::OrderedTarget() -> CBattleEntity*')
fn = cpp[fn_at:cpp.index('auto CTrustController::EngageDelayPassed', fn_at)]
check('it is for squad mates only', 'POwner->GetLocalVar("SQUAD_ID") == 0' in fn)
check('it reads the three local vars from the master', all(v in fn for v in ('PMaster->GetLocalVar("SQUAD_ATTACK_TARGET")', 'PMaster->GetLocalVar("SQUAD_ATTACK_ZONE")', 'PMaster->GetLocalVar("SQUAD_ATTACK_SEEN")')))
check('the monster is looked up as a monster in the zone', 'GetEntity(static_cast<uint16>(targid), TYPE_MOB)' in fn)
for what, text in (('the monster is dead', 'PMob->isDead()'), ('it is gone', 'xi::Status::Disappear'), ('it is not an enemy', 'PMob->allegiance != xi::Allegiance::Mob'),
                   ('the player is dead', 'PMaster->isDead()'), ('the player is in another zone', 'PMaster->getZone()'),
                   ('nobody looked at it for a while', 'now > seen + OrderStaleSec'), ('it is too far from the player', '> OrderLeash')):
    check(f'the order is dropped when {what}', text in fn)
check('dropping it clears the var, so squad.lua sees it too', 'PMaster->SetLocalVar("SQUAD_ATTACK_TARGET", 0);' in fn)
check('a standing order is stamped each time a mate reads it', 'PMaster->SetLocalVar("SQUAD_ATTACK_SEEN", now);' in fn)
check('leash 60 yalms, stale after 15 s', 'OrderLeash    = 60.0f' in cpp and 'OrderStaleSec = 15' in cpp)

combat = cpp[cpp.index('auto CTrustController::DoCombatTick'):cpp.index('auto CTrustController::DoNonCombatTick')]
branch = combat[combat.index('else if (!PMaster->PAI->IsEngaged())'):combat.index('if (inCamp && PMob && distance(PMob->loc.p, camp) > CampFightRadius)')]
check('in a fight, master not engaged: the order is asked before letting go',
      branch.index('POrdered = OrderedTarget();') < branch.index('PTrust->PAI->Internal_Disengage();'))
check('...no order: lets go as before', re.search(r'if \(POrdered == nullptr\)\s*\{\s*PTrust->PAI->Internal_Disengage\(\);\s*m_CombatEndTime = m_Tick;', branch) is not None)
check('...another target than the ordered one: change to it', 'else if (PTarget != POrdered)' in branch and 'Internal_ChangeTarget(EntityId(POrdered))' in branch)
check('a mate on an order runs to the monster instead of appearing next to it',
      '!inCamp && !PMaster->PAI->IsEngaged() && POrdered == nullptr && currentDistanceToTarget > WarpDistance' in combat)
check('the camp fight is untouched', 'if (PTarget == nullptr || PTarget->isDead() || distance(PTarget->loc.p, camp) > CampLeash)' in combat)

roam = cpp[cpp.index('auto CTrustController::DoRoamTick'):cpp.index('auto CTrustController::OrderedTarget()')]
check('out of a fight: your own engage still comes first',
      roam.index('POwner->PAI->Internal_Engage(PMaster->battleTarget());') < roam.index('POwner->PAI->Internal_Engage(EntityId(POrdered));'))
check('...then the order, only while you are not engaged', 'PMaster->PAI->IsEngaged() ? nullptr : OrderedTarget(); POrdered != nullptr' in roam)
check("...and a mate's engage delay counts for it", re.search(r'if \(EngageDelayPassed\(POrdered\)\)\s*\{\s*POwner->PAI->Internal_Engage\(EntityId\(POrdered\)\);', roam) is not None)
check('at a camp: the ordered monster is fought if it is within the camp\'s reach',
      'if (auto* POrdered = OrderedTarget(); POrdered != nullptr && distance(POrdered->loc.p, camp) <= CampFightRadius)' in roam)
check('the camp reach in squad.lua matches the C++', 'xi.squad.ATTACK_CAMP_REACH = 20' in squad and 'constexpr float CampFightRadius = 20.0f;' in cpp)
check('braces balance in the changed file', cpp.count('{') == cpp.count('}') and cpp.count('(') == cpp.count(')'))

# ---------------------------------------------------------------- the menu (the buttons are clicked in test_menu_opens.py)
check('the menu has Attack my target and Stop', "button('Attack my target', 'sqattack'" in menu and "button('Stop', 'sqstop'" in menu)
check('they send the two commands', "enqueue('/say !squad attack')" in menu and "enqueue('/say !squad stop')" in menu)
check('the tooltip gives the macro line', 'In a macro:  /say !squad attack' in menu)

print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
