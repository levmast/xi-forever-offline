# VanaSync contributor instructions

- Keep the battle-first scope and independent MELODIES OF FOREVER and RESONANCE OF VANA’DIEL preferences.
- Keep policy in app/core.js, media lifecycle in app/audio.js, and UI wiring in app/app.js.
- Run the Node and Python suites after changes. Use the Edge smoke test for playback and UI changes.
- Label simulator, browser media and native game evidence explicitly.
- Use maintainer-approved, version-pinned interfaces and an isolated test install for native proof. Live game changes require explicit approval.
- Keep original game audio intact. Require positive confirmation for ownership of game BGM and release ownership on every failure or exit.
- Preserve exact imported filenames, stable IDs and explicit album order.
- Ship assets and links with verified provenance. Keep unavailable alternate tracks out of manifests.
- Keep personal playback data, test catalog, debug profiles and diagnostics out of release archives.
