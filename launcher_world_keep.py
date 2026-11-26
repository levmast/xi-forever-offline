"""Looking after a world that runs without the launcher's window (XI: Forever Offline, open worlds, 2026-11-23): a copy
of its database every night, and its own updates with a way back. launcher_world.py calls this while a world runs; the
commands "backup", "restore" and "update" of launcher_world.py use it by hand.

Settings: world.json in the kit (made by the world's setup; every value has a default):
    backup_hour            the hour of the day (0-23, this machine's clock) after which the nightly copy is made
    backup_keep_days       nightly copies older than this are removed (the newest three always stay)
    auto_update            true: the world installs every full release by itself (never a test build)
    update_notice_minutes  how long players in the game are warned before the world restarts for an update
    update_check_minutes   how often it looks for a new release

Backups: backups/world/db-<kind>-<date>-<time>.sql.gz, the whole database, made while the world runs.

Updates: when a newer full release has its files for this system and their checksums, the world downloads and checks
them, warns the players in the game, stops, and starts again. On that start, before the game servers run: the database
is saved, every file the update will replace is copied aside, and the same updater the players' launcher uses is run.
The world then has two starts to get its map server ready. If it does not, the copied files and the database are put
back, the world starts as it was, and that release is left alone until its owner says to try again
("launcher_world.py update --retry") or a newer one is published.
"""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import launcher_coop as co                      # noqa: E402
import launcher_core as core                    # noqa: E402

WORLD_FILE = "world.json"
DEFAULTS = {"backup_hour": 4, "backup_keep_days": 7, "auto_update": True, "update_notice_minutes": 10,
            "update_check_minutes": 30}
LIMITS = {"backup_hour": (0, 23), "backup_keep_days": (1, 365), "update_notice_minutes": (0, 120),
          "update_check_minutes": (5, 1440)}
BACKUP_DIR = ("backups", "world")
BACKUP_NAME = re.compile(r"^db-(nightly|before-update|by-hand|before-erase)-(\d{8}-\d{6})\.sql\.gz$")
KEEP_AT_LEAST = 3                               # nightly copies that stay however old they are
KEEP_BEFORE_UPDATE = 2                          # copies made before an update that stay
SPARE_BYTES = 512 * 1024 * 1024                 # free disk space that must be left over after a copy or an update
REQUEST_FILE = "world-request.json"             # in logs: what the owner asked the running world to do
MAX_TRIES = 2                                   # starts an updated world gets before the update is taken back
RESTART_CODE = 75                               # the program's exit code for "start me again" (after an update)
STUCK_CODE = 78                                 # ...and for "do not start me again: a person has to look first"
SUMS_NAME = "SHA256SUMS.txt" if os.name == "nt" else "SHA256SUMS-linux.txt"
NO_WINDOW = core.NO_WINDOW


class KeepError(Exception):
    """A backup, a restore or an update could not be done. The text can be shown as it is."""


class Restart(Exception):
    """The world has to stop and be started again (its service does that): an update is waiting, or was taken back."""


class Stuck(KeepError):
    """An update could not be taken back completely. The game servers are not started on files or a database nobody
    has looked at: a person has to put it right first."""


# ----- settings -----
def load_settings(kit):
    out = dict(DEFAULTS)
    try:
        with open(os.path.join(kit, WORLD_FILE), encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {}
    if isinstance(data, dict):
        if isinstance(data.get("auto_update"), bool):
            out["auto_update"] = data["auto_update"]
        for key, (low, high) in LIMITS.items():
            try:
                out[key] = max(low, min(high, int(data[key])))
            except (KeyError, TypeError, ValueError):
                pass
    return out


def save_settings(kit, settings):
    path = os.path.join(kit, WORLD_FILE)
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as handle:
        json.dump({key: settings.get(key, DEFAULTS[key]) for key in DEFAULTS}, handle, indent=2)
        handle.write("\n")
    os.replace(path + ".part", path)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=1)
        handle.write("\n")
    os.replace(path + ".part", path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


# ----- backups -----
def backup_folder(kit):
    return os.path.join(kit, *BACKUP_DIR)


def backups(kit):
    """The copies in backups/world, newest first: {"file", "path", "kind", "time", "bytes"}."""
    folder, out = backup_folder(kit), []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        found = BACKUP_NAME.match(name)
        if not found:
            continue
        try:
            when = time.mktime(time.strptime(found.group(2), "%Y%m%d-%H%M%S"))
            size = os.path.getsize(os.path.join(folder, name))
        except (ValueError, OverflowError, OSError):
            continue
        out.append({"file": name, "path": os.path.join(folder, name), "kind": found.group(1), "time": when, "bytes": size})
    return sorted(out, key=lambda item: (item["time"], item["file"]), reverse=True)


def last_backup(kit, kind="nightly"):
    return next((item for item in backups(kit) if item["kind"] == kind), None)


def dump_command(cfg, target):
    """(command, environment or None) that writes the whole database to target with the database's own dump program."""
    env = None
    if cfg.get("mariadb_dir"):
        import launcher_setup
        tool = launcher_setup.mariadb_cmd(cfg["mariadb_dir"], "mariadb-dump")       # (Linux: never /etc/my.cnf)
        env = launcher_setup.mariadb_env(cfg["mariadb_dir"])
    else:
        tool = [shutil.which("mariadb-dump") or shutil.which("mysqldump") or "mysqldump"]
    return tool + [f"--host={cfg.get('db_host', '127.0.0.1')}", f"--port={int(cfg.get('db_port', 3306))}",
                   f"--user={cfg['db_user']}", f"--password={cfg['db_pass']}", "--single-transaction",
                   f"--result-file={target}", cfg["db_name"]], env


def _free(folder):
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


def _complete(path):
    """True when a dump file ends the way the dump program ends one it finished."""
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, os.path.getsize(path) - 400))
            return b"-- Dump completed" in handle.read()
    except OSError:
        return False


def backup_now(cfg, kit, kind="nightly", log=print, run=subprocess.run, now=None):
    """Saves the whole database into backups/world while the world runs. Returns the file. KeepError when it could not
    be made; nothing half-made is left behind."""
    folder = backup_folder(kit)
    os.makedirs(folder, exist_ok=True)
    newest = next(iter(backups(kit)), None)
    free = _free(folder)
    if free is not None and free < SPARE_BYTES + 12 * (newest["bytes"] if newest else 0):
        raise KeepError(f"The database was not saved: the disk is nearly full ({free // (1024 * 1024)} MB free).")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now if now is not None else time.time()))
    plain = os.path.join(folder, f"db-{kind}-{stamp}.sql")
    packed = plain + ".gz"
    command, env = dump_command(cfg, plain)
    try:
        result = run(command, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=1800,
                     **({"env": env} if env else {}))
        if result.returncode != 0 or not _complete(plain):
            said = (getattr(result, "stderr", "") or "").strip()[-300:]
            raise KeepError("The database could not be saved" + (f": {said}" if said else " (the copy was not finished)."))
        with open(plain, "rb") as source, gzip.open(packed + ".part", "wb", compresslevel=6) as out:
            shutil.copyfileobj(source, out, 1 << 20)
        os.replace(packed + ".part", packed)
    except KeepError:
        raise
    except Exception as e:
        raise KeepError(f"The database could not be saved ({type(e).__name__}: {e}).")
    finally:
        _remove(plain)
        _remove(packed + ".part")
    log(f"Database saved: {os.path.basename(packed)} ({os.path.getsize(packed) // (1024 * 1024)} MB).")
    return packed


def due(settings, last, now):
    """True when no nightly copy was made since the newest backup hour that has passed."""
    here = time.localtime(now)
    slot = time.mktime((here.tm_year, here.tm_mon, here.tm_mday, int(settings["backup_hour"]), 0, 0, 0, 0, -1))
    if slot > now:
        slot -= 86400
    return last < slot


def prune(kit, settings, now=None, log=print):
    """Removes nightly copies older than backup_keep_days (the newest KEEP_AT_LEAST always stay), all but the newest
    copies made before an update, and what a stopped copy left behind. Copies made by hand are never removed.
    Returns the names removed."""
    now = now if now is not None else time.time()
    removed = []
    found = backups(kit)
    nightly = [item for item in found if item["kind"] == "nightly"]
    for item in nightly[KEEP_AT_LEAST:]:
        if now - item["time"] > int(settings["backup_keep_days"]) * 86400:
            removed.append(item)
    removed += [item for item in found if item["kind"] == "before-update"][KEEP_BEFORE_UPDATE:]
    for item in removed:
        _remove(item["path"])
    names = [item["file"] for item in removed]
    folder = backup_folder(kit)
    try:
        leftovers = [n for n in os.listdir(folder) if n.startswith(("db-", "restore-")) and n.endswith((".sql", ".part"))]
    except OSError:
        leftovers = []
    for name in leftovers:
        path = os.path.join(folder, name)
        try:
            if now - os.path.getmtime(path) > 86400:
                os.remove(path)
                names.append(name)
        except OSError:
            pass
    if names:
        log("Old database copies removed: " + ", ".join(names))
    return names


def check_backup(path):
    """Reads a copy from end to end: it must unpack, hold the table of characters, and be a finished dump. KeepError
    otherwise. Returns its size unpacked."""
    size, tail, chars = 0, b"", False
    try:
        with gzip.open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                joined = tail + block
                chars = chars or b"CREATE TABLE `chars`" in joined
                tail = joined[-400:]
                size += len(block)
    except (OSError, EOFError, ValueError) as e:
        raise KeepError(f"{os.path.basename(path)} cannot be read ({type(e).__name__}): it is not used.")
    if not chars or b"-- Dump completed" not in tail:
        raise KeepError(f"{os.path.basename(path)} is not a whole copy of a world's database: it is not used.")
    return size


def restore(cfg, kit, path, log=print, run=subprocess.run):
    """Puts the database back as it was in that copy. The game servers must be stopped and the database running.
    Only for the kit's own database. The copy is read to its end before anything is changed."""
    import launcher_setup as setup
    if not cfg.get("mariadb_dir"):
        raise KeepError("Only a world with the kit's own database can be put back from a copy.")
    size = check_backup(path)
    folder = backup_folder(kit)
    free = _free(folder)
    if free is not None and free < size + SPARE_BYTES:
        raise KeepError("The database was not put back: the disk is nearly full.")
    mdb, port, name = cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), cfg["db_name"]
    if not re.fullmatch(r"\w+", name):
        raise KeepError("The database's name is not one this can put back.")
    plain = os.path.join(folder, f"restore-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.sql")
    try:
        with gzip.open(path, "rb") as source, open(plain, "wb") as out:
            shutil.copyfileobj(source, out, 1 << 20)
        charset = "" if setup.IS_WINDOWS else " CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
        try:
            setup.sql(mdb, port, "root", setup.portable_keys(cfg)["root"],
                      f"DROP DATABASE IF EXISTS `{name}`; CREATE DATABASE `{name}`{charset};", run=run)
            setup.sql(mdb, port, cfg["db_user"], cfg["db_pass"],
                      "SET SESSION lock_wait_timeout=120; SET autocommit=0; SET unique_checks=0; SET foreign_key_checks=0; "
                      f"SOURCE {plain.replace(os.sep, '/')}; SET unique_checks=1; SET foreign_key_checks=1; COMMIT;",
                      database=name, run=run)
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            raise KeepError(f"The database could not be put back from {os.path.basename(path)}: {e}")
    finally:
        _remove(plain)
    log(f"Database put back from {os.path.basename(path)}.")


# ----- starting the world over (2026-11-25, the user: "a server erase button in options that will erase everything") -----
BOT_ACCOUNT_BASE = 21000000                     # bot players' accounts start here (launcher_armory, bots.cpp)


def erase_world(cfg, kit, server_dir, log=print, run=subprocess.run, backup=None):
    """Starts the world over: every character (yours, your squads, bot players, visitors' copies), the auction house,
    linkshells, mail, server records... everything in the database goes, and the server's own tables are loaded fresh.
    Kept: your game logins (the accounts, so you sign in as before), the launcher's settings, add-ons and the character
    backup files in the kit. A full copy of the database is saved first (backups/world/db-before-erase-*.sql.gz;
    "put back" restores it). The game servers must be stopped and the kit's database running. Returns the copy's path."""
    import launcher_setup as setup
    if not cfg.get("mariadb_dir"):
        raise KeepError("Only a world with the kit's own database can be started over here.")
    mdb, port, name = cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), cfg["db_name"]
    if not re.fullmatch(r"\w+", name):
        raise KeepError("The database's name is not one this can start over.")
    files = setup.import_order(server_dir)
    if not files:
        raise KeepError("The server's SQL files were not found, so the world was not started over.")
    copy = (backup or backup_now)(cfg, kit, kind="before-erase", log=log, run=run)
    folder = backup_folder(kit)
    os.makedirs(folder, exist_ok=True)
    accounts = os.path.join(folder, f"erase-accounts-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.sql")
    try:
        # 1. the players' logins (not the bot players'), as REPLACE lines that go back in after the fresh tables
        tool, env = dump_command(cfg, accounts)
        tool = [t for t in tool if t != name and t != "--single-transaction"]
        tool += ["--no-create-info", "--replace", "--skip-triggers", f"--where=id < {BOT_ACCOUNT_BASE}", name, "accounts"]
        result = run(tool, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=600,
                     **({"env": env} if env else {}))
        if result.returncode != 0 or not _complete(accounts):
            said = (getattr(result, "stderr", "") or "").strip()[-300:]
            raise KeepError("Your logins could not be saved, so nothing was erased" + (f": {said}" if said else "."))
        # 2. an empty database, then the server's own tables, as the first setup made them
        charset = "" if setup.IS_WINDOWS else " CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
        try:
            setup.sql(mdb, port, "root", setup.portable_keys(cfg)["root"],
                      f"DROP DATABASE IF EXISTS `{name}`; CREATE DATABASE `{name}`{charset};", run=run)
            log("The world is empty. Loading the server's tables (a few minutes)...")
            for index, path in enumerate(files, 1):        # (setup.import_sql, but into this install's own database)
                if index % 20 == 1 or index == len(files):
                    log(f"Database: loading {index}/{len(files)} ({os.path.basename(path)})...")
                setup.sql(mdb, port, cfg["db_user"], cfg["db_pass"],
                          "SET SESSION lock_wait_timeout=120; SET autocommit=0; SET unique_checks=0; SET foreign_key_checks=0; "
                          f"SOURCE {path.replace(os.sep, '/')}; SET unique_checks=1; SET foreign_key_checks=1; COMMIT;",
                          database=name, run=run)
            # 3. the logins back
            setup.sql(mdb, port, cfg["db_user"], cfg["db_pass"],
                      f"SET foreign_key_checks=0; SOURCE {accounts.replace(os.sep, '/')}; SET foreign_key_checks=1;",
                      database=name, run=run)
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            raise KeepError(f"Starting over stopped part way ({e}). Put the world back from {os.path.basename(copy)} "
                            "(SYSTEM > the world's copies), or run the first-time setup's database step again.")
    finally:
        _remove(accounts)
    log(f"The world was started over. Your logins are kept; the old world is saved as {os.path.basename(copy)}.")
    return copy


# ----- the files of an update: copied aside before, put back when it has to be taken back -----
def package_files(package):
    """The files a release package holds, as paths below its single top folder."""
    out = []
    if package.lower().endswith(".zip"):
        with zipfile.ZipFile(package) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
    else:
        with tarfile.open(package, "r:*") as archive:
            names = [member.name for member in archive if member.isfile()]
    for name in names:
        _head, _sep, rest = name.partition("/")
        parts = rest.split("/")
        if not rest or ".." in parts or rest.startswith("/") or ":" in rest:
            continue                                # (the updater itself refuses such a package)
        out.append(rest)
    return out


def snapshot(package, dest, snap, keep=()):
    """Before a package is unpacked over dest: every file it will replace is copied into snap, and the files it will
    add are written down. Returns {"existing": [...], "new": [...]}."""
    if os.path.isdir(snap):
        shutil.rmtree(snap)
    existing, new = [], []
    for rel in package_files(package):
        if rel in keep:
            continue
        target = os.path.join(dest, *rel.split("/"))
        if os.path.isfile(target):
            copy = os.path.join(snap, "files", *rel.split("/"))
            os.makedirs(os.path.dirname(copy), exist_ok=True)
            shutil.copy2(target, copy)
            existing.append(rel)
        elif not os.path.lexists(target):
            new.append(rel)
    made = {"existing": existing, "new": new}
    _write_json(os.path.join(snap, "manifest.json"), made)
    return made


def snapshot_bytes(package, dest, keep=()):
    total = 0
    for rel in package_files(package):
        if rel not in keep:
            try:
                total += os.path.getsize(os.path.join(dest, *rel.split("/")))
            except OSError:
                pass
    return total


def restore_snapshot(snap, dest):
    """Puts back what snapshot() copied and removes the files the update added. Returns (put back, removed)."""
    made = _read_json(os.path.join(snap, "manifest.json"))
    if made is None:
        raise KeepError("The files from before the update are not there, so they could not be put back.")
    back = gone = 0
    for rel in made.get("existing", []):
        copy = os.path.join(snap, "files", *rel.split("/"))
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(copy, target + ".part")
        os.replace(target + ".part", target)
        back += 1
    for rel in made.get("new", []):
        target = os.path.join(dest, *rel.split("/"))
        if os.path.isfile(target):
            _remove(target)
            gone += 1
    return back, gone


# ----- updates -----
def update_folder(kit):
    return os.path.join(backup_folder(kit), "update")


def state_path(kit):
    return os.path.join(update_folder(kit), "state.json")


def skip_path(kit):
    return os.path.join(update_folder(kit), "skip.json")


def load_state(kit):
    state = _read_json(state_path(kit))
    return state if state and state.get("state") in ("pending", "applying", "applied", "trying") else None


def save_state(kit, state):
    _write_json(state_path(kit), state)


def clear_state(kit):
    _remove(state_path(kit))
    for key in ("kit", "server"):
        shutil.rmtree(os.path.join(update_folder(kit), key), ignore_errors=True)


def load_skip(kit):
    return _read_json(skip_path(kit)) or {}


def tags(found):
    """"v0.3.3" (or "launcher v0.3.3, server v0.3.4") for what an update holds."""
    kit, server = ((found.get(key) or {}).get("tag_name") for key in ("kit", "server"))
    if kit and server and kit != server:
        return f"launcher {kit}, server {server}"
    return kit or server or "?"


class Cache:
    """What the updater fetches with: files that were already downloaded and checked are read from the disk."""

    def __init__(self, fetch, files=None, texts=None):
        self.fetch, self.files, self.texts = fetch, dict(files or {}), dict(texts or {})

    def __call__(self, url, timeout=60):
        if url in self.files:
            with open(self.files[url], "rb") as handle:
                return handle.read()
        if url in self.texts:
            return self.texts[url].encode("utf-8")
        if self.fetch is None:
            raise KeepError("The update's files are not all here.")
        return self.fetch(url, timeout=timeout)


def _trim(release, installed):
    return {"tag_name": release.get("tag_name"), "from": installed,
            "assets": [{"name": a.get("name"), "browser_download_url": a.get("browser_download_url")}
                       for a in release.get("assets", [])]}


def _patterns():
    import launcher_update as lu
    return (("kit", lu.KIT_ASSET, "launcher"), ("server", lu.SERVER_ASSET, "server"))


def find_update(kit, cfg, fetch):
    """What this world should update to: {"kit": release or None, "server": release or None, "waiting": [...]}.
    Full releases only. waiting names the newer releases whose files for this system are not up yet (they are built
    a while after a release): nothing is installed until none is waiting. A release that was taken back is left out."""
    import launcher_update as lu
    info = lu.check(kit, cfg.get("server_dir"), False, fetch)
    skip = load_skip(kit)
    found = {"kit": None, "server": None, "waiting": []}
    for key, pattern, what in _patterns():
        item = info[key]
        if not item["newer"] or skip.get(key) == item["newest"]:
            continue
        names = [a.get("name") or "" for a in item["release"].get("assets", [])]
        if SUMS_NAME in names and any(re.search(pattern, name) for name in names):
            found[key] = _trim(item["release"], item["installed"])
        else:
            found["waiting"].append(f"{what} {item['newest']}")
    return found


def download(kit, found, fetch, log=print):
    """Downloads the packages of an update and checks them against the release's checksums. Returns the Cache the
    updater reads them from afterwards. KeepError when a package is not listed there or does not match."""
    import launcher_update as lu
    cache = Cache(fetch)
    for key, pattern, what in _patterns():
        release = found.get(key)
        if not release:
            continue
        assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
        name = next((n for n in assets if re.search(pattern, n)), None)
        try:
            sums = fetch(assets[SUMS_NAME]).decode("utf-8", "replace")
        except Exception as e:
            raise KeepError(f"The checksums of {what} {release['tag_name']} could not be fetched ({type(e).__name__}: {e}).")
        if not name or not any(line.split()[:1] and line.strip().endswith(name) for line in sums.splitlines()):
            raise KeepError(f"{what} {release['tag_name']} has no checksum for its download: it is not installed.")
        cache.texts[assets[SUMS_NAME]] = sums
        try:
            path = lu._download(release, pattern, kit, cache, log, what)
        except KeepError:
            raise
        except Exception as e:
            raise KeepError(f"{what} {release['tag_name']} could not be downloaded: {e}")
        cache.files[assets[os.path.basename(path)]] = path
    return cache


def selftest_command(kit):
    return core.py_cmd(os.path.join(kit, "launcher_world.py"), "selftest")


def selftest(kit, run=subprocess.run):
    """Starts the launcher that is in the kit now (after an update: the new one) just far enough to see that it can
    run a world at all. KeepError when it cannot."""
    try:
        done = run(selftest_command(kit), cwd=kit, capture_output=True, text=True, errors="replace", timeout=180,
                   creationflags=NO_WINDOW)
    except Exception as e:
        raise KeepError(f"the new launcher did not start ({type(e).__name__})")
    if done.returncode != 0 or "world selftest ok" not in (done.stdout or ""):
        said = ((done.stderr or "") + (done.stdout or "")).strip().splitlines()[-1:] or ["no answer"]
        raise KeepError("the new launcher did not start: " + said[0][:200])


def leave_alone(kit, state, why):
    """Notes that this release is not to be tried again by itself (find_update leaves it out)."""
    note = {key: (state.get(key) or {}).get("tag_name") for key in ("kit", "server") if state.get(key)}
    note.update({"why": why, "at": int(time.time())})
    _write_json(skip_path(kit), note)


def roll_back(kit, cfg, state, why, log=print, run=subprocess.run):
    """Takes an update back: the files from before, then the database from before, and a note that leaves that release
    alone from now on. Returns True when files of the launcher were put back (it has to be started again then)."""
    what = tags(state)
    log(f"The update to {what} is taken back: {why}.")
    problems, kit_back = [], False
    for key, dest in (("server", cfg.get("server_dir")), ("kit", kit)):
        snap = os.path.join(update_folder(kit), key)
        if not state.get(key) or not os.path.exists(os.path.join(snap, "manifest.json")):
            continue
        try:
            back, gone = restore_snapshot(snap, dest)
            log(f"{'Launcher' if key == 'kit' else 'Server'}: {back} files put back, {gone} new ones removed.")
            kit_back = kit_back or key == "kit"
        except Exception as e:
            problems.append(f"the {'launcher' if key == 'kit' else 'server'} files ({e})")
    if state.get("db"):
        try:
            restore(cfg, kit, state["db"], log=log, run=run)
        except Exception as e:
            problems.append(f"the database ({e})")
    leave_alone(kit, state, why)
    if problems:
        # (the state stays, with what was copied aside: nothing more is tried by itself, a person has to look)
        state.update({"state": "applying", "stuck": "; ".join(problems)})
        save_state(kit, state)
        raise Stuck(f"The update to {what} could not be taken back completely: " + "; ".join(problems)
                    + f". What was saved before it is in {update_folder(kit)} and {state.get('db')}. Put it right by "
                    "hand, then delete state.json in that folder.")
    clear_state(kit)
    return kit_back


def apply(kit, cfg, state, log=print, run=subprocess.run, connect=None, fetch=None, check=None):
    """Installs a downloaded update. The game servers are stopped and the database is running. Returns True when the
    launcher itself was updated (it has to be started again). KeepError when it could not be installed: everything is
    as it was before then, and that release is left alone from now on."""
    import launcher_update as lu
    what = tags(state)
    cache = Cache(fetch, state.get("files"), state.get("texts"))
    packages = {}
    for key, pattern, _what in _patterns():
        release = state.get(key)
        if release:
            url = next((a["browser_download_url"] for a in release["assets"] if re.search(pattern, a["name"] or "")), None)
            packages[key] = cache.files.get(url)
            if not packages[key] or not os.path.isfile(packages[key]):
                clear_state(kit)
                raise KeepError(f"The download for {what} is not there any more: the update is looked for again later.")
    places = {"server": (cfg.get("server_dir"), ("settings/network.lua",)), "kit": (kit, ())}
    need = SPARE_BYTES + sum(snapshot_bytes(path, *places[key]) + 2 * os.path.getsize(path) for key, path in packages.items())
    free = _free(kit)
    if free is not None and free < need:
        clear_state(kit)
        leave_alone(kit, state, "not enough free disk space")
        raise KeepError(f"Not enough free disk space to update to {what} safely (about {need // (1024 * 1024)} MB is needed, "
                        f"{free // (1024 * 1024)} MB is free).")
    try:
        state["db"] = backup_now(cfg, kit, "before-update", log=log, run=run)
    except KeepError as e:
        clear_state(kit)
        leave_alone(kit, state, "the database could not be saved first")
        raise KeepError(f"Not updated to {what}: {e}")
    state["state"] = "applying"
    save_state(kit, state)                          # from here on a stop in the middle is taken back at the next start
    started = time.time()
    try:
        for key, path in packages.items():
            snapshot(path, places[key][0], os.path.join(update_folder(kit), key), keep=places[key][1])
        if "server" in packages:
            log(f"Updating the server to {state['server']['tag_name']}...")
            lu.update_server(kit, cfg, state["server"], cache, log=log, run=run, connect=connect)
            _drop_plain_dumps(kit, state["server"]["tag_name"], started)
        if "kit" in packages:
            log(f"Updating the launcher to {state['kit']['tag_name']}...")
            lu.update_kit(kit, state["kit"], cache, log=log)
            (check or selftest)(kit)
    except Exception as e:
        why = str(e) or type(e).__name__
        kit_back = roll_back(kit, cfg, state, why, log=log, run=run)
        problem = KeepError(f"The update to {what} did not go in ({why}). The world is as it was before.")
        problem.restart = kit_back
        raise problem
    state.update({"state": "applied", "tries": 0, "files": {}, "texts": {}})
    save_state(kit, state)
    return "kit" in packages


def _drop_plain_dumps(kit, tag, since):
    """The players' updater saves the database too, unpacked, in backups/db-before-<tag>-<time>.sql. A world has just
    saved its own (packed, and that one is put back if need be), so the second copy of this update goes."""
    folder = os.path.join(kit, "backups")
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        path = os.path.join(folder, name)
        try:
            if name.startswith(f"db-before-{tag}-") and name.endswith(".sql") and os.path.getmtime(path) >= since - 2:
                os.remove(path)
        except OSError:
            pass


def request(kit, what, **more):
    """Asks the running world to do something at its next look (the owner's commands use this)."""
    _write_json(os.path.join(kit, "logs", REQUEST_FILE), dict(more, do=what, at=int(time.time())))


def take_request(kit):
    path = os.path.join(kit, "logs", REQUEST_FILE)
    asked = _read_json(path)
    if asked is not None or os.path.exists(path):
        _remove(path)
    return asked


class Keeper:
    """What a running world does for its backups and updates. world: launcher_world.World."""

    def __init__(self, world, fetch=None, run=subprocess.run, connect=None):
        self.world, self.kit, self.cfg = world, world.kit, world.cfg
        self.settings = load_settings(self.kit)
        self.fetch, self.run, self.connect = fetch, run, connect
        self.check = None                           # (tests stand in for the start of the new launcher)
        self.job = None                             # the one piece of work going on beside the world (a thread)
        self.results = []                           # what finished work hands back to the world's own thread
        self.lock = threading.Lock()
        self.trying = None                          # an update that is in but has not shown yet that it starts
        self.plan = None                            # a downloaded update and when the world restarts for it
        self.last_check = self.last_backup_try = 0
        self.check_now = False
        self.backup_problem = self.update_problem = ""
        self.waiting = []
        self.versioned = self.has_version()         # (a self-built copy has no version: it never looks for releases)

    def has_version(self):
        import launcher_update as lu
        return bool(lu.installed_version(self.kit) or (self.cfg.get("server_dir") and lu.installed_version(self.cfg["server_dir"])))

    def say(self, text):
        self.world.say(text)

    def get(self):
        if self.fetch is None:
            import launcher_thirdparty as tp
            self.fetch = tp._get
        return self.fetch

    def background(self, work):
        """Runs work beside the world (one at a time). Tests replace this to run it at once."""
        thread = threading.Thread(target=work, daemon=True)
        self.job = thread
        thread.start()

    def busy(self):
        if self.job is not None and not self.job.is_alive():
            self.job = None
        return self.job is not None

    # --- when the world starts: the database runs, the game servers do not yet ---
    def at_start(self):
        state = load_state(self.kit)
        if not state:
            return
        what = tags(state)
        if state["state"] == "pending":
            self.say(f"Updating to {what} before the world starts...")
            try:
                if apply(self.kit, self.cfg, state, log=self.say, run=self.run, connect=self.connect, check=self.check):
                    raise Restart(f"The launcher is now {state['kit']['tag_name']}: starting again with it.")
            except Stuck:
                raise
            except KeepError as e:
                self.update_problem = str(e)
                self.say(str(e))
                if getattr(e, "restart", False):
                    raise Restart("The launcher's files were put back: starting again with them.")
                return
            state = load_state(self.kit)
        if state and state["state"] == "applying":
            if state.get("stuck"):                  # an update that could not be taken back: nothing is tried again
                raise Stuck(f"The update to {what} could not be taken back completely: {state['stuck']}. What was saved "
                            f"before it is in {update_folder(self.kit)}. Put it right by hand, then delete state.json there.")
            self.back(state, "it was stopped in the middle")
        elif state and state.get("tries", 0) >= MAX_TRIES:
            self.back(state, f"the world did not get ready with it in {MAX_TRIES} starts")
        elif state:
            state.update({"state": "trying", "tries": int(state.get("tries", 0)) + 1})
            save_state(self.kit, state)
            self.trying = state

    def back(self, state, why):
        what = tags(state)
        kit_back = roll_back(self.kit, self.cfg, state, why, log=self.say, run=self.run)      # (Stuck stops the start)
        self.update_problem = f"The update to {what} was taken back: {why}. It is not tried again by itself."
        if kit_back:
            raise Restart("The launcher's files were put back: starting again with them.")

    def ready(self):
        """The map server said it is ready: an update that was being tried is in for good."""
        if self.trying is None:
            return
        what, self.trying = tags(self.trying), None
        clear_state(self.kit)
        _remove(skip_path(self.kit))
        self.update_problem = ""
        self.say(f"This world is now on {what}.")

    # --- while the world runs ---
    def tick(self, now):
        if self.trying is not None and core.map_ready(self.world.logs):
            self.ready()
        with self.lock:
            results, self.results = self.results, []
        for result in results:
            result()
        asked = take_request(self.kit)
        if asked and asked.get("do") == "update":
            self.check_now = True
            if asked.get("retry"):
                _remove(skip_path(self.kit))
            self.say("Looking for an update now, as asked.")
        if self.plan is not None:
            self.countdown(now)
        if self.busy():
            return
        if self.due_backup(now):
            self.last_backup_try = now
            self.background(self.backup)
        elif self.plan is None and self.trying is None and (
                self.check_now or (self.settings["auto_update"] and self.versioned and now - self.last_check >= self.settings["update_check_minutes"] * 60)):
            self.check_now, self.last_check = False, now
            self.background(self.look)

    def due_backup(self, now):
        if now - self.last_backup_try < 3600:       # (a copy that failed is tried again an hour later, not every look)
            return False
        newest = last_backup(self.kit)
        return due(self.settings, newest["time"] if newest else 0, now)

    def backup(self):
        try:
            now = self.world.clock()
            backup_now(self.cfg, self.kit, "nightly", log=self.say, run=self.run, now=now)
            prune(self.kit, self.settings, now=now, log=self.say)
            self.backup_problem = ""
        except KeepError as e:
            self.backup_problem = str(e)
            self.say(str(e))
        except Exception as e:
            self.backup_problem = f"The database was not saved ({type(e).__name__}: {e})."
            self.say(self.backup_problem)

    def look(self):
        """Is there a release to update to? If so its files are fetched and checked, and the world plans its restart."""
        try:
            found = find_update(self.kit, self.cfg, self.get())
            self.waiting = found["waiting"]
            if found["waiting"] or not (found["kit"] or found["server"]):
                return
            self.say(f"A new release is out ({tags(found)}): downloading it...")
            cache = download(self.kit, found, self.get(), log=self.say)
        except KeepError as e:
            self.update_problem = str(e)
            self.say(str(e))
            return
        except Exception as e:                      # (no internet, GitHub's limit: tried again at the next look)
            self.say(f"Could not look for an update ({type(e).__name__}: {e}).")
            return

        def planned():
            self.plan = {"found": found, "files": cache.files, "texts": cache.texts, "at": None, "said": set()}
        with self.lock:
            self.results.append(planned)

    def countdown(self, now):
        """Players in the game are warned, then the world stops to update. With nobody in the game it stops at once."""
        plan, what = self.plan, tags(self.plan["found"])
        minutes = int(self.settings["update_notice_minutes"])
        if plan["at"] is None:
            plan["at"] = now + minutes * 60
        left = plan["at"] - now
        if left > 0 and not self.world.visitors_in_game():
            left = 0                                # (nobody is in the game, or everybody logged out meanwhile)
        if left > 0:
            for mark in sorted({minutes, 5, 1}):
                if mark > minutes or left > mark * 60:
                    continue
                if mark not in plan["said"]:
                    plan["said"].update(m for m in (minutes, 5, 1) if m >= mark)
                    co.announce(self.cfg.get("server_dir"),
                                f"This world updates to {what} in {mark} minute{'' if mark == 1 else 's'}. It is back a few "
                                "minutes later; your character stays here.")
                    self.say(f"Players are told: the update to {what} starts in {mark} minute(s).")
                break
            return
        state = dict(plan["found"], state="pending", files=plan["files"], texts=plan["texts"], at=int(now))
        state.pop("waiting", None)
        save_state(self.kit, state)
        self.plan = None
        raise Restart(f"Stopping to update to {what}.")

    def status(self):
        newest = last_backup(self.kit)
        state = load_state(self.kit)
        update = {"auto": bool(self.settings["auto_update"]), "problem": self.update_problem, "waiting": list(self.waiting)}
        if self.plan is not None:
            update.update({"state": "planned", "to": tags(self.plan["found"]), "at": int(self.plan["at"] or 0)})
        elif state:
            update.update({"state": state["state"], "to": tags(state)})
        else:
            update["state"] = "none"
        return {"backup": {"last": int(newest["time"]) if newest else 0, "file": newest["file"] if newest else "",
                           "problem": self.backup_problem},
                "update": update}
