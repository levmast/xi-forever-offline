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
    Each world numbers mates its own way, so they are matched by their slot (1-6) and the settings that carry a
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
WORLD_VAR_PREFIXES = ("[Bots]", "[Bot]", "COOP_")               # character variables that belong to one world
MAX_MATES = 12                # squad mates one character may bring (the game keeps six)
SQUAD_TABLES = ("squad_mate", "squad_job", "squad_equip", "squad_unlock")
MATE_VAR = re.compile(r"^(SQUAD_[A-Z_]*_)(\d+)((?:_\d+)?)$")                # a mate's own setting: SQUAD_AI_<mate id>, SQUAD_LOOK_<mate id>...
GUEST_VAR = "COOP_GUEST"
MAX_PASSPORT_BYTES = 64 * 1024 * 1024
MAX_ROWS = 20000

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
    "PRIMARY KEY (`guest_id`), UNIQUE KEY `home` (`home_world`, `home_charid`)) "
    "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci",
)


class PassportError(Exception):
    """Something about a passport or a character that the player can be told as it is."""


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


def unpack(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("passport.json")
            if info.file_size > MAX_PASSPORT_BYTES:
                raise PassportError("That passport is too large to be real.")
            passport = json.loads(archive.read("passport.json").decode("utf-8"))
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
        raise PassportError(f"A character named {name} already lives in this world, so {name} cannot visit it.")
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


def depart(conn, charid, host, versions=None):
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
        tables = _read(cur, layout, charid)
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


def come_home(conn, data, backup_dir=None):
    """A character returns: its rows are replaced by the passport's and it is unlocked. Returns a dict for the player
    (name, what changed, notes). The same passport twice is harmless; a passport of another visit is refused."""
    passport = unpack(data)
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


def take_back(conn, charid, checkpoint=None, backup_dir=None):
    """Ends a visit without the host. With a checkpoint (bytes) of this visit the character comes back as it was then;
    without one it is simply unlocked as it was before it left. A later return from that host is refused."""
    if checkpoint:
        passport = unpack(checkpoint)
        home = passport.get("home") or {}
        if int(home.get("charid", 0)) != int(charid):
            raise PassportError("That checkpoint belongs to another character.")
        return come_home(conn, checkpoint, backup_dir=backup_dir)
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
def guest_list(conn, include_gone=False):
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        rows = _all(cur, "SELECT g.guest_id, g.name, g.charid, g.accid, g.login, g.state, g.generation, g.arrived, g.updated, "
                         "g.home_world, g.home_charid, g.final_file, (SELECT COUNT(*) FROM accounts_sessions s WHERE s.charid = g.charid), "
                         "g.gkey, g.nonce FROM coop_guest g" + ("" if include_gone else " WHERE g.state <> 'gone'") + " ORDER BY g.arrived")
        return [{"guest_id": r[0], "name": r[1], "charid": int(r[2]), "accid": int(r[3]), "login": r[4], "state": r[5],
                 "generation": int(r[6]), "arrived": str(r[7]), "updated": str(r[8]), "home_world": r[9],
                 "home_charid": int(r[10]), "final_file": r[11], "online": bool(r[12]), "gkey": r[13], "nonce": r[14]} for r in rows]
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


def import_guest(conn, data, guest_id, gkey, login, password, max_guests=6, stamp=None, avoid=()):
    """A visitor arrives: a guest account and the character, from the passport. Returns the guest's record (a dict).
    Sending the same passport again changes nothing and returns the same record. The character keeps its own id when
    that is free here (its macros then just work); otherwise it gets a new one that is none of `avoid` (the ids of the
    visitor's other characters, whose macro folders on the visitor's PC must not be touched)."""
    avoid = {int(i) for i in list(avoid)[:200] if isinstance(i, int)}
    passport = unpack(data)
    world = world_identity(conn)
    home = passport.get("home") or {}
    home_world, home_charid = str(home.get("world", "")), int(home.get("charid", 0))
    if passport.get("kind") != "visit" or not home_world or not home_charid or not passport.get("nonce"):
        raise PassportError("That is not a passport for a visit.")
    if passport.get("format") != FORMAT:      # (a new visit: both worlds on the version in which squads travel)
        raise PassportError("That passport was made by another version of XI: Forever Offline. Update both worlds first.")
    if home_world == world["id"]:
        raise PassportError("That character lives in this world already.")
    name = passport["name"]
    ensure_tables(conn)
    cur = conn.cursor()
    try:
        old = _one(cur, "SELECT guest_id, charid, accid, login, state, nonce, generation, gkey FROM coop_guest "
                        "WHERE home_world = ? AND home_charid = ? FOR UPDATE", (home_world, home_charid))
        if old is not None and old[5] == passport["nonce"] and old[4] == "active":
            conn.rollback()
            return {"guest_id": old[0], "charid": int(old[1]), "accid": int(old[2]), "login": old[3], "name": name,
                    "gkey": old[7], "again": True}
        if old is not None and old[5] == passport["nonce"]:
            raise PassportError(f"{name} has already left this world on that visit.")
        active = _one(cur, "SELECT COUNT(*) FROM coop_guest WHERE state = 'active'")[0]
        if old is None and int(active) >= int(max_guests):
            raise PassportError("This world already has all the visitors it allows.")
        layout, squad = local_layout(cur), squad_layout(cur)
        _check_tables(passport, layout, squad)
        if old is not None:                      # an earlier visit of the same character: its old copy here is replaced
            if old[4] != "gone":
                if is_online(cur, int(old[1])):
                    raise PassportError(f"{name} is in the game here right now.")
                _delete_character(cur, int(old[1]), int(old[2]), old[3])
            cur.execute("DELETE FROM coop_guest WHERE guest_id = ?", (old[0],))
        renamed = _make_room_for_name(cur, name)
        accid = _free_id(cur, "accounts", "id", 1000, BOT_ACCOUNT_BASE)
        if _one(cur, "SELECT 1 FROM accounts WHERE login = ? LIMIT 1", (login,)):
            raise PassportError("That guest login is taken; try again.")
        cur.execute("INSERT INTO accounts (id, login, password, timecreate, timelastmodify, status, priv) "
                    "VALUES (?, ?, PASSWORD(?), NOW(), NOW(), 1, 1)", (accid, login, password))
        charid = home_charid if not _one(cur, "SELECT 1 FROM chars WHERE charid = ?", (home_charid,)) and \
            home_charid < BOT_CHAR_BASE else _free_id(cur, "chars", "charid", 1, BOT_CHAR_BASE, avoid)
        cols = layout["chars"]
        values = [_dec(v) for v in passport["tables"]["chars"]["rows"][0]]
        values[cols.index("charname")] = name
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
                    "generation, arrived, updated, info) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)",
                    (guest_id, gkey, home_world, home_charid, name, charid, accid, login, passport["nonce"],
                     int(passport.get("generation", 1)), _now(), _now(), info))
        conn.commit()
        return {"guest_id": guest_id, "charid": charid, "accid": accid, "login": login, "name": name, "gkey": gkey,
                "again": False, "renamed_bot": renamed}
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


def remove_guest(conn, guest_id):
    """The visitor is home (or the host says goodbye): its character and account are removed from this world."""
    cur = conn.cursor()
    try:
        row = _one(cur, "SELECT charid, accid, state, name, login FROM coop_guest WHERE guest_id = ? FOR UPDATE", (guest_id,))
        if row is None:
            raise PassportError("That visitor is not in this world.")
        if row[2] == "gone":
            conn.rollback()
            return False
        if is_online(cur, int(row[0])):
            raise PassportError(f"{row[3]} is in the game right now.")
        _delete_character(cur, int(row[0]), int(row[1]), row[4])
        cur.execute("UPDATE coop_guest SET state = 'gone', updated = ? WHERE guest_id = ?", (_now(), guest_id))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


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
