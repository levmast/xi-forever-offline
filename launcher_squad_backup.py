"""Squad backup and restore (2026-11-24, Rennie's suggestion; the user: "yes to squad backups and restores").

One file (.xisquad, JSON) holds a character's whole squad, so it can be put back after a mistake, a reinstall or on
another character:
  * every mate: name, look, jobs and levels with their exp, gear for each job, and the items unlocked for the squad
    (the same squad tables a co-op passport carries, launcher_passport.SQUAD_TABLES);
  * the character variables that belong to a mate (SQUAD_<WHAT>_<mate id>[_<job>]: which Rule Set each job uses, the
    weapon skill choice, a picked look...). A mate gets a new number when it is restored, so these are renumbered;
  * each mate's personality sheet for squad chat (squad-chat/mates/<name>.json) and its own greetings.
Not inside: the Rule Sets themselves. They stay in the world's Rule Set store (and can be shared with Export / Import in
/gambits); a restored mate on the same world keeps using its sets.

Restoring REPLACES the character's squad (a backup of the squad as it was is made first, next to the file).
No GUI code.
"""
import json
import os
import re
import time

import launcher_passport as pp
import launcher_personality as pers
import launcher_squad as sq

FORMAT = "xifo-squad-backup"
VERSION = 1
SUFFIX = ".xisquad"
MATE_VAR = re.compile(r"^(SQUAD_[A-Z]+_)(\d+)((?:_\d+)?)$")   # SQUAD_RS_12_3, SQUAD_LOOK_12, SQUAD_WS_12_5 ...


class SquadBackupError(Exception):
    pass


def _rows(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def _character(cur, charid):
    rows = _rows(cur, "SELECT charname FROM chars WHERE charid = ?", (charid,))
    if not rows:
        raise SquadBackupError("That character is not in this world.")
    return str(rows[0][0])


def backup(conn, kit, charid, greeting_user=None):
    """The character's squad as a dict (see the module text). Changes nothing."""
    cur = conn.cursor()
    try:
        name = _character(cur, charid)
        layout = pp.squad_layout(cur)
        if not layout:
            raise SquadBackupError("This world has no squad tables yet: press PLAY once, then try again.")
        squad = pp._read_squad(cur, layout, charid)
        ids = {int(r[squad["squad_mate"]["cols"].index("id")]) for r in squad["squad_mate"]["rows"]}
        names = [r[squad["squad_mate"]["cols"].index("name")] for r in squad["squad_mate"]["rows"]]
        variables = []
        for var, value in _rows(cur, "SELECT varname, value FROM char_vars WHERE charid = ? AND varname LIKE 'SQUAD%'", (charid,)):
            m = MATE_VAR.match(str(var))
            if m and int(m.group(2)) in ids:
                variables.append([str(var), int(value)])
    finally:
        cur.close()
        try:
            conn.rollback()
        except Exception:
            pass
    sheets = {}
    for mate in names:
        sheet = pers.load_sheet(kit, mate)
        if sheet:
            sheets[mate] = sheet
    greetings = {}
    if greeting_user:
        user = sq.load_json(greeting_user)
        greetings = {mate: user[mate] for mate in names if isinstance(user.get(mate), dict)}
    return {"format": FORMAT, "version": VERSION, "made": int(time.time()), "character": name,
            "summary": pp.squad_summary(squad), "squad": squad, "vars": variables,
            "personalities": sheets, "greetings": greetings}


def save(path, data):
    if not path.lower().endswith(SUFFIX):
        path += SUFFIX
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
    return path


def load(path):
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as e:
        raise SquadBackupError(f"That file could not be read ({e}).")
    if not isinstance(data, dict) or data.get("format") != FORMAT or not isinstance(data.get("squad"), dict):
        raise SquadBackupError("That is not a squad backup.")
    if int(data.get("version") or 0) > VERSION:
        raise SquadBackupError("That backup was made by a newer launcher: update first.")
    return data


def describe(data):
    """One line per mate, for the confirm box."""
    lines = [f"{m['name']} ({m['job']} {m['level']})" for m in data.get("summary") or []]
    return ", ".join(lines) if lines else "no mates"


def restore(conn, kit, charid, data, greeting_user=None):
    """Replaces the character's squad with the backup's. Returns the names restored. The caller makes a backup of the
    squad as it is first (backup() + save())."""
    squad = data["squad"]
    cur = conn.cursor()
    try:
        _character(cur, charid)
        if pp.is_online(cur, charid):
            raise SquadBackupError("That character is in the game right now. Log it out first.")
        layout = pp.squad_layout(cur)
        if not layout:
            raise SquadBackupError("This world has no squad tables yet: press PLAY once, then try again.")
        # the backup's columns must all exist here (an older backup may have fewer: those keep their defaults)
        for table, cols in layout.items():
            block = squad.get(table)
            if not isinstance(block, dict) or not isinstance(block.get("rows"), list):
                raise SquadBackupError("That backup is damaged.")
            missing = [c for c in block.get("cols", []) if c not in cols]
            if missing:
                raise SquadBackupError("That backup is from a newer version of the squad: update first.")
        try:
            conn.autocommit = False
        except Exception:
            pass
        old_ids = [int(r[0]) for r in _rows(cur, "SELECT id FROM squad_mate WHERE charid = ?", (charid,))]
        for var, in _rows(cur, "SELECT varname FROM char_vars WHERE charid = ? AND varname LIKE 'SQUAD%'", (charid,)):
            m = MATE_VAR.match(str(var))
            if m and int(m.group(2)) in old_ids:
                cur.execute("DELETE FROM char_vars WHERE charid = ? AND varname = ?", (charid, var))
        mapping = pp._put_squad(cur, layout, charid, squad, keep_ids=False)
        for var, value in data.get("vars") or []:
            m = MATE_VAR.match(str(var))
            if not m or int(m.group(2)) not in mapping:
                continue
            new = f"{m.group(1)}{mapping[int(m.group(2))]}{m.group(3)}"
            cur.execute("DELETE FROM char_vars WHERE charid = ? AND varname = ?", (charid, new))
            cur.execute("INSERT INTO char_vars (charid, varname, value) VALUES (?, ?, ?)", (charid, new, int(value)))
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()
    for mate, sheet in (data.get("personalities") or {}).items():
        if isinstance(sheet, dict):
            sheet = dict(sheet)
            sheet["name"] = mate
            try:
                pers.save_sheet(kit, sheet)
            except Exception:
                pass
    if greeting_user and data.get("greetings"):
        user = sq.load_json(greeting_user)
        for mate, row in data["greetings"].items():
            if isinstance(row, dict):
                user[mate] = row
        sq._write_json(greeting_user, user)
    return [m["name"] for m in data.get("summary") or []]


def default_name(character):
    return f"{character}-squad-{time.strftime('%Y%m%d-%H%M%S')}{SUFFIX}"
