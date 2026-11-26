# Codex assignment · Native VanaSync integration

## Objective

Build a maintainer-approved, fail-open adapter for a pinned XI Forever Offline build. Start with battle music. Preserve the simulator and leave native feature flags disabled until verified.

1. **Reproduce the baseline.** Run the packaged tests and verify the three SHA-256 hashes. Obtain the approved repository/commit, exact client/launcher/add-on versions, test install and interface documentation.
2. **Verify read-only state.** Identify supported combat, group, alliance, zone, cutscene and lifecycle sources. For each report the exact source, semantics, timing and compatibility. Trace developer-controlled scenarios. Identify unknown or unsupported fields.
3. **Prove BGM ownership in isolation.** Use an approved BGM-specific capability. Prove SFX, dialogue and protected cues remain game-owned. Implement acknowledgement, renewable lease, game-side watchdog and fail-open release. Exercise app, adapter and game loss in every ownership phase.
4. **Connect battle policy.** Adapt native snapshots to the documented state contract. Preserve the five-second grace, overrides, re-entry continuity and fallback. Test delayed, duplicate and stale events. Fade where cue timing is unverified. Enable synced position only after compatible timing metadata or approved measurements exist.
5. **Connect Album Mode.** Read the separately approved album manifest. Preserve album continuity through zones, optional interruptions, checkpoints and restoration of the prior soundtrack mode. Yield to protected cutscenes. Verify SFX and voice independently.
6. **Prepare release evidence.** Add version gates, feature flags, diagnostics, install/uninstall/rollback instructions and authorized isolated tests. Request explicit approval before changes to the live installation.

## Required outputs

- Native adapter source and test suite with a pinned build and supported capability matrix.
- Implementation and rollback instructions and reviewable change set.
- Evidence of alternate mode behavior, audio ownership, failure recovery and unchanged original game file hashes.
- Updated integration, known issues, testing, acceptance and release notes.
- Native go/no-go recommendation identifying unsupported features and dependencies.

See [the integration contract](../INTEGRATION.md) and [acceptance checklist](DEVELOPER_ACCEPTANCE_CHECKLIST.md). Keep all writes away from original game audio files.
