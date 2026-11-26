"""Ventures: squad mates sent off from the XIFO app to level at a real exp camp of the era.

The hub works out the whole venture when the mates leave (from venture_data.json, built from the player's own server
by dev/ventures/build_venture_data.py): every kill, level up, drop, rest and highlight, with its time. The app plays
that timeline back as a pixel scene and shows the report once they are back; the launcher takes the rewards into the
game (exp to each mate, gil and items to the character, like portable fishing).

Balance (the user's call): exp is full, a flat 3,000 an hour for everyone (1x, whatever the world's rates); gil,
items and crystals stay modest. In a party the mate wins a lot one time in six (the other five are the party), the
camp's real drop rates are rolled at 45% ("always" drops at 60%), gil is split six ways, and crystals and seals come rarely. Levels 1-9 are
solo (no party): every drop is theirs, but they kill fewer things and roll the drops at 20%.

Deterministic: the same seed and venture always give the same result, so a recall (coming home early) is the same
timeline cut at that moment.
"""
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "venture_data.json")

EXP_PER_HOUR = 3000
MAX_LEVEL = 75
HOURS = (1, 2, 4, 8, 12)
PARTY_FROM = 10                    # level: parties from here, solo below
PARTY_SIZE = 6
LOOT_PARTY = 0.45                  # the camp's drop rates are rolled at this share (parties: then a 1-in-6 lot)
LOOT_SOLO = 0.2
CRYSTAL_PARTY = 0.40               # a crystal drops (Signet) this often per kill, then the lot
CRYSTAL_SOLO = 0.08
SEAL_CHANCE = 0.05                 # Beastmen's Seal per kill (Kindred's Seal from monsters above 50: 0.03)
KINDRED_CHANCE = 0.03
# Caps per venture and mate: one item at most 1 + 1 per 4 hours, crystals of one kind 1 + 1 per 2 hours
GIL_PER_LEVEL = (0.5, 1.0)         # beastmen drop gil: mob level x this, split six ways in a party

TNL = [500, 750, 1000, 1250, 1500, 1750, 2000, 2200, 2400, 2600, 2800, 3000, 3200, 3400, 3600, 3800, 4000, 4200, 4400,
       4600, 4800, 5000, 5100, 5200, 5300, 5400, 5500, 5600, 5700, 5800, 5900, 6000, 6100, 6200, 6300, 6400, 6500, 6600,
       6700, 6800, 6900, 7000, 7100, 7200, 7300, 7400, 7500, 7600, 7700, 7800, 8000, 9200, 10400, 11600, 12800, 14000,
       15200, 16400, 17600, 18800, 20000, 21500, 23000, 24500, 26000, 27500, 29000, 30500, 32000, 34000, 36000, 38000,
       40000, 42000, 44000]
CRYSTAL = {"fire": 4096, "ice": 4097, "wind": 4098, "earth": 4099, "thunder": 4100, "lightning": 4100, "water": 4101,
           "light": 4102, "dark": 4103}
BEASTMEN_SEAL, KINDREDS_SEAL = 1126, 1127
JOBS = ["WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN", "BLU",
        "COR", "PUP"]
TANKS, HEALERS = {"PLD", "NIN", "WAR"}, {"WHM", "RDM"}
DD = ["THF", "BLM", "SAM", "DRG", "RNG", "MNK", "DRK", "BLU", "COR", "BRD"]
SKILLCHAINS = ["Fragmentation", "Distortion", "Fusion", "Gravitation", "Scission", "Liquefaction", "Detonation",
               "Impaction", "Reverberation", "Induration", "Compression", "Transfixion", "Light", "Darkness"]
SYL_A = ["Ka", "Mi", "Ro", "Ta", "Ze", "Lu", "Fen", "Ar", "Vel", "Shi", "Bo", "Ny", "Ira", "Kor", "Sel", "Dar", "Yu", "Ma",
         "Gal", "Tor", "Ri", "Eli", "Ash", "Pa", "Kel", "Nao", "Ul", "Fa", "Jin", "Ro"]
SYL_B = ["ra", "mi", "ko", "rin", "dor", "lia", "nos", "vy", "ta", "zel", "mo", "ris", "ka", "lan", "ne", "th", "ru", "xis",
         "pi", "gan", "wen", "ly", "so", "dra"]
ITEM_FIX = {"Beastmens Seal": "Beastmen's Seal", "Kindreds Seal": "Kindred's Seal"}

_DATA = None


def data():
    global _DATA
    if _DATA is None:
        with open(DATA_PATH, encoding="utf-8") as f:
            _DATA = json.load(f)
        _DATA["by_id"] = {c["id"]: c for c in _DATA["camps"]}
    return _DATA


def item_name(iid):
    name = data()["items"].get(str(iid), f"Item {iid}")
    return ITEM_FIX.get(name, name)


def made_up_name(rng):
    return rng.choice(SYL_A) + rng.choice(SYL_B) + (rng.choice(SYL_B) if rng.random() < 0.3 else "")


def plural(name):
    if name.endswith(("s", "x", "ch", "sh")):
        return name + "es" if not name.endswith("s") else name
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return name[:-1] + "ies"
    return name + "s"


def camps_for(level):
    """The camps that fit a level (the app's list): solo spots below 10, party camps from 10."""
    out = []
    for c in data()["camps"]:
        if c["lo"] <= level <= c["hi"] and (c["solo"] == (level < PARTY_FROM) or (level == PARTY_FROM - 1 and not c["solo"])):
            out.append(c)
    if not out:                          # (never empty: the closest camp of the right kind)
        kind = [c for c in data()["camps"] if c["solo"] == (level < PARTY_FROM)]
        out = [min(kind, key=lambda c: abs((c["lo"] + c["hi"]) / 2 - level))]
    return out


def public_camp(c):
    return {"id": c["id"], "zone": c["zone"], "title": c["title"], "spot": c["spot"], "lo": c["lo"], "hi": c["hi"],
            "solo": c["solo"], "scene": c["scene"],
            "mobs": [{"name": m["name"], "lo": m["lo"], "hi": m["hi"], "look": m["look"]} for m in c["mobs"]]}


def camp_list():
    return [public_camp(c) for c in data()["camps"]]


def exp_needed(level):
    return TNL[max(1, min(MAX_LEVEL, level)) - 1]


# ------------------------------------------------------------------------------------------------ the simulation
def _fit(mob, level, solo, rng):
    """How much this camp's monster fits a party / soloer of this level (they fight Tough to Incredibly Tough)."""
    want = level + (2 if solo else 4)
    mid = (mob["lo"] + mob["hi"]) / 2
    return max(0.02, math.exp(-((mid - want) ** 2) / 10.0)) * (0.5 + min(mob.get("n", 4), 40) / 40)


def _pick(rng, weights):
    total = sum(w for _, w in weights)
    r = rng.uniform(0, total)
    for v, w in weights:
        r -= w
        if r <= 0:
            return v
    return weights[-1][0]


def _next_camp(cur, level):
    fits = [c for c in camps_for(level) if c["id"] != cur["id"]]
    same = [c for c in fits if c["zone"] == cur["zone"]]
    return (same or fits or [cur])[0]


def _party(rng, mates, bots, solo):
    """The party: the mates, then bot players of the world (or made-up adventurers) to six, a tank and healer first."""
    if solo:
        return []
    have = [JOBS[m["job"] - 1] if 1 <= m["job"] <= 18 else "WAR" for m in mates]
    need = []
    if not TANKS & set(have):
        need.append(rng.choice(["PLD", "NIN", "PLD"]))
    if not HEALERS & set(have):
        need.append(rng.choice(["WHM", "WHM", "RDM"]))
    if "RDM" not in have and "RDM" not in need and len(mates) + len(need) < PARTY_SIZE - 1:
        need.append("RDM")
    while len(mates) + len(need) < PARTY_SIZE:
        need.append(rng.choice(DD))
    pool = [b for b in (bots or []) if b.get("name")]
    rng.shuffle(pool)
    out, taken = [], {m["name"].lower() for m in mates}
    for job in need:
        b = pool.pop() if pool else None
        name = b["name"] if b else made_up_name(rng)
        while name.lower() in taken:
            name = made_up_name(rng)
        taken.add(name.lower())
        out.append({"name": name, "job": job, "race": int((b or {}).get("race") or rng.randint(1, 8)), "bot": bool(b)})
    return out


def _drop_list(mob):
    """A monster's drops with doubles merged (some templates list an item once per spawn variant): the best chance."""
    if "_merged" not in mob:
        best, groups = {}, []
        for d in mob.get("drops") or []:
            if isinstance(d, list):
                best[d[0]] = max(best.get(d[0], 0), d[1])
            else:
                groups.append(d)
        mob["_merged"] = [[i, c] for i, c in best.items()] + groups
    return mob["_merged"]


def _roll_drops(rng, mob, share):
    got = []
    for d in _drop_list(mob):
        if isinstance(d, list):
            if rng.random() < min(d[1], 600) / 1000 * share:      # ("always" drops: still not every single kill)
                got.append(d[0])
        elif rng.random() < d["g"] / 1000 * share:
            got.append(_pick(rng, [(i, w) for i, w in d["of"]]))
    return got


def simulate(seed, camp_id, mates, hours, start, bots=None):
    """The whole venture. mates: [{slot, name, job, race, level, exp}] (exp = progress in the current level)."""
    rng = random.Random(f"{seed}|{camp_id}|{hours}")
    camp = data()["by_id"].get(camp_id) or data()["camps"][0]
    mates = [dict(m) for m in mates][:PARTY_SIZE]
    for m in mates:
        m["level"] = max(1, min(MAX_LEVEL, int(m.get("level") or 1)))
        m["exp"] = max(0, min(exp_needed(m["level"]) - 1, int(m.get("exp") or 0)))
        m["start"], m["exp0"] = m["level"], m["exp"]
    lvl = lambda: min(m["level"] for m in mates)
    solo = lvl() < PARTY_FROM
    party = _party(rng, mates, bots, solo)
    total = int(hours * 3600)
    travel = int(min(900, total * 0.06) * rng.uniform(0.7, 1.0))
    t = travel
    kph = rng.uniform(11, 17) if solo else rng.uniform(18, 26)
    per_kill_exp = EXP_PER_HOUR / kph / 0.86            # (a first guess; rescaled below to exactly 3,000 an hour)
    events = [{"t": 0, "k": "leave"}, {"t": travel, "k": "arrive", "camp": camp["id"]}]
    if party:
        events.append({"t": travel + 20, "k": "party"})
    chain, since_rest = 0, 0
    have = {}                                                    # (mate, item) -> count, for the caps
    cap_item = 1 + int(hours // 4)
    cap_crystal = 1 + int(hours // 2)

    def give(idx, iid):
        cap = cap_crystal if 4096 <= iid <= 4103 else cap_item
        if have.get((idx, iid), 0) < cap:
            have[(idx, iid)] = have.get((idx, iid), 0) + 1
            ev["drops"].append([idx, iid])
    while True:
        gap = 3600 / kph * rng.uniform(0.6, 1.4)
        if since_rest >= rng.randint(6, 11):
            rest = int(rng.uniform(60, 150))
            if t + rest >= total:
                break
            events.append({"t": int(t), "k": "rest", "d": rest})
            t += rest
            since_rest = 0
        if t + gap >= total:
            break
        t += gap
        level_now = lvl()
        if level_now > camp["hi"] + 1 and level_now < MAX_LEVEL:
            new = _next_camp(camp, level_now)
            if new["id"] != camp["id"]:
                camp = new
                walk = int(rng.uniform(180, 420))
                events.append({"t": int(t), "k": "move", "camp": camp["id"]})
                t += walk
                if t >= total:
                    break
        mi = _pick(rng, [(i, _fit(m, level_now, solo, rng)) for i, m in enumerate(camp["mobs"])])
        mob = camp["mobs"][mi]
        mlv = rng.randint(mob["lo"], max(mob["lo"], mob["hi"]))
        chain = chain + 1 if rng.random() < 0.8 else 0
        gain = int(round(per_kill_exp * rng.uniform(0.75, 1.25)))
        ev = {"t": int(t), "k": "kill", "c": camp["id"], "m": mi, "lv": mlv, "x": gain, "drops": []}
        if not solo and chain >= 3 and rng.random() < 0.12:
            ev["sc"] = rng.choice(SKILLCHAINS[:12] if level_now < 30 else SKILLCHAINS)
        if not solo and rng.random() < 0.05:
            ev["link"] = True
        if rng.random() < (0.012 if not solo else 0.02):
            ev["close"] = True                                   # a close call: someone got low, a cure in time
        # the loot, for each mate (each one is a lotter)
        share = LOOT_SOLO if solo else LOOT_PARTY
        for idx, m in enumerate(mates):
            win = 1.0 if solo else 1.0 / PARTY_SIZE
            for iid in _roll_drops(rng, mob, share):
                if rng.random() < win:
                    give(idx, iid)
            if rng.random() < (CRYSTAL_SOLO if solo else CRYSTAL_PARTY / PARTY_SIZE) and mlv > 1:
                give(idx, CRYSTAL.get(mob.get("el"), 4103))
            if mlv > 1 and rng.random() < SEAL_CHANCE * win:
                give(idx, BEASTMEN_SEAL)
            if mlv > 50 and rng.random() < KINDRED_CHANCE * win:
                give(idx, KINDREDS_SEAL)
        if mob.get("beast"):
            gil = mlv * rng.uniform(*GIL_PER_LEVEL) / (1 if solo else PARTY_SIZE)
            ev["gil"] = max(1, int(gil)) * len(mates)
        ups = []
        for idx, m in enumerate(mates):
            if m["level"] >= MAX_LEVEL:
                continue
            m["exp"] += gain
            while m["level"] < MAX_LEVEL and m["exp"] >= exp_needed(m["level"]):
                m["exp"] -= exp_needed(m["level"])
                m["level"] += 1
                ups.append([idx, m["level"]])
        if ups:
            ev["up"] = ups
        if not ev["drops"]:
            del ev["drops"]
        events.append(ev)
        since_rest += 1
    events.append({"t": total, "k": "home"})
    _rescale(events, mates, hours)
    return {"camp": camp_id, "solo": solo, "party": party, "events": events, "hours": hours, "start": int(start),
            "end": int(start) + total,
            "mates": [{"slot": m.get("slot"), "name": m["name"], "job": m["job"], "race": m.get("race", 1),
                       "face": m.get("face", 0), "weapon": m.get("weapon", 0), "level": m["start"],
                       "exp": m["exp0"]} for m in mates]}


def _rescale(events, mates, hours):
    """Full exp: the kills share exactly 3,000 an hour (the guess above lands near it), then the level ups again."""
    kills = [e for e in events if e["k"] == "kill"]
    if not kills:
        return
    target = EXP_PER_HOUR * hours
    raw = sum(e["x"] for e in kills)
    for e in kills:
        e["x"] = max(1, int(round(e["x"] * target / raw)))
    for m in mates:
        m["level"], m["exp"] = m["start"], m["exp0"]
    for e in kills:
        e.pop("up", None)
        ups = []
        for idx, m in enumerate(mates):
            if m["level"] >= MAX_LEVEL:
                continue
            m["exp"] += e["x"]
            while m["level"] < MAX_LEVEL and m["exp"] >= exp_needed(m["level"]):
                m["exp"] -= exp_needed(m["level"])
                m["level"] += 1
                ups.append([idx, m["level"]])
        if ups:
            e["up"] = ups


def end_state(plan, until=None):
    """(2026-11-25, user: a second venture before syncing started from the old level) where each mate stands when the
    venture is over (or at `until`): {slot: (level, exp in that level)}, worked out from its start and what it earned."""
    res = results(plan, until)
    out = {}
    for i, m in enumerate(plan["mates"]):
        lv = int(m.get("start", m.get("level", 1)))
        xp = int(m.get("exp0", m.get("exp", 0))) + res["exp"][i]
        while lv < MAX_LEVEL and xp >= exp_needed(lv):
            xp -= exp_needed(lv)
            lv += 1
        if lv >= MAX_LEVEL:
            lv, xp = MAX_LEVEL, 0
        out[m["slot"]] = (lv, xp)
    return out


def results(plan, until=None):
    """What the venture brought up to `until` seconds in (all of it when None): exp per mate, levels, gil, items."""
    cut = plan["end"] - plan["start"] if until is None else max(0, int(until))
    n = len(plan["mates"])
    exp = [0] * n
    level = [m["level"] for m in plan["mates"]]
    gil, items, kills, best = 0, {}, 0, []
    highlights = []
    for ev in plan["events"]:
        if ev["t"] > cut:
            break
        if ev["k"] != "kill":
            continue
        kills += 1
        for i in range(n):
            if plan["mates"][i]["level"] < MAX_LEVEL:
                exp[i] += ev["x"]
        for idx, lv in ev.get("up", []):
            level[idx] = lv
        gil += ev.get("gil", 0)
        for idx, iid in ev.get("drops", []):
            items[iid] = items.get(iid, 0) + 1
    return {"exp": exp, "levels": level, "gil": gil, "kills": kills,
            "items": [[iid, c, item_name(iid)] for iid, c in sorted(items.items(), key=lambda kv: (-kv[1], kv[0]))]}


# ------------------------------------------------------------------------------------------------ the story
def story(plan, until=None):
    """The report the mates bring home: a few short paragraphs written from what really happened."""
    rng = random.Random(f"story|{plan['start']}|{plan['camp']}")
    cut = plan["end"] - plan["start"] if until is None else max(0, int(until))
    camps = data()["by_id"]
    mates = plan["mates"]
    names = [m["name"] for m in mates]
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    first = camps.get(plan["camp"]) or data()["camps"][0]
    res = results(plan, until)
    lines = []
    open_ = [f"{who} set off for {first['title']}" + (f", {first['spot']}." if first.get("spot") else "."),
             f"{who} packed some food and headed out to {first['title']}.",
             f"Bags packed, {who} left for {first['title']}" + (f" and made camp at {first['spot']}." if first.get("spot") else ".")]
    lines.append(rng.choice(open_))
    if plan["party"]:
        p = [{"name": m["name"], "job": JOBS[m["job"] - 1] if 1 <= m["job"] <= 18 else "WAR"} for m in mates] + plan["party"]
        tank = next((x for x in p if x["job"] in TANKS), None)
        heal = next((x for x in p if x["job"] in HEALERS and x is not tank), None)
        bits = []
        if tank:
            bits.append(f"{tank['name']} ({tank['job']}) held hate")
        if heal:
            bits.append(f"{heal['name']} ({heal['job']}) kept everyone standing")
        rest = [x["name"] for x in p[len(mates):] if x is not tank and x is not heal]
        sent = ("They joined a party: " + ", ".join(bits) + ("" if not rest else f", with {', '.join(rest)} rounding it out") + ".")
        lines.append(sent)
    else:
        lines.append(rng.choice(["No party at this level: just hunting alone, one monster at a time.",
                                 "Too early for parties, so it was solo work: pick a target, fight, rest, repeat."]))
    counts = {}
    for ev in plan["events"]:
        if ev["t"] > cut:
            break
        if ev["k"] == "kill":
            name = camps[ev["c"]]["mobs"][ev["m"]]["name"]
            counts[name] = counts.get(name, 0) + 1
    if counts:
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
        lines.append("Mostly " + ", ".join(plural(n) for n, _ in top)
                     + f": {res['kills']} kills in all.")
    notes = []
    for ev in plan["events"]:
        if ev["t"] > cut:
            break
        if ev["k"] == "move":
            c = camps[ev["camp"]]
            notes.append(f"The monsters stopped giving much, so the group moved on to {c['title']} ({c['spot']}).")
        elif ev["k"] == "kill" and ev.get("sc") and len([n for n in notes if "skillchain" in n]) < 1:
            notes.append(f"Somewhere in there came a perfect {ev['sc']} skillchain. Everyone cheered in party chat.")
        elif ev["k"] == "kill" and ev.get("close") and len([n for n in notes if "close" in n]) < 1:
            mob = camps[ev["c"]]["mobs"][ev["m"]]["name"]
            notes.append(f"One {mob} got too close for comfort: HP in the red before the cure landed.")
        elif ev["k"] == "kill" and ev.get("link") and len([n for n in notes if "linked" in n]) < 1:
            mob = camps[ev["c"]]["mobs"][ev["m"]]["name"]
            notes.append(f"A pull linked and two {plural(mob)} came in at once. Sleep, then one at a time.")
    lines.extend(notes[:3])
    ups = [(i, lv) for i, lv in enumerate(res["levels"]) if lv > mates[i]["level"]]
    for i, lv in ups:
        lines.append(f"{names[i]} went from level {mates[i]['level']} to {lv}!")
    rare = [it for it in res["items"] if it[0] not in CRYSTAL.values() and it[0] not in (BEASTMEN_SEAL, KINDREDS_SEAL)]
    if rare:
        lines.append("Brought home: " + ", ".join(f"{c} {n}" if c > 1 else n for _, c, n in rare[:4])
                     + (" and a few more things." if len(rare) > 4 else "."))
    if until is not None and until < plan["end"] - plan["start"]:
        lines.append(f"Called home early, after {fmt_hours(until)}.")
    lines.append(rng.choice(["Back home now, tired and happy.", "Good hunt. Ready for the next one.",
                             "Home again, and already talking about the next camp.", "Worth it. Back in town now."]))
    return lines


def fmt_hours(sec):
    sec = int(sec)
    h, m = sec // 3600, (sec % 3600) // 60
    return (f"{h} hour{'s' if h != 1 else ''}" if h else "") + (" " if h and m else "") + (f"{m} minute{'s' if m != 1 else ''}" if m or not h else "")
