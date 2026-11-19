# Dialogue packs

Written lines for the bot players. Every player gets these, AI or not. With AI chatter on, the AI uses them as examples.

```
dialogue/
  packs/<name>/dialogue.json     a pack exactly as it came (never edited)
  voice/<name>/*.txt             our layer for it: what each line is used for, a casual version, what is left out and why
  build_dialogue.py              checks everything, then writes the two files below
  dialogue_lines.json            for the AI helpers (personalities, example lines)       <- generated
  AUDIT-living-world.md          what was checked in the Living World pack and what was decided
```

The game reads `<server>\modules\custom\lua\bots_dialogue_data.lua`, which is also generated. Never edit either generated file by hand.

## After changing a voice file, or adding a pack

```powershell
cd C:\FFXISOLO\dialogue
python build_dialogue.py --check
python build_dialogue.py --server C:\ffxi-local\server
```

Then STOP and PLAY. No rebuild is needed (Lua only).

## Adding a pack (for example the squad pack)

1. Put its `dialogue.json` in `packs\<name>\`.
2. Run `python build_dialogue.py --check`. It lists every template of the new pack that has no voice record yet.
3. Write `voice\<name>\*.txt` (see `voice\living_world\README.txt` for the format) until the check passes.

A pack with no voice folder is reported and left out, so nothing gets in unchecked.

## Our own lines

Lines we write ourselves go in the voice folder too: `+id` records in `voice_d.txt` (bots) and `squad_more.txt`
(squad mates, with who may say each one: role, voice, familiarity, race, gender). Same build, same checks.
