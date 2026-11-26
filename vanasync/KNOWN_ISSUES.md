# Known issues

- Combat, groups, zones, cutscenes and Vanilla references are simulated. Native hooks, BGM ownership, SFX preservation and installer behavior need game-side verification.
- The album masters are a separate delivery. In 0.1.0, add the files from folders 1 through 11 in numeric order. Folder import automation is pending.
- The battle mixes have different durations and lack verified timing landmarks. Shared-position matching defaults off. Sample-accurate looping is beyond the current browser playback implementation.
- Browser audio requires activation each session. Background scheduling and codec support vary.
- Settings persist per browser profile and loopback port. Use one active tab. An abrupt close may lose the last second of an album checkpoint.
- A corrupt album entry yields to a playable reference where assigned. Use Next to skip it. Retry audio reopens repaired files with unchanged names.
- Rename a track inside its ID directory and keep one supported file there. Catalog file removal is manual.
- Dragging moves the player inside the page. Shortcut handling is tab-local.
