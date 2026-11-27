"""The in-game Ventures window (addons-src/venture) together with the launcher's relay, without the game:
    python3 dev/ventures/test_venture_addon.py
The add-on's own Lua runs under LuaJIT with stand-ins for Ashita and ImGui (venture_window.py), the launcher's relay
runs for real with a stand-in roster and clock, and the two talk through the same files as in the game. Needs lupa
and Pillow; the pictures must have been built (dev/ventures/build_venture_addon.py).
"""
import json
import os
import sys
import tempfile
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "dev", "armory"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launcher_ventures as LV  # noqa: E402
import ventures as V  # noqa: E402

try:
    from venture_window import ADDON, Window
except Exception as e:                                # pragma: no cover
    Window, ADDON, WHY = None, None, e

MATES = [{"slot": 0, "name": "Volker", "race": 1, "face": 2, "weapon": 3, "job": 1, "sjob": 2, "level": 18, "exp": 100},
         {"slot": 1, "name": "Curilla", "race": 4, "face": 5, "weapon": 3, "job": 7, "sjob": 1, "level": 18, "exp": 0},
         {"slot": 2, "name": "Shantotto", "race": 6, "face": 9, "weapon": 12, "job": 4, "sjob": 3, "level": 19, "exp": 0},
         {"slot": 3, "name": "Ayame", "race": 2, "face": 3, "weapon": 10, "job": 12, "sjob": 1, "level": 5, "exp": 0}]
BOTS = [{"name": n, "race": r} for n, r in (("Zuki", 5), ("Roru", 6), ("Mihli", 7), ("Balrahn", 3), ("Ovjang", 2))]
T0 = 1_800_000_000


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


class World:
    """A launcher relay with its own planner, a roster, and the window looking at the same Ashita folder."""

    def __init__(self, chars=("Hurami",), mates=MATES, ashita=None):
        self.kit, self.ashita = tempfile.mkdtemp(), ashita or tempfile.mkdtemp()
        self.clock = Clock()
        self.roster = {"chars": [{"name": c, "mates": [dict(m) for m in mates], "bots": BOTS} for c in chars]}
        self.logs = []
        self.relay = LV.Relay({"ashita_dir": self.ashita}, self.kit, log=self.logs.append, caller=lambda p, b=None: {},
                              connector=lambda: type("C", (), {"close": lambda s: None})(), clock=self.clock)
        self.launcher()

    def launcher(self, dt=0):
        """The launcher's turn: `dt` seconds pass, it reads the window's requests and looks."""
        self.clock.t += dt
        self.relay.tick()
        self.relay.look()
        self.relay.alive_at = 0
        self.relay.alive()

    def game_takes_in(self):
        path = os.path.join(self.kit, "ventures", "in.txt")
        ids = [line.split("|")[0] for line in open(path).read().splitlines() if line] if os.path.exists(path) else []
        with open(os.path.join(self.kit, "ventures", "out.txt"), "a") as f:
            for vid in ids:
                f.write(vid + "|ok\n")
        self.launcher(31)

    def window(self, size=2, **kw):
        w = Window(self.ashita, time=self.clock(), width=int(240 * size + 2 + 16 + 14 + 14), **kw)
        w.command("/venture")
        w.frame(advance=0.6)
        return w

    def see(self, win, dt=0.6):
        """The window's turn: it catches up with the launcher's clock and reads what the launcher wrote."""
        win.time = max(win.time, float(self.clock()))
        win.frame(advance=dt)
        return win.frame(advance=0.1)

    def requests(self):
        base = os.path.join(self.ashita, "config", "addons", "venture", "req")
        return sorted(open(os.path.join(base, f)).read().strip() for f in os.listdir(base)) if os.path.isdir(base) else []


@unittest.skipIf(Window is None, "lupa or Pillow is not installed")
class AddOn(unittest.TestCase):
    def setUp(self):
        if not os.path.exists(os.path.join(ADDON, "assets", "gm", "WAR_1.png")):
            self.skipTest("the add-on's pictures are not built: python dev/ventures/build_venture_addon.py")
        self._deliver, self._build = LV.deliver, LV.build_roster
        self.world = None
        LV.deliver = lambda conn, char, items, log=print: True
        LV.build_roster = lambda conn: json.loads(json.dumps(self.world.roster))

    def tearDown(self):
        LV.deliver, LV.build_roster = self._deliver, self._build

    def make(self, **kw):
        self.world = World.__new__(World)
        World.__init__(self.world, **kw)
        return self.world

    # ---------------------------------------------------------------- before anything is there
    def test_shut_it_draws_and_reads_nothing(self):
        win = Window(tempfile.mkdtemp())
        self.assertEqual(win.frame(), [])
        self.assertFalse(os.path.exists(os.path.join(win.ashita, "config", "addons", "venture")),
                         "a shut window reads nothing of the launcher's and makes no folder for it")
        self.assertEqual(os.listdir(os.path.join(win.ashita, "config", "addons")), ["xiforever"],
                         "all it leaves is its word to the Squads menu that it is loaded")
        # (1.1) nothing in the chat log: the add-on is not started with the game, so whoever has it loaded asked for it
        for dt in (5, 10, 60):
            win.frame(advance=dt)
        self.assertEqual(win.printed(), [])
        self.assertFalse(os.path.exists(os.path.join(win.ashita, "config", "addons", "venture")))
        self.assertTrue(win.command("/venture"))
        self.assertFalse(win.command("/squad"))
        win.frame(advance=1)
        self.assertTrue(win.has("Waiting for the launcher"))
        self.assertEqual(win.printed(), [])
        settings = os.path.join(win.ashita, "config", "addons", "venture", "settings.txt")
        win.command("/venture sound")
        self.assertNotIn("hinted", open(settings).read(), "the setting of 1.0's one-time chat line is gone")
        with open(settings, "a") as f:
            f.write("hinted = yes\n")                    # (a settings file 1.0 wrote is read without complaint)
        again = Window(win.ashita)
        again.command("/venture")
        again.frame(advance=1)
        self.assertEqual(again.printed(), [])
        self.assertFalse(again.mod.V.cfg.sound, "and its other settings are kept")
        win.command("/venture")
        self.assertEqual(win.frame(), [])

    def test_no_squads_yet(self):
        w = self.make(mates=[])
        win = w.window()
        self.assertTrue(win.has("No squad mates on this character yet."))
        w.roster["chars"] = []
        w.relay.local_roster_at = 0
        w.launcher(61)
        w.see(win)
        self.assertTrue(win.has("No squads yet."))

    # ---------------------------------------------------------------- the whole round, with no app and no internet
    def test_send_watch_call_home_read(self):
        w = self.make()
        win = w.window()
        self.assertTrue(win.has("SEND HURAMI'S SQUAD"))
        self.assertTrue(win.has("3,000 exp an hour"))
        self.assertFalse(win.has("WHICH CAMP"), "no camps before someone is picked")
        win.frame(click="Volker")
        win.frame(click="Curilla")
        win.frame()
        self.assertTrue(win.has("WHICH CAMP"))
        self.assertTrue(win.has("Valkurm Dunes"))
        self.assertFalse(win.has("East Ronfaure"), "a level 18 pair is not offered the level 1 woods")
        self.assertTrue(win.has("About 6,000 exp for each of them. They go as one party."))
        pictures = set(win.images())
        self.assertTrue({"bg/valkurm.png", "fg/valkurm.png", "gm/WAR_1.png", "gm/PLD_4.png"} <= pictures, pictures)
        win.frame(click="4 H")
        win.frame()
        self.assertTrue(win.has("About 12,000 exp"))
        win.frame(click="SEND THEM OFF")
        start = [r for r in w.requests() if "|start|" in r]
        self.assertEqual(len(start), 1)
        fields = start[0].split("|")
        self.assertEqual((fields[0], fields[1], fields[3], fields[4], fields[5]), ("Hurami", "start", "0,1", "valkurm_beach", "4"))
        self.assertRegex(fields[2], r"^v[0-9a-f]{20}$")
        win.frame(advance=0.1)
        self.assertTrue(win.has("SENDING..."))
        win.frame(click="SENDING...")
        self.assertEqual(len([r for r in w.requests() if "|start|" in r]), 1, "one press, one venture")

        w.launcher()
        w.see(win)
        self.assertEqual(win.printed(), [])
        self.assertTrue(win.has("On the road..."))
        self.assertTrue(win.has("back in 3h 59m"))
        self.assertTrue(win.has("Away: Volker, Curilla"))
        self.assertFalse(win.has("SENDING..."))
        self.assertIn("0 kills", win.texts())
        self.assertEqual([v["id"] for v in w.relay.local.state["list"]["local"]], [fields[2]])

        # on to a moment when they fight (the venture's own timeline says when: after the third kill, not at a rest)
        with open(os.path.join(w.kit, "ventures", "plans", fields[2] + ".json")) as f:
            events = json.load(f)["events"]
        rests = [(e["t"], e["t"] + e.get("d", 0)) for e in events if e["k"] == "rest"]
        kills = [e["t"] for e in events if e["k"] == "kill"]
        at = next(t - 20 for t in kills[3:] if not any(a - 5 <= t - 20 <= b + 5 for a, b in rests) and t - 20 > kills[2] + 5)
        w.launcher(at - 1)
        w.see(win)
        self.assertTrue(win.has("VALKURM DUNES"))
        left = 4 * 3600 - at
        self.assertTrue(any(t.startswith("back in %dh %02dm" % (left // 3600, (left % 3600) // 60)) or t.startswith("back in %dh %02dm" % ((left - 60) // 3600, ((left - 60) % 3600) // 60))
                            for t in win.texts()), [t for t in win.texts() if "back in" in t])
        self.assertTrue(any("Lv." in t for t in win.texts()), "the monster's name plate")
        self.assertNotIn("0 kills", win.texts())          # (the whole text: "10 kills" is not "0 kills")
        self.assertTrue(any(t.endswith(" kills") for t in win.texts()))
        self.assertTrue(any(i.startswith(("m/", "mt/")) for i in win.images()), "a monster is drawn")
        frames = set()
        for _ in range(12):                                # it moves: places and poses change from frame to frame
            win.frame(advance=0.12)
            frames.add(tuple(c[2:10] for c in win.cmds if c[0] == "image"))
        self.assertGreater(len(frames), 6)

        win.frame(click="CALL HOME")
        win.frame()
        self.assertTrue(win.has("Call them home early?"))
        win.frame(click="NO")
        win.frame()
        self.assertFalse(win.has("Call them home early?"))
        self.assertFalse(any("|recall|" in r for r in w.requests()))
        win.frame(click="CALL HOME")
        win.frame()
        win.frame(click="YES")
        self.assertEqual([r for r in w.requests() if "|recall|" in r], [f"Hurami|recall|{fields[2]}"])
        w.launcher(2)
        w.see(win)
        self.assertTrue(win.has("BACK FROM VALKURM DUNES"))
        self.assertTrue(win.has("Read the report"))
        self.assertTrue(any(t.startswith("+") and "exp" in t and "item(s)" in t for t in win.texts()))
        self.assertFalse(win.has("Away:"), "they are home: they can be picked again")
        self.assertIn(fields[2] + "|Hurami|", open(os.path.join(w.kit, "ventures", "in.txt")).read())

        win.frame(click="Read the report")
        self.assertEqual([r for r in w.requests() if "|seen|" in r], [f"Hurami|seen|{fields[2]}"])
        win.frame(advance=0.2)
        self.assertTrue(win.has("REPORT: VOLKER & CURILLA"))
        for label in ("Setting off", "At camp", "Home again", "WHAT THEY BROUGHT HOME", "Arrives in your game"):
            self.assertTrue(win.has(label), label)
        self.assertTrue(any(t.startswith(": +") and t.endswith(" exp") for t in win.texts()))
        self.assertEqual(sum(1 for i in win.images() if i == "bg/valkurm.png"), 4, "four pictures of the venture")
        w.game_takes_in()
        w.see(win)
        self.assertTrue(win.has("Already in your game"))
        win.frame(click="BACK")
        win.frame()
        self.assertTrue(win.has("PAST VENTURES"))
        self.assertTrue(win.has("(called home early)"))
        self.assertFalse(win.has("BACK FROM VALKURM DUNES"), "read once: it is in the album now")
        self.assertEqual(win.printed(), [])

    # ---------------------------------------------------------------- the launcher's answers and silences
    def test_the_launchers_no_is_shown(self):
        w = self.make()
        win = w.window()
        win.frame(click="Volker")
        win.frame()
        w.relay.local.start("local", {"id": "vbeforehand1", "char": "Hurami", "slots": [0], "camp": "valkurm_beach", "hours": 1})
        win.frame(click="SEND THEM OFF")                   # (the window has not heard yet that he left)
        w.launcher()
        w.see(win)
        self.assertTrue(win.has("Volker is already out on a venture."))
        self.assertTrue(win.has("Away: Volker"))

    def test_without_the_launcher_nothing_is_sent(self):
        w = self.make()
        win = w.window()
        win.frame(click="Volker")
        win.frame()
        before = [r for r in w.requests() if "|start|" in r]
        win.time += 60                                     # a minute without a sign of life from the launcher
        win.frame(advance=4)
        self.assertTrue(win.has("The launcher is not running"))
        win.frame(click="SEND THEM OFF")
        self.assertEqual([r for r in w.requests() if "|start|" in r], before)

    def test_an_answer_that_never_comes(self):
        w = self.make()
        win = w.window()
        win.frame(click="Volker")
        win.frame()
        win.frame(click="SEND THEM OFF")
        for _ in range(9):
            w.relay.alive_at = 0
            w.clock.t += 2
            w.relay.alive()                                # (the launcher is alive, but never reads the request)
            win.time = float(w.clock())
            win.frame(advance=0.1)
        self.assertTrue(win.has("The launcher did not answer."))
        self.assertFalse(win.has("SENDING..."))

    # ---------------------------------------------------------------- more than one character
    def test_the_character_you_play_comes_first(self):
        w = self.make(chars=("Hurami", "Taru"))
        win = w.window(me="Taru")
        self.assertTrue(win.has("SEND TARU'S SQUAD"))
        self.assertTrue(win.has("HURAMI"), "the other character has a button")
        win.frame(click="HURAMI")
        win.frame()
        self.assertTrue(win.has("SEND HURAMI'S SQUAD"))
        win.frame(click="Ayame")
        win.frame()
        self.assertTrue(win.has("WHERE"))
        self.assertTrue(win.has("solo hunting below level 10"))
        win.frame(click="SEND THEM OFF")
        self.assertTrue(any(r.startswith("Hurami|start|") and r.endswith("|3|ronfaure|2") for r in w.requests()), w.requests())

    # ---------------------------------------------------------------- how it is drawn
    def test_sizes(self):
        w = self.make()
        w.relay.local.start("local", {"id": "vsizes000001", "char": "Hurami", "slots": [0], "camp": "valkurm_beach", "hours": 1})
        w.launcher(1200)
        for size in (1.5, 2, 3):
            win = w.window(size=size)
            w.see(win)
            widths = {round(c[4] - c[2]) for c in win.cmds if c[0] == "image" and win.textures[int(c[1])].endswith(os.path.join("bg", "valkurm.png"))}
            self.assertEqual(widths, {int(240 * size)}, f"the scene at {size}: {widths}")

    def test_an_imgui_that_cannot_size_fonts(self):
        w = self.make()
        w.relay.local.start("local", {"id": "vfonts000001", "char": "Hurami", "slots": [0], "camp": "valkurm_beach", "hours": 1})
        w.launcher(1200)
        win = w.window(sized_fonts=False)
        w.see(win)
        self.assertTrue(win.has("back in"))
        self.assertGreater(len({c[5] for c in win.cmds if c[0] == "text"}), 2, "several letter sizes, by stretching")
        self.assertEqual(win.printed(), [])

    def test_a_font_scale_for_all_of_ashita(self):
        """ImGui 1.92 multiplies a pushed size by the scale set for everything: the window asks for less, so its
        letters come out the size it means."""
        w = self.make()
        w.relay.local.start("local", {"id": "vscale000001", "char": "Hurami", "slots": [0], "camp": "valkurm_beach", "hours": 1})
        w.launcher(1200)
        plain = w.window()
        w.see(plain)
        big = w.window(font_scale=1.5)
        w.see(big)
        self.assertEqual(big.printed(), [])
        # the scene's letters go by the scene's size (7 grid pixels: 14), never smaller than 10 px of the font in use
        def plate(win):
            return next(c[5] for c in win.cmds if c[0] == "text" and "Lv." in str(c[4]))
        self.assertAlmostEqual(plate(plain), 14, delta=0.6)
        self.assertAlmostEqual(plate(big), 15, delta=0.6)
        # the window's own letters follow the font: half as big again
        def title(win):
            return next(c[5] for c in win.cmds if c[0] == "text" and c[4] == "VALKURM DUNES")
        self.assertAlmostEqual(title(big) / title(plain), 1.5, delta=0.1)

    def test_pictures_are_let_go(self):
        w = self.make()
        win = w.window()
        win.frame(click="Volker")
        win.frame()
        gfx = win.mod.gfx
        self.assertGreater(gfx.count(), 3)
        win.frame(click="Volker")                          # nobody picked: no scene
        for _ in range(8):
            win.frame(advance=6)
        self.assertEqual(gfx.count(), 0)

    def test_a_venture_whose_timeline_is_missing(self):
        w = self.make()
        w.relay.local.start("local", {"id": "vnofile00001", "char": "Hurami", "slots": [0], "camp": "valkurm_beach", "hours": 1})
        w.launcher(1200)
        os.remove(os.path.join(w.ashita, "config", "addons", "venture", "v", "vnofile00001.lua"))
        win = w.window()
        w.see(win)
        self.assertTrue(win.has("back in"))
        self.assertEqual(win.printed(), [])


@unittest.skipIf(Window is None, "lupa or Pillow is not installed")
class Scene(unittest.TestCase):
    """The scene's own sums, against the app's (xifo-app/src/ventures/Stage.tsx)."""

    @classmethod
    def setUpClass(cls):
        cls.win = Window(tempfile.mkdtemp())
        cls.stage = cls.win.mod.Stage
        cls.lua = cls.win.lua

    def events(self, rows):
        return self.lua.table_from([self.lua.table_from(r) for r in rows])

    def test_state_at(self):
        ev = self.events([{"t": 0, "k": "leave"}, {"t": 600, "k": "arrive", "camp": "a"}, {"t": 700, "k": "kill", "c": "a", "m": 1, "x": 100},
                          {"t": 800, "k": "rest", "d": 60}, {"t": 900, "k": "move", "camp": "b"}, {"t": 1000, "k": "kill", "c": "b", "m": 0, "x": 90},
                          {"t": 1100, "k": "home"}])
        at = self.stage.stateAt
        s = at(ev, 300, False)
        self.assertEqual((s.phase, s.camp, s.roadT), ("road", "a", 0.5))
        s = at(ev, 650, False)
        self.assertEqual((s.phase, s.camp, s.fighting.t, s.last), ("fight", "a", 700, None))
        self.assertAlmostEqual(s.hp, 0.5)
        s = at(ev, 820, False)
        self.assertEqual((s.phase, s.last.t, s.fighting.t), ("rest", 700, 1000))
        s = at(ev, 950, False)
        self.assertEqual((s.phase, s.camp), ("fight", "b"))
        self.assertAlmostEqual(s.hp, 1 - 250 / 300)
        s = at(ev, 1050, False)
        self.assertEqual((s.fighting.t, s.hp), (1000, 1))
        self.assertEqual(at(ev, 1100, True).phase, "home")

    def test_members(self):
        mates = self.lua.table_from([self.lua.table_from({"race": 6, "job": 4, "face": 9}), self.lua.table_from({"race": 1, "job": 99})])
        party = self.lua.table_from([self.lua.table_from({"name": n, "job": "WAR"}) for n in ("Zuki", "Roru", "Mihli", "Balrahn", "Ovjang")])
        got = [dict(m) for m in self.stage.membersOf(mates, party).values()]
        self.assertEqual(len(got), 6)
        self.assertEqual((got[0]["kind"], got[0]["job"], got[1]["job"]), ("mate", "BLM", "WAR"))

        def idx(name, i):                                 # the app's: h = (h * 31 + code) >>> 0; (h + i) % 6
            h = 0
            for ch in name:
                h = (h * 31 + ord(ch)) & 0xFFFFFFFF
            return (h + i) % 6
        self.assertEqual([m["idx"] for m in got[2:]], [idx(n, i) for i, n in enumerate(("Zuki", "Roru", "Mihli", "Balrahn"))])

    def test_mate_frames(self):
        f = self.stage.mateFrame
        # idle and walk go 0 1 2 1; a job with a sheet three (walk: two) times slower
        self.assertEqual([f(0, "WAR", s, False) for s in range(5)], [0, 1, 2, 1, 0])
        self.assertEqual([f(0, "WAR", s, True) for s in range(0, 13, 3)], [0, 1, 2, 1, 0])
        self.assertEqual([f(2, "WAR", s, True) for s in range(0, 9, 2)], [3, 4, 5, 4, 3])
        # the attack by job: swing, thrust, shoot, cast
        self.assertEqual([(f(4, j, 0, True), f(5, j, 0, True)) for j in ("WAR", "MNK", "RNG", "BLM")], [(6, 8), (9, 11), (12, 14), (15, 16)])
        self.assertEqual((f(7, "WAR", 0, True), f(8, "WAR", 0, True), f(9, "WAR", 0, True), f(9, "WAR", 3, True)), (17, 19, 20, 21))

    def test_vanadiel_hour(self):
        self.assertEqual(self.stage.vanaHour(1009810800), 0)
        self.assertEqual(self.stage.vanaHour(1009810800 + 144), 1)          # an hour there is 144 seconds here
        self.assertEqual([self.stage.timeOfDay(h) for h in (3, 4, 6, 16, 17, 20)], ["night", "dawn", "day", "day", "dusk", "night"])


class Files(unittest.TestCase):
    def test_every_picture_the_planner_can_ask_for_is_there(self):
        art = os.path.join(KIT, "addons-src", "venture", "art.lua")
        if not os.path.exists(art):
            self.skipTest("the add-on's pictures are not built")
        text = open(art, encoding="ascii").read()
        for camp in V.camp_list():
            self.assertIn(f"['{camp['scene']}'] = true", text, camp["id"])
            for mob in camp["mobs"]:
                own = "".join(ch if ch.isalnum() and ch.isascii() else "_" for ch in mob["name"])
                self.assertTrue(f"['{own}'] = true" in text or f"['{mob['look']}'] = true" in text, mob)
        for job in ("WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN", "BLU", "COR", "PUP"):
            for race in range(1, 9):
                self.assertTrue(os.path.exists(os.path.join(KIT, "addons-src", "venture", "assets", "gm", f"{job}_{race}.png")), (job, race))

    def test_pictures_are_what_direct3d_takes_as_they_are(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest("Pillow is not installed")
        base = os.path.join(KIT, "addons-src", "venture", "assets")
        if not os.path.isdir(base):
            self.skipTest("the add-on's pictures are not built")
        seen = 0
        for kind in ("bg", "fg", "m", "mt", "p", "gm"):
            names = sorted(os.listdir(os.path.join(base, kind)))
            for name in names[:3] + names[-2:]:
                im = Image.open(os.path.join(base, kind, name))
                self.assertEqual(im.mode, "RGBA", name)
                for side in im.size:
                    self.assertEqual(side & (side - 1), 0, f"{kind}/{name}: {im.size} is not a power of two")
                seen += 1
        self.assertGreater(seen, 20)


if __name__ == "__main__":
    unittest.main(verbosity=1)
