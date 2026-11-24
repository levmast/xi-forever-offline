"""Tests for the first setup of a world that runs without the launcher's window (launcher_world_setup.py, 2026-11-23).
The internet and the database's programs are stand-ins; the world's name goes into a real scratch database (the one
the other co-op tests use).   Run: COOP_TEST_DB=socket:/run/mysqld/mysqld.sock:xi python test_world_setup.py"""
import hashlib, io, json, os, shutil, stat, sys, tarfile, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_coop as co
import launcher_core as core
import launcher_passport as pp
import launcher_setup as setup
import launcher_thirdparty as tp
import launcher_update as lu
import launcher_world_keep as keep
import launcher_world_setup as ws

NETWORK = "xi.settings.network =\n{\n    SQL_HOST     = '127.0.0.1',\n    SQL_PORT     = 3306,\n    SQL_LOGIN    = 'root',\n    SQL_PASSWORD = 'root',\n    SQL_DATABASE = 'xidb',\n}\n"
LINUX = os.name != "nt"
KEPT = {}


def setUpModule():
    try:
        ct.make_world(ct.HOST_DB).close()
    except Exception as e:
        raise unittest.SkipTest(f"no scratch database ({e})")
    KEPT["start"] = setup.start_mariadb
    setup.start_mariadb = lambda mdb, port, popen=None, wait=30: None           # ("already running")


def tearDownModule():
    setup.start_mariadb = KEPT["start"]
    ct.drop_worlds()


class Done:
    def __init__(self, out=""):
        self.returncode, self.stdout, self.stderr = 0, out, ""


class FakeMaria:
    """Stands in for the database's programs. tables: what SHOW TABLES LIKE 'accounts' answers."""

    def __init__(self, tables=""):
        self.calls, self.tables = [], tables

    def run(self, cmd, **kw):
        self.calls.append(list(cmd))
        if "mariadb-install-db" in cmd[0]:
            data = next(part.split("=", 1)[1] for part in cmd if str(part).startswith("--datadir="))
            os.makedirs(os.path.join(data, "mysql"), exist_ok=True)
        if cmd[-1].startswith("SHOW TABLES LIKE"):
            return Done(self.tables)
        return Done("")

    def statements(self):
        return [c[-1] for c in self.calls if "-e" in c]


def server_package(marker):
    data = io.BytesIO()
    files = {"xi_map": "program", "VERSION.txt": f"XI: Forever Offline server {marker}\n", "sql/accounts.sql": "--\n", "sql/zones.sql": "--\n",
             "sql/triggers.sql": "--\n", "settings/default/network.lua": NETWORK, "modules/init.txt": "custom/sql\n",
             "modules/custom/sql/squad.sql": "--\n", "settings/network.lua": "someone else's login\n" if marker == "bad" else NETWORK}
    files.pop("settings/network.lua")
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for rel, text in files.items():
            raw = text.encode()
            info = tarfile.TarInfo("server/" + rel)
            info.size, info.mode = len(raw), 0o755 if rel == "xi_map" else 0o644
            archive.addfile(info, io.BytesIO(raw))
    return data.getvalue()


class Net:
    """The stand-in internet: two server releases (the newer one a test build), and sites that tell an address."""

    def __init__(self, address="93.184.216.34"):
        self.asked, self.pages = [], {}
        releases = []
        for tag, pre in (("v0.4.0-test1", True), ("v0.3.2", False)):
            name = f"xi-forever-offline-server-{tag}-linux-x64.tar.gz"
            data = server_package(tag)
            self.pages[f"https://dl/{tag}/{name}"] = data
            self.pages[f"https://dl/{tag}/sums"] = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode()
            releases.append({"tag_name": tag, "draft": False, "prerelease": pre, "assets": [
                {"name": name, "browser_download_url": f"https://dl/{tag}/{name}"},
                {"name": "SHA256SUMS-linux.txt", "browser_download_url": f"https://dl/{tag}/sums"}]})
        self.releases = releases
        self.pages[tp.API + lu.SERVER_REPO + "/releases?per_page=30"] = json.dumps(releases).encode()
        self.pages[tp.API + lu.SERVER_REPO + "/releases?per_page=20"] = json.dumps(releases).encode()
        self.pages[tp.API + lu.SERVER_REPO + "/releases/tags/v0.3.2"] = json.dumps(releases[1]).encode()
        self.pages[tp.API + lu.SERVER_REPO + "/releases/tags/v0.4.0-test1"] = json.dumps(releases[0]).encode()
        self.pages[tp.API + lu.SERVER_REPO + "/releases/latest"] = json.dumps(releases[1]).encode()
        if address:
            self.pages[ws.ADDRESS_SITES[1]] = (address + "\n").encode()

    def __call__(self, url, timeout=60):
        self.asked.append(url)
        if url not in self.pages:
            raise OSError("no such page: " + url)
        return self.pages[url]


class Answers(unittest.TestCase):
    def test_defaults_for_an_open_world_and_for_friends(self):
        got = ws.clean_answers({"address": " 203.0.113.20 ", "open": True})
        self.assertEqual((got["name"], got["address"], got["port"], got["max_guests"], got["world"], got["population"], got["rates"],
                          got["password"], got["bots"]), ("A world", "203.0.113.20", co.PORT, ws.OPEN_GUESTS, "living", "small", "era", None, None))
        self.assertEqual(ws.clean_answers({"address": "203.0.113.20", "open": False})["max_guests"], ws.FRIEND_GUESTS)
        self.assertEqual(ws.clean_answers({"address": "8.8.8.8", "name": "  Vana'diel <b>Hub</b>!  "})["name"], "Vana'diel bHubb!")
        self.assertIsNone(ws.clean_answers({"address": "8.8.8.8"})["note"])
        self.assertIn("not an address of the open internet", ws.clean_answers({"address": "192.168.1.20"})["note"])

    def test_what_cannot_work_is_said_before_anything_is_done(self):
        good = {"address": "8.8.8.8", "open": True}
        for bad in ({"address": "hub.example.com"}, {"address": "8.8.8"}, {"address": "300.1.1.1"}, {"address": "127.0.0.1"}, {"address": "0.0.0.0"},
                    {"port": 54230}, {"port": 80}, {"port": "x"}, {"max_guests": 0}, {"max_guests": co.MAX_OPEN_GUESTS + 1},
                    {"open": False, "max_guests": co.MAX_GUESTS + 1}, {"open": False, "password": "secret"}, {"password": "x" * 65},
                    {"password": "two\nlines"}, {"world": "living_ai"}, {"population": "huge"}, {"rates": "x100"}, {"bots": "many"}):
            with self.assertRaises(ws.SetupError, msg=str(bad)):
                ws.clean_answers(dict(good, **bad))
        self.assertEqual(ws.clean_answers(dict(good, max_guests=co.MAX_OPEN_GUESTS))["max_guests"], co.MAX_OPEN_GUESTS)
        self.assertEqual(ws.clean_answers(dict(good, open=False, max_guests=co.MAX_GUESTS))["max_guests"], co.MAX_GUESTS)
        self.assertEqual(ws.clean_answers(dict(good, bots=9999))["bots"], 550)

    def test_the_rules_of_a_world(self):
        answers = lambda **more: ws.clean_answers(dict({"address": "8.8.8.8"}, **more))
        living = ws.world_rates(answers())
        self.assertEqual((living["bots"], living["crowds"], living["ah_sim"], living["bots_online"], living["bots_roster"], living["crowds_per_zone"]),
                         (True, True, True, 40, 100, 10))
        self.assertEqual((living["crowds_chat_ai"], living["squad_chat"]), (False, False), "nothing on a server runs an AI")
        kept = dict(core.WORLD_SWITCHES["living"])
        core.WORLD_SWITCHES["living"].update({"crowds_chat_ai": True, "squad_chat": True})      # (should a living world ever come with it)
        try:
            talking = ws.world_rates(answers())
        finally:
            core.WORLD_SWITCHES["living"].update(kept)
        self.assertEqual((talking["crowds_chat_ai"], talking["squad_chat"], talking["bots"]), (False, False, True))
        self.assertEqual((living["era_exp"], living["map.EXP_RATE"]), (True, core.RATE_DEFAULTS["map.EXP_RATE"]))
        quiet = ws.world_rates(answers(world="quiet", bots=100))
        self.assertEqual((quiet["bots"], quiet["crowds"], quiet["ah_sim"]), (False, False, False))
        self.assertEqual(quiet["bots_online"], 40, "no bot players: the number is left as the population has it")
        hub = ws.world_rates(answers(bots=100))
        self.assertEqual((hub["bots_online"], hub["bots_roster"]), (100, 200))
        fast = ws.world_rates(answers(rates="fast", population="large"))
        self.assertEqual((fast["map.EXP_RATE"], fast["era_exp"], fast["bots_online"], fast["squad_chat"]), (5.0, False, 500, False))

    def test_this_servers_address_is_looked_up(self):
        net = Net(address="93.184.216.34")
        net.pages[ws.ADDRESS_SITES[0]] = b"10.0.0.5"                    # a site that answers with an address inside a network
        self.assertEqual(ws.find_address(net), "93.184.216.34")
        self.assertEqual(net.asked, list(ws.ADDRESS_SITES[:2]))
        self.assertEqual(ws.find_address(Net(address="")), "")
        self.assertEqual(ws.find_address(Net(address="<html>not an address</html>")), "")

    def test_a_world_never_takes_a_test_build(self):
        net = Net()
        item = next(i for i in tp.load_manifest(ct.KIT) if i["id"] == "server")
        pinned = ws.server_item(item, net)
        self.assertEqual((pinned["source"]["tag"], pinned["source"].get("prereleases")), ("v0.3.2", None))
        self.assertEqual(item["source"]["tag"], "latest", "the manifest's own entry is not changed")
        net.pages[tp.API + lu.SERVER_REPO + "/releases?per_page=30"] = json.dumps(net.releases[:1]).encode()     # only a test build is out
        with self.assertRaises(ws.SetupError):
            ws.server_item(item, net)


@unittest.skipUnless(LINUX, "the packages here are the Linux ones")
class WholeSetup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kit = os.path.join(self.tmp, "kit")
        os.makedirs(os.path.join(self.kit, "mariadb", "bin"))
        for name in ("thirdparty.json", "config.example.json"):
            shutil.copy(os.path.join(ct.KIT, name), self.kit)
        with open(os.path.join(self.kit, "mariadb", "bin", "mariadbd"), "w") as handle:      # the database program is "there"
            handle.write("x")
        self.net, self.maria, self.lines = Net(), FakeMaria(), []
        conn = ct.connect(ct.HOST_DB)
        ct.run(conn, "DROP TABLE IF EXISTS coop_meta")
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def setup(self, **given):
        return ws.setup_world(self.kit, dict({"address": "93.184.216.34"}, **given), log=self.lines.append, fetch=self.net,
                              run=self.maria.run, connect=lambda cfg: ct.connect(ct.HOST_DB))

    def json(self, name):
        with open(os.path.join(self.kit, name), encoding="utf-8") as handle:
            return json.load(handle)

    def world_name(self):
        conn = ct.connect(ct.HOST_DB)
        try:
            return pp.world_identity(conn)["name"]
        finally:
            conn.close()

    def test_a_world_is_set_up_with_nothing_of_the_game(self):
        made = self.setup(name="The Hub", open=True, password="mog house", max_guests=30, bots=100)
        server = os.path.join(self.kit, "server")
        with open(os.path.join(server, "VERSION.txt")) as handle:
            self.assertIn("v0.3.2", handle.read(), "the newest full release, not the newer test build")
        self.assertTrue(os.access(os.path.join(server, "xi_map"), os.X_OK))
        cfg = self.json("config.json")
        self.assertEqual((cfg["server_dir"], cfg["mariadb_dir"], cfg["db_name"], cfg["db_user"], cfg["world_only"], cfg["mariadb_service"]),
                         (server, os.path.join(self.kit, "mariadb"), "xiforever", "xi", True, ""))
        self.assertEqual((cfg["ffxi_client_dir"], cfg["ashita_dir"], cfg["game_user"], cfg["game_pass"]), ("", "", "", ""))
        keys = self.json("mariadb/xiforever-db.json")
        self.assertEqual((cfg["db_pass"], cfg["db_port"]), (keys["xi"], keys["port"]))
        with open(os.path.join(server, "settings", "network.lua")) as handle:
            text = handle.read()
        self.assertIn(f"SQL_PASSWORD = '{keys['xi']}'", text)
        self.assertIn("SQL_DATABASE = 'xiforever'", text)
        rates = self.json("rates.json")
        self.assertEqual((rates["bots"], rates["bots_online"], rates["squad_chat"], rates["crowds_chat_ai"], rates["ah_sim"]), (True, 100, False, False, True))
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["enabled"], settings["hosting"], settings["mode"], settings["address"], settings["port"], settings["max_guests"],
                          settings["open"], settings["backup_done"]), (True, True, "direct", "93.184.216.34", co.PORT, 30, True, True))
        self.assertTrue(co.check_password(settings["password"], "mog house") and not co.check_password(settings["password"], "x"))
        self.assertNotIn("mog house", json.dumps(self.json("coop.json")))
        self.assertEqual(self.json("world.json"), keep.DEFAULTS)
        self.assertEqual((self.world_name(), made["name"], made["invite"]), ("The Hub", "The Hub", None))
        # the database: made, every SQL file of the server imported once, stopped again; no player account
        statements = self.maria.statements()
        self.assertTrue(any("CREATE DATABASE IF NOT EXISTS `xiforever`" in s for s in statements))
        self.assertEqual(len([s for s in statements if "SOURCE" in s]), 4)
        self.assertFalse(any("INSERT INTO accounts" in s for s in statements))
        self.assertTrue(any("shutdown" in c for c in self.maria.calls))
        # nothing of the game was fetched: no Ashita, no loader, no Proton, no game files
        self.assertTrue(all(lu.SERVER_REPO in url or url.startswith("https://dl/v0.3.2/") for url in self.net.asked), self.net.asked)
        for name in ("Ashita", "proton", "prefix", "Game"):
            self.assertFalse(os.path.exists(os.path.join(self.kit, name)))
        # only the world's own user reads its passwords
        for name in ("config.json", "coop.json", "mariadb/xiforever-db.json"):
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.kit, name)).st_mode), 0o600, name)
        self.assertIn('Setup finished. "The Hub" at 93.184.216.34, port 54100: open to anyone with its link, with a password, 30 visitors at most.', self.lines)

    def test_running_it_again_keeps_the_world_and_takes_the_new_answers(self):
        self.setup(name="First", open=True, password="one", max_guests=10)
        stored = co.load_settings(self.kit)["password"]
        first = {name: open(os.path.join(self.kit, name)).read() for name in ("config.json", "mariadb/xiforever-db.json")}
        rates = self.json("rates.json")
        rates["map.EXP_RATE"] = 3.0                                   # the owner changed a rule by hand
        core.save_rates(self.kit, rates)
        keep.save_settings(self.kit, dict(keep.DEFAULTS, backup_hour=6))
        asked = len(self.net.asked)
        self.maria = FakeMaria(tables="accounts\n")
        self.setup(address="93.184.216.99", open=True, max_guests=20, world="quiet")
        self.assertEqual({name: open(os.path.join(self.kit, name)).read() for name in first}, first)
        self.assertEqual(self.net.asked[asked:], [], "nothing is downloaded again")
        self.assertEqual([s for s in self.maria.statements() if "SOURCE" in s], [], "the tables are not imported over the world")
        self.assertEqual((self.json("rates.json")["map.EXP_RATE"], self.json("rates.json")["bots"]), (3.0, True), "the rules stay as they are")
        self.assertEqual(self.json("world.json")["backup_hour"], 6)
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["address"], settings["max_guests"]), ("93.184.216.99", 20))
        self.assertTrue(stored and settings["password"] == stored, "no password given: the one from before stays")
        self.assertEqual(self.world_name(), "First", "no name given: the one from before stays")
        self.setup(name="Second", open=True, password="")
        self.assertEqual((self.world_name(), co.load_settings(self.kit)["password"]), ("Second", ""))

    def test_a_world_for_friends_gets_an_invite_code(self):
        made = self.setup(name="Ours", open=False)
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["open"], settings["max_guests"], settings["password"]), (False, ws.FRIEND_GUESTS, ""))
        invite = co.read_invite(made["invite"])
        self.assertEqual((invite["address"], invite["port"], invite["world"]), ("93.184.216.34", co.PORT, "Ours"))
        self.setup(open=True, password="pw")
        self.setup(open=False)
        self.assertEqual(co.load_settings(self.kit)["password"], "", "back to friends only: the password goes")

    def test_never_over_a_players_install(self):
        with open(os.path.join(self.kit, "config.json"), "w") as handle:
            json.dump({"server_dir": "x", "game_user": "player1"}, handle)
        with self.assertRaises(ws.SetupError):
            self.setup()
        self.assertEqual((self.maria.calls, self.net.asked), ([], []))
        self.assertFalse(os.path.exists(os.path.join(self.kit, "coop.json")))

    def test_bad_answers_stop_it_before_anything_is_downloaded(self):
        with self.assertRaises(ws.SetupError):
            self.setup(address="not an address")
        self.assertEqual((self.maria.calls, self.net.asked, os.path.exists(os.path.join(self.kit, "server"))), ([], [], False))

    def test_a_release_whose_linux_server_is_not_up_yet(self):
        release = dict(self.net.releases[1], assets=[])
        self.net.pages[tp.API + lu.SERVER_REPO + "/releases/tags/v0.3.2"] = json.dumps(release).encode()
        with self.assertRaises(ws.SetupError) as caught:
            self.setup()
        self.assertIn("still being built", str(caught.exception))

    # --- the command ---
    def command(self, *argv, terminal=None, net=None):
        return ws.main(list(argv), kit=self.kit, log=self.lines.append, fetch=net or self.net, terminal=terminal,
                       run=self.maria.run, connect=lambda cfg: ct.connect(ct.HOST_DB))

    def test_the_command_without_questions(self):
        self.assertEqual(self.command("--yes", "--name", "Cloud"), 0)
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["address"], settings["open"], settings["max_guests"], settings["password"]), ("93.184.216.34", True, ws.OPEN_GUESTS, ""))
        self.assertEqual(self.world_name(), "Cloud")
        self.assertTrue(any("status" in line for line in self.lines))

    def test_a_second_run_keeps_what_it_is_not_told_to_change(self):
        secret, empty = os.path.join(self.tmp, "pw.txt"), os.path.join(self.tmp, "none.txt")
        with open(secret, "w") as handle:
            handle.write("kupo nuts\n")
        open(empty, "w").close()
        self.assertEqual(self.command("--yes", "--name", "The Hub", "--port", "54111", "--max-guests", "30", "--password-file", secret), 0)
        self.assertFalse(any("already set up" in line for line in self.lines))
        self.maria = FakeMaria(tables="accounts\n")
        net = Net(address="93.184.216.77")                             # (this server's address would be found differently now)
        self.assertEqual(self.command("--yes", "--password-file", empty, net=net), 0)      # the hub's case: only the password comes off
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["address"], settings["port"], settings["max_guests"], settings["open"], settings["password"]),
                         ("93.184.216.34", 54111, 30, True, ""))
        self.assertFalse(any(site in net.asked for site in ws.ADDRESS_SITES), "the address a world has is not looked up again")
        self.assertEqual(self.world_name(), "The Hub")
        self.assertTrue(any("already set up" in line for line in self.lines))
        self.assertTrue(any(line.endswith("open to anyone with its link, 30 visitors at most.") for line in self.lines))
        self.assertEqual(self.command("--yes", "--password-file", secret), 0)
        self.assertEqual(self.command("--yes", "--max-guests", "20", "--address", "93.184.216.99"), 0)     # what is said is taken
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["address"], settings["port"], settings["max_guests"]), ("93.184.216.99", 54111, 20))
        self.assertTrue(co.check_password(settings["password"], "kupo nuts"), "no password given: the one from before stays")
        self.assertEqual(self.command("--yes", "--friends"), 0)        # another kind of world has its own limit, not the old one
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["open"], settings["max_guests"], settings["password"], settings["port"]), (False, ws.FRIEND_GUESTS, "", 54111))
        self.assertEqual(self.command("--yes"), 0)
        self.assertEqual((co.load_settings(self.kit)["open"], co.load_settings(self.kit)["max_guests"]), (False, ws.FRIEND_GUESTS))
        self.assertEqual(self.command("--yes", "--open"), 0)
        self.assertEqual((co.load_settings(self.kit)["open"], co.load_settings(self.kit)["max_guests"]), (True, ws.OPEN_GUESTS))
        self.assertEqual(self.setup(address=None, max_guests=None, open=None)["settings"]["max_guests"], ws.OPEN_GUESTS)
        self.assertEqual(co.load_settings(self.kit)["address"], "93.184.216.99", "also for a setup that is called, not typed")

    def test_a_second_run_asks_nothing(self):
        self.assertEqual(self.command("--yes", "--max-guests", "30"), 0)
        self.maria = FakeMaria(tables="accounts\n")

        class Never:
            handle = io.StringIO()
            usable = lambda self: True
            close = lambda self: None

            def ask(self, question, *_more, **_others):
                raise AssertionError("a world that is set up is not asked: " + question)

            choose = ask

        self.assertEqual(self.command(terminal=Never()), 0)
        self.assertEqual((co.load_settings(self.kit)["max_guests"], self.world_name()), (30, ws.DEFAULT_NAME))

    def test_a_folder_that_is_no_world_has_nothing_to_keep(self):
        self.assertEqual(ws.stored_answers(self.kit), {})
        self.assertEqual(ws.with_stored(self.kit, {"max_guests": None, "open": None}), {"max_guests": None, "open": None})
        with open(os.path.join(self.kit, "config.json"), "w") as handle:      # a player's install with co-op hosting on
            json.dump({"server_dir": "x"}, handle)
        co.save_settings(self.kit, dict(co.load_settings(self.kit), enabled=True, hosting=True, address="192.168.1.20", max_guests=5))
        self.assertEqual(ws.stored_answers(self.kit), {})

    def test_the_command_needs_an_address_it_can_find_or_is_told(self):
        self.assertEqual(self.command("--yes", net=Net(address="")), 1)
        self.assertTrue(any("could not be found out. Say it with --address" in line for line in self.lines))
        self.assertFalse(os.path.exists(os.path.join(self.kit, "config.json")))
        net = Net(address="")
        self.assertEqual(self.command("--yes", "--address", "93.184.216.8", "--friends", net=net), 0)
        self.assertFalse(any(site in net.asked for site in ws.ADDRESS_SITES), "an address that was given is not looked up")
        self.assertTrue(any(line.startswith("Invite code for your friends: XIFO1-") for line in self.lines))

    def test_the_password_comes_from_a_file_never_from_the_command_line(self):
        secret = os.path.join(self.tmp, "pw.txt")
        with open(secret, "w") as handle:
            handle.write("kupo nuts\nsecond line\n")
        self.assertEqual(self.command("--yes", "--password-file", secret), 0)
        self.assertTrue(co.check_password(co.load_settings(self.kit)["password"], "kupo nuts"))
        with self.assertRaises(SystemExit):
            self.command("--yes", "--password", "x")

    def test_questions_are_asked_for_what_was_not_said(self):
        class Asked:
            def __init__(self, answers):
                self.answers, self.questions, self.handle = list(answers), [], io.StringIO()
            usable = lambda self: True
            close = lambda self: None

            def ask(self, question, default="", secret=False):
                self.questions.append((question.split(" (")[0], default, secret))
                answer = self.answers.pop(0)
                return answer if answer else default

            choose = ws.Terminal.choose
        terminal = Asked(["", "", "9", "2", "6", "2"])
        self.assertEqual(self.command("--rates", "relaxed", terminal=terminal), 0)
        asked = [q[0] for q in terminal.questions]
        self.assertEqual(asked, ["The world's name", "This server's address on the internet", "Who can come in", "Who can come in",
                                 "Visitors at most", "The world"])
        self.assertEqual(terminal.answers, [], "friends only: no password is asked for; a quiet world: no population")
        self.assertEqual(terminal.questions[1][1], "93.184.216.34", "the address that was found is offered")
        self.assertNotIn("The rates", asked, "what an option said is not asked")
        self.assertIn("Please answer with one of the numbers.", terminal.handle.getvalue())
        settings = co.load_settings(self.kit)
        self.assertEqual((settings["open"], settings["max_guests"], settings["password"]), (False, 6, ""))
        self.assertEqual((self.json("rates.json")["bots"], self.json("rates.json")["map.EXP_RATE"]), (False, 2.0))


if __name__ == "__main__":
    unittest.main(verbosity=1)
