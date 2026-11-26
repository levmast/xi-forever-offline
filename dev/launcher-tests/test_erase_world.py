"""Erase the world (2026-11-25): a copy first, the players' logins kept, an empty database, the server's tables fresh."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import launcher_world_keep as wk  # noqa: E402
import launcher_setup as setup    # noqa: E402


class Result:
    def __init__(self, code=0, err=""):
        self.returncode, self.stderr, self.stdout = code, err, ""


class Erase(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        self.server = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.server, "sql"))
        for n in ("accounts.sql", "chars.sql", "triggers.sql"):
            open(os.path.join(self.server, "sql", n), "w").write("-- x")
        self.mdb = tempfile.mkdtemp()
        open(os.path.join(self.mdb, "xiforever-db.json"), "w").write('{"root": "R", "xi": "P"}')
        self.cfg = {"mariadb_dir": self.mdb, "db_port": 3307, "db_name": "xiforever", "db_user": "xi", "db_pass": "P"}
        self.calls = []

    def run_ok(self, cmd, **kw):
        self.calls.append(cmd)
        for part in cmd:
            if str(part).startswith("--result-file="):
                open(part.split("=", 1)[1], "w").write("REPLACE INTO accounts VALUES (1);\n-- Dump completed on now\n")
        return Result()

    def backup(self, cfg, kit, kind, log, run):
        self.calls.append(["BACKUP", kind])
        return os.path.join(kit, "db-before-erase-x.sql.gz")

    def test_order_and_what_is_kept(self):
        said = []
        copy = wk.erase_world(self.cfg, self.kit, self.server, log=said.append, run=self.run_ok, backup=self.backup)
        self.assertTrue(copy.endswith("db-before-erase-x.sql.gz"))
        self.assertEqual(self.calls[0], ["BACKUP", "before-erase"])                 # 1. a copy first
        dump = self.calls[1]
        self.assertIn("--no-create-info", dump)
        self.assertIn("--replace", dump)
        self.assertIn("--where=id < 21000000", dump)                                # bots' logins are not kept
        self.assertEqual(dump[-2:], ["xiforever", "accounts"])
        self.assertNotIn("--single-transaction", dump)
        text = [" ".join(map(str, c)) for c in self.calls[2:]]
        self.assertIn("DROP DATABASE IF EXISTS `xiforever`; CREATE DATABASE", text[0])  # 2. empty, as root
        self.assertIn("-uroot", text[0])
        loads = [t for t in text if "SOURCE" in t and "/sql/" in t]
        self.assertEqual([os.path.basename(t.split("SOURCE ")[1].split(";")[0]) for t in loads],
                         ["accounts.sql", "chars.sql", "triggers.sql"])                # the server's own order, triggers last
        self.assertTrue(all("-uxi" in t and "xiforever" in t for t in loads))
        self.assertIn("erase-accounts-", text[-1])                                    # 3. the logins back, last
        self.assertFalse([n for n in os.listdir(wk.backup_folder(self.kit)) if n.startswith("erase-accounts-")])

    def test_nothing_dropped_when_logins_cannot_be_saved(self):
        def run(cmd, **kw):
            self.calls.append(cmd)
            return Result(1, "access denied")
        with self.assertRaises(wk.KeepError):
            wk.erase_world(self.cfg, self.kit, self.server, log=lambda *_: None, run=run, backup=self.backup)
        self.assertFalse([c for c in self.calls if "DROP DATABASE" in " ".join(map(str, c))])

    def test_only_the_kits_own_database(self):
        with self.assertRaises(wk.KeepError):
            wk.erase_world({"db_name": "x"}, self.kit, self.server, run=self.run_ok, backup=self.backup)


if __name__ == "__main__":
    unittest.main()
