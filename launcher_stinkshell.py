"""Stinkshell (2026-11-23, the user): an online chat room for players of every world, in a window that looks like a
1999 chat room. Off by default: it is the add-on "stinkshell" on OPTIONS > Addons. While that add-on is switched on
and the launcher runs, this bridge carries the lines between the add-on and the relay on the hub server
(dev/stinkshell/stinkshell_relay.py at chat.xiforever.com). Nothing goes online while the add-on is off.

The add-on and the bridge talk through three files in Ashita's config/addons/stinkshell folder:
  out.txt     written by the add-on: "say|<character>|<text>" or "hello|<character>"; the bridge empties it
  in.txt      written by the bridge, one line per message: "<seq>|<kind>|<screen name>|<text>|<time>"
  people.txt  written by the bridge: the screen names in the room, one per line; line 1 is "#me|<your screen name>"
No tkinter here. Tests: dev/launcher-tests/test_stinkshell.py.
"""
import json
import os
import secrets
import threading
import time
import urllib.request

URL = "https://chat.xiforever.com"
FOLDER = os.path.join("config", "addons", "stinkshell")
KEY_FILE = "stinkshell.json"            # in the kit folder: this launcher's own random key (never sent to anyone else)


def key_for(kit):
    path = os.path.join(kit, KEY_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            key = json.load(handle).get("key", "")
            if len(key) == 32:
                return key
    except (OSError, ValueError):
        pass
    key = secrets.token_hex(16)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"key": key}, handle)
    return key


def clean(text, limit=200):
    return "".join(ch for ch in str(text) if 32 <= ord(ch) < 127 and ch != "|")[:limit]


class Bridge:
    """Started and stopped by the launcher (App.stinkshell_tick); does its network work on its own thread."""

    def __init__(self, kit, ashita, url=URL, opener=None, log=None):
        self.kit, self.ashita, self.url = kit, ashita, url.rstrip("/")
        self.folder = os.path.join(ashita, FOLDER)
        self.key = key_for(kit)
        self.opener = opener                    # tests: opener(method, path, body) -> dict
        self.log = log or (lambda text: None)
        self.stop_flag = threading.Event()
        self.thread = None
        self.name = None
        self.screen = None
        self.seq = 0
        self.problem = None

    # ---------------------------------------------------------------- files
    def path(self, name):
        return os.path.join(self.folder, name)

    def take_out(self):
        """The add-on's waiting lines, and an empty out.txt."""
        path, work = self.path("out.txt"), self.path("out.work")
        try:
            if os.path.getsize(path) == 0:
                return []
            os.replace(path, work)              # the add-on starts a new out.txt if it writes meanwhile: nothing is lost
            with open(work, encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
            os.remove(work)
            return lines
        except OSError:
            return []

    def write_in(self, lines):
        if not lines:
            return
        with open(self.path("in.txt"), "a", encoding="utf-8", newline="\n") as handle:
            for line in lines:
                handle.write("%d|%s|%s|%s|%d\n" % (int(line.get("seq", 0)), clean(line.get("kind", "say"), 10),
                                                  clean(line.get("screen", ""), 20), clean(line.get("text", "")), int(line.get("t", 0))))

    def write_people(self, people):
        with open(self.path("people.txt") + ".part", "w", encoding="utf-8", newline="\n") as handle:
            handle.write("#me|%s\n" % clean(self.screen or "", 20))
            for p in people[:200]:
                handle.write(clean(p, 20) + "\n")
        os.replace(self.path("people.txt") + ".part", self.path("people.txt"))

    def note(self, text):
        self.write_in([{"seq": 0, "kind": "system", "screen": "", "text": text, "t": int(time.time())}])

    # ---------------------------------------------------------------- network
    def call(self, method, path, body=None, timeout=10):
        if self.opener is not None:
            return self.opener(method, path, body)
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method,
                                         headers={"X-Stink-Key": self.key, "Content-Type": "application/json",
                                                  "User-Agent": "XI-Forever-Offline-Stinkshell"})
        try:
            import launcher_thirdparty
            context = launcher_thirdparty.ssl_context()
        except Exception:
            context = None
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read(65536) or b"{}")

    def hello(self, name):
        answer = self.call("POST", "/hello", {"name": name})
        if answer.get("error"):
            self.note(answer["error"])
            return False
        self.name, self.screen = name, answer.get("screen", name)
        self.seq = int(answer.get("seq", 0))
        return True

    def send_waiting(self):
        for line in self.take_out():
            kind, _, rest = line.partition("|")
            name, _, text = rest.partition("|")
            name = clean(name, 20)
            if not name:
                continue
            if kind == "hello" or name != self.name:
                if not self.hello(name):
                    continue
            if kind == "say" and text.strip():
                answer = self.call("POST", "/say", {"name": name, "text": clean(text)})
                if answer.get("error"):
                    self.note(answer["error"])

    def poll_once(self, timeout=30):
        answer = self.call("GET", f"/poll?since={self.seq}", timeout=timeout)
        if answer.get("error"):
            self.note(answer["error"])
        lines = answer.get("lines") or []
        self.write_in(lines)
        if lines:
            self.seq = max(self.seq, max(int(line.get("seq", 0)) for line in lines))
        self.seq = max(self.seq, int(answer.get("seq", 0)) if not lines else self.seq)
        self.write_people(answer.get("people") or [])

    # ---------------------------------------------------------------- the thread
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        os.makedirs(self.folder, exist_ok=True)
        for name in ("in.txt", "out.txt"):
            open(self.path(name), "w").close()
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    def run(self):
        sender = threading.Thread(target=self.send_loop, daemon=True)
        sender.start()
        wait = 2
        while not self.stop_flag.is_set():
            if self.name is None:
                self.stop_flag.wait(1)
                continue
            try:
                self.poll_once()
                if self.problem:
                    self.problem = None
                    self.note("Connected to Stinkshell again.")
                wait = 2
            except Exception as e:
                if not self.problem:
                    self.problem = str(e)
                    self.note("Stinkshell can't reach the chat room right now. Trying again...")
                    self.log(f"Stinkshell: {e}")
                self.stop_flag.wait(wait)
                wait = min(60, wait * 2)

    def send_loop(self):
        while not self.stop_flag.is_set():
            try:
                self.send_waiting()
            except Exception as e:
                self.log(f"Stinkshell: {e}")
                self.note("Your line could not be sent (no connection).")
            self.stop_flag.wait(0.5)


def addon_on(ashita, boot_name):
    """True while the stinkshell add-on is switched on in the launcher's script."""
    try:
        import launcher_core as core
        return "stinkshell" in core.ScriptManager(ashita, boot_name).enabled("addon")
    except Exception:
        return False
