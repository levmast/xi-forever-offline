#!/usr/bin/env python3
"""Installs the Tetra Master addon (art: Nalfey) and turns it on for your MAIN game window.

  python install_tetramaster.py

It copies C:\\FFXISOLO\\tetramaster into Ashita's addons folder and adds it to your main window's addon list (the same
list as the launcher's Addons tab, "Main window"). Nothing else in that list is changed, and the second window is not
touched. In the game: /tm opens the board. The server side is modules/custom/lua/tetramaster.lua (!tm).
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import launcher_core as core

SOURCE = os.path.join(HERE, "tetramaster")
NAME = "tetramaster"


def say(text=""):
    print(text, flush=True)


def install(cfg):
    if not os.path.isfile(os.path.join(SOURCE, NAME + ".lua")):
        raise RuntimeError("The tetramaster folder is missing from " + HERE + ".")
    if not os.path.isfile(os.path.join(SOURCE, "assets", "sprites", "graphics.png")):
        raise RuntimeError("Nalfey's art is missing (tetramaster\\assets\\sprites\\graphics.png).")
    ashita = cfg["ashita_dir"]
    boot = cfg.get("ashita_boot", "phoenixsolo.ini")
    if not os.path.isfile(os.path.join(ashita, "config", "boot", boot)):
        raise RuntimeError("I could not find your boot file " + boot + " in " + os.path.join(ashita, "config", "boot"))

    say("1. Installing the addon")
    dest = os.path.join(ashita, "addons", NAME)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(SOURCE, dest, dirs_exist_ok=True)
    say("   Installed to " + dest)

    say("2. Turning it on for the main window")
    manager = core.ScriptManager(ashita, boot)
    manager.prepare()
    if NAME in {a.lower() for a in manager.enabled("addon")}:
        say("   It was already on.")
    else:
        manager.set("addon", NAME, True)
        say("   Added to " + manager.path)
    say()
    say("DONE. Restart the server from the launcher, start the game and type  /tm  (or /addon load tetramaster if the game is already open).")
    return 0


def main():
    with open(os.path.join(HERE, "config.json"), "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    if "ashita_dir" not in cfg:
        raise SystemExit("config.json has no ashita_dir, so I can not find your Ashita folder.")
    return install(cfg)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - shown to the player
        say("ERROR: " + str(exc))
        sys.exit(1)
