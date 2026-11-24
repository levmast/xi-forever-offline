#!/usr/bin/env python3
"""Stinkshell relay (XI: Forever Offline, 2026-11-23): one online chat room for every player who switches the
Stinkshell add-on on, whatever world they play in. Runs on the hub server behind Caddy (chat.xiforever.com).

Standard library only. HTTP on 127.0.0.1 (Caddy adds HTTPS). Players never sign up: each launcher sends its own random
key (X-Stink-Key); the relay keeps only a hash of it.
  POST /hello {"name"}            -> {"screen", "seq"}   the character's name; the first launcher to use a name keeps it,
                                                         anyone else gets Name2, Name3...
  POST /say   {"name", "text"}    -> {"ok"} or {"error"} a line, or a /command (see below)
  GET  /poll?since=N              -> {"seq", "lines": [...], "people": [...]}  waits up to 25 s for something new
Commands (typed in the chat): /who; owner and moderators: /mute Name [minutes], /unmute Name, /ban Name, /unban Name,
/kick Name; owner only: /modcode (a new one-time moderator code), /unmod Name. Anyone: /login CODE (the owner code
printed at the first start, or a moderator code).
Files in the data folder (default /var/lib/stinkshell): state.json (names, bans, mutes, moderators), owner.txt.
Run: python3 stinkshell_relay.py [--port 54300] [--data /var/lib/stinkshell]
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MAX_TEXT = 200
MAX_NAME = 15
HISTORY = 300
JOIN_HISTORY = 40
ONLINE_FOR = 70            # seconds since the last poll: still in the room
POLL_WAIT = 25
RATE = (5, 10)             # at most 5 lines in 10 seconds
NAME_RE = re.compile(r"^[A-Za-z]{2,15}$")


def clean(text, limit=MAX_TEXT):
    """Printable plain text only, one line: nothing that could fake a game message or break a window."""
    text = "".join(ch for ch in str(text) if 32 <= ord(ch) < 127)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def keyhash(key):
    return hashlib.sha256(("stinkshell|" + str(key)).encode()).hexdigest()[:32]


class Room:
    def __init__(self, data):
        self.data = data
        self.lock = threading.Condition()
        self.lines = []          # {seq, t, kind, screen, text, to}
        self.seq = 0
        self.seen = {}           # keyhash -> {"screen", "t"}
        self.sent = {}           # keyhash -> [times]
        self.state = {"names": {}, "bans": {}, "mutes": {}, "mods": {}, "codes": {}}
        os.makedirs(data, exist_ok=True)
        try:
            with open(os.path.join(data, "state.json"), encoding="utf-8") as handle:
                self.state.update(json.load(handle))
        except (OSError, ValueError):
            pass
        owner = os.path.join(data, "owner.txt")
        if not os.path.exists(owner):
            with open(owner, "w", encoding="utf-8") as handle:
                handle.write(secrets.token_hex(12) + "\n")
            os.chmod(owner, 0o600)
        with open(owner, encoding="utf-8") as handle:
            self.owner_code = handle.read().strip()

    def save(self):
        path = os.path.join(self.data, "state.json")
        with open(path + ".part", "w", encoding="utf-8") as handle:
            json.dump(self.state, handle)
        os.replace(path + ".part", path)

    # ---------------------------------------------------------------- who is who
    def screen_for(self, kh, name):
        """The name shown for this launcher: the character's name if no other launcher has it, else Name2, Name3..."""
        base = clean(name, MAX_NAME)
        if not NAME_RE.match(base):
            base = "Adventurer"
        names = self.state["names"]
        n, screen = 1, base
        while names.get(screen.lower(), kh) != kh:
            n += 1
            screen = (base[:MAX_NAME - len(str(n))] + str(n))
        if names.get(screen.lower()) != kh:
            names[screen.lower()] = kh
            self.save()
        return screen

    def role(self, kh):
        if self.state.get("owner") == kh:
            return "owner"
        return "mod" if kh in self.state["mods"] else "player"

    def key_of(self, screen):
        return self.state["names"].get(clean(screen, MAX_NAME + 3).lower())

    def people(self):
        now = time.time()
        return sorted({v["screen"] for v in self.seen.values() if now - v["t"] < ONLINE_FOR}, key=str.lower)

    # ---------------------------------------------------------------- lines
    def add(self, kind, screen, text, to=None):
        with self.lock:
            self.seq += 1
            self.lines.append({"seq": self.seq, "t": int(time.time()), "kind": kind, "screen": screen, "text": text, "to": to})
            del self.lines[:-HISTORY]
            self.lock.notify_all()

    def visible(self, kh, since):
        return [{k: v for k, v in line.items() if k != "to"} for line in self.lines
                if line["seq"] > since and (line["to"] is None or line["to"] == kh)]

    def touch(self, kh, screen):
        was = self.seen.get(kh)
        fresh = was is None or time.time() - was["t"] >= ONLINE_FOR
        self.seen[kh] = {"screen": screen, "t": time.time()}
        if fresh and not self.banned(kh):
            self.add("enter", screen, screen + " has entered the room.")

    def sweep(self):
        now = time.time()
        for kh, v in list(self.seen.items()):
            if now - v["t"] >= ONLINE_FOR:
                del self.seen[kh]
                self.add("leave", v["screen"], v["screen"] + " has left the room.")

    def banned(self, kh):
        return kh in self.state["bans"]

    def muted(self, kh):
        until = self.state["mutes"].get(kh, 0)
        return until and (until < 0 or until > time.time())

    def rate_ok(self, kh):
        now = time.time()
        times = [t for t in self.sent.get(kh, []) if now - t < RATE[1]]
        if len(times) >= RATE[0]:
            self.sent[kh] = times
            return False
        self.sent[kh] = times + [now]
        return True

    # ---------------------------------------------------------------- commands
    def command(self, kh, screen, text):
        parts = text.split()
        word, args = parts[0].lower(), parts[1:]
        me = self.role(kh)

        def tell(msg):
            self.add("system", "", msg, to=kh)

        if word == "/who":
            people = self.people()
            return tell(f"People here ({len(people)}): " + ", ".join(people))
        if word == "/login" and args:
            code = args[0]
            if secrets.compare_digest(code, self.owner_code):
                self.state["owner"] = kh
            elif code in self.state["codes"]:
                del self.state["codes"][code]
                self.state["mods"][kh] = screen
            else:
                return tell("That code is not right.")
            self.save()
            return tell("You are now " + ("the owner" if self.role(kh) == "owner" else "a moderator") + " of this room.")
        if me == "player":
            return tell("Commands: /who")
        if word == "/modcode" and me == "owner":
            code = secrets.token_hex(6)
            self.state["codes"][code] = int(time.time())
            self.save()
            return tell(f"New moderator code: {code}  (they type /login {code} once)")
        if word in ("/mute", "/unmute", "/ban", "/unban", "/kick", "/unmod") and args:
            target = self.key_of(args[0])
            if not target:
                return tell(f"Nobody called {clean(args[0], 20)} has been in this room.")
            if target == self.state.get("owner") or (target in self.state["mods"] and me != "owner"):
                return tell("You cannot do that to a moderator.")
            name = clean(args[0], 20)
            if word == "/mute":
                minutes = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
                self.state["mutes"][target] = time.time() + minutes * 60
                self.add("system", "", f"{name} has been muted for {minutes} minutes.")
            elif word == "/unmute":
                self.state["mutes"].pop(target, None)
                self.add("system", "", f"{name} can talk again.")
            elif word == "/ban":
                self.state["bans"][target] = int(time.time())
                self.seen.pop(target, None)
                self.add("system", "", f"{name} has been banned from the room.")
            elif word == "/unban":
                self.state["bans"].pop(target, None)
                tell(f"{name} is no longer banned.")
            elif word == "/kick":
                self.seen.pop(target, None)
                self.state["mutes"][target] = time.time() + 300
                self.add("system", "", f"{name} has been kicked (5 minutes).")
            elif word == "/unmod" and me == "owner":
                self.state["mods"].pop(target, None)
                tell(f"{name} is no longer a moderator.")
            self.save()
            return None
        return tell("Commands: /who /mute Name [minutes] /unmute Name /kick Name /ban Name /unban Name" +
                    (" /modcode /unmod Name" if me == "owner" else ""))

    def say(self, kh, name, text):
        with self.lock:
            screen = self.screen_for(kh, name)
            if self.banned(kh):
                return {"error": "You are banned from this room."}
            text = clean(text)
            if not text:
                return {"error": "Nothing to send."}
            self.touch(kh, screen)
            if text.startswith("/"):
                self.command(kh, screen, text)
                return {"ok": True}
            if self.muted(kh):
                return {"error": "You are muted for now."}
            if not self.rate_ok(kh):
                return {"error": "Slow down a little."}
        self.add("say", screen, text)
        return {"ok": True}


def make_handler(room):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Stinkshell/1"

        def log_message(self, *args):
            pass

        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def key(self):
            key = self.headers.get("X-Stink-Key", "")
            return keyhash(key) if re.fullmatch(r"[0-9a-f]{32,64}", key or "") else None

        def body(self):
            size = int(self.headers.get("Content-Length") or 0)
            if size <= 0 or size > 2048:
                return {}
            try:
                value = json.loads(self.rfile.read(size))
                return value if isinstance(value, dict) else {}
            except ValueError:
                return {}

        def do_POST(self):
            kh = self.key()
            if not kh:
                return self.reply(403, {"error": "no key"})
            body = self.body()
            path = urlparse(self.path).path.rstrip("/")
            if path == "/hello":
                with room.lock:
                    banned = room.banned(kh)
                    if not banned:
                        screen = room.screen_for(kh, body.get("name", ""))
                        room.touch(kh, screen)
                        answer = {"screen": screen, "seq": max(0, room.seq - JOIN_HISTORY)}
                if banned:
                    return self.reply(200, {"error": "You are banned from this room."})
                return self.reply(200, answer)
            if path == "/say":
                return self.reply(200, room.say(kh, body.get("name", ""), body.get("text", "")))
            return self.reply(404, {"error": "unknown"})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.rstrip("/") == "/health":
                return self.reply(200, {"ok": True, "people": len(room.people())})
            kh = self.key()
            if not kh or url.path.rstrip("/") != "/poll":
                return self.reply(403, {"error": "no key"})
            if room.banned(kh):
                return self.reply(200, {"error": "You are banned from this room.", "seq": room.seq, "lines": [], "people": []})
            try:
                since = int(parse_qs(url.query).get("since", ["0"])[0])
            except ValueError:
                since = 0
            end = time.time() + POLL_WAIT
            with room.lock:
                if kh in room.seen:
                    room.seen[kh]["t"] = time.time()
                while not room.visible(kh, since) and time.time() < end:
                    room.lock.wait(max(0.1, end - time.time()))
                body = {"seq": room.seq, "lines": room.visible(kh, since)[-JOIN_HISTORY * 2:], "people": room.people()}
            return self.reply(200, body)                    # sent after the lock is let go: a slow player holds up nobody

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Stinkshell relay")
    ap.add_argument("--port", type=int, default=54300)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--data", default="/var/lib/stinkshell")
    args = ap.parse_args()
    room = Room(args.data)

    def sweeper():
        while True:
            time.sleep(10)
            room.sweep()
    threading.Thread(target=sweeper, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(room))
    server.daemon_threads = True
    print(f"Stinkshell relay on {args.host}:{args.port}, data in {args.data}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
