# XI: Forever Offline on Linux and the Steam Deck (experimental)

The server, the database and the launcher run natively on Linux. The game itself (PlayOnline, FINAL FANTASY XI, Ashita
and our addons) is a Windows program and runs through Proton, which the launcher downloads and keeps inside its own
folder. Nothing is installed system-wide and nothing needs `sudo`, so it works on the Steam Deck's read-only system too.

## What you need
- A 64-bit Linux from 2022 or newer (SteamOS 3.5+, Bazzite, Fedora 37+, Ubuntu 22.04+, Arch, Mint 21+...).
- About 25 GB free: the game (about 16 GB), Proton and its runtime (about 2 GB), the server and the database.
- **FINAL FANTASY XI**, its `SquareEnix` folder (the one with `PlayOnlineViewer` and `FINAL FANTASY XI` in it). We never
  host Square Enix's files. It can come from a Windows PC (inside `C:\Program Files (x86)\PlayOnline`, copied to a USB stick
  or straight to the Linux machine), or from the game installed on Linux itself: the Steam version, or the official
  installer from playonline.com run through Proton or Wine. Update the game first (PlayOnline, once). (Thanks Sunie.)

## Install
1. Download `XI-Forever-Offline-Linux.tar.gz` and extract it where you want it (your home folder, or the SD card on a
   Deck). Steam Deck: do this in Desktop Mode.
2. Open the `XI Forever Offline` folder and run `XI-Forever-Offline`.
3. The setup asks for the game folder (the `SquareEnix` folder you copied), your world and an account, then downloads
   Ashita, the server, Proton and MariaDB. The first PLAY also downloads Proton's runtime (a few minutes).

On a Steam Deck the setup picks a small world, turns AI chat off (it needs a lot of memory) and sets the game to the
Deck's screen (1280 x 800).

## Steam Deck: play from Game Mode
Launcher: **SYSTEM > Linux > Add to Steam and the menu**, then in Steam's window tick XI: Forever Offline and press
*Add Selected Programs*. In Game Mode start it from your library; press PLAY with the touchscreen or the trackpad.
For the game itself, a controller layout with the trackpads as mouse works well (FFXI's own gamepad settings apply too).

## If something goes wrong
- Logs are in the `logs` folder. Send `logs/ashita.log`, `logs/proton-setup.log` and `logs/xi_map.log` with a report.
- SYSTEM > Linux > **Write Proton logs** makes Proton write `logs/steam-*.log` too (big, only while you need it).
- SYSTEM > Linux > **Redo the game's Proton setup** registers the game in Proton again at the next PLAY.
- `config.json` (advanced): `"proton_env": {"NAME": "value"}` passes extra Proton settings; `"linux_sandbox": true`
  uses Ashita's Sandbox plugin to find the game instead of Proton's registry.

Not on Linux yet: the Shaders page (dgVoodoo/ReShade) and the GET TAILSCALE button (co-op on your own network works).
