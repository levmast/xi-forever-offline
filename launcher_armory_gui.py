"""The "Character page & phone app" card on the launcher's Characters page (2026-11-24). The work is launcher_armory.py.

attach(page, grid, row): page is launcher_pages.CharactersPage (its .coop does background jobs and notes, its .choice is
the picked character), grid the page's card grid, row the grid row to use."""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

import launcher_armory as LA
import launcher_widgets as w

VIS_LABELS = {"public": "Everyone (public)", "link": "Only people with the link", "hidden": "Nobody (hidden)"}
VIS_KEYS = {v: k for k, v in VIS_LABELS.items()}


def attach(page, grid, row):
    coop = page.coop
    data = LA.load()
    card = w.Card(grid, "Character page & XIFO app")
    card.grid(row=row, column=0, columnspan=2, sticky="new", pady=(10, 0))
    card.note("SYNC puts your characters on xiforever.com as character pages: looks, jobs, gear, crafts, squad. They show "
              "in the Armory and the Hall of Fame. Gil and your bags are never shown. The XIFO app (phone, PC or xiforever.com/app), "
              "paired with PAIR APP, shows your characters and lets you fish on the go: what you catch arrives in the delivery box at your "
              "next PLAY.", wrap=960)
    auto = tk.BooleanVar(value=bool(data.get("sync")))

    def toggle():
        d = LA.load()
        d["sync"] = bool(auto.get())
        LA.save(d)
        coop.note("Your character pages update every time you press STOP." if d["sync"] else "Character pages: only when you press SYNC NOW.")

    card.row("Update my character pages when I press STOP", lambda parent: w.Switch(parent, auto, command=toggle))
    vis = tk.StringVar()

    def show_vis(*_):
        name = page.choice.get()
        vis.set(VIS_LABELS[LA.load()["visibility"].get(name, "public")] if name else "")

    def set_vis(*_):
        name = page.choice.get()
        if not name or vis.get() not in VIS_KEYS:
            return
        d = LA.load()
        d["visibility"][name] = VIS_KEYS[vis.get()]
        LA.save(d)
        coop.note(f"{name}'s page: {vis.get().lower()}. It changes on the site at the next SYNC.")

    def vis_box(parent):
        box = ttk.Combobox(parent, textvariable=vis, state="readonly", width=26, values=list(VIS_LABELS.values()))
        box.bind("<<ComboboxSelected>>", set_vis)
        return box

    card.row("Who can see the picked character's page", vis_box)
    page.choice.trace_add("write", show_vis)
    show_vis()

    def sync_now():
        def done(results):
            if results is None:
                return
            ok = [n for n, r in results.items() if r == "ok"]
            bad = [f"{n}: {r}" for n, r in results.items() if r != "ok"]
            coop.note((f"Synced to xiforever.com: {', '.join(ok)}." if ok else "Nothing synced.") + (" " + " ".join(bad) if bad else ""))
        coop.job(lambda: LA.sync(coop.cfg, log=coop.log), done, "Sending your characters to xiforever.com...")

    def open_page():
        name = page.choice.get()
        d = LA.load()
        link = d.get("links", {}).get(name)
        if not link:
            coop.note(f"{name or 'This character'} has no page yet: press SYNC NOW first.")
            return
        webbrowser.open(link)

    def pair():
        def done(code):
            if not code:
                return
            coop.note(f"App pairing code: {code} (for 10 minutes).")
            messagebox.showinfo("Pair the XIFO app",
                                f"In the XIFO app (phone, PC app or xiforever.com/app): ME > Pair with my launcher, and type\n\n        {code}\n\n"
                                "The code works once, for 10 minutes. Pair each phone or PC separately. Press SYNC NOW too, so the app has your characters.",
                                parent=page)
        coop.job(LA.pair, done, "Asking xiforever.com for a pairing code...")

    def unpair():
        if messagebox.askyesno("Forget paired apps", "Forget every phone and PC paired with this launcher? They stop seeing your characters "
                                                "and can't send catches until you pair them again.", parent=page):
            coop.job(LA.unpair, lambda _r: coop.note("Every paired app was forgotten."), "Forgetting paired apps...")

    bar = tk.Frame(card.body, bg=w.PANEL)
    bar.pack(fill="x", pady=(8, 2))
    w.button(bar, "SYNC NOW", sync_now, primary=True).pack(side="left")
    w.button(bar, "Open the picked character's page", open_page).pack(side="left", padx=8)
    w.button(bar, "PAIR APP...", pair).pack(side="left")
    w.button(bar, "Forget paired apps", unpair, small=True).pack(side="left", padx=8)
    tk.Label(bar, text="Armory: xiforever.com/armory", bg=w.PANEL, fg=w.DIM, font=(w.UI_FONT, 9), cursor="hand2").pack(side="right")
    bar.winfo_children()[-1].bind("<Button-1>", lambda e: webbrowser.open(LA.base_url(LA.load()) + "/armory"))
    return card
