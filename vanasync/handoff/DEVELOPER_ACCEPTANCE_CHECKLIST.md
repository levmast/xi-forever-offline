# Developer acceptance checklist

Per run, record reviewer, date, OS, package digest, asset manifest, browser, pinned client/launcher version and adapter commit. Attach traces where approved.

## Simulator baseline

- [ ] Validate archive and three file hashes.
- [ ] Exercise auto Solo/Party/Alliance, every override and group changes mid-combat.
- [ ] Verify mode switching, five-second grace, re-entry, fade and exploration return.
- [ ] Check corrupt/missing recovery, emergency restoration, Unicode rename and persistence.
- [ ] Check album order, controls, position save, zoning, interrupt/resume and soundtrack restoration.
- [ ] Exercise layout, lock, scale, opacity, quick settings, shortcuts, volume and export.

## Native gates

- [ ] Pin client, launcher and add-on versions; verify provenance of every state field.
- [ ] Verify real solo, companion/party, co-op, alliance, regroup, rapid pulls, zones, death and reconnect.
- [ ] Confirm BGM-only ownership and preserved game SFX, dialogue and protected scenes.
- [ ] Verify release when disabled, disconnected, crashed, timed out, uninstalled or emergency-restored.
- [ ] Reject stale messages and leave native ownership intact on unknown client versions.
- [ ] Compare original audio and installation hashes before and after. Verify no outbound telemetry.
- [ ] Record CPU, memory, frame timing and resource release in a soak test.
- [ ] Get maintainer sign-off on assets, rollback and release gates. Obtain explicit approval for live installation changes.

Mark Pass, Fail, Blocked or N/A with evidence. Simulator observations are independent of native acceptance.

## Region packs and future theme packs

- [ ] Inventory source paths, exact filenames and checksums. Confirm stable zone IDs, explicit cue roles and unresolved input.
- [ ] Reprocess the same pack and verify no duplicate entries or lost preferences. Test interrupted or partially invalid updates and rollback.
- [ ] Verify zone cue selection, two consecutive loop boundaries, correct titles, rapid combat re-entry and restore to the current zone.
- [ ] Exercise zone transitions, corrupt or missing assets, cutscenes, Vanilla, Off and Album Mode. Record simulator and verified native results separately.
- [ ] Verify each future theme is triggered by approved cue data and stays separate from region music and the album.
- [ ] Provide the patched build or reviewable PR and follow the [operator prompt](DEV_AI_CONTINUATION.md) for every submission. Obtain approval for community distribution or live changes.

## Numbered album pack

- [ ] Validate one playable song per folder numbered 1 through 11. Reject incomplete, duplicate or ambiguous packs without replacing the current album.
- [ ] Verify numeric order across 9, 10 and 11 and exact filename display. Confirm reimport does not duplicate tracks.
- [ ] Verify rollback, saved position on unchanged tracks, repeat after 11, battle and cutscene resume, and soundtrack restoration on exit.
