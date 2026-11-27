"""Character pages on xiforever.com and the phone app (2026-11-24). No GUI here, so it can be tested on its own.

SYNC sends a *card* for each of this world's own characters to the armory on the hub (dev/armory/armory_service.py):
looks, jobs and levels, gear, crafts and fishing, quests, titles, key items, playtime, hardcore mode and the squad.
The site shows it as a 2004-style character page (xiforever.com/c/<Name>), in the Armory list and the Hall of Fame.
Each character can be public (default), link-only or hidden.

The phone app pairs with this launcher (PAIR PHONE gives a 6-character code for 10 minutes) and then sees these
characters (gil and fishing tackle too) on its ME and FISH tabs. Portable fishing on the phone sends back what was
caught; at the next PLAY, before the servers start, `fish` takes it in: fishing skill (up to the guild rank's cap),
the catches in the delivery box (sender "Phone Fishing"), gil spent on bait taken off, gil fished up added, and the
character's own bait used on the phone taken out of the bag.

Command line (the launcher runs these):
  python launcher_armory.py sync        cards of every character up to the armory (only when "sync" is on, or --now)
  python launcher_armory.py fish        take in the phone's catches (only when paired; before the servers start)
  python launcher_armory.py pair        a pairing code for the phone app
  python launcher_armory.py unpair      forget every phone paired with this launcher
  python launcher_armory.py status      what is set

armory.json (in the kit, never shared): {"key", "sync", "visibility": {name: public|link|hidden}, "url", "links",
"applied", "paired"}.
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_URL = "https://xiforever.com"
JOBS = ["war", "mnk", "whm", "blm", "rdm", "thf", "pld", "drk", "bst", "brd", "rng", "sam", "nin", "drg", "smn", "blu",
        "cor", "pup", "dnc", "sch", "geo", "run"]
CRAFTS = {48: "Fishing", 49: "Woodworking", 50: "Smithing", 51: "Goldsmithing", 52: "Clothcraft", 53: "Leathercraft",
          54: "Bonecraft", 55: "Alchemy", 56: "Cooking"}
FISHING = 48
GIL = 65535
BOT_ACCOUNT_BASE = 21000000
SENDER = "Phone Fishing"
FAME_LEVELS = (0, 50, 125, 225, 325, 425, 488, 550, 613)       # fame points at which fame level 1..9 starts
QUEST_AREAS = 11


# ----------------------------------------------------------------------------------------------- settings
def settings_path(kit=HERE):
    return os.path.join(kit, "armory.json")


def load(kit=HERE):
    try:
        with open(settings_path(kit), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        data = {}
    if not isinstance(data.get("key"), str) or len(data["key"]) != 48:
        data["key"] = secrets.token_hex(24)
        save(data, kit)
    data.setdefault("sync", False)
    data.setdefault("visibility", {})
    data.setdefault("links", {})
    data.setdefault("applied", [])
    return data


def save(data, kit=HERE):
    path = settings_path(kit)
    with open(path + ".part", "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    os.replace(path + ".part", path)


def base_url(data):
    return (data.get("url") or DEFAULT_URL).rstrip("/")


# ---- HTTPS that works on every Windows PC --------------------------------------------------------------------------
# xiforever.com's certificate comes from Let's Encrypt. Python checks it with the PC's own certificate store, and on
# some Windows PCs that store still has the old, expired Let's Encrypt cross-certificate and not the current root (a
# browser fetches the root on demand; Python can't), so the check fails with "certificate has expired". Adding the
# current public roots of Let's Encrypt (ISRG Root X1/X2) and ZeroSSL (USERTrust) to the PC's own list fixes it.
_PUBLIC_ROOTS = """-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw
CQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg
R3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00
MDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT
ZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw
EAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW
+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9
ItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T
AQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI
zj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW
tL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1
/q4AaOeMSQ+2b1tbFfLn
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIF3jCCA8agAwIBAgIQAf1tMPyjylGoG7xkDjUDLTANBgkqhkiG9w0BAQwFADCB
iDELMAkGA1UEBhMCVVMxEzARBgNVBAgTCk5ldyBKZXJzZXkxFDASBgNVBAcTC0pl
cnNleSBDaXR5MR4wHAYDVQQKExVUaGUgVVNFUlRSVVNUIE5ldHdvcmsxLjAsBgNV
BAMTJVVTRVJUcnVzdCBSU0EgQ2VydGlmaWNhdGlvbiBBdXRob3JpdHkwHhcNMTAw
MjAxMDAwMDAwWhcNMzgwMTE4MjM1OTU5WjCBiDELMAkGA1UEBhMCVVMxEzARBgNV
BAgTCk5ldyBKZXJzZXkxFDASBgNVBAcTC0plcnNleSBDaXR5MR4wHAYDVQQKExVU
aGUgVVNFUlRSVVNUIE5ldHdvcmsxLjAsBgNVBAMTJVVTRVJUcnVzdCBSU0EgQ2Vy
dGlmaWNhdGlvbiBBdXRob3JpdHkwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIK
AoICAQCAEmUXNg7D2wiz0KxXDXbtzSfTTK1Qg2HiqiBNCS1kCdzOiZ/MPans9s/B
3PHTsdZ7NygRK0faOca8Ohm0X6a9fZ2jY0K2dvKpOyuR+OJv0OwWIJAJPuLodMkY
tJHUYmTbf6MG8YgYapAiPLz+E/CHFHv25B+O1ORRxhFnRghRy4YUVD+8M/5+bJz/
Fp0YvVGONaanZshyZ9shZrHUm3gDwFA66Mzw3LyeTP6vBZY1H1dat//O+T23LLb2
VN3I5xI6Ta5MirdcmrS3ID3KfyI0rn47aGYBROcBTkZTmzNg95S+UzeQc0PzMsNT
79uq/nROacdrjGCT3sTHDN/hMq7MkztReJVni+49Vv4M0GkPGw/zJSZrM233bkf6
c0Plfg6lZrEpfDKEY1WJxA3Bk1QwGROs0303p+tdOmw1XNtB1xLaqUkL39iAigmT
Yo61Zs8liM2EuLE/pDkP2QKe6xJMlXzzawWpXhaDzLhn4ugTncxbgtNMs+1b/97l
c6wjOy0AvzVVdAlJ2ElYGn+SNuZRkg7zJn0cTRe8yexDJtC/QV9AqURE9JnnV4ee
UB9XVKg+/XRjL7FQZQnmWEIuQxpMtPAlR1n6BB6T1CZGSlCBst6+eLf8ZxXhyVeE
Hg9j1uliutZfVS7qXMYoCAQlObgOK6nyTJccBz8NUvXt7y+CDwIDAQABo0IwQDAd
BgNVHQ4EFgQUU3m/WqorSs9UgOHYm8Cd8rIDZsswDgYDVR0PAQH/BAQDAgEGMA8G
A1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQEMBQADggIBAFzUfA3P9wF9QZllDHPF
Up/L+M+ZBn8b2kMVn54CVVeWFPFSPCeHlCjtHzoBN6J2/FNQwISbxmtOuowhT6KO
VWKR82kV2LyI48SqC/3vqOlLVSoGIG1VeCkZ7l8wXEskEVX/JJpuXior7gtNn3/3
ATiUFJVDBwn7YKnuHKsSjKCaXqeYalltiz8I+8jRRa8YFWSQEg9zKC7F4iRO/Fjs
8PRF/iKz6y+O0tlFYQXBl2+odnKPi4w2r78NBc5xjeambx9spnFixdjQg3IM8WcR
iQycE0xyNN+81XHfqnHd4blsjDwSXWXavVcStkNr/+XeTWYRUc+ZruwXtuhxkYze
Sf7dNXGiFSeUHM9h4ya7b6NnJSFd5t0dCy5oGzuCr+yDZ4XUmFF0sbmZgIn/f3gZ
XHlKYC6SQK5MNyosycdiyA5d9zZbyuAlJQG03RoHnHcAP9Dc1ew91Pq7P8yF1m9/
qS3fuQL39ZeatTXaw2ewh0qpKJ4jjv9cJ2vhsE/zB+4ALtRZh8tSQZXq9EfX7mRB
VXyNWQKV3WKdwrnuWih0hKWbt5DHDAff9Yk2dDLWKMGwsAvgnEzDHNb842m1R0aB
L6KCq9NjRHDEjf8tM7qtj3u1cIiuPhnPQCjY/MiQu12ZIvVS5ljFH4gxQ+6IHdfG
jjxDah2nGN59PRbxYvnKkKj9
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICjzCCAhWgAwIBAgIQXIuZxVqUxdJxVt7NiYDMJjAKBggqhkjOPQQDAzCBiDEL
MAkGA1UEBhMCVVMxEzARBgNVBAgTCk5ldyBKZXJzZXkxFDASBgNVBAcTC0plcnNl
eSBDaXR5MR4wHAYDVQQKExVUaGUgVVNFUlRSVVNUIE5ldHdvcmsxLjAsBgNVBAMT
JVVTRVJUcnVzdCBFQ0MgQ2VydGlmaWNhdGlvbiBBdXRob3JpdHkwHhcNMTAwMjAx
MDAwMDAwWhcNMzgwMTE4MjM1OTU5WjCBiDELMAkGA1UEBhMCVVMxEzARBgNVBAgT
Ck5ldyBKZXJzZXkxFDASBgNVBAcTC0plcnNleSBDaXR5MR4wHAYDVQQKExVUaGUg
VVNFUlRSVVNUIE5ldHdvcmsxLjAsBgNVBAMTJVVTRVJUcnVzdCBFQ0MgQ2VydGlm
aWNhdGlvbiBBdXRob3JpdHkwdjAQBgcqhkjOPQIBBgUrgQQAIgNiAAQarFRaqflo
I+d61SRvU8Za2EurxtW20eZzca7dnNYMYf3boIkDuAUU7FfO7l0/4iGzzvfUinng
o4N+LZfQYcTxmdwlkWOrfzCjtHDix6EznPO/LlxTsV+zfTJ/ijTjeXmjQjBAMB0G
A1UdDgQWBBQ64QmG1M8ZwpZ2dEl23OA1xmNjmjAOBgNVHQ8BAf8EBAMCAQYwDwYD
VR0TAQH/BAUwAwEB/zAKBggqhkjOPQQDAwNoADBlAjA2Z6EWCNzklwBBHU6+4WMB
zzuqQhFkoJ2UOQIReVx7Hfpkue4WQrO/isIJxOzksU0CMQDpKmFHjFJKS04YcPbW
RNZu9YO6bVi9JNlWSOrvxKJGgYhqOkbRqZtNyWHa0V1Xahg=
-----END CERTIFICATE-----
"""
_CTX = None


def _ssl_context():
    global _CTX
    if _CTX is None:
        import ssl
        ctx = ssl.create_default_context()
        try:
            ctx.load_verify_locations(cadata=_PUBLIC_ROOTS)
        except Exception:
            pass
        _CTX = ctx
    return _CTX


def call(data, path, body=None, timeout=25):
    req = urllib.request.Request(base_url(data) + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Armory-Key": data["key"],
                                          "User-Agent": "XI-Forever-Offline-launcher"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as res:
            return json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}") or {"error": f"the armory answered {e.code}"}
        except ValueError:
            return {"error": f"the armory answered {e.code}"}


# ----------------------------------------------------------------------------------------------- the database
def connect(cfg):
    import mariadb

    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)), user=cfg["db_user"],
                           password=cfg["db_pass"], database=cfg["db_name"], autocommit=False)


def _all(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def _one(cur, sql, params=()):
    rows = _all(cur, sql, params)
    return rows[0] if rows else None


def _columns(cur, table):
    try:
        return [r[0] for r in _all(cur, "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() "
                                        "AND table_name = ? ORDER BY ordinal_position", (table,))]
    except Exception:
        return []


def _has(cur, table):
    return bool(_columns(cur, table))


def pretty_item(name):
    """'terras_staff' -> "Terra's Staff" (item_basic keeps lower-case names with underscores)."""
    small = {"of", "the", "a", "an", "and", "in", "on", "to"}
    words = str(name or "").replace("_", " ").split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (i and w in small) else (w[:1].upper() + w[1:]))
    text = " ".join(out)
    for a, b in (("Terras ", "Terra's "), (" +1", " +1")):
        text = text.replace(a, b)
    return text


def popcount(blob, start=0, length=None, stride=None, part=None):
    """Bits set in a blob; with stride/part only the first `part` bytes of every `stride`-byte record count."""
    if not blob:
        return 0
    data = bytes(blob)
    if stride and part:
        return sum(bin(b).count("1") for i in range(0, len(data), stride) for b in data[i:i + part])
    end = len(data) if length is None else start + length
    return sum(bin(b).count("1") for b in data[start:end])


def fame_level(points):
    points = int(points or 0)
    return max(i + 1 for i, t in enumerate(FAME_LEVELS) if points >= t)


def home_characters(conn):
    """[(charid, name)] of this world's own players (no bots, no visitors, none that are away visiting)."""
    cur = conn.cursor()
    try:
        sql = ("SELECT c.charid, c.charname FROM chars c JOIN accounts a ON a.id = c.accid "
               "WHERE c.accid > 0 AND c.accid < ? AND a.login <> 'coopaway'")
        if _has(cur, "coop_guest"):
            sql += " AND c.charid NOT IN (SELECT charid FROM coop_guest WHERE state <> 'gone')"
        return [(int(r[0]), str(r[1])) for r in _all(cur, sql + " ORDER BY c.charname", (BOT_ACCOUNT_BASE,))]
    finally:
        cur.close()
        conn.rollback()


def existing_names(conn):
    """The lower-case names of every player character this world still has: its own, those away visiting and visitors
    (a deleted character has account 0). Bots are left out. Used to take deleted characters off the armory."""
    cur = conn.cursor()
    try:
        return {str(r[0]).lower() for r in _all(cur, "SELECT charname FROM chars WHERE accid > 0 AND accid < ?", (BOT_ACCOUNT_BASE,))}
    finally:
        cur.close()
        conn.rollback()


def item_names(cur, ids):
    ids = sorted({int(i) for i in ids if i})
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    return {int(r[0]): pretty_item(r[1]) for r in _all(cur, f"SELECT itemid, name FROM item_basic WHERE itemid IN ({marks})", ids)}


def fishing_rates(kit=HERE, key="map.FISHING_SKILL_MULTIPLIER"):
    """{0: the world's rate, mode: a hardcore profile's} for one of the launcher's rates (by default the fishing skill-up
    rate, map.FISHING_SKILL_MULTIPLIER, which the phone uses too; main.TM_GIL_RATE for Tetra Master). Missing files: 1.0."""
    out = {0: 1.0}
    try:
        import launcher_core as core
        out[0] = float(core.load_rates(kit).get(key, 1.0))
    except Exception:
        pass
    try:
        import launcher_hardcore as hc
        for mode, rates in hc.profiles(kit).items():
            if key in rates:
                out[int(mode)] = float(rates[key])
    except Exception:
        pass
    return out


TM_TYPES = "PMXA"


def tetra_cards(cur, charid):
    """(2026-11-25) The character's Tetra Master cards, as the server keeps them (modules/custom/lua/tetramaster.lua):
    TM_STARTER = 1 once Luto Mewrilah gave the starter deck (that unlocks Tetra Master in the app); TM_N cards,
    TM_A<i> = id + 256 * arrows + 65536 * class, TM_B<i> = attack + 256 * physical + 65536 * magical defence;
    TM_D1..TM_D5 the deck (card numbers)."""
    v = {str(k): int(val or 0) for k, val in _all(cur, "SELECT varname, value FROM char_vars WHERE charid = ? AND varname LIKE ?",
                                                    (charid, "TM_%"))}
    cards = []
    for i in range(1, min(v.get("TM_N", 0), 200) + 1):
        a, b = v.get(f"TM_A{i}", 0), v.get(f"TM_B{i}", 0)
        cid = a % 256
        if a <= 0 or not 1 <= cid <= 250:
            continue
        cards.append({"uid": i, "id": cid, "arrows": (a // 256) % 256, "type": TM_TYPES[(a // 65536) % 4],
                      "atk": b % 256, "pdef": (b // 256) % 256, "mdef": (b // 65536) % 256})
    deck = [v.get(f"TM_D{k}", 0) for k in range(1, 6) if v.get(f"TM_D{k}", 0)]
    return {"unlocked": v.get("TM_STARTER", 0) == 1, "cards": cards, "deck": deck}


def build_card(conn, charid, world="", rates=None, tm_rates=None):
    """The card of one character, as the armory takes it (see armory_service.clean_card)."""
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT charname, nation, playtime, quests, keyitems, titles, UNIX_TIMESTAMP(timecreated) FROM chars WHERE charid = ?", (charid,))
        if not row:
            raise ValueError(f"no character {charid}")
        name, nation, playtime, quests, keyitems, titles, created = row
        look = _one(cur, "SELECT race, face, size FROM char_look WHERE charid = ?", (charid,)) or (1, 0, 0)
        stats = _one(cur, "SELECT mjob, sjob, mlvl, slvl, hp, mp FROM char_stats WHERE charid = ?", (charid,)) or (1, 0, 1, 0, 0, 0)
        job_cols = [c for c in JOBS if c in _columns(cur, "char_jobs")]
        jrow = _one(cur, f"SELECT {', '.join(job_cols)} FROM char_jobs WHERE charid = ?", (charid,)) if job_cols else None
        jobs = {c.upper(): int(v) for c, v in zip(job_cols, jrow or []) if v}
        equip_rows = _all(cur, "SELECT e.equipslotid, i.itemId FROM char_equip e JOIN char_inventory i ON i.charid = e.charid "
                               "AND i.location = e.containerid AND i.slot = e.slotid WHERE e.charid = ?", (charid,))
        skills = _all(cur, "SELECT skillid, value, `rank` FROM char_skills WHERE charid = ? AND skillid BETWEEN 48 AND 56", (charid,))
        prof = None
        if _has(cur, "char_profile"):
            prof = _one(cur, "SELECT rank_sandoria, rank_bastok, rank_windurst, fame_sandoria, fame_bastok, fame_windurst, fame_norg "
                             "FROM char_profile WHERE charid = ?", (charid,))
        gil = _one(cur, "SELECT quantity FROM char_inventory WHERE charid = ? AND location = 0 AND slot = 0 AND itemId = ?", (charid, GIL))
        hcv = dict(_all(cur, "SELECT varname, value FROM char_vars WHERE charid = ? AND varname LIKE ?", (charid, "[HC]%")))
        inv = _all(cur, "SELECT itemId, SUM(quantity) FROM char_inventory WHERE charid = ? GROUP BY itemId", (charid,))
        rods = {int(r[0]) for r in _all(cur, "SELECT rodid FROM fishing_rod")} if _has(cur, "fishing_rod") else set()
        baits = {int(r[0]) for r in _all(cur, "SELECT baitid FROM fishing_bait")} if _has(cur, "fishing_bait") else set()
        mates = []
        if _has(cur, "squad_mate"):
            for mid, mname, mrace, mface, mjob, msjob in _all(cur, "SELECT id, name, race, face, mjob, sjob FROM squad_mate WHERE charid = ? "
                                                                   "ORDER BY slot", (charid,)):
                lvl = _one(cur, "SELECT level FROM squad_job WHERE squad_id = ? AND job = ?", (mid, mjob))
                gear = _all(cur, "SELECT slot, itemid FROM squad_equip WHERE squad_id = ? AND job = ?", (mid, mjob)) \
                    if _has(cur, "squad_equip") else []
                mates.append({"name": str(mname), "race": int(mrace or 1), "face": int(mface or 0), "mjob": int(mjob or 1),
                              "sjob": int(msjob or 0), "level": int((lvl or [1])[0] or 1), "gear": [(int(s), int(i)) for s, i in gear if i]})
        tetra = tetra_cards(cur, charid)
        names = item_names(cur, [i for _, i in equip_rows] + [i for m in mates for _, i in m["gear"]]
                           + [i for i, _ in inv if int(i) in rods or int(i) in baits])
    finally:
        cur.close()
        conn.rollback()

    crafts = {CRAFTS[int(s)]: {"skill": round(int(v) / 10, 1), "rank": int(r)} for s, v, r in skills if int(s) in CRAFTS}
    fish_skill = crafts.get("Fishing", {"skill": 0.0, "rank": 0})
    card = {
        "name": name, "race": int(look[0] or 1), "face": int(look[1] or 0), "size": int(look[2] or 0),
        "nation": int(nation or 0), "mjob": int(stats[0] or 1), "sjob": int(stats[1] or 0), "mlvl": int(stats[2] or 1),
        "slvl": int(stats[3] or 0), "hp": int(stats[4] or 0), "mp": int(stats[5] or 0), "jobs": jobs,
        "equip": [{"slot": int(s), "id": int(i), "name": names.get(int(i), f"Item {i}")} for s, i in equip_rows],
        "crafts": {k: v for k, v in crafts.items() if k != "Fishing"},
        "quests": _quests_done(quests),
        "titles": popcount(titles), "keyitems": popcount(keyitems, stride=128, part=64),
        "playtime": int(playtime or 0), "created": int(created or 0), "gil": int((gil or [0])[0] or 0), "world": world,
        "fishing": {"skill": fish_skill["skill"], "rank": fish_skill["rank"], "cap": (fish_skill["rank"] + 1) * 10,
                    "rods": [{"id": int(i), "name": names.get(int(i), f"Item {i}")} for i, q in inv if int(i) in rods],
                    "bait": [{"id": int(i), "name": names.get(int(i), f"Item {i}"), "qty": int(q)} for i, q in inv if int(i) in baits]},
        "squad": [{"name": m["name"], "race": m["race"], "face": m["face"], "mjob": m["mjob"], "sjob": m["sjob"], "level": m["level"],
                   "equip": [{"slot": s, "id": i, "name": names.get(i, f"Item {i}")} for s, i in m["gear"]]} for m in mates],
    }
    if prof:
        card["rank"] = int(prof[int(nation or 0)] or 0)
        card["fame"] = {"sandoria": fame_level(prof[3]), "bastok": fame_level(prof[4]), "windurst": fame_level(prof[5]),
                        "jeuno": fame_level((int(prof[3] or 0) + int(prof[4] or 0) + int(prof[5] or 0)) // 3),
                        "norg": fame_level(prof[6])}
    mode = int(hcv.get("[HC]Mode", 0) or 0)
    rates = rates or {0: 1.0}
    card["fishing"]["rate"] = round(max(0.0, min(20.0, float(rates.get(mode, rates.get(0, 1.0))))), 2)
    tm_rates = tm_rates or {0: 1.0}
    tetra["gilRate"] = round(max(0.0, min(10.0, float(tm_rates.get(mode, tm_rates.get(0, 1.0))))), 2)
    card["tetra"] = tetra
    if mode:
        card["hardcore"] = {"mode": int(hcv["[HC]Mode"]), "dead": bool(int(hcv.get("[HC]Dead", 0) or 0)),
                            "deaths": int(hcv.get("[HC]Deaths", 0) or 0), "resets": int(hcv.get("[HC]Resets", 0) or 0),
                            "start": int(hcv.get("[HC]Start", 0) or 0)}
    return card


def _quests_done(blob):
    """Completed quests: the server keeps 11 quest logs of 64 bytes (32 bytes "current", then 32 bytes "complete")."""
    if not blob:
        return 0
    data = bytes(blob)
    return sum(bin(b).count("1") for area in range(QUEST_AREAS) for b in data[area * 64 + 32: area * 64 + 64])


# ----------------------------------------------------------------------------------------------- sync / pair
def sync(cfg, kit=HERE, log=print, names=None):
    """Send the cards. Returns {name: result}."""
    data = load(kit)
    conn = connect(cfg)
    try:
        chars = [c for c in home_characters(conn) if names is None or c[1] in names]
        still_here = existing_names(conn) if names is None else None
        world = cfg.get("world_name") or ""
        rates = fishing_rates(kit)
        tm_rates = fishing_rates(kit, "main.TM_GIL_RATE")
        cards = []
        for charid, name in chars:
            try:
                cards.append(build_card(conn, charid, world, rates, tm_rates))
            except Exception as e:                    # one odd character never stops the others
                log(f"{name}: not synced ({e})")
    finally:
        conn.close()
    if not cards:
        log("No characters to sync.")
        return {}
    vis = {c["name"]: data["visibility"].get(c["name"], "public") for c in cards}
    out = call(data, "/armory/api/sync", {"cards": cards, "visibility": vis})
    if out.get("error"):
        raise RuntimeError(out["error"])
    data = load(kit)
    data["links"].update({k: base_url(data) + v for k, v in (out.get("links") or {}).items()})
    data["synced"] = int(time.time())
    save(data, kit)
    results = out.get("results") or {}
    for name, res in results.items():
        log(f"{name}: " + ("on your character page" if res == "ok" else res))
    # (2026-11-25, the user: deleted characters stayed on the armory) a full sync takes down the cards of characters
    # that are gone from this world; an older armory server sends no "yours" and nothing happens
    gone = [n for n in (out.get("yours") or []) if still_here is not None and str(n).lower() not in still_here]
    if gone:
        try:
            removed = call(data, "/armory/api/sync", {"cards": [], "remove": gone[:40]})
            for name, res in (removed.get("results") or {}).items():
                log(f"{name}: taken off the armory (the character was deleted)")
                results[name] = res
                data["links"].pop(name, None)
                data["visibility"].pop(name, None)
            save(data, kit)
        except Exception as e:
            log(f"Deleted characters could not be taken off the armory ({e}).")
    return results


def pair(kit=HERE):
    data = load(kit)
    out = call(data, "/armory/api/pair", {})
    if out.get("error") or not out.get("code"):
        raise RuntimeError(out.get("error") or "no code")
    data["paired"] = True
    save(data, kit)
    return out["code"]


def unpair(kit=HERE):
    data = load(kit)
    call(data, "/armory/api/unpair", {})
    data["paired"] = False
    save(data, kit)


# ----------------------------------------------------------------------------------------------- the phone's catches
def apply_reports(conn, reports, log=print):
    """Take the phone's fishing reports into the database (the characters must be logged out). Returns the ids done."""
    done = []
    cur = conn.cursor()
    try:
        home = {name.lower(): charid for charid, name in home_characters(conn)}
        for rep in reports:
            charid = home.get(str(rep.get("char", "")).lower())
            if not charid:
                log(f"{rep.get('char')}: not here (or away visiting) - the phone's catches wait for the next PLAY.")
                continue
            name = str(rep["char"])
            # fishing skill, up to the cap of the character's guild rank (the server's own rule)
            gained = max(0, int(rep.get("skill", 0) or 0))
            if gained:
                row = _one(cur, "SELECT value, `rank` FROM char_skills WHERE charid = ? AND skillid = ?", (charid, FISHING))
                value, rank = (int(row[0]), int(row[1])) if row else (0, 0)
                new = min(value + gained, (rank + 1) * 100)
                if row:
                    cur.execute("UPDATE char_skills SET value = ? WHERE charid = ? AND skillid = ?", (new, charid, FISHING))
                else:
                    cur.execute("INSERT INTO char_skills (charid, skillid, value, `rank`) VALUES (?, ?, ?, 0)", (charid, FISHING, new))
            # gil: bait bought on the phone, gil fished up
            delta = int(rep.get("gilFound", 0) or 0) - int(rep.get("gil", 0) or 0)
            if delta:
                g = _one(cur, "SELECT quantity FROM char_inventory WHERE charid = ? AND location = 0 AND slot = 0 AND itemId = ?", (charid, GIL))
                if g is not None:
                    cur.execute("UPDATE char_inventory SET quantity = ? WHERE charid = ? AND location = 0 AND slot = 0 AND itemId = ?",
                                (max(0, int(g[0]) + delta), charid, GIL))
            # the character's own bait used on the phone
            for b in rep.get("bait") or []:
                left = int(b.get("count", 0) or 0)
                for loc, slot, qty in _all(cur, "SELECT location, slot, quantity FROM char_inventory WHERE charid = ? AND itemId = ? "
                                                "ORDER BY location, slot", (charid, int(b["item"]))):
                    if left <= 0:
                        break
                    take = min(left, int(qty))
                    if take >= int(qty):
                        cur.execute("DELETE FROM char_inventory WHERE charid = ? AND location = ? AND slot = ?", (charid, loc, slot))
                    else:
                        cur.execute("UPDATE char_inventory SET quantity = quantity - ? WHERE charid = ? AND location = ? AND slot = ?",
                                    (take, charid, loc, slot))
                    left -= take
            # (2026-11-25) Tetra Master on the phone: gil won (above, in gilFound) and cards that went up a class
            tm = rep.get("tetra") or {}
            upgraded = 0
            for u in tm.get("upgrades") or []:
                uid, cid, kind = int(u.get("uid", 0) or 0), int(u.get("id", 0) or 0), str(u.get("type", ""))
                if kind not in ("X", "A") or not 1 <= uid <= 200:
                    continue
                row = _one(cur, "SELECT value FROM char_vars WHERE charid = ? AND varname = ?", (charid, f"TM_A{uid}"))
                if not row or int(row[0]) % 256 != cid:
                    continue                          # that card was sold or changed in the game since
                a = int(row[0])
                old = TM_TYPES[(a // 65536) % 4]
                if TM_TYPES.index(kind) > TM_TYPES.index(old):
                    a = (a % 65536) + 65536 * TM_TYPES.index(kind)
                    cur.execute("UPDATE char_vars SET value = ? WHERE charid = ? AND varname = ?", (a, charid, f"TM_A{uid}"))
                    upgraded += 1
            # the catches, in stacks, into the delivery box
            stacks = {}
            for c in rep.get("catches") or []:
                item = int(c.get("item", 0) or 0)
                if item and item != GIL:
                    stacks[item] = stacks.get(item, 0) + int(c.get("count", 0) or 0)
            if stacks:
                marks = ",".join("?" * len(stacks))
                sizes = {int(r[0]): max(1, int(r[1])) for r in _all(cur, f"SELECT itemid, stackSize FROM item_basic WHERE itemid IN ({marks})",
                                                                     list(stacks))}
                # (the server's own trigger, delivery_box_insert, numbers incoming items from slot 8 up: they wait there
                # until the box has room, like mail from another player)
                slot = int((_one(cur, "SELECT IFNULL(MAX(slot) + 1, 8) FROM delivery_box WHERE charid = ? AND box = 1", (charid,)) or [8])[0])
                for item, count in stacks.items():
                    if item not in sizes:
                        continue                          # not an item of this server
                    # (2026-11-26, Frost: 200 catches came as 200 deliveries) the phone reports a few catches at a time,
                    # and each report used to start its own stacks. The stacks of this item that still wait in the box
                    # are filled up first; only what is left over starts a new one.
                    if sizes[item] > 1:
                        for waiting, held in _all(cur, "SELECT slot, quantity FROM delivery_box WHERE charid = ? AND box = 1 AND itemid = ? "
                                                       "AND itemsubid = 0 AND sender = ? AND quantity < ? ORDER BY slot",
                                                  (charid, item, SENDER, sizes[item])):
                            if count <= 0:
                                break
                            add = min(count, sizes[item] - int(held))
                            cur.execute("UPDATE delivery_box SET quantity = quantity + ? WHERE charid = ? AND box = 1 AND slot = ?",
                                        (add, charid, int(waiting)))
                            count -= add
                    while count > 0:
                        q = min(count, sizes[item])
                        cur.execute("INSERT INTO delivery_box (charid, charname, box, slot, itemid, itemsubid, quantity, senderid, sender) "
                                    "VALUES (?, ?, 1, ?, ?, 0, ?, 0, ?)", (charid, name[:15], slot, item, q, SENDER))
                        slot += 1
                        count -= q
            fish = sum(int(c.get("count", 0) or 0) for c in rep.get("catches") or [] if int(c.get("item", 0) or 0) != GIL)
            if tm and not fish and not gained:
                wins = int(tm.get("wins", 0) or 0)
                log(f"{name}: Tetra Master on your phone, {wins} win{'s' if wins != 1 else ''}"
                    + (f", gil +{delta}" if delta > 0 else "")
                    + (f", {upgraded} card{'s' if upgraded != 1 else ''} up a class" if upgraded else "") + ".")
            else:
                log(f"{name}: {fish} catch{'es' if fish != 1 else ''} from your phone in the delivery box"
                    + (f", fishing +{gained / 10:.1f}" if gained else "")
                    + (f", gil {'+' if delta > 0 else ''}{delta}" if delta else "") + ".")
            done.append(str(rep["id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return done


def fish(cfg, kit=HERE, log=print):
    """Fetch the phone's reports, take them in, tell the armory. A report is never taken in twice."""
    data = load(kit)
    out = call(data, "/armory/api/fish")
    if out.get("error"):
        raise RuntimeError(out["error"])
    reports = [r for r in out.get("reports") or [] if str(r.get("id")) not in set(data.get("applied", []))]
    already = [str(r.get("id")) for r in out.get("reports") or [] if str(r.get("id")) in set(data.get("applied", []))]
    done = []
    if reports:
        conn = connect(cfg)
        try:
            done = apply_reports(conn, reports, log)
        finally:
            conn.close()
        data = load(kit)
        data["applied"] = (data.get("applied", []) + done)[-500:]          # kept first: a lost answer can't apply it twice
        save(data, kit)
    if done or already:
        call(data, "/armory/api/fish/done", {"ids": done + already})
    return len(done)


# ----------------------------------------------------------------------------------------------- command line
def _main(argv):
    with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as handle:
        cfg = json.load(handle)
    what = argv[1] if len(argv) > 1 else "status"
    data = load()
    try:
        if what == "sync":
            if not data.get("sync") and "--now" not in argv:
                return 0
            results = sync(cfg)
            ok = sum(1 for r in results.values() if r == "ok")
            print(f"character pages: {ok} character(s) synced to xiforever.com" if ok else "character pages: nothing synced")
        elif what == "fish":
            if not data.get("paired"):
                return 0
            n = fish(cfg)
            if n:
                print(f"phone fishing: {n} trip(s) taken in")
        elif what == "pair":
            print(pair())
        elif what == "unpair":
            unpair()
            print("Every phone paired with this launcher was forgotten.")
        else:
            print(json.dumps({k: v for k, v in data.items() if k != "key"}, indent=1))
    except (OSError, RuntimeError, urllib.error.URLError) as e:
        print(f"{what}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
