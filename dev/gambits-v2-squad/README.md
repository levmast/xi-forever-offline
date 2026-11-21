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
| `test_gambits_squad.lua` | the `!gsq` server command: protocol, catalogs (`cat`, `catm`), codec, saving, ownership, errors |
| `test_squad_rulesets.lua` | Rule Sets in `squad.lua` and the job ability rules (U13), plus a sweep that every built-in job profile is unchanged |
| `test_squad_upstream_integration.lua` | the hooks together with the current `squad.lua`: bard songs, spacing, skillchain wait, camp commands, the command error wrapper |
| `test_gambits_ws_batch.lua` | the WAR/PLD/RDM/Weapon Skill batch: `squad_ws.lua` (storage, precedence, apply), `!gsq` v5 (`wsg`/`wsl`/`wss`/`wsa`, `catm j`), the new conditions/target, the starter templates, the editor's Weapon Skills flows; a specification table of the new C++ weapon skill triggers and C++ source checks (enum values, code shapes) - the C++ itself is not run |
| `example_squad_rulesets_data.lua` | a valid example store (one WHM set) |

Lua 5.4 note: the server's `!squad` wrapper uses the LuaJIT global `unpack`; `run_tests.ps1` defines it for the Lua 5.4
runs on the command line only.

## Generators
- `make_squad_ja_jobs.py <server>/sql/abilities.sql <out>/squad_ja_jobs_data.lua` (`--check` to verify)
- `make_squad_spell_jobs.py <spell_list.sql> <magic.lua> <item_basic.sql> <out>/squad_spell_jobs_data.lua`
  (`--check`; `--trusts` / `--check-trusts` for the addon's `trust_spells.lua`)

Run them again when `abilities.sql`, `spell_list.sql`, `magic.lua` or `item_basic.sql` change; `run_tests.ps1` fails when
a table is out of date.
