"""Tests for the world that runs without the launcher's window (launcher_world.py, 2026-11-23). The programs it would
start (the database, the five game servers) are stand-ins; the co-op door is the real one, over the real port, on the
scratch databases of test_openservice.py. Run: python test_world.py"""
import json, os, socket, sys, threading, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_coop as co
import launcher_core as core
import launcher_passport as pp
import launcher_update as lu
import launcher_world as wd
import launcher_world_keep as keep
import test_openservice as svc
import test_world_keep as tk

ACC, CHAR = svc.ACC, svc.CHAR
KEPT = {}


def setUpModule():
    svc.setUpModule()
    KEPT.update(connect=pp.connect, addresses=co.local_addresses, tick=wd.TICK_SECONDS, keep_out=co.KEEP_OUT_SECONDS)
    pp.connect = lambda cfg: ct.connect(cfg["db_name"])
    co.local_addresses = lambda: []                  # (this machine has no address of its own kind to fall back on)
    wd.TICK_SECONDS = 0.01


def tearDownModule():
    pp.connect, co.local_addresses, wd.TICK_SECONDS, co.KEEP_OUT_SECONDS = KEPT["connect"], KEPT["addresses"], KEPT["tick"], KEPT["keep_out"]
    svc.tearDownModule()


class Proc:
    """A stand-in for a started program."""

    def __init__(self, name):
        self.name, self.code, self.ended_by = name, None, None

    def poll(self):
        return self.code

    def terminate(self):
        if self.code is None:
            self.code, self.ended_by = 0, "terminate"

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code, self.ended_by = -9, "kill"


class World(wd.World):
    """The real world with stand-ins for everything that starts a program or takes real time."""

    def __init__(self, kit, cfg, map_says="the map server is ready to work\n"):
        self.steps, self.lines, self.now, self.map_says = [], [], 1000000.0, map_says
        super().__init__(kit, cfg, log=self.lines.append)
        self.clock = lambda: self.now
        self.sleep = self.pass_time
        # backups and updates: the work beside the world is done at once, the programs and the internet are stand-ins
        self.maria, self.net, self.backups_on = tk.FakeMaria(), tk.Net(), False
        due = self.keeper.due_backup
        self.keeper.due_backup = lambda now: self.backups_on and due(now)
        self.keeper.background = lambda work: work()
        at_start = self.keeper.at_start
        self.keeper.at_start = lambda: (self.steps.append("updates"), at_start())[1]
        self.keeper.run, self.keeper.fetch, self.keeper.check = self.maria.run, self.net, lambda kit: None

    def pass_time(self, seconds):
        self.now += seconds

    def load_rates(self):
        return {"ah_sim": False, "conquest_sim": False}

    def clean_up(self):
        self.steps.append("clean up")

    def database(self):
        self.steps.append("database")

    def stop_database(self):
        self.steps.append("database stopped")

    def chores(self):
        self.steps.append("chores")

    def apply_rates(self):
        self.steps.append(f"rules (hosting {self.hosting})")

    def spawn(self, name):
        self.steps.append("start " + name)
        os.makedirs(self.logs, exist_ok=True)
        log = open(os.path.join(self.logs, name + ".log"), "wb")
        if name == "xi_map":
            log.write(self.map_says.encode())
            log.flush()
        return Proc(name), log


def listening(port):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


class WorldCase(unittest.TestCase):
    def setUp(self):
        svc.OpenWorld.setUp(self)                # two scratch worlds, a certificate, settings of an open world
        self.host.stop()                         # (the world under test opens the door itself)
        self.cfg_host = {"server_dir": self.server, "db_name": ct.HOST_DB}
        self.worlds = []

    def tearDown(self):
        for world in self.worlds:
            world.stop(grace=0)
        svc.OpenWorld.tearDown(self)

    q, away = svc.OpenWorld.q, svc.OpenWorld.away

    def world(self, **settings):
        self.settings.update(settings)
        co.save_settings(self.kit_host, self.settings)
        world = World(self.kit_host, self.cfg_host)
        self.worlds.append(world)
        return world

    def door(self):
        return {"address": "127.0.0.1", "port": self.settings["port"], "pin": co.server_fingerprint(self.server), "world": "", "open": True}

    def visit(self):
        return co.start_visit(self.cfg, self.kit_home, self.door(), CHAR, log=self.logs.append, connect=self.connect_home)

    def lua_lines(self, kind):
        try:
            with open(os.path.join(self.server, "modules", "custom", "lua", "coop_in.txt")) as handle:
                return [line.split("|", 3)[3] for line in handle.read().splitlines() if f"|{kind}|" in line]
        except OSError:
            return []


class Worlds(WorldCase):
    # --- starting ---
    def test_a_start_does_what_play_does_for_the_servers(self):
        world = self.world(address="203.0.113.9")        # an address this machine does not own, as on a rented server
        world.start()
        # (a waiting update goes in while only the database runs, and before the chores: they change tables an update imports again)
        self.assertEqual(world.steps, ["clean up", "database", "updates", "chores", "rules (hosting True)"] + ["start " + n for n in core.SERVERS])
        self.assertEqual((world.state, world.hosting), ("running", True))
        self.assertEqual(self.q(self.host_db, "SELECT DISTINCT zoneip FROM zone_settings"), [("203.0.113.9",)])   # the game hands out that address
        with open(os.path.join(self.server, "modules", "custom", "lua", "coop_config.lua")) as handle:
            self.assertIn("open = true", handle.read())
        greeting = co.hello(self.door())                                           # the door answers, with the server's own certificate
        self.assertTrue(greeting["open"] and greeting["open_world"])
        status = wd.read_status(self.kit_host)
        self.assertEqual((status["state"], status["hosting"], status["open"], status["address"], status["port"], status["visitors"],
                          status["max_guests"], status["pid"]),
                         ("running", True, True, "203.0.113.9", self.settings["port"], 0, self.settings["max_guests"], os.getpid()))
        self.assertTrue(any(line.startswith("World link: XIFO2-") for line in world.lines))
        self.assertTrue(any("The world is ready" in line for line in world.lines))
        with open(os.path.join(self.kit_host, "logs", "world.log"), encoding="utf-8") as handle:
            self.assertIn("The world is ready", handle.read())

    def test_on_a_home_network_an_address_that_is_not_this_machines_keeps_the_world_private(self):
        world = self.world(mode="lan", address="203.0.113.9")
        world.start()
        self.assertEqual((world.state, world.hosting, world.host), ("running", False, None))
        self.assertIn("rules (hosting False)", world.steps)
        self.assertFalse(listening(self.settings["port"]))
        self.assertEqual(wd.read_status(self.kit_host)["hosting"], False)
        self.assertIn("Private", wd.describe(wd.read_status(self.kit_host)))

    def test_a_world_with_co_op_switched_off_runs_private(self):
        world = self.world(enabled=False)
        world.start()
        self.assertEqual((world.state, world.hosting, world.host), ("running", False, None))
        self.assertEqual(len(world.procs), len(core.SERVERS))

    def test_one_world_per_install(self):
        first = self.world()
        first.start()
        second = World(self.kit_host, self.cfg_host)
        self.assertEqual(second.run(), 1)                                          # refused...
        self.assertIn("already running", second.problem)
        self.assertEqual(second.steps, [])                                         # ...before it touched anything
        self.assertTrue(all(proc.code is None for proc in first.procs.values()))   # the first one's servers are left alone
        self.assertEqual(wd.read_status(self.kit_host)["state"], "running")        # and so is what it wrote about itself
        first.stop(grace=0)
        third = World(self.kit_host, self.cfg_host)
        self.worlds.append(third)
        third.start()                                                              # once it has stopped, the install is free again
        self.assertEqual(third.state, "running")

    def test_a_start_that_fails_leaves_nothing_running(self):
        world = self.world()
        world.database = lambda: (_ for _ in ()).throw(wd.WorldError("The database service 'MariaDB' was not found or would not start."))
        self.assertEqual(world.run(), 1)
        self.assertEqual((world.state, world.procs, world.host), ("stopped", {}, None))
        status = wd.read_status(self.kit_host)
        self.assertEqual(status["state"], "stopped")
        self.assertIn("database service", status["problem"])
        self.assertIn("Last problem: The database service", wd.describe(status))

    def test_a_server_that_stops_while_the_world_loads_ends_the_start(self):
        world = self.world()
        world.map_says = "still loading\n"
        spawn = world.spawn

        def dying(name):
            proc, log = spawn(name)
            if name == "xi_search":
                proc.code = 3
                log.write(b"could not bind the search port\n")
                log.flush()
            return proc, log

        world.spawn = dying
        self.assertEqual(world.run(), 1)
        self.assertIn("xi_search stopped by itself", world.problem)
        self.assertIn("could not bind the search port", world.problem)             # with the end of its log
        self.assertFalse(any("The world is ready" in line for line in world.lines))
        self.assertEqual(world.state, "stopped")
        self.assertFalse(listening(self.settings["port"]))                         # the door was never opened

    # --- running ---
    def test_a_game_server_that_stops_ends_the_world_so_the_service_starts_it_again(self):
        world = self.world()
        looks, tick = [], world.tick

        def watched():
            looks.append(1)
            if len(looks) == 2:                                                    # a visitor is in the game when it happens
                self.visit()
                guest = pp.guest_list(self.host_db)[0]
                ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
                self.host_db.commit()
            if len(looks) == 3:
                world.procs["xi_map"].code = 139
            if len(looks) > 40:                                                    # (a world that did not notice: end the test anyway)
                world.stopping.set()
            tick()

        world.tick = watched
        started = dict.fromkeys(core.SERVERS)
        spawn = world.spawn
        world.spawn = lambda name: started.__setitem__(name, spawn(name)) or started[name]
        before = world.now
        self.assertEqual(world.run(), 1)
        self.assertEqual(len(looks), 3)
        self.assertIn("xi_map stopped by itself", world.problem)
        self.assertLess(world.now - before, wd.STOP_GRACE_SECONDS)                 # no minute of grace: the game is gone already
        self.assertNotIn(wd.CLOSING_LINE[:150], self.lua_lines("SAY"))
        self.assertEqual({name: pair[0].ended_by for name, pair in started.items() if name != "xi_map"},
                         {name: "terminate" for name in core.SERVERS if name != "xi_map"})    # the others are stopped with it
        self.assertFalse(listening(self.settings["port"]))
        self.assertEqual(world.steps[-1], "database stopped")
        self.assertEqual(wd.read_status(self.kit_host)["state"], "stopped")

    def test_the_world_keeps_a_banned_visitor_out_by_itself(self):
        co.KEEP_OUT_SECONDS = 0                                                    # (asked out again at every look, for this test)
        world = self.world()
        world.start()
        host = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()
        world.tick()                                                               # (the first look of a running world)
        world.host.ban(host["guest_id"])
        self.assertEqual(len(self.lua_lines("KICK")), 1)
        world.tick()                                                               # too soon after the last look: nothing
        self.assertEqual(len(self.lua_lines("KICK")), 1)
        world.pass_time(wd.GUESTS_SECONDS)
        world.tick()
        self.assertEqual(self.lua_lines("KICK"), [str(guest["charid"])] * 2)
        world.pass_time(wd.GUESTS_SECONDS)
        world.tick()
        self.assertEqual(len(self.lua_lines("KICK")), 3)
        self.assertEqual(wd.read_status(self.kit_host)["visitors"], 0)             # (written at the start; the next one is due later)
        world.pass_time(wd.STATUS_SECONDS)
        world.tick()
        status = wd.read_status(self.kit_host)
        self.assertEqual((status["visitors"], status["online"]), (1, 1))

    def test_a_look_that_fails_does_not_stop_the_world(self):
        world = self.world()
        world.start()
        world.host.guests = lambda: (_ for _ in ()).throw(RuntimeError("the database went away"))
        world.pass_time(wd.GUESTS_SECONDS)
        world.tick()
        self.assertEqual(world.state, "running")
        self.assertTrue(any("could not look at the visitors" in line for line in world.lines))

    # --- stopping ---
    def test_asked_to_stop_visitors_are_told_and_keep_their_place(self):
        world = self.world()
        done = []
        runner = threading.Thread(target=lambda: done.append(world.run()), daemon=True)
        runner.start()
        end = time.time() + 20
        while world.state != "running" and time.time() < end:
            time.sleep(0.02)
        self.assertEqual(world.state, "running")
        self.visit()
        guest = pp.guest_list(self.host_db)[0]
        ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()
        before = world.now
        world.stopping.set()                                                       # what Ctrl+C or the service's stop does
        runner.join(30)
        self.assertEqual(done, [0])
        self.assertEqual(self.lua_lines("SAY")[-1], wd.CLOSING_LINE.replace("|", " ")[:150])
        self.assertGreaterEqual(world.now - before, wd.STOP_GRACE_SECONDS)         # the visitor did not log out: the whole minute was given
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("active",)])   # nobody was sent home
        self.assertTrue(self.away()[0]["host"]["arrived"])
        self.assertEqual((world.state, world.procs, world.host), ("stopped", {}, None))
        self.assertFalse(listening(self.settings["port"]))
        self.assertEqual(world.steps[-1], "database stopped")
        self.assertEqual(wd.read_status(self.kit_host)["state"], "stopped")

    def test_nobody_in_the_game_means_no_waiting(self):
        world = self.world()
        world.start()
        self.visit()                                                               # visiting, but not in the game right now
        before = world.now
        world.stop()
        self.assertLess(world.now - before, 10)
        self.assertEqual(self.lua_lines("SAY"), ["Visitor is visiting this world."])   # (no closing line was needed)
        world.stop()                                                               # a second stop is harmless
        self.assertEqual(world.steps.count("database stopped"), 1)

    def test_visitors_who_log_out_end_the_wait_early(self):
        world = self.world()
        world.start()
        self.visit()
        guest = pp.guest_list(self.host_db)[0]
        ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()
        naps = []

        def nap(seconds):
            naps.append(seconds)
            world.now += seconds
            if len(naps) == 3:                                                     # the visitor logs out after a few seconds
                ct.run(self.host_db, "DELETE FROM accounts_sessions")
                self.host_db.commit()

        world.sleep = nap
        before = world.now
        world.stop()
        self.assertEqual(len(naps), 3)
        self.assertLess(world.now - before, wd.STOP_GRACE_SECONDS)

    # --- what it tells about itself ---
    def test_status_for_a_person(self):
        self.assertEqual(wd.describe(None), "No world has run on this install yet.")
        status = {"state": "running", "updated": 1000, "versions": {"kit": "v0.3.2", "server": "v0.3.2"}, "hosting": True, "open": True,
                  "address": "203.0.113.9", "port": 54100, "visitors": 3, "online": 2, "max_guests": 30, "problem": ""}
        text = wd.describe(status, now=1010)
        self.assertIn("State: running (last heard from 10 seconds ago)", text)
        self.assertIn("Open to everyone at 203.0.113.9 port 54100: 3 of 30 visitors, 2 in the game", text)
        self.assertIn("launcher v0.3.2, server v0.3.2", text)
        self.assertNotIn("may have been stopped", text)
        self.assertIn("may have been stopped", wd.describe(status, now=1000 + 4 * wd.STATUS_SECONDS))   # running, but silent for too long
        self.assertIn("Open to friends", wd.describe(dict(status, open=False), now=1010))
        self.assertEqual(wd.read_status(os.path.join(self.tmp, "no-such-kit")), None)
        os.makedirs(os.path.join(self.kit_home, "logs"))
        with open(os.path.join(self.kit_home, "logs", wd.STATUS_FILE), "w") as handle:
            handle.write("{half a file")
        self.assertEqual(wd.read_status(self.kit_home), None)


class Keeping(WorldCase):
    """Backups and updates of a running world (launcher_world_keep.py)."""
    NEW_SERVER = {"xi_map": "new map\n", "sql/zones.sql": "new zones\n", "VERSION.txt": "XI: Forever Offline server v0.3.3\n"}
    NEW_KIT = {"ah_sim.py": "new sim\n", "VERSION.txt": "XI: Forever Offline v0.3.3\n"}

    def setUp(self):
        super().setUp()
        self.mdb = os.path.join(self.kit_host, "mariadb")
        os.makedirs(self.mdb, exist_ok=True)
        with open(os.path.join(self.mdb, "xiforever-db.json"), "w") as handle:
            json.dump({"root": "rootpw", "xi": "xipw", "port": 3306}, handle)
        self.cfg_host.update({"db_user": "xi", "db_pass": "xipw", "db_port": 3306, "mariadb_dir": self.mdb})
        self.net = tk.Net()

    def put(self, folder, files):
        for rel, text in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

    def installed(self, kit=None, server=None):
        """Gives the install versions (a self-built copy has none) and the internet its releases."""
        self.put(self.kit_host, {"VERSION.txt": "XI: Forever Offline v0.3.2\n", "ah_sim.py": "old sim\n"})
        self.put(self.server, {"VERSION.txt": "XI: Forever Offline server v0.3.2\n", "xi_map": "old map\n", "sql/zones.sql": "old zones\n"})
        for repo, files in ((lu.KIT_REPO, kit), (lu.SERVER_REPO, server)):
            if files:
                tk.publish(self.net, self.kit_host, repo, "v0.3.3", files)
            else:
                self.net.pages.setdefault(tk.tp.API + repo + "/releases?per_page=30", b"[]")

    def world(self, **settings):
        world = super().world(**settings)
        world.net = world.keeper.fetch = self.net
        return world

    def in_the_game(self):
        self.visit()
        guest = pp.guest_list(self.host_db)[0]
        ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()

    def versions(self):
        return lu.installed_version(self.kit_host), lu.installed_version(self.server)

    # --- backups ---
    def test_the_database_is_saved_once_a_night_while_the_world_runs(self):
        world = self.world()
        world.backups_on = True
        world.start()
        world.tick()
        first = keep.backups(self.kit_host)
        self.assertEqual([b["kind"] for b in first], ["nightly"])
        self.assertEqual(first[0]["time"], int(world.now), "named by the world's own clock")
        for _ in range(3):
            world.pass_time(3600)
            world.tick()
        self.assertEqual(len(keep.backups(self.kit_host)), 1, "one a night, not one an hour")
        world.pass_time(86400)
        world.tick()
        self.assertEqual(len(keep.backups(self.kit_host)), 2)
        world.write_status()
        status = wd.read_status(self.kit_host)
        self.assertEqual((status["backup"]["last"], status["backup"]["problem"]), (int(keep.backups(self.kit_host)[0]["time"]), ""))
        self.assertIn("Database last saved: ", wd.describe(status))
        for day in range(12):                                                      # old copies go, the newest stay
            world.pass_time(86400)
            world.tick()
        ages = sorted(round((world.now - b["time"]) / 86400) for b in keep.backups(self.kit_host))
        self.assertEqual(ages, list(range(0, 8)))

    def test_a_backup_that_fails_is_said_and_tried_again_an_hour_later(self):
        world = self.world()
        world.backups_on, world.maria.dump = True, None
        world.start()
        world.tick()
        self.assertEqual((keep.backups(self.kit_host), world.state), ([], "running"))
        tries = len(world.maria.calls)
        world.pass_time(600)
        world.tick()
        self.assertEqual(len(world.maria.calls), tries, "not at every look")
        world.write_status()
        status = wd.read_status(self.kit_host)
        self.assertIn("could not be saved", status["backup"]["problem"])
        self.assertIn("Backup problem: ", wd.describe(status))
        self.assertIn("not saved yet", wd.describe(status))
        world.maria.dump = tk.DUMP
        world.pass_time(3600)
        world.tick()
        self.assertEqual(len(keep.backups(self.kit_host)), 1)
        world.write_status()
        self.assertEqual(wd.read_status(self.kit_host)["backup"]["problem"], "")

    # --- updates ---
    def test_a_copy_without_a_version_never_looks_for_releases(self):
        world = self.world()
        world.start()
        for _ in range(3):
            world.pass_time(3600)
            world.tick()
        self.assertEqual(self.net.asked, [])

    def test_a_world_updates_itself_and_is_back_on_the_new_version(self):
        self.installed(server=self.NEW_SERVER)
        world = self.world()
        self.assertEqual(world.run(), keep.RESTART_CODE)                           # it looked, downloaded, and stopped to update
        self.assertEqual((world.state, self.versions()), ("stopped", ("v0.3.2", "v0.3.2")))
        self.assertEqual(keep.load_state(self.kit_host)["state"], "pending")
        self.assertIn("Stopping to update to v0.3.3.", world.lines)
        self.assertEqual(self.lua_lines("SAY"), [], "nobody is in the game: nobody is told, nobody is waited for")
        asked = len(self.net.asked)
        second = self.world()
        second.start()                                                             # the service starts it again
        self.assertEqual((second.state, self.versions()), ("running", ("v0.3.2", "v0.3.3")))
        self.assertEqual(self.net.asked[asked:], [], "the update goes in from what was already downloaded")
        # only the database runs then, and the chores come after: they change tables that an update imports again
        self.assertEqual(second.steps[:4], ["clean up", "database", "updates", "chores"])
        with open(os.path.join(self.server, "xi_map")) as handle:
            self.assertEqual(handle.read(), "new map\n")
        self.assertIsNone(keep.load_state(self.kit_host))
        self.assertIn("This world is now on v0.3.3.", second.lines)
        self.assertEqual([b["kind"] for b in keep.backups(self.kit_host)], ["before-update"])
        self.assertEqual(wd.read_status(self.kit_host)["update"]["state"], "none")
        second.pass_time(3600)
        second.tick()                                                              # nothing newer: it just runs on
        self.assertEqual(second.state, "running")

    def test_players_in_the_game_are_warned_before_the_world_stops(self):
        self.installed(server=self.NEW_SERVER)
        world = self.world()
        world.start()
        self.in_the_game()
        world.tick()                                                               # looks, downloads
        world.tick()                                                               # plans: ten minutes from now
        told = lambda: [line for line in self.lua_lines("SAY") if "updates to" in line]
        self.assertEqual(len(told()), 1)
        self.assertIn("updates to v0.3.3 in 10 minutes", told()[0])
        world.write_status()
        status = wd.read_status(self.kit_host)
        self.assertEqual((status["update"]["state"], status["update"]["to"], status["update"]["at"]), ("planned", "v0.3.3", int(world.now) + 600))
        self.assertIn("the world restarts for it at", wd.describe(status))
        world.pass_time(120)
        world.tick()
        self.assertEqual(len(told()), 1)
        world.pass_time(180)
        world.tick()
        self.assertIn("in 5 minutes", told()[-1])
        world.pass_time(240)
        world.tick()
        self.assertIn("in 1 minute.", told()[-1])
        self.assertEqual((len(told()), world.state, keep.load_state(self.kit_host)), (3, "running", None))
        world.pass_time(60)
        with self.assertRaises(keep.Restart):
            world.tick()
        self.assertEqual(keep.load_state(self.kit_host)["state"], "pending")

    def test_the_wait_ends_when_the_last_player_logs_out(self):
        self.installed(server=self.NEW_SERVER)
        world = self.world()
        world.start()
        self.in_the_game()
        world.tick()
        world.tick()
        ct.run(self.host_db, "DELETE FROM accounts_sessions")
        self.host_db.commit()
        world.pass_time(30)
        with self.assertRaises(keep.Restart):
            world.tick()

    def test_an_update_of_the_launcher_starts_the_world_once_more(self):
        self.installed(kit=self.NEW_KIT, server=self.NEW_SERVER)
        self.assertEqual(self.world().run(), keep.RESTART_CODE)                    # stopped to update
        second = self.world()
        self.assertEqual(second.run(), keep.RESTART_CODE)                          # updated; the new launcher has to be the one that runs
        self.assertEqual((self.versions(), keep.load_state(self.kit_host)["state"]), (("v0.3.3", "v0.3.3"), "applied"))
        self.assertNotIn("start xi_map", second.steps)
        self.assertEqual(second.steps[-1], "database stopped")
        third = self.world()
        third.start()
        self.assertEqual((third.state, keep.load_state(self.kit_host)), ("running", None))
        self.assertIn("This world is now on v0.3.3.", third.lines)

    def test_an_update_the_world_does_not_get_ready_with_is_taken_back(self):
        self.installed(server=self.NEW_SERVER)
        self.assertEqual(self.world().run(), keep.RESTART_CODE)

        def failing():
            world = self.world()
            world.map_says = "still loading\n"
            spawn = world.spawn

            def dying(name):
                proc, log = spawn(name)
                if name == "xi_map":
                    proc.code = 139
                return proc, log
            world.spawn = dying
            return world
        self.assertEqual(failing().run(), 1)                                       # the update is in; the map server dies
        self.assertEqual((self.versions()[1], keep.load_state(self.kit_host)["tries"]), ("v0.3.3", 1))
        self.assertEqual(failing().run(), 1)                                       # the second start too
        self.assertEqual(keep.load_state(self.kit_host)["tries"], 2)
        third = self.world()
        third.start()                                                              # the third start takes it back and runs as before
        self.assertEqual((third.state, self.versions()), ("running", ("v0.3.2", "v0.3.2")))
        with open(os.path.join(self.server, "sql", "zones.sql")) as handle:
            self.assertEqual(handle.read(), "old zones\n")
        self.assertTrue(any("DROP DATABASE" in s for s in third.maria.statements()), "the database from before the update is put back")
        self.assertLess(third.steps.index("database"), third.steps.index("start xi_connect"))
        self.assertIsNone(keep.load_state(self.kit_host))
        status = wd.read_status(self.kit_host)
        self.assertIn("was taken back", status["update"]["problem"])
        self.assertIn("Update problem: The update to v0.3.3 was taken back", wd.describe(status))
        asked = len(self.net.asked)
        for _ in range(3):
            third.pass_time(3600)
            third.tick()                                                           # it looks again, and leaves that release alone
        self.assertGreater(len(self.net.asked), asked)
        self.assertEqual((third.state, self.versions(), keep.load_state(self.kit_host)), ("running", ("v0.3.2", "v0.3.2"), None))
        # the owner says to try it again
        keep.request(self.kit_host, "update", retry=True)
        third.tick()
        with self.assertRaises(keep.Restart):
            third.tick()

    def test_a_world_that_gets_ready_late_still_counts(self):
        self.installed(server=self.NEW_SERVER)
        self.assertEqual(self.world().run(), keep.RESTART_CODE)
        world = self.world()
        world.map_says = "still loading\n"                                         # (the start gives up waiting; the servers live)
        world.start()
        self.assertEqual((world.state, keep.load_state(self.kit_host)["state"]), ("running", "trying"))
        world.tick()
        self.assertEqual(keep.load_state(self.kit_host)["state"], "trying")
        with open(os.path.join(self.kit_host, "logs", "xi_map.log"), "ab") as handle:
            handle.write(b"the map server is ready to work\n")
        world.tick()
        self.assertIsNone(keep.load_state(self.kit_host))
        self.assertIn("This world is now on v0.3.3.", world.lines)

    def test_an_update_that_could_not_be_taken_back_keeps_the_servers_off(self):
        self.installed()
        keep.save_state(self.kit_host, {"state": "applying", "stuck": "the database (it failed)", "server": {"tag_name": "v0.3.3", "assets": []}})
        world = self.world()
        self.assertEqual(world.run(), keep.STUCK_CODE)
        self.assertEqual([step for step in world.steps if step.startswith("start ")], [])
        self.assertEqual(world.steps[-1], "database stopped")
        status = wd.read_status(self.kit_host)
        self.assertEqual(status["state"], "stopped")
        self.assertIn("could not be taken back completely", status["problem"])
        self.assertEqual(keep.load_state(self.kit_host)["stuck"], "the database (it failed)", "nothing is tried again by itself")

    def test_an_update_that_was_cut_off_in_the_middle_is_taken_back_at_the_next_start(self):
        self.installed(server=self.NEW_SERVER)
        self.assertEqual(self.world().run(), keep.RESTART_CODE)
        state = keep.load_state(self.kit_host)
        maria = tk.FakeMaria()
        calls = []

        def power_cut(cmd, **kw):                                                  # the machine goes down while the tables are imported
            calls.append(cmd)
            if "SOURCE" in str(cmd[-1]):
                raise KeyboardInterrupt()
            return maria.run(cmd, **kw)
        with self.assertRaises(KeyboardInterrupt):
            keep.apply(self.kit_host, self.cfg_host, state, run=power_cut, check=lambda kit: None)
        self.assertEqual((keep.load_state(self.kit_host)["state"], self.versions()[1]), ("applying", "v0.3.3"))
        world = self.world()
        world.start()
        self.assertEqual((world.state, self.versions(), keep.load_state(self.kit_host)), ("running", ("v0.3.2", "v0.3.2"), None))
        self.assertTrue(any("it was stopped in the middle" in line for line in world.lines))
        self.assertTrue(any("DROP DATABASE" in s for s in world.maria.statements()))

    # --- the owner's commands ---
    def command(self, *argv):
        said = []
        with open(os.path.join(self.kit_host, "config.json"), "w") as handle:
            json.dump(self.cfg_host, handle)
        return wd.by_hand(["launcher_world.py"] + list(argv), kit=self.kit_host, say=said.append), said

    def test_commands_given_by_hand(self):
        self.assertEqual(self.command("backups"), (0, ["No copies yet (backups/world)."]))
        code, said = self.command("selftest")
        self.assertEqual((code, said), (0, ["world selftest ok"]))
        world = self.world()
        world.start()
        self.assertTrue(wd.world_running(self.kit_host))
        copy = keep.backup_now(self.cfg_host, self.kit_host, "by-hand", run=world.maria.run, log=lambda m: None)
        code, said = self.command("backups")
        self.assertEqual(code, 0)
        self.assertTrue(said[0].endswith(copy))
        code, said = self.command("restore", os.path.basename(copy))               # never under a running world
        self.assertEqual(code, 1)
        self.assertIn("Stop it first", said[0])
        self.assertEqual(self.command("restore")[0], 2)
        code, said = self.command("update", "--retry")                             # a running world is asked to look
        self.assertEqual(code, 0)
        asked = keep.take_request(self.kit_host)
        self.assertEqual((asked["do"], asked["retry"]), ("update", True))
        self.assertEqual(self.command("fly")[0], 2)
        world.stop(grace=0)
        self.assertFalse(wd.world_running(self.kit_host))

    def test_updates_can_be_left_to_the_owner(self):
        self.installed(server=self.NEW_SERVER)
        keep.save_settings(self.kit_host, dict(keep.DEFAULTS, auto_update=False))
        world = self.world()
        world.start()
        for _ in range(3):
            world.pass_time(3600)
            world.tick()
        self.assertEqual(self.net.asked, [])
        world.write_status()
        self.assertIn("not installed by itself", wd.describe(wd.read_status(self.kit_host)))
        keep.request(self.kit_host, "update")
        world.tick()
        self.assertIn("Looking for an update now, as asked.", world.lines)
        with self.assertRaises(keep.Restart):
            world.tick()

    def test_a_release_whose_files_are_not_up_yet_is_waited_for(self):
        self.installed()
        tk.publish(self.net, self.kit_host, lu.SERVER_REPO, "v0.3.3")              # released; the Linux build is still running
        world = self.world()
        world.start()
        world.tick()
        world.tick()
        self.assertEqual((world.state, keep.load_state(self.kit_host)), ("running", None))
        world.write_status()
        status = wd.read_status(self.kit_host)
        self.assertEqual(status["update"]["waiting"], ["server v0.3.3"])
        self.assertIn("server v0.3.3 is out; its files for this system are not up yet.", wd.describe(status))

    def test_a_world_waits_until_both_halves_of_a_release_are_up(self):
        self.installed(kit=self.NEW_KIT)                                           # the launcher's Linux files are up...
        tk.publish(self.net, self.kit_host, lu.SERVER_REPO, "v0.3.3")              # ...the server's are still being built
        world = self.world()
        world.start()
        for _ in range(3):
            world.pass_time(3600)
            world.tick()
        self.assertEqual((world.state, keep.load_state(self.kit_host), world.keeper.plan, self.versions()), ("running", None, None, ("v0.3.2", "v0.3.2")))
        self.assertEqual(world.keeper.waiting, ["server v0.3.3"])
        self.assertFalse(os.path.isdir(os.path.join(self.kit_host, "downloads", "updates")), "nothing is downloaded while one half is missing")
        page = tk.tp.API + lu.SERVER_REPO + "/releases?per_page=30"
        self.net.pages[page] = b"[]"
        tk.publish(self.net, self.kit_host, lu.SERVER_REPO, "v0.3.3", self.NEW_SERVER)      # the build has finished
        world.pass_time(3600)
        world.tick()
        with self.assertRaises(keep.Restart):
            world.tick()
        state = keep.load_state(self.kit_host)
        self.assertEqual((state["kit"]["tag_name"], state["server"]["tag_name"]), ("v0.3.3", "v0.3.3"), "one restart for both")

    def test_no_internet_is_no_reason_to_stop(self):
        self.installed()
        self.net.pages.clear()
        world = self.world()
        world.start()
        world.tick()
        self.assertEqual(world.state, "running")
        self.assertTrue(any(line.startswith("Could not look for an update") for line in world.lines))


class Visitors(WorldCase):
    """What the owner and the moderators do about visitors by hand, on a world with no launcher window:
    who, kick, ban, bans, unban, places, forget (2026-11-23)."""

    def setUp(self):
        super().setUp()
        self.wait, self.hello = wd.ANSWER_WAIT_SECONDS, wd.HELLO_WAIT_SECONDS

    def tearDown(self):
        wd.ANSWER_WAIT_SECONDS, wd.HELLO_WAIT_SECONDS = self.wait, self.hello
        super().tearDown()

    def command(self, *argv, world=None):
        """One command by hand. world: the running world, which takes a look whenever the command waits."""
        said = []
        with open(os.path.join(self.kit_host, "config.json"), "w") as handle:
            json.dump(self.cfg_host, handle)
        looks = (lambda _seconds: world.tick()) if world is not None else (lambda _seconds: None)
        return wd.by_hand(["launcher_world.py"] + list(argv), kit=self.kit_host, say=said.append, sleep=looks), said

    def online(self, guest):
        ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()

    def folders(self):
        return [sorted(os.listdir(os.path.join(self.kit_host, "logs", name))) for name in (wd.ASKED_DIR, wd.ANSWERS_DIR)]

    def test_a_visitor_is_seen_kicked_and_banned_by_hand(self):
        world = self.world()
        world.start()
        visit = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        code, said = self.command("who", world=world)
        self.assertEqual(code, 0)
        self.assertEqual(said[0], "Visitors here: 1, of them in the game: 0 (at most 3).")
        self.assertTrue(said[1].startswith(f"  #{guest['charid']}  Visitor  not in the game"), said[1])
        self.assertEqual(said[-2:], ["Kept places: 0 ('places' lists them). Bans: 0 ('bans' lists them).",
                                     "The running world answers: kick and ban get through."])
        self.assertFalse(any("hello" in line for line in world.lines), "a look by hand is not written down as something done")
        code, said = self.command("kick", "visitor", world=world)                    # not in the game: there is nothing to log out
        self.assertEqual((code, self.lua_lines("KICK")), (1, []))
        self.assertIn("is not in the game right now", said[0])
        self.online(guest)
        self.assertIn("  in the game  ", self.command("who", world=world)[1][1])
        code, said = self.command("kick", f"#{guest['charid']}", world=world)        # by the number 'who' shows
        self.assertEqual((code, self.lua_lines("KICK")), (0, [str(guest["charid"])]))
        self.assertIn("Visitor is being logged out of the game", said[0])
        self.assertEqual(world.host.out, {}, "a kick is one request: the visitor may log in again")
        code, said = self.command("kick", "Nobody", world=world)
        self.assertEqual((code, said), (1, ["Nobody called 'Nobody' is here. 'who' lists the visitors."]))
        code, said = self.command("ban", "Visitor", "--address", "kept", "training", "mobs", world=world)
        self.assertEqual(code, 0)
        self.assertTrue(said[0].startswith("Visitor is banned from this world"), said)
        self.assertEqual(said[1], "The address it last used is banned too.")
        self.assertEqual(sorted((b["kind"], b["value"], b["reason"]) for b in pp.ban_list(self.host_db)),
                         [("ip", "127.0.0.1", "Visitor: kept training mobs"), ("key", guest["owner"], "Visitor: kept training mobs")])
        self.assertEqual(len(self.lua_lines("KICK")), 2, "it is put out of the game at once")
        self.assertIn(visit["guest_id"], world.host.out, "and the running world asks it out again until it has left")
        self.assertEqual(self.q(self.host_db, "SELECT status FROM accounts WHERE id = ?", (guest["accid"],)), [(0,)])
        self.assertTrue(any(line.startswith("By hand (ban): Visitor is banned") for line in world.lines), "what was done by hand is in the world's log")
        self.assertEqual(self.folders(), [[], []], "nothing is left lying around")
        code, said = self.command("bans", world=world)
        self.assertEqual((code, len(said)), (0, 3))
        self.assertTrue(said[0].startswith("Bans: 2. To lift one: launcher_world.py unban"), said[0])
        self.assertTrue(any(line.startswith("  address 127.0.0.1  Visitor: kept training mobs  since ") for line in said[1:]), said)
        self.assertTrue(any(line.startswith(f"  launcher {guest['owner'][:12]}...  Visitor: kept training mobs") for line in said[1:]), said)
        code, said = self.command("unban", "visitor", world=world)                   # by the name: its launcher and its address
        self.assertEqual((code, pp.ban_list(self.host_db)), (0, []))
        self.assertIn("the address 127.0.0.1", said[0])
        self.assertEqual(self.command("unban", "visitor", world=world), (1, ["No ban matches 'visitor'. 'bans' lists them."]))

    def test_a_ban_without_the_address_and_a_ban_lifted_by_its_address(self):
        world = self.world()
        world.start()
        self.visit()
        guest = pp.guest_list(self.host_db)[0]
        code, said = self.command("ban", str(guest["charid"]), world=world)
        self.assertEqual((code, len(said)), (0, 1))
        self.assertEqual([(b["kind"], b["reason"]) for b in pp.ban_list(self.host_db)], [("key", "Visitor")])
        self.assertEqual(self.lua_lines("KICK"), [str(guest["charid"])])
        world.host.addresses.clear()                                                # (nothing is known of where it came from)
        ct.run(self.host_db, "UPDATE coop_visitor SET address = ''")
        self.host_db.commit()
        code, said = self.command("ban", "Visitor", "--address", world=world)
        self.assertEqual((code, said[1]), (0, "No address is known for it, so only its launcher is banned."))
        pp.ban(self.host_db, "ip", "203.0.113.9", "someone else")
        self.assertEqual(self.command("unban", "203.0.113.9", world=world)[0], 0)
        self.assertEqual([b["kind"] for b in pp.ban_list(self.host_db)], ["key"])
        self.assertEqual(self.command("unban", guest["owner"][:5], world=world)[0], 1, "five letters of a key are too few to mean one")
        self.assertEqual(self.command("unban", guest["owner"][:8], world=world)[0], 0)
        self.assertEqual(pp.ban_list(self.host_db), [])

    def test_kept_places_are_listed_banned_and_given_up_also_while_the_world_is_stopped(self):
        world = self.world()
        world.start()
        self.visit()
        guest = pp.guest_list(self.host_db)[0]
        co.come_home(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home)
        code, said = self.command("places", world=world)
        self.assertEqual((code, said[0]), (0, f"Kept places: 1 (a place is cleared {pp.LOCKER_DAYS} days after the last visit)."))
        self.assertTrue(said[1].startswith(f"  #{guest['charid']}  Visitor  last here "), said[1])
        self.assertIn("  kept until 2", said[1])
        self.assertEqual(self.command("who", world=world), (0, ["Visitors here: 0, of them in the game: 0 (at most 3).",
                                                                 "Kept places: 1 ('places' lists them). Bans: 0 ('bans' lists them).",
                                                                 "The running world answers: kick and ban get through."]))
        self.assertEqual(self.command("kick", "Visitor", world=world)[0], 1, "a visitor who is home is not here to be kicked")
        for wrong in (("forget", "Visitor", "--now"), ("forget",), ("kick",), ("ban",), ("unban",), ("who", "Visitor"), ("bans", "x"),
                      ("places", "x"), ("kick", "a", "b"), ("kick", "Visitor", "--address")):
            code, said = self.command(*wrong, world=world)
            self.assertEqual((code, said[0].split()[0:2]), (2, ["launcher_world.py", wrong[0]]), wrong)
        world.stop(grace=0)
        self.assertEqual(self.command("kick", "Visitor"), (1, ["The world is not running: nobody is in the game."]))
        code, said = self.command("who")
        self.assertEqual((code, len(said)), (0, 2), "a stopped world is not asked whether it answers")
        self.assertTrue(said[0].endswith(" The world is not running."))
        code, said = self.command("ban", "Visitor", "--address")                    # the kept place of a visitor who is home
        self.assertEqual(code, 0)
        self.assertEqual(sorted((b["kind"], b["reason"]) for b in pp.ban_list(self.host_db)), [("ip", "Visitor"), ("key", "Visitor")])
        self.assertEqual(self.lua_lines("KICK"), [], "nobody is in the game")
        self.assertEqual(self.command("unban", "Visitor")[0], 0)
        self.assertEqual(pp.ban_list(self.host_db), [])
        self.assertEqual(self.command("forget", "Nobody")[0], 1)
        code, said = self.command("forget", str(guest["charid"]))
        self.assertEqual(code, 0)
        self.assertIn("kept place is given up", said[0])
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("gone",)])
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM chars WHERE charid = ?", (guest["charid"],)), [(0,)])
        self.assertEqual(self.command("forget", "Visitor")[0], 1)
        self.assertEqual(self.command("places")[1], [f"Kept places: 0 (a place is cleared {pp.LOCKER_DAYS} days after the last visit)."])

    def test_a_visitor_who_is_here_is_not_forgotten(self):
        world = self.world()
        world.start()
        visit = self.visit()
        self.assertEqual(self.command("forget", "Visitor", world=world), (1, ["No kept place is called 'Visitor'. 'places' lists them."]))
        self.assertEqual(wd.moderate(world.host, {"do": "forget", "guest": visit["guest_id"]})[0], 1)
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("active",)])
        self.assertEqual(wd.moderate(world.host, {"do": "kick", "guest": "no-such-visitor"}), (1, ["That visitor is not here any more. Nothing was done."]))
        self.assertEqual(wd.moderate(world.host, {"do": "ban", "guest": "no-such-visitor", "reason": "x"})[0], 1)
        self.assertEqual(wd.moderate(world.host, {"do": "unban", "bans": []})[0], 1)
        self.assertEqual(wd.moderate(world.host, {"do": "fly"})[0], 2)
        self.assertEqual(pp.ban_list(self.host_db), [])

    def test_what_nobody_waits_for_is_not_done(self):
        world = self.world()
        world.start()
        visit = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.online(guest)
        asked = os.path.join(self.kit_host, "logs", wd.ASKED_DIR)
        kick = {"do": "kick", "guest": visit["guest_id"]}
        keep._write_json(os.path.join(asked, "old.json"), dict(kick, at=time.time() - wd.ANSWER_WAIT_SECONDS - 1))
        keep._write_json(os.path.join(asked, "later.json"), dict(kick, at=time.time() + 600))
        keep._write_json(os.path.join(asked, "undated.json"), kick)
        with open(os.path.join(asked, "torn.json"), "w") as handle:
            handle.write("{")
        world.tick()
        self.assertEqual((self.lua_lines("KICK"), self.folders()), ([], [[], []]))
        wd.ANSWER_WAIT_SECONDS = 0.3
        code, said = self.command("kick", "Visitor")                                # (this world takes no look while the command waits)
        self.assertEqual(code, 1)
        self.assertIn("did not answer", said[0])
        self.assertEqual(self.folders(), [[], []], "the command takes back what was not taken")
        wd.HELLO_WAIT_SECONDS = 0.3
        code, said = self.command("who")                                             # 'who' says so too, and still lists
        self.assertEqual((code, len(said)), (1, 4))
        self.assertTrue(said[-1].startswith("The running world did not answer: kick and ban would not get through right now."))
        self.assertEqual(self.folders(), [[], []])
        world.tick()
        self.assertEqual(self.lua_lines("KICK"), [])
        keep._write_json(os.path.join(asked, "left.json"), dict(kick, at=time.time()))      # asked just before the world went down
        world.stop(grace=0)
        again = self.world()
        again.start()
        self.assertEqual(self.folders(), [[], []], "a new start does nothing that was asked of the run before")
        again.tick()
        self.assertEqual(self.lua_lines("KICK"), [])
        code, said = self.command("kick", "Visitor", world=again)                   # and this run answers again
        self.assertEqual((code, self.lua_lines("KICK")), (0, [str(guest["charid"])]))

    def test_a_request_that_fails_is_answered_and_the_world_goes_on(self):
        world = self.world()
        world.start()
        visit = self.visit()

        def broken(*_a, **_k):
            raise RuntimeError("the database went away")

        world.host.ban = broken
        code, said = self.command("ban", "Visitor", world=world)
        self.assertEqual(code, 1)
        self.assertIn("That did not work (RuntimeError: the database went away)", said[0])
        world.tick()
        self.assertEqual(world.state, "running")
        self.assertEqual(self.folders(), [[], []])
        self.assertTrue(visit["guest_id"])

    def test_a_world_started_before_the_commands_existed_says_so(self):
        os.makedirs(os.path.join(self.kit_host, "logs"), exist_ok=True)
        code, said = wd.ask_world(self.kit_host, {"do": "kick", "guest": "x"}, wait=0.1, sleep=lambda _s: None)
        self.assertEqual(code, 1)
        self.assertIn("Restart the world", said[0])
        self.assertFalse(os.path.exists(os.path.join(self.kit_host, "logs", wd.ASKED_DIR)))

    def test_names_numbers_and_two_of_the_same_name(self):
        rows = [{"charid": 21, "name": "Kupo", "local": "Kupo", "state": "locker", "guest_id": "a", "owner": "k1"},
                {"charid": 22, "name": "Kupo", "local": "Mog", "state": "locker", "guest_id": "b", "owner": "k2"},
                {"charid": 23, "name": "Stilt", "local": "Stilt", "state": "locker", "guest_id": "c", "owner": "k3"}]
        find = lambda text: [row["charid"] for row in wd.find_visitor(rows, text)]
        self.assertEqual((find("kupo"), find("MOG"), find("#23"), find(" 22 "), find("nobody"), find("2")), ([21, 22], [22], [23], [22], [], []))
        self.assertEqual((wd.shown(rows[0]), wd.shown(rows[1])), ("Kupo", "Mog (Kupo at home)"))
        real = pp.guest_list
        pp.guest_list = lambda conn, **_more: [dict(row) for row in rows]
        try:
            code, said = self.command("ban", "Kupo")
        finally:
            pp.guest_list = real
        self.assertEqual((code, said), (1, ["More than one is called 'Kupo'. Say the number instead:", "  #21  Kupo", "  #22  Mog (Kupo at home)"]))
        self.assertEqual(pp.ban_list(self.host_db), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
