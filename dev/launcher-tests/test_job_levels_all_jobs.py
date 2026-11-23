"""(krazy, 2026-11-22) "Cor not gaining EXP": a squad Corsair levelled in game while the launcher's Job levels tab kept
showing level 1. The tab filled in (and saved) jobs 1-15 only; Blue Mage, Corsair and Puppetmaster are 16-18.

Run: python test_job_levels_all_jobs.py      (reads launcher_gui.pyw; no window is opened)
"""
import os
import re
import sys

os.environ.setdefault('XIFO_TEST_PLATFORM', 'windows')
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_squad as sq
passed = failed = 0


def check(name, ok):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
        print('FAIL:', name)


gui = open(os.path.join(KIT, 'launcher_gui.pyw'), encoding='utf-8').read()
check('the squad has 18 jobs, the Aht Urhgan three last', len(sq.JOBS) == 18 and sq.JOBS[15:] == ['BLU', 'COR', 'PUP'])
check('no loop over the jobs stops at 15 any more', 'range(1, 16)' not in gui)
show = gui[gui.index('for job in range(1, len(sq.JOBS) + 1):\n            level, exp = m["jobs"].get(job, (1, 0))'):]
check('the Job levels tab fills in every job\'s level and exp', 'self.level_vars[job].set(level)' in show[:600] and 'self.level_vars[("exp", job)]' in show[:700])
save = gui[gui.index('def apply_levels(self):'):gui.index('def pick_item(self, slot, label):')]
check('Save levels goes through every job', re.search(r'for job in range\(1, len\(sq\.JOBS\) \+ 1\):', save) is not None)
build = gui[gui.index('def build_levels_page(self, pages):'):gui.index('def build_gear_page(self, pages):')]
check('every job has a field on the tab', 'for i, job in enumerate(sq.JOBS):' in build and 'self.level_vars[i + 1] = var' in build)
mate = {'jobs': {17: (16, 420), 3: (38, 3800)}}
check('the data it reads has the Corsair\'s real level', sq.job_level(mate, 17) == 16 and sq.job_level(mate, 16) == 1)
print(f'{passed} passed, {failed} failed')
sys.exit(1 if failed else 0)
