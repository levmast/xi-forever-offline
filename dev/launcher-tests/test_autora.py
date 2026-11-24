"""autora (auto ranged attack, 2026-11-23, JØ): the add-on in LuaJIT with a stand-in game. Shoots once per finished
shot, waits while busy or moving, needs a ranged weapon or ammo, and in "Until hate" holds while the monster attacks
you. Run: python3 dev/launcher-tests/test_autora.py"""
import os
import tempfile
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ME, MOB, TANK = 0x01000001, 0x0100A001, 0x01000002


def action_packet(actor, category, param, targets):
    """A 0x028 packet: header (4 bytes), size, actor, then bit-packed fields; one action per target."""
    bits = []

    def put(value, count):
        for i in range(count):
            bits.append((value >> i) & 1)
    put(0, 32)                                   # header
    put(0, 8)                                    # size
    put(actor, 32)                               # bits 40..71
    put(len(targets), 10)                        # 72
    put(category, 4)                             # 82
    put(param, 16)                               # 86
    put(0, 150 - 102)
    for t in targets:
        put(t, 32)
        put(1, 4)
        put(0, 86)                               # one action, no additional effect (bit 85 = 0)
        put(0, 1)                                # no spikes
    while len(bits) % 8:
        bits.append(0)
    return bytes(sum(bits[i + j] << j for j in range(8)) for i in range(0, len(bits), 8))


class AutoRATests(unittest.TestCase):
    def setUp(self):
        from lupa import luajit21 as lupa
        self.lua = lua = lupa.LuaRuntime()
        lua.execute("""
            CLOCK = 100; sent = {}; events = {}; G = { status = 1, ranged = 7, x = 0, mobflags = 0x10, hpp = 100 }
            os.clock = function() return CLOCK end
            addon = {}
            local party = { GetMemberServerId = function() return %d end, GetMemberTargetIndex = function() return 1 end }
            local entity = { GetStatus = function(self, i) return G.status end,
                GetServerId = function(self, i) return %d end, GetSpawnFlags = function() return G.mobflags end,
                GetHPPercent = function() return G.hpp end,
                GetLocalPositionX = function() return G.x end, GetLocalPositionY = function() return 0 end }
            local target = { GetIsSubTargetActive = function() return 0 end, GetTargetIndex = function() return 300 end }
            local inv = { GetEquippedItem = function(self, slot) return { Index = (slot == 2) and G.ranged or 0 } end }
            local mm = { GetParty = function() return party end, GetEntity = function() return entity end,
                GetTarget = function() return target end, GetInventory = function() return inv end }
            AshitaCore = { GetInstallPath = function() return INSTALL end, GetMemoryManager = function() return mm end,
                GetChatManager = function() return { QueueCommand = function(self, mode, cmd) sent[#sent+1] = cmd end } end }
            ashita = { events = { register = function(ev, name, fn) events[ev] = fn end }, fs = {} }
            package.preload['common'] = function() string.args = function(s) local t = {} for w in s:gmatch('%%S+') do t[#t+1] = w end return t end end
            package.preload['imgui'] = function() return setmetatable({}, { __index = function() return function() return false end end }) end
            print = function(...) end
        """ % (ME, MOB))
        lua.globals().INSTALL = tempfile.mkdtemp() + "/"
        lua.globals().ashita.fs.create_directory = lambda path: os.makedirs(path, exist_ok=True) or True
        with open(os.path.join(KIT, "addons-src", "autora", "autora.lua"), encoding="utf-8") as f:
            lua.execute(f.read())
        lua.execute("events.load()")

    def step(self, seconds=0.25):
        self.lua.execute(f"CLOCK = CLOCK + {seconds}; events.d3d_present()")

    def sent(self):
        return len(self.lua.eval("sent"))

    def packet(self, actor, category, targets, param=0):
        self.lua.globals().PKT = action_packet(actor, category, param, targets)
        self.lua.execute("events.packet_in({ id = 0x028, data = PKT })")

    def command(self, text):
        self.lua.execute(f"events.command({{ command = '{text}', blocked = false }})")

    def test_manual_does_nothing(self):
        for _ in range(10):
            self.step()
        self.assertEqual(self.sent(), 0)

    def test_auto_shoots_after_each_shot(self):
        self.command("/autora auto")
        self.step()
        self.assertEqual(self.sent(), 1)
        self.assertEqual(self.lua.eval("sent[1]"), "/ra <t>")
        for _ in range(8):
            self.step()
        self.assertEqual(self.sent(), 1)                 # waits for the shot
        self.packet(ME, 12, [MOB])
        self.packet(ME, 2, [MOB])
        self.step(0.25)
        self.assertEqual(self.sent(), 1)                 # the pause after the shot (0.5 s)
        self.step(0.5)
        self.assertEqual(self.sent(), 2)

    def test_needs_ranged_engaged_and_standing_still(self):
        self.command("/autora auto")
        self.lua.execute("G.ranged = 0")
        self.step()
        self.assertEqual(self.sent(), 0)
        self.lua.execute("G.ranged = 7; G.status = 0")
        self.step()
        self.assertEqual(self.sent(), 0)
        self.lua.execute("G.status = 1; G.x = 5")
        self.step()
        self.lua.execute("G.x = 6")
        self.step()
        self.assertEqual(self.sent(), 0)                 # moving
        self.step(0.5)
        self.assertEqual(self.sent(), 1)

    def test_until_hate(self):
        self.command("/autora hate")
        self.packet(MOB, 1, [ME])                        # the monster hits you
        for _ in range(8):
            self.step()
        self.assertEqual(self.sent(), 0)
        self.packet(MOB, 1, [TANK])                      # the tank has it back
        self.step()
        self.assertEqual(self.sent(), 1)

    def test_mode_is_kept(self):
        self.command("/autora hate")
        path = self.lua.globals().INSTALL + "config/addons/autora/settings.txt"
        self.assertIn("mode=hate", open(path).read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
