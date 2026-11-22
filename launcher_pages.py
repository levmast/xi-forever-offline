"""The launcher's newer look (2026-11): the eight-button bar, the World and Rules pages, the Play page layout and
the System pages. launcher_gui.pyw builds its windows as before and then hands over to build() here.

How it fits together:
- The settings still live in the Rates tab (launcher_gui.RatesTab). It is made as always but not shown; the pages
  here are another view of its Tk variables, so PLAY reads and saves exactly what it did before.
- launcher_settings.py says which setting goes on which page. A new setting needs a line there.
- "classic_ui": true in config.json brings the old pages back; so does any error while these are being made."""
import os
import tkinter as tk
from tkinter import messagebox, ttk

import launcher_core as core
import launcher_settings as st
import launcher_widgets as w
from launcher_widgets import BG, BORDER, DIM, FG, GOLD, GOLD_LIT, PANEL, PANEL2, UI_FONT
from launcher_widgets import LINE as LINE_COLOUR

# the page buttons along the bottom: (picture in assets\ui, name, the pages it opens)
NAV_BUTTONS = (("home", "HOME", ("Play",)), ("world", "WORLD", ("World",)), ("rules", "RULES", ("Rules",)),
               ("squad", "SQUADS", ("Squad",)),
               ("options", "OPTIONS", ("Graphics", "Shaders", "Controller", "Addons", "Plugins", "Other")),
               ("coop", "CO-OP", ("Co-op",)), ("system", "SYSTEM", ("Settings", "Patch notes", "Characters", "Era", "About")))
WINDOW = (1100, 810)            # one size for every page
BANNER = (800, 320)             # the Play page's picture (the classic page: 920 x 368)
DISCORD = "https://discord.gg/2bh3QYPptz"       # the invite in README.md

WORLD_CARDS = {     # shorter words than core.WORLDS, which the first-run setup shows in full
    "quiet": "No town crowds or bot players. Squad mates use scripted lines. Nothing uses the AI.",
    "living": "Town crowds, field parties, bot players who level, craft and chat with ready-made lines, and a stocked auction house.",
    "living_ai": "The living world, plus AI-written chatter, bots who answer you and squad mates who talk. "
                 "Needs Ollama and a model, about 8 GB.",
}
PRESET_CARDS = (("Era default", "Everything at the era's own pace."),
                ("Relaxed solo", "2x experience and skill-ups, 1.5x drops and gil."),
                ("Fast", "5x experience, 4x skill-ups, 2x drops, 3x gil."))

class _Gui:
    """launcher_gui's own names (HERE, ASSETS, tp, linux, the picture sizes...), read and set where they live."""

    def __init__(self, names):
        self.__dict__["_names"] = names

    def __getattr__(self, name):
        return self._names[name]

    def __setattr__(self, name, value):
        self._names[name] = value


G = None            # launcher_gui's names (set by prepare)


def prepare(app, names):
    """Called before the launcher builds its pages, with launcher_gui's globals()."""
    global G
    G = _Gui(names)
    # (2026-11-21) a taller picture fills the Play page (it left empty bands above and below). Not on a short screen
    # (the Steam Deck's 800 lines, or a laptop): there the window is shorter and the classic height fits.
    global BANNER
    try:
        tall = names.get("linux") is None and app.winfo_screenheight() >= 900
    except Exception:
        tall = False
    if tall:
        width = 1056 if names.get("coopgui") is not None else 936      # (launcher_gui.fit_window: 1100 / 980 wide)
        BANNER = (width, round(width / 2.5))
    G.GALLERY_W, G.GALLERY_H = BANNER      # the press and loading pictures are cut to this when they are loaded
    G.ACCENT = GOLD                         # one highlight colour: what the older pages drew in cyan is gold too
    if "CheckList" in names:                # the "download" tag in the addon and plugin lists was cyan as well
        names["CheckList"].TAG_COLORS = dict(names["CheckList"].TAG_COLORS, download="#8aa9bd")
    for module in (names.get("coopgui"),):
        if module is not None and hasattr(module, "ACCENT"):
            module.ACCENT = GOLD


def player_install(app):
    return bool(app.cfg.get("mariadb_dir"))


def log_problem(what):
    """A problem that the launcher carries on from: kept in logs\\new-pages-error.log to look at later."""
    import traceback
    try:
        os.makedirs(G.LOGS, exist_ok=True)
        with open(os.path.join(G.LOGS, "new-pages-error.log"), "a", encoding="utf-8") as handle:
            handle.write(what + "\n" + traceback.format_exc() + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- controls from the settings table
def rate_field(key):
    return next(f for f in core.RATE_FIELDS if f[0] == key)


def variable_of(tab, entry):
    if entry["kind"] in (st.RATE, st.PERCENT, st.NUMBER, st.FLAG):
        return tab.vars[entry["key"]]
    return getattr(tab, entry["attr"])


def make_control(parent, entry, tab):
    """The control for one line of launcher_settings.SETTINGS, showing the Rates tab's own variable."""
    kind, var = entry["kind"], variable_of(tab, entry)
    if kind in (st.RATE, st.PERCENT, st.NUMBER):
        _id, _file, _key, _label, _default, lo, hi, _type = rate_field(entry["key"])
        if kind == st.RATE:
            return w.Stepper(parent, var, lo, hi, step=entry.get("step", 0.25), unit="x", special=entry.get("special"))
        if kind == st.PERCENT:
            return w.Stepper(parent, var, lo, hi, step=entry.get("step", 0.05), scale=100.0, unit="%")
        return w.Stepper(parent, var, lo, hi, step=entry.get("step", 1), integer=True)
    if kind == st.COUNT:
        return w.Stepper(parent, var, entry["lo"], entry["hi"], step=entry["step"], integer=True)
    if kind == st.CHOICE:
        return w.Choice(parent, var, entry["options"])
    command = getattr(tab, entry["command"]) if entry.get("command") else None
    return w.Switch(parent, var, command=command)


def fill_card(card, entries, tab, wrap=300):
    """Puts the settings into a card, one line each. Returns {key: control}."""
    made = {}
    for entry in entries:
        if entry["key"] == "bots_head_start" and getattr(tab, "head_start_done", False):
            continue        # used once per world, then gone for good
        if not entry["label"]:      # a choice that is the whole section (seasonal events)
            line = tk.Frame(card.body, bg=PANEL)
            line.pack(fill="x", pady=(4, 2))
            made[entry["key"]] = make_control(line, entry, tab)
            made[entry["key"]].pack(side="left")
            continue
        made[entry["key"]] = card.row(entry["label"], lambda parent, e=entry: make_control(parent, e, tab), tip=entry["tip"])
        if entry["note"]:
            card.note(entry["note"], wrap=wrap)
    return made


class SettingsPage(w.ScrollPage):
    """A page of cards made from launcher_settings: the page's sections in columns."""
    page, title, subtitle = "", "", ""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app, self.tab, self.player = app, app.rates_tab, player_install(app)
        self.cards, self.controls, self._pending = {}, {}, None
        w.page_header(self.body, self.title, self.subtitle).pack(fill="x")
        self.build_top()
        self.build_columns()
        self.build_bottom()
        self.watch()
        self.refresh()

    def build_top(self):
        pass

    def build_bottom(self):
        pass

    def build_columns(self):
        columns = st.sections(self.page, self.player)
        grid = tk.Frame(self.body, bg=BG)
        grid.pack(fill="x", pady=(12, 0))
        for index, column in enumerate(columns):
            grid.grid_columnconfigure(index, weight=1, uniform="column")
            holder = tk.Frame(grid, bg=BG)
            holder.grid(row=0, column=index, sticky="new", padx=(0 if index == 0 else 6, 0 if index == len(columns) - 1 else 6))
            for name, entries in column:
                master = getattr(self.tab, st.MASTERS[name]) if name in st.MASTERS else None
                card = w.Card(holder, name, master=master)
                card.pack(fill="x", pady=(0, 10))
                if name in st.SECTION_NOTES:
                    card.note(st.SECTION_NOTES[name])
                self.controls.update(fill_card(card, entries, self.tab))
                self.cards[name] = card
                self.extend_card(name, card)
        self.grid = grid

    def extend_card(self, name, card):
        pass

    # the cards at the top (world, preset) show which one the settings match: look again after any change
    def watch(self):
        seen = list(self.tab.vars.values())
        for value in vars(self.tab).values():
            if isinstance(value, tk.Variable) and value not in seen:
                seen.append(value)
        for var in seen:
            var.trace_add("write", self.changed)

    def changed(self, *_a):
        if self._pending is None:
            try:
                self._pending = self.after_idle(self._refresh_now)
            except tk.TclError:
                pass

    def _refresh_now(self):
        self._pending = None
        try:
            self.refresh()
        except tk.TclError:
            pass

    def refresh(self):
        pass


# ---------------------------------------------------------------- World
class WorldPage(SettingsPage):
    page, title, subtitle = "world", "World", "Who else lives in Vana'diel."

    def build_top(self):
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        self.world_cards = {}
        for index, (key, (label, _about)) in enumerate(core.WORLDS.items()):
            row.grid_columnconfigure(index, weight=1, uniform="world")
            card = w.ChoiceCard(row, label, WORLD_CARDS.get(key, _about), lambda k=key: self.pick_world(k), wrap=300)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 0 if index == len(core.WORLDS) - 1 else 6))
            self.world_cards[key] = card
        line = tk.Frame(self.body, bg=BG)
        line.pack(fill="x", pady=(12, 0))
        tk.Label(line, text="Population", bg=BG, fg=FG, font=(UI_FONT, 10, "bold")).pack(side="left", padx=(0, 12))
        self.population = tk.StringVar(value="custom")
        options = [(key, label) for key, (label, *_rest) in core.POPULATIONS.items()] + [("custom", "Custom")]
        w.Choice(line, self.population, options, command=self.pick_population, bg=BG).pack(side="left")
        self.population_text = tk.Label(line, text="", bg=BG, fg=DIM, font=(UI_FONT, 9))
        self.population_text.pack(side="left", padx=(8, 0))

    def extend_card(self, name, card):
        if name == "AI chat" and hasattr(self.tab, "ai_model"):
            line = tk.Frame(card.body, bg=PANEL)
            line.pack(fill="x", pady=2, before=card.body.winfo_children()[0] if card.body.winfo_children() else None)
            tk.Label(line, text="Model", bg=PANEL, fg=FG, font=(UI_FONT, 10)).pack(side="left")
            w.button(line, "Change", self.change_model, small=True).pack(side="right")
            tk.Label(line, textvariable=self.tab.ai_model, bg=PANEL, fg=FG, font=(UI_FONT, 10, "bold")).pack(side="right", padx=(0, 10))
            # downloads report their progress into the Rates tab's note: show that note here
            self.tab.ai_model_note = card.note(self.model_words())
            self.tab.ai_model_note.pack_configure(after=line)

    def model_words(self):
        tp = G.tp
        if tp is None:
            return ""
        now = self.tab.ai_model.get()
        return next((words[0].upper() + words[1:] + "." for model, words in tp.SUGGESTED_MODELS if model == now),
                    "Bigger models chat better but need more video memory.")

    def change_model(self):
        ModelDialog(self, self.tab)

    def now(self):
        rates = self.tab.collect()
        return core.world_of(rates), core.population_of(rates), rates

    def pick_world(self, key):
        world, _population, _rates = self.now()
        if world == "custom" and not messagebox.askyesno("World", f"Change your own mix of switches to {core.WORLDS[key][0]}?",
                                                         parent=self):
            return
        self.tab.world_box.set(self.tab.world_names[key])
        self.tab.pop_box.set("Custom")          # the world card leaves the sizes alone
        self.tab.fill_world()

    def pick_population(self):
        key = self.population.get()
        if key not in core.POPULATIONS:
            self.refresh()
            return
        self.tab.world_box.set("Custom")        # the population buttons leave the switches alone
        self.tab.pop_box.set(self.tab.pop_names[key])
        self.tab.fill_world()

    def refresh(self):
        world, population, rates = self.now()
        for key, card in self.world_cards.items():
            card.set_selected(key == world)
        if self.population.get() != population:
            self.population.set(population)
        self.population_text.configure(text=f"{rates['crowds_per_zone']} adventurers per town  ·  "
                                            f"{rates['bots_online']} bot players online")


class ModelDialog(tk.Toplevel):
    """Pick the local AI model for squad and town chat: a suggested one, any Ollama model name, or a .gguf file."""

    def __init__(self, parent, tab):
        super().__init__(parent)
        self.tab = tab
        self.title("AI chat model")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent.winfo_toplevel())
        tp = G.tp
        tk.Label(self, text="AI chat model", bg=BG, fg=w.PARCH, font=w.head_font(self, 16)).pack(anchor="w", padx=18, pady=(14, 2))
        tk.Label(self, text="Bigger models chat better but need more video memory and can lower your frame rate. "
                 "Any model from ollama.com/library works: type its name.", bg=BG, fg=DIM, font=(UI_FONT, 9),
                 wraplength=440, justify="left").pack(anchor="w", padx=18)
        box = tk.Frame(self, bg=BG)
        box.pack(fill="x", padx=18, pady=(10, 4))
        names = [model for model, _words in tp.SUGGESTED_MODELS]
        ttk.Combobox(box, values=names, textvariable=tab.ai_model, width=30).pack(side="left")
        listing = tk.Frame(self, bg=BG)
        listing.pack(fill="x", padx=18, pady=(4, 8))
        for model, words in tp.SUGGESTED_MODELS:
            line = tk.Frame(listing, bg=BG)
            line.pack(fill="x")
            name = w.link(line, model, lambda m=model: tab.ai_model.set(m))
            name.pack(side="left")
            tk.Label(line, text=words, bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(side="left", padx=(8, 0))
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=18, pady=(4, 16))
        w.button(bar, "Use and download", self.use, primary=True).pack(side="left")
        w.button(bar, "Use a .gguf file...", self.gguf).pack(side="left", padx=8)
        w.button(bar, "Close", self.destroy).pack(side="right")

    def use(self):
        self.destroy()
        self.tab.use_ai_model()

    def gguf(self):
        self.destroy()
        self.tab.use_gguf()


# ---------------------------------------------------------------- Rules
class RulesPage(SettingsPage):
    page, title, subtitle = "rules", "Rules", "How fast and how forgiving. 1x is the era's own pace."

    def build_top(self):
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill="x", pady=(12, 0))
        self.preset_cards = {}
        count = len(PRESET_CARDS) + 1
        for index, (name, words) in enumerate(PRESET_CARDS):
            row.grid_columnconfigure(index, weight=1, uniform="preset")
            card = w.ChoiceCard(row, name, words, lambda n=name: self.pick_preset(n), wrap=210)
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 6, 6))
            self.preset_cards[name] = card
        row.grid_columnconfigure(count - 1, weight=1, uniform="preset")
        self.build_profiles(row).grid(row=0, column=count - 1, sticky="nsew", padx=(6, 0))

    def build_profiles(self, parent):
        """My builds: the rate profiles (save these settings under a name, load them later, share them as .txt files)."""
        outer = tk.Frame(parent, bg=BORDER)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(inner, bg=PANEL)
        head.pack(fill="x", padx=14, pady=(10, 4))
        title = tk.Label(head, text="My builds", bg=PANEL, fg=FG, font=(UI_FONT, 11, "bold"))
        title.pack(side="left")
        self.custom_mark = tk.Label(head, text="", bg=PANEL, fg=GOLD, font=(UI_FONT, 8, "bold"))
        self.custom_mark.pack(side="right")
        self.profile = ttk.Combobox(inner, values=core.list_profiles(G.HERE), state="readonly", width=12)
        self.profile.pack(fill="x", padx=14, pady=(0, 4))
        bar = tk.Frame(inner, bg=PANEL)
        bar.pack(fill="x", padx=14, pady=(0, 10))
        for index, (text, action) in enumerate((("Load", "load_profile"), ("Save as", "save_profile"),
                                                ("Import", "import_profile"), ("Export", "export_profile"))):
            bar.grid_columnconfigure(index, weight=1, uniform="build")
            b = w.button(bar, text, lambda a=action: self.profile_action(a), small=True)
            b.configure(padx=2)
            b.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 2, 0))
        w.Tip(title, "Your own settings saved under a name, to load later or share as .txt files.")
        return outer

    def profile_action(self, action):
        self.tab.profile.set(self.profile.get())
        getattr(self.tab, action)()
        self.profile.configure(values=core.list_profiles(G.HERE))
        self.profile.set(self.tab.profile.get())

    def build_bottom(self):
        line = tk.Frame(self.body, bg=BG)
        line.pack(fill="x", pady=(2, 0))
        self.missing = tk.Label(line, text="", bg=BG, fg=GOLD, font=(UI_FONT, 9))
        self.missing.pack(side="left")
        w.link(line, "Classic settings list", lambda: show_classic(self.app)).pack(side="right")
        # (2026-11-21) the squad rules are a section of this page now (launcher_settings.py, "Squad")

    def names(self):
        return [name for name, _words in PRESET_CARDS]

    def pick_preset(self, name):
        rates = self.tab.collect()
        now = st.preset_now(core, rates, self.names())
        if now == name:
            return
        if now is None and not messagebox.askyesno("Rules", f"Replace the rates you set yourself with {name}?\n\n"
                                                   "(Save as... under My builds keeps a copy first.)", parent=self):
            return
        self.tab.preset.set(name)
        self.tab.fill_preset()

    def refresh(self):
        rates = self.tab.collect()
        now = st.preset_now(core, rates, self.names())
        for name, card in self.preset_cards.items():
            card.set_selected(name == now)
        self.custom_mark.configure(text="" if now else "YOUR OWN RATES")
        missing = st.missing_keys(rates)
        self.missing.configure(text=f"{len(missing)} newer setting(s) are only on the classic list for now." if missing else "")


def show_classic(app):
    """The old Rates page, shown as a page of its own (it stays in step: both show the same settings)."""
    if "Rates" not in app.page_index:
        app.tabs.add(app.rates_tab, text="  Rates  ")
        app.page_index["Rates"] = len(app.tabs.tabs()) - 1
    app.select_tab(app.page_index["Rates"])


# ---------------------------------------------------------------- Era (the dev PC only)
class EraPage(SettingsPage):
    page, title, subtitle = "era", "Era", "This PC only. Players always get the era values."

    def build_top(self):
        names = [name for name in core.RATE_PRESETS if name not in [n for n, _w in PRESET_CARDS]]
        if not names:
            return
        line = tk.Frame(self.body, bg=BG)
        line.pack(fill="x", pady=(12, 0))
        tk.Label(line, text="Fill in:", bg=BG, fg=DIM, font=(UI_FONT, 9)).pack(side="left", padx=(0, 8))
        for name in names:
            w.button(line, name, lambda n=name: self.fill(n), small=True).pack(side="left", padx=(0, 6))

    def fill(self, name):
        if messagebox.askyesno("Era", f"Fill in the preset '{name}'? It replaces the rates on the Rules page too.", parent=self):
            self.tab.preset.set(name)
            self.tab.fill_preset()


# ---------------------------------------------------------------- Play
class PlayPage:
    """The Play page's newer layout, made from the widgets launcher_gui has already built (so start, stop, the loading
    pictures and the log work as they always did): the picture with a summary of what PLAY will start beside it, PLAY
    and STOP sharing one spot, a smaller DUALBOX, and an update notice only when there is an update."""

    def __init__(self, app):
        self.app, self.player = app, player_install(app)
        self.box = app.stage.master
        self.strip, self.buttons, self.actions = app.progress.master, app.play_btn.master, app.update_btn.master
        self.status_label = next(c for c in self.strip.pack_slaves() if c is not app.progress)
        self.classic = [(widget, widget.pack_info()) for widget in
                        (app.stage, self.strip, self.buttons, self.actions, self.status_label, app.progress,
                         app.play_btn, app.stop_btn, app.dual_btn)]
        self.made = []
        try:
            self.arrange()
        except Exception:
            self.restore()
            raise
        self.running_shown, self.busy_shown, self.notice_shown, self.ticks = None, None, False, 0
        self.tick()

    def restore(self):
        """Back to the classic layout (something went wrong while arranging)."""
        for widget in self.made:
            try:
                widget.destroy()
            except tk.TclError:
                pass
        for widget, info in self.classic:
            widget.pack_forget()
        self.app.stage.configure(width=G.GALLERY_W + 2, height=G.GALLERY_H + 2)
        for widget, info in self.classic:
            info = {k: v for k, v in info.items() if k != "in"}
            widget.pack(**info)

    def frame(self, parent, **options):
        made = tk.Frame(parent, bg=options.pop("bg", BG), **options)
        self.made.append(made)
        return made

    def arrange(self):
        app = self.app
        for widget in (app.stage, self.strip, self.buttons, self.actions):
            widget.pack_forget()
        self.build_notice()
        # (2026-11-21) the picture across the whole page at its own shape (2.5 : 1, nothing cut off), PLAY under it,
        # and the newest patch notes in a strip filling the rest. The World / Rules / Squad summary tiles are gone:
        # the same pages are one click away in the bar below.
        try:
            self.box.pack_configure(fill="both", expand=True)
        except tk.TclError:
            pass
        top = self.frame(self.box)
        top.pack(fill="x", pady=(4, 14))
        self.top = top
        app.stage.configure(width=BANNER[0] + 2, height=BANNER[1] + 2)
        app.stage.pack(in_=top)
        app.stage.lift()
        self.tiles = {}
        row = self.frame(self.box)
        row.pack(fill="x")
        notes = self.frame(self.box)
        notes.pack(side="bottom", fill="both", expand=True, pady=(14, 4))
        self.build_notes(notes)
        self.buttons.pack(in_=row, side="left")
        self.buttons.lift()
        app.stop_btn.pack_forget()
        app.play_btn.pack_configure(padx=(0, 18))
        app.dual_btn.pack_configure(padx=(0, 22))
        small = G.load_ui_images("dualbox_small")
        if small["normal"] is not None:
            app._images.extend(i for i in small.values() if i)
            app.dual_btn.imgs = small
            tk.Canvas.configure(app.dual_btn, width=small["normal"].width(), height=small["normal"].height())
            app.dual_btn._show()
        self.strip.pack(in_=row, side="left", fill="x", expand=True)
        self.strip.lift()
        self.status_label.pack_forget()
        app.progress.pack_forget()
        app.log.configure(height=11)        # the picture frame is lower than the classic one
        ttk.Style(app).configure("Solo.Horizontal.TProgressbar", background=GOLD, lightcolor=GOLD, darkcolor=GOLD)
        self.status_label.configure(font=(UI_FONT, 12))
        self.status_label.pack(side="top", fill="x")
        self.hint = tk.Label(self.strip, text="PLAY starts your world, then the game.", bg=BG, fg=DIM, font=(UI_FONT, 9), anchor="w")
        self.hint.pack(side="top", fill="x")
        self.made.append(self.hint)
        if not self.player:              # the dev PC: the server lights and the log, shown in the picture's place
            self.log_link = w.link(self.strip, "Show the server log", self.toggle_log)
            self.log_link.pack(side="bottom", anchor="w", pady=(6, 0))
            self.made.append(self.log_link)

    def tile(self, parent, name, page):
        outer = self.frame(parent, bg=BORDER, cursor="hand2")
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        middle = tk.Frame(inner, bg=PANEL)
        middle.pack(fill="x", expand=True, padx=14)
        head = tk.Frame(middle, bg=PANEL)
        head.pack(fill="x")
        title = tk.Label(head, text=name.upper(), bg=PANEL, fg=GOLD, font=(UI_FONT, 8, "bold"))
        title.pack(side="left")
        change = tk.Label(head, text="Change", bg=PANEL, fg=DIM, font=(UI_FONT, 8))
        change.pack(side="right")
        value = tk.Label(middle, text="", bg=PANEL, fg=FG, font=(UI_FONT, 11, "bold"), anchor="w")
        value.pack(fill="x")
        about = tk.Label(middle, text="", bg=PANEL, fg=DIM, font=(UI_FONT, 9), anchor="w")
        about.pack(fill="x")
        for widget in (outer, inner, middle, head, title, change, value, about):
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", lambda e, p=page: self.app.go(p))
            widget.bind("<Enter>", lambda e, o=outer: o.configure(bg=GOLD), add="+")
            widget.bind("<Leave>", lambda e, o=outer: o.configure(bg=BORDER), add="+")
        return {"frame": outer, "value": value, "about": about}

    def build_notice(self):
        self.notice = self.frame(self.box, bg=GOLD)
        inner = tk.Frame(self.notice, bg=PANEL2)
        inner.pack(fill="x", padx=1, pady=1)
        self.notice_text = tk.Label(inner, text="", bg=PANEL2, fg=FG, font=(UI_FONT, 10, "bold"))
        self.notice_text.pack(side="left", padx=(14, 10), pady=7)
        tk.Label(inner, text="Your characters, squad mates and settings are kept.", bg=PANEL2, fg=DIM, font=(UI_FONT, 9)).pack(side="left")
        w.button(inner, "Update now", self.update_now, primary=True, small=True).pack(side="right", padx=6)
        w.link(inner, "What's new", self.whats_new, bg=PANEL2).pack(side="right", padx=10)

    # ----- what the page shows, looked at a few times a second -----
    def tick(self):
        app = self.app
        try:
            running = bool(app.running)
            busy = running or app.play_btn.state == "disabled"
            if running != self.running_shown:
                self.running_shown = running
                if running:
                    app.play_btn.pack_forget()
                    app.stop_btn.pack(side="left", padx=(0, 18), before=app.dual_btn)
                else:
                    app.stop_btn.pack_forget()
                    app.play_btn.pack(side="left", padx=(0, 18), before=app.dual_btn)
            if busy != self.busy_shown:
                self.busy_shown = busy
                if busy:
                    self.hint.pack_forget()
                    app.progress.pack(side="top", fill="x", pady=(8, 0))
                else:
                    app.progress.pack_forget()
                    self.hint.pack(side="top", fill="x")
            if self.ticks % 4 == 0:
                self.refresh_summary()
                self.refresh_notice()
            self.ticks += 1
            app.after(300, self.tick)
        except tk.TclError:
            pass                    # the window is closing

    # ----- the newest patch notes, beside the picture -----
    @staticmethod
    def latest_notes():
        """(title, [(kind, text)]) of the newest version in PATCH-NOTES.md; kind is 'head' or 'item'."""
        try:
            with open(os.path.join(G.HERE, "PATCH-NOTES.md"), "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            return None, []
        title, lines = None, []
        for raw in text.splitlines():
            line = raw.strip()
            if line.startswith("## "):
                if title is not None:
                    break
                title = line[3:].strip()
            elif title is None or not line or line.startswith("# "):
                continue
            elif line.startswith("### "):
                lines.append(("head", line[4:].strip()))
            elif line.startswith(("\u2022", "- ", "* ")):
                lines.append(("item", line.lstrip("\u2022-* ").strip()))
            else:
                lines.append(("item", line))
        return title, lines

    def build_notes(self, parent):
        outer = self.frame(parent, bg=BORDER)
        outer.pack(fill="both", expand=True)
        inner = tk.Frame(outer, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Frame(inner, bg=GOLD, width=3).pack(side="left", fill="y")       # a thin gold edge on the left
        left = tk.Frame(inner, bg=PANEL, width=210)
        left.pack(side="left", fill="y", padx=(16, 0), pady=(10, 10))
        left.pack_propagate(False)
        tk.Label(left, text="PATCH NOTES", bg=PANEL, fg=GOLD, font=(UI_FONT, 8, "bold"), anchor="w").pack(fill="x")

        title, lines = self.latest_notes()
        version, when = "", ""
        if title:
            parts = [p.strip() for p in title.split("\u00b7")]
            version, when = parts[0], (parts[1] if len(parts) > 1 else "")
        mine = ""
        try:
            import launcher_update as lu
            mine = (lu.installed_version(G.HERE) or "").lstrip("v")
        except Exception:
            pass
        tk.Label(left, text=("Version " + version.lstrip("v")) if version else "Patch notes", bg=PANEL, fg=FG,
                 font=(UI_FONT, 14, "bold"), anchor="w").pack(fill="x", pady=(2, 0))
        sub = [x for x in (when, "your version" if mine and version.lstrip("v") == mine else "") if x]
        if sub:
            tk.Label(left, text="  \u00b7  ".join(sub), bg=PANEL, fg=DIM, font=(UI_FONT, 9), anchor="w").pack(fill="x")
        more = tk.Label(left, text="All patch notes  \u203a", bg=PANEL, fg=DIM, font=(UI_FONT, 9), cursor="hand2", anchor="w")
        more.pack(side="bottom", fill="x")
        more.bind("<Button-1>", lambda e: self.app.go("Patch notes"))
        more.bind("<Enter>", lambda e: more.configure(fg=GOLD_LIT))
        more.bind("<Leave>", lambda e: more.configure(fg=DIM))
        tk.Frame(inner, bg=LINE_COLOUR, width=1).pack(side="left", fill="y", pady=12)

        text = tk.Text(inner, bg=PANEL, fg=FG, relief="flat", bd=0, highlightthickness=0, wrap="word", height=1,
                       font=(UI_FONT, 9), cursor="arrow", padx=16, pady=2, spacing1=1, spacing3=3,
                       selectbackground=PANEL, inactiveselectbackground=PANEL)
        text.tag_configure("head", foreground=GOLD_LIT, font=(UI_FONT, 9, "bold"), spacing1=8, spacing3=3)
        text.tag_configure("item", lmargin1=0, lmargin2=13)
        text.tag_configure("dot", foreground=GOLD)
        text.tag_configure("dim", foreground=DIM)
        if lines:
            first = True
            for kind, words in lines:
                if kind == "head":
                    text.insert("end", words.upper() + "\n", "head")
                else:
                    # the card shows the first sentence of each note (the full text is one click away)
                    short = words.split(". ")[0].rstrip(".")
                    credit = words[words.rfind(" ("):] if words.endswith(")") and " (" in words and short != words else ""
                    credit = credit if len(credit) <= 30 else ""        # (a name or two, not a long remark)
                    if len(short) > 120:
                        short = short[:117].rsplit(" ", 1)[0] + "..."
                    text.insert("end", "\u2022  ", ("item", "dot"))
                    text.insert("end", short + ("." if not short.endswith(("...", ")", "!", "?")) else ""), "item")
                    text.insert("end", (credit.rstrip(".") if credit else "") + "\n", ("item", "dim"))
                first = False
        else:
            text.insert("end", "No patch notes in this install yet. They come with the next update.", "dim")
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True, pady=(8, 8))
        # the wheel scrolls the notes (there is no scroll bar: it would crowd the card)
        text.bind("<MouseWheel>", lambda e: (text.yview_scroll(int(-e.delta / 40) or (-1 if e.delta > 0 else 1), "units"), "break")[1])
        text.bind("<Button-4>", lambda e: (text.yview_scroll(-2, "units"), "break")[1])
        text.bind("<Button-5>", lambda e: (text.yview_scroll(2, "units"), "break")[1])
        text.bind("<Double-Button-1>", lambda e: self.app.go("Patch notes"))
        self.notes_text = text

    def refresh_summary(self):
        if not self.tiles:
            return                  # (the summary tiles were replaced by the patch notes)
        app, tab = self.app, self.app.rates_tab
        rates = tab.collect()
        world, population = core.world_of(rates), core.population_of(rates)
        words = [f"{core.POPULATIONS[population][0]} population" if population in core.POPULATIONS
                 else f"{rates['bots_online']} bots online" if rates.get("bots") else "No bot players"]
        if core.needs_ai(rates) and hasattr(tab, "ai_model"):
            words.append(tab.ai_model.get())
        self.show("World", core.WORLDS[world][0] if world in core.WORLDS else "Your own mix", "  \u00b7  ".join(words))
        preset = st.preset_now(core, rates, [name for name, _words in PRESET_CARDS])
        self.show("Rules", preset or "Your own rates",
                  f"Experience {w.number_text(rates['map.EXP_RATE'])}x  \u00b7  drops {w.number_text(rates['map.DROP_RATE_MULTIPLIER'])}x")
        squad = app.squad_tab
        if squad is None:
            self.show("Squad", "Squad", "Needs the database.")
        else:
            name = squad.char_var.get().split(" (#")[0]
            mates = [str(m.get("name", "")) for m in squad.mates if isinstance(m, dict)]
            about = ", ".join(mates[:5]) + (f" +{len(mates) - 5}" if len(mates) > 5 else "") if mates else "No squad mates yet."
            self.show("Squad", name or "No character yet", about if name else "Make one in the game first.")

    def show(self, name, value, about):
        tile = self.tiles[name]
        if tile["value"].cget("text") != value:
            tile["value"].configure(text=value)
        if tile["about"].cget("text") != about:
            tile["about"].configure(text=about)

    def update_info(self):
        info = getattr(getattr(self.app, "updates_tab", None), "update_info", None) if self.player else None
        if not info:
            return None, []
        return info, [k for k in ("kit", "server") if info.get(k, {}).get("newer")]

    def refresh_notice(self):
        info, newer = self.update_info()
        if newer and not self.notice_shown:
            newest = max((info[k].get("newest") or "" for k in newer))
            self.notice_text.configure(text=f"Version {newest.lstrip('v')} is ready." if newest else "An update is ready.")
            self.notice.pack(fill="x", pady=(0, 12), before=self.top)
        elif not newer and self.notice_shown:
            self.notice.pack_forget()
        self.notice_shown = bool(newer)

    def whats_new(self):
        info, newer = self.update_info()
        notes = next((info[k].get("notes") for k in newer if info[k].get("notes")), "") if info else ""
        messagebox.showinfo("What's new", (notes or "This version came without notes.")[:1800], parent=self.app)

    def update_now(self):
        open_system(self.app, "updates")
        self.app.updates_tab.player_update()

    def toggle_log(self):
        self.app.toggle_details()
        self.log_link.configure(text="Hide the server log" if self.app.showing_details else "Show the server log")


# ---------------------------------------------------------------- System
class SystemSections:
    """The Settings page (launcher_gui.UpdatesTab) shown one part at a time: Updates, GM and testing, Steam Deck,
    Team. The page is made as always; this sorts what it packed by its headings and shows the parts of one section,
    with the output box under them. A part with a heading nobody listed here goes with the first section, so nothing
    is ever out of reach."""
    HEADINGS = {"GM account for testing": "gm", "Linux": "linux", "Steam Deck": "linux", "Updates": "updates",
                "Publish an update for players": "team", "Updates from your team": "team",
                "Keep your server up to date with Phoenix": "team"}

    def __init__(self, tab, first):
        self.tab, self.parts, self.now = tab, {}, None
        packed = tab.pack_slaves()
        self.box = packed[-1]                       # the output box: shown under every section
        current = None
        for widget in packed[:-1]:
            if widget is getattr(tab, "contrib_frame", None):
                key = "team"
            elif isinstance(widget, tk.Label):
                key = self.HEADINGS.get(str(widget.cget("text")))
                if key:
                    current = key
                key = key or current
            else:
                key = self.heading_key(widget) or current
            self.parts.setdefault(key or first, []).append((widget, widget.pack_info()))
        self.show(first if first in self.parts else next(iter(self.parts), None))

    def heading_key(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Label):
                return self.HEADINGS.get(str(child.cget("text")))
        return None

    def show(self, key):
        if key is None or key == self.now:
            return
        self.now = key
        for parts in self.parts.values():
            for widget, _info in parts:
                widget.pack_forget()
        for widget, info in self.parts.get(key, []):
            widget.pack(before=self.box, **{k: v for k, v in info.items() if k != "in"})


def system_chips(app):
    """The System pages in order: (shown name, "section" or "page", which)."""
    sections, pages, chips = app.system_sections, app.page_index, []
    player = player_install(app)
    team = bool(app.cfg.get("contributor") or app.cfg.get("contributor_mode")) if player else True

    def section(name, key):
        if sections is not None and key in sections.parts and "Settings" in pages:
            chips.append((name, "section", key))

    def page(name, title=None):
        if (title or name) in pages:
            chips.append((name, "page", pages[title or name]))

    if player:
        section("Updates", "updates")
    else:
        section("Team", "team")
    page("Patch notes")
    page("Characters")
    section("GM and testing", "gm")
    section("Steam Deck" if G.linux is not None and G.linux.is_steam_deck() else "Linux", "linux")
    if player and team:
        section("Team", "team")
    page("Era")
    page("About")
    return chips


def open_system(app, key):
    """Opens the System page on one of its sections (updates, team, gm, linux)."""
    if app.system_sections is not None and key in app.system_sections.parts:
        app.system_sections.show(key)
    app.go("Settings")


class CharactersPage(w.ScrollPage):
    """Back up a character, put one back, or carry one (with its squad) to your other PC. The work is the Co-op page's
    own (launcher_coop_gui.CoopTab: save_character, restore_character, carry_save, carry_load); this page is where
    they are found, whether co-op is switched on or not."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app, self.coop, self.characters = app, app.coop_tab, []
        w.page_header(self.body, "Characters", "Back up a character, put one back, or carry one to your other PC.", note="").pack(fill="x")
        if self.coop is None:
            tk.Label(self.body, text="This page needs the game's database (db_user, db_pass and db_name in config.json).",
                     bg=BG, fg=DIM, font=(UI_FONT, 10)).pack(anchor="w", pady=(16, 0))
            return
        coop = self.coop
        if not hasattr(coop, "carry_auto"):             # the Co-op page makes these only in the classic look
            coop.carry_auto = tk.BooleanVar(value=bool(coop.cfg.get("char_sync")))
        if not hasattr(coop, "carry_folder_text"):
            coop.carry_folder_text = tk.StringVar()
        coop.carry_show_folder()
        line = tk.Frame(self.body, bg=BG)
        line.pack(fill="x", pady=(14, 0))
        tk.Label(line, text="Character", bg=BG, fg=FG, font=(UI_FONT, 10, "bold")).pack(side="left", padx=(0, 12))
        self.choice = tk.StringVar()
        self.picker = ttk.Combobox(line, textvariable=self.choice, state="readonly", width=24)
        self.picker.pack(side="left")
        w.button(line, "Refresh", self.load, small=True).pack(side="left", padx=8)
        grid = tk.Frame(self.body, bg=BG)
        grid.pack(fill="x", pady=(14, 0))
        for index in range(2):
            grid.grid_columnconfigure(index, weight=1, uniform="column")

        backup = w.Card(grid, "Backup")
        backup.grid(row=0, column=0, sticky="new", padx=(0, 6))
        backup.note("A backup file of the picked character, to restore in this same world. Restore replaces everything the "
                    "character did since the file was made.", wrap=460)
        bar = tk.Frame(backup.body, bg=PANEL)
        bar.pack(fill="x", pady=(6, 2))
        w.button(bar, "Save a backup...", lambda: self.call("save_character"), primary=True).pack(side="left")
        w.button(bar, "Restore from a backup...", lambda: self.call("restore_character")).pack(side="left", padx=8)
        world = w.Card(grid, "Whole database")
        world.grid(row=1, column=0, sticky="new", padx=(0, 6), pady=(10, 0))
        world.note("Everything in your world in one file: every character, the squads, the auction house.", wrap=460)
        bar = tk.Frame(world.body, bg=PANEL)
        bar.pack(fill="x", pady=(6, 2))
        w.button(bar, "Back up database now", self.backup_database).pack(side="left")
        w.button(bar, "Open backups folder", lambda: app.open_dir(os.path.join(G.HERE, "backups"))).pack(side="left", padx=8)

        carry = w.Card(grid, "Play on another PC")
        carry.grid(row=0, column=1, rowspan=2, sticky="new", padx=(6, 0))
        carry.note("Takes the picked character and its squad mates to your other PC. Each PC keeps its own world "
                   "(settings, bot players, linkshells).", wrap=460)
        bar = tk.Frame(carry.body, bg=PANEL)
        bar.pack(fill="x", pady=(6, 8))
        w.button(bar, "Save for another PC...", lambda: self.call("carry_save"), primary=True).pack(side="left")
        w.button(bar, "Load from another PC...", lambda: self.call("carry_load")).pack(side="left", padx=8)
        carry.row("Do it automatically: load on PLAY, save on STOP", lambda parent: w.Switch(parent, coop.carry_auto, command=coop.carry_toggle))
        bar = tk.Frame(carry.body, bg=PANEL)
        bar.pack(fill="x", pady=(6, 2))
        w.button(bar, "Folder...", coop.carry_pick_folder, small=True).pack(side="left")
        tk.Label(bar, textvariable=coop.carry_folder_text, bg=PANEL, fg=DIM, font=(UI_FONT, 9), anchor="w", justify="left",
                 wraplength=380).pack(side="left", padx=10)
        # (2026-11-20) character transfer: charcapture (VanaDreams, with permission) on the other game, char_import.py here
        bring = w.Card(grid, "Bring a character from another server")
        bring.grid(row=2, column=0, columnspan=2, sticky="new", pady=(10, 0))
        bring.note("From retail or another private server: 1) Get the capture add-on into that game's Ashita folder, "
                   "2) there: /addon load charcapture, zone once, then /capture, 3) make a character here in the lobby and log "
                   "out, 4) pick it above and Import. Jobs, skills, spells, key items, gil and bags come across (capped at this "
                   "world's level cap); quests, missions and fame don't. The character here is backed up first.", wrap=960)
        bar = tk.Frame(bring.body, bg=PANEL)
        bar.pack(fill="x", pady=(6, 2))
        w.button(bar, "Get the capture add-on...", self.get_capture).pack(side="left")
        w.button(bar, "Import a snapshot...", self.import_snapshot, primary=True).pack(side="left", padx=8)
        tk.Label(self.body, textvariable=coop.note_text, bg=BG, fg=GOLD, font=(UI_FONT, 9), anchor="w", justify="left",
                 wraplength=1000).pack(fill="x", pady=(12, 0))
        self.bind("<Map>", lambda e: self.load(), add="+")

    def get_capture(self):
        """Puts VanaDreams' charcapture add-on into the Ashita folder of the game the character is coming from."""
        from tkinter import filedialog
        folder = filedialog.askdirectory(title="The Ashita folder of the game you're bringing the character from", parent=self)
        if not folder:
            return
        import char_import as ci
        self.coop.job(lambda: ci.install_capture(folder, log=lambda _t: None),
                      lambda target: self.coop.note(f"charcapture is in {target}. In that game: /addon load charcapture, "
                                                    "zone once, then /capture. The file lands in its config\\charcapture folder."),
                      "Downloading charcapture...")

    def import_snapshot(self):
        """Reads a /capture file and puts it onto the character picked above (after a backup and a yes)."""
        from tkinter import filedialog
        import char_import as ci
        name = self.choice.get()
        if not name:
            messagebox.showinfo("Import", "Make the character in the lobby first, log out, then pick it above.", parent=self)
            return
        if getattr(self.app, "running", False):
            messagebox.showinfo("Import", "Press STOP first: a character is imported while the game is closed.", parent=self)
            return
        path = filedialog.askopenfilename(title="A snapshot made with /capture (config\\charcapture\\<Name>.json)",
                                          filetypes=[("Character snapshot", "*.json")], parent=self)
        if not path:
            return
        try:
            snap = ci.load_snapshot(path)
        except ci.ImportError_ as e:
            messagebox.showwarning("Import", str(e), parent=self)
            return
        max_level = ci.server_max_level(self.app.cfg.get("server_dir"))
        coop = self.coop

        def look():
            conn = coop.connect()
            try:
                charid = ci.find_character(conn, name)
                return charid, ci.plan(conn, snap, charid, max_level)
            finally:
                conn.close()

        def ask(result):
            charid, plan = result
            if not messagebox.askyesno("Import", ci.describe(plan) + f"\n\nPut this onto {name}? Its jobs, skills, spells, key "
                                       "items and bags here are replaced (a backup is made first).", icon="warning", parent=self):
                return

            def write():
                conn = coop.connect()
                try:
                    saved = ci.backup_first(conn, charid, name)
                    ci.apply(conn, plan)
                    return saved
                finally:
                    conn.close()

            coop.job(write, lambda saved: coop.note(f"{plan['name']} came across as {name}. The old {name} is backed up in "
                                                    f"{saved} (Restore from a backup puts it back)."), "Importing...")

        def failed(e):
            messagebox.showwarning("Import", str(e), parent=self)

        def guarded():
            try:
                return ("ok", look())
            except ci.ImportError_ as e:
                return ("err", e)

        coop.job(guarded, lambda r: ask(r[1]) if r[0] == "ok" else failed(r[1]), "Reading the snapshot...")

    def load(self):
        """Read the characters that are at home in this world (in the background: the database may be slow to answer)."""
        coop = self.coop

        def work():
            import launcher_passport as pp
            conn = coop.connect()
            try:
                return pp.home_characters(conn)
            finally:
                conn.close()

        def done(found):
            self.characters = [(charid, name) for charid, name in found]
            names = [name for _id, name in self.characters]
            self.picker.configure(values=names)
            if self.choice.get() not in names:
                self.choice.set(names[0] if names else "")

        coop.job(work, done)

    def call(self, method):
        """Runs one of the Co-op page's own actions for the character picked here."""
        coop = self.coop
        if not hasattr(coop, "character"):
            coop.character = tk.StringVar()
        if self.characters:
            coop.characters = list(self.characters)
        coop.character.set(self.choice.get())
        getattr(coop, method)()
        self.after(2500, self.load)             # a loaded or restored character may be new to the list

    def backup_database(self):
        open_system(self.app, "gm")             # its result is printed in the output box there
        self.app.updates_tab.run_script("setup_gm.py", ["backup"])


class PatchNotesPage(w.ScrollPage):
    """What changed in each update, from PATCH-NOTES.md in the kit (newest first; the same notes as #patch-notes)."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        w.page_header(self.body, "Patch notes", "What changed in each update.", note="").pack(fill="x")
        path = os.path.join(G.HERE, "PATCH-NOTES.md")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            text = ""
        mine = ""
        try:
            import launcher_update as lu
            mine = (lu.installed_version(G.HERE) or "").lstrip("v")
        except Exception:
            pass
        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x", pady=(10, 0))
        w.button(bar, "All releases on GitHub", lambda: app.open_url(f"https://github.com/{G.KIT_REPO_NAME}/releases"),
                 small=True).pack(side="left")
        w.button(bar, "Discord", lambda: app.open_url(DISCORD), small=True).pack(side="left", padx=8)
        if not text.strip():
            tk.Label(self.body, text="No patch notes in this install yet.", bg=BG, fg=DIM, font=(UI_FONT, 10)).pack(anchor="w", pady=14)
            return
        card = None
        for raw in text.splitlines():
            line = raw.rstrip()
            if line.startswith("## "):
                title = line[3:].strip()
                version = title.split()[0].lstrip("v") if title else ""
                card = w.Card(self.body, title + ("   ·   your version" if mine and version == mine else ""))
                card.pack(fill="x", pady=(12, 0))
            elif card is None or not line.strip() or line.startswith("# "):
                continue
            elif line.startswith("### "):
                tk.Label(card.body, text=line[4:].strip(), bg=PANEL, fg=GOLD_LIT, font=(UI_FONT, 10, "bold"),
                         anchor="w").pack(fill="x", pady=(8, 2))
            elif line.lstrip().startswith(("•", "- ", "* ")):
                row = tk.Frame(card.body, bg=PANEL)
                row.pack(fill="x", pady=1)
                tk.Label(row, text="•", bg=PANEL, fg=GOLD, font=(UI_FONT, 10)).pack(side="left", anchor="n", padx=(4, 6))
                tk.Label(row, text=line.lstrip().lstrip("•-* ").strip(), bg=PANEL, fg=FG, font=(UI_FONT, 10), anchor="w",
                         justify="left", wraplength=940).pack(side="left", fill="x")
            else:
                card.note(line.strip(), wrap=960)


class AboutPage(w.ScrollPage):
    """What this is, which version, and the credits."""

    def __init__(self, parent, app):
        super().__init__(parent)
        w.page_header(self.body, "About", "XI: Forever Offline", note="").pack(fill="x")
        versions = []
        try:
            import launcher_update as lu
            versions.append(("Launcher and kit", lu.installed_version(G.HERE) or "built from source"))
            if app.cfg.get("server_dir"):
                versions.append(("Server", lu.installed_version(app.cfg["server_dir"]) or "built from source"))
        except Exception:
            pass
        card = w.Card(self.body, "This install")
        card.pack(fill="x", pady=(14, 0))
        for name, value in versions:
            card.row(name, lambda parent, v=value: tk.Label(parent, text=v, bg=PANEL, fg=FG, font=(UI_FONT, 10, "bold")))
        card.row("Folder", lambda parent: tk.Label(parent, text=G.HERE, bg=PANEL, fg=DIM, font=(UI_FONT, 9)))
        bar = tk.Frame(card.body, bg=PANEL)
        bar.pack(fill="x", pady=(8, 2))
        w.button(bar, "Open this folder", lambda: app.open_dir(G.HERE), small=True).pack(side="left")
        w.button(bar, "Open logs folder", lambda: app.open_dir(G.LOGS), small=True).pack(side="left", padx=8)
        w.button(bar, "Project page on GitHub", lambda: app.open_url(f"https://github.com/{G.KIT_REPO_NAME}"), small=True).pack(side="left")
        w.button(bar, "Discord", lambda: app.open_url(DISCORD), small=True).pack(side="left", padx=8)
        credits = w.Card(self.body, "Credits")
        credits.pack(fill="x", pady=(10, 0))
        credits.note("An offline, single-player take on classic-era FINAL FANTASY XI: a 75-era server based on Phoenix (a fork of "
                     "LandSandBoat), a launcher, and Ashita addons. XI: Forever Offline is an unofficial fan project. It is not "
                     "affiliated with or endorsed by Square Enix. Square Enix material and the tools made by other people are "
                     "listed with their authors and licences in CREDITS.md.", wrap=980)
        path = os.path.join(G.HERE, "CREDITS.md")
        if os.path.exists(path):
            bar = tk.Frame(credits.body, bg=PANEL)
            bar.pack(fill="x", pady=(6, 2))
            w.button(bar, "Open CREDITS.md", lambda: open_file(app, path), small=True).pack(side="left")


def open_file(app, path):
    try:
        if G.IS_WINDOWS:
            os.startfile(path)
        else:
            G.linux.open_path(path)
    except Exception as e:
        messagebox.showinfo("Open", f"Could not open {path}: {e}", parent=app)


# ---------------------------------------------------------------- Squad: the rules for the whole squad, on the Squad page
def add_squad_rules(app):
    """Call timer, spell scrolls and kept gear, on the right of the Squad page's top line."""
    tab = app.squad_tab
    if tab is None:
        return
    rows = tab.pack_slaves()
    if not rows:
        return
    top = rows[0]                       # the line with the character box
    for entry in reversed(st.section_entries("squad", "Squad rules", player_install(app))):
        make_control_on(top, entry, app.rates_tab).pack(side="right", padx=(0, 14))
        text = tk.Label(top, text=entry["label"], bg=BG, fg=FG, font=(UI_FONT, 9))
        text.pack(side="right", padx=(0, 6))
        if entry["tip"]:
            w.Tip(text, entry["tip"] + " Applies at your next PLAY.")


def make_control_on(parent, entry, tab):
    """make_control for a parent on the page background (switches and number boxes take their parent's colour)."""
    control = make_control(parent, entry, tab)
    try:
        control.configure(bg=BG)
        for child in control.winfo_children():
            if isinstance(child, tk.Entry):
                child.configure(bg=BG, highlightbackground=BG, disabledbackground=BG)
            elif child.cget("text") in ("", "x", "%"):
                child.configure(bg=BG)
        if isinstance(control, w.Switch):
            control.draw()
    except tk.TclError:
        pass
    return control


# ---------------------------------------------------------------- the bar along the bottom
class ListDownloads:
    """Other people's addons and plugins (thirdparty.json) on the Addons and Plugins pages, where they belong, instead
    of the Get more page. An installed one gets its update button on its own row in the list; the ones not installed
    yet are listed under the installed ones with an Install button. Get more keeps the tools (Ashita, Ollama...).
    Which page an item goes to is read from the file the launcher looks for: addons/<name>/<name>.lua or plugins/<name>.dll."""

    TITLES = {"addon": "MORE ADDONS", "plugin": "MORE PLUGINS"}

    def __init__(self, app):
        self.app, self.newer = app, {}
        self.kinds = {lst.kind for lst in app.lists}
        self._seen, self._items = None, []

    @staticmethod
    def place(item):
        """("addon", "cadence"), ("plugin", "nameplate"), or None for anything else (it stays on Get more)."""
        parts = str(item.get("check") or "").replace("\\", "/").split("/")
        if item.get("into", "ashita") != "ashita":
            return None
        if len(parts) == 3 and parts[0] == "addons" and parts[2].lower().endswith(".lua"):
            return "addon", parts[1].lower()
        if len(parts) == 2 and parts[0] == "plugins" and parts[1].lower().endswith(".dll"):
            return "plugin", parts[1][:-4].lower()
        return None

    def moved(self, item):
        place = self.place(item)
        return place is not None and place[0] in self.kinds

    def items(self):
        """thirdparty.json's items, read again only when the file changed."""
        path = os.path.join(G.HERE, "thirdparty.json")
        try:
            seen = os.path.getmtime(path)
            if seen != self._seen:
                self._items, self._seen = G.tp.load_manifest(G.HERE), seen
        except Exception:
            self._items, self._seen = [], None
        return self._items

    def of_kind(self, kind):
        return [(item, self.place(item)[1]) for item in self.items() if self.moved(item) and self.place(item)[0] == kind]

    def status(self, item):
        try:
            return G.tp.status(item, G.HERE, self.app.ashita, G.tp.load_state(G.HERE), server=self.app.cfg.get("server_dir"))
        except Exception:
            return False, ""

    def controls(self, parent, item, installed, version, bg):
        """Newer version (when the last check found one), the install or update button, the item's own extra button, its home page."""
        app = self.app
        newest = self.newer.get(item["id"])
        if newest and newest != version:
            tk.Label(parent, text=f"newer: {newest}", bg=bg, fg=GOLD, font=(UI_FONT, 8, "bold")).pack(side="left", padx=(0, 8))
        if item["source"]["type"] == "page":
            label = "Open download page"
        else:
            label = "Update" if installed else "Install"
        w.button(parent, label, lambda: app.install_download(item), primary=not installed, small=True).pack(side="left")
        if item.get("patch") and installed:
            w.button(parent, "Apply era edits", lambda: app.apply_download_patch(item), small=True).pack(side="left", padx=(6, 0))
        w.link(parent, "home page", lambda: app.open_url(item["homepage"]), bg=bg).pack(side="left", padx=(10, 0))

    def on_row(self, lst, row, name):
        """Called by the list for each installed addon or plugin: its update button, when it is one of the downloads."""
        try:
            for item, key in self.of_kind(lst.kind):
                if key == name.lower():
                    side = tk.Frame(row, bg=PANEL)
                    side.grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 10))
                    self.controls(side, item, True, self.status(item)[1], PANEL)
                    return
        except Exception:
            log_problem("An update button could not be added to the list")

    def more_rows(self, lst, wanted, names):
        """Called by the list after its rows: the downloads of this kind that are not in the list yet."""
        try:
            have = {name.lower() for name in names}
            rest = [item for item, key in self.of_kind(lst.kind) if key not in have]
            if wanted:
                rest = [item for item in rest
                        if wanted in " ".join((item["name"], item.get("author", ""), item.get("note", ""))).lower()]
            if not self.of_kind(lst.kind) or (wanted and not rest):
                return
            head = tk.Frame(lst.inner, bg=BG)
            head.pack(fill="x", padx=8, pady=(16, 0))
            tk.Label(head, text=self.TITLES.get(lst.kind, "MORE"), bg=BG, fg=GOLD, font=(UI_FONT, 9, "bold")).pack(side="left")
            w.link(head, "Check for newer versions", self.app.check_download_updates).pack(side="right")
            tk.Label(lst.inner, bg=BG, fg=DIM, font=(UI_FONT, 9), justify="left", anchor="w", wraplength=900,
                     text=("Made by other people. Each one comes straight from its author's own release page; files it replaces "
                           "are saved in backups\\thirdparty first, and your settings are never overwritten."
                           if rest else "Everything the launcher can download for this page is installed.")
                     ).pack(fill="x", padx=8, pady=(2, 4))
            for item in rest:
                installed, version = self.status(item)
                row = tk.Frame(lst.inner, bg=PANEL)
                row.pack(fill="x", padx=8, pady=2)
                head = tk.Frame(row, bg=PANEL)
                head.grid(row=0, column=0, sticky="w", padx=(12, 0), pady=(5, 0))
                tk.Label(head, text=item["name"], bg=PANEL, fg=FG, font=(UI_FONT, 10, "bold")).pack(side="left")
                tk.Label(head, text=f"by {item['author']}  ·  license: {item['license']}", bg=PANEL, fg=DIM,
                         font=(UI_FONT, 9)).pack(side="left", padx=(8, 0))
                tk.Label(head, text=("installed " + version).strip() if installed else "not installed", bg=PANEL,
                         fg=G.GREEN if installed else DIM, font=(UI_FONT, 8, "bold")).pack(side="left", padx=(10, 0))
                if item.get("note"):
                    tk.Label(row, text=item["note"], bg=PANEL, fg=DIM, font=(UI_FONT, 9), wraplength=700, justify="left",
                             anchor="w").grid(row=1, column=0, sticky="w", padx=(12, 0), pady=(0, 5))
                side = tk.Frame(row, bg=PANEL)
                side.grid(row=0, column=1, rowspan=2, sticky="e", padx=(8, 10))
                self.controls(side, item, installed, version, PANEL)
                row.columnconfigure(0, weight=1)
        except Exception:
            log_problem("The downloads could not be listed on the Addons or Plugins page")


def add_list_downloads(app):
    """Addons and plugins from thirdparty.json move from Get more to the Addons and Plugins pages (see ListDownloads)."""
    if not getattr(app, "lists", None) or not hasattr(app, "dl_rows") or G.tp is None:
        return
    downloads = ListDownloads(app)
    older = app.show_downloads

    def show_downloads(newer=None):         # after an install, an update or a version check: Get more and both lists again
        if newer:
            downloads.newer = dict(newer)
        older(newer)
        for lst in app.lists:
            lst.reload()

    app.list_downloads, app.dl_filter, app.show_downloads = downloads, (lambda item: not downloads.moved(item)), show_downloads
    for lst in app.lists:
        lst.extra = downloads
        wheel_scrolls(app, lst, lst.inner.master)
    box = app.dl_rows.master.master         # the Get more page: its list, and the words above it
    wheel_scrolls(app, box, app.dl_rows.master)
    words = box.master.winfo_children()[0] if box.master.winfo_children() else None
    if isinstance(words, tk.Label):
        words.configure(text="Tools and extras made by other people; addons and plugins are on their own pages. Each one comes "
                             "straight from its author's own release page; files it replaces are saved in backups\\thirdparty "
                             "first, and your settings are never overwritten.")
    show_downloads()


def wheel_scrolls(app, area, canvas):
    """The mouse wheel scrolls this older list while the pointer is over it (it had a scroll bar only)."""
    def turn(event):
        try:
            if not area.winfo_ismapped():
                return
            x, y = area.winfo_pointerxy()
            left, top = area.winfo_rootx(), area.winfo_rooty()
            if not (left <= x < left + area.winfo_width() and top <= y < top + area.winfo_height()):
                return
            first, last = canvas.yview()
            if first <= 0.0 and last >= 1.0:        # everything is in view
                return
            step = -1 if (getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4) else 1
            canvas.yview_scroll(step * 2, "units")
        except tk.TclError:
            pass
    for wheel in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        app.bind_all(wheel, turn, add="+")


class NavButton:
    """A page button with the gold line under it. The launcher only ever calls set_active on these."""

    def __init__(self, button, line):
        self.button, self.line = button, line

    def set_active(self, on):
        self.button.set_active(on)
        self.line.configure(bg=GOLD if on else BG)


def build_nav(app):
    """HOME, WORLD, RULES, SQUADS, OPTIONS, CO-OP, SYSTEM, then EXIT. A button for several pages opens the one you were
    last on in it; a page in no group gets a MORE button, so nothing is ever unreachable."""
    app.page_index = {app.tabs.tab(tab_id, "text").strip(): index for index, tab_id in enumerate(app.tabs.tabs())}
    placed, groups = set(), []
    for image, title, names in NAV_BUTTONS:
        members = [(name, app.page_index[name]) for name in names if name in app.page_index]
        if members:
            groups.append((image, title, members))
            placed.update(name for name, _ in members)
    leftover = [(name, index) for name, index in app.page_index.items() if name not in placed]
    if leftover:
        groups.append(("more", "MORE", leftover))
    app.subnav = tk.Frame(app, bg=BG)
    app.nav_groups = []

    def place(image, title, command):
        holder = tk.Frame(app.nav, bg=BG)
        holder.pack(side="left", padx=2)
        button = app.ui_button(holder, image, command, title)
        button.pack()
        line = tk.Frame(holder, bg=BG, height=3)
        line.pack(fill="x", pady=(3, 0))
        return NavButton(button, line)

    for image, title, members in groups:
        group = {"title": title, "members": members, "last": members[0][1]}
        group["button"] = place(image, title, lambda g=group: app.select_tab(g["last"]))
        app.nav_groups.append(group)
    app.exit_btn = place("exit", "EXIT", app.on_close).button
    app.select_tab(0)


def show_subnav(app, group, index):
    """The pages of the open group as small buttons at the top of the page (nothing for a group of one page). The
    System group also lists the sections of its Settings page (Updates, GM and testing, Team...)."""
    for child in app.subnav.winfo_children():
        child.destroy()
    if group is not None and group["title"] == "SYSTEM":
        chips = system_chips(app)
        current = app.tabs.tab(index, "text").strip()
        now = ("section", app.system_sections.now) if current == "Settings" and app.system_sections is not None else ("page", index)
    elif group is not None:
        chips = [(SUBNAV_NAMES.get(name, name), "page", page) for name, page in group["members"]]
        now = ("page", index)
    if group is None or len(chips) < 2:
        app.subnav.pack_forget()
        return

    def pick(kind, which):
        if kind == "section":
            app.system_sections.show(which)
            app.select_tab(app.page_index["Settings"])
        else:
            app.select_tab(which)

    for name, kind, which in chips:
        on = (kind, which) == now
        holder = tk.Frame(app.subnav, bg=GOLD if on else BORDER)
        holder.pack(side="left", padx=(0, 6))
        label = tk.Label(holder, text=name.upper(), bg=PANEL2 if on else PANEL, fg=GOLD if on else DIM,
                         font=(UI_FONT, 9, "bold"), padx=16, pady=5, cursor="hand2")
        label.pack(padx=1, pady=1)
        label.bind("<Button-1>", lambda e, k=kind, x=which: pick(k, x))
    app.subnav.pack(fill="x", padx=24, pady=(12, 0), before=app.tabs)


SUBNAV_NAMES = {"Other": "Get more"}


def fit_window(app):
    width, height = WINDOW
    if G.linux is not None:     # the Steam Deck's screen is 1280 x 800: never taller (or wider) than the screen
        width = min(width, app.winfo_screenwidth())
        height = min(height, app.winfo_screenheight() - (0 if G.linux.in_game_mode() else 40))
    app.geometry(f"{width}x{height}")


# ---------------------------------------------------------------- the older pages in the same colours
def polish(widget):
    """One widget of an older page: dark text on a gold button (they were white on cyan), dark text on a gold
    list selection."""
    try:
        if isinstance(widget, tk.Button):
            if str(widget.cget("bg")).lower() == GOLD and str(widget.cget("fg")).lower() in ("white", "#ffffff", "#fff"):
                widget.configure(fg=BG, activebackground=GOLD_LIT, activeforeground=BG)
        elif isinstance(widget, tk.Listbox):
            if str(widget.cget("selectbackground")).lower() == GOLD:
                widget.configure(selectforeground=BG)
    except tk.TclError:
        pass


def polish_all(widget):
    polish(widget)
    for child in widget.winfo_children():
        polish_all(child)


def style_older_pages(app):
    """ttk pieces the older pages use: the Squad page's own tabs in the launcher's colours."""
    style = ttk.Style(app)
    style.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BORDER, lightcolor=BG, darkcolor=BG, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=PANEL, foreground=DIM, bordercolor=BORDER, lightcolor=PANEL, darkcolor=PANEL,
                    padding=(14, 6), font=(UI_FONT, 9, "bold"))
    style.map("TNotebook.Tab", background=[("selected", PANEL2), ("active", PANEL2)], foreground=[("selected", GOLD), ("active", FG)],
              lightcolor=[("selected", PANEL2)], darkcolor=[("selected", PANEL2)], bordercolor=[("selected", GOLD)])
    style.configure("Tabless.TNotebook", bordercolor=BG, lightcolor=BG, darkcolor=BG)       # no light frame round the page area
    polish_all(app)
    # anything made later (a dialog, a refreshed list) is looked at when it appears
    app.bind_all("<Map>", lambda event: polish(event.widget) if isinstance(event.widget, (tk.Button, tk.Listbox)) else None, add="+")


# ---------------------------------------------------------------- putting it together
def build(app, tabs):
    """Called when the launcher has made its own pages and before it makes the bar: adds World and Rules (and Era on
    the dev PC), the squad rules on the Squad page, and takes over the bar, the page names row and the window size."""
    made, model_note = [], getattr(app.rates_tab, "ai_model_note", None)
    try:                                # the pages every setting needs: without one of them, the classic look
        world = WorldPage(tabs, app)
        tabs.add(world, text="  World  ")
        made.append(world)
        rules = RulesPage(tabs, app)
        tabs.add(rules, text="  Rules  ")
        made.append(rules)
        add_squad_rules(app)
    except Exception:                   # leave nothing half made behind: the launcher shows its Rates page again
        for page in made:
            try:
                tabs.forget(page)
                page.destroy()
            except tk.TclError:
                pass
        if model_note is not None:
            app.rates_tab.ai_model_note = model_note
        raise
    app.world_page, app.rules_page = world, rules
    app.system_sections = None
    try:
        tabs.add(CharactersPage(tabs, app), text="  Characters  ")
        if not player_install(app):
            app.era_page = EraPage(tabs, app)
            tabs.add(app.era_page, text="  Era  ")
        tabs.add(AboutPage(tabs, app), text="  About  ")
        tabs.add(PatchNotesPage(tabs, app), text="  Patch notes  ")
        app.system_sections = SystemSections(app.updates_tab, "updates" if player_install(app) else "team")
    except Exception:                   # the Settings page stays whole, as in the classic look
        log_problem("The System pages could not be made")
    try:
        app.play_page = PlayPage(app)
    except Exception:                   # the classic Play layout stays (PlayPage puts it back); the other pages are fine
        app.play_page = None
        log_problem("The newer Play layout could not be made")
    try:
        add_list_downloads(app)
    except Exception:                   # they stay on the Get more page, as in the classic look
        app.dl_filter = None
        log_problem("The downloads could not be moved to the Addons and Plugins pages")
    try:
        style_older_pages(app)
    except Exception:
        log_problem("The older pages could not be restyled")
    app.build_nav = lambda: build_nav(app)
    app.show_subnav = lambda group, index: show_subnav(app, group, index)
    app.fit_window = lambda: fit_window(app)
