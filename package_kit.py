"""Makes the player download: xi-forever-offline-<version>-win64.zip (+ SHA256SUMS.txt) in dist\\kit\\, or on Linux
xi-forever-offline-<version>-linux-x64.tar.gz (+ SHA256SUMS-linux.txt; build_release.sh builds the launcher first).

    python package_kit.py v0.1.1            (build the exe first: .\\build_release.ps1)
    python package_kit.py v0.1.1 --list     only shows what would go in

Inside is one folder, "XI Forever Offline", with every file git tracks in this kit (the launcher's scripts, assets,
addons, data, tests) and XI Forever Offline.exe. A player unzips it anywhere and runs the exe; the first-run setup
does the rest. Never inside: anything git does not track (config.json, rates.json, your squad mates, backups, logs, ROMs,
downloads, dist\\ and build\\).
"""
import argparse
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXE = "XI Forever Offline.exe"
LINUX_EXE = "XI-Forever-Offline"
TOP = "XI Forever Offline/"
LINUX_ONE_CLICK = "XI-Forever-Offline-Linux.tar.gz"     # same file under a fixed name: .../releases/latest/download/<this>


def is_song(rel):
    """The launcher's theme songs (assets/press). They go LAST in the zip, after the exe and VERSION.txt: a launcher up
    to v0.3.1 keeps the song it played open and stops its update at the first file it cannot replace ("Access is
    denied ... .mp3", Hasuko 2026-11-22). With the songs last, such a launcher has everything else by then, and is the
    new version the next time it is opened."""
    return rel.startswith("assets/press/") and rel.lower().endswith((".mp3", ".wav", ".ogg"))


def tracked():
    out = subprocess.run(["git", "-C", HERE, "ls-files", "-z"], capture_output=True, text=True, encoding="utf-8",
                         env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    if out.returncode != 0:
        raise RuntimeError("git ls-files: " + out.stderr.strip())
    return [f for f in out.stdout.split("\0") if f]


def linux_extras():
    """Linux: lib/mariadb-compat (old libraries for MariaDB's generic package, copied from Ubuntu 22.04 by the release
    workflow; not in git). The launcher only uses the ones a player's Linux lacks."""
    compat = os.path.join(HERE, "lib", "mariadb-compat")
    names = sorted(os.listdir(compat)) if os.path.isdir(compat) else []
    if not names:
        print("WARNING: lib/mariadb-compat is empty: MariaDB may miss old libraries on newer Linux (Arch, SteamOS).")
    return ["lib/mariadb-compat/" + name for name in names if os.path.isfile(os.path.join(compat, name))]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("--out", default=os.path.join(HERE, "dist", "kit"))
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--platform", choices=("windows", "linux"), default="windows" if os.name == "nt" else "linux")
    args = parser.parse_args(argv)
    files = [f for f in tracked() if os.path.isfile(os.path.join(HERE, *f.split("/")))]
    if args.platform == "linux":
        files += [f for f in linux_extras() if f not in files]
    exe_name = EXE if args.platform == "windows" else LINUX_EXE
    exe = os.path.join(HERE, exe_name)
    if not os.path.isfile(exe):
        raise SystemExit(f"{exe_name} is missing: run " + (".\\build_release.ps1" if args.platform == "windows"
                                                          else "./build_release.sh") + " first.")
    changed = subprocess.run(["git", "-C", HERE, "status", "--porcelain", "--untracked-files=no"], capture_output=True,
                             text=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")).stdout.splitlines()
    if changed:
        print(f"WARNING: {len(changed)} tracked file(s) are not committed; they are packaged as they are on disk.")
    size = sum(os.path.getsize(os.path.join(HERE, *f.split("/"))) for f in files) + os.path.getsize(exe)
    print(f"{len(files)} kit files + {exe_name}, {size / 1e6:.0f} MB before compression.")
    if args.list:
        return 0
    commit = subprocess.run(["git", "-C", HERE, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    os.makedirs(args.out, exist_ok=True)
    if args.platform == "linux":
        return write_linux(args, files, exe, commit)
    name = f"xi-forever-offline-{args.version}-win64.zip"
    target = os.path.join(args.out, name)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        songs = [rel for rel in files if is_song(rel)]
        for rel in files:
            if rel not in songs:
                archive.write(os.path.join(HERE, *rel.split("/")), TOP + rel)
        archive.write(exe, TOP + EXE)
        archive.writestr(TOP + "VERSION.txt", f"XI: Forever Offline {args.version}\ncommit {commit}\n")
        for rel in songs:                       # last: see is_song
            archive.write(os.path.join(HERE, *rel.split("/")), TOP + rel)
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    with open(os.path.join(args.out, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{digest.hexdigest()}  {name}\n")
    print(f"Wrote {target} ({os.path.getsize(target) / 1e6:.0f} MB) and SHA256SUMS.txt.")
    return 0


def write_linux(args, files, exe, commit):
    """The Linux download: a .tar.gz (the launcher and the shell scripts keep their run permission)."""
    name = f"xi-forever-offline-{args.version}-linux-x64.tar.gz"
    target = os.path.join(args.out, name)

    def clean(info):
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        if info.name.endswith((".sh", "/" + LINUX_EXE)):
            info.mode = 0o755
        return info

    with tarfile.open(target, "w:gz", compresslevel=6) as archive:
        for rel in files:
            archive.add(os.path.join(HERE, *rel.split("/")), TOP + rel, recursive=False, filter=clean)
        archive.add(exe, TOP + LINUX_EXE, recursive=False, filter=clean)
        data = f"XI: Forever Offline {args.version}\ncommit {commit}\n".encode()
        info = tarfile.TarInfo(TOP + "VERSION.txt")
        info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
        archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    with open(os.path.join(args.out, "SHA256SUMS-linux.txt"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{digest.hexdigest()}  {name}\n{digest.hexdigest()}  {LINUX_ONE_CLICK}\n")
    print(f"Wrote {target} ({os.path.getsize(target) / 1e6:.0f} MB) and SHA256SUMS-linux.txt.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
