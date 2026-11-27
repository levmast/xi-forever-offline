"""Native presentation for the optional PlayOffline Viewer theme."""
import ctypes
import os
from pathlib import Path
import tkinter as tk


def reduced_motion():
    if os.name == "nt":
        enabled = ctypes.c_int(1)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
            return not enabled.value
    return False


def splash(kit):
    """Show the supplied GIF once, preserving its frame times and proportions."""
    from PIL import Image, ImageSequence, ImageTk
    path = Path(kit) / "assets/press/playoffline-media/startup.gif"
    if not path.is_file():
        return
    win = tk.Tk()
    try:
        win.withdraw()
        win.overrideredirect(True)
        win.configure(bg="#233e59")
        still = reduced_motion()
        with Image.open(path) as gif:
            width, height = gif.size
            scale = min(1, win.winfo_screenwidth() * .85 / width, win.winfo_screenheight() * .85 / height)
            size = (max(1, round(width * scale)), max(1, round(height * scale)))
            frames = []
            for frame in ImageSequence.Iterator(gif):
                pic = frame.convert("RGB")
                if pic.size != size:
                    pic = pic.resize(size, Image.Resampling.LANCZOS)
                frames.append((ImageTk.PhotoImage(pic, master=win), max(10, frame.info.get("duration", 100))))
        width, height = size
        win.geometry(f"{width}x{height}+{(win.winfo_screenwidth()-width)//2}+{(win.winfo_screenheight()-height)//2}")
        label = tk.Label(win, borderwidth=0, highlightthickness=0)
        label.pack()
        timer = None

        def schedule(ms, command):
            nonlocal timer
            timer = win.after(ms, command)

        def fade(step=1):
            if step >= 10:
                win.quit()
            else:
                try:
                    win.attributes("-alpha", 1 - step / 10)
                except tk.TclError:
                    win.quit()
                    return
                schedule(35, lambda: fade(step + 1))

        def show(index):
            pic, duration = frames[index]
            label.configure(image=pic)
            if still:
                schedule(800, win.quit)
            elif index + 1 == len(frames):
                schedule(duration + 1000, fade)
            else:
                schedule(duration, lambda: show(index + 1))

        for event in ("<Escape>", "<Return>", "<space>", "<Button-1>"):
            win.bind(event, lambda _e: win.quit())
        win.protocol("WM_DELETE_WINDOW", win.quit)
        show(len(frames) - 1 if still else 0)
        win.deiconify()
        win.lift()
        win.focus_force()
        watch_pad(win, lambda keys: win.quit() if keys & 0x3000 else None)
        win.mainloop()
        if timer:
            win.after_cancel(timer)
    finally:
        win.destroy()


def decorate(app, kit):
    """Use the launcher's existing group buttons as a left menu on its Play page."""
    app.title("PlayOffline Viewer   —   XI: Forever Offline")
    header = tk.Frame(app, bg="#355877")
    header.pack(fill="x", before=app.navbar)
    brand = tk.Canvas(header, height=40, bg="#345674", highlightthickness=0, bd=0)
    brand.pack(fill="x")
    def draw_brand(event):
        brand.delete("all")
        for y in range(40):
            light = (40-y)//3 + (2 if y%4 == 0 else 0)
            brand.create_line(0,y,event.width,y,fill="#%02x%02x%02x" % (44+light,75+light,104+light))
        for offset in (0,22,40):
            x = event.width * .67 + offset
            brand.create_oval(x,-44,x+132,77,outline="#547591")
        brand.create_text(18,20,anchor="w",text="PlayOffline Viewer",fill="#f2faff",font=("Tahoma",14,"bold italic"))
        brand.create_text(event.width-18,20,anchor="e",text="XI   FOREVER OFFLINE",fill="#d4ebfa",font=("Tahoma",9,"bold"))
    brand.bind("<Configure>",draw_brand)
    section = tk.StringVar(master=app)
    tk.Label(header, textvariable=section, bg="#b2c5d2", fg="#203b50", anchor="w",
             padx=18, pady=2, font=("Tahoma", 9, "bold")).pack(fill="x")
    cursor = None
    if os.name == "nt":
        media = Path(kit) / "assets/press/playoffline-media"
        for filename in (("chocobo.cur",) if reduced_motion() else ("chocobo.ani", "chocobo.cur")):
            candidate = "@" + (media / filename).as_posix()
            try:
                header.configure(cursor=candidate)
                cursor = candidate
                break
            except tk.TclError:
                continue
    buttons = [g["button"].button for g in app.nav_groups] + [app.exit_btn]
    for i, btn in enumerate(buttons):
        btn.configure(takefocus=True)
        for key, offset in (("Down", 1), ("Right", 1), ("Up", -1), ("Left", -1)):
            btn.bind("<"+key+">", lambda e, j=(i+offset)%len(buttons): (buttons[j].focus_set(), "break")[1])
        btn.bind("<Return>", btn._click)
        btn.bind("<space>", btn._click)
        btn.bind("<FocusIn>", lambda e, item=btn: item._set_hover(True))
        btn.bind("<FocusOut>", lambda e, item=btn: item._set_hover(False))
        if cursor:
            btn.bind("<Enter>", lambda e, item=btn: item.configure(cursor=cursor), add="+")
    rail = None
    def arrange():
        nonlocal rail
        page = app.tabs.tab(app.tabs.select(), "text").strip()
        section.set("Local Viewer    /    " + page)
        # Wide pages retain the complete horizontal toolbar. The rail fits the smaller home banner.
        holders = app.nav.winfo_children()
        width = app.winfo_width()
        vertical = page == "Play" and width >= 970 and app.winfo_height() >= 620
        wrapped = not vertical and sum(item.winfo_reqwidth() + 4 for item in holders) > width - 12
        layout = (vertical, wrapped)
        if layout == rail:
            return
        rail = layout
        app.navbar.pack_forget()
        app.navbar.pack(side="left" if vertical else "bottom", fill="y" if vertical else "x",
                        before=app.tabs, padx=(8,0) if vertical else 0, pady=(4,6))
        cols = 1 if vertical else (len(holders)+1)//2 if wrapped else len(holders)
        for item in holders:
            item.pack_forget()
            item.grid_forget()
        for i,item in enumerate(holders):
            item.grid(row=i//cols,column=i%cols,padx=2,sticky="w")
    app.tabs.bind("<<NotebookTabChanged>>", lambda e: arrange(), add="+")
    app.bind("<Configure>", lambda e: arrange() if e.widget is app else None, add="+")
    app.after_idle(arrange)

    def navigate(keys):
        focused = app.focus_displayof()
        if keys & 0x2000:
            app.go("Play")
            buttons[0].focus_set()
        elif keys & 15:
            offset = -1 if keys & 5 else 1
            index = buttons.index(focused) if focused in buttons else -1 if offset == 1 else 0
            buttons[(index + offset) % len(buttons)].focus_set()
        elif keys & 0x1000 and focused in buttons:
            focused._click(None)
    watch_pad(app, navigate)

def watch_pad(root, action):
    """Send fresh XInput presses only while this window has focus."""
    if os.name != "nt":
        return
    try:
        read = ctypes.windll.xinput1_4.XInputGetState
    except (OSError, AttributeError):
        return
    # XINPUT_STATE is a DWORD packet number followed by XINPUT_GAMEPAD.
    import struct
    state = ctypes.create_string_buffer(16)
    previous = None
    selected = None
    timer = None
    def later(delay):
        nonlocal timer
        timer = root.after(delay, poll)
    def cancel(event):
        if event.widget is root and timer:
            root.after_cancel(timer)
    def poll():
        nonlocal previous, selected
        focused = root.focus_displayof()
        if focused is None or focused.winfo_toplevel() is not root or root.grab_current() not in (None, root):
            previous = None
            later(200)
            return
        for slot in ([selected] if selected is not None else range(4)):
            if read(slot, ctypes.byref(state)) == 0:
                selected = slot
                buttons = struct.unpack_from("<H", state.raw, 4)[0]
                x, y = struct.unpack_from("<hh", state.raw, 8)
                buttons |= (1 if y > 20000 else 2 if y < -20000 else 0)
                buttons |= (8 if x > 20000 else 4 if x < -20000 else 0)
                pressed = 0 if previous is None else buttons & ~previous
                previous = buttons
                if pressed:
                    action(pressed)
                later(60)
                return
        selected, previous = None, None
        later(1000)
    # Destroying the Tk root also removes its polling callback.
    root.bind("<Destroy>", cancel, add="+")
    later(100)
