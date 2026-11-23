# XI: Forever Offline patch notes

Newest first. The launcher shows this file on SYSTEM > Patch notes; the same notes go to #patch-notes on Discord.

## v0.3.2 · 22 November 2026

### New
• Squad: "Attack my target" and "Stop" in the Squads menu, and the commands !squad attack and !squad stop. Target a monster and your squad goes in without you drawing your weapon: stay back, sit and rest, stand up to heal. They fight it to the end and come back to you; Stop calls them back early. It also works on the move, and at a camp on anything within 20 yalms of it. Bot players in your party go in too. In a macro: /say !squad attack. (Hasuko, Yenkei)

## v0.3.1 · 22 November 2026

### Fixes
• The Squads menu opens again. In v0.3.0 a click on the Squads button (or /menu) opened nothing and put a red "MESSAGE FROM DEAR IMGUI: Missing PopStyleColor()" box on the screen. A mistake in the new menu opacity setting. Until you have this update: click the Squads button once more (or type /menu) and the red box goes away; the !squad commands typed in the chat still work. Sorry about that. (Hasuko)

## v0.3.0 · 22 November 2026

### New
• Guild shops are always open: no closing hours and no weekly holiday. On by default; switch it off under RULES > Comforts > "Guild shops always open" for the era's opening hours. (Dugahst)
• RULES > Battle, a new section. Out of era, so everything starts at the era's value. Support job level: half (75/37, the era), two thirds (75/50) or equal (75/75), and your squad mates follow it (Hexblood). Monster and notorious monster HP and MP, from 0.1x to 2x (Poptart). TP gain for you and your squad, and for monsters. EXPERIMENTAL: the support job level and the HP and MP multipliers have hardly been tried; tell us what breaks.
• RULES > Damage, a new section. EXPERIMENTAL, out of era, everything starts at 1x (the era). "Damage you and your squad take": every hit, spell and breath that lands on you or a squad mate, from half to double; it sits apart from the damage reduction on gear, so gear still counts in full. "You deal": a slider each for weapon skills, elemental, dark and divine magic, ninjutsu and blue magic, from 0.25x to 3x, for you, your squad, trusts and pets. A monster's own spells are not changed by them. Plain melee hits have no slider: to hit harder across the board, lower the monster HP under Battle. (Poptart)
• RULES > Battle > "Your HP" and "Your MP". EXPERIMENTAL, out of era, both start at 1x (the era). From half to three times your own HP and MP, before gear, food and traits are added; your squad mates follow it, bot players and monsters keep theirs. (delukard)
• RULES > Loot and gil > "Gil from every monster": every monster drops gil by its level, on top of what it carries anyway. 0 = off, the era. (VRTRA)
• RULES > Loot and gil > "Wait between seals (minutes)": after a Beastmen's or Kindred's Seal drops, your party gets no other for this long. 5 = as it has been, 0 = no wait. (delukard)
• RULES > Experience and fame > "Experience chain time": more time to reach the next monster and keep a chain going. 1x = the era. (Gilder)
• Squad: choose what a mate eats. The Food button on a mate's row in the Squads window (or !squad food <slot>) opens a menu: "As it comes" (its own pick by job and level, as before) or one of 38 foods. A food is unlocked once per character for what it costs on the auction house on average; after that it is free for every mate, like their food always was. !squad food <slot> auto goes back to its own pick. (Altair)
• Squad: best gear in one click. Auto-equip in the Squads window is one button that lights up: click it and every mate puts on the best gear you gave the squad, and keeps picking the best each time it is called. Click it again to switch it off: the gear stays on, and you can change any piece by hand. (!squad autoequip now [slot] does it once from chat.) (FalconX51, Bigbadbill)
• Squad: auto-equip knows the job. It used to take the highest-level piece a mate could wear, so a Warrior ended up in a Silver Hairpin. Now every piece is rated for the job: what it adds (STR for a fighter, MND for a healer, INT for a nuker, CHR for a Bard...) and, for a weapon, how hard it hits in that job's hands. A Warrior takes the great axe over a higher-level dagger, a Monk keeps his knuckles, a Paladin keeps sword and shield, a White Mage takes the Justice Badge and leaves the Spike Necklace to the fighters; a piece that would only cost the job something is left off. (lilibun)
• Bot players in your party sit down with you when you /heal, whether they need the rest or not, and get up when you do. Squad mates already did; a bot only sat when it was hurt. (K-Andy)
• Squad camp: the puller keeps pulling while you rest. Sit down for MP and your squad carries on; it used to wait until you stood up with at least 30% MP. A player on his feet still holds the pull while hurt (under 60% HP), and the mates' own HP and MP hold it as before. Pause is still Pause (the Squads window, or !squad camp pause). The old rule: !squad camp wait on. (Hasuko)
• Squad: pressing Attack sends your squad in, whether you hit anything or not, so a mage can start the fight from where he stands. This is now how every squad starts (it was "after your first swing" unless you had changed it); "Engage: first" in the Squads window shows it, and clicking it (or !squad engage normal) brings the first-swing rule back.
• Squad: area buffs reach you. A mate about to cast Protectra, Shellra or a Bar spell first walks to within reach of you, and out of a fight the rest of the squad closes up around you for a moment so the back of the line is covered too; then it is cast and everyone goes back to their places. In a fight only the caster steps in, as near as the spell needs. If she cannot get there within a few seconds she casts from where she stands. Not for songs (a Bard has her own walk) or at a camp. (Hexblood)
• Squad mates fight by the players' rules. They block, parry and guard; they hit and are hit by the same sums as a player (combat ratings and skills, level correction, damage caps, magic damage and resists); a job's abilities share their recast timers and charges as they do for you; a Bard mate's instrument skill counts; an unarmed Monk or Puppetmaster swings at the fists' own speed. Ranger and Corsair mates get the weapon skills of their bow or gun (Hot Shot, Sidewinder, Slug Shot...), which they never had. !squad sheet shows a mate's attack and defense totals. Ordinary Trusts are unchanged. (wildthing; reported by Mikoto, Velderen)
• Gambits 0.3.3: Bard song tiers in the "has / lacks a status" conditions (only the songs this server has), a choice of which roles a song is for or not for, and short share codes for Rule Sets (the older codes still import). (wildthing)
• Squad Roles explained where you pick them: the Squads window, the Squad panel and the launcher's Behavior page say what each Role really does (the cure limits, what Tank and Damage leave out, what Healer and Support drop), with a gold note where Tank or Damage limits a White Mage's, Red Mage's or Paladin's healing. Gambits says its Tank / Melee / Mage / Ranged targets are not the Squad Role. Changing a mate's main job now says once when its Role stays, since a Role belongs to the mate, not the job. (wildthing)
• Era fishing (RULES > Skills and crafting > "Fishing minigame" off): the catch no longer comes up by itself. The bite line shows what is on the hook ("Something caught the hook!", "You feel something pulling at your line.", "Something clamps onto your line ferociously!"), then you reel in with confirm or let it go with cancel. The fishing screen opens while the game waits for you, but there is nothing to win in it: your skill decides the catch. (Dugahst)
• Bot players understand auto-translate: phrases in your tells, party chat, linkshell chat and shouts reach them (and their chat AI) as words, not as symbols. (Sunie)
• Squad mates on your linkshell: !squad ls <slot or all> on puts a mate on the linkshell you wear (off takes it out, !squad ls lists them). Members talk there whether they are out with you or not: one says hello when you log in, the ones that are not out say now and then what they are up to, and when you say something on the linkshell a member answers. A member that is out with you answers through the squad chat AI when that is on. (Truth)
• Squad mates can answer quest and mission questions from the Phoenix wiki: with AI chat on and a mate out, type /p !wiki on. A question in party chat is then looked up on wiki.phoenix-xi.com and answered from that page only. OFF by default, because the words of your question go to that website; /p !wiki off turns it off again. (Dugahst)
• OPTIONS > Controller: three more things can go on a button: Target the nearest NPC, Map and Jump (and shutting the game down, on no button unless you choose one). The launcher's own layout now starts with R1 / RB on Target the nearest NPC and Select / Back on Map, the two changes gamepad players make first; screenshot and hiding the windows are still in the list. If you changed buttons before, your choices are kept. The setup also no longer leaves out the newer button slots of today's game. (Frost, FalconX51)
• Squads window: opacity. Right-click the Squads button for 100, 75, 50 or 25%, or type /menu opacity <10-100>; the button turns solid while the mouse is on it. /menu opacity menu <10-100> does the same for the menu's background. (K-Andy)
• SYSTEM > Settings > "Run setup again...": the first-time setup, on the install you have. Point the launcher at another game, Ashita or server folder, or let it fill in what is missing, without starting over. Your world, characters, squad, account and settings are kept; nothing changes until you press Install there, and the old folders are not deleted. (Sunie)
• OPTIONS > Addons and Plugins: "Remove" on the add-ons and plugins you downloaded from the list or added yourself. It takes the add-on out of Ashita and its line out of the load script; its settings are kept, so installing it again brings them back. Ashita's own add-ons and ours have no Remove. Get more has a Remove for the AI model (frees several GB) and for the Ollama this launcher installed (Windows opens Ollama's own uninstaller; the models go only if you say so). (lilibun)
• SYSTEM > Settings > "Clear the auction house...": takes everything the auction house simulator listed off the auction house, for a world that plays without one. Switching the simulator off only stops new stock. What you or a bot player listed stays. (delukard)
• RULES > Comforts > "Auction house from anywhere", off by default. The ahgo add-on (OPTIONS > Addons) opens the auction house wherever you stand with /ah, but the server only answered in areas that have an Auction House, so a bid out in the field hung on "placing bid". With the switch on, you can bid and sell from any area. Off = the era. (Velderen)
• RULES > Comforts > "Land kings on a timer", off by default. Off is how it has been here: Fafnir, Adamantoise and Behemoth are called at their ??? with the item. On is the era: the ??? is gone, a king appears by itself 21 to 24 hours after the last one fell (the first one within a day), and from the fourth kill in a row Nidhogg, Aspidochelone or King Behemoth can come in its place. The hours count while the servers are off too. (sparkiie)
• OPTIONS > Theme, a new page: pick the launcher's look. Default is the launcher as you know it. Vaporwave is here for a limited time: it is on by itself until 2 December, with its own colours, buttons, banners and song, and then goes away by itself. 8-Bit turns the launcher into a console RPG menu: pixel lettering, and every button and banner redrawn with 8-bit sprites of FFXI characters (sprites from the "Records of Vana'diel" pack). Changing the theme restarts the launcher, and you can switch back to Default at any time.
• The launcher has music. A theme song plays once when the launcher opens and stops when the game starts; OPTIONS > Theme names the song and who made it, and has its on / off switch and its volume. Every song was made for XI: Forever Offline by JØ, our Head of Music: "A Place to Return" (the launcher's own theme), the Vaporwave songs (a short opener the first time the launcher opens, then "No Signal, All Vibes") and "Beyond the Veil" (8-Bit). (JØ)

### Fixes
• Party-only spells and job abilities can be used on a squad mate. Spells: Regen I-III, Refresh, Erase, Phalanx II, Curaga I-IV, the fourteen Etudes, and Blue Magic's Wild Carrot and Magic Fruit. Job abilities: Cover, Accomplice, Collaborator, Martyr, Devotion, Shikikoyo, Healing Waltz and Carbuncle's Healing Ruby. The game only offers a squad mate as a target when the spell's or ability's own target list includes NPCs (Cure, Protect, Shell, Haste, the -na spells and Curing Waltz have that; these did not), so the launcher adds it to them in the game's own tables at PLAY, and the server now lets Cover, Accomplice and Collaborator land on a mate. Yourself and anyone in your party (bot players, a second character, friends in co-op) were valid targets before and still are. Your original file is kept in backups\spell-targets-dat. (Yache)
• Co-op: the launcher's own changes to the game files (item entries, Home Points, the spell targets above) are now also made before you visit a friend's world, not only when you press PLAY in your own.
• Guild shops: the Goldsmiths' Guild list (and other long guild lists) showed prices but no names or icons on its first and last pages. Our "full refill every day" rule also refilled the things a guild only resells after a player sold them to it, so every line was on the shelf: 124 at the Goldsmiths' instead of the 21 it stocks, more than the game's guild window can show. It happened at once with "Guild shops never run out" on, and from the second game day of a session with it off. Only what a guild stocks itself is refilled now. (Yumainai, Meli)
• Squad camp: the lines about which levels your puller takes said "your level" and showed your own, while the window is counted from the lowest level among you and your squad mates (so a pull is fair for everyone). They now name whose level it counts from, and "nothing to pull nearby" tells you the level range it is looking for and how to change it. (Hasuko, FalconX51, Yenkei)
• Squads window: now and then a button did nothing and the chat log showed its command instead (">> /say !squad camp start"); a sub job or another option that did not save had the same cause. The game refuses a chat line that comes too soon after another, and the window's own refresh every few seconds counted as one, so a click right after a refresh was lost. Every line the window sends now waits its turn, and a click goes before a refresh. (Dugahst)
• "The game loader never started ... Injection failed!" at PLAY now says what it is (security software stopping Ashita from attaching to the game) and what to do about it. (Telunian)
• Threw away the Forever Beta Shirt while it showed as a nameless Lv127 item? You get another one. After this update it is waiting in your delivery box, and the game tells you so when you log in. Once per character, and only if you have none left (bags, Mog House and delivery box all count).
• The game or the server closing the moment it starts, without any message: the launcher now checks the Microsoft Visual C++ runtimes at setup and at every PLAY (the 32-bit one for the game loader and Ashita, the 64-bit one for the server and the database) and installs the current one when yours is missing or older than 14.40. Windows asks for permission once. Until now only the 64-bit one was looked at, and only whether it existed. (Leyna Crosse, Lion, RobinDesBois)
• PLAY stopped with "NoneType object has no attribute lower" on Windows set to some languages other than English, when the launcher uses its own copy of the game. (R1PFake)
• "xi_connect stopped unexpectedly ... Cannot load login.cert and login.key" after a first start that was cut short: the half-made key is removed and made again. (Helix, ManTears)
• "[WinError 4551] An Application Control policy has blocked this file" now says what it is (Windows' Smart App Control) and what you can do about it. (Helix, ManTears)
• A game that closes within a minute of starting no longer leaves you guessing: the launcher's log says what the game loader reported, and the loader's own log is kept as logs/xiloader-last.log for bug reports. (Sunie)
• Linux: the game closing right after "Profile loaded." with nothing on screen (seen with game files updated after Square Enix's 18 November patch). The game checks its own version file against registry values that PlayOnline keeps up to date on Windows and that are fixed inside Proton. When it happens the launcher now switches on Ashita's Sandbox, which answers that check, and asks you to press PLAY again. (Sunie, Ziegh, skibbity rizzard)
• Linux: backing up the world no longer prints a SyntaxWarning. (Sunie)
• Linux, Steam Deck and other handhelds in Game Mode: the launcher's window is now exactly the size of the screen. Game Mode stretches every window over the whole screen, so the launcher's own shape was drawn stretched. Not tried on a Deck yet: tell us how it looks. (Sunie)
• RULES page: Relaxed solo and Fast are marked SELECTED when you pick them; they used to count as "your own rates". (EyalRA)
• Beaucedine Glacier: a treasure casket could turn up as "Peculiar Footprints" that did nothing when touched. (Bob Roberts)
• Casino Dealer: a bet of gil alone was refused with "Gil only, please". (Yache; reported by Altair, Kentar4565)
• AI chat model list: the lighter choice was "gemma4:4b", a model that doesn't exist, so picking it failed with "ollama pull ... failed". It is gemma4:e2b now, and a failed model download shows what Ollama itself said. (Yumainai)
• "xi_profile stopped unexpectedly ... access a socket in a way forbidden by its access permissions": the launcher now says what it means (Windows set the port aside for Hyper-V, WSL or Docker) and the two commands that free it. (Tetazos)
• Squad: a mate whose main job is level 1 keeps a level 1 support job, as a player does; it used to lose it. (wildthing; reported by Hammer)
• SQUADS > Gear: a Warrior's Main list stopped at level 12, because the picker held the first 300 items counted from level 1 and a Warrior can use a lot of weapons. The list now starts from the highest level and holds 600. (Gilder)
• The Squads page saying "Table 'xiforever.squad_mate' doesn't exist": a setup whose database import was cut short left the squad and guild shop tables out. PLAY now checks for them and puts them in. (NRDTheGamer)
• SQUADS page: a mate's support job is shown from level 1 once you have support jobs, as it already works in the game. The page only showed it from level 18. (FalconX51, Meli)
• SQUADS > Job levels: Blue Mage, Corsair and Puppetmaster always showed level 1 and no exp, whatever the mate's real level, so a Corsair that was levelling fine looked stuck. (krazy)
• The game closing at once with the loader's log saying "polcore (US) file ... doesn't exist": a European or Japanese game on a PC whose registry still holds another language's PlayOnline, even an uninstalled one. The launcher now tells the game loader and Ashita which game is yours. (Sirloinofbeef)
• Home Point #1 in Port Windurst, Port San d'Oria, Bastok Markets and Port Bastok: a teleport from inside the same area still left you at today's spot, away from the crystal (v0.1.59's fix did not work in the game). The server now watches where the game puts you after such a jump and moves you to the crystal. (notsensible)

## v0.1.59 · 22 November 2026

### New
• Casino Dealer in Southern San d'Oria, Bastok Markets, Windurst Woods and Lower Jeuno: trade gil, and you and the dealer each roll 0-999. Roll higher and your bet is doubled; a tie gives it back. (Yache)
• Rules > Comforts, all off by default (out of era): "Caskets tell you the code" (Dugahst), "Guild shops never run out" (delukard), "Full merits" (every merit to its own maximum) and "Merit points you can hold" up to 99 (PTgamerguy, Ricc).
• OPTIONS > Graphics > "Gamepad setup" opens FFXI's own gamepad tool, on Windows and Linux. (Sunie)
• OPTIONS > Controller: set your controller up in the launcher. Pick Xbox, PlayStation 4 / 5 or Switch Pro and the buttons are laid out for it; change any button, confirm on the right (Nintendo / Japanese style), vibration, invert the camera, keep the pad working with the game in the background. Off by default: then the game keeps what its own gamepad tool saved. Ported from LocalXI (seamuswilkie31-dev, GPL-3.0). (Sunie)
• WORLD page: six new switches for a livelier world, all on by default. Town crowds come and go through the zone lines and Mog House doors and may stop to wave at each other. Bot players emote (they cheer level ups, bow when they join you, wave goodbye), remember where they died and hunt somewhere else for a while, keep a life story between play sessions (!bots story Name), and leave and return through the town gate.
• tCrossBar, on-screen controller macros, can be added from the add-on list. (Yache)
• Gambits 0.3.2: job-aware spell and ability lists, a Weapon Skills section, and a Party roles section for who counts as Tank / Melee / Mage / Ranged. (wildthing)
• The Job rules editor now explains what it does and points to Gambits for your own spell choices. (wildthing)
• RULES > Skills and crafting > "Fishing minigame": on by default (today's fishing). Switch it off for era fishing: no fight on screen, the catch is decided as soon as the fish bites, and your skill still decides lost catches and broken lines.
• SYSTEM > Settings > "Change game folder": moved FINAL FANTASY XI to another drive? Pick the new folder and keep playing. (K-Andy)

### Squad
• Gear chosen by hand is checked against the rest of the outfit: a Rare item can't be worn twice, and Sub must fit Main (a two-handed weapon takes a grip only). Old setups simply leave the extra piece off. (Ricc, Meli)
• !squad give / equip / lockstyle take item names of several words: "Light Crossbow +1". (wildthing)
• Squad mates lose enmity when they take damage, like players. (wildthing)
• Squad Dragoons no longer get the Shikaree Z template's MP bonus. (wildthing)
• Party roles apply at once. (wildthing)
• The bard's "NOT MOVING" line only shows with !bard debug. (Meli, PTgamerguy)
• Squad mates stay put while you use a home point, a survival guide, a treasure casket, chest or coffer, a Fields or Grounds book or a conquest guard (Signet). They are still hidden during cutscenes and longer talks with other NPCs. (Ricc, Altair, Yumainai, Dugahst, Meli)
• A Dragoon's wyvern runs as fast as its master, so it keeps up with a raised run speed. (Yache)
• Squad mates know a spell from their job's Trust template only when their own jobs learn it, and at the level they learn it: a squad Paladin has Flash from 37 (was 45) and a White Mage Paralyze from 4, and a squad Bard, Dragoon or Puppetmaster no longer casts White Mage spells its sub job doesn't have. (wildthing)
• Squad Thieves get Trick Attack's sure critical hit (with Assassin, level 60+) like players do, and a squad Dark Knight's Souleater now really adds damage and costs HP.

### Fixes
• Forever Beta Shirt: on player installs it showed as a blank Lv127 item. It now gets its name, icon and look at the next PLAY, on Windows and Linux. (Ricc, Trinity, ザックス)
• Character transfer: an out-of-range body size (CatsEye exports) no longer stops the import. (delukard, MrDink, Bigbadbill)
• Port San d'Oria Home Point #1 sits on the ground and works again. (Tasou, Yache)
• A Home Point teleport inside the same town to the moved Home Point #1s (Port San d'Oria, Bastok Markets, Port Bastok, Port Windurst) lands next to the crystal. (Yumainai)
• Blue Mage AF quests no longer wait for Japanese midnight between steps. (Yache)
• Treasure casket "ghost" after opening removed. (Yache)
• Bot players fish at the water again: fishing spots are marked on the docks of Port San d'Oria, Port Bastok, Port Windurst, Selbina and Mhaura. (Tasou, Sunie)
• Squad chat: a long line from a mate is no longer cut off in the middle of a word (the game stops at 150 characters). It now comes as two or three lines. (Altair)
• Closing the launcher always stops its own database. It used to stay running in the background after a launcher had been closed from Task Manager. (Meli)
• Server menu: MY AUTO off now always reaches autobox, so your rules no longer run while the menu says OFF. (wildthing, Altair)
• Crystal Boy 1.8c: more detail in its trace files for crash reports, and a test switch for the crash that unloads every add-on: type /cb jit off, play, and tell us if it still happens (/cb jit on puts it back). (Ricc)
• Combat and magic skill-up rate: above about 2x it did nothing more (a 50% ceiling). The ceiling now rises with the rate, and from 10x each skill-up is bigger too. (Ricc)
• The launcher keeps the size you give it when you change pages. (Starfret)
• Linux setup: when the database's first-time step fails, the full message is kept in mariadb/install-db.log (the screen only had room for its start and end). (ザックス)

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
