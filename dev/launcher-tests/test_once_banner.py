"""One-time banners (assets\\press\\name__once.png): shown on one start of the launcher, then never again.

Starts the real launcher three times from a COPY of the kit (stand-in config, database driver and addons folder; nothing
of the real install is read or changed) and checks what the Play page shows and what config.json remembers.
Needs python3-tk, Pillow and a screen:
    xvfb-run -a -s "-screen 0 1500x1000x24" python3 dev/launcher-tests/test_once_banner.py [OUTDIR for screenshots]"""
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
TAG = "__once"


def make_copy():
    work = tempfile.mkdtemp(prefix="xif-once-")
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
    if not any(TAG in n.lower() for n in os.listdir(press)):          # no one-time banner in the kit right now: a plain test one
        from PIL import Image
        Image.new("RGB", (920, 368), (230, 40, 150)).save(os.path.join(press, "test__once.png"))
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
    cfg.update({"ashita_dir": ashita, "ashita_boot": "xiforever.ini", "server_dir": os.path.join(work, "server"),
                "mariadb_dir": os.path.join(kit, "mariadb")})
    with open(os.path.join(kit, "config.json"), "w") as f:
        json.dump(cfg, f, indent=1)
    stubs = os.path.join(work, "stubs")
    os.makedirs(stubs)
    with open(os.path.join(stubs, "mariadb.py"), "w") as f:
        f.write("class Error(Exception):\n    pass\n\n\ndef connect(*a, **k):\n    raise Error('stand-in: no database in this test')\n")
    return work


def seen(kit):
    with open(os.path.join(kit, "config.json"), encoding="utf-8-sig") as f:
        return json.load(f).get("banners_seen")


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
    press = os.path.join(kit, "assets", "press")
    once_files = sorted(n for n in os.listdir(press) if TAG in n.lower())
    usual = [n for n in os.listdir(press) if TAG not in n.lower() and n.lower().endswith((".png", ".jpg", ".jpeg"))]
    if hasattr(gui, "press_names"):              # limited-time banners (__until-DATE) may stand in for the usual ones today
        usual = gui.press_names(os.listdir(press))
    app = gui.App()
    fails = []

    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

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

    showing = lambda: str(app.banner_label.cget("image"))
    heroes = [str(h) for h in app.heroes]
    settle(1.5)
    if step == "first":
        check(app.once_banner is not None, "first start: there is a one-time banner")
        check(showing() == str(app.once_banner), "first start: the Play page shows it")
        check(len(app.heroes) == len(usual), f"it is not in the rotation ({len(app.heroes)} banners loaded, {len(usual)} files in the rotation today)")
        check(str(app.once_banner) not in [str(p) for p in app.pictures], "it is not among the loading pictures")
        check(not seen(kit), "not marked as shown in the first second")
        shot("once-first-start")
        settle(4.0)
        check(seen(kit) == [once_files[0]], f"after a few seconds config.json remembers it: {seen(kit)}")
        for _ in range(6):                       # the rotation's own timer, six turns (36 seconds' worth)
            app.next_picture(manual=True)
            app.hero_ticks += 1
            if not app.running and not app.showing_details and len(app.heroes) > 1 and app.once_banner is None and app.hero_ticks % 2 == 0:
                app.next_hero()
        check(showing() == str(app.once_banner), "it stays up while the launcher is open")
        app.banner_label.event_generate("<Button-1>")
        settle(0.3)
        check(app.once_banner is None and showing() in heroes, "a click puts the usual banners back")
        before = showing()
        app.banner_label.event_generate("<Button-1>")
        settle(0.3)
        check(len(heroes) < 2 or showing() != before and showing() in heroes, "the next click moves through the usual banners")
        check(seen(kit) == [once_files[0]], "config.json lists it once, not twice")
    elif step == "second":
        check(app.once_banner is None, "second start: no one-time banner")
        check(showing() in heroes, "second start: the Play page shows a usual banner")
        shot("once-second-start")
        settle(4.5)
        check(seen(kit) == [once_files[0]], "config.json unchanged")
    elif step == "quick":
        check(app.once_banner is not None and showing() == str(app.once_banner), "banner up again after config.json forgot it")
        check(not seen(kit), "closed within a second or two: not marked, so it shows on the next start")
    elif step == "clicked":
        check(app.once_banner is not None, "one-time banner up")
        app.banner_label.event_generate("<Button-1>")
        settle(0.3)
        check(seen(kit) == [once_files[0]], "clicked away before the few seconds were up: marked as shown")
        settle(4.5)
        check(seen(kit) == [once_files[0]], "and still listed once after the timer")
    app.destroy()
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--launch":
        launch(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
    if out:
        os.makedirs(out, exist_ok=True)
    work = make_copy()
    kit = os.path.join(work, "kit")
    bad = 0
    try:
        for step in ("first", "second", "quick", "clicked"):
            if step in ("quick", "clicked"):     # config.json forgets, as on an install that has not seen it yet
                with open(os.path.join(kit, "config.json"), encoding="utf-8-sig") as f:
                    cfg = json.load(f)
                cfg.pop("banners_seen", None)
                with open(os.path.join(kit, "config.json"), "w") as f:
                    json.dump(cfg, f, indent=1)
            print(step)
            bad += subprocess.run([sys.executable, os.path.abspath(__file__), "--launch", work, step, out]).returncode != 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("ALL OK" if not bad else f"{bad} step(s) FAILED")
    sys.exit(1 if bad else 0)
