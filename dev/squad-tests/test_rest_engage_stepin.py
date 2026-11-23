"""(2026-11-22, the user's decisions after Hasuko's and Hexblood's suggestions)

* The camp keeps pulling while a player rests; a player on his feet holds it only while hurt (squadCampWaitsFor).
* Pressing Attack sends the squad in without a swing: for squad mates "nothing set" means engage first.
* An area spell cast on oneself (Protectra...) waits until its caster has stepped within reach of the player, and
  out of a fight the squad closes up around him (trust_controller.cpp: Cast, StepInTick, SQUAD_GATHER).

The Lua function is run as written; the C++ can only be read here, so those checks are on its text.
Run: python test_rest_engage_stepin.py [server folder]      (default C:\\ffxi-local\\server; needs lupa)
"""
import os
import re
import sys
from lupa import luajit21 as lupa

SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


def read(*parts):
    with open(os.path.join(SERVER, *parts), encoding='utf-8') as handle:
        return handle.read()


squad = read('modules', 'custom', 'lua', 'squad.lua')
start = squad.index('function squadCampWaitsFor(player, member)')
fn = squad[start:squad.index('\nend\n', start) + 5]
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
CAMP_READY_HP, CAMP_READY_MP = 60, 30
xi = { animation = { HEALING = 33, NONE = 0 } }
bots = {}
BotIsBot = function(id) return bots[id] == true end
local function percentOf(entity, now, max)
    local top = entity[max](entity)
    if top == nil or top <= 0 then return 100 end
    return math.floor(entity[now](entity) * 100 / top)
end
''' + fn.replace('function squadCampWaitsFor', 'squadCampWaitsFor = function', 1) + '''
function member(id, hp, mp, maxmp, resting)
    return { getID = function() return id end, getHP = function() return hp end, getMaxHP = function() return 100 end,
             getMP = function() return mp end, getMaxMP = function() return maxmp end,
             getAnimation = function() return resting and 33 or 0 end }
end
function waits(old, bot, hp, mp, maxmp, resting)
    bots = { [7] = bot }
    local player = { getCharVar = function(_, name) return (name == 'SQUAD_CAMP_WAIT' and old) and 1 or 0 end }
    return squadCampWaitsFor(player, member(7, hp, mp, maxmp, resting)) and true or false
end
''')
waits = lua.globals().waits
# (old rule?, bot?, HP%, MP, max MP, resting?)
check('a White Mage leader sitting with no MP: the puller keeps pulling', waits(False, False, 100, 5, 100, True) is False)
check('...the same when she is also hurt and resting it off', waits(False, False, 40, 5, 100, True) is False)
check('any player sitting, full or not', waits(False, False, 100, 0, 0, True) is False)
check('a player on his feet and hurt holds the pull', waits(False, False, 50, 100, 100, False) is True)
check('a player on his feet with no MP does not', waits(False, False, 100, 5, 100, False) is False)
check('a player in good shape does not', waits(False, False, 100, 100, 100, False) is False)
check('a bot player low on MP holds it, like a mate', waits(False, True, 100, 20, 100, False) is True)
check('a bot player hurt holds it', waits(False, True, 50, 100, 100, False) is True)
check('a bot that sits only because you do (full) does not', waits(False, True, 100, 100, 100, True) is False)
check('a bot that sits because it needs it is waited for, as before', waits(False, True, 90, 100, 100, True) is True)
check('a bot without MP is judged by HP alone', waits(False, True, 100, 0, 0, False) is False)
check('!squad camp wait on: a resting player holds the pull again', waits(True, False, 100, 100, 100, True) is True)
check('...and one low on MP', waits(True, False, 100, 5, 100, False) is True)
check('...and one in good shape does not', waits(True, False, 100, 100, 100, False) is False)

check('the ready check asks it for every player-type member', 'if member:getObjType() == xi.objType.PC and squadCampWaitsFor(player, member) then' in squad)
check('the old three-way test is gone from the ready check', "member:getAnimation() == xi.animation.HEALING or percentOf(member, 'getHP'" not in squad)
check('the mates\' own HP and MP still hold the pull', "percentOf(trust, 'getHP', 'getMaxHP') < CAMP_READY_HP" in squad and "percentOf(trust, 'getMP', 'getMaxMP') < CAMP_READY_MP" in squad)
check('it is defined after what it uses and before the camp tick', squad.index('local function percentOf') < start < squad.index('squadCampWaitsFor(player, member) then')
      and squad.index('local CAMP_READY_HP') < start)
check('the puller on its way out is not sat down with a resting player',
      re.search(r"local resting = master:getAnimation\(\) == xi\.animation\.HEALING and not mob:isEngaged\(\) and not master:isEngaged\(\) and\s+mob:getLocalVar\('SQUAD_PULL_PHASE'\) == 0", squad) is not None)
check('!squad camp wait on | off', "elseif what == 'wait' then" in squad and "player:setCharVar('SQUAD_CAMP_WAIT', on == 'on' and 1 or 0)" in squad
      and "!squad camp wait on | off" in squad)

# Attack sends the squad in
controller = read('src', 'map', 'ai', 'controllers', 'trust_controller.cpp')
header = read('src', 'map', 'ai', 'controllers', 'trust_controller.h')
case0 = controller[controller.index('case 0: // Nothing set'):controller.index('default: // Something invalid set')]
check('squad mates: nothing set = join as soon as you engage', 'if (POwner->GetLocalVar("SQUAD_ID") != 0)' in case0
      and 'trustEngageCondition = PMaster->GetBattleTarget();' in case0 and 'break;' in case0 and '[[fallthrough]];' in case0)
check('other Trusts keep the retail rule', 'trustEngageCondition = PMaster->GetBattleTarget() && masterMeleeSwing;' in controller)
check('!squad engage normal sets 2, the retail rule', "player:setCharVar('TrustEngageType', 2)" in squad and "player:setCharVar('TrustEngageType', 0)" not in squad)
check('the Squads window is told "first" unless normal was chosen', "player:getCharVar('TrustEngageType') ~= 2 and 1 or 0" in squad)

# the step-in for area spells
cast = controller[controller.index('auto CTrustController::Cast(const EntityId target, SpellID spellid) -> bool'):controller.index('// FFXI Offline squad: the reach of an area spell')]
check('Cast holds an area spell back until it covers everyone', 'if (!m_StepInCasting)' in cast and 'StepInRadius(PSpell, PTarget)' in cast
      and 'AreaSpellCovers(radius)' in cast and cast.rstrip().endswith('}') and 'return CMobController::Cast(castTarget, spellid);' in cast)
check('...and gives up waiting after a few seconds', '(fighting ? 4s : 7s)' in cast and controller.count('(fighting ? 4s : 7s)') == 2)
check('out of a fight it asks the squad to close up', 'PMaster->SetLocalVar("SQUAD_GATHER", earth_time::timestamp() + 5);' in cast)
radius = controller[controller.index('auto CTrustController::StepInRadius'):controller.index('auto CTrustController::AreaSpellCovers')]
check('only squad mates, only area spells cast on oneself, no songs, no enemy spells', 'POwner->GetLocalVar("SQUAD_ID") == 0' in radius
      and 'PTarget != POwner' in radius and 'getAOE() != SPELLAOE_RADIAL' in radius and 'SPELLGROUP_SONG' in radius and 'TARGET_ENEMY' in radius)
check('a mate holding a camp does not leave its spot for it', 'if (campOf(POwner, camp))' in radius)
check('not when the player is down, in another area or far away', 'PMaster->isDead()' in radius and '> 40.0f' in radius)
covers = controller[controller.index('auto CTrustController::AreaSpellCovers'):controller.index('auto CTrustController::StepInTick')]
check('in a fight only the player counts', 'if (PMaster->PAI->IsEngaged())' in covers and 'return true;' in covers)
check('out of a fight the mates near him too, not the puller or one that is fighting', 'SQUAD_PULL_PHASE' in covers and 'POther->PAI->IsEngaged()' in covers and '> 25.0f' in covers)
step = controller[controller.index('auto CTrustController::StepInTick() -> bool'):controller.index('auto CTrustController::GetTopEnmity')]
check('StepInTick casts once covered or out of patience, and only then', 'm_StepInCasting = true;' in step and 'Cast(EntityId(POwner), spellid);' in step
      and 'm_StepInCasting = false;' in step and step.index('m_StepInCasting = true;') < step.index('Cast(EntityId(POwner), spellid);') < step.index('m_StepInCasting = false;'))
check('out of a fight she comes right up to the player, in one only as near as needed', 'const float want = fighting ? radius - 3.0f : 2.5f;' in step)
check('both ticks walk her in', controller.count('if (StepInTick())') == 2)
combat = controller[controller.index('auto CTrustController::DoCombatTick'):controller.index('auto CTrustController::DoNonCombatTick')]
hook = combat[combat.index('if (StepInTick())'):]
check('in a fight her rules keep running while she walks (cures are not held up)', hook.index('co_await m_GambitsContainer->Tick(tick);') < hook.index('co_return;'))
roam = controller[controller.index('auto CTrustController::DoRoamTick'):controller.index('auto CTrustController::EngageDelayPassed')]
check('the squad closes up around the player while asked to', 'PMaster->GetLocalVar("SQUAD_GATHER") > earth_time::timestamp()' in roam
      and '(currentPartyPos > 0 && !gather)' in roam and 'const bool isFirstTrust = (currentPartyPos == 0) || gather;' in roam)
check('...each a little further out than the one before', 'gather ? 1.0f + 0.35f * static_cast<float>(currentPartyPos)' in roam)
check('the usual follow styles are untouched otherwise', 'followStyle == 1 ? 0.7f : (followStyle == 2 ? 1.8f : 1.0f)' in roam)
for name, text in (('Cast', cast), ('StepInRadius', radius), ('AreaSpellCovers', covers), ('StepInTick', step)):
    check(name + ': braces and brackets balance', text.count('{') == text.count('}') and text.count('(') == text.count(')'))
check('the header declares them', all(word in header for word in ('SpellID           m_StepInSpell   = SpellID::None;', 'auto StepInRadius(', 'auto AreaSpellCovers(',
                                                                  'auto StepInTick() -> bool;', 'auto IsSteppingIn() const -> bool')))
check('the time header is included', '#include "common/earth_time.h"' in controller)
cpp = read('modules', 'custom', 'cpp', 'squad.cpp')
check('a spell asked for in party chat that waits for the step-in is not reported as busy', 'controller->Cast(PTarget->entityId(), spellId) || controller->IsSteppingIn()' in cpp)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
