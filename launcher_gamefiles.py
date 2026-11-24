"""The up-to-date game files, from XI: Forever Offline's own GitHub release (Hurami89/xi-forever-gamefiles).

Square Enix's full installer puts in the game as it was in April 2019, and the server needs a newer one. Instead of the
PlayOnline login and update, the launcher can bring the game up to date from a release that holds an updated
FINAL FANTASY XI and PlayOnlineViewer:

  gamefiles.json       the list: every file (path, size, sha256) and which bundle holds it
  gamefiles-NN.zip     the bundles, each under GitHub's 2 GiB limit per release file

Only the files that are missing or different are taken, so only the bundles that hold one of them are downloaded.
Files the Era-DATs replaced keep the era version in the game: the updated original goes into dat-backup (the same rule
as launcher_game.refresh_copy). A player's own settings (FINAL FANTASY XI\\USER, PlayOnlineViewer\\usr) are never in the
release and never touched.

Building a release (on the PC that has the updated game):
  python launcher_gamefiles.py build "<...\\FINAL FANTASY XI>" "<...\\PlayOnlineViewer>" <out folder> <tag> [--base <2019 FINAL FANTASY XI>]
With --base (a fresh install from Square Enix's installer), the files that differ from it are packed first, into their
own bundles, so a fresh install downloads only those.
"""
import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile

REPO = "Hurami89/xi-forever-gamefiles"
MANIFEST_URL = f"https://github.com/{REPO}/releases/latest/download/gamefiles.json"
MANIFEST_NAME = "gamefiles.json"
FORMAT = 1
BUNDLE_LIMIT = 1900 * 2**20                 # GitHub: each release file under 2 GiB
ROOTS = ("ffxi", "viewer")                  # paths in the list start with one of these
# never in the release and never written: the player's own settings and account, PlayOnline's download leftovers
SKIP_DIRS = {"ffxi": {"user", "screenshots"}, "viewer": {"usr", "patchfiles", "tmp"}}
SKIP_NAMES = {"thumbs.db", "desktop.ini", "vtable.dat.before-update"}
SKIP_ENDINGS = (".log", ".tmp", ".part")
USER_AGENT = "XI-Forever-Offline"
# without a 2019 install to compare with: a file written after Square Enix's installer came out (April 2019) counts
# as changed (PlayOnline's updates write new dates; the installer keeps the old ones)
INSTALLER_DATE = 1556668800        # 2019-05-01 UTC


def sha256(path, chunk=1 << 20):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def _skipped(root, rel):
    parts = rel.replace("\\", "/").split("/")
    if parts[0].lower() in SKIP_DIRS.get(root, ()):
        return True
    name = parts[-1].lower()
    return name in SKIP_NAMES or name.endswith(SKIP_ENDINGS)


def walk(root, folder):
    """Relative paths (with / ) of every file in folder that belongs in the release, sorted."""
    out = []
    for base, dirs, names in os.walk(folder):
        dirs.sort()
        for name in names:
            rel = os.path.relpath(os.path.join(base, name), folder).replace("\\", "/")
            if not _skipped(root, rel):
                out.append(rel)
    return sorted(out, key=str.lower)


# ----- building a release -----
MIN_GAME_BUILD = (2026, 9, 1)               # the same as launcher_game.MIN_GAME_BUILD


def dll_build(path):
    """(year, month, day) a dll was built (its PE time stamp), or None (as launcher_game.game_build)."""
    import datetime
    import struct
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096)
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if head[pe:pe + 4] != b"PE\0\0":
            return None
        when = datetime.datetime.fromtimestamp(struct.unpack_from("<I", head, pe + 8)[0], datetime.timezone.utc)
        return (when.year, when.month, when.day)
    except (OSError, ValueError, OverflowError, struct.error):
        return None


def build(ffxi_dir, viewer_dir, out_dir, tag, base_dir=None, log=print, limit=BUNDLE_LIMIT, game_build=None):
    """Writes gamefiles.json and gamefiles-NN.zip into out_dir. Returns the manifest."""
    for path, what in ((ffxi_dir, "FINAL FANTASY XI"), (viewer_dir, "PlayOnlineViewer")):
        if not os.path.isdir(path):
            raise RuntimeError(f"{what} folder not found: {path}")
    if not os.path.isfile(os.path.join(ffxi_dir, "FFXiMain.dll")):
        raise RuntimeError("That FINAL FANTASY XI folder has no FFXiMain.dll.")
    if game_build is None:
        game_build = dll_build(os.path.join(ffxi_dir, "FFXiMain.dll"))
    log(f"The game in {ffxi_dir}: FFXiMain.dll built " + ("-".join(f"{n:02d}" for n in game_build) if game_build else "(unknown)"))
    if game_build and tuple(game_build) < MIN_GAME_BUILD:
        raise RuntimeError("That game is older than the September 2026 update the server needs. Update it with PlayOnline first.")
    os.makedirs(out_dir, exist_ok=True)
    entries = []
    for root, folder in (("ffxi", ffxi_dir), ("viewer", viewer_dir)):
        names = walk(root, folder)
        log(f"{root}: {len(names)} files, working out their fingerprints...")
        for index, rel in enumerate(names, 1):
            full = os.path.join(folder, rel)
            entry = {"path": f"{root}/{rel}", "size": os.path.getsize(full), "sha256": sha256(full)}
            if base_dir and root == "ffxi":
                old = os.path.join(base_dir, rel)
                entry["new"] = not (os.path.isfile(old) and os.path.getsize(old) == entry["size"] and sha256(old) == entry["sha256"])
            else:
                entry["new"] = os.path.getmtime(full) >= INSTALLER_DATE
            entries.append(entry)
            if index % 2000 == 0:
                log(f"   {index}/{len(names)}")
    # files that differ from the 2019 install first, so they share bundles of their own
    order = sorted(entries, key=lambda e: (not e["new"], e["path"].lower()))
    bundles, current, size = [], [], 0
    for entry in order:
        if current and (size + entry["size"] > limit or current[0]["new"] != entry["new"]):
            bundles.append(current)
            current, size = [], 0
        current.append(entry)
        size += entry["size"]
    if current:
        bundles.append(current)
    sources = {"ffxi": ffxi_dir, "viewer": viewer_dir}
    out_bundles = []
    for number, group in enumerate(bundles, 1):
        name = f"gamefiles-{number:02d}.zip"
        path = os.path.join(out_dir, name)
        log(f"Packing {name}: {len(group)} files, {sum(e['size'] for e in group) / 2**30:.2f} GB...")
        with zipfile.ZipFile(path + ".tmp", "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for entry in group:
                root, rel = entry["path"].split("/", 1)
                archive.write(os.path.join(sources[root], rel), entry["path"])
                entry["bundle"] = name
        os.replace(path + ".tmp", path)
        packed = os.path.getsize(path)
        if packed >= 2 * 2**30:
            raise RuntimeError(f"{name} came out at {packed} bytes, over GitHub's 2 GiB limit. Build again with a smaller limit.")
        out_bundles.append({"name": name, "size": packed, "sha256": sha256(path), "new": group[0]["new"]})
    manifest = {"format": FORMAT, "tag": tag, "game_build": list(game_build) if game_build else None,
                "bundles": out_bundles, "files": [{k: e[k] for k in ("path", "size", "sha256", "bundle")} for e in entries]}
    with open(os.path.join(out_dir, MANIFEST_NAME), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1)
    total = sum(b["size"] for b in out_bundles)
    log(f"Done: {len(entries)} files in {len(out_bundles)} bundles ({total / 2**30:.2f} GB) in {out_dir}.")
    fresh = sum(b["size"] for b in out_bundles if b["new"])
    if fresh:
        log(f"A fresh install from Square Enix's installer downloads {fresh / 2**30:.2f} GB of that.")
    return manifest


# ----- bringing a player's game up to date -----

def fetch_manifest(url=MANIFEST_URL, context=None, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    if manifest.get("format") != FORMAT or not manifest.get("files") or not manifest.get("tag"):
        raise RuntimeError("The game files list on GitHub isn't one this launcher understands. Update the launcher.")
    return manifest


def bundle_url(manifest, name):
    return f"https://github.com/{REPO}/releases/download/{manifest['tag']}/{name}"


def _era_rules(kit):
    """(files the Era-DATs added, dat-backup folder) for an install with the Era-DATs in it."""
    backup = os.path.join(kit, "dat-backup")
    added = set()
    try:
        with open(os.path.join(backup, "new-files.txt"), encoding="utf-8") as handle:
            added = {os.path.normcase(os.path.normpath(line.strip())) for line in handle if line.strip()}
    except OSError:
        pass
    return added, backup


def targets(manifest, ffxi_dir, viewer_dir, kit):
    """[(entry, where it goes)] for every listed file, with the Era-DATs rule applied (None: leave it alone)."""
    added, backup = _era_rules(kit)
    folders = {"ffxi": ffxi_dir, "viewer": viewer_dir}
    out = []
    for entry in manifest["files"]:
        root, rel = entry["path"].split("/", 1)
        folder = folders.get(root)
        if not folder or _skipped(root, rel):
            out.append((entry, None))
            continue
        local = os.path.normpath(rel)
        if root == "ffxi" and os.path.normcase(local) in added:
            out.append((entry, None))                       # an era file with no retail original: the era one stays
            continue
        dest = os.path.join(folder, local)
        if root == "ffxi" and os.path.isfile(os.path.join(backup, local)):
            dest = os.path.join(backup, local)              # an era file is in the game: refresh its saved original
        out.append((entry, dest))
    return out


def plan(manifest, ffxi_dir, viewer_dir, kit, log=print):
    """What has to come down: {"files": [(entry, dest)], "bundles": [bundle], "download": bytes, "write": bytes}."""
    todo = []
    pairs = targets(manifest, ffxi_dir, viewer_dir, kit)
    log(f"Checking your game against the up-to-date files ({len(pairs)} files)...")
    for index, (entry, dest) in enumerate(pairs, 1):
        if dest is None:
            continue
        try:
            same = os.path.getsize(dest) == entry["size"] and sha256(dest) == entry["sha256"]
        except OSError:
            same = False
        if not same:
            todo.append((entry, dest))
        if index % 5000 == 0:
            log(f"   {index}/{len(pairs)}")
    wanted = {entry["bundle"] for entry, _dest in todo}
    bundles = [b for b in manifest["bundles"] if b["name"] in wanted]
    return {"files": todo, "bundles": bundles, "download": sum(b["size"] for b in bundles),
            "write": sum(entry["size"] for entry, _dest in todo)}


def update(kit, ffxi_dir, viewer_dir, log=print, context=None, manifest=None, download=None, free=None, keep=False):
    """Brings the game up to date from the release. Returns the number of files written (0: it already was)."""
    import launcher_game as lg
    download = download or lg.download_to
    manifest = manifest or fetch_manifest(context=context)
    work = plan(manifest, ffxi_dir, viewer_dir, kit, log=log)
    if not work["files"]:
        log("Your game files are already up to date.")
        return 0
    folder = os.path.join(kit, "downloads", "gamefiles", manifest["tag"])
    os.makedirs(folder, exist_ok=True)
    biggest = max(b["size"] for b in work["bundles"])
    need = biggest + work["write"] + 2**30
    have = (free or (lambda p: shutil.disk_usage(p).free))(folder)
    if have < need:
        raise RuntimeError(f"Not enough free disk space for the game update: {need / 2**30:.1f} GB needed, "
                           f"{have / 2**30:.1f} GB free.")
    log(f"Updating the game: {len(work['files'])} files from {len(work['bundles'])} download(s), "
        f"{work['download'] / 2**30:.1f} GB in all.")
    by_bundle = {}
    for entry, dest in work["files"]:
        by_bundle.setdefault(entry["bundle"], []).append((entry, dest))
    written = 0
    for number, bundle in enumerate(work["bundles"], 1):
        path = os.path.join(folder, bundle["name"])
        log(f"   Download {number} of {len(work['bundles'])}: {bundle['name']} ({bundle['size'] / 2**30:.2f} GB)")
        download(bundle_url(manifest, bundle["name"]), path, log=log, context=context)
        if os.path.getsize(path) != bundle["size"] or sha256(path) != bundle["sha256"]:
            os.remove(path)
            raise RuntimeError(f"{bundle['name']} didn't download correctly (it was removed). Try again.")
        with zipfile.ZipFile(path) as archive:
            for entry, dest in by_bundle[bundle["name"]]:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                temp = dest + ".xifo-new"
                with archive.open(entry["path"]) as source, open(temp, "wb") as target:
                    shutil.copyfileobj(source, target, 1 << 20)
                if os.path.getsize(temp) != entry["size"] or sha256(temp) != entry["sha256"]:
                    os.remove(temp)
                    raise RuntimeError(f"{entry['path']} in {bundle['name']} isn't the right file. Try again.")
                os.replace(temp, dest)
                written += 1
        if not keep:
            os.remove(path)
        log(f"   {written}/{len(work['files'])} files updated")
    if not keep:
        shutil.rmtree(folder, ignore_errors=True)
    log(f"The game is up to date ({written} files updated).")
    return written


def main(argv):
    if len(argv) >= 5 and argv[0] == "build":
        base = None
        if "--base" in argv:
            at = argv.index("--base")
            base = argv[at + 1]
            argv = argv[:at] + argv[at + 2:]
        build(argv[1], argv[2], argv[3], argv[4], base_dir=base)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
