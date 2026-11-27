"""The Squads menu's Ventures button and the venture add-on, without the game:
    python3 dev/ventures/test_venture_button.py

Ventures is NOT started with the game. The Squads menu (servermenu 1.36) has a Ventures button on its Squad tab: it
loads the add-on ("/addon load venture"), shows its window ("/venture show"), shuts it again ("/venture hide"), and is
lit while the window is shown. The two add-ons agree through two small files in the character's folder
(config/addons/xiforever/<Name>_<Id>/venture.loaded and venture.open) and the line "/xifoventure".

  Marks      the add-on's side alone: its two files and its line.
  Together   BOTH real add-ons, each in its own Lua state as Ashita runs them, with Ashita's part played between them:
             a line an add-on hands to the chat manager goes to every loaded add-on's command handler at the start of
             the next frame, "/addon load venture" loads the add-on, and whatever no add-on stops reaches the game
             (where an unknown command is "A command error occurred"). The menu runs in the stand-ins of its own test
             (dev/squad-tests/test_squad_menu_ui.lua), the add-on in venture_window.py.

This system has no Windows process id, so a file left by an earlier game always looks like this game's: the worst
case, and the one the button has to get out of by itself. Needs lupa (with LuaJIT) and Pillow.
"""
import os
import random
import re
import shutil
import sys
import tempfile
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "dev", "armory"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from lupa import luajit21 as lupa
    from venture_window import ADDON, Window
    WHY = None
except Exception as e:                                # pragma: no cover
    lupa, Window, ADDON, WHY = None, None, None, e

MENU_TEST = os.path.join(KIT, "dev", "squad-tests", "test_squad_menu_ui.lua")
MENU_UI = os.path.join(KIT, "addons-src", "servermenu", "xifo_ui.lua")
BTN = "Ventures##ventures"
T0 = 1_800_000_000


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def folder(ashita, who="Hurami_7"):
    return os.path.join(ashita, "config", "addons", "xiforever", who)


# ---------------------------------------------------------------------------------------------------------------------
@unittest.skipIf(Window is None, f"lupa or Pillow is not installed ({WHY})")
class Marks(unittest.TestCase):
    """The add-on's word to the Squads menu: venture.loaded, venture.open and "/xifoventure"."""

    def test_loaded_says_so_at_once(self):
        win = Window(tempfile.mkdtemp())
        self.assertEqual(win.marks(), ["venture.loaded"], "loaded with a character in the game: the file is there before the first frame")
        self.assertRegex(read(os.path.join(folder(win.ashita), "venture.loaded")), r"\AVentures 1\.1\n(pid=\d+\n)?\Z")
        self.assertEqual(win.queued(), ["/xifoventure"], "and it says so, once")
        for _ in range(5):
            win.frame(advance=0.7)
        self.assertEqual(win.queued(), ["/xifoventure"], "nothing more while nothing changes")
        self.assertEqual(win.marks(), ["venture.loaded"])
        self.assertEqual(win.printed(), [])

    def test_show_hide_and_toggle(self):
        win = Window(tempfile.mkdtemp())
        win.queued(clear=True)
        self.assertTrue(win.command("/venture show"), "the add-on stops its own command")
        self.assertEqual(win.marks(), ["venture.loaded"], "the file follows the window: after the frame it was drawn in")
        win.frame(advance=0.05)
        self.assertTrue(win.has("Waiting for the launcher"), "the window is drawn")
        self.assertEqual(win.marks(), ["venture.loaded", "venture.open"])
        self.assertRegex(read(os.path.join(folder(win.ashita), "venture.open")), r"\AVentures 1\.1\n(pid=\d+\n)?\Z")
        self.assertEqual(win.queued(clear=True), ["/xifoventure"])
        win.command("/venture show")
        win.frame(advance=0.05)
        self.assertEqual(win.queued(), [], "shown already: nothing changed, nothing said")
        self.assertTrue(win.command("/venture hide"))
        self.assertEqual(win.frame(advance=0.05), [], "shut: nothing is drawn")
        self.assertEqual(win.marks(), ["venture.loaded"])
        self.assertEqual(win.queued(clear=True), ["/xifoventure"])
        win.command("/venture hide")
        win.frame(advance=0.05)
        self.assertEqual(win.queued(), [])
        for line, shown in (("/venture", True), ("/venture", False), ("/ventures toggle", True), ("/venture close", False),
                            ("/venture open", True), ("/VENTURE HIDE", False)):
            win.command(line)
            win.frame(advance=0.05)
            self.assertEqual(win.marks(), ["venture.loaded"] + (["venture.open"] if shown else []), line)
            self.assertEqual(win.queued(clear=True), ["/xifoventure"], line)
        self.assertEqual(win.printed(), [])

    def test_its_own_line_never_reaches_the_game(self):
        win = Window(tempfile.mkdtemp())
        before = win.marks()
        self.assertTrue(win.command("/xifoventure"), "stopped here, so it is harmless with an older menu or with none")
        self.assertTrue(win.command("/XifoVenture now"))
        win.frame(advance=0.05)
        self.assertEqual(win.marks(), before)
        self.assertEqual(win.frame(), [], "and it does not open the window")
        self.assertFalse(win.command("/xifogambits"))
        self.assertFalse(win.command("/menu"))

    def test_the_windows_own_x(self):
        win = Window(tempfile.mkdtemp())
        win.command("/venture show")
        win.frame(advance=0.05)
        win.queued(clear=True)
        win.click_x()
        win.frame(advance=0.05)
        self.assertEqual(win.marks(), ["venture.loaded"], "shut with the X: the file is gone in that frame")
        self.assertEqual(win.queued(), ["/xifoventure"])

    def test_size_opens_the_window(self):
        win = Window(tempfile.mkdtemp())
        win.queued(clear=True)
        win.command("/venture size 3")
        win.frame(advance=0.05)
        self.assertEqual(win.marks(), ["venture.loaded", "venture.open"], "whatever opened the window, the file says it is shown")
        self.assertEqual(win.queued(), ["/xifoventure"])

    def test_nobody_logged_in_yet(self):
        win = Window(tempfile.mkdtemp(), me="")
        win.frame(advance=2)
        self.assertFalse(os.path.exists(os.path.join(win.ashita, "config")), "at the title screen there is no character's folder: nothing is written")
        self.assertEqual(win.queued(), [])
        win.me = "Hurami"
        win.frame(advance=1.1)
        self.assertEqual(win.marks(), ["venture.loaded"], "logged in: within a second")
        self.assertEqual(win.queued(), ["/xifoventure"])

    def test_another_character(self):
        win = Window(tempfile.mkdtemp())
        win.command("/venture show")
        win.frame(advance=0.05)
        win.queued(clear=True)
        # a zone loads (or the title screen): no character for a while. The files stay where they are.
        win.me = ""
        for _ in range(4):
            win.frame(advance=1.5)
        self.assertEqual(win.marks("Hurami_7"), ["venture.loaded", "venture.open"])
        self.assertEqual(win.queued(), [])
        win.me, win.me_id = "Kaza", 12
        win.frame(advance=1.1)
        self.assertEqual(win.marks("Hurami_7"), [], "another character logs in: the first one's files are removed")
        self.assertEqual(win.marks("Kaza_12"), ["venture.loaded", "venture.open"], "and the new one's say what is so (the window is still shown)")
        self.assertEqual(win.queued(clear=True), ["/xifoventure", "/xifoventure"])
        win.me, win.me_id = "Hurami", 7
        win.command("/venture hide")
        win.frame(advance=1.1)
        self.assertEqual((win.marks("Hurami_7"), win.marks("Kaza_12")), (["venture.loaded"], []))

    def test_unloaded(self):
        win = Window(tempfile.mkdtemp())
        win.command("/venture show")
        win.frame(advance=0.05)
        win.queued(clear=True)
        win.unload()
        self.assertEqual(win.marks(), [], "unloaded: both files are removed")
        self.assertEqual(win.queued(), [], "and nothing is said (nobody could stop the line any more)")

    def test_files_an_earlier_game_left(self):
        ashita = tempfile.mkdtemp()
        os.makedirs(folder(ashita))
        for name in ("venture.loaded", "venture.open"):
            with open(os.path.join(folder(ashita), name), "w") as f:
                f.write("Ventures 1.1\npid=4\n")
        with open(os.path.join(folder(ashita), "gambits.loaded"), "w") as f:
            f.write("Gambits 0.3.9\npid=4\n")
        win = Window(ashita)
        self.assertEqual(win.marks(), ["venture.loaded"], "a venture.open left behind is removed when the add-on loads (its window is shut)")
        self.assertNotIn("pid=4", read(os.path.join(folder(ashita), "venture.loaded")))
        self.assertTrue(os.path.exists(os.path.join(folder(ashita), "gambits.loaded")), "another add-on's file is not touched")

    def test_a_file_that_goes_missing_is_put_back(self):
        win = Window(tempfile.mkdtemp())
        win.command("/venture show")
        win.frame(advance=0.05)
        win.queued(clear=True)
        for name in ("venture.loaded", "venture.open"):
            os.remove(os.path.join(folder(win.ashita), name))
        win.frame(advance=1.1)
        self.assertEqual(win.marks(), ["venture.loaded", "venture.open"],
                         "the menu took the files for an earlier game's (or the folder was tidied): back within a second")
        self.assertEqual(win.queued(clear=True), ["/xifoventure", "/xifoventure"])
        shutil.rmtree(os.path.join(win.ashita, "config", "addons", "xiforever"))
        win.frame(advance=1.1)
        self.assertEqual(win.marks(), ["venture.loaded", "venture.open"], "the whole folder too")

    def test_where_the_menu_looks(self):
        """The folder and the file are what the menu's own helpers (xifo_ui.lua) name and accept."""
        rt = lupa.LuaRuntime(unpack_returned_tuples=True)
        ui = rt.eval("function(p) return dofile(p) end")(MENU_UI)
        for name, cid in (("Hurami", 7), ("Kaza", 4096), ("Abc_def", 1), ("O'Neil", 33), ("Two Words", 2)):
            win = Window(tempfile.mkdtemp(), me=name, me_id=cid)
            want = ui.identity(name, cid)
            self.assertEqual(win.mod.identity(), want)
            there = ui.pref_dir(win.ashita + os.sep, want)
            self.assertTrue(os.path.isfile(there + "venture.loaded"), there)
            self.assertTrue(ui.presence_valid(there + "venture.loaded"))
            self.assertFalse(ui.presence_valid(there + "venture.open"))
            win.command("/venture show")
            win.frame(advance=0.05)
            self.assertTrue(ui.presence_valid(there + "venture.open"))
        for name, cid in (("", 7), ("Hurami", 0), ("   ", 3)):
            win = Window(tempfile.mkdtemp(), me=name, me_id=cid)
            win.me_id = cid
            self.assertIsNone(ui.identity(name, cid))
            self.assertIsNone(win.mod.identity(), (name, cid))

    def test_both_sides_use_the_same_words(self):
        menu = read(os.path.join(KIT, "addons-src", "servermenu", "servermenu.lua"))
        addon = read(os.path.join(ADDON, "venture.lua"))
        self.assertIn("X.VENTURE_SIGNAL = '/xifoventure';", menu)
        self.assertIn("local SIGNAL = '/xifoventure';", addon)
        for word in ("'venture.loaded'", "'venture.open'"):
            self.assertIn(word, menu)
            self.assertIn(word, addon)
        for line in ("'/venture show'", "'/venture hide'", "'/addon load venture'"):
            self.assertIn(line, menu)
        self.assertEqual(re.search(r"addon\.version = '([\d.]+)'", addon).group(1), "1.1")
        self.assertEqual(re.search(r"addon\.version = '([\d.]+)'", menu).group(1), "1.36")


# ---------------------------------------------------------------------------------------------------------------------
class Game:
    """One game with both add-ons, and Ashita's part between them."""

    def __init__(self, ashita=None, who=("Hurami", 7), copied=True, t=T0):
        self.ashita = ashita or tempfile.mkdtemp()
        self.who, self.time = list(who), float(t)
        if copied:                     # what the launcher does at PLAY: the add-on is in Ashita's addons folder, not in its start script
            os.makedirs(os.path.join(self.ashita, "addons", "venture"), exist_ok=True)
            shutil.copy2(os.path.join(ADDON, "venture.lua"), os.path.join(self.ashita, "addons", "venture", "venture.lua"))
        self.rt = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.rt.execute("SQUAD_MENU_UI_LIB = true")
        self.rt.globals().arg = self.rt.table_from({0: MENU_TEST})
        run = self.rt.eval("function(p) return dofile(p) end")
        self.lib = run(MENU_TEST)
        colours = run(MENU_UI).menu("crimson").c
        self.sel, self.busy = self._rgb(colours.sel), self._rgb(colours.busy)
        self.W = self.lib.world(self.rt.table_from({"cfg": "theme=crimson\nbutton_wide=true\n", "dir": self.ashita,
                                                    "who": self.rt.table_from(list(who))}))
        self.venture = None            # the add-on's Lua state, while it is loaded
        self.loads = 0
        self.seen = 0                  # how many of the menu's lines Ashita has handed on
        self.lines, self.game, self.notices = [], [], []
        self.W.command("/menu squad")
        self.lib.feed(self.W)
        self.frame()
        self.frame()

    @staticmethod
    def _rgb(c):
        return tuple(round(c[i], 4) for i in (1, 2, 3))

    # ------------------------------------------------------------------ Ashita
    def frame(self, dt=0.05):
        self.time += dt
        sent = list(self.W.sent.values())
        new, self.seen = sent[self.seen:], len(sent)
        if self.venture is not None:
            new += self.venture.queued(clear=True)
        for line in new:
            self.run(line)
        self.W.frame(dt)
        if self.venture is not None:
            self.venture.frame(advance=dt)

    def run(self, line):
        """A line on its way through Ashita: its own commands, then every add-on in the order they were loaded."""
        self.lines.append(line)
        words = line.lower().split()
        if words[:1] == ["/addon"]:
            if words[1:] == ["load", "venture"]:
                if self.venture is None:
                    self.venture = Window(self.ashita, time=self.time, me=self.who[0], me_id=self.who[1])
                    self.loads += 1
                else:
                    self.notices.append("venture is already loaded")
            elif words[1:] == ["unload", "venture"] and self.venture is not None:
                self.venture.unload()
                self.venture = None
            return
        e = self.rt.table_from({"command": line, "blocked": False})
        self.W.handlers.command(e)
        blocked = bool(e.blocked)
        if self.venture is not None:
            e = self.venture.lua.table_from({"command": line, "blocked": blocked})
            self.venture.handlers["command"](e)
            blocked = bool(e.blocked)
        if not blocked:
            self.game.append(line)

    # ------------------------------------------------------------------ the player
    def press(self, frames=1):
        self.W.clicks[BTN] = True
        for _ in range(frames):
            self.frame()
        self.W.clicks[BTN] = None        # (a click on a button that was not drawn is not kept for later)

    def relog(self, name, cid):
        self.who = [name, cid]
        self.W.who = self.rt.table_from([name, cid])
        if self.venture is not None:
            self.venture.me, self.venture.me_id = name, cid

    # ------------------------------------------------------------------ what is so
    def look(self):
        """The button as it was drawn in the last frame: None (not drawn), "plain", "busy" or "lit"."""
        c = self.W.look[BTN]
        if c is None:
            return None
        c = self._rgb(c)
        return "lit" if c == self.sel else "busy" if c == self.busy else "plain"

    def shown(self):
        return self.venture is not None and bool(self.venture.mod.V.open[1])

    def until(self, what, limit=400, dt=0.05):
        """Frames until the button looks like `what`."""
        n = 0
        while self.look() != what and n < limit:
            self.frame(dt)
            n += 1
        return n

    def asked(self, start):
        """Every line so far that starts like this: those Ashita has handed on, and those the menu has just handed to it."""
        waiting = list(self.W.sent.values())[self.seen:]
        return [line for line in self.lines + waiting if line.lower().startswith(start)]

    def strangers(self):
        """Lines the game was handed that are not the menu's own squad lines: each one is a "command error" in the chat log."""
        return [line for line in self.game if not line.startswith("/say !")]

    def said(self):
        out = [str(p) for p in self.W.prints.values()][1:]             # (the first is the menu's "loaded" line)
        if self.venture is not None:
            out += self.venture.printed()
        return out

    def marks(self):
        d = folder(self.ashita, f"{self.who[0]}_{self.who[1]}")
        return sorted(n for n in ("venture.loaded", "venture.open") if os.path.exists(os.path.join(d, n)))


@unittest.skipIf(Window is None, f"lupa or Pillow is not installed ({WHY})")
class Together(unittest.TestCase):
    def test_off_until_the_button_is_clicked(self):
        g = Game()
        for _ in range(40):
            g.frame(0.5)
        self.assertIsNone(g.venture, "nothing loads the add-on by itself")
        self.assertEqual(g.look(), "plain")
        self.assertEqual((g.marks(), g.asked("/addon"), g.asked("/venture"), g.strangers(), g.said()), ([], [], [], [], []))
        self.assertFalse(os.path.exists(os.path.join(g.ashita, "config", "addons", "venture")), "and nothing of it is on the disk")

    def test_without_the_add_on_there_is_no_button(self):
        g = Game(copied=False)
        self.assertIsNone(g.look())
        g.press(3)
        self.assertEqual((g.asked("/addon"), g.asked("/venture")), ([], []))

    def test_first_click_loads_it_and_shows_the_window(self):
        g = Game()
        g.press()
        self.assertEqual(g.asked("/addon"), ["/addon load venture"])
        n = g.until("lit", limit=40)
        self.assertLessEqual(n, 6, "the window is up a few frames after the click")
        self.assertTrue(g.shown())
        self.assertTrue(g.venture.has("Waiting for the launcher"), "and it is drawn")
        self.assertEqual(g.marks(), ["venture.loaded", "venture.open"])
        self.assertEqual(g.asked("/addon") + g.asked("/venture"), ["/addon load venture", "/venture show"])
        for _ in range(30):
            g.frame(0.4)
        self.assertEqual(g.look(), "lit")
        self.assertEqual(g.asked("/addon") + g.asked("/venture"), ["/addon load venture", "/venture show"], "nothing is sent twice")
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (1, [], [], []))

    def test_click_again_shuts_it_and_the_third_opens_it_without_loading(self):
        g = Game()
        g.press()
        g.until("lit")
        g.press()
        self.assertEqual(g.asked("/venture")[-1], "/venture hide")
        self.assertLessEqual(g.until("plain", limit=40), 6)
        self.assertFalse(g.shown())
        self.assertIsNotNone(g.venture, "the add-on stays loaded: only its window is shut")
        self.assertEqual(g.marks(), ["venture.loaded"])
        g.press()
        self.assertLessEqual(g.until("lit", limit=40), 6)
        self.assertTrue(g.shown())
        self.assertEqual(g.asked("/addon") + g.asked("/venture"), ["/addon load venture", "/venture show", "/venture hide", "/venture show"])
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (1, [], [], []))

    def test_clicks_while_it_waits_do_nothing(self):
        g = Game()
        g.W.clicks[BTN] = True
        g.W.frame(0.05)                    # the click is taken; Ashita has not handed "/addon load venture" on yet
        for _ in range(3):
            g.W.clicks[BTN] = True
            g.W.frame(0.05)
            self.assertEqual(g.look(), "busy")
        g.W.clicks[BTN] = None
        g.until("lit", limit=40)
        self.assertEqual(g.asked("/addon") + g.asked("/venture"), ["/addon load venture", "/venture show"])
        self.assertEqual((g.loads, g.notices, g.strangers()), (1, [], []))

    def test_the_window_opened_and_shut_in_other_ways(self):
        g = Game()
        g.press()
        g.until("lit")
        g.run("/venture")                  # typed by the player
        self.assertLessEqual(g.until("plain", limit=40), 3, "/venture shut the window: the button follows in a frame or two")
        g.run("/venture")
        self.assertLessEqual(g.until("lit", limit=40), 3)
        g.venture.click_x()
        self.assertLessEqual(g.until("plain", limit=40), 3, "its own X")
        g.run("/venture size 2.5")
        self.assertLessEqual(g.until("lit", limit=40), 3)
        self.assertEqual((g.notices, g.strangers()), ([], []))

    def test_the_menu_shut_and_opened(self):
        g = Game()
        g.press()
        g.until("lit")
        g.run("/menu")                     # the Squads menu is shut: its button is not drawn
        g.frame()
        self.assertIsNone(g.look())
        g.run("/venture hide")
        for _ in range(5):
            g.frame(0.01)
        g.run("/menu")
        g.frame()
        self.assertEqual(g.look(), "plain", "shut while the menu was shut: right in the menu's first frame again")
        g.run("/menu")
        g.frame()
        g.run("/venture show")
        g.frame()
        g.frame()
        g.run("/menu")
        g.frame()
        self.assertEqual(g.look(), "lit")

    def test_unloaded_by_hand(self):
        g = Game()
        g.press()
        g.until("lit")
        g.run("/addon unload venture")
        self.assertEqual(g.marks(), [])
        self.assertLessEqual(g.until("plain", limit=100, dt=0.05) * 0.05, 1.11, "the add-on is gone: the button is plain within a second")
        g.press()
        g.until("lit", limit=40)
        self.assertTrue(g.shown())
        self.assertEqual(g.asked("/addon"), ["/addon load venture", "/addon unload venture", "/addon load venture"])
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (2, [], [], []))

    def test_loaded_with_the_game(self):
        """Switched on in OPTIONS > Addons (or loaded by hand before the menu looked): the button only shows the window."""
        g = Game()
        g.run("/addon load venture")
        for _ in range(3):
            g.frame()
        self.assertEqual(g.look(), "plain")
        g.press()
        self.assertLessEqual(g.until("lit", limit=40), 4)
        self.assertEqual(g.asked("/addon") + g.asked("/venture"), ["/addon load venture", "/venture show"])
        self.assertEqual((g.loads, g.notices, g.strangers()), (1, [], []))

    def test_a_game_closed_with_the_window_open(self):
        """No unload: both files stay. The next game cannot tell them from its own (same process id, the worst case)."""
        g = Game()
        g.press()
        g.until("lit")
        g = Game(ashita=g.ashita)
        self.assertEqual(g.marks(), ["venture.loaded", "venture.open"])
        self.assertEqual(g.look(), "lit", "(the button believes the files)")
        g.press()
        self.assertEqual(g.asked("/venture"), ["/venture hide"])
        t = g.until("plain", limit=400, dt=0.02) * 0.02
        self.assertTrue(2.0 <= t <= 2.6, f"nobody answers: after two seconds the files are taken for what they are ({t:.2f} s)")
        self.assertEqual(g.marks(), [])
        self.assertEqual(g.strangers(), ["/venture hide"], "the game saw one line it does not know, once")
        g.press()
        self.assertLessEqual(g.until("lit", limit=40), 6, "and the next click loads the add-on and shows its window")
        self.assertTrue(g.shown())
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (1, [], ["/venture hide"], []))

    def test_a_game_closed_with_the_add_on_loaded(self):
        g = Game()
        g.press()
        g.until("lit")
        g.press()
        g.until("plain")
        g = Game(ashita=g.ashita)
        self.assertEqual(g.marks(), ["venture.loaded"])
        self.assertEqual(g.look(), "plain")
        g.press()
        self.assertEqual(g.asked("/venture"), ["/venture show"], "(the click believes the file)")
        t = g.until("lit", limit=400, dt=0.02) * 0.02
        self.assertTrue(2.0 <= t <= 2.8, f"nobody answers: after two seconds the add-on is loaded for real, and its window shown ({t:.2f} s)")
        self.assertTrue(g.shown())
        self.assertEqual(g.asked("/addon") + g.asked("/venture"), ["/addon load venture", "/venture show", "/venture show"])
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (1, [], ["/venture show"], []))

    def test_the_game_stands_still(self):
        """A zone loading or a minimised window: seconds pass without a frame. That is not an unanswered line."""
        g = Game()
        g.press()
        g.until("lit")
        g.press()
        g.until("plain")
        for want in ("lit", "plain", "lit", "plain"):
            g.W.clicks[BTN] = True
            g.frame(0.05)                  # the click is taken in this frame ...
            g.W.clicks[BTN] = None
            g.frame(30)                    # ... and then the game stands still: a minute goes by in two frames
            g.frame(30)
            self.assertLessEqual(g.until(want, limit=10), 4, want)
            self.assertEqual(g.shown(), want == "lit")
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said(), g.marks()[:1]), (1, [], [], [], ["venture.loaded"]))
        # the same while the add-on is loading
        g = Game()
        g.W.clicks[BTN] = True
        g.frame(0.05)
        g.W.clicks[BTN] = None
        g.frame(45)
        self.assertLessEqual(g.until("lit", limit=10), 6)
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (1, [], [], []))

    def test_another_character(self):
        g = Game()
        g.press()
        g.until("lit")
        g.relog("", 0)                     # logging out: nobody for a while
        for _ in range(10):
            g.frame(1.0)
        g.relog("Kaza", 12)
        for _ in range(8):
            g.frame(0.5)
        self.assertEqual(g.marks(), ["venture.loaded", "venture.open"], "the add-on's files are in the new character's folder")
        self.assertEqual(g.look(), "lit", "and the button says what is so for that character (the window was left open)")
        g.press()
        self.assertLessEqual(g.until("plain", limit=40), 6)
        self.assertFalse(g.shown())
        g.press()
        g.until("lit", limit=40)
        self.assertEqual((g.loads, g.notices, g.strangers(), g.said()), (1, [], [], []))
        self.assertEqual(sorted(os.listdir(folder(g.ashita, "Hurami_7"))), ["ui.cfg"] if os.path.exists(os.path.join(folder(g.ashita, "Hurami_7"), "ui.cfg")) else [])

    def test_with_the_launcher_the_window_has_the_squad(self):
        import json
        import launcher_ventures as LV
        from test_venture_addon import World
        keep = LV.deliver, LV.build_roster
        try:
            g = Game()
            box = {}
            LV.deliver = lambda conn, char, items, log=print: True
            LV.build_roster = lambda conn: json.loads(json.dumps(box["world"].roster))
            w = box["world"] = World.__new__(World)
            World.__init__(w, ashita=g.ashita)               # the launcher: its relay, and a roster with Hurami's four mates
            self.assertEqual(g.look(), "plain")
            g.press()
            g.until("lit", limit=40)
            for _ in range(2):
                w.launcher(2)
                for _ in range(20):
                    g.frame(0.1)
            self.assertTrue(g.venture.has("SEND HURAMI'S SQUAD") and g.venture.has("Volker") and g.venture.has("Shantotto"),
                            "the Ventures screen, with this character's squad mates")
            self.assertEqual((g.said(), w.logs), ([], []))
        finally:
            LV.deliver, LV.build_roster = keep

    def test_anything_in_any_order(self):
        """Clicks, typed commands, the X, unloading, the menu shut, a game that stands still: whenever things have
        settled the button says what is so, the add-on is never loaded twice, and the game is never handed a line."""
        for seed in range(16):
            rnd = random.Random(seed)
            g = Game()
            menu_open = True
            for step in range(140):
                what = rnd.choice(("press", "press", "press", "press", "typed", "typed", "x", "unload", "menu", "still", "wait", "wait"))
                slow = 0.0
                if what == "press":
                    g.press()
                elif what == "typed" and g.venture is not None:
                    g.run(rnd.choice(("/venture", "/venture show", "/venture hide", "/venture", "/ventures toggle")))
                elif what == "x" and g.shown():
                    g.venture.click_x()
                elif what == "unload" and g.venture is not None and rnd.random() < 0.4:
                    g.run("/addon unload venture")
                    slow = 1.2             # (no line is said for this one: the button looks once a second)
                elif what == "menu":
                    g.run("/menu")
                    menu_open = not menu_open
                elif what == "still":
                    g.frame(rnd.uniform(3, 90))
                else:
                    for _ in range(rnd.randint(1, 25)):
                        g.frame(rnd.uniform(0.004, 0.25))
                for _ in range(8):
                    g.frame(rnd.uniform(0.01, 0.06))
                while slow > 0:
                    g.frame(0.1)
                    slow -= 0.1
                where = f"seed {seed}, step {step} ({what})"
                self.assertEqual(g.look() is not None, menu_open, where)
                if menu_open:
                    self.assertEqual(g.look(), "lit" if g.shown() else "plain", where)
                self.assertEqual(g.marks(), ([] if g.venture is None else ["venture.loaded"] + (["venture.open"] if g.shown() else [])), where)
                self.assertEqual((g.notices, g.strangers(), g.said()), ([], [], []), where)


if __name__ == "__main__":
    unittest.main()
