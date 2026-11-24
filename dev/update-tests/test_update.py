"""Stand-in tests for launcher_update.py (player updates): no network, no MariaDB. Run: python test_update.py [server folder]"""
import hashlib, io, json, os, shutil, sys, tempfile, unittest, zipfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_update as up
import launcher_thirdparty as tp


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)
    return buf.getvalue()


class Done:
    def __init__(self, out=""):
        self.returncode, self.stdout, self.stderr = 0, out, ""


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kit = os.path.join(self.tmp, "kit"); os.makedirs(self.kit)
        self.server = os.path.join(self.tmp, "server")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def releases(self, repo_assets):
        """A stand-in GitHub: {repo: [(tag, prerelease, {asset: bytes})]}"""
        urls = {}
        def fetch(url, timeout=60):
            for repo, rels in repo_assets.items():
                if url == tp.API + repo + "/releases?per_page=30":
                    out = []
                    for tag, pre, assets in rels:
                        items = []
                        for name, data in assets.items():
                            urls[f"u/{repo}/{tag}/{name}"] = data
                            items.append({"name": name, "browser_download_url": f"u/{repo}/{tag}/{name}"})
                        out.append({"tag_name": tag, "prerelease": pre, "draft": False, "body": "notes " + tag, "assets": items})
                    return json.dumps(out).encode()
            return urls[url]
        return fetch

    def test_versions_sort_as_numbers(self):
        self.assertGreater(up.version_key("v0.1.10"), up.version_key("v0.1.9"))

    def test_check_respects_test_builds(self):
        open(os.path.join(self.kit, "VERSION.txt"), "w").write("XI: Forever Offline v0.1.0\n")
        fetch = self.releases({up.KIT_REPO: [("v0.1.0", True, {}), ("v0.2.0", True, {}), ("v0.1.1", False, {})],
                               up.SERVER_REPO: [("v0.1.0", True, {})]})
        r = up.check(self.kit, None, False, fetch)
        self.assertEqual((r["kit"]["newest"], r["kit"]["newer"]), ("v0.1.1", True))
        self.assertIsNone(r["server"]["newest"])
        self.assertEqual(up.check(self.kit, None, True, fetch)["kit"]["newest"], "v0.2.0")

    def test_kit_update_keeps_personal_files_and_checks_sum(self):
        for name, data in (("config.json", "mine"), ("launcher_core.py", "old"), ("rates.json", "my rates")):
            open(os.path.join(self.kit, name), "w").write(data)
        data = zip_bytes({"XI Forever Offline/launcher_core.py": "new", "XI Forever Offline/VERSION.txt": "XI: Forever Offline v0.1.1\n"})
        name = "xi-forever-offline-v0.1.1-win64.zip"
        good = self.releases({up.KIT_REPO: [("v0.1.1", False, {name: data, "SHA256SUMS.txt": (hashlib.sha256(data).hexdigest() + "  " + name).encode()})]})
        rel = up.newest_release(up.KIT_REPO, False, good)
        up.update_kit(self.kit, rel, good, log=lambda m: None)
        read = lambda n: open(os.path.join(self.kit, n)).read()
        self.assertEqual((read("launcher_core.py"), read("config.json"), read("rates.json")), ("new", "mine", "my rates"))
        self.assertEqual(up.installed_version(self.kit), "v0.1.1")
        bad = self.releases({up.KIT_REPO: [("v0.1.2", False, {name: data + b"x", "SHA256SUMS.txt": (hashlib.sha256(data).hexdigest() + "  " + name).encode()})]})
        with self.assertRaises(RuntimeError):
            up.update_kit(self.kit, up.newest_release(up.KIT_REPO, False, bad), bad, log=lambda m: None)

    def test_running_exe_is_moved_aside(self):
        exe = os.path.join(self.kit, "XI Forever Offline.exe"); open(exe, "w").write("old exe")
        zpath = os.path.join(self.tmp, "k.zip"); open(zpath, "wb").write(zip_bytes({"top/XI Forever Offline.exe": "new exe"}))
        up._unpack(zpath, self.kit, log=lambda m: None, running_exe=exe)
        self.assertEqual(open(exe).read(), "new exe")
        self.assertEqual(open(os.path.join(self.kit, "XI Forever Offline.old.exe")).read(), "old exe")

    # ---- (v0.3.3 launcher fixes) the release zip goes to disk a piece at a time ----
    def test_release_zip_is_streamed_and_checked(self):
        data = os.urandom(2 * (1 << 20) + 5)
        name = "xi-forever-offline-v9.9.9-win64.zip"
        answers = {"u/zip": data, "u/sums": (hashlib.sha256(data).hexdigest() + "  " + name).encode()}
        asked = []

        class Response:
            def __init__(self, body):
                self.body = io.BytesIO(body)
            def read(self, size=None):
                asked.append(size)
                return self.body.read() if size is None else self.body.read(size)
            def __enter__(self):
                return self
            def __exit__(self, *exc):
                return False
        real = tp._open_url
        tp._open_url = lambda url, timeout=60, headers=None: Response(answers[url])
        try:
            release = {"tag_name": "v9.9.9", "assets": [{"name": name, "browser_download_url": "u/zip"},
                                                         {"name": "SHA256SUMS.txt", "browser_download_url": "u/sums"}]}
            path = up._download(release, up.KIT_ASSET, self.kit, tp._get, lambda m: None, "launcher")
            self.assertEqual(open(path, "rb").read(), data)
            self.assertTrue(all(size is not None and size <= 1 << 20 for size in asked[-4:]))
            answers["u/zip"] = data + b"!"                      # a changed file: refused, nothing kept
            os.remove(path)
            with self.assertRaises(RuntimeError):
                up._download(release, up.KIT_ASSET, self.kit, tp._get, lambda m: None, "launcher")
            self.assertFalse(os.path.exists(path))
            self.assertFalse(os.path.exists(path + ".part"))
        finally:
            tp._open_url = real

    # ---- (Hasuko, 2026-11-22) "Update stopped: [WinError 5] Access is denied: ...xifo_theme...mp3.part -> ...mp3"
    def _held(self, names, times=10 ** 6):
        """os.replace as Windows does it for a file another program has open: PermissionError for these targets."""
        real, left = os.replace, {n: times for n in names}

        def replace(src, dst):
            name = os.path.basename(dst)
            if left.get(name, 0) > 0:
                left[name] -= 1
                raise PermissionError(5, "Access is denied", src, None, dst)
            return real(src, dst)
        return replace

    def _kit_zip(self, files):
        zpath = os.path.join(self.tmp, "k.zip")
        open(zpath, "wb").write(zip_bytes({"xi/" + n: d for n, d in files.items()}))
        return zpath

    def _with(self, replace, call):
        real, wait = os.replace, up.REPLACE_WAIT
        os.replace, up.REPLACE_WAIT = replace, 0
        try:
            return call()
        finally:
            os.replace, up.REPLACE_WAIT = real, wait

    def test_unchanged_file_is_left_alone_even_while_it_is_open(self):
        os.makedirs(os.path.join(self.kit, "assets", "press"))
        song = os.path.join(self.kit, "assets", "press", "theme.mp3")
        open(song, "wb").write(b"SONG" * 1000)
        before = os.stat(song).st_mtime_ns
        zpath = self._kit_zip({"assets/press/theme.mp3": b"SONG" * 1000, "launcher_core.py": "new", "VERSION.txt": "v2"})
        said = []
        count = self._with(self._held(["theme.mp3"]), lambda: up._unpack(zpath, self.kit, log=said.append))
        self.assertEqual(count, 2)                                              # the two that changed
        self.assertEqual(os.stat(song).st_mtime_ns, before)                     # not written again
        self.assertFalse(os.path.exists(song + ".part"))
        self.assertEqual(open(os.path.join(self.kit, "VERSION.txt")).read(), "v2")
        self.assertIn("1 already up to date", said[0])

    def test_changed_song_that_is_being_played_does_not_stop_the_update(self):
        os.makedirs(os.path.join(self.kit, "assets", "press"))
        song = os.path.join(self.kit, "assets", "press", "theme.mp3")
        open(song, "wb").write(b"OLD SONG")
        zpath = self._kit_zip({"assets/press/theme.mp3": b"NEW SONG", "launcher_core.py": "new", "VERSION.txt": "v2"})
        said = []
        count = self._with(self._held(["theme.mp3"]), lambda: up._unpack(zpath, self.kit, log=said.append))
        self.assertEqual(count, 2)
        self.assertEqual(open(song, "rb").read(), b"OLD SONG")                  # kept, replaced at the next update
        self.assertFalse(os.path.exists(song + ".part"))                        # and no leftover beside it
        self.assertEqual(open(os.path.join(self.kit, "launcher_core.py")).read(), "new")
        self.assertEqual(open(os.path.join(self.kit, "VERSION.txt")).read(), "v2")
        self.assertTrue(any("Left as it was" in line and "assets/press/theme.mp3" in line for line in said))

    def test_file_held_for_a_moment_is_replaced_on_a_later_try(self):
        open(os.path.join(self.kit, "launcher_core.py"), "w").write("old")
        zpath = self._kit_zip({"launcher_core.py": "new"})
        count = self._with(self._held(["launcher_core.py"], times=3), lambda: up._unpack(zpath, self.kit, log=lambda m: None))
        self.assertEqual(count, 1)
        self.assertEqual(open(os.path.join(self.kit, "launcher_core.py")).read(), "new")

    def test_changed_program_file_that_stays_held_stops_with_a_plain_reason(self):
        target = os.path.join(self.kit, "launcher_core.py")
        open(target, "w").write("old")
        zpath = self._kit_zip({"launcher_core.py": "new"})
        with self.assertRaises(RuntimeError) as caught:
            self._with(self._held(["launcher_core.py"]), lambda: up._unpack(zpath, self.kit, log=lambda m: None))
        self.assertIn("another program has it open", str(caught.exception))
        self.assertIn("Update again", str(caught.exception))
        self.assertFalse(os.path.exists(target + ".part"))
        self.assertEqual(open(target).read(), "old")

    def test_same_size_but_other_content_is_replaced(self):
        target = os.path.join(self.kit, "launcher_core.py")
        open(target, "w").write("abc")
        up._unpack(self._kit_zip({"launcher_core.py": "abd"}), self.kit, log=lambda m: None)
        self.assertEqual(open(target).read(), "abd")

    def test_songs_go_last_in_the_player_zip(self):
        import package_kit as pk
        self.assertTrue(pk.is_song("assets/press/xifo_theme__plays-1__until-2026-12-02.mp3"))
        self.assertTrue(pk.is_song("assets/press/default.MP3"))
        self.assertFalse(pk.is_song("assets/press/banner.png"))
        self.assertFalse(pk.is_song("tetramaster/assets/sound/mus_quadmist.mp3"))   # the launcher never plays that one
        source = open(os.path.join(KIT, "package_kit.py"), encoding="utf-8").read()
        body = source[source.index("with zipfile.ZipFile(target"):source.index("digest = hashlib.sha256()", source.index("with zipfile.ZipFile(target"))]
        self.assertLess(body.index('archive.write(exe, TOP + EXE)'), body.index('for rel in songs:'))
        self.assertLess(body.index('TOP + "VERSION.txt"'), body.index('for rel in songs:'))

    def test_the_song_is_stopped_before_an_update(self):
        source = open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8").read()
        body = source[source.index("    def player_update(self):"):source.index("    def restart_launcher(self)") if "    def restart_launcher(self)" in source else None]
        self.assertIn("launcher_theme.PLAYER.stop()", body)
        self.assertLess(body.index("launcher_theme.PLAYER.stop()"), body.index("threading.Thread(target=work"))   # on the window's thread

    def test_database_update_keeps_player_tables_and_runs_migrations(self):
        os.makedirs(os.path.join(self.server, "sql")); os.makedirs(os.path.join(self.server, "tools", "migrations"))
        for f in ("accounts.sql", "chars.sql", "item_basic.sql", "triggers.sql"):
            open(os.path.join(self.server, "sql", f), "w").write("--")
        open(os.path.join(self.server, "tools", "migrations", "001_x.py"), "w").write(
            "def migration_name(): return 'x'\ndef check_preconditions(cur): pass\n"
            "def needs_to_run(cur): return True\ndef migrate(cur, db): cur.execute('ALTER x')\n")
        calls, executed = [], []

        def run(cmd, **kw):
            calls.append(cmd[-1])
            return Done("accounts\nchars\nitem_basic\n" if cmd[-1] == "SHOW TABLES" else "")

        class Cur:
            def execute(self, q): executed.append(q)

        class Db:
            def cursor(self): return Cur()
            def commit(self): pass
            def close(self): pass
        cfg = {"mariadb_dir": self.tmp, "db_port": 3306, "db_user": "xi", "db_pass": "p", "db_name": "xiforever"}
        up.update_database(cfg, self.server, log=lambda m: None, run=run, connect=lambda: Db())
        imported = [c for c in calls if "SOURCE" in c]
        self.assertEqual(len(imported), 2)                       # item_basic + triggers; accounts and chars kept
        self.assertTrue(all("accounts.sql" not in c and "chars.sql" not in c for c in imported))
        self.assertEqual(executed, ["ALTER x"])

    def test_real_player_table_list(self):
        server = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None
        if not server:
            self.skipTest("no server folder given")
        self.assertEqual(sorted(up.player_tables(server)), sorted(up.PLAYER_DATA))


if __name__ == "__main__":
    unittest.main(argv=sys.argv[:1], verbosity=1)
