"""Ventures (2026-11-25): squad mates sent off from the XIFO app (phone, PC app or xiforever.com/app) to level at a real
exp camp. No GUI here, so it can be tested on its own.

The hub (dev/armory/ventures_hub.py) plans each venture. This launcher side:
  * ROSTER: tells the hub each home character's squad (slot, looks, job, level, progress in the level) and a few of the
    world's bot players (they turn up in the parties). At PLAY, then every 10 minutes while playing.
  * THE RELAY (a thread while the game runs, a look every 30 seconds) talks to the game through three files in
    <kit>/ventures/ (squad_ventures.lua reads and writes them):
      away.txt   char|slot|end time|camp      mates out now: the game won't call them (and sends home any that are out)
      in.txt     id|char|gil|camp|slot:exp,...  a venture that is over: the game gives the exp to each mate and the gil
      out.txt    id|ok                          written by the game once it has done that
    Then the relay puts the items in the character's delivery box (sender "Venture"), and tells the hub, so nothing
    is ever handed out twice.

Command line:  python launcher_ventures.py roster     (the launcher runs it at PLAY; only when an app is paired)
"""
import json
import os
import random
import sys
import threading
import time

import launcher_armory as A

HERE = os.path.dirname(os.path.abspath(__file__))
SENDER = "Venture"
ROSTER_EVERY = 600
LOOK_EVERY = 30


def folder(kit=HERE):
    path = os.path.join(kit, "ventures")
    os.makedirs(path, exist_ok=True)
    return path


# ----------------------------------------------------------------------------------------------- roster
RANGED_JOBS = {11: (25, 26), 17: (25, 26), 10: (41, 42)}     # RNG, COR: the bow or gun; BRD: the instrument


def _weapon_skill(cur, squad_id, job):
    """(2026-11-25) The weapon skill of what this mate holds for the app's Ventures picture: the main hand
    (item_weapon.skill), or for a Ranger, Corsair or Bard what's in the ranged slot. 0 = unknown (the job's usual)."""
    try:
        rows = dict(A._all(cur, "SELECT e.slot, w.skill FROM squad_equip e JOIN item_weapon w ON w.itemId = e.itemid "
                                "WHERE e.squad_id = ? AND e.job = ? AND e.slot IN (0, 2)", (squad_id, job)))
    except Exception:
        return 0
    ranged = int(rows.get(2) or 0)
    if ranged and ranged in RANGED_JOBS.get(job, ()):
        return ranged
    return int(rows.get(0) or 0)


def build_roster(conn):
    cur = conn.cursor()
    try:
        chars = []
        for charid, name in A.home_characters(conn):
            mates = []
            # (2026-11-25) a Randomized character's random squad: the mates look like Fate rolled them ([HC]RSLook<id>)
            rs = {}
            try:
                rs = dict(A._all(cur, "SELECT varname, value FROM char_vars WHERE charid = ? AND varname LIKE ?", (charid, "[HC]RS%")))
            except Exception:
                rs = {}
            random_squad = int(rs.get("[HC]RSquad", 0) or 0) == 1
            if A._has(cur, "squad_mate"):
                for mid, slot, mname, race, face, mjob, sjob in A._all(
                        cur, "SELECT id, slot, name, race, face, mjob, sjob FROM squad_mate WHERE charid = ? ORDER BY slot", (charid,)):
                    row = A._one(cur, "SELECT level, exp FROM squad_job WHERE squad_id = ? AND job = ?", (mid, mjob))
                    weapon = _weapon_skill(cur, mid, int(mjob or 1))
                    look = int(rs.get(f"[HC]RSLook{mid}", 0) or 0) if random_squad else 0
                    if 1000 <= look < 9000:
                        race, face = look // 1000, (look // 10) % 100
                    mates.append({"slot": int(slot), "name": str(mname), "race": int(race or 1), "face": int(face or 0),
                                  "weapon": weapon, "job": int(mjob or 1), "sjob": int(sjob or 0), "level": int((row or [1, 0])[0] or 1),
                                  "exp": int((row or [1, 0])[1] or 0)})
            chars.append({"name": name, "mates": mates})
        bots = []
        try:
            rows = A._all(cur, "SELECT c.charname, l.race FROM chars c JOIN char_look l ON l.charid = c.charid "
                               "WHERE c.accid >= ? LIMIT 400", (A.BOT_ACCOUNT_BASE,))
            random.shuffle(rows)
            bots = [{"name": str(n), "race": int(r or 1)} for n, r in rows[:30]]
        except Exception:
            pass
        for ch in chars:
            ch["bots"] = bots
        return {"chars": chars}
    finally:
        cur.close()
        conn.rollback()


def send_roster(cfg, kit=HERE):
    data = A.load(kit)
    conn = A.connect(cfg)
    try:
        body = build_roster(conn)
    finally:
        conn.close()
    out = A.call(data, "/armory/api/ventures/roster", body)
    if out.get("error"):
        raise RuntimeError(out["error"])
    return sum(len(c["mates"]) for c in body["chars"])


# ----------------------------------------------------------------------------------------------- files
def write_away(path, away):
    lines = [f"{a['char']}|{int(a['slot'])}|{int(a['end'])}|{str(a.get('camp', '')).replace('|', ' ')}" for a in away]
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    os.replace(path + ".part", path)


def in_line(v):
    mates = ",".join(f"{int(m['slot'])}:{int(m['exp'])}" for m in v["mates"])
    return f"{v['id']}|{v['char']}|{int(v.get('gil', 0))}|{str(v.get('camp', '')).replace('|', ' ')}|{mates}\n"


def read_out(path):
    done = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 2 and parts[1] == "ok":
                    done.add(parts[0])
    except OSError:
        pass
    return done


def deliver(conn, char, items, log=print):
    """The venture's items into the character's delivery box, in stacks (like the phone's fishing catches)."""
    cur = conn.cursor()
    try:
        home = {n.lower(): cid for cid, n in A.home_characters(conn)}
        charid = home.get(str(char).lower())
        if not charid:
            return False
        stacks = {}
        for iid, count in items:
            if int(iid) and int(iid) != A.GIL:
                stacks[int(iid)] = stacks.get(int(iid), 0) + int(count)
        if stacks:
            marks = ",".join("?" * len(stacks))
            sizes = {int(r[0]): max(1, int(r[1])) for r in A._all(cur, f"SELECT itemid, stackSize FROM item_basic WHERE itemid IN ({marks})",
                                                                 list(stacks))}
            slot = int((A._one(cur, "SELECT IFNULL(MAX(slot) + 1, 8) FROM delivery_box WHERE charid = ? AND box = 1", (charid,)) or [8])[0])
            for iid, count in stacks.items():
                if iid not in sizes:
                    continue
                while count > 0:
                    q = min(count, sizes[iid])
                    cur.execute("INSERT INTO delivery_box (charid, charname, box, slot, itemid, itemsubid, quantity, senderid, sender) "
                                "VALUES (?, ?, 1, ?, ?, 0, ?, 0, ?)", (charid, str(char)[:15], slot, iid, q, SENDER))
                    slot += 1
                    count -= q
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ----------------------------------------------------------------------------------------------- the relay
class Relay:
    """While the game runs: who is away, what came home. One thread; quiet when no app is paired."""

    def __init__(self, cfg, kit=HERE, log=None, caller=None, connector=None):
        self.cfg, self.kit = cfg, kit
        self.log = log or (lambda text: None)
        self.call = caller or (lambda path, body=None: A.call(A.load(kit), path, body))
        self.connect = connector or (lambda: A.connect(cfg))
        self.stop_flag = threading.Event()
        self.roster_at = 0

    def state(self):
        return A.load(self.kit).get("ventures") or {"handed": {}, "delivered": []}

    def save_state(self, st):
        data = A.load(self.kit)
        data["ventures"] = st
        A.save(data, self.kit)

    def look(self):
        if not A.load(self.kit).get("paired"):
            return
        if time.time() - self.roster_at > ROSTER_EVERY:
            try:
                conn = self.connect()
                try:
                    self.call("/armory/api/ventures/roster", build_roster(conn))
                finally:
                    conn.close()
                self.roster_at = time.time()
            except Exception as e:
                self.log(f"Ventures: could not send the squads ({e}).")
        out = self.call("/armory/api/ventures/launcher")
        if out.get("error"):
            return
        base = folder(self.kit)
        write_away(os.path.join(base, "away.txt"), out.get("away") or [])
        st = self.state()
        handed, delivered = st.setdefault("handed", {}), st.setdefault("delivered", [])
        new = [v for v in out.get("done") or [] if v["id"] not in handed and v["id"] not in delivered]
        again = [v["id"] for v in out.get("done") or [] if v["id"] in delivered]     # (the hub missed our "applied")
        if new:
            with open(os.path.join(base, "in.txt"), "a", encoding="utf-8", newline="\n") as f:
                for v in new:
                    f.write(in_line(v))
                    handed[v["id"]] = {"char": v["char"], "items": v.get("items") or [], "camp": v.get("camp", "")}
        applied = read_out(os.path.join(base, "out.txt"))
        finished = []
        for vid, v in list(handed.items()):
            if vid in applied:
                conn = self.connect()
                try:
                    deliver(conn, v["char"], v["items"])
                finally:
                    conn.close()
                finished.append(vid)
                delivered.append(vid)
                del handed[vid]
                if v["items"]:
                    self.log(f"Ventures: {v['char']}'s squad brought home {sum(c for _, c in v['items'])} item(s) - "
                             "they are in the delivery box.")
        if not handed:                                              # everything taken in: start in.txt afresh
            try:
                open(os.path.join(base, "in.txt"), "w").close()
            except OSError:
                pass
        st["delivered"] = delivered[-500:]
        self.save_state(st)
        if finished or again:
            self.call("/armory/api/ventures/applied", {"ids": finished + again})

    def run(self):
        while not self.stop_flag.is_set():
            try:
                self.look()
            except Exception as e:
                self.log(f"Ventures: {e}")
            self.stop_flag.wait(LOOK_EVERY)

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="ventures").start()

    def stop(self):
        self.stop_flag.set()


def _main(argv):
    with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    if not A.load().get("paired"):
        return 0
    try:
        n = send_roster(cfg)
        print(f"ventures: {n} squad mate(s) ready for the app")
    except Exception as e:
        print(f"ventures: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
