"""Logic for the XI: Forever Offline launcher (no GUI code here, so it can be tested on its own)."""
import json, os, re, shutil, subprocess, sys

# XIFO_TEST_PLATFORM=windows: the stand-in tests check the Windows paths on a Linux machine
IS_WINDOWS = os.name == "nt" or os.environ.get("XIFO_TEST_PLATFORM") == "windows"
IS_LINUX = sys.platform.startswith("linux") and not IS_WINDOWS
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0    # Windows: start a process without a console window (0 elsewhere: Popen refuses it)
SERVERS = ["xi_connect", "xi_world", "xi_search", "xi_profile", "xi_map"]
MANAGED_SCRIPT = "xiforever.txt"          # the Ashita script the launcher owns on a new install
OLD_MANAGED_SCRIPT = "phoenixsolo.txt"    # the same script on installs made before the rename (kept as it is)
DEFAULT_BOOT = "xiforever.ini"            # boot file name for a new install; config.json's ashita_boot wins
# Packaged as "XI Forever Offline.exe" (PyInstaller) the kit folder is where the exe is, not where Python unpacked itself.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:   # programs we start from the exe (helpers, the restarted launcher) are new instances, not onefile children:
    os.environ["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # else "invalid originating onefile parent process" once we exit
KIT_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
if FROZEN and IS_LINUX:   # programs we start must not see the packaged launcher's own libraries (LD_LIBRARY_PATH)
    import launcher_linux as _linux
    _linux.fix_frozen_environment()


def ui_fonts():
    """(text font, fixed-width font) for the launcher's windows: Windows' own, else the best one this Linux has
    (Tk would otherwise pick something odd for the missing Segoe UI)."""
    if IS_WINDOWS:
        return "Segoe UI", "Consolas"
    families = set()
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            families.update(part.strip() for part in line.split(","))
    except (OSError, subprocess.SubprocessError):
        pass
    text = next((f for f in ("Noto Sans", "Cantarell", "DejaVu Sans", "Liberation Sans", "Ubuntu") if f in families), "Helvetica")
    mono = next((f for f in ("Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono", "Hack") if f in families), "Courier")
    return text, mono


def exe_name(name):
    """A program's file name on this system: xi_map.exe on Windows, xi_map on Linux."""
    return name + ".exe" if IS_WINDOWS else name


def py_cmd(script, *args, unbuffered=False):
    """The command that runs one of the kit's Python scripts (a sidecar or a tool): python script.py ... from source,
    or the launcher exe itself (XI Forever Offline.exe --run script.py ...) when packaged, so players need no Python."""
    if FROZEN:
        return [sys.executable, "--run", script] + list(args)
    return [sys.executable] + (["-u"] if unbuffered else []) + [script] + list(args)


def run_script_main(argv):
    """The exe's --run mode: runs a kit script as if it were started with python. argv = [script, args...]."""
    import runpy
    script = os.path.abspath(argv[0])
    for name, fd in (("stdout", 1), ("stderr", 2)):          # a windowed exe starts without them; use the handles the launcher gave
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, "w", buffering=1, encoding="utf-8", errors="replace", closefd=False))
            except OSError:
                setattr(sys, name, open(os.devnull, "w"))
    sys.argv = [script] + list(argv[1:])
    sys.path.insert(0, os.path.dirname(script))             # its neighbours import each other (crowd_chat_ai, bots_chat_ai)
    sys.path.insert(1, KIT_DIR)                              # and the launcher's own modules (setup_gm imports launcher_core)
    runpy.run_path(script, run_name="__main__")


def managed_script_name(ashita_dir):
    """phoenixsolo.txt if this Ashita already has it (an install from before the rename), else xiforever.txt."""
    if ashita_dir and os.path.exists(os.path.join(ashita_dir, "scripts", OLD_MANAGED_SCRIPT)):
        return OLD_MANAGED_SCRIPT
    return MANAGED_SCRIPT

ADDON_RE  = re.compile(r"^\s*/addon\s+load\s+(\S+)\s*$", re.I)
PLUGIN_RE = re.compile(r"^\s*/load\s+(\S+)\s*$", re.I)


def load_config(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# ---------- processes (Windows; Linux through launcher_linux, which reads /proc) ----------
def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)

def is_running(image_name):
    if not IS_WINDOWS:
        import launcher_linux
        return bool(launcher_linux.pids_named(image_name))
    out = _run(["tasklist", "/FI", f"IMAGENAME eq {image_name}.exe", "/NH"]).stdout.lower()
    return f"{image_name.lower()}.exe" in out

def count_running(image_name):
    """How many copies of a program are running (two game windows = two xiloader)."""
    if not IS_WINDOWS:
        import launcher_linux
        return len(launcher_linux.pids_named(image_name))
    out = _run(["tasklist", "/FI", f"IMAGENAME eq {image_name}.exe", "/NH"]).stdout.lower()
    return out.count(f"{image_name.lower()}.exe")

def kill(image_name):
    if not IS_WINDOWS:
        import launcher_linux
        launcher_linux.stop_pids(launcher_linux.pids_named(image_name), grace=2.0)
        return
    _run(["taskkill", "/F", "/IM", f"{image_name}.exe"])

def kill_tree(proc):
    """Stops a process we started and everything it started. The packaged launcher runs its helpers (squad chat,
    auction house, crowd chat AI) as 'XI Forever Offline.exe --run ...', and a one-file exe is two processes: a
    starter and the real one. terminate() only ended the starter, so the real helpers kept running after the
    launcher closed (Yumainai, Careb)."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
    except Exception:
        return
    if os.name == "nt":
        _run(["taskkill", "/PID", str(proc.pid), "/T", "/F"])
    elif IS_LINUX:
        import launcher_linux
        launcher_linux.kill_tree(proc.pid)
    try:
        if proc.poll() is None:
            proc.terminate()
    except Exception:
        pass


def kill_stray_helpers():
    """At PLAY: helpers an earlier launcher left running (packaged exe with --run), except the game-copy helper,
    which puts PlayOnline's settings back when the game closes."""
    if IS_LINUX:
        import launcher_linux
        exe = os.path.basename(sys.executable) if FROZEN else ""
        launcher_linux.stop_pids(launcher_linux.pids_where(
            lambda argv: bool(exe) and len(argv) > 1 and os.path.basename(argv[0]) == exe and "--run" in argv
            and not any("launcher_game" in a for a in argv)))
        return
    if os.name != "nt":
        return
    script = ("Get-CimInstance Win32_Process -Filter \"name LIKE 'XI%Forever%Offline%.exe'\" | "
              "Where-Object { $_.ProcessId -ne %d -and $_.CommandLine -like '*--run*' -and $_.CommandLine -notlike '*launcher_game*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }").replace("%d", str(os.getpid()))
    _run(["powershell", "-NoProfile", "-Command", script])


def kill_squad_chat():
    """Stop a squad-chat sidecar left over from an earlier run (two of them would both answer every line)."""
    if not IS_WINDOWS:
        import launcher_linux
        launcher_linux.stop_pids(launcher_linux.pids_where(lambda argv: any(a.endswith("squad_chat.py") for a in argv)))
        return
    script = ("Get-CimInstance Win32_Process -Filter \"name='pythonw.exe' OR name='python.exe' OR name LIKE 'XI_Forever_Offline.exe'\" | "
              "Where-Object { $_.CommandLine -like '*squad_chat.py*' } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    _run(["powershell", "-NoProfile", "-Command", script])

def ensure_service(name):
    if not IS_WINDOWS:          # Linux installs always use the kit's own MariaDB (config.json mariadb_dir)
        return False
    out = _run(["sc", "query", name]).stdout
    if "RUNNING" in out:
        return True
    if "does not exist" in out or "1060" in out:
        return False
    _run(["net", "start", name])
    return "RUNNING" in _run(["sc", "query", name]).stdout


# ---------- servers ----------
def start_server(cfg, name, logs_dir):
    exe = os.path.join(cfg["server_dir"], exe_name(name))
    if not os.path.exists(exe):
        raise FileNotFoundError(f"Missing {exe} - did the build finish?")
    os.makedirs(logs_dir, exist_ok=True)
    log = open(os.path.join(logs_dir, name + ".log"), "wb")
    # stdin stays open (PIPE) so the server's console reader does not see end-of-file and quit
    p = subprocess.Popen([exe], cwd=cfg["server_dir"], stdin=subprocess.PIPE,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
                         **({} if IS_WINDOWS else {"start_new_session": True}))
    return p, log

def map_ready(logs_dir):
    try:
        with open(os.path.join(logs_dir, "xi_map.log"), "rb") as f:
            return "ready to work" in f.read().decode("utf-8", "ignore")
    except OSError:
        return False

def map_ready_from(logs_dir, offset):
    """(ready, new offset). Looks only at what the map log gained since 'offset', so a big log is not read again every second."""
    path = os.path.join(logs_dir, "xi_map.log")
    try:
        size = os.path.getsize(path)
        if size < offset:                       # the log was started afresh
            offset = 0
        with open(path, "rb") as f:
            f.seek(max(0, offset - 20))         # a little overlap, in case the phrase was split between two reads
            data = f.read()
            return b"ready to work" in data, f.tell()
    except OSError:
        return False, offset

def log_size(logs_dir, name):
    try:
        return os.path.getsize(os.path.join(logs_dir, name + ".log"))
    except OSError:
        return 0

def tail(path, lines=12):
    try:
        with open(path, "rb") as f:
            data = f.read().decode("utf-8", "ignore")
        data = re.sub(r"\x1b\[[0-9;]*m", "", data)
        return "\n".join(data.strip().splitlines()[-lines:])
    except OSError:
        return ""


# ---------- Ashita ----------
def sync_loader(cfg):
    """Keep a copy of the built xiloader inside Ashita's bootloader folder (where Ashita expects it)."""
    built = None
    for root, _dirs, files in os.walk(cfg.get("xiloader_dir") or ""):
        if "xiloader.exe" in files:
            built = os.path.join(root, "xiloader.exe")
            break
    dest = os.path.join(cfg["ashita_dir"], "bootloader", "xiloader.exe")
    if built and (not os.path.exists(dest) or os.path.getmtime(built) > os.path.getmtime(dest)):
        shutil.copy2(built, dest)
        return True
    return False

def list_addons(ashita_dir):
    d = os.path.join(ashita_dir, "addons")
    out = []
    if os.path.isdir(d):
        for name in sorted(os.listdir(d), key=str.lower):
            sub = os.path.join(d, name)
            if os.path.isdir(sub) and any(f.lower() == name.lower() + ".lua" for f in os.listdir(sub)):
                out.append(name)
    return out

def list_plugins(ashita_dir):
    d = os.path.join(ashita_dir, "plugins")
    out = []
    if os.path.isdir(d):
        for f in sorted(os.listdir(d), key=str.lower):
            if f.lower().endswith(".dll"):
                out.append(f[:-4])
    return out


# ---------- what an addon or plugin is (for the Addons page) ----------
OWN_ADDONS = {"gambits", "autobox", "followme", "servermenu", "squadpanel", "crystalboy"}
PLUGIN_NOTES = {"addons": "Runs Lua addons (keep this on).", "thirdparty": "Lets third-party plugins load.",
                "screenshot": "Screenshots without the interface.", "minimap": "A minimap on screen.",
                "hardwaremouse": "Hardware mouse cursor.", "toon": "Cel-shaded look.", "winefix": "Fixes for Wine (Linux).",
                "xiuiplus": "XIUIplus: the party list, target bar and other windows (alpha).",
                "nameplate": "Clearer name plates.", "movement": "Movement helper used by AutoBot."}


def addon_info(ashita_dir, name):
    """name, version, author and description from the addon's own lua file (addon.version = '...' and so on)."""
    info = {"name": name, "version": "", "author": "", "desc": ""}
    path = os.path.join(ashita_dir, "addons", name, name + ".lua")
    if not os.path.exists(path):
        folder = os.path.join(ashita_dir, "addons", name)
        hits = [f for f in os.listdir(folder) if f.lower() == name.lower() + ".lua"] if os.path.isdir(folder) else []
        path = os.path.join(folder, hits[0]) if hits else path
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = handle.read(30000)
    except OSError:
        return info
    for key, field in (("version", "version"), ("author", "author"), ("desc", "desc")):
        found = re.search(r"addon\.%s\s*=\s*(['\"])(.*?)\1" % field, head)
        if found:
            info[key] = found.group(2).strip()
    return info


def item_origin(kind, name, thirdparty_ids=(), added=()):
    """Where it comes from, for the Addons page: ours, a third-party download, one the player added, or Ashita's own."""
    low = name.lower()
    if kind == "addon" and low in OWN_ADDONS:
        return "XI: Forever Offline"
    if low in {t.lower() for t in added}:
        return "added by you"
    if low in {t.lower() for t in thirdparty_ids}:
        return "download"
    return "Ashita"


def added_items(kit_dir):
    """Names the player added with 'Add addon or plugin' (kept in added-addons.json in the kit folder)."""
    try:
        with open(os.path.join(kit_dir, "added-addons.json"), encoding="utf-8") as handle:
            return set(json.load(handle))
    except (OSError, ValueError):
        return set()


def remember_added(kit_dir, names):
    have = added_items(kit_dir) | set(names)
    with open(os.path.join(kit_dir, "added-addons.json"), "w", encoding="utf-8") as handle:
        json.dump(sorted(have), handle, indent=1)


def _backup(path, backups, name):
    stamp = __import__("time").strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(backups, f"{name}-{stamp}")
    os.makedirs(backups, exist_ok=True)
    if os.path.isdir(path):
        shutil.copytree(path, dest)
    else:
        shutil.copy2(path, dest + os.path.splitext(path)[1])
    return dest


def install_user_item(ashita_dir, source, backups):
    """Adds an addon or plugin the player chose: a plugin .dll, an addon folder (with <name>.lua in it), or a .zip holding
    either (also the usual 'addons/<name>/...' and 'plugins/x.dll' layouts, under one top folder or not). Anything it
    replaces is copied to backups first. Returns [(kind, name)] of what was installed."""
    import tempfile
    import zipfile
    installed = []
    work = None
    try:
        if source.lower().endswith(".zip"):
            work = tempfile.mkdtemp(prefix="xifo-addon-")
            with zipfile.ZipFile(source) as archive:
                for info in archive.infolist():
                    parts = info.filename.replace("\\", "/").split("/")
                    if ".." in parts or info.filename.startswith(("/", "\\")) or ":" in info.filename:
                        raise RuntimeError("That zip has a file outside its own folders - not installed.")
                archive.extractall(work)
            root = work
            entries = [e for e in os.listdir(root) if not e.startswith((".", "__MACOSX"))]
            if len(entries) == 1 and os.path.isdir(os.path.join(root, entries[0])) and not _is_addon(os.path.join(root, entries[0])):
                root = os.path.join(root, entries[0])          # one top folder around everything (a GitHub "main" zip)
            candidates = [root]
        else:
            candidates = [source]
        for base in candidates:
            if os.path.isfile(base) and base.lower().endswith(".dll"):
                installed.append(_put(ashita_dir, "plugin", base, backups))
                continue
            if _is_addon(base):
                installed.append(_put(ashita_dir, "addon", base, backups))
                continue
            for folder, kind in (("addons", "addon"), ("plugins", "plugin")):
                sub = os.path.join(base, folder)
                if not os.path.isdir(sub):
                    continue
                for entry in sorted(os.listdir(sub)):
                    path = os.path.join(sub, entry)
                    if kind == "addon" and _is_addon(path):
                        installed.append(_put(ashita_dir, "addon", path, backups))
                    elif kind == "plugin" and entry.lower().endswith(".dll"):
                        installed.append(_put(ashita_dir, "plugin", path, backups))
            if not installed and os.path.isdir(base):     # loose: addon folders or dlls straight inside
                for entry in sorted(os.listdir(base)):
                    path = os.path.join(base, entry)
                    if _is_addon(path):
                        installed.append(_put(ashita_dir, "addon", path, backups))
                    elif entry.lower().endswith(".dll"):
                        installed.append(_put(ashita_dir, "plugin", path, backups))
    finally:
        if work:
            shutil.rmtree(work, ignore_errors=True)
    if not installed:
        raise RuntimeError("No addon (a folder with <name>.lua in it) or plugin (.dll) was found there.")
    return installed


def _is_addon(path):
    name = os.path.basename(path.rstrip("/\\"))
    return os.path.isdir(path) and any(f.lower() == name.lower() + ".lua" for f in os.listdir(path))


def _put(ashita_dir, kind, path, backups):
    name = os.path.basename(path.rstrip("/\\"))
    if kind == "addon":
        dest = os.path.join(ashita_dir, "addons", name)
        if os.path.exists(dest):
            _backup(dest, backups, "addon-" + name)
        shutil.copytree(path, dest, dirs_exist_ok=True)
        return ("addon", name)
    dest = os.path.join(ashita_dir, "plugins", name)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        _backup(dest, backups, "plugin-" + name[:-4])
    shutil.copy2(path, dest)
    return ("plugin", name[:-4])


class ScriptManager:
    """Owns scripts\\xiforever.txt (phoenixsolo.txt on older installs). The first time, it copies your boot script into it and points the
    boot .ini at it; after that, toggling an addon adds/removes its '/addon load' line."""

    def __init__(self, ashita_dir, boot_name, script_name=None):
        """script_name: the script this manager owns. The main window uses xiforever.txt (or phoenixsolo.txt); the second window (dualbox) uses dualbox.txt."""
        self.ashita = ashita_dir
        script_name = script_name or managed_script_name(ashita_dir)
        self.script_name = script_name
        self.boot_path = os.path.join(ashita_dir, "config", "boot", boot_name)
        self.scripts = os.path.join(ashita_dir, "scripts")
        self.path = os.path.join(self.scripts, script_name)

    def prepare(self):
        if not os.path.exists(self.boot_path):
            raise FileNotFoundError(f"Boot file not found: {self.boot_path}")
        with open(self.boot_path, "r", encoding="utf-8-sig") as f:
            ini = f.read()
        m = re.search(r"(?mi)^script\s*=\s*(.*?)\s*$", ini)
        current = m.group(1) if m else "default.txt"
        os.makedirs(self.scripts, exist_ok=True)
        if not os.path.exists(self.path):
            src = os.path.join(self.scripts, current)
            if current != self.script_name and os.path.exists(src):
                shutil.copy2(src, self.path)
            else:
                with open(self.path, "w", encoding="utf-8", newline="\r\n") as f:
                    f.write("# Managed by the XI: Forever Offline launcher\n")
        if current != self.script_name:
            bak = self.boot_path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(self.boot_path, bak)
            if m:
                ini = re.sub(r"(?mi)^script\s*=.*$", f"script      = {self.script_name}", ini, count=1)
            else:
                ini = ini.replace("[ashita.boot]", f"[ashita.boot]\nscript      = {self.script_name}", 1)
            with open(self.boot_path, "w", encoding="utf-8", newline="") as f:
                f.write(ini)

    def _lines(self):
        with open(self.path, "r", encoding="utf-8-sig") as f:
            return f.read().splitlines()

    def _write(self, lines):
        with open(self.path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(lines).rstrip("\n") + "\n")

    @staticmethod
    def _regex(kind):
        return ADDON_RE if kind == "addon" else PLUGIN_RE

    def enabled(self, kind):
        rx = self._regex(kind)
        names = set()
        for line in self._lines():
            if line.lstrip().startswith("#"):
                continue
            m = rx.match(line)
            if m:
                names.add(m.group(1).lower())
        return names

    def set(self, kind, name, on):
        rx = self._regex(kind)
        lines = self._lines()
        kept = []
        for line in lines:
            m = rx.match(line)
            if m and not line.lstrip().startswith("#") and m.group(1).lower() == name.lower():
                continue
            kept.append(line)
        if on:
            kept.append(f"/addon load {name}" if kind == "addon" else f"/load {name}")
        self._write(kept)


# ---------- rates (written into the server's settings before every launch) ----------
# Each field: id, settings file, key, label, default, min, max, kind ("float" or "int")
RATE_FIELDS = [
    ("map.EXP_RATE",                    "map.lua",  "EXP_RATE",                    "Experience from monsters",              1.0, 0.0, 100.0, "float"),
    ("main.EXP_RATE",                   "main.lua", "EXP_RATE",                    "Experience from quests and scripts",    1.0, 0.0, 100.0, "float"),
    ("main.BOOK_EXP_RATE",              "main.lua", "BOOK_EXP_RATE",               "Experience from Fields/Grounds pages",  0.125, 0.0, 100.0, "float"),
    ("main.ROE_EXP_RATE",               "main.lua", "ROE_EXP_RATE",                "Experience from Records of Eminence",   1.0, 0.0, 100.0, "float"),
    ("map.CAPACITY_RATE",               "map.lua",  "CAPACITY_RATE",               "Capacity points",                       1.0, 0.0, 100.0, "float"),
    ("map.EXP_LOSS_RATE",               "map.lua",  "EXP_LOSS_RATE",               "Experience lost on death (0 = none)",   1.0, 0.0, 10.0,  "float"),
    ("map.DROP_RATE_MULTIPLIER",        "map.lua",  "DROP_RATE_MULTIPLIER",        "Monster item drop rate",                1.0, 0.0, 100.0, "float"),
    ("map.MOB_GIL_MULTIPLIER",          "map.lua",  "MOB_GIL_MULTIPLIER",          "Gil dropped by monsters",               1.0, 0.0, 100.0, "float"),
    ("main.GIL_RATE",                   "main.lua", "GIL_RATE",                    "Gil from quests",                       1.0, 0.0, 100.0, "float"),
    ("main.AH_PRICE_RATE",              "main.lua", "AH_PRICE_RATE",               "Auction house prices (1 = as they are)", 1.0, 0.1, 10.0, "float"),
    ("main.FAME_RATE",                  "main.lua", "FAME_RATE",                   "Fame from quests (1 = retail)",         1.0, 0.1, 20.0, "float"),
    # (2026-11-20) lottery NMs (Leaping Lizzy, Valkurm Emperor...): the server reads these since v0.1.49 (spawn_slot.cpp).
    # Chance: a multiplier on each NM's own chance; any negative value = the NM always comes next. 0 counts as 1%.
    # Wait: a multiplier on the time after a kill before the NM can be rolled again; 0 = none.
    ("main.NM_LOTTERY_CHANCE",          "main.lua", "NM_LOTTERY_CHANCE",           "Lottery NM spawn chance (1 = retail, -1 = always)", 1.0, -1.0, 100.0, "float"),
    ("main.NM_LOTTERY_COOLDOWN",        "main.lua", "NM_LOTTERY_COOLDOWN",         "Lottery NM wait after a kill (1 = retail, 0 = none)", 1.0, 0.0, 10.0, "float"),
    ("main.TABS_RATE",                  "main.lua", "TABS_RATE",                   "Tabs from Fields of Valor",             1.0, 0.0, 100.0, "float"),
    ("main.SPARKS_RATE",                "main.lua", "SPARKS_RATE",                 "Sparks from Records of Eminence",       1.0, 0.0, 100.0, "float"),
    ("main.CASKET_DROP_RATE",           "main.lua", "CASKET_DROP_RATE",            "Treasure casket chance (0.1 = 10%)",    0.1, 0.0, 1.0,   "float"),
    ("map.SKILLUP_CHANCE_MULTIPLIER",   "map.lua",  "SKILLUP_CHANCE_MULTIPLIER",   "Combat and magic skill-up chance",      1.0, 0.0, 20.0,  "float"),
    ("map.BLUE_LEARN_MULTIPLIER",       "map.lua",  "BLUE_LEARN_MULTIPLIER",       "Blue magic learning chance",            1.0, 0.0, 3.0,   "float"),
    ("map.CRAFT_CHANCE_MULTIPLIER",     "map.lua",  "CRAFT_CHANCE_MULTIPLIER",     "Crafting skill-up chance",              1.0, 0.0, 20.0,  "float"),
    ("map.CRAFT_HQ_CHANCE_MULTIPLIER",  "map.lua",  "CRAFT_HQ_CHANCE_MULTIPLIER",  "Crafting high-quality chance",          1.0, 0.0, 20.0,  "float"),
    ("map.FISHING_SKILL_MULTIPLIER",    "map.lua",  "FISHING_SKILL_MULTIPLIER",    "Fishing skill-up chance",               1.0, 0.0, 20.0,  "float"),
    ("main.MAX_LEVEL",                  "main.lua", "MAX_LEVEL",                   "Level cap",                             75,  50,  99,    "int"),
    ("main.ENABLE_COP",                 "main.lua", "ENABLE_COP",                  "Chains of Promathia (1 = on)",          1,   0,   1,     "int"),
    ("main.ENABLE_TOAU",                "main.lua", "ENABLE_TOAU",                 "Treasures of Aht Urhgan (1 = on)",      1,   0,   1,     "int"),
    ("main.ENABLE_WOTG",                "main.lua", "ENABLE_WOTG",                 "Wings of the Goddess (1 = on)",         0,   0,   1,     "int"),
    ("main.ENABLE_ACP",                 "main.lua", "ENABLE_ACP",                  "A Crystalline Prophecy (1 = on)",       0,   0,   1,     "int"),
    ("main.ENABLE_AMK",                 "main.lua", "ENABLE_AMK",                  "A Moogle Kupo d'Etat (1 = on)",         0,   0,   1,     "int"),
    ("main.ENABLE_ASA",                 "main.lua", "ENABLE_ASA",                  "A Shantotto Ascension (1 = on)",        0,   0,   1,     "int"),
    ("main.ENABLE_ABYSSEA",             "main.lua", "ENABLE_ABYSSEA",              "Abyssea (1 = on)",                      0,   0,   1,     "int"),
    ("main.ENABLE_SOA",                 "main.lua", "ENABLE_SOA",                  "Seekers of Adoulin (1 = on)",           0,   0,   1,     "int"),
    ("main.ENABLE_ROV",                 "main.lua", "ENABLE_ROV",                  "Rhapsodies of Vana'diel (1 = on)",      0,   0,   1,     "int"),
    ("main.ENABLE_VOIDWATCH",           "main.lua", "ENABLE_VOIDWATCH",            "Voidwatch NPCs (1 = on)",               0,   0,   1,     "int"),
    ("main.ENABLE_TVR",                 "main.lua", "ENABLE_TVR",                  "Voracious Resurgence (1 = on)",         0,   0,   1,     "int"),
    ("main.RESTRICT_CONTENT",           "main.lua", "RESTRICT_CONTENT",            "Hide switched-off content (1 = on)", 1, 0, 1, "int"),
    ("main.ENABLE_TRUST_QUESTS",        "main.lua", "ENABLE_TRUST_QUESTS",         "Trust quest NPCs (1 = on)", 0, 0, 1, "int"),
    ("main.ENABLE_DAILY_TALLY",         "main.lua", "ENABLE_DAILY_TALLY",          "Gobbie Mystery Box (1 = on)", 0, 0, 1, "int"),
    ("main.HALLOWEEN_2005",             "main.lua", "HALLOWEEN_2005",              "Harvest Festival (Oct 20-Nov 1, 1=on)", 1,   0,   1,     "int"),
    # (2026-11-20) off by default for now: on the November 2026 game version the opening scene stops at the map page and
    # the new character is stuck (Ste, Odeken, tarolin, shujimi): the era event files were made for October. A world
    # that already has a saved value keeps it. Put the default back to 1 once the era files match the game again.
    ("main.NEW_CHARACTER_CUTSCENE",     "main.lua", "NEW_CHARACTER_CUTSCENE",      "New-character cutscenes (1 = on)", 0, 0, 1, "int"),
    ("main.HOMEPOINT_TELEPORT",         "main.lua", "HOMEPOINT_TELEPORT",          "Home Point teleports (1 = on, 0 = classic)", 1, 0, 1, "int"),
    ("main.ENABLE_SURVIVAL_GUIDE",      "main.lua", "ENABLE_SURVIVAL_GUIDE",       "Survival Guide teleports (1 = on, 0 = classic)", 1, 0, 1, "int"),
    ("map.BASE_SPEED",                  "map.lua",  "BASE_SPEED",                  "Run speed (50 = retail)",               50,  40,  120,   "int"),
    ("map.MOUNT_SPEED",                 "map.lua",  "MOUNT_SPEED",                 "Chocobo and mount speed (80 = retail)", 80,  50,  150,   "int"),
]
RATE_DEFAULTS = {f[0]: f[4] for f in RATE_FIELDS}
RATE_DEFAULTS.update({"all_crafts": True, "ah_sim": False, "era_exp": True, "conquest_sim": True, "claim_shield": False,
                      "defaults_version": 2})
RATE_DEFAULTS.update({"crowds": True, "crowds_per_zone": 15})   # ambient crowds (modules/custom/lua/crowds.lua)
RATE_DEFAULTS.update({"crowds_chat": True, "crowds_chat_amount": "normal", "crowds_chat_ai": True})   # crowd chat (crowds_chat.lua)
RATE_DEFAULTS.update({"crowds_field": True, "crowds_field_parties": 1})   # field parties (crowds_field.lua)
RATE_DEFAULTS.update({"bots": True, "bots_roster": 100, "bots_online": 50})   # bot players (bots.lua, bots_life.lua)
RATE_DEFAULTS.update({"bots_growth": "realistic"})
RATE_DEFAULTS.update({"bots_head_start": False, "bots_head_start_done": False})   # one-time bot head start (bots_growth.lua)
RATE_DEFAULTS.update({"squad_all_gear": False})   # (Yache) every piece of gear counts as given to the squad (squad.lua squadAllGear)
RATE_DEFAULTS.update({"bots_pass_loot": True})   # (delukard) bot players in your party pass every drop at once (bots.cpp)
RATE_DEFAULTS.update({"training_dummies": False})   # (Jon Tanta) !sandbox training dummies in Rolanberry Fields, a testing tool (squad_sandbox.lua)
RATE_DEFAULTS.update({"squad_keep_gear": False})   # gear given to the squad is unlocked and you keep the piece (squad.lua squadKeepGear)
RATE_DEFAULTS.update({"spell_scrolls": False})  # squad mates need scrolls for spells of level 18+ (blue magic from monsters) (squad.lua)
RATE_DEFAULTS.update({"short_quest_waits": True})   # Chocobo's Wounds 1 minute, Forge Your Destiny 1 hour (late/quest_waits.lua)
RATE_DEFAULTS.update({"event_harvest": True, "event_starlight": True, "event_egg_hunt": True, "event_horro": True})   # one switch per seasonal event (events_mode.lua)
RATE_DEFAULTS.update({"events": "date"})   # seasonal events: "date" (their own dates), "on" (all year), "off" (events_mode.lua)
RATE_DEFAULTS.update({"modern_stacks": True})   # item stacks as in today's game (12 / 99); off = Phoenix's era stacks (stack_mode.py)
RATE_DEFAULTS.update({"full_bags": True})   # every bag (inventory, Mog Safe, Satchel, Sack, Case, Wardrobes) at 80 from the start (crystalboy_quests.lua)
RATE_DEFAULTS.update({"squad_call_cooldown": 5})   # minutes before a squad mate can be called again (squad.lua)   # bots grow while you are away (bots_growth.lua)
RATE_DEFAULTS.update({"squad_chat": True})   # squad mates answer in party chat with the local AI (squad-chat/squad_chat.py)

# ---------- the world: install-time choice, also on the Rates tab ----------
# Each world is a set of the switches above. Picking one only fills them in; any switch can still be changed by hand
# (the Rates tab then shows "Custom").
WORLDS = {
    "quiet": ("Quiet world", "No town crowds or bot players. Squad mates use their scripted lines. Nothing uses the AI."),
    "living": ("Living world", "Town crowds, parties in the field, bot players who level, craft and chat with "
                               "ready-made lines, and a stocked auction house. No AI download."),
    "living_ai": ("Living world + AI chat", "The living world, plus AI-written crowd chatter, bot players who answer "
                                            "you, and squad mates who talk. Needs Ollama and a model (about 8 GB)."),
}
WORLD_SWITCHES = {
    "quiet": {"crowds": False, "crowds_chat": False, "crowds_chat_ai": False, "crowds_field": False, "bots": False, "squad_chat": False},
    "living": {"crowds": True, "crowds_chat": True, "crowds_chat_ai": False, "crowds_field": True, "bots": True, "squad_chat": False},
    "living_ai": {"crowds": True, "crowds_chat": True, "crowds_chat_ai": True, "crowds_field": True, "bots": True, "squad_chat": True},
}
# worlds that also switch the auction house simulator on (it stays the player's own switch afterwards)
LIVING_AH = ("living", "living_ai")
# crowd size per town, bot players in the roster, bot players online at once
POPULATIONS = {"small": ("Small", 10, 100, 40), "medium": ("Medium", 20, 200, 150), "large": ("Large", 30, 300, 500)}


def apply_world(rates, world=None, population=None):
    """The rates with a world's switches and a population's sizes filled in (either can be None to leave it)."""
    out = dict(rates)
    if world in WORLD_SWITCHES:
        out.update(WORLD_SWITCHES[world])
        if world in LIVING_AH:
            out["ah_sim"] = True    # a living world starts with a stocked auction house (not part of world_of)
    if population in POPULATIONS:
        _label, crowd, roster, online = POPULATIONS[population]
        out.update({"crowds_per_zone": crowd, "bots_roster": roster, "bots_online": online})
    return out


def world_of(rates):
    """Which world the switches match, or "custom"."""
    for key, switches in WORLD_SWITCHES.items():
        if all(bool(rates.get(k, RATE_DEFAULTS.get(k))) == v for k, v in switches.items()):
            return key
    return "custom"


def population_of(rates):
    for key, (_label, crowd, roster, online) in POPULATIONS.items():
        if (rates.get("crowds_per_zone"), rates.get("bots_roster"), rates.get("bots_online")) == (crowd, roster, online):
            return key
    return "custom"


def needs_ai(rates):
    """True when something in this world talks through the local AI (Ollama)."""
    chat_ai = rates.get("crowds_chat_ai", True) and (rates.get("crowds", True) or rates.get("bots", True))
    return bool(rates.get("squad_chat", True) or chat_ai)


# ---------- the interface: XIUI (an addon, stable) or XIUIplus (a plugin, alpha) ----------
INTERFACES = {"xiui": ("XIUI", "addon", "xiui"), "xiuiplus": ("XIUIplus", "plugin", "XIUIplus")}


def interface_of(manager):
    """"xiui", "xiuiplus", "both" or "none", from what the managed script loads."""
    addons, plugins = manager.enabled("addon"), manager.enabled("plugin")
    have = [key for key, (_label, kind, name) in INTERFACES.items() if name.lower() in (addons if kind == "addon" else plugins)]
    return have[0] if len(have) == 1 else ("both" if have else "none")


def set_interface(manager, choice):
    """Loads one interface and unloads the other (they draw the same windows)."""
    for key, (_label, kind, name) in INTERFACES.items():
        manager.set(kind, name, key == choice)

EXPANSION_IDS = ["main.ENABLE_COP", "main.ENABLE_TOAU", "main.ENABLE_WOTG", "main.ENABLE_ACP", "main.ENABLE_AMK", "main.ENABLE_ASA",
                 "main.ENABLE_ABYSSEA", "main.ENABLE_SOA", "main.ENABLE_ROV", "main.ENABLE_VOIDWATCH", "main.ENABLE_TVR"]

RATE_PRESETS = {
    "Classic (retail rates)": {"era_exp": False},
    "All expansions on": {fid: 1 for fid in EXPANSION_IDS},
    # The real pre-2011 tables: the base exp table and the per-monster caps (200 / 250 / 300) from the Classic FFXI wiki.
    # The exp rate goes back to 1.0, because the tables themselves carry the era pace.
    "Aht Urhgan era (real exp tables)": {"era_exp": True},
    "Relaxed solo": {"era_exp": False, "map.EXP_RATE": 2.0, "main.EXP_RATE": 2.0, "main.BOOK_EXP_RATE": 2.0, "main.ROE_EXP_RATE": 2.0, "map.CAPACITY_RATE": 2.0,
                     "map.DROP_RATE_MULTIPLIER": 1.5, "map.MOB_GIL_MULTIPLIER": 1.5, "main.GIL_RATE": 1.5, "main.CASKET_DROP_RATE": 0.15,
                     "map.SKILLUP_CHANCE_MULTIPLIER": 2.0, "map.CRAFT_CHANCE_MULTIPLIER": 2.0, "map.FISHING_SKILL_MULTIPLIER": 2.0},
    "Fast": {"era_exp": False, "map.EXP_RATE": 5.0, "main.EXP_RATE": 5.0, "main.BOOK_EXP_RATE": 5.0, "main.ROE_EXP_RATE": 5.0, "map.CAPACITY_RATE": 5.0,
             "map.EXP_LOSS_RATE": 0.5, "map.DROP_RATE_MULTIPLIER": 2.0, "map.MOB_GIL_MULTIPLIER": 3.0, "main.GIL_RATE": 3.0,
             "main.TABS_RATE": 3.0, "main.CASKET_DROP_RATE": 0.25, "map.SKILLUP_CHANCE_MULTIPLIER": 4.0, "map.CRAFT_CHANCE_MULTIPLIER": 4.0,
             "map.CRAFT_HQ_CHANCE_MULTIPLIER": 1.5, "map.FISHING_SKILL_MULTIPLIER": 4.0},
}

# Player installs (first-run setup) only see the options that fit this era project. The rest stay at their era values
# (the RATE_DEFAULTS above): level cap 75, everything after Aht Urhgan off, switched-off content hidden, no Trust quests
# or Gobbie Mystery Box, the Harvest Festival as set, and the Aht Urhgan-era exp tables on. The dev launcher shows all of it.
PLAYER_HIDDEN_RATES = {"map.CAPACITY_RATE", "main.SPARKS_RATE", "main.MAX_LEVEL", "main.ENABLE_WOTG", "main.ENABLE_ACP",
                       "main.ENABLE_AMK", "main.ENABLE_ASA", "main.ENABLE_ABYSSEA", "main.ENABLE_SOA", "main.ENABLE_ROV",
                       "main.ENABLE_VOIDWATCH", "main.ENABLE_TVR", "main.RESTRICT_CONTENT", "main.ENABLE_TRUST_QUESTS",
                       "main.ENABLE_DAILY_TALLY", "main.HALLOWEEN_2005",
                       "main.ROE_EXP_RATE"}   # (Records of Eminence are not in this era: Senna, 2026-11-18)
RATE_PRESETS["Era default"] = {}
PLAYER_RATE_PRESETS = ["Era default", "Relaxed solo", "Fast"]


def lock_player_rates(rates):
    """A player's rates with the hidden options back at their era values (a preset or an old rates.json can't change them)."""
    out = dict(rates)
    for key in PLAYER_HIDDEN_RATES:
        out[key] = RATE_DEFAULTS[key]
    out["era_exp"] = True
    return out


def rates_path(here):
    return os.path.join(here, "rates.json")


def clean_rate(field, value):
    """Turn whatever was typed into a valid number for that field (falls back to the default)."""
    _id, _file, _key, _label, default, lo, hi, kind = field
    try:
        number = float(str(value).strip().replace(",", "."))
    except ValueError:
        return default
    number = max(lo, min(hi, number))
    return int(round(number)) if kind in ("int", "bool") else round(number, 3)


def write_kit_paths(server_dir, kit_dir=None, ashita_dir=None):
    """Where the kit and Ashita are, for the server's Lua (squad chat bridge, Crystal Boy claims).
    modules/custom/lua/kit_paths.lua, rewritten every launch; the Lua falls back to C:/FFXISOLO and
    C:/Ashita-v4beta-main when it is missing."""
    def lua_path(p):
        p = str(p).replace("\\", "/")
        return (p if p.endswith("/") else p + "/").replace("'", "\\'")
    module_dir = os.path.join(server_dir, "modules", "custom", "lua")
    os.makedirs(module_dir, exist_ok=True)
    parts = ["kit = '%s'" % lua_path(kit_dir or KIT_DIR)]
    if ashita_dir:
        parts.append("ashita = '%s'" % lua_path(ashita_dir))
    with open(os.path.join(module_dir, "kit_paths.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher. Do not edit: it is rewritten every launch.\n")
        f.write("return { " + ", ".join(parts) + " }\n")


def write_crowds_config(server_dir, rates):
    """Ambient crowds + chat settings for modules/custom/lua/crowds.lua (rewritten every launch)."""
    amount = rates.get("crowds_chat_amount", "normal")
    amount = amount if amount in ("quiet", "normal", "busy") else "normal"
    module_dir = os.path.join(server_dir, "modules", "custom", "lua")
    os.makedirs(module_dir, exist_ok=True)
    with open(os.path.join(module_dir, "crowds_config.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
        f.write("return { enabled = %s, per_zone = %d, chat = %s, chat_amount = '%s', chat_ai = %s, field = %s, field_parties = %d }\n" % (
            "true" if rates.get("crowds", True) else "false", clean_crowd_size(rates.get("crowds_per_zone", 30)),
            "true" if rates.get("crowds_chat", True) else "false", amount,
            "true" if rates.get("crowds_chat_ai", True) else "false",
            "true" if rates.get("crowds_field", True) else "false", max(0, min(3, int(rates.get("crowds_field_parties", 1) or 0)))))
    with open(os.path.join(module_dir, "bots_config.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
        growth = rates.get("bots_growth", "realistic")
        growth = growth if growth in ("off", "realistic", "fast") else "realistic"
        head_start = bool(rates.get("bots_head_start")) and not rates.get("bots_head_start_done")
        f.write("return { enabled = %s, roster = %d, online = %d, growth = '%s', head_start = %s, pass_loot = %s }\n" % (
            "true" if rates.get("bots", True) else "false", max(0, min(600, int(rates.get("bots_roster", 100) or 0))),
            max(0, min(550, int(rates.get("bots_online", 50) or 0))), growth, "true" if head_start else "false",
            "true" if rates.get("bots_pass_loot", True) else "false"))
    with open(os.path.join(module_dir, "squad_config.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
        f.write("return { call_cooldown_min = %d, spell_scrolls = %s, keep_gear = %s, training_dummies = %s, all_gear = %s }\n" % (
            clean_call_cooldown(rates.get("squad_call_cooldown", 5)), "true" if rates.get("spell_scrolls", False) else "false",
            "true" if rates.get("squad_keep_gear", False) else "false", "true" if rates.get("training_dummies", False) else "false",
            "true" if rates.get("squad_all_gear", False) else "false"))
    with open(os.path.join(module_dir, "storage_config.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
        f.write("return { full_bags = %s }\n" % ("true" if rates.get("full_bags", True) else "false"))
    with open(os.path.join(module_dir, "quest_waits_config.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
        f.write("return { short = %s }\n" % ("true" if rates.get("short_quest_waits", True) else "false"))
    with open(os.path.join(module_dir, "events_config.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
        f.write("return { mode = '%s', harvest = %s, starlight = %s, egg_hunt = %s, horro = %s }\n" % (
            clean_events(rates.get("events", "date")),
            *("true" if rates.get(k, True) else "false" for k in ("event_harvest", "event_starlight", "event_egg_hunt", "event_horro"))))


EVENTS_MODES = ("date", "on", "off")


def clean_events(value):
    """Seasonal events setting: "date", "on" or "off" (anything else falls back to "date")."""
    return value if value in EVENTS_MODES else "date"


def clean_call_cooldown(value):
    """Squad call timer: minutes before a mate can be called again, 0-30 (anything else falls back to 5)."""
    try:
        return max(0, min(30, int(round(float(str(value).strip().replace(",", "."))))))
    except ValueError:
        return 5


_SETTING_LINE = re.compile(r"""(?m)^(\s*)([A-Z][A-Z0-9_]*)(\s*=\s*)(-?\d[\d.]*|true|false|'[^'\n]*'|"[^"\n]*")""")


def carry_hand_edits(text, base, old, managed):
    """Settings the player changed by hand in a launcher-written file (old differs from base, what the launcher wrote
    then) are put into the new text. Simple values only (numbers, true/false, quoted text); keys in managed are the
    launcher's own and are never carried. Returns (new text, list of the keys kept)."""
    before = {m.group(2): m.group(4) for m in _SETTING_LINE.finditer(base)}
    now = {m.group(2): m.group(4) for m in _SETTING_LINE.finditer(old)}
    kept = []
    for key, value in now.items():
        if key in managed or key not in before or before[key] == value:
            continue
        pattern = re.compile(r"(?m)^(\s*" + re.escape(key) + r"\s*=\s*)(-?\d[\d.]*|true|false|'[^'\n]*'|\"[^\"\n]*\")")
        text, count = pattern.subn(lambda m, v=value: m.group(1) + v, text, count=1)
        if count:
            kept.append(key)
    return text, kept


def clean_crowd_size(value):
    """Ambient crowds: adventurers per area, 0-40 (anything else falls back to 15)."""
    try:
        return max(0, min(40, int(round(float(str(value).strip().replace(",", "."))))))
    except ValueError:
        return 15


# Settings that players set by hand in settings/main.lua before the launcher had a box for them. The first time the
# launcher sees no saved value for one, it takes the value from that file instead of the default, so an update does not
# quietly undo a hand edit (the launcher writes its own value over the file from then on).
ADOPTED_RATES = ("main.NM_LOTTERY_CHANCE", "main.NM_LOTTERY_COOLDOWN")


def _adopt_hand_edits(here, rates, saved):
    try:
        missing = [f for f in RATE_FIELDS if f[0] in ADOPTED_RATES and f[0] not in saved]
        if not missing:
            return
        with open(os.path.join(here, "config.json"), "r", encoding="utf-8-sig") as f:
            server_dir = json.load(f).get("server_dir") or ""
        for field in missing:
            path = os.path.join(server_dir, "settings", field[1])
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                found = re.search(r"(?m)^\s*" + re.escape(field[2]) + r"\s*=\s*(-?\d+(?:\.\d+)?)\s*,", f.read())
            if found:
                rates[field[0]] = clean_rate(field, found.group(1))
    except Exception:
        pass      # (no config.json yet, an unreadable file: the defaults stand)


def load_rates(here):
    rates = dict(RATE_DEFAULTS)
    try:
        with open(rates_path(here), "r", encoding="utf-8-sig") as f:
            saved = json.load(f)
        for field in RATE_FIELDS:
            if field[0] in saved:
                rates[field[0]] = clean_rate(field, saved[field[0]])
        _adopt_hand_edits(here, rates, saved)
        for flag in ("all_crafts", "ah_sim", "era_exp", "conquest_sim"):
            if flag in saved:
                rates[flag] = bool(saved[flag])
        if int(saved.get("defaults_version", 1) or 1) < 2:
            # launcher 1.3.1: era exp tables and the conquest simulator are on by default; switch them on once for older settings
            rates["era_exp"], rates["conquest_sim"] = True, True
        rates["claim_shield"] = False  # the claim shield stays off on this solo server (its switch was removed)
        if "crowds" in saved:
            rates["crowds"] = bool(saved["crowds"])
        if "crowds_per_zone" in saved:
            rates["crowds_per_zone"] = clean_crowd_size(saved["crowds_per_zone"])
        for key in ("crowds_chat", "crowds_chat_ai"):
            if key in saved:
                rates[key] = bool(saved[key])
        if saved.get("crowds_chat_amount") in ("quiet", "normal", "busy"):
            rates["crowds_chat_amount"] = saved["crowds_chat_amount"]
        if "crowds_field" in saved:
            rates["crowds_field"] = bool(saved["crowds_field"])
        if "crowds_field_parties" in saved:
            try:
                rates["crowds_field_parties"] = max(0, min(3, int(saved["crowds_field_parties"])))
            except (TypeError, ValueError):
                pass
        if "bots" in saved:
            rates["bots"] = bool(saved["bots"])
        if "squad_chat" in saved:
            rates["squad_chat"] = bool(saved["squad_chat"])
        if saved.get("bots_growth") in ("off", "realistic", "fast"):
            rates["bots_growth"] = saved["bots_growth"]
        for key in ("bots_head_start", "bots_head_start_done"):
            if key in saved:
                rates[key] = bool(saved[key])
        if "squad_call_cooldown" in saved:
            rates["squad_call_cooldown"] = clean_call_cooldown(saved["squad_call_cooldown"])
        if "full_bags" in saved:
            rates["full_bags"] = bool(saved["full_bags"])
        if "modern_stacks" in saved:
            rates["modern_stacks"] = bool(saved["modern_stacks"])
        if "spell_scrolls" in saved:
            rates["spell_scrolls"] = bool(saved["spell_scrolls"])
        if "squad_keep_gear" in saved:
            rates["squad_keep_gear"] = bool(saved["squad_keep_gear"])
        if "training_dummies" in saved:
            rates["training_dummies"] = bool(saved["training_dummies"])
        if "bots_pass_loot" in saved:
            rates["bots_pass_loot"] = bool(saved["bots_pass_loot"])
        if "squad_all_gear" in saved:
            rates["squad_all_gear"] = bool(saved["squad_all_gear"])
        if "short_quest_waits" in saved:
            rates["short_quest_waits"] = bool(saved["short_quest_waits"])
        if "events" in saved:
            rates["events"] = clean_events(saved["events"])
        for k in ("event_harvest", "event_starlight", "event_egg_hunt", "event_horro"):
            if k in saved:
                rates[k] = bool(saved[k])
        for key, lo, hi in (("bots_roster", 0, 600), ("bots_online", 0, 550)):
            if key in saved:
                try:
                    rates[key] = max(lo, min(hi, int(saved[key])))
                except (TypeError, ValueError):
                    pass
    except (OSError, ValueError):
        pass
    return rates


def save_rates(here, rates):
    with open(rates_path(here), "w", encoding="utf-8") as f:
        json.dump(rates, f, indent=2)


# --- Rate profiles (2026-11-18): save the Rates tab under a name, load it later, share it as a .txt file -----------
PROFILE_DIR = "rate-profiles"
PROFILE_SKIP = {"bots_head_start", "bots_head_start_done", "defaults_version"}   # (this PC's own one-time state)


def profile_dir(here):
    return os.path.join(here, PROFILE_DIR)


def profile_name_ok(name):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _\-()'.,!]{0,39}", (name or "").strip()))


def list_profiles(here):
    folder = profile_dir(here)
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.splitext(n)[0] for n in os.listdir(folder) if n.lower().endswith(".txt"))


def profile_text(name, rates):
    """The shareable form: a short header plus the settings as JSON (only the known settings)."""
    data = {k: v for k, v in rates.items() if k in RATE_DEFAULTS and k not in PROFILE_SKIP}
    return ("# XI: Forever Offline rate profile: %s\n# Load it in the launcher: RULES > My builds > Import.\n" % name
            + json.dumps({"name": name, "rates": data}, indent=2) + "\n")


def parse_profile(text):
    """(name, rates) from a profile file; only known settings, each checked like a hand-edited rates.json."""
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    data = json.loads(body)
    name, raw = str(data.get("name") or "Imported"), data.get("rates") or {}
    if not isinstance(raw, dict):
        raise ValueError("not a rate profile")
    fields = {f[0]: f for f in RATE_FIELDS}
    rates = {}
    for key, value in raw.items():
        if key not in RATE_DEFAULTS or key in PROFILE_SKIP:
            continue
        default = RATE_DEFAULTS[key]
        if key in fields:
            rates[key] = clean_rate(fields[key], value)
        elif isinstance(default, bool):
            rates[key] = bool(value)
        elif isinstance(default, int):
            try:
                rates[key] = int(value)
            except (TypeError, ValueError):
                pass
        elif isinstance(default, str) and isinstance(value, str):
            rates[key] = value[:20]
    return name, rates


def save_profile(here, name, rates):
    if not profile_name_ok(name):
        raise ValueError("Use letters, numbers and spaces for the name (up to 40).")
    os.makedirs(profile_dir(here), exist_ok=True)
    path = os.path.join(profile_dir(here), name.strip() + ".txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(profile_text(name.strip(), rates))
    return path


def load_profile(here, name):
    with open(os.path.join(profile_dir(here), name + ".txt"), encoding="utf-8") as f:
        return parse_profile(f.read())[1]


def import_profile(here, path):
    with open(path, encoding="utf-8") as f:
        name, rates = parse_profile(f.read())
    name = re.sub(r"[^A-Za-z0-9 _\-()'.,!]", "", name)
    name = re.sub(r"^[^A-Za-z0-9]+", "", name).strip()[:40] or "Imported"
    save_profile(here, name, rates)
    return name


def apply_preset(rates, name):
    out = dict(RATE_DEFAULTS)
    out["ah_sim"], out["all_crafts"] = rates.get("ah_sim", False), True
    out["conquest_sim"] = rates.get("conquest_sim", True)
    out["crowds"] = rates.get("crowds", True)
    for key, default in (("crowds_chat", True), ("crowds_chat_amount", "normal"), ("crowds_chat_ai", True),
                         ("crowds_field", True), ("crowds_field_parties", 1),
                         ("bots", True), ("bots_roster", 100), ("bots_online", 50), ("bots_growth", "realistic"),
                         ("squad_chat", True), ("bots_head_start", False), ("bots_head_start_done", False),
                         ("squad_call_cooldown", 5), ("full_bags", True), ("modern_stacks", True), ("spell_scrolls", False), ("squad_keep_gear", False), ("training_dummies", False), ("bots_pass_loot", True), ("squad_all_gear", False),
                         ("short_quest_waits", True), ("events", "date"), ("event_harvest", True), ("event_starlight", True), ("event_egg_hunt", True), ("event_horro", True)):
        out[key] = rates.get(key, default)
    out["crowds_per_zone"] = rates.get("crowds_per_zone", 15)
    out["main.MAX_LEVEL"] = rates.get("main.MAX_LEVEL", 75)
    out.update(RATE_PRESETS.get(name, {}))
    return out


LOGIN_EXPANSION_KEYS = {
    "main.ENABLE_COP":     ["CHAINS_OF_PROMATHIA"],
    "main.ENABLE_TOAU":    ["TREASURES_OF_AHT_URGHAN", "TREASURES_OF_AHT_URHGAN"],   # the server's own file spells it "URGHAN"
    "main.ENABLE_WOTG":    ["WINGS_OF_THE_GODDESS"],
    "main.ENABLE_ACP":     ["A_CRYSTALLINE_PROPHECY"],
    "main.ENABLE_AMK":     ["A_MOOGLE_KUPOD_ETAT"],
    "main.ENABLE_ASA":     ["A_SHANTOTTO_ASCENSION"],
    "main.ENABLE_ABYSSEA": ["VISIONS_OF_ABYSSEA", "SCARS_OF_ABYSSEA", "HEROES_OF_ABYSSEA"],
    "main.ENABLE_SOA":     ["SEEKERS_OF_ADOULIN"],
}

LOGIN_OPTIONAL_KEYS = {"TREASURES_OF_AHT_URGHAN", "TREASURES_OF_AHT_URHGAN"}   # two spellings: whichever the file has is used, no complaint about the other

RATES_MARKER = "-- Generated by the XI: Forever Offline launcher (Rates tab) from settings/default/"
OLD_RATES_MARKER = ("-- Generated by the FFXI Solo launcher (Rates tab) from settings/default/",
                    "-- Generated by the Phoenix Solo launcher (Rates tab) from settings/default/")   # files written by earlier versions


def _format_number(value, kind):
    if kind == "bool":
        return "true" if value else "false"
    return str(int(value)) if kind == "int" else ("%.3f" % value).rstrip("0").rstrip(".") if value != int(value) else "%d.0" % int(value)


CLAIM_SHIELD_ENTRY = "custom/lua/claim_shield.lua"


def set_module(server_dir, entry, enabled):
    """Switches one module on or off in modules/init.txt by commenting out its own line (or restoring it). Only a line that is exactly the
    module's entry is touched, never the comments that merely mention it. Returns a message when something changed or looks wrong, else None."""
    path = os.path.join(server_dir, "modules", "init.txt")
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
    except OSError:
        return f"modules/init.txt could not be read - {entry} left as it is"
    pattern = re.compile(r"(?m)^([ \t]*)(#[ \t]*)?(" + re.escape(entry) + r")[ \t]*(\r?)$")
    found = pattern.search(text)
    if not found:
        return f"{entry} was not found in modules/init.txt - nothing changed"
    is_off = found.group(2) is not None
    if is_off == (not enabled):
        return None                                                         # already the way it should be
    replacement = (lambda m: m.group(1) + m.group(3) + m.group(4)) if enabled else (lambda m: m.group(1) + "# " + m.group(3) + m.group(4))
    new_text = pattern.sub(replacement, text, count=1)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    return f"{entry}: switched {'on' if enabled else 'off'}"


FAST_TRAVEL_DIR_ENTRY = "custom/late"
FAST_TRAVEL_OLD_ENTRY = "custom/lua/fast_travel.lua"


def ensure_fast_travel(server_dir, kit_dir=None):
    """Fast travel on the Home Point crystals is always on. It must load AFTER Phoenix's era folder (whose "set your home point only"
    menu would otherwise replace it), so it lives in modules/custom/late, listed as the last folder entry of modules/init.txt.
    Run before every start: puts the file and the line back if an update or anything else moved them. Returns a list of messages."""
    messages = []
    kit_dir = kit_dir or KIT_DIR
    modules = os.path.join(server_dir, "modules")
    late = os.path.join(modules, "custom", "late", "fast_travel.lua")
    old = os.path.join(modules, "custom", "lua", "fast_travel.lua")
    kit = os.path.join(kit_dir, "travel", "fast_travel.lua")
    if not os.path.isfile(late):
        os.makedirs(os.path.dirname(late), exist_ok=True)
        if os.path.isfile(old):
            shutil.move(old, late)
            messages.append("fast travel: moved to modules/custom/late")
        elif os.path.isfile(kit):
            shutil.copy2(kit, late)
            messages.append("fast travel: restored from the kit")
        else:
            messages.append("fast travel: fast_travel.lua not found anywhere - teleporting from crystals is off")
            return messages
    path = os.path.join(modules, "init.txt")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    changed = False
    out = []
    for line in lines:
        bare = line.strip()
        if bare == FAST_TRAVEL_OLD_ENTRY:                       # the old place: would load it a second time, before the era folder
            out.append("# " + bare + "   (fast travel now loads from custom/late, at the end)")
            changed = True
        elif bare == FAST_TRAVEL_DIR_ENTRY or bare.startswith("# Loaded LAST: overrides here win"):
            changed = True                                       # taken out here, put back at the very end below
        else:
            out.append(line)
    active = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if active and active[-1] == FAST_TRAVEL_DIR_ENTRY and FAST_TRAVEL_OLD_ENTRY not in active:
        return messages                                          # already right: leave the file alone
    while out and out[-1].strip() == "":
        out.pop()
    out += ["", "# Loaded LAST: overrides here win over the era/phoenix folders above (fast travel, always on)", FAST_TRAVEL_DIR_ENTRY]
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(newline.join(out) + newline)
    messages.append("fast travel: modules/init.txt put right (custom/late is the last entry)")
    return messages


def apply_rates(server_dir, rates):
    """Writes settings/main.lua and settings/map.lua: a copy of the defaults with the chosen values filled in.
    A fresh copy is made every launch, so server updates to the defaults are never missed. Returns a list of messages."""
    messages = []
    settings_dir = os.path.join(server_dir, "settings")
    wanted = {"main.lua": [], "map.lua": [], "login.lua": []}
    for field in RATE_FIELDS:
        wanted[field[1]].append((field[2], rates.get(field[0], field[4]), field[7]))
    # The character screen's expansion icons come from the login server's own settings. They follow the same switches.
    for switch, login_keys in LOGIN_EXPANSION_KEYS.items():
        for login_key in login_keys:
            wanted["login.lua"].append((login_key, bool(rates.get(switch, 1)), "bool"))
    wanted["login.lua"].append(("RISE_OF_ZILART", True, "bool"))          # always part of the base setup
    wanted["login.lua"].append(("MOG_WARDROBE_3", True, "bool"))          # the character screen offers Mog Wardrobe 3 and 4
    wanted["login.lua"].append(("MOG_WARDROBE_4", True, "bool"))
    # Phoenix's defaults only let the newest retail client in (FFXI-3331 "The game's data has been updated"); this is an
    # offline server, so any client version may log in
    wanted["login.lua"].append(("VER_LOCK", 0, "int"))
    # co-op: while friends can reach this server, nobody makes accounts on it from the game's log in screen
    # (a visitor gets its account from the launcher's CO-OP page)
    if rates.get("coop_hosting"):
        wanted["login.lua"].append(("ACCOUNT_CREATION", False, "bool"))
    # crafting: 600 = the 75-era point where the shared pool starts; 3200 lets all eight crafts reach the top
    wanted["map.lua"].append(("CRAFT_COMMON_CAP", 600, "int"))
    wanted["map.lua"].append(("CRAFT_SPECIALIZATION_POINTS", 3200 if rates.get("all_crafts", True) else 400, "int"))
    # auction house: no limit on your own listings (the ah_pagination module shows them 6 per page)
    wanted["map.lua"].append(("AH_LIST_LIMIT", 0, "int"))
    # (2026-11-21, Bob Roberts) the core caps a player's speed at map.SPEED_LIMIT (80), so a "Run speed" above 50 was cut
    # back as soon as Flee or movement gear added to it, and above 80 it did nothing at all. The limit keeps the retail
    # ratio (80 for 50: room for Flee and gear) and never drops below the mount speed or 80.
    try:
        _base = int(float(rates.get("map.BASE_SPEED", 50)))
        _mount = int(float(rates.get("map.MOUNT_SPEED", 80)))
    except (TypeError, ValueError):
        _base, _mount = 50, 80
    wanted["map.lua"].append(("SPEED_LIMIT", max(80, _mount, min(255, round(_base * 1.6))), "int"))
    # (2026-11-20, Trinity: "Is fishing disabled?") the server default switches all fishing off (a guard against fishing
    # bots on public servers, "enable at your own risk"); there is no such risk on your own world
    wanted["map.lua"].append(("FISHING_ENABLE", True, "bool"))
    # (2026-11-20, the user: "there is no reason for a limit here") no daily limits on your own world: fishing (200
    # catches a day and the fatigue meter; needs the server from this release on, older ones skip the key) and
    # chocobo digging (100 finds a day)
    wanted["map.lua"].append(("FISHING_DAILY_LIMITS", False, "bool"))
    wanted["main.lua"].append(("DIG_FATIGUE", 0, "int"))
    # (2026-11-20, Yumainai: the rank 2-3 dragon was not capped) the server default lifts the level cap of every mission
    # fight to the max level; on, they keep their era caps (era/lua/battlefields/mission_level_caps.lua: rank 2-3 at 25,
    # rank 5-1 at 50, Promathia 30 / 40 / 50 / 60 / 75), like every other capped battlefield
    wanted["map.lua"].append(("LV_CAP_MISSION_BCNM", True, "bool"))
    # Keep crash dumps on: settings/main.lua is rebuilt from the defaults every launch, so a hand edit
    # there is lost. With dumps on, a crash writes a minidump and a tombstone that names the function.
    # (2026-11-20, Yumainai: "Explorer Moogles" standing in the middle of Northern San d'Oria, Bastok Mines and Mhaura that
    # do nothing) they are Wings of the Goddess content, so the server parks them at 0,0,0 and hides them; but the zone
    # scripts un-hide them whenever this level is not 0 (xi.server.setExplorerMoogles). 0 = no Explorer Moogles.
    wanted["main.lua"].append(("EXPLORER_MOOGLE_LV", 0, "int"))
    wanted["main.lua"].append(("GENERATE_CORE_DUMP", True, "bool"))
    # The watchdog kills the map server when one tick takes 2 s. On slower PCs a log in (the bots logging in with you and
    # catching up on their history) can take longer; that's fine offline, so allow 15 s before it counts as a hang.
    wanted["main.lua"].append(("INACTIVITY_WATCHDOG_PERIOD", 15000, "int"))
    # Full bags (default): new characters start at 80 and crystalboy_quests.lua opens every other bag at 80 on log in.
    # Off = the usual Phoenix bags: 30 slots, the Gobbiebag quests add space (and still give the Crystal Boy items)
    wanted["main.lua"].append(("START_INVENTORY", 80 if rates.get("full_bags", True) else 30, "int"))

    for filename, entries in wanted.items():
        default_path = os.path.join(settings_dir, "default", filename)
        if not os.path.exists(default_path):
            messages.append(f"{filename}: default settings file not found - skipped")
            continue
        with open(default_path, "r", encoding="utf-8-sig") as f:
            text = f.read()
        for key, value, kind in entries:
            pattern = re.compile(r"(?m)^(\s*" + re.escape(key) + r"\s*=\s*)(-?\d[\d.]*|true|false)")
            text, count = pattern.subn(lambda m: m.group(1) + _format_number(value, kind), text, count=1)
            if count == 0 and not (filename == "login.lua" and key in LOGIN_OPTIONAL_KEYS):
                messages.append(f"{filename}: setting {key} not found - left at the default")
        target = os.path.join(settings_dir, filename)
        base = os.path.join(settings_dir, ".launcher-base", filename)
        base_text = f"{RATES_MARKER}{filename}\n" + text          # what the launcher alone writes (before your own edits)
        if os.path.exists(target):
            with open(target, "r", encoding="utf-8-sig", errors="replace") as f:
                old = f.read()
            if not old.startswith((RATES_MARKER,) + OLD_RATES_MARKER):
                shutil.copy2(target, target + ".before-launcher")  # keep a hand-made override safe, once
            elif os.path.exists(base):
                # your own edits in this file (SERVER_NAME and the like) are carried over: whatever differs from what the
                # launcher wrote last time, except the values the Rates tab itself sets
                with open(base, "r", encoding="utf-8-sig", errors="replace") as f:
                    text, kept = carry_hand_edits(text, f.read(), old, {key for key, _v, _k in entries})
                if kept:
                    messages.append(f"{filename}: kept your own changes ({', '.join(kept)})")
        out_text = f"{RATES_MARKER}{filename}\n" + text
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(out_text)
        try:
            os.makedirs(os.path.dirname(base), exist_ok=True)
            with open(base, "w", encoding="utf-8", newline="\n") as f:
                f.write(base_text)
        except OSError:
            pass

    # The era experience module (modules/custom/lua/era_exp.lua) reads its on/off switch from this small file
    try:
        module_dir = os.path.join(server_dir, "modules", "custom", "lua")
        os.makedirs(module_dir, exist_ok=True)
        with open(os.path.join(module_dir, "era_exp_config.lua"), "w", encoding="utf-8", newline="\n") as f:
            f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
            f.write("return { enabled = " + ("true" if rates.get("era_exp", False) else "false") + " }\n")
    except OSError as problem:
        messages.append(f"era_exp_config.lua: could not be written ({problem})")
    # Ambient crowds (modules/custom/lua/crowds.lua) read their switch and size from this small file
    try:
        module_dir = os.path.join(server_dir, "modules", "custom", "lua")
        os.makedirs(module_dir, exist_ok=True)
        with open(os.path.join(module_dir, "crowds_config.lua"), "w", encoding="utf-8", newline="\n") as f:
            f.write("-- Written by the XI: Forever Offline launcher (Rates tab). Do not edit: it is rewritten every launch.\n")
            f.write("return { enabled = %s, per_zone = %d }\n" % ("true" if rates.get("crowds", True) else "false",
                                                             clean_crowd_size(rates.get("crowds_per_zone", 15))))
    except OSError as problem:
        messages.append(f"crowds_config.lua: could not be written ({problem})")
    try:
        write_crowds_config(server_dir, rates)   # the full file, with the chat settings
    except OSError as problem:
        messages.append(f"crowds_config.lua (chat): could not be written ({problem})")
    # Fast travel from the Home Point crystals: always on, whatever an update did to init.txt
    try:
        messages.extend(ensure_fast_travel(server_dir))
    except OSError as problem:
        messages.append(f"fast travel: could not be checked ({problem})")
    # NM claim shield: only useful with other players competing for NMs. Off by default for solo play (modules/init.txt, applied at server start).
    try:
        note = set_module(server_dir, CLAIM_SHIELD_ENTRY, bool(rates.get("claim_shield", False)))
        if note:
            messages.append(note)
    except OSError as problem:
        messages.append(f"claim shield: modules/init.txt could not be changed ({problem})")
    return messages


# ---------- graphics (the [ffxi.registry] section of the Ashita boot file) ----------
# id: (registry key, default, min, max)   keys and meanings from the community registry guides
GRAPHICS_KEYS = {
    "screen_w":    ("0001", 1920, 640, 7680),
    "screen_h":    ("0002", 1080, 480, 4320),
    "bg_w":        ("0003", 4096, 512, 8192),
    "bg_h":        ("0004", 4096, 512, 8192),
    "mip":         ("0000", 6,    0,   6),
    "bump":        ("0017", 0,    0,   1),
    "textures":    ("0018", 2,    0,   2),     # 0 = most compressed, 1 = low compression, 2 = uncompressed
    "window_mode": ("0034", 1,    0,   3),     # 0 = fullscreen, 1 = window, 3 = borderless window
    "bg_sound":    ("0035", 1,    0,   1),     # keep playing sound when the window is not in front
    "fonts":       ("0036", 2,    0,   2),     # 0 = compressed, 1 = uncompressed, 2 = high quality
    "menu_w":      ("0037", 1920, 320, 7680),
    "menu_h":      ("0038", 1080, 240, 4320),
    "stab":        ("0040", 0,    0,   1),     # graphics stabilization
}
GRAPHICS_DEFAULTS = {k: v[1] for k, v in GRAPHICS_KEYS.items()}
WINDOW_MODES = {0: "Fullscreen", 1: "Windowed", 3: "Borderless window"}
TEXTURE_LEVELS = {0: "Compressed (smallest)", 1: "Low compression", 2: "Uncompressed (best)"}
FONT_LEVELS = {0: "Compressed", 1: "Uncompressed", 2: "High quality"}
GRAPHICS_PRESETS = {
    "Low (weak PC)":          {"bg_w": 1024, "bg_h": 1024, "textures": 0, "fonts": 0, "mip": 0, "bump": 0},
    "Balanced":               {"bg_w": 2048, "bg_h": 2048, "textures": 2, "fonts": 2, "mip": 6, "bump": 0},
    "Sharp (Ashita default)": {"bg_w": 4096, "bg_h": 4096, "textures": 2, "fonts": 2, "mip": 6, "bump": 0},
}
REGISTRY_SECTION = "ffxi.registry"


def clean_graphics(values):
    out = {}
    for gid, (_key, default, lo, hi) in GRAPHICS_KEYS.items():
        try:
            number = int(round(float(str(values.get(gid, default)).strip())))
        except ValueError:
            number = default
        out[gid] = max(lo, min(hi, number))
    if out["window_mode"] not in WINDOW_MODES:
        out["window_mode"] = GRAPHICS_DEFAULTS["window_mode"]
    return out


def _section_bounds(lines):
    start = end = None
    for i, line in enumerate(lines):
        m = re.match(r"^\s*\[(.+?)\]", line)
        if m:
            if start is not None:
                end = i
                break
            if m.group(1).strip().lower() == REGISTRY_SECTION:
                start = i
    if start is not None and end is None:
        end = len(lines)
    return start, end


def read_boot_graphics(ini_path):
    """What the boot file currently says (values it does not mention, or marks -1, fall back to the defaults)."""
    values = dict(GRAPHICS_DEFAULTS)
    try:
        with open(ini_path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return values
    start, end = _section_bounds(lines)
    if start is None:
        return values
    found = {}
    for line in lines[start + 1:end]:
        m = re.match(r"^\s*(\d{4})\s*=\s*(-?\d+)", line)
        if m:
            found[m.group(1)] = int(m.group(2))
    for gid, (key, _d, _lo, _hi) in GRAPHICS_KEYS.items():
        if key in found and found[key] >= 0:
            values[gid] = found[key]
    return clean_graphics(values)


def game_dir_value(game_dir):
    """Registry 0042 (the game's install folder, where PrintScreen saves screenshots) as the game sees it: on Linux the
    Proton Z: path. None when the folder is not known or missing."""
    if not game_dir or not os.path.isdir(game_dir):
        return None
    if os.name == "nt":
        return os.path.abspath(game_dir)
    import launcher_linux
    return launcher_linux.windows_path(game_dir)


def apply_graphics(ini_path, values, game_dir=None):
    """Writes the chosen display values into [ffxi.registry]; every other line in the file stays exactly as it was.
    With game_dir, key 0042 is pointed at the real game folder too (Ashita's example file says C:\\Program Files (x86),
    and the game crashed on PrintScreen when that folder did not exist).
    The original file is saved once as <file>.before-graphics."""
    values = clean_graphics(values)
    shot_dir = game_dir_value(game_dir)
    with open(ini_path, "r", encoding="utf-8-sig", newline="") as f:   # newline="" keeps the file's own line endings
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    start, end = _section_bounds(lines)
    if start is None:
        raise RuntimeError("The boot file has no [ffxi.registry] section.")
    backup = ini_path + ".before-graphics"
    if not os.path.exists(backup):
        shutil.copy2(ini_path, backup)
    pending = {key: values[gid] for gid, (key, _d, _lo, _hi) in GRAPHICS_KEYS.items()}
    for i in range(start + 1, end):
        m = re.match(r"^(\s*)(\d{4})(\s*=\s*)(-?\d+)(.*)$", lines[i])
        if m and m.group(2) in pending:
            lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{pending.pop(m.group(2))}{m.group(5)}"
        elif shot_dir and re.match(r"^\s*0042\s*=", lines[i]):
            lines[i] = f"0042 = {shot_dir}"
            shot_dir = None
    if shot_dir:
        pending["0042"] = shot_dir
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1   # keep blank lines before the next section where they were
    for key in sorted(pending):
        lines.insert(insert_at, f"{key} = {pending[key]}")
        insert_at += 1
    lines = _borderless_startpos(lines, values["window_mode"] == 3)
    with open(ini_path, "w", encoding="utf-8", newline="") as f:
        f.write(newline.join(lines) + newline)


def apply_shot_dir(ini_path, game_dir):
    """Only key 0042 (the game folder, where PrintScreen saves) in a boot file's [ffxi.registry]; nothing else changes.
    For the boot files that do not get the Graphics page's values: the GM game and the second character (Abbot,
    2026-11-19: PrintScreen still froze the game on his GM account). True when the file was changed."""
    shot_dir = game_dir_value(game_dir)
    if not shot_dir or not ini_path or not os.path.exists(ini_path):
        return False
    with open(ini_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    start, end = _section_bounds(lines)
    if start is None:
        return False
    want = f"0042 = {shot_dir}"
    for i in range(start + 1, end):
        if re.match(r"^\s*0042\s*=", lines[i]):
            if lines[i].strip() == want:
                return False
            lines[i] = want
            break
    else:
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, want)
    with open(ini_path, "w", encoding="utf-8", newline="") as f:
        f.write(newline.join(lines) + newline)
    return True


def _borderless_startpos(lines, borderless):
    """A borderless window starts at the screen's top-left corner (x = 0, y = 0 in [ashita.window.startpos]); otherwise
    Ashita's default (-1: centred). Only the launcher's own values (-1 or 0) are changed, never a position someone set."""
    want = "0" if borderless else "-1"
    inside = False
    for i, line in enumerate(lines):
        head = line.strip().lower()
        if head.startswith("["):
            inside = head == "[ashita.window.startpos]"
            continue
        m = re.match(r"^(\s*)([xy])(\s*=\s*)(-?\d+)(.*)$", line) if inside else None
        if m and m.group(4) in ("-1", "0"):
            lines[i] = f"{m.group(1)}{m.group(2)}{m.group(3)}{want}{m.group(5)}"
    return lines


def restore_graphics(ini_path):
    backup = ini_path + ".before-graphics"
    if not os.path.exists(backup):
        return False
    shutil.copy2(backup, ini_path)
    return True


def aspect_warning(values):
    """The menu and the screen should have the same shape, or the game can crash or look stretched."""
    try:
        screen = values["screen_w"] / values["screen_h"]
        menu = values["menu_w"] / values["menu_h"]
    except (KeyError, ZeroDivisionError):
        return ""
    if abs(screen - menu) > 0.02:
        return "The menu resolution is a different shape from the screen resolution. That can make the game crash or look stretched."
    return ""


def graphics_path(here):
    return os.path.join(here, "graphics.json")


def load_graphics(here, ini_path=None):
    """Saved choices if there are any, otherwise whatever the boot file says now."""
    try:
        with open(graphics_path(here), "r", encoding="utf-8-sig") as f:
            return clean_graphics(json.load(f))
    except (OSError, ValueError):
        return read_boot_graphics(ini_path) if ini_path else dict(GRAPHICS_DEFAULTS)


def save_graphics(here, values):
    with open(graphics_path(here), "w", encoding="utf-8") as f:
        json.dump(clean_graphics(values), f, indent=2)


# ---------- graphics mod: dgVoodoo + ReShade, installed next to pol.exe ----------
GFX_DGVOODOO_FILES = ("D3D8.dll", "D3DImm.dll", "DDraw.dll", "dgVoodoo.conf", "dgVoodooCpl.exe")   # the last one is dgVoodoo's own settings window
GFX_RESHADE_FILES = ("dxgi.dll", "ReShade.ini", "ReShadePreset.ini", "DefaultPreset.ini")
GFX_RESHADE_DIRS = ("reshade-shaders", "reshade-presets")
GFX_HOOK_DLLS = ("D3D8.dll", "D3DImm.dll", "DDraw.dll", "dxgi.dll")     # the ones switched off/on by renaming
GFX_SETTINGS_EXT = (".ini", ".conf")                                     # never overwritten on a plain update
POL_FOLDER_DEFAULT = r"C:\Program Files (x86)\PlayOnline\SquareEnix\PlayOnlineViewer"


def gfx_state_path(here):
    return os.path.join(here, "gfxmod.json")


def gfx_default_state():
    return {"dgvoodoo": "", "reshade": "", "target": "", "installed": {"files": [], "dirs": []}, "backups": {}}


def gfx_load(here):
    state = gfx_default_state()
    try:
        with open(gfx_state_path(here), "r", encoding="utf-8-sig") as f:
            saved = json.load(f)
        for key in ("dgvoodoo", "reshade", "target"):
            state[key] = str(saved.get(key, ""))
        installed = saved.get("installed", {})
        state["installed"] = {"files": list(installed.get("files", [])), "dirs": list(installed.get("dirs", []))}
        state["backups"] = dict(saved.get("backups", {}))
    except (OSError, ValueError):
        pass
    return state


def gfx_save(here, state):
    with open(gfx_state_path(here), "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def gfx_find_target(cfg_target="", ashita_dir=""):
    """The folder of the loader that starts the game (xiloader.exe / pol.exe): the game loads dgVoodoo and ReShade from there.
    With Ashita that is Ashita's own bootloader folder, the same layout HorizonXI uses."""
    candidates = [cfg_target]
    if ashita_dir:
        candidates.append(os.path.join(ashita_dir, "bootloader"))
    candidates.append(POL_FOLDER_DEFAULT)
    for candidate in candidates:
        if candidate and (os.path.exists(os.path.join(candidate, "xiloader.exe")) or os.path.exists(os.path.join(candidate, "pol.exe"))):
            return candidate
    return cfg_target or ""


def gfx_dgvoodoo_sources(folder):
    """Where each dgVoodoo file is: the folder itself, or the official package's MS\\x86 folder for the DLLs."""
    found = {}
    for name in GFX_DGVOODOO_FILES:
        for sub in ("", os.path.join("MS", "x86")):
            path = os.path.join(folder, sub, name)
            if folder and os.path.isfile(path):
                found[name] = path
                break
    return found


GFX_OUTPUT_APIS = {
    "bestavailable": "best available (usually Direct3D 11)",
    "direct3d11_fl10_0": "Direct3D 11 (feature level 10.0)",
    "direct3d11_fl11_0": "Direct3D 11 (feature level 11.0)",
    "direct3d12_fl11_0": "Direct3D 12 (feature level 11.0)",
    "direct3d12_fl12_0": "Direct3D 12 (feature level 12.0)",
}


def gfx_read_output_api(folder):
    """What dgVoodoo.conf in that folder says dgVoodoo draws with. Returns readable text, or '' if the file or the setting is not there."""
    try:
        with open(os.path.join(folder, "dgVoodoo.conf"), "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                m = re.match(r"^\s*OutputAPI\s*=\s*([A-Za-z0-9_]+)", line)
                if m:
                    return GFX_OUTPUT_APIS.get(m.group(1).lower(), m.group(1))
    except OSError:
        pass
    return ""


def gfx_guess_sources():
    """Looks for the usual places a dgVoodoo or ReShade folder gets left (Desktop). Returns (dgvoodoo, reshade) or empty strings."""
    home = os.path.expanduser("~")
    desktops = [os.path.join(home, "Desktop"), os.path.join(home, "OneDrive", "Desktop")]
    dg, rs = "", ""
    # a HorizonXI install keeps the finished set in its bootloader folder: the best place to copy from
    for horizon in (os.path.join("C:\\", "Games", "Horizonxi", "HorizonXI", "Game", "bootloader"),
                    os.path.join(home, "Games", "Horizonxi", "HorizonXI", "Game", "bootloader")):
        if os.path.isfile(os.path.join(horizon, "D3D8.dll")) and os.path.isfile(os.path.join(horizon, "dxgi.dll")):
            return horizon, horizon
    for desktop in desktops:
        for name in ("dgvoodoo", "dgvoodoo2"):
            folder = os.path.join(desktop, name)
            if not dg and "D3D8.dll" in gfx_dgvoodoo_sources(folder):
                dg = folder
        for name in ("reshadesetup", "reshade"):
            folder = os.path.join(desktop, name)
            if not rs and os.path.isfile(os.path.join(folder, "dxgi.dll")):
                rs = folder
    return dg, rs


def _off(path):
    return path + ".off"


def gfx_install(here, state, reset_settings=False):
    """Copies the chosen dgVoodoo and ReShade files next to pol.exe. Anything of yours that would be overwritten is saved
    first. Your current settings files (.ini, .conf) are kept unless reset_settings is True. Returns a list of messages."""
    target = state["target"]
    if not target or not os.path.isdir(target):
        raise RuntimeError("The game folder (the one with pol.exe) was not found.")
    notes = []
    backup_dir = os.path.join(here, "gfxmod-backup")
    os.makedirs(backup_dir, exist_ok=True)
    installed_files, installed_dirs = state["installed"]["files"], state["installed"]["dirs"]

    plan = []   # (destination name, source path)
    if state["dgvoodoo"]:
        sources = gfx_dgvoodoo_sources(state["dgvoodoo"])
        if "D3D8.dll" not in sources:
            raise RuntimeError("No D3D8.dll in the dgVoodoo folder (looked in the folder and its MS\\x86 subfolder).")
        plan += list(sources.items())
    if state["reshade"]:
        if not os.path.isfile(os.path.join(state["reshade"], "dxgi.dll")):
            raise RuntimeError("No dxgi.dll (ReShade) in the ReShade folder.")
        for name in GFX_RESHADE_FILES:
            path = os.path.join(state["reshade"], name)
            if os.path.isfile(path):
                plan.append((name, path))
    if not plan:
        raise RuntimeError("Choose a dgVoodoo folder, a ReShade folder, or both.")

    for name, source in plan:
        if os.path.normcase(os.path.dirname(source)) == os.path.normcase(target):
            continue
        dest = os.path.join(target, name)
        is_settings = name.lower().endswith(GFX_SETTINGS_EXT)
        if os.path.exists(_off(dest)) and name in GFX_HOOK_DLLS:
            os.remove(_off(dest))                      # installing turns it on
        if os.path.exists(dest):
            if name not in installed_files and name not in state["backups"]:
                shutil.copy2(dest, os.path.join(backup_dir, name))
                state["backups"][name] = name
                notes.append(f"Saved your existing {name} to the backup folder.")
            elif is_settings and not reset_settings:
                notes.append(f"Kept your current {name}.")
                if name not in installed_files:
                    installed_files.append(name)
                continue
        shutil.copy2(source, dest)
        if name not in installed_files:
            installed_files.append(name)
        notes.append(f"Copied {name}.")

    if state["reshade"]:
        for dirname in GFX_RESHADE_DIRS:
            source = os.path.join(state["reshade"], dirname)
            if not os.path.isdir(source):
                continue
            dest = os.path.join(target, dirname)
            if os.path.exists(dest) and dirname not in installed_dirs and not os.path.exists(dest + ".before-launcher"):
                os.rename(dest, dest + ".before-launcher")
                notes.append(f"Moved your existing {dirname} folder to {dirname}.before-launcher.")
            shutil.copytree(source, dest, dirs_exist_ok=True)
            if dirname not in installed_dirs:
                installed_dirs.append(dirname)
            notes.append(f"Copied the {dirname} folder.")
        if not os.path.isdir(os.path.join(state["reshade"], "reshade-shaders")) and not os.path.isdir(os.path.join(target, "reshade-shaders")):
            notes.append("There is no reshade-shaders folder, so the effects in your preset may not load. "
                         "Put the shader files in a folder named reshade-shaders next to your ReShade files and install again.")
    return notes


def gfx_set_enabled(state, enabled):
    """Turns the mod on or off by renaming the DLLs (nothing is deleted)."""
    target = state["target"]
    changed = 0
    for name in state["installed"]["files"]:
        if name not in GFX_HOOK_DLLS:
            continue
        on, off = os.path.join(target, name), _off(os.path.join(target, name))
        if enabled and os.path.exists(off):
            if os.path.exists(on):
                os.remove(on)
            os.rename(off, on)
            changed += 1
        elif not enabled and os.path.exists(on):
            if os.path.exists(off):
                os.remove(off)
            os.rename(on, off)
            changed += 1
    return changed


def gfx_status(state):
    files = state["installed"]["files"]
    if not files:
        return "Not installed"
    hooks = [n for n in files if n in GFX_HOOK_DLLS]
    on = sum(os.path.exists(os.path.join(state["target"], n)) for n in hooks)
    off = sum(os.path.exists(_off(os.path.join(state["target"], n))) for n in hooks)
    if on and not off:
        return "Installed - ON"
    if off and not on:
        return "Installed - OFF"
    if on and off:
        return "Installed - partly on (use Turn ON or Turn OFF)"
    return "Installed, but the files are missing - install again"


def gfx_uninstall(here, state):
    """Removes only what the launcher added and puts your own files back."""
    target = state["target"]
    notes = []
    backup_dir = os.path.join(here, "gfxmod-backup")
    for name in state["installed"]["files"]:
        for path in (os.path.join(target, name), _off(os.path.join(target, name))):
            if os.path.exists(path):
                os.remove(path)
        if name in state["backups"]:
            saved = os.path.join(backup_dir, state["backups"][name])
            if os.path.exists(saved):
                shutil.copy2(saved, os.path.join(target, name))
                notes.append(f"Put your original {name} back.")
        notes.append(f"Removed {name}.")
    for dirname in state["installed"]["dirs"]:
        path = os.path.join(target, dirname)
        if os.path.isdir(path):
            shutil.rmtree(path)
        if os.path.isdir(path + ".before-launcher"):
            os.rename(path + ".before-launcher", path)
            notes.append(f"Put your original {dirname} folder back.")
        notes.append(f"Removed the {dirname} folder.")
    state["installed"] = {"files": [], "dirs": []}
    state["backups"] = {}
    return notes


def gfx_check_shaders(target):
    """Compares the shader folders ReShade.ini looks in with what is really there.
    Returns None if there is no ReShade.ini, else (folders_found, folders_total, missing_names, fx_file_count)."""
    ini = os.path.join(target, "ReShade.ini")
    try:
        with open(ini, "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r"(?mi)^EffectSearchPaths\s*=\s*(.*)$", text)
    if not m:
        return (0, 0, [], 0)
    found, missing, fx = 0, [], 0
    entries = [e.strip() for e in m.group(1).split(",") if e.strip()]
    for entry in entries:
        path = entry.replace("\\", "/").rstrip("*").rstrip("/")
        if path.startswith("./"):
            path = path[2:]
        full = path if os.path.isabs(path) else os.path.join(target, *path.split("/"))
        if os.path.isdir(full):
            found += 1
            fx += sum(1 for name in os.listdir(full) if name.lower().endswith(".fx"))
        else:
            missing.append(path.split("/")[-1] or path)
    return (found, len(entries), missing, fx)


def gfx_ini_add_paths(target, effect_paths=(), texture_paths=()):
    """Makes sure ReShade.ini searches the given folders (a backup is saved once as ReShade.ini.before-launcher)."""
    ini = os.path.join(target, "ReShade.ini")
    if not os.path.isfile(ini):
        return False
    with open(ini, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines()
    if not os.path.exists(ini + ".before-launcher"):
        shutil.copy2(ini, ini + ".before-launcher")

    def merge(key, wanted):
        for i, line in enumerate(lines):
            m = re.match(r"^" + key + r"=(.*)$", line)
            if m:
                have = [e for e in m.group(1).split(",") if e.strip()]
                norm = {e.strip().rstrip("\\*").lower() for e in have}
                for path in wanted:
                    if path.rstrip("\\*").lower() not in norm and path.lower() not in {e.strip().lower() for e in have}:
                        have.append(path)
                lines[i] = key + "=" + ",".join(have)
                return
        for i, line in enumerate(lines):          # key missing: add it under [GENERAL]
            if line.strip().upper() == "[GENERAL]":
                lines.insert(i + 1, key + "=" + ",".join(wanted))
                return
        lines.append(key + "=" + ",".join(wanted))

    if effect_paths:
        merge("EffectSearchPaths", list(effect_paths))
    if texture_paths:
        merge("TextureSearchPaths", list(texture_paths))
    with open(ini, "w", encoding="utf-8", newline="") as f:
        f.write(newline.join(lines) + newline)
    return True


def _count_files(folder, extensions=None):
    total = 0
    for _root, _dirs, files in os.walk(folder):
        total += sum(1 for n in files if not extensions or n.lower().endswith(extensions))
    return total


def gfx_add_shaders(state, folder):
    """Adds shaders from a folder. Two kinds of folder work:
    - a reshade-shaders folder (it has Shaders and Textures inside): merged into the game's reshade-shaders folder;
    - a loose folder of .fx files: copied to reshade-shaders\\Shaders\\<folder name>, and ReShade.ini is told to search it.
    Nothing already there is deleted. Returns a list of messages."""
    target = state["target"]
    if not target or not os.path.isdir(target):
        raise RuntimeError("The loader folder was not found.")
    if not folder or not os.path.isdir(folder):
        raise RuntimeError("Choose a folder that holds shaders.")
    dest = os.path.join(target, "reshade-shaders")
    existed = os.path.isdir(dest)
    before = _count_files(dest) if existed else 0

    source = folder
    if not os.path.isdir(os.path.join(source, "Shaders")):
        inner = os.path.join(folder, "reshade-shaders")
        if os.path.isdir(os.path.join(inner, "Shaders")):
            source = inner
    if os.path.isdir(os.path.join(source, "Shaders")):
        if os.path.normcase(os.path.abspath(source)) == os.path.normcase(os.path.abspath(dest)):
            raise RuntimeError("That is already the game's own reshade-shaders folder.")
        shutil.copytree(source, dest, dirs_exist_ok=True)
        notes = [f"Added the shaders from {source}."]
    else:
        fx = _count_files(folder, (".fx", ".fxh"))
        if fx == 0:
            raise RuntimeError("No shader files (.fx) were found in that folder.")
        name = os.path.basename(os.path.normpath(folder)) or "Added"
        loose_shaders = os.path.join(dest, "Shaders", name)
        if os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(loose_shaders)):
            raise RuntimeError("That folder is already inside the game's reshade-shaders folder.")
        os.makedirs(os.path.dirname(loose_shaders), exist_ok=True)
        shutil.copytree(folder, loose_shaders, dirs_exist_ok=True)
        effect_paths = [".\\reshade-shaders\\Shaders\\" + name + "\\**"]
        texture_paths = []
        textures = os.path.join(os.path.dirname(os.path.normpath(folder)), "Textures")
        if os.path.isdir(textures) and os.path.normcase(os.path.basename(os.path.normpath(folder))) == os.path.normcase("Shaders"):
            shutil.copytree(textures, os.path.join(dest, "Textures", name), dirs_exist_ok=True)
            texture_paths.append(".\\reshade-shaders\\Textures\\" + name + "\\**")
        updated = gfx_ini_add_paths(target, effect_paths, texture_paths)
        notes = [f"Copied {fx} shader file(s) from {folder} into reshade-shaders\\Shaders\\{name}."]
        notes.append("ReShade.ini now searches that folder." if updated else "There is no ReShade.ini yet, so ReShade is not told about the new folder.")
    after = _count_files(dest)
    if not existed and "reshade-shaders" not in state["installed"]["dirs"]:
        state["installed"]["dirs"].append("reshade-shaders")
    notes.append(f"The game's reshade-shaders folder now holds {after} files ({after - before} new).")
    return notes


def gfx_unsearched_shader_folders(target):
    """Shader folders that exist under reshade-shaders but that ReShade.ini does not search, so their effects never show up.
    Returns a list of (folder name, shader file count)."""
    shaders = os.path.join(target, "reshade-shaders", "Shaders")
    if not os.path.isdir(shaders):
        return []
    searched, recursive = set(), set()
    try:
        with open(os.path.join(target, "ReShade.ini"), "r", encoding="utf-8-sig", errors="replace") as f:
            m = re.search(r"(?mi)^EffectSearchPaths\s*=\s*(.*)$", f.read())
        if m:
            for entry in m.group(1).split(","):
                raw = entry.strip().replace("\\", "/")
                path = raw.rstrip("*").rstrip("/").lower()
                if path.startswith("./"):
                    path = path[2:]
                searched.add(path)
                if raw.endswith("**"):
                    recursive.add(path)       # a "folder\**" entry also covers everything inside that folder
    except OSError:
        return []
    result = []
    for name in sorted(os.listdir(shaders)):
        folder = os.path.join(shaders, name)
        if not os.path.isdir(folder):
            continue
        key = "reshade-shaders/shaders/" + name.lower()
        covered = key in searched or any(key.startswith(root + "/") for root in recursive)
        count = _count_files(folder, (".fx",))
        if not covered and count:
            result.append((name, count))
    return result


def gfx_fix_search_paths(target):
    """Adds every shader and texture folder that exists to the search lists in ReShade.ini. Returns the list of folders added."""
    unsearched = gfx_unsearched_shader_folders(target)
    effect_paths = [".\\reshade-shaders\\Shaders\\" + name + "\\**" for name, _count in unsearched]
    texture_paths = []
    textures = os.path.join(target, "reshade-shaders", "Textures")
    if os.path.isdir(textures):
        try:
            with open(os.path.join(target, "ReShade.ini"), "r", encoding="utf-8-sig", errors="replace") as f:
                m = re.search(r"(?mi)^TextureSearchPaths\s*=\s*(.*)$", f.read())
            have = {e.strip().replace("\\", "/").rstrip("*").rstrip("/").lower().lstrip("./") for e in (m.group(1).split(",") if m else [])}
        except OSError:
            have = set()
        for name in sorted(os.listdir(textures)):
            if os.path.isdir(os.path.join(textures, name)) and ("reshade-shaders/textures/" + name.lower()) not in have:
                texture_paths.append(".\\reshade-shaders\\Textures\\" + name + "\\**")
    if effect_paths or texture_paths:
        if not gfx_ini_add_paths(target, effect_paths, texture_paths):
            raise RuntimeError("There is no ReShade.ini in the loader folder.")
    return [p.rstrip("\\*") for p in effect_paths + texture_paths]


def polplugin_on(boot_ini, name):
    """True when Ashita's boot file loads the PlayOnline-stage plugin `name` ([ashita.polplugins] name = 1)."""
    try:
        with open(boot_ini, encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return False
    section = re.search(r"(?ms)^\[ashita\.polplugins\]\s*$(.*?)(?=^\[|\Z)", text)
    if not section:
        return False
    m = re.search(r"(?mi)^\s*" + re.escape(name) + r"\s*=\s*(\S+)", section.group(1))
    return bool(m) and m.group(1) not in ("0", "false", "False")


def set_polplugin(boot_ini, name, on):
    """Turns a PlayOnline-stage plugin (XIPivot = 'pivot') on or off in Ashita's boot file. Other lines untouched."""
    with open(boot_ini, encoding="utf-8-sig", errors="replace") as handle:
        text = handle.read()
    value = "1" if on else "0"
    section = re.search(r"(?ms)^\[ashita\.polplugins\]\s*$(.*?)(?=^\[|\Z)", text)
    if not section:
        text = text.rstrip("\n") + f"\n\n[ashita.polplugins]\n{name} = {value}\n"
    else:
        body = section.group(1)
        pattern = r"(?mi)^(\s*" + re.escape(name) + r"\s*=\s*)\S*"
        if re.search(pattern, body):
            body = re.sub(pattern, lambda m: m.group(1) + value, body, count=1)
        else:
            body = f"\n{name} = {value}" + body if not body.startswith("\n") else f"\n{name} = {value}" + body
        text = text[:section.start(1)] + body + text[section.end(1):]
    with open(boot_ini, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)


def pivot_first_config(ashita_dir):
    """XIPivot's README: the first time, config/pivot/pivot.sample.ini becomes pivot.ini. Never replaces a pivot.ini."""
    folder = os.path.join(ashita_dir, "config", "pivot")
    target, sample = os.path.join(folder, "pivot.ini"), os.path.join(folder, "pivot.sample.ini")
    if os.path.exists(sample) and not os.path.exists(target):
        shutil.copyfile(sample, target)
        return True
    return False
