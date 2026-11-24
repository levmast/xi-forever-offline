"""Training dummies (Rolanberry Fields) are on by default (v0.3.3a), no screen needed:
a new install has them on and squad_config.lua says so; a switch the player turned off himself (explicit) stays off;
an older rates.json with a saved False and no explicit record gets the new default; presets and profiles keep the rule.
Run:  python -I dev/launcher-tests/test_training_dummies.py"""
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


def load_saved(saved):
    here = tempfile.mkdtemp(prefix="dummies-")
    try:
        if saved is not None:
            with open(core.rates_path(here), "w", encoding="utf-8") as f:
                json.dump(saved, f)
        return core.load_rates(here)
    finally:
        shutil.rmtree(here, ignore_errors=True)


def squad_config(rates):
    server = tempfile.mkdtemp(prefix="dummies-srv-")
    try:
        core.write_crowds_config(server, rates)
        with open(os.path.join(server, "modules", "custom", "lua", "squad_config.lua"), encoding="utf-8") as f:
            return f.read()
    finally:
        shutil.rmtree(server, ignore_errors=True)


ok(core.RATE_DEFAULTS["training_dummies"] is True, "the default is on")
ok(core.RATE_DEFAULTS["training_dummies_explicit"] is False, "no explicit record by default")
ok(load_saved(None)["training_dummies"] is True, "a new install (no rates.json) has the dummies on")
ok("training_dummies = true" in squad_config(dict(core.RATE_DEFAULTS)),
   "squad_config.lua tells the server the dummies are on")
ok("training_dummies = true" in squad_config({}), "squad_config.lua: a rates dict without the key means on")
ok(load_saved({"training_dummies": False})["training_dummies"] is True, "an old saved False with no explicit record: the new default (on)")
ok(load_saved({"training_dummies": False, "training_dummies_explicit": False})["training_dummies"] is True, "explicit false: still the default")
off = load_saved({"training_dummies": False, "training_dummies_explicit": True})
ok(off["training_dummies"] is False and off["training_dummies_explicit"] is True, "a player who turned it off keeps it off")
ok("training_dummies = false" in squad_config(off), "squad_config.lua says off for him")
ok(load_saved({"training_dummies": True, "training_dummies_explicit": True})["training_dummies"] is True, "explicit on stays on")
ok(core.apply_preset({}, next(iter(core.RATE_PRESETS)))["training_dummies"] is True, "a preset keeps the default")
ok(core.apply_preset(off, next(iter(core.RATE_PRESETS)))["training_dummies"] is False, "a preset keeps an explicit off")
ok("training_dummies_explicit" in core.PROFILE_SKIP, "a shared profile does not carry one player's choice record")
print("PASS: %d checks" % checks)
