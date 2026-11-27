"""The launcher puts the in-game Ventures window into Ashita and does NOT start it with the game (the Squads menu's
Ventures button loads it; see test_venture_button.py). The first build switched it on once: that is taken back once.
    python3 dev/ventures/test_venture_install.py
"""
import os
import shutil
import sys
import tempfile
import time
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
import launcher_setup as S  # noqa: E402


def write(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


class Install(unittest.TestCase):
    def setUp(self):
        self.kit, self.ashita = tempfile.mkdtemp(), tempfile.mkdtemp()
        write(os.path.join(self.kit, "addons-src", "venture", "venture.lua"), "-- venture")
        write(os.path.join(self.kit, "addons-src", "venture", "assets", "bg", "ronfaure.png"), "picture one")
        write(os.path.join(self.kit, "addons-src", "venture", "venture.lua.before-x"), "old")
        write(os.path.join(self.ashita, "config", "boot", "phoenixsolo.ini"), "[ashita.boot]\nscript      = default.txt\n")
        write(os.path.join(self.ashita, "scripts", "default.txt"), "/load addons\n/addon load servermenu\n")
        self.said = []

    def script(self):
        names = [n for n in os.listdir(os.path.join(self.ashita, "scripts")) if n != "default.txt"]
        return read(os.path.join(self.ashita, "scripts", names[0])) if names else ""

    def test_it_is_one_of_the_kits_own_addons(self):
        self.assertIn("venture", S.OWN_ADDONS)
        with open(os.path.join(KIT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("!/addons-src/venture/", f.read().split())

    def test_copied_and_unchanged_pictures_left_alone(self):
        S.install_own_addons(self.kit, self.ashita)
        dst = os.path.join(self.ashita, "addons", "venture")
        self.assertEqual(read(os.path.join(dst, "venture.lua")), "-- venture")
        self.assertFalse(os.path.exists(os.path.join(dst, "venture.lua.before-x")))
        pic = os.path.join(dst, "assets", "bg", "ronfaure.png")
        self.assertEqual(read(pic), "picture one")
        # the same size and time: not written again (a mark put into the copy survives the next PLAY)
        stamp = os.stat(pic)
        write(pic, "PICTURE ONE")
        os.utime(pic, (stamp.st_atime, stamp.st_mtime))
        S.install_own_addons(self.kit, self.ashita)
        self.assertEqual(read(pic), "PICTURE ONE")
        # an update brings a new picture of the same size: copied
        src = os.path.join(self.kit, "addons-src", "venture", "assets", "bg", "ronfaure.png")
        write(src, "picture two")
        os.utime(src, (time.time() + 60, time.time() + 60))
        S.install_own_addons(self.kit, self.ashita)
        self.assertEqual(read(pic), "picture two")

    def marker(self, name="enabled-once.txt"):
        return os.path.join(self.ashita, "config", "addons", "venture", name)

    def test_copied_but_not_started(self):
        S.install_own_addons(self.kit, self.ashita)
        self.assertFalse(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
        self.assertEqual(self.script(), "", "the start script is not even looked at")
        self.assertEqual(self.said, [])
        self.assertFalse(os.path.exists(os.path.join(self.ashita, "config", "addons", "venture")), "and no marker is left")
        for names in (S.START_ADDONS, S.STOCK_ADDONS, S.STOCK_PLUGINS):
            self.assertNotIn("venture", [n.lower() for n in names], "a new install does not start it either")
        self.assertFalse(hasattr(S, "enable_venture"), "nothing in the launcher switches it on")
        with open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8") as f:
            gui = f.read()
        self.assertNotIn("enable_venture", gui)
        self.assertEqual(gui.count("launcher_setup.venture_off_by_default("), 1)

    def test_the_first_builds_switch_on_is_taken_back_once(self):
        import launcher_core as core
        S.install_own_addons(self.kit, self.ashita)
        manager = core.ScriptManager(self.ashita, "phoenixsolo.ini")
        manager.prepare()
        manager.set("addon", "venture", True)               # what the first build of 2026-11-26 did at PLAY
        write(self.marker(), "2026-11-26 21:40:00\n")
        self.assertIn("/addon load venture", self.script())
        self.assertTrue(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
        self.assertNotIn("venture", self.script())
        self.assertIn("/addon load servermenu", self.script(), "what else was on stays on")
        self.assertEqual(len(self.said), 1)
        self.assertIn("Ventures button", self.said[0])
        self.assertFalse(os.path.exists(self.marker()))
        self.assertTrue(os.path.exists(self.marker("off-by-default.txt")))
        self.assertFalse(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
        # the player wants it started with the game after all (OPTIONS > Addons): every later PLAY leaves it on
        manager.set("addon", "venture", True)
        for _ in range(3):
            self.assertFalse(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
        self.assertIn("/addon load venture", self.script())
        self.assertEqual(len(self.said), 1)

    def test_switched_off_by_the_player_before_the_update(self):
        import launcher_core as core
        manager = core.ScriptManager(self.ashita, "phoenixsolo.ini")
        manager.prepare()
        before = self.script()
        write(self.marker(), "2026-11-26 21:40:00\n")
        self.assertFalse(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
        self.assertEqual((self.script(), self.said), (before, []), "nothing to take out: nothing is changed or said")
        self.assertFalse(os.path.exists(self.marker()), "and it is not looked at again")

    def test_a_marker_that_cannot_be_renamed(self):
        import launcher_core as core
        manager = core.ScriptManager(self.ashita, "phoenixsolo.ini")
        manager.prepare()
        manager.set("addon", "venture", True)
        write(self.marker(), "2026-11-26 21:40:00\n")
        replace = os.replace

        def refuse(a, b):
            if a == self.marker():
                raise PermissionError(13, "in use")
            return replace(a, b)
        os.replace = refuse
        try:
            self.assertTrue(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
            manager.set("addon", "venture", True)           # the player's own choice, later
            self.assertFalse(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))
        finally:
            os.replace = replace
        self.assertIn("/addon load venture", self.script(), "taken back once, even while the first marker cannot be renamed")
        self.assertTrue(os.path.exists(self.marker()) and os.path.exists(self.marker("off-by-default.txt")))

    def test_no_boot_file(self):
        """An Ashita without the boot file: the launcher's PLAY step says so and goes on (it catches this)."""
        write(self.marker(), "x")
        os.remove(os.path.join(self.ashita, "config", "boot", "phoenixsolo.ini"))
        with self.assertRaises(FileNotFoundError):
            S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append)
        self.assertTrue(os.path.exists(self.marker()), "left for the next PLAY")

    def test_a_kit_without_the_window(self):
        shutil.rmtree(os.path.join(self.kit, "addons-src", "venture"))
        S.install_own_addons(self.kit, self.ashita)
        self.assertFalse(os.path.exists(os.path.join(self.ashita, "addons", "venture")))
        self.assertFalse(S.venture_off_by_default(self.ashita, "phoenixsolo.ini", log=self.said.append))


if __name__ == "__main__":
    unittest.main(verbosity=1)
