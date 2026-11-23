"""(Sunie, 2026-11-22) "Peek under the AI hood": the helpers write their prompts to logs/ai-hood.log only while the
switch file ai-hood.on is in the kit folder; the launcher shows the AI hood box only then; the zip's scripts add and
remove that file and nothing else.

Run: python test_ai_hood.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
sys.path.insert(0, os.path.join(KIT, "dev", "ai-hood"))
import launcher_hood as lh
import make_zip

HELPERS = {"squad": ("squad-chat", "squad_chat.py"), "crowd": ("crowds", "crowd_chat_ai.py"),
           "bots": ("crowds", "bots", "bots_chat_ai.py")}


def read(*parts):
    with open(os.path.join(KIT, *parts), encoding="utf-8") as handle:
        return handle.read()


def hood_of(which, kit):
    """The helper's own hood() function, run on a pretend kit folder."""
    source = read(*HELPERS[which])
    body = re.search(r"^def hood\(.*?(?=^def )", source, re.S | re.M).group(0)
    space = {"time": time, "KIT": kit, "BASE": Path(kit) / "squad-chat"}
    exec(body, space)
    return space["hood"]


class HoodTests(unittest.TestCase):
    def setUp(self):
        self.kit = tempfile.mkdtemp()
        self.log = os.path.join(self.kit, "logs", "ai-hood.log")

    def tearDown(self):
        shutil.rmtree(self.kit, ignore_errors=True)

    def switch_on(self):
        open(os.path.join(self.kit, "ai-hood.on"), "w").close()

    def test_off_for_everyone_else(self):
        for which in HELPERS:
            hood_of(which, self.kit)("squad chat", "m", [{"role": "user", "content": "hello"}], "hi", 1.0)
        self.assertFalse(os.path.exists(self.log), "no switch file: nothing is written")
        self.assertFalse(os.path.exists(os.path.join(self.kit, "logs")))
        self.assertFalse(lh.is_on(self.kit))

    def test_on_writes_the_whole_prompt_and_the_reply(self):
        self.switch_on()
        self.assertTrue(lh.is_on(self.kit))
        long_text = "You are Kupo, a white mage. " + "lore " * 800
        for which in HELPERS:
            hood_of(which, self.kit)(f"from {which}", "gemma4:12b", [{"role": "system", "content": long_text},
                                                                    {"role": "user", "content": "where do I farm silk?"}],
                                     "crawlers nest, kupo", 2.34)
        text = open(self.log, encoding="utf-8").read()
        for which in HELPERS:
            self.assertIn(f"from {which}  |  model gemma4:12b  |  2.3s =====", text)
        self.assertEqual(text.count(long_text.rstrip()), 3, "the system prompt is there in full, not cut")
        self.assertEqual(text.count("--- system ---"), 3)
        self.assertEqual(text.count("--- reply ---\ncrawlers nest, kupo"), 3)

    def test_a_missing_reply_and_odd_messages_never_break_the_helper(self):
        self.switch_on()
        hood = hood_of("squad", self.kit)
        hood("squad chat", "m", [{"role": "user", "content": "x"}], None, 0.5)
        hood("squad chat", "m", [{"content": 5}, {}], "(no reply: timed out)", 40)
        hood("squad chat", "m", None, "x", 1)                       # nonsense in: no error out
        text = open(self.log, encoding="utf-8").read()
        self.assertIn("--- reply ---\n(no reply)", text)
        self.assertIn("(no reply: timed out)", text)

    def test_the_log_rolls_over(self):
        self.switch_on()
        os.makedirs(os.path.dirname(self.log))
        with open(self.log, "w") as handle:
            handle.write("x" * 4_100_000)
        hood_of("bots", self.kit)("bot players", "m", [{"role": "user", "content": "hi"}], "yo", 1)
        self.assertGreater(os.path.getsize(self.log + ".1"), 4_000_000)
        self.assertLess(os.path.getsize(self.log), 1000)

    def test_every_helper_calls_it_where_the_model_answers(self):
        self.assertEqual(read(*HELPERS["squad"]).count('hood("squad chat", model, messages,'), 3)
        self.assertIn('hood(f"town crowd lines ({category})", cfg["model"], payload["messages"], content,', read(*HELPERS["crowd"]))
        self.assertIn('hood("bot players", cfg["model"], messages, content,', read(*HELPERS["bots"]))

    def test_the_window_reads_what_is_new(self):
        self.assertEqual(lh.read_new(self.log, 0), ("", 0))
        os.makedirs(os.path.dirname(self.log))
        with open(self.log, "w", encoding="utf-8") as handle:
            handle.write("===== 10:00:00  squad chat  |  model m  |  1.0s =====\n--- user ---\nhello\n")
        text, offset = lh.read_new(self.log, 0)
        self.assertEqual(text.splitlines()[2], "hello")
        self.assertEqual(lh.read_new(self.log, offset), ("", offset))
        with open(self.log, "a", encoding="utf-8") as handle:
            handle.write("--- reply ---\nhi there\n")
        more, offset2 = lh.read_new(self.log, offset)
        self.assertEqual(more, "--- reply ---\nhi there\n")
        self.assertTrue(lh.clear(self.kit))
        self.assertEqual(lh.read_new(self.log, offset2), ("", 0), "a cleared log starts again")
        with open(self.log, "w", encoding="utf-8") as handle:           # a long log: only its last part, whole lines
            handle.write("".join(f"line {i}\n" for i in range(5000)))
        tail, _ = lh.read_new(self.log, 0, most=200)
        self.assertTrue(tail.startswith("line ") and tail.endswith("line 4999\n") and len(tail) <= 200)

    def test_how_lines_are_shown(self):
        self.assertEqual(lh.line_kind("===== 10:00:00  squad chat  |  model m  |  1.0s ====="), "head")
        self.assertEqual(lh.line_kind("--- system ---"), "role")
        self.assertEqual(lh.line_kind("--- reply ---"), "role")
        self.assertEqual(lh.line_kind("just words --- here"), "")

    def test_the_files_to_tinker_with_exist_in_the_kit(self):
        labels = [label for label, _path in lh.places(KIT)]
        self.assertTrue(any("Squad chat: settings" in label for label in labels) or
                        not os.path.exists(os.path.join(KIT, "squad-chat", "config.json")))
        self.assertTrue(any("Bot players" in label for label in labels))
        self.assertTrue(any("Town crowd" in label for label in labels))

    def test_the_launcher_shows_the_box_only_with_the_switch(self):
        gui = read("launcher_gui.pyw")
        at = gui.index("import launcher_hood")
        self.assertIn("if launcher_hood.is_on(HERE):", gui[at:at + 200])
        self.assertIn("except Exception:", gui[at:at + 700])
        self.assertIn("launcher_hood", read("build_release.ps1"))
        self.assertIn("launcher_hood", read("build_release.sh"))
        self.assertIn("!/launcher_hood.py", read(".gitignore"))

    def test_the_zip_scripts(self):
        folder = os.path.join(self.kit, "unzipped", "somewhere", "XIFO-AI-hood")   # a copy, away from the real kit
        shutil.copytree(os.path.join(KIT, "dev", "ai-hood"), folder)
        game = os.path.join(self.kit, "games", "XI Forever Offline")
        os.makedirs(os.path.join(game, "squad-chat"))
        old = os.path.join(game, "squad-chat", "squad_chat.py")
        open(old, "w").write("# v0.1.59\n")
        run = lambda script, *args: subprocess.run(["bash", os.path.join(folder, script), *args], capture_output=True,
                                                   text=True, stdin=subprocess.DEVNULL, cwd=self.kit, env=dict(os.environ, HOME=self.kit))
        result = run("add-ai-hood.sh", game)
        self.assertEqual(result.returncode, 1)
        self.assertIn("older than v0.1.60", result.stdout)
        self.assertFalse(os.path.exists(os.path.join(game, "ai-hood.on")))
        shutil.copy(os.path.join(KIT, "squad-chat", "squad_chat.py"), old)        # today's helper
        before = sorted(os.listdir(game)) + sorted(os.listdir(os.path.join(game, "squad-chat")))
        result = run("add-ai-hood.sh", game)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(lh.is_on(game))
        self.assertIn("Open the AI hood", result.stdout)
        after = sorted(os.listdir(game)) + sorted(os.listdir(os.path.join(game, "squad-chat")))
        self.assertEqual(sorted(after), sorted(before + ["ai-hood.on"]), "one file added, nothing else touched")
        self.assertEqual(run("remove-ai-hood.sh", game).returncode, 0)
        self.assertFalse(lh.is_on(game))
        result = run("add-ai-hood.sh")                    # no folder given and none found: it asks, and stops without input
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not find", result.stdout)
        self.assertFalse(lh.is_on(game))
        # unzipped into the game's folder: it finds the game by itself
        inside = os.path.join(game, "XIFO-AI-hood")
        shutil.copytree(os.path.join(KIT, "dev", "ai-hood"), inside)
        found = subprocess.run(["bash", os.path.join(inside, "add-ai-hood.sh")], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, cwd=self.kit, env=dict(os.environ, HOME=self.kit))
        self.assertEqual(found.returncode, 0, found.stdout + found.stderr)
        self.assertTrue(lh.is_on(game))

    def test_the_zip(self):
        path = make_zip.build(self.kit)
        with zipfile.ZipFile(path) as z:
            names = sorted(z.namelist())
            self.assertEqual(names, sorted("XIFO-AI-hood/" + n for n in make_zip.FILES))
            self.assertEqual(z.getinfo("XIFO-AI-hood/add-ai-hood.sh").external_attr >> 16, 0o755)
            for name in names:                       # words and scripts only: no game files, nothing to run but these
                self.assertTrue(name.endswith((".txt", ".sh", ".bat")), name)
            self.assertLess(sum(i.file_size for i in z.infolist()), 20_000)
            bat = z.read("XIFO-AI-hood/add-ai-hood.bat")
            self.assertIn(b"\r\n", bat)
            self.assertNotIn(b"\n", bat.replace(b"\r\n", b""))
        self.assertIn("v0.1.60", read("dev", "ai-hood", "README.txt"))


if __name__ == "__main__":
    unittest.main()
