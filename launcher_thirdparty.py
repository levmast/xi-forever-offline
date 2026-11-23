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


def load_manifest(kit, platform=None):
    with open(os.path.join(kit, "thirdparty.json"), encoding="utf-8-sig") as handle:
        return for_platform(json.load(handle)["items"], platform)


def state_path(kit):
    return os.path.join(kit, "thirdparty-installed.json")


def load_state(kit):
    try:
        with open(state_path(kit), encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(kit, state):
    with open(state_path(kit), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, indent=2)


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


def _get(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl_context()) as response:
        return response.read()


def resolve(item, fetch=_get):
    """What to download: {"version", "url", "name", "sha256" (or None)}. Raises ValueError for a page-only item."""
    source = item["source"]
    kind = source["type"]
    if kind == "github_release":
        tag = source.get("tag", "latest")
        if tag == "latest" and source.get("prereleases"):
            # GitHub's releases/latest skips pre-releases: take the newest published one, test builds included
            releases = [r for r in json.loads(fetch(API + source["repo"] + "/releases?per_page=20")) if not r.get("draft")]
            if not releases:
                raise RuntimeError(f"{item['name']}: no release published yet.")
            release = releases[0]
        else:
            path = "releases/latest" if tag == "latest" else "releases/tags/" + tag
            release = json.loads(fetch(API + source["repo"] + "/" + path))
        assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
        names = [n for n in assets if re.search(source["asset"], n)]
        if not names:
            raise RuntimeError(f"{item['name']}: no file matching {source['asset']} in release {release.get('tag_name')}")
        name = sorted(names)[0]
        digest = digest512 = None
        if source.get("sha256sums"):
            sums = fetch(assets[source["sha256sums"]]).decode("utf-8", "replace")
            for line in sums.splitlines():
                parts = line.split()
                if len(parts) >= 2 and os.path.basename(parts[-1].lstrip("*")) == name:
                    digest = parts[0].lower()
            if not digest:
                raise RuntimeError(f"{item['name']}: {name} is not listed in {source['sha256sums']}")
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
        return {"version": ref, "url": url, "name": source["repo"].split("/")[-1] + "-" + ref + ".zip", "sha256": None}
    if kind == "kit":                              # shipped inside the kit folder (no download)
        return {"version": source["version"], "url": "", "name": source["path"], "sha256": source.get("sha256"),
                "local": source["path"]}
    if kind == "ollama_model":
        return {"version": source["model"], "url": "", "name": source["model"], "sha256": None}
    if kind in ("url", "installer"):
        return {"version": time.strftime("%Y-%m-%d"), "url": source["url"], "name": source["url"].rsplit("/", 1)[-1], "sha256": None}
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
    data = fetch(found["url"], timeout=600)
    actual = hashlib.sha256(data).hexdigest()
    if found.get("sha256") and actual != found["sha256"]:
        raise RuntimeError(f"{item['name']}: the download does not match its published checksum - not installed.")
    path = os.path.join(folder, found["name"])
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
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if have:
            request.add_header("Range", f"bytes={have}-")
        with urllib.request.urlopen(request, timeout=60, context=ssl_context()) as response:
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


def install(item, kit, ashita, fetch=_get, log=print, server=None, run=None):
    """Downloads and installs one item. Returns the version installed."""
    if item["source"]["type"] == "ollama_model":
        pull_model(item["source"]["model"], log=log)
        return item["source"]["model"]
    root = target_root(item, kit, ashita, server)
    if not root:
        raise RuntimeError("Set the " + ("server" if item.get("into") == "server" else "Ashita") + " folder first.")
    found = resolve(item, fetch)
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
    if item["source"]["type"] == "installer":
        log(f"{item['name']}: starting its installer.")
        if item["source"].get("wait"):             # quiet installers (Visual C++): wait until done
            import subprocess
            result = (run or subprocess.run)([path] + list(item["source"].get("args", [])))
            if result.returncode not in (0, 1638, 3010):    # 1638 = a newer one is installed, 3010 = done, restart later
                raise RuntimeError(f"{item['name']}: the installer stopped with code {result.returncode}.")
        elif os.name == "nt":
            os.startfile(path)                     # Windows: the installer asks the player itself
        else:
            raise RuntimeError(f"{item['name']} is a Windows installer.")
    else:
        modes = {}
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
            read = lambda _name: open(path, "rb").read()
        moves = plan(item, names)
        if not moves:
            raise RuntimeError(f"{item['name']}: nothing in {found['name']} matched where it should go.")
        keep = tuple(item.get("keep", []))
        # files inside a kept folder that belong to the tool itself and must follow its version (Ashita's own memory
        # offsets and pointers in config/ashita/ashita.*.ini; the player's custom.*.ini stay)
        replace = tuple(item.get("replace", []))
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(kit, "backups", "thirdparty", f"{item['id']}-{stamp}")
        written = kept = 0
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
        log(f"{item['name']}: {written} file(s) installed" + (f", {kept} of your own kept" if kept else "")
            + (f"; replaced files saved in {backup}" if os.path.isdir(backup) else "") + ".")
    state = load_state(kit)
    state[item["id"]] = {"version": found["version"], "file": found["name"], "sha256": found.get("sha256_actual"),
                         "from": found["url"], "at": time.strftime("%Y-%m-%d %H:%M")}
    _save_state(kit, state)
    return found["version"]


def latest_version(item, fetch=_get):
    """The newest release tag for a GitHub release item (to offer an update), or None."""
    source = item["source"]
    if source["type"] != "github_release":
        return None
    try:
        if source.get("prereleases"):
            releases = [r for r in json.loads(fetch(API + source["repo"] + "/releases?per_page=20")) if not r.get("draft")]
            return releases[0]["tag_name"] if releases else None
        return json.loads(fetch(API + source["repo"] + "/releases/latest")).get("tag_name")
    except Exception:
        return None


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
