"""squad_ventures.lua with a stand-in game (python3 dev/ventures/test_squad_ventures.py; needs lupa)."""
import os
import tempfile
import time
import unittest

from lupa import LuaRuntime

HERE = os.path.dirname(os.path.abspath(__file__))


class SquadVentures(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp() + "/"
        os.makedirs(self.kit + "ventures")
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("""
            package.preload['modules/custom/lua/kit_paths'] = function() return { kit = KIT } end
            xi = { objType = { TRUST = 2 } }
            said, gil, levels, dismissed = {}, 0, {}, {}
            function AddSquadExp(id, job, gain, cap)
                levels[id] = (levels[id] or 0) + gain
                if gain >= 3000 then return { gained = 1, level = 21 } end
                return { gained = 0, level = 20 }
            end
            trust = { getObjType = function() return 2 end, getLocalVar = function(_, k) return 11 end }
            player = {
                getName = function() return 'Hurami' end, getID = function() return 1 end,
                addGil = function(_, n) gil = gil + n end,
                getPartyWithTrusts = function() return { trust } end,
            }
            squad = { { id = 11, slot = 1, name = 'Ayame', mjob = 1 }, { id = 12, slot = 2, name = 'Naji', mjob = 3 } }
            function say(p, text) said[#said + 1] = text end
            function dismiss(m) dismissed[#dismissed + 1] = m end
        """.replace("KIT", repr(self.kit)))
        self.V = self.lua.execute("return dofile(%r)" % os.path.join(HERE, "squad_ventures.lua"))

    def write(self, name, text):
        with open(self.kit + "ventures/" + name, "w") as f:
            f.write(text)

    def said(self):
        t = self.lua.eval("said")
        return [t[i] for i in range(1, len(t) + 1)]

    def test_away_blocks_calling_and_sends_home(self):
        self.write("away.txt", f"Hurami|1|{int(time.time()) + 5400}|Qufim Island (the shore)\n")
        line = self.V.away(self.lua.eval("player"), self.lua.eval("squad[1]"))
        self.assertIn("Ayame is away on a venture at Qufim Island", line)
        self.assertIn("1h 3", line)
        self.assertIsNone(self.V.away(self.lua.eval("player"), self.lua.eval("squad[2]")))
        self.V.look(self.lua.eval("player"), self.lua.eval("squad"), self.lua.eval("dismiss"), self.lua.eval("say"))
        self.assertEqual(len(self.lua.eval("dismissed")), 1)
        self.assertIn("heads off on a venture", self.said()[0])

    def test_takes_in_once(self):
        self.write("in.txt", "v1|Hurami|120|Qufim Island|1:6000,2:6000\nv2|Someone|5|X|1:10\n")
        for _ in range(2):
            self.V.look(self.lua.eval("player"), self.lua.eval("squad"), self.lua.eval("dismiss"), self.lua.eval("say"))
        self.assertEqual(self.lua.eval("gil"), 120)
        self.assertEqual(self.lua.eval("levels[11]"), 6000)
        self.assertEqual(self.lua.eval("levels[12]"), 6000)
        text = " ".join(self.said())
        self.assertIn("Ayame and Naji are back from Qufim Island!", text)
        self.assertIn("reaches level 21", text)
        self.assertIn("6,000 exp", text)
        with open(self.kit + "ventures/out.txt") as f:
            self.assertEqual(f.read(), "v1|ok\n")

    def test_already_done_in_out_file(self):
        self.write("out.txt", "v1|ok\n")
        self.write("in.txt", "v1|Hurami|120|Qufim Island|1:6000\n")
        V = self.lua.execute("return dofile(%r)" % os.path.join(HERE, "squad_ventures.lua"))
        V.look(self.lua.eval("player"), self.lua.eval("squad"), self.lua.eval("dismiss"), self.lua.eval("say"))
        self.assertEqual(self.lua.eval("gil"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
