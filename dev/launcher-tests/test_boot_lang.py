"""Windows: an EU or JP game is named to the loader and Ashita in the boot file (launcher_game.py).

Sirloinofbeef, 2026-11-22: a Steam EU game on a PC that still had registry entries of an uninstalled US game. The
loader went for the US PlayOnline: "[fail] polcore (US) file: F:\\...\\polcore.dll doesn't exist".
Run with: python test_boot_lang.py
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import launcher_game as lg  # noqa: E402

BOOT = ("[ashita.boot]\r\n"
        "file        = .\\\\bootloader\\\\xiloader.exe\r\n"
        "command     = --server 127.0.0.1 --user hero --pass secret\r\n"
        "gamemodule  = ffximain.dll\r\n"
        "\r\n"
        "[ashita.language]\r\n"
        "playonline  = 2\r\n"
        "ashita      = 2\r\n")

STEAM_EU = r"C:\Steam\steamapps\common\FFXIEU\SquareEnix\FINAL FANTASY XI"
OLD_US = r"F:\SquareEnix\FINAL FANTASY XI"


class FakeReg:
    def __init__(self, values):
        self.values = values

    def get(self, path, name):
        return self.values.get((path, name))


def folder(key):
    return rf"SOFTWARE\{key}\InstallFolder"


class InstallLang(unittest.TestCase):
    def test_a_copy_remembers_its_language(self):
        self.assertEqual(lg.install_lang({"pol_lang": "eu", "ffxi_client_dir": "x"}, FakeReg({})), "EU")

    def test_installed_eu_game_beside_leftovers_of_a_us_one(self):
        reg = FakeReg({(folder("PlayOnlineUS"), "0001"): OLD_US, (folder("PlayOnlineEU"), "0001"): STEAM_EU})
        self.assertEqual(lg.install_lang({"ffxi_client_dir": STEAM_EU}, reg), "EU")

    def test_installed_us_game(self):
        reg = FakeReg({(folder("PlayOnlineUS"), "0001"): OLD_US})
        self.assertEqual(lg.install_lang({"ffxi_client_dir": OLD_US}, reg), "US")

    def test_unknown_when_nothing_matches(self):
        reg = FakeReg({(folder("PlayOnlineUS"), "0001"): OLD_US})
        self.assertIsNone(lg.install_lang({"ffxi_client_dir": STEAM_EU}, reg))
        self.assertIsNone(lg.install_lang({}, reg))


class ApplyBootLang(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.boot = os.path.join(self.tmp.name, "xiforever.ini")
        with open(self.boot, "w", encoding="utf-8", newline="") as handle:
            handle.write(BOOT)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        with open(self.boot, encoding="utf-8", newline="") as handle:
            return handle.read()

    def test_eu_is_named_to_the_loader_and_ashita(self):
        self.assertTrue(lg.apply_boot_lang(self.boot, "EU"))
        text = self.read()
        self.assertIn("command     = --server 127.0.0.1 --user hero --pass secret --lang EU\r\n", text)
        self.assertIn("playonline  = 3\r\n", text)
        self.assertIn("ashita      = 2\r\n", text)
        self.assertEqual(text.count("\r\n"), BOOT.count("\r\n"))       # every line keeps its ending
        with open(self.boot + lg.BOOT_LANG_BACKUP, encoding="utf-8", newline="") as handle:
            self.assertEqual(handle.read(), BOOT)                      # the boot file as it was

    def test_doing_it_again_changes_nothing(self):
        lg.apply_boot_lang(self.boot, "EU")
        before = self.read()
        self.assertFalse(lg.apply_boot_lang(self.boot, "EU"))
        self.assertEqual(self.read(), before)

    def test_jp(self):
        self.assertTrue(lg.apply_boot_lang(self.boot, "JP"))
        self.assertIn("--pass secret --lang JP\r\n", self.read())
        self.assertIn("playonline  = 1\r\n", self.read())

    def test_a_us_game_is_left_alone(self):
        self.assertFalse(lg.apply_boot_lang(self.boot, "US"))
        self.assertEqual(self.read(), BOOT)
        self.assertFalse(os.path.exists(self.boot + lg.BOOT_LANG_BACKUP))

    def test_unknown_language_changes_nothing(self):
        self.assertFalse(lg.apply_boot_lang(self.boot, None))
        self.assertEqual(self.read(), BOOT)

    def test_back_to_a_us_game_takes_the_lang_off_again(self):
        lg.apply_boot_lang(self.boot, "EU")
        self.assertTrue(lg.apply_boot_lang(self.boot, "US"))
        self.assertEqual(self.read(), BOOT)

    def test_eu_to_jp_replaces_the_lang(self):
        lg.apply_boot_lang(self.boot, "EU")
        lg.apply_boot_lang(self.boot, "JP")
        text = self.read()
        self.assertEqual(text.count("--lang"), 1)
        self.assertIn("--lang JP", text)

    def test_other_options_on_the_command_line_stay(self):
        with open(self.boot, "w", encoding="utf-8", newline="") as handle:
            handle.write(BOOT.replace("--pass secret", "--pass secret --fingerprint SHA256:abc --hide"))
        lg.apply_boot_lang(self.boot, "EU")
        self.assertIn("--pass secret --fingerprint SHA256:abc --hide --lang EU\r\n", self.read())


if __name__ == "__main__":
    unittest.main()
