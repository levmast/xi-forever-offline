"""Tests for the CO-OP page with open worlds (launcher_coop_gui.py, slice 1c of 2026-11-22): two real pages in one
process, a host's and a visitor's, each with its own scratch database and kit folder, talking over the real port.
Every question box is answered by the test. Needs a display (on Linux: xvfb-run -a python test_openworld_page.py),
tkinter, and what test_openservice.py needs.
OPENWORLD_SHOTS=<folder> also saves pictures of the page (needs ImageMagick's "import")."""
import gc, json, os, shutil, subprocess, sys, tempfile, time, types, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cooptest as ct
import launcher_coop as co
import launcher_passport as pp
import test_openservice as svc

try:
    import tkinter as tk
    ROOT = tk.Tk()
except Exception as e:                           # no tkinter, or no display
    raise unittest.SkipTest(f"no window system to draw the page on ({e})")

# the page's own imports: a stand-in for launcher_core (fonts, the kit folder) and no limited-time look
core = types.ModuleType("launcher_core")
core.ui_fonts = lambda: ("DejaVu Sans", "DejaVu Sans Mono")
core.KIT_DIR = ct.KIT
_before = {name: sys.modules.get(name) for name in ("launcher_core", "launcher_theme")}
sys.modules["launcher_core"], sys.modules["launcher_theme"] = core, None
import launcher_coop_gui as gui
for _name, _module in _before.items():
    if _module is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _module

ACC, CHAR = svc.ACC, svc.CHAR
co.refresh_worlds = lambda kit, **_more: False      # (the tests never ask the real website for its list of worlds)
SHOTS = os.environ.get("OPENWORLD_SHOTS")
KEPT = {}


def setUpModule():
    svc.setUpModule()
    KEPT.update(connect=pp.connect, addresses=co.local_addresses, kind=co.address_kind)
    pp.connect = lambda cfg: ct.connect(cfg["db_name"])
    co.local_addresses = lambda: [{"address": "127.0.0.1", "kind": "lan"}]
    co.address_kind = lambda address: "lan"
    ROOT.geometry("1100x720+0+0")


def tearDownModule():
    pp.connect, co.local_addresses, co.address_kind = KEPT["connect"], KEPT["addresses"], KEPT["kind"]
    svc.tearDownModule()
    try:
        ROOT.destroy()
    except Exception:
        pass


class Button(tk.Canvas):
    """The launcher's picture button, as far as the page uses it."""

    def __init__(self, parent, images, command, fallback_text):
        normal = images.get("normal")
        width, height = (normal.width(), normal.height()) if normal else (200, 48)
        super().__init__(parent, width=width, height=height, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.imgs, self.command, self.state, self.fallback_text = images, command, "normal", fallback_text
        self.item = self.create_image(0, 0, anchor="nw", image=normal) if normal else \
            self.create_text(width // 2, height // 2, text=fallback_text, fill="#e9f1f5")

    def configure(self, cnf=None, **kw):
        if "state" in kw:
            self.state = kw.pop("state")
            image = self.imgs.get("off" if self.state == "disabled" else "normal") or self.imgs.get("normal")
            if image:
                self.itemconfigure(self.item, image=image)
        if cnf or kw:
            return super().configure(cnf, **kw)

    def press(self):
        if self.state != "disabled":
            self.command()


class App:
    def __init__(self, cfg):
        self.cfg, self.running, self.new_ui, self.said, self.visit = cfg, False, True, [], None

    def say(self, text):
        self.said.append(text)

    def open_url(self, _url):
        pass

    def go(self, _page):
        pass

    def start(self):
        pass


def texts(widget):
    """Every piece of text a widget and its children show."""
    out = []
    for child in widget.winfo_children():
        try:
            if child.winfo_manager():
                if isinstance(child, Button):
                    out.append(child.fallback_text)
                elif isinstance(child, tk.Text):
                    out.append(child.get("1.0", "end").strip())
                elif child.winfo_class() in ("Label", "Radiobutton", "Checkbutton", "Button"):
                    out.append(str(child.cget("text")))
                out.extend(texts(child))
        except tk.TclError:
            pass
    return out


def find(widget, text):
    """The shown picture button with that label, or None."""
    for child in widget.winfo_children():
        if not child.winfo_manager():
            continue
        if isinstance(child, Button) and child.fallback_text == text:
            return child
        found = find(child, text)
        if found is not None:
            return found
    return None


class Pages(unittest.TestCase):
    def setUp(self):
        svc.OpenWorld.setUp(self)                # two worlds, a character in each; (its own Host is stopped again below)
        self.host.stop()
        self.settings.update({"enabled": True, "hosting": False, "open": False, "mode": "lan", "address": "127.0.0.1"})
        co.save_settings(self.kit_host, self.settings)
        home = co.load_settings(self.kit_home)
        home["enabled"] = True
        co.save_settings(self.kit_home, home)
        if SHOTS:                                # pictures need the art; the tests themselves do not
            for kit in (self.kit_host, self.kit_home):
                shutil.copytree(os.path.join(ct.KIT, "assets", "ui"), os.path.join(kit, "assets", "ui"))
        self.boxes, self.answers = [], {}
        self._real = {}
        for name in ("askyesno", "showinfo", "showwarning", "showerror", "askyesnocancel"):
            self._real[name] = getattr(gui.messagebox, name)
            setattr(gui.messagebox, name, lambda title, text="", _kind=name, **_k: self.box(_kind, title, text))
        self._real["askstring"] = gui.simpledialog.askstring
        gui.simpledialog.askstring = lambda title, text="", **_k: self.box("askstring", title, text)
        self.frames = []
        self.host_page = self.page(self.kit_host, {"db_name": ct.HOST_DB, "server_dir": self.server})
        self.home_page = self.page(self.kit_home, {"db_name": ct.HOME_DB, "server_dir": None})
        self.show(self.host_page)
        self.wait(lambda: self.home_page.characters and self.host_page.loaded)

    def tearDown(self):
        for page in (self.host_page, self.home_page):
            try:
                page.shutdown()
            except Exception:
                pass
        for frame in self.frames:
            frame.destroy()
        ROOT.update()
        self.frames, self.host_page, self.home_page = [], None, None
        gc.collect()                             # (the pages' Tk variables are let go here, in the window's own thread)
        for name, real in self._real.items():
            setattr(gui.simpledialog if name == "askstring" else gui.messagebox, name, real)
        svc.OpenWorld.tearDown(self)

    q, away = svc.OpenWorld.q, svc.OpenWorld.away

    def page(self, kit, cfg):
        core.KIT_DIR = kit
        frame = tk.Frame(ROOT)
        self.frames.append(frame)
        page = gui.CoopTab(frame, App(cfg), Button)
        page.pack(fill="both", expand=True)
        return page

    def show(self, page):
        for frame in self.frames:
            frame.pack_forget()
        page.master.pack(fill="both", expand=True)
        ROOT.update()

    def box(self, kind, title, text):
        """A question or message box of the page: noted, and answered from self.answers[title] (a list) when there is one."""
        self.boxes.append((kind, title, str(text)))
        waiting = self.answers.get(title) if kind.startswith("ask") else None
        if waiting:
            return waiting.pop(0)
        return {"askyesno": True, "askyesnocancel": True, "askstring": None}.get(kind)

    def said(self, title):
        return [text for _kind, name, text in self.boxes if name == title]

    def wait(self, done, seconds=30):
        end = time.time() + seconds
        while time.time() < end:
            ROOT.update()
            if done():
                ROOT.update()
                return
            time.sleep(0.02)
        self.fail("waited too long; boxes so far: " + repr(self.boxes[-4:]))

    def settle(self, seconds=0.8):
        end = time.time() + seconds
        while time.time() < end:
            ROOT.update()
            time.sleep(0.02)

    def shot(self, name, window=None):
        if not SHOTS:
            return
        os.makedirs(SHOTS, exist_ok=True)
        self.settle(0.6)
        target = window or ROOT
        target.lift()
        ROOT.update()
        x, y, w, h = target.winfo_rootx(), target.winfo_rooty(), target.winfo_width(), target.winfo_height()
        subprocess.run(["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", "+repage", os.path.join(SHOTS, name + ".png")], check=False)

    def kicks(self):
        try:
            with open(os.path.join(self.server, "modules", "custom", "lua", "coop_in.txt")) as handle:
                return [line.split("|")[3] for line in handle.read().splitlines() if "|KICK|" in line]
        except OSError:
            return []

    def open_the_world(self, visitors="12"):
        page = self.host_page
        page.world_name.set("Test Hub")
        page.who.set("open")
        page.who_changed()
        page.max_guests.set(visitors)
        page.address.set("127.0.0.1")
        page.start_hosting()
        self.wait(lambda: self.said("Hosting is on"))
        return page

    def no_errors(self):
        self.assertEqual([b for b in self.boxes if b[0] == "showerror"], [])

    # --- the host's page ---
    def test_between_friends_the_page_is_as_before(self):
        page = self.host_page
        self.assertEqual(page.who.get(), "friends")
        self.assertEqual(int(page.max_box.cget("to")), co.MAX_GUESTS)
        self.assertIsNotNone(find(page, "COPY INVITE"))
        for label in ("COPY LINK", "PASSWORD", "PLACES", "KICK", "BAN"):
            self.assertIsNone(find(page, label), label)
        page.max_guests.set("5")
        page.address.set("127.0.0.1")
        page.start_hosting()
        self.wait(lambda: self.said("Hosting is on"))
        self.assertEqual(self.said("Open to everyone"), [])                      # nothing new is asked
        self.assertIn("invite code", self.said("Hosting is on")[0])
        saved = co.load_settings(self.kit_host)
        self.assertEqual((saved["hosting"], saved["open"], saved["max_guests"]), (True, False, 5))
        self.assertTrue(page.invite_code.get().startswith(co.PREFIX))
        self.assertEqual((page.code_label.cget("text"), page.reach_label.cget("text")), ("Invite code", "Friends reach me"))
        self.assertIsNone(page.host.tls)                                          # the service answers friends only
        # a friend visits with the invite code, through the visitor's page
        home = self.home_page
        home.their_code.set(page.invite_code.get())
        home.visit()
        self.wait(lambda: self.said("Arrived"))
        self.assertTrue(self.away()[0]["host"]["arrived"])
        self.assertNotIn("open", self.away()[0]["host"])
        self.assertEqual(self.said("World password") + self.said("Visiting name"), [])
        page.refresh()
        self.wait(lambda: page.guest_rows)
        self.assertIsNone(find(page, "KICK"))                                     # a friend's visit: SEND HOME only, as before
        self.assertIsNotNone(find(page, "SEND HOME"))
        self.no_errors()

    def test_opening_the_world_to_everyone(self):
        page = self.host_page
        page.start_service()                                                      # (as when the launcher opened with a visitor still here)
        self.assertIsNone(page.host.tls)
        page.who.set("open")
        page.who_changed()
        self.assertEqual(int(page.max_box.cget("to")), co.MAX_OPEN_GUESTS)
        self.assertEqual((page.code_label.cget("text"), page.reach_label.cget("text")), ("World link", "Visitors reach me"))
        self.assertIn("anyone who has its link", page.host_state.cget("text"))
        page.max_guests.set("40")
        page.who.set("friends")                                                   # back to friends: the old limit stands again
        page.who_changed()
        self.assertEqual(page.max_guests.get(), str(co.MAX_GUESTS))
        self.answers["Open to everyone"] = [False]                                # asked first; "no" starts nothing
        page.who.set("open")
        page.who_changed()
        page.address.set("127.0.0.1")
        page.start_hosting()
        self.settle()
        self.assertFalse(co.load_settings(self.kit_host)["hosting"])
        self.open_the_world("12")
        self.assertIn("12 visitor", self.said("Open to everyone")[-1])
        self.assertIn("COPY LINK", self.said("Hosting is on")[0])
        saved = co.load_settings(self.kit_host)
        self.assertEqual((saved["hosting"], saved["open"], saved["max_guests"]), (True, True, 12))
        link = co.read_code(page.invite_code.get())
        self.assertEqual((link["open"], link["address"], link["port"], link["pin"], link["world"]),
                         (True, "127.0.0.1", self.settings["port"], co.server_fingerprint(self.server), "Test Hub"))
        self.assertIsNotNone(page.host.tls)
        self.assertEqual(co.hello(link)["world"]["name"], "Test Hub")              # and it answers on that link
        for label in ("COPY LINK", "PASSWORD", "PLACES", "STOP HOSTING"):
            self.assertIsNotNone(find(page, label), label)
        for label in ("COPY INVITE", "NEW CODE", "START HOSTING"):
            self.assertIsNone(find(page, label), label)
        self.assertEqual([str(b.cget("state")) for b in page.who_buttons], ["disabled", "disabled"])   # chosen before hosting
        self.assertIn("Password: none.", page.host_state.cget("text"))
        find(page, "COPY LINK").press()
        self.assertEqual(ROOT.clipboard_get(), page.invite_code.get())
        self.assertIn("World link copied", page.note_text.get())
        # a password: only its scrambled form is kept, and an empty answer removes it
        self.answers["World password"] = ["moogle", None, "  "]
        find(page, "PASSWORD").press()
        saved = co.load_settings(self.kit_host)["password"]
        self.assertTrue(co.check_password(saved, "moogle") and "moogle" not in saved)
        self.assertIn("Password: set.", page.host_state.cget("text"))
        self.assertTrue(co.hello(link)["password"])
        find(page, "PASSWORD").press()                                             # Cancel: nothing changes
        self.assertEqual(co.load_settings(self.kit_host)["password"], saved)
        find(page, "PASSWORD").press()
        self.assertEqual(co.load_settings(self.kit_host)["password"], "")
        self.assertFalse(co.hello(link)["password"])
        self.no_errors()

    def test_no_link_before_the_game_server_has_a_key(self):
        os.remove(os.path.join(self.server, "login.cert"))
        page = self.open_the_world()
        self.assertEqual(page.invite_code.get(), "")
        self.assertIn("Press PLAY once", page.host_state.cget("text"))
        self.assertEqual(find(page, "COPY LINK").state, "disabled")

    # --- a whole visit through both pages ---
    def test_a_stranger_visits_is_kicked_banned_and_comes_home(self):
        host_page, home = self.open_the_world(), self.home_page
        self.answers["World password"] = ["moogle"]
        find(host_page, "PASSWORD").press()
        ct.make_character(self.host_db, ACC, CHAR + 1, "Visitor", linkshell=False)   # the visitor's name is taken there
        link = host_page.invite_code.get()

        # TEST CONNECTION tells what kind of world it is
        self.show(home)
        home.their_code.set(link)
        home.test_connection()
        self.wait(lambda: "answered" in home.info.get("1.0", "end"))
        told = home.info.get("1.0", "end")
        self.assertIn("open to everyone who knows its password", told)
        self.assertIn(f"keeps your place for {pp.LOCKER_DAYS} days", told)

        # VISIT: the password is asked for (a wrong one first), then a visiting name because "Visitor" is taken
        self.answers.update({"World password": ["kupo", "moogle"], "Visiting name": ["x", "kupo"]})
        home.visit()
        self.wait(lambda: self.said("Arrived") or "still packed" in home.note_text.get())
        self.assertEqual(len(self.said("World password")), 3)                      # (once at the host, then asked twice here)
        self.assertIn("is not this world's password", self.said("World password")[-1])
        self.assertIn("open to everyone", self.said("Visit")[0])
        self.assertIn(f"{pp.LOCKER_DAYS} days", self.said("Visit")[0])
        self.assertEqual(self.said("Arrived"), [])                                  # "x" is no name: still packed, nothing lost
        self.assertFalse(self.away()[0]["host"]["arrived"])
        self.assertIn("still packed", home.note_text.get())
        self.wait(lambda: home.away_rows)
        home.away_pick.set(str(CHAR))
        home.show_away_buttons()
        find(home, "TRY AGAIN").press()
        self.wait(lambda: self.said("Arrived"))
        self.assertIn("as Kupo", self.said("Arrived")[0])
        row = self.away()[0]
        self.assertEqual((row["host"]["arrived"], row["host"]["local"], row["host"]["open"]), (True, "Kupo", True))
        self.wait(lambda: home.away_rows and home.away_rows[0]["host"].get("arrived"))
        self.assertTrue(any("as Kupo" in text for text in texts(home.away_box)))
        self.shot("visitor-visiting")

        # the host's page: the visitor under its visiting name, with KICK and BAN
        self.show(host_page)
        host_page.refresh()
        self.wait(lambda: host_page.guest_rows)
        guest = host_page.guest_rows[0]
        self.assertIn("Kupo", texts(host_page.guest_box))
        for label in ("SEND HOME", "KICK", "BAN"):
            self.assertIsNotNone(find(host_page, label), label)
        find(host_page, "KICK").press()
        self.assertIn("not in the game", self.said("Kick")[0])
        self.assertEqual(self.kicks(), [])
        ct.run(self.host_db, "INSERT INTO accounts_sessions (accid, charid) VALUES (?, ?)", (guest["accid"], guest["charid"]))
        self.host_db.commit()
        host_page.refresh()
        self.wait(lambda: host_page.guest_rows and host_page.guest_rows[0]["online"])
        self.shot("host-open-with-visitor")
        self.answers["Kick"] = [False, True]
        find(host_page, "KICK").press()                                            # "no": nothing happens
        self.settle(0.5)
        self.assertEqual(self.kicks(), [])
        find(host_page, "KICK").press()
        self.wait(lambda: self.kicks())
        self.assertEqual(self.kicks(), [str(guest["charid"])])
        self.assertEqual(self.q(self.host_db, "SELECT status FROM accounts WHERE id = ?", (guest["accid"],)), [(1,)])   # a kick closes nothing
        self.answers["Ban"] = [True, False]                                        # ban, but not the address
        find(host_page, "BAN").press()
        self.wait(lambda: host_page.host.bans())
        self.assertEqual([(b["kind"], b["value"], b["reason"]) for b in host_page.host.bans()], [("key", guest["owner"], "Kupo")])
        self.assertEqual(self.q(self.host_db, "SELECT status FROM accounts WHERE id = ?", (guest["accid"],)), [(0,)])
        self.assertEqual(len(self.kicks()), 2)
        self.assertIn(guest["guest_id"], host_page.host.out)                       # asked out again until it has left

        # home again from the visitor's page; its place there is listed with its end date
        ct.run(self.host_db, "DELETE FROM accounts_sessions")
        self.host_db.commit()
        self.show(home)
        home.away_pick.set(str(CHAR))
        home.come_home()
        self.wait(lambda: self.said("Welcome home"))
        self.assertEqual(self.away(), [])
        self.wait(lambda: home.place_rows and not home.away_rows)
        shown = texts(home.place_area)
        self.assertIn("YOUR PLACES IN OPEN WORLDS", shown)
        self.assertTrue(any(text.startswith("Kupo  in  Test Hub") for text in shown), shown)
        self.assertTrue(any(text == "kept until " + gui.day(home.place_rows[0]["until"]) for text in shown), shown)
        self.shot("visitor-kept-place")

        # the host's window of kept places and bans
        self.show(host_page)
        window = host_page.kept_places()
        self.wait(lambda: any("Kupo" == text for text in texts(window)))
        shown = texts(window)
        self.assertTrue(any(text.startswith("last here ") and "kept until " in text for text in shown), shown)
        self.assertTrue(any(text.startswith("their launcher, since ") for text in shown), shown)
        self.shot("host-kept-places", window)
        find(window, "LIFT BAN").press()
        self.wait(lambda: not host_page.host.bans())
        self.wait(lambda: "Nobody is banned." in texts(window))
        self.assertEqual(find(window, "LIFT BAN").state, "disabled")
        self.answers["Forget this place"] = [False, True]
        find(window, "FORGET").press()
        self.settle(0.5)
        self.assertEqual(len(host_page.host.lockers()), 1)                         # "no": the place stays
        find(window, "FORGET").press()
        self.wait(lambda: not host_page.host.lockers())
        self.wait(lambda: "No places are kept right now." in texts(window))
        window.destroy()

        # VISIT AGAIN fills in the way back; FORGET takes the place off the visitor's own list
        self.show(home)
        home.their_code.set("")
        home.character.set("")
        self.answers.update({"World password": ["moogle"], "Visit": [False]})
        find(home, "VISIT AGAIN").press()
        self.wait(lambda: len(self.said("Visit")) == 2)
        self.assertEqual(co.read_code(home.their_code.get()), co.read_code(link))
        self.assertEqual(home.character.get(), "Visitor")
        self.settle(0.5)
        self.assertEqual(self.away(), [])                                           # "no" at the question: nobody travelled
        self.answers["Forget"] = [True]
        find(home, "FORGET").press()
        self.assertEqual(co.places(self.kit_home), [])
        self.assertNotIn("YOUR PLACES IN OPEN WORLDS", texts(home.place_area))
        self.no_errors()

    def test_a_ban_can_take_the_address_too_and_a_kept_place_can_be_banned(self):
        host_page, home = self.open_the_world(), self.home_page
        home.their_code.set(host_page.invite_code.get())
        home.visit()
        self.wait(lambda: self.said("Arrived"))
        self.assertEqual(self.said("World password") + self.said("Visiting name"), [])   # no password, the name was free
        self.wait(lambda: home.away_rows and home.away_rows[0]["host"].get("arrived"))
        home.away_pick.set(str(CHAR))
        home.come_home()
        self.wait(lambda: self.said("Welcome home"))
        window = host_page.kept_places()
        self.wait(lambda: "Visitor" in texts(window))
        find(window, "BAN").press()                                                 # banned while it is home
        self.wait(lambda: host_page.host.bans())
        self.assertEqual([(b["kind"], b["reason"]) for b in host_page.host.bans()], [("key", "Visitor")])
        self.assertEqual(self.kicks(), [])
        window.destroy()
        self.boxes.clear()
        home.their_code.set(host_page.invite_code.get())
        home.visit()
        self.wait(lambda: self.said("Co-op"))                                       # turned away, and told so
        self.assertIn("does not let you in", self.said("Co-op")[0])
        self.assertEqual(self.away(), [])
        host_page.host.unban("key", host_page.host.bans()[0]["value"])
        home.visit()
        self.wait(lambda: self.said("Arrived"))
        self.wait(lambda: home.away_rows and home.away_rows[0]["host"].get("arrived"))
        self.assertTrue(home.place_rows)                                            # noted at the last homecoming,
        self.assertNotIn("YOUR PLACES IN OPEN WORLDS", texts(home.place_area))      # but not "kept" while the character is in it
        visit = self.away()[0]["host"]["guest_id"]
        host_page.refresh()
        self.wait(lambda: [g["guest_id"] for g in host_page.guest_rows] == [visit])
        self.answers["Ban"] = [True, True]                                          # this time with the address
        find(host_page, "BAN").press()
        self.wait(lambda: len(host_page.host.bans()) == 2)
        self.assertEqual(sorted((b["kind"], b["value"] if b["kind"] == "ip" else "") for b in host_page.host.bans()),
                         [("ip", "127.0.0.1"), ("key", "")])
        self.wait(lambda: "is banned from your world" in host_page.note_text.get())
        # a visitor the page still shows but who has left meanwhile: the page does not claim a ban that did not happen
        host_page.host.unban("ip", "127.0.0.1")
        stale = dict(host_page.guest_rows[0], guest_id="0" * 24)
        host_page.guest_rows = [stale]
        host_page.guest_pick.set(stale["guest_id"])
        before = len(host_page.host.bans())
        self.answers["Ban"] = [True, False]
        host_page.ban()
        self.wait(lambda: "nothing was changed" in host_page.note_text.get())
        self.assertEqual(len(host_page.host.bans()), before)
        self.no_errors()

    # --- the list of open worlds (2026-11-23) ---
    def test_the_listed_worlds_are_on_the_page_and_picking_one_fills_in_its_link(self):
        host_page = self.open_the_world()
        hub = host_page.invite_code.get()
        self.assertTrue(hub.startswith(co.LINK_PREFIX))
        nowhere = co.make_link("127.0.0.1", 9, co.read_code(hub)["pin"], "Nowhere")
        with open(os.path.join(self.kit_home, co.WORLDS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "worlds": [{"name": "Nowhere", "link": nowhere},
                                                {"name": "Test Hub", "official": True, "about": "The official world.", "link": hub}]}, handle)
        page = self.page(self.kit_home, {"db_name": ct.HOME_DB, "server_dir": None})      # a launcher that starts with this list in its kit
        try:
            self.show(page)
            self.wait(lambda: page.characters)
            shown = texts(page)
            self.assertIn("OPEN WORLDS", shown)
            at = shown.index("Test Hub")
            self.assertLess(at, shown.index("Nowhere"), "the official world is first")
            self.assertEqual(shown[at + 1], " OFFICIAL ")
            self.assertEqual(page.their_code.get(), "", "nothing is filled in before the player picks")
            self.wait(lambda: "online: 0 of 12 visitors" in texts(page), seconds=40)     # the page looks by itself while it is on the screen
            self.assertIn("no answer right now", texts(page))
            self.assertEqual(self.home_page.last_worlds, 0, "a page that is not on the screen asks no world anything")
            page.world_pick.set(hub)
            page.picked_world()
            self.assertEqual(page.their_code.get(), hub)
            said = page.info.get("1.0", "end")
            self.assertIn("Test Hub (the official world): The official world.", said)
            self.assertIn("Press VISIT", said)
            page.show_worlds()                                       # drawn again (as once a minute): the pick stays
            self.assertEqual(page.world_pick.get(), hub)
            page.test_connection()                                   # and the buttons below work on what was filled in
            self.wait(lambda: "answered" in page.info.get("1.0", "end"))
            self.assertIn("Test Hub answered. Visitors: 0 of 12.", page.info.get("1.0", "end"))
            self.shot("visitor-open-worlds")
        finally:
            page.shutdown()
        self.assertNotIn("OPEN WORLDS", texts(self.home_page), "a launcher without a list shows none")
        fresh = os.path.join(self.tmp, "fresh")                      # co-op not switched on yet: the first page says the world is there
        os.makedirs(fresh)
        shutil.copy(os.path.join(self.kit_home, co.WORLDS_FILE), fresh)
        intro = self.page(fresh, {"db_name": ct.HOME_DB, "server_dir": None})
        try:
            self.show(intro)
            self.assertIn("Test Hub, the official world, is always online. Turn co-op on to visit it.", texts(intro))
        finally:
            intro.shutdown()
        self.no_errors()


if __name__ == "__main__":
    unittest.main(verbosity=1)
