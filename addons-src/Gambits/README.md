> **2026-11-19:** this addon is now called **Gambits** (folder `addons/Gambits`, commands `/gambits` and `/gv2`). Where this
> text says GambitsV2 it means this addon. The addon that used to be called Gambits (your own character's rules, Parser,
> EXP Watch, Enemy Info) is now **autobox**. Settings are still kept in `config/addons/GambitsV2/`.

# GambitsV2

GambitsV2 is rule-based automation for XI: Forever Offline, built from ordered **Target → Conditions → Action** rules.
This first version edits your **squad mates' Rule Sets** in game: a Rule Set is a list of rules for one main job, and a
mate that follows one uses those rules instead of its built-in job rules. Player and bot rules are not part of it.
GambitsV2 is a separate addon from the original Gambits, which is unchanged and can stay loaded.

**Status:** development contribution. Squad **WHM** is the first job verified in game (see *Tested*). The editor and the
server are generic, but other jobs and rule combinations are not yet gameplay-tested.

## How it works
- **The addon** (`GambitsV2.lua`, `transport.lua`, `squad_editor.lua`) is the editor. Editing is local; the addon talks
  to the server only to load, save, check, delete, assign and apply, through `/say !gsq …` lines.
- **The server** (in the server repo, `modules/custom/lua/`) owns the data and the rules:
  - `gambits_squad.lua`: the `!gsq` command (protocol **version 4**); its answers are hidden chat lines of at most
    140 bytes, so they fit the game's chat packet.
  - `squad_rulesets.lua` and `squad_rulesets_store.lua`: the Rule Set store (`squad_rulesets_data.lua`), checked on
    load, saved atomically, and only by the owner.
  - `squad_ability_rules.lua`: which job abilities a mate may use (level, sub job, two-hour and main-job-only
    abilities, the owner's merits).
  - `squad_ja_jobs_data.lua`, `squad_spell_jobs_data.lua`: generated tables (made by `dev/gambits-v2-squad/make_*.py`).
  - `squad.lua`: four small hooks (the `!squad ruleset` command, the Rule Set at a mate's call, the job ability check,
    and the read-only `xi.squad.levelsFor`).
  - `squad.cpp`: `SquadOwnerMerit` (the owner's merits).
- **The server decides.** The editor offers only what the server lists for that mate, and the server checks again when
  the mate is called.

## Requirements and install
- XI: Forever Offline **v0.1.48** or later, with the GambitsV2 server changes. The server must register
  `custom/lua/gambits_squad.lua` in `server/modules/init.txt` (after `custom/lua/squad.lua`). An older server is
  detected: the editor says so and writes nothing.
- Copy this folder to `Ashita/addons/GambitsV2/`, then `/addon load GambitsV2` and `/gv2`.
  (The launcher does not copy it there by itself yet; see the contribution notes.)

## Use
1. `/gv2` opens the window. Pick a squad mate; the list shows its main and sub job with levels.
2. **New**, **Open** or **Copy** a set, **Add rule**, and **Save**. Saved sets are kept on the server.
3. **Check** (the mate must be summoned) tests the set at the mate's current level.
4. **Assign to <mate>** makes the mate follow the set; **Apply now** recalls the mates so it takes effect now.
5. In chat, `!squad ruleset` lists sets, `!squad ruleset <slot> <number>` assigns one, `!squad ruleset <slot> off`
   goes back to the built-in rules.

| Command | What it does |
|---|---|
| `/gv2` | show or hide the window |
| `/gv2 ping [n] [gap]` | n round trips to the server (default 10); also reports lines the game refused |
| `/gv2 show [slot]` | show the window, on that squad mate (the Squads menu's Gambits button uses it) |
| `/gv2 theme classic\|squad\|crimson` | window colours (FFXIPort 1.2.0 palettes). Crimson on a new installation; an installation that already has settings keeps its theme. The theme you pick is this character's, here and in the Squads menu |
| `/gv2 interval <seconds>` | time between two chat lines (default 1.0, 0.6–5.0) |
| `/gv2 scale <70-200>` | text and control size in percent (also the Size − / % / + buttons, behind Options) |

**0.3.4: one bar for Save, Assign and Apply.** Below the rules, the bar shows what fits the open Rule Set and the
selected mate, and what the mate really runs (the server's report, when the server gives it):

| The bar says | Buttons | What happens |
|---|---|---|
| Unsaved changes, the mate runs this set | Save · Save & Apply | Save stores only. Save & Apply stores, then calls the mate again. A rename alone applies nothing |
| Unsaved changes, another set is the mate's | Save · Save, Assign & Apply | (Save & Assign while the mate is away) |
| Saved, not used by the mate | Assign & Apply | (Assign while the mate is away) |
| Apply needed | Apply | the mate still runs the rules of its last call |
| Active on the mate | none | the server says this set runs |

With a server that has it, Apply calls only that mate again and the others stay out. An older server can only call the
whole squad again; the button's tooltip and the message say so. Rule Sets and choices of a mate that were loaded once
are kept until Refresh; Top and Bottom move the selected rule to either end. The theme, size and window size you set
are saved per character (until 0.3.3 they were lost when the add-on was loaded before logging in).

**0.3.5: one look with the Squads menu and the Profile.** The first row is the squad mate (a list to pick another one
from) and its jobs. The Rule Set column is narrower and the line between it and the editor can be dragged. Above the
Save buttons two lines say it all: **Editing** (the open set and its state) and **<mate> runs** (what the server
reports the mate runs, which can be another set than the open one). In the list a set is *active* only on the server's
word; *Apply needed*, *next call* and *chosen* say the rest. Next to the rule list: Add rule, Up, Down, Remove, and More
(Move to top / to bottom). A rule is switched on and off with the tick box of its row.

**0.3.6.** A row of the Rule Set list is the set's name; only *(active)*, the server's word, is added to it. What is
chosen for the next call and whether Apply is needed stand in the status area. When the window reaches below the
bottom of the game's screen, the panels end at the screen so the Save buttons stay reachable, and the window is never
larger than the screen.

**0.3.9.** The number fields of a condition (HP below, Enemies, Party members, the effect count) are wide enough for their
value at any Size, and a field wraps to the next line together with its label, unit and step buttons. The status
line's label column fits its longest label, so "runs" no longer covers the mate's name, and a long Rule Set name wraps
instead of running off the window. Scrollbars take the theme's colours. The Squads launcher's Gambits half now shows
whether this window is open and closes it again.

**0.3.8.** Three new conditions, offered when the server has them (gambits_squad.lua version 11 and its map server):
**Enemy family** (the enemy is a Goblin, an Orc, a Bat ...; it looks at the enemy whatever the rule's target is, so
"Enemy family is Goblin -> Barfira" works on Self or Party), **Party members** (how many members within 20 yalms match:
all, asleep, or with a status; e.g. at least 2 asleep -> Curaga, otherwise Cure) and **Enemies** (how many monsters fighting
the party are near the enemy, above an HP %; e.g. at least 3 above 30% -> Stonega, otherwise Stone). Monsters only standing
nearby are not counted. Rules that fix a status (Sleep -> Cure, Petrification -> Stona) now also run after a fight, while
you are not engaged.

**0.3.7.** A theme picked here is in the Squads menu at its next frame, and one picked there is here at the next frame:
the add-on that saves the choice tells the other to read it. A window that opens reads it before its first frame.

Settings live in `config/addons/GambitsV2/` (per character). An unsaved draft is kept in
`config/addons/GambitsV2/squad_draft.lua`.

## The editor
- **Target:** Self, Party member, Tank (PLD/RUN), Mage, Melee, Ranged (RNG/COR), Ally with aggro, Enemy (current
  target), Master (you). Party member is the first member in party order that matches, not the one with the lowest HP.
- **Conditions:** up to two, both must hold (AND): HP or MP below / at least (%), TP below / at least, missing HP,
  aggro, status effect has / missing, enemy casting or readying an ability. Values are kept exactly as typed; a value
  out of range is shown in red and blocks Save.
- **Action:** Best of Family, Specific Spell or Job Ability, plus an optional wait. Rules run top to bottom.
- **The choices are the mate's own:** job abilities by its main and sub job and level (two-hour and main-job-only
  abilities only from the main job, merit abilities only with your merits); spells by the game's rules for squad mates
  (no Trust, Summoning or Geomancy spells, only spells that come on a scroll, and with "spells from scrolls" on, only
  learned spells from level 18). Names are listed alphabetically; the tooltip gives the level and job.
- **Planning ahead (0.3.1):** Best of Family and Specific Spell also list what the mate's jobs learn later (the main
  job up to level 75, the sub job up to its level cap), dimmed and marked with the level ("Haste (Lv 48)"); a rule
  with one starts working at that level. **Show all** lists every family the server offers (and the sub job's
  spells above its cap), marked "(not RDM)" where no spell of the mate's jobs fits. Only the lists change: saved rules
  stay as they are, and the server checks every rule on Save. The setting is remembered.
- **Job Abilities the same way (0.3.1):** what the mate can use now, then what its jobs learn later ("Warcry (Lv 35)",
  "Divine Seal (sub Lv 15)"), and merit abilities you have not unlocked ("(Lv 75, merit)"). The same **Show all** adds the
  sub job's two-hour and main-job-only abilities and those above the level caps, marked. Show all covers the mate's
  main and support jobs only: other jobs' abilities are not listed (no extra server requests). A saved ability the list
  leaves out stays selected and marked (e.g. "(WAR, not RDM)"). The lists are about job, level and merits only: recast
  and status are checked in combat. The job, level and restrictions come from the server's own ability table
  (`gambits_data.lua`, generated).
- **Status effects (0.3.1):** one dropdown: the effects the mate's jobs give (from the server's ability scripts and
  spell data), the common ones, and **Custom...** for any other name (typed with spaces; a name the server does not
  have is marked and never changed silently).
- **Tooltips** on every dropdown entry: targets, conditions, families (their spells and levels), spells, effects.
- **Weapon Skills** is a section of the same editor (click its header to open it; remembered); closed, it shows one
  line with what is saved. The **Save** button stays visible below the rules.
- **Party roles (0.3.2):** a section below Weapon Skills (remembered) for who the targets **Tank, Melee, Mage and
  Ranged** mean (and who a Bard's role songs reach): you and each squad mate, with a dropdown **Auto / Tank / Melee /
  Mage / Ranged** - the same setting as `!squad partyrole`, stored on the server. **Auto** follows the main job and can
  mean more than one target (a PLD is "Auto (Tank, Melee)"); a role you choose replaces the job for every target (a
  PLD set to Melee is no longer a Tank) and stays when the job changes, until you choose Auto again. A change counts
  only when the server confirms it; it works at once for a mate that is out, else from its next call. It is **not**
  the Squad menu's Role (Auto / Tank / Damage / Healer / Support): that one filters a mate's default job rules (Damage,
  for one, cures only below 30% HP and drops status removal), is not used while a Rule Set is assigned, and never
  decides who a target is. The target tooltips and the "uses: default job rules" line say so too. Closed, the section
  shows who counts as what in your whole party, dualbox characters and other members included (read-only: they set
  their own with `!squad partyrole me <role>`). Needs gambits_squad.lua version 7; with an older server the section
  only says so.
  Known limits (unchanged engine rules): the conditions "Tank in party" / "No tank" also count a NIN by job and the
  mate checking the rule itself (a WAR set to Tank with "No tank -> Provoke" does not Provoke); a target still has to
  be alive, in the zone and in range.
- **One song of a song type (0.3.3):** with **Has / Missing effect** and a Bard song type (March, Minuet, Madrigal,
  Ballad, Minne, Paeon, Prelude, Mambo, Operetta), a second dropdown chooses **Any March** (as before) or one
  song, e.g. **Victory March**. Then "Missing effect Victory March -> Victory March" and "Missing effect Advancing March
  -> Advancing March" keep both Marches up, each sung again only when it wears off. A squad Bard holds two songs per
  target, as before. Songs sung for Tank / Melee / Mage / Ranged by a rule that names one song reach that rule's roles
  only (two Marches for two roles stay apart). Etudes, Carols and Mazurkas cannot be told apart this way (their songs
  share one tier). Needs gambits_squad.lua version 8 and the matching map server.
- **Include / Exclude roles (0.3.3):** with the target Tank, Melee, Mage or Ranged, each other role has one choice: **-**
  (ignored), **Include** (its members also count) or **Exclude** (its members never count, even with an included role).
  The target's own role always counts.
  A Paladin on Auto is both Tank and Melee, so "Melee, exclude Tank" sings the Marches for the melee only, and "Tank,
  include Mage" gives Mage's Ballad to tanks and mages. It works the same for every job and action (a WHM's Haste for
  "Melee, exclude Tank", an RDM's Refresh for "Tank, include Mage"). Without boxes ticked a rule works exactly as before. Roles come
  from Party roles (Auto by main job, or the role you set). Needs gambits_squad.lua version 9 and the matching map
  server.
- **Share codes (0.3.3):** **Export** (next to New) shows the open Rule Set (name, job, number of rules) and its share
  code, a line of letters and digits such as `GS1...`; **Copy Share Code** puts it on the clipboard to paste into
  Discord or a message. **Import**: paste a code into the box, **Preview Import** (name, job and every rule), then
  **Import as New Rule Set**: it opens as a new, unsaved Rule Set - nothing is saved, replaced, assigned or applied, and
  a name you already have gets a number ("My set 2"). A code holds everything (rule order, on/off, conditions, song
  tiers, role filters, actions, waits, levels, ids) and a check number; it is only data (never run). A cut or changed
  code, a newer format or a broken rule is refused with the reason. Older shared text (`GRS1|...`) still imports.
  **Save** then checks the set on the server as any other.
- **Level Sync** does not change the choices; the server runs each rule at the mate's current level, and Check says
  which level it checked.
- **Saved rules are never rewritten:** a spell or ability that is not in the list any more stays as saved, with a note;
  a rule the editor cannot show exactly is marked **[kept]** and its set is read-only.

## Without a Rule Set
A mate with no Rule Set chosen behaves exactly as before: its built-in job rules, role and mode, unchanged by GambitsV2.
The job ability check (level, sub job, merits) applies to every squad mate's job abilities.

## Tested
- **In game** (XI: Forever Offline v0.1.48 with these server changes; squad WHM): loading the addon and talking to the
  server; creating, editing, copying, saving and reloading Rule Sets; Check, Assign and Apply; HP thresholds, rule
  order and AND conditions; Cure, Cure II and Divine Seal used by the mate; main/sub job eligibility (for example
  WHM 25 / WAR 12: Provoke yes, Berserk no); Level Sync; and the squad's v0.1.48 behaviour around it.
- **Automated:** `dev/gambits-v2-squad/run_tests.ps1` (addon, server command, Rule Sets and job ability rules, and the
  squad.lua hooks, on LuaJIT and Lua 5.4).

## Known limitations
- Only squad WHM is verified in game. Other jobs, sub-job combinations and conditions are untested in play.
- Not available (the engine has no such choice): Healer target, a specific member, lowest-HP ally, "equal", absolute HP
  or MP values, weapon skills as actions.
- Check validates spells by name only; blue magic is never offered (it is set when the mate is called); spells from a
  trust's own template list are not offered.
- Run one Squad Rule Set editor at a time (a development build of the old Gambits with a SQUAD tab would take the same
  answers; the released Gambits is not affected).

## Files
`GambitsV2.lua` (window, settings, commands, events), `transport.lua` (chat transport), `squad_editor.lua` (the
editor), `share_code.lua` (Rule Set share codes, 0.3.3), `trust_spells.lua` (generated: Trust spells left out of the spell list), `gambits_data.lua` (generated from
the server's data: spell families, status effects and what gives them, and each job ability's job, level and sub job /
merit restrictions; 0.3.1). Tests and tools:
`dev/gambits-v2-squad/`.

The colour palettes come from FFXIPort 1.2.0 (© 2026 wildthing, GPL-3.0-only).
