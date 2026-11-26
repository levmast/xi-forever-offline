"""Character cards (launcher_charcards.py): the slot order, the one-launch autologin block, the cache, the addon copy.
Run: python dev/launcher-tests/test_charcards.py"""
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
import launcher_charcards as cc  # noqa: E402


def world(rows, content_ids=3):
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE accounts (id INTEGER, login TEXT, content_ids INTEGER);
        CREATE TABLE chars (charid INTEGER, accid INTEGER, charname TEXT, nation INTEGER, pos_zone INTEGER, playtime INTEGER);
        CREATE TABLE char_stats (charid INTEGER, mjob INTEGER, sjob INTEGER, mlvl INTEGER, slvl INTEGER);
        CREATE TABLE char_look (charid INTEGER, race INTEGER, face INTEGER);
        CREATE TABLE char_jobs (charid INTEGER);
        CREATE TABLE char_vars (charid INTEGER, varname TEXT, value INTEGER);
        CREATE TABLE zone_settings (zoneid INTEGER, name TEXT);
    """)
    db.execute("INSERT INTO accounts VALUES (1, 'me', ?)", (content_ids,))
    db.execute("INSERT INTO accounts VALUES (2, 'other', 3)")
    db.execute("INSERT INTO zone_settings VALUES (240, 'Port_Windurst')")
    for charid, accid, name, stats in rows:
        db.execute("INSERT INTO chars VALUES (?, ?, ?, 2, 240, 7200)", (charid, accid, name))
        if stats:
            db.execute("INSERT INTO char_stats VALUES (?, 4, 5, 37, 18)", (charid,))
        db.execute("INSERT INTO char_look VALUES (?, 6, 4)", (charid,))
        db.execute("INSERT INTO char_jobs VALUES (?)", (charid,))
    return db


class Fetch(unittest.TestCase):
    def test_slots_follow_charid_like_the_login_server(self):
        db = world([(30, 1, "Cee", True), (10, 1, "Aye", True), (20, 2, "NotMine", True), (25, 1, "Bee", True)])
        got = cc.fetch(db, "me")
        self.assertEqual([(c["slot"], c["name"]) for c in got], [(0, "Aye"), (1, "Bee"), (2, "Cee")])
        self.assertEqual(got[0]["zone_name"], "Port Windurst")
        self.assertEqual(cc.job_line(got[0]), "BLM 37 / RDM 18")

    def test_a_character_the_login_list_leaves_out_takes_no_slot(self):
        db = world([(10, 1, "Aye", True), (11, 1, "Broken", False), (12, 1, "Cee", True)])
        self.assertEqual([c["name"] for c in cc.fetch(db, "me")], ["Aye", "Cee"])

    def test_only_as_many_as_the_account_has_content_ids(self):
        db = world([(10, 1, "Aye", True), (11, 1, "Bee", True), (12, 1, "Cee", True)], content_ids=2)
        self.assertEqual(len(cc.fetch(db, "me")), 2)

    def test_hardcore_mode_shows(self):
        db = world([(10, 1, "Aye", True)])
        db.execute("INSERT INTO char_vars VALUES (10, '[HC]Mode', 3)")
        self.assertEqual(cc.fetch(db, "me")[0]["hc"], 3)

    def test_unknown_account(self):
        self.assertEqual(cc.fetch(world([]), "nobody"), [])


class Script(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "xiforever.txt")
        with open(self.path, "w") as f:
            f.write("/load thirdparty\n/addon load servermenu\n/wait 10\n")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self):
        with open(self.path) as f:
            return f.read().splitlines()

    def test_block_goes_first_and_is_replaced_and_removed(self):
        # a script without "/load addons": the block brings it, first of all
        cc.set_autologin(self.path, 2)
        lines = self.read()
        self.assertEqual(lines[:4], [cc.BEGIN, "/load addons", "/addon load autologin 2", cc.END])
        self.assertEqual(lines[4:], ["/load thirdparty", "/addon load servermenu", "/wait 10"])
        cc.set_autologin(self.path, 0)
        self.assertEqual(self.read().count("/addon load autologin 0"), 1)
        self.assertNotIn("/addon load autologin 2", self.read())
        cc.set_autologin(self.path, None)
        self.assertEqual(self.read(), ["/load thirdparty", "/addon load servermenu", "/wait 10"])

    def test_block_goes_after_load_addons(self):
        # (2026-11-25) /addon only works once the add-on loader is up: the block sits right after "/load addons"
        with open(self.path, "w") as f:
            f.write("/load thirdparty\n/load addons\n/addon load servermenu\n/wait 10\n")
        cc.set_autologin(self.path, 3)
        self.assertEqual(self.read(), ["/load thirdparty", "/load addons", cc.BEGIN, "/addon load autologin 3", cc.END,
                                       "/addon load servermenu", "/wait 10"])
        cc.set_autologin(self.path, None)
        self.assertEqual(self.read(), ["/load thirdparty", "/load addons", "/addon load servermenu", "/wait 10"])

    def test_missing_script(self):
        self.assertFalse(cc.set_autologin(os.path.join(self.dir, "none.txt"), 1))


class CacheAndAddon(unittest.TestCase):
    def test_cache_per_login(self):
        d = tempfile.mkdtemp()
        try:
            cc.save_cache(d, "Me", [{"slot": 0, "name": "Aye"}])
            cc.save_cache(d, "other", [{"slot": 0, "name": "Zed"}])
            self.assertEqual(cc.load_cache(d, "me")[0]["name"], "Aye")
            self.assertEqual(cc.load_cache(d, "nobody"), [])
        finally:
            shutil.rmtree(d)

    def test_addon_copied_only_when_missing(self):
        d = tempfile.mkdtemp()
        try:
            self.assertTrue(cc.ensure_addon(KIT, d))
            path = os.path.join(d, "addons", "autologin", "autologin.lua")
            self.assertTrue(os.path.isfile(path))
            with open(path, "w") as f:
                f.write("-- a newer stock one")
            self.assertTrue(cc.ensure_addon(KIT, d))
            with open(path) as f:
                self.assertEqual(f.read(), "-- a newer stock one")
        finally:
            shutil.rmtree(d)

    def test_face_files(self):
        self.assertTrue(cc.face_path({"race": 6, "face": 4}).endswith(os.path.join("faces", "Tf3a.jpg")))
        self.assertTrue(cc.face_path({"race": 8, "face": 15}).endswith(os.path.join("faces", "G8b.jpg")))


if __name__ == "__main__":
    unittest.main()
