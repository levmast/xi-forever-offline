"""Run by render_pages.py with "checks": screenshots of the extra states (Play while running, every System page,
Co-op switched on) and checks on the whole window in the newer look. Uses render_pages.py's names (app, shot, settle...)."""
import tkinter as tk

# ---- more screenshots ----
if newer:
    app.select_tab(app.page_index["Play"])
    app.running = True
    app.play_btn.configure(state="disabled"); app.stop_btn.configure(state="normal"); app.progress.start(14)
    app.status.set("Starting the game servers...")
    app.refresh_stage()
    settle(1.6)
    print("running:", app.stop_btn.winfo_ismapped(), app.play_btn.winfo_ismapped(), app.progress.winfo_ismapped())
    shot("play-running")
    app.running = False
    app.play_btn.configure(state="normal"); app.stop_btn.configure(state="disabled"); app.progress.stop()
    app.status.set("Ready when you are.")
    app.refresh_stage()
    settle(1.6)
    print("idle:", app.stop_btn.winfo_ismapped(), app.play_btn.winfo_ismapped(), app.progress.winfo_ismapped())
    if getattr(app, "play_page", None) is not None and not player:
        app.play_page.toggle_log(); settle(0.6); shot("play-log"); app.play_page.toggle_log()
    if player:
        app.updates_tab.update_info = {"kit": {"installed": "v0.1.55", "newest": "v0.1.56", "newer": True, "notes": "- New launcher look\n- Fixes"},
                                       "server": {"installed": "v0.1.55", "newest": "v0.1.56", "newer": False, "notes": ""}}
        settle(1.6)
        print("notice:", app.play_page.notice.winfo_ismapped())
        shot("play-update")
    if getattr(app, "system_sections", None) is not None:
        app.select_tab(app.page_index["Settings"])
        settle(0.3)
        for name, kind, which in pages_mod.system_chips(app):
            if kind == "section":
                app.system_sections.show(which); app.select_tab(app.page_index["Settings"])
            else:
                app.select_tab(which)
            shot("system-" + name.lower().replace(" ", "-"))
        print("system chips:", [c[0] for c in pages_mod.system_chips(app)])
    try:
        tab = app.coop_tab
        app.select_tab(app.page_index["Co-op"])
        tab.settings["enabled"] = True
        tab.build()
        shot("co-op-on")
    except Exception as e:
        print("co-op on failed:", repr(e))

# ---- checks ----
if newer:
    P = pages_mod
    done = 0
    def ok(cond, what):
        global done
        done += 1
        if not cond:
            raise AssertionError(what)
    ok(app.new_ui is True, "the newer look is on")
    titles = [g["title"] for g in app.nav_groups]
    ok(titles == ["HOME", "WORLD", "RULES", "SQUADS", "OPTIONS", "CO-OP", "SYSTEM"], f"bar buttons: {titles}")
    for group in app.nav_groups:
        app.select_tab(group["members"][0][1]); settle(0.15)
        lit = [g["title"] for g in app.nav_groups if g["button"].line.cget("bg") == P.GOLD]
        ok(lit == [group["title"]], f"gold line under {group['title']} only: {lit}")
        ok(app.winfo_width() == 1100 and app.winfo_height() == 810, f"one window size ({app.winfo_width()}x{app.winfo_height()})")
    # the classic list shows the same settings as the new pages
    before = app.rates_tab.collect()
    app.rules_page.controls["map.EXP_RATE"].nudge(1); settle(0.1)
    ok(app.rates_tab.collect()["map.EXP_RATE"] == before["map.EXP_RATE"] + 0.25, "a change on Rules reaches what PLAY saves")
    P.show_classic(app); settle(0.2)
    ok("Rates" in app.page_index and app.tabs.index("current") == app.page_index["Rates"], "the classic settings list opens")
    app.rates_tab.vars["map.EXP_RATE"].set(str(before["map.EXP_RATE"])); settle(0.1)
    ok(app.rules_page.controls["map.EXP_RATE"].shown.get() == P.w.number_text(before["map.EXP_RATE"]), "a change on the classic list shows on Rules")
    ok(app.rates_tab.collect() == before, "back where it started")
    # System: one section at a time
    sections = app.system_sections
    ok(sections is not None, "the System sections were made")
    chips = P.system_chips(app)
    names = [c[0] for c in chips]
    if player:
        ok(names[0] == "Updates" and "Era" not in names and ("Team" in names) == ("contributor" in flags), f"player System pages: {names}")
    else:
        ok(names[0] == "Team" and "Era" in names and "Characters" in names and "About" in names, f"dev System pages: {names}")
    for name, kind, which in chips:
        if kind != "section":
            continue
        sections.show(which); app.select_tab(app.page_index["Settings"]); settle(0.2)
        for key, parts in sections.parts.items():
            for widget, _info in parts:
                ok(bool(widget.winfo_ismapped()) == (key == which), f"System > {name}: a part of '{key}' is {'shown' if widget.winfo_ismapped() else 'hidden'}")
        ok(sections.box.winfo_ismapped(), f"System > {name}: the output box is shown")
    every = [w_ for parts in sections.parts.values() for w_, _i in parts] + [sections.box]
    ok(set(every) == set(app.updates_tab.pack_slaves()) | set(every), "nothing on the Settings page was lost")
    P.open_system(app, "gm"); settle(0.2)
    ok(app.tabs.index("current") == app.page_index["Settings"] and sections.now == "gm", "open_system goes to GM and testing")
    # Characters: the Co-op page's own actions, with co-op off and with no characters
    chars = app.nametowidget(app.tabs.tabs()[app.page_index["Characters"]])
    for action in ("save_character", "carry_save"):
        chars.call(action)
    settle(0.3)
    ok(isinstance(app.coop_tab.carry_auto, tk.BooleanVar), "the automatic-folder switch has its value")
    # Co-op page: backup and carry are not drawn there in the newer look
    app.coop_tab.settings["enabled"] = True; app.coop_tab.build(); settle(0.3)
    texts = []
    def walk(widget):
        for child in widget.winfo_children():
            try:
                texts.append(str(child.cget("text")))
            except tk.TclError:
                pass
            walk(child)
    walk(app.coop_tab)
    ok("PLAY ON ANOTHER PC" not in texts and "YOUR CHARACTERS IN OTHER WORLDS" in texts, "Co-op page keeps visiting, without backup and carry")
    # the squad rules sit on the Squad page
    top = app.squad_tab.pack_slaves()[0]
    kinds = [type(c).__name__ for c in top.winfo_children()]
    ok(kinds.count("Switch") == 2 and kinds.count("Stepper") == 1, f"squad rules on the Squad page: {kinds}")
    # other people's addons and plugins are listed on the Addons and Plugins pages, the tools stay on Get more
    import launcher_thirdparty as tp_mod
    catalog = app.list_downloads
    manifest = tp_mod.load_manifest(kit)
    moved = {item["id"]: catalog.place(item)[0] for item in manifest if catalog.moved(item)}
    ok({i for i, k in moved.items() if k == "addon"} == {"xiui", "autobot", "mobdb", "cadence", "checkmate", "momentum", "ffxiport", "chains", "journal"}
       and {i for i, k in moved.items() if k == "plugin"} == {"xiuiplus", "nameplate"}, f"which downloads moved: {moved}")
    def texts_of(widget, out):
        for child in widget.winfo_children():
            try:
                out.append(str(child.cget("text")))
            except tk.TclError:
                pass
            texts_of(child, out)
        return out
    on_more = texts_of(app.dl_rows, [])
    names_of = {item["id"]: item["name"] for item in manifest}
    ok(all(names_of[i] not in on_more for i in moved), "a moved download is still on Get more")
    ok(all(item["name"] in on_more for item in manifest if item["id"] not in moved and (player or item.get("into") != "server")),
       "a tool is missing from Get more")
    for lst in app.lists:
        lst.search.set(""); settle(0.1)
        shown = texts_of(lst.inner, [])
        mine = [item for item in manifest if moved.get(item["id"]) == lst.kind]
        installed = [n.lower() for n in (gui.core.list_addons(ashita) if lst.kind == "addon" else gui.core.list_plugins(ashita))]
        ok(all(item["name"] in shown or catalog.place(item)[1] in installed for item in mine), f"{lst.kind}s: a download is not listed: {shown[:6]}")
        ok(("MORE ADDONS" if lst.kind == "addon" else "MORE PLUGINS") in shown and "Install" in shown, f"{lst.kind}s: no install rows")
        ok(shown.count("Update") == sum(1 for i, k in moved.items() if k == lst.kind and catalog.place(next(x for x in manifest if x["id"] == i))[1] in installed),
           f"{lst.kind}s: update buttons {shown.count('Update')}")
        lst.search.set("zzzz-nothing"); settle(0.1)
        ok("Install" not in texts_of(lst.inner, []), f"{lst.kind}s: the search does not narrow the downloads")
        lst.search.set(""); settle(0.1)
    # Play
    ok(app.play_page is not None and app.stage.winfo_width() == P.BANNER[0] + 2, "the Play page has its newer layout")
    ok(not app.update_btn.winfo_ismapped(), "no permanent UPDATE button")
    print(f"hook_checks: {done} checks passed ({'player' if player else 'dev'})")
