"""The look and the small controls of the launcher's newer pages (World, Rules, Play, System): one gold accent,
square corners, switches, minus / plus number boxes, choice buttons, cards. Plain Tk (frames and a canvas), so it
looks the same on Windows and Linux. Nothing here reads or writes settings: every control shows a Tk variable."""
import math
import tkinter as tk
from tkinter import ttk

import launcher_core as core

UI_FONT, MONO_FONT = core.ui_fonts()
BG, PANEL, PANEL2, FG, DIM = "#0a1118", "#101c28", "#162634", "#e9f1f5", "#8aa0ad"
BORDER, LINE, OFF = "#1d3445", "#2a4358", "#5c7488"
GOLD, GOLD_LIT, GOLD_DIM, PARCH = "#e6be64", "#f3d58c", "#6b5a2e", "#efe6d0"
HEAD_FONT = ("Georgia", 20, "bold")      # page titles; head_font() swaps in the nearest serif this PC has


def is_on(value):
    """A switch value: a real True / False, or the 1 / 0 text the server settings use."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "0.0", "false", "off", "no")
    return bool(value)


def number_text(value, integer=False):
    """12.0 -> '12', 0.125 -> '0.125', 2.50 -> '2.5'."""
    if integer:
        return str(int(round(value)))
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def parse_number(text):
    try:
        return float(str(text).strip().replace(",", ".").replace("%", "").replace("x", "").replace("×", ""))
    except ValueError:
        return None


def step_value(current, step, direction, lo, hi):
    """The next value on the step grid above (direction 1) or below (-1) current, kept inside lo..hi. Where lo is
    below zero (a special value such as -1 = always), one step down from 0 lands on it and one step up leaves it for 0."""
    grid = current / step
    if direction > 0:
        nxt = 0.0 if current < 0 else (math.floor(grid + 1e-6) + 1) * step
    else:
        nxt = (math.ceil(grid - 1e-6) - 1) * step
        if nxt < 0:
            nxt = lo
    return max(lo, min(hi, round(nxt, 6)))


class Tip:
    """A small text box under a widget while the pointer is on it. text is a string or a function giving one."""

    def __init__(self, widget, text):
        self.widget, self.text, self.box = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Button-1>", self.hide, add="+")

    def show(self, _event=None):
        text = self.text() if callable(self.text) else self.text
        if not text or self.box is not None:
            return
        self.box = tk.Toplevel(self.widget)
        self.box.wm_overrideredirect(True)
        x, y = self.widget.winfo_rootx() + 12, self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.box.wm_geometry(f"+{x}+{y}")
        tk.Label(self.box, text=text, bg=PANEL2, fg=FG, relief="solid", bd=1, justify="left", wraplength=380,
                 padx=8, pady=5, font=(UI_FONT, 9)).pack()

    def hide(self, _event=None):
        if self.box is not None:
            self.box.destroy()
            self.box = None


class Switch(tk.Canvas):
    """An on / off switch for a Tk variable (BooleanVar, or a StringVar holding 1 / 0). command runs after a click."""
    W, H = 38, 20

    def __init__(self, parent, variable, command=None, bg=PANEL):
        super().__init__(parent, width=self.W, height=self.H, bg=bg, highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self.variable, self.command, self.enabled = variable, command, True
        self.textual = isinstance(variable, tk.StringVar)
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        self._trace = variable.trace_add("write", lambda *a: self.draw())
        self.bind("<Destroy>", self._forget, add="+")
        self.draw()

    def _forget(self, _event=None):
        try:
            self.variable.trace_remove("write", self._trace)
        except (tk.TclError, ValueError):
            pass

    def on(self):
        try:
            return is_on(self.variable.get())
        except tk.TclError:
            return False

    def toggle(self, _event=None):
        if not self.enabled:
            return
        new = not self.on()
        self.variable.set(("1" if new else "0") if self.textual else new)
        if self.command:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if self.enabled else "arrow")
        self.draw()

    def draw(self):
        try:
            self.delete("all")
        except tk.TclError:
            return
        on = self.on()
        edge = (GOLD if on else OFF) if self.enabled else LINE
        fill = (GOLD if on else self.cget("bg")) if self.enabled else PANEL2
        self.create_rectangle(0, 0, self.W - 1, self.H - 1, outline=edge, fill=fill)
        x = self.W - 17 if on else 3
        knob = (BG if on else DIM) if self.enabled else OFF
        self.create_rectangle(x, 3, x + 13, self.H - 4, outline=knob, fill=knob)
        if self.focus_displayof() is self:
            self.create_rectangle(1, 1, self.W - 2, self.H - 2, outline=GOLD_LIT if on else FG, dash=(2, 2))


class Stepper(tk.Frame):
    """A number with minus and plus beside it. The number can also be typed. variable holds the stored value as text;
    scale turns it into what is shown (100 shows 0.15 as 15). The mouse wheel does nothing here on purpose."""

    def __init__(self, parent, variable, lo, hi, step=1.0, integer=False, scale=1.0, unit="", width=5, bg=PANEL, command=None,
                 special=None):
        super().__init__(parent, bg=bg)
        self.variable, self.lo, self.hi, self.step, self.integer, self.scale = variable, lo, hi, step, integer, scale
        self.command, self.special = command, dict(special or {})      # special: stored value -> the word shown for it
        self.shown = tk.StringVar()
        self.minus = self._button("−", -1)
        self.minus.pack(side="left")
        self.entry = tk.Entry(self, textvariable=self.shown, width=width, justify="center", bg=bg, fg=FG, insertbackground=FG,
                              relief="flat", bd=0, highlightthickness=1, highlightbackground=bg, highlightcolor=GOLD,
                              font=(UI_FONT, 10, "bold"), disabledbackground=bg, disabledforeground=DIM)
        self.entry.pack(side="left", padx=2, ipady=2)
        self.plus = self._button("+", 1)
        self.plus.pack(side="left")
        tk.Label(self, text=unit, width=1, anchor="w", bg=bg, fg=DIM, font=(UI_FONT, 10)).pack(side="left", padx=(3, 0))
        self.entry.bind("<Return>", self.typed)
        self.entry.bind("<FocusOut>", self.typed)
        self._trace = variable.trace_add("write", lambda *a: self.show())
        self.bind("<Destroy>", self._forget, add="+")
        self.show()

    def _forget(self, event=None):
        if event is not None and event.widget is not self:
            return
        try:
            self.variable.trace_remove("write", self._trace)
        except (tk.TclError, ValueError):
            pass

    def _button(self, text, direction):
        b = tk.Label(self, text=text, width=1, bg=PANEL2, fg=FG, font=(UI_FONT, 10), cursor="hand2", padx=5, pady=1,
                     highlightthickness=1, highlightbackground=LINE)
        b.bind("<Button-1>", lambda e, d=direction: self.nudge(d))
        b.bind("<Enter>", lambda e: b.configure(bg=LINE))
        b.bind("<Leave>", lambda e: b.configure(bg=PANEL2))
        return b

    def stored(self):
        try:
            value = parse_number(self.variable.get())
        except tk.TclError:
            value = None
        return self.lo if value is None else value

    def show(self):
        if self.focus_displayof() is self.entry:
            return
        try:
            value = self.stored()
            word = next((text for number, text in self.special.items() if abs(number - value) < 1e-6), None)
            self.shown.set(word or number_text(round(value * self.scale, 3), self.integer))
        except tk.TclError:
            pass

    def store(self, value):
        value = max(self.lo, min(self.hi, value))
        self.variable.set(number_text(value, self.integer))
        self.show()
        if self.command:
            self.command()

    def nudge(self, direction):
        self.winfo_toplevel().focus_set()
        self.store(step_value(self.stored(), self.step, direction, self.lo, self.hi))

    def typed(self, event=None):
        text = self.shown.get().strip().lower()
        value = next((number * self.scale for number, word in self.special.items() if word == text), None)
        if value is None:
            value = parse_number(text)
        if event is not None and getattr(event, "keysym", "") == "Return":
            self.winfo_toplevel().focus_set()
        if value is not None:
            value = value / self.scale
            self.store(round(value) if self.integer else round(value, 3))
        self.after_idle(self.show)


class Choice(tk.Frame):
    """A row of buttons where one is chosen. options: (stored value, shown text) pairs. variable: a StringVar."""

    def __init__(self, parent, variable, options, command=None, bg=PANEL):
        super().__init__(parent, bg=bg)
        self.variable, self.command, self.buttons = variable, command, []
        for value, text in options:
            b = tk.Label(self, text=text, font=(UI_FONT, 9), padx=10, pady=4, cursor="hand2", highlightthickness=1)
            b.pack(side="left", padx=(0, 4))
            b.bind("<Button-1>", lambda e, v=value: self.pick(v))
            self.buttons.append((value, b))
        self._trace = variable.trace_add("write", lambda *a: self.draw())
        self.bind("<Destroy>", self._forget, add="+")
        self.draw()

    def _forget(self, event=None):
        if event is not None and event.widget is not self:
            return
        try:
            self.variable.trace_remove("write", self._trace)
        except (tk.TclError, ValueError):
            pass

    def pick(self, value):
        self.variable.set(value)
        if self.command:
            self.command()

    def draw(self):
        try:
            now = self.variable.get()
        except tk.TclError:
            return
        for value, b in self.buttons:
            on = value == now
            try:
                b.configure(bg=GOLD if on else PANEL, fg=BG if on else FG, highlightbackground=GOLD if on else LINE,
                            font=(UI_FONT, 9, "bold") if on else (UI_FONT, 9))
            except tk.TclError:
                pass


class Card(tk.Frame):
    """A titled box. Rows go into .body. master: a Tk variable for a switch beside the title (the whole feature on / off)."""

    def __init__(self, parent, title, master=None, command=None):
        super().__init__(parent, bg=BORDER)
        inner = tk.Frame(self, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(inner, bg=PANEL)
        head.pack(fill="x", padx=14, pady=(9, 2))
        tk.Label(head, text=title.upper(), bg=PANEL, fg=GOLD, font=(UI_FONT, 9, "bold")).pack(side="left")
        self.switch = None
        if master is not None:
            self.switch = Switch(head, master, command=command)
            self.switch.pack(side="right")
        self.body = tk.Frame(inner, bg=PANEL)
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    def row(self, label, control=None, tip=None):
        """One line: the label on the left, the control (made by control(parent)) on the right. Returns the control."""
        line = tk.Frame(self.body, bg=PANEL)
        line.pack(fill="x", pady=2)
        made = None
        if control is not None:         # packed first, so a long label is the thing that gets cut short, never the control
            made = control(line)
            made.pack(side="right")
        text = tk.Label(line, text=label, bg=PANEL, fg=FG, font=(UI_FONT, 10), anchor="w")
        text.pack(side="left")
        if tip:
            Tip(text, tip)
        return made

    def note(self, text, color=DIM, wrap=300):
        label = tk.Label(self.body, text=text, bg=PANEL, fg=color, font=(UI_FONT, 9), anchor="w", justify="left", wraplength=wrap)
        label.pack(fill="x", pady=(0, 2))
        return label


class ChoiceCard(tk.Frame):
    """A box to click: a name, a few words about it, and SELECTED when it is the one in use."""

    def __init__(self, parent, title, text, command, wrap=290):
        super().__init__(parent, bg=BORDER, cursor="hand2")
        self.inner = tk.Frame(self, bg=PANEL)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(self.inner, bg=PANEL)
        head.pack(fill="x", padx=14, pady=(10, 2))
        self.title = tk.Label(head, text=title, bg=PANEL, fg=FG, font=(UI_FONT, 11, "bold"), anchor="w")
        self.title.pack(side="left")
        self.mark = tk.Label(head, text="", bg=PANEL, fg=GOLD, font=(UI_FONT, 8, "bold"))
        self.mark.pack(side="right")
        self.text = tk.Label(self.inner, text=text, bg=PANEL, fg=DIM, font=(UI_FONT, 9), anchor="nw", justify="left", wraplength=wrap)
        self.text.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.parts = (self.inner, head, self.title, self.mark, self.text)
        for widget in (self,) + self.parts:
            widget.bind("<Button-1>", lambda e: command())
            widget.configure(cursor="hand2")
        self.selected = None
        self.set_selected(False)

    def set_selected(self, selected):
        if selected == self.selected:
            return
        self.selected = selected
        self.configure(bg=GOLD if selected else BORDER)
        for widget in self.parts:
            widget.configure(bg=PANEL2 if selected else PANEL)
        self.mark.configure(text="SELECTED" if selected else "")


def button(parent, text, command, primary=False, small=False):
    """A flat text button. primary: the one gold button of a group."""
    return tk.Button(parent, text=text, command=command, relief="flat", bd=0, cursor="hand2",
                     bg=GOLD if primary else PANEL2, fg=BG if primary else FG,
                     activebackground=GOLD_LIT if primary else LINE, activeforeground=BG if primary else FG,
                     font=(UI_FONT, 9 if small else 10, "bold" if primary else "normal"), padx=10 if small else 14, pady=3 if small else 5)


def link(parent, text, command, bg=BG, size=9):
    """Underlined gold text that runs command when clicked."""
    label = tk.Label(parent, text=text, bg=bg, fg=GOLD, cursor="hand2", font=(UI_FONT, size, "underline"))
    label.bind("<Button-1>", lambda e: command())
    return label


def chip(parent, text, bg=BG):
    """A small framed note, such as 'Applies at your next PLAY'."""
    frame = tk.Frame(parent, bg=GOLD_DIM)
    tk.Label(frame, text=text, bg=bg, fg=GOLD, font=(UI_FONT, 8), padx=8, pady=3).pack(padx=1, pady=1)
    return frame


_HEAD = None


def head_font(widget, size=20):
    """The serif for page titles: the first of these this PC has (Windows has Georgia; Linux usually DejaVu Serif)."""
    global _HEAD
    if _HEAD is None:
        try:
            from tkinter import font as tkfont
            have = set(tkfont.families(widget))
        except tk.TclError:
            have = set()
        _HEAD = next((name for name in ("Caladea", "Georgia", "Cambria", "DejaVu Serif", "Noto Serif", "Liberation Serif")
                      if name in have), HEAD_FONT[0])
    return (_HEAD, size, "bold")


def page_header(parent, title, subtitle, note="Applies at your next PLAY"):
    """The top line of a page: its name, a few words about it, and a note on the right."""
    head = tk.Frame(parent, bg=BG)
    tk.Label(head, text=title, bg=BG, fg=PARCH, font=head_font(parent)).pack(side="left", anchor="s")
    if subtitle:
        tk.Label(head, text=subtitle, bg=BG, fg=DIM, font=(UI_FONT, 10)).pack(side="left", anchor="s", padx=(14, 0), pady=(0, 5))
    if note:
        chip(head, note).pack(side="right", anchor="s", pady=(0, 4))
    return head


class ScrollPage(tk.Frame):
    """A page whose content (.body) scrolls only when it is taller than the window; the bar hides itself otherwise."""

    def __init__(self, parent, pad=(24, 16)):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._set_bar)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((pad[0], pad[1]), window=self.body, anchor="nw")
        self.pad, self.bar_shown = pad, False
        self.body.bind("<Configure>", self._sized)
        self.canvas.bind("<Configure>", self._sized)
        # the wheel scrolls the page from anywhere on it, when there is something to scroll; it never changes a setting
        for wheel in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(wheel, self._wheel, add="+")

    def _sized(self, _event=None):
        width = max(200, self.canvas.winfo_width() - 2 * self.pad[0])
        self.canvas.itemconfigure(self.window, width=width)
        self.canvas.configure(scrollregion=(0, 0, width + 2 * self.pad[0], self.body.winfo_reqheight() + 2 * self.pad[1]))

    def _set_bar(self, first, last):
        needed = float(first) > 0.0 or float(last) < 1.0
        if needed != self.bar_shown:
            self.bar_shown = needed
            if needed:
                self.bar.pack(side="right", fill="y")
            else:
                self.bar.pack_forget()
        self.bar.set(first, last)

    def _wheel(self, event):
        try:
            if not self.bar_shown or not self.winfo_ismapped():
                return
            x, y = self.winfo_pointerxy()
            left, top = self.winfo_rootx(), self.winfo_rooty()
            if not (left <= x < left + self.winfo_width() and top <= y < top + self.winfo_height()):
                return
            step = -1 if (getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4) else 1
            self.canvas.yview_scroll(step * 2, "units")
        except tk.TclError:
            pass                        # the page is gone


class _WaveLoader(tk.Canvas):
    """Fallback (no Pillow or no assets/ui/loader_crystals.png): a row of small diamonds that light up in a slow golden wave,
    with a brighter glint running through it. Same start(ms) / stop() as the ttk progress bar it replaces."""

    def __init__(self, parent, bg=BG, height=22, count=15, **kw):
        super().__init__(parent, bg=bg, height=height, highlightthickness=0, bd=0, **kw)
        self.count, self.phase, self.job, self.items = count, 0.0, None, []
        self.bind("<Configure>", lambda e: self._layout())

    @staticmethod
    def _mix(a, b, t):
        a, b = a.lstrip("#"), b.lstrip("#")
        rgb = [int(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t) for i in (0, 2, 4)]
        return "#%02x%02x%02x" % tuple(rgb)

    def _layout(self):
        self.delete("all")
        width, height = max(self.winfo_width(), 60), int(self.cget("height"))
        step = width / self.count
        r = min(step * 0.32, height * 0.42)
        mid = height / 2
        self.items = []
        for i in range(self.count):
            x = step * (i + 0.5)
            shape = self.create_polygon(x, mid - r, x + r * 0.62, mid, x, mid + r, x - r * 0.62, mid,
                                        fill=GOLD_DIM, outline=BORDER, width=1)
            shine = self.create_line(x - r * 0.25, mid - r * 0.35, x, mid - r * 0.75, fill=BG, width=1)
            self.items.append((shape, shine))
        self._paint()

    def _paint(self):
        import math
        for i, (shape, shine) in enumerate(self.items):
            wave = (math.sin(self.phase - i * 0.55) + 1) / 2            # 0..1, a slow wave down the row
            glint = max(0.0, math.cos(self.phase * 0.5 - i * 0.42)) ** 12  # a narrow bright run now and then
            fill = self._mix(GOLD_DIM, GOLD, wave)
            if glint > 0.05:
                fill = self._mix(fill, PARCH, min(1.0, glint))
            self.itemconfigure(shape, fill=fill, outline=self._mix(BORDER, GOLD_LIT, wave * 0.7))
            self.itemconfigure(shine, fill=self._mix(fill, PARCH, 0.6 + 0.4 * glint))

    def _tick(self, ms):
        self.phase += 0.18
        if getattr(self, "ready", False):
            for shape, shine in self.items:
                self.itemconfigure(shape, fill="#46dc6e", outline="#9ff0b4")
                self.itemconfigure(shine, fill="#d8ffe4")
        else:
            self._paint()
        self.job = self.after(ms, self._tick, ms)

    def success(self):
        self.ready = True

    def start(self, ms=40):
        if self.job is None:
            if not self.items:
                self._layout()
            self._tick(max(30, int(ms) * 3))

    def stop(self):
        if self.job is not None:
            self.after_cancel(self.job)
            self.job = None
        self.phase = 0.0
        self.ready = False
        if self.items:
            for shape, shine in self.items:
                self.itemconfigure(shape, fill=GOLD_DIM, outline=BORDER)
                self.itemconfigure(shine, fill=BG)


class CrystalLoader(tk.Canvas):
    """The loading animation while the world starts: the eight elemental crystals (fire, ice, wind, earth, lightning,
    water, light, dark) glow up one after another in a slow wave, bob a little, and now and then catch a glint.
    The crystals are drawn ahead of time (dev/launcher-tests/make_loader_crystals.py -> assets/ui/loader_crystals.png:
    8 rows, 10 glow levels, then the same 10 with a glint), so this only swaps pictures. start(ms) / stop() as before;
    without Pillow or the picture it falls back to the plain diamond wave."""

    CELL = (32, 50)
    LEVELS = 10

    def __new__(cls, parent, bg=BG, **kw):
        frames = cls._load_frames(parent)
        if frames is None:
            return _WaveLoader(parent, bg=bg, **{k: v for k, v in kw.items() if k in ("width", "height", "count")})
        self = super().__new__(cls)
        self._frames = frames
        return self

    @classmethod
    def _load_frames(cls, parent):
        try:
            import os
            from PIL import Image, ImageTk
            here = os.path.dirname(os.path.abspath(__file__))
            sheet = Image.open(os.path.join(here, "assets", "ui", "loader_crystals.png")).convert("RGB")
            cw, ch = cls.CELL
            rows = sheet.height // ch
            frames = []
            for r in range(rows):
                row = []
                for c in range(cls.LEVELS * 2):
                    row.append(ImageTk.PhotoImage(sheet.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)), master=parent))
                frames.append(row)
            return frames
        except Exception:
            return None

    def __init__(self, parent, bg=BG, width=380, height=None, **_kw):
        cw, ch = self.CELL
        super().__init__(parent, bg=bg, width=width, height=height or ch + 4, highlightthickness=0, bd=0)
        self.phase, self.job, self.items = 0.0, None, []
        # the sheet's 9th row is green: success() turns the crystals green one by one once the game has started
        self.count = min(8, len(self._frames))
        self.green = self._frames[8] if len(self._frames) > 8 else None
        self.ready_at = None
        self.bind("<Configure>", lambda e: self._layout())

    def _layout(self):
        self.delete("all")
        count = self.count
        width = max(self.winfo_width(), int(self.cget("width")))
        step = width / count
        self.items = [self.create_image(step * (i + 0.5), int(self.cget("height")) / 2, image=self._frames[i][0]) for i in range(count)]
        self.base_y = int(self.cget("height")) / 2
        self._paint()

    def _paint(self):
        import math
        for i, item in enumerate(self.items):
            if self.ready_at is not None and self.green is not None:
                since = self.phase - self.ready_at - i * 0.55        # each crystal turns a moment after the one before it
                if since >= 0:
                    pulse = (math.sin(self.phase * 0.6 - i * 0.5) + 1) / 2
                    level = 6 + int(round(pulse * (self.LEVELS - 7)))    # a calm bright green, gently breathing
                    flash = since < 0.6                                   # the glint as it turns
                    self.itemconfigure(item, image=self.green[level + (self.LEVELS if flash else 0)])
                    self.coords(item, self.coords(item)[0], self.base_y)
                    continue
            wave = (math.sin(self.phase - i * 0.7) + 1) / 2
            glint = max(0.0, math.cos(self.phase * 0.5 - i * 0.6)) ** 14
            level = min(self.LEVELS - 1, int(round(wave * (self.LEVELS - 1))))
            frame = self._frames[i][level + (self.LEVELS if glint > 0.45 else 0)]
            self.itemconfigure(item, image=frame)
            x = self.coords(item)[0]
            self.coords(item, x, self.base_y - round(math.sin(self.phase - i * 0.7) * 2) if self.job else self.base_y)

    def _tick(self, ms):
        self.phase += 0.16
        self._paint()
        self.job = self.after(ms, self._tick, ms)

    def success(self):
        """The game has started: the crystals turn green, left to right, and stay green until stop()."""
        if self.ready_at is None:
            if self.job is None:
                self.start()
            self.ready_at = self.phase

    def start(self, ms=40):
        if self.job is None:
            self.ready_at = None
            if not self.items:
                self._layout()
            self.job = True
            self._tick(max(40, int(ms) * 4))

    def stop(self):
        if self.job is not None and self.job is not True:
            self.after_cancel(self.job)
        self.job = None
        self.phase = 0.0
        self.ready_at = None
        if self.items:
            for i, item in enumerate(self.items):
                self.itemconfigure(item, image=self._frames[i][0])
                self.coords(item, self.coords(item)[0], self.base_y)
