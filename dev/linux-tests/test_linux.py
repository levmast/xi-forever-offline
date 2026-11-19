"""Tests for the Linux / Steam Deck parts of the launcher (launcher_linux.py and the Linux paths in launcher_setup,
launcher_thirdparty, launcher_update and launcher_core). Run on Linux:  python3 test_linux.py
No Proton, no game, no network. MariaDB: the real-database test runs only when MARIADB_TEST_DIR points at a folder laid
out like MariaDB's Linux package (bin/, scripts/, share/), e.g. one made of symlinks to the system's MariaDB."""
import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
os.environ.pop("XIFO_TEST_PLATFORM", None)
import launcher_core as core
import launcher_linux as ll
import launcher_setup as ls
import launcher_thirdparty as tp
import launcher_update as lu

SANDBOX = r"""
; comment
[(PlayOnline|PlayOnlineUS)$]
CommonFilesFolder="{COMMON_PATH}"

[(PlayOnline|PlayOnlineUS)\\InstallFolder$]
0001="{FFXI_PATH}"
1000="{POL_PATH}"

[(PlayOnline|PlayOnlineUS)\\(Square|SquareEnix)\\PlayOnlineViewer$]
FirstBootPlayMovie=dword:0000001f

[CLSID\\\{3501F5DD-7894-42DF-866A-A2B6527D8049\}\\InprocServer32$]
@="{POL_PATH}\viewer\com\polcore.dll"
ThreadingModel="Apartment"

[CLSID\\\{1BD94C71-26E5-42C3-8A8A-8D4F004A309E\}\\Programmable$]
"""


def tar_bytes(entries, mode="w:gz"):
    """entries: (name, data or None for a folder, mode, link)"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as archive:
        for name, data, fmode, link in entries:
            info = tarfile.TarInfo(name)
            if link is not None:
                info.type, info.linkname = tarfile.SYMTYPE, link
                archive.addfile(info)
            elif data is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(info)
            else:
                info.size, info.mode = len(data), fmode
                archive.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class Processes(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(ll.matches("xiloader", "xiloader.exe", ["C:\\Ashita\\bootloader\\xiloader.exe"]))
        self.assertTrue(ll.matches("xiloader", "something", ["Z:\\home\\deck\\x\\XILOADER.EXE", "--server"]))
        self.assertTrue(ll.matches("xi_map", "xi_map", ["/opt/xi/xi_map"]))
        self.assertFalse(ll.matches("xi_map", "xi_map_tests", ["/opt/xi/xi_map_tests"]))
        self.assertTrue(ll.matches("Ashita-cli", "Ashita-cli.exe", []))
        self.assertTrue(ll.matches("averyveryverylongname", "averyveryverylo", []))   # short names are cut at 15

    def test_table_helpers(self):
        table = [(10, 1, "umu-run", ["python3", "umu-run"]), (11, 10, "xiloader.exe", ["xiloader.exe"]),
                 (12, 11, "FFXi", ["pol"]), (20, 1, "xi_map", ["./xi_map"])]
        self.assertEqual(ll.pids_named("xiloader", table), [11])
        self.assertEqual(sorted(ll.descendants(10, table)), [11, 12])
        self.assertEqual(ll.pids_where(lambda a: "umu-run" in a, table), [10])

    def test_real_processes(self):
        proc = subprocess.Popen(["sh", "-c", "sleep 60 & sleep 60; wait"], start_new_session=True)
        time.sleep(0.5)
        try:
            kids = ll.descendants(proc.pid)
            self.assertGreaterEqual(len(kids), 2)
            self.assertTrue(core.is_running("sleep"))
            core.kill_tree(proc)
            proc.wait(timeout=10)
            time.sleep(0.3)
            self.assertFalse(any(ll.alive(k) for k in kids))
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_lock(self):
        with tempfile.TemporaryDirectory() as kit:
            first = ll.take_lock(kit)
            self.assertIsNotNone(first)
            self.assertIsNone(ll.take_lock(kit))
            self.assertEqual(ll.lock_holder(kit), os.getpid())
            os.close(first)
            again = ll.take_lock(kit)
            self.assertIsNotNone(again)
            os.close(again)

    def test_frozen_environment(self):
        env = {"LD_LIBRARY_PATH": "/tmp/_MEI123", "LD_LIBRARY_PATH_ORIG": "/usr/local/lib", "X": "1"}
        ll.fix_frozen_environment(env)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/usr/local/lib")
        env = {"LD_LIBRARY_PATH": "/tmp/_MEI123"}
        ll.fix_frozen_environment(env)
        self.assertNotIn("LD_LIBRARY_PATH", env)


class Machine(unittest.TestCase):
    def test_deck(self):
        self.assertTrue(ll.is_steam_deck(os_release='NAME="SteamOS"\nID=steamos\n', board="", env={}))
        self.assertTrue(ll.is_steam_deck(os_release="ID=arch\n", board="Galileo\n", env={}))
        self.assertFalse(ll.is_steam_deck(os_release="ID=fedora\n", board="X570", env={}))
        self.assertTrue(ll.is_steam_deck(os_release="", board="", env={"SteamDeck": "1"}))

    def test_windows_path(self):
        self.assertEqual(ll.windows_path("/home/deck/XI Forever Offline/Game"), "Z:\\home\\deck\\XI Forever Offline\\Game")


class Registry(unittest.TestCase):
    def test_parse(self):
        keys = dict((k, v) for k, v in ll.parse_sandbox_registry(SANDBOX))
        self.assertIn("PlayOnlineUS\\InstallFolder", keys)
        self.assertIn("PlayOnline\\SquareEnix\\PlayOnlineViewer", keys)
        self.assertIn("PlayOnlineUS\\Square\\PlayOnlineViewer", keys)
        self.assertEqual(keys["PlayOnline\\Square\\PlayOnlineViewer"], [("FirstBootPlayMovie", "dword", 31)])
        clsid = keys["CLSID\\{3501F5DD-7894-42DF-866A-A2B6527D8049}\\InprocServer32"]
        self.assertEqual(clsid[0], ("", "sz", "{POL_PATH}\\viewer\\com\\polcore.dll"))
        self.assertEqual(keys["CLSID\\{1BD94C71-26E5-42C3-8A8A-8D4F004A309E}\\Programmable"], [])

    def test_reg_file(self):
        paths = {"pol": "Z:\\g\\PlayOnlineViewer", "ffxi": "Z:\\g\\FINAL FANTASY XI", "common": "C:\\Common", "tetra": ""}
        text = ll.registry_file_text(SANDBOX, paths)
        self.assertTrue(text.startswith("Windows Registry Editor Version 5.00"))
        self.assertIn('[HKEY_LOCAL_MACHINE\\Software\\PlayOnlineUS\\InstallFolder]\r\n"0001"="Z:\\\\g\\\\FINAL FANTASY XI"', text)
        self.assertIn('[HKEY_LOCAL_MACHINE\\Software\\Classes\\CLSID\\{3501F5DD-7894-42DF-866A-A2B6527D8049}\\InprocServer32]'
                      '\r\n@="Z:\\\\g\\\\PlayOnlineViewer\\\\viewer\\\\com\\\\polcore.dll"', text)
        self.assertIn('"FirstBootPlayMovie"=dword:0000001f', text)

    def test_fallback_has_the_game(self):
        text = ll.registry_file_text(ll.FALLBACK_REGISTRY, {"pol": "P", "ffxi": "F"})
        for clsid in ("989D790D", "1027DC46", "0DF0E951", "3501F5DD"):
            self.assertIn(clsid, text)

    def test_real_sandbox_file_if_present(self):
        path = os.environ.get("ASHITA_SANDBOX_INI")
        if not path:
            self.skipTest("ASHITA_SANDBOX_INI not set")
        with open(path, encoding="utf-8") as handle:
            keys = [k for k, _v in ll.parse_sandbox_registry(handle.read())]
        self.assertIn("CLSID\\{1027DC46-750D-4B1F-8834-1D25B8BEBAB8}\\InprocServer32", keys)
        self.assertIn("PlayOnlineEU\\InstallFolder", keys)


class Prefix(unittest.TestCase):
    def make_kit(self, kit):
        proton = os.path.join(kit, "proton", "GE-Proton11-11")
        os.makedirs(proton)
        open(os.path.join(proton, "proton"), "w").close()
        os.makedirs(os.path.join(kit, "proton", "umu"))
        open(os.path.join(kit, "proton", "umu", "umu-run"), "w").close()
        ashita = os.path.join(kit, "Ashita")
        os.makedirs(os.path.join(ashita, "config", "sandbox"))
        with open(os.path.join(ashita, "config", "sandbox", "sandbox.registry.ini"), "w") as handle:
            handle.write(SANDBOX)
        game = os.path.join(kit, "Game", "SquareEnix")
        os.makedirs(os.path.join(game, "FINAL FANTASY XI"))
        os.makedirs(os.path.join(game, "PlayOnlineViewer"))
        return {"ashita_dir": ashita, "ffxi_client_dir": os.path.join(game, "FINAL FANTASY XI"),
                "pol_dir": os.path.join(game, "PlayOnlineViewer")}

    def test_prepare_once(self):
        with tempfile.TemporaryDirectory() as kit:
            cfg = self.make_kit(kit)
            calls = []

            def run(args, **kw):
                calls.append(args)
                if args == ["createprefix"]:
                    os.makedirs(os.path.join(kit, "prefix", "drive_c", "windows", "syswow64"))
                    open(os.path.join(kit, "prefix", "drive_c", "windows", "syswow64", "regedit.exe"), "w").close()
                return 0

            self.assertTrue(ll.prepare_prefix(kit, cfg, log=lambda m: None, run=run))
            self.assertEqual(calls[0], ["createprefix"])
            self.assertTrue(calls[1][0].endswith(os.path.join("syswow64", "regedit.exe")))
            self.assertEqual(calls[1][1], "/S")
            reg = os.path.join(kit, "prefix", ll.REGISTRY_FILE)
            with open(reg, encoding="utf-16") as handle:
                self.assertIn("PlayOnlineUS\\InstallFolder", handle.read())
            self.assertEqual(calls[1][2], ll.windows_path(reg))
            self.assertFalse(ll.prepare_prefix(kit, cfg, log=lambda m: None, run=run))     # nothing changed
            self.assertEqual(len(calls), 2)
            cfg["ffxi_client_dir"] = os.path.join(kit, "elsewhere")
            self.assertTrue(ll.prepare_prefix(kit, cfg, log=lambda m: None, run=run))      # the game moved: again
            self.assertEqual(calls[2][1], "/S")                                           # (no second createprefix)

    def test_prefix_failure(self):
        with tempfile.TemporaryDirectory() as kit:
            cfg = self.make_kit(kit)
            with self.assertRaises(RuntimeError):
                ll.prepare_prefix(kit, cfg, log=lambda m: None, run=lambda args, **kw: 1)

    def test_env_and_command(self):
        with tempfile.TemporaryDirectory() as kit:
            cfg = self.make_kit(kit)
            env = ll.game_env(kit, dict(cfg, proton_log=True, proton_env={"DXVK_HUD": "fps"}),
                              base={"HOME": "/home/x", "LD_LIBRARY_PATH": "/tmp/_MEI", "LD_LIBRARY_PATH_ORIG": ""})
            self.assertEqual(env["WINEPREFIX"], os.path.join(kit, "prefix"))
            self.assertTrue(env["PROTONPATH"].endswith("GE-Proton11-11"))
            self.assertEqual(env["UMU_FOLDERS_PATH"], os.path.join(kit, "proton", "runtime"))
            self.assertEqual(env["PROTON_LOG"], "1")
            self.assertEqual(env["DXVK_HUD"], "fps")
            self.assertEqual(env["LD_LIBRARY_PATH"], "")
            cmd = ll.umu_command(kit, ["Ashita-cli.exe", "x.ini"], python="/usr/bin/python3")
            self.assertEqual(cmd, ["/usr/bin/python3", os.path.join(kit, "proton", "umu", "umu-run"), "Ashita-cli.exe", "x.ini"])

    def test_newest_proton(self):
        with tempfile.TemporaryDirectory() as kit:
            for name in ("GE-Proton9-20", "GE-Proton11-2", "GE-Proton10-25"):
                os.makedirs(os.path.join(kit, "proton", name))
                open(os.path.join(kit, "proton", name, "proton"), "w").close()
            self.assertTrue(ll.installed_proton(kit).endswith("GE-Proton11-2"))
            self.assertTrue(ll.installed_proton(kit, "GE-Proton9-20").endswith("GE-Proton9-20"))


class GameFolder(unittest.TestCase):
    def test_find(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "usb", "PlayOnline", "SquareEnix")
            os.makedirs(os.path.join(base, "FINAL FANTASY XI"))
            os.makedirs(os.path.join(base, "PlayOnlineViewer", "viewer", "com"))
            open(os.path.join(base, "FINAL FANTASY XI", "FFXiMain.dll"), "w").close()
            want = (os.path.join(base, "FINAL FANTASY XI"), os.path.join(base, "PlayOnlineViewer"))
            for pick in (base, os.path.join(base, "FINAL FANTASY XI"), os.path.join(root, "usb", "PlayOnline"),
                         os.path.join(root, "usb")):
                self.assertEqual(ll.find_game_parts(pick), want, pick)
            self.assertEqual(ll.find_game_parts(root), (None, None))
            self.assertEqual(ll.detect_lang(want[1]), "US")
            open(os.path.join(base, "PlayOnlineViewer", "viewer", "com", "polcoreeu.dll"), "w").close()
            self.assertEqual(ll.detect_lang(want[1]), "EU")

    def test_letter_case(self):
        with tempfile.TemporaryDirectory() as root:
            base = os.path.join(root, "squareenix")
            os.makedirs(os.path.join(base, "Final Fantasy XI"))
            os.makedirs(os.path.join(base, "playonlineviewer"))
            open(os.path.join(base, "Final Fantasy XI", "FFXiMain.dll"), "w").close()
            self.assertEqual(ll.find_game_parts(root), (os.path.join(base, "Final Fantasy XI"),
                                                        os.path.join(base, "playonlineviewer")))


class Desktop(unittest.TestCase):
    def test_entry(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "Desktop"))
            old = os.environ.pop("XDG_DATA_HOME", None)
            try:
                path = ll.install_desktop_entry("/games/XI Forever Offline", home=home)
            finally:
                if old is not None:
                    os.environ["XDG_DATA_HOME"] = old
            with open(path) as handle:
                text = handle.read()
            self.assertIn("Name=XI: Forever Offline", text)
            self.assertIn("Path=/games/XI Forever Offline", text)
            self.assertTrue(os.path.exists(os.path.join(home, "Desktop", "xi-forever-offline.desktop")))


class Database(unittest.TestCase):
    API = {"releases": {"11.4.14": {"files": [
        {"file_name": "mariadb-11.4.14-winx64.zip", "file_download_url": "http://x/w.zip", "checksum": {"sha256sum": "aa"}},
        {"file_name": "mariadb-11.4.14-linux-systemd-x86_64.tar.gz", "file_download_url": "http://x/l.tar.gz",
         "checksum": {"sha256sum": "bb"}},
        {"file_name": "mariadb-11.4.14-linux-systemd-x86_64-debug.tar.gz", "file_download_url": "http://x/d"}]},
        "11.4.9": {"files": []}}}

    def test_resolve(self):
        fetch = lambda url, timeout=60: json.dumps(self.API).encode()
        found = ls.resolve_mariadb(fetch, linux=True)
        self.assertEqual((found["name"], found["sha256"], found["url"]),
                         ("mariadb-11.4.14-linux-systemd-x86_64.tar.gz", "bb", "https://x/l.tar.gz"))
        self.assertEqual(ls.resolve_mariadb(fetch, linux=False)["name"], "mariadb-11.4.14-winx64.zip")

    def test_unpack_tar(self):
        data = tar_bytes([("mariadb-11.4.14/", None, 0, None), ("mariadb-11.4.14/bin/mariadbd", b"#!/bin/sh\n", 0o755, None),
                          ("mariadb-11.4.14/lib/libx.so.1", b"x", 0o644, None),
                          ("mariadb-11.4.14/lib/libx.so", None, 0, "libx.so.1"),
                          ("mariadb-11.4.14/scripts/mariadb-install-db", b"#!/bin/sh\n", 0o755, None),
                          ("mariadb-11.4.14/lib/evil", None, 0, "../../../etc/passwd")])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.tar.gz")
            with open(path, "wb") as handle:
                handle.write(data)
            dest = os.path.join(tmp, "mariadb")
            ls.unpack_package(path, dest)
            self.assertTrue(os.access(os.path.join(dest, "bin", "mariadbd"), os.X_OK))
            self.assertEqual(os.readlink(os.path.join(dest, "lib", "libx.so")), "libx.so.1")
            self.assertFalse(os.path.lexists(os.path.join(dest, "lib", "evil")))
            self.assertEqual(ls.mariadb_exe(dest, "mariadb-install-db"), os.path.join(dest, "scripts", "mariadb-install-db"))
            self.assertEqual(ls.mariadb_exe(dest, "mariadbd"), os.path.join(dest, "bin", "mariadbd"))

    def test_commands(self):
        calls = []

        class Done:
            returncode, stdout, stderr = 0, "", ""

        def run(cmd, **kw):
            calls.append((cmd, kw))
            if "mariadb-install-db" in cmd[0]:
                os.makedirs(os.path.join(datadir, "mysql"))
            return Done()

        with tempfile.TemporaryDirectory() as mdb:
            datadir = os.path.join(mdb, "data")
            ls.init_mariadb(mdb, "pw", 3307, run=run)
            cmd, kw = calls[0]
            self.assertEqual(cmd[1], "--no-defaults")
            self.assertIn("--auth-root-authentication-method=normal", cmd)
            self.assertIn(f"--datadir={datadir}", cmd)
            self.assertNotIn("--password=pw", cmd)
            self.assertIn(os.path.join(mdb, "lib"), kw["env"]["LD_LIBRARY_PATH"])
            ls.sql(mdb, 3307, "root", "", "SELECT 1", run=run)
            cmd = calls[-1][0]
            self.assertEqual(cmd[1], "--no-defaults")
            self.assertFalse(any(c.startswith("-p") and not c.startswith("-P") for c in cmd))   # no empty -p (it would ask)
            ls.sql(mdb, 3307, "xi", "secret", "SELECT 1", database="xiforever", run=run)
            self.assertIn("-psecret", calls[-1][0])
            self.assertEqual(calls[-1][0][-3:], ["xiforever", "-e", "SELECT 1"])

    def test_start_command(self):
        port = ls.free_port(39000)
        seen = {}

        class Proc:
            def poll(self):
                return None

        def popen(cmd, **kw):
            seen["cmd"], seen["kw"] = cmd, kw
            srv = socket.socket()
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", port))
            srv.listen(1)
            seen["srv"] = srv
            return Proc()

        with tempfile.TemporaryDirectory() as mdb:
            try:
                ls.start_mariadb(mdb, port, popen=popen, wait=5)
            finally:
                if "srv" in seen:
                    seen["srv"].close()
            cmd = seen["cmd"]
            self.assertEqual(cmd[1], "--no-defaults")
            self.assertIn(f"--basedir={mdb}", cmd)
            self.assertIn(f"--socket={os.path.join(mdb, 'mariadb.sock')}", cmd)
            self.assertIn("--bind-address=127.0.0.1", cmd)
            self.assertTrue(seen["kw"]["start_new_session"])

    def test_real_mariadb(self):
        base = os.environ.get("MARIADB_TEST_DIR")
        if not base:
            self.skipTest("MARIADB_TEST_DIR not set")
        with tempfile.TemporaryDirectory() as tmp:
            mdb = os.path.join(tmp, "mariadb")
            shutil.copytree(base, mdb, symlinks=True)
            port = ls.free_port(39100)
            ls.init_mariadb(mdb, "root-pw", port)
            proc = ls.start_mariadb(mdb, port)
            try:
                self.assertTrue(ls.set_root_password(mdb, port, "root-pw"))
                ls.create_database(mdb, port, "root-pw", "xi-pw")
                self.assertEqual(ls.sql(mdb, port, "xi", "xi-pw", "SELECT 41 + 1", database="xiforever").strip(), "42")
                with self.assertRaises(RuntimeError):
                    ls.sql(mdb, port, "root", "", "SELECT 1")          # root needs its password now
            finally:
                ls.stop_mariadb(mdb, port, "root-pw")
                if proc is not None:
                    proc.wait(timeout=30)


class OldLibraries(unittest.TestCase):
    """MariaDB's generic package can need libraries a newer Linux dropped: only the missing ones are added."""

    def test_fill_missing_libs(self):
        cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not cc:
            self.skipTest("no C compiler")
        with tempfile.TemporaryDirectory() as tmp:
            def build(name, code, *args):
                src = os.path.join(tmp, name + ".c")
                with open(src, "w") as handle:
                    handle.write(code)
                subprocess.run([cc, src, *args], check=True, cwd=tmp)
            os.makedirs(os.path.join(tmp, "compat"))
            os.makedirs(os.path.join(tmp, "mdb", "bin"))
            build("chain", "int chain(void){return 2;}\n", "-shared", "-fPIC", "-o", "compat/libxifochain.so.1",
                  "-Wl,-soname,libxifochain.so.1")
            build("aio", "int chain(void); int aio(void){return chain()+1;}\n", "-shared", "-fPIC",
                  "-o", "compat/libxifoaio.so.1", "-Wl,-soname,libxifoaio.so.1", "compat/libxifochain.so.1")
            build("main", "int aio(void); int main(void){return aio()==3?0:1;}\n", "-o", "mdb/bin/mariadbd",
                  "compat/libxifoaio.so.1", "-Wl,--allow-shlib-undefined")
            mdb = os.path.join(tmp, "mdb")
            self.assertEqual(ls.missing_libs(mdb), ["libxifoaio.so.1"])
            self.assertEqual(ls.fill_missing_libs(mdb, os.path.join(tmp, "compat"), log=lambda m: None), [])
            self.assertEqual(sorted(os.listdir(os.path.join(mdb, "lib"))), ["libxifoaio.so.1", "libxifochain.so.1"])
            self.assertEqual(subprocess.run([ls.mariadb_exe(mdb, "mariadbd")], env=ls.mariadb_env(mdb)).returncode, 0)
            os.remove(os.path.join(mdb, "lib", "libxifochain.so.1"))
            os.remove(os.path.join(tmp, "compat", "libxifochain.so.1"))
            self.assertEqual(ls.fill_missing_libs(mdb, os.path.join(tmp, "compat"), log=lambda m: None),
                             ["libxifochain.so.1"])


class Downloads(unittest.TestCase):
    MANIFEST = [{"id": "a", "source": {"type": "url", "url": "x"}},
                {"id": "w", "platforms": ["windows"], "source": {"type": "url", "url": "x"}},
                {"id": "s", "check": "xi_map.exe", "source": {"type": "github_release", "asset": "win", "repo": "r"},
                 "linux": {"check": "xi_map", "source": {"asset": "linux"}}}]

    def test_platform(self):
        lin = {i["id"]: i for i in tp.for_platform(self.MANIFEST, "linux")}
        win = {i["id"]: i for i in tp.for_platform(self.MANIFEST, "windows")}
        self.assertNotIn("w", lin)
        self.assertIn("w", win)
        self.assertEqual((lin["s"]["check"], lin["s"]["source"]["asset"], lin["s"]["source"]["repo"]), ("xi_map", "linux", "r"))
        self.assertEqual((win["s"]["check"], win["s"]["source"]["asset"]), ("xi_map.exe", "win"))

    def test_real_manifest(self):
        lin = {i["id"]: i for i in tp.load_manifest(KIT, "linux")}
        win = {i["id"]: i for i in tp.load_manifest(KIT, "windows")}
        self.assertIn("proton", lin)
        self.assertIn("umu", lin)
        self.assertNotIn("vcredist", lin)
        self.assertNotIn("proton", win)
        self.assertEqual(win["server"]["check"], "xi_map.exe")
        self.assertEqual(lin["server"]["source"]["sha256sums"], "SHA256SUMS-linux.txt")

    def test_resolve_sha512(self):
        release = {"tag_name": "GE-Proton11-11", "assets": [
            {"name": "GE-Proton11-11-x86_64.tar.gz", "browser_download_url": "https://d/p.tar.gz"},
            {"name": "GE-Proton11-11-x86_64.sha512sum", "browser_download_url": "https://d/p.sha512sum"}]}

        def fetch(url, timeout=60):
            if url.endswith(".sha512sum"):
                return b"abc123  GE-Proton11-11-x86_64.tar.gz\n"
            return json.dumps(release).encode()

        item = {"name": "GE-Proton", "source": {"type": "github_release", "repo": "g/p", "tag": "GE-Proton11-11",
                                                 "asset": "^GE-Proton11-11-x86_64\\.tar\\.gz$",
                                                 "sha512sums": "^GE-Proton11-11-x86_64\\.sha512sum$"}}
        found = tp.resolve(item, fetch)
        self.assertEqual((found["sha512"], found["url"]), ("abc123", "https://d/p.tar.gz"))

    def test_tree_install(self):
        # (the real GE-Proton11-11 tarball's top folder is GE-Proton11-11-x86_64: Sunie's log, 2026-11-18)
        data = tar_bytes([("GE-Proton11-11-x86_64/proton", b"#!/usr/bin/env python3\n", 0o755, None),
                          ("GE-Proton11-11-x86_64/files/lib/libx.so.1", b"x", 0o644, None),
                          ("GE-Proton11-11-x86_64/files/lib/libx.so", None, 0, "libx.so.1")])
        digest = hashlib.sha512(data).hexdigest()
        release = {"tag_name": "GE-Proton11-11", "assets": [
            {"name": "GE-Proton11-11-x86_64.tar.gz", "browser_download_url": "https://d/p.tar.gz"},
            {"name": "GE-Proton11-11-x86_64.sha512sum", "browser_download_url": "https://d/p.sha512sum"}]}

        def fetch(url, timeout=60):
            if url.endswith(".sha512sum"):
                return f"{digest}  GE-Proton11-11-x86_64.tar.gz\n".encode()
            if url.endswith(".tar.gz"):
                return data
            return json.dumps(release).encode()

        item = [i for i in tp.load_manifest(KIT, "linux") if i["id"] == "proton"][0]
        with tempfile.TemporaryDirectory() as kit:
            tp.install(item, kit, os.path.join(kit, "Ashita"), fetch=fetch, log=lambda m: None)
            proton = os.path.join(kit, "proton", "GE-Proton11-11-x86_64")
            self.assertTrue(os.access(os.path.join(proton, "proton"), os.X_OK))
            self.assertEqual(os.readlink(os.path.join(proton, "files", "lib", "libx.so")), "libx.so.1")
            self.assertTrue(tp.status(item, kit, os.path.join(kit, "Ashita"))[0])
            self.assertEqual(ll.installed_proton(kit), proton)
            bad = lambda url, timeout=60: b"0" * 128 + b"  GE-Proton11-11-x86_64.tar.gz" if url.endswith("sum") else fetch(url)
            shutil.rmtree(os.path.join(kit, "downloads"))
            with self.assertRaises(RuntimeError):
                tp.install(item, kit, os.path.join(kit, "Ashita"), fetch=bad, log=lambda m: None)

    def test_tree_unpack_twice(self):
        # a relative link deep inside (like GE-Proton's default_pfx drivers) must unpack again over the first copy
        entries = [("P/files/lib/wine/x.sys", b"x", 0o644, None),
                   ("P/files/share/pfx/drive_c/windows/system32/drivers/x.sys", None, 0, "../../../../../../lib/wine/x.sys")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.tar.gz")
            with open(path, "wb") as handle:
                handle.write(tar_bytes(entries))
            dest = os.path.join(tmp, "dest")
            tp.extract_tree(path, dest)
            tp.extract_tree(path, dest)
            with open(os.path.join(dest, "P/files/share/pfx/drive_c/windows/system32/drivers/x.sys"), "rb") as f:
                self.assertEqual(f.read(), b"x")

    def test_tree_refuses_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            for entries in ([("../escape", b"x", 0o644, None)], [("ok/link", None, 0, "/etc")],
                            [("ok/link", None, 0, "../../x")]):
                path = os.path.join(tmp, "bad.tar.gz")
                with open(path, "wb") as handle:
                    handle.write(tar_bytes(entries))
                with self.assertRaises(RuntimeError):
                    tp.extract_tree(path, os.path.join(tmp, "dest"))

    def test_server_tar_install(self):
        data = tar_bytes([("xi-forever-offline-server-v1/xi_map", b"\x7fELF", 0o755, None),
                          ("xi-forever-offline-server-v1/sql/a.sql", b"--", 0o644, None),
                          ("xi-forever-offline-server-v1/settings/network.lua", b"new", 0o644, None)])
        sums = f"{hashlib.sha256(data).hexdigest()}  xi-forever-offline-server-v1-linux-x64.tar.gz\n".encode()
        release = {"tag_name": "v1", "assets": [
            {"name": "xi-forever-offline-server-v1-win64.zip", "browser_download_url": "https://d/w.zip"},
            {"name": "xi-forever-offline-server-v1-linux-x64.tar.gz", "browser_download_url": "https://d/l.tar.gz"},
            {"name": "SHA256SUMS-linux.txt", "browser_download_url": "https://d/sums"}]}

        def fetch(url, timeout=60):
            return {"https://d/l.tar.gz": data, "https://d/sums": sums}.get(url) or json.dumps([release]).encode()

        item = [i for i in tp.load_manifest(KIT, "linux") if i["id"] == "server"][0]
        with tempfile.TemporaryDirectory() as tmp:
            server = os.path.join(tmp, "server")
            os.makedirs(os.path.join(server, "settings"))
            with open(os.path.join(server, "settings", "network.lua"), "w") as handle:
                handle.write("mine")
            tp.install(item, tmp, os.path.join(tmp, "Ashita"), fetch=fetch, log=lambda m: None, server=server)
            self.assertTrue(os.access(os.path.join(server, "xi_map"), os.X_OK))
            with open(os.path.join(server, "settings", "network.lua")) as handle:
                self.assertEqual(handle.read(), "mine")
            self.assertTrue(ls.valid_server(server))

    def test_update_unpack(self):
        data = tar_bytes([("XI Forever Offline/XI-Forever-Offline", b"new", 0o755, None),
                          ("XI Forever Offline/launcher_core.py", b"code", 0o644, None),
                          ("XI Forever Offline/keep.txt", b"theirs", 0o644, None)])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "k.tar.gz")
            with open(path, "wb") as handle:
                handle.write(data)
            kit = os.path.join(tmp, "kit")
            os.makedirs(kit)
            with open(os.path.join(kit, "keep.txt"), "w") as handle:
                handle.write("mine")
            self.assertEqual(lu._unpack(path, kit, keep=("keep.txt",), log=lambda m: None), 2)
            self.assertTrue(os.access(os.path.join(kit, "XI-Forever-Offline"), os.X_OK))
            self.assertFalse(os.access(os.path.join(kit, "launcher_core.py"), os.X_OK))
            with open(os.path.join(kit, "keep.txt")) as handle:
                self.assertEqual(handle.read(), "mine")
        self.assertTrue(lu.KIT_ASSET.endswith("linux-x64\\.tar\\.gz$"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
