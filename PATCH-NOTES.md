# XI: Forever Offline patch notes

Newest first. The launcher shows this file on SYSTEM > Patch notes; the same notes go to #patch-notes on Discord.

## v0.1.58 · 21 November 2026

### Tetra Master (new)
• The PlayOnline card game, inside FFXI. Visit Luto Mewrilah in Upper Jeuno (G-8) for a free starter deck, then type /tm and play the computer on Easy, Normal or Hard for gil.
• Collect 250 cards: from card traders, monster families, notorious monsters, treasure caskets and Vana'diel's biggest fights. Guide in #tetra-master-guide.
• Rules page sliders for card drops, casket cards, win gil and card prices.
• Card art, sounds and the original add-on by Nalfey.

### Character transfer (new)
• Bring a character over from retail or another private server: SYSTEM > Characters > "Bring a character from another server". Get the capture add-on, snapshot your character there, then import it onto a character here. Jobs, levels, skills, spells, key items, gear and items come along, within this era's limits. Your character is backed up first. How-to in #character-transfer. (charcapture by the VanaDreams team, used with their permission)

### Forever Beta Shirt (new)
• A thank-you for playing the beta: a shirt of its own, in royal purple and gold with a crystal on the chest. Use it for the Chariot Band's bonus (+75% experience for 12 hours), 5 times. New characters start with it; everyone else finds it in their delivery box at the next login.

### Launcher
• A new loading animation: a row of Vana'diel crystals that light up as the world starts, and turn green when the game launches.
• SYSTEM > Patch notes: these notes, right in the launcher.
• The status bar says World asleep / Crystallizing world... / World awake.
• "Squad gets all gear" is kept when you close the launcher, and the gear pickers (launcher Squad tab and the in-game squad menu) now list everything the mate can wear, not only what you gave. (Tasou, Yache)
• The Squad tab shows the support job level from your sub job ratio setting. (Bob Roberts)
• Rules > Travel > "Sneak and Invisible duration": 1x is the era's random 30 seconds to 5 minutes, up to 5x. (Yache)
• New optional add-ons: VanaFish and VanaCam by the VanaDreams team (off by default). XIUI and FFXIPort updated.

### Fixes
• Borghertz's hands quests: a squad mate on the right job counts, like the other AF quests. (Tasou)
• Squad mates cast enemy spells on the monster you have targeted before anyone engages: /p sleepga ii, /p dia. (sparkiie)
• Squad mates can Raise a knocked-out party member: /p raise <name>, co-op players included. (Tasou)
• A Ninja squad mate's Mijin Gakure knocks it out, like a player's. (sparkiie)
• Squad mates step out of sight during cutscenes and NPC conversations, and come back when they end. (lilibun)
• A bot player that dropped out of your party when you changed area joins you again and keeps following. (Sunie)
• Inside your Mog House you only see and hear your room: no town crowd chatter, no NPCs wandering in. (Trinity, Velderen)
• No more floating names left behind when a town crowd NPC leaves. (Sunie, Starfret)
• Bot players fish only at the water's edge. (Sunie)
• Horro's Visit: the message now sends you to the right place for Slarin (next to Home Point #2 in Southern San d'Oria). (Altair)
• "Modern item stacks" now really works on your PC: the part that changes the stack sizes was missing from the download, so sheepskin, goblin masks and the rest stayed single. (Egon, Ricc)
• Crystal Boy 1.8: fixes a crash that could take all your add-ons down with it, and Enter works on more setups. (krazy, Ricc)

## v0.1.57 · 21 November 2026

### Gambits: every job (thanks wildthing)
• Starter Rule Sets for MNK, BLM, THF, DRK, BST, BRD, RNG, COR, SAM, NIN, DRG and BLU in the Gambits editor (Gambits 0.3.0).
• New "Shadows / images" condition: a Ninja recasts Utsusemi when it's down to the shadows you choose.
• Party roles: !squad partyrole <slot|name> tank|melee|mage|ranged|auto tells your Rule Sets who the tank, melee and mages are.
• Bards sing for roles: Minuet for the melee, Ballad for the mages, each to the members your rules name.
• Thieves line up Sneak and Trick Attack from a Rule Set, and the party's weapon skill can wait a moment for them.
• Beastmaster pets go after their master's target; Dragoons use Spirit Link when the wyvern is low.
• Mates read finished skillchains properly and magic burst on them.
• "More conditions" in the editor for skillchain and burst windows, level, timers and random.

### Starlight Celebration (December, by date)
• The full event, ported from AirSkyBoat (credit to them): present delivery to the town children in a Dream Hat, Starlight greetings, Goblin Merrymakers, the Smilebringer Boot Camp in the starter zones, token and vendor moogles, Dream gear, holiday trees, and decorations in Jeuno too.
• Seasonal events now have a switch each in the launcher (World > Seasonal events): Harvest Festival, Starlight Celebration, Egg Hunt and Horro's Visit, all on by default. By date / Always on / Off still sits above them.

### Bot players
• Ask a bot in your party for a spell: /p cure me, /p protect Kurami, /p haste. It casts if it knows the spell and has the MP. (Sunie)
• Below level 12, bots don't split your exp, same as squad mates. (delukard)
• New switch "Bots pass all loot" (on): drops come straight to you. (delukard)
• Bot friends stay online, and you can trade them gifts.

### New launcher options
• Rules > Skills and crafting > "Learning blue magic": 1x retail, up to 3x for nearly every time. (Yache)
• Rules > Squad > "Squad gets all gear" (off): mates wear anything without you giving it first. (Yache)
• Rules > Loot and gil > "Auction house prices": 1x as now, lower is cheaper. (Tasou)
• "Short quest waits" now also clears the waits between Aht Urhgan missions. (PTgamerguy)
• The squad switches moved to Rules > Squad.

### Fixes
• Black Mage mates without their best element yet cast their strongest known nuke instead of Shock or Paralyze. (Tasou)
• Squad mates' support job follows your sub job level setting. (Bob Roberts)
• Old update downloads are cleaned up, keeping the newest. (Yumainai)

### Add-ons
• XIUI 1.8.5 and FFXIPort 1.2.0 (themes, UI size, expansion filter), updated for you if installed.

## v0.1.56 · 20 November 2026

### Squad
• Healers reach the party again: on auto or far range a healer could stand just past the distance its cure rules looked within and stop healing. Squad mates' cures and buffs now reach as far as the spell really does. (Thanks wildthing, and Ricc for the report.)
• A mate given an engage delay (!squad delay) now actually joins the fight. Before, its wait kept starting over and it never engaged.
• New from Jon: an Actions ON/OFF button on each mate card in the Squads window. OFF means the mate does nothing at all: no fighting, following, eating or casting.
• !idle on / !idle off stops or releases the whole squad at once.
• The squad Bard walks to one spot beside the fighters and holds it while it sings (!bard off to turn it off).

### Gambits
• Fixed a crash when the help text popped up in the Gambits editor (lilibun). (wildthing)
• New condition: "Party tank" (there is / there is none a NIN, PLD or RUN in the party).

### Launcher
• Run speeds above 50 now work: the server's speed limit rises with your run speed setting. (Bob Roberts)
• New switch (off by default): Training dummies for testing. !sandbox puts dummies of level 1 to 99 in Rolanberry Fields that never die and never attack.
• The GAME button is now OPTIONS (graphics, shaders, addons, plugins), and add-ons and plugins made by other people are installed and updated from the Addons and Plugins pages.

Big thanks to wildthing and Jon Tanta for this one.

## v0.1.55 · 20 November 2026

### New switches
• Modern item stacks (on by default): sheepskin, goblin helms, beastman drops and the like stack to 12 again, and some things to 99, as in today's game. Turn it off for the era's stack sizes (most of those don't stack at all). Split or empty stacks of those items before switching it off.
• Squad gear: you keep the item (off by default): trading gear to a squad mate (or !squad give) unlocks it for the whole squad and you keep your piece. Off = the squad takes the piece, as before. One-of-a-kind gear is always kept either way.

### Squad
• Mates set to mid or far range (!squad range <slot> mid|far) now shoot with a bow, gun or throwing weapon. Before, only Ranger and Corsair did, so a Thief with a bow just stood there.
• Dualbox: your second character's own gambits stay on.

### Crystal Boy 1.7
• While the Crystal Boy window has focus, every key goes to the Game Boy and none to your character (arrows and Enter used to reach both). Click inside the window to play, click the game to get your keys back.
• The window no longer presses its own Save/Load/Reset buttons with your keys.

### Small fixes
• A golden super casket now reads as the same chest: "...and it is a golden super casket!"

## v0.1.54 · 20 November 2026

### No more daily limits
• Fishing: the 200 catches a day and the fatigue meter are gone. Fish as long as you like.
• Chocobo digging: the 100 finds a day are gone. (The short wait between digs stays.)

### Crystal Boy (add-on 1.5)
• Sound! There's a "Sound: on/off" button next to Reset, plus /cb sound on|off and /cb volume 0-100. It goes quiet while fast forwarding.

### Experience
• Fields and Grounds pages: the exp cap now rises with your page rate, the same way monster exp works. At x3 a page can give up to 600 (750 at 51-60, 900 above) instead of stopping at 200.

### World
• The "Explorer Moogles" in the middle of Northern San d'Oria, Bastok Mines and Mhaura that did nothing are gone. They're later-era NPCs that were showing by mistake.
• Slime event: a slime hit by anyone who isn't gooed up now gets away instead of being caught. Your squad mates still count.
