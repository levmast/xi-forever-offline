#!/usr/bin/env python3
"""A GM account for testing. In LandSandBoat a GM is a CHARACTER (chars.gmlevel 1-5), so this makes a separate account whose
characters are GMs automatically, and your real character stays untouched.

  python setup_gm.py setup                  the GM account, its own boot file, and a rule that makes new characters on it GMs
  python setup_gm.py report                 what is set up, and the characters on the GM account
  python setup_gm.py promote Name [level]   make an existing character a GM (default level 5); log that character out first
  python setup_gm.py demote Name            take GM away again
  python setup_gm.py commands               the GM commands your server has, with the level each needs
  python setup_gm.py backup                 save the database to the kit's backups folder (do this before testing things)
  python setup_gm.py window 1600 900 [windowed|borderless|fullscreen]   the size of the GM game window

It never edits your main boot file, script or account.
"""
import json
import os
import secrets
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import setup_dualbox as sd

# A new random password is made for each new install; once setup has run, config.json holds the one in use.
GM_USER, GM_PASS, GM_LEVEL = "gm1", "gm-" + secrets.token_hex(5), 5
TRIGGER = "gm_account_gmlevel"


def say(text=""):
    print(text, flush=True)


def gm_boot_name(cfg):
    if cfg.get("ashita_boot_gm"):
        return cfg["ashita_boot_gm"]
    root, ext = os.path.splitext(cfg.get("ashita_boot", "xiforever.ini"))
    return f"{root}_gm{ext or '.ini'}"


def main_script_name(first_boot_path):
    """The script the main boot file runs, so the GM game loads the same addons as your main game."""
    with open(first_boot_path, "r", encoding="utf-8-sig", errors="replace") as f:
        m = re.search(r"(?im)^\s*script\s*=\s*(\S+)", f.read())
    return m.group(1) if m else "xiforever.txt"


def install_trigger(conn, user, level):
    """New characters on the GM account are created as GMs. Done in the database, so it needs no server change."""
    cur = conn.cursor()
    body = (f"BEFORE INSERT ON chars FOR EACH ROW {{follows}} "
            f"SET NEW.gmlevel = IF(NEW.accid = (SELECT id FROM accounts WHERE login = '{user}'), {int(level)}, NEW.gmlevel)")
    cur.execute(f"DROP TRIGGER IF EXISTS {TRIGGER}")
    try:
        cur.execute(f"CREATE TRIGGER {TRIGGER} " + body.format(follows="FOLLOWS char_insert"))
        how = "created (it runs right after the game's own new-character rule)"
    except Exception:
        cur.execute(f"CREATE TRIGGER {TRIGGER} " + body.format(follows=""))
        how = "created"
    conn.commit()
    cur.close()
    return how


def make_account_characters_gm(conn, user, level):
    cur = conn.cursor()
    cur.execute("UPDATE chars SET gmlevel = ? WHERE accid = (SELECT id FROM accounts WHERE login = ?)", (int(level), user))
    count = cur.rowcount
    conn.commit()
    cur.close()
    return count


def has_gmlevel_column(conn):
    cur = conn.cursor()
    cur.execute("SHOW COLUMNS FROM chars LIKE 'gmlevel'")
    found = cur.fetchone() is not None
    cur.close()
    return found


def set_level(conn, name, level):
    cur = conn.cursor()
    cur.execute("UPDATE chars SET gmlevel = ? WHERE LOWER(charname) = LOWER(?)", (int(level), name))
    count = cur.rowcount
    conn.commit()
    cur.close()
    return count


def update_config(cfg, boot_gm):
    changed = {}
    for key, value in (("ashita_boot_gm", boot_gm), ("game_user_gm", GM_USER), ("game_pass_gm", GM_PASS)):
        if not cfg.get(key):
            changed[key] = value
    if not changed:
        return False
    path = os.path.join(HERE, "config.json")
    backup = path + ".before-gm"
    if not os.path.exists(backup):
        import shutil
        shutil.copy2(path, backup)
    cfg.update(changed)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
    return True


def setup(cfg, connect_fn=sd.connect, graphics_module=None, hasher=sd.hash_password, trigger_fn=install_trigger, column_check=has_gmlevel_column):
    problems = 0
    user, password = cfg.get("game_user_gm", GM_USER), cfg.get("game_pass_gm", GM_PASS)
    first_name = cfg.get("ashita_boot", "xiforever.ini")
    boot = gm_boot_name(cfg)
    first, gm_path = sd.boot_file(cfg, first_name), sd.boot_file(cfg, boot)
    if not os.path.exists(first):
        raise RuntimeError(f"Your boot file was not found: {first}")

    say("1. The GM boot file")
    if os.path.exists(gm_path):
        say(f"   {boot} already exists - left as it is.")
    else:
        sd.make_second_boot(first, gm_path, user, password, main_script_name(first), graphics_module)
        say(f"   Created {boot}: logs in as '{user}', loads the same addons as your main game, small windowed display.")

    say("2. The GM account and the rule that makes its characters GMs")
    try:
        conn = connect_fn(cfg)
        say("   " + sd.ensure_account(conn, cfg.get("game_user", "player1"), user, password, hasher))
        if not column_check(conn):
            raise RuntimeError("the chars table has no gmlevel column, so this server does not use GM levels the usual way")
        say("   Rule " + trigger_fn(conn, user, GM_LEVEL) + f": a character created on '{user}' becomes GM level {GM_LEVEL}.")
        count = make_account_characters_gm(conn, user, GM_LEVEL)
        say(f"   Characters already on that account made GM: {count}")
        conn.close()
    except Exception as e:
        problems += 1
        say("   !! " + str(e))
        say("   (Is the database running? Open the launcher once and press PLAY, or start the MariaDB service.)")

    say("3. config.json")
    say("   " + ("Added ashita_boot_gm, game_user_gm and game_pass_gm." if update_config(cfg, boot) else "Already has the GM settings."))
    say()
    if problems:
        say(f"Finished with {problems} problem(s) above. Send Claude the lines starting with '!!'.")
    else:
        say("DONE. In the launcher: SYSTEM > GM and testing > 'Start GM game'.")
        say(f"The first time, create a character in the lobby (account '{user}'): it is a GM from its first login.")
    return problems


def report(cfg, connect_fn=sd.connect):
    boot = gm_boot_name(cfg)
    say("GM boot file : " + ("yes" if os.path.exists(sd.boot_file(cfg, boot)) else "NO") + f"  ({boot})")
    user = cfg.get("game_user_gm", GM_USER)
    try:
        conn = connect_fn(cfg)
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE login = ?", (user,))
        row = cur.fetchone()
        say(f"GM account   : {'yes (id ' + str(row[0]) + ')' if row else 'NO'}  ({user})")
        if row:
            cur.execute("SELECT charname, gmlevel FROM chars WHERE accid = ? ORDER BY charname", (row[0],))
            chars = cur.fetchall()
            say("Characters   : " + (", ".join(f"{n} (GM {g})" for n, g in chars) if chars else "none yet - create one in the game lobby"))
        cur.execute("SELECT charname, gmlevel FROM chars WHERE gmlevel > 0 ORDER BY charname")
        everyone = cur.fetchall()
        say("All GMs      : " + (", ".join(f"{n} ({g})" for n, g in everyone) if everyone else "none"))
        conn.close()
    except Exception as e:
        say("Database     : could not read (" + str(e)[:80] + ")")


def list_commands(cfg):
    folder = os.path.join(cfg["server_dir"], "scripts", "commands")
    if not os.path.isdir(folder):
        say("Could not find " + folder)
        return 1
    rows = []
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".lua"):
            continue
        with open(os.path.join(folder, name), "r", encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
        level = re.search(r"permission\s*=\s*(\d+)", text)
        desc = re.search(r"^--\s*desc:\s*(.+)$", text, re.M)
        rows.append((int(level.group(1)) if level else -1, name[:-4], (desc.group(1).strip() if desc else "")))
    say(f"{len(rows)} commands on your server. Type them in the game with a ! in front. The level is what a character needs (GM 5 can use all).")
    for level in sorted({r[0] for r in rows}):
        say()
        say(("Anyone" if level == 0 else f"GM level {level}") if level >= 0 else "Level not found")
        for _lvl, name, desc in (r for r in rows if r[0] == level):
            say(f"  !{name:<22} {desc[:70]}")
    return 0



def db_tool(cfg, name):
    """mysqldump / mysql: from the portable MariaDB in the kit when there is one, else from PATH. Port only when set."""
    if cfg.get("mariadb_dir") and os.name != "nt":    # Linux: the kit's MariaDB package, its own names, no /etc/my.cnf
        import launcher_setup
        new = {"mysqldump": "mariadb-dump", "mysql": "mariadb"}.get(name, name)
        return launcher_setup.mariadb_cmd(cfg["mariadb_dir"], new) + ([f"-P{cfg['db_port']}"] if cfg.get("db_port") else [])
    exe = os.path.join(cfg["mariadb_dir"], "bin", name + ".exe") if cfg.get("mariadb_dir") else name
    return [exe] + ([f"-P{cfg['db_port']}"] if cfg.get("db_port") else [])

def backup(cfg):
    folder = os.path.join(HERE, "backups")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "db-manual-" + time.strftime("%Y%m%d-%H%M%S") + ".sql")
    cmd = db_tool(cfg, "mysqldump") + [f"-h{cfg.get('db_host', '127.0.0.1')}", f"-u{cfg['db_user']}", f"-p{cfg['db_pass']}", cfg["db_name"], f"--result-file={path}"]
    env = None
    if cfg.get("mariadb_dir") and os.name != "nt":
        import launcher_setup
        env = launcher_setup.mariadb_env(cfg["mariadb_dir"])
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        say("The backup FAILED: " + (result.stderr or "").strip()[:200])
        return 1
    say(f"Saved the database to {path} ({os.path.getsize(path) // 1024} KB).")
    return 0


def set_gm_window(cfg, width, height, mode, core):
    path = sd.boot_file(cfg, gm_boot_name(cfg))
    if not os.path.exists(path):
        raise RuntimeError("The GM boot file does not exist yet. Run: python setup_gm.py setup")
    values = core.read_boot_graphics(path)
    values.update({"screen_w": width, "screen_h": height, "menu_w": width, "menu_h": height})
    if mode is not None:
        values["window_mode"] = sd.MODES[mode]
    core.apply_graphics(path, values)
    clean = core.clean_graphics(values)
    return f"The GM game window is now {clean['screen_w']} x {clean['screen_h']}, {core.WINDOW_MODES[clean['window_mode']].lower()}. It applies the next time you start it."


def main(argv):
    mode = argv[1] if len(argv) > 1 else "report"
    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    if mode == "commands":
        return list_commands(cfg)
    if mode == "backup":
        return backup(cfg)
    if "ashita_dir" not in cfg:
        raise SystemExit("config.json has no ashita_dir, so I can not find your Ashita folder.")
    import launcher_core as core
    if mode == "setup":
        return setup(cfg, graphics_module=core)
    if mode == "report":
        report(cfg)
        return 0
    if mode in ("promote", "demote"):
        if len(argv) < 3:
            raise SystemExit(f"Use:  python setup_gm.py {mode} CharacterName" + (" [level 1-5]" if mode == "promote" else ""))
        level = 0 if mode == "demote" else int(argv[3]) if len(argv) > 3 else GM_LEVEL
        if not 0 <= level <= 5:
            raise SystemExit("The level must be 1 to 5.")
        conn = sd.connect(cfg)
        count = set_level(conn, argv[2], level)
        conn.close()
        say((f"{argv[2]} is now GM level {level}" if level else f"{argv[2]} is not a GM any more") + " (log that character out and in again for it to apply)."
            if count else f"No character named '{argv[2]}' was found.")
        return 0 if count else 1
    if mode == "window":
        try:
            width, height = int(argv[2]), int(argv[3])
            wanted = argv[4].lower() if len(argv) > 4 else None
            if wanted is not None and wanted not in sd.MODES:
                raise ValueError
        except (IndexError, ValueError):
            raise SystemExit("Use:  python setup_gm.py window <width> <height> [windowed|borderless|fullscreen]")
        say(set_gm_window(cfg, width, height, wanted, core))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except RuntimeError as problem:               # a plain message, not a wall of red text
        print("\n" + str(problem))
        sys.exit(1)
