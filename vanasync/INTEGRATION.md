# XI Forever Offline integration boundary

The shipped code is a Python host and browser player. The proposed adapter contract requires verification against the exact developer-approved build.

| Contract | Required behavior |
| --- | --- |
| Session | Versioned capability report, unique runtime session and ordered monotonic snapshots |
| Game state | Engagement, group count including local player, explicit alliance status, current zone and protected cutscene state |
| Audio ownership | Game BGM channel only, acknowledged, renewable and expiring independently of the renderer |
| Restore | Idempotent release. The game owns BGM when control is invalid, expired, unavailable or released. |
| Playback | Decoder readiness, seek and gain capability, explicit media failure and bounded cleanup |
| Diagnostics | Version, capability, event source, lease activity and failures. Exclude player IDs, paths and secrets. |

Assign a session generation and sequence number to snapshots. Reject stale snapshots and release control when state is missing. Start native investigation in passive observation. If the client cannot isolate BGM from SFX or restore the current game cue, disable the affected mode and record it as unsupported.

Custom playback order is **game owns BGM → custom decoder ready → lease acknowledged → custom playback → release and restore**. Release on protected scenes, failure, stale heartbeat, disconnect, game exit and emergency restore. Keep rollback in the game-owning component so a renderer crash cannot leave the game muted. Explicitly define the native Off semantics with maintainers. Use a normal fade if verified playheads and matching cue points are unavailable.

Use a narrow local protocol with an OS access boundary or per-session authentication, allowlisted operations, replay rejection, timeout and disconnect cleanup. Keep the prototype's local browser and filesystem boundary separate from the game adapter. See [the Codex assignment](handoff/CODEX_NATIVE_DEVELOPMENT_ASSIGNMENT.md).
