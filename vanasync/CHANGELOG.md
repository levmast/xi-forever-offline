# Changelog

## 0.1.2 (2026-11-26)

- New bundled track from J: "Choose to Fight (Special Battle Theme XIFO Exclusive)". It is an extra (battle-pack.json
  "extras"): seeded into the library, assigned to no slot, so Solo / Party / Alliance stay as they were.
- Titles no longer show the copy numbers a download adds at the end of a file name (" (1)", " (2) (1)"). Display only:
  files, ids and assignments are untouched. Words in brackets and numbers elsewhere in a name stay.
- Two more extras from J, his in-game versions of the app's tunes: "Just One More Cast" (fishing) and "Beyond the Next
  Hill" (Ventures). In the library only: nothing starts them by itself yet (the add-on does not report fishing).
- Add-on 0.1.2: the game's own battle theme no longer plays underneath (Zaltyz525, JØ). The game starts a new track at
  its own volume when a fight begins or ends, after the add-on's one request to fade; the request is now repeated
  once a second while VanaSync plays (four times a second for two seconds around a combat change), and full volume is
  asked for a few more times after the music is handed back. Not yet confirmed in the real game.
- `/vanasync open` (or `/vsync open`) in game brings the player window back after it was closed (Hexblood). The
  add-on's next three snapshots carry `"open": true`; the host keeps the request (`GameBridge.take_open()`, one window
  per ten seconds) and the launcher, which owns the window, opens it again within its five-second check. An app window
  that is still there is closed first, so two players never play at once. Not yet tried on Windows.

## 0.1.1 · Live in XI: Forever Offline (2026-11-25)

- Live game bridge: the XI: Forever Offline add-on `vanasync` sends combat, group size, alliance, zone and cutscene
  state over loopback UDP 8766 (`--game-port`, 0 turns it off). `GET /api/game` gives the player the latest state;
  the simulator inputs are locked while the game is live.
- Ownership handshake: the player posts `POST /api/owner` while it really plays one of its own tracks; each UDP reply
  tells the add-on, which fades the game's music out with the client's music-volume command (0x060) only then. Silence
  for 2 s (window closed, crash) gives the music back to the game.
- Live mode (`/?live=1`) plays only VanaSync's own tracks: the game itself plays the "native" music. A fresh profile
  starts in Resonance, and audio is enabled at start because the launcher opens the window with autoplay allowed.
- Tests: `tests/test_bridge.py`.

## 0.1.0 · Battle Resonance

- Added the midnight-blue and antique-gold local player and persistent layout controls.
- Added battle selection and overrides, five-second grace, soundtrack modes, crossfade, optional shared position and fallback.
- Added stable filename-driven catalog with rename tracking.
- Added a separate album queue with transport, checkpoints and optional battle interruption. Simulator cutscenes have priority.
- Included the three supplied battle mixes with SHA-256 verification and first-run assignments.
- Added the Windows launcher, test suite and native integration handoff.
