# Gambatte libretro core (shipped with XI: Forever Offline)

Gambatte is a Game Boy / Game Boy Color emulator; this is its libretro core, by the Gambatte and libretro teams:
https://github.com/libretro/gambatte-libretro (documentation: https://docs.libretro.com/library/gambatte/).

`cores/gambatte_libretro.dll` is libretro's own 32-bit Windows build from their build server
(https://buildbot.libretro.com/nightly/windows/x86/), downloaded on 2026-10-27. Nothing in it was changed by us.

Why it ships with the kit: the launcher used to download whatever build was newest on the day of the install, and a
newer build crashed the Crystal Boy add-on for a player right after a game loaded. This is the build the add-on was
made and tested with, so everyone gets the same one.

License: GNU General Public License, version 2 (https://www.gnu.org/licenses/old-licenses/gpl-2.0.html). The source
code is at https://github.com/libretro/gambatte-libretro.
