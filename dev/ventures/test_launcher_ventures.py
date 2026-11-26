"""The launcher's venture relay with a stand-in hub and game (python3 dev/ventures/test_launcher_ventures.py)."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
import launcher_armory as A  # noqa: E402
import launcher_ventures as LV  # noqa: E402


class Relay(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        data = A.load(self.kit)
        data["paired"] = True
        A.save(data, self.kit)
        self.calls, self.delivered = [], []
        self.hub = {"away": [{"char": "Hurami", "slot": 2, "end": 2000000000, "camp": "Qufim Island (the shore)"}],
                    "done": [{"id": "v1", "char": "Hurami", "camp": "Valkurm Dunes", "gil": 40,
                              "mates": [{"slot": 1, "name": "Ayame", "exp": 6000}], "items": [[4096, 2], [926, 1]]}]}

        def caller(path, body=None):
            self.calls.append((path, body))
            return self.hub if path.endswith("/launcher") else {"ok": True}

        LV.deliver = lambda conn, char, items, log=print: self.delivered.append((char, items)) or True
        LV.build_roster = lambda conn: {"chars": []}
        self.r = LV.Relay({}, self.kit, caller=caller, connector=lambda: type("C", (), {"close": lambda s: None})())

    def path(self, n):
        return os.path.join(self.kit, "ventures", n)

    def test_flow(self):
        self.r.look()
        self.assertIn("Hurami|2|2000000000|Qufim Island (the shore)", open(self.path("away.txt")).read())
        self.assertEqual(open(self.path("in.txt")).read(), "v1|Hurami|40|Valkurm Dunes|1:6000\n")
        self.r.look()                                          # the game hasn't taken it in yet: not written twice
        self.assertEqual(open(self.path("in.txt")).read().count("v1|"), 1)
        self.assertEqual(self.delivered, [])
        with open(self.path("out.txt"), "w") as f:
            f.write("v1|ok\n")                                 # the game took it in
        self.r.look()
        self.assertEqual(self.delivered, [("Hurami", [[4096, 2], [926, 1]])])
        self.assertIn(("/armory/api/ventures/applied", {"ids": ["v1"]}), self.calls)
        self.assertEqual(open(self.path("in.txt")).read(), "")
        self.r.look()                                          # the hub still lists it (lost answer): nothing twice
        self.assertEqual(len(self.delivered), 1)

    def test_quiet_when_not_paired(self):
        data = A.load(self.kit)
        data["paired"] = False
        A.save(data, self.kit)
        self.r.look()
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
