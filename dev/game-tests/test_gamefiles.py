"""Stand-in tests for launcher_gamefiles.py (no Windows, no GitHub): python test_gamefiles.py [kit folder]"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, sys.argv.pop(1) if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", ".."))
import launcher_gamefiles as gf   # noqa: E402
import launcher_setup as ls       # noqa: E402


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def read(path):
    with open(path, "rb") as handle:
        return handle.read()


class GameFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        j = lambda *p: os.path.join(self.tmp, *p)   # noqa: E731
        # the updated game (what the release is built from)
        self.new_f, self.new_v = j("new", "FINAL FANTASY XI"), j("new", "PlayOnlineViewer")
        put(os.path.join(self.new_f, "FFXiMain.dll"), b"main-2026")
        put(os.path.join(self.new_f, "ROM", "0", "0.DAT"), b"same in both")
        put(os.path.join(self.new_f, "ROM", "1", "1.DAT"), b"updated dat" * 50)
        put(os.path.join(self.new_f, "ROM", "1", "2.DAT"), b"era replaces this, updated")
        put(os.path.join(self.new_f, "ROM9", "0", "0.DAT"), b"a whole new ROM folder" * 40)
        put(os.path.join(self.new_f, "USER", "1234", "mcr.dat"), b"the builder's own macros")
        put(os.path.join(self.new_f, "debug.log"), b"noise")
        put(os.path.join(self.new_v, "polcore.dll"), b"polcore-2026")
        put(os.path.join(self.new_v, "usr", "all", "login_w.bin"), b"builder's account")
        # the 2019 install (base) = the player's fresh install
        self.base_f, self.base_v = j("player", "FINAL FANTASY XI"), j("player", "PlayOnlineViewer")
        put(os.path.join(self.base_f, "FFXiMain.dll"), b"main-2019")
        put(os.path.join(self.base_f, "ROM", "0", "0.DAT"), b"same in both")
        put(os.path.join(self.base_f, "ROM", "1", "1.DAT"), b"old dat")
        put(os.path.join(self.base_f, "ROM", "1", "2.DAT"), b"era replaces this, old")
        put(os.path.join(self.base_f, "USER", "9999", "mcr.dat"), b"the player's macros")
        put(os.path.join(self.base_v, "polcore.dll"), b"polcore-2019")
        put(os.path.join(self.base_v, "usr", "all", "login_w.bin"), b"player's account")
        self.out, self.kit = j("out"), j("kit")
        os.makedirs(self.kit)
        self.base_copy = j("base2019")
        shutil.copytree(self.base_f, self.base_copy)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, **kw):
        return gf.build(self.new_f, self.new_v, self.out, "game-2026-11", log=lambda *_: None, game_build=(2026, 11, 2), **kw)

    def fake_download(self, got):
        def download(url, path, log=None, context=None):
            got.append(url)
            shutil.copy(os.path.join(self.out, url.rsplit("/", 1)[-1]), path)
            return path
        return download

    def test_build_skips_own_settings_and_logs(self):
        manifest = self.build()
        paths = {f["path"] for f in manifest["files"]}
        self.assertIn("ffxi/ROM9/0/0.DAT", paths)
        self.assertIn("viewer/polcore.dll", paths)
        self.assertFalse(any("/USER/" in p or "/usr/" in p or p.endswith(".log") for p in paths))
        self.assertEqual(manifest["game_build"], [2026, 11, 2])
        with open(os.path.join(self.out, "gamefiles.json")) as handle:
            self.assertEqual(json.load(handle)["tag"], "game-2026-11")

    def test_base_puts_changed_files_in_their_own_bundles(self):
        manifest = self.build(base_dir=self.base_copy, limit=600)
        by_name = {b["name"]: b for b in manifest["bundles"]}
        for f in manifest["files"]:
            if f["path"] == "ffxi/ROM/0/0.DAT":
                self.assertFalse(by_name[f["bundle"]]["new"])
            if f["path"] in ("ffxi/ROM/1/1.DAT", "ffxi/ROM9/0/0.DAT", "ffxi/FFXiMain.dll"):
                self.assertTrue(by_name[f["bundle"]]["new"])
        self.assertGreater(len(manifest["bundles"]), 2)        # the small limit splits them

    def test_dates_mark_changed_files_without_a_base(self):
        old = 1171611490                                    # 2007, as the installer leaves its files
        for root, _dirs, names in os.walk(self.new_f):
            for name in names:
                os.utime(os.path.join(root, name), (old, old))
        os.utime(os.path.join(self.new_f, "ROM", "1", "1.DAT"), None)       # written by an update (now)
        manifest = self.build(limit=600)
        by_name = {b["name"]: b for b in manifest["bundles"]}
        new = {f["path"] for f in manifest["files"] if by_name[f["bundle"]]["new"]}
        self.assertIn("ffxi/ROM/1/1.DAT", new)
        self.assertNotIn("ffxi/ROM/0/0.DAT", new)
        self.assertIn("viewer/polcore.dll", new)            # the viewer's files kept today's date

    def test_update_fresh_install(self):
        manifest = self.build(base_dir=self.base_copy, limit=600)
        got = []
        n = gf.update(self.kit, self.base_f, self.base_v, log=lambda *_: None, manifest=manifest,
                      download=self.fake_download(got))
        self.assertEqual(read(os.path.join(self.base_f, "FFXiMain.dll")), b"main-2026")
        self.assertEqual(read(os.path.join(self.base_f, "ROM9", "0", "0.DAT")), b"a whole new ROM folder" * 40)
        self.assertEqual(read(os.path.join(self.base_v, "polcore.dll")), b"polcore-2026")
        # the player's own settings are untouched, the builder's never arrive
        self.assertEqual(read(os.path.join(self.base_f, "USER", "9999", "mcr.dat")), b"the player's macros")
        self.assertFalse(os.path.exists(os.path.join(self.base_f, "USER", "1234")))
        self.assertEqual(read(os.path.join(self.base_v, "usr", "all", "login_w.bin")), b"player's account")
        # the bundle that holds only unchanged files was never downloaded
        unchanged = [b["name"] for b in manifest["bundles"] if not b["new"]]
        self.assertTrue(unchanged)
        self.assertFalse(any(u.endswith(name) for u in got for name in unchanged))
        self.assertTrue(all(u.startswith("https://github.com/Hurami89/xi-forever-gamefiles/releases/download/game-2026-11/") for u in got))
        self.assertEqual(n, 5)
        self.assertFalse(os.path.exists(os.path.join(self.kit, "downloads", "gamefiles", "game-2026-11")))
        # a second run finds nothing to do
        self.assertEqual(gf.update(self.kit, self.base_f, self.base_v, log=lambda *_: None, manifest=manifest,
                                   download=self.fake_download([])), 0)

    def test_era_files_stay_and_their_originals_update(self):
        manifest = self.build()
        backup = os.path.join(self.kit, "dat-backup")
        put(os.path.join(backup, "ROM", "1", "2.DAT"), b"era replaces this, old")   # saved retail original
        put(os.path.join(self.base_f, "ROM", "1", "2.DAT"), b"ERA FILE")             # the era file in the game
        put(os.path.join(self.base_f, "ROM9", "0", "0.DAT"), b"ERA ADDED")           # a file the Era-DATs added
        put(os.path.join(backup, "new-files.txt"), os.path.join("ROM9", "0", "0.DAT").encode() + b"\n")
        gf.update(self.kit, self.base_f, self.base_v, log=lambda *_: None, manifest=manifest, download=self.fake_download([]))
        self.assertEqual(read(os.path.join(self.base_f, "ROM", "1", "2.DAT")), b"ERA FILE")
        self.assertEqual(read(os.path.join(backup, "ROM", "1", "2.DAT")), b"era replaces this, updated")
        self.assertEqual(read(os.path.join(self.base_f, "ROM9", "0", "0.DAT")), b"ERA ADDED")
        self.assertEqual(read(os.path.join(self.base_f, "ROM", "1", "1.DAT")), b"updated dat" * 50)

    def test_bad_download_is_refused_and_removed(self):
        manifest = self.build()

        def broken(url, path, log=None, context=None):
            put(path, b"not the bundle")
            return path
        with self.assertRaises(RuntimeError):
            gf.update(self.kit, self.base_f, self.base_v, log=lambda *_: None, manifest=manifest, download=broken)
        self.assertEqual(read(os.path.join(self.base_f, "FFXiMain.dll")), b"main-2019")
        name = manifest["bundles"][0]["name"]
        self.assertFalse(os.path.exists(os.path.join(self.kit, "downloads", "gamefiles", "game-2026-11", name)))

    def test_not_enough_space(self):
        manifest = self.build()
        with self.assertRaises(RuntimeError) as caught:
            gf.update(self.kit, self.base_f, self.base_v, log=lambda *_: None, manifest=manifest,
                      download=self.fake_download([]), free=lambda _p: 10)
        self.assertIn("disk space", str(caught.exception))

    def test_setup_falls_back_when_the_release_is_unreachable(self):
        put(os.path.join(self.base_f, "ROM", "0", "0.DAT"), b"x")
        lines = []

        def offline(*a, **k):
            raise OSError("no internet")
        import launcher_game as lg
        old = lg.find_viewer
        lg.find_viewer = lambda *_a, **_k: self.base_v
        try:
            self.assertFalse(ls.update_game_files(self.kit, self.base_f, log=lines.append, update=offline))
            self.assertTrue(any("PlayOnline can update it" in line for line in lines))
            self.assertTrue(ls.update_game_files(self.kit, self.base_f, log=lines.append, update=lambda *a, **k: 3))
        finally:
            lg.find_viewer = old


if __name__ == "__main__":
    unittest.main()
