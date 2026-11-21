"""Tests for the carry files of launcher_passport.py (one player, several PCs) on two scratch databases (see
cooptest.py). Run: python test_carry.py"""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_passport as pp

ACC, CHAR = 1000, 21828
BOT_ACC, BOT_CHAR = pp.BOT_ACCOUNT_BASE + 5, pp.BOT_CHAR_BASE + 5


def setUpModule():
    try:
        ct.drop_worlds()
    except Exception as e:
        raise unittest.SkipTest(f"no database to test on ({e})")


def tearDownModule():
    ct.drop_worlds()


class CarryTests(unittest.TestCase):
    def setUp(self):
        self.pc = ct.make_world(ct.HOME_DB)
        self.laptop = ct.make_world(ct.HOST_DB)
        ct.make_account(self.pc, ACC, "pcplayer")
        ct.make_character(self.pc, ACC, CHAR, "Traveller")
        ct.make_account(self.laptop, ACC, "laptopplayer")
        ct.make_character(self.laptop, ACC, CHAR, "Other", linkshell=False)       # the same ids on purpose
        self.tmp = tempfile.mkdtemp()
        self.kit_pc, self.kit_laptop, self.cloud = (os.path.join(self.tmp, n) for n in ("pc", "laptop", "cloud"))
        for folder in (self.kit_pc, self.kit_laptop, self.cloud):
            os.makedirs(folder)
        self.lines = []

    def tearDown(self):
        for conn in (self.pc, self.laptop):
            conn.rollback()
            conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def q(self, conn, sql, params=()):
        rows = ct.run(conn, sql, params)
        conn.rollback()
        return rows

    def gil(self, conn, name):
        return self.q(conn, "SELECT i.quantity FROM char_inventory i JOIN chars c ON c.charid = i.charid "
                            "WHERE c.charname = ? AND i.itemId = 65535", (name,))[0][0]

    def set_gil(self, conn, name, amount):
        ct.run(conn, "UPDATE char_inventory i JOIN chars c ON c.charid = i.charid SET i.quantity = ? "
                     "WHERE c.charname = ? AND i.itemId = 65535", (amount, name))
        conn.commit()

    def test_new_character_on_the_other_pc(self):
        data = pp.save_carry(self.pc, CHAR)
        done = pp.load_carry(self.laptop, data, backup_dir=self.tmp)
        self.assertTrue(done["new"])
        self.assertNotEqual(done["charid"], CHAR)                                   # that id is taken on the laptop
        self.assertEqual(self.q(self.laptop, "SELECT accid FROM chars WHERE charname = 'Traveller'")[0][0], ACC)
        self.assertEqual(self.gil(self.laptop, "Traveller"), 1000)
        self.assertEqual(self.q(self.laptop, "SELECT COUNT(*) FROM chars WHERE charname = 'Other'")[0][0], 1)
        self.assertEqual(self.q(self.pc, "SELECT accid FROM chars WHERE charid = ?", (CHAR,))[0][0], ACC)   # nothing is locked at home
        items = [r[0] for r in self.q(self.laptop, "SELECT itemId FROM char_inventory WHERE charid = ?", (done["charid"],))]
        self.assertNotIn(515, items)                                                # linkshell items stay home

    def test_newer_copy_replaces_and_keeps_a_backup(self):
        first = pp.load_carry(self.laptop, pp.save_carry(self.pc, CHAR), backup_dir=self.tmp)
        self.set_gil(self.laptop, "Traveller", 5555)                                # played on the laptop
        back = pp.load_carry(self.pc, pp.save_carry(self.laptop, first["charid"]), backup_dir=self.tmp)
        self.assertFalse(back["new"])
        self.assertEqual(back["charid"], CHAR)
        self.assertEqual(self.gil(self.pc, "Traveller"), 5555)
        self.assertTrue(back["backup"] and os.path.exists(back["backup"]))
        items = [r[0] for r in self.q(self.pc, "SELECT itemId FROM char_inventory WHERE charid = ?", (CHAR,))]
        self.assertIn(515, items)                                                   # the PC's own linkshell item is still there
        with open(back["backup"], "rb") as handle:
            pp.restore_backup(self.pc, handle.read())
        self.assertEqual(self.gil(self.pc, "Traveller"), 1000)

    def test_squad_travels_both_ways(self):
        ct.make_squad(self.pc, CHAR, [(1, "Momo", 3, 20), (2, "Kasumi", 6, 18)])
        first = pp.load_carry(self.laptop, pp.save_carry(self.pc, CHAR))
        names = [r[0] for r in self.q(self.laptop, "SELECT name FROM squad_mate WHERE charid = ? ORDER BY slot", (first["charid"],))]
        self.assertEqual(names, ["Momo", "Kasumi"])
        pp.load_carry(self.pc, pp.save_carry(self.laptop, first["charid"]))
        self.assertEqual(self.q(self.pc, "SELECT COUNT(*) FROM squad_mate WHERE charid = ?", (CHAR,))[0][0], 2)

    def test_refusals(self):
        with self.assertRaises(pp.PassportError):
            pp.load_carry(self.laptop, pp.backup_character(self.pc, CHAR))          # a backup is not a carry file
        ct.make_account(self.pc, BOT_ACC, "bot5")
        ct.make_character(self.pc, BOT_ACC, BOT_CHAR, "Botty", linkshell=False)
        with self.assertRaises(pp.PassportError):
            pp.save_carry(self.pc, BOT_CHAR)                                        # bots never travel
        ct.run(self.pc, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (ACC, CHAR))
        self.pc.commit()
        with self.assertRaises(pp.PassportError):
            pp.save_carry(self.pc, CHAR)                                            # in the game
        self.assertTrue(pp.save_carry(self.pc, CHAR, stopped=True))                 # servers stopped: a stale session row

    def test_a_bot_with_the_name_makes_room(self):
        ct.make_account(self.laptop, BOT_ACC, "bot5")
        ct.make_character(self.laptop, BOT_ACC, BOT_CHAR, "Traveller", linkshell=False)
        done = pp.load_carry(self.laptop, pp.save_carry(self.pc, CHAR))
        self.assertTrue(done["new"])
        self.assertNotEqual(self.q(self.laptop, "SELECT charname FROM chars WHERE charid = ?", (BOT_CHAR,))[0][0], "Traveller")

    def test_folder_back_and_forth_without_ping_pong(self):
        say = self.lines.append
        self.assertEqual(pp.sync_out(self.pc, self.cloud, self.kit_pc, say), 1)       # STOP on the PC
        self.assertEqual(pp.sync_out(self.pc, self.cloud, self.kit_pc, say), 0)       # nothing changed: not saved again
        self.assertEqual(pp.sync_in(self.pc, self.cloud, self.kit_pc, say), 0)        # its own file is not loaded back
        self.assertEqual(pp.sync_in(self.laptop, self.cloud, self.kit_laptop, say), 1)    # PLAY on the laptop
        self.assertEqual(pp.sync_in(self.laptop, self.cloud, self.kit_laptop, say), 0)
        saved = pp.sync_out(self.laptop, self.cloud, self.kit_laptop, say)            # STOP on the laptop, nothing played:
        self.assertEqual(saved, 1)                                                   # only its own "Other" is new to the folder
        self.assertEqual(pp.sync_in(self.pc, self.cloud, self.kit_pc, say), 1)        # "Other" arrives on the PC, Traveller untouched
        self.set_gil(self.laptop, "Traveller", 777)
        self.assertEqual(pp.sync_out(self.laptop, self.cloud, self.kit_laptop, say), 1)
        self.assertEqual(pp.sync_in(self.pc, self.cloud, self.kit_pc, say), 1)
        self.assertEqual(self.gil(self.pc, "Traveller"), 777)
        self.assertEqual(pp.sync_out(self.pc, self.cloud, self.kit_pc, say), 0)

    def test_a_bad_file_does_not_stop_the_others(self):
        with open(os.path.join(self.cloud, "Broken" + pp.CARRY_EXT), "wb") as handle:
            handle.write(b"not a zip")
        pp.sync_out(self.pc, self.cloud, self.kit_pc, self.lines.append)
        self.assertEqual(pp.sync_in(self.laptop, self.cloud, self.kit_laptop, self.lines.append), 1)
        self.assertTrue(any("Broken" in line for line in self.lines))


if __name__ == "__main__":
    unittest.main()
