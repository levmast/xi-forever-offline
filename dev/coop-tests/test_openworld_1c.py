"""Tests for open worlds, slice 1c (2026-11-22): what the CO-OP page needs from launcher_coop.py (a banned visitor is
asked out until it has left, bans and kept places from the host's side, the visitor's own list of kept places) and two
passport rules for strangers' worlds (a yell ban stays in its world; a character handed over in jail is put at its home
point). Uses the worlds and the listener of test_openservice.py. Run: python test_openworld_1c.py"""
import json, os, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_coop as co
import launcher_passport as pp
import test_openservice as svc

ACC, CHAR = svc.ACC, svc.CHAR
setUpModule, tearDownModule = svc.setUpModule, svc.tearDownModule


class Plain(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        self.row = {"charid": 7, "name": "Hurami"}
        self.host = {"open": True, "keep_days": 90, "world": {"id": "w1", "name": "The Hub"}, "address": "203.0.113.9", "port": 54100,
                     "pin": "SHA256:" + "A" * 43, "local": "Hura"}

    def tearDown(self):
        shutil.rmtree(self.kit, ignore_errors=True)

    def test_days_a_world_says_it_keeps_a_place(self):
        self.assertEqual([co._days(v) for v in (90, "90", 0, -5, 10 ** 9, None, "soon", [], float("inf"), 1.9)],
                         [90, 90, 0, 0, 3650, 0, 0, 0, 0, 1])

    def test_a_place_is_noted_with_its_end_date(self):
        self.assertEqual(co.places(self.kit), [])
        place = co.remember_place(self.kit, self.row, self.host, now=1000000)
        self.assertEqual(place["local"], "Hura")
        found = co.places(self.kit, now=1000001)
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["world"], found[0]["charid"], found[0]["name"], found[0]["local"], found[0]["days"]),
                         ("The Hub", 7, "Hurami", "Hura", 90))
        self.assertEqual(found[0]["until"], 1000000 + 90 * 86400)
        self.assertEqual(co.read_code(co.place_link(found[0])),
                         {"address": "203.0.113.9", "port": 54100, "pin": "SHA256:" + "A" * 43, "world": "The Hub", "open": True})
        self.assertEqual(co.places(self.kit, now=1000000 + 90 * 86400 + 1), [])          # its time is up: no longer listed
        with open(os.path.join(self.kit, "coop", "places.json"), encoding="utf-8") as handle:
            self.assertNotIn("until", handle.read())                                      # worked out, never stored

    def test_one_place_per_character_and_world(self):
        co.remember_place(self.kit, self.row, self.host, now=1000)
        co.remember_place(self.kit, {"charid": 8, "name": "Kurami"}, self.host, now=2000)
        co.remember_place(self.kit, self.row, dict(self.host, world={"id": "w2", "name": "Other"}), now=3000)
        co.remember_place(self.kit, self.row, dict(self.host, address="203.0.113.77"), now=4000)      # the same place, visited again
        found = co.places(self.kit, now=5000)
        self.assertEqual([(p["world_id"], p["charid"], p["last"], p["address"]) for p in found],
                         [("w1", 7, 4000, "203.0.113.77"), ("w2", 7, 3000, "203.0.113.9"), ("w1", 8, 2000, "203.0.113.9")])
        with open(os.path.join(self.kit, "coop", "places.json"), encoding="utf-8") as handle:
            self.assertNotIn("until", handle.read())
        co.forget_place(self.kit, "w2", 7, now=5000)
        self.assertEqual([(p["world_id"], p["charid"]) for p in co.places(self.kit, now=5000)], [("w1", 7), ("w1", 8)])

    def test_worlds_that_keep_no_place_are_not_noted(self):
        for host in (dict(self.host, open=False), dict(self.host, keep_days=0), dict(self.host, keep_days="x"),
                     dict(self.host, world={}), dict(self.host, pin="")):
            self.assertIsNone(co.remember_place(self.kit, self.row, host))
        self.assertEqual(co.places(self.kit), [])
        self.assertFalse(os.path.exists(os.path.join(self.kit, "coop", "places.json")))

    def test_a_damaged_list_is_read_as_far_as_it_goes(self):
        os.makedirs(os.path.join(self.kit, "coop"))
        path = os.path.join(self.kit, "coop", "places.json")
        for text in ("not json", "{}", "[1, null, \"x\", {}]"):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
            self.assertEqual(co.places(self.kit), [])
        good = {"world": "The Hub", "world_id": "w1", "address": "203.0.113.9", "port": 54100, "pin": "SHA256:x", "charid": 7,
                "name": "Hurami", "last": int(time.time()), "days": 90}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump([dict(good, address="not an address!"), dict(good, port=0), dict(good, days=0), good, dict(good, charid="seven")], handle)
        self.assertEqual([(p["world_id"], p["local"]) for p in co.places(self.kit)], [("w1", "Hurami")])


class OpenWorld(unittest.TestCase):
    setUp, tearDown = svc.OpenWorld.setUp, svc.OpenWorld.tearDown
    q, visit, go_home, away = svc.OpenWorld.q, svc.OpenWorld.visit, svc.OpenWorld.go_home, svc.OpenWorld.away

    def kicks(self):
        try:
            with open(os.path.join(self.server, "modules", "custom", "lua", "coop_in.txt")) as handle:
                return [line.split("|")[3] for line in handle.read().splitlines() if "|KICK|" in line]
        except OSError:
            return []

    def online(self, guest, yes=True):
        ct.run(self.host_db, "DELETE FROM accounts_sessions WHERE charid = ?", (guest["charid"],))
        if yes:
            ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()

    # --- the host's side ---
    def test_hello_says_how_long_a_place_is_kept(self):
        self.assertEqual(co.hello(self.link)["keep_days"], pp.LOCKER_DAYS)
        self.settings["open"] = False                                              # a friends world keeps no places
        invite = co.read_code(co.make_invite("127.0.0.1", self.settings["port"], self.settings["secret"], "Host world"))
        self.assertEqual(co.hello(invite)["keep_days"], 0)

    def test_a_banned_visitor_still_in_the_game_is_asked_out_again(self):
        host = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.online(guest)
        self.assertEqual(self.host.ban(host["guest_id"]), "Visitor")
        self.assertEqual(self.kicks(), [str(guest["charid"])])
        self.host.guests()                                                         # the page's look, a moment later: nothing new
        self.assertEqual(len(self.kicks()), 1)
        now = time.time()
        self.host._keep_out(self.host.guests(), now + co.KEEP_OUT_SECONDS + 1)     # half a minute on and still in the game
        self.assertEqual(self.kicks(), [str(guest["charid"])] * 2)
        self.host._keep_out(self.host.guests(), now + co.KEEP_OUT_SECONDS + 5)     # asked a moment ago: not again yet
        self.assertEqual(len(self.kicks()), 2)
        self.online(guest, False)
        self.host._keep_out(self.host.guests(), now + 3 * co.KEEP_OUT_SECONDS)     # out of the game: left in peace
        self.assertEqual(len(self.kicks()), 2)
        self.assertIn(host["guest_id"], self.host.out)                             # ...but watched while its character is here
        self.assertFalse(self.go_home()["already"])
        self.host.guests()
        self.assertEqual(self.host.out, {})                                        # home: nothing left to watch

    def test_a_plain_kick_is_one_request(self):
        host = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.online(guest)
        self.assertTrue(self.host.kick(host["guest_id"]))
        self.host._keep_out(self.host.guests(), time.time() + 600)
        self.assertEqual(self.kicks(), [str(guest["charid"])])                     # the visitor may come straight back
        self.assertEqual(self.host.out, {})

    def test_a_ban_is_given_up_after_an_hour_of_asking(self):
        host = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.online(guest)
        self.host.ban(host["guest_id"])
        self.host._keep_out(self.host.guests(), time.time() + 3601)
        self.assertEqual(self.host.out, {})
        self.assertEqual(len(self.kicks()), 1)

    def test_a_visitor_who_is_home_can_be_banned_from_its_kept_place(self):
        self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.go_home()
        kept = self.host.lockers()[0]
        self.host.addresses.clear()                                                # (as after the launcher was closed and opened)
        self.assertEqual(self.host.ban(kept["guest_id"], "left a mess", with_address=True), "Visitor")
        self.assertEqual(self.kicks(), [])                                          # nobody is in the game
        self.assertEqual(self.host.out, {})
        self.assertEqual(sorted((b["kind"], b["value"], b["reason"]) for b in self.host.bans()),
                         [("ip", "127.0.0.1", "left a mess"), ("key", guest["owner"], "left a mess")])
        with self.assertRaises(co.Refused) as refused:
            self.visit()
        self.assertEqual(refused.exception.code, "banned")
        self.host.unban("ip", "127.0.0.1")
        self.host.unban("key", guest["owner"])
        self.assertEqual(self.host.bans(), [])
        self.assertTrue(self.visit()["shelf"])                                     # its place was still there
        self.assertIsNone(self.host.ban("no-such-visitor"))

    def test_a_kept_place_can_be_given_up_but_not_a_visitor_who_is_here(self):
        host = self.visit()
        guest = pp.guest_list(self.host_db)[0]
        self.assertFalse(self.host.forget(host["guest_id"]))                       # here right now: not a kept place
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM chars WHERE charid = ?", (guest["charid"],)), [(1,)])
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("active",)])
        self.go_home()
        kept = self.host.lockers()[0]
        self.assertFalse(self.host.forget("no-such-visitor"))
        self.assertTrue(self.host.forget(kept["guest_id"]))
        self.assertEqual(self.q(self.host_db, "SELECT state FROM coop_guest"), [("gone",)])
        self.assertEqual(self.q(self.host_db, "SELECT COUNT(*) FROM chars WHERE charid = ?", (guest["charid"],)), [(0,)])
        self.assertEqual(self.host.lockers(), [])
        self.assertFalse(self.host.forget(kept["guest_id"]))
        self.assertFalse(self.visit()["shelf"])                                    # a new visit starts from nothing

    # --- the visitor's side ---
    def test_the_visitors_launcher_notes_the_place_kept_for_it(self):
        host = self.visit()
        self.assertEqual(host["keep_days"], pp.LOCKER_DAYS)
        self.assertEqual(co.places(self.kit_home), [])                             # while it is there, nothing is "kept" yet
        self.go_home()
        place = co.places(self.kit_home)[0]
        world = pp.world_identity(self.host_db)
        self.host_db.rollback()
        self.assertEqual((place["world_id"], place["world"], place["charid"], place["name"], place["local"], place["days"]),
                         (world["id"], world["name"], CHAR, "Visitor", "Visitor", pp.LOCKER_DAYS))
        self.assertLess(abs(place["until"] - (time.time() + pp.LOCKER_DAYS * 86400)), 120)
        self.assertEqual(co.read_code(co.place_link(place)), self.link)            # the way back
        self.assertTrue(self.visit()["shelf"])
        self.go_home()
        self.assertEqual(len(co.places(self.kit_home)), 1)

    def test_a_right_password_is_not_asked_for_again_when_the_name_is_taken(self):
        self.settings["password"] = co.hash_password("moogle")
        ct.make_character(self.host_db, ACC, CHAR + 1, "Visitor", linkshell=False)
        again = lambda **more: co.finish_arrival(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home, **more)
        with self.assertRaises(co.Refused) as refused:
            self.visit(password="kupo")
        self.assertEqual(refused.exception.code, "password")
        with self.assertRaises(co.Refused) as refused:
            again(password="moogle")                                               # the right one now, but the name is taken
        self.assertEqual(refused.exception.code, "name")
        host = again(alias="Kupo")                                                 # only the name is given this time
        self.assertEqual((host["arrived"], host["local"]), (True, "Kupo"))
        self.assertNotIn("password", self.away()[0]["host"])                       # once arrived it is not kept
        self.assertFalse(self.go_home()["already"])

    def test_a_visit_to_a_friend_leaves_no_place(self):
        invite = co.read_code(co.make_invite("127.0.0.1", self.settings["port"], self.settings["secret"], "Host world"))
        co.start_visit(self.cfg, self.kit_home, invite, CHAR, log=self.logs.append, connect=self.connect_home)
        self.go_home()
        self.assertEqual(co.places(self.kit_home), [])

    # --- passports of strangers' worlds ---
    def var(self, conn, charid, name):
        return self.q(conn, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (charid, name))

    def test_a_yell_ban_stays_in_the_world_that_gave_it(self):
        ct.run(self.home, "INSERT INTO char_vars (charid, varname, value) VALUES (?, '[YELL]Banned', 1)", (CHAR,))
        self.home.commit()
        host = self.visit()
        there = host["host_charid"]
        self.assertEqual(self.var(self.host_db, there, "[YELL]Banned"), [])        # home's ban did not come along
        self.assertEqual(self.var(self.host_db, there, "[Quest]Progress"), [(3,)])  # (ordinary settings still travel)
        ct.run(self.host_db, "INSERT INTO char_vars (charid, varname, value) VALUES (?, '[YELL]Cooldown', 1)", (there,))
        ct.run(self.host_db, "UPDATE char_vars SET value = 7 WHERE charid = ? AND varname = '[Quest]Progress'", (there,))
        self.host_db.commit()
        self.go_home()
        self.assertEqual(self.var(self.home, CHAR, "[YELL]Banned"), [(1,)])        # home keeps its own
        self.assertEqual(self.var(self.home, CHAR, "[YELL]Cooldown"), [])          # the other world's did not come home
        self.assertEqual(self.var(self.home, CHAR, "[Quest]Progress"), [(7,)])
        self.visit()
        self.assertEqual(self.var(self.host_db, there, "[YELL]Cooldown"), [(1,)])  # and waits in its kept place there

    def place(self, conn, charid):
        return self.q(conn, "SELECT pos_zone, pos_prevzone, pos_x, pos_y, pos_z, pos_rot FROM chars WHERE charid = ?", (charid,))[0]

    def home_point(self, conn, charid, zone=230):
        ct.run(conn, "UPDATE chars SET home_zone = ?, home_x = 11.5, home_y = -2.0, home_z = 44.25, home_rot = 64 WHERE charid = ?", (zone, charid))
        conn.commit()

    def test_a_character_sent_home_from_jail_is_put_at_its_home_point(self):
        self.home_point(self.home, CHAR)
        host = self.visit()
        ct.run(self.host_db, "UPDATE chars SET pos_zone = ?, pos_x = 1, pos_y = 2, pos_z = 3 WHERE charid = ?", (pp.GAOL, host["host_charid"]))
        self.host_db.commit()
        result = self.go_home()
        self.assertEqual(self.place(self.home, CHAR), (230, 230, 11.5, -2.0, 44.25, 64))
        self.assertTrue(any("jail" in note for note in result["notes"]), result["notes"])
        self.assertEqual(self.away(), [])

    def test_also_from_a_mog_house_entered_from_the_jail(self):
        self.home_point(self.home, CHAR)
        host = self.visit()
        ct.run(self.host_db, "UPDATE chars SET pos_zone = 0, pos_prevzone = ? WHERE charid = ?", (pp.GAOL, host["host_charid"]))
        self.host_db.commit()
        self.go_home()
        self.assertEqual(self.place(self.home, CHAR)[:2], (230, 230))

    def test_an_ordinary_return_is_left_where_it_was(self):
        self.home_point(self.home, CHAR)
        host = self.visit()
        ct.run(self.host_db, "UPDATE chars SET pos_zone = 240, pos_prevzone = 238, pos_x = 5 WHERE charid = ?", (host["host_charid"],))
        self.host_db.commit()
        result = self.go_home()
        self.assertEqual(self.place(self.home, CHAR)[:3], (240, 238, 5.0))
        self.assertFalse(any("jail" in note for note in result["notes"]))
        ct.run(self.host_db, "UPDATE chars SET pos_zone = 0, pos_prevzone = 240 WHERE charid = ?", (host["host_charid"],))
        self.host_db.commit()
        self.visit()                                                               # (its place here: the passport's rows replace these)
        self.go_home()
        self.assertEqual(self.place(self.home, CHAR)[:2], (240, 238))

    def test_jail_with_no_home_point_to_go_to_opens_take_back(self):
        for zone in (pp.GAOL, 0):
            with self.subTest(home_zone=zone):
                host = self.visit()
                ct.run(self.host_db, "UPDATE chars SET pos_zone = ?, home_zone = ? WHERE charid = ?", (pp.GAOL, zone, host["host_charid"]))
                self.host_db.commit()
                with self.assertRaises(co.Refused) as refused:
                    self.go_home()
                self.assertEqual(refused.exception.code, "bad")
                self.assertTrue(co.can_take_back(self.away()[0]["host"])[0])
                co.take_back(self.cfg, self.kit_home, CHAR, log=self.logs.append, connect=self.connect_home)
                self.assertEqual(self.place(self.home, CHAR)[0], 238)             # as it was before the visit
                ct.run(self.host_db, "DELETE FROM accounts_sessions")
                self.host.send_home(host["guest_id"])                              # the host clears the stranded copy
                pp.remove_guest(self.host_db, host["guest_id"], forget=True)

    def test_a_visitor_who_arrives_from_jail_lands_at_its_home_point(self):
        self.home_point(self.home, CHAR, zone=235)
        ct.run(self.home, "UPDATE chars SET pos_zone = ? WHERE charid = ?", (pp.GAOL, CHAR))
        self.home.commit()
        host = self.visit()
        self.assertEqual(self.place(self.host_db, host["host_charid"]), (235, 235, 11.5, -2.0, 44.25, 64))
        self.assertEqual(self.place(self.home, CHAR)[0], pp.GAOL)                  # at home nothing was touched


class Friends(unittest.TestCase):
    """Between friends a passport is taken as it is: a friend's world may send its visitor home from anywhere."""
    setUp, tearDown = svc.OpenWorld.setUp, svc.OpenWorld.tearDown
    q, go_home = svc.OpenWorld.q, svc.OpenWorld.go_home

    def test_between_friends_a_character_comes_home_as_it_was_sent(self):
        invite = co.read_code(co.make_invite("127.0.0.1", self.settings["port"], self.settings["secret"], "Host world"))
        host = co.start_visit(self.cfg, self.kit_home, invite, CHAR, log=self.logs.append, connect=self.connect_home)
        ct.run(self.host_db, "UPDATE chars SET pos_zone = ? WHERE charid = ?", (pp.GAOL, host["host_charid"]))
        self.host_db.commit()
        result = self.go_home()
        self.assertEqual(self.q(self.home, "SELECT pos_zone FROM chars WHERE charid = ?", (CHAR,)), [(pp.GAOL,)])
        self.assertFalse(any("jail" in note for note in result["notes"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
