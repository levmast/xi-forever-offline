"""Themes (launcher_theme.py): a .json in assets\\press gives the launcher its colours and its own buttons. A dated one is a
limited-time theme (it turns itself on, with a dated .mp3 / .wav as its opening theme, and is gone by itself the day after its
date); an undated one is always there to pick. OPTIONS > Theme has a switch for Default and one for every theme.

Starts the real launcher twelve times from a COPY of the kit (stand-in config, database driver and addons folder; nothing of the
real install is read or changed): a limited-time theme in date, the music switched off, Default picked the way the first Theme
page wrote it ("limited_look": false), another theme picked, a pick made before the limited-time theme arrived, a song that is
only played once (__plays-1 in its name: the start that plays it, and the start after it), the classic look
(the same choices in a strip on the banner), the date passed, the date passed with the earlier pick still there, and twice with
the launcher's own opening theme (default.wav): Default picked during the limited-time theme, and no theme at all.
Who made the songs (music.json in assets\\press): the song card names the song and its maker and carries the credit, and before
anything is started the kit's own music.json is checked against the songs in its assets\\press (a song with no line there fails).
No sound is made: the player is replaced by one that only notes what it was asked to do.
Needs python3-tk, Pillow and a screen:
    xvfb-run -a -s "-screen 0 1500x1000x24" python3 dev/launcher-tests/test_limited_look.py [OUTDIR for screenshots]"""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import wave

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
LOOK = {"name": "Test look",
        "colours": {"BG": "#201030", "PANEL": "#2A1540", "PANEL2": "#341a50", "FG": "#fff0ff", "DIM": "#b0a0d0", "BORDER": "#503080",
                    "LINE": "#6040a0", "OFF": "#8070a0", "GOLD": "#ff50c0", "GOLD_LIT": "#ff90e0", "GOLD_DIM": "#703070",
                    "PARCH": "#f0e0ff", "ACCENT": "#40e0e0", "GREEN": "#40f0b0", "RED": "#ff5080", "GREY": "#504070",
                    "NOT_A_NAME": "#123456", "BAD": "pink"},
        "art": {"folder": "t-ui", "ramp": [[0, "#100020"], [0.5, "#ff40c0"], [1, "#ffffff"]], "mix": 0.8}}
OWN, OWN_HOVER = (10, 200, 220), (9, 90, 190)        # the colours of the look's own stand-in pictures
USUAL = {"BG": "#0a1118", "GOLD": "#e6be64"}
PLAIN = {"name": "Plain", "colours": {"BG": "#102018", "GOLD": "#80e060"}, "sound": "t_own.wav",       # a theme that is always there to pick,
         "font": {"family": "Galmuri11", "files": ["fonts/Galmuri11-Regular.ttf", "fonts/no-such-file.ttf"]}}   # with lettering of its own
CREDIT = "All of the music is by T. B\u00e5rd, the test's Head of Music."
WEARING = {"during": "event", "muted": "event", "classic": "event", "earlier": "event", "opener": "event", "opener-done": "event",
           "picked": "plain", "back": "plain"}   # other steps: its own look


def day(offset):
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


def tone(path):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)


def put_dated(press, offset, plain=False, own=False, credits=True, opener=False):
    """The copy's own limited-time theme, banner and tune, dated `offset` days from today (any others are taken out first).
    plain: also a theme with no date (always there to pick), with a tune of its own. own: also the launcher's own opening theme.
    credits: also a music.json that says who made them (the dated tune by a guest, the launcher's own with no title).
    opener: also a second dated tune that is played once only (__plays-1 in its name)."""
    for name in os.listdir(press):
        if os.path.isfile(os.path.join(press, name)) and (name.lower().endswith((".json", ".mp3", ".wav")) or "__until-" in name.lower()
                                                           or "__theme-t_plain" in name.lower()):
            os.remove(os.path.join(press, name))
    with open(os.path.join(press, f"t_look__until-{day(offset)}.json"), "w") as f:
        json.dump(LOOK, f)
    from PIL import Image
    Image.new("RGB", (920, 368), (240, 60, 160)).save(os.path.join(press, f"t_banner__until-{day(offset)}.png"))
    tone(os.path.join(press, f"t_theme__until-{day(offset)}.wav"))
    if plain:
        with open(os.path.join(press, "t_plain.json"), "w") as f:
            json.dump(PLAIN, f)
        tone(os.path.join(press, "t_own.wav"))
        Image.new("RGB", (920, 368), (30, 90, 50)).save(os.path.join(press, "t_plain_banner__center__theme-t_plain.png"))      # that theme's own banner
    if own:
        tone(os.path.join(press, "default.wav"))
    if opener:
        tone(os.path.join(press, f"t_first__plays-1__until-{day(offset)}.wav"))
    if credits:
        notes = {"by": "T. B\u00e5rd", "credit": CREDIT,
                 "songs": {f"T_Theme__until-{day(offset)}.WAV": {"title": "Event  Song", "by": "A Guest"}, "t_own.wav": "Own Song", "default.wav": "",
                           f"t_first__plays-1__until-{day(offset)}.wav": "First Song"}}
        with open(os.path.join(press, "music.json"), "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False)


def kit_music():
    """The kit's own music.json against the songs in its assets\\press: what is wrong, one line each (none: every song is credited)."""
    press = os.path.join(KIT, "assets", "press")
    songs = sorted(n for n in os.listdir(press) if n.lower().endswith((".mp3", ".wav"))) if os.path.isdir(press) else []
    path = os.path.join(press, "music.json")
    if not os.path.isfile(path):
        return [f"assets\\press has {len(songs)} song(s) and no music.json to say who made them"] if songs else []
    try:
        with open(path, encoding="utf-8-sig") as f:
            notes = json.load(f)
    except (OSError, ValueError) as e:
        return [f"music.json cannot be read: {e}"]
    if not isinstance(notes, dict) or not isinstance(notes.get("songs"), dict):
        return ['music.json has no "songs" table']
    wrong = []
    listed = {str(name).lower(): entry for name, entry in notes["songs"].items()}
    for song in songs:
        if song.lower() not in listed:
            wrong.append(f"{song} has no line in music.json")
            continue
        entry = listed[song.lower()]
        by = entry.get("by") if isinstance(entry, dict) and entry.get("by") is not None else notes.get("by")
        if not isinstance(by, str) or not by.strip():
            wrong.append(f"music.json names nobody for {song}")
    for name in listed:
        if name not in [song.lower() for song in songs]:
            wrong.append(f"music.json lists {name}, which is not in assets\\press")
    if not isinstance(notes.get("credit"), str) or not notes["credit"].strip():
        wrong.append('music.json has no "credit" sentence for the Theme page')
    return wrong


def make_copy():
    work = tempfile.mkdtemp(prefix="xif-look-")
    kit = os.path.join(work, "kit")
    os.makedirs(kit)
    for name in os.listdir(KIT):
        path = os.path.join(KIT, name)
        if os.path.isfile(path) and (name.startswith("launcher_") and name.endswith((".py", ".pyw"))
                                     or name in ("rates.json", "thirdparty.json", "graphics.json", "gfxmod.json", "contributors.json",
                                                 "CREDITS.md", "config.example.json")):
            shutil.copy2(path, os.path.join(kit, name))
    for folder in ("ui", "press"):
        source = os.path.join(KIT, "assets", folder)
        if os.path.isdir(source):
            shutil.copytree(source, os.path.join(kit, "assets", folder))
    press = os.path.join(kit, "assets", "press")
    os.makedirs(press, exist_ok=True)
    os.makedirs(os.path.join(kit, "assets", "ui"), exist_ok=True)
    from PIL import Image
    Image.new("RGB", (60, 30), (230, 190, 100)).save(os.path.join(kit, "assets", "ui", "t_gold.png"))       # a button-like picture
    Image.new("RGB", (60, 30), (230, 190, 100)).save(os.path.join(kit, "assets", "t_plain.png"))            # the same, outside ui
    Image.new("RGB", (60, 30), (230, 190, 100)).save(os.path.join(kit, "assets", "ui", "t_swap.png"))       # one the look has its own picture for
    os.makedirs(os.path.join(kit, "assets", "buttons", "play"), exist_ok=True)                               # a PLAY variant, as on the dev PC
    Image.new("RGB", (60, 30), (230, 190, 100)).save(os.path.join(kit, "assets", "buttons", "play", "t_variant_hover.png"))
    os.makedirs(os.path.join(press, "t-ui"), exist_ok=True)                                                  # the look's own buttons
    Image.new("RGB", (60, 30), OWN).save(os.path.join(press, "t-ui", "t_swap.png"))
    Image.new("RGB", (60, 30), OWN_HOVER).save(os.path.join(press, "t-ui", "play_hover.png"))
    Image.new("RGB", (920, 368), (200, 180, 120)).save(os.path.join(press, "t_usual__center.png"))
    ashita = os.path.join(work, "ashita")
    for name in ("servermenu", "XIUI"):
        os.makedirs(os.path.join(ashita, "addons", name))
        with open(os.path.join(ashita, "addons", name, name + ".lua"), "w") as f:
            f.write(f"addon.name = '{name}';\naddon.author = 'test';\naddon.version = '1.0';\naddon.desc = 'stand-in';\n")
    os.makedirs(os.path.join(ashita, "plugins"))
    os.makedirs(os.path.join(ashita, "config", "boot"))
    os.makedirs(os.path.join(ashita, "scripts"))
    with open(os.path.join(ashita, "config", "boot", "xiforever.ini"), "w") as f:
        f.write("[ashita.boot]\nscript      = xiforever.txt\n\n[ffxi.registry]\n0001 = 1920\n0002 = 1080\n")
    with open(os.path.join(ashita, "scripts", "xiforever.txt"), "w") as f:
        f.write("# Managed by the XI: Forever Offline launcher\n/load addons\n/wait 3\n/addon load servermenu\n")
    with open(os.path.join(kit, "config.example.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg.update({"ashita_dir": ashita, "ashita_boot": "xiforever.ini", "server_dir": os.path.join(work, "server"),
                "mariadb_dir": os.path.join(kit, "mariadb"), "banners_seen": [n for n in os.listdir(press) if "__once" in n.lower()]})
    with open(os.path.join(kit, "config.json"), "w") as f:
        json.dump(cfg, f, indent=1)
    stubs = os.path.join(work, "stubs")
    os.makedirs(stubs)
    with open(os.path.join(stubs, "mariadb.py"), "w") as f:
        f.write("class Error(Exception):\n    pass\n\n\ndef connect(*a, **k):\n    raise Error('stand-in: no database in this test')\n")
    return work


def set_config(kit, **changes):
    path = os.path.join(kit, "config.json")
    with open(path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    for key, value in changes.items():
        if value is None:
            cfg.pop(key, None)
        else:
            cfg[key] = value
    with open(path, "w") as f:
        json.dump(cfg, f, indent=1)


def get_config(kit):
    with open(os.path.join(kit, "config.json"), encoding="utf-8-sig") as f:
        return json.load(f)


class QuietPlayer:
    """Stands in for launcher_theme.Player: no sound, just a note of what was asked."""

    def __init__(self):
        self.calls, self.on = [], False

    def play(self, path, volume=0.5):
        self.calls.append(("play", os.path.basename(path)))
        self.on = True
        return True

    def volume(self, level):
        self.calls.append(("volume", round(level, 2)))

    def playing(self):
        return self.on

    def stop(self):
        if self.on:
            self.calls.append(("stop",))
        self.on = False


def launch(work, step, out):
    kit = os.path.join(work, "kit")
    sys.path.insert(0, kit)
    sys.path.insert(0, os.path.join(work, "stubs"))
    os.chdir(kit)
    loader = importlib.machinery.SourceFileLoader("launcher_gui", os.path.join(kit, "launcher_gui.pyw"))
    spec = importlib.util.spec_from_loader("launcher_gui", loader)
    gui = importlib.util.module_from_spec(spec)
    sys.modules["launcher_gui"] = gui
    loader.exec_module(gui)
    for name in ("showerror", "showinfo", "showwarning"):
        setattr(gui.messagebox, name, lambda *a, **k: None)
    for name in ("askyesno", "askokcancel"):
        setattr(gui.messagebox, name, lambda *a, **k: False)
    import tkinter as tk
    theme = sys.modules.get("launcher_theme")
    widgets, coop = sys.modules.get("launcher_widgets"), sys.modules.get("launcher_coop_gui")
    fails = []

    def check(ok, what):
        print(("  ok   " if ok else "  FAIL ") + what)
        if not ok:
            fails.append(what)

    check(theme is not None, "the launcher loaded launcher_theme")
    if theme is None:
        sys.exit(1)
    player = QuietPlayer()
    theme.PLAYER = player
    wearing = WEARING.get(step)
    themed = wearing == "event"                                # the limited-time theme, with its own pictures
    want = {k: v.lower() for k, v in LOOK["colours"].items()} if themed else dict(USUAL, **PLAIN["colours"]) if wearing == "plain" else USUAL
    event_id = f"t_look__until-{day(3)}"

    if step == "during":
        check(theme.until("a__until-2026-12-02.json") == "2026-12-02" and theme.until("a.json") == "" and theme.until("a__until-soon.mp3") == "0",
              "the last day is read from a file's name")
        check(theme.LOOK is not None and theme.LOOK.get("name") == "Test look" and theme.LOOK["key"] == "t_look" and theme.LOOK["id"] == event_id,
              "the dated .json is the look, by itself")
        check([t["key"] for t in theme.themes()] == ["default", "t_look", "t_plain"] and theme.themes()[0]["colours"].get("GOLD") == USUAL["GOLD"],
              "the themes to pick: Default (in the launcher's own colours), the limited-time one, then the one with no date")
        check(theme.key_of("Vaporwave__until-2026-12-02.json") == "vaporwave" and theme.key_of("windurst.json") == "windurst", "a theme's short name is its file name without the date")
        gone = {"until": "x", "id": "new__until-2030-01-01", "key": "new"}
        check(theme.picked({}, None) is None and theme.picked({"limited_look": False}, gone) == "default" and theme.picked({"theme": "a"}, None) == "a"
              and theme.picked({"theme": "a"}, gone) is None and theme.picked({"theme": "a", "theme_event": gone["id"]}, gone) == "a",
              "a pick counts unless it was made before today's limited-time theme arrived")
        check("NOT_A_NAME" not in theme.colours(vars(gui)) and "BAD" not in theme.LOOK["colours"], "names the launcher does not have, and values that are no colour, are left out")
        luts = theme._luts(LOOK["art"]["ramp"])
        check([t[0] for t in luts] == [0x10, 0x00, 0x20] and [t[255] for t in luts] == [255, 255, 255] and len(luts[0]) == 256, "the tint's ramp runs from its first colour to its last")
        from PIL import Image
        src = Image.new("RGBA", (8, 8), (230, 190, 100, 120))
        done = theme.tint(src, dict(LOOK["art"], _luts=luts))
        check(done.size == (8, 8) and done.mode == "RGBA" and done.getpixel((0, 0))[3] == 120 and done.getpixel((0, 0))[:3] != (230, 190, 100),
              "a tinted picture keeps its size and its see-through parts, and changes colour")
        check(theme.Player().play(os.path.join(kit, "no-such-file.mp3")) in (True, False), "the real player never raises, whatever it is given")

    check(all(getattr(gui, k) == v for k, v in want.items() if hasattr(gui, k)) and gui.BG == want["BG"],
          f"launcher_gui's colours are {'the limited-time theme' if themed else 'the picked theme' if wearing else 'its own'}'s (BG {gui.BG}, GOLD {gui.GOLD})")
    check(widgets is not None and widgets.BG == want["BG"] and widgets.GOLD == want["GOLD"], "... and launcher_widgets' (the newer pages)")
    check(coop is None or (coop.BG == want["BG"] and coop.GOLD == want["GOLD"]), "... and the Co-op page's")
    pages = sys.modules.get("launcher_pages")
    check(pages is None or pages.GOLD == want["GOLD"], "... and launcher_pages picked them up from launcher_widgets")
    check((tk.PhotoImage is theme.TintedPhotoImage) == themed, "the tinted picture loader is " + ("in place" if themed else "not in place"))
    has_song = bool(wearing) or step in ("own-picked", "own-only")
    font_there = os.path.isfile(os.path.join(kit, "assets", "press", "fonts", "Galmuri11-Regular.ttf"))      # the kit's own pixel font
    own_font = "Galmuri11" if wearing == "plain" and font_there else None
    usual_font = gui.core.ui_fonts()[0] if not own_font else None
    check(theme.FONT == own_font and (gui.UI_FONT == own_font if own_font else gui.UI_FONT == usual_font) and widgets.UI_FONT == gui.UI_FONT,
          f"the launcher's text font is {'the theme\'s own' if own_font else 'the usual one'} ({gui.UI_FONT})")
    if step == "during":
        check(theme.load_font({"font": {"family": "X", "files": ["../../config.json", "fonts/nothing.ttf", 7]}}) is None and theme.load_font({}) is None
              and theme.load_font({"font": {"files": ["fonts/Galmuri11-Regular.ttf"]}}) is None,
              "a font that is not a .ttf in assets\\press, is missing, or has no family name is not taken")
    check((theme.music_file() is not None) == has_song, "there is " + ("an" if has_song else "no") + " opening theme for this look")

    app = gui.App()

    def settle(seconds):
        end = time.time() + seconds
        while time.time() < end:
            app.update()
            time.sleep(0.02)

    def shot(name):
        if not out:
            return
        app.lift()
        app.update()
        x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", "+repage", os.path.join(out, name + ".png")], check=False)

    def colour_of(path):
        picture = tk.PhotoImage(file=path)
        value = picture.get(5, 5)
        return tuple(int(v) for v in (value.split() if isinstance(value, str) else value))[:3]

    gold = (230, 190, 100)
    check((colour_of(os.path.join(kit, "assets", "ui", "t_gold.png")) not in (gold, OWN)) == themed,
          "a picture from assets\\ui the look has no picture for comes out " + ("tinted" if themed else "as it is"))
    check(colour_of(os.path.join(kit, "assets", "ui", "t_swap.png")) == (OWN if themed else gold),
          "one the look has its own picture for is " + ("the look's" if themed else "the usual one"))
    check(colour_of(os.path.join(kit, "assets", "buttons", "play", "t_variant_hover.png")) == (OWN_HOVER if themed else gold),
          "a PLAY variant from assets\\buttons is " + ("the look's play_hover" if themed else "the usual one"))
    check(colour_of(os.path.join(kit, "assets", "t_plain.png")) == gold, "a picture from elsewhere in assets is left as it is")
    check(isinstance(tk.PhotoImage(file=os.path.join(kit, "assets", "ui", "t_gold.png")).subsample(2), theme._RealPhotoImage), "it is still a real Tk picture (subsample works)")
    check("launcher_theme.start(app)" in open(os.path.join(kit, "launcher_gui.pyw"), encoding="utf-8").read(), "launcher_gui's main() starts the opening theme")

    asked, restarts = [], []
    theme.messagebox.askyesno = lambda *a, **k: (asked.append("ask"), step == "during")[1]      # "Restart now?": yes in the first start only
    theme.messagebox.showinfo = lambda *a, **k: asked.append("info")
    theme.restart = lambda _app: restarts.append("restart")
    page = getattr(app, "theme_page", None)
    c = theme.start(app)
    settle(1.3)
    press = os.path.join(kit, "assets", "press")
    pictures = sorted(n for n in os.listdir(press) if n.lower().endswith((".png", ".jpg", ".jpeg")) and "__once" not in n.lower())
    own_banners = [n for n in pictures if "__theme-t_plain" in n.lower()]            # the undated theme's own (pictures of other themes never count)
    pictures = [n for n in pictures if "__theme-" not in n.lower()]
    limited = [n for n in pictures if "__until-" in n.lower() and n.lower().split("__until-", 1)[1][:10] >= day(0)]
    usual = [n for n in pictures if "__until-" not in n.lower()]
    if wearing == "plain":
        check(len(own_banners) == 1 and len(app.heroes) == 1, f"the banners are the picked theme's own ({len(app.heroes)} loaded, {len(own_banners)} of its own)")
    else:
        check(len(app.heroes) == (len(limited) if themed else len(usual)),
              f"the banners are {'the limited-time ones' if themed else 'the usual ones'} ({len(app.heroes)} loaded; {len(limited)} in date, {len(usual)} usual, "
              f"{len(own_banners)} of a theme that is not worn)")
    if step == "during":
        check(gui.press_theme("a__center__theme-8bit.png") == "8bit" and gui.press_theme("a__theme-8Bit__top.JPG") == "8bit" and gui.press_theme("a__center.png") == ""
              and gui.press_anchor("a__top__theme-8bit.png") == 0.0 and gui.press_anchor("a__theme-8bit__bottom.png") == 1.0 and theme.worn() == "t_look",
              "a banner's theme is read from its name, and the name still says which part of the picture to keep")
    groups = {g["title"]: [name for name, _ in g["members"]] for g in getattr(app, "nav_groups", [])}
    strip = getattr(c, "strip", None) if c else None
    song, own_song = f"t_theme__until-{day(3)}.wav", "t_own.wav"

    def on():
        return sorted(key for key, var in page.theme_vars.items() if var.get())

    def pending():
        return page.pending.cget("text") if page.pending.winfo_manager() else ""

    if step not in ("classic", "after"):
        check(page is not None and "Theme" in app.page_index and "Theme" in groups.get("OPTIONS", []) and "MORE" not in groups,
              f"there is a Theme page under OPTIONS ({groups.get('OPTIONS')})")
        check(strip is None, "... and nothing on the banner")
    if step == "during":
        check(player.calls == [("play", song)], f"the opening theme was started once: {player.calls}")
        check(list(page.theme_switches) == ["default", "t_look", "t_plain"] and on() == ["t_look"] and page.music_switch is not None and page.slider is not None
              and page.music_var.get() and pending() == "",
              "the page has a switch for Default, the limited-time theme (on) and the other theme, the song switch (on) and the volume slider")
        check(page.song is not None and page.song.cget("text") == '"Event Song" by A Guest' and page.music_credit is not None
              and page.music_credit.cget("text") == CREDIT,
              f"the song card names the song and who made it, and carries the music credit ({page.song.cget('text') if page.song else None!r})")
        check(theme.song_credit(os.path.join(press, "T_OWN.WAV")) == ("Own Song", "T. B\u00e5rd") and theme.song_line("default.wav") == "by T. B\u00e5rd"
              and theme.song_credit("not-listed.mp3") == ("", "") and theme.song_line("not-listed.mp3") == "" and theme.song_line(None) == "",
              "music.json: a title with the usual maker, a song with no title, and nobody is named for a song it does not list")
        check(theme.song_line("a.mp3", {"songs": {"a.mp3": "Only A Title"}}) == '"Only A Title"'
              and theme.song_line("a.mp3", {"by": "X", "songs": {"a.mp3": {"title": "T", "by": ""}}}) == '"T"'
              and theme.song_credit("a.mp3", {"songs": ["a.mp3"]}) == ("", "") and theme.song_credit("a.mp3", {"by": 7, "songs": {"a.mp3": 9}}) == ("", "")
              and theme.music_credit({"credit": 5}) == "" and theme.music_credit([]) == "" and theme.song_credit("a.mp3", []) == ("", ""),
              "... and a music.json with odd contents names nobody")
        app.select_tab(app.page_index["Theme"])
        shot("look-theme-page")
        page.music_switch.toggle()
        settle(0.2)
        check(player.calls[-1] == ("stop",) and get_config(kit).get("theme_music") is False and not page.music_var.get(),
              "the song switch off: the song stops, and it is remembered in config.json")
        page.music_switch.toggle()
        settle(0.2)
        check(player.calls[-1][0] == "play" and "theme_music" not in get_config(kit), "on again: it plays, and the note is out of config.json")
        slider = page.slider
        slider.drag(type("Click", (), {"x": int(slider["width"]) - 1})())
        slider.released(slider.value)
        check(player.calls[-1] == ("volume", 1.0) and get_config(kit).get("theme_volume") == 1.0 and page.percent.cget("text") == "100%",
              "the slider at its right end: full volume at once, remembered, and the page says 100%")
        slider.drag(type("Click", (), {"x": 8 + (int(slider["width"]) - 16) // 4})())
        slider.released(slider.value)
        check(0.2 <= get_config(kit).get("theme_volume") <= 0.3 and player.calls[-1][0] == "volume", f"a quarter of the way along: {get_config(kit).get('theme_volume')}")
        check(theme.volume_now() == get_config(kit)["theme_volume"], "the next start plays at that volume")
        app.running = True
        settle(1.0)
        check(player.calls[-1] == ("stop",) and not player.on, "the song stops when the game is running")
        count = len(player.calls)
        settle(1.2)
        check(len(player.calls) == count, "... and stays stopped")
        page.theme_switches["default"].toggle()
        cfg = get_config(kit)
        check(cfg.get("theme") == "default" and cfg.get("theme_event") == event_id and on() == ["default"] and asked[-1] == "info" and not restarts,
              "Default switched on while the game runs: the other switch goes off, it is remembered (for this limited-time theme), no restart")
        check("Default" in pending(), f"... and the page says it is from the next start ({pending()!r})")
        shot("look-default-picked")
        app.running = False
        notes = len(asked)
        page.theme_switches["default"].toggle()
        check(on() == ["default"] and get_config(kit).get("theme") == "default" and len(asked) == notes, "switching the picked one off leaves it on: one theme is always on")
        page.theme_switches["t_look"].toggle()
        cfg = get_config(kit)
        check("theme" not in cfg and "theme_event" not in cfg and on() == ["t_look"] and len(asked) == notes and pending() == "",
              "back to the theme it wears: nothing kept in config.json, nothing asked, nothing to restart for")
        page.theme_switches["t_plain"].toggle()
        cfg = get_config(kit)
        check(cfg.get("theme") == "t_plain" and cfg.get("theme_event") == event_id and on() == ["t_plain"] and asked[-1] == "ask" and restarts == ["restart"],
              "the other theme switched on with the game closed: remembered, it asks, and restarts the launcher on Yes")
        page.theme_switches["t_plain"].toggle()
        check(get_config(kit).get("theme") == "default" and on() == ["default"] and restarts == ["restart"] * 2, "a theme switched off is Default switched on")
    elif step == "muted":
        check(player.calls == [], "music switched off earlier: nothing is played")
        check(page.music_var.get() is False and on() == ["t_look"], "the page shows the song off and the theme on")
        c.play(asked=True)
        check(player.calls == [("play", song)], "'Play it now' still plays it")
        check(theme.since("a__from-2026-11-24__until-2026-12-02.mp3") == "2026-11-24" and theme.since("a__until-2026-12-02.mp3") == ""
              and theme.since("a__from-soon.mp3") == "9" and theme.until("a__from-2026-11-24__until-2026-12-02.mp3") == "2026-12-02",
              "the first day of a song is read from its name")
        tone(os.path.join(press, f"a_later__from-{day(1)}__until-{day(3)}.wav"))
        tone(os.path.join(press, "a_never__from-soon__until-2999-01-01.wav"))
        check(os.path.basename(theme.music_file()) == song, "a song that starts tomorrow (or whose first day cannot be read) is not played yet")
        tone(os.path.join(press, f"z_newer__from-{day(0)}__until-{day(3)}.wav"))
        check(os.path.basename(theme.music_file()) == f"z_newer__from-{day(0)}__until-{day(3)}.wav", "from its first day on it takes over from the one that was playing")
        tone(os.path.join(press, f"z_over__from-{day(-5)}__until-{day(-1)}.wav"))
        tone(os.path.join(press, f"b_older__from-{day(-2)}__until-{day(3)}.wav"))
        check(os.path.basename(theme.music_file()) == f"z_newer__from-{day(0)}__until-{day(3)}.wav", "of two that have started, the one that started last plays; one that is over never does")
        check(theme.song_line(theme.music_file()) == "" and theme.song_line(os.path.join(press, song)) == '"Event Song" by A Guest',
              "a new song music.json does not list yet is credited to nobody (the listed one still is)")
        with open(os.path.join(press, "music.json"), "w") as f:
            f.write("{ not json")
        check(theme.music_notes() == {} and theme.song_line(os.path.join(press, song)) == "" and theme.music_credit() == "",
              "a music.json that cannot be read: no names, and nothing breaks")
        check(theme.plays("a__plays-3__until-2026-12-02.mp3") == 3 and theme.plays("a__until-2026-12-02__PLAYS-12.MP3") == 12 and theme.plays("a.mp3") == 0
              and theme.plays("a__plays-many.mp3") == -1 and theme.plays("a__plays-0.mp3") == -1
              and theme.song_key("Xifo_Theme__plays-3__until-2026-12-02.MP3") == "xifo_theme" and theme.song_key("default.mp3") == "default",
              "how often a song may play is read from its name, and its plays are counted under its name without the tags")
        opener = os.path.join(press, f"a_opener__plays-2__until-{day(3)}.wav")
        newer = f"z_newer__from-{day(0)}__until-{day(3)}.wav"
        tone(opener)
        tone(os.path.join(press, f"a_broken__plays-many__until-{day(3)}.wav"))
        check(os.path.basename(theme.music_file()) == os.path.basename(opener) and theme.plays_left(opener) == 2 and theme.plays_left(newer) is None,
              "a song with plays left goes first, ahead of the one that started last; one whose number cannot be read never plays")
        theme.count_play(opener)
        check(os.path.basename(theme.music_file()) == os.path.basename(opener) and get_config(kit).get("theme_plays") == {"a_opener": 1},
              "after the first of its two plays it is still the one")
        theme.count_play(opener)
        theme.count_play(os.path.join(press, newer))
        check(os.path.basename(theme.music_file()) == newer and theme.plays_left(opener) == 0 and get_config(kit).get("theme_plays") == {"a_opener": 2},
              "after the second it is done and the other song is back; a song with no number in its name is never counted")
        os.rename(opener, os.path.join(press, f"a_opener__plays-2__until-{day(9)}.wav"))
        check(os.path.basename(theme.music_file()) == newer, "... for good: a new date in its name does not bring it back")
        set_config(kit, theme_plays={"a_opener": "x", "other": True})
        check(theme.played("a_opener__plays-2.wav") == 0 and theme.played("other__plays-2.wav") == 0 and theme.plays_left("a_opener__plays-2.wav") == 2,
              "a count in config.json that is not a number counts as none")
    elif step == "off":
        check(player.calls == [], "Default picked: no song")
        check(on() == ["default"] and page.music_switch is None and page.slider is None, "the page shows Default on, the limited-time theme off, and no song card")
        app.select_tab(app.page_index["Theme"])
        shot("look-off-page")
        page.theme_switches["t_look"].toggle()
        cfg = get_config(kit)
        check("limited_look" not in cfg and "theme" not in cfg and on() == ["t_look"] and asked == ["ask"] and not restarts and "Test look" in pending(),
              "its switch turns it on for the next start (the old note is out of config.json); No to the restart leaves this window as it is")
    elif step == "picked":
        if own_font:
            from tkinter import font as tkfont
            check(tkfont.nametofont("TkDefaultFont").actual("family") == own_font and widgets._HEAD == own_font
                  and (coop is None or coop._UI_FONT == own_font) and gui.core.ui_fonts()[0] == own_font and gui.core.ui_fonts()[1] == gui.MONO_FONT,
                  "... also for the plain ttk widgets, the page titles and the Co-op page; the fixed-width font stays")
            check(own_font in tkfont.families(app), "Tk knows the font although it is not installed on this PC")
        else:
            print("  note the kit has no assets\\press\\fonts\\Galmuri11-Regular.ttf: the font checks were skipped")
        check(player.calls == [("play", own_song)], f"the picked theme's own song plays, not the limited-time one's: {player.calls}")
        check(on() == ["t_plain"] and page.music_switch is not None, "the page shows the picked theme on, and its song card")
        check(page.song is not None and page.song.cget("text") == '"Own Song" by T. B\u00e5rd' and page.music_credit is not None,
              f"... which names that theme's song and who made it ({page.song.cget('text') if page.song else None!r})")
        app.select_tab(app.page_index["Theme"])
        shot("look-picked-page")
    elif step == "earlier":
        check(player.calls == [("play", song)] and on() == ["t_look"] and get_config(kit).get("theme") == "t_plain",
              "a pick from before the limited-time theme arrived: the limited-time theme shows by itself, and the pick is kept for later")
    elif step == "back":
        check(player.calls == [("play", own_song)] and list(page.theme_switches) == ["default", "t_plain"] and on() == ["t_plain"],
              "the limited-time theme has gone: the earlier pick is back, and the page offers Default and that theme")
    elif step == "own-picked":
        check(player.calls == [("play", "default.wav")], f"Default picked during the limited-time theme: the launcher's own opening theme plays ({player.calls})")
        check(on() == ["default"] and page.music_switch is not None and page.slider is not None, "the page shows Default on, with the song card")
        check(page.song is None and page.music_credit is None and theme.music_notes() == {},
              "no music.json in assets\\press: the song card has no song line and no credit, and everything else is there")
        app.select_tab(app.page_index["Theme"])
        shot("look-own-picked")
    elif step == "own-only":
        check(player.calls == [("play", "default.wav")], f"no theme at all: the launcher's own opening theme plays ({player.calls})")
        check(page.theme_switches == {} and page.pending is None and page.music_switch is not None and page.slider is not None,
              "the Theme page is still there for the song (on / off, volume), with no themes to pick")
        check(page.song is not None and page.song.cget("text") == "by T. B\u00e5rd" and page.music_credit.cget("text") == CREDIT,
              "a song with no title: the card says who made it")
        app.select_tab(app.page_index["Theme"])
        shot("look-own-only")
        page.music_switch.toggle()
        settle(0.2)
        check(player.calls[-1] == ("stop",) and get_config(kit).get("theme_music") is False, "its switch stops it and is remembered")
        worn = theme.LOOK
        theme.LOOK = {"key": "x", "id": "x", "until": "", "colours": {}}
        plain_song = os.path.basename(theme.music_file() or "")
        theme.LOOK = {"key": "y", "id": "y__until-2999-01-01", "until": "2999-01-01", "colours": {}}
        event_song = os.path.basename(theme.music_file() or "")
        theme.LOOK = worn
        check(plain_song == "default.wav" and event_song == "default.wav", "a theme with no song of its own plays the launcher's own opening theme")
    elif step == "opener":
        first = f"t_first__plays-1__until-{day(3)}.wav"
        check(player.calls == [("play", first)] and get_config(kit).get("theme_plays") == {"t_first": 1},
              f"a song with __plays-1 in its name opens the launcher, ahead of the theme's other song, and the play is counted ({player.calls})")
        check(page.song is not None and page.song.cget("text") == '"First Song" by T. B\u00e5rd', "... and the song card names it")
        c.play(asked=True)
        page.music_switch.toggle()
        settle(0.2)
        page.music_switch.toggle()
        settle(0.2)
        check([call for call in player.calls if call[0] == "play"] == [("play", first)] * 3 and get_config(kit).get("theme_plays") == {"t_first": 1},
              "'Play it now' and the song switch play it again in this window without counting: only the launcher opening counts")
        check(os.path.basename(theme.music_file()) == song, "its one play is used: from the next start the theme's other song is the one")
    elif step == "opener-done":
        check(player.calls == [("play", song)] and get_config(kit).get("theme_plays") == {"t_first": 1},
              f"the start after: the first song has had its play, so the theme's other song plays, and nothing more is counted ({player.calls})")
        check(page.song is not None and page.song.cget("text") == '"Event Song" by A Guest', "... and the song card names that one")
    elif step == "classic":
        labels = [w for w in strip.winfo_children() if isinstance(w, tk.Label)] if strip is not None else []
        texts = [str(w.cget("text")) for w in labels]
        check(page is None and not getattr(app, "new_ui", False), "the classic look has no Theme page")
        check(texts == ["♪ MUSIC ON", "THEME: TEST LOOK"], f"... so the choices sit in a strip on the banner ({texts})")
        check(player.calls == [("play", song)], "the opening theme plays there too")
        labels[-1].event_generate("<Button-1>")
        settle(0.2)
        check(get_config(kit).get("theme") == "default" and str(labels[-1].cget("text")) == "THEME: DEFAULT" and asked == ["ask"],
              "a click on THEME steps to the next theme (here Default) and offers the restart")
    else:
        check(c is None and page is None and "Theme" not in app.page_index and player.calls == [], "the date has passed: no song, no Theme page")
        shot("look-after")
    app.destroy()
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--launch":
        launch(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "")
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else ""
    if out:
        os.makedirs(out, exist_ok=True)
    work = make_copy()
    kit = os.path.join(work, "kit")
    press = os.path.join(kit, "assets", "press")
    wrong = kit_music()
    print("kit")
    for line in wrong:
        print("  FAIL " + line)
    if not wrong:
        print("  ok   every song in the kit's assets\\press has its line in music.json, which names who made it")
    bad = 1 if wrong else 0
    try:
        for step in ("during", "muted", "off", "picked", "earlier", "opener", "opener-done", "classic", "after", "back", "own-picked", "own-only"):
            put_dated(press, -1 if step in ("after", "back", "own-only") else 3, plain=step in ("during", "picked", "earlier", "back"),
                      own=step in ("own-picked", "own-only"), credits=step != "own-picked", opener=step in ("opener", "opener-done"))
            if step != "opener-done":                # (that start finds the count the start before it left)
                set_config(kit, theme_plays=None)
            set_config(kit, theme_music=False if step == "muted" else None, limited_look=False if step == "off" else None,
                       theme="t_plain" if step in ("picked", "earlier", "back") else "default" if step == "own-picked" else None,
                       theme_event=f"t_look__until-{day(3)}" if step in ("picked", "back", "own-picked") else "t_old__until-2020-01-01" if step == "earlier" else None,
                       theme_volume=None, classic_ui=True if step == "classic" else None)
            print(step)
            bad += subprocess.run([sys.executable, os.path.abspath(__file__), "--launch", work, step, out]).returncode != 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("ALL OK" if not bad else f"{bad} step(s) FAILED")
    sys.exit(1 if bad else 0)
