"""Tests for launcher_hardcore.py (no tkinter, no database): python test_hardcore.py [kit folder]"""
import json
import os
import shutil
import sys
import tempfile
import time

KIT = sys.argv[1] if len(sys.argv) > 1 else os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, KIT)
import launcher_hardcore as hc  # noqa: E402

passed = 0


def check(cond, msg):
    global passed
    if not cond:
        raise SystemExit("FAIL: " + msg)
    passed += 1
    print("ok  " + msg)


tmp = tempfile.mkdtemp()
try:
    shutil.copy(os.path.join(KIT, "hardcore_profiles.json"), tmp)
    server = os.path.join(tmp, "server")
    os.makedirs(os.path.join(server, "modules", "custom", "lua"))
    p = hc.profiles(tmp)
    check(p[1]["map.EXP_RATE"] == 1.0 and p[2]["map.EXP_RATE"] == 2.0 and p[3]["map.EXP_RATE"] == 3.5, "the three profiles load")
    check(p[2]["main.HOMEPOINT_TELEPORT"] == 0 and p[3]["main.ENABLE_SURVIVAL_GUIDE"] == 0, "Steel and Silver never teleport")
    check(p[1]["main.HOMEPOINT_TELEPORT"] == 1, "Iron keeps teleports")

    mine = {"map.EXP_RATE": 5.0, "bots": True, "bots_online": 42, "crowds_per_zone": 9, "ah_sim": True, "own_thing": 7}
    s = hc.session_rates(tmp, mine, 3)
    check(s["map.EXP_RATE"] == 3.5 and s["bots_online"] == 42 and s["crowds_per_zone"] == 9, "PLAY HARDCORE: profile over yours, bots kept")
    check(s["ah_sim"] is False and s["own_thing"] == 7 and mine["map.EXP_RATE"] == 5.0, "AH sim off; your dict untouched")
    check(hc.session_rates(tmp, {"ah_sim": True}, 4)["ah_sim"] is True and p[4]["map.EXP_RATE"] == 2.5,
          "PLAY RANDOMIZED keeps the auction house simulator; its new rates load")
    check(hc.session_rates(tmp, mine, 0) is mine, "plain PLAY: unchanged")

    hc.add_pending(tmp, server, "Steely", 2)
    hc.add_pending(tmp, server, "steely", 3)
    check(len(hc.settings(tmp)["pending"]) == 1 and hc.settings(tmp)["pending"][0]["mode"] == 3, "pending: one per name, last wins")
    probs = hc.write_server_files(tmp, server, True, "Hurami's World")
    check(probs == [], "server files written")
    folder = os.path.join(server, "modules", "custom", "lua")
    text = open(os.path.join(folder, "hardcore_profiles.lua")).read()
    check("['map.EXP_RATE'] = 3.5" in text and "['main.HOMEPOINT_TELEPORT'] = 0" in text and "bots" not in text, "profiles lua: character keys only")
    wtext = open(os.path.join(folder, "hardcore_world.lua")).read()
    check("hub = true" in wtext and "Hurami\\'s World" in wtext, "world lua")

    try:
        import lupa.luajit21 as L
        rt = L.LuaRuntime()
        for name in ("hardcore_profiles.lua", "hardcore_world.lua", "hardcore_pending.lua"):
            value = rt.execute(open(os.path.join(folder, name)).read())
            check(value is not None, name + " runs in LuaJIT")
        pend = rt.execute(open(os.path.join(folder, "hardcore_pending.lua")).read())
        check(pend[1]["name"].lower() == "steely" and pend[1]["mode"] == 3, "pending lua content")
    except ImportError:
        print("(lupa not installed: the Lua files were not run)")

    hc.forget_pending(tmp, ["STEELY"])
    check(hc.settings(tmp)["pending"] == [], "pending forgotten once it is hardcore")

    # the announcer
    posted, served = [], {"seq": 0, "lines": []}

    def opener(method, path, body):
        if method == "POST":
            posted.append(body)
            return {"ok": True}
        return served

    out = os.path.join(folder, "hardcore_out.txt")
    now = int(time.time())
    with open(out, "w") as f:
        f.write(f"{now}|milestone|Steely|Steel|WAR|20||Hurami's World\n{now - 9 * 86400}|death|Old|Silver|WHM|30|1d|X\nbroken line\n")
    a = hc.Announcer(tmp, server, "k" * 32, is_open=lambda: True, opener=opener)
    check(a.send_new() == 1 and posted[0]["name"] == "Steely" and posted[0]["level"] == 20, "a new line is sent, an old one is not")
    check(a.send_new() == 0, "nothing sent twice")
    with open(out, "a") as f:
        f.write(f"{now}|death|Silvia|Silver|WHM|30|2d 1h|Hurami's World\n")
    check(a.send_new() == 1 and posted[-1]["extra"] == "2d 1h", "the next line")
    s = hc.settings(tmp); s["share"] = False; hc.save_settings(tmp, s)
    with open(out, "a") as f:
        f.write(f"{now}|milestone|Silvia|Silver|WHM|40||Hurami's World\n")
    check(a.send_new() == 0 and len(posted) == 2, "sharing off: nothing goes online")

    served = {"seq": 5, "lines": [{"seq": 5, "text": "Old (Iron) reached level 10 on WAR."}]}
    check(a.fetch_others() == 0, "first look at the room only notes where it is")
    served = {"seq": 7, "lines": [{"seq": 6, "text": "Bob (Silver) has fallen: THF 50. Rest well."},
                                  {"seq": 7, "text": "Steely (Steel) reached level 20 on WAR in Hurami's World."}]}
    check(a.fetch_others() == 1, "another world's line comes in, this world's own does not")
    lines = open(os.path.join(folder, "hardcore_in.txt")).read().splitlines()
    check(lines == ["6|Bob (Silver) has fallen: THF 50. Rest well."], "hardcore_in.txt")
    a2 = hc.Announcer(tmp, server, "k" * 32, is_open=lambda: False, opener=opener)
    check(a2.fetch_others() == 0, "a world that is not open does not fetch")

    check(hc.survival_text(3 * 86400 + 4 * 3600) == "3d 4h" and hc.survival_text(65) == "1m", "survival text")
    check(hc.parse_out_line("1|start|A|Iron|WAR|1||W")["kind"] == "start", "parse a line")

    # the four mode titles go into a game title list laid out like the real one (ROM/180/78.DAT)
    import struct
    import launcher_client as lc
    game = os.path.join(tmp, "game")
    os.makedirs(os.path.join(game, "ROM", "180"))
    header = bytearray(0x40)
    header[:5] = b"d_msg"
    struct.pack_into("<I", header, 0x20, 0x100)
    body = b"".join(lc._title_entry("Fodderchief Flayer" if i == 1 else ("Eternal Master" if i == 1077 else "")) for i in range(1150))
    with open(os.path.join(game, "ROM", "180", "78.DAT"), "wb") as handle:
        handle.write(bytes(header) + body)
    first = lc.mode_titles(tmp, game)
    data = open(os.path.join(game, "ROM", "180", "78.DAT"), "rb").read()
    check(first and lc._title_text(data, 1081) == "Altana's Wild Card" and lc._title_text(data, 1077) == "Eternal Master",
          "mode titles written into slots 1078 - 1081, the rest untouched")
    check(lc.mode_titles(tmp, game) is None, "mode titles: nothing to do the second time")
    # the mode marks go into an icon sheet laid out like the game's ("ustats" in ROM/0/1.DAT)
    import shutil as _sh
    os.makedirs(os.path.join(game, "ROM", "0"))
    os.makedirs(os.path.join(tmp, "client-patches"), exist_ok=True)
    _sh.copy(os.path.join(KIT, "client-patches", "mode_marks.json"), os.path.join(tmp, "client-patches"))
    body = bytes([0xA1]) + b"menu    ustats  " + struct.pack("<IiiHHIIiiII", 40, 128, 64, 1, 32, 0, 0, 0, 0, 0, 16) \
        + b"3TXD" + struct.pack("<II", 8192, 0x80) + bytes(8192)
    body += bytes(-(16 + len(body)) % 16)
    chunk = b"ustt" + struct.pack("<I", ((16 + len(body)) // 16) << 7 | 0x20) + bytes(8) + body
    other = b"none" + struct.pack("<I", (32 // 16) << 7 | 0x01) + bytes(8) + bytes(16)
    with open(os.path.join(game, "ROM", "0", "1.DAT"), "wb") as handle:
        handle.write(other + chunk + other)
    first = lc.mode_marks(tmp, game)
    data = open(os.path.join(game, "ROM", "0", "1.DAT"), "rb").read()
    marks = json.load(open(os.path.join(KIT, "client-patches", "mode_marks.json")))["cells"]
    start = len(other) + 85
    iron = [m for m in marks if m["name"] == "iron"][0]
    offs = lc._cell_offsets(start, iron["row"], iron["col"])
    check(first and b"".join(data[o:o + 16] for o in offs) == bytes.fromhex(iron["dxt3"]) and data[:len(other)] == other
          and data[-len(other):] == other, "mode marks: the Iron shield lands in the leaf's cell, nothing else moves")
    check(lc.mode_marks(tmp, game) is None, "mode marks: nothing to do the second time")
    check(len(marks) == 5 and {m["name"] for m in marks} == {"iron", "steel", "silver", "random", "newplayer"},
          "mode marks: four shields and the new-player mark")
    import random as _random
    rolls = [hc.roll_randomized(_random.Random(n)) for n in range(200)]
    check(all(1 <= r["race"] <= 8 and 0 <= r["face"] <= 15 and 0 <= r["size"] <= 2 and r["zone"] in hc.START_ZONES[r["nation"]] for r in rolls)
          and {r["nation"] for r in rolls} == {0, 1, 2}, "Randomized roll: race, face, size, every nation and its starting cities")
    sdir = os.path.join(tmp, "srv")
    os.makedirs(os.path.join(sdir, "settings", "default"))
    open(os.path.join(sdir, "settings", "default", "main.lua"), "w").write("NEW_CHARACTER_CUTSCENE = 1,")
    check(hc._opening_cutscene(sdir), "opening cutscene setting read from the defaults")
    open(os.path.join(sdir, "settings", "main.lua"), "w").write("NEW_CHARACTER_CUTSCENE         = 0,")
    check(not hc._opening_cutscene(sdir), "and the world's own setting wins")
    check(lc.restore_mode_titles(tmp, game) and lc._title_text(open(os.path.join(game, "ROM", "180", "78.DAT"), "rb").read(), 1078) == "",
          "mode titles: the original comes back")
    # (2026-11-24) a deleted character leaves the waiting list (Kandra)
    import sqlite3
    pk = os.path.join(tmp, "prunekit")
    os.makedirs(pk)
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE chars(charid INTEGER, accid INTEGER, charname TEXT)")
    db.executemany("INSERT INTO chars VALUES(?, ?, ?)", [(10, 1000, "Livia"), (11, 1000, "Ironhide"), (12, 1000, "Reborn")])
    db.commit()
    hc.add_pending(pk, None, "Kandra", 4)              # Randomized, character deleted, no charid known (the old way)
    hc.add_pending(pk, None, "Livia", 4, 10)           # Randomized, still there
    hc.add_pending(pk, None, "Ironhide", 1)            # Iron, character exists: its charid gets remembered
    hc.add_pending(pk, None, "Futura", 2)              # Steel, not made on the creation screen yet: stays
    hc.add_pending(pk, None, "Reborn", 3)
    hc.prune_pending(pk, db)
    left = {e["name"]: e for e in hc.settings(pk)["pending"]}
    check(set(left) == {"Livia", "Ironhide", "Futura", "Reborn"}, "prune: a deleted Randomized character leaves the list")
    check(left["Ironhide"].get("charid") == 11 and "charid" not in left["Futura"], "prune: a seen character is remembered, an unmade one waits")
    db.execute("DELETE FROM chars WHERE charid = 11")
    db.execute("UPDATE chars SET charid = 99 WHERE charid = 12")   # Reborn deleted and a new Reborn made
    db.commit()
    gone = hc.prune_pending(pk, db)
    left = {e["name"] for e in hc.settings(pk)["pending"]}
    check(set(gone) == {"Ironhide", "Reborn"} and left == {"Livia", "Futura"},
          "prune: a seen Iron character that was deleted leaves, and an old entry doesn't pass to a new character of the same name")
    check("Ironhide" not in hc.pending_lua(pk) and "Futura" in hc.pending_lua(pk), "prune: the server's pending file follows")
    check(hc.prune_pending(pk, db) == [], "prune: nothing more to do the second time")
    # (2026-11-25) Randomized with permadeath and a random squad, asked when it is made
    hc.add_pending(pk, None, "Fated", 4, 50, perma=True, rsquad=True)
    hc.add_pending(pk, None, "Ironfist", 1, perma=True, rsquad=True)  # only Randomized takes the two
    lua = hc.pending_lua(pk)
    check("name = 'Fated', mode = 4, perma = 1, rsquad = 1 }" in lua and "name = 'Ironfist', mode = 1 }" in lua,
          "pending: permadeath and random squad go to the server for a Randomized character only")
    db.execute("CREATE TABLE char_vars(charid INTEGER, varname TEXT, value INTEGER)")
    db.execute("CREATE TABLE accounts_sessions(charid INTEGER)")
    db.executemany("INSERT INTO chars VALUES(?, ?, ?)", [(60, 1000, "Silv"), (61, 1000, "Perma"), (62, 1000, "Plain"), (63, 1000, "Fresh")])
    old = int(__import__("time").time()) - 8 * 86400
    db.executemany("INSERT INTO char_vars VALUES(?, ?, ?)", [(60, "[HC]Mode", 3), (60, "[HC]Dead", old),
                   (61, "[HC]Mode", 4), (61, "[HC]Perma", 1), (61, "[HC]Dead", old),
                   (62, "[HC]Mode", 4), (62, "[HC]Dead", old),
                   (63, "[HC]Mode", 4), (63, "[HC]Perma", 1), (63, "[HC]Dead", old + 7 * 86400)])
    db.commit()
    gone = hc.expire_fallen(db)
    check(sorted(gone) == ["Perma", "Silv"], "fallen: Silver and permadeath Randomized go after 7 days, not a normal Randomized or a recent fall")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print(f"{passed} checks passed")
