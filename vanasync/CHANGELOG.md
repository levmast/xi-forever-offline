# Changelog

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
