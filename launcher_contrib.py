"""Contributor mode: team members send their changes to the dev for review (no GUI code here).

Who may send what is decided by contributors.json on GitHub (the copy on the main branch, which only the repo owner can
change), never by a local file. A contributor signs in with the GitHub sign-in Git keeps on their PC, the launcher checks
their username against that list, and "Send update" puts the files they pick on a new branch of their own fork and opens
a pull request: launcher/addon/tool files to the kit repo (main), server files (Lua, C++, SQL...) to the server repo (dev).
Nothing reaches players until the owner merges it and publishes an update. No git commands are needed on the
contributor's side: everything goes through the GitHub API.
"""
import base64
import hashlib
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

UPSTREAM = "Hurami89/xi-forever-offline"          # the kit repo: holds contributors.json
BASE_BRANCH = "main"
LIST_PATH = "contributors.json"
REPOS = {
    "kit":    {"repo": UPSTREAM, "branch": BASE_BRANCH},
    "server": {"repo": "Hurami89/xi-forever-offline-server", "branch": "dev"},
}
API = "https://api.github.com/repos/"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# What each area covers: the repo and folder in it, and where the contributor's working copy is on their PC
# ("contrib_<area>_dir" in config.json overrides it). "all" in contributors.json means every area.
#   gambits: the live Ashita addon they test in game (every changed file is found by itself)
#   kit:     their XI: Forever Offline folder (launcher, addons-src, tools...)
#   server:  their server folder (modules, scripts, src, sql...)
# For kit and server only files that already exist on GitHub are compared (an install folder holds far more than the
# repo); new files are added by hand ("Add files...").
AREAS = {
    "gambits": {"label": "Gambits", "short": "Gambits", "repo": "kit", "repo_path": "addons-src/Gambits", "live": ("addons", "Gambits")},
    "kit":     {"label": "Launcher, addons and tools", "short": "Launcher", "repo": "kit", "repo_path": "", "local": "kit"},
    "server":  {"label": "Server (Lua, C++, SQL)", "short": "Server", "repo": "server", "repo_path": "", "local": "server"},
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
                     text=True, errors="replace", creationflags=NO_WINDOW, timeout=180)
        found = dict(line.split("=", 1) for line in (result.stdout or "").splitlines() if "=" in line)
        if result.returncode == 0 and found.get("password"):
            return found["password"]
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        result = run(["gh", "auth", "token"], capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=30)
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
            wanted = (entry or {}).get("areas", [])
            if "all" in wanted:
                return list(AREAS)
            return [a for a in wanted if a in AREAS]
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


def local_folder(area, cfg, kit_dir=""):
    own = cfg.get(f"contrib_{area}_dir")
    if own:
        return own
    where = AREAS[area].get("local")
    if where == "kit":
        return kit_dir
    if where == "server":
        return cfg.get("server_dir") or ""
    ashita = cfg.get("ashita_dir") or ""
    return os.path.join(ashita, *AREAS[area]["live"]) if ashita else ""


def repo_of(area):
    return REPOS[AREAS[area]["repo"]]


def prefix_of(area):
    path = AREAS[area]["repo_path"].strip("/")
    return path + "/" if path else ""


def is_text(data):
    return b"\0" not in data[:8192]


def lf(data):
    return data.replace(b"\r\n", b"\n")


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
    """(commit sha, tree sha, {relative path: blob sha}) for the area on its repo's branch."""
    repo = repo_of(area)
    ref = opener("GET", f"{repo['repo']}/git/ref/heads/{repo['branch']}", token)["object"]["sha"]
    tree = opener("GET", f"{repo['repo']}/git/commits/{ref}", token)["tree"]["sha"]
    prefix = prefix_of(area)
    listing = opener("GET", f"{repo['repo']}/git/trees/{tree}?recursive=1", token)
    files = {item["path"][len(prefix):]: item["sha"] for item in listing.get("tree", [])
             if item.get("type") == "blob" and item["path"].startswith(prefix)}
    return ref, tree, files


def tracked_files(folder, remote):
    """For big folders (kit, server): {rel: (sha, path)} for the files that exist on GitHub, checking the copy with
    Windows line endings turned back too, so a CRLF checkout of an unchanged file doesn't count as changed."""
    out = {}
    for rel, remote_sha in remote.items():
        if skipped(rel.rsplit("/", 1)[-1]):
            continue
        path = os.path.join(folder, *rel.split("/"))
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE:
            continue
        with open(path, "rb") as handle:
            data = handle.read()
        sha = blob_sha(data)
        if sha != remote_sha and b"\r\n" in data and is_text(data) and blob_sha(lf(data)) == remote_sha:
            sha = remote_sha
        out[rel] = (sha, path)
    return out


def compare(local, remote):
    """{"changed": [...], "added": [...]} (sorted). Files only on GitHub are left alone: nothing is ever deleted."""
    changed = sorted(rel for rel in local if rel in remote and local[rel][0] != remote[rel])
    added = sorted(rel for rel in local if rel not in remote)
    return {"changed": changed, "added": added}


def check(token, area, cfg, opener=api, kit_dir=""):
    folder = local_folder(area, cfg, kit_dir)
    if not folder or not os.path.isdir(folder):
        raise RuntimeError(f"Can't find your {AREAS[area]['label']} folder ({folder or 'not set'}).")
    ref, tree, remote = upstream_files(token, area, opener)
    local = local_files(folder) if AREAS[area].get("live") else tracked_files(folder, remote)
    return {"area": area, "folder": folder, "local": local, "ref": ref, "tree": tree, "diff": compare(local, remote),
            "remote": remote}


def add_file(found, path):
    """Adds a file the contributor picked (a new one, usually) to the update. Returns its path in the repo folder."""
    folder = os.path.abspath(found["folder"])
    path = os.path.abspath(path)
    if os.path.commonpath([folder, path]) != folder:
        raise RuntimeError(f"{path} is not inside {folder}: only files from that folder can be sent.")
    rel = os.path.relpath(path, folder).replace(os.sep, "/")
    with open(path, "rb") as handle:
        found["local"][rel] = (blob_sha(handle.read()), path)
    if rel in found["remote"]:
        if rel not in found["diff"]["changed"] and found["local"][rel][0] != found["remote"][rel]:
            found["diff"]["changed"].append(rel)
    elif rel not in found["diff"]["added"]:
        found["diff"]["added"].append(rel)
    return rel


# ----- sending -----
def ensure_fork(token, login, opener=api, log=print, wait=time.sleep, repo=None):
    """The contributor's fork of a repo (made if they have none) with its branch brought up to date where GitHub can."""
    repo = repo or REPOS["kit"]
    upstream, branch = repo["repo"], repo["branch"]
    name = upstream.split("/")[1]
    fork = f"{login}/{name}"
    try:
        found = opener("GET", fork, token)
        if (found.get("parent") or found.get("source") or {}).get("full_name", "").lower() != upstream.lower():
            raise RuntimeError(f"{fork} exists but is not a fork of {upstream}.")
    except RuntimeError as e:
        if "404" not in str(e):
            raise
        log(f"Making your fork of {name} on GitHub...")
        fork = opener("POST", f"{upstream}/forks", token, {"default_branch_only": False})["full_name"]
        for _ in range(30):                         # GitHub makes forks in the background
            try:
                opener("GET", f"{fork}/git/ref/heads/{branch}", token)
                break
            except RuntimeError:
                wait(2)
    try:
        opener("POST", f"{fork}/merge-upstream", token, {"branch": branch})
    except RuntimeError:
        pass        # their own main has its own commits: fine, the update branch starts from the main repo anyway
    return fork


def area_for_path(founds, path):
    """Which checked area a picked file belongs to: the one whose folder holds it (the deepest, so the live Gambits
    folder wins over a parent folder). None when it is in none of them."""
    path = os.path.abspath(path)
    best = None
    for area, found in founds.items():
        folder = os.path.abspath(found["folder"])
        try:
            inside = os.path.commonpath([folder, path]) == folder
        except ValueError:                       # another drive on Windows
            inside = False
        if inside and (best is None or len(folder) > len(os.path.abspath(founds[best]["folder"]))):
            best = area
    return best


def _file_data(token, area, found, rel, opener):
    with open(found["local"][rel][1], "rb") as handle:
        data = handle.read()
    if b"\r\n" in data and is_text(data) and rel in found.get("remote", {}):
        # a Windows checkout: keep the file's line endings as GitHub has them, so only real changes show
        try:
            blob = opener("GET", f"{repo_of(area)['repo']}/git/blobs/{found['remote'][rel]}", token)
            if b"\r\n" not in base64.b64decode(blob.get("content", "")):
                data = lf(data)
        except RuntimeError:
            pass
    return data


def send_all(token, login, founds, chosen, title, note, opener=api, log=print, now=time.strftime, wait=time.sleep):
    """One update from everything the contributor picked: chosen = [(area, relative path), ...] over the checked areas
    (founds = {area: check() result}). Files for the same repo go in one pull request (kit: Gambits + launcher files;
    server: its own, since it is another repo). Returns the pull request URLs."""
    chosen = [(area, rel) for area, rel in chosen if area in founds and rel in founds[area]["local"]]
    if not chosen:
        raise RuntimeError("Nothing to send: pick at least one changed or new file.")
    message = title.strip() or "Update"
    urls = []
    for repo_key, repo in REPOS.items():
        mine = [(area, rel) for area, rel in chosen if AREAS[area]["repo"] == repo_key]
        if not mine:
            continue
        fork = ensure_fork(token, login, opener, log, wait, repo)
        base = founds[mine[0][0]]
        entries, listed, seen = [], [], set()
        for area, rel in sorted(mine, key=lambda x: AREAS[x[0]].get("live") is None):   # the live Gambits copy wins
            path = prefix_of(area) + rel
            if path in seen:
                continue
            seen.add(path)
            data = _file_data(token, area, founds[area], rel, opener)
            log(f"Uploading {path} ({len(data) // 1024} KB)...")
            blob = opener("POST", f"{fork}/git/blobs", token, {"content": base64.b64encode(data).decode(), "encoding": "base64"})
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            listed.append(f"- {path}" + (" (new)" if rel in founds[area]["diff"]["added"] else ""))
        tree = opener("POST", f"{fork}/git/trees", token, {"base_tree": base["tree"], "tree": entries})
        commit = opener("POST", f"{fork}/git/commits", token,
                        {"message": message + ("\n\n" + note.strip() if note.strip() else ""), "tree": tree["sha"],
                         "parents": [base["ref"]]})
        branch = f"contrib/{repo_key}-{now('%Y%m%d-%H%M%S')}"
        opener("POST", f"{fork}/git/refs", token, {"ref": "refs/heads/" + branch, "sha": commit["sha"]})
        body = [note.strip() or "(no note)", "", "Files:"] + listed + ["", "Sent from the XI: Forever Offline launcher (contributor mode)."]
        pull = opener("POST", f"{repo['repo']}/pulls", token, {"title": message, "head": f"{login}:{branch}",
                                                              "base": repo["branch"], "body": "\n".join(body),
                                                              "maintainer_can_modify": True})
        log(f"Sent: {pull['html_url']}")
        urls.append(pull["html_url"])
    return urls


def send(token, login, area, found, title, note, opener=api, log=print, now=time.strftime, wait=time.sleep, files=None):
    """One area only (see send_all). files: the relative paths to send (default: every changed and new file).
    Returns the pull request's URL."""
    if files is None:
        files = found["diff"]["changed"] + found["diff"]["added"]
    return send_all(token, login, {area: found}, [(area, rel) for rel in files], title, note, opener, log, now, wait)[0]


def my_updates(token, login, opener=api):
    """[(number, title, url)] of this contributor's open pull requests, in both repos."""
    out = []
    for repo in REPOS.values():
        pulls = opener("GET", f"{repo['repo']}/pulls?state=open&per_page=50", token)
        out += [(p["number"], p["title"], p["html_url"]) for p in pulls
                if (p.get("user") or {}).get("login", "").lower() == login.lower()]
    return out


# ----- the owner's side -----
def open_updates(fetch_json):
    """[(number, title, who, url)] of every open pull request in both repos (public, no sign-in needed)."""
    out = []
    for repo in REPOS.values():
        pulls = fetch_json(f"{API}{repo['repo']}/pulls?state=open&per_page=50")
        out += [(p["number"], p["title"], (p.get("user") or {}).get("login", "?"), p["html_url"]) for p in pulls]
    return out
