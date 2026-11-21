"""Game-file changes XI: Forever Offline makes to the player's FINAL FANTASY XI folder, after the era game files.

  1. Home Point teleport window: the era files only offer "Set home point"; 11 bytes per Home Point are put back
     (client-patches\\homepoints.json; only when the era files are installed, i.e. <kit>\\dat-backup exists).
  2. Crystal Boy items: the Crystal Boy and the four Recollections (ROM\\118\\107.DAT), the four Memory key items
     (ROM\\175\\35.DAT) and the Anniversary Ring made stackable (ROM\\118\\109.DAT) (install_crystalboy_items.py).
  3. Chariot Band: its description (+75%, 720 min, 4000), 3 charges and a 15-hour recast (client-patches\\chariot_band.json).
  4. Item stacks: today's stack sizes or the era's, to match the server (the "Modern item stacks" switch; stack_mode.py).
  5. Forever Beta Shirt (item 25725): its look (body model 399) and its item entry in ROM\\286\\73.DAT (forever_beta_shirt.py).

Every step checks first and only writes what is missing, so this runs at the end of first-run setup and again on
every PLAY of a player install (an update or a reinstalled era pack is caught the next time). A step that cannot be
done (a folder Windows won't let the launcher write, a file that is not the expected one) is reported and skipped;
it never stops the game from starting. Originals are kept in <kit>\\backups.
"""
import json
import os
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


def apply_all(kit, game, server, log=print):
    """Runs the five steps; returns the messages. Never raises."""
    messages = []
    for name, step in (("Home Points", lambda: homepoints(kit, game, server, log)),
                       ("Crystal Boy", lambda: crystalboy(kit, game, log)),
                       ("Chariot Band", lambda: chariot_band(kit, game, log)),
                       ("Item stacks", lambda: item_stacks(kit, game, server, log)),
                       ("Forever Beta Shirt", lambda: forever_beta_shirt(kit, game, log))):
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
