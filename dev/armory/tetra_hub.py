"""Tetra Master PvP for the XIFO app (2026-11-25, the user: "add pvp for people to play in the app against each other,
maybe random with whoever is playing"). Part of the armory service (armory_service.py routes /armory/api/tm/*).

A paired phone picks one of its characters and 5 of that character's cards (as the launcher last synced them: the
same cards, with the same hidden numbers, as in the game) and joins the queue. The first two players waiting from two
different phones are matched. The hub runs the match with its own dice (tetra_rules.py, the server's rules), so neither
app decides anything: each sends its moves and gets back what happened.

  GET  /armory/api/tm/lobby?char=Name     how many are waiting and playing; the character's PvP record
  POST /armory/api/tm/queue {char, uids}  join (5 card numbers from the character's collection) -> {ticket}
  GET  /armory/api/tm/poll?t=&since=n     waits up to 20 s: {state: waiting} or the match from event n on
  POST /armory/api/tm/move {t, hand, x, y} or {t, battle}
  POST /armory/api/tm/leave {t}           stop waiting, or give up the match (the other player wins)

A turn has TURN_SECONDS. When it runs out the hub plays a random move for that player (Nalfey's easy AI); after
MAX_TIMEOUTS in a row that player has left and loses. Like the game, no cards change hands: a match only counts in
the win / loss / draw record (kept in <data>/tetra.json). Matches themselves live in memory only."""
import json
import os
import secrets
import threading
import time

import tetra_rules as T

TURN_SECONDS = 45
MAX_TIMEOUTS = 2
WAIT_DROP = 45            # a waiting ticket that is not polled this long is dropped
MATCH_KEEP = 600          # a finished match stays readable this long
POLL_WAIT = 20


def _num(v, lo, hi, default=None):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    return v if lo <= v <= hi else default


class Tetra:
    def __init__(self, folder, arm):
        self.arm = arm
        self.path = os.path.join(folder, "tetra.json")
        self.cv = threading.Condition(threading.RLock())
        self.records = {}
        try:
            with open(self.path, encoding="utf-8") as f:
                self.records = json.load(f).get("records", {})
        except (OSError, ValueError):
            pass
        self.waiting = []           # tickets: {t, phone, char, look, hand, seen}
        self.tickets = {}           # t -> ticket (waiting) or {t, phone, match, side}
        self.matches = {}           # id -> match record
        self.rng = T.sys_rng()
        threading.Thread(target=self._clock, daemon=True).start()

    # ------------------------------------------------------------------ helpers
    def _save(self):
        with open(self.path + ".part", "w", encoding="utf-8") as f:
            json.dump({"records": self.records}, f)
        os.replace(self.path + ".part", self.path)

    def _record(self, name):
        r = self.records.get(name.lower()) or {}
        return {"w": int(r.get("w", 0)), "l": int(r.get("l", 0)), "d": int(r.get("d", 0))}

    def _character(self, owner, name):
        """The synced card of one of this owner's characters, with Tetra Master unlocked, or (None, reason)."""
        with self.arm.lock:
            rec = self.arm.cards.get(str(name).lower())
            if not rec or rec["owner"] != owner:
                return None, "Not one of your characters."
            card = rec["card"]
        tm = card.get("tetra") or {}
        if not tm.get("unlocked"):
            return None, f"{card['name']} hasn't unlocked Tetra Master yet: visit Luto Mewrilah in Upper Jeuno in the game."
        return card, None

    def lobby(self, owner, name):
        with self.cv:
            self._sweep()
            playing = sum(2 for m in self.matches.values() if not m["over"])
            out = {"waiting": len(self.waiting), "playing": playing, "turnSeconds": TURN_SECONDS}
        if name:
            with self.arm.lock:
                rec = self.arm.cards.get(str(name).lower())
            if rec and rec["owner"] == owner:
                out["record"] = self._record(rec["card"]["name"])
        return out

    # ------------------------------------------------------------------ joining
    def queue(self, owner, phone, body):
        card, why = self._character(owner, body.get("char", ""))
        if not card:
            return {"error": why}
        uids = body.get("uids")
        if not isinstance(uids, list) or len(uids) != T.HAND_SIZE or len({str(u) for u in uids}) != T.HAND_SIZE:
            return {"error": "Pick 5 different cards."}
        mine = {int(c["uid"]): c for c in (card.get("tetra") or {}).get("cards", []) if isinstance(c, dict) and "uid" in c}
        hand = []
        for u in uids:
            c = mine.get(_num(u, 1, 10 ** 6, -1))
            if not c:
                return {"error": "That card isn't in your collection any more. Press PLAY in the launcher to sync your cards."}
            hand.append({k: c[k] for k in ("uid", "id", "type", "arrows", "atk", "pdef", "mdef")})
        look = {"name": card["name"], "race": card.get("race", 1), "face": card.get("face", 0)}
        with self.cv:
            self._sweep()
            self._drop_phone(phone)
            other = next((w for w in self.waiting if w["phone"] != phone and w["char"].lower() != card["name"].lower()), None)
            t = secrets.token_hex(12)
            me = {"t": t, "phone": phone, "char": card["name"], "look": look, "hand": hand, "seen": time.time()}
            if other is None:
                self.waiting.append(me)
                self.tickets[t] = me
            else:
                self.waiting.remove(other)
                self._start(other, me)
            self.cv.notify_all()
            return {"ticket": t}

    def _drop_phone(self, phone):
        """A phone plays one match at a time: joining again ends what it had (a match it leaves is lost)."""
        for w in [w for w in self.waiting if w["phone"] == phone]:
            self.waiting.remove(w)
            self.tickets.pop(w["t"], None)
        for t, tk in list(self.tickets.items()):
            if tk.get("phone") == phone and tk.get("match"):
                m = self.matches.get(tk["match"])
                if m and not m["over"]:
                    self._finish(m, T.opposite(tk["side"]), "left")

    def _start(self, a, b):
        mid = secrets.token_hex(8)
        sides = {"blue": a, "red": b} if self.rng(1, 2) == 1 else {"blue": b, "red": a}
        first = "blue" if self.rng(1, 2) == 1 else "red"
        m = T.new_match(self.rng, {"blue": sides["blue"]["hand"], "red": sides["red"]["hand"]}, first)
        blocks = [{"x": x, "y": y, "block": m["cells"][x][y]["block"]} for x in range(1, 5) for y in range(1, 5)
                  if m["cells"][x][y] is not None]
        rec = {"id": mid, "m": m, "players": {s: {"phone": p["phone"], "char": p["char"], "look": p["look"]} for s, p in sides.items()},
               "events": [], "over": False, "result": None, "blocks": blocks, "first": first, "deadline": time.time() + TURN_SECONDS,
               "timeouts": {"blue": 0, "red": 0}, "ended": 0}
        self.matches[mid] = rec
        for side, p in sides.items():
            self.tickets[p["t"]] = {"t": p["t"], "phone": p["phone"], "match": mid, "side": side}

    # ------------------------------------------------------------------ playing
    def _ticket(self, phone, t):
        tk = self.tickets.get(str(t or ""))
        return tk if tk and tk["phone"] == phone else None

    def _view(self, tk, since):
        if not tk.get("match"):
            tk["seen"] = time.time()
            return {"state": "waiting", "waiting": len(self.waiting), "playing": sum(2 for m in self.matches.values() if not m["over"])}
        m = self.matches.get(tk["match"])
        if not m:
            return {"state": "gone"}
        side, other = tk["side"], T.opposite(tk["side"])
        mt = m["m"]
        return {
            "state": "over" if m["over"] else "playing", "match": m["id"], "you": side, "first": m["first"], "blocks": m["blocks"],
            "hand": [dict(c, n=i + 1) for i, c in enumerate(mt["hands"][side])] if not m["over"] else [],
            "opponent": dict(m["players"][other]["look"], cards=len(mt["hands"][other]), record=self._record(m["players"][other]["char"])),
            "turn": mt["turn"], "pending": mt["pending"] if mt["turn"] == side else None,
            "seconds": max(0, int(m["deadline"] - time.time())) if not m["over"] else 0,
            "events": m["events"][since:], "next": len(m["events"]), "result": m["result"],
        }

    def poll(self, phone, t, since):
        since = _num(since, 0, 10 ** 6, 0)
        end = time.time() + POLL_WAIT
        with self.cv:
            tk = self._ticket(phone, t)
            if not tk:
                return {"state": "gone"}
            while True:
                self._sweep()
                v = self._view(tk, since)
                if v["state"] in ("gone", "over") or (v["state"] == "playing" and (v["events"] or since == 0)):
                    return v
                if v["state"] == "waiting" and not tk.get("told"):      # the first look answers at once
                    tk["told"] = True
                    return v
                left = end - time.time()
                if left <= 0:
                    return v
                self.cv.wait(min(left, 2.0))
                tk = self._ticket(phone, t)
                if not tk:
                    return {"state": "gone"}

    def move(self, phone, body):
        with self.cv:
            tk = self._ticket(phone, body.get("t"))
            if not tk or not tk.get("match"):
                return {"error": "No match."}
            m = self.matches.get(tk["match"])
            if not m or m["over"]:
                return {"error": "The match is over."}
            side = tk["side"]
            if "battle" in body:
                events, err = T.choose_battle(m["m"], side, _num(body.get("battle"), 1, 8, 0))
            else:
                events, err = T.place(m["m"], side, _num(body.get("hand"), 1, 5, 0), _num(body.get("x"), 1, 4, 0), _num(body.get("y"), 1, 4, 0))
            if err:
                return {"error": err}
            m["timeouts"][side] = 0
            self._add(m, events)
            self.cv.notify_all()
            return {"ok": True, "next": len(m["events"])}

    def leave(self, phone, body):
        with self.cv:
            tk = self._ticket(phone, body.get("t"))
            if not tk:
                return {"ok": True}
            if tk.get("match"):
                m = self.matches.get(tk["match"])
                if m and not m["over"]:
                    self._finish(m, T.opposite(tk["side"]), "left")
            else:
                self.waiting = [w for w in self.waiting if w["t"] != tk["t"]]
                self.tickets.pop(tk["t"], None)
            self.cv.notify_all()
            return {"ok": True}

    # ------------------------------------------------------------------ the match's clock
    def _add(self, m, events):
        for e in events:
            e = dict(e)
            e["n"] = len(m["events"])
            m["events"].append(e)
        m["deadline"] = time.time() + TURN_SECONDS
        if m["m"]["over"]:
            winner, perfect = T.result(m["m"])
            self._finish(m, winner, "perfect" if perfect else "score")

    def _finish(self, m, winner, how):
        if m["over"]:
            return
        m["over"] = True
        m["ended"] = time.time()
        b, r = T.score(m["m"])
        m["result"] = {"winner": winner, "how": how, "blue": b, "red": r}
        if how == "left":
            m["events"].append({"type": "left", "winner": winner, "n": len(m["events"])})
        for side, p in m["players"].items():
            key = p["char"].lower()
            rec = self.records.setdefault(key, {"w": 0, "l": 0, "d": 0})
            rec["w" if winner == side else "d" if winner == "draw" else "l"] += 1
        try:
            self._save()
        except OSError:
            pass

    def _sweep(self):
        now = time.time()
        for w in [w for w in self.waiting if now - w["seen"] > WAIT_DROP]:
            self.waiting.remove(w)
            self.tickets.pop(w["t"], None)
        for mid, m in list(self.matches.items()):
            if m["over"]:
                if now - m["ended"] > MATCH_KEEP:
                    del self.matches[mid]
                    for t in [t for t, tk in self.tickets.items() if tk.get("match") == mid]:
                        self.tickets.pop(t, None)
                continue
            if now >= m["deadline"]:
                mt = m["m"]
                side = mt["turn"]
                m["timeouts"][side] += 1
                if m["timeouts"][side] > MAX_TIMEOUTS:
                    self._finish(m, T.opposite(side), "left")
                    continue
                if mt["pending"]:
                    events, _ = T.choose_battle(mt, side, self.rng(1, len(mt["pending"])))
                else:
                    h, x, y = T.random_move(mt, side, self.rng)
                    events, _ = T.place(mt, side, h, x, y)
                events = [dict(e, auto=True) if i == 0 else e for i, e in enumerate(events or [])]
                self._add(m, events)

    def _clock(self):
        while True:
            time.sleep(1.0)
            with self.cv:
                before = sum(len(m["events"]) for m in self.matches.values())
                self._sweep()
                if sum(len(m["events"]) for m in self.matches.values()) != before:
                    self.cv.notify_all()
