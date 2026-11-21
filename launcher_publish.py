"""Publishing an update for players from the dev PC (the launcher's Settings tab; no GUI code here).

One press, after you confirm: build XI Forever Offline.exe, make the server and player zips, tag both repos and push the
tags (and the server's release branch), then create both GitHub releases and upload the files. GitHub is reached with
the sign-in Git already keeps on this PC (Git Credential Manager), the same one your own git push uses.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

KIT_REPO = "Hurami89/xi-forever-offline"
SERVER_REPO = "Hurami89/xi-forever-offline-server"
API = "https://api.github.com/repos/"
UPLOADS = "https://uploads.github.com/repos/"
# The one-click download (Discord, website): GitHub always serves the newest full release's file under this name at
# https://github.com/Hurami89/xi-forever-offline/releases/latest/download/XI-Forever-Offline.zip
ONE_CLICK_NAME = "XI-Forever-Offline.zip"
ONE_CLICK_URL = f"https://github.com/{KIT_REPO}/releases/latest/download/{ONE_CLICK_NAME}"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def git(folder, *args, check=True):
    out = subprocess.run(["git", "-C", folder] + list(args), capture_output=True, text=True, encoding="utf-8",
                         errors="replace", creationflags=NO_WINDOW if os.name == "nt" else 0)
    if check and out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(out.stderr or out.stdout).strip()[-400:]}")
    return out.stdout.rstrip()          # (not strip: "git status" lines start with a meaningful space)


def last_tag(folder):
    tags = [t for t in git(folder, "tag", "--list", "v*").splitlines() if t.strip()]
    from launcher_update import version_key
    return sorted(tags, key=version_key)[-1] if tags else None


def next_version(tag):
    numbers = [int(x) for x in re.findall(r"\d+", tag or "v0.0.0")] + [0, 0, 0]
    return f"v{numbers[0]}.{numbers[1]}.{numbers[2] + 1}"


def changes(folder, since):
    """One line per commit since the last release (your commit messages)."""
    if not since:
        return []
    log = git(folder, "log", "--no-merges", "--pretty=format:%s", f"{since}..HEAD", check=False)
    return [line for line in log.splitlines() if line.strip() and not line.startswith("FFXI Solo: local server edits")
            and not line.startswith("XI: Forever Offline: local server edits")]


def preflight(kit, server, server_running=False):
    """(problems that stop a publish, warnings to read first)."""
    problems, warnings = [], []
    for label, folder in (("Kit", kit), ("Server", server)):
        dirty = [l for l in git(folder, "status", "--porcelain", "--untracked-files=no", check=False).splitlines() if l.strip()]
        if dirty:
            problems.append(f"{label}: {len(dirty)} changed file(s) are not committed ({', '.join(l[3:] for l in dirty[:4])}...). Commit them first.")
    git(kit, "fetch", "--quiet", "origin", "main", check=False)        # contributions merged on GitHub since your last pull
    behind = git(kit, "rev-list", "--count", "HEAD..origin/main", check=False)
    if behind.isdigit() and int(behind):
        problems.append(f"Kit: {behind} commit(s) on GitHub are not on this PC yet (merged contributions?). "
                        f'Pull them first: git -C "{kit}" pull')
    ahead = git(kit, "rev-list", "--count", "origin/main..HEAD", check=False)
    if ahead.isdigit() and int(ahead):
        problems.append(f"Kit: {ahead} commit(s) are not pushed yet. Push them first.")
    if server_running:
        problems.append("The servers are running: close the game first (the server files are read while packaging).")
    exe = os.path.join(server, "xi_map.exe")
    if os.path.exists(exe):
        built = os.path.getmtime(exe)
        newer = []
        for rel in git(server, "ls-files", "src", "modules", check=False).splitlines():
            if rel.endswith((".cpp", ".h")):
                path = os.path.join(server, *rel.split("/"))
                if os.path.exists(path) and os.path.getmtime(path) > built + 60:
                    newer.append(rel)
        if newer:
            warnings.append(f"{len(newer)} C++ file(s) changed after the last build ({newer[0]}...): rebuild the server first "
                            "(Rebuild server.bat), or players get the old programs.")
    else:
        problems.append("The server is not built (no xi_map.exe).")
    return problems, warnings


def github_token(run=subprocess.run):
    """The GitHub sign-in Git keeps on this PC (git credential fill), so nothing new needs setting up."""
    result = run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True,
                 creationflags=NO_WINDOW if os.name == "nt" else 0, timeout=120)
    found = dict(line.split("=", 1) for line in (result.stdout or "").splitlines() if "=" in line)
    if result.returncode != 0 or not found.get("password"):
        raise RuntimeError("Git has no GitHub sign-in on this PC yet: do one git push to GitHub first (it asks you to sign in).")
    return found["password"]


def api(method, url, token, data=None, body=None, content_type="application/json", length=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "XI-Forever-Offline-publish"}
    if data is not None:
        body = json.dumps(data).encode()
    if body is not None:
        headers["Content-Type"] = content_type
        if length is not None:
            headers["Content-Length"] = str(length)
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=3600) as response:
        text = response.read()
    return json.loads(text) if text else {}


class _ReadProgress:
    """Hands a file to the upload a block at a time and logs every 10%, so a big upload never looks stuck."""

    def __init__(self, handle, total, name, log):
        self.handle, self.total, self.name, self.log = handle, max(total, 1), name, log
        self.done, self.next = 0, 10

    def read(self, size=-1):
        data = self.handle.read(size)
        self.done += len(data)
        percent = self.done * 100 // self.total
        if percent >= self.next:
            self.log(f"   {self.name}: {percent}% ({self.done / 1e6:.0f} of {self.total / 1e6:.0f} MB)")
            self.next = percent // 10 * 10 + 10
        return data


def make_release(repo, tag, title, notes, prerelease, files, token, log=print, opener=api):
    """Creates the release as a draft, uploads the files, then publishes it (so players never see a half-made one)."""
    release = opener("POST", API + repo + "/releases", token, {"tag_name": tag, "name": title, "body": notes,
                                                             "draft": True, "prerelease": bool(prerelease)})
    for item in files:                               # a path, or (path, name to upload it as)
        path, name = item if isinstance(item, tuple) else (item, os.path.basename(item).replace(" ", "."))
        log(f"Uploading {name} ({os.path.getsize(path) / 1e6:.0f} MB)...")
        with open(path, "rb") as handle:
            opener("POST", f"{UPLOADS}{repo}/releases/{release['id']}/assets?name={urllib.request.quote(name)}", token,
                   body=_ReadProgress(handle, os.path.getsize(path), name, log), content_type="application/octet-stream",
                   length=os.path.getsize(path))
    opener("PATCH", API + repo + f"/releases/{release['id']}", token, {"draft": False})
    log(f"Published {repo} {tag}.")
    return release


def stream(cmd, cwd, log):
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                            errors="replace", creationflags=NO_WINDOW if os.name == "nt" else 0)
    for line in proc.stdout:
        if line.strip():
            log(line.rstrip())
    if proc.wait() != 0:
        raise RuntimeError(f"{os.path.basename(cmd[-2] if len(cmd) > 1 else cmd[0])} stopped with an error (see above).")


def publish(kit, server, version, notes, prerelease, log=print, run=subprocess.run, token=None, steps=None):
    """The whole publish. steps: which ones to do (default all): build, package, tag, release."""
    steps = steps or ("build", "package", "tag", "release")
    python = sys.executable
    if "build" in steps:
        log("1/4 Building XI Forever Offline.exe (a few minutes)...")
        stream(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(kit, "build_release.ps1")], kit, log)
    if "package" in steps:
        log("2/4 Making the server and player zips...")
        stream([python, os.path.join(kit, "package_server.py"), version, "--server", server], kit, log)
        stream([python, os.path.join(kit, "package_kit.py"), version], kit, log)
    if "tag" in steps:
        log("3/4 Tagging and pushing...")
        for folder, remote, extra in ((server, "xiforever", ["HEAD:refs/heads/release"]), (kit, "origin", [])):
            git(folder, "tag", "-a", version, "-m", f"XI: Forever Offline {version}")
            for ref in extra + [version]:
                git(folder, "push", remote, ref)
    if "release" in steps:
        log("4/4 Creating the GitHub releases...")
        token = token or github_token(run)
        dist = os.path.join(kit, "dist")
        make_release(SERVER_REPO, version, f"XI: Forever Offline server {version}", notes, prerelease,
                     [os.path.join(dist, f"xi-forever-offline-server-{version}-win64.zip"), os.path.join(dist, "SHA256SUMS.txt")], token, log)
        make_release(KIT_REPO, version, f"XI: Forever Offline {version}", notes, prerelease,
                     [os.path.join(dist, "kit", f"xi-forever-offline-{version}-win64.zip"), os.path.join(dist, "kit", "SHA256SUMS.txt"),
                      (os.path.join(dist, "kit", f"xi-forever-offline-{version}-win64.zip"), ONE_CLICK_NAME)], token, log)
    if "release" in steps:
        prune_dist(kit, version, log)
    log(f"Done: {version} is published. Players' launchers will offer it" + (" to testers (test build)." if prerelease else "."))


def prune_dist(kit, version, log=print, keep=2):
    """(2026-11-21) dist/ kept every release ever built (about 0.45 GB each, 25 GB after two weeks). Once a version is on
    GitHub its zips are only needed there, so only the newest `keep` server zips and player zips stay here."""
    import re as _re
    freed = 0
    for folder, pattern in ((os.path.join(kit, "dist"), r"^xi-forever-offline-server-v(\d+)\.(\d+)\.(\d+)-win64\.zip$"),
                            (os.path.join(kit, "dist", "kit"), r"^xi-forever-offline-v(\d+)\.(\d+)\.(\d+)-win64\.zip$")):
        if not os.path.isdir(folder):
            continue
        found = []
        for name in os.listdir(folder):
            m = _re.match(pattern, name)
            if m:
                found.append((tuple(int(x) for x in m.groups()), name))
        for _, name in sorted(found, reverse=True)[keep:]:
            path = os.path.join(folder, name)
            try:
                freed += os.path.getsize(path)
                os.remove(path)
            except OSError:
                pass
    if freed:
        log(f"Removed old release zips from dist ({freed // (1024 * 1024)} MB); GitHub keeps every release.")
    return freed

