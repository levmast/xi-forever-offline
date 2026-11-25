"""The game files for XI: Forever Offline.

Three ways to get them (first-run setup asks):
  copy      the player has FINAL FANTASY XI: copy PlayOnline and FFXI into the kit's own Game folder, so their own
            install (retail, other servers, HD packs) is never changed. Era-DATs then go into the copy only.
  existing  use the installed game as it is (how every install worked before this file).
  official  no FFXI on this PC: download Square Enix's own full installer from Square Enix and run it.

xiloader finds the game through Windows' registry (32-bit view): PlayOnline's InstallFolder values (0001 = FFXI,
1000 = the PlayOnline viewer) and two COM registrations, polcore (one class per language) and FFXi.dll. When a copy
is used and those point at another install, Play runs this file elevated ("hold"): it points them at the copy, waits
until every game window is closed and puts the old values back. The old values are kept in game-switch.json until
then, so a crash or power cut is undone the next time the launcher starts ("recover").
"""
import json
import ntpath
import os
import shutil
import subprocess
import sys
import time
import urllib.request

LANG_KEY = {"JP": "PlayOnline", "US": "PlayOnlineUS", "EU": "PlayOnlineEU"}
POLCORE_CLSID = {"JP": "{07974581-0DF6-4EF0-BD05-604B3ADA9BE9}", "US": "{3501F5DD-7894-42DF-866A-A2B6527D8049}",
                 "EU": "{E5966FB3-C97B-42EB-84BF-37F95EE54A9F}"}
POLCORE_DLL = {"JP": "polcore.dll", "US": "polcore.dll", "EU": "polcoreeu.dll"}
FFXI_CLSID = "{989D790D-6236-11D4-80E9-00105A81E890}"
FFXI_DLL = "FFXi.dll"
MSI_DESCRIPTOR = "InprocServer32"     # the Windows Installer value inside an InprocServer32 key (see entries)
FFXI_MSI_COMPONENT = "{2E08E9A0-5906-4A28-9D0A-7CBF0FAEE1D7}"   # the MSI component whose key file is FFXi.dll (US)
# Square Enix's own full installer (FFXI, PlayOnline and every expansion), straight from Square Enix: part1.exe
# unpacks itself and part2.rar, part3.rar... (5 parts, about 7.2 GB, in 2026) into FFXIFullSetup_US, then
# FFXISetup.exe in there installs the game. Parts are fetched until Square Enix has no next one.
OFFICIAL_BASE = {"US": "https://gdl.square-enix.com/ffxi/download/us/FFXIFullSetup_US"}
OFFICIAL_MIN_PARTS = 5
OFFICIAL_MAX_PARTS = 12
STATE_FILE = "game-switch.json"
HKLM = "HKLM"


def game_paths(root):
    """Where a copy lives: <root>\\SquareEnix\\PlayOnlineViewer and <root>\\SquareEnix\\FINAL FANTASY XI."""
    base = os.path.join(root, "SquareEnix")
    return {"viewer": os.path.join(base, "PlayOnlineViewer"), "ffxi": os.path.join(base, "FINAL FANTASY XI")}


# ----- the registry (32-bit view, as xiloader reads it) -----
class WinRegistry:
    """get/set/delete one value under HKLM in the 32-bit view. name "" is a key's default value."""

    def __init__(self):
        import winreg
        self.w = winreg

    def get(self, path, name):
        w = self.w
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_READ | w.KEY_WOW64_32KEY) as key:
                return w.QueryValueEx(key, name)[0]
        except OSError:
            return None

    def set(self, path, name, value):
        """A string is written as REG_SZ, a list of strings (an MSI descriptor read back by get) as REG_MULTI_SZ."""
        w = self.w
        kind = w.REG_MULTI_SZ if isinstance(value, list) else w.REG_SZ
        with w.CreateKeyEx(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_WRITE | w.KEY_WOW64_32KEY) as key:
            w.SetValueEx(key, name, 0, kind, value)

    def delete(self, path, name):
        w = self.w
        try:
            with w.OpenKey(w.HKEY_LOCAL_MACHINE, path, 0, w.KEY_WRITE | w.KEY_WOW64_32KEY) as key:
                w.DeleteValue(key, name)
        except OSError:
            pass

    def com_servers(self):
        """[(clsid, dll)] for every 32-bit COM class whose DLL is in a PlayOnline or FINAL FANTASY XI folder."""
        w = self.w
        found = []
        try:
            root = w.OpenKey(w.HKEY_LOCAL_MACHINE, r"SOFTWARE\Classes\CLSID", 0, w.KEY_READ | w.KEY_WOW64_32KEY)
        except OSError:
            return found
        with root:
            index = 0
            while True:
                try:
                    clsid = w.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    with w.OpenKey(root, clsid + r"\InprocServer32") as key:
                        dll = w.QueryValueEx(key, "")[0]
                except OSError:
                    continue
                if isinstance(dll, str) and _game_dll(dll):
                    found.append((clsid, dll))
        return found


def registry():
    return WinRegistry()


def entries(lang, viewer, ffxi, reg):
    """[(path, name, value wanted for this copy)] for the four values xiloader and the game read."""
    folder = rf"SOFTWARE\{LANG_KEY[lang]}\InstallFolder"
    polcore = rf"SOFTWARE\Classes\CLSID\{POLCORE_CLSID[lang]}\InprocServer32"
    game = rf"SOFTWARE\Classes\CLSID\{FFXI_CLSID}\InprocServer32"
    # keep where the installed registration has the DLL inside its folder (polcore.dll is not always at the top of
    # PlayOnlineViewer), only the folder moves; if the copy has it elsewhere, use the copy's own file
    polcore_path = _moved(reg.get(polcore, ""), reg.get(folder, "1000"), viewer, POLCORE_DLL[lang])
    game_path = _moved(reg.get(game, ""), reg.get(folder, "0001"), ffxi, FFXI_DLL)
    want = [(folder, "0001", ffxi), (folder, "1000", viewer), (polcore, "", polcore_path), (game, "", game_path)]
    # The other PlayOnline language keys too: FFXi.dll tries PlayOnline (JP), then PlayOnlineUS, then PlayOnlineEU, and
    # Ashita reads the English one (its boot file says playonline = 2). With an EU install, or a second install
    # registered under another language, Ashita and the game found the retail folder (Miniberg, datadecay, 2026-11-16:
    # the game closed ~20 s after "Profile loaded."; Ashita's log showed the retail path). PlayOnlineUS is always
    # pointed at the copy; JP and EU only when they exist. Put back (or removed again) after the game closes.
    for other_lang, key in LANG_KEY.items():
        other = rf"SOFTWARE\{key}\InstallFolder"
        if other == folder:
            continue
        if key == "PlayOnlineUS" or reg.get(other, "0001") is not None or reg.get(other, "1000") is not None:
            want += [(other, "0001", ffxi), (other, "1000", viewer)]
    # Every other COM class of the game or PlayOnline follows too. FFXi.dll itself creates FFXiMain.dll through COM
    # ({0DF0E951-...}): pointing only FFXi.dll at the copy left the game's main file (and so its menus, item data
    # and event files) loading from the retail install (shujimi, 2026-11-16: crash in the retail FFXiMain.dll).
    roots = [(reg.get(folder, "0001"), ffxi), (reg.get(folder, "1000"), viewer)]
    done = {polcore.lower(), game.lower()}
    servers = reg.com_servers() if hasattr(reg, "com_servers") else []
    for clsid, dll in servers:
        path = rf"SOFTWARE\Classes\CLSID\{clsid}\InprocServer32"
        if path.lower() in done:
            continue
        new = _into_copy(dll, roots, viewer, ffxi)
        if new is not None and not _same(new, dll):
            want.append((path, "", new))
            done.add(path.lower())
    # Square Enix's installer is an MSI: each class it registers also gets a Windows Installer descriptor, a
    # REG_MULTI_SZ value also named InprocServer32. While it is there COM asks Windows Installer for the DLL and
    # ignores the default value, so the retail files kept loading after the switch (2026-11-18: retail installed with
    # the official installer; pol.exe crashed in the retail FFXiMain.dll / app.dll, ~15 s after "Profile loaded.").
    # It is removed for every class that points at the copy during the game, and put back afterwards.
    to_copy = {p.lower(): p for p, n, _v in want if n == "" and p.lower() in done}
    for clsid, dll in servers:
        path = rf"SOFTWARE\Classes\CLSID\{clsid}\InprocServer32"
        if _inside(dll, (ffxi, viewer)):          # already pointing at the copy (a switch left in place, or set by hand)
            to_copy.setdefault(path.lower(), path)
    for _low, path in sorted(to_copy.items()):
        if reg.get(path, MSI_DESCRIPTOR) is not None:
            want.append((path, MSI_DESCRIPTOR, None))
    return want


def _inside(dll, folders):
    """True when dll is inside one of folders."""
    low = ntpath.normpath((dll or "").strip('"')).lower()
    return any(f and low.startswith(ntpath.normpath(f).rstrip("\\").lower() + "\\") for f in folders)


def _matches(current, wanted):
    """wanted None means the value must not exist."""
    return current is None if wanted is None else _same(current, wanted)


def _game_dll(dll):
    """True for a DLL inside a PlayOnline / FINAL FANTASY XI folder (the COM classes the game and PlayOnline use)."""
    low = dll.lower()
    return "final fantasy xi" in low or "playonline" in low


def _into_copy(dll, roots, viewer, ffxi):
    """The copy's file for a retail game or PlayOnline DLL, or None (already the copy's, or the copy has no such file)."""
    full = ntpath.normpath(dll.strip('"'))
    low = full.lower()
    for mine in (ffxi, viewer):
        if mine and low.startswith(ntpath.normpath(mine).rstrip("\\").lower() + "\\"):
            return None
    candidates = []
    for old, new in roots:
        if old and new:
            base = ntpath.normpath(old).rstrip("\\").lower() + "\\"
            if low.startswith(base) and not _same(old, new):
                candidates.append((new, full[len(base):]))
    parts = full.split("\\")
    for i in range(len(parts) - 2, -1, -1):
        name = parts[i].lower()
        if name == "final fantasy xi" and ffxi:
            candidates.append((ffxi, "\\".join(parts[i + 1:])))
            break
        if name == "playonlineviewer" and viewer:
            candidates.append((viewer, "\\".join(parts[i + 1:])))
            break
    for new_root, rel in candidates:
        path = ntpath.join(new_root, rel)
        if os.path.exists(path.replace("\\", os.sep)):
            return path
        moved = ntpath.join(new_root, "viewer", "com", ntpath.basename(full))     # (the newer PlayOnline layout)
        if os.path.exists(moved.replace("\\", os.sep)):
            return moved
    return None


def _moved(registered, old_root, new_root, default_name):
    """Where the registered DLL is inside new_root. Tried in order: the same path below the folder as in the old
    install; the newer PlayOnline layout (PlayOnlineViewer\\viewer\\com\\polcore.dll); the top of new_root; any file of
    that name in the copy except under patchfiles (PlayOnline's update staging, not the live files). If none
    exists, the first of those paths."""
    registered = registered or ""
    name = ntpath.basename(registered) or default_name
    rels = []
    if registered and old_root:
        root = ntpath.normpath(old_root).rstrip("\\").lower() + "\\"
        full = ntpath.normpath(registered)
        if full.lower().startswith(root):
            rels.append(full[len(root):])
    rels += ["viewer\\com\\" + name, name]
    for rel in rels:
        path = ntpath.join(new_root, rel)
        if os.path.exists(path.replace("\\", os.sep)):     # (os.sep is "\\" on Windows; this lets the tests run anywhere)
            return path
    for here, dirs, files in os.walk(new_root.replace("\\", os.sep)):
        dirs[:] = sorted(d for d in dirs if d.lower() != "patchfiles")
        for f in files:
            if f.lower() == name.lower():
                return os.path.join(here, f)
    return ntpath.join(new_root, rels[0])


def _same(a, b):
    return a is not None and b is not None and os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def needs_switch(cfg, reg):
    """True when the game copy is used and Windows points PlayOnline at another install."""
    if not cfg.get("game_copy"):
        return False
    lang = cfg.get("pol_lang", "US")
    return any(not _matches(reg.get(p, n), v) for p, n, v in entries(lang, cfg["pol_dir"], cfg["ffxi_client_dir"], reg))


def _restore(originals, reg):
    for path, name, value in originals:
        if value is None:
            reg.delete(path, name)
        else:
            reg.set(path, name, value)


def _write_state(state_path, state):
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=1)
    os.replace(tmp, state_path)


def msi_ffxi_paths():
    """Where Windows Installer expects FFXi.dll for each install of Square Enix's FINAL FANTASY XI MSI ([] when it
    can't be asked). MsiGetComponentPath gives the key file's path also when the file is gone."""
    try:
        import ctypes
        from ctypes import wintypes
        msi = ctypes.windll.msi
    except (ImportError, AttributeError, OSError):
        return []
    paths = []
    product = ctypes.create_unicode_buffer(39)
    index = 0
    try:
        while msi.MsiEnumClientsW(FFXI_MSI_COMPONENT, index, product) == 0 and index < 16:
            index += 1
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            msi.MsiGetComponentPathW(product.value, FFXI_MSI_COMPONENT, buf, ctypes.byref(size))
            if buf.value:
                paths.append(buf.value)
    except OSError:
        pass
    return paths


def fill_missing_ffxi_dll(candidates, copy_ffxi):
    """Puts the copy's FFXi.dll where Windows Installer expects it when that file is gone. Square Enix's installer is
    an MSI and FFXi.dll is the key file of its game component: when the player deleted or moved their own install
    after making the copy, Windows checked that file on every start, found it missing and tried to repair the game
    from an installer folder that was long gone ("The feature you are trying to use is on a network resource that is
    unavailable ... FINAL_FANTASY_XI.msi"; Hurami, 2026-11-24, MsiInstaller event 1004). Only a missing FFXi.dll in
    a "FINAL FANTASY XI" folder outside the copy is written; nothing is ever overwritten. Returns the paths written."""
    source = ntpath.join(copy_ffxi, FFXI_DLL).replace("\\", os.sep)
    if not os.path.isfile(source):
        return []
    written, seen = [], set()
    for path in candidates:
        if not isinstance(path, str) or not path.strip('" '):
            continue
        path = ntpath.normpath(path.strip('" '))
        local = path.replace("\\", os.sep)
        key = os.path.normcase(local)
        if key in seen:
            continue
        seen.add(key)
        if (ntpath.basename(path).lower() != FFXI_DLL.lower()
                or ntpath.basename(ntpath.dirname(path)).lower() != "final fantasy xi"
                or _inside(path, (copy_ffxi,)) or not os.path.isabs(local) or os.path.exists(local)):
            continue
        try:
            os.makedirs(os.path.dirname(local), exist_ok=True)
            shutil.copy2(source, local)
            written.append(path)
        except OSError:
            pass
    return written


def hold(state_path, reg, is_running, sleep=time.sleep, start_wait=180, poll=2, msi_paths=msi_ffxi_paths):
    """Elevated: point the registry at the copy, wait until the game has started and every game window is closed,
    then put the old values back. The old values are saved first, so recover() can undo a crash."""
    with open(state_path, encoding="utf-8") as handle:
        state = json.load(handle)
    # the player's own install may be gone: give Windows Installer back the one file it checks (see fill_missing_ffxi_dll)
    try:
        registered = reg.get(rf"SOFTWARE\Classes\CLSID\{FFXI_CLSID}\InprocServer32", "")
        state["filled_ffxi_dll"] = fill_missing_ffxi_dll([registered] + list(msi_paths() or []), state["ffxi"])
    except Exception:          # never let this stop Play
        pass
    want = entries(state["lang"], state["viewer"], state["ffxi"], reg)
    state["originals"] = [(p, n, reg.get(p, n)) for p, n, _v in want]
    _write_state(state_path, state)
    try:
        for path, name, value in want:
            if value is None:
                reg.delete(path, name)
            else:
                reg.set(path, name, value)
        state["applied"] = True
        _write_state(state_path, state)
        waited = 0
        while not is_running() and waited < start_wait:     # the launcher starts the game right after "applied"
            sleep(poll)
            waited += poll
        while is_running():
            sleep(poll)
    finally:
        _restore(state["originals"], reg)
        os.remove(state_path)


def recover(state_path, reg):
    """Puts back what a hold() that never finished (crash, power cut) had changed. True when something was undone."""
    if not os.path.exists(state_path):
        return False
    with open(state_path, encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("originals"):
        _restore(state["originals"], reg)
    os.remove(state_path)
    return bool(state.get("originals"))


def pending_recovery(kit):
    """True when an earlier switch was left in place (its helper never got to put the old values back)."""
    return os.path.exists(os.path.join(kit, STATE_FILE))


def start_switch(kit, cfg, run_elevated, reg=None, is_running=None, sleep=time.sleep, timeout=60):
    """Before Play: when the copy is used and the registry points elsewhere, starts the elevated helper and waits until
    it has switched. Returns False when nothing needed switching. Raises when Windows' permission was refused."""
    reg = reg or registry()
    if not needs_switch(cfg, reg):
        return False
    state_path = os.path.join(kit, STATE_FILE)
    if os.path.exists(state_path):
        if is_running is not None and is_running():
            return True          # a game window is open: the helper from that Play still holds the switch
        run_elevated(["recover", state_path])           # left over from a crash: undo it first
        for _ in range(timeout):
            if not os.path.exists(state_path):
                break
            sleep(1)
    _write_state(state_path, {"lang": cfg.get("pol_lang", "US"), "viewer": cfg["pol_dir"], "ffxi": cfg["ffxi_client_dir"]})
    run_elevated(["hold", state_path])
    for _ in range(timeout * 2):
        try:
            with open(state_path, encoding="utf-8") as handle:
                if json.load(handle).get("applied"):
                    return True
        except (OSError, ValueError):
            pass
        sleep(0.5)
    try:
        os.remove(state_path)
    except OSError:
        pass
    raise RuntimeError("PlayOnline could not be pointed at XI: Forever Offline's copy of the game: Windows' permission "
                       "prompt was refused or never answered. Press PLAY again and choose Yes, or the game would start "
                       "your other FINAL FANTASY XI install.")


def detect_lang(ffxi_dir, reg=None):
    """US, EU or JP: the PlayOnline entry whose FFXI folder is this one (US when none matches)."""
    try:
        reg = reg or registry()
    except ImportError:
        return "US"
    for lang, key in (("US", "PlayOnlineUS"), ("EU", "PlayOnlineEU"), ("JP", "PlayOnline")):
        if _same(reg.get(rf"SOFTWARE\{key}\InstallFolder", "0001"), ffxi_dir):
            return lang
    return "US"


def install_lang(cfg, reg=None):
    """US, EU or JP when it is known which PlayOnline this install starts, else None. A copy remembers the language of
    the install it was made from; an installed game is the PlayOnline entry whose FFXI folder is this one."""
    lang = str(cfg.get("pol_lang") or "").upper()
    if lang in LANG_KEY:
        return lang
    ffxi = cfg.get("ffxi_client_dir", "")
    if not ffxi:
        return None
    try:
        reg = reg or registry()
    except ImportError:
        return None
    for lang, key in (("US", "PlayOnlineUS"), ("EU", "PlayOnlineEU"), ("JP", "PlayOnline")):
        if _same(reg.get(rf"SOFTWARE\{key}\InstallFolder", "0001"), ffxi):
            return lang
    return None


BOOT_LANG = {"JP": "1", "US": "2", "EU": "3"}         # Ashita's [ashita.language] playonline
BOOT_LANG_BACKUP = ".before-pol-language"


def apply_boot_lang(boot_ini, lang):
    """(2026-11-22, Sirloinofbeef: a Steam EU game on a PC with registry leftovers of an uninstalled US game. The loader
    went for the US PlayOnline and stopped with "polcore (US) file ... doesn't exist".) An EU or JP game is named to
    the loader (--lang on the boot file's command line) and to Ashita ([ashita.language] playonline), as the Linux
    launcher already does, so entries of another language can't be picked in its place. A US game: the boot file is
    left alone, unless its command line still carries a --lang from another game. An unknown language (None) changes
    nothing. The first change keeps a copy of the boot file. Returns True when the file was changed."""
    import re
    if lang not in BOOT_LANG:
        return False
    with open(boot_ini, "r", encoding="utf-8-sig", newline="") as handle:
        text = handle.read()
    line = re.search(r"(?m)^command[ \t]*=[ \t]*([^\r\n]*)", text)
    had = bool(line and re.search(r"(?:^|\s)--lang\s+\S+", line.group(1)))
    if lang == "US" and not had:
        return False

    def command(match):
        rest = re.sub(r"\s*--lang\s+\S+", "", match.group(2)).strip()
        return match.group(1) + (rest + (f" --lang {lang}" if lang != "US" else "")).strip()

    new = re.sub(r"(?m)^(command[ \t]*=[ \t]*)([^\r\n]*)", command, text, count=1)
    new = re.sub(r"(?m)^(playonline[ \t]*=[ \t]*)\d+", lambda m: m.group(1) + BOOT_LANG[lang], new, count=1)
    if new == text:
        return False
    if not os.path.exists(boot_ini + BOOT_LANG_BACKUP):
        shutil.copyfile(boot_ini, boot_ini + BOOT_LANG_BACKUP)
    with open(boot_ini, "w", encoding="utf-8", newline="") as handle:
        handle.write(new)
    return True


# ----- making a copy -----
def find_viewer(ffxi_dir, lang="US", reg=None):
    """The PlayOnline viewer folder that belongs with this FFXI folder."""
    try:
        reg = reg or registry()
        viewer = reg.get(rf"SOFTWARE\{LANG_KEY[lang]}\InstallFolder", "1000")
        if viewer and os.path.isdir(viewer):
            return viewer
    except ImportError:
        pass
    sibling = os.path.join(os.path.dirname(os.path.normpath(ffxi_dir)), "PlayOnlineViewer")
    return sibling if os.path.isdir(sibling) else None


def pick_game_folder(path, lang="US", reg=None):
    """(2026-11-22, K-Andy: moved FFXI to another drive) (ffxi, viewer) for a folder the player picked: the FINAL FANTASY XI
    folder itself, its SquareEnix folder or the PlayOnline folder above it. Raises ValueError when there is no game there."""
    path = os.path.normpath(path or "")
    ffxi = next((c for c in (path, os.path.join(path, "FINAL FANTASY XI"), os.path.join(path, "SquareEnix", "FINAL FANTASY XI"))
                 if os.path.isfile(os.path.join(c, "FFXiMain.dll"))), None)
    if ffxi is None:
        raise ValueError("No FINAL FANTASY XI there (FFXiMain.dll not found). Pick the FINAL FANTASY XI folder.")
    sibling = os.path.join(os.path.dirname(ffxi), "PlayOnlineViewer")
    viewer = sibling if os.path.isdir(sibling) else find_viewer(ffxi, lang, reg)
    if not viewer:
        raise ValueError("PlayOnlineViewer was not found next to that FINAL FANTASY XI folder. Move both folders together "
                         "(they sit side by side in SquareEnix).")
    return ffxi, viewer


def folder_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def copy_install(ffxi_dir, viewer_dir, dest_root, log=print, free=None):
    """Copies PlayOnline and FFXI into dest_root (see game_paths). Files already copied (same size) are skipped, so
    it can be run again after a stop. Returns the new paths."""
    paths = game_paths(dest_root)
    jobs = [(viewer_dir, paths["viewer"]), (ffxi_dir, paths["ffxi"])]
    todo = []
    for src, dst in jobs:
        for root, _dirs, files in os.walk(src):
            for name in files:
                s = os.path.join(root, name)
                d = os.path.join(dst, os.path.relpath(s, src))
                size = os.path.getsize(s)
                if not (os.path.exists(d) and os.path.getsize(d) == size):
                    todo.append((s, d, size))
    need = sum(size for _s, _d, size in todo)
    os.makedirs(dest_root, exist_ok=True)
    have = free if free is not None else shutil.disk_usage(dest_root).free
    if need > have - 512 * 1024 * 1024:
        raise RuntimeError(f"Not enough free space for the game copy: it needs {need / 2**30:.1f} GB and "
                           f"{have / 2**30:.1f} GB is free on that drive.")
    log(f"   Copying {len(todo)} game files ({need / 2**30:.1f} GB) into {dest_root}...")
    done, step = 0, max(need // 20, 1)
    mark = step
    for s, d, size in todo:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        done += size
        if done >= mark:
            log(f"   {done * 100 // max(need, 1)}%")
            mark += step
    return paths


# ----- is the game new enough? (and refreshing a copy from an updated install) -----
# The server speaks the newest game version. A game from before FFXI's September 2026 version update misreads some of
# what it sends (shujimi, 2026-11-16: an August 2026 FFXiMain.dll crashed opening Equipment; October works). The game's
# build is the link date of FFXiMain.dll. Raise this when a later update turns out to be needed too.
MIN_GAME_BUILD = (2026, 9, 1)
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def game_build(ffxi_dir):
    """(year, month, day) FFXiMain.dll was built (its PE time stamp), or None."""
    import struct
    import datetime
    try:
        with open(os.path.join(ffxi_dir, "FFXiMain.dll"), "rb") as handle:
            head = handle.read(4096)
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if head[pe:pe + 4] != b"PE\0\0":
            return None
        stamp = struct.unpack_from("<I", head, pe + 8)[0]
        when = datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc)
        return (when.year, when.month, when.day)
    except (OSError, ValueError, OverflowError, struct.error):
        return None


def build_text(build):
    return f"{MONTHS[build[1] - 1]} {build[0]}" if build else "an unknown version"


def too_old(build):
    return build is not None and tuple(build) < MIN_GAME_BUILD


def retail_install(kit, cfg, reg=None):
    """(ffxi, viewer) of the player's regular FFXI that a copy was made from (the registry's PlayOnline folders when no
    switch is in place), or None. Only meaningful for a copy install."""
    if os.path.exists(os.path.join(kit, STATE_FILE)):
        return None           # the registry points at the copy right now
    reg = reg or registry()
    copy_ffxi = cfg.get("ffxi_client_dir", "")
    order = [cfg.get("pol_lang", "US")] + [lang for lang in LANG_KEY if lang != cfg.get("pol_lang", "US")]
    for lang in order:
        folder = rf"SOFTWARE\{LANG_KEY.get(lang, 'PlayOnlineUS')}\InstallFolder"
        ffxi, viewer = reg.get(folder, "0001"), reg.get(folder, "1000")
        if ffxi and not _same(ffxi, copy_ffxi) and os.path.isfile(os.path.join(ffxi, "FFXiMain.dll")):
            return ffxi, (viewer if viewer and os.path.isdir(viewer) and not _same(viewer, cfg.get("pol_dir")) else None)
    return None


TARGET_OFFSET_NOV = (2026, 10, 26)  # FFXiMain linked from here on = the November 2026 game update (client 30261102_0; its link date can be a few days earlier; the October client is 2026-10-05). Ashita main a807426
_OFFSET_BEGIN = "; >>> XI: Forever Offline: target offset for this game version (written at PLAY)"
_OFFSET_END = "; <<< XI: Forever Offline"


def match_target_offset(ashita_dir, ffxi_dir):
    """Ashita's offsets follow the newest game (November 2026: [target.target] offset1 = 0x02F0). On a September or
    October game that reads the target in the wrong place: the target bar is gone and addons that read it (XIUI,
    tparty, mobdb, distance) crash in d3d_present. For an older game this writes the old value (0x02F4) into Ashita's
    custom.offsets.ini (overrides, never replaced by updates); for the November game or newer it removes it.
    Returns 'old', 'new' or None (nothing done)."""
    build = game_build(ffxi_dir)
    path = os.path.join(ashita_dir, "config", "ashita", "custom.offsets.ini")
    if not build or not os.path.isdir(os.path.dirname(path)):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
            text = handle.read()
    except OSError:
        text = ""
    begin, end = text.find(_OFFSET_BEGIN), text.find(_OFFSET_END)
    if begin >= 0 and end > begin:
        text = text[:begin].rstrip("\n") + "\n" + text[end + len(_OFFSET_END):].lstrip("\n")
    old = tuple(build) < TARGET_OFFSET_NOV
    if old:
        block = f"{_OFFSET_BEGIN}\n[target.target]\noffset1 = 0x02F4 ; the game before the November 2026 update\n{_OFFSET_END}\n"
        marker = "; Fin!"
        at = text.rfind(marker)
        text = (text[:at] + block + "\n" + text[at:]) if at >= 0 else (text.rstrip("\n") + "\n\n" + block)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError:
        return None
    return "old" if old else "new"


def game_check(kit, cfg, reg=None):
    """What PLAY should say about the game's version: {build, too_old, copy, retail, retail_build, retail_ok}."""
    build = game_build(cfg.get("ffxi_client_dir", ""))
    info = {"build": build, "too_old": too_old(build), "copy": bool(cfg.get("game_copy")), "retail": None,
            "retail_build": None, "retail_ok": False}
    if info["too_old"] and info["copy"]:
        try:
            retail = retail_install(kit, cfg, reg)
        except Exception:
            retail = None
        if retail:
            rb = game_build(retail[0])
            info.update(retail=retail, retail_build=rb, retail_ok=bool(rb) and not too_old(rb) and tuple(rb) > tuple(build))
    return info


def refresh_copy(kit, cfg, retail_ffxi, retail_viewer=None, log=print):
    """Brings the copy up to date with the (updated) regular install: copies every file that is new, a different size
    or newer. Game files the Era-DATs replaced keep the era version in the game; the updated original goes into
    dat-backup instead (what restore-original-dats.ps1 puts back). Files the Era-DATs added are left alone. Returns
    the number of files copied."""
    copy_ffxi, copy_viewer = cfg.get("ffxi_client_dir", ""), cfg.get("pol_dir", "")
    backup = os.path.join(kit, "dat-backup")
    added = set()
    try:
        with open(os.path.join(backup, "new-files.txt"), encoding="utf-8") as handle:
            added = {os.path.normcase(os.path.normpath(line.strip())) for line in handle if line.strip()}
    except OSError:
        pass

    def stale(src, dst):
        if not os.path.exists(dst):
            return True
        a, b = os.stat(src), os.stat(dst)
        return a.st_size != b.st_size or int(a.st_mtime) > int(b.st_mtime) + 2

    jobs = [(retail_ffxi, copy_ffxi, True)]
    if retail_viewer and copy_viewer:
        jobs.insert(0, (retail_viewer, copy_viewer, False))
    todo = []
    for src_root, dst_root, is_game in jobs:
        for root, dirs, files in os.walk(src_root):
            dirs[:] = [d for d in dirs if d.lower() != "patchfiles"]
            for name in files:
                src = os.path.join(root, name)
                rel = os.path.relpath(src, src_root)
                if is_game and os.path.normcase(os.path.normpath(rel)) in added:
                    continue
                target = os.path.join(dst_root, rel)
                if is_game and os.path.isfile(os.path.join(backup, rel)):
                    target = os.path.join(backup, rel)        # an era file is in the game: refresh its saved original
                if stale(src, target):
                    todo.append((src, target))
    log(f"Updating the game copy: {len(todo)} files to copy...")
    for index, (src, target) in enumerate(todo, 1):
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        if index % 200 == 0:
            log(f"   {index}/{len(todo)}")
    log(f"The game copy is up to date ({len(todo)} files copied).")
    return len(todo)


# ----- Square Enix's official installer -----
def download_to(url, path, log=print, context=None, chunk=1 << 20):
    """Streams a big file to disk; a stopped download carries on from where it was (<name>.part)."""
    if os.path.exists(path):
        return path
    part = path + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    request = urllib.request.Request(url, headers={"User-Agent": "XI-Forever-Offline"})
    if have:
        request.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(request, timeout=60, context=context) as response:
        if have and response.status != 206:      # the server started over: so do we
            have = 0
        total = have + int(response.headers.get("Content-Length") or 0)
        mark = 0
        with open(part, "ab" if have else "wb") as handle:
            done = have
            while True:
                data = response.read(chunk)
                if not data:
                    break
                handle.write(data)
                done += len(data)
                if total and done * 10 // total > mark:
                    mark = done * 10 // total
                    log(f"   {os.path.basename(path)}: {done * 100 // total}% of {total / 2**30:.1f} GB")
    os.replace(part, path)
    return path


def official_folder(kit):
    return os.path.join(kit, "downloads", "ffxi-installer")


def download_official(kit, log=print, lang="US", context=None, download=None):
    """Every part of Square Enix's installer into downloads\\ffxi-installer (parts already there are kept)."""
    import urllib.error
    download = download or download_to
    folder = official_folder(kit)
    os.makedirs(folder, exist_ok=True)
    files = []
    for number in range(1, OFFICIAL_MAX_PARTS + 1):
        name = f"{OFFICIAL_BASE[lang].rsplit('/', 1)[-1]}.part{number}." + ("exe" if number == 1 else "rar")
        url = f"{OFFICIAL_BASE[lang]}.part{number}." + ("exe" if number == 1 else "rar")
        log(f"   Downloading {name} from Square Enix...")
        try:
            files.append(download(url, os.path.join(folder, name), log=log, context=context))
        except urllib.error.HTTPError as problem:
            if problem.code == 404 and number > OFFICIAL_MIN_PARTS:
                log(f"   That was the last part ({number - 1} in all).")
                break
            raise
    return files


def find_setup(kit):
    """FFXISetup.exe inside what part1.exe unpacked, or None."""
    for root, _dirs, names in os.walk(official_folder(kit)):
        for name in names:
            if name.lower() == "ffxisetup.exe":
                return os.path.join(root, name)
    return None


def run_official_installer(kit, files, log=print, popen=subprocess.Popen):
    """Unpacks the parts (part1.exe: press Extract and keep its folder) unless that was done, then runs FFXISetup.exe
    (tick PlayOnline, FINAL FANTASY XI and the expansions, then Install) and waits for it."""
    setup = find_setup(kit)
    if setup is None:
        log("   Square Enix's unpacker is opening: press Extract and keep the folder it suggests.")
        popen([files[0]], cwd=os.path.dirname(files[0])).wait()
        setup = find_setup(kit)
        if setup is None:
            raise RuntimeError("Square Enix's files were not unpacked into " + official_folder(kit) + ". Press Install again "
                               "and let the unpacker extract into the folder it suggests.")
    log("   Square Enix's setup is opening: tick every box (PlayOnline, FINAL FANTASY XI and the expansions), press "
        "Install and follow it to the end.")
    proc = popen([setup], cwd=os.path.dirname(setup))
    proc.wait()
    return proc.returncode


# ----- the first update of a fresh install (PlayOnline's free "Check Files"; no Square Enix account needed) -----
VTABLE = "VTABLE.DAT"
VTABLE_BACKUP = "VTABLE.DAT.before-update"


def viewer_dir(cfg, reg=None):
    """The PlayOnline viewer folder of this install (the copy's own, or the one that goes with the FFXI folder)."""
    if cfg.get("pol_dir") and os.path.isdir(cfg["pol_dir"]):
        return cfg["pol_dir"]
    ffxi = cfg.get("ffxi_client_dir", "")
    lang = cfg.get("pol_lang") or detect_lang(ffxi, reg)
    return find_viewer(ffxi, lang, reg)


def pol_exe(cfg, reg=None):
    viewer = viewer_dir(cfg, reg)
    for name in ("pol.exe", "polboot.exe"):
        if viewer and os.path.isfile(os.path.join(viewer, name)):
            return os.path.join(viewer, name)
    return None


def open_playonline(cfg, start=None, reg=None):
    """Starts PlayOnline the way Windows would (so it can ask for administrator rights for its own update)."""
    exe = pol_exe(cfg, reg)
    if not exe:
        raise RuntimeError("PlayOnline (pol.exe) wasn't found next to your game. Start 'PlayOnline Viewer' from the "
                           "Start menu instead.")
    (start or os.startfile)(exe)
    return exe


def force_version_check(ffxi_dir):
    """When Check Files says there is nothing to update (it happens without a retail account), moving VTABLE.DAT
    aside makes it look again. finish_version_check puts it back if PlayOnline didn't rebuild it."""
    table, backup = os.path.join(ffxi_dir, VTABLE), os.path.join(ffxi_dir, VTABLE_BACKUP)
    if not os.path.exists(table):
        return os.path.exists(backup)          # already moved
    if os.path.exists(backup):
        os.remove(backup)
    os.replace(table, backup)
    return True


def finish_version_check(ffxi_dir):
    """'updated' (PlayOnline rebuilt VTABLE.DAT: our copy is dropped), 'restored' (it didn't: ours put back),
    or 'unchanged' (the trick was never used)."""
    table, backup = os.path.join(ffxi_dir, VTABLE), os.path.join(ffxi_dir, VTABLE_BACKUP)
    if not os.path.exists(backup):
        return "unchanged"
    if os.path.exists(table):
        os.remove(backup)
        return "updated"
    os.replace(backup, table)
    return "restored"


# ----- the whole game from XI: Forever Offline's own download (2026-11-24, the user: "it's still downloading from SE
# instead of our GitHub") -----
# No Square Enix installer: every game and PlayOnline file comes from the xi-forever-gamefiles release
# (launcher_gamefiles.py) into the kit's own Game folder, and the launcher registers it with Windows itself, once, from
# the same template Ashita's sandbox uses (Ashita\config\sandbox\sandbox.registry.ini: PlayOnline's InstallFolder,
# Interface and settings keys and every COM class of PlayOnline and FFXI), imported into the 32-bit view with
# "reg import /reg:32" from an elevated helper (Windows asks once).
REG_FILE = "xiforever-game.reg"


def install_from_release(kit, log=print, context=None, update=None):
    r"""Downloads the whole game into <kit>\Game\SquareEnix. Returns its paths (see game_paths)."""
    import launcher_gamefiles as gf
    paths = game_paths(os.path.join(kit, "Game"))
    for folder in paths.values():
        os.makedirs(folder, exist_ok=True)
    log("   Downloading FINAL FANTASY XI from XI: Forever Offline (about 7.5 GB; a stopped download carries on "
        "where it left off)...")
    (update or gf.update)(kit, paths["ffxi"], paths["viewer"], log=log, context=context)
    if not os.path.isfile(os.path.join(paths["ffxi"], "FFXiMain.dll")):
        raise RuntimeError("the download finished, but FFXiMain.dll is missing from it")
    # (the release leaves out the folders a player's own install keeps settings and screenshots in: make them empty)
    for folder in (os.path.join(paths["ffxi"], "USER"), os.path.join(paths["ffxi"], "screenshots"),
                   os.path.join(paths["viewer"], "usr")):
        os.makedirs(folder, exist_ok=True)
    return paths


def registry_text(kit, ashita_dir, ffxi, viewer):
    """The .reg file that registers this game with Windows (paths filled in)."""
    import launcher_linux as ll
    tetra = os.path.join(os.path.dirname(os.path.normpath(ffxi)), "TetraMaster")
    paths = {"pol": viewer, "ffxi": ffxi, "tetra": tetra, "common": r"C:\Program Files (x86)\Common Files"}
    return ll.registry_file_text(ll.sandbox_registry_text(ashita_dir or ""), paths)


def write_registry_file(kit, ashita_dir, ffxi, viewer):
    path = os.path.join(kit, "downloads", REG_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-16", newline="") as handle:     # (reg import reads UTF-16 .reg files)
        handle.write(registry_text(kit, ashita_dir, ffxi, viewer))
    return path


def registered(cfg, reg=None):
    """True when Windows has this game's folders and FFXiMain's COM class pointing at it."""
    reg = reg or registry()
    ffxi = cfg.get("ffxi_client_dir", "")
    main_dll = reg.get(r"SOFTWARE\Classes\CLSID\{1027DC46-750D-4B1F-8834-1D25B8BEBAB8}\InprocServer32", "")
    return _same(reg.get(r"SOFTWARE\PlayOnlineUS\InstallFolder", "0001"), ffxi) and _inside(main_dll, (ffxi,))


def register_import(reg_file, run=subprocess.run):
    """(elevated) reg import into the 32-bit view; writes <reg_file>.done with the exit code."""
    result = run(["reg", "import", reg_file, "/reg:32"], capture_output=True, text=True)
    with open(reg_file + ".done", "w", encoding="utf-8") as handle:
        handle.write(f"{result.returncode}\n{(result.stdout or '')[-500:]}{(result.stderr or '')[-500:]}")
    return result.returncode


def main(argv):
    """XI Forever Offline.exe --run launcher_game.py hold|recover <state file> | register <.reg file>   (run elevated)"""
    if len(argv) == 2 and argv[0] == "register":
        return register_import(argv[1])
    if len(argv) != 2 or argv[0] not in ("hold", "recover"):
        print(main.__doc__)
        return 2
    reg = registry()
    if argv[0] == "recover":
        recover(argv[1], reg)
        return 0
    import launcher_core as core
    hold(argv[1], reg, lambda: core.is_running("xiloader"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
