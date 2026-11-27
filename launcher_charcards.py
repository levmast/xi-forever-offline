"""Character cards (2026-11-25): PLAY shows a card per character on your account; picking one logs you straight in
(no character list), like the Hardcore menu's mode cards. No tkinter here; the window is launcher_charcards_gui.py.

How the log in is skipped: Ashita's stock autologin addon (atom0s; addons-src\\autologin is a copy, put into Ashita only
when Ashita has none) clicks through the game's menus to a character SLOT. For one launch the launcher puts a block at the
top of its start script:  /addon load autologin <slot>  and takes it out again at the next PLAY.

The slot is the character's place in the list the login server sends: your account's characters in charid order
(src/login/data_session.cpp, which says ORDER BY charid since 2026-11-25), the same joins and the same LIMIT as there.

The list is kept in charcards.json too, so the cards show before the world's database is running (a player install
starts its database at PLAY): it is read again whenever the database is up (the card screen, and the end of every game).

The picture: the character's own face, the character creation portrait of its race and face (assets\\faces, the ones the
Squad page and the website show), in the Hardcore cards' gold frame over its nation's colours.
"""
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = "charcards.json"
FACES = os.path.join(HERE, "assets", "faces")
FACE_FILES = {1: "Hm", 2: "Hf", 3: "Em", 4: "Ef", 5: "Tm", 6: "Tf", 7: "M", 8: "G"}   # as launcher_gui.FACE_FILES
FONT = os.path.join(HERE, "assets", "press", "fonts", "Galmuri11-Bold.ttf")
CARD = (232, 330)
BEGIN, END = "# xifo-autologin (written by PLAY's character cards: one launch only)", "# xifo-autologin end"

JOBS = ["WAR", "MNK", "WHM", "BLM", "RDM", "THF", "PLD", "DRK", "BST", "BRD", "RNG", "SAM", "NIN", "DRG", "SMN", "BLU",
        "COR", "PUP", "DNC", "SCH", "GEO", "RUN"]
NATIONS = {0: "sandoria", 1: "bastok", 2: "windurst"}
NATION_NAMES = {"sandoria": "San d'Oria", "bastok": "Bastok", "windurst": "Windurst"}
# card colours per nation: (top of the gradient, bottom, the name's colour, embers)
NATION_LOOK = {
    "sandoria": ((150, 40, 44), (26, 8, 10), (255, 226, 180), ("#ff8a6a", "#ffd890")),
    "bastok": ((52, 84, 150), (10, 16, 36), (214, 230, 255), ("#8cc0ff", "#e8f0ff")),
    "windurst": ((60, 124, 66), (10, 30, 14), (230, 255, 206), ("#a8f08c", "#fff6b0")),
}
HC_NAMES = {1: "IRON", 2: "STEEL", 3: "SILVER", 4: "RANDOM"}


# ------------------------------------------------------------------ the characters

def fetch(conn, login):
    """Your account's characters in slot order: [{slot, charid, name, race, face, nation, zone, mjob, mlvl, sjob, slvl,
    playtime, hc}]. login = config.json's game_user (the account PLAY logs in to)."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, content_ids FROM accounts WHERE login = ?", (login,))
        row = cur.fetchone()
        if not row:
            return []
        accid, limit = int(row[0]), max(1, int(row[1] or 3))
        # the login server's own list (data_session.cpp): the same joins, order and limit, so the slots match
        cur.execute("SELECT c.charid, c.charname, c.nation, c.pos_zone, l.race, l.face, s.mjob, s.sjob, s.mlvl, s.slvl "
                    "FROM chars c INNER JOIN char_stats s USING(charid) INNER JOIN char_look l USING(charid) "
                    "INNER JOIN char_jobs j USING(charid) WHERE c.accid = ? ORDER BY c.charid LIMIT ?", (accid, limit))
        rows = cur.fetchall()
        out = []
        for slot, r in enumerate(rows):
            charid = int(r[0])
            out.append({"slot": slot, "charid": charid, "name": str(r[1]), "nation": int(r[2] or 0), "zone": int(r[3] or 0),
                        "race": int(r[4] or 1), "face": int(r[5] or 0), "mjob": int(r[6] or 1), "sjob": int(r[7] or 0),
                        "mlvl": int(r[8] or 1), "slvl": int(r[9] or 0)})
        for c in out:
            c["zone_name"] = _zone_name(cur, c["zone"])
            c["playtime"] = _one(cur, "SELECT playtime FROM chars WHERE charid = ?", (c["charid"],), 0)
            c["hc"] = _one(cur, "SELECT value FROM char_vars WHERE charid = ? AND varname = '[HC]Mode'", (c["charid"],), 0)
            # (2026-11-25) permadeath (Silver, or a Randomized character made with it) and whether it has fallen
            c["perma"] = c["hc"] == 3 or (c["hc"] == 4 and bool(_one(cur, "SELECT value FROM char_vars WHERE charid = ? "
                                                                          "AND varname = '[HC]Perma'", (c["charid"],), 0)))
            c["dead"] = _one(cur, "SELECT value FROM char_vars WHERE charid = ? AND varname = '[HC]Dead'", (c["charid"],), 0) \
                if c["perma"] else 0
        return out
    finally:
        cur.close()
        try:
            conn.rollback()
        except Exception:
            pass


def _one(cur, sql, args, default):
    try:
        cur.execute(sql, args)
        row = cur.fetchone()
        return int(row[0] or 0) if row else default
    except Exception:
        return default


def _zone_name(cur, zone):
    try:
        cur.execute("SELECT name FROM zone_settings WHERE zoneid = ?", (zone,))
        row = cur.fetchone()
        return str(row[0]).replace("_", " ").replace("-", " - ") if row and row[0] else ""
    except Exception:
        return ""


def load_cache(kit, login):
    try:
        with open(os.path.join(kit, CACHE), encoding="utf-8") as f:
            data = json.load(f)
        return [c for c in data.get(str(login).lower(), []) if isinstance(c, dict) and "slot" in c]
    except (OSError, ValueError, AttributeError):
        return []


def save_cache(kit, login, chars):
    path = os.path.join(kit, CACHE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    data[str(login).lower()] = chars
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(path + ".tmp", path)


def refresh(kit, cfg, connect):
    """Reads the characters from the database (connect() -> a connection) into the cache. Returns them, or None.
    (2026-11-25) The second window's account (game_user2, setup_dualbox.py) is read and cached too: load_second()."""
    login = cfg.get("game_user", "")
    if not login:
        return None
    conn = connect()
    try:
        chars = fetch(conn, login)
        second = cfg.get("game_user2", "")
        if second and second.lower() != login.lower():
            twos = fetch(conn, second)
            for c in twos:
                c["dualbox"] = True
            save_cache(kit, second, twos)
    finally:
        conn.close()
    save_cache(kit, login, chars)
    return chars


def load_second(kit, cfg):
    """The second window's characters (dualbox cards), from the cache; [] when there is no second window."""
    second = cfg.get("game_user2", "")
    if not second or second.lower() == str(cfg.get("game_user", "")).lower():
        return []
    out = load_cache(kit, second)
    for c in out:
        c["dualbox"] = True
    return out


def save_config_value(kit, key, value):
    """One value in config.json (as launcher_gui.save_config_value)."""
    path = os.path.join(kit, "config.json")
    with open(path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg[key] = value
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def job_line(c):
    main = JOBS[c["mjob"] - 1] if 1 <= c.get("mjob", 0) <= len(JOBS) else "?"
    line = f"{main} {c.get('mlvl', 1)}"
    if c.get("sjob") and 1 <= c["sjob"] <= len(JOBS) and c.get("slvl"):
        line += f" / {JOBS[c['sjob'] - 1]} {c['slvl']}"
    return line


def played(seconds):
    h = int(seconds or 0) // 3600
    return f"{h} h played" if h else "new"


# ------------------------------------------------------------------ the autologin block in the start script

def set_autologin(script_path, slot):
    """Puts (slot = 0..15) or takes out (slot = None) the one-launch autologin block at the top of the start script.
    It goes right after "/load addons" (the /addon command needs it), before any /wait, so it is set up before the log in."""
    try:
        with open(script_path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return False
    kept, inside = [], False
    for line in lines:
        if line.strip() == BEGIN:
            inside = True
            continue
        if inside:
            if line.strip() == END:
                inside = False
            continue
        kept.append(line)
    if slot is not None:
        # (2026-11-25, the user: "it doesn't skip the login") /addon only exists once Ashita's add-on loader is up, so the
        # block goes right after "/load addons" (still before any /wait); a script without that line gets it in the block
        block = [BEGIN, f"/addon load autologin {int(slot)}", END]
        at = next((i for i, l in enumerate(kept) if l.strip().lower() == "/load addons"), None)
        if at is None:
            kept = [BEGIN, "/load addons", f"/addon load autologin {int(slot)}", END] + kept
        else:
            kept = kept[:at + 1] + block + kept[at + 1:]
    with open(script_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(kept).rstrip("\n") + "\n")
    return True


def ensure_addon(kit, ashita_dir):
    """Ashita's autologin addon, copied from the kit only when this Ashita has none (a newer stock one is kept)."""
    if not ashita_dir:
        return False
    dest = os.path.join(ashita_dir, "addons", "autologin")
    if os.path.isfile(os.path.join(dest, "autologin.lua")):
        return True
    src = os.path.join(kit, "addons-src", "autologin")
    if not os.path.isfile(os.path.join(src, "autologin.lua")):
        return False
    shutil.copytree(src, dest, dirs_exist_ok=True)
    return True


# ------------------------------------------------------------------ the pictures

def face_path(c):
    """assets\\faces\\<race><1-8><a|b>.jpg for this character (game face 0..15 = 1A, 1B, ... 8B)."""
    face = max(0, min(15, int(c.get("face", 0))))
    return os.path.join(FACES, f"{FACE_FILES.get(int(c.get('race', 1)), 'Hm')}{face // 2 + 1}{'ab'[face % 2]}.jpg")


# ------------------------------------------------------------------ the looks: every launcher theme, every kind of character
# kind: "regular", "iron", "steel", "silver", "random" (the Hardcore modes, [HC]Mode 1-4) or "dualbox" (the second window)
KINDS = ("regular", "iron", "steel", "silver", "random", "dualbox")
HC_KEYS = {1: "iron", 2: "steel", 3: "silver", 4: "random"}
KIND_LABEL = {"regular": "", "iron": "IRON", "steel": "STEEL", "silver": "SILVER", "random": "RANDOMIZED", "dualbox": "2ND WINDOW"}
# each look's border colours per kind: (light, dark, accent for the name and the sparks)
METALS = {
    "playoffline": {
        "regular": ((213, 244, 255), (53, 92, 123), (133, 204, 233)),
        "iron": ((224, 225, 227), (68, 79, 88), (162, 180, 192)),
        "steel": ((201, 227, 245), (46, 70, 102), (139, 184, 216)),
        "silver": ((246, 249, 255), (91, 106, 133), (203, 215, 235)),
        "random": ((232, 208, 255), (79, 62, 113), (199, 165, 225)),
        "dualbox": ((185, 248, 236), (44, 91, 94), (129, 219, 207)),
    },
    "classic": {"regular": ((250, 226, 150), (176, 128, 46), (255, 226, 160)), "iron": ((206, 210, 220), (92, 96, 108), (214, 218, 228)),
                "steel": ((176, 210, 250), (52, 90, 150), (180, 214, 255)), "silver": ((250, 250, 255), (170, 172, 186), (255, 120, 100)),
                "random": ((226, 196, 255), (120, 70, 190), (230, 200, 255)), "dualbox": ((150, 240, 226), (30, 140, 136), (160, 250, 236))},
    "chronicle": {"regular": ((236, 196, 110), (128, 82, 30), (120, 30, 22)), "iron": ((176, 172, 166), (70, 66, 62), (60, 58, 56)),
                  "steel": ((150, 178, 206), (52, 74, 110), (40, 66, 110)), "silver": ((236, 232, 226), (150, 140, 130), (150, 20, 20)),
                  "random": ((206, 170, 230), (100, 56, 130), (96, 40, 130)), "dualbox": ((140, 206, 190), (40, 110, 100), (30, 100, 90))},
    "aero": {"regular": ((230, 246, 255), (60, 150, 220), (10, 90, 170)), "iron": ((236, 238, 242), (110, 116, 128), (60, 66, 80)),
             "steel": ((214, 236, 255), (40, 110, 200), (20, 70, 150)), "silver": ((255, 255, 255), (196, 70, 80), (180, 30, 50)),
             "random": ((244, 226, 255), (150, 90, 220), (110, 50, 180)), "dualbox": ((220, 255, 250), (20, 170, 160), (0, 120, 110))},
    "vaporwave": {"regular": ((255, 140, 220), (255, 92, 203), (255, 120, 220)), "iron": ((200, 220, 240), (120, 150, 190), (200, 230, 255)),
                  "steel": ((120, 220, 255), (40, 140, 255), (110, 220, 255)), "silver": ((255, 250, 255), (255, 70, 110), (255, 90, 120)),
                  "random": ((210, 150, 255), (150, 70, 255), (220, 160, 255)), "dualbox": ((120, 255, 230), (0, 220, 200), (120, 255, 230))},
    "windurst": {"regular": ((246, 214, 120), (52, 118, 62), (40, 96, 50)), "iron": ((206, 204, 190), (96, 100, 84), (70, 76, 60)),
                 "steel": ((170, 210, 236), (48, 96, 140), (36, 80, 120)), "silver": ((250, 246, 230), (150, 46, 40), (150, 46, 40)),
                 "random": ((220, 196, 246), (110, 76, 160), (100, 60, 150)), "dualbox": ((180, 236, 170), (40, 130, 70), (30, 110, 60))},
    "8bit": {"regular": ((252, 252, 252), (188, 188, 188), (252, 208, 64)), "iron": ((188, 188, 188), (116, 116, 116), (252, 252, 252)),
             "steel": ((60, 188, 252), (0, 88, 248), (164, 228, 252)), "silver": ((252, 252, 252), (228, 0, 88), (252, 160, 68)),
             "random": ((216, 120, 248), (104, 68, 252), (248, 184, 248)), "dualbox": ((88, 248, 152), (0, 168, 68), (184, 248, 184))},
}
# each look's colours round the picture: card top, card bottom, the panel under the name, the small text
LOOK_PANELS = {
    "playoffline": ((75, 113, 145), (31, 56, 78), (28, 51, 72, 242), (212, 232, 246)),
    "classic": ((40, 36, 46), (10, 8, 12), (8, 6, 10, 210), (230, 216, 180)),
    "chronicle": ((60, 38, 22), (30, 18, 10), (236, 222, 186, 240), (80, 56, 34)),
    "aero": ((210, 236, 250), (150, 200, 236), (240, 250, 255, 225), (30, 70, 110)),
    "vaporwave": ((40, 14, 70), (14, 6, 30), (20, 8, 44, 215), (240, 200, 255)),
    "windurst": ((70, 120, 70), (24, 50, 30), (250, 242, 214, 238), (40, 70, 40)),
    "8bit": ((20, 28, 140), (6, 8, 28), (20, 28, 140, 255), (252, 252, 252)),
}


def look_key():
    """The launcher's look now: "classic" (its own), "chronicle", "aero", "vaporwave", "8bit" or "windurst" (launcher_theme.worn)."""
    try:
        import launcher_theme
        key = launcher_theme.worn() or ""
    except Exception:
        key = ""
    key = key.split("__")[0].lower()
    return key if key in METALS else "classic"


def spark_colours(c, look=None):
    """The sparks a lit card sends up: its border's colours."""
    look = look or look_key()
    light, dark, accent = METALS[look][kind_of(c) if c else "regular"]
    return tuple("#%02x%02x%02x" % tuple(v) for v in (light, accent, dark))


def kind_of(c):
    if c.get("dualbox"):
        return "dualbox"
    return HC_KEYS.get(int(c.get("hc") or 0), "regular")


def _font(size, look="8bit"):
    from PIL import ImageFont
    windows = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    wanted = {"playoffline": ["tahomabd.ttf", "DejaVuSans-Bold.ttf"],
              "classic": ["georgiab.ttf", "Caladea-Bold.ttf", "DejaVuSerif-Bold.ttf"],
              "chronicle": ["georgiab.ttf", "Caladea-Bold.ttf", "DejaVuSerif-Bold.ttf"],
              "aero": ["segoeuib.ttf", "DejaVuSans-Bold.ttf"],
              "vaporwave": ["ariblk.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]}.get(look, [])
    for name in wanted:
        for folder in (windows, "/usr/share/fonts/truetype/crosextra", "/usr/share/fonts/truetype/dejavu"):
            try:
                return ImageFont.truetype(os.path.join(folder, name), size)
            except OSError:
                continue
    try:
        return ImageFont.truetype(FONT, 11 * max(1, round(size / 11)))   # Galmuri: crisp at 11, 22, 33
    except OSError:
        return ImageFont.load_default()


def _mix(a, b, t):
    return tuple(int(a[k] * (1 - t) + b[k] * t) for k in range(3))


def _icon(kind, look, size):
    """The Hardcore mode's shield (assets\\ui\\hc_icon_<mode>.png), or the second window's "2" badge."""
    from PIL import Image, ImageDraw
    if kind in ("iron", "steel", "silver", "random"):
        try:
            im = Image.open(os.path.join(HERE, "assets", "ui", f"hc_icon_{kind}.png")).convert("RGBA")
            im = im.resize((size, size), Image.LANCZOS if look != "8bit" else Image.NEAREST)
            if look == "8bit":                                   # chunky: down to a few pixels and back
                im = im.resize((size // 3, size // 3), Image.BOX).resize((size, size), Image.NEAREST)
            return im
        except OSError:
            return None
    if kind == "dualbox":
        light, dark, accent = METALS[look]["dualbox"]
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if look == "8bit":
            d.rectangle([2, 2, size - 3, size - 3], fill=(0, 0, 0), outline=light, width=3)
        else:
            d.ellipse([1, 1, size - 2, size - 2], fill=dark, outline=(16, 12, 8), width=2)
            d.ellipse([5, 5, size - 6, size - 6], outline=light, width=2)
        _text(d, (size // 2, size // 2 + 1), "2", _font(int(size * 0.55), look), (255, 255, 255), shadow=(0, 0, 0))
        return im
    return None


def _photo_for(look, photo):
    """The portrait as each look wants it: as it is, warmer (Chronicle), neon duotone (Vaporwave), chunky pixels (8-Bit)."""
    from PIL import Image, ImageEnhance, ImageOps
    if look == "8bit":
        small = photo.convert("RGB").resize((photo.width // 4, photo.height // 4), Image.BOX)
        small = small.quantize(colors=24, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).convert("RGBA")
        out = small.resize(photo.size, Image.NEAREST)
        out.putalpha(photo.split()[3])
        return out
    if look == "vaporwave":
        grey = ImageOps.grayscale(photo.convert("RGB"))
        tone = ImageOps.colorize(grey, (40, 10, 90), (255, 150, 230), mid=(150, 60, 200)).convert("RGBA")
        out = Image.blend(photo.convert("RGBA"), tone, 0.55)
        out.putalpha(photo.split()[3])
        return out
    if look == "chronicle":
        out = ImageEnhance.Color(photo).enhance(0.8)
        warm = Image.new("RGBA", photo.size, (120, 80, 30, 0))
        warm.putalpha(photo.split()[3].point(lambda v: int(v * 0.18)))
        out.alpha_composite(warm)
        return out
    return photo


def _border(card, look, kind, lit):
    """Each look's border, in the colours of the kind of character. Dualbox: two lines (twin borders)."""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = card.size
    light, dark, accent = METALS[look][kind]
    if lit:
        light, dark = _mix(light, (255, 255, 255), 0.35), _mix(dark, light, 0.35)
    d = ImageDraw.Draw(card)
    twin = kind == "dualbox"
    if look == "8bit":                                           # chunky pixels, notched corners, no smoothing
        for i, col in enumerate((0, light, light, dark, 0)):
            c = (0, 0, 0) if col == 0 else col
            d.rectangle([i * 2, i * 2, w - 1 - i * 2, h - 1 - i * 2], outline=c, width=2)
        for x0, y0 in ((0, 0), (w - 8, 0), (0, h - 8), (w - 8, h - 8)):
            d.rectangle([x0, y0, x0 + 7, y0 + 7], fill=(0, 0, 0, 0))
        for x0, y0 in ((4, 4), (w - 8, 4), (4, h - 8), (w - 8, h - 8)):   # a pixel step inside each notch
            d.rectangle([x0, y0, x0 + 3, y0 + 3], fill=light)
        if twin:
            d.rectangle([14, 14, w - 15, h - 15], outline=light, width=2)
        return card
    if look == "vaporwave":                                      # neon tubes: a blurred glow and a bright core
        glow = Image.new("RGBA", card.size, (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        lines = [3] + ([12] if twin else [])
        for inset in lines:
            g.rounded_rectangle([inset, inset, w - 1 - inset, h - 1 - inset], radius=10, outline=dark + (255,), width=4)
        card.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5 if lit else 3)))
        for inset in lines:
            d.rounded_rectangle([inset, inset, w - 1 - inset, h - 1 - inset], radius=10, outline=light, width=2)
        return card
    if look in ("aero", "playoffline"):                          # glass: rounded, glossy top, soft blue rim
        for i in range(4):
            t = i / 3
            d.rounded_rectangle([i, i, w - 1 - i, h - 1 - i], radius=14 - i, outline=_mix(light, dark, t), width=1)
        gloss = Image.new("RGBA", card.size, (0, 0, 0, 0))               # a shine along the top of the rim only
        ImageDraw.Draw(gloss).rounded_rectangle([5, 5, w - 6, h - 6], radius=11, outline=(255, 255, 255, 150), width=2)
        ImageDraw.Draw(gloss).rectangle([0, h // 3, w, h], fill=(0, 0, 0, 0))
        card.alpha_composite(gloss)
        if twin:
            d.rounded_rectangle([10, 10, w - 11, h - 11], radius=9, outline=dark, width=2)
        return card
    if look == "chronicle":                                      # a bookplate: wood, a metal band, notched corners
        d.rectangle([0, 0, w - 1, h - 1], outline=(40, 22, 10), width=4)
        for i in range(3):
            d.rectangle([4 + i, 4 + i, w - 5 - i, h - 5 - i], outline=_mix(light, dark, i / 2))
        d.rectangle([7, 7, w - 8, h - 8], outline=(40, 22, 10))
        for cx, cy in ((0, 0), (w, 0), (0, h), (w, h)):
            d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(0, 0, 0, 0))
            d.arc([cx - 16, cy - 16, cx + 16, cy + 16], 0, 360, fill=light, width=3)
        if twin:
            d.rectangle([12, 12, w - 13, h - 13], outline=dark, width=2)
        return card
    # classic: the Hardcore cards' frame (ink, a metal band, ink) and a small diamond top and bottom
    d.rectangle([0, 0, w - 1, h - 1], outline=(16, 12, 8))
    for i in range(3):
        d.rectangle([1 + i, 1 + i, w - 2 - i, h - 2 - i], outline=_mix(light, dark, i / 2))
    d.rectangle([4, 4, w - 5, h - 5], outline=(16, 12, 8))
    if twin:
        d.rectangle([9, 9, w - 10, h - 10], outline=(16, 12, 8))
        d.rectangle([10, 10, w - 11, h - 11], outline=light, width=2)
        d.rectangle([12, 12, w - 13, h - 13], outline=(16, 12, 8))
    for y in (2, h - 3):
        d.polygon([(w // 2, y - 4), (w // 2 + 5, y), (w // 2, y + 4), (w // 2 - 5, y)], fill=light, outline=(16, 12, 8))
    return card


def _text(d, xy, s, f, fill, anchor="mm", shadow=(0, 0, 0)):
    x, y = xy
    if shadow:
        for dx, dy in ((1, 1), (2, 2)):
            d.text((x + dx, y + dy), s, font=f, fill=shadow, anchor=anchor)
    d.text((x, y), s, font=f, fill=fill, anchor=anchor)


def render_card(c, lit=False, look=None):
    """One character's card (232 x 330) in the launcher's look: the portrait, the name, job and place, a border that
    says what kind of character it is (regular, Iron, Steel, Silver, Randomized, second window) and the mode's shield."""
    from PIL import Image, ImageDraw, ImageEnhance
    look = look or look_key()
    kind = kind_of(c)
    w, h = CARD
    top, bottom, panel, small = LOOK_PANELS[look]
    light, dark, accent = METALS[look][kind]
    card = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(card)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=_mix(top, bottom, y / (h - 1)) + (255,))
    inset = 8 if look != "8bit" else 12
    try:                                                      # the character's portrait, fading into the card
        photo = Image.open(face_path(c)).convert("RGBA")
        pw, ph = w - inset * 2, 236 - inset
        k = max(pw / photo.width, ph / photo.height)
        photo = photo.resize((round(photo.width * k), round(photo.height * k)), Image.LANCZOS)
        x0 = (photo.width - pw) // 2
        photo = _photo_for(look, photo.crop((x0, 0, x0 + pw, ph)))
        if look != "8bit":
            fade = Image.linear_gradient("L").resize(photo.size).point(lambda v: 255 if v < 160 else max(0, 255 - (v - 160) * 3))
            photo.putalpha(fade)
        card.alpha_composite(photo, (inset, inset))
    except OSError:
        pass
    if lit:
        card = ImageEnhance.Brightness(card).enhance(1.1)
    # the name panel
    plate = Image.new("RGBA", (w, 96), (0, 0, 0, 0))
    pd = ImageDraw.Draw(plate)
    if look == "8bit":
        pd.rectangle([inset, 6, w - inset - 1, 95 - inset + 4], fill=panel, outline=(252, 252, 252), width=2)
    else:
        for y in range(96):
            a = int(panel[3] * min(1.0, y / 28))
            pd.line([(0, y), (w, y)], fill=panel[:3] + (a,))
    card.alpha_composite(plate, (0, h - 96))
    d = ImageDraw.Draw(card)
    name = c.get("name", "?")
    name_colour = accent if look != "chronicle" else (60, 34, 18)
    shadow = None if look in ("chronicle", "aero") else (0, 0, 0)
    big = 26 if look != "8bit" else 22
    if len(name) > 11:
        big = 20 if look != "8bit" else 11
    _text(d, (w // 2, h - 70), name.upper() if look != "chronicle" else name, _font(big, look), name_colour, shadow=shadow)
    _text(d, (w // 2, h - 45), job_line(c), _font(12 if look != "8bit" else 11, look), small, shadow=shadow)
    where = c.get("zone_name") or NATION_NAMES[NATIONS.get(c.get("nation", 0), "sandoria")]
    _text(d, (w // 2, h - 28), where[:30], _font(11, look), _mix(small, panel[:3], 0.3), shadow=shadow)
    label = KIND_LABEL[kind]
    if kind == "random" and c.get("perma"):
        label = "PERMA RANDOMIZED"                    # (2026-11-25) made with permadeath
    if c.get("perma") and c.get("dead"):                  # fallen for good: grey, with FALLEN across the picture
        grey = ImageEnhance.Color(card).enhance(0.15)
        card = ImageEnhance.Brightness(grey).enhance(0.6)
        d = ImageDraw.Draw(card)
        _text(d, (w // 2, 120), "FALLEN", _font(30 if look != "8bit" else 26, look), (230, 70, 60), shadow=(0, 0, 0))
    if label:                                                  # the kind, as a small ribbon under the picture
        f = _font(11, look)
        tw = int(d.textlength(label, font=f)) + 16
        y = h - 98
        d.rectangle([w // 2 - tw // 2, y - 8, w // 2 + tw // 2, y + 8], fill=dark, outline=(16, 12, 8))
        _text(d, (w // 2, y), label, f, (255, 255, 255), shadow=(0, 0, 0) if look != "aero" else None)
    card = _border(card, look, kind, lit)
    icon = _icon(kind, look, 50)
    if icon is not None:                                       # the mode's shield, pinned to the top-left corner
        card.alpha_composite(icon, (10, 10))
    return card


def render_screen_card(lit=False, look=None):
    """The last card: the game's own character screen (to make a new character, or pick one yourself)."""
    from PIL import Image, ImageDraw
    look = look or look_key()
    w, h = CARD
    top, bottom, panel, small = LOOK_PANELS[look]
    light, dark, accent = METALS[look]["regular"]
    card = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(card)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=_mix(top, bottom, y / (h - 1)) + (255,))
    plus = _mix(accent, (255, 255, 255), 0.3) if lit else accent
    if look == "chronicle":                               # parchment ink on this look's dark leather (2026-11-25)
        plus = (226, 196, 140) if not lit else (255, 226, 170)
        small = (196, 172, 130)
    d.rectangle([w // 2 - 4, 90, w // 2 + 4, 170], fill=plus)
    d.rectangle([w // 2 - 40, 126, w // 2 + 40, 134], fill=plus)
    shadow = None if look == "aero" else (0, 0, 0)
    _text(d, (w // 2, 246), "CREATE A", _font(20 if look != "8bit" else 22, look), plus, shadow=shadow)
    _text(d, (w // 2, 272), "CHARACTER", _font(20 if look != "8bit" else 22, look), plus, shadow=shadow)
    _text(d, (w // 2, 298), "or choose one in the game", _font(11, look), small, shadow=shadow)
    return _border(card, look, "regular", lit)


def render_choice_card(title, lines, kind="regular", lit=False, look=None, mark=None):
    """(2026-11-25) A card for one step of CREATE A CHARACTER (Normal / Hardcore / Randomized, Yes / No, Main / 2nd
    window): a title, a few short lines, the border of the kind it leads to and that kind's shield (mark: "plus",
    "skull", "dice", "window" or None)."""
    from PIL import Image, ImageDraw
    look = look or look_key()
    w, h = CARD
    top, bottom, panel, small = LOOK_PANELS[look]
    light, dark, accent = METALS[look][kind]
    card = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(card)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=_mix(top, bottom, y / (h - 1)) + (255,))
    ink = _mix(accent, (255, 255, 255), 0.3) if lit else accent
    if look == "chronicle":                               # parchment ink on the dark leather of this look
        ink = (226, 196, 140) if not lit else (255, 226, 170)
        small = (196, 172, 130)
    shadow = None if look in ("aero",) else (0, 0, 0)
    icon = _icon(kind, look, 96) if kind != "regular" else None
    cx, cy = w // 2, 120
    if icon is not None and mark is None:
        card.alpha_composite(icon, (cx - icon.width // 2, cy - icon.height // 2))
    elif mark == "plus" or (mark is None and icon is None):
        d.rectangle([cx - 4, cy - 40, cx + 4, cy + 40], fill=ink)
        d.rectangle([cx - 40, cy - 4, cx + 40, cy + 4], fill=ink)
    elif mark == "skull":
        d.ellipse([cx - 34, cy - 40, cx + 34, cy + 22], fill=ink)
        d.rectangle([cx - 20, cy + 14, cx + 20, cy + 38], fill=ink)
        for ex in (cx - 15, cx + 15):
            d.ellipse([ex - 10, cy - 16, ex + 10, cy + 4], fill=_mix(top, bottom, 0.4))
        for tx in range(cx - 14, cx + 15, 9):
            d.line([(tx, cy + 22), (tx, cy + 38)], fill=_mix(top, bottom, 0.4), width=2)
    elif mark == "dice":
        for ox, oy in ((-26, -18), (18, 6)):
            d.rectangle([cx + ox - 22, cy + oy - 22, cx + ox + 22, cy + oy + 22], outline=ink, width=4)
            for px, py in ((-10, -10), (0, 0), (10, 10)):
                d.ellipse([cx + ox + px - 4, cy + oy + py - 4, cx + ox + px + 4, cy + oy + py + 4], fill=ink)
    elif mark == "window":
        for ox, oy in ((-16, -14), (14, 12)):
            d.rectangle([cx + ox - 34, cy + oy - 26, cx + ox + 34, cy + oy + 26], outline=ink, width=4, fill=_mix(top, bottom, 0.5))
            d.rectangle([cx + ox - 34, cy + oy - 26, cx + ox + 34, cy + oy - 16], fill=ink)
    elif mark == "one":
        d.rectangle([cx - 36, cy - 28, cx + 36, cy + 28], outline=ink, width=4)
        d.rectangle([cx - 36, cy - 28, cx + 36, cy - 18], fill=ink)
    big = 22 if look != "8bit" else 18
    if len(title) > 12:
        big = 18 if look != "8bit" else 14
    _text(d, (w // 2, 216), title.upper() if look != "chronicle" else title, _font(big, look), ink, shadow=shadow)
    y = 246
    for line in lines[:4]:
        _text(d, (w // 2, y), line, _font(11, look), small, shadow=shadow)
        y += 18
    return _border(card, look, kind, lit)
