"""Tests for Tetra Master in the app (python3 dev/armory/test_tetra.py): the hub's rules, PvP matchmaking and matches over
a real armory server on a free local port, the cards on a character's card, the phone's results, and the launcher
reading the cards and taking the results in (sqlite stands in for the world's database)."""
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import armory_service as A  # noqa: E402
import tetra_hub  # noqa: E402
import tetra_rules as T  # noqa: E402

OWNER, OTHER = "a" * 32, "b" * 32
PHONE1, PHONE2, PHONE3 = "c" * 32, "d" * 32, "e" * 32


def tm_cards(n=8, start=1):
    rng = (lambda s: (lambda lo, hi: lo + next(s) % (hi - lo + 1)))(iter(range(10 ** 6)))
    out = []
    for i in range(n):
        c = T.new_card(rng, start + i)
        c["uid"] = i + 1
        out.append(c)
    return out


def card(name, unlocked=True):
    return {"name": name, "race": 5, "face": 3, "mjob": 4, "mlvl": 30,
            "tetra": {"unlocked": unlocked, "cards": tm_cards(), "deck": [1, 2, 3, 4, 5], "gilRate": 1.5}}


class Rules(unittest.TestCase):
    def test_a_whole_match(self):
        rng = T.sys_rng()
        hands = {s: [T.new_card(rng, rng(1, 250)) for _ in range(5)] for s in T.SIDES}
        m = T.new_match(rng, hands, "blue")
        n = 0
        while not m["over"]:
            if m["pending"]:
                ev, err = T.choose_battle(m, m["turn"], 1)
            else:
                h, x, y = T.random_move(m, m["turn"], rng)
                ev, err = T.place(m, m["turn"], h, x, y)
            self.assertIsNone(err)
            n += 1
        b, r = T.score(m)
        self.assertEqual(ev[-1]["type"], "end")
        self.assertGreaterEqual(b + r, 10 - 0)          # all 10 cards are on the board
        self.assertEqual(T.place(m, "blue", 1, 1, 1), (None, "over"))

    def test_code(self):
        self.assertEqual(T.card_code({"atk": 0x3F, "type": "X", "pdef": 0xC0, "mdef": 0x05}), "3XC0")


class Service(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        tetra_hub.TURN_SECONDS = 2                          # quick turns for the timeout test
        tetra_hub.POLL_WAIT = 2
        cls.arm = A.Armory(cls.tmp)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), A.make_handler(cls.arm, os.path.join(cls.tmp, "static")))
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        cls.call("/armory/api/sync", {"cards": [card("Hurami"), card("Kandra", unlocked=False)]}, owner=OWNER)
        cls.call("/armory/api/sync", {"cards": [card("Ayame")]}, owner=OTHER)
        for owner, phone in ((OWNER, PHONE1), (OTHER, PHONE2), (OWNER, PHONE3)):
            code = cls.call("/armory/api/pair", {}, owner=owner)["code"]
            cls.call("/armory/api/claim", {"code": code}, phone=phone)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    @classmethod
    def call(cls, path, body=None, owner=None, phone=None):
        headers = {"Content-Type": "application/json"}
        if owner:
            headers["X-Armory-Key"] = owner
        if phone:
            headers["X-Armory-Phone"] = phone
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(cls.base + path, data=data, headers=headers, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return json.loads(res.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def test_1_cards_are_private(self):
        pub = self.call("/armory/api/c/Hurami")
        self.assertEqual(pub["card"]["tetra"], {"unlocked": True, "count": 8})
        me = self.call("/armory/api/me", phone=PHONE1)
        mine = {c["name"]: c for c in me["cards"]}
        self.assertEqual(len(mine["Hurami"]["tetra"]["cards"]), 8)
        self.assertEqual(mine["Hurami"]["tetra"]["gilRate"], 1.5)

    def test_2_queue_checks(self):
        self.assertIn("Luto", self.call("/armory/api/tm/queue", {"char": "Kandra", "uids": [1, 2, 3, 4, 5]}, phone=PHONE1)["error"])
        self.assertIn("Not one", self.call("/armory/api/tm/queue", {"char": "Ayame", "uids": [1, 2, 3, 4, 5]}, phone=PHONE1)["error"])
        self.assertIn("isn't in your collection", self.call("/armory/api/tm/queue", {"char": "Hurami", "uids": [1, 2, 3, 4, 99]}, phone=PHONE1)["error"])
        self.assertIn("5 different", self.call("/armory/api/tm/queue", {"char": "Hurami", "uids": [1, 1, 2, 3, 4]}, phone=PHONE1)["error"])

    def test_3_a_pvp_match(self):
        t1 = self.call("/armory/api/tm/queue", {"char": "Hurami", "uids": [1, 2, 3, 4, 5]}, phone=PHONE1)["ticket"]
        v = self.call(f"/armory/api/tm/poll?t={t1}&since=0", phone=PHONE1)
        self.assertEqual(v["state"], "waiting")
        self.assertEqual(self.call("/armory/api/tm/lobby?char=Hurami", phone=PHONE1)["waiting"], 1)
        t2 = self.call("/armory/api/tm/queue", {"char": "Ayame", "uids": [3, 4, 5, 6, 7]}, phone=PHONE2)["ticket"]
        views = {t1: self.call(f"/armory/api/tm/poll?t={t1}&since=0", phone=PHONE1),
                 t2: self.call(f"/armory/api/tm/poll?t={t2}&since=0", phone=PHONE2)}
        self.assertEqual({v["state"] for v in views.values()}, {"playing"})
        self.assertEqual({v["you"] for v in views.values()}, {"blue", "red"})
        self.assertEqual(views[t1]["opponent"]["name"], "Ayame")
        self.assertEqual(len(views[t1]["hand"]), 5)
        phones = {t1: PHONE1, t2: PHONE2}
        since = {t1: 0, t2: 0}
        moves = 0
        while True:
            v = {t: self.call(f"/armory/api/tm/poll?t={t}&since={since[t]}", phone=phones[t]) for t in (t1, t2)}
            if v[t1]["state"] == "over":
                break
            t = next(t for t in (t1, t2) if v[t]["turn"] == v[t]["you"])
            other = t2 if t == t1 else t1
            # the other player can't move now
            self.assertIn("error", self.call("/armory/api/tm/move", {"t": other, "hand": 1, "x": 1, "y": 1}, phone=phones[other]))
            if v[t]["pending"]:
                res = self.call("/armory/api/tm/move", {"t": t, "battle": 1}, phone=phones[t])
            else:
                free = [(x, y) for x in range(1, 5) for y in range(1, 5)]
                taken = set()
                for e in self.call(f"/armory/api/tm/poll?t={t}&since=0", phone=phones[t])["events"]:
                    if e["type"] == "place":
                        taken.add((e["x"], e["y"]))
                for b in v[t]["blocks"]:
                    taken.add((b["x"], b["y"]))
                x, y = next(c for c in free if c not in taken)
                res = self.call("/armory/api/tm/move", {"t": t, "hand": 1, "x": x, "y": y}, phone=phones[t])
            self.assertTrue(res.get("ok"), res)
            moves += 1
            self.assertLess(moves, 30)
        res = v[t1]["result"]
        self.assertIn(res["winner"], ("blue", "red", "draw"))
        rec = self.call("/armory/api/tm/lobby?char=Hurami", phone=PHONE1)["record"]
        self.assertEqual(sum(rec.values()), 1)

    def test_4_timeouts_and_leaving(self):
        t1 = self.call("/armory/api/tm/queue", {"char": "Hurami", "uids": [1, 2, 3, 4, 5]}, phone=PHONE1)["ticket"]
        t2 = self.call("/armory/api/tm/queue", {"char": "Ayame", "uids": [1, 2, 3, 4, 5]}, phone=PHONE2)["ticket"]
        v = self.call(f"/armory/api/tm/poll?t={t1}&since=0", phone=PHONE1)
        n = v["next"]
        time.sleep(3.2)                                      # a turn runs out: the hub plays for that player
        v = self.call(f"/armory/api/tm/poll?t={t1}&since={n}", phone=PHONE1)
        self.assertTrue(any(e.get("auto") for e in v["events"]), v["events"])
        self.assertTrue(self.call("/armory/api/tm/leave", {"t": t2}, phone=PHONE2)["ok"])
        v = self.call(f"/armory/api/tm/poll?t={t1}&since=0", phone=PHONE1)
        self.assertEqual(v["state"], "over")
        self.assertEqual(v["result"]["how"], "left")
        self.assertEqual(v["result"]["winner"], v["you"])

    def test_5_same_character_never_meets_itself(self):
        a = self.call("/armory/api/tm/queue", {"char": "Hurami", "uids": [1, 2, 3, 4, 5]}, phone=PHONE1)["ticket"]
        b = self.call("/armory/api/tm/queue", {"char": "Hurami", "uids": [1, 2, 3, 4, 5]}, phone=PHONE3)["ticket"]
        self.assertEqual(self.call(f"/armory/api/tm/poll?t={a}&since=0", phone=PHONE1)["state"], "waiting")
        self.assertEqual(self.call(f"/armory/api/tm/poll?t={b}&since=0", phone=PHONE3)["state"], "waiting")
        self.call("/armory/api/tm/leave", {"t": a}, phone=PHONE1)
        self.call("/armory/api/tm/leave", {"t": b}, phone=PHONE3)

    def test_6_phone_results(self):
        out = self.call("/armory/api/fish", {"id": "tm-test-0001", "char": "Hurami", "catches": [], "gilFound": 10 ** 6,
                                             "tetra": {"gil": 10 ** 6, "wins": 3, "upgrades": [{"uid": 2, "id": 2, "type": "X"},
                                                                                              {"uid": 3, "id": 99, "type": "A"}]}},
                        phone=PHONE1)
        self.assertTrue(out.get("ok"), out)
        rep = next(r for r in self.call("/armory/api/fish", owner=OWNER)["reports"] if r["id"] == "tm-test-0001")
        self.assertEqual(rep["tetra"]["upgrades"], [{"uid": 2, "id": 2, "type": "X"}])   # not a card of that number
        self.assertEqual(rep["tetra"]["gil"], int(40 * 1600 * 1.5) + 1)                     # capped


class Launcher(unittest.TestCase):
    def test_cards_and_results(self):
        import launcher_armory as L
        db = sqlite3.connect(":memory:")
        db.executescript("""
            CREATE TABLE accounts(id INTEGER, login TEXT); INSERT INTO accounts VALUES (1000, 'me');
            CREATE TABLE chars(charid INTEGER, accid INTEGER, charname TEXT); INSERT INTO chars VALUES (7, 1000, 'Hurami');
            CREATE TABLE char_vars(charid INTEGER, varname TEXT, value INTEGER);
            CREATE TABLE char_inventory(charid INTEGER, location INTEGER, slot INTEGER, itemId INTEGER, quantity INTEGER);
            INSERT INTO char_inventory VALUES (7, 0, 0, 65535, 500);
        """)
        a1 = 24 + 256 * 5 + 65536 * 0        # Cactuar, arrows up + left (1 + 4), class P
        b1 = 0x3A + 256 * 0xC5 + 65536 * 0x07
        rows = [("TM_STARTER", 1), ("TM_N", 2), ("TM_A1", a1), ("TM_B1", b1), ("TM_A2", 0), ("TM_B2", 0), ("TM_D1", 1)]
        db.executemany("INSERT INTO char_vars VALUES (7, ?, ?)", rows)
        db.commit()
        cur = db.cursor()
        tm = L.tetra_cards(cur, 7)
        self.assertTrue(tm["unlocked"])
        self.assertEqual(tm["cards"], [{"uid": 1, "id": 24, "arrows": 5, "type": "P", "atk": 0x3A, "pdef": 0xC5, "mdef": 7}])
        self.assertEqual(tm["deck"], [1])
        rep = {"id": "r1", "char": "Hurami", "catches": [], "gilFound": 600, "gil": 0,
               "tetra": {"gil": 600, "wins": 2, "upgrades": [{"uid": 1, "id": 24, "type": "X"}, {"uid": 2, "id": 5, "type": "A"}]}}
        lines = []
        self.assertEqual(L.apply_reports(db, [rep], lines.append), ["r1"])
        a = db.execute("SELECT value FROM char_vars WHERE charid = 7 AND varname = 'TM_A1'").fetchone()[0]
        self.assertEqual(a, 24 + 256 * 5 + 65536 * 2)          # class X now, same card and arrows
        self.assertEqual(db.execute("SELECT quantity FROM char_inventory WHERE itemId = 65535").fetchone()[0], 1100)
        self.assertIn("Tetra Master on your phone, 2 wins, gil +600, 1 card up a class", lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
