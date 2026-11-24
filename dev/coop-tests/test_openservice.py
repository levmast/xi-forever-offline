"""Tests for open worlds in launcher_coop.py (2026-11-22): the world link, a launcher's own keys, the TLS side of the
co-op port and a whole visit over it, passwords, visiting names, bans and the checked way home.
Two scratch databases (see cooptest.py) and a real listener on this machine. Needs the openssl program to make a
certificate for the pretend game server. Run: python test_openservice.py"""
import datetime, os, shutil, socket, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_coop as co
import launcher_passport as pp

ACC, CHAR = 1000, 21828
ITEMS = (65535, 16535, 4112, 12345, 513, 514, 515)
CERTS = None


def setUpModule():
    global CERTS
    try:
        ct.drop_worlds()
    except Exception as e:
        raise unittest.SkipTest(f"no database to test on ({e})")
    CERTS = tempfile.mkdtemp()
    for name in ("one", "two"):                              # two game servers, each with a key of its own
        folder = os.path.join(CERTS, name)
        os.makedirs(folder)
        try:
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "30", "-subj", "/CN=xi",
                            "-keyout", os.path.join(folder, "login.key"), "-out", os.path.join(folder, "login.cert")],
                           check=True, capture_output=True, timeout=120)
        except Exception as e:
            raise unittest.SkipTest(f"no openssl to make a test certificate ({e})")


def tearDownModule():
    ct.drop_worlds()
    shutil.rmtree(CERTS, ignore_errors=True)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Plain(unittest.TestCase):
    def test_world_links(self):
        link = co.make_link("203.0.113.9", 54100, "SHA256:" + "A" * 43, "The Hub")
        self.assertTrue(link.startswith("XIFO2-"))
        self.assertEqual(co.read_code(link), {"address": "203.0.113.9", "port": 54100, "pin": "SHA256:" + "A" * 43, "world": "The Hub", "open": True})
        self.assertNotIn("secret", co.read_code(link))
        invite = co.make_invite("10.0.0.2", 54100, "ab" * 16, "Home")
        self.assertEqual(co.read_code(invite)["secret"], "ab" * 16)
        for bad in ("XIFO2-", "XIFO2-abc", link[:-6], co.make_link("bad address!", 54100, "SHA256:" + "A" * 43, "x"),
                    co.make_link("10.0.0.2", 54100, "MD5:abc", "x"), co.make_link("10.0.0.2", 0, "SHA256:" + "A" * 43, "x")):
            with self.assertRaises(co.CoopError):
                co.read_link(bad)

    def test_a_launcher_has_a_different_key_for_every_world(self):
        kit = tempfile.mkdtemp()
        try:
            mine = co.identity(kit)
            self.assertRegex(mine, r"^[0-9a-f]{64}$")
            self.assertEqual(co.identity(kit), mine)                              # made once
            a, b = co.world_keys(mine, "SHA256:worldA"), co.world_keys(mine, "SHA256:worldB")
            self.assertEqual(a, co.world_keys(mine, "SHA256:worldA"))
            self.assertNotEqual(a[0], b[0])
            self.assertNotEqual(a[1], b[1])
            self.assertRegex(a[0], r"^[0-9a-f]{32}$")
            self.assertRegex(a[1], r"^[0-9a-f]{64}$")
            self.assertNotIn(mine, a)
            other = tempfile.mkdtemp()
            self.assertNotEqual(co.world_keys(co.identity(other), "SHA256:worldA"), a)   # another launcher, another visitor
            shutil.rmtree(other)
            with open(os.path.join(kit, "coop", "identity"), "w") as handle:      # a damaged file is kept aside, never lost silently
                handle.write("not a key")
            fresh = co.identity(kit)
            self.assertNotEqual(fresh, mine)
            self.assertEqual(len([n for n in os.listdir(os.path.join(kit, "coop")) if n.startswith("identity.damaged-")]), 1)
            with self.assertRaises(co.CoopError):
                co.world_keys("short", "SHA256:worldA")
        finally:
            shutil.rmtree(kit)

    def test_world_passwords(self):
        kept = co.hash_password("mog house")
        self.assertNotIn("mog", kept)
        self.assertNotEqual(kept, co.hash_password("mog house"))
        self.assertTrue(co.check_password(kept, "mog house"))
        for wrong in ("mog", "", None, "Mog house"):
            self.assertFalse(co.check_password(kept, wrong))
        self.assertTrue(co.check_password("", "anything"))                        # no password set
        self.assertFalse(co.check_password("zz$zz", "x"))

    def test_settings_of_an_open_world(self):
        kit = tempfile.mkdtemp()
        try:
            settings = co.load_settings(kit)
            self.assertEqual((settings["open"], settings["password"]), (False, ""))
            settings.update({"open": True, "max_guests": 40, "password": co.hash_password("x")})
            co.save_settings(kit, settings)
            self.assertEqual(co.load_settings(kit)["max_guests"], 40)
            settings.update({"open": False})
            co.save_settings(kit, settings)
            self.assertEqual(co.load_settings(kit)["max_guests"], co.MAX_GUESTS)   # between friends the old limit stands
            settings.update({"open": "yes", "max_guests": 500, "password": "plain text"})
            co.save_settings(kit, settings)
            again = co.load_settings(kit)
            self.assertEqual((again["open"], again["max_guests"], again["password"]), (False, co.MAX_GUESTS, ""))
        finally:
            shutil.rmtree(kit)


class OpenWorld(unittest.TestCase):
    def setUp(self):
        self.home = ct.make_world(ct.HOME_DB)
        self.host_db = ct.make_world(ct.HOST_DB)
        ct.make_account(self.home, ACC, "homeplayer")
        ct.make_character(self.home, ACC, CHAR, "Visitor")
        ct.make_account(self.host_db, ACC, "hostplayer")
        ct.make_character(self.host_db, ACC, CHAR, "Hostess", linkshell=False)
        template = ct.settings()[1]
        for world in (self.home, self.host_db):
            ct.run(world, f"CREATE TABLE item_basic LIKE `{template}`.item_basic")
            ct.run(world, f"INSERT INTO item_basic SELECT * FROM `{template}`.item_basic WHERE itemid IN ({', '.join('?' for _ in ITEMS)})", ITEMS)
            ct.run(world, f"INSERT INTO zone_settings SELECT * FROM `{template}`.zone_settings")
            world.commit()
        self.tmp = tempfile.mkdtemp()
        self.kit_home, self.kit_host, self.server = (os.path.join(self.tmp, n) for n in ("home", "host", "server"))
        for folder in (self.kit_home, self.kit_host, os.path.join(self.server, "modules", "custom", "lua")):
            os.makedirs(folder)
        for name in ("login.cert", "login.key"):
            shutil.copy(os.path.join(CERTS, "one", name), self.server)
        self.settings = co.load_settings(self.kit_host)
        self.settings.update({"enabled": True, "hosting": True, "open": True, "mode": "direct", "address": "127.0.0.1",
                              "port": free_port(), "max_guests": 3})
        self.logs = []
        self.connect_host = lambda: ct.connect(ct.HOST_DB)
        self.connect_home = lambda: ct.connect(ct.HOME_DB)
        self.host = co.Host({"server_dir": self.server}, self.kit_host, self.settings, log=self.logs.append, connect=self.connect_host)
        self.host.start()
        self.cfg = {"server_dir": None}
        self.link = co.read_code(self.host.link())

    def tearDown(self):
        self.host.stop()
        for conn in (self.home, self.host_db):
            conn.rollback()
            conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def q(self, conn, sql, params=()):
        rows = ct.run(conn, sql, params)
        conn.rollback()
        return rows

    def visit(self, **more):
        return co.start_visit(self.cfg, self.kit_home, self.link, CHAR, log=self.logs.append, connect=self.connect_home, **more)

    def go_home(self, **more):
        return co.come_home(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home, **more)

    def away(self):
        return co.away(self.cfg, self.connect_home)

    # --- a whole visit over the real port ---
    def test_a_visit_and_a_second_one(self):
        self.assertEqual(self.link["pin"], co.server_fingerprint(self.server))
        host = self.visit()
        self.assertTrue(host["arrived"] and host["open"] and not host["shelf"])
        self.assertEqual(host["local"], "Visitor")
        self.assertNotIn("password", host)
        vid, vkey = co.world_keys(co.identity(self.kit_home), self.link["pin"])
        self.assertNotIn(co.identity(self.kit_home), str(self.away()))            # the launcher's secret is never stored with a visit
        guest = pp.guest_list(self.host_db)[0]
        self.assertEqual((guest["owner"], guest["kept"], guest["state"], guest["gkey"]), (vid, True, "active", co.guest_key(vkey, host["guest_id"])))
        self.assertEqual(self.q(self.host_db, "SELECT vid, vkey FROM coop_visitor"), [(vid, vkey)])
        self.assertIn("Visitor is visiting this world.", open(os.path.join(self.server, "modules", "custom", "lua", "coop_in.txt")).read())
        self.assertEqual(co.keep_visit(self.cfg, self.kit_home, self.away()[0], connect=self.connect_home), "checkpoint")
        self.assertTrue(os.path.exists(co.checkpoint_file(self.kit_home, CHAR)))
        # things left in the auction house do not hold a visitor of an open world back: its place is kept
        ct.run(self.host_db, "INSERT INTO auction_house (itemid, stack, seller, seller_name, date, price) VALUES (4112, 0, ?, 'Visitor', 1, 500)", (guest["charid"],))
        self.host_db.commit()
        result = self.go_home()
        self.assertEqual((result["name"], result["already"]), ("Visitor", False))
        self.assertEqual(self.away(), [])
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("locker",)])
        self.assertEqual([k["local"] for k in self.host.lockers()], ["Visitor"])
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM auction_house")[0][0], 1)
        again = self.visit()
        self.assertTrue(again["shelf"])
        self.assertEqual(again["host_charid"], guest["charid"])
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM coop_visitor")[0][0], 1)
        self.go_home()

    def test_friends_with_an_invite_code_still_get_in_on_the_same_port(self):
        invite = co.read_code(co.make_invite("127.0.0.1", self.settings["port"], self.settings["secret"], "Host world"))
        self.assertTrue(co.hello(invite)["open"])
        host = co.start_visit(self.cfg, self.kit_home, invite, CHAR, log=self.logs.append, connect=self.connect_home)
        self.assertTrue(host["arrived"])
        self.assertEqual(self.q(self.host_db, "SELECT owner, kept FROM coop_guest"), [("", 0)])
        self.go_home()
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("gone",)])

    def test_a_world_with_another_key_is_told_nothing(self):
        with open(os.path.join(CERTS, "two", "login.cert")) as handle:
            other = co.certificate_fingerprint(handle.read())
        self.assertNotEqual(other, self.link["pin"])
        self.link = dict(self.link, pin=other)
        with self.assertRaises(co.Refused) as refused:
            self.visit()
        self.assertEqual(refused.exception.code, "pin")
        self.assertEqual(self.away(), [])
        pp.ensure_tables(self.host_db)
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM coop_visitor")[0][0], 0)

    def test_open_requests_only_over_tls_and_only_to_an_open_world(self):
        hello = co.seal(co.OPEN_KEY, {"op": "hello"})
        self.assertTrue(co.unseal(co.OPEN_KEY, self.host.handle("open", hello, "1.2.3.4", secure=True))[0]["open_world"])
        with self.assertRaises(co.CoopError):
            self.host.handle("open", hello, "1.2.3.4", secure=False)
        with self.assertRaises(co.Refused) as refused:                             # the same request on the plain side of the port
            co.call(dict(self.link, pin=None), "open", co.OPEN_KEY, {"op": "hello"})
        self.assertEqual(refused.exception.code, "key")
        self.settings["open"] = False
        with self.assertRaises(co.CoopError):
            self.host.handle("open", hello, "1.2.3.4", secure=True)
        with self.assertRaises(co.CoopError):
            self.host.handle("visitor:" + "a" * 32, hello, "1.2.3.4", secure=True)
        with self.assertRaises(co.CoopError):                                      # more than an open world reads from a stranger
            self.settings["open"] = True
            self.host.handle("open", co.seal(co.OPEN_KEY, {"op": "hello"}, b"x" * (co.OPEN_MAX_BODY + 1)), "1.2.3.4", secure=True)

    def test_a_visitor_id_belongs_to_the_first_key_that_showed_it(self):
        def register(vid, vkey, client="9.9.9.9"):
            return co.unseal(co.OPEN_KEY, self.host.handle("open", co.seal(co.OPEN_KEY, {"op": "register", "vid": vid, "vkey": vkey}), client, secure=True))[0]

        self.assertEqual(register("a" * 32, "1" * 64), {"ok": True, "known": False})
        self.assertEqual(register("a" * 32, "1" * 64), {"ok": True, "known": True})
        self.assertFalse(register("a" * 32, "2" * 64)["ok"])
        self.assertEqual(self.q(self.host_db, "SELECT vkey FROM coop_visitor WHERE vid = ?", ("a" * 32,)), [("1" * 64,)])
        with self.assertRaises(co.CoopError):                                      # nobody can speak as that visitor without its key
            self.host.handle("visitor:" + "a" * 32, co.seal(bytes.fromhex("2" * 64), {"op": "arrive"}), "9.9.9.9", secure=True)
        for bad in ({"vid": "short", "vkey": "1" * 64}, {"vid": "b" * 32, "vkey": "xyz"}, {}):
            self.assertFalse(register(bad.get("vid", ""), bad.get("vkey", ""))["ok"])
        limit, co.REGISTER_PER_HOUR = co.REGISTER_PER_HOUR, 2                      # one address cannot fill the list with made-up visitors
        try:
            self.assertTrue(register("c" * 32, "3" * 64, "7.7.7.7")["ok"])
            self.assertTrue(register("d" * 32, "4" * 64, "7.7.7.7")["ok"])
            self.assertEqual(register("e" * 32, "5" * 64, "7.7.7.7")["code"], "busy")
            self.assertTrue(register("c" * 32, "3" * 64, "7.7.7.7")["ok"])
            self.assertTrue(register("e" * 32, "5" * 64, "8.8.8.8")["ok"])
        finally:
            co.REGISTER_PER_HOUR = limit

    # --- passwords and names ---
    def test_a_world_with_a_password(self):
        self.settings["password"] = co.hash_password("kupo")
        with self.assertRaises(co.Refused) as refused:
            self.visit()
        self.assertEqual(refused.exception.code, "password")
        self.assertEqual(self.away(), [])                                          # asked for before anything is packed
        with self.assertRaises(co.Refused) as refused:
            self.visit(password="kupopo")
        self.assertEqual(refused.exception.code, "password")
        self.assertEqual([a["host"]["arrived"] for a in self.away()], [False])     # packed, and it can try again
        host = co.finish_arrival(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home, password="kupo")
        self.assertTrue(host["arrived"])
        self.assertNotIn("kupo", str(self.away()))
        self.go_home()

    def test_a_taken_name_and_a_visiting_name(self):
        ct.make_character(self.host_db, ACC, 30000, "Visitor", linkshell=False)
        with self.assertRaises(co.Refused) as refused:
            self.visit()
        self.assertEqual(refused.exception.code, "name")
        self.assertEqual([a["host"]["arrived"] for a in self.away()], [False])
        with self.assertRaises(co.Refused) as refused:
            co.finish_arrival(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home, alias="Hostess")
        self.assertEqual(refused.exception.code, "name")
        host = co.finish_arrival(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home, alias="Visitorb")
        self.assertEqual((host["arrived"], host["local"]), (True, "Visitorb"))
        self.assertEqual(self.go_home()["name"], "Visitor")
        self.assertEqual(self.q(self.home, "SELECT charname FROM chars WHERE charid = ?", (CHAR,)), [("Visitor",)])
        self.assertEqual(self.visit()["local"], "Visitorb")                        # its visiting name is kept with its place
        self.go_home()

    def test_a_visit_that_is_refused_can_be_called_off(self):
        ct.make_character(self.host_db, ACC, 30000, "Visitor", linkshell=False)
        with self.assertRaises(co.Refused):
            self.visit()
        co.cancel_visit(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home)
        self.assertEqual(self.away(), [])
        self.assertEqual(self.q(self.home, "SELECT accid FROM chars WHERE charid = ?", (CHAR,)), [(ACC,)])

    def test_a_character_the_host_cannot_load_is_turned_away(self):
        ct.run(self.home, "UPDATE chars SET pos_zone = 9999 WHERE charid = ?", (CHAR,))
        self.home.commit()
        with self.assertRaises(co.Refused) as refused:
            self.visit()
        self.assertEqual(refused.exception.code, "bad")
        self.assertEqual(self.away(), [])                                          # a clear no: unpacked at once
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM coop_guest")[0][0], 0)
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM chars")[0][0], 1)

    # --- the host's tools ---
    def test_a_ban_puts_a_visitor_out_and_lets_its_character_go_home(self):
        host = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.assertEqual(self.host.ban(host["guest_id"], "testing", with_address=True), "Visitor")
        lines = open(os.path.join(self.server, "modules", "custom", "lua", "coop_in.txt")).read().splitlines()
        self.assertTrue(lines[-1].endswith(f"|KICK|{guest['charid']}"))
        self.assertEqual(self.q(self.host_db, "SELECT status FROM accounts WHERE id = ?", (guest["accid"],)), [(0,)])
        self.assertEqual(sorted((b["kind"], b["value"]) for b in pp.ban_list(self.host_db)), [("ip", "127.0.0.1"), ("key", guest["owner"])])
        self.assertFalse(self.go_home()["already"])                                # the character is not trapped
        with self.assertRaises(co.Refused) as refused:
            self.visit()
        self.assertEqual(refused.exception.code, "banned")
        self.assertEqual(self.away(), [])
        pp.unban(self.host_db, "ip", "127.0.0.1")
        with self.assertRaises(co.Refused) as refused:                             # the key alone is enough
            self.visit()
        self.assertEqual(refused.exception.code, "banned")
        pp.unban(self.host_db, "key", guest["owner"])
        self.assertTrue(self.visit()["shelf"])
        self.assertFalse(self.host.kick("no-such-visitor"))

    def test_kept_places_run_out_at_the_daily_sweep(self):
        self.visit()
        self.go_home()
        old = datetime.datetime.now() - datetime.timedelta(days=pp.LOCKER_DAYS + 2)
        ct.run(self.host_db, "UPDATE coop_guest SET updated = ?", (old,))
        self.host_db.commit()
        self.host.sweep()                                                          # not yet: it swept when it started
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("locker",)])
        self.host.swept = 0
        self.host.sweep()
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("gone",)])
        self.assertTrue(any("ran out" in line for line in self.logs))

    # --- the way home from a stranger's world ---
    def test_a_bad_character_from_the_host_opens_take_back(self):
        host = self.visit()
        before = ct.rows_of(self.home, "char_inventory", CHAR, "location, slot")
        ct.run(self.host_db, "UPDATE chars SET pos_zone = 9999 WHERE charid = ?", (host["host_charid"],))
        self.host_db.commit()
        with self.assertRaises(co.Refused) as refused:
            self.go_home()
        self.assertEqual(refused.exception.code, "bad")
        row = self.away()[0]
        self.assertTrue(row["host"]["bad_return"])
        self.assertTrue(co.can_take_back(row["host"])[0])
        result = co.take_back(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home)
        self.assertEqual(result["name"], "Visitor")
        self.assertEqual(self.away(), [])
        self.assertEqual(self.q(self.home, "SELECT accid, pos_zone FROM chars WHERE charid = ?", (CHAR,)), [(ACC, 238)])
        self.assertEqual(ct.rows_of(self.home, "char_inventory", CHAR, "location, slot"), before)


if __name__ == "__main__":
    unittest.main(verbosity=1)
