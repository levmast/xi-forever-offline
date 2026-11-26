"""Hub personal rates (2026-11-25): a visitor's own rates travel in the passport as [HR] character variables."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import launcher_passport as pp  # noqa: E402


def block(rows):
    return {"chars": {"cols": ["charid"], "rows": [[7]]},
            "char_vars": {"cols": ["charid", "varname", "value", "expiry"], "rows": rows}}


class HubRates(unittest.TestCase):
    def test_values_are_rate_times_1000_plus_1(self):
        out = pp.hub_rate_vars({"map.EXP_RATE": 2.5, "map.DROP_RATE_MULTIPLIER": 0, "main.GIL_RATE": 100})
        self.assertEqual(out["[HR]map.EXP_RATE"], 2501)
        self.assertEqual(out["[HR]map.DROP_RATE_MULTIPLIER"], 1)        # a rate of 0 travels too
        self.assertEqual(out["[HR]main.GIL_RATE"], 100001)             # no cap

    def test_only_the_listed_keys_travel(self):
        out = pp.hub_rate_vars({"map.EXP_RATE": 1, "map.PLAYER_HP_MULTIPLIER": 3, "main.NM_LOTTERY_CHANCE": -1})
        self.assertEqual(set(out), {"[HR]map.EXP_RATE"})

    def test_bad_values_are_left_out(self):
        out = pp.hub_rate_vars({"map.EXP_RATE": "x", "map.DROP_RATE_MULTIPLIER": -2, "main.GIL_RATE": float("nan"),
                                "main.TABS_RATE": None})
        self.assertEqual(out, {})

    def test_huge_value_fits_the_column(self):
        out = pp.hub_rate_vars({"map.EXP_RATE": 1e12})
        self.assertLess(out["[HR]map.EXP_RATE"], 2 ** 31)

    def test_old_rows_are_replaced_and_others_kept(self):
        tables = block([[7, "[HR]map.EXP_RATE", 50001, 0], [7, "SomeQuest", 3, 0]])
        out = pp._with_hub_rates(tables, 7, {"map.EXP_RATE": 2})
        rows = {r[1]: r for r in out["char_vars"]["rows"]}
        self.assertEqual(rows["[HR]map.EXP_RATE"], [7, "[HR]map.EXP_RATE", 2001, 0])
        self.assertEqual(rows["SomeQuest"], [7, "SomeQuest", 3, 0])
        self.assertEqual(len(rows), 2)

    def test_no_rates_changes_nothing(self):
        tables = block([[7, "[HR]map.EXP_RATE", 50001, 0]])
        self.assertEqual(pp._with_hub_rates(tables, 7, None)["char_vars"]["rows"], [[7, "[HR]map.EXP_RATE", 50001, 0]])

    def test_the_three_lists_match(self):
        here = os.path.dirname(os.path.abspath(__file__))
        lua = os.path.join(here, "..", "..", "..", "ffxi-local", "server", "modules", "custom", "late", "hardcore.lua")
        if not os.path.exists(lua):
            self.skipTest("the server folder is not next to the kit")
        text = open(lua, encoding="utf-8").read()
        listed = text[text.index("H.HUB_KEYS ="):text.index("}", text.index("H.HUB_KEYS ="))]
        for key in pp.HUB_RATE_KEYS:
            self.assertIn("'" + key + "'", listed)
        self.assertEqual(listed.count("'") // 2, len(pp.HUB_RATE_KEYS))


if __name__ == "__main__":
    unittest.main()
