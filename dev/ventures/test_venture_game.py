"""Ventures sent in game (2026-11-26): the launcher's own planner, the in-game window's files, and the hub's side.
    python3 dev/ventures/test_venture_game.py
A stand-in game (it answers in.txt with out.txt), a stand-in clock, and for the paired cases the hub's real Ventures
class behind a stand-in connection. state.lua is read back with LuaJIT when lupa is installed.
"""
import json
import os
import sys
import tempfile
import threading
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "dev", "armory"))
import launcher_armory as A  # noqa: E402
import launcher_ventures as LV  # noqa: E402
import ventures as V  # noqa: E402
import ventures_hub as H  # noqa: E402

try:
    from lupa import luajit21 as lupa
except Exception:                                    # pragma: no cover
    try:
        import lupa
    except Exception:
        lupa = None

OWNER = "o" * 8
MATES = [{"slot": 0, "name": "Volker", "race": 1, "face": 2, "weapon": 3, "job": 1, "sjob": 2, "level": 18, "exp": 100},
         {"slot": 1, "name": "Curilla", "race": 4, "face": 5, "weapon": 3, "job": 7, "sjob": 1, "level": 18, "exp": 0},
         {"slot": 2, "name": "Shantotto", "race": 6, "face": 9, "weapon": 12, "job": 4, "sjob": 3, "level": 19, "exp": 0}]
BOTS = [{"name": "Zuki", "race": 5}, {"name": "Roru", "race": 6}]
CAMP = V.camps_for(18)[0]["id"]


class Clock:
    def __init__(self, t=1_800_000_000):
        self.t = t

    def __call__(self):
        return self.t


def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_lua(path):
    """state.lua as the add-on reads it (LuaJIT), turned back into Python values."""
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    table = lua.eval("function(p) local f = assert(loadfile(p)); setfenv(f, {}); return f() end")(path)

    def py(v):
        if lupa.lua_type(v) != "table":
            return v
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys):
            return [py(v[k]) for k in sorted(keys)]
        return {k: py(v[k]) for k in keys}
    return py(table)


class Game(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        self.ashita = tempfile.mkdtemp()
        self.clock = Clock()
        self.delivered, self.logs, self.calls = [], [], []
        self.roster = {"chars": [{"name": "Hurami", "mates": [dict(m) for m in MATES], "bots": BOTS}]}
        self.hub = None                                   # the hub's Ventures (paired cases)
        self.hub_up = True
        self.hub_has_game = True
        self._deliver, self._build = LV.deliver, LV.build_roster
        LV.deliver = lambda conn, char, items, log=print: self.delivered.append((char, items)) or True
        LV.build_roster = lambda conn: json.loads(json.dumps(self.roster))

    def tearDown(self):
        LV.deliver, LV.build_roster = self._deliver, self._build

    # ------------------------------------------------------------ stand-ins
    def pair(self):
        data = A.load(self.kit)
        data["paired"] = True
        A.save(data, self.kit)
        self.hub = H.Ventures(tempfile.mkdtemp(), threading.RLock(), now=lambda: self.clock() + 7)   # (its clock is 7 s ahead)

    def caller(self, path, body=None):
        self.calls.append(path)
        if not self.hub_up:
            raise OSError("no route to host")
        what, _, query = path[len("/armory/api/ventures"):].lstrip("/").partition("?")
        if what == "roster":
            return self.hub.roster(OWNER, body)
        if what == "launcher":
            return self.hub.launcher(OWNER)
        if what == "applied":
            return self.hub.applied(OWNER, body.get("ids"))
        if not self.hub_has_game:                           # (an older hub: its "not found" page for a GET, this for a POST)
            return {"error": "the armory answered 404"} if what == "game" else {"error": "unknown"}
        if what == "game":
            return self.hub.phone(OWNER, query == "camps=1")
        if what == "game/start":
            return self.hub.start(OWNER, body)
        if what in ("game/recall", "game/seen"):
            return getattr(self.hub, what[5:])(OWNER, body.get("id"))
        return {"error": "unknown"}

    def relay(self):
        return LV.Relay({"ashita_dir": self.ashita}, self.kit, log=self.logs.append, caller=self.caller,
                        connector=lambda: type("C", (), {"close": lambda s: None})(), clock=self.clock)

    def ask(self, rid, line):
        base = os.path.join(self.ashita, "config", "addons", "venture", "req")
        os.makedirs(base, exist_ok=True)
        path = os.path.join(base, rid + ".txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(line + "\n")
        os.utime(path, (self.clock(), self.clock()))

    def ui(self, *names):
        return os.path.join(self.ashita, "config", "addons", "venture", *names)

    def state(self):
        if lupa is None:
            self.skipTest("lupa is not installed")
        return load_lua(self.ui("state.lua"))

    def events(self, vid):
        return load_lua(self.ui("v", vid + ".lua"))

    def camps(self):
        return load_lua(self.ui("camps.lua"))

    def kitfile(self, name):
        return os.path.join(self.kit, "ventures", name)

    def game_takes_in(self):
        """The game's part: every venture in in.txt is given out and marked in out.txt."""
        ids = [line.split("|")[0] for line in read(self.kitfile("in.txt")).splitlines() if line]
        with open(self.kitfile("out.txt"), "a", encoding="utf-8") as f:
            for vid in ids:
                f.write(vid + "|ok\n")
        return ids

    def step(self, r):
        if r.tick() or r.due():
            r.look()

    # ------------------------------------------------------------ no app, no internet
    def test_alone_start_to_finish(self):
        r = self.relay()
        self.step(r)
        self.assertEqual(self.calls, [], "nothing goes to the hub when no app is paired")
        st = self.state()
        self.assertEqual([c["name"] for c in st["roster"]], ["Hurami"])
        self.assertEqual(len(st["roster"][0]["mates"]), 3)
        self.assertTrue(st["canSend"] and not st["hub"] and not st["paired"])
        self.assertEqual(st["campsSeq"], 1)
        camps = self.camps()
        self.assertEqual(len(camps["local"]), len(V.data()["camps"]))
        self.assertNotIn("hub", camps)
        self.assertEqual(camps["local"][0]["mobs"][0]["name"], V.camp_list()[0]["mobs"][0]["name"])
        self.assertTrue(abs(int(read(self.ui("alive.txt"))) - self.clock()) < 2)

        self.ask("r1", f"Hurami|start|vgame0001|0,1|{CAMP}|2")
        self.step(r)
        st = self.state()
        self.assertEqual(st["replies"]["r1"]["ok"], True, st["replies"])
        self.assertEqual(self.calls, [])
        v = st["ventures"][0]
        self.assertEqual((v["id"], v["src"], v["skew"], v["slots"], v["hours"]), ("vgame0001", "local", 0, [0, 1], 2))
        self.assertEqual(v["start"], self.clock())
        self.assertEqual([m["name"] for m in v["mates"]], ["Volker", "Curilla"])
        self.assertNotIn("events", v)
        self.assertNotIn("results", v, "what a venture has so far changes all the time: the window works it out")
        events = self.events("vgame0001")
        self.assertEqual(v["ev"], f"{len(events)}-{v['end']}")
        self.assertGreater(len(events), 10)
        self.assertEqual(events[0]["k"], "leave")
        self.assertIn("kill", {e["k"] for e in events})
        seq = st["seq"]
        for _ in range(3):                                # nothing new: the window's file is left alone
            self.clock.t += 31
            self.step(r)
        self.assertEqual(self.state()["seq"], seq)
        self.clock.t -= 93
        away = read(self.kitfile("away.txt")).splitlines()
        self.assertEqual(sorted(line.split("|")[:2] for line in away), [["Hurami", "0"], ["Hurami", "1"]])
        self.assertEqual(read(self.kitfile("in.txt")), "")

        # the same mate can't leave twice; another one can
        self.ask("r2", f"Hurami|start|vgame0002|1|{CAMP}|1")
        self.step(r)
        self.assertIn("already out", self.state()["replies"]["r2"]["error"])
        self.ask("r3", f"Hurami|start|vgame0003|2|{CAMP}|1")
        self.step(r)
        self.assertEqual(self.state()["replies"]["r3"]["ok"], True)

        # the PC is off for the night; the next day the launcher hands both to the game, once
        self.clock.t += 9 * 3600
        r2 = self.relay()
        self.step(r2)
        lines = read(self.kitfile("in.txt")).splitlines()
        self.assertEqual(sorted(line.split("|")[0] for line in lines), ["vgame0001", "vgame0003"])
        first = [line for line in lines if line.startswith("vgame0001")][0].split("|")
        self.assertEqual(first[1], "Hurami")
        exp = dict(part.split(":") for part in first[4].split(","))
        self.assertAlmostEqual(int(exp["0"]), 6000, delta=30)
        self.assertEqual(read(self.kitfile("away.txt")), "")
        self.assertEqual(self.delivered, [])
        # a mate who is back can leave again at once, and starts from where the last venture ended (the game has not
        # even given the exp yet)
        self.ask("r4", f"Hurami|start|vgame0004|0|{CAMP}|1")
        self.step(r2)
        st = self.state()
        self.assertEqual(st["replies"]["r4"]["ok"], True, st["replies"])
        v4 = {v["id"]: v for v in st["ventures"]}["vgame0004"]
        self.assertGreater((v4["mates"][0]["level"], v4["mates"][0]["exp"]), (18, 100))
        self.assertEqual([line.split("|")[:2] for line in read(self.kitfile("away.txt")).splitlines()], [["Hurami", "0"]])
        self.game_takes_in()
        self.clock.t += 31
        self.step(r2)
        self.assertEqual(sorted(c for c, _ in self.delivered), ["Hurami", "Hurami"])
        self.clock.t += 31
        self.step(r2)
        self.assertEqual(len(self.delivered), 2, "nothing is handed out twice")
        self.assertEqual(read(self.kitfile("in.txt")), "")
        st = self.state()
        done = {v["id"]: v for v in st["ventures"]}
        self.assertTrue(done["vgame0001"]["over"] and done["vgame0001"]["applied"])
        self.assertTrue(done["vgame0001"]["story"])
        self.assertAlmostEqual(done["vgame0001"]["results"]["exp"][0], 6000, delta=30)

    def test_recall_and_seen(self):
        r = self.relay()
        self.step(r)
        self.ask("a1", f"Hurami|start|vgame0010|0|{CAMP}|4")
        self.step(r)
        self.clock.t += 3600
        self.ask("a2", "Hurami|recall|vgame0010")
        self.step(r)
        st = self.state()
        self.assertEqual(st["replies"]["a2"]["ok"], True)
        v = st["ventures"][0]
        self.assertTrue(v["recalled"] and v["over"])
        self.assertEqual(v["end"], self.clock())
        self.assertTrue(1500 < v["results"]["exp"][0] < 3300, v["results"]["exp"])     # (the walk to the camp is part of the hour)
        events = self.events("vgame0010")
        self.assertEqual(events[-1]["k"], "home")
        self.assertEqual(v["ev"], f"{len(events)}-{v['end']}")
        self.assertIn("vgame0010|Hurami|", read(self.kitfile("in.txt")))
        self.ask("a3", "Hurami|seen|vgame0010")
        self.step(r)
        self.assertTrue(self.state()["ventures"][0]["seen"])

    def test_bad_requests_get_an_answer(self):
        r = self.relay()
        self.step(r)
        for rid, line, want in (("b1", "Hurami|start|vgame0020|0|nowhere|2", "camp"), ("b2", f"Hurami|start|vgame0021|0|{CAMP}|3", "hours"),
                                ("b3", f"Nobody|start|vgame0022|0|{CAMP}|2", "squad"), ("b4", f"Hurami|start|vgame0023|9|{CAMP}|2", "squad mates"),
                                ("b5", "Hurami|dance", "understand"), ("b6", "Hurami|recall|nothere", "from the app")):
            self.ask(rid, line)
            self.step(r)
            self.assertIn(want, self.state()["replies"][rid]["error"], rid)
        self.assertEqual(read(self.kitfile("away.txt")), "")

    def test_old_requests_are_dropped(self):
        r = self.relay()
        self.step(r)
        self.ask("c1", f"Hurami|start|vgame0030|0|{CAMP}|2")
        self.clock.t += 600                               # the launcher was closed for ten minutes
        self.step(r)
        self.assertFalse(self.state()["ventures"])
        self.assertEqual(os.listdir(os.path.join(self.ashita, "config", "addons", "venture", "req")), [])

    def test_open_keeps_the_picture_fresh(self):
        r = self.relay()
        self.step(r)
        self.assertFalse(r.tick())
        self.clock.t += 11
        self.assertFalse(r.due())
        self.ask("o1", "Hurami|open")
        self.step(r)
        self.clock.t += 11
        self.assertTrue(r.due(), "while the window shows, a look every ten seconds")
        self.roster["chars"][0]["mates"][0]["level"] = 25
        self.ask("o2", "Hurami|open")
        self.step(r)
        self.assertEqual(self.state()["roster"][0]["mates"][0]["level"], 25)

    # ------------------------------------------------------------ an app is paired
    def test_paired_goes_through_the_hub(self):
        self.pair()
        r = self.relay()
        self.step(r)
        st = self.state()
        self.assertTrue(st["paired"] and st["online"] and st["hub"])
        self.ask("p1", f"Hurami|start|vgame0100|0,1|{CAMP}|2")
        self.step(r)
        st = self.state()
        self.assertEqual(st["replies"]["p1"]["ok"], True)
        self.assertEqual([v["id"] for v in self.hub.state["list"][OWNER]], ["vgame0100"], "the hub planned it: the app shows it too")
        self.assertEqual(r.local.state["list"].get(LV.LOCAL, []), [])
        v = st["ventures"][0]
        self.assertEqual((v["src"], v["skew"]), ("hub", 7))
        away = read(self.kitfile("away.txt")).splitlines()
        self.assertEqual(len(away), 2)
        self.assertEqual(int(away[0].split("|")[2]), v["end"] - 7, "the hub's clock is 7 s ahead: the game goes by this PC's")
        self.assertEqual(self.events("vgame0100")[0]["k"], "leave")

        # one sent from the app shows in game with its timeline
        self.hub.start(OWNER, {"id": "vphone0001", "char": "Hurami", "slots": [2], "camp": CAMP, "hours": 1})
        self.clock.t += 31
        self.step(r)
        st = self.state()
        self.assertEqual(sorted(v["id"] for v in st["ventures"]), ["vgame0100", "vphone0001"])
        self.assertEqual(len(read(self.kitfile("away.txt")).splitlines()), 3)

        # called home from the game: the hub's venture ends
        self.ask("p2", "Hurami|recall|vphone0001")
        self.step(r)
        self.assertTrue(self.hub.state["list"][OWNER][1]["recalled"])
        self.game_takes_in()
        self.clock.t += 31
        self.step(r)
        self.assertEqual([c for c, _ in self.delivered], ["Hurami"])
        self.assertTrue(self.hub.state["list"][OWNER][1]["applied"])

    def test_hub_away_stays_away_when_the_hub_is_gone(self):
        self.pair()
        r = self.relay()
        self.step(r)
        self.hub.start(OWNER, {"id": "vphone0002", "char": "Hurami", "slots": [0], "camp": CAMP, "hours": 4})
        self.clock.t += 31
        self.step(r)
        self.assertIn("Hurami|0|", read(self.kitfile("away.txt")))
        self.hub_up = False
        self.clock.t += 31
        self.step(r)
        self.assertIn("Hurami|0|", read(self.kitfile("away.txt")), "no internet for a moment does not bring a mate home")
        r2 = self.relay()                                    # ... nor does a launcher restart
        self.step(r2)
        self.assertIn("Hurami|0|", read(self.kitfile("away.txt")))
        self.assertFalse(self.state()["online"])
        self.clock.t += 5 * 3600
        self.step(r2)
        self.assertEqual(read(self.kitfile("away.txt")), "")

    def test_paired_but_offline_plans_here_and_the_first_one_out_counts(self):
        self.pair()
        r = self.relay()
        self.step(r)
        self.hub_up = False
        self.clock.t += 31
        self.step(r)
        self.ask("q1", f"Hurami|start|vgame0200|0|{CAMP}|4")
        self.step(r)
        st = self.state()
        self.assertEqual(st["replies"]["q1"]["ok"], True)
        self.assertEqual([v["src"] for v in st["ventures"]], ["local"])
        # meanwhile the phone sends the same mate (the hub does not know he left), and another one
        self.clock.t += 600
        self.hub.start(OWNER, {"id": "vphone0003", "char": "Hurami", "slots": [0], "camp": CAMP, "hours": 2})
        self.hub.start(OWNER, {"id": "vphone0004", "char": "Hurami", "slots": [1], "camp": CAMP, "hours": 2})
        self.hub_up = True
        self.clock.t += 31
        self.step(r)
        self.clock.t += 31
        self.step(r)
        hub = {v["id"]: v for v in self.hub.state["list"][OWNER]}
        self.assertTrue(hub["vphone0003"].get("recalled"), "the later venture of the same mate is called home")
        self.assertFalse(hub["vphone0004"].get("recalled"))
        self.assertEqual([v["id"] for v in r.local.state["list"][LV.LOCAL]], ["vgame0200"])
        self.assertTrue(any("already out" in line for line in self.logs), self.logs)

    def test_the_app_was_first(self):
        self.pair()
        r = self.relay()
        self.step(r)
        self.hub.start(OWNER, {"id": "vphone0005", "char": "Hurami", "slots": [0], "camp": CAMP, "hours": 2})
        self.hub_up = False                                 # the game never heard of it
        self.clock.t += 600
        r.hub_bare, r.hub_state = [], None                  # (as after a fresh start with no internet)
        self.ask("s1", f"Hurami|start|vgame0300|0|{CAMP}|4")
        self.step(r)
        self.assertEqual(self.state()["replies"]["s1"]["ok"], True)
        self.assertIn("stays on this PC", self.state()["replies"]["s1"]["note"])
        self.hub_up = True
        self.clock.t += 61
        self.step(r)
        self.assertEqual(r.local.state["list"][LV.LOCAL], [], "the one sent in game is taken back")
        self.assertFalse(self.hub.state["list"][OWNER][0].get("recalled"))
        self.assertEqual(len(read(self.kitfile("away.txt")).splitlines()), 1)

    def test_a_hub_that_is_down_is_left_alone_for_a_while(self):
        self.pair()
        r = self.relay()
        self.step(r)
        self.hub_up = False
        del self.calls[:]
        for _ in range(4):                                  # four looks in 40 seconds: one try
            self.clock.t += 10
            r.look()
        self.assertEqual(len(self.calls), 1, self.calls)
        self.clock.t += 40
        r.look()
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(self.state()["online"])

    def test_a_broken_hub_counts_as_gone(self):
        self.pair()
        r = self.relay()
        self.step(r)
        real = r.call
        r.call = lambda path, body=None: {"error": "the armory answered 502"}
        self.clock.t += 31
        self.step(r)
        self.ask("x1", f"Hurami|start|vgame0500|0|{CAMP}|1")
        self.step(r)
        st = self.state()
        self.assertEqual(st["replies"]["x1"]["ok"], True)
        self.assertEqual([v["src"] for v in st["ventures"]], ["local"])
        r.call = real

    def test_the_album_is_kept_small(self):
        keep, LV.KEEP_PAST = LV.KEEP_PAST, 2
        try:
            r = self.relay()
            self.step(r)
            for i in range(4):
                self.ask(f"k{i}", f"Hurami|start|vgame06{i:02d}|0|{CAMP}|1")
                self.step(r)
                self.clock.t += 3700
                self.step(r)
                self.game_takes_in()
                self.clock.t += 31
                self.step(r)
                self.ask(f"s{i}", f"Hurami|seen|vgame06{i:02d}")
                self.step(r)
            st = self.state()
            self.assertEqual(sorted(v["id"] for v in st["ventures"]), ["vgame0602", "vgame0603"])
            self.assertEqual(sorted(os.listdir(self.ui("v"))), ["vgame0602.lua", "vgame0603.lua"])
        finally:
            LV.KEEP_PAST = keep

    def test_a_broken_list_is_put_aside(self):
        r = self.relay()
        self.step(r)
        self.ask("y1", f"Hurami|start|vgame0700|0|{CAMP}|1")
        self.step(r)
        with open(self.kitfile("state.json"), "w") as f:
            f.write('{"roster": {"local"')                  # (cut off in the middle)
        r2 = self.relay()
        self.step(r2)
        self.assertIsNotNone(r2.local)
        self.assertTrue(os.path.exists(self.kitfile("state.json.broken")))
        self.ask("y2", f"Hurami|start|vgame0701|0|{CAMP}|1")
        self.step(r2)
        self.assertEqual(self.state()["replies"]["y2"]["ok"], True)

    def test_a_kit_without_the_planner(self):
        """An old kit folder (no dev/armory): no ventures of its own, but the hub's still reach the game."""
        self.pair()
        self.hub.roster(OWNER, self.roster)
        self.hub.start(OWNER, {"id": "vphone0009", "char": "Hurami", "slots": [1], "camp": CAMP, "hours": 1})
        found = LV.engine_module
        LV.engine_module = lambda kit=None: None
        self.addCleanup(setattr, LV, "engine_module", found)
        r = LV.Relay({"ashita_dir": self.ashita}, self.kit, log=self.logs.append, caller=self.caller,
                     connector=lambda: type("C", (), {"close": lambda s: None})(), clock=self.clock)
        self.assertIsNone(r.local)
        self.step(r)
        self.assertIn("Hurami|1|", read(self.kitfile("away.txt")))
        st = self.state()
        self.assertTrue(st["hub"] and st["canSend"])
        self.assertEqual(len(self.camps()["local"]), len(V.data()["camps"]), "the hub's camps stand in")
        self.ask("z1", f"Hurami|start|vgame0800|0|{CAMP}|1")
        self.step(r)
        self.assertEqual(self.state()["replies"]["z1"]["ok"], True)
        self.assertEqual(sorted(v["id"] for v in self.hub.state["list"][OWNER]), ["vgame0800", "vphone0009"])
        self.hub_up = False
        self.clock.t += 61
        self.step(r)
        self.ask("z2", f"Hurami|start|vgame0801|2|{CAMP}|1")
        self.step(r)
        self.assertIn("can't be reached", self.state()["replies"]["z2"]["error"])

    def test_an_older_hub(self):
        self.pair()
        self.hub_has_game = False
        r = self.relay()
        self.step(r)
        self.hub.start(OWNER, {"id": "vphone0006", "char": "Hurami", "slots": [1], "camp": CAMP, "hours": 2})
        self.clock.t += 31
        self.step(r)
        st = self.state()
        self.assertTrue(st["paired"] and st["online"] and not st["hub"] and st["canSend"])
        self.assertEqual([(v["id"], v.get("bare")) for v in st["ventures"]], [("vphone0006", True)])
        self.ask("t1", f"Hurami|start|vgame0400|1|{CAMP}|2")
        self.step(r)
        self.assertIn("already out", self.state()["replies"]["t1"]["error"])
        self.ask("t2", f"Hurami|start|vgame0401|0|{CAMP}|2")
        self.step(r)
        st = self.state()
        self.assertEqual(st["replies"]["t2"]["ok"], True)
        self.assertIn("does not take ventures from the game yet", st["replies"]["t2"]["note"])
        self.assertEqual(sorted((v["id"], v["src"]) for v in st["ventures"]), [("vgame0401", "local"), ("vphone0006", "hub")])


class Lua(unittest.TestCase):
    def test_values_survive(self):
        if lupa is None:
            self.skipTest("lupa is not installed")
        folder = tempfile.mkdtemp()
        value = {"seq": 3, "end": 5, "name": 'Ay"a\\me', "list": [1, 2.5, True, "x"], "deep": {"a": [{"k": "kill", "t": 7}]},
                 "odd": "café — ok", "empty": [], "line": "a\nb"}
        self.assertTrue(LV.write_state(folder, value))
        self.assertTrue(read(os.path.join(folder, "state.lua")).startswith("-- seq 3 at 0\n"))
        back = load_lua(os.path.join(folder, "state.lua"))
        self.assertEqual(back["end"], 5)
        self.assertEqual(back["name"], 'Ay"a\\me')
        self.assertEqual(back["list"], [1, 2.5, True, "x"])
        self.assertEqual(back["deep"]["a"][0], {"k": "kill", "t": 7})
        self.assertEqual(back["odd"], "caf\u00e9 \u2014 ok")
        self.assertEqual(back["line"], "a\nb")


if __name__ == "__main__":
    unittest.main(verbosity=1)
