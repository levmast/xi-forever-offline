"""The launcher shows a squad mate's support job by the game's own rule (squad.lua levelsFor).

FalconX51, 2026-11-22: a level 5 BLM/WHM mate had its sub job in the game but the launcher showed none until 18.
Run with: python test_sub_job_shown.py
Nothing here touches a real database: the connection is a small stand-in.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import launcher_squad as sq  # noqa: E402


class FakeCursor:
    def __init__(self, tables):
        self.tables, self.rows = tables, []

    def execute(self, sql, params=()):
        for marker, rows in self.tables.items():
            if marker in sql:
                self.rows = rows
                return
        self.rows = []

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, **tables):
        self.tables = tables

    def cursor(self):
        return FakeCursor(self.tables)


def mate(main, sub, jobs, owner=False):
    return {"slot": 1, "name": "Test", "mjob": main, "sjob": sub, "jobs": jobs, "owner_sub": owner}


class SubJobShown(unittest.TestCase):
    def setUp(self):
        self.ratio = sq.SUBJOB_RATIO
        sq.SUBJOB_RATIO = 1

    def tearDown(self):
        sq.SUBJOB_RATIO = self.ratio

    def test_owner_with_support_jobs_gives_the_sub_from_level_one(self):
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (5, 0), 3: (10, 0)}, True)), (5, 3, 2))
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (1, 0), 3: (10, 0)}, True)), (1, 3, 1))
        self.assertIn("BLM5/WHM2", sq.describe(mate(4, 3, {4: (5, 0), 3: (10, 0)}, True)))

    def test_no_sub_before_anyone_has_support_jobs(self):
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (5, 0), 3: (10, 0)})), (5, 0, 0))

    def test_any_job_of_the_mate_at_18_unlocks_it(self):
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (5, 0), 1: (18, 0)})), (5, 3, 1))
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (18, 0), 3: (30, 0)})), (18, 3, 9))

    def test_sub_level_never_above_the_sub_jobs_own_level(self):
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (40, 0), 3: (7, 0)}, True)), (40, 3, 7))

    def test_ratio_none_means_no_sub(self):
        sq.SUBJOB_RATIO = 0
        self.assertEqual(sq.effective_levels(mate(4, 3, {4: (30, 0), 3: (30, 0)}, True)), (30, 0, 0))

    def test_a_mate_without_the_owner_fact_still_works(self):
        m = mate(4, 3, {4: (5, 0)})
        del m["owner_sub"]
        self.assertEqual(sq.effective_levels(m), (5, 0, 0))

    def test_owner_has_support_jobs(self):
        quest = FakeConn(**{"FROM char_jobs": [(1 | (1 << 7),)], "FROM char_stats": [(9,)]})
        level = FakeConn(**{"FROM char_jobs": [(0,)], "FROM char_stats": [(18,)]})
        neither = FakeConn(**{"FROM char_jobs": [(1 << 7,)], "FROM char_stats": [(17,)]})
        self.assertTrue(sq.owner_has_support_jobs(quest, 1))
        self.assertTrue(sq.owner_has_support_jobs(level, 1))
        self.assertFalse(sq.owner_has_support_jobs(neither, 1))
        self.assertFalse(sq.owner_has_support_jobs(FakeConn(), 1))

    def test_get_squad_marks_every_mate(self):
        conn = FakeConn(**{
            "FROM squad_mate WHERE charid = ? ORDER BY slot": [(11, 1, "Kasumi", 1, 0, 4, 3)],
            "FROM squad_job": [(11, 4, 5, 0), (11, 3, 10, 0)],
            "FROM squad_equip": [],
            "FROM char_jobs": [(1,)],
            "FROM char_stats": [(21,)],
        })
        squad = sq.get_squad(conn, 1)
        self.assertEqual(len(squad), 1)
        self.assertTrue(squad[0]["owner_sub"])
        self.assertEqual(sq.effective_levels(squad[0]), (5, 3, 2))


if __name__ == "__main__":
    unittest.main()
