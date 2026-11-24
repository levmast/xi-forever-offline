# Revamped shells and the Revamped switch (v0.3.3 baseline)

Branch `v033/revamped-shells`, based on tag v0.3.2. Companion server branch: `v033/revamped-hooks` in xi-forever-offline-server.

## What this is, in plain words

Gambits Revamped and Squads Revamped are separate packages that come after this kit. This branch only prepares the ground so they plug in without anyone editing files by hand. It adds no feature a player can see by itself.

1. **Two shell add-ons**, `GambitsRevamped` and `SquadsRevamped`, installed by the kit into Ashita's `addons` folder. A shell loads silently: it draws nothing, registers no command, prints nothing. It only reads the saved Revamped switch. When a Revamped package is installed over a shell, the package's files replace the shell's (same names, same layout) and the launcher never copies a shell back over a package.
2. **One saved switch** both the game and the launcher read and write: `<Ashita>\config\addons\revamped\choice.txt` (`asked=1`, `use_revamped=1` or `0`).
3. **The first-load question**, shown only when a Revamped package (not just a shell) is present and nothing was answered yet: "Turn off the old Squads / old Gambits and use the Revamped versions?" Yes saves the choice, switches the old Squads window (`squadpanel`) and the old Gambits add-on (`Gambits`) off (kept on disk, never deleted) and uses Revamped now. No changes nothing and the Revamped Settings button switches later. With only shells installed it never appears.

What it prepares: Gambits Revamped (the full Gambits editor and engine) and Squads Revamped (the one-window Squads panel) both read the same switch, so the player answers once and both agree with the launcher.

## Files touched

| File | Change |
|---|---|
| `addons-src/GambitsRevamped/` (`GambitsRevamped.lua`, `rv_switch.lua`) | new shell |
| `addons-src/SquadsRevamped/` (`SquadsRevamped.lua`, `rv_switch.lua`) | new shell, same `rv_switch.lua` byte for byte |
| (launcher side) | `launcher_revamped.py` and the launcher hooks live on branch `v033/launcher` (SirTanta/xi-forever-offline): it installs these shells, loads them once, reads and writes the same `choice.txt`, and drops the old add-ons from the start script after a Yes. This branch is the game side only. |
| `dev/revamped-tests/test_revamped_shells.py` | tests (Lua through lupa: silent, no command, reads the switch, question only with a package) |

## Turn it off or revert

- Switch a shell off: OPTIONS > Addons, untick GambitsRevamped / SquadsRevamped (or delete the two `/addon load ...Revamped` lines from `Ashita\scripts\xiforever.txt`). Nothing else depends on them.
- Undo a Yes: delete `Ashita\config\addons\revamped\choice.txt`, then on OPTIONS > Addons tick `squadpanel` and `Gambits` again. The old add-ons were never deleted.
- Revert the branch: `git revert` the commit, or do not take it. The old add-ons do not read the switch, so nothing else changes.

## Test steps

Automated (no game needed): `python dev/revamped-tests/test_revamped_shells.py` expects `Ran 10 tests ... OK`.

In game (needs only the game and the launcher). Use a throw-away copy of the kit, not a live install.

A. Shells alone are silent
1. Start the launcher, then the game. Expected: Ashita's `addons` folder holds `GambitsRevamped` and `SquadsRevamped`, and OPTIONS > Addons lists both as "XI: Forever Offline".
2. In game, type `/addon list`. Expected: both are loaded.
3. Look at the screen and chat for a minute. Expected: no window, no chat line, no error. `/gambitsrevamped` and `/squadsrevamped` do nothing (no command is registered). The old Squads menu and old Gambits work exactly as before.

B. The question appears only with a package
4. Copy any file named `gr_editor.lua` (a stand-in for the package) into `addons\GambitsRevamped\`. Restart the game, wait about 5 seconds after you are in the world. Expected: a small "Revamped" window with Yes and No, text "Turn off the old Squads / old Gambits and use the Revamped versions?".
5. Press No. Expected: the window closes and never comes back; `config\addons\revamped\choice.txt` reads `asked=1` and `use_revamped=0`; the old Squads window and old Gambits stay on.
6. Delete `choice.txt`, restart, press Yes. Expected: the old Squads window and the old Gambits add-on unload at once (`/addon list` no longer shows `squadpanel` and `Gambits`), `choice.txt` reads `use_revamped=1`, the folders `addons\squadpanel` and `addons\Gambits` are still there.
7. Close the game, start the launcher, start the game again. Expected: `squadpanel` and `Gambits` are not in `scripts\xiforever.txt` any more and do not load; the question does not come back.
8. To undo: delete `choice.txt`, tick `squadpanel` and `Gambits` on OPTIONS > Addons, restart. Expected: old windows back.

C. Package over shell
9. Put a real package file set into `addons\SquadsRevamped\` (any `SquadsRevamped.lua` plus `sr_window.lua`). Start the launcher. Expected: the launcher does not copy the shell over it (your `SquadsRevamped.lua` is unchanged).

## Our proof

`Ran 10 tests ... OK` and `24 passed, 0 failed`, run on the v0.3.2 tree (the Lua tests run the real shell files in `lupa` against a fake Ashita, Lua 5.5, not LuaJIT). Not tested in the real game: steps A to C above are for Jon's test, not marked passed.

## Release note (draft, plain words)

Two empty add-ons, Gambits Revamped and Squads Revamped, are installed and loaded. They show nothing and do nothing until the Revamped packages are installed over them. When a package is there, the game asks once whether to turn off the old Squads window and the old Gambits and use the Revamped ones; the answer is saved and the launcher respects it. Nothing is deleted, and you can switch back from OPTIONS > Addons.
