"""The newer World / Rules / Era pages (launcher_pages.py, launcher_settings.py, launcher_widgets.py) against the
Rates tab they sit on: every setting has a place, building the pages changes nothing, and each control writes what
the old one did. Needs a screen (real Tk). Run:  python dev\\launcher-tests\\test_settings.py"""
import importlib.machinery
import importlib.util
import itertools
import json
import os
import sys
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
import launcher_widgets as w

for name in ("askyesno", "askokcancel"):
    setattr(pages.messagebox, name, lambda *a, **k: True)
    setattr(gui.messagebox, name, lambda *a, **k: True)
for name in ("showinfo", "showerror", "showwarning"):
    setattr(gui.messagebox, name, lambda *a, **k: None)

root = tk.Tk()
root.withdraw()
pages.prepare(None, vars(gui))
checks = 0


def ok(condition, what):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(what)


def make(rates, player=False, with_pages=True):
    tab = gui.RatesTab(root, dict(rates), player=player)
    app = types.SimpleNamespace(rates_tab=tab, cfg={"mariadb_dir": "x"} if player else {}, squad_tab=None, _images=[])
    made = {}
    if with_pages:
        made["world"], made["rules"] = pages.WorldPage(root, app), pages.RulesPage(root, app)
        if not player:
            made["era"] = pages.EraPage(root, app)
    root.update()
    return tab, made


def settle():
    root.update()
    root.update_idletasks()


defaults = dict(core.RATE_DEFAULTS)
sets = {"defaults": defaults}
try:
    sets["this PC's rates.json"] = core.load_rates(KIT)
except Exception:
    pass
for preset, world, population in itertools.product(["Era default", "Relaxed solo", "Fast"], core.WORLDS, core.POPULATIONS):
    sets[f"{preset} / {world} / {population}"] = core.apply_world(core.apply_preset(defaults, preset), world, population)

# 1. every setting has a place, and every line of the table points at something real
for player in (False, True):
    tab, _ = make(defaults, player, with_pages=False)
    collected = tab.collect()
    ok(st.missing_keys(collected) == [], f"settings with no place on the new pages: {st.missing_keys(collected)} "
       "(add a line to launcher_settings.py)")
    for entry in st.SETTINGS:
        pages.variable_of(tab, entry)                       # raises if the tab has no such variable
        for key in entry["keys"]:
            ok(key in collected, f"launcher_settings.py names {key}, which the Rates tab does not save")
    for master in st.MASTERS.values():
        ok(isinstance(getattr(tab, master), tk.BooleanVar), f"section switch {master} is not an on/off value of the Rates tab")
    tab.destroy()
ids = {f[0] for f in core.RATE_FIELDS}
ok(ids <= st.covered_keys(), f"rate fields with no place: {sorted(ids - st.covered_keys())}")
keys = [e["key"] for e in st.SETTINGS]
ok(len(keys) == len(set(keys)), "a setting is listed twice in launcher_settings.py")
for page, columns in st.LAYOUT.items():
    names = [name for column in columns for name in column]
    used = {e["section"] for e in st.SETTINGS if e["page"] == page} | {n for n in st.MASTERS if n in names}
    ok(used <= set(names), f"{page}: sections in SETTINGS that LAYOUT does not place: {sorted(used - set(names))}")

# 2. making the pages changes nothing: the same rates.json as the old tab alone
for label, rates in sets.items():
    for player in (False, True):
        old, _ = make(rates, player, with_pages=False)
        new, made = make(rates, player)
        ok(new.collect() == old.collect(), f"{label} (player={player}): the pages changed what would be saved")
        if player:
            ok(new.collect() == core.lock_player_rates(new.collect()), f"{label}: a player install is no longer locked to the era values")
            ok("era" not in made, "the Era page was made on a player install")
        for page in made.values():
            page.destroy()
        old.destroy()
        new.destroy()

# 3. each control writes what the old one did
tab, made = make(defaults)
world, rules, era = made["world"], made["rules"], made["era"]
step = rules.controls["map.EXP_RATE"]
step.nudge(1)
ok(tab.collect()["map.EXP_RATE"] == 1.25, "plus on experience from monsters")
step.nudge(-1); step.nudge(-1)
ok(tab.collect()["map.EXP_RATE"] == 0.75, "minus on experience from monsters")
step.shown.set("3,5"); step.typed()
ok(tab.collect()["map.EXP_RATE"] == 3.5, "typing a rate")
step.shown.set("999"); step.typed()
ok(tab.collect()["map.EXP_RATE"] == 100.0, "a typed rate stays inside its limits")
step.shown.set("nonsense"); step.typed(); settle()
ok(tab.collect()["map.EXP_RATE"] == 100.0, "a typed word leaves the rate alone")
book = rules.controls["main.BOOK_EXP_RATE"]
book.nudge(1)
ok(tab.collect()["main.BOOK_EXP_RATE"] == 0.25, "FoV/GoV pages: 0.125 steps up to 0.25")
casket = rules.controls["main.CASKET_DROP_RATE"]
ok(casket.shown.get() == "10", f"casket chance shows as a percentage ({casket.shown.get()})")
casket.nudge(1)
ok(tab.collect()["main.CASKET_DROP_RATE"] == 0.15, "casket chance +5%")
casket.shown.set("12.5"); casket.typed()
ok(tab.collect()["main.CASKET_DROP_RATE"] == 0.125, "casket chance typed as 12.5")
nm = rules.controls["main.NM_LOTTERY_CHANCE"]
for _ in range(4):
    nm.nudge(-1)
ok(tab.collect()["main.NM_LOTTERY_CHANCE"] == 0, "NM chance down to 0")
nm.nudge(-1); settle()
ok(tab.collect()["main.NM_LOTTERY_CHANCE"] == -1 and nm.shown.get() == "always", "NM chance: one below 0 is 'always'")
nm.nudge(1)
ok(tab.collect()["main.NM_LOTTERY_CHANCE"] == 0, "NM chance: up from 'always' is 0")
speed = rules.controls["map.BASE_SPEED"]
speed.nudge(1)
ok(tab.collect()["map.BASE_SPEED"] == 55 and isinstance(tab.collect()["map.BASE_SPEED"], int), "run speed +5, a whole number")
cop = rules.controls["main.ENABLE_COP"]
cop.toggle()
ok(tab.collect()["main.ENABLE_COP"] == 0, "Chains of Promathia off")
cop.toggle()
ok(tab.collect()["main.ENABLE_COP"] == 1, "Chains of Promathia on")
travel = rules.controls["fast_travel"]
travel.toggle()
got = tab.collect()
ok(got["main.HOMEPOINT_TELEPORT"] == 0 and got["main.ENABLE_SURVIVAL_GUIDE"] == 0, "fast travel off = both teleports off")
travel.toggle()
got = tab.collect()
ok(got["main.HOMEPOINT_TELEPORT"] == 1 and got["main.ENABLE_SURVIVAL_GUIDE"] == 1, "fast travel on = both teleports on")
for key in ("all_crafts", "full_bags", "modern_stacks", "short_quest_waits"):
    before = tab.collect()[key]
    rules.controls[key].toggle()
    ok(tab.collect()[key] == (not before), f"switch {key}")
for key in ("crowds_chat", "crowds_chat_ai", "squad_chat", "bots_head_start"):
    before = tab.collect()[key]
    world.controls[key].toggle()
    ok(tab.collect()[key] == (not before), f"switch {key}")
for section, key in st.MASTERS.items():
    before = tab.collect()[key]
    world.cards[section].switch.toggle()
    ok(tab.collect()[key] == (not before), f"the switch beside {section}")
world.controls["crowds_chat_amount"].pick("busy")
ok(tab.collect()["crowds_chat_amount"] == "busy", "chat amount")
world.controls["bots_growth"].pick("fast")
ok(tab.collect()["bots_growth"] == "fast", "bot growth")
ok(tab.collect()["buff_range"] == "retail", "buff range starts at retail")
ok(not (rules.buff_warning.winfo_manager() == "pack"), "no buff range warning while Retail is picked")
rules.controls["buff_range"].pick("extended"); settle()
ok(tab.collect()["buff_range"] == "extended", "buff range: extended")
ok((rules.buff_warning.winfo_manager() == "pack") and rules.buff_warning.cget("text") == st.BUFF_RANGE_WARNING, "buff range warning shown with Extended")
ok([e for e in st.SETTINGS if e["key"] == "buff_range"][0]["tip"].count(st.BUFF_RANGE_WARNING) == 1, "the warning is in the tooltip")
rules.controls["buff_range"].pick("retail"); settle()
ok(tab.collect()["buff_range"] == "retail" and not (rules.buff_warning.winfo_manager() == "pack"), "buff range back to retail hides the warning")
world.controls["events"].pick("Always on")
ok(tab.collect()["events"] == "on", "seasonal events: always on")
world.controls["events"].pick("Off")
ok(tab.collect()["events"] == "off", "seasonal events: off")
world.controls["bots_online"].nudge(1)
ok(tab.collect()["bots_online"] == 60, "bots online +10")
world.controls["crowds_per_zone"].shown.set("99"); world.controls["crowds_per_zone"].typed()
ok(tab.collect()["crowds_per_zone"] == 40, "crowd size stays inside 0-40")
era.controls["main.ENABLE_WOTG"].toggle()
ok(tab.collect()["main.ENABLE_WOTG"] == 1, "Era page: Wings of the Goddess on")
era.controls["main.MAX_LEVEL"].nudge(1)
ok(tab.collect()["main.MAX_LEVEL"] == 76, "Era page: level cap")
era.controls["era_exp"].toggle()
ok(tab.collect()["era_exp"] is False, "Era page: era experience tables")
for page in made.values():
    page.destroy()
tab.destroy()

# 4. the world cards and the population buttons do what "Fill in" did
for start in ("defaults", "Fast / quiet / large"):
    for key in core.WORLDS:
        tab, made = make(sets[start])
        before = tab.collect()
        made["world"].pick_world(key)
        settle()
        ok(tab.collect() == core.apply_world(before, key, None), f"world card {key} from {start}")
        ok(made["world"].world_cards[key].selected, f"world card {key} is not marked after picking it")
        for page in made.values():
            page.destroy()
        tab.destroy()
    for key in core.POPULATIONS:
        tab, made = make(sets[start])
        before = tab.collect()
        made["world"].population.set(key)
        made["world"].pick_population()
        settle()
        ok(tab.collect() == core.apply_world(before, None, key), f"population {key} from {start}")
        ok(made["world"].population.get() == key, f"population {key} is not marked after picking it")
        for page in made.values():
            page.destroy()
        tab.destroy()

# 5. the preset cards do what "Fill in preset" did
for start in ("defaults", "Relaxed solo / living_ai / medium", "this PC's rates.json"):
    if start not in sets:
        continue
    for name, _words in pages.PRESET_CARDS:
        old, _ = make(sets[start], with_pages=False)
        old.preset.set(name)
        old.fill_preset()
        tab, made = make(sets[start])
        made["rules"].pick_preset(name)
        settle()
        ok(tab.collect() == old.collect(), f"preset card {name} from {start}")
        ok(made["rules"].preset_cards[name].selected, f"preset card {name} is not marked after picking it")
        for page in made.values():
            page.destroy()
        old.destroy()
        tab.destroy()

# 6. a player install: no dev-only line is drawn
tab, made = make(defaults, player=True)
drawn = set(made["world"].controls) | set(made["rules"].controls)
dev_only = {e["key"] for e in st.SETTINGS if e["dev"]}
ok(not (drawn & dev_only), f"dev-only settings drawn on a player install: {sorted(drawn & dev_only)}")
for key in core.PLAYER_HIDDEN_RATES:
    ok(key not in drawn, f"{key} is hidden from players but is on a page")

print(f"test_settings: {checks} checks passed ({len(sets)} sets of rates)")
