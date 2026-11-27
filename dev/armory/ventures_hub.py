"""The hub's side of Ventures (armory_service.py calls these). Plain files under <data>/ventures.

  POST /armory/api/ventures/roster   (launcher key) {"chars": [{"name", "mates": [...], "bots": [...]}]}
  GET  /armory/api/ventures/launcher (launcher key) -> {"away": [{char, slot, end}], "done": [result...]}
  POST /armory/api/ventures/applied  (launcher key) {"ids": [...]}
  GET  /armory/api/ventures?camps=1  (phone key)    -> {"now", "roster", "ventures", "camps"?}
  POST /armory/api/ventures/start    (phone key)    {"id", "char", "slots": [..], "camp", "hours"}
  POST /armory/api/ventures/recall   (phone key)    {"id"}
  POST /armory/api/ventures/seen     (phone key)    {"id"}
  GET  /armory/api/ventures/game     (launcher key) -> the same as the phone's GET     } (2026-11-26) for the in-game
  POST /armory/api/ventures/game/start | recall | seen   (launcher key), as the phone's } window, through the launcher

The kit's launcher runs this same class as its own planner when no app is paired or the hub can't be reached
(launcher_ventures.py: owner "local", files in <kit>/ventures), so Ventures also work with no internet.

A mate is "out" from the moment it leaves until its venture ends (or is recalled): the launcher tells the game, which
will not call it meanwhile. The rewards are worked out from the plan (ventures.py) and handed to the launcher once the
venture is over; it says when they are in the game, and they are never handed out twice.
"""
import json
import os
import re
import time

import ventures as V

ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
NAME_RE = re.compile(r"^[A-Za-z]{3,15}$")
KEEP_DONE = 40                 # finished ventures kept per character (the app's postcard album)
MAX_OUT = 60                   # ventures out at once per launcher


def _num(v, lo, hi, default=0):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _clean_name(v):
    v = str(v or "")
    return v if NAME_RE.match(v) else None


class Ventures:
    def __init__(self, folder, lock, now=time.time):
        self.folder = os.path.join(folder, "ventures")
        os.makedirs(os.path.join(self.folder, "plans"), exist_ok=True)
        self.lock, self.now = lock, now
        self.state = {"roster": {}, "list": {}}
        path = os.path.join(self.folder, "state.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.state.update(json.load(f))

    # ---------------------------------------------------------------- storage
    def _write(self, path, data):
        with open(path + ".part", "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(path + ".part", path)

    def save(self):
        self._write(os.path.join(self.folder, "state.json"), self.state)

    def plan(self, vid):
        try:
            with open(os.path.join(self.folder, "plans", vid + ".json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _effective(self, owner, ch, now):
        """(2026-11-25) The character's mates as they stand now: the roster's level and exp, moved on by every venture
        that is over but not in the game yet (or put in the game after the roster was last sent). Without this a
        second venture started before you played again began from the old level."""
        mates = [dict(m) for m in ch.get("mates", [])]
        by_slot = {m["slot"]: m for m in mates}
        at = ch.get("at", 0)
        done = [v for v in self.state["list"].get(owner, []) if v["char"].lower() == ch["name"].lower() and now >= v["end"]
                and (not v.get("applied") or v.get("appliedAt", 0) > at)]
        for v in sorted(done, key=lambda v: v["end"]):
            plan = self.plan(v["id"])
            if not plan:
                continue
            for slot, (lv, xp) in V.end_state(plan, v["end"] - v["start"]).items():
                m = by_slot.get(slot)
                if m and (lv, xp) > (m["level"], m.get("exp", 0)):
                    m["level"], m["exp"] = lv, xp
        return mates

    # ---------------------------------------------------------------- launcher
    def roster(self, owner, body):
        """The launcher's squads: every home character's mates (slot, looks, job, level, progress) and a few of the
        world's bot players (they show up in the parties)."""
        out = {}
        for ch in (body.get("chars") or [])[:40]:
            name = _clean_name((ch or {}).get("name"))
            if not name:
                continue
            mates = []
            for m in (ch.get("mates") or [])[:12]:
                mname = str((m or {}).get("name", ""))[:20]
                if not mname:
                    continue
                mates.append({"slot": _num(m.get("slot"), 0, 31), "name": mname, "race": _num(m.get("race"), 1, 8, 1),
                              "face": _num(m.get("face"), 0, 15), "weapon": _num(m.get("weapon"), 0, 60),
                              "job": _num(m.get("job"), 1, 22, 1),
                              "sjob": _num(m.get("sjob"), 0, 22), "level": _num(m.get("level"), 1, 99, 1),
                              "exp": _num(m.get("exp"), 0, 100000)})
            bots = [{"name": b["name"], "race": _num(b.get("race"), 1, 8, 1)} for b in (ch.get("bots") or [])[:30]
                    if isinstance(b, dict) and _clean_name(b.get("name"))]
            out[name.lower()] = {"name": name, "mates": mates, "bots": bots, "at": int(self.now())}
        with self.lock:
            self.state["roster"][owner] = out
            self.save()
        return {"ok": True, "chars": len(out)}

    def launcher(self, owner):
        now = self.now()
        with self.lock:
            away, done = [], []
            for v in self.state["list"].get(owner, []):
                if v.get("applied"):
                    continue
                if now < v["end"]:
                    for slot in v["slots"]:
                        away.append({"id": v["id"], "char": v["char"], "slot": slot, "end": v["end"], "camp": v["campTitle"]})
                    continue
                plan = self.plan(v["id"])
                if not plan:
                    continue
                res = V.results(plan, v["end"] - v["start"])
                done.append({"id": v["id"], "char": v["char"], "camp": v["campTitle"],
                             "mates": [{"slot": m["slot"], "name": m["name"], "exp": res["exp"][i],
                                        "level": res["levels"][i]} for i, m in enumerate(plan["mates"])],
                             "gil": res["gil"], "items": [[iid, c] for iid, c, _ in res["items"]]})
            return {"away": away, "done": done, "now": int(now)}

    def applied(self, owner, ids):
        ids = {str(i) for i in (ids or [])[:200]}
        with self.lock:
            for v in self.state["list"].get(owner, []):
                if v["id"] in ids and not v.get("applied"):
                    v["applied"], v["appliedAt"] = True, int(self.now())
            self.save()
        return {"ok": True}

    # ---------------------------------------------------------------- phone
    def _public(self, v, now):
        plan = self.plan(v["id"])
        if not plan:
            return None
        cut = int(min(now, v["end"]) - v["start"])
        over = now >= v["end"]
        out = {"id": v["id"], "char": v["char"], "slots": v["slots"], "camp": v["camp"], "hours": v["hours"],
               "start": v["start"], "end": v["end"], "planned": plan["end"], "recalled": bool(v.get("recalled")),
               "over": over, "applied": bool(v.get("applied")), "seen": bool(v.get("seen")),
               "party": plan["party"], "mates": plan["mates"], "solo": plan["solo"],
               "events": [e for e in plan["events"] if e["t"] <= cut] + [{"t": cut, "k": "home"}] if v.get("recalled") else plan["events"],
               "results": V.results(plan, cut)}
        if over:
            out["story"] = V.story(plan, cut if v.get("recalled") else None)
        return out

    def phone(self, owner, camps=False):
        now = self.now()
        with self.lock:
            roster = [dict(ch, mates=self._effective(owner, ch, now)) for ch in (self.state["roster"].get(owner) or {}).values()]
            vs = [self._public(v, now) for v in self.state["list"].get(owner, [])]
        out = {"now": int(now), "roster": roster, "ventures": [v for v in vs if v], "hours": list(V.HOURS),
               "expPerHour": V.EXP_PER_HOUR, "partyFrom": V.PARTY_FROM}
        if camps:
            out["camps"] = V.camp_list()
        return out

    def start(self, owner, body):
        vid = str(body.get("id", ""))
        if not ID_RE.match(vid):
            return {"error": "bad venture id"}
        hours = _num(body.get("hours"), 0, 99)
        if hours not in V.HOURS:
            return {"error": "Pick 1, 2, 4, 8 or 12 hours."}
        camp = V.data()["by_id"].get(str(body.get("camp", "")))
        if not camp:
            return {"error": "That camp doesn't exist."}
        now = self.now()
        with self.lock:
            lst = self.state["list"].setdefault(owner, [])
            if any(v["id"] == vid for v in lst):
                return {"ok": True, "again": True}
            ch = (self.state["roster"].get(owner) or {}).get(str(body.get("char", "")).lower())
            if not ch:
                return {"error": "That character's squad isn't known yet. Press PLAY (or SYNC NOW) in the launcher once."}
            want = []
            for s in (body.get("slots") or [])[:6]:
                s = _num(s, 0, 31, -1)
                if s not in want:
                    want.append(s)
            mates = [m for m in self._effective(owner, ch, now) if m["slot"] in want]
            if not mates or len(mates) != len(want):
                return {"error": "Pick one or more of this character's squad mates."}
            out_now = {s for v in lst if v["char"].lower() == ch["name"].lower() and now < v["end"] for s in v["slots"]}
            busy = [m["name"] for m in mates if m["slot"] in out_now]
            if busy:
                return {"error": f"{', '.join(busy)} {'is' if len(busy) == 1 else 'are'} already out on a venture."}
            if sum(1 for v in lst if now < v["end"]) >= MAX_OUT:
                return {"error": "Too many ventures out at once."}
            low = min(m["level"] for m in mates)
            if not (camp["lo"] - 3 <= low <= camp["hi"] + 3):
                return {"error": f"{camp['title']} ({camp['spot']}) is for levels {camp['lo']}-{camp['hi']}."}
            plan = V.simulate(vid, camp["id"], mates, hours, now, ch.get("bots"))
            self._write(os.path.join(self.folder, "plans", vid + ".json"), plan)
            lst.append({"id": vid, "char": ch["name"], "slots": [m["slot"] for m in mates], "camp": camp["id"],
                        "campTitle": f"{camp['title']} ({camp['spot']})", "hours": hours, "start": int(now),
                        "end": plan["end"]})
            # keep the album small: the oldest finished-and-applied ventures of this character go first
            mine = [v for v in lst if v["char"] == ch["name"] and v.get("applied") and now >= v["end"]]
            for v in sorted(mine, key=lambda v: v["end"])[:-KEEP_DONE] if len(mine) > KEEP_DONE else []:
                lst.remove(v)
                try:
                    os.remove(os.path.join(self.folder, "plans", v["id"] + ".json"))
                except OSError:
                    pass
            self.save()
            return {"ok": True, "venture": self._public(lst[-1], now)}

    def recall(self, owner, vid):
        now = self.now()
        with self.lock:
            for v in self.state["list"].get(owner, []):
                if v["id"] == str(vid):
                    if now >= v["end"]:
                        return {"ok": True, "again": True}
                    v["end"], v["recalled"] = int(now), True
                    self.save()
                    return {"ok": True, "venture": self._public(v, now)}
        return {"error": "No such venture."}

    def seen(self, owner, vid):
        with self.lock:
            for v in self.state["list"].get(owner, []):
                if v["id"] == str(vid):
                    v["seen"] = True
                    self.save()
                    return {"ok": True}
        return {"error": "No such venture."}
