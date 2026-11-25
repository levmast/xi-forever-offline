"""Game-file changes XI: Forever Offline makes to the player's FINAL FANTASY XI folder, after the era game files.

  1. Home Point teleport window: the era files only offer "Set home point"; 11 bytes per Home Point are put back
     (client-patches\\homepoints.json; only when the era files are installed, i.e. <kit>\\dat-backup exists).
  2. Crystal Boy items: the Crystal Boy and the four Recollections (ROM\\118\\107.DAT), the four Memory key items
     (ROM\\175\\35.DAT) and the Anniversary Ring made stackable (ROM\\118\\109.DAT) (install_crystalboy_items.py).
  3. Chariot Band: its description (+75%, 720 min, 4000), 3 charges and a 15-hour recast (client-patches\\chariot_band.json).
  4. Item stacks: today's stack sizes or the era's, to match the server (the "Modern item stacks" switch; stack_mode.py).
  5. Forever Beta Shirt (item 25725): its look (body model 399) and its item entry in ROM\\286\\73.DAT (forever_beta_shirt.py).
  6. Spells on squad mates: the party-only spells (Regen, Refresh, Erase, Curaga, Phalanx II, the Etudes, Wild Carrot,
     Magic Fruit) and job abilities (Cover, Accomplice, Collaborator, Martyr, Devotion, Shikikoyo, Healing Waltz,
     Healing Ruby) get the "NPC" target, so the game lets you aim them at a squad mate (the game's spell and ability
     tables in ROM\\118\\114.DAT; client-patches\\spell_targets.json).
  7. Mode titles: the four game-mode titles (Iron, Steel, Silver, Randomized) in empty slots 1078 - 1081 of the game's
     English title list (ROM\\180\\78.DAT), so the title the server puts on those characters has a name.
  8. Mode marks: the four mode shields and XI: Forever's own new-player "?" in the game's icon sheet ("ustats" in
     ROM\\0\\1.DAT and three more copies), the marks the game draws beside a name (client-patches\\mode_marks.json).

Every step checks first and only writes what is missing, so this runs at the end of first-run setup and again on
every PLAY of a player install (an update or a reinstalled era pack is caught the next time). A step that cannot be
done (a folder Windows won't let the launcher write, a file that is not the expected one) is reported and skipped;
it never stops the game from starting. Originals are kept in <kit>\\backups.
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _kit_module(kit, name):
    if kit not in sys.path:
        sys.path.insert(0, kit)
    return __import__(name)


# ----- 1. Home Points -----
def _entry_starts(data):
    """{NPC id: start} for an event file (count, table of entry sizes, entries that begin with the NPC id)."""
    import struct
    if len(data) < 8:
        return {}
    count = struct.unpack_from("<I", data, 0)[0]
    if count == 0 or count > 5000 or 4 + 4 * count > len(data):
        return {}
    sizes = struct.unpack_from("<%dI" % count, data, 4)
    if 4 + 4 * count + sum(sizes) != len(data):
        return {}
    out, off = {}, 4 + 4 * count
    for size in sizes:
        if size >= 4:
            out[struct.unpack_from("<I", data, off)[0]] = off
        off += size
    return out


def homepoints(kit, game, server=None, log=print):
    """Puts the Home Point teleport window back with the 11-byte table in client-patches\\homepoints.json. It never
    copies from the player's own game files: an older launcher copied whole retail entries from them, which breaks
    with a game version newer than the era files (the crystal shows a Chains of Promathia message and waits). Files
    that older launcher changed are rebuilt from the untouched era file it saved in backups\\homepoint-events."""
    if not os.path.isdir(os.path.join(kit, "dat-backup")):
        return "Home Points: the era game files are not installed, so they are already retail."
    with open(os.path.join(kit, "client-patches", "homepoints.json"), encoding="utf-8") as handle:
        table = json.load(handle)
    retail = bytes.fromhex(table["retail"])
    by_file = {}
    for row in table["entries"]:
        by_file.setdefault(row["file"], []).append(row)
    fixed = files = repaired = 0
    unknown = []
    for rel, rows in sorted(by_file.items()):
        parts = rel.split("/")
        path = os.path.join(game, *parts)
        keep = os.path.join(kit, "backups", "homepoint-events", *parts)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as handle:
            current = handle.read()
        source = current
        if os.path.isfile(keep):
            with open(keep, "rb") as handle:
                source = handle.read()             # the untouched era file
        data = bytearray(source)
        starts = _entry_starts(data)
        changed = 0
        for row in rows:
            start = starts.get(row["npc"])
            if start is None:
                unknown.append(row["npc"])
                continue
            at = start + row["at"]
            here = bytes(data[at:at + len(retail)])
            if here == retail:
                continue
            if here != bytes.fromhex(row["era"]):
                unknown.append(row["npc"])
                continue
            data[at:at + len(retail)] = retail
            changed += 1
        if bytes(data) == current:
            continue
        if not os.path.isfile(keep):
            os.makedirs(os.path.dirname(keep), exist_ok=True)
            with open(keep, "wb") as handle:
                handle.write(current)
        tmp = path + ".hp-tmp"
        with open(tmp, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
        files += 1
        fixed += changed
        if source is not current:
            repaired += 1
    notes = []
    if files:
        notes.append(f"Home Points: the teleport window is back on {fixed} crystal(s) in {files} file(s)"
                     + (f" ({repaired} file(s) rebuilt from the era originals)" if repaired else "") + ".")
    if unknown:
        notes.append(f"Home Points: {len(unknown)} crystal(s) skipped (their event file is not the expected era file).")
    return " ".join(notes) or None


# ----- 2. Crystal Boy items -----
def crystalboy(kit, game, log=print):
    icb = _kit_module(kit, "install_crystalboy_items")
    done = []
    path = os.path.join(game, icb.DAT_REL)
    rs = icb.record_size(path)
    with open(path, "rb") as handle:
        data = handle.read()
    if any(icb.item_name(icb.read_record(data, rs, it["id"])) != it["name"] for it in icb.ITEMS):
        icb.dat_install(game)
        done.append("items")
    with open(os.path.join(game, icb.KI_REL), "rb") as handle:
        index, body = icb.ki_entries(handle.read())
    def ki_name(kid):
        j = index.get(kid)
        return None if j is None else icb.ki_parse(body[j * icb.KI_ENTRY:(j + 1) * icb.KI_ENTRY])[4]
    if any(ki_name(k["id"]) != k["name"] for k in icb.KEY_ITEMS):
        icb.ki_install(game)
        done.append("key items")
    ring = icb.ring_install(game)
    if "already" not in ring:
        done.append("Anniversary Ring")
    return ("Crystal Boy: game files updated (" + ", ".join(done) + ").") if done else None


# ----- 3. Chariot Band -----
def chariot_band(kit, game, log=print):
    with open(os.path.join(kit, "client-patches", "chariot_band.json"), encoding="utf-8") as handle:
        patch = json.load(handle)
    path = os.path.join(game, *patch["file"].split("/"))
    if os.path.getsize(path) != patch["size"]:
        return "Chariot Band: the game's armor file is not the expected one; its description was left as it is."
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    if all(data[at] == new for at, _old, new in patch["bytes"]):
        return None
    if not all(data[at] == old for at, old, _new in patch["bytes"]):
        return "Chariot Band: the game's armor file is not the expected one; its description was left as it is."
    keep = os.path.join(kit, "backups", "chariot-band-dat", "109.DAT.original")
    if not os.path.exists(keep):
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        with open(keep, "wb") as handle:
            handle.write(data)
    for at, _old, new in patch["bytes"]:
        data[at] = new
    tmp = path + ".cb-tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)
    return "Chariot Band: its description now matches this server (+75%, 3 charges, 15 hours)."


# ----- 4. Item stacks -----
def item_stacks(kit, game, server, log=print):
    """The game's item files say how far each item stacks, and they have to agree with the server's item table.
    The switch is "modern_stacks" in the launcher's rates (on = today's sizes, the default; off = the era's)."""
    sm = _kit_module(kit, "stack_mode")
    core = _kit_module(kit, "launcher_core")
    rows = sm.overrides(server) if server else []
    if not rows:
        return None
    modern = bool(core.load_rates(kit).get("modern_stacks", True))
    changed, _right, skipped = sm.apply_dats(game, rows, modern, os.path.join(kit, "backups", "stacking-dat"))
    if not changed:
        return None
    return "Item stacks: %d item(s) in the game files now stack %s%s." % (
        changed, "as in today's game (12 / 99)" if modern else "as in the era",
        (" (%d left alone)" % skipped) if skipped else "")


# ----- 5. Forever Beta Shirt -----
def forever_beta_shirt(kit, game, log=print):
    """Its own look and item entry. Checks first; rebuilds only what an update or the era pack replaced."""
    fbs = _kit_module(kit, "forever_beta_shirt")
    return fbs.apply(game, log=log)


# ----- 6. Spells you can aim at a squad mate -----
# (2026-11-22, Yache: Wild Carrot and Magic Fruit cannot be aimed at a squad mate) The server accepts them; the game
# itself refuses the target. To the game a squad mate is an NPC in your party, like a Trust, and it only offers one as
# a target for spells whose own target list includes NPCs (Cure, Protect, Haste do; these two are party-only).
# The spell table is the "mgc_" part of ROM\118\114.DAT: 100 bytes a spell, in spell id order. Each entry is stored
# with every byte turned by a few bits; how many is worked out from three bytes that are stored as they are.
SPELL_FILE = ("ROM", "118", "114.DAT")
SPELL_ENTRY = 100
SPELL_TARGETS_AT = 6          # the low byte of the entry's target list
TARGET_NPC = 0x10
_BITS = [bin(n).count("1") for n in range(256)]


def _spell_turn(entry):
    """How many bits each byte of this entry is turned by (bytes 2, 11 and 12 are stored unturned and decide it)."""
    return (7, 1, 6, 2, 5)[abs(_BITS[entry[2]] - _BITS[entry[11]] + _BITS[entry[12]]) % 5]


def _turn_right(value, bits):
    return ((value >> bits) | (value << (8 - bits))) & 0xFF


def _turn_left(value, bits):
    return ((value << bits) | (value >> (8 - bits))) & 0xFF


# the two tables of that file the launcher changes: (the part's name, bytes an entry, where the low byte of its target
# list is, what a listed id has to be raised by to get its entry)
_TARGET_TABLES = {"spells": (b"mgc_", SPELL_ENTRY, SPELL_TARGETS_AT, 0),
                  "abilities": (b"comm", 48, 10, 512)}        # (2026-11-22) job abilities: the same idea, their own table


def _game_table(data, name, entry_size):
    """(where the first entry starts, how many entries) of one table in the game's file, or None."""
    at = 0
    while at + 16 <= len(data):
        packed = int.from_bytes(data[at + 4:at + 8], "little")
        size = ((packed >> 7) & 0x7FFFF) * 16
        if size <= 0 or at + size > len(data):
            return None
        if bytes(data[at:at + 4]) == name:
            return at + 16, (size - 16) // entry_size
        at += size
    return None


def _table_field(data, start, entry_size, index, offset):
    """A byte of an entry as the game reads it, after checking the entry really is the one with that number."""
    at = start + index * entry_size
    entry = data[at:at + entry_size]
    turn = _spell_turn(entry)
    if _turn_right(entry[0], turn) | (_turn_right(entry[1], turn) << 8) != index:
        raise ValueError("not the expected table")
    return _turn_right(entry[offset], turn), turn


def _spell_table(data):
    return _game_table(data, b"mgc_", SPELL_ENTRY)


def _spell_field(data, start, spell_id, offset):
    return _table_field(data, start, SPELL_ENTRY, spell_id, offset)


def spell_targets(kit, game, log=print):
    """Adds the NPC target to the listed spells and job abilities. Each one is checked by itself: what is already done
    is skipped, what does not have the target list we know is left alone."""
    with open(os.path.join(kit, "client-patches", "spell_targets.json"), encoding="utf-8") as handle:
        listed = json.load(handle)
    path = os.path.join(game, *SPELL_FILE)
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    unexpected = "Spells on squad mates: the game's spell file is not the expected one; it was left as it is."
    changes, done, odd = [], 0, 0
    for key, (part, entry_size, targets_at, raise_by) in _TARGET_TABLES.items():
        wanted = listed.get(key) or []
        if not wanted:
            continue
        table = _game_table(data, part, entry_size)
        if table is None:
            if key == "spells":
                return unexpected
            odd += len(wanted)
            continue
        start, count = table
        try:
            _table_field(data, start, entry_size, 1, targets_at)      # (the table reads as one of the game's at all)
        except (ValueError, IndexError):
            if key == "spells":
                return unexpected
            odd += len(wanted)
            continue
        for one in wanted:
            index = one["id"] + raise_by
            try:
                if index >= count:
                    raise IndexError(index)
                targets, turn = _table_field(data, start, entry_size, index, targets_at)
            except (ValueError, IndexError):
                if key == "spells":
                    return unexpected
                odd += 1
                continue
            if targets == one["targets"] | TARGET_NPC:
                done += 1                                              # already done
            elif targets != one["targets"]:
                odd += 1                                               # not the target list we know: it stays as it is
            else:
                changes.append((start + index * entry_size + targets_at, _turn_left(targets | TARGET_NPC, turn), one["name"]))
    if not changes:
        return None if done else unexpected
    keep = os.path.join(kit, "backups", "spell-targets-dat", "114.DAT.original")
    if not os.path.exists(keep):
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        with open(keep, "wb") as handle:
            handle.write(data)
    for at, value, _name in changes:
        data[at] = value
    tmp = path + ".st-tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)
    names = [name for _at, _value, name in changes]
    shown = " and ".join(names) if len(names) <= 3 else "%s and %d more" % (", ".join(names[:3]), len(names) - 3)
    return "Spells on squad mates: %s can now be aimed at a squad mate%s." % (
        shown, (" (%d left as they were)" % odd) if odd else "")


# ----- 7. Mode titles -----
# (2026-11-23) The game's English title list is a "d_msg" file: a 0x40-byte header, then one 0x100-byte entry a title,
# in title id order, every byte XOR 0xFF. An entry holds one text: [count 1][where it is, kind 0][1, 24 zero bytes,
# the text]. Slots 1078 - 1115 are empty in the game's own file and the server uses none of them; the server gives
# these four to the game modes (hardcoreutils::modeTitle) and keeps them on.
TITLE_FILE = ("ROM", "180", "78.DAT")
TITLE_ENTRY = 0x100
MODE_TITLES = {1078: "Forged in Solitude", 1079: "Tempered by Ruin", 1080: "Bearer of a Single Flame",
               1081: "Altana's Wild Card"}


def _title_text(data, title_id):
    """The text of one title, or None when the entry is not laid out as expected."""
    at = 0x40 + title_id * TITLE_ENTRY
    entry = bytes(c ^ 0xFF for c in data[at:at + TITLE_ENTRY])
    if len(entry) != TITLE_ENTRY:
        return None
    count, offset, kind = struct.unpack_from("<III", entry, 0)
    if count != 1 or kind != 0 or offset + 0x1C >= TITLE_ENTRY:
        return None
    start = offset + 0x1C
    end = entry.find(b"\0", start)
    return entry[start:end if end >= 0 else TITLE_ENTRY].decode("latin-1")


def _title_entry(text):
    blob = struct.pack("<IIII", 1, 0x0C, 0, 1) + b"\0" * 24 + text.encode("latin-1") + b"\0"
    if len(blob) > TITLE_ENTRY:
        raise ValueError("title too long: " + text)
    return bytes(c ^ 0xFF for c in blob.ljust(TITLE_ENTRY, b"\0"))


def mode_titles(kit, game, log=print):
    path = os.path.join(game, *TITLE_FILE)
    if not os.path.exists(path):
        return "Mode titles: the game's title file is missing, so the game-mode titles show without a name."
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    if (data[:5] != b"d_msg" or struct.unpack_from("<I", data, 0x20)[0] != TITLE_ENTRY
            or len(data) < 0x40 + (max(MODE_TITLES) + 1) * TITLE_ENTRY or _title_text(data, 1) != "Fodderchief Flayer"):
        return "Mode titles: the game's title file is not the expected one; it was left as it is."
    # the layout is understood: an entry rebuilt from its own text gives the same bytes
    if bytes(data[0x40 + TITLE_ENTRY:0x40 + 2 * TITLE_ENTRY]) != _title_entry("Fodderchief Flayer"):
        return "Mode titles: the game's title file is laid out differently; it was left as it is."
    todo = []
    for title_id, text in sorted(MODE_TITLES.items()):
        now = _title_text(data, title_id)
        if now == text:
            continue
        if now != "" and now not in MODE_TITLES.values():
            return "Mode titles: slot %d of the game's title list is already used by '%s'; nothing was changed." % (title_id, now)
        todo.append((title_id, text))
    if not todo:
        return None
    keep = os.path.join(kit, "backups", "mode-titles-dat", "78.DAT.original")
    if not os.path.exists(keep):
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        with open(keep, "wb") as handle:
            handle.write(data)
    for title_id, text in todo:
        at = 0x40 + title_id * TITLE_ENTRY
        data[at:at + TITLE_ENTRY] = _title_entry(text)
    tmp = path + ".mt-tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)
    with open(path, "rb") as handle:
        back = handle.read()
    if any(_title_text(back, title_id) != text for title_id, text in MODE_TITLES.items()):
        return "Mode titles: the title file did not read back as written; restore it from %s." % keep
    return "Mode titles: %s are in the game's title list." % ", ".join('"%s"' % t for _i, t in todo)


def restore_mode_titles(kit, game):
    keep = os.path.join(kit, "backups", "mode-titles-dat", "78.DAT.original")
    if os.path.exists(keep):
        import shutil
        shutil.copy2(keep, os.path.join(game, *TITLE_FILE))
        return True
    return False


# ----- 8. Mode marks beside the name -----
# (2026-11-23) The game draws its own marks beside a name from one icon sheet, the texture "ustats" in ROM\0\1.DAT:
# 128x64 pixels of 16x16 cells, DXT3. The server shows four marks the era never uses on the mode characters
# (hardcoreutils::modeMarks): Iron the trial-account leaf, Steel the PlayOnline orb, Silver the mentor globe,
# Randomized the "accepting party requests" goblet; and every new character's "?" becomes XI: Forever's own.
# client-patches\mode_marks.json holds the five pictures already in the game's format (art-src\scripts\mode_marks_art.py).
MARKS_FILES = (("ROM", "0", "1.DAT"), ("ROM", "0", "13.DAT"), ("ROM", "118", "111.DAT"), ("ROM", "280", "15.DAT"))
# the high-resolution copy "ustatshd" (256x256): large nameplates draw from it. Its 32x32 cells get mode_marks.json's
# "hd" pictures, and its top-left 128x64 is the 16x16 sheet again, which gets the 16x16 ones.
MARKS_HD_FILES = (("ROM", "119", "51.DAT"), ("ROM", "91", "15.DAT"), ("ROM", "176", "75.DAT"), ("ROM", "178", "14.DAT"))


def _marks_texture(data, name=b"ustats", size=(128, 64)):
    """Where an icon picture's blocks start ("ustats" 128x64, or "ustatshd" 256x256), or None when the file is not
    laid out as expected."""
    at = 0
    while at + 16 <= len(data):
        packed = int.from_bytes(data[at + 4:at + 8], "little")
        block = ((packed >> 7) & 0x7FFFF) * 16
        if block <= 0 or at + block > len(data):
            return None
        if packed & 0x7F == 0x20 and bytes(data[at + 17:at + 33]).split() == [b"menu", name]:
            width, height = struct.unpack_from("<ii", data, at + 37)
            if data[at + 16] == 0xA1 and (width, height) == tuple(size) and bytes(data[at + 73:at + 77]) == b"3TXD" \
                    and at + 85 + width * height <= at + block:
                return at + 85
            return None
        at += block
    return None


def _cell_offsets(start, row, col, width=128, cell=16):
    """The block offsets (4x4-pixel blocks of 16 bytes) of one cell, in the order the picture lists them."""
    per_row, n = width // 4, cell // 4
    return [start + ((row * n + y) * per_row + col * n + x) * 16 for y in range(n) for x in range(n)]


def _keep_name(parts):
    """The backup's name: 1.DAT.original and 13.DAT.original as before, ROM-118-111.DAT.original for the others."""
    return (parts[-1] if parts[1] == "0" else "-".join(parts)) + ".original"


def _mark_one(kit, game, parts, marks, hd=None):
    """Draws the marks into one copy of the icon sheet (hd: the "hd" pictures for a "ustatshd" copy): True when
    changed, None when already done, else a message."""
    path = os.path.join(game, *parts)
    if not os.path.exists(path):
        return "missing"
    with open(path, "rb") as handle:
        data = bytearray(handle.read())
    if hd is None:
        start = _marks_texture(data)
        jobs = [(mark, 128, 16) for mark in marks]
    else:
        start = _marks_texture(data, b"ustatshd", (256, 256))
        jobs = [(mark, 256, 16) for mark in marks] + [(mark, 256, 32) for mark in hd]
    if start is None:
        return "not the expected file"
    todo = []
    for mark, width, cell in jobs:
        blocks = bytes.fromhex(mark["dxt3"])
        offsets = _cell_offsets(start, mark["row"], mark["col"], width, cell)
        if len(blocks) != cell * cell:
            return "the marks file is damaged"
        if any(bytes(data[o:o + 16]) != blocks[i * 16:(i + 1) * 16] for i, o in enumerate(offsets)):
            todo.append((mark, blocks, offsets))
    if not todo:
        return None
    keep = os.path.join(kit, "backups", "mode-marks-dat", _keep_name(parts))
    if not os.path.exists(keep):
        os.makedirs(os.path.dirname(keep), exist_ok=True)
        with open(keep, "wb") as handle:
            handle.write(data)
    for _mark, blocks, offsets in todo:
        for i, o in enumerate(offsets):
            data[o:o + 16] = blocks[i * 16:(i + 1) * 16]
    tmp = path + ".mm-tmp"
    with open(tmp, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)
    with open(path, "rb") as handle:
        back = handle.read()
    if any(back[o:o + 16] != blocks[i * 16:(i + 1) * 16] for _m, blocks, offsets in todo for i, o in enumerate(offsets)):
        return "did not read back as written; restore it from %s" % keep
    return True


def mode_marks(kit, game, log=print):
    # (2026-11-24) the game keeps four identical copies of "ustats" (ROM\0\1.DAT, ROM\0\13.DAT, ROM\118\111.DAT,
    # ROM\280\15.DAT; found by searching every game file for the goblet's pixels), and the current client draws the
    # marks from a later one, so all four are patched (only 1.DAT was, and the retail goblet kept showing)
    with open(os.path.join(kit, "client-patches", "mode_marks.json"), encoding="utf-8") as handle:
        sheet = json.load(handle)
    marks, hd = sheet["cells"], sheet.get("hd", {}).get("cells", [])
    changed, problems, found = False, [], 0
    for parts, pictures in [(p, None) for p in MARKS_FILES] + [(p, hd) for p in (MARKS_HD_FILES if hd else ())]:
        if not os.path.exists(os.path.join(game, *parts)):
            continue                            # not every game has every copy (an older one has no high-resolution sheet)
        found += 1
        result = _mark_one(kit, game, parts, marks, pictures)
        if result is True:
            changed = True
        elif result is not None:
            problems.append("%s: %s" % (parts[-1], result))
    if not found:
        return "Mode marks: the game's icon file is missing; hardcore characters show no mark beside their name."
    if problems and not changed:
        return "Mode marks: the game's icon files were left as they are (%s)." % "; ".join(problems)
    if not changed:
        return None
    note = (" (%s)" % "; ".join(problems)) if problems else ""
    return "Mode marks: the hardcore and Randomized shields and the new-player mark are in the game's icon sheet." + note


def restore_mode_marks(kit, game):
    import shutil
    done = False
    for parts in MARKS_FILES + MARKS_HD_FILES:
        keep = os.path.join(kit, "backups", "mode-marks-dat", _keep_name(parts))
        if os.path.exists(keep):
            shutil.copy2(keep, os.path.join(game, *parts))
            done = True
    return done


def apply_all(kit, game, server, log=print):
    """Runs the eight steps; returns the messages. Never raises."""
    messages = []
    for name, step in (("Home Points", lambda: homepoints(kit, game, server, log)),
                       ("Crystal Boy", lambda: crystalboy(kit, game, log)),
                       ("Chariot Band", lambda: chariot_band(kit, game, log)),
                       ("Item stacks", lambda: item_stacks(kit, game, server, log)),
                       ("Forever Beta Shirt", lambda: forever_beta_shirt(kit, game, log)),
                       ("Spells on squad mates", lambda: spell_targets(kit, game, log)),
                       ("Mode titles", lambda: mode_titles(kit, game, log)),
                       ("Mode marks", lambda: mode_marks(kit, game, log))):
        try:
            message = step()
        except PermissionError:
            message = (f"{name}: Windows did not let the launcher change the game files in {game}. "
                       "Run the launcher as administrator once (right-click > Run as administrator).")
        except Exception as problem:            # a game file that is not what we expect: leave it alone
            message = f"{name}: skipped ({problem})."
        if message:
            messages.append(message)
            log(message)
    return messages
