"""Ventures: squad mates sent off to level at a real exp camp, from the XIFO app (phone, PC app or xiforever.com/app)
or, since 2026-11-26, from the game itself (the /venture window, addons-src/venture). No GUI here, so it can be tested
on its own.

WHO PLANS A VENTURE. The hub (dev/armory/ventures_hub.py) when an app is paired and the hub can be reached: then the
app and the game show the same ventures. Otherwise this launcher, with the very same code (it loads
dev/armory/ventures_hub.py and ventures.py from the kit; its files are <kit>/ventures/state.json and plans/): that is
how Ventures work with no internet and with no app at all. The timer needs nothing running: the whole venture is worked
out when the mates leave, and only the clock decides how far along it is.

This launcher side:
  * ROSTER: each home character's squad (slot, looks, job, level, progress in the level) and a few of the world's bot
    players (they turn up in the parties). To the hub at PLAY and every 10 minutes (only when an app is paired); to its
    own planner every minute.
  * THE RELAY (a thread while the game runs) talks to the game through three files in <kit>/ventures/
    (squad_ventures.lua reads and writes them):
      away.txt   char|slot|end time|camp      mates out now: the game won't call them (and sends home any that are out)
      in.txt     id|char|gil|camp|slot:exp,...  a venture that is over: the game gives the exp to each mate and the gil
      out.txt    id|ok                          written by the game once it has done that
    Then the relay puts the items in the character's delivery box (sender "Venture"), and tells whoever planned the
    venture, so nothing is ever handed out twice.
  * THE WINDOW in game talks to the relay through <Ashita>/config/addons/venture/:
      state.lua      written here when something changed: the squads, every venture (without its timeline), answers
      v/<id>.lua     one venture's timeline (the window loads it when it draws that venture)
      camps.lua      the camps (this kit's, and the hub's when they differ)
      alive.txt      the time, every few seconds: the launcher is running
      req/<id>.txt   written by the window: char|start|id|slots|camp|hours, char|recall|venture, char|seen|venture,
                     char|open (the window is showing: keep the picture fresh)

Command line:  python launcher_ventures.py roster     (the launcher runs it at PLAY; only when an app is paired)
"""
import importlib.util
import json
import os
import random
import re
import sys
import threading
import time

import launcher_armory as A

HERE = os.path.dirname(os.path.abspath(__file__))
SENDER = "Venture"
ROSTER_EVERY = 600                 # the squads to the hub
LOCAL_ROSTER_EVERY = 60            # the squads to this launcher's own planner
LOOK_EVERY = 30                    # who is away, what came home
WATCH_EVERY = 10                   # the same while the in-game window is showing
WATCH_FOR = 60                     # how long one "open" from the window counts
TICK = 1                           # how often the window's requests are read
STATE_EVERY = 300                  # the hub's full list at least this often (it is asked sooner when something changed)
KEEP_PAST = 20                     # finished ventures a character keeps in the window's album
HUB_RETRY = 45                     # after the hub could not be reached: leave it alone this long
ALIVE_EVERY = 5                    # the window is told this often that the launcher is running
LOCAL = "local"                    # the owner name this launcher's own planner files things under
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")      # a request's name (the file's name) and a venture's id


def folder(kit=HERE):
    path = os.path.join(kit, "ventures")
    os.makedirs(path, exist_ok=True)
    return path


# ----------------------------------------------------------------------------------------------- this launcher's own planner
_ENGINE = {}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def engine_module(kit=HERE):
    """The hub's Ventures code, loaded from the kit (dev/armory): the planner and its file store. None when this kit
    does not have it (then ventures can only be planned by the hub)."""
    for base in (kit, HERE):
        folder_ = os.path.join(base, "dev", "armory")
        if folder_ in _ENGINE:
            return _ENGINE[folder_]
        if not all(os.path.exists(os.path.join(folder_, n)) for n in ("ventures.py", "ventures_hub.py", "venture_data.json")):
            continue
        try:
            sim = sys.modules.get("ventures")
            if sim is None or not hasattr(sim, "simulate"):
                _load("ventures", os.path.join(folder_, "ventures.py"))      # (ventures_hub imports it by this name)
            hub = sys.modules.get("ventures_hub")
            if hub is None or not hasattr(hub, "Ventures"):
                hub = _load("ventures_hub", os.path.join(folder_, "ventures_hub.py"))
            _ENGINE[folder_] = hub
            return hub
        except Exception:
            _ENGINE[folder_] = None
    return None


def local_engine(kit=HERE, clock=time.time):
    """This launcher's own planner: the hub's Ventures class over <kit>/ventures (state.json, plans/). None without it."""
    mod = engine_module(kit)
    if mod is None:
        return None
    try:
        return mod.Ventures(kit, threading.RLock(), now=clock)
    except ValueError:                       # its list can't be read (a PC that lost power while it was written):
        path = os.path.join(kit, "ventures", "state.json")       # put it aside and start a new one
        os.replace(path, path + ".broken")
        return mod.Ventures(kit, threading.RLock(), now=clock)


def cancel_local(engine, vid):
    """Takes a venture off this launcher's own list as if it had never left (the rule when the app had sent the same
    mate first)."""
    with engine.lock:
        lst = engine.state["list"].get(LOCAL, [])
        for v in list(lst):
            if v["id"] == vid:
                lst.remove(v)
                try:
                    os.remove(os.path.join(engine.folder, "plans", vid + ".json"))
                except OSError:
                    pass
        engine.save()


# ----------------------------------------------------------------------------------------------- the in-game window's files
def ui_folder(cfg):
    """<Ashita>/config/addons/venture, where the window's add-on can find it. None when Ashita's folder is not known."""
    base = (cfg or {}).get("ashita_dir")
    if not base or not os.path.isdir(base):
        return None
    path = os.path.join(base, "config", "addons", "venture")
    try:
        os.makedirs(os.path.join(path, "req"), exist_ok=True)
        os.makedirs(os.path.join(path, "v"), exist_ok=True)
    except OSError:
        return None
    return path


def lua(value):
    """A value as Lua source (the window loads state.lua with loadfile: no JSON reader needed in game). Every key is
    written as a string, so "end" and the like are safe. Text outside ASCII goes in as byte escapes."""
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if value == value and abs(value) != float("inf") else "0"
    if isinstance(value, str):
        out = []
        for byte in value.encode("utf-8"):
            ch = chr(byte)
            if ch == "\\" or ch == '"':
                out.append("\\" + ch)
            elif 32 <= byte < 127:
                out.append(ch)
            else:
                out.append("\\%03d" % byte)
        return '"' + "".join(out) + '"'
    if isinstance(value, dict):
        return "{" + ",".join("[%s]=%s" % (lua(str(k)), lua(v)) for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "{" + ",".join(lua(v) for v in value) + "}"
    return "nil"


def _replace(tmp, path):
    """os.replace that waits out the moment the game has the file open (Windows refuses meanwhile)."""
    for _ in range(40):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.05)
    return False


def write_state(folder_, state):
    """state.lua. Its first line is all the window reads to know whether anything is new."""
    return write_lua(os.path.join(folder_, "state.lua"), state, "-- seq %d at %d\n" % (int(state.get("seq", 0)), int(state.get("at", 0))))


def write_lua(path, value, head=""):
    """One Lua file the window loads (`return <value>`), swapped in whole."""
    with open(path + ".part", "w", encoding="ascii", newline="\n") as f:
        f.write(head + "return " + lua(value) + "\n")
    return _replace(path + ".part", path)


def read_requests(folder_, now=None, max_age=120):
    """The window's requests, oldest first, each taken off the disk: [(id, [fields])]. One that sat there for minutes
    (the launcher was closed) is dropped: the window has long given up on it."""
    now = time.time() if now is None else now
    base = os.path.join(folder_, "req")
    out = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".txt"):
            continue
        path = os.path.join(base, name)
        try:
            age = now - os.path.getmtime(path)
            with open(path, encoding="utf-8", errors="replace") as f:
                line = f.readline().strip()
            os.remove(path)
        except OSError:
            continue
        rid = name[:-4]
        if ID_RE.match(rid) and line and age <= max_age:
            out.append((rid, line.split("|")))
    return out


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
    """While the game runs: who is away, what came home, and what the in-game window asks for. One thread.
    Two planners can be at work: the hub (when an app is paired) and this launcher's own."""

    def __init__(self, cfg, kit=HERE, log=None, caller=None, connector=None, clock=time.time, engine="auto", ui="auto"):
        self.cfg, self.kit = cfg, kit
        self.log = log or (lambda text: None)
        self.call = caller or (lambda path, body=None: A.call(A.load(kit), path, body, timeout=10))
        self.connect = connector or (lambda: A.connect(cfg))
        self.now = clock
        self.local = engine
        if engine == "auto":
            try:
                self.local = local_engine(kit, clock)
            except Exception as e:           # (the hub's ventures must go on whatever happens here)
                self.local = None
                self.log(f"Ventures: this PC's own planner did not start ({e}); ventures can still be sent from the XIFO app.")
        self.ui = ui_folder(cfg) if ui == "auto" else ui
        self.stop_flag = threading.Event()
        self.roster_at = 0                 # the squads last went to the hub
        self.local_roster_at = 0           # ... and to this launcher's own planner
        self.local_roster_key = None
        self.look_at = 0
        self.alive_at = 0
        self.watch_until = 0               # the in-game window is showing until then
        self.hub_ok = False                # the last talk with the hub worked
        self.hub_down_until = 0            # ... and when it did not: no new try before this
        self.hub_game = None               # the hub knows the in-game window's requests (None: not asked yet)
        self.hub_probe_at = 0              # when an older hub was last asked whether it has learned them
        self.hub_state = None              # the hub's full list (what the phone sees), and when it was fetched
        self.hub_state_at = 0
        self.hub_mark = None               # what the hub's short list looked like at that time
        self.hub_camps = None              # the hub's camps (asked for once)
        self.hub_skew = 0                  # hub clock minus this PC's
        self.hub_bare = []                 # mates the hub has out (hub time), kept for when it can't be asked
        self.replies = {}                  # answers to the window's requests (the last few)
        self.seq = 0
        self.last_state = None
        self.camps_key, self.camps_seq = None, 0
        self.ev_written = {}               # venture id -> the stamp of its timeline file
        self.said = {}                     # the same trouble is logged once in ten minutes, not at every look
        try:
            st = self.state()
            self.hub_bare = list(st.get("hubAway") or [])
            self.hub_skew = int(st.get("hubSkew") or 0)
        except Exception:
            pass

    # ---------------------------------------------------------------- what this launcher remembers
    def state(self):
        return A.load(self.kit).get("ventures") or {"handed": {}, "delivered": []}

    def save_state(self, st):
        data = A.load(self.kit)
        data["ventures"] = st
        A.save(data, self.kit)

    def paired(self):
        return bool(A.load(self.kit).get("paired"))

    def trouble(self, text):
        if self.now() - self.said.get(text, -1e9) > 600:
            self.said[text] = self.now()
            self.log(text)

    # ---------------------------------------------------------------- the squads
    def _roster(self):
        conn = self.connect()
        try:
            return build_roster(conn)
        finally:
            conn.close()

    def refresh_rosters(self, force=False, hub=True):
        """The squads: to this launcher's own planner (every minute, or now), and to the hub when an app is paired
        (every ten minutes; `force` brings that forward to once a minute, `hub=False` leaves the hub's turn alone)."""
        now = self.now()
        body = None
        if self.local is not None and (force or now - self.local_roster_at > LOCAL_ROSTER_EVERY):
            try:
                body = self._roster()
                key = json.dumps([[ch.get("name"), ch.get("mates")] for ch in body.get("chars") or []], sort_keys=True)
                if key != self.local_roster_key:          # (unchanged squads are not written again)
                    self.local.roster(LOCAL, body)
                    self.local_roster_key = key
                self.local_roster_at = now
            except Exception as e:
                self.trouble(f"Ventures: could not read the squads ({e}).")
        if self.paired() and (now - self.roster_at > ROSTER_EVERY or (force and hub and now - self.roster_at > 60)):
            try:
                out = self._hub("/armory/api/ventures/roster", body or self._roster())
                if out is not None and not out.get("error"):
                    self.roster_at = now
            except Exception as e:
                self.trouble(f"Ventures: could not send the squads ({e}).")

    # ---------------------------------------------------------------- the hub
    def _hub(self, path, body=None):
        """One talk with the hub. Returns its answer, or None when it could not be reached (or is broken: a 5xx)."""
        now = self.now()
        if now < self.hub_down_until:
            return None
        try:
            out = self.call(path, body)
            if not isinstance(out, dict):
                out = {}
            if re.fullmatch(r"the armory answered 5\d\d", str(out.get("error", ""))):
                raise OSError(out["error"])
        except Exception:
            self.hub_ok = False
            self.hub_down_until = now + HUB_RETRY
            return None
        self.hub_ok = True
        return out

    def _hub_away(self, now):
        return [a for a in self.hub_bare if a.get("end", 0) > now + self.hub_skew]

    def hub_look(self):
        """Who the hub has out and what came home there; and, when something changed, its full list for the window."""
        if not self.paired():
            self.hub_ok, self.hub_state, self.hub_bare, self.hub_mark = False, None, [], None
            return {}
        out = self._hub("/armory/api/ventures/launcher")
        now = self.now()
        if out is None or out.get("error"):
            # the hub can't be asked right now: the mates it had out stay out until their time is up
            return {"away": self._hub_away(now), "done": []}
        if out.get("now"):
            self.hub_skew = int(out["now"]) - int(now)
        mark = (sorted((a.get("id", ""), a["char"], a["slot"], a["end"]) for a in out.get("away") or []),
                sorted(v["id"] for v in out.get("done") or []))
        self.hub_bare = out.get("away") or []
        # (the full list can be big: fetched when the short one changed, and now and then for what the app changed)
        want = self.hub_state is None or mark != self.hub_mark or now - self.hub_state_at > STATE_EVERY
        if self.hub_game is False and now - self.hub_probe_at > 1800:
            self.hub_game = None                                       # an older hub may have been updated meanwhile
        if self.hub_game is not False and want:
            self.hub_probe_at = now
            full = self._hub("/armory/api/ventures/game" + ("?camps=1" if self.hub_camps is None else ""))
            if full is not None:
                if isinstance(full.get("ventures"), list):
                    if isinstance(full.get("camps"), list):
                        self.hub_camps = full.pop("camps")
                    self.hub_game, self.hub_state, self.hub_state_at, self.hub_mark = True, full, now, mark
                elif self.hub_game is None and "404" in str(full.get("error", "")):
                    self.hub_game = False                              # an older hub: it has no such page
        return out

    # ---------------------------------------------------------------- one look
    def look(self):
        self.look_at = self.now()
        self.refresh_rosters()
        hub = self.hub_look()
        local = self.local.launcher(LOCAL) if self.local is not None else {}
        if self._settle_doubles(hub, local):
            hub = dict(hub, away=[a for a in hub.get("away") or [] if a.get("id") not in self._recalled])
            local = self.local.launcher(LOCAL)
        base = folder(self.kit)
        # (the hub's times are by its clock: the game goes by this PC's)
        away = [dict(a, end=int(a["end"]) - self.hub_skew) for a in hub.get("away") or []] + (local.get("away") or [])
        write_away(os.path.join(base, "away.txt"), away)
        done = [dict(v, src="hub") for v in hub.get("done") or []] + [dict(v, src=LOCAL) for v in local.get("done") or []]
        st = self.state()
        before = json.dumps(st, sort_keys=True)
        handed, delivered = st.setdefault("handed", {}), st.setdefault("delivered", [])
        new = [v for v in done if v["id"] not in handed and v["id"] not in delivered]
        again = [v for v in done if v["id"] in delivered]            # (whoever planned it missed our "applied")
        if new:
            with open(os.path.join(base, "in.txt"), "a", encoding="utf-8", newline="\n") as f:
                for v in new:
                    f.write(in_line(v))
                    handed[v["id"]] = {"char": v["char"], "items": v.get("items") or [], "camp": v.get("camp", ""), "src": v["src"]}
        applied = read_out(os.path.join(base, "out.txt"))
        finished = {"hub": [], LOCAL: []}
        for vid, v in list(handed.items()):
            if vid in applied:
                conn = self.connect()
                try:
                    deliver(conn, v["char"], v["items"])
                finally:
                    conn.close()
                finished[v.get("src", "hub")].append(vid)
                delivered.append(vid)
                del handed[vid]
                if v["items"]:
                    self.log(f"Ventures: {v['char']}'s squad brought home {sum(c for _, c in v['items'])} item(s) - "
                             "they are in the delivery box.")
        for v in again:
            finished[v["src"]].append(v["id"])
        if not handed:                                              # everything taken in: start in.txt afresh
            try:
                if os.path.getsize(os.path.join(base, "in.txt")) > 0:
                    open(os.path.join(base, "in.txt"), "w").close()
            except OSError:
                pass
        st["delivered"] = delivered[-500:]
        st["hubAway"] = self._hub_away(self.now()) if self.paired() else []
        if abs(int(st.get("hubSkew") or 0) - self.hub_skew) > 5:
            st["hubSkew"] = self.hub_skew
        if json.dumps(st, sort_keys=True) != before:               # (armory.json is the launcher's too: no needless writes)
            self.save_state(st)
        if finished["hub"]:
            self._hub("/armory/api/ventures/applied", {"ids": finished["hub"]})
        if finished[LOCAL] and self.local is not None:
            self.local.applied(LOCAL, finished[LOCAL])
        self.publish()

    def _settle_doubles(self, hub, local):
        """The same mate out twice (sent in game while the hub could not be reached, and from the app): the venture
        that left first counts. The later one is taken back: this launcher's own as if it had never left, the hub's
        called home at once. Returns True when something was taken back."""
        self._recalled = set()
        if self.local is None or not (hub.get("away") and local.get("away")):
            return False
        starts = {v["id"]: v["start"] - self.hub_skew for v in ((self.hub_state or {}).get("ventures") or [])}
        mine = {v["id"]: v for v in self.local.state["list"].get(LOCAL, [])}
        theirs = {(a["char"].lower(), int(a["slot"])): a for a in hub["away"]}
        gone = set()
        for a in local["away"]:
            other = theirs.get((a["char"].lower(), int(a["slot"])))
            if other is None or a["id"] in gone or other.get("id") in gone:
                continue
            hub_start = starts.get(other.get("id"))
            if hub_start is None or hub_start <= mine[a["id"]]["start"] or not self.hub_game:
                cancel_local(self.local, a["id"])
                gone.add(a["id"])
                self.log(f"Ventures: {a['char']}'s venture sent in game was taken back - the app had sent the same squad mate first.")
            else:
                out = self._hub("/armory/api/ventures/game/recall", {"id": other["id"]})
                if out is not None and out.get("ok"):
                    gone.add(other["id"])
                    self._recalled.add(other["id"])
                    self.hub_mark = None                               # (the hub's list changed: fetch it again)
                    self.log(f"Ventures: a venture sent from the app was called home - {a['char']}'s squad mate was "
                             "already out, sent in game.")
        return bool(gone)

    # ---------------------------------------------------------------- the in-game window
    def use_hub(self):
        """A venture sent in game goes to the hub (so the app shows it too) when an app is paired, the hub answers and
        knows how; otherwise this launcher plans it."""
        return self.paired() and self.hub_ok and self.hub_game is True

    def _full_ventures(self):
        """Every venture as its planner tells it (the hub's, then this launcher's own), newest facts."""
        out, ids = [], set()
        if self.paired() and self.hub_state:
            for v in self.hub_state.get("ventures") or []:
                out.append(dict(v, src="hub", skew=self.hub_skew))
                ids.add(v["id"])
        elif self.paired():
            byid = {}
            for a in self._hub_away(self.now()):                     # an older hub: who is out, without the timeline
                vid = a.get("id") or f"{a['char']}-{a['end']}"
                v = byid.setdefault(vid, {"id": vid, "char": a["char"], "slots": [], "campTitle": a.get("camp", ""),
                                          "end": a["end"], "src": "hub", "skew": self.hub_skew, "bare": True})
                v["slots"].append(a["slot"])
            out.extend(byid.values())
        if self.local is not None:
            for v in self.local.phone(LOCAL).get("ventures") or []:
                if v["id"] not in ids:
                    out.append(dict(v, src=LOCAL, skew=0))
        return out

    def _ventures(self):
        """The ventures the window shows: all that are out or not read yet, and each character's last few."""
        now = self.now()
        keep, past = [], {}
        for v in self._full_ventures():
            if v.get("bare") or now + v["skew"] < v["end"] or not v.get("seen"):
                keep.append(v)
            else:
                past.setdefault(v["char"].lower(), []).append(v)
        for lst in past.values():
            keep.extend(sorted(lst, key=lambda v: -v["end"])[:KEEP_PAST])
        return keep

    def _camps(self):
        mod = engine_module(self.kit)
        V = sys.modules.get("ventures") if mod is not None else None
        mine = V.camp_list() if V is not None else None
        theirs = self.hub_camps if (self.hub_camps and self.hub_camps != mine) else None
        return {"local": mine or theirs or [], "hub": theirs}

    def _roster_view(self):
        """The squads as they stand: this launcher's own reading (fresh), moved on by what either planner knows of
        ventures that are over but not in the game yet."""
        mine = self.local.phone(LOCAL).get("roster") if self.local is not None else None
        theirs = (self.hub_state or {}).get("roster") if self.paired() else None
        base = mine or theirs or []
        other = {ch["name"].lower(): {m["slot"]: m for m in ch.get("mates") or []} for ch in (theirs if mine else None) or []}
        out = []
        for ch in base:
            mates = []
            for m in ch.get("mates") or []:
                m = dict(m)
                o = other.get(ch["name"].lower(), {}).get(m["slot"])
                if o and o.get("job") == m.get("job") and (o["level"], o.get("exp", 0)) > (m["level"], m.get("exp", 0)):
                    m["level"], m["exp"] = o["level"], o.get("exp", 0)
                mates.append(m)
            out.append({"name": ch["name"], "mates": mates})
        return out

    def ui_state(self):
        mod = engine_module(self.kit)
        V = sys.modules.get("ventures") if mod is not None else None
        use_hub = self.use_hub()
        base = (self.hub_state if use_hub else None) or {}
        ventures = []
        for v in self._ventures():
            v = dict(v)
            if not v.get("bare"):
                events = v.pop("events", None) or []
                v["ev"] = f"{len(events)}-{v['end']}"
                if not v.get("over"):
                    v.pop("results", None)                           # (what they have so far the window works out itself)
            ventures.append(v)
        return {"v": 1, "paired": self.paired(), "online": bool(self.hub_ok), "hub": use_hub,
                "canSend": bool(use_hub or self.local is not None),
                "hours": list(base.get("hours") or (V.HOURS if V is not None else (1, 2, 4, 8, 12))),
                "expPerHour": int(base.get("expPerHour") or (V.EXP_PER_HOUR if V is not None else 3000)),
                "partyFrom": int(base.get("partyFrom") or (V.PARTY_FROM if V is not None else 10)),
                "campsSeq": self.camps_seq, "roster": self._roster_view(), "ventures": ventures, "replies": dict(self.replies)}

    def _write_timelines(self):
        """v/<id>.lua for every venture the window can show (written once; again when one is called home early), and
        the files of ventures that are gone removed."""
        base = os.path.join(self.ui, "v")
        ids = set()
        for v in self._ventures():
            if v.get("bare"):
                continue
            ids.add(v["id"])
            events = v.get("events") or []
            stamp = f"{len(events)}-{v['end']}"
            if self.ev_written.get(v["id"]) != stamp and write_lua(os.path.join(base, v["id"] + ".lua"), events):
                self.ev_written[v["id"]] = stamp
        try:
            for name in os.listdir(base):
                if name.endswith(".lua") and name[:-4] not in ids:
                    os.remove(os.path.join(base, name))
                    self.ev_written.pop(name[:-4], None)
        except OSError:
            pass

    def publish(self, force=False):
        """Tells the window: the camps (when they changed), each venture's timeline, then state.lua (when what it
        shows has changed)."""
        if self.ui is None:
            return
        try:
            camps = self._camps()
            key = json.dumps(camps, sort_keys=True)
            if key != self.camps_key and write_lua(os.path.join(self.ui, "camps.lua"), camps):
                self.camps_key, self.camps_seq = key, self.camps_seq + 1
            self._write_timelines()
            st = self.ui_state()
            key = json.dumps(st, sort_keys=True, default=str)
            if not force and key == self.last_state:
                return
            self.seq += 1
            st["seq"], st["at"] = self.seq, int(self.now())
            if write_state(self.ui, st):
                self.last_state = key
        except Exception as e:
            self.trouble(f"Ventures: the in-game window was not told ({e}).")

    def alive(self):
        """A few bytes every few seconds: the window sees that the launcher is running."""
        if self.ui is None or self.now() - self.alive_at < ALIVE_EVERY:
            return
        self.alive_at = self.now()
        try:
            path = os.path.join(self.ui, "alive.txt")
            with open(path + ".part", "w", encoding="ascii") as f:
                f.write(str(int(self.now())))
            _replace(path + ".part", path)
        except OSError:
            pass

    def _busy_elsewhere(self, char, slots, at_hub):
        """Mates of this request that the other planner has out (their names, for the answer)."""
        now = self.now()
        if at_hub:
            other = [dict(v, skew=0) for v in (self.local.phone(LOCAL).get("ventures") or [])] if self.local is not None else []
        else:
            other = [v for v in self._full_ventures() if v.get("src") == "hub"]
        roster = {ch["name"].lower(): {m["slot"]: m["name"] for m in ch["mates"]} for ch in self._roster_view()}
        busy = []
        for v in other:
            if v["char"].lower() == char.lower() and now + v.get("skew", 0) < v["end"]:
                for slot in v.get("slots") or []:
                    if slot in slots:
                        busy.append(roster.get(char.lower(), {}).get(slot) or f"slot {slot}")
        return busy

    def handle(self, rid, fields):
        """One request from the window: [char, what, ...]. Returns the answer the window gets (None: no answer due)."""
        if len(fields) < 2:
            return {"error": "The launcher did not understand that."}
        char, what = fields[0], fields[1]
        if what == "open":
            self.watch_until = self.now() + WATCH_FOR
            self.refresh_rosters(force=True, hub=False)
            return None
        if what == "start":
            if len(fields) < 6 or not ID_RE.match(fields[2]):
                return {"error": "The launcher did not understand that."}
            try:
                slots = [int(x) for x in fields[3].split(",") if x != ""]
                hours = int(fields[5])
            except ValueError:
                return {"error": "The launcher did not understand that."}
            body = {"id": fields[2], "char": char, "slots": slots, "camp": fields[4], "hours": hours}
            self.refresh_rosters(force=True)
            at_hub = self.use_hub()
            busy = self._busy_elsewhere(char, slots, at_hub)
            if busy:
                return {"error": f"{', '.join(busy)} {'is' if len(busy) == 1 else 'are'} already out on a venture."}
            if at_hub:
                out = self._hub("/armory/api/ventures/game/start", body)
                if out is not None:
                    self.hub_mark = None                               # (fetch the hub's list again right away)
                    return {"ok": True} if out.get("ok") else {"error": out.get("error") or "The hub refused that."}
            if self.local is None:
                return {"error": "The hub can't be reached right now. Try again in a moment." if self.paired()
                        else "Ventures can't be planned on this PC (the kit's dev\\armory folder is missing)."}
            out = self.local.start(LOCAL, body)
            if out.get("ok"):
                note = ""
                if self.paired():                                      # (an app is paired, and still it is planned here)
                    note = ("The hub does not take ventures from the game yet" if self.hub_ok and self.hub_game is False
                            else "The hub can't be reached") + ", so this venture stays on this PC (the app won't show it)."
                return {"ok": True, "note": note}
            return {"error": out.get("error") or "That did not work."}
        if what in ("recall", "seen"):
            vid = fields[2] if len(fields) > 2 else ""
            if self.local is not None and any(v["id"] == vid for v in self.local.state["list"].get(LOCAL, [])):
                out = self.local.recall(LOCAL, vid) if what == "recall" else self.local.seen(LOCAL, vid)
            elif self.paired() and self.hub_game:
                out = self._hub(f"/armory/api/ventures/game/{what}", {"id": vid})
                if out is None:
                    return {"error": "The hub can't be reached right now. Try again in a moment."}
                self.hub_mark = None
            else:
                return {"error": "That venture was sent from the app: call it home there."}
            return {"ok": True} if out.get("ok") else {"error": out.get("error") or "That did not work."}
        return {"error": "The launcher did not understand that."}

    def tick(self):
        """Reads the window's requests. Returns True when a look is due right now."""
        if self.ui is None:
            return False
        self.alive()
        did = False
        for rid, fields in read_requests(self.ui, self.now()):
            try:
                answer = self.handle(rid, fields)
            except Exception as e:
                answer = {"error": f"The launcher ran into a problem ({e})."}
            if answer is not None:
                self.replies[rid] = answer
                for old in list(self.replies)[:-20]:
                    del self.replies[old]
            did = True
        return did

    def due(self):
        every = WATCH_EVERY if self.now() < self.watch_until else LOOK_EVERY
        return self.now() - self.look_at >= every

    def run(self):
        while not self.stop_flag.is_set():
            try:
                if self.tick() or self.due():
                    self.look()
            except Exception as e:
                self.trouble(f"Ventures: {e}")
            self.stop_flag.wait(TICK)

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
