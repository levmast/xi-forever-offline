"""Linux and Steam Deck support for the XI: Forever Offline launcher (no GUI code here, so it can be tested on its own).

On Linux the game server, the database (MariaDB's own Linux build) and the launcher run natively. Only the game itself
(PlayOnline, FINAL FANTASY XI, Ashita, xiloader and our addons) is a Windows program: it runs through Proton, started
with umu (the standard way to run Proton outside Steam, also used by Lutris and Heroic). Everything stays inside the
install folder:

    proton/GE-Proton<version>/   Proton itself (GE-Proton, downloaded at setup)
    proton/umu/umu-run           umu (a small Python program)
    proton/runtime/              the Steam Linux Runtime umu downloads the first time
    prefix/                      the game's own Windows "drive" (a Wine prefix): nothing else uses it

PlayOnline and FINAL FANTASY XI are registered inside that prefix only, from the registry and COM data Ashita ships for
its Sandbox plugin (config/sandbox/sandbox.registry.ini). So there is no administrator prompt and no switching of the
registry before and after playing, as there is on Windows.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

IS_LINUX = sys.platform.startswith("linux")
PROTON_DIR = "proton"
PREFIX_DIR = "prefix"
UMU_RELATIVE = os.path.join(PROTON_DIR, "umu", "umu-run")
PREFIX_STAMP = "xiforever-prefix.json"
REGISTRY_FILE = "xiforever-game.reg"
DESKTOP_ID = "xi-forever-offline"
APP_NAME = "XI: Forever Offline"


# ----- what machine is this -----
def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def is_steam_deck(os_release=None, board=None, env=None):
    """True on a Steam Deck (SteamOS, or another system on Deck hardware: boards Jupiter = LCD, Galileo = OLED)."""
    env = os.environ if env is None else env
    if env.get("SteamDeck") == "1":
        return True
    text = _read("/etc/os-release") if os_release is None else os_release
    if re.search(r"(?m)^ID=\"?steamos\"?\s*$", text):
        return True
    board = _read("/sys/class/dmi/id/board_name") if board is None else board
    return board.strip() in ("Jupiter", "Galileo")


def in_game_mode(env=None):
    """True when started from Steam's Game Mode (gamescope) on the Deck: Steam sets SteamGamepadUI."""
    env = os.environ if env is None else env
    return env.get("SteamGamepadUI") == "1" or env.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope"


def fix_frozen_environment(env=None):
    """The packaged launcher (PyInstaller) points LD_LIBRARY_PATH at its own unpacked libraries. Programs it starts
    (MariaDB, the servers, Python for umu, Proton) must see the system's libraries instead, so put back the value from
    before (LD_LIBRARY_PATH_ORIG), or remove it. The launcher itself already loaded what it needs."""
    env = os.environ if env is None else env
    if not getattr(sys, "frozen", False) and env is os.environ:
        return
    for name in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
        orig = env.get(name + "_ORIG")
        if orig is not None:
            env[name] = orig
        elif name == "LD_LIBRARY_PATH":
            env.pop(name, None)


# ----- processes (/proc) -----
def _proc_table():
    """[(pid, ppid, comm, argv)] for every process we can see."""
    out = []
    try:
        names = os.listdir("/proc")
    except OSError:
        return out
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f"/proc/{pid}/stat", "rb") as handle:
                stat = handle.read().decode("utf-8", "replace")
            comm = stat[stat.index("(") + 1:stat.rindex(")")]
            ppid = int(stat[stat.rindex(")") + 2:].split()[1])
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                argv = [part.decode("utf-8", "replace") for part in handle.read().split(b"\0") if part]
        except (OSError, ValueError, IndexError):
            continue
        out.append((pid, ppid, comm, argv))
    return out


def _names_for(image):
    low = image.lower()
    base = low[:-4] if low.endswith(".exe") else low
    return {base, base + ".exe"}


def matches(image, comm, argv):
    """A process is `image` (xi_map, xiloader...) when its short name or its program file is that name. Wine shows a
    Windows program as e.g. 'xiloader.exe' (short names are cut at 15 letters)."""
    wanted = _names_for(image)
    if comm.lower() in {name[:15] for name in wanted}:
        return True
    if argv:
        first = re.split(r"[\\/]", argv[0])[-1].lower()
        return first in wanted
    return False


def pids_named(image, table=None):
    me = os.getpid()
    return [pid for pid, _pp, comm, argv in (_proc_table() if table is None else table)
            if pid != me and matches(image, comm, argv)]


def pids_where(test, table=None):
    """Processes whose command line (a list) passes test(argv)."""
    me = os.getpid()
    return [pid for pid, _pp, _comm, argv in (_proc_table() if table is None else table) if pid != me and test(argv)]


def descendants(pid, table=None):
    table = _proc_table() if table is None else table
    children = {}
    for p, pp, _c, _a in table:
        children.setdefault(pp, []).append(p)
    out, todo = [], [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in out:
                out.append(child)
                todo.append(child)
    return out


def signal_pids(pids, sig):
    for pid in pids:
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:                                   # a finished child we never waited for is gone too
        with open(f"/proc/{pid}/stat", "rb") as handle:
            return b") Z " not in handle.read()
    except OSError:
        return False


def stop_pids(pids, grace=4.0, sleep=time.sleep):
    """SIGTERM, then SIGKILL whatever is still there after `grace` seconds."""
    pids = [p for p in pids if p != os.getpid()]
    signal_pids(pids, signal.SIGTERM)
    waited = 0.0
    while waited < grace and any(alive(p) for p in pids):
        sleep(0.2)
        waited += 0.2
    signal_pids([p for p in pids if alive(p)], signal.SIGKILL)


def kill_tree(pid, grace=4.0):
    """Stops a process and everything it started (the packaged helpers are a starter and the real program)."""
    stop_pids([pid] + descendants(pid), grace)


# ----- one launcher at a time -----
def lock_path(kit):
    return os.path.join(kit, "logs", "launcher.lock")


def take_lock(kit):
    """Locks the install for this launcher. Returns the open lock (keep it until the launcher closes) or None when
    another launcher holds it. The lock goes away by itself when that launcher's process ends, even after a crash."""
    import fcntl
    os.makedirs(os.path.dirname(lock_path(kit)), exist_ok=True)
    fd = os.open(lock_path(kit), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def lock_holder(kit):
    """The process id written by the launcher that holds the lock, or None."""
    try:
        return int(_read(lock_path(kit)).strip() or 0) or None
    except ValueError:
        return None


# ----- Windows paths for the game -----
def windows_path(path):
    """A Linux path as the game sees it inside Proton: Z: is the whole Linux file system."""
    return "Z:" + os.path.abspath(path).replace("/", "\\")


# ----- Proton and umu -----
def proton_root(kit):
    return os.path.join(kit, PROTON_DIR)


def installed_proton(kit, version=None):
    """The folder of the newest (or the named) Proton in proton/, or None."""
    root = proton_root(kit)
    try:
        names = [n for n in os.listdir(root) if os.path.isfile(os.path.join(root, n, "proton"))]
    except OSError:
        return None
    if version:
        names = [n for n in names if n == version]
    if not names:
        return None
    names.sort(key=lambda n: [int(x) for x in re.findall(r"\d+", n)] or [0])
    return os.path.join(root, names[-1])


def umu_path(kit):
    path = os.path.join(kit, UMU_RELATIVE)
    return path if os.path.isfile(path) else None


def host_python(which=shutil.which, run=subprocess.run):
    """A Python 3.10 or newer on this system (umu needs one), or None."""
    for name in ("python3", "python"):
        exe = which(name)
        if not exe:
            continue
        try:
            out = run([exe, "-c", "import sys; print(sys.version_info[0] * 100 + sys.version_info[1])"],
                      capture_output=True, text=True, errors="replace", timeout=10)
            if int((out.stdout or "0").strip() or 0) >= 310:
                return exe
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
    return None


def umu_command(kit, args, python=None):
    """The command that runs umu-run with args: the system's Python, or the packaged launcher's own (--run)."""
    umu = umu_path(kit)
    if not umu:
        raise RuntimeError("Proton's starter (umu) is not installed yet: run the setup again, or OPTIONS > Get more > umu.")
    python = python if python is not None else host_python()
    if python:
        return [python, umu] + list(args)
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run", umu] + list(args)
    return [sys.executable, umu] + list(args)


def prefix_path(kit):
    return os.path.join(kit, PREFIX_DIR)


def game_env(kit, cfg, base=None):
    """The environment for umu: our prefix, our Proton, umu's runtime inside the install folder."""
    env = dict(os.environ if base is None else base)
    fix_frozen_environment(env)
    proton = installed_proton(kit, cfg.get("proton_version"))
    if not proton:
        raise RuntimeError("Proton is not installed yet: run the setup again, or OPTIONS > Get more > GE-Proton.")
    env.update({
        "WINEPREFIX": prefix_path(kit),
        "PROTONPATH": proton,
        "GAMEID": "umu-default",
        "STORE": "none",
        "UMU_FOLDERS_PATH": os.path.join(proton_root(kit), "runtime"),
        # the whole install folder (game copy, Ashita, prefix) must be visible inside the runtime's container, also
        # when it is on an SD card or a second drive
        "STEAM_COMPAT_LIBRARY_PATHS": os.path.abspath(kit),
        "WINEDEBUG": env.get("WINEDEBUG", "-all"),
    })
    if cfg.get("proton_log"):
        env["PROTON_LOG"] = "1"
        env["PROTON_LOG_DIR"] = os.path.join(kit, "logs")
        env["UMU_LOG"] = "1"
    for key, value in (cfg.get("proton_env") or {}).items():    # extra switches a tester can try in config.json
        env[str(key)] = str(value)
    return env


def run_windows(kit, cfg, args, cwd=None, log_file=None, wait=True, timeout=None, popen=subprocess.Popen):
    """Runs a Windows program (or a Wine tool such as regedit) through umu in our prefix. wait=False returns the
    process; otherwise its exit code."""
    cmd = umu_command(kit, args)
    proc = popen(cmd, cwd=cwd or kit, env=game_env(kit, cfg), stdin=subprocess.DEVNULL,
                 stdout=log_file or subprocess.DEVNULL, stderr=subprocess.STDOUT if log_file else subprocess.DEVNULL,
                 start_new_session=True)
    if not wait:
        return proc
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_tree(proc.pid)
        raise RuntimeError(f"{os.path.basename(args[0])} did not finish in {timeout} seconds.")


# ----- registering the game inside the prefix -----
def _expand(pattern):
    """'(PlayOnline|PlayOnlineUS)\\\\InstallFolder$' -> ['PlayOnline\\InstallFolder', 'PlayOnlineUS\\InstallFolder']
    (the section names in Ashita's sandbox.registry.ini are patterns)."""
    pattern = pattern.rstrip("$")
    match = re.search(r"\(([^()]*)\)", pattern)
    if match:
        out = []
        for choice in match.group(1).split("|"):
            out += _expand(pattern[:match.start()] + choice + pattern[match.end():])
        return out
    text = pattern.replace("\\\\", "\0").replace("\\", "").replace("\0", "\\")
    return [text]


def parse_sandbox_registry(text):
    """Ashita's sandbox.registry.ini -> [(key, [(name, kind, value)])]; kind is 'sz' or 'dword', name '' is the
    default value. Keys are relative: PlayOnline keys go under Software, CLSID keys under Software\\Classes."""
    out, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = []
            for key in _expand(line[1:-1]):
                out.append((key, current))
            continue
        if current is None or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        name = "" if name == "@" else name.strip('"')
        value = value.strip()
        if value.lower().startswith("dword:"):
            current.append((name, "dword", int(value[6:], 16)))
        else:
            current.append((name, "sz", value[1:-1] if len(value) >= 2 and value[0] == value[-1] == '"' else value))
    return out


FALLBACK_REGISTRY = r"""
[(PlayOnline|PlayOnlineUS|PlayOnlineEU)\\InstallFolder$]
0001="{FFXI_PATH}"
1000="{POL_PATH}"
[CLSID\\\{3501F5DD-7894-42DF-866A-A2B6527D8049\}\\InprocServer32$]
@="{POL_PATH}\viewer\com\polcore.dll"
ThreadingModel="Apartment"
[CLSID\\\{07974581-0DF6-4EF0-BD05-604B3ADA9BE9\}\\InprocServer32$]
@="{POL_PATH}\viewer\com\polcore.dll"
ThreadingModel="Apartment"
[CLSID\\\{E5966FB3-C97B-42EB-84BF-37F95EE54A9F\}\\InprocServer32$]
@="{POL_PATH}\viewer\com\polcoreeu.dll"
ThreadingModel="Apartment"
[CLSID\\\{989D790D-6236-11D4-80E9-00105A81E890\}\\InprocServer32$]
@="{FFXI_PATH}\ffxi.dll"
[CLSID\\\{0DF0E951-D03C-4A94-90EF-40AE60668F5F\}\\InprocServer32$]
@="{FFXI_PATH}\ffxi.dll"
[CLSID\\\{1027DC46-750D-4B1F-8834-1D25B8BEBAB8\}\\InprocServer32$]
@="{FFXI_PATH}\ffximain.dll"
"""


def _reg_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def registry_file_text(sandbox_text, paths):
    """A .reg file (for the 32-bit regedit inside the prefix) that registers PlayOnline and FFXI at `paths`
    (pol, ffxi, common, tetra: Windows paths)."""
    fill = {"{POL_PATH}": paths["pol"], "{FFXI_PATH}": paths["ffxi"], "{COMMON_PATH}": paths.get("common", ""),
            "{TETRA_PATH}": paths.get("tetra", "")}
    lines = ["Windows Registry Editor Version 5.00", ""]
    for key, values in parse_sandbox_registry(sandbox_text):
        root = "HKEY_LOCAL_MACHINE\\Software\\Classes\\" if key.upper().startswith("CLSID\\") else "HKEY_LOCAL_MACHINE\\Software\\"
        lines.append(f"[{root}{key}]")
        for name, kind, value in values:
            label = "@" if name == "" else _reg_string(name)
            if kind == "dword":
                lines.append(f"{label}=dword:{value:08x}")
            else:
                for marker, real in fill.items():
                    value = value.replace(marker, real)
                lines.append(f"{label}={_reg_string(value)}")
        lines.append("")
    return "\r\n".join(lines) + "\r\n"


def sandbox_registry_text(ashita_dir):
    text = _read(os.path.join(ashita_dir, "config", "sandbox", "sandbox.registry.ini"))
    return text if "InstallFolder" in text else FALLBACK_REGISTRY


def game_paths(cfg, kit):
    """Windows paths for the registry: PlayOnline, FFXI, Common Files, TetraMaster."""
    ffxi = cfg["ffxi_client_dir"]
    pol = cfg.get("pol_dir") or os.path.join(os.path.dirname(os.path.normpath(ffxi)), "PlayOnlineViewer")
    tetra = os.path.join(os.path.dirname(os.path.normpath(ffxi)), "TetraMaster")
    return {"pol": windows_path(pol), "ffxi": windows_path(ffxi), "tetra": windows_path(tetra),
            "common": "C:\\Program Files (x86)\\Common Files"}


def prefix_state(kit):
    try:
        with open(os.path.join(prefix_path(kit), PREFIX_STAMP), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def wanted_state(kit, cfg):
    paths = game_paths(cfg, kit)
    return {"paths": paths, "proton": os.path.basename(installed_proton(kit, cfg.get("proton_version")) or ""),
            "registry": len(sandbox_registry_text(cfg.get("ashita_dir", "")))}


def prepare_prefix(kit, cfg, log=print, run=None):
    """Makes the prefix (first time) and registers the game in it. Done again only when the game folder, Proton or
    Ashita's registry data changed, so PLAY normally skips it. Returns True when something was done."""
    run = run or (lambda args, **kw: run_windows(kit, cfg, args, **kw))
    want = wanted_state(kit, cfg)
    if prefix_state(kit) == want and os.path.isdir(os.path.join(prefix_path(kit), "drive_c")):
        return False
    os.makedirs(prefix_path(kit), exist_ok=True)
    os.makedirs(os.path.join(kit, "logs"), exist_ok=True)
    with open(os.path.join(kit, "logs", "proton-setup.log"), "ab") as out:
        if not os.path.isdir(os.path.join(prefix_path(kit), "drive_c")):
            log("Making the game's Windows folder (Proton's first start downloads its runtime, a few minutes)...")
            code = run(["createprefix"], log_file=out, timeout=1800)
            if not os.path.isdir(os.path.join(prefix_path(kit), "drive_c")):
                raise RuntimeError(f"Proton could not make the game's Windows folder (code {code}); see logs/proton-setup.log.")
        log("Registering PlayOnline and FINAL FANTASY XI inside it...")
        reg = os.path.join(prefix_path(kit), REGISTRY_FILE)
        with open(reg, "w", encoding="utf-16", newline="") as handle:
            handle.write(registry_file_text(sandbox_registry_text(cfg.get("ashita_dir", "")), want["paths"]))
        regedit = os.path.join(prefix_path(kit), "drive_c", "windows", "syswow64", "regedit.exe")
        tool = regedit if os.path.isfile(regedit) else "regedit"        # 32-bit regedit: the game is 32-bit
        code = run([tool, "/S", windows_path(reg)], log_file=out, timeout=300)
        if code not in (0, None):
            raise RuntimeError(f"Registering the game in Proton failed (code {code}); see logs/proton-setup.log.")
    with open(os.path.join(prefix_path(kit), PREFIX_STAMP), "w", encoding="utf-8") as handle:
        json.dump(want, handle, indent=1)
    return True


# ----- starting the game -----
def start_game(kit, cfg, ashita_dir, boot, log_file, popen=subprocess.Popen):
    """Starts Ashita (Ashita-cli.exe <boot file>) through Proton. Returns umu's process: it stays until every program in
    the prefix has closed."""
    cli = os.path.join(ashita_dir, "Ashita-cli.exe")
    if not os.path.isfile(cli):
        raise RuntimeError(f"Missing {cli}")
    return run_windows(kit, cfg, [cli, boot], cwd=ashita_dir, log_file=log_file, wait=False, popen=popen)


def game_running(proc=None):
    """True while xiloader runs (seen from Linux as 'xiloader.exe'), or while umu's process is still up."""
    if pids_named("xiloader"):
        return True
    return proc is not None and proc.poll() is None


def stop_game(kit):
    """Ends every program in our prefix (wineserver -k through Proton's own wine)."""
    for pid in pids_named("xiloader") + pids_named("Ashita-cli"):
        signal_pids([pid], signal.SIGTERM)
    proton = installed_proton(kit)
    wineserver = os.path.join(proton, "files", "bin", "wineserver") if proton else None
    if wineserver and os.path.isfile(wineserver):
        env = dict(os.environ)
        fix_frozen_environment(env)
        env["WINEPREFIX"] = prefix_path(kit)
        try:
            subprocess.run([wineserver, "-k"], env=env, timeout=15, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            pass


# ----- Ashita on Linux -----
WINE_PLUGINS = ("winefix",)      # Ashita's own fix for a Wine hitch (PlayOnline polls network statistics every second)


def wine_plugin_lines(ashita_dir):
    return [f"/load {name}" for name in WINE_PLUGINS
            if os.path.isfile(os.path.join(ashita_dir, "plugins", name + ".dll"))]


def ensure_wine_plugins(manager):
    """Adds winefix to the launcher's Ashita script (core.ScriptManager) when it isn't there. Returns what was added."""
    added = []
    have = manager.enabled("plugin")
    for name in WINE_PLUGINS:
        if name not in have and os.path.isfile(os.path.join(manager.ashita, "plugins", name + ".dll")):
            manager.set("plugin", name, True)
            added.append(name)
    return added


SANDBOX_BEGIN = "; >>> XI: Forever Offline (Linux): Ashita's Sandbox finds the game"
SANDBOX_END = "; <<< XI: Forever Offline (Linux)"


def set_sandbox(boot_ini, cfg, on):
    """Optional (config.json "linux_sandbox": true): Ashita's Sandbox plugin answers the game's registry and COM
    questions itself, instead of the prefix's registry. A second way in, for testers, if registering doesn't work."""
    import launcher_core as core
    core.set_polplugin(boot_ini, "sandbox", on)
    with open(boot_ini, encoding="utf-8-sig", errors="replace") as handle:
        text = handle.read()
    begin, end = text.find(SANDBOX_BEGIN), text.find(SANDBOX_END)
    if begin >= 0 and end > begin:
        text = text[:begin].rstrip("\n") + "\n" + text[end + len(SANDBOX_END):].lstrip("\n")
    if on:
        ffxi = cfg["ffxi_client_dir"]
        pol = cfg.get("pol_dir") or os.path.join(os.path.dirname(os.path.normpath(ffxi)), "PlayOnlineViewer")
        text = (text.rstrip("\n") + f"\n\n{SANDBOX_BEGIN}\n[sandbox.paths]\ncommon = C:\\Program Files (x86)\\Common Files\n"
                f"pol    = {windows_path(pol)}\nffxi   = {windows_path(ffxi)}\n{SANDBOX_END}\n")
    with open(boot_ini, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)


# ----- Steam Deck screen -----
DECK_GRAPHICS = {"screen_w": 1280, "screen_h": 800, "menu_w": 1280, "menu_h": 800, "window_mode": 3,
                 "bg_w": 2048, "bg_h": 2048}      # the Deck's own screen, borderless; the "Balanced" background size


def deck_defaults(kit, boot_ini):
    """Steam Deck: the game at the Deck's screen size (graphics.json and the boot file). Returns the values."""
    import launcher_core as core
    values = core.load_graphics(kit, boot_ini if os.path.exists(boot_ini) else None)
    values.update(DECK_GRAPHICS)
    core.save_graphics(kit, values)
    if os.path.exists(boot_ini):
        core.apply_graphics(boot_ini, values)
    return values


# ----- the game copy (Linux: from a folder) -----
def find_game_parts(folder):
    """Given the folder a player picked (SquareEnix, FINAL FANTASY XI or the folder above SquareEnix), returns
    (ffxi, viewer) or (None, None). Looks one or two levels down, letter case ignored."""
    def child(parent, name):
        try:
            for entry in os.listdir(parent):
                if entry.lower() == name.lower() and os.path.isdir(os.path.join(parent, entry)):
                    return os.path.join(parent, entry)
        except OSError:
            pass
        return None

    folder = os.path.normpath(folder or "")
    candidates = [folder, os.path.dirname(folder)]
    for base in list(candidates):
        for name in ("SquareEnix", "PlayOnline"):
            sub = child(base, name)
            if sub:
                candidates.append(sub)
                deeper = child(sub, "SquareEnix")
                if deeper:
                    candidates.append(deeper)
    for base in candidates:
        if os.path.isfile(os.path.join(base, "FFXiMain.dll")):          # the FFXI folder itself
            viewer = child(os.path.dirname(base), "PlayOnlineViewer")
            return base, viewer
        ffxi = child(base, "FINAL FANTASY XI")
        if ffxi and os.path.isfile(os.path.join(ffxi, "FFXiMain.dll")):
            return ffxi, child(base, "PlayOnlineViewer")
    return None, None


def detect_lang(viewer):
    """EU when PlayOnline's EU core is there, else US (the registry has entries for every language anyway)."""
    for root, _dirs, files in os.walk(viewer or ""):
        if "patchfiles" in root.lower():
            continue
        if any(f.lower() == "polcoreeu.dll" for f in files):
            return "EU"
    return "US"


def game_lang(cfg):
    """JP, US or EU for xiloader: the setup's choice when it is not US, else EU when the copy has only the EU core."""
    lang = (cfg.get("pol_lang") or "US").upper()
    if lang in ("JP", "EU"):
        return lang
    viewer = cfg.get("pol_dir") or os.path.join(os.path.dirname(os.path.normpath(cfg.get("ffxi_client_dir", ""))), "PlayOnlineViewer")
    if detect_lang(viewer) == "EU" and not any(f.lower() == "polcore.dll" for _r, _d, fs in os.walk(viewer)
                                               if "patchfiles" not in _r.lower() for f in fs):
        return "EU"
    return "US"


def apply_boot_lang(boot_ini, lang):
    """(2026-11-18, Sunie: an EU install on Linux) xiloader looks for the US PlayOnline unless told otherwise, and an EU
    install has only polcoreeu.dll. Writes --lang into the boot file's command line and Ashita's [ashita.language]
    playonline (1 JP, 2 US, 3 EU). US removes our --lang again. Other lines are left as they are."""
    import re
    with open(boot_ini, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    def command(m):
        cmd = re.sub(r"\s*--lang\s+\S+", "", m.group(2))
        if lang != "US":
            cmd += f" --lang {lang}"
        return m.group(1) + cmd
    new = re.sub(r"(?m)^(command\s*=\s*)(.*?)\s*$", command, text, count=1)
    new = re.sub(r"(?m)^(playonline\s*=\s*)\d+", lambda m: m.group(1) + {"JP": "1", "US": "2", "EU": "3"}[lang], new, count=1)
    if new != text:
        with open(boot_ini, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    return lang


# ----- menu entry and Steam -----
def desktop_entry_text(kit, exe):
    icon = os.path.join(kit, "assets", "ui", "icon.png")
    return ("[Desktop Entry]\nType=Application\nVersion=1.0\n"
            f"Name={APP_NAME}\nComment=Offline FINAL FANTASY XI with squad mates and a living world\n"
            f"Exec=\"{exe}\"\nPath={kit}\nIcon={icon}\nTerminal=false\nCategories=Game;RolePlaying;\n"
            "StartupWMClass=XI Forever Offline\n")


def launcher_exe(kit):
    """The program a menu entry or Steam starts: the packaged launcher, else the launcher started with Python."""
    if getattr(sys, "frozen", False):
        return sys.executable
    for name in ("XI-Forever-Offline", "XI Forever Offline"):
        if os.path.isfile(os.path.join(kit, name)):
            return os.path.join(kit, name)
    return os.path.join(kit, "xi-forever-offline.sh")


def install_desktop_entry(kit, home=None):
    """Adds XI: Forever Offline to the application menu (and so to Steam's 'Add a Non-Steam Game' list).
    Returns the .desktop file's path."""
    home = home or os.path.expanduser("~")
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    folder = os.path.join(data, "applications")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, DESKTOP_ID + ".desktop")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(desktop_entry_text(kit, launcher_exe(kit)))
    os.chmod(path, 0o755)
    desktop = os.path.join(home, "Desktop")
    if os.path.isdir(desktop):
        shutil.copy2(path, os.path.join(desktop, DESKTOP_ID + ".desktop"))
        os.chmod(os.path.join(desktop, DESKTOP_ID + ".desktop"), 0o755)
    return path


def steam_running():
    return bool(pids_named("steam"))


def open_steam_add_game(popen=subprocess.Popen):
    """Opens Steam's 'Add a Non-Steam Game' window, where XI: Forever Offline is now listed. False when Steam isn't
    there."""
    steam = shutil.which("steam")
    if not steam:
        return False
    env = dict(os.environ)
    fix_frozen_environment(env)
    popen([steam, "steam://addnonsteamgame"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
          start_new_session=True)
    return True


def open_path(path, popen=subprocess.Popen):
    """A folder, file or web page in the desktop's own program (xdg-open)."""
    env = dict(os.environ)
    fix_frozen_environment(env)
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if not opener:
        raise RuntimeError("No program to open it with (xdg-open is missing).")
    args = [opener, path] if opener.endswith("xdg-open") else [opener, "open", path]
    popen(args, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
