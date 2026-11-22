"""launcher_gamepad: the controller values the launcher writes into the Ashita boot file (2026-11-22)."""
import os
import shutil
import sys
import tempfile
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
import launcher_gamepad as g   # noqa: E402

RETAIL_SETUP_E = "8,9,13,12,10,0,1,3,2,15,-1,-1,14,-33,-33,32,32,-36,-36,35,35,6,7,5,4,11,-1"
BOOT = """[ashita.boot]
command   = .\\bootloader\\xiloader.exe --server 127.0.0.1

[ashita.input]
gamepad.allowbackground         = 0
gamepad.disableenumeration      = 0
keyboard.windowskeyenabled      = 0

[ffxi.registry]
0001 = 1920
padguid000 = -1
padmode000 = -1
padsin000 = -1

[ashita.misc]
addons = 1
"""


class Values(unittest.TestCase):
    def test_xbox_is_retail_setup_e(self):
        v = g.clean({"managed": True})
        self.assertEqual(g.pad_buttons(v), RETAIL_SETUP_E)
        self.assertEqual(g.pad_mode(v), "1,1,0,0,0,1")

    def test_confirm_on_right_swaps_only_confirm_and_cancel(self):
        a = g.pad_buttons(g.clean({"managed": True})).split(",")
        b = g.pad_buttons(g.clean({"managed": True, "confirm_right": True})).split(",")
        self.assertEqual((b[5], b[7]), (a[7], a[5]))
        self.assertEqual([x for i, x in enumerate(a) if i not in (5, 7)], [x for i, x in enumerate(b) if i not in (5, 7)])

    def test_playstation_direct_and_through_steam(self):
        own = g.clean({"managed": True, "type": "ps5"})
        self.assertFalse(g.uses_xinput(own))
        self.assertTrue(g.pad_mode(own).endswith(",0"))
        self.assertEqual(g.pad_buttons(own).split(",")[7], "1")          # Cross confirms
        steam = g.clean({"managed": True, "type": "ps5", "steam_input": True})
        self.assertEqual(g.pad_buttons(steam), RETAIL_SETUP_E)

    def test_invert_camera_flips_only_the_camera_up_down(self):
        a = g.pad_buttons(g.clean({"managed": True})).split(",")
        b = g.pad_buttons(g.clean({"managed": True, "invert_camera": True})).split(",")
        self.assertEqual(b[17:19], ["36", "36"])
        self.assertEqual(a[:17] + a[19:], b[:17] + b[19:])

    def test_own_button_choice_and_bad_ones_dropped(self):
        v = g.clean({"managed": True, "buttons": {"25": 13, "13": 3, "6": 999, "x": 1}})
        self.assertEqual(v["buttons"], {25: 13})                           # stick slot, unknown button, junk: dropped
        self.assertEqual(g.pad_buttons(v).split(",")[25], "13")

    def test_off_and_junk(self):
        self.assertEqual(g.pad_mode(g.clean({"managed": True, "enabled": False})), "0,0,0,0,0,0")
        v = g.clean({"type": "gamecube", "vibration": "yes", "buttons": None})
        self.assertEqual(v["type"], "xbox")
        self.assertEqual(len(g.pad_buttons(v).split(",")), g.SLOTS)


class BootFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ini = os.path.join(self.dir, "xiforever.ini")
        with open(self.ini, "w", encoding="utf-8", newline="") as f:
            f.write(BOOT.replace("\n", "\r\n"))

    def tearDown(self):
        shutil.rmtree(self.dir)

    def read(self):
        with open(self.ini, "r", encoding="utf-8", newline="") as f:
            return f.read()

    def test_unmanaged_never_touches_the_file(self):
        changed, _ = g.apply(self.ini, {})
        self.assertFalse(changed)
        self.assertFalse(os.path.exists(self.ini + ".before-gamepad"))

    def test_managed_writes_only_its_keys(self):
        changed, saved = g.apply(self.ini, {"managed": True, "background": True})
        self.assertTrue(changed and saved["applied"])
        text = self.read()
        self.assertIn("\r\n", text)
        self.assertIn(f"padsin000 = {RETAIL_SETUP_E}", text)
        self.assertIn("padmode000 = 1,1,0,0,1,1", text)
        self.assertIn("gamepad.allowbackground         = 1", text)
        before, after = BOOT.splitlines(), text.splitlines()
        self.assertEqual(len(before), len(after))
        diff = [b for b, a in zip(before, after) if b != a]
        self.assertEqual(sorted(l.split("=")[0].strip() for l in diff), ["gamepad.allowbackground", "padmode000", "padsin000"])
        self.assertTrue(os.path.exists(self.ini + ".before-gamepad"))

    def test_switching_off_gives_the_game_its_own_back(self):
        _, saved = g.apply(self.ini, {"managed": True})
        saved["managed"] = False
        changed, saved = g.apply(self.ini, saved)
        self.assertTrue(changed)
        self.assertFalse(saved["applied"])
        self.assertEqual(self.read().replace("\r\n", "\n"), BOOT)
        self.assertFalse(g.apply(self.ini, saved)[0])                    # and after that it is left alone

    def test_missing_keys_and_section_are_added(self):
        with open(self.ini, "w", encoding="utf-8") as f:
            f.write("[ffxi.registry]\n0001 = 1920\n\n[ashita.misc]\naddons = 1\n")
        g.apply(self.ini, {"managed": True})
        text = self.read()
        self.assertEqual(g.read_boot(self.ini), ("1,1,0,0,0,1", RETAIL_SETUP_E))
        self.assertLess(text.index("padsin000"), text.index("[ashita.misc]"))
        self.assertIn("[ashita.input]", text)

    def test_json_round_trip(self):
        g.save(self.dir, {"managed": True, "type": "ps4", "buttons": {25: 13}})
        self.assertEqual(g.load(self.dir)["buttons"], {25: 13})
        self.assertEqual(g.load(os.path.join(self.dir, "nothing"))["managed"], False)


if __name__ == "__main__":
    unittest.main()
