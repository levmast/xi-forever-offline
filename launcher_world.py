"""A world that runs without the launcher's window (XI: Forever Offline, open worlds, 2026-11-23): the database, the
game servers and the co-op door, started and watched by one program, so that a service can run it. The hub, a rented
server ("cloud world") and a home PC that keeps its world open all use it.

    python launcher_world.py run        start the world and stay with it until it is told to stop (Ctrl+C, or the stop
                                        of the service that runs it)
    python launcher_world.py status     what the running world last wrote about itself (logs/world-status.json)
    python launcher_world.py setup      the first setup of a world on a server (launcher_world_setup.py; --help)
    python launcher_world.py backup     save the database now (backups/world)
    python launcher_world.py backups    the copies that are there
    python launcher_world.py restore FILE   put the database back from a copy (the world must be stopped)
    python launcher_world.py update [--retry]   look for a new release now (a running world is asked to; a stopped
                                        one installs it at once). --retry: also a release that was taken back
    python launcher_world.py who        the visitors that are here: name, number, in the game or not; it also says
                                        whether the running world answers (kick and ban go through it)
    python launcher_world.py kick WHO   log a visitor out of the game (WHO: a name, or the number 'who' shows)
    python launcher_world.py ban WHO [--address] [why]   ban a visitor's launcher (--address: and the address it last
                                        used): it is put out of the game and cannot come back; its character can still
                                        go home. Also for a visitor who is home and has a kept place here
    python launcher_world.py bans       the bans
    python launcher_world.py unban WHAT lift a ban (WHAT: the name, the address, or the start of the launcher's key)
    python launcher_world.py places     the places kept for visitors who are home
    python launcher_world.py forget WHO give up a kept place (its character here goes, with listings and delivery box)
  From the packaged launcher:  XI-Forever-Offline --run launcher_world.py run

It does for the server side what PLAY does in the launcher's window (launcher_gui.pyw, launch), from the same settings:
config.json, the RULES page's rates.json and the CO-OP page's coop.json. Nothing of the game client is touched. The
auction house simulator is started when the rules have it on, and the bots' chat helper when this world chats through
Google's Gemma (crowds/ai_cloud.py: ai-cloud.json and a key in the kit; the hub). No local AI is ever started. While it runs it keeps a banned
visitor out, clears kept places whose time is up, and writes its state to a file every half minute. If one of the
game servers stops by itself, the world is stopped as a whole and the program ends with exit code 1, so the service
that runs it starts it again.

Stopping is a restart as far as visitors are concerned: they are told, given a minute to log out, and their
characters stay in the world for when it is back. Nobody is sent home.

While it runs it also saves its database every night and installs new full releases by itself, with a way back
(launcher_world_keep.py). For an update it ends with exit code 75: the service (or run-world.sh) starts it again, and
the update goes in before the game servers start.
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import launcher_coop as co                      # noqa: E402
import launcher_core as core                    # noqa: E402
import launcher_world_keep as keep              # noqa: E402

STATUS_FILE = "world-status.json"               # in the kit's logs folder
LOG_FILE = "world.log"
TICK_SECONDS = 2                                # how often the running world looks at itself
GUESTS_SECONDS = 6                              # how often it looks at its visitors (as the CO-OP page does)
STATUS_SECONDS = 30
STOP_GRACE_SECONDS = 60                         # visitors in the game get this long to log out before the servers stop
SERVER_GAP_SECONDS = 3                          # between the starts of two game servers (as PLAY does)
CLOSING_LINE = "This world is restarting in one minute. Log out now: your character stays here, and you can log in again when it is back."
ASKED_DIR = "world-asked"                       # in logs: what was asked by hand about a visitor, one small file each
ANSWERS_DIR = "world-answers"                   # ...and what the running world said back
ANSWER_WAIT_SECONDS = 20                        # how long a command waits for the running world (which looks every 2 seconds)
HELLO_WAIT_SECONDS = 8                          # ...and how long 'who' waits to hear that the running world answers at all
VISITOR_COMMANDS = ("who", "kick", "ban", "bans", "unban", "places", "forget")
USAGE = {"kick": "kick <name or number>", "ban": "ban <name or number> [--address] [why]",
         "unban": "unban <name, address, or the start of a launcher's key>", "forget": "forget <name or number>"}


class WorldError(Exception):
    """The world could not start, or stopped by itself. The text can be shown as it is."""


class World:
    def __init__(self, kit, cfg=None, log=None):
        self.kit = kit
        self.cfg = cfg if cfg is not None else core.load_config(os.path.join(kit, "config.json"))
        self.logs = os.path.join(kit, "logs")
        self.settings = co.load_settings(kit)
        self.rates = self.load_rates()
        self.log = log
        self.procs, self.logfiles, self.helpers = {}, [], {}
        self.host, self.db_proc, self.lock = None, None, None
        self.hosting = False
        self.state, self.since, self.problem = "stopped", 0, ""
        self.stopping = threading.Event()
        self.sleep, self.clock = time.sleep, time.time          # (tests stand in for these)
        self.last_guests = self.last_status = 0
        self.link = ""                                          # an open world's link, once its door is open
        self.keeper = keep.Keeper(self)                         # nightly backups and updates

    # ----- telling what happens -----
    def say(self, text):
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(text)
        if self.log is not None:
            self.log(str(text))
        else:
            print(line, flush=True)
        try:
            os.makedirs(self.logs, exist_ok=True)
            with open(os.path.join(self.logs, LOG_FILE), "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    def write_status(self):
        visitors = online = 0
        if self.host is not None:
            try:
                rows = [g for g in self.host.guests() if g["state"] == "active"]
                visitors, online = len(rows), len([g for g in rows if g["online"]])
            except Exception:
                pass
        status = {"state": self.state, "since": int(self.since), "updated": int(self.clock()), "pid": os.getpid(),
                  "versions": co.versions(self.kit, self.cfg.get("server_dir")), "hosting": bool(self.hosting),
                  "open": bool(self.hosting and self.settings.get("open")), "address": self.settings.get("address", ""),
                  "port": int(self.settings.get("port", co.PORT)), "visitors": visitors, "online": online,
                  "max_guests": int(self.settings.get("max_guests", 0)), "problem": self.problem, "link": self.link}
        try:
            status.update(self.keeper.status())
        except Exception:
            pass
        try:
            os.makedirs(self.logs, exist_ok=True)
            path = os.path.join(self.logs, STATUS_FILE)
            with open(path + ".part", "w", encoding="utf-8", newline="\n") as handle:
                json.dump(status, handle, indent=1)
                handle.write("\n")
            os.replace(path + ".part", path)
        except OSError:
            pass
        self.last_status = self.clock()
        return status

    # ----- the pieces of a start (each one small, so a test can stand in for the ones that start programs) -----
    def load_rates(self):
        return core.load_rates(self.kit)

    def take_lock(self):
        """One launcher or world at a time, the launcher's own rule (a second one would stop the first one's servers).
        Windows: the launcher's named mutex. Linux: its lock file in logs. Returns False when another holds it."""
        if os.name == "nt":
            try:
                import ctypes
                k32 = ctypes.windll.kernel32
                handle = k32.CreateMutexW(None, False, "XIForeverOfflineLauncher")
                if k32.GetLastError() == 183:            # ERROR_ALREADY_EXISTS: a launcher window is open
                    k32.CloseHandle(handle)
                    return False
                self.lock = handle
            except Exception:
                pass
            return True
        import launcher_linux
        self.lock = launcher_linux.take_lock(self.kit)
        return self.lock is not None

    def release_lock(self):
        if self.lock is None:
            return
        try:
            if os.name == "nt":
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self.lock)
            else:
                os.close(self.lock)
        except Exception:
            pass
        self.lock = None

    def clean_up(self):
        for name in core.SERVERS:
            core.kill(name)
        self.sleep(2)

    def database(self):
        """The database is running and has what the map server needs. The kit's own MariaDB is started here."""
        cfg = self.cfg
        if cfg.get("mariadb_dir"):
            import launcher_setup
            started = launcher_setup.start_portable(cfg)
            if started is not None:
                self.db_proc = started
                self.say("Database started.")
            for what, check in (("the database triggers", launcher_setup.ensure_triggers),
                                ("the add-on tables", launcher_setup.ensure_module_tables)):
                try:
                    check(cfg, cfg["server_dir"], log=self.say)
                except Exception as e:
                    self.say(f"Could not check {what} ({e}) - starting anyway.")
        else:
            service = cfg.get("mariadb_service", "MariaDB")
            if not core.ensure_service(service):
                raise WorldError(f"The database service '{service}' was not found or would not start.")

    def stop_database(self):
        if self.cfg.get("mariadb_dir"):
            import launcher_setup
            launcher_setup.stop_portable(self.cfg)

    def script(self, name, *args, timeout=120):
        """Runs one of the kit's own scripts to its end. Returns its last line, or None when it is not there or failed."""
        path = os.path.join(self.kit, name)
        if not os.path.exists(path):
            return None
        done = subprocess.run(core.py_cmd(path, *args), cwd=self.kit, capture_output=True, text=True, errors="replace",
                              timeout=timeout, creationflags=core.NO_WINDOW)
        lines = ((done.stdout if done.returncode == 0 else done.stderr or done.stdout) or "").strip().splitlines()
        if done.returncode != 0:
            raise WorldError(lines[-1] if lines else f"{name} failed")
        return lines[-1] if lines else ""

    def chores(self):
        """What PLAY does to the server's files and database before the servers start. None of it may stop a start."""
        cfg, rates = self.cfg, self.rates

        def certificate():
            if core.clear_half_made_certificate(cfg["server_dir"]):
                self.say("Removed a half-made login certificate from an interrupted start; the server makes a new one.")

        def kit_paths():
            core.write_kit_paths(cfg["server_dir"], self.kit, cfg.get("ashita_dir"))

        def conquest():
            if rates.get("conquest_sim", True):
                last = self.script("conquest_sim.py", "tick", timeout=90)
                if last:
                    self.say(last)

        def stacks():
            self.script("stack_mode.py", "db", "modern" if rates.get("modern_stacks", True) else "era", timeout=90)

        def equipment():
            import fix_equip
            count, names, _backup = fix_equip.repair(cfg, self.kit)
            if count:
                self.say(f"Fixed {count} broken equipment row(s): {', '.join(names[:6])}")

        def house():
            import house_rules
            for what in house_rules.apply(cfg):
                self.say(f"House rule applied: {what}")

        for what, chore in (("the login certificate", certificate), ("kit_paths.lua", kit_paths), ("the conquest simulator", conquest),
                            ("item stacks", stacks), ("equipment rows", equipment), ("the house rules", house)):
            try:
                chore()
            except Exception as e:
                self.say(f"Could not see to {what} ({e}) - starting anyway.")

    def is_local(self):
        """How prepare_world decides whether the hosting address is this machine's. A world set to "direct" is reached
        through an address its machine may not own (a rented server behind its provider's address translation, a
        home PC behind a router), so the address in its settings is taken as it is."""
        return (lambda _address: True) if self.settings.get("mode") == "direct" else None

    def cloud_chat(self):
        """True when the bots chat through Google here (crowds/ai_cloud.py is set up with a key)."""
        try:
            sys.path.insert(0, os.path.join(self.kit, "crowds"))
            import ai_cloud
            return bool(ai_cloud.ready(self.kit)) and bool(self.rates.get("bots") or self.rates.get("crowds"))
        except Exception:
            return False

    def apply_rates(self):
        try:
            # the bots' AI chat is on exactly when its helper will run (else the server would wait for answers in vain)
            for note in core.apply_rates(self.cfg["server_dir"], dict(self.rates, coop_hosting=self.hosting, crowds_chat_ai=self.cloud_chat())):
                self.say(note)
        except Exception as e:
            self.say(f"Could not apply the rates ({e}) - starting with the server's normal settings.")
        # (2026-11-25) the HARDCORE server files, as PLAY writes them: this world's hardcore switches, open or not, and on
        # The Hub whether visitors play at the rates they bring from home (hardcore.json "visitor_rates")
        try:
            import launcher_hardcore
            import launcher_passport as pp
            name = ""
            try:
                conn = pp.connect(self.cfg)
                try:
                    name = pp.world_identity(conn)["name"]
                finally:
                    conn.close()
            except Exception:
                pass
            is_open = bool(self.hosting and self.settings.get("open"))
            for problem in launcher_hardcore.write_server_files(self.kit, self.cfg["server_dir"], is_open, name):
                self.say(problem)
            if is_open and launcher_hardcore.settings(self.kit).get("visitor_rates"):
                self.say("Visitors play at the rates they bring from home.")
        except Exception as e:
            self.say(f"Could not write the Hardcore files ({e}).")

    def spawn(self, name):
        return core.start_server(self.cfg, name, self.logs)

    def wait_for_map(self):
        """Waits for the map server to say it is ready (as PLAY does: as long as its log keeps growing, at most ten
        minutes). WorldError when a server stops meanwhile."""
        cfg, start = self.cfg, self.clock()
        offset, grew, last_size = 0, self.clock(), core.log_size(self.logs, "xi_map")
        while self.clock() - start < cfg.get("map_max_wait_seconds", 600):
            if self.stopping.is_set():
                raise WorldError("Stopped while the world was loading.")
            self.check_servers()
            ready, offset = core.map_ready_from(self.logs, offset)
            if ready:
                break
            size = core.log_size(self.logs, "xi_map")
            if size != last_size:
                last_size, grew = size, self.clock()
            if self.clock() - start > cfg.get("map_wait_seconds", 25) and size == 0:
                break                                    # the log cannot be read: carry on after the fixed wait
            if self.clock() - grew > 90:
                break                                    # the log has stopped moving: carry on instead of waiting for ever
            self.sleep(1)
        return int(self.clock() - start)

    def check_servers(self):
        for name, proc in self.procs.items():
            if proc.poll() is not None:
                raise WorldError(f"{name} stopped by itself. The last lines of its log:\n" + core.tail(os.path.join(self.logs, name + ".log")))

    def start_helpers(self):
        script = os.path.join(self.kit, "ah_sim.py")
        if self.rates.get("ah_sim", self.cfg.get("ah_sim", False)) and os.path.exists(script):
            try:
                log = open(os.path.join(self.logs, "ah_sim.log"), "wb")
                self.logfiles.append(log)
                self.helpers["ah_sim"] = subprocess.Popen(core.py_cmd(script, "run"), cwd=self.kit, stdout=log, stderr=subprocess.STDOUT,
                                                          creationflags=core.NO_WINDOW)
                self.say("Auction house simulator started.")
            except Exception as e:
                self.say(f"Auction house simulator did not start: {e}")
        script = os.path.join(self.kit, "crowds", "crowd_chat_ai.py")
        if self.cloud_chat() and os.path.exists(script):
            crowds = bool(self.rates.get("crowds") and self.rates.get("crowds_chat", True))
            try:
                log = open(os.path.join(self.logs, "crowd-chat-ai.log"), "wb")
                self.logfiles.append(log)
                args = core.py_cmd(script, "--server", self.cfg["server_dir"], *([] if crowds else ["--bots-only"]), unbuffered=True)
                self.helpers["chat_ai"] = subprocess.Popen(args, cwd=os.path.dirname(script), stdout=log, stderr=subprocess.STDOUT,
                                                           creationflags=core.NO_WINDOW)
                self.say("Bot chat through Google's Gemma started.")
            except Exception as e:
                self.say(f"Bot chat helper did not start: {e}")

    def open_door(self):
        """The co-op service visitors' launchers talk to."""
        self.host = co.Host(self.cfg, self.kit, self.settings, log=self.say)
        try:
            self.host.start()
        except OSError as e:
            raise WorldError(f"Could not listen for visitors on port {self.settings['port']} ({e}). Is a launcher open on this install?")
        who = "anyone with its link" if self.settings.get("open") else "friends"
        self.say(f"Co-op: this world is open to {who} at {self.settings['address']}.")
        if self.settings.get("open"):
            link = self.host.link()
            self.link = link or ""
            self.say(f"World link: {link}" if link else "No world link yet: the game server has made no certificate.")
        self.clear_asked()

    # ----- what is asked by hand about a visitor (launcher_world.py kick ...): a small file the running world answers -----
    def clear_asked(self):
        """When the door opens: both folders are there and empty, so nothing asked of an earlier run is done now."""
        for name in (ASKED_DIR, ANSWERS_DIR):
            folder = os.path.join(self.logs, name)
            try:
                os.makedirs(folder, exist_ok=True)
                for old in os.listdir(folder):
                    keep._remove(os.path.join(folder, old))
            except OSError:
                pass

    def answer_asked(self):
        """Does what was asked by hand since the last look, oldest first, and leaves an answer for each."""
        folder = os.path.join(self.logs, ASKED_DIR)
        try:
            names = sorted(name for name in os.listdir(folder) if name.endswith(".json"))
        except OSError:
            return
        for name in names:
            path = os.path.join(folder, name)
            asked = keep._read_json(path)
            keep._remove(path)
            try:
                waited = time.time() - float(asked["at"])
            except (TypeError, KeyError, ValueError):
                continue
            if not -5 <= waited <= ANSWER_WAIT_SECONDS:
                continue                         # (nobody waits for it any more: it is not done behind their back)
            try:
                code, lines = moderate(self.host, asked)
            except Exception as e:
                code, lines = 1, [f"That did not work ({type(e).__name__}: {e}). Look with 'who' and 'bans' at what is true now."]
            if asked.get("do") != "hello":
                self.say(f"By hand ({asked.get('do')}): " + " ".join(lines))
            try:
                keep._write_json(os.path.join(self.logs, ANSWERS_DIR, name), {"code": code, "lines": lines})
            except OSError:
                pass

    # ----- start, run, stop -----
    def start(self):
        if not self.take_lock():
            raise WorldError("A launcher or another world is already running on this install. Close it first.")
        self.state, self.since, self.problem = "starting", self.clock(), ""
        self.write_status()
        self.say("Cleaning up old processes...")
        self.clean_up()
        self.database()
        self.keeper.at_start()                   # an update that is waiting goes in now (or one that failed comes out)
        self.chores()
        try:
            self.hosting = bool(co.prepare_world(self.cfg, self.kit, self.settings, log=self.say, is_local=self.is_local()))
        except Exception as e:
            self.hosting = False
            self.say(f"Co-op: could not set up hosting ({e}) - starting as a private world.")
        self.say("Applying the rules...")
        self.apply_rates()
        for name in core.SERVERS:
            if self.stopping.is_set():
                raise WorldError("Stopped while the servers were starting.")
            self.say(f"Starting {name}...")
            proc, log = self.spawn(name)
            self.procs[name] = proc
            self.logfiles.append(log)
            self.sleep(SERVER_GAP_SECONDS)
        self.say("Loading the world (this can take a minute or two)...")
        seconds = self.wait_for_map()
        self.say(f"The world is ready ({seconds} seconds).")
        if core.map_ready(self.logs):
            self.keeper.ready()                  # (an update that was being tried is in for good)
        if self.hosting:
            self.open_door()
        self.start_helpers()
        self.state, self.since = "running", self.clock()
        self.write_status()

    def tick(self):
        """One look at the running world. WorldError when a game server has stopped by itself."""
        self.check_servers()
        now = self.clock()
        if self.host is not None:
            self.answer_asked()                  # (who was kicked or banned by hand: launcher_world.py kick ...)
        if self.host is not None and now - self.last_guests >= GUESTS_SECONDS:
            self.last_guests = now
            try:
                self.host.guests()               # (a banned visitor still in the game is asked out again)
                self.host.sweep()                # (once a day: kept places whose time is up)
            except Exception as e:
                self.say(f"Co-op: could not look at the visitors ({type(e).__name__}: {e}).")
        if now - self.last_status >= STATUS_SECONDS:
            self.write_status()
        self.keeper.tick(now)                    # (keep.Restart when the world has to stop for an update)

    def visitors_in_game(self):
        if self.host is None:
            return []
        try:
            return [g for g in self.host.guests() if g["state"] == "active" and g["online"]]
        except Exception:
            return []

    def stop(self, grace=STOP_GRACE_SECONDS):
        """Stops everything this world started. Visitors in the game are told first and given `grace` seconds; their
        characters stay in the world."""
        if self.state in ("stopped", "stopping"):          # (also: a start that was refused because the install is taken)
            return
        was_running = self.state == "running"
        self.state = "stopping"
        self.write_status()
        if was_running and grace > 0 and self.visitors_in_game():
            self.say("Visitors are in the game: they are told, and given a minute to log out.")
            co.announce(self.cfg.get("server_dir"), CLOSING_LINE)
            end = self.clock() + grace
            while self.clock() < end and self.visitors_in_game():
                self.sleep(2)
        self.say("Stopping...")
        for proc in self.helpers.values():
            core.kill_tree(proc)
        self.helpers.clear()
        if self.host is not None:
            self.host.stop()
            self.host = None
        for proc in self.procs.values():
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        for proc in self.procs.values():         # they save to the database as they end
            try:
                proc.wait(timeout=20)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self.procs.clear()
        for handle in self.logfiles:
            try:
                handle.close()
            except Exception:
                pass
        self.logfiles = []
        try:
            if self.rates.get("conquest_sim", True):
                self.script("conquest_sim.py", "stamp", timeout=90)
        except Exception:
            pass
        try:
            self.stop_database()
        except Exception as e:
            self.say(f"The database did not stop cleanly ({e}).")
        self.state, self.since = "stopped", self.clock()
        self.write_status()
        self.release_lock()
        self.say("Stopped.")

    def run(self):
        """Starts the world and stays with it. Returns the exit code: 0 after a stop that was asked for, 1 after a
        start that failed or a game server that stopped by itself, 75 (keep.RESTART_CODE) when it has to be started
        again for an update, 78 (keep.STUCK_CODE) when a person has to look before it is started again."""
        code = 0
        try:
            self.start()
            while not self.stopping.is_set():
                self.tick()
                self.stopping.wait(TICK_SECONDS)
        except keep.Restart as e:
            code = keep.RESTART_CODE
            self.say(str(e))
        except keep.Stuck as e:                  # an update that could not be taken back: not started again by itself
            self.problem, code = str(e), keep.STUCK_CODE
            self.say(str(e))
        except WorldError as e:
            self.problem, code = str(e), 1
            self.say(str(e))
        except Exception as e:                   # anything unforeseen: say what, stop cleanly, and let the service start it again
            self.problem, code = f"{type(e).__name__}: {e}", 1
            self.say(f"The world ran into a problem ({self.problem}).")
        finally:
            self.stop(grace=STOP_GRACE_SECONDS if code in (0, keep.RESTART_CODE) else 0)
        return code


def read_status(kit):
    try:
        with open(os.path.join(kit, "logs", STATUS_FILE), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def describe(status, now=None):
    """A few lines for a person from what the world last wrote."""
    if not status:
        return "No world has run on this install yet."
    now = now or time.time()
    age = int(now - status.get("updated", 0))
    lines = [f"State: {status.get('state', '?')}" + (f" (last heard from {age} seconds ago)" if status.get("state") == "running" else "")]
    if status.get("state") == "running" and age > 3 * STATUS_SECONDS:
        lines.append("It has not written its state for a while: it may have been stopped without a chance to say so.")
    versions = status.get("versions") or {}
    lines.append(f"Version: launcher {versions.get('kit', '?')}, server {versions.get('server', '?')}")
    if status.get("hosting"):
        lines.append(f"{'Open to everyone' if status.get('open') else 'Open to friends'} at {status.get('address')} port {status.get('port')}: "
                     f"{status.get('visitors', 0)} of {status.get('max_guests', '?')} visitors, {status.get('online', 0)} in the game")
    else:
        lines.append("Private: nobody can visit.")
    if status.get("link"):
        lines.append("World link: " + status["link"])
    backup = status.get("backup") or {}
    if backup.get("last"):
        lines.append("Database last saved: " + time.strftime("%Y-%m-%d %H:%M", time.localtime(backup["last"])) + f" ({backup.get('file')})")
    elif "backup" in status:
        lines.append("Database not saved yet (it is saved every night).")
    if backup.get("problem"):
        lines.append("Backup problem: " + str(backup["problem"]))
    update = status.get("update") or {}
    if update.get("state") == "planned":
        lines.append(f"Update: {update.get('to')} is downloaded; the world restarts for it"
                     + (" at " + time.strftime("%H:%M", time.localtime(update["at"])) if update.get("at") else " now") + ".")
    elif update.get("state") in ("pending", "applying", "applied", "trying"):
        lines.append(f"Update: {update.get('to')} is going in ({update['state']}).")
    elif "update" in status:
        lines.append("Updates: " + ("installed by itself (full releases)." if update.get("auto") else "not installed by itself (launcher_world.py update)."))
    for name in update.get("waiting") or []:
        lines.append(f"Update: {name} is out; its files for this system are not up yet.")
    if update.get("problem"):
        lines.append("Update problem: " + str(update["problem"]))
    if status.get("problem"):
        lines.append("Last problem: " + str(status["problem"]).splitlines()[0])
    return "\n".join(lines)


class Database:
    """The database for a command given by hand: started when it is not running, and stopped again afterwards."""

    def __init__(self, cfg):
        self.cfg, self.proc = cfg, None

    def __enter__(self):
        if self.cfg.get("mariadb_dir"):
            import launcher_setup
            self.proc = launcher_setup.start_portable(self.cfg)
        return self

    def __exit__(self, *_problem):
        if self.proc is not None:
            import launcher_setup
            launcher_setup.stop_portable(self.cfg)
            try:
                self.proc.wait(timeout=30)
            except Exception:
                pass


def world_running(kit):
    """True when a launcher or a world holds this install (Linux: the lock in logs; Windows: the launcher's mutex)."""
    probe = World.__new__(World)
    probe.kit, probe.lock = kit, None
    if not World.take_lock(probe):
        return True
    World.release_lock(probe)
    return False


def shown(guest):
    """A visitor's name as this world sees it, with its own name when it visits under another one."""
    local, name = guest.get("local") or guest["name"], guest["name"]
    return local if local == name else f"{local} ({name} at home)"


def find_visitor(rows, text):
    """The rows a person means by a name or by the number 'who' and 'places' show (the character's number here)."""
    text = str(text).strip().lstrip("#")
    if text.isdigit():
        return [row for row in rows if int(row["charid"]) == int(text)]
    return [row for row in rows if text.lower() in (str(row.get("local") or "").lower(), str(row["name"]).lower())]


def moderate(host, asked):
    """One thing asked by hand about a visitor, done on the world's own door (launcher_coop.Host), so that a banned
    visitor is kept out the same way as from the CO-OP page. Returns (exit code, lines for the person who asked)."""
    do, guest_id = asked.get("do"), str(asked.get("guest") or "")
    if do == "hello":                            # ('who' asks this, to say whether kick and ban would get through)
        return 0, ["The running world answers: kick and ban get through."]
    if do == "kick":
        for guest in host.guests():
            if guest["guest_id"] == guest_id and guest["state"] == "active":
                if not guest["online"]:
                    return 1, [f"{shown(guest)} is not in the game right now. Nothing was done."]
                host.kick(guest_id)
                return 0, [f"{shown(guest)} is being logged out of the game (within a few seconds). It can log in again; a ban keeps it out."]
        return 1, ["That visitor is not here any more. Nothing was done."]
    if do == "ban":
        reason, address = str(asked.get("reason") or "")[:200], bool(asked.get("address"))
        name = host.ban(guest_id, reason=reason, with_address=address)
        if name is None:
            return 1, ["That visitor is not known here any more. Nothing was done."]
        lines = [f"{name} is banned from this world: it is put out of the game and cannot come back. Its character can still go home."]
        if address:
            done = any(ban["kind"] == "ip" and ban["reason"] == reason for ban in host.bans())
            lines.append("The address it last used is banned too." if done else "No address is known for it, so only its launcher is banned.")
        return 0, lines
    if do == "unban":
        lifted = []
        for kind, value in asked.get("bans") or []:
            host.unban(str(kind), str(value))
            lifted.append(f"the address {value}" if kind == "ip" else f"the launcher {str(value)[:12]}...")
        return (0, ["Ban lifted: " + ", ".join(lifted) + "."]) if lifted else (1, ["Nothing to lift."])
    if do == "forget":
        if host.forget(guest_id):
            return 0, ["That kept place is given up: the character it held here is gone, with its auction listings and delivery box."]
        return 1, ["That is not a kept place (a visitor who is here is sent home, not forgotten). Nothing was done."]
    return 2, ["The world does not know that request."]


def ask_world(kit, asked, wait=None, sleep=time.sleep):
    """Hands one request to the running world and waits for its answer. Returns (exit code, lines)."""
    wait = ANSWER_WAIT_SECONDS if wait is None else wait
    folder = os.path.join(kit, "logs", ASKED_DIR)
    if not os.path.isdir(folder):
        return 1, ["The running world does not take this command: it was started before the command existed, or it "
                   "runs private. Restart the world."]
    name = f"{int(time.time() * 1000)}-{os.getpid()}-{os.urandom(4).hex()}.json"
    answer = os.path.join(kit, "logs", ANSWERS_DIR, name)
    try:
        keep._write_json(os.path.join(folder, name), dict(asked, at=time.time()))
    except OSError as e:
        return 1, [f"Could not hand that to the running world ({e}). Run the command as the world's own user."]
    until = time.time() + wait
    while time.time() < until:
        said = keep._read_json(answer)
        if said is not None:
            keep._remove(answer)
            return int(said.get("code", 1)), [str(line) for line in said.get("lines") or []]
        sleep(0.25)
    keep._remove(os.path.join(folder, name))
    return 1, ["The running world did not answer. Look with 'who' and 'bans' at what is true now, then ask again."]


def about_visitors(command, rest, kit, cfg, say=print, sleep=time.sleep):
    """who, kick, ban, bans, unban, places, forget: what the owner and the moderators do about a world's visitors
    when there is no launcher window. The lists are read from the database. What changes something is done by the
    running world itself (its door keeps a banned visitor out), or at once while the world is stopped."""
    options = [word for word in rest if word.startswith("--")]
    words = [word for word in rest if not word.startswith("--")]
    if ([o for o in options if not (command == "ban" and o == "--address")] or (command in USAGE) != bool(words)
            or (command in ("kick", "unban", "forget") and len(words) != 1)):
        say("launcher_world.py " + USAGE.get(command, command))
        return 2
    running = world_running(kit)
    if command == "kick" and not running:
        say("The world is not running: nobody is in the game.")
        return 1
    settings = co.load_settings(kit)
    with Database(cfg):
        try:
            conn = co.pp.connect(cfg)
            try:
                rows, kept, bans = co.pp.guest_list(conn, lockers=True), co.pp.locker_list(conn), co.pp.ban_list(conn)
            finally:
                conn.close()
        except Exception as e:
            say(f"The world's database could not be read ({type(e).__name__}: {e}).")
            return 1
        here = [guest for guest in rows if guest["state"] == "active"]
        if command == "who":
            say(f"Visitors here: {len(here)}, of them in the game: {len([g for g in here if g['online']])} "
                f"(at most {settings.get('max_guests')})." + ("" if running else " The world is not running."))
            for guest in here:
                say(f"  #{guest['charid']}  {shown(guest)}  {'in the game' if guest['online'] else 'not in the game'}  (arrived {guest['arrived'][:16]})")
            for guest in rows:
                if guest["state"] == "left":
                    say(f"  #{guest['charid']}  {shown(guest)}  has left: saved for its trip home, not picked up yet")
            say(f"Kept places: {len(kept)} ('places' lists them). Bans: {len(bans)} ('bans' lists them).")
            if not running:
                return 0
            code, lines = ask_world(kit, {"do": "hello"}, wait=HELLO_WAIT_SECONDS, sleep=sleep)
            say(lines[0] if code == 0 else "The running world did not answer: kick and ban would not get through right now. "
                                           "If this stays so, restart the world.")
            return 0 if code == 0 else 1
        if command == "places":
            say(f"Kept places: {len(kept)} (a place is cleared {co.pp.LOCKER_DAYS} days after the last visit).")
            for place in kept:
                say(f"  #{place['charid']}  {shown(place)}  last here {place['since'][:16]}  kept until {place['expires'][:10]}")
            return 0
        if command == "bans":
            say(f"Bans: {len(bans)}." + (" To lift one: launcher_world.py " + USAGE["unban"] if bans else ""))
            for ban in bans:
                what = f"address {ban['value']}" if ban["kind"] == "ip" else f"launcher {ban['value'][:12]}..."
                say(f"  {what}  {ban['reason'] or '(no note)'}  since {ban['since'][:16]}")
            return 0
        what = words[0]
        if command == "unban":
            low = what.lower()
            found = [ban for ban in bans if ban["value"] == what or (ban["kind"] == "key" and len(what) >= 6 and ban["value"].startswith(what))
                     or (ban["reason"] or "").lower() == low or (ban["reason"] or "").lower().startswith(low + ":")]
            if not found:
                say(f"No ban matches '{what}'. 'bans' lists them.")
                return 1
            asked = {"do": "unban", "bans": [[ban["kind"], ban["value"]] for ban in found]}
        else:
            found = find_visitor({"kick": here, "ban": rows, "forget": kept}[command], what)
            if not found:
                say({"kick": f"Nobody called '{what}' is here. 'who' lists the visitors.",
                     "ban": f"No visitor and no kept place is called '{what}'. 'who' and 'places' list them.",
                     "forget": f"No kept place is called '{what}'. 'places' lists them."}[command])
                return 1
            if len(found) > 1:
                say(f"More than one is called '{what}'. Say the number instead:")
                for guest in found:
                    say(f"  #{guest['charid']}  {shown(guest)}")
                return 1
            asked = {"do": command, "guest": found[0]["guest_id"]}
            if command == "ban":
                why = " ".join(words[1:]).strip()
                asked.update(reason=(found[0].get("local") or found[0]["name"]) + (": " + why if why else ""),
                             address="--address" in options)
        if running:
            code, lines = ask_world(kit, asked, sleep=sleep)
        else:
            code, lines = moderate(co.Host(cfg, kit, settings, log=lambda _line: None), asked)
    for line in lines:
        say(line)
    return code


def by_hand(argv, kit=HERE, say=print, sleep=time.sleep):
    """The owner's commands: backup, backups, restore, update, selftest, and the ones about visitors. Returns the exit code."""
    command, rest = argv[1], argv[2:]
    if command == "selftest":                    # (run by an update on the launcher it has just put in: can it run a world?)
        import launcher_passport, launcher_setup, launcher_update, launcher_world_setup      # noqa: F401, E401
        core.load_config(os.path.join(kit, "config.json"))
        say("world selftest ok")
        return 0
    cfg = core.load_config(os.path.join(kit, "config.json"))
    try:
        if command == "backups":
            found = keep.backups(kit)
            for item in found:
                say(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(item['time']))}  {item['bytes'] // (1024 * 1024):5d} MB  {item['path']}")
            if not found:
                say("No copies yet (backups/world).")
        elif command == "backup":
            with Database(cfg):
                keep.backup_now(cfg, kit, "by-hand", log=say)
        elif command == "restore":
            if len(rest) != 1:
                say("Say which copy: launcher_world.py restore <file> (launcher_world.py backups lists them).")
                return 2
            path = rest[0] if os.path.isabs(rest[0]) or os.path.exists(rest[0]) else os.path.join(keep.backup_folder(kit), rest[0])
            if world_running(kit):
                say("The world is running (or a launcher is open on this install). Stop it first: the database cannot be put back under it.")
                return 1
            keep.check_backup(path)
            with Database(cfg):
                keep.backup_now(cfg, kit, "by-hand", log=say)        # (what is there now is saved first)
                keep.restore(cfg, kit, path, log=say)
        elif command == "update":
            retry = "--retry" in rest
            if world_running(kit):
                keep.request(kit, "update", retry=retry)
                say("The running world looks for an update now. 'launcher_world.py status' shows what it found.")
                return 0
            if retry:
                keep._remove(keep.skip_path(kit))
            import launcher_thirdparty as tp
            found = keep.find_update(kit, cfg, tp._get)
            for name in found["waiting"]:
                say(f"{name} is out, but its files for this system are not up yet. Try again later.")
            if found["waiting"] or not (found["kit"] or found["server"]):
                say("Nothing to install.")
                return 0
            cache = keep.download(kit, found, tp._get, log=say)
            state = dict(found, state="pending", files=cache.files, texts=cache.texts, at=int(time.time()))
            state.pop("waiting", None)
            keep.save_state(kit, state)
            with Database(cfg):
                keep.apply(kit, cfg, state, log=say)
            say(f"Updated to {keep.tags(found)}. Start the world: it is taken back by itself if the world does not get ready with it.")
        elif command in VISITOR_COMMANDS:
            return about_visitors(command, rest, kit, cfg, say=say, sleep=sleep)
        else:
            say(__doc__)
            return 2
    except keep.KeepError as e:
        say(str(e))
        return 1
    return 0


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "status":
        print(describe(read_status(HERE)))
        return 0
    if command == "setup":
        import launcher_world_setup
        if "-h" not in argv and "--help" not in argv and world_running(HERE):
            print("The world is running (or a launcher is open on this install). Stop it first, then run the setup again.")
            return 1
        return launcher_world_setup.main(argv[2:], kit=HERE)
    if command in ("backup", "backups", "restore", "update", "selftest") + VISITOR_COMMANDS:
        return by_hand(argv)
    if command != "run":
        print(__doc__)
        return 2
    world = World(HERE)

    def asked_to_stop(_number, _frame):
        world.stopping.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), asked_to_stop)
    return world.run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
