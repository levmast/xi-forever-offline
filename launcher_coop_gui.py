"""The launcher's CO-OP page (experimental): host your world for friends, or visit a friend's world.

All the work is in launcher_coop.py (talking to the other launcher, the PC's settings) and launcher_passport.py (the
character itself); this file is only the page. Anything slow (the database, the network) runs in a background thread and
its result comes back through a queue, so the window never freezes.
"""
import copy
import json
import os
import queue
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

import launcher_coop as co
import launcher_core as core
import launcher_passport as pp

BG, PANEL, PANEL2, FG, DIM = "#0a1118", "#101c28", "#162634", "#e9f1f5", "#8aa0ad"
BORDER, GOLD, GREEN, RED, ACCENT = "#1d3445", "#e6be64", "#3ecf6e", "#e5534b", "#35c4e0"
try:        # a limited-time look (a dated .json in assets\press) stands in for these colours while it is in date: launcher_theme.py
    import launcher_theme
    globals().update(launcher_theme.colours(globals()))
except Exception:
    pass
_UI_FONT = core.ui_fonts()[0]
FONT, SMALL, BOLD = (_UI_FONT, 10), (_UI_FONT, 9), (_UI_FONT, 10, "bold")
KEEP_SECONDS = 20                    # how often a visit is looked at (is the host there, time for a fresh copy...)
GUESTS_SECONDS = 6                   # how often the host's list of visitors is refreshed
CLOSE_GRACE_SECONDS = 60             # Stop hosting: visitors get this long to log out before they are packed for home
TAILSCALE_URL = "https://tailscale.com/download"
INTRO = ("Co-op lets a friend bring their own character into your world, or you into theirs. Whatever is earned on a "
         "visit goes home with the visitor. It works on the same network (LAN or Wi-Fi, no internet needed) and over "
         "the internet with Tailscale.\n\n"
         "This is an early test version: both of you need the same version of XI: Forever Offline. A character's "
         "squad mates travel with it, and a copy of each travelling character is saved before every trip.")
TAILSCALE_STEPS = ("Tailscale is a free program that puts your PC and your friend's on one private network, so nothing "
                   "on your PC is opened to the rest of the internet.\n\n"
                   "1. Both of you get Tailscale: GET TAILSCALE below downloads its installer from Tailscale's own site "
                   "and starts it. Then log in from the Tailscale icon near the clock (the account is free).\n"
                   "2. The host opens the Tailscale admin page (Machines), picks this PC, chooses Share and sends the "
                   "link to the friend, who accepts it.\n"
                   "3. Back here, the host picks 'Over the internet with Tailscale': the address that starts with 100. "
                   "appears by itself. Start hosting and send the invite code.\n\n"
                   "The visitor keeps Tailscale switched on too. "
                   "The free plan is enough (up to 6 people in one network, and sharing with others).")


def when(stamp):
    """'3 minutes ago' for a time in seconds."""
    if not stamp:
        return "never"
    seconds = max(0, int(time.time() - stamp))
    if seconds < 90:
        return "just now"
    if seconds < 5400:
        return f"{seconds // 60} minutes ago"
    if seconds < 129600:
        return f"{seconds // 3600} hours ago"
    return f"{seconds // 86400} days ago"


class CoopTab(tk.Frame):
    def __init__(self, parent, app, button_class):
        super().__init__(parent, bg=BG)
        self.app, self.cfg, self.kit, self.button_class = app, app.cfg, core.KIT_DIR, button_class
        self.sets, self.loaded = {}, False
        self.settings = co.load_settings(self.kit)
        self.host = None
        self.q = queue.Queue()
        self.images = {}
        self.away_rows, self.guest_rows, self.characters = [], [], []
        self.closing_since, self.closing_job = None, False
        self.last_keep = self.last_guests = 0
        self.keeping = self.listing = False
        self.note_text = tk.StringVar(value="")
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.build()
        self.after(400, self.pump)
        self.after(1500, self.tick)
        if self.settings["enabled"]:
            self.job(self.load_everything, self.show_everything)

    # ----- plumbing -----
    def picture(self, name):
        if name not in self.images:
            try:
                self.images[name] = tk.PhotoImage(file=os.path.join(self.kit, "assets", "ui", name + ".png"))
            except tk.TclError:
                self.images[name] = None
        return self.images[name]

    def button(self, parent, name, command, text):
        """A picture button (normal, hover and off pictures from assets\\ui; plain text if they are missing)."""
        if name not in self.sets:
            normal = self.picture(name)
            self.sets[name] = {"normal": normal, "hover": self.picture(name + "_hover") or normal, "off": self.picture(name + "_off") or normal}
        return self.button_class(parent, self.sets[name], command, text)

    def badge(self, parent, name, text):
        image = self.picture("coop_badge_" + name)
        if image:
            return tk.Label(parent, image=image, bg=parent.cget("bg"), bd=0)
        return tk.Label(parent, text=f" {text} ", bg=PANEL2, fg=GOLD, font=(_UI_FONT, 8, "bold"))

    def connect(self):
        return pp.connect(self.cfg)

    def note(self, text):
        self.note_text.set(text)

    def log(self, text):
        """A line for the launcher's activity log (safe from any thread)."""
        try:
            self.app.say(text)
        except Exception:
            pass
        self.q.put(("note", text, None))

    def job(self, work, done=None, label=None):
        """Runs work() in the background; done(result) is called in the window when it finished, or the error is shown."""
        if label:
            self.note(label)

        def run():
            try:
                self.q.put((done, work(), None))
            except Exception as e:
                self.q.put((done, None, e))

        threading.Thread(target=run, daemon=True).start()

    def pump(self):
        try:
            while True:
                done, result, error = self.q.get_nowait()
                if done == "note":
                    self.note(result)
                elif error is not None:
                    self.fail(error)
                elif done is not None:
                    done(result)
        except queue.Empty:
            pass
        except Exception as e:
            self.fail(e)
        if self.winfo_exists():
            self.after(300, self.pump)

    def fail(self, error):
        self.keeping = self.listing = self.closing_job = False
        if isinstance(error, (co.CoopError, pp.PassportError)):
            self.note(str(error))
            messagebox.showwarning("Co-op", str(error), parent=self)
            return
        text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        try:
            os.makedirs(os.path.join(self.kit, "logs"), exist_ok=True)
            with open(os.path.join(self.kit, "logs", "coop-error.log"), "a", encoding="utf-8") as handle:
                handle.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + text + "\n")
        except OSError:
            pass
        self.note(f"Something went wrong: {type(error).__name__}: {error}")
        messagebox.showerror("Co-op", f"{type(error).__name__}: {error}\n\n(Details are in logs\\coop-error.log.)", parent=self)

    # ----- the page -----
    def build(self):
        for child in self.body.winfo_children():
            child.destroy()
        if not self.settings["enabled"]:
            self.build_intro()
            return
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x", padx=14, pady=(10, 2))
        tk.Label(top, text="Co-op", bg=BG, fg=FG, font=(_UI_FONT, 14, "bold")).pack(side="left")
        self.badge(top, "experimental", "EXPERIMENTAL").pack(side="left", padx=10)
        tk.Label(top, text="Same version on both PCs. Squad mates travel with their character.", bg=BG, fg=DIM, font=SMALL).pack(side="left")
        tk.Button(top, text="Turn co-op off", command=self.turn_off, bg=PANEL, fg=DIM, relief="flat", padx=8, font=SMALL).pack(side="right")
        columns = tk.Frame(self.body, bg=BG)
        columns.pack(fill="both", expand=True, padx=8)
        left = tk.Frame(columns, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 8))
        tk.Frame(columns, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)
        right = tk.Frame(columns, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 6))
        self.build_host(left)
        self.build_visit(right)
        tk.Label(self.body, textvariable=self.note_text, bg=BG, fg=GOLD, font=SMALL, anchor="w", justify="left",
                 wraplength=1040).pack(fill="x", padx=16, pady=(2, 6))

    def build_intro(self):
        box = tk.Frame(self.body, bg=BG)
        box.pack(expand=True)
        row = tk.Frame(box, bg=BG)
        row.pack(pady=(0, 8))
        tk.Label(row, text="Co-op", bg=BG, fg=FG, font=(_UI_FONT, 18, "bold")).pack(side="left")
        self.badge(row, "experimental", "EXPERIMENTAL").pack(side="left", padx=12)
        tk.Label(box, text=INTRO, bg=BG, fg=FG, font=FONT, wraplength=640, justify="left").pack(pady=(0, 16))
        self.button(box, "coop_on", self.turn_on, "TURN CO-OP ON").pack()
        tk.Label(box, textvariable=self.note_text, bg=BG, fg=GOLD, font=SMALL, wraplength=640).pack(pady=(12, 0))

    def heading(self, parent, name, text):
        image = self.picture(name)
        if image:
            tk.Label(parent, image=image, bg=BG, bd=0).pack(pady=(8, 8))
        else:
            tk.Label(parent, text=text, bg=BG, fg=GOLD, font=(_UI_FONT, 13, "bold")).pack(pady=(8, 8))

    def field(self, parent, label, width=15):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=BG, fg=DIM, font=SMALL, width=width, anchor="w").pack(side="left")
        return row

    def entry(self, parent, variable, width, readonly=False, fill=False):
        widget = tk.Entry(parent, textvariable=variable, width=width, bg=PANEL2, fg=FG, insertbackground=FG, relief="flat",
                          font=FONT, readonlybackground=PANEL2, highlightbackground=BORDER, highlightthickness=1,
                          state="readonly" if readonly else "normal")
        widget.pack(side="left", ipady=3, fill="x", expand=fill)
        return widget

    def build_host(self, parent):
        self.heading(parent, "coop_head_host", "HOST MY WORLD")
        self.world_name = tk.StringVar()
        row = self.field(parent, "World name")
        self.entry(row, self.world_name, 30)
        self.mode = tk.StringVar(value=self.settings["mode"] if self.settings["mode"] in ("lan", "tailscale") else "lan")
        row = self.field(parent, "Friends reach me")
        modes = tk.Frame(row, bg=BG)
        modes.pack(side="left")
        for value in ("lan", "tailscale"):
            line = tk.Frame(modes, bg=BG)
            line.pack(anchor="w")
            tk.Radiobutton(line, text=co.MODES[value], value=value, variable=self.mode, command=self.mode_changed, bg=BG, fg=FG,
                           selectcolor=PANEL, activebackground=BG, activeforeground=FG, font=FONT, highlightthickness=0, bd=0).pack(side="left")
            if value == "tailscale":
                how = tk.Label(line, text="How?", bg=BG, fg=ACCENT, cursor="hand2", font=(_UI_FONT, 9, "underline"))
                how.pack(side="left", padx=6)
                how.bind("<Button-1>", lambda e: self.tailscale_help())
        row = self.field(parent, "My address")
        self.address = tk.StringVar(value=self.settings["address"])
        self.address_box = ttk.Combobox(row, textvariable=self.address, width=17, font=FONT)
        self.address_box.pack(side="left")
        tk.Label(row, text="   Visitors at most", bg=BG, fg=DIM, font=SMALL).pack(side="left")
        self.max_guests = tk.StringVar(value=str(self.settings["max_guests"]))
        ttk.Spinbox(row, from_=1, to=co.MAX_GUESTS, textvariable=self.max_guests, width=3, font=FONT, state="readonly").pack(side="left", padx=6)
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 2))
        self.host_btn = self.button(row, "coop_host", self.start_hosting, "START HOSTING")
        self.stop_btn = self.button(row, "coop_stop", self.stop_hosting, "STOP HOSTING")
        self.host_badge = tk.Frame(row, bg=BG)
        self.host_state = tk.Label(parent, text="", bg=BG, fg=DIM, font=SMALL, anchor="w", justify="left", wraplength=500)
        self.host_state.pack(fill="x")
        row = self.field(parent, "Invite code")
        self.invite_code = tk.StringVar()
        self.entry(row, self.invite_code, 30, readonly=True, fill=True)
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(4, 2))
        self.copy_btn = self.button(row, "coop_copy", self.copy_invite, "COPY INVITE")
        self.copy_btn.pack(side="left")
        self.code_btn = self.button(row, "coop_newcode", self.new_code, "NEW CODE")
        self.code_btn.pack(side="left", padx=8)
        tk.Label(parent, text="VISITORS IN YOUR WORLD", bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x", pady=(8, 0))
        self.guest_box = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.guest_box.pack(fill="x", pady=2)
        self.guest_pick = tk.StringVar()
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.send_btn = self.button(row, "coop_sendhome", self.send_home, "SEND HOME")
        self.send_btn.pack(side="left")
        self.bots_row = tk.Frame(parent, bg=BG)
        self.bots_value = tk.IntVar(value=0)
        tk.Label(self.bots_row, text="Bots online right now", bg=BG, fg=DIM, font=SMALL).pack(side="left")
        scale = tk.Scale(self.bots_row, from_=0, to=550, orient="horizontal", variable=self.bots_value, length=190, bg=BG, fg=FG,
                         troughcolor=PANEL2, highlightthickness=0, sliderrelief="flat", font=SMALL, resolution=10)
        scale.pack(side="left", padx=8)
        scale.bind("<ButtonRelease-1>", lambda e: self.set_bots())
        tk.Label(self.bots_row, text="lower it if the game stutters", bg=BG, fg=DIM, font=SMALL).pack(side="left")
        self.show_host()

    def build_visit(self, parent):
        self.heading(parent, "coop_head_visit", "VISIT A FRIEND")
        row = self.field(parent, "Character")
        self.character = tk.StringVar()
        self.character_box = ttk.Combobox(row, textvariable=self.character, width=22, font=FONT, state="readonly")
        self.character_box.pack(side="left")
        row = self.field(parent, "Invite code")
        self.their_code = tk.StringVar()
        self.entry(row, self.their_code, 30, fill=True)
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 2))
        self.button(row, "coop_test", self.test_connection, "TEST CONNECTION").pack(side="left")
        self.visit_btn = self.button(row, "coop_visit", self.visit, "VISIT")
        self.visit_btn.pack(side="left", padx=8)
        self.info = tk.Text(parent, height=5, width=62, bg=PANEL, fg=DIM, relief="flat", font=(_UI_FONT, 9), wrap="word",
                            highlightbackground=BORDER, highlightthickness=1, state="disabled")
        self.info.pack(fill="x", pady=4)
        tk.Label(parent, text="YOUR CHARACTERS IN OTHER WORLDS", bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
        self.away_box = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.away_box.pack(fill="x", pady=2)
        self.away_pick = tk.StringVar()
        self.away_buttons = tk.Frame(parent, bg=BG)
        self.away_buttons.pack(fill="x", pady=(4, 0))
        if not getattr(self.app, "new_ui", False):      # the newer look has these on SYSTEM > Characters (launcher_pages.py)
            tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(10, 6))
            row = tk.Frame(parent, bg=BG)
            row.pack(fill="x")
            self.button(row, "coop_save", self.save_character, "SAVE CHARACTER").pack(side="left")
            self.button(row, "coop_load", self.restore_character, "RESTORE").pack(side="left", padx=8)
            tk.Label(parent, text="A backup file of the character picked above, to restore in this same world.", bg=BG, fg=DIM,
                     font=SMALL, anchor="w").pack(fill="x", pady=(2, 0))
            self.build_carry(parent)
        self.show_away()

    # ----- one player, several PCs (2026-11-20): the character and its squad move, each PC keeps its own world -----
    def build_carry(self, parent):
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(10, 6))
        tk.Label(parent, text="PLAY ON ANOTHER PC", bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x")
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        self.button(row, "coop_carry_save", self.carry_save, "SAVE FOR ANOTHER PC").pack(side="left")
        self.button(row, "coop_carry_load", self.carry_load, "LOAD FROM ANOTHER PC").pack(side="left", padx=8)
        tk.Label(parent, text="Takes the character picked above and its squad mates to your other PC. Each PC keeps its own world "
                 "(settings, bot players, linkshells).", bg=BG, fg=DIM, font=SMALL, anchor="w", justify="left",
                 wraplength=520).pack(fill="x", pady=(2, 0))
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.carry_auto = tk.BooleanVar(value=bool(self.cfg.get("char_sync")))
        tk.Checkbutton(row, text="Do it automatically: load on PLAY, save on STOP", variable=self.carry_auto, command=self.carry_toggle,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG, font=FONT).pack(side="left")
        self.button(row, "coop_carry_folder", self.carry_pick_folder, "FOLDER...").pack(side="left", padx=8)
        self.carry_folder_text = tk.StringVar()
        tk.Label(parent, textvariable=self.carry_folder_text, bg=BG, fg=DIM, font=SMALL, anchor="w", justify="left",
                 wraplength=520).pack(fill="x")
        self.carry_show_folder()

    def carry_set(self, key, value):
        self.cfg[key] = value
        path = os.path.join(self.kit, "config.json")
        with open(path, encoding="utf-8-sig") as handle:
            saved = json.load(handle)
        saved[key] = value
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(saved, handle, indent=2)

    def carry_show_folder(self):
        folder = self.cfg.get("char_sync_dir") or ""
        self.carry_folder_text.set(("Folder: " + folder) if folder else
                                   "Off. To use it, pick a folder that both PCs share (OneDrive, Dropbox, Google Drive...).")

    def carry_pick_folder(self):
        folder = filedialog.askdirectory(title="A folder that both PCs share (OneDrive, Dropbox, Google Drive...)", parent=self)
        if not folder:
            return False
        self.carry_set("char_sync_dir", os.path.normpath(folder))
        self.carry_show_folder()
        return True

    def carry_toggle(self):
        on = bool(self.carry_auto.get())
        if on and not self.cfg.get("char_sync_dir") and not self.carry_pick_folder():
            self.carry_auto.set(False)
            return
        if on and not messagebox.askyesno(
                "Automatic", "From now on, on this PC:\n\n  - STOP saves your characters and their squads to the folder\n"
                "  - PLAY loads a character that your other PC saved there (a backup of the copy here is kept first)\n\n"
                "Switch it on on the other PC too, with the same folder, and let the folder finish syncing before you press PLAY "
                "there. The newest save wins: play on one PC at a time.\n\nSwitch it on?", parent=self):
            self.carry_auto.set(False)
            return
        self.carry_set("char_sync", on)
        self.note("Automatic character folder: " + ("on." if on else "off."))

    def carry_save(self):
        charid = self.picked_character()
        if charid is None:
            messagebox.showinfo("Save for another PC", "Pick a character first (Character, above).", parent=self)
            return
        name = self.character.get()
        path = filedialog.asksaveasfilename(title="Save " + name + " for another PC", defaultextension=pp.CARRY_EXT,
                                            filetypes=[("XI: Forever Offline character", "*" + pp.CARRY_EXT)],
                                            initialdir=self.cfg.get("char_sync_dir") or None, initialfile=name + pp.CARRY_EXT, parent=self)
        if not path:
            return

        def work():
            conn = self.connect()
            try:
                data = pp.save_carry(conn, charid, stopped=not getattr(self.app, "running", False))
            finally:
                conn.close()
            with open(path, "wb") as handle:
                handle.write(data)
            return path

        self.job(work, lambda saved: self.note(f"Saved {name} and its squad to {saved}. Load that file on your other PC."), f"Saving {name}...")

    def carry_load(self):
        path = filedialog.askopenfilename(title="A file made with SAVE FOR ANOTHER PC",
                                          filetypes=[("XI: Forever Offline character", "*" + pp.CARRY_EXT)],
                                          initialdir=self.cfg.get("char_sync_dir") or None, parent=self)
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                data = handle.read()
            passport = pp.read_carry(data)
        except (OSError, pp.PassportError) as e:
            messagebox.showwarning("Load from another PC", str(e), parent=self)
            return
        if getattr(self.app, "running", False):
            messagebox.showinfo("Load from another PC", "Press STOP first: a character is loaded while the game is closed.", parent=self)
            return
        look, name = passport.get("summary", {}), passport["name"]
        mates = len(look.get("squad") or [])
        here = any(n == name for _c, n in self.characters)
        text = (f"{name} (level {look.get('level', '?')} {look.get('job', '')}, {look.get('gil', 0):,} gil, {mates} squad mate(s)), saved "
                f"{when(passport.get('made'))}.\n\n")
        text += (f"{name} is already in this world: the copy here is REPLACED by the one in the file (a backup of it is kept in the "
                 "backups folder)." if here else f"{name} joins your account in this world as a new character.")
        if not messagebox.askyesno("Load from another PC", text + "\n\nLoad it?", icon="warning" if here else "question", parent=self):
            return

        def work():
            conn = self.connect()
            try:
                return pp.load_carry(conn, data, backup_dir=os.path.join(self.kit, "backups"), stopped=True)
            finally:
                conn.close()

        def done(result):
            extra = " ".join(result.get("notes") or [])
            self.note(f"{name} was loaded" + (" as a new character." if result["new"] else "; the old copy is in backups.") + (" " + extra if extra else ""))
            self.refresh()

        self.job(work, done, f"Loading {name}...")

    def say_info(self, text):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("end", text)
        self.info.configure(state="disabled")

    # ----- turning it on and off -----
    def turn_on(self):
        if not messagebox.askyesno("Turn co-op on", "Co-op is an early test version.\n\nA copy of your whole database is saved "
                                   "first (backups folder), and a copy of each character before every trip.\n\nTurn it on?", parent=self):
            return

        def work():
            if not self.settings.get("backup_done"):
                co.full_backup(self.cfg, self.kit, log=self.log)
                self.settings["backup_done"] = True
            conn = self.connect()
            try:
                pp.ensure_tables(conn)
            finally:
                conn.close()
            self.settings["enabled"] = True
            co.save_settings(self.kit, self.settings)
            return self.load_everything()

        def done(result):
            self.loaded = False
            self.build()
            self.show_everything(result)

        self.job(work, done, "Saving a copy of your database first (this can take a minute)...")

    def turn_off(self):
        if self.settings.get("hosting") or self.away_rows or self.guest_rows:
            messagebox.showinfo("Co-op", "Stop hosting and bring your characters home first.", parent=self)
            return
        self.settings["enabled"] = False
        co.save_settings(self.kit, self.settings)
        self.stop_service()
        self.build()

    # ----- loading what the page shows -----
    def load_everything(self):
        conn = self.connect()
        try:
            data = {"world": pp.world_identity(conn, self.default_world_name(conn)), "characters": pp.home_characters(conn),
                    "away": pp.away_list(conn), "guests": pp.guest_list(conn)}
        finally:
            conn.close()
        data["addresses"] = co.local_addresses()
        data["rules"] = co.world_rules(self.kit)
        if self.settings["hosting"] or data["guests"]:
            try:
                self.start_service()
            except co.CoopError as e:
                self.log(str(e))
        return data

    def default_world_name(self, conn):
        try:
            names = pp.home_characters(conn)
            return f"{names[0][1]}'s world" if names else "A world"
        except Exception:
            return "A world"

    def show_everything(self, data):
        if not self.settings["enabled"] or not data:
            return
        if not self.loaded:
            self.world_name.set(data["world"]["name"])
            self.loaded = True
        self.addresses = data["addresses"]
        self.mode_changed(keep=True)
        self.characters = data["characters"]
        self.character_box.configure(values=[name for _id, name in self.characters])
        if self.characters and self.character.get() not in [name for _id, name in self.characters]:
            self.character.set(self.characters[0][1])
        elif not self.characters:
            self.character.set("")
        self.away_rows, self.guest_rows = data["away"], data["guests"]
        if data["rules"].get("bots"):
            self.bots_value.set(int(data["rules"].get("bots_online", 0)))
            self.bots_row.pack(fill="x", pady=(8, 0))
        self.show_host()
        self.show_guests()
        self.show_away()

    def refresh(self):
        if self.settings["enabled"]:
            self.job(self.load_everything, self.show_everything)

    # ----- hosting -----
    def mode_changed(self, keep=False):
        mode = self.mode.get()
        choices = [a["address"] for a in getattr(self, "addresses", []) if a["kind"] == mode]
        self.address_box.configure(values=choices)
        if not (keep and self.address.get() and co.address_kind(self.address.get()) == mode):
            self.address.set(choices[0] if choices else "")
        if mode == "tailscale" and not choices and not keep:      # just installed, or just logged in? look again
            self.refresh_addresses()

    def refresh_addresses(self):
        """Looks at this PC's addresses again and refills the list (Tailscale's appears once it is installed and logged in)."""
        if getattr(self, "refreshing", False) or not hasattr(self, "address_box"):
            return
        self.refreshing = True

        def work():
            try:
                return co.local_addresses()
            except Exception:
                return None

        def done(found):
            self.refreshing = False
            if found is not None and self.winfo_exists():
                self.addresses = found
                self.mode_changed(keep=True)

        self.job(work, done)

    def get_tailscale(self, parent=None, why=""):
        """GET TAILSCALE: downloads Tailscale's own installer, checks that Windows trusts it as Tailscale's, and starts
        it. When that cannot be done from here the download page opens instead."""
        if parent is None or not parent.winfo_exists():
            parent = self
        if co.tailscale_program() is not None:
            messagebox.showinfo("Tailscale", "Tailscale is already installed on this PC.\n\nOpen it from its icon near the clock and "
                                "log in. Once it has an address (it starts with 100.), pick 'Over the internet with Tailscale' "
                                "here and the address appears by itself.", parent=parent)
            self.refresh_addresses()
            return
        if not messagebox.askyesno("Get Tailscale", why + "This downloads Tailscale's installer from Tailscale's own site "
                                   "(pkgs.tailscale.com) and starts it.\n\nWindows may ask for permission. Click through the "
                                   "installer, then log in from the Tailscale icon near the clock: the account is free.\n\nGo on?",
                                   parent=parent):
            return

        def work():
            try:
                co.install_tailscale(self.kit, log=self.log)
            except co.CoopError as e:
                return str(e)
            return ""

        def done(problem):
            if problem:
                self.note(problem)
                messagebox.showwarning("Get Tailscale", problem + "\n\nThe download page opens instead: get Tailscale there.", parent=self)
                self.app.open_url(co.TAILSCALE_PAGE)
                return
            self.note("Tailscale's installer has started. Log in to Tailscale when it is installed, then come back here.")
            self.after(30000, self.refresh_addresses)

        self.job(work, done, "Downloading Tailscale's installer...")

    def needs_tailscale(self, invite):
        """An invite that goes through Tailscale, on a PC that has no Tailscale: offers to get it. True = stop here."""
        if co.address_kind(invite["address"]) != "tailscale" or co.tailscale_program() is not None:
            return False
        self.get_tailscale(why="Your friend's world is reached through Tailscale, and Tailscale is not installed on this PC yet.\n\n")
        return True

    def tailscale_help(self):
        win = tk.Toplevel(self)
        win.title("Playing over the internet with Tailscale")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        tk.Label(win, text=TAILSCALE_STEPS, bg=BG, fg=FG, font=FONT, wraplength=520, justify="left").pack(padx=18, pady=(16, 8))

        def close():
            win.destroy()
            self.refresh_addresses()                 # (Tailscale may have been installed and logged in meanwhile)

        win.protocol("WM_DELETE_WINDOW", close)
        self.button(win, "coop_tailscale", lambda: self.get_tailscale(win), "GET TAILSCALE").pack(pady=(2, 4))
        link = tk.Label(win, text="or get it yourself at tailscale.com/download", bg=BG, fg=ACCENT, cursor="hand2",
                        font=(_UI_FONT, 9, "underline"))
        link.pack()
        link.bind("<Button-1>", lambda e: self.app.open_url(TAILSCALE_URL))
        tk.Button(win, text="Close", command=close, bg=PANEL, fg=FG, relief="flat", padx=12).pack(pady=(10, 14))

    def start_service(self):
        """The small service friends' launchers talk to (also started when the launcher opens with visitors still here)."""
        if self.host is None:
            self.host = co.Host(self.cfg, self.kit, self.settings, log=self.log)
        if not self.host.running():
            try:
                self.host.start()
            except OSError as e:
                raise co.CoopError(f"Could not listen for friends on port {self.settings['port']} ({e}). Is another launcher open?")

    def stop_service(self):
        if self.host is not None:
            self.host.stop()

    def start_hosting(self):
        mode, address, name = self.mode.get(), self.address.get().strip(), self.world_name.get().strip()
        if co.address_kind(address) != mode:
            if mode == "tailscale" and co.tailscale_program() is None:
                self.get_tailscale(why="Tailscale is not installed on this PC yet. (How? next to the choice has all the steps.)\n\n")
                return
            hint = ("Tailscale is installed, but it has no address yet (it starts with 100.). Open Tailscale from its icon near "
                    "the clock and log in, then press START HOSTING again. How? has all the steps."
                    if mode == "tailscale" else "Pick this PC's address on your home network (it usually starts with 192.168.).")
            messagebox.showinfo("Start hosting", hint, parent=self)
            if mode == "tailscale":
                self.refresh_addresses()
            return
        if not co.is_local_address(address):
            messagebox.showinfo("Start hosting", f"{address} is not an address of this PC right now. Pick one from the list.", parent=self)
            return
        try:
            limit = max(1, min(co.MAX_GUESTS, int(self.max_guests.get())))
        except ValueError:
            limit = 3

        def work():
            conn = self.connect()
            try:
                pp.set_world_name(conn, name or "A world")
            finally:
                conn.close()
            self.settings.update({"hosting": True, "mode": mode, "address": address, "max_guests": limit})
            co.save_settings(self.kit, self.settings)
            self.start_service()
            self.host.closing = False
            self.closing_since = None
            ok, text = co.firewall_open(self.cfg["server_dir"], self.settings["port"], mode)
            return ok, text

        def done(result):
            ok, text = result
            self.show_host()
            extra = "" if ok else ("\n\n" + text + "\nYour friends may not get through until Windows' firewall lets the game "
                                   "server in (allow it when Windows asks, or run the launcher as administrator).")
            running = getattr(self.app, "running", False)
            messagebox.showinfo("Hosting is on", ("Press STOP, then PLAY: the world opens to your friends when it starts again."
                                                   if running else "Now press PLAY. The world opens to your friends when it has loaded.")
                                + "\n\nSend them the invite code (COPY INVITE)." + extra, parent=self)
            self.note(text)

        self.job(work, done, "Opening your world to friends...")

    def stop_hosting(self):
        if self.host is None:
            return
        waiting = [g for g in self.guest_rows if g["state"] == "active"]
        question = ("Stop hosting?" if not waiting else
                    f"{len(waiting)} visitor(s) are in your world. They are told to log out and, after a minute, their characters are "
                    "packed for the trip home (each one's launcher picks its character up; keep this launcher open until they have).\n\nStop hosting?")
        if not messagebox.askyesno("Stop hosting", question, parent=self):
            return
        self.host.closing = True
        self.closing_since = time.time()
        self.settings["hosting"] = False
        co.save_settings(self.kit, self.settings)
        if waiting:
            co.announce(self.cfg.get("server_dir"), "This world closes to visitors in one minute. Visitors: log out now, then press COME HOME in your launcher.")
        self.show_host()
        self.note("Hosting is off. Your world is private again from the next PLAY.")
        self.close_step()

    def close_step(self):
        """After Stop hosting: pack whoever is out of the game; when nobody is left, close the door completely."""
        if self.host is None or self.closing_since is None or self.closing_job:
            return
        if time.time() - self.closing_since < CLOSE_GRACE_SECONDS and any(g["state"] == "active" and g["online"] for g in self.guest_rows):
            return

        def work():
            self.host.send_everyone_home()
            left = self.host.waiting()
            if not left:
                self.stop_service()
                co.firewall_close()
            return left

        def done(left):
            self.closing_job = False
            if not left:
                self.closing_since = None
                self.note("Hosting is off and every visitor is home.")
            self.guest_rows = left
            self.show_guests()
            self.show_host()

        self.closing_job = True
        self.job(work, done)

    def show_host(self):
        if not self.settings["enabled"] or not hasattr(self, "host_btn"):
            return
        hosting = bool(self.settings["hosting"])
        for widget in (self.host_btn, self.stop_btn, self.host_badge):
            widget.pack_forget()
        (self.stop_btn if hosting else self.host_btn).pack(side="left")
        for child in self.host_badge.winfo_children():
            child.destroy()
        self.badge(self.host_badge, "open" if hosting else "closed", "OPEN" if hosting else "CLOSED").pack()
        self.host_badge.pack(side="left", padx=12)
        if hosting:
            running = getattr(self.app, "running", False)
            text = (f"Open to friends at {self.settings['address']}." if running else
                    f"Ready at {self.settings['address']}: the world opens when you press PLAY.")
            code = co.make_invite(self.settings["address"], self.settings["port"], self.settings["secret"], self.world_name.get() or "A world")
        elif self.closing_since:
            text, code = "Closing: waiting for your visitors to pick up their characters. Keep the launcher open.", ""
        else:
            text, code = "Your world is private. Start hosting to let friends in.", ""
        self.host_state.configure(text=text)
        self.invite_code.set(code)
        for widget in (self.copy_btn, self.code_btn):
            widget.configure(state="normal" if hosting else "disabled")

    def copy_invite(self):
        if self.invite_code.get():
            self.clipboard_clear()
            self.clipboard_append(self.invite_code.get())
            self.note("Invite code copied. Paste it to your friend (a Discord message is fine).")

    def new_code(self):
        if not messagebox.askyesno("New invite code", "The old code stops working for new visitors (friends already in your world "
                                   "are not affected).\n\nMake a new code?", parent=self):
            return
        self.settings["secret"] = os.urandom(16).hex()
        co.save_settings(self.kit, self.settings)
        self.show_host()

    def show_guests(self):
        if not hasattr(self, "guest_box"):
            return
        for child in self.guest_box.winfo_children():
            child.destroy()
        rows = [g for g in self.guest_rows if g["state"] in ("active", "left")]
        if not rows:
            tk.Label(self.guest_box, text="Nobody is visiting.", bg=PANEL, fg=DIM, font=SMALL, anchor="w").pack(fill="x", padx=8, pady=6)
        ids = [g["guest_id"] for g in rows]
        if self.guest_pick.get() not in ids:
            self.guest_pick.set(ids[0] if ids else "")
        for guest in rows:
            line = tk.Frame(self.guest_box, bg=PANEL)
            line.pack(fill="x", padx=4, pady=1)
            tk.Radiobutton(line, text=guest["name"], value=guest["guest_id"], variable=self.guest_pick, bg=PANEL, fg=FG, selectcolor=BG,
                           activebackground=PANEL, activeforeground=FG, font=BOLD, width=14, anchor="w", highlightthickness=0, bd=0).pack(side="left")
            kind = "leaving" if guest["state"] == "left" else ("playing" if guest["online"] else "resting")
            self.badge(line, kind, kind.upper()).pack(side="left", padx=4)
            detail = "its launcher has not picked it up yet" if guest["state"] == "left" else f"arrived {guest['arrived'][:16]}"
            tk.Label(line, text=detail, bg=PANEL, fg=DIM, font=SMALL).pack(side="left", padx=6)
        self.send_btn.configure(state="normal" if any(g["state"] == "active" for g in rows) else "disabled")

    def send_home(self):
        guest = next((g for g in self.guest_rows if g["guest_id"] == self.guest_pick.get() and g["state"] == "active"), None)
        if guest is None or self.host is None:
            return
        if guest["online"]:
            co.announce(self.cfg.get("server_dir"), f"{guest['name']}: the owner of this world asks you to head home. Log out, then press COME HOME in your launcher.")
            messagebox.showinfo("Send home", f"{guest['name']} is in the game and has been asked to log out. Press SEND HOME again once they have.", parent=self)
            return
        if not messagebox.askyesno("Send home", f"Pack {guest['name']} for the trip home?\n\nTheir launcher picks the character up the next "
                                   "time it is open. They keep everything they earned here.", parent=self):
            return
        self.job(lambda: self.host.send_home(guest["guest_id"]), lambda _r: self.refresh(), f"Packing {guest['name']}...")

    def set_bots(self):
        if getattr(self.app, "running", False):
            co.announce(self.cfg.get("server_dir"), str(int(self.bots_value.get())), kind="BOTS")
            self.note(f"Bots online right now: {int(self.bots_value.get())} (they log in or out over the next minutes; the CONFIG page's number applies again at the next PLAY).")
        else:
            self.note("That changes the running game only: press PLAY first.")

    # ----- called by the launcher around PLAY -----
    def before_servers(self, say):
        """Just before the game servers start: point the world at the hosting address (or back). True = hosting."""
        if not self.settings["enabled"]:
            return False
        return co.prepare_world(self.cfg, self.kit, self.settings, log=say)

    def after_servers(self, say):
        """The world has loaded while hosting: make sure the door is open."""
        try:
            self.start_service()
        except co.CoopError as e:
            say(f"Co-op: {e}")
            return
        say(f"Co-op: your world is open to friends at {self.settings['address']}.")
        self.q.put((lambda _r: self.show_host(), None, None))

    def may_close(self):
        """Closing the launcher while visitors' characters are here: ask first."""
        if self.settings["enabled"] and any(g["state"] in ("active", "left") for g in self.guest_rows):
            return messagebox.askyesno("Visitors are still here", "Characters of your visitors are still in your world. They can only go "
                                       "home while this launcher is open (they stay safe here until then).\n\nClose anyway?", parent=self)
        return True

    def shutdown(self):
        self.stop_service()

    # ----- visiting -----
    def picked_character(self):
        return next((charid for charid, name in self.characters if name == self.character.get()), None)

    def read_code(self):
        return co.read_invite(self.their_code.get())

    def test_connection(self):
        try:
            invite = self.read_code()
        except co.CoopError as e:
            self.say_info(str(e))
            return

        if self.needs_tailscale(invite):
            return

        def work():
            results = co.test_connection(invite)
            if not results[0][1]:
                text = "No answer.\n" + results[0][2]
                if co.address_kind(invite["address"]) == "tailscale":
                    text += ("\n\nThis invite goes through Tailscale. Check that Tailscale is switched on on this PC (its icon "
                             "near the clock) and that your friend has shared their PC with you: How? on the left has the steps.")
                return text
            greeting = co.hello(invite)
            clash = co.versions_clash(co.versions(self.kit, self.cfg.get("server_dir")), greeting.get("versions"))
            lines = [f"{greeting['world']['name']} answered. Visitors: {greeting.get('guests', 0)} of {greeting.get('max_guests', '?')}."
                     + ("" if greeting.get("open") else " Not taking visitors right now."),
                     "Its rules: " + co.describe_rules(greeting.get("rules")) + "."]
            if clash:
                lines.append(clash)
            closed = [what for what, ok, _detail in results[1:] if not ok]
            if not closed:
                lines.append("Its game server is running and can be reached.")
            elif len(closed) == len(results) - 1:
                lines.append("Its game server is not running yet (your friend presses PLAY), or their firewall is in the way.")
            else:
                lines.append("Parts of its game server cannot be reached (" + ", ".join(closed) + "): their firewall is in the way.")
            return "\n".join(lines)

        self.job(work, self.say_info, "Looking for your friend's world...")

    def visit(self):
        charid = self.picked_character()
        if charid is None:
            messagebox.showinfo("Visit", "Pick the character that travels first.", parent=self)
            return
        try:
            invite = self.read_code()
        except co.CoopError as e:
            messagebox.showwarning("Visit", str(e), parent=self)
            return
        if self.needs_tailscale(invite):
            return
        name = self.character.get()
        if not messagebox.askyesno("Visit", f"{name} travels to {invite['world'] or 'your friend'}.\n\n"
                                   f"• {name} cannot be played at home until it comes back.\n"
                                   "• Everything earned there comes home with it.\n"
                                   "• Its squad mates travel with it; what they earn comes home too.\n"
                                   "• Linkshells stay home.\n"
                                   "• Auction listings and delivery-box items at home wait for the return.\n\nGo?", parent=self):
            return

        def done(host):
            self.refresh()
            messagebox.showinfo("Arrived", f"{name} is in {host['world'].get('name', 'the other world')}.\n\nPress PLAY THERE (or PLAY) to "
                                "start the game in your friend's world. The first time, the game loader may ask you to trust their server.", parent=self)

        self.job(lambda: co.start_visit(self.cfg, self.kit, invite, charid, log=self.log), done, f"{name} is packing...")

    def picked_away(self):
        return next((row for row in self.away_rows if str(row["charid"]) == self.away_pick.get()), None)

    @staticmethod
    def away_state(rows):
        """What decides which buttons a visit gets (not the times, which change all the while)."""
        return [(r["charid"], bool(r["host"].get("arrived")), bool(r["host"].get("unreachable_since")), co.can_take_back(r["host"])[0])
                for r in rows]

    def show_away(self, buttons=True):
        if not hasattr(self, "away_box"):
            return
        for child in self.away_box.winfo_children():
            child.destroy()
        if not self.away_rows:
            tk.Label(self.away_box, text="All your characters are home.", bg=PANEL, fg=DIM, font=SMALL, anchor="w").pack(fill="x", padx=8, pady=6)
            self.show_away_buttons()
            return
        ids = [str(row["charid"]) for row in self.away_rows]
        if self.away_pick.get() not in ids:
            self.away_pick.set(ids[0])
            buttons = True
        for row in self.away_rows:
            host = row["host"]
            line = tk.Frame(self.away_box, bg=PANEL)
            line.pack(fill="x", padx=4, pady=1)
            tk.Radiobutton(line, text=f"{row['name']}  \u2192  {host.get('world', {}).get('name', '?')}", value=str(row["charid"]),
                           variable=self.away_pick, command=self.show_away_buttons, bg=PANEL, fg=FG, selectcolor=BG, activebackground=PANEL,
                           activeforeground=FG, font=BOLD, anchor="w", highlightthickness=0, bd=0).pack(side="left")
            if not host.get("arrived"):
                kind, detail = "packed", "packed, but your friend's launcher has not answered yet"
            elif host.get("unreachable_since"):
                kind, detail = "unreachable", f"no answer since {when(host['unreachable_since'])}"
            else:
                kind = "visiting"
                detail = f"copy saved {when(host.get('checkpoint_at'))}" if host.get("checkpoint_at") else "no saved copy yet"
            self.badge(line, kind, kind.upper()).pack(side="left", padx=6)
            tk.Label(line, text=detail, bg=PANEL, fg=DIM, font=SMALL).pack(side="left", padx=4)
        if buttons:
            self.show_away_buttons()

    def show_away_buttons(self):
        for child in self.away_buttons.winfo_children():
            child.destroy()
        self.away_buttons.configure(height=1)       # (an emptied frame keeps its old height otherwise)
        row = self.picked_away()
        if row is None:
            return
        first = tk.Frame(self.away_buttons, bg=BG)
        first.pack(fill="x")
        second = tk.Frame(self.away_buttons, bg=BG)
        second.pack(fill="x", pady=(4, 0))
        if not row["host"].get("arrived"):
            self.button(first, "coop_retry", self.try_again, "TRY AGAIN").pack(side="left")
            self.button(first, "coop_cancel", self.cancel_visit, "CANCEL VISIT").pack(side="left", padx=8)
            return
        self.button(first, "coop_play", self.play_there, "PLAY THERE").pack(side="left")
        self.button(first, "coop_home", self.come_home, "COME HOME").pack(side="left", padx=8)
        allowed, why = co.can_take_back(row["host"])
        back = self.button(second, "coop_takeback", self.take_back, "TAKE BACK")
        back.pack(side="left")
        back.configure(state="normal" if allowed else "disabled")
        self.button(second, "coop_file", self.load_file, "LOAD FILE").pack(side="left", padx=8)
        if row["host"].get("unreachable_since"):
            tk.Label(self.away_buttons, text=why, bg=BG, fg=DIM, font=SMALL, anchor="w").pack(fill="x")

    def try_again(self):
        row = self.picked_away()
        if row:
            self.job(lambda: co.finish_arrival(self.cfg, self.kit, row["charid"], log=self.log), lambda _h: self.refresh(), "Trying again...")

    def cancel_visit(self):
        row = self.picked_away()
        if row and messagebox.askyesno("Cancel visit", f"{row['name']} is unpacked and stays home, exactly as it was.\n\nCancel the visit?", parent=self):
            self.job(lambda: co.cancel_visit(self.cfg, self.kit, row["charid"], log=self.log), lambda _r: self.refresh())

    def play_there(self):
        row = self.picked_away()
        if row is None:
            return
        if getattr(self.app, "running", False):
            messagebox.showinfo("Play there", "Press STOP first: your own world closes while you play in your friend's.", parent=self)
            return
        self.app.visit = row
        self.app.go("Play")
        self.app.start()

    def ask_play_there(self):
        """PLAY was pressed while a character is visiting: play there? Returns the visit, None (play at home) or 'cancel'."""
        rows = [row for row in self.away_rows if row["host"].get("arrived")] if self.settings["enabled"] else []
        if not rows:
            return None
        row = rows[-1]
        answer = messagebox.askyesnocancel("Where to?", f"{row['name']} is visiting {row['host'].get('world', {}).get('name') or 'a friend'}.\n\n"
                                           "Yes = play there\nNo = play in your own world (without that character)", parent=self.app)
        if answer is None:
            return "cancel"
        return row if answer else None

    def welcome_home(self, result):
        self.refresh()
        if result.get("already"):
            self.note(f"{result['name']} is already home.")
            return
        changes = result.get("changes") or {}
        lines = [f"{result['name']} is home."]
        if changes.get("levels"):
            lines.append(f"Level {changes.get('level')} {changes.get('job', '')} (+{changes['levels']}).")
        if changes.get("gil"):
            lines.append(f"Gil: {changes['gil']:+,}.")
        if changes.get("items"):
            lines.append(f"Item stacks: {changes['items']:+d}.")
        for mate in changes.get("mates") or []:                         # the squad mates that came back stronger, or new
            if mate.get("new"):
                lines.append(f"New squad mate: {mate['name']} ({mate.get('job', '')} {mate.get('level', 1)}).")
            else:
                lines.append(f"{mate['name']}: level {mate.get('level')} {mate.get('job', '')} (+{mate.get('gained', 0)}).")
        if result.get("from_checkpoint") is True:
            lines.append("Brought back from the last saved copy.")
        elif result.get("from_checkpoint") is False:
            lines.append("Brought back as it was before the visit (there was no saved copy).")
        lines.extend(result.get("notes") or [])
        messagebox.showinfo("Welcome home", "\n".join(lines), parent=self)

    def come_home(self, force=False):
        row = self.picked_away()
        if row is None:
            return

        def work():
            try:
                return co.come_home(self.cfg, self.kit, row["charid"], force=force, log=self.log)
            except co.Refused as e:
                if e.code in ("online", "holdings"):
                    return e
                raise

        def done(result):
            if isinstance(result, co.Refused):
                if result.code == "online":
                    messagebox.showinfo("Come home", f"{row['name']} is still in the game there. Log out (or close the game), then press COME HOME again.", parent=self)
                else:
                    left = result.extra.get("holdings", {})
                    if messagebox.askyesno("Things left behind", f"{row['name']} still has {left.get('auctions', 0)} auction(s) running and "
                                           f"{left.get('delivery', 0)} item(s) in the delivery box in that world. They do not travel.\n\n"
                                           "Yes = come home without them\nNo = go back and collect them first", parent=self):
                        self.come_home(force=True)
                return
            self.welcome_home(result)

        self.job(work, done, f"Bringing {row['name']} home...")

    def take_back(self):
        row = self.picked_away()
        if row is None:
            return
        allowed, why = co.can_take_back(row["host"])
        if not allowed:
            messagebox.showinfo("Take back", why, parent=self)
            return
        saved = row["host"].get("checkpoint_at")
        what = (f"as it was when the last copy was saved ({when(saved)})" if saved else "as it was before the visit (no copy was saved during it)")
        if not messagebox.askyesno("Take back", f"{why}\n\n{row['name']} comes back {what}. Anything earned after that is lost, and the "
                                   "copy in your friend's world can never come home.\n\nTake it back?", icon="warning", parent=self):
            return
        self.job(lambda: co.take_back(self.cfg, self.kit, row["charid"], log=self.log), self.welcome_home, f"Taking {row['name']} back...")

    def load_file(self):
        path = filedialog.askopenfilename(title="A going-home file from your friend", filetypes=[("Character file", "*.zip")], parent=self)
        if path:
            self.job(lambda: co.load_return_file(self.cfg, self.kit, path), self.welcome_home, "Reading the file...")

    def save_character(self):
        charid = self.picked_character()
        if charid is None:
            messagebox.showinfo("Save character", "Pick a character first (Character, above).", parent=self)
            return
        name = self.character.get()
        path = filedialog.asksaveasfilename(title="Save a backup of " + name, defaultextension=".zip", filetypes=[("Character file", "*.zip")],
                                            initialfile=f"{name}-{time.strftime('%Y%m%d')}.zip", parent=self)
        if not path:
            return

        def work():
            conn = self.connect()
            try:
                data = pp.backup_character(conn, charid)
            finally:
                conn.close()
            with open(path, "wb") as handle:
                handle.write(data)
            return path

        self.job(work, lambda saved: self.note(f"Saved {name} to {saved}."), f"Saving {name}...")

    def restore_character(self):
        path = filedialog.askopenfilename(title="A backup file made with SAVE CHARACTER", filetypes=[("Character file", "*.zip")], parent=self)
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                data = handle.read()
            passport = pp.unpack(data)
        except (OSError, pp.PassportError) as e:
            messagebox.showwarning("Restore", str(e), parent=self)
            return
        look = passport.get("summary", {})
        if getattr(self.app, "running", False):
            messagebox.showinfo("Restore", "Press STOP first: a character is restored while the game is closed.", parent=self)
            return
        if not messagebox.askyesno("Restore", f"Put {passport['name']} back as saved in this file (level {look.get('level', '?')} "
                                   f"{look.get('job', '')}, {look.get('gil', 0):,} gil)?\n\nEverything the character did since then is "
                                   "replaced.", icon="warning", parent=self):
            return

        def work():
            conn = self.connect()
            try:
                return pp.restore_backup(conn, data)
            finally:
                conn.close()

        self.job(work, lambda _r: self.note(f"{passport['name']} was restored from the file."), "Restoring...")

    # ----- the regular look at visits and visitors -----
    def tick(self):
        if not self.winfo_exists():
            return
        now = time.time()
        if self.settings["enabled"]:
            if not self.keeping and now - self.last_keep >= KEEP_SECONDS and any(r["host"].get("arrived") for r in self.away_rows):
                self.keeping, self.last_keep = True, now
                rows = copy.deepcopy(self.away_rows)          # the background thread works on its own copy
                self.job(lambda: self.keep_all(rows), self.kept)
            if not self.listing and now - self.last_guests >= GUESTS_SECONDS and self.host is not None and (self.host.running() or self.guest_rows):
                self.listing, self.last_guests = True, now
                self.job(self.host.guests, self.listed)
        self.after(2000, self.tick)

    def keep_all(self, rows):
        events = []
        for row in rows:
            if row["host"].get("arrived"):
                events.append((row, co.keep_visit(self.cfg, self.kit, row, log=self.log)))
        conn = self.connect()
        try:
            return events, pp.away_list(conn), pp.home_characters(conn)
        finally:
            conn.close()

    def kept(self, result):
        self.keeping = False
        events, away, characters = result
        before = self.away_state(self.away_rows)
        self.away_rows, self.characters = away, characters
        self.character_box.configure(values=[name for _id, name in characters])
        self.show_away(buttons=before != self.away_state(away))
        for row, what in events:
            if what == "home":
                messagebox.showinfo("Welcome home", f"{row['name']} was sent home from {row['host'].get('world', {}).get('name') or 'your friend'} "
                                    "and is back with everything it earned.", parent=self)

    def listed(self, rows):
        self.listing = False
        changed = [(g["guest_id"], g["state"], g["online"]) for g in rows] != [(g["guest_id"], g["state"], g["online"]) for g in self.guest_rows]
        self.guest_rows = rows
        if changed:
            self.show_guests()
        if self.closing_since is not None:
            self.close_step()
