"""Puts Ventures into the server and the kit (python dev\\ventures\\apply_ventures.py --server C:\\ffxi-local\\server).

  * copies squad_ventures.lua into <server>/modules/custom/lua/
  * squad.lua: a mate away on a venture can't be called; a look every 20 s while you play (send-offs, homecomings)
  * build_release.ps1 / .sh: launcher_ventures in the packaged launcher
Every file changed gets a .before-ventures backup first. Safe to run twice.
"""
import argparse
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, "..", ".."))
MARK = "(2026-11-25) Ventures"


def patch(path, edits):
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    if MARK in text:
        print(f"{os.path.basename(path)}: already done")
        return
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit(f"{os.path.basename(path)}: anchor found {text.count(old)} times, nothing changed:\n{old}")
    backup = path + ".before-ventures"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    for old, new in edits:
        text = text.replace(old, new)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"{os.path.basename(path)}: done")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    a = ap.parse_args(argv)
    lua = os.path.join(a.server, "modules", "custom", "lua")
    shutil.copy2(os.path.join(HERE, "squad_ventures.lua"), os.path.join(lua, "squad_ventures.lua"))
    print("squad_ventures.lua: copied")
    nl = "\r\n" if b"\r\n" in open(os.path.join(lua, "squad.lua"), "rb").read(4000) else "\n"
    j = lambda s: s.replace("\n", nl)
    patch(os.path.join(lua, "squad.lua"), [
        (j("local function callMate(player, mate)\n"),
         j("local function callMate(player, mate)\n"
           "    -- (2026-11-25) Ventures: a mate out on a venture from the XIFO app can't be called (squad_ventures.lua)\n"
           "    if type(xi.squad.ventures) == 'table' then\n"
           "        local away = xi.squad.ventures.away(player, mate)\n"
           "        if away then\n"
           "            say(player, away)\n"
           "            return\n"
           "        end\n"
           "    end\n\n")),
        (j("            pcall(xi.squad.shell.onGameIn, player, zoning) -- (mates on your linkshell: squad_shell.lua)\n        end\n"),
         j("            pcall(xi.squad.shell.onGameIn, player, zoning) -- (mates on your linkshell: squad_shell.lua)\n        end\n"
           "        -- (2026-11-25) Ventures: send-offs and homecomings while you play (squad_ventures.lua)\n"
           "        pcall(function()\n"
           "            if xi.squad.ventures == nil then\n"
           "                xi.squad.ventures = require('modules/custom/lua/squad_ventures')\n"
           "            end\n"
           "            xi.squad.ventures.onGameIn(player, GetSquad, SquadDismissMate, say)\n"
           "        end)\n")),
    ])
    ps1 = os.path.join(KIT, "build_release.ps1")
    if os.path.exists(ps1):
        patch(ps1, [('"launcher_armory", "launcher_armory_gui"', '"launcher_armory", "launcher_armory_gui", "launcher_ventures" <# (2026-11-25) Ventures #>')])
    sh = os.path.join(KIT, "build_release.sh")
    if os.path.exists(sh):
        patch(sh, [("launcher_armory launcher_armory_gui", "launcher_armory launcher_armory_gui launcher_ventures")])
        with open(sh, encoding="utf-8") as f:
            if MARK not in f.read():
                with open(sh, "a", encoding="utf-8", newline="\n") as f2:
                    f2.write("# (2026-11-25) Ventures: launcher_ventures added to the module list above\n")


if __name__ == "__main__":
    sys.exit(main())
