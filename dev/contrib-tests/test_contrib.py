"""Stand-in tests for launcher_contrib.py (contributor mode): no GitHub, no network. Run: python test_contrib.py"""
import base64, json, os, sys, tempfile, unittest
KIT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, KIT)
import launcher_contrib as lc


class Done:
    def __init__(self, out="", code=0):
        self.stdout, self.returncode, self.stderr = out, code, ""


class FakeGitHub:
    """Answers the calls launcher_contrib makes, and records them."""

    def __init__(self, people, upstream_files, fork_exists=True):
        self.people, self.files, self.fork_exists, self.calls = people, upstream_files, fork_exists, []

    def __call__(self, method, url, token, data=None):
        self.calls.append((method, url.replace(lc.API, ""), data))
        path = url.replace(lc.API, "")
        if url.endswith("/user"):
            return {"login": "WildCabbagePatch"}
        if path.startswith(lc.UPSTREAM + "/contents/contributors.json"):
            return {"content": base64.b64encode(json.dumps(self.people).encode()).decode()}
        if path == lc.UPSTREAM + "/git/ref/heads/main":
            return {"object": {"sha": "c0ffee"}}
        if path == lc.UPSTREAM + "/git/commits/c0ffee":
            return {"tree": {"sha": "t1"}}
        if path.startswith(lc.UPSTREAM + "/git/trees/t1"):
            return {"tree": [{"type": "blob", "path": "addons-src/Gambits/" + k, "sha": v} for k, v in self.files.items()] +
                            [{"type": "blob", "path": "launcher_gui.pyw", "sha": "x"}]}
        if path == "WildCabbagePatch/xi-forever-offline" and method == "GET":
            if not self.fork_exists:
                raise RuntimeError("GitHub said 404: Not Found")
            return {"parent": {"full_name": lc.UPSTREAM}}
        if path.endswith("/forks"):
            self.fork_exists = True
            return {"full_name": "WildCabbagePatch/xi-forever-offline"}
        if path.endswith("/git/blobs"):
            return {"sha": "b" + str(len(self.calls))}
        if path.endswith("/git/trees"):
            return {"sha": "t2"}
        if path.endswith("/git/commits"):
            return {"sha": "c2"}
        if path.endswith("/pulls") and method == "POST":
            return {"html_url": "https://github.com/" + lc.UPSTREAM + "/pull/1"}
        return {}


def folder_with(files):
    tmp = tempfile.mkdtemp()
    for rel, data in files.items():
        path = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
    return tmp


PEOPLE = {"contributors": {"wildcabbagepatch": {"areas": ["gambits", "not-an-area"]}}}


class ContribTests(unittest.TestCase):
    def test_list_decides_and_ignores_case(self):
        self.assertEqual(lc.areas_for(PEOPLE, "WildCabbagePatch"), ["gambits"])
        self.assertEqual(lc.areas_for(PEOPLE, "someone-else"), [])
        self.assertEqual(lc.areas_for({}, "wildcabbagepatch"), [])

    def test_sign_in_reads_the_list_from_github(self):
        gh = FakeGitHub(PEOPLE, {})
        run = lambda cmd, **kw: Done("protocol=https\nhost=github.com\nusername=w\npassword=gho_abc\n")
        self.assertEqual(lc.sign_in(run, gh), ("gho_abc", "WildCabbagePatch", ["gambits"]))

    def test_token_falls_back_to_gh_then_explains(self):
        def run(cmd, **kw):
            if cmd[0] == "git":
                raise FileNotFoundError
            return Done("gho_cli\n")
        self.assertEqual(lc.github_token(run), "gho_cli")
        with self.assertRaises(RuntimeError):
            lc.github_token(lambda cmd, **kw: Done("", 1))

    def test_blob_sha_matches_git(self):
        self.assertEqual(lc.blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")   # git hash-object

    def test_compare_skips_backups_and_never_deletes(self):
        same = b"same"
        folder = folder_with({"Gambits.lua": b"new code", "Gambits_README.md": same, "jobs/WAR.lua": b"x",
                              "Gambits.lua.before-credit": b"old", "Gambits.lua.bak": b"old"})
        local = lc.local_files(folder)
        self.assertEqual(sorted(local), ["Gambits.lua", "Gambits_README.md", "jobs/WAR.lua"])
        diff = lc.compare(local, {"Gambits.lua": lc.blob_sha(b"old code"), "Gambits_README.md": lc.blob_sha(same),
                                  "only_on_github.lua": "z"})
        self.assertEqual(diff, {"changed": ["Gambits.lua"], "added": ["jobs/WAR.lua"]})

    def test_live_folder_and_override(self):
        self.assertEqual(lc.local_folder("gambits", {"ashita_dir": "C:/A"}), os.path.join("C:/A", "addons", "Gambits"))
        self.assertEqual(lc.local_folder("gambits", {"ashita_dir": "C:/A", "contrib_gambits_dir": "D:/dev/G"}), "D:/dev/G")

    def test_send_makes_fork_branch_and_pull_request(self):
        folder = folder_with({"Gambits.lua": b"new code", "Gambits_README.md": b"same"})
        gh = FakeGitHub(PEOPLE, {"Gambits.lua": lc.blob_sha(b"old"), "Gambits_README.md": lc.blob_sha(b"same")}, fork_exists=False)
        found = lc.check("tok", "gambits", {"contrib_gambits_dir": folder}, gh)
        self.assertEqual(found["diff"], {"changed": ["Gambits.lua"], "added": []})
        url = lc.send("tok", "WildCabbagePatch", "gambits", found, "Gambits: smarter cures", "Tested on WHM 30",
                      opener=gh, log=lambda m: None, now=lambda f: "20261118-1500", wait=lambda s: None)
        self.assertTrue(url.endswith("/pull/1"))
        by = {(m, p.split("?")[0]): d for m, p, d in gh.calls}
        self.assertIn(("POST", lc.UPSTREAM + "/forks"), by)
        tree = by[("POST", "WildCabbagePatch/xi-forever-offline/git/trees")]
        self.assertEqual(tree["base_tree"], "t1")
        self.assertEqual([e["path"] for e in tree["tree"]], ["addons-src/Gambits/Gambits.lua"])    # only the changed file
        self.assertEqual(by[("POST", "WildCabbagePatch/xi-forever-offline/git/commits")]["parents"], ["c0ffee"])
        self.assertEqual(by[("POST", "WildCabbagePatch/xi-forever-offline/git/refs")]["ref"], "refs/heads/contrib/kit-20261118-1500")
        pull = by[("POST", lc.UPSTREAM + "/pulls")]
        self.assertEqual((pull["head"], pull["base"]), ("WildCabbagePatch:contrib/kit-20261118-1500", "main"))
        self.assertIn("Tested on WHM 30", pull["body"])

    def test_nothing_to_send(self):
        with self.assertRaises(RuntimeError):
            lc.send("tok", "w", "gambits", {"diff": {"changed": [], "added": []}}, "t", "", opener=FakeGitHub(PEOPLE, {}))

    def test_fork_of_something_else_is_refused(self):
        gh = FakeGitHub(PEOPLE, {})
        gh.__class__ = type("Other", (FakeGitHub,), {"__call__": lambda self, m, u, t, d=None: {"parent": {"full_name": "x/y"}}})
        with self.assertRaises(RuntimeError):
            lc.ensure_fork("tok", "w", gh, log=lambda m: None)

    def test_list_file_in_repo_is_valid(self):
        with open(os.path.join(KIT, "contributors.json"), encoding="utf-8") as handle:
            people = json.load(handle)
        self.assertEqual(lc.areas_for(people, "wildcabbagepatch"), list(lc.AREAS))
        self.assertEqual(lc.areas_for(people, "sirtanta"), list(lc.AREAS))


class FakeServerRepo:
    """The server repo (branch dev) and the contributor's fork of it."""
    SRV = "Hurami89/xi-forever-offline-server"

    def __init__(self, files, crlf_on_github=()):
        self.files, self.crlf, self.calls = files, set(crlf_on_github), []

    def __call__(self, method, url, token, data=None):
        path = url.replace(lc.API, "")
        self.calls.append((method, path, data))
        if path == self.SRV + "/git/ref/heads/dev":
            return {"object": {"sha": "s0"}}
        if path == self.SRV + "/git/commits/s0":
            return {"tree": {"sha": "st"}}
        if path.startswith(self.SRV + "/git/trees/st"):
            return {"tree": [{"type": "blob", "path": k, "sha": lc.blob_sha(v)} for k, v in self.files.items()]}
        if path.startswith(self.SRV + "/git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            for k, v in self.files.items():
                if lc.blob_sha(v) == sha:
                    return {"content": base64.b64encode(v).decode()}
        if path == "SirTanta/xi-forever-offline-server" and method == "GET":
            return {"parent": {"full_name": self.SRV}}
        if path.endswith("/git/blobs") and method == "POST":
            return {"sha": "b" + str(len(self.calls)), "_data": data}
        if path.endswith("/git/trees"):
            return {"sha": "t2"}
        if path.endswith("/git/commits"):
            return {"sha": "c2"}
        if path.endswith("/pulls") and method == "POST":
            return {"html_url": "https://github.com/" + self.SRV + "/pull/7"}
        return {}


class EverythingTests(unittest.TestCase):
    def test_all_means_every_area(self):
        people = {"contributors": {"SirTanta": {"areas": ["all"]}}}
        self.assertEqual(lc.areas_for(people, "sirtanta"), list(lc.AREAS))
        self.assertIn("server", lc.areas_for(people, "SirTanta"))

    def test_server_update_goes_to_server_repo_dev(self):
        squad_old = b"local x = 1\nreturn x\n"
        files = {"modules/custom/lua/squad.lua": squad_old, "src/map/a.cpp": b"int a;\n", "README.md": b"hi\n"}
        folder = folder_with({
            "modules/custom/lua/squad.lua": b"local x = 2\r\nreturn x\r\n",   # changed, saved with Windows line endings
            "src/map/a.cpp": b"int a;\r\n",                                   # unchanged, CRLF checkout
            "README.md": b"hi\n",                                             # unchanged
            "build/xi_map.exe": b"\0binary",                                  # not on GitHub: never listed by itself
            "modules/custom/lua/squad_space.lua": b"return {}\n",             # new: added by hand
        })
        gh = FakeServerRepo(files)
        found = lc.check("tok", "server", {"server_dir": folder}, gh)
        self.assertEqual(found["diff"], {"changed": ["modules/custom/lua/squad.lua"], "added": []})
        rel = lc.add_file(found, os.path.join(folder, "modules", "custom", "lua", "squad_space.lua"))
        self.assertEqual(rel, "modules/custom/lua/squad_space.lua")
        with self.assertRaises(RuntimeError):
            lc.add_file(found, os.path.abspath(__file__))                     # outside the server folder
        url = lc.send("tok", "SirTanta", "server", found, "Squad: spacing", "from Jon", opener=gh, log=lambda m: None,
                      now=lambda f: "x", wait=lambda s: None)
        self.assertTrue(url.endswith("/pull/7"))
        blobs = [d for m, p, d in gh.calls if m == "POST" and p.endswith("/git/blobs")]
        self.assertEqual(base64.b64decode(blobs[0]["content"]), b"local x = 2\nreturn x\n")   # sent with GitHub's LF endings
        tree = [d for m, p, d in gh.calls if m == "POST" and p.endswith("/git/trees")][0]
        self.assertEqual([e["path"] for e in tree["tree"]],
                         ["modules/custom/lua/squad.lua", "modules/custom/lua/squad_space.lua"])
        pull = [d for m, p, d in gh.calls if m == "POST" and p.endswith("/pulls")][0]
        self.assertEqual((pull["base"], pull["head"]), ("dev", "SirTanta:contrib/server-x"))
        self.assertTrue([p for m, p, d in gh.calls if m == "POST" and p == FakeServerRepo.SRV + "/pulls"])

    def test_pick_only_some_files(self):
        files = {"a.lua": b"1\n", "b.lua": b"1\n"}
        folder = folder_with({"a.lua": b"2\n", "b.lua": b"2\n"})
        gh = FakeServerRepo(files)
        found = lc.check("tok", "server", {"server_dir": folder}, gh)
        lc.send("tok", "SirTanta", "server", found, "t", "", opener=gh, log=lambda m: None, now=lambda f: "x",
                wait=lambda s: None, files=["b.lua"])
        tree = [d for m, p, d in gh.calls if m == "POST" and p.endswith("/git/trees")][0]
        self.assertEqual([e["path"] for e in tree["tree"]], ["b.lua"])
        with self.assertRaises(RuntimeError):
            lc.send("tok", "SirTanta", "server", found, "t", "", opener=gh, files=[])

    def test_kit_folder_is_the_launcher_folder(self):
        self.assertEqual(lc.local_folder("kit", {}, "C:/XIF"), "C:/XIF")
        self.assertEqual(lc.local_folder("server", {"server_dir": "C:/XIF/server"}), "C:/XIF/server")


class OneButtonTests(unittest.TestCase):
    def test_everything_in_one_go(self):
        """Gambits + launcher files share one pull request on the kit repo; server files get their own."""
        kit_gh = FakeGitHub(PEOPLE, {"Gambits.lua": lc.blob_sha(b"old")})
        srv_gh = FakeServerRepo({"modules/custom/lua/squad.lua": b"1\n"})

        def both(method, url, token, data=None):
            path = url.replace(lc.API, "")
            if "xi-forever-offline-server" in path:
                return srv_gh(method, url, token, data)
            if path.startswith(lc.UPSTREAM + "/git/trees/t1"):          # the whole kit repo
                return {"tree": [{"type": "blob", "path": "addons-src/Gambits/Gambits.lua", "sha": lc.blob_sha(b"old")},
                                 {"type": "blob", "path": "launcher_gui.pyw", "sha": lc.blob_sha(b"gui\n")}]}
            if path == "SirTanta/xi-forever-offline" and method == "GET":
                return {"parent": {"full_name": lc.UPSTREAM}}
            return kit_gh(method, url, token, data)

        live = folder_with({"Gambits.lua": b"new"})
        kit = folder_with({"launcher_gui.pyw": b"gui changed\n", "addons-src/Gambits/Gambits.lua": b"old"})
        srv = folder_with({"modules/custom/lua/squad.lua": b"2\n"})
        cfg = {"contrib_gambits_dir": live, "server_dir": srv}
        founds = {a: lc.check("tok", a, cfg, both, kit_dir=kit) for a in ("gambits", "kit", "server")}
        self.assertEqual(founds["kit"]["diff"]["changed"], ["launcher_gui.pyw"])
        self.assertEqual(lc.area_for_path(founds, os.path.join(srv, "x.lua")), "server")
        self.assertEqual(lc.area_for_path(founds, os.path.join(live, "y.lua")), "gambits")
        chosen = [(a, rel) for a, f in founds.items() for rel in f["diff"]["changed"] + f["diff"]["added"]]
        urls = lc.send_all("tok", "SirTanta", founds, chosen, "Big update", "", opener=both, log=lambda m: None,
                           now=lambda f: "t", wait=lambda s: None)
        self.assertEqual(len(urls), 2)
        kit_tree = [d for m, p, d in kit_gh.calls if m == "POST" and p.endswith("/git/trees")][0]
        self.assertEqual(sorted(e["path"] for e in kit_tree["tree"]), ["addons-src/Gambits/Gambits.lua", "launcher_gui.pyw"])
        srv_tree = [d for m, p, d in srv_gh.calls if m == "POST" and p.endswith("/git/trees")][0]
        self.assertEqual([e["path"] for e in srv_tree["tree"]], ["modules/custom/lua/squad.lua"])


if __name__ == "__main__":
    unittest.main()
