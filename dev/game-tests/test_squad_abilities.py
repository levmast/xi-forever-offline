"""(2026-11-22) Party-only spells and job abilities on squad mates: the server side.
The launcher lets the game offer a mate as the target (client-patches/spell_targets.json); this checks that the server
then accepts every listed spell and ability on a mate, and that Cover, Accomplice and Collaborator, whose own check said
"the target has to be a player", let a squad mate through (and nobody else they did not let through before).

Run with: python test_squad_abilities.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
"""
import json
import os
import re
import sys
from lupa import luajit21 as lupa

SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
passed = failed = 0
PARTY = 0x02          # the server's "party member" target


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


with open(os.path.join(KIT, 'client-patches', 'spell_targets.json'), encoding='utf-8') as handle:
    listed = json.load(handle)

# every listed spell and ability is one the server lets you use on a party member
spell_sql = read('sql', 'spell_list.sql')
for spell in listed['spells']:
    row = re.search(r"VALUES \(%d,'([^']+)',0x[0-9A-Fa-f]+,\d+,\d+,[^,]+,\d+,(\d+)," % spell['id'], spell_sql)
    check('%s: the server knows it and allows a party member' % spell['name'], row is not None and int(row.group(2)) & PARTY)
ability_sql = read('sql', 'abilities.sql')
for one in listed['abilities']:
    row = re.search(r"VALUES \(%d,'([^']+)',\d+,\d+,(\d+)," % one['id'], ability_sql)
    check('%s: the server knows it and allows a party member' % one['name'], row is not None and int(row.group(2)) & PARTY)
    check('%s: the name matches the server\'s' % one['name'], row is not None and row.group(1) == one['name'].lower().replace(' ', '_'))

# a squad mate counts as a party member for a player's spell or ability (it has no party of its own: its master's)
trust = read('src', 'map', 'entities', 'trust_entity.cpp')
check('the server takes a squad mate as a party target', re.search(r'targetFlags & TARGET_PLAYER_PARTY && PInitiator->allegiance == allegiance && PMaster', trust) is not None)

# Cover, Accomplice, Collaborator: the "has to be a player" checks
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
overrides = {}
Module = { new = function() return { addOverride = function(_, name, fn) overrides[name] = fn end } end }
require = function() return {} end
xi = {}
function who(id, pc, mate) return { getID = function() return id end, isPC = function() return pc end, isSquadMate = function() return mate end } end
super = function(player, target, ability)                       -- the game's own check
    if target == nil or target:getID() == player:getID() or not target:isPC() then return 155, 0 else return 0, 0 end
end
you = who(1, true, false)
''')
lua.globals().SRC = read('modules', 'custom', 'late', 'squad_abilities.lua')
check('the module loads', lua.eval("(function() local f, e = loadstring(SRC); if not f then return e end; local ok, e2 = pcall(f); return ok and 'ok' or e2 end)()") == 'ok')
for name in ('xi.job_utils.paladin.checkCover', 'xi.job_utils.thief.checkAccomplice', 'xi.job_utils.thief.checkCollaborator'):
    f = "overrides['%s']" % name
    short = name.split('.')[-1]
    check(short + ': has its place', lua.eval(f + ' ~= nil'))
    check(short + ': a squad mate is let through', lua.eval(f + '(you, who(9, false, true), {})') == (0, 0))
    check(short + ': a player as before', lua.eval(f + '(you, who(2, true, false), {})') == (0, 0))
    check(short + ': not yourself', lua.eval(f + '(you, who(1, true, false), {})') == (155, 0))
    check(short + ': not a stock Trust or a monster', lua.eval(f + '(you, who(7, false, false), {})') == (155, 0))
    check(short + ': no target', lua.eval(f + '(you, nil, {})') == (155, 0))
for path, fn in ((('scripts', 'globals', 'job_utils', 'paladin.lua'), 'xi.job_utils.paladin.checkCover = function'),
                 (('scripts', 'globals', 'job_utils', 'thief.lua'), 'xi.job_utils.thief.checkAccomplice = function'),
                 (('scripts', 'globals', 'job_utils', 'thief.lua'), 'xi.job_utils.thief.checkCollaborator = function')):
    check(fn.split(' ')[0] + ' is still where the module looks for it', fn in read(*path))

# Cover: the covering Paladin is found through the mate's master
battle = read('src', 'map', 'utils', 'battleutils.cpp')
start = battle.index('auto GetCoverAbilityUser(')
body = battle[start:battle.index('auto IsMagicCovered(', start)]
check('Cover: a squad mate\'s party is its master\'s',
      re.search(r'PTargetParty == nullptr && PCoverAbilityTarget->isSquadMate\(\) && PCoverAbilityTarget->PMaster != nullptr\)\s*\{\s*PTargetParty = PCoverAbilityTarget->PMaster->PParty;', body) is not None)
check('Cover: the search uses that party', 'for (auto* PMember : PTargetParty->members)' in body and 'if (PTargetParty != nullptr)' in body)
check('Cover: braces balance', body.count('{') == body.count('}') and body.count('(') == body.count(')'))

# the ones that need nothing: no "has to be a player" in their checks
white = read('scripts', 'globals', 'job_utils', 'white_mage.lua')
sam = read('scripts', 'globals', 'job_utils', 'samurai.lua')
for text, fn in ((white, 'checkMartyr'), (white, 'checkDevotion'), (sam, 'checkShikikoyo')):
    at = text.index(fn + ' = function')
    check(fn + ' has no player-only check', 'isPC' not in text[at:text.index('\nend', at)])
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
