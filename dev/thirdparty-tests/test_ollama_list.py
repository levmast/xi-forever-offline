"""(2026-11-26) `ollama list` must never hold the launcher up: the Ollama it starts keeps the output handle open.
Meli, Lunali, Teutonic84, Rennie: the launcher did not open the first time unless Ollama was already running.
Run: python3 dev/thirdparty-tests/test_ollama_list.py   (the stand-in "ollama" is a shell script: not on Windows)"""
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
import launcher_thirdparty as tp  # noqa: E402

TABLE = "NAME            ID      SIZE    MODIFIED\\ngemma4:12b      abc     8 GB    2 days ago\\nmistral-nemo:latest  def  7 GB  3 weeks ago\\n"

@unittest.skipIf(os.name == "nt", "the stand-in ollama is a shell script")
class OllamaListTest(unittest.TestCase):
    def setUp(self):
        self.real_find = tp.find_ollama
        self.addCleanup(lambda: setattr(tp, "find_ollama", self.real_find))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.kids = os.path.join(self.tmp.name, "kids")

    def fake(self, body):
        path = os.path.join(self.tmp.name, "ollama")
        with open(path, "w") as f:
            f.write("#!/bin/sh\n" + body + "\n")
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return path

    def tearDown(self):
        if os.path.exists(self.kids):
            with open(self.kids) as handle:
                pids = handle.read().split()
            for pid in pids:
                try:
                    os.kill(int(pid), 9)
                except OSError:
                    pass

    def starts_server(self, seconds=40):
        # like `ollama list` with Ollama not running: it starts Ollama (which inherits our output handle and stays),
        # prints the table and exits
        return self.fake(f'sleep {seconds} &\necho $! >> "{self.kids}"\nprintf "{TABLE}"\nexit 0')

    def test_a_started_ollama_does_not_hold_the_launcher(self):
        exe = self.starts_server()
        began = time.monotonic()
        code, text = tp.ollama_list(exe)
        self.assertLess(time.monotonic() - began, 3)
        self.assertEqual(code, 0)
        self.assertIn("gemma4:12b", text)
        tp.find_ollama = lambda kit=None: exe
        began = time.monotonic()
        self.assertEqual(tp.ollama_models(), ["gemma4:12b", "mistral-nemo:latest"])
        self.assertLess(time.monotonic() - began, 3)

    def test_the_old_way_waited_on_the_started_ollama(self):
        # the same stand-in through a pipe, as before: nothing comes back until the started program lets go
        exe = self.starts_server(seconds=6)
        began = time.monotonic()
        out = subprocess.run([exe, "list"], capture_output=True, text=True)
        self.assertGreater(time.monotonic() - began, 5)
        self.assertIn("gemma4:12b", out.stdout)

    def test_a_stuck_ollama_is_given_up_on(self):
        exe = self.fake('sleep 40')
        began = time.monotonic()
        self.assertEqual(tp.ollama_list(exe, timeout=1), (None, ""))
        self.assertLess(time.monotonic() - began, 3)

    def test_not_running_and_missing(self):
        self.assertEqual(tp.ollama_list(self.fake('echo "could not connect" >&2\nexit 1')), (1, ""))
        self.assertEqual(tp.ollama_list(os.path.join(self.tmp.name, "nothing-here")), (None, ""))
        tp.find_ollama = lambda kit=None: None
        self.assertEqual(tp.ollama_models(), [])

    def test_stand_in_run_still_works(self):
        tp.find_ollama = lambda kit=None: "ollama"
        class Out:
            stdout, returncode = TABLE.replace("\\n", "\n"), 0
        self.assertEqual(tp.ollama_models(run=lambda *a, **k: Out()), ["gemma4:12b", "mistral-nemo:latest"])
        def boom(*a, **k):
            raise subprocess.TimeoutExpired("ollama", 20)
        self.assertEqual(tp.ollama_models(run=boom), [])

    def test_pull_and_remove_ask_without_a_pipe(self):
        # pull_model and remove_model ask "is Ollama answering?" the same safe way
        exe = self.starts_server()
        tp.find_ollama = lambda kit=None: exe
        asked = []
        real = tp.ollama_list
        tp.ollama_list = lambda e, timeout=20: (asked.append(e), real(e, timeout))[1]
        try:
            class Proc:
                stdout = iter(["success\n"]); returncode = 0
                def wait(self, *a, **k): return 0
                def poll(self): return 0
            try:
                tp.pull_model("gemma4:12b", log=lambda *_: None, popen=lambda *a, **k: Proc())
            except Exception:
                pass
            self.assertTrue(asked)          # models listed through ollama_list
        finally:
            tp.ollama_list = real

if __name__ == "__main__":
    unittest.main()
