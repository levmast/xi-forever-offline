# VanaSync 0.1.0 · Battle Resonance

**Player README** · JØ × NOX · XI Forever Offline prototype  
*Attune yourself to the world.*

VanaSync is the player. **MELODIES OF FOREVER** is the reimagined game soundtrack. **RESONANCE OF VANA’DIEL** is JØ’s separate 11-track narrative album.

## Start the battle prototype

1. Extract the entire ZIP. Use Windows, Python 3.11 or newer, and a desktop Chromium browser.
2. Run `Start-VanaSync.cmd` and keep the console open. The player opens at [127.0.0.1:8765](http://127.0.0.1:8765) by default.
3. Select **Resonance**, click **Enable audio**, and toggle **In combat** under **Game simulator**. The three battle mixes are preassigned on a clean browser profile.
4. Change **Group members** to hear the Solo mix for one member, Party for two through six, or Alliance for seven or more. The **Alliance flag** also selects Alliance. Use **Battle arrangement** to force a mix.
5. Use **Track assignments** to add your own optional Vanilla, exploration or cutscene test references. The prototype uses a five-second post-combat grace by default. **Restore native** requests a Vanilla reference in the simulator and holds that choice until you click **Retry audio**.

Drag the header to move the player. Right-click it for quick settings. The player settings include lock, scale, opacity and independent volumes. In the focused tab, F2 collapses the player, F3 toggles Album Mode and F8 requests restore. Shortcuts are configurable.

## Play RESONANCE OF VANA’DIEL

The album is delivered in a folder named `Resonance of Vana'diel`. Inside are eleven folders named `1` through `11`. Each contains the labeled song for that album position. For example, the file in folder `2` is played second. Folder numbers set the order, and each song’s filename supplies its display title.

In 0.1.0, use **RESONANCE OF VANA’DIEL** → **Add audio in selection order**. Add the song from folder `1`, then `2`, continuing through `11`. Check the visible playlist or use the arrow controls to put it in order. Remove duplicates if you’re replacing an earlier import. Click **Enter Album Mode** and enable audio if prompted. You can pause, skip, repeat the album or allow battles to interrupt it. Exiting Album Mode returns to your selected soundtrack. The album MP3s are a separate delivery from this ZIP.

## Region and theme packs

JØ will deliver new game soundtrack music as `Region / Zone / Track.mp3`. The developer’s AI checks the MP3s, maps them to the game’s zones, patches the player, and asks the operator whether to share an update with the community. Zone music should loop while you stay in the zone. Future themes, such as Moogle music, will come as separate packs. The [creator’s delivery instructions](handoff/DEV_AI_CONTINUATION.md) explain the full process.

The 0.1.0 prototype simulates game events and supports a single looping exploration reference. Automatic region import, per-zone playback, and native XI Forever Offline integration require developer work.

## Local settings and support

Imports copy files into `%LOCALAPPDATA%\VanaSync\tracks` by default. To rename an imported track, change its filename inside the same ID directory and keep one supported file in that directory. The displayed title updates after catalog refresh and keeps the filename exactly, minus its final extension. Settings and album position persist when you use the same browser profile and port. Use one player tab.

The importer accepts MP3, WAV, OGG, FLAC, M4A, Opus, AAC and WebM up to 128 MiB per input. Browser decode support varies. MP3 is the tested release format.

Run `python server.py --port 8765 --data <path> --no-open` for an isolated catalog. Add `--no-bundled` for a blank catalog. Use **Export diagnostics** in the simulator before closing the tab. Stop the host with Ctrl+C.

See [test results](TEST_REPORT.md), [known issues](KNOWN_ISSUES.md), and the [developer handoff](AI_HANDOFF.md).
