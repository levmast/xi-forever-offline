"""Screenshots of every launcher page, and checks on the whole window, from a COPY of the kit with a stand-in
config, a stand-in database driver and a stand-in addons folder. Nothing of the real install is read or changed:
the copy is made in a temporary folder first.

For a Linux machine without the game (this is how the pages were looked at while the newer look was built):
needs python3-tk, Pillow, Xvfb and ImageMagick's "import".
    xvfb-run -a -s "-screen 0 1500x1000x24" python3 dev/launcher-tests/render_pages.py OUTDIR [player] [classic] [windows] [broken] [checks]
player  = as a player install sees it      classic = "classic_ui": true      checks = also run render_checks.py
windows = the pages Windows makes (the Shaders page, no Linux part)       broken = the newer pages fail: the classic ones must open
contributor = a signed-in team member's install (use with player)
Fonts and spacing differ a little from Windows, so the last look is always on Windows itself."""
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
HERE_TESTS = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) < 2:
    sys.exit(__doc__)
out = os.path.abspath(sys.argv[1])
flags = sys.argv[2:]
player, classic, checks = "player" in flags, "classic" in flags, "checks" in flags
os.makedirs(out, exist_ok=True)

# ---- the copy: launcher code, its art and its data files, never config.json ----
work = tempfile.mkdtemp(prefix="xif-render-")
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
ashita = os.path.join(work, "ashita")
for name, author, version, about in (("servermenu", "XI: Forever Offline", "1.25", "The XI: Forever Offline menu."),
                                     ("Gambits", "XI: Forever Offline", "0.2.0", "Rule Sets for your squad mates."),
                                     ("XIUI", "Team XIUI", "1.8.4", "Party list, target bar, cast bar and more."),
                                     ("minimap", "atom0s", "1.1", "Shows a minimap."), ("fps", "atom0s", "1.0", "Shows the frame rate.")):
    os.makedirs(os.path.join(ashita, "addons", name))
    with open(os.path.join(ashita, "addons", name, name + ".lua"), "w") as f:
        f.write(f"addon.name = '{name}';\naddon.author = '{author}';\naddon.version = '{version}';\naddon.desc = '{about}';\n")
os.makedirs(os.path.join(ashita, "plugins"))
for name in ("addons", "thirdparty", "screenshot", "XIUIplus"):
    open(os.path.join(ashita, "plugins", name + ".dll"), "wb").close()
os.makedirs(os.path.join(ashita, "config", "boot"))
os.makedirs(os.path.join(ashita, "scripts"))
with open(os.path.join(ashita, "config", "boot", "xiforever.ini"), "w") as f:
    f.write("[ashita.boot]\nscript      = xiforever.txt\n\n[ffxi.registry]\n0001 = 1920\n0002 = 1080\n")
with open(os.path.join(ashita, "scripts", "xiforever.txt"), "w") as f:
    f.write("# Managed by the XI: Forever Offline launcher\n/load addons\n/wait 3\n/addon load servermenu\n/addon load XIUI\n")
with open(os.path.join(kit, "config.example.json"), encoding="utf-8-sig") as f:
    cfg = json.load(f)
cfg.update({"ashita_dir": ashita, "ashita_boot": "xiforever.ini", "server_dir": os.path.join(work, "server")})
if player:
    cfg["mariadb_dir"] = os.path.join(kit, "mariadb")
if classic:
    cfg["classic_ui"] = True
if os.environ.get("XIF_RENDER_THEME"):       # look at the pages in one theme, e.g. XIF_RENDER_THEME=aero
    cfg["theme"] = os.environ["XIF_RENDER_THEME"]
    _events = sorted(n[:-5] for n in os.listdir(os.path.join(KIT, "assets", "press")) if n.endswith(".json") and "__until-" in n)
    if _events:                             # picked while today's limited-time theme was in date, so the pick holds
        cfg["theme_event"] = _events[-1]
if "contributor" in flags:                  # a team member's install: signed in, may send Rule Sets
    cfg.update({"contributor": "tester", "contributor_areas": ["gambits"]})
with open(os.path.join(kit, "config.json"), "w") as f:
    json.dump(cfg, f, indent=1)
stubs = os.path.join(work, "stubs")
os.makedirs(stubs)
with open(os.path.join(stubs, "mariadb.py"), "w") as f:
    f.write("class Error(Exception):\n    pass\n\n\ndef connect(*a, **k):\n    raise Error('stand-in: no database in this preview')\n")
sys.path.insert(0, kit)
sys.path.insert(0, stubs)
os.chdir(kit)
loader = importlib.machinery.SourceFileLoader("launcher_gui", os.path.join(kit, "launcher_gui.pyw"))
spec = importlib.util.spec_from_loader("launcher_gui", loader)
gui = importlib.util.module_from_spec(spec)
sys.modules["launcher_gui"] = gui
loader.exec_module(gui)
for _name in ("showerror", "showinfo", "showwarning"):
    setattr(gui.messagebox, _name, lambda *a, **k: print("[box]", *[str(x)[:160] for x in a]))
for _name in ("askyesno", "askokcancel"):
    setattr(gui.messagebox, _name, lambda *a, **k: (print("[ask]", *[str(x)[:160] for x in a]), True)[1])

if "windows" in flags:                      # best effort: the pages Windows makes (Shaders, no Linux part), still drawn by this Linux
    gui.IS_WINDOWS, gui.linux = True, None
    gui.linux_look = lambda root: root.option_add("*highlightThickness", 0)
if "broken" in flags:                       # the newer pages fail while being made (the Rules page, after World is in): the launcher must still open
    def _broken(self, *a, **k):
        raise RuntimeError("broken on purpose")
    sys.modules["launcher_pages"].RulesPage.build_top = _broken
app = gui.App()
prefix = (os.environ.get("XIF_RENDER_THEME", "") + ("-" if os.environ.get("XIF_RENDER_THEME") else "") + ("player-" if player else "dev-") + ("classic-" if classic else "") + ("windows-" if "windows" in flags else "")
          + ("contributor-" if "contributor" in flags else ""))


def settle(seconds=0.5):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def shot(name):
    settle()
    app.lift()
    app.update()
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", "+repage", os.path.join(out, prefix + name + ".png")], check=False)
    return w, h


settle(1.5)
newer = bool(getattr(app, "new_ui", False))
print("new_ui:", newer, "pages:", list(app.page_index))
if "broken" in flags:
    left = [name for name in ("World", "Rules") if name in app.page_index]
    print("broken on purpose:", "the classic pages opened, as they should" if not newer and "Rates" in app.page_index and not left
          else f"PROBLEM: no clean fallback (left over: {left})")
for name, index in app.page_index.items():
    app.select_tab(index)
    size = shot(name.lower().replace(" ", "-"))
    page = app.nametowidget(app.tabs.tabs()[index])
    need = page.body.winfo_reqheight() + 2 * page.pad[1] if hasattr(page, "pad") else page.winfo_reqheight()
    print(f"{name:10} window {size[0]}x{size[1]}  page area {page.winfo_width()}x{page.winfo_height()}  needs {need}")

pages_mod = sys.modules.get("launcher_pages")
if checks:
    exec(open(os.path.join(HERE_TESTS, "render_checks.py"), encoding="utf-8").read())
app.destroy()
shutil.rmtree(work, ignore_errors=True)
