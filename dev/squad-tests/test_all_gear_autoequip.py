"""(2026-11-22, the user) "When someone has the setting to have all gear unlocked, auto-equip isn't working, but in the
text it says wear the best given item."

Auto-equip only chose from the gear that was given to the squad. With the launcher's "Squad gets all gear" on nothing
has to be given, so there was nothing to choose from. Now, with that switch on, it chooses from everything the job can
wear at its level (GetSquadGearPool in squad.cpp, asked once per job), and only puts on what adds something for the
job. The lines it says name where the choice was made from.

The Lua runs as written, against the real item tables (sql/item_equipment.sql, item_weapon.sql, item_mods.sql) and the
real rating (modules/custom/late/squad_gear_score.lua). The C++ can only be read here.
Run: python test_all_gear_autoequip.py [server folder]      (default C:\\ffxi-local\\server; needs lupa)
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
    with open(os.path.join(SERVER, *parts), encoding='utf-8', errors='replace') as handle:
        return handle.read().replace('\r\n', '\n')


def rows(table):
    out = []
    for line in read('sql', table + '.sql').splitlines():
        if line.startswith('INSERT INTO'):
            start = line.index('VALUES (') + 8
            body, vals, cur, quoted = line[start:line.index(');', start)], [], '', False
            for ch in body:
                if ch == "'":
                    quoted = not quoted
                elif ch == ',' and not quoted:
                    vals.append(cur)
                    cur = ''
                else:
                    cur += ch
            out.append(vals + [cur])
    return out


EQ = {int(r[0]): dict(name=r[1], level=int(r[2]), ilevel=int(r[3]), jobs=int(r[4]), shield=int(r[6]), slot=int(r[8])) for r in rows('item_equipment')}
WP = {int(r[0]): dict(skill=int(r[2]), delay=int(r[9]), dmg=int(r[10])) for r in rows('item_weapon')}
MODS = {}
for r in rows('item_mods'):
    MODS.setdefault(int(r[0]), {})[int(r[1])] = int(r[2])
ID = {}
for item_id, e in EQ.items():
    ID.setdefault(e['name'], item_id)
SLOTS = 'main sub range ammo head body hands legs feet neck waist ear1 ear2 ring1 ring2 back'.split()
JOBS = 'WAR MNK WHM BLM RDM THF PLD DRK BST BRD RNG SAM NIN DRG SMN BLU COR PUP DNC SCH GEO RUN'.split()
squad = read('modules', 'custom', 'lua', 'squad.lua')
cpp = read('modules', 'custom', 'cpp', 'squad.cpp')
MOD = {m[1]: int(m[2]) for m in (re.match(r'\s*([A-Z0-9_]+)\s*=\s*(\d+),', l) for l in read('scripts', 'enum', 'mod.codegen.lua').splitlines()) if m}
RACE_MOD = MOD['EQUIPMENT_ONLY_RACE']


def runtime(pool=True):
    """The auto-equip part of squad.lua with stand-ins for what squad.cpp gives it. pool=False: an xi_map from before
    GetSquadGearPool."""
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('xi = { mod = {\n' + '\n'.join(f'{k} = {v},' for k, v in MOD.items()) + '\n} }')
    lua.execute('Module = { new = function() return {} end }; require = function() end')
    lua.execute(read('modules', 'custom', 'late', 'squad_gear_score.lua').replace('return m\n', ''))

    def info(item_id):
        item_id = int(item_id)
        e, w = EQ.get(item_id), WP.get(item_id, {})
        if not e:
            return lua.table(valid=False)
        mods = lua.table()
        for k, v in MODS.get(item_id, {}).items():
            mods[k] = v
        return lua.table(valid=True, name=e['name'], level=e['level'], jobs=e['jobs'], slot=e['slot'], shield=e['shield'],
                         skill=w.get('skill', 0), dmg=w.get('dmg', 0), delay=w.get('delay', 0), mods=mods)

    def gear_pool(job, level):
        out = lua.table()
        for item_id, e in EQ.items():                 # the three queries of getSquadGearPool
            if (e['jobs'] >> (int(job) - 1)) & 1 and e['level'] <= int(level) and e['ilevel'] == 0:
                out[item_id] = info(item_id)
        return out

    g = lua.globals()
    g.pyInfo, g.pyPool = info, gear_pool
    start = squad.index('SQUAD_GEAR_POOL = SQUAD_GEAR_POOL or {}')
    lua.execute('SQUAD_TWO_HANDED = { [4] = true, [6] = true, [7] = true, [8] = true, [10] = true, [12] = true }\n'
                'function hasBit(mask, i) return math.floor((mask or 0) / 2 ^ i) % 2 == 1 end\n'
                'function levelsFor(mate) return mate.lvl end\n'
                'UNLOCKS = {}; SET = {}; ASKED = 0; POOLS = 0; ALL_GEAR = true\n'
                'function GetSquadUnlocks() return UNLOCKS end\n'
                'function GetSquadItemInfo(id) ASKED = ASKED + 1 return pyInfo(id) end\n'
                + ('function GetSquadGearPool(job, level) POOLS = POOLS + 1 return pyPool(job, level) end\n' if pool else '')
                + 'function SetSquadEquip(mateId, job, slot, item) SET[slot] = item end\n'
                'function squadAllGear() return ALL_GEAR end\n'
                + squad[start:squad.index('\nend\n', squad.index('function squadAutoEquip(player, mate)')) + 5])
    return lua


def outfit(lua, job, lvl, given=(), race=1, all_gear=True):
    lua.execute('UNLOCKS = {}; SET = {}')
    lua.globals().ALL_GEAR = all_gear
    unlocks = lua.globals().UNLOCKS
    for name in given:
        unlocks[ID[name]] = True
    mate = lua.table(mjob=JOBS.index(job) + 1, lvl=lvl, id=1, race=race, equip=lua.table())
    changed = lua.globals().squadAutoEquip(lua.eval('{ getID = function() return 1 end }'), mate)
    return changed, {SLOTS[s]: i for s, i in dict(lua.globals().SET).items() if i}


lua = runtime()
rate = lua.eval('function(id, job, lvl) return SQUAD_GEAR_SCORE.rate(pyInfo(id), job, lvl) end')

# ---------------------------------------------------------------- the report: all gear on, nothing given
changed, worn = outfit(lua, 'WAR', 75, all_gear=False)
check('all gear OFF and nothing given: nothing to put on (as before)', changed == 0 and worn == {})

changed, worn = outfit(lua, 'WAR', 75)
names = {slot: EQ[i]['name'] for slot, i in worn.items()}
check(f'all gear ON and nothing given: a level 75 Warrior is dressed ({changed} pieces)', changed >= 12 and len(worn) >= 12)
check('...in every armour slot', all(s in worn for s in ('head', 'body', 'hands', 'legs', 'feet')))
check('...with a weapon a Warrior is good with (great axe or axe): ' + names.get('main', '-'), WP.get(worn.get('main'), {}).get('skill') in (5, 6))
check('...and its main weapon is the best rated of everything it could hold',
      rate(worn['main'], 1, 75) >= max(rate(i, 1, 75) for i, e in EQ.items()
                                       if e['slot'] & 1 and e['jobs'] & 1 and e['level'] <= 75 and e['ilevel'] == 0 and not e['name'].startswith('judges_')) - 0.001)

FIT_JOBS = (('WAR', 75), ('WHM', 75), ('BLM', 30), ('THF', 10), ('PLD', 50), ('RNG', 75), ('MNK', 5), ('COR', 1), ('NIN', 75), ('BRD', 60), ('SMN', 40), ('PUP', 50))
for job, lvl in FIT_JOBS:
    j = JOBS.index(job)
    changed, worn = outfit(lua, job, lvl)
    items = [(slot, i, EQ[i]) for slot, i in worn.items()]
    check(f'{job} {lvl}: something is worn ({len(worn)} pieces)', len(worn) >= 8)
    check(f'{job} {lvl}: every piece is for that job, at or under its level, in its slot',
          all((e['jobs'] >> j) & 1 and e['level'] <= lvl and (e['slot'] >> SLOTS.index(slot)) & 1 for slot, i, e in items))
    check(f"{job} {lvl}: none of the game masters' Judge's set", not any(e['name'].startswith('judges_') for _, _, e in items))
    check(f'{job} {lvl}: every piece adds something for the job (no costume, fishing rod or pearl)',
          all(rate(i, j + 1, lvl) > e['level'] * 0.005 + 0.0001 for _, i, e in items))
    check(f'{job} {lvl}: nothing made for another race (a Hume male)',
          all(MODS.get(i, {}).get(RACE_MOD, 0) == 0 or MODS[i][RACE_MOD] & 1 for _, i, _ in items))
    check(f'{job} {lvl}: no piece twice', len(set(worn.values())) == len(worn))

for job, lvl in (('BLM', 30), ('WHM', 75), ('SMN', 40)):
    _, worn = outfit(lua, job, lvl)
    check(f'{job} {lvl}: no bow, gun or throwing weapon for a job with no skill in it',
          not any(25 <= WP.get(i, {}).get('skill', 0) <= 27 for i in worn.values()))
_, worn = outfit(lua, 'RNG', 75)
check('a Ranger still gets a bow or gun, and ammunition for it',
      WP.get(worn.get('range'), {}).get('skill') in (25, 26) and WP.get(worn.get('ammo'), {}).get('skill') == WP[worn['range']]['skill'])
_, worn = outfit(lua, 'MNK', 5)
check('a level 5 Monk does not wear the Moogle Suit, a fishing rod or a Signal Pearl',
      not ({EQ[i]['name'] for i in worn.values()} & {'moogle_suit', 'ebisu_fishing_rod', 'signal_pearl', 'tactics_pearl', 'soulgauger_sgr-1'}))

# another race's gear is left out; the same mate of that race may get it
race_only = [i for i, m in MODS.items() if m.get(RACE_MOD, 0) > 0 and i in EQ]
check('the item tables have race-only gear to test with', len(race_only) > 50)
for race in (1, 3, 5, 7, 8):
    _, worn = outfit(lua, 'WAR', 30, race=race)
    check(f'race {race}: nothing made only for other races',
          all(MODS.get(i, {}).get(RACE_MOD, 0) == 0 or (MODS[i][RACE_MOD] >> (race - 1)) & 1 for i in worn.values()))

# ---------------------------------------------------------------- gear you gave, with all gear on
_, worn = outfit(lua, 'WAR', 20, given=['leather_bandana'])
best_head = worn.get('head')
check('all gear ON: a better piece than the one you gave is put on', best_head is not None and rate(best_head, 1, 20) >= rate(ID['leather_bandana'], 1, 20))
_, alone = outfit(lua, 'WAR', 75)
_, with_given = outfit(lua, 'WAR', 75, given=[EQ[alone['body']]['name']])
check('the best piece is the same whether you gave it or not', with_given.get('body') == alone['body'])
lua.execute('''
tie = { { id = 2, info = { level = 10 }, score = 5 }, { id = 1, info = { level = 10 }, score = 5, given = true }, { id = 3, info = { level = 12 }, score = 5 } }
''')
sort_src = squad[squad.index('    table.sort(cand, function(a, b)'):squad.index('    local used, pick = {}, {}')]
lua.execute('local cand, scored = tie, true\n' + sort_src)
check('between equally good pieces the one you gave comes first', lua.eval('tie[1].id') == 1 and lua.eval('tie[2].id') == 3)

_, worn = outfit(lua, 'WAR', 20, given=['leather_bandana'], all_gear=False)
check('all gear OFF: only what you gave, as before', {EQ[i]['name'] for i in worn.values()} == {'leather_bandana'})

# ---------------------------------------------------------------- the pool is asked once per job
lua.execute('POOLS = 0; ASKED = 0')
for lvl in (10, 40, 75, 75):
    outfit(lua, 'DRK', lvl)
check('the whole list is asked once per job, whatever the level', lua.eval('POOLS') == 1)
check('and no piece of it is asked for one by one', lua.eval('ASKED') == 0)
outfit(lua, 'SAM', 75)
check('another job asks once more', lua.eval('POOLS') == 2)

# ---------------------------------------------------------------- an older xi_map (no GetSquadGearPool)
old = runtime(pool=False)
changed, worn = outfit(old, 'WAR', 75)
check('older server program, all gear ON, nothing given: nothing happens, and nothing breaks', changed == 0 and worn == {})
_, worn = outfit(old, 'WAR', 20, given=['leather_bandana'])
check('older server program: gear you gave still works', {EQ[i]['name'] for i in worn.values()} == {'leather_bandana'})

# ---------------------------------------------------------------- what it says
cmd = squad[squad.index("    if action == 'autoequip' or action == 'auto' then"):]
cmd = cmd[:cmd.index("\n    if action == ", 10)]
check('with all gear on the lines say the choice is from everything their jobs can wear',
      'the best gear their jobs and levels can wear ("Squad gets all gear" is on)' in cmd and "'the best gear you have given them'" in cmd)
check('...also for !squad autoequip now', "allGear and ', from everything their jobs can wear' or ''" in cmd)
check('an older server program is named as the reason when it cannot list all gear',
      "type(GetSquadGearPool) ~= 'function'" in cmd and 'cannot list all gear yet' in cmd)
check('the help line mentions it', 'with "Squad gets all gear" on, the best their jobs can wear' in squad)

# ---------------------------------------------------------------- squad.cpp (read only)
fn = cpp[cpp.index('auto getSquadGearPool(const uint32 job, const uint32 level) -> sol::table'):cpp.index('// Basic level 1 gear a job can wear')]
check('GetSquadGearPool is registered for Lua', '::lua.set_function("GetSquadGearPool", getSquadGearPool);' in cpp)
check('three queries, whatever the number of pieces', fn.count('db::preparedStmt(') == 3)
check('gear the job can wear up to the level, no item-level gear',
      fn.count('(jobs & ?) <> 0 AND level <= ? AND ilevel = 0') == 1 and fn.count('(e.jobs & ?) <> 0 AND e.level <= ? AND e.ilevel = 0') == 2)
for field in ('valid', 'name', 'level', 'jobs', 'slot', 'shield', 'skill', 'dmg', 'delay', 'mods'):
    check(f'each piece carries {field}, as GetSquadItemInfo does', f'info["{field}"]' in fn or f'it->second["{field}"]' in fn)
check('a job outside 1-22 gets an empty list', 'if (job < 1 || job > 22)' in fn)
check('braces and brackets balance in the new function', fn.count('{') == fn.count('}') and fn.count('(') == fn.count(')'))

print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
