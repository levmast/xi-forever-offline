"""Contributor mode: team members send their changes to the dev for review (no GUI code here).

Who may send what is decided by contributors.json on GitHub (the copy on the main branch, which only the repo owner can
change), never by a local file. A contributor signs in with the GitHub sign-in Git keeps on their PC, the launcher checks
their username against that list, and "Send update" puts the changed files of their area (Gambits first) on a new branch
of their own fork and opens a pull request to the main repo. Nothing reaches players until the owner merges it and
publishes an update. No git commands are needed on the contributor's side: everything goes through the GitHub API.
"""
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

UPSTREAM = "Hurami89/xi-forever-offline"
BASE_BRANCH = "main"
LIST_PATH = "contributors.json"
API = "https://api.github.com/repos/"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# What each area covers: the folder in the repo, and where the contributor's working copy is on their PC
# (the live Ashita addon they test in game, unless config.json says otherwise with "contrib_<area>_dir").
AREAS = {
    "gambits": {"label": "Gambits", "repo_path": "addons-src/Gambits", "live": ("addons", "Gambits")},
}

# never sent: backups and leftovers next to the real files
SKIP_SUFFIXES = (".bak", ".orig", ".tmp", ".old", ".retired", "~", ".swp", ".log")
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__", ".git"}
MAX_FILE = 20 * 1024 * 1024


# ----- signing in -----
def github_token(run=subprocess.run):
    """The GitHub sign-in on this PC: Git's (Git Credential Manager opens a browser sign-in the first time), else the
    GitHub CLI's."""
    try:
        result = run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True,
                     text=True, creationflags=NO_WINDOW, timeout=180)
        found = dict(line.split("=", 1) for line in (result.stdout or "").splitlines() if "=" in line)
        if result.returncode == 0 and found.get("password"):
            return found["password"]
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        result = run(["gh", "auth", "token"], capture_output=True, text=True, creationflags=NO_WINDOW, timeout=30)
        if result.returncode == 0 and (result.stdout or "").strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    raise RuntimeError("No GitHub sign-in on this PC. Install Git for Windows (git-scm.com) and press Sign in again: "
                       "it opens GitHub's sign-in page in your browser.")


def api(method, url, token, data=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "User-Agent": "XI-Forever-Offline-contrib", "X-GitHub-Api-Version": "2022-11-28"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url if url.startswith("http") else API + url, data=body, headers=headers, method=method)
    try:
        import launcher_thirdparty as tp             # the same certificates the other downloads use (the built exe too)
        context = tp.ssl_context()
    except Exception:
        context = None
    try:
        with urllib.request.urlopen(request, timeout=300, context=context) as response:
            text = response.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("message", detail)
        except ValueError:
            pass
        raise RuntimeError(f"GitHub said {e.code}: {detail[:300]}") from None
    return json.loads(text) if text else {}


def whoami(token, opener=api):
    return opener("GET", "https://api.github.com/user", token)["login"]


# ----- the list (on GitHub, main branch) -----
def load_list(token, opener=api):
    found = opener("GET", f"{UPSTREAM}/contents/{LIST_PATH}?ref={BASE_BRANCH}", token)
    return json.loads(base64.b64decode(found["content"]).decode("utf-8-sig"))


def areas_for(people, login):
    """The areas this GitHub user may send (case does not matter in GitHub names); [] when not on the list."""
    for name, entry in (people.get("contributors") or {}).items():
        if name.lower() == (login or "").lower():
            return [a for a in (entry or {}).get("areas", []) if a in AREAS]
    return []


def sign_in(run=subprocess.run, opener=api):
    """(token, login, areas). areas is [] when this user is not a contributor."""
    token = github_token(run)
    login = whoami(token, opener)
    return token, login, areas_for(load_list(token, opener), login)


# ----- what changed -----
def blob_sha(data):
    """The id Git gives a file's contents, so local files compare with GitHub's without downloading them."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def skipped(name):
    return name in SKIP_NAMES or name.endswith(SKIP_SUFFIXES) or ".before-" in name


def local_folder(area, cfg):
    own = cfg.get(f"contrib_{area}_dir")
    if own:
        return own
    ashita = cfg.get("ashita_dir") or ""
    return os.path.join(ashita, *AREAS[area]["live"]) if ashita else ""


def local_files(folder):
    """{"Gambits.lua": (sha, path), "sub/x.lua": ...} for every file worth sending."""
    out = {}
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not skipped(d)]
        for name in files:
            path = os.path.join(root, name)
            if skipped(name) or os.path.getsize(path) > MAX_FILE:
                continue
            rel = os.path.relpath(path, folder).replace(os.sep, "/")
            with open(path, "rb") as handle:
                out[rel] = (blob_sha(handle.read()), path)
    return out


def upstream_files(token, area, opener=api):
    """(commit sha, tree sha, {relative path: blob sha}) for the area on the main branch."""
    ref = opener("GET", f"{UPSTREAM}/git/ref/heads/{BASE_BRANCH}", token)["object"]["sha"]
    tree = opener("GET", f"{UPSTREAM}/git/commits/{ref}", token)["tree"]["sha"]
    prefix = AREAS[area]["repo_path"].rstrip("/") + "/"
    listing = opener("GET", f"{UPSTREAM}/git/trees/{tree}?recursive=1", token)
    files = {item["path"][len(prefix):]: item["sha"] for item in listing.get("tree", [])
             if item.get("type") == "blob" and item["path"].startswith(prefix)}
    return ref, tree, files


def compare(local, remote):
    """{"changed": [...], "added": [...]} (sorted). Files only on GitHub are left alone: nothing is ever deleted."""
    changed = sorted(rel for rel in local if rel in remote and local[rel][0] != remote[rel])
    added = sorted(rel for rel in local if rel not in remote)
    return {"changed": changed, "added": added}


def check(token, area, cfg, opener=api):
    folder = local_folder(area, cfg)
    if not folder or not os.path.isdir(folder):
        raise RuntimeError(f"Can't find your {AREAS[area]['label']} folder ({folder or 'no Ashita folder set'}).")
    local = local_files(folder)
    ref, tree, remote = upstream_files(token, area, opener)
    return {"folder": folder, "local": local, "ref": ref, "tree": tree, "diff": compare(local, remote)}


# ----- sending -----
def ensure_fork(token, login, opener=api, log=print, wait=time.sleep):
    """The contributor's fork (made if they have none) with its main brought up to date where GitHub can."""
    name = UPSTREAM.split("/")[1]
    fork = f"{login}/{name}"
    try:
        found = opener("GET", fork, token)
        if (found.get("parent") or found.get("source") or {}).get("full_name", "").lower() != UPSTREAM.lower():
            raise RuntimeError(f"{fork} exists but is not a fork of {UPSTREAM}.")
    except RuntimeError as e:
        if "404" not in str(e):
            raise
        log("Making your fork on GitHub...")
        fork = opener("POST", f"{UPSTREAM}/forks", token, {"default_branch_only": True})["full_name"]
        for _ in range(30):                         # GitHub makes forks in the background
            try:
                opener("GET", f"{fork}/git/ref/heads/{BASE_BRANCH}", token)
                break
            except RuntimeError:
                wait(2)
    try:
        opener("POST", f"{fork}/merge-upstream", token, {"branch": BASE_BRANCH})
    except RuntimeError:
        pass        # their own main has its own commits: fine, the update branch starts from the main repo anyway
    return fork


def send(token, login, area, found, title, note, opener=api, log=print, now=time.strftime, wait=time.sleep):
    """Puts the changed and new files on a new branch of the contributor's fork and opens a pull request. Returns its URL."""
    files = found["diff"]["changed"] + found["diff"]["added"]
    if not files:
        raise RuntimeError("Nothing to send: your files are the same as the released ones.")
    fork = ensure_fork(token, login, opener, log, wait)
    entries = []
    for rel in files:
        with open(found["local"][rel][1], "rb") as handle:
            data = handle.read()
        log(f"Uploading {rel} ({len(data) // 1024} KB)...")
        blob = opener("POST", f"{fork}/git/blobs", token, {"content": base64.b64encode(data).decode(), "encoding": "base64"})
        entries.append({"path": AREAS[area]["repo_path"].rstrip("/") + "/" + rel, "mode": "100644", "type": "blob",
                        "sha": blob["sha"]})
    tree = opener("POST", f"{fork}/git/trees", token, {"base_tree": found["tree"], "tree": entries})
    message = title.strip() or f"{AREAS[area]['label']} update"
    commit = opener("POST", f"{fork}/git/commits", token, {"message": message + ("\n\n" + note.strip() if note.strip() else ""),
                                                           "tree": tree["sha"], "parents": [found["ref"]]})
    branch = f"contrib/{area}-{now('%Y%m%d-%H%M%S')}"
    opener("POST", f"{fork}/git/refs", token, {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
    lines = [note.strip() or "(no note)", "", "Files:"] + [f"- {AREAS[area]['repo_path']}/{rel}" +
                                                         (" (new)" if rel in found["diff"]["added"] else "") for rel in files]
    lines += ["", f"Sent from the XI: Forever Offline launcher (contributor mode, {AREAS[area]['label']})."]
    pull = opener("POST", f"{UPSTREAM}/pulls", token, {"title": message, "head": f"{login}:{branch}", "base": BASE_BRANCH,
                                                      "body": "\n".join(lines), "maintainer_can_modify": True})
    log(f"Sent: {pull['html_url']}")
    return pull["html_url"]


def my_updates(token, login, opener=api):
    """[(number, title, url)] of this contributor's open pull requests."""
    pulls = opener("GET", f"{UPSTREAM}/pulls?state=open&per_page=50", token)
    return [(p["number"], p["title"], p["html_url"]) for p in pulls if (p.get("user") or {}).get("login", "").lower() == login.lower()]


# ----- the owner's side -----
def open_updates(fetch_json):
    """[(number, title, who, url)] of every open pull request (public, no sign-in needed)."""
    pulls = fetch_json(f"{API}{UPSTREAM}/pulls?state=open&per_page=50")
    return [(p["number"], p["title"], (p.get("user") or {}).get("login", "?"), p["html_url"]) for p in pulls]
