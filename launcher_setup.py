"""First-run setup for players (no GUI code here, so every step can be tested on its own).

Runs only when the kit has no config.json: it finds Final Fantasy XI, installs Ashita and the chosen add-ons from their
official releases, sets up a portable MariaDB inside the kit folder (no Windows service, no admin rights), creates the
database and the game account, writes the server's database settings, the Ashita boot file and script, rates.json and
config.json. An existing install (a config.json is present) never comes here.
"""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import zipfile

# XIFO_TEST_PLATFORM=windows: the stand-in tests check the Windows paths on a Linux machine
IS_WINDOWS = os.name == "nt" or os.environ.get("XIFO_TEST_PLATFORM") == "windows"
IS_LINUX = sys.platform.startswith("linux") and not IS_WINDOWS
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
MARIADB_SERIES = "11.4"                                # long-term support series
MARIADB_API = "https://downloads.mariadb.org/rest-api/mariadb/{series}/latest"
MARIADB_PAGE = "https://mariadb.org/download/"
BOOT_NAME = "xiforever.ini"
SCRIPT_NAME = "xiforever.txt"
DB_NAME = "xiforever"
DB_USER = "xi"

# ----- finding things -----
FFXI_REGISTRY = [(r"SOFTWARE\WOW6432Node\PlayOnlineUS\InstallFolder", "0001"),
                 (r"SOFTWARE\WOW6432Node\PlayOnlineEU\InstallFolder", "0001"),
                 (r"SOFTWARE\WOW6432Node\PlayOnline\InstallFolder", "0001"),
                 (r"SOFTWARE\PlayOnlineUS\InstallFolder", "0001"),
                 (r"SOFTWARE\PlayOnline\InstallFolder", "0001")]
FFXI_GUESSES = [r"C:\Program Files (x86)\PlayOnline\SquareEnix\FINAL FANTASY XI",
                r"C:\Program Files\PlayOnline\SquareEnix\FINAL FANTASY XI",
                r"C:\PlayOnline\SquareEnix\FINAL FANTASY XI",
                r"D:\PlayOnline\SquareEnix\FINAL FANTASY XI"]


def valid_ffxi(path):
    return bool(path) and os.path.isfile(os.path.join(path, "FFXiMain.dll"))


def find_ffxi():
    """The FINAL FANTASY XI folder from the PlayOnline registry entry, else a usual place, else None."""
    try:
        import winreg
        for key, value in FFXI_REGISTRY:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as handle:
                    path = winreg.QueryValueEx(handle, value)[0]
                if valid_ffxi(path):
                    return path
            except OSError:
                continue
    except ImportError:          # not Windows (tests)
        pass
    for path in FFXI_GUESSES:
        if valid_ffxi(path):
            return path
    return None


def valid_server(path):
    program = "xi_map.exe" if IS_WINDOWS else "xi_map"
    return bool(path) and os.path.isfile(os.path.join(path, program)) and os.path.isdir(os.path.join(path, "sql"))


def default_layout(kit):
    return {"ashita_dir": os.path.join(kit, "Ashita"), "server_dir": os.path.join(kit, "server"),
            "mariadb_dir": os.path.join(kit, "mariadb")}


def free_port(preferred=3306, tries=20):
    """preferred if nothing listens there, else the next free one (another MariaDB or MySQL may already use 3306)."""
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free port for the database near 3306.")


def new_password(length=16):
    return secrets.token_urlsafe(length)[:length]


def valid_login(name):
    """LandSandBoat logins: 3-16 letters and numbers."""
    return bool(re.fullmatch(r"[A-Za-z0-9]{3,16}", name or ""))


# ----- portable MariaDB -----
def mariadb_package_wanted(name, linux=None):
    """Windows: the -winx64.zip. Linux: the x86_64 binary tarball (MariaDB's own build for any distro)."""
    linux = (not IS_WINDOWS) if linux is None else linux
    if "debug" in name:
        return False
    if linux:
        return bool(re.search(r"-linux-(systemd-)?x86_64\.tar\.gz$", name))
    return name.endswith("-winx64.zip")


def resolve_mariadb(fetch, linux=None):
    """The newest MariaDB package for this system in the long-term support series: {"version", "url", "name",
    "sha256"}. Windows: the zip. Linux: the binary tarball."""
    data = json.loads(fetch(MARIADB_API.format(series=MARIADB_SERIES)))
    releases = data.get("releases") or {}
    for version in sorted(releases, key=lambda v: [int(x) for x in re.findall(r"\d+", v)], reverse=True):
        for item in releases[version].get("files", []):
            name = item.get("file_name", "")
            if mariadb_package_wanted(name, linux):
                digest = (item.get("checksum") or {}).get("sha256sum")
                url = item.get("file_download_url") or ""
                if url.startswith("http://") and not IS_WINDOWS:     # (Linux: always https)
                    url = "https://" + url[len("http://"):]
                return {"version": version, "url": url, "name": name, "sha256": digest}
    raise RuntimeError(f"No MariaDB package for this system found; download it from {MARIADB_PAGE} and unpack it "
                       "into the mariadb folder.")


def unpack_single_folder(zip_path, dest):
    """Unpacks a zip whose files are all inside one top folder, without that folder."""
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            head, _, rest = info.filename.partition("/")
            if not rest or info.is_dir():
                continue
            parts = rest.split("/")
            if ".." in parts or ":" in rest:
                raise RuntimeError("refusing a path outside the folder: " + info.filename)
            target = os.path.join(dest, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def unpack_single_folder_tar(tar_path, dest):
    """Linux: unpacks a .tar.gz whose files are all inside one top folder, without that folder. Keeps the programs'
    run permission and the library links inside the package; refuses anything that would land outside dest."""
    import tarfile
    real = os.path.realpath(dest)
    with tarfile.open(tar_path, "r:*") as archive:
        for member in archive.getmembers():
            head, _, rest = member.name.partition("/")
            if not rest:
                continue
            parts = rest.split("/")
            if ".." in parts or rest.startswith("/"):
                raise RuntimeError("refusing a path outside the folder: " + member.name)
            target = os.path.join(dest, *parts)
            if not os.path.realpath(target).startswith(real + os.sep):
                raise RuntimeError("refusing a path outside the folder: " + member.name)
            if member.isdir():
                os.makedirs(target, exist_ok=True)
            elif member.issym():
                link = member.linkname
                if link.startswith("/") or not os.path.realpath(os.path.join(os.path.dirname(target), link)).startswith(real + os.sep):
                    continue                                 # a link pointing outside the package: left out
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if os.path.lexists(target):
                    os.remove(target)
                os.symlink(link, target)
            elif member.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with archive.extractfile(member) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(target, member.mode & 0o755 | 0o644)


def unpack_package(path, dest):
    if path.lower().endswith(".zip"):
        unpack_single_folder(path, dest)
    else:
        unpack_single_folder_tar(path, dest)


def mariadb_exe(mariadb_dir, name):
    if IS_WINDOWS:
        return os.path.join(mariadb_dir, "bin", name + ".exe")
    for folder in ("bin", "scripts"):                       # Linux tarball: mariadb-install-db is in scripts/
        path = os.path.join(mariadb_dir, folder, name)
        if os.path.isfile(path):
            return path
    return os.path.join(mariadb_dir, "bin", name)


def mariadb_cmd(mariadb_dir, name):
    """A MariaDB program and, on Linux, --no-defaults first (never read a system MariaDB's /etc/my.cnf)."""
    return [mariadb_exe(mariadb_dir, name)] + ([] if IS_WINDOWS else ["--no-defaults"])


def mariadb_env(mariadb_dir):
    """Linux: the package's own libraries first; the system's otherwise (not the packaged launcher's)."""
    if IS_WINDOWS:
        return None
    env = dict(os.environ)
    try:
        import launcher_linux
        launcher_linux.fix_frozen_environment(env)
    except ImportError:
        pass
    libs = [os.path.join(mariadb_dir, "lib")]
    if env.get("LD_LIBRARY_PATH"):
        libs.append(env["LD_LIBRARY_PATH"])
    env["LD_LIBRARY_PATH"] = os.pathsep.join(libs)
    return env


# Linux: MariaDB's generic package is built on an older Linux and wants a few old libraries that newer systems dropped
# (libaio.so.1 on Ubuntu 24.04, libcrypt.so.1 and old ncurses on Arch / SteamOS). The release build copies them from
# Ubuntu 22.04 into the kit's lib/mariadb-compat; only the ones this system lacks go into mariadb/lib.
COMPAT_LIBS = ("lib", "mariadb-compat")
MARIADB_PROGRAMS = ("mariadbd", "mariadb", "mariadb-admin", "mariadb-dump", "my_print_defaults")


def missing_libs(mariadb_dir):
    """Linux: the libraries MariaDB's programs need that this system can't find (ldd's "not found"), in order."""
    if IS_WINDOWS:
        return []
    missing = []
    for name in MARIADB_PROGRAMS:
        exe = mariadb_exe(mariadb_dir, name)
        if not os.path.isfile(exe):
            continue
        try:
            out = subprocess.run(["ldd", exe], capture_output=True, text=True, errors="replace", env=mariadb_env(mariadb_dir),
                                 timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            return []                                  # no ldd: MariaDB itself says what is wrong when it starts
        for line in out.splitlines():
            if "=> not found" in line:
                lib = line.split("=>")[0].strip()
                if lib and lib not in missing:
                    missing.append(lib)
    return missing


def fill_missing_libs(mariadb_dir, compat_dir, log=print):
    """Linux: copy the old libraries this system lacks from compat_dir into mariadb/lib (only those, so the system's
    own newer libraries are never replaced). Repeats because a copied library can need another one (libncurses.so.5
    needs libtinfo.so.5). Returns the libraries still missing."""
    if IS_WINDOWS:
        return []
    lib = os.path.join(mariadb_dir, "lib")
    missing = missing_libs(mariadb_dir)
    for _ in range(4):
        fixable = [name for name in missing if os.path.isfile(os.path.join(compat_dir, name))
                   and not os.path.exists(os.path.join(lib, name))]
        if not fixable:
            break
        os.makedirs(lib, exist_ok=True)
        for name in fixable:
            shutil.copy2(os.path.join(compat_dir, name), os.path.join(lib, name))
        log("MariaDB: added " + ", ".join(fixable) + " (old libraries this Linux doesn't have).")
        missing = missing_libs(mariadb_dir)
    return missing


def socket_path(mariadb_dir, port):
    """Linux: the server's local socket inside the mariadb folder (short enough), else in /tmp."""
    path = os.path.join(mariadb_dir, "mariadb.sock")
    return path if len(path.encode()) < 100 else f"/tmp/xiforever-mariadb-{port}.sock"


def _as_root():
    return not IS_WINDOWS and hasattr(os, "geteuid") and os.geteuid() == 0


def no_space_path(path, cache=None):
    """Linux: MariaDB's mariadb-install-db is a shell script that splits --basedir/--datadir at spaces ("XI Forever
    Offline" -> "XI", "Forever"...: Sunie, Fedora, 2026-11-18), so it gets a link to the same folder without spaces."""
    if IS_WINDOWS or not any(c.isspace() for c in path):
        return path
    import hashlib
    roots = [cache] if cache else [os.path.join(os.path.expanduser("~"), ".cache", "xi-forever-offline"), "/tmp/xi-forever-offline"]
    for root in roots:
        if any(c.isspace() for c in root):
            continue
        link = os.path.join(root, "mariadb-" + hashlib.sha1(os.path.abspath(path).encode("utf-8")).hexdigest()[:10])
        try:
            os.makedirs(root, exist_ok=True)
            if os.path.islink(link) and os.path.realpath(link) != os.path.realpath(path):
                os.remove(link)
            if not os.path.islink(link):
                os.symlink(os.path.abspath(path), link)
            return link
        except OSError:
            continue
    return path


def init_mariadb(mariadb_dir, root_password, port, run=subprocess.run):
    """Creates the data folder once (mariadb-install-db)."""
    data = os.path.join(mariadb_dir, "data")
    if os.path.isdir(os.path.join(data, "mysql")):
        return "The database folder already exists."
    if IS_WINDOWS:
        cmd = [mariadb_exe(mariadb_dir, "mariadb-install-db"), f"--datadir={data}", f"--password={root_password}",
               f"--port={port}"]
    else:   # Linux: root starts with no password; set_root_password() gives it one once the server runs
        base = no_space_path(mariadb_dir)          # (the script can't take paths with spaces)
        cmd = mariadb_cmd(base, "mariadb-install-db") + [
            f"--basedir={base}", f"--datadir={os.path.join(base, 'data')}", "--auth-root-authentication-method=normal",
            "--skip-test-db", "--loose-innodb-buffer-pool-size-max=2G"] + (["--user=root"] if _as_root() else [])   # (passed on to the server: see start_mariadb)
    result = run(cmd, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW,
                 **({} if IS_WINDOWS else {"env": mariadb_env(mariadb_dir), "cwd": base}))
    if result.returncode != 0:
        out = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
        saved = ""
        if len(out) > 700:      # the middle is cut below, and that is often where the reason is: keep all of it in a file
            try:
                with open(os.path.join(mariadb_dir, "install-db.log"), "w", encoding="utf-8", errors="replace") as f:
                    f.write(out + "\n")
                saved = " (all of it: %s)" % os.path.join(mariadb_dir, "install-db.log")
            except OSError:
                pass
        raise RuntimeError("mariadb-install-db failed" + saved + ": "
                           + (out if len(out) <= 700 else out[:350] + " ... " + out[-350:]))
    return "Database folder created."


def set_root_password(mariadb_dir, port, root_password, run=subprocess.run):
    """Linux: a new database's root accounts have no password yet; give every one of them this install's.
    Returns False when root already needed a password (done before)."""
    try:
        hosts = sql(mariadb_dir, port, "root", "", "SELECT host FROM mysql.user WHERE user = 'root'", run=run).split()
    except RuntimeError:
        return False
    statements = " ".join(f"ALTER USER 'root'@{quote(host)} IDENTIFIED BY {quote(root_password)};" for host in hosts)
    if statements:
        sql(mariadb_dir, port, "root", "", statements + " FLUSH PRIVILEGES;", run=run)
    return True


def aria_logs_broken(mariadb_dir):
    """True when the newest MariaDB error log says its Aria logs could not be replayed (a PC that lost power or a
    database that was killed): "Aria recovery failed ... delete all aria_log.######## files"."""
    data = os.path.join(mariadb_dir, "data")
    try:
        logs = [os.path.join(data, n) for n in os.listdir(data) if n.lower().endswith(".err")]
    except OSError:
        return False
    if not logs:
        return False
    newest = max(logs, key=os.path.getmtime)
    try:
        with open(newest, "rb") as f:
            f.seek(max(0, os.path.getsize(newest) - 20000))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    last = tail.rfind("Aria recovery failed")
    return last >= 0 and "ready for connections" not in tail[last:]


def set_aria_logs_aside(mariadb_dir):
    """MariaDB's own advice for a failed Aria recovery: the aria_log files go (moved to mariadb/aria-logs-<time>, not
    deleted), and the server checks its Aria tables itself when it starts. Returns how many files were moved."""
    data = os.path.join(mariadb_dir, "data")
    keep = os.path.join(mariadb_dir, "aria-logs-" + time.strftime("%Y%m%d-%H%M%S"))
    moved = 0
    for name in os.listdir(data):
        if name.lower().startswith("aria_log"):
            os.makedirs(keep, exist_ok=True)
            shutil.move(os.path.join(data, name), os.path.join(keep, name))
            moved += 1
    return moved


def start_mariadb(mariadb_dir, port, popen=subprocess.Popen, wait=30, _retry=True):
    """Starts the portable server in the background if nothing answers on its port. Returns the process (or None).
    If it stops at once because its Aria logs are broken, the logs are set aside and it is started once more."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", int(port))) == 0:
            return None
    data = os.path.join(mariadb_dir, "data")
    linux = [] if IS_WINDOWS else [f"--basedir={mariadb_dir}", f"--socket={socket_path(mariadb_dir, port)}",
                                   f"--pid-file={os.path.join(data, 'mariadb.pid')}",
                                   f"--log-error={os.path.join(data, 'mariadb.err')}",
                                   # (2026-11-23, ザックス: "Cannot map innodb_buffer_pool_size_max=8388608m") newer 11.4 builds
                                   # reserve address space for an 8 TB buffer pool by default, which a system with limited
                                   # virtual memory refuses; 2 GB is far more than this server uses. "loose-": a build without
                                   # the option ignores it instead of refusing to start.
                                   "--loose-innodb-buffer-pool-size-max=2G"] + (["--user=root"] if _as_root() else [])
    proc = popen(mariadb_cmd(mariadb_dir, "mariadbd") + linux + [
                  f"--datadir={data}", f"--port={port}",
                  "--bind-address=127.0.0.1",
                  # write the log to disk once a second instead of after every statement: the map server waits on each
                  # database write, and a slow disk then made its watchdog stop it (seen 2026-11-11 with 500 bots)
                  "--innodb-flush-log-at-trx-commit=2"], cwd=mariadb_dir, creationflags=NO_WINDOW,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 **({} if IS_WINDOWS else {"env": mariadb_env(mariadb_dir), "start_new_session": True}))
    for _ in range(wait * 2):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", int(port))) == 0:
                return proc
        if getattr(proc, "poll", None) and proc.poll() is not None:
            break                                     # it stopped already (its .err says why): no use waiting
        time.sleep(0.5)
    if _retry and aria_logs_broken(mariadb_dir) and set_aria_logs_aside(mariadb_dir):
        return start_mariadb(mariadb_dir, port, popen, wait, _retry=False)
    raise RuntimeError("The database did not start (see " + os.path.join("mariadb", "data", "*.err") + ").")


def stop_mariadb(mariadb_dir, port, root_password, run=subprocess.run):
    run(mariadb_cmd(mariadb_dir, "mariadb-admin") + ["-h127.0.0.1", f"-P{port}", "-uroot", f"-p{root_password}", "shutdown"],
        capture_output=True, creationflags=NO_WINDOW, **({} if IS_WINDOWS else {"env": mariadb_env(mariadb_dir)}))


def sql(mariadb_dir, port, user, password, statement, database=None, run=subprocess.run):
    """Runs SQL with the MariaDB command-line client that came in the zip (no Python database driver needed)."""
    cmd = mariadb_cmd(mariadb_dir, "mariadb") + ["-h127.0.0.1", f"-P{port}", f"-u{user}"] + \
        ([f"-p{password}"] if password or IS_WINDOWS else []) + ["--batch", "--skip-column-names", "-e", statement]
    if database:
        cmd.insert(-2, database)
    result = run(cmd, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW,
                 **({} if IS_WINDOWS else {"env": mariadb_env(mariadb_dir)}))
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip()[-500:] or "SQL failed")
    return result.stdout


def quote(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def create_database(mariadb_dir, port, root_password, db_password, run=subprocess.run):
    # Linux: utf8mb4 from the start (the server warns about latin1, MariaDB's own default; Windows installs unchanged)
    charset = "" if IS_WINDOWS else " CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
    sql(mariadb_dir, port, "root", root_password,
        f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}`{charset}; "
        f"CREATE USER IF NOT EXISTS {quote(DB_USER)}@'localhost' IDENTIFIED BY {quote(db_password)}; "
        f"CREATE USER IF NOT EXISTS {quote(DB_USER)}@'127.0.0.1' IDENTIFIED BY {quote(db_password)}; "
        f"GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO {quote(DB_USER)}@'localhost'; "
        f"GRANT ALL PRIVILEGES ON `{DB_NAME}`.* TO {quote(DB_USER)}@'127.0.0.1'; FLUSH PRIVILEGES;", run=run)


def import_order(server_dir):
    """The server's SQL files in the order its own tools/dbtool.py imports them: sql/*.sql sorted with triggers.sql
    last, then each module in modules/init.txt (a folder: every .sql under it, sorted)."""
    sql_dir = os.path.join(server_dir, "sql")
    files = sorted(os.path.join(sql_dir, f) for f in os.listdir(sql_dir) if f.endswith(".sql"))
    triggers = os.path.join(sql_dir, "triggers.sql")
    if triggers in files:
        files.remove(triggers)
        files.append(triggers)
    init = os.path.join(server_dir, "modules", "init.txt")
    if os.path.exists(init):
        with open(init, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                path = os.path.join(server_dir, "modules", line)
                if os.path.isdir(path):
                    found = []
                    for root, _dirs, names in os.walk(path):
                        found += [os.path.join(root, n) for n in names if n.endswith(".sql")]
                    files += sorted(found, key=lambda p: p.replace("\\", "/"))
                elif line.endswith(".sql") and os.path.exists(path):
                    files.append(path)
    return files


def import_sql(mariadb_dir, port, db_password, files, log=print, run=subprocess.run):
    for index, path in enumerate(files, 1):
        source = path.replace("\\", "/")
        if index % 20 == 1 or index == len(files):
            log(f"Database: importing {index}/{len(files)} ({os.path.basename(path)})...")
        sql(mariadb_dir, port, DB_USER, db_password,
            f"SET SESSION lock_wait_timeout=120; SET autocommit=0; SET unique_checks=0; SET foreign_key_checks=0; "
            f"SOURCE {source}; "
            "SET unique_checks=1; SET foreign_key_checks=1; COMMIT;", database=DB_NAME, run=run)


def trigger_names(server_dir):
    """The triggers the server's sql/triggers.sql creates (the map server stops at start when one is missing)."""
    import re
    path = os.path.join(server_dir, "sql", "triggers.sql")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as handle:
        return re.findall(r"CREATE\s+TRIGGER\s+`?(\w+)`?", handle.read(), re.IGNORECASE)


def ensure_triggers(cfg, server_dir, log=print, run=subprocess.run):
    """Re-creates the server's triggers when any is missing (an update run by an older launcher could lose them:
    its Squad tab held a table lock while triggers.sql was re-imported). Returns the names that were missing."""
    wanted = trigger_names(server_dir)
    if not wanted:
        return []
    mdb, port, pw = cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), cfg["db_pass"]
    have = set(sql(mdb, port, cfg.get("db_user", DB_USER), pw,
                   "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA = DATABASE()",
                   database=cfg.get("db_name", DB_NAME), run=run).split())
    missing = [name for name in wanted if name not in have]
    if missing:
        log("Database: putting back missing triggers (" + ", ".join(missing) + ")...")
        import_sql(mdb, port, pw, [os.path.join(server_dir, "sql", "triggers.sql")], log=lambda m: None, run=run)
    return missing


def module_sql_files(server_dir):
    """The modules' own SQL files (modules/init.txt), in import order."""
    base = os.path.join(server_dir, "modules") + os.sep
    return [path for path in import_order(server_dir) if path.startswith(base)]


def module_tables(server_dir):
    """The tables the modules' SQL files create (squad_mate, guild_shop_state, ...)."""
    import re
    tables = []
    for path in module_sql_files(server_dir):
        try:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        tables += re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", text, re.IGNORECASE)
    return tables


def ensure_module_tables(cfg, server_dir, log=print, run=subprocess.run):
    """(2026-11-22, NRDTheGamer: the Squads page said "Table 'xiforever.squad_mate' doesn't exist") A setup whose
    database import was cut short after the game's own tables leaves the modules' tables out, and nothing put them in
    afterwards: no squad, no guild shop stock. When a table that a module's SQL file creates is missing, every module
    SQL file is imported again (they are written to be imported at each update). Returns the tables that were missing."""
    wanted = module_tables(server_dir)
    if not wanted:
        return []
    mdb, port, pw = cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), cfg["db_pass"]
    have = set(sql(mdb, port, cfg.get("db_user", DB_USER), pw, "SHOW TABLES",
                   database=cfg.get("db_name", DB_NAME), run=run).split())
    missing = [name for name in wanted if name not in have]
    if missing:
        log("Database: tables are missing (" + ", ".join(missing) + "); importing the add-on data again...")
        import_sql(mdb, port, pw, module_sql_files(server_dir), log=lambda m: None, run=run)
    return missing


def create_account(mariadb_dir, port, db_password, login, password, run=subprocess.run):
    """The player's game account. PASSWORD() is MariaDB's own hash: the login server accepts it and turns it into
    bcrypt the first time you log in (src/login/auth_session.cpp)."""
    if not valid_login(login):
        raise ValueError("The login must be 3-16 letters and numbers.")
    existing = sql(mariadb_dir, port, DB_USER, db_password, f"SELECT id FROM accounts WHERE login = {quote(login)}",
                   database=DB_NAME, run=run).strip()
    if existing:
        return f"The account '{login}' already exists."
    sql(mariadb_dir, port, DB_USER, db_password,
        "INSERT INTO accounts (id, login, password, timecreate, timelastmodify, status, priv) "
        f"SELECT GREATEST(1000, IFNULL(MAX(id), 0) + 1), {quote(login)}, PASSWORD({quote(password)}), NOW(), NOW(), 1, 1 "
        "FROM accounts WHERE id < 21000000",          # (below the bot accounts)
        database=DB_NAME, run=run)
    return f"Created the account '{login}'."


# ----- files -----
def set_lua_values(text, values):
    """Replaces KEY = value lines in a LandSandBoat settings file (strings quoted, numbers as they are)."""
    for key, value in values.items():
        literal = str(value) if isinstance(value, int) else "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"
        text, count = re.subn(r"(?m)^(\s*" + re.escape(key) + r"\s*=\s*)('[^']*'|\"[^\"]*\"|-?\d+)", lambda m: m.group(1) + literal, text, count=1)
        if count == 0:
            raise RuntimeError(f"{key} was not found in the server's network settings.")
    return text


def write_network_settings(server_dir, port, db_password):
    """settings/network.lua with this install's database login. An existing file is never replaced."""
    target = os.path.join(server_dir, "settings", "network.lua")
    if os.path.exists(target):
        return "settings/network.lua already exists - left as it is."
    with open(os.path.join(server_dir, "settings", "default", "network.lua"), encoding="utf-8-sig") as handle:
        text = handle.read()
    text = set_lua_values(text, {"SQL_HOST": "127.0.0.1", "SQL_PORT": int(port), "SQL_LOGIN": DB_USER,
                                 "SQL_PASSWORD": db_password, "SQL_DATABASE": DB_NAME})
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return "Wrote settings/network.lua."


def write_boot(ashita_dir, login, password):
    """config/boot/xiforever.ini from Ashita's private-server example: xiloader, this PC, the new account."""
    boot_dir = os.path.join(ashita_dir, "config", "boot")
    target = os.path.join(boot_dir, BOOT_NAME)
    if os.path.exists(target):
        return f"{BOOT_NAME} already exists - left as it is."
    with open(os.path.join(boot_dir, "example-privateserver.ini"), encoding="utf-8-sig") as handle:
        text = handle.read()
    lines = {"name": "XI: Forever Offline", "file": ".\\\\bootloader\\\\xiloader.exe",
             "command": f"--server 127.0.0.1 --user {login} --pass {password}", "script": SCRIPT_NAME}
    for key, value in lines.items():
        text, count = re.subn(r"(?m)^(" + key + r"\s*=\s*).*$", lambda m: m.group(1) + value, text, count=1)
        if count == 0:
            raise RuntimeError(f"Ashita's example boot file has no '{key}' line.")
    with open(target, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)
    return f"Wrote config/boot/{BOOT_NAME}."


def write_script(ashita_dir, interface, addons=(), plugins=()):
    """scripts/xiforever.txt: Ashita's default script plus the chosen interface and add-ons."""
    scripts = os.path.join(ashita_dir, "scripts")
    target = os.path.join(scripts, SCRIPT_NAME)
    if os.path.exists(target):
        return f"{SCRIPT_NAME} already exists - left as it is."
    try:
        with open(os.path.join(scripts, "default.txt"), encoding="utf-8-sig") as handle:
            lines = handle.read().splitlines()
    except OSError:
        lines = ["/load thirdparty", "/load addons", "/load screenshot"]
    lines = ["# Managed by the XI: Forever Offline launcher (Addons tab)."] + lines
    loads = [f"/load {p}" for p in plugins] + [f"/addon load {a}" for a in addons]
    if interface == "xiui":
        loads.append("/addon load xiui")
    elif interface == "xiuiplus":
        loads.append("/load XIUIplus")
    present = {line.strip().lower() for line in lines}
    lines += [line for line in loads if line.lower() not in present]
    with open(target, "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write("\n".join(lines) + "\n")
    return f"Wrote scripts/{SCRIPT_NAME}."


def write_config(kit, values):
    """config.json from config.example.json with this install's values. Never replaces an existing one."""
    target = os.path.join(kit, "config.json")
    if os.path.exists(target):
        raise RuntimeError("config.json already exists.")
    with open(os.path.join(kit, "config.example.json"), encoding="utf-8-sig") as handle:
        cfg = json.load(handle)
    cfg.update(values)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(cfg, handle, indent=2)
    os.replace(tmp, target)
    return cfg


# ----- the first-time setup, run again on an install (Sunie, 2026-11-22: "restart installation") -----
# SYSTEM > Settings > "Run setup again..." opens the setup window with this install's folders filled in. Every step of
# run_setup keeps what is already there (the database and its tables, the account, Ashita's boot file and script, the
# server's network settings, the Rules), so the only thing that had to change is the end: config.json is updated,
# not written new. The database folder is never asked for and never moves.
def same_path(a, b):
    if not a or not b:
        return False
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def again_choices(kit, cfg):
    """What the setup window starts from when it is run again: this install's own folders, account and world."""
    layout = default_layout(kit)
    return {"ffxi_dir": cfg.get("ffxi_client_dir") or "", "ashita_dir": cfg.get("ashita_dir") or layout["ashita_dir"],
            "server_dir": cfg.get("server_dir") or layout["server_dir"],
            "mariadb_dir": cfg.get("mariadb_dir") or layout["mariadb_dir"],
            "login": cfg.get("game_user") or "player1", "password": cfg.get("game_pass") or "",
            "world": cfg.get("world") or "living"}


def update_config(kit, values, drop=()):
    """config.json of an existing install with these values changed and everything else as it was. The file from
    before is kept next to it as config.json.before-setup-again (the newest one only)."""
    target = os.path.join(kit, "config.json")
    with open(target, encoding="utf-8-sig") as handle:
        text = handle.read()
    cfg = json.loads(text)
    with open(target + ".before-setup-again", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    cfg.update(values)
    for key in drop:
        cfg.pop(key, None)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(cfg, handle, indent=2)
    os.replace(tmp, target)
    return cfg


# ----- the kit's own addons -----
# (2026-11-19) "Gambits" is now the squad Rule Set editor (wildcabbagepatch's Gambits v2, first shipped as GambitsV2);
# the addon that had the name before (your own character's rules, Parser, EXP Watch, Enemy Info) is "autobox".
OWN_ADDONS = ("Gambits", "autobox", "followme", "servermenu", "squadpanel", "stinkshell", "autora", "hcicons")
STOCK_ADDONS = ("distance", "fps", "move", "timestamp", "tparty", "checker", "drawdistance", "allmaps")
STOCK_PLUGINS = ("minimap",)
START_ADDONS = ("Gambits", "servermenu", "crystalboy")          # loaded at startup on a new install
# (2026-11-21) Tetra Master (art: Nalfey): <kit>\tetramaster is copied into Ashita when the kit has it, and turned on
# at startup once (new installs and existing ones). Only the files the addon uses are copied: the sound effects as .wav,
# the music as .mp3 (the .wav music and the .mp3 sound effects in Nalfey's asset pack are left out).
TM_ADDON = "tetramaster"
TM_SKIP = ("*.before-*", "*.bak", "mus_quadmist.wav", "snd_*.mp3", "screenshots")


def migrate_gambits_names(kit, ashita_dir, log=print):
    """One time, on an install from before 2026-11-19: Ashita\\addons\\Gambits still holds the old engine (now "autobox")
    and the squad editor may sit in addons\\GambitsV2. Both are moved to <kit>\\backups\\addons, the new Gambits and autobox
    are copied in, and the start scripts follow: the main window keeps "/addon load Gambits" (now the squad editor; a
    GambitsV2 line is dropped), the second window (dualbox.txt), whose character is driven by the old engine, loads
    autobox instead. Player sheets stay where they are (config\\addons\\Gambits). Returns the messages."""
    addons = os.path.join(ashita_dir, "addons")
    if not os.path.isdir(addons):
        return []
    old = os.path.join(addons, "Gambits")
    v2 = os.path.join(addons, "GambitsV2")
    old_engine = os.path.isdir(old) and not os.path.exists(os.path.join(old, "squad_editor.lua"))
    if not old_engine and not os.path.isdir(v2):
        return []
    if not os.path.exists(os.path.join(kit, "addons-src", "Gambits", "squad_editor.lua")) or \
            not os.path.exists(os.path.join(kit, "addons-src", "autobox", "autobox.lua")):
        return []                                  # (this kit does not have the renamed addons: leave everything alone)
    keep = os.path.join(kit, "backups", "addons")
    os.makedirs(keep, exist_ok=True)
    tag = time.strftime("%Y%m%d-%H%M%S")
    messages = []
    if old_engine:
        shutil.move(old, os.path.join(keep, f"Gambits-before-autobox-{tag}"))
    if os.path.isdir(v2):
        shutil.move(v2, os.path.join(keep, f"GambitsV2-{tag}"))
    for name in ("Gambits", "autobox"):
        shutil.copytree(os.path.join(kit, "addons-src", name), os.path.join(addons, name), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.before-*", "*.bak"))
    scripts = os.path.join(ashita_dir, "scripts")
    line_re = re.compile(r"^(\s*/addon\s+load\s+)(\S+)\s*$", re.I)
    for name in (os.listdir(scripts) if os.path.isdir(scripts) else []):
        if not name.lower().endswith(".txt"):
            continue
        path = os.path.join(scripts, name)
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue
        second = name.lower() == "dualbox.txt"
        out, changed = [], False
        loaded = {m.group(2).lower() for m in (line_re.match(x) for x in lines) if m}
        for line in lines:
            m = line_re.match(line)
            addon = m.group(2).lower() if m else ""
            if addon == "gambitsv2":
                changed = True
                if "gambits" not in loaded and not second:
                    out.append(m.group(1) + "Gambits")
                    loaded.add("gambits")
                continue
            switch = re.match(r"^\s*/gambits\s+(on|off)\s*$", line, re.I)
            if switch and old_engine:               # a start-up "/gambits off" was meant for the old engine
                changed = True
                if second:
                    out.append("/autobox " + switch.group(1).lower())
                continue
            if addon == "gambits" and second and old_engine:
                changed = True
                if "autobox" not in loaded:
                    out.append(m.group(1) + "autobox")
                    loaded.add("autobox")
                continue
            out.append(line)
        if changed:
            with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
                handle.write("\n".join(out).rstrip("\n") + "\n")
    messages.append("Gambits is now the squad Rule Set editor (/gambits). Your own character's rules moved to the add-on "
                    "'autobox' (/autobox): switch it on in OPTIONS > Addons if you use them. Your sheets are untouched.")
    for line in messages:
        log(line)
    return messages


def install_own_addons(kit, ashita_dir):
    """Copies the kit's addons (addons-src, crystalboy) into Ashita and makes Crystal Boy's folders."""
    addons = os.path.join(ashita_dir, "addons")
    for name in OWN_ADDONS:
        src = os.path.join(kit, "addons-src", name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(addons, name), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.before-*", "*.bak"))
    src = os.path.join(kit, "crystalboy")
    if os.path.isdir(src):
        shutil.copytree(src, os.path.join(addons, "crystalboy"), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.before-*", "*.bak"))
        cfg = os.path.join(ashita_dir, "config", "addons", "crystalboy")
        for folder in ("roms", "system", "saves", "states", "claims", "snaps"):
            os.makedirs(os.path.join(cfg, folder), exist_ok=True)
        rewards = os.path.join(cfg, "rewards.lua")
        if not os.path.exists(rewards) and os.path.exists(os.path.join(src, "rewards_default.lua")):
            shutil.copy2(os.path.join(src, "rewards_default.lua"), rewards)
        install_free_games(kit, cfg)
    src = os.path.join(kit, TM_ADDON)
    if os.path.isfile(os.path.join(src, TM_ADDON + ".lua")):
        shutil.copytree(src, os.path.join(addons, TM_ADDON), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*TM_SKIP))


def enable_new_addons(kit, ashita_dir, boot_name, log=print):
    """Turns Tetra Master on for the main window ONCE per install, when the kit has it: an existing install gets it
    with the update, and a player who switches it off later (OPTIONS > Addons) keeps it off. The marker file
    <Ashita>/config/addons/tetramaster/enabled-once.txt remembers that it was done."""
    if not os.path.isfile(os.path.join(kit, TM_ADDON, TM_ADDON + ".lua")):
        return False
    import launcher_core as core
    marker = os.path.join(ashita_dir, "config", "addons", TM_ADDON, "enabled-once.txt")
    if os.path.exists(marker) or not os.path.isdir(os.path.join(ashita_dir, "addons", TM_ADDON)):
        return False
    manager = core.ScriptManager(ashita_dir, boot_name)
    manager.prepare()
    if TM_ADDON not in {a.lower() for a in manager.enabled("addon")}:
        manager.set("addon", TM_ADDON, True)
        log("Tetra Master is now on (type /tm in game; turn it off in OPTIONS > Addons).")
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w", encoding="utf-8") as handle:
        handle.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
    return True


def enable_hcicons(ashita_dir, boot_name, log=print):
    """(2026-11-23) The hardcore / randomized icons (addons-src/hcicons) are part of the game modes, like the server's
    rules: the launcher puts the add-on back on at every PLAY (the user: it has to always be on)."""
    import launcher_core as core
    if not os.path.isdir(os.path.join(ashita_dir, "addons", "hcicons")):
        return False
    manager = core.ScriptManager(ashita_dir, boot_name)
    manager.prepare()
    if "hcicons" not in {a.lower() for a in manager.enabled("addon")}:
        manager.set("addon", "hcicons", True)
        log("Hardcore icons are on (Iron / Steel / Silver / Random over their heads).")
    return True


# The free games this loader copied into <Ashita>\config\addons\crystalboy\roms, one file name per line, so the
# next run knows what it may delete again. A player's own ROMs are never listed here.
FREE_MANIFEST = "FREE-GAMES-MANIFEST.txt"

# Games earlier builds shipped. They are removed when the current set is installed, so every player's folder ends up
# with exactly the games in <kit>\crystalboy-games (the owner's rule, 2026-11-19: the Jueno games are the standard).
RETIRED_FREE_GAMES = ("Aevilia.gbc", "Airaki.gb", "Labirinth.gbc", "GBHack.gbc")


def install_free_games(kit, crystalboy_cfg):
    """Make Crystal Boy's roms folder match <kit>\\crystalboy-games.

    A shipped game is copied over whatever is there (so an old or damaged copy is replaced), a game this kit used to
    ship is deleted (RETIRED_FREE_GAMES plus whatever the last run listed in FREE-GAMES-MANIFEST.txt), and anything
    else in the folder -- the player's own ROMs -- is left alone. Returns the names it copied."""
    src = os.path.join(kit, "crystalboy-games")
    roms = os.path.join(crystalboy_cfg, "roms")
    if not os.path.isdir(src):
        return []
    os.makedirs(roms, exist_ok=True)
    games = sorted(n for n in os.listdir(src) if n.lower().endswith((".gb", ".gbc")))
    manifest = os.path.join(roms, FREE_MANIFEST)
    stale = set(RETIRED_FREE_GAMES)
    try:
        with open(manifest, encoding="utf-8") as f:
            stale.update(line.strip() for line in f if line.strip() and not line.startswith("#"))
    except OSError:
        pass
    for name in sorted(stale - set(games)):
        path = os.path.join(roms, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass                    # read-only or open in game: try again next launch
    added = []
    for name in games:
        dest = os.path.join(roms, name)
        same = os.path.isfile(dest) and os.path.getsize(dest) == os.path.getsize(os.path.join(src, name))
        shutil.copy2(os.path.join(src, name), dest)
        if not same:
            added.append(name)
    try:
        with open(manifest, "w", encoding="utf-8", newline="\n") as f:
            f.write("# The free games this kit put in this folder (removed again when the kit stops shipping them).\n")
            f.write("# Your own ROMs are never listed here, and never touched. One file name per line.\n")
            for name in games:
                f.write(name + "\n")
    except OSError:
        pass
    for name in ("CREDITS.md",):
        if os.path.exists(os.path.join(src, name)):
            shutil.copy2(os.path.join(src, name), os.path.join(roms, "FREE-GAMES-" + name))
    return added


# ----- the whole setup -----
def run_setup(kit, choices, tp, log=print, fetch=None, run=subprocess.run, popen=subprocess.Popen, again=None):
    """choices: ffxi_dir, ashita_dir, server_dir, mariadb_dir, world, population, interface, extras (list of
    thirdparty ids), login, password. Every step can be run again: what is already there is kept.
    again: the install's config.json when setup is run again from the launcher (see update_config above); the
    database stays where it is, and the account, the world and the Rules are not touched."""
    import launcher_core as core
    fetch = fetch or tp._get
    items = {item["id"]: item for item in tp.load_manifest(kit)}
    if again:
        start = again_choices(kit, again)
        choices["mariadb_dir"] = start["mariadb_dir"]
        choices["login"], choices["password"], choices["world"] = start["login"], start["password"], start["world"]
        log("Setup again: your world, characters and settings are kept.")
    ashita, server, mdb = choices["ashita_dir"], choices["server_dir"], choices["mariadb_dir"]

    log("1/9 Final Fantasy XI...")
    game = choices.get("game", "existing")      # copy | existing | official (launcher_game.py)
    extra_cfg, drop_cfg = {}, []
    # setup again with the game folder this install already uses: nothing about the game is changed (and a copy in
    # the kit's Game folder is never copied onto itself)
    same_game = bool(again) and same_path(choices.get("ffxi_dir"), again.get("ffxi_client_dir")) and valid_ffxi(choices.get("ffxi_dir"))
    if same_game:
        log("   The game folder is the one already in use.")
        game = "same"
    elif not IS_WINDOWS:                        # Linux: the game comes from a folder (copied from a Windows PC)
        import launcher_game as lg
        import launcher_linux as ll
        ffxi, viewer = ll.find_game_parts(choices.get("ffxi_dir"))
        if not ffxi or not viewer:
            raise RuntimeError("That folder doesn't have both FINAL FANTASY XI and PlayOnlineViewer in it. Choose the "
                               "SquareEnix folder (it has both), from a Windows PC or from the game installed here through Steam or Proton.")
        lang = ll.detect_lang(viewer)
        if game == "copy":
            paths = lg.copy_install(ffxi, viewer, os.path.join(kit, "Game"), log=log)
            ffxi, viewer = paths["ffxi"], paths["viewer"]
        choices["ffxi_dir"] = ffxi
        extra_cfg.update({"game_copy": game == "copy", "pol_dir": viewer, "pol_lang": lang})
        game = "linux"
    if game == "official" and not valid_ffxi(choices.get("ffxi_dir")):
        import launcher_game as lg
        found = find_ffxi()
        if not valid_ffxi(found):
            files = lg.download_official(kit, log=log, context=tp.ssl_context())
            lg.run_official_installer(kit, files, log=log, popen=popen)
            found = find_ffxi()
            if not valid_ffxi(found):
                raise RuntimeError("FINAL FANTASY XI isn't installed yet. Finish Square Enix's installer (it may still be "
                                   "open), then press Install again; the download is kept.")
        choices["ffxi_dir"] = found
        extra_cfg["game_update_needed"] = not update_game_files(kit, found, log=log, context=tp.ssl_context())
    if not valid_ffxi(choices.get("ffxi_dir")):
        raise RuntimeError("That folder is not FINAL FANTASY XI (FFXiMain.dll is missing). Install the game first.")
    if game == "copy":
        import launcher_game as lg
        lang = lg.detect_lang(choices["ffxi_dir"])
        viewer = lg.find_viewer(choices["ffxi_dir"], lang)
        if not viewer:
            raise RuntimeError("The PlayOnline folder that goes with that FFXI folder wasn't found, so the game can't be "
                               "copied. Choose 'Use my installed FFXI' instead.")
        paths = lg.copy_install(choices["ffxi_dir"], viewer, os.path.join(kit, "Game"), log=log)
        choices["ffxi_dir"] = paths["ffxi"]
        extra_cfg.update({"game_copy": True, "pol_dir": paths["viewer"], "pol_lang": lang})
    elif again and game == "existing":
        # setup again, pointed at another installed game: the same as SYSTEM > Settings > "Change game folder"
        # (at PLAY the launcher points PlayOnline at these folders). Without a PlayOnlineViewer next to it, it is
        # used the way a first-time "use my installed FFXI" is: through PlayOnline's own settings.
        import launcher_game as lg
        try:
            ffxi, viewer = lg.pick_game_folder(choices["ffxi_dir"], again.get("pol_lang") or "US")
            choices["ffxi_dir"] = ffxi
            extra_cfg.update({"game_copy": True, "pol_dir": viewer})
        except ValueError:
            extra_cfg["game_copy"] = False
            drop_cfg.append("pol_dir")

    log("2/9 The game server...")
    if not valid_server(server):
        try:
            tp.install(items["server"], kit, ashita, fetch=fetch, log=log, server=server)
        except Exception as problem:
            if not IS_WINDOWS and "no file matching" in str(problem):
                # (Sunie, 2026-11-18) the Linux server is built on GitHub after each release and arrives about 40 minutes
                # later; until then the release has only the Windows files
                raise RuntimeError("The Linux server for the newest version is still being built (it arrives about 40 "
                                   "minutes after a release). Wait a little and press Install again.")
            raise RuntimeError(f"The server files could not be downloaded ({problem}). Check the internet connection, "
                               "or choose a folder with a built server.")
    for iid in ("vcredist", "vcredist86"):       # (Windows only) 64-bit: server and database; 32-bit: xiloader, Ashita
        if iid in items and not tp.status(items[iid], kit, ashita)[0]:
            tp.install(items[iid], kit, ashita, fetch=fetch, log=log, run=run)
    log("   Ashita and xiloader...")
    for iid in ("ashita", "xiloader"):
        if not tp.status(items[iid], kit, ashita)[0]:
            tp.install(items[iid], kit, ashita, fetch=fetch, log=log)
    if not IS_WINDOWS:
        log("   Proton (runs the game on Linux, about 550 MB)...")
        for iid in ("umu", "proton"):
            if iid in items and not tp.status(items[iid], kit, ashita)[0]:
                tp.install(items[iid], kit, ashita, fetch=fetch, log=log)
    log("3/9 Add-ons...")
    wanted = [choices["interface"]] if choices.get("interface") in ("xiui", "xiuiplus") else []
    for iid in wanted + list(choices.get("extras", [])):
        item = items.get(iid)
        if item and item["source"]["type"] not in ("page", "installer") and not tp.status(item, kit, ashita)[0]:
            try:
                tp.install(item, kit, ashita, fetch=fetch, log=log)
            except Exception as problem:             # an optional add-on never stops the setup
                log(f"{item['name']} was not installed ({problem}); get it later on the Downloads tab.")
    install_own_addons(kit, ashita)
    if choices.get("era_dats", True):                 # Phoenix's era game files, with a backup of the originals
        try:
            if not tp.status(items["eradats"], kit, ashita)[0]:
                tp.install(items["eradats"], kit, ashita, fetch=fetch, log=log)
            for line in install_era_dats(kit, choices["ffxi_dir"], log=log):
                log(line)
        except Exception as problem:
            log(f"The Era-DATs were not installed ({problem}); do it later on the Downloads tab.")
    import launcher_client                            # Home Point teleport, Crystal Boy items, Chariot Band (never stops setup)
    launcher_client.apply_all(kit, choices["ffxi_dir"], server, log=log)
    if choices.get("world") == "living_ai":           # the AI: Ollama, then the model (about 8 GB) - never stops the setup
        try:
            if not tp.find_ollama():
                tp.install(items["ollama"], kit, ashita, fetch=fetch, log=log, run=run)
            if not tp.status(items["aimodel"], kit, ashita)[0]:
                log("Getting the AI model (about 8 GB, this takes a while)...")
                tp.install(items["aimodel"], kit, ashita, fetch=fetch, log=log)
        except Exception as problem:
            log(f"The AI is not ready ({problem}). Finish it later on the launcher's Downloads tab (Ollama, then the AI model).")

    log("4/9 Database program (MariaDB)...")
    if not os.path.isfile(mariadb_exe(mdb, "mariadbd")):
        found = resolve_mariadb(fetch)
        log(f"Downloading MariaDB {found['version']}...")
        folder = os.path.join(kit, "downloads", "mariadb")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, found["name"])
        # (2026-11-23, Art-Machine: setup sat on "Downloading MariaDB" with no sign of life) streamed to disk on Windows
        # too: a progress line every 10%, a stalled mirror gives up after 60 s instead of 30 minutes, a second try
        # carries on from the part already downloaded, and a zip already in downloads\mariadb is used as it is.
        log(f"   (from {found['url'].split('/')[2] if '//' in found['url'] else 'mariadb.org'}; about 100 MB on Windows)")
        tp.download_file(found["url"], path, log=log, sha256=found.get("sha256"), fetch=fetch)
        unpack_package(path, mdb)
    if not IS_WINDOWS:
        still = fill_missing_libs(mdb, os.path.join(kit, *COMPAT_LIBS), log=log)
        if still:
            raise RuntimeError("MariaDB can't run on this Linux: it is missing " + ", ".join(still) + ". Please post "
                               "this message in #linux-bugs on our Discord (with your Linux and its version).")
    secrets_file = os.path.join(mdb, "xiforever-db.json")       # the database passwords of this install (git-ignored)
    if os.path.exists(secrets_file):
        with open(secrets_file, encoding="utf-8") as handle:
            keys = json.load(handle)
    else:
        keys = {"root": new_password(), "xi": new_password(), "port": free_port()}
        with open(secrets_file, "w", encoding="utf-8") as handle:
            json.dump(keys, handle)
    log(init_mariadb(mdb, keys["root"], keys["port"], run=run))
    proc = start_mariadb(mdb, keys["port"], popen=popen)
    try:
        if not IS_WINDOWS:
            set_root_password(mdb, keys["port"], keys["root"], run=run)
        log("5/9 Database and tables (a few minutes)...")
        create_database(mdb, keys["port"], keys["root"], keys["xi"], run=run)
        tables = sql(mdb, keys["port"], DB_USER, keys["xi"], "SHOW TABLES LIKE 'accounts'", database=DB_NAME, run=run).strip()
        if not tables:
            import_sql(mdb, keys["port"], keys["xi"], import_order(server), log=log, run=run)
        else:
            log("The tables are already there.")
        log("6/9 Your game account...")
        log(create_account(mdb, keys["port"], keys["xi"], choices["login"], choices["password"], run=run))
    finally:
        stop_mariadb(mdb, keys["port"], keys["root"], run=run)
        if proc is not None:
            try:
                proc.wait(timeout=20)
            except Exception:
                proc.kill()

    log("7/9 Server settings...")
    log(write_network_settings(server, keys["port"], keys["xi"]))
    log("8/9 Ashita boot file and script...")
    log(write_boot(ashita, choices["login"], choices["password"]))
    if "xipivot" in choices.get("extras", []):          # chosen at setup: XIPivot (a PlayOnline-stage plugin) on
        try:
            import launcher_core
            launcher_core.set_polplugin(os.path.join(ashita, "config", "boot", BOOT_NAME), "pivot", True)
            launcher_core.pivot_first_config(ashita)
            log("XIPivot turned on in the boot file.")
        except Exception as e:
            log(f"Could not turn XIPivot on ({e}).")
    addons = list(STOCK_ADDONS) + list(START_ADDONS) + [a for a in ("mobdb", "chains") if a in choices.get("extras", [])]
    plugins = list(STOCK_PLUGINS) + (["Nameplate"] if "nameplate" in choices.get("extras", []) else [])
    if not IS_WINDOWS:                                   # Ashita's own fix for Wine (Proton)
        import launcher_linux as ll
        plugins += [line.split()[-1] for line in ll.wine_plugin_lines(ashita)]
    log(write_script(ashita, choices.get("interface"), addons, plugins))

    log("9/9 Your settings...")
    rates = core.apply_world(dict(core.RATE_DEFAULTS), choices["world"], choices["population"])
    if not os.path.exists(core.rates_path(kit)):
        core.save_rates(kit, rates)
    if again:
        # only where things are; the account, the database login and the world stay as config.json has them
        values = {"server_dir": server, "ffxi_client_dir": choices["ffxi_dir"], "ashita_dir": ashita, **extra_cfg}
        if not same_path(ashita, again.get("ashita_dir")):
            values["ashita_boot"] = BOOT_NAME
        cfg = update_config(kit, values, drop=drop_cfg)
    else:
        cfg = write_config(kit, {
            "server_dir": server, "ffxi_client_dir": choices["ffxi_dir"], "ashita_dir": ashita, "ashita_boot": BOOT_NAME,
            "db_name": DB_NAME, "db_user": DB_USER, "db_pass": keys["xi"], "db_port": keys["port"],
            "game_user": choices["login"], "game_pass": choices["password"],
            "mariadb_dir": mdb, "mariadb_service": "", "world": choices["world"], **extra_cfg})
    if not IS_WINDOWS:                                    # the game's own Windows folder in Proton (PLAY tries again)
        import launcher_linux as ll
        try:
            ll.prepare_prefix(kit, cfg, log=log)
        except Exception as problem:
            log(f"Proton isn't ready yet ({problem}). PLAY tries again; send logs/proton-setup.log if it keeps failing.")
    if extra_cfg.get("game_update_needed"):
        log("One more step before your first PLAY: log in to PlayOnline once with your Square Enix account (a free "
            "trial works) so it can update the game. The launcher shows you how when it opens.")
    log("Setup finished.")
    return cfg


# ----- used by the launcher on every Play (portable installs only) -----
def portable_keys(cfg):
    with open(os.path.join(cfg["mariadb_dir"], "xiforever-db.json"), encoding="utf-8") as handle:
        return json.load(handle)


def start_portable(cfg, popen=subprocess.Popen):
    """Starts the kit's MariaDB if it is not running yet. Returns the process this call started, or None."""
    return start_mariadb(cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), popen=popen)


def stop_portable(cfg, run=subprocess.run):
    try:
        stop_mariadb(cfg["mariadb_dir"], int(cfg.get("db_port", 3306)), portable_keys(cfg)["root"], run=run)
    except (OSError, ValueError, KeyError):
        pass


def existing_case(base, rel):
    """The path of rel under base with the letter case already on disk (Linux: a game folder copied from Windows may
    say rom2 where the Era-DATs say ROM2; Wine treats both as one name, so writing a second one would be ambiguous)."""
    if IS_WINDOWS:
        return os.path.join(base, rel)
    path = base
    for part in rel.replace("\\", "/").split("/"):
        candidate = os.path.join(path, part)
        if not os.path.exists(candidate):
            try:
                low = part.lower()
                candidate = next((os.path.join(path, n) for n in os.listdir(path) if n.lower() == low), candidate)
            except OSError:
                pass
        path = candidate
    return path


def update_game_files(kit, ffxi_dir, log=print, context=None, update=None):
    """(2026-11-23) Square Enix's installer puts in the April 2019 game: bring it up to date from XI: Forever Offline's
    own release of the game files (launcher_gamefiles.py). True when the game is up to date; False (with a message)
    when it couldn't be done, so the PlayOnline login and update stays the way to update it."""
    import launcher_game as lg
    import launcher_gamefiles as gf
    log("   Updating the game to the newest version (only the files that changed since Square Enix's installer)...")
    try:
        lang = lg.detect_lang(ffxi_dir)
        viewer = lg.find_viewer(ffxi_dir, lang)
        if not viewer:
            raise RuntimeError("the PlayOnline folder that goes with the game wasn't found")
        (update or gf.update)(kit, ffxi_dir, viewer, log=log, context=context)
        return True
    except Exception as problem:
        log(f"   The game couldn't be updated from XI: Forever Offline's download ({problem}). PlayOnline can update it "
            "instead; the launcher shows you how. Or press Install again to try the download again: finished parts are kept.")
        return False


# ----- Phoenix's Era-DATs (the same steps and backup layout as install-era-dats.ps1 / restore-original-dats.ps1) -----
def reapply_era_dats(ffxi_dir, era_dir, backup, files, log=print):
    """(2026-11-19, Altair) The Era-DATs are installed already (dat-backup exists), but a PlayOnline/FFXI update wrote its
    own files over some of them. Copies back only the era files that differ. A game file that is neither the era file nor
    the saved original is a newer original from the update: it replaces the saved one, so restore-original-dats.ps1
    still gives back the current game files."""
    import filecmp
    changed = 0
    for index, rel in enumerate(files, 1):
        src, dest = os.path.join(era_dir, rel), existing_case(ffxi_dir, rel)
        if os.path.exists(dest) and filecmp.cmp(src, dest, shallow=False):
            continue
        saved = os.path.join(backup, rel)
        if os.path.exists(dest) and not (os.path.exists(saved) and filecmp.cmp(saved, dest, shallow=False)):
            if os.path.exists(saved) or os.path.exists(dest):
                os.makedirs(os.path.dirname(saved), exist_ok=True)
                shutil.copy2(dest, saved)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        changed += 1
        if index % 500 == 0:
            log(f"Era-DATs: checked {index}/{len(files)}")
    if changed == 0:
        return ["The Era-DATs are installed and up to date."]
    return [f"Era-DATs put back: {changed} file(s) a game update had replaced (the update's files are saved in dat-backup)."]


def _era_files(era_dir):
    files = []
    for rom in ("ROM", "ROM2", "ROM3", "ROM4"):
        for root, _dirs, names in os.walk(os.path.join(era_dir, rom)):
            files += [os.path.relpath(os.path.join(root, n), era_dir) for n in names]
    return files


def _era_state_path(kit):
    return os.path.join(kit, "backups", "era-state.json")


def check_era_dats(kit, ffxi_dir, log=print):
    """(2026-11-19, Yumainai, Altair) An FFXI/PlayOnline update quietly writes retail files over the era ones (wrong monster
    names, Home Points that freeze...). On every PLAY: files whose size/time changed since the last PLAY are compared with
    the era copy, and the ones an update replaced are put back (reapply_era_dats). Nothing happens when the era files were
    never installed or were removed on purpose (no dat-backup). Returns the messages."""
    import filecmp, json
    era_dir, backup = os.path.join(kit, "Era-DATs"), os.path.join(kit, "dat-backup")
    if not ffxi_dir or not os.path.isdir(backup) or not os.path.isdir(os.path.join(ffxi_dir, "ROM")):
        return []
    files = _era_files(era_dir)
    if not files:
        return []
    try:
        with open(_era_state_path(kit), "r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, ValueError):
        state = {}
    drifted = []
    for rel in files:
        dest = existing_case(ffxi_dir, rel)
        try:
            st = os.stat(dest)
        except OSError:
            drifted.append(rel)
            continue
        if state.get(rel) == [st.st_size, st.st_mtime_ns]:
            continue
        src = os.path.join(era_dir, rel)
        if st.st_size != os.path.getsize(src) or not filecmp.cmp(src, dest, shallow=False):
            drifted.append(rel)
    if not drifted:
        return []
    log(f"Era-DATs: {len(drifted)} game file(s) changed since the last PLAY (a game update?) - checking them.")
    return reapply_era_dats(ffxi_dir, era_dir, backup, drifted, log)


def record_era_state(kit, ffxi_dir):
    """Remembers size and time of every era file in the game (after our own patches), so the next PLAY only looks at the
    files that changed since."""
    import json
    era_dir = os.path.join(kit, "Era-DATs")
    if not ffxi_dir or not os.path.isdir(os.path.join(kit, "dat-backup")):
        return
    state = {}
    for rel in _era_files(era_dir):
        try:
            st = os.stat(existing_case(ffxi_dir, rel))
        except OSError:
            continue
        state[rel] = [st.st_size, st.st_mtime_ns]
    path = _era_state_path(kit)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    os.replace(path + ".tmp", path)


def install_era_dats(kit, ffxi_dir, era_dir=None, log=print):
    """Copies Era-DATs\\ROM..ROM4 into the game folder. Every file it replaces is saved in <kit>\\dat-backup first and the
    new ones are listed in dat-backup\\new-files.txt, so restore-original-dats.ps1 can undo it."""
    era_dir = era_dir or os.path.join(kit, "Era-DATs")
    backup = os.path.join(kit, "dat-backup")
    if not os.path.isdir(os.path.join(ffxi_dir, "ROM")):
        raise RuntimeError("That is not the FFXI game folder (no ROM folder).")
    files = []
    for rom in ("ROM", "ROM2", "ROM3", "ROM4"):
        for root, _dirs, names in os.walk(os.path.join(era_dir, rom)):
            files += [os.path.relpath(os.path.join(root, n), era_dir) for n in names]
    if not files:
        raise RuntimeError("The Era-DATs are not downloaded yet.")
    if os.path.isdir(backup):
        return reapply_era_dats(ffxi_dir, era_dir, backup, files, log)
    new = []
    for index, rel in enumerate(files, 1):
        dest = existing_case(ffxi_dir, rel)
        if os.path.exists(dest):
            os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
            shutil.copy2(dest, os.path.join(backup, rel))
        else:
            new.append(rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(os.path.join(era_dir, rel), dest)
        if index % 500 == 0:
            log(f"Era-DATs: {index}/{len(files)}")
    os.makedirs(backup, exist_ok=True)
    with open(os.path.join(backup, "new-files.txt"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(new) + ("\n" if new else ""))
    return [f"Era-DATs installed: {len(files)} files ({len(files) - len(new)} originals saved in dat-backup)."]
