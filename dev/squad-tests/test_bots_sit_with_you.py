"""(K-Andy, 2026-11-22) "When you sit down your group should also": squad mates already sat with you when you /heal
(squad.lua restTick), but a bot player in your party only sat when it was hurt. Now it sits with you, full or not,
away from camp and at camp, and stands up when you do.

The two conditions are taken out of bots.lua as they are written there and run with every combination.

Run: python test_bots_sit_with_you.py [server folder]      (default C:\\ffxi-local\\server; needs lupa)
"""
import itertools
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


bots = read('modules', 'custom', 'lua', 'bots.lua')
away = re.search(r'local wantRest = (.*?\n\s*and bot:checkDistance\(leader\) < 10)', bots, re.S)
up = re.search(r'elseif st\.resting and not camp and (\(moved or \(full and not leaderRests\)\)) then', bots)
camp_sit = re.search(r'if restOn and (\(leaderRests or \(low and not full\)\)) and not st\.resting then', bots)
camp_up = re.search(r'elseif st\.resting and (full and not leaderRests) then', bots)
check('the four conditions are where they were', all((away, up, camp_sit, camp_up)))
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
REST_STILL_S = 8
os_time = 1000
os = { time = function() return os_time end }
function want(camp, full, hurt, leaderRests, still, far)
    local st = { stillSince = os_time - still }
    local bot = { checkDistance = function() return far and 30 or 3 end }
    local leader = {}
    return (%s) and true or false
end
function campSit(low, full, leaderRests) return (%s) and true or false end
function campUp(full, leaderRests) return (%s) and true or false end
function standUp(moved, full, leaderRests) return (%s) and true or false end
''' % (away.group(1), camp_sit.group(1), camp_up.group(1), up.group(1)))
want, camp_sit_fn, camp_up_fn, stand = (lua.globals()[n] for n in ('want', 'campSit', 'campUp', 'standUp'))

check('you /heal, the bot is full: it sits with you (before: it stood)', want(False, True, False, True, 0, False) is True)
check('you /heal, the bot is hurt: it sits', want(False, False, True, True, 0, False) is True)
check('you /heal but the bot is far away: it does not sit where it stands', want(False, True, False, True, 0, True) is False)
check('you stand, the bot is full: it does not sit', want(False, True, False, False, 60, False) is False)
check('you stand still, the bot is low: it sits by itself after 8 s, as before', want(False, False, True, False, 8, False) is True)
check('...and not before the 8 s', want(False, False, True, False, 3, False) is False)
check('you stand still, the bot is only a little down: it stays up, as before', want(False, False, False, False, 60, False) is False)
for full, hurt, rests in itertools.product((True, False), repeat=3):
    check('with a camp set this rule stays out of it', want(True, full, hurt, rests, 60, False) is False)
check('it gets up when you move off', stand(True, False, True) is True)
check('it gets up when you stand and it is full', stand(False, True, False) is True)
check('it stays down while you rest, full or not', stand(False, True, True) is False and stand(False, False, True) is False)
check('it stays down until full when it sat by itself', stand(False, False, False) is False)
check('camp: you /heal, the bot is full: it sits', camp_sit_fn(False, True, True) is True)
check('camp: a low bot sits between fights, as before', camp_sit_fn(True, False, False) is True)
check('camp: a full bot does not sit by itself', camp_sit_fn(False, True, False) is False and camp_sit_fn(True, True, False) is False)
check('camp: it stays down while you rest and gets up when you stand, once full', camp_up_fn(True, True) is False and camp_up_fn(True, False) is True
      and camp_up_fn(False, False) is False)

# a bot that sits only for company still cures and buffs (2026-11-22: before it sat with you it stood and cured you)
act = re.search(r'if partyPlay and \((not st\.resting or emergency or \(leaderRests and full\))\) then', bots)
check('the condition for acting while sitting is where it was', act is not None)
lua.execute('function acts(resting, emergency, leaderRests, full) local st = { resting = resting } return (%s) and true or false end' % act.group(1))
acts = lua.globals().acts
check('standing: it acts, as always', acts(False, False, False, False) is True)
check('sitting with you, full: it still cures and buffs', acts(True, False, True, True) is True)
check('sitting because it needs the rest: only an emergency gets it up, as before', acts(True, False, True, False) is False and acts(True, True, True, False) is True)
check('sitting by itself, low: only an emergency', acts(True, False, False, False) is False and acts(True, True, False, False) is True)

squad = read('modules', 'custom', 'lua', 'squad.lua')
check('squad mates: sit with you whenever you /heal and nobody fights, full or not',
      'local resting = master:getAnimation() == xi.animation.HEALING and not mob:isEngaged() and not master:isEngaged()' in squad)
controller = read('src', 'map', 'ai', 'controllers', 'trust_controller.cpp')
check('squad mates: no HP or MP by themselves, only while resting',
      'POwner->GetLocalVar("SQUAD_ID") == 0 && POwner->CanRest()' in controller)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
