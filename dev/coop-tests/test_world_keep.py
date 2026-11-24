"""Tests for a world's nightly backups and its own updates (launcher_world_keep.py, 2026-11-23). The database programs
are stand-ins here, the release packages are real .tar.gz files made by the test, and the players' updater
(launcher_update.py) is the real one. With WORLD_TEST_MARIADB=<a folder laid out like the kit's mariadb folder> the
backup and the restore are also run against a real database.   Run: python test_world_keep.py"""
import gzip, hashlib, io, json, os, shutil, sys, tarfile, tempfile, time, unittest
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_setup as setup
import launcher_thirdparty as tp
import launcher_update as lu
import launcher_world_keep as keep

DUMP = "-- MariaDB dump\nCREATE TABLE `chars` (charid int);\nINSERT INTO `chars` VALUES (1);\n-- Dump completed on 2026-11-23  4:00:00\n"
KIT_NAME = "xi-forever-offline-{}-linux-x64.tar.gz"
SERVER_NAME = "xi-forever-offline-server-{}-linux-x64.tar.gz"
LINUX = os.name != "nt"


class Done:
    def __init__(self, out="", code=0, err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


class FakeMaria:
    """Stands in for the database's programs: records every command; a dump writes a small finished dump file."""

    def __init__(self):
        self.calls, self.dump, self.fail, self.fail_once, self.tables = [], DUMP, None, None, "chars\n"

    def run(self, cmd, **kw):
        self.calls.append(list(cmd))
        text = " ".join(str(part) for part in cmd)
        if self.fail and self.fail in text:
            return Done(code=1, err="it failed")
        if self.fail_once and self.fail_once in text:
            self.fail_once = None
            return Done(code=1, err="it failed once")
        if text.endswith("SHOW TABLES"):
            return Done(self.tables)
        for part in cmd:
            if str(part).startswith("--result-file="):
                if self.dump is None:
                    return Done(code=1, err="Got error: 1045: Access denied")
                with open(str(part).split("=", 1)[1], "w") as handle:
                    handle.write(self.dump)
        return Done("")

    def statements(self):
        return [c[-1] for c in self.calls if "-e" in c]


class Net:
    """Stands in for the internet: answers by address, and counts what was asked for."""

    def __init__(self):
        self.pages, self.asked = {}, []

    def __call__(self, url, timeout=60):
        self.asked.append(url)
        if url not in self.pages:
            raise OSError("no such page: " + url)
        return self.pages[url]


def package(path, files, top="XI Forever Offline"):
    with tarfile.open(path, "w:gz") as archive:
        for rel, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(top + "/" + rel)
            info.size, info.mode = len(data), 0o755 if rel.endswith(("xi_map", ".sh")) else 0o644
            archive.addfile(info, io.BytesIO(data))
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def publish(net, folder, repo, tag, files=None, name=None, prerelease=False, sums=True, wrong_sum=False):
    """Publishes a release on the stand-in internet with its Linux package (files: what is in it; None: no package yet)."""
    template = KIT_NAME if repo == lu.KIT_REPO else SERVER_NAME
    assets = []
    if files is not None:
        name = name or template.format(tag)
        path = package(os.path.join(folder, name), files, top="XI Forever Offline" if repo == lu.KIT_REPO else "server")
        with open(path, "rb") as handle:
            data = handle.read()
        url = f"https://dl/{repo}/{tag}/{name}"
        net.pages[url] = data
        assets.append({"name": name, "browser_download_url": url})
        if sums:
            digest = "0" * 64 if wrong_sum else hashlib.sha256(data).hexdigest()
            net.pages[url + ".sums"] = f"{digest}  {name}\n".encode()
            assets.append({"name": keep.SUMS_NAME, "browser_download_url": url + ".sums"})
    made = {"tag_name": tag, "draft": False, "prerelease": prerelease, "body": "notes", "assets": assets}
    page = tp.API + repo + "/releases?per_page=30"
    net.pages[page] = json.dumps(json.loads(net.pages.get(page, b"[]")) + [made]).encode()
    return made


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.kit = os.path.join(self.tmp, "kit")
        self.server = os.path.join(self.kit, "server")
        self.mdb = os.path.join(self.kit, "mariadb")
        for folder in (self.server + "/sql", self.server + "/settings", self.mdb, self.kit + "/logs"):
            os.makedirs(folder)
        with open(os.path.join(self.mdb, "xiforever-db.json"), "w") as handle:
            json.dump({"root": "rootpw", "xi": "xipw", "port": 3306}, handle)
        self.cfg = {"server_dir": self.server, "mariadb_dir": self.mdb, "db_name": "xiforever", "db_user": "xi", "db_pass": "xipw", "db_port": 3306}
        self.put(self.kit, {"VERSION.txt": "XI: Forever Offline v0.3.2\n", "launcher_core.py": "old core\n", "ah_sim.py": "old sim\n",
                            "config.json": "{}\n"})
        self.put(self.server, {"VERSION.txt": "XI: Forever Offline server v0.3.2\n", "xi_map": "old map\n", "sql/chars.sql": "--\n",
                               "sql/triggers.sql": "--\n", "settings/network.lua": "my database login\n"})
        self.maria, self.net, self.lines = FakeMaria(), Net(), []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, folder, files):
        for rel, text in files.items():
            path = os.path.join(folder, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)

    def backup_file(self, kind, when, text=DUMP):
        folder = keep.backup_folder(self.kit)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"db-{kind}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(when))}.sql.gz")
        with gzip.open(path, "wb") as handle:
            handle.write(text.encode())
        return path

    # --- a release on the stand-in internet ---
    def release(self, repo, tag, files=None, **more):
        return publish(self.net, self.tmp, repo, tag, files, **more)

    def nothing_new(self, repo):
        self.net.pages.setdefault(tp.API + repo + "/releases?per_page=30", b"[]")


class Settings(Base):
    def test_every_value_has_a_default_and_a_range(self):
        self.assertEqual(keep.load_settings(self.kit), keep.DEFAULTS)
        self.put(self.kit, {"world.json": json.dumps({"backup_hour": 99, "backup_keep_days": 0, "auto_update": "yes",
                                                      "update_notice_minutes": "3", "update_check_minutes": 1, "other": 1})})
        got = keep.load_settings(self.kit)
        self.assertEqual((got["backup_hour"], got["backup_keep_days"], got["auto_update"], got["update_notice_minutes"],
                          got["update_check_minutes"]), (23, 1, True, 3, 5))
        got["auto_update"] = False
        keep.save_settings(self.kit, got)
        self.assertEqual(keep.load_settings(self.kit)["auto_update"], False)
        self.assertNotIn("other", json.loads(read(os.path.join(self.kit, "world.json"))))


class Backups(Base):
    def test_a_backup_is_one_packed_file_and_nothing_else(self):
        path = keep.backup_now(self.cfg, self.kit, "nightly", log=self.lines.append, run=self.maria.run, now=1795000000)
        self.assertEqual(os.listdir(keep.backup_folder(self.kit)), [os.path.basename(path)])
        self.assertRegex(os.path.basename(path), r"^db-nightly-\d{8}-\d{6}\.sql\.gz$")
        with gzip.open(path, "rt") as handle:
            self.assertEqual(handle.read(), DUMP)
        command = self.maria.calls[0]
        self.assertTrue(command[0].endswith("mariadb-dump") and "--single-transaction" in command and command[-1] == "xiforever")
        self.assertIn("--no-defaults", command)                 # (Linux: the kit's own programs, never /etc/my.cnf)
        self.assertEqual(keep.check_backup(path), len(DUMP))
        self.assertEqual([(b["kind"], b["file"]) for b in keep.backups(self.kit)], [("nightly", os.path.basename(path))])

    def test_a_dump_that_failed_or_was_cut_short_leaves_nothing(self):
        self.maria.dump = None
        with self.assertRaises(keep.KeepError) as caught:
            keep.backup_now(self.cfg, self.kit, run=self.maria.run)
        self.assertIn("Access denied", str(caught.exception))
        self.maria.dump = "CREATE TABLE `chars` (charid int);\nINSERT INTO"          # the program ended early without saying so
        with self.assertRaises(keep.KeepError):
            keep.backup_now(self.cfg, self.kit, run=self.maria.run)
        self.assertEqual(os.listdir(keep.backup_folder(self.kit)), [])

    def test_no_backup_on_a_disk_that_is_nearly_full(self):
        kept, keep._free = keep._free, lambda folder: keep.SPARE_BYTES - 1
        try:
            with self.assertRaises(keep.KeepError) as caught:
                keep.backup_now(self.cfg, self.kit, run=self.maria.run)
        finally:
            keep._free = kept
        self.assertIn("nearly full", str(caught.exception))
        self.assertEqual(self.maria.calls, [])

    def test_due_once_after_each_backup_hour(self):
        settings = dict(keep.DEFAULTS, backup_hour=4)
        day = time.mktime((2026, 11, 23, 0, 0, 0, 0, 0, -1))
        at = lambda hour, minute=0: day + hour * 3600 + minute * 60
        self.assertTrue(keep.due(settings, 0, at(12)))                       # never saved
        self.assertTrue(keep.due(settings, at(3, 59), at(4, 1)))             # saved before today's hour
        self.assertFalse(keep.due(settings, at(4, 1), at(23)))               # saved since
        self.assertFalse(keep.due(settings, at(4, 1) - 86400, at(3, 59)))    # today's hour has not come: yesterday's copy counts
        self.assertTrue(keep.due(settings, at(3) - 86400, at(3, 59)))        # ...but one from before yesterday's hour does not

    def test_old_nightly_copies_go_and_the_newest_three_always_stay(self):
        now = 1795000000
        day = 86400
        files = {age: self.backup_file("nightly", now - age * day) for age in (1, 2, 3, 6, 9, 30)}
        hand = self.backup_file("by-hand", now - 400 * day)
        before = [self.backup_file("before-update", now - age * day) for age in (5, 50, 90)]
        stray = os.path.join(keep.backup_folder(self.kit), "db-nightly-20200101-000000.sql")
        fresh = os.path.join(keep.backup_folder(self.kit), "db-nightly-20990101-000000.sql")
        for path in (stray, fresh):
            self.put(os.path.dirname(path), {os.path.basename(path): "half"})
        os.utime(stray, (now - 3 * day, now - 3 * day))
        os.utime(fresh, (now - 60, now - 60))                            # (a copy being made right now)
        removed = keep.prune(self.kit, dict(keep.DEFAULTS, backup_keep_days=7), now=now, log=self.lines.append)
        left = set(os.listdir(keep.backup_folder(self.kit)))
        gone = {os.path.basename(files[9]), os.path.basename(files[30]), os.path.basename(before[2]), os.path.basename(stray)}
        self.assertEqual(set(removed), gone)
        self.assertEqual(left, {os.path.basename(p) for p in list(files.values()) + before + [hand, fresh]} - gone)
        # a world that was switched off for a month keeps its newest three, however old
        removed = keep.prune(self.kit, dict(keep.DEFAULTS, backup_keep_days=7), now=now + 60 * day, log=self.lines.append)
        self.assertEqual([n for n in removed if "nightly" in n and n.endswith(".gz")], [os.path.basename(files[6])])
        self.assertTrue(all(os.path.exists(files[age]) for age in (1, 2, 3)))
        self.assertTrue(os.path.exists(hand))

    def test_only_a_whole_copy_is_ever_put_back(self):
        good = self.backup_file("nightly", 1795000000)
        cut = self.backup_file("nightly", 1795000100, DUMP[:60])
        other = self.backup_file("nightly", 1795000200, DUMP.replace("`chars`", "`notes`"))
        broken = os.path.join(keep.backup_folder(self.kit), "db-nightly-20261124-040000.sql.gz")
        with open(good, "rb") as whole, open(broken, "wb") as part:
            part.write(whole.read()[:-12])
        for path in (cut, other, broken, os.path.join(self.tmp, "not-there.sql.gz")):
            with self.assertRaises(keep.KeepError):
                keep.restore(self.cfg, self.kit, path, run=self.maria.run)
        self.assertEqual(self.maria.calls, [], "nothing is dropped for a copy that cannot be used")
        keep.restore(self.cfg, self.kit, good, log=self.lines.append, run=self.maria.run)
        drop, source = self.maria.statements()
        self.assertIn("DROP DATABASE IF EXISTS `xiforever`; CREATE DATABASE `xiforever`", drop)
        self.assertIn("-uroot", self.maria.calls[0])
        self.assertIn("-prootpw", self.maria.calls[0])
        self.assertRegex(source, r"SOURCE .*restore-\d{8}-\d{6}-\d+\.sql; ")
        self.assertIn("-uxi", self.maria.calls[1])
        self.assertEqual([n for n in os.listdir(keep.backup_folder(self.kit)) if n.startswith("restore-")], [], "the unpacked copy is removed")
        before = len(self.maria.calls)
        with self.assertRaises(keep.KeepError) as caught:       # a world on a database service of its own (the dev PC)
            keep.restore(dict(self.cfg, mariadb_dir=""), self.kit, good, run=self.maria.run)
        self.assertIn("the kit's own database", str(caught.exception))
        self.assertEqual(len(self.maria.calls), before)


@unittest.skipUnless(LINUX, "the packages here are the Linux ones")
class Snapshots(Base):
    def test_files_are_put_back_and_new_ones_removed(self):
        pack = package(os.path.join(self.tmp, "p.tar.gz"), {"xi_map": "new map\n", "sql/chars.sql": "new\n", "sql/added.sql": "added\n",
                                                            "settings/network.lua": "the default login\n", "../outside": "x"}, top="server")
        snap = os.path.join(self.tmp, "snap")
        made = keep.snapshot(pack, self.server, snap, keep=("settings/network.lua",))
        self.assertEqual((sorted(made["existing"]), made["new"]), (["sql/chars.sql", "xi_map"], ["sql/added.sql"]))
        self.assertEqual(keep.snapshot_bytes(pack, self.server, keep=("settings/network.lua",)), len("old map\n") + len("--\n"))
        self.assertNotIn("../outside", keep.package_files(pack))
        self.put(self.server, {"xi_map": "new map\n", "sql/chars.sql": "new\n", "sql/added.sql": "added\n"})     # what the update does
        self.assertEqual(keep.restore_snapshot(snap, self.server), (2, 1))
        self.assertEqual((read(self.server + "/xi_map"), read(self.server + "/sql/chars.sql")), ("old map\n", "--\n"))
        self.assertFalse(os.path.exists(self.server + "/sql/added.sql"))
        self.assertEqual(read(self.server + "/settings/network.lua"), "my database login\n")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "outside")))
        with self.assertRaises(keep.KeepError):
            keep.restore_snapshot(os.path.join(self.tmp, "no-snap"), self.server)


@unittest.skipUnless(LINUX, "the packages here are the Linux ones")
class Updates(Base):
    NEW_KIT = {"launcher_core.py": "new core\n", "launcher_new.py": "added\n", "VERSION.txt": "XI: Forever Offline v0.3.3\n"}
    NEW_SERVER = {"xi_map": "new map\n", "sql/chars.sql": "new table\n", "sql/more.sql": "--\n", "settings/network.lua": "the default login\n",
                  "VERSION.txt": "XI: Forever Offline server v0.3.3\n"}

    def both(self, tag="v0.3.3"):
        return self.release(lu.KIT_REPO, tag, self.NEW_KIT), self.release(lu.SERVER_REPO, tag, self.NEW_SERVER)

    def pending(self, found):
        cache = keep.download(self.kit, found, self.net, log=self.lines.append)
        state = dict(found, state="pending", files=cache.files, texts=cache.texts)
        state.pop("waiting", None)
        keep.save_state(self.kit, state)
        return state

    def as_before(self):
        return (read(self.kit + "/launcher_core.py"), os.path.exists(self.kit + "/launcher_new.py"), read(self.kit + "/VERSION.txt"),
                read(self.server + "/xi_map"), read(self.server + "/sql/chars.sql"), os.path.exists(self.server + "/sql/more.sql"),
                read(self.server + "/VERSION.txt")) == ("old core\n", False, "XI: Forever Offline v0.3.2\n", "old map\n", "--\n", False,
                                                        "XI: Forever Offline server v0.3.2\n")

    # --- finding one ---
    def test_only_full_releases_with_their_files_and_checksums(self):
        self.release(lu.KIT_REPO, "v0.3.2", self.NEW_KIT)
        self.release(lu.SERVER_REPO, "v0.3.2", self.NEW_SERVER)
        found = keep.find_update(self.kit, self.cfg, self.net)
        self.assertEqual((found["kit"], found["server"], found["waiting"]), (None, None, []))            # nothing newer
        self.release(lu.KIT_REPO, "v0.4.0-test1", self.NEW_KIT, prerelease=True)                           # a test build: never
        self.assertIsNone(keep.find_update(self.kit, self.cfg, self.net)["kit"])
        self.release(lu.KIT_REPO, "v0.3.3")                                                                # released, Linux files not up yet
        self.release(lu.SERVER_REPO, "v0.3.3", self.NEW_SERVER, sums=False)                                # the package without its checksums
        found = keep.find_update(self.kit, self.cfg, self.net)
        self.assertEqual((found["kit"], found["server"], found["waiting"]), (None, None, ["launcher v0.3.3", "server v0.3.3"]))

    def test_a_release_that_is_ready_is_found_with_where_it_comes_from(self):
        self.both()
        found = keep.find_update(self.kit, self.cfg, self.net)
        self.assertEqual((found["kit"]["tag_name"], found["kit"]["from"], found["server"]["tag_name"], found["waiting"]),
                         ("v0.3.3", "v0.3.2", "v0.3.3", []))
        self.assertEqual(keep.tags(found), "v0.3.3")
        self.assertEqual(keep.tags({"kit": {"tag_name": "v0.3.3"}, "server": {"tag_name": "v0.3.4"}}), "launcher v0.3.3, server v0.3.4")
        keep._write_json(keep.skip_path(self.kit), {"kit": "v0.3.3", "server": "v0.3.3", "why": "x"})     # taken back earlier
        found = keep.find_update(self.kit, self.cfg, self.net)
        self.assertEqual((found["kit"], found["server"]), (None, None))
        self.release(lu.SERVER_REPO, "v0.3.4", self.NEW_SERVER)                                            # a newer one is tried again
        self.assertEqual(keep.find_update(self.kit, self.cfg, self.net)["server"]["tag_name"], "v0.3.4")

    def test_a_download_must_match_its_checksum(self):
        self.release(lu.KIT_REPO, "v0.3.3", self.NEW_KIT, wrong_sum=True)
        self.nothing_new(lu.SERVER_REPO)
        found = keep.find_update(self.kit, self.cfg, self.net)
        with self.assertRaises(keep.KeepError) as caught:
            keep.download(self.kit, found, self.net)
        self.assertIn("checksum", str(caught.exception))
        self.assertEqual(os.listdir(self.kit + "/downloads/updates") if os.path.isdir(self.kit + "/downloads/updates") else [], [])

    def test_a_download_that_the_checksums_do_not_list_is_refused(self):
        made = self.release(lu.KIT_REPO, "v0.3.3", self.NEW_KIT)
        self.nothing_new(lu.SERVER_REPO)
        self.net.pages[made["assets"][1]["browser_download_url"]] = b"abc  some-other-file.tar.gz\n"
        asked = len(self.net.asked)
        with self.assertRaises(keep.KeepError):
            keep.download(self.kit, keep.find_update(self.kit, self.cfg, self.net), self.net)
        self.assertNotIn(made["assets"][0]["browser_download_url"], self.net.asked[asked:], "the package is not even fetched")

    # --- putting one in ---
    def test_an_update_goes_in_with_the_players_updater(self):
        self.both()
        state = self.pending(keep.find_update(self.kit, self.cfg, self.net))
        asked = len(self.net.asked)
        seen = []

        def watching(cmd, **kw):                                 # what is on the disk when the updater's own work begins
            if len(self.maria.calls) == 1:
                seen.append((keep.load_state(self.kit)["state"], read(self.server + "/xi_map"),
                             os.path.exists(os.path.join(keep.update_folder(self.kit), "kit", "manifest.json"))))
            return self.maria.run(cmd, **kw)
        restart = keep.apply(self.kit, self.cfg, state, log=self.lines.append, run=watching, check=lambda kit: None)
        self.assertEqual(seen, [("applying", "old map\n", True)], "noted as begun, and everything copied aside, before a file changes")
        self.assertTrue(restart, "the launcher itself changed")
        self.assertEqual(self.net.asked[asked:], [], "nothing is downloaded a second time")
        self.assertEqual((read(self.kit + "/launcher_core.py"), read(self.kit + "/launcher_new.py"), read(self.kit + "/ah_sim.py")),
                         ("new core\n", "added\n", "old sim\n"))
        self.assertEqual((read(self.server + "/xi_map"), read(self.server + "/settings/network.lua")), ("new map\n", "my database login\n"))
        self.assertEqual((lu.installed_version(self.kit), lu.installed_version(self.server)), ("v0.3.3", "v0.3.3"))
        state = keep.load_state(self.kit)
        self.assertEqual((state["state"], state["tries"], state["files"]), ("applied", 0, {}))
        saved = [b for b in keep.backups(self.kit) if b["kind"] == "before-update"]
        self.assertEqual((len(saved), state["db"]), (1, saved[0]["path"]))
        self.assertEqual([n for n in os.listdir(self.kit + "/backups") if n.endswith(".sql")], [], "the updater's own unpacked copy is not kept twice")
        sources = [s for s in self.maria.statements() if "SOURCE" in s]
        self.assertEqual(len(sources), 2, "the game's tables are imported again (chars.sql is a player table and is not)")
        self.assertFalse(any("chars.sql" in s for s in sources))
        # the first thing done is the copy of the database; the files are copied aside before any is replaced
        self.assertTrue(any(str(part).startswith("--result-file=") for part in self.maria.calls[0]))
        self.assertEqual(read(os.path.join(keep.update_folder(self.kit), "server", "files", "xi_map")), "old map\n")
        self.assertEqual(read(os.path.join(keep.update_folder(self.kit), "kit", "files", "launcher_core.py")), "old core\n")

    def test_a_server_only_update_needs_no_restart_of_the_launcher(self):
        self.nothing_new(lu.KIT_REPO)
        self.release(lu.SERVER_REPO, "v0.3.3", self.NEW_SERVER)
        state = self.pending(keep.find_update(self.kit, self.cfg, self.net))
        checked = []
        self.assertFalse(keep.apply(self.kit, self.cfg, state, log=self.lines.append, run=self.maria.run, check=checked.append))
        self.assertEqual((checked, read(self.kit + "/launcher_core.py"), read(self.server + "/xi_map")), ([], "old core\n", "new map\n"))

    def test_a_new_launcher_that_cannot_start_is_taken_back_at_once(self):
        self.both()
        state = self.pending(keep.find_update(self.kit, self.cfg, self.net))

        def broken(kit):
            raise keep.KeepError("the new launcher did not start: ImportError")
        with self.assertRaises(keep.KeepError) as caught:
            keep.apply(self.kit, self.cfg, state, log=self.lines.append, run=self.maria.run, check=broken)
        self.assertTrue(caught.exception.restart, "the launcher's files were put back: it has to be started again")
        self.assertTrue(self.as_before())
        self.assertIsNone(keep.load_state(self.kit))
        self.assertFalse(os.path.exists(os.path.join(keep.update_folder(self.kit), "kit")))
        skip = keep.load_skip(self.kit)
        self.assertEqual((skip["kit"], skip["server"]), ("v0.3.3", "v0.3.3"))
        statements = self.maria.statements()
        self.assertTrue(any("DROP DATABASE" in s for s in statements) and "SOURCE" in statements[-1], "the database from before is put back")
        found = keep.find_update(self.kit, self.cfg, self.net)
        self.assertEqual((found["kit"], found["server"]), (None, None), "that release is left alone from now on")

    def test_an_update_that_stops_half_way_is_taken_back(self):
        self.both()
        state = self.pending(keep.find_update(self.kit, self.cfg, self.net))
        self.maria.fail_once = "SOURCE"                          # the database update fails after the server's files went in
        with self.assertRaises(keep.KeepError) as caught:
            keep.apply(self.kit, self.cfg, state, log=self.lines.append, run=self.maria.run, check=lambda kit: None)
        self.assertNotIsInstance(caught.exception, keep.Stuck)
        self.assertIn("as it was before", str(caught.exception))
        self.assertTrue(self.as_before())
        self.assertIsNone(keep.load_state(self.kit))
        self.assertEqual(keep.load_skip(self.kit)["server"], "v0.3.3")
        self.assertIn("SOURCE", self.maria.statements()[-1], "the database from before is put back last")

    def test_nothing_is_touched_without_room_or_without_a_copy_of_the_database(self):
        self.both()
        found = keep.find_update(self.kit, self.cfg, self.net)
        state = self.pending(found)
        kept, keep._free = keep._free, lambda folder: 1024
        try:
            with self.assertRaises(keep.KeepError) as caught:
                keep.apply(self.kit, self.cfg, state, run=self.maria.run, check=lambda kit: None)
        finally:
            keep._free = kept
        self.assertIn("disk space", str(caught.exception))
        self.assertTrue(self.as_before() and self.maria.calls == [] and keep.load_state(self.kit) is None)
        self.assertEqual(keep.load_skip(self.kit)["why"], "not enough free disk space")
        os.remove(keep.skip_path(self.kit))
        state = self.pending(found)
        self.maria.dump = None
        with self.assertRaises(keep.KeepError):
            keep.apply(self.kit, self.cfg, state, run=self.maria.run, check=lambda kit: None)
        self.assertTrue(self.as_before() and keep.load_state(self.kit) is None)
        self.assertFalse(getattr(caught.exception, "restart", False))

    def test_a_download_that_is_gone_is_looked_for_again(self):
        self.both()
        found = keep.find_update(self.kit, self.cfg, self.net)
        state = self.pending(found)
        shutil.rmtree(self.kit + "/downloads")
        with self.assertRaises(keep.KeepError):
            keep.apply(self.kit, self.cfg, state, run=self.maria.run, check=lambda kit: None)
        self.assertTrue(self.as_before() and self.maria.calls == [] and keep.load_state(self.kit) is None)
        self.assertEqual(keep.load_skip(self.kit), {}, "not left alone: it is downloaded again at the next look")

    def test_taking_back_puts_files_and_database_back(self):
        self.both()
        state = self.pending(keep.find_update(self.kit, self.cfg, self.net))
        keep.apply(self.kit, self.cfg, state, log=self.lines.append, run=self.maria.run, check=lambda kit: None)
        self.assertFalse(self.as_before())
        before = len(self.maria.calls)
        self.assertTrue(keep.roll_back(self.kit, self.cfg, keep.load_state(self.kit), "the world did not get ready", log=self.lines.append, run=self.maria.run))
        self.assertTrue(self.as_before())
        self.assertTrue(any("DROP DATABASE" in s for s in [c[-1] for c in self.maria.calls[before:]]))
        self.assertIsNone(keep.load_state(self.kit))
        self.assertEqual(keep.load_skip(self.kit)["why"], "the world did not get ready")

    def test_an_update_that_cannot_be_taken_back_waits_for_a_person(self):
        self.both()
        state = self.pending(keep.find_update(self.kit, self.cfg, self.net))
        keep.apply(self.kit, self.cfg, state, log=self.lines.append, run=self.maria.run, check=lambda kit: None)
        self.maria.fail = "DROP DATABASE"
        with self.assertRaises(keep.Stuck) as caught:
            keep.roll_back(self.kit, self.cfg, keep.load_state(self.kit), "x", log=self.lines.append, run=self.maria.run)
        self.assertIn("the database", str(caught.exception))
        state = keep.load_state(self.kit)
        self.assertTrue(state["stuck"] and os.path.exists(state["db"]), "what was saved stays where it is")
        self.assertEqual(read(self.server + "/xi_map"), "old map\n")

    def test_requests_from_the_owner(self):
        self.assertIsNone(keep.take_request(self.kit))
        keep.request(self.kit, "update", retry=True)
        asked = keep.take_request(self.kit)
        self.assertEqual((asked["do"], asked["retry"]), ("update", True))
        self.assertIsNone(keep.take_request(self.kit), "asked once, done once")
        self.put(self.kit, {"logs/" + keep.REQUEST_FILE: "{half"})
        self.assertIsNone(keep.take_request(self.kit))
        self.assertFalse(os.path.exists(os.path.join(self.kit, "logs", keep.REQUEST_FILE)), "a damaged request is thrown away")


@unittest.skipUnless(os.environ.get("WORLD_TEST_MARIADB"), "set WORLD_TEST_MARIADB to a folder laid out like the kit's mariadb folder")
class RealDatabase(unittest.TestCase):
    """The backup and the restore against a real database, started and stopped with the kit's own code."""
    PORT = 3397

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.kit = os.path.join(cls.tmp, "kit")
        cls.mdb = os.path.join(cls.kit, "mariadb")
        shutil.copytree(os.environ["WORLD_TEST_MARIADB"], cls.mdb, symlinks=True)
        with open(os.path.join(cls.mdb, "xiforever-db.json"), "w") as handle:
            json.dump({"root": "rootpw", "xi": "xipw", "port": cls.PORT}, handle)
        cls.cfg = {"mariadb_dir": cls.mdb, "db_name": setup.DB_NAME, "db_user": setup.DB_USER, "db_pass": "xipw", "db_port": cls.PORT}
        setup.init_mariadb(cls.mdb, "rootpw", cls.PORT)
        cls.proc = setup.start_mariadb(cls.mdb, cls.PORT)
        setup.set_root_password(cls.mdb, cls.PORT, "rootpw")
        setup.create_database(cls.mdb, cls.PORT, "rootpw", "xipw")

    @classmethod
    def tearDownClass(cls):
        setup.stop_mariadb(cls.mdb, cls.PORT, "rootpw")
        try:
            cls.proc.wait(timeout=30)
        except Exception:
            cls.proc.kill()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def sql(self, statement):
        return setup.sql(self.mdb, self.PORT, "xi", "xipw", statement, database=setup.DB_NAME)

    def test_what_is_saved_comes_back_and_what_came_later_is_gone(self):
        self.sql("CREATE TABLE `chars` (charid INT PRIMARY KEY, charname VARCHAR(20)); INSERT INTO `chars` VALUES (1, 'Hurami'), (2, 'Kurami');"
                 "CREATE TABLE `gil` (charid INT PRIMARY KEY, amount INT); INSERT INTO `gil` VALUES (1, 500);"
                 "CREATE TRIGGER char_gone BEFORE DELETE ON `chars` FOR EACH ROW DELETE FROM `gil` WHERE charid = OLD.charid;")
        path = keep.backup_now(self.cfg, self.kit, "nightly")
        self.assertGreater(keep.check_backup(path), 500)
        self.sql("UPDATE `gil` SET amount = 1; DELETE FROM `chars` WHERE charid = 2; CREATE TABLE `from_the_update` (x INT);")
        keep.restore(self.cfg, self.kit, path)
        self.assertEqual(self.sql("SELECT charname FROM `chars` ORDER BY charid").split(), ["Hurami", "Kurami"])
        self.assertEqual(self.sql("SELECT amount FROM `gil`").split(), ["500"])
        self.assertEqual(self.sql("SHOW TABLES").split(), ["chars", "gil"])
        self.sql("DELETE FROM `chars` WHERE charid = 1")                         # the trigger came back with the copy
        self.assertEqual(self.sql("SELECT COUNT(*) FROM `gil`").split(), ["0"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
