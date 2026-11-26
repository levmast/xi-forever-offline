# Testing

Run these from the extracted package root.

- `node --test tests/*.test.js`
- `python -m unittest discover -s tests -v`
- `node tests/browser-smoke.mjs <your-reference.mp3>`

The Node suite uses a deterministic media stub for cancellation, gain overlap, position and deck cleanup. The Python suite isolates the catalog and loopback host. The Edge smoke suite uses Node 22+, an installed Edge browser, a temporary profile and an authorized local MP3 for reference scenarios. The optional second argument is an output PNG. Override executable paths with VANASYNC_EDGE and VANASYNC_PYTHON.

## Manual simulator check

1. Launch in a fresh profile and verify the preassigned battle mixes. Try all automatic group branches and force an override during battle.
2. Supply local references for Vanilla and exploration. Switch modes, time grace, re-engage quickly and check the fade and position by listening.
3. Remove or replace a copied track in the test catalog. Verify reference recovery and emergency restore.
4. Import two local album files, verify order, zone continuity, transport, resume and cutscene priority.
5. Drag and lock the player, change scale and opacity, check quick settings and keys, and reload. Export diagnostics.
6. Rename a local catalog file including Japanese characters. Verify the name updates and the assignment persists.
7. Check [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) and report native evidence separately.
