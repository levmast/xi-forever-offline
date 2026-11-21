#!/usr/bin/env python3
"""Adds your team's waiting updates (pull requests on GitHub) to the build on this PC, the same safe way as a Phoenix update.

  python team_update.py check     what is waiting (changes nothing)
  python team_update.py update    add every waiting update to this PC: merge, rebuild if needed, copy new add-ons to Ashita
  python team_update.py undo      go back to how both folders were before the last "update"
  python team_update.py push      send what is on this PC to GitHub (your own commits and the merged updates)

How it stays safe (the same rules as server_update.py):
  * Your own uncommitted edits are saved as ONE local commit first, in each folder that gets an update.
  * Each update is merged in. If anything clashes, everything is cancelled and both folders are put back exactly as they
    were, so a failed run changes nothing. The server update goes first: an add-on never arrives without its server side.
  * The versions from before are written to team-update-state.json, which "undo" uses.
  * Nothing is sent to GitHub by "update". Test in game first, then "push" (or publish): GitHub then marks the pull
    requests as merged by itself.
"""
import json
import os
import shutil
import sys
import urllib.request

import server_update as su

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "team-update-state.json")
API = "https://api.github.com/repos/"
say = su.say


def repos(cfg):
    """The two folders updates can arrive for. The server's branch on this PC is 'beta'; on GitHub it is 'dev'."""
    return [
        {"key": "server", "label": "Server", "root": cfg["server_dir"], "remote": "xiforever",
         "repo": "Hurami89/xi-forever-offline-server", "branch": "dev", "push": ["push", "xiforever", "HEAD:dev"]},
        {"key": "kit", "label": "Launcher and add-ons", "root": HERE, "remote": "origin",
         "repo": "Hurami89/xi-forever-offline", "branch": "main", "push": ["push", "origin", "HEAD:main"]},
    ]


def fetch_json(url):
    try:
        import launcher_thirdparty as tp
        return json.loads(tp._get(url))
    except ImportError:
        request = urllib.request.Request(url, headers={"User-Agent": "XI-Forever-Offline", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def waiting(repo, fetch=fetch_json):
    """[{number, title, who, url}] of the open pull requests of one repo, oldest first."""
    pulls = fetch(f"{API}{repo['repo']}/pulls?state=open&per_page=50&sort=created&direction=asc")
    return [{"number": p["number"], "title": p["title"], "who": (p.get("user") or {}).get("login", "?"), "url": p["html_url"]}
            for p in pulls]


def check(cfg, fetch=fetch_json):
    total = 0
    for repo in repos(cfg):
        for pull in waiting(repo, fetch):
            total += 1
            say(f"{repo['label']}: #{pull['number']} {pull['title']}  (from {pull['who']})  {pull['url']}")
    say("No updates are waiting." if total == 0 else f"{total} update(s) waiting. 'Add to my build' brings them onto this PC.")
    return total


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2)


def load_state():
    if not os.path.exists(STATE_PATH):
        return None
    with open(STATE_PATH, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def copy_addons(cfg, files, tag):
    """A merged update that changed addons-src/<name>: copy that add-on into Ashita so it can be tried in game.
    The Ashita copy from before is kept in backups/addons-before-team-<tag>/<name>."""
    ashita = cfg.get("ashita_dir") or ""
    names = sorted({f.split("/")[1] for f in files if f.startswith("addons-src/") and f.count("/") >= 2})
    copied = []
    for name in names:
        src, dest = os.path.join(HERE, "addons-src", name), os.path.join(ashita, "addons", name)
        if not ashita or not os.path.isdir(src) or not os.path.isdir(os.path.join(ashita, "addons")):
            continue
        if os.path.isdir(dest):
            shutil.copytree(dest, os.path.join(su.BACKUPS, f"addons-before-team-{tag}", name), dirs_exist_ok=True)
        shutil.copytree(src, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.before-*", "*.bak"))
        copied.append(name)
    return copied


def update(cfg, hooks=None, fetch=fetch_json, force_running=False):
    hooks = {**su.HOOKS, **(hooks or {})}
    plan = []
    for repo in repos(cfg):
        pulls = waiting(repo, fetch)
        if pulls:
            plan.append((repo, pulls))
    if not plan:
        say("No updates are waiting. Nothing to do.")
        return 2
    if not force_running and hooks["servers_running"]():
        say("The server is running. Close the game first, then try again.")
        return 1
    for repo, _ in plan:
        g = su.Git(repo["root"])
        if not os.path.exists(os.path.join(repo["root"], ".git")):
            say(f"{repo['label']}: this folder is not a git checkout.")
            return 1
        if g.run("rev-parse", "-q", "--verify", "MERGE_HEAD")[0] == 0:
            say(f"{repo['label']}: a merge is already in progress there. Nothing was changed. Tell Claude.")
            return 1

    tag = su.stamp()
    os.makedirs(su.BACKUPS, exist_ok=True)
    state = {"time": tag, "stage": "started", "repos": {}}
    done = []                 # (repo, g, before, ours_commit) of every folder touched so far, for a clean cancel

    def cancel(reason, conflicts=()):
        for repo, g, before, ours_commit in done:
            su.put_back(g, before, ours_commit)
        state["stage"] = "cancelled"
        save_state(state)
        say()
        say("CANCELLED: both folders are exactly as they were.")
        say(reason)
        for name in conflicts:
            say("   " + name)
        say("Tell Claude and paste this.")
        return 1

    changed = {}
    for repo, pulls in plan:
        g = su.Git(repo["root"])
        before = g.out("rev-parse", "HEAD")
        patch = os.path.join(su.BACKUPS, repo["key"] + "-edits-before-team-" + tag + ".patch")
        g.run("diff", "HEAD", "--output=" + patch)
        ours_commit = None
        if g.run("diff", "--quiet", "HEAD")[0] != 0:
            say(f"{repo['label']}: saving your own edits as a local commit...")
            g.run("add", "-u")
            rc, _, err = g.run("commit", "-m", f"XI: Forever Offline: local edits before team update {tag}", ident=True)
            if rc != 0:
                g.run("reset", "--mixed", before)
                return cancel(f"{repo['label']}: could not save your edits ({err[:200]}).")
            ours_commit = g.out("rev-parse", "HEAD")
        done.append((repo, g, before, ours_commit))
        state["repos"][repo["key"]] = {"before": before, "ours_commit": ours_commit}
        save_state(state)

        files = []
        for pull in pulls:
            say(f"{repo['label']}: getting #{pull['number']} {pull['title']} (from {pull['who']})...")
            rc, _, err = g.run("fetch", "--quiet", repo["remote"], f"pull/{pull['number']}/head")
            if rc != 0:
                return cancel(f"{repo['label']}: could not download #{pull['number']} ({err[:200]}).")
            theirs = g.out("rev-parse", "FETCH_HEAD")
            base = g.out("merge-base", "HEAD", theirs)
            files += g.lines("diff", "--name-only", base, theirs) if base else []
            rc, _, err = g.run("merge", "--no-edit", "-m", f"Team update #{pull['number']}: {pull['title']} (from {pull['who']})",
                               theirs, ident=True)
            if rc != 0:
                conflicts = g.lines("diff", "--name-only", "--diff-filter=U")
                if conflicts:
                    return cancel(f"{repo['label']}: #{pull['number']} clashes with what is on this PC in these files:", conflicts)
                return cancel(f"{repo['label']}: #{pull['number']} could not be merged ({(err or 'unknown reason')[:300]}).")
            say(f"{repo['label']}: #{pull['number']} added.")
        changed[repo["key"]] = files
        state["repos"][repo["key"]]["after"] = g.out("rev-parse", "HEAD")
        save_state(state)

    state["stage"] = "merged"
    server_files = changed.get("server", [])
    state["rebuild"] = su.needs_rebuild(server_files)
    save_state(state)

    if su.needs_database(server_files):
        say("Note: this update changes the server's sql folder. Run the Phoenix 'Update now' database step or tell Claude.")
    if state["rebuild"]:
        say("Rebuilding the server (this can take a while)...")
        reconfigure = any(f.endswith((".cpp", ".c", "CMakeLists.txt", ".cmake")) for f in server_files)
        if not hooks["rebuild"](cfg, reconfigure):
            state["stage"] = "build-failed"
            save_state(state)
            say("!! The build FAILED (see above). Use Undo to go back to the version that worked.")
            return 1
    copied = copy_addons(cfg, changed.get("kit", []), tag)
    if copied:
        say("Copied into Ashita so you can try it in game: " + ", ".join(copied))
    state["stage"] = "done"
    save_state(state)
    say()
    say("DONE. The updates are on this PC. Try them in game. They go to players with your next Publish;")
    say("press 'Send to GitHub' first (Publish asks for that), which also marks them as merged there.")
    return 0


def undo(cfg, hooks=None, force_running=False):
    hooks = {**su.HOOKS, **(hooks or {})}
    state = load_state()
    if not state or not state.get("repos") or state.get("stage") in ("undone", "cancelled"):
        say("There is no team update to undo.")
        return 1
    if not force_running and hooks["servers_running"]():
        say("The server is running. Close the game first.")
        return 1
    by_key = {repo["key"]: repo for repo in repos(cfg)}
    for key, saved in state["repos"].items():
        repo = by_key[key]
        g = su.Git(repo["root"])
        if saved.get("after") and g.out("rev-parse", "HEAD") != saved["after"]:
            say(f"{repo['label']}: this folder has changed since the team update (new commits), so it is left alone.")
            continue
        pushed = g.run("merge-base", "--is-ancestor", "HEAD", repo["remote"] + "/" + repo["branch"])[0] == 0
        if saved.get("after") and pushed:
            say(f"{repo['label']}: the update was already sent to GitHub, so it is left alone (undoing it here would not undo it there).")
            continue
        say(f"{repo['label']}: going back to version {su.short(saved['before'])}...")
        if g.run("rev-parse", "-q", "--verify", "MERGE_HEAD")[0] == 0:
            g.run("merge", "--abort")
        if saved.get("ours_commit"):
            g.run("reset", "--hard", saved["ours_commit"])
            g.run("reset", "--mixed", saved["before"])
        else:
            g.run("reset", "--hard", saved["before"])
    if state.get("rebuild"):
        say("The code changed back, so the server is being rebuilt...")
        if not hooks["rebuild"](cfg, True):
            say("!! The rebuild failed. Run 'Rebuild server.bat' yourself and send Claude the last lines.")
            return 1
    state["stage"] = "undone"
    save_state(state)
    say("DONE. Add-ons copied into Ashita were left there; their old copies are in backups (addons-before-team-...).")
    return 0


def push(cfg):
    """Sends this PC's commits to GitHub: the kit to main, the server to dev (never to Phoenix)."""
    worst = 0
    for repo in repos(cfg):
        g = su.Git(repo["root"])
        dirty = [line for line in g.lines("status", "--porcelain", "--untracked-files=no")]
        if dirty:
            say(f"{repo['label']}: {len(dirty)} changed file(s) are not committed yet; only what is committed is sent.")
        rc, out, err = g.run(*repo["push"])
        text = (err or out or "").strip().splitlines()
        if rc == 0:
            say(f"{repo['label']}: sent to GitHub." + (" (" + text[-1].strip() + ")" if text else ""))
        else:
            worst = 1
            say(f"{repo['label']}: NOT sent: " + " ".join(text)[-300:])
    return worst


def main(argv):
    mode = argv[1] if len(argv) > 1 else "check"
    cfg = su.load_config()
    if mode == "check":
        check(cfg)
        return 0
    if mode == "update":
        return update(cfg)
    if mode == "undo":
        return undo(cfg)
    if mode == "push":
        return push(cfg)
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
