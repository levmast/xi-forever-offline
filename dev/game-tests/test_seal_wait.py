"""(delukard, 2026-11-22) "Wait between seals": Beastmen's and Kindred's Seals drop once per party every 5 minutes
(the base's rule). RULES > Loot and gil has a slider for it, 0 to 5 minutes.

Run with: python test_seal_wait.py [server folder]      (default C:\\ffxi-local\\server)
"""
import os
import re
import shutil
import sys
import tempfile

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


check('the server knows the setting and it is 5', re.search(r'^\s*SEAL_DROP_MINUTES\s*=\s*5\s*,', read('settings', 'default', 'main.lua'), re.M) is not None)
cpp = read('src', 'map', 'entities', 'mob_entity.cpp')
start = cpp.index('auto specialDropCooldown() -> timer::duration')
body = cpp[start:cpp.index('\n}\n', start)]
check('the wait is read from the setting', 'settings::get<float>("main.SEAL_DROP_MINUTES")' in body)
check('below 0 counts as the base\'s 5 minutes, and it is never more than an hour', 'if (minutes < 0.0f)' in body and 'return SPECIAL_DROP_COOLDOWN;' in body
      and 'std::min(minutes, 60.0f) * 60.0f' in body)
check('both places that start the wait use it', cpp.count('AddLootRecast(id, specialDropCooldown());') == 2 and 'AddLootRecast(id, SPECIAL_DROP_COOLDOWN)' not in cpp)
check('the base\'s 5 minutes is still what the constant says', 'constexpr timer::duration SPECIAL_DROP_COOLDOWN = 5min;' in cpp)
check('braces balance', body.count('{') == body.count('}') + 1)
field = {f[0]: f for f in core.RATE_FIELDS}.get('main.SEAL_DROP_MINUTES')
check('the launcher has it: 5 by default, 0 to 5, whole minutes', field is not None and field[1] == 'main.lua' and field[4:8] == (5, 0, 5, 'int'))
line = {e['key']: e for e in st.SETTINGS}.get('main.SEAL_DROP_MINUTES')
check('RULES > Loot and gil, a number', line is not None and (line['page'], line['section'], line['kind']) == ('rules', 'Loot and gil', st.NUMBER))
for value in (0, 2, 5):
    tmp = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(SERVER, 'settings', 'default'), os.path.join(tmp, 'settings', 'default'))
        rates = dict(core.RATE_DEFAULTS)
        rates['main.SEAL_DROP_MINUTES'] = value
        core.apply_rates(tmp, rates)
        with open(os.path.join(tmp, 'settings', 'main.lua'), encoding='utf-8') as handle:
            written = handle.read()
        check('the launcher writes %d to the server' % value, re.search(r'^\s*SEAL_DROP_MINUTES\s*=\s*%d\s*,' % value, written, re.M) is not None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
