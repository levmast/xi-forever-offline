# VanaSync continuation assignment

**For the XI Forever Offline developer’s AI**

Continue the project from this ZIP and the developer’s authorized working repository. The archive is the verified 0.1.0 battle simulator. Treat native game audio and per-zone music as work to implement and verify. Use the [independent audit](INDEPENDENT_TECHNICAL_AUDIT.md) as the first review, then use the findings to improve and maintain the build.

## Review the implementation and set it up

1. Run the simulator tests on the archived baseline. Identify the exact game and launcher version, approved extension points, and available isolated test client. Work in the approved repository on a reviewable branch.
2. Compare the current browser-side player and a maintainer-supported game add-on or sidecar. Use any other documented extension point that fits the pinned build. Compare reliable game-state input, ownership and restoration of game music, SFX and dialogue preservation, zone loop quality, installation, rollback, and maintenance. Record sources, known gaps and trade-offs. Implement the best supported option in the test environment, preserving the simulator as a fallback and test surface. Follow the [native development assignment](CODEX_NATIVE_DEVELOPMENT_ASSIGNMENT.md).
3. Prove the battle and native recovery paths before enabling live integration. Keep native features gated by capability. A missing facility, unavailable game state or failure should leave music under the game’s control. Keep original game audio intact and obtain approval before changing the live install.

## Creator deliverables

JØ will submit original soundtrack MP3s by region. The usual input shape is:

| Relative path pattern | Meaning |
| --- | --- |
| `<Region>/<Zone>/<Exact track filename>.mp3` | Original zone music for the game soundtrack |
| `<Separate theme pack>/<Theme>/<Exact track filename>.mp3` | Possible future theme music, such as a Moogle theme. Confirm the actual pack layout and trigger when delivered. |

Keep the original MP3 bytes unless JØ supplies a replacement master. Keep capitalization, punctuation, Japanese characters and the filename exactly. Display the filename without its final extension. The region submissions expand **MELODIES OF FOREVER**, the game soundtrack. **RESONANCE OF VANA’DIEL** remains the separate narrative album and retains its own track order and playback rules.

Use region and zone folder labels as source metadata. Map zones to stable, authoritative IDs from the pinned game build. Resolve aliases explicitly and keep track IDs stable across filename changes and intentional updates. When a zone has multiple tracks, use creator-confirmed roles or ordering. Ask about unmapped zones, collisions or ambiguous roles while continuing work on valid entries. Assign no day/night, weather, alternate or theme cue based on a filename guess.

## Each time an updated or new region pack arrives

1. **Inventory in isolation.** Inspect the layout and list actual files, additions, replacements, unchanged tracks and unresolved mappings. Verify each MP3 decodes through the end and record its SHA-256 and duration. Reject unsafe paths, ambiguous duplicates, corrupt files and unmapped entries from the patch. Keep the last known good mapping available.
2. **Patch the player.** Stage the assets and update the versioned soundtrack manifest/zone mappings, tests and release notes. Prefer one reusable importer and a data-driven patch for later regions. Keep slot assignments and user settings intact across updates. A repeated import with matching content should produce no duplicate assets or assignment changes. Publish the manifest and assets as a single validated update, with a backwards-compatible fallback and rollback path. For any real additions or replacements, deliver the patched build or reviewable PR, plus an install/rollback note. If the native integration is still blocked, implement and verify the mappings in the simulator and report the native limitation.
3. **Test the changed zones.** Check zone entry, repeat visits, regional boundaries, correct track and display name, extension removal, in-zone looping, combat grace, battle-to-zone restore, zoning during combat, protected cutscene yield, Album Mode, Off and Vanilla. Test missing/corrupt assets and rollback. Run the battle regression suite. Record what ran in the simulator versus the approved game test environment.
4. **Prompt the operator about the community update.** After processing each submission, show its status, region, added/updated zones, unresolved items, build or PR, and whether it is ready for review. For a validated build, provide a short post draft and explicitly ask the person operating the AI: **“The [region] pack is ready for review. Would you like to publish the VanaSync update for the XI Forever Offline community?”** For a blocked or unchanged submission, give the same status recap and ask whether the operator wants to update the community about that status. Label incomplete builds accordingly. Wait for authorization before posting, sharing the MP3s externally, deploying or editing the live install.

Keep future theme packs on a distinct manifest type or namespace, with the same validation, patch, verification and operator prompt. Add a theme only when the creator supplies the files and its cue trigger can be verified. A Moogle theme is a future example.

## Import RESONANCE OF VANA’DIEL

JØ will deliver the original album in the following structure. The folder names are literal track positions.

| Path | Album position |
| --- | --- |
| `Resonance of Vana'diel/1/<Labeled song>.mp3` | 1 |
| `Resonance of Vana'diel/2/<Labeled song>.mp3` | 2 |
| `Resonance of Vana'diel/…` | 3 through 9, each in its own numbered folder |
| `Resonance of Vana'diel/10/<Labeled song>.mp3` | 10 |
| `Resonance of Vana'diel/11/<Labeled song>.mp3` | 11 |

- Build an album-specific folder or archive import path. In the current simulator, the player adds the individual songs manually as described in the [player README](../README.md).
- Expect exactly one playable song in each numbered folder. Validate all eleven slots and the media bytes before activating an album import. Ask JØ to resolve missing, duplicate or ambiguous entries, and retain the existing playable album if validation fails.
- Order by the **numeric folder position** from 1 through 11, independent of filenames, file picker order, tags and lexicographic sorting. Preserve exact filenames and show their stems as titles. Keep album files and manifest separate from region and theme files.
- Make reimport of the same package idempotent. Handle replacements with an undo or rollback path. Preserve the saved position for an unchanged track. If the active track is replaced, keep its album slot and reset its playback time.
- Verify automatic order across 9 → 10 → 11, the repeat setting after track 11, Album Mode interruption and resume, and restoration of the selected soundtrack when the listener exits. Use the supplied masters and keep their original bytes. The album tracks use normal sequential playback and the listener’s repeat setting. Zone looping rules apply to the game cues.

## Required zone loop behavior

- Zone music repeats by default while the same zone and soundtrack preference remain active. Refreshes and unchanged zone snapshots preserve the existing playback instance.
- Start from full-track repeat for tracks supplied without loop points. MP3 decoder padding and the musical tail can make a repeat audible. Check the actual seam after import. For a track requiring a seamless seam, use creator-confirmed loop points or an approved loop-ready export and document the measured result. Avoid inventing loop points or rewriting the master.
- Track loop behavior per cue. Protected narrative cues and album tracks keep their own transport rules. Battle and cutscene interruptions must restore the current zone’s valid cue according to policy. Test interrupted playback, missing assets and transitions out of the zone.
- Observe at least two consecutive loop boundaries in every changed zone in a supported playback environment. Record heard or measured gaps and clicks. Mark seamless looping verified only when an appropriate listening or timing check passes.

**0.1.0 baseline:** The browser mixer supports a repeat flag for its battle, exploration-reference, cutscene-reference and ambience playback targets. The simulator has a zone ID input. It currently resolves a single exploration reference and contains no region importer, per-zone track resolver or verified native zone loop. The first real region pack is the acceptance input for those features.
