import http.client
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Catalog, GameBridge, MAX_IMPORT, PACK


class GameBridgeOpenTest(unittest.TestCase):
    # (2026-11-26) "/vanasync open" in game: the add-on's snapshot carries "open": true
    SNAPSHOT = b'{"v":1,"engaged":false,"cutscene":false,"members":1,"alliance":false,"zone":230,"open":true}'

    def test_only_a_real_open_flag_counts_and_the_snapshot_is_unchanged(self):
        self.assertTrue(GameBridge.asks_open(self.SNAPSHOT))
        self.assertFalse(GameBridge.asks_open(self.SNAPSHOT.replace(b',"open":true', b'')))
        self.assertFalse(GameBridge.asks_open(b'{"v":1,"open":"true"}'))
        self.assertFalse(GameBridge.asks_open(b'["open", true]'))
        self.assertFalse(GameBridge.asks_open(b'not json "open"'))
        state = GameBridge.parse(self.SNAPSHOT)
        self.assertEqual(state["zone"], 230)
        self.assertNotIn("open", state)

    def test_taken_once_and_page_age(self):
        bridge = GameBridge(0)
        self.assertFalse(bridge.take_open())
        bridge.open_asked = True
        self.assertTrue(bridge.take_open())
        self.assertFalse(bridge.take_open())
        self.assertIsNone(bridge.page_age())
        bridge.seen_page()
        self.assertLess(bridge.page_age(), 1)


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.addCleanup(self.data.cleanup)
        self.catalog = Catalog(Path(self.data.name))

    def test_identity_survives_rename_and_ambiguous_entries_fail_closed(self):
        track_id = self.catalog.add("戦闘・A.Final.MP3", 3, io.BytesIO(b"abc"))
        track = self.catalog.find(track_id)
        track.rename(track.with_name("戦闘・新名.MP3"))
        self.assertEqual(self.catalog.list(), {track_id: "戦闘・新名.MP3"})
        track.write_bytes(b"another file")
        self.assertIsNone(self.catalog.find(track_id))
        track.unlink()
        self.assertEqual(self.catalog.find(track_id).read_bytes(), b"abc")

    def test_invalid_names_sizes_and_partial_data(self):
        for name in ("../a.mp3", "C:\\a.mp3", "NUL.mp3", "CON .mp3", "a.html", "a.mp3."):
            with self.assertRaises(ValueError, msg=name):
                self.catalog.add(name, 1, io.BytesIO(b"x"))
        for size in (0, MAX_IMPORT + 1, 2):
            with self.assertRaises(ValueError):
                self.catalog.add("ok.mp3", size, io.BytesIO(b"x"))
        self.assertEqual(self.catalog.list(), {})
        self.assertEqual(list(self.catalog.tracks.iterdir()), [])

    def test_hardlinked_track_is_not_served(self):
        track_id = self.catalog.add("track.mp3", 1, io.BytesIO(b"x"))
        target = self.catalog.find(track_id)
        link = Path(self.data.name) / "elsewhere.mp3"
        link.hardlink_to(target)
        self.assertIsNone(self.catalog.find(track_id))

    @unittest.skipUnless(PACK.is_dir(), "Source-only build")
    def test_bundled_tracks_seed_once_under_stable_ids(self):
        defaults = self.catalog.seed_battle_pack()
        self.assertEqual(set(defaults), {"solo", "party", "alliance"})
        # (2026-11-26) the extras (Choose to Fight, J's in-game fishing and Ventures tunes) are in the catalog too, under no slot
        listed = self.catalog.list()
        self.assertTrue(set(defaults.values()) <= set(listed))
        extra = sorted(name for track, name in listed.items() if track not in defaults.values())
        self.assertEqual(extra, ["Beyond the Next Hill.mp3", "Choose to Fight (Special Battle Theme XIFO Exclusive).mp3",
                                 "Just One More Cast.mp3"])
        original = self.catalog.find(defaults["solo"])
        original.rename(original.with_name("My Solo.mp3"))
        self.assertEqual(self.catalog.seed_battle_pack(), defaults)
        self.assertEqual(self.catalog.find(defaults["solo"]).name, "My Solo.mp3")


class HTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.data.cleanup)
        script = Path(__file__).resolve().parents[1] / "server.py"
        cls.server = subprocess.Popen(
            [sys.executable, str(script), "--port", "0", "--no-open", "--no-bundled",
             "--data", cls.data.name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        cls.addClassCleanup(cls.shutdown)
        line = cls.server.stdout.readline()
        cls.origin = line.strip().split()[-1]
        cls.port = urlsplit(cls.origin).port

    @classmethod
    def shutdown(cls):
        cls.server.terminate()
        cls.server.communicate(timeout=5)

    def request(self, path, method="GET", headers=None, payload=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            conn.request(method, path, body=payload, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def test_origin_rebinding_path_and_content_guards(self):
        self.assertEqual(self.request("/", headers={"Host": "outside.example"})[0], 403)
        self.assertEqual(self.request("/", headers={"Origin": "null"})[0], 403)
        self.assertEqual(self.request("/api/tracks", "POST")[0], 403)
        self.assertEqual(self.request("/media/../../server.py")[0], 404)
        self.assertEqual(self.request("/media/%2e%2e%2fserver.py")[0], 404)
        self.assertEqual(self.request("/server.py")[0], 404)
        status, headers, _ = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_unicode_upload_and_media_range_requests(self):
        import json
        name = "出陣・Battle.Mix.MP3"
        headers = {"Origin": self.origin, "X-VanaSync": "1", "X-Filename": quote(name),
                   "Content-Type": "application/octet-stream"}
        status, _, body = self.request("/api/tracks", "POST", headers, b"123456")
        self.assertEqual(status, 201)
        record = json.loads(body)
        self.assertEqual(record["filename"], name)
        path = "/media/" + record["id"]
        self.assertEqual(self.request(path, "HEAD")[2], b"")
        status, headers, body = self.request(path, headers={"Range": "bytes=2-3"})
        self.assertEqual((status, headers["Content-Range"], body), (206, "bytes 2-3/6", b"34"))
        self.assertEqual(self.request(path, headers={"Range": "bytes=-2"})[2], b"56")
        self.assertEqual(self.request(path, headers={"Range": "bytes=8-"})[0], 416)


if __name__ == "__main__":
    unittest.main()
