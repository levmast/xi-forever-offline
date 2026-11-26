"""(2026-11-22, the user) HD texture packs from Nexus Mods through XIPivot: the player downloads the file, the launcher
puts it in the right folder and switches it on (launcher_hd.py).

Stand-in archives are built here; the two real packs are only looked at when they are in the Downloads folder.
Run: python test_hd_packs.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_hd as hd

SAMPLE = ("; XIPivot default configuration\r\n[settings]\r\n; debug\r\ndebug_log=false\r\n\r\n[overlays]\r\n; sample\r\n;0=XI-View\r\n"
          ";1=XI-Vision\r\n\r\n[cache]\r\nenabled=false\r\nmax_age=600\r\nsize=128\r\n")


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


class HdPacks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ashita = os.path.join(self.tmp, "Ashita")
        self.kit = os.path.join(self.tmp, "kit")
        os.makedirs(os.path.join(self.ashita, "config", "pivot"))
        os.makedirs(os.path.join(self.ashita, "polplugins", "DATs"))
        with open(os.path.join(self.ashita, "config", "pivot", "pivot.sample.ini"), "w", newline="") as handle:
            handle.write(SAMPLE)
        era = os.path.join(self.kit, "Era-DATs", "ROM", "0")           # our era set replaces ROM/0/0.DAT and ROM3/3/82.DAT
        os.makedirs(era)
        open(os.path.join(era, "0.DAT"), "wb").write(b"era")
        os.makedirs(os.path.join(self.kit, "Era-DATs", "ROM3", "3"))
        open(os.path.join(self.kit, "Era-DATs", "ROM3", "3", "82.DAT"), "wb").write(b"era")
        self.said = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def dats(self, *parts):
        return os.path.join(self.ashita, "polplugins", "DATs", *parts)

    def ini(self):
        with open(hd.ini_path(self.ashita), newline="") as handle:
            return handle.read()

    # ---------------------------------------------------------------- names
    def test_nexus_file_names(self):
        self.assertEqual(hd.nexus_parts("NextHD Package-12-1-0-1648563600.zip"), ("NextHD Package", 12))
        self.assertEqual(hd.nexus_parts("AshenbubsHD Prime - November 2021-1-1-2111-1636901722.rar"), ("AshenbubsHD Prime - November 2021", 1))
        self.assertEqual(hd.nexus_parts("NextHD.zip"), ("NextHD", None))
        self.assertEqual(hd.known_pack("AshenbubsHD Prime - November 2021-1-1-2111-1636901722.rar")["id"], "ashenbubs")
        self.assertEqual(hd.known_pack("NextHD Package-12-1-0-1648563600.zip")["id"], "nextgames")
        self.assertEqual(hd.known_pack("NextLore.zip")["id"], "nextgames")
        self.assertIsNone(hd.known_pack("holiday photos.zip"))
        self.assertIsNone(hd.known_pack("Some Other Game HD-1-2-3-1648563600.zip"))     # mod 1 of another game: the name decides

    def test_folder_names_are_plain(self):
        self.assertEqual(hd.folder_name("NextHD Package"), "NextHD-Package")
        self.assertEqual(hd.folder_name("AshenbubsHD-Prime"), "AshenbubsHD-Prime")
        self.assertEqual(hd.folder_name("..\\..\\evil"), "evil")
        self.assertEqual(hd.folder_name("???"), "HD-pack")

    def test_found_in_downloads_newest_first_known_only(self):
        d = os.path.join(self.tmp, "Downloads")
        os.makedirs(d)
        for i, n in enumerate(("NextHD Package-12-1-0-1648563600.zip", "notes.zip", "AshenbubsHD Basic-1-1-0-1636901722.rar", "NextHD.txt")):
            p = os.path.join(d, n)
            open(p, "wb").write(b"x" * (i + 1))
            os.utime(p, (1000 + i, 1000 + i))
        found = hd.find_downloads([d, os.path.join(self.tmp, "nowhere")])
        self.assertEqual([os.path.basename(f["path"]) for f in found], ["AshenbubsHD Basic-1-1-0-1636901722.rar", "NextHD Package-12-1-0-1648563600.zip"])
        self.assertEqual(found[0]["pack"]["id"], "ashenbubs")

    # ---------------------------------------------------------------- what is inside
    def test_pack_roots_three_layouts(self):
        top = hd.pack_roots(["ROM/0/1.DAT", "ROM2/21/README.txt", "ROM9/1/2.DAT", "readme.txt"])
        self.assertEqual(set(top), {""})
        self.assertEqual(len(top[""]), 3)                                    # readme.txt at the top is no game data
        nested = hd.pack_roots(["All-In One/XIPivot/data/DATs/NextHD/ROM/0/1.DAT", "All-In One/XIPivot/data/DATs/NextLore/ROM/0/1.DAT",
                                "All-In One/4GB Patch/LargeAddressAwarePatcher.exe", "All-In One/ReShade/reshade.ini",
                                "All-In One\\XIPivot\\data\\DATs\\NextHD\\sound\\win\\music\\data\\music101.bgw"])
        self.assertEqual(set(nested), {"All-In One/XIPivot/data/DATs/NextHD", "All-In One/XIPivot/data/DATs/NextLore"})
        self.assertEqual(sorted(rel for _p, rel in nested["All-In One/XIPivot/data/DATs/NextHD"]), ["ROM/0/1.DAT", "sound/win/music/data/music101.bgw"])
        self.assertEqual(hd.pack_roots(["AshenbubsHD-Prime/ROM/0/0.DAT"]), {"AshenbubsHD-Prime": [("AshenbubsHD-Prime/ROM/0/0.DAT", "ROM/0/0.DAT")]})
        self.assertEqual(hd.pack_roots(["../ROM/0/1.DAT", "ROM", "docs/ROM.txt", "program/romance/x.dat"]), {})

    def test_root_names_are_unique_and_from_the_archive_when_at_the_top(self):
        self.assertEqual(hd.root_names({"": []}, "C:/x/NextHD Package-12-1-0-1648563600.zip"), {"": "NextHD-Package"})
        names = hd.root_names({"a/Pack": [], "b/pack": [], "c/Other Pack": []}, "x.zip")
        self.assertEqual(names, {"a/Pack": "Pack", "b/pack": "pack-2", "c/Other Pack": "Other-Pack"})

    # ---------------------------------------------------------------- pivot.ini
    def test_ini_is_made_from_the_sample_and_keeps_everything_else(self):
        self.assertEqual(hd.read_overlays(self.ashita), [])                  # no pivot.ini yet
        hd.write_overlays(self.ashita, ["NextHD", "AshenbubsHD-Prime", "nexthd"])
        text = self.ini()
        self.assertIn("[overlays]\r\n; sample\r\n;0=XI-View\r\n;1=XI-Vision\r\n0=NextHD\r\n1=AshenbubsHD-Prime\r\n\r\n[cache]\r\nenabled=false", text)
        self.assertIn("[settings]\r\n; debug\r\ndebug_log=false", text)
        self.assertNotIn("\r\r", text)
        self.assertEqual(hd.read_overlays(self.ashita), ["NextHD", "AshenbubsHD-Prime"])     # the same pack is never listed twice
        hd.write_overlays(self.ashita, ["AshenbubsHD-Prime"])
        self.assertEqual(hd.read_overlays(self.ashita), ["AshenbubsHD-Prime"])
        self.assertIn(";0=XI-View", self.ini())                              # the sample's comment lines stay

    def test_ini_player_settings_survive(self):
        with open(hd.ini_path(self.ashita), "w", newline="") as handle:
            handle.write("[settings]\ndebug_log=true\nroot_path=D:\\mods\n\n[overlays]\n0=Mine\n1=Theirs\n3=Skipped\n\n[cache]\nenabled=true\nsize=512\n")
        self.assertEqual(hd.read_overlays(self.ashita), ["Mine", "Theirs"])  # XIPivot stops at the first missing number
        hd.set_on(self.ashita, "NextHD", True)
        text = self.ini()
        self.assertIn("root_path=D:\\mods", text)
        self.assertIn("[cache]\nenabled=true\nsize=512", text)
        self.assertIn("[overlays]\n0=Mine\n1=Theirs\n2=NextHD\n", text)
        self.assertNotIn("3=Skipped", text)
        self.assertNotIn("\r", text)                                         # the file's own line ends are kept

    def test_moved_kit_root_path_is_fixed(self):
        # (2026-11-23, Ryan) the kit moved: its old DATs folder in root_path is gone, so XIPivot loaded nothing
        with open(hd.ini_path(self.ashita), "w", newline="") as handle:
            handle.write("[settings]\r\nroot_path=Q:\\gone\\Ashita\\polplugins\\DATs\r\n\r\n[overlays]\r\n0=LoFi-FFXI\r\n")
        self.assertTrue(hd.fix_root(self.ashita))
        text = self.ini()
        self.assertIn("root_path=" + hd.dats_dir(self.ashita) + "\r\n", text.replace("\n", "\r\n") if "\r" not in text else text)
        self.assertEqual(hd.read_overlays(self.ashita), ["LoFi-FFXI"])
        self.assertFalse(hd.fix_root(self.ashita))                         # now it exists: left alone
        with open(hd.ini_path(self.ashita), "w", newline="") as handle:
            handle.write("[settings]\nroot_path=Q:\\my\\mods\n")       # a folder the player chose: never touched
        self.assertFalse(hd.fix_root(self.ashita))

    def test_no_sample_no_ini_gets_a_plain_one(self):
        os.remove(os.path.join(self.ashita, "config", "pivot", "pivot.sample.ini"))
        hd.write_overlays(self.ashita, ["A"])
        self.assertEqual(hd.read_overlays(self.ashita), ["A"])
        self.assertIn("[cache]", self.ini())

    def test_on_off_and_order(self):
        hd.write_overlays(self.ashita, ["A", "B", "C"])
        self.assertEqual(hd.move(self.ashita, "c", True), ["A", "C", "B"])
        self.assertEqual(hd.move(self.ashita, "A", True), ["A", "C", "B"])    # already first
        self.assertEqual(hd.move(self.ashita, "A", False), ["C", "A", "B"])
        self.assertEqual(hd.set_on(self.ashita, "A", False), ["C", "B"])
        self.assertEqual(hd.set_on(self.ashita, "A", True), ["C", "B", "A"])  # switched on again: at the end
        self.assertEqual(hd.move(self.ashita, "Nobody", True), ["C", "B", "A"])

    # ---------------------------------------------------------------- installing a .zip
    def test_zip_all_in_one_only_game_data_goes_in(self):
        z = make_zip(os.path.join(self.tmp, "NextHD.zip"), {
            "Pack/XIPivot/data/DATs/NextHD/ROM/0/100.DAT": b"hd100", "Pack/XIPivot/data/DATs/NextHD/ROM/0/0.DAT": b"retail zero",
            "Pack/XIPivot/data/DATs/NextHD/ROM3/3/82.DAT": b"retail", "Pack/XIPivot/data/DATs/NextHD/ROM2/21/README.txt": b"hi",
            "Pack/4GB Patch/LargeAddressAwarePatcher.exe": b"MZ", "Pack/ReShade/ReShade.ini": b"x", "Pack/XIPivot/": b""})
        done = hd.install(z, self.ashita, self.kit, log=self.said.append)
        self.assertEqual([d["name"] for d in done], ["NextHD"])
        self.assertEqual(open(self.dats("NextHD", "ROM", "0", "100.DAT"), "rb").read(), b"hd100")
        self.assertTrue(os.path.exists(self.dats("NextHD", "ROM2", "21", "README.txt")))
        self.assertFalse(os.path.exists(self.dats("NextHD", "ROM", "0", "0.DAT")))        # the era file wins
        self.assertFalse(os.path.exists(self.dats("NextHD", "ROM3", "3", "82.DAT")))
        self.assertEqual(done[0]["left_out"], 2)
        self.assertEqual(done[0]["files"], 2)
        everything = [os.path.join(r, n) for r, _d, names in os.walk(self.ashita) for n in names]
        self.assertFalse(any(n.lower().endswith((".exe", "reshade.ini", ".part")) for n in everything))
        self.assertEqual(hd.read_overlays(self.ashita), ["NextHD"])
        note = json.load(open(self.dats("NextHD", hd.MARK)))
        self.assertEqual((note["source"], note["files"], note["left_out"]), ("NextHD.zip", 2, 2))
        self.assertTrue(any("2 left out so the era files win" in line for line in self.said))

    def test_zip_with_data_at_the_top_is_named_after_the_file(self):
        z = make_zip(os.path.join(self.tmp, "NextHD Package-12-1-0-1648563600.zip"), {"ROM/1/2.DAT": b"a", "ROM9/3/4.DAT": b"b"})
        done = hd.install(z, self.ashita, self.kit, log=self.said.append)
        self.assertEqual(done[0]["name"], "NextHD-Package")
        self.assertTrue(os.path.exists(self.dats("NextHD-Package", "ROM9", "3", "4.DAT")))

    def test_second_pack_goes_after_the_first_and_again_changes_nothing(self):
        a = make_zip(os.path.join(self.tmp, "A.zip"), {"PackA/ROM/1/1.DAT": b"a"})
        b = make_zip(os.path.join(self.tmp, "B.zip"), {"PackB/ROM/1/1.DAT": b"b", "PackC/ROM/1/1.DAT": b"c"})
        hd.install(a, self.ashita, self.kit, log=self.said.append)
        hd.install(b, self.ashita, self.kit, log=self.said.append)
        hd.install(a, self.ashita, self.kit, log=self.said.append)
        self.assertEqual(hd.read_overlays(self.ashita), ["PackA", "PackB", "PackC"])
        packs = hd.installed(self.ashita)
        self.assertEqual([(p["name"], p["on"], p["order"]) for p in packs], [("PackA", True, 0), ("PackB", True, 1), ("PackC", True, 2)])
        self.assertEqual(packs[0]["source"], "A.zip")

    def test_zip_without_game_data_is_refused_with_a_reason(self):
        z = make_zip(os.path.join(self.tmp, "x.zip"), {"readme.txt": b"hi", "tools/patch.exe": b"MZ"})
        with self.assertRaises(RuntimeError) as caught:
            hd.install(z, self.ashita, self.kit, log=self.said.append)
        self.assertIn("not a texture pack", str(caught.exception))
        self.assertEqual(hd.read_overlays(self.ashita), [])

    def test_zip_cannot_write_outside_its_pack_folder(self):
        z = make_zip(os.path.join(self.tmp, "evil.zip"), {"Pack/ROM/../../../../escaped.DAT": b"x", "Pack/ROM/1/ok.DAT": b"y"})
        hd.install(z, self.ashita, self.kit, log=self.said.append)
        self.assertTrue(os.path.exists(self.dats("Pack", "ROM", "1", "ok.DAT")))
        self.assertFalse(any(n == "escaped.DAT" for _r, _d, names in os.walk(self.tmp) for n in names))

    # ---------------------------------------------------------------- a folder the player unpacked himself
    def test_folder_is_copied_not_moved(self):
        src = os.path.join(self.tmp, "unpacked", "AshenbubsHD-Basic", "ROM", "5")
        os.makedirs(src)
        open(os.path.join(src, "6.DAT"), "wb").write(b"z")
        done = hd.install(os.path.join(self.tmp, "unpacked"), self.ashita, self.kit, log=self.said.append)
        self.assertEqual(done[0]["name"], "AshenbubsHD-Basic")
        self.assertTrue(os.path.exists(self.dats("AshenbubsHD-Basic", "ROM", "5", "6.DAT")))
        self.assertTrue(os.path.exists(os.path.join(src, "6.DAT")))

    # ---------------------------------------------------------------- .rar / .7z through another program
    def unpacker(self, files, code=0, said=""):
        calls = []

        def run(command):
            calls.append(command)
            dest = command[command.index("-C") + 1] if "-C" in command else next(c[2:] for c in command if c.startswith("-o"))
            if code == 0:
                for name, data in files.items():
                    path = os.path.join(dest, *name.split("/"))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    open(path, "wb").write(data)
            return code, said
        return run, calls

    def test_the_hardcore_marks_files_are_left_out(self):
        # (2026-11-25, the user) a pack such as MoonIcon-Tactics must not hide the Hardcore / Randomized marks
        import zipfile
        z = os.path.join(self.tmp, "MoonIcon-Tactics 1.2-46-1-2-1763000000.zip")
        with zipfile.ZipFile(z, "w") as archive:
            for rel in ("MoonIcon-Tactics-1.0/ROM/119/51.DAT", "MoonIcon-Tactics-1.0/ROM/0/13.DAT", "MoonIcon-Tactics-1.0/ROM/119/52.DAT"):
                archive.writestr(rel, b"icons")
        done = hd.install(z, self.ashita, self.kit, log=self.said.append, free=100 << 30)
        self.assertEqual((done[0]["files"], done[0]["left_out"]), (1, 2))
        self.assertTrue(os.path.exists(self.dats(done[0]["name"], "ROM", "119", "52.DAT")))
        self.assertFalse(os.path.exists(self.dats(done[0]["name"], "ROM", "119", "51.DAT")))
        self.assertEqual(hd.known_pack(os.path.basename(z))["id"], "moonicon")

    def test_rar_is_unpacked_beside_its_place_and_moved_in(self):
        rar = os.path.join(self.tmp, "AshenbubsHD Prime - November 2021-1-1-2111-1636901722.rar")
        open(rar, "wb").write(b"Rar!")
        run, calls = self.unpacker({"AshenbubsHD-Prime/ROM/0/0.DAT": b"retail", "AshenbubsHD-Prime/ROM/0/2.DAT": b"hd", "AshenbubsHD-Prime/ROM9/1/1.DAT": b"hd9"})
        done = hd.install(rar, self.ashita, self.kit, log=self.said.append, run=run, tools=[("tar", "C:/Windows/System32/tar.exe")], free=100 << 30)
        self.assertEqual(calls[0][:2], ["C:/Windows/System32/tar.exe", "-xf"])
        self.assertEqual(done[0]["name"], "AshenbubsHD-Prime")
        self.assertEqual((done[0]["files"], done[0]["left_out"]), (2, 1))
        self.assertTrue(os.path.exists(self.dats("AshenbubsHD-Prime", "ROM9", "1", "1.DAT")))
        self.assertFalse(os.path.exists(self.dats("AshenbubsHD-Prime", "ROM", "0", "0.DAT")))
        self.assertEqual([n for n in os.listdir(self.dats()) if n.startswith(hd.TEMP)], [])   # nothing left of the unpacking
        self.assertEqual(hd.read_overlays(self.ashita), ["AshenbubsHD-Prime"])

    def test_second_program_is_tried_when_the_first_cannot_read_it(self):
        rar = os.path.join(self.tmp, "p.rar")
        open(rar, "wb").write(b"Rar!")
        ok, _calls = self.unpacker({"P/ROM/1/1.DAT": b"x"})
        seen = []

        def run(command):
            seen.append(os.path.basename(command[0]))
            if "tar" in command[0]:
                dest = command[command.index("-C") + 1]
                os.makedirs(os.path.join(dest, "half"))                     # what a failed try leaves behind
                open(os.path.join(dest, "half", "junk"), "wb").write(b"j")
                return 1, "tar.exe: Unrecognized archive format\n"
            return ok(command)
        done = hd.install(rar, self.ashita, self.kit, log=self.said.append, run=run, free=100 << 30,
                          tools=[("tar", "C:/Windows/System32/tar.exe"), ("7z", "C:/Program Files/7-Zip/7z.exe")])
        self.assertEqual(seen, ["tar.exe", "7z.exe"])
        self.assertEqual(done[0]["name"], "P")
        self.assertFalse(os.path.exists(self.dats("half")))

    def test_no_program_or_none_that_works_says_what_to_do(self):
        rar = os.path.join(self.tmp, "p.rar")
        open(rar, "wb").write(b"Rar!")
        with self.assertRaises(RuntimeError) as caught:
            hd.install(rar, self.ashita, self.kit, log=self.said.append, tools=[], free=100 << 30)
        self.assertIn("7-Zip", str(caught.exception))
        self.assertIn("Install from a folder", str(caught.exception))
        run, _calls = self.unpacker({}, code=1, said="tar.exe: Unrecognized archive format\n")
        with self.assertRaises(RuntimeError) as caught:
            hd.install(rar, self.ashita, self.kit, log=self.said.append, run=run, tools=[("tar", "tar.exe")], free=100 << 30)
        self.assertIn("Unrecognized archive format", str(caught.exception))
        self.assertIn("7-Zip", str(caught.exception))
        self.assertEqual([n for n in os.listdir(self.dats()) if n.startswith(hd.TEMP)], [])
        self.assertEqual(hd.read_overlays(self.ashita), [])

    def test_which_programs(self):
        env = {"SystemRoot": "C:\\Windows", "ProgramFiles": "C:\\Program Files", "ProgramFiles(x86)": "C:\\Program Files (x86)"}
        here = {os.path.join("C:\\Windows", "System32", "tar.exe"), os.path.join("C:\\Program Files", "7-Zip", "7z.exe")}
        tools = hd.unpackers("win32", exists=lambda p: p in here, env=env)
        self.assertEqual([k for k, _p in tools], ["tar", "7z"])                # Windows' own first: nothing to install
        self.assertEqual(hd.unpackers("win32", exists=lambda p: False, env=env), [])
        linux = hd.unpackers("linux", which=lambda n: "/usr/bin/" + n if n in ("7z", "unrar") else None)
        self.assertEqual(linux, [("7z", "/usr/bin/7z"), ("unrar", "/usr/bin/unrar")])
        self.assertEqual(hd.unpack_command("tar", "tar.exe", "a.rar", "D")[1:], ["-xf", "a.rar", "-C", "D"])
        self.assertIn("-oD", hd.unpack_command("7z", "7z.exe", "a.rar", "D"))

    # ---------------------------------------------------------------- room on the drive
    def test_room_is_checked_before_anything_is_written(self):
        z = make_zip(os.path.join(self.tmp, "P.zip"), {"P/ROM/1/1.DAT": b"x" * 5000})
        self.assertEqual(hd.space_needed(z), 5000)
        self.assertIsNone(hd.check_space(z, self.ashita, free=hd.MIN_SPARE + 5000))
        with self.assertRaises(RuntimeError) as caught:
            hd.install(z, self.ashita, self.kit, log=self.said.append, free=hd.MIN_SPARE + 4999)
        self.assertIn("Not enough room", str(caught.exception))
        self.assertFalse(os.path.exists(self.dats("P")))
        rar = os.path.join(self.tmp, "p.rar")
        open(rar, "wb").write(b"R" * 1000)
        self.assertEqual(hd.space_needed(rar), int(1000 * hd.SPACE_FACTOR))   # a guess from the file's size: about 4 times

    # ---------------------------------------------------------------- the list, and taking one out
    def test_installed_lists_the_players_own_folders_too_and_remove_deletes_one(self):
        os.makedirs(self.dats("Mine", "ROM", "1"))
        open(self.dats("Mine", "ROM", "1", "1.DAT"), "wb").write(b"12345")
        os.makedirs(self.dats("NotAPack", "stuff"))
        os.makedirs(self.dats(hd.TEMP + "x", "ROM"))
        hd.install(make_zip(os.path.join(self.tmp, "A.zip"), {"PackA/ROM/1/1.DAT": b"a"}), self.ashita, self.kit, log=self.said.append)
        packs = hd.installed(self.ashita)
        self.assertEqual([(p["name"], p["on"]) for p in packs], [("PackA", True), ("Mine", False)])
        size_before = hd.tree_size(self.dats("PackA"))[0]
        self.assertEqual(hd.remove(self.ashita, "PackA"), size_before)        # the bytes it gave back
        self.assertFalse(os.path.exists(self.dats("PackA")))
        self.assertEqual(hd.read_overlays(self.ashita), [])
        self.assertTrue(os.path.exists(self.dats("Mine", "ROM", "1", "1.DAT")))
        for bad in ("..", "", "Mine/ROM", "..\\..", "C:", "Nope", hd.TEMP + "x"):
            with self.assertRaises(ValueError):
                hd.remove(self.ashita, bad)
        self.assertTrue(os.path.isdir(self.ashita))

    def test_pivot_dll_decides_whether_xipivot_is_there(self):
        self.assertFalse(hd.pivot_installed(self.ashita))
        open(os.path.join(self.ashita, "polplugins", "pivot.dll"), "wb").write(b"MZ")
        self.assertTrue(hd.pivot_installed(self.ashita))
        self.assertFalse(hd.pivot_installed(""))

    # ---------------------------------------------------------------- the window, with a stand-in tkinter
    def test_window_runs_its_buttons(self):
        """No screen here: tkinter is replaced by widgets that only remember what they were given, and the window's own
        buttons are pressed through their commands. It catches a misspelled name or a wrong call, not how it looks."""
        import types, time
        made, asked, shown = [], [], []

        class Widget:
            def __init__(self, master=None, **kw):
                self.master, self.kw, self.children, self.alive = master, kw, [], True
                made.append(self)
                if isinstance(master, Widget):
                    master.children.append(self)

            def pack(self, **kw): return None
            def grid(self, **kw): return None
            def bind(self, *a, **kw): return None
            def configure(self, **kw): self.kw.update(kw)
            def winfo_children(self): return [c for c in self.children if c.alive]
            def destroy(self):
                self.alive = False
                for child in self.children:
                    child.destroy()
            def title(self, *a): return None
            def geometry(self, *a): return None
            def minsize(self, *a): return None
            def protocol(self, name, fn): self.kw["close"] = fn
            def lift(self): return None
            def focus_force(self): return None
            def after(self, ms, fn): self.kw["after"] = fn

        class Var:
            def __init__(self, value=""): self.value = value
            def set(self, v): self.value = v
            def get(self): return self.value

        tk = types.ModuleType("tkinter")
        tk.Toplevel = tk.Frame = tk.Label = tk.Button = Widget
        tk.StringVar, tk.TclError = Var, RuntimeError
        fd, mb = types.ModuleType("tkinter.filedialog"), types.ModuleType("tkinter.messagebox")
        fd.askopenfilename = lambda **kw: ""
        fd.askdirectory = lambda **kw: ""
        mb.askyesno = lambda title, text, **kw: asked.append(title) or True
        mb.showinfo = mb.showwarning = mb.showerror = lambda title, text, **kw: shown.append((title, text))
        tk.filedialog, tk.messagebox = fd, mb
        saved = {n: sys.modules.get(n) for n in ("tkinter", "tkinter.filedialog", "tkinter.messagebox", "launcher_hd_gui")}
        sys.modules.update({"tkinter": tk, "tkinter.filedialog": fd, "tkinter.messagebox": mb})
        sys.modules.pop("launcher_hd_gui", None)
        try:
            import launcher_hd_gui as gui
            downloads = os.path.join(self.tmp, "Downloads")
            os.makedirs(downloads)
            pack = make_zip(os.path.join(downloads, "NextHD Package-12-1-0-1648563600.zip"), {"ROM/1/2.DAT": b"abc"})
            hd.install(make_zip(os.path.join(self.tmp, "A.zip"), {"PackA/ROM/1/1.DAT": b"a", "PackB/ROM/1/1.DAT": b"b"}), self.ashita, self.kit, log=self.said.append)
            real_dirs, hd.downloads_dirs = hd.downloads_dirs, lambda kit=None: [downloads]
            boot = os.path.join(self.tmp, "boot.ini")
            open(boot, "w").write("[ashita.polplugins]\nsandbox = 1\n")
            open(os.path.join(self.ashita, "polplugins", "pivot.dll"), "wb").write(b"MZ")
            sys.path.insert(0, KIT)
            import launcher_core as core
            said = []
            look = dict(bg="#000", panel="#111", fg="#fff", dim="#888", accent="#0af", green="#0f0", red="#f00", gold="#fc0", font="Segoe UI")
            win = gui.open_window(Widget(), self.kit, self.ashita, boot, look, say=said.append, running=lambda: False, core=core)

            def buttons(text):
                return [w for w in made if w.alive and w.kw.get("text") == text and callable(w.kw.get("command"))]

            def settle():
                for _ in range(200):
                    win.kw["after"]()
                    if not any(w.kw.get("state") == "disabled" for w in made if w.alive):
                        return
                    time.sleep(0.02)
                self.fail("the window stayed busy")

            self.assertTrue(buttons("Open its page"))
            self.assertEqual(len(buttons("Install")), 1)                        # the pack in Downloads is offered
            self.assertEqual(len(buttons("Remove")), 2)
            self.assertEqual(len(buttons("On - turn off")), 2)
            buttons("Down")[0].kw["command"]()                                  # PackA one down
            self.assertEqual(hd.read_overlays(self.ashita), ["PackB", "PackA"])
            buttons("On - turn off")[0].kw["command"]()
            self.assertEqual(hd.read_overlays(self.ashita), ["PackA"])
            buttons("Off - turn on")[0].kw["command"]()
            self.assertEqual(hd.read_overlays(self.ashita), ["PackA", "PackB"])
            self.assertTrue(core.polplugin_on(boot, "pivot"))                   # switching a pack on switches XIPivot on
            buttons("Install")[0].kw["command"]()
            settle()
            self.assertEqual(shown, [])
            self.assertTrue(os.path.exists(self.dats("NextHD-Package", "ROM", "1", "2.DAT")))
            self.assertEqual(hd.read_overlays(self.ashita), ["PackA", "PackB", "NextHD-Package"])
            self.assertTrue(any("Installed: NextHD-Package" in line for line in said))
            self.assertEqual(len(buttons("Remove")), 3)
            buttons("Remove")[0].kw["command"]()
            settle()
            self.assertEqual(len(hd.installed(self.ashita)), 2)
            self.assertIn("Remove PackA", asked)
            self.assertIs(gui.open_window(Widget(), self.kit, self.ashita, boot, look), win)   # a second click shows the same window
            win.kw["close"]()
            hd.downloads_dirs = real_dirs
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    # ---------------------------------------------------------------- hooked into the launcher and into the build
    def test_the_launcher_opens_it_and_the_build_ships_it(self):
        gui = open(os.path.join(KIT, "launcher_gui.pyw"), encoding="utf-8").read()
        row = gui[gui.index("    def show_downloads(self, newer=None):"):gui.index("    def open_hd_packs(self):")]
        self.assertIn('if item["id"] == "xipivot":', row)
        self.assertIn('text="HD packs and music..."', row)
        self.assertIn("command=self.open_hd_packs", row)
        opener = gui[gui.index("    def open_hd_packs(self):"):gui.index("    def toggle_polplugin(self, item, on):")]
        self.assertIn("launcher_hd_gui.open_window(", opener)
        self.assertIn("except Exception as e:", opener)                       # a problem in the window never takes the page down
        for key in ("bg", "panel", "fg", "dim", "accent", "green", "red", "gold", "font"):
            self.assertIn(f'"{key}":', opener)
        ignore = open(os.path.join(KIT, ".gitignore"), encoding="utf-8").read()
        self.assertIn("!/launcher_hd.py", ignore)                             # the allow-list: else the files are not in the download
        self.assertIn("!/launcher_hd_gui.py", ignore)
        for script in ("build_release.ps1", "build_release.sh"):
            text = open(os.path.join(KIT, script), encoding="utf-8").read()
            self.assertRegex(text, r"launcher_hd\b")                          # imported only when the window opens: the exe needs telling
            self.assertIn("launcher_hd_gui", text)
        manifest = json.load(open(os.path.join(KIT, "thirdparty.json"), encoding="utf-8"))
        items = manifest["items"] if isinstance(manifest, dict) else manifest
        pivot = next(i for i in items if i["id"] == "xipivot")
        self.assertEqual(pivot["check"], "polplugins/pivot.dll")              # what pivot_installed looks for
        self.assertIn("HD packs and music...", pivot["note"])

    # ---------------------------------------------------------------- the real packs, when they are on this PC
    def test_real_downloads_are_recognised(self):
        folder = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(folder):
            folder = os.environ.get("XIFO_DOWNLOADS", "")
        real = os.path.join(folder, "NextHD Package-12-1-0-1648563600.zip")
        if not os.path.exists(real):
            self.skipTest("the NextHD pack is not in Downloads")
        with zipfile.ZipFile(real) as z:
            roots = hd.pack_roots([i.filename for i in z.infolist() if not i.is_dir()])
        self.assertEqual(set(roots), {""})
        self.assertGreater(len(roots[""]), 4000)
        self.assertEqual(hd.root_names(roots, real), {"": "NextHD-Package"})
        self.assertEqual(hd.known_pack(real)["id"], "nextgames")


if __name__ == "__main__":
    unittest.main()
