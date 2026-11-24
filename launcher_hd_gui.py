"""The "HD texture packs" window (OPTIONS > Get more, on XIPivot's row). What it does is in launcher_hd.py:
the player downloads a pack from Nexus Mods himself, this window puts it where XIPivot loads it from and switches it on.

Opened with open_window(...) from launcher_gui.pyw. Everything slow (unpacking 7 GB) runs on its own thread; the
window only ever changes from its own `after` calls.
"""
import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

import launcher_hd as hd

_OPEN = {"win": None}


def gb(size):
    if size is None:
        return "?"
    return f"{size / (1 << 30):.1f} GB" if size >= (1 << 30) // 10 else f"{size / (1 << 20):.0f} MB"


def open_window(parent, kit, ashita, boot_ini, look, say=None, running=None, core=None):
    """look: the launcher's colours and font {bg, panel, fg, dim, accent, green, red, gold, font}. say: the launcher's
    own log line. running(): True while the game runs. core: launcher_core (to switch XIPivot on in the boot file)."""
    if _OPEN["win"] is not None:
        try:
            _OPEN["win"].lift()
            _OPEN["win"].focus_force()
            return _OPEN["win"]
        except tk.TclError:
            _OPEN["win"] = None
    BG, PANEL, FG, DIM = look["bg"], look["panel"], look["fg"], look["dim"]
    ACCENT, GREEN, RED, GOLD, FONT = look["accent"], look["green"], look["red"], look["gold"], look["font"]
    say = say or (lambda text: None)
    running = running or (lambda: False)

    win = tk.Toplevel(parent)
    _OPEN["win"] = win
    win.title("HD texture packs and music")
    win.configure(bg=BG)
    win.geometry("760x720")
    win.minsize(640, 520)
    lines = queue.Queue()
    state = {"busy": False, "closed": False, "free_at_start": None, "last_tick": 0.0}

    def close():
        state["closed"] = True
        _OPEN["win"] = None
        win.destroy()
    win.protocol("WM_DELETE_WINDOW", close)

    def label(master, text, **kw):
        kw.setdefault("bg", BG)
        kw.setdefault("fg", FG)
        kw.setdefault("justify", "left")
        kw.setdefault("anchor", "w")
        return tk.Label(master, text=text, **kw)

    def button(master, text, command, strong=False, **kw):
        return tk.Button(master, text=text, command=command, relief="flat", padx=10, bg=ACCENT if strong else PANEL,
                         fg="white" if strong else FG, activebackground=PANEL, activeforeground=FG, **kw)

    label(win, "HD texture packs and music", font=(FONT, 14, "bold")).pack(fill="x", padx=14, pady=(12, 0))
    label(win, "Experimental. Sharper textures made by players, loaded through XIPivot: your FINAL FANTASY XI folder is not "
               "changed, and a pack comes out again with one click. You download the pack from Nexus Mods (a free account "
               "there is enough); this window does the rest.", fg=DIM, wraplength=720, font=(FONT, 9)).pack(fill="x", padx=14, pady=(2, 8))

    # ---------------------------------------------------------------- 1. get a pack
    label(win, "1.  Get a pack", fg=GOLD, font=(FONT, 11, "bold")).pack(fill="x", padx=14)
    for pack in hd.KNOWN:
        row = tk.Frame(win, bg=PANEL)
        row.pack(fill="x", padx=14, pady=2)
        text = tk.Frame(row, bg=PANEL)
        text.pack(side="left", fill="x", expand=True, padx=8, pady=5)
        label(text, pack["name"], bg=PANEL, font=(FONT, 10, "bold")).pack(fill="x")
        label(text, "by " + pack["by"] + ".  " + pack["note"], bg=PANEL, fg=DIM, font=(FONT, 9), wraplength=520).pack(fill="x")
        button(row, "Open its page", lambda url=pack["url"]: webbrowser.open(url), strong=True).pack(side="right", padx=8)
    have = {p["name"].lower() for p in hd.installed(ashita)} if ashita else set()
    for pack in hd.DIRECT:
        row = tk.Frame(win, bg=PANEL)
        row.pack(fill="x", padx=14, pady=2)
        text = tk.Frame(row, bg=PANEL)
        text.pack(side="left", fill="x", expand=True, padx=8, pady=5)
        label(text, pack["name"], bg=PANEL, font=(FONT, 10, "bold")).pack(fill="x")
        label(text, "by " + pack["by"] + ".  " + pack["note"], bg=PANEL, fg=DIM, font=(FONT, 9), wraplength=520).pack(fill="x")
        if pack["folder"].lower() in have:
            label(row, "installed (see 3.)", bg=PANEL, fg=GREEN, font=(FONT, 9, "bold")).pack(side="right", padx=8)
        else:
            button(row, "Download", lambda p=pack: fetch_direct(p), strong=True).pack(side="right", padx=8)
    more = label(win, "All FFXI mods on Nexus Mods", fg=ACCENT, cursor="hand2", font=(FONT, 9, "underline"))
    more.pack(anchor="w", padx=14, pady=(2, 8))
    more.bind("<Button-1>", lambda e: webbrowser.open(hd.NEXUS))

    # ---------------------------------------------------------------- 2. install
    label(win, "2.  Install what you downloaded", fg=GOLD, font=(FONT, 11, "bold")).pack(fill="x", padx=14)
    found_box = tk.Frame(win, bg=BG)
    found_box.pack(fill="x", padx=14)
    pick = tk.Frame(win, bg=BG)
    pick.pack(fill="x", padx=14, pady=(4, 8))

    # ---------------------------------------------------------------- 3. your packs
    label(win, "3.  Your packs", fg=GOLD, font=(FONT, 11, "bold")).pack(fill="x", padx=14)
    label(win, "Where two packs change the same thing, the one higher up wins. Changes count from the next PLAY.",
          fg=DIM, font=(FONT, 9)).pack(fill="x", padx=14)
    packs_box = tk.Frame(win, bg=BG)
    packs_box.pack(fill="x", padx=14, pady=(2, 6))
    status = tk.StringVar(value="")
    label(win, "", textvariable=status, fg=DIM, wraplength=720, font=(FONT, 9)).pack(fill="x", padx=14, pady=(4, 2), side="bottom")
    label(win, "If the screen goes black when you change areas, the game ran out of memory: switch the biggest pack off.",
          fg=DIM, wraplength=720, font=(FONT, 9)).pack(fill="x", padx=14, side="bottom")
    controls = []

    def tell(text):
        status.set(text)
        say(text)

    def guard(action):
        """Runs a quick change (on/off, order) and redraws; a problem is shown instead of thrown."""
        if state["busy"]:
            return
        try:
            action()
        except Exception as e:
            messagebox.showerror("HD texture packs", str(e), parent=win)
        refresh()

    def refresh():
        if state["closed"]:
            return
        for box in (found_box, packs_box, pick):
            for widget in box.winfo_children():
                widget.destroy()
        del controls[:]
        found = hd.find_downloads(hd.downloads_dirs())
        if not found:
            label(found_box, "No pack found in your Downloads folder yet. Download one (step 1), then press Look again, or choose the file below.",
                  fg=DIM, wraplength=720, font=(FONT, 9)).pack(fill="x")
        for f in found[:6]:
            row = tk.Frame(found_box, bg=PANEL)
            row.pack(fill="x", pady=2)
            label(row, os.path.basename(f["path"]), bg=PANEL, font=(FONT, 9, "bold")).pack(side="left", padx=8, pady=4)
            label(row, gb(f["size"]), bg=PANEL, fg=DIM, font=(FONT, 9)).pack(side="left")
            b = button(row, "Install", lambda p=f["path"]: start(p), strong=True)
            b.pack(side="right", padx=8)
            controls.append(b)
        for text, command in (("Look again", refresh), ("Choose a file...", choose_file), ("Install from a folder...", choose_folder)):
            b = button(pick, text, command)
            b.pack(side="left", padx=(0, 8))
            controls.append(b)
        packs = hd.installed(ashita)
        if not packs:
            label(packs_box, "None yet.", fg=DIM, font=(FONT, 9)).pack(fill="x")
        on_count = sum(1 for p in packs if p["on"])
        for p in packs:
            row = tk.Frame(packs_box, bg=PANEL)
            row.pack(fill="x", pady=2)
            label(row, p["name"], bg=PANEL, font=(FONT, 10, "bold")).pack(side="left", padx=8, pady=4)
            detail = gb(p["bytes"]) if p["bytes"] is not None else ""
            if p["left_out"]:
                detail += f"   {p['left_out']} file(s) left out so the era files win"
            label(row, detail, bg=PANEL, fg=DIM, font=(FONT, 9)).pack(side="left")
            b = button(row, "Remove", lambda n=p["name"]: take_out(n))
            b.pack(side="right", padx=(4, 8))
            controls.append(b)
            if p["on"] and on_count > 1:
                for text, up in (("Down", False), ("Up", True)):
                    b = button(row, text, lambda n=p["name"], u=up: guard(lambda: hd.move(ashita, n, u)))
                    b.pack(side="right", padx=2)
                    controls.append(b)
            b = tk.Button(row, text="On - turn off" if p["on"] else "Off - turn on", relief="flat", padx=10, bg=PANEL,
                          fg=GREEN if p["on"] else FG, command=lambda n=p["name"], v=not p["on"]: guard(lambda: switch(n, v)))
            b.pack(side="right", padx=4)
            controls.append(b)
        for c in controls:
            c.configure(state="disabled" if state["busy"] else "normal")

    def pivot_on():
        """XIPivot loads from the next PLAY: its line in Ashita's boot file, and its pivot.ini."""
        if core is None or not boot_ini or not os.path.exists(boot_ini):
            return False
        if not core.polplugin_on(boot_ini, "pivot"):
            core.set_polplugin(boot_ini, "pivot", True)
            return True
        return False

    def switch(name, on):
        hd.set_on(ashita, name, on)
        if on and pivot_on():
            tell("XIPivot was switched on (from the next PLAY).")

    def take_out(name):
        if state["busy"]:
            return
        if running():
            messagebox.showinfo("Remove " + name, "Close the game first: it may be reading this pack's files.", parent=win)
            return
        if not messagebox.askyesno("Remove " + name, f"Delete the texture pack {name} from this PC?\n\nYour game files are not touched. "
                                                     "To get the pack back you install it again from its downloaded file.", parent=win):
            return
        state["busy"] = True
        refresh()
        tell(f"Removing {name}...")

        def work():
            try:
                freed = hd.remove(ashita, name)
                lines.put(("done", f"{name} was removed ({gb(freed)} freed)."))
            except Exception as e:
                lines.put(("failed", f"Could not remove {name}: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def fetch_direct(pack):
        if state["busy"]:
            return
        if not hd.pivot_installed(ashita):
            messagebox.showinfo(pack["name"], "XIPivot is not installed yet. Install it first: OPTIONS > Get more, "
                                              "the XIPivot row, Install. Then come back here.", parent=win)
            return
        if running():
            messagebox.showinfo(pack["name"], "Close the game first, then download it.", parent=win)
            return
        if pack["folder"].lower() in {p["name"].lower() for p in hd.installed(ashita)}:
            messagebox.showinfo(pack["name"], "It is already installed: see 3. Your packs.", parent=win)
            return
        if not messagebox.askyesno(pack["name"], f"Download {pack['name']} from its author's GitHub page and install it?\n\n"
                                                 f"{pack['note']}", parent=win):
            return
        state["busy"] = True
        refresh()
        tell(f"Downloading {pack['name']}...")

        def work():
            try:
                hd.download_direct(pack, kit, ashita, log=lambda text: lines.put(("line", text)))
                lines.put(("done", f"{pack['name']} is installed, switched off. Turn it on in 3. Your packs (from the next PLAY)."))
            except Exception as e:
                lines.put(("failed", f"{pack['name']}: not installed ({e})"))
        threading.Thread(target=work, daemon=True).start()

    def choose_file():
        path = filedialog.askopenfilename(parent=win, title="The texture pack you downloaded",
                                          filetypes=[("Texture packs", "*.zip *.rar *.7z"), ("All files", "*.*")])
        if path:
            start(path)

    def choose_folder():
        path = filedialog.askdirectory(parent=win, title="The folder you unpacked the texture pack into")
        if path:
            start(path)

    def start(source):
        if state["busy"]:
            return
        if not hd.pivot_installed(ashita):
            messagebox.showinfo("HD texture packs", "XIPivot is not installed yet. Install it first: OPTIONS > Get more, "
                                                    "the XIPivot row, Install. Then come back here.", parent=win)
            return
        if running():
            messagebox.showinfo("HD texture packs", "Close the game first, then install the pack.", parent=win)
            return
        try:
            problem = hd.check_space(source, ashita)
            need = hd.space_needed(source)
        except Exception as e:
            messagebox.showerror("HD texture packs", f"Could not read {os.path.basename(source)}: {e}", parent=win)
            return
        if problem:
            messagebox.showwarning("Not enough room", problem, parent=win)
            return
        if not messagebox.askyesno("Install " + os.path.basename(source),
                                   f"Unpack {os.path.basename(source)} into Ashita's XIPivot folder?\n\nIt takes about {gb(need)} "
                                   "on the drive Ashita is on, and several minutes for a big pack. Your game files are not changed.", parent=win):
            return
        state["busy"] = True
        try:
            import shutil
            state["free_at_start"] = shutil.disk_usage(hd.dats_dir(ashita)).free
        except OSError:
            state["free_at_start"] = None
        refresh()
        tell(f"Installing {os.path.basename(source)}...")

        def tick():
            now = time.time()
            if state["free_at_start"] is None or now - state["last_tick"] < 8:
                return
            state["last_tick"] = now
            try:
                import shutil
                written = state["free_at_start"] - shutil.disk_usage(hd.dats_dir(ashita)).free
                if written > 0:
                    lines.put(("line", f"Unpacking... {gb(written)} so far."))
            except OSError:
                pass

        def work():
            try:
                done = hd.install(source, ashita, kit, log=lambda text: lines.put(("line", text)), tick=tick)
                names = ", ".join(d["name"] for d in done)
                lines.put(("installed", f"Installed: {names}. It shows from the next PLAY."))
            except Exception as e:
                lines.put(("failed", f"Not installed: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def pump():
        if state["closed"]:
            return
        try:
            while True:
                kind, text = lines.get_nowait()
                tell(text)
                if kind in ("installed", "done", "failed"):
                    state["busy"] = False
                    if kind == "installed":
                        try:
                            if pivot_on():
                                tell(text + " XIPivot was switched on.")
                        except Exception as e:
                            tell(text + f" (XIPivot could not be switched on by itself: {e}. Switch it on in its row.)")
                    if kind == "failed":
                        messagebox.showerror("HD texture packs", text, parent=win)
                    refresh()
        except queue.Empty:
            pass
        win.after(250, pump)

    refresh()
    pump()
    return win
