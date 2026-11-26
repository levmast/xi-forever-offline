"""Offline checks for launcher_thirdparty.py: no network, a stand-in GitHub. Run: python test_thirdparty.py"""
import hashlib, io, json, os, shutil, sys, tempfile, time, unittest, urllib.error, urllib.request, zipfile
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_thirdparty as tp


def zip_of(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


class FakeResponse:
    """A stand-in for an open connection: remembers how much was asked for in one read (a read with no size would mean
    the whole file in memory)."""
    def __init__(self, data, headers=None):
        self.buf, self.reads, self.headers = io.BytesIO(data), [], headers or {}

    def read(self, size=None):
        self.reads.append(size)
        return self.buf.read() if size is None else self.buf.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ThirdPartyTests(unittest.TestCase):
    def setUp(self):
        self.kit, self.ash = tempfile.mkdtemp(), tempfile.mkdtemp()
        shutil.copy(os.path.join(KIT, "thirdparty.json"), self.kit)
        self.items = {i["id"]: i for i in tp.load_manifest(self.kit)}

    def tearDown(self):
        shutil.rmtree(self.kit, ignore_errors=True)
        shutil.rmtree(self.ash, ignore_errors=True)

    def fake(self, release, files):
        def fetch(url, timeout=60):
            if url.startswith(tp.API):
                return json.dumps(release).encode()
            return files[url]
        return fetch

    def test_every_item_is_complete(self):
        for item in self.items.values():
            for key in ("id", "name", "author", "license", "homepage", "source"):
                self.assertIn(key, item, item.get("id"))
            # (items unpacked whole, "unpack": "tree" or "zips" (umu, Proton, XISpeaks), say where with unpack_to instead)
            if item["source"]["type"] not in ("page", "installer", "ollama_model") and not item.get("unpack"):
                self.assertTrue(item.get("files"), item["id"])

    def test_release_with_checksum(self):
        dll = b"MZ fake dll"
        release = {"tag_name": "v9", "assets": [{"name": "XIUIplus.dll", "browser_download_url": "u/dll"},
                                                {"name": "SHA256SUMS.txt", "browser_download_url": "u/sums"}]}
        good = self.fake(release, {"u/dll": dll, "u/sums": (hashlib.sha256(dll).hexdigest() + "  XIUIplus.dll\n").encode()})
        self.assertEqual(tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=good, log=lambda m: None), "v9")
        with open(os.path.join(self.ash, "plugins", "XIUIplus.dll"), "rb") as f:
            self.assertEqual(f.read(), dll)
        bad = self.fake(release, {"u/dll": dll + b"!", "u/sums": (hashlib.sha256(dll).hexdigest() + "  XIUIplus.dll\n").encode()})
        with self.assertRaises(RuntimeError):
            tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=bad, log=lambda m: None)

    def test_archive_keeps_settings_and_backs_up(self):
        os.makedirs(os.path.join(self.ash, "config", "boot"))
        with open(os.path.join(self.ash, "config", "boot", "my.ini"), "w") as f:
            f.write("mine")
        with open(os.path.join(self.ash, "Ashita-cli.exe"), "w") as f:
            f.write("old")
        os.makedirs(os.path.join(self.ash, "config", "ashita"))
        for name, text in (("ashita.offsets.ini", "old offsets"), ("custom.offsets.ini", "my offsets")):
            with open(os.path.join(self.ash, "config", "ashita", name), "w") as f:
                f.write(text)
        data = zip_of({"Ashita-v4beta-x/Ashita-cli.exe": "new", "Ashita-v4beta-x/config/boot/my.ini": "theirs",
                       "Ashita-v4beta-x/addons/fps/fps.lua": "fps",
                       "Ashita-v4beta-x/config/ashita/ashita.offsets.ini": "new offsets",
                       "Ashita-v4beta-x/config/ashita/custom.offsets.ini": "blank"})
        ref = self.items["ashita"]["source"]["ref"]
        url = "https://github.com/AshitaXI/Ashita-v4beta/archive/%s.zip" % ref
        tp.install(self.items["ashita"], self.kit, self.ash, fetch=self.fake({}, {url: data}), log=lambda m: None)
        read = lambda *p: open(os.path.join(self.ash, *p)).read()
        self.assertEqual((read("Ashita-cli.exe"), read("config", "boot", "my.ini"), read("addons", "fps", "fps.lua")), ("new", "mine", "fps"))
        # Ashita's own offsets follow its version (the November 2026 client fix); the player's custom file stays
        self.assertEqual((read("config", "ashita", "ashita.offsets.ini"), read("config", "ashita", "custom.offsets.ini")),
                         ("new offsets", "my offsets"))
        backups = os.listdir(os.path.join(self.kit, "backups", "thirdparty"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(tp.status(self.items["ashita"], self.kit, self.ash), (True, ref))

    def test_model_status_reads_ollama_list(self):
        tp.ollama_models = lambda run=None: ["gemma4:12b", "mistral-nemo:latest"]
        self.assertEqual(tp.status(self.items["aimodel"], self.kit, self.ash), (True, "gemma4:12b"))
        tp.ollama_models = lambda run=None: []
        self.assertEqual(tp.status(self.items["aimodel"], self.kit, self.ash)[0], False)

    def test_nothing_outside_its_folder(self):
        with self.assertRaises(RuntimeError):
            tp.plan({"name": "bad", "files": [["a/", "../../evil/"]]}, ["a/x.lua"])

    def test_page_items_are_not_downloaded(self):
        # (2026-11-25) the Journal is a GitHub release now (Kxteel's 0.4.6); a stand-in page item keeps this checked
        with self.assertRaises(ValueError):
            tp.resolve({"name": "Page item", "homepage": "https://example.com", "source": {"type": "page", "url": "https://example.com"}})
        self.assertEqual(self.items["journal"]["source"]["type"], "github_release")

    # ----- channels: a "beta" item is for players who switched on "Get test builds" -----
    BETA = {"id": "betaaddon", "name": "Beta addon", "author": "a", "license": "l", "homepage": "h", "channel": "beta",
            "into": "ashita", "check": "addons/betaaddon/betaaddon.lua", "files": [["betaaddon/", "addons/betaaddon/"]],
            "source": {"type": "github_release", "repo": "x/betaaddon", "tag": "latest", "asset": "^betaaddon\.zip$"}}

    def with_beta(self, test_builds=None):
        with open(os.path.join(self.kit, "thirdparty.json"), encoding="utf-8-sig") as f:
            data = json.load(f)
        data["items"].append(self.BETA)
        with open(os.path.join(self.kit, "thirdparty.json"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        if test_builds is not None:
            with open(os.path.join(self.kit, "config.json"), "w") as f:
                json.dump({"test_builds": test_builds}, f)
        return [i["id"] for i in tp.load_manifest(self.kit)]

    def test_beta_hidden_by_default(self):
        self.assertNotIn("betaaddon", self.with_beta())
        self.assertNotIn("betaaddon", self.with_beta(False))

    def test_beta_shown_with_test_builds(self):
        self.assertIn("betaaddon", self.with_beta(True))

    def test_beta_stays_listed_once_installed(self):
        self.with_beta(False)
        with open(os.path.join(self.kit, "thirdparty-installed.json"), "w") as f:
            json.dump({"betaaddon": {"version": "v1.0.0-beta.1"}}, f)
        self.assertIn("betaaddon", [i["id"] for i in tp.load_manifest(self.kit)])

    def test_beta_group_needs_a_sign_up(self):
        self.BETA = dict(self.BETA, group="gear-gambits")
        self.assertNotIn("betaaddon", self.with_beta(True))                       # test builds on, no group chosen
        for value, shown in (("gear-gambits", True), ("Vault, Gear-Gambits", True), (["gear-gambits"], True), ("vault", False)):
            with open(os.path.join(self.kit, "config.json"), "w") as f:
                json.dump({"test_builds": True, "beta_groups": value}, f)
            self.assertEqual("betaaddon" in [i["id"] for i in tp.load_manifest(self.kit)], shown, value)
        with open(os.path.join(self.kit, "config.json"), "w") as f:
            json.dump({"test_builds": False, "beta_groups": "gear-gambits"}, f)     # test builds off beats the sign-up
        self.assertNotIn("betaaddon", [i["id"] for i in tp.load_manifest(self.kit)])

    def test_beta_takes_the_newest_prerelease(self):
        releases = [{"tag_name": "v1.0.0-beta.2", "prerelease": True, "assets": [{"name": "betaaddon.zip", "browser_download_url": "u/b2"}]},
                    {"tag_name": "v0.9.0", "assets": [{"name": "betaaddon.zip", "browser_download_url": "u/s"}]}]
        fetch = lambda url, timeout=60: json.dumps(releases).encode()
        self.assertEqual(tp.resolve(self.BETA, fetch)["version"], "v1.0.0-beta.2")
        self.assertEqual(tp.latest_version(self.BETA, fetch), "v1.0.0-beta.2")
        stable = dict(self.BETA, channel="stable")
        one = lambda url, timeout=60: json.dumps(releases[1]).encode()
        self.assertEqual(tp.latest_version(stable, one), "v0.9.0")

    def test_pinned_item_is_never_offered_a_newer_version(self):
        # Chains is pinned to the tested v0.86: asking GitHub for "latest" showed "(newer: ...)" for ever, and
        # Reinstall / update put v0.86 back
        asked = []
        fetch = lambda url, timeout=60: asked.append(url) or b'{"tag_name": "v9.9"}'
        self.assertEqual(self.items["chains"]["source"]["tag"], "v0.86")
        self.assertIsNone(tp.latest_version(self.items["chains"], fetch))
        self.assertEqual(asked, [])
        self.assertEqual(tp.latest_version(self.items["xiuiplus"], fetch), "v9.9")

    def test_damaged_state_is_kept_not_overwritten(self):
        path = tp.state_path(self.kit)
        with open(path, "w") as f:
            f.write('{"server": {"version": "v1"')           # cut off mid-write
        self.assertEqual(tp.load_state(self.kit), {})
        self.assertFalse(os.path.exists(path))
        with open(path + ".bad") as f:
            self.assertIn("server", f.read())

    def test_state_save_leaves_no_temp_file(self):
        tp._save_state(self.kit, {"a": {"version": "1"}})
        self.assertEqual(tp.load_state(self.kit), {"a": {"version": "1"}})
        self.assertFalse(os.path.exists(tp.state_path(self.kit) + ".tmp"))

    def test_missing_checksum_file_is_a_clear_refusal(self):
        release = {"tag_name": "v9", "assets": [{"name": "XIUIplus.dll", "browser_download_url": "u/dll"}]}
        with self.assertRaises(RuntimeError) as caught:
            tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=self.fake(release, {"u/dll": b"MZ"}), log=lambda m: None)
        self.assertIn("SHA256SUMS.txt", str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(self.ash, "plugins", "XIUIplus.dll")))

    def test_downloaded_zip_is_closed_after_install(self):
        # on Windows an open zip cannot be deleted: the downloads folder could not be cleaned up
        url = "https://github.com/AshitaXI/Ashita-v4beta/archive/%s.zip" % self.items["ashita"]["source"]["ref"]
        data = zip_of({"Ashita-v4beta-x/Ashita-cli.exe": "new"})
        tp.install(self.items["ashita"], self.kit, self.ash, fetch=self.fake({}, {url: data}), log=lambda m: None,
                   keep_download=True)                    # (the install deletes its download unless asked to keep it)
        folder = os.path.join(self.kit, "downloads", "ashita")
        for name in os.listdir(folder):
            os.remove(os.path.join(folder, name))          # would raise PermissionError on Windows if still open

    def install_chains(self, files, **kw):
        release = {"tag_name": "v0.86", "assets": [{"name": "Chains-v0.86-Phoenix.zip", "browser_download_url": "u/z"}]}
        fetch = self.fake(release, {"u/z": zip_of(files)})
        tp.install(self.items["chains"], self.kit, self.ash, fetch=fetch, log=lambda m: None, **kw)

    def test_uninstall_removes_what_was_installed_and_keeps_the_rest(self):
        self.install_chains({"chains/chains.lua": "x", "chains/data/a.lua": "y"})
        mine = os.path.join(self.ash, "addons", "chains", "my-notes.txt")
        with open(mine, "w") as f:
            f.write("mine")
        self.assertEqual(tp.uninstall(self.items["chains"], self.kit, self.ash, log=lambda m: None), 2)
        self.assertFalse(os.path.exists(os.path.join(self.ash, "addons", "chains", "chains.lua")))
        self.assertTrue(os.path.exists(mine))                      # not ours: stays
        self.assertNotIn("chains", tp.load_state(self.kit))
        saved = os.listdir(os.path.join(self.kit, "backups", "thirdparty"))
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].startswith("chains-uninstall-"))

    def test_uninstall_leaves_no_empty_folders(self):
        self.install_chains({"chains/chains.lua": "x", "chains/data/a.lua": "y"})
        tp.uninstall(self.items["chains"], self.kit, self.ash, log=lambda m: None)
        self.assertFalse(os.path.exists(os.path.join(self.ash, "addons", "chains")))

    def test_uninstall_refuses_without_a_record_and_for_required_items(self):
        os.makedirs(os.path.join(self.ash, "addons", "chains"))
        with self.assertRaises(RuntimeError):
            tp.uninstall(self.items["chains"], self.kit, self.ash, log=lambda m: None)
        self.assertTrue(os.path.isdir(os.path.join(self.ash, "addons", "chains")))
        with self.assertRaises(RuntimeError):
            tp.uninstall(self.items["ashita"], self.kit, self.ash, log=lambda m: None)

    def test_uninstall_refuses_a_tampered_list(self):
        self.install_chains({"chains/chains.lua": "x"})
        state = tp.load_state(self.kit)
        state["chains"]["files"] = ["../../outside.txt"]
        tp._save_state(self.kit, state)
        with self.assertRaises(RuntimeError):
            tp.uninstall(self.items["chains"], self.kit, self.ash, log=lambda m: None)

    def test_update_keeps_the_list_of_older_files(self):
        # (an update that leaves the old file on disk, remove_old=False, keeps it on the list so uninstall still takes it out)
        self.install_chains({"chains/chains.lua": "x", "chains/old.lua": "y"})
        self.install_chains({"chains/chains.lua": "x2"}, remove_old=False)
        self.assertEqual(sorted(tp.load_state(self.kit)["chains"]["files"]), ["addons/chains/chains.lua", "addons/chains/old.lua"])

    # ---- (v0.3.3 launcher fixes) a download goes to disk a piece at a time, never whole into memory ----
    def with_connection(self, answers):
        """tp._open_url answers {url: bytes or an exception}; returns the list of FakeResponses handed out."""
        handed, real = [], tp._open_url

        def fake(url, timeout=60, headers=None):
            answer = answers[url]
            if isinstance(answer, BaseException):
                raise answer
            response = FakeResponse(answer)
            handed.append(response)
            return response
        tp._open_url = fake
        self.addCleanup(setattr, tp, "_open_url", real)
        return handed

    def test_download_is_read_in_pieces_not_whole(self):
        data = os.urandom(3 * (1 << 20) + 17)
        handed = self.with_connection({"u/big": data})
        found = {"url": "u/big", "name": "big.zip", "sha256": hashlib.sha256(data).hexdigest()}
        path = tp.download({"id": "big", "name": "Big"}, self.kit, found, tp._get)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), data)
        self.assertNotIn(None, handed[0].reads)                       # never "read everything"
        self.assertLessEqual(max(r for r in handed[0].reads), 1 << 20)
        self.assertGreaterEqual(len(handed[0].reads), 4)
        self.assertEqual(found["sha256_actual"], hashlib.sha256(data).hexdigest())
        self.assertFalse(os.path.exists(path + ".part"))

    def test_streamed_download_that_does_not_match_leaves_nothing(self):
        self.with_connection({"u/x": b"tampered"})
        found = {"url": "u/x", "name": "x.zip", "sha256": hashlib.sha256(b"the real one").hexdigest()}
        with self.assertRaises(RuntimeError) as caught:
            tp.download({"id": "x", "name": "Xthing"}, self.kit, found, tp._get)
        self.assertIn("does not match its published checksum", str(caught.exception))
        self.assertEqual(os.listdir(os.path.join(self.kit, "downloads", "x")), [])      # no file, no .part

    def test_streamed_download_that_breaks_half_way_leaves_nothing(self):
        class Breaks(FakeResponse):
            def read(self, size=None):
                data = super().read(size)
                if len(self.reads) > 1:
                    raise OSError("connection reset")
                return data
        real = tp._open_url
        tp._open_url = lambda url, timeout=60, headers=None: Breaks(b"y" * 5000)
        self.addCleanup(setattr, tp, "_open_url", real)
        with self.assertRaises(OSError):
            tp.stream_to_file("u/y", os.path.join(self.kit, "y.zip"), chunk=1000)
        self.assertEqual(os.listdir(self.kit).count("y.zip"), 0)
        self.assertEqual(os.listdir(self.kit).count("y.zip.part"), 0)

    # ---- (v0.3.3 launcher fixes) downloads/ is cleaned up ----
    def release_for(self, dll):
        release = {"tag_name": "v9", "assets": [{"name": "XIUIplus.dll", "browser_download_url": "u/dll"},
                                                {"name": "SHA256SUMS.txt", "browser_download_url": "u/sums"}]}
        return release, {"u/dll": dll, "u/sums": (hashlib.sha256(dll).hexdigest() + "  XIUIplus.dll\n").encode()}

    def test_download_is_deleted_after_a_good_install(self):
        release, files = self.release_for(b"MZ fake dll")
        tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=self.fake(release, files), log=lambda m: None)
        self.assertTrue(os.path.exists(os.path.join(self.ash, "plugins", "XIUIplus.dll")))
        self.assertFalse(os.path.exists(os.path.join(self.kit, "downloads", "xiuiplus")))

    def test_download_is_kept_when_asked(self):
        release, files = self.release_for(b"MZ fake dll")
        tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=self.fake(release, files), log=lambda m: None, keep_download=True)
        self.assertTrue(os.path.exists(os.path.join(self.kit, "downloads", "xiuiplus", "XIUIplus.dll")))

    def test_nothing_is_left_after_a_refused_install(self):
        release, files = self.release_for(b"MZ fake dll")
        files["u/dll"] = b"changed"
        with self.assertRaises(RuntimeError):
            tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=self.fake(release, files), log=lambda m: None)
        self.assertFalse(os.path.exists(os.path.join(self.kit, "downloads", "xiuiplus")))

    @unittest.skipUnless(os.name == "nt", "a Windows installer is started with os.startfile")
    def test_an_installer_that_is_still_open_keeps_its_file(self):
        item = {"id": "setup", "name": "Setup", "source": {"type": "installer", "url": "https://example.test/setup.exe"},
                "into": "kit"}
        opened = []
        os.startfile = lambda path: opened.append(path)        # (only on Windows, so only here)
        try:
            tp.install(item, self.kit, self.ash, fetch=lambda url, timeout=60: b"MZ", log=lambda m: None)
        finally:
            del os.startfile
        self.assertEqual(len(opened), 1)
        self.assertTrue(os.path.exists(opened[0]))

    def test_a_quiet_installer_is_deleted_after_it_ran(self):
        item = {"id": "quiet", "name": "Quiet", "source": {"type": "installer", "url": "https://example.test/q.exe", "wait": True},
                "into": "kit"}
        ran = []
        run = lambda cmd: ran.append(cmd) or type("R", (), {"returncode": 0})()
        tp.install(item, self.kit, self.ash, fetch=lambda url, timeout=60: b"MZ", log=lambda m: None, run=run)
        self.assertEqual(len(ran), 1)
        self.assertFalse(os.path.exists(os.path.join(self.kit, "downloads", "quiet")))

    def test_old_leftovers_are_pruned_and_new_ones_and_updates_stay(self):
        base = os.path.join(self.kit, "downloads")
        now = time.time()
        for name, age in (("old", 30), ("recent", 1), ("updates", 90)):
            os.makedirs(os.path.join(base, name))
            path = os.path.join(base, name, "f.bin")
            with open(path, "wb") as handle:
                handle.write(b"x" * 2048)
            os.utime(path, (now - age * 86400, now - age * 86400))
        said = []
        freed = tp.prune_downloads(self.kit, days=7, log=said.append, now=now)
        self.assertEqual(freed, 2048)
        self.assertEqual(sorted(os.listdir(base)), ["recent", "updates"])
        self.assertTrue(said)
        self.assertEqual(tp.prune_downloads(self.kit, days=7, log=said.append, now=now), 0)

    def test_clean_download_never_leaves_the_downloads_folder(self):
        outside = os.path.join(self.kit, "keepme")
        os.makedirs(outside)
        os.makedirs(os.path.join(self.kit, "downloads"))
        self.assertEqual(tp.clean_download(self.kit, "../keepme"), 0)
        self.assertEqual(tp.clean_download(self.kit, ""), 0)
        self.assertTrue(os.path.isdir(outside))

    # ---- (v0.3.3 launcher fixes) a checksum for every kind of download there can be one for ----
    def test_github_own_checksum_is_used_when_the_author_lists_none(self):
        dll = b"MZ the real dll"
        release = {"tag_name": "v9", "assets": [{"name": "XIUIplus.dll", "browser_download_url": "u/dll",
                                                "digest": "sha256:" + hashlib.sha256(dll).hexdigest()}]}
        item = dict(self.items["xiuiplus"], source=dict(self.items["xiuiplus"]["source"], sha256sums=None))
        self.assertEqual(tp.resolve(item, self.fake(release, {}))["sha256"], hashlib.sha256(dll).hexdigest())
        tp.install(item, self.kit, self.ash, fetch=self.fake(release, {"u/dll": dll}), log=lambda m: None)
        with self.assertRaises(RuntimeError) as caught:
            tp.install(item, self.kit, self.ash, fetch=self.fake(release, {"u/dll": dll + b"!"}), log=lambda m: None)
        self.assertIn("does not match its published checksum", str(caught.exception))

    def test_checksums_that_disagree_refuse_the_install(self):
        dll = b"MZ dll"
        release = {"tag_name": "v9", "assets": [{"name": "XIUIplus.dll", "browser_download_url": "u/dll", "digest": "sha256:" + "0" * 64},
                                                {"name": "SHA256SUMS.txt", "browser_download_url": "u/sums"}]}
        files = {"u/dll": dll, "u/sums": (hashlib.sha256(dll).hexdigest() + "  XIUIplus.dll\n").encode()}
        with self.assertRaises(RuntimeError) as caught:
            tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=self.fake(release, files), log=lambda m: None)
        self.assertIn("do not agree", str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(self.ash, "plugins", "XIUIplus.dll")))

    def test_a_pin_in_thirdparty_json_is_checked_for_archives_and_urls(self):
        data = zip_of({"x-main/addons/zz/zz.lua": "ok"})
        archive = {"id": "zz", "name": "ZZ", "into": "ashita", "files": [["*/addons/", "addons/"]], "check": "addons/zz/zz.lua",
                   "source": {"type": "github_archive", "repo": "a/b", "ref": "main", "sha256": hashlib.sha256(data).hexdigest().upper()}}
        url = "https://github.com/a/b/archive/main.zip"
        self.assertEqual(tp.install(archive, self.kit, self.ash, fetch=self.fake({}, {url: data}), log=lambda m: None), "main")
        with self.assertRaises(RuntimeError):
            tp.install(archive, self.kit, self.ash, fetch=self.fake({}, {url: data + b"x"}), log=lambda m: None)
        pinned_url = {"id": "uu", "name": "UU", "into": "kit", "files": [["uu.bin", "uu.bin"]],
                      "source": {"type": "url", "url": "https://example.test/uu.bin", "sha256": hashlib.sha256(b"abc").hexdigest()}}
        with self.assertRaises(RuntimeError):
            tp.install(pinned_url, self.kit, self.ash, fetch=lambda u, timeout=60: b"abd", log=lambda m: None)
        tp.install(pinned_url, self.kit, self.ash, fetch=lambda u, timeout=60: b"abc", log=lambda m: None)

    def test_an_unlisted_download_says_so_and_records_its_checksum(self):
        data = zip_of({"x-main/addons/zz/zz.lua": "ok"})
        archive = {"id": "zz", "name": "ZZ", "into": "ashita", "files": [["*/addons/", "addons/"]],
                   "source": {"type": "github_archive", "repo": "a/b", "ref": "main"}}
        said = []
        tp.install(archive, self.kit, self.ash, fetch=self.fake({}, {"https://github.com/a/b/archive/main.zip": data}), log=said.append)
        self.assertTrue(any("publishes no checksum" in line for line in said))
        self.assertEqual(tp.load_state(self.kit)["zz"]["sha256"], hashlib.sha256(data).hexdigest())
        # one that has a checksum says nothing of the kind
        release, files = self.release_for(b"MZ fake dll")
        said.clear()
        tp.install(self.items["xiuiplus"], self.kit, self.ash, fetch=self.fake(release, files), log=said.append)
        self.assertFalse(any("publishes no checksum" in line for line in said))

    def test_manifest_names_microsoft_as_the_signer_of_the_runtimes(self):
        for key in ("vcredist", "vcredist86"):
            self.assertEqual(self.items[key]["source"].get("signer"), "Microsoft Corporation")

    def test_installer_signature_is_checked_before_it_is_started(self):
        item = {"id": "setup", "name": "Setup", "into": "kit",
                "source": {"type": "installer", "url": "https://example.test/s.exe", "wait": True, "signer": "Microsoft Corporation"}}
        ran, real = [], tp._signature_of
        run = lambda cmd: ran.append(cmd) or type("R", (), {"returncode": 0})()
        fetch = lambda url, timeout=60: b"MZ"
        self.addCleanup(setattr, tp, "_signature_of", real)
        tp._signature_of = lambda path: ("Valid", "CN=Microsoft Corporation, O=Microsoft Corporation")
        tp.install(item, self.kit, self.ash, fetch=fetch, log=lambda m: None, run=run)
        self.assertEqual(len(ran), 1)
        for answer in (("Valid", "CN=Someone Else"), ("NotSigned", ""), ("HashMismatch", "CN=Microsoft Corporation")):
            tp._signature_of = lambda path, answer=answer: answer
            with self.assertRaises(RuntimeError) as caught:
                tp.install(item, self.kit, self.ash, fetch=fetch, log=lambda m: None, run=run)
            self.assertIn("not signed by Microsoft Corporation", str(caught.exception))
        self.assertEqual(len(ran), 1)                                   # none of the three was started
        said = []
        tp._signature_of = lambda path: None                            # Windows could not be asked: goes ahead, says so
        tp.install(item, self.kit, self.ash, fetch=fetch, log=said.append, run=run)
        self.assertEqual(len(ran), 2)
        self.assertTrue(any("could not ask Windows" in line for line in said))

    # ---- (v0.3.3 launcher fixes) GitHub's request limit is said out loud ----
    def http_error(self, code, headers):
        return urllib.error.HTTPError("https://api.github.com/repos/x/y/releases/latest", code, "x", headers, io.BytesIO(b"{}"))

    def opening(self, error):
        """urllib's urlopen answers with `error` (raised) for the length of the test."""
        real = urllib.request.urlopen

        def fail(*args, **kwargs):
            raise error
        urllib.request.urlopen = fail
        self.addCleanup(setattr, urllib.request, "urlopen", real)

    def test_github_limit_is_reported_with_the_time_it_ends(self):
        reset = int(time.time()) + 1500
        self.opening(self.http_error(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}))
        with self.assertRaises(tp.RateLimited) as caught:
            tp._get("https://api.github.com/repos/x/y/releases/latest")
        self.assertIn("limiting this connection", str(caught.exception))
        self.assertIn(time.strftime("%H:%M", time.localtime(reset)), str(caught.exception))
        self.opening(self.http_error(429, {"Retry-After": "120"}))
        with self.assertRaises(tp.RateLimited):
            tp._get("https://api.github.com/repos/x/y/releases/latest")

    def test_other_http_errors_stay_what_they_are(self):
        for code, headers in ((404, {}), (403, {"X-RateLimit-Remaining": "17"}), (500, {})):
            self.opening(self.http_error(code, headers))
            with self.assertRaises(urllib.error.HTTPError):
                tp._get("https://api.github.com/repos/x/y/releases/latest")

    def test_latest_version_lets_the_limit_through_but_still_hides_other_trouble(self):
        item = self.items["xiuiplus"]

        def limited(url, timeout=60):
            raise tp.RateLimited("limit")

        def broken(url, timeout=60):
            raise OSError("no network")
        with self.assertRaises(tp.RateLimited):
            tp.latest_version(item, limited)
        self.assertIsNone(tp.latest_version(item, broken))
        with self.assertRaises(OSError):
            tp.latest_version(item, broken, strict=True)

    def test_check_stops_and_says_why_when_github_limits_it(self):
        items = [i for i in tp.load_manifest(self.kit) if i["source"]["type"] == "github_release" and i["source"].get("tag") == "latest"]
        self.assertGreaterEqual(len(items), 2)
        versions = {i["id"]: "v1" for i in items}
        asked = []

        def fetch(url, timeout=60):
            asked.append(url)
            raise tp.RateLimited("GitHub is limiting this connection for a while.")
        newer, problems = tp.check_updates(items, versions, fetch)
        self.assertEqual(newer, {})
        self.assertEqual(len(asked), 1)                                    # it did not keep knocking
        self.assertEqual(len(problems), 1)
        self.assertIn("limiting this connection", problems[0])
        self.assertIn("The rest were not checked", problems[0])

    def test_check_lists_what_went_wrong_per_item_and_skips_what_is_not_installed(self):
        items = [i for i in tp.load_manifest(self.kit) if i["source"]["type"] == "github_release" and i["source"].get("tag") == "latest"]
        first, second = items[0], items[1]
        asked = []

        def fetch(url, timeout=60):
            asked.append(url)
            if first["source"]["repo"] in url:
                raise OSError("no network")
            return json.dumps({"tag_name": "v9"}).encode()
        newer, problems = tp.check_updates(items, {first["id"]: "v1", second["id"]: "v1"}, fetch)
        self.assertEqual(newer, {second["id"]: "v9"})
        self.assertEqual(len(problems), 1)
        self.assertIn(first["name"], problems[0])
        self.assertEqual(len(asked), 2)                                    # only the two installed items were asked about

    def test_one_answer_is_asked_for_once_per_repository(self):
        item = self.items["xiuiplus"]
        twin = dict(item, id="twin", name="Twin")
        asked = []

        def fetch(url, timeout=60):
            asked.append(url)
            return json.dumps({"tag_name": "v9"}).encode()
        newer, problems = tp.check_updates([item, twin], {"xiuiplus": "v1", "twin": "v1"}, fetch)
        self.assertEqual((sorted(newer), problems, len(asked)), (["twin", "xiuiplus"], [], 1))

    def test_the_downloads_page_uses_the_checker_and_shows_its_problems(self):
        with open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8") as handle:
            source = handle.read()
        body = source[source.index("def check_download_updates"):source.index("def add_note")]
        self.assertIn("tp.check_downloads(", body)
        self.assertIn("for line in problems", body)
        self.assertIn("messagebox.showinfo", body)

    # ---- (v0.3.3 launcher fixes) versions are compared as versions, not with "is different" ----
    def test_a_newer_release_is_newer_and_an_older_one_is_not(self):
        newer = [("v1.10", "v1.9"), ("v0.86", "v0.85"), ("v2.0.0", "v1.99.9"), ("1.4.4", "1.4.3"), ("GE-Proton11-12", "GE-Proton11-11"),
                 ("v1.0.0", "v1.0.0-beta.2"), ("v1.0.0-rc1", "v1.0.0-beta.9"), ("v1.0.0-beta.10", "v1.0.0-beta.2"),
                 ("v1.0.1", "v1.0"), ("v1.4.3-1", "v1.4.3")]
        for tag, have in newer:
            self.assertTrue(tp.is_newer(tag, have), f"{tag} should be newer than {have}")
            self.assertFalse(tp.is_newer(have, tag), f"{have} should not be newer than {tag}")

    def test_the_same_version_in_other_spellings_is_not_newer(self):
        for tag, have in (("v1.0", "v1.0.0"), ("1.4.4", "v1.4.4"), ("v0.86", "v0.86"), ("v1.0.0-beta.2", "v1.0.0-beta.2")):
            self.assertFalse(tp.is_newer(tag, have), f"{tag} vs {have}")
            self.assertFalse(tp.is_newer(have, tag), f"{have} vs {tag}")

    def test_a_downgrade_is_not_offered_as_an_update(self):
        # the old comparison was "is it different": a release page that rolled back, or an author's older tag, showed "(newer: ...)"
        self.assertFalse(tp.is_newer("v1.8.4", "v1.8.5"))
        self.assertFalse(tp.is_newer("v2.20", "v2.21"))

    def test_words_that_only_look_like_a_pre_release_marker_are_not_one(self):
        self.assertEqual(tp.parse_version("Source-v2.1")[1], (9, 0))
        self.assertEqual(tp.parse_version("Chains-v0.86-Phoenix")[0], (0, 86))
        self.assertEqual(tp.parse_version("v1.0.0-beta.2"), ((1,), (1, 2)))

    def test_without_numbers_it_stays_as_it_was(self):
        # a branch name, or an install this launcher did not record: any different tag still counts as newer (and the same one not)
        self.assertTrue(tp.is_newer("v2", "installed"))
        self.assertTrue(tp.is_newer("v2", ""))
        self.assertFalse(tp.is_newer("main", "main"))
        self.assertFalse(tp.is_newer("", "v1"))
        self.assertFalse(tp.is_newer(None, "v1"))

    def test_the_check_offers_only_what_is_really_newer(self):
        a = {"id": "aa", "name": "AA", "source": {"type": "github_release", "repo": "x/aa", "tag": "latest", "asset": "a"}}
        b = {"id": "bb", "name": "BB", "source": {"type": "github_release", "repo": "x/bb", "tag": "latest", "asset": "b"}}
        items = [a, b]
        tags = {a["source"]["repo"]: "v1.8.4", b["source"]["repo"]: "v1.10.0"}

        def fetch(url, timeout=60):
            repo = next(r for r in tags if r in url)
            return json.dumps({"tag_name": tags[repo]}).encode()
        newer, problems = tp.check_updates(items, {a["id"]: "v1.8.5", b["id"]: "v1.9.0"}, fetch)
        self.assertEqual((newer, problems), ({b["id"]: "v1.10.0"}, []))

    def test_both_download_lists_use_the_same_comparison(self):
        for name, needle in (("launcher_gui.pyw", "tp.is_newer(newer[item[\"id\"]], version)"),
                             ("launcher_pages.py", "G.tp.is_newer(newest, version)")):
            with open(os.path.join(KIT, name), encoding="utf-8") as handle:
                self.assertIn(needle, handle.read(), name)

    # ---- (v0.3.3 launcher fixes) the downloads are checked for newer versions when the launcher starts ----
    def two_items(self):
        a = {"id": "aa", "name": "AA", "source": {"type": "github_release", "repo": "x/aa", "tag": "latest", "asset": "a"}}
        b = {"id": "bb", "name": "BB", "source": {"type": "github_release", "repo": "x/bb", "tag": "latest", "asset": "b"}}
        return [a, b]

    def counting_fetch(self, answers):
        asked = []

        def fetch(url, timeout=60):
            asked.append(url)
            return json.dumps({"tag_name": answers[next(r for r in answers if r in url)]}).encode()
        return fetch, asked

    def test_an_item_pinned_to_a_tested_version_is_never_offered_a_newer_one(self):
        asked = []
        fetch = lambda url, timeout=60: asked.append(url) or b'{"tag_name": "v9.9"}'
        self.assertEqual(self.items["chains"]["source"]["tag"], "v0.86")
        self.assertIsNone(tp.latest_version(self.items["chains"], fetch))
        self.assertEqual(asked, [])
        self.assertEqual(tp.latest_version(self.items["xiuiplus"], fetch), "v9.9")
        del asked[:]
        newer, problems = tp.check_updates([self.items["chains"]], {"chains": "v0.86"}, fetch)
        self.assertEqual((newer, problems, asked), ({}, [], []))

    def test_start_check_asks_github_at_most_every_six_hours(self):
        items = self.two_items()
        fetch, asked = self.counting_fetch({"x/aa": "v2", "x/bb": "v2"})
        versions = {"aa": "v1", "bb": "v1"}
        now = 1_000_000.0
        newer, problems, did = tp.check_downloads(self.kit, items, versions, fetch, now=now)
        self.assertEqual((newer, problems, did, len(asked)), ({"aa": "v2", "bb": "v2"}, [], True, 2))
        # ten more starts within the six hours: no new requests, the same answer
        for start in range(10):
            newer, problems, did = tp.check_downloads(self.kit, items, versions, fetch, now=now + 60 * (start + 1))
            self.assertEqual((newer, did, len(asked)), ({"aa": "v2", "bb": "v2"}, False, 2))
        # an item updated in between is no longer listed
        newer, _problems, _did = tp.check_downloads(self.kit, items, {"aa": "v2", "bb": "v1"}, fetch, now=now + 3600)
        self.assertEqual(newer, {"bb": "v2"})
        # the button always asks; six hours later the start asks again
        self.assertTrue(tp.check_downloads(self.kit, items, versions, fetch, force=True, now=now + 100)[2])
        self.assertTrue(tp.check_downloads(self.kit, items, versions, fetch, now=now + 100 + 6 * 3600 + 1)[2])

    def test_start_check_survives_a_damaged_answer_file(self):
        items = self.two_items()
        fetch, asked = self.counting_fetch({"x/aa": "v2", "x/bb": "v1"})
        for text in ("{not json", "[]", '{"at": "yesterday", "newer": 5}'):
            with open(os.path.join(self.kit, tp.CHECK_FILE), "w") as handle:
                handle.write(text)
            newer, problems, did = tp.check_downloads(self.kit, items, {"aa": "v1", "bb": "v1"}, fetch, now=5000.0)
            self.assertEqual((newer, problems, did), ({"aa": "v2"}, [], True), text)

    def test_start_check_that_hit_the_limit_does_not_knock_again_for_hours(self):
        items = self.two_items()
        calls = []

        def fetch(url, timeout=60):
            calls.append(url)
            raise tp.RateLimited("GitHub is limiting this connection for a while.")
        newer, problems, did = tp.check_downloads(self.kit, items, {"aa": "v1", "bb": "v1"}, fetch, now=1000.0)
        self.assertEqual((newer, did, len(calls)), ({}, True, 1))
        self.assertIn("limiting this connection", problems[0])
        tp.check_downloads(self.kit, items, {"aa": "v1", "bb": "v1"}, fetch, now=1000.0 + 600)
        self.assertEqual(len(calls), 1)

    def test_the_start_check_is_wired_to_the_launcher_and_can_be_switched_off(self):
        with open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8") as handle:
            source = handle.read()
        body = source[source.index("def check_downloads_quietly"):source.index("def add_note")]
        self.assertIn('self.cfg.get("check_downloads_on_start", True)', body)       # on unless config.json says false
        self.assertIn('self.cfg.get("mariadb_dir")', body)                          # a player install, like the launcher's own check
        self.assertIn("self.after(5000, self.check_downloads_quietly)", source)
        self.assertNotIn("messagebox", body.split("def check_downloads_quietly")[1])
        quiet = source[source.index("def check_download_updates"):source.index("def check_downloads_quietly")]
        self.assertIn("if quiet:", quiet)
        self.assertIn("force=not quiet", quiet)

    # ---- (v0.3.3 launcher fixes) an update takes out the files the old version had and the new one does not ----
    def release_chains(self, tag, files):
        release = {"tag_name": tag, "assets": [{"name": "Chains-v0.86-Phoenix.zip", "browser_download_url": "u/z"}]}
        return self.fake(release, {"u/z": zip_of(files)})

    def test_an_update_removes_files_the_new_version_dropped_and_backs_them_up(self):
        item = self.items["chains"]
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v1", {"chains/chains.lua": "one", "chains/old.lua": "gone soon",
                                                                             "chains/data/a.lua": "a"}), log=lambda m: None)
        base = os.path.join(self.ash, "addons", "chains")
        self.assertTrue(os.path.exists(os.path.join(base, "old.lua")))
        said = []
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v2", {"chains/chains.lua": "two", "chains/data/a.lua": "a2"}),
                   log=said.append)
        self.assertEqual(open(os.path.join(base, "chains.lua")).read(), "two")
        self.assertFalse(os.path.exists(os.path.join(base, "old.lua")))                 # dropped by v2: gone
        self.assertEqual(sorted(tp.load_state(self.kit)["chains"]["files"]), ["addons/chains/chains.lua", "addons/chains/data/a.lua"])
        self.assertTrue(any("1 file(s) the old version had" in line for line in said))
        saved = [os.path.join(top, n) for top, _d, names in os.walk(os.path.join(self.kit, "backups", "thirdparty")) for n in names
                 if n == "old.lua"]
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0].replace("\\", "/").count("-old/") == 1)
        self.assertEqual(open(saved[0]).read(), "gone soon")

    def test_the_first_update_after_the_list_was_not_kept_removes_nothing(self):
        item = self.items["chains"]
        base = os.path.join(self.ash, "addons", "chains")
        os.makedirs(base)
        open(os.path.join(base, "mine.lua"), "w").write("the player's own file")
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v1", {"chains/chains.lua": "one"}), log=lambda m: None)
        self.assertEqual(open(os.path.join(base, "mine.lua")).read(), "the player's own file")

    def test_a_file_another_download_also_put_there_is_not_removed(self):
        item = self.items["chains"]
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v1", {"chains/chains.lua": "one", "chains/shared.lua": "s"}),
                   log=lambda m: None)
        state = tp.load_state(self.kit)
        state["other"] = {"version": "1", "files": ["addons/chains/shared.lua"]}
        tp._save_state(self.kit, state)
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v2", {"chains/chains.lua": "two"}), log=lambda m: None)
        self.assertTrue(os.path.exists(os.path.join(self.ash, "addons", "chains", "shared.lua")))

    def test_settings_folders_and_other_folders_are_never_swept(self):
        item = dict(self.items["chains"], keep=["addons/chains/settings/"])
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v1", {"chains/chains.lua": "one", "chains/settings/s.xml": "x"}),
                   log=lambda m: None)
        state = tp.load_state(self.kit)
        state["chains"]["files"] += ["addons/chains/settings/s.xml", "../escape.txt"]
        tp._save_state(self.kit, state)
        open(os.path.join(os.path.dirname(self.ash), "escape.txt"), "w").write("outside")
        self.addCleanup(os.remove, os.path.join(os.path.dirname(self.ash), "escape.txt"))
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v2", {"chains/chains.lua": "two"}), log=lambda m: None)
        self.assertTrue(os.path.exists(os.path.join(self.ash, "addons", "chains", "settings", "s.xml")))      # a kept folder
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(self.ash), "escape.txt")))             # outside its folder

    def test_it_can_be_switched_off(self):
        item = self.items["chains"]
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v1", {"chains/chains.lua": "one", "chains/old.lua": "x"}),
                   log=lambda m: None)
        tp.install(item, self.kit, self.ash, fetch=self.release_chains("v2", {"chains/chains.lua": "two"}), log=lambda m: None,
                   remove_old=False)
        self.assertTrue(os.path.exists(os.path.join(self.ash, "addons", "chains", "old.lua")))
        self.assertIn("addons/chains/old.lua", tp.load_state(self.kit)["chains"]["files"])        # still listed for uninstall
        with open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8") as handle:
            self.assertIn('remove_old=bool(self.cfg.get("remove_old_files", True))', handle.read())


if __name__ == "__main__":
    unittest.main(verbosity=1)
