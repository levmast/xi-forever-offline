"""PLAY's character cards (2026-11-25, the user: "like the stylized cards for each mode pick in hardcore, ... your
character card for each character, selecting it would log you right in bypassing character select").

(2026-11-25: the one PLAY screen, see CardScreen.) PLAY opens a dark screen with a card per character on your account (launcher_charcards.py draws them); the card under
the mouse lights up and sends up sparks in its nation's colours, like the Hardcore mode cards. Clicking one starts the
world and the game and logs that character straight in (Ashita's autologin addon, for that launch only). The last card,
CHARACTER SCREEN, is the game's own list (to make a character). "Show this at PLAY" turns the screen off (cfg
"char_cards"); the "Choose a character" link under PLAY (launcher_pages.PlayPage) still opens it.
"""
import os as _os
import random
import threading
import time as _time
import tkinter as tk

import launcher_charcards as cc
import launcher_widgets as w

DARK = "#07060a"


def wanted(app):
    return bool(app.cfg.get("char_cards", True)) and bool(app.cfg.get("game_user")) and bool(getattr(app, "ashita", None))


def play_pressed(app):
    """PLAY: the card screen (when it's on and there are cards to show), else straight to the game as before."""
    if app.running:
        return
    if not wanted(app) or not cc.load_cache(cc.HERE, app.cfg.get("game_user", "")) and not _db_up(app):
        app.autologin_slot = None
        app.start()
        return
    if getattr(app, "card_window", None) is not None:
        try:
            app.card_window.lift()
            return
        except tk.TclError:
            pass
    app.card_window = CardScreen(app)


def open_cards(app):
    """The "Choose a character" link under PLAY: the card screen even when PLAY is set to skip it. While the world is
    running it opens too: a 2nd-window card then opens the second window."""
    if not app.cfg.get("game_user") or not getattr(app, "ashita", None):
        return
    if getattr(app, "card_window", None) is not None:
        try:
            app.card_window.lift()
            return
        except tk.TclError:
            pass
    app.card_window = CardScreen(app)


def _connect(app):
    import launcher_passport as pp
    return pp.connect(app.cfg)


def _db_up(app):
    try:
        cc.refresh(cc.HERE, app.cfg, lambda: _connect(app))
        return bool(cc.load_cache(cc.HERE, app.cfg.get("game_user", "")))
    except Exception:
        return False


def refresh_after_game(app):
    """Called while the world's database is still up (the end of a game): the cards learn new levels, jobs and places."""
    try:
        cc.refresh(cc.HERE, app.cfg, lambda: _connect(app))
    except Exception:
        pass


def before_start(app, visit=None):
    """Called by App.start: the autologin block for the card that was picked (or taken out when none was)."""
    slot = getattr(app, "autologin_slot", None)
    app.autologin_slot = None
    if visit is not None:
        slot = None                                   # a visit to a friend's world uses another account's list
    scripts = getattr(app, "scripts", None)
    if scripts is None:
        return
    if slot is not None and not cc.ensure_addon(cc.HERE, getattr(app, "ashita", None)):
        app.say("The autologin add-on isn't in Ashita: choose your character on the character screen.")
        slot = None
    try:
        cc.set_autologin(scripts.path, slot)
    except Exception as e:
        app.say(f"Could not set up the log in ({e}) - choose your character on the character screen.")
        return
    if slot is not None:
        name = getattr(app, "autologin_name", "") or f"slot {slot + 1}"
        app.say(f"Logging {name} straight in.")


def before_gm(app):
    """Called by App.start_gm. (2026-11-26, Animelaine, Frenzo: Start GM game went to the character screen and hung there)
    The GM game runs the same start script as the main game (setup_gm.py main_script_name), so a card's one-launch log in
    was still in it when the GM game opened next to the main window: it tried to pick that character's slot on the GM
    account. The block is taken out first (the main window has read it already)."""
    import re
    paths = []
    scripts = getattr(app, "scripts", None)
    if scripts is not None and getattr(scripts, "path", None):
        paths.append(scripts.path)
    try:
        ashita, boot = getattr(app, "ashita", None), app.cfg.get("ashita_boot_gm")
        ini = _os.path.join(ashita, "config", "boot", boot) if (ashita and boot) else ""
        if ini and _os.path.exists(ini):
            with open(ini, encoding="utf-8-sig", errors="replace") as f:
                m = re.search(r"(?im)^\s*script\s*=\s*(\S+)", f.read())
            own = _os.path.join(ashita, "scripts", m.group(1)) if m else ""
            if own and _os.path.exists(own) and not any(_os.path.normcase(own) == _os.path.normcase(p) for p in paths):
                paths.append(own)
    except Exception:
        pass
    for path in paths:
        try:
            with open(path, encoding="utf-8-sig") as f:
                if cc.BEGIN not in f.read():
                    continue                          # nothing of ours in it: the file is left as it is
            cc.set_autologin(path, None)
        except Exception:
            pass


def _second_ready(app):
    """The second window is set up (setup_dualbox.py): its boot file and its account."""
    return bool(app.cfg.get("ashita_boot2")) and bool(app.cfg.get("game_user2"))


def _launch_second(app, slot, name=None):
    """The second window, with its character logged straight in (slot) or at its character screen (None)."""
    try:
        manager, _why = app.second_manager()
        if manager is not None:
            if slot is not None:
                cc.ensure_addon(cc.HERE, getattr(app, "ashita", None))
            cc.set_autologin(manager.path, slot)
    except Exception:
        pass
    app.start_second()
    if slot is not None and name:
        app.say(f"Logging {name} straight in, in the second window.")
    try:
        if _second_ready(app) and app.running:          # (it was really started: not one of start_second's notices)
            _watch_second(app, _time.time())
    except Exception:
        pass


def _second_loader_log(began):
    """The text of the log the game loader started after `began` (xiloader keeps one per start), or ''."""
    folder = _os.path.join(_os.environ.get("APPDATA", ""), "xiloader", "logs")
    best, best_time = "", 0.0
    try:
        for name in _os.listdir(folder):
            if name.lower().startswith("xiloader-") and name.lower().endswith(".log"):
                path = _os.path.join(folder, name)
                made = _os.path.getctime(path)
                if made >= began - 3 and made > best_time:
                    best, best_time = path, made
        if best:
            with open(best, encoding="utf-8", errors="replace") as handle:
                return handle.read()
    except OSError:
        pass
    return ""


def second_window_report(loader_log, ashita_tail, trouble_marks):
    """The lines the launcher shows when the second window did not come up (2026-11-26, Thomas: "the second window
    never opens", with nothing on screen to say why)."""
    lines = ["The second window did not open."]
    rows = [row.strip() for row in loader_log.splitlines() if row.strip()]
    trouble = [row for row in rows if any(mark in row.lower() for mark in trouble_marks)]
    if trouble:
        lines.append("Its game loader said: " + " | ".join(trouble[-3:]))
    elif rows:
        lines.append("Its game loader's last line: " + rows[-1])
    else:
        lines.append("Its game loader (xiloader) wrote no log, so Ashita did not get as far as starting it.")
    for row in [r for r in ashita_tail.splitlines() if r.strip()][-5:]:
        lines.append("ashita2.log: " + row.strip())
    lines.append("For a bug report, send logs\\ashita2.log from the launcher's folder.")
    return lines


def _watch_second(app, began, waited=0):
    """After the second window is started: 40 seconds later with still only one game running, say why (above)."""
    import launcher_core as core
    try:
        if core.count_running("xiloader") >= 2 or not app.running:
            return
    except Exception:
        return
    if waited < 40:
        app.after(5000, lambda: _watch_second(app, began, waited + 5))
        return
    try:
        tail = core.tail(_os.path.join(cc.HERE, "logs", "ashita2.log"), 8)
        for line in second_window_report(_second_loader_log(began), tail, core.LOADER_TROUBLE):
            app.say(line)
    except Exception:
        pass


def _second_after_main(app, slot, name, waited=0):
    """(2026-11-25) a 2nd-window card picked with a main one: the second window opens once the main game is up."""
    import launcher_core as core
    try:
        up = app.running and core.is_running("xiloader")
    except Exception:
        up = False
    if up:
        app.after(12000, lambda: _launch_second(app, slot, name))     # the main window logs in first
        return
    if waited > 300 or (waited > 20 and not app.running):
        return
    app.after(3000, lambda: _second_after_main(app, slot, name, waited + 3))


# the steps of CREATE A CHARACTER: (title, lines, kind, mark) for each choice
KIND_CHOICES = [("normal", "Normal", ["Your own rules,", "any job, any time"], "regular", "plus"),
                ("hardcore", "Hardcore", ["Iron, Steel or Silver:", "locked rates, earn", "everything yourself"], "steel", None),
                ("random", "Randomized", ["Fate rolls looks", "and jobs; you pick", "only the name"], "random", None)]
MODE_CHOICES = [(1, "Iron", ["No auction house", "or trades.", "Deaths are normal"], "iron", None),
                (2, "Steel", ["Knocked out: the job", "goes back to", "level 1"], "steel", None),
                (3, "Silver", ["PERMADEATH", "Knocked out:", "gone for good"], "silver", None)]
PERMA_CHOICES = [(True, "Permadeath", ["Knocked out once:", "gone for good,", "like Silver"], "silver", "skull"),
                 (False, "No permadeath", ["Normal deaths:", "get up and", "keep rolling"], "random", "plus")]
SQUAD_CHOICES = [(True, "Random squad", ["Your mates roll", "their own looks", "and jobs too"], "random", "dice"),
                 (False, "Own squad", ["Your mates stay", "themselves"], "regular", "one")]
WINDOW_CHOICES = [("main", "Main window", ["The character", "you play"], "regular", "one"),
                  ("second", "2nd window", ["Opens beside your", "main (dualbox)"], "dualbox", "window")]


class CardScreen(tk.Toplevel):
    """(2026-11-25, the user: "one play screen ... when you press create a character it asks if you want to create a
    hardcore character then shows you the cards then asks if you want perma death ... dualbox character ... all animated
    and stylized") PLAY's one character screen: every character as a card (regular, Iron, Steel, Silver, Randomized,
    second window), and CREATE A CHARACTER, which walks through the choices on cards of their own:
        Normal / Hardcore / Randomized
        Hardcore: Iron / Steel / Silver (Silver is permadeath)
        Randomized: permadeath? then randomize the squad too?
        Main window / 2nd window (when the second window is set up)
        the name (not for a Normal character: the game's own creation screen makes it)
    Picking a Hardcore or Randomized card plays with that mode's rules (as PLAY HARDCORE did). A 2nd-window card picked
    before a main one opens next to it once the main game is up."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Choose your character")
        self.configure(bg=DARK)
        self.minsize(1040, 600)                # the steps of CREATE A CHARACTER keep the window's size
        self.cards, self.images = [], []
        self.second_pick = None             # a 2nd-window character waiting for the main one
        self.choice = {}
        self.protocol("WM_DELETE_WINDOW", self.close)
        body = tk.Frame(self, bg=DARK)
        body.pack(fill="both", expand=True, padx=24, pady=18)
        self.heading = tk.Label(body, text="CHOOSE YOUR CHARACTER", bg=DARK, fg=w.GOLD, font=(w.UI_FONT, 24, "bold"))
        self.heading.pack(pady=(4, 2))
        self.sub = tk.Label(body, text="", bg=DARK, fg="#9a8f80", font=(w.UI_FONT, 10))
        self.sub.pack(pady=(0, 14))
        self.grid_box = tk.Frame(body, bg=DARK)
        self.grid_box.pack()
        self.extra = tk.Frame(body, bg=DARK)
        self.extra.pack(pady=(10, 0))
        bottom = tk.Frame(body, bg=DARK)
        bottom.pack(side="bottom", fill="x", pady=(14, 0))
        self.show_var = tk.BooleanVar(value=bool(app.cfg.get("char_cards", True)))
        self.show_box = tk.Checkbutton(bottom, text="Show this at PLAY", variable=self.show_var, command=self.toggle, bg=DARK,
                                       fg="#9a8f80", selectcolor=DARK, activebackground=DARK, activeforeground=w.GOLD,
                                       font=(w.UI_FONT, 9))
        self.show_box.pack(side="left")
        w.button(bottom, "Cancel", self.close, small=True).pack(side="right")
        self.back_btn = w.button(bottom, "Back", self.back, small=True)
        self.steps = []
        self.chars = cc.load_cache(cc.HERE, app.cfg.get("game_user", ""))
        self.show_list()
        threading.Thread(target=self.load_live, daemon=True).start()
        self.tick()

    # ------------------------------------------------------------ the list
    def load_live(self):
        """The database, when it's up, may know newer levels and places than the saved list."""
        try:
            chars = cc.refresh(cc.HERE, self.app.cfg, lambda: _connect(self.app))
        except Exception:
            return
        if chars is not None:
            try:
                self.after(0, lambda: self.live(chars))
            except tk.TclError:
                pass

    def live(self, chars):
        self.chars = chars
        if not self.steps:
            self.show_list()

    def clear(self):
        self.gen = getattr(self, "gen", 0) + 1           # cards still being dealt for the last step are dropped
        for box in (self.grid_box, self.extra):
            for child in box.winfo_children():
                child.destroy()
        self.cards = []

    def lay_out(self, items, box=None, per_row=None):
        """Cards dealt in one by one (a short stagger), each with sparks while the mouse is on it."""
        box = box or self.grid_box
        n = len(items)
        per_row = per_row or (5 if n > 8 else 4 if n > 4 else max(1, n))
        gen = self.gen
        for i, (c, render, on_pick) in enumerate(items):
            self.after(70 * i, lambda i=i, c=c, render=render, on_pick=on_pick:
                       self.deal(gen, box, c, render, on_pick, i // per_row, i % per_row))

    def deal(self, gen, box, c, render, on_pick, row, col):
        try:
            if gen != self.gen or not box.winfo_exists():
                return
            self.cards.append(Card(box, self, c, row, col, render, on_pick))
        except tk.TclError:
            pass

    def show_list(self):
        self.steps, self.choice = [], {}
        self.clear()
        self.back_btn.pack_forget()
        self.heading.configure(text="CHOOSE YOUR CHARACTER")
        waiting = self.second_pick
        self.sub.configure(text=(f"{waiting['name']} opens in the second window with the main character you pick."
                                 if waiting else "Pick a card and you're in: no character list."))
        items = [(c, None, self.picked) for c in self.chars] + [(None, None, lambda _c: self.create())]
        self.lay_out(items)
        seconds = cc.load_second(cc.HERE, self.app.cfg) if _second_ready(self.app) else []
        if seconds:
            tk.Label(self.extra, text="SECOND WINDOW", bg=DARK, fg="#9ad8c8", font=(w.UI_FONT, 11, "bold")).grid(
                row=0, column=0, columnspan=6, pady=(0, 4))
            row = tk.Frame(self.extra, bg=DARK)
            row.grid(row=1, column=0, columnspan=6)
            self.lay_out([(c, None, self.picked_second) for c in seconds], box=row, per_row=6)
        if not self.chars:
            self.sub.configure(text="No characters yet: CREATE A CHARACTER.")

    # ------------------------------------------------------------ picking a card
    def picked(self, c):
        if self.app.running:
            messagebox.showinfo("Your world is running", "Your world is already running. To play another main character, "
                                "press STOP first. (A SECOND WINDOW card opens the second window now.)", parent=self)
            return
        if c.get("perma") and c.get("dead"):
            messagebox.showinfo(c["name"], f"{c['name']} has fallen and rests on the memorial. It is deleted 7 days after it "
                                "fell.", parent=self)
            return
        self.app.autologin_slot = int(c["slot"])
        self.app.autologin_name = c.get("name")
        mode = int(c.get("hc") or 0)
        self.app.hardcore_mode = mode if mode in (1, 2, 3, 4) else 0      # its mode's rules, as PLAY HARDCORE did
        second = self.second_pick
        self.close()
        self.app.start()
        if second is not None:
            _second_after_main(self.app, second.get("slot"), second.get("name"))

    def picked_second(self, c):
        if c.get("perma") and c.get("dead"):
            self.picked(c)
            return
        if self.app.running:
            self.close()
            _launch_second(self.app, int(c["slot"]), c.get("name"))
            return
        same = self.second_pick is not None and self.second_pick.get("charid") == c.get("charid")
        self.second_pick = None if same else c
        self.sub.configure(text=(f"{c['name']} opens in the second window with the main character you pick." if not same
                                 else "Pick a card and you're in: no character list."))

    # ------------------------------------------------------------ CREATE A CHARACTER
    def step(self, heading, sub, choices, on_pick):
        self.clear()
        self.heading.configure(text=heading)
        self.sub.configure(text=sub)
        self.back_btn.pack(side="right", padx=8)
        items = []
        for value, title, lines, kind, mark in choices:
            render = (lambda lit, t=title, l=lines, k=kind, m=mark: cc.render_choice_card(t, l, k, lit, None, m))
            items.append(({"kind": kind, "value": value}, render, lambda c, v=value: on_pick(v)))
        self.lay_out(items)

    def go(self, name, *args):
        self.steps.append((name, args))
        getattr(self, "step_" + name)(*args)

    def back(self):
        if self.steps:
            self.steps.pop()
        if not self.steps:
            self.show_list()
            return
        name, args = self.steps[-1]
        getattr(self, "step_" + name)(*args)

    def create(self):
        self.steps, self.choice = [], {}
        self.go("kind")

    def step_kind(self):
        def chose(v):
            self.choice = {"kind": v}
            if v == "hardcore":
                self.go("mode")
            elif v == "random":
                self.choice["mode"] = 4
                self.go("perma")
            else:
                self.choice["mode"] = 0
                self.go_window()
        self.step("CREATE A CHARACTER", "What kind of character?", KIND_CHOICES, chose)

    def step_mode(self):
        def chose(v):
            self.choice["mode"] = v
            self.choice["perma"] = v == 3
            self.go_window()
        self.step("HARDCORE", "Choose your path. Once chosen, a mode can only be stepped down, never up.", MODE_CHOICES, chose)

    def step_perma(self):
        def chose(v):
            self.choice["perma"] = v
            self.go("squad")
        self.step("PERMADEATH?", "A Randomized character can fall for good, like Silver: one knock out and it's gone.",
                  PERMA_CHOICES, chose)

    def step_squad(self):
        def chose(v):
            self.choice["rsquad"] = v
            self.go_window()
        self.step("RANDOMIZE THE SQUAD?", "Your squad mates can roll their own looks and jobs too "
                  "(you can switch this later: !squad random on / off).", SQUAD_CHOICES, chose)

    def go_window(self):
        if _second_ready(self.app):
            self.go("window")
        else:
            self.choice["window"] = "main"
            self.after_window()

    def step_window(self):
        def chose(v):
            self.choice["window"] = v
            self.after_window()
        self.step("WHICH WINDOW?", "Play it as your main character, or as the dualbox character in the second window.",
                  WINDOW_CHOICES, chose)

    def after_window(self):
        if self.choice.get("mode", 0) == 0:
            self.begin_normal()
        else:
            self.go("name")

    def step_name(self):
        import launcher_hardcore as hc
        mode = self.choice["mode"]
        self.clear()
        self.back_btn.pack(side="right", padx=8)
        title = {1: "IRON", 2: "STEEL", 3: "SILVER", 4: "RANDOMIZED"}[mode]
        if mode == 4 and self.choice.get("perma"):
            title = "RANDOMIZED - PERMADEATH"
        self.heading.configure(text=title)
        self.sub.configure(text="\n".join(hc.RULES[mode][:4]))
        form = tk.Frame(self.grid_box, bg=DARK)
        form.pack(pady=6)
        if self.choice.get("perma"):
            tk.Label(form, text="When it falls, it is gone. There is no coming back.", bg=DARK, fg="#ff5a4a",
                     font=(w.UI_FONT, 12, "bold")).pack(pady=(0, 10))
        tk.Label(form, text=("The new character's name. Fate makes the rest now: race, face, size and nation, and its job "
                             "when it first logs in." if mode == 4 else
                             "The character's name: a new one you'll make on the game's character screen, or one that "
                             "hasn't gained a level yet."), bg=DARK, fg="#9a8f80", font=(w.UI_FONT, 10),
                 wraplength=620).pack(anchor="w")
        self.name_var = tk.StringVar()
        entry = tk.Entry(form, textvariable=self.name_var, font=(w.UI_FONT, 14), width=20, bg=w.PANEL, fg=w.FG,
                         insertbackground=w.FG)
        entry.pack(anchor="w", pady=6)
        entry.focus_set()
        entry.bind("<Return>", lambda e: self.begin())
        if mode in (2, 3) or self.choice.get("perma"):
            tk.Label(form, text="Typing the name is your confirmation: this is not a mode to pick by accident.", bg=DARK,
                     fg="#9a8f80", font=(w.UI_FONT, 9, "italic")).pack(anchor="w")
        where = "the second window" if self.choice.get("window") == "second" else "your main window"
        w.button(form, f"BEGIN ({where})", self.begin, primary=True).pack(anchor="w", pady=(12, 0))

    def begin_normal(self):
        if self.app.running and self.choice.get("window") != "second":
            messagebox.showinfo("Your world is running", "Press STOP first to make a main character.", parent=self)
            return
        if self.choice.get("window") == "second":
            self.start_second_screen()
            return
        self.app.autologin_slot = None
        self.app.hardcore_mode = 0
        self.close()
        self.app.start()
        self.app.say("The game's character screen: make your new character there.")

    def start_second_screen(self, mode=0):
        """The second window at its character screen (to make the character there)."""
        if self.app.running:
            self.close()
            _launch_second(self.app, None)
            return
        self.second_pick = {"slot": None, "name": "The second window (character screen)", "charid": -1}
        self.show_list()
        self.sub.configure(text="Now pick your main character: the second window opens at its character screen beside it.")

    def begin(self):
        import launcher_hardcore as hc
        name = self.name_var.get().strip()
        if not hc.NAME_RE.match(name):
            messagebox.showinfo("New character", "A character name is 3 to 15 letters (A-Z), no spaces.", parent=self)
            return
        name = name[0].upper() + name[1:].lower()
        mode, second = self.choice["mode"], self.choice.get("window") == "second"
        perma, rsquad = bool(self.choice.get("perma")) and mode == 4, bool(self.choice.get("rsquad"))
        if mode == 4:
            self.make_randomized(name, second, perma, rsquad)
            return
        try:
            hc.add_pending(cc.HERE, self.app.cfg.get("server_dir"), name, mode)
        except OSError as e:
            messagebox.showinfo("New character", f"Could not save it ({e}).", parent=self)
            return
        if not second and self.app.running:
            messagebox.showinfo("Your world is running", f"{name} is saved: it becomes {hc.MODES[mode]} at its first log in. "
                                "Press STOP, then make it from the main window.", parent=self)
            return
        if second:
            self.start_second_screen(mode)
            self.sub.configure(text=f"Make {name} on the second window's character screen: it becomes {hc.MODES[mode]} at its "
                               f"first log in. Now pick your main character.")
            return
        self.app.autologin_slot = None
        self.app.hardcore_mode = mode
        self.close()
        self.app.start()
        self.app.say(f"Make {name} on the character screen: it becomes {hc.MODES[mode]} the first time it logs in.")

    def make_randomized(self, name, second, perma, rsquad):
        import launcher_hardcore as hc
        cfg = self.app.cfg
        login = cfg.get("game_user2" if second else "game_user", "")
        self.sub.configure(text="Fate is rolling...")

        def work():
            try:
                conn = _connect(self.app)
                try:
                    charid, _roll = hc.create_randomized(conn, login, name, cfg.get("server_dir"))
                finally:
                    conn.close()
                hc.add_pending(cc.HERE, cfg.get("server_dir"), name, 4, charid, perma=perma, rsquad=rsquad)
                chars = cc.refresh(cc.HERE, cfg, lambda: _connect(self.app))
                text, ok = f"Fate has made {name}. Its card is ready: pick it to begin.", True
            except hc.CreateError as e:
                text, ok, chars = str(e), False, None
            except Exception as e:
                text, ok, chars = (f"Could not make the character ({e}). The world's database has to be running: press "
                                   f"PLAY once, close the game, then try again."), False, None

            def done():
                try:
                    if ok:
                        if chars is not None:
                            self.chars = chars
                        self.show_list()
                        self.sub.configure(text=text)
                    else:
                        self.sub.configure(text="")
                        messagebox.showinfo("Randomized", text, parent=self)
                except tk.TclError:
                    pass
            try:
                self.after(0, done)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------
    def tick(self):
        try:
            if not self.winfo_exists():
                return
            for card in self.cards:
                card.step()
            self.after(40, self.tick)
        except tk.TclError:
            pass

    def toggle(self):
        self.app.cfg["char_cards"] = bool(self.show_var.get())
        try:
            cc.save_config_value(cc.HERE, "char_cards", self.app.cfg["char_cards"])
        except Exception:
            pass

    def close(self):
        self.app.card_window = None
        try:
            self.destroy()
        except tk.TclError:
            pass


class Card:
    """One card: its picture on a canvas, rising into place when dealt, sparks while the mouse is on it."""

    def __init__(self, parent, screen, c, row, col, render=None, on_pick=None):
        from PIL import ImageTk
        self.screen, self.c = screen, c
        if render is not None:
            normal, lit = render(False), render(True)
        else:
            normal = cc.render_screen_card(False) if c is None else cc.render_card(c, False)
            lit = cc.render_screen_card(True) if c is None else cc.render_card(c, True)
        self.normal, self.lit_img = ImageTk.PhotoImage(normal), ImageTk.PhotoImage(lit)
        screen.images.extend([self.normal, self.lit_img])
        self.w, self.h = cc.CARD
        if render is not None:
            self.colours = cc.spark_colours({"dualbox": c["kind"] == "dualbox", "hc": {"iron": 1, "steel": 2, "silver": 3,
                                                                                       "random": 4}.get(c["kind"], 0)})
        else:
            self.colours = cc.spark_colours(c)                # the sparks match the card's border
        self.canvas = tk.Canvas(parent, width=self.w, height=self.h, bg=DARK, highlightthickness=0, cursor="hand2")
        self.canvas.grid(row=row, column=col, padx=8, pady=8)
        self.rise = 24                                         # dealt: slides up into place
        self.picture = self.canvas.create_image(0, self.rise, anchor="nw", image=self.normal)
        self.lit, self.sparks = False, []
        self.canvas.bind("<Enter>", self.enter)
        self.canvas.bind("<Leave>", self.leave)
        pick = on_pick or screen.picked
        self.canvas.bind("<Button-1>", lambda e: pick(c))

    def enter(self, _e=None):
        self.lit = True
        self.canvas.itemconfigure(self.picture, image=self.lit_img)

    def leave(self, _e=None):
        self.lit = False
        self.canvas.itemconfigure(self.picture, image=self.normal)

    def step(self):
        if self.rise > 0:
            move = max(1, self.rise // 3)
            self.rise -= move
            self.canvas.move(self.picture, 0, -move)
        held = self.screen.second_pick is not None and self.c is not None and self.c.get("dualbox") and \
            self.screen.second_pick.get("charid") == self.c.get("charid")
        if (self.lit or held) and len(self.sparks) < 36 and random.random() < 0.8:
            for _ in range(2):
                x = random.uniform(10, self.w - 10)
                size = random.uniform(1.5, 3.2)
                item = self.canvas.create_rectangle(x, self.h - 8, x + size, self.h - 8 + size, fill=random.choice(self.colours),
                                                    outline="")
                self.sparks.append([item, random.uniform(-0.5, 0.5), random.uniform(1.4, 3.2), random.randint(40, 90)])
        alive = []
        for item, dx, dy, life in self.sparks:
            life -= 1
            if life <= 0:
                self.canvas.delete(item)
                continue
            dx += random.uniform(-0.2, 0.2)
            self.canvas.move(item, dx, -dy)
            if life < 15:
                self.canvas.itemconfigure(item, stipple="gray50")
            alive.append([item, dx, dy, life])
        self.sparks = alive
