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
        open(path, "wb").write(data)
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
        self.assertEqual(by[("POST", "WildCabbagePatch/xi-forever-offline/git/refs")]["ref"], "refs/heads/contrib/gambits-20261118-1500")
        pull = by[("POST", lc.UPSTREAM + "/pulls")]
        self.assertEqual((pull["head"], pull["base"]), ("WildCabbagePatch:contrib/gambits-20261118-1500", "main"))
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
        self.assertEqual(lc.areas_for(people, "wildcabbagepatch"), ["gambits"])


if __name__ == "__main__":
    unittest.main()
