"""The XI: Forever Offline armory (2026-11-24): character pages on xiforever.com, the phone app's ME and FISH tabs.

A launcher sends its characters' cards (SYNC): looks, jobs, gear, skills, squad. The site shows them as 2004-style pages:
  /c/<Name>              one character (public, or link-only with ?k=<token>; hidden ones are not shown at all)
  /armory                browse and search the public characters
  /armory/fame           the Hall of Fame (top levels, jobs at 75, fishing, hardcore, playtime)
The phone app pairs with a launcher (a 6-character code that lasts 10 minutes), reads its own characters (hidden ones
too) and sends back what it caught with portable fishing; the launcher takes that in at the next PLAY.

  POST /armory/api/sync        (launcher key)  {"cards": [card...], "remove": [name...]} -> {"results": {name: "ok"|error},
                                                "links": {...}, "yours": [every name this launcher has on the armory]}
  POST /armory/api/pair        (launcher key)  -> {"code", "expires"}
  POST /armory/api/unpair      (launcher key)  forgets every phone paired with this launcher
  POST /armory/api/claim       (phone key)     {"code"} -> {"ok", "names"}
  GET  /armory/api/me          (phone key)     -> {"cards": [...full cards...], "pending": [...]}
  POST /armory/api/fish        (phone key)     {"id", "char", "catches": [{"item","count"}], "skill", "gil", "bait"} -> {"ok"}
  GET  /armory/api/fish        (launcher key)  -> {"reports": [...]}     the launcher applies them, then:
  POST /armory/api/fish/done   (launcher key)  {"ids": [...]}
  GET  /armory/api/list?q=&page=               public characters (summary)
  GET  /armory/api/c/<Name>?k=                 one public / link-only card (no gil, no bait, no owner data)
  GET  /armory/health

Keys: X-Armory-Key (a launcher's own random key, kept in its armory.json) and X-Armory-Phone (a phone's random key).
Only hashes are stored. The first launcher to sync a name keeps it. Everything is plain files under --data.
Python 3 standard library only.

Run: python3 armory_service.py [--port 54302] [--data /var/lib/xifo-armory] [--static DIR]
"""
import argparse
import hashlib
import html
import json
import urllib.request
import math
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

try:                                        # (2026-11-25) Ventures: squad mates sent off to level from the app
    import ventures_hub
except Exception as _e:                     # (the rest of the armory keeps working without it)
    ventures_hub = None
    print("ventures off:", _e, flush=True)
try:                                        # (2026-11-25) Tetra Master PvP in the app
    import tetra_hub
except Exception as _e:
    tetra_hub = None
    print("tetra master pvp off:", _e, flush=True)

NAME_RE = re.compile(r"^[A-Za-z]{3,15}$")
KEY_RE = re.compile(r"^[0-9a-f]{32,64}$")
MAX_BODY = 512 * 1024
MAX_CARD = 96 * 1024
PAIR_SECONDS = 600
PAIR_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_REPORTS = 200            # waiting fishing reports per launcher
MAX_CATCH = 300              # catches in one report
PAGE = 40
JOBS = ["WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN", "BLU",
        "COR", "PUP", "DNC", "SCH", "GEO", "RUN"]
ERA_JOBS = JOBS[:18]
RACES = {1: ("Hume", "Male"), 2: ("Hume", "Female"), 3: ("Elvaan", "Male"), 4: ("Elvaan", "Female"),
         5: ("Tarutaru", "Male"), 6: ("Tarutaru", "Female"), 7: ("Mithra", "Female"), 8: ("Galka", "Male")}
FACE_FILES = {1: "Hm", 2: "Hf", 3: "Em", 4: "Ef", 5: "Tm", 6: "Tf", 7: "M", 8: "G"}
NATIONS = {0: "San d'Oria", 1: "Bastok", 2: "Windurst"}
MODES = {1: "Iron", 2: "Steel", 3: "Silver", 4: "Randomized"}
MODE_ICONS = {1: "hc_iron.png", 2: "hc_steel.png", 3: "hc_silver.png", 4: "hc_random.png"}
SLOTS = ["Main", "Sub", "Range", "Ammo", "Head", "Neck", "Ear", "Ear", "Body", "Hands", "Ring", "Ring", "Back", "Waist",
         "Legs", "Feet"]
CRAFTS = ["Fishing", "Woodworking", "Smithing", "Goldsmithing", "Clothcraft", "Leathercraft", "Bonecraft", "Alchemy",
          "Cooking"]
VIS = ("public", "link", "hidden")
DEFAULT_BIO = "Adventurer of Vana'diel"


def h(text):
    return hashlib.sha256(("xifo-armory|" + str(text)).encode()).hexdigest()[:32]


def esc(value):
    return html.escape(str(value), quote=True)


def clean_text(value, limit=60):
    text = "".join(ch for ch in str(value) if ch.isprintable())
    return re.sub(r"\s+", " ", text).strip()[:limit]


def num(value, lo=0, hi=10 ** 9, default=0):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def fmt_time(seconds):
    seconds = int(seconds or 0)
    d, rest = divmod(seconds, 86400)
    hrs = rest // 3600
    return f"{d}d {hrs}h" if d else f"{hrs}h {rest % 3600 // 60}m"


def ago(t):
    if not t:
        return "never"
    s = max(0, int(time.time() - t))
    if s < 90:
        return "just now"
    if s < 5400:
        return f"{s // 60} minutes ago"
    if s < 129600:
        return f"{s // 3600} hours ago"
    return f"{s // 86400} days ago"


# ---------------------------------------------------------------------------------------------------- the card
def clean_card(raw):
    """A card exactly as stored: only known fields, every value checked and clipped. Raises ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("not a card")
    name = str(raw.get("name", ""))
    if not NAME_RE.match(name):
        raise ValueError("bad name")
    card = {
        "v": 1,
        "name": name,
        "race": num(raw.get("race"), 1, 8, 1),
        "face": num(raw.get("face"), 0, 15),
        "size": num(raw.get("size"), 0, 2),
        "nation": num(raw.get("nation"), 0, 2),
        "mjob": num(raw.get("mjob"), 1, 22, 1),
        "sjob": num(raw.get("sjob"), 0, 22),
        "mlvl": num(raw.get("mlvl"), 1, 99, 1),
        "slvl": num(raw.get("slvl"), 0, 99),
        "hp": num(raw.get("hp"), 0, 99999),
        "mp": num(raw.get("mp"), 0, 99999),
        "jobs": {j: num((raw.get("jobs") or {}).get(j), 0, 99) for j in JOBS if num((raw.get("jobs") or {}).get(j), 0, 99)},
        "equip": [],
        "crafts": {},
        "rank": num(raw.get("rank"), 0, 10),
        "fame": {k: num(v, 0, 9) for k, v in (raw.get("fame") or {}).items() if k in ("sandoria", "bastok", "windurst", "jeuno", "norg")},
        "quests": num(raw.get("quests"), 0, 5000),
        "titles": num(raw.get("titles"), 0, 5000),
        "keyitems": num(raw.get("keyitems"), 0, 5000),
        "playtime": num(raw.get("playtime"), 0, 10 ** 9),
        "created": num(raw.get("created"), 0, 4 * 10 ** 9),
        "gil": num(raw.get("gil"), 0, 10 ** 10),
        "hardcore": None,
        "squad": [],
        "fishing": {},
        "world": clean_text(raw.get("world", ""), 40),
        "bio": clean_text(raw.get("bio", ""), 200),
    }
    for e in (raw.get("equip") or [])[:16]:
        if isinstance(e, dict):
            card["equip"].append({"slot": num(e.get("slot"), 0, 15), "id": num(e.get("id"), 0, 65535),
                                  "name": clean_text(e.get("name", ""), 40)})
    for k, v in (raw.get("crafts") or {}).items():
        if k in CRAFTS:
            card["crafts"][k] = {"skill": round(max(0.0, min(110.0, float(v.get("skill", 0) if isinstance(v, dict) else 0))), 1),
                                 "rank": num(v.get("rank") if isinstance(v, dict) else 0, 0, 10)}
    hc = raw.get("hardcore")
    if isinstance(hc, dict) and num(hc.get("mode"), 0, 4):
        card["hardcore"] = {"mode": num(hc.get("mode"), 1, 4), "dead": bool(hc.get("dead")),
                            "deaths": num(hc.get("deaths"), 0, 9999), "resets": num(hc.get("resets"), 0, 9999),
                            "start": num(hc.get("start"), 0, 4 * 10 ** 9)}
    for m in (raw.get("squad") or [])[:12]:
        if not isinstance(m, dict):
            continue
        card["squad"].append({
            "name": clean_text(m.get("name", ""), 20), "race": num(m.get("race"), 1, 8, 1), "face": num(m.get("face"), 0, 15),
            "mjob": num(m.get("mjob"), 1, 22, 1), "sjob": num(m.get("sjob"), 0, 22), "level": num(m.get("level"), 1, 99, 1),
            "role": clean_text(m.get("role", ""), 20),
            "equip": [{"slot": num(e.get("slot"), 0, 15), "id": num(e.get("id"), 0, 65535), "name": clean_text(e.get("name", ""), 40)}
                      for e in (m.get("equip") or [])[:16] if isinstance(e, dict)],
        })
    f = raw.get("fishing") or {}
    if isinstance(f, dict):
        card["fishing"] = {
            "skill": round(max(0.0, min(110.0, float(f.get("skill", 0) or 0))), 1),
            "rank": num(f.get("rank"), 0, 10),
            "cap": num(f.get("cap"), 0, 110, 10),
            "rods": [{"id": num(r.get("id"), 0, 65535), "name": clean_text(r.get("name", ""), 40)}
                     for r in (f.get("rods") or [])[:40] if isinstance(r, dict)],
            "bait": [{"id": num(b.get("id"), 0, 65535), "name": clean_text(b.get("name", ""), 40), "qty": num(b.get("qty"), 0, 99999)}
                     for b in (f.get("bait") or [])[:60] if isinstance(b, dict)],
            "catches": num(f.get("catches"), 0, 10 ** 7),
            "rate": round(max(0.0, min(20.0, float(f.get("rate", 1.0) or 0))), 2),
        }
    # (2026-11-25) Tetra Master: unlocked at Luto Mewrilah (TM_STARTER), the collection with its hidden numbers, the deck
    tm = raw.get("tetra")
    if isinstance(tm, dict):
        cards = []
        for c in (tm.get("cards") or [])[:200]:
            if isinstance(c, dict) and num(c.get("id"), 1, 250) and c.get("type") in ("P", "M", "X", "A"):
                cards.append({"uid": num(c.get("uid"), 1, 10 ** 6, 1), "id": num(c.get("id"), 1, 250, 1), "type": c["type"],
                              "arrows": num(c.get("arrows"), 0, 255), "atk": num(c.get("atk"), 0, 255),
                              "pdef": num(c.get("pdef"), 0, 255), "mdef": num(c.get("mdef"), 0, 255)})
        card["tetra"] = {"unlocked": bool(tm.get("unlocked")), "cards": cards,
                         "deck": [num(u, 1, 10 ** 6, 1) for u in (tm.get("deck") or [])[:5]],
                         "gilRate": round(max(0.0, min(10.0, float(tm.get("gilRate", 1.0) or 0))), 2)}
    if len(json.dumps(card)) > MAX_CARD:
        raise ValueError("card too big")
    return card


def public_card(card):
    """What strangers may see: no gil, no bait or rods, nothing about the owner."""
    out = dict(card)
    out.pop("gil", None)
    f = dict(out.get("fishing") or {})
    f.pop("rods", None)
    f.pop("bait", None)
    out["fishing"] = f
    tm = out.get("tetra")
    if isinstance(tm, dict):                 # strangers see how many cards, not which (nor their hidden numbers)
        out["tetra"] = {"unlocked": bool(tm.get("unlocked")), "count": len(tm.get("cards") or [])}
    return out


# ---------------------------------------------------------------------------------------------------- storage
class Armory:
    def __init__(self, folder):
        self.folder = folder
        self.lock = threading.RLock()
        self.ventures = ventures_hub.Ventures(folder, self.lock) if ventures_hub else None
        self.tetra = None
        os.makedirs(os.path.join(folder, "cards"), exist_ok=True)
        self.state = {"names": {}, "phones": {}, "pairs": {}, "queue": {}, "done": {}}
        path = os.path.join(folder, "state.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                self.state.update(json.load(handle))
        self.cards = {}
        for fn in os.listdir(os.path.join(folder, "cards")):
            if fn.endswith(".json"):
                try:
                    with open(os.path.join(folder, "cards", fn), encoding="utf-8") as handle:
                        rec = json.load(handle)
                    self.cards[rec["card"]["name"].lower()] = rec
                except (OSError, ValueError, KeyError):
                    pass
        self.tetra = tetra_hub.Tetra(folder, self) if tetra_hub else None

    def _write(self, path, data):
        with open(path + ".part", "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        os.replace(path + ".part", path)

    # (2026-11-25, the user: gear slots show the item's picture, as the squad profile does) the same public 32x32 item
    # icons the launcher uses, fetched once per item and kept in <folder>/icons. Only items some card wears are fetched.
    ICON_URL = "https://static.ffxiah.com/images/icon/{}.png"

    def worn(self, item_id):
        with self.lock:
            for rec in self.cards.values():
                card = rec["card"]
                if any(e.get("id") == item_id for e in card.get("equip", [])):
                    return True
                if any(e.get("id") == item_id for m in card.get("squad", []) for e in m.get("equip", [])):
                    return True
        return False

    def icon(self, item_id):
        """The item's 32x32 PNG, or None."""
        folder = os.path.join(self.folder, "icons")
        path = os.path.join(folder, "%d.png" % item_id)
        if os.path.exists(path):
            with open(path, "rb") as handle:
                return handle.read()
        if not self.worn(item_id):
            return None
        try:
            req = urllib.request.Request(self.ICON_URL.format(item_id), headers={"User-Agent": "XIForeverOffline-Armory/1"})
            with urllib.request.urlopen(req, timeout=6) as res:
                data = res.read(64 * 1024 + 1)
        except Exception:
            return None
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 64 * 1024:
            return None
        os.makedirs(folder, exist_ok=True)
        with open(path + ".part", "wb") as handle:
            handle.write(data)
        os.replace(path + ".part", path)
        return data

    def save(self):
        self._write(os.path.join(self.folder, "state.json"), self.state)

    def save_card(self, rec):
        self._write(os.path.join(self.folder, "cards", rec["card"]["name"].lower() + ".json"), rec)

    def drop_card(self, name):
        self.cards.pop(name.lower(), None)
        try:
            os.remove(os.path.join(self.folder, "cards", name.lower() + ".json"))
        except OSError:
            pass

    # ------------------------------------------------------------ launcher side
    def sync(self, owner, body):
        results = {}
        cards = body.get("cards") if isinstance(body.get("cards"), list) else []
        vis = body.get("visibility") if isinstance(body.get("visibility"), dict) else {}
        with self.lock:
            for raw in cards[:40]:
                try:
                    card = clean_card(raw)
                except (ValueError, TypeError, AttributeError) as e:
                    results[str((raw or {}).get("name", "?"))[:20] if isinstance(raw, dict) else "?"] = f"not taken ({e})"
                    continue
                key = card["name"].lower()
                holder = self.state["names"].get(key)
                if holder and holder != owner:
                    results[card["name"]] = "taken: another player already shows a character with this name"
                    continue
                self.state["names"][key] = owner
                old = self.cards.get(key) or {}
                v = vis.get(card["name"], old.get("vis", "public"))
                rec = {"card": card, "owner": owner, "vis": v if v in VIS else "public",
                       "token": old.get("token") or secrets.token_urlsafe(9), "synced": int(time.time()),
                       "first": old.get("first") or int(time.time())}
                self.cards[key] = rec
                self.save_card(rec)
                results[card["name"]] = "ok"
            for name in (body.get("remove") or [])[:40]:
                key = str(name).lower()
                if self.state["names"].get(key) == owner:
                    self.state["names"].pop(key, None)
                    self.drop_card(key)
                    results[str(name)] = "removed"
            self.save()
        links = {}
        for name, res in results.items():
            rec = self.cards.get(name.lower())
            if res == "ok" and rec:
                links[name] = "/c/" + quote(rec["card"]["name"]) + ("?k=" + rec["token"] if rec["vis"] == "link" else "")
        # (2026-11-25, the user: the armory still showed deleted characters) every card this launcher owns, so it can
        # ask for the ones whose character is gone from its world to be taken down
        return {"results": results, "links": links, "yours": self.owner_names(owner)}

    def pair(self, owner):
        with self.lock:
            now = time.time()
            self.state["pairs"] = {c: p for c, p in self.state["pairs"].items() if p["exp"] > now}
            code = "".join(secrets.choice(PAIR_ALPHABET) for _ in range(6))
            self.state["pairs"][code] = {"owner": owner, "exp": now + PAIR_SECONDS}
            self.save()
            return {"code": code, "expires": int(now + PAIR_SECONDS)}

    def unpair(self, owner):
        with self.lock:
            self.state["phones"] = {p: o for p, o in self.state["phones"].items() if o.get("owner") != owner}
            self.save()
            return {"ok": True}

    def reports(self, owner):
        with self.lock:
            return {"reports": list(self.state["queue"].get(owner, []))}

    def reports_done(self, owner, ids):
        with self.lock:
            ids = {str(i) for i in (ids or [])[:MAX_REPORTS]}
            q = self.state["queue"].get(owner, [])
            self.state["queue"][owner] = [r for r in q if r["id"] not in ids]
            done = self.state["done"].setdefault(owner, [])
            done.extend(sorted(ids))
            self.state["done"][owner] = done[-500:]
            self.save()
            return {"ok": True}

    # ------------------------------------------------------------ phone side
    def claim(self, phone, code):
        with self.lock:
            code = str(code or "").strip().upper().replace("-", "").replace(" ", "")
            p = self.state["pairs"].get(code)
            if not p or p["exp"] < time.time():
                return {"error": "That code is wrong or too old. Make a new one in the launcher."}
            del self.state["pairs"][code]
            self.state["phones"][phone] = {"owner": p["owner"], "made": int(time.time())}
            self.save()
            return {"ok": True, "names": self.owner_names(p["owner"])}

    def owner_names(self, owner):
        return sorted(rec["card"]["name"] for rec in self.cards.values() if rec["owner"] == owner)

    def owner_of_phone(self, phone):
        return (self.state["phones"].get(phone) or {}).get("owner")

    def me(self, owner):
        with self.lock:
            cards = []
            for rec in sorted(self.cards.values(), key=lambda r: r["card"]["name"]):
                if rec["owner"] == owner:
                    c = dict(rec["card"])
                    c["_vis"], c["_synced"] = rec["vis"], rec["synced"]
                    c["_link"] = "/c/" + quote(c["name"]) + ("?k=" + rec["token"] if rec["vis"] == "link" else "")
                    cards.append(c)
            pending = [{"id": r["id"], "char": r["char"], "made": r["made"], "count": sum(c["count"] for c in r["catches"]),
                        "skill": r["skill"], "gil": r["gil"], "tetra": r.get("tetra")} for r in self.state["queue"].get(owner, [])]
            return {"cards": cards, "pending": pending}

    def fish(self, owner, body):
        with self.lock:
            rid = str(body.get("id", ""))[:40]
            if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", rid):
                return {"error": "bad report id"}
            q = self.state["queue"].setdefault(owner, [])
            if any(r["id"] == rid for r in q) or rid in self.state["done"].get(owner, []):
                return {"ok": True, "again": True}
            char = str(body.get("char", ""))
            rec = self.cards.get(char.lower())
            if not rec or rec["owner"] != owner:
                return {"error": "not one of your characters"}
            if len(q) >= MAX_REPORTS:
                return {"error": "Too many catches are waiting. Press PLAY in the launcher to take them in first."}
            catches = []
            for c in (body.get("catches") or [])[:MAX_CATCH]:
                if isinstance(c, dict):
                    item, count = num(c.get("item"), 1, 65535), num(c.get("count"), 1, 999)
                    if item:
                        catches.append({"item": item, "count": count, "name": clean_text(c.get("name", ""), 40)})
            used = []
            for b in (body.get("bait") or [])[:40]:
                if isinstance(b, dict) and num(b.get("item"), 1, 65535):
                    used.append({"item": num(b.get("item"), 1, 65535), "count": num(b.get("count"), 1, 9999)})
            report = {"id": rid, "char": rec["card"]["name"], "made": int(time.time()), "catches": catches,
                      "skill": num(body.get("skill"), 0, 1100), "gil": num(body.get("gil"), 0, 10 ** 8),
                      "gilFound": num(body.get("gilFound"), 0, 10 ** 7), "bait": used}
            # (2026-11-25) Tetra Master against the computer on the phone: gil won and cards that went up a class.
            # The gil is capped at 40 hard perfect wins at the world's rate in one report.
            tm = body.get("tetra")
            if isinstance(tm, dict):
                rate = float(((rec["card"].get("tetra") or {}).get("gilRate")) or 1.0)
                owned = {c["uid"]: c for c in (rec["card"].get("tetra") or {}).get("cards", [])}
                ups = []
                for u in (tm.get("upgrades") or [])[:200]:
                    if isinstance(u, dict) and u.get("type") in ("X", "A"):
                        c = owned.get(num(u.get("uid"), 1, 10 ** 6, -1))
                        if c and c["id"] == num(u.get("id"), 1, 250):
                            ups.append({"uid": c["uid"], "id": c["id"], "type": u["type"]})
                report["tetra"] = {"gil": min(num(tm.get("gil"), 0, 10 ** 7), int(40 * 1600 * rate) + 1),
                                   "wins": num(tm.get("wins"), 0, 10000), "played": num(tm.get("played"), 0, 10000),
                                   "upgrades": ups}
            q.append(report)
            self.save()
            return {"ok": True}

    # ------------------------------------------------------------ the site
    def visible(self, name, token=None):
        rec = self.cards.get(str(name).lower())
        if not rec or rec["vis"] == "hidden":
            return None
        if rec["vis"] == "link" and token != rec["token"]:
            return None
        return rec

    def public(self):
        return [rec for rec in self.cards.values() if rec["vis"] == "public"]


# ---------------------------------------------------------------------------------------------------- pages (2004)
CSS = """
*{box-sizing:border-box}
body{margin:0;font:400 15px/1.55 'Alegreya Sans','Trebuchet MS','Segoe UI',sans-serif;color:#2a2416;
 background-color:#070d24;background-image:radial-gradient(1px 1px at 12% 18%,rgba(255,255,255,.55) 50%,transparent 51%),
 radial-gradient(1px 1px at 63% 42%,rgba(255,255,255,.45) 50%,transparent 51%),radial-gradient(1.5px 1.5px at 35% 77%,rgba(207,226,255,.55) 50%,transparent 51%),
 linear-gradient(#0b1434,#070d24 600px);background-size:220px 180px,260px 210px,310px 240px,100% 100%;background-attachment:fixed}
a{color:#23408f;text-decoration-color:#d9b45a}
a:hover{color:#9a5b12}
.wrap{max-width:1040px;margin:0 auto;padding:0 0 14px}
.top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;min-height:150px;padding:18px 20px;
 background:#0e1840 url(/img/vana-header.webp) right bottom/auto 100% no-repeat;border:2px solid #8f7a45;border-bottom:0;
 box-shadow:inset 0 -40px 30px -20px rgba(9,15,40,.9)}
.brand{text-decoration:none;color:#f3e7c3;font-family:Cinzel,Georgia,serif;line-height:1}
.brand b{font-size:44px;color:#f3e7c3;text-shadow:0 2px 0 #000,0 0 12px rgba(217,180,90,.5)}
.brand span{font-size:13px;letter-spacing:.22em;color:#d9b45a;margin-left:8px;font-weight:700}
.brand i{display:block;font:italic 14px 'Alegreya Sans',sans-serif;letter-spacing:0;color:#c9d3ef;margin-top:4px}
.nav{display:flex;gap:6px;flex-wrap:wrap}
.nav a{display:inline-block;padding:6px 13px;border-radius:3px;border:1px solid #d9b45a;color:#1b2a5e;font:700 13px Cinzel,Georgia,serif;
 text-decoration:none;background:linear-gradient(#fbf1d2,#e6cf94);box-shadow:0 2px 4px rgba(0,0,0,.4)}
.nav a.blue{color:#f3e7c3;background:linear-gradient(#2a3f86,#172a63 55%,#0c1638)}
.nav a:hover{filter:brightness(1.1)}
.sheet{background:#f3e9cf;border:2px solid #8f7a45;padding:22px;box-shadow:0 0 0 1px #2b220f,0 0 40px rgba(0,0,0,.6)}
.win{border:1px solid #a9b8db;outline:1px solid #0c1638;border-radius:4px;overflow:hidden;background:#f7efd9;margin-bottom:16px;
 box-shadow:0 3px 10px rgba(20,24,50,.35)}
.win>.title{height:30px;display:flex;align-items:center;gap:8px;padding:0 10px;color:#f3e7c3;font:700 14px Cinzel,Georgia,serif;letter-spacing:.03em;
 text-shadow:0 1px 0 #000;background:linear-gradient(#2a3f86,#172a63 55%,#0c1638);border-bottom:1px solid #d9b45a}
.win>.title img{display:none}
.win>.title::before{content:"";width:10px;height:16px;flex:none;background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 16'%3E%3Cpath d='M5 0l5 5v6l-5 5-5-5V5z' fill='%237fcbe6'/%3E%3Cpath d='M5 0v8L0 5z' fill='%23e6f7ff'/%3E%3Cpath d='M5 8l5-3v6l-5 5z' fill='%23387ea3' opacity='.7'/%3E%3C/svg%3E") center/contain no-repeat}
.win>.title .caps{display:none}
.win>.body{padding:12px}
.pane{background:#fffaf0;border:1px solid #c4ab6c;border-radius:2px}
.strip{background:linear-gradient(#efe2bd,#e3d1a0);border-bottom:1px solid #c4ab6c;padding:5px 9px;font:700 13px Cinzel,Georgia,serif;color:#1b2a5e}
.card{display:grid;grid-template-columns:240px 1fr;gap:16px}
@media(max-width:700px){.card{grid-template-columns:1fr}}
.portrait{border:2px solid #8f7a45;outline:1px solid #2b220f;padding:4px;background:#0c1638;position:relative;align-self:start}
.portrait img.face{width:100%;display:block}
.portrait img.mode{position:absolute;right:10px;top:10px;width:52px}
.name{font:700 34px/1.1 Cinzel,Georgia,serif;color:#1b2a5e;margin:0}
.sub{color:#6b5a35;margin:4px 0 10px}
.job{font:700 19px Cinzel,Georgia,serif;color:#2a2416}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{background:#fffaf0;border:1px solid #c4ab6c;border-radius:2px;padding:2px 9px;font-size:13px}
.chip.hc{background:#efe3f6;border-color:#a98bc0;color:#5a1a7d;font-weight:bold}
.chip.dead{background:#2b2238;color:#f3e7c3;border-color:#2b2238}
.equip{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;padding:8px;background:#172a63}
.slot{display:flex;align-items:center;gap:7px;background:linear-gradient(#22357a,#13235a);border:1px solid #5d6fa8;border-radius:2px;
 padding:5px 6px;min-height:52px;color:#f3e7c3}
.slot .ico{width:32px;height:32px;flex:none;border:1px solid #d9b45a;background:#0c1638}
.slot b{display:block;font-size:10.5px;color:#a9b8db;text-transform:uppercase;letter-spacing:.5px}
.slot span{font-size:12.5px}
.slot.empty span{color:#6f7ea8}
table{border-collapse:collapse;width:100%}
td,th{padding:5px 8px;border-bottom:1px solid #eadcb4;text-align:left}
th{font:700 12.5px Cinzel,Georgia,serif;color:#6b5a35}
.jobs{display:grid;grid-template-columns:repeat(auto-fill,minmax(82px,1fr));gap:5px;padding:8px}
.jobs div{background:#fffaf0;border:1px solid #c4ab6c;border-radius:2px;text-align:center;padding:4px}
.jobs div b{display:block;font:700 12px Cinzel,Georgia,serif;color:#6b5a35}
.jobs div.max{background:linear-gradient(#fff3c8,#e8c872);border-color:#b88a35}
.jobs div.off{opacity:.35}
.bar{height:9px;background:#e9dcb8;border-radius:1px;overflow:hidden;border:1px solid #c4ab6c}
.bar i{display:block;height:100%;background:linear-gradient(#7fcbe6,#387ea3)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.grid2{grid-template-columns:1fr}}
.mates{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;padding:8px}
.mate{background:#fffaf0;border:1px solid #c4ab6c;border-radius:2px;padding:6px;text-align:center}
.mate img{width:100%}
.mate details{text-align:left;font-size:12px}
.list td img{width:44px;border:1px solid #8f7a45;vertical-align:middle}
.list td img.m{width:24px;border:0}
form.search{display:flex;gap:6px;margin-bottom:10px}
form.search input{flex:1;padding:7px;border:1px solid #8f7a45;border-radius:2px;font:inherit;background:#fffaf0}
form.search button,.btn{padding:6px 14px;border:1px solid #d9b45a;border-radius:3px;color:#f3e7c3;font:700 13px Cinzel,Georgia,serif;cursor:pointer;
 background:linear-gradient(#2a3f86,#172a63 55%,#0c1638)}
.foot{text-align:center;color:#c9d3ef;font-size:12px;margin:0;padding:12px;background:linear-gradient(#172a63,#0c1638);
 border:2px solid #8f7a45;border-top:1px solid #d9b45a}
.foot a{color:#e8c872}
.b88 img{width:88px;height:31px}
.fame{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:16px;align-items:start}
@media(max-width:520px){.equip{grid-template-columns:repeat(2,1fr)}.brand b{font-size:32px}.brand span{font-size:10px;letter-spacing:.12em;margin-left:5px}.top{min-height:120px;padding:12px}.nav a{padding:5px 9px;font-size:12px}.name{font-size:26px}.sheet{padding:12px}}
.fame ol{margin:0;padding:8px 8px 8px 34px}
.fame li{padding:3px 0}
.empty-note{color:#6b5a35;padding:10px}
"""


def page(title, body, desc="", image=""):
    meta = (f'<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">'
            f'<meta property="og:site_name" content="XI: Forever Offline">'
            + (f'<meta property="og:image" content="https://xiforever.com{esc(image)}">' if image else "")
            + f'<meta name="description" content="{esc(desc)}">')
    nav = ('<div class="nav"><a class="blue" href="/">xiforever.com</a><a href="/armory">Armory</a>'
           '<a href="/armory/fame">Hall of Fame</a><a class="blue" href="/app/">Get the app</a></div>')
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title>{meta}<link rel="icon" href="/armory/static/icon.png"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Alegreya+Sans:ital,wght@0,400;0,700;1,400&display=swap"><style>{CSS}</style></head><body>'
            f'<div class="wrap"><div class="top"><a class="brand" href="/armory"><b>XI</b><span>FOREVER OFFLINE</span><i>The Armory</i></a>{nav}</div>'
            f'<div class="sheet">{body}</div><div class="foot">XI: Forever Offline Armory &middot; characters synced from players\' own worlds &middot; '
            f'Unofficial fan project, not affiliated with Square Enix. FINAL FANTASY XI &copy; SQUARE ENIX CO., LTD.</div></div></body></html>')


def win(title, body, icon="buddy_game.png", pad=True):
    return (f'<div class="win"><div class="title"><img src="/armory/static/{icon}" width="20" alt="">{esc(title)}'
            f'<div class="caps"><span></span><span class="x"></span></div></div>'
            f'<div class="body"{"" if pad else " style=padding:0"}>{body}</div></div>')


def face_url(race, face):
    return f"/armory/static/faces/{FACE_FILES.get(race, 'Hm')}{face // 2 + 1}{'ab'[face % 2]}.jpg"


def job_line(c):
    main = f"{JOBS[c['mjob'] - 1]}{c['mlvl']}"
    return main + (f"/{JOBS[c['sjob'] - 1]}{c['slvl']}" if c.get("sjob") else "")


def equip_grid(equip):
    by = {e["slot"]: e for e in equip}
    order = [0, 1, 2, 3, 4, 9, 11, 12, 5, 6, 13, 14, 15, 10, 7, 8]     # the game's equipment window, row by row
    labels = {0: "Main", 1: "Sub", 2: "Range", 3: "Ammo", 4: "Head", 9: "Neck", 11: "Ear", 12: "Ear", 5: "Body",
              6: "Hands", 13: "Ring", 14: "Ring", 15: "Back", 10: "Waist", 7: "Legs", 8: "Feet"}
    cells = []
    for s in order:
        e = by.get(s)
        icon = (f'<img class="ico" src="/armory/i/{int(e["id"])}.png" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">'
                if e and e.get("id") else '<i class="ico"></i>')
        cells.append(f'<div class="slot{"" if e else " empty"}">{icon}<div><b>{labels[s]}</b><span>{esc(e["name"]) if e else "(empty)"}</span></div></div>')
    return '<div class="equip">' + "".join(cells) + "</div>"


def character_page(rec):
    c = rec["card"]
    race, sex = RACES.get(c["race"], ("Hume", "Male"))
    hc = c.get("hardcore")
    mode_img = f'<img class="mode" src="/armory/static/{MODE_ICONS[hc["mode"]]}" alt="{MODES[hc["mode"]]}">' if hc else ""
    chips = [f'<span class="chip">{esc(race)} {esc(sex)}</span>', f'<span class="chip">{esc(NATIONS.get(c["nation"], ""))}'
             + (f' &middot; Rank {c["rank"]}' if c.get("rank") else "") + '</span>']
    if hc:
        chips.append(f'<span class="chip hc">{MODES[hc["mode"]]}{" hardcore" if hc["mode"] != 4 else ""}</span>')
        if hc.get("dead"):
            chips.append('<span class="chip dead">Fallen</span>')
        if hc.get("deaths") and hc["mode"] == 2:
            chips.append(f'<span class="chip">{hc["deaths"]} Steel falls</span>')
    if c.get("world"):
        chips.append(f'<span class="chip">World: {esc(c["world"])}</span>')
    stats = [("Playtime", fmt_time(c.get("playtime"))), ("Quests done", c.get("quests", 0)), ("Titles", c.get("titles", 0)),
             ("Key items", c.get("keyitems", 0))]
    if c.get("hp"):
        stats.insert(0, ("HP / MP", f'{c["hp"]} / {c["mp"]}'))
    stat_rows = "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in stats)
    head = (f'<div class="card"><div class="portrait"><img class="face" src="{face_url(c["race"], c["face"])}" alt="">{mode_img}</div>'
            f'<div><p class="name">{esc(c["name"])}</p><div class="sub">{esc(c.get("bio") or DEFAULT_BIO)}</div>'
            f'<div class="job">{esc(job_line(c))}</div><div class="chips">{"".join(chips)}</div>'
            f'<div class="pane">{equip_grid(c.get("equip", []))}</div></div></div>')
    jobs = "".join(f'<div class="{"max" if c["jobs"].get(j, 0) >= 75 else ("off" if not c["jobs"].get(j) else "")}"><b>{j}</b>{c["jobs"].get(j, 0) or "-"}</div>'
                   for j in ERA_JOBS)
    crafts = ""
    for k in CRAFTS:
        v = (c.get("crafts") or {}).get(k)
        if k == "Fishing" and c.get("fishing"):
            v = {"skill": c["fishing"].get("skill", 0), "rank": c["fishing"].get("rank", 0)}
        skill = (v or {}).get("skill", 0)
        crafts += (f'<tr><th style="width:110px">{k}</th><td style="width:60px">{skill:.1f}</td>'
                   f'<td><div class="bar"><i style="width:{min(100, skill)}%"></i></div></td></tr>')
    fished = (c.get("fishing") or {}).get("catches")
    if fished:
        crafts += f'<tr><th>Fish caught</th><td colspan="2">{fished} (phone fishing)</td></tr>'
    mates = ""
    for m in c.get("squad", []):
        gear = "".join(f"<div>{esc(e['name'])}</div>" for e in m.get("equip", []) if e.get("name"))
        mates += (f'<div class="mate"><img src="{face_url(m["race"], m["face"])}" alt=""><b>{esc(m["name"])}</b>'
                  f'<div>{JOBS[m["mjob"] - 1]}{m["level"]}{("/" + JOBS[m["sjob"] - 1]) if m.get("sjob") else ""}</div>'
                  + (f'<div style="color:#4a6b84;font-size:12px">{esc(m["role"])}</div>' if m.get("role") else "")
                  + (f"<details><summary>Gear</summary>{gear}</details>" if gear else "") + "</div>")
    body = win(f'{c["name"]} - Character Profile', head)
    body += '<div class="grid2">' + win("Jobs", f'<div class="pane"><div class="jobs">{jobs}</div></div>') + \
        win("Crafts & Fishing", f'<div class="pane"><table>{crafts}</table></div>', "buddy_web.png") + "</div>"
    body += '<div class="grid2">' + win("Adventure", f'<div class="pane"><table>{stat_rows}</table></div>', "buddy_phone.png")
    fame = c.get("fame") or {}
    fame_rows = "".join(f"<tr><th>{k.title().replace('Sandoria', 'San d&#39;Oria')}</th><td>{'&#9733;' * v}{'&#9734;' * (9 - v)}</td></tr>"
                        for k, v in fame.items())
    body += win("Fame", f'<div class="pane"><table>{fame_rows or "<tr><td>Not yet famous.</td></tr>"}</table></div>', "buddy_game.png") + "</div>"
    if mates:
        body += win(c["name"] + "'s Squad", f'<div class="pane"><div class="mates">{mates}</div></div>', "buddy_game.png")
    body += f'<div style="text-align:center;color:#6b5a35;font-size:13px">Last synced {ago(rec["synced"])}</div>'
    desc = f'{race} {sex} {job_line(c)} of {NATIONS.get(c["nation"], "")}' + (f', {MODES[hc["mode"]]} mode' if hc else "")
    return page(f'{c["name"]} - XI: Forever Offline', body, desc, face_url(c["race"], c["face"]))


def list_rows(recs):
    rows = ""
    for rec in recs:
        c = rec["card"]
        race, sex = RACES.get(c["race"], ("Hume", "Male"))
        hc = c.get("hardcore")
        rows += (f'<tr><td><img src="{face_url(c["race"], c["face"])}" alt=""></td><td><a href="/c/{quote(c["name"])}"><b>{esc(c["name"])}</b></a>'
                 + (f' <img class="m" src="/armory/static/{MODE_ICONS[hc["mode"]]}" alt="{MODES[hc["mode"]]}">' if hc else "")
                 + f'</td><td>{esc(job_line(c))}</td><td>{esc(race)} {esc(sex)}</td><td>{esc(NATIONS.get(c["nation"], ""))}</td>'
                 f'<td>{ago(rec["synced"])}</td></tr>')
    return rows


def armory_page(arm, q, pg):
    recs = arm.public()
    if q:
        recs = [r for r in recs if q.lower() in r["card"]["name"].lower()]
    recs.sort(key=lambda r: (-r["card"]["mlvl"], r["card"]["name"]))
    pages = max(1, math.ceil(len(recs) / PAGE))
    pg = max(1, min(pg, pages))
    shown = recs[(pg - 1) * PAGE: pg * PAGE]
    form = (f'<form class="search" action="/armory"><input name="q" value="{esc(q)}" placeholder="Search a character name...">'
            f'<button>Search</button></form>')
    table = (f'<div class="pane list"><table><tr><th></th><th>Name</th><th>Job</th><th>Race</th><th>Nation</th><th>Synced</th></tr>'
             f'{list_rows(shown)}</table>' + ("" if shown else '<div class="empty-note">No characters here yet. Press SYNC in your launcher\'s Characters page to be the first!</div>') + '</div>')
    links = ""
    if pages > 1:
        links = '<div style="margin-top:8px">' + " ".join(
            (f"<b>{i}</b>" if i == pg else f'<a href="/armory?page={i}&q={quote(q)}">{i}</a>') for i in range(1, pages + 1)) + "</div>"
    body = win(f"Armory - {len(recs)} adventurer{'s' if len(recs) != 1 else ''}", form + table + links, "buddy_web.png")
    return page("Armory - XI: Forever Offline", body, "Characters of XI: Forever Offline players.")


def fame_page(arm):
    recs = arm.public()

    def top(key, n=10, cond=lambda r: True):
        return sorted([r for r in recs if cond(r)], key=key)[:n]

    def ol(items, fmt):
        if not items:
            return '<div class="empty-note">Nobody yet.</div>'
        return "<ol>" + "".join(f'<li><a href="/c/{quote(r["card"]["name"])}">{esc(r["card"]["name"])}</a> &middot; {fmt(r)}</li>' for r in items) + "</ol>"

    def total(r):
        return sum(r["card"]["jobs"].get(j, 0) for j in ERA_JOBS)

    boxes = [
        ("Highest levels", ol(top(lambda r: (-r["card"]["mlvl"], -total(r))), lambda r: job_line(r["card"])), "buddy_game.png"),
        ("Most jobs at 75", ol(top(lambda r: -sum(1 for j in ERA_JOBS if r["card"]["jobs"].get(j, 0) >= 75),
                                   cond=lambda r: any(v >= 75 for v in r["card"]["jobs"].values())),
                               lambda r: (lambda n: f'{n} job{"s" if n != 1 else ""}')(sum(1 for j in ERA_JOBS if r["card"]["jobs"].get(j, 0) >= 75))), "buddy_game.png"),
        ("Master anglers", ol(top(lambda r: -(r["card"].get("fishing") or {}).get("skill", 0),
                                  cond=lambda r: (r["card"].get("fishing") or {}).get("skill", 0) > 0),
                              lambda r: f'fishing {(r["card"].get("fishing") or {}).get("skill", 0):.1f}'), "buddy_phone.png"),
        ("Longest adventures", ol(top(lambda r: -r["card"].get("playtime", 0)), lambda r: fmt_time(r["card"].get("playtime"))), "buddy_web.png"),
    ]
    for mode in (1, 2, 3, 4):
        alive = top(lambda r: (-r["card"]["mlvl"], r["card"]["name"]),
                    cond=lambda r, m=mode: (r["card"].get("hardcore") or {}).get("mode") == m and not r["card"]["hardcore"].get("dead"))
        boxes.append((f"{MODES[mode]}: still standing", ol(alive, lambda r: job_line(r["card"])), MODE_ICONS[mode]))
    fallen = top(lambda r: (-r["card"]["mlvl"], r["card"]["name"]), 20,
                 cond=lambda r: (r["card"].get("hardcore") or {}).get("dead"))
    boxes.append(("Silver memorial", ol(fallen, lambda r: f'fell at {job_line(r["card"])}'), "hc_silver.png"))
    body = '<div class="fame">' + "".join(win(t, f'<div class="pane">{b}</div>', i) for t, b, i in boxes) + "</div>"
    return page("Hall of Fame - XI: Forever Offline", body, "The best of XI: Forever Offline.")


def not_found():
    return page("Not here - XI: Forever Offline", win("Not found", '<div class="pane empty-note">No character by that name is shown here. '
                                                     'It may be hidden, or not synced yet.</div>'))


# ---------------------------------------------------------------------------------------------------- HTTP
TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".ttf": "font/ttf", ".css": "text/css"}


def make_handler(arm, static):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XifoArmory/1"

        def log_message(self, *args):
            pass

        def send(self, code, data, ctype, cache=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            if cache:
                self.send_header("Cache-Control", cache)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def reply(self, code, body):
            self.send(code, json.dumps(body).encode(), "application/json", "no-store")

        def html(self, code, text):
            self.send(code, text.encode("utf-8"), "text/html; charset=utf-8", "no-cache")

        def owner(self):
            key = self.headers.get("X-Armory-Key", "")
            return h("owner|" + key) if KEY_RE.fullmatch(key or "") else None

        def phone(self):
            key = self.headers.get("X-Armory-Phone", "")
            return h("phone|" + key) if KEY_RE.fullmatch(key or "") else None

        def body(self):
            size = int(self.headers.get("Content-Length") or 0)
            if size <= 0 or size > MAX_BODY:
                return {}
            try:
                value = json.loads(self.rfile.read(size))
                return value if isinstance(value, dict) else {}
            except ValueError:
                return {}

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            url = urlparse(self.path)
            path = url.path.rstrip("/") or "/"
            qs = parse_qs(url.query)
            if path == "/armory/health":
                return self.reply(200, {"ok": True, "characters": len(arm.cards), "public": len(arm.public())})
            if path.startswith("/armory/static/"):
                rel = unquote(path[len("/armory/static/"):])
                if not re.fullmatch(r"(faces/)?[A-Za-z0-9_.-]+\.(png|jpg|ttf)", rel):
                    return self.send(404, b"not found", "text/plain")
                full = os.path.join(static, rel)
                if not os.path.isfile(full):
                    return self.send(404, b"not found", "text/plain")
                with open(full, "rb") as handle:
                    return self.send(200, handle.read(), TYPES[os.path.splitext(full)[1]], "public, max-age=86400")
            m = re.fullmatch(r"/armory/i/(\d{1,5})\.png", path)
            if m:
                data = arm.icon(int(m.group(1)))
                return self.send(200, data, "image/png", "public, max-age=604800") if data else self.send(404, b"not found", "text/plain")
            if path == "/armory":
                return self.html(200, armory_page(arm, clean_text(qs.get("q", [""])[0], 20), num(qs.get("page", ["1"])[0], 1, 10000, 1)))
            if path == "/armory/fame":
                return self.html(200, fame_page(arm))
            m = re.fullmatch(r"/c/([A-Za-z]{3,15})", path)
            if m:
                with arm.lock:
                    rec = arm.visible(m.group(1), qs.get("k", [None])[0])
                    text = character_page(rec) if rec else None
                return self.html(200, text) if text else self.html(404, not_found())
            if path == "/armory/api/list":
                q = clean_text(qs.get("q", [""])[0], 20).lower()
                with arm.lock:
                    recs = [r for r in arm.public() if q in r["card"]["name"].lower()]
                    recs.sort(key=lambda r: (-r["card"]["mlvl"], r["card"]["name"]))
                    pg = num(qs.get("page", ["1"])[0], 1, 10000, 1)
                    out = [{"name": r["card"]["name"], "race": r["card"]["race"], "face": r["card"]["face"],
                            "job": job_line(r["card"]), "hardcore": r["card"].get("hardcore"), "synced": r["synced"]}
                           for r in recs[(pg - 1) * PAGE: pg * PAGE]]
                return self.reply(200, {"total": len(recs), "page": pg, "characters": out})
            m = re.fullmatch(r"/armory/api/c/([A-Za-z]{3,15})", path)
            if m:
                with arm.lock:
                    rec = arm.visible(m.group(1), qs.get("k", [None])[0])
                    out = {"card": public_card(rec["card"]), "synced": rec["synced"]} if rec else None
                return self.reply(200, out) if out else self.reply(404, {"error": "not shown"})
            if path == "/armory/api/me":
                phone = self.phone()
                owner = phone and arm.owner_of_phone(phone)
                if not owner:
                    return self.reply(403, {"error": "This phone is not paired. Pair it from the launcher's Characters page."})
                return self.reply(200, arm.me(owner))
            if path in ("/armory/api/ventures", "/armory/api/ventures/launcher", "/armory/api/ventures/game"):
                if not arm.ventures:
                    return self.reply(503, {"error": "Ventures are not running on this server yet."})
                if path == "/armory/api/ventures/launcher":
                    owner = self.owner()
                    return self.reply(200, arm.ventures.launcher(owner)) if owner else self.reply(403, {"error": "no key"})
                if path == "/armory/api/ventures/game":
                    # (2026-11-26) the in-game window (the kit's venture add-on, through the launcher): the same list
                    # the paired phone sees, asked for with the launcher's own key
                    owner = self.owner()
                    if not owner:
                        return self.reply(403, {"error": "no key"})
                    return self.reply(200, arm.ventures.phone(owner, qs.get("camps", ["0"])[0] == "1"))
                phone = self.phone()
                owner = phone and arm.owner_of_phone(phone)
                if not owner:
                    return self.reply(403, {"error": "This phone is not paired. Pair it from the launcher's Characters page."})
                return self.reply(200, arm.ventures.phone(owner, qs.get("camps", ["0"])[0] == "1"))
            if path == "/armory/api/fish":
                owner = self.owner()
                if not owner:
                    return self.reply(403, {"error": "no key"})
                return self.reply(200, arm.reports(owner))
            if path in ("/armory/api/tm/lobby", "/armory/api/tm/poll"):
                if not arm.tetra:
                    return self.reply(503, {"error": "Tetra Master matches are not running on this server yet."})
                phone = self.phone()
                owner = phone and arm.owner_of_phone(phone)
                if not owner:
                    return self.reply(403, {"error": "This phone is not paired. Pair it from the launcher's Characters page."})
                if path == "/armory/api/tm/lobby":
                    return self.reply(200, arm.tetra.lobby(owner, qs.get("char", [""])[0]))
                return self.reply(200, arm.tetra.poll(phone, qs.get("t", [""])[0], qs.get("since", ["0"])[0]))
            return self.html(404, not_found())

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            body = self.body()
            if path in ("/armory/api/tm/queue", "/armory/api/tm/move", "/armory/api/tm/leave"):
                if not arm.tetra:
                    return self.reply(503, {"error": "Tetra Master matches are not running on this server yet."})
                phone = self.phone()
                owner = phone and arm.owner_of_phone(phone)
                if not owner:
                    return self.reply(403, {"error": "This phone is not paired."})
                if path == "/armory/api/tm/queue":
                    return self.reply(200, arm.tetra.queue(owner, phone, body))
                if path == "/armory/api/tm/move":
                    return self.reply(200, arm.tetra.move(phone, body))
                return self.reply(200, arm.tetra.leave(phone, body))
            if path.startswith("/armory/api/ventures/"):
                if not arm.ventures:
                    return self.reply(503, {"error": "Ventures are not running on this server yet."})
                what = path[len("/armory/api/ventures/"):]
                if what in ("roster", "applied"):
                    owner = self.owner()
                    if not owner:
                        return self.reply(403, {"error": "no key"})
                    return self.reply(200, arm.ventures.roster(owner, body) if what == "roster"
                                      else arm.ventures.applied(owner, body.get("ids")))
                if what in ("start", "recall", "seen", "game/start", "game/recall", "game/seen"):
                    if what.startswith("game/"):                      # (2026-11-26) sent in game: the launcher's key
                        what = what[5:]
                        owner = self.owner()
                        if not owner:
                            return self.reply(403, {"error": "no key"})
                    else:
                        phone = self.phone()
                        owner = phone and arm.owner_of_phone(phone)
                        if not owner:
                            return self.reply(403, {"error": "This phone is not paired."})
                    if what == "start":
                        return self.reply(200, arm.ventures.start(owner, body))
                    return self.reply(200, getattr(arm.ventures, what)(owner, body.get("id")))
                return self.reply(404, {"error": "unknown"})
            if path in ("/armory/api/sync", "/armory/api/pair", "/armory/api/unpair", "/armory/api/fish/done"):
                owner = self.owner()
                if not owner:
                    return self.reply(403, {"error": "no key"})
                if path == "/armory/api/sync":
                    return self.reply(200, arm.sync(owner, body))
                if path == "/armory/api/pair":
                    return self.reply(200, arm.pair(owner))
                if path == "/armory/api/unpair":
                    return self.reply(200, arm.unpair(owner))
                return self.reply(200, arm.reports_done(owner, body.get("ids")))
            if path in ("/armory/api/claim", "/armory/api/fish"):
                phone = self.phone()
                if not phone:
                    return self.reply(403, {"error": "no key"})
                if path == "/armory/api/claim":
                    return self.reply(200, arm.claim(phone, body.get("code")))
                owner = arm.owner_of_phone(phone)
                if not owner:
                    return self.reply(403, {"error": "This phone is not paired."})
                return self.reply(200, arm.fish(owner, body))
            return self.reply(404, {"error": "unknown"})

    return Handler


def main():
    ap = argparse.ArgumentParser(description="XI: Forever Offline armory")
    ap.add_argument("--port", type=int, default=54302)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--data", default="/var/lib/xifo-armory")
    ap.add_argument("--static", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static"))
    args = ap.parse_args()
    arm = Armory(args.data)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(arm, args.static))
    server.daemon_threads = True
    print(f"armory on {args.host}:{args.port}, {len(arm.cards)} characters", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
