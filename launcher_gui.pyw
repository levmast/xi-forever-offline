"""XI: Forever Offline launcher - one window: Home (Play, Stop, Dualbox), squad, config, tools, settings."""
import ctypes, os, queue, random, subprocess, sys, threading, time, traceback
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))  # the kit folder
sys.path.insert(0, HERE)
import launcher_core as core
import launcher_gamepad as gp
import launcher_revamped as rv

IS_WINDOWS = os.name == "nt"
UI_FONT, MONO_FONT = core.ui_fonts()
linux = None
if not IS_WINDOWS:          # Linux / Steam Deck: the game runs through Proton (launcher_linux.py)
    import launcher_linux as linux

try:
    import launcher_squad as sq
except Exception:  # the Squad tab just won't appear
    sq = None

try:
    import launcher_rules as lr
except Exception:  # the rules editor just won't be offered
    lr = None

try:
    import launcher_thirdparty as tp
except Exception:  # the launcher still works without the Downloads page
    tp = None
try:
    import launcher_personality as lp
except Exception:  # the Squad tab still works, without the Personality page
    lp = None
try:
    import launcher_icons as itemicons
except Exception:  # the gear list still works, without pictures
    itemicons = None
try:
    import launcher_coop_gui as coopgui
except Exception:  # the launcher still works, without the Co-op page
    coopgui = None
try:
    import launcher_pages as newui     # the newer look: World, Rules, the eight-button bar ("classic_ui": true in config.json = the old one)
except Exception:  # the launcher still works, with the classic pages
    newui = None

LOGS = os.path.join(HERE, "logs")
KIT_REPO_NAME = "Hurami89/xi-forever-offline"
BG, PANEL, PANEL2, FG, DIM = "#0a1118", "#101c28", "#162634", "#e9f1f5", "#8aa0ad"
BORDER, GOLD = "#1d3445", "#e6be64"
GREEN, RED, GREY, ACCENT = "#3ecf6e", "#e5534b", "#44525d", "#35c4e0"
try:        # a limited-time look (a dated .json in assets\press) stands in for these colours while it is in date: launcher_theme.py
    import launcher_theme
    globals().update(launcher_theme.colours(globals()))
except Exception:
    pass
ASSETS = os.path.join(HERE, "assets")
VERSION = "1.3"


GALLERY_W, GALLERY_H, PICTURE_SECONDS = 920, 368, 6
LIST_HINT_MAIN = "Tick what you want loaded in your main game window. Changes apply the next time you press PLAY."
LIST_HINT_SECOND = "Tick what you want loaded in the second window (dualbox). Changes apply the next time you click DUALBOX."


# The page buttons along the bottom: (picture in assets\\ui, name, the pages it opens). A button for several pages opens the one you were last on
# in it. A page that is in none of them gets a MORE button, so nothing is ever unreachable.
NAV_BUTTONS = (("home", "HOME", ("Play",)), ("squad", "SQUADS", ("Squad",)), ("coop", "CO-OP", ("Co-op",)),
               ("config", "CONFIG", ("Rates", "Graphics", "Shaders", "Controller")),
               ("addons", "ADDONS", ("Addons", "Plugins", "Other")), ("settings", "SETTINGS", ("Settings",)))
PRESS_ANCHOR = 0.38      # press pictures are wider than the frame is tall: keep the part 38% of the way down (sky and skyline are above, people below)
PRESS_NOTE = ""
ONCE_TAG = "__once"      # a press picture with this in its name (xifo__once.png) is a one-time banner: see load_once
UNTIL_TAG = "__until-"   # ... and one with __until-2026-12-02 in its name is a limited-time banner: see press_names
THEME_TAG = "__theme-"   # ... and one with __theme-8bit in its name is a banner of that theme: see press_names


def fit_picture(img, width, height, anchor=0.5):
    """The picture scaled to cover width x height, then cropped. anchor is where the crop sits vertically: 0 = keep the top, 1 = the bottom."""
    from PIL import Image
    img = img.convert("RGB")
    scale = max(width / img.width, height / img.height)
    img = img.resize((max(width, round(img.width * scale)), max(height, round(img.height * scale))), Image.LANCZOS)
    left = (img.width - width) // 2
    top = round((img.height - height) * min(1.0, max(0.0, anchor)))
    return img.crop((left, top, left + width, top + height))


def press_anchor(name):
    """A picture called  castle__top.jpg  keeps its top, castle__bottom.jpg its bottom, castle__center.jpg its middle."""
    stem = os.path.splitext(name)[0].lower().replace(ONCE_TAG, "")
    cut = stem.find(UNTIL_TAG)
    if cut >= 0:
        stem = stem[:cut] + stem[cut + len(UNTIL_TAG) + 10:]
    cut = stem.find(THEME_TAG)
    if cut >= 0:
        end = stem.find("__", cut + len(THEME_TAG))
        stem = stem[:cut] + (stem[end:] if end >= 0 else "")
    for tag, value in (("__top", 0.0), ("__center", 0.5), ("__middle", 0.5), ("__bottom", 1.0)):
        if stem.endswith(tag):
            return value
    return PRESS_ANCHOR


def press_today():
    """Today on this PC, written 2026-12-02 (a function of its own so the tests can pick the day)."""
    return time.strftime("%Y-%m-%d")


def press_until(name):
    """The last day a limited-time picture is shown: the date after __until- in its name (party__until-2026-12-02.jpg). "" for a usual
    picture, "0" (always over) when the date cannot be read."""
    low = name.lower()
    cut = low.find(UNTIL_TAG)
    if cut < 0:
        return ""
    day = low[cut + len(UNTIL_TAG):cut + len(UNTIL_TAG) + 10]
    return day if len(day) == 10 and day[4] == "-" and day[7] == "-" and (day[:4] + day[5:7] + day[8:]).isdigit() else "0"


def press_limited_on():
    """False when a limited-time theme is in date and this PC picked Default or another theme (OPTIONS > Theme): its banners rest too."""
    try:
        import launcher_theme
        return not launcher_theme.switched_off()
    except Exception:
        return True


def press_theme(name):
    """The theme a picture belongs to: the word after __theme- in its name (title__theme-8bit.png -> "8bit"); "" for the others."""
    low = os.path.splitext(name)[0].lower()
    cut = low.find(THEME_TAG)
    return low[cut + len(THEME_TAG):].split("__", 1)[0] if cut >= 0 else ""


def press_worn():
    """The theme the launcher wears (OPTIONS > Theme): its short name, "" for the launcher's own look."""
    try:
        import launcher_theme
        return launcher_theme.worn()
    except Exception:
        return ""


def press_names(names):
    """Which of the pictures in assets\\press are in the rotation today. Limited-time pictures (__until-DATE in the name) that are still in
    date take the place of the usual ones: while there is at least one, only they are shown, and the day after the date the usual ones are
    back by themselves. A limited-time picture that is over is never shown; one-time pictures (__once) are never in the rotation.
    A theme's own pictures (__theme-KEY in the name) come before all of that: while that theme is worn only they are shown, and they are
    never shown with any other look."""
    names = sorted(n for n in names if n.lower().endswith((".png", ".jpg", ".jpeg")) and ONCE_TAG not in n.lower())
    today = press_today()
    worn = press_worn()
    own = [n for n in names if worn and press_theme(n) == worn and (not press_until(n) or press_until(n) >= today)]
    if own:
        return own
    names = [n for n in names if not press_theme(n)]
    limited = [n for n in names if press_until(n) >= today] if press_limited_on() else []
    return limited or [n for n in names if not press_until(n)]


def load_press():
    """Pictures you put in assets\\press (from the press kit or anywhere), fitted to the picture frame. Needs Pillow; without it they are skipped
    and PRESS_NOTE says why."""
    global PRESS_NOTE
    folder = os.path.join(ASSETS, "press")
    try:
        names = press_names(os.listdir(folder))
    except OSError:
        return []
    if not names:
        return []
    try:
        from PIL import Image, ImageTk
    except ImportError:
        PRESS_NOTE = "Pictures in assets\\press need Pillow:  python -m pip install pillow"
        return []
    pictures = []
    for name in names:
        try:
            pictures.append(ImageTk.PhotoImage(fit_picture(Image.open(os.path.join(folder, name)), GALLERY_W, GALLERY_H, press_anchor(name))))
        except Exception:
            continue
    return pictures


def load_once(cfg):
    """A one-time banner: a picture in assets\\press with __once in its name (xifo__once.png) is shown first on ONE start of the launcher
    and is never part of the rotation. config.json remembers the ones that have been shown ("banners_seen"), so to see one again, take
    its name out of that list. With several waiting, each start shows the next. Returns (picture, file name) or (None, None)."""
    folder = os.path.join(ASSETS, "press")
    seen = {str(s).lower() for s in (cfg.get("banners_seen") or [])}
    try:
        names = sorted(n for n in os.listdir(folder)
                       if n.lower().endswith((".png", ".jpg", ".jpeg")) and ONCE_TAG in n.lower() and n.lower() not in seen
                       and (not press_until(n) or press_until(n) >= press_today()))
    except OSError:
        return None, None
    for name in names:
        try:
            from PIL import Image, ImageTk
            return ImageTk.PhotoImage(fit_picture(Image.open(os.path.join(folder, name)), GALLERY_W, GALLERY_H, press_anchor(name))), name
        except Exception:
            continue
    return None, None


def load_ui_images(name):
    """The three pictures of a button from assets\\ui: <name>.png, <name>_hover.png, <name>_off.png. Missing ones come back as None
    (the button then shows its name as plain text)."""
    def get(suffix, fallback=None):
        path = os.path.join(ASSETS, "ui", name + suffix + ".png")
        if os.path.exists(path):
            try:
                return tk.PhotoImage(file=path)
            except tk.TclError:
                return fallback
        return fallback

    normal = get("")
    return {"normal": normal, "hover": get("_hover", normal), "off": get("_off", normal)}


def load_gallery():
    """The pictures shown while the game loads: every png/gif/jpg in assets\\taru. With Pillow installed any picture is fitted to the
    frame; without it only png/gif files that are already 920x368 are used."""
    folder = os.path.join(ASSETS, "taru")
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith((".png", ".gif", ".jpg", ".jpeg")))
    except OSError:
        return []
    try:
        from PIL import Image, ImageTk
    except ImportError:
        Image = ImageTk = None
    pictures = []
    for name in names:
        path = os.path.join(folder, name)
        try:
            if Image is not None:
                pictures.append(ImageTk.PhotoImage(fit_picture(Image.open(path), GALLERY_W, GALLERY_H)))
            elif name.lower().endswith((".png", ".gif")):
                photo = tk.PhotoImage(file=path)
                if photo.width() == GALLERY_W and photo.height() == GALLERY_H:
                    pictures.append(photo)
        except Exception:
            continue
    return pictures


def button_variants(kind):
    """The names of the button pictures in assets\\buttons\\<kind>: every <name>.png, with optional <name>_hover.png and <name>_off.png."""
    folder = os.path.join(ASSETS, "buttons", kind)
    try:
        return sorted(n[:-4] for n in os.listdir(folder) if n.lower().endswith(".png") and not n.lower().endswith(("_hover.png", "_off.png")))
    except OSError:
        return []


def load_button_images(kind, name):
    base = os.path.join(ASSETS, "buttons", kind, name)

    def get(suffix, fallback=None):
        path = base + suffix + ".png"
        if os.path.exists(path):
            try:
                return tk.PhotoImage(file=path)
            except tk.TclError:
                return fallback
        return fallback

    normal = get("")
    return {"normal": normal, "hover": get("_hover", normal), "off": get("_off", normal)}


def choose_button_sets():
    """One random picture for PLAY, STOP and DUALBOX from the folders, so every launch looks different. When there are at least three
    pictures of each, the three buttons show three different ones. A kind with no pictures is left out (the old single picture is used)."""
    names = {kind: button_variants(kind) for kind in ("play", "stop", "dual")}
    present = {kind: values for kind, values in names.items() if values}
    if not present:
        return {}
    shortest = min(len(values) for values in present.values())
    chosen = {}
    if len(present) == 3 and shortest >= 3:
        for kind, index in zip(present, random.sample(range(shortest), 3)):
            chosen[kind] = present[kind][index]
    else:
        for kind, values in present.items():
            chosen[kind] = random.choice(values)
    return {kind: load_button_images(kind, name) for kind, name in chosen.items()}


def load_image(name, shrink=1):
    """A picture from the assets folder, or None if it is missing (the launcher still works without the art)."""
    try:
        img = tk.PhotoImage(file=os.path.join(ASSETS, name))
        return img.subsample(shrink) if shrink > 1 else img
    except Exception:
        return None


def linux_look(root):
    """Linux (X11/Wayland): Tk draws a light focus frame round every flat button, radio button and entry, which
    Windows doesn't; turn it off so the launcher looks the same on both."""
    if linux is not None:
        root.option_add("*highlightThickness", 0)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def elevate_and_exit():
    params = "" if getattr(sys, "frozen", False) else f'"{os.path.abspath(__file__)}"'     # the exe needs no script
    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, HERE, 1)
    except Exception as e:
        result = f"{type(e).__name__}: {e}"
    if isinstance(result, int) and result > 32:
        sys.exit(0)                                       # the administrator copy is starting
    # Refused (No on Windows' prompt) or no prompt available: say so instead of closing without a word.
    text = ("XI: Forever Offline needs to run as administrator (it starts the game server and points PlayOnline at "
            "the game it uses), but Windows' permission prompt was refused or could not be shown "
            f"(code {result}).\n\nStart it again and choose Yes, or right-click it and pick 'Run as administrator'.")
    try:
        os.makedirs(LOGS, exist_ok=True)
        with open(os.path.join(LOGS, "launcher-error.log"), "w", encoding="utf-8") as f:
            f.write(text + "\n")
    except OSError:
        pass
    try:
        messagebox.showerror("XI: Forever Offline", text)
    except Exception:
        pass
    sys.exit(1)


def run_elevated(args, script="launcher_game.py"):
    """Runs one of the kit's scripts as administrator (Windows asks first) and returns at once."""
    cmd = core.py_cmd(os.path.join(HERE, script), *args)
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", cmd[0], subprocess.list2cmdline(cmd[1:]), HERE, 0)
    if result <= 32:
        raise RuntimeError("Windows' permission prompt was refused.")


class Cancelled(Exception):
    pass


class CheckList(tk.Frame):
    """The addons or plugins of one Ashita window, like other private-server launchers list them: a switch, the name,
    version and author, where it comes from, and what it does. Switching one adds/removes its load line right away."""

    TAG_COLORS = {"XI: Forever Offline": GOLD, "download": ACCENT, "added by you": GREEN, "Ashita": DIM}

    def __init__(self, parent, kind, scripts):
        super().__init__(parent, bg=BG)
        self.kind, self.scripts, self.message = kind, scripts, ""
        self.extra = None       # the newer look puts the downloads for these items here too (launcher_pages.ListDownloads)
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(top, text="Search:", bg=BG, fg=DIM).pack(side="left")
        self.search = tk.StringVar()
        entry = tk.Entry(top, textvariable=self.search, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", width=24)
        entry.pack(side="left", padx=6)
        self.search.trace_add("write", lambda *a: self.reload())
        self.count = tk.Label(top, text="", bg=BG, fg=DIM)
        self.count.pack(side="right")
        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", expand=True)
        canvas = tk.Canvas(box, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=BG)
        window = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))      # rows as wide as the page
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.reload()

    def use(self, scripts, message=""):
        """Show another window's list (or nothing, with a message saying why)."""
        self.scripts, self.message = scripts, message
        self.reload()

    def thirdparty_ids(self):
        try:
            import launcher_thirdparty
            return [i["id"] for i in launcher_thirdparty.load_manifest(HERE)] + ["XIUIplus", "Nameplate", "autobot", "movement"]
        except Exception:
            return []

    def reload(self):
        for w in self.inner.winfo_children():
            w.destroy()
        if self.scripts is None:
            tk.Label(self.inner, text=self.message or "Nothing to show.", bg=BG, fg=DIM, wraplength=480, justify="left").pack(anchor="w", padx=8, pady=8)
            self.count.configure(text="")
            return
        ashita = self.scripts.ashita
        names = core.list_addons(ashita) if self.kind == "addon" else core.list_plugins(ashita)
        try:
            on = self.scripts.enabled(self.kind)
        except Exception:
            on = set()
        self.count.configure(text=f"{sum(1 for n in names if n.lower() in on)} of {len(names)} loaded")
        if not names:
            tk.Label(self.inner, text="Nothing here yet. Use 'Add addon or plugin...' below, or copy one into the folder and press Refresh.",
                     bg=BG, fg=DIM, wraplength=480, justify="left").pack(anchor="w", padx=8, pady=8)
        wanted = self.search.get().strip().lower()
        third, added = self.thirdparty_ids(), core.added_items(HERE)
        for n in names:
            info = core.addon_info(ashita, n) if self.kind == "addon" else {"name": n, "version": "", "author": "",
                                                                            "desc": core.PLUGIN_NOTES.get(n.lower(), "")}
            if wanted and wanted not in (n + " " + info["author"] + " " + info["desc"]).lower():
                continue
            origin = core.item_origin(self.kind, n, third, added)
            row = tk.Frame(self.inner, bg=PANEL)
            row.pack(fill="x", padx=8, pady=2)
            var = tk.BooleanVar(value=n.lower() in on)
            tk.Checkbutton(row, variable=var, command=lambda n=n, v=var: self.toggle(n, v), bg=PANEL, activebackground=PANEL,
                           fg=FG, activeforeground=FG, selectcolor=BG).grid(row=0, column=0, rowspan=2, padx=(6, 2), pady=4, sticky="n")
            head = tk.Frame(row, bg=PANEL)
            head.grid(row=0, column=1, sticky="w", pady=(4, 0))
            tk.Label(head, text=n, bg=PANEL, fg=FG, font=(UI_FONT, 10, "bold")).pack(side="left")
            extra = "  ".join(x for x in ((("v" + info["version"]) if info["version"] else ""), (("by " + info["author"]) if info["author"] else "")) if x)
            if extra:
                tk.Label(head, text=extra, bg=PANEL, fg=DIM, font=(UI_FONT, 9)).pack(side="left", padx=(8, 0))
            tk.Label(head, text=origin, bg=PANEL, fg=self.TAG_COLORS.get(origin, DIM), font=(UI_FONT, 8, "bold")).pack(side="left", padx=(10, 0))
            if core.can_remove(self.kind, n, origin):       # (lilibun, 2026-11-22) what you downloaded or added can go again
                gone = tk.Label(head, text="Remove", bg=PANEL, fg=DIM, font=(UI_FONT, 8, "underline"), cursor="hand2")
                gone.pack(side="left", padx=(10, 0))
                gone.bind("<Button-1>", lambda e, n=n, o=origin: self.remove(n, o))
            warning = core.addon_warning(self.kind, n)       # (PikaFox, Neet) an add-on that does harm on this server
            if warning or info["desc"]:
                tk.Label(row, text=warning or info["desc"], bg=PANEL, fg=RED if warning else DIM, font=(UI_FONT, 9), wraplength=720,
                         justify="left", anchor="w").grid(row=1, column=1, sticky="w", pady=(0, 4))
            row.columnconfigure(1, weight=1)
            if self.extra is not None:
                self.extra.on_row(self, row, n)
        if self.extra is not None:
            self.extra.more_rows(self, wanted, names)

    def toggle(self, name, var):
        warning = core.addon_warning(self.kind, name)
        if warning and var.get() and not messagebox.askyesno("Switch " + name + " on?", warning + "\n\nSwitch it on anyway?",
                                                             default="no", icon="warning"):
            var.set(False)
            return
        try:
            self.scripts.set(self.kind, name, var.get())
        except Exception as e:
            messagebox.showerror("Could not save", str(e))
        self.reload()

    def remove(self, name, origin):
        """(lilibun, 2026-11-22) Takes an addon or plugin you downloaded or added out of Ashita again: its folder (or
        .dll) and its load line in every script. Its settings stay. Ashita's own addons and ours have no Remove."""
        ashita = self.scripts.ashita
        size = core.size_text(core.path_size(core.item_path(ashita, self.kind, name)))
        again = ("You can install it again from this page." if origin == "download"
                 else "To get it back you need your own copy of it.")
        if not messagebox.askyesno("Remove " + name, f"Remove the {self.kind} {name} from Ashita ({size})?\n\n"
                                                     f"Its settings are kept. {again}"):
            return
        try:
            core.remove_item(ashita, HERE, self.kind, name, origin)
        except Exception as e:
            messagebox.showerror("Could not remove", str(e))
        self.reload()


class ItemPicker(tk.Toplevel):
    """Pick one piece of equipment for a slot."""

    def __init__(self, parent, conn, slot, slot_label, job, level, charid, require_unlock, on_pick, icon_loader=None):
        super().__init__(parent)
        self.conn, self.slot, self.job, self.level = conn, slot, job, level
        self.charid, self.require_unlock, self.on_pick = charid, require_unlock, on_pick
        self.rows = []
        self.preview_item_id = None
        self.own_icons = icon_loader is None and itemicons is not None
        self.icon_loader = icon_loader or (itemicons.ItemIcons(self, ASSETS) if itemicons else None)
        self.title(f"Choose {slot_label} item")
        self.configure(bg=BG)
        self.geometry("440x520")
        self.transient(parent.winfo_toplevel())

        self.search = tk.StringVar()
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Search:", bg=BG, fg=FG).pack(side="left")
        entry = tk.Entry(top, textvariable=self.search, bg=PANEL, fg=FG, insertbackground=FG, relief="flat")
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.focus_set()
        self.search.trace_add("write", lambda *a: self.refresh())

        self.only_usable = tk.BooleanVar(value=True)
        tk.Checkbutton(self, text="Only items this job can wear at this level", variable=self.only_usable, command=self.refresh,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG).pack(anchor="w", padx=10)
        self.show_locked = tk.BooleanVar(value=False)
        if require_unlock:
            tk.Checkbutton(self, text="Show locked items too (not yet given to your squad)", variable=self.show_locked, command=self.refresh,
                           bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG).pack(anchor="w", padx=10)

        preview = tk.Frame(self, bg=BG)
        preview.pack(fill="x", padx=10, pady=(6, 0))
        icon_size = itemicons.ICON_SIZE if itemicons else 24
        self.preview_icon = tk.Canvas(preview, width=icon_size, height=icon_size, bg=PANEL2, highlightthickness=1,
                                      highlightbackground=BORDER, bd=0)
        self.preview_icon.pack(side="left")
        self.preview_name = tk.Label(preview, text="Select an item to see its icon.", bg=BG, fg=DIM, anchor="w")
        self.preview_name.pack(side="left", padx=8)

        self.stats = tk.Label(self, text="", bg=BG, fg=FG, wraplength=400, justify="left")
        self.stats.pack(anchor="w", padx=10)
        self.server_dir = getattr(parent, "cfg", {}).get("server_dir", "")
        self.info = tk.Label(self, text="", bg=BG, fg=DIM, wraplength=400, justify="left")
        self.info.pack(anchor="w", padx=10, pady=4)
        self.listbox = tk.Listbox(self, bg=PANEL, fg=FG, selectbackground=ACCENT, relief="flat", exportselection=False, font=(UI_FONT, 10))
        self.listbox.pack(fill="both", expand=True, padx=10, pady=4)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.show_preview())
        self.listbox.bind("<Double-Button-1>", lambda e: self.choose())

        bar = tk.Frame(self, bg=BG)
        bar.pack(pady=8)
        tk.Button(bar, text="Equip", command=self.choose, bg=ACCENT, fg="white", relief="flat", padx=16).pack(side="left", padx=4)
        tk.Button(bar, text="Cancel", command=self.destroy, bg=PANEL, fg=FG, relief="flat", padx=16).pack(side="left", padx=4)
        self.refresh()

    def refresh(self):
        usable = self.only_usable.get()
        locked_only = self.require_unlock and not self.show_locked.get()
        try:
            self.rows = sq.search_items(self.conn, self.slot, self.job if usable else 0, self.level if usable else 0,
                                        self.search.get(), charid=self.charid, require_unlock=locked_only)
        except Exception as e:
            self.rows = []
            self.info.configure(text=f"Search failed: {e}")
            return
        self.listbox.delete(0, "end")
        for _id, name, lv in self.rows:
            self.listbox.insert("end", f"{sq.pretty(name)}   (Lv {lv})")
        if locked_only and not self.rows and not self.search.get():
            self.info.configure(text="No unlocked items for this slot yet. In game, use  !squad give <item>  to add items to your squad's collection.")
        else:
            self.info.configure(text=f"{len(self.rows)} item(s)" + (" (the highest levels; type part of a name to find others)"
                                                                 if len(self.rows) >= sq.SEARCH_LIMIT else ""))
        self.preview_item_id = None
        self.stats.configure(text="")
        self.preview_name.configure(text="Select an item to see its icon.", fg=DIM)
        self.preview_icon.delete("all")

    def show_preview(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.rows):
            return
        item_id, name, level = self.rows[sel[0]]
        self.preview_item_id = item_id
        self.preview_name.configure(text=f"{sq.pretty(name)}   (Lv {level})", fg=FG)
        try:
            self.stats.configure(text="\n".join(sq.item_stats(self.conn, item_id, self.server_dir)))
        except Exception:
            self.stats.configure(text="")
        self.preview_icon.delete("all")
        if self.icon_loader is None:
            return
        picture = self.icon_loader.get(item_id, lambda p: self._paint_preview(item_id, p))
        if picture is not None:
            self._paint_preview(item_id, picture)

    def _paint_preview(self, item_id, picture):
        if item_id != self.preview_item_id:
            return
        try:
            self.preview_icon.delete("all")
            if picture is not None:
                size = self.preview_icon.winfo_reqwidth()
                self.preview_icon.create_image(size // 2, size // 2, image=picture)
        except Exception:
            pass

    def destroy(self):
        if self.own_icons and self.icon_loader is not None:
            self.icon_loader.close()
        super().destroy()

    def choose(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.on_pick(self.rows[sel[0]][0])
        self.destroy()


class RuleDialog(tk.Toplevel):
    """Add or change one squad rule. Calls on_ok(rule) with a rule that has passed the checks."""

    def __init__(self, parent, names, rule=None, on_ok=None):
        super().__init__(parent)
        self.title("Rule")
        self.configure(bg=BG)
        self.transient(parent)
        self.resizable(False, False)
        self.names, self.on_ok, self.original = names, on_ok, rule
        rule = rule or {"on": True, "target": "PARTY", "cond": ["ALWAYS", 0], "action": ["family", "CURE"]}
        body = tk.Frame(self, bg=BG)
        body.pack(padx=14, pady=12)
        self.on_var = tk.BooleanVar(value=rule.get("on", True))
        tk.Checkbutton(body, text="This rule is on", variable=self.on_var, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                       activeforeground=FG).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        self.target_labels = [lr.TARGET_LABELS[t] for t in lr.TARGETS]
        self.target_box = self.combo(body, 1, "For", self.target_labels, readonly=True, width=26)
        self.target_box.set(lr.TARGET_LABELS.get(rule.get("target"), lr.TARGET_LABELS["PARTY"]))
        self.cond1 = self.condition(body, 2, "When", rule.get("cond"), False)
        self.cond2 = self.condition(body, 3, "And", rule.get("cond2"), True)
        self.kind_box = self.combo(body, 4, "Do", list(lr.ACTIONS), readonly=True, width=26)
        self.kind_box.set(rule["action"][0] if rule.get("action") else "family")
        self.kind_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_action())
        self.kind_text = tk.Label(body, text="", bg=BG, fg=DIM)
        self.kind_text.grid(row=4, column=2, sticky="w", padx=6)
        self.name_box = self.combo(body, 5, "Name", [], readonly=False, width=26)
        if rule.get("action") and len(rule["action"]) == 2:
            self.name_box.set(rule["action"][1])
        self.refresh_action()
        tk.Label(body, text="Retry (seconds)", bg=BG, fg=FG).grid(row=6, column=0, sticky="w", pady=3)
        self.retry_var = tk.StringVar(value=str(rule.get("retry", "")))
        tk.Entry(body, textvariable=self.retry_var, width=8, bg=PANEL, fg=FG, insertbackground=FG, relief="flat").grid(row=6, column=1, sticky="w")
        tk.Label(body, text="the least time before it may repeat on the same enemy", bg=BG, fg=DIM).grid(row=6, column=2, sticky="w", padx=6)
        tk.Label(body, text="Least level", bg=BG, fg=FG).grid(row=7, column=0, sticky="w", pady=3)
        self.level_var = tk.StringVar(value=str(rule.get("level", "")))
        tk.Entry(body, textvariable=self.level_var, width=8, bg=PANEL, fg=FG, insertbackground=FG, relief="flat").grid(row=7, column=1, sticky="w")
        tk.Label(body, text="job abilities only: the level the mate needs for it", bg=BG, fg=DIM).grid(row=7, column=2, sticky="w", padx=6)
        bar = tk.Frame(self, bg=BG)
        bar.pack(pady=(0, 12))
        tk.Button(bar, text="OK", command=self.ok, bg=ACCENT, fg="white", relief="flat", padx=18).pack(side="left", padx=4)
        tk.Button(bar, text="Cancel", command=self.destroy, bg=PANEL, fg=FG, relief="flat", padx=14).pack(side="left", padx=4)

    def combo(self, parent, row, label, values, readonly, width):
        tk.Label(parent, text=label, bg=BG, fg=FG).grid(row=row, column=0, sticky="w", pady=3)
        box = ttk.Combobox(parent, values=values, state="readonly" if readonly else "normal", width=width)
        box.grid(row=row, column=1, sticky="w")
        return box

    def condition(self, parent, row, label, cond, allow_none):
        names = (["(none)"] if allow_none else []) + list(lr.CONDITIONS)
        name_box = self.combo(parent, row, label, names, readonly=True, width=26)
        arg_box = ttk.Combobox(parent, values=[], width=20)
        arg_box.grid(row=row, column=2, sticky="w", padx=6)
        name, text = lr.condition_to_fields(cond) if cond else ("(none)" if allow_none else "ALWAYS", "")
        name_box.set(name)
        parts = {"name": name_box, "arg": arg_box}
        name_box.bind("<<ComboboxSelected>>", lambda e: self.refresh_condition(parts))
        self.refresh_condition(parts, text)
        return parts

    def refresh_condition(self, parts, text=None):
        name = parts["name"].get()
        kind = lr.CONDITIONS.get(name, (None, None))[1]
        parts["arg"].configure(values=self.names.get(kind, []) if kind in ("effect", "flag", "ecosystem") else [],
                               state="normal" if kind else "disabled")
        parts["arg"].set(text if (text is not None and kind) else "")

    def refresh_action(self):
        kind = self.kind_box.get()
        self.kind_text.configure(text=lr.ACTIONS.get(kind, ""))
        named = kind in ("family", "spell", "ja")
        self.name_box.configure(values=self.names.get(kind, []) if named else [], state="normal" if named else "disabled")
        if not named:
            self.name_box.set("")

    def ok(self):
        label = self.target_box.get()
        target = lr.TARGETS[self.target_labels.index(label)] if label in self.target_labels else None
        fields = {"cond": (self.cond1["name"].get(), self.cond1["arg"].get()), "cond2": (self.cond2["name"].get(), self.cond2["arg"].get())}
        rule, problems = lr.build_rule(self.on_var.get(), target, fields["cond"][0], fields["cond"][1], fields["cond2"][0], fields["cond2"][1],
                                       self.kind_box.get(), self.name_box.get(), self.retry_var.get(), self.level_var.get())
        if problems:
            messagebox.showerror("Rule", "\n".join(problems), parent=self)
            return
        rule = lr.keep_original_conditions(self.original, rule, fields)
        self.destroy()
        if self.on_ok:
            self.on_ok(rule)


class RulesEditor(tk.Toplevel):
    """Edit what each job does: the rules a squad mate follows, starting from the built-in ones. Saved to squad_rules_user.json, and written
    for the server as modules/custom/lua/squad_rules_data.lua (read when the servers start)."""

    COLUMNS = (("on", "On", 42), ("target", "For", 130), ("when", "When", 230), ("and", "And", 170), ("do", "Do", 190), ("retry", "Retry s", 56), ("level", "Level", 48))

    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.title("Squad job rules")
        self.configure(bg=BG)
        self.geometry("1000x600")
        self.transient(parent)
        defaults = lr.load_json(os.path.join(HERE, "squad-data", "squad_rules_default.json"))
        if not defaults:
            messagebox.showerror("Squad job rules", "I could not find squad-data\\squad_rules_default.json.\n\nInstall the squad behavior update first.")
            self.after(0, self.destroy)
            return
        self.names = lr.known_names(defaults)
        user_path = os.path.join(HERE, "squad-data", "squad_rules_user.json")
        lua_path = os.path.join(cfg["server_dir"], "modules", "custom", "lua", "squad_rules_data.lua")
        self.state = lr.EditorState(lr.RuleSet(defaults, lr.load_json(user_path)), user_path, lua_path)
        self.build()
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def build(self):
        style = ttk.Style(self)
        style.configure("Rules.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24, borderwidth=0)
        style.map("Rules.Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        style.configure("Rules.Treeview.Heading", background=PANEL2, foreground=FG, relief="flat")
        # (2026-11-22, wildthing: players looked here for a way to add spells) what this editor is, and where the rest lives
        note = tk.Frame(self, bg=PANEL2)
        note.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(note, text="Job rules are the built-in behaviour every squad mate of a job follows: when it uses the abilities "
                            "and spells its job already knows. They can't add new spells or choose them for one mate. For that, "
                            "use Gambits: type /gambits in the game to give one mate your own Rule Sets (spells, targets, "
                            "conditions, weapon skills). When a Gambits Rule Set is applied to a mate, it decides that mate's actions.",
                 bg=PANEL2, fg=FG, wraplength=820, justify="left").pack(side="left", padx=10, pady=8)
        tk.Button(note, text="Gambits guide", relief="flat", bg=ACCENT, fg="white", padx=10,
                  command=lambda: __import__("webbrowser").open(
                      "https://discord.com/channels/1571346961779400859/1573535859980894338")).pack(side="right", padx=10, pady=8)
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(top, text="Job", bg=BG, fg=FG).pack(side="left")
        self.job_box = ttk.Combobox(top, values=lr.JOB_ORDER, state="readonly", width=6)
        self.job_box.set(self.state.job)
        self.job_box.pack(side="left", padx=6)
        self.job_box.bind("<<ComboboxSelected>>", lambda e: self.pick())
        self.part_var = tk.StringVar(value=self.state.part)
        for part in lr.PARTS:
            tk.Radiobutton(top, text=lr.PART_LABELS[part], value=part, variable=self.part_var, command=self.pick, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG).pack(side="left", padx=(8, 0))
        self.enabled_var = tk.BooleanVar(value=True)
        self.enabled_check = tk.Checkbutton(top, text="Use my rules for this job", variable=self.enabled_var, command=self.toggle_enabled, bg=BG, fg=FG,
                                            selectcolor=PANEL, activebackground=BG, activeforeground=FG)
        self.enabled_check.pack(side="left", padx=(20, 0))
        self.status = tk.Label(self, text="", bg=BG, fg=DIM, anchor="w")
        self.status.pack(fill="x", padx=14)

        middle = tk.Frame(self, bg=BG)
        middle.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree = ttk.Treeview(middle, columns=[c[0] for c in self.COLUMNS], show="headings", style="Rules.Treeview", selectmode="browse")
        for key, title, width in self.COLUMNS:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor="w", stretch=key in ("when", "do"))
        scroll = ttk.Scrollbar(middle, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit_rule())

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=12, pady=4)
        for text, command in (("Add rule", self.add_rule), ("Edit", self.edit_rule), ("Delete", self.delete_rule), ("Move up", lambda: self.move(-1)),
                              ("Move down", lambda: self.move(1)), ("Turn on / off", self.toggle_rule)):
            tk.Button(bar, text=text, command=command, bg=PANEL, fg=FG, relief="flat", padx=10, pady=3).pack(side="left", padx=(0, 6))
        tk.Button(bar, text="Reset this list", command=self.reset_list, bg=PANEL, fg=FG, relief="flat", padx=10, pady=3).pack(side="right", padx=(6, 0))
        tk.Button(bar, text="Reset this job", command=self.reset_job, bg=PANEL, fg=FG, relief="flat", padx=10, pady=3).pack(side="right")

        tk.Label(self, text=("Rules are read top to bottom. A role or mode (Behavior page) still applies on top of them. How a mate stands and moves is not part of "
                             "the rules. Names the server does not know are skipped and logged, so a typo never stops a mate from appearing."),
                 bg=BG, fg=DIM, wraplength=950, justify="left").pack(anchor="w", padx=14, pady=(2, 0))
        bottom = tk.Frame(self, bg=BG)
        bottom.pack(fill="x", padx=12, pady=8)
        tk.Button(bottom, text="Save", command=self.save, bg=ACCENT, fg="white", relief="flat", padx=22, pady=4).pack(side="left")
        tk.Button(bottom, text="Close", command=self.close, bg=PANEL, fg=FG, relief="flat", padx=16, pady=4).pack(side="left", padx=8)
        self.msg = tk.Label(bottom, text="", bg=BG, fg=DIM, wraplength=760, justify="left")
        self.msg.pack(side="left", padx=10)

    def say(self, text):
        self.msg.configure(text=text)

    def pick(self):
        self.state.pick(self.job_box.get(), self.part_var.get())
        self.refresh()

    def refresh(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.state.rows()):
            self.tree.insert("", "end", iid=str(i), values=[row[key] for key, _title, _w in self.COLUMNS])
        job = self.state.job
        self.enabled_var.set(self.state.rs.enabled(job))
        self.enabled_check.configure(state="normal" if self.state.rs.is_custom(job) else "disabled")
        self.status.configure(text=f"{job} - {lr.PART_LABELS[self.state.part]}: {self.state.status()}")
        if select is not None and 0 <= select < len(self.state.rules):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))

    def selected(self):
        chosen = self.tree.selection()
        return int(chosen[0]) if chosen else None

    def need_selection(self):
        index = self.selected()
        if index is None:
            self.say("Pick a rule in the list first.")
        return index

    def add_rule(self):
        index = self.selected()
        at = None if index is None else index + 1
        RuleDialog(self, self.names, None, lambda rule: (self.state.add(rule, at), self.refresh(select=len(self.state.rules) - 1 if at is None else at)))

    def edit_rule(self):
        index = self.need_selection()
        if index is not None:
            RuleDialog(self, self.names, self.state.rules[index], lambda rule: (self.state.update(index, rule), self.refresh(select=index)))

    def delete_rule(self):
        index = self.need_selection()
        if index is not None and messagebox.askyesno("Delete rule", "Delete this rule?", parent=self):
            self.state.delete(index)
            self.refresh(select=min(index, len(self.state.rules) - 1))

    def move(self, delta):
        index = self.need_selection()
        if index is not None:
            self.refresh(select=self.state.move(index, delta))

    def toggle_rule(self):
        index = self.need_selection()
        if index is not None:
            self.state.toggle(index)
            self.refresh(select=index)

    def toggle_enabled(self):
        self.state.set_enabled(bool(self.enabled_var.get()))
        self.refresh()

    def reset_list(self):
        if messagebox.askyesno("Reset", "Put this list back to the built-in rules?", parent=self):
            self.state.reset_list()
            self.refresh()

    def reset_job(self):
        if messagebox.askyesno("Reset", f"Put every list of {self.state.job} back to the built-in rules?", parent=self):
            self.state.reset_job()
            self.refresh()

    def save(self):
        try:
            self.say(self.state.save())
        except ValueError as problem:
            messagebox.showerror("Squad job rules", str(problem), parent=self)
        except OSError as problem:
            messagebox.showerror("Squad job rules", f"Could not write the files: {problem}", parent=self)

    def close(self):
        if self.state.dirty:
            answer = messagebox.askyesnocancel("Squad job rules", "Save your changes before closing?", parent=self)
            if answer is None:
                return
            if answer:
                self.save()
                if self.state.dirty:
                    return
        self.destroy()


class HoverTip:
    """A small text box that follows the pointer while it is over a widget. text_fn() gives the text (None = nothing)."""

    def __init__(self, widget, text_fn):
        self.widget, self.text_fn, self.tip = widget, text_fn, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, event=None):
        try:
            text = self.text_fn()
        except Exception:
            text = None
        if not text:
            return
        self.hide()
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        x, y = self.widget.winfo_rootx() + 20, self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=text, bg=PANEL2, fg=FG, relief="solid", bd=1, justify="left", wraplength=360,
                 padx=8, pady=4).pack()

    def hide(self, event=None):
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None


REVAMPED_GREY_TIP = "Comes with Gambits Revamped / Squads Revamped"

# Squad faces: the game's face numbers 0-15 are 1A, 1B, 2A ... 8B (char_entity.h CharFace)
FACE_LABELS = [f"{i // 2 + 1}{'AB'[i % 2]}  ({i + 1})" for i in range(16)]
FACE_FILES = {1: "Hm", 2: "Hf", 3: "Em", 4: "Ef", 5: "Tm", 6: "Tf", 7: "M", 8: "G"}  # race id -> assets\faces prefix
_face_cache = {}


def face_photo(race, face, w, h):
    """The picture assets/faces/<race><n><a|b>.jpg as a Tk picture (None without Pillow or the file)."""
    key = (race, face, w, h)
    if key not in _face_cache:
        photo = None
        path = os.path.join(ASSETS, "faces", f"{FACE_FILES.get(race, 'Hm')}{face // 2 + 1}{'ab'[face % 2]}.jpg")
        try:
            from PIL import Image, ImageTk
            photo = ImageTk.PhotoImage(Image.open(path).convert("RGB").resize((w, h)))
        except Exception:
            photo = None
        _face_cache[key] = photo
    return _face_cache[key]


class SquadTab(tk.Frame):
    """Create squad mates, set their look, jobs, job levels and gear. Changes are saved to the database right away
    and apply the next time a mate is called in game."""

    def __init__(self, parent, cfg):
        super().__init__(parent, bg=BG)
        self.cfg = cfg
        self.conn = None
        self.chars, self.mates, self.mate = [], [], None
        # (2026-11-21) the Rules page's "Squad gets all gear" lifts the gear lock in the gear picker too
        self.require_unlock = bool(cfg.get("squad_require_unlock", True)) and not core.load_rates(HERE).get("squad_all_gear", False)
        # player installs: mates start at level 1 and level up in game, and a look is picked once (as in squad.lua)
        self.player = bool(cfg.get("mariadb_dir"))
        try:
            sq.read_subjob_ratio(cfg.get("server_dir", ""))    # (Bob Roberts) sub levels as the server's SUBJOB_RATIO
        except Exception:
            pass
        self.level_vars, self.gear_vars, self.level_spins = {}, {}, {}
        self.raise_buttons = {}
        self.gear_icons, self.gear_items = {}, {}
        self.icon_loader = itemicons.ItemIcons(self, ASSETS) if itemicons else None
        self.unlocked, self.choices = set(), []
        self.greeting_defaults = os.path.join(HERE, "squad-data", "squad_greetings_default.json")
        self.greeting_user = os.path.join(HERE, "squad-data", "squad_greetings_user.json")
        self.greeting_lua = os.path.join(cfg.get("server_dir", ""), "modules", "custom", "lua", "squad_greetings_data.lua")
        self.is_running = lambda: False          # the launcher sets this: True while the servers are up
        self.build()
        self.after(300, self.load_characters)

    # ----- layout -----
    def build(self):
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Character:", bg=BG, fg=FG).pack(side="left")
        self.char_var = tk.StringVar()
        self.char_box = ttk.Combobox(top, textvariable=self.char_var, state="readonly", width=22)
        self.char_box.pack(side="left", padx=6)
        self.char_box.bind("<<ComboboxSelected>>", lambda e: self.load_squad())
        tk.Button(top, text="Refresh", command=self.load_characters, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left")
        self.msg = tk.Label(self, text="", bg=BG, fg=DIM, wraplength=520, justify="left")
        self.msg.pack(anchor="w", padx=10)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=4)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        self.listbox = tk.Listbox(left, height=8, width=26, bg=PANEL, fg=FG, selectbackground=ACCENT, relief="flat",
                                  exportselection=False, font=(UI_FONT, 10))
        self.listbox.pack()
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.on_select())
        bar = tk.Frame(left, bg=BG)
        bar.pack(pady=6)
        tk.Button(bar, text="New", command=self.new_mate, bg=ACCENT, fg="white", relief="flat", padx=12).pack(side="left", padx=3)
        tk.Button(bar, text="Delete", command=self.delete_mate, bg=PANEL, fg=FG, relief="flat", padx=12).pack(side="left", padx=3)
        # (2026-11-24) the whole squad to one file and back (launcher_squad_backup.py)
        bar2 = tk.Frame(left, bg=BG)
        bar2.pack()
        tk.Button(bar2, text="Back up squad", command=self.backup_squad, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left", padx=3)
        tk.Button(bar2, text="Restore...", command=self.restore_squad, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left", padx=3)

        pages = ttk.Notebook(body)
        pages.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.build_look_page(pages)
        self.build_levels_page(pages)
        self.build_gear_page(pages)
        self.build_behavior_page(pages)
        self.build_greetings_page(pages)
        if lp is not None:
            self.build_personality_page(pages)

    def row(self, parent, label):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", padx=10, pady=3)
        tk.Label(f, text=label, bg=BG, fg=FG, width=11, anchor="w").pack(side="left")
        return f

    def build_look_page(self, pages):
        page = tk.Frame(pages, bg=BG)
        pages.add(page, text=" Look & jobs ")
        self.name_var = tk.StringVar()
        f = self.row(page, "Name")
        tk.Entry(f, textvariable=self.name_var, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", width=18).pack(side="left")
        tk.Button(f, text="Rename", command=self.apply_name, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left", padx=6)

        f = self.row(page, "Race")
        self.race_box = ttk.Combobox(f, values=sq.RACES, state="readonly", width=18)
        self.race_box.pack(side="left")
        f = self.row(page, "Face")
        self.face_box = ttk.Combobox(f, values=FACE_LABELS, state="readonly", width=10)
        self.face_box.pack(side="left")
        self.look_button = tk.Button(f, text="Apply look", command=self.apply_look, bg=PANEL, fg=FG, relief="flat", padx=8)
        self.look_button.pack(side="left", padx=6)
        self.faces_button = tk.Button(f, text="See all faces", command=self.show_faces, bg=PANEL, fg=FG, relief="flat", padx=8)
        self.faces_button.pack(side="left")
        # a picture of the chosen race and face (assets\faces, the character creation pictures)
        self.face_picture = tk.Label(page, bg=BG)
        self.face_picture.pack(anchor="w", padx=(96, 10), pady=(2, 2))
        self.face_photo = None
        self.race_box.bind("<<ComboboxSelected>>", lambda e: self.show_face_picture())
        self.face_box.bind("<<ComboboxSelected>>", lambda e: self.show_face_picture())
        if self.player:
            self.look_note = tk.Label(page, text="", bg=BG, fg=DIM, justify="left")
            self.look_note.pack(anchor="w", padx=10)

        f = self.row(page, "Main job")
        self.mjob_box = ttk.Combobox(f, values=sq.JOBS, state="readonly", width=8)
        self.mjob_box.pack(side="left")
        f = self.row(page, "Sub job")
        self.sjob_box = ttk.Combobox(f, values=["None"] + sq.JOBS, state="readonly", width=8)
        self.sjob_box.pack(side="left")
        tk.Button(f, text="Apply jobs", command=self.apply_jobs, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left", padx=6)

        self.summary = tk.Label(page, text="", bg=BG, fg=FG, justify="left", wraplength=360)
        self.summary.pack(anchor="w", padx=10, pady=10)
        tk.Label(page, text="Sub jobs unlock at main level 18. The sub level is half the main level, but never higher\n"
                            "than the sub job's own level. Changes apply next time you call the mate in game.",
                 bg=BG, fg=DIM, justify="left", wraplength=360).pack(anchor="w", padx=10)

    def build_levels_page(self, pages):
        page = tk.Frame(pages, bg=BG)
        pages.add(page, text=" Job levels ")
        grid = tk.Frame(page, bg=BG)
        grid.pack(padx=10, pady=8, anchor="w")
        for i, job in enumerate(sq.JOBS):
            col, r = (i // 8) * 4, i % 8
            tk.Label(grid, text=job, bg=BG, fg=FG, width=5, anchor="w").grid(row=r, column=col, pady=2)
            var = tk.IntVar(value=1)
            self.level_vars[i + 1] = var
            spin = tk.Spinbox(grid, from_=1, to=sq.MAX_LEVEL, width=4, textvariable=var, bg=PANEL, fg=FG, relief="flat",
                              state="disabled" if self.player else "normal")     # players: levels are earned (and set when a mate is made)
            spin.grid(row=r, column=col + 1, padx=4)
            self.level_spins[i + 1] = spin
            exp = tk.Label(grid, text="", bg=BG, fg=DIM, width=9, anchor="w")
            exp.grid(row=r, column=col + 2)
            self.level_vars[("exp", i + 1)] = exp
            # (2026-11-24, levi) a quick start for an unlocked job: raise it to 12 (shown only while it is below 12)
            raise_btn = tk.Button(grid, text=f"To {sq.RAISE_LEVEL}", command=lambda j=i + 1: self.raise_job(j),
                                  bg=PANEL, fg=FG, relief="flat", padx=4, pady=0, font=(UI_FONT, 8))
            raise_btn.grid(row=r, column=col + 3, padx=(0, 12))
            self.raise_buttons[i + 1] = raise_btn
        if not self.player:
            tk.Button(page, text="Save levels", command=self.apply_levels, bg=ACCENT, fg="white", relief="flat", padx=14).pack(pady=8)
        tk.Label(page, text="Each job levels on its own in game. Exp is shown next to each level." if not self.player else
                 "Squad mates start at level 1 and level up by fighting with you, one job at a time.\n"
                 f"Exp is shown next to each level. \"To {sq.RAISE_LEVEL}\" raises an unlocked job below {sq.RAISE_LEVEL} "
                 f"straight to {sq.RAISE_LEVEL}.", bg=BG, fg=DIM, justify="left").pack(anchor="w", padx=10, pady=8)

    def build_gear_page(self, pages):
        page = tk.Frame(pages, bg=BG)
        pages.add(page, text=" Gear ")
        self.gear_title = tk.Label(page, text="", bg=BG, fg=FG, font=(UI_FONT, 10, "bold"))
        self.gear_title.pack(anchor="w", padx=10, pady=(8, 2))
        grid = tk.Frame(page, bg=BG)
        grid.pack(padx=10, anchor="w")
        icon_size = itemicons.ICON_SIZE if itemicons else 24
        for r, (slot, label) in enumerate(sq.EQUIP_SLOTS):
            tk.Label(grid, text=label, bg=BG, fg=DIM, width=7, anchor="w").grid(row=r, column=0, pady=1)
            icon = tk.Canvas(grid, width=icon_size, height=icon_size, bg=PANEL2, highlightthickness=1,
                             highlightbackground=BORDER, bd=0)
            icon.grid(row=r, column=1, padx=(0, 6), pady=1)
            self.gear_icons[slot] = icon
            var = tk.StringVar(value="-")
            self.gear_vars[slot] = var
            name_label = tk.Label(grid, textvariable=var, bg=BG, fg=FG, width=26, anchor="w")
            name_label.grid(row=r, column=2)
            HoverTip(name_label, lambda s=slot: self.gear_stats(s))   # (its stats when the pointer is on the name)
            tk.Button(grid, text="Change", command=lambda s=slot, l=label: self.pick_item(s, l), bg=PANEL, fg=FG, relief="flat", padx=6).grid(row=r, column=3, padx=2)
            tk.Button(grid, text="Clear", command=lambda s=slot: self.clear_item(s), bg=PANEL, fg=FG, relief="flat", padx=6).grid(row=r, column=4)
        tk.Label(page, text="Gear is saved per job. Items must fit the slot, the job and the mate's level.",
                 bg=BG, fg=DIM).pack(anchor="w", padx=10, pady=4)

    def destroy(self):
        if self.icon_loader is not None:
            self.icon_loader.close()
        super().destroy()

    # ----- data -----
    def build_behavior_page(self, pages):
        page = tk.Frame(pages, bg=BG)
        pages.add(page, text=" Behavior ")
        self.beh_title = tk.Label(page, text="", bg=BG, fg=FG, font=(UI_FONT, 10, "bold"))
        self.beh_title.pack(anchor="w", padx=10, pady=(10, 4))
        f = self.row(page, "Role")
        self.role_box = ttk.Combobox(f, values=sq.ROLES, state="readonly", width=12)
        self.role_box.pack(side="left")
        f = self.row(page, "Mode")
        self.mode_box = ttk.Combobox(f, values=sq.MODES, state="readonly", width=12)
        self.mode_box.pack(side="left")
        tk.Button(f, text="Apply", command=self.apply_behavior, bg=PANEL, fg=FG, relief="flat", padx=14).pack(side="left", padx=10)
        tk.Label(page, text=sq.behavior_help_text(),
                 bg=BG, fg=DIM, wraplength=520, justify="left").pack(anchor="w", padx=10, pady=(8, 4))
        tk.Label(page, text="Applies the next time you call the mate. Change it with the game closed here, or in the game (the Squad panel, /sq). "
                            + sq.ROLE_FOOTER,
                 bg=BG, fg=DIM, wraplength=520, justify="left").pack(anchor="w", padx=10)
        tk.Button(page, text="Edit job rules...", command=self.open_rules, bg=ACCENT, fg="white", relief="flat", padx=14, pady=4).pack(anchor="w", padx=10, pady=(12, 2))
        tk.Label(page, text="Job rules set how every mate of a job behaves by default. To choose your own spells, targets and "
                            "conditions for one mate, use Gambits instead (type /gambits in the game).",
                 bg=BG, fg=DIM, wraplength=520, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

    def build_greetings_page(self, pages):
        page = tk.Frame(pages, bg=BG)
        pages.add(page, text=" Greetings ")
        tk.Label(page, text="What this mate says when called, when they level up, when knocked out, and on a weaponskill.",
                 bg=BG, fg=FG, font=(UI_FONT, 10, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(page, text=sq.GREETING_HELP, bg=BG, fg=DIM, wraplength=470, justify="left").pack(anchor="w", padx=10)

        grid = tk.Frame(page, bg=BG)
        grid.pack(fill="both", expand=True, padx=10, pady=4)
        grid.columnconfigure(0, weight=1)
        self.greeting_boxes = {}
        for index, event in enumerate(sq.GREETING_EVENTS):
            tk.Label(grid, text=sq.GREETING_LABELS[event], bg=BG, fg=FG, anchor="w").grid(
                row=index * 2, column=0, sticky="w", pady=(6, 0))
            box = tk.Text(grid, height=3, width=56, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                          wrap="word", font=(UI_FONT, 9))
            box.grid(row=index * 2 + 1, column=0, sticky="ew")
            self.greeting_boxes[event] = box

        tk.Label(page, text="The server reads these when it starts, so save here and press PLAY again to hear them.",
                 bg=BG, fg=DIM, wraplength=470, justify="left").pack(anchor="w", padx=10, pady=(2, 0))
        bar = tk.Frame(page, bg=BG)
        bar.pack(anchor="w", padx=10, pady=8)
        tk.Button(bar, text="Save greetings", command=self.save_greetings, bg=ACCENT, fg="white", relief="flat", padx=14, pady=4).pack(side="left")
        tk.Button(bar, text="Reset to built-in", command=self.reset_greetings, bg=PANEL, fg=FG, relief="flat", padx=12, pady=4).pack(side="left", padx=8)

    def show_greetings(self):
        if self.mate is None or not getattr(self, "greeting_boxes", None):
            return
        data = sq.greeting_data(self.greeting_defaults, self.greeting_user)
        row = data.get(self.mate["name"], {})
        for event, box in self.greeting_boxes.items():
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(row.get(event) or []))
        if not os.path.exists(self.greeting_defaults):
            self.say("squad-data\\squad_greetings_default.json is missing: the boxes start empty.")

    def save_greetings(self):
        m = self.mate
        if m is None:
            return
        lines = {event: box.get("1.0", "end").splitlines() for event, box in self.greeting_boxes.items()}
        if not any(sq.clean_greeting_lines(value) for value in lines.values()):
            if not messagebox.askyesno("Greetings", f"{m['name']} will use the built-in voice lines. Save that?", parent=self):
                return

        def go():
            sq.save_greetings(self.greeting_user, m["name"], lines)
            sq.write_greetings_lua(self.greeting_lua, sq.greeting_data(self.greeting_defaults, self.greeting_user))
            self.show_greetings()
            self.say(f"Saved greetings for {m['name']}. Restart the servers (PLAY) so the new lines load.")
        self.guard(go)

    def reset_greetings(self):
        m = self.mate
        if m is None:
            return
        if not messagebox.askyesno("Greetings", f"Put {m['name']} back to the built-in greetings?", parent=self):
            return

        def go():
            sq.clear_greetings(self.greeting_user, m["name"])
            sq.write_greetings_lua(self.greeting_lua, sq.greeting_data(self.greeting_defaults, self.greeting_user))
            self.show_greetings()
            self.say(f"{m['name']} uses the built-in greetings again. Restart the servers (PLAY) to hear them.")
        self.guard(go)

    # ----- personality (the sheet squad chat uses: squad-chat\mates\<name>.json) -----
    def build_personality_page(self, pages):
        page = tk.Frame(pages, bg=BG)
        pages.add(page, text=" Personality ")
        self.pers_title = tk.Label(page, text="Personality", bg=BG, fg=FG, font=(UI_FONT, 10, "bold"))
        self.pers_title.pack(anchor="w", padx=10, pady=(8, 0))
        tk.Label(page, text="Who this mate is when they talk in party chat (squad chat, part of Living world + AI chat). "
                 "Write it yourself, start from an example, or let the AI write one. Name, race and job come from the "
                 "Look & jobs page.", bg=BG, fg=DIM, wraplength=470, justify="left").pack(anchor="w", padx=10)

        f = tk.Frame(page, bg=BG)
        f.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(f, text="Start from", bg=BG, fg=FG, width=11, anchor="w").pack(side="left")
        self.pers_example = ttk.Combobox(f, state="readonly", width=26)
        self.pers_example.pack(side="left")
        tk.Button(f, text="Use example", command=self.use_personality_example, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left", padx=6)

        grid = tk.Frame(page, bg=BG)
        grid.pack(fill="both", expand=True, padx=10, pady=2)
        grid.columnconfigure(1, weight=1)
        self.pers_fields = {}
        rows = (("personality", "Personality", 2), ("voice", "Voice", 1), ("quirk", "Quirk", 1), ("goal", "Goal", 1),
                ("fear", "Fear", 1), ("backstory", "Backstory", 5), ("hooks", "Story hooks", 2),
                ("chat_examples", "How they sound", 3))
        for index, (key, label, height) in enumerate(rows):
            tk.Label(grid, text=label, bg=BG, fg=FG, anchor="nw", width=13).grid(row=index, column=0, sticky="nw", pady=2)
            box = tk.Text(grid, height=height, width=48, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                          wrap="word", font=(UI_FONT, 9))
            box.grid(row=index, column=1, sticky="ew", pady=2)
            self.pers_fields[key] = box
        tk.Label(grid, text="(one per line)", bg=BG, fg=DIM, font=(UI_FONT, 8)).grid(row=len(rows), column=1, sticky="w")

        f = tk.Frame(page, bg=BG)
        f.pack(fill="x", padx=10, pady=2)
        tk.Label(f, text="Talkativeness", bg=BG, fg=FG, width=13, anchor="w").pack(side="left")
        self.pers_talk = tk.Scale(f, from_=0.2, to=3.0, resolution=0.1, orient="horizontal", length=200, bg=BG, fg=FG,
                                  highlightthickness=0, troughcolor=PANEL, showvalue=True)
        self.pers_talk.pack(side="left")
        tk.Label(f, text="quiet ... chatty", bg=BG, fg=DIM).pack(side="left", padx=6)

        bar = tk.Frame(page, bg=BG)
        bar.pack(anchor="w", padx=10, pady=8)
        tk.Button(bar, text="Save personality", command=self.save_personality, bg=ACCENT, fg="white", relief="flat", padx=14, pady=4).pack(side="left")
        tk.Button(bar, text="Let the AI write it", command=self.ai_personality, bg=PANEL, fg=FG, relief="flat", padx=12, pady=4).pack(side="left", padx=8)
        self.pers_note = tk.Label(page, text="", bg=BG, fg=DIM, wraplength=470, justify="left")
        self.pers_note.pack(anchor="w", padx=10)

    def _pers_facts(self):
        m = self.mate
        return m["name"], m["race"] or 1, sq.JOBS[m["mjob"] - 1], sq.effective_levels(m)[0]

    def _pers_sheet(self):
        """The mate's sheet as it is on disk, with today's name, race, job and level."""
        name, race, job, level = self._pers_facts()
        sheet = lp.load_sheet(HERE, name)
        return lp.update_facts(sheet, name, race, job, level) if sheet else lp.new_sheet(name, race, job, level)

    def _pers_fill(self, sheet):
        for key, box in self.pers_fields.items():
            value = sheet.get(key, "")
            if isinstance(value, list):
                value = "\n".join(str(item) for item in value)
            box.delete("1.0", "end")
            box.insert("1.0", str(value or ""))
        self.pers_talk.set(lp.clamp_talk(sheet.get("talkativeness", 1.0)))

    def _pers_read(self):
        sheet = self._pers_sheet()
        for key, box in self.pers_fields.items():
            text = box.get("1.0", "end").strip()
            sheet[key] = [line for line in text.splitlines() if line.strip()] if key in lp.LIST_FIELDS else text
        sheet["talkativeness"] = self.pers_talk.get()
        return sheet

    def show_personality(self):
        if lp is None or self.mate is None or not getattr(self, "pers_fields", None):
            return
        self.pers_examples = lp.examples(HERE)
        self.pers_example.configure(values=[title for title, _ in self.pers_examples])
        if self.pers_examples and not self.pers_example.get():
            self.pers_example.current(0)
        on_disk = lp.load_sheet(HERE, self.mate["name"]) is not None
        self._pers_fill(self._pers_sheet())
        self.pers_title.configure(text=f"{self.mate['name']}: personality" + ("" if on_disk else " (none yet)"))
        self.pers_note.configure(text="" if on_disk else "No personality yet. Squad chat writes one with the AI the first "
                                 "time this mate is called, unless you save one here first.")

    def use_personality_example(self):
        if self.mate is None:
            return
        chosen = dict(getattr(self, "pers_examples", [])).get(self.pers_example.get())
        if not chosen:
            return
        self._pers_fill(lp.apply_example(self._pers_read(), chosen))
        self.pers_note.configure(text="Example filled in. Change anything you like, then Save personality.")

    def save_personality(self):
        if self.mate is None:
            return
        sheet = self._pers_read()
        trouble = lp.problems(sheet)
        if trouble:
            messagebox.showinfo("Personality", "\n".join(trouble), parent=self)
            return

        def go():
            lp.save_sheet(HERE, sheet)
            self.show_personality()
            self.pers_note.configure(text=f"Saved. Squad chat uses it the next time {sheet['name']} speaks (the old one is kept as .json.bak).")
        self.guard(go)

    def ai_personality(self):
        if self.mate is None:
            return
        name, race, job, level = self._pers_facts()
        rewrite = lp.load_sheet(HERE, name) is not None
        if rewrite and not messagebox.askyesno("Personality", f"Let the AI write a new personality for {name}? "
                                               "The current one is kept as a .json.bak file.", parent=self):
            return

        def go():
            lp.request_ai_sheet(HERE, name, race, job, level)
            self.pers_note.configure(text="Asked squad chat to write it. It needs Living world + AI chat; it is written while "
                                     "the game runs (a minute or so), and you get a [Squad] note in game when it is ready.")
        self.guard(go)

    def show_behavior(self):
        m = self.mate
        if m is None or lr is None:
            return
        try:
            role, mode = sq.get_behavior(self.conn, self.charid(), m["id"])
        except Exception as problem:
            self.beh_title.configure(text=f"{m['name']}: role and mode (could not be read: {problem})")
            return
        self.role_box.set(role)
        self.mode_box.set(mode)
        self.beh_title.configure(text=f"{m['name']}: role and mode")

    def apply_behavior(self):
        def go():
            m = self.mate
            if m is None:
                return
            if self.is_running():
                messagebox.showinfo("Squad", "The servers are running, and they keep a character's variables in memory, so a change made here "
                                             "could be lost.\n\nClose the game first, or use the Squad panel in the game (/sq).")
                return
            sq.set_behavior(self.conn, self.charid(), m["id"], self.role_box.get(), self.mode_box.get())
            self.say(f"Saved: {m['name']} is now {self.role_box.get()} / {self.mode_box.get()}. It applies the next time you call them.")
        self.guard(go)

    def open_rules(self):
        if lr is None:
            messagebox.showerror("Squad", "The rules editor (launcher_rules.py) is missing. Unpack the squad behavior update again.")
            return
        RulesEditor(self, self.cfg)

    def say(self, text):
        self.msg.configure(text=text)

    def guard(self, fn):
        """Run a database action; show a message instead of crashing on errors."""
        try:
            return fn()
        except Exception as e:
            self.say(f"Error: {e}")
            messagebox.showerror("Squad", str(e))
            return None

    def load_characters(self):
        def go():
            if self.conn is None:
                self.conn = sq.connect(self.cfg)
            self.chars = sq.list_characters(self.conn)
            self.char_box.configure(values=[f"{n} (#{i})" for i, n in self.chars])
            if self.chars:
                if self.char_box.current() < 0:
                    self.char_box.current(0)
                self.load_squad()
            else:
                self.say("No characters found. Log in to the game once to create one.")
        self.guard(go)

    def charid(self):
        i = self.char_box.current()
        return self.chars[i][0] if 0 <= i < len(self.chars) else None

    def load_squad(self, select_id=None):
        def go():
            charid = self.charid()
            if charid is None:
                return
            self.mates = sq.get_squad(self.conn, charid)
            self.unlocked = sq.unlocked_jobs(self.conn, charid)
            self.listbox.delete(0, "end")
            for m in self.mates:
                self.listbox.insert("end", sq.describe(m))
            index = 0
            for i, m in enumerate(self.mates):
                if m["id"] == select_id:
                    index = i
            if self.mates:
                self.listbox.selection_clear(0, "end")
                self.listbox.selection_set(index)
                self.on_select()
            else:
                self.mate = None
                self.say("No squad mates yet. Press New to create one.")
        self.guard(go)

    def on_select(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.mates):
            return
        self.mate = self.mates[sel[0]]
        m = self.mate
        self.name_var.set(m["name"])
        self.race_box.current((m["race"] or 1) - 1)  # a mate with no race chosen is a Hume male
        self.face_box.current(min(m["face"], 15))
        self.show_face_picture()
        if self.player:
            fixed = sq.look_locked(self.conn, self.charid(), m["id"])
            for w in (self.race_box, self.face_box):
                w.configure(state="disabled" if fixed else "readonly")
            self.faces_button.configure(state="disabled" if fixed else "normal")
            self.look_button.configure(state="disabled" if fixed else "normal")
            self.look_note.configure(text="This look is set for good." if fixed else
                                     "Pick carefully: a look can be set only once.")
        # Only offer jobs this character has unlocked (plus whatever the mate already has set)
        self.choices = sorted((self.unlocked | {m["mjob"], m["sjob"]}) - {0})
        names = [sq.JOBS[j - 1] for j in self.choices]
        self.mjob_box.configure(values=names)
        self.sjob_box.configure(values=["None"] + names)
        self.mjob_box.current(self.choices.index(m["mjob"]))
        self.sjob_box.current(0 if m["sjob"] == 0 else self.choices.index(m["sjob"]) + 1)
        main, sub, sub_level = sq.effective_levels(m)
        text = f"{sq.JOBS[m['mjob'] - 1]} {main}"
        if sub:
            text += f"  /  {sq.JOBS[sub - 1]} {sub_level}"
        self.summary.configure(text=text)
        # (2026-11-22, krazy: "Cor not gaining EXP": his Corsair levelled in game and this tab kept showing 1) the list
        # stopped at Summoner: Blue Mage, Corsair and Puppetmaster (16-18) never got their level and exp filled in
        for job in range(1, len(sq.JOBS) + 1):
            level, exp = m["jobs"].get(job, (1, 0))
            locked = job not in self.unlocked and job not in m["jobs"]
            self.level_vars[job].set(level)
            self.level_spins[job].configure(state="disabled" if (locked or self.player) else "normal")
            self.level_vars[("exp", job)].configure(text="locked" if locked else (f"{exp} exp" if exp else ""))
            if locked or level >= sq.RAISE_LEVEL:
                self.raise_buttons[job].grid_remove()
            else:
                self.raise_buttons[job].grid()
        self.refresh_gear()
        self.show_behavior()
        self.show_greetings()
        self.show_personality()
        self.say(f"Editing {m['name']}. Changes apply the next time you call them in game.")

    def refresh_gear(self):
        m = self.mate
        job = m["mjob"]
        self.gear_title.configure(text=f"{m['name']} - gear for {sq.JOBS[job - 1]}")
        worn = m["equip"].get(job, {})
        for slot, var in self.gear_vars.items():
            item = worn.get(slot)
            var.set(sq.pretty(item[1]) if item and item[1] else (f"item #{item[0]}" if item else "-"))
            self.gear_items[slot] = item[0] if item else 0
            self._show_gear_icon(slot)

    def gear_stats(self, slot):
        item_id = self.gear_items.get(slot, 0)
        if not item_id or self.conn is None:
            return None
        lines = sq.item_stats(self.conn, item_id, self.cfg.get("server_dir", ""))
        return "\n".join([self.gear_vars[slot].get()] + lines) if lines else None

    def _show_gear_icon(self, slot):
        canvas = self.gear_icons.get(slot)
        if canvas is None:
            return
        item_id = self.gear_items.get(slot, 0)
        try:
            canvas.delete("all")
        except Exception:
            return
        if not item_id or self.icon_loader is None:
            return
        picture = self.icon_loader.get(item_id, lambda p, s=slot, i=item_id: self._paint_gear_icon(s, i, p))
        if picture is not None:
            self._paint_gear_icon(slot, item_id, picture)

    def _paint_gear_icon(self, slot, item_id, picture):
        if self.gear_items.get(slot) != item_id:
            return
        canvas = self.gear_icons.get(slot)
        if canvas is None:
            return
        try:
            canvas.delete("all")
            if picture is not None:
                size = canvas.winfo_reqwidth()
                canvas.create_image(size // 2, size // 2, image=picture)
        except Exception:
            pass

    def reload(self):
        self.load_squad(self.mate["id"] if self.mate else None)

    # ----- actions -----
    def new_mate(self):
        def go():
            charid = self.charid()
            if charid is None:
                raise ValueError("Pick a character first.")
            name = simpledialog.askstring("New squad mate", "Name (3-15 letters):", parent=self)
            if name is None:
                return
            if not (name.isalpha() and 3 <= len(name) <= 15):
                raise ValueError("The name must be 3-15 letters, no spaces or numbers.")
            job = simpledialog.askstring("New squad mate", f"Job for {name} (e.g. WAR, WHM, BLM):", initialvalue="WAR", parent=self)
            if job is None:
                return
            job = job.strip().upper()
            if job not in sq.JOBS:
                raise ValueError("Unknown job. Jobs: " + " ".join(sq.JOBS))
            top = sq.new_mate_max_level(self.conn, charid) if self.player else sq.MAX_LEVEL
            level = 1
            if top > 1:
                level = simpledialog.askinteger("New squad mate", f"Starting level for {name} (1-{top}; after that "
                                                f"they level up by fighting with you):", initialvalue=top,
                                                minvalue=1, maxvalue=top, parent=self)
                if level is None:
                    return
            job_id = sq.JOBS.index(job) + 1
            new_id = sq.create_mate(self.conn, charid, name, job_id, level)
            if lp is not None:                    # squad chat writes their personality, as it does for !squad new
                try:
                    lp.request_ai_sheet(HERE, name, 1, job, level)
                except Exception:
                    pass
            self.load_squad(new_id)
            self.say(f"Created {name} as a level {level} {job}. Set their look and gear on the right.")
        self.guard(go)

    def delete_mate(self):
        if self.mate is None:
            return
        if not messagebox.askyesno("Delete", f"Delete {self.mate['name']} and all of their levels and gear?"):
            return
        self.guard(lambda: (sq.delete_mate(self.conn, self.mate["id"]), self.load_squad()))

    # ----- squad backup and restore (2026-11-24) -----
    def backup_squad(self):
        charid = self.charid()
        if charid is None or self.conn is None:
            return
        import launcher_squad_backup as sb
        folder = os.path.join(HERE, "backups", "squads")
        os.makedirs(folder, exist_ok=True)

        def go():
            data = sb.backup(self.conn, HERE, charid, self.greeting_user)
            if not data["summary"]:
                raise ValueError("This character has no squad mates to back up.")
            path = filedialog.asksaveasfilename(title="Save the squad backup", initialdir=folder,
                                                initialfile=sb.default_name(data["character"]), defaultextension=sb.SUFFIX,
                                                filetypes=[("Squad backup", "*" + sb.SUFFIX)], parent=self)
            if not path:
                return
            path = sb.save(path, data)
            self.say(f"Squad backed up: {sb.describe(data)} -> {path}")
        self.guard(go)

    def restore_squad(self):
        charid = self.charid()
        if charid is None or self.conn is None:
            return
        import launcher_squad_backup as sb
        folder = os.path.join(HERE, "backups", "squads")
        os.makedirs(folder, exist_ok=True)

        def go():
            path = filedialog.askopenfilename(title="Pick a squad backup", initialdir=folder,
                                              filetypes=[("Squad backup", "*" + sb.SUFFIX)], parent=self)
            if not path:
                return
            data = sb.load(path)
            who = self.char_var.get() or "this character"
            if not messagebox.askyesno("Restore squad", f"Put this squad on {who}?\n\n{sb.describe(data)}\n(from {data.get('character', '?')})\n\n"
                                       f"{who}'s squad as it is now is REPLACED. A backup of it is saved first, in "
                                       "backups\\squads. Log the character out before you restore.", parent=self):
                return
            current = sb.backup(self.conn, HERE, charid, self.greeting_user)
            if current["summary"]:
                sb.save(os.path.join(folder, "before-restore-" + sb.default_name(current["character"])), current)
            names = sb.restore(self.conn, HERE, charid, data, self.greeting_user)
            try:
                sq.write_greetings_lua(self.greeting_lua, sq.greeting_data(self.greeting_defaults, self.greeting_user))
            except Exception:
                pass
            self.load_squad()
            self.say(f"Squad restored: {', '.join(names) or 'no mates'}. They come out like this the next time you call them.")
        self.guard(go)

    def apply_name(self):
        def go():
            name = self.name_var.get().strip()
            if not (name.isalpha() and 3 <= len(name) <= 15):
                raise ValueError("The name must be 3-15 letters, no spaces or numbers.")
            old = self.mate["name"]
            sq.rename_mate(self.conn, self.mate["id"], name)
            if old != name:
                sq.rename_greetings(self.greeting_user, old, name)
                sq.write_greetings_lua(self.greeting_lua, sq.greeting_data(self.greeting_defaults, self.greeting_user))
                if lp is not None:
                    lp.request_rename(HERE, old, name)     # squad chat moves the personality and memory along
            self.reload()
        if self.mate:
            self.guard(go)

    def show_face_picture(self):
        """The picture next to the Race/Face boxes: what the chosen look will be."""
        race = self.race_box.current() + 1
        face = self.face_box.current()
        photo = face_photo(race, face, 133, 124)
        self.face_photo = photo
        self.face_picture.configure(image=photo if photo else "", text="" if photo else "(no picture)", fg=DIM)

    def show_faces(self):
        """Every face of the chosen race as a picture grid (A faces on top, B below); a click picks it."""
        race = self.race_box.current() + 1
        win = tk.Toplevel(self)
        win.title(f"Faces - {sq.RACES[race - 1]}")
        win.configure(bg=BG)
        win.transient(self.winfo_toplevel())
        tk.Label(win, text="Click a face to pick it, then press Apply look.", bg=BG, fg=DIM).grid(
            row=0, column=0, columnspan=8, pady=(8, 4))
        win.photos = []
        for face in range(16):
            photo = face_photo(race, face, 133, 124)
            win.photos.append(photo)
            col, row = face // 2, 1 + (face % 2) * 2
            b = tk.Button(win, image=photo if photo else "", text="" if photo else FACE_LABELS[face], relief="flat",
                          bg=PANEL, activebackground=ACCENT, bd=0, cursor="hand2",
                          command=lambda f=face: (self.face_box.current(f), self.show_face_picture(), win.destroy()))
            if face == self.face_box.current():
                b.configure(bg=ACCENT)
            b.grid(row=row, column=col, padx=3, pady=(3, 0))
            tk.Label(win, text=FACE_LABELS[face], bg=BG, fg=FG).grid(row=row + 1, column=col)
        tk.Label(win, text="Pictures: FINAL FANTASY XI character creation (\u00a9 SQUARE ENIX)", bg=BG, fg=DIM,
                 font=(UI_FONT, 8)).grid(row=5, column=0, columnspan=8, pady=(6, 8))

    def apply_look(self):
        def go():
            charid, mate_id = self.charid(), self.mate["id"]
            if self.player:
                if sq.look_locked(self.conn, charid, mate_id):
                    raise ValueError(f"{self.mate['name']}'s look is already set for good.")
                if not messagebox.askyesno("Set look", f"Set {self.mate['name']}'s look for good? It can't be changed later."):
                    return
            sq.set_look(self.conn, mate_id, self.race_box.current() + 1, self.face_box.current())
            if self.player:
                sq.lock_look(self.conn, charid, mate_id)
            self.reload()
        if self.mate:
            self.guard(go)

    def apply_jobs(self):
        if self.mate:
            si = self.sjob_box.current()
            mjob = self.choices[self.mjob_box.current()]
            sjob = 0 if si <= 0 else self.choices[si - 1]
            self.guard(lambda: (sq.set_jobs(self.conn, self.charid(), self.mate["id"], mjob, sjob), self.reload()))

    def apply_levels(self):
        if self.player:
            return
        def go():
            for job in range(1, len(sq.JOBS) + 1):      # (was 1-15: the three Aht Urhgan jobs were never saved)
                if job not in self.unlocked and job not in self.mate["jobs"]:
                    continue
                level = int(self.level_vars[job].get())
                old = self.mate["jobs"].get(job, (1, 0))
                if level != old[0]:
                    sq.set_job_level(self.conn, self.mate["id"], job, level, 0)
            self.reload()
        if self.mate:
            self.guard(go)

    def raise_job(self, job):
        """(2026-11-24, levi) the Job levels page's "Raise to 12": one unlocked job straight to level 12, exp from 0."""
        m = self.mate
        if m is None:
            return
        name, target = sq.JOBS[job - 1], sq.RAISE_LEVEL
        if job not in self.unlocked and job not in m["jobs"]:
            messagebox.showinfo("Squad", f"{name} has not been unlocked on this character yet.")
            return
        level = m["jobs"].get(job, (1, 0))[0]
        if level >= target:
            return
        if not messagebox.askyesno("Raise job", f"Raise {m['name']}'s {name} from level {level} to {target}?\n\n"
                                   f"Their {name} exp starts over at {target}. If {m['name']} is out in the game now, "
                                   "dismiss and call them again to use the new level."):
            return

        def go():
            sq.raise_job_level(self.conn, m["id"], job, target)
            self.reload()
            self.say(f"{m['name']}'s {name} is now level {target}.")
        self.guard(go)

    def pick_item(self, slot, label):
        if self.mate is None:
            return
        m = self.mate
        main, _sub, _sl = sq.effective_levels(m)

        def chosen(item_id):
            self.guard(lambda: (sq.set_equip(self.conn, m["id"], m["mjob"], slot, item_id), self.reload()))

        # (2026-11-21, Tasou) the Rules page's "Squad gets all gear" counts as soon as it is ticked, not only after PLAY
        live = getattr(self, "all_gear_var", None)
        need_unlock = self.require_unlock and not (live is not None and bool(live.get()))
        ItemPicker(self, self.conn, slot, label, m["mjob"], main, self.charid(), need_unlock, chosen,
                   icon_loader=self.icon_loader)

    def clear_item(self, slot):
        if self.mate:
            self.guard(lambda: (sq.set_equip(self.conn, self.mate["id"], self.mate["mjob"], slot, 0), self.reload()))


class ImageButton(tk.Canvas):
    """A button drawn from pictures: normal, hover and off. Falls back to plain text if the pictures are missing."""

    def __init__(self, parent, images, command, fallback_text):
        normal = images.get("normal")
        width, height = (normal.width(), normal.height()) if normal else (200, 48)
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0, cursor="hand2")
        self.imgs, self.command, self.state, self.hover, self.fallback_text = images, command, "normal", False, fallback_text
        self.active = False
        if normal:
            self.item = self.create_image(0, 0, anchor="nw", image=normal)
        else:
            self.item = self.create_text(width // 2, height // 2, text=fallback_text, fill=FG, font=(UI_FONT, 12, "bold"))
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    def _set_hover(self, value):
        self.hover = value
        self._show()

    def set_active(self, value):
        """Lit all the time, as if the pointer were on it: the button of the page that is open."""
        self.active = bool(value)
        self._show()

    def _show(self):
        key = "off" if self.state == "disabled" else ("hover" if (self.hover or self.active) else "normal")
        img = self.imgs.get(key) or self.imgs.get("normal")
        if img:
            self.itemconfigure(self.item, image=img)
        else:
            self.itemconfigure(self.item, fill=DIM if self.state == "disabled" else (ACCENT if (self.hover or self.active) else FG))
        tk.Canvas.configure(self, cursor="arrow" if self.state == "disabled" else "hand2")

    def _click(self, _event):
        if self.state != "disabled" and self.command:
            self.command()

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self.state = kw.pop("state")
            self._show()
        if cnf or kw:
            return tk.Canvas.configure(self, cnf, **kw)

    config = configure


class RatesTab(tk.Frame):
    """Experience, drop, gil and skill-up rates, the level cap and a few switches. Read when PLAY is pressed.
    In the newer look this tab is made but not shown: the World, Rules, Squad and Era pages (launcher_pages.py) show
    its variables. A NEW SETTING ALSO NEEDS A LINE IN launcher_settings.py, which says where it goes on those pages
    (dev\\launcher-tests\\test_settings.py fails until it has one)."""
    FAST_TRAVEL = ("main.HOMEPOINT_TELEPORT", "main.ENABLE_SURVIVAL_GUIDE")   # one "Fast travel" checkbox for both
    # (2026-11-18) settings about the era and how classic the game feels, shown together under "Era options"
    ERA_KEYS = ("main.MAX_LEVEL", "main.ENABLE_COP", "main.ENABLE_TOAU", "main.ENABLE_WOTG", "main.ENABLE_ACP", "main.ENABLE_AMK",
                "main.ENABLE_ASA", "main.ENABLE_ABYSSEA", "main.ENABLE_SOA", "main.ENABLE_ROV", "main.ENABLE_VOIDWATCH",
                "main.ENABLE_TVR", "main.RESTRICT_CONTENT", "main.ENABLE_TRUST_QUESTS", "main.ENABLE_DAILY_TALLY",
                "main.HALLOWEEN_2005", "main.NEW_CHARACTER_CUTSCENE", "map.BASE_SPEED", "map.MOUNT_SPEED")

    def __init__(self, parent, rates, player=False):
        super().__init__(parent, bg=BG)
        self.vars, self.rates, self.player = {}, rates, player      # player: a player install shows only the era options
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Preset:", bg=BG, fg=FG).pack(side="left")
        self.preset = ttk.Combobox(top, values=core.PLAYER_RATE_PRESETS if player else [p for p in core.RATE_PRESETS if p != "Era default"],
                                   state="readonly", width=22)
        self.preset.pack(side="left", padx=6)
        tk.Button(top, text="Fill in preset", command=self.fill_preset, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left")
        # (2026-11-18) your own rate builds: save them under a name, load them later, share them as .txt files
        prof = tk.Frame(self, bg=BG)
        prof.pack(fill="x", padx=10, pady=(2, 2))
        tk.Label(prof, text="Profile:", bg=BG, fg=FG).pack(side="left")
        self.profile = ttk.Combobox(prof, values=core.list_profiles(HERE), state="readonly", width=22)
        self.profile.pack(side="left", padx=6)
        for text, cmd in (("Load", self.load_profile), ("Save as...", self.save_profile), ("Import...", self.import_profile),
                          ("Export...", self.export_profile)):
            tk.Button(prof, text=text, command=cmd, bg=PANEL, fg=FG, relief="flat", padx=6).pack(side="left", padx=(0, 3))
        tk.Label(prof, text="your own rate builds, shareable as .txt files", bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(side="left", padx=6)
        world = tk.Frame(self, bg=BG)
        world.pack(fill="x", padx=10, pady=(2, 2))
        tk.Label(world, text="World:", bg=BG, fg=FG).pack(side="left")
        self.world_names = {key: label for key, (label, _text) in core.WORLDS.items()}
        self.world_box = ttk.Combobox(world, values=list(self.world_names.values()) + ["Custom"], state="readonly", width=22)
        self.world_box.pack(side="left", padx=6)
        tk.Label(world, text="Population:", bg=BG, fg=FG).pack(side="left", padx=(8, 0))
        self.pop_names = {key: f"{label} ({crowd} per town, {online} bots online)" for key, (label, crowd, _roster, online) in core.POPULATIONS.items()}
        self.pop_box = ttk.Combobox(world, values=list(self.pop_names.values()) + ["Custom"], state="readonly", width=30)
        self.pop_box.pack(side="left", padx=6)
        tk.Button(world, text="Fill in", command=self.fill_world, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left")
        self.world_text = tk.Label(self, text="", bg=BG, fg=DIM, font=(UI_FONT, 9), wraplength=720, justify="left")
        self.world_text.pack(anchor="w", padx=10)
        self.world_box.bind("<<ComboboxSelected>>", lambda e: self.show_world_text())
        tk.Label(self, text="Changes apply the next time you press PLAY. 1 = normal game speed.", bg=BG, fg=DIM,
                 font=(UI_FONT, 9)).pack(anchor="w", padx=10)

        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", expand=True, padx=6, pady=4)
        canvas = tk.Canvas(box, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        row, era_fields = 0, []
        for field in core.RATE_FIELDS:
            hidden = player and field[0] in core.PLAYER_HIDDEN_RATES
            var = tk.StringVar(value=str(field[4] if hidden else rates.get(field[0], field[4])))
            self.vars[field[0]] = var
            if hidden or field[0] in self.FAST_TRAVEL:   # (fast travel: one checkbox below sets both)
                continue
            if field[0] in self.ERA_KEYS:
                era_fields.append(field)
                continue
            tk.Label(inner, text=field[3], bg=BG, fg=FG, anchor="w", width=38).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            ttk.Spinbox(inner, from_=field[5], to=field[6], increment=1 if field[7] == "int" else 0.25,
                        textvariable=var, width=8).grid(row=row, column=1, padx=6, pady=2)
            row += 1

        # (2026-11-18) sections: the rates above, then Era options, World, Squad and AI. R[k] is the row of what used to
        # be row n + k (the old single list), so each widget below only says which slot it fills.
        R = {}
        def header(title, at):
            tk.Label(inner, text=title, bg=BG, fg=GOLD, font=(UI_FONT, 11, "bold"),
                     anchor="w").grid(row=at, column=0, columnspan=2, sticky="w", padx=6, pady=(14, 2))
            return at + 1
        row = header("Era options", row)
        for field in era_fields:
            var = self.vars[field[0]]
            tk.Label(inner, text=field[3], bg=BG, fg=FG, anchor="w", width=38).grid(row=row, column=0, sticky="w", padx=6, pady=2)
            ttk.Spinbox(inner, from_=field[5], to=field[6], increment=1 if field[7] == "int" else 0.25,
                        textvariable=var, width=8).grid(row=row, column=1, padx=6, pady=2)
            row += 1
        for k in (2, 20, 18, 25, 23, 0, 24, 30, 31, 32, 33, 34):    # era exp tables, fast travel, full bags, item stacks, short quest waits, all crafts, seasonal events
            R[k], row = row, row + 1
        row = header("World", row)
        # (34-35: crowd members through the gates / stopping for each other; 36-39: bot players' emotes, death memory,
        #  life stories, gate travel - the 2026-11-21 additions, extras.lua)
        for k in (3, 1, 4, 5, 34, 35, 6, 7, 8, 9, 10, 11, 12, 13, 14, 28, 36, 37, 38, 39):   # (28: bots pass all loot)
            R[k], row = row, row + 1
        row = header("Squad and AI", row)
        for k in (15, 16, 19, 26, 29, 27, 21, 22, 17, 40):   # (26: squad gear, you keep the item; 29: all gear; 27: training dummies; 40: buff range)
            R[k], row = row, row + 1
        self.all_crafts = tk.BooleanVar(value=rates.get("all_crafts", True))
        tk.Checkbutton(inner, text="Every craft can reach 100 (off = only one, like the retail rule)", variable=self.all_crafts, bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG).grid(row=R[0], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.ah_sim = tk.BooleanVar(value=rates.get("ah_sim", False))
        tk.Checkbutton(inner, text="Auction house simulator (stocks the auction house, buys what you list)", variable=self.ah_sim, bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG).grid(row=R[1], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.era_exp = tk.BooleanVar(value=True if player else rates.get("era_exp", True))
        era_box = tk.Checkbutton(inner, text="Aht Urhgan-era experience tables (kill exp and per-monster cap). Keep 'Experience from monsters' at 1.0 with this on.",
                                 variable=self.era_exp, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                                 wraplength=520, justify="left")
        if not player:                                   # players always have the era tables
            era_box.grid(row=R[2], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.conquest_sim = tk.BooleanVar(value=rates.get("conquest_sim", True))
        tk.Checkbutton(inner, text="Conquest simulator: the other nations and the beastmen act while you are away, so regions can change hands",
                       variable=self.conquest_sim, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[3], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.crowds = tk.BooleanVar(value=rates.get("crowds", True))
        tk.Checkbutton(inner, text="Ambient crowds: adventurers resting, shopping and walking around in towns and outposts",
                       variable=self.crowds, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[4], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        tk.Label(inner, text="Crowd size (adventurers per area, 0-40)", bg=BG, fg=FG, anchor="w", width=38).grid(
            row=R[5], column=0, sticky="w", padx=6, pady=2)
        self.crowds_size = tk.StringVar(value=str(rates.get("crowds_per_zone", 15)))
        ttk.Spinbox(inner, from_=0, to=40, increment=1, textvariable=self.crowds_size, width=8).grid(row=R[5], column=1, padx=6, pady=2)
        self.crowds_chat = tk.BooleanVar(value=rates.get("crowds_chat", True))
        tk.Checkbutton(inner, text="Crowd chat: party-wanted shouts, people selling crafted items, small talk near you",
                       variable=self.crowds_chat, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[6], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        tk.Label(inner, text="Chat amount", bg=BG, fg=FG, anchor="w", width=38).grid(row=R[7], column=0, sticky="w", padx=6, pady=2)
        self.crowds_chat_amount = tk.StringVar(value=rates.get("crowds_chat_amount", "normal"))
        ttk.Combobox(inner, values=["quiet", "normal", "busy"], state="readonly", textvariable=self.crowds_chat_amount,
                     width=8).grid(row=R[7], column=1, padx=6, pady=2)
        self.crowds_chat_ai = tk.BooleanVar(value=rates.get("crowds_chat_ai", True))
        tk.Checkbutton(inner, text="AI chatter: your local Ollama model writes some of the small talk (runs quietly in the background)",
                       variable=self.crowds_chat_ai, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[8], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.crowds_field = tk.BooleanVar(value=rates.get("crowds_field", True))
        self.crowds_field_parties = tk.StringVar(value=str(rates.get("crowds_field_parties", 1)))
        if not player:                                   # players get field parties from their world choice
            tk.Checkbutton(inner, text="Field parties: adventurer parties camping and fighting monsters out in the field (away from you)",
                           variable=self.crowds_field, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                           wraplength=520, justify="left").grid(row=R[9], column=0, columnspan=2, sticky="w", padx=6, pady=2)
            tk.Label(inner, text="Field parties per area (0-3)", bg=BG, fg=FG, anchor="w", width=38).grid(
                row=R[10], column=0, sticky="w", padx=6, pady=2)
            ttk.Spinbox(inner, from_=0, to=3, increment=1, textvariable=self.crowds_field_parties, width=8).grid(row=R[10], column=1, padx=6, pady=2)
        self.bots = tk.BooleanVar(value=rates.get("bots", True))
        tk.Checkbutton(inner, text="Bot players: real characters (no game window) living in the nation towns - /sea, /check, invite them",
                       variable=self.bots, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[11], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        tk.Label(inner, text="Bot roster (characters, 0-%d)" % core.BOTS_ROSTER_SAFE, bg=BG, fg=FG, anchor="w", width=38).grid(
            row=R[12], column=0, sticky="w", padx=6, pady=2)
        self.bots_roster = tk.StringVar(value=str(rates.get("bots_roster", 100)))
        ttk.Spinbox(inner, from_=0, to=core.BOTS_ROSTER_MAX, increment=50, textvariable=self.bots_roster, width=8).grid(row=R[12], column=1, padx=6, pady=2)
        tk.Label(inner, text="Bots online (0-%d; at most 60%% of the roster)" % core.BOTS_ONLINE_SAFE, bg=BG, fg=FG, anchor="w", width=42).grid(
            row=R[13], column=0, sticky="w", padx=6, pady=2)
        self.bots_online = tk.StringVar(value=str(rates.get("bots_online", 50)))
        ttk.Spinbox(inner, from_=0, to=core.BOTS_ONLINE_MAX, increment=10, textvariable=self.bots_online, width=8).grid(row=R[13], column=1, padx=6, pady=2)
        # (2026-11-23, Meli) past the usual top value only after a warning (once per launcher session); "No" puts it back
        self._bots_past_safe = False

        def past_safe(var, safe, what):
            def check(*_):
                try:
                    value = int(float(var.get()))
                except (TypeError, ValueError):
                    return
                if value <= safe or self._bots_past_safe:
                    return
                if messagebox.askyesno("More bots than usual",
                                       f"{value} {what} is more than the usual {safe}.\n\nEvery bot online is a character the "
                                       "server moves, fights and talks for. Above the usual numbers a strong PC copes, "
                                       "but the server can lag (monsters and mates react late) and starting takes longer.\n\n"
                                       "Go past the usual top value?", icon="warning", parent=inner):
                    self._bots_past_safe = True
                else:
                    var.set(str(safe))
            var.trace_add("write", check)

        past_safe(self.bots_roster, core.BOTS_ROSTER_SAFE, "bot characters")
        past_safe(self.bots_online, core.BOTS_ONLINE_SAFE, "bots online")
        tk.Label(inner, text="Bots grow while you are away", bg=BG, fg=FG, anchor="w", width=38).grid(row=R[14], column=0, sticky="w", padx=6, pady=2)
        self.bots_growth = tk.StringVar(value=rates.get("bots_growth", "realistic"))
        ttk.Combobox(inner, values=["off", "realistic", "fast"], state="readonly", textvariable=self.bots_growth,
                     width=8).grid(row=R[14], column=1, padx=6, pady=2)
        self.squad_chat = tk.BooleanVar(value=rates.get("squad_chat", True))
        tk.Checkbutton(inner, text="Squad mates talk: they answer you in party chat with the local AI (Ollama), each with their own personality",
                       variable=self.squad_chat, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[15], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        tk.Label(inner, text="Squad call timer (minutes, 0-30)", bg=BG, fg=FG, anchor="w", width=38).grid(row=R[16], column=0, sticky="w", padx=6, pady=2)
        self.squad_call_cooldown = tk.StringVar(value=str(rates.get("squad_call_cooldown", 5)))
        ttk.Spinbox(inner, from_=0, to=30, increment=1, textvariable=self.squad_call_cooldown, width=8).grid(
            row=R[16], column=1, padx=6, pady=2)
        tk.Label(inner, text="Buff range (retail or extended)", bg=BG, fg=FG, anchor="w", width=38).grid(row=R[40], column=0, sticky="w", padx=6, pady=2)
        self.buff_range = tk.StringVar(value=rates.get("buff_range", "retail") if rates.get("buff_range") in core.BUFF_RANGES else "retail")
        ttk.Combobox(inner, values=list(core.BUFF_RANGES), state="readonly", textvariable=self.buff_range, width=8).grid(
            row=R[40], column=1, padx=6, pady=2)
        # One time per server: once a PLAY has used it, the switch is gone for good
        self.head_start_done = bool(rates.get("bots_head_start_done", False))
        self.bots_head_start = tk.BooleanVar(value=bool(rates.get("bots_head_start", False)) and not self.head_start_done)
        if not self.head_start_done:
            tk.Checkbutton(inner, text="Bot head start (one time): the starting bots get a few months of history - levels 1-75 "
                           "(most 10-30), subjobs, crafts, gil, gear - as if the server had been running a while. "
                           "Used at your next PLAY, then this switch goes away.",
                           variable=self.bots_head_start, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                           wraplength=520, justify="left").grid(row=R[17], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.full_bags = tk.BooleanVar(value=rates.get("full_bags", True))
        tk.Checkbutton(inner, text="Full bags from the start: inventory, Mog Safe, Mog Satchel, Mog Sack, Mog Case and every "
                       "Mog Wardrobe open at 80. Off = the classic way: 30 slots, and the Gobbiebag quests (and Phoenix's "
                       "wardrobe rewards) add space. Bags never shrink.",
                       variable=self.full_bags, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[18], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.modern_stacks = tk.BooleanVar(value=rates.get("modern_stacks", True))
        tk.Checkbutton(inner, text="Modern item stacks: items stack as in today's game (sheepskin, goblin helms and the like "
                       "to 12, and some to 99). Off = the era: most of those don't stack at all. Empty or split your stacks "
                       "of those items before switching this off.",
                       variable=self.modern_stacks, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[25], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        on = all(str(self.vars[k].get()).strip() not in ("0", "0.0") for k in self.FAST_TRAVEL)
        self.fast_travel = tk.BooleanVar(value=on)
        tk.Checkbutton(inner, text="Fast travel: Home Point and Survival Guide teleports (touch one once, then teleport to it "
                       "for a fee). Off = classic travel: walk, chocobos, airships and Teleport spells.",
                       variable=self.fast_travel, command=self.set_fast_travel, bg=BG, fg=FG, selectcolor=PANEL,
                       activebackground=BG, activeforeground=FG, wraplength=520, justify="left").grid(
                       row=R[20], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.spell_scrolls = tk.BooleanVar(value=rates.get("spell_scrolls", False))
        tk.Checkbutton(inner, text="Squad mates learn spells from scrolls: spells of level 18 and up must be bought and given "
                       "to your squad once (trade the scroll to a mate, or !squad give). Blue magic from 18 is learned "
                       "from monsters you defeat with a squad Blue Mage out. Below 18 everything stays automatic. "
                       "Always on for Randomized characters.",
                       variable=self.spell_scrolls, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[19], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.squad_keep_gear = tk.BooleanVar(value=rates.get("squad_keep_gear", False))
        tk.Checkbutton(inner, text="Squad gear: you keep the item. Trading a piece to a mate (or !squad give) unlocks it for "
                       "the whole squad and you keep yours. Off = the squad takes the piece (one-of-a-kind gear is always kept).",
                       variable=self.squad_keep_gear, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[26], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.bots_pass_loot = tk.BooleanVar(value=rates.get("bots_pass_loot", True))
        tk.Checkbutton(inner, text="Bots pass all loot: bot players in your party pass every drop at once, so it comes to "
                       "you without waiting for the lot timer. Off = they leave it to the timer.",
                       variable=self.bots_pass_loot, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[28], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        # (2026-11-21) one switch each for the crowd and bot player additions (extras.lua; in game: !extras)
        for slot, key, text in (
                (34, "crowd_gates", "Crowds use the gates: newcomers walk in from the zone lines and Mog House doors, and people "
                                    "leaving walk out through them or warp from the Home Point. Off = they appear and fade by the Home Point."),
                (35, "crowd_meet", "Crowds stop for each other: two adventurers walking past each other may stop, turn and wave."),
                (36, "bot_social", "Bot emotes: bot players cheer level ups, bow when they join you, wave goodbye, panic when "
                                   "badly hurt, and trade emotes with each other in town."),
                (37, "bot_memory", "Bots remember where they died: after dying twice in an area a bot hunts somewhere else for a "
                                   "while, and it keeps away from the camp it died at."),
                (38, "bot_story", "Bot life stories: each bot keeps its milestones between play sessions (!bots story Name), so "
                                  "in a chat it still knows what it did yesterday."),
                (39, "bot_gates", "Bots use the town gates: a bot going hunting runs to the gate first, and one coming home "
                                  "arrives at the gate and walks in. Off = they leave from and return to their spot.")):
            var = tk.BooleanVar(value=rates.get(key, True))
            setattr(self, key, var)
            tk.Checkbutton(inner, text=text, variable=var, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                           activeforeground=FG, wraplength=520, justify="left").grid(
                           row=R[slot], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.squad_all_gear = tk.BooleanVar(value=rates.get("squad_all_gear", False))
        tk.Checkbutton(inner, text="Squad gets all gear: mates can wear anything their job and level allow without it being "
                       "given to them first. Off = gear has to be given once (trade it, or !squad give).",
                       variable=self.squad_all_gear, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[29], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.training_dummies = tk.BooleanVar(value=rates.get("training_dummies", True))
        self.training_dummies_explicit = bool(rates.get("training_dummies_explicit", False))   # set once the player flips the switch
        self.training_dummies.trace_add("write", lambda *_: setattr(self, "training_dummies_explicit", True))
        tk.Checkbutton(inner, text="Training dummies (for testing): !sandbox puts dummies of level 1 to 99 in Rolanberry "
                       "Fields that never die and never attack, to try out squads and gambits. On by default; off = no dummies.",
                       variable=self.training_dummies, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[27], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        self.short_quest_waits = tk.BooleanVar(value=rates.get("short_quest_waits", True))
        tk.Checkbutton(inner, text="Short quest waits: Chocobo's Wounds 1 minute between feedings (era: a game day each), "
                       "Forge Your Destiny 1 hour at the forge (era: three game days), Aht Urhgan missions about 1 minute "
                       "between missions. Off = the era waits.",
                       variable=self.short_quest_waits, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       wraplength=520, justify="left").grid(row=R[23], column=0, columnspan=2, sticky="w", padx=6, pady=2)
        # (2026-11-18) seasonal events: by their dates (default), all year, or none (events_mode.lua)
        tk.Label(inner, text="Seasonal events (Harvest Festival, Starlight, Egg Hunt, Horro's Visit, Sunbreeze)", bg=BG, fg=FG,
                 anchor="w", width=38, wraplength=300, justify="left").grid(row=R[24], column=0, sticky="w", padx=6, pady=2)
        self.events = tk.StringVar(value=self.EVENTS_LABELS[core.clean_events(rates.get("events", "date"))])
        ttk.Combobox(inner, values=list(self.EVENTS_LABELS.values()), state="readonly", textvariable=self.events,
                     width=16).grid(row=R[24], column=1, padx=6, pady=2)
        # (2026-11-20) one switch per event: on = it runs on its dates (or all year with "Always on"), off = never
        for slot, key, name in ((30, "event_harvest", "Harvest Festival"), (31, "event_starlight", "Starlight Celebration"),
                                (32, "event_egg_hunt", "Egg Hunt"), (33, "event_horro", "Horro's Visit"),
                                (34, "event_sunbreeze", "Sunbreeze Festival")):
            var = tk.BooleanVar(value=rates.get(key, True))
            setattr(self, key, var)
            tk.Checkbutton(inner, text="   " + name, variable=var, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                           activeforeground=FG).grid(row=R[slot], column=0, columnspan=2, sticky="w", padx=6, pady=1)
        if tp is not None:
            self.ai_model_row(inner, R[21])
        self.show_world(rates)

    def ai_model_row(self, inner, row):
        """(Meli, 2026-11-18) which local AI model squad chat and the town/bot chat use: a suggested one, any Ollama
        model name, or your own .gguf file. Saved in squad-chat/config.json right away; used from the next PLAY."""
        tk.Label(inner, text="AI chat model (Ollama)", bg=BG, fg=FG, anchor="w", width=38).grid(row=row, column=0, sticky="w", padx=6, pady=2)
        box = tk.Frame(inner, bg=BG)
        box.grid(row=row, column=1, sticky="w", padx=6, pady=2)
        self.ai_model = tk.StringVar(value=tp.chat_model(HERE))
        names = [m for m, _ in tp.SUGGESTED_MODELS]
        ttk.Combobox(box, values=names, textvariable=self.ai_model, width=22).pack(side="left")
        tk.Button(box, text="Use and download", command=self.use_ai_model, bg=PANEL, fg=FG, relief="flat", padx=6).pack(side="left", padx=4)
        tk.Button(box, text="Use a .gguf file...", command=self.use_gguf, bg=PANEL, fg=FG, relief="flat", padx=6).pack(side="left")
        hints = "; ".join(f"{m} ({t})" for m, t in tp.SUGGESTED_MODELS)
        self.ai_model_note = tk.Label(inner, text="Bigger models chat better but need more video memory and can lower your "
                                      "frame rate. Any model from ollama.com/library works. " + hints,
                                      bg=BG, fg=FG, wraplength=520, justify="left", anchor="w")
        self.ai_model_note.grid(row=row + 1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 4))

    def _ai_work(self, job, done_text):
        def work():
            try:
                name = job()
                self.after(0, lambda: messagebox.showinfo("AI model", done_text.format(name=name)))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: messagebox.showerror("AI model", err))
        threading.Thread(target=work, daemon=True).start()

    def use_ai_model(self):
        model = self.ai_model.get().strip()
        try:
            tp.set_chat_model(model, HERE)
        except ValueError as e:
            messagebox.showerror("AI model", str(e))
            return
        if model in tp.ollama_models():
            messagebox.showinfo("AI model", f"Squad and town chat will use {model} from your next PLAY.")
            return
        self.ai_model_note.configure(text=f"Downloading {model} (several GB; you can keep using the launcher)...")
        def job():
            tp.pull_model(model, log=lambda line: self.after(0, lambda: self.ai_model_note.configure(text=line)))
            return model
        self._ai_work(job, "{name} is downloaded. Squad and town chat use it from your next PLAY.")

    def use_gguf(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Pick a .gguf model file", filetypes=[("GGUF model", "*.gguf")])
        if not path:
            return
        self.ai_model_note.configure(text="Importing the model into Ollama...")
        def job():
            name = tp.import_gguf(path, log=lambda line: self.after(0, lambda: self.ai_model_note.configure(text=line)))
            tp.set_chat_model(name, HERE)
            self.after(0, lambda: self.ai_model.set(name))
            return name
        self._ai_work(job, "Your model is in Ollama as {name}. Squad and town chat use it from your next PLAY.")

    def show_world(self, rates):
        """Show which world and population the switches below match (or Custom)."""
        world, population = core.world_of(rates), core.population_of(rates)
        self.world_box.set(self.world_names.get(world, "Custom"))
        self.pop_box.set(self.pop_names.get(population, "Custom"))
        self.show_world_text()

    def show_world_text(self):
        key = next((k for k, v in self.world_names.items() if v == self.world_box.get()), None)
        self.world_text.configure(text=core.WORLDS[key][1] if key else "Your own mix of the switches below.")

    def fill_world(self):
        """Fill in the crowd, bot and chat switches below from the chosen world and population."""
        world = next((k for k, v in self.world_names.items() if v == self.world_box.get()), None)
        population = next((k for k, v in self.pop_names.items() if v == self.pop_box.get()), None)
        values = core.apply_world(self.collect(), world, population)
        for key in ("crowds", "crowds_chat", "crowds_chat_ai", "crowds_field", "bots", "squad_chat"):
            getattr(self, key).set(bool(values[key]))
        if values.get("ah_sim"):
            self.ah_sim.set(True)
        self.crowds_size.set(str(values["crowds_per_zone"]))
        self.bots_roster.set(str(values["bots_roster"]))
        self.bots_online.set(str(values["bots_online"]))
        self.show_world(values)

    def fill_preset(self):
        name = self.preset.get()
        if not name:
            return
        values = core.apply_preset(self.collect(), name)
        for fid, var in self.vars.items():
            var.set(str(values.get(fid)))
        self.era_exp.set(bool(values.get("era_exp", True)))
        self.fast_travel.set(all(str(values.get(k, 1)) not in ("0", "0.0") for k in self.FAST_TRAVEL))

    EVENTS_LABELS = {"date": "By date", "on": "Always on", "off": "Off"}

    def events_value(self):
        label = self.events.get()
        return next((k for k, v in self.EVENTS_LABELS.items() if v == label), "date")

    BOOL_KEYS = ("all_crafts", "ah_sim", "era_exp", "conquest_sim", "crowds", "crowds_chat", "crowds_chat_ai", "crowds_field",
                 "bots", "squad_chat", "full_bags", "modern_stacks", "spell_scrolls", "squad_keep_gear", "training_dummies", "bots_pass_loot", "squad_all_gear", "short_quest_waits",
                 "event_harvest", "event_starlight", "event_egg_hunt", "event_horro", "event_sunbreeze") + tuple(core.EXTRAS_KEYS)
    TEXT_KEYS = (("crowds_per_zone", "crowds_size"), ("crowds_chat_amount", "crowds_chat_amount"),
                 ("crowds_field_parties", "crowds_field_parties"), ("bots_roster", "bots_roster"), ("bots_online", "bots_online"),
                 ("bots_growth", "bots_growth"), ("buff_range", "buff_range"), ("squad_call_cooldown", "squad_call_cooldown"))

    def apply_values(self, values):
        """Puts a whole set of settings (a loaded profile) into the tab. Nothing is saved until PLAY."""
        for fid, var in self.vars.items():
            if fid in values and not (self.player and fid in core.PLAYER_HIDDEN_RATES):
                var.set(str(values[fid]))
        for key in self.BOOL_KEYS:
            if key in values and hasattr(self, key):
                getattr(self, key).set(bool(values[key]))
        for key, attr in self.TEXT_KEYS:
            if key in values and hasattr(self, attr):
                getattr(self, attr).set(str(values[key]))
        if "events" in values and hasattr(self, "events"):
            self.events.set(self.EVENTS_LABELS[core.clean_events(values["events"])])
        self.fast_travel.set(all(str(self.vars[k].get()) not in ("0", "0.0") for k in self.FAST_TRAVEL))
        self.show_world(self.collect())

    def refresh_profiles(self, select=None):
        self.profile.configure(values=core.list_profiles(HERE))
        if select:
            self.profile.set(select)

    def load_profile(self):
        name = self.profile.get()
        if not name:
            messagebox.showinfo("Rate profiles", "Pick a profile first (Save as... makes one from the settings below).")
            return
        try:
            values = core.load_profile(HERE, name)
        except Exception as e:
            messagebox.showerror("Rate profiles", f"Could not read {name}: {e}")
            return
        self.apply_values(values)
        messagebox.showinfo("Rate profiles", f"Loaded {name}. It is used from your next PLAY.")

    def save_profile(self):
        name = simpledialog.askstring("Save rate profile", "Name for these settings (for example 2x rates or WotG era):",
                                      initialvalue=self.profile.get() or "", parent=self)
        if not name:
            return
        try:
            core.save_profile(HERE, name, self.collect())
        except ValueError as e:
            messagebox.showerror("Rate profiles", str(e))
            return
        self.refresh_profiles(name.strip())

    def import_profile(self):
        path = filedialog.askopenfilename(title="Import a rate profile", filetypes=[("Rate profile", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            name = core.import_profile(HERE, path)
        except Exception as e:
            messagebox.showerror("Rate profiles", f"That file is not a rate profile ({e}).")
            return
        self.refresh_profiles(name)
        messagebox.showinfo("Rate profiles", f"Imported {name}. Press Load to use it.")

    def export_profile(self):
        name = self.profile.get() or "My rates"
        path = filedialog.asksaveasfilename(title="Export a rate profile", defaultextension=".txt", initialfile=name + ".txt",
                                            filetypes=[("Rate profile", "*.txt")])
        if not path:
            return
        values = core.load_profile(HERE, name) if self.profile.get() else self.collect()
        with open(path, "w", encoding="utf-8") as f:
            f.write(core.profile_text(name, values))
        messagebox.showinfo("Rate profiles", f"Saved {os.path.basename(path)}. Share it: others use Import... to add it.")

    def set_fast_travel(self):
        value = "1" if self.fast_travel.get() else "0"
        for key in self.FAST_TRAVEL:
            self.vars[key].set(value)

    def collect(self):
        rates = dict(core.RATE_DEFAULTS)
        for field in core.RATE_FIELDS:
            rates[field[0]] = core.clean_rate(field, self.vars[field[0]].get())
        rates["all_crafts"] = bool(self.all_crafts.get())
        rates["ah_sim"] = bool(self.ah_sim.get())
        rates["era_exp"] = bool(self.era_exp.get())
        rates["conquest_sim"] = bool(self.conquest_sim.get())
        rates["crowds"] = bool(self.crowds.get())
        rates["crowds_per_zone"] = core.clean_crowd_size(self.crowds_size.get())
        rates["crowds_chat"] = bool(self.crowds_chat.get())
        amount = self.crowds_chat_amount.get()
        rates["crowds_chat_amount"] = amount if amount in ("quiet", "normal", "busy") else "normal"
        rates["crowds_chat_ai"] = bool(self.crowds_chat_ai.get())
        rates["crowds_field"] = bool(self.crowds_field.get())
        try:
            rates["crowds_field_parties"] = max(0, min(3, int(float(self.crowds_field_parties.get()))))
        except (TypeError, ValueError):
            rates["crowds_field_parties"] = 1
        rates["bots"] = bool(self.bots.get())
        growth = self.bots_growth.get()
        rates["bots_growth"] = growth if growth in ("off", "realistic", "fast") else "realistic"
        buff = self.buff_range.get()
        rates["buff_range"] = buff if buff in core.BUFF_RANGES else "retail"
        for key, var, lo, hi, default in (("bots_roster", self.bots_roster, 0, core.BOTS_ROSTER_MAX, 100),
                                          ("bots_online", self.bots_online, 0, core.BOTS_ONLINE_MAX, 50)):
            try:
                rates[key] = max(lo, min(hi, int(float(var.get()))))
            except (TypeError, ValueError):
                rates[key] = default
        rates["squad_chat"] = bool(self.squad_chat.get())
        rates["squad_call_cooldown"] = core.clean_call_cooldown(self.squad_call_cooldown.get())
        rates["full_bags"] = bool(self.full_bags.get())
        rates["modern_stacks"] = bool(self.modern_stacks.get())
        rates["spell_scrolls"] = bool(self.spell_scrolls.get())
        rates["squad_keep_gear"] = bool(self.squad_keep_gear.get())
        rates["training_dummies"] = bool(self.training_dummies.get())
        rates["training_dummies_explicit"] = bool(self.training_dummies_explicit)
        rates["bots_pass_loot"] = bool(self.bots_pass_loot.get())
        for k in core.EXTRAS_KEYS:
            rates[k] = bool(getattr(self, k).get())
        rates["squad_all_gear"] = bool(self.squad_all_gear.get())
        rates["short_quest_waits"] = bool(self.short_quest_waits.get())
        rates["events"] = self.events_value()
        for k in ("event_harvest", "event_starlight", "event_egg_hunt", "event_horro", "event_sunbreeze"):
            rates[k] = bool(getattr(self, k).get())
        rates["bots_head_start"] = bool(self.bots_head_start.get()) and not self.head_start_done
        rates["bots_head_start_done"] = self.head_start_done
        rates["claim_shield"] = False
        return core.lock_player_rates(rates) if self.player else rates


class ControllerTab(tk.Frame):
    """(2026-11-22) Controller setup from the launcher, instead of FFXI's own FFXiPadConfig.exe (launcher_gamepad.py,
    ported from LocalXI). Written into the Ashita boot file's [ffxi.registry] when PLAY is pressed."""

    def __init__(self, parent, values):
        super().__init__(parent, bg=BG)
        values = gp.clean(values)
        self.applied = values["applied"]
        self.managed = tk.BooleanVar(value=values["managed"])
        self.enabled = tk.BooleanVar(value=values["enabled"])
        self.kind = tk.StringVar(value=gp.CONTROLLER_NAMES[values["type"]])
        self.steam = tk.BooleanVar(value=values["steam_input"])
        self.confirm_right = tk.BooleanVar(value=values["confirm_right"])
        self.vibration = tk.BooleanVar(value=values["vibration"])
        self.background = tk.BooleanVar(value=values["background"])
        self.invert = tk.BooleanVar(value=values["invert_camera"])
        self.chosen = dict(values["buttons"])          # slot -> button id the player changed
        self.action_vars = {}

        def check(parent, text, var, command=None):
            b = tk.Checkbutton(parent, text=text, variable=var, command=command, bg=BG, fg=FG, selectcolor=PANEL,
                               activebackground=BG, activeforeground=FG, anchor="w", justify="left")
            b.pack(anchor="w", padx=10, pady=1)
            return b

        check(self, "Set up my controller here", self.managed, self.refresh)
        tk.Label(self, text="Off = the game keeps what FFXI's own gamepad tool saved. Applied when you press PLAY "
                            "(the main window; the dualbox window keeps its own).",
                 bg=BG, fg=DIM, wraplength=760, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=10, pady=(0, 6))

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True)
        left = tk.Frame(self.body, bg=BG)
        left.pack(side="left", fill="y", anchor="n")
        row = tk.Frame(left, bg=BG)
        row.pack(anchor="w", padx=10, pady=4)
        tk.Label(row, text="Controller:", bg=BG, fg=FG).pack(side="left")
        box = ttk.Combobox(row, values=[n for _, n in gp.CONTROLLERS], textvariable=self.kind, state="readonly", width=26)
        box.pack(side="left", padx=6)
        box.bind("<<ComboboxSelected>>", self.kind_changed)
        check(left, "Use a controller (off: keyboard only, and no controller search, which can stutter)", self.enabled)
        self.steam_box = check(left, "PlayStation pad through Steam Input or DS4Windows", self.steam, self.layout_changed)
        check(left, "Confirm with the right face button (Nintendo's A, Japanese style)", self.confirm_right, self.layout_changed)
        check(left, "Vibration", self.vibration)
        check(left, "Controller works while the game is in the background", self.background)
        check(left, "Invert camera up / down", self.invert)
        self.hint = tk.Label(left, text="", bg=BG, fg=DIM, wraplength=330, justify="left", font=(UI_FONT, 9))
        self.hint.pack(anchor="w", padx=10, pady=(8, 0))
        bar = tk.Frame(left, bg=BG)
        bar.pack(anchor="w", padx=10, pady=10)
        tk.Button(bar, text="Reset buttons", command=self.reset_buttons, bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left")
        tk.Button(bar, text="FFXI's own gamepad tool", command=lambda: GraphicsTab.open_pad_config(self),
                  bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left", padx=6)

        right = tk.Frame(self.body, bg=BG)
        right.pack(side="left", fill="both", expand=True, anchor="n", padx=(20, 10))
        tk.Label(right, text="Buttons", bg=BG, fg=FG, font=(UI_FONT, 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 4))
        self.boxes = {}
        for i, (slot, name) in enumerate(gp.ACTIONS, start=1):
            tk.Label(right, text=name, bg=BG, fg=FG, anchor="w").grid(row=i, column=0, sticky="w", pady=1)
            var = tk.StringVar()
            b = ttk.Combobox(right, textvariable=var, state="readonly", width=20)
            b.grid(row=i, column=1, sticky="w", padx=6, pady=1)
            b.bind("<<ComboboxSelected>>", lambda _e, s=slot: self.button_changed(s))
            self.action_vars[slot], self.boxes[slot] = var, b
        tk.Label(right, text="Sticks and D-pad: left stick moves, right stick turns the camera, D-pad moves in menus.",
                 bg=BG, fg=DIM, wraplength=420, justify="left", font=(UI_FONT, 9)).grid(row=len(gp.ACTIONS) + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.layout_changed()

    def _type(self):
        return next((k for k, n in gp.CONTROLLERS if n == self.kind.get()), "xbox")

    def collect(self):
        values = {"managed": self.managed.get(), "enabled": self.enabled.get(), "type": self._type(),
                  "steam_input": self.steam.get(), "confirm_right": self.confirm_right.get(),
                  "vibration": self.vibration.get(), "background": self.background.get(),
                  "invert_camera": self.invert.get(), "buttons": dict(self.chosen), "applied": self.applied}
        return gp.clean(values)

    def kind_changed(self, _event=None):
        kind = self._type()
        self.confirm_right.set(kind in ("switch", "switch2"))      # Nintendo's A is the right button
        if kind not in ("ps4", "ps5"):
            self.steam.set(False)
        self.chosen = {}                                            # button numbers differ between pads
        self.layout_changed()

    def layout_changed(self):
        values = self.collect()
        self.chosen = dict(values["buttons"])
        names = gp.buttons(values)
        self.names = {b: n for b, n in names}
        current = gp.default_buttons(values)
        current.update(self.chosen)
        for slot, var in self.action_vars.items():
            self.boxes[slot].configure(values=[n for _, n in names])
            var.set(self.names.get(current.get(slot, gp.NONE), "(nothing)"))
        kind = values["type"]
        self.steam_box.configure(state="normal" if kind in ("ps4", "ps5") else "disabled")
        if kind in ("switch", "switch2"):
            text = "Nintendo controllers need Steam Input (or BetterJoy for the Switch 1 Pro), which makes them act like an Xbox pad."
        elif kind in ("ps4", "ps5") and not values["steam_input"]:
            text = "Plugged in directly, on Sony's own driver. If it goes through Steam or DS4Windows, tick that box above."
        else:
            text = "On the Steam Deck, keep Xbox: Steam Input makes its controls act like an Xbox pad."
        self.hint.configure(text=text)
        self.refresh()

    def button_changed(self, slot):
        wanted = self.action_vars[slot].get()
        button = next((b for b, n in self.names.items() if n == wanted), gp.NONE)
        if button == gp.default_buttons(self.collect()).get(slot, gp.NONE):
            self.chosen.pop(slot, None)
        else:
            self.chosen[slot] = button

    def reset_buttons(self):
        self.chosen = {}
        self.layout_changed()

    def refresh(self):
        """The choices only show while the launcher sets the controller up (off: the game's own settings apply)."""
        if self.managed.get():
            if not self.body.winfo_ismapped():
                self.body.pack(fill="both", expand=True)
            self.steam_box.configure(state="normal" if self._type() in ("ps4", "ps5") else "disabled")
        else:
            self.body.pack_forget()


class GraphicsTab(tk.Frame):
    """Display settings, written into the Ashita boot file's [ffxi.registry] section when PLAY is pressed."""

    def __init__(self, parent, values, ini_path):
        super().__init__(parent, bg=BG)
        self.ini_path = ini_path
        self.v = {gid: tk.StringVar(value=str(values[gid])) for gid in core.GRAPHICS_KEYS}
        self.window = tk.StringVar(value=core.WINDOW_MODES[values["window_mode"]])
        self.textures = tk.StringVar(value=core.TEXTURE_LEVELS[values["textures"]])
        self.fonts = tk.StringVar(value=core.FONT_LEVELS[values["fonts"]])
        self.bump = tk.BooleanVar(value=bool(values["bump"]))
        self.stab = tk.BooleanVar(value=bool(values["stab"]))
        self.bg_sound = tk.BooleanVar(value=bool(values["bg_sound"]))
        self.warning = tk.StringVar(value="")

        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(top, text="Preset:", bg=BG, fg=FG).pack(side="left")
        self.preset = ttk.Combobox(top, values=list(core.GRAPHICS_PRESETS), state="readonly", width=24)
        self.preset.pack(side="left", padx=6)
        tk.Button(top, text="Fill in preset", command=self.fill_preset, bg=PANEL, fg=FG, relief="flat", padx=8).pack(side="left")
        tk.Label(self, text="Applied when you press PLAY. Presets only change quality, not your screen size.", bg=BG, fg=DIM,
                 font=(UI_FONT, 9)).pack(anchor="w", padx=10)

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="x", padx=10, pady=6)
        row = 0

        def label(text, r):
            tk.Label(grid, text=text, bg=BG, fg=FG, anchor="w", width=26).grid(row=r, column=0, sticky="w", pady=3)

        def pair(text, kw, kh, r):
            label(text, r)
            for col, k in ((1, kw), (2, kh)):
                lo, hi = core.GRAPHICS_KEYS[k][2], core.GRAPHICS_KEYS[k][3]
                ttk.Spinbox(grid, from_=lo, to=hi, increment=64, textvariable=self.v[k], width=7).grid(row=r, column=col, padx=4)

        label("Window", row)
        ttk.Combobox(grid, values=list(core.WINDOW_MODES.values()), textvariable=self.window, state="readonly", width=18).grid(row=row, column=1, columnspan=2, sticky="w", padx=4)
        row += 1
        pair("Screen resolution", "screen_w", "screen_h", row); row += 1
        pair("Menu resolution", "menu_w", "menu_h", row)
        tk.Button(grid, text="Match screen", command=self.match_menu, bg=PANEL, fg=FG, relief="flat", padx=6).grid(row=row, column=3, padx=6)
        row += 1
        pair("3D (background) resolution", "bg_w", "bg_h", row); row += 1
        label("Mip mapping (0 = off, 6 = most)", row)
        ttk.Spinbox(grid, from_=0, to=6, increment=1, textvariable=self.v["mip"], width=7).grid(row=row, column=1, padx=4); row += 1
        label("Textures", row)
        ttk.Combobox(grid, values=list(core.TEXTURE_LEVELS.values()), textvariable=self.textures, state="readonly", width=22).grid(row=row, column=1, columnspan=3, sticky="w", padx=4); row += 1
        label("Fonts", row)
        ttk.Combobox(grid, values=list(core.FONT_LEVELS.values()), textvariable=self.fonts, state="readonly", width=22).grid(row=row, column=1, columnspan=3, sticky="w", padx=4); row += 1
        for text, var in (("Bump mapping", self.bump), ("Graphics stabilization", self.stab), ("Keep playing sound when the window is in the background", self.bg_sound)):
            tk.Checkbutton(grid, text=text, variable=var, bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG,
                           activeforeground=FG).grid(row=row, column=0, columnspan=4, sticky="w", pady=1)
            row += 1
        # (2026-11-23, Dugahst) draw distance, through Ashita's drawdistance addon: a multiplier on the game's own
        # (1 = as the game draws it, 0 = leave it alone). Far scenery and far people/monsters separately.
        draw = core.load_draw(HERE)
        self.draw_world = tk.StringVar(value=f"{draw['world']:g}")
        self.draw_entity = tk.StringVar(value=f"{draw['entity']:g}")
        label("Draw distance: scenery", row)
        ttk.Spinbox(grid, from_=core.DRAW_LIMITS[0], to=core.DRAW_LIMITS[1], increment=0.5, textvariable=self.draw_world, width=7).grid(row=row, column=1, padx=4)
        tk.Label(grid, text="0 = the game's own", bg=BG, fg=DIM, font=(UI_FONT, 8)).grid(row=row, column=2, columnspan=2, sticky="w", padx=4)
        row += 1
        label("Draw distance: characters", row)
        ttk.Spinbox(grid, from_=core.DRAW_LIMITS[0], to=core.DRAW_LIMITS[1], increment=0.5, textvariable=self.draw_entity, width=7).grid(row=row, column=1, padx=4)
        tk.Label(grid, text="x the game's own; 2-4 is plenty, more costs speed", bg=BG, fg=DIM, font=(UI_FONT, 8)).grid(row=row, column=2, columnspan=2, sticky="w", padx=4)
        row += 1

        tk.Label(self, textvariable=self.warning, bg=BG, fg="#e0a030", wraplength=480, justify="left").pack(anchor="w", padx=10, pady=(2, 0))
        bar = tk.Frame(self, bg=BG)
        bar.pack(anchor="w", padx=10, pady=6)
        tk.Button(bar, text="Check", command=self.check, bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left", padx=(0, 6))
        tk.Button(bar, text="Restore original settings", command=self.restore, bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left")
        # (2026-11-22, Sunie: handheld players) FFXI's own gamepad setup tool, without hunting for it in the game folder
        tk.Button(bar, text="Gamepad setup", command=self.open_pad_config, bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left", padx=(6, 0))
        tk.Label(self, text="Not listed yet: Map Compression, Maintain Aspect Ratio, 3D LCD Mode and Environment. "
                            "I have not confirmed which values control those, so they are left alone.",
                 bg=BG, fg=DIM, wraplength=480, justify="left", font=(UI_FONT, 8)).pack(anchor="w", padx=10, pady=(4, 0))
        self.check()

    def open_pad_config(self):
        """Opens FFXiPadConfig.exe from the game folder the launcher plays (ToolsUS / ToolsEU / Tools)."""
        cfg = core.load_config(os.path.join(HERE, "config.json"))
        game = cfg.get("ffxi_client_dir", "")
        first = {"US": "ToolsUS", "EU": "ToolsEU", "JP": "Tools"}.get(cfg.get("pol_lang", "US"), "ToolsUS")
        for sub in (first, "ToolsUS", "Tools", "ToolsEU"):
            exe = os.path.join(game, sub, "FFXiPadConfig.exe") if game else ""
            if exe and os.path.isfile(exe):
                try:
                    if linux is not None:
                        linux.run_windows(HERE, cfg, [exe], cwd=os.path.dirname(exe), wait=False)
                    else:
                        os.startfile(exe)          # (the tool can ask for Windows' permission; startfile shows that prompt)
                except Exception as problem:
                    messagebox.showerror("Gamepad setup", f"Could not open the gamepad setup tool:\n{problem}", parent=self)
                return
        messagebox.showinfo("Gamepad setup", "FFXI's gamepad setup tool (FFXiPadConfig.exe) was not found in the game "
                            "folder's Tools folders" + (f":\n{game}" if game else ".") , parent=self)

    def collect_draw(self):
        out = {}
        for key, var in (("world", self.draw_world), ("entity", self.draw_entity)):
            try:
                out[key] = max(core.DRAW_LIMITS[0], min(core.DRAW_LIMITS[1], float(var.get())))
            except (TypeError, ValueError):
                out[key] = 0.0
        return out

    def _reverse(self, table, text):
        return next((k for k, v in table.items() if v == text), None)

    def collect(self):
        values = {gid: var.get() for gid, var in self.v.items()}
        values["window_mode"] = self._reverse(core.WINDOW_MODES, self.window.get())
        values["textures"] = self._reverse(core.TEXTURE_LEVELS, self.textures.get())
        values["fonts"] = self._reverse(core.FONT_LEVELS, self.fonts.get())
        values["bump"], values["stab"], values["bg_sound"] = int(bool(self.bump.get())), int(bool(self.stab.get())), int(bool(self.bg_sound.get()))
        return core.clean_graphics({k: v for k, v in values.items() if v is not None})

    def show(self, values):
        for gid, var in self.v.items():
            var.set(str(values[gid]))
        self.window.set(core.WINDOW_MODES[values["window_mode"]])
        self.textures.set(core.TEXTURE_LEVELS[values["textures"]])
        self.fonts.set(core.FONT_LEVELS[values["fonts"]])
        self.bump.set(bool(values["bump"]))
        self.stab.set(bool(values["stab"]))
        self.bg_sound.set(bool(values["bg_sound"]))
        self.check()

    def fill_preset(self):
        name = self.preset.get()
        if name:
            values = self.collect()
            values.update(core.GRAPHICS_PRESETS[name])
            self.show(core.clean_graphics(values))

    def match_menu(self):
        self.v["menu_w"].set(self.v["screen_w"].get())
        self.v["menu_h"].set(self.v["screen_h"].get())
        self.check()

    def check(self):
        self.warning.set(core.aspect_warning(self.collect()))

    def restore(self):
        if core.restore_graphics(self.ini_path):
            self.show(core.read_boot_graphics(self.ini_path))
            messagebox.showinfo("Restored", "The boot file is back to how it was before the launcher first changed the display settings.")
        else:
            messagebox.showinfo("Nothing to restore", "The launcher has not changed the display settings yet.")


class GfxModTab(tk.Frame):
    """dgVoodoo + ReShade: install them next to pol.exe, switch them on and off, take them out again."""

    def __init__(self, parent, here, cfg):
        super().__init__(parent, bg=BG)
        self.here = here
        self.state = core.gfx_load(here)
        recommended = core.gfx_find_target(cfg.get("gfxmod_target", ""), cfg.get("ashita_dir", ""))
        nothing_installed = not self.state["installed"]["files"]
        if not self.state["target"] or not os.path.isdir(self.state["target"]) or (nothing_installed and recommended):
            self.state["target"] = recommended   # until something is installed the recommended folder always wins
        if not self.state["dgvoodoo"] and not self.state["reshade"]:
            self.state["dgvoodoo"], self.state["reshade"] = core.gfx_guess_sources()
        self.dg_var = tk.StringVar(value=self.state["dgvoodoo"])
        self.rs_var = tk.StringVar(value=self.state["reshade"])
        self.target_var = tk.StringVar(value=self.state["target"])
        self.status = tk.StringVar(value="")

        tk.Label(self, text="Sharper, nicer-looking graphics with dgVoodoo and ReShade.", bg=BG, fg=FG,
                 font=(UI_FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(14, 2))
        tk.Label(self, text="Point this at the files you already use (for example from your Horizon setup). The launcher copies them next to the "
                            "game, keeps a backup of anything of yours it would replace, and can switch them off or remove them again.",
                 bg=BG, fg=DIM, wraplength=860, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=14)

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="x", padx=14, pady=(10, 4))
        self._row(grid, 0, "dgVoodoo folder", self.dg_var, "Has D3D8.dll and dgVoodoo.conf (the official download works too).")
        self._row(grid, 1, "ReShade folder", self.rs_var, "Has dxgi.dll, ReShade.ini and your preset, and ideally a reshade-shaders folder.")
        self._row(grid, 2, "Loader folder", self.target_var, "Where the files go: the folder with xiloader.exe (Ashita's bootloader). Found automatically.")

        tk.Label(self, textvariable=self.status, bg=BG, fg=ACCENT, font=(UI_FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(8, 0))
        self.api = tk.StringVar(value="")
        tk.Label(self, textvariable=self.api, bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(anchor="w", padx=14, pady=(0, 2))
        bar = tk.Frame(self, bg=BG)
        bar.pack(anchor="w", padx=14, pady=4)
        for text, command in (("Install / update", self.install), ("Turn ON", lambda: self.toggle(True)), ("Turn OFF", lambda: self.toggle(False)),
                              ("Reset settings", self.reset), ("Uninstall", self.uninstall), ("Add shaders...", self.add_shaders), ("Check shaders", self.check_shaders), ("Fix search paths", self.fix_paths), ("dgVoodoo settings", self.open_cpl), ("Open folder", self.open_target)):
            tk.Button(bar, text=text, command=command, bg=PANEL2, fg=FG, relief="flat", padx=12, pady=4,
                      activebackground=BORDER, activeforeground=FG).pack(side="left", padx=(0, 6))

        self.log = tk.Text(self, height=9, bg=PANEL, fg=DIM, relief="flat", font=(MONO_FONT, 9), state="disabled", bd=0, highlightthickness=0)
        self.log.pack(fill="both", expand=True, padx=14, pady=(8, 6))
        tk.Label(self, text="Close the game before installing, switching or removing (Windows locks the files while it runs). "
                            "Install / update keeps your current ReShade and dgVoodoo settings; Reset settings replaces them with the source files. "
                            "If another launcher (such as the Horizon launcher) also manages these files, use only one launcher at a time.",
                 bg=BG, fg=DIM, wraplength=860, justify="left", font=(UI_FONT, 8)).pack(anchor="w", padx=14, pady=(0, 10))
        self.refresh()

    def _row(self, grid, row, label, var, hint):
        tk.Label(grid, text=label, bg=BG, fg=FG, anchor="w", width=20).grid(row=row * 2, column=0, sticky="w", pady=(4, 0))
        tk.Entry(grid, textvariable=var, bg=PANEL2, fg=FG, insertbackground=FG, relief="flat", width=70).grid(row=row * 2, column=1, padx=6, pady=(4, 0))
        tk.Button(grid, text="Browse...", command=lambda: self.browse(var), bg=PANEL2, fg=FG, relief="flat", padx=8,
                  activebackground=BORDER, activeforeground=FG).grid(row=row * 2, column=2)
        tk.Label(grid, text=hint, bg=BG, fg=DIM, font=(UI_FONT, 8), anchor="w").grid(row=row * 2 + 1, column=1, sticky="w", padx=6)

    def browse(self, var):
        chosen = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~"))
        if chosen:
            var.set(os.path.normpath(chosen))

    def read_fields(self):
        self.state["dgvoodoo"], self.state["reshade"], self.state["target"] = self.dg_var.get().strip(), self.rs_var.get().strip(), self.target_var.get().strip()

    def refresh(self):
        self.status.set("Status: " + core.gfx_status(self.state))
        installed = core.gfx_read_output_api(self.state["target"]) if self.state["installed"]["files"] else ""
        chosen = installed or core.gfx_read_output_api(self.dg_var.get().strip()) or core.gfx_read_output_api(os.path.join(self.dg_var.get().strip(), ""))
        self.api.set(f"dgVoodoo draws using: {chosen}   (change it in 'dgVoodoo settings')" if chosen
                     else "dgVoodoo draws using: not shown here - open 'dgVoodoo settings' to see or change it")

    def say(self, lines):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", "\n".join(lines))
        self.log.configure(state="disabled")

    def run(self, action):
        self.read_fields()
        try:
            notes = action()
        except PermissionError:
            messagebox.showwarning("Close the game first", "Windows would not let the launcher change a file. Close the game (and anything using it) and try again.")
            self.refresh()
            return
        except Exception as e:
            messagebox.showerror("That did not work", str(e))
            self.refresh()
            return
        try:
            core.gfx_save(self.here, self.state)
        except OSError:
            pass
        self.say(notes or ["Done."])
        self.refresh()

    def install(self):
        self.run(lambda: core.gfx_install(self.here, self.state))

    def reset(self):
        self.run(lambda: core.gfx_install(self.here, self.state, reset_settings=True))

    def toggle(self, enabled):
        word = "ON" if enabled else "OFF"

        def action():
            if not self.state["installed"]["files"]:
                return ["Nothing is installed yet - press Install / update first."]
            n = core.gfx_set_enabled(self.state, enabled)
            if n:
                return [f"Turned {word} ({n} file(s) switched). Start the game to see it."]
            return [f"It is already {word}."]
        self.run(action)

    def uninstall(self):
        if messagebox.askyesno("Uninstall", "Remove the dgVoodoo and ReShade files the launcher added, and put your own files back?"):
            self.run(lambda: core.gfx_uninstall(self.here, self.state))

    def add_shaders(self):
        chosen = filedialog.askdirectory(title="Choose a folder of shaders (a reshade-shaders folder, or any folder with .fx files)", initialdir=os.path.expanduser("~"))
        if chosen:
            self.run(lambda: core.gfx_add_shaders(self.state, os.path.normpath(chosen)) + ["Press 'Check shaders' to see if ReShade can find everything now."])

    def check_shaders(self):
        target = self.target_var.get().strip()
        result = core.gfx_check_shaders(target)
        if result is None:
            self.say(["There is no ReShade.ini in the loader folder yet. Install first."])
            return
        found, total, missing, fx = result
        lines = [f"ReShade looks in {total} shader folder(s): {found} exist, {len(missing)} missing. Shader files found: {fx}."]
        if missing:
            lines.append("Missing: " + ", ".join(missing))
            lines.append("")
            lines.append("To get them: close the game, run the ReShade installer (ReShade_Setup_6.8.0.exe), choose xiloader.exe in the loader folder,")
            lines.append("pick 'Direct3D 10/11/12', then tick the effect packages and press Install. Then press Check shaders again.")
        elif fx == 0:
            lines.append("The folders exist but hold no shader files.")
        else:
            lines.append("All of ReShade's shader folders are there.")
        hidden = core.gfx_unsearched_shader_folders(target)
        if hidden:
            lines.append("")
            lines.append("These folders exist but ReShade is NOT told to look in them, so their effects do not show up: "
                         + ", ".join(f"{name} ({count} files)" for name, count in hidden))
            lines.append("Press 'Fix search paths' to add them.")
        self.say(lines)

    def fix_paths(self):
        def action():
            added = core.gfx_fix_search_paths(self.target_var.get().strip())
            if not added:
                return ["ReShade already searches every shader folder that exists."]
            return ["Added to ReShade.ini: " + ", ".join(added), "Start the game (or press Reload in ReShade) to see the new effects."]
        self.run(action)

    def open_cpl(self):
        cpl = os.path.join(self.target_var.get().strip(), "dgVoodooCpl.exe")
        if os.path.isfile(cpl):
            os.startfile(cpl)
        else:
            messagebox.showinfo("dgVoodoo settings", "Install it first (that copies dgVoodoo's settings window next to the game), then press this again.")

    def open_target(self):
        target = self.target_var.get().strip()
        if target and os.path.isdir(target):
            os.startfile(target)


class UpdatesTab(tk.Frame):
    """The Settings page: a GM account for testing, and updates from Phoenix. setup_gm.py and server_update.py do the work; this page shows what they say."""

    # (2026-11-22, K-Andy: moved FFXI from a hard disk to an SSD and the game closed right away) where the game is
    def build_game_folder(self):
        box = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(box, text="Game folder", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        self.game_folder_text = tk.StringVar(value=self.app.cfg.get("ffxi_client_dir", "") or "(not set)")
        tk.Label(box, textvariable=self.game_folder_text, bg=PANEL, fg=DIM, font=(UI_FONT, 9)).pack(anchor="w", padx=12)
        tk.Label(box, text="Moved FINAL FANTASY XI to another drive? Close the game, move the whole SquareEnix folder (FINAL FANTASY XI "
                           "and PlayOnlineViewer together), then pick the new FINAL FANTASY XI folder here.",
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(2, 4))
        tk.Button(box, text="Change game folder...", command=self.change_game_folder, bg=PANEL2, fg=FG, relief="flat", padx=12, pady=5,
                  activebackground=BORDER, activeforeground=FG).pack(anchor="w", padx=12, pady=(0, 12))

    # (2026-11-22, Sunie: "restart installation") the first-time setup again, on this install: other folders, or
    # whatever is missing filled in. The world is never touched (launcher_setup.run_setup, again=...).
    def build_setup_again(self):
        box = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(box, text="First-time setup", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(box, text="Point the launcher at other folders (game, Ashita, server) or let setup fill in what is missing, "
                           "without starting over. Your world, characters, squad and settings are kept.",
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(2, 4))
        tk.Button(box, text="Run setup again...", command=self.setup_again, bg=PANEL2, fg=FG, relief="flat", padx=12, pady=5,
                  activebackground=BORDER, activeforeground=FG).pack(anchor="w", padx=12, pady=(0, 12))

    # (2026-11-23) the Revamped switch: old Squads / old Gambits off, the Revamped versions on (launcher_revamped.py)
    def build_revamped(self):
        box = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(box, text="Revamped Squads and Gambits", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        self.revamped_text = tk.StringVar()
        tk.Label(box, textvariable=self.revamped_text, bg=PANEL, fg=DIM, wraplength=880, justify="left",
                 font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(2, 4))
        bar = tk.Frame(box, bg=PANEL)
        bar.pack(anchor="w", padx=12, pady=(0, 12))
        self.revamped_buttons = []
        for text, value in (("Use the Revamped versions", "revamped"), ("Use the old versions", "stock")):
            button = tk.Button(bar, text=text, command=lambda v=value: self.revamped_switch(v), bg=PANEL2, fg=FG, relief="flat",
                               padx=12, pady=5, activebackground=BORDER, activeforeground=FG, disabledforeground=DIM)
            button.pack(side="left", padx=(0, 8))
            # (v0.3.3a) greyed out until a Revamped package is installed; the tip says where it comes from
            HoverTip(button, lambda b=button: REVAMPED_GREY_TIP if str(b.cget("state")) == "disabled" else None)
            self.revamped_buttons.append(button)
        self.revamped_refresh()

    def revamped_refresh(self):
        kit, ashita = HERE, self.app.ashita
        found = rv.detected(ashita)
        if not found:
            self.revamped_text.set("No Revamped Squads or Gambits package is installed, so nothing to switch. The old ones stay as they are.")
            for button in self.revamped_buttons:
                button.configure(state="disabled")
            return
        names = ", ".join("%s: %s" % (rv.TABLE[c]["label"], {"revamped": "Revamped", "stock": "old"}.get(rv.choice(kit, c), "not chosen")) for c in found)
        self.revamped_text.set("Revamped is installed. Now: " + names + ". The old add-ons stay installed with their settings; "
                               "only their lines in the start script are switched, and the change applies at the next launch.")
        for button in self.revamped_buttons:
            button.configure(state="normal")

    def revamped_switch(self, value):
        found = rv.detected(self.app.ashita)
        if not found:
            return
        try:
            done = rv.choose(HERE, self.app.ashita, found, value)
        except Exception as e:
            messagebox.showerror("Revamped", "Could not change the start script: %s" % e)
            return
        self.revamped_refresh()
        messagebox.showinfo("Revamped", ("Done. " if done else "Already set. ") + "Takes effect the next time the game starts.")

    def build_clear_ah(self):
        """(delukard, 2026-11-22) An empty auction house for a world that plays without one: switching the simulator
        off only stops new stock, what it listed before stays."""
        box = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", padx=14, pady=(0, 6))
        tk.Label(box, text="Auction house", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(box, text="Take everything the auction house simulator listed off the auction house, for a world that plays "
                           "without one. What you or a bot player listed stays, and so does the sales history.",
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(2, 4))
        tk.Button(box, text="Clear the auction house...", command=self.clear_auction_house, bg=PANEL2, fg=FG, relief="flat",
                  padx=12, pady=5, activebackground=BORDER, activeforeground=FG).pack(anchor="w", padx=12, pady=(0, 12))

    def clear_auction_house(self):
        title = "Clear the auction house"
        on = bool(self.app.rates.get("ah_sim", self.app.cfg.get("ah_sim", False)))
        text = "Take every listing of the auction house simulator off the auction house?\n\nWhat you listed yourself stays."
        if on:
            text += ("\n\nThe simulator is switched ON (WORLD > Auction house), so it stocks the auction house again at "
                     "the next PLAY. Switch it off first if you want it to stay empty.")
        if not messagebox.askyesno(title, text, parent=self):
            return
        try:
            import ah_sim
            conn = sq.connect(self.app.cfg)
            try:
                count = ah_sim.clear_listings(conn)
            finally:
                conn.close()
            messagebox.showinfo(title, f"{count} listing(s) were taken off the auction house." if count
                                else "The simulator has nothing listed: the auction house was already clear of it.", parent=self)
        except Exception as e:
            messagebox.showerror(title, f"The database could not be reached ({e}).\n\nIf the servers are not running, press "
                                        "PLAY, wait for the game window, and try again.", parent=self)

    def setup_again(self):
        if self.app.running:
            messagebox.showwarning("Close the game first", "The servers are running. Close the game (it stops the servers), "
                                   "then run setup again.", parent=self)
            return
        if not messagebox.askyesno("Run setup again", "The launcher closes and the first-time setup opens with this install's "
                                   "folders filled in.\n\nYour world, characters, squad and settings are kept. Nothing "
                                   "changes until you press Install there: closing that window leaves everything as it is."
                                   "\n\nGo on?", parent=self):
            return
        try:
            extra = {} if IS_WINDOWS else {"start_new_session": True}
            cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.join(HERE, "launcher_gui.pyw")]
            subprocess.Popen(cmd + ["--setup-again"], cwd=HERE, **extra)
        finally:
            self.app.on_close()

    def change_game_folder(self):
        chosen = filedialog.askdirectory(parent=self, title="Pick the FINAL FANTASY XI folder",
                                         initialdir=self.app.cfg.get("ffxi_client_dir") or None)
        if not chosen:
            return
        import launcher_game as lg
        try:
            ffxi, viewer = lg.pick_game_folder(chosen, self.app.cfg.get("pol_lang", "US"))
        except ValueError as problem:
            messagebox.showerror("Game folder", str(problem), parent=self)
            return
        if not messagebox.askyesno("Game folder", f"Play FINAL FANTASY XI from here from now on?\n\n{ffxi}\n{viewer}", parent=self):
            return
        # game_copy: at PLAY the launcher points PlayOnline at these folders until the game closes (Windows asks once),
        # so the registry's old location no longer matters
        for key, value in (("ffxi_client_dir", ffxi), ("pol_dir", viewer), ("game_copy", True)):
            save_config_value(key, value)
            self.app.cfg[key] = value
        self.game_folder_text.set(ffxi)
        messagebox.showinfo("Game folder", "Saved. Press PLAY: Windows asks for permission once, so the launcher can point "
                            "PlayOnline at this folder while you play.", parent=self)

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.busy = False
        self.lines = queue.Queue()
        self.gm_buttons = []
        gm = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        gm.pack(fill="x", padx=14, pady=(14, 6))
        tk.Label(gm, text="GM account for testing", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(gm, text=("A separate account whose characters are GMs, so your real character is never touched. Set it up once, then press Start GM game. "
                           "The first time, create a character in the lobby: it is a GM from its first login. GM commands can change your world, "
                           "so back up the database first."),
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(0, 8))
        gm_bar = tk.Frame(gm, bg=PANEL)
        gm_bar.pack(anchor="w", padx=12, pady=(0, 12))
        for text, command in (("Set up GM account", lambda: self.run_script("setup_gm.py", ["setup"])), ("Start GM game", app.start_gm),
                              ("GM commands", lambda: self.run_script("setup_gm.py", ["commands"])), ("Make a character GM...", self.promote),
                              ("Back up database now", lambda: self.run_script("setup_gm.py", ["backup"]))):
            button = tk.Button(gm_bar, text=text, command=command, bg=PANEL2, fg=FG, relief="flat", padx=12, pady=5, activebackground=BORDER, activeforeground=FG)
            button.pack(side="left", padx=(0, 8))
            self.gm_buttons.append(button)
        if IS_WINDOWS:
            self.build_game_folder()
        self.player = bool(app.cfg.get("mariadb_dir"))      # a player install (first-run setup); else this is the dev PC
        if self.player:
            self.build_setup_again()
        # (2026-11-23, the user: "remove this") the Revamped switch shows only once a Revamped package is installed;
        # without one it only said there was nothing to switch
        if app.ashita and os.path.isdir(app.ashita) and rv.detected(app.ashita):
            self.build_revamped()
        if not getattr(app, "new_ui", False):              # (2026-11-24, the user) the newer look has it on WORLD > Auction house
            self.build_clear_ah()
        try:                                                # (2026-11-22, Sunie) the AI hood: only where its switch file is
            import launcher_hood
            if launcher_hood.is_on(HERE):
                launcher_hood.build_box(self, app, HERE, {"bg": BG, "panel": PANEL, "panel2": PANEL2, "fg": FG, "dim": DIM,
                                                          "border": BORDER, "gold": GOLD, "font": UI_FONT, "mono": MONO_FONT})
        except Exception:
            pass
        self.buttons = []
        if linux is not None:
            self.build_linux()
        self.contributor = app.cfg.get("contributor")       # a team member's GitHub name, once they signed in (contributor mode)
        if self.player:
            self.build_player_updates()
        else:
            if not self.contributor:
                self.build_publish()
                self.build_team()
            tk.Label(self, text="Keep your server up to date with Phoenix", bg=BG, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=14, pady=(8, 2))
            tk.Label(self, text=("Check shows what is new and changes nothing. Update saves your database, then merges the new version in, applies database "
                                 "changes and rebuilds the server. If anything clashes with our own changes it is cancelled and nothing changes. "
                                 "Close the game before updating. Undo goes back to the version from before the last update."),
                     bg=BG, fg=DIM, wraplength=900, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=14, pady=(0, 8))
            bar = tk.Frame(self, bg=BG)
            bar.pack(anchor="w", padx=14)
            for text, command in (("Check for updates", self.check), ("Update now", self.update), ("Undo last update", self.undo),
                                  ("Open backups folder", lambda: app.open_dir(os.path.join(HERE, "backups")))):
                button = tk.Button(bar, text=text, command=command, bg=PANEL, fg=FG, relief="flat", padx=14, pady=6, activebackground=PANEL2, activeforeground=FG)
                button.pack(side="left", padx=(0, 8))
                self.buttons.append(button)
        self.contrib_frame = tk.Frame(self, bg=BG)
        self.contrib_frame.pack(fill="x")
        if self.contributor or app.cfg.get("contributor_mode"):      # hidden unless switched on in config.json (team members only)
            self.build_contributor()
        box = tk.Frame(self, bg=BG)
        box.pack(fill="both", expand=True, padx=14, pady=10)
        self.output = tk.Text(box, bg=PANEL, fg=FG, font=(MONO_FONT, 9), state="disabled", relief="flat", wrap="word", bd=0, highlightthickness=0)
        scroll = ttk.Scrollbar(box, command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self.write("Press 'Check for updates' to see whether there is a new version." if self.player else
                   "Press 'Check for updates' to see whether Phoenix has released anything new. The GM buttons above print their results here too.")
        if self.player:
            self.after(1500, lambda: self.player_check(True))       # quietly, on start: only speaks up when there is an update
        self.after(200, self.pump)

    # ----- Linux / Steam Deck: the menu entry and Steam -----
    def build_linux(self):
        frame = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="x", padx=14, pady=6)
        deck = linux.is_steam_deck()
        tk.Label(frame, text="Steam Deck" if deck else "Linux", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(frame, text=("Add XI: Forever Offline to your application menu, then to Steam (Steam's Add a Non-Steam Game list shows it), "
                              "so you can start it from Game Mode with the controller. The game runs through Proton, which the "
                              "launcher keeps inside its own folder."),
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(0, 8))
        bar = tk.Frame(frame, bg=PANEL)
        bar.pack(anchor="w", padx=12, pady=(0, 12))
        tk.Button(bar, text="Add to Steam and the menu", command=self.add_to_steam, bg=ACCENT, fg="white", relief="flat",
                  padx=14, pady=5).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="Redo the game's Proton setup", command=self.redo_prefix, bg=PANEL2, fg=FG, relief="flat",
                  padx=12, pady=5).pack(side="left", padx=(0, 8))
        self.proton_log = tk.BooleanVar(value=bool(self.app.cfg.get("proton_log", False)))
        tk.Checkbutton(bar, text="Write Proton logs (for bug reports)", variable=self.proton_log, command=self.save_proton_log,
                       bg=PANEL, fg=FG, selectcolor=PANEL2, activebackground=PANEL, activeforeground=FG).pack(side="left", padx=(8, 0))

    def add_to_steam(self):
        try:
            path = linux.install_desktop_entry(HERE)
        except Exception as e:
            messagebox.showerror("Add to Steam", f"Could not add the menu entry: {e}", parent=self)
            return
        opened = linux.open_steam_add_game()
        messagebox.showinfo("Add to Steam", "XI: Forever Offline is in your application menu now" +
                            (" and on your desktop" if os.path.isdir(os.path.expanduser("~/Desktop")) else "") + ".\n\n" +
                            ("In Steam's window that opened, tick XI: Forever Offline and press Add Selected Programs."
                             if opened else "In Steam: Games > Add a Non-Steam Game to My Library, tick XI: Forever Offline, "
                                            "then Add Selected Programs.") +
                            "\n\nIn Game Mode, start it from your library like any game.\n\n(" + path + ")", parent=self)

    def redo_prefix(self):
        if self.app.running:
            messagebox.showinfo("Proton", "Stop the game and the servers first.", parent=self)
            return
        try:
            os.remove(os.path.join(linux.prefix_path(HERE), linux.PREFIX_STAMP))
        except OSError:
            pass
        self.write("The game's Proton setup is done again at the next PLAY.")

    def save_proton_log(self):
        self.app.cfg["proton_log"] = bool(self.proton_log.get())
        try:
            save_config_value("proton_log", self.app.cfg["proton_log"])
        except Exception as e:
            self.write(f"Could not save the setting: {e}")

    # ----- dev PC: publish an update for players -----
    def build_publish(self):
        frame = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="x", padx=14, pady=6)
        tk.Label(frame, text="Publish an update for players", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(frame, text=("Players only get what you publish: your own changes and Phoenix updates reach them when you publish a new version. "
                              "This builds the launcher and the server and player zips, tags and pushes both repos and creates the GitHub "
                              "releases. It shows everything first and asks before anything is pushed."),
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(0, 8))
        tk.Button(frame, text="Publish update...", command=lambda: PublishDialog(self.app), bg=ACCENT, fg="white", relief="flat",
                  padx=14, pady=5).pack(anchor="w", padx=12, pady=(0, 12))

    # ----- dev PC: updates your team sent (contributor mode) -----
    def build_team(self):
        frame = tk.Frame(self, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="x", padx=14, pady=6)
        tk.Label(frame, text="Updates from your team", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(frame, text=("Contributors send their changes from their launcher; each one arrives as a pull request on GitHub. "
                              "Add to my build brings every waiting update onto this PC (your own edits are saved first; if anything "
                              "clashes it is cancelled and nothing changes), rebuilds the server when needed and copies new add-ons "
                              "into Ashita. Try it in game, then Send to GitHub and publish as usual. Undo goes back. Who can send "
                              "what is in contributors.json."),
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(0, 8))
        bar = tk.Frame(frame, bg=PANEL)
        bar.pack(anchor="w", padx=12, pady=(0, 12))
        tk.Button(bar, text="Show waiting updates", command=self.team_check, bg=PANEL2, fg=FG, relief="flat",
                  padx=12, pady=5).pack(side="left", padx=(0, 8))
        # (2026-11-19) the same safe steps as the Phoenix update, for the team's pull requests: team_update.py
        tk.Button(bar, text="Add to my build", command=self.team_add, bg=ACCENT, fg="white", relief="flat",
                  padx=12, pady=5).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="Undo", command=self.team_undo, bg=PANEL2, fg=FG, relief="flat",
                  padx=12, pady=5).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="Send to GitHub", command=self.team_push, bg=PANEL2, fg=FG, relief="flat",
                  padx=12, pady=5).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="Open on GitHub", command=lambda: self.app.open_url(f"https://github.com/{KIT_REPO_NAME}/pulls"),
                  bg=PANEL2, fg=FG, relief="flat", padx=12, pady=5).pack(side="left", padx=(0, 8))

    def team_add(self):
        if self.app.running:
            messagebox.showinfo("Updates from your team", "Close the game first (the servers must be stopped).")
            return
        if messagebox.askyesno("Updates from your team",
                               "Add every waiting update to the build on this PC?\n\n"
                               "Your own uncommitted edits are saved as a local commit first. If anything clashes, it is "
                               "cancelled and nothing changes. The server is rebuilt when the update needs it.\n\n"
                               "Nothing is sent to GitHub or to players by this."):
            self.run_script("team_update.py", ["update"])

    def team_undo(self):
        if self.app.running:
            messagebox.showinfo("Updates from your team", "Close the game first (the servers must be stopped).")
            return
        if messagebox.askyesno("Updates from your team", "Go back to how both folders were before the last 'Add to my build'?"):
            self.run_script("team_update.py", ["undo"])

    def team_push(self):
        if messagebox.askyesno("Send to GitHub",
                               "Send the commits on this PC to GitHub (launcher to main, server to dev)?\n\n"
                               "Only committed work is sent. Merged team updates are marked as merged on GitHub. "
                               "Players get nothing until you publish."):
            self.run_script("team_update.py", ["push"])

    def team_check(self):
        def work():
            try:
                import json as _json
                import launcher_contrib as lc
                import launcher_thirdparty as tp
                waiting = lc.open_updates(lambda url: _json.loads(tp._get(url)))
            except Exception as e:
                self.lines.put(("line", f"Could not check: {e}"))
                return
            if not waiting:
                self.lines.put(("line", "No updates waiting for review."))
            for number, title, who, url in waiting:
                self.lines.put(("line", f"#{number} {title}  (from {who})  {url}"))
        threading.Thread(target=work, daemon=True).start()

    # ----- contributor mode: send your changes to the dev for review -----
    def build_contributor(self):
        for child in self.contrib_frame.winfo_children():
            child.destroy()
        if not self.contributor:            # switched on but not signed in yet: only names on the list on GitHub get any further
            tk.Button(self.contrib_frame, text="Contributor sign-in", command=self.contrib_sign_in, bg=BG, fg=DIM, relief="flat",
                      bd=0, font=(UI_FONT, 8), activebackground=BG, activeforeground=FG, cursor="hand2").pack(anchor="w", padx=14, pady=(6, 0))
            return
        import launcher_contrib as lc
        areas = self.app.cfg.get("contributor_areas") or []
        frame = tk.Frame(self.contrib_frame, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(fill="x", padx=14, pady=6)
        tk.Label(frame, text=f"Contributor: {self.contributor}", bg=PANEL, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(frame, text=("Change and test as usual, then press Send. The launcher finds everything you changed (" +
                              (", ".join(lc.AREAS[a]["label"] for a in areas) or "nothing yet") +
                              "), you untick what shouldn't go and add new files, and it goes to Hurami for review on GitHub. "
                              "Nothing reaches players until it is merged and published."),
                 bg=PANEL, fg=DIM, wraplength=880, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(0, 8))
        bar = tk.Frame(frame, bg=PANEL)
        bar.pack(anchor="w", padx=12, pady=(0, 12))
        tk.Button(bar, text="Send an update to Hurami...", command=self.contrib_send_all, bg=ACCENT, fg="white",
                  relief="flat", padx=14, pady=5, state="normal" if areas else "disabled").pack(side="left", padx=(0, 8))
        tk.Button(bar, text="My sent updates", command=self.contrib_mine, bg=PANEL2, fg=FG, relief="flat", padx=12, pady=5).pack(side="left", padx=(0, 8))
        tk.Button(bar, text="Sign out", command=self.contrib_sign_out, bg=PANEL2, fg=FG, relief="flat", padx=12, pady=5).pack(side="left")

    def contrib_sign_in(self):
        self.write("Signing in to GitHub (a browser page may open the first time)...")

        def work():
            try:
                import launcher_contrib as lc
                token, login, areas = lc.sign_in()
            except Exception as e:
                self.lines.put(("line", f"Sign-in stopped: {e}"))
                return
            if not areas:
                self.lines.put(("line", f"Signed in as {login}, but {login} is not on the contributor list. Ask Hurami to add you."))
                return
            self.after(0, lambda: self.contrib_signed_in(login, areas))
        threading.Thread(target=work, daemon=True).start()

    def contrib_signed_in(self, login, areas):
        self.contributor = login
        self.app.cfg["contributor"], self.app.cfg["contributor_areas"] = login, areas
        try:
            save_config_value("contributor", login)
            save_config_value("contributor_areas", areas)
        except Exception as e:
            self.write(f"Could not save the sign-in: {e}")
        self.build_contributor()
        self.write(f"Contributor mode is on for {login}.")

    def contrib_sign_out(self):
        self.contributor = None
        for key in ("contributor", "contributor_areas", "contributor_mode"):
            self.app.cfg.pop(key, None)
            try:
                save_config_value(key, None)
            except Exception:
                pass
        self.build_contributor()
        self.write("Contributor mode is off.")

    def contrib_check(self, area, then=None):
        import launcher_contrib as lc
        self.write(f"Looking for your changed {lc.AREAS[area]['label']} files (the server can take a minute)...")

        def work():
            try:
                import launcher_contrib as lc
                token, login, areas = lc.sign_in()       # the list on GitHub decides, every time
                if area not in areas:
                    raise RuntimeError(f"{login} can't send {lc.AREAS[area]['label']} updates (not on the contributor list for it).")
                found = lc.check(token, area, self.app.cfg, kit_dir=HERE)
            except Exception as e:
                self.lines.put(("line", f"Could not check: {e}"))
                return
            d = found["diff"]
            self.lines.put(("line", f"{lc.AREAS[area]['label']} ({found['folder']}): " +
                            (f"{len(d['changed'])} changed, {len(d['added'])} new" if d["changed"] or d["added"] else "same as the released files")))
            for rel in d["changed"]:
                self.lines.put(("line", f"   changed  {rel}"))
            for rel in d["added"]:
                self.lines.put(("line", f"   new      {rel}"))
            if then:
                self.after(0, lambda: then(token, login, found))
        threading.Thread(target=work, daemon=True).start()

    def contrib_send_all(self):
        """One button: checks every area this contributor may send and opens one dialog with all their changes."""
        import launcher_contrib as lc
        self.write("Looking for everything you changed (the server folder can take a minute)...")

        def work():
            try:
                token, login, areas = lc.sign_in()       # the list on GitHub decides, every time
                if not areas:
                    raise RuntimeError(f"{login} is not on the contributor list.")
            except Exception as e:
                self.lines.put(("line", f"Could not check: {e}"))
                return
            founds = {}
            for area in areas:
                try:
                    founds[area] = lc.check(token, area, self.app.cfg, kit_dir=HERE)
                    d = founds[area]["diff"]
                    self.lines.put(("line", f"{lc.AREAS[area]['label']}: {len(d['changed'])} changed, {len(d['added'])} new"))
                except Exception as e:
                    self.lines.put(("line", f"{lc.AREAS[area]['label']}: skipped ({e})"))
            if founds:
                self.after(0, lambda: SendUpdateDialog(self.app, token, login, founds))
        threading.Thread(target=work, daemon=True).start()

    def contrib_send(self, area):
        def ready(token, login, found):
            if area == "gambits" and not (found["diff"]["changed"] or found["diff"]["added"]):
                messagebox.showinfo("Send update", "Nothing to send: your files are the same as the released ones.", parent=self)
                return
            SendUpdateDialog(self.app, token, login, area, found)
        self.contrib_check(area, then=ready)

    def contrib_mine(self):
        def work():
            try:
                import launcher_contrib as lc
                token, login, _ = lc.sign_in()
                mine = lc.my_updates(token, login)
            except Exception as e:
                self.lines.put(("line", f"Could not check: {e}"))
                return
            if not mine:
                self.lines.put(("line", "No sent updates waiting for review."))
            for number, title, url in mine:
                self.lines.put(("line", f"Waiting for review: #{number} {title}  {url}"))
        threading.Thread(target=work, daemon=True).start()

    # ----- player install: updates from the GitHub releases -----
    def build_player_updates(self):
        tk.Label(self, text="Updates", bg=BG, fg=FG, font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=14, pady=(8, 2))
        import launcher_update as lu
        have = lu.installed_version(HERE) or "self-built"
        tk.Label(self, text=(f"You have {have}. The launcher checks for a new version when it starts. Updating keeps your settings, "
                             "characters and squad mates; your database is saved first."),
                 bg=BG, fg=DIM, wraplength=900, justify="left", font=(UI_FONT, 9)).pack(anchor="w", padx=14, pady=(0, 6))
        bar = tk.Frame(self, bg=BG)
        bar.pack(anchor="w", padx=14)
        for text, command in (("Check for updates", lambda: self.player_check(False)), ("Update now", self.player_update),
                              ("Repair...", self.player_repair), ("Start the world over...", self.player_erase)):
            button = tk.Button(bar, text=text, command=command, bg=PANEL, fg=FG, relief="flat", padx=14, pady=6)
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
        self.test_builds = tk.BooleanVar(value=bool(self.app.cfg.get("test_builds", False)))
        tk.Checkbutton(bar, text="Get test builds (pre-releases)", variable=self.test_builds, command=self.save_test_builds,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG).pack(side="left", padx=(8, 0))
        tk.Label(bar, text="Beta groups:", bg=BG, fg=DIM).pack(side="left", padx=(14, 4))
        groups = self.app.cfg.get("beta_groups") or ""
        self.beta_groups = tk.StringVar(value=", ".join(groups) if isinstance(groups, list) else str(groups))
        entry = tk.Entry(bar, textvariable=self.beta_groups, width=24, bg=PANEL, fg=FG, insertbackground=FG, relief="flat")
        entry.pack(side="left")
        entry.bind("<FocusOut>", lambda _e: self.save_test_builds())
        entry.bind("<Return>", lambda _e: self.save_test_builds())
        self.update_info = None

    def save_test_builds(self):
        import json
        self.app.cfg["test_builds"] = bool(self.test_builds.get())
        self.app.cfg["beta_groups"] = [g.strip() for g in self.beta_groups.get().split(",") if g.strip()]
        try:
            path = os.path.join(HERE, "config.json")
            with open(path, encoding="utf-8-sig") as handle:
                cfg = json.load(handle)
            cfg["test_builds"] = self.app.cfg["test_builds"]
            cfg["beta_groups"] = self.app.cfg["beta_groups"]
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(cfg, handle, indent=2)
        except (OSError, ValueError) as e:
            self.write(f"Could not save the setting: {e}")

    def player_check(self, silent):
        """Looks for a newer version. silent: on start, only speaks up when there is one."""
        def work():
            try:
                import launcher_update as lu
                import launcher_thirdparty as tp
                info = lu.check(HERE, self.app.cfg.get("server_dir"), bool(self.app.cfg.get("test_builds")), tp._get)
            except Exception as e:
                if not silent:
                    self.lines.put(("line", f"Could not check for updates: {e}"))
                return
            self.update_info = info
            newer = [k for k in ("server", "kit") if info[k]["newer"]]
            if not silent or newer:
                for key, label in (("kit", "Launcher"), ("server", "Server")):
                    i = info[key]
                    size = lu.size_text(i.get("size")) if i["newer"] else ""
                    self.lines.put(("line", f"{label}: you have {i['installed'] or '?'}, newest {i['newest'] or 'none published'}"
                                            + (" - update available" if i["newer"] else "") + (f" (download {size})" if size else "")))
            if newer and silent:
                self.after(0, self.offer_update)
        threading.Thread(target=work, daemon=True).start()

    def offer_update(self):
        info = self.update_info
        newest = max((info[k]["newest"] for k in ("kit", "server") if info[k]["newer"]), key=lambda t: t or "")
        notes = next((info[k]["notes"] for k in ("kit", "server") if info[k]["newer"] and info[k]["notes"]), "")
        try:                     # (2026-11-24, Jaymz) the download size, for slow connections
            import launcher_update as lu
            size = lu.size_text(lu.download_size(info))
        except Exception:
            size = ""
        if messagebox.askyesno("Update available", f"XI: Forever Offline {newest} is out." + (f" Download: {size}." if size else "")
                               + f"\n\n{notes[:900]}\n\nUpdate now? "
                               "Your settings, characters and squad mates are kept, and your database is saved first."):
            self.player_update()

    def player_repair(self):
        """(2026-11-23, Reika, Ryan: an update stopped halfway, then the server stopped at PLAY, or "you have ?" and
        Update now did nothing) installs the newest launcher and server again over what is there, database update
        included, as an update would. Settings, characters and squad mates are kept; the database is saved first."""
        if self.app.running:
            messagebox.showwarning("Close the game first", "The servers are running. Close the game (it stops the servers), then repair.")
            return
        if self.busy:
            return
        if not messagebox.askyesno("Repair", "Install the newest launcher and server again, over the ones you have?\n\n"
                                   "Use this when an update stopped halfway, or the server stops at PLAY after one. Your "
                                   "settings, characters and squad mates are kept, and your database is saved first. "
                                   "The launcher restarts at the end.", parent=self):
            return

        def work():
            try:
                import launcher_update as lu
                import launcher_thirdparty as tp
                info = lu.check(HERE, self.app.cfg.get("server_dir"), bool(self.app.cfg.get("test_builds")), tp._get)
            except Exception as e:
                self.lines.put(("line", f"Could not reach the releases: {e}"))
                return
            for key in ("kit", "server"):
                info[key]["newer"] = bool(info[key].get("release"))
            self.update_info = info
            self.lines.put(("line", "Repair: installing " + ", ".join(
                f"{label} {info[key]['newest']}" for key, label in (("kit", "launcher"), ("server", "server")) if info[key]["newer"]) + " again..."))
            self.after(0, self.player_update)
        threading.Thread(target=work, daemon=True).start()

    def player_erase(self):
        """(2026-11-25, the user: "a server erase button ... that will erase everything, characters etc.") starts the
        world over: every character, squad, bot player and record goes; the game logins, launcher settings and add-ons
        stay. A full copy of the database is saved first (launcher_world_keep.erase_world)."""
        if self.app.running:
            messagebox.showwarning("Close the game first", "The servers are running. Close the game (it stops the servers), then start over.")
            return
        if self.busy:
            return
        cfg = self.app.cfg
        if not cfg.get("mariadb_dir") or not cfg.get("server_dir"):
            messagebox.showinfo("Start the world over", "This only works for a world with the kit's own database (a normal install).", parent=self)
            return
        typed = simpledialog.askstring(
            "Start the world over",
            "This erases EVERYTHING in your world: all your characters, their items and gil, your squad mates, the bot "
            "players, the auction house, linkshells, mail and Hardcore records. Characters away visiting another world "
            "are erased too.\n\nKept: your game logins (you sign in as before), the launcher's settings, add-ons and "
            "the character backup files.\n\nA full copy of the old world is saved first (backups\\world, "
            "db-before-erase-...).\n\nType ERASE to start over:", parent=self)
        if (typed or "").strip() != "ERASE":
            if typed is not None:
                messagebox.showinfo("Start the world over", "Nothing was erased (you need to type ERASE).", parent=self)
            return
        self.busy = True
        for button in self.buttons:
            button.configure(state="disabled")

        def work():
            started = None
            try:
                import launcher_setup
                import launcher_world_keep as wk
                started = launcher_setup.start_portable(cfg)
                wk.erase_world(cfg, HERE, cfg["server_dir"], log=lambda text: self.lines.put(("line", text)))
                done = "Your world was started over. Press PLAY and make a new character."
            except Exception as e:
                done = f"Your world was not started over: {e}"
            finally:
                if started is not None:
                    try:
                        launcher_setup.stop_portable(cfg)
                    except Exception:
                        pass
            self.lines.put(("line", done))

            def finish():
                self.busy = False
                for button in self.buttons:
                    button.configure(state="normal")
                messagebox.showinfo("Start the world over", done, parent=self)
            self.after(0, finish)
        threading.Thread(target=work, daemon=True).start()

    def player_update(self):
        if self.app.running:
            messagebox.showwarning("Close the game first", "The servers are running. Close the game (it stops the servers), then update.")
            return
        info = self.update_info
        if not info or not (info["kit"]["newer"] or info["server"]["newer"]):
            self.write("No update to install (press Check for updates first).")
            return
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.configure(state="disabled")
        cfg = self.app.cfg
        try:        # (Hasuko: "Update stopped: [WinError 5] Access is denied ... xifo_theme...mp3") the theme song's file stays
            import launcher_theme               # open while it plays and after it ends, and Windows will not replace an open
            launcher_theme.PLAYER.stop()        # file. Stopped here, on the window's own thread (the player belongs to it).
        except Exception:
            pass

        def work():
            restart = False
            try:
                import launcher_update as lu
                import launcher_thirdparty as tp
                import launcher_setup
                log = lambda m: self.lines.put(("line", m))
                if info["server"]["newer"]:
                    started = launcher_setup.start_portable(cfg)
                    if started is not None:
                        self.app.db_proc = started
                    lu.update_server(HERE, cfg, info["server"]["release"], tp._get, log=log)
                if info["kit"]["newer"]:
                    restart = lu.update_kit(HERE, info["kit"]["release"], tp._get, log=log)
                lu.refresh_pinned(HERE, cfg, tp._get, log=log)
                log("Update finished." + (" The launcher restarts now." if restart else ""))
            except Exception as e:
                self.lines.put(("line", f"Update stopped: {e}"))
            self.lines.put(("done", 0))
            if restart:
                self.after(1500, self.restart_launcher)
        threading.Thread(target=work, daemon=True).start()

    def restart_launcher(self):
        try:
            extra = {} if IS_WINDOWS else {"start_new_session": True}
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable], cwd=HERE, **extra)
            else:
                subprocess.Popen([sys.executable, os.path.join(HERE, "launcher_gui.pyw")], cwd=HERE, **extra)
        finally:
            self.app.on_close()

    def write(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def check(self):
        self.start(["check"])

    def update(self):
        if self.app.running:
            messagebox.showwarning("Close the game first", "The servers are running. Close the game (it stops the servers), then update.")
            return
        if messagebox.askyesno("Update", "Update the server to Phoenix's newest version?\n\nYour database is saved first. If anything clashes with our changes "
                                         "the update is cancelled and nothing changes. A rebuild can take up to half an hour."):
            self.start(["update"])

    def undo(self):
        if self.app.running:
            messagebox.showwarning("Close the game first", "The servers are running. Close the game (it stops the servers), then undo.")
            return
        answer = messagebox.askyesnocancel("Undo the last update",
                                           "Go back to the version from before the last update?\n\n"
                                           "Yes: also put the saved database back (anything you did in the game since then is lost).\n"
                                           "No: go back to the old code only and keep the database as it is.\n"
                                           "Cancel: do nothing.")
        if answer is None:
            return
        self.start(["undo"] + (["--restore-db"] if answer else []))

    def promote(self):
        name = simpledialog.askstring("Make a character a GM", "Character name (log that character out first):", parent=self)
        if name and name.strip():
            self.run_script("setup_gm.py", ["promote", name.strip(), "5"])

    def start(self, args):
        self.run_script("server_update.py", args)

    def run_script(self, script_name, args):
        if self.busy:
            return
        script = os.path.join(HERE, script_name)
        if not os.path.exists(script):
            self.write(f"{script_name} is missing from the launcher folder. Unpack the update zip again.")
            return
        self.busy = True
        for button in self.buttons[:3] + self.gm_buttons:
            button.configure(state="disabled")
        self.write("")
        self.write("---- " + script_name.replace(".py", "") + " " + " ".join(args) + " ----")
        threading.Thread(target=self.work, args=(script, args), daemon=True).start()

    def work(self, script, args):
        try:
            proc = subprocess.Popen(core.py_cmd(script, *args, unbuffered=True), cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace", creationflags=core.NO_WINDOW)
            for line in proc.stdout:
                self.lines.put(("line", line.rstrip()))
            self.lines.put(("done", proc.wait()))
        except Exception as problem:
            self.lines.put(("line", f"Could not run the update tool: {problem}"))
            self.lines.put(("done", 1))

    def pump(self):
        try:
            while True:
                kind, value = self.lines.get_nowait()
                if kind == "line":
                    self.write(value)
                else:
                    self.busy = False
                    for button in self.buttons + self.gm_buttons:
                        button.configure(state="normal")
        except queue.Empty:
            pass
        self.after(200, self.pump)


class SendUpdateDialog(tk.Toplevel):
    """Contributor mode: everything you changed (all your areas) in one list, a title and a note for Hurami, then Send
    (launcher_contrib.send_all: one pull request per repo)."""

    def __init__(self, app, token, login, founds, *legacy):
        super().__init__(app)
        import launcher_contrib as lc
        if legacy:                                   # old call: (area, found)
            founds = {founds: legacy[0]}
        self.app, self.lc, self.token, self.login, self.founds = app, lc, token, login, founds
        self.title("Send an update to Hurami")
        self.geometry("780x700")
        self.configure(bg=BG)
        self.q = queue.Queue()
        tk.Label(self, text="Files going in this update. Click a file to leave it out; Add files... for new ones.",
                 bg=BG, fg=FG, font=(UI_FONT, 10, "bold"), wraplength=740, justify="left").pack(anchor="w", padx=14, pady=(12, 2))
        box = tk.Frame(self, bg=BG)
        box.pack(fill="x", padx=14)
        self.files = tk.Listbox(box, selectmode="multiple", height=11, bg=PANEL, fg=FG, selectbackground=ACCENT, relief="flat",
                                font=(MONO_FONT, 9), activestyle="none", exportselection=False)
        scroll = tk.Scrollbar(box, command=self.files.yview)
        self.files.configure(yscrollcommand=scroll.set)
        self.files.pack(side="left", fill="x", expand=True)
        scroll.pack(side="left", fill="y")
        self.rows = []
        for area, found in founds.items():
            for rel in found["diff"]["changed"]:
                self.add_row(area, rel, "changed")
            for rel in found["diff"]["added"]:
                self.add_row(area, rel, "new")
        if not self.rows:
            self.files.insert("end", "(no changed files found: use Add files...)")
        row = tk.Frame(self, bg=BG)
        row.pack(anchor="w", padx=14, pady=(4, 0))
        tk.Button(row, text="Add files...", command=self.add_files, bg=PANEL, fg=FG, relief="flat", padx=12).pack(side="left")
        tk.Label(row, text="Launcher and Gambits files go to the kit repo, server files to the server repo (one review each).",
                 bg=BG, fg=DIM, font=(UI_FONT, 8)).pack(side="left", padx=10)
        tk.Label(self, text="Title (one line: what this update does)", bg=BG, fg=FG).pack(anchor="w", padx=14, pady=(10, 2))
        self.subject = tk.StringVar(value="")
        tk.Entry(self, textvariable=self.subject, bg=PANEL, fg=FG, insertbackground=FG, relief="flat").pack(fill="x", padx=14)
        tk.Label(self, text="Note for Hurami (what changed, how you tested it)", bg=BG, fg=FG).pack(anchor="w", padx=14, pady=(10, 2))
        self.note = tk.Text(self, height=6, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", wrap="word", font=(UI_FONT, 9))
        self.note.pack(fill="x", padx=14)
        bar = tk.Frame(self, bg=BG)
        bar.pack(anchor="w", padx=14, pady=8)
        self.go = tk.Button(bar, text="Send", command=self.send, bg=ACCENT, fg="white", relief="flat", padx=18)
        self.go.pack(side="left")
        self.links = []
        self.open_button = tk.Button(bar, text="Open on GitHub", command=lambda: [self.app.open_url(u) for u in self.links],
                                     bg=PANEL, fg=FG, relief="flat", padx=12, state="disabled")
        self.open_button.pack(side="left", padx=8)
        self.log = tk.Text(self, bg=PANEL, fg=FG, relief="flat", font=(MONO_FONT, 9), wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.after(200, self.pump)

    def add_row(self, area, rel, kind):
        if (area, rel) in self.rows:
            return
        if not self.rows:
            self.files.delete(0, "end")
        self.rows.append((area, rel))
        where = self.lc.AREAS[area].get("short", area)
        self.files.insert("end", f"{kind:<8} {where:<9} {rel}")
        self.files.selection_set("end")

    def add_files(self):
        start = next(iter(self.founds.values()))["folder"]
        paths = filedialog.askopenfilenames(parent=self, title="Add files to this update", initialdir=start)
        for path in paths or ():
            area = self.lc.area_for_path(self.founds, path)
            if area is None:
                folders = ", ".join(f["folder"] for f in self.founds.values())
                messagebox.showerror("Add files", f"{path} is not in one of your folders ({folders}).", parent=self)
                continue
            try:
                rel = self.lc.add_file(self.founds[area], path)
            except Exception as e:
                messagebox.showerror("Add files", str(e), parent=self)
                continue
            self.add_row(area, rel, "new" if rel in self.founds[area]["diff"]["added"] else "changed")

    def send(self):
        chosen = [self.rows[i] for i in self.files.curselection() if i < len(self.rows)]
        if not chosen:
            messagebox.showinfo("Send update", "Pick at least one file to send.", parent=self)
            return
        title = self.subject.get().strip()
        if len(title) < 4:
            messagebox.showinfo("Send update", "Add a title that says what the update does.", parent=self)
            return
        self.go.configure(state="disabled")
        note = self.note.get("1.0", "end").strip()

        def work():
            try:
                urls = self.lc.send_all(self.token, self.login, self.founds, chosen, title, note, log=lambda m: self.q.put(m))
                for url in urls:
                    self.q.put(("link", url))
                self.q.put("Sent! Hurami gets it on GitHub. You'll get GitHub notifications when he comments or merges it.")
            except Exception as e:
                self.q.put(f"Stopped: {e}")
                self.q.put(("again", None))
        threading.Thread(target=work, daemon=True).start()

    def pump(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple):
                    if item[0] == "link":
                        self.links.append(item[1])
                        self.open_button.configure(state="normal")
                    else:
                        self.go.configure(state="normal")
                    continue
                self.log.configure(state="normal")
                self.log.insert("end", item + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(200, self.pump)


class PublishDialog(tk.Toplevel):
    """Publish an update for players (dev PC). Shows the version, what changed and what is not ready yet; publishes after you confirm.
    The work is launcher_publish.publish."""

    def __init__(self, app):
        super().__init__(app)
        import launcher_publish as lpub
        self.app, self.lpub = app, lpub
        self.server = app.cfg["server_dir"]
        self.title("Publish an update for players")
        self.geometry("820x680")
        self.configure(bg=BG)
        self.q = queue.Queue()
        last = lpub.last_tag(HERE)
        top = tk.Frame(self, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(top, text=f"Last published: {last or 'nothing yet'}     New version:", bg=BG, fg=FG).pack(side="left")
        self.version = tk.StringVar(value=lpub.next_version(last))
        tk.Entry(top, textvariable=self.version, width=12, bg=PANEL, fg=FG, insertbackground=FG, relief="flat").pack(side="left", padx=6)
        self.prerelease = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="Test build (only players with 'Get test builds' on get it)", variable=self.prerelease,
                       bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG).pack(side="left", padx=(12, 0))
        tk.Label(self, text="Release notes (players see these). Filled in from your commit messages; edit them as you like.",
                 bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(anchor="w", padx=14)
        self.notes = tk.Text(self, height=10, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", wrap="word", font=(UI_FONT, 9))
        self.notes.pack(fill="x", padx=14, pady=4)
        lines = ["## What's new", ""] + [f"- {c}" for c in lpub.changes(HERE, last)]
        server_changes = lpub.changes(self.server, lpub.last_tag(self.server))
        if server_changes:
            lines += ["", "Server:"] + [f"- {c}" for c in server_changes]
        self.notes.insert("1.0", "\n".join(lines) + "\n")
        self.checks = tk.Label(self, text="", bg=BG, fg=FG, wraplength=780, justify="left", font=(UI_FONT, 9))
        self.checks.pack(anchor="w", padx=14, pady=4)
        bar = tk.Frame(self, bg=BG)
        bar.pack(anchor="w", padx=14, pady=4)
        tk.Button(bar, text="Check again", command=self.run_checks, bg=PANEL, fg=FG, relief="flat", padx=12).pack(side="left")
        self.go = tk.Button(bar, text="Publish", command=self.publish, bg=ACCENT, fg="white", relief="flat", padx=18)
        self.go.pack(side="left", padx=8)
        self.log = tk.Text(self, bg=PANEL, fg=FG, relief="flat", font=(MONO_FONT, 9), wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.run_checks()
        self.after(200, self.pump)

    def run_checks(self):
        problems, warnings = self.lpub.preflight(HERE, self.server, server_running=self.app.running)
        text = "\n".join(["Not ready: " + p for p in problems] + ["Check: " + w for w in warnings]) or "Ready to publish."
        self.checks.configure(text=text, fg=RED if problems else (GOLD if warnings else GREEN))
        self.go.configure(state="disabled" if problems else "normal")

    def publish(self):
        import re
        version = self.version.get().strip()
        if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
            messagebox.showinfo("Publish", "Use a version like v0.1.1.", parent=self)
            return
        kind = "a test build" if self.prerelease.get() else "a full release (every player is offered it)"
        if not messagebox.askyesno("Publish", f"Publish {version} as {kind}?\n\nThis will:\n"
                                   "1. build XI Forever Offline.exe\n2. make the server and player zips\n"
                                   f"3. tag both repos {version} and push the tags and the server's release branch\n"
                                   "4. create both GitHub releases and upload the files\n\nIt takes a while (the server zip is ~400 MB).",
                                   parent=self):
            return
        self.go.configure(state="disabled")
        notes = self.notes.get("1.0", "end").strip()

        def work():
            try:
                self.lpub.publish(HERE, self.server, version, notes, self.prerelease.get(), log=lambda m: self.q.put(m))
            except Exception as e:
                self.q.put(f"Stopped: {e}")
        threading.Thread(target=work, daemon=True).start()

    def pump(self):
        try:
            while True:
                line = self.q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(200, self.pump)


_LINUX_LOCK = None


def one_launcher_only_linux():
    """Linux: the same rule as one_launcher_only (a lock file in logs/ that goes away with the launcher's process)."""
    global _LINUX_LOCK
    for _ in range(15):                    # a launcher restarting itself after an update: the old one is still closing
        _LINUX_LOCK = linux.take_lock(HERE)
        if _LINUX_LOCK is not None:
            return True
        time.sleep(1)
    try:
        root = tk.Tk()
        root.withdraw()
        close_other = messagebox.askyesno(
            "XI: Forever Offline",
            "The launcher is already open (it may be behind other windows, or still closing).\n\n"
            "Yes = close the other one and its servers, and open this one.\nNo = keep the other one.", parent=root)
        root.destroy()
    except Exception:
        close_other = False
    if not close_other:
        return False
    other = linux.lock_holder(HERE)
    if other and other != os.getpid():
        linux.kill_tree(other)
    for n in core.SERVERS + ["xiloader"]:
        core.kill(n)
    core.kill_squad_chat()
    time.sleep(2)
    _LINUX_LOCK = linux.take_lock(HERE)
    return _LINUX_LOCK is not None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        linux_look(self)
        self.title("XI: Forever Offline")
        self.geometry("980x770")
        self.minsize(900, 420)          # the Play page is compact; the other pages set the taller window themselves
        self.configure(bg=BG)
        self._images = []   # keep pictures alive (Tk forgets a picture nobody holds on to)
        icon = load_image(os.path.join("ui", "icon.png")) or load_image("logo_icon.png") or load_image("logo.png")
        if icon:
            self._images.append(icon)
            try:
                self.iconphoto(True, icon)
            except Exception:
                pass
        self.cfg = core.load_config(os.path.join(HERE, "config.json"))
        self.db_proc = None
        if self.cfg.get("mariadb_dir"):     # a player install: the kit's own MariaDB has no Windows service, so start it now
            try:                            # (the Squad tab reads the mates from it); stopped again when the launcher closes
                import launcher_setup
                self.db_proc = launcher_setup.start_portable(self.cfg)
            except Exception as e:
                print(f"Could not start the database: {e}")
        if IS_WINDOWS and self.cfg.get("game_copy"):   # a game copy switch left in place by a crash: put PlayOnline back
            try:
                import launcher_game as lg
                if lg.pending_recovery(HERE) and not core.is_running("xiloader"):
                    run_elevated(["recover", os.path.join(HERE, lg.STATE_FILE)])
            except Exception as e:
                print(f"Could not put PlayOnline's settings back: {e}")
        self.q = queue.Queue()
        self.procs, self.logfiles = {}, []
        self.running, self.stop_requested = False, False
        self.scripts = None
        self.ashita = self.cfg.get("ashita_dir")
        self.rates = core.load_rates(HERE)
        self.boot_ini = os.path.join(self.ashita, "config", "boot", self.cfg.get("ashita_boot", core.DEFAULT_BOOT)) if self.ashita else None
        has_ini = bool(self.boot_ini) and os.path.exists(self.boot_ini)
        self.graphics = core.load_graphics(HERE, self.boot_ini if has_ini else None)
        self.gamepad = gp.load(HERE)
        self.new_ui = newui is not None and not self.cfg.get("classic_ui")
        if self.new_ui:
            newui.prepare(self, globals())
        self.build_ui()
        self.after(200, self.pump)
        self.after(1000, self.lights)
        self.after(1800, self.revamped_prompt)
        self.after(PICTURE_SECONDS * 1000, self.next_picture)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if self.cfg.get("game_update_needed"):     # installed with Square Enix's installer: its first update comes first
            self.after(700, self.first_game_update)

    def first_game_update(self):
        """(2026-11-24, the user: "we uploaded all the files to github but the launcher still directs to SE") the game's
        first update comes from XI: Forever Offline's own download; the PlayOnline login guide only if that can't be had."""
        if not self.offer_game_files("Your game hasn't had its first update yet (Square Enix's installer puts in an "
                                     "older version)."):
            PolUpdateGuide(self)

    # ----- UI -----
    def build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        # the page switcher is our own top bar, so the notebook's own tabs are hidden
        style.layout("Tabless.TNotebook.Tab", [])
        style.layout("Tabless.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
        style.configure("Tabless.TNotebook", background=BG, borderwidth=0)
        style.configure("TCombobox", fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=ACCENT,
                        bordercolor=BORDER, lightcolor=PANEL2, darkcolor=PANEL2, selectbackground=PANEL2, selectforeground=FG)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL2)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", PANEL2)], selectforeground=[("readonly", FG)])
        style.configure("TSpinbox", fieldbackground=PANEL2, background=PANEL2, foreground=FG, arrowcolor=ACCENT,
                        bordercolor=BORDER, lightcolor=PANEL2, darkcolor=PANEL2)
        # (Altair 2026-11-19: "Experience from monsters" was 0.0 and he never touched it) the mouse wheel changes a
        # number box or a drop-down under the pointer, so scrolling a page of settings quietly changed them: four
        # notches took the first rate from 1.0 to 0. The wheel no longer changes values; arrows and typing still do.
        for widget_class in ("TSpinbox", "TCombobox", "Spinbox"):
            for wheel in ("<MouseWheel>", "<Shift-MouseWheel>", "<Button-4>", "<Button-5>"):
                try:
                    self.unbind_class(widget_class, wheel)
                except tk.TclError:
                    pass
        style.configure("Vertical.TScrollbar", background=BORDER, troughcolor=BG, arrowcolor=DIM, bordercolor=BG,
                        lightcolor=BORDER, darkcolor=BORDER)
        style.configure("Solo.Horizontal.TProgressbar", troughcolor=PANEL, background=ACCENT, bordercolor=BORDER,
                        lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        self.option_add("*TCombobox*Listbox.background", PANEL2)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", BG)

        # bottom status bar (packed before the pages so it always keeps its room)
        bar = tk.Frame(self, bg=PANEL)
        bar.pack(side="bottom", fill="x")
        tk.Frame(bar, bg=BORDER, height=1).pack(fill="x")
        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(fill="x", padx=20, pady=7)
        self.summary_dot = tk.Label(inner, text="\u25cf", bg=PANEL, fg=GREY, font=(UI_FONT, 11))
        self.summary_dot.pack(side="left")
        self.summary = tk.StringVar(value="World asleep")
        tk.Label(inner, textvariable=self.summary, bg=PANEL, fg=FG, font=(UI_FONT, 9, "bold")).pack(side="left", padx=(4, 18))
        tk.Label(inner, text=f"Launcher v{VERSION}", bg=PANEL, fg=DIM, font=(UI_FONT, 9)).pack(side="right")

        # the page buttons: along the bottom of every page, just above the status bar (filled in by build_nav once every page exists)
        self.navbar = tk.Frame(self, bg=BG)
        self.navbar.pack(side="bottom", fill="x", pady=(0, 6))
        tk.Frame(self.navbar, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(0, 6))
        self.nav = tk.Frame(self.navbar, bg=BG)
        self.nav.pack()

        tabs = ttk.Notebook(self, style="Tabless.TNotebook")
        tabs.pack(fill="both", expand=True, padx=10, pady=(4, 6))
        self.tabs = tabs

        play = tk.Frame(tabs, bg=BG)
        tabs.add(play, text="  Play  ")
        homebox = tk.Frame(play, bg=BG)                     # everything on this page, kept in the middle of it
        homebox.pack(expand=True)
        self.showing_details = False

        # the big picture: a banner from assets\\press while nothing runs (changes by itself, a click shows the next),
        # the loading pictures while the game runs, or the server lights and log when LOGS is pressed
        self.stage = tk.Frame(homebox, bg=PANEL, width=GALLERY_W + 2, height=GALLERY_H + 2, highlightbackground=BORDER, highlightthickness=1)
        self.stage.pack(pady=(8, 0))
        self.stage.pack_propagate(False)
        banner = load_image("banner.png")
        self.heroes = load_press()
        self._images.extend(self.heroes)
        self.hero_index, self.hero_ticks = (random.randrange(len(self.heroes)) if self.heroes else 0), 0
        self.banner_label = tk.Label(self.stage, bg=PANEL, bd=0)
        if self.heroes:
            self.banner_label.configure(image=self.heroes[self.hero_index])
            if len(self.heroes) > 1:
                self.banner_label.configure(cursor="hand2")
                self.banner_label.bind("<Button-1>", lambda e: self.next_hero())
        elif banner:
            self._images.append(banner)
            self.banner_label.configure(image=banner)
        else:
            self.banner_label.configure(text="XI: FOREVER OFFLINE", fg=FG, font=("Georgia", 30, "bold"))
        # a one-time banner (assets\\press\\name__once.png): up for this start of the launcher only, until it is clicked; the next start is
        # back to the usual banners. It counts as shown once it has been on screen for a few seconds (or was clicked away).
        self.once_banner, self.once_name = load_once(self.cfg)
        if self.once_banner is not None:
            self._images.append(self.once_banner)
            self.banner_label.configure(image=self.once_banner, text="")
            if self.heroes:
                self.banner_label.configure(cursor="hand2")
                self.banner_label.bind("<Button-1>", lambda e: self.next_hero())
            self.after(4000, self.once_shown)
        self.pictures = load_gallery() + self.heroes
        self._images.extend(g for g in self.pictures if g not in self._images)
        self.picture_index = 0
        self.picture_label = tk.Label(self.stage, bg=PANEL, bd=0, cursor="hand2")
        if self.pictures:
            self.picture_label.configure(image=self.pictures[0])
            self.picture_label.bind("<Button-1>", lambda e: self.next_picture(manual=True))
        self.banner_label.pack(fill="both", expand=True)

        # the server lights and the activity log: kept out of the way until LOGS is pressed
        self.details = tk.Frame(self.stage, bg=PANEL)
        tk.Label(self.details, text="GAME SERVERS", bg=PANEL, fg=DIM, font=(UI_FONT, 8, "bold")).pack(anchor="w", padx=14, pady=(10, 0))
        row = tk.Frame(self.details, bg=PANEL)
        row.pack(anchor="w", padx=8, pady=(2, 6))
        self.dots = {}
        for n in core.SERVERS:
            f = tk.Frame(row, bg=PANEL)
            f.pack(side="left", padx=9)
            d = tk.Label(f, text="\u25cf", bg=PANEL, fg=GREY, font=(UI_FONT, 16))
            d.pack()
            tk.Label(f, text=n[3:], bg=PANEL, fg=DIM, font=(UI_FONT, 8)).pack()
            self.dots[n] = d
        tk.Label(self.details, text="ACTIVITY", bg=PANEL, fg=DIM, font=(UI_FONT, 8, "bold")).pack(anchor="w", padx=14, pady=(4, 2))
        self.log = tk.Text(self.details, height=14, width=96, bg=PANEL, fg=DIM, relief="flat", font=(MONO_FONT, 9), state="disabled", bd=0, highlightthickness=0)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        opener = tk.Label(self.details, text="Open logs folder", bg=PANEL, fg=ACCENT, cursor="hand2", font=(UI_FONT, 9, "underline"))
        opener.pack(anchor="w", padx=14, pady=(0, 8))
        opener.bind("<Button-1>", lambda e: self.open_dir(LOGS))

        # what is happening, with the loading bar beside it
        strip = tk.Frame(homebox, bg=BG)
        strip.pack(fill="x", padx=2, pady=(10, 6))
        self.status = tk.StringVar(value=PRESS_NOTE or "Ready when you are.")
        tk.Label(strip, textvariable=self.status, bg=BG, fg=FG, font=(UI_FONT, 11), anchor="w").pack(side="left", fill="x", expand=True)
        from launcher_widgets import CrystalLoader
        self.progress = CrystalLoader(strip, width=380)   # (2026-11-21) a crystal wave instead of the sliding bar
        self.progress.pack(side="right")

        # PLAY, STOP and DUALBOX, then UPDATE and LOGS (pictures in assets\\ui; plain text buttons if they are missing)
        main_row = tk.Frame(homebox, bg=BG)
        main_row.pack(pady=(8, 6))
        self.play_btn = self.ui_button(main_row, "play", self.play_pressed, "PLAY")      # (2026-11-25) the character cards first
        self.play_btn.pack(side="left", padx=10)
        self.stop_btn = self.ui_button(main_row, "stop", self.stop, "STOP")
        self.stop_btn.pack(side="left", padx=10)
        self.stop_btn.configure(state="disabled")
        # a second character in a second game window (set up once with setup_dualbox.py)
        self.dual_btn = self.ui_button(main_row, "dualbox", self.start_second, "DUALBOX")
        self.dual_btn.pack(side="left", padx=10)
        actions = tk.Frame(homebox, bg=BG)
        actions.pack(pady=(4, 0))
        self.update_btn = self.ui_button(actions, "update", self.check_updates, "UPDATE")
        self.update_btn.pack(side="left", padx=6)
        self.logs_btn = self.ui_button(actions, "logs", self.toggle_details, "LOGS")
        if not self.cfg.get("mariadb_dir"):              # players don't need the server log; the status line says what happens
            self.logs_btn.pack(side="left", padx=6)

        # Squad tab
        self.squad_tab = None
        if sq is not None and "db_user" in self.cfg and "db_name" in self.cfg:
            try:
                import mariadb  # noqa: F401  (comes with the server's Python requirements)
                self.squad_tab = SquadTab(tabs, self.cfg)
                self.squad_tab.is_running = lambda: self.running
                tabs.add(self.squad_tab, text="  Squad  ")
            except ImportError:
                self.add_note(tabs, "Squad", "The Squad tab needs the Python 'mariadb' package.\nRun:  python -m pip install mariadb")
        else:
            self.add_note(tabs, "Squad", "The Squad tab needs db_user, db_pass and db_name in config.json.")

        # Rates tab
        self.rates_tab = RatesTab(tabs, self.rates, player=bool(self.cfg.get("mariadb_dir")))
        if self.squad_tab is not None:
            self.squad_tab.all_gear_var = self.rates_tab.squad_all_gear
        if not self.new_ui:                    # the newer World and Rules pages show these settings instead (launcher_pages.py)
            tabs.add(self.rates_tab, text="  Rates  ")

        # Graphics tab (needs the Ashita boot file)
        self.graphics_tab = None
        if self.boot_ini and os.path.exists(self.boot_ini):
            self.graphics_tab = GraphicsTab(tabs, self.graphics, self.boot_ini)
            tabs.add(self.graphics_tab, text="  Graphics  ")
        else:
            self.add_note(tabs, "Graphics", "The Graphics tab needs ashita_dir and ashita_boot in config.json to point at your Ashita boot file.")

        # Controller tab (2026-11-22): controller setup in the boot file, instead of FFXI's own gamepad tool
        self.pad_tab = None
        if self.boot_ini and os.path.exists(self.boot_ini):
            self.pad_tab = ControllerTab(tabs, self.gamepad)
            tabs.add(self.pad_tab, text="  Controller  ")

        # Shaders tab: dgVoodoo + ReShade (Windows; on Linux Proton's own DXVK draws the game)
        self.gfx_tab = None
        if IS_WINDOWS:
            self.gfx_tab = GfxModTab(tabs, HERE, self.cfg)
            tabs.add(self.gfx_tab, text="  Shaders  ")

        # Updates tab: new Phoenix versions
        self.updates_tab = UpdatesTab(tabs, self)
        tabs.add(self.updates_tab, text="  Settings  ")

        # Co-op tab (experimental): host your world for friends, or visit a friend's (launcher_coop_gui.py)
        self.coop_tab, self.visit, self.visit_mode = None, None, False
        if coopgui is not None and "db_user" in self.cfg and "db_name" in self.cfg:
            try:
                import mariadb  # noqa: F401
                self.coop_tab = coopgui.CoopTab(tabs, self, ImageButton)
                tabs.add(self.coop_tab, text="  Co-op  ")
            except Exception as e:
                self.coop_tab = None
                print(f"The Co-op page could not be made: {e}")

        # Addons / Plugins tabs
        self.lists = []
        if self.ashita and os.path.isdir(self.ashita):
            try:
                self.scripts = core.ScriptManager(self.ashita, self.cfg.get("ashita_boot", core.DEFAULT_BOOT))
                self.scripts.prepare()
            except Exception as e:
                self.scripts = None
                self.add_note(tabs, "Addons", f"Could not set up addon control:\n{e}")
        else:
            self.add_note(tabs, "Addons", "Set ashita_dir in config.json to manage addons here.")
        if self.scripts:
            self.list_target = tk.StringVar(value="main")
            self.hints = []
            self.second_scripts = None
            for kind, title, folder in (("addon", "  Addons  ", "addons"), ("plugin", "  Plugins  ", "plugins")):
                page = tk.Frame(tabs, bg=BG)
                tabs.add(page, text=title)
                hint = tk.Label(page, text=LIST_HINT_MAIN, bg=BG, fg=DIM, font=(UI_FONT, 9))
                hint.pack(anchor="w", padx=10, pady=(10, 4))
                self.hints.append(hint)
                picker = tk.Frame(page, bg=BG)
                picker.pack(anchor="w", padx=10, pady=(0, 4))
                tk.Label(picker, text="List for:", bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(side="left")
                for value, text in (("main", "Main window"), ("second", "Second window (dualbox)")):
                    tk.Radiobutton(picker, text=text, value=value, variable=self.list_target, command=self.switch_list_target,
                                   bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                                   font=(UI_FONT, 10)).pack(side="left", padx=(10, 0))
                if kind == "addon":
                    self.build_interface_row(page)
                lst = CheckList(page, kind, self.scripts)
                lst.pack(fill="both", expand=True, padx=6)
                self.lists.append(lst)
                bar = tk.Frame(page, bg=BG)
                bar.pack(pady=8)
                tk.Button(bar, text="Refresh", command=lst.reload, bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left", padx=4)
                tk.Button(bar, text=f"Open {folder} folder", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=lambda f=folder: self.open_dir(os.path.join(self.ashita, f))).pack(side="left", padx=4)
                tk.Button(bar, text="Add addon or plugin...", relief="flat", bg=ACCENT, fg="white", padx=12,
                          command=lambda: self.add_user_item(folder=False)).pack(side="left", padx=(12, 4))
                tk.Button(bar, text="Add a folder...", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=lambda: self.add_user_item(folder=True)).pack(side="left", padx=4)
        if tp is not None and os.path.exists(os.path.join(HERE, "thirdparty.json")):
            self.build_downloads_page(tabs)
        if self.new_ui:                        # World, Rules, the new bar (launcher_pages.py takes over build_nav, show_subnav, fit_window)
            try:
                newui.build(self, tabs)
            except Exception:                  # anything wrong with the newer pages: the classic ones, so the launcher always opens
                self.new_ui = False
                try:
                    os.makedirs(LOGS, exist_ok=True)
                    with open(os.path.join(LOGS, "new-pages-error.log"), "w") as f:
                        f.write(traceback.format_exc())
                except OSError:
                    pass
                tabs.add(self.rates_tab, text="  Rates  ")
        self.build_nav()

    def ui_button(self, parent, name, command, text):
        images = load_ui_images(name)
        self._images.extend(i for i in images.values() if i)
        return ImageButton(parent, images, command, text)

    def go(self, name):
        """Opens a page by its name (Rates, Addons, Settings...)."""
        index = getattr(self, "page_index", {}).get(name)
        if index is not None:
            self.select_tab(index)

    def check_updates(self):
        """The UPDATE button: opens Settings and asks whether Phoenix has new commits (it only looks, it changes nothing)."""
        self.go("Settings")
        tab = getattr(self, "updates_tab", None)
        if tab is not None:
            if tab.player:             # a player install checks for our releases, not Phoenix's git history
                tab.player_check(False)
            else:
                tab.check()

    def second_manager(self):
        """The second window's addon/plugin list: (manager, "") or (None, why it is not available)."""
        if getattr(self, "second_scripts", None) is not None:
            return self.second_scripts, ""
        boot2 = self.cfg.get("ashita_boot2")
        path = os.path.join(self.ashita, "config", "boot", boot2) if (self.ashita and boot2) else ""
        if not path or not os.path.exists(path):
            return None, "The second window is not set up yet. In PowerShell, in " + HERE + ", run:   python setup_dualbox.py setup"
        try:
            manager = core.ScriptManager(self.ashita, boot2, script_name="dualbox.txt")
            manager.prepare()
        except Exception as e:
            return None, f"Could not read the second window's script: {e}"
        self.second_scripts = manager
        return manager, ""

    def add_user_item(self, folder=False):
        """Install an addon or plugin the player has: a .zip, a plugin .dll, or an addon folder."""
        if folder:
            path = filedialog.askdirectory(title="Choose the addon's folder (the one with <name>.lua in it)")
        else:
            path = filedialog.askopenfilename(title="Choose an addon or plugin",
                                              filetypes=[("Addon or plugin", "*.zip *.dll"), ("Zip file", "*.zip"), ("Plugin", "*.dll")])
        if not path:
            return
        try:
            done = core.install_user_item(self.ashita, path, os.path.join(HERE, "backups", "addons"))
        except Exception as e:
            messagebox.showerror("Add addon or plugin", str(e))
            return
        core.remember_added(HERE, [name for _kind, name in done])
        names = ", ".join(f"{name} ({kind})" for kind, name in done)
        if messagebox.askyesno("Add addon or plugin", f"Installed: {names}.\n\nLoad it in your main game window from the next PLAY?"):
            for kind, name in done:
                try:
                    self.scripts.set(kind, name, True)
                except Exception as e:
                    messagebox.showerror("Add addon or plugin", str(e))
        for lst in self.lists:
            lst.reload()
        self.say(f"Added {names}. Anything it replaced is saved in backups\\addons.")

    def build_interface_row(self, page):
        """XIUI (an addon, stable) or XIUIplus (a plugin, alpha): the party list, target bar and other windows."""
        row = tk.Frame(page, bg=BG)
        row.pack(anchor="w", padx=10, pady=(0, 4))
        tk.Label(row, text="Interface:", bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(side="left")
        try:
            now = core.interface_of(self.scripts)
        except Exception:
            now = "none"
        self.interface_var = tk.StringVar(value=now)
        for key, text in (("xiui", "XIUI (stable addon)"), ("xiuiplus", "XIUIplus (alpha plugin)"), ("none", "Neither")):
            tk.Radiobutton(row, text=text, value=key, variable=self.interface_var, command=self.set_interface,
                           bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                           font=(UI_FONT, 10)).pack(side="left", padx=(10, 0))

    def set_interface(self):
        choice = self.interface_var.get()
        try:
            core.set_interface(self.scripts, choice)
        except Exception as e:
            messagebox.showerror("Interface", f"Could not change the interface: {e}")
            return
        for lst in self.lists:
            lst.reload()
        names = {"xiui": "XIUI", "xiuiplus": "XIUIplus", "none": "no interface addon"}
        self.say(f"Main window: {names.get(choice, choice)} from the next PLAY.")

    def switch_list_target(self):
        second = self.list_target.get() == "second"
        manager, why = self.second_manager() if second else (self.scripts, "")
        for lst in self.lists:
            lst.use(manager, why)
        for hint in self.hints:
            hint.configure(text=LIST_HINT_SECOND if second else LIST_HINT_MAIN)

    def build_nav(self):
        # The page buttons along the bottom: HOME, SQUADS, CONFIG, TOOLS, SETTINGS, then EXIT a little apart. A button for several pages
        # (CONFIG: Rates, Graphics, Shaders; TOOLS: Addons, Plugins) opens the page you were last on in it, and a thin row of page names at
        # the top of the page switches between them. A page that is in no group gets a MORE button, so nothing is ever unreachable.
        self.page_index = {self.tabs.tab(tab_id, "text").strip(): index for index, tab_id in enumerate(self.tabs.tabs())}
        placed, groups = set(), []
        for image, title, names in NAV_BUTTONS:
            members = [(name, self.page_index[name]) for name in names if name in self.page_index]
            if members:
                groups.append((image, title, members))
                placed.update(name for name, _ in members)
        leftover = [(name, index) for name, index in self.page_index.items() if name not in placed]
        if leftover:
            groups.append(("more", "MORE", leftover))
        self.subnav = tk.Frame(self, bg=BG)
        self.nav_groups = []
        for image, title, members in groups:
            group = {"title": title, "members": members, "last": members[0][1]}
            group["button"] = self.ui_button(self.nav, image, lambda g=group: self.select_tab(g["last"]), title)
            group["button"].pack(side="left", padx=3)
            self.nav_groups.append(group)
        self.exit_btn = self.ui_button(self.nav, "exit", self.on_close, "EXIT")
        self.exit_btn.pack(side="left", padx=(20, 3))
        self.select_tab(0)

    def select_tab(self, index):
        self.tabs.select(index)
        self.current_index = index
        current = None
        for group in self.nav_groups:
            on = any(i == index for _name, i in group["members"])
            group["button"].set_active(on)
            if on:
                group["last"] = index
                current = group
        self.show_subnav(current, index)
        self.fit_window()

    def fit_window(self):
        """One window size for every page: the Play page has the big picture (LOGS shows the log in its place).
        With the CO-OP button in the bottom bar the window is a little wider, so the bar fits."""
        page = self.tabs.tab(getattr(self, "current_index", 0), "text").strip() if self.tabs.tabs() else ""
        width, height = (1100 if getattr(self, "coop_tab", None) is not None else 980), 810
        if page.upper().startswith("CO-OP") or page.lower().startswith("co-op"):     # (2026-11-23) the worlds page is roomier
            width, height = 1240, 900
        if linux is not None:     # the Steam Deck's screen is 1280 x 800: never taller (or wider) than the screen
            width = min(width, self.winfo_screenwidth())
            height = min(height, self.winfo_screenheight() - (0 if linux.in_game_mode() else 40))
            if linux.in_game_mode():
                # (2026-11-22, Sunie) Game Mode stretches any window over the whole screen, so a window of another
                # shape was drawn stretched, with parts off the panel. Be exactly the screen's size there.
                width, height = self.winfo_screenwidth(), self.winfo_screenheight()
        # (2026-11-22, Starfret: a window made bigger by hand snapped back on every page) after the first fit only grow it
        if getattr(self, "_fitted", False):
            try:
                if self.state() == "zoomed" or (self.winfo_width() >= width and self.winfo_height() >= height):
                    return
                width, height = max(width, self.winfo_width()), max(height, self.winfo_height())
            except tk.TclError:
                pass
        self._fitted = True
        self.geometry(f"{width}x{height}")

    def show_subnav(self, group, index):
        """The pages of the open group as small buttons at the top of the page (nothing for a group of one page)."""
        for child in self.subnav.winfo_children():
            child.destroy()
        if group is None or len(group["members"]) < 2:
            self.subnav.pack_forget()
            return
        for name, page in group["members"]:
            on = page == index
            label = tk.Label(self.subnav, text=name.upper(), bg=PANEL2 if on else PANEL, fg=ACCENT if on else DIM, font=(UI_FONT, 9, "bold"),
                             padx=16, pady=5, cursor="hand2", highlightbackground=ACCENT if on else BORDER, highlightthickness=1)
            label.pack(side="left", padx=(0, 6))
            label.bind("<Button-1>", lambda e, i=page: self.select_tab(i))
        self.subnav.pack(fill="x", padx=18, pady=(10, 2), before=self.tabs)

    # ----- Downloads: other people's add-ons and tools, from their official releases (thirdparty.json) -----
    def build_downloads_page(self, tabs):
        page = tk.Frame(tabs, bg=BG)
        tabs.add(page, text="  Other  ")
        tk.Label(page, text="Add-ons and tools made by other people. Each one comes straight from its author's own release page; "
                 "files it replaces are saved in backups\\thirdparty first, and your settings are never overwritten.",
                 bg=BG, fg=DIM, font=(UI_FONT, 9), wraplength=880, justify="left").pack(anchor="w", padx=10, pady=(10, 6))
        bar = tk.Frame(page, bg=BG)
        bar.pack(anchor="w", padx=10, pady=(0, 6))
        tk.Button(bar, text="Refresh", command=self.show_downloads, bg=PANEL, fg=FG, relief="flat", padx=10).pack(side="left")
        tk.Button(bar, text="Check for newer versions", command=self.check_download_updates, bg=PANEL, fg=FG, relief="flat",
                  padx=10).pack(side="left", padx=6)
        box = tk.Frame(page, bg=BG)
        box.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        canvas = tk.Canvas(box, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        self.dl_rows = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=self.dl_rows, anchor="nw")
        self.dl_rows.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(4, 0))
        scroll.pack(side="right", fill="y")
        self.dl_busy = False
        self.show_downloads()
        self.after(5000, self.check_downloads_quietly)

    def show_downloads(self, newer=None):
        for widget in self.dl_rows.winfo_children():
            widget.destroy()
        try:
            items = tp.load_manifest(HERE)
        except Exception as e:
            tk.Label(self.dl_rows, text=f"thirdparty.json could not be read: {e}", bg=BG, fg=RED).pack(anchor="w")
            return
        state = tp.load_state(HERE)
        if not self.cfg.get("mariadb_dir"):       # a self-built (dev) server is never replaced by the release package
            items = [item for item in items if item.get("into") != "server"]
        if getattr(self, "dl_filter", None) is not None:      # the newer look lists addons and plugins on their own pages
            items = [item for item in items if self.dl_filter(item)]
        for row, item in enumerate(items):
            installed, version = tp.status(item, HERE, self.ashita, state, server=self.cfg.get("server_dir"))
            tk.Label(self.dl_rows, text=item["name"], bg=BG, fg=FG, font=(UI_FONT, 10, "bold"), anchor="w").grid(
                row=row * 2, column=0, sticky="w", pady=(6, 0))
            text = ("installed " + version) if installed else "not installed"
            if newer and newer.get(item["id"]) and tp.is_newer(newer[item["id"]], version):
                text += f"  (newer: {newer[item['id']]})"
            tk.Label(self.dl_rows, text=text, bg=BG, fg=GREEN if installed else DIM, anchor="w").grid(
                row=row * 2, column=1, sticky="w", padx=10, pady=(6, 0))
            page_only = item["source"]["type"] == "page"
            label = "Open download page" if page_only else ("Reinstall / update" if installed else "Install")
            tk.Button(self.dl_rows, text=label, relief="flat", bg=PANEL if installed else ACCENT, fg=FG if installed else "white",
                      padx=10, command=lambda i=item: self.install_download(i)).grid(row=row * 2, column=2, sticky="w", pady=(6, 0))
            if item.get("apply") == "era_dats" and installed:
                tk.Button(self.dl_rows, text="Apply to the game", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=self.apply_era_dats).grid(row=row * 2 + 1, column=2, sticky="w")
            if item.get("polplugin") and installed and self.boot_ini and os.path.exists(self.boot_ini):
                on = core.polplugin_on(self.boot_ini, item["polplugin"])
                tk.Button(self.dl_rows, text=("On - turn off" if on else "Off - turn on"), relief="flat",
                          bg=PANEL, fg=GREEN if on else FG, padx=10,
                          command=lambda i=item, v=not on: self.toggle_polplugin(i, v)).grid(row=row * 2 + 1, column=2, sticky="w")
            if item.get("patch") and installed:
                tk.Button(self.dl_rows, text="Apply era edits", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=lambda i=item: self.apply_download_patch(i)).grid(row=row * 2 + 1, column=2, sticky="w")
            # (lilibun, 2026-11-22) the two big ones can be taken out again: the AI model, and the Ollama this launcher installed
            if installed and item["source"]["type"] == "ollama_model":
                tk.Button(self.dl_rows, text="Remove", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=lambda i=item: self.remove_ai_model(i)).grid(row=row * 2 + 1, column=2, sticky="w")
            if installed and item["id"] == "ollama":
                tk.Button(self.dl_rows, text="Remove", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=lambda i=item: self.remove_ollama(i)).grid(row=row * 2 + 1, column=2, sticky="w")
            link = tk.Label(self.dl_rows, text="home page", bg=BG, fg=ACCENT, cursor="hand2")
            link.grid(row=row * 2, column=3, sticky="w", padx=10, pady=(6, 0))
            if installed and not item.get("required") and (state.get(item["id"]) or {}).get("files"):
                tk.Button(self.dl_rows, text="Uninstall", relief="flat", bg=PANEL, fg=FG, padx=10,
                          command=lambda i=item: self.uninstall_download(i)).grid(row=row * 2, column=4, sticky="w", pady=(6, 0))
            link.bind("<Button-1>", lambda e, url=item["homepage"]: self.open_url(url))
            if item["id"] == "xipivot":             # (2026-11-22) HD texture packs: what most players want XIPivot for
                tk.Button(self.dl_rows, text="HD packs and music...", relief="flat", bg=PANEL, fg=GOLD, padx=10,
                          command=self.open_hd_packs).grid(row=row * 2 + 1, column=3, sticky="w", padx=10)
            info = f"by {item['author']} - license: {item['license']}" + (f" - {item['note']}" if item.get("note") else "")
            # (the description spans the name and status columns only: across all four it was drawn over the
            #  buttons in column 2 of this row, e.g. XIPivot's on/off switch, sparkiie 2026-11-17)
            tk.Label(self.dl_rows, text=info, bg=BG, fg=DIM, font=(UI_FONT, 9), anchor="w", wraplength=520,
                     justify="left").grid(row=row * 2 + 1, column=0, columnspan=2, sticky="w")

    def open_hd_packs(self):
        """(2026-11-22, the user) HD texture packs through XIPivot: the player downloads a pack from Nexus Mods himself;
        the window (launcher_hd_gui.py) finds the file, unpacks it into Ashita's XIPivot folder and switches it on."""
        try:
            import launcher_hd_gui
            window = launcher_hd_gui.open_window(
                self, HERE, self.ashita, self.boot_ini,
                {"bg": BG, "panel": PANEL, "fg": FG, "dim": DIM, "accent": ACCENT, "green": GREEN, "red": RED, "gold": GOLD, "font": UI_FONT},
                say=self.say, running=lambda: bool(getattr(self, "running", False)), core=core)

            def closed(event):                      # XIPivot's own switch on this page may have changed meanwhile
                if event.widget is window:
                    try:
                        self.show_downloads()
                    except Exception:
                        pass
            window.bind("<Destroy>", closed, add="+")
        except Exception as e:
            messagebox.showerror("HD texture packs", f"The HD texture packs window could not be opened: {e}")

    def toggle_polplugin(self, item, on):
        try:
            core.set_polplugin(self.boot_ini, item["polplugin"], on)
            if on and item["polplugin"] == "pivot" and self.ashita:
                core.pivot_first_config(self.ashita)
            self.say(f"{item['name']} is now {'on' if on else 'off'} (from the next PLAY).")
        except Exception as e:
            self.say(f"Could not change {item['name']} ({e}).")
        self.show_downloads()

    def remove_ai_model(self, item):
        """(lilibun, 2026-11-22) ollama rm: gives back the disk space of the AI model (several GB)."""
        model = item["source"]["model"]
        if self.running:
            messagebox.showinfo("Remove " + item["name"], "Close the game first: the AI chat may be using the model.")
            return
        if not messagebox.askyesno("Remove " + item["name"],
                                   f"Delete the AI model {model} from this PC?\n\nIt frees several GB. Squad and town chat "
                                   "then use their short built-in lines until a model is installed again."):
            return
        self.say(f"Removing the AI model {model}...")

        def work():
            try:
                tp.remove_model(model)
                done = f"The AI model {model} was removed."
            except Exception as e:
                done = f"The AI model was not removed: {e}"
            self.say(done)
            self.after(0, self.show_downloads)
            self.after(0, lambda: messagebox.showinfo("Remove " + item["name"], done))
        threading.Thread(target=work, daemon=True).start()

    def remove_ollama(self, item):
        """(lilibun, 2026-11-22) Takes out the Ollama this launcher installed: Windows opens Ollama's own uninstaller,
        Linux deletes the copy in the install folder. The models it downloaded only when you say so."""
        if self.running:
            messagebox.showinfo("Remove Ollama", "Close the game first.")
            return
        if not messagebox.askyesno("Remove Ollama", "Remove Ollama, the local AI program, from this PC?\n\nSquad and town chat then "
                                                    "use their short built-in lines. On Windows, Ollama's own uninstaller "
                                                    "opens and you finish it there."):
            return
        size = core.path_size(tp.ollama_models_dir())
        models = size > 0 and messagebox.askyesno("Remove Ollama", f"Also delete the AI models it downloaded ({core.size_text(size)})?"
                                                                   "\n\nChoose No if you use Ollama for other things too.")
        try:
            self.unload_ollama()
            ours = getattr(self, "ollama_proc", None)
            if ours is not None and ours.poll() is None:
                ours.terminate()
            self.ollama_proc = None
            tp.remove_ollama(HERE, models=models, log=self.say)
        except Exception as e:
            messagebox.showerror("Remove Ollama", str(e))
        self.show_downloads()

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def install_download(self, item):
        if item["source"]["type"] == "page":
            self.open_url(item["source"]["url"])
            self.say(f"{item['name']}: opened its download page. Unpack it into {os.path.join(self.ashita or '', 'addons')}.")
            return
        if self.dl_busy:
            self.say("A download is already running.")
            return
        # (2026-11-23) a big download (XISpeaks, about 2.9 GB) asks first, so nobody fetches gigabytes by one stray click
        if item.get("confirm") and not messagebox.askyesno("Downloads", item["confirm"]):
            return
        if item.get("into") == "server" and self.running:
            messagebox.showinfo("Downloads", "Stop the servers first (close the game), then update the server.")
            return
        if item.get("into", "ashita") == "ashita" and not self.ashita:
            messagebox.showinfo("Downloads", "Set the Ashita folder first (ashita_dir in config.json).")
            return
        if self.running and item.get("into", "ashita") == "ashita":
            if not messagebox.askyesno("Downloads", "The game is running. Install anyway? It takes effect the next time the game starts."):
                return
        self.dl_busy = True

        self.say(f"{item['name']}: downloading...")

        def work():
            # (Altair 2026-11-19: Reinstall / update showed nothing, its lines only went to the LOGS panel on the Play page)
            try:
                version = tp.install(item, HERE, self.ashita, log=self.say, server=self.cfg.get("server_dir"),
                                     keep_download=bool(self.cfg.get("keep_downloads", False)),
                                     remove_old=bool(self.cfg.get("remove_old_files", True)))
                done = f"{item['name']} {version} is ready."
            except Exception as e:
                done = f"{item['name']}: not installed ({e})."
            self.dl_busy = False
            self.say(done)
            self.after(0, self.show_downloads)
            self.after(0, lambda: messagebox.showinfo("Add-ons", done))
        threading.Thread(target=work, daemon=True).start()

    def uninstall_download(self, item):
        if self.running:
            messagebox.showinfo("Downloads", "Close the game first.")
            return
        if not messagebox.askyesno("Downloads", f"Remove {item['name']}? The files it installed are copied to backups\\thirdparty first; "
                                   "your own settings and files are left alone."):
            return
        try:
            tp.uninstall(item, HERE, self.ashita, server=self.cfg.get("server_dir"), log=self.say)
        except Exception as e:
            messagebox.showinfo("Downloads", f"{item['name']}: not removed ({e}).")
        self.show_downloads()

    def apply_download_patch(self, item):
        try:
            for line in tp.apply_patch(HERE, self.ashita, item["patch"]):
                self.say(f"{item['name']}: {line}")
            self.say(f"{item['name']}: reload it in game (/addon reload {item['id']}).")
        except Exception as e:
            messagebox.showinfo("Downloads", f"{item['name']}: {e}")

    def apply_era_dats(self):
        if self.running:
            messagebox.showinfo("Era-DATs", "Close the game first.")
            return
        if not messagebox.askyesno("Era-DATs", "Copy the Era-DATs into your FFXI folder? The files they replace are saved in "
                                   "dat-backup first; restore-original-dats.ps1 puts them back."):
            return

        def work():
            try:
                import launcher_setup
                for line in launcher_setup.install_era_dats(HERE, self.cfg.get("ffxi_client_dir", ""), log=self.say):
                    self.say(line)
            except Exception as e:
                self.say(f"Era-DATs: not installed ({e}).")
        threading.Thread(target=work, daemon=True).start()

    def check_download_updates(self, quiet=False):
        """The "Check for newer versions" button (always asks GitHub), and the quiet check at launcher start (quiet=True:
        asks at most every 6 hours, speaks only in the log, never in a pop-up)."""
        def work():
            try:
                items = tp.load_manifest(HERE)
                versions = tp.installed_versions(items, HERE, self.ashita, self.cfg.get("server_dir"))
                newer, problems, asked = tp.check_downloads(HERE, items, versions, force=not quiet)
            except Exception as e:
                newer, problems, asked = {}, [f"The check stopped: {e}"], True
            for line in problems:                 # (a limit GitHub sets, no network, ...) said out loud, never "nothing newer"
                self.say(line)
            if quiet:
                if newer:
                    names = {i["id"]: i["name"] for i in items}
                    self.say("Newer versions are out for: " + ", ".join(names.get(k, k) for k in newer)
                             + " (Downloads: Reinstall / update).")
            else:
                self.say("Checked the release pages for newer versions." if not problems else
                         "The check for newer versions could not be finished (see above).")
                if problems:
                    self.after(0, lambda: messagebox.showinfo("Check for newer versions", "\n\n".join(problems)))
            if not quiet or asked or newer:
                self.after(0, lambda: self.show_downloads(newer))
        threading.Thread(target=work, daemon=True).start()

    def check_downloads_quietly(self):
        """At launcher start (player installs, like the launcher's own update check): are there newer versions of the
        downloads the player has installed? Off with "check_downloads_on_start": false in config.json."""
        if self.cfg.get("check_downloads_on_start", True) and self.cfg.get("mariadb_dir"):
            self.check_download_updates(quiet=True)

    def add_note(self, tabs, title, text):
        page = tk.Frame(tabs, bg=BG)
        tabs.add(page, text=f"  {title}  ")
        tk.Label(page, text=text, bg=BG, fg=DIM, wraplength=480, justify="left").pack(padx=14, pady=20, anchor="w")

    def open_dir(self, path):
        os.makedirs(path, exist_ok=True)
        if IS_WINDOWS:
            os.startfile(path)
        else:
            linux.open_path(path)

    # ----- the details on the Play page -----
    def refresh_stage(self):
        """The LOGS button: shows the server lights and the activity log below the buttons, or puts them away."""
        logs = getattr(self, "logs_btn", None)
        if logs is not None:
            logs.set_active(self.showing_details)
        for widget in (self.banner_label, self.picture_label, self.details):
            widget.pack_forget()
        if self.showing_details:
            self.details.pack(fill="both", expand=True)
        elif self.running and self.pictures:
            self.picture_label.pack(fill="both", expand=True)
        else:
            self.banner_label.pack(fill="both", expand=True)
        self.fit_window()

    def once_shown(self):
        """The one-time banner has been seen: its name goes into config.json ("banners_seen"), so the next start has the usual banners."""
        name, self.once_name = getattr(self, "once_name", None), None
        if not name:
            return
        try:
            shown = [s for s in (self.cfg.get("banners_seen") or []) if isinstance(s, str)] + [name]
            save_config_value("banners_seen", shown)
            self.cfg["banners_seen"] = shown
        except Exception:
            pass                                    # config.json could not be written: it shows once more, nothing worse

    def next_hero(self):
        if getattr(self, "once_banner", None) is not None:      # the one-time banner makes way for the usual ones
            self.once_banner = None
            self.once_shown()
            if self.heroes:
                self.banner_label.configure(image=self.heroes[self.hero_index])
            return
        if len(self.heroes) > 1:
            self.hero_index = (self.hero_index + 1) % len(self.heroes)
            self.banner_label.configure(image=self.heroes[self.hero_index])

    def next_picture(self, manual=False):
        if len(self.pictures) > 1 and self.running and not self.showing_details:
            self.picture_index = (self.picture_index + 1) % len(self.pictures)
            self.picture_label.configure(image=self.pictures[self.picture_index])
        elif (not manual and not self.running and not self.showing_details and len(self.heroes) > 1
              and getattr(self, "once_banner", None) is None):
            self.hero_ticks += 1
            if self.hero_ticks % 2 == 0:                  # while nothing is running, the banner changes about every twelve seconds
                self.next_hero()
        if not manual:
            self.after(PICTURE_SECONDS * 1000, self.next_picture)

    def toggle_details(self):
        self.showing_details = not self.showing_details
        self.refresh_stage()

    # ----- messages from the worker thread -----
    def say(self, msg):
        self.q.put(("log", msg))

    def say_status(self, msg):
        """Changes the status line only, without adding a line to the details log (for something that updates every second)."""
        self.q.put(("status", msg))

    def pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "status":
                    self.status.set(val)
                elif kind == "log":
                    self.status.set(val)
                    if str(val).startswith("Game is running") and hasattr(self.progress, "success"):
                        self.progress.success()          # (2026-11-21) the loading crystals turn green
                    self.log.configure(state="normal")
                    self.log.insert("end", time.strftime("%H:%M:%S  ") + val + "\n")
                    self.log.see("end")
                    self.log.configure(state="disabled")
                elif kind == "error":
                    messagebox.showerror("Launcher", val)
                elif kind == "done":
                    self.progress.stop()
                    self.play_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.refresh_stage()
        except queue.Empty:
            pass
        self.after(200, self.pump)

    def lights(self):
        up = 0
        for n, d in self.dots.items():
            p = self.procs.get(n)
            if p is None:
                d.configure(fg=GREY)
            else:
                alive = p.poll() is None
                up += alive
                d.configure(fg=GREEN if alive else RED)
        if up == len(self.dots):
            self.summary.set("World awake")
            self.summary_dot.configure(fg=GREEN)
        elif up:
            self.summary.set("Crystallizing world...")
            self.summary_dot.configure(fg="#e0a030")
        else:
            self.summary.set("World asleep")
            self.summary_dot.configure(fg=GREY)
        self.stinkshell_tick()
        self.companion_tick()
        self.vanasync_tick()
        self.after(1000, self.lights)

    def companion_tick(self):
        """(2026-11-23, XISpeaks) Downloads with a "companion" program (thirdparty.json): it runs while the world is up and
        the item's add-on is ticked on the Addons page, and is closed when either stops. Started at most 3 times per
        session, so a companion that keeps failing is not restarted forever. Checked every 5 seconds."""
        if getattr(self, "_stink_count", 0) % 5 or not self.ashita:
            return
        try:
            procs = self.__dict__.setdefault("companions", {})
            tries = self.__dict__.setdefault("companion_tries", {})
            items = [i for i in tp.load_manifest(HERE) if i.get("companion")]
            if not items and not procs:
                return
            on = core.ScriptManager(self.ashita, self.cfg.get("ashita_boot", core.DEFAULT_BOOT)).enabled("addon") if items else set()
            for item in items:
                place = tp.place(item)
                exe = os.path.join(self.ashita, *item["companion"].split("/"))
                proc = procs.get(item["id"])
                alive = proc is not None and proc.poll() is None
                want = bool(self.running) and place is not None and place[1] in on and os.path.isfile(exe)
                if want and not alive and tries.get(item["id"], 0) < 3:
                    tries[item["id"]] = tries.get(item["id"], 0) + 1
                    procs[item["id"]] = subprocess.Popen([exe], cwd=os.path.dirname(exe),
                                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    self.q.put(("log", f"{item['name']}: started its voice program."))
                elif not want and alive:
                    proc.terminate()
                    procs.pop(item["id"], None)
        except Exception as e:
            print("companion:", e)

    def vanasync_tick(self):
        """(2026-11-25) VanaSync, JØ's battle music player (VanaSync by JØ × NOX): runs while the vanasync add-on is
        switched on (OPTIONS > Addons; off by default) and the world is up. Checked every 5 seconds, like Stinkshell."""
        if getattr(self, "_stink_count", 0) % 5 or not self.ashita:
            return
        try:
            import launcher_vanasync as vanasync
            vanasync.tick(self.__dict__.setdefault("vanasync_state", {}), HERE, self.ashita,
                          self.cfg.get("ashita_boot", core.DEFAULT_BOOT), self.running,
                          log=lambda text: self.q.put(("log", text)))
        except Exception as e:
            print("vanasync:", e)

    def stop_companions(self):
        for proc in list(getattr(self, "companions", {}).values()):
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass

    def stinkshell_tick(self):
        """(2026-11-23) Stinkshell, the online chat room: its bridge runs only while the stinkshell add-on is switched on
        (OPTIONS > Addons; off by default). Checked every 5 seconds."""
        self._stink_count = getattr(self, "_stink_count", 0) + 1
        if self._stink_count % 5 or not self.ashita:
            return
        try:
            import launcher_stinkshell as stink
            on = stink.addon_on(self.ashita, self.cfg.get("ashita_boot", core.DEFAULT_BOOT))
            bridge = getattr(self, "stink_bridge", None)
            if on and bridge is None:
                self.stink_bridge = stink.Bridge(HERE, self.ashita, log=lambda text: self.q.put(("log", text)))
                self.stink_bridge.start()
                self.q.put(("log", "Stinkshell is on: the chat room is connected through the internet."))
            elif not on and bridge is not None:
                bridge.stop()
                self.stink_bridge = None
        except Exception as e:
            print("stinkshell:", e)

    # ----- buttons -----
    def play_pressed(self):
        """PLAY: (2026-11-25) the character cards (launcher_charcards_gui.py): pick a character and it logs straight in.
        Off, or nothing to show: straight to start() as before."""
        try:
            import launcher_charcards_gui
            launcher_charcards_gui.play_pressed(self)
        except Exception as e:
            self.say(f"The character cards could not be shown ({e}).")
            self.autologin_slot = None
            self.start()

    def start(self):
        if self.running:
            return
        visit, self.visit = self.visit, None           # set by the CO-OP page's PLAY THERE
        if visit is None and self.coop_tab is not None:
            visit = self.coop_tab.ask_play_there()      # a character is visiting a friend's world: play there?
            if visit == "cancel":
                return
        if self.cfg.get("game_update_needed"):
            if self.offer_game_files("Your game hasn't had its first update yet (Square Enix's installer puts in an "
                                     "older version)."):
                return
            if messagebox.askyesno("Update the game first", "Your game hasn't had its first update yet (Square Enix's "
                                   "installer puts in an older version). Show the steps?\n\nNo = play anyway.", parent=self):
                PolUpdateGuide(self)
                return
        if IS_WINDOWS and self.cfg.get("game_registry_needed") and not self.register_game():
            return
        if not getattr(self, "age_checked", False) and self.game_too_old():
            return
        self.rates = self.rates_tab.collect()
        try:
            core.save_rates(HERE, self.rates)
        except OSError:
            pass
        try:                                   # (2026-11-23) HARDCORE: the server's hardcore files, and PLAY HARDCORE's rules
            import launcher_hardcore_gui       # for this session only (rates.json above stays your own)
            self.rates = launcher_hardcore_gui.before_play(self, self.rates)
        except Exception as e:
            self.say(f"Hardcore: {e}")
        if self.graphics_tab is not None:
            self.graphics = self.graphics_tab.collect()
            try:
                core.save_graphics(HERE, self.graphics)
            except OSError:
                pass
            try:                               # (2026-11-23) draw distance: a block at the end of the start script
                draw = self.graphics_tab.collect_draw()
                core.save_draw(HERE, draw)
                if self.scripts is not None:
                    core.apply_draw(self.scripts.path, draw)
            except Exception as e:
                self.say(f"Could not set the draw distance ({e}) - starting anyway.")
        if self.pad_tab is not None:
            self.gamepad = self.pad_tab.collect()
            try:
                gp.save(HERE, self.gamepad)
            except OSError:
                pass
        try:                                   # (2026-11-25) a character card picked: log it straight in, this launch only
            import launcher_charcards_gui
            launcher_charcards_gui.before_start(self, visit)
        except Exception as e:
            self.say(f"Character cards: {e}")
        try:                                   # (2026-11-23) small fixes to downloaded add-ons (thirdparty.json "fixups")
            for item in tp.load_manifest(HERE):
                if item.get("fixups") and self.ashita:
                    tp.apply_fixups(item, self.ashita, self.say)
        except Exception:
            pass
        try:                                   # (2026-11-23) XIPivot's root_path left pointing at a folder that moved
            import launcher_hd
            if self.ashita and launcher_hd.fix_root(self.ashita):
                self.say("XIPivot was looking for its packs in a folder that is gone (the game folder moved): fixed.")
        except Exception:
            pass
        self.running, self.stop_requested = True, False
        self.pending_visit = visit
        self.play_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.start(14)
        self.refresh_stage()
        threading.Thread(target=self.worker, daemon=True).start()

    def game_too_old(self):
        """Before PLAY: a game older than the server needs crashes (Equipment) and freezes NPCs. Offers the fix; True
        when PLAY should wait. Asked once per launcher session."""
        self.age_checked = True
        try:
            import launcher_game as lg
            info = lg.game_check(HERE, self.cfg)
        except Exception:
            return False
        if not info.get("too_old"):
            return False
        have, need = lg.build_text(info["build"]), lg.MONTHS[lg.MIN_GAME_BUILD[1] - 1] + f" {lg.MIN_GAME_BUILD[0]}"
        where = "XI: Forever Offline's copy of FINAL FANTASY XI" if info.get("copy") else "Your FINAL FANTASY XI"
        if self.offer_game_files(f"{where} is the {have} version, older than the {need} update the server needs (older "
                                 "games crash opening Equipment and can freeze at some NPCs)."):
            return True
        if linux is not None:                 # Linux: the game is updated on the Windows PC, then copied over again
            if not info.get("copy"):
                messagebox.showinfo("Update FINAL FANTASY XI", f"Your FINAL FANTASY XI is the {have} version, older than "
                                    f"the {need} update the server needs (older games crash opening Equipment). Update it "
                                    "where you installed it (PlayOnline, on Windows or through Steam / Proton here), copy "
                                    "its SquareEnix folder over this one again, then press PLAY.", parent=self)
                return False
            if messagebox.askyesno("Update your game copy", f"XI: Forever Offline's copy of FINAL FANTASY XI is the {have} "
                                   f"version, older than the {need} update the server needs (older games crash opening "
                                   "Equipment and can freeze at some NPCs).\n\nUpdate the game where you installed it "
                                   "(PlayOnline, on Windows or through Steam / Proton here), copy its SquareEnix folder here again, then choose it: only changed files "
                                   "are copied; your era files stay.\n\nChoose the updated folder now? No = play anyway.",
                                   parent=self):
                folder = filedialog.askdirectory(title="The updated SquareEnix folder", parent=self)
                ffxi, viewer = linux.find_game_parts(folder) if folder else (None, None)
                if ffxi:
                    self.refresh_game_copy((ffxi, viewer))
                    return True
                if folder:
                    messagebox.showinfo("Update your game copy", "That folder doesn't have FINAL FANTASY XI in it.", parent=self)
            return False
        if info.get("retail_ok"):
            if messagebox.askyesno("Update your game copy", f"XI: Forever Offline's copy of FINAL FANTASY XI is the {have} "
                                   f"version, older than the {need} update the server needs (older games crash opening "
                                   f"Equipment and can freeze at some NPCs).\n\nYour regular FFXI is newer "
                                   f"({lg.build_text(info['retail_build'])}). Update the copy from it now? Only changed "
                                   f"files are copied; your era files stay.\n\nNo = play anyway.", parent=self):
                self.refresh_game_copy(info["retail"])
                return True
            return False
        where = "XI: Forever Offline's copy of FINAL FANTASY XI" if info.get("copy") else "Your FINAL FANTASY XI"
        if messagebox.askyesno("Update FINAL FANTASY XI", f"{where} is the {have} version, older than the {need} update "
                               f"the server needs (older games crash opening Equipment and can freeze at some NPCs)."
                               f"\n\nTo update: open PlayOnline, log in with your Square Enix account, start FINAL FANTASY "
                               f"XI and let it download the update, then quit at the title screen."
                               + ("\nAfter that, press PLAY here: the launcher offers to copy the update into its copy."
                                  if info.get("copy") else "") +
                               "\n\nOpen PlayOnline now?\n\nNo = play anyway.", parent=self):
            try:
                cfg = dict(self.cfg)
                if info.get("retail"):
                    cfg = {"ffxi_client_dir": info["retail"][0], "pol_dir": info["retail"][1] or ""}
                elif info.get("copy"):
                    cfg = {"ffxi_client_dir": "", "pol_dir": ""}          # the registry's own PlayOnline
                lg.open_playonline(cfg)
            except Exception as e:
                messagebox.showinfo("PlayOnline", f"{e}", parent=self)
            self.age_checked = False                                    # ask again after the update
            return True
        return False

    def register_game(self):
        """(2026-11-24) A game that came from XI: Forever Offline's own download (no Square Enix installer) is registered
        with Windows once, here, before its first start: PlayOnline's folders and COM classes (launcher_game.registry_text).
        Windows asks for permission once. True when it is registered."""
        import launcher_game as lg
        try:
            if lg.registered(self.cfg):
                done = True
            else:
                reg_file = lg.write_registry_file(HERE, self.cfg.get("ashita_dir", ""), self.cfg["ffxi_client_dir"],
                                                  self.cfg["pol_dir"])
                marker = reg_file + ".done"
                if os.path.exists(marker):
                    os.remove(marker)
                messagebox.showinfo("One more step", "FINAL FANTASY XI is downloaded. Windows needs to know where it is, "
                                    "once: Windows will ask for permission next. Choose Yes.", parent=self)
                run_elevated(["register", reg_file])
                for _ in range(120):
                    if os.path.exists(marker):
                        break
                    self.update()
                    time.sleep(0.5)
                done = lg.registered(self.cfg)
        except Exception as e:
            messagebox.showerror("Register the game", f"The game couldn't be registered with Windows: {e}\n\nPress PLAY "
                                 "to try again.", parent=self)
            return False
        if not done:
            messagebox.showerror("Register the game", "Windows didn't register the game (the permission prompt was "
                                 "refused or something went wrong). Press PLAY to try again.", parent=self)
            return False
        self.cfg.pop("game_registry_needed", None)
        try:
            save_config_value("game_registry_needed", None)
        except (OSError, ValueError):
            pass
        self.say("The game is registered with Windows.")
        return True

    def offer_game_files(self, why):
        """(2026-11-23) Offers to bring the game up to date from XI: Forever Offline's own release of the game files
        (launcher_gamefiles.py). True when the update was started (PLAY waits for it); False when the release can't be
        reached or the player said no, so the PlayOnline ways are offered as before."""
        try:
            import launcher_game as lg
            import launcher_gamefiles as gf
            ffxi, viewer = self.cfg.get("ffxi_client_dir", ""), lg.viewer_dir(self.cfg)
            if not ffxi or not viewer or not os.path.isdir(ffxi):
                return False
            manifest = gf.fetch_manifest(context=tp.ssl_context(), timeout=10)
        except Exception:
            return False
        most = sum(b["size"] for b in manifest["bundles"]) / 2**30
        if not messagebox.askyesno("Update FINAL FANTASY XI", f"{why}\n\nDownload the newest game files from XI: "
                                   f"Forever Offline now? Only the files that changed are downloaded (at most "
                                   f"{most:.1f} GB). Your era files and your game settings stay.\n\nNo = other ways "
                                   "to update.", parent=self):
            return False
        self.play_btn.configure(state="disabled")
        self.progress.start(14)

        def work():
            done = False
            try:
                gf.update(HERE, ffxi, viewer, log=self.say, context=tp.ssl_context(), manifest=manifest)
                done = True
                self.say("The game is up to date. Press PLAY.")
            except Exception as e:
                self.say(f"Could not update the game: {e}  Press PLAY to try again (finished parts are kept).")

            def finish():
                self.progress.stop()
                self.play_btn.configure(state="normal")
                self.age_checked = False
                if done:
                    self.cfg.pop("game_update_needed", None)
                    try:
                        save_config_value("game_update_needed", None)
                    except (OSError, ValueError):
                        pass
            self.after(0, finish)

        threading.Thread(target=work, daemon=True).start()
        return True

    def refresh_game_copy(self, retail):
        import launcher_game as lg
        self.play_btn.configure(state="disabled")
        self.progress.start(14)

        def work():
            try:
                lg.refresh_copy(HERE, self.cfg, retail[0], retail[1], log=self.say)
                self.say("Game copy updated. Press PLAY.")
            except Exception as e:
                self.say(f"Could not update the game copy: {e}")
            self.after(0, lambda: (self.progress.stop(), self.play_btn.configure(state="normal")))

        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        self.stop_requested = True
        self.say("Stopping...")

    def on_close(self):
        if self.running and not messagebox.askyesno("Quit", "The servers are running. Stop them and quit?"):
            return
        if getattr(self, "coop_tab", None) is not None:
            if not self.coop_tab.may_close():      # visitors' characters are still in this world
                return
            self.coop_tab.shutdown()
        self.stop_companions()
        try:
            import launcher_vanasync
            launcher_vanasync.stop(getattr(self, "vanasync_state", {}))
        except Exception:
            pass
        # (2026-11-21, Tasou: "Squad gets all gear" was unticked again after a restart) the Rules page is kept on quit too,
        # not only when PLAY is pressed
        try:
            core.save_rates(HERE, self.rates_tab.collect())
        except Exception:
            pass
        # (2026-11-24, Dugahst: the draw distances were back at 0 after a restart) kept on quit too, not only at PLAY
        try:
            if getattr(self, "graphics_tab", None) is not None:
                core.save_draw(HERE, self.graphics_tab.collect_draw())
        except Exception:
            pass
        self.stop_requested = True
        self.cleanup()
        # the kit's own MariaDB (player installs) is stopped whoever started it. (2026-11-21, Meli) It used to be left
        # running when an earlier launcher had started it and was then closed from Task Manager: every launcher after
        # that found it running, so none of them stopped it. Only one launcher runs at a time (one_launcher_only) and
        # the servers are stopped by now, so nothing else is using it.
        if self.cfg.get("mariadb_dir"):
            try:
                import launcher_setup
                launcher_setup.stop_portable(self.cfg)
            except Exception:
                pass
        self.destroy()

    # ----- the actual launch sequence (runs in a background thread) -----
    def check(self):
        if self.stop_requested:
            raise Cancelled()

    def worker(self):
        try:
            self.launch()
        except Cancelled:
            self.say("Stopped.")
        except Exception as e:
            self.q.put(("error", core.explain_start_error(e)))
            self.say("Failed - see the message.")
        finally:
            self.cleanup()
            self.running = False
            self.q.put(("done", None))

    def launch(self):
        cfg = self.cfg
        self.say("Cleaning up old processes...")
        for n in core.SERVERS + ["xiloader"]:
            core.kill(n)
        core.kill_squad_chat()
        core.kill_stray_helpers()              # helpers an earlier launcher left running
        time.sleep(2)
        self.check()
        if linux is None:                      # (2026-11-22) the Visual C++ runtimes: an old or missing one stops the game
            try:                               # loader, Ashita or the server as it starts, without any message
                import launcher_thirdparty as tp_runtimes
                tp_runtimes.ensure_system_runtimes(HERE, cfg.get("ashita_dir"), log=self.say)
            except Exception as e:
                self.say(f"Could not check the Microsoft Visual C++ runtimes ({e}) - starting anyway.")
            self.check()
        try:                                   # a login key left without its certificate by a start that was cut short
            if core.clear_half_made_certificate(cfg["server_dir"]):
                self.say("Removed a half-made login certificate from an interrupted start; the server makes a new one.")
        except Exception as e:
            self.say(f"Could not check the login certificate ({e}) - starting anyway.")
        try:                                   # Ashita's target offset to match this game's version (target bar, XIUI)
            import launcher_game as lg_offsets
            got = lg_offsets.match_target_offset(cfg.get("ashita_dir", ""), cfg.get("ffxi_client_dir", ""))
            if got == "old":
                self.say("Game is older than the November 2026 update: using its target offset in Ashita.")
        except Exception as e:
            self.say(f"Could not check Ashita's target offset ({e}).")

        try:                                  # (2026-11-21, Yumainai) old update downloads: keep only the newest of each
            import launcher_update as _upd
            _upd.prune_updates(HERE, log=self.say)
        except Exception as e:
            self.say(f"Could not tidy the old update downloads ({e}).")
        try:                                  # downloads/<id> folders an install left behind (nothing touched them for 7 days)
            if not cfg.get("keep_downloads"):
                tp.prune_downloads(HERE, log=self.say)
        except Exception as e:
            self.say(f"Could not tidy the old downloads ({e}).")

        try:                                  # (2026-11-19) Gambits -> autobox, GambitsV2 -> Gambits: once, every install
            import launcher_setup as _names
            _names.migrate_gambits_names(HERE, cfg.get("ashita_dir", ""), log=self.say)
        except Exception as e:
            self.say(f"Could not rename the Gambits add-ons ({e}) - starting anyway.")
        if cfg.get("mariadb_dir"):            # a player install: the kit's own MariaDB, started here (no Windows service)
            import launcher_setup
            try:                              # a loader the server needs (e.g. after updating from an older launcher)
                import launcher_update as lu
                import launcher_thirdparty as tp
                lu.refresh_pinned(HERE, cfg, tp._get, log=self.say)
            except Exception as e:
                self.say(f"Could not update the game loader ({e}) - starting anyway.")
            try:                              # an update brings new versions of our own addons and the free mini games
                launcher_setup.install_own_addons(HERE, cfg["ashita_dir"])
            except Exception as e:
                self.say(f"Could not refresh the addons ({e}) - starting anyway.")
            try:                              # (2026-11-21) Tetra Master: switched on once when an update brings it
                launcher_setup.enable_new_addons(HERE, cfg["ashita_dir"], cfg.get("ashita_boot", "phoenixsolo.ini"),
                                                 log=self.say)
            except Exception as e:
                self.say(f"Could not turn Tetra Master on ({e}) - starting anyway.")
            try:                              # (2026-11-23) the hardcore icons: on at every PLAY
                launcher_setup.enable_hcicons(cfg["ashita_dir"], cfg.get("ashita_boot", "phoenixsolo.ini"), log=self.say)
            except Exception as e:
                self.say(f"Could not turn the hardcore badges on ({e}) - starting anyway.")
            try:                              # era game files an FFXI update wrote over (Yumainai, Altair 2026-11-19)
                for line in launcher_setup.check_era_dats(HERE, cfg.get("ffxi_client_dir", ""), log=self.say):
                    self.say(line)
            except PermissionError:
                self.say("Era-DATs: Windows did not let the launcher put the era game files back. "
                         "Run the launcher as administrator once (right-click > Run as administrator).")
            except Exception as e:
                self.say(f"Could not check the era game files ({e}) - starting anyway.")
            import launcher_client            # our game-file changes, again if an update or the era pack replaced them
            launcher_client.apply_all(HERE, cfg.get("ffxi_client_dir", ""), cfg["server_dir"], log=self.say)
            try:
                launcher_setup.record_era_state(HERE, cfg.get("ffxi_client_dir", ""))
            except Exception:
                pass
            started = launcher_setup.start_portable(cfg)
            if started is not None:
                self.db_proc = started
                self.say("Database started.")
            try:                              # the map server stops at start when a trigger is missing
                launcher_setup.ensure_triggers(cfg, cfg["server_dir"], log=self.say)
            except Exception as e:
                self.say(f"Could not check the database triggers ({e}) - starting anyway.")
            try:                              # (2026-11-22) squad and guild shop tables a cut-short setup left out
                if launcher_setup.ensure_module_tables(cfg, cfg["server_dir"], log=self.say):
                    self.say("Database: the missing tables are in place.")
            except Exception as e:
                self.say(f"Could not check the add-on tables ({e}) - starting anyway.")
        else:
            svc = cfg.get("mariadb_service", "MariaDB")
            if not core.ensure_service(svc):
                raise RuntimeError(f"The database service '{svc}' was not found or would not start.")

        if linux is not None and self.ashita:  # Linux: the game's Windows folder in Proton (made/registered once)
            self.say("Getting Proton ready...")
            linux.prepare_prefix(HERE, cfg, log=self.say)
            try:
                if self.scripts is not None and linux.ensure_wine_plugins(self.scripts):
                    self.say("Turned on Ashita's winefix plugin (smoother play under Proton).")
                boot = os.path.join(self.ashita, "config", "boot", cfg.get("ashita_boot", core.DEFAULT_BOOT))
                if bool(cfg.get("linux_sandbox")) != core.polplugin_on(boot, "sandbox"):
                    linux.set_sandbox(boot, cfg, bool(cfg.get("linux_sandbox")))
            except Exception as e:
                self.say(f"Could not check the Ashita script for Linux ({e}).")
            self.check()

        visit, self.pending_visit = getattr(self, "pending_visit", None), None
        if visit is not None:                 # co-op: play in a friend's world; none of our own servers start
            return self.launch_visit(visit)
        hosting = False
        if self.coop_tab is not None:         # co-op: while hosting, the world answers on the address friends use
            try:
                hosting = self.coop_tab.before_servers(self.say)
            except Exception as e:
                self.say(f"Co-op: could not set up hosting ({e}) - starting as a private world.")

        self.say("Applying your rates...")
        try:
            if float(self.rates.get("map.EXP_RATE", 1) or 0) <= 0:
                self.say("Note: Experience from monsters is 0 on the RULES page, so monsters give no experience. Set it to 1 for the normal amount.")
        except (TypeError, ValueError):
            pass
        try:
            for note in core.apply_rates(cfg["server_dir"], dict(self.rates, coop_hosting=hosting)):
                self.say(note)
        except Exception as e:
            self.say(f"Could not apply the rates ({e}) - starting with the server's normal settings.")
        if self.rates.get("bots_head_start") and not self.rates.get("bots_head_start_done"):
            # the one-time bot head start went into bots_config.lua: the server keeps it from here, the switch goes away
            self.rates["bots_head_start"], self.rates["bots_head_start_done"] = False, True
            self.rates_tab.head_start_done = True
            try:
                core.save_rates(HERE, self.rates)
            except OSError:
                pass
            self.say("Bot head start: on. The starting bots get a few months of history as they log in.")
        try:
            core.write_kit_paths(cfg["server_dir"], HERE, cfg.get("ashita_dir"))
        except Exception as e:
            self.say(f"Could not write kit_paths.lua ({e}) - squad chat and Crystal Boy rewards use the default folders.")

        self.conquest_ticked = self.run_conquest("tick")      # catch the world up on the time you were away (servers are not running yet)
        self.run_char_sync("sync-in")                         # (off by default) characters your other PC saved to the shared folder
        self.run_armory("fish")                               # (when a phone is paired) what it caught: skill, delivery box, gil
        self.start_ventures()                                 # (when an app is paired) squads for Ventures, and the relay while you play
        self.run_stack_mode()                                 # item stacks on the server: today's sizes (default) or the era's

        # broken "what a character wears" rows crash the login (2026-11-07): remove them while the servers are down
        try:
            import fix_equip
            n, names, _backup = fix_equip.repair(cfg, HERE)
            if n:
                self.say(f"Fixed {n} broken equipment row(s): {', '.join(names[:6])}{' ...' if len(names) > 6 else ''}")
        except Exception as e:
            self.say(f"Could not check equipment rows ({e}) - starting anyway.")

        # house rules in the item data (Chariot Band: 3 charges, 15 hours between uses); read by the map server at start
        try:
            import house_rules
            for what in house_rules.apply(cfg):
                self.say(f"House rule applied: {what}")
        except Exception as e:
            self.say(f"Could not apply the house rules ({e}) - starting anyway.")

        self.procs.clear()
        for n in core.SERVERS:
            self.check()
            self.say(f"Starting {n}...")
            p, f = core.start_server(cfg, n, LOGS)
            self.procs[n] = p
            self.logfiles.append(f)
            time.sleep(3)

        self.wait_for_map()
        time.sleep(2)
        self.check()
        if hosting:
            try:
                self.coop_tab.after_servers(self.say)
            except Exception as e:
                self.say(f"Co-op: {e}")

        self.start_ah_sim()
        if core.needs_ai(self.rates):        # Quiet world / Living world: nothing talks through the AI, so leave Ollama alone
            self.start_ollama()
        else:
            self.unload_ollama()             # ...and give back the memory a model loaded earlier still holds
        if self.rates.get("squad_chat", True):
            self.start_squad_chat()
        self.start_crowd_chat_ai()
        if self.ashita:
            self.launch_ashita()
        else:
            self.launch_plain()

    def launch_visit(self, visit):
        """Co-op: the game starts in a friend's world with the visiting character's login (launcher_coop.py)."""
        import launcher_coop as co
        if not self.ashita:
            raise RuntimeError("Playing in a friend's world needs Ashita (ashita_dir in config.json).")
        host = visit["host"]
        world = (host.get("world") or {}).get("name") or "your friend's world"
        self.say(f"Getting ready to play in {world}...")
        if self.graphics_tab is not None:      # the visit's boot file is a copy of yours: put your graphics settings in first
            try:
                core.apply_graphics(self.boot_ini, self.graphics, self.cfg.get("ffxi_client_dir"))
            except Exception:
                pass
        self.apply_gamepad()                   # the visit's boot file is a copy of yours too
        if self.cfg.get("mariadb_dir"):        # (2026-11-22) a player install: our game-file changes before a visit as well
            try:                               # (spells you can aim at a squad mate, item entries), in case an update
                import launcher_client         # came in since the last PLAY in your own world. Never stops the visit.
                launcher_client.apply_all(HERE, self.cfg.get("ffxi_client_dir", ""), self.cfg.get("server_dir", ""), log=self.say)
            except Exception:
                pass
        self.launch_boot = co.write_visit_boot(self.ashita, self.cfg.get("ashita_boot", core.DEFAULT_BOOT), host)
        self.visit_mode = True
        try:
            self.launch_ashita()
        finally:
            self.visit_mode = False
        # (2026-11-23, the user: "when you log out it takes your character back, I don't want you to have to press a
        #  button") the game closed: the character comes home by itself
        if getattr(self, "coop_tab", None) is not None and self.cfg.get("coop_auto_home", True):
            self.say(f"Bringing {visit['name']} home from {world}...")
            self.coop_tab.home_after_game(visit)
        else:
            self.say(f"{visit['name']} stays in {world} until you press COME HOME on the CO-OP page.")

    def wait_for_map(self):
        """Waits for the map server to say it is ready, showing the seconds so far. It waits as long as the map log keeps growing (the first
        start can take a minute or two) and only gives up if the log has not moved for 90 seconds, or after 10 minutes."""
        cfg = self.cfg
        self.say("Loading the world (this can take a minute or two)...")
        minwait, start = cfg.get("map_wait_seconds", 25), time.time()
        offset, grew = 0, time.time()
        last_size = core.log_size(LOGS, "xi_map")
        while time.time() - start < cfg.get("map_max_wait_seconds", 600):
            self.check()
            for n, p in self.procs.items():
                if p.poll() is not None:
                    raise RuntimeError(f"{n} stopped unexpectedly.\n\nLast lines of its log:\n"
                                       + core.tail(os.path.join(LOGS, n + ".log")))
            ready, offset = core.map_ready_from(LOGS, offset)
            if ready:
                break
            size = core.log_size(LOGS, "xi_map")
            if size != last_size:
                last_size, grew = size, time.time()
            if time.time() - start > minwait and size == 0:
                break  # log not readable; fall back to the fixed wait
            if time.time() - grew > 90:
                break  # the log has stopped moving: carry on instead of waiting for ever
            self.say_status(f"Loading the world... {int(time.time() - start)} seconds so far")
            time.sleep(1)
        seconds = int(time.time() - start)
        self.say(f"The world is ready ({seconds} seconds).")
        return seconds

    def launch_ashita(self):
        if linux is not None:
            return self.launch_ashita_linux()
        cfg = self.cfg
        cli = os.path.join(self.ashita, "Ashita-cli.exe")
        if not os.path.exists(cli):
            raise RuntimeError(f"Missing {cli}")
        if core.sync_loader(cfg):
            self.say("Updated the loader inside Ashita.")
        if self.graphics_tab is not None:
            try:
                core.apply_graphics(self.boot_ini, self.graphics, self.cfg.get("ffxi_client_dir"))
                self.say("Applied your graphics settings.")
            except Exception as e:
                self.say(f"Could not apply the graphics settings ({e}) - starting with the boot file as it is.")
        self.apply_gamepad()
        self.apply_revamped()
        self.say("Starting the game through Ashita...")
        alog = open(os.path.join(LOGS, "ashita.log"), "wb")
        self.logfiles.append(alog)
        boot = getattr(self, "launch_boot", None) or cfg.get("ashita_boot", core.DEFAULT_BOOT)      # the GM game starts with its own boot file
        self.launch_boot = None
        self.apply_game_lang(boot)
        if cfg.get("game_copy"):     # our own copy of the game: point PlayOnline at it until every game window closes
            import launcher_game as lg
            if lg.start_switch(HERE, cfg, run_elevated, is_running=lambda: core.is_running("xiloader")):
                self.say("Pointed PlayOnline at XI: Forever Offline's copy of the game (put back when the game closes).")
        subprocess.Popen([cli, boot], cwd=self.ashita, stdout=alog,
                         stderr=subprocess.STDOUT, creationflags=core.NO_WINDOW)
        for _ in range(60):
            self.check()
            if core.is_running("xiloader"):
                break
            time.sleep(1)
        else:
            raise RuntimeError("The game loader never started.\n\nAshita said:\n"
                               + core.tail(os.path.join(LOGS, "ashita.log")))
        self.say("Game is running in your friend's world." if getattr(self, "visit_mode", False)
                 else "Game is running. Closing it will stop the servers.")
        began = time.time()
        while core.is_running("xiloader"):
            self.check()
            time.sleep(2)
        self.say("Game closed.")
        self.explain_quick_close(began)

    def apply_revamped(self):
        """Before every game start: the start scripts follow the saved Revamped choice (launcher_revamped.py)."""
        try:
            for line in rv.apply(HERE, self.ashita):
                self.say("Revamped switch: " + line)
        except Exception as e:
            self.say("Could not apply the Revamped choice (%s) - starting with the scripts as they are." % e)

    def revamped_prompt(self):
        """Once, at launcher start, when a Revamped package (not just a shell) is installed and nothing was chosen."""
        try:
            if not self.ashita:
                return
            ask = rv.to_ask(HERE, self.ashita)
            if not ask:
                return
            if messagebox.askyesno("Revamped", rv.question(ask) + "\n\nYes: the old ones stop loading and the Revamped ones load at every "
                                   "start (the old add-ons stay installed). No: nothing changes and this is not asked again; "
                                   "SYSTEM has a button to switch later."):
                for line in rv.choose(HERE, self.ashita, ask, "revamped"):
                    print("Revamped switch: " + line)
            else:
                rv.declined(HERE, self.ashita)
            page = getattr(self, "updates_tab", None)
            if page is not None and hasattr(page, "revamped_refresh"):
                page.revamped_refresh()
        except Exception as e:
            print("Revamped question skipped: %s" % e)

    def apply_game_lang(self, boot):
        """(2026-11-22, Sirloinofbeef) Windows: an EU or JP game is named to the loader and Ashita in the boot file, so
        leftovers of another language's PlayOnline in the registry can't be picked in its place (launcher_game.py)."""
        try:
            import launcher_game as lg
            lang = lg.install_lang(self.cfg)
            if lg.apply_boot_lang(os.path.join(self.ashita, "config", "boot", boot), lang):
                self.say(f"PlayOnline language: {lang}.")
        except Exception as e:
            self.say(f"Could not set the PlayOnline language ({e}).")

    def explain_quick_close(self, began, appdata=None):
        """(2026-11-22) A game that closes within a minute of starting says nothing about why: the loader's own log does.
        Its lines go into the launcher's log, and a copy of that log into the logs folder for a bug report."""
        seconds = time.time() - began
        if seconds > 75 or self.stop_requested:
            return
        try:
            import shutil
            path, text = core.loader_log_since(began - 90, appdata)
            for line in core.why_game_closed(seconds, text, windows=linux is None):
                self.say(line)
            if path:
                shutil.copyfile(path, os.path.join(LOGS, "xiloader-last.log"))
            # (2026-11-22, Sunie, Ziegh, skibbity rizzard) Linux: the game checks its version file (patch.ver) against
            # the Interface values in the registry. PlayOnline keeps those right on Windows; in our Proton prefix they
            # are fixed placeholders, so a game updated after Square Enix's 2026-11-18 patch fails the check and closes
            # right after "Profile loaded." Ashita's Sandbox answers that check itself: switched on once, for good.
            if linux is not None and core.game_gave_up(text) and not self.cfg.get("linux_sandbox"):
                self.cfg["linux_sandbox"] = True
                save_config_value("linux_sandbox", True)
                self.say("Linux: this game version needs Ashita's Sandbox to pass its own version check. It is "
                         "switched on now: press PLAY again.")
        except Exception as e:
            self.say(f"Could not read the game loader's log ({e}).")

    def launch_ashita_linux(self):
        """Linux: Ashita (and through it xiloader and the game) through Proton. Waits until the game has closed."""
        cfg = self.cfg
        if self.graphics_tab is not None:
            try:
                core.apply_graphics(self.boot_ini, self.graphics, self.cfg.get("ffxi_client_dir"))
                self.say("Applied your graphics settings.")
            except Exception as e:
                self.say(f"Could not apply the graphics settings ({e}) - starting with the boot file as it is.")
        self.apply_gamepad()
        self.say("Starting the game through Ashita and Proton...")
        alog = open(os.path.join(LOGS, "ashita.log"), "wb")
        self.logfiles.append(alog)
        boot = getattr(self, "launch_boot", None) or cfg.get("ashita_boot", core.DEFAULT_BOOT)
        self.launch_boot = None
        try:
            lang = linux.apply_boot_lang(os.path.join(self.ashita, "config", "boot", boot), linux.game_lang(cfg))
            if lang != "US":
                self.say(f"PlayOnline language: {lang}.")
        except Exception as e:
            self.say(f"Could not set the PlayOnline language ({e}).")
        self.game_proc = linux.start_game(HERE, cfg, self.ashita, boot, alog)
        start, limit = time.time(), cfg.get("game_start_seconds", 300)     # the first start can download Proton's runtime
        while not core.is_running("xiloader"):
            self.check()
            if self.game_proc.poll() is not None:
                raise RuntimeError("The game closed before it started (Proton said it was done).\n\nAshita / Proton said:\n"
                                   + core.tail(os.path.join(LOGS, "ashita.log"))
                                   + "\n\nTurn on 'Write Proton logs' on SYSTEM > Linux and send logs/steam-*.log with the report.")
            if time.time() - start > limit:
                raise RuntimeError("The game loader never started.\n\nAshita / Proton said:\n" + core.tail(os.path.join(LOGS, "ashita.log")))
            self.say_status(f"Starting the game... {int(time.time() - start)} seconds")
            time.sleep(1)
        self.say("Game is running in your friend's world." if getattr(self, "visit_mode", False)
                 else "Game is running. Closing it will stop the servers.")
        began = time.time()
        while linux.game_running(self.game_proc):
            self.check()
            time.sleep(2)
        self.say("Game closed.")
        try:                                   # the loader's log is inside the game's Windows folder (Proton's prefix)
            import glob
            roaming = glob.glob(os.path.join(HERE, "prefix", "drive_c", "users", "*", "AppData", "Roaming"))
        except Exception:
            roaming = []
        self.explain_quick_close(began, roaming[0] if roaming else None)

    def launch_plain(self):
        cfg = self.cfg
        loader = None
        for root, _d, files in os.walk(cfg["xiloader_dir"]):
            if "xiloader.exe" in files:
                loader = os.path.join(root, "xiloader.exe")
                break
        if not loader:
            raise RuntimeError("xiloader.exe not found - did setup finish?")
        self.say("Starting the game...")
        p = subprocess.Popen([loader, "--server", "127.0.0.1", "--user", cfg["game_user"], "--pass", cfg["game_pass"]],
                             cwd=cfg["ffxi_client_dir"])
        while p.poll() is None:
            self.check()
            time.sleep(2)
        self.say("Game closed.")

    def start_second(self):
        """Opens a second game window (a second character on a second account) next to the first. The servers stay up until every window is closed."""
        if not self.running or not core.is_running("xiloader"):
            messagebox.showinfo("Second character", "Press PLAY first. The second character joins the servers that are already running.")
            return
        boot2 = self.cfg.get("ashita_boot2")
        if not boot2:
            # (2026-11-24, Miniberg) setup_dualbox.py run while the launcher was open: its settings are in config.json
            # but not in the copy the launcher read at start
            try:
                fresh = core.load_config(os.path.join(HERE, "config.json"))
                for key in ("ashita_boot2", "game_user2", "game_pass2"):
                    if fresh.get(key) and not self.cfg.get(key):
                        self.cfg[key] = fresh[key]
                boot2 = self.cfg.get("ashita_boot2")
            except Exception:
                pass
        path = os.path.join(self.ashita, "config", "boot", boot2) if (self.ashita and boot2) else ""
        if not path or not os.path.exists(path):
            messagebox.showinfo("Second character", "The second character is not set up yet.\n\nOpen PowerShell, go to " + HERE + " and run:\n\n    python setup_dualbox.py setup\n\nThen try again.")
            return
        if core.count_running("xiloader") >= 2:
            messagebox.showinfo("Second character", "A second game window is already open.")
            return
        try:                                    # (2026-11-25, Ricc) the add-ons ticked for the second window need Ashita's
            import setup_dualbox                # addons plugin in its script first; an older script never had it
            setup_dualbox.ensure_script(os.path.join(self.ashita, "scripts", "dualbox.txt"))
        except Exception:
            pass
        self.launch_extra(boot2, "ashita2.log")
        self.say("Starting the second character... (the first time it shows character creation)")

    def launch_extra(self, boot, log_name):
        """Opens one more game window with the given boot file, next to the one already running."""
        cli = os.path.join(self.ashita, "Ashita-cli.exe")
        self.fix_shot_dir(boot)
        log = open(os.path.join(LOGS, log_name), "wb")
        self.logfiles.append(log)
        if linux is not None:
            linux.start_game(HERE, self.cfg, self.ashita, boot, log)
            return
        self.apply_game_lang(boot)
        self.apply_revamped()
        subprocess.Popen([cli, boot], cwd=self.ashita, stdout=log, stderr=subprocess.STDOUT, creationflags=core.NO_WINDOW)

    def apply_gamepad(self):
        """The Controller tab's setup into the main boot file (launcher_gamepad.py). Nothing changes while it is off."""
        if getattr(self, "pad_tab", None) is None or not self.boot_ini:
            return
        try:
            changed, self.gamepad = gp.apply(self.boot_ini, self.gamepad)
            gp.save(HERE, self.gamepad)
            if changed:
                self.say("Applied your controller settings." if self.gamepad["managed"] else
                         "Gave the controller back to the game's own gamepad settings.")
        except Exception as e:
            self.say(f"Could not apply the controller settings ({e}) - starting with the boot file as it is.")

    def fix_shot_dir(self, boot):
        """Points a boot file's screenshot folder (registry 0042) at the real game folder. The main boot file gets this
        with the graphics settings; the GM and second-character files did not, and PrintScreen froze the game there."""
        try:
            if self.ashita and boot:
                core.apply_shot_dir(os.path.join(self.ashita, "config", "boot", boot), self.cfg.get("ffxi_client_dir"))
        except Exception:
            pass

    def start_gm(self):
        """Opens the game as the GM account (set up on the Settings page). With the servers off it starts them too, like PLAY."""
        if not self.cfg.get("ashita_boot_gm"):
            # (2026-11-23, Oldboy: "The GM account is not set up yet" right after setting it up) 'Set up GM account' writes
            # config.json from its own process; this window still had the settings it read when it opened
            try:
                fresh = core.load_config(os.path.join(HERE, "config.json"))
                for key in ("ashita_boot_gm", "game_user_gm", "game_pass_gm"):
                    if fresh.get(key) and not self.cfg.get(key):
                        self.cfg[key] = fresh[key]
            except Exception:
                pass
        boot = self.cfg.get("ashita_boot_gm")
        path = os.path.join(self.ashita, "config", "boot", boot) if (self.ashita and boot) else ""
        if not path or not os.path.exists(path):
            messagebox.showinfo("GM game", "The GM account is not set up yet.\n\nOn SYSTEM > GM and testing press 'Set up GM account' first.")
            return
        if self.running and core.is_running("xiloader"):
            self.launch_extra(boot, "ashita-gm.log")
            self.say("Starting the GM game next to your other window...")
            return
        if self.running:
            return
        self.fix_shot_dir(boot)
        self.launch_boot = boot
        self.select_tab(0)          # shows the Play page and highlights it in the top bar
        self.start()

    def run_stack_mode(self):
        # Rates tab, "Modern item stacks": stack_mode.py sets the stack size of the items on Phoenix's era list in the
        # server's item table before the servers start (an update puts the era values back, so this runs on every PLAY).
        # The game's own item files are done by launcher_client.apply_all with the other game-file changes.
        script = os.path.join(HERE, "stack_mode.py")
        if not os.path.exists(script):
            return
        try:
            mode = "modern" if self.rates.get("modern_stacks", True) else "era"
            done = subprocess.run(core.py_cmd(script, "db", mode), cwd=HERE, capture_output=True, text=True, errors="replace", timeout=90,
                                  creationflags=core.NO_WINDOW)
            lines = (done.stdout or "").strip().splitlines()
            if done.returncode != 0:
                errors = (done.stderr or "").strip().splitlines()
                self.say("Item stacks were not set on the server: " + (errors[-1] if errors else "unknown") + " - continuing.")
            elif lines and "already" not in lines[-1]:
                self.say(lines[-1][:1].upper() + lines[-1][1:])
            # a player install does the game files in launcher_client.apply_all; this PC (no kit MariaDB) does them here
            if not core.load_config(os.path.join(HERE, "config.json")).get("mariadb_dir"):
                done = subprocess.run(core.py_cmd(script, "dats", mode), cwd=HERE, capture_output=True, text=True, errors="replace", timeout=120,
                                      creationflags=core.NO_WINDOW)
                lines = (done.stdout or "").strip().splitlines()
                if done.returncode != 0:
                    errors = (done.stderr or "").strip().splitlines()
                    self.say("Item stacks were not set in the game files: " + (errors[-1] if errors else "unknown") + " - continuing.")
                elif lines and not lines[-1].startswith("item stacks: 0 changed"):
                    self.say(lines[-1][:1].upper() + lines[-1][1:])
        except Exception as e:
            self.say(f"Item stacks were not set on the server: {e}")

    def run_char_sync(self, mode):
        # CO-OP page, "PLAY ON ANOTHER PC", automatic (off by default): launcher_passport.py loads the characters your other
        # PC saved to the shared folder before the servers start ("sync-in") and saves yours after they stop ("sync-out").
        try:
            cfg = core.load_config(os.path.join(HERE, "config.json"))
            if not cfg.get("char_sync") or not cfg.get("char_sync_dir"):
                return
            done = subprocess.run(core.py_cmd(os.path.join(HERE, "launcher_passport.py"), mode), cwd=HERE, capture_output=True,
                                  text=True, errors="replace", timeout=120, creationflags=core.NO_WINDOW)
            lines = (done.stdout or "").strip().splitlines()
            if done.returncode != 0:
                errors = (done.stderr or "").strip().splitlines()
                self.say("The character folder had a problem: " + (errors[-1] if errors else "unknown") + " - continuing without it.")
            for line in lines:
                self.say(line[:1].upper() + line[1:])
        except Exception as e:
            self.say(f"The character folder was not used: {e}")

    def run_armory(self, mode):
        # (2026-11-24) launcher_armory.py: "fish" takes in what the paired phone caught (before the servers start), "sync"
        # updates the character pages on xiforever.com (after they stop, only when that switch is on). Never stops PLAY.
        try:
            script = os.path.join(HERE, "launcher_armory.py")
            if not os.path.exists(script):
                return
            done = subprocess.run(core.py_cmd(script, mode), cwd=HERE, capture_output=True, text=True, errors="replace",
                                  timeout=90, creationflags=core.NO_WINDOW)
            for line in (done.stdout or "").strip().splitlines():
                self.say(line[:1].upper() + line[1:])
            if done.returncode != 0:
                errors = (done.stderr or "").strip().splitlines()
                self.say(("Phone fishing" if mode == "fish" else "Character pages") + " skipped: " + (errors[-1] if errors else "unknown"))
        except Exception as e:
            self.say(f"Character pages / phone fishing skipped: {e}")

    def start_ventures(self):
        # (2026-11-25) Ventures (launcher_ventures.py): squad mates sent off from the XIFO app to level at a real camp.
        # Only when an app is paired. The squads go to the hub now; while the game runs, a relay keeps the game told who
        # is away and takes in what came home (exp and gil in game, items in the delivery box). Never stops PLAY.
        try:
            import launcher_armory
            import launcher_ventures
            if not launcher_armory.load(HERE).get("paired"):
                return
            try:
                n = launcher_ventures.send_roster(self.cfg, HERE)
                self.say(f"Ventures: {n} squad mate(s) ready in the XIFO app.")
            except Exception as e:
                self.say(f"Ventures: the squads were not sent ({e}).")
            self.venture_relay = launcher_ventures.Relay(self.cfg, HERE, log=lambda text: self.q.put(("log", text)))
            self.venture_relay.roster_at = time.time()
            self.venture_relay.start()
        except Exception as e:
            self.say(f"Ventures skipped: {e}")

    def run_conquest(self, mode):
        # The conquest simulator (conquest_sim.py) edits the conquest table. "tick" runs before the servers start, "stamp" after they stop.
        script = os.path.join(HERE, "conquest_sim.py")
        if not self.rates.get("conquest_sim", True) or not os.path.exists(script):
            return False
        try:
            done = subprocess.run(core.py_cmd(script, mode), cwd=HERE, capture_output=True, text=True, errors="replace", timeout=90,
                                  creationflags=core.NO_WINDOW)
            if done.returncode != 0:
                lines = (done.stderr or done.stdout or "").strip().splitlines()
                self.say("The conquest simulator had a problem: " + (lines[-1] if lines else "unknown") + " - continuing without it.")
                return False
            lines = (done.stdout or "").strip().splitlines()
            if mode == "tick" and lines:
                self.say(lines[-1])
            return True
        except Exception as e:
            self.say(f"The conquest simulator did not run: {e}")
            return False

    def unload_ollama(self):
        # AI chat is off for this world: an Ollama left running (by us or by an earlier session) keeps its model in
        # memory for half an hour. Ask it to unload every loaded model now. Nothing happens if Ollama isn't running.
        import json, urllib.request
        url = "http://127.0.0.1:11434"
        try:
            with open(os.path.join(HERE, "squad-chat", "config.json"), encoding="utf-8-sig") as f:
                url = json.load(f).get("ollama_url", url)
        except Exception:
            pass
        url = url.rstrip("/")
        try:
            with urllib.request.urlopen(url + "/api/ps", timeout=2) as r:
                models = [m.get("name") or m.get("model") for m in json.load(r).get("models", [])]
        except Exception:
            return
        for name in filter(None, models):
            try:
                body = json.dumps({"model": name, "keep_alive": 0}).encode()
                req = urllib.request.Request(url + "/api/generate", data=body, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=10).close()
                self.say("AI chat is off: unloaded %s from memory." % name)
            except Exception:
                pass

    def start_ollama(self):
        # Ollama (the local AI model squad chat, crowd chatter and the bots' tells use): start it if it is not running yet.
        import json
        url = "http://127.0.0.1:11434"
        try:
            with open(os.path.join(HERE, "squad-chat", "config.json"), encoding="utf-8-sig") as f:
                url = json.load(f).get("ollama_url", url)
        except Exception:
            pass
        import urllib.request
        def running():
            try:
                with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=2):
                    return True
            except Exception:
                return False
        if running():
            self.say("Ollama is already running.")
            return
        import shutil
        exe = shutil.which("ollama")
        for guess in (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
                      os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
                      os.path.join(HERE, "ollama", "bin", "ollama")):
            if not exe and os.path.exists(guess):
                exe = guess
        if not exe:
            self.say("Ollama was not found (install it from ollama.com): AI chat stays off, bots use short lines.")
            return
        try:
            log = open(os.path.join(LOGS, "ollama.log"), "wb")
            self.logfiles.append(log)
            self.ollama_proc = subprocess.Popen([exe, "serve"], stdout=log, stderr=subprocess.STDOUT, creationflags=core.NO_WINDOW,
                                                **({} if IS_WINDOWS else {"start_new_session": True}))
            for _ in range(20):  # up to 10 s for it to answer
                if running():
                    break
                time.sleep(0.5)
            self.say("Ollama started." if running() else "Ollama is starting (it may take a moment).")
        except Exception as e:
            self.say(f"Ollama did not start: {e}")

    def start_squad_chat(self):
        # The Ollama sidecar (squad-chat/squad_chat.py) writes the mates' party-chat replies and backstories.
        # Without it the mates only say their scripted lines, because nothing is answering in the chat bridge.
        folder = os.path.join(HERE, "squad-chat")
        script = os.path.join(folder, "squad_chat.py")
        if not os.path.exists(script):
            return
        try:
            log = open(os.path.join(LOGS, "squad-chat.log"), "wb")
            self.logfiles.append(log)
            self.chat_proc = subprocess.Popen(core.py_cmd(script), cwd=folder, stdout=log, stderr=subprocess.STDOUT,
                                              creationflags=core.NO_WINDOW)
            self.say("Squad chat started.")
        except Exception as e:
            self.say(f"Squad chat did not start: {e}")

    def start_crowd_chat_ai(self):
        # Crowd chat AI helper (crowds/crowd_chat_ai.py): keeps a pool of AI-written small talk for the town crowds.
        script = os.path.join(HERE, "crowds", "crowd_chat_ai.py")
        # It also answers the bot players' tells, party and linkshell chat (crowds/bots/bots_chat_ai.py), so it runs whenever
        # the bot players are on too, even with the crowds off (then only for the bots: --bots-only).
        rates = self.rates
        crowds_ai = rates.get("crowds", True) and rates.get("crowds_chat", True) and rates.get("crowds_chat_ai", True)
        bots_ai = rates.get("bots", True) and rates.get("crowds_chat_ai", True)
        if not (crowds_ai or bots_ai) or not os.path.exists(script):
            return
        try:
            log = open(os.path.join(LOGS, "crowd-chat-ai.log"), "wb")
            self.logfiles.append(log)
            args = core.py_cmd(script, *([] if crowds_ai else ["--bots-only"]), unbuffered=True)
            self.crowd_ai_proc = subprocess.Popen(args, cwd=os.path.dirname(script), stdout=log,
                                                  stderr=subprocess.STDOUT, creationflags=core.NO_WINDOW)
            self.say("Chat AI helper started" + ("." if crowds_ai else " (bot players only)."))
        except Exception as e:
            self.say(f"Crowd chat AI helper did not start: {e}")

    def start_ah_sim(self):
        # The auction house simulator (ah_sim.py) stocks the auction house and buys what you list. Switched on the Rates tab.
        script = os.path.join(HERE, "ah_sim.py")
        if not self.rates.get("ah_sim", self.cfg.get("ah_sim", False)) or not os.path.exists(script):
            return
        try:
            log = open(os.path.join(LOGS, "ah_sim.log"), "wb")
            self.logfiles.append(log)
            self.ah_proc = subprocess.Popen(core.py_cmd(script, "run"), cwd=HERE, stdout=log, stderr=subprocess.STDOUT,
                                            creationflags=core.NO_WINDOW)
            self.say("Auction house simulator started.")
        except Exception as e:
            self.say(f"Auction house simulator did not start: {e}")

    def cleanup(self):
        had_servers = bool(self.procs)
        if had_servers:                                              # (2026-11-25) the character cards learn new levels
            try:                                                     # and places while the database is still up
                import launcher_charcards_gui
                launcher_charcards_gui.refresh_after_game(self)
            except Exception:
                pass
        relay = getattr(self, "venture_relay", None)                # (2026-11-25) Ventures: the relay stops with the game
        if relay is not None:
            relay.stop()
            self.venture_relay = None
        ollama = getattr(self, "ollama_proc", None)
        if ollama is not None:  # only the Ollama this launcher started (one you started yourself keeps running)
            # (2026-11-23, Sunie: Ollama kept running on Linux after the launcher closed) "ollama serve" starts a runner
            # process per loaded model; terminate() ended only the server, so the whole tree is stopped now
            try:
                core.kill_tree(ollama)
            except Exception:
                pass
            self.ollama_proc = None
        chat = getattr(self, "chat_proc", None)
        if chat is not None:
            core.kill_tree(chat)   # (the packaged exe: the starter and the real helper both)
            self.chat_proc = None
        crowd_ai = getattr(self, "crowd_ai_proc", None)
        if crowd_ai is not None:
            core.kill_tree(crowd_ai)   # (the packaged exe: the starter and the real helper both)
            self.crowd_ai_proc = None
        ah = getattr(self, "ah_proc", None)
        if ah is not None:
            core.kill_tree(ah)   # (the packaged exe: the starter and the real helper both)
            self.ah_proc = None
        for p in self.procs.values():
            try:
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass
        if linux is not None:      # Linux: wait for them to finish (they save to the database), and leave no zombies
            for p in self.procs.values():
                try:
                    p.wait(timeout=20)
                except Exception:
                    try:
                        p.kill()
                        p.wait(timeout=5)
                    except Exception:
                        pass
        # Only the servers this window started are stopped (above). Killing by image name here would also
        # take down the servers of another launcher window that is still running, which looks like
        # "xi_connect stopped unexpectedly" in that other window.
        if self.stop_requested:
            core.kill("xiloader")
            if linux is not None:
                linux.stop_game(HERE)
        if getattr(self, "conquest_ticked", False):
            self.run_conquest("stamp")                         # the session is over: note the time so the tally is not repeated
            self.conquest_ticked = False
        self.run_char_sync("sync-out")                         # (off by default) your characters go to the shared folder
        self.run_armory("sync")                                # (off by default) your character pages on xiforever.com
        for f in self.logfiles:
            try:
                f.close()
            except Exception:
                pass
        self.logfiles.clear()
        self.procs.clear()
        if had_servers or not getattr(self, "coop_tab", None):     # (a visit to a friend's world started no servers)
            self.say("Servers stopped.")


def save_config_value(key, value):
    """Changes one value in config.json (keeps everything else as it is)."""
    import json
    path = os.path.join(HERE, "config.json")
    with open(path, encoding="utf-8-sig") as handle:
        cfg = json.load(handle)
    if value is None:
        cfg.pop(key, None)
    else:
        cfg[key] = value
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2)


class PolUpdateGuide(tk.Toplevel):
    """The first update of a game installed with Square Enix's installer. PlayOnline only offers FINAL FANTASY XI's
    update after the game has connected to Square Enix once (the install is registered then), so this needs one login
    with a Square Enix account that has the game. LandSandBoat's client guide says the same; we don't work around it."""

    STEPS = [
        ("Open PlayOnline",
         "Press the button below. PlayOnline updates itself first (Windows may ask for permission; say Yes). "
         "Wait until its welcome screen shows."),
        ("Log in with your Square Enix account",
         "Add a member with your Square Enix ID and password (and your one-time password, if you use one). The account "
         "needs FINAL FANTASY XI on it (a free trial account works). This is the only time you connect to Square Enix."),
        ("Start FINAL FANTASY XI once",
         "Choose FINAL FANTASY XI and press Play. PlayOnline downloads the game's update first: 10 to 60 minutes. "
         "Let it finish."),
        ("Quit, then press I'm done",
         "When the game reaches its title or character screen, quit (you don't need to make a character there). "
         "Close PlayOnline and press I'm done here. From now on you only use PLAY in this launcher."),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("One more step: update the game")
        self.configure(bg=BG)
        self.geometry("760x760")
        self.minsize(700, 560)
        tk.Label(self, text="Update FINAL FANTASY XI once", bg=BG, fg=GOLD, font=(UI_FONT, 15, "bold")).pack(
            anchor="w", padx=18, pady=(14, 2))
        tk.Label(self, text="Square Enix's installer puts in an older version of the game. PlayOnline brings it up to date "
                            "after one login with your Square Enix account. After that you play offline with PLAY.",
                 bg=BG, fg=DIM, wraplength=710, justify="left").pack(anchor="w", padx=18, pady=(0, 8))
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12)
        for n, (title, text) in enumerate(self.STEPS, 1):
            row = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=4)
            pic = tk.Canvas(row, width=210, height=118, bg="#0d1620", highlightthickness=0)
            pic.pack(side="left", padx=8, pady=8)
            getattr(self, f"draw_{n}")(pic)
            words = tk.Frame(row, bg=PANEL)
            words.pack(side="left", fill="both", expand=True, padx=(4, 10), pady=8)
            tk.Label(words, text=f"{n}. {title}", bg=PANEL, fg=FG, font=(UI_FONT, 11, "bold")).pack(anchor="w")
            tk.Label(words, text=text, bg=PANEL, fg=DIM, wraplength=440, justify="left").pack(anchor="w", pady=(2, 0))
            if n == 1:
                tk.Button(words, text="Open PlayOnline", command=self.open_pol, bg=ACCENT, fg="white", relief="flat",
                          padx=14).pack(anchor="w", pady=(6, 0))
        self.note = tk.StringVar(value="")
        bar = tk.Frame(self, bg=BG)
        bar.pack(side="bottom", fill="x", padx=18, pady=12, before=body)        # buttons stay visible on small screens
        tk.Label(self, textvariable=self.note, bg=BG, fg=GOLD, wraplength=720, justify="left").pack(
            side="bottom", anchor="w", padx=18, pady=(6, 0), before=body)
        tk.Button(bar, text="I'm done", command=self.done, bg=GREEN, fg="white", relief="flat", padx=18).pack(side="right")
        tk.Button(bar, text="Later", command=self.destroy, bg=PANEL, fg=FG, relief="flat", padx=14).pack(side="right", padx=6)
        tk.Button(bar, text="Game already updated before? Re-check files", command=self.force, bg=PANEL, fg=FG,
                  relief="flat", padx=10).pack(side="left")
        self.transient(app)
        self.lift()

    # ----- little pictures (drawn, so they work in any language and need no files) -----
    def window(self, c, title):
        c.create_rectangle(8, 8, 202, 110, fill="#1b2a3a", outline="#3a5468")
        c.create_rectangle(8, 8, 202, 24, fill="#2c4258", outline="#3a5468")
        c.create_text(14, 16, text=title, anchor="w", fill="#cfe3ee", font=(UI_FONT, 7))

    def draw_1(self, c):
        self.window(c, "PlayOnline Viewer")
        c.create_text(105, 52, text="Updating PlayOnline...", fill="#e9f1f5", font=(UI_FONT, 9))
        c.create_rectangle(30, 68, 180, 80, outline="#5f7f95")
        c.create_rectangle(31, 69, 120, 79, fill=ACCENT, outline="")

    def draw_2(self, c):
        self.window(c, "PlayOnline - Member")
        for i, label in enumerate(("Square Enix ID", "Password", "One-time pass")):
            y = 36 + i * 22
            c.create_text(16, y, text=label, anchor="w", fill="#9fb6c4", font=(UI_FONT, 7))
            c.create_rectangle(96, y - 8, 192, y + 8, fill="#0d1620", outline="#5f7f95")
            c.create_text(101, y, text="your own" if i == 0 else ("********" if i == 1 else "(if used)"), anchor="w",
                          fill=GOLD, font=(MONO_FONT, 8, "bold"))
        c.create_rectangle(120, 94, 190, 106, fill="#2c4258", outline=GOLD)
        c.create_text(155, 100, text="Connect", fill="#e9f1f5", font=(UI_FONT, 7, "bold"))

    def draw_3(self, c):
        self.window(c, "PlayOnline - Version Update")
        c.create_text(105, 40, text="FINAL FANTASY XI", fill=GOLD, font=(UI_FONT, 8, "bold"))
        c.create_text(105, 56, text="Downloading update...", fill="#e9f1f5", font=(UI_FONT, 8))
        c.create_rectangle(30, 68, 180, 80, outline="#5f7f95")
        c.create_rectangle(31, 69, 95, 79, fill=ACCENT, outline="")
        c.create_text(105, 98, text="10 - 60 minutes", fill=DIM, font=(UI_FONT, 7))

    def draw_4(self, c):
        self.window(c, "FINAL FANTASY XI")
        c.create_text(105, 44, text="Select Character", fill="#e9f1f5", font=(UI_FONT, 8))
        c.create_rectangle(40, 56, 170, 68, fill="#22364a", outline="#3a5468")
        c.create_rectangle(40, 72, 170, 84, fill="#3b5a2a", outline=GOLD, width=2)
        c.create_text(105, 78, text="Exit", fill="#e9f1f5", font=(UI_FONT, 8, "bold"))
        c.create_text(105, 100, text="then press I'm done", fill=DIM, font=(UI_FONT, 7))

    # ----- buttons -----
    def open_pol(self):
        import launcher_game as lg
        try:
            exe = lg.open_playonline(self.app.cfg)
            self.note.set(f"PlayOnline started ({exe}). Follow steps 2 to 4 there.")
        except Exception as e:
            self.note.set(str(e))

    def force(self):
        import launcher_game as lg
        ffxi = self.app.cfg.get("ffxi_client_dir", "")
        if core.is_running("pol"):
            self.note.set("Close PlayOnline first, then press this button again.")
            return
        try:
            lg.force_version_check(ffxi)
            self.note.set("Done: open PlayOnline, click Check Files, choose FINAL FANTASY XI and let it repair. "
                          "(This works once the game has connected to Square Enix one time.)")
        except Exception as e:
            self.note.set(f"Couldn't do that: {e}")

    def done(self):
        import launcher_game as lg
        try:
            result = lg.finish_version_check(self.app.cfg.get("ffxi_client_dir", ""))
        except Exception as e:
            self.note.set(f"Couldn't check the game files: {e}")
            return
        if result == "restored":
            if not messagebox.askyesno("Update", "PlayOnline didn't finish updating the game (a file it should have "
                                       "rebuilt is missing, so the old one was put back).\n\nClose this guide anyway?",
                                       parent=self):
                return
        else:
            self.app.cfg.pop("game_update_needed", None)
            try:
                save_config_value("game_update_needed", None)
            except (OSError, ValueError) as e:
                self.note.set(f"Couldn't save that the update is done: {e}")
                return
        self.destroy()


class SetupWizard(tk.Tk):
    """First run (no config.json yet): find FFXI, install Ashita and the add-ons, set up the database and the account.
    The work itself is launcher_setup.run_setup; this window only asks the questions and shows the progress."""

    EXTRAS = (("mobdb", "mobdb: monster info on your target", True), ("nameplate", "Nameplate: clearer name plates", True),
              ("xipivot", "XIPivot: load DAT mods without changing game files", False),
              ("gambatte", "Mini game player", True),
              ("chains", "Chains: skillchain helper", False),
              ("cadence", "Cadence: auto-attack and resting timers (loads switched off)", False),
              ("checkmate", "Checkmate: detailed monster check (loads switched off)", False),
              ("momentum", "Momentum: EXP and merit tracking (loads switched off)", False),
              ("ffxiport", "FFXIPort: a teleport window, /port (loads switched off)", False), ("vanafish", "VanaFish: fishing bot, /vanafish (loads switched off)", False), ("vanacam", "VanaCam: camera presets and combat distance (loads switched off)", False), ("autobot", "AutoBot: for a second (dualbox) character", False))

    def __init__(self, again=None):
        super().__init__()
        linux_look(self)
        import launcher_setup
        self.setup = launcher_setup
        # (2026-11-22, Sunie) again: this install's config.json when setup is run again from SYSTEM > Settings. The
        # folders start as they are now, the world and account pages are left out, and nothing of the world changes.
        self.again = again if (again and hasattr(launcher_setup, "again_choices")) else None
        self.title("XI: Forever Offline - setup, again" if self.again else "XI: Forever Offline - first-time setup")
        self.geometry("760x600")
        self.configure(bg=BG)
        icon = load_image(os.path.join("ui", "icon.png"))
        if icon:
            self._icon = icon
            try:
                self.iconphoto(True, icon)
            except Exception:
                pass
        self.done = False
        self.q = queue.Queue()
        layout = launcher_setup.default_layout(HERE)
        self.ffxi = tk.StringVar(value=launcher_setup.find_ffxi() or "")
        # the game files: a separate copy when FFXI is installed, else Square Enix's official installer
        # (Linux: always from a folder, copied from a Windows PC)
        self.game = tk.StringVar(value="copy" if (self.ffxi.get() or linux is not None) else "official")
        self.ashita = tk.StringVar(value=layout["ashita_dir"])
        self.server = tk.StringVar(value=layout["server_dir"])
        self.deck = linux is not None and linux.is_steam_deck()
        self.world = tk.StringVar(value="living")
        self.population = tk.StringVar(value="small" if self.deck else "medium")
        self.interface = tk.StringVar(value="xiui")
        self.extras = {key: tk.BooleanVar(value=on) for key, _text, on in self.EXTRAS}
        self.era_dats = tk.BooleanVar(value=True)
        self.login = tk.StringVar(value="player1")
        self.password = tk.StringVar(value=launcher_setup.new_password(12))
        self.mariadb_dir = layout["mariadb_dir"]

        tk.Label(self, text="XI: Forever Offline", bg=BG, fg=GOLD, font=("Georgia", 20, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
        self.step_title = tk.Label(self, text="", bg=BG, fg=FG, font=(UI_FONT, 12, "bold"))
        self.step_title.pack(anchor="w", padx=16, pady=(2, 8))
        # (2026-11-18, Sunie on Hyprland) the Back/Next row is packed first at the bottom, so a tall page can never push
        # it out of the window; the window also grows to fit the page (up to the screen)
        nav = tk.Frame(self, bg=BG)
        nav.pack(side="bottom", fill="x", padx=16, pady=12)
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=16)
        self.back_btn = tk.Button(nav, text="Back", command=lambda: self.show(self.page - 1), bg=PANEL, fg=FG, relief="flat", padx=14)
        self.back_btn.pack(side="left")
        self.next_btn = tk.Button(nav, text="Next", command=self.next, bg=ACCENT, fg="white", relief="flat", padx=18)
        self.next_btn.pack(side="right")
        self.pages = [self.page_folders, self.page_world, self.page_account, self.page_install]
        if self.again:
            self.start_again()
            self.pages = [self.page_folders, self.page_world, self.page_install]
        self.show(0)

    def start_again(self):
        """Setup run again: the pages start from what this install has now."""
        start = self.setup.again_choices(HERE, self.again)
        self.ffxi.set(start["ffxi_dir"])
        self.game.set("existing")                 # the game where it is; a new copy only when the player picks it
        self.ashita.set(start["ashita_dir"])
        self.server.set(start["server_dir"])
        self.world.set(start["world"])
        self.login.set(start["login"])
        self.password.set(start["password"])
        self.mariadb_dir = start["mariadb_dir"]
        try:                                      # tick what this install has, so nothing is added or asked twice
            import launcher_thirdparty as tp
            items = {item["id"]: item for item in tp.load_manifest(HERE)}
            have = lambda iid: bool(iid in items and tp.status(items[iid], HERE, start["ashita_dir"])[0])
            for key, var in self.extras.items():
                var.set(have(key))
            self.interface.set("xiuiplus" if have("xiuiplus") else "xiui" if have("xiui") else "none")
        except Exception:
            pass

    def fit(self):
        """Make the window tall enough for the page it shows (never taller than the screen)."""
        try:
            self.update_idletasks()
            want_w = max(760, self.winfo_reqwidth())
            want_h = max(600, self.winfo_reqheight())
            screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight() - 60
            w, h = min(want_w, screen_w), min(want_h, screen_h)
            if w > self.winfo_width() or h > self.winfo_height():
                self.geometry(f"{max(w, self.winfo_width())}x{max(h, self.winfo_height())}")
        except Exception:
            pass

    # ----- pages -----
    def clear(self, title):
        for widget in self.body.winfo_children():
            widget.destroy()
        self.step_title.configure(text=title)
        if getattr(self, "again", None) and title.startswith("1."):
            tk.Label(self.body, text="Setup again: your world, characters, squad and settings stay as they are. Choose the "
                                     "folders to use from now on. What is already in them is kept; what is missing is "
                                     "downloaded and set up. The old folders are not deleted.",
                     bg=BG, fg=GOLD, wraplength=720, justify="left").pack(anchor="w", pady=(0, 6))

    def text(self, words, fg=None):
        tk.Label(self.body, text=words, bg=BG, fg=fg or DIM, wraplength=720, justify="left").pack(anchor="w", pady=(0, 6))

    def folder_row(self, label, var, hint):
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG, fg=FG, width=16, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", width=56).pack(side="left")
        tk.Button(row, text="Browse...", relief="flat", bg=PANEL, fg=FG, padx=8,
                  command=lambda: var.set(filedialog.askdirectory(initialdir=var.get() or HERE) or var.get())).pack(side="left", padx=6)
        tk.Label(self.body, text=hint, bg=BG, fg=DIM, font=(UI_FONT, 9), wraplength=720, justify="left").pack(anchor="w", padx=(4, 0))

    def page_folders_linux(self):
        self.clear("1. Where things are")
        self.text("This sets up everything here: the game files, the game add-on loader (Ashita), Proton (runs the "
                  "Windows game on Linux), the game server and a small database. It takes a while and needs an internet "
                  "connection for the downloads (about 2 GB).")
        self.text("FINAL FANTASY XI: choose its SquareEnix folder (the one with PlayOnlineViewer and FINAL FANTASY XI in it). "
                  "It can come from a Windows PC (inside PlayOnline in Program Files, copied to a USB stick or this machine), "
                  "or from the game installed on this machine: the Steam version, or the official installer from "
                  "playonline.com run through Proton or Wine. An older game is brought up to date by the launcher at PLAY.", fg=FG)
        for key, label, about in (
                ("copy", "Copy the game into XI: Forever Offline's folder (recommended)",
                 "The folder you choose stays as it is (a USB stick can be unplugged afterwards). Needs about 16 GB free."),
                ("existing", "Use the game where it is",
                 "No copy: the era game files (Phoenix Era-DATs) go into that folder; its original files are backed up.")):
            tk.Radiobutton(self.body, text=label, value=key, variable=self.game, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG, font=(UI_FONT, 10, "bold")).pack(anchor="w")
            tk.Label(self.body, text=about, bg=BG, fg=DIM, font=(UI_FONT, 9), wraplength=700, justify="left").pack(anchor="w", padx=(26, 0))
        self.folder_row("Game folder", self.ffxi, "The SquareEnix folder (or the FINAL FANTASY XI folder next to "
                        "PlayOnlineViewer).")
        self.folder_row("Ashita", self.ashita, "A new folder is fine: Ashita is downloaded from its official release.")
        self.folder_row("Server", self.server, "A new folder is fine: the ready-made Linux server is downloaded.")
        self.text(f"The database is kept in {self.mariadb_dir}." +
                  (" Steam Deck found: the world starts small and the game uses the Deck's screen size." if self.deck else ""))

    def page_folders(self):
        if linux is not None:
            return self.page_folders_linux()
        self.clear("1. Where things are")
        self.text("This sets up everything on this PC: the game files, the game add-on loader (Ashita), the game server and a "
                  "small database. It takes a while and needs an internet connection for the downloads.")
        found = bool(self.setup.valid_ffxi(self.ffxi.get()))
        options = [("copy", "Make a separate copy of my FINAL FANTASY XI for XI: Forever Offline (recommended)",
                    "Your own install (retail, other servers, HD packs) stays exactly as it is. Needs as much free space as "
                    "your FFXI install uses. On PLAY, Windows asks once for permission to point PlayOnline at the copy; "
                    "it is put back when the game closes."),
                   ("existing", "Use my installed FINAL FANTASY XI",
                    "No copy. The era game files (Phoenix Era-DATs) then go into that install; its original files are backed up."),
                   ("official", "Download FINAL FANTASY XI (I don't have it)",
                    "The whole game, up to date (about 7.5 GB), from XI: Forever Offline's own download into the "
                    "launcher's folder. At the first PLAY, Windows asks once for permission to register it. No Square "
                    "Enix account, login or installer needed.")]
        for key, label, about in options:
            if key == "official" and found:
                continue
            tk.Radiobutton(self.body, text=label, value=key, variable=self.game, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG, font=(UI_FONT, 10, "bold")).pack(anchor="w")
            tk.Label(self.body, text=about, bg=BG, fg=DIM, font=(UI_FONT, 9), wraplength=700, justify="left").pack(anchor="w", padx=(26, 0))
        self.folder_row("Final Fantasy XI", self.ffxi, "Found from PlayOnline's settings when it can be. The folder with FFXiMain.dll "
                        "in it (not needed for the download).")
        self.folder_row("Ashita", self.ashita, "A new folder is fine: Ashita is downloaded from its official release.")
        self.folder_row("Server", self.server, "A new folder is fine: the ready-made server is downloaded (a few hundred MB). "
                        "If you built the server yourself, choose its folder.")
        self.text(f"The database is kept in {self.mariadb_dir}.")

    def page_world(self):
        self.clear("2. Interface and add-ons" if self.again else "2. Your world")
        import launcher_core as lc
        if self.again:
            self.text("Your world and its rules stay as they are (change them on the launcher's WORLD and RULES pages). "
                      "These are for the Ashita folder you chose: what it already has is ticked.")
        for key, (label, about) in ({} if self.again else lc.WORLDS).items():
            tk.Radiobutton(self.body, text=label, value=key, variable=self.world, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG, font=(UI_FONT, 10, "bold")).pack(anchor="w")
            tk.Label(self.body, text=about, bg=BG, fg=DIM, font=(UI_FONT, 9), wraplength=700, justify="left").pack(anchor="w", padx=(26, 0))
        row = tk.Frame(self.body, bg=BG)
        row.pack(anchor="w", pady=(10, 2))
        if not self.again:
            tk.Label(row, text="Population:", bg=BG, fg=FG).pack(side="left")
        for key, (label, crowd, _roster, online) in ({} if self.again else lc.POPULATIONS).items():
            tk.Radiobutton(row, text=f"{label} ({crowd}/town, {online} bots)", value=key, variable=self.population,
                           bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG).pack(side="left", padx=4)
        row = tk.Frame(self.body, bg=BG)
        row.pack(anchor="w", pady=(6, 2))
        tk.Label(row, text="Interface:", bg=BG, fg=FG).pack(side="left")
        for key, label in (("xiui", "XIUI (stable)"), ("xiuiplus", "XIUIplus (alpha, newer)"), ("none", "The game's own")):
            tk.Radiobutton(row, text=label, value=key, variable=self.interface, bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG).pack(side="left", padx=6)
        self.era_dats.set(True)        # the era game files are always installed: the server is built for them
        tk.Label(self.body, text="Add-ons (downloaded from their authors; more on the launcher's Downloads tab later):",
                 bg=BG, fg=FG).pack(anchor="w", pady=(10, 2))
        for key, label, _on in self.EXTRAS:
            tk.Checkbutton(self.body, text=label, variable=self.extras[key], bg=BG, fg=FG, selectcolor=PANEL,
                           activebackground=BG, activeforeground=FG).pack(anchor="w", padx=(10, 0))

    def page_account(self):
        self.clear("3. Your game account")
        self.text("The login the game uses on your own server. It stays on this PC (in config.json and Ashita's boot file); "
                  "the launcher logs you in with it, so you don't need to remember the password.")
        for label, var in (("Login", self.login), ("Password", self.password)):
            row = tk.Frame(self.body, bg=BG)
            row.pack(anchor="w", pady=4)
            tk.Label(row, text=label, bg=BG, fg=FG, width=16, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=var, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", width=24).pack(side="left")
        self.text("Login: 3-16 letters and numbers. You make your character in the game after the first login.")

    def page_install(self):
        self.clear("3. Set up" if self.again else "4. Install")
        self.log_box = tk.Text(self.body, height=20, bg=PANEL, fg=FG, relief="flat", font=(MONO_FONT, 9), wrap="word")
        self.log_box.pack(fill="both", expand=True)
        self.log_box.insert("end", "Press Install to start.\n")
        self.next_btn.configure(text="Install", command=self.start_install)

    # ----- moving between pages -----
    def show(self, index):
        self.page = max(0, min(index, len(self.pages) - 1))
        self.next_btn.configure(text="Next", command=self.next, state="normal")
        self.back_btn.configure(state="normal" if self.page > 0 else "disabled")
        self.pages[self.page]()
        self.after_idle(self.fit)

    def next(self):
        problem = self.check_page()
        if problem:
            messagebox.showinfo("Setup", problem, parent=self)
            return
        self.show(self.page + 1)

    def check_page(self):
        if self.page == 0 and linux is not None:
            ffxi, viewer = linux.find_game_parts(self.ffxi.get())
            if not ffxi or not viewer:
                return ("Choose the folder with both FINAL FANTASY XI and PlayOnlineViewer in it (the SquareEnix folder, "
                        "from a Windows PC or from the game installed here through Steam or Proton).")
            return None
        if self.page == 0:
            if self.game.get() != "official" and not self.setup.valid_ffxi(self.ffxi.get()):
                return "Choose the FINAL FANTASY XI folder (the one with FFXiMain.dll in it), or pick the Square Enix download."
        if self.again:                           # no account page: the account stays as it is
            return None
        if self.page == 2 and not self.setup.valid_login(self.login.get()):
            return "The login must be 3-16 letters and numbers."
        if self.page == 2 and len(self.password.get()) < 6:
            return "Use a password of at least 6 characters."
        return None

    # ----- the install -----
    def start_install(self):
        self.next_btn.configure(state="disabled")
        self.back_btn.configure(state="disabled")
        choices = {"ffxi_dir": self.ffxi.get(), "game": self.game.get(), "ashita_dir": self.ashita.get(), "server_dir": self.server.get(),
                   "mariadb_dir": self.mariadb_dir, "world": self.world.get(), "population": self.population.get(),
                   "interface": self.interface.get(), "extras": [k for k, v in self.extras.items() if v.get()],
                   "era_dats": self.era_dats.get(),
                   "login": self.login.get(), "password": self.password.get()}

        def work():
            try:
                import launcher_thirdparty
                cfg = self.setup.run_setup(HERE, choices, launcher_thirdparty, log=lambda m: self.q.put(("log", m)),
                                           **({"again": self.again} if self.again else {}))
                if self.deck:
                    try:
                        boot = os.path.join(cfg["ashita_dir"], "config", "boot", cfg.get("ashita_boot", core.DEFAULT_BOOT))
                        linux.deck_defaults(HERE, boot)
                        self.q.put(("log", "Steam Deck: the game is set to the Deck's screen (1280 x 800)."))
                        linux.install_desktop_entry(HERE)
                        self.q.put(("log", "Added XI: Forever Offline to the menu: add it to Steam on the launcher's SYSTEM > Linux page."))
                    except Exception as e:
                        self.q.put(("log", f"Could not set the Steam Deck defaults ({e})."))
                self.q.put(("done", None))
            except Exception as e:
                self.q.put(("fail", str(e)))
        threading.Thread(target=work, daemon=True).start()
        self.after(200, self.pump)

    def pump(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == "log":
                    self.log_box.insert("end", value + "\n")
                    self.log_box.see("end")
                elif kind == "done":
                    self.log_box.insert("end", "\nAll set. Press Open the launcher, then PLAY.\n")
                    self.done = True
                    self.next_btn.configure(text="Open the launcher", state="normal", command=self.destroy)
                    return
                elif kind == "fail":
                    self.log_box.insert("end", f"\nSetup stopped: {value}\nFix that and press Install again; finished steps are kept.\n")
                    self.next_btn.configure(text="Install", state="normal", command=self.start_install)
                    self.back_btn.configure(state="normal")
                    return
        except queue.Empty:
            pass
        self.after(200, self.pump)


_LAUNCHER_MUTEX = None

def one_launcher_only():
    """Only one launcher at a time. A second one (an old window hidden behind the game, or a double click) used to
    start the servers again next to the first one's, and players got FFXI-3001 or the game closing right away.
    Returns True when this launcher may go on."""
    global _LAUNCHER_MUTEX
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        for _ in range(15):                # (a launcher that restarts itself after an update: the old one is still closing)
            _LAUNCHER_MUTEX = k32.CreateMutexW(None, False, "XIForeverOfflineLauncher")
            if k32.GetLastError() != 183:  # ERROR_ALREADY_EXISTS
                return True
            k32.CloseHandle(_LAUNCHER_MUTEX)
            _LAUNCHER_MUTEX = None
            time.sleep(1)
        _LAUNCHER_MUTEX = k32.CreateMutexW(None, False, "XIForeverOfflineLauncher")
    except Exception:
        return True
    try:
        close_other = messagebox.askyesno(
            "XI: Forever Offline",
            "The launcher is already open (it may be behind other windows, or still closing).\n\n"
            "Yes = close the other one and its servers, and open this one.\nNo = keep the other one.")
    except Exception:
        close_other = False
    if not close_other:
        return False
    me, parent = os.getpid(), os.getppid()    # (the packaged exe runs as two processes: its starter and us)
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne %d -and $_.ProcessId -ne %d -and "
              "(($_.Name -like 'XI*Forever*Offline*.exe' -and $_.CommandLine -notlike '*--run*') -or "
              "(($_.Name -eq 'pythonw.exe' -or $_.Name -eq 'python.exe') -and $_.CommandLine -like '*launcher_gui.pyw*')) } | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }") % (me, parent)
    try:
        core._run(["powershell", "-NoProfile", "-Command", script])
        for n in core.SERVERS + ["xiloader"]:
            core.kill(n)
        core.kill_squad_chat()
    except Exception:
        pass
    time.sleep(2)
    return True


def bring_to_front(win):
    """(2026-11-18, Yumainai) after the admin prompt Windows often opens the elevated launcher behind other windows (or
    without its taskbar button flashing), so it looked like it never opened. Raise it once it is drawn."""
    def up():
        try:
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
            win.after(400, lambda: win.attributes("-topmost", False))
            win.focus_force()
        except Exception:
            pass
    try:
        win.after(250, up)
    except Exception:
        pass


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--run":     # the packaged exe running one of the kit's scripts (see core.py_cmd)
        core.run_script_main(sys.argv[2:])
        return
    if os.name == "nt" and not is_admin():
        elevate_and_exit()
    if os.name == "nt" and not one_launcher_only():
        return
    if linux is not None and not one_launcher_only_linux():
        return
    try:                                          # the launcher copy the last update moved aside (it has closed now)
        import launcher_update
        launcher_update.cleanup_old_exes(HERE)
    except Exception:
        pass
    try:
        if not os.path.exists(os.path.join(HERE, "config.json")):     # first run on a new PC: set everything up first
            wizard = SetupWizard()
            wizard.mainloop()
            if not wizard.done or not os.path.exists(os.path.join(HERE, "config.json")):
                return
        elif "--setup-again" in sys.argv[1:]:      # SYSTEM > Settings > "Run setup again..." (the launcher restarted itself)
            try:
                wizard = SetupWizard(again=core.load_config(os.path.join(HERE, "config.json")))
                wizard.mainloop()
            except Exception:                      # whatever happens there, the launcher still opens
                os.makedirs(LOGS, exist_ok=True)
                with open(os.path.join(LOGS, "setup-again-error.log"), "w") as f:
                    f.write(traceback.format_exc())
        app = App()
        bring_to_front(app)
        try:                                      # the opening theme of a limited-time look, while one is in date
            import launcher_theme
            launcher_theme.start(app)
        except Exception:
            try:                                  # (2026-11-23) the reason the song (and theme strip) did not come, in logs\theme-music.log
                launcher_theme.note("start failed: " + traceback.format_exc().strip().replace("\n", " | "))
            except Exception:
                pass
        app.mainloop()
    except Exception:
        os.makedirs(LOGS, exist_ok=True)
        err = traceback.format_exc()
        with open(os.path.join(LOGS, "launcher-error.log"), "w") as f:
            f.write(err)
        try:
            messagebox.showerror("Launcher crashed", err[-1500:])
        except Exception:
            pass


if __name__ == "__main__":
    main()
