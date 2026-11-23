"""Co-op for XI: Forever Offline (no GUI here): invite codes, the host's small service, the visitor's side of a visit, and
the settings a PC needs to let friends in. Character data itself is handled by launcher_passport.py.

How two launchers talk
  The host's launcher listens on one TCP port (54100). The visitor's launcher sends it requests; the host never has to
  reach the visitor, so a visitor needs no open ports. Every message is sealed with a key both sides already have:
  the invite code's secret for "hello" and "arrive", then a key of the visitor's own. A message that was not sealed with
  the right key is dropped before anything is done. (This is standard-library sealing, not TLS; use the same network or
  Tailscale rather than an open port on the internet.)

Experimental: off until the player turns it on in the launcher's CO-OP page.
"""
import base64
import hashlib
import hmac
import json
import ntpath
import os
import re
import secrets
import shutil
import socket
import struct
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import launcher_passport as pp

PORT = 54100
MAX_GUESTS = 6
PREFIX = "XIFO1-"
SETTINGS_FILE = "coop.json"
PATH = "/xifo"
CHECKPOINT_SECONDS = 300             # a visitor's launcher fetches a fresh copy of its character this often
CHECKPOINT_MIN_SECONDS = 60          # ...and the host makes one at most this often per visitor
TAKE_BACK_HOURS = 24                 # the host must be out of reach this long before "take back" is offered
MAX_BODY = 48 * 1024 * 1024
GAME_PORTS = (("log in", 54231), ("lobby", 54230), ("lobby view", 54001), ("search", 54002), ("profile", 51220))
FIREWALL_RULE = "XI Forever Offline co-op"
SERVER_PROGRAMS = ("xi_connect", "xi_map", "xi_search", "xi_profile")
VISIT_BOOT = "xiforever-coop.ini"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
MODES = {"lan": "Same network (LAN / Wi-Fi)", "tailscale": "Over the internet with Tailscale", "direct": "Over the internet, direct (advanced)"}
TAILSCALE_PAGE = "https://tailscale.com/download"
# Tailscale's own Windows installer: the address behind the download button on tailscale.com/download/windows
TAILSCALE_INSTALLER = "https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe"
TAILSCALE_MAX_BYTES = 400 * 1024 * 1024
SCOPES = {"lan": "LocalSubnet", "tailscale": "100.64.0.0/10", "direct": "Any"}


class CoopError(Exception):
    """Something the player can be told as it is."""


class Unreachable(CoopError):
    """The other launcher did not answer (off, asleep, wrong address, blocked)."""


class Busy(CoopError):
    """The host's launcher could not look something up just now (its database is restarting, say)."""


class Refused(CoopError):
    """The other launcher answered and said no. `code` is a short word for the reason."""

    def __init__(self, message, code="", extra=None):
        super().__init__(message)
        self.code, self.extra = code, extra or {}


# ----- settings (coop.json in the kit folder) -----
def load_settings(kit):
    data = {}
    try:
        with open(os.path.join(kit, SETTINGS_FILE), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        pass
    out = {"enabled": False, "hosting": False, "mode": "lan", "address": "", "port": PORT, "secret": "",
           "max_guests": 3, "zoneip_set": "", "backup_done": False}
    if isinstance(data, dict):
        out.update({k: v for k, v in data.items() if k in out})
    if out["mode"] not in MODES:
        out["mode"] = "lan"
    try:
        out["port"] = int(out["port"])
        out["max_guests"] = max(1, min(MAX_GUESTS, int(out["max_guests"])))
    except (TypeError, ValueError):
        out["port"], out["max_guests"] = PORT, 3
    if not re.fullmatch(r"[0-9a-f]{32}", str(out["secret"])):
        out["secret"] = secrets.token_hex(16)
    return out


def save_settings(kit, settings):
    path = os.path.join(kit, SETTINGS_FILE)
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    os.replace(path + ".part", path)


def versions(kit, server_dir):
    """{"kit": "v0.1.30" or "dev", "server": ...} from the VERSION.txt of each folder (a self-built copy has none)."""
    def read(folder):
        try:
            with open(os.path.join(folder, "VERSION.txt"), encoding="utf-8") as handle:
                found = re.search(r"\bv\d[\w.\-]*", handle.readline())
            return found.group(0) if found else "dev"
        except OSError:
            return "dev"
    return {"kit": read(kit), "server": read(server_dir) if server_dir else "dev"}


def versions_clash(mine, theirs):
    """A sentence when two worlds cannot be mixed because their server versions differ, else None."""
    a, b = (mine or {}).get("server", "dev"), (theirs or {}).get("server", "dev")
    if a != "dev" and b != "dev" and a != b:
        return f"The two worlds are on different versions ({b} there, {a} here). Update both to the newest version first."
    return None


# ----- sealing messages -----
def _keys(key):
    return hmac.new(key, b"xifo-enc", hashlib.sha256).digest(), hmac.new(key, b"xifo-mac", hashlib.sha256).digest()


def _xor(data, stream):
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big") if data else b""


def seal(key, obj, blob=b""):
    """A message only the holder of `key` can read or make: JSON plus an optional file, scrambled and signed."""
    head = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    plain = struct.pack(">I", len(head)) + head + blob
    nonce = os.urandom(16)
    enc, mac = _keys(key)
    scrambled = _xor(plain, hashlib.shake_256(enc + nonce).digest(len(plain)))
    return b"XC1" + nonce + hmac.new(mac, nonce + scrambled, hashlib.sha256).digest() + scrambled


def unseal(key, data):
    if len(data) < 55 or data[:3] != b"XC1":
        raise CoopError("That was not a co-op message.")
    nonce, tag, scrambled = data[3:19], data[19:51], data[51:]
    enc, mac = _keys(key)
    if not hmac.compare_digest(tag, hmac.new(mac, nonce + scrambled, hashlib.sha256).digest()):
        raise CoopError("That message was not made with the right invite code.")
    plain = _xor(scrambled, hashlib.shake_256(enc + nonce).digest(len(scrambled)))
    size = struct.unpack(">I", plain[:4])[0]
    if size > len(plain) - 4:
        raise CoopError("That message is damaged.")
    obj = json.loads(plain[4:4 + size].decode("utf-8"))
    if not isinstance(obj, dict):
        raise CoopError("That message is damaged.")
    return obj, plain[4 + size:]


# ----- invite codes and what is worked out from them -----
def valid_address(address):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.\-]{0,252}", str(address or "")))


def make_invite(address, port, secret, world_name):
    data = json.dumps({"a": address, "p": int(port), "s": secret, "w": world_name}, separators=(",", ":")).encode("utf-8")
    return PREFIX + base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def read_invite(text):
    text = re.sub(r"\s+", "", str(text or ""))
    if not text.startswith(PREFIX):
        raise CoopError("That is not an invite code. It starts with " + PREFIX + " and your friend's launcher makes it.")
    try:
        raw = text[len(PREFIX):]
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
        invite = {"address": str(data["a"]), "port": int(data["p"]), "secret": str(data["s"]), "world": pp.clean_world_name(data.get("w", ""))}
    except Exception:
        raise CoopError("That invite code is damaged. Ask your friend to copy it again.")
    if not valid_address(invite["address"]) or not 1 <= invite["port"] <= 65535 or not re.fullmatch(r"[0-9a-f]{32}", invite["secret"]):
        raise CoopError("That invite code is damaged. Ask your friend to copy it again.")
    return invite


def guest_key(secret, guest_id):
    return hmac.new(bytes.fromhex(secret), b"guest|" + guest_id.encode("ascii"), hashlib.sha256).hexdigest()


def guest_login(guest_id):
    return "v" + guest_id[:11]


def guest_password(gkey):
    digest = hmac.new(bytes.fromhex(gkey), b"game-password", hashlib.sha256).digest()
    return base64.b32encode(digest).decode("ascii").lower()[:16]


# ----- the host's side -----
class Host:
    """The service friends' launchers talk to. start() listens; handle() answers one sealed request (also used by tests)."""

    def __init__(self, cfg, kit, settings, log=print, connect=None):
        self.cfg, self.kit, self.settings, self.log = cfg, kit, settings, log
        self.connect = connect or (lambda: pp.connect(cfg))
        self.closing = False                 # the host pressed Stop hosting: no new arrivals, visitors are sent home
        self.server, self.thread = None, None
        self.lock = threading.Lock()
        self.last_checkpoint, self.last_seen, self.failures = {}, {}, {}
        self.save_dir = os.path.join(kit, "backups", "coop")

    # --- listening ---
    def start(self):
        if self.server is not None:
            return
        host = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if self.path != PATH or size <= 0 or size > MAX_BODY:
                        raise CoopError("no")
                    answer = host.handle(self.headers.get("X-Coop-Key", ""), self.rfile.read(size), self.client_address[0])
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Length", str(len(answer)))
                    self.end_headers()
                    self.wfile.write(answer)
                except Exception as e:
                    try:
                        self.send_response(503 if isinstance(e, Busy) else 403)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                    except Exception:
                        pass

            def do_GET(self):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *_args):
                pass

        bind = self.settings.get("address") if self.settings.get("mode") != "direct" else ""
        try:
            self.server = ThreadingHTTPServer((bind or "0.0.0.0", int(self.settings["port"])), Handler)
        except OSError:
            self.server = ThreadingHTTPServer(("0.0.0.0", int(self.settings["port"])), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is not None:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
        self.server, self.thread = None, None

    def running(self):
        return self.server is not None

    # --- one request ---
    def _guest_row(self, guest_id):
        conn = self.connect()
        try:
            for guest in pp.guest_list(conn, include_gone=True):
                if guest["guest_id"] == guest_id:
                    return guest
            return None
        finally:
            conn.close()

    def handle(self, key_header, body, client="?"):
        """Answers one sealed request with one sealed reply. Raises when the request cannot be trusted."""
        now = time.time()
        fails = self.failures.get(client)
        if fails and fails[0] >= 20 and now - fails[1] < 600:
            raise CoopError("too many wrong tries")
        kind, _sep, guest_id = str(key_header).partition(":")
        guest = None
        try:
            if kind == "invite":
                key = bytes.fromhex(self.settings["secret"])
            elif kind == "guest" and re.fullmatch(r"[0-9a-f]{16,32}", guest_id):
                try:
                    guest = self._guest_row(guest_id)
                except Exception:
                    raise Busy("the database did not answer")
                if guest is None:
                    raise CoopError("unknown visitor")
                key = bytes.fromhex(guest["gkey"])
            else:
                raise CoopError("no key")
            request, blob = unseal(key, body)
        except Busy:
            raise
        except Exception:
            count = fails[0] + 1 if fails and now - fails[1] < 600 else 1
            self.failures[client] = (count, now)
            raise
        op = request.get("op")
        try:
            if kind == "invite" and op == "hello":
                reply, out = self._hello(), b""
            elif kind == "invite" and op == "arrive":
                reply, out = self._arrive(request, blob), b""
            elif kind == "guest" and op == "status":
                reply, out = self._status(guest), b""
            elif kind == "guest" and op == "checkpoint":
                reply, out = self._checkpoint(guest)
            elif kind == "guest" and op == "go_home":
                reply, out = self._go_home(guest, bool(request.get("force")))
            elif kind == "guest" and op == "confirm_home":
                reply, out = self._confirm(guest), b""
            else:
                reply, out = {"ok": False, "code": "unknown", "error": "This version does not know that request."}, b""
        except pp.PassportError as e:
            reply, out = {"ok": False, "code": "refused", "error": str(e)}, b""
        except CoopError as e:
            reply, out = {"ok": False, "code": getattr(e, "code", "") or "refused", "error": str(e)}, b""
        except Exception as e:                   # a database hiccup and the like: say so, the visitor's launcher tries again
            self.log(f"Co-op: a request failed ({type(e).__name__}: {e})")
            reply, out = {"ok": False, "code": "busy", "error": "The host's launcher had a problem. Try again in a moment."}, b""
        if guest is not None:
            self.last_seen[guest["guest_id"]] = now
        return seal(key, reply, out)

    # --- the requests ---
    def _world(self, conn):
        return pp.world_identity(conn)

    def _hello(self):
        conn = self.connect()
        try:
            world = self._world(conn)
            guests = [g for g in pp.guest_list(conn) if g["state"] == "active"]
            signature = pp.schema_signature(conn)
        finally:
            conn.close()
        return {"ok": True, "world": world, "versions": versions(self.kit, self.cfg.get("server_dir")), "schema": signature,
                "guests": len(guests), "max_guests": int(self.settings["max_guests"]), "open": self.open_for_arrivals(),
                "rules": world_rules(self.kit), "fingerprint": self.fingerprint()}

    def fingerprint(self):
        """The game server's key, so a visitor's game loader knows it is talking to the right server."""
        return server_fingerprint(self.cfg.get("server_dir"))

    def open_for_arrivals(self):
        return bool(self.settings.get("hosting")) and not self.closing

    def _arrive(self, request, blob):
        guest_id = str(request.get("guest_id", ""))
        if not re.fullmatch(r"[0-9a-f]{16,32}", guest_id):
            raise CoopError("That request is damaged.")
        if not self.open_for_arrivals():
            raise Refused("This world is not taking visitors right now.", "closed")
        clash = versions_clash(versions(self.kit, self.cfg.get("server_dir")), request.get("versions"))
        if clash:
            raise Refused(clash, "version")
        gkey = guest_key(self.settings["secret"], guest_id)
        with self.lock:
            conn = self.connect()
            try:
                world = self._world(conn)
                stamp = {"world": world["name"], "id": world["id"], "arrived": int(time.time()), "rules": world_rules(self.kit)}
                avoid = [i for i in (request.get("avoid") or []) if isinstance(i, int)]
                record = pp.import_guest(conn, blob, guest_id, gkey, guest_login(guest_id), guest_password(gkey),
                                         max_guests=int(self.settings["max_guests"]), stamp=stamp, avoid=avoid)
            finally:
                conn.close()
        if record["guest_id"] != guest_id:
            raise Refused(f"{record['name']} is already visiting this world from another launcher.", "duplicate")
        if not record.get("again"):
            self.log(f"Co-op: {record['name']} has arrived in your world.")
            announce(self.cfg.get("server_dir"), f"{record['name']} is visiting this world.")
            if record.get("renamed_bot"):
                self.log(f"Co-op: a bot player had the same name and is now called {record['renamed_bot']} (from the next start).")
        return {"ok": True, "guest_id": guest_id, "login": record["login"], "charid": record["charid"], "name": record["name"],
                "address": self.settings.get("address", ""), "world": world, "fingerprint": self.fingerprint()}

    def _status(self, guest):
        holdings = {}
        if guest["state"] == "active":
            conn = self.connect()
            try:
                holdings = pp.guest_holdings(conn, guest["charid"])
            finally:
                conn.close()
        return {"ok": True, "state": guest["state"], "online": guest["online"], "generation": guest["generation"],
                "closing": self.closing or not self.settings.get("hosting"), "holdings": holdings,
                "fingerprint": self.fingerprint(), "address": self.settings.get("address", "")}

    def _checkpoint(self, guest):
        if guest["state"] != "active":
            return {"ok": False, "code": guest["state"], "error": "That visit is over."}, b""
        last = self.last_checkpoint.get(guest["guest_id"], 0)
        if time.time() - last < CHECKPOINT_MIN_SECONDS:
            return {"ok": True, "skipped": True}, b""
        with self.lock:
            conn = self.connect()
            try:
                data, generation = pp.export_guest(conn, guest["guest_id"], versions=versions(self.kit, self.cfg.get("server_dir")))
            finally:
                conn.close()
        self.last_checkpoint[guest["guest_id"]] = time.time()
        return {"ok": True, "generation": generation}, data

    def _go_home(self, guest, force):
        if guest["state"] == "gone":
            return {"ok": False, "code": "gone", "error": "This world no longer has that character."}, b""
        if guest["state"] == "active":
            if guest["online"]:
                return {"ok": False, "code": "online", "error": f"{guest['name']} is still in the game. Log out first."}, b""
            conn = self.connect()
            try:
                holdings = pp.guest_holdings(conn, guest["charid"])
            finally:
                conn.close()
            if (holdings["auctions"] or holdings["delivery"]) and not force:
                return {"ok": False, "code": "holdings", "holdings": holdings,
                        "error": "Some of your things are still in this world's auction house or delivery box."}, b""
        with self.lock:
            conn = self.connect()
            try:
                data, generation = pp.export_guest(conn, guest["guest_id"], final=True, save_dir=self.save_dir,
                                                   versions=versions(self.kit, self.cfg.get("server_dir")))
            finally:
                conn.close()
        if guest["state"] == "active":
            self.log(f"Co-op: {guest['name']} is on the way home.")
        return {"ok": True, "generation": generation}, data

    def _confirm(self, guest):
        if guest["state"] == "active":
            raise Refused("That character has not left yet.", "active")
        if guest["state"] == "left":
            with self.lock:
                conn = self.connect()
                try:
                    pp.remove_guest(conn, guest["guest_id"])
                finally:
                    conn.close()
            self.log(f"Co-op: {guest['name']} is home safely.")
        return {"ok": True}

    # --- what the host's own page does ---
    def guests(self):
        conn = self.connect()
        try:
            rows = pp.guest_list(conn)
        finally:
            conn.close()
        for row in rows:
            row["seen"] = self.last_seen.get(row["guest_id"])
        return rows

    def send_home(self, guest_id):
        """Ends a visit from the host's side: the character is saved for its trip home (it must be out of the game).
        Its launcher picks the passport up the next time it asks; until then nothing is deleted."""
        with self.lock:
            conn = self.connect()
            try:
                pp.export_guest(conn, guest_id, final=True, save_dir=self.save_dir,
                                versions=versions(self.kit, self.cfg.get("server_dir")))
            finally:
                conn.close()

    def send_everyone_home(self):
        """Stop hosting: every visitor who is out of the game is saved for the trip home. Returns the names still in game."""
        self.closing = True
        still = []
        for guest in self.guests():
            if guest["state"] != "active":
                continue
            try:
                self.send_home(guest["guest_id"])
            except pp.PassportError:
                still.append(guest["name"])
        return still

    def waiting(self):
        """Visitors whose characters are still here (playing, or saved and not picked up yet)."""
        return [g for g in self.guests() if g["state"] in ("active", "left")]


def world_rules(kit):
    """The few settings a visitor wants to know before coming over."""
    try:
        with open(os.path.join(kit, "rates.json"), encoding="utf-8") as handle:
            rates = json.load(handle)
    except (OSError, ValueError):
        rates = {}
    def number(key, default=1.0):
        try:
            return float(rates.get(key, default))
        except (TypeError, ValueError):
            return default
    return {"exp": number("map.EXP_RATE"), "drops": number("map.DROP_RATE_MULTIPLIER"), "skill": number("map.SKILLUP_CHANCE_MULTIPLIER"),
            "bots": bool(rates.get("bots", False)), "bots_online": int(number("bots_online", 0))}


def describe_rules(rules):
    rules = rules or {}
    def times(value):
        return ("%g" % float(value)) + "x"
    parts = [f"experience {times(rules.get('exp', 1))}", f"drops {times(rules.get('drops', 1))}", f"skill-ups {times(rules.get('skill', 1))}"]
    parts.append("bot players on" if rules.get("bots") else "no bot players")
    return ", ".join(parts)


# ----- talking to a host (the visitor's side) -----
def _post(address, port, key_header, body, timeout):
    request = urllib.request.Request(f"http://{address}:{int(port)}{PATH}", data=body, method="POST",
                                     headers={"X-Coop-Key": key_header, "Content-Type": "application/octet-stream"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # straight to the friend, never through a proxy
    with opener.open(request, timeout=timeout) as response:
        return response.read(MAX_BODY + 1024)


def call(where, key_header, key, obj, blob=b"", timeout=25, post=None):
    """One request to a host. Returns (reply dict, file bytes). Unreachable when nothing answers, Refused when it says no."""
    post = post or _post
    try:
        raw = post(where["address"], where["port"], key_header, seal(key, obj, blob), timeout)
    except CoopError:
        raise
    except Exception as e:
        code = getattr(e, "code", None)
        if code == 403:
            raise Refused("Your friend's launcher did not accept the invite code (or does not know this visit).", "key")
        raise Unreachable(f"Could not reach your friend's launcher at {where['address']} ({type(e).__name__}).")
    reply, data = unseal(key, raw)
    if not reply.get("ok"):
        raise Refused(str(reply.get("error") or "Your friend's launcher said no."), str(reply.get("code") or ""), reply)
    return reply, data


def hello(invite, post=None, timeout=12):
    reply, _data = call(invite, "invite", bytes.fromhex(invite["secret"]), {"op": "hello"}, timeout=timeout, post=post)
    return reply


def test_connection(invite, post=None, connect=socket.create_connection):
    """[(what, ok, detail)] for the Test connection button: the friend's launcher first, then each game port."""
    results = []
    try:
        reply = hello(invite, post=post, timeout=8)
        results.append(("Your friend's launcher", True, f"{reply['world']['name']} answered."))
    except Refused as e:
        results.append(("Your friend's launcher", False, str(e)))
        return results
    except CoopError as e:
        results.append(("Your friend's launcher", False, str(e) + " Is hosting switched on there, and are you on the same "
                        "network (or both in Tailscale)?"))
        return results
    for what, port in GAME_PORTS:
        try:
            connect((invite["address"], port), timeout=4).close()
            results.append((f"Game server ({what}, port {port})", True, "open"))
        except OSError:
            results.append((f"Game server ({what}, port {port})", False, "no answer: your friend has to press PLAY first, "
                            "or their firewall is in the way"))
    return results


# ----- a visit, from the visitor's launcher -----
def _dir(kit, name):
    path = os.path.join(kit, "coop", name)
    os.makedirs(path, exist_ok=True)
    return path


def _outgoing(kit, charid):
    return os.path.join(_dir(kit, "outgoing"), f"{int(charid)}.zip")


def checkpoint_file(kit, charid):
    return os.path.join(_dir(kit, "checkpoints"), f"{int(charid)}.zip")


def _write(path, data):
    with open(path + ".part", "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(path + ".part", path)


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def away(cfg, connect=None):
    """This world's characters that are visiting somewhere: [{charid, name, host, since, ...}]."""
    conn = (connect or (lambda: pp.connect(cfg)))()
    try:
        return pp.away_list(conn)
    finally:
        conn.close()


def start_visit(cfg, kit, invite, charid, log=print, post=None, connect=None):
    """The character leaves for the invite's world. Returns what the host answered (login, address, ...).
    If the host says no, the character is unlocked again at once. If the host cannot be reached after the character was
    packed, it stays packed: finish_arrival() tries again, cancel_visit() unpacks it."""
    connect = connect or (lambda: pp.connect(cfg))
    mine = versions(kit, cfg.get("server_dir"))
    greeting = hello(invite, post=post)
    if not greeting.get("open"):
        raise Refused("That world is not taking visitors right now.", "closed")
    clash = versions_clash(mine, greeting.get("versions"))
    if clash:
        raise Refused(clash, "version")
    conn = connect()
    try:
        if greeting.get("schema") != pp.schema_signature(conn):
            raise Refused("The two worlds are on different versions. Update both to the newest version first.", "version")
        if greeting["world"]["id"] == pp.world_identity(conn)["id"]:
            raise Refused("That invite is for your own world.", "self")
        guest_id = secrets.token_hex(12)
        host = {"address": invite["address"], "port": invite["port"], "guest_id": guest_id,
                "gkey": guest_key(invite["secret"], guest_id), "secret": invite["secret"], "world": greeting["world"],
                "arrived": False, "started": int(time.time())}
        data, _nonce = pp.depart(conn, charid, host, versions=mine)
    finally:
        conn.close()
    _write(_outgoing(kit, charid), data)
    _remove(checkpoint_file(kit, charid))
    log(f"Packed for the trip to {greeting['world']['name']}.")
    return finish_arrival(cfg, kit, charid, log=log, post=post, connect=connect)


def _away_row(cfg, charid, connect):
    for row in away(cfg, connect):
        if row["charid"] == int(charid):
            return row
    raise CoopError("That character is not visiting another world.")


def finish_arrival(cfg, kit, charid, log=print, post=None, connect=None):
    """Hands the packed character to the host (again, if the first try got no answer)."""
    connect = connect or (lambda: pp.connect(cfg))
    row = _away_row(cfg, charid, connect)
    host = row["host"]
    if host.get("arrived"):
        return host
    try:
        with open(_outgoing(kit, charid), "rb") as handle:
            data = handle.read()
    except OSError:
        raise CoopError("The packed character is missing. Use Cancel visit to unpack it as it was.")
    conn = connect()
    try:
        mine = pp.own_character_ids(conn)
    finally:
        conn.close()
    try:
        reply, _blob = call(host, "invite", bytes.fromhex(host["secret"]),
                            {"op": "arrive", "guest_id": host["guest_id"], "versions": versions(kit, cfg.get("server_dir")),
                             "avoid": mine}, blob=data, timeout=60, post=post)
    except Refused as e:
        if e.code in ("key", "busy"):
            raise
        conn = connect()                      # a clear no: nothing was made over there, so unpack at once
        try:
            pp.take_back(conn, charid)
        finally:
            conn.close()
        _remove(_outgoing(kit, charid))
        raise
    host.update({"arrived": True, "login": reply["login"], "host_charid": int(reply["charid"]), "fingerprint": reply.get("fingerprint"),
                 "game_address": reply.get("address") or host["address"], "last_ok": int(time.time())})
    host.pop("secret", None)                  # from here on the visitor's own key is used
    conn = connect()
    try:
        pp.update_away(conn, charid, host=host)
    finally:
        conn.close()
    _remove(_outgoing(kit, charid))
    try:                                      # macros and settings follow the character when it got another id there
        copy_user_folder(cfg.get("ffxi_client_dir"), charid, host["host_charid"])
    except Exception:
        pass
    log(f"{row['name']} has arrived in {host['world'].get('name', 'the other world')}.")
    return host


def _guest_call(host, obj, blob=b"", timeout=25, post=None):
    return call(host, "guest:" + host["guest_id"], bytes.fromhex(host["gkey"]), obj, blob=blob, timeout=timeout, post=post)


def can_take_back(host, now=None):
    """(allowed, why). Allowed at once when the character never arrived, else after the host was out of reach long enough."""
    now = now or time.time()
    if not host.get("arrived"):
        return True, "The character never arrived there."
    since = host.get("unreachable_since")
    if host.get("gone"):
        return True, "That world no longer has the character."
    if since and now - since >= TAKE_BACK_HOURS * 3600:
        return True, f"Your friend's world has been out of reach for over {TAKE_BACK_HOURS} hours."
    if since:
        left = TAKE_BACK_HOURS - (now - since) / 3600
        return False, f"Out of reach for now. Take back opens in about {max(1, int(left + 0.5))} hour(s)."
    return False, "Your friend's world can be reached: use Come home."


def _save_host(cfg, charid, host, connect, generation=None):
    conn = connect()
    try:
        pp.update_away(conn, charid, host=host, generation=generation)
    finally:
        conn.close()


def keep_visit(cfg, kit, row, log=print, post=None, connect=None, now=None):
    """One look at a visit (the launcher does this every 20 seconds or so): is the host there, is it time for a fresh
    copy, was the character sent home. Returns a short word for what happened."""
    connect = connect or (lambda: pp.connect(cfg))
    now = now or time.time()
    host, charid = row["host"], row["charid"]
    if not host.get("arrived"):
        return "not-arrived"
    try:
        status, _blob = _guest_call(host, {"op": "status"}, timeout=12, post=post)
    except Unreachable:
        if not host.get("unreachable_since"):
            host["unreachable_since"] = int(now)
            _save_host(cfg, charid, host, connect)
        return "unreachable"
    except Refused as e:
        if e.code == "key" and not host.get("unreachable_since"):     # what answered does not know this visit: the same
            host["unreachable_since"] = int(now)                       # as out of reach, so take back needs the same wait
            _save_host(cfg, charid, host, connect)
        return "unreachable" if e.code == "key" else "busy"
    changed = bool(host.pop("unreachable_since", None))
    host.update({"last_ok": int(now), "online": bool(status.get("online")), "closing": bool(status.get("closing")),
                 "holdings": status.get("holdings") or {}})
    if status.get("fingerprint") and status["fingerprint"] != host.get("fingerprint"):
        host["fingerprint"], changed = status["fingerprint"], True
    if status.get("address") and valid_address(status["address"]) and status["address"] != host.get("game_address"):
        host["game_address"], changed = status["address"], True
    result = "ok"
    if status.get("state") == "gone":
        host["gone"] = True
        result = "gone"
    elif status.get("state") == "left":
        _save_host(cfg, charid, host, connect)
        come_home(cfg, kit, charid, log=log, post=post, connect=connect)
        return "home"
    elif now - host.get("checkpoint_at", 0) >= CHECKPOINT_SECONDS and \
            (status.get("online") or int(status.get("generation", 0)) > int(host.get("checkpoint_gen", 0)) or not host.get("checkpoint_at")):
        try:
            reply, data = _guest_call(host, {"op": "checkpoint"}, timeout=60, post=post)
            if data:
                _write(checkpoint_file(kit, charid), data)
                host.update({"checkpoint_at": int(now), "checkpoint_gen": int(reply.get("generation", 0))})
                result = "checkpoint"
        except CoopError:
            pass
    if changed or result != "ok" or now - host.get("saved_at", 0) > 120:
        host["saved_at"] = int(now)
        _save_host(cfg, charid, host, connect, generation=host.get("checkpoint_gen"))
    return result


def come_home(cfg, kit, charid, force=False, log=print, post=None, connect=None):
    """Fetches the character from the host and puts it back at home. Returns pp.come_home()'s result.
    Refused with code "online" (still in the game there) or "holdings" (things left in the auction house or delivery
    box; force=True comes home without them)."""
    connect = connect or (lambda: pp.connect(cfg))
    row = _away_row(cfg, charid, connect)
    host = row["host"]
    reply, data = _guest_call(host, {"op": "go_home", "force": bool(force)}, timeout=90, post=post)
    conn = connect()
    try:
        result = pp.come_home(conn, data, backup_dir=os.path.join(kit, "backups", "coop"))
    finally:
        conn.close()
    try:
        _guest_call(host, {"op": "confirm_home", "generation": reply.get("generation")}, timeout=30, post=post)
    except CoopError:                         # the host keeps the spent copy until it hears; nothing is lost either way
        result.setdefault("notes", []).append("Your friend's launcher has not been told yet that the trip home is done.")
    _remove(checkpoint_file(kit, charid))
    try:
        copy_user_folder(cfg.get("ffxi_client_dir"), host.get("host_charid"), charid)
    except Exception:
        pass
    log(f"{result['name']} is home.")
    return result


def take_back(cfg, kit, charid, log=print, connect=None):
    """Ends a visit without the host: from the newest checkpoint when there is one, else as the character was before."""
    connect = connect or (lambda: pp.connect(cfg))
    checkpoint = None
    try:
        with open(checkpoint_file(kit, charid), "rb") as handle:
            checkpoint = handle.read()
    except OSError:
        pass
    conn = connect()
    try:
        try:
            result = pp.take_back(conn, charid, checkpoint=checkpoint, backup_dir=os.path.join(kit, "backups", "coop"))
        except pp.PassportError:
            if checkpoint is None:
                raise
            result = pp.take_back(conn, charid)            # a checkpoint of some older visit: use the pre-visit copy
            checkpoint = None
    finally:
        conn.close()
    result["from_checkpoint"] = checkpoint is not None
    _remove(checkpoint_file(kit, charid))
    _remove(_outgoing(kit, charid))
    log(f"{result['name']} was taken back.")
    return result


def cancel_visit(cfg, kit, charid, log=print, connect=None):
    """A trip that never got there (the host did not answer): the character is unpacked as it was."""
    connect = connect or (lambda: pp.connect(cfg))
    if _away_row(cfg, charid, connect)["host"].get("arrived"):
        raise CoopError("That character has arrived. Use Come home instead.")
    conn = connect()
    try:
        result = pp.take_back(conn, charid)
    finally:
        conn.close()
    _remove(_outgoing(kit, charid))
    log(f"{result['name']} stays home.")
    return result


def load_return_file(cfg, kit, path, connect=None):
    """A going-home passport the host sent as a file (when the two launchers could not talk)."""
    with open(path, "rb") as handle:
        data = handle.read()
    conn = (connect or (lambda: pp.connect(cfg)))()
    try:
        return pp.come_home(conn, data, backup_dir=os.path.join(kit, "backups", "coop"))
    finally:
        conn.close()


# ----- the visitor's game: boot file and macros -----
def visit_command(command, address, login, password, fingerprint=None):
    """An Ashita boot 'command' line pointed at the friend's server with the visitor's login."""
    parts = str(command or "").split()
    out, skip = [], False
    for part in parts:
        if skip:
            skip = False
            continue
        if part in ("--server", "--user", "--username", "--pass", "--password", "--fingerprint"):
            skip = True
            continue
        out.append(part)
    command = f"--server {address} --user {login} --pass {password}"
    if fingerprint and re.fullmatch(r"SHA256:[A-Za-z0-9+/]{20,64}", fingerprint):
        command += f" --fingerprint {fingerprint}"
    return (command + " " + " ".join(out)).strip()


def write_visit_boot(ashita_dir, base_boot, host):
    """config/boot/xiforever-coop.ini: the player's own boot file with the server and login changed. Returns its name."""
    if not valid_address(host.get("game_address") or host.get("address")):
        raise CoopError("The host's address is not usable.")
    boot_dir = os.path.join(ashita_dir, "config", "boot")
    with open(os.path.join(boot_dir, base_boot), encoding="utf-8-sig", errors="replace") as handle:
        text = handle.read()
    password = guest_password(host["gkey"])
    command = None

    def swap(match):
        nonlocal command
        command = visit_command(match.group(2), host.get("game_address") or host["address"], host["login"], password, host.get("fingerprint"))
        return match.group(1) + command

    text, count = re.subn(r"(?m)^(command\s*=\s*)(.*)$", swap, text, count=1)
    if count == 0:
        raise CoopError("Your Ashita boot file has no 'command' line to point at your friend's world.")
    with open(os.path.join(boot_dir, VISIT_BOOT), "w", encoding="utf-8", newline="\r\n") as handle:
        handle.write(text)
    return VISIT_BOOT


def user_folder(ffxi_dir, charid):
    return os.path.join(ffxi_dir, "USER", format(int(charid), "x"))


def copy_user_folder(ffxi_dir, from_id, to_id):
    """The game keeps macros and settings in USER/<character id>. A visitor can get another id in the friend's world, so
    its folder is copied across (and back when it comes home). Returns True when something was copied."""
    if not ffxi_dir or not from_id or not to_id or int(from_id) == int(to_id):
        return False
    source, target = user_folder(ffxi_dir, from_id), user_folder(ffxi_dir, to_id)
    if not os.path.isdir(source):
        return False
    os.makedirs(target, exist_ok=True)
    for name in os.listdir(source):
        path = os.path.join(source, name)
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(target, name))
    return True


# ----- the host's PC: addresses, the zone address, the firewall, the server's key -----
def address_kind(address):
    try:
        a, b = [int(x) for x in address.split(".")[:2]]
    except ValueError:
        return "other"
    if a == 127:
        return "loopback"
    if a == 100 and 64 <= b <= 127:
        return "tailscale"
    if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168):
        return "lan"
    if a == 169 and b == 254:
        return "none"
    return "direct"


def local_addresses():
    """This PC's IPv4 addresses with what each is good for: [{"address", "kind"}], the main network first."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:      # no packet is sent: this only asks the route
            probe.connect(("10.255.255.255", 1))
            found.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        found.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    tail = tailscale_address()
    if tail:
        found.append(tail)
    out, seen = [], set()
    for address in found:
        kind = address_kind(address)
        if address not in seen and kind in ("lan", "tailscale", "direct"):
            seen.add(address)
            out.append({"address": address, "kind": kind})
    return out


def tailscale_program():
    """Where tailscale.exe is when Tailscale is installed on this PC, else None."""
    if os.name != "nt":                          # Linux: Tailscale from the system's own packages
        return shutil.which("tailscale")
    program = shutil.which("tailscale") or os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Tailscale", "tailscale.exe")
    return program if os.path.exists(program) else None


def tailscale_address(run=subprocess.run):
    """This PC's Tailscale address (100.x.y.z) when Tailscale is installed and running, else None."""
    program = tailscale_program()
    if program is None:
        return None
    try:
        result = run([program, "ip", "-4"], capture_output=True, text=True, errors="replace", timeout=8, creationflags=NO_WINDOW if os.name == "nt" else 0)
        found = re.search(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", result.stdout or "")
        return found.group(0) if found else None
    except Exception:
        return None


def tailscale_state(run=subprocess.run):
    """"missing": not installed. "off": installed, but it has no address (not signed in yet, or switched off). "ready"."""
    if tailscale_program() is None:
        return "missing"
    return "ready" if tailscale_address(run) else "off"


def _tailscale_site(url):
    """An https address at tailscale.com? (The installer comes from pkgs.tailscale.com, which may hand over to another
    of Tailscale's own servers.)"""
    parts = urllib.parse.urlparse(str(url or ""))
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "tailscale.com" or host.endswith(".tailscale.com"))


def download_tailscale(kit, log=print, opener=None):
    """Fetches Tailscale's Windows installer from Tailscale's own site into <kit>\\coop\\downloads. Returns its path.
    Nothing is started here. CoopError says why when it could not be fetched."""
    folder = os.path.join(kit, "coop", "downloads")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "tailscale-setup.exe")
    part = path + ".part"

    def tidy():
        try:
            os.remove(part)
        except OSError:
            pass

    request = urllib.request.Request(TAILSCALE_INSTALLER, headers={"User-Agent": "XI-Forever-Offline-launcher"})
    size, first = 0, b""
    try:
        with (opener or urllib.request.urlopen)(request, timeout=30) as response:
            if not _tailscale_site(response.geturl()):
                raise CoopError("The download was passed on to a site that is not Tailscale's, so it was stopped.")
            with open(part, "wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    first = first or chunk[:2]
                    size += len(chunk)
                    if size > TAILSCALE_MAX_BYTES:
                        raise CoopError("The download is far too big to be Tailscale's installer, so it was stopped.")
                    handle.write(chunk)
    except CoopError:
        tidy()
        raise
    except (OSError, ValueError) as e:              # no internet, the site is down, the address has moved...
        tidy()
        raise CoopError(f"Tailscale's installer could not be downloaded ({getattr(e, 'reason', None) or e}).")
    if size < 1024 * 1024 or first != b"MZ":        # an error page, not a Windows program
        tidy()
        raise CoopError("What came back is not Tailscale's installer.")
    os.replace(part, path)
    log(f"Tailscale's installer is downloaded ({size // (1024 * 1024)} MB).")
    return path


def signed_by_tailscale(path, run=subprocess.run):
    """(ok, detail): does Windows vouch that this file was signed by Tailscale Inc. and has not been changed since?
    (PowerShell's Get-AuthenticodeSignature; the file's path travels in an environment variable, not in the command.)"""
    script = ("$s = Get-AuthenticodeSignature -LiteralPath $env:XIFO_CHECK_FILE; Write-Output ([string]$s.Status); "
              "if ($s.SignerCertificate) { Write-Output $s.SignerCertificate.Subject }")
    try:
        result = run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                     capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=60, env=dict(os.environ, XIFO_CHECK_FILE=path))
    except Exception as e:
        return False, f"its signature could not be checked ({type(e).__name__})"
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    status, signer = (lines[0] if lines else ""), (lines[1] if len(lines) > 1 else "")
    if status == "Valid" and re.search(r'(?:^|,\s*)(?:CN|O)="?Tailscale Inc\.?"?\s*(?:,|$)', signer):
        return True, signer
    return False, f"signature: {status or 'none'}" + (f", signed by {signer}" if signer else "")


def install_tailscale(kit, log=print, run=subprocess.run, opener=None, start=None):
    """The GET TAILSCALE button: downloads Tailscale's installer, makes sure Windows trusts it as Tailscale's own, and
    starts it (the player clicks through it and signs in). Returns the installer's path. CoopError when a step fails:
    then nothing was started."""
    if os.name != "nt":
        raise CoopError("On Linux, Tailscale is installed from tailscale.com/download/linux (it needs administrator "
                        "rights, so the launcher can't do it; on a Steam Deck, look up Tailscale's Steam Deck guide). "
                        "Playing together on the same network works without it.")
    path = download_tailscale(kit, log, opener)
    ok, detail = signed_by_tailscale(path, run)
    if not ok:
        try:
            os.remove(path)
        except OSError:
            pass
        raise CoopError(f"The downloaded file does not carry Tailscale's signature ({detail}), so it was not started.")
    try:
        (start or os.startfile)(path)
    except OSError as e:
        raise CoopError(f"The installer could not be started ({e}). It is here if you want to start it yourself: {path}")
    log("Tailscale's installer has started.")
    return path


def is_local_address(address):
    """True when this PC has that address right now (a network it has left, or Tailscale switched off, gives False)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((address, 0))
        return True
    except OSError:
        return False


def suggest_address(mode, addresses=None):
    for item in (addresses if addresses is not None else local_addresses()):
        if item["kind"] == mode:
            return item["address"]
    return ""


def zone_address(cfg, connect=None):
    """The address the game server tells clients to use for the world (zone_settings.zoneip), or None when mixed."""
    conn = (connect or (lambda: pp.connect(cfg)))()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT zoneip FROM zone_settings")
        rows = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.rollback()
        return rows[0] if len(rows) == 1 else None
    finally:
        conn.close()


def set_zone_address(cfg, address, connect=None):
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", str(address)):
        raise CoopError("The game server needs a number address like 192.168.1.20 for the world.")
    conn = (connect or (lambda: pp.connect(cfg)))()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE zone_settings SET zoneip = ?", (address,))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def prepare_world(cfg, kit, settings, log=print, connect=None, is_local=None):
    """Before the servers start: point the world at the hosting address, or back at this PC when hosting was switched
    off (only if this launcher was the one that changed it). Returns True when hosting is set up.
    The hosting address must still be this PC's: if the PC got another one on the same kind of network that one is used
    (friends then need the new invite code); if it is on no such network now, the world stays private this time,
    because the game cannot even be reached by its owner on an address the PC does not have."""
    is_local = is_local or is_local_address
    hosting = bool(settings.get("enabled") and settings.get("hosting") and settings.get("address"))
    if hosting and not is_local(settings["address"]):
        other = suggest_address(settings.get("mode", "lan"))
        if other and is_local(other):
            log(f"Co-op: this PC's address changed from {settings['address']} to {other}. Your friends need the new invite code (CO-OP page).")
            settings["address"] = other
            save_settings(kit, settings)
        else:
            what = "Tailscale is not running" if settings.get("mode") == "tailscale" else "this PC is not on that network right now"
            log(f"Co-op: {what} ({settings['address']} is not this PC's address), so your world stays private this time.")
            hosting = False
    current = zone_address(cfg, connect)
    if hosting:
        if current != settings["address"]:
            set_zone_address(cfg, settings["address"], connect)
            log(f"Co-op: the world now answers on {settings['address']} for you and your friends.")
        if settings.get("zoneip_set") != settings["address"]:
            settings["zoneip_set"] = settings["address"]
            save_settings(kit, settings)
    elif settings.get("zoneip_set"):
        if current == settings["zoneip_set"]:
            set_zone_address(cfg, "127.0.0.1", connect)
            log("Co-op: hosting is off, the world is private to this PC again.")
        settings["zoneip_set"] = ""
        save_settings(kit, settings)
    write_host_config(cfg.get("server_dir"), hosting, connect or (lambda: pp.connect(cfg)))
    return hosting


def write_host_config(server_dir, hosting, connect):
    """modules/custom/lua/coop_config.lua for the server's co-op script (read when the server starts)."""
    if not server_dir:
        return
    name = "This world"
    try:
        conn = connect()
        try:
            name = pp.world_identity(conn)["name"]
        finally:
            conn.close()
    except Exception:
        pass
    safe = name.replace("\\", "").replace("'", "\\'")
    target = os.path.join(server_dir, "modules", "custom", "lua", "coop_config.lua")
    try:
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("-- Written by the XI: Forever Offline launcher (CO-OP page) at every PLAY.\n"
                         f"return {{ hosting = {'true' if hosting else 'false'}, world = '{safe}' }}\n")
    except OSError:
        pass


_announce_lock = threading.Lock()


def announce(server_dir, text, kind="SAY"):
    """A line every player in the world sees within a few seconds (read by the server's co-op script). kind="BOTS" with
    a number instead changes how many bot players are online."""
    if not server_dir:
        return
    text = re.sub(r"[\r\n|]+", " ", str(text))[:150]
    path = os.path.join(server_dir, "modules", "custom", "lua", "coop_in.txt")
    try:
        with _announce_lock:
            lines = []
            try:
                with open(path, encoding="utf-8") as handle:
                    lines = [line for line in handle.read().splitlines() if line.strip()][-20:]
            except OSError:
                pass
            last = 0
            for line in lines:
                try:
                    last = max(last, int(line.split("|")[1]))
                except (IndexError, ValueError):
                    pass
            lines.append(f"{int(time.time())}|{last + 1}|{kind}|{text}")
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines) + "\n")
    except OSError:
        pass


def firewall_script(server_dir, port, mode):
    """PowerShell that lets friends reach the game servers and the co-op port (and removes our older rules first)."""
    scope = SCOPES.get(mode, "LocalSubnet")
    programs = ", ".join("'" + ntpath.normpath(ntpath.join(server_dir, name + ".exe")).replace("'", "''") + "'" for name in SERVER_PROGRAMS)
    return (f"$n = '{FIREWALL_RULE}'; "
            "Get-NetFirewallRule -DisplayName $n -ErrorAction SilentlyContinue | Remove-NetFirewallRule; "
            f"foreach ($p in @({programs})) {{ "
            "Get-NetFirewallApplicationFilter -Program $p -ErrorAction SilentlyContinue | Get-NetFirewallRule | "
            "Where-Object { $_.Action -eq 'Block' -and $_.Direction -eq 'Inbound' } | Remove-NetFirewallRule; "
            f"New-NetFirewallRule -DisplayName $n -Direction Inbound -Action Allow -Program $p -RemoteAddress {scope} -Profile Any | Out-Null }}; "
            f"New-NetFirewallRule -DisplayName $n -Direction Inbound -Action Allow -Protocol TCP -LocalPort {int(port)} "
            f"-RemoteAddress {scope} -Profile Any | Out-Null; "
            "(Get-NetFirewallRule -DisplayName $n | Measure-Object).Count")


def firewall_open(server_dir, port, mode, run=subprocess.run):
    """Adds the rules (the launcher already runs as administrator). Returns (ok, text)."""
    if os.name != "nt":                          # Linux: most desktops (and SteamOS) have no firewall switched on
        ports = ", ".join(str(p) for _name, p in GAME_PORTS)
        return True, f"Linux: if this PC has a firewall switched on, let in TCP ports {ports} and {int(port)}, and UDP 54230."
    try:
        result = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", firewall_script(server_dir, port, mode)],
                     capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=60)
    except Exception as e:
        return False, f"Could not change the Windows firewall ({type(e).__name__})."
    count = (result.stdout or "").strip().splitlines()[-1:] or [""]
    if result.returncode == 0 and count[0].isdigit() and int(count[0]) >= len(SERVER_PROGRAMS) + 1:
        return True, "Windows firewall: open for your friends."
    return False, "Could not change the Windows firewall: " + ((result.stderr or result.stdout or "").strip()[-300:] or "no answer")


def firewall_close(run=subprocess.run):
    if os.name != "nt":
        return True
    try:
        run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
             f"Get-NetFirewallRule -DisplayName '{FIREWALL_RULE}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"],
            capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=60)
        return True
    except Exception:
        return False


def _der_item(data, offset):
    """(tag, start of the value, end of the item) of the DER item at `offset`."""
    tag, length, pos = data[offset], data[offset + 1], offset + 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    return tag, pos, pos + length


def certificate_fingerprint(pem_text):
    """SHA256:<base64> of the public key in a certificate, the way xiloader 3 shows and checks it (--fingerprint)."""
    found = re.search(r"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----", pem_text, re.S)
    if not found:
        return None
    der = base64.b64decode("".join(found.group(1).split()))
    _tag, start, _end = _der_item(der, 0)                 # Certificate
    _tag, pos, end = _der_item(der, start)                # TBSCertificate
    items = []
    while pos < end:
        tag, _value, after = _der_item(der, pos)
        items.append((tag, pos, after))
        pos = after
    if items and items[0][0] == 0xA0:                     # the optional version field
        items = items[1:]
    if len(items) < 6:
        return None
    _tag, key_start, key_end = items[5]                   # serial, algorithm, issuer, validity, subject, then the key
    digest = hashlib.sha256(der[key_start:key_end]).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def server_fingerprint(server_dir):
    """The key of this PC's game server, for the visitor's loader (None before the server has ever run)."""
    if not server_dir:
        return None
    try:
        with open(os.path.join(server_dir, "login.cert"), encoding="ascii", errors="replace") as handle:
            return certificate_fingerprint(handle.read())
    except (OSError, ValueError, IndexError):
        return None


def full_backup(cfg, kit, log=print, run=subprocess.run):
    """A copy of the whole database, made once when co-op is first switched on. Returns the file, or None."""
    backups = os.path.join(kit, "backups")
    os.makedirs(backups, exist_ok=True)
    path = os.path.join(backups, f"db-before-coop-{time.strftime('%Y%m%d-%H%M%S')}.sql")
    env = None
    if cfg.get("mariadb_dir") and os.name != "nt":       # Linux: the kit's MariaDB package (and never /etc/my.cnf)
        import launcher_setup
        tool = launcher_setup.mariadb_cmd(cfg["mariadb_dir"], "mariadb-dump")
        env = launcher_setup.mariadb_env(cfg["mariadb_dir"])
    elif cfg.get("mariadb_dir"):
        tool = [os.path.join(cfg["mariadb_dir"], "bin", "mariadb-dump.exe")]
    else:
        tool = [shutil.which("mariadb-dump") or shutil.which("mysqldump") or "mysqldump"]
    command = tool + [f"--host={cfg.get('db_host', '127.0.0.1')}", f"--port={int(cfg.get('db_port', 3306))}", f"--user={cfg['db_user']}",
               f"--password={cfg['db_pass']}", "--single-transaction", f"--result-file={path}", cfg["db_name"]]
    try:
        result = run(command, capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=900,
                     **({"env": env} if env else {}))
        if result.returncode == 0 and os.path.exists(path):
            log("Co-op: saved a copy of your database first (backups folder).")
            return path
    except Exception:
        pass
    log("Co-op: could not save a copy of the whole database (your characters are still backed up at each trip).")
    return None
