"""VanaSync (2026-11-25): the vanasync add-on in LuaJIT with a stand-in Ashita, and launcher_vanasync's start/stop.
Run: python3 dev/launcher-tests/test_vanasync.py   (the add-on part needs `pip install lupa`; skipped without it)"""
import json
import os
import socket
import sys
import tempfile
import types
import unittest
import urllib.request

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
import launcher_vanasync as vs  # noqa: E402

ADDON = os.path.join(KIT, "addons-src", "vanasync", "vanasync.lua")

STANDIN = r"""
sent, injected, events, printed = {}, {}, {}, {}
replies = {}
clock = 100.0
status, members, zone = 0, 1, 230
addon = { path = '' }
package.loaded['common'] = true
function string.args(s) local t = {} for w in s:gmatch('%S+') do t[#t+1] = w end return t end
package.loaded['socket'] = {
  gettime = function() return clock end,
  udp = function() return {
    settimeout = function() end, setpeername = function() end, close = function() end,
    send = function(_, d) sent[#sent+1] = d end,
    receive = function() return table.remove(replies, 1) end } end }
ashita = { events = { register = function(name, _, fn) events[name] = fn end } }
AshitaCore = {
  GetPacketManager = function() return { AddIncomingPacket = function(_, id, bytes)
    injected[#injected+1] = { id = id, bytes = bytes } end } end,
  GetMemoryManager = function() return { GetParty = function() return {
    GetMemberIsActive = function(_, i) return i < members and 1 or 0 end,
    GetMemberZone = function() return zone end } end } end }
function GetPlayerEntity() return { Status = status } end
print = function(s) printed[#printed+1] = s end
"""


def lua_runtime():
    try:
        from lupa import luajit21 as lupa
    except ImportError:
        return None
    lua = lupa.LuaRuntime()
    lua.execute(STANDIN)
    with open(ADDON, encoding="utf-8") as handle:
        lua.execute(handle.read())
    lua.globals().events["load"]()
    return lua


@unittest.skipIf(lua_runtime() is None, "lupa not installed")
class AddonTests(unittest.TestCase):
    def setUp(self):
        self.lua = lua_runtime()
        self.g = self.lua.globals()

    def frame(self, seconds=0.3, reply=None):
        self.g.clock = self.g.clock + seconds
        if reply is not None:
            self.lua.eval("function(r) replies[#replies+1] = r end")(json.dumps({"own": reply}))
        self.g.events["d3d_present"]()

    def injected(self):
        out = []
        for i in range(1, len(self.g.injected) + 1):
            item = self.g.injected[i]
            out.append((item.id, [item.bytes[j] for j in range(1, 9)]))
        return out

    def last_snapshot(self):
        return json.loads(self.g.sent[len(self.g.sent)])

    def test_sends_state(self):
        self.g.status, self.g.members = 1, 4
        self.frame()
        snap = self.last_snapshot()
        self.assertEqual(snap, {"v": 1, "engaged": True, "cutscene": False, "members": 4, "alliance": False, "zone": 230})
        self.g.members, self.g.status = 9, 4
        self.frame()
        snap = self.last_snapshot()
        self.assertTrue(snap["alliance"])
        self.assertTrue(snap["cutscene"])
        self.assertEqual(snap["members"], 9)

    def test_nothing_injected_without_player(self):
        for _ in range(10):
            self.frame()
        self.assertEqual(self.injected(), [])

    def test_fades_out_while_owned_and_back_when_silent(self):
        self.frame(reply=True)
        # 0x060, size 8 bytes = 2 words: header 0x060 | 2 << 9 = 0x0460; time 30; volume 0
        self.assertEqual(self.injected(), [(0x60, [0x60, 0x04, 0, 0, 30, 0, 0, 0])])
        self.frame(reply=True)
        self.assertEqual(len(self.injected()), 1)        # sent once, not every frame
        self.frame(seconds=2.0)                           # no reply for 2 s: the player went away
        self.assertEqual(self.injected()[-1], (0x60, [0x60, 0x04, 0, 0, 30, 0, 127, 0]))

    def test_asks_again_while_owned(self):
        # (2026-11-26, Zaltyz525, JØ: the game's battle theme played underneath) one request is not enough
        self.frame(reply=True)
        self.frame(seconds=0.5, reply=True)
        self.assertEqual(len(self.injected()), 1)
        self.frame(seconds=0.6, reply=True)               # a second has passed: asked again, at once (time 0)
        self.assertEqual(self.injected()[-1], (0x60, [0x60, 0x04, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(len(self.injected()), 2)

    def test_combat_change_asks_faster(self):
        self.frame(reply=True)
        self.g.status = 1                                 # a fight starts: the game puts its battle theme on
        before = len(self.injected())
        for _ in range(4):
            self.frame(seconds=0.3, reply=True)
        self.assertGreaterEqual(len(self.injected()) - before, 3)
        self.assertTrue(all(b[6] == 0 for _, b in self.injected()))
        for _ in range(8):                                # the burst is over: back to once a second
            self.frame(seconds=0.3, reply=True)
        count = len(self.injected())
        self.frame(seconds=0.3, reply=True)
        self.frame(seconds=0.3, reply=True)
        self.assertLessEqual(len(self.injected()) - count, 1)

    def test_full_volume_asked_again_after_handing_back_then_quiet(self):
        self.frame(reply=True)
        self.frame(reply=False)
        self.assertEqual(self.injected()[-1], (0x60, [0x60, 0x04, 0, 0, 30, 0, 127, 0]))
        for _ in range(3):
            self.frame(seconds=1.05)
        self.assertEqual([b[6] for _, b in self.injected()], [0, 127, 127, 127])
        self.assertEqual(self.injected()[-1][1][4], 0)    # the repeats do not fade
        for _ in range(5):
            self.frame(seconds=1.05)
        self.assertEqual(len(self.injected()), 4)         # and then it is left alone

    def test_untouched_music_is_never_touched(self):
        for _ in range(10):
            self.frame(seconds=1.0, reply=False)
        self.assertEqual(self.injected(), [])

    def test_player_says_not_owner(self):
        self.frame(reply=True)
        self.frame(reply=False)
        self.assertEqual(self.injected()[-1][1][6], 127)

    def test_zoning_asks_again(self):
        self.frame(reply=True)
        self.g.events["packet_in"](self.lua.table_from({"id": 0x0A}))
        self.frame(reply=True)
        self.assertEqual([b[6] for _, b in self.injected()], [0, 0])

    def test_restore_hold_and_unload(self):
        self.frame(reply=True)
        cmd = self.lua.table_from({"command": "/vanasync restore", "blocked": False})
        self.g.events["command"](cmd)
        self.assertTrue(cmd.blocked)
        self.frame(reply=True)
        self.assertEqual([b[6] for _, b in self.injected()], [0, 127])
        self.g.events["command"](self.lua.table_from({"command": "/vanasync restore"}))
        self.frame(reply=True)
        self.g.events["unload"]()
        self.assertEqual([b[6] for _, b in self.injected()], [0, 127, 0, 127])

    def test_open_asks_for_the_player_window(self):
        # (2026-11-26, Hexblood) /vanasync open: the next three snapshots carry "open": true, then it stops asking
        self.frame(reply=False)                           # the player answers: connected
        for command in ("/vanasync open", "/vsync show"):
            cmd = self.lua.table_from({"command": command, "blocked": False})
            self.g.events["command"](cmd)
            self.assertTrue(cmd.blocked)
            asked = []
            for _ in range(4):
                self.frame(reply=False)
                asked.append(self.last_snapshot().get("open") is True)
            self.assertEqual(asked, [True, True, True, False])
            self.assertIn("Opening the VanaSync player", self.g.printed[len(self.g.printed)])
        self.assertEqual(self.injected(), [])             # asking for the window never touches the music

    def test_open_without_the_player_says_so(self):
        cmd = self.lua.table_from({"command": "/vanasync open", "blocked": False})
        self.g.events["command"](cmd)
        self.assertTrue(cmd.blocked)
        self.frame()
        self.assertNotIn("open", self.last_snapshot())
        self.assertIn("not running", self.g.printed[len(self.g.printed)])

    def test_other_commands_pass_through(self):
        cmd = self.lua.table_from({"command": "/echo hi", "blocked": False})
        self.g.events["command"](cmd)
        self.assertFalse(cmd.blocked)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.on = False
        fake = types.ModuleType("launcher_core")
        test = self

        class ScriptManager:
            def __init__(self, *_):
                pass

            def enabled(self, kind):
                return {"vanasync"} if test.on else set()
        fake.ScriptManager = ScriptManager
        self.saved = sys.modules.get("launcher_core")
        sys.modules["launcher_core"] = fake
        self.ports = (vs.PORT, vs.GAME_PORT)
        vs.PORT, vs.GAME_PORT = free_port(socket.SOCK_STREAM), free_port(socket.SOCK_DGRAM)
        self.opened = []
        self.real_open = vs.Player.open_window
        vs.Player.open_window = lambda player: self.opened.append(player)
        os.environ["LOCALAPPDATA"] = self.tmp.name
        self.state, self.logs = {}, []

    def tearDown(self):
        vs.stop(self.state)
        vs.Player.open_window = self.real_open
        vs.PORT, vs.GAME_PORT = self.ports
        if self.saved is not None:
            sys.modules["launcher_core"] = self.saved
        else:
            sys.modules.pop("launcher_core", None)
        self.tmp.cleanup()

    def tick(self, running=True):
        vs.tick(self.state, KIT, "ashita", "boot", running, log=self.logs.append)

    def test_off_by_default(self):
        self.tick()
        self.assertNotIn("player", self.state)
        self.assertEqual(self.opened, [])

    def test_starts_with_addon_and_world_then_stops(self):
        self.on = True
        self.tick(running=False)
        self.assertNotIn("player", self.state)
        self.tick()
        self.assertIn("player", self.state)
        self.assertEqual(len(self.opened), 1)
        with urllib.request.urlopen(urllib.request.Request(
                f"http://127.0.0.1:{vs.PORT}/api/game", headers={"Host": f"127.0.0.1:{vs.PORT}"})) as r:
            self.assertEqual(json.load(r)["live"], False)
        self.tick()
        self.assertEqual(len(self.opened), 1)             # not opened twice
        self.on = False
        self.tick()
        self.assertNotIn("player", self.state)

    def test_world_stop_closes(self):
        self.on = True
        self.tick()
        self.tick(running=False)
        self.assertNotIn("player", self.state)

    def test_port_in_use_tries_once_per_session(self):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", vs.PORT))
        blocker.listen()
        try:
            self.on = True
            self.tick()
            self.tick()
            self.assertNotIn("player", self.state)
            self.assertEqual(len([line for line in self.logs if "could not start" in line]), 1)
            self.tick(running=False)
            self.assertNotIn("failed", self.state)
        finally:
            blocker.close()

    def ask_open(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(5)
        try:
            probe.sendto(json.dumps({"v": 1, "engaged": False, "cutscene": False, "members": 1, "alliance": False,
                                     "zone": 230, "open": True}).encode(), ("127.0.0.1", vs.GAME_PORT))
            probe.recvfrom(1024)                          # answered: the host has read it
        finally:
            probe.close()

    def test_open_request_opens_the_window_again_once(self):
        # (2026-11-26, Hexblood) /vanasync open in game: tick() opens the player window again, once per request
        self.on = True
        self.tick()
        self.tick()
        self.assertEqual(len(self.opened), 1)             # nothing asked, nothing opened
        self.ask_open()
        self.tick()
        self.assertEqual(len(self.opened), 2)
        self.ask_open()                                   # the add-on sends the request three times: still one window
        self.tick()
        self.assertEqual(len(self.opened), 2)

    def test_reopen_closes_our_window_first_and_leaves_a_browser_tab_alone(self):
        self.on = True
        self.tick()
        player = self.state["player"]

        class Window:
            closed = False

            def poll(self):
                return 1 if self.closed else None

            def terminate(self):
                self.closed = True

            def wait(self, timeout=None):
                return 0
        window = player.window = Window()
        player.reopen()
        self.assertTrue(window.closed)                    # never two players at once
        self.assertEqual(len(self.opened), 2)
        real_find = vs.find_edge
        vs.find_edge = lambda: None                       # no Edge or Chrome: the player is a tab in the browser
        try:
            player.window = None
            player.server.game.seen_page()                # the tab is still asking for the game's state
            player.reopen()
            self.assertEqual(len(self.opened), 2)
            self.assertTrue(any("already open" in line for line in self.logs))
            player.server.game.page_at -= vs.Player.PAGE_FRESH + 1   # the tab was closed a while ago
            player.reopen()
            self.assertEqual(len(self.opened), 3)
        finally:
            vs.find_edge = real_find

    def test_window_command(self):
        cmd = vs.window_command("msedge.exe", "D:\\data")
        self.assertIn("--autoplay-policy=no-user-gesture-required", cmd)
        self.assertTrue(any(a.startswith("--app=http://127.0.0.1:") and a.endswith("/?live=1") for a in cmd))
        self.assertTrue(any(a.startswith("--user-data-dir=") for a in cmd))


def free_port(kind):
    probe = socket.socket(socket.AF_INET, kind)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


if __name__ == "__main__":
    unittest.main()
