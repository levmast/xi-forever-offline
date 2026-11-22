# GambitsV2: tests and tools

Automated checks and generators for the GambitsV2 addon (`addons-src/GambitsV2`) and its server side (server repo,
`modules/custom/lua`: `gambits_squad.lua`, `squad_rulesets*.lua`, `squad_ability_rules.lua`, the generated tables, and
the hooks in `squad.lua` / `squad.cpp`).

## Run everything
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File dev\gambits-v2-squad\run_tests.ps1 -Server <server checkout>
```
Needs `luajit`, `lua`/`luac` 5.4, `python` 3.8+ and `git` on PATH (or pass `-LuaJitExe`, `-LuaExe`, `-LuacExe`,
`-PythonExe`, `-GitExe`). `-BaseRef` (default `origin/dev`) is the server revision without the GambitsV2 hooks; the Rule Set suite checks
that every built-in job rule set is unchanged against it. `-RuleSetData <copy>` also loads a copy of a real
`squad_rulesets_data.lua`. Nothing outside the temporary work folder is written.

| File | What it checks |
|---|---|
| `test_gambitsv2_addon.lua` | the addon end to end: editor, transport (with the game's 150-byte chat cut) and the real server module |
| `test_gambits_squad.lua` | the `!gsq` server command: protocol, catalogs (`cat`, `catm`), codec, saving, ownership, errors; (v7) the party roles `prl` / `prs`: read-back answers, your own squad only, a dualbox character's mate with the same id untouched, refused input, line sizes |
| `test_squad_rulesets.lua` | Rule Sets in `squad.lua` and the job ability rules (U13), plus a sweep that every built-in job profile is unchanged |
| `test_squad_upstream_integration.lua` | the hooks together with the current `squad.lua`: bard songs, spacing, skillchain wait, camp commands, the command error wrapper |
| `test_gambits_ws_batch.lua` | the WAR/PLD/RDM/Weapon Skill batch: `squad_ws.lua` (storage, precedence, apply), `!gsq` v5 (`wsg`/`wsl`/`wss`/`wsa`, `catm j`), the new conditions/target, the starter templates, the editor's Weapon Skills flows; a specification table of the new C++ weapon skill triggers and C++ source checks (enum values, code shapes) - the C++ itself is not run |
| `test_gambits_uiux.lua` | Gambits 0.3.1: `gambits_data.lua` against the server's enums and data; the job-aware family/spell lists against real `catm`/`cat` catalogs (saved rules kept, Show all = the server's list); per-option tooltips through the safe helper only; the Weapon Skills section; the layout (2 and 32 rules, three themes, scales, sizes); the status effect selector (job effects, Custom, typing, unknown names); the rule list height, tooltip wrapping and the WS "unsaved" state; the job-aware Job Ability lists (main / sub job, ratios 0-3, merits, Show all, saved rules, older servers, `gambits_data.jas` = the server's `squad_ja_jobs_data.lua`); (0.3.2) the Party roles section through the real transport and server module: only confirmed changes shown, stale and out-of-order answers ignored, Auto with several targets, the whole-party summary (dualbox characters included), older servers, themes, the Aldric WAR / WHM Regen case |
| `example_squad_rulesets_data.lua` | a valid example store (one WHM set) |

Lua 5.4 note: the server's `!squad` wrapper uses the LuaJIT global `unpack`; `run_tests.ps1` defines it for the Lua 5.4
runs on the command line only.

## Generators
- `make_squad_ja_jobs.py <server>/sql/abilities.sql <out>/squad_ja_jobs_data.lua` (`--check` to verify)
- `make_squad_spell_jobs.py <spell_list.sql> <magic.lua> <item_basic.sql> <out>/squad_spell_jobs_data.lua`
  (`--check`; `--trusts` / `--check-trusts` for the addon's `trust_spells.lua`)

- `make_gambits_addon_data.py <server checkout> <kit>/addons-src/Gambits/gambits_data.lua` (`--check`): the addon's
  spell families, status effects, which effect each spell and job ability gives (spell_list.sql, the spell
  parameter tables, the ability scripts and job_utils; nothing is guessed from names), and each job ability's job,
  level and two-hour / main-only / merit flags (copied from `modules/custom/lua/squad_ja_jobs_data.lua`). Only for what
  the editor shows.

Run them again when `abilities.sql`, `spell_list.sql`, `magic.lua`, `item_basic.sql`, `data/status_effects.yaml`,
`squad_ja_jobs_data.lua` or the ability / spell scripts change; `run_tests.ps1` fails when a table is out of date.
