"""(Velderen, 2026-11-22) "Auction house from anywhere": the ahgo add-on's /ah opens the auction house in any area, but
the server only answered in areas that have one. RULES > Comforts has a switch for it, off by default (the era).

Run with: python test_ah_anywhere.py [server folder]      (default C:\\ffxi-local\\server)
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


defaults = read('settings', 'default', 'map.lua')
check('the server knows the setting and it is off', re.search(r'^\s*AH_ANYWHERE\s*=\s*0\s*,', defaults, re.M) is not None)

cpp = read('src', 'map', 'packets', 'c2s', '0x04e_auc.cpp')
start = cpp.index('GP_CLI_COMMAND_AUC::validate')
body = cpp[start:cpp.index('switch (this->Command)', start)]
guard = re.search(r'if \(settings::get<uint8>\("map\.AH_ANYWHERE"\) == 0\)\s*\{\s*pv\.hasZoneMiscFlag\(xi::ZoneMisc::AuctionHouse\);\s*\}', body)
check('off: the area still has to have an Auction House', guard is not None)
check('the area check is nowhere else in the request check', body.count('hasZoneMiscFlag') == 1)
check('the other checks are all still there (event, jail, command, result)',
      all(word in body for word in ('BlockedState::InEvent', 'jailutils::InPrison', 'oneOf<GP_CLI_COMMAND_AUC_COMMAND>', '"Result not 0"', '"Result status"')))
check('braces balance', body.count('{') == body.count('}') + 1 and body.count('(') == body.count(')'))
check('the settings header is included', '#include "common/settings.h"' in cpp)
check('delivery boxes are not touched by the switch', 'AH_ANYWHERE' not in read('src', 'map', 'packets', 'c2s', '0x04d_pbx.cpp'))

field = {f[0]: f for f in core.RATE_FIELDS}.get('map.AH_ANYWHERE')
check('the launcher has it, off by default, on or off only', field is not None and field[1] == 'map.lua' and field[4:7] == (0, 0, 1))
line = {e['key']: e for e in st.SETTINGS}.get('map.AH_ANYWHERE')
check('RULES > Comforts, a switch', line is not None and (line['page'], line['section'], line['kind']) == ('rules', 'Comforts', st.FLAG))
check('its tip names the add-on and the command', line is not None and 'ahgo' in line.get('tip', '') and '/ah' in line.get('tip', ''))
for value in (0, 1):
    tmp = tempfile.mkdtemp()
    try:
        shutil.copytree(os.path.join(SERVER, 'settings', 'default'), os.path.join(tmp, 'settings', 'default'))
        rates = dict(core.RATE_DEFAULTS)
        rates['map.AH_ANYWHERE'] = value
        core.apply_rates(tmp, rates)
        with open(os.path.join(tmp, 'settings', 'map.lua'), encoding='utf-8') as handle:
            written = handle.read()
        check('the launcher writes %d to the server' % value, re.search(r'^\s*AH_ANYWHERE\s*=\s*%d\s*,' % value, written, re.M) is not None)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
