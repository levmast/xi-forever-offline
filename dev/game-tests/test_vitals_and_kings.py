"""(2026-11-22) Two rules the user said yes to:

* delukard: "Your HP" / "Your MP" (RULES > Battle), you and your squad mates, 1x = the era.
* sparkiie: "Land kings on a timer" (RULES > Comforts), off = as it is today (called at the ??? with the item).

Run with: python test_vitals_and_kings.py [server folder]      (default C:\\ffxi-local\\server; needs lupa)
"""
import os
import re
import shutil
import sys
import tempfile
from lupa import luajit21 as lupa

SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_core as core
import launcher_settings as st
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


def written(rates, name):
    tmp = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(SERVER, 'settings', 'default'), os.path.join(tmp, 'settings', 'default'))
        core.apply_rates(tmp, rates)
        with open(os.path.join(tmp, 'settings', name), encoding='utf-8') as handle:
            return handle.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


fields = {f[0]: f for f in core.RATE_FIELDS}
lines = {e['key']: e for e in st.SETTINGS}

# ---- Your HP / Your MP ----------------------------------------------------------------------------------------------
defaults = read('settings', 'default', 'map.lua')
char = read('src', 'map', 'utils', 'charutils.cpp')
trust = read('src', 'map', 'utils', 'trustutils.cpp')
for what in ('HP', 'MP'):
    key = 'PLAYER_%s_MULTIPLIER' % what
    check(what + ': the server knows the setting and it is 1.0', re.search(r'^\s*%s\s*=\s*1\.0\s*,' % key, defaults, re.M) is not None)
    check(what + ': the player side reads it', 'vitalRate("map.%s")' % key in char)
    check(what + ': squad mates read it too', 'vitalRate("map.%s")' % key in trust)
    field = fields.get('map.' + key)
    check(what + ': the launcher has it, 1x by default, 0.5x to 3x', field is not None and field[1] == 'map.lua' and field[4:7] == (1.0, 0.5, 3.0))
    line = lines.get('map.' + key)
    check(what + ': RULES > Battle, marked experimental', line is not None and (line['page'], line['section'], line['kind']) == ('rules', 'Battle', st.RATE)
          and 'experimental' in line['label'])
for source, name in ((char, 'charutils.cpp'), (trust, 'trustutils.cpp')):
    start = source.index('const auto vitalRate')
    body = source[start:source.index('};', start)]
    check(name + ': a missing or zero value counts as 1.0, and the rate stays between 0.5 and 3', 'rate > 0.0f ? std::clamp(rate, 0.5f, 3.0f) : 1.0f' in body)
    check(name + ': the result cannot run past what the game can hold', source.count('std::min(30000.0f,') >= 2)
check('charutils.cpp: merits are part of what is multiplied', re.search(r'baseHP = static_cast<float>\(grade::GetBaseHP\(.*\) \+ hpMerits\);', char) is not None)
check('trustutils.cpp: only squad mates, the Trust formula above it is left alone',
      trust.index('ALTER_EGO_MP_MULTIPLIER') < trust.index('const auto vitalRate') and trust.count('vitalRate("map.PLAYER_HP_MULTIPLIER")') == 1)
check('1x writes the era value', re.search(r'^\s*PLAYER_HP_MULTIPLIER\s*=\s*1\.0*\s*,', written(dict(core.RATE_DEFAULTS), 'map.lua'), re.M) is not None)
rates = dict(core.RATE_DEFAULTS)
rates['map.PLAYER_HP_MULTIPLIER'] = 2.0
rates['map.PLAYER_MP_MULTIPLIER'] = 1.5
text = written(rates, 'map.lua')
check('the launcher writes 2x HP to the server', re.search(r'^\s*PLAYER_HP_MULTIPLIER\s*=\s*2\.0*\s*,', text, re.M) is not None)
check('the launcher writes 1.5x MP to the server', re.search(r'^\s*PLAYER_MP_MULTIPLIER\s*=\s*1\.50*\s*,', text, re.M) is not None)
check('the monsters\' lines are not moved by it', re.search(r'^\s*MOB_HP_MULTIPLIER\s*=\s*1\.0*\s*,', text, re.M) is not None)

# ---- Land kings on a timer ------------------------------------------------------------------------------------------
main = read('settings', 'default', 'main.lua')
check('kings: the server knows the setting and it is off', re.search(r'^\s*LAND_KINGS_TIMED\s*=\s*0\s*,', main, re.M) is not None)
field = fields.get('main.LAND_KINGS_TIMED')
check('kings: the launcher has it, off by default, on or off only', field is not None and field[1] == 'main.lua' and field[4:7] == (0, 0, 1))
line = lines.get('main.LAND_KINGS_TIMED')
check('kings: RULES > Comforts, a switch', line is not None and (line['page'], line['section'], line['kind']) == ('rules', 'Comforts', st.FLAG))
check('kings: the tip says what off means', line is not None and '???' in line['tip'] and 'Honey Wine' in line['tip'])
for value in (0, 1):
    rates = dict(core.RATE_DEFAULTS)
    rates['main.LAND_KINGS_TIMED'] = value
    check('kings: the launcher writes %d to the server' % value,
          re.search(r'^\s*LAND_KINGS_TIMED\s*=\s*%d\s*,' % value, written(rates, 'main.lua'), re.M) is not None)

HARNESS = '''
made = {}
Module = {}
Module.__index = Module
function Module:new(name, condition)
    if condition ~= nil and type(condition) ~= 'boolean' then error('condition must be a boolean') end
    local o = setmetatable({ name = name, overrides = {}, enabled = condition == nil or condition }, self)
    made[#made + 1] = o
    return o
end
function Module:setEnabled(v) if type(v) ~= 'boolean' then error('setEnabled must be a boolean') end self.enabled = v end
function Module:addOverride(target, fn) self.overrides[#self.overrides + 1] = { target = target, fn = fn } end
require = function() end
xi = { settings = { main = {} }, mobMod = { IDLE_DESPAWN = 55 }, zone = setmetatable({}, { __index = function() return 1 end }),
       status = { DISAPPEAR = 2 } }
zones = setmetatable({}, { __index = function() return { mob = {}, npc = {} } end })
function load_with(setting, source)
    made = {}
    xi.settings.main.LAND_KINGS_TIMED = setting
    assert(loadstring(source))()
    return made[1]
end
'''
era = read('modules', 'era', 'lua', 'globals', 'era_hnm_system.lua')
ours = read('modules', 'custom', 'late', 'land_kings.lua')
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute(HARNESS)
load = lua.globals().load_with
for setting, want in ((0, False), (None, False), (False, False), (1, True), (True, True)):
    check('kings: the era module is %s with the setting at %r' % ('on' if want else 'off', setting), load(setting, era).enabled is want)
    check('kings: our module is %s with the setting at %r' % ('on' if want else 'off', setting), load(setting, ours).enabled is want)
module = load(1, era)
targets = sorted(o.target for o in module.overrides.values())
check('kings: the era module does the three areas and the six kings', len(targets) == 9 and sum(t.endswith('Zone.onInitialize') for t in targets) == 3
      and sum(t.endswith('.onMobDespawn') for t in targets) == 6)
check('kings: the other HNM module of the base stays off', re.search(r'^hnmSystem:setEnabled\(false\)', read('modules', 'custom', 'lua', 'custom_hnm_system.lua'), re.M) is not None)
module = load(1, ours)
targets = [o.target for o in module.overrides.values()]
check('kings: our module touches the six kings\' start-up and nothing else', len(targets) == 6 and all(t.endswith('.onMobInitialize') for t in targets)
      and {t.split('.')[-2] for t in targets} == {'Fafnir', 'Nidhogg', 'Adamantoise', 'Aspidochelone', 'Behemoth', 'King_Behemoth'})
lua.execute('''
calls = {}
super = function(mob) calls[#calls + 1] = 'super' end
mob = { setMobMod = function(self, id, value) calls[#calls + 1] = id .. '=' .. value end }
''')
for override in module.overrides.values():
    lua.execute('calls = {}')
    override.fn(lua.globals().mob)
    check('kings: %s keeps its own start-up and then stays until someone comes' % override.target.split('.')[-2],
          list(lua.globals().calls.values()) == ['super', '55=0'])
for name in ('Fafnir', 'Nidhogg'):
    check('kings: %s still leaves after 90 seconds when called at the ??? (the switch off)' % name,
          'IDLE_DESPAWN, 90' in read('scripts', 'zones', 'Dragons_Aery', 'mobs', name + '.lua'))
check('kings: custom/late is loaded last', read('modules', 'init.txt').rstrip().splitlines()[-1].strip() == 'custom/late')
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
