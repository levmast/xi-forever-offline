> **2026-11-19:** this addon is now called **autobox** (folder `addons/autobox`, command `/autobox`). Where this text says
> Gambits or `/gambits` it means autobox and `/autobox`. The name Gambits now belongs to the squad Rule Set editor.
> Your sheets are still kept in `config/addons/Gambits/`. It is not loaded at start: OPTIONS > Addons, or the server
> menu's AUTO button, loads it.

# Gambits 2.2.207

Gambits runs ordered Gambit rules for your **player character**. Your personal main-job sheets, conditions, action picker, ON/OFF switch, and local save files continue to work. Sheets live under `config/addons/Gambits` so launcher updates do not overwrite them. (Earlier versions kept them in `config/addons/TitanGambits`; Gambits moves that folder over by itself the first time it loads.)

The Gambits tab keeps the existing Gambits, Recruit, Optimize and Inventory controls. The Inventory button runs the existing `!sort` command directly.

## Utility tabs

The same window now has **Gambits**, **Parser**, **EXP Watch**, and **Enemy Info** tabs. The original Gambits sheet and controls retain their dimensions; the outer window is only taller for the tab row. Version 2.2.204 fixes the tab row on Ashita builds that report available space as separate width and height values. Parser and EXP Watch continue collecting while another tab is selected.

Parser ranks human party/alliance members and Recruits by damage dealt to monsters during the previous 60 minutes. It uses native combat action packets, including supported additional-effect damage, and reuses the existing Tank/Support/DPS colors. Job abbreviations appear where the website's image assets cannot be loaded safely by the addon. Its hourly number is the damage accumulated in the moving one-hour window.

EXP Watch reads native EXP and limit-point award packets. The server marks FoV and GoV page awards in the existing award packet so the display can separate them from monster rewards without adding visible chat text. The rolling hour never resets at a clock boundary.

Enemy Info requests loaded server mob metadata once when the current target changes, then refreshes HP, MP and Treasure Hunter at a slower interval. It shows verified detection flags, shared spawn-slot candidates, configured loot rows and rates computed by the server's own Treasure Hunter function. Spawn-group and exact NM/placeholder relationships are not retained in the loaded mob object; a shared spawn slot is shown only as a candidate relationship. Scripted drops and special reward paths can differ from the static loot table.

## Generated Recruit Trusts

Recruit Trust combat is controlled by the server. The party member name buttons are display-only; clicking a player or Recruit name cannot change the selected sheet. Gambits edits and executes only your player character's Gambits. No addon action, control, or recast requests are sent for Trusts. On addon load, obsolete Recruit job sheets and their local migration backups are deleted from this launcher's `config/addons/Gambits/recruits` folder. Player job sheets and historical named Trust sheets are preserved.
The beta Recruit button and job picker have been removed. All 18 supported jobs can still appear at world anchors or in eligible automatic party fills. Names, races, faces, sizes, artifact looks, and cosmetic relic weapons are generated once per Recruit. The server uses one main-job AI profile per job, with no subjob. PLD and NIN may use Provoke as an explicit tanking exception.

The server controls Recruit engagement and support actions. It chooses cures based on missing HP, avoids recasting known effects, and uses unlimited self-only medicine when useful. Each item still follows its normal use check, recast, and Medicated restriction. Recruits do not eat food from Gambits.

The manual RECRUIT button shows its 15-minute countdown even when the party is full. At six members it remains disabled, and its hover hint explains why; the timer stays visible. `!recruit` reports a full party even during cooldown. Vacant companion buttons show their saved Tank, Support, or DPS reservation in dim blue, green, or red; clicking cycles Tank Ã¢â€ â€™ Support Ã¢â€ â€™ DPS. Individual job choices are no longer available; old saved job choices return to that slot's default pool. Each click updates the button immediately; the server receives only the final pool choice three seconds after the last click on that slot, so older receipts cannot make the button play catch-up. Occupied Recruit buttons keep the Recruit's name and a subdued pool color. Human party members keep the standard brown button. The default order is Tank, Support, DPS, DPS, DPS. Each manual draw is random within its chosen pool and excludes jobs already in the party.

## Player Gambits

The addon hides the exact generic client line `...A command error occurred.` from the visible chat log and keeps a local diagnostic trace. Other command errors and chat remain visible.

Target, Condition 1, Condition 2, and Action pickers use the main Gambits window as their center, including when it is near the bottom of the screen. Condition pickers remain anchored across frames as their contents are measured.

Open the addon with `/gambits`. Configure up to 14 ordered rows on your own character. Rows are saved per main job; the master ON/OFF state is per character. The action button itself shows a green fill for known spell and ability recasts. Player weapon skills, including Best Weapon Skill, fill with current TP and are solid green at 1,000 TP. Manual player commands take priority over addon-generated commands. Player consumables are not offered in the Gambit action picker.

Historical named Trust sheets remain on disk, but Gambits no longer selects or runs them. Trust actions are server controlled.

Reload after a launcher update with `/addon reload Gambits`. Server AI changes require the matching server update; an addon-only update cannot activate them. In-game timing, movement, and all job abilities remain subject to live beta verification.

Help text now fits the actual bar width and current font size; resizing preserves the complete message.

Inventory sorting runs directly when its button is clicked.

Earned level-75 jobs use full names and yellow buttons; pool reservations retain blue/green/red. Server verifies character job levels. Three-second selection delay and action confirmations remain.
