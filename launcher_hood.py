"""(Sunie, 2026-11-22) "Peek under the AI hood": a window that shows, live, every prompt the AI helpers send to the
model and what comes back.

It is for one tester, so it is switched on by a file: ai-hood.on in the kit folder, which the small zip we send her
adds. Without that file the launcher shows nothing of this and the helpers write nothing.

The helpers (squad-chat/squad_chat.py, crowds/crowd_chat_ai.py, crowds/bots/bots_chat_ai.py) append to
logs/ai-hood.log while the switch file is there (their hood() function); this module only reads that file.
"""
import os

SWITCH = "ai-hood.on"
LOG = os.path.join("logs", "ai-hood.log")
KEEP_LINES = 6000            # the window forgets its oldest lines past this (the file keeps them)


def is_on(kit):
    return os.path.exists(os.path.join(kit, SWITCH))


def log_path(kit):
    return os.path.join(kit, LOG)


def read_new(path, offset, most=400_000):
    """(text, new offset): what was added to the log since offset. A log that got shorter (cleared, or rolled over
    to ai-hood.log.1) is read from its start again. A first look at a long log gives its last part only."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return "", 0
    if size < offset:
        offset = 0
    if size == offset:
        return "", offset
    start = max(offset, size - most)
    with open(path, "rb") as handle:
        handle.seek(start)
        data = handle.read(size - start)
    text = data.decode("utf-8", errors="replace")
    if start > offset:                                   # cut in the middle of a line: begin at the next one
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text, size


def line_kind(line):
    """How a line of the log is shown: 'head' (a new prompt), 'role' (system / user / assistant / reply) or ''."""
    if line.startswith("===== ") and line.rstrip().endswith("====="):
        return "head"
    if line.startswith("--- ") and line.rstrip().endswith(" ---"):
        return "role"
    return ""


def places(kit):
    """The files worth opening for someone who wants to tinker, the ones that exist."""
    found = []
    for label, parts in (("Squad chat: settings (model, how often they talk)", ("squad-chat", "config.json")),
                         ("Squad chat: each mate's sheet", ("squad-chat", "mates")),
                         ("Squad chat: the world knowledge they share", ("squad-chat", "lore", "ffxi_era.md")),
                         ("Squad chat: how it works", ("squad-chat", "README.md")),
                         ("Town crowd lines: the prompts", ("crowds", "crowd_chat_ai.py")),
                         ("Bot players: the prompts", ("crowds", "bots", "bots_chat_ai.py"))):
        path = os.path.join(kit, *parts)
        if os.path.exists(path):
            found.append((label, path))
    return found


def clear(kit):
    """Empties the log (the window then starts again from nothing)."""
    try:
        with open(log_path(kit), "w", encoding="utf-8"):
            pass
        return True
    except OSError:
        return False


# ----- the launcher's side (tkinter is only loaded here) -----
def build_box(parent, app, kit, theme):
    """The box on SYSTEM > Settings. Only called when is_on(kit)."""
    import tkinter as tk
    t = theme
    box = tk.Frame(parent, bg=t["panel"], highlightbackground=t["border"], highlightthickness=1)
    box.pack(fill="x", padx=14, pady=(0, 6))
    tk.Label(box, text="AI hood", bg=t["panel"], fg=t["fg"], font=(t["font"], 12, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
    tk.Label(box, text="Every prompt the AI helpers send to the model, and each reply, as it happens. Only this install has "
                       "it: the file ai-hood.on in the game's folder switches it on (delete the file to switch it off).",
             bg=t["panel"], fg=t["dim"], wraplength=880, justify="left", font=(t["font"], 9)).pack(anchor="w", padx=12, pady=(2, 4))
    bar = tk.Frame(box, bg=t["panel"])
    bar.pack(anchor="w", padx=12, pady=(0, 12))
    state = {"window": None}

    def show():
        window = state["window"]
        try:
            if window is not None and window.winfo_exists():
                window.lift()
                return
        except Exception:
            pass
        state["window"] = Window(parent.winfo_toplevel(), app, kit, theme)

    for text, command in (("Open the AI hood", show),
                          ("Open the AI files", lambda: app.open_dir(os.path.join(kit, "squad-chat")))):
        tk.Button(bar, text=text, command=command, bg=t["panel2"], fg=t["fg"], relief="flat", padx=12, pady=5,
                  activebackground=t["border"], activeforeground=t["fg"]).pack(side="left", padx=(0, 8))
    return box


def Window(master, app, kit, theme):
    """The live view: logs/ai-hood.log as it grows."""
    import tkinter as tk
    from tkinter import ttk
    t = theme
    win = tk.Toplevel(master)
    win.title("XI: Forever Offline - AI hood")
    win.geometry("980x680")
    win.configure(bg=t["bg"])
    tk.Label(win, text="AI hood", bg=t["bg"], fg=t["gold"], font=("Georgia", 16, "bold")).pack(anchor="w", padx=14, pady=(10, 0))
    tk.Label(win, text="Talk to a squad mate or a bot player, or wait for the town crowd to get new lines: each prompt shows up "
                       "here as it is sent, with the model's reply under it. The same text is kept in logs/ai-hood.log.",
             bg=t["bg"], fg=t["dim"], wraplength=940, justify="left", font=(t["font"], 9)).pack(anchor="w", padx=14, pady=(2, 6))
    bar = tk.Frame(win, bg=t["bg"])
    bar.pack(fill="x", padx=14, pady=(0, 6))
    frame = tk.Frame(win, bg=t["bg"])
    frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
    box = tk.Text(frame, bg=t["panel"], fg=t["fg"], font=(t["mono"], 10), relief="flat", wrap="word", bd=0,
                  highlightthickness=0, state="disabled")
    scroll = ttk.Scrollbar(frame, command=box.yview)
    box.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    box.pack(side="left", fill="both", expand=True)
    box.tag_configure("head", foreground=t["gold"], font=(t["mono"], 10, "bold"))
    box.tag_configure("role", foreground=t["dim"], font=(t["mono"], 10, "bold"))
    state = {"offset": 0, "paused": False, "lines": 0}
    path = log_path(kit)

    def add(text):
        box.configure(state="normal")
        for line in text.splitlines():
            kind = line_kind(line)
            box.insert("end", line + "\n", (kind,) if kind else ())
            state["lines"] += 1
        if state["lines"] > KEEP_LINES:
            extra = state["lines"] - KEEP_LINES
            box.delete("1.0", f"{extra + 1}.0")
            state["lines"] = KEEP_LINES
        box.configure(state="disabled")
        box.see("end")

    def tick():
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        if not state["paused"]:
            try:
                text, state["offset"] = read_new(path, state["offset"])
                if text:
                    add(text)
            except Exception:
                pass
        win.after(700, tick)

    def pause():
        state["paused"] = not state["paused"]
        pause_btn.configure(text="Go on" if state["paused"] else "Pause")

    def wipe():
        clear(kit)
        state["offset"], state["lines"] = 0, 0
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.configure(state="disabled")

    def button(text, command):
        b = tk.Button(bar, text=text, command=command, bg=t["panel2"], fg=t["fg"], relief="flat", padx=12, pady=4,
                      activebackground=t["border"], activeforeground=t["fg"])
        b.pack(side="left", padx=(0, 8))
        return b

    pause_btn = button("Pause", pause)
    button("Clear", wipe)
    button("Open the AI files", lambda: app.open_dir(os.path.join(kit, "squad-chat")))
    button("Open the log's folder", lambda: app.open_dir(os.path.join(kit, "logs")))
    if not os.path.exists(path):
        add("Nothing yet. Start the game with AI chat on, then say something to a squad mate in party chat.")
        state["lines"] = 0
    tick()
    return win
