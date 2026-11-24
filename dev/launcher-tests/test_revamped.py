"""The Revamped switch (launcher_revamped.py), no screen needed: detection (package, shell, nothing), the ask-once rule,
the start script edits (on, off, back, twice), dualbox.txt, a missing package, CRLF kept, and the saved file.
Run:  python -I dev\\launcher-tests\\test_revamped.py"""
import json
import os
import shutil
import sys
import tempfile

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
import launcher_revamped as rv

checks = 0


def ok(condition, what):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(what)


SCRIPT = ("# Managed by the XI: Forever Offline launcher (Addons tab).\r\n/load thirdparty\r\n/addon load distance\r\n"
          "/addon load Gambits\r\n/addon load servermenu\r\n# /addon load squadpanel\r\n/addon load autobox\r\n/addon load followme\r\n")


def world(gambits=None, squads=None, script=SCRIPT, dual=None):
    """A fake kit + Ashita. gambits / squads: None, 'package' or 'shell'."""
    kit = tempfile.mkdtemp(prefix="revamped-")
    ash = os.path.join(kit, "Ashita")
    os.makedirs(os.path.join(ash, "scripts"))
    for comp, kind in (("gambits", gambits), ("squads", squads)):
        if kind:
            name = rv.TABLE[comp]["addon"]
            folder = os.path.join(ash, "addons", name)
            os.makedirs(folder)
            open(os.path.join(folder, name + ".lua"), "w").write("-- addon")
            if kind == "package":
                open(os.path.join(folder, rv.MARKERS[comp]), "w").write("-- package")
            if kind == "shell":
                open(os.path.join(folder, rv.SHELL_MARK), "w").write("{}")
    with open(os.path.join(ash, "scripts", "xiforever.txt"), "w", newline="") as f:
        f.write(script)
    if dual is not None:
        with open(os.path.join(ash, "scripts", "dualbox.txt"), "w", newline="") as f:
            f.write(dual)
    return kit, ash


def text(ash, name="xiforever.txt"):
    with open(os.path.join(ash, "scripts", name), newline="") as f:
        return f.read()


def active(ash, name="xiforever.txt"):
    return [l.strip() for l in text(ash, name).splitlines() if l.strip().lower().startswith("/addon load")]


# detection
kit, ash = world(gambits="package", squads="shell")
ok(rv.detected(ash) == ["gambits"], "a shell is not a package")
ok(rv.state(ash, "squads") == "shell", "shell recognised")
ok(rv.to_ask(kit, ash) == ["gambits"], "asks about the package only")
kit2, ash2 = world(squads="shell")
ok(rv.to_ask(kit2, ash2) == [], "silent when only shells are installed")
kit3, ash3 = world()
ok(rv.to_ask(kit3, ash3) == [] and rv.detected(ash3) == [], "silent with nothing installed")
ok(rv.apply(kit3, ash3) == [] and rv.load(kit3) == {}, "no choice, nothing written")

# ask once
kit, ash = world(gambits="package", squads="package")
ok(rv.to_ask(kit, ash) == ["gambits", "squads"], "both packages are asked about")
ok(rv.question(["gambits", "squads"]) == "Turn off the old Squads / old Gambits and use the Revamped versions?", "question text")
rv.declined(kit)
ok(rv.to_ask(kit, ash) == [], "No is not asked again")
ok("gambits" not in rv.load(kit) and text(ash) == SCRIPT, "No changes nothing")
shutil.rmtree(kit)

# Yes
kit, ash = world(gambits="package", squads="package")
before = text(ash)
messages = rv.choose(kit, ash, rv.detected(ash), "revamped", date="2026-11-23")
now = active(ash)
ok("/addon load GambitsRevamped" in now and "/addon load SquadsRevamped" in now, f"Revamped lines on: {now}")
ok("/addon load Gambits" not in now and "/addon load autobox" not in now, f"old Gambits lines off: {now}")
ok("/addon load servermenu" in now and "/addon load followme" in now, "servermenu and followme untouched")
ok("# (off 2026-11-23, launcher Revamped switch) /addon load Gambits" in text(ash), "the old line is commented in place")
ok("\r\n" in text(ash) and "\n" not in text(ash).replace("\r\n", ""), "CRLF kept")
ok(rv.load(kit)["gambits"] == "revamped" and rv.load(kit)["squads"] == "revamped" and rv.load(kit)["asked"], "file saved")
ok(messages, "messages say what changed")
ok(rv.apply(kit, ash, date="2026-11-24") == [] and text(ash).count("(off") == 2 + 0, "second run changes nothing")
# an old line comes back (Addons tab toggle): the next launch takes it off again
with open(os.path.join(ash, "scripts", "xiforever.txt"), "a", newline="") as f:
    f.write("/addon load Gambits\r\n")
ok(rv.apply(kit, ash, date="2026-11-24") != [] and "/addon load Gambits" not in active(ash), "a returned old line is turned off again")
# stock: back to how it was
rv.choose(kit, ash, ["gambits", "squads"], "stock", date="2026-11-25")
now = active(ash)
ok("/addon load Gambits" in now and "/addon load autobox" in now, f"old Gambits back on: {now}")
ok("/addon load GambitsRevamped" not in now and "/addon load SquadsRevamped" not in now, "Revamped lines off")
ok("squadpanel" not in "".join(now), "squadpanel was off before and stays off")
ok(rv.load(kit)["off"] == [], "the record of switched-off lines is empty again")
shutil.rmtree(kit)

# a Revamped package that is not installed: the old ones stay
kit, ash = world(gambits="package")
rv.choose(kit, ash, ["gambits", "squads"], "revamped", date="2026-11-23")
now = active(ash)
ok("/addon load SquadsRevamped" not in now, "a missing Squads package is not switched on")
ok("/addon load servermenu" in now, "the old Squads side is untouched")
shutil.rmtree(kit)
kit, ash = world(gambits="package")
rv.choose(kit, ash, ["gambits"], "revamped", date="2026-11-23")
os.rename(os.path.join(ash, "addons", "GambitsRevamped"), os.path.join(ash, "addons", "gone"))
with open(os.path.join(ash, "scripts", "xiforever.txt"), "w", newline="") as f:
    f.write(SCRIPT)
ok(rv.apply(kit, ash) == [] and "/addon load Gambits" in active(ash), "package removed: the old Gambits is not turned off")
shutil.rmtree(kit)

# the Revamped installer's own off-tag (an earlier install commented the line) is turned on
kit, ash = world(gambits="package", script=SCRIPT + "# (off 2026-11-22 until the chat-spam fix lands) /addon load GambitsRevamped\r\n")
rv.choose(kit, ash, ["gambits"], "revamped", date="2026-11-23")
ok(active(ash).count("/addon load GambitsRevamped") == 1 and "(off 2026-11-22 until" not in text(ash), "an installer-commented line is switched on in place")
shutil.rmtree(kit)

# a line the player commented by hand is not turned on by 'stock'
kit, ash = world(gambits="package", script="/addon load GambitsRevamped\n# /addon load Gambits\n/addon load servermenu\n")
rv.choose(kit, ash, ["gambits"], "stock", date="2026-11-23")
ok("/addon load Gambits" not in active(ash), "a hand-written '# /addon load Gambits' stays off")
shutil.rmtree(kit)

# the second window's script follows too, and a script with no Revamped line gets one
kit, ash = world(gambits="package", dual="/addon load autobox\n/addon load servermenu\n")
rv.choose(kit, ash, ["gambits"], "revamped", date="2026-11-23")
ok(active(ash, "dualbox.txt") == ["/addon load servermenu", "/addon load GambitsRevamped"] or
   set(active(ash, "dualbox.txt")) == {"/addon load servermenu", "/addon load GambitsRevamped"}, f"dualbox.txt: {active(ash, 'dualbox.txt')}")
ok("/addon load autobox" not in active(ash, "dualbox.txt"), "dualbox.txt: old engine off")
shutil.rmtree(kit)

# a damaged revamped.json is no choice, other keys survive a save
kit, ash = world(gambits="package")
os.makedirs(os.path.join(kit, "config"))
open(rv.config_path(kit), "w").write("{not json")
ok(rv.load(kit) == {} and rv.to_ask(kit, ash) == ["gambits"], "a damaged file is no choice")
open(rv.config_path(kit), "w").write(json.dumps({"shell_seen": 3, "gambits": "stock"}))
rv.choose(kit, ash, ["squads"], "revamped")
ok(rv.load(kit)["shell_seen"] == 3 and rv.load(kit)["gambits"] == "stock", "keys of the shell lane are kept")
ok(rv.choice(kit, "gambits") == "stock" and rv.to_ask(kit, ash) == [], "a saved choice is not asked again")
shutil.rmtree(kit)

# ---- v033: the shared switch file choice.txt (the game side, rv_switch.lua) and the shell add-ons ----
kit, ash = world(gambits="package", squads="package")
txt = rv.choice_txt_path(ash)
ok(rv.read_choice_txt(ash) == {"asked": False, "use": None}, "no choice.txt: never asked")
os.makedirs(os.path.dirname(txt))
open(txt, "w").write("asked=1\nuse_revamped=1\n")
ok(rv.to_ask(kit, ash) == [], "an in-game answer is not asked again in the launcher")
ok(rv.choice(kit, "gambits") == "revamped" and rv.choice(kit, "squads") == "revamped", "an in-game Yes is a Revamped choice")
rv.apply(kit, ash, "2026-11-23")
ok("/addon load GambitsRevamped" in active(ash) and "/addon load Gambits" not in active(ash), "an in-game Yes switches the start script")
rv.choose(kit, ash, ["gambits", "squads"], "stock")
ok(rv.read_choice_txt(ash) == {"asked": True, "use": False}, "the launcher writes use_revamped=0 for stock")
rv.choose(kit, ash, ["gambits"], "revamped")
ok(rv.read_choice_txt(ash) == {"asked": True, "use": True}, "the launcher writes use_revamped=1 for Revamped")
shutil.rmtree(kit)

kit, ash = world(gambits="package", squads="package")
rv.declined(kit, ash)
ok(rv.read_choice_txt(ash) == {"asked": True, "use": False} and rv.to_ask(kit, ash) == [], "No is written for the game too")
ok(active(ash) == ["/addon load distance", "/addon load Gambits", "/addon load servermenu", "/addon load autobox", "/addon load followme"],
   "No changes nothing in the start script")
shutil.rmtree(kit)

# a shell without its marker file is a shell; a package keeps its own file; shells are copied in once and loaded once
kit, ash = world()
for name in ("GambitsRevamped", "SquadsRevamped"):
    os.makedirs(os.path.join(kit, "addons-src", name))
    open(os.path.join(kit, "addons-src", name, name + ".lua"), "w").write("-- shell")
os.makedirs(os.path.join(ash, "addons"), exist_ok=True)
rv.apply(kit, ash)
ok(rv.state(ash, "gambits") == "shell" and rv.state(ash, "squads") == "shell" and rv.detected(ash) == [], "shells alone are not packages")
ok("/addon load GambitsRevamped" in active(ash) and "/addon load SquadsRevamped" in active(ash), "the shells load at start")
rv.apply(kit, ash)
ok(active(ash).count("/addon load GambitsRevamped") == 1, "twice does not add them twice")
ok(rv.to_ask(kit, ash) == [], "shells alone are never asked about")
open(os.path.join(ash, "addons", "GambitsRevamped", "gr_editor.lua"), "w").write("-- package")
open(os.path.join(kit, "addons-src", "GambitsRevamped", "GambitsRevamped.lua"), "w").write("-- shell again")
open(os.path.join(ash, "addons", "GambitsRevamped", "GambitsRevamped.lua"), "w").write("-- the package main file")
rv.apply(kit, ash)
ok(open(os.path.join(ash, "addons", "GambitsRevamped", "GambitsRevamped.lua")).read() == "-- the package main file", "a shell is never copied over a package")
ok(rv.detected(ash) == ["gambits"] and rv.to_ask(kit, ash) == ["gambits"], "the marker file makes it a package and the question is due")
shutil.rmtree(kit)

# the launcher is wired to it: the prompt at start, the switch before each game start (both ways of starting), the System box
with open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8") as f:
    gui = f.read()
ok("self.after(1800, self.revamped_prompt)" in gui, "the question is asked at launcher start")
ok(gui.count("self.apply_revamped()") == 2, "the scripts follow the choice before each game start")
ok("self.build_revamped()" in gui and "Use the Revamped versions" in gui and "Use the old versions" in gui, "System has the switch buttons")
ok("rv.to_ask(HERE, self.ashita)" in gui and "rv.declined(HERE, self.ashita)" in gui, "Yes saves, No is remembered")
# (v0.3.3a) without a package the buttons are greyed out and say where the switch comes from
ok('REVAMPED_GREY_TIP = "Comes with Gambits Revamped / Squads Revamped"' in gui, "the grey-out tip text")
ok("HoverTip(button, lambda b=button: REVAMPED_GREY_TIP" in gui and "disabledforeground=DIM" in gui, "disabled buttons are grey and carry the tip")
ok('button.configure(state="disabled")' in gui, "no package: the buttons are disabled, not hidden")

print(f"test_revamped: {checks} checks passed")
