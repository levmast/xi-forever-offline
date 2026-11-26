# Acceptance criteria

| ID | Simulator proof | Native proof required |
| --- | --- | --- |
| VS-01 | Auto and forced group selection, mid-fight group changes | Authority and semantics of real group state |
| VS-02 | Vanilla, Resonance and Off, fade and fallback | BGM-only ownership and audible continuity |
| VS-03 | Configurable five-second default grace, re-entry and restore | Real pull timestamps and exploration return |
| VS-04 | Compatible elapsed-position seek; opt-in | Composer timings or measured cue alignment |
| VS-05 | Exact filename stem, Unicode, rename, stable ID | Native cue provenance where supported |
| VS-06 | Ordered album, transport, saved position, interrupts | SFX and cutscene protection, real zone continuity |
| VS-07 | Missing/corrupt recovery, emergency restore, report and cleanup | Game-side recovery with bridge or renderer dead |
| VS-08 | Layout controls, keyboard and independent volume | Input and overlay coexistence |
| VS-09 | Loopback guards and deterministic performance test | IPC audit, asset integrity and extended native performance |

Read [TEST_REPORT.md](TEST_REPORT.md) for results. Native acceptance is a separate release gate.
