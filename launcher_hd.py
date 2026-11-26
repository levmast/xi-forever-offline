"""HD texture packs through XIPivot (2026-11-22, the user: "on Nexus Mods there are some HD mods for FFXI, can we have an
option for players to download it and have it work natively in the launcher with XIPivot").

What this does, and what it does not:
* The PLAYER downloads the pack from Nexus Mods with his own (free) account. Nexus only gives automatic download links
  to premium members, and the packs' authors do not allow them to be uploaded anywhere else, so the launcher neither
  downloads them nor ships them. It opens the pack's page.
* The launcher does everything after that: it finds the downloaded file, unpacks only the game-data folders (ROM,
  ROM2..ROM9, sound...) into Ashita's polplugins/DATs/<pack>/, switches XIPivot on and lists the pack in
  config/pivot/pivot.ini. XIPivot then hands those files to the game instead of the game's own; nothing in the FFXI
  folder is changed. Taking a pack out again is deleting its folder.
* Era files win: where a pack holds a file our era set replaces (Era-DATs, 155 files), the pack's copy is left out.
  XIPivot would otherwise prefer the pack's (made from today's retail game) over the era file in the game folder.

No tkinter here: the window is launcher_hd_gui.py. Tests: dev/launcher-tests/test_hd_packs.py.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

NEXUS = "https://www.nexusmods.com/finalfantasy11/mods"
# The packs players ask about. `match` recognises a downloaded file by its name; `nexus` is the mod's number on Nexus,
# which is also in every file name Nexus hands out (<name>-<mod>-<version...>-<time>.zip).
KNOWN = (
    {"id": "ashenbubs", "nexus": 1, "name": "AshenbubsHD", "by": "Ashenbubs", "url": NEXUS + "/1", "match": r"ashenbubs",
     "note": "Every texture in the game, redone. Two versions: Basic (twice the size of the originals) and Prime (four times). "
             "Pick one. Prime is about 7 GB to download and 26 GB unpacked."},
    {"id": "nextgames", "nexus": 12, "name": "NextGames HD / Lore Friendly", "by": "NextGames, with work by Amelila and RadialArcana",
     "url": NEXUS + "/12", "match": r"next\s*(hd|lore)",
     "note": "Zone and character textures. NextHD is the sharper one, NextLore stays closer to the original look. "
             "About 3.6 GB to download and 7 GB unpacked."},
    # (2026-11-25, the user) character textures in HD, off until you install it
    {"id": "jasmint", "nexus": 13, "name": "Jasmint's HD Textures", "by": "Jasmint", "url": NEXUS + "/13", "match": r"jasmint",
     "note": "Player characters redone at four times the size (Elvaan, Hume and Mithra so far; Tarutaru and Galka next), closer "
             "to how they look at character creation. Made to sit on top of NextGames HD. Colours and some faces differ from "
             "the original look."},
    # (2026-11-25, the user) a new look for the interface: status and menu icons, lettering, cursor, menu colours
    {"id": "moonicon", "nexus": 46, "name": "MoonIcon-Tactics", "by": "Gdragoon91", "url": NEXUS + "/46", "match": r"moon\s*icon",
     "note": "Final Fantasy Tactics style icons for status effects and menus, new lettering and numbers, a gold cursor and "
             "three menu palettes. Put it above any texture pack in the list below. The few files that hold the Hardcore "
             "and Randomized marks are left out, so those marks stay."},
)
# (2026-11-25) Visual extras that are not texture packs and can't be installed here: the window shows their page and
# what they need, nothing more.
GUIDES = (
    {"id": "reshade-ultra", "nexus": 18, "name": "Yourmothers Ultra HD Reshade", "by": "yourmom", "url": NEXUS + "/18",
     "note": "A ReShade look (HDR, bloom, depth of field, ambient occlusion, anti-aliasing). Installed by hand: it needs "
             "dgVoodoo2, ReShade (with add-on support) and the iMMERSE Pro or Ultimate shaders; its page has the steps. "
             "Heavy on the graphics card."},
)

# (2026-11-25, the user: "I don't want it to affect my hardcore or randomized icons") the game files that hold the
# Hardcore and Randomized marks beside a name (launcher_client.py MARKS_FILES and MARKS_HD_FILES): a pack's copy of one
# of these is left out like an era file, or XIPivot would show the pack's sheet without the marks.
OUR_MARKS = {"ROM/0/1.DAT", "ROM/0/13.DAT", "ROM/118/111.DAT", "ROM/280/15.DAT",
             "ROM/119/51.DAT", "ROM/91/15.DAT", "ROM/176/75.DAT", "ROM/178/14.DAT"}
# (2026-11-23, datadecay) Packs whose authors publish them openly on GitHub: the launcher downloads these itself (pinned
# to one commit, straight from the author's page, never rehosted), installs them switched OFF, and the player turns them
# on in the packs window.
DIRECT = (
    {"id": "lofi", "name": "LoFi FFXI music", "folder": "LoFi-FFXI", "repo": "CatsAndBoats/LoFi-FFXI",
     "ref": "7ec7a317e10ac103754460a753e354f0b7c736ed", "url": "https://github.com/CatsAndBoats/LoFi-FFXI",
     "by": "Spaceroast (the remixes), converted for XIPivot by CatsAndBoats",
     "note": "Lo-fi remixes of the game's music: towns, areas, battles, the Mog House. About 430 MB. Installed switched off; "
             "turn it on below. Support Spaceroast: open.spotify.com/artist/1EPZJb9PkAT60jX4vWvg8u"},
)
ARCHIVES = (".zip", ".rar", ".7z")
PACK_DIR = re.compile(r"^(rom\d?|sound\d?)$", re.I)        # the game-data folders XIPivot overlays
NEXUS_NAME = re.compile(r"^(?P<name>.+?)-(?P<mod>\d+)(?:-[0-9A-Za-z]+)*-(?P<time>\d{9,11})$")
MARK = ".xifo-pack.json"                                   # what the launcher notes in a pack's folder
TEMP = "_unpacking-"
SPACE_FACTOR = 4.2                                         # a .rar or .7z unpacks to about this many times its size
MIN_SPARE = 2 << 30                                        # ...and this much has to stay free afterwards


# ---------------------------------------------------------------- places
def dats_dir(ashita):
    return os.path.join(ashita, "polplugins", "DATs")


def ini_path(ashita):
    return os.path.join(ashita, "config", "pivot", "pivot.ini")


def pivot_installed(ashita):
    return bool(ashita) and os.path.exists(os.path.join(ashita, "polplugins", "pivot.dll"))


def downloads_dirs(kit=None):
    home = os.path.expanduser("~")
    out = [os.path.join(home, "Downloads")]
    if kit:
        out.append(kit)
    return [d for d in out if os.path.isdir(d)]


# ---------------------------------------------------------------- names
def nexus_parts(filename):
    """('NextHD Package', 12) from 'NextHD Package-12-1-0-1648563600.zip'; (stem, None) for any other name."""
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = NEXUS_NAME.match(stem)
    return (m.group("name").strip(), int(m.group("mod"))) if m else (stem.strip(), None)


def known_pack(filename):
    """The KNOWN entry a downloaded file belongs to, by its Nexus mod number or its name; None for anything else."""
    name, mod = nexus_parts(filename)
    for pack in KNOWN:
        if mod == pack["nexus"] and re.search(pack["match"], name, re.I):
            return pack
    for pack in KNOWN:
        if re.search(pack["match"], name, re.I):
            return pack
    return None


def folder_name(text):
    """A plain folder name for polplugins/DATs: letters, digits, '-', '_' and '.', no spaces, never empty or dotted."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-.")
    return name[:60] or "HD-pack"


def find_downloads(folders):
    """Archives in the given folders that look like an FFXI texture pack: a KNOWN one, or any with 'hd' in its name
    from Nexus. Newest first: [{path, size, name, pack}]."""
    found = []
    for folder in folders:
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for n in names:
            path = os.path.join(folder, n)
            if not n.lower().endswith(ARCHIVES) or not os.path.isfile(path):
                continue
            pack = known_pack(n)
            if pack is None:
                continue
            try:
                stat = os.stat(path)
            except OSError:
                continue
            found.append({"path": path, "size": stat.st_size, "name": nexus_parts(n)[0], "pack": pack, "time": stat.st_mtime})
    found.sort(key=lambda f: -f["time"])
    return found


# ---------------------------------------------------------------- what is inside
def pack_roots(paths):
    """Where the packs are inside a list of file paths. A pack is a folder that holds ROM, ROM2... or sound folders;
    an archive may hold one at its top, one or more further down (.../XIPivot/data/DATs/NextHD/ROM/...), and things
    that are no pack at all (a 4 GB patcher, ReShade). Returns {root: [(path, path below the root)]}, root '' = top."""
    roots = {}
    for path in paths:
        parts = [p for p in str(path).replace("\\", "/").split("/") if p not in ("", ".")]
        if ".." in parts:
            continue
        for i, part in enumerate(parts[:-1]):
            if PACK_DIR.match(part):
                roots.setdefault("/".join(parts[:i]), []).append((path, "/".join(parts[i:])))
                break
    return roots


def root_names(roots, archive_name):
    """A folder name for each root: its own folder's name, or the archive's for a pack at the top. No two alike."""
    out, used = {}, set()
    for root in sorted(roots):
        base = folder_name(root.split("/")[-1] if root else nexus_parts(archive_name)[0])
        name, n = base, 2
        while name.lower() in used:
            name, n = f"{base}-{n}", n + 1
        used.add(name.lower())
        out[root] = name
    return out


def era_paths(kit):
    """The files our era set replaces, as upper-case paths (ROM/0/0.DAT). A pack's copy of one of these is left out."""
    out = set()
    base = os.path.join(kit, "Era-DATs") if kit else ""
    for rom in ("ROM", "ROM2", "ROM3", "ROM4"):
        for folder, _dirs, names in os.walk(os.path.join(base, rom)):
            for n in names:
                out.add(os.path.relpath(os.path.join(folder, n), base).replace("\\", "/").upper())
    return out


# ---------------------------------------------------------------- pivot.ini
DEFAULT_INI = ("[settings]\ndebug_log=false\n\n[overlays]\n\n[cache]\nenabled=false\nmax_age=600\nsize=128\n")
_SECTION = re.compile(r"(?ms)^\[overlays\][^\n]*\n(.*?)(?=^\[|\Z)")
_ENTRY = re.compile(r"^[ \t]*(\d+)[ \t]*=[ \t]*(.*?)[ \t]*$")


def _read_ini(ashita):
    try:
        with open(ini_path(ashita), encoding="utf-8-sig", errors="replace", newline="") as handle:
            return handle.read()
    except OSError:
        return None


def read_overlays(ashita):
    """The packs XIPivot loads, first (the one that wins) first. XIPivot stops at the first missing number, so do we."""
    text = _read_ini(ashita)
    section = _SECTION.search(text.replace("\r\n", "\n")) if text else None
    if not section:
        return []
    entries = {}
    for line in section.group(1).split("\n"):
        m = _ENTRY.match(line)
        if m and m.group(2):
            entries.setdefault(int(m.group(1)), m.group(2))
    out, n = [], 0
    while n in entries:
        out.append(entries[n])
        n += 1
    return out


def write_overlays(ashita, names):
    """Writes the list of packs into pivot.ini, numbered from 0 with no gaps. Everything else in the file stays: the
    other sections, the comments, a root_path the player set. The first time, the file is made from XIPivot's sample."""
    path = ini_path(ashita)
    text = _read_ini(ashita)
    if text is None:
        sample = os.path.join(os.path.dirname(path), "pivot.sample.ini")
        try:
            with open(sample, encoding="utf-8-sig", errors="replace", newline="") as handle:
                text = handle.read()
        except OSError:
            text = DEFAULT_INI
    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")
    seen, clean = set(), []
    for name in names:
        if name and name.lower() not in seen:
            seen.add(name.lower())
            clean.append(name)
    lines = "".join(f"{i}={name}\n" for i, name in enumerate(clean))
    section = _SECTION.search(text)
    if not section:
        text = text.rstrip("\n") + "\n\n[overlays]\n" + lines
    else:
        kept = [line for line in section.group(1).split("\n") if not _ENTRY.match(line)]
        while kept and kept[-1].strip() == "":
            kept.pop()
        body = "\n".join(kept) + ("\n" if kept else "") + lines + "\n"
        text = text[:section.start(1)] + body + text[section.end(1):]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", newline))
    try:
        fix_root(ashita)
    except OSError:
        pass
    return clean


_ROOT = re.compile(r"(?mi)^([ \t]*root_path[ \t]*=[ \t]*)([^\r\n]*?)[ \t]*(?=\r?$)")


def fix_root(ashita):
    """(2026-11-23, Ryan: LoFi on but silent after moving the game's folder) a root_path in pivot.ini that points at a
    folder that is gone (the old place of the kit) makes XIPivot load nothing. Points it at this kit's DATs folder.
    True when the file was changed. A root_path that exists, or none, is left alone."""
    text = _read_ini(ashita)
    if not text:
        return False
    m = _ROOT.search(text)
    old = m.group(2).strip().strip('"') if m else ""
    # only a kit's own DATs folder (…/polplugins/DATs) that is gone: a folder the player chose is not touched
    if not old or os.path.isdir(old) or not old.replace("\\", "/").rstrip("/").lower().endswith("polplugins/dats"):
        return False
    text = text[:m.start(2)] + dats_dir(ashita) + text[m.end(2):]
    with open(ini_path(ashita), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return True


# ---------------------------------------------------------------- the packs that are installed
def _is_pack(folder):
    try:
        return any(PACK_DIR.match(n) and os.path.isdir(os.path.join(folder, n)) for n in os.listdir(folder))
    except OSError:
        return False


def _safe(ashita, name):
    """The pack's folder, or None for anything that is not one plain folder name inside polplugins/DATs."""
    if not name or name in (".", "..") or any(c in name for c in "/\\:") or name.startswith(TEMP):
        return None
    folder = os.path.join(dats_dir(ashita), name)
    return folder if os.path.isdir(folder) else None


def tree_size(folder):
    total = files = 0
    for root, _dirs, names in os.walk(folder):
        for n in names:
            try:
                total += os.path.getsize(os.path.join(root, n))
                files += 1
            except OSError:
                pass
    return total, files


def installed(ashita):
    """Every pack folder in polplugins/DATs: [{name, on, order, bytes, files, source}], the ones XIPivot loads first, in
    their order (the first wins), then the rest by name. Folders the player put there himself are listed too."""
    order = read_overlays(ashita)
    lower = [n.lower() for n in order]
    out = []
    try:
        names = sorted(os.listdir(dats_dir(ashita)), key=str.lower)
    except OSError:
        names = []
    for name in names:
        folder = _safe(ashita, name)
        if not folder or not _is_pack(folder):
            continue
        note = {}
        try:
            with open(os.path.join(folder, MARK), encoding="utf-8") as handle:
                note = json.load(handle)
        except (OSError, ValueError):
            pass
        on = name.lower() in lower
        out.append({"name": name, "on": on, "order": lower.index(name.lower()) if on else None, "bytes": note.get("bytes"),
                    "files": note.get("files"), "source": note.get("source", ""), "left_out": note.get("left_out", 0)})
    out.sort(key=lambda p: (not p["on"], p["order"] if p["on"] else 0, p["name"].lower()))
    return out


def set_on(ashita, name, on):
    """Lists the pack in pivot.ini (at the end: what is already there keeps winning) or takes it off the list."""
    names = [n for n in read_overlays(ashita) if n.lower() != name.lower()]
    if on:
        names.append(name)
    return write_overlays(ashita, names)


def move(ashita, name, up):
    """One place up (wins over the one below) or down in pivot.ini."""
    names = read_overlays(ashita)
    lower = [n.lower() for n in names]
    if name.lower() not in lower:
        return names
    i = lower.index(name.lower())
    j = i - 1 if up else i + 1
    if 0 <= j < len(names):
        names[i], names[j] = names[j], names[i]
    return write_overlays(ashita, names)


def remove(ashita, name):
    """Deletes the pack's folder and takes it off XIPivot's list. Returns the bytes freed."""
    folder = _safe(ashita, name)
    if not folder:
        raise ValueError(f"{name} is not a pack folder in polplugins/DATs.")
    size, _files = tree_size(folder)
    write_overlays(ashita, [n for n in read_overlays(ashita) if n.lower() != name.lower()])
    shutil.rmtree(folder)
    return size


# ---------------------------------------------------------------- unpacking
def unpackers(platform=None, which=shutil.which, exists=os.path.exists, env=None):
    """Programs that can unpack .rar and .7z, best first: [(kind, path)]. Windows has one built in since 2018
    (System32\\tar.exe, libarchive; its newer versions read .rar too), 7-Zip is used when it is installed."""
    platform = platform or sys.platform
    env = os.environ if env is None else env
    out = []
    if platform.startswith("win"):
        tar = os.path.join(env.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
        if exists(tar):
            out.append(("tar", tar))
        for base in (env.get("ProgramFiles"), env.get("ProgramFiles(x86)"), env.get("ProgramW6432")):
            seven = os.path.join(base, "7-Zip", "7z.exe") if base else ""
            if seven and exists(seven) and ("7z", seven) not in out:
                out.append(("7z", seven))
    else:
        for kind, names in (("tar", ("bsdtar",)), ("7z", ("7z", "7zz", "7za")), ("unrar", ("unrar",)), ("unar", ("unar",))):
            for n in names:
                path = which(n)
                if path:
                    out.append((kind, path))
                    break
    return out


def unpack_command(kind, program, archive, dest):
    if kind == "tar":
        return [program, "-xf", archive, "-C", dest]
    if kind == "7z":
        return [program, "x", "-y", "-bso0", "-bsp0", "-o" + dest, archive]
    if kind == "unrar":
        return [program, "x", "-o+", "-y", archive, dest + os.sep]
    return [program, "-force-overwrite", "-no-directory", "-output-directory", dest, archive]


def _unpack_external(archive, dest, log, run=None, tools=None, tick=None):
    """Unpacks a .rar / .7z into dest with the first program that manages it. Raises with what to do when none does."""
    tools = unpackers() if tools is None else tools
    if not tools:
        raise RuntimeError("This PC has no program that unpacks " + os.path.splitext(archive)[1] + " files. Install 7-Zip (free, 7-zip.org) "
                           "and try again, or unpack the file yourself and use \"Install from a folder\".")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    problems = []
    for kind, program in tools:
        for leftover in os.listdir(dest):
            path = os.path.join(dest, leftover)
            shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
        log(f"Unpacking with {os.path.basename(program)} (a big pack takes several minutes)...")
        command = unpack_command(kind, program, archive, dest)
        if run is not None:
            code, said = run(command)
        else:
            with tempfile.TemporaryFile() as said_file:    # (a file, not a pipe: a full pipe would stop the unpacker)
                proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=said_file, stderr=subprocess.STDOUT, creationflags=flags)
                while proc.poll() is None:
                    time.sleep(2)
                    if tick:
                        tick()
                said_file.seek(0)
                code, said = proc.returncode, said_file.read()[-4000:].decode("utf-8", "replace")
        if code == 0:
            return kind
        problems.append(f"{os.path.basename(program)}: {said.strip().splitlines()[-1][:160] if said.strip() else 'stopped with code ' + str(code)}")
    raise RuntimeError("Could not unpack this file (" + "; ".join(problems) + "). Install 7-Zip (free, 7-zip.org) and try again, "
                       "or unpack it yourself and use \"Install from a folder\".")


def _note(folder, source, bytes_, files, left_out):
    with open(os.path.join(folder, MARK), "w", encoding="utf-8") as handle:
        json.dump({"source": os.path.basename(source), "installed": time.strftime("%Y-%m-%d %H:%M"), "bytes": bytes_, "files": files,
                   "left_out": left_out}, handle)


def space_needed(source):
    """Roughly what installing this takes on the Ashita drive, in bytes."""
    if os.path.isdir(source):
        return tree_size(source)[0]
    if source.lower().endswith(".zip"):
        with zipfile.ZipFile(source) as archive:
            return sum(info.file_size for info in archive.infolist())
    return int(os.path.getsize(source) * SPACE_FACTOR)


def check_space(source, ashita, free=None):
    """None when there is room, else a sentence saying how much is missing."""
    need = space_needed(source)
    os.makedirs(dats_dir(ashita), exist_ok=True)
    have = shutil.disk_usage(dats_dir(ashita)).free if free is None else free
    if have >= need + MIN_SPARE:
        return None
    return (f"Not enough room on the drive Ashita is on: this pack needs about {need / (1 << 30):.1f} GB and "
            f"{have / (1 << 30):.1f} GB is free. Free some space and try again.")


def _take(items, target, era, move_files):
    """Puts the files of one pack into its folder. items: [(full source path, path below the pack's root)].
    Files the era set replaces are left out. Returns (bytes, files, left out)."""
    total = files = left = 0
    for src, rel in items:
        if rel.upper() in era:
            left += 1
            if move_files:
                try:
                    os.remove(src)
                except OSError:
                    pass
            continue
        dst = os.path.join(target, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if move_files:
            os.replace(src, dst)
        else:
            shutil.copyfile(src, dst)
        total += os.path.getsize(dst)
        files += 1
    return total, files, left


def install(source, ashita, kit=None, log=print, run=None, tools=None, free=None, tick=None, switch_on=True, name=None):
    """Installs the pack(s) in an archive (.zip, .rar, .7z) or a folder into polplugins/DATs and lists them in
    pivot.ini. Returns [{name, files, bytes, left_out}]. XIPivot itself is switched on by the caller (the boot file).
    tick: called every couple of seconds while a .rar / .7z unpacks (for a "still working" line)."""
    if not ashita or not os.path.isdir(ashita):
        raise RuntimeError("Ashita's folder was not found. Run the first-time setup before adding a texture pack.")
    if not os.path.exists(source):
        raise RuntimeError("That file is not there any more: " + source)
    problem = check_space(source, ashita, free)
    if problem:
        raise RuntimeError(problem)
    dats = dats_dir(ashita)
    os.makedirs(dats, exist_ok=True)
    era = era_paths(kit) | OUR_MARKS           # (era files, and the files with the Hardcore / Randomized marks)
    done = []
    if os.path.isdir(source):
        listing = []
        for folder, _dirs, names in os.walk(source):
            listing += [os.path.relpath(os.path.join(folder, n), source).replace("\\", "/") for n in names]
        roots = pack_roots(listing)
        names = root_names(roots, os.path.basename(os.path.normpath(source)))
        for root, items in roots.items():
            log(f"Copying {names[root]} ({len(items)} files)...")
            target = os.path.join(dats, names[root])
            got = _take([(os.path.join(source, *p.split("/")), rel) for p, rel in items], target, era, False)
            _note(target, source, *got)
            done.append({"name": names[root], "bytes": got[0], "files": got[1], "left_out": got[2]})
    elif source.lower().endswith(".zip"):
        with zipfile.ZipFile(source) as archive:
            infos = {info.filename: info for info in archive.infolist() if not info.is_dir()}
            roots = pack_roots(list(infos))
            names = root_names(roots, source)
            if name and len(roots) == 1:
                names = {root: folder_name(name) for root in roots}
            for root, items in roots.items():
                log(f"Unpacking {names[root]} ({len(items)} files)...")
                target = os.path.join(dats, names[root])
                total = files = left = 0
                for path, rel in items:
                    if rel.upper() in era:
                        left += 1
                        continue
                    dst = os.path.join(target, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with archive.open(infos[path]) as src, open(dst + ".part", "wb") as out:
                        shutil.copyfileobj(src, out, 1 << 20)
                    os.replace(dst + ".part", dst)
                    total += infos[path].file_size
                    files += 1
                _note(target, source, total, files, left)
                done.append({"name": names[root], "bytes": total, "files": files, "left_out": left})
    else:
        temp = os.path.join(dats, TEMP + folder_name(nexus_parts(source)[0]))
        shutil.rmtree(temp, ignore_errors=True)
        os.makedirs(temp)
        try:
            _unpack_external(source, temp, log, run=run, tools=tools, tick=tick)
            listing = []
            for folder, _dirs, names_ in os.walk(temp):
                listing += [os.path.relpath(os.path.join(folder, n), temp).replace("\\", "/") for n in names_]
            roots = pack_roots(listing)
            names = root_names(roots, source)
            for root, items in roots.items():
                log(f"Putting {names[root]} in place ({len(items)} files)...")
                target = os.path.join(dats, names[root])
                got = _take([(os.path.join(temp, *p.split("/")), rel) for p, rel in items], target, era, True)
                _note(target, source, *got)
                done.append({"name": names[root], "bytes": got[0], "files": got[1], "left_out": got[2]})
        finally:
            shutil.rmtree(temp, ignore_errors=True)
    if not done:
        raise RuntimeError("No game-data folders (ROM, ROM2... or sound) were found in there, so this is not a texture pack XIPivot can load.")
    if switch_on:
        current = read_overlays(ashita)
        write_overlays(ashita, current + [d["name"] for d in done if d["name"].lower() not in [c.lower() for c in current]])
    for d in done:
        era_note = f", {d['left_out']} left out so the era files win" if d["left_out"] else ""
        log(f"{d['name']}: {d['files']} files, {d['bytes'] / (1 << 30):.1f} GB{era_note}.")
    return done


def download_direct(pack, kit, ashita, log=print, fetch=None):
    """A DIRECT pack: downloads the author's GitHub archive of the pinned commit into <kit>/downloads/packs, unpacks it
    into polplugins/DATs/<folder> switched off (not in pivot.ini), and deletes the download. Returns install()'s list."""
    import launcher_thirdparty as tp
    if not ashita or not os.path.isdir(ashita):
        raise RuntimeError("Ashita's folder was not found. Run the first-time setup first.")
    url = f"https://github.com/{pack['repo']}/archive/{pack['ref']}.zip"
    path = os.path.join(kit, "downloads", "packs", pack["folder"] + "-" + pack["ref"][:8] + ".zip")
    log(f"{pack['name']}: downloading from {pack['url']}...")
    tp.download_file(url, path, log=log, fetch=fetch)
    try:
        done = install(path, ashita, kit, log=log, switch_on=False, name=pack["folder"])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return done
