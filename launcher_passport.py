"""Character passports for co-op (no GUI and no network here, so it can be tested on its own).

A passport is a copy of one character's rows from the game database, packed into a small zip. Co-op uses it like this:

  home world                               friend's world (the host)
  ----------                               -------------------------
  depart()   locks the character and  -->  import_guest()   the character arrives on a guest account
             makes the passport
                                           export_guest()   a checkpoint while it plays (kept by the visitor), or the
  come_home() puts the returned rows  <--                   final passport when it leaves
             in and unlocks it
  take_back() unlocks without the host (from the newest checkpoint, or as it was before the visit)

Rules that keep it safe:
  * Only the tables and columns listed here travel, and only when both worlds have exactly the same columns.
  * Table and column names always come from this file and the local database, never from the passport.
  * While a character is away its home copy sits on a locked account, so it cannot be played in two places.
  * A return is only accepted for the visit it belongs to (the nonce made at departure), and only once.
  * Linkshell items and bot settings belong to a world: they stay home and never travel.
  * Squad mates travel with their character (levels, jobs, outfits, the shared gear collection and their settings).
    Each world numbers mates its own way, so they are matched by their slot (1-7) and the settings that carry a
    mate's number (SQUAD_AI_<n> and the like) are renumbered on the way in.

Works with the `mariadb` Python package ('?' placeholders). Every function takes an open connection with autocommit OFF
and finishes with a commit or a rollback, so no transaction is ever left open.
"""
import base64
import datetime
import decimal
import hashlib
import io
import json
import math
import os
import re
import secrets
import time
import zipfile

FORMAT = 2                           # 2: squad mates travel too
OLD_FORMAT = 1                       # the first co-op build: squads stayed home. Its backups, and the returns of
                                     # visits that began with it, are still read (as they were written: no squad).
BOT_ACCOUNT_BASE = 21000000          # bot players live on accounts from here up (bots.cpp)
BOT_CHAR_BASE = 16000000             # ...and their characters from here up
AWAY_LOGIN = "coopaway"              # the locked account that holds characters who are visiting another world
LS_ITEMS = (513, 514, 515)           # linkshell, pearlsack, linkpearl: they point at a linkshell of one world
LINK_SLOTS = (16, 17)                # char_equip slots of the two worn linkshells
WORLD_VAR_PREFIXES = ("[Bots]", "[Bot]", "COOP_", "[YELL]")     # character variables that belong to one world
# (2026-11-25, the user) On the hub a visitor plays at the rates of its home world. The visitor's own rates travel as
# character variables "[HR]<key>" = rate x 1000 + 1 (0 = not sent), refreshed on every trip. Only the hub reads them
# (server: src/map/utils/hardcoreutils.h rate, modules/custom/late/hardcore.lua H.HUB_KEYS, keep the lists in step);
# nothing about combat or the world itself travels.
HUB_RATE_PREFIX = "[HR]"
HUB_RATE_KEYS = ("map.EXP_RATE", "map.DROP_RATE_MULTIPLIER", "map.MOB_GIL_MULTIPLIER", "map.ALL_MOBS_GIL_BONUS",
                  "map.SKILLUP_CHANCE_MULTIPLIER", "map.BLUE_LEARN_MULTIPLIER", "map.CRAFT_CHANCE_MULTIPLIER",
                  "map.CRAFT_HQ_CHANCE_MULTIPLIER", "map.FISHING_SKILL_MULTIPLIER",
                  "main.GIL_RATE", "main.TABS_RATE", "main.BOOK_EXP_RATE", "main.CASKET_DROP_RATE", "main.DIG_SKILL_RATE",
                  "main.TM_CARD_DROP_RATE", "main.TM_CASKET_CARD_RATE", "main.TM_GIL_RATE", "main.TM_PRICE_RATE")
HUB_RATE_MAX = 1_000_000                # 1,000,000x: no cap on purpose (the user), only a bound that fits the column


def hub_rate_vars(rates):
    """{varname: stored value} for the rates a visitor takes to the hub. A missing or unreadable key is left out."""
    out = {}
    for key in HUB_RATE_KEYS:
        try:
            value = float((rates or {}).get(key))
        except (TypeError, ValueError):
            continue
        if value != value or value < 0:     # NaN or negative: not a rate
            continue
        out[HUB_RATE_PREFIX + key] = int(round(min(value, HUB_RATE_MAX) * 1000)) + 1
    return out


def _with_hub_rates(tables, charid, rates):
    """The char_vars block with the old [HR] rows replaced by this trip's. Unchanged when rates is None."""
    block = tables.get("char_vars")
    if rates is None or not block or "varname" not in block["cols"]:
        return tables
    cols = block["cols"]
    name_at = cols.index("varname")
    def _name(cell):
        value = _dec(cell)
        return value.decode("utf-8", "replace") if isinstance(value, (bytes, bytearray)) else str(value)
    rows = [r for r in block["rows"] if not _name(r[name_at]).startswith(HUB_RATE_PREFIX)]
    for name, value in sorted(hub_rate_vars(rates).items()):
        row = []
        for col in cols:
            row.append(_enc(charid if col == "charid" else name if col == "varname" else value if col == "value" else 0))
        rows.append(row)
    block["rows"] = rows
    return tables

GAOL = 131                           # Mordion Gaol: without GM rights a character there can do nothing (jail)
MAX_MATES = 12                # squad mates one character may bring (the game keeps seven)
SQUAD_TABLES = ("squad_mate", "squad_job", "squad_equip", "squad_unlock")
MATE_VAR = re.compile(r"^(SQUAD_[A-Z_]*_)(\d+)((?:_\d+)?)$")                # a mate's own setting: SQUAD_AI_<mate id>, SQUAD_LOOK_<mate id>...
GUEST_VAR = "COOP_GUEST"
MAX_PASSPORT_BYTES = 64 * 1024 * 1024
MAX_ROWS = 20000
# open worlds (anyone may come in): passports of strangers are read with tighter limits and checked value by value
OPEN_PASSPORT_BYTES = 8 * 1024 * 1024
OPEN_ROWS = {"char_inventory": 1500, "char_spells": 1500, "char_vars": 5000, "char_effects": 200}
LOCKER_DAYS = 90                     # a visitor's place in an open world is kept this long after its last visit
ALIAS = re.compile(r"[A-Z][a-z]{2,14}")           # a visiting name, written the way the game writes names
INT_BITS = {"tinyint": 8, "smallint": 16, "mediumint": 24, "int": 32, "bigint": 64}
TEXT_TYPES = ("varchar", "char", "text", "tinytext", "mediumtext", "longtext")
BLOB_TYPES = ("blob", "tinyblob", "mediumblob", "longblob", "varbinary", "binary")
MAX_LEVEL = 99
MAX_CONTAINER, MAX_SLOT, MAX_EQUIP_SLOT = 17, 80, 17

CHARS_SKIP = ("charid", "accid", "original_accid", "gmlevel")
ONE_ROW = ("char_stats", "char_jobs", "char_exp", "char_look", "char_profile", "char_points", "char_storage",
           "char_style", "char_unlocks", "char_pet", "char_history")
MANY_ROWS = ("char_inventory", "char_equip", "char_equip_saved", "char_skills", "char_spells", "char_merit",
             "char_vars", "char_effects", "char_recast", "char_job_points")
TABLES = ("chars",) + ONE_ROW + MANY_ROWS
JOBS = ["", "WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN",
        "BLU", "COR", "PUP", "DNC", "SCH", "GEO", "RUN"]
# where a kept linkshell item may go when its old slot was filled during the visit: char_inventory.location -> the
# char_storage column with that container's size
CONTAINERS = ((0, "inventory"), (1, "safe"), (5, "satchel"), (6, "sack"), (7, "case"))

DDL = (
    "CREATE TABLE IF NOT EXISTS `coop_meta` (`k` VARCHAR(32) NOT NULL, `v` TEXT NOT NULL, PRIMARY KEY (`k`)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci",
    "CREATE TABLE IF NOT EXISTS `coop_away` (`charid` INT UNSIGNED NOT NULL, `accid` INT UNSIGNED NOT NULL, "
    "`nonce` VARCHAR(64) NOT NULL, `generation` INT UNSIGNED NOT NULL DEFAULT 1, `state` VARCHAR(16) NOT NULL DEFAULT 'away', "
    "`host` TEXT NOT NULL, `since` DATETIME NOT NULL, `updated` DATETIME NOT NULL, `squad` TINYINT NOT NULL DEFAULT 0, "
    "PRIMARY KEY (`charid`)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci",
    "CREATE TABLE IF NOT EXISTS `coop_guest` (`guest_id` VARCHAR(32) NOT NULL, `gkey` VARCHAR(64) NOT NULL, "
    "`home_world` VARCHAR(64) NOT NULL, `home_charid` INT UNSIGNED NOT NULL, `name` VARCHAR(15) NOT NULL, "
    "`charid` INT UNSIGNED NOT NULL, `accid` INT UNSIGNED NOT NULL, `login` VARCHAR(16) NOT NULL, "
    "`state` VARCHAR(16) NOT NULL DEFAULT 'active', `nonce` VARCHAR(64) NOT NULL, `generation` INT UNSIGNED NOT NULL DEFAULT 1, "
    "`arrived` DATETIME NOT NULL, `updated` DATETIME NOT NULL, `final_file` TEXT NULL, `info` TEXT NULL, "
    "`owner` VARCHAR(64) NOT NULL DEFAULT '', `alias` VARCHAR(15) NULL, `kept` TINYINT NOT NULL DEFAULT 0, "
    "PRIMARY KEY (`guest_id`), UNIQUE KEY `home` (`owner`, `home_world`, `home_charid`)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci",
    "CREATE TABLE IF NOT EXISTS `coop_visitor` (`vid` VARCHAR(64) NOT NULL, `vkey` VARCHAR(64) NOT NULL, "
    "`first_seen` DATETIME NOT NULL, `last_seen` DATETIME NOT NULL, `address` VARCHAR(64) NOT NULL DEFAULT '', "
    "PRIMARY KEY (`vid`)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci",
    "CREATE TABLE IF NOT EXISTS `coop_ban` (`kind` VARCHAR(8) NOT NULL, `value` VARCHAR(64) NOT NULL, "
    "`reason` VARCHAR(200) NOT NULL DEFAULT '', `since` DATETIME NOT NULL, PRIMARY KEY (`kind`, `value`)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci",
)


class PassportError(Exception):
    """Something about a passport or a character that the player can be told as it is."""


class NameTaken(PassportError):
    """A character of that name already lives in the world (an open world lets the visitor pick a visiting name)."""


class BadPassport(PassportError):
    """A passport from a stranger's world holds something this world must not take in."""


# ----- small database helpers -----
def connect(cfg):
    """A connection of its own for one passport job (autocommit off; close it when the job is done)."""
    import mariadb

    return mariadb.connect(host=cfg.get("db_host", "127.0.0.1"), port=int(cfg.get("db_port", 3306)), user=cfg["db_user"],
                           password=cfg["db_pass"], database=cfg["db_name"], autocommit=False)


def _all(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def _one(cur, sql, params=()):
    rows = _all(cur, sql, params)
    return rows[0] if rows else None


def _now():
    return datetime.datetime.now().replace(microsecond=0)


def ensure_tables(conn):
    """The three small co-op tables (made the first time co-op is used; creating a table ends any open transaction)."""
    cur = conn.cursor()
    for statement in DDL:
        cur.execute(statement)
    if "squad" not in table_columns(cur, "coop_away"):     # (a table made by the first co-op build)
        cur.execute("ALTER TABLE `coop_away` ADD COLUMN `squad` TINYINT NOT NULL DEFAULT 0")
    if "owner" not in table_columns(cur, "coop_guest"):    # (a table made before open worlds)
        cur.execute("ALTER TABLE `coop_guest` ADD COLUMN `owner` VARCHAR(64) NOT NULL DEFAULT '', ADD COLUMN `alias` VARCHAR(15) NULL, "
                    "ADD COLUMN `kept` TINYINT NOT NULL DEFAULT 0, DROP INDEX `home`, "
                    "ADD UNIQUE KEY `home` (`owner`, `home_world`, `home_charid`)")
    conn.commit()
    cur.close()


def table_columns(cur, table):
    rows = _all(cur, "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ? "
                     "ORDER BY ordinal_position", (table,))
    return [r[0] for r in rows]


def local_layout(cur):
    """{table: [columns that travel]} for this database: the listed tables that exist, without the id columns."""
    layout = {}
    for table in TABLES:
        cols = table_columns(cur, table)
        if not cols:
            continue
        skip = CHARS_SKIP if table == "chars" else ("charid",)
        layout[table] = [c for c in cols if c not in skip]
    if "chars" not in layout:
        raise PassportError("This database has no characters table.")
    return layout


def squad_layout(cur):
    """{table: [columns that travel]} for the squad tables (charid is filled in on arrival). {} when a world has none."""
    layout = {}
    for table in SQUAD_TABLES:
        cols = table_columns(cur, table)
        if not cols:
            return {}
        layout[table] = [c for c in cols if c != "charid"]
    need = {"squad_mate": ("id", "slot", "name"), "squad_job": ("squad_id",), "squad_equip": ("squad_id",)}
    if any(c not in layout[t] for t, cs in need.items() for c in cs):
        return {}
    return layout


def layout_signature(layout, squad=None, fmt=FORMAT):
    """One short text for 'these two worlds store characters (and their squads) the same way'."""
    if fmt == OLD_FORMAT:                  # (as the first co-op build wrote it: the character tables only)
        text = json.dumps(layout, sort_keys=True, separators=(",", ":"))
    else:
        text = json.dumps([layout, squad or {}], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def schema_signature(conn):
    cur = conn.cursor()
    try:
        return layout_signature(local_layout(cur), squad_layout(cur))
    finally:
        cur.close()
        conn.rollback()


def world_identity(conn, default_name=None):
    """This world's id (made once, kept in the database) and name."""
    ensure_tables(conn)
    cur = conn.cursor()
    row = _one(cur, "SELECT v FROM coop_meta WHERE k = 'world_id'")
    if row is None:
        cur.execute("INSERT INTO coop_meta (k, v) VALUES ('world_id', ?)", (secrets.token_hex(12),))
        row = _one(cur, "SELECT v FROM coop_meta WHERE k = 'world_id'")
    name = _one(cur, "SELECT v FROM coop_meta WHERE k = 'world_name'")
    if name is None and default_name:
        cur.execute("INSERT INTO coop_meta (k, v) VALUES ('world_name', ?)", (clean_world_name(default_name),))
        name = (clean_world_name(default_name),)
    conn.commit()
    cur.close()
    return {"id": row[0], "name": name[0] if name else "A world"}


def clean_world_name(name):
    text = re.sub(r"[^\w '\-.!]", "", str(name or ""), flags=re.UNICODE).strip()[:32]
    return text or "A world"


def set_world_name(conn, name):
    ensure_tables(conn)
    cur = conn.cursor()
    cur.execute("REPLACE INTO coop_meta (k, v) VALUES ('world_name', ?)", (clean_world_name(name),))
    conn.commit()
    cur.close()


# ----- values: database <-> JSON -----
def _enc(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"b": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, datetime.datetime):
        return {"t": value.strftime("%Y-%m-%d %H:%M:%S")}
    if isinstance(value, datetime.date):
        return {"d": value.isoformat()}
    if isinstance(value, datetime.timedelta):
        return {"s": value.total_seconds()}
    if isinstance(value, decimal.Decimal):
        return {"n": str(value)}
    return value


def _dec(value):
    if isinstance(value, dict):
        if "b" in value:
            return base64.b64decode(value["b"])
        if "t" in value:
            return value["t"]
        if "d" in value:
            return value["d"]
        if "s" in value:
            return datetime.timedelta(seconds=float(value["s"]))
        if "n" in value:
            return decimal.Decimal(value["n"])
        raise PassportError("The passport holds a value this version does not know.")
    if value is None or isinstance(value, (int, float, str)):
        return value
    raise PassportError("The passport holds a value this version does not know.")


def pack(passport):
    """The passport as the bytes of a small zip (passport.json inside)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("passport.json", json.dumps(passport, separators=(",", ":"), ensure_ascii=False))
    return buffer.getvalue()


def unpack(data, limit=MAX_PASSPORT_BYTES):
    try:
        if len(data) > limit:
            raise PassportError("That passport is too large to be real.")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("passport.json")
            if info.file_size > limit:
                raise PassportError("That passport is too large to be real.")
            with archive.open(info) as handle:          # (never more than the limit, whatever the zip claims)
                raw = handle.read(limit + 1)
            if len(raw) > limit:
                raise PassportError("That passport is too large to be real.")
            passport = json.loads(raw.decode("utf-8"))
    except PassportError:
        raise
    except Exception:
        raise PassportError("That file is not a character passport (or it is damaged).")
    if not isinstance(passport, dict) or passport.get("format") not in (FORMAT, OLD_FORMAT) or not isinstance(passport.get("tables"), dict):
        raise PassportError("That passport was made by another version of XI: Forever Offline.")
    name = passport.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z]{3,15}", name):
        raise PassportError("That passport has no valid character name.")
    return passport


# ----- reading a character -----
def _is_world_var(name):
    return str(name).startswith(WORLD_VAR_PREFIXES)


def _read(cur, layout, charid, full=False):
    """{table: {"cols": [...], "rows": [[...]]}} for one character. full=True keeps what never travels too (a backup)."""
    tables = {}
    for table, cols in layout.items():
        names = ", ".join(f"`{c}`" for c in cols)
        rows = [list(r) for r in _all(cur, f"SELECT {names} FROM `{table}` WHERE `charid` = ?", (charid,))]
        if not full:
            if table == "char_inventory" and "itemId" in cols:
                i = cols.index("itemId")
                rows = [r for r in rows if r[i] not in LS_ITEMS]
            elif table == "char_equip" and "equipslotid" in cols:
                i = cols.index("equipslotid")
                rows = [r for r in rows if r[i] not in LINK_SLOTS]
            elif table == "char_vars" and "varname" in cols:
                i = cols.index("varname")
                rows = [r for r in rows if not _is_world_var(r[i])]
        tables[table] = {"cols": cols, "rows": [[_enc(v) for v in r] for r in rows]}
    if len(tables["chars"]["rows"]) != 1:
        raise PassportError("That character does not exist here.")
    return tables


def _read_squad(cur, squad, charid):
    """The character's squad: {table: {"cols", "rows"}} with this world's mate ids in it (they are renumbered on arrival)."""
    if not squad:
        return None
    out = {}
    for table, cols in squad.items():
        names = ", ".join(f"`{c}`" for c in cols)
        where = "`charid` = ?" if table in ("squad_mate", "squad_unlock") else "`squad_id` IN (SELECT id FROM squad_mate WHERE charid = ?)"
        rows = _all(cur, f"SELECT {names} FROM `{table}` WHERE {where}", (charid,))
        out[table] = {"cols": cols, "rows": [[_enc(v) for v in r] for r in rows]}
    return out


def squad_summary(squad):
    """[{slot, name, job, level}] of a passport's squad block (each mate's main job and its level)."""
    if not squad:
        return []
    mates, jobs = squad["squad_mate"], squad["squad_job"]
    mi = {c: mates["cols"].index(c) for c in mates["cols"]}
    ji = {c: jobs["cols"].index(c) for c in jobs["cols"]}
    levels = {}
    if all(c in ji for c in ("squad_id", "job", "level")):
        levels = {(r[ji["squad_id"]], r[ji["job"]]): r[ji["level"]] for r in jobs["rows"]}
    out = []
    for row in sorted(mates["rows"], key=lambda r: r[mi["slot"]]):
        job = row[mi["mjob"]] if "mjob" in mi else 0
        out.append({"slot": int(row[mi["slot"]]), "name": row[mi["name"]], "job": JOBS[job] if isinstance(job, int) and 0 <= job < len(JOBS) else "?",
                    "level": int(levels.get((row[mi["id"]], job), 1) or 1)})
    return out


def _cell(tables, table, column, default=None):
    block = tables.get(table)
    if not block or not block["rows"] or column not in block["cols"]:
        return default
    return block["rows"][0][block["cols"].index(column)]


def summary(tables):
    """The few numbers shown to the player: job, level, gil, how many item stacks."""
    job = _cell(tables, "char_stats", "mjob", 0) or 0
    gil, items = 0, 0
    inv = tables.get("char_inventory")
    if inv and "itemId" in inv["cols"]:
        ii, qi = inv["cols"].index("itemId"), inv["cols"].index("quantity")
        for row in inv["rows"]:
            if row[ii] == 65535:
                gil += int(row[qi] or 0)
            else:
                items += 1
    return {"job": JOBS[job] if 0 <= job < len(JOBS) else "?", "level": int(_cell(tables, "char_stats", "mlvl", 0) or 0),
            "gil": gil, "items": items, "playtime": int(_cell(tables, "chars", "playtime", 0) or 0)}


def is_online(cur, charid):
    return _one(cur, "SELECT 1 FROM accounts_sessions WHERE charid = ? LIMIT 1", (charid,)) is not None


def find_character(conn, name):
    """(charid, accid, charname) of a character by name, or None."""
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT charid, accid, charname FROM chars WHERE charname = ? LIMIT 1", (name,))
        return (int(row[0]), int(row[1]), row[2]) if row else None
    finally:
        cur.close()
        conn.rollback()


def _make(kind, tables, name, world, home, nonce, generation, signature, versions=None, stamps=None, squad=None):
    look = summary(tables)
    look["squad"] = squad_summary(squad)
    return {"format": FORMAT, "kind": kind, "name": name, "world": world, "home": home, "nonce": nonce,
            "generation": int(generation), "schema": signature, "made": int(time.time()), "versions": versions or {},
            "stamps": list(stamps or []), "summary": look, "tables": tables, "squad": squad}


# ----- writing a character -----
def _check_squad(passport, squad):
    """The passport's squad block must be exactly the squad tables and columns this world has."""
    theirs = passport.get("squad")
    if not squad:
        if theirs:
            raise PassportError("The two worlds are on different versions. Update both first.")
        return
    if not isinstance(theirs, dict) or set(theirs) != set(squad):
        raise PassportError("The two worlds are on different versions. Update both first.")
    for table, cols in squad.items():
        block = theirs[table]
        if not isinstance(block, dict) or block.get("cols") != cols or not isinstance(block.get("rows"), list):
            raise PassportError("The two worlds are on different versions. Update both first.")
        if len(block["rows"]) > MAX_ROWS or any(not isinstance(r, list) or len(r) != len(cols) for r in block["rows"]):
            raise PassportError("That passport is damaged.")
    mates = theirs["squad_mate"]
    slots = [r[mates["cols"].index("slot")] for r in mates["rows"]]
    ids = [r[mates["cols"].index("id")] for r in mates["rows"]]
    names = [r[mates["cols"].index("name")] for r in mates["rows"]]
    if len(mates["rows"]) > MAX_MATES or len(set(slots)) != len(slots) or len(set(ids)) != len(ids) or \
            any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in slots + ids) or any(v > 255 for v in slots):
        raise PassportError("That passport is damaged.")
    if any(not isinstance(n, str) or not n.isalpha() or len(n) > 15 for n in names):
        raise PassportError("A squad mate in that passport has a name this world cannot use (letters only, 15 at most).")


def _check_tables(passport, layout, squad=None):
    """The passport's tables must be exactly the tables and columns this world has (names are taken from `layout`)."""
    theirs = passport["tables"]
    fmt = passport.get("format")
    if fmt == OLD_FORMAT:                   # written before squads travelled: there is no squad in it
        if passport.get("squad"):
            raise PassportError("That passport is damaged.")
    else:
        _check_squad(passport, squad)
    if passport.get("schema") != layout_signature(layout, squad, fmt) or set(theirs) != set(layout):
        raise PassportError("The two worlds are on different versions (their characters are stored differently). "
                            "Update both to the same version of XI: Forever Offline first.")
    for table, cols in layout.items():
        block = theirs[table]
        if not isinstance(block, dict) or block.get("cols") != cols or not isinstance(block.get("rows"), list):
            raise PassportError("The two worlds are on different versions. Update both first.")
        if len(block["rows"]) > MAX_ROWS or any(not isinstance(r, list) or len(r) != len(cols) for r in block["rows"]):
            raise PassportError("That passport is damaged.")
    if len(theirs["chars"]["rows"]) != 1:
        raise PassportError("That passport is damaged.")


def _insert(cur, table, cols, rows, charid):
    if not rows:
        return
    names = ", ".join(f"`{c}`" for c in cols)
    marks = ", ".join("?" for _ in cols)
    statement = f"INSERT INTO `{table}` (`charid`, {names}) VALUES (?, {marks})"
    for row in rows:
        cur.execute(statement, tuple([charid] + [_dec(v) for v in row]))


def _mate_var(name, mates):
    """A variable's name in this world: a mate's own setting follows its mate's new number (None = that mate is gone)."""
    found = MATE_VAR.match(name)
    if not found:
        return name
    new = (mates or {}).get(int(found.group(2)))
    # (group 3: the job of a per-job setting, SQUAD_WSC_<mate id>_<job>, the Gambits weapon skill settings)
    return None if new is None else found.group(1) + str(new) + found.group(3)


def _travel_rows(table, block, mates=None):
    """A passport's rows for one table, minus anything that must never arrive from another world. `mates` is
    {a mate's number in the passport: its number here}."""
    cols, rows = block["cols"], block["rows"]
    if table == "char_inventory" and "itemId" in cols:
        i = cols.index("itemId")
        rows = [r for r in rows if r[i] not in LS_ITEMS]
    elif table == "char_equip" and "equipslotid" in cols:
        i = cols.index("equipslotid")
        rows = [r for r in rows if r[i] not in LINK_SLOTS]
    elif table == "char_vars" and "varname" in cols:
        i = cols.index("varname")
        out, seen = [], set()
        for row in rows:
            name = _mate_var(row[i], mates) if isinstance(row[i], str) and not _is_world_var(row[i]) else None
            if name is not None and name not in seen:
                seen.add(name)
                out.append(row[:i] + [name] + row[i + 1:])
        rows = out
    return rows


def _put_squad(cur, squad, charid, theirs, keep_ids):
    """Puts a passport's squad in place of the character's squad here. Returns {a mate's number in the passport: here}.
    keep_ids=True (coming home, restoring): a mate in the same slot keeps the number it has here, so nothing else that
    knows it by number changes; mates whose slot is not in the passport were dismissed for good while away."""
    if not squad or not theirs:
        return {}
    mates = theirs["squad_mate"]
    mcols = mates["cols"]
    idi, sloti = mcols.index("id"), mcols.index("slot")
    here = {int(r[1]): int(r[0]) for r in _all(cur, "SELECT id, slot FROM squad_mate WHERE charid = ?", (charid,))}
    coming = {int(r[sloti]) for r in mates["rows"]}
    for slot, mate_id in here.items():
        if not keep_ids or slot not in coming:
            for table in ("squad_equip", "squad_job"):
                cur.execute(f"DELETE FROM `{table}` WHERE squad_id = ?", (mate_id,))
            cur.execute("DELETE FROM squad_mate WHERE id = ?", (mate_id,))
    mapping = {}
    plain = [c for c in mcols if c not in ("id",)]
    for row in sorted(mates["rows"], key=lambda r: r[sloti]):
        values = {c: _dec(v) for c, v in zip(mcols, row)}
        slot = int(values["slot"])
        if keep_ids and slot in here:
            sets = ", ".join(f"`{c}` = ?" for c in plain if c != "slot")
            cur.execute(f"UPDATE squad_mate SET {sets} WHERE id = ?", tuple(values[c] for c in plain if c != "slot") + (here[slot],))
            mapping[int(row[idi])] = here[slot]
        else:
            names = ", ".join(f"`{c}`" for c in plain)
            cur.execute(f"INSERT INTO squad_mate (`charid`, {names}) VALUES (?, {', '.join('?' for _ in plain)})",
                        tuple([charid] + [values[c] for c in plain]))
            mapping[int(row[idi])] = int(cur.lastrowid)
    for table in ("squad_job", "squad_equip"):
        cols = theirs[table]["cols"]
        si = cols.index("squad_id")
        for mate_id in mapping.values():
            cur.execute(f"DELETE FROM `{table}` WHERE squad_id = ?", (mate_id,))
        names = ", ".join(f"`{c}`" for c in cols)
        statement = f"INSERT INTO `{table}` ({names}) VALUES ({', '.join('?' for _ in cols)})"
        for row in theirs[table]["rows"]:
            if row[si] in mapping:
                cur.execute(statement, tuple(mapping[row[si]] if i == si else _dec(v) for i, v in enumerate(row)))
    cols = theirs["squad_unlock"]["cols"]
    cur.execute("DELETE FROM squad_unlock WHERE charid = ?", (charid,))
    if cols:
        names = ", ".join(f"`{c}`" for c in cols)
        statement = f"INSERT IGNORE INTO squad_unlock (`charid`, {names}) VALUES (?, {', '.join('?' for _ in cols)})"
        for row in theirs["squad_unlock"]["rows"]:
            cur.execute(statement, tuple([charid] + [_dec(v) for v in row]))
    return mapping


def _free_id(cur, table, column, start, limit, avoid=()):
    row = _one(cur, f"SELECT COALESCE(MAX(`{column}`), 0) FROM `{table}` WHERE `{column}` < ?", (limit,))
    candidate = max(start, int(row[0]) + 1)
    while candidate < limit and (candidate in avoid or _one(cur, f"SELECT 1 FROM `{table}` WHERE `{column}` = ?", (candidate,))):
        candidate += 1
    if candidate >= limit:
        raise PassportError("This world has no room for another visitor.")
    return candidate


def _make_room_for_name(cur, name):
    """A bot may be using the visitor's name: the bot gets another one. A real character with it stops the visit."""
    row = _one(cur, "SELECT charid, accid FROM chars WHERE charname = ? LIMIT 1", (name,))
    if row is None:
        return None
    if int(row[1]) < BOT_ACCOUNT_BASE:
        raise NameTaken(f"A character named {name} already lives in this world, so {name} cannot visit it.")
    for ending in ("a", "o", "e", "i", "u", "an", "el", "is", "or", "us"):
        other = (name[:15 - len(ending)] + ending)
        if not _one(cur, "SELECT 1 FROM chars WHERE charname = ? LIMIT 1", (other,)):
            cur.execute("UPDATE chars SET charname = ? WHERE charid = ?", (other, int(row[0])))
            return other
    raise PassportError(f"A bot player named {name} is in the way and could not be renamed.")


# ----- home world: leaving, coming back, taking back -----
def away_account(cur):
    """The id of the locked account that holds characters who are away (made the first time)."""
    row = _one(cur, "SELECT id FROM accounts WHERE login = ? LIMIT 1", (AWAY_LOGIN,))
    if row:
        return int(row[0])
    accid = 900
    while _one(cur, "SELECT 1 FROM accounts WHERE id = ?", (accid,)):
        accid += 1
        if accid >= 1000:
            raise PassportError("Could not make the account that keeps travelling characters safe.")
    cur.execute("INSERT INTO accounts (id, login, password, timecreate, timelastmodify, status, priv) "
                "VALUES (?, ?, ?, NOW(), NOW(), 0, 1)", (accid, AWAY_LOGIN, "!" + secrets.token_hex(24)))
    return accid


def own_character_ids(conn):
    """The ids of this world's own (not bot, not visiting) characters."""
    cur = conn.cursor()
    try:
        return [int(r[0]) for r in _all(cur, "SELECT charid FROM chars WHERE accid < ? ORDER BY charid LIMIT 200", (BOT_ACCOUNT_BASE,))]
    finally:
        cur.close()
        conn.rollback()


def home_characters(conn):
    """[(charid, name)] of the characters that are at home here and could travel (no bots, visitors or absentees)."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT c.charid, c.charname FROM chars c JOIN accounts a ON a.id = c.accid "
                         "WHERE c.accid < ? AND a.login <> ? AND c.charid NOT IN (SELECT charid FROM coop_guest WHERE state <> 'gone') "
                         "ORDER BY c.charname", (BOT_ACCOUNT_BASE, AWAY_LOGIN))
        return [(int(r[0]), r[1]) for r in rows]
    finally:
        cur.close()
        conn.rollback()


def away_list(conn):
    """Characters of this world that are visiting another one: [{charid, name, nonce, generation, host, since}]."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT a.charid, c.charname, a.nonce, a.generation, a.host, a.since, a.state FROM coop_away a "
                         "JOIN chars c ON c.charid = a.charid WHERE a.state = 'away' ORDER BY a.since")
        return [{"charid": int(r[0]), "name": r[1], "nonce": r[2], "generation": int(r[3]), "host": json.loads(r[4] or "{}"),
                 "since": str(r[5])} for r in rows]
    finally:
        cur.close()
        conn.rollback()


def depart(conn, charid, host, versions=None, travel_rates=None):
    """Locks a character at home and returns (passport bytes, nonce). `host` is whatever the caller wants remembered about
    where it went (address, world name...). Nothing changes if anything fails."""
    ensure_tables(conn)
    world = world_identity(conn)
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT accid, charname FROM chars WHERE charid = ? FOR UPDATE", (charid,))
        if row is None:
            raise PassportError("That character does not exist here.")
        accid, name = int(row[0]), row[1]
        if accid >= BOT_ACCOUNT_BASE:
            raise PassportError("Bot players cannot travel.")
        if _one(cur, "SELECT 1 FROM coop_away WHERE charid = ? AND state = 'away'", (charid,)):
            raise PassportError(f"{name} is already visiting another world.")
        if _one(cur, "SELECT 1 FROM coop_guest WHERE charid = ? AND state <> 'gone'", (charid,)):
            raise PassportError(f"{name} is a visitor here. Visitors go home before they travel on.")
        if is_online(cur, charid):
            raise PassportError(f"{name} is in the game right now. Log out first.")
        layout, squad = local_layout(cur), squad_layout(cur)
        tables = _with_hub_rates(_read(cur, layout, charid), charid, travel_rates)   # (the hub plays you at these)
        nonce = secrets.token_hex(16)
        passport = _make("visit", tables, name, world, {"world": world["id"], "charid": charid}, nonce, 1,
                         layout_signature(layout, squad), versions, squad=_read_squad(cur, squad, charid))
        cur.execute("REPLACE INTO coop_away (charid, accid, nonce, generation, state, host, since, updated, squad) "
                    "VALUES (?, ?, ?, 1, 'away', ?, ?, ?, ?)",
                    (charid, accid, nonce, json.dumps(host or {}), _now(), _now(), 1 if squad else 0))
        cur.execute("UPDATE chars SET accid = ? WHERE charid = ?", (away_account(cur), charid))
        conn.commit()
        return pack(passport), nonce
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def update_away(conn, charid, host=None, generation=None):
    """Remembers more about a visit (what the host answered, the newest checkpoint's number)."""
    cur = conn.cursor()
    try:
        if host is not None:
            cur.execute("UPDATE coop_away SET host = ?, updated = ? WHERE charid = ? AND state = 'away'",
                        (json.dumps(host), _now(), charid))
        if generation is not None:
            cur.execute("UPDATE coop_away SET generation = GREATEST(generation, ?), updated = ? WHERE charid = ? AND state = 'away'",
                        (int(generation), _now(), charid))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _put_back_kept(cur, charid, kept_items, kept_links, tables):
    """Linkshell items stayed home. Their slots may have been filled during the visit: each goes back to its own slot
    when it is free, else to the first free slot of a bag. Returns the items that found no room at all."""
    if not kept_items:
        return []
    used = {(int(r[0]), int(r[1])) for r in _all(cur, "SELECT location, slot FROM char_inventory WHERE charid = ?", (charid,))}
    sizes = {location: max(0, min(80, int(_cell(tables, "char_storage", column, 0) or 0))) for location, column in CONTAINERS}
    homeless = []
    for cols, row in kept_items:
        location, slot = int(row[cols.index("location")]), int(row[cols.index("slot")])
        target = None
        if (location, slot) not in used:
            target = (location, slot)
        else:
            for where in [location] + [loc for loc, _c in CONTAINERS if loc != location]:
                for candidate in range(1, sizes.get(where, 0) + 1):
                    if (where, candidate) not in used:
                        target = (where, candidate)
                        break
                if target:
                    break
        if target is None:
            homeless.append(row[cols.index("itemId")])
            continue
        used.add(target)
        new = list(row)
        new[cols.index("location")], new[cols.index("slot")] = target
        names = ", ".join(f"`{c}`" for c in cols)
        cur.execute(f"INSERT INTO `char_inventory` (`charid`, {names}) VALUES (?, {', '.join('?' for _ in cols)})",
                    tuple([charid] + new))
        if target == (location, slot):          # still where the worn-linkshell row points
            for ecols, erow in kept_links:
                if int(erow[ecols.index("slotid")]) == slot and int(erow[ecols.index("containerid")]) == location:
                    enames = ", ".join(f"`{c}`" for c in ecols)
                    cur.execute(f"INSERT INTO `char_equip` (`charid`, {enames}) VALUES (?, {', '.join('?' for _ in ecols)})",
                                tuple([charid] + list(erow)))
    return homeless


def _replace_rows(cur, layout, charid, tables, accid=None, mates=None, squad_home=False):
    """Puts a passport's rows in place of a home character's, keeping what belongs to this world. Returns notes.
    `mates` = {a mate's number in the passport: its number here}, for the settings that carry a mate's number.
    squad_home=True: the squad never left (a visit that began with the first co-op build), so its settings stay too."""
    notes = []
    kept_items, kept_links = [], []
    if "char_inventory" in layout:
        cols = layout["char_inventory"]
        names = ", ".join(f"`{c}`" for c in cols)
        marks = ", ".join("?" for _ in LS_ITEMS)
        kept_items = [(cols, list(r)) for r in _all(cur, f"SELECT {names} FROM char_inventory WHERE charid = ? AND itemId IN ({marks})",
                                                    (charid,) + LS_ITEMS)]
    if "char_equip" in layout:
        cols = layout["char_equip"]
        names = ", ".join(f"`{c}`" for c in cols)
        marks = ", ".join("?" for _ in LINK_SLOTS)
        kept_links = [(cols, list(r)) for r in _all(cur, f"SELECT {names} FROM char_equip WHERE charid = ? AND equipslotid IN ({marks})",
                                                    (charid,) + LINK_SLOTS)]
    for table in ONE_ROW + MANY_ROWS:
        if table not in layout:
            continue
        rows = _travel_rows(table, tables[table], mates)
        if table == "char_vars":               # this world's own variables (bots, co-op) stay as they are
            for (varname,) in _all(cur, "SELECT varname FROM char_vars WHERE charid = ?", (charid,)):
                if not _is_world_var(varname) and not (squad_home and str(varname).startswith("SQUAD_")):
                    cur.execute("DELETE FROM char_vars WHERE charid = ? AND varname = ?", (charid, varname))
            if squad_home and "varname" in layout[table]:
                i = layout[table].index("varname")
                rows = [r for r in rows if not str(r[i]).startswith("SQUAD_")]
        else:
            cur.execute(f"DELETE FROM `{table}` WHERE charid = ?", (charid,))
        _insert(cur, table, layout[table], rows, charid)
    cols = layout["chars"]
    row = [_dec(v) for v in tables["chars"]["rows"][0]]
    pairs = [(c, v) for c, v in zip(cols, row) if c != "charname"]
    sets = ", ".join(f"`{c}` = ?" for c, _v in pairs)
    params = [v for _c, v in pairs]
    if accid is not None:
        sets += ", `accid` = ?"
        params.append(accid)
    cur.execute(f"UPDATE chars SET {sets} WHERE charid = ?", tuple(params) + (charid,))
    if "char_stats" in layout and "zoning" in layout["char_stats"]:
        cur.execute("UPDATE char_stats SET zoning = 0 WHERE charid = ?", (charid,))
    homeless = _put_back_kept(cur, charid, kept_items, kept_links, tables)
    if homeless:
        notes.append(f"{len(homeless)} linkshell item(s) had no free bag slot to go back to and were left out.")
    return notes


def backup_character(conn, charid):
    """Everything of the listed tables for one character, as passport bytes (kind 'backup': only for this world)."""
    world = world_identity(conn)
    cur = conn.cursor()
    try:
        layout, squad = local_layout(cur), squad_layout(cur)
        tables = _read(cur, layout, charid, full=True)
        name = _cell(tables, "chars", "charname")
        return pack(_make("backup", tables, name, world, {"world": world["id"], "charid": charid}, "", 0,
                          layout_signature(layout, squad), squad=_read_squad(cur, squad, charid)))
    finally:
        cur.close()
        conn.rollback()


def restore_backup(conn, data):
    """Puts a backup made by backup_character() back over the same character of the same world."""
    passport = unpack(data)
    world = world_identity(conn)
    home = passport.get("home") or {}
    if passport.get("kind") != "backup" or home.get("world") != world["id"]:
        raise PassportError("That file is not a backup of a character of this world.")
    charid = int(home.get("charid", 0))
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT charname FROM chars WHERE charid = ? FOR UPDATE", (charid,))
        if row is None or row[0] != passport["name"]:
            raise PassportError(f"{passport['name']} is not a character of this world any more.")
        if is_online(cur, charid):
            raise PassportError(f"{row[0]} is in the game right now. Log out first.")
        layout, squad = local_layout(cur), squad_layout(cur)
        _check_tables(passport, layout, squad)
        old = passport.get("format") == OLD_FORMAT          # (a backup from before squads travelled: the squad is not in it)
        mates = None if old else _put_squad(cur, squad, charid, passport.get("squad"), keep_ids=True)
        for table in ONE_ROW + MANY_ROWS:
            if table in layout:
                rows = passport["tables"][table]["rows"]
                if not old and table == "char_vars" and "varname" in layout[table]:      # a mate's settings follow its number here
                    i = layout[table].index("varname")
                    rows = [r[:i] + [_mate_var(r[i], mates)] + r[i + 1:] for r in rows if isinstance(r[i], str) and _mate_var(r[i], mates)]
                cur.execute(f"DELETE FROM `{table}` WHERE charid = ?", (charid,))
                _insert(cur, table, layout[table], rows, charid)
        cols = layout["chars"]
        pairs = [(c, _dec(v)) for c, v in zip(cols, passport["tables"]["chars"]["rows"][0]) if c != "charname"]
        cur.execute(f"UPDATE chars SET {', '.join(f'`{c}` = ?' for c, _v in pairs)} WHERE charid = ?",
                    tuple(v for _c, v in pairs) + (charid,))
        conn.commit()
        return passport["summary"]
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def difference(before, after):
    """What a visit changed, for the 'welcome home' message."""
    out = {"job": after.get("job"), "level": after.get("level"), "levels": after.get("level", 0) - before.get("level", 0)
           if after.get("job") == before.get("job") else 0, "gil": after.get("gil", 0) - before.get("gil", 0),
           "items": after.get("items", 0) - before.get("items", 0), "mates": []}
    was = {m["slot"]: m for m in before.get("squad") or []}
    for mate in after.get("squad") or []:
        old = was.get(mate["slot"])
        if old is None:
            out["mates"].append(dict(mate, gained=0, new=True))
        elif old.get("job") == mate.get("job") and mate.get("level", 0) > old.get("level", 0):
            out["mates"].append(dict(mate, gained=mate["level"] - old["level"], new=False))
    return out


def come_home(conn, data, backup_dir=None, strict=False):
    """A character returns: its rows are replaced by the passport's and it is unlocked. Returns a dict for the player
    (name, what changed, notes). The same passport twice is harmless; a passport of another visit is refused.
    strict=True (the visit was to an open world, whose owner is a stranger): every value is checked first, and
    BadPassport is raised with the character left exactly as it was."""
    passport = unpack(data, OPEN_PASSPORT_BYTES if strict else MAX_PASSPORT_BYTES)
    world = world_identity(conn)
    home = passport.get("home") or {}
    if passport.get("kind") not in ("return", "checkpoint") or home.get("world") != world["id"]:
        raise PassportError("That passport does not belong to a character of this world.")
    charid = int(home.get("charid", 0))
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        away = _one(cur, "SELECT accid, nonce, state, generation, squad FROM coop_away WHERE charid = ? FOR UPDATE", (charid,))
        if away is None or away[1] != passport.get("nonce"):
            raise PassportError("That passport is from an older visit and cannot be used any more.")
        name_row = _one(cur, "SELECT charname FROM chars WHERE charid = ? FOR UPDATE", (charid,))
        if name_row is None:
            raise PassportError("That character does not exist here any more.")
        if away[2] != "away":
            conn.rollback()
            return {"name": name_row[0], "already": True, "changes": {}, "notes": [], "summary": passport["summary"]}
        layout, squad = local_layout(cur), squad_layout(cur)
        _check_tables(passport, layout, squad)
        if strict:
            inspect_passport(cur, passport, layout, squad)
        freed = strict and _out_of_gaol(passport)
        # Did the squad leave with the character? Not on a visit that began with the first co-op build: then the
        # squad at home is left exactly as it is, whatever the passport holds.
        took_squad = bool(away[4]) and passport.get("format") == FORMAT
        if bool(away[4]) and not took_squad:
            raise PassportError("That passport was made by another version of XI: Forever Offline.")
        before_tables = _read(cur, layout, charid, full=True)
        before_squad = _read_squad(cur, squad, charid)
        before = summary(before_tables)
        before["squad"] = squad_summary(before_squad) if took_squad else []
        backup_path = None
        if backup_dir:
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"home-{name_row[0]}-{time.strftime('%Y%m%d-%H%M%S')}.zip")
            with open(backup_path, "wb") as handle:
                handle.write(pack(_make("backup", before_tables, name_row[0], world, {"world": world["id"], "charid": charid},
                                        "", 0, layout_signature(layout, squad), squad=before_squad)))
        mates = _put_squad(cur, squad, charid, passport.get("squad"), keep_ids=True) if took_squad else None
        notes = _replace_rows(cur, layout, charid, passport["tables"], accid=int(away[0]), mates=mates, squad_home=not took_squad)
        if freed:
            notes.append(f"{name_row[0]} came back from that world's jail and was put at its home point.")
        cur.execute("UPDATE coop_away SET state = 'home', generation = ?, updated = ? WHERE charid = ?",
                    (int(passport.get("generation", 0)), _now(), charid))
        conn.commit()
        after = passport["summary"] if took_squad else dict(passport["summary"], squad=[])
        return {"name": name_row[0], "already": False, "changes": difference(before, after), "notes": notes,
                "summary": passport["summary"], "backup": backup_path, "stamps": passport.get("stamps", [])}
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def take_back(conn, charid, checkpoint=None, backup_dir=None, strict=False):
    """Ends a visit without the host. With a checkpoint (bytes) of this visit the character comes back as it was then;
    without one it is simply unlocked as it was before it left. A later return from that host is refused."""
    if checkpoint:
        passport = unpack(checkpoint)
        home = passport.get("home") or {}
        if int(home.get("charid", 0)) != int(charid):
            raise PassportError("That checkpoint belongs to another character.")
        return come_home(conn, checkpoint, backup_dir=backup_dir, strict=strict)
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        away = _one(cur, "SELECT accid, state FROM coop_away WHERE charid = ? FOR UPDATE", (charid,))
        name_row = _one(cur, "SELECT charname FROM chars WHERE charid = ?", (charid,))
        if away is None or name_row is None:
            raise PassportError("That character is not away.")
        if away[1] == "away":
            cur.execute("UPDATE chars SET accid = ? WHERE charid = ?", (int(away[0]), charid))
            cur.execute("UPDATE coop_away SET state = 'home', updated = ? WHERE charid = ?", (_now(), charid))
        conn.commit()
        return {"name": name_row[0], "already": away[1] != "away", "changes": {}, "notes": [], "summary": None}
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ----- host world: a visitor arrives, is saved, leaves -----
def guest_list(conn, include_gone=False, lockers=False):
    """The visitors of this world. lockers=True also lists the places kept for visitors who went home (open worlds)."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT g.guest_id, g.name, g.charid, g.accid, g.login, g.state, g.generation, g.arrived, g.updated, "
                         "g.home_world, g.home_charid, g.final_file, (SELECT COUNT(*) FROM accounts_sessions s WHERE s.charid = g.charid), "
                         "g.gkey, g.nonce, g.owner, g.alias, g.kept FROM coop_guest g" +
                         ("" if include_gone else " WHERE g.state <> 'gone'" + ("" if lockers else " AND g.state <> 'locker'")) +
                         " ORDER BY g.arrived")
        return [{"guest_id": r[0], "name": r[1], "charid": int(r[2]), "accid": int(r[3]), "login": r[4], "state": r[5],
                 "generation": int(r[6]), "arrived": str(r[7]), "updated": str(r[8]), "home_world": r[9],
                 "home_charid": int(r[10]), "final_file": r[11], "online": bool(r[12]), "gkey": r[13], "nonce": r[14],
                 "owner": r[15] or "", "alias": r[16], "local": r[16] or r[1], "kept": bool(r[17])} for r in rows]
    finally:
        cur.close()
        conn.rollback()


def _delete_character(cur, charid, accid, login):
    """Removes a visitor's character and account (the database's own trigger clears the character's other rows).
    Ids can be used again by someone else after a visitor has gone, so nothing is removed unless the account still has
    the visitor's own login and the character is still on it."""
    if not _one(cur, "SELECT 1 FROM accounts a JOIN chars c ON c.accid = a.id WHERE a.id = ? AND a.login = ? AND c.charid = ? "
                     "AND a.id < ? AND a.login <> ?", (accid, login, charid, BOT_ACCOUNT_BASE, AWAY_LOGIN)):
        cur.execute("DELETE FROM accounts WHERE id = ? AND login = ? AND login <> ? AND id < ? "
                    "AND NOT EXISTS (SELECT 1 FROM chars WHERE accid = ?)", (accid, login, AWAY_LOGIN, BOT_ACCOUNT_BASE, accid))
        return
    row = _one(cur, "SELECT partyid, partyflag FROM accounts_parties WHERE charid = ?", (charid,))
    if row is not None:
        cur.execute("DELETE FROM accounts_parties WHERE charid = ?", (charid,))
        if int(row[1]) & 0x0004:                 # it led the party: the first member left becomes the leader
            other = _one(cur, "SELECT charid FROM accounts_parties WHERE partyid = ? ORDER BY charid LIMIT 1", (int(row[0]),))
            if other:
                cur.execute("UPDATE accounts_parties SET partyflag = partyflag | 4 WHERE charid = ?", (int(other[0]),))
    cur.execute("DELETE FROM accounts_sessions WHERE charid = ?", (charid,))
    for table in ("squad_equip", "squad_job"):
        if table_columns(cur, table):
            cur.execute(f"DELETE FROM `{table}` WHERE squad_id IN (SELECT id FROM squad_mate WHERE charid = ?)", (charid,))
    for table in ("squad_mate", "squad_unlock"):
        if table_columns(cur, table):
            cur.execute(f"DELETE FROM `{table}` WHERE charid = ?", (charid,))
    cur.execute("DELETE FROM chars WHERE charid = ? AND accid = ?", (charid, accid))
    cur.execute("DELETE FROM accounts WHERE id = ? AND login = ?", (accid, login))


def import_guest(conn, data, guest_id, gkey, login, password, max_guests=6, stamp=None, avoid=(), owner="", keep=False,
                 alias=None, strict=False):
    """A visitor arrives: a guest account and the character, from the passport. Returns the guest's record (a dict).
    Sending the same passport again changes nothing and returns the same record. The character keeps its own id when
    that is free here (its macros then just work); otherwise it gets a new one that is none of `avoid` (the ids of the
    visitor's other characters, whose macro folders on the visitor's PC must not be touched).
    Open worlds: `owner` is the visitor's own id (two visitors never share or take each other's place here); keep=True
    keeps the character's place when it goes home (see remove_guest) and gives it back on the next visit; `alias` is
    the name it uses here when its own is taken (NameTaken says so); strict=True checks every value of the passport."""
    avoid = {int(i) for i in list(avoid)[:200] if isinstance(i, int)}
    passport = unpack(data, OPEN_PASSPORT_BYTES if strict else MAX_PASSPORT_BYTES)
    owner = str(owner or "")
    world = world_identity(conn)
    home = passport.get("home") or {}
    home_world, home_charid = str(home.get("world", "")), int(home.get("charid", 0))
    if passport.get("kind") != "visit" or not home_world or not home_charid or not passport.get("nonce"):
        raise PassportError("That is not a passport for a visit.")
    if passport.get("format") != FORMAT:      # (a new visit: both worlds on the version in which squads travel)
        raise PassportError("That passport was made by another version of XI: Forever Offline. Update both worlds first.")
    if home_world == world["id"]:
        raise PassportError("That character lives in this world already.")
    name = local = passport["name"]
    if alias is not None:
        if not isinstance(alias, str) or not ALIAS.fullmatch(alias):
            raise PassportError("A visiting name is 3 to 15 letters and starts with a capital, like Hurami.")
        local = alias
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        old = _one(cur, "SELECT guest_id, charid, accid, login, state, nonce, generation, gkey, alias FROM coop_guest "
                        "WHERE owner = ? AND home_world = ? AND home_charid = ? FOR UPDATE", (owner, home_world, home_charid))
        if old is not None and old[5] == passport["nonce"] and old[4] == "active":
            conn.rollback()
            return {"guest_id": old[0], "charid": int(old[1]), "accid": int(old[2]), "login": old[3], "name": name,
                    "gkey": old[7], "again": True, "local": old[8] or name}
        if old is not None and old[5] == passport["nonce"]:
            raise PassportError(f"{name} has already left this world on that visit.")
        active = _one(cur, "SELECT COUNT(*) FROM coop_guest WHERE state = 'active'")[0]
        if (old is None or (keep and old[4] != "active")) and int(active) >= int(max_guests):
            raise PassportError("This world already has all the visitors it allows.")
        layout, squad = local_layout(cur), squad_layout(cur)
        _check_tables(passport, layout, squad)
        if strict:
            inspect_passport(cur, passport, layout, squad)
            _out_of_gaol(passport)
        # Its place here was kept from an earlier visit (an open world's locker): the same character and account are
        # used again, so what stayed in this world (linkshells, auction listings, the delivery box, its name) is still its own.
        shelf = bool(keep and old is not None and old[4] == "locker" and
                     _one(cur, "SELECT 1 FROM chars WHERE charid = ? AND accid = ? FOR UPDATE", (int(old[1]), int(old[2]))))
        if shelf:
            return _back_to_locker(conn, cur, passport, old, layout, squad, guest_id, gkey, login, password, stamp, owner)
        if old is not None:                      # an earlier visit of the same character: its old copy here is replaced
            if old[4] != "gone":
                if is_online(cur, int(old[1])):
                    raise PassportError(f"{name} is in the game here right now.")
                _delete_character(cur, int(old[1]), int(old[2]), old[3])
            cur.execute("DELETE FROM coop_guest WHERE guest_id = ?", (old[0],))
        renamed = _make_room_for_name(cur, local)
        accid = _free_id(cur, "accounts", "id", 1000, BOT_ACCOUNT_BASE)
        if _one(cur, "SELECT 1 FROM accounts WHERE login = ? LIMIT 1", (login,)):
            raise PassportError("That guest login is taken; try again.")
        cur.execute("INSERT INTO accounts (id, login, password, timecreate, timelastmodify, status, priv) "
                    "VALUES (?, ?, PASSWORD(?), NOW(), NOW(), 1, 1)", (accid, login, password))
        charid = home_charid if not _one(cur, "SELECT 1 FROM chars WHERE charid = ?", (home_charid,)) and \
            home_charid < BOT_CHAR_BASE else _free_id(cur, "chars", "charid", 1, BOT_CHAR_BASE, avoid)
        cols = layout["chars"]
        values = [_dec(v) for v in passport["tables"]["chars"]["rows"][0]]
        values[cols.index("charname")] = local
        names = ", ".join(f"`{c}`" for c in cols)
        extra_cols, extra_vals = ["charid", "accid"], [charid, accid]
        if "original_accid" in table_columns(cur, "chars"):
            extra_cols.append("original_accid")
            extra_vals.append(accid)
        cur.execute(f"INSERT INTO chars ({', '.join('`' + c + '`' for c in extra_cols)}, {names}) "
                    f"VALUES ({', '.join('?' for _ in extra_cols)}, {', '.join('?' for _ in cols)})",
                    tuple(extra_vals + values))
        mates = _put_squad(cur, squad, charid, passport.get("squad"), keep_ids=False)     # its squad, numbered this world's way
        for table in ONE_ROW + MANY_ROWS:        # the new-character trigger made empty rows: the passport's replace them
            if table not in layout:
                continue
            cur.execute(f"DELETE FROM `{table}` WHERE charid = ?", (charid,))
            _insert(cur, table, layout[table], _travel_rows(table, passport["tables"][table], mates), charid)
        if "char_vars" in layout:
            vcols = table_columns(cur, "char_vars")
            cur.execute("REPLACE INTO char_vars (charid, varname, value" + (", expiry" if "expiry" in vcols else "") + ") "
                        "VALUES (?, ?, 1" + (", 0" if "expiry" in vcols else "") + ")", (charid, GUEST_VAR))
        if "char_stats" in layout and "zoning" in layout["char_stats"]:
            cur.execute("UPDATE char_stats SET zoning = 0 WHERE charid = ?", (charid,))
        stamps = list(passport.get("stamps") or [])
        if stamp:
            stamps.append(stamp)
        info = json.dumps({"stamps": stamps, "home_name": (passport.get("world") or {}).get("name", ""), "renamed_bot": renamed,
                           "arrived_as": passport.get("summary", {})})
        cur.execute("INSERT INTO coop_guest (guest_id, gkey, home_world, home_charid, name, charid, accid, login, state, nonce, "
                    "generation, arrived, updated, info, owner, alias, kept) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (guest_id, gkey, home_world, home_charid, name, charid, accid, login, passport["nonce"],
                     int(passport.get("generation", 1)), _now(), _now(), info, owner, local if local != name else None, 1 if keep else 0))
        conn.commit()
        return {"guest_id": guest_id, "charid": charid, "accid": accid, "login": login, "name": name, "gkey": gkey,
                "again": False, "renamed_bot": renamed, "local": local, "shelf": False}
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def guest_holdings(conn, charid):
    """What a visitor would leave behind here: auction listings not sold yet and items in the delivery box."""
    cur = conn.cursor()
    try:
        auctions = _one(cur, "SELECT COUNT(*) FROM auction_house WHERE seller = ? AND sale = 0", (charid,))[0]
        box = _one(cur, "SELECT COUNT(*) FROM delivery_box WHERE charid = ?", (charid,))[0]
        return {"auctions": int(auctions), "delivery": int(box)}
    finally:
        cur.close()
        conn.rollback()


def export_guest(conn, guest_id, final=False, versions=None, save_dir=None):
    """The visitor's character as it is now. final=False: a checkpoint (it may be in the game). final=True: the passport
    it goes home with (it must be logged out; its account is closed so it cannot be played here again, and the passport
    is written to save_dir before anything is marked, so it can be handed out again as often as needed).
    Returns (passport bytes, generation)."""
    world = world_identity(conn)
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT charid, accid, state, nonce, generation, home_world, home_charid, name, info, final_file "
                        "FROM coop_guest WHERE guest_id = ? FOR UPDATE", (guest_id,))
        if row is None or row[2] == "gone":
            raise PassportError("That visitor is not in this world.")
        if row[2] == "left":
            if not final:
                raise PassportError("That visitor has already left.")
            if row[9] and os.path.exists(row[9]):
                with open(row[9], "rb") as handle:
                    data = handle.read()
                conn.rollback()
                return data, int(row[4])
        charid = int(row[0])
        if final and is_online(cur, charid):
            raise PassportError(f"{row[7]} is still in the game. Log out first.")
        layout, squad = local_layout(cur), squad_layout(cur)
        tables = _read(cur, layout, charid)
        generation = int(row[4]) + 1
        info = json.loads(row[8] or "{}")
        data = pack(_make("return" if final else "checkpoint", tables, row[7], world, {"world": row[5], "charid": int(row[6])},
                          row[3], generation, layout_signature(layout, squad), versions, info.get("stamps"),
                          squad=_read_squad(cur, squad, charid)))
        path = None
        if final:
            if not save_dir:
                raise PassportError("No folder to keep the going-home passport in.")
            os.makedirs(save_dir, exist_ok=True)
            path = os.path.join(save_dir, f"guest-{row[7]}-{guest_id[:8]}-{generation}.zip")
            with open(path + ".part", "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(path + ".part", path)
            cur.execute("UPDATE accounts SET status = 0 WHERE id = ?", (int(row[1]),))
        cur.execute("UPDATE coop_guest SET generation = ?, updated = ?" + (", state = 'left', final_file = ?" if final else "") +
                    " WHERE guest_id = ?", (generation, _now()) + ((path,) if final else ()) + (guest_id,))
        conn.commit()
        return data, generation
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def remove_guest(conn, guest_id, forget=False):
    """The visitor is home (or the host says goodbye): its character and account are removed from this world.
    A visitor of an open world (kept) keeps its place instead: the character stays behind with its account closed, so
    its linkshells, auction listings, delivery box and name are there on the next visit. forget=True removes it anyway."""
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT charid, accid, state, name, login, kept FROM coop_guest WHERE guest_id = ? FOR UPDATE", (guest_id,))
        if row is None:
            raise PassportError("That visitor is not in this world.")
        if row[2] == "gone" or (row[2] == "locker" and not forget):
            conn.rollback()
            return False
        if is_online(cur, int(row[0])):
            raise PassportError(f"{row[3]} is in the game right now.")
        if int(row[5] or 0) and not forget:      # an open world keeps its place: the character stays, with its account closed
            cur.execute("UPDATE accounts SET status = 0 WHERE id = ? AND login = ?", (int(row[1]), row[4]))
            cur.execute("UPDATE coop_guest SET state = 'locker', updated = ? WHERE guest_id = ?", (_now(), guest_id))
            conn.commit()
            return True
        _delete_character(cur, int(row[0]), int(row[1]), row[4])
        cur.execute("UPDATE coop_guest SET state = 'gone', updated = ? WHERE guest_id = ?", (_now(), guest_id))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ----- open worlds: a visitor's place is kept between visits, and passports of strangers are checked -----
def _back_to_locker(conn, cur, passport, old, layout, squad, guest_id, gkey, login, password, stamp, owner):
    """A visitor returns to the place an open world kept for it. Its rows are replaced by the passport's the way a
    character's are when it comes home: what belongs to this world (linkshell items, this world's variables, its name
    here) stays. Finishes the transaction import_guest() began and returns the guest's record."""
    name, charid, accid = passport["name"], int(old[1]), int(old[2])
    if is_online(cur, charid):
        raise PassportError(f"{name} is in the game here right now.")
    if _one(cur, "SELECT 1 FROM accounts WHERE login = ? AND id <> ? LIMIT 1", (login, accid)):
        raise PassportError("That guest login is taken; try again.")
    if not _one(cur, "SELECT 1 FROM accounts WHERE id = ? AND id < ? AND login <> ?", (accid, BOT_ACCOUNT_BASE, AWAY_LOGIN)):
        raise PassportError(f"The place kept for {name} in this world is damaged.")
    cur.execute("UPDATE accounts SET login = ?, password = PASSWORD(?), status = 1, timelastmodify = NOW() WHERE id = ?",
                (login, password, accid))
    mates = _put_squad(cur, squad, charid, passport.get("squad"), keep_ids=True)
    _replace_rows(cur, layout, charid, passport["tables"], mates=mates)
    if "char_vars" in layout:
        vcols = table_columns(cur, "char_vars")
        cur.execute("REPLACE INTO char_vars (charid, varname, value" + (", expiry" if "expiry" in vcols else "") + ") "
                    "VALUES (?, ?, 1" + (", 0" if "expiry" in vcols else "") + ")", (charid, GUEST_VAR))
    stamps = list(passport.get("stamps") or [])
    if stamp:
        stamps.append(stamp)
    info = json.dumps({"stamps": stamps, "home_name": (passport.get("world") or {}).get("name", ""), "renamed_bot": None,
                       "arrived_as": passport.get("summary", {})})
    cur.execute("UPDATE coop_guest SET guest_id = ?, gkey = ?, login = ?, state = 'active', nonce = ?, generation = ?, arrived = ?, "
                "updated = ?, final_file = NULL, info = ?, name = ?, kept = 1 WHERE guest_id = ?",
                (guest_id, gkey, login, passport["nonce"], int(passport.get("generation", 1)), _now(), _now(), info, name, old[0]))
    conn.commit()
    return {"guest_id": guest_id, "charid": charid, "accid": accid, "login": login, "name": name, "gkey": gkey,
            "again": False, "renamed_bot": None, "local": old[8] or name, "shelf": True}


def locker_list(conn, days=LOCKER_DAYS):
    """The places an open world keeps for visitors who are home: [{guest_id, name, local, owner, since, expires}]."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT guest_id, name, alias, owner, updated, charid FROM coop_guest WHERE state = 'locker' ORDER BY updated")
        return [{"guest_id": r[0], "name": r[1], "local": r[2] or r[1], "owner": r[3] or "", "since": str(r[4]), "charid": int(r[5]),
                 "expires": str(r[4] + datetime.timedelta(days=days)) if isinstance(r[4], datetime.datetime) else ""} for r in rows]
    finally:
        cur.close()
        conn.rollback()


def expire_lockers(conn, days=LOCKER_DAYS, now=None):
    """Removes the places of visitors who have not been back for `days` days (their character, account, listings and
    delivery box here). Returns the names. One that cannot be removed right now is left for the next time."""
    ensure_tables(conn)
    limit = (now or _now()) - datetime.timedelta(days=days)
    cur = conn.cursor()
    gone = []
    try:
        rows = _all(cur, "SELECT guest_id, charid, accid, login, name, alias FROM coop_guest WHERE state = 'locker' AND updated < ? FOR UPDATE", (limit,))
        for guest_id, charid, accid, login, name, alias in rows:
            if is_online(cur, int(charid)):
                continue
            _delete_character(cur, int(charid), int(accid), login)
            cur.execute("UPDATE coop_guest SET state = 'gone', updated = ? WHERE guest_id = ?", (_now(), guest_id))
            gone.append(alias or name)
        conn.commit()
        return gone
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def visitor(conn, vid):
    """What an open world remembers of a launcher that has been here: {vid, vkey, first_seen, last_seen, address}, or None."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT vid, vkey, first_seen, last_seen, address FROM coop_visitor WHERE vid = ?", (vid,))
        return {"vid": row[0], "vkey": row[1], "first_seen": str(row[2]), "last_seen": str(row[3]), "address": row[4]} if row else None
    finally:
        cur.close()
        conn.rollback()


def register_visitor(conn, vid, vkey, address=""):
    """A launcher shows an open world its id and key. The first time they are remembered; after that the key must be
    the same one (PassportError otherwise: somebody else is using that id). Returns True when it was new."""
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT vkey FROM coop_visitor WHERE vid = ? FOR UPDATE", (vid,))
        if row is None:
            cur.execute("INSERT INTO coop_visitor (vid, vkey, first_seen, last_seen, address) VALUES (?, ?, ?, ?, ?)",
                        (vid, vkey, _now(), _now(), str(address)[:64]))
        elif row[0] != vkey:
            raise PassportError("This world knows that visitor under another key.")
        else:
            cur.execute("UPDATE coop_visitor SET last_seen = ?, address = ? WHERE vid = ?", (_now(), str(address)[:64], vid))
        conn.commit()
        return row is None
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def ban(conn, kind, value, reason=""):
    """kind 'key' (a visitor's id) or 'ip' (an address). A banned visitor cannot arrive; a character already here can still go home."""
    if kind not in ("key", "ip") or not value:
        raise PassportError("Nothing to ban.")
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        cur.execute("REPLACE INTO coop_ban (kind, value, reason, since) VALUES (?, ?, ?, ?)", (kind, str(value)[:64], str(reason)[:200], _now()))
        conn.commit()
    finally:
        cur.close()


def unban(conn, kind, value):
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM coop_ban WHERE kind = ? AND value = ?", (kind, str(value)[:64]))
        conn.commit()
    finally:
        cur.close()


def ban_list(conn):
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        return [{"kind": r[0], "value": r[1], "reason": r[2], "since": str(r[3])}
                for r in _all(cur, "SELECT kind, value, reason, since FROM coop_ban ORDER BY since")]
    finally:
        cur.close()
        conn.rollback()


def is_banned(conn, vid, address=""):
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        return _one(cur, "SELECT 1 FROM coop_ban WHERE (kind = 'key' AND value = ? AND value <> '') OR (kind = 'ip' AND value = ? AND value <> '') LIMIT 1",
                    (str(vid or ""), str(address or ""))) is not None
    finally:
        cur.close()
        conn.rollback()


def close_guest_account(conn, guest_id):
    """A visitor's account is closed (it cannot log in again); its character stays so it can still go home."""
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT accid, login FROM coop_guest WHERE guest_id = ? AND state = 'active'", (guest_id,))
        if row is not None:
            cur.execute("UPDATE accounts SET status = 0 WHERE id = ? AND login = ?", (int(row[0]), row[1]))
        conn.commit()
        return row is not None
    finally:
        cur.close()


def _column_types(cur, table):
    """{column: (type, unsigned, longest value, may be empty)} of a table of this database."""
    rows = _all(cur, "SELECT column_name, data_type, column_type, character_maximum_length, is_nullable FROM information_schema.columns "
                     "WHERE table_schema = DATABASE() AND table_name = ?", (table,))
    return {r[0]: (str(r[1]).lower(), "unsigned" in str(r[2]).lower(), r[3], str(r[4]).upper() == "YES") for r in rows}


def _fits(value, kind, unsigned, size, nullable):
    """Is this passport value something that column can hold? (As it sits in the passport: see _enc.)"""
    if value is None:
        return nullable
    if kind in INT_BITS:
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        bits = INT_BITS[kind]
        low, high = (0, 2 ** bits - 1) if unsigned else (-2 ** (bits - 1), 2 ** (bits - 1) - 1)
        return low <= value <= high
    if kind in ("float", "double"):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and abs(value) < 1e30
    if kind == "decimal":
        if isinstance(value, dict) and set(value) == {"n"} and isinstance(value["n"], str):
            return bool(re.fullmatch(r"-?\d{1,30}(\.\d{1,30})?", value["n"]))
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    if kind in TEXT_TYPES:
        return isinstance(value, str) and len(value) <= int(size or 65535) and not re.search(r"[\x00-\x1f\x7f]", value)
    if kind in BLOB_TYPES:
        if not (isinstance(value, dict) and set(value) == {"b"} and isinstance(value["b"], str)):
            return False
        if len(value["b"]) > (int(size or 65535) * 4) // 3 + 8:
            return False
        try:
            return len(base64.b64decode(value["b"], validate=True)) <= int(size or 65535)
        except Exception:
            return False
    if kind in ("datetime", "timestamp"):
        return isinstance(value, dict) and set(value) == {"t"} and isinstance(value["t"], str) and \
            bool(re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", value["t"]))
    if kind == "date":
        return isinstance(value, dict) and set(value) == {"d"} and isinstance(value["d"], str) and bool(re.fullmatch(r"\d{4}-\d\d-\d\d", value["d"]))
    if kind == "time":
        return isinstance(value, dict) and set(value) == {"s"} and isinstance(value["s"], (int, float)) and not isinstance(value["s"], bool)
    return False                                 # a kind of column this version has never seen travel


def inspect_passport(cur, passport, layout, squad=None):
    """For passports that come from strangers (an open world's visitors, or the way home from an open world). Called
    after _check_tables(). Every value must be one its column can hold, and the few values the game server trusts
    blindly (areas, jobs, levels, looks, items, bag slots) must exist. Raises BadPassport; changes nothing.
    This is about what a server can safely load, not about how a character was earned."""
    def bad(why):
        raise BadPassport(f"{passport['name']} cannot be taken in: {why}.")

    blocks = [(t, passport["tables"][t]) for t in layout]
    if squad and passport.get("squad"):
        blocks += [(t, passport["squad"][t]) for t in squad]
    for table, block in blocks:
        types = _column_types(cur, table)
        if len(block["rows"]) > OPEN_ROWS.get(table, MAX_ROWS):
            bad(f"it has more {table} entries than a character can have")
        specs = [types.get(c) for c in block["cols"]]
        if any(spec is None for spec in specs):
            bad("this world stores characters differently")
        for row in block["rows"]:
            for column, spec, value in zip(block["cols"], specs, row):
                if not _fits(value, *spec):
                    bad(f"a value does not fit ({table}.{column})")

    tables = passport["tables"]

    def cell(table, column):
        return _cell(tables, table, column)

    def column(table, name):
        block = tables.get(table)
        if not block or name not in block["cols"]:
            return []
        i = block["cols"].index(name)
        return [r[i] for r in block["rows"]]

    if table_columns(cur, "zone_settings"):
        zones = {int(r[0]) for r in _all(cur, "SELECT zoneid FROM zone_settings")}
        for name in ("pos_zone", "pos_prevzone", "home_zone"):
            value = cell("chars", name)
            if zones and value is not None and value not in zones:
                bad("it is in an area this world does not have")
    nation = cell("chars", "nation")
    if nation is not None and nation > 2:
        bad("its nation is not one of the three")
    job, sub = cell("char_stats", "mjob"), cell("char_stats", "sjob")
    if job is not None and not 1 <= job < len(JOBS):
        bad("its job is not one this world knows")
    if sub is not None and not 0 <= sub < len(JOBS):
        bad("its support job is not one this world knows")
    for name, low in (("mlvl", 1), ("slvl", 0)):
        value = cell("char_stats", name)
        if value is not None and not low <= value <= MAX_LEVEL:
            bad("its level is not a level")
    block = tables.get("char_jobs")
    if block and block["rows"]:
        for name, value in zip(block["cols"], block["rows"][0]):
            if name.upper() in JOBS[1:] and isinstance(value, int) and value > MAX_LEVEL:
                bad("one of its job levels is not a level")
    race, face, size = cell("char_look", "race"), cell("char_look", "face"), cell("char_look", "size")
    if (race is not None and not 1 <= race <= 8) or (face is not None and face > 15) or (size is not None and size > 2):
        bad("its looks are not ones the game has")
    block = tables.get("char_storage")
    if block and block["rows"]:
        if any(isinstance(v, int) and v > MAX_SLOT for v in block["rows"][0]):
            bad("one of its bags is larger than a bag can be")
    places = list(zip(column("char_inventory", "location"), column("char_inventory", "slot")))
    if any(location > MAX_CONTAINER or slot > MAX_SLOT for location, slot in places):
        bad("it keeps items where there is no bag")
    if len(set(places)) != len(places):
        bad("two of its items are in the same bag slot")
    items = set(column("char_inventory", "itemId"))
    if items and table_columns(cur, "item_basic"):
        marks = ", ".join("?" for _ in items)
        known = {int(r[0]) for r in _all(cur, f"SELECT itemid FROM item_basic WHERE itemid IN ({marks})", tuple(sorted(items)))}
        if _one(cur, "SELECT 1 FROM item_basic LIMIT 1") and items - known:
            bad(f"it carries an item this world does not know (item {sorted(items - known)[0]}); leave it at home")
    worn = column("char_equip", "equipslotid")
    if any(v > MAX_EQUIP_SLOT for v in worn) or len(set(worn)) != len(worn) or \
            any(v > MAX_CONTAINER for v in column("char_equip", "containerid")) or any(v > MAX_SLOT for v in column("char_equip", "slotid")):
        bad("it wears things in places the game does not have")
    names = column("char_vars", "varname")
    if len(set(names)) != len(names):
        bad("two of its settings have the same name")
    if squad and passport.get("squad"):
        mates = passport["squad"]["squad_mate"]
        for name in ("mjob", "sjob"):
            if name in mates["cols"]:
                i = mates["cols"].index(name)
                if any(not 0 <= r[i] < len(JOBS) for r in mates["rows"]):
                    bad("a squad mate's job is not one this world knows")
        for name, top in (("race", 8), ("face", 15)):
            if name in mates["cols"]:
                i = mates["cols"].index(name)
                if any(r[i] is not None and r[i] > top for r in mates["rows"]):
                    bad("a squad mate's looks are not ones the game has")
        jobs = passport["squad"]["squad_job"]
        if "level" in jobs["cols"]:
            i = jobs["cols"].index("level")
            if any(r[i] is not None and r[i] > MAX_LEVEL for r in jobs["rows"]):
                bad("a squad mate's level is not a level")


def _out_of_gaol(passport):
    """A stranger's world can hand a character over standing in jail, where it could never leave by itself. Such a
    character is put at its home point instead (in the passport: nothing is written here). Returns True when it was
    moved; BadPassport when its home point is the jail too. Call after inspect_passport()."""
    block = passport["tables"]["chars"]
    cols, row = block["cols"], block["rows"][0]
    at = {name: cols.index(name) for name in cols}
    if "pos_zone" not in at:
        return False
    in_house = row[at["pos_zone"]] == 0 and "pos_prevzone" in at       # (in a Mog House the area is the one it was entered from)
    if row[at["pos_zone"]] != GAOL and not (in_house and row[at["pos_prevzone"]] == GAOL):
        return False
    if "home_zone" not in at or row[at["home_zone"]] in (None, 0, GAOL):
        raise BadPassport(f"{passport['name']} cannot be taken in: it is in jail and has no home point to go to.")
    row[at["pos_zone"]] = row[at["home_zone"]]
    for here, there in (("pos_rot", "home_rot"), ("pos_x", "home_x"), ("pos_y", "home_y"), ("pos_z", "home_z")):
        if here in at and there in at:
            row[at[here]] = row[at[there]]
    if "pos_prevzone" in at:
        row[at["pos_prevzone"]] = row[at["home_zone"]]
    return True


# ----- one player, several PCs: a character (and its squad) carried from one world to another (2026-11-20) -----
# A "carry" file is the same passport a visit uses, but nothing is locked and nobody is a guest: the character simply
# exists in both worlds, and loading the file puts the newer copy over the older one (a backup of the older one is
# kept first). Each world keeps its own settings, bots, linkshells and conquest: only the character and squad move.
CARRY = "carry"
CARRY_EXT = ".xichar"
SYNC_STATE = "character_sync.json"


def save_carry(conn, charid, versions=None, stopped=False):
    """One of this world's own characters as carry-file bytes. The character must be logged out (stopped=True: the
    servers are not running, so a session row left behind by a server that was closed means nothing)."""
    ensure_tables(conn)
    world = world_identity(conn)
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT c.charname, c.accid, a.login FROM chars c JOIN accounts a ON a.id = c.accid WHERE c.charid = ?", (charid,))
        if row is None or int(row[1]) >= BOT_ACCOUNT_BASE:
            raise PassportError("That character does not exist here.")
        if row[2] == AWAY_LOGIN:
            raise PassportError(f"{row[0]} is visiting a friend's world. Bring it home first.")
        if _one(cur, "SELECT 1 FROM coop_guest WHERE charid = ? AND state <> 'gone' LIMIT 1", (charid,)):
            raise PassportError(f"{row[0]} is a visitor here: it goes home with its own world.")
        if not stopped and is_online(cur, charid):
            raise PassportError(f"{row[0]} is in the game right now. Log out first.")
        layout, squad = local_layout(cur), squad_layout(cur)
        tables = _read(cur, layout, charid)
        return pack(_make(CARRY, tables, row[0], world, {"world": world["id"], "charid": charid}, "", int(time.time()),
                          layout_signature(layout, squad), versions, squad=_read_squad(cur, squad, charid)))
    finally:
        cur.close()
        conn.rollback()


def read_carry(data):
    """The unpacked carry file, or PassportError when it is something else."""
    passport = unpack(data)
    if passport.get("kind") != CARRY:
        raise PassportError("That file was not made with SAVE FOR ANOTHER PC.")
    if passport.get("format") != FORMAT:
        raise PassportError("That file was made by another version of XI: Forever Offline. Update both PCs first.")
    return passport


def _player_account(cur):
    """The account a carried character joins when it is new here: the player's own (the one with the most characters)."""
    rows = _all(cur, "SELECT a.id, COUNT(c.charid) FROM accounts a LEFT JOIN chars c ON c.accid = a.id "
                     "WHERE a.id < ? AND a.login <> ? AND a.id NOT IN (SELECT accid FROM coop_guest) "
                     "GROUP BY a.id ORDER BY COUNT(c.charid) DESC, a.id LIMIT 1", (BOT_ACCOUNT_BASE, AWAY_LOGIN))
    if not rows:
        raise PassportError("This world has no account yet. Press PLAY and log in once (make any character), then load the file again.")
    if int(rows[0][1]) >= 16:
        raise PassportError("Your account here already has 16 characters: there is no room for another one.")
    return int(rows[0][0])


def load_carry(conn, data, backup_dir=None, stopped=False):
    """Puts a carried character into this world: over the character of the same name when there is one (a backup of it
    is written to backup_dir first), or as a new character on the player's account. Returns a dict for the message."""
    passport = read_carry(data)
    name = passport["name"]
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        layout, squad = local_layout(cur), squad_layout(cur)
        _check_tables(passport, layout, squad)
        row = _one(cur, "SELECT c.charid, c.accid, a.login FROM chars c JOIN accounts a ON a.id = c.accid "
                        "WHERE c.charname = ? LIMIT 1 FOR UPDATE", (name,))
        here = row is not None and int(row[1]) < BOT_ACCOUNT_BASE
        if here:
            charid = int(row[0])
            if row[2] == AWAY_LOGIN:
                raise PassportError(f"{name} is visiting a friend's world from this PC. Bring it home first.")
            if _one(cur, "SELECT 1 FROM coop_guest WHERE charid = ? AND state <> 'gone' LIMIT 1", (charid,)):
                raise PassportError(f"A visitor named {name} is in this world, so {name} cannot be loaded now.")
            if not stopped and is_online(cur, charid):
                raise PassportError(f"{name} is in the game right now. Log out first.")
    except Exception:
        conn.rollback()
        cur.close()
        raise
    saved = None
    if here and backup_dir:                    # (backup_character ends its own transaction, so it runs between ours)
        conn.rollback()
        os.makedirs(backup_dir, exist_ok=True)
        saved = os.path.join(backup_dir, f"{name}-before-load-{time.strftime('%Y%m%d-%H%M%S')}.zip")
        with open(saved, "wb") as handle:
            handle.write(backup_character(conn, charid))
    try:
        notes = []
        if here:
            if _one(cur, "SELECT 1 FROM chars WHERE charid = ? FOR UPDATE", (charid,)) is None or (not stopped and is_online(cur, charid)):
                raise PassportError(f"{name} changed while the file was being read. Try again.")
            mates = _put_squad(cur, squad, charid, passport.get("squad"), keep_ids=True)
            notes = _replace_rows(cur, layout, charid, passport["tables"], mates=mates)
        else:
            renamed = _make_room_for_name(cur, name)          # (a bot with that name gets another one)
            if renamed:
                notes.append(f"A bot player was using the name and is now called {renamed}.")
            accid = _player_account(cur)
            wanted = int((passport.get("home") or {}).get("charid", 0))
            charid = wanted if 0 < wanted < BOT_CHAR_BASE and not _one(cur, "SELECT 1 FROM chars WHERE charid = ?", (wanted,)) \
                else _free_id(cur, "chars", "charid", 1, BOT_CHAR_BASE)
            cols = layout["chars"]
            values = [_dec(v) for v in passport["tables"]["chars"]["rows"][0]]
            values[cols.index("charname")] = name
            extra_cols, extra_vals = ["charid", "accid"], [charid, accid]
            if "original_accid" in table_columns(cur, "chars"):
                extra_cols.append("original_accid")
                extra_vals.append(accid)
            cur.execute(f"INSERT INTO chars ({', '.join('`' + c + '`' for c in extra_cols)}, {', '.join('`' + c + '`' for c in cols)}) "
                        f"VALUES ({', '.join('?' for _ in extra_cols)}, {', '.join('?' for _ in cols)})", tuple(extra_vals + values))
            mates = _put_squad(cur, squad, charid, passport.get("squad"), keep_ids=False)
            for table in ONE_ROW + MANY_ROWS:      # the new-character trigger made empty rows: the file's replace them
                if table in layout:
                    cur.execute(f"DELETE FROM `{table}` WHERE charid = ?", (charid,))
                    _insert(cur, table, layout[table], _travel_rows(table, passport["tables"][table], mates), charid)
            if "char_stats" in layout and "zoning" in layout["char_stats"]:
                cur.execute("UPDATE char_stats SET zoning = 0 WHERE charid = ?", (charid,))
        conn.commit()
        return {"name": name, "charid": charid, "new": not here, "backup": saved, "notes": notes,
                "summary": passport.get("summary", {}), "made": int(passport.get("made", 0)),
                "from": (passport.get("world") or {}).get("id", "")}
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def _sync_state(kit):
    try:
        with open(os.path.join(kit, SYNC_STATE), encoding="utf-8-sig") as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_sync_state(kit, state):
    with open(os.path.join(kit, SYNC_STATE), "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def _fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def _content(conn, charid):
    """A fingerprint of what a character and its squad are right now in this world (to tell whether a session changed it)."""
    passport = unpack(save_carry(conn, charid, stopped=True))
    return _fingerprint(json.dumps([passport["tables"], passport.get("squad")], sort_keys=True).encode("utf-8"))


def sync_in(conn, folder, kit, log=print):
    """Before the servers start: every carry file in the folder that this PC has not seen yet (another PC saved it) is
    loaded. Returns how many characters were loaded. One bad file never stops the others."""
    state, loaded = _sync_state(kit), 0
    if not os.path.isdir(folder):
        log(f"Character folder not found ({folder}): nothing loaded.")
        return 0
    for filename in sorted(os.listdir(folder)):
        if not filename.lower().endswith(CARRY_EXT):
            continue
        path = os.path.join(folder, filename)
        try:
            if os.path.getsize(path) > MAX_PASSPORT_BYTES:
                continue
            with open(path, "rb") as handle:
                data = handle.read()
            mark = _fingerprint(data)
            passport = read_carry(data)
            name = passport["name"]
            if state.get(name, {}).get("mark") == mark:
                continue                                    # the copy this PC saved or already loaded
            if int(passport.get("made", 0)) < int(state.get(name, {}).get("made", 0)):
                log(f"{name}: the copy in the folder is older than the one here (the other PC has not saved yet?) - left alone.")
                continue
            done = load_carry(conn, data, backup_dir=os.path.join(kit, "backups"), stopped=True)
            # (its fingerprint as it is stored here: mates are numbered this world's way, so the file's own would differ
            # and the character would be saved back, and loaded on the other PC again, after every session)
            state[name] = {"mark": mark, "made": int(passport.get("made", 0)), "content": _content(conn, done["charid"])}
            _write_sync_state(kit, state)
            loaded += 1
            look = done["summary"]
            log(f"{name} arrived from your other PC (level {look.get('level', '?')} {look.get('job', '')})"
                + ("" if done["new"] else "; the copy that was here is in backups."))
        except (PassportError, OSError, ValueError) as e:
            log(f"{filename}: not loaded ({e})")
    return loaded


def sync_out(conn, folder, kit, log=print):
    """After the servers stop: each of this world's own characters is saved to the folder (only when it changed)."""
    state, saved = _sync_state(kit), 0
    os.makedirs(folder, exist_ok=True)
    for charid, name in home_characters(conn):
        try:
            data = save_carry(conn, charid, stopped=True)
            passport = unpack(data)
            content = _fingerprint(json.dumps([passport["tables"], passport.get("squad")], sort_keys=True).encode("utf-8"))
            if state.get(name, {}).get("content") == content and os.path.exists(os.path.join(folder, name + CARRY_EXT)):
                continue                                    # nothing happened to it this session
            path = os.path.join(folder, name + CARRY_EXT)
            with open(path + ".part", "wb") as handle:
                handle.write(data)
            os.replace(path + ".part", path)
            state[name] = {"mark": _fingerprint(data), "made": int(passport.get("made", 0)), "content": content}
            _write_sync_state(kit, state)
            saved += 1
        except (PassportError, OSError) as e:
            log(f"{name}: not saved to the character folder ({e})")
    return saved


def _main(argv):
    """python launcher_passport.py sync-in|sync-out   (the launcher runs these around a play session when the option is on)"""
    kit = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(kit, "config.json"), encoding="utf-8-sig") as handle:
        cfg = json.load(handle)
    folder = cfg.get("char_sync_dir") or ""
    if len(argv) < 2 or argv[1] not in ("sync-in", "sync-out") or not cfg.get("char_sync") or not folder:
        return 0
    conn = connect(cfg)
    try:
        if argv[1] == "sync-in":
            count = sync_in(conn, folder, kit)
            print(f"character folder: {count} character(s) loaded" if count else "character folder: nothing new")
        else:
            count = sync_out(conn, folder, kit)
            print(f"character folder: {count} character(s) saved" if count else "character folder: nothing changed")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv))
