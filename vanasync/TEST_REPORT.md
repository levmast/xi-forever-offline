# VanaSync 0.1.0 test report

**Test date** 25 November 2026, Japan time  
**Environment** Windows NT 10.0.26300, Python 3.11.9, Node 22.20.0, Microsoft Edge 158.0.4370.33  
**Scope** Verified standalone simulator with real browser playback. Native game integration remains pending.

## Automated results

| Suite | Result | Evidence |
| --- | --- | --- |
| Node selection and mixer | 15 passed | Automatic and forced composition, clock boundary and re-entry, mode priority, album traversal and repeat, settings normalization, two-deck overlap, matched seek, runtime fallback, interruption cancellation and cleanup |
| Python host and catalog | 6 passed | Seed and rename behavior, path and file validation, range delivery, origin/Host protection, hardlinks and invalid imports |
| Edge playback and interface | 4 scenario groups passed | Real MP3 playback for all three mixes, mode switching and exploration return, quick re-engagement without a new media object, Unicode rename, missing and decode failure fallback, emergency restore, ordered import, transport, zoning, battle/cutscene resume, drag/lock, shortcuts, settings reload and diagnostics download |
| Audio validation | 3 passed | Full-stream decode with FFmpeg error-on-failure, plus exact SHA-256 verification |
| Policy regression budget | Passed | 100,000 simulated state updates and selections in about 53 ms on this machine, budget 2 seconds |

## Supplied battle audio

| Role | Exact source filename | Length |
| --- | --- | ---: |
| Solo | Against the Odds (Solo Battle Theme) (1).mp3 | 190.000 s |
| Party | Beyond the Veil (Party Battle Theme).mp3 | 183.200 s |
| Alliance | The March of Many (Alliance Battle Theme).mp3 | 181.120 s |

All three are stereo 48 kHz MP3. Full hashes are in battle-pack.json. Album, Vanilla and cutscene reference scenarios used a local copy of the creator’s *A Place to Return* as a QA reference. That copy is outside the archive. The real album queue and track sequence remain to be verified with album masters.

## Manual and qualitative review

The rendered expanded player was visually inspected at a desktop viewport during simulated Party combat. The circular V, midnight-blue and antique-gold treatment, exact display title, combat marker, controls and simulator labeling were visible and readable. Pointer input, position lock, opacity and custom shortcuts were exercised in the automated Edge run. A direct desktop-browser loopback test timed out in the test environment. A human listening pass for transition feel, musical compatibility and physical audio-device behavior remains open.

## Fixes found during QA

- Clamped fade progress at zero for a frame timestamp preceding fade start. This avoids invalid HTML audio volume writes.
- Cleared pending status when a failed candidate falls back to an already-playing deck. The fallback preserves the playing instance.
- Persisted drag position at pointer end, including cancellation and capture loss.

## Native verification status

No native callbacks, game BGM changes, SFX behavior, actual zoning, native cutscene yield, live install mutation or native performance were tested. The loopback checks are a scoped defensive review. Full client integration, actual listening checks and an extended soak remain developer acceptance items. See [developer acceptance](handoff/DEVELOPER_ACCEPTANCE_CHECKLIST.md).
