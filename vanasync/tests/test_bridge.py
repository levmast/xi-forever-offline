"""Live game bridge (XI: Forever Offline add-on): UDP snapshots in, ownership out, /api/game and /api/owner."""
import http.client
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

SNAP = {"v": 1, "engaged": True, "cutscene": False, "members": 3, "alliance": False, "zone": 230}


def free_udp_port():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class ParseTest(unittest.TestCase):
    def test_valid_and_clamped(self):
        state = server.GameBridge.parse(json.dumps({**SNAP, "members": 40}).encode())
        self.assertEqual(state, {"engaged": True, "alliance": False, "cutscene": False, "members": 18, "zone": 230})

    def test_rejects_bad_snapshots(self):
        for bad in (b"nope", b"[]", json.dumps({**SNAP, "v": 2}).encode(),
                    json.dumps({**SNAP, "members": "3"}).encode(), json.dumps({**SNAP, "zone": True}).encode()):
            with self.assertRaises(ValueError):
                server.GameBridge.parse(bad)

    def test_booleans_must_be_true(self):
        state = server.GameBridge.parse(json.dumps({**SNAP, "engaged": "yes", "alliance": 1}).encode())
        self.assertFalse(state["engaged"])
        self.assertFalse(state["alliance"])


class LiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.TemporaryDirectory()
        cls.game_port = free_udp_port()
        cls.srv = server.Server(0, Path(cls.data.name), bundled=False, game_port=cls.game_port)
        cls.port = cls.srv.server_port
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cls.udp.settimeout(2)

    @classmethod
    def tearDownClass(cls):
        cls.udp.close()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.data.cleanup()

    def http(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            headers.update({"Origin": f"http://127.0.0.1:{self.port}", "X-VanaSync": "1",
                            "Content-Type": "application/json"})
            body = json.dumps(body).encode()
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read() or b"null")
        conn.close()
        return response.status, data

    def send(self, snap=SNAP):
        self.udp.sendto(json.dumps(snap).encode(), ("127.0.0.1", self.game_port))
        return json.loads(self.udp.recvfrom(1024)[0])

    def test_round_trip(self):
        self.srv.game.set_owner(False)
        self.assertEqual(self.send(), {"own": False})
        status, data = self.http("GET", "/api/game")
        self.assertEqual(status, 200)
        self.assertTrue(data["live"])
        self.assertEqual(data["state"]["members"], 3)
        self.assertTrue(data["state"]["engaged"])

        status, _ = self.http("POST", "/api/owner", {"own": True})
        self.assertEqual(status, 200)
        self.assertEqual(self.send(), {"own": True})

        # The player stops reporting (window closed, crash): ownership expires by itself.
        with self.srv.game.lock:
            self.srv.game.owner_at -= server.GameBridge.OWNER_FRESH + 0.1
        self.assertEqual(self.send(), {"own": False})

    def test_owner_needs_local_origin(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/api/owner", body=b'{"own": true}',
                     headers={"Host": f"127.0.0.1:{self.port}", "Origin": "http://evil.example",
                              "X-VanaSync": "1", "Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 403)
        conn.close()

    def test_garbage_gets_no_reply(self):
        self.udp.sendto(b"\x00garbage", ("127.0.0.1", self.game_port))
        with self.assertRaises(socket.timeout):
            self.udp.settimeout(0.6)
            try:
                self.udp.recvfrom(1024)
            finally:
                self.udp.settimeout(2)

    def test_stale_when_game_stops(self):
        self.send()
        with self.srv.game.lock:
            self.srv.game.received -= server.GameBridge.FRESH + 0.1
        self.assertFalse(self.http("GET", "/api/game")[1]["live"])


class OffTest(unittest.TestCase):
    def test_no_bridge_by_default(self):
        with tempfile.TemporaryDirectory() as data:
            srv = server.Server(0, Path(data), bundled=False)
            try:
                self.assertIsNone(srv.game.sock)
                self.assertFalse(srv.game.snapshot()["live"])
            finally:
                srv.server_close()


if __name__ == "__main__":
    unittest.main()
