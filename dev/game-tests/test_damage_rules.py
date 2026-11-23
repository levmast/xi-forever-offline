"""RULES > Damage (Poptart, 2026-11-22): "Damage you and your squad take" is put on players and squad mates with the
game's uncapped damage-taken stats (server: modules/custom/late/comforts.lua), and the "you deal" sliders for magic
leave a monster's own spells alone (scripts/globals/spells/damage_spell.lua).

Run with: python test_damage_rules.py [server folder]      (needs lupa; default C:\\ffxi-local\\server)
"""
import os
import re
import sys
from lupa import luajit21 as lupa
SERVER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('XIFO_SERVER', r'C:\ffxi-local\server')
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


def read(*parts):
    return open(os.path.join(SERVER, *parts), encoding='utf-8').read()


lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute('''
overrides = {}
Module = { new = function() return { addOverride = function(_, name, fn) overrides[name] = fn end } end }
require = function() return {} end
super = function() return 'base' end
xi = { settings = { main = { PLAYER_DAMAGE_TAKEN_MULTIPLIER = 1 } },
       mod = { UDMGPHYS = 387, UDMGBREATH = 388, UDMGMAGIC = 389, UDMGRANGE = 390 }, caskets = {}, guildShops = {} }
function ent()
    local e = { mods = {}, v = {} }
    function e:addMod(id, n) self.mods[id] = (self.mods[id] or 0) + n end
    function e:getLocalVar(n) return self.v[n] or 0 end
    function e:setLocalVar(n, x) assert(x >= 0, 'a local var cannot be negative'); self.v[n] = x end
    return e
end
function all(e, n) return e.mods[387] == n and e.mods[388] == n and e.mods[389] == n and e.mods[390] == n end
''')
lua.globals().SRC = read('modules', 'custom', 'late', 'comforts.lua')
lua.execute('loadstring(SRC)()')
ev = lua.eval

lua.execute("p = ent(); overrides['xi.player.onGameIn'](p, false, true)")
check('1x puts nothing on', ev('next(p.mods) == nil'))
lua.execute("xi.settings.main.PLAYER_DAMAGE_TAKEN_MULTIPLIER = 0.5; a = overrides['xi.player.onGameIn'](p, false, true)")
check('0.5x: minus half on physical, magic, breath and ranged', ev('all(p, -5000)'))
check("the game's own log-in work still runs", ev("a == 'base'"))
lua.execute("overrides['xi.player.onGameIn'](p, false, true)")
check('a second look at the same character does not double it', ev('all(p, -5000)'))
lua.execute("xi.settings.main.PLAYER_DAMAGE_TAKEN_MULTIPLIER = 2; xi.comforts.damageTaken(p)")
check('the setting changed to 2x: plus 100%', ev('all(p, 10000)'))
lua.execute("xi.settings.main.PLAYER_DAMAGE_TAKEN_MULTIPLIER = 1; xi.comforts.damageTaken(p)")
check('back to 1x takes it off again', ev('all(p, 0)'))
lua.execute("xi.settings.main.PLAYER_DAMAGE_TAKEN_MULTIPLIER = 1.5; t = ent(); xi.comforts.damageTaken(t)")
check('a squad mate called at 1.5x gets plus half', ev('all(t, 5000)'))
lua.execute("xi.settings.main.PLAYER_DAMAGE_TAKEN_MULTIPLIER = 99; q = ent(); xi.comforts.damageTaken(q)")
check('a silly value is held to 3x', ev('all(q, 20000)'))
lua.execute("xi.settings.main.PLAYER_DAMAGE_TAKEN_MULTIPLIER = nil; n = ent(); xi.comforts.damageTaken(n)")
check('a missing setting is 1x', ev('next(n.mods) == nil'))

# the stats exist under these names, and squad mates get the rule when they are called
codegen = read('scripts', 'enum', 'mod.codegen.lua')
for name in ('UDMGPHYS', 'UDMGMAGIC', 'UDMGBREATH', 'UDMGRANGE'):
    check('the server knows ' + name, re.search(r'^\s*' + name + r'\s*=\s*\d+', codegen, re.M) is not None)
check('squad mates get it at the call', 'xi.comforts.damageTaken, trust' in read('modules', 'custom', 'lua', 'squad.lua'))
check('the setting has a default of 1', re.search(r'PLAYER_DAMAGE_TAKEN_MULTIPLIER\s*=\s*1\.0', read('settings', 'default', 'main.lua')) is not None)

# "you deal" magic sliders: monsters keep 1x
spell = read('scripts', 'globals', 'spells', 'damage_spell.lua')
start = spell.index('xi.spells.damage.calculateSkillTypeMultiplier = function')
body = spell[start:spell.index('xi.spells.damage.calculateNinSkillBonus', start)]
lua.execute('''
xi = { skill = { ELEMENTAL_MAGIC = 1, DARK_MAGIC = 2, NINJUTSU = 3, DIVINE_MAGIC = 4, BLUE_MAGIC = 5 }, spells = { damage = {} },
       settings = { main = { ELEMENTAL_POWER = 2, DARK_POWER = 3, NINJUTSU_POWER = 4, DIVINE_POWER = 5 } } }
monster = { isMob = function() return true end }
player  = { isMob = function() return false end }
''')
lua.execute(body)
f = 'xi.spells.damage.calculateSkillTypeMultiplier'
check('your elemental magic gets the slider', ev(f + '(1, player) == 2'))
check('your dark, ninjutsu and divine magic too', ev(f + '(2, player) == 3 and ' + f + '(3, player) == 4 and ' + f + '(4, player) == 5'))
check("a monster's spells stay at 1x", ev(f + '(1, monster) == 1 and ' + f + '(4, monster) == 1'))
check('an old call without the caster still works', ev(f + '(1) == 2 and ' + f + '(5) == 1'))
check('the spell code hands the caster over', 'calculateSkillTypeMultiplier(skillType, caster)' in spell)

# the launcher: every slider is on RULES > Damage, 1x by default, and lands in settings/main.lua
import launcher_core as core
import launcher_settings as st
fields = {f[0]: f for f in core.RATE_FIELDS}
wanted = ['main.PLAYER_DAMAGE_TAKEN_MULTIPLIER', 'main.WEAPON_SKILL_POWER', 'main.ELEMENTAL_POWER', 'main.DARK_POWER',
          'main.DIVINE_POWER', 'main.NINJUTSU_POWER', 'main.BLUE_POWER']
lines = {e['key']: e for e in st.SETTINGS}
defaults = read('settings', 'default', 'main.lua')
for key in wanted:
    check(key + ' is a launcher setting, 1x by default', key in fields and fields[key][4] == 1.0 and fields[key][1] == 'main.lua')
    check(key + ' is on RULES > Damage', key in lines and lines[key]['page'] == 'rules' and lines[key]['section'] == 'Damage')
    check(key + ' exists in the server defaults', re.search(r'^\s*' + key.split('.')[1] + r'\s*=', defaults, re.M) is not None)
check('Damage has a place on the page', any('Damage' in col for col in st.LAYOUT['rules']))
check('the section says it is experimental', 'experimental' in st.SECTION_NOTES.get('Damage', ''))
low, high = fields['main.PLAYER_DAMAGE_TAKEN_MULTIPLIER'][5:7]
check('damage taken runs from half to double', (low, high) == (0.5, 2.0))

print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
