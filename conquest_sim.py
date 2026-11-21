#!/usr/bin/env python3
"""Conquest simulator: lets the other nations and the beastmen act while you are away.

The game's conquest only moves when a player acts, and its weekly tally (Sunday 00:00 JST = Saturday 15:00 UTC) only happens if the
server is running at that moment. On a single-player server neither happens, so nothing ever changes. This tool runs when you press
PLAY (before the servers start) and catches the world up on the time you were away:

  * every 6 hours of away time, each nation gains influence in each region, the way other players would have,
    using the game's own catch-up rule (a nation behind the leader gains double, or triple if under half of the leader);
  * other players also kill monsters and set home points, which is what lets the beastmen take a region (the game's real formula);
  * at every Sunday tally that passed, region owners are decided with the game's own rule, last week's owner is remembered,
    and the counters reset, exactly like conquest_system.cpp does.

Modes:
  python conquest_sim.py tick [--dry-run]   catch up (the launcher runs this before starting the servers)
  python conquest_sim.py stamp              note that a play session has ended (the launcher runs this after the servers stop)
  python conquest_sim.py report             show the regions, owners and influence
  python conquest_sim.py restore FILE       put a saved backup of the table back

Settings are in conquest_sim.json next to this file (speed, randomness, own_nation_share, history_weeks, own_nation).
"""
import datetime
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "conquest_sim.json")
BACKUPS = os.path.join(HERE, "backups")

# ---------- time: tallies are every Saturday 15:00 UTC; a step is 6 hours, so every tally falls on a step boundary ----------
ANCHOR = 2 * 86400 + 15 * 3600       # Saturday 3 January 1970, 15:00 UTC (= Sunday 00:00 JST), in seconds since 1970
STEP = 6 * 3600
STEPS_PER_WEEK = 28

# ---------- the game's own numbers ----------
NEUTRAL, BEASTMEN = 5, 3
MAX_BEASTMEN = (2 ** 31 - 1) // 100
REGION_NAMES = ["Ronfaure", "Zulkheim", "Norvallen", "Gustaberg", "Derfland", "Sarutabaruta", "Kolshushu", "Aragoneu", "Fauregandi",
                "Valdeaunia", "Qufim Island", "Li'Telor", "Kuzotz", "Vollbow", "Elshimo Lowlands", "Elshimo Uplands", "Tu'Lia",
                "Movalpolos", "Tavnazian Archipelago"]
OWNER_NAMES = {0: "San d'Oria", 1: "Bastok", 2: "Windurst", 3: "Beastmen", 4: "Other", 5: "Neutral"}
# one home point is worth this many mob kills (conquest_data.h): general 10, semi-stronghold 25, stronghold 50
WEIGHT = {0: 10, 1: 10, 3: 10, 5: 10, 6: 10,
          8: 25, 10: 25, 11: 25, 12: 25, 13: 25, 14: 25, 15: 25, 16: 25, 18: 25,
          2: 50, 4: 50, 7: 50, 9: 50, 17: 50}

# ---------- how lively the imaginary population is (tuned so that regions flip but the world stays varied) ----------
RAW_WEEK = 4000.0              # exp-like activity per nation per region per week, before the game's /10 scaling
KILLS_WEEK = 75.0              # monster kills per region per week by other players
HOMEPOINTS_WEEK = {10: 1.7, 25: 1.0, 50: 0.45}
ALPHA = 0.70                   # how much of last week's player distribution carries over (higher = steadier)
SIGMA = 0.45                    # how far the distribution wanders each week
STEP_NOISE = 0.20              # randomness of each 6-hour step
GALPHA = 0.85                  # nations have good and bad stretches: how slowly their overall strength changes
GSIGMA = 0.40                  # and how big those swings are
INCUMBENT = 1.70               # the nation that holds a region defends it: its players put in this much more effort there
BACKLASH = 1.25                # a region the beastmen hold draws extra effort from every nation
# where each nation's imaginary players like to be (1.0 = no preference)
HOME_BIAS = {0: {0: 3.0, 1: 2.2, 2: 2.0, 8: 1.4}, 1: {3: 3.0, 4: 2.2, 1: 1.6, 12: 1.3}, 2: {5: 3.0, 6: 2.6, 7: 2.0, 14: 1.3}}
STRONGHOLD_QUIET = 0.7         # strongholds see fewer players

DEFAULTS = {"speed": 1.0, "randomness": 1.0, "own_nation": 2, "own_nation_share": 0.8, "history_weeks": 6}


# ---------- the game's rules, copied from conquest_data.h and conquest_system.cpp ----------
def beastmen_influence(region, nations, kills, homepoints):
    if homepoints == 0:
        return 0
    if kills == 0:
        return MAX_BEASTMEN
    total = sum(nations)
    if total == 0:
        return MAX_BEASTMEN
    weight = WEIGHT.get(region, 10)
    return min(weight * homepoints * total // (kills + weight), MAX_BEASTMEN)


def decide_owner(nations, beastmen):
    s, b, w = nations
    if s > b and s > w and s > beastmen:
        return 0
    if b > s and b > w and b > beastmen:
        return 1
    if w > s and w > b and w > beastmen:
        return 2
    if beastmen > s and beastmen > b and beastmen > w:
        return BEASTMEN
    return NEUTRAL


def lag_multiplier(nations, index):
    first = max(nations)
    if nations[index] < first // 2:
        return 3
    if nations[index] < first:
        return 2
    return 1


def tally(rows):
    """What conquest_system.cpp does at the weekly tally."""
    for region, row in enumerate(rows):
        row["prev"] = row["ctrl"]
        bm = beastmen_influence(region, row["inf"], row["kills"], row["hp"])
        row["ctrl"] = decide_owner(row["inf"], bm)
        row["inf"] = [0, 0, 0]
        row["kills"] = 0
        row["hp"] = 0


# ---------- the imaginary population ----------
_weights_cache = {}


def _base_bias(nation):
    """Where a nation's players like to be: its home regions count more, every other region counts the same for all nations."""
    return [HOME_BIAS[nation].get(region, 1.0) * (STRONGHOLD_QUIET if WEIGHT.get(region) == 50 else 1.0) for region in range(19)]


def attention(seed, nation, week, randomness):
    """How a nation's players spread over the regions in a given week (mean 1.0). It drifts from week to week."""
    key = (seed, nation, week, randomness)
    if key in _weights_cache:
        return _weights_cache[key]
    base = _base_bias(nation)
    w, g = list(base), 1.0
    for i in range(week - 40, week + 1):
        rng = random.Random(f"{seed}/{nation}/{i}")
        w = [ALPHA * w[r] + (1 - ALPHA) * base[r] * math.exp(SIGMA * randomness * rng.gauss(0, 1)) for r in range(19)]
        g = GALPHA * g + (1 - GALPHA) * math.exp(GSIGMA * randomness * rng.gauss(0, 1))
    result = [v * g for v in w]
    _weights_cache[key] = result
    return result


def simulate_step(rows, j, settings, seed):
    """One 6-hour step of other players acting. Adds to the rows in place."""
    week = (j - 1) // STEPS_PER_WEEK          # steps 1..28 make up one week; step 28 ends with the tally
    slot = (j - 1) % STEPS_PER_WEEK
    own, share, speed, rnd = settings["own_nation"], settings["own_nation_share"], settings["speed"], settings["randomness"]
    att = [attention(seed, n, week, rnd) for n in range(3)]
    for region, row in enumerate(rows):
        rng = random.Random(f"{seed}/{j}/{region}")
        activity = 0.0
        before = list(row["inf"])        # every nation is judged against the same starting scores, whatever order they are handled in
        owner = row["ctrl"]
        for nation in range(3):
            factor = share if nation == own else 1.0
            if owner == nation:
                factor *= INCUMBENT
            elif owner == BEASTMEN:
                factor *= BACKLASH
            activity += factor * att[nation][region] / 3
            raw = RAW_WEEK * speed * factor * att[nation][region] / STEPS_PER_WEEK
            raw *= max(0.0, 1.0 + STEP_NOISE * rnd * rng.gauss(0, 1))
            if raw <= 0:
                continue
            points = int(raw * lag_multiplier(before, nation))
            row["inf"][nation] += max(points // 10, 1)
        # kills and home point uses follow the region's activity steadily: the week's total is spread over the 28 steps
        wt = WEIGHT.get(region, 10)
        phase = random.Random(f"{seed}/{week}/{region}/counters")
        kill_phase, hp_phase = phase.random(), phase.random()
        # (activity is the week's average, so it is the same in every step of the week)
        week_activity = sum((share if n == own else 1.0) * att[n][region] / 3 for n in range(3))
        kills_week = KILLS_WEEK * speed * week_activity
        hp_week = HOMEPOINTS_WEEK[wt] * speed * week_activity
        row["kills"] += int(kills_week * (slot + 1) / STEPS_PER_WEEK + kill_phase) - int(kills_week * slot / STEPS_PER_WEEK + kill_phase)
        row["hp"] += int(hp_week * (slot + 1) / STEPS_PER_WEEK + hp_phase) - int(hp_week * slot / STEPS_PER_WEEK + hp_phase)


def advance(rows, from_j, to_j, settings, seed):
    """Steps (from_j, to_j]. A tally happens at the end of every step whose number is a multiple of 28. Returns how many tallies ran."""
    tallies = 0
    for j in range(from_j + 1, to_j + 1):
        simulate_step(rows, j, settings, seed)
        if j % STEPS_PER_WEEK == 0:
            tally(rows)
            tallies += 1
    return tallies


def blank_rows():
    return [{"ctrl": NEUTRAL, "prev": NEUTRAL, "inf": [0, 0, 0], "kills": 0, "hp": 0} for _ in range(19)]


def step_of(timestamp):
    return int((timestamp - ANCHOR) // STEP)


# ---------- state, settings and the database ----------
def load_state():
    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8-sig") as f:
            state = json.load(f)
    changed = False
    for key, value in DEFAULTS.items():
        if key not in state:
            state[key], changed = value, True
    if "seed" not in state:
        state["seed"], changed = random.SystemRandom().randrange(10 ** 9), True
    if changed:
        save_state(state)
    return state


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(state, f, indent=2)


def connect():
    import mariadb
    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])


def read_rows(conn):
    cur = conn.cursor()
    cur.execute("SELECT region_id, region_control, region_control_prev, sandoria_influence, bastok_influence, windurst_influence, "
                "mob_kills, player_homepoints FROM conquest_system ORDER BY region_id")
    rows = blank_rows()
    for rid, ctrl, prev, s, b, w, kills, hp in cur.fetchall():
        if 0 <= rid < 19:
            rows[rid] = {"ctrl": int(ctrl), "prev": int(prev), "inf": [int(s), int(b), int(w)], "kills": int(kills), "hp": int(hp)}
    cur.close()
    return rows


def write_rows(conn, rows):
    cur = conn.cursor()
    for rid, r in enumerate(rows):
        cur.execute("UPDATE conquest_system SET region_control = ?, region_control_prev = ?, sandoria_influence = ?, bastok_influence = ?, "
                    "windurst_influence = ?, mob_kills = ?, player_homepoints = ? WHERE region_id = ?",
                    (r["ctrl"], r["prev"], r["inf"][0], r["inf"][1], r["inf"][2], r["kills"], r["hp"], rid))
    conn.commit()
    cur.close()


def backup(rows):
    os.makedirs(BACKUPS, exist_ok=True)
    path = os.path.join(BACKUPS, "conquest-before-sim-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    old = sorted(n for n in os.listdir(BACKUPS) if n.startswith("conquest-before-sim-"))
    for name in old[:-5]:
        try:
            os.remove(os.path.join(BACKUPS, name))
        except OSError:
            pass
    return path


# ---------- modes ----------
def repair_bot_homepoints(rows):
    """One time (2026-11-20): until then every bot that returned to its Home Point after dying counted for the beastmen, and
    the bots die a lot, so the Home Point counters ran into the hundreds and the beastmen took nearly every region. Puts the
    counters back to what the kills in the region would bring, and gives each region the beastmen hold back to the nation that
    held it before (or, when the beastmen held it then too, to the nation leading there now). Returns how many regions changed
    hands."""
    returned = 0
    for region, row in enumerate(rows):
        weight = WEIGHT.get(region, 10)
        row["hp"] = min(row["hp"], int(round(row["kills"] * HOMEPOINTS_WEEK[weight] / KILLS_WEEK)))
        if row["ctrl"] == BEASTMEN:
            owner = row["prev"] if row["prev"] in (0, 1, 2) else decide_owner(row["inf"], 0)
            if owner in (0, 1, 2):
                row["ctrl"] = owner
                returned += 1
        if row["prev"] == BEASTMEN and row["ctrl"] in (0, 1, 2):
            row["prev"] = row["ctrl"]
    return returned


def tick(conn, state, now, dry_run=False):
    seed, j_now = state["seed"], step_of(now)
    rows = read_rows(conn)
    notes = []
    if "last_step" in state and not state.get("bot_homepoints_repaired"):
        returned = repair_bot_homepoints(rows)
        notes.append(f"one-time repair: the bots' Home Points no longer count for the beastmen, {returned} region(s) given back")
    if not dry_run:
        state["bot_homepoints_repaired"] = True
    if "last_step" not in state:                 # first run: build a few weeks of history so the map is not blank
        weeks = int(state["history_weeks"])
        j_tally = j_now - (j_now % STEPS_PER_WEEK)            # the most recent tally
        history = blank_rows()
        if weeks > 0:
            advance(history, j_tally - weeks * STEPS_PER_WEEK, j_tally, state, seed)
            for region, row in enumerate(rows):               # keep whatever you have done so far this week
                history[region]["inf"] = [a + b for a, b in zip(history[region]["inf"], row["inf"])]
                history[region]["kills"] += row["kills"]
                history[region]["hp"] += row["hp"]
            rows = history
            notes.append(f"first run: built {weeks} weeks of history")
        done = advance(rows, j_tally, j_now, state, seed)
    else:
        last = int(state["last_step"])
        if j_now < last:
            notes.append("the clock went backwards - nothing done")
            return rows, notes, False
        done = advance(rows, last, j_now, state, seed)
        notes.append(f"{j_now - last} step(s) of away time, {done} tally(ies)")
    if not dry_run:
        path = backup(read_rows(conn))
        write_rows(conn, rows)
        state["last_step"] = j_now
        save_state(state)
        notes.append("saved; the old table is in " + path)
    return rows, notes, True


def report(rows):
    lines = [f"{'#':>2} {'region':<22} {'owner':<10} {'last week':<10} {'Sandy':>7} {'Bastok':>7} {'Windy':>7} {'Beast':>9} {'kills':>6} {'hp':>3}"]
    counts = {}
    for region, r in enumerate(rows):
        bm = beastmen_influence(region, r["inf"], r["kills"], r["hp"])
        counts[r["ctrl"]] = counts.get(r["ctrl"], 0) + 1
        lines.append(f"{region:>2} {REGION_NAMES[region]:<22} {OWNER_NAMES.get(r['ctrl'], r['ctrl']):<10} {OWNER_NAMES.get(r['prev'], r['prev']):<10} "
                     f"{r['inf'][0]:>7} {r['inf'][1]:>7} {r['inf'][2]:>7} {bm if bm < MAX_BEASTMEN else 'max':>9} {r['kills']:>6} {r['hp']:>3}")
    lines.append("")
    lines.append("regions held: " + ", ".join(f"{OWNER_NAMES.get(k, k)} {v}" for k, v in sorted(counts.items())))
    return "\n".join(lines)


def main(argv):
    mode = argv[1] if len(argv) > 1 else "report"
    dry = "--dry-run" in argv
    state = load_state()
    conn = connect()
    if mode == "tick":
        rows, notes, _ = tick(conn, state, time.time(), dry)
        print("conquest simulator:", "; ".join(notes))
        if dry:
            print(report(rows))
    elif mode == "stamp":
        if "last_step" in state:
            state["last_step"] = step_of(time.time())
            save_state(state)
        print("conquest simulator: session noted")
    elif mode == "report":
        print(report(read_rows(conn)))
    elif mode == "restore":
        with open(argv[2], "r", encoding="utf-8") as f:
            write_rows(conn, json.load(f))
        print("restored the conquest table from", argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
