"""Updates for players: is there a newer XI: Forever Offline, and install it (no GUI code here).

The kit (launcher, scripts, addons) and the server are released separately on GitHub. Installing a kit update unpacks
the player zip over the kit folder (only files that come in the zip are replaced, so config.json, rates.json, your squad
mates and every other personal file stay). Installing a server update first saves the database, then unpacks the server
zip over the server folder (settings/network.lua and the files the launcher writes are not in it), and then updates the
database the way the server's own tools/dbtool.py does: the game-data tables are imported again, the player tables
(accounts, characters, linkshells, auction house...) never are, and the migrations in tools/migrations run.
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import time
import zipfile

KIT_REPO = "Hurami89/xi-forever-offline"
SERVER_REPO = "Hurami89/xi-forever-offline-server"
# XIFO_TEST_PLATFORM=windows: the stand-in tests check the Windows paths on a Linux machine
IS_WINDOWS = os.name == "nt" or os.environ.get("XIFO_TEST_PLATFORM") == "windows"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
# each system takes its own files from the same release
KIT_ASSET = r"^xi-forever-offline-v.+-win64\.zip$" if IS_WINDOWS else r"^xi-forever-offline-v.+-linux-x64\.tar\.gz$"
SERVER_ASSET = (r"^xi-forever-offline-server-v.+-win64\.zip$" if IS_WINDOWS
                else r"^xi-forever-offline-server-v.+-linux-x64\.tar\.gz$")
# from the server's tools/dbtool.py (player_data); read again from the server folder when it is there
PLAYER_DATA = ("account_ip_record accounts accounts_banned accounts_files accounts_friends accounts_messages accounts_profile "
               "accounts_totp auction_house_items auction_house audit_bazaar audit_chat audit_dbox audit_gm audit_trade audit_vendor "
               "char_blacklist char_chocobos char_effects char_equip char_equip_saved char_exp char_fishing_contest_history char_flags "
               "char_history char_inventory char_jobs char_job_points char_look char_merit char_monstrosity char_pet char_points "
               "char_profile char_skills char_spells char_stats char_storage char_style char_unlocks char_vars char_world_passes chars "
               "chocobo_race_quills chocobo_race_results conquest_system delivery_box fishing_contest fishing_contest_entries help_desk "
               "ip_exceptions linkshell_concierge linkshells server_variables unity_system").split()


def version_key(tag):
    """v0.1.10 -> (0, 1, 10) so versions sort as numbers."""
    return tuple(int(x) for x in re.findall(r"\d+", str(tag or ""))) or (0,)


def installed_version(folder):
    """The version in VERSION.txt (written into both release zips), or None (a self-built copy)."""
    try:
        with open(os.path.join(folder, "VERSION.txt"), encoding="utf-8") as handle:
            found = re.search(r"\bv\d[\w.\-]*", handle.readline())
        return found.group(0) if found else None
    except OSError:
        return None


def newest_release(repo, test_builds, fetch):
    """The newest published release (pre-releases only when test_builds), or None."""
    import launcher_thirdparty as tp
    releases = json.loads(fetch(tp.API + repo + "/releases?per_page=30"))
    usable = [r for r in releases if not r.get("draft") and (test_builds or not r.get("prerelease"))]
    usable.sort(key=lambda r: version_key(r.get("tag_name")), reverse=True)
    return usable[0] if usable else None


def check(kit, server, test_builds, fetch):
    """{"kit": {...}, "server": {...}} each with installed, newest (tag), notes, release, and newer (bool)."""
    out = {}
    for key, repo, folder in (("kit", KIT_REPO, kit), ("server", SERVER_REPO, server)):
        have = installed_version(folder) if folder else None
        release = newest_release(repo, test_builds, fetch)
        tag = release.get("tag_name") if release else None
        out[key] = {"installed": have, "newest": tag, "notes": (release or {}).get("body", ""), "release": release,
                    "newer": bool(tag and have and version_key(tag) > version_key(have))}
    return out


def _download(release, pattern, kit, fetch, log, what):
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    names = [n for n in assets if re.search(pattern, n)]
    if not names:
        raise RuntimeError(f"The {what} release {release.get('tag_name')} has no download" +
                           ("." if IS_WINDOWS else " for Linux yet (the Linux files are added a while after the "
                                                    "release: try again later)."))
    name = names[0]
    log(f"Downloading {name}...")
    data = fetch(assets[name], timeout=3600)
    sums_name = "SHA256SUMS.txt" if IS_WINDOWS else "SHA256SUMS-linux.txt"
    if sums_name in assets:
        sums = fetch(assets[sums_name]).decode("utf-8", "replace")
        wanted = next((line.split()[0].lower() for line in sums.splitlines() if line.strip().endswith(name)), None)
        if wanted and hashlib.sha256(data).hexdigest() != wanted:
            raise RuntimeError(f"{name} does not match its published checksum: nothing was changed.")
    folder = os.path.join(kit, "downloads", "updates")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with open(path, "wb") as handle:
        handle.write(data)
    prune_updates(kit, keep=(path,), log=log)
    return path


def prune_updates(kit, keep=(), log=print):
    """(2026-11-21, Yumainai) downloads/updates only ever grew: every release zip stayed. An update is unpacked straight
    after its download and never read again, so only the newest launcher and the newest server download are kept
    (plus anything in `keep`). Returns the bytes freed."""
    folder = os.path.join(kit, "downloads", "updates")
    if not os.path.isdir(folder):
        return 0
    files = [os.path.join(folder, n) for n in os.listdir(folder)]
    files = [f for f in files if os.path.isfile(f)]
    keep = {os.path.normcase(os.path.abspath(k)) for k in keep}
    newest = {}
    for f in sorted(files, key=os.path.getmtime, reverse=True):
        kind = "server" if "-server-" in os.path.basename(f).lower() else "launcher"
        newest.setdefault(kind, f)
    keep |= {os.path.normcase(os.path.abspath(f)) for f in newest.values()}
    freed = 0
    for f in files:
        if os.path.normcase(os.path.abspath(f)) in keep:
            continue
        try:
            size = os.path.getsize(f)
            os.remove(f)
            freed += size
        except OSError:
            pass
    if freed:
        log(f"Removed old update downloads ({freed // (1024 * 1024)} MB).")
    return freed


def _unpack_tar(tar_path, dest, keep=(), log=print):
    """Linux: the .tar.gz's single top folder over dest. Each file is written beside its target and renamed into place,
    so even the running launcher can be replaced; programs keep their run permission."""
    import tarfile
    count = 0
    with tarfile.open(tar_path, "r:*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            head, _, rest = member.name.partition("/")
            if not rest:
                continue
            parts = rest.split("/")
            if ".." in parts or rest.startswith("/"):
                raise RuntimeError("refusing a path outside the folder: " + member.name)
            if rest in keep:
                continue
            target = os.path.join(dest, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.extractfile(member) as src, open(target + ".part", "wb") as out:
                shutil.copyfileobj(src, out)
            os.chmod(target + ".part", 0o755 if member.mode & 0o111 else 0o644)
            os.replace(target + ".part", target)
            count += 1
    log(f"{count} files updated.")
    return count


def _unpack(zip_path, dest, keep=(), log=print, running_exe=None):
    """Unpacks the zip's single top folder over dest. A file in keep is never replaced. The running exe is renamed
    out of the way first (Windows lets a running program be renamed, not replaced)."""
    if not zip_path.lower().endswith(".zip"):
        return _unpack_tar(zip_path, dest, keep=keep, log=log)
    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            head, _, rest = info.filename.partition("/")
            if not rest or info.is_dir():
                continue
            parts = rest.split("/")
            if ".." in parts or ":" in rest:
                raise RuntimeError("refusing a path outside the folder: " + info.filename)
            if rest in keep:
                continue
            target = os.path.join(dest, *parts)
            if running_exe and os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(running_exe)):
                old = target[:-4] + ".old.exe"
                if os.path.exists(old):
                    try:
                        os.remove(old)
                    except OSError:               # still running (an old launcher or one of its helpers): move it aside
                        os.replace(old, target[:-4] + f".old-{int(time.time())}.exe")
                os.replace(target, old)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as src, open(target + ".part", "wb") as out:
                shutil.copyfileobj(src, out)
            os.replace(target + ".part", target)
            count += 1
    log(f"{count} files updated.")
    return count


def cleanup_old_exes(kit):
    """Deletes the launcher copies an update moved aside (XI Forever Offline.old.exe, .old-<time>.exe). Called when the
    launcher starts (the old one has closed by then) and before an update. One still running is left for next time."""
    running = os.path.normcase(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else None
    removed = 0
    try:
        names = os.listdir(kit)
    except OSError:
        return 0
    for name in names:
        low = name.lower()
        if low.endswith(".exe") and (low.endswith(".old.exe") or ".old-" in low):
            path = os.path.join(kit, name)
            if running and os.path.normcase(os.path.abspath(path)) == running:
                continue
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed


def update_kit(kit, release, fetch, log=print):
    """Installs a kit release over the kit folder. Returns True: the launcher must restart."""
    cleanup_old_exes(kit)                         # leftovers from an update made while an old copy was still running
    path = _download(release, KIT_ASSET, kit, fetch, log, "launcher")
    running = sys.executable if getattr(sys, "frozen", False) else None
    _unpack(path, kit, log=log, running_exe=running)
    return True


def player_tables(server_dir):
    """The player tables from the server's own dbtool.py, else the list above."""
    try:
        with open(os.path.join(server_dir, "tools", "dbtool.py"), encoding="utf-8") as handle:
            text = handle.read()
        block = text[text.index("player_data = ["):]
        block = block[:block.index("]")]
        found = re.findall(r'"([a-z_0-9]+)\.sql"', block)
        if found:
            return found
    except (OSError, ValueError):
        pass
    return list(PLAYER_DATA)


def update_database(cfg, server_dir, log=print, run=None, connect=None):
    """Like 'dbtool.py update': import every SQL file again except the player tables that exist, then run the migrations."""
    import subprocess
    import launcher_setup as setup
    run = run or subprocess.run
    mdb, port, pw = cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), cfg["db_pass"]
    existing = set(setup.sql(mdb, port, cfg["db_user"], pw, "SHOW TABLES", database=cfg["db_name"], run=run).split())
    protected = {t + ".sql" for t in player_tables(server_dir) if t in existing}
    files = [f for f in setup.import_order(server_dir)
             if not (os.path.dirname(f) == os.path.join(server_dir, "sql") and os.path.basename(f) in protected)]
    log(f"Database: importing {len(files)} files (your {len(protected)} player tables are kept)...")
    setup.import_sql(mdb, port, pw, files, log=log, run=run)
    folder = os.path.join(server_dir, "tools", "migrations")
    if not os.path.isdir(folder):
        return
    if connect is None:
        import mariadb
        connect = lambda: mariadb.connect(host="127.0.0.1", port=port, user=cfg["db_user"], password=pw, database=cfg["db_name"])
    db = connect()
    cur = db.cursor()
    ran = 0
    try:
        for name in sorted(n for n in os.listdir(folder) if n.endswith(".py")):
            spec = importlib.util.spec_from_file_location("migration_" + name[:-3], os.path.join(folder, name))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.check_preconditions(cur)
            if module.needs_to_run(cur):
                log("Database: " + module.migration_name())
                module.migrate(cur, db)
                ran += 1
        db.commit()
    finally:
        db.close()
    log(f"Database up to date ({ran} migration(s) run).")


def update_server(kit, cfg, release, fetch, log=print, run=None, connect=None):
    """Saves the database, installs a server release over the server folder, updates the database."""
    import subprocess
    import launcher_setup as setup
    run = run or subprocess.run
    server = cfg["server_dir"]
    path = _download(release, SERVER_ASSET, kit, fetch, log, "server")
    backups = os.path.join(kit, "backups")
    os.makedirs(backups, exist_ok=True)
    dump = os.path.join(backups, f"db-before-{release.get('tag_name')}-{time.strftime('%Y%m%d-%H%M%S')}.sql")
    log("Saving your database first...")
    result = run(setup.mariadb_cmd(cfg["mariadb_dir"], "mariadb-dump") + ["-h127.0.0.1", f"-P{cfg.get('db_port', 3306)}",
                  f"-u{cfg['db_user']}", f"-p{cfg['db_pass']}", "--single-transaction", cfg["db_name"], f"--result-file={dump}"],
                 capture_output=True, text=True, creationflags=NO_WINDOW,
                 **({} if IS_WINDOWS else {"env": setup.mariadb_env(cfg["mariadb_dir"])}))
    if result.returncode != 0:
        raise RuntimeError("Could not save the database, so nothing was changed: " + (result.stderr or "")[-300:])
    _unpack(path, server, keep=("settings/network.lua",), log=log)
    update_database(cfg, server, log=log, run=run, connect=connect)
    log(f"Server updated to {release.get('tag_name')}. Your database from before is in {dump}.")

# Tools a server release depends on: when the kit pins another version (thirdparty.json "tag"), the installed copy is
# replaced. xiloader has to match the server (Phoenix's server from 2026-11 refuses any xiloader older than 3.0).
PINNED_REFRESH = ("xiloader", "ashita", "proton", "umu")      # (proton and umu: Linux only)


def refresh_pinned(kit, cfg, fetch, log=print, ids=PINNED_REFRESH):
    """Reinstalls pinned tools whose recorded version differs from the pin. Returns the ids reinstalled."""
    import launcher_thirdparty as tp
    state = tp.load_state(kit)
    done = []
    for item in tp.load_manifest(kit):
        source = item.get("source", {})
        tag = source.get("tag") or source.get("ref") or (source.get("version") if source.get("type") == "kit" else None)
        have = (state.get(item["id"]) or {}).get("version")
        # pinned tools always; items marked refresh_if_installed (Nameplate shipped with the kit) only when installed
        wanted = item.get("id") in ids or (item.get("refresh_if_installed") and have)
        if not wanted or not tag or tag == "latest":
            continue
        if have == tag:
            continue
        log(f"{item['name']}: updating {have or 'the installed copy'} to {tag} (this release needs it)...")
        tp.install(item, kit, cfg.get("ashita_dir"), fetch=fetch, log=log, server=cfg.get("server_dir"))
        done.append(item["id"])
    return done
