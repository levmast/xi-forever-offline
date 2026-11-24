"""Downloads other people's add-ons and tools from their official releases (thirdparty.json). No GUI code.

Nothing here is rehosted: every file comes from the author's own release page, and the version that was installed is
written to thirdparty-installed.json in the kit folder. Files a download would replace are copied first to
backups\\thirdparty\\<id>-<time>\\, and folders listed in an item's "keep" (your settings) are never overwritten.
"""
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

USER_AGENT = "XI-Forever-Offline-launcher"
API = "https://api.github.com/repos/"
# XIFO_TEST_PLATFORM=windows: the stand-in tests check the Windows paths on a Linux machine
PLATFORM = "windows" if (os.name == "nt" or os.environ.get("XIFO_TEST_PLATFORM") == "windows") else "linux"
NO_WINDOW = 0x08000000 if PLATFORM == "windows" else 0


def for_platform(items, platform=None):
    """The items for this system: an item with "platforms" only where listed; an item's "<platform>" block (e.g.
    "linux": {...}) replaces those fields there ("source" is merged key by key)."""
    platform = platform or PLATFORM
    out = []
    for item in items:
        if item.get("platforms") and platform not in item["platforms"]:
            continue
        override = item.get(platform)
        if isinstance(override, dict):
            item = dict(item)
            for key, value in override.items():
                if key == "source" and isinstance(value, dict):
                    item["source"] = dict(item.get("source", {}), **value)
                else:
                    item[key] = value
        out.append(item)
    return out


def test_builds_on(kit):
    """The 'Get test builds (pre-releases)' setting (config.json in the kit folder)."""
    try:
        with open(os.path.join(kit, "config.json"), encoding="utf-8-sig") as handle:
            return bool(json.load(handle).get("test_builds"))
    except (OSError, ValueError, AttributeError):
        return False


def channel_of(item):
    """'stable' (the default) or 'beta'. A beta item is offered only to players who switched on 'Get test builds' (or who
    already have it installed, so they can still update or remove it), and it follows the newest release including
    pre-releases."""
    return "beta" if item.get("channel") == "beta" else "stable"


def beta_groups(kit):
    """The beta groups the player signed up for ("beta_groups" in config.json, a list or 'a, b'), lower case."""
    try:
        with open(os.path.join(kit, "config.json"), encoding="utf-8-sig") as handle:
            value = json.load(handle).get("beta_groups") or []
    except (OSError, ValueError, AttributeError):
        return set()
    if isinstance(value, str):
        value = value.split(",")
    return {str(v).strip().lower() for v in value if str(v).strip()}


def for_channel(items, kit, test_builds=None):
    """Stable items always. A beta item only with 'Get test builds' on and, when it names a "group", only if the player
    signed up for that group (beta_groups); an item that is installed stays listed so it can be updated or removed."""
    if test_builds is None:
        test_builds = test_builds_on(kit)
    state = load_state(kit)
    groups = beta_groups(kit)
    out = []
    for item in items:
        if channel_of(item) != "beta" or item["id"] in state:
            out.append(item)
        elif test_builds and (not item.get("group") or str(item["group"]).lower() in groups):
            out.append(item)
    return out


def load_manifest(kit, platform=None, test_builds=None):
    with open(os.path.join(kit, "thirdparty.json"), encoding="utf-8-sig") as handle:
        return for_channel(for_platform(json.load(handle)["items"], platform), kit, test_builds)


def state_path(kit):
    return os.path.join(kit, "thirdparty-installed.json")


def load_state(kit):
    try:
        with open(state_path(kit), encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except OSError:
        return {}
    except ValueError:
        # a damaged file: keep it (thirdparty-installed.json.bad) instead of letting the next save overwrite the
        # record of everything that was installed
        try:
            os.replace(state_path(kit), state_path(kit) + ".bad")
        except OSError:
            pass
        return {}


def _save_state(kit, state):
    tmp = state_path(kit) + ".tmp"          # write whole, then swap: a crash never leaves half a file
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2)
    os.replace(tmp, state_path(kit))


def target_root(item, kit, ashita, server=None):
    into = item.get("into", "ashita")
    return ashita if into == "ashita" else server if into == "server" else kit


def _kit_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_ollama(kit=None):
    """ollama(.exe) from PATH or where its installer puts it (Linux: the install folder's ollama/bin), or None."""
    found = shutil.which("ollama")
    if PLATFORM == "linux":
        guesses = (os.path.join(kit or _kit_dir(), "ollama", "bin", "ollama"),)
    else:
        guesses = (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
                   os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"))
    for guess in guesses:
        if not found and os.path.isfile(guess):
            found = guess
    return found


def ollama_models(run=None):
    """The model names Ollama has pulled ([] when Ollama is missing or not running)."""
    import subprocess
    exe = find_ollama()
    if not exe:
        return []
    try:
        out = (run or subprocess.run)([exe, "list"], capture_output=True, text=True, errors="replace", timeout=20, creationflags=NO_WINDOW)
    except Exception:
        return []
    return [line.split()[0] for line in (out.stdout or "").splitlines()[1:] if line.strip()]


def status(item, kit, ashita, state=None, server=None):
    """(installed, version text) from what this launcher recorded, else from the item's check file."""
    if item["source"]["type"] == "ollama_model":
        model = item["source"]["model"]
        have = any(name == model or name == model + ":latest" for name in ollama_models())
        return have, model if have else ""
    if item.get("check_system"):             # something Windows itself keeps (the Visual C++ runtime)
        present, version, _why = system_file_status(item)
        return present, version if present else ""
    state = load_state(kit) if state is None else state
    record = state.get(item["id"])
    root = target_root(item, kit, ashita, server)
    present = bool(item.get("check")) and bool(root) and os.path.exists(os.path.join(root, item["check"]))
    if record and (present or not item.get("check")):
        return True, record.get("version", "")
    if present:
        version = ""
        if item["check"].endswith(".lua"):
            try:
                with open(os.path.join(root, item["check"]), encoding="utf-8", errors="replace") as handle:
                    found = re.search(r"addon\.version\s*=\s*['\"]([^'\"]+)", handle.read(20000))
                version = found.group(1) if found else ""
            except OSError:
                pass
        return True, version or "installed"
    return False, ""


# ----- taking things out again (lilibun, 2026-11-22) -----
def forget(kit, item_id):
    """The launcher no longer counts this download as installed."""
    state = load_state(kit)
    if item_id in state:
        del state[item_id]
        _save_state(kit, state)
        return True
    return False


def place(item):
    """("addon", "cadence"), ("plugin", "nameplate"), or None: which list row a download is, from the file the launcher
    looks for (addons/<name>/<name>.lua or plugins/<name>.dll)."""
    parts = str(item.get("check") or "").replace("\\", "/").split("/")
    if item.get("into", "ashita") != "ashita":
        return None
    if len(parts) == 3 and parts[0] == "addons" and parts[2].lower().endswith(".lua"):
        return "addon", parts[1].lower()
    if len(parts) == 2 and parts[0] == "plugins" and parts[1].lower().endswith(".dll"):
        return "plugin", parts[1][:-4].lower()
    return None


def forget_place(kit, kind, name):
    """After an addon or plugin was removed: the download it came from shows as "not installed" again."""
    try:
        items = load_manifest(kit)
    except Exception:
        return False
    done = False
    for item in items:
        if place(item) == (kind, name.lower()):
            done = forget(kit, item["id"]) or done
    return done


def ollama_models_dir():
    """Where Ollama keeps the models it downloaded."""
    return os.environ.get("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")


def ollama_uninstaller():
    """Ollama's own uninstaller on Windows (next to ollama.exe), or None."""
    if PLATFORM != "windows":
        return None
    exe = find_ollama()
    folders = ([os.path.dirname(exe)] if exe else []) + [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama")]
    for folder in folders:
        guess = os.path.join(folder, "unins000.exe")
        if os.path.isfile(guess):
            return guess
    return None


def remove_model(model, run=None, start=None, wait=5):
    """ollama rm <model>: gives back the disk space of one AI model. Ollama has to be running for it, so it is started
    when it is not. Raises with Ollama's own words when it says no."""
    import subprocess
    exe = find_ollama()
    if not exe:
        raise RuntimeError("Ollama is not installed, so there is no model to remove.")
    run = run or subprocess.run
    if run([exe, "list"], capture_output=True, text=True, errors="replace", timeout=20, creationflags=NO_WINDOW).returncode != 0:
        if start is None:
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW,
                             **({} if os.name == "nt" else {"start_new_session": True}))
        else:
            start()
        time.sleep(wait)
    out = run([exe, "rm", model], capture_output=True, text=True, errors="replace", timeout=120, creationflags=NO_WINDOW)
    if out.returncode != 0:
        said = [l.strip() for l in ((out.stderr or "") + "\n" + (out.stdout or "")).splitlines() if l.strip()]
        raise RuntimeError(f"ollama rm {model} did not work." + (f"\n\nOllama said: {said[-1][:300]}" if said else ""))
    return model


def remove_ollama(kit, models=False, run=None, log=print):
    """Takes Ollama out: on Windows its own uninstaller is started (you finish it in its window); on Linux the copy in
    the install folder is deleted. models=True also deletes every model Ollama downloaded. Returns what was done."""
    import subprocess
    done = []
    if PLATFORM == "windows":
        uninstaller = ollama_uninstaller()
        if uninstaller:
            (run or subprocess.Popen)([uninstaller])
            done.append("uninstaller")
            log("Ollama's own uninstaller is open: finish it there.")
        else:
            log("Ollama's uninstaller was not found: remove Ollama under Windows Settings > Apps > Installed apps.")
    else:
        folder = os.path.join(kit, "ollama")
        if os.path.isdir(folder) and not os.path.islink(folder):
            shutil.rmtree(folder)
            done.append("folder")
            log("Ollama was removed from the install folder.")
    if models:
        folder = ollama_models_dir()
        if os.path.isdir(folder) and not os.path.islink(folder) and os.path.basename(folder.rstrip("/\\")).lower() == "models":
            shutil.rmtree(folder, ignore_errors=True)
            done.append("models")
            log("The downloaded AI models were deleted.")
    forget(kit, "ollama")
    return done


# ----- finding the download -----
_SSL_CONTEXT = None


def file_version(path):
    """(major, minor, build, revision) of a Windows program or DLL, from its version resource, or None. Read straight
    from the file (the fixed version block starts with 0xFEEF04BD), so it needs none of Windows' own functions."""
    import struct
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    at = data.find(b"\xbd\x04\xef\xfe")
    if at < 0 or at + 16 > len(data):
        return None
    _signature, _struct_version, high, low = struct.unpack_from("<IIII", data, at)
    return (high >> 16, high & 0xFFFF, low >> 16, low & 0xFFFF)


def _version_numbers(text):
    return tuple(int(n) for n in re.findall(r"\d+", text or "")[:4])


def system_file_status(item):
    """(ok, version text, why) for an item Windows itself keeps ("check_system": a file that is there once it is
    installed). With "min_version" the file also has to be at least that version; why is '' / 'missing' / 'old'.
    A file whose version can't be read counts as fine (better than asking for an installer again and again)."""
    path = os.path.expandvars(item["check_system"])
    if not os.path.exists(path):
        return False, "", "missing"
    need = _version_numbers(item.get("min_version"))
    have = file_version(path) if need else None
    if have is None:
        return True, "installed", ""
    text = ".".join(str(n) for n in have[:3])
    if have[:len(need)] < need:
        return False, text, "old"
    return True, text, ""


def ensure_system_runtimes(kit, ashita, fetch=None, log=print, run=None, items=None):
    """(Windows) The Microsoft Visual C++ runtimes: the game loader and Ashita use the 32-bit one, the server and the
    database the 64-bit one. (2026-11-22, Leyna Crosse: xiloader.exe stopped inside MSVCP140.dll 14.29 without a word;
    installing the current runtime fixed it. Programs built with Visual Studio 2022 17.10 or newer stop like that on
    a runtime older than 14.40. The launcher used to check only that the 64-bit one existed and never installed the
    32-bit one.) Installs each runtime that is missing or older than its "min_version".
    Returns [(id, 'installed' | 'failed', text)]; nothing is raised, PLAY goes on either way."""
    out = []
    for item in (load_manifest(kit) if items is None else items):
        source = item.get("source", {})
        if not item.get("check_system") or source.get("type") != "installer":
            continue
        ok, have, why = system_file_status(item)
        if ok:
            continue
        log(f"{item['name']}: " + ("not installed" if why == "missing" else
                                   f"version {have} is too old (needs {item.get('min_version')} or newer)")
            + ". Installing it now; Windows may ask for permission...")
        try:
            install(item, kit, ashita, fetch=fetch or _get, log=log, run=run)
            ok, have, why = system_file_status(item)
            problem = "" if ok else "its installer finished but the runtime is still " + ("missing" if why == "missing" else "the old one")
        except Exception as e:
            ok, problem = False, str(e)
        if ok:
            log(f"{item['name']}: installed ({have}).")
            out.append((item["id"], "installed", have))
        else:
            log(f"{item['name']} could not be installed ({problem}). Without it the game or the server can stop as "
                f"soon as it starts. Install it yourself from {source.get('url')} and press PLAY again.")
            out.append((item["id"], "failed", problem))
    return out


def ssl_context():
    """Windows' own certificates plus Mozilla's list (certifi, bundled in the exe). A fresh PC or VM often has not
    fetched GitHub's root certificate into Windows yet, which gave CERTIFICATE_VERIFY_FAILED during setup."""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        import ssl
        context = ssl.create_default_context()
        try:
            import certifi
            context.load_verify_locations(cafile=certifi.where())
        except (ImportError, OSError, ssl.SSLError):
            pass
        _SSL_CONTEXT = context
    return _SSL_CONTEXT


class RateLimited(RuntimeError):
    """The site has stopped answering this connection for a while. GitHub gives about 60 requests an hour to someone who
    is not signed in; the message says when it starts again."""


def _rate_limit_message(error, url):
    """The plain-words message for an HTTP error that means "too many requests", else None."""
    headers = getattr(error, "headers", None) or {}
    remaining, retry = headers.get("X-RateLimit-Remaining"), headers.get("Retry-After")
    if not (error.code == 429 or (error.code == 403 and (remaining == "0" or retry))):
        return None
    reset = headers.get("X-RateLimit-Reset")
    if reset and str(reset).isdigit():
        at = int(reset)
    elif retry and str(retry).isdigit():
        at = time.time() + int(retry)
    else:
        at = None
    who = "GitHub" if "github" in url else "The download site"
    return (f"{who} is limiting this connection for a while (it allows about 60 requests an hour without signing in)."
            + (f" It answers again at {time.strftime('%H:%M', time.localtime(at))}." if at else " Try again in an hour."))


def _open_url(url, timeout=60, headers=None):
    """The open connection to a URL (use it in a `with`). The one place the launcher's downloads go through."""
    request = urllib.request.Request(url, headers=dict({"User-Agent": USER_AGENT}, **(headers or {})))
    try:
        return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())
    except urllib.error.HTTPError as error:
        message = _rate_limit_message(error, url)
        if message:
            raise RateLimited(message) from error
        raise


def _get(url, timeout=60):
    """A small answer (a GitHub page of release data, a checksum file) as bytes. Big files go through stream_to_file."""
    with _open_url(url, timeout, {"Accept": "application/vnd.github+json"}) as response:
        return response.read()


def stream_to_file(url, path, sha256=None, mismatch="The download does not match its published checksum - not installed.",
                   chunk=1 << 20, timeout=600):
    """Saves a download to disk a piece at a time (never the whole file in memory: the server zip is hundreds of MB),
    working out its SHA-256 on the way. The data goes to <path>.part first; when `sha256` is given and does not match,
    the part file is deleted and nothing is left at `path`. Returns the SHA-256 of what was saved."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    part = path + ".part"
    digest = hashlib.sha256()
    try:
        with _open_url(url, timeout) as response, open(part, "wb") as handle:
            while True:
                block = response.read(chunk)
                if not block:
                    break
                handle.write(block)
                digest.update(block)
        actual = digest.hexdigest()
        if sha256 and actual != sha256.lower():
            raise RuntimeError(mismatch)
        os.replace(part, path)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return actual


def resolve(item, fetch=_get):
    """What to download: {"version", "url", "name", "sha256" (or None)}. Raises ValueError for a page-only item."""
    source = item["source"]
    kind = source["type"]
    if kind == "github_release":
        tag = source.get("tag", "latest")
        if tag == "latest" and (source.get("prereleases") or channel_of(item) == "beta"):
            # GitHub's releases/latest skips pre-releases: take the newest published one, test builds included
            releases = [r for r in json.loads(fetch(API + source["repo"] + "/releases?per_page=20")) if not r.get("draft")]
            if not releases:
                raise RuntimeError(f"{item['name']}: no release published yet.")
            release = releases[0]
        else:
            path = "releases/latest" if tag == "latest" else "releases/tags/" + tag
            release = json.loads(fetch(API + source["repo"] + "/" + path))
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        sizes = {a["name"]: int(a.get("size") or 0) for a in release.get("assets", [])}
        if source.get("assets"):                     # (XISpeaks, 2026-11-23) one program in several files, all needed
            sums = {}
            if source.get("sha256sums"):
                for line in fetch(assets[source["sha256sums"]]).decode("utf-8", "replace").splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        sums[os.path.basename(parts[-1].lstrip("*"))] = parts[0].lower()
            parts = []
            for pattern in source["assets"]:
                found_names = sorted(n for n in assets if re.search(pattern, n))
                if not found_names:
                    raise RuntimeError(f"{item['name']}: no file matching {pattern} in release {release.get('tag_name')}")
                name = found_names[0]
                if source.get("sha256sums") and name not in sums:
                    raise RuntimeError(f"{item['name']}: {name} is not listed in {source['sha256sums']}")
                parts.append({"name": name, "url": assets[name], "sha256": sums.get(name), "size": sizes.get(name, 0)})
            return {"version": release.get("tag_name", tag), "url": parts[0]["url"], "name": parts[0]["name"],
                    "sha256": parts[0]["sha256"], "parts": parts}
        names = [n for n in assets if re.search(source["asset"], n)]
        if not names:
            raise RuntimeError(f"{item['name']}: no file matching {source['asset']} in release {release.get('tag_name')}")
        name = sorted(names)[0]
        digest = digest512 = None
        if source.get("sha256sums"):
            if source["sha256sums"] not in assets:
                raise RuntimeError(f"{item['name']}: release {release.get('tag_name')} has no {source['sha256sums']} "
                                   f"to check {name} against - not installed.")
            sums = fetch(assets[source["sha256sums"]]).decode("utf-8", "replace")
            for line in sums.splitlines():
                parts = line.split()
                if len(parts) >= 2 and os.path.basename(parts[-1].lstrip("*")) == name:
                    digest = parts[0].lower()
            if not digest:
                raise RuntimeError(f"{item['name']}: {name} is not listed in {source['sha256sums']}")
        # every checksum there is for this file: the author's list, GitHub's own record of the upload (the "digest" it
        # keeps for each release file), and a pin in thirdparty.json. They must agree; the first one found is checked.
        listed = next((a.get("digest") for a in release.get("assets", []) if a.get("name") == name), None)
        known = [d.lower() for d in (digest, listed[7:] if str(listed).lower().startswith("sha256:") else None,
                                     source.get("sha256")) if d]
        if len(set(known)) > 1:
            raise RuntimeError(f"{item['name']}: the checksums for {name} do not agree with each other - not installed.")
        digest = known[0] if known else None
        if source.get("sha512sums"):                 # GE-Proton: one <name>.sha512sum file per download
            sums_names = [n for n in assets if re.search(source["sha512sums"], n)]
            for sums_name in sums_names:
                for line in fetch(assets[sums_name]).decode("utf-8", "replace").splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and os.path.basename(parts[-1].lstrip("*")) == name:
                        digest512 = parts[0].lower()
            if not digest512:
                raise RuntimeError(f"{item['name']}: no SHA-512 checksum published for {name}")
        found = {"version": release.get("tag_name", tag), "url": assets[name], "name": name, "sha256": digest}
        if digest512:
            found["sha512"] = digest512
        return found
    if kind == "github_archive":
        ref = source["ref"]
        url = f"https://github.com/{source['repo']}/archive/{ref}.zip"
        return {"version": ref, "url": url, "name": source["repo"].split("/")[-1] + "-" + ref + ".zip",
                "sha256": (source.get("sha256") or "").lower() or None}      # GitHub builds these on the spot: no list, only a pin
    if kind == "kit":                              # shipped inside the kit folder (no download)
        return {"version": source["version"], "url": "", "name": source["path"], "sha256": source.get("sha256"),
                "local": source["path"]}
    if kind == "ollama_model":
        return {"version": source["model"], "url": "", "name": source["model"], "sha256": None}
    if kind in ("url", "installer"):
        return {"version": time.strftime("%Y-%m-%d"), "url": source["url"], "name": source["url"].rsplit("/", 1)[-1],
                "sha256": (source.get("sha256") or "").lower() or None}
    raise ValueError(f"{item['name']} is downloaded from its page by hand: {source.get('url', item.get('homepage'))}")


def download(item, kit, found, fetch=_get):
    """Downloads into downloads\\<id>\\ and checks the SHA-256 when the release lists one. Returns the file path."""
    if found.get("local"):                         # a folder inside the kit: zipped in memory, checked like a download
        import io
        base = os.path.join(kit, found["local"])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for top, _dirs, files in os.walk(base):
                for name in files:
                    full = os.path.join(top, name)
                    archive.write(full, os.path.relpath(full, base).replace("\\", "/"))
        if found.get("sha256"):
            dll = [n for n in zipfile.ZipFile(buf).namelist() if n.lower().endswith(".dll")]
            actual = hashlib.sha256(open(os.path.join(base, dll[0]), "rb").read()).hexdigest() if dll else ""
            if actual != found["sha256"]:
                raise RuntimeError(f"{item['name']}: the file in the kit does not match its checksum - not installed.")
        path = os.path.join(kit, "downloads", item["id"], item["id"] + ".zip")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(buf.getvalue())
        found["sha256_actual"] = found.get("sha256")
        return path
    folder = os.path.join(kit, "downloads", item["id"])
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, found["name"])
    if fetch is _get:                              # the real thing: straight to disk, a piece at a time
        found["sha256_actual"] = stream_to_file(found["url"], path, found.get("sha256"),
                                                  mismatch=f"{item['name']}: the download does not match its published checksum - not installed.")
        return path
    data = fetch(found["url"], timeout=600)        # a stand-in fetch (the tests) hands over the bytes
    actual = hashlib.sha256(data).hexdigest()
    if found.get("sha256") and actual != found["sha256"]:
        raise RuntimeError(f"{item['name']}: the download does not match its published checksum - not installed.")
    with open(path, "wb") as handle:
        handle.write(data)
    found["sha256_actual"] = actual
    return path


# ----- putting the files in place -----
def plan(item, names):
    """Where each file in the download goes: [(name in the download, relative destination)]."""
    out = []
    for name in names:
        if name.endswith("/"):
            continue
        for source, dest in item.get("files", []):
            if source.startswith("*/"):              # "*/x/" = x/ inside the download's single top folder
                head, _, rest = name.partition("/")
                pattern = source[2:]
                if not rest:
                    continue
                if pattern == "":
                    out.append((name, dest + rest))
                    break
                if rest.startswith(pattern):
                    out.append((name, dest + rest[len(pattern):]))
                    break
            elif source.endswith("/"):
                if name.startswith(source):
                    out.append((name, dest + name[len(source):]))
                    break
            elif fnmatch.fnmatch(name, source) or name == source:
                out.append((name, dest))
                break
    for _name, dest in out:
        parts = dest.replace("\\", "/").split("/")
        if dest.startswith(("/", "\\")) or ":" in dest or ".." in parts:
            raise RuntimeError(f"{item['name']}: refusing to write outside its folder ({dest})")
    return out


# --- Choosing the AI model (Meli, 2026-11-18) -------------------------------------------------------------------
# Squad chat and the crowd/bot chat both read "model" from squad-chat/config.json, so that is the one place to set it.
SUGGESTED_MODELS = [
    ("gemma4:12b", "default: good chat, about 8 GB of video memory"),
    # (2026-11-22, Yumainai: "ollama pull gemma4:4b failed") there is no gemma4:4b; the small ones are e2b and e4b
    ("gemma4:e2b", "lighter: about 5 GB, for smaller graphics cards"),
    ("qwen3:8b", "about 5 GB"),
    ("qwen3:14b", "about 9 GB, needs a strong graphics card"),
    ("mistral-nemo:latest", "about 7 GB"),
    ("llama3.1:8b", "about 5 GB"),
]


def chat_config_path(kit=None):
    return os.path.join(kit or _kit_dir(), "squad-chat", "config.json")


def chat_model(kit=None):
    """The model squad chat and the crowd chat use now (gemma4:12b when none is set)."""
    try:
        with open(chat_config_path(kit), encoding="utf-8") as f:
            return json.load(f).get("model") or "gemma4:12b"
    except (OSError, ValueError):
        return "gemma4:12b"


def set_chat_model(model, kit=None):
    """Saves the model name in squad-chat/config.json, keeping everything else in it. The chat helpers pick it up
    at the next PLAY (until it is pulled they keep using the fallback model)."""
    model = (model or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-/]*(:[A-Za-z0-9._\-]+)?", model):
        raise ValueError(f"'{model}' is not a model name Ollama understands (like gemma4:12b).")
    path = chat_config_path(kit)
    data = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    data["model"] = model
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)
    return model


def import_gguf(gguf_path, name=None, log=print, run=None):
    """Makes an Ollama model from your own .gguf file (ollama create with a one-line Modelfile) and returns its name.
    The Modelfile is kept in ai-models/ beside the kit; the .gguf stays where it is."""
    import subprocess
    exe = find_ollama()
    if not exe:
        raise RuntimeError("Ollama is not installed yet (OPTIONS > Get more > Ollama).")
    if not (os.path.isfile(gguf_path) and gguf_path.lower().endswith(".gguf")):
        raise ValueError("Pick a .gguf file.")
    base = name or re.sub(r"[^a-z0-9._-]+", "-", os.path.splitext(os.path.basename(gguf_path))[0].lower()).strip("-.") or "my-model"
    name = base if ":" in base else base + ":latest"
    folder = os.path.join(_kit_dir(), "ai-models")
    os.makedirs(folder, exist_ok=True)
    modelfile = os.path.join(folder, re.sub(r"[:/]", "_", name) + ".Modelfile")
    with open(modelfile, "w", encoding="utf-8") as f:
        f.write(f'FROM "{os.path.abspath(gguf_path)}"\n')
    log(f"Importing {os.path.basename(gguf_path)} into Ollama as {name} (this can take a few minutes)...")
    out = (run or subprocess.run)([exe, "create", name, "-f", modelfile], capture_output=True, text=True, errors="replace",
                                  creationflags=NO_WINDOW)
    if out.returncode != 0:
        raise RuntimeError(((out.stderr or out.stdout or "").strip()[-300:]) or "ollama create failed")
    log(f"AI model {name} is ready.")
    return name


def pull_model(model, log=print, popen=None):
    """ollama pull <model>, starting Ollama first when it is not running. Reports progress about every 20 seconds."""
    import subprocess
    exe = find_ollama()
    if not exe:
        raise RuntimeError("Ollama is not installed yet (install it first).")
    if not ollama_models() and subprocess.run([exe, "list"], capture_output=True, creationflags=NO_WINDOW).returncode != 0:
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW,
                         **({} if os.name == "nt" else {"start_new_session": True}))
        time.sleep(5)
    proc = (popen or subprocess.Popen)([exe, "pull", model], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       creationflags=NO_WINDOW)
    last, buffer = 0.0, b""
    while True:
        chunk = proc.stdout.read(256)
        if not chunk:
            break
        buffer = (buffer + chunk)[-400:]
        if time.time() - last > 20:
            text = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buffer.decode("utf-8", "replace")).replace("\r", "\n")
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if lines:
                log(f"AI model {model}: {lines[-1][:90]}")
            last = time.time()
    if proc.wait() != 0:
        # what Ollama itself said last (a name that doesn't exist, an Ollama that is too old for the model, no room)
        said = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buffer.decode("utf-8", "replace")).replace("\r", "\n")
        said = [l.strip() for l in said.splitlines() if l.strip()]
        raise RuntimeError(f"ollama pull {model} failed (code {proc.returncode})."
                           + (f"\n\nOllama said: {said[-1][:300]}" if said else ""))
    log(f"AI model {model} is ready.")


def download_file(url, path, log=print, sha256=None, sha512=None, fetch=None, chunk=1 << 20):
    """A big download straight to disk (resumed if it stopped: <name>.part), then checked against its published
    checksum; a file that doesn't match is deleted. With a test `fetch` the data comes from it instead."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if fetch is not None and fetch is not _get:
        with open(path, "wb") as handle:
            handle.write(fetch(url, timeout=1800))
    elif not os.path.exists(path):
        part = path + ".part"
        have = os.path.getsize(part) if os.path.exists(part) else 0
        with _open_url(url, 60, {"Range": f"bytes={have}-"} if have else None) as response:
            if have and getattr(response, "status", 200) != 206:
                have = 0
            total = have + int(response.headers.get("Content-Length") or 0)
            mark, done = 0, have
            with open(part, "ab" if have else "wb") as handle:
                while True:
                    data = response.read(chunk)
                    if not data:
                        break
                    handle.write(data)
                    done += len(data)
                    if total and done * 10 // total > mark:
                        mark = done * 10 // total
                        log(f"   {os.path.basename(path)}: {done * 100 // total}% of {total / 2**20:.0f} MB")
        os.replace(part, path)
    for want, algo in ((sha256, hashlib.sha256), (sha512, hashlib.sha512)):
        if want:
            digest = algo()
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
            if digest.hexdigest() != want.lower():
                os.remove(path)
                raise RuntimeError(f"{os.path.basename(path)} does not match its published checksum - deleted, not installed.")
    return path


def extract_tree(archive_path, dest):
    """Unpacks a whole .tar(.gz/.xz) into dest as it is (programs keep their run permission, links stay links).
    Anything that would land outside dest is refused."""
    os.makedirs(dest, exist_ok=True)
    real = os.path.realpath(dest)
    if archive_path.lower().endswith(".zst"):
        try:
            tarfile.open(archive_path, "r:zst").close()       # Python 3.14 reads zstd itself
        except (tarfile.TarError, ValueError, ImportError, AttributeError):
            return _extract_with_system_tar(archive_path, dest)
        mode = "r:zst"
    else:
        mode = "r:*"
    with tarfile.open(archive_path, mode) as archive:
        members = archive.getmembers()
        for member in members:
            # (the folder of the entry, not the entry itself: on a second unpack a link already on disk would be
            #  followed, and its target checked from the wrong folder: Sunie, GE-Proton winexinput.sys, 2026-11-18)
            parts = member.name.rstrip("/").split("/")
            target = os.path.join(os.path.realpath(os.path.join(dest, *parts[:-1])), parts[-1]) if parts[-1] else real
            if member.name.startswith("/") or ".." in member.name.split("/") or not (target == real or target.startswith(real + os.sep)):
                raise RuntimeError(f"refusing a path outside the folder: {member.name}")
            if member.issym() or member.islnk():
                link = os.path.join(os.path.dirname(target), member.linkname) if member.issym() else os.path.join(dest, member.linkname)
                if member.linkname.startswith("/") or not os.path.realpath(link).startswith(real + os.sep):
                    raise RuntimeError(f"refusing a link outside the folder: {member.name}")
        try:
            archive.extractall(dest, members=members, filter="tar")
        except TypeError:                                       # Python before 3.12: checked above already
            archive.extractall(dest, members=members)


def _extract_with_system_tar(archive_path, dest):
    """A .tar.zst with a Python that can't read zstd: the system's tar does it (SteamOS and most distros have zstd)."""
    import subprocess
    listing = subprocess.run(["tar", "--zstd", "-tf", archive_path], capture_output=True, text=True, errors="replace")
    if listing.returncode != 0:
        raise RuntimeError("This system can't unpack .tar.zst files (install zstd).")
    for name in listing.stdout.splitlines():
        if name.startswith("/") or ".." in name.split("/"):
            raise RuntimeError(f"refusing a path outside the folder: {name}")
    done = subprocess.run(["tar", "--zstd", "--no-same-owner", "-xf", archive_path, "-C", dest], capture_output=True, text=True, errors="replace")
    if done.returncode != 0:
        raise RuntimeError("Unpacking failed: " + (done.stderr or "")[-300:])


def extract_zip(archive_path, dest, keep=(), log=print):
    """Unpacks a .zip into dest file by file (a big archive never sits in memory). Paths outside dest are refused;
    files under a `keep` folder that already exist (your own settings) are left alone. Returns (written, kept)."""
    real = os.path.realpath(dest)
    written = kept = 0
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            parts = name.split("/")
            if name.startswith("/") or ".." in parts or ":" in parts[0]:
                raise RuntimeError(f"refusing a path outside the folder: {info.filename}")
            target = os.path.realpath(os.path.join(dest, *[p for p in parts if p]))
            if not target.startswith(real + os.sep):
                raise RuntimeError(f"refusing a path outside the folder: {info.filename}")
            if name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            if keep and name.startswith(keep) and os.path.exists(target):
                kept += 1
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as source, open(target + ".part", "wb") as out:
                shutil.copyfileobj(source, out, 1 << 20)
            os.replace(target + ".part", target)
            written += 1
    return written, kept


def apply_fixups(item, root, log=print):
    """(2026-11-23) Small fixes to another author's files after they are unpacked: item "fixups" = [[file, old text, new
    text, why], ...], each one only where the old text is found (an author's newer release that fixed it is left alone).
    XISpeaks beta 4: its NPC list window called imgui.BeginChild(..., true), which this Ashita refuses (krazy)."""
    for fix in item.get("fixups", []):
        try:
            rel, old, new = fix[0], fix[1], fix[2]
        except (IndexError, TypeError):
            continue
        parts = rel.replace("\\", "/").split("/")
        if rel.startswith("/") or ".." in parts:
            continue
        path = os.path.join(root, *parts)
        try:
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except OSError:
            continue
        if old in text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text.replace(old, new))
            log(f"{item['name']}: fixed {rel} ({fix[3] if len(fix) > 3 else 'a small fix'}).")


def check_free_space(item, folder, parts, free=None):
    """Big multi-file downloads: room for everything unpacked plus the biggest download (each is deleted after it is
    unpacked) plus 1 GB to spare. Raises with a plain message when there is not."""
    total = sum(p.get("size", 0) for p in parts)
    need = int(total * item.get("unpacked_factor", 1.1)) + max([p.get("size", 0) for p in parts] or [0]) + (1 << 30)
    if free is None:
        probe = folder
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        free = shutil.disk_usage(probe or ".").free
    if total and free < need:
        raise RuntimeError(f"not enough free disk space: it needs about {need / 2**30:.1f} GB, "
                           f"and {free / 2**30:.1f} GB is free on that drive.")
    return need


def _signature_of(path):
    """(status, who signed it) of a Windows program, from Windows itself (Get-AuthenticodeSignature), or None when
    Windows' answer could not be had."""
    import subprocess
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:XIFO_CHECK_PATH; "
              "[Console]::Out.WriteLine([string]$s.Status); "
              "if ($s.SignerCertificate) { [Console]::Out.WriteLine($s.SignerCertificate.Subject) }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True,
                             errors="replace", timeout=120, creationflags=NO_WINDOW, env=dict(os.environ, XIFO_CHECK_PATH=path))
    except Exception:
        return None
    lines = [l.strip() for l in (out.stdout or "").splitlines() if l.strip()]
    if out.returncode != 0 or not lines:
        return None
    return lines[0], (lines[1] if len(lines) > 1 else "")


def check_signature(item, path, log=print):
    """(Windows) An installer item that names its "signer" in thirdparty.json (the company that signs it) is only started
    when Windows says its signature is valid and is that company's. Nothing is checked when no signer is named, and when
    Windows can't be asked the installer goes ahead with a note, so a broken check never stops the Visual C++ runtime."""
    signer = item["source"].get("signer")
    if not signer or PLATFORM != "windows":
        return True
    found = _signature_of(path)
    if found is None:
        log(f"{item['name']}: could not ask Windows who signed this installer, starting it without that check.")
        return True
    status, subject = found
    if status != "Valid" or signer.lower() not in subject.lower():
        raise RuntimeError(f"{item['name']}: the installer is not signed by {signer} "
                           f"(Windows says: {status}{', ' + subject if subject else ''}) - not started.")
    return True


def clean_download(kit, item_id):
    """Deletes downloads/<id>/ (the file an install fetched and has used). Returns the bytes freed."""
    base = os.path.realpath(os.path.join(kit, "downloads"))
    folder = os.path.realpath(os.path.join(base, item_id))
    if not item_id or os.path.dirname(folder) != base or not os.path.isdir(folder):
        return 0
    freed = sum(os.path.getsize(os.path.join(top, name)) for top, _dirs, names in os.walk(folder) for name in names
                if os.path.exists(os.path.join(top, name)))
    shutil.rmtree(folder, ignore_errors=True)
    return freed


def prune_downloads(kit, days=7, log=print, now=None):
    """What an install left behind (an installer that was still running when the launcher stopped looking at it, a
    download that broke): every downloads/<id>/ folder nothing has touched for `days` days is deleted. The folder
    downloads/updates is the launcher's own update files and is tidied by launcher_update. Returns the bytes freed."""
    base = os.path.join(kit, "downloads")
    if not os.path.isdir(base):
        return 0
    limit = (now or time.time()) - days * 86400
    freed = 0
    for name in os.listdir(base):
        folder = os.path.join(base, name)
        if name == "updates" or not os.path.isdir(folder) or os.path.islink(folder):
            continue
        stamps = [os.path.getmtime(os.path.join(top, n)) for top, _dirs, names in os.walk(folder) for n in names]
        if stamps and max(stamps) > limit:
            continue
        freed += clean_download(kit, name)
        if os.path.isdir(folder) and not os.listdir(folder):      # an empty folder is only clutter
            os.rmdir(folder)
    if freed:
        log(f"Removed old downloads ({max(1, freed // (1024 * 1024))} MB).")
    return freed


def remove_stale(item, kit, root, state, wanted, log=print, stamp=None):
    """An update used to leave behind the files the old version had and the new one does not (a renamed or dropped Lua
    file keeps loading, or keeps showing in the addon's folder). Removes the files an earlier install of this item put in
    place (the list kept in thirdparty-installed.json) that are not in `wanted` (the files of the version just installed).
    Never touches: a file another download also installed, a file inside the item's kept (settings) folders, anything
    outside the item's folder. Every file is copied to backups/thirdparty/<id>-<time>-old/ first.
    Returns the list of files removed."""
    old = (state.get(item["id"]) or {}).get("files") or []
    if not old or not root:
        return []
    norm = lambda path: str(path).replace("\\", "/")
    wanted = {norm(w) for w in wanted}
    keep = tuple(norm(k) for k in item.get("keep", []))
    replace = tuple(norm(r) for r in item.get("replace", []))
    others = {norm(f) for other, record in state.items() if other != item["id"] and isinstance(record, dict)
              for f in record.get("files", [])}
    real = os.path.realpath(root)
    backup = os.path.join(kit, "backups", "thirdparty", f"{item['id']}-{stamp or time.strftime('%Y%m%d-%H%M%S')}-old")
    removed, folders = [], set()
    for rel in old:
        rel = norm(rel)
        parts = rel.split("/")
        full = os.path.realpath(os.path.join(root, *parts))
        if rel in wanted or rel in others or ".." in parts or not full.startswith(real + os.sep):
            continue
        if keep and rel.startswith(keep) and not (replace and rel.startswith(replace)):
            continue
        if not os.path.isfile(full):
            continue
        os.makedirs(os.path.dirname(os.path.join(backup, *parts)), exist_ok=True)
        shutil.copy2(full, os.path.join(backup, *parts))
        os.remove(full)
        removed.append(rel)
        folders.add(os.path.dirname(full))
    for folder in sorted(folders, key=len, reverse=True):          # folders that are empty now
        while folder.startswith(real + os.sep):
            try:
                os.rmdir(folder)
            except OSError:
                break
            folder = os.path.dirname(folder)
    if removed:
        log(f"{item['name']}: {len(removed)} file(s) the old version had and this one does not were removed (copies saved in {backup}).")
    return removed


def install(item, kit, ashita, fetch=_get, log=print, server=None, run=None, keep_download=False, remove_old=True):
    """Downloads and installs one item. Returns the version installed. The downloaded file is deleted afterwards
    (keep_download=True keeps it); an installer that is still open on the player's screen is left alone. An update also
    removes the files the old version had and the new one does not (remove_old=False leaves them)."""
    started = []
    try:
        return _install(item, kit, ashita, fetch, log, server, run, started, remove_old)
    finally:
        if not keep_download and not started:
            try:
                clean_download(kit, item["id"])
            except OSError:
                pass


def _install(item, kit, ashita, fetch, log, server, run, started, remove_old=True):
    if item["source"]["type"] == "ollama_model":
        pull_model(item["source"]["model"], log=log)
        return item["source"]["model"]
    root = target_root(item, kit, ashita, server)
    if not root:
        raise RuntimeError("Set the " + ("server" if item.get("into") == "server" else "Ashita") + " folder first.")
    found = resolve(item, fetch)
    if item.get("unpack") == "zips" and found.get("parts"):     # several big .zip files, streamed to disk one by one
        dest = os.path.join(root, *item.get("unpack_to", "").split("/")) if item.get("unpack_to") else root
        check_free_space(item, dest, found["parts"])
        keep = tuple(item.get("keep", []))
        written = kept = 0
        for number, part in enumerate(found["parts"], 1):
            log(f"{item['name']}: downloading part {number} of {len(found['parts'])}, {part['name']}"
                + (f" ({part['size'] / 2**20:.0f} MB)" if part.get("size") else "") + "...")
            path = download_file(part["url"], os.path.join(kit, "downloads", item["id"], part["name"]), log=log,
                                 sha256=part.get("sha256"), fetch=None if fetch is _get else fetch)
            log(f"{item['name']}: unpacking part {number}...")
            w, k = extract_zip(path, dest, keep=keep, log=log)
            written, kept = written + w, kept + k
            try:
                os.remove(path)
            except OSError:
                pass
        log(f"{item['name']}: {written} file(s) installed" + (f", {kept} of your own kept" if kept else "") + ".")
        apply_fixups(item, root, log)
        state = load_state(kit)
        state[item["id"]] = {"version": found["version"], "file": ", ".join(p["name"] for p in found["parts"]),
                             "sha256": None, "from": found["url"], "at": time.strftime("%Y-%m-%d %H:%M")}
        _save_state(kit, state)
        return found["version"]
    log(f"{item['name']}: downloading {found['name']} ({found['version']})...")
    if item.get("unpack") == "tree":                # big Linux tools (Proton, umu, Ollama): streamed, unpacked whole
        path = download_file(found["url"], os.path.join(kit, "downloads", item["id"], found["name"]), log=log,
                             sha256=found.get("sha256"), sha512=found.get("sha512"),
                             fetch=None if fetch is _get else fetch)
        dest = os.path.join(root, *item.get("unpack_to", "").split("/")) if item.get("unpack_to") else root
        log(f"{item['name']}: unpacking...")
        extract_tree(path, dest)
        found["sha256_actual"] = found.get("sha256") or found.get("sha512")
        if item.get("delete_download", True):
            try:
                os.remove(path)
            except OSError:
                pass
        log(f"{item['name']}: installed.")
        state = load_state(kit)
        state[item["id"]] = {"version": found["version"], "file": found["name"], "sha256": found.get("sha256_actual"),
                             "from": found["url"], "at": time.strftime("%Y-%m-%d %H:%M")}
        _save_state(kit, state)
        return found["version"]
    path = download(item, kit, found, fetch)
    if not found.get("sha256") and not found.get("local"):
        log(f"{item['name']}: the author publishes no checksum for this file, so it could not be checked against one. "
            f"Its SHA-256 ({(found.get('sha256_actual') or '')[:16]}...) is saved in thirdparty-installed.json.")
    if item["source"]["type"] == "installer":
        check_signature(item, path, log=log)
        log(f"{item['name']}: starting its installer.")
        if item["source"].get("wait"):             # quiet installers (Visual C++): wait until done
            import subprocess
            result = (run or subprocess.run)([path] + list(item["source"].get("args", [])))
            if result.returncode not in (0, 1638, 3010):    # 1638 = a newer one is installed, 3010 = done, restart later
                raise RuntimeError(f"{item['name']}: the installer stopped with code {result.returncode}.")
        elif os.name == "nt":
            os.startfile(path)                     # Windows: the installer asks the player itself
            started.append(path)                   # (it is still running: its file stays until the next tidy)
        else:
            raise RuntimeError(f"{item['name']} is a Windows installer.")
    else:
        modes = {}
        archive = None
        if zipfile.is_zipfile(path):
            archive = zipfile.ZipFile(path)
            names = archive.namelist()
            read = archive.read
        elif tarfile.is_tarfile(path):                     # Linux packages (the server): files keep their run permission
            archive = tarfile.open(path, "r:*")
            members = {m.name: m for m in archive.getmembers() if m.isfile()}
            names = list(members)
            modes = {name: m.mode for name, m in members.items()}
            read = lambda name: archive.extractfile(members[name]).read()
        else:
            names = [found["name"]]

            def read(_name):
                with open(path, "rb") as single:
                    return single.read()
        moves = plan(item, names)
        if not moves:
            if archive is not None:
                archive.close()
            raise RuntimeError(f"{item['name']}: nothing in {found['name']} matched where it should go.")
        keep = tuple(item.get("keep", []))
        # files inside a kept folder that belong to the tool itself and must follow its version (Ashita's own memory
        # offsets and pointers in config/ashita/ashita.*.ini; the player's custom.*.ini stay)
        replace = tuple(item.get("replace", []))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(kit, "backups", "thirdparty", f"{item['id']}-{stamp}")
        written = kept = 0
        placed = []
        for name, rel in moves:
            dest = os.path.join(root, rel)
            if os.path.exists(dest):
                if keep and rel.startswith(keep) and not (replace and rel.replace("\\", "/").startswith(replace)):
                    kept += 1
                    continue
                os.makedirs(os.path.dirname(os.path.join(backup, rel)), exist_ok=True)
                shutil.copy2(dest, os.path.join(backup, rel))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as handle:
                handle.write(read(name))
            if modes.get(name, 0) & 0o111:
                os.chmod(dest, 0o755)
            written += 1
            placed.append(rel.replace("\\", "/"))
        if archive is not None:
            archive.close()                   # (a zip left open stays locked on Windows)
        log(f"{item['name']}: {written} file(s) installed" + (f", {kept} of your own kept" if kept else "")
            + (f"; replaced files saved in {backup}" if os.path.isdir(backup) else "") + ".")
    state = load_state(kit)
    record = {"version": found["version"], "file": found["name"], "sha256": found.get("sha256_actual"),
              "from": found["url"], "at": time.strftime("%Y-%m-%d %H:%M")}
    if item["source"]["type"] != "installer":
        # every file this item put in its folder (an update adds to the list), so uninstall() can take them out again
        before = set((state.get(item["id"]) or {}).get("files", []))
        gone = set()
        if remove_old and before:
            gone = set(remove_stale(item, kit, root, state, [rel for _name, rel in moves], log=log, stamp=stamp))
        record["files"] = sorted(set(placed) | (before - gone))
    state[item["id"]] = record
    _save_state(kit, state)
    return found["version"]


def uninstall(item, kit, ashita, server=None, log=print):
    """Removes the files this launcher installed for an item (the list kept in thirdparty-installed.json), after copying
    them to backups/thirdparty/<id>-uninstall-<time>/. Settings kept from your own folders are not on the list, so they stay.
    Returns the number of files removed."""
    if item.get("required"):
        raise RuntimeError(f"{item['name']} is needed by the launcher and can't be removed here.")
    state = load_state(kit)
    files = (state.get(item["id"]) or {}).get("files")
    if not files:
        raise RuntimeError(f"{item['name']}: no list of installed files was kept (it was installed by hand or by an older "
                           "launcher). Delete its folder yourself.")
    root = target_root(item, kit, ashita, server)
    if not root:
        raise RuntimeError("Set the " + ("server" if item.get("into") == "server" else "Ashita") + " folder first.")
    real = os.path.realpath(root)
    backup = os.path.join(kit, "backups", "thirdparty", f"{item['id']}-uninstall-{time.strftime('%Y%m%d-%H%M%S')}")
    removed, folders = 0, set()
    for rel in files:
        parts = rel.split("/")
        full = os.path.realpath(os.path.join(root, *parts))
        if ".." in parts or not full.startswith(real + os.sep):
            raise RuntimeError(f"{item['name']}: refusing to remove outside its folder ({rel})")
        if not os.path.isfile(full):
            continue
        os.makedirs(os.path.dirname(os.path.join(backup, *parts)), exist_ok=True)
        shutil.copy2(full, os.path.join(backup, *parts))
        os.remove(full)
        removed += 1
        folders.add(os.path.dirname(full))
    for folder in sorted(folders, key=len, reverse=True):          # empty folders the item left behind
        while folder.startswith(real + os.sep):
            try:
                os.rmdir(folder)
            except OSError:
                break
            folder = os.path.dirname(folder)
    del state[item["id"]]
    _save_state(kit, state)
    log(f"{item['name']}: {removed} file(s) removed" + (f"; copies saved in {backup}" if removed else "") + ".")
    return removed


def latest_version(item, fetch=_get, strict=False):
    """The newest release tag for a GitHub release item (to offer an update), or None. An item pinned to a tested
    version has nothing newer to offer. An answer that could not be had is None, except that "GitHub is limiting this
    connection" is always raised (RateLimited), and with strict=True every error is."""
    source = item["source"]
    if source["type"] != "github_release":
        return None
    if source.get("tag", "latest") != "latest":       # pinned to a tested version: nothing newer to offer
        return None
    try:
        if source.get("prereleases") or channel_of(item) == "beta":
            releases = [r for r in json.loads(fetch(API + source["repo"] + "/releases?per_page=20")) if not r.get("draft")]
            return releases[0]["tag_name"] if releases else None
        return json.loads(fetch(API + source["repo"] + "/releases/latest")).get("tag_name")
    except RateLimited:
        raise
    except Exception:
        if strict:
            raise
        return None


# ----- which version is newer (2026-11-23) -----
_PRE_RANK = {"alpha": 0, "beta": 1, "preview": 1, "pre": 1, "rc": 2}


def parse_version(text):
    """A release tag as something that sorts: v1.10.0 -> ((1, 10), (9, 0)); v1.0.0-beta.2 -> ((1,), (1, 2)), which is
    before v1.0.0 (a finished release is rank 9). None when the text holds no number (main, installed)."""
    text = str(text or "")
    mark = re.search(r"(?<![A-Za-z])(alpha|beta|preview|pre|rc)(?![A-Za-z])[-._]?(\d*)", text, re.I)
    numbers = [int(n) for n in re.findall(r"\d+", text[:mark.start()] if mark else text)]
    if not numbers:
        return None
    while len(numbers) > 1 and numbers[-1] == 0:          # 1.0 and 1.0.0 are the same version
        numbers.pop()
    rank = (_PRE_RANK[mark.group(1).lower()], int(mark.group(2) or 0)) if mark else (9, 0)
    return tuple(numbers), rank


def is_newer(tag, have):
    """Is the release `tag` newer than the installed version `have`? Compared as numbers, so v1.10 is newer than v1.9 and
    an older release is not offered as an "update". When one of them is not a version number (a branch name, or an
    install this launcher did not record) any different tag counts as newer, as before."""
    if not tag:
        return False
    a, b = parse_version(tag), parse_version(have)
    if a is None or b is None:
        return tag != have
    return a > b


def installed_versions(items, kit, ashita, server=None, state=None):
    """{item id: installed version text} for the installed items whose newest version can be looked up (GitHub releases)."""
    state = load_state(kit) if state is None else state
    out = {}
    for item in items:
        if item.get("source", {}).get("type") != "github_release":
            continue
        installed, version = status(item, kit, ashita, state, server=server)
        if installed:
            out[item["id"]] = version
    return out


def check_updates(items, versions, fetch=_get):
    """Asks GitHub which installed downloads have a newer release: ({item id: newer tag}, [what went wrong]).
    `versions` is installed_versions(). Items that are not installed or are pinned are not asked about; one answer is
    asked for once however many items share a repository. When GitHub starts limiting this connection the check stops
    there and says so (the rest were not checked), instead of showing "nothing newer" for all of them."""
    newer, problems, answers = {}, [], {}

    def once(url, timeout=60):
        if url not in answers:
            answers[url] = fetch(url, timeout)
        return answers[url]
    for item in items:
        if item["id"] not in versions:
            continue
        try:
            tag = latest_version(item, once, strict=True)
        except RateLimited as error:
            problems.append(f"{error} The rest were not checked.")
            break
        except Exception as error:
            problems.append(f"{item['name']}: could not look up the newest version ({error}).")
            continue
        if tag and is_newer(tag, versions[item["id"]]):
            newer[item["id"]] = tag
    return newer, problems


CHECK_FILE = "thirdparty-check.json"


def check_downloads(kit, items, versions, fetch=_get, force=False, now=None, every=6 * 3600):
    """check_updates, but asking GitHub at most once every `every` seconds unless force: the last answer is kept in
    thirdparty-check.json, so starting the launcher ten times does not use up the 60 requests an hour. Returns
    (newer, problems, asked): `newer` is always only what is still newer than what is installed now."""
    now = time.time() if now is None else now
    path = os.path.join(kit, CHECK_FILE)
    try:
        with open(path, encoding="utf-8-sig") as handle:
            last = json.load(handle)
        if not isinstance(last, dict):
            last = {}
    except (OSError, ValueError):
        last = {}
    if not force and isinstance(last.get("at"), (int, float)) and 0 <= now - last["at"] < every:
        known = last.get("newer") if isinstance(last.get("newer"), dict) else {}
        return {k: v for k, v in known.items() if k in versions and is_newer(v, versions[k])}, [], False
    newer, problems = check_updates(items, versions, fetch)
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"at": now, "newer": newer}, handle, indent=2)
    except OSError:
        pass
    return newer, problems, True


def credits_lines(kit):
    """One line per item for the About box and CREDITS: name, author, license, home page."""
    return [f"{i['name']} - {i['author']} - {i['license']} - {i['homepage']}" for i in load_manifest(kit)]


# ----- our edits to an add-on the player installs by hand (Journal's era filter) -----
def apply_patch(kit, ashita, folder, dry_run=False):
    """Applies addons-src\\<folder>\\patch.json to Ashita. Every 'find' must appear exactly once (or its 'replace' must
    already be there: applied before), else nothing is changed. Changed files are backed up as <file>.before-era first.
    Returns a list of messages."""
    base = os.path.join(kit, "addons-src", folder)
    with open(os.path.join(base, "patch.json"), encoding="utf-8") as handle:
        patch = json.load(handle)
    texts, todo = {}, []
    for rel, find, replace in patch["edits"]:
        path = os.path.join(ashita, *rel.split("/"))
        if rel not in texts:
            if not os.path.exists(path):
                raise RuntimeError(f"{rel} is not there: install the add-on first.")
            with open(path, encoding="utf-8", newline="") as handle:
                texts[rel] = handle.read()
        text = texts[rel]
        crlf = "\r\n" in text
        f, r = (find.replace("\n", "\r\n"), replace.replace("\n", "\r\n")) if crlf else (find, replace)
        if text.count(f) == 1:
            todo.append((rel, f, r))
        elif text.count(r) == 1:
            continue                                   # already applied
        else:
            raise RuntimeError(f"{rel} is not the version these edits were made for ({patch.get('made_for')}): nothing was changed.")
    if dry_run:
        return [f"{len(todo)} change(s) to make"]
    messages = []
    for rel, f, r in todo:
        texts[rel] = texts[rel].replace(f, r, 1)
    for rel in sorted({t[0] for t in todo}):
        path = os.path.join(ashita, *rel.split("/"))
        if not os.path.exists(path + ".before-era"):
            shutil.copy2(path, path + ".before-era")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(texts[rel])
        messages.append(f"Edited {rel}.")
    for src, dest in patch.get("copy", []):
        target = os.path.join(ashita, *dest.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not os.path.exists(target):
            shutil.copy2(os.path.join(base, src), target)
            messages.append(f"Added {dest}.")
    return messages or ["The edits were already there."]
