"""VanaSync (2026-11-25, the user): JØ's battle music player (VanaSync by JØ × NOX) in the game.

Off by default: it is the add-on "vanasync" on OPTIONS > Addons. While that add-on is switched on and the world runs,
the launcher runs JØ's VanaSync host (<kit>/vanasync/server.py, loaded from disk, Python standard library only) on
127.0.0.1:8765 and opens its player in a small window. The add-on sends the game's state (combat, group size,
alliance, zone, cutscene) to the host over loopback UDP 8766; the player picks the Solo, Party or Alliance mix.
While the player really is playing one of its own tracks the add-on fades the game's music out (client packet 0x060,
sound effects untouched) and fades it back in when it stops, fails or the window is closed.

Nothing goes online. Imported tracks and settings live in %LOCALAPPDATA%\\VanaSync (JØ's default).
No tkinter here. Tests: dev/launcher-tests/test_vanasync.py.
"""
import importlib.util
import os
import subprocess
import threading
import webbrowser

FOLDER = "vanasync"          # in the kit: JØ's VanaSync (server.py, app/, battle-pack/, battle-pack.json)
ADDON = "vanasync"           # the Ashita add-on (addons-src/vanasync)
PORT, GAME_PORT = 8765, 8766
URL = f"http://127.0.0.1:{PORT}/?live=1"


def addon_on(ashita, boot_name):
    """True while the vanasync add-on is switched on in the launcher's script."""
    try:
        import launcher_core as core
        return ADDON in core.ScriptManager(ashita, boot_name).enabled("addon")
    except Exception:
        return False


def load_server(kit):
    """JØ's server.py as a module, straight from the kit folder (it stays his file, unchanged by the launcher)."""
    path = os.path.join(kit, FOLDER, "server.py")
    spec = importlib.util.spec_from_file_location("vanasync_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_edge():
    """Microsoft Edge (on every Windows 10/11 PC), else Chrome: both can open a page as its own app window."""
    places = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if root:
            places.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
            places.append(os.path.join(root, "Google", "Chrome", "Application", "chrome.exe"))
    return next((p for p in places if os.path.isfile(p)), None)


def window_command(browser, data_dir):
    """An app window with its own profile, so the autoplay switch applies even when Edge is already open."""
    return [browser, f"--app={URL}", "--autoplay-policy=no-user-gesture-required",
            f"--user-data-dir={os.path.join(data_dir, 'window')}", "--no-first-run",
            "--no-default-browser-check", "--window-size=440,720"]


class Player:
    """The host thread plus the player window, for one world session."""

    def __init__(self, kit, log=print, open_window=True):
        self.log = log
        self.window = None
        mod = load_server(kit)
        self.data = mod.DEFAULT_DATA
        self.server = mod.Server(PORT, self.data, bundled=True, game_port=GAME_PORT)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        if open_window:
            self.open_window()

    def open_window(self):
        browser = find_edge()
        if browser:
            os.makedirs(self.data, exist_ok=True)
            self.window = subprocess.Popen(window_command(browser, str(self.data)),
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.log("VanaSync: battle music player opened.")
        else:
            webbrowser.open(URL)
            self.log("VanaSync: player opened in your browser; click Enable audio once.")

    def close(self):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        if self.window is not None and self.window.poll() is None:
            try:
                self.window.terminate()
            except Exception:
                pass
        self.window = None


def tick(app_state, kit, ashita, boot_name, running, log=print):
    """Called every few seconds by the launcher. app_state is a dict the launcher keeps between calls.
    Starts the player when the add-on is on and the world runs, closes it when either stops. One failed start per
    world session is enough (a port in use, missing files): it is not retried until the world starts again."""
    want = bool(running) and addon_on(ashita, boot_name) \
        and os.path.isfile(os.path.join(kit, FOLDER, "server.py"))
    player = app_state.get("player")
    if want and player is None and not app_state.get("failed"):
        try:
            app_state["player"] = Player(kit, log)
        except OSError as e:
            app_state["failed"] = True
            log(f"VanaSync: could not start ({e}). Is another VanaSync already open?")
        except Exception as e:
            app_state["failed"] = True
            log(f"VanaSync: could not start ({e}).")
    elif not want and player is not None:
        player.close()
        app_state.pop("player", None)
    if not running:
        app_state.pop("failed", None)


def stop(app_state):
    player = app_state.pop("player", None)
    if player is not None:
        player.close()
