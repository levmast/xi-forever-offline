"""Tests for Ventures (python3 dev/armory/test_ventures.py): the simulation's balance and the hub's flow."""
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ventures as V  # noqa: E402
import ventures_hub as H  # noqa: E402

OWNER = "o" * 8


def mate(slot=1, name="Ayame", job=1, level=20, exp=0, race=4):
    return {"slot": slot, "name": name, "job": job, "level": level, "exp": exp, "race": race, "face": 2}


class Simulation(unittest.TestCase):
    def test_exp_is_3000_an_hour_everywhere(self):
        for camp in V.data()["camps"]:
            lv = max(1, min(74, (camp["lo"] + camp["hi"]) // 2))
            for hours in (1, 4, 12):
                plan = V.simulate("t" + camp["id"], camp["id"], [mate(level=lv)], hours, 0)
                got = V.results(plan)["exp"][0]
                self.assertAlmostEqual(got / hours, 3000, delta=15, msg=f"{camp['id']} {hours}h: {got}")

    def test_same_seed_same_venture(self):
        a = V.simulate("seed1", "qufim", [mate(level=22)], 4, 100)
        b = V.simulate("seed1", "qufim", [mate(level=22)], 4, 100)
        self.assertEqual(a, b)

    def test_solo_below_10_party_from_10(self):
        self.assertTrue(V.simulate("s", "ronfaure", [mate(level=3)], 2, 0)["solo"])
        p = V.simulate("s", "valkurm_lizards", [mate(level=12)], 2, 0)
        self.assertFalse(p["solo"])
        self.assertEqual(len(p["party"]) + 1, V.PARTY_SIZE)
        jobs = {x["job"] for x in p["party"]} | {"WAR"}
        self.assertTrue(jobs & V.TANKS and jobs & V.HEALERS)

    def test_loot_stays_modest(self):
        """Balance: per 12 hours at any party camp, a few dozen cheap items and under 2,000 gil."""
        for camp in V.data()["camps"]:
            if camp["solo"]:
                continue
            lv = (camp["lo"] + camp["hi"]) // 2
            r = V.results(V.simulate("loot" + camp["id"], camp["id"], [mate(level=lv)], 12, 0))
            n = sum(c for _, c, _ in r["items"])
            self.assertLess(n, 40, f"{camp['id']}: {n} items")
            self.assertLess(r["gil"], 2000, f"{camp['id']}: {r['gil']} gil")

    def test_levels_cap_at_75(self):
        r = V.results(V.simulate("cap", "boyahda_top", [mate(level=75)], 12, 0))
        self.assertEqual(r["levels"], [75])
        self.assertEqual(r["exp"], [0])

    def test_level_up_math(self):
        plan = V.simulate("up", "ronfaure", [mate(level=1)], 4, 0)
        r = V.results(plan)
        total, lv = 12000, 1
        while total >= V.exp_needed(lv):
            total -= V.exp_needed(lv)
            lv += 1
        self.assertEqual(r["levels"][0], lv)

    def test_outgrown_camp_moves_on(self):
        plan = V.simulate("move", "ronfaure", [mate(level=5)], 12, 0)
        self.assertTrue(any(e["k"] == "move" for e in plan["events"]))

    def test_recall_is_a_prefix(self):
        plan = V.simulate("rc", "jugner", [mate(level=17)], 8, 0)
        half = V.results(plan, 4 * 3600)
        full = V.results(plan)
        self.assertLessEqual(half["exp"][0], full["exp"][0])
        self.assertAlmostEqual(half["exp"][0], 12000, delta=1500)

    def test_group_venture_each_mate_gets_full_exp(self):
        plan = V.simulate("g", "yuhtunga", [mate(1, "Ayame", 1, 30), mate(2, "Naji", 3, 31)], 2, 0)
        r = V.results(plan)
        self.assertEqual(r["exp"][0], r["exp"][1])
        self.assertAlmostEqual(r["exp"][0], 6000, delta=15)
        self.assertEqual(len(plan["party"]), 4)

    def test_story_tells_the_truth(self):
        plan = V.simulate("st", "valkurm_beach", [mate(level=16)], 4, 0)
        text = " ".join(V.story(plan))
        r = V.results(plan)
        self.assertIn(f"{r['kills']} kills", text)
        if r["levels"][0] > 16:
            self.assertIn(f"level 16 to {r['levels'][0]}", text)


class Hub(unittest.TestCase):
    def setUp(self):
        self.t = [1_000_000.0]
        self.v = H.Ventures(tempfile.mkdtemp(), threading.RLock(), now=lambda: self.t[0])
        self.v.roster(OWNER, {"chars": [{"name": "Hurami", "mates": [mate(1, "Ayame", 1, 20), mate(2, "Naji", 3, 21)],
                                         "bots": [{"name": "Mimiru", "race": 6}]}]})

    def start(self, vid="v0000001", slots=(1,), camp="qufim", hours=2):
        return self.v.start(OWNER, {"id": vid, "char": "Hurami", "slots": list(slots), "camp": camp, "hours": hours})

    def test_flow(self):
        out = self.start()
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(self.start()["again"], True)                       # sent twice: one venture
        away = self.v.launcher(OWNER)
        self.assertEqual([(a["char"], a["slot"]) for a in away["away"]], [("Hurami", 1)])
        self.assertEqual(away["done"], [])
        self.assertIn("already out", self.start("v0000002")["error"])        # Ayame is busy
        self.t[0] += 2 * 3600 + 5
        lt = self.v.launcher(OWNER)
        self.assertEqual(lt["away"], [])
        self.assertEqual(len(lt["done"]), 1)
        d = lt["done"][0]
        self.assertAlmostEqual(d["mates"][0]["exp"], 6000, delta=15)
        ph = self.v.phone(OWNER)
        self.assertTrue(ph["ventures"][0]["over"])
        self.assertTrue(ph["ventures"][0]["story"])
        self.v.applied(OWNER, [d["id"]])
        self.assertEqual(self.v.launcher(OWNER)["done"], [])               # never twice

    def test_recall(self):
        self.start(hours=8)
        self.t[0] += 3600
        out = self.v.recall(OWNER, "v0000001")
        self.assertTrue(out["ok"])
        d = self.v.launcher(OWNER)["done"][0]
        self.assertAlmostEqual(d["mates"][0]["exp"], 3000, delta=900)
        self.assertTrue(self.v.phone(OWNER)["ventures"][0]["recalled"])

    def test_checks(self):
        self.assertIn("error", self.start(hours=3))
        self.assertIn("error", self.start(camp="nowhere"))
        self.assertIn("error", self.start(slots=(9,)))
        self.assertIn("error", self.start(camp="boyahda_top"))              # level 20 at a 68-75 camp
        self.assertIn("error", self.v.start("someone else", {"id": "v0000009", "char": "Hurami", "slots": [1],
                                                              "camp": "qufim", "hours": 1}))

    def test_together(self):
        out = self.start(slots=(1, 2))
        self.assertTrue(out.get("ok"), out)
        self.assertEqual(len(out["venture"]["mates"]), 2)
        self.assertEqual(len(self.v.launcher(OWNER)["away"]), 2)

    def test_survives_restart(self):
        self.start()
        again = H.Ventures(os.path.dirname(self.v.folder), threading.RLock(), now=lambda: self.t[0])
        self.assertEqual(len(again.launcher(OWNER)["away"]), 1)


class Chained(unittest.TestCase):
    """(2026-11-25) a second venture before playing again starts from where the first one left the mate"""

    def test_second_venture_starts_from_the_new_level(self):
        import tempfile, threading
        import ventures_hub as H
        clock = [1000.0]
        hub = H.Ventures(tempfile.mkdtemp(), threading.Lock(), now=lambda: clock[0])
        hub.roster("o", {"chars": [{"name": "Hurami", "mates": [mate(level=10)]}]})
        self.assertIsNone(hub.start("o", {"id": "venture0001", "char": "Hurami", "slots": [1], "camp": "valkurm_lizards", "hours": 12}).get("error"))
        clock[0] += 13 * 3600
        lv, xp = V.end_state(hub.plan("venture0001"))[1]
        self.assertGreater(lv, 10)
        self.assertEqual(hub.phone("o")["roster"][0]["mates"][0]["level"], lv)
        camp = next(c for c in V.data()["camps"] if c["lo"] - 3 <= lv <= c["hi"] + 3)
        self.assertIsNone(hub.start("o", {"id": "venture0002", "char": "Hurami", "slots": [1], "camp": camp["id"], "hours": 1}).get("error"))
        m = hub.plan("venture0002")["mates"][0]
        self.assertEqual((m["level"], m["exp"]), (lv, xp))


if __name__ == "__main__":
    unittest.main(verbosity=1)
