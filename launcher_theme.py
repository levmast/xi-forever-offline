"""Themes for the launcher: its colours, its own buttons and an opening theme, picked on the Theme page (OPTIONS > Theme).

A theme is a .json in assets\\press with a "colours" table. Two kinds, told apart by the file's name:
    vaporwave__until-2026-12-02.json    a limited-time theme (named like the limited-time banners, name__until-YEAR-MONTH-DAY): it
                                        turns itself on when it arrives and is gone, by itself, the day after its date
    windurst.json                       a theme that is always there to pick; it is never on unless the player picks it
What a theme's .json may hold:
    "name"      what the Theme page calls it (otherwise the file's name)
    "colours"   the launcher's palette: BG, PANEL, GOLD ... (the names at the top of launcher_widgets.py); names left out stay as usual
    "art"       its own buttons: {"folder": "vaporwave-ui"}, a folder in assets\\press whose pictures stand in for the ones in
                assets\\ui, name for name (or a tint for the usual ones: {"ramp": [...], "mix": 0.7})
    "sound"     its own opening theme: the name of a .mp3 / .wav in assets\\press
    "font"      its own lettering for the launcher's text: {"family": "Pixelify Sans", "files": ["fonts/PixelifySans-Regular.ttf",
                "fonts/PixelifySans-Bold.ttf"]}, .ttf files in assets\\press (kept to this program, nothing is installed on the PC)
                and the name they go by. A font whose letters are about as wide as the usual ones keeps every label in its place.
A theme's own banners are pictures in assets\\press with __theme- and its short name in their name (title__theme-8bit.png): shown only
while that theme is worn, and then in place of the usual ones.
A dated .mp3 / .wav (theme__until-2026-12-02.mp3) is the opening theme of the limited-time theme of those days: played once when the
launcher opens. A limited-time theme also has the limited-time banners of its days. A song can also say when it starts
(newer__from-2026-11-24__until-2026-12-02.mp3): from that day on it takes over from the one that was playing. Or how often it
is played (opener__plays-3__until-2026-12-02.mp3): it opens the launcher three times on a PC, ahead of the theme's other song, and
then never again there.
default.mp3 (or default.wav) in assets\\press is the launcher's own opening theme: it plays with the Default look, and with any theme
that has no song of its own.
music.json in assets\\press says who made the songs: the Theme page names the song that plays and its maker from it, and shows its
"credit" sentence. A new song needs a line there (and in CREDITS.md and the patch notes).

The Theme page is there whenever there is something to choose (a theme to pick, or a song to switch off): a switch for Default (the
launcher's own look) and one for every theme, the song on / off and its volume. The classic look has no such page: there the same sit in a small strip on the banner.
config.json keeps the choices:
    "theme": "default" or a theme's short name (its file name without the date)      what was picked; nothing = no pick
    "theme_event": the limited-time theme that was in date when the pick was made: a pick holds back that one only, so the next
                   limited-time theme shows by itself again, and the pick is back when it has gone
    "theme_music": false    the song is off          "theme_volume": 0.0 to 1.0    how loud it is
    "theme_plays": {"opener": 3}    how often a song with __plays- in its name has opened the launcher here (by its name up to the first tag)
("limited_look": false, written by the first Theme page for "off", still counts as Default.)
A theme whose .json says "standard": true (aero.json, from 2026-11-23) is what a PC wears when nothing is picked, ahead of any
limited-time theme: it takes the place of the launcher's own look, which stays on the Theme page as "Classic" (key "default").

The three files that define the launcher's colours (launcher_gui.pyw, launcher_widgets.py, launcher_coop_gui.py) each call colours()
right after their own, launcher_pages.build() calls add_page(app, tabs) and launcher_gui's main() calls start(app). Nothing in here
can stop the launcher: any problem at all means the usual look and no sound."""
import atexit
import ctypes
import datetime
import json
import os
import tempfile
import shutil
import subprocess
import sys
import time
import tkinter as tk
from tkinter import messagebox

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))  # the kit folder
PRESS = os.path.join(HERE, "assets", "press")


def note(text):
    """(2026-11-23, the user: players may not hear the launcher's music) one line in logs\\theme-music.log, so a song that
    does not play says why."""
    try:
        import time
        folder = os.path.join(HERE, "logs")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "theme-music.log"), "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except Exception:
        pass
UNTIL_TAG = "__until-"
FROM_TAG = "__from-"             # ... and a song with __from-2026-11-24 in its name is not used before that day
PLAYS_TAG = "__plays-"           # ... and a song with __plays-3 in its name opens the launcher three times on a PC, then never again
TINTED = ("ui", "buttons")       # the folders of assets whose pictures a look may replace or tint
BUTTON_KINDS = {"play": "play", "stop": "stop", "dual": "dualbox"}     # assets\\buttons\\<kind>\\ holds variants of these assets\\ui pictures
SOUNDS = (".mp3", ".wav")
OWN_SOUNDS = ("default.mp3", "default.wav")        # the launcher's own opening theme, in assets\\press (the first one that is there)
MUSIC = "music.json"             # who made the songs, in assets\\press: see music_notes()
VOLUME = 0.55
DEFAULT = "default"              # the launcher's own look, as the Theme page and config.json call it
PALETTE = ("BG", "PANEL", "PANEL2", "FG", "DIM", "BORDER", "LINE", "OFF", "GOLD", "GOLD_LIT", "GOLD_DIM", "PARCH", "ACCENT", "GREEN", "RED", "GREY")
OWN = {}                         # the launcher's own colours, noted as its files hand them to colours(): what Default looks like
FONT_NAMES = ("UI_FONT", "_UI_FONT")               # the names the launcher's files keep their text font under


def today():
    """Today on this PC, written 2026-12-02 (a function of its own so the tests can pick the day)."""
    return time.strftime("%Y-%m-%d")


def until(name):
    """The last day a dated file is used: the date after __until- in its name. "" when it has none, "0" (over) when it cannot be read."""
    low = name.lower()
    cut = low.find(UNTIL_TAG)
    if cut < 0:
        return ""
    day = low[cut + len(UNTIL_TAG):cut + len(UNTIL_TAG) + 10]
    return day if len(day) == 10 and day[4] == "-" and day[7] == "-" and (day[:4] + day[5:7] + day[8:]).isdigit() else "0"


def since(name):
    """The first day a dated file is used: the date after __from- in its name. "" when it has none (from the start), "9" (never) when
    it cannot be read."""
    low = name.lower()
    cut = low.find(FROM_TAG)
    if cut < 0:
        return ""
    day = low[cut + len(FROM_TAG):cut + len(FROM_TAG) + 10]
    return day if len(day) == 10 and day[4] == "-" and day[7] == "-" and (day[:4] + day[5:7] + day[8:]).isdigit() else "9"


def dated(endings):
    """The files in assets\\press with one of these endings that are in date today (not over, and started if their name says when
    they start), as full paths: the one that started last comes first, so a newer one takes over; otherwise by name."""
    try:
        names = sorted((n for n in os.listdir(PRESS) if n.lower().endswith(endings) and until(n) >= today() and since(n) <= today()), key=str.lower)
    except OSError:
        return []
    names.sort(key=since, reverse=True)
    return [os.path.join(PRESS, n) for n in names]


def plays(name):
    """How often a song may open the launcher on one PC: the number after __plays- in its name. 0 when it has none (as often as it
    likes), -1 (never) when it cannot be read."""
    low = os.path.splitext(os.path.basename(name))[0].lower()
    cut = low.find(PLAYS_TAG)
    if cut < 0:
        return 0
    number = low[cut + len(PLAYS_TAG):].split("__", 1)[0]
    return int(number) if number.isascii() and number.isdigit() and 0 < int(number) < 1000 else -1


def song_key(name):
    """What config.json calls a song when it counts its plays: its file name up to the first tag ('xifo_theme' for
    xifo_theme__plays-3__until-2026-12-02.mp3), so a new date or a new number in the name does not start the count again."""
    return os.path.splitext(os.path.basename(name))[0].lower().split("__", 1)[0].strip()


def played(name, cfg=None):
    """How often this song has opened the launcher on this PC ("theme_plays" in config.json)."""
    counts = (config() if cfg is None else cfg).get("theme_plays")
    count = counts.get(song_key(name)) if isinstance(counts, dict) else None
    return count if isinstance(count, int) and not isinstance(count, bool) and count > 0 else 0


def plays_left(name, cfg=None):
    """None for a song with no __plays- in its name; otherwise how many openings it still has on this PC (0: it is done, for good)."""
    most = plays(name)
    return None if most == 0 else max(0, most - played(name, cfg))


def count_play(path):
    """Notes in config.json that a song with __plays- in its name has opened the launcher once more (any other song: nothing)."""
    if plays(path) <= 0:
        return
    counts = config().get("theme_plays")
    counts = dict(counts) if isinstance(counts, dict) else {}
    counts[song_key(path)] = played(path, {"theme_plays": counts}) + 1
    save_all({"theme_plays": counts})


def config():
    try:
        with open(os.path.join(HERE, "config.json"), encoding="utf-8-sig") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_all(changes):
    """Changes values in config.json and keeps the rest (None takes a key out), the way the launcher itself does."""
    path = os.path.join(HERE, "config.json")
    with open(path, encoding="utf-8-sig") as handle:
        cfg = json.load(handle)
    for key, value in changes.items():
        if value is None:
            cfg.pop(key, None)
        else:
            cfg[key] = value
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2)


def save(key, value):
    save_all({key: value})


def is_colour(value):
    return isinstance(value, str) and len(value) == 7 and value[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in value[1:])


def key_of(name):
    """A theme's short name, from its file: 'vaporwave' for vaporwave__until-2026-12-02.json."""
    stem = os.path.splitext(os.path.basename(name))[0]
    cut = stem.lower().find(UNTIL_TAG)
    return (stem if cut < 0 else stem[:cut]).strip().lower()


def looks():
    """Every theme there is to pick today: each .json in assets\\press with a "colours" table whose date, if its name has one, has not
    passed. The limited-time ones (dated) first, then the others, by name."""
    try:
        names = [n for n in os.listdir(PRESS) if n.lower().endswith(".json") and (not until(n) or until(n) >= today())]
    except OSError:
        return []
    found = []
    for name in sorted(names, key=lambda n: (not until(n), n.lower())):
        try:
            with open(os.path.join(PRESS, name), encoding="utf-8-sig") as handle:
                look = json.load(handle)
        except (OSError, ValueError):
            continue
        key = key_of(name)
        if not isinstance(look, dict) or not isinstance(look.get("colours"), dict) or not key or key == DEFAULT or any(key == other["key"] for other in found):
            continue
        look["colours"] = {k: v.lower() for k, v in look["colours"].items() if is_colour(v)}
        look["file"], look["key"], look["id"], look["until"] = name, key, os.path.splitext(name)[0].lower(), until(name)
        if not isinstance(look.get("name"), str) or not look["name"].strip():
            look["name"] = key.replace("_", " ").replace("-", " ").title()
        found.append(look)
    return found


def standard_look(found=None):
    """The theme a PC wears when nothing is picked ("standard": true in its .json, undated), or None."""
    for look in (looks() if found is None else found):
        if look.get("standard") is True and not look["until"]:
            return look
    return None


def event_look(found=None):
    """The limited-time theme in date today (the first dated one), or None."""
    for look in (looks() if found is None else found):
        if look["until"]:
            return look
    return None


def picked(cfg, event):
    """What this PC picked on the Theme page, as it counts today: 'default', a theme's short name, or None (no pick: a limited-time
    theme shows by itself, otherwise the launcher's own look). A pick made before today's limited-time theme arrived does not hold
    it back: that theme shows by itself once, and the pick is back when it has gone."""
    pick = cfg.get("theme")
    if not isinstance(pick, str) or not pick.strip():
        return DEFAULT if cfg.get("limited_look") is False else None        # how the first Theme page wrote "off"
    if event is not None and cfg.get("theme_event") != event["id"]:
        return None
    return pick.strip().lower()


def load_look():
    """The look the launcher wears this time: the theme picked on the Theme page, else the limited-time one in date, else None (its own)."""
    found = looks()
    standard = standard_look(found)
    event = event_look(found)
    pick = picked(config(), None if standard is not None else event)     # with a standard theme a limited-time one never turns itself on
    if pick == DEFAULT:
        return None
    for look in found:
        if look["key"] == pick:
            return look
    return standard or event


def switched_off():
    """True when a limited-time theme is in date and this PC wears another one (picked on the Theme page): its banners rest with it."""
    event = event_look()
    return event is not None and (LOOK is None or LOOK.get("id") != event["id"])


def worn():
    """The short name of the theme the launcher wears this time ("8bit"), "" for its own look. launcher_gui asks: a banner with
    __theme-8bit in its name is shown only while that theme is worn, and then in place of the usual ones."""
    return LOOK["key"] if LOOK is not None else ""


def themes():
    """What the Theme page offers: Default (the launcher's own look), then every theme there is today."""
    found = looks()
    name = "Classic" if standard_look(found) is not None else "Default"
    return [{"key": DEFAULT, "name": name, "until": "", "colours": dict(OWN)}] + found


def load_font(look):
    """Makes a theme's own font (.ttf files in assets\\press, named by its "font") known to this program only; nothing is installed
    on the PC. Returns the family name to ask Tk for, or None (no font, or it could not be loaded: the usual lettering stays)."""
    spec = look.get("font") if isinstance(look, dict) else None
    if not isinstance(spec, dict) or not isinstance(spec.get("family"), str) or not spec["family"].strip():
        return None
    files = spec.get("files", spec.get("file"))
    files = [files] if isinstance(files, str) else files if isinstance(files, list) else []
    added = 0
    for name in files:
        if not isinstance(name, str):
            continue
        parts = [part for part in name.replace("\\", "/").split("/") if part not in ("", ".", "..")]
        path = os.path.join(PRESS, *parts) if parts else ""
        if not path.lower().endswith((".ttf", ".otf")) or not os.path.isfile(path):
            continue
        try:
            if os.name == "nt":
                added += 1 if ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0) else 0     # FR_PRIVATE: this program only, until it closes
            else:
                import ctypes.util
                library = ctypes.CDLL(ctypes.util.find_library("fontconfig") or "libfontconfig.so.1")
                library.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
                added += 1 if library.FcConfigAppFontAddFile(None, os.fsencode(path)) else 0
        except Exception:
            continue
    return spec["family"].strip() if added else None


def _font_elsewhere():
    """The worn theme's font for the two places colours() cannot reach by name: the Co-op page asks launcher_core.ui_fonts() for its
    font after its own colours, and the page titles' serif is picked late (launcher_widgets._HEAD). Both only if they are there."""
    core = sys.modules.get("launcher_core")
    usual = getattr(core, "ui_fonts", None)
    if callable(usual) and not getattr(usual, "themed", False):
        def ui_fonts():
            return (FONT,) + tuple(usual())[1:]
        ui_fonts.themed = True
        core.ui_fonts = ui_fonts
    widgets = sys.modules.get("launcher_widgets")
    if widgets is not None and hasattr(widgets, "_HEAD"):
        widgets._HEAD = FONT


def apply_font(root):
    """The worn theme's font for everything that uses Tk's own default fonts (the plain ttk labels, buttons, boxes and tabs, which
    name no font of their own). Tk's named fonts change live, so this can come after the windows are made; once is enough."""
    global _FONT_APPLIED
    if not FONT or _FONT_APPLIED:
        return
    _FONT_APPLIED = True
    from tkinter import font as tkfont
    for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkCaptionFont", "TkSmallCaptionFont", "TkTooltipFont", "TkIconFont"):
        try:
            tkfont.nametofont(name, root).configure(family=FONT)
        except Exception:
            pass


_FONT_APPLIED = False


def colours(names):
    """The worn look's colours (and, if it has one, its font) for the names this file defines (BG, PANEL, GOLD ... UI_FONT): {} when
    the launcher wears its own, so nothing changes. On the way it notes the file's own colours (OWN): the Theme page shows them
    beside Default."""
    try:
        for key in PALETTE:
            if key not in OWN and is_colour(names.get(key)):
                OWN[key] = names[key].lower()
    except Exception:
        pass
    if LOOK is None:
        return {}
    out = {key: value for key, value in LOOK["colours"].items() if key in names}
    if FONT:
        out.update({key: FONT for key in FONT_NAMES if key in names})
        try:
            _font_elsewhere()
        except Exception:
            pass
    return out


# ---------- the tint of the painted buttons ----------
def _luts(ramp):
    """A ramp [[0, "#140630"], [0.5, "#ff46be"], [1, "#ffffff"]] as three 256-entry tables: grey level -> red, green, blue."""
    stops = sorted((float(p), tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))) for p, c in ramp if is_colour(c))
    if len(stops) < 2:
        raise ValueError("a tint needs at least two colours")
    tables = [[], [], []]
    for level in range(256):
        t = level / 255.0
        lo, hi = stops[0], stops[-1]
        for a, b in zip(stops, stops[1:]):
            if a[0] <= t <= b[0]:
                lo, hi = a, b
                break
        k = 0.0 if hi[0] == lo[0] else min(1.0, max(0.0, (t - lo[0]) / (hi[0] - lo[0])))
        for i in range(3):
            tables[i].append(int(round(lo[1][i] + (hi[1][i] - lo[1][i]) * k)))
    return tables


def tint(image, art):
    """A picture washed towards the look: its light and dark are mapped onto the look's ramp, then mixed with the picture itself."""
    from PIL import Image
    rgba = image.convert("RGBA")
    rgb = rgba.convert("RGB")
    grey = rgb.convert("L")
    red, green, blue = art["_luts"]
    mapped = Image.merge("RGB", (grey.point(red), grey.point(green), grey.point(blue)))
    out = Image.blend(rgb, mapped, min(1.0, max(0.0, float(art.get("mix", 0.7))))).convert("RGBA")
    out.putalpha(rgba.getchannel("A"))
    return out


def _wants_tint(path):
    parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
    return len(parts) >= 3 and "assets" in parts and any(parts[i] == "assets" and parts[i + 1] in TINTED for i in range(len(parts) - 1))


def swapped(path, art):
    """The look's own picture for one of the launcher's: the file of the same name in the look's folder (assets\\press\\<art "folder">),
    for a picture from assets\\ui, or for a PLAY / STOP / DUALBOX variant from assets\\buttons. None when the look has none for it."""
    folder = os.path.basename(str(art.get("folder") or ""))
    if not folder:
        return None
    parts = os.path.normpath(os.path.abspath(path)).split(os.sep)
    for i in range(len(parts) - 2):
        if parts[i] != "assets":
            continue
        name = None
        if parts[i + 1] == "ui" and i + 3 == len(parts):
            name = parts[-1]
        elif parts[i + 1] == "buttons" and i + 4 == len(parts) and parts[i + 2] in BUTTON_KINDS:
            stem = os.path.splitext(parts[-1])[0].lower()
            state = next((s for s in ("_hover", "_off") if stem.endswith(s)), "")
            name = BUTTON_KINDS[parts[i + 2]] + state + ".png"
        if name:
            candidate = os.path.join(PRESS, folder, name)
            return candidate if os.path.isfile(candidate) else None
    return None


_RealPhotoImage = tk.PhotoImage


class TintedPhotoImage(_RealPhotoImage):
    """tk.PhotoImage, but a picture loaded from assets\\ui or assets\\buttons is the look's own one when it has one (same name in its
    folder), and otherwise takes the look's tint when it has a tint. Still a real PhotoImage."""

    def __init__(self, name=None, cnf={}, master=None, **kw):
        path = kw.get("file")
        other = None
        if path and LOOK is not None and LOOK.get("art"):
            try:
                other = swapped(str(path), LOOK["art"])
            except Exception:
                other = None
        if other:
            kw = dict(kw, file=other)
        elif path and LOOK is not None and LOOK.get("art") and LOOK["art"].get("_luts") and _wants_tint(str(path)):
            try:
                import base64
                import io
                from PIL import Image
                buffer = io.BytesIO()
                with Image.open(path) as picture:
                    tint(picture, LOOK["art"]).save(buffer, "PNG")
                kw = {k: v for k, v in kw.items() if k != "file"}
                kw["data"] = base64.b64encode(buffer.getvalue())
            except Exception:
                kw = dict(kw, file=path)                # any trouble: the picture as it is
        _RealPhotoImage.__init__(self, name, cnf, master, **kw)


def install():
    """Puts the look's picture loader in tk.PhotoImage's place while a look with its own buttons, or a tint, is in date."""
    if LOOK is None or not isinstance(LOOK.get("art"), dict):
        return False
    art = LOOK["art"]
    if art.get("ramp"):
        try:                                            # a tint needs Pillow; without it the usual pictures stay as they are
            import PIL.Image  # noqa: F401
            art["_luts"] = _luts(art["ramp"])
        except Exception:
            art.pop("_luts", None)
    has_folder = bool(art.get("folder")) and os.path.isdir(os.path.join(PRESS, os.path.basename(str(art["folder"]))))
    if not has_folder and not art.get("_luts"):
        return False
    tk.PhotoImage = TintedPhotoImage
    return True


def uninstall():
    tk.PhotoImage = _RealPhotoImage


# ---------- the opening theme ----------
class Player:
    """Plays one sound file without waiting for it: Windows' own player (winmm), on Linux whichever of ffplay / mpv / mpg123 / cvlc is there."""
    ALIAS = "xifo_theme"

    def __init__(self):
        self.proc, self.open = None, False
        self.why = ""                                  # why the last play() did not start, for logs\theme-music.log

    def _mci(self, command):
        answer = ctypes.create_unicode_buffer(128)
        return ctypes.windll.winmm.mciSendStringW(command, answer, 127, 0), answer.value

    def _mci_error(self, code):
        text = ctypes.create_unicode_buffer(256)
        try:
            ctypes.windll.winmm.mciGetErrorStringW(code, text, 255)
        except Exception:
            pass
        return f"MCI error {code}: {text.value}"

    def play(self, path, volume=VOLUME):
        self.stop()
        self.why = ""
        if not os.path.isfile(path) or os.path.getsize(path) < 1024:
            self.why = f"the song file is missing or empty: {path}"
            return False
        try:
            if os.name == "nt":
                short = ctypes.create_unicode_buffer(600)          # the short 8.3 path: the old player trips over long or unusual ones
                if ctypes.windll.kernel32.GetShortPathNameW(path, short, 600):
                    path = short.value
                kind = "waveaudio" if path.lower().endswith(".wav") else "mpegvideo"
                code = self._mci(f'open "{path}" type {kind} alias {self.ALIAS}')[0]
                if code:
                    first = self._mci_error(code)
                    # (2026-11-24, lilibun, Hexblood, Sterling: "MCI error 277" on Windows 10 Pro / 11) the old MCI player
                    # needs Windows' DirectShow MP3 decoder, which codec packs or a broken registry entry can knock out
                    # while every music app still plays the file. Then Windows Media Foundation plays it instead.
                    if self._play_mf(path, volume):
                        return True
                    self.why = "Windows could not open the song (" + first + "; " + (self.why or "the other player failed too") + ")"
                    return False
                self.open = True
                self._mci(f"setaudio {self.ALIAS} volume to {int(max(0.0, min(1.0, volume)) * 1000)}")
                code = self._mci(f"play {self.ALIAS}")[0]
                if code:
                    self.why = "Windows could not play the song (" + self._mci_error(code) + ")"
                    self.stop()
                    return False
                return True
            percent = str(int(max(0.0, min(1.0, volume)) * 100))
            for command in (["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", percent], ["mpv", "--no-video", "--really-quiet", "--volume=" + percent],
                            ["mpg123", "-q"], ["cvlc", "--play-and-exit", "--quiet"]):
                if shutil.which(command[0]):
                    self.proc = subprocess.Popen(command + [path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
            self.why = "no sound player found (install ffplay, mpv, mpg123 or vlc)"
        except Exception as e:
            self.why = f"{type(e).__name__}: {e}"
            self.stop()
        return False

    # Windows Media Foundation through WPF's MediaPlayer, in a hidden PowerShell that lives as long as the song
    MF_SCRIPT = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName PresentationCore,System.Windows.Forms;"
        "$p=New-Object System.Windows.Media.MediaPlayer;"
        "$p.Volume=[double]$env:XIFO_SONG_VOLUME;"
        "$p.Open([Uri]::new($env:XIFO_SONG));"
        "$t=0;while(-not $p.NaturalDuration.HasTimeSpan -and $t -lt 100){[System.Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 100;$t++};"
        "if(-not $p.NaturalDuration.HasTimeSpan){exit 3};"
        "$p.Play();"
        "$end=(Get-Date).AddSeconds($p.NaturalDuration.TimeSpan.TotalSeconds+1);"
        "$vf=$env:XIFO_SONG_VOLFILE;"
        # (2026-11-25, Hexblood) the slider moves this player too: the launcher writes the level to a small file
        "while((Get-Date) -lt $end){[System.Windows.Forms.Application]::DoEvents();"
        "if($vf -and (Test-Path $vf)){try{$c=(Get-Content $vf -Raw);if($c -and $c.Trim()){$v=[double]$c.Trim();if($v -ge 0 -and $v -le 1){$p.Volume=$v}}}catch{}};"
        "Start-Sleep -Milliseconds 250}")

    def _play_mf(self, path, volume):
        """The fallback player: True when the song started (the process still runs after a short wait)."""
        try:
            self._volfile = os.path.join(tempfile.gettempdir(), "xifo-song-volume-%d.txt" % os.getpid())
            self._write_volume(volume)
            env = dict(os.environ, XIFO_SONG=os.path.abspath(path), XIFO_SONG_VOLFILE=self._volfile,
                       XIFO_SONG_VOLUME=str(max(0.0, min(1.0, volume))))
            proc = subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                     "-WindowStyle", "Hidden", "-Command", self.MF_SCRIPT],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env,
                                    creationflags=0x08000000)          # CREATE_NO_WINDOW
            try:
                code = proc.wait(timeout=12)                         # still running after 12 s: it is playing
            except subprocess.TimeoutExpired:
                self.proc = proc
                return True
            err = (proc.stderr.read() or b"").decode("utf-8", "replace").strip().splitlines()
            self.why = "Windows Media Foundation could not play it either" + (f" ({err[-1][:160]})" if err else f" (code {code})")
        except Exception as e:
            self.why = f"Windows Media Foundation: {type(e).__name__}: {e}"
        return False

    def _write_volume(self, level):
        """The level for the Media Foundation player, which reads this file while it plays."""
        try:
            if getattr(self, "_volfile", None):
                with open(self._volfile, "w", encoding="ascii") as handle:
                    handle.write("%.3f" % max(0.0, min(1.0, level)))
        except OSError:
            pass

    def volume(self, level):
        """Louder or quieter while it plays (Windows: either player; elsewhere the new level counts from the next time)."""
        try:
            if os.name == "nt" and self.open:
                self._mci(f"setaudio {self.ALIAS} volume to {int(max(0.0, min(1.0, level)) * 1000)}")
            elif os.name == "nt" and self.proc is not None:
                self._write_volume(level)          # (2026-11-25, Hexblood) the Media Foundation player follows the slider too
        except Exception:
            pass

    def playing(self):
        try:
            if os.name == "nt" and self.proc is None:
                return self.open and self._mci(f"status {self.ALIAS} mode")[1] == "playing"
            return self.proc is not None and self.proc.poll() is None
        except Exception:
            return False

    def stop(self):
        try:
            if os.name == "nt" and self.open:
                self._mci(f"stop {self.ALIAS}")
                self._mci(f"close {self.ALIAS}")
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass
        self.proc, self.open = None, False


PLAYER = Player()
atexit.register(PLAYER.stop)


def own_sound():
    """The launcher's own opening theme (default.mp3 or default.wav in assets\\press), or None."""
    for name in OWN_SOUNDS:
        path = os.path.join(PRESS, name)
        if os.path.isfile(path):
            return path
    return None


def music_file():
    """The opening theme that goes with the look worn this time, or None. In order: the file the theme names itself ("sound", in
    assets\\press); for a limited-time theme, or the launcher's own look while no limited-time theme is in date, the first dated
    .mp3 / .wav in assets\\press (one with __plays- in its name first while it has plays left on this PC, and not at all once it
    has had them); otherwise the launcher's own opening theme (default.mp3 / default.wav)."""
    if LOOK is not None and isinstance(LOOK.get("sound"), str):
        path = os.path.join(PRESS, os.path.basename(LOOK["sound"]))
        if path.lower().endswith(SOUNDS) and os.path.isfile(path):
            return path
    if (LOOK is not None and LOOK.get("until")) or (LOOK is None and event_look() is None):
        cfg = config()
        found = [path for path in dated(SOUNDS) if plays_left(path, cfg) != 0]       # a song that has had its plays is done
        found.sort(key=lambda path: plays_left(path, cfg) is None)                    # one with plays left goes first (the rest keep their order)
        if found:
            return found[0]
    return own_sound()


def music_notes():
    """Who made the launcher's songs, from music.json in assets\\press: "credit" (a sentence for the Theme page), "by" (who made
    every song that does not say otherwise) and "songs" (a song's file name: its title, or {"title": ..., "by": ...}). {} when the
    file is missing or cannot be read."""
    try:
        with open(os.path.join(PRESS, MUSIC), encoding="utf-8-sig") as handle:
            notes = json.load(handle)
    except (OSError, ValueError):
        return {}
    return notes if isinstance(notes, dict) else {}


def _words(value, most=200):
    return " ".join(value.split())[:most] if isinstance(value, str) else ""


def song_credit(path, notes=None):
    """(title, who made it) of a song as music.json has it, '' for what it does not say. A song that is not listed there gets
    neither: nobody is named for a song unless the file names them for it."""
    notes = music_notes() if notes is None else notes
    songs = notes.get("songs") if isinstance(notes, dict) else None
    if not path or not isinstance(songs, dict):
        return "", ""
    name = os.path.basename(path).lower()
    listed = [value for key, value in songs.items() if isinstance(key, str) and key.lower() == name]
    if not listed:
        return "", ""
    entry = listed[0]
    title, by = (entry.get("title"), entry.get("by")) if isinstance(entry, dict) else (entry, None)
    return _words(title), _words(notes.get("by") if by is None else by)


def song_line(path, notes=None):
    """A song's line on the Theme page: '"A Place to Return" by JØ', just the title, 'by JØ', or '' (a song music.json does not list)."""
    title, by = song_credit(path, notes)
    if title and by:
        return f'"{title}" by {by}'
    return f'"{title}"' if title else f"by {by}" if by else ""


def music_credit(notes=None):
    """The sentence that credits the launcher's music ("credit" in music.json), or ''."""
    notes = music_notes() if notes is None else notes
    return _words(notes.get("credit"), 400) if isinstance(notes, dict) else ""


def volume_now():
    try:
        return max(0.0, min(1.0, float(config().get("theme_volume", VOLUME))))
    except (TypeError, ValueError):
        return VOLUME


def restart(app):
    """Opens the launcher again and closes this one (the way it restarts itself after an update)."""
    extra = {} if os.name == "nt" else {"start_new_session": True}
    command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.join(HERE, "launcher_gui.pyw")]
    subprocess.Popen(command, cwd=HERE, **extra)
    app.on_close()


def last_day_text(day):
    """'2 December' for 2026-12-02 ('' if it cannot be read)."""
    try:
        when = datetime.date.fromisoformat(day)
        return f"{when.day} {when.strftime('%B')}"
    except (TypeError, ValueError):
        return ""


def swatch(parent, theme, bg, edge):
    """Five small squares of a theme's colours (Default: the launcher's own), to see what one looks like before picking it."""
    shades = dict(OWN)
    shades.update(theme.get("colours") or {})
    canvas = tk.Canvas(parent, width=5 * 15 + 1, height=16, bg=bg, highlightthickness=0)
    for i, key in enumerate(("BG", "PANEL2", "GOLD", "ACCENT", "FG")):
        canvas.create_rectangle(i * 15, 0, i * 15 + 15, 15, fill=shades.get(key, bg), outline=edge)
    return canvas


class Slider(tk.Canvas):
    """A small volume slider: a line and a knob. Click or drag; `moved` hears every change, `released` the last one."""

    def __init__(self, parent, value, moved, released, bg, line, knob, width=66, height=16):
        tk.Canvas.__init__(self, parent, width=width, height=height, bg=bg, highlightthickness=0, cursor="hand2")
        self.value, self.moved, self.released, self.line, self.knob = value, moved, released, line, knob
        self.pad = 8
        self.bind("<Button-1>", self.drag)
        self.bind("<B1-Motion>", self.drag)
        self.bind("<ButtonRelease-1>", lambda _e: self.released(self.value))
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = int(self["width"]), int(self["height"])
        x = self.pad + (w - 2 * self.pad) * self.value
        self.create_line(self.pad, h // 2, w - self.pad, h // 2, fill=self.line, width=3)
        self.create_line(self.pad, h // 2, x, h // 2, fill=self.knob, width=3)
        self.create_oval(x - 6, h // 2 - 6, x + 6, h // 2 + 6, fill=self.knob, outline=self.knob)

    def drag(self, event):
        w = int(self["width"])
        self.value = max(0.0, min(1.0, (event.x - self.pad) / float(w - 2 * self.pad)))
        self.draw()
        self.moved(self.value)


class Controls:
    """What the Theme page (or, in the classic look, the strip on the banner) does: which theme, the song, its volume."""

    def __init__(self, app):
        self.app = app
        self.themes = themes()                         # Default first, then every theme there is today
        self.event = event_look(self.themes[1:])       # the limited-time one, if one is in date
        standard = standard_look(self.themes[1:])
        self.fallback = standard["key"] if standard is not None else DEFAULT    # what a PC wears with nothing picked
        if standard is not None:
            self.event = None                          # it does not turn itself on: it is simply one to pick
        self.worn = LOOK["key"] if LOOK is not None else DEFAULT       # what the launcher wears this time
        self.pick = self.worn                          # what is picked: it counts from the next start
        self.sound = music_file()                      # the worn look's opening theme
        self.music_on = config().get("theme_music") is not False
        self.changed = []                              # things to redraw after a change

    def there(self):
        return len(self.themes) > 1 or self.sound is not None

    def theme(self, key):
        return next((theme for theme in self.themes if theme["key"] == key), None)

    def name(self, key):
        return (self.theme(key) or {}).get("name") or key

    def following(self, key):
        """The theme after this one in the list (the classic strip steps through them)."""
        keys = [theme["key"] for theme in self.themes]
        return keys[(keys.index(key) + 1) % len(keys)] if key in keys else DEFAULT

    def refresh(self):
        for redraw in self.changed:
            try:
                redraw()
            except Exception:
                pass

    def remember(self, changes):
        try:
            save_all(changes)
        except Exception:
            pass                                      # not remembered, but it does what was asked now

    def watch(self):
        if not PLAYER.playing():
            return
        if getattr(self.app, "running", False):       # the game has its own music
            PLAYER.stop()
            return
        self.app.after(500, self.watch)

    def play(self, asked=False, opening=False):
        """The opening theme: by itself only when the music is on and the theme is the one worn; `asked` is the page's own Play button.
        `opening` is the one play when the launcher opens: the only one a song with __plays- in its name counts."""
        if not self.sound:
            note("no song: no .mp3 / .wav for this look in assets\\press")
            return False
        if getattr(self.app, "running", False):
            return False
        if not asked and not (self.music_on and self.pick == self.worn):
            if opening:
                note("not played: the music is switched off" if not self.music_on else "not played: another theme is picked")
            return False
        if volume_now() <= 0.0:
            note("playing at volume 0 (the slider is all the way down)")
        if PLAYER.play(self.sound, volume_now()):
            if opening:
                try:
                    count_play(self.sound)
                except Exception:
                    pass                              # not counted this time: it simply gets one more opening
            self.app.after(500, self.watch)
            if opening:
                note("playing " + os.path.basename(self.sound))
            return True
        note("could not play " + os.path.basename(self.sound) + ": " + (PLAYER.why or "unknown reason"))
        return False

    def stop(self):
        PLAYER.stop()

    def set_music(self, on):
        self.music_on = bool(on)
        self.remember({"theme_music": None if self.music_on else False})
        if self.music_on:
            self.play()
        else:
            PLAYER.stop()
        self.refresh()

    def volume_moved(self, level):
        PLAYER.volume(level)

    def volume_set(self, level):
        self.remember({"theme_volume": round(level, 2)})
        self.refresh()

    def set_theme(self, key):
        """Picks a theme. The whole launcher changes, so it counts from the next start; it offers to restart right away."""
        if key == self.pick or self.theme(key) is None:
            self.refresh()
            return
        self.pick = key
        by_itself = self.event["key"] if self.event is not None else self.fallback
        if key == by_itself:                          # what the launcher wears with no pick at all: nothing to keep
            self.remember({"theme": None, "theme_event": None, "limited_look": None})
        else:
            self.remember({"theme": key, "theme_event": self.event["id"] if self.event is not None else None, "limited_look": None})
        if key != self.worn:
            PLAYER.stop()
        self.refresh()
        if key == self.worn:                          # back to the one it wears already: nothing to restart for
            return
        name = self.name(key)
        try:
            if getattr(self.app, "running", False):
                messagebox.showinfo("XI: Forever Offline", f"{name} is the theme from the next time you open the launcher.")
            elif messagebox.askyesno("XI: Forever Offline", f"{name} is the theme from the next time the launcher opens.\n\nRestart the launcher now?"):
                restart(self.app)
        except Exception:
            pass


_CONTROLS = None


def controls(app):
    global _CONTROLS
    if _CONTROLS is None or _CONTROLS.app is not app:
        _CONTROLS = Controls(app)
    return _CONTROLS


def add_page(app, tabs):
    """OPTIONS > Theme, in the launcher's newer look: made whenever there is a theme to pick or an opening theme to switch off. A
    switch for Default and one for every theme (one is on at a time), the song on or off, its volume. Returns the page (None when
    there is nothing to choose)."""
    try:
        apply_font(app)
    except Exception:
        pass
    c = controls(app)
    if not c.there():
        return None
    import launcher_widgets as w
    event = c.event
    last = last_day_text(event["until"]) if event is not None else ""
    song_last = last_day_text(until(os.path.basename(c.sound))) if c.sound else ""
    page = w.ScrollPage(tabs)
    subtitle = "Pick the launcher's look." if len(c.themes) > 1 else "The launcher's opening theme" + (f", here until {song_last}." if song_last else ".")
    if last:
        subtitle += f" {event['name']} is here until {last}."
    w.page_header(page.body, "Theme", subtitle, note="").pack(fill="x")
    page.theme_vars, page.theme_switches = {}, {}
    page.music_var = tk.BooleanVar(app, c.music_on)
    page.slider = page.percent = page.music_switch = page.pending = page.song = page.music_credit = None
    wrap = 940
    if len(c.themes) > 1:
        card = w.Card(page.body, "Look")
        card.pack(fill="x", pady=(14, 0))
        for theme in c.themes:
            key = theme["key"]
            var = page.theme_vars[key] = tk.BooleanVar(app, key == c.pick)
            line = tk.Frame(card.body, bg=w.PANEL)
            line.pack(fill="x", pady=3)
            switch = page.theme_switches[key] = w.Switch(line, var, command=lambda key=key, var=var: c.set_theme(key if var.get() else c.fallback))
            switch.pack(side="right")
            swatch(line, theme, w.PANEL, w.LINE).pack(side="left", padx=(0, 10))
            tk.Label(line, text=theme["name"], bg=w.PANEL, fg=w.FG, font=(w.UI_FONT, 10), anchor="w").pack(side="left")
            about = ("The launcher's original look" if c.fallback != DEFAULT else "The launcher's own look") if key == DEFAULT else \
                "The standard look" if key == c.fallback else f"Limited time: until {last_day_text(theme['until'])}" if theme["until"] else ""
            if about:
                tk.Label(line, text=about, bg=w.PANEL, fg=w.DIM, font=(w.UI_FONT, 9), anchor="w").pack(side="left", padx=(12, 0))
        words = "A theme changes the launcher's colours and buttons, and the launcher restarts to change it."
        if event is not None:
            words += (" A limited-time theme turns itself on when it arrives, brings its own banners and opening song, and goes away by "
                      "itself after its last day.")
        about_themes = card.note(words, wrap=wrap)
        page.pending = tk.Label(card.body, bg=w.PANEL, fg=w.GOLD, font=(w.UI_FONT, 9), anchor="w", justify="left", wraplength=wrap)

        def show_pick():
            for key, var in page.theme_vars.items():
                if bool(var.get()) != (key == c.pick):
                    var.set(key == c.pick)
            if c.pick == c.worn:
                page.pending.pack_forget()
            else:
                page.pending.configure(text=f"{c.name(c.pick)} is picked: the launcher wears it the next time it opens.")
                page.pending.pack(fill="x", pady=(0, 2), before=about_themes)

        c.changed.append(show_pick)
    if c.sound:
        card = w.Card(page.body, "Opening theme")
        card.pack(fill="x", pady=(10, 0))
        try:                                           # the song's name and who made it (music.json)
            notes = music_notes()
            song, credit = song_line(c.sound, notes), music_credit(notes)
        except Exception:
            song = credit = ""
        if song:
            page.song = card.row("Song", lambda parent: tk.Label(parent, text=song, bg=w.PANEL, fg=w.GOLD, font=(w.UI_FONT, 10, "bold")))
        page.music_switch = card.row("Play the theme song when the launcher opens",
                                     lambda parent: w.Switch(parent, page.music_var, command=lambda: c.set_music(page.music_var.get())))

        def volume_row(parent):
            box = tk.Frame(parent, bg=w.PANEL)
            page.percent = tk.Label(box, bg=w.PANEL, fg=w.DIM, font=(w.UI_FONT, 9), width=5, anchor="e")
            page.percent.pack(side="right")
            page.slider = Slider(box, volume_now(), lambda level: (c.volume_moved(level), show_percent()), c.volume_set, w.PANEL, w.LINE, w.GOLD, width=220, height=20)
            page.slider.pack(side="right")
            return box

        def show_percent():
            if page.percent is not None and page.slider is not None:
                page.percent.configure(text=f"{int(round(page.slider.value * 100))}%")

        card.row("Volume", volume_row)
        show_percent()
        bar = tk.Frame(card.body, bg=w.PANEL)
        bar.pack(fill="x", pady=(8, 2))
        w.button(bar, "Play it now", lambda: c.play(asked=True), small=True).pack(side="left")
        w.button(bar, "Stop", c.stop, small=True).pack(side="left", padx=8)
        card.note("It plays once when the launcher opens and stops when the game starts.", wrap=wrap)
        if credit:
            page.music_credit = card.note(credit, color=w.FG, wrap=wrap)
        c.changed.append(lambda: page.music_var.get() != c.music_on and page.music_var.set(c.music_on))
    if last:
        words = (f"After {last} {event['name']} goes away by itself." if len(c.themes) > 2
                 else f"After {last} the launcher goes back to normal by itself." if own_sound()
                 else f"After {last} the launcher goes back to normal by itself, and this page goes away.")
        tk.Label(page.body, text=words, bg=w.BG, fg=w.DIM, font=(w.UI_FONT, 9), anchor="w").pack(fill="x", pady=(12, 0))
    tabs.add(page, text="  Theme  ")
    page.controls = c
    app.theme_page = page
    return page


def start(app):
    """Called once the launcher's window is up: plays the opening theme (once, not while the game is running; it stops when the game
    starts). In the classic look, which has no Theme page, it also puts the same choices in a small strip on the banner (a click on
    THEME steps to the next theme). Returns the controls (None when there is nothing to choose)."""
    try:
        apply_font(app)
    except Exception:
        pass
    c = controls(app)
    if not c.there():
        return None
    c.strip = None
    stage = getattr(app, "stage", None)
    if getattr(app, "theme_page", None) is None and stage is not None:
        names = (LOOK or {}).get("colours", {})
        panel, lit, dim, line = names.get("PANEL", "#101c28"), names.get("GOLD", "#e6be64"), names.get("DIM", "#8aa0ad"), names.get("BORDER", "#1d3445")
        font = ("Segoe UI" if os.name == "nt" else "DejaVu Sans", 8, "bold")
        strip = tk.Frame(stage, bg=panel, padx=4, pady=1)
        music = theme = None
        if c.sound:
            music = tk.Label(strip, bg=panel, font=font, padx=4, cursor="hand2")
            music.pack(side="left")
            music.bind("<Button-1>", lambda _e: c.set_music(not c.music_on))
            Slider(strip, volume_now(), c.volume_moved, c.volume_set, panel, line, lit).pack(side="left", padx=(0, 6))
        if len(c.themes) > 1:
            theme = tk.Label(strip, bg=panel, font=font, padx=4, cursor="hand2")
            theme.pack(side="left")
            theme.bind("<Button-1>", lambda _e: c.set_theme(c.following(c.pick)))

        def show():
            if music is not None:
                music.configure(text="♪ MUSIC ON" if c.music_on else "♪ MUSIC OFF", fg=lit if c.music_on else dim)
            if theme is not None:
                theme.configure(text="THEME: " + c.name(c.pick).upper(), fg=dim if c.pick == DEFAULT else lit)

        if strip.winfo_children():
            strip.place(relx=1.0, rely=1.0, anchor="se", x=-6, y=-6)
            strip.lift()
            c.changed.append(show)
            show()
            c.strip = strip
        else:
            strip.destroy()
    app.after(700, lambda: c.play(opening=True))
    return c


# ---------- set up when the launcher first asks for it ----------
FONT = None
try:
    LOOK = load_look()
    install()
except Exception:
    LOOK = None
try:
    FONT = load_font(LOOK)
except Exception:
    FONT = None
