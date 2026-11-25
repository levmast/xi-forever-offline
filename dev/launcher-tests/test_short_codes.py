"""Short invite codes (2026-11-23): sealing, the hub's code book, and falling back to the long code."""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "worldlist"))
import launcher_coop as co
import worldlist_service as ws

co.SHORT_ROUNDS = 2000          # (fast for the test; the real code uses 200000)
passed = 0


def check(what, ok):
    global passed
    if not ok:
        raise SystemExit("FAIL: " + what)
    passed += 1


book = ws.CodeBook(tempfile.mkdtemp())


def fetch(url, body):
    kind = url.rsplit("/", 1)[1]
    return json.dumps(getattr(book, kind)(body, "203.0.113.5"))


def down(url, body):
    raise OSError("no internet")


long_code = co.make_invite("100.64.1.2", 54100, os.urandom(16).hex(), "Kupo Land")
for _ in range(200):
    c = co.make_short()
    check("shape " + c, co.short_code(c) == c and len(c) == 12 and c[:6].isalpha() and c[6:9].isdigit() and c[9:].isalpha())
    check("no I/O/0/1", not set(c) & set("IO01"))
code = co.make_short()
shown = co.show_short(code)
check("shown with dashes", shown.count("-") == 2 and co.short_code(shown) == code)
check("typed loosely", co.short_code(" " + shown.lower().replace("-", " ") + " ") == code)
check("long code is not short", co.short_code(long_code) is None)
check("too short", co.short_code("ABCDEF-234-XY") is None)

token = "a" * 32
check("register", co.register_short(code, long_code, token, fetch=fetch))
check("hub keeps no secret", json.loads(long_code[6:] + "") if False else co.read_invite(long_code)["secret"] not in json.dumps(book.codes))
check("hub keeps no address", "100.64.1.2" not in json.dumps(book.codes))
check("resolve", co.resolve_short(shown, fetch=fetch) == long_code)
check("resolve typed loosely", co.resolve_short(shown.lower(), fetch=fetch) == long_code)
try:
    co.resolve_short(co.make_short(), fetch=fetch)
    check("unknown code refused", False)
except co.CoopError as e:
    check("unknown code says so", "isn't known" in str(e))
try:
    co.resolve_short(shown, fetch=down)
    check("no hub refused", False)
except co.CoopError as e:
    check("no hub: ask for the long code", "long code" in str(e))
check("register with no hub is False", co.register_short(co.make_short(), long_code, token, fetch=down) is False)

# someone else cannot take over or drop the code
cid, box = co.seal_short(code, long_code)
check("other drop token refused", not book.put({"id": cid, "box": box, "drop": "b" * 32}, "198.51.100.1")["ok"])
co.drop_short(code, "wrong-token", fetch=fetch)
check("wrong token does not drop", co.resolve_short(code, fetch=fetch) == long_code)
co.drop_short(code, token, fetch=fetch)
try:
    co.resolve_short(code, fetch=fetch)
    check("dropped", False)
except co.CoopError:
    check("dropped code is gone", True)

# a tampered box does not open
code2 = co.make_short()
cid2, box2 = co.seal_short(code2, long_code)
bad = box2[:-3] + ("A" if box2[-3] != "A" else "B") + box2[-2:]
try:
    co.open_short(code2, bad)
    check("tampered", False)
except co.CoopError:
    check("tampered box refused", True)

# lookups are limited per address
book2 = ws.CodeBook(tempfile.mkdtemp())
answers = [book2.get({"id": "0" * 32}, "192.0.2.9")["error"] for _ in range(ws.CODE_GETS + 2)]
check("lookups limited", answers[-1].startswith("Too many") and answers[0] == "unknown")

# expiry and the file
book3 = ws.CodeBook(tempfile.mkdtemp())
cid3, box3 = co.seal_short(code2, long_code)
book3.put({"id": cid3, "box": box3, "drop": "c" * 32}, "192.0.2.1", now=time.time() - 8 * 86400)
check("expired code gone", book3.get({"id": cid3}, "192.0.2.1")["error"] == "unknown")
again = ws.CodeBook(book.path.rsplit(os.sep, 1)[0])
check("code book reloads from its file", isinstance(again.codes, dict))
check("settings keep short fields", all(k in co.load_settings(tempfile.mkdtemp()) for k in ("short", "short_for", "short_drop", "short_at")))
print("PASS", passed)
