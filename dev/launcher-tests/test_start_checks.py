"""Offline checks for what PLAY looks at before and after the game starts (2026-11-22): the Visual C++ runtimes, a
half-made login certificate, Windows' "blocked this file", and why a game that closed at once closed.
Run: python test_start_checks.py"""
import os, shutil, struct, sys, tempfile, time, unittest
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
os.environ["XIFO_TEST_PLATFORM"] = "windows"
import launcher_core as core
import launcher_thirdparty as tp


def dll_bytes(major, minor, build, revision=0):
    """Enough of a DLL for file_version: filler, then the fixed version block."""
    block = struct.pack("<IIII", 0xFEEF04BD, 0x00010000, (major << 16) | minor, (build << 16) | revision)
    return b"MZ" + b"\0" * 300 + block + b"\0" * 64


class Result:
    def __init__(self, code=0):
        self.returncode = code


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        self.dll = os.path.join(self.kit, "sys", "msvcp140.dll")
        os.makedirs(os.path.dirname(self.dll))
        self.item = {"id": "vcredist86", "name": "Microsoft Visual C++ runtime (x86)", "into": "kit",
                     "source": {"type": "installer", "url": "https://aka.ms/vc14/vc_redist.x86.exe",
                                "args": ["/install", "/passive", "/norestart"], "wait": True},
                     "check_system": self.dll, "min_version": "14.40"}
        self.said = []

    def tearDown(self):
        shutil.rmtree(self.kit, ignore_errors=True)

    def put(self, *version):
        with open(self.dll, "wb") as handle:
            handle.write(dll_bytes(*version))

    def test_file_version(self):
        self.put(14, 29, 30156)
        self.assertEqual(tp.file_version(self.dll), (14, 29, 30156, 0))
        self.assertIsNone(tp.file_version(os.path.join(self.kit, "nothing.dll")))
        with open(self.dll, "wb") as handle:
            handle.write(b"not a program")
        self.assertIsNone(tp.file_version(self.dll))

    def test_status_missing_old_and_new(self):
        self.assertEqual(tp.system_file_status(self.item), (False, "", "missing"))
        self.put(14, 29, 30156)                      # Leyna's: xiloader stopped inside it
        self.assertEqual(tp.system_file_status(self.item), (False, "14.29.30156", "old"))
        self.assertEqual(tp.status(self.item, self.kit, None), (False, ""))
        self.put(14, 40, 33810)
        self.assertEqual(tp.system_file_status(self.item), (True, "14.40.33810", ""))
        self.put(14, 51, 36231)
        self.assertEqual(tp.status(self.item, self.kit, None), (True, "14.51.36231"))

    def test_unreadable_version_counts_as_fine(self):
        with open(self.dll, "wb") as handle:
            handle.write(b"no version block here")
        self.assertEqual(tp.system_file_status(self.item), (True, "installed", ""))

    def test_no_min_version_is_the_old_check(self):
        item = dict(self.item)
        del item["min_version"]
        self.assertFalse(tp.system_file_status(item)[0])
        self.put(14, 0, 1)
        self.assertEqual(tp.system_file_status(item), (True, "installed", ""))

    def test_old_runtime_is_installed(self):
        self.put(14, 29, 30156)
        ran = []

        def run(cmd):
            ran.append(cmd)
            self.put(14, 51, 36231)                  # what the installer does
            return Result(0)

        out = tp.ensure_system_runtimes(self.kit, None, fetch=lambda url, timeout=60: b"installer", log=self.said.append,
                                        run=run, items=[self.item])
        self.assertEqual(out, [("vcredist86", "installed", "14.51.36231")])
        self.assertEqual(ran[0][1:], ["/install", "/passive", "/norestart"])
        self.assertTrue(ran[0][0].endswith("vc_redist.x86.exe"))
        self.assertIn("14.29.30156 is too old", self.said[0])

    def test_current_runtime_is_left_alone(self):
        self.put(14, 44, 35211)
        out = tp.ensure_system_runtimes(self.kit, None, fetch=self.fail, log=self.said.append, run=self.fail, items=[self.item])
        self.assertEqual((out, self.said), ([], []))

    def test_failed_install_does_not_stop_play(self):
        def no_internet(url, timeout=60):
            raise OSError("no internet")

        out = tp.ensure_system_runtimes(self.kit, None, fetch=no_internet, log=self.said.append, run=self.fail, items=[self.item])
        self.assertEqual(out[0][:2], ("vcredist86", "failed"))
        self.assertIn("https://aka.ms/vc14/vc_redist.x86.exe", self.said[-1])
        # declined or failed installer: still the old file afterwards
        self.put(14, 29, 30156)
        out = tp.ensure_system_runtimes(self.kit, None, fetch=lambda url, timeout=60: b"x", log=self.said.append,
                                        run=lambda cmd: Result(1602), items=[self.item])
        self.assertEqual(out[0][:2], ("vcredist86", "failed"))

    def test_the_kit_lists_both_runtimes(self):
        items = {i["id"]: i for i in tp.load_manifest(KIT)}
        for iid, folder, exe in (("vcredist", "System32", "vc_redist.x64.exe"), ("vcredist86", "SysWOW64", "vc_redist.x86.exe")):
            item = items[iid]
            self.assertEqual(item["min_version"], "14.40")
            self.assertIn(folder + "\\msvcp140.dll", item["check_system"])
            self.assertEqual(item["source"]["url"], "https://aka.ms/vc14/" + exe)
            self.assertTrue(item["source"]["wait"])


class StartTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def touch(self, name, text="x"):
        with open(os.path.join(self.dir, name), "w") as handle:
            handle.write(text)

    def test_key_without_certificate_is_removed(self):
        self.assertFalse(core.clear_half_made_certificate(self.dir))        # nothing there: first start
        self.touch("login.key")
        self.touch("login.cert.tmp")
        self.assertTrue(core.clear_half_made_certificate(self.dir))
        self.assertEqual(os.listdir(self.dir), [])

    def test_certificate_without_key_is_removed(self):
        self.touch("login.cert")                                             # (Lion) the key renamed away by hand
        self.touch("login.key.bak")
        self.assertTrue(core.clear_half_made_certificate(self.dir))
        self.assertEqual(os.listdir(self.dir), ["login.key.bak"])

    def test_a_complete_pair_is_kept(self):
        self.touch("login.key")
        self.touch("login.cert")
        self.assertFalse(core.clear_half_made_certificate(self.dir))
        self.assertEqual(sorted(os.listdir(self.dir)), ["login.cert", "login.key"])

    def test_blocked_program_is_explained(self):
        problem = OSError(22, "An Application Control policy has blocked this file")
        problem.winerror = 4551
        self.assertIn("Smart App Control", core.explain_start_error(problem))
        self.assertIn("Smart App Control", core.explain_start_error(RuntimeError("[WinError 4551] An Application Control policy has blocked this file")))
        self.assertEqual(core.explain_start_error(RuntimeError("xi_map stopped")), "xi_map stopped")
        blocked = core.explain_start_error(RuntimeError("xi_profile stopped unexpectedly.\nbind: An attempt was made to "
                                                        "access a socket in a way forbidden by its access permissions."))
        self.assertTrue(blocked.startswith("xi_profile stopped unexpectedly."))
        self.assertIn("net stop winnat", blocked)
        self.assertIn("another program", core.explain_start_error(RuntimeError("bind: Only one usage of each socket address")))
        # (2026-11-22, Telunian) Ashita could not attach to the game loader: say that it is security software
        stopped = core.explain_start_error(RuntimeError("The game loader never started.\n\nAshita said:\n[E] Failed to install "
                                                        "Ashita into the remote process!\n[E] Injection failed!"))
        self.assertTrue(stopped.startswith("The game loader never started."))
        self.assertIn("exclusions", stopped)
        self.assertIn("Smart App Control", stopped)

    def test_tasklist_output_that_could_not_be_read(self):
        class Nothing:
            stdout = None
        real = core._run
        core._run = lambda cmd: Nothing()
        try:
            self.assertFalse(core.is_running("xiloader"))                    # (R1PFake) was: NoneType has no attribute lower
            self.assertEqual(core.count_running("xiloader"), 0)
        finally:
            core._run = real

    def test_loader_log_of_this_start(self):
        logs = os.path.join(self.dir, "xiloader", "logs")
        os.makedirs(logs)
        old, new = os.path.join(logs, "xiloader-20261121-100000-1.log"), os.path.join(logs, "xiloader-20261122-144403-372.log")
        for path, text in ((old, "old start"), (new, "this start")):
            with open(path, "w") as handle:
                handle.write(text)
        now = time.time()
        os.utime(old, (now - 5000, now - 5000))
        os.utime(new, (now - 3, now - 3))
        self.assertEqual(core.loader_log_since(now - 60, self.dir), (new, "this start"))
        self.assertEqual(core.loader_log_since(now + 60, self.dir), ("", ""))
        self.assertEqual(core.loader_log_since(now, os.path.join(self.dir, "missing")), ("", ""))

    def test_why_the_game_closed(self):
        # no log at all: the loader never ran (Leyna's crash inside the runtime)
        lines = core.why_game_closed(2.4, "")
        self.assertEqual(lines[0], "The game closed 2 seconds after it started.")
        self.assertIn("vc_redist.x86.exe", lines[1])
        self.assertNotIn("vc_redist", core.why_game_closed(2, "", windows=False)[1])
        # Sunie's log of 2026-11-22: everything fine, then the game itself gave up
        sunie = ("[11/22/26 14:44:03] Successfully logged in as player1!\n[11/22/26 14:44:03] Connected to server!\n"
                 "[11/22/26 14:44:04] Connected to the profile server.\n[11/22/26 14:44:04] Profile loaded.\n"
                 "[11/22/26 14:44:05] Closing...\n")
        self.assertIn("the game itself closed before its window opened", core.why_game_closed(4, sunie)[1])
        # the loader's own complaint is passed on, without its time stamp
        said = core.why_game_closed(1, "[11/22/26 10:00:00] Resolving '127.0.0.1' ...\n[11/22/26 10:00:01] Failed to initialize instance of polcore!\n[11/22/26 10:00:01] Closing...\n")
        self.assertEqual(said[1], "The game loader said: Failed to initialize instance of polcore!")
        self.assertEqual(core.why_game_closed(1, "[x] Resolving '127.0.0.1' ...\n")[1], "The game loader's last line: Resolving '127.0.0.1' ...")
        # only that first pattern switches the Sandbox on (Linux)
        self.assertTrue(core.game_gave_up(sunie))
        self.assertFalse(core.game_gave_up(""))
        self.assertFalse(core.game_gave_up("[x] Profile loaded.\n[x] Failed to initialize instance of FFxi!\n"))
        self.assertFalse(core.game_gave_up("[x] Resolving '127.0.0.1' ...\n"))


if __name__ == "__main__":
    unittest.main()
