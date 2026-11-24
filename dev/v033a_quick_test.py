#!/usr/bin/env python3
"""v0.3.3a quick test (kit): every automated check of this update, one command, PASS or FAIL per check.

    python dev/v033a_quick_test.py        (from the kit folder; needs Python 3 and the `lupa` package: pip install lupa)

No game, no server, no network; nothing outside temporary folders is written. The launcher tests open a small hidden Tk window.
Add a server folder as the first argument to also run the Squads tests that read the server's Lua (they need a full server tree
with scripts/enum/mod.codegen.lua, i.e. one that was built once).
"""
import os
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = [
    ("Buff range option (Rules page, map.lua key)", "dev/launcher-tests/test_buff_range.py"),
    ("Launcher settings page", "dev/launcher-tests/test_settings.py"),
    ("Training dummies on by default (an explicit off is kept)", "dev/launcher-tests/test_training_dummies.py"),
    ("Revamped switch (greyed out without a package)", "dev/launcher-tests/test_revamped.py"),
    ("Revamped shell add-ons", "dev/revamped-tests/test_revamped_shells.py"),
    ("Third-party manager (downloads, checksums, versions, uninstall, old files)", "dev/thirdparty-tests/test_thirdparty.py"),
    ("Start-up check for newer versions", "dev/launcher-tests/test_start_checks.py"),
    ("Launcher update", "dev/update-tests/test_update.py"),
    ("HD texture packs (upstream v0.3.3, still green)", "dev/launcher-tests/test_hd_packs.py"),
    ("XISpeaks download (upstream, still green with downloads cleanup)", "dev/launcher-tests/test_xispeaks.py"),
]
SERVER_TESTS = [
    ("Squad auto-equip with all gear (needs a server folder)", "dev/squad-tests/test_all_gear_autoequip.py"),
    ("Squad gear score (needs a server folder)", "dev/squad-tests/test_gear_score.py"),
    ("Squad attack order (needs a server folder)", "dev/squad-tests/test_attack_order.py"),
]


def run_lua(path):
    """Child mode: python v033a_quick_test.py --lua <test.lua>  (the Server menu addon channel test; stand-in Ashita)."""
    from lupa.luajit21 import LuaRuntime
    rt = LuaRuntime(unpack_returned_tuples=True)
    rt.globals().arg = rt.table_from({0: path.replace("\\", "/")})
    os.chdir(os.path.dirname(path))
    with open(path, encoding="utf-8") as handle:
        rt.execute(handle.read())
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--lua":
        return run_lua(sys.argv[2])
    jobs = [(label, [sys.executable, "-I", os.path.join(KIT, rel)]) for label, rel in TESTS]
    jobs.append(("Server menu addon channel (stand-in Ashita)",
                 [sys.executable, "-I", os.path.abspath(__file__), "--lua", os.path.join(KIT, "dev/duo-tests/test_servermenu_channel.lua")]))
    if len(sys.argv) > 1:
        jobs += [(label, [sys.executable, "-I", os.path.join(KIT, rel), sys.argv[1]]) for label, rel in SERVER_TESTS]
    bad = 0
    for label, cmd in jobs:
        result = subprocess.run(cmd, cwd=KIT, capture_output=True, text=True, check=False)
        text = result.stdout + result.stderr
        good = result.returncode == 0 and "FAILED" not in text and "Traceback" not in text and " 0 passed" not in text
        print(("PASS  " if good else "FAIL  ") + label)
        if not good:
            bad += 1
            print("      " + "\n      ".join(text.strip().splitlines()[-10:]))
    total = len(jobs)
    print("\nALL %d CHECKS PASS" % total if not bad else "\n%d of %d CHECKS FAILED" % (bad, total))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
