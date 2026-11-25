"""Stinkshell (2026-11-23): the relay, the launcher bridge against a real relay on this machine, and the add-on's file
format read by Lua. Run: python3 dev/launcher-tests/test_stinkshell.py"""
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "dev", "stinkshell"))
import stinkshell_relay as relay   # noqa: E402
import launcher_stinkshell as stink  # noqa: E402

relay.POLL_WAIT = 1


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.room = relay.Room(self.tmp)

    def kh(self, n):
        return relay.keyhash("%032x" % n)

    def test_first_come_keeps_the_name(self):
        self.assertEqual(self.room.screen_for(self.kh(1), "Hurami"), "Hurami")
        self.assertEqual(self.room.screen_for(self.kh(2), "Hurami"), "Hurami2")
        self.assertEqual(self.room.screen_for(self.kh(3), "hurami"), "hurami3")
        self.assertEqual(self.room.screen_for(self.kh(1), "Hurami"), "Hurami")      # still his after a restart
        again = relay.Room(self.tmp)
        self.assertEqual(again.screen_for(self.kh(2), "Hurami"), "Hurami2")
        self.assertEqual(self.room.screen_for(self.kh(4), "<b>x"), "Adventurer")

    def test_text_is_cleaned(self):
        self.room.say(self.kh(1), "Hurami", "hi\x1e\x01 there   \n you" + "a" * 500)
        line = [l for l in self.room.lines if l["kind"] == "say"][0]
        self.assertTrue(line["text"].startswith("hi there you"))
        self.assertEqual(len(line["text"]), relay.MAX_TEXT)

    def test_rate_limit(self):
        answers = [self.room.say(self.kh(1), "Hurami", "x%d" % i) for i in range(7)]
        self.assertEqual(sum(1 for a in answers if a.get("ok")), 5)
        self.assertEqual(answers[-1]["error"], "Slow down a little.")

    def test_website_visitors(self):
        """xiforever.com/chat.html (2026-11-23): "website: Nick", never a character name; mods name them in full;
        a ban also covers the visitor's network address."""
        web, game = self.kh(20), self.kh(21)
        self.assertEqual(self.room.screen_for(game, "Hurami"), "Hurami")
        self.assertEqual(self.room.screen_for(web, "Hurami", web=True), "website: Hurami")
        self.assertEqual(self.room.screen_for(self.kh(22), "Hurami", web=True), "website: Hurami2")
        self.assertEqual(self.room.screen_for(self.kh(23), "<i>", web=True), "website: Guest")
        self.assertEqual(relay.web_target(["website:", "Hurami", "5"]), ["website: Hurami", "5"])
        self.assertEqual(relay.web_target(["website:Hurami"]), ["website: Hurami"])
        owner = self.kh(24)
        self.room.say(owner, "Owner", "/login " + self.room.owner_code)
        self.room.note_ip(web, relay.iphash("10.0.0.9"))
        self.room.say(owner, "Owner", "/ban website: Hurami")
        self.assertTrue(self.room.banned(web))
        fresh = self.kh(25)                      # the same visitor after clearing the browser
        self.room.note_ip(fresh, relay.iphash("10.0.0.9"))
        self.assertTrue(self.room.banned(fresh))
        self.assertFalse(self.room.banned(game))  # the player called Hurami is untouched
        self.room.say(owner, "Owner", "/unban website:Hurami")
        self.assertFalse(self.room.banned(fresh))

    def test_owner_mod_codes_mute_ban(self):
        owner, mod, troll = self.kh(1), self.kh(2), self.kh(3)
        self.room.say(troll, "Troll", "hello")
        self.room.say(mod, "Modder", "hey")
        self.room.say(mod, "Modder", "/mute Troll")                       # not a moderator yet
        self.assertFalse(self.room.muted(troll))
        self.room.say(owner, "Hurami", "/login wrong")
        self.assertEqual(self.room.role(owner), "player")
        self.room.say(owner, "Hurami", "/login " + self.room.owner_code)
        self.assertEqual(self.room.role(owner), "owner")
        self.room.say(owner, "Hurami", "/modcode")
        code = list(self.room.state["codes"])[0]
        private = [l for l in self.room.lines if l["to"] == owner and code in l["text"]]
        self.assertTrue(private)
        self.assertFalse(self.room.visible(mod, 0) and any(code in l["text"] for l in self.room.visible(mod, 0)))
        self.room.say(mod, "Modder", "/login " + code)
        self.assertEqual(self.room.role(mod), "mod")
        self.assertNotIn(code, self.room.state["codes"])                   # one use only
        self.room.say(mod, "Modder", "/mute Troll 10")
        self.assertEqual(self.room.say(troll, "Troll", "spam")["error"], "You are muted for now.")
        self.room.say(mod, "Modder", "/ban Hurami")                         # a mod cannot touch the owner
        self.assertFalse(self.room.banned(owner))
        self.room.say(mod, "Modder", "/ban Troll")
        self.assertTrue(self.room.banned(troll))
        # the ban sticks to the launcher, not the name: a new character on the same launcher is still banned
        self.assertEqual(self.room.say(troll, "Newname", "hi")["error"], "You are banned from this room.")
        self.room.say(owner, "Hurami", "/unban Troll")
        self.assertFalse(self.room.banned(troll))
        state = relay.Room(self.tmp).state
        self.assertIn(mod, state["mods"])


class BridgeTests(unittest.TestCase):
    """The launcher's bridge against a real relay on 127.0.0.1 (no HTTPS here; Caddy adds it on the hub)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.room = relay.Room(os.path.join(self.tmp, "relay"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), relay.make_handler(self.room))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()

    def make(self, who):
        kit, ashita = os.path.join(self.tmp, who, "kit"), os.path.join(self.tmp, who, "ashita")
        os.makedirs(kit)
        os.makedirs(ashita)
        bridge = stink.Bridge(kit, ashita, url=self.url)
        bridge.start()
        return bridge

    @staticmethod
    def read(path):
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def wait_for(self, path, needle, seconds=8):
        end = time.time() + seconds
        while time.time() < end:
            if os.path.exists(path) and needle in self.read(path):
                return True
            time.sleep(0.1)
        return False

    def test_two_players_talk(self):
        a, b = self.make("a"), self.make("b")
        try:
            self.assertEqual(len(stink.key_for(a.kit)), 32)
            self.assertEqual(stink.key_for(a.kit), a.key)                  # kept, not made again
            with open(a.path("out.txt"), "a") as f:
                f.write("hello|Hurami|\n")
            with open(b.path("out.txt"), "a") as f:
                f.write("hello|Hurami|\n")
            self.assertTrue(self.wait_for(b.path("people.txt"), "#me|Hurami2"))
            self.assertTrue(self.wait_for(a.path("people.txt"), "#me|Hurami\n"))
            with open(a.path("out.txt"), "a") as f:
                f.write("say|Hurami|ASL? |pipe| test\n")
            self.assertTrue(self.wait_for(b.path("in.txt"), "|say|Hurami|ASL? pipe test|"))
            self.assertTrue(self.wait_for(a.path("in.txt"), "|enter|Hurami2|Hurami2 has entered the room.|"))
            self.assertTrue(self.wait_for(b.path("people.txt"), "Hurami2\n"))
            for line in self.read(b.path("in.txt")).splitlines():
                self.assertEqual(line.count("|"), 4, line)
        finally:
            a.stop()
            b.stop()

    def test_no_relay_says_so(self):
        kit, ashita = os.path.join(self.tmp, "c", "kit"), os.path.join(self.tmp, "c", "ashita")
        os.makedirs(kit)
        os.makedirs(ashita)
        bridge = stink.Bridge(kit, ashita, url="http://127.0.0.1:1")
        bridge.start()
        try:
            with open(bridge.path("out.txt"), "a") as f:
                f.write("hello|Hurami|\n")
            self.assertTrue(self.wait_for(bridge.path("in.txt"), "|system||"))
        finally:
            bridge.stop()


class AddonTests(unittest.TestCase):
    """The add-on in LuaJIT with a stand-in Ashita and imgui: it reads in.txt and people.txt, writes out.txt."""

    def test_addon(self):
        try:
            from lupa import luajit21 as lupa
        except ImportError:
            from lupa import lua54 as lupa
        tmp = tempfile.mkdtemp() + "/"
        folder = tmp + "config/addons/stinkshell/"
        os.makedirs(folder)
        with open(folder + "in.txt", "w") as f:
            f.write("1|enter|Hurami2|Hurami2 has entered the room.|0\n2|say|Hurami2|hi|0\n3|say|Hurami|yo|0\n4|sa")
        with open(folder + "people.txt", "w") as f:
            f.write("#me|Hurami\nHurami\nHurami2\n")
        lua = lupa.LuaRuntime()
        lua.execute("""
            events = {}; drawn = {}; INSTALL = @@PATH@@
            addon = {}
            AshitaCore = { GetInstallPath = function() return INSTALL end,
              GetMemoryManager = function() return { GetParty = function() return {
                  GetMemberName = function(self, i) return 'Hurami' end } end } end }
            ashita = { events = { register = function(ev, name, fn) events[ev] = fn end }, fs = {} }
            package.preload['common'] = function() string.args = function(s) local t = {} for w in s:gmatch('%S+') do t[#t+1] = w end return t end end
            local function nop() return false end
            local im = setmetatable({}, { __index = function() return nop end })
            im.Begin = function() return true end
            im.Text = function(t) drawn[#drawn+1] = t end
            im.TextWrapped = im.Text
            im.InputText = function(label, buf) return false end
            package.preload['imgui'] = function() return im end
            print = function(...) end
        """.replace("@@PATH@@", repr(tmp)))
        with open(os.path.join(KIT, "addons-src", "stinkshell", "stinkshell.lua"), encoding="utf-8") as f:
            lua.execute(f.read())
        lua.execute("events.load(); events.d3d_present()")
        drawn = list(lua.eval("drawn").values())
        self.assertIn("Hurami2:", drawn)
        self.assertIn("hi", drawn)
        self.assertIn("*** Hurami2 has entered the room.", drawn)
        self.assertIn("People Here: 2", drawn)
        self.assertNotIn("sa", drawn)                                     # a half-written line waits
        with open(folder + "out.txt") as f:
            self.assertEqual(f.read(), "hello|Hurami|\n")
        lua.execute("""
            local e = { command = '/sl hey |all| \\1x', blocked = false }
            e.command = e.command  -- string methods
            setmetatable(e, {}); events.command({ command = e.command, blocked = false })
        """)
        with open(folder + "out.txt") as f:
            self.assertEqual(f.read().splitlines()[-1], "say|Hurami|hey all x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
