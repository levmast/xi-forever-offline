"""XISpeaks through the Downloads list (2026-11-23): one release in three big .zip files, each checked against the
release's SHA256SUMS.txt, unpacked file by file into Ashita's addons folder, deleted after; the player's voice database
is kept; nothing is downloaded without a confirmation. Run: python3 dev/launcher-tests/test_xispeaks.py"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
os.environ["XIFO_TEST_PLATFORM"] = "windows"
import launcher_thirdparty as tp  # noqa: E402


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class XISpeaksTests(unittest.TestCase):
    def setUp(self):
        self.item = [i for i in tp.load_manifest(KIT, "windows") if i["id"] == "xispeaks"][0]
        base = "https://github.com/lord-daeloth/XISpeaks/releases/download/v1.0.0-beta.4/XISpeaks-v1.0.0-beta.4-windows-x64"
        self.zips = {
            base + "-app.zip": make_zip({"XISpeaks/XISpeaks.lua": "addon.version = '1.0.0-beta.4'",
                                         "XISpeaks/START-XISpeaks.cmd": "@echo off",
                                         "XISpeaks/companion/XISpeaks-Companion.exe": "exe",
                                         "XISpeaks/companion/pocket-runtime/npcs.sqlite3": "NEW"}),
            base + "-voices-1.zip": make_zip({"XISpeaks/companion/voices/a.wav": "a"}),
            base + "-voices-2.zip": make_zip({"XISpeaks/companion/voices/b.wav": "b"}),
        }
        self.sums = "".join(f"{hashlib.sha256(d).hexdigest()}  {u.rsplit('/', 1)[1]}\n" for u, d in self.zips.items())
        assets = [{"name": u.rsplit("/", 1)[1], "browser_download_url": u, "size": 1000} for u in self.zips]
        assets.append({"name": "SHA256SUMS.txt", "browser_download_url": "SUMS", "size": 10})
        self.release = {"tag_name": "v1.0.0-beta.4", "assets": assets}
        self.fetched = []

    def fetch(self, url, timeout=60):
        self.fetched.append(url)
        if url.endswith("releases/tags/v1.0.0-beta.4"):
            return json.dumps(self.release).encode()
        if url == "SUMS":
            return self.sums.encode()
        return self.zips[url]

    def test_manifest(self):
        item = self.item
        self.assertEqual(tp.place(item), ("addon", "xispeaks"))
        self.assertIn("2.9 GB", item["confirm"])
        self.assertNotIn("required", item)
        self.assertEqual([i for i in tp.load_manifest(KIT, "linux") if i["id"] == "xispeaks"], [])   # Windows only

    def test_resolve_all_three(self):
        found = tp.resolve(self.item, self.fetch)
        self.assertEqual([p["name"][-14:] for p in found["parts"]], ["windows-x64-app.zip"[-14:], "x64-voices-1.zip"[-14:], "x64-voices-2.zip"[-14:]])
        self.assertTrue(all(p["sha256"] for p in found["parts"]))

    def test_install_keeps_your_database(self):
        kit, ashita = tempfile.mkdtemp(), tempfile.mkdtemp()
        mine = os.path.join(ashita, "addons", "XISpeaks", "companion", "pocket-runtime", "npcs.sqlite3")
        os.makedirs(os.path.dirname(mine))
        with open(mine, "w") as f:
            f.write("MINE")
        lines = []
        version = tp.install(self.item, kit, ashita, fetch=self.fetch, log=lines.append)
        self.assertEqual(version, "v1.0.0-beta.4")
        root = os.path.join(ashita, "addons", "XISpeaks")
        for rel in ("XISpeaks.lua", "companion/XISpeaks-Companion.exe", "companion/voices/a.wav", "companion/voices/b.wav"):
            self.assertTrue(os.path.isfile(os.path.join(root, rel)), rel)
        self.assertEqual(open(mine).read(), "MINE")
        folder = os.path.join(kit, "downloads", "xispeaks")
        self.assertEqual(os.listdir(folder) if os.path.isdir(folder) else [], [])        # each zip deleted after
        self.assertEqual(tp.status(self.item, kit, ashita), (True, "v1.0.0-beta.4"))
        self.assertTrue(any("part 3 of 3" in line for line in lines))

    def test_bad_checksum_stops(self):
        url = list(self.zips)[1]
        self.zips[url] = make_zip({"XISpeaks/companion/voices/evil.wav": "x"})       # not what SHA256SUMS lists
        kit, ashita = tempfile.mkdtemp(), tempfile.mkdtemp()
        with self.assertRaises(RuntimeError):
            tp.install(self.item, kit, ashita, fetch=self.fetch, log=lambda line: None)
        self.assertFalse(os.path.exists(os.path.join(ashita, "addons", "XISpeaks", "companion", "voices", "evil.wav")))
        self.assertNotIn("xispeaks", tp.load_state(kit))

    def test_path_outside_refused(self):
        tmp = tempfile.mkdtemp()
        bad = os.path.join(tmp, "bad.zip")
        with open(bad, "wb") as f:
            f.write(make_zip({"../../evil.txt": "x"}))
        with self.assertRaises(RuntimeError):
            tp.extract_zip(bad, os.path.join(tmp, "dest"))

    def test_space(self):
        parts = [{"size": 1200 << 20}, {"size": 1200 << 20}, {"size": 400 << 20}]
        with self.assertRaises(RuntimeError) as e:
            tp.check_free_space(self.item, "/", parts, free=3 << 30)
        self.assertIn("free disk space", str(e.exception))
        self.assertTrue(tp.check_free_space(self.item, "/", parts, free=20 << 30))


if __name__ == "__main__":
    unittest.main(verbosity=2)
