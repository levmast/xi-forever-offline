"""Stand-in tests for launcher_setup.py (first-run setup): no Windows, no MariaDB, no network.
Run: python test_setup.py [server folder]   (the server folder is only read, for the import order)"""
import json, os, shutil, sys, tempfile, unittest, zipfile, io
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_setup as ls
import launcher_thirdparty as tp

EXAMPLE_INI = """[ashita.launcher]
autoclose   = 1
name        = Example Configuration
[ashita.boot]
file        = .\\\\bootloader\\\\pol.exe
command     = --server homepointxi.com
gamemodule  = ffximain.dll
script      = default.txt
args        =
"""
NETWORK = """xi = xi or {}\nxi.settings = xi.settings or {}\nxi.settings.network =\n{\n    SQL_HOST     = '127.0.0.1',\n    SQL_PORT     = 3306,\n    SQL_LOGIN    = 'root',\n    SQL_PASSWORD = 'root',\n    SQL_DATABASE = 'xidb',\n}\n"""


class Done:
    def __init__(self, out=""):
        self.returncode, self.stdout, self.stderr = 0, out, ""


class FakeMaria:
    """Records every command; SHOW TABLES says 'no tables' the first time."""
    def __init__(self):
        self.calls = []

    def run(self, cmd, **kw):
        self.calls.append(cmd)
        if "mariadb-install-db" in cmd[0]:
            os.makedirs(os.path.join(cmd[1].split("=", 1)[1], "mysql"), exist_ok=True)
        return Done("")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kit = os.path.join(self.tmp, "kit")
        os.makedirs(self.kit)
        for name in ("thirdparty.json", "config.example.json"):
            shutil.copy(os.path.join(KIT, name), self.kit)
        os.makedirs(os.path.join(self.kit, "addons-src", "Gambits"))
        open(os.path.join(self.kit, "addons-src", "Gambits", "Gambits.lua"), "w").write("--")
        self.ffxi = os.path.join(self.tmp, "ffxi"); os.makedirs(self.ffxi)
        open(os.path.join(self.ffxi, "FFXiMain.dll"), "w").write("x")
        self.server = os.path.join(self.tmp, "server")
        for d in ("sql", "settings/default", "modules/custom/sql"):
            os.makedirs(os.path.join(self.server, d))
        open(os.path.join(self.server, "xi_map.exe"), "w").write("x")
        for f in ("triggers.sql", "accounts.sql", "zones.sql"):
            open(os.path.join(self.server, "sql", f), "w").write("--")
        open(os.path.join(self.server, "modules", "custom", "sql", "squad.sql"), "w").write("--")
        open(os.path.join(self.server, "modules", "init.txt"), "w").write("# x\ncustom/sql\n")
        open(os.path.join(self.server, "settings", "default", "network.lua"), "w").write(NETWORK)
        self.ashita = os.path.join(self.tmp, "Ashita")
        os.makedirs(os.path.join(self.ashita, "config", "boot")); os.makedirs(os.path.join(self.ashita, "scripts"))
        open(os.path.join(self.ashita, "config", "boot", "example-privateserver.ini"), "w").write(EXAMPLE_INI)
        open(os.path.join(self.ashita, "scripts", "default.txt"), "w").write("/load thirdparty\n/load addons\n")
        for f in ("Ashita-cli.exe", "bootloader/xiloader.exe", "plugins/XIUIplus.dll"):   # already "installed": no downloads
            os.makedirs(os.path.dirname(os.path.join(self.ashita, f)), exist_ok=True)
            open(os.path.join(self.ashita, f), "w").write("x")
        self.mdb = os.path.join(self.tmp, "mariadb")
        os.makedirs(os.path.join(self.mdb, "bin")); open(os.path.join(self.mdb, "bin", "mariadbd.exe"), "w").write("x")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_order_triggers_last_then_modules(self):
        names = [os.path.basename(p) for p in ls.import_order(self.server)]
        self.assertEqual(names, ["accounts.sql", "zones.sql", "triggers.sql", "squad.sql"])

    def test_network_settings_and_never_twice(self):
        ls.write_network_settings(self.server, 3307, "pw'x")
        text = open(os.path.join(self.server, "settings", "network.lua")).read()
        self.assertIn("SQL_PORT     = 3307", text)
        self.assertIn("SQL_LOGIN    = 'xi'", text)
        self.assertIn("SQL_PASSWORD = 'pw\\'x'", text)
        self.assertIn("SQL_DATABASE = 'xiforever'", text)
        self.assertIn("left as it is", ls.write_network_settings(self.server, 1, "other"))

    def test_boot_and_script(self):
        ls.write_boot(self.ashita, "player1", "secret1")
        boot = open(os.path.join(self.ashita, "config", "boot", "xiforever.ini")).read()
        self.assertIn("command     = --server 127.0.0.1 --user player1 --pass secret1", boot)
        self.assertIn("script      = xiforever.txt", boot)
        self.assertIn("bootloader\\\\xiloader.exe", boot)
        ls.write_script(self.ashita, "xiuiplus", ["Gambits"], ["minimap"])
        script = open(os.path.join(self.ashita, "scripts", "xiforever.txt")).read().splitlines()
        self.assertEqual(script[-3:], ["/load minimap", "/addon load Gambits", "/load XIUIplus"])

    def test_account_sql_uses_password(self):
        fake = FakeMaria()
        ls.create_account(self.mdb, 3306, "dbpw", "player1", "it's", run=fake.run)
        insert = fake.calls[-1][-1]
        self.assertIn("PASSWORD('it''s')", insert)
        self.assertIn("GREATEST(1000", insert)
        with self.assertRaises(ValueError):
            ls.create_account(self.mdb, 3306, "dbpw", "bad name!", "x", run=fake.run)

    def test_mariadb_zip_from_the_api(self):
        api = {"releases": {"11.4.9": {"files": [{"file_name": "mariadb-11.4.9-winx64-debugsymbols.zip"},
                                                  {"file_name": "mariadb-11.4.9-winx64.zip", "file_download_url": "u",
                                                   "checksum": {"sha256sum": "abc"}}]},
                            "11.4.10": {"files": [{"file_name": "mariadb-11.4.10-winx64.zip", "file_download_url": "v"}]}}}
        found = ls.resolve_mariadb(lambda url, timeout=60: json.dumps(api).encode())
        self.assertEqual((found["version"], found["url"]), ("11.4.10", "v"))

    def test_whole_setup_with_stand_ins(self):
        fake = FakeMaria()
        logs = []
        ls.start_mariadb = lambda d, p, popen=None, wait=30: None          # "already running"
        cfg = ls.run_setup(self.kit, {"ffxi_dir": self.ffxi, "ashita_dir": self.ashita, "server_dir": self.server,
                                      "mariadb_dir": self.mdb, "world": "quiet", "population": "small",
                                      "interface": "xiuiplus", "extras": [], "login": "player1", "password": "pw123456"},
                           tp, log=logs.append, fetch=lambda *a, **k: b"", run=fake.run)
        self.assertEqual((cfg["db_name"], cfg["ashita_boot"], cfg["mariadb_service"]), ("xiforever", "xiforever.ini", ""))
        self.assertTrue(os.path.exists(os.path.join(self.kit, "config.json")))
        rates = json.load(open(os.path.join(self.kit, "rates.json")))
        self.assertEqual((rates["bots"], rates["squad_chat"], rates["crowds_per_zone"]), (False, False, 10))
        sources = [c[-1] for c in fake.calls if "SOURCE" in c[-1]]
        self.assertEqual(len(sources), 4)
        self.assertTrue(os.path.exists(os.path.join(self.ashita, "addons", "Gambits", "Gambits.lua")))
        self.assertTrue(any("shutdown" in c for c in fake.calls), "the database is stopped at the end")
        with self.assertRaises(RuntimeError):                      # never over an existing install
            ls.write_config(self.kit, {})

    def test_server_is_downloaded_when_missing(self):
        """A new server folder: the setup downloads the release zip (checked against SHA256SUMS.txt)."""
        import hashlib
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xi-forever-offline-server-v9/xi_map.exe", "exe")
            z.writestr("xi-forever-offline-server-v9/sql/accounts.sql", "--")
            z.writestr("xi-forever-offline-server-v9/settings/default/network.lua", NETWORK)
        data = buf.getvalue()
        name = "xi-forever-offline-server-v9-win64.zip"
        release = {"tag_name": "v9", "assets": [{"name": name, "browser_download_url": "u/zip"},
                                                {"name": "SHA256SUMS.txt", "browser_download_url": "u/sums"}]}

        def fetch(url, timeout=60):
            if url.startswith(tp.API):           # the server item lists releases (pre-releases count)
                return json.dumps([dict(release, draft=False, prerelease=True)] if "/releases?" in url else release).encode()
            return {"u/zip": data, "u/sums": (hashlib.sha256(data).hexdigest() + "  " + name + "\n").encode()}[url]
        items = {i["id"]: i for i in tp.load_manifest(self.kit)}
        new_server = os.path.join(self.tmp, "newserver")
        tp.install(items["server"], self.kit, self.ashita, fetch=fetch, log=lambda m: None, server=new_server)
        self.assertTrue(ls.valid_server(new_server))

    def test_era_dats_back_up_what_they_replace(self):
        era = os.path.join(self.kit, "Era-DATs")
        for rel, data in (("ROM/1/1.DAT", "era"), ("ROM2/9/9.DAT", "new")):
            os.makedirs(os.path.dirname(os.path.join(era, rel)), exist_ok=True)
            open(os.path.join(era, rel), "w").write(data)
        os.makedirs(os.path.join(self.ffxi, "ROM", "1"))
        open(os.path.join(self.ffxi, "ROM", "1", "1.DAT"), "w").write("original")
        ls.install_era_dats(self.kit, self.ffxi)
        read = lambda *p: open(os.path.join(*p)).read()
        self.assertEqual(read(self.ffxi, "ROM", "1", "1.DAT"), "era")
        self.assertEqual(read(self.kit, "dat-backup", "ROM", "1", "1.DAT"), "original")
        self.assertEqual(read(self.kit, "dat-backup", "new-files.txt").split(), [os.path.join("ROM2", "9", "9.DAT")])
        self.assertIn("up to date", ls.install_era_dats(self.kit, self.ffxi)[0])
        # a game update writes its own file over an era one: applying again puts the era file back and keeps the
        # update's file as the saved original (2026-11-19)
        open(os.path.join(self.ffxi, "ROM", "1", "1.DAT"), "w").write("updated")
        self.assertIn("put back: 1", ls.install_era_dats(self.kit, self.ffxi)[0])
        self.assertEqual(read(self.ffxi, "ROM", "1", "1.DAT"), "era")
        self.assertEqual(read(self.kit, "dat-backup", "ROM", "1", "1.DAT"), "updated")
        items = {i["id"]: i for i in tp.load_manifest(self.kit)}
        moves = tp.plan(items["eradats"], ["Era-DATs-main/README.md", "Era-DATs-main/ROM/1/1.DAT", "Era-DATs-main/YAML/x.yaml"])
        self.assertEqual(moves, [("Era-DATs-main/ROM/1/1.DAT", "Era-DATs/ROM/1/1.DAT")])

    def test_real_server_order(self):
        server = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None
        if not server:
            self.skipTest("no server folder given")
        files = ls.import_order(server)
        self.assertEqual(os.path.basename([f for f in files if os.sep + "sql" + os.sep in f or "/sql/" in f][0]), "abilities.sql")


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1], verbosity=1)
