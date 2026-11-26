#!/usr/bin/env python3
"""Stinkshell relay (XI: Forever Offline, 2026-11-23): one online chat room for every player who switches the
Stinkshell add-on on, whatever world they play in. Runs on the hub server behind Caddy (chat.xiforever.com).

Standard library only. HTTP on 127.0.0.1 (Caddy adds HTTPS). Players never sign up: each launcher sends its own random
key (X-Stink-Key); the relay keeps only a hash of it.
  POST /hello {"name"}            -> {"screen", "seq"}   the character's name; the first launcher to use a name keeps it,
                                                         anyone else gets Name2, Name3...
  POST /say   {"name", "text"}    -> {"ok"} or {"error"} a line, or a /command (see below)
  GET  /poll?since=N              -> {"seq", "lines": [...], "people": [...]}  waits up to 25 s for something new
  POST /announce {"kind", "name", "mode", "job", "level", "extra", "world"}   (2026-11-23) a hardcore milestone, Steel
                                  delevel, Silver death or new hardcore run from a player's world: the relay writes the line
                                  itself (no free text) as kind "hardcore", shown in the room and to the hub
  GET  /announcements?since=N     -> {"seq", "lines": [...]}  the hardcore lines only, no waiting (the hub's launcher)
Website visitors (2026-11-23): the chat room page on xiforever.com talks to the relay straight from the browser (CORS,
only for the site's own address). A visitor picks a nickname and shows as "website: Nick", so nobody on the website can
take a character's name. Their key lives in the browser; a ban of a website name also bans that visitor's network
address (kept only as a hash), so clearing the browser does not get round it.
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
HC_KINDS = ("milestone", "delevel", "death", "start", "grant")
WEB_PREFIX = "website: "
APP_PREFIX = "mobile: "    # (2026-11-24) the XIFO phone app: header X-Stink-App: 1
WEB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{2,15}$")
SITE_ORIGINS = {"https://xiforever.com", "https://www.xiforever.com"}


def clean(text, limit=MAX_TEXT):
    """Printable plain text only, one line: nothing that could fake a game message or break a window."""
    text = "".join(ch for ch in str(text) if 32 <= ord(ch) < 127)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def keyhash(key):
    return hashlib.sha256(("stinkshell|" + str(key)).encode()).hexdigest()[:32]


def iphash(ip):
    return hashlib.sha256(("stinkshell-ip|" + str(ip)).encode()).hexdigest()[:24]


def web_target(args):
    """'/ban website: Nick' or '/ban website:Nick' -> ['website: Nick', ...] (moderators name website visitors this way)."""
    if args and args[0].lower() in ("website:", "web:") and len(args) > 1:
        return [WEB_PREFIX + args[1]] + args[2:]
    if args and args[0].lower().startswith("website:") and len(args[0]) > 8:
        return [WEB_PREFIX + args[0][8:]] + args[1:]
    if args and args[0].lower() in ("mobile:", "app:") and len(args) > 1:
        return [APP_PREFIX + args[1]] + args[2:]
    if args and args[0].lower().startswith("mobile:") and len(args[0]) > 7:
        return [APP_PREFIX + args[0][7:]] + args[1:]
    return args


class Room:
    def __init__(self, data):
        self.data = data
        self.lock = threading.Condition()
        self.lines = []          # {seq, t, kind, screen, text, to}
        self.announced = {}      # key hash -> times of its hardcore announcements (the last hour)
        self.seq = 0
        self.seen = {}           # keyhash -> {"screen", "t"}
        self.sent = {}           # keyhash -> [times]
        self.state = {"names": {}, "bans": {}, "mutes": {}, "mods": {}, "codes": {}, "webips": {}, "ipbans": {}}
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
    def screen_for(self, kh, name, web=False):
        """The name shown for this launcher: the character's name if no other launcher has it, else Name2, Name3...
        A website visitor: "website: Nick" (Nick2, Nick3... the same way); the phone app (web = APP_PREFIX): "mobile: Nick"."""
        base = clean(name, MAX_NAME)
        if not (WEB_NAME_RE if web else NAME_RE).match(base):
            base = "Guest" if web else "Adventurer"
        prefix = web if isinstance(web, str) and web else (WEB_PREFIX if web else "")
        names = self.state["names"]
        n, screen = 1, prefix + base
        while names.get(screen.lower(), kh) != kh:
            n += 1
            screen = prefix + (base[:MAX_NAME - len(str(n))] + str(n))
        if names.get(screen.lower()) != kh:
            names[screen.lower()] = kh
            self.save()
        return screen

    def role(self, kh):
        if self.state.get("owner") == kh:
            return "owner"
        return "mod" if kh in self.state["mods"] else "player"

    def key_of(self, screen):
        return self.state["names"].get(clean(screen, MAX_NAME + len(WEB_PREFIX) + 3).lower())

    def note_ip(self, kh, ip):
        """A website visitor's network address (as a hash), so a ban also covers a cleared browser."""
        if ip and self.state["webips"].get(kh) != ip:
            self.state["webips"][kh] = ip
            self.save()

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
        ip = self.state["webips"].get(kh)
        return kh in self.state["bans"] or (ip is not None and ip in self.state["ipbans"])

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

    # ---------------------------------------------------------------- hardcore announcements (2026-11-23)
    def announce(self, kh, body):
        """A hardcore line from a player's world. The text is made here from checked fields, so nobody can post free
        text this way. At most 12 an hour per launcher."""
        if self.banned(kh):
            return {"error": "banned"}
        now = time.time()
        times = [t for t in self.announced.get(kh, []) if now - t < 3600]
        if len(times) >= 12:
            self.announced[kh] = times
            return {"error": "Slow down a little."}
        kind = str(body.get("kind", ""))
        name = str(body.get("name", ""))
        mode = str(body.get("mode", ""))
        job = str(body.get("job", ""))
        try:
            level = int(body.get("level", 0))
        except (TypeError, ValueError):
            level = 0
        extra = clean(str(body.get("extra", "")), 20)
        world = clean(str(body.get("world", "")), 30)
        if (kind not in HC_KINDS or not NAME_RE.match(name) or mode not in ("Iron", "Steel", "Silver", "Randomized") or
                not re.fullmatch(r"[A-Z]{3}", job) or not 0 <= level <= 99):
            return {"error": "bad announcement"}
        where = f" in {world}" if world else ""
        if kind == "milestone":
            text = f"{name} ({mode}) reached level {level} on {job}{where}."
        elif kind == "delevel":
            text = f"{name} (Steel) fell on {job} at level {level}{where}. Back to level 1."
        elif kind == "grant":
            text = f"{name} (Randomized) was given {job} at level {level}{where}."
        elif kind == "death":
            text = f"{name} (Silver) has fallen: {job} {level}{', hardcore for ' + extra if extra else ''}{where}. Rest well."
        elif mode == "Randomized":
            text = f"{name} has begun a Randomized journey as a {job}{where}."
        else:
            text = f"{name} has begun a {mode} hardcore journey{where}."
        self.announced[kh] = times + [now]
        self.add("hardcore", "", text)
        return {"ok": True}

    def announcements(self, since):
        return [{k: v for k, v in line.items() if k != "to"} for line in self.lines
                if line["seq"] > since and line["kind"] == "hardcore"]

    # ---------------------------------------------------------------- commands
    def command(self, kh, screen, text):
        parts = text.split()
        word, args = parts[0].lower(), web_target(parts[1:])
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
                return tell(f"Nobody called {clean(args[0], 30)} has been in this room.")
            if target == self.state.get("owner") or (target in self.state["mods"] and me != "owner"):
                return tell("You cannot do that to a moderator.")
            name = clean(args[0], MAX_NAME + len(WEB_PREFIX) + 3)
            ip = self.state["webips"].get(target)
            if word == "/mute":
                minutes = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
                self.state["mutes"][target] = time.time() + minutes * 60
                self.add("system", "", f"{name} has been muted for {minutes} minutes.")
            elif word == "/unmute":
                self.state["mutes"].pop(target, None)
                self.add("system", "", f"{name} can talk again.")
            elif word == "/ban":
                self.state["bans"][target] = int(time.time())
                if ip:
                    self.state["ipbans"][ip] = int(time.time())
                self.seen.pop(target, None)
                self.add("system", "", f"{name} has been banned from the room.")
            elif word == "/unban":
                self.state["bans"].pop(target, None)
                if ip:
                    self.state["ipbans"].pop(ip, None)
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

    def say(self, kh, name, text, web=False):
        with self.lock:
            screen = self.screen_for(kh, name, web)
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

        def site(self):
            """True when the request comes from the website's own chat room page (a browser on xiforever.com)."""
            return self.headers.get("Origin", "") in SITE_ORIGINS

        def cors(self):
            if self.site():
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin"))
                self.send_header("Vary", "Origin")

        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.cors()
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            if not self.site():
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(204)
            self.cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Stink-Key")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def app(self):
            """The XIFO phone app (2026-11-24): its names show as "mobile: Nick". Returns the prefix, or ""."""
            return APP_PREFIX if self.headers.get("X-Stink-App", "") == "1" else ""

        def web_ip(self, kh):
            """Website visitors and the phone app: note their address (Caddy passes it on in X-Forwarded-For)."""
            if self.site() or self.app():
                ip = (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[0].strip()
                with room.lock:
                    room.note_ip(kh, iphash(ip))

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
            web = self.app() or self.site()   # (a browser on the website is always a website visitor; the phone app: "mobile: ")
            self.web_ip(kh)
            if path == "/hello":
                with room.lock:
                    banned = room.banned(kh)
                    if not banned:
                        screen = room.screen_for(kh, body.get("name", ""), web)
                        room.touch(kh, screen)
                        answer = {"screen": screen, "seq": max(0, room.seq - JOIN_HISTORY)}
                if banned:
                    return self.reply(200, {"error": "You are banned from this room."})
                return self.reply(200, answer)
            if path == "/say":
                return self.reply(200, room.say(kh, body.get("name", ""), body.get("text", ""), web))
            if path == "/announce":
                if web:
                    return self.reply(403, {"error": "not from the website"})
                with room.lock:
                    answer = room.announce(kh, body)
                return self.reply(200, answer)
            return self.reply(404, {"error": "unknown"})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path.rstrip("/") == "/health":
                return self.reply(200, {"ok": True, "people": len(room.people())})
            kh = self.key()
            if kh and url.path.rstrip("/") == "/announcements":
                try:
                    since = int(parse_qs(url.query).get("since", ["0"])[0])
                except ValueError:
                    since = 0
                with room.lock:
                    body = {"seq": room.seq, "lines": room.announcements(since)[-50:]}
                return self.reply(200, body)
            if not kh or url.path.rstrip("/") != "/poll":
                return self.reply(403, {"error": "no key"})
            self.web_ip(kh)
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
