"""Limited-time banners (assets\\press\\name__until-YYYY-MM-DD.png): they take the place of the usual banners up to and
including that day, and the day after the usual ones are back by themselves.

Starts the real launcher twice from a COPY of the kit (stand-in config, database driver and addons folder; nothing of
the real install is read or changed): once today, once with the calendar set far ahead. Needs python3-tk, Pillow and a
screen:
    xvfb-run -a -s "-screen 0 1500x1000x24" python3 dev/launcher-tests/test_limited_banners.py [OUTDIR for screenshots]"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PICS = (".png", ".jpg", ".jpeg")


def day(offset):
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


def make_copy():
    work = tempfile.mkdtemp(prefix="xif-until-")
    kit = os.path.join(work, "kit")
    os.makedirs(kit)
    for name in os.listdir(KIT):
        path = os.path.join(KIT, name)
        if os.path.isfile(path) and (name.startswith("launcher_") and name.endswith((".py", ".pyw"))
                                     or name in ("rates.json", "thirdparty.json", "graphics.json", "gfxmod.json", "contributors.json",
                                                 "CREDITS.md", "config.example.json")):
            shutil.copy2(path, os.path.join(kit, name))
    for folder in ("ui", "press"):
        source = os.path.join(KIT, "assets", folder)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(kit, "assets", folder))
    press = os.path.join(kit, "assets", "press")
    os.makedirs(press, exist_ok=True)
    from PIL import Image
    for name, colour in ((f"t_a__until-{day(0)}.png", (240, 60, 160)),            # its last day is today: still shown
                         (f"t_b__top__until-{day(5)}.png", (60, 220, 230)),
                         (f"t_old__until-{day(-1)}.png", (90, 90, 90)),           # over since yesterday
                         ("t_bad__until-soon.png", (90, 90, 90)),                 # no date to read: never shown
                         (f"t_gone__once__until-{day(-1)}.png", (90, 90, 90)),    # a one-time banner whose date has passed
                         ("t_usual__center.png", (200, 180, 120))):
        Image.new("RGB", (920, 368), colour).save(os.path.join(press, name))
    ashita = os.path.join(work, "ashita")
    for name in ("servermenu", "XIUI"):
        os.makedirs(os.path.join(ashita, "addons", name))
        with open(os.path.join(ashita, "addons", name, name + ".lua"), "w") as f:
            f.write(f"addon.name = '{name}';\naddon.author = 'test';\naddon.version = '1.0';\naddon.desc = 'stand-in';\n")
    os.makedirs(os.path.join(ashita, "plugins"))
    os.makedirs(os.path.join(ashita, "config", "boot"))
    os.makedirs(os.path.join(ashita, "scripts"))
    with open(os.path.join(ashita, "config", "boot", "xiforever.ini"), "w") as f:
        f.write("[ashita.boot]\nscript      = xiforever.txt\n\n[ffxi.registry]\n0001 = 1920\n0002 = 1080\n")
    with open(os.path.join(ashita, "scripts", "xiforever.txt"), "w") as f:
        f.write("# Managed by the XI: Forever Offline launcher\n/load addons\n/wait 3\n/addon load servermenu\n")
    with open(os.path.join(kit, "config.example.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    seen = [n for n in os.listdir(press) if "__once" in n.lower() and "t_gone" not in n]       # the one-time banners are not this test's subject
    cfg.update({"ashita_dir": ashita, "ashita_boot": "xiforever.ini", "server_dir": os.path.join(work, "server"),
                "mariadb_dir": os.path.join(kit, "mariadb"), "banners_seen": seen})
    with open(os.path.join(kit, "config.json"), "w") as f:
        json.dump(cfg, f, indent=1)
    stubs = os.path.join(work, "stubs")
    os.makedirs(stubs)
    with open(os.path.join(stubs, "mariadb.py"), "w") as f:
        f.write("class Error(Exception):\n    pass\n\n\ndef connect(*a, **k):\n    raise Error('stand-in: no database in this test')\n")
    return work


def until_of(name):
    """The test's own reading of a file name: (is limited, last day or None)."""
    low = name.lower()
    if "__until-" not in low:
        return False, None
    text = low.split("__until-", 1)[1][:10]
    try:
        return True, datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        return True, None


def launch(work, step, out):
    kit = os.path.join(work, "kit")
    sys.path.insert(0, kit)
    sys.path.insert(0, os.path.join(work, "stubs"))
    os.chdir(kit)
    loader = importlib.machinery.SourceFileLoader("launcher_gui", os.path.join(kit, "launcher_gui.pyw"))
    spec = importlib.util.spec_from_loader("launcher_gui", loader)
    gui = importlib.util.module_from_spec(spec)
    sys.modules["launcher_gui"] = gui
    loader.exec_module(gui)
    for name in ("showerror", "showinfo", "showwarning"):
        setattr(gui.messagebox, name, lambda *a, **k: None)
    for name in ("askyesno", "askokcancel"):
        setattr(gui.messagebox, name, lambda *a, **k: False)
    fails = []

    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    press = os.path.join(kit, "assets", "press")
    files = sorted(n for n in os.listdir(press) if n.lower().endswith(PICS) and "__once" not in n.lower()
                   and "__theme-" not in n.lower())        # a theme's own banners (name__theme-8bit.png) are only shown while it is worn
    today = day(0) if step == "during" else "2099-01-01"
    if step == "after":
        gui.press_today = lambda: today
    in_date = [n for n in files if until_of(n)[1] and until_of(n)[1] >= today]
    usual = [n for n in files if not until_of(n)[0]]

    if step == "during":
        check(gui.press_today() == day(0), f"the launcher's day is today ({gui.press_today()})")
        check(gui.press_until("a__center.png") == "", "a usual picture has no last day")
        check(gui.press_until("a__until-2026-12-02.jpg") == "2026-12-02", "the last day is read from the name")
        check(gui.press_until("A__UNTIL-2026-12-02__top.PNG") == "2026-12-02", "... whatever the letter case and whatever follows it")
        check(gui.press_until("a__until-soon.png") == "0" and gui.press_until("a__until-2026-1-2.png") == "0", "an unreadable date counts as over")
        check(gui.press_anchor("a__top__until-2026-12-02.png") == 0.0 and gui.press_anchor("a__until-2026-12-02__bottom.jpg") == 1.0,
              "the __top / __bottom tags still work beside the date")
        check(gui.press_anchor("a__until-2026-12-02.jpg") == gui.PRESS_ANCHOR, "no tag: the usual part of the picture is kept")
        mixed = ["u1.png", "u2__center.jpg", "x__once.png", "notes.txt", f"l1__until-{day(0)}.png", f"l2__until-{day(3)}.jpg", f"l3__until-{day(-1)}.png"]
        check(gui.press_names(mixed) == [f"l1__until-{day(0)}.png", f"l2__until-{day(3)}.jpg"], "in date: only the limited-time pictures are shown")
        check(gui.press_names([n for n in mixed if not n.startswith(("l1", "l2"))]) == ["u1.png", "u2__center.jpg"],
              "all over: the usual pictures, and the old limited one is not among them")
        check(gui.press_names(["u1.png", "x__once.png"]) == ["u1.png"], "no limited-time pictures: the usual ones, as before")
        check(gui.press_names(mixed + ["t__center__theme-nobody.png"]) == [f"l1__until-{day(0)}.png", f"l2__until-{day(3)}.jpg"]
              and gui.press_names(["u1.png", "t__theme-nobody.png"]) == ["u1.png"], "a picture of a theme that is not worn is never shown")
        really_worn, gui.press_worn = gui.press_worn, lambda: "nobody"
        check(gui.press_names(mixed + ["t__center__theme-nobody.png", "s__theme-someone.png", f"old__theme-nobody__until-{day(-1)}.png"]) == ["t__center__theme-nobody.png"],
              "while its theme is worn, only that theme's pictures are shown (not another theme's, not one whose date has passed)")
        check(gui.press_names(mixed) == [f"l1__until-{day(0)}.png", f"l2__until-{day(3)}.jpg"], "a worn theme with no pictures of its own leaves the banners as they are")
        gui.press_worn = really_worn
        check(gui.load_once({"banners_seen": [n for n in os.listdir(press) if "__once" in n.lower() and "t_gone" not in n]}) == (None, None),
              "a one-time banner whose date has passed is not shown")

    app = gui.App()

    def settle(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def shot(name):
        if not out:
            return
        app.lift()
        app.update()
        x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", "+repage", os.path.join(out, name + ".png")], check=False)

    settle(1.5)
    heroes = [str(h) for h in app.heroes]
    showing = str(app.banner_label.cget("image"))
    if step == "during":
        check(len(in_date) >= 2, f"the copy holds limited-time pictures that are in date ({len(in_date)})")
        check(len(heroes) == len(in_date), f"only they are in the rotation: {len(heroes)} loaded, {len(in_date)} in date, {len(usual)} usual ones left out")
        check(app.once_banner is None and showing in heroes, "the Play page opens on one of them (the launcher picks at random)")
        check(set(heroes) <= {str(p) for p in app.pictures}, "they are among the loading pictures too")
        shot("limited-during")
        app.banner_label.event_generate("<Button-1>")
        settle(0.3)
        check(str(app.banner_label.cget("image")) == heroes[(heroes.index(showing) + 1) % len(heroes)], "a click goes to the next of them")
    else:
        check(len(heroes) == len(usual) and len(usual) >= 1, f"the day after: the usual banners are back ({len(heroes)} loaded, {len(usual)} usual files)")
        check(showing in heroes, "the Play page opens on a usual banner")
        shot("limited-after")
    app.destroy()
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--launch":
        launch(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
    if out:
        os.makedirs(out, exist_ok=True)
    work = make_copy()
    bad = 0
    try:
        for step in ("during", "after"):
            print(step)
            bad += subprocess.run([sys.executable, os.path.abspath(__file__), "--launch", work, step, out]).returncode != 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("ALL OK" if not bad else f"{bad} step(s) FAILED")
    sys.exit(1 if bad else 0)
