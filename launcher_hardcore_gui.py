"""The HARDCORE button and the Hardcore menu (2026-11-23). The rest of the hardcore work, with no tkinter, is in
launcher_hardcore.py.

attach(app) is called once the Play page is laid out (launcher_pages.PlayPage): it puts HARDCORE beside DUALBOX, writes
the server's hardcore files, starts the announcer and deletes Silver characters whose 7 days are up. before_play(app, rates)
is called by App.start at every PLAY: it writes the files again and, when PLAY HARDCORE asked for it, returns the mode's
world rules for that session.

The menu: a card per hardcore character (PLAY, STEP DOWN, and RESTORE on the dev PC for a Silver that fell to a bug), then
NEW HARDCORE CHARACTER, the mode pick screen: the mode cards side by side on a dark screen; the card under the mouse lights up
and sends up embers in its metal's colour, and its rules show below. Steel and Silver are confirmed by typing the character's
name. RANDOM (Randomized, 2026-11-23) starts a Randomized character the same way. The pictures are assets\\ui\\hardcore*.png and
hc_card_*.png (every theme has its own, made by art-src\\scripts\\hardcore_art.py).
"""
import os
import random
import threading
import tkinter as tk
from tkinter import messagebox

import launcher_hardcore as hc
import launcher_widgets as w

HERE = os.path.dirname(os.path.abspath(__file__))
EMBER = {1: ("#c8ccd6", "#8c919e"), 2: ("#96bef0", "#4a6fa8"), 3: ("#ff6a4a", "#e8e8f8"), 4: ("#d6b4ff", "#8c5ad8")}
CARD_KEYS = {1: "iron", 2: "steel", 3: "silver", 4: "random"}


def _image(name, suffix=""):
    path = os.path.join(HERE, "assets", "ui", name + suffix + ".png")
    if not os.path.exists(path):
        return None
    try:
        return tk.PhotoImage(file=path)          # a theme's own picture when it has one (launcher_theme swaps it in)
    except tk.TclError:
        return None


def _connect(app):
    import launcher_passport as pp
    return pp.connect(app.cfg)


def _bot_base():
    try:
        import launcher_passport as pp
        return pp.BOT_ACCOUNT_BASE
    except Exception:
        return 21000000


def _world(app):
    """(is this an open world, its name) from the CO-OP settings."""
    try:
        import launcher_coop as co
        s = co.load_settings(HERE)
        name = ""
        try:
            import launcher_passport as pp
            conn = pp.connect(app.cfg)
            try:
                name = pp.world_identity(conn)["name"]
            finally:
                conn.close()
        except Exception:
            pass
        return bool(s.get("hosting") and s.get("open")), name
    except Exception:
        return False, ""


# ---------------------------------------------------------------- hooks
def before_play(app, rates):
    mode = getattr(app, "hardcore_mode", 0)
    app.hardcore_mode = 0
    try:
        is_open, name = _world(app)
        for problem in hc.write_server_files(HERE, app.cfg.get("server_dir"), is_open, name):
            app.say(f"Hardcore: {problem}")
    except Exception as problem:
        app.say(f"Hardcore: the server's hardcore files could not be written ({problem}).")
    if mode in hc.MODES:
        app.say(f"PLAY HARDCORE: this session uses the {hc.MODES[mode]} rules (your own rules on the RULES page are kept for PLAY).")
        return hc.session_rates(HERE, rates, mode)
    return rates


def attach(app, page=None):
    app.hardcore_mode = 0
    images = {"normal": _image("hardcore"), "hover": _image("hardcore", "_hover"), "off": _image("hardcore", "_off")}
    if images["normal"] is not None:
        app._images.extend(i for i in images.values() if i)
        cls = type(app.dual_btn)
        app.hardcore_btn = cls(app.dual_btn.master, images, lambda: open_menu(app), "HARDCORE")
    else:
        app.hardcore_btn = w.button(app.dual_btn.master, "HARDCORE", lambda: open_menu(app), primary=True)
    app.hardcore_btn.pack(side="left", padx=(0, 22), after=app.dual_btn)

    def background():
        try:
            is_open, name = _world(app)
            hc.write_server_files(HERE, app.cfg.get("server_dir"), is_open, name)
        except Exception:
            pass
        try:
            conn = _connect(app)
            try:
                gone = hc.expire_fallen(conn, _bot_base())
                if hc.prune_pending(HERE, conn, _bot_base()):          # (2026-11-24) deleted characters leave the list
                    is_open, name = _world(app)
                    hc.write_server_files(HERE, app.cfg.get("server_dir"), is_open, name)
            finally:
                conn.close()
            for name in gone:
                app.say(f"Hardcore: {name} (Silver) fell 7 days ago and has been deleted. Rest well.")
        except Exception:
            pass

    threading.Thread(target=background, daemon=True).start()
    try:
        import launcher_stinkshell as ls
        key = ls.key_for(HERE)
        app.hardcore_announcer = hc.Announcer(HERE, app.cfg.get("server_dir"), key, is_open=lambda: _world_open_cached(app),
                                              log=lambda text: _say_later(app, text))
        app.hardcore_announcer.start()
    except Exception:
        pass


_open_cache = {"t": 0, "value": False}


def _world_open_cached(app):
    import time
    if time.time() - _open_cache["t"] > 60:
        try:
            import launcher_coop as co
            s = co.load_settings(HERE)
            _open_cache["value"] = bool(s.get("hosting") and s.get("open"))
        except Exception:
            _open_cache["value"] = False
        _open_cache["t"] = time.time()
    return _open_cache["value"]


def _say_later(app, text):
    try:
        app.after(0, lambda: app.say(text))
    except Exception:
        pass


def open_menu(app):
    existing = getattr(app, "hardcore_window", None)
    if existing is not None:
        try:
            existing.lift()
            existing.focus_force()
            return
        except tk.TclError:
            pass
    app.hardcore_window = HardcoreMenu(app)


# ---------------------------------------------------------------- the menu
class HardcoreMenu(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Hardcore")
        self.configure(bg=w.BG)
        self.geometry("1100x720")
        self.minsize(1080, 660)
        self.images = []
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.body = None
        self.show_list()

    def close(self):
        self.app.hardcore_window = None
        self.destroy()

    def clear(self):
        if self.body is not None:
            self.body.destroy()
        self.body = tk.Frame(self, bg=w.BG)
        self.body.pack(fill="both", expand=True, padx=24, pady=18)
        return self.body

    def header(self, parent, title, sub):
        tk.Label(parent, text=title, bg=w.BG, fg=w.GOLD, font=(w.UI_FONT, 22, "bold")).pack(anchor="w")
        tk.Label(parent, text=sub, bg=w.BG, fg=w.DIM, font=(w.UI_FONT, 10), justify="left").pack(anchor="w", pady=(0, 12))

    # ----- the list of hardcore characters
    def show_list(self):
        body = self.clear()
        self.header(body, "HARDCORE", "Iron, Steel and Silver characters. Their rates are locked, they earn everything "
                                      "themselves, and the harder the mode, the more a fall costs.")
        top = tk.Frame(body, bg=w.BG)
        top.pack(fill="x")
        w.button(top, "NEW HARDCORE CHARACTER", self.show_pick, primary=True).pack(side="left")
        self.status = tk.Label(top, text="Reading your characters...", bg=w.BG, fg=w.DIM, font=(w.UI_FONT, 9))
        self.status.pack(side="left", padx=14)
        self.cards = tk.Frame(body, bg=w.BG)
        self.cards.pack(fill="both", expand=True, pady=(14, 8))
        self.options(body)
        threading.Thread(target=self.load_cards, daemon=True).start()

    def load_cards(self):
        try:
            conn = _connect(self.app)
            try:
                if hc.prune_pending(HERE, conn, _bot_base()):          # (2026-11-24) deleted characters leave the list
                    try:
                        hc.write_server_files(HERE, self.app.cfg.get("server_dir"), *_world(self.app))
                    except Exception:
                        pass
                found = hc.characters(conn, _bot_base())
            finally:
                conn.close()
            problem = None
        except Exception as e:
            found, problem = [], e
        try:
            self.after(0, lambda: self.fill_cards(found, problem))
        except tk.TclError:
            pass

    def fill_cards(self, found, problem):
        try:
            for child in self.cards.winfo_children():
                child.destroy()
        except tk.TclError:
            return
        if problem is not None:
            self.status.configure(text="Your world's database isn't running: press PLAY once, then open this again.")
            for entry in hc.settings(HERE)["pending"]:
                self.pending_row(entry)
            return
        hc.forget_pending(HERE, [c["name"] for c in found])
        pending = hc.settings(HERE)["pending"]
        self.status.configure(text=f"{len(found)} hardcore character{'s' if len(found) != 1 else ''}" +
                              (f", {len(pending)} waiting to start" if pending else ""))
        if not found and not pending:
            tk.Label(self.cards, text="No hardcore characters yet. NEW HARDCORE CHARACTER starts one.", bg=w.BG, fg=w.DIM,
                     font=(w.UI_FONT, 11)).pack(anchor="w", pady=20)
        for entry in pending:
            self.pending_row(entry)
        for entry in found:
            self.card_row(entry)

    def pending_row(self, entry):
        row = tk.Frame(self.cards, bg=w.PANEL, highlightbackground=w.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=4)
        mode = int(entry.get("mode", 1))
        tk.Label(row, text=f"{entry.get('name')}  ·  {hc.MODES.get(mode, '?')}  ·  waiting for its first log in", bg=w.PANEL,
                 fg=w.FG, font=(w.UI_FONT, 11, "bold")).pack(side="left", padx=12, pady=10)
        w.button(row, "PLAY RANDOMIZED" if mode == 4 else "PLAY HARDCORE", lambda m=mode: self.play(m), primary=True,
                 small=True).pack(side="right", padx=8)
        w.button(row, "Cancel", lambda n=entry.get("name"): self.cancel_pending(n), small=True).pack(side="right")

    def card_row(self, c):
        key = hc.KEYS[c["mode"]]
        row = tk.Frame(self.cards, bg=w.PANEL, highlightbackground=w.BORDER, highlightthickness=1)
        row.pack(fill="x", pady=4)
        icon = _image(f"hc_card_{key}", "_off" if c["left"] is not None else "")
        if icon is not None:
            small = icon.subsample(4, 4)
            self.images.extend([icon, small])
            tk.Label(row, image=small, bg=w.PANEL).pack(side="left", padx=(8, 12), pady=6)
        text = tk.Frame(row, bg=w.PANEL)
        text.pack(side="left", fill="x", expand=True)
        title = f"{c['name']}  ·  {hc.MODES[c['mode']]}"
        tk.Label(text, text=title, bg=w.PANEL, fg=w.GOLD, font=(w.UI_FONT, 13, "bold"), anchor="w").pack(fill="x")
        import time
        lasted = hc.survival_text((c["dead"] or time.time()) - c["start"]) if c["start"] else "?"
        line = f"{c['job']} {c['level']}  ·  hardcore for {lasted}  ·  deaths {c['deaths']}"
        if c["mode"] == 2:
            line += f"  ·  jobs back to 1: {c['resets']}"
        if c["milestones"]:
            line += "  ·  milestones: " + ", ".join(f"{j} {v}" for j, v in sorted(c["milestones"].items()))
        tk.Label(text, text=line, bg=w.PANEL, fg=w.FG, font=(w.UI_FONT, 10), anchor="w").pack(fill="x")
        if c["left"] is not None:
            tk.Label(text, text=f"Fallen. Rests on the memorial; deleted in {hc.survival_text(c['left'])}.", bg=w.PANEL, fg="#ff6a6a",
                     font=(w.UI_FONT, 10, "italic"), anchor="w").pack(fill="x")
            if not self.app.cfg.get("mariadb_dir"):           # the dev PC: a Silver that fell to a bug can be brought back
                w.button(row, "RESTORE (bug)", lambda cid=c["charid"], n=c["name"]: self.restore(cid, n), small=True).pack(side="right", padx=8)
            return
        w.button(row, "PLAY HARDCORE" if c["mode"] in hc.HARDCORE else "PLAY RANDOMIZED", lambda m=c["mode"]: self.play(m),
                 primary=True, small=True).pack(side="right", padx=8)
        if c["mode"] in hc.HARDCORE:
            lower = "a regular character" if c["mode"] == 1 else "Iron"
            w.button(row, f"Step down to {lower}", lambda cid=c["charid"], n=c["name"], m=c["mode"]: self.step_down(cid, n, m),
                     small=True).pack(side="right")

    def options(self, body):
        box = tk.Frame(body, bg=w.BG)
        box.pack(fill="x", side="bottom")
        s = hc.settings(HERE)
        self.only = tk.BooleanVar(value=bool(s["hardcore_only"]))
        self.share = tk.BooleanVar(value=bool(s["share"]))
        for var, text in ((self.only, "My world takes hardcore visitors only (co-op and open worlds; the world list says so)"),
                          (self.share, "Share my hardcore milestones and deaths on the hub and in Stinkshell")):
            tk.Checkbutton(box, text=text, variable=var, command=self.save_options, bg=w.BG, fg=w.FG, selectcolor=w.PANEL2,
                           activebackground=w.BG, activeforeground=w.GOLD, font=(w.UI_FONT, 10), anchor="w").pack(fill="x")
        tk.Label(box, text="Changes to these apply at your next PLAY.", bg=w.BG, fg=w.DIM, font=(w.UI_FONT, 8)).pack(anchor="w")

    def save_options(self):
        s = hc.settings(HERE)
        s["hardcore_only"], s["share"] = bool(self.only.get()), bool(self.share.get())
        hc.save_settings(HERE, s)

    # ----- actions
    def play(self, mode):
        if self.app.running:
            messagebox.showinfo("Hardcore", f"Your world is already running with its usual rules. Your hardcore characters still "
                                f"keep their own rates. For the full {hc.MODES[mode]} world rules, press STOP, then PLAY HARDCORE.",
                                parent=self)
            return
        self.app.hardcore_mode = mode
        self.close()
        self.app.start()

    def cancel_pending(self, name):
        s = hc.settings(HERE)
        s["pending"] = [e for e in s["pending"] if str(e.get("name", "")).lower() != str(name).lower()]
        hc.save_settings(HERE, s)
        try:
            hc.write_server_files(HERE, self.app.cfg.get("server_dir"), *_world(self.app))
        except Exception:
            pass
        self.show_list()

    def step_down(self, charid, name, mode):
        lower = "a regular character" if mode == 1 else "Iron"
        if not messagebox.askyesno("Step down", f"Step {name} down from {hc.MODES[mode]} to {lower}?\n\nThis can't be undone: "
                                   f"a character never goes back up to a harder mode.", parent=self):
            return
        try:
            conn = _connect(self.app)
            try:
                hc.step_down(conn, charid)
            finally:
                conn.close()
        except Exception as e:
            messagebox.showinfo("Step down", str(e), parent=self)
            return
        self.show_list()

    def restore(self, charid, name):
        if not messagebox.askyesno("Restore", f"Bring {name} back? Only for a death caused by a bug.", parent=self):
            return
        try:
            conn = _connect(self.app)
            try:
                hc.restore(conn, charid)
            finally:
                conn.close()
        except Exception as e:
            messagebox.showinfo("Restore", str(e), parent=self)
            return
        self.show_list()

    # ----- the mode pick screen
    def show_pick(self):
        body = self.clear()
        body.configure(bg="#07060a")
        self.configure(bg="#07060a")
        tk.Label(body, text="CHOOSE YOUR PATH", bg="#07060a", fg=w.GOLD, font=(w.UI_FONT, 24, "bold")).pack(pady=(4, 2))
        tk.Label(body, text="Once chosen, a mode can only be stepped down, never up.", bg="#07060a", fg="#9a8f80",
                 font=(w.UI_FONT, 10)).pack(pady=(0, 14))
        row = tk.Frame(body, bg="#07060a")
        row.pack()
        self.rules_box = tk.Label(body, text="", bg="#07060a", fg="#e8dcc0", font=(w.UI_FONT, 11), justify="center")
        self.rules_box.pack(pady=(16, 6))
        self.mode_cards = []
        for mode in (1, 2, 3, 4):
            self.mode_cards.append(ModeCard(row, self, mode))
        bottom = tk.Frame(body, bg="#07060a")
        bottom.pack(side="bottom", fill="x")
        w.button(bottom, "Back", self.back_to_list, small=True).pack(side="left")
        self.ember_tick()

    def back_to_list(self):
        self.configure(bg=w.BG)
        self.show_list()

    def hovered(self, mode):
        if mode in hc.RULES:
            self.rules_box.configure(text=hc.MODES[mode].upper() + "\n" + "\n".join(hc.RULES[mode]))
        else:
            self.rules_box.configure(text="")

    def ember_tick(self):
        try:
            if not self.winfo_exists() or not getattr(self, "mode_cards", None):
                return
            for card in self.mode_cards:
                card.step()
            self.after(40, self.ember_tick)
        except tk.TclError:
            pass

    def picked(self, mode):
        self.show_confirm(mode)

    def show_confirm(self, mode):
        self.mode_cards = []
        body = self.clear()
        body.configure(bg="#07060a")
        name = hc.MODES[mode]
        tk.Label(body, text=f"{name.upper()} HARDCORE" if mode in hc.HARDCORE else "RANDOMIZED", bg="#07060a", fg=w.GOLD, font=(w.UI_FONT, 24, "bold")).pack(pady=(4, 8))
        tk.Label(body, text="\n".join(hc.RULES[mode]), bg="#07060a", fg="#e8dcc0", font=(w.UI_FONT, 11), justify="left").pack()
        if mode == 3:
            tk.Label(body, text="When a Silver character falls, it is gone. There is no coming back.", bg="#07060a", fg="#ff5a4a",
                     font=(w.UI_FONT, 12, "bold")).pack(pady=(10, 0))
        form = tk.Frame(body, bg="#07060a")
        form.pack(pady=18)
        tk.Label(form, text=("The new character's name. Fate makes the character now: race, face, size and nation are rolled, "
                             "and its job when it first logs in. No character creation screen." if mode == 4 else
                             "The character's name: a new one you will make in the game, or one below that hasn't gained a level yet."),
                 bg="#07060a", fg="#9a8f80", font=(w.UI_FONT, 10)).pack(anchor="w")
        self.name_var = tk.StringVar()
        entry = tk.Entry(form, textvariable=self.name_var, font=(w.UI_FONT, 14), width=20, bg=w.PANEL, fg=w.FG, insertbackground=w.FG)
        entry.pack(anchor="w", pady=6)
        entry.focus_set()
        if mode in (2, 3):
            tk.Label(form, text=f"Typing the name is your confirmation: {name} is not a mode to pick by accident.",
                     bg="#07060a", fg="#9a8f80", font=(w.UI_FONT, 9, "italic")).pack(anchor="w")
        self.ready_box = tk.Frame(form, bg="#07060a")
        self.ready_box.pack(anchor="w", pady=(8, 0))
        threading.Thread(target=self.load_eligible, daemon=True).start()
        buttons = tk.Frame(body, bg="#07060a")
        buttons.pack(pady=8)
        w.button(buttons, f"BEGIN {name.upper()}", lambda: self.begin(mode), primary=True).pack(side="left", padx=6)
        w.button(buttons, "Back", self.show_pick, small=True).pack(side="left", padx=6)

    def load_eligible(self):
        try:
            conn = _connect(self.app)
            try:
                names = [n for _cid, n in hc.eligible(conn, _bot_base())]
            finally:
                conn.close()
        except Exception:
            names = []
        try:
            self.after(0, lambda: self.fill_eligible(names))
        except tk.TclError:
            pass

    def create_randomized(self, name):
        """(2026-11-23) Randomized: the launcher makes the character itself, with everything rolled but the name."""
        cfg = self.app.cfg

        def work():
            try:
                conn = _connect(self.app)
                try:
                    charid, _roll = hc.create_randomized(conn, cfg.get("game_user", ""), name, cfg.get("server_dir"))
                finally:
                    conn.close()
                hc.add_pending(HERE, cfg.get("server_dir"), name, 4, charid)
                text, ok = (f"Fate has made {name}.\n\nPress PLAY RANDOMIZED and choose {name} on the character list. "
                            f"Who you are, where you were born and what job you start with: you'll find out when you arrive."), True
            except hc.CreateError as e:
                text, ok = str(e), False
            except Exception as e:
                text, ok = (f"Could not make the character ({e}). The world's database has to be running: press PLAY once, "
                            f"close the game, then try again."), False

            def done():
                try:
                    messagebox.showinfo("Randomized", text, parent=self)
                    if ok:
                        self.configure(bg=w.BG)
                        self.show_list()
                except tk.TclError:
                    pass
            try:
                self.after(0, done)
            except tk.TclError:
                pass

        threading.Thread(target=work, daemon=True).start()

    def fill_eligible(self, names):
        self.eligible_names = {n.lower() for n in names}
        try:
            if not names:
                return
            tk.Label(self.ready_box, text="Level 1 characters you have:", bg="#07060a", fg="#9a8f80", font=(w.UI_FONT, 9)).pack(side="left")
            for n in names[:8]:
                w.link(self.ready_box, n, lambda v=n: self.name_var.set(v), bg="#07060a").pack(side="left", padx=5)
        except tk.TclError:
            pass

    def begin(self, mode):
        name = self.name_var.get().strip()
        if not hc.NAME_RE.match(name):
            messagebox.showinfo("Hardcore", "A character name is 3 to 15 letters (A-Z), no spaces.", parent=self)
            return
        name = name[0].upper() + name[1:].lower()
        if mode == 4 and name.lower() not in getattr(self, "eligible_names", set()):
            self.create_randomized(name)
            return
        try:
            hc.add_pending(HERE, self.app.cfg.get("server_dir"), name, mode)
        except OSError as e:
            messagebox.showinfo("Hardcore", f"Could not save it ({e}).", parent=self)
            return
        messagebox.showinfo("Hardcore", f"{name} will become {hc.MODES[mode]} the first time it logs in.\n\n"
                            f"Press PLAY HARDCORE, then make {name} on the character screen (or log in, if it already exists). "
                            f"Its first level must still be ahead of it.", parent=self)
        self.configure(bg=w.BG)
        self.show_list()


class ModeCard:
    """One mode's card on the pick screen: its picture on a canvas, embers rising while the mouse is on it."""

    def __init__(self, parent, menu, mode):
        self.menu, self.mode = menu, mode
        key = CARD_KEYS[mode]
        disabled = False
        self.normal = _image(f"hc_card_{key}", "_off" if disabled else "")
        self.hover = _image(f"hc_card_{key}", "_off" if disabled else "_hover") or self.normal
        menu.images.extend(i for i in (self.normal, self.hover) if i)
        wdt = self.normal.width() if self.normal else 232
        hgt = self.normal.height() if self.normal else 330
        self.canvas = tk.Canvas(parent, width=wdt, height=hgt, bg="#07060a", highlightthickness=0, cursor="arrow" if disabled else "hand2")
        self.canvas.pack(side="left", padx=10)
        if self.normal:
            self.picture = self.canvas.create_image(0, 0, anchor="nw", image=self.normal)
        else:
            self.picture = None
            self.canvas.create_text(wdt // 2, hgt // 2, text=key.upper(), fill="white", font=(w.UI_FONT, 20, "bold"))
        if disabled:
            self.canvas.create_rectangle(0, hgt // 2 - 18, wdt, hgt // 2 + 18, fill="#000000", stipple="gray50", outline="")
            self.canvas.create_text(wdt // 2, hgt // 2, text="COMING SOON", fill="#d6b4ff", font=(w.UI_FONT, 14, "bold"))
        self.w, self.h, self.lit, self.embers = wdt, hgt, False, []
        self.canvas.bind("<Enter>", self.enter)
        self.canvas.bind("<Leave>", self.leave)
        self.canvas.bind("<Button-1>", lambda e: menu.picked(mode))

    def enter(self, _event=None):
        self.lit = True
        if self.picture is not None and self.hover:
            self.canvas.itemconfigure(self.picture, image=self.hover)
        self.menu.hovered(self.mode)

    def leave(self, _event=None):
        self.lit = False
        if self.picture is not None and self.normal:
            self.canvas.itemconfigure(self.picture, image=self.normal)

    def step(self):
        """Embers rise from the bottom of the lit card and fade; the others let theirs burn out."""
        colours = EMBER[self.mode]
        if self.lit and len(self.embers) < 40 and random.random() < 0.8:
            for _ in range(2):
                x = random.uniform(8, self.w - 8)
                size = random.uniform(1.5, 3.5)
                item = self.canvas.create_oval(x, self.h - 6, x + size, self.h - 6 + size, fill=random.choice(colours), outline="")
                self.embers.append([item, random.uniform(-0.6, 0.6), random.uniform(1.6, 3.6), random.randint(40, 90)])
        alive = []
        for ember in self.embers:
            item, dx, dy, life = ember
            life -= 1
            if life <= 0:
                self.canvas.delete(item)
                continue
            dx += random.uniform(-0.25, 0.25)
            self.canvas.move(item, dx, -dy)
            if life < 15:
                self.canvas.itemconfigure(item, stipple="gray50")
            alive.append([item, dx, dy, life])
        self.embers = alive
