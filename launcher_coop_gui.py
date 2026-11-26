"""The launcher's CO-OP page (experimental): host your world for friends, or visit a friend's world.

All the work is in launcher_coop.py (talking to the other launcher, the PC's settings) and launcher_passport.py (the
character itself); this file is only the page. Anything slow (the database, the network) runs in a background thread and
its result comes back through a queue, so the window never freezes.
"""
import copy
import json
import os
import queue
import secrets
import threading
import time
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, simpledialog, ttk

import launcher_coop as co
import launcher_core as core
import launcher_passport as pp

try:                                 # banners on the OPEN WORLDS cards (Pillow ships with the launcher)
    from PIL import Image, ImageTk
except Exception:
    Image = ImageTk = None

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
WORLDS_SECONDS = 60                  # how often the listed open worlds are looked at, while this page is on the screen
WORLDS_SHOWN = 12                    # how many of them the page shows (2026-11-23: cards with banners)
CARD_BANNER = (320, 80)              # an OPEN WORLDS card's banner; The Hub's is HUB_BANNER
HUB_BANNER = (560, 140)
HOME_TRIES = 8                       # closing the game in another world: the character is asked home this many times...
HOME_WAIT = 8                        # ...this many seconds apart (the world may still see it logged in for a moment)
CLOSE_GRACE_SECONDS = 60             # Stop hosting: visitors get this long to log out before they are packed for home
TAILSCALE_URL = "https://tailscale.com/download"
INTRO = ("Co-op lets a friend bring their own character into your world, or you into theirs. Whatever is earned on a "
         "visit goes home with the visitor. It works on the same network (LAN or Wi-Fi, no internet needed) and over "
         "the internet with Tailscale. You can also open your world to anyone who has its link, and visit worlds "
         "that are open.\n\n"
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


def day(stamp):
    """'20 Feb 2027' for a time in seconds."""
    return time.strftime("%d %b %Y", time.localtime(stamp)).lstrip("0")


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
        self.place_rows = []                 # the places open worlds keep for this player's characters
        self.world_rows, self.world_states = [], {}      # the open worlds the project lists (The Hub first), and how each is doing
        self.last_worlds, self.looking = 0, False
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
                elif done is not None and not callable(done):
                    # (2026-11-24, Jker_s81: "'BooleanVar' object is not callable" every few seconds) a finished job
                    # whose callback is not a function: noted for the log once, never shown as an error box
                    if not getattr(self, "_odd_done_noted", False):
                        self._odd_done_noted = True
                        try:
                            import traceback
                            with open(os.path.join(self.kit, "logs", "coop-error.log"), "a", encoding="utf-8") as handle:
                                handle.write(time.strftime("%Y-%m-%d %H:%M:%S") + f"\nskipped a job callback that is not a function: "
                                             f"{type(done).__name__} {done!r} (result {type(result).__name__})\n"
                                             + "".join(traceback.format_stack(limit=6)) + "\n")
                        except Exception:
                            pass
                elif done is not None:
                    done(result)
        except queue.Empty:
            pass
        except Exception as e:
            self.fail(e)
        if self.winfo_exists():
            self.after(300, self.pump)

    def fail(self, error):
        self.keeping = self.listing = self.closing_job = self.looking = self.shorting = False
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
        tk.Label(self.body, textvariable=self.note_text, bg=BG, fg=GOLD, font=SMALL, anchor="w", justify="left",
                 wraplength=1140).pack(fill="x", padx=16, pady=(0, 2), side="bottom")
        # (2026-11-23, the user: "separate the hub, make the window a little bigger, a third section with the available
        #  worlds, their description and banner") one page that scrolls: The Hub, OPEN WORLDS, then your world and friends
        holder = tk.Frame(self.body, bg=BG)
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, bg=BG, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        page = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=page, anchor="nw")
        page.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        def wheel(event):
            if canvas.winfo_exists() and str(event.widget).startswith(str(canvas)):
                canvas.yview_scroll(-1 if (getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4) else 1, "units")
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(sequence, wheel, add="+")
        self.page_canvas = canvas

        row = tk.Frame(page, bg=BG)
        row.pack(fill="x", padx=16, pady=(6, 2))
        tk.Label(row, text="Your character", bg=BG, fg=FG, font=BOLD).pack(side="left")
        self.character = tk.StringVar()
        self.character_box = ttk.Combobox(row, textvariable=self.character, width=22, font=FONT, state="readonly")
        self.character_box.pack(side="left", padx=8)
        tk.Label(row, text="PLAY on a world takes this character there and starts the game. Close the game: it comes home "
                           "with everything it earned.", bg=BG, fg=DIM, font=SMALL).pack(side="left", padx=6)
        self.hub_area = tk.Frame(page, bg=BG)
        self.hub_area.pack(fill="x", padx=14, pady=(4, 2))
        self.cards_area = tk.Frame(page, bg=BG)
        self.cards_area.pack(fill="x", padx=14, pady=(4, 2))
        self.friends_area = tk.Frame(page, bg=BG)          # (2026-11-23) friends' worlds you went to: one click next time
        self.friends_area.pack(fill="x", padx=14, pady=(4, 2))
        self.friend_rows = co.friends(self.kit)
        self.world_rows = co.all_worlds(self.kit)
        self.cards = {}                  # link -> what its card shows (world_card), filled in the background
        self.card_images = {}
        tk.Frame(page, bg=BORDER, height=1).pack(fill="x", padx=14, pady=(10, 0))
        columns = tk.Frame(page, bg=BG)
        columns.pack(fill="both", expand=True, padx=8)
        left = tk.Frame(columns, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(6, 8))
        tk.Frame(columns, bg=BORDER, width=1).pack(side="left", fill="y", pady=8)
        right = tk.Frame(columns, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(8, 6))
        self.build_host(left)
        self.build_visit(right)
        self.show_worlds()

    def build_intro(self):
        box = tk.Frame(self.body, bg=BG)
        box.pack(expand=True)
        row = tk.Frame(box, bg=BG)
        row.pack(pady=(0, 8))
        tk.Label(row, text="Co-op", bg=BG, fg=FG, font=(_UI_FONT, 18, "bold")).pack(side="left")
        self.badge(row, "experimental", "EXPERIMENTAL").pack(side="left", padx=12)
        tk.Label(box, text=INTRO, bg=BG, fg=FG, font=FONT, wraplength=640, justify="left").pack(pady=(0, 16))
        official = [world["name"] for world in co.listed_worlds(self.kit) if world["official"]]
        if official:
            tk.Label(box, text=f"{official[0]}, the official world, is always online. Turn co-op on to visit it.", bg=BG, fg=GOLD,
                     font=BOLD, wraplength=640).pack(pady=(0, 14))
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
        self.who = tk.StringVar(value="open" if self.settings.get("open") else "friends")
        row = self.field(parent, "Who can come in")
        self.who_buttons = []
        for value, text in (("friends", "Friends (invite code)"), ("open", "Anyone (world link)")):
            choice = tk.Radiobutton(row, text=text, value=value, variable=self.who, command=self.who_changed, bg=BG, fg=FG,
                                    selectcolor=PANEL, activebackground=BG, activeforeground=FG, disabledforeground=DIM, font=FONT,
                                    highlightthickness=0, bd=0)
            choice.pack(side="left", padx=(0, 10))
            self.who_buttons.append(choice)
        self.mode = tk.StringVar(value=self.settings["mode"] if self.settings["mode"] in ("lan", "tailscale") else "lan")
        row = self.field(parent, "Friends reach me")
        self.reach_label = row.winfo_children()[0]      # ("Visitors reach me" for an open world: show_host)
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
        self.max_box = ttk.Spinbox(row, from_=1, to=co.MAX_OPEN_GUESTS if self.settings.get("open") else co.MAX_GUESTS,
                                   textvariable=self.max_guests, width=3, font=FONT, state="readonly")
        self.max_box.pack(side="left", padx=6)
        # (2026-11-23) an open world's card in everyone's OPEN WORLDS: its description, its banner, and whether it is listed
        self.card_box = tk.Frame(parent, bg=BG)
        row = self.field(self.card_box, "About my world")
        self.about = tk.StringVar(value=self.settings.get("about", ""))
        self.entry(row, self.about, 40, fill=True)
        self.about.trace_add("write", lambda *_a: self.about_changed())
        row = self.field(self.card_box, "Banner")
        self.banner_note = tk.Label(row, text="", bg=BG, fg=DIM, font=SMALL)
        tk.Button(row, text="Choose a picture...", command=self.choose_banner, bg=PANEL, fg=FG, relief="flat", padx=8,
                  font=SMALL).pack(side="left")
        tk.Button(row, text="Remove", command=lambda: self.choose_banner(remove=True), bg=PANEL, fg=DIM, relief="flat", padx=8,
                  font=SMALL).pack(side="left", padx=6)
        self.banner_note.pack(side="left", padx=4)
        self.list_mine = tk.BooleanVar(value=self.settings.get("listed", True))
        tk.Checkbutton(self.card_box, text="List my world in everyone's OPEN WORLDS (needs an address on the internet)",
                       variable=self.list_mine, command=self.listed_changed, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                       activeforeground=FG, font=SMALL, anchor="w", highlightthickness=0).pack(fill="x")
        self.show_banner_note()
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 2))
        self.host_btn = self.button(row, "coop_host", self.start_hosting, "START HOSTING")
        self.stop_btn = self.button(row, "coop_stop", self.stop_hosting, "STOP HOSTING")
        self.host_badge = tk.Frame(row, bg=BG)
        self.host_state = tk.Label(parent, text="", bg=BG, fg=DIM, font=SMALL, anchor="w", justify="left", wraplength=500)
        self.host_state.pack(fill="x")
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=3)
        self.code_label = tk.Label(row, text="Invite code", bg=BG, fg=DIM, font=SMALL, width=15, anchor="w")
        self.code_label.pack(side="left")
        self.invite_code = tk.StringVar()
        self.entry(row, self.invite_code, 30, readonly=True, fill=True)
        row = tk.Frame(parent, bg=BG)             # friends: COPY INVITE, NEW CODE.  open: COPY LINK, PASSWORD, KEPT PLACES
        row.pack(fill="x", pady=(4, 2))
        self.copy_btn = self.button(row, "coop_copy", self.copy_invite, "COPY INVITE")
        self.code_btn = self.button(row, "coop_newcode", self.new_code, "NEW CODE")
        self.long_btn = self.button(row, "coop_copylong", self.copy_long, "COPY LONG CODE")   # (shown with a short code)
        self.link_btn = self.button(row, "coop_copylink", self.copy_invite, "COPY LINK")
        self.pass_btn = self.button(row, "coop_password", self.set_password, "PASSWORD")
        self.places_btn = self.button(row, "coop_places", self.kept_places, "PLACES")
        tk.Label(parent, text="VISITORS IN YOUR WORLD", bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x", pady=(8, 0))
        self.guest_box = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.guest_box.pack(fill="x", pady=2)
        self.guest_pick = tk.StringVar()
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.send_btn = self.button(row, "coop_sendhome", self.send_home, "SEND HOME")
        self.send_btn.pack(side="left")
        self.kick_btn = self.button(row, "coop_kick", self.kick, "KICK")       # (shown for an open world: show_guests)
        self.ban_btn = self.button(row, "coop_ban", self.ban, "BAN")
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
        tk.Label(parent, text="A friend's invite code, or the link of a world that is not listed above.", bg=BG, fg=DIM,
                 font=SMALL, anchor="w").pack(fill="x")
        row = self.field(parent, "Code or link")
        self.their_code = tk.StringVar()
        self.entry(row, self.their_code, 30, fill=True)
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 2))
        self.button(row, "coop_test", self.test_connection, "TEST CONNECTION").pack(side="left")
        self.visit_btn = self.button(row, "coop_go", self.visit, "PLAY")
        self.visit_btn.pack(side="left", padx=8)
        self.info = tk.Text(parent, height=6, width=62, bg=PANEL, fg=DIM, relief="flat", font=(_UI_FONT, 9), wrap="word",
                            highlightbackground=BORDER, highlightthickness=1, state="disabled")
        self.info.pack(fill="x", pady=4)
        tk.Label(parent, text="YOUR CHARACTERS IN OTHER WORLDS", bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
        self.away_box = tk.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        self.away_box.pack(fill="x", pady=2)
        self.away_pick = tk.StringVar()
        self.away_buttons = tk.Frame(parent, bg=BG)
        self.away_buttons.pack(fill="x", pady=(4, 0))
        self.place_area = tk.Frame(parent, bg=BG)       # the places open worlds keep for your characters (show_places)
        self.place_area.pack(fill="x")
        self.place_pick = tk.StringVar()
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
        data["places"] = co.places(self.kit)
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
        self.place_rows = data.get("places") or []
        if data["rules"].get("bots"):
            self.bots_value.set(int(data["rules"].get("bots_online", 0)))
            self.bots_row.pack(fill="x", pady=(8, 0))
        self.show_host()
        self.show_guests()
        self.show_away()
        self.show_places()

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

    def host_object(self):
        if self.host is None:
            self.host = co.Host(self.cfg, self.kit, self.settings, log=self.log)
        return self.host

    def start_service(self):
        """The small service friends' launchers talk to (also started when the launcher opens with visitors still here)."""
        self.host_object()
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
        is_open = self.who.get() == "open"
        try:
            limit = max(1, min(co.MAX_OPEN_GUESTS if is_open else co.MAX_GUESTS, int(self.max_guests.get())))
        except ValueError:
            limit = 3
        if is_open and not messagebox.askyesno(
                "Open to everyone", f"Anyone who has your world's link can bring a character in, up to {limit} visitor(s) at a time. "
                "They do not need an invite code.\n\n"
                "\u2022 The link shows this PC's address on that network.\n"
                "\u2022 PASSWORD sets a password for your world.\n"
                "\u2022 You can KICK or BAN a visitor, and SEND HOME as before.\n"
                f"\u2022 A visitor's place here (name, linkshells, auction listings, delivery box) is kept for {pp.LOCKER_DAYS} days after "
                "each visit.\n\nOpen your world?", parent=self):
            return

        def work():
            conn = self.connect()
            try:
                pp.set_world_name(conn, name or "A world")
            finally:
                conn.close()
            self.settings.update({"hosting": True, "mode": mode, "address": address, "max_guests": limit, "open": is_open})
            co.save_settings(self.kit, self.settings)
            self.stop_service()                  # (the service decides at its start whether it also answers open visitors)
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
                                + ("\n\nGive out your world's link (COPY LINK)." if self.settings.get("open") else
                                   "\n\nSend them the invite code (COPY INVITE).") + extra, parent=self)
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
        self.drop_short_code()
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
        busy = hosting or bool(self.closing_since)
        is_open = bool(self.settings.get("open")) if busy else self.who.get() == "open"
        if busy:
            self.who.set("open" if is_open else "friends")
        for choice in self.who_buttons:           # who can come in is chosen before hosting starts
            choice.configure(state="disabled" if busy else "normal")
        self.max_box.configure(to=co.MAX_OPEN_GUESTS if is_open else co.MAX_GUESTS)
        if is_open:
            self.card_box.pack(fill="x", pady=(2, 2), after=self.max_box.master)
        else:
            self.card_box.pack_forget()
        for widget in (self.host_btn, self.stop_btn, self.host_badge):
            widget.pack_forget()
        (self.stop_btn if hosting else self.host_btn).pack(side="left")
        for child in self.host_badge.winfo_children():
            child.destroy()
        self.badge(self.host_badge, "open" if hosting else "closed", "OPEN" if hosting else "CLOSED").pack()
        self.host_badge.pack(side="left", padx=12)
        if hosting:
            running = getattr(self.app, "running", False)
            text = (f"Open to {'anyone with its link' if is_open else 'friends'} at {self.settings['address']}." if running else
                    f"Ready at {self.settings['address']}: the world opens when you press PLAY.")
            if is_open:
                mark = co.server_fingerprint(self.cfg.get("server_dir"))
                if mark:
                    code = co.make_link(self.settings["address"], self.settings["port"], mark, self.world_name.get() or "A world")
                    text += " Password: " + ("set." if self.settings.get("password") else "none.")
                else:
                    text, code = "Press PLAY once: your game server makes its key the first time it starts, and the world link needs it.", ""
            else:
                self.long_code = co.make_invite(self.settings["address"], self.settings["port"], self.settings["secret"],
                                                self.world_name.get() or "A world")
                code = self.short_for(self.long_code) or self.long_code
        elif self.closing_since:
            text, code = "Closing: waiting for your visitors to pick up their characters. Keep the launcher open.", ""
        elif is_open:
            text, code = "Your world is private. Start hosting to let in anyone who has its link.", ""
        else:
            text, code = "Your world is private. Start hosting to let friends in.", ""
        self.host_state.configure(text=text)
        self.invite_code.set(code)
        self.code_label.configure(text="World link" if is_open else "Invite code")
        self.reach_label.configure(text="Visitors reach me" if is_open else "Friends reach me")
        for widget in (self.copy_btn, self.code_btn, self.long_btn, self.link_btn, self.pass_btn, self.places_btn):
            widget.pack_forget()
        if is_open:
            self.link_btn.pack(side="left")
            self.pass_btn.pack(side="left", padx=8)
            self.places_btn.pack(side="left")
            self.link_btn.configure(state="normal" if code else "disabled")
        else:
            self.copy_btn.pack(side="left")
            self.code_btn.pack(side="left", padx=8)
            for widget in (self.copy_btn, self.code_btn):
                widget.configure(state="normal" if hosting else "disabled")
            if hosting and code and not code.startswith(co.PREFIX):
                self.long_btn.pack(side="left")

    # ----- short invite codes (2026-11-23): shown while The Hub keeps one; the long code otherwise -----
    def short_for(self, long_code):
        """The short code to show for this long code, or None (then the long code is shown). Starts registering one."""
        st = self.settings
        if st.get("short") and st.get("short_for") == long_code and time.time() - float(st.get("short_at") or 0) < 7 * 86400:
            if time.time() - float(st.get("short_at") or 0) >= co.SHORT_REFRESH:
                self.register_short(long_code)            # renew it now and then; the code stays the same
            return co.show_short(st["short"])
        self.register_short(long_code)
        return None

    def register_short(self, long_code):
        if getattr(self, "shorting", False) or time.time() - getattr(self, "short_tried", 0) < co.SHORT_RETRY:
            return
        st = self.settings
        old = (st.get("short"), st.get("short_drop")) if st.get("short") and st.get("short_for") != long_code else None
        same = st.get("short") and st.get("short_for") == long_code
        code = st["short"] if same else co.make_short()
        token = st["short_drop"] if same and st.get("short_drop") else secrets.token_hex(16)
        self.shorting, self.short_tried = True, time.time()

        def work():
            try:
                if old:
                    co.drop_short(*old)
                return co.register_short(code, long_code, token)
            except Exception:
                return False           # (no Hub: the long code stays on show)

        def done(ok):
            self.shorting = False
            if ok:
                self.settings.update({"short": code, "short_for": long_code, "short_drop": token, "short_at": int(time.time())})
            elif old or not same:
                self.settings.update({"short": "", "short_for": "", "short_drop": "", "short_at": 0})
            try:
                co.save_settings(self.kit, self.settings)
            except OSError:
                pass
            if ok and not same:
                self.show_host()
                self.note("Short invite code ready: " + co.show_short(code) + ". COPY INVITE copies it; COPY LONG CODE is for "
                          "friends with no internet (same home network).")

        self.job(work, done)

    def drop_short_code(self):
        st = self.settings
        if st.get("short"):
            code, token = st["short"], st.get("short_drop") or ""
            self.settings.update({"short": "", "short_for": "", "short_drop": "", "short_at": 0})
            self.short_tried = 0
            if token:
                threading.Thread(target=lambda: co.drop_short(code, token), daemon=True).start()

    def copy_long(self):
        code = getattr(self, "long_code", "")
        if code:
            self.clipboard_clear()
            self.clipboard_append(code)
            self.note("Long invite code copied. It works without The Hub, for example for a friend on your home network.")

    def copy_invite(self):
        if self.invite_code.get():
            self.clipboard_clear()
            self.clipboard_append(self.invite_code.get())
            self.note("World link copied. Anyone who has it can visit: post it where your players are."
                      if self.invite_code.get().startswith(co.LINK_PREFIX) else
                      "Invite code copied. Paste it to your friend (a Discord message is fine)."
                      + (" If they can't use it (no internet, or The Hub is down), COPY LONG CODE." if not
                         self.invite_code.get().startswith(co.PREFIX) else ""))

    def about_changed(self):
        self.settings["about"] = co.clean_about(self.about.get())
        try:
            co.save_settings(self.kit, self.settings)
        except OSError:
            pass

    def listed_changed(self):
        self.settings["listed"] = bool(self.list_mine.get())
        try:
            co.save_settings(self.kit, self.settings)
        except OSError:
            pass

    def show_banner_note(self):
        self.banner_note.configure(text="set (640 x 160)" if co.banner_hash(self.kit) else "none: the card shows your world's name")

    def choose_banner(self, remove=False):
        if remove:
            co.set_banner(self.kit, None)
        else:
            path = filedialog.askopenfilename(parent=self, title="A banner for your world (shown 640 x 160)",
                                              filetypes=[("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"), ("All files", "*.*")])
            if not path:
                return
            try:
                co.set_banner(self.kit, path)
            except Exception as e:
                messagebox.showwarning("Banner", f"That picture could not be used ({type(e).__name__}).", parent=self)
                return
        self.show_banner_note()
        self.note("Banner saved: players see it on your world's card." if not remove else "Banner removed.")

    def who_changed(self):
        """Friends or everyone: the visitor limit follows (6 between friends), and the page shows that kind's buttons."""
        try:
            if self.who.get() != "open" and int(self.max_guests.get()) > co.MAX_GUESTS:
                self.max_guests.set(str(co.MAX_GUESTS))
        except ValueError:
            self.max_guests.set("3")
        self.show_host()

    def set_password(self):
        """A password for an open world (only a scrambled form of it is kept). An empty answer removes it."""
        has = bool(self.settings.get("password"))
        answer = simpledialog.askstring(
            "World password", "Visitors must type this password to come in." + (" Your world has one now." if has else "") +
            "\n\nLeave it empty for no password.", show="*", parent=self)
        if answer is None:
            return
        self.settings["password"] = co.hash_password(answer.strip())
        co.save_settings(self.kit, self.settings)
        self.show_host()
        self.note("Your world asks visitors for the new password from now on." if self.settings["password"] else
                  "Your world has no password now: the link is enough.")

    def new_code(self):
        if not messagebox.askyesno("New invite code", "The old code stops working for new visitors (friends already in your world "
                                   "are not affected).\n\nMake a new code?", parent=self):
            return
        self.settings["secret"] = os.urandom(16).hex()
        self.drop_short_code()
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
            tk.Radiobutton(line, text=guest.get("local") or guest["name"], value=guest["guest_id"], variable=self.guest_pick, bg=PANEL, fg=FG, selectcolor=BG,
                           activebackground=PANEL, activeforeground=FG, font=BOLD, width=14, anchor="w", highlightthickness=0, bd=0).pack(side="left")
            kind = "leaving" if guest["state"] == "left" else ("playing" if guest["online"] else "resting")
            self.badge(line, kind, kind.upper()).pack(side="left", padx=4)
            detail = "its launcher has not picked it up yet" if guest["state"] == "left" else f"arrived {guest['arrived'][:16]}"
            tk.Label(line, text=detail, bg=PANEL, fg=DIM, font=SMALL).pack(side="left", padx=6)
        active = any(g["state"] == "active" for g in rows)
        self.send_btn.configure(state="normal" if active else "disabled")
        tools = bool(self.settings.get("open")) or any(g.get("kept") for g in rows)     # an open world's visitors
        for widget in (self.kick_btn, self.ban_btn):
            widget.pack_forget()
            if tools:
                widget.pack(side="left", padx=(8, 0))
                widget.configure(state="normal" if active else "disabled")

    def picked_guest(self):
        return next((g for g in self.guest_rows if g["guest_id"] == self.guest_pick.get() and g["state"] == "active"), None)

    def kick(self):
        guest = self.picked_guest()
        if guest is None:
            return
        name = guest.get("local") or guest["name"]
        if not guest["online"]:
            messagebox.showinfo("Kick", f"{name} is not in the game right now.", parent=self)
            return
        if not messagebox.askyesno("Kick", f"Log {name} out of your world?\n\nThey can come straight back. To keep them out, use BAN.", parent=self):
            return
        self.job(lambda: self.host_object().kick(guest["guest_id"]),
                 lambda ok: self.note(f"{name} is being logged out (it takes a few seconds)." if ok else f"{name} is not visiting any more."))

    def ban(self):
        guest = self.picked_guest()
        if guest is None:
            return
        name = guest.get("local") or guest["name"]
        if not messagebox.askyesno("Ban", f"Ban {name} from your world?\n\n"
                                   "\u2022 They are logged out, and their launcher cannot bring any character in again.\n"
                                   "\u2022 Their character is not harmed: their launcher can still bring it home.\n"
                                   "\u2022 PLACES lists your bans; you can lift one there.", icon="warning", parent=self):
            return
        address = messagebox.askyesno("Ban", "Also ban the internet address they came from?\n\nThat is stronger, but it can lock out "
                                      "other people in the same house, and addresses change.", default="no", parent=self)
        self.job(lambda: self.host_object().ban(guest["guest_id"], reason=name, with_address=address),
                 lambda who: (self.note(f"{who} is banned from your world." if who else
                                        f"{name} is not visiting any more, so nothing was changed. PLACES can ban a visitor who is home."),
                              self.refresh()))

    def kept_places(self):
        """A window with the places this world keeps for visitors who are home, and its bans."""
        host = self.host_object()
        win = tk.Toplevel(self)
        win.title("Kept places and bans")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        tk.Label(win, text="An open world keeps a visitor's place while they are home (their name here, linkshells, auction listings "
                 f"and delivery box) for {pp.LOCKER_DAYS} days after their last visit.", bg=BG, fg=FG, font=FONT, wraplength=560,
                 justify="left").pack(padx=18, pady=(16, 8), anchor="w")
        boxes, picks, state = [], [tk.StringVar(), tk.StringVar()], {"places": [], "bans": []}
        for title in ("PLACES KEPT", "BANS"):
            tk.Label(win, text=title, bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x", padx=18, pady=(6, 0))
            box = tk.Frame(win, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="x", padx=18, pady=2)
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=18, pady=(4, 4))
            boxes.append((box, row))

        def picked(which):
            key = picks[0 if which == "places" else 1].get()
            return next((item for item in state[which] if item["key"] == key), None)

        def load():
            self.job(lambda: (host.lockers(), host.bans()), fill)

        def forget():
            place = picked("places")
            if place and messagebox.askyesno("Forget this place", f"Clear the place kept for {place['local']}?\n\nIts copy here goes, with "
                                             "anything it left in your auction house or delivery box. They can still visit again and "
                                             "start fresh.", icon="warning", parent=win):
                self.job(lambda: host.forget(place["guest_id"]), lambda _ok: load())

        def ban_place():
            place = picked("places")
            if place and messagebox.askyesno("Ban", f"Ban {place['local']} from your world?\n\nTheir launcher cannot bring any character in "
                                             "again. The place stays until you forget it or its time runs out.", icon="warning", parent=win):
                self.job(lambda: host.ban(place["guest_id"], reason=place["local"]), lambda _who: load())

        def lift():
            ban = picked("bans")
            if ban:
                self.job(lambda: host.unban(ban["kind"], ban["value"]), lambda _r: load())

        forget_btn = self.button(boxes[0][1], "coop_forget", forget, "FORGET")
        forget_btn.pack(side="left")
        ban_btn = self.button(boxes[0][1], "coop_ban", ban_place, "BAN")
        ban_btn.pack(side="left", padx=8)
        lift_btn = self.button(boxes[1][1], "coop_unban", lift, "LIFT BAN")
        lift_btn.pack(side="left")
        tk.Button(win, text="Close", command=win.destroy, bg=PANEL, fg=FG, relief="flat", padx=12).pack(pady=(10, 14))

        def fill(data):
            if not win.winfo_exists():
                return
            state["places"] = [dict(p, key=p["guest_id"], text=p["local"],
                                    detail=f"last here {p['since'][:10]}, kept until {p['expires'][:10]}") for p in data[0]]
            state["bans"] = [dict(b, key=b["kind"] + "|" + b["value"], text=b["reason"] or "A visitor",
                                  detail=("their launcher" if b["kind"] == "key" else "the address " + b["value"]) + f", since {b['since'][:10]}")
                             for b in data[1]]
            for (box, _row), pick, which, nothing in ((boxes[0], picks[0], "places", "No places are kept right now."),
                                                      (boxes[1], picks[1], "bans", "Nobody is banned.")):
                for child in box.winfo_children():
                    child.destroy()
                items = state[which]
                if not items:
                    tk.Label(box, text=nothing, bg=PANEL, fg=DIM, font=SMALL, anchor="w").pack(fill="x", padx=8, pady=6)
                if pick.get() not in [item["key"] for item in items]:
                    pick.set(items[0]["key"] if items else "")
                for item in items[:12]:
                    line = tk.Frame(box, bg=PANEL)
                    line.pack(fill="x", padx=4, pady=1)
                    tk.Radiobutton(line, text=item["text"], value=item["key"], variable=pick, bg=PANEL, fg=FG, selectcolor=BG,
                                   activebackground=PANEL, activeforeground=FG, font=BOLD, width=16, anchor="w", highlightthickness=0,
                                   bd=0).pack(side="left")
                    tk.Label(line, text=item["detail"], bg=PANEL, fg=DIM, font=SMALL).pack(side="left", padx=6)
                if len(items) > 12:
                    tk.Label(box, text=f"... and {len(items) - 12} more", bg=PANEL, fg=DIM, font=SMALL, anchor="w").pack(fill="x", padx=8)
            for widget in (forget_btn, ban_btn):
                widget.configure(state="normal" if state["places"] else "disabled")
            lift_btn.configure(state="normal" if state["bans"] else "disabled")

        fill(([], []))
        load()
        return win

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
        say(f"Co-op: your world is open to {'anyone with its link' if self.settings.get('open') else 'friends'} at {self.settings['address']}.")
        self.q.put((lambda _r: self.show_host(), None, None))

    def may_close(self):
        """Closing the launcher while visitors' characters are here: ask first."""
        if self.settings["enabled"] and any(g["state"] in ("active", "left") for g in self.guest_rows):
            return messagebox.askyesno("Visitors are still here", "Characters of your visitors are still in your world. They can only go "
                                       "home while this launcher is open (they stay safe here until then).\n\nClose anyway?", parent=self)
        return True

    def shutdown(self):
        self.stop_service()

    # ----- the open worlds the project lists (2026-11-23): The Hub first; picking one fills in its link -----
    def show_worlds(self):
        """The Hub on its own, then a card for every other open world: its banner, description, who is there, PLAY."""
        if not hasattr(self, "hub_area") or not self.hub_area.winfo_exists():
            return
        self.show_friends()
        for area in (self.hub_area, self.cards_area):
            for child in area.winfo_children():
                child.destroy()
        mine = co.server_fingerprint(self.cfg.get("server_dir"))          # your own open world is not a place to visit
        rows = [w for w in self.world_rows if not mine or w["invite"].get("pin") != mine]
        official = [w for w in rows if w["official"]][:1]
        others = [w for w in rows if w not in official][:WORLDS_SHOWN]
        for world in official:
            self.world_card_widget(self.hub_area, world, big=True)
        head = tk.Frame(self.cards_area, bg=BG)
        head.pack(fill="x", pady=(8, 2))
        tk.Label(head, text="OPEN WORLDS", bg=BG, fg=GOLD, font=(_UI_FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text="worlds other players opened to everyone. Their rules, your character.", bg=BG, fg=DIM,
                 font=SMALL).pack(side="left", padx=8)
        if not others:
            tk.Label(self.cards_area, text="No other open worlds right now. Yours can be the first: HOST MY WORLD below, "
                     "Anyone (world link), and tick \"List my world\".", bg=BG, fg=DIM, font=SMALL, anchor="w").pack(fill="x", pady=4)
            return
        grid = tk.Frame(self.cards_area, bg=BG)
        grid.pack(fill="x")
        for i, world in enumerate(others):
            cell = tk.Frame(grid, bg=BG)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 6, 0), pady=3)
            self.world_card_widget(cell, world, big=False)
        grid.columnconfigure(0, weight=1, uniform="cards")
        grid.columnconfigure(1, weight=1, uniform="cards")

    def friend_world(self, row):
        return {"name": row["name"], "about": "", "official": False, "link": row["code"], "invite": row["invite"], "friend": True}

    def show_friends(self):
        area = self.friends_area
        for child in area.winfo_children():
            child.destroy()
        area.configure(height=1)
        head = tk.Frame(area, bg=BG)
        head.pack(fill="x", pady=(8, 2))
        tk.Label(head, text="YOUR FRIENDS' WORLDS", bg=BG, fg=GOLD, font=(_UI_FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text="same network, Tailscale or the internet: once you have been there, it is one click.", bg=BG,
                 fg=DIM, font=SMALL).pack(side="left", padx=8)
        if not self.friend_rows:
            tk.Label(area, text="None yet. Paste a friend's invite code under VISIT A FRIEND below and press PLAY: next time "
                     "their world is right here.", bg=BG, fg=DIM, font=SMALL, anchor="w").pack(fill="x", pady=4)
            return
        grid = tk.Frame(area, bg=BG)
        grid.pack(fill="x")
        for i, row in enumerate(self.friend_rows):
            cell = tk.Frame(grid, bg=BG)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0 if i % 2 == 0 else 6, 0), pady=3)
            self.world_card_widget(cell, self.friend_world(row), big=False)
        grid.columnconfigure(0, weight=1, uniform="friends")
        grid.columnconfigure(1, weight=1, uniform="friends")

    def forget_friend(self, world):
        if messagebox.askyesno("Forget", f"Take {world['name']} off YOUR FRIENDS' WORLDS?\n\nYou can always paste the invite code again.",
                               parent=self):
            co.forget_friend(self.kit, world["link"])
            self.friend_rows = co.friends(self.kit)
            self.show_friends()

    def banner_image(self, world, card, big):
        """The card's banner as a Tk picture: the world's own (from world_card), The Hub's from the kit, or None."""
        size = HUB_BANNER if big else CARD_BANNER
        path = card.get("banner")
        if not path and world["official"]:
            path = os.path.join(self.kit, "assets", "worlds", "hub_banner.jpg")
        if not path or Image is None or not os.path.exists(path):
            return None
        key = (path, size)
        if key not in self.card_images:
            try:
                with Image.open(path) as picture:
                    picture = picture.convert("RGB")
                    picture.thumbnail(size)
                    self.card_images[key] = ImageTk.PhotoImage(picture)
            except Exception:
                self.card_images[key] = None
        return self.card_images[key]

    def world_card_widget(self, parent, world, big):
        card = self.cards.get(world["link"]) or {"state": "looking...", "up": None, "name": world["name"], "about": world["about"],
                                                  "banner": None, "password": False}
        box = tk.Frame(parent, bg=PANEL, highlightbackground=GOLD if big else BORDER, highlightthickness=1)
        box.pack(fill="x")
        image = self.banner_image(world, card, big)
        if image is not None:
            tk.Label(box, image=image, bg=PANEL, bd=0).pack(side="left", padx=6, pady=6)
        else:
            w, h = HUB_BANNER if big else CARD_BANNER
            plate = tk.Canvas(box, width=w, height=h, bg=PANEL2, highlightthickness=1, highlightbackground=BORDER, bd=0)
            plate.create_text(w // 2, h // 2, text=card["name"], fill=GOLD, font=(_UI_FONT, 16 if big else 12, "bold"), width=w - 20)
            plate.pack(side="left", padx=6, pady=6)
        text = tk.Frame(box, bg=PANEL)
        text.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=6)
        line = tk.Frame(text, bg=PANEL)
        line.pack(fill="x")
        tk.Label(line, text=card["name"], bg=PANEL, fg=FG, font=(_UI_FONT, 14 if big else 11, "bold"), anchor="w").pack(side="left")
        if world["official"]:
            tk.Label(line, text=" OFFICIAL ", bg=PANEL2, fg=GOLD, font=(_UI_FONT, 8, "bold")).pack(side="left", padx=6)
        if card.get("password"):
            tk.Label(line, text=" PASSWORD ", bg=PANEL2, fg=DIM, font=(_UI_FONT, 8, "bold")).pack(side="left", padx=2)
        if card["about"]:
            tk.Label(text, text=card["about"], bg=PANEL, fg=DIM, font=SMALL, anchor="w", justify="left",
                     wraplength=420 if big else 200).pack(fill="x", pady=(2, 0))
        there = self.visiting(world)
        state = f"{there['name']} is there" if there else card["state"]
        colour = GREEN if (there or card.get("up")) else (DIM if card.get("up") is None else RED)
        tk.Label(text, text="\u25cf " + state, bg=PANEL, fg=colour, font=SMALL, anchor="w").pack(fill="x", pady=(4, 0))
        go = tk.Button(text, text="PLAY" if not there else f"PLAY ({there['name']})", command=lambda w=world: self.play_world(w),
                       bg=GREEN if big else ACCENT, fg="#06121a", activebackground=GOLD, relief="flat", font=(_UI_FONT, 12 if big else 10, "bold"),
                       padx=18 if big else 12, pady=4 if big else 2, cursor="hand2")
        go.pack(side="left", anchor="w", pady=(6, 0)) if world.get("friend") else go.pack(anchor="w", pady=(6, 0))
        if card.get("up") is False and not there:
            go.configure(state="disabled")
        if world.get("friend"):
            forget = tk.Label(text, text="forget", bg=PANEL, fg=DIM, font=(_UI_FONT, 8, "underline"), cursor="hand2")
            forget.pack(side="left", padx=10, pady=(6, 0))
            forget.bind("<Button-1>", lambda e, w=world: self.forget_friend(w))

    def visiting(self, world):
        """The character of yours that is in that world right now (arrived), or None."""
        invite = world["invite"]
        for row in self.away_rows:
            host = row["host"]
            if not host.get("arrived"):
                continue
            if invite.get("pin") and host.get("pin") == invite["pin"]:
                return row
            if not invite.get("pin") and not host.get("pin") and host.get("address") == invite["address"] \
                    and int(host.get("port") or 0) == int(invite["port"]):
                return row
        return None

    def look_at_worlds(self):
        """(in the background) The lists from the website and the hub when the copies here are old, and each world's card."""
        try:
            co.refresh_worlds(self.kit)
            co.refresh_directory(self.kit)
            rows = co.all_worlds(self.kit)
            official = [w for w in rows if w["official"]][:1]
            shown = official + [w for w in rows if w not in official][:WORLDS_SHOWN]
            shown += [self.friend_world(row) for row in co.friends(self.kit)]
            return rows, {world["link"]: co.world_card(self.kit, world) for world in shown}
        except Exception:
            return None

    def looked(self, result):
        self.looking = False
        if result and self.settings["enabled"] and getattr(self, "hub_area", None) is not None and self.hub_area.winfo_exists():
            self.world_rows, self.cards = result
            self.friend_rows = co.friends(self.kit)
            self.show_worlds()

    # ----- (2026-11-23) one button: PLAY on a world takes the character there and starts the game -----
    def play_world(self, world):
        if getattr(self.app, "running", False):
            messagebox.showinfo("Play", "Press STOP first: your own world closes while you play in another one.", parent=self)
            return
        there = self.visiting(world)
        if there is not None:
            return self.go_play(there)
        charid = self.picked_character()
        if charid is None:
            messagebox.showinfo("Play", "Pick your character at the top of the page first.", parent=self)
            return
        busy = next((row for row in self.away_rows if row["charid"] == charid), None)
        if busy is not None:
            where = busy["host"].get("world", {}).get("name") or "another world"
            messagebox.showinfo("Play", f"{busy['name']} is in {where} right now. Pick another character, or play there first "
                                "(closing the game brings it home).", parent=self)
            return
        name = self.character.get()
        invite = world["invite"]
        if not invite.get("open"):                 # a friend's world (invite code): LAN, Tailscale or the internet
            if self.needs_tailscale(invite):
                return
            code = world["link"]
            self.note(f"{name} is travelling to {world['name']}. The game starts as soon as it arrives.")

            def arrived(charid_, code=code, world_name=world["name"]):
                co.remember_friend(self.kit, code, world_name)
                self.friend_rows = co.friends(self.kit)
                self.play_arrived(charid_)
            self.arrive(lambda: co.start_visit(self.cfg, self.kit, invite, charid, log=self.log), charid, name, False, then=arrived)
            return
        self.job(lambda: co.hello(invite), lambda greeting: self.play_open(invite, charid, name, greeting),
                 f"Looking for {world['name']}...")

    def play_open(self, invite, charid, name, greeting):
        world = (greeting.get("world") or {}).get("name") or invite["world"] or "that world"
        if not greeting.get("open"):
            messagebox.showinfo("Play", f"{world} is not taking visitors right now.", parent=self)
            return
        password = None
        if greeting.get("password"):
            password = simpledialog.askstring("World password", f"{world} asks for a password.", show="*", parent=self)
            if not password:
                return
        self.note(f"{name} is travelling to {world}. The game starts as soon as it arrives.")
        self.arrive(lambda: co.start_visit(self.cfg, self.kit, invite, charid, log=self.log, password=password), charid, name, True,
                    then=self.play_arrived)

    def play_arrived(self, charid):
        """The character arrived: start the game there (the page's visit list is read again first)."""
        def done(away):
            self.away_rows = away
            self.show_away()
            self.show_worlds()
            row = next((r for r in away if r["charid"] == charid and r["host"].get("arrived")), None)
            if row is not None:
                self.go_play(row)

        def work():
            conn = self.connect()
            try:
                return pp.away_list(conn)
            finally:
                conn.close()
        self.job(work, done)

    def go_play(self, row):
        if getattr(self.app, "running", False):
            return
        self.app.visit = row
        self.app.go("Play")
        self.app.start()

    def home_after_game(self, visit):
        """Called by the launcher (in its worker thread) when the game closed after playing in another world: the
        character comes home by itself. Things left on that world's auction house or in its delivery box: the player is
        asked in the window (they can go back for them)."""
        try:
            result = co.come_home_after_game(self.cfg, self.kit, visit["charid"], log=self.log, tries=HOME_TRIES, wait=HOME_WAIT)
        except co.CoopError as e:
            text = (f"{visit['name']} stays in that world for now: {e} It comes home the next time the world answers "
                    "(or press COME HOME below).")
            self.q.put((lambda r: self.came_home(None, r), text, None))
            return
        self.q.put((lambda r, v=visit: self.came_home(v, r), result, None))

    def came_home(self, visit, result):
        """In the window: what home_after_game found."""
        if visit is None:
            self.note(str(result))
            self.refresh()
            return
        if result is None:
            self.note(f"{visit['name']} still looked logged in there. Press COME HOME below in a moment.")
            self.refresh()
            return
        if isinstance(result, co.Refused):
            if result.code == "holdings":
                left = result.extra.get("holdings", {})
                if messagebox.askyesno("Things left behind", f"{visit['name']} still has {left.get('auctions', 0)} auction(s) running and "
                                       f"{left.get('delivery', 0)} item(s) in the delivery box in that world. They do not travel.\n\n"
                                       "Yes = come home without them\nNo = stay there (press PLAY on that world to go back for them)",
                                       parent=self):
                    def work():
                        return co.come_home(self.cfg, self.kit, visit["charid"], force=True, log=self.log)
                    self.job(work, self.welcome_home, f"Bringing {visit['name']} home...")
                else:
                    self.refresh()
            else:
                self.note(f"{visit['name']} still looked logged in there. Press COME HOME below in a moment.")
                self.refresh()
            return
        self.welcome_home(result)

    # ----- visiting -----
    def picked_character(self):
        return next((charid for charid, name in self.characters if name == self.character.get()), None)

    def read_code(self):
        text = self.their_code.get()
        if co.short_code(text):                          # (2026-11-23) a short code: The Hub knows the long one
            text = co.resolve_short(text)
            self.their_code.set(text)                    # (so a friend's card keeps the long code, which needs no Hub)
        return co.read_code(text)                        # a friend's invite code, or the link of an open world

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
            clash = None if invite.get("open") else co.versions_clash(co.versions(self.kit, self.cfg.get("server_dir")), greeting.get("versions"))
            lines = [f"{greeting['world']['name']} answered. Visitors: {greeting.get('guests', 0)} of {greeting.get('max_guests', '?')}."
                     + ("" if greeting.get("open") else " Not taking visitors right now."),
                     "Its rules: " + co.describe_rules(greeting.get("rules")) + "."]
            if invite.get("open"):
                days = co._days(greeting.get("keep_days"))
                lines.append("It is open to everyone" + (" who knows its password." if greeting.get("password") else ".") +
                             (f" It keeps your place for {days} days after each visit." if days else ""))
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
        """PLAY under VISIT A FRIEND: the code or link in the box, then the same as PLAY on a card (2026-11-23)."""
        try:
            invite = self.read_code()
        except co.CoopError as e:
            messagebox.showwarning("Play", str(e), parent=self)
            return
        code = "".join(self.their_code.get().split())
        self.play_world({"name": invite.get("world") or "your friend's world", "about": "", "official": False, "link": code,
                         "invite": invite, "friend": not invite.get("open")})

    def visit_old(self):
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
        if invite.get("open"):                    # ask the world first: does it want a password, how long it keeps a place
            self.job(lambda: co.hello(invite), lambda greeting: self.visit_open(invite, charid, name, greeting), "Looking for that world...")
            return
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

    def visit_open(self, invite, charid, name, greeting):
        """The second half of VISIT for an open world, once it has answered."""
        world = (greeting.get("world") or {}).get("name") or invite["world"] or "that world"
        if not greeting.get("open"):
            messagebox.showinfo("Visit", f"{world} is not taking visitors right now.", parent=self)
            return
        password = None
        if greeting.get("password"):
            password = simpledialog.askstring("World password", f"{world} asks for a password.", show="*", parent=self)
            if not password:
                return
        days = co._days(greeting.get("keep_days"))
        if not messagebox.askyesno("Visit", f"{name} travels to {world}, a world that is open to everyone.\n\n"
                                   f"\u2022 {name} cannot be played at home until it comes back.\n"
                                   "\u2022 Everything earned there comes home with it (your launcher checks the character on the way in).\n"
                                   "\u2022 Its squad mates travel with it; what they earn comes home too.\n"
                                   "\u2022 Linkshells stay home.\n"
                                   + ("\u2022 Its bot players chat through Google's Gemma AI: what you say to them is sent to Google, "
                                      "which may use it to improve its products.\n" if (greeting.get("rules") or {}).get("ai_chat") == "google" else "")
                                   + (f"\u2022 That world keeps your place (your name there, its linkshells, your auction listings and "
                                      f"delivery box) for {days} days after each visit.\n" if days else "") +
                                   "\u2022 Auction listings and delivery-box items at home wait for the return.\n\nGo?", parent=self):
            return
        self.arrive(lambda: co.start_visit(self.cfg, self.kit, invite, charid, log=self.log, password=password), charid, name, True)

    def arrive(self, work, charid, name, is_open, then=None):
        """Runs the trip in the background. An open world may answer that the name is taken there or that the
        password is wrong: the character stays packed, the player is asked, and the arrival is tried again."""
        def guarded():
            try:
                return work()
            except co.Refused as e:
                if is_open and e.code in ("name", "password"):
                    return e
                raise

        def again(**more):
            self.arrive(lambda: co.finish_arrival(self.cfg, self.kit, charid, log=self.log, **more), charid, name, True, then=then)

        def done(result):
            self.refresh()
            if not isinstance(result, co.Refused) and then is not None:
                then(charid)
                return
            if not isinstance(result, co.Refused):
                there = result.get("world", {}).get("name", "the other world")
                known = f" as {result['local']}" if result.get("local") and result["local"] != name else ""
                messagebox.showinfo("Arrived", f"{name} is in {there}{known}.\n\nPress PLAY THERE (or PLAY) to start the game in that world. "
                                    "The first time, the game loader may ask you to trust its server.", parent=self)
                return
            packed = f"{name} is still packed: TRY AGAIN asks once more, CANCEL VISIT unpacks it."
            if result.code == "name":
                alias = simpledialog.askstring("Visiting name", f"{result}\n\nPick a name for {name} to use in that world (3 to 15 "
                                               "letters). At home it keeps its own name.", parent=self)
                alias = (alias or "").strip().capitalize()
                if alias and not pp.ALIAS.fullmatch(alias):
                    messagebox.showinfo("Visiting name", "A visiting name is 3 to 15 letters, like Hurami.", parent=self)
                    alias = ""
                if alias:
                    again(alias=alias)
                else:
                    self.note(packed)
            else:
                password = simpledialog.askstring("World password", "That is not this world's password. Try again:", show="*", parent=self)
                if password:
                    again(password=password)
                else:
                    self.note(packed)

        self.job(guarded, done, f"{name} is packing...")

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
                if host.get("local") and host["local"] != row["name"]:
                    detail = f"as {host['local']}, " + detail
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
            self.arrive(lambda: co.finish_arrival(self.cfg, self.kit, row["charid"], log=self.log), row["charid"], row["name"],
                        bool(row["host"].get("open")))

    # ----- the places open worlds keep for this player's characters -----
    def show_places(self):
        area = self.place_area
        for child in area.winfo_children():
            child.destroy()
        area.configure(height=1)                  # (an emptied frame keeps its old height otherwise)
        there = {(str(r["host"].get("world", {}).get("id")), r["charid"]) for r in self.away_rows}      # visiting right now
        rows = [p for p in self.place_rows if (p["world_id"], p["charid"]) not in there]
        if not rows:
            return
        tk.Label(area, text="YOUR PLACES IN OPEN WORLDS", bg=BG, fg=DIM, font=(_UI_FONT, 8, "bold"), anchor="w").pack(fill="x", pady=(8, 0))
        box = tk.Frame(area, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", pady=2)
        keys = [f"{p['world_id']}|{p['charid']}" for p in rows]
        if self.place_pick.get() not in keys:
            self.place_pick.set(keys[0])
        for place, key in list(zip(rows, keys))[:4]:
            line = tk.Frame(box, bg=PANEL)
            line.pack(fill="x", padx=4, pady=1)
            tk.Radiobutton(line, text=f"{place['local']}  in  {place['world'] or 'a world'}", value=key, variable=self.place_pick, bg=PANEL,
                           fg=FG, selectcolor=BG, activebackground=PANEL, activeforeground=FG, font=BOLD, anchor="w", highlightthickness=0,
                           bd=0).pack(side="left")
            tk.Label(line, text=f"kept until {day(place['until'])}", bg=PANEL, fg=DIM, font=SMALL).pack(side="left", padx=6)
        if len(rows) > 4:
            tk.Label(box, text=f"... and {len(rows) - 4} more", bg=PANEL, fg=DIM, font=SMALL, anchor="w").pack(fill="x", padx=8)
        row = tk.Frame(area, bg=BG)
        row.pack(fill="x", pady=(4, 0))
        self.button(row, "coop_again", self.visit_again, "VISIT AGAIN").pack(side="left")
        self.button(row, "coop_forget", self.forget_place, "FORGET").pack(side="left", padx=8)

    def picked_place(self):
        return next((p for p in self.place_rows if f"{p['world_id']}|{p['charid']}" == self.place_pick.get()), None)

    def visit_again(self):
        place = self.picked_place()
        if place is None:
            return
        if place["name"] not in [name for _id, name in self.characters]:
            messagebox.showinfo("Visit again", f"{place['name']} is not at home right now.", parent=self)
            return
        self.character.set(place["name"])
        self.their_code.set(co.place_link(place))
        self.visit()

    def forget_place(self):
        place = self.picked_place()
        if place and messagebox.askyesno("Forget", f"Take {place['local']}'s place in {place['world'] or 'that world'} off this list?\n\n"
                                         f"That world is not told: it clears the place by itself after {day(place['until'])} "
                                         "unless you visit again.", parent=self):
            co.forget_place(self.kit, place["world_id"], place["charid"])
            self.place_rows = co.places(self.kit)
            self.show_places()

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
            if not self.looking and now - self.last_worlds >= WORLDS_SECONDS and self.winfo_viewable():
                self.looking, self.last_worlds = True, now
                self.job(self.look_at_worlds, self.looked)
            if not self.listing and now - self.last_guests >= GUESTS_SECONDS and self.host is not None and (self.host.running() or self.guest_rows):
                self.listing, self.last_guests = True, now
                self.job(self.host.guests, self.listed)
            if (self.settings.get("hosting") and not self.settings.get("open") and getattr(self, "long_code", "")
                    and not self.settings.get("short") and not getattr(self, "shorting", False)
                    and now - getattr(self, "short_tried", 0) >= co.SHORT_RETRY):
                self.show_host()                          # (tries The Hub again; shows the short code once it answers)
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
        self.place_rows = co.places(self.kit)     # (a character that was sent home left a kept place behind)
        self.show_places()
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
