"""The six switches for the 2026-11-21 additions (crowds through the gates / stopping for each other, bot players'
emotes, death memory, life stories, gate travel): saved in rates.json, written to extras_config.lua on every launch,
shown in the classic Rates list and on the World page, for players as well as the dev launcher.
Needs a screen (real Tk). Run:  python dev\\launcher-tests\\test_extras_switches.py"""
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import types

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
import tkinter as tk

loader = importlib.machinery.SourceFileLoader("launcher_gui_under_test", os.path.join(KIT, "launcher_gui.pyw"))
gui = importlib.util.module_from_spec(importlib.util.spec_from_loader("launcher_gui_under_test", loader))
loader.exec_module(gui)
import launcher_core as core
import launcher_pages as pages
import launcher_settings as st

for name in ("askyesno", "askokcancel"):
    setattr(pages.messagebox, name, lambda *a, **k: True)
    setattr(gui.messagebox, name, lambda *a, **k: True)

KEYS = ("crowd_gates", "crowd_meet", "bot_social", "bot_memory", "bot_story", "bot_gates")
CLASSIC = ("Crowds use the gates", "Crowds stop for each other", "Bot emotes", "Bots remember where they died",
           "Bot life stories", "Bots use the town gates")
PAGE = ("Come and go through the gates", "Stop for each other", "Emotes and greetings", "Remember where they died",
        "Life stories", "Use the town gates")
count = 0


def check(condition, what):
    global count
    assert condition, what
    count += 1


def texts(widget, out):
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
            if text:
                out.append(str(text))
        except Exception:
            pass
        texts(child, out)
    return out


# --- saved, loaded and written -------------------------------------------------------------------------------
check(core.EXTRAS_KEYS == KEYS, "the six keys, in the order extras.lua lists them")
check(all(core.RATE_DEFAULTS[k] is True for k in KEYS), "all on by default")
check(not any(k in core.PLAYER_HIDDEN_RATES for k in KEYS), "players may change them")
with tempfile.TemporaryDirectory() as box:
    here, server = os.path.join(box, "kit"), os.path.join(box, "server")
    os.makedirs(here)
    with open(os.path.join(here, "rates.json"), "w", encoding="utf-8") as f:
        json.dump({"bots": True}, f)                       # a rates.json from before the switches
    rates = core.load_rates(here)
    check(all(rates[k] is True for k in KEYS), "an older rates.json: everything on")
    with open(os.path.join(here, "rates.json"), "w", encoding="utf-8") as f:
        json.dump({"bot_gates": False, "crowd_meet": 0, "bot_story": True}, f)
    rates = core.load_rates(here)
    check(rates["bot_gates"] is False and rates["crowd_meet"] is False, "a saved off is kept")
    check(rates["bot_story"] is True and rates["bot_social"] is True, "the rest stay on")
    core.write_crowds_config(server, rates)
    with open(os.path.join(server, "modules", "custom", "lua", "extras_config.lua"), encoding="utf-8") as f:
        written = f.read()
    check(written.count("\n") == 2 and written.split("\n")[1].startswith("return { "), "one comment line, one table")
    for k in KEYS:
        check("%s = %s" % (k, "true" if rates[k] else "false") in written, "extras_config.lua: " + k)
    locked = core.lock_player_rates(rates)
    check(all(locked[k] == rates[k] for k in KEYS), "a player's own choices survive the player lock")
    for name in core.RATE_PRESETS:
        preset = core.apply_preset(rates, name)
        check(all(preset[k] == rates[k] for k in KEYS), "a rates preset leaves them alone: " + name)

# --- both views ------------------------------------------------------------------------------------------------
root = tk.Tk()
root.withdraw()
pages.prepare(None, vars(gui))
lines = {entry["key"]: entry for entry in st.SETTINGS}
check(all(lines[k]["page"] == "world" and not lines[k]["dev"] for k in KEYS), "on the World page, players too")
check([lines[k]["section"] for k in KEYS] == ["Town crowds"] * 2 + ["Bot players"] * 4, "under crowds and bots")
for player in (False, True):
    rates = dict(core.RATE_DEFAULTS)
    rates["bot_gates"] = rates["crowd_meet"] = False
    tab = gui.RatesTab(root, dict(rates), player=player)
    app = types.SimpleNamespace(rates_tab=tab, cfg={"mariadb_dir": "x"} if player else {}, squad_tab=None, _images=[])
    world = pages.WorldPage(root, app)
    root.update()
    got = tab.collect()
    check(all(got[k] == rates[k] for k in KEYS), "building both views changes nothing")
    tab.bot_gates.set(True)
    tab.bot_social.set(False)
    root.update()
    got = tab.collect()
    check(got["bot_gates"] is True and got["bot_social"] is False, "a switch is collected")
    shown = " | ".join(texts(tab, []))
    for label in CLASSIC:
        check(label in shown, "classic Rates list: " + label)
    shown = " | ".join(texts(world, []))
    for label in PAGE:
        check(label in shown, ("player" if player else "dev") + " World page: " + label)
root.destroy()
print("test_extras_switches: %d checks passed" % count)
