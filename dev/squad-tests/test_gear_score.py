"""(lilibun, 2026-11-22) "Better auto-equip for squad": a Warrior put on a Silver Hairpin, because auto-equip took the
highest-level piece a mate could wear. Now each piece is rated for the job (modules/custom/late/squad_gear_score.lua)
and squadAutoEquip (squad.lua) takes the best rated.

The real squadAutoEquip and the real rating file are run here on the server's own item data (sql/item_equipment.sql,
item_weapon.sql, item_mods.sql). Run: python test_gear_score.py [server folder]   (default C:\\ffxi-local\\server; lupa)
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


def load_items():
    eq, wp, mods = {}, {}, {}
    for line in read('sql', 'item_equipment.sql').splitlines():
        m = re.match(r"INSERT INTO `item_equipment` VALUES \((\d+),'((?:[^'\\]|\\.)*)',(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),(\d+),", line)
        if m:
            eq[int(m[1])] = dict(name=m[2], level=int(m[3]), ilevel=int(m[4]), jobs=int(m[5]), shield=int(m[7]), slot=int(m[9]))
    for line in read('sql', 'item_weapon.sql').splitlines():
        m = re.match(r"INSERT INTO `item_weapon` VALUES \((\d+),'((?:[^'\\]|\\.)*)',(\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(\d+),(\d+),(-?\d+),(\d+),", line)
        if m:
            wp[int(m[1])] = dict(skill=int(m[3]), delay=int(m[10]), dmg=int(m[11]))
    for line in read('sql', 'item_mods.sql').splitlines():
        m = re.match(r'INSERT INTO `item_mods` VALUES \((\d+),(\d+),(-?\d+)\)', line)
        if m:
            mods.setdefault(int(m[1]), {})[int(m[2])] = int(m[3])
    return eq, wp, mods


EQ, WP, MODS = load_items()
ID = {}
for item_id, e in EQ.items():
    ID.setdefault(e['name'], item_id)
SLOTS = 'main sub range ammo head body hands legs feet neck waist ear1 ear2 ring1 ring2 back'.split()
JOBS = 'WAR MNK WHM BLM RDM THF PLD DRK BST BRD RNG SAM NIN DRG SMN BLU COR PUP DNC SCH GEO RUN'.split()


def runtime(with_mods=True):
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    mod_lines = [l for l in read('scripts', 'enum', 'mod.codegen.lua').splitlines() if re.match(r'\s*[A-Z0-9_]+\s*=\s*\d+,', l)]
    lua.execute('xi = { mod = {\n' + '\n'.join(mod_lines) + '\n} }')
    lua.execute('Module = { new = function() return {} end }; require = function() end')
    lua.execute(read('modules', 'custom', 'late', 'squad_gear_score.lua').replace('return m\n', ''))
    squad = read('modules', 'custom', 'lua', 'squad.lua')
    start = squad.index('function squadAutoEquip(player, mate)')
    lua.execute('SQUAD_TWO_HANDED = { [4] = true, [6] = true, [7] = true, [8] = true, [10] = true, [12] = true }\n'
                'function hasBit(mask, i) return math.floor((mask or 0) / 2 ^ i) % 2 == 1 end\n'
                'function levelsFor(mate) return mate.lvl end\n'
                'ITEMS = {}; UNLOCKS = {}; SET = {}; ASKED = 0\n'
                'function GetSquadUnlocks() return UNLOCKS end\n'
                'function GetSquadItemInfo(id) ASKED = ASKED + 1 return ITEMS[id] or { valid = false } end\n'
                'function SetSquadEquip(mateId, job, slot, item) SET[slot] = item end\n'
                # (2026-11-22) auto-equip also asks whether "Squad gets all gear" is on: off here, as it was for these
                # cases (test_all_gear_autoequip.py has it on)
                'function squadAllGear() return false end\n' + squad[start:squad.index('\nend\n', start) + 5])
    items = lua.globals().ITEMS
    for item_id, e in EQ.items():
        w = WP.get(item_id, {})
        t = lua.table(valid=True, name=e['name'], level=e['level'], jobs=e['jobs'], slot=e['slot'], shield=e['shield'],
                      skill=w.get('skill', 0), dmg=w.get('dmg', 0), delay=w.get('delay', 0))
        if with_mods:
            mt = lua.table()
            for k, v in MODS.get(item_id, {}).items():
                mt[k] = v
            t['mods'] = mt
        items[item_id] = t
    return lua


def outfit(lua, job, lvl, names):
    lua.execute('UNLOCKS = {}; SET = {}; SQUAD_ITEM_INFO = nil')
    unlocks = lua.globals().UNLOCKS
    for name in names:
        unlocks[ID[name]] = True
    mate = lua.table(mjob=JOBS.index(job) + 1, lvl=lvl, id=1, equip=lua.table())
    lua.globals().squadAutoEquip(lua.eval('{ getID = function() return 1 end }'), mate)
    return {SLOTS[s]: (EQ[i]['name'] if i else '') for s, i in dict(lua.globals().SET).items()}


lua = runtime()
G = lua.globals().SQUAD_GEAR_SCORE

# lilibun's examples
heads = ['silver_hairpin', 'leather_bandana', 'bronze_cap']
check('a level 20 Warrior wears the bandana, not the Silver Hairpin', outfit(lua, 'WAR', 20, heads).get('head') == 'leather_bandana')
check('a Black Mage of the same level does take the hairpin (MP+15)', outfit(lua, 'BLM', 20, heads).get('head') == 'silver_hairpin')
check('a White Mage too', outfit(lua, 'WHM', 20, heads).get('head') == 'silver_hairpin')
check('a Warrior with nothing but the hairpin leaves it off (it only costs him HP)', 'head' not in outfit(lua, 'WAR', 20, ['silver_hairpin']))
neck = ['spike_necklace', 'justice_badge']
check('Spike Necklace on a melee job', outfit(lua, 'WAR', 21, neck).get('neck') == 'spike_necklace')
check('...and on a Thief and a Samurai', outfit(lua, 'THF', 21, neck).get('neck') == 'spike_necklace' and outfit(lua, 'SAM', 21, neck).get('neck') == 'spike_necklace')
check('Justice Badge on a White Mage (the Spike Necklace takes 6 MND)', outfit(lua, 'WHM', 21, neck).get('neck') == 'justice_badge')
check('a White Mage with only the Spike Necklace leaves it off', 'neck' not in outfit(lua, 'WHM', 21, ['spike_necklace']))
ears = ['beetle_earring', 'beetle_earring_+1', 'energy_earring', 'energy_earring_+1']
got = outfit(lua, 'WAR', 21, ears)
check('Beetle Earrings in both ears of a melee job', {got.get('ear1'), got.get('ear2')} == {'beetle_earring', 'beetle_earring_+1'})
got = outfit(lua, 'BLM', 21, ears)
check('Energy Earrings in both ears of a mage', {got.get('ear1'), got.get('ear2')} == {'energy_earring', 'energy_earring_+1'})
rings = ['saintly_ring', 'courage_ring', 'balance_ring', 'eremites_ring']
got = outfit(lua, 'WHM', 14, rings)
check('Saintly Ring on a White Mage', 'saintly_ring' in (got.get('ring1'), got.get('ring2')) and 'courage_ring' not in got.values())
got = outfit(lua, 'RDM', 14, rings)
check('Saintly and Eremite\'s Rings on a Red Mage', {got.get('ring1'), got.get('ring2')} == {'saintly_ring', 'eremites_ring'})
got = outfit(lua, 'WAR', 14, rings)
check('Courage and Balance Rings on a Warrior', {got.get('ring1'), got.get('ring2')} == {'courage_ring', 'balance_ring'})

# weapons: what the job is good with, not the highest level
check('a Monk keeps his knuckles when a higher-level club is on offer', outfit(lua, 'MNK', 25, ['metal_knuckles', 'spiked_club_+1']).get('main') == 'metal_knuckles')
check('a Warrior takes the great axe over a higher-level dagger', outfit(lua, 'WAR', 20, ['greataxe', 'mercenarys_knife']).get('main') == 'greataxe')
got = outfit(lua, 'PLD', 60, ['bastard_sword', 'terras_staff', 'kite_shield'])
check('a Paladin keeps sword and shield when a Terra\'s Staff is on offer', got.get('main') == 'bastard_sword' and got.get('sub') == 'kite_shield')
got = outfit(lua, 'RNG', 50, ['war_bow', 'iron_arrow', 'silver_bullet', 'pet_food_delta', 'hawkers_knife'])
check('a Ranger: bow, arrows that fit it, and no pet food', got.get('range') == 'war_bow' and got.get('ammo') == 'iron_arrow')
got = outfit(lua, 'WAR', 20, ['greataxe', 'lauan_shield', 'tenax_strap'])
check('a two-handed weapon takes a grip, never a shield (as before)', got.get('main') == 'greataxe' and got.get('sub') == 'tenax_strap')
got = outfit(lua, 'WAR', 20, ['greataxe', 'lauan_shield'])
check('...and no shield when there is no grip', got.get('main') == 'greataxe' and not got.get('sub'))
check('a White Mage takes the wand with MND over a plain hammer of a higher level',
      outfit(lua, 'WHM', 20, ['yew_wand', 'warhammer']).get('main') == 'yew_wand')

# every job has weights and gets a number; an unknown job is rated as a melee fighter
rate, weights = G.rate, G.weights
hairpin = lua.globals().ITEMS[ID['silver_hairpin']]
check('all 22 jobs are rated', all(isinstance(rate(hairpin, job, 20), (int, float)) for job in range(1, 23)))
check('melee and tank jobs lose on the hairpin, MP jobs gain', all(rate(hairpin, j, 20) < 0 for j in (1, 2, 6, 12, 14)) and all(rate(hairpin, j, 20) > 0 for j in (3, 4, 5, 15, 20)))
check('an unknown job is rated like a melee job', abs(rate(hairpin, 99, 20) - rate(hairpin, 1, 20)) < 1e-9)
check('a weapon counts most for those who swing it', weights(1)['weapon'] > weights(7)['weapon'] > weights(3)['weapon'] and weights(11)['ranged'] > weights(1)['ranged'])
check('the same answer twice', outfit(lua, 'THF', 30, heads + neck + ears + rings) == outfit(lua, 'THF', 30, heads + neck + ears + rings))
lua.execute('ASKED = 0; SQUAD_ITEM_INFO = nil')
for _ in range(3):
    lua.execute('UNLOCKS = {}; SET = {}')
    for name in heads:
        lua.globals().UNLOCKS[ID[name]] = True
    lua.globals().squadAutoEquip(lua.eval('{ getID = function() return 1 end }'), lua.table(mjob=1, lvl=20, id=1, equip=lua.table()))
check('an item is read from the database once, not at every call', lua.globals().ASKED == len(heads))

# an older xi_map (no stats sent): by level, exactly as before
old = runtime(with_mods=False)
check('without stats from the server the highest level goes first, as before', outfit(old, 'WAR', 20, heads).get('head') == 'silver_hairpin')
check('...and nothing is left off', outfit(old, 'WHM', 21, ['spike_necklace']).get('neck') == 'spike_necklace')
check('rate() says it cannot tell', old.globals().SQUAD_GEAR_SCORE.rate(old.globals().ITEMS[ID['silver_hairpin']], 1, 20) is None)

cpp = read('modules', 'custom', 'cpp', 'squad.cpp')
start = cpp.index('auto getSquadItemInfo(const uint32 itemId) -> sol::table')
body = cpp[start:cpp.index('\n}\n', start)]
check('squad.cpp sends what a piece adds', 'SELECT modId, value FROM item_mods WHERE itemId = ?' in body and 'info["mods"] = mods;' in body)
check('squad.cpp sends a weapon\'s damage and delay', 'SELECT skill, dmg, delay FROM item_weapon WHERE itemId = ?' in body and 'info["dmg"]' in body and 'info["delay"]' in body)
check('...and still everything it sent before', all('info["%s"]' % k in body for k in ('valid', 'name', 'level', 'jobs', 'slot', 'shield', 'skill')))
check('braces balance', body.count('{') == body.count('}') + 1)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
