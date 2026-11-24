"""The Buff range option (rates key buff_range -> settings/map.lua TRUST_AOE_RANGE), no screen needed:
both values are written, anything else falls back to retail, a server without the key is skipped with no message,
rates.json keeps the value, and presets keep it. Run:  python -I dev\\launcher-tests\\test_buff_range.py"""
import json
import os
import shutil
import sys
import tempfile

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
import launcher_core as core

checks = 0


def ok(condition, what):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(what)


MAIN = "xi = xi or {}\nxi.settings = xi.settings or {}\nxi.settings.main = {\n}\n"
LOGIN = "xi.settings.login = {\n}\n"
MAP_NEW = ("xi.settings.map = {\n    EXP_RATE = 1.000,\n    FISHING_DAILY_LIMITS = true,\n"
           "    TRUST_AOE_RANGE = 'retail', -- 'retail' or 'extended'\n    SPEED_LIMIT = 80,\n}\n")
MAP_OLD = "xi.settings.map = {\n    EXP_RATE = 1.000,\n    SPEED_LIMIT = 80,\n}\n"


def write_server(map_text):
    root = tempfile.mkdtemp(prefix="buff-range-")
    default = os.path.join(root, "settings", "default")
    os.makedirs(default)
    for name, text in (("main.lua", MAIN), ("login.lua", LOGIN), ("map.lua", map_text)):
        with open(os.path.join(default, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return root


def written(root):
    with open(os.path.join(root, "settings", "map.lua"), encoding="utf-8") as f:
        return f.read()


for value, wanted in (("retail", "'retail'"), ("extended", "'extended'"), ("bogus", "'retail'"), (None, "'retail'"),
                      ("extended'; os.execute('x", "'retail'")):
    root = write_server(MAP_NEW)
    rates = dict(core.RATE_DEFAULTS)
    if value is not None:
        rates["buff_range"] = value
    messages = core.apply_rates(root, rates)
    text = written(root)
    ok(f"TRUST_AOE_RANGE = {wanted}," in text, f"buff_range {value!r}: wanted {wanted} in map.lua")
    ok("-- 'retail' or 'extended'" in text, "the comment after the value is left alone")
    ok(not any("TRUST_AOE_RANGE" in m for m in messages), f"buff_range {value!r}: no message about the key ({messages})")
    shutil.rmtree(root)

# an older server: the default file has no such key. Nothing is added, and no message says so.
root = write_server(MAP_OLD)
messages = core.apply_rates(root, dict(core.RATE_DEFAULTS, buff_range="extended"))
ok("TRUST_AOE_RANGE" not in written(root), "an older server's map.lua is left without the key")
ok(not any("TRUST_AOE_RANGE" in m for m in messages), f"older server: no message ({messages})")
shutil.rmtree(root)

# rates.json round trip
ok(core.RATE_DEFAULTS["buff_range"] == "retail", "the default is retail")
here = tempfile.mkdtemp(prefix="buff-range-rates-")
for value in ("extended", "retail"):
    with open(core.rates_path(here), "w", encoding="utf-8") as f:
        json.dump(dict(core.RATE_DEFAULTS, buff_range=value), f)
    ok(core.load_rates(here)["buff_range"] == value, f"rates.json keeps {value}")
with open(core.rates_path(here), "w", encoding="utf-8") as f:
    json.dump(dict(core.RATE_DEFAULTS, buff_range="everywhere"), f)
ok(core.load_rates(here)["buff_range"] == "retail", "an unknown value in rates.json loads as retail")
os.remove(core.rates_path(here))
ok(core.load_rates(here)["buff_range"] == "retail", "no rates.json: retail")
shutil.rmtree(here)

# presets keep what was picked (it is a server switch, not a rate) and clean up a bad value
for name in ("Era default", "Relaxed solo", "Fast"):
    ok(core.apply_preset({"buff_range": "extended"}, name)["buff_range"] == "extended", f"{name} keeps extended")
    ok(core.apply_preset({}, name)["buff_range"] == "retail", f"{name} without a choice is retail")
    ok(core.apply_preset({"buff_range": "x"}, name)["buff_range"] == "retail", f"{name} cleans a bad value")

print(f"test_buff_range: {checks} checks passed")
