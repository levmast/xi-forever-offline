"""LoFi FFXI music (2026-11-23, datadecay): a DIRECT pack in launcher_hd, downloaded from its author's GitHub archive
of one pinned commit, unpacked into polplugins/DATs/LoFi-FFXI and left OFF (not in pivot.ini) until the player turns
it on; the download is deleted after. Run: python3 dev/launcher-tests/test_lofi.py"""
import io
import os
import sys
import tempfile
import unittest
import zipfile

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
import launcher_hd as hd  # noqa: E402


class LofiTests(unittest.TestCase):
    def test_download_installs_switched_off(self):
        pack = [p for p in hd.DIRECT if p["id"] == "lofi"][0]
        self.assertEqual(len(pack["ref"]), 40)                          # pinned to a commit, not a moving branch
        kit, ashita = tempfile.mkdtemp(), tempfile.mkdtemp()
        top = "LoFi-FFXI-" + pack["ref"]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr(top + "/README.md", "hi")
            z.writestr(top + "/sound/win/music/data/music107.bgw", "sandy")
            z.writestr(top + "/sound2/win/music/data/music200.bgw", "x")
        urls = []

        def fetch(url, timeout=60):
            urls.append(url)
            return buf.getvalue()
        hd.write_overlays(ashita, ["NextHD"])
        done = hd.download_direct(pack, kit, ashita, log=lambda line: None, fetch=fetch)
        self.assertEqual(urls, [f"https://github.com/CatsAndBoats/LoFi-FFXI/archive/{pack['ref']}.zip"])
        self.assertEqual([d["name"] for d in done], ["LoFi-FFXI"])
        self.assertTrue(os.path.isfile(os.path.join(hd.dats_dir(ashita), "LoFi-FFXI", "sound", "win", "music", "data", "music107.bgw")))
        self.assertEqual(hd.read_overlays(ashita), ["NextHD"])          # off: the player turns it on
        listed = {p["name"]: p["on"] for p in hd.installed(ashita)}
        self.assertEqual(listed.get("LoFi-FFXI"), False)
        self.assertEqual(os.listdir(os.path.join(kit, "downloads", "packs")), [])
        hd.set_on(ashita, "LoFi-FFXI", True)
        self.assertEqual(hd.read_overlays(ashita), ["NextHD", "LoFi-FFXI"])

    def test_window_offers_it(self):
        gui = open(os.path.join(KIT, "launcher_hd_gui.py"), encoding="utf-8").read()
        self.assertIn("for pack in hd.DIRECT:", gui)
        self.assertIn("hd.download_direct(pack, kit, ashita", gui)


if __name__ == "__main__":
    unittest.main(verbosity=2)
