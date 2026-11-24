"""Tests for the open-world parts of launcher_passport.py (2026-11-22): a visitor's place kept between visits (lockers),
visiting names, one place per visitor, and the value-by-value check of passports that come from strangers.
Two scratch databases, as in test_passport.py (see cooptest.py). Run: python test_openworld.py"""
import datetime, json, os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_passport as pp

HOME_ACC, HOME_CHAR, SECOND_CHAR = 1000, 21828, 21829
ITEMS = (65535, 16535, 4112, 12345, 513, 514, 515)       # what cooptest's character carries, and the linkshell items
OLD_GUEST_TABLE = (
    "CREATE TABLE `coop_guest` (`guest_id` VARCHAR(32) NOT NULL, `gkey` VARCHAR(64) NOT NULL, "
    "`home_world` VARCHAR(64) NOT NULL, `home_charid` INT UNSIGNED NOT NULL, `name` VARCHAR(15) NOT NULL, "
    "`charid` INT UNSIGNED NOT NULL, `accid` INT UNSIGNED NOT NULL, `login` VARCHAR(16) NOT NULL, "
    "`state` VARCHAR(16) NOT NULL DEFAULT 'active', `nonce` VARCHAR(64) NOT NULL, `generation` INT UNSIGNED NOT NULL DEFAULT 1, "
    "`arrived` DATETIME NOT NULL, `updated` DATETIME NOT NULL, `final_file` TEXT NULL, `info` TEXT NULL, "
    "PRIMARY KEY (`guest_id`), UNIQUE KEY `home` (`home_world`, `home_charid`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4")


def setUpModule():
    try:
        ct.drop_worlds()
    except Exception as e:
        raise unittest.SkipTest(f"no database to test on ({e})")


def tearDownModule():
    ct.drop_worlds()


class OpenWorldTests(unittest.TestCase):
    def setUp(self):
        self.home = ct.make_world(ct.HOME_DB)
        self.host = ct.make_world(ct.HOST_DB)
        ct.make_account(self.home, HOME_ACC, "homeplayer")
        ct.make_character(self.home, HOME_ACC, HOME_CHAR, "Visitor")
        ct.make_character(self.home, HOME_ACC, SECOND_CHAR, "Second")
        ct.make_account(self.host, HOME_ACC, "hostplayer")
        ct.make_character(self.host, HOME_ACC, HOME_CHAR, "Hostess", linkshell=False)      # the same ids on purpose
        template = ct.settings()[1]
        for world in (self.host, self.home):                 # the items each world knows (a real one has thousands)
            ct.run(world, f"CREATE TABLE item_basic LIKE `{template}`.item_basic")
            ct.run(world, f"INSERT INTO item_basic SELECT * FROM `{template}`.item_basic WHERE itemid IN ({', '.join('?' for _ in ITEMS)})", ITEMS)
            ct.run(world, f"INSERT INTO zone_settings SELECT * FROM `{template}`.zone_settings")       # ...and its areas
            world.commit()
            pp.ensure_tables(world)
            if ct.run(world, "SELECT COUNT(*) FROM item_basic")[0][0] != len(ITEMS):
                raise unittest.SkipTest("the template database has no item list (import the server's sql/item_basic.sql)")
            world.rollback()
        self.tmp = tempfile.mkdtemp()
        self.counter = 0

    def tearDown(self):
        for conn in (self.home, self.host):
            conn.rollback()
            conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def q(self, conn, sql, params=()):
        rows = ct.run(conn, sql, params)
        conn.rollback()
        return rows

    def arrive(self, data, owner="owner-a", **more):
        self.counter += 1
        guest_id = f"g{self.counter}"
        args = dict(owner=owner, keep=True, strict=True, stamp={"world": "Host"})
        args.update(more)
        return pp.import_guest(self.host, data, guest_id, "key-" + guest_id, "guest" + guest_id, "pw-" + guest_id, **args)

    def leave(self, guest):
        """The visitor logs out, goes home and tells the host it arrived. Returns what its home world answered."""
        data, _generation = pp.export_guest(self.host, guest["guest_id"], final=True, save_dir=self.tmp)
        result = pp.come_home(self.home, data, backup_dir=self.tmp, strict=True)
        pp.remove_guest(self.host, guest["guest_id"])
        return result

    def tamper(self, data, change):
        passport = pp.unpack(data)
        change(passport)
        return pp.pack(passport)

    def set_cell(self, table, column, value):
        def change(passport):
            block = passport["tables"][table]
            block["rows"][0][block["cols"].index(column)] = value
        return change

    def host_is_untouched(self):
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM chars")[0][0], 1)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM accounts")[0][0], 1)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM coop_guest")[0][0], 0)

    # --- the guest table of an older version ---
    def test_an_older_guest_table_is_brought_up_to_date(self):
        ct.run(self.host, "DROP TABLE coop_guest")
        ct.run(self.host, OLD_GUEST_TABLE)
        ct.run(self.host, "INSERT INTO coop_guest (guest_id, gkey, home_world, home_charid, name, charid, accid, login, nonce, arrived, updated) "
                          "VALUES ('old1', 'k', 'w1', 5, 'Older', 77, 1500, 'vold1', 'n', NOW(), NOW())")
        self.host.commit()
        pp.ensure_tables(self.host)
        cur = self.host.cursor()
        columns = pp.table_columns(cur, "coop_guest")
        cur.close()
        self.assertTrue({"owner", "alias", "kept"} <= set(columns))
        self.assertEqual(self.q(self.host, "SELECT owner, alias, kept FROM coop_guest WHERE guest_id = 'old1'"), [("", None, 0)])
        index = self.q(self.host, "SELECT GROUP_CONCAT(column_name ORDER BY seq_in_index) FROM information_schema.statistics "
                                  "WHERE table_schema = DATABASE() AND table_name = 'coop_guest' AND index_name = 'home'")[0][0]
        self.assertEqual(index, "owner,home_world,home_charid")
        pp.ensure_tables(self.host)                          # a second time changes nothing
        self.assertEqual(len(pp.guest_list(self.host)), 1)

    # --- passports of strangers ---
    def test_a_normal_character_passes_the_check(self):
        ct.make_squad(self.home, HOME_CHAR, [(1, "Matea", 3, 20), (2, "Mateb", 4, 25)], unlocks=(16535,))
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        guest = self.arrive(data)
        self.assertEqual((guest["local"], guest["shelf"], guest["again"]), ("Visitor", False, False))
        self.assertEqual(self.q(self.host, "SELECT charname FROM chars WHERE charid = ?", (guest["charid"],)), [("Visitor",)])
        self.assertEqual(self.q(self.host, "SELECT owner, alias, kept, state FROM coop_guest"), [("owner-a", None, 1, "active")])
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM squad_mate WHERE charid = ?", (guest["charid"],))[0][0], 2)

    def test_what_a_server_cannot_load_is_refused(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})

        def add_item(row):
            def change(passport):
                block = passport["tables"]["char_inventory"]
                new = list(block["rows"][-1])
                for column, value in row.items():
                    new[block["cols"].index(column)] = value
                block["rows"].append(new)
            return change

        def many_items(passport):
            block = passport["tables"]["char_inventory"]
            block["rows"] = [list(block["rows"][-1]) for _ in range(pp.OPEN_ROWS["char_inventory"] + 1)]

        cases = {
            "an area that does not exist": self.set_cell("chars", "pos_zone", 9999),
            "a home point that does not exist": self.set_cell("chars", "home_zone", 4000),
            "a job that does not exist": self.set_cell("char_stats", "mjob", 77),
            "no job": self.set_cell("char_stats", "mjob", 0),
            "a level that is not a level": self.set_cell("char_stats", "mlvl", 150),
            "a job level that is not a level": self.set_cell("char_jobs", "war", 200),
            "a race that does not exist": self.set_cell("char_look", "race", 12),
            "a face that does not exist": self.set_cell("char_look", "face", 40),
            "a bag larger than a bag": self.set_cell("char_storage", "inventory", 200),
            "an unknown item": add_item({"itemId": 60000, "slot": 9}),
            "two items in one slot": add_item({}),
            "an item in a bag that does not exist": add_item({"location": 40, "slot": 9}),
            "text where a number goes": self.set_cell("char_stats", "hp", "500"),
            "a number too large for its column": self.set_cell("char_stats", "hp", 70000),
            "a negative number": self.set_cell("chars", "playtime", -5),
            "true where a number goes": self.set_cell("char_stats", "hp", True),
            "a list where a number goes": self.set_cell("char_stats", "hp", [1]),
            "not a number": self.set_cell("chars", "pos_x", float("nan")),
            "infinity": self.set_cell("chars", "pos_x", float("inf")),
            "nothing where something must be": self.set_cell("chars", "nation", None),
            "a control character in text": add_item({"signature": "Ma\x01ker", "slot": 9}),
            "text too long for its column": add_item({"signature": "M" * 21, "slot": 9}),
            "a number where bytes go": self.set_cell("chars", "missions", 5),
            "bytes that are not bytes": self.set_cell("chars", "missions", {"b": "***"}),
            "bytes too long for their column": self.set_cell("chars", "missions", {"b": "QUFB" * 30000}),
            "a date that is not a date": self.set_cell("chars", "timecreated", {"t": "yesterday"}),
            "more items than bags hold": many_items,
        }
        for what, change in cases.items():
            with self.subTest(what):
                with self.assertRaises(pp.BadPassport):
                    self.arrive(self.tamper(data, change))
                self.host_is_untouched()
        self.arrive(data)                                    # and the same passport, untouched, is welcome

    def test_a_squad_from_a_stranger_is_checked_too(self):
        ct.make_squad(self.home, HOME_CHAR, [(1, "Matea", 3, 20)])
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})

        def mate(column, value):
            def change(passport):
                block = passport["squad"]["squad_mate"]
                block["rows"][0][block["cols"].index(column)] = value
            return change

        def level(passport):
            block = passport["squad"]["squad_job"]
            block["rows"][0][block["cols"].index("level")] = 120

        for what, change in (("job", mate("mjob", 99)), ("race", mate("race", 30)), ("level", level), ("type", mate("mjob", "3"))):
            with self.subTest(what):
                with self.assertRaises(pp.BadPassport):
                    self.arrive(self.tamper(data, change))
                self.host_is_untouched()

    def test_a_passport_far_too_large_is_not_even_read(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        limit, pp.OPEN_PASSPORT_BYTES = pp.OPEN_PASSPORT_BYTES, 2000
        try:
            with self.assertRaises(pp.PassportError):
                self.arrive(data)
        finally:
            pp.OPEN_PASSPORT_BYTES = limit
        self.host_is_untouched()
        self.assertFalse(pp.import_guest(self.host, data, "gx", "k", "guestgx", "pw")["again"])     # between friends it is fine

    # --- a place that is kept ---
    def stay_a_while(self, charid):
        """What a visitor leaves in an open world: a linkshell (worn), an auction listing, mail, and what bots know of it."""
        ct.run(self.host, "INSERT INTO char_inventory (charid, location, slot, itemId, quantity, extra) VALUES (?, 0, 7, 515, 1, ?)",
               (charid, b"\x09\x00\x00\x00" + b"\x22" * 20))
        ct.run(self.host, "INSERT INTO char_equip (charid, slotid, equipslotid, containerid) VALUES (?, 7, 16, 0)", (charid,))
        ct.run(self.host, "INSERT INTO auction_house (itemid, stack, seller, seller_name, date, price) VALUES (4112, 0, ?, 'Visitor', 1, 500)", (charid,))
        ct.run(self.host, "INSERT INTO delivery_box (charid, charname, box, slot, itemid, quantity, sender) VALUES (?, 'Visitor', 1, 8, 65535, 500, 'AH')", (charid,))
        ct.run(self.host, "INSERT INTO char_vars (charid, varname, value) VALUES (?, '[Bots]Friend', 3)", (charid,))
        ct.run(self.host, "UPDATE char_inventory SET quantity = 7777 WHERE charid = ? AND location = 0 AND slot = 0", (charid,))
        self.host.commit()

    def test_a_place_is_kept_and_given_back(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        first = self.arrive(data)
        charid, accid = first["charid"], first["accid"]
        self.stay_a_while(charid)
        result = self.leave(first)
        self.assertFalse(result["already"])
        self.assertEqual(self.q(self.home, "SELECT quantity FROM char_inventory WHERE charid = ? AND location = 0 AND slot = 0", (HOME_CHAR,)), [(7777,)])
        self.assertEqual(self.q(self.home, "SELECT COUNT(*) FROM char_vars WHERE charid = ? AND varname = '[Bots]Friend'", (HOME_CHAR,))[0][0], 0)
        # at the host: the character stays behind with its account closed, and is no longer in the list of visitors
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("locker",)])
        self.assertEqual(self.q(self.host, "SELECT status FROM accounts WHERE id = ?", (accid,)), [(0,)])
        self.assertEqual(self.q(self.host, "SELECT charname FROM chars WHERE charid = ?", (charid,)), [("Visitor",)])
        self.assertEqual(pp.guest_list(self.host), [])
        kept = pp.locker_list(self.host)
        self.assertEqual([(k["name"], k["local"], k["owner"], k["charid"]) for k in kept], [("Visitor", "Visitor", "owner-a", charid)])
        self.assertFalse(pp.remove_guest(self.host, first["guest_id"]))                      # telling it twice changes nothing
        self.assertNotIn(charid, [c for c, _n in pp.home_characters(self.host)])             # it is not one of the host's own
        # the passport of the visit that is over cannot be used again
        with self.assertRaises(pp.PassportError):
            self.arrive(data)
        # the next visit: the same character and account, with what it left here
        ct.run(self.home, "UPDATE char_inventory SET quantity = 9000 WHERE charid = ? AND location = 0 AND slot = 0", (HOME_CHAR,))
        self.home.commit()
        data2, _nonce = pp.depart(self.home, HOME_CHAR, {})
        second = self.arrive(data2)
        self.assertEqual((second["charid"], second["accid"], second["shelf"], second["local"]), (charid, accid, True, "Visitor"))
        self.assertEqual(self.q(self.host, "SELECT login, status FROM accounts WHERE id = ?", (accid,)), [(second["login"], 1)])
        self.assertEqual(self.q(self.host, "SELECT guest_id, state, kept, final_file FROM coop_guest"), [(second["guest_id"], "active", 1, None)])
        self.assertEqual(self.q(self.host, "SELECT quantity FROM char_inventory WHERE charid = ? AND location = 0 AND slot = 0", (charid,)), [(9000,)])
        self.assertEqual(self.q(self.host, "SELECT location, slot FROM char_inventory WHERE charid = ? AND itemId = 515", (charid,)), [(0, 7)])
        self.assertEqual(self.q(self.host, "SELECT slotid FROM char_equip WHERE charid = ? AND equipslotid = 16", (charid,)), [(7,)])
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM auction_house WHERE seller = ?", (charid,))[0][0], 1)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM delivery_box WHERE charid = ?", (charid,))[0][0], 1)
        self.assertEqual(self.q(self.host, "SELECT value FROM char_vars WHERE charid = ? AND varname = '[Bots]Friend'", (charid,)), [(3,)])
        self.assertEqual(self.q(self.host, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (charid, pp.GUEST_VAR)), [(1,)])
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM chars")[0][0], 2)
        self.assertEqual(pp.locker_list(self.host), [])
        self.assertFalse(self.leave(second)["already"])
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("locker",)])

    def test_the_squad_comes_back_to_the_kept_place(self):
        ct.make_squad(self.home, HOME_CHAR, [(1, "Matea", 3, 20), (2, "Mateb", 4, 25)])
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        first = self.arrive(data)
        before = self.q(self.host, "SELECT id, slot FROM squad_mate WHERE charid = ? ORDER BY slot", (first["charid"],))
        self.leave(first)
        ct.run(self.home, "DELETE FROM squad_mate WHERE charid = ? AND slot = 2", (HOME_CHAR,))
        self.home.commit()
        data2, _nonce = pp.depart(self.home, HOME_CHAR, {})
        second = self.arrive(data2)
        self.assertTrue(second["shelf"])
        self.assertEqual(self.q(self.host, "SELECT id, slot FROM squad_mate WHERE charid = ? ORDER BY slot", (first["charid"],)), before[:1])

    def test_between_friends_nothing_is_kept(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        guest = pp.import_guest(self.host, data, "gf", "key", "guestgf", "pw")
        self.assertEqual(self.q(self.host, "SELECT owner, kept FROM coop_guest"), [("", 0)])
        self.stay_a_while(guest["charid"])
        out, _generation = pp.export_guest(self.host, "gf", final=True, save_dir=self.tmp)
        pp.come_home(self.home, out, backup_dir=self.tmp)
        self.assertTrue(pp.remove_guest(self.host, "gf"))
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("gone",)])
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM chars WHERE charid = ?", (guest["charid"],))[0][0], 0)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM auction_house")[0][0], 0)

    def test_a_kept_place_runs_out(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        first = self.arrive(data)
        self.stay_a_while(first["charid"])
        self.leave(first)
        now = datetime.datetime.now()
        self.assertEqual(pp.expire_lockers(self.host, now=now + datetime.timedelta(days=pp.LOCKER_DAYS - 1)), [])
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("locker",)])
        self.assertEqual(pp.expire_lockers(self.host, now=now + datetime.timedelta(days=pp.LOCKER_DAYS + 1)), ["Visitor"])
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("gone",)])
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM chars WHERE charid = ?", (first["charid"],))[0][0], 0)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM accounts WHERE id = ?", (first["accid"],))[0][0], 0)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM auction_house")[0][0], 0)
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM delivery_box")[0][0], 0)
        self.assertEqual(self.q(self.host, "SELECT charname FROM chars"), [("Hostess",)])
        data2, _nonce = pp.depart(self.home, HOME_CHAR, {})          # and it is welcome again, as a new visitor
        again = self.arrive(data2)
        self.assertFalse(again["shelf"])
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("active",)])

    def test_the_host_can_clear_a_kept_place(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        first = self.arrive(data)
        self.leave(first)
        self.assertTrue(pp.remove_guest(self.host, first["guest_id"], forget=True))
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest"), [("gone",)])
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM chars")[0][0], 1)

    # --- names and owners ---
    def test_a_taken_name_needs_a_visiting_name(self):
        ct.make_character(self.host, HOME_ACC, 30000, "Visitor", linkshell=False)
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        with self.assertRaises(pp.NameTaken):
            self.arrive(data)
        for name in ("vi", "visitorb", "VISITORB", "Visitor2", "Averyveryverylongname", 7):
            with self.assertRaises(pp.PassportError):
                self.arrive(data, alias=name)
        with self.assertRaises(pp.NameTaken):
            self.arrive(data, alias="Hostess")
        self.assertEqual(self.q(self.host, "SELECT COUNT(*) FROM coop_guest")[0][0], 0)
        guest = self.arrive(data, alias="Visitorb")
        self.assertEqual(guest["local"], "Visitorb")
        self.assertEqual(self.q(self.host, "SELECT charname FROM chars WHERE charid = ?", (guest["charid"],)), [("Visitorb",)])
        self.assertEqual(self.q(self.host, "SELECT name, alias FROM coop_guest"), [("Visitor", "Visitorb")])
        listed = pp.guest_list(self.host)[0]
        self.assertEqual((listed["name"], listed["local"], listed["kept"], listed["owner"]), ("Visitor", "Visitorb", True, "owner-a"))
        out, _generation = pp.export_guest(self.host, guest["guest_id"], final=True, save_dir=self.tmp)
        self.assertEqual(pp.unpack(out)["name"], "Visitor")                           # it goes home under its own name
        pp.come_home(self.home, out, backup_dir=self.tmp, strict=True)
        self.assertEqual(self.q(self.home, "SELECT charname FROM chars WHERE charid = ?", (HOME_CHAR,)), [("Visitor",)])
        pp.remove_guest(self.host, guest["guest_id"])
        data2, _nonce = pp.depart(self.home, HOME_CHAR, {})                           # next time its visiting name is still its own
        again = self.arrive(data2)
        self.assertEqual((again["shelf"], again["local"], again["charid"]), (True, "Visitorb", guest["charid"]))

    def test_every_visitor_has_a_place_of_its_own(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        mine = self.arrive(data, owner="owner-a")
        # somebody else's launcher claims the same home world and character number (it only has to say so)
        stranger = self.tamper(data, lambda passport: passport.update(nonce="another-visit"))
        with self.assertRaises(pp.NameTaken):
            self.arrive(stranger, owner="owner-b")
        theirs = self.arrive(stranger, owner="owner-b", alias="Impostor")
        self.assertNotEqual(theirs["charid"], mine["charid"])
        self.assertEqual(sorted(self.q(self.host, "SELECT owner, state FROM coop_guest")), [("owner-a", "active"), ("owner-b", "active")])
        self.leave(mine)
        self.assertEqual(sorted(self.q(self.host, "SELECT owner, state FROM coop_guest")), [("owner-a", "locker"), ("owner-b", "active")])
        # ...and cannot have the place kept for the first one
        data2 = self.tamper(data, lambda passport: passport.update(nonce="a-third-visit"))
        pp.remove_guest(self.host, theirs["guest_id"], forget=True)
        with self.assertRaises(pp.NameTaken):
            self.arrive(data2, owner="owner-b")
        self.assertEqual(self.q(self.host, "SELECT owner, state FROM coop_guest WHERE state <> 'gone'"), [("owner-a", "locker")])

    def test_a_full_world_is_full_for_returning_visitors_too(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        first = self.arrive(data, max_guests=1)
        other, _nonce = pp.depart(self.home, SECOND_CHAR, {})
        with self.assertRaises(pp.PassportError):
            self.arrive(other, max_guests=1)
        self.leave(first)
        second = self.arrive(other, max_guests=1)
        data2, _nonce = pp.depart(self.home, HOME_CHAR, {})
        with self.assertRaises(pp.PassportError):
            self.arrive(data2, max_guests=1)
        self.assertEqual(self.q(self.host, "SELECT state FROM coop_guest ORDER BY name"), [("active",), ("locker",)])
        self.leave(second)
        self.assertTrue(self.arrive(data2, max_guests=1)["shelf"])

    # --- the way home from a stranger's world ---
    def test_a_bad_passport_on_the_way_home_changes_nothing(self):
        data, _nonce = pp.depart(self.home, HOME_CHAR, {})
        guest = self.arrive(data)
        before = ct.rows_of(self.home, "char_inventory", HOME_CHAR, "location, slot")
        out, _generation = pp.export_guest(self.host, guest["guest_id"], final=True, save_dir=self.tmp)
        for change in (self.set_cell("chars", "pos_zone", 9999), self.set_cell("char_stats", "mjob", 99),
                       self.set_cell("char_stats", "hp", "lots")):
            with self.assertRaises(pp.BadPassport):
                pp.come_home(self.home, self.tamper(out, change), backup_dir=self.tmp, strict=True)
            self.assertEqual(self.q(self.home, "SELECT state FROM coop_away"), [("away",)])
            self.assertEqual(ct.rows_of(self.home, "char_inventory", HOME_CHAR, "location, slot"), before)
        with self.assertRaises(pp.BadPassport):                                       # a bad checkpoint is no way home either
            pp.take_back(self.home, HOME_CHAR, checkpoint=self.tamper(out, self.set_cell("chars", "pos_zone", 9999)), strict=True)
        result = pp.take_back(self.home, HOME_CHAR)                                   # as it was before the visit
        self.assertFalse(result["already"])
        self.assertEqual(self.q(self.home, "SELECT accid FROM chars WHERE charid = ?", (HOME_CHAR,)), [(HOME_ACC,)])
        self.assertEqual(ct.rows_of(self.home, "char_inventory", HOME_CHAR, "location, slot"), before)


if __name__ == "__main__":
    unittest.main(verbosity=1)
