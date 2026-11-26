#!/usr/bin/env python3
"""Sets up a second game window (a second character on a second account) for multiboxing.

  python setup_dualbox.py setup               second account, second boot file, second script, and the AutoBot addon
  python setup_dualbox.py plugin              also install AutoBot's Movement plugin (a compiled DLL) - only after you have looked at it
  python setup_dualbox.py report              show what is set up
  python setup_dualbox.py window 1600 900     change the second window's size (and optionally the mode: windowed, borderless, fullscreen)
  python setup_dualbox.py enable autobot xiui turn addons on for the second window (checks the names against your addons folder)
  python setup_dualbox.py language            show the Ashita language of each boot file (1 = Japanese, 2 = English)
  python setup_dualbox.py language english    set it to English for the second window and the GM window (add --all for the main window too)

It only creates NEW things: a copy of your boot file (for example xiforever2.ini), a script (dualbox.txt), a second account, and the AutoBot files.
It never edits your main boot file, your main script or your main account. (config.json gets three new lines; the old one is kept.)
"""
import json
import os
import secrets
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

AUTOBOT_URL = "https://github.com/Buckfutt/AutoBot-Ashita"
# A new random password is made for each new install; once setup has run, config.json holds the one in use.
SECOND_USER, SECOND_PASS = "player2", "p2-" + secrets.token_hex(5)
# the second window: small, windowed, light on the PC, quiet when it is not in front
SECOND_GRAPHICS = {"screen_w": 1280, "screen_h": 720, "menu_w": 1280, "menu_h": 720, "bg_w": 1024, "bg_h": 1024,
                   "mip": 0, "bump": 0, "textures": 0, "fonts": 0, "window_mode": 1, "bg_sound": 0, "stab": 0}


def say(text=""):
    print(text, flush=True)


def config_path():
    return os.path.join(HERE, "config.json")


def load_config():
    with open(config_path(), "r", encoding="utf-8-sig") as f:
        return json.load(f)


def second_boot_name(cfg):
    if cfg.get("ashita_boot2"):
        return cfg["ashita_boot2"]
    first = cfg.get("ashita_boot", "xiforever.ini")
    root, ext = os.path.splitext(first)
    return f"{root}2{ext or '.ini'}"


def boot_file(cfg, name):
    return os.path.join(cfg["ashita_dir"], "config", "boot", name)


# ---------- the second boot file ----------
def make_second_boot(first_path, second_path, user, password, script_name, graphics_module=None):
    """A copy of the main boot file that logs in as the second account, runs its own script and opens a small window."""
    with open(first_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    text, users = re.subn(r"(--user[ =]+)(\S+)", lambda m: m.group(1) + user, text, count=1)
    text, passes = re.subn(r"(--pass[ =]+)(\S+)", lambda m: m.group(1) + password, text, count=1)
    if users == 0 or passes == 0:
        boot_section = "\n".join(line for line in text.splitlines() if re.match(r"^\s*(file|command|args|script|gamemodule)\s*=", line, re.I))
        raise RuntimeError("I could not find --user and --pass in your boot file, so I did not make a second one.\n"
                           "These are the lines I looked at:\n" + (boot_section or "(none found)"))
    text, scripts = re.subn(r"(?im)^(\s*script\s*=\s*)(.*)$", lambda m: m.group(1) + script_name, text, count=1)
    if scripts == 0:
        text = text.replace("[ashita.boot]", "[ashita.boot]\nscript = " + script_name, 1)
    with open(second_path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    if graphics_module is not None:
        values = dict(graphics_module.GRAPHICS_DEFAULTS)
        values.update(SECOND_GRAPHICS)
        graphics_module.apply_graphics(second_path, values)
    return True


ADDON_LINE = re.compile(r"^\s*/addon\s+load\s+(\S+)\s*$", re.I)
PLUGIN_LINE = re.compile(r"^\s*/load\s+(\S+)\s*$", re.I)
SCRIPT_HEADER = ["##########################################################################",
                 "# Script for the SECOND character (written by setup_dualbox.py).",
                 "# The launcher's Addons tab edits this too (List for: Second window).",
                 "##########################################################################"]
DEFAULT_ADDONS = ["autobot", "xiui"]


def ensure_script(path, addons=(), plugins=()):
    """Creates the second script if it is missing. If it exists, ONLY adds load lines that are not there yet:
    nothing you ticked or typed is ever removed or rewritten. Plugins are placed before the addons, so a plugin is loaded first."""
    lines = SCRIPT_HEADER[:]
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    live = [line for line in lines if not line.lstrip().startswith("#")]
    have_addons = {m.group(1).lower() for m in (ADDON_LINE.match(x) for x in live) if m}
    have_plugins = {m.group(1).lower() for m in (PLUGIN_LINE.match(x) for x in live) if m}
    added = []
    # (2026-11-25, Ricc) "/addon load" lines do nothing unless Ashita's own addons plugin is loaded first; a new script
    # never had it, so ticked add-ons stayed off on the second window while plugins worked
    plugins = ["addons"] + [p for p in plugins if p.lower() != "addons"]
    for name in plugins:
        if name.lower() not in have_plugins:
            first_addon = next((i for i, x in enumerate(lines) if ADDON_LINE.match(x) and not x.lstrip().startswith("#")), len(lines))
            lines.insert(first_addon, f"/load {name}")
            added.append(f"plugin {name}")
    for name in addons:
        if name.lower() not in have_addons:
            lines.append(f"/addon load {name}")
            added.append(f"addon {name}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    return added


def loaded_in_script(path):
    """(addons, plugins) the second script loads."""
    if not os.path.exists(path):
        return [], []
    with open(path, "r", encoding="utf-8-sig") as f:
        live = [line for line in f.read().splitlines() if not line.lstrip().startswith("#")]
    return ([m.group(1) for m in (ADDON_LINE.match(x) for x in live) if m], [m.group(1) for m in (PLUGIN_LINE.match(x) for x in live) if m])


def installed_addons(cfg):
    folder = os.path.join(cfg["ashita_dir"], "addons")
    return sorted(d for d in os.listdir(folder) if os.path.isdir(os.path.join(folder, d))) if os.path.isdir(folder) else []


def enable_addons(cfg, names):
    """Turns addons on for the second window, using the exact folder name from your addons folder. Returns (turned on, already on, not found)."""
    by_lower = {d.lower(): d for d in installed_addons(cfg)}
    script = os.path.join(cfg["ashita_dir"], "scripts", "dualbox.txt")
    already = {a.lower() for a in loaded_in_script(script)[0]}
    on, was, missing = [], [], []
    for name in names:
        folder = by_lower.get(name.lower())
        if folder is None:
            missing.append(name)
        elif folder.lower() in already:
            was.append(folder)
        else:
            ensure_script(script, addons=[folder])
            on.append(folder)
    return on, was, missing


# ---------- the second account ----------
def hash_password(password, like_hash):
    """A password hash in the same style as the first account's. Falls back to plain text only if the first account is not bcrypt."""
    if not like_hash or not str(like_hash).startswith("$2"):
        return password
    try:
        import bcrypt
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "bcrypt"], check=True)
        import bcrypt
    marker = str(like_hash)[:4]                      # $2a$ / $2b$ / $2y$
    cost = int(str(like_hash)[4:6]) if str(like_hash)[4:6].isdigit() else 10
    prefix = b"2a" if marker == "$2a$" else b"2b"
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=cost, prefix=prefix)).decode("ascii")
    return "$2y$" + hashed[4:] if marker == "$2y$" else hashed


def ensure_account(conn, source_login, new_login, new_password, hasher=hash_password):
    """Copies the first account's row (so every column is valid), with a new id, login and password."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM accounts WHERE login = ?", (new_login,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        return f"account '{new_login}' already exists (id {existing[0]})"
    cur.execute("SELECT * FROM accounts WHERE login = ?", (source_login,))
    row = cur.fetchone()
    if row is None:
        cur.close()
        raise RuntimeError(f"the first account '{source_login}' was not found, so there is nothing to copy")
    columns = [d[0] for d in cur.description]
    values = dict(zip(columns, row))
    # below the bot accounts (21000000 up): the next id after the last bot made the bots play this account (Reika)
    cur.execute("SELECT MAX(id) FROM accounts WHERE id < 21000000")
    values["id"] = max(1000, int(cur.fetchone()[0] or 0) + 1)
    values["login"] = new_login
    values["password"] = hasher(new_password, values.get("password"))
    cur.execute(f"INSERT INTO accounts ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})", [values[c] for c in columns])
    conn.commit()
    cur.close()
    return f"created account '{new_login}' (id {values['id']})"


def connect(cfg):
    import mariadb
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])


# ---------- AutoBot ----------
def git_clone_or_pull(target):
    if os.path.isdir(os.path.join(target, ".git")):
        return subprocess.run(["git", "-C", target, "pull", "--ff-only"], capture_output=True, text=True).returncode == 0
    return subprocess.run(["git", "clone", "--depth", "1", AUTOBOT_URL, target], capture_output=True, text=True).returncode == 0


def install_autobot(cfg, install_plugin=False, fetch=git_clone_or_pull):
    lines = []
    repo = os.path.join(HERE, "AutoBot-Ashita")
    if not fetch(repo):
        raise RuntimeError("Could not download AutoBot from " + AUTOBOT_URL + " (is git installed, and are you online?)")
    addon_src = os.path.join(repo, "addons", "autobot")
    if not os.path.isdir(addon_src):
        raise RuntimeError("The download has no addons\\autobot folder. The project may have been reorganised; tell Claude.")
    addon_dest = os.path.join(cfg["ashita_dir"], "addons", "autobot")
    shutil.copytree(addon_src, addon_dest, dirs_exist_ok=True)
    lines.append("AutoBot addon copied to " + addon_dest)
    plugin_src = os.path.join(repo, "plugins", "movement")
    if os.path.isdir(plugin_src):
        found = [os.path.relpath(os.path.join(r, f), plugin_src) for r, _d, files in os.walk(plugin_src) for f in files]
        kinds = sorted({os.path.splitext(f)[1].lower() or "(no extension)" for f in found})
        lines.append(f"The Movement plugin has {len(found)} file(s): " + ", ".join(sorted(found)[:12]) + (" ..." if len(found) > 12 else ""))
        has_source = any(k in (".cpp", ".c", ".h", ".hpp", ".cs", ".vcxproj") for k in kinds)
        lines.append("It " + ("includes source code you can read." if has_source else "has NO source code, only compiled files (" + ", ".join(kinds) + ")."))
        if install_plugin:
            plugin_dest = os.path.join(cfg["ashita_dir"], "plugins", "movement")
            shutil.copytree(plugin_src, plugin_dest, dirs_exist_ok=True)
            lines.append("Movement plugin copied to " + plugin_dest)
        else:
            lines.append("The plugin was NOT installed. Follow, approach and path-walking need it; to install it: python setup_dualbox.py plugin")
    else:
        lines.append("This version of AutoBot has no Movement plugin folder.")
    return lines


# ---------- config ----------
def update_config(cfg, boot2):
    changed = {}
    for key, value in (("ashita_boot2", boot2), ("game_user2", SECOND_USER), ("game_pass2", SECOND_PASS)):
        if not cfg.get(key):
            changed[key] = value
    if not changed:
        return False
    backup = config_path() + ".before-dualbox"
    if not os.path.exists(backup):
        shutil.copy2(config_path(), backup)
    cfg.update(changed)
    with open(config_path(), "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
    return True


# ---------- modes ----------
def setup(cfg, install_plugin=False, connect_fn=connect, fetch=git_clone_or_pull, graphics_module=None, hasher=hash_password):
    problems = 0
    first_boot_name = cfg.get("ashita_boot", "xiforever.ini")
    boot2 = second_boot_name(cfg)
    user2, pass2 = cfg.get("game_user2", SECOND_USER), cfg.get("game_pass2", SECOND_PASS)
    first, second = boot_file(cfg, first_boot_name), boot_file(cfg, boot2)
    if not os.path.exists(first):
        raise RuntimeError(f"Your boot file was not found: {first}")

    say("1. The second boot file")
    if os.path.exists(second):
        say(f"   {boot2} already exists - left as it is.")
    else:
        make_second_boot(first, second, user2, pass2, "dualbox.txt", graphics_module)
        say(f"   Created {boot2}: logs in as '{user2}', runs dualbox.txt, small windowed display.")

    say("2. AutoBot")
    try:
        for line in install_autobot(cfg, install_plugin, fetch):
            say("   " + line)
    except Exception as e:
        problems += 1
        say("   !! " + str(e))
    with_movement = os.path.isdir(os.path.join(cfg["ashita_dir"], "plugins", "movement"))

    say("3. The second script")
    script = os.path.join(cfg["ashita_dir"], "scripts", "dualbox.txt")
    existed = os.path.exists(script)
    ensure_script(script, plugins=["movement"] if with_movement else [])
    on, was, missing = enable_addons(cfg, DEFAULT_ADDONS)
    say(f"   {script} " + ("already existed: everything in it was kept." if existed else "created."))
    if on:
        say("   Turned on for the second window: " + ", ".join(on))
    if was:
        say("   Already on: " + ", ".join(was))
    for name in missing:
        say(f"   !! '{name}' is not in your addons folder, so it was not turned on. Check its folder name in the launcher's Addons tab.")

    say("4. The second account")
    try:
        conn = connect_fn(cfg)
        say("   " + ensure_account(conn, cfg.get("game_user", "player1"), user2, pass2, hasher))
        conn.close()
    except Exception as e:
        problems += 1
        say("   !! " + str(e))
        say("   (Is the database running? Open the launcher once and press PLAY, or start the MariaDB service.)")

    say("5. config.json")
    say("   " + ("Added ashita_boot2, game_user2 and game_pass2." if update_config(cfg, boot2) else "Already has the dualbox settings."))
    say()
    if problems:
        say(f"Finished with {problems} problem(s) above. Everything that worked is in place; send Claude the lines starting with '!!'.")
    else:
        say("DONE. Now: open the launcher, press PLAY, then click 'Start second character' on the Play page.")
        say(f"The first time, the second window shows character creation: make the second character (account '{user2}').")
    return problems


MODES = {"windowed": 1, "window": 1, "borderless": 3, "fullscreen": 0}


def set_window(cfg, width, height, mode, graphics_module):
    """Changes only the second window's size and mode. The main boot file is not touched."""
    second = boot_file(cfg, second_boot_name(cfg))
    if not os.path.exists(second):
        raise RuntimeError("The second boot file does not exist yet. Run: python setup_dualbox.py setup")
    values = graphics_module.read_boot_graphics(second)
    values.update({"screen_w": width, "screen_h": height, "menu_w": width, "menu_h": height})     # the menu and the screen must have the same shape
    if mode is not None:
        values["window_mode"] = MODES[mode]
    graphics_module.apply_graphics(second, values)
    clean = graphics_module.clean_graphics(values)
    names = graphics_module.WINDOW_MODES
    return f"The second window is now {clean['screen_w']} x {clean['screen_h']}, {names[clean['window_mode']].lower()}. It applies the next time you start it."


# ---------- the language Ashita's addons see ----------
# [ashita.language] ashita = 1 means Japanese, 2 means English (LuAshitacast reads it the same way). Addons that look spells up by name
# (the gambit engine) read names in this language, so with 1 an English name like "Dia" is never found.
LANGUAGES = {"english": 2, "japanese": 1}


def boot_files(cfg):
    """(label, path) of the boot files that exist: main window, second window, GM window."""
    out = []
    for label, name in (("main", cfg.get("ashita_boot", "xiforever.ini")), ("second", second_boot_name(cfg)), ("gm", cfg.get("ashita_boot_gm", ""))):
        path = boot_file(cfg, name) if name else ""
        if path and os.path.isfile(path):
            out.append((label, path))
    return out


def read_language(path):
    """{"playonline": n or None, "ashita": n or None} from the [ashita.language] section."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    section = re.search(r"(?ims)^\[ashita\.language\]\s*$(.*?)(?=^\[|\Z)", text)
    found = {"playonline": None, "ashita": None}
    if section:
        for key in found:
            m = re.search(r"(?im)^\s*" + key + r"\s*=\s*(\d+)", section.group(1))
            if m:
                found[key] = int(m.group(1))
    return found


def set_ashita_language(path, value):
    """Sets only the 'ashita' line of [ashita.language] (adding it if missing). The original is kept once as .before-language. Returns True if the file changed."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    section = re.search(r"(?ims)^(\[ashita\.language\][ \t]*\r?$)(.*?)(?=^\[|\Z)", text)
    line = f"ashita = {value}"
    if section is None:
        new = text.rstrip("\r\n") + newline + newline + "[ashita.language]" + newline + line + newline
    else:
        body = section.group(2)
        if re.search(r"(?im)^\s*ashita\s*=", body):
            body_new = re.sub(r"(?im)^([ \t]*)ashita[ \t]*=[^\r\n]*", lambda m: m.group(1) + line, body, count=1)
        else:
            body_new = newline + line + body
        new = text[:section.start(2)] + body_new + text[section.end(2):]
    if new == text:
        return False
    backup = path + ".before-language"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return True


def language_command(cfg, words):
    files = boot_files(cfg)
    if not words:
        for label, path in files:
            lang = read_language(path)
            names = {1: "Japanese", 2: "English"}
            say(f"{label:<7} {os.path.basename(path):<24} ashita = {lang['ashita']} ({names.get(lang['ashita'], 'not set, the default')})   playonline = {lang['playonline']}")
        say("With ashita = 1 the gambit engine sees Japanese spell names and cannot find English ones. Fix: python setup_dualbox.py language english")
        return 0
    wanted = words[0].lower()
    if wanted not in LANGUAGES:
        raise RuntimeError("Use:  python setup_dualbox.py language english   (or japanese)")
    value, everything = LANGUAGES[wanted], "--all" in words
    changed = 0
    for label, path in files:
        if label == "main" and not everything:
            continue
        if set_ashita_language(path, value):
            changed += 1
            say(f"{label}: {os.path.basename(path)} is now ashita = {value} ({wanted}). The old file is kept as {os.path.basename(path)}.before-language")
        else:
            say(f"{label}: {os.path.basename(path)} was already {wanted}")
    say("Close the game window(s) and start them again from the launcher: the boot file is only read when a window starts." if changed else "Nothing needed changing.")
    return 0


def report(cfg):
    boot2 = second_boot_name(cfg)
    say("Second boot file : " + ("yes" if os.path.exists(boot_file(cfg, boot2)) else "NO") + f"  ({boot2})")
    script = os.path.join(cfg["ashita_dir"], "scripts", "dualbox.txt")
    say("Second script    : " + ("yes" if os.path.exists(script) else "NO"))
    addons, plugins = loaded_in_script(script)
    say("Loads on window 2 : addons: " + (", ".join(addons) or "none") + "   plugins: " + (", ".join(plugins) or "none"))
    say("AutoBot addon    : " + ("yes" if os.path.isdir(os.path.join(cfg["ashita_dir"], "addons", "autobot")) else "NO"))
    say("Movement plugin  : " + ("yes" if os.path.isdir(os.path.join(cfg["ashita_dir"], "plugins", "movement")) else "no (optional)"))
    try:
        conn = connect(cfg)
        cur = conn.cursor()
        cur.execute("SELECT id, login FROM accounts ORDER BY id")
        say("Accounts         : " + ", ".join(f"{login} (id {i})" for i, login in cur.fetchall()))
        conn.close()
    except Exception as e:
        say("Accounts         : could not read (" + str(e)[:80] + ")")


def main(argv):
    mode = argv[1] if len(argv) > 1 else "report"
    cfg = load_config()
    if "ashita_dir" not in cfg:
        raise SystemExit("config.json has no ashita_dir, so I can not find your Ashita folder.")
    import launcher_core as core
    if mode == "setup":
        return setup(cfg, graphics_module=core)
    if mode == "plugin":
        for line in install_autobot(cfg, install_plugin=True):
            say(line)
        added = ensure_script(os.path.join(cfg["ashita_dir"], "scripts", "dualbox.txt"), plugins=["movement"])
        say("Added to dualbox.txt: " + (", ".join(added) if added else "nothing (the Movement plugin was already there)") + ". Everything else in it was kept.")
        return 0
    if mode == "report":
        report(cfg)
        return 0
    if mode == "language":
        return language_command(cfg, argv[2:])
    if mode == "enable":
        names = argv[2:]
        if not names:
            raise SystemExit("Use:  python setup_dualbox.py enable autobot xiui")
        on, was, missing = enable_addons(cfg, names)
        if on:
            say("Turned on for the second window: " + ", ".join(on))
        if was:
            say("Already on: " + ", ".join(was))
        if missing:
            say("Not found in your addons folder: " + ", ".join(missing))
            say("The addons you have: " + ", ".join(installed_addons(cfg)))
        return 0 if not missing else 1
    if mode == "window":
        try:
            width, height = int(argv[2]), int(argv[3])
            wanted = argv[4].lower() if len(argv) > 4 else None
            if wanted is not None and wanted not in MODES:
                raise ValueError
        except (IndexError, ValueError):
            raise SystemExit("Use:  python setup_dualbox.py window <width> <height> [windowed|borderless|fullscreen]\nfor example:  python setup_dualbox.py window 1600 900 windowed")
        say(set_window(cfg, width, height, wanted, core))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except RuntimeError as problem:               # a plain message, not a wall of red text
        print("\n" + str(problem))
        sys.exit(1)
