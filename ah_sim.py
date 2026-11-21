#!/usr/bin/env python3
"""Auction house simulator for the solo server.

  python ah_sim.py report   show what would be stocked (counts, newest items) - changes nothing
  python ah_sim.py seed     stock the auction house now
  python ah_sim.py run      keep running: restock, and buy what you list at fair prices (the launcher starts this)
  python ah_sim.py clear    remove everything the simulator listed
  python ah_sim.py status   count the simulator's listings and check the game can see them - changes nothing
  python ah_sim.py prices   download current HorizonXI auction prices from PSXI (psxi.gg) into ah_prices.json
  python ah_sim.py unhide   put every item hidden from the auction house menus back (undo for browse.hide_above_level)

Settings live in ah_sim.json (created on first run). The era filter, prices, stock depth and buying rules are all there.
Every item the auction house menus can show is stocked; items with no vendor or market price use prices.no_price_fallback.
"""
import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "seller_name": "AHBot",
    "cycle_seconds": 60,
    "era": {
        # Items newer than the 75 era are left out. Item ids grow roughly with release date, so this is a ceiling per kind of item.
        "other_max_id": 5800,        # materials, food, potions, scrolls...
        "armor_min_id": 12000,
        "armor_max_id": 15999,       # armor and jewelry
        "weapon_max_id": 18199,      # weapons and ammo (from 16000 up)
        "equipment_max_level": 75,
        "allow_ids": [],             # always stock these item ids
        # Spell scrolls: the scroll's spell (item_basic.subid = spell_list.spellid) must be from these expansions (spell_list.content_tag;
        # "" = the original game) and learnable at level 1-75 by a job of the era (WAR..PUP). Everything else is left out and hidden.
        "spell_tags": ["", "ROTZ", "COP", "TOAU"],
        "spell_max_level": 75,
        "spell_max_job": 18,         # job ids 1-18: WAR MNK WHM BLM RDM THF PLD DRK BST BRD RNG SAM NIN DRG SMN BLU COR PUP
        "deny_ids": [],              # never stock these item ids
        "stock_all_visible": True,    # stock every item the auction house menus can show, not just the era ranges above
    },
    "prices": {
        "default_multiplier": 4.0,           # fair price = vendor sell price x this
        "equipment_base_multiplier": 3.0,    # equipment: base multiplier ...
        "equipment_level_multiplier": 0.12,  # ... plus this per item level
        "min_over_vendor": 1.5,              # never below this x the vendor price
        "no_price_fallback": 1000,           # items with no vendor and no market price are listed at this (gear: level x 100)
        "stack_discount": 0.9,
        "use_price_file": True,              # price items from ah_prices.json (HorizonXI market data) when it exists
        "price_file": "ah_prices.json",
        "psxi_url": "https://www.psxi.gg/api/v1/market/horizonxi",
    },
    "stock": {
        "cheap_below": 200, "mid_below": 2000, "pricey_below": 20000,
        "depth_cheap": 6, "depth_mid": 4, "depth_pricey": 2, "depth_luxury": 1,
        "luxury_chance": 0.5,
        "max_stack_unit_price": 3000,        # stackable items also get one full stack up to this unit price
        "price_jitter": 0.15,
    },
    "history": {
        "keep_per_item": 10,                 # past sales kept per item (the game shows the newest 10)
        "seed_min": 3,                       # items with no history get this many made-up past sales ...
        "seed_max": 7,                       # ... up to this many
        "seed_days": 7,                      # spread over this many days
        "market_sales_per_cycle": 15,        # the market buys this many of the simulator's own listings each cycle
    },
    "browse": {
        "hide_above_level": True,            # hide equipment above equipment_max_level (and item-level gear) from the auction house menus
    },
    "buying": {
        "min_delay_seconds": 120,            # a listing waits at least this long before the market buys it
        "max_delay_seconds": 1200,
        "max_price_ratio": 1.5,              # prices above this x fair value are never bought
    },
}

REQUIRED_COLUMNS = {"itemid", "stack", "seller", "seller_name", "date", "price", "buyer_name", "sale", "sell_date"}


# Made-up names for the market's buyers and sellers in the sale history.
MARKET_NAMES = [
    "Aldric", "Bellamy", "Corvina", "Dashiel", "Elowen", "Fennick", "Galbrin", "Haleth", "Isolde", "Jorvan",
    "Kestrel", "Lumira", "Marrow", "Nerissa", "Orrin", "Pellam", "Quillon", "Rowenna", "Sable", "Tamsin",
    "Ulric", "Vesper", "Wynne", "Yarrow", "Zephra", "Brannoc", "Cressida", "Dorin", "Emberly", "Faelan",
    "Gwendal", "Hollis", "Ivarra", "Jessamy", "Kordin", "Lisette", "Mabry", "Nolwen", "Oswin", "Perrin",
    "Riona", "Soren", "Thessaly", "Varick", "Wrenna", "Alvise", "Bryndis", "Caelum", "Delphine", "Eamon",
    "Tarumi", "Pokiroko", "Nanapiri", "Kopuru", "Mithrin", "Raelani", "Zalbak", "Gorrund", "Haruki", "Seren",
]


def market_name(rng):
    return rng.choice(MARKET_NAMES)


def merge(base, extra):
    out = dict(base)
    for key, value in (extra or {}).items():
        out[key] = merge(base[key], value) if isinstance(base.get(key), dict) and isinstance(value, dict) else value
    return out


def load_settings(path=None):
    path = path or os.path.join(HERE, "ah_sim.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2)
    with open(path, "r", encoding="utf-8-sig") as f:
        return merge(DEFAULTS, json.load(f))


def connect():
    import mariadb

    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)),
                           user=cfg["db_user"], password=cfg["db_pass"], database=cfg["db_name"])


def query(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def execute(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    cur.close()


def table_columns(conn):
    try:
        return {str(r[0]).lower() for r in query(conn, "SHOW COLUMNS FROM auction_house")}
    except Exception:
        return {str(r[1]).lower() for r in query(conn, "PRAGMA table_info(auction_house)")}  # sqlite, for tests


def buyer_name_nullable(conn):
    """The game server counts a listing as for sale only while buyer_name IS NULL (that is how it writes a player's own listing)."""
    try:
        for row in query(conn, "SHOW COLUMNS FROM auction_house"):
            if str(row[0]).lower() == "buyer_name":
                return str(row[2]).upper() == "YES"
    except Exception:
        for row in query(conn, "PRAGMA table_info(auction_house)"):  # sqlite, for tests
            if str(row[1]).lower() == "buyer_name":
                return not row[3]
    return True


def unsold_buyer(conn):
    return None if buyer_name_nullable(conn) else ""


def repair_listings(conn):
    """Older versions wrote buyer_name = '' on the simulator's unsold listings, which hides them in the game. Put NULL back."""
    if not buyer_name_nullable(conn):
        return 0
    cur = conn.cursor()
    cur.execute("UPDATE auction_house SET buyer_name = NULL WHERE seller = 0 AND sale = 0 AND buyer_name = ''")
    fixed = cur.rowcount
    conn.commit()
    cur.close()
    return max(0, int(fixed or 0))


def check_schema(conn):
    cols = table_columns(conn)
    missing = REQUIRED_COLUMNS - cols
    if missing:
        raise SystemExit("The auction_house table does not look as expected. Missing columns: " + ", ".join(sorted(missing))
                         + "\nColumns found: " + ", ".join(sorted(cols)) + "\nNothing was changed. Send this to Claude.")


class Item:
    __slots__ = ("itemid", "name", "stack_size", "basesell", "level", "equipment", "fair", "stack_fair", "source")

    def __init__(self, itemid, name, stack_size, basesell, level, equipment, fair, stack_fair=None, source="formula"):
        self.itemid, self.name, self.stack_size, self.basesell = itemid, name, stack_size, basesell
        self.level, self.equipment, self.fair = level, equipment, fair
        self.stack_fair, self.source = stack_fair, source


def spell_in_era(jobs, tag, era):
    """jobs: spell_list.jobs, one byte per job (byte 0 = WAR); 0 = that job never learns it."""
    if (tag or "") not in era.get("spell_tags", ["", "ROTZ", "COP", "TOAU"]):
        return False
    levels = bytes(jobs or b"")[:era.get("spell_max_job", 18)]
    return any(1 <= level <= era.get("spell_max_level", 75) for level in levels)


def out_of_era_scrolls(conn, era):
    """{itemid: aH} for every spell scroll whose spell is not from the era (newer expansion, only above level 75, or only for newer jobs).
    Scrolls without a spell (instant warp, instant reraise...) are not spell scrolls and are left to the other rules."""
    spells_by_id, spells_by_name = {}, {}
    for spellid, name, jobs, tag in query(conn, "SELECT spellid, name, jobs, content_tag FROM spell_list"):
        spells_by_id[int(spellid)] = (str(name), jobs, tag)
        spells_by_name[str(name)] = (str(name), jobs, tag)
    out = {}
    # Spell items come in three spellings: scroll_of_<spell>, <spell>_schema (Scholar) and plate_of_<spell> (Geomancer)
    for itemid, name, subid, ah in query(conn, "SELECT itemid, name, subid, aH FROM item_basic "
                                               "WHERE name LIKE 'scroll_of_%' OR name LIKE '%_schema' OR name LIKE 'plate_of_%'"):
        itemid, name, subid = int(itemid), str(name), int(subid or 0)
        if itemid in era["allow_ids"] or subid == 0:
            continue
        if name.startswith("scroll_of_"):
            wanted = name[len("scroll_of_"):]
        elif name.startswith("plate_of_"):
            wanted = name[len("plate_of_"):]
        else:
            wanted = name[:-len("_schema")]
        spell = spells_by_id.get(subid)
        if spell is None or spell[0] != wanted:              # a few scrolls have an odd sub id: go by the spell's name
            spell = spells_by_name.get(wanted, spell)
        if spell is None or not spell_in_era(spell[1], spell[2], era):
            out[itemid] = int(ah or 0)
    return out


def fair_price(basesell, level, equipment, prices):
    mult = (prices["equipment_base_multiplier"] + prices["equipment_level_multiplier"] * level) if equipment else prices["default_multiplier"]
    return max(int(round(basesell * mult)), int(round(basesell * prices["min_over_vendor"])), basesell + 1)


def in_era(itemid, equipment, level, ilevel, su_level, era):
    if itemid in era["deny_ids"]:
        return False
    if itemid in era["allow_ids"]:
        return True
    if equipment:
        # Gear the era does not have (above the cap, item-level gear) is hidden from the menus as well, so it is
        # never stocked even with stock_all_visible on.
        if level > era["equipment_max_level"] or ilevel > 0 or su_level > 0:
            return False
        if era.get("stock_all_visible", True):
            return True
        return era["armor_min_id"] <= itemid <= era["armor_max_id"] or (16000 <= itemid <= era["weapon_max_id"])
    if era.get("stock_all_visible", True):
        return True
    return itemid <= era["other_max_id"]


# ---- HorizonXI prices (PSXI) ----

def _pick(stats):
    """From one PSXI price block (single or stack), take the 7-day median, else the 7-day average, else the last sale."""
    if not isinstance(stats, dict):
        return None
    for key in ("median", "avg", "lastSale"):
        value = stats.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return int(round(value))
    return None


def parse_psxi(payload):
    """PSXI market snapshot -> {itemid: [single price or None, stack price or None]}."""
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("no 'data' list in the PSXI answer")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("itemId") is None:
            continue
        ah = row.get("ah") or {}
        single, stack = _pick(ah.get("single")), _pick(ah.get("stack"))
        if single or stack:
            out[int(row["itemId"])] = [single, stack]
    return out


def fetch_prices(settings, here=HERE):
    import urllib.request

    url = settings["prices"]["psxi_url"]
    request = urllib.request.Request(url, headers={"User-Agent": "FFXI-Offline-ah_sim/1.0 (single-player private server)",
                                                   "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as answer:
        raw = answer.read()
    with open(os.path.join(here, "ah_prices_raw.json"), "wb") as f:
        f.write(raw)  # kept for checking, if the format ever changes
    prices = parse_psxi(json.loads(raw.decode("utf-8")))
    if not prices:
        raise SystemExit("PSXI answered but no prices were found in it. The answer is saved in ah_prices_raw.json - send it to Claude.")
    data = {"source": url, "fetched": int(time.time()), "items": {str(k): v for k, v in sorted(prices.items())}}
    with open(os.path.join(here, settings["prices"]["price_file"]), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def load_price_file(settings, here=HERE):
    if not settings["prices"]["use_price_file"]:
        return None
    path = os.path.join(here, settings["prices"]["price_file"])
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    data["items"] = {int(k): v for k, v in data.get("items", {}).items()}
    return data


def _median(values):
    values = sorted(values)
    n = len(values)
    return None if not n else (values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2)


def calibrate(rows, market, prices):
    """For items Horizon has no price for: learn 'market price / vendor price' from the items it does have, per kind and level band."""
    groups = {}
    for itemid, basesell, equipment, level in rows:
        single = (market.get(itemid) or [None, None])[0]
        if single and basesell > 0:
            key = ("eq", level // 10) if equipment else ("other", 0)
            groups.setdefault(key, []).append(single / basesell)
            groups.setdefault(("eq",) if equipment else ("other",), []).append(single / basesell)
    ratios = {k: _median(v) for k, v in groups.items() if len(v) >= 10}
    lo = prices["min_over_vendor"]
    return {k: max(lo, min(200.0, r)) for k, r in ratios.items()}


def estimate(basesell, equipment, level, ratios, prices):
    key = ("eq", level // 10) if equipment else ("other", 0)
    ratio = ratios.get(key) or ratios.get(("eq",) if equipment else ("other",))
    if ratio is None:
        return fair_price(basesell, level, equipment, prices)
    return max(int(round(basesell * ratio)), basesell + 1)


def price_rate(here=HERE):
    """(2026-11-21, Tasou) the launcher's "Auction house prices" rate (rates.json main.AH_PRICE_RATE): 1 = the prices as
    they are, 0.5 = half, 2 = double. Never below the vendor price + 1 (the item checks below keep that floor)."""
    try:
        with open(os.path.join(here, "rates.json"), "r", encoding="utf-8-sig") as f:
            value = float(json.load(f).get("main.AH_PRICE_RATE", 1.0))
        return max(0.1, min(10.0, value))
    except (OSError, ValueError, TypeError):
        return 1.0


def eligible_items(conn, settings, price_data=None):
    rows = query(conn, "SELECT b.itemid, b.name, b.stackSize, b.BaseSell, e.itemId, e.level, e.ilevel, e.su_level "
                       "FROM item_basic b LEFT JOIN item_equipment e ON e.itemId = b.itemid "
                       "WHERE b.aH > 0")
    market = (price_data or {}).get("items", {})
    scrolls = out_of_era_scrolls(conn, settings["era"])
    era_rows = []
    for itemid, name, stack_size, basesell, eq_id, level, ilevel, su_level in rows:
        if int(itemid) in scrolls:
            continue
        equipment = eq_id is not None
        level, ilevel, su_level = int(level or 0), int(ilevel or 0), int(su_level or 0)
        if in_era(int(itemid), equipment, level, ilevel, su_level, settings["era"]):
            era_rows.append((int(itemid), name, max(1, int(stack_size or 1)), int(basesell or 0), equipment, level))
    ratios = calibrate([(i, b, e, l) for i, _n, _s, b, e, l in era_rows], market, settings["prices"]) if market else {}
    rate = price_rate()
    items = {}
    for itemid, name, stack_size, basesell, equipment, level in era_rows:
        single, stack = (market.get(itemid) or [None, None])
        stack_fair = None
        if stack_size > 1 and stack:
            stack_fair = max(int(stack), basesell * stack_size + 1)
        if single:
            fair, source = max(int(single), basesell + 1), "horizon"
        elif stack_fair:
            fair, source = max(stack_fair // stack_size, basesell + 1), "horizon"
        elif basesell > 0:
            fair, source = (estimate(basesell, equipment, level, ratios, settings["prices"]) if market
                            else fair_price(basesell, level, equipment, settings["prices"])), ("estimate" if market else "formula")
        else:
            # No market price and no vendor price (furniture, quest items, broken gear...): give it a listing anyway,
            # so every item that the auction house menus can show has something for sale.
            fair = int(settings["prices"]["no_price_fallback"])
            if equipment:
                fair = max(fair, level * 100)
            source = "fallback"
        if rate != 1.0:
            fair = max(int(fair * rate), basesell + 1)
            if stack_fair:
                stack_fair = max(int(stack_fair * rate), basesell * stack_size + 1)
        items[itemid] = Item(itemid, name, stack_size, basesell, level, equipment, fair, stack_fair, source)
    return items


def target_depth(item, stock):
    # every item is always in stock: cheap things deeper, expensive things at least one
    if item.fair < stock["cheap_below"]:
        return stock["depth_cheap"]
    if item.fair < stock["mid_below"]:
        return stock["depth_mid"]
    if item.fair < stock["pricey_below"]:
        return stock["depth_pricey"]
    return max(1, stock["depth_luxury"])


def bot_counts(conn):
    singles, stacks = {}, {}
    for itemid, stack, count in query(conn, "SELECT itemid, stack, COUNT(*) FROM auction_house WHERE seller = 0 AND sale = 0 GROUP BY itemid, stack"):
        (stacks if int(stack) else singles)[int(itemid)] = int(count)
    return singles, stacks


def listing_price(item, stack, settings, rng):
    st = settings["stock"]
    if not stack:
        return max(item.basesell + 1, int(item.fair * (1 + rng.uniform(-st["price_jitter"], st["price_jitter"]))))
    if item.stack_fair:
        return max(item.basesell * item.stack_size + 1, int(item.stack_fair * (1 + rng.uniform(-st["price_jitter"], st["price_jitter"]))))
    unit = int(item.fair * (1 + rng.uniform(-st["price_jitter"], st["price_jitter"])))
    return max(item.basesell * item.stack_size + 1, int(unit * item.stack_size * settings["prices"]["stack_discount"]))


def stocks_stacks(item, settings):
    return item.stack_size > 1 and (bool(item.stack_fair) or item.fair <= settings["stock"]["max_stack_unit_price"])


def stock(conn, settings, items, now, fraction=1.0, rng=None):
    """Add missing listings. fraction < 1 adds only some of what is missing each cycle, so the stock refills gradually."""
    rng = rng or random.Random()
    singles, stacks = bot_counts(conn)
    st, name = settings["stock"], settings["seller_name"]
    blank = unsold_buyer(conn)
    rows = []
    for item in items.values():
        want = target_depth(item, st)
        for _ in range(max(0, want - singles.get(item.itemid, 0))):
            if fraction >= 1.0 or rng.random() < fraction:
                rows.append((item.itemid, 0, 0, name, now, listing_price(item, 0, settings, rng), blank, 0, 0))
        if stocks_stacks(item, settings) and want > 0 and stacks.get(item.itemid, 0) == 0:
            if fraction >= 1.0 or rng.random() < fraction:
                rows.append((item.itemid, 1, 0, name, now, listing_price(item, 1, settings, rng), blank, 0, 0))
    if rows:
        cur = conn.cursor()
        cur.executemany("INSERT INTO auction_house (itemid, stack, seller, seller_name, date, price, buyer_name, sale, sell_date) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        cur.close()
    return len(rows)


def buy_player_listings(conn, settings, items, now, rng=None):
    """The market buys what the player lists, at prices close to fair value, after a short wait."""
    rng = rng or random.Random()
    b, name = settings["buying"], settings["seller_name"]
    bought = 0
    for row_id, itemid, stack, price, listed in query(conn, "SELECT id, itemid, stack, price, date FROM auction_house WHERE sale = 0 AND seller <> 0"):
        item = items.get(int(itemid))
        if item is None:
            continue  # not an era item, or no known value: leave it
        delay = b["min_delay_seconds"] + (int(row_id) * 7919) % max(1, b["max_delay_seconds"] - b["min_delay_seconds"])
        if now - int(listed) < delay:
            continue
        if int(stack):
            value = item.stack_fair or item.fair * item.stack_size
        else:
            value = item.fair
        ratio = int(price) / max(1, value)
        if ratio <= 1.0:
            chance = 1.0
        elif ratio <= b["max_price_ratio"]:
            chance = (b["max_price_ratio"] - ratio) / (b["max_price_ratio"] - 1.0)
        else:
            continue
        if rng.random() <= chance:
            execute(conn, "UPDATE auction_house SET buyer_name = ?, sale = ?, sell_date = ? WHERE id = ? AND sale = 0",
                    (market_name(rng), int(price), now, int(row_id)))
            bought += 1
    return bought


def housekeeping(conn, now):
    # bot listings stay "fresh" so the game never expires them (sold ones are kept as sale history, see trim_history)
    execute(conn, "UPDATE auction_house SET date = ? WHERE seller = 0 AND sale = 0 AND date < ?", (now, now - 86400))


def history_keys(conn):
    return {(int(i), 1 if int(st) else 0) for i, st in query(conn, "SELECT DISTINCT itemid, stack FROM auction_house WHERE seller = 0 AND sale > 0")}


def seed_history(conn, settings, items, now, rng=None):
    """Give every stocked item that has no sale history a few made-up past sales near its fair price."""
    rng = rng or random.Random()
    h, have = settings["history"], history_keys(conn)
    rows = []
    for item in items.values():
        if target_depth(item, settings["stock"]) <= 0:
            continue
        for stack in ((0, 1) if stocks_stacks(item, settings) else (0,)):
            if (item.itemid, stack) in have:
                continue
            for _ in range(rng.randint(h["seed_min"], max(h["seed_min"], h["seed_max"]))):
                sold = now - rng.randint(600, max(601, int(h["seed_days"] * 86400)))
                price = listing_price(item, stack, settings, rng)
                rows.append((item.itemid, stack, 0, market_name(rng), sold - rng.randint(1800, 172800), price, market_name(rng), price, sold))
    if rows:
        cur = conn.cursor()
        cur.executemany("INSERT INTO auction_house (itemid, stack, seller, seller_name, date, price, buyer_name, sale, sell_date) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        cur.close()
    return len(rows)


def market_buys(conn, settings, now, rng=None):
    """Other "players" buy some of the simulator's listings, so sale history keeps growing and prices drift. The stock refills."""
    rng = rng or random.Random()
    count = int(settings["history"]["market_sales_per_cycle"])
    if count <= 0:
        return 0
    rows = query(conn, "SELECT id, price FROM auction_house WHERE seller = 0 AND sale = 0 AND buyer_name IS NULL")
    bought = 0
    for row_id, price in rng.sample(rows, min(count, len(rows))):
        execute(conn, "UPDATE auction_house SET buyer_name = ?, sale = ?, sell_date = ? WHERE id = ? AND sale = 0 AND buyer_name IS NULL",
                (market_name(rng), int(price), now, int(row_id)))
        bought += 1
    return bought


def trim_history(conn, settings):
    """Keep only the newest sales per item (and stack/single) of the simulator's own listings and of the bot players'
    (character ids 16000000-16777215: their sales would otherwise pile up forever). Your own sales are never touched."""
    keep = max(1, int(settings["history"]["keep_per_item"]))
    seen, drop = {}, []
    for row_id, itemid, stack in query(conn, "SELECT id, itemid, stack FROM auction_house WHERE (seller = 0 OR seller BETWEEN 16000000 AND 16777215) "
                                             "AND sale > 0 ORDER BY sell_date DESC, id DESC"):
        key = (int(itemid), 1 if int(stack) else 0)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > keep:
            drop.append((int(row_id),))
    if drop:
        cur = conn.cursor()
        cur.executemany("DELETE FROM auction_house WHERE id = ?", drop)
        conn.commit()
        cur.close()
    return len(drop)


# ---- hiding gear above the level cap from the auction house menus ----
# The menus list every item whose item_basic.aH (auction category) is above 0. Hidden items get aH = 0; the original category is kept
# in the table ah_sim_hidden so "unhide" can put it back. Server updates may reload item_basic, so this is re-applied at every start.

def ensure_hidden_table(conn):
    execute(conn, "CREATE TABLE IF NOT EXISTS ah_sim_hidden (itemid INT PRIMARY KEY, ah INT NOT NULL)")


def items_to_hide(conn, settings):
    era = settings["era"]
    rows = query(conn, "SELECT b.itemid, b.aH, e.level, e.ilevel, e.su_level FROM item_basic b "
                       "JOIN item_equipment e ON e.itemId = b.itemid WHERE b.aH > 0")
    out = []
    for itemid, ah, level, ilevel, su_level in rows:
        itemid = int(itemid)
        if itemid in era["allow_ids"]:
            continue
        if int(level or 0) > era["equipment_max_level"] or int(ilevel or 0) > 0 or int(su_level or 0) > 0:
            out.append((itemid, int(ah)))
    out += [(itemid, ah) for itemid, ah in out_of_era_scrolls(conn, era).items() if ah > 0]    # newer or above-75 spell scrolls
    if era["deny_ids"]:                                                                          # items you named in era.deny_ids
        denied = set(int(i) for i in era["deny_ids"])
        listed = {i for i, _ in out}
        out += [(int(i), int(ah)) for i, ah in query(conn, "SELECT itemid, aH FROM item_basic WHERE aH > 0")
                if int(i) in denied and int(i) not in listed]
    return out


def remove_ineligible_listings(conn, items):
    """The simulator's unsold listings of items it no longer stocks (e.g. out-of-era scrolls) are taken down. Your own listings stay."""
    rows = query(conn, "SELECT DISTINCT itemid FROM auction_house WHERE seller = 0 AND sale = 0")
    gone = [int(r[0]) for r in rows if int(r[0]) not in items]
    if gone:
        cur = conn.cursor()
        for itemid in gone:
            cur.execute("DELETE FROM auction_house WHERE seller = 0 AND sale = 0 AND itemid = ?", (itemid,))
        conn.commit()
        cur.close()
    return len(gone)


def hide_above_level(conn, settings):
    if not settings["browse"]["hide_above_level"]:
        return 0
    ensure_hidden_table(conn)
    rows = items_to_hide(conn, settings)
    if not rows:
        return 0
    cur = conn.cursor()
    for itemid, ah in rows:
        cur.execute("DELETE FROM ah_sim_hidden WHERE itemid = ?", (itemid,))
        cur.execute("INSERT INTO ah_sim_hidden (itemid, ah) VALUES (?, ?)", (itemid, ah))
        cur.execute("UPDATE item_basic SET aH = 0 WHERE itemid = ?", (itemid,))
    conn.commit()
    cur.close()
    return len(rows)


def unhide(conn):
    ensure_hidden_table(conn)
    rows = query(conn, "SELECT itemid, ah FROM ah_sim_hidden")
    cur = conn.cursor()
    for itemid, ah in rows:
        cur.execute("UPDATE item_basic SET aH = ? WHERE itemid = ? AND aH = 0", (int(ah), int(itemid)))
    cur.execute("DELETE FROM ah_sim_hidden")
    conn.commit()
    cur.close()
    return len(rows)


def cycle(conn, settings, items, now=None, rng=None):
    now = int(now or time.time())
    bought = buy_player_listings(conn, settings, items, now, rng)
    housekeeping(conn, now)
    market_buys(conn, settings, now, rng)
    trim_history(conn, settings)
    added = stock(conn, settings, items, now, rng=rng)  # anything bought is back in stock within a minute
    return bought, added


def report(items, settings):
    sources = {}
    for it in items.values():
        sources[it.source] = sources.get(it.source, 0) + 1
    names = {"horizon": "HorizonXI market price", "estimate": "estimated from similar items' Horizon prices",
             "formula": "vendor-price formula (no price file)", "fallback": "fallback price (no vendor or market price)"}
    lines = [f"Items that would be stocked: {len(items)}"]
    for key, count in sorted(sources.items()):
        lines.append(f"  priced by {names.get(key, key)}: {count}")
    groups = {"equipment (armor, jewelry)": [], "weapons and ammo": [], "everything else": []}
    for it in items.values():
        key = "everything else" if not it.equipment else ("weapons and ammo" if it.itemid >= 16000 else "equipment (armor, jewelry)")
        groups[key].append(it)
    for key, group in groups.items():
        group.sort(key=lambda i: i.itemid)
        lines.append(f"\n{key}: {len(group)}")
        for it in group[-12:]:
            lines.append(f"  newest: #{it.itemid} {it.name}  (Lv {it.level})  price {it.fair}" + (f", stack {it.stack_fair}" if it.stack_fair else "") + f"  [{it.source}]")
        for it in group[:3]:
            lines.append(f"  oldest: #{it.itemid} {it.name}  price {it.fair}  [{it.source}]")
    total = sum(1 for it in items.values() if target_depth(it, settings["stock"]) > 0)
    lines.append(f"\nItems that get listings at the current stock settings: {total}")
    return "\n".join(lines)


def price_stamp(price_data):
    # (the price rate is part of it: a new rate restocks everything at the new prices)
    rate = price_rate()
    base = "none" if not price_data else f"{price_data.get('source')}@{price_data.get('fetched')}"
    return base if rate == 1.0 else f"{base}x{rate:g}"


def reprice_if_needed(conn, price_data, here=HERE):
    """When the prices change (first run of this version, or a new download), the simulator's old listings and history go,
    so everything is restocked at the new prices. Your own listings are never touched."""
    path = os.path.join(here, "ah_sim_state.json")
    state = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except ValueError:
            state = {}
    stamp = price_stamp(price_data)
    if state.get("prices") == stamp:
        return False
    execute(conn, "DELETE FROM auction_house WHERE seller = 0")
    state["prices"] = stamp
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    return True


def status(conn):
    total = query(conn, "SELECT COUNT(*) FROM auction_house WHERE seller = 0 AND sale = 0")[0][0]
    visible = query(conn, "SELECT COUNT(*) FROM auction_house WHERE seller = 0 AND sale = 0 AND buyer_name IS NULL")[0][0]
    items = query(conn, "SELECT COUNT(DISTINCT itemid) FROM auction_house WHERE seller = 0 AND sale = 0")[0][0]
    yours = query(conn, "SELECT COUNT(*) FROM auction_house WHERE seller <> 0 AND sale = 0")[0][0]
    lines = [f"Simulator listings for sale: {total} (over {items} different items)",
             f"  of those, visible to the game: {visible}",
             f"Your own listings waiting to sell: {yours}"]
    if total and visible < total:
        lines.append("Some listings are hidden from the game. Restart the simulator (STOP then PLAY) and they are repaired.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["report", "seed", "run", "tick", "clear", "status", "unhide", "prices"])
    args = parser.parse_args()
    settings = load_settings()
    if args.mode == "prices":
        data = fetch_prices(settings)
        print(f"Saved prices for {len(data['items'])} items from {data['source']}.")
        print("They are used the next time the simulator starts (STOP, then PLAY). Its old listings are replaced at the new prices.")
        return
    conn = connect()
    check_schema(conn)

    if args.mode == "status":
        print(status(conn))
        return

    if args.mode == "unhide":
        print(f"Put {unhide(conn)} items back in the auction house menus.")
        print("Set browse.hide_above_level to false in ah_sim.json, or they are hidden again the next time the simulator starts.")
        return

    if args.mode == "clear":
        execute(conn, "DELETE FROM auction_house WHERE seller = 0")
        print("Removed everything the simulator listed.")
        return

    price_data = load_price_file(settings)
    items = eligible_items(conn, settings, price_data)
    if args.mode == "report":
        text = report(items, settings)
        print(text)
        with open(os.path.join(HERE, "ah-report.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        return
    if args.mode == "seed":
        print(f"Listed {stock(conn, settings, items, int(time.time()))} items. {len(items)} items are eligible.")
        return
    if args.mode == "tick":
        print("bought %d, added %d" % cycle(conn, settings, items))
        return

    print(f"Auction house simulator running: {len(items)} items. Press Ctrl+C to stop.", flush=True)
    if price_data:
        print(f"Prices: HorizonXI market data from {time.strftime('%Y-%m-%d', time.localtime(price_data.get('fetched', 0)))}"
              f" ({sum(1 for i in items.values() if i.source == 'horizon')} items priced directly).", flush=True)
    else:
        print("Prices: vendor-price formula (run 'python ah_sim.py prices' to use HorizonXI prices).", flush=True)
    if reprice_if_needed(conn, price_data):
        print("Prices changed: replaced the simulator's old listings and history.", flush=True)
    fixed = repair_listings(conn)
    if fixed:
        print(f"Repaired {fixed} older listings so the game can see them.", flush=True)
    hidden = hide_above_level(conn, settings)
    if hidden:
        print(f"Hid {hidden} items (gear above level {settings['era']['equipment_max_level']}, newer spell scrolls) from the auction house menus.", flush=True)
    removed = remove_ineligible_listings(conn, items)
    if removed:
        print(f"Took down the simulator's listings of {removed} items that are not from the era.", flush=True)
    now = int(time.time())
    added = stock(conn, settings, items, now)
    print(f"Stocked {added} new listings.", flush=True)
    seeded = seed_history(conn, settings, items, now)
    if seeded:
        print(f"Added {seeded} past sales so items have a price history.", flush=True)
    trim_history(conn, settings)
    print(status(conn), flush=True)
    while True:
        time.sleep(settings["cycle_seconds"])
        try:
            bought, added = cycle(conn, settings, items)
            if bought or added:
                print(time.strftime("%H:%M:%S") + f"  bought {bought} of your listings, added {added}", flush=True)
        except Exception as exc:  # reconnect if the database restarted
            print("cycle failed:", exc, flush=True)
            try:
                conn = connect()
            except Exception:
                pass


if __name__ == "__main__":
    main()
