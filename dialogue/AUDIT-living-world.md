# Audit: Vana'diel Living World dialogue pack v1.0.0

Date: 2026-11-17. The pack in `packs/living_world/dialogue.json` is byte-for-byte the one from `C:\ffxi dialogue\data\dialogue.json`. The second version of the day added a `squad` section (93 lines, 6 scenes), and the third a `crowd` section (482 lines, 70 pairs), written from our brief (`C:\ffxi dialogue\docs\CROWD_PACK_BRIEF.md`). The 1,020 main entries and the squad section are unchanged. Nothing in it was edited. Every decision below is recorded in `voice/living_world/*.txt`, one line per distinct template, and `build_dialogue.py` refuses to build if any template is missing a decision.

The pack's own validator passes: `OK: 1020 entries, 52 categories, 39 personalities, 35 scenarios, 93 squad lines, 6 squad scenes, 482 crowd lines, 70 crowd pairs, 12 templates`, with one warning (`npc_guard` has 7 lines, the guideline is 8).

## Result

| | Count |
| --- | --- |
| Entries in the pack | 1,020 |
| Distinct lines after removing stuck-on endings and zone/job swaps | 675 |
| Used (each with a casual version; polite personalities keep the pack's wording) | 446 |
| Kept for the NPC phase (wording unchanged) | 60 |
| Mapped to real game emotes (not wired yet) | 6 |
| Left out | 163 templates (235 pack entries) |
| New Forever Offline lines, only where the pack had nothing for a real event or reply | 61 |
| Scenes used / left out | 23 / 12 |

## What is good

- About 400 hand-written-feeling lines: greetings, goodbyes, deaths, humor, crafting, NM camping, newcomer help, rivalry, inside jokes, quiet presence. They fit the era.
- The 39 personalities are useful: each has a voice, habits and things to avoid. Every bot now gets one, used both by its written lines and by its AI prompt.
- The truthfulness idea is right: no invented drops, wins, prices or spawn times. We keep it.

## Problems found

1. **The count is inflated.** 211 entries are a sentence with one of 16 stock endings stuck on (each ending is used 4-16 times, e.g. "I will let you know how it goes." x16). `zone_chatter` (96 entries) is 6 sentences repeated for 16 zones. `contextual_chatter` (150) is an activity glued to a time phrase, 54 combinations.
2. **Machine-stitched nonsense and broken grammar (93 templates + 6 airship lines).** Examples: "Has anyone been near Valkurm Dunes after the airship arrives?" (no airship there), "Has anyone been near Kuftal Tunnel once I finish this errand?", "Thanks again for helping with helping a new member.", "I am finishing a mission once I finish this errand."
3. **The pack breaks its own truthfulness rule (33 templates).** Lines that claim things the server never saw: "I think you mentioned your subjob last time.", "While you were away, a few of us were talking about making a trip to the dunes.", leader announcements for expeditions that do not exist, NPCs saying "Your friends are waiting near the gate."
4. **Design rules written as dialogue (17).** "I will wait for the actual loot record before congratulating anyone.", "That is a fine find. The battle record confirms it, too.", "That is a callback, not a fact about today's adventure." No player talks like this.
5. **Event scheduling for events that do not exist (8).** All of `event_scheduling`.
6. **Voice.** Only 56 of 1,020 lines use a contraction and about 50 use any MMO shorthand. It reads like polite NPCs. Fixed with a casual layer. 17 personalities (mentors, knights, leaders, scholars, healers) keep the pack's polite wording, and 3 (quiet regular, restless thief, night owl) type very short.
7. **Not FFXI.** "I should repair my gear" / "taking a moment to repair": there is no durability in FFXI. Both were rewritten (restock / catch my breath). Ten `*emote*` lines were turned into real emotes where one exists (wave, nod, salute, sit, stretch); the other 4 were left out.
8. **Era check.** One line mentions Guild Points. It is left out until checked on the Phoenix wiki.
9. **Scenes put words in the player's mouth.** In 4 scenes a line belongs to the newcomer or the returning member, which is you. Those lines were removed, so bots never speak for you. 12 scenes need events the server does not have (loot, a declined invite, arguments, event rosters) and are left out.

## How the lines are used

- **Linkshell chatter** (your bot linkshell, every 2.5-7 minutes): 139 lines. A quarter of the time it's a short scene between two or three members. Half the time it's about what the bot is really doing (crafting, a battlefield, a quest). With AI chatter on, 40% comes from the AI's `ls` pool, written by your model with these lines as examples.
- **Real events** (from the bots' diary): level ups (round levels, or 30% of others), deaths, cleared or wiped battlefields, rank ups, new gear and job changes. The bot may say so in the shell and one or two others react. At most one event every 90 seconds per shell.
- **You**: members say hi when you log in (a different set after 3+ days away), welcome you on your first words after joining, and say bye when they log out.
- **Answers without the AI**: a tell, party or linkshell line gets a fitting written answer (yes/no to a party by whether the bot is busy, what it's doing, its job and level, thanks, bye, help, newbie questions, sympathy, unsure). With AI chatter off, or after 3 unanswered requests (then for 10 minutes), the answer comes in seconds instead of after 25.
- **Town pairs**: 15% of two-bot exchanges in town use the pack's pairs.
- **The AI** (Ollama, opt-in): each bot's prompt gets its personality and 4 example lines in its register for what was said. The crowd pool gets a new `ls` category seeded with pack lines.

Repeats: chatter and pairs not again for 24 hours (72 for the same bot), event lines for 6 hours, reactions for 10 minutes, answers for 20 minutes. Answers and event lines reuse the oldest line rather than stay silent; chatter stays silent. This is kept across restarts in `bots_dialogue_state.txt`.

## Not wired yet (data is ready)

- 37 party-chat lines ("nice chain, let's keep it going"): they need fight awareness for bots in your party, or they would claim things that did not happen. A good fit for the squad pack work, which already has fight events.
- 60 NPC lines (town, guild, guards, wilderness), the 6 emotes (needs a bot emote call in bots.cpp, which means a rebuild), 5 loot reactions (bots have no loot event), and 16 looking-for-party lines (bots have no "looking for a party" state that you could act on).

## Squad mates (the pack's squad section)

The 93 lines are in a steady companion voice that already fits squad mates (who sound like characters, not players typing), so they keep the pack's wording. Three were reworded. Decisions are in `voice/living_world/squad.txt`.

**Used: 74 lines and 5 of 6 scenes.** Left out: 19 lines and 1 scene.
- **Raise lines (6):** a squad mate who is knocked out leaves the party and cannot be raised, so lines like "Get me up when it is safe" would never be true.
- **Claims (7):** lines claiming things that did not happen, like "I will keep training while you are out" (the pack's own bench rule says benched mates do nothing), "I kept your gear clean", "Two incoming", or a nickname you never used.
- **No event to trigger them (4):** gear, appearance and weapon changes, and the puller's run.
- **Read oddly in party chat (4):** two unprompted "ledger" remarks, a call that fits no fight start, and a line answering a disagreement that never happened.
- **One scene:** the bench farewell, because nothing says who is being benched for whom.

**How they are used** (`squad_pack.lua`). They come on top of each mate's own voice lines, which still come first most of the time:
- **Calling a mate:**
  - A brand-new mate (level 5 or lower, never called) introduces itself.
  - After you were knocked out, "we go again".
  - After you changed jobs, a word about it.
  - After 3+ days, "welcome back" from a mate you levelled to 50+.
  - Otherwise, now and then a bond line for how long you have been together (by the mate's own level: below 20, 20-49, 50+) or a race line.
- **Roles, race and gender:** the role comes from the job (PLD/NIN tank, WHM healer, RDM hybrid, BRD/COR support, the rest damage), and race and gender from the mate's look. A line only plays for a mate it fits.
- **Scenes:**
  - The first time a tank, a healer and a damage dealer are out together.
  - "We go again" after you were knocked out.
  - "You came back" after 3+ days.
  - A camp-rest scene.
  - A hard-fight scene.
- **Knocked out:** 30% a pack line instead of the voice line.
- **Commands:** `!squad camp` / `camp off` get "Holding here." / "Following.", and `!squad dismiss <slot>` gets a goodbye.
- **Fights and quiet moments** play only while the squad chat AI is quiet (squad chat off, or it said nothing for 5 minutes), so the two never talk over each other:
  - A call at the pull (25%), by role.
  - Low HP (once per drop below 30%) and a healer's low MP.
  - Sometimes a word after the fight, with a reply from another mate.
  - Idle talk in town or in the field every 5-10 minutes (or nothing).
- **The squad chat AI:** with Ollama on, two pack lines that fit the moment and the mate's role go into its fight and idle instructions as examples of the feel.

## Crowd chatter (the pack's crowd section)

Written to our brief, and it shows: casual 2006 typing, our fill-ins (`{job}`, `{camp}`, `{item}`, `{price}`...) instead of made-up values, levels and jobs on each line, place flavor, and a polite version of the conversational lines. Decisions are in `voice/living_world/crowd.txt`.

**Used: 451 lines and 55 pairs.** Left out: 31 lines and 15 pairs.
- **Camp talk in town pairs (12 pairs):** two-line exchanges are only said in town, so "is that mob claimed", "u pulling?" and "how much mp u got" are out of place there.
- **Outpost lines the player can see are false (14):** "i died, someone raise me" from someone standing right there, and "train incoming, run" or "inc, 3 on the way" with nothing coming. Calm camp talk stays.
- **Wrong prices (4):** the price is a crafted item's price, so "{price} for a stack of crystals" would be wrong.
- **Other claims (7):** a bard playing, a bazaar by the fountain, someone just levelled, and two "need a pt?" lines from crowd characters who cannot join a party.
- **Fill-in mix-ups (5):** a line using `{item}` twice gets the same item twice, crafted items "farmed", "guild in {nation}", and "{nation} consulate" said in its own city.
- **Wrong directions (2 pairs):** "north, past the bridge", "the one past the bridge".
- **Odd in its place (1 pair):** bats in town.

**Fixed (not left out):**
- **Pair openings:** 68 of the 70 pairs started with "u", so about half now open differently ("heading to {camp}?", "got a map?", "still lfp?").
- **Geography:** San d'Oria's gate leads to Ronfaure, not La Theine.
- **Place:** the Upper Jeuno music line plays only in Upper Jeuno, the Signet lines only in the nation cities, and the ferry and boat lines only where there is one (Selbina, Mhaura, Nashmau, Whitegate). "going to Jeuno after" and "cheaper in Jeuno" are never said in Jeuno.
- **Time of day:** "night all" plays only at night and "evening" only in the evening.
- **Levels and jobs:** "just unlocked my subjob" is now for levels 18-30, "no sub yet" for 10-17, and "tank or dd" / "pull or tank" for WAR, PLD and NIN only.
- **Wording:** "whispers open" (another game's word) became "/t for a spot".

**Checked and correct:** the healer shouts name spells at the right levels (WHM Cure III 21, Raise 25, Haste 40, Cure IV 41, Raise II 56; RDM Refresh 41 and Convert 40).

**How they are used** (`crowds_pack.lua`, through `crowds_chat.lua`, for the crowds and for the bot players standing in town):
- **Share:** 70% of the lines that are not from the AI pool come from the pack: town small talk, outpost camp talk, two-line exchanges, greetings, replies when you target someone, and every kind of shout. The old templates fill the other 30%.
- **No AI:** the "misc" shouts (directions, a crafter, a hello to the town) come from the pack instead of turning into another looking-for-party shout.
- **Fit:** a line only plays where its place, level, job and time fit.
- **Personality:** each speaker has its pack personality (from its name, the same one it has in tells), so polite speakers type the polite version and the very short typists drop capitals and full stops.
- **Repeats:** a line does not come back until about half of the lines that fit have been used.
- **AI on:** the crowd AI pool now gets crowd pack lines as style examples for its small talk, camp talk, replies, pairs and shouts.

## Our second batch (2026-11-18): the thin spots

Written by us, not the pack, for the two places players without the AI would hear repeats first. Same checks as the
pack lines (truthful, era words, length, fill-ins), plus a builder check that reactions never show the speaker's own
level or job.

**Squad mates: 253 lines and 7 scenes** (`voice/living_world/squad_more.txt`), now 327 lines and 12 scenes in all.
- **By role and voice:** each mate now has 7 to 10 lines at the pull, 6 to 10 at low HP, about 19 after a fight and
  about 25 for each kind of quiet moment, from its role (tank, healer, red mage, bard/corsair, damage) and its voice.
  A red mage had no pull line at all before, and each other role had one.
- **Voices:** about a third of the lines are for one voice only (bold, calm, cheerful or gruff, the voice the mate
  already has in squad_dialogue.lua), so a gruff mate says "Hmph. Done." and a cheerful one "We did it! Yay!". The
  squad chat AI never gets voice lines as examples (they would fight the mate's AI personality).
- **Also:** replies to an after-fight line, knock-outs, "we go again", hold/follow, bond and welcome-back lines,
  job changes, the bench, and two more lines per race. Scenes: four rest scenes (two need no healer), one hard fight,
  one after a wipe, one welcome back.
- **Result:** in a simulated 3-hour session with the AI off, the most repeated squad line came up 3 to 4 times
  instead of 10 to 18 ("I need a breath before the next pull."), and players hear 68 to 84 different lines
  instead of about 32.

**Bots: 136 lines** (`voice/living_world/voice_d.txt`), now 639 in all.
- **Answers:** "where are you" 1 -> 10, "what are you doing" 3 -> 12, "what job" 3 -> 10, an answer to "gz" 2 -> 9,
  to "lol" 2 -> 10, to "back" 1 -> 9, to news 3 -> 11, to thanks 4 -> 10, hello 6 -> 12, bye 6 -> 11, bad news
  6 -> 12, and everything else (the most common answer) 6 -> 20.
- **Linkshell events:** level-ups 4 -> 11 and their reactions 8 -> 14, knock-out reactions 3 -> 8, new gear 2 -> 6
  (reactions 1 -> 5), job changes 4 -> 8, rank-ups 2 -> 5 (reactions 1 -> 4), win reactions 4 -> 7.

**Fixed or left out:**
- **A reaction showed the wrong level:** "grats on {lvl}!" filled in the level of the bot saying it, not the one who
  levelled. Now "grats on the ding!", and the builder refuses any reaction with {lvl}, {job}, {sub} or {doing}.
- **Wrong answers to a "gz" (2):** "ty for explaining that" and "appreciate the help, saved me a trip" were the only
  thanks a bot gave when you said gz to it.
- **Odd answers to a plain "lol" (2):** "not saying I was right, but not saying I was wrong either" and "that's going
  in the stories we tell new members".
