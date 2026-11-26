# Architecture

| Component | Responsibility |
| --- | --- |
| server.py | Loopback host, binary imports, stable-ID catalog, byte range playback and asset seed verification |
| app/core.js | Settings normalization, group policy, combat clock, playback intents and album traversal |
| app/audio.js | Browser decoder lifecycle, cancellation, crossfade, position and resource release |
| app/app.js | UI controls, simulator input, profile settings, album checkpoints and diagnostics |
| battle-pack.json | Filenames and SHA-256 values for user-supplied battle arrangements |

The UI sends snapshots to a combat clock. An engaged-to-idle update starts the grace timer. Re-entry cancels it. Selection builds an ordered music intent stack and optional independent ambience. The mixer keeps its current deck while a replacement loads, discards canceled generations and releases superseded decks. A resolved title keeps its media instance through repeated events. Media failure tries the next candidate. A runtime failure excludes the failed candidate until the plan changes or audio is retried.

Playback priority is cutscene, emergency Vanilla, active Album Mode, and selected soundtrack. Album interruptions can temporarily hand control back to the soundtrack. Paused album playback stays paused. Album position is checkpointed once per second and before priority transitions. A zone ID by itself does not select a new album track.

An import creates one ID directory and preserves the original filename. Name polling runs every 1.5 seconds. A missing or ambiguous directory is unavailable, with assignments retained. Verified bundled tracks seed new local catalogs from the manifest. Settings use versioned browser-local storage.

The host binds IPv4 loopback and checks exact Host and Origin. Imports require same-origin POST, a custom header and an expected content type. Catalog routes accept opaque IDs and inspect file types. The Windows account and files it can write are trusted. Browser codecs decode audio. The diagnostic ring keeps 300 events per tab until export.

Keep selection independent of game API and file names. Versioned pack records and channel-scoped playback intents provide extension points for a zone resolver, multichannel audio and creator tools.
