"""The first setup of a world that runs without the launcher's window (XI: Forever Offline, open worlds, 2026-11-23):
a rented server ("cloud world"), the hub. Run through launcher_world.py:

    XI-Forever-Offline --run launcher_world.py setup [options]
    python launcher_world.py setup [options]

It does the server side of the players' first-run setup (launcher_setup.run_setup) and nothing of the game: the game
server's files (the newest full release, never a test build), the kit's own MariaDB, the database and its tables, the
server's database login, and then this world's own settings:
    config.json   where things are (no game, no Ashita, no player account)
    rates.json    the rules, as the RULES page writes them
    coop.json     who can come in, the address and port, how many visitors, the password (only its hash)
    world.json    backups and updates (launcher_world_keep.py)
Every step can be run again: what is already there is kept. Running it again with other answers changes who can come
in, the address, the limit, the password and the name; the rules are only written when rates.json is missing.

Questions are asked on the terminal for whatever was not given as an option. With --yes, or without a terminal,
nothing is asked and the defaults are used.
"""
import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import launcher_coop as co                      # noqa: E402
import launcher_core as core                    # noqa: E402
import launcher_setup as setup                  # noqa: E402
import launcher_world_keep as keep              # noqa: E402

ADDRESS_SITES = ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ipv4.icanhazip.com")
RATES = {"era": None, "classic": "Classic (retail rates)", "relaxed": "Relaxed solo", "fast": "Fast"}
WORLDS = ("living", "quiet")                    # (no "living_ai": nothing here runs an AI)
OPEN_GUESTS, FRIEND_GUESTS = 12, 3              # visitors at most when nothing was said (a starting value, not a measured one)
KEPT_ANSWERS = ("address", "port", "max_guests", "open")     # a later setup keeps these from an earlier one unless it is told otherwise
DEFAULT_NAME = "A world"


class SetupError(Exception):
    """The setup cannot go on. The text can be shown as it is."""


# ----- the answers -----
def number_address(text):
    """The address as the game server needs it (four numbers), or None."""
    text = str(text or "").strip()
    try:
        return str(ipaddress.IPv4Address(text)) if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", text) else None
    except ValueError:
        return None


def address_note(address):
    """A sentence when players elsewhere on the internet cannot reach that address, else None."""
    ip = ipaddress.IPv4Address(address)
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        raise SetupError(f"{address} is not an address players can reach.")
    if not ip.is_global:
        return (f"{address} is not an address of the open internet: only people on that same network (or the same VPN) "
                "can reach this world.")
    return None


def find_address(fetch):
    """This machine's address as the internet sees it, or "" when it could not be found out."""
    for site in ADDRESS_SITES:
        try:
            found = number_address(fetch(site, timeout=10).decode("ascii", "replace"))
        except Exception:
            continue
        if found and ipaddress.IPv4Address(found).is_global:
            return found
    return ""


def clean_answers(given):
    """The answers with every value checked and filled in. SetupError says what is wrong with one."""
    out = {}
    out["name"] = co.pp.clean_world_name(given.get("name") or DEFAULT_NAME)
    out["address"] = number_address(given.get("address"))
    if not out["address"]:
        raise SetupError("The world needs this server's address as four numbers, like 203.0.113.20 (--address).")
    out["note"] = address_note(out["address"])
    out["open"] = bool(given.get("open", True))
    try:
        out["port"] = int(given.get("port") or co.PORT)
        limit = given.get("max_guests")
        out["max_guests"] = int(limit) if limit not in (None, "") else (OPEN_GUESTS if out["open"] else FRIEND_GUESTS)
    except (TypeError, ValueError):
        raise SetupError("The port and the number of visitors have to be numbers.")
    if not 1024 <= out["port"] <= 65535 or out["port"] in [port for _name, port in co.GAME_PORTS]:
        raise SetupError(f"Port {out['port']} cannot be used for visitors' launchers (1024-65535, and not one of the game's own).")
    most = co.MAX_OPEN_GUESTS if out["open"] else co.MAX_GUESTS
    if not 1 <= out["max_guests"] <= most:
        raise SetupError(f"A world that is open to {'everyone' if out['open'] else 'friends'} can take 1 to {most} visitors.")
    password = given.get("password")
    if password is not None and not isinstance(password, str):
        raise SetupError("The password has to be text.")
    if password and not out["open"]:
        raise SetupError("Only a world that is open to everyone has a password (friends come in with the invite code).")
    if password and (len(password) > 64 or any(ord(c) < 32 for c in password)):
        raise SetupError("The password can be up to 64 characters, on one line.")
    out["password"] = password                      # None: leave as it is; "": none
    out["world"] = given.get("world") or "living"
    if out["world"] not in WORLDS:
        raise SetupError("The world is 'living' (town crowds, bot players, a stocked auction house) or 'quiet'.")
    out["population"] = given.get("population") or "small"
    if out["population"] not in core.POPULATIONS:
        raise SetupError("The population is small, medium or large.")
    out["rates"] = given.get("rates") or "era"
    if out["rates"] not in RATES:
        raise SetupError("The rates are era, classic, relaxed or fast.")
    bots = given.get("bots")
    try:
        out["bots"] = None if bots in (None, "") else max(0, min(550, int(bots)))
    except (TypeError, ValueError):
        raise SetupError("The number of bot players has to be a number.")
    return out


def world_rates(answers):
    """rates.json for these answers: the world and its population, the chosen rates, and no AI (nothing here runs one)."""
    rates = core.apply_world(dict(core.RATE_DEFAULTS), answers["world"], answers["population"])
    if RATES[answers["rates"]]:
        rates = core.apply_preset(rates, RATES[answers["rates"]])
    if answers["bots"] is not None and rates.get("bots"):
        rates["bots_online"] = answers["bots"]
        rates["bots_roster"] = max(int(rates.get("bots_roster", 0)), min(600, answers["bots"] * 2))
    rates.update({"crowds_chat_ai": False, "squad_chat": False})
    return rates


def server_item(item, fetch):
    """The manifest's server entry pointed at the newest full release. (The players' setup also takes a test build
    when that is the newest; a world never does, and never updates to one.)"""
    import launcher_update as lu
    release = lu.newest_release(lu.SERVER_REPO, False, fetch)
    if not release:
        raise SetupError("No full release of the server is published yet.")
    pinned = json.loads(json.dumps(item))
    pinned["source"]["tag"] = release["tag_name"]
    pinned["source"].pop("prereleases", None)
    return pinned


def _private(path):
    """Linux: only the world's own user reads its passwords."""
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


# ----- a world that is already set up -----
def stored_answers(kit):
    """What an earlier setup of this world decided: its address, port, visitor limit and who can come in.
    {} on a first setup, and in a folder that is not a world's."""
    config_path = os.path.join(kit, "config.json")
    try:
        if not os.path.exists(config_path) or not core.load_config(config_path).get("world_only"):
            return {}
        if not os.path.exists(os.path.join(kit, co.SETTINGS_FILE)):
            return {}
        settings = co.load_settings(kit)
    except Exception:
        return {}
    if not settings.get("hosting") or not settings.get("address"):
        return {}
    return {key: settings[key] for key in KEPT_ANSWERS}


def with_stored(kit, given):
    """given, with what was not said taken from the earlier setup of this world (unchanged on a first setup).
    A world that changes between "everyone" and "friends" does not keep its old visitor limit: each has its own range."""
    out, stored = dict(given), stored_answers(kit)
    if not stored:
        return out
    switched = out.get("open") is not None and bool(out["open"]) != bool(stored["open"])
    for key in KEPT_ANSWERS:
        if out.get(key) in (None, "") and not (switched and key == "max_guests"):
            out[key] = stored[key]
    return out


# ----- the setup -----
def setup_world(kit, given, log=print, fetch=None, run=subprocess.run, popen=subprocess.Popen, connect=None):
    """Returns {"cfg", "settings", "answers", "invite"}. invite: the code for friends (None for an open world, whose
    link exists once the game server has run)."""
    import launcher_thirdparty as tp
    fetch = fetch or tp._get
    given = with_stored(kit, given)                 # (a second run keeps what it is not told to change)
    answers = clean_answers(given)
    config_path = os.path.join(kit, "config.json")
    if os.path.exists(config_path) and not core.load_config(config_path).get("world_only"):
        raise SetupError("This folder holds a player's install (its config.json says so). A world that runs by itself "
                         "needs a folder of its own.")
    layout = setup.default_layout(kit)
    server, mdb = layout["server_dir"], layout["mariadb_dir"]
    if answers["note"]:
        log(answers["note"])

    log("1/5 The game server...")
    if not setup.valid_server(server):
        items = {item["id"]: item for item in tp.load_manifest(kit)}
        try:
            tp.install(server_item(items["server"], fetch), kit, None, fetch=fetch, log=log, server=server)
        except SetupError:
            raise
        except Exception as problem:
            if not setup.IS_WINDOWS and "no file matching" in str(problem):
                raise SetupError("The Linux server for the newest version is still being built (it arrives about 40 "
                                 "minutes after a release). Wait a little and run the setup again.")
            raise SetupError(f"The server files could not be downloaded ({problem}).")
    else:
        log("   The server files are already there.")

    log("2/5 Database program (MariaDB)...")
    if not os.path.isfile(setup.mariadb_exe(mdb, "mariadbd")):
        found = setup.resolve_mariadb(fetch)
        log(f"Downloading MariaDB {found['version']}...")
        folder = os.path.join(kit, "downloads", "mariadb")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, found["name"])
        if setup.IS_WINDOWS:
            import hashlib
            data = fetch(found["url"], timeout=1800)
            if found.get("sha256") and hashlib.sha256(data).hexdigest() != found["sha256"].lower():
                raise SetupError("The MariaDB download does not match its published checksum.")
            with open(path, "wb") as handle:
                handle.write(data)
        else:
            tp.download_file(found["url"], path, log=log, sha256=found.get("sha256"), fetch=fetch)
        setup.unpack_package(path, mdb)
    if not setup.IS_WINDOWS:
        still = setup.fill_missing_libs(mdb, os.path.join(kit, *setup.COMPAT_LIBS), log=log)
        if still:
            raise SetupError("MariaDB can't run on this Linux: it is missing " + ", ".join(still) + ". On Ubuntu or "
                             "Debian the packages libaio1 (or libaio1t64), libncurses6 and libcrypt1 have them.")
    secrets_file = os.path.join(mdb, "xiforever-db.json")       # the database passwords of this install
    if os.path.exists(secrets_file):
        with open(secrets_file, encoding="utf-8") as handle:
            keys = json.load(handle)
    else:
        keys = {"root": setup.new_password(), "xi": setup.new_password(), "port": setup.free_port()}
        with open(secrets_file, "w", encoding="utf-8") as handle:
            json.dump(keys, handle)
    _private(secrets_file)
    cfg_values = {"server_dir": server, "ffxi_client_dir": "", "ashita_dir": "", "ashita_boot": "", "xiloader_dir": "",
                  "era_dats_dir": "", "db_name": setup.DB_NAME, "db_user": setup.DB_USER, "db_pass": keys["xi"],
                  "db_port": keys["port"], "game_user": "", "game_pass": "", "mariadb_dir": mdb, "mariadb_service": "",
                  "world": answers["world"], "world_only": True}
    log(setup.init_mariadb(mdb, keys["root"], keys["port"], run=run))
    proc = setup.start_mariadb(mdb, keys["port"], popen=popen)
    try:
        if not setup.IS_WINDOWS:
            setup.set_root_password(mdb, keys["port"], keys["root"], run=run)
        log("3/5 Database and tables (a few minutes)...")
        setup.create_database(mdb, keys["port"], keys["root"], keys["xi"], run=run)
        tables = setup.sql(mdb, keys["port"], setup.DB_USER, keys["xi"], "SHOW TABLES LIKE 'accounts'",
                           database=setup.DB_NAME, run=run).strip()
        if not tables:
            setup.import_sql(mdb, keys["port"], keys["xi"], setup.import_order(server), log=log, run=run)
        else:
            log("The tables are already there.")
        conn = (connect or co.pp.connect)(cfg_values)
        try:
            co.pp.world_identity(conn, default_name=answers["name"])
            if given.get("name"):                    # (a name given now replaces the one from an earlier setup)
                co.pp.set_world_name(conn, answers["name"])
            name = co.pp.world_identity(conn)["name"]
        finally:
            conn.close()
    finally:
        setup.stop_mariadb(mdb, keys["port"], keys["root"], run=run)
        if proc is not None:
            try:
                proc.wait(timeout=20)
            except Exception:
                proc.kill()

    log("4/5 Server settings...")
    log(setup.write_network_settings(server, keys["port"], keys["xi"]))

    log("5/5 This world's settings...")
    if os.path.exists(config_path):
        cfg = core.load_config(config_path)
    else:
        cfg = setup.write_config(kit, cfg_values)
    _private(config_path)
    if not os.path.exists(core.rates_path(kit)):
        core.save_rates(kit, world_rates(answers))
    settings = co.load_settings(kit)
    settings.update({"enabled": True, "hosting": True, "mode": "direct", "address": answers["address"],
                     "port": answers["port"], "max_guests": answers["max_guests"], "open": answers["open"],
                     "backup_done": True})
    if answers["password"] is not None:
        settings["password"] = co.hash_password(answers["password"])
    if not answers["open"]:
        settings["password"] = ""
    co.save_settings(kit, settings)
    _private(os.path.join(kit, co.SETTINGS_FILE))
    if not os.path.exists(os.path.join(kit, keep.WORLD_FILE)):
        keep.save_settings(kit, keep.load_settings(kit))
    invite = None if answers["open"] else co.make_invite(answers["address"], answers["port"], settings["secret"], name)
    who = ("anyone with its link" + (", with a password" if settings["password"] else "")) if answers["open"] else "friends with the invite code"
    log(f"Setup finished. \"{name}\" at {answers['address']}, port {answers['port']}: open to {who}, "
        f"{answers['max_guests']} visitors at most.")
    return {"cfg": cfg, "settings": settings, "answers": answers, "invite": invite, "name": name}


# ----- asking on the terminal -----
class Terminal:
    """Questions and answers on the terminal itself (/dev/tty), so the setup can be asked things even when its own
    input is a pipe ("curl ... | bash")."""

    def __init__(self, path=None):
        self.handle = None
        try:
            self.handle = open(path or ("CON" if os.name == "nt" else "/dev/tty"), "r+", encoding="utf-8", errors="replace")
        except OSError:
            pass

    def usable(self):
        return self.handle is not None

    def ask(self, question, default="", secret=False):
        shown = f" [{default}]" if default not in ("", None) else ""
        self.handle.write(f"{question}{shown}: ")
        self.handle.flush()
        if secret:
            import getpass
            try:
                answer = getpass.getpass("", stream=self.handle)
            except Exception:
                answer = self.handle.readline()
        else:
            answer = self.handle.readline()
        answer = answer.strip()
        return answer if answer else default

    def choose(self, question, choices, default):
        """choices: [(value, text)]. Asked again until the answer is one of them (its number or its name)."""
        while True:
            for number, (_value, text) in enumerate(choices, 1):
                self.handle.write(f"  {number}) {text}\n")
            answer = str(self.ask(question, str(1 + [value for value, _text in choices].index(default)))).lower()
            for number, (value, _text) in enumerate(choices, 1):
                if answer in (str(number), str(value).lower()):
                    return value
            self.handle.write("Please answer with one of the numbers.\n")

    def close(self):
        if self.handle is not None:
            self.handle.close()


def ask_answers(given, terminal, found_address=""):
    """Fills in what the options did not say by asking. given: {key: value or None}."""
    out = dict(given)
    if out.get("name") is None:
        out["name"] = terminal.ask("The world's name (players see it)", DEFAULT_NAME)
    while not number_address(out.get("address")):
        out["address"] = terminal.ask("This server's address on the internet (four numbers)", found_address)
        if not number_address(out["address"]):
            terminal.handle.write("That is not an address like 203.0.113.20.\n")
    if out.get("open") is None:
        out["open"] = terminal.choose("Who can come in", [(True, "Anyone with the world's link"),
                                                          (False, "Only friends with the invite code")], True)
    if out["open"] and out.get("password") is None:
        out["password"] = terminal.ask("A password for the world (empty: none)", "", secret=True)
    if out.get("max_guests") is None:
        most = co.MAX_OPEN_GUESTS if out["open"] else co.MAX_GUESTS
        out["max_guests"] = terminal.ask(f"Visitors at most (1-{most})", OPEN_GUESTS if out["open"] else FRIEND_GUESTS)
    if out.get("world") is None:
        out["world"] = terminal.choose("The world", [("living", core.WORLDS["living"][0] + ": " + core.WORLDS["living"][1]),
                                                     ("quiet", core.WORLDS["quiet"][0] + ": " + core.WORLDS["quiet"][1])], "living")
    if out["world"] == "living" and out.get("population") is None:
        out["population"] = terminal.choose("How many bot players and townspeople", [
            (key, f"{label}: {online} bot players online, {crowd} people per town") for key, (label, crowd, _roster, online)
            in core.POPULATIONS.items()], "small")
    if out.get("rates") is None:
        out["rates"] = terminal.choose("The rates", [("era", "Era (the project's own: Aht Urhgan-era exp tables)"),
                                                     ("classic", "Classic (retail rates)"), ("relaxed", "Relaxed (about 2x)"),
                                                     ("fast", "Fast (about 5x)")], "era")
    return out


def parse(argv):
    parser = argparse.ArgumentParser(prog="launcher_world.py setup", allow_abbrev=False,
                                     description="Sets up a world that runs without the launcher's window.")
    parser.add_argument("--name", help="the world's name")
    parser.add_argument("--address", help="this server's address on the internet (four numbers); looked up when left out")
    parser.add_argument("--port", type=int, help=f"the port for visitors' launchers (default {co.PORT})")
    who = parser.add_mutually_exclusive_group()
    who.add_argument("--open", dest="open", action="store_true", default=None, help="anyone with the world's link can come in")
    who.add_argument("--friends", dest="open", action="store_false", help="only friends with the invite code")
    parser.add_argument("--password-file", help="a file whose first line is the world's password (an empty file: no password)")
    parser.add_argument("--max-guests", type=int, help="visitors at most")
    parser.add_argument("--world", choices=WORLDS)
    parser.add_argument("--population", choices=sorted(core.POPULATIONS))
    parser.add_argument("--rates", choices=sorted(RATES))
    parser.add_argument("--bots", type=int, help="bot players online at once (a living world)")
    parser.add_argument("--yes", action="store_true", help="ask nothing: defaults for whatever was not said "
                                                           "(a world that is already set up keeps what it has)")
    return parser.parse_args(argv)


def main(argv, kit=HERE, log=print, fetch=None, terminal=None, **stand_ins):
    """The "setup" command. Returns the exit code."""
    import launcher_thirdparty as tp
    args = parse(argv)
    fetch = fetch or tp._get
    given = {"name": args.name, "address": args.address, "port": args.port, "open": args.open, "max_guests": args.max_guests,
             "world": args.world, "population": args.population, "rates": args.rates, "bots": args.bots, "password": None}
    try:
        if args.password_file is not None:
            with open(args.password_file, encoding="utf-8") as handle:
                given["password"] = handle.readline().rstrip("\r\n")
        again = bool(stored_answers(kit))
        given = with_stored(kit, given)
        found = "" if number_address(given["address"]) else find_address(fetch)
        terminal = terminal or (None if args.yes or again else Terminal())
        if again:
            log("This world is already set up: it keeps its settings, except what the options say.")
        if terminal is not None and terminal.usable() and not args.yes and not again:
            given = ask_answers(given, terminal, found)
        else:
            if not given["address"]:
                given["address"] = found
                if not found:
                    raise SetupError("This server's address could not be found out. Say it with --address.")
            if given["open"] is None:
                given["open"] = True
        made = setup_world(kit, given, log=log, fetch=fetch, **stand_ins)
    except (SetupError, OSError, RuntimeError, ValueError) as problem:
        log(f"Setup stopped: {problem}")
        return 1
    finally:
        if terminal is not None:
            terminal.close()
    if made["invite"]:
        log("Invite code for your friends: " + made["invite"])
    else:
        log("The world's link is shown by 'launcher_world.py status' once the world has started for the first time.")
    return 0
