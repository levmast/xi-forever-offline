#!/usr/bin/env python3
"""The worlds list (XI: Forever Offline, 2026-11-23): open worlds list themselves here, and every launcher's CO-OP page
shows them under OPEN WORLDS. Runs on the hub server behind Caddy (https://hub.xiforever.com/worlds).

Standard library only. It keeps nothing but world links: each world's name, description, banner and visitor count are
asked from the world itself by the players' launchers, checked against the key in its link, so nobody can put up a
card for someone else's world.

  POST /worlds/announce {"link"}  a world says it is open (its launcher does this every 5 minutes). Kept only if the world
                                  answers at the address in its link with the key in its link (TLS), from a public address.
  GET  /worlds                    {"worlds": [{"link", "seen"}]}: the worlds heard from in the last 15 minutes
  GET  /worlds/health
Moderation (the owner only, with the code in owner.txt): POST /worlds/hide {"code", "pin"} hides a world for good,
POST /worlds/unhide {"code", "pin"}.
Run: python3 worldlist_service.py [--port 54301] [--data /var/lib/xifo-worldlist]
"""
import argparse
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FRESH = 15 * 60          # a world not heard from for this long drops off the list
MOST = 200               # the most worlds on the list
PER_ADDRESS = 5          # the most listed worlds behind one public address
RATE = 30                # one announce per world per this many seconds
LINK_RE = re.compile(r"^XIFO2-[A-Za-z0-9_\-]{20,600}$")


def read_link(link):
    """{address, port, pin, world} from a world link (XIFO2-<base64url json>), or None."""
    link = re.sub(r"\s+", "", str(link or ""))
    if not LINK_RE.match(link):
        return None
    try:
        raw = link[6:]
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        address, port, pin = str(data["a"]), int(data["p"]), str(data["f"])
    except Exception:
        return None
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", address) or not 1 <= port <= 65535:
        return None
    if not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{20,64}", pin):
        return None
    return {"address": address, "port": port, "pin": pin, "link": link}


def public(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_global and not ip.is_multicast and not ip.is_reserved


def _der_item(data, offset):
    tag, length, pos = data[offset], data[offset + 1], offset + 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    return tag, pos, pos + length


def key_fingerprint(der):
    """SHA256:<base64> of the public key in a DER certificate (the same as the launcher and xiloader 3)."""
    _tag, start, _end = _der_item(der, 0)
    _tag, pos, end = _der_item(der, start)
    items = []
    while pos < end:
        tag, _value, after = _der_item(der, pos)
        items.append((tag, pos, after))
        pos = after
    if items and items[0][0] == 0xA0:
        items = items[1:]
    _tag, key_start, key_end = items[5]
    return "SHA256:" + base64.b64encode(hashlib.sha256(der[key_start:key_end]).digest()).decode().rstrip("=")


def check_world(address, port, pin, timeout=6):
    """True when a TLS server answers there with that key (an open world's launcher does)."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((address, port), timeout=timeout) as raw:
            with context.wrap_socket(raw) as conn:
                der = conn.getpeercert(binary_form=True)
        return bool(der) and key_fingerprint(der) == pin
    except Exception:
        return False


class WorldList:
    def __init__(self, data, check=check_world, allow_private=False):
        self.data, self.check, self.allow_private = data, check, allow_private
        self.lock = threading.Lock()
        self.worlds = {}        # pin -> {"link", "address", "seen"}
        self.state = {"hidden": {}}
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
            self.owner = handle.read().strip()

    def save(self):
        path = os.path.join(self.data, "state.json")
        with open(path + ".part", "w", encoding="utf-8") as handle:
            json.dump(self.state, handle)
        os.replace(path + ".part", path)

    def announce(self, link, now=None):
        now = now or time.time()
        world = read_link(link)
        if world is None:
            return {"ok": False, "error": "That is not a world link."}
        if world["pin"] in self.state["hidden"]:
            return {"ok": False, "error": "This world is not listed."}
        if not self.allow_private and not public(world["address"]):
            return {"ok": False, "error": "Only worlds at a public internet address can be listed (this one is on a home "
                                          "network or Tailscale, which other players cannot reach)."}
        with self.lock:
            known = self.worlds.get(world["pin"])
            if known and known["link"] == world["link"] and now - known["seen"] < RATE:
                return {"ok": True}
            same = [w for p, w in self.worlds.items() if w["address"] == world["address"] and p != world["pin"]
                    and now - w["seen"] < FRESH]
            if len(same) >= PER_ADDRESS:
                return {"ok": False, "error": "Too many worlds at that address."}
            if not known and len([w for w in self.worlds.values() if now - w["seen"] < FRESH]) >= MOST:
                return {"ok": False, "error": "The list is full right now."}
        if not self.check(world["address"], world["port"], world["pin"]):
            return {"ok": False, "error": "Your world did not answer from the internet at the address in its link "
                                          "(is its port open in the firewall?)."}
        with self.lock:
            self.worlds[world["pin"]] = {"link": world["link"], "address": world["address"], "seen": now}
        return {"ok": True}

    def listing(self, now=None):
        now = now or time.time()
        with self.lock:
            for pin in [p for p, w in self.worlds.items() if now - w["seen"] >= FRESH]:
                del self.worlds[pin]
            rows = sorted(self.worlds.values(), key=lambda w: -w["seen"])
        return {"worlds": [{"link": w["link"], "seen": int(w["seen"])} for w in rows[:MOST]]}

    def hide(self, code, pin, on=True):
        if not secrets.compare_digest(str(code), self.owner):
            return {"ok": False, "error": "no"}
        with self.lock:
            if on:
                self.state["hidden"][str(pin)] = int(time.time())
                self.worlds.pop(str(pin), None)
            else:
                self.state["hidden"].pop(str(pin), None)
            self.save()
        return {"ok": True}


def make_handler(worlds):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XIFO-Worlds/1"

        def log_message(self, *args):
            pass

        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=60")
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            size = int(self.headers.get("Content-Length") or 0)
            if size <= 0 or size > 4096:
                return {}
            try:
                value = json.loads(self.rfile.read(size))
                return value if isinstance(value, dict) else {}
            except ValueError:
                return {}

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/")
            if path == "/worlds":
                return self.reply(200, worlds.listing())
            if path == "/worlds/health":
                return self.reply(200, {"ok": True, "worlds": len(worlds.listing()["worlds"])})
            return self.reply(404, {"error": "unknown"})

        def do_POST(self):
            path = self.path.split("?")[0].rstrip("/")
            body = self.body()
            if path == "/worlds/announce":
                return self.reply(200, worlds.announce(body.get("link")))
            if path in ("/worlds/hide", "/worlds/unhide"):
                return self.reply(200, worlds.hide(body.get("code"), body.get("pin"), path.endswith("/hide")))
            return self.reply(404, {"error": "unknown"})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="XI: Forever Offline worlds list")
    ap.add_argument("--port", type=int, default=54301)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--data", default="/var/lib/xifo-worldlist")
    args = ap.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(WorldList(args.data)))
    server.daemon_threads = True
    print(f"Worlds list on {args.host}:{args.port}, data in {args.data}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
