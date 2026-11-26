"""Tetra Master's rules for the hub's PvP matches (2026-11-25), ported line for line from the server
(modules/custom/lua/tetramaster_rules.lua, itself a 1-to-1 port of Nalfey's TetraMaster addon). The app's src/tetra/rules.ts
is the same again; test_tetra.py plays the same matches in all three and compares them event by event.

Board: cells[x][y], x and y 1-4 (index 0 unused). A cell is None, {"block": 1|2} or a card dict with a "side".
rng(lo, hi) returns an integer in [lo, hi]. Python 3 standard library only."""
import random

CARDS = None          # [None, (name, code), ...] by id, loaded from tetra_cards.json next to this file
SIDES = ("blue", "red")
HAND_SIZE = 5
DIRS = [("up", 0, -1, "down"), ("down", 0, 1, "up"), ("left", -1, 0, "right"), ("right", 1, 0, "left"),
        ("upleft", -1, -1, "downright"), ("upright", 1, -1, "downleft"), ("downleft", -1, 1, "upright"),
        ("downright", 1, 1, "upleft")]
BIT = {d[0]: 1 << i for i, d in enumerate(DIRS)}
HEX = "0123456789ABCDEF"


def load_cards(path=None):
    global CARDS
    import json
    import os
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "tetra_cards.json")
    with open(path, encoding="utf-8") as f:
        CARDS = [None] + [tuple(c) for c in json.load(f)]
    return CARDS


def has_arrow(mask, name):
    return (mask & BIT[name]) != 0


def opposite(side):
    return "red" if side == "blue" else "blue"


def base(cid):
    if CARDS is None:
        load_cards()
    if not isinstance(cid, int) or cid < 1 or cid >= len(CARDS):
        return None
    name, code = CARDS[cid]
    return {"name": name, "attack": HEX.index(code[0]), "type": code[1], "pdef": HEX.index(code[2]), "mdef": HEX.index(code[3])}


def new_card(rng, cid):
    b = base(cid)
    if b is None:
        return None
    mask = 0
    for i in range(len(DIRS)):
        if rng(1, 2) == 1:
            mask |= 1 << i
    return {"id": cid, "type": b["type"], "arrows": mask, "atk": rng(b["attack"] * 16, b["attack"] * 16 + 15),
            "pdef": rng(b["pdef"] * 16, b["pdef"] * 16 + 15), "mdef": rng(b["mdef"] * 16, b["mdef"] * 16 + 15)}


def copy_card(c):
    return {k: c[k] for k in ("id", "type", "arrows", "atk", "pdef", "mdef", "uid") if k in c}


def card_code(c):
    d = lambda v: HEX[min(15, v // 16)]
    return d(c["atk"]) + c["type"] + d(c["pdef"]) + d(c["mdef"])


def new_board(rng):
    cells = [[None] * 5 for _ in range(5)]
    blocks = rng(0, 6)
    placed = 0
    while placed < blocks:
        x = rng(1, 4)
        y = rng(1, 4)
        if cells[x][y] is None:
            cells[x][y] = {"block": 2 if rng(1, 2) == 1 else 1}
            placed += 1
    return cells


def card_at(cells, x, y):
    if x < 1 or x > 4 or y < 1 or y > 4:
        return None
    c = cells[x][y]
    return c if c is not None and c.get("side") else None


def new_match(rng, hands, first="blue", cells=None):
    m = {"rng": rng, "cells": cells or new_board(rng), "hands": {"blue": [], "red": []}, "turn": first, "pending": None,
         "over": False, "moves": 0, "px": None, "py": None}
    for side in SIDES:
        for card in hands[side]:
            c = copy_card(card)
            c["owner"] = side
            m["hands"][side].append(c)
    return m


def free_cells(m):
    return [(x, y) for x in range(1, 5) for y in range(1, 5) if m["cells"][x][y] is None]


def battle_stats(a, d):
    t = a["type"]
    if t == "M":
        return a["atk"], d["mdef"]
    if t == "X":
        return a["atk"], min(d["pdef"], d["mdef"])
    if t == "A":
        return max(a["atk"], a["pdef"], a["mdef"]), min(d["atk"], d["pdef"], d["mdef"])
    return a["atk"], d["pdef"]


def _roll_battle(rng, a, d):
    ap, dp = battle_stats(a, d)
    af = ap - rng(0, ap)
    df = dp - rng(0, dp)
    return {"attacker_power": ap, "defender_power": dp, "attacker_final": af, "defender_final": df, "attacker_wins": af > df}


def _maybe_upgrade(rng, card, x, y, events):
    before = card["type"]
    if before in ("P", "M"):
        if rng(1, 64) == 1:
            card["type"] = "X"
    elif before == "X":
        if rng(1, 128) == 1:
            card["type"] = "A"
    if card["type"] != before:
        events.append({"type": "upgrade", "x": x, "y": y, "from": before, "to": card["type"]})


def _flip(card, x, y, side, events, ev):
    card["side"] = side
    ev.update({"x": x, "y": y, "side": side})
    events.append(ev)


def _arrow_targets(cells, ox, oy, winner, seen):
    out = []
    card = card_at(cells, ox, oy)
    if card is None:
        return out
    for name, dx, dy, _ in DIRS:
        if has_arrow(card["arrows"], name):
            nx, ny = ox + dx, oy + dy
            key = nx * 10 + ny
            if key not in seen:
                t = card_at(cells, nx, ny)
                if t is not None and t["side"] != winner:
                    seen.add(key)
                    out.append((nx, ny, t, ox, oy))
    return out


def _pending(m, px, py):
    out = []
    placed = card_at(m["cells"], px, py)
    for name, dx, dy, counter in DIRS:
        d = card_at(m["cells"], px + dx, py + dy)
        if d is not None and d["side"] != placed["side"] and has_arrow(placed["arrows"], name) and has_arrow(d["arrows"], counter):
            out.append({"x": px + dx, "y": py + dy, "dir": name})
    return out


def _fight(m, px, py, battle, events):
    placed = card_at(m["cells"], px, py)
    d = card_at(m["cells"], battle["x"], battle["y"])
    res = _roll_battle(m["rng"], placed, d)
    ev = {"type": "battle", "ax": px, "ay": py, "dx": battle["x"], "dy": battle["y"]}
    ev.update(res)
    events.append(ev)
    if res["attacker_wins"]:
        winner = placed["side"]
        _flip(d, battle["x"], battle["y"], winner, events, {"type": "capture"})
        seen = {battle["x"] * 10 + battle["y"]}
        combo = _arrow_targets(m["cells"], battle["x"], battle["y"], winner, seen)
        combo += _arrow_targets(m["cells"], px, py, winner, seen)
        for i, (fx, fy, card, ox, oy) in enumerate(combo):
            _flip(card, fx, fy, winner, events, {"type": "combo", "count": i + 1, "from_x": ox, "from_y": oy})
        _maybe_upgrade(m["rng"], placed, px, py, events)
    else:
        winner, loser = d["side"], placed["side"]
        n = 0
        for name, dx, dy, _ in DIRS:
            if has_arrow(placed["arrows"], name):
                adj = card_at(m["cells"], px + dx, py + dy)
                if adj is not None and adj is not placed and adj["side"] == loser:
                    n += 1
                    _flip(adj, px + dx, py + dy, winner, events, {"type": "combo", "count": n, "from_x": px, "from_y": py})
        _flip(placed, px, py, winner, events, {"type": "capture"})
        _maybe_upgrade(m["rng"], d, battle["x"], battle["y"], events)


def score(m):
    b = r = 0
    for x in range(1, 5):
        for y in range(1, 5):
            c = card_at(m["cells"], x, y)
            if c is not None:
                if c["side"] == "blue":
                    b += 1
                else:
                    r += 1
    return b, r


def result(m):
    b, r = score(m)
    if b == r:
        return "draw", False
    return ("blue", r == 0) if b > r else ("red", b == 0)


def _end_turn(m, events):
    m["pending"] = None
    m["moves"] += 1
    if not m["hands"]["blue"] and not m["hands"]["red"]:
        m["over"] = True
        b, r = score(m)
        winner, perfect = result(m)
        events.append({"type": "end", "blue": b, "red": r, "winner": winner, "perfect": perfect})
    else:
        m["turn"] = opposite(m["turn"])
        events.append({"type": "turn", "side": m["turn"]})


def _resolve(m, events):
    while True:
        lst = _pending(m, m["px"], m["py"])
        if not lst:
            _end_turn(m, events)
            return
        if len(lst) > 1:
            m["pending"] = lst
            events.append({"type": "choose", "side": m["turn"], "options": lst})
            return
        _fight(m, m["px"], m["py"], lst[0], events)


def place(m, side, hand_index, x, y):
    """Card number hand_index (1-based) of side's hand at (x, y). Returns (events, None) or (None, reason)."""
    if m["over"]:
        return None, "over"
    if m["pending"]:
        return None, "choose a battle first"
    if side != m["turn"]:
        return None, "not your turn"
    if not (isinstance(x, int) and isinstance(y, int) and 1 <= x <= 4 and 1 <= y <= 4) or m["cells"][x][y] is not None:
        return None, "cell not free"
    hand = m["hands"][side]
    if not isinstance(hand_index, int) or not 1 <= hand_index <= len(hand):
        return None, "no such card"
    card = hand.pop(hand_index - 1)
    card["side"] = side
    m["cells"][x][y] = card
    m["px"], m["py"] = x, y
    events = [{"type": "place", "side": side, "x": x, "y": y, "id": card["id"], "arrows": card["arrows"], "code": card_code(card)}]
    for name, dx, dy, counter in DIRS:
        if has_arrow(card["arrows"], name):
            d = card_at(m["cells"], x + dx, y + dy)
            if d is not None and d["side"] != side and not has_arrow(d["arrows"], counter):
                _flip(d, x + dx, y + dy, side, events, {"type": "capture"})
    _resolve(m, events)
    return events, None


def choose_battle(m, side, index):
    if not m["pending"]:
        return None, "nothing to choose"
    if side != m["turn"]:
        return None, "not your turn"
    if not isinstance(index, int) or not 1 <= index <= len(m["pending"]):
        return None, "no such battle"
    battle = m["pending"][index - 1]
    m["pending"] = None
    events = []
    _fight(m, m["px"], m["py"], battle, events)
    _resolve(m, events)
    return events, None


def random_move(m, side, rng):
    """Nalfey's easy AI (a random free cell and card), for a player whose time ran out."""
    while True:
        x = rng(1, 4)
        y = rng(1, 4)
        if m["cells"][x][y] is None:
            return rng(1, len(m["hands"][side])), x, y


def sys_rng():
    r = random.SystemRandom()
    return lambda lo, hi: r.randint(lo, hi)
