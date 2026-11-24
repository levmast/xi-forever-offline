"""Where every game setting lives in the launcher's World, Rules, Squad and Era pages, and how it is shown.

One line per setting. A NEW SETTING NEEDS A LINE HERE (dev\\launcher-tests\\test_settings.py fails when a key that
RatesTab.collect() returns has no line), otherwise it only shows on the classic settings list.

The values themselves still live in the Rates tab's own Tk variables (launcher_gui.RatesTab), which stays the one
place that reads, checks and saves them: the pages made from this table are another view of the same variables, so
rates.json comes out exactly as before. Nothing in this file needs Tk."""

# how a setting is drawn
RATE = "rate"          # a multiplier with minus / plus (1 = the era's own pace); a RATE_FIELDS number
PERCENT = "percent"    # a 0-1 RATE_FIELDS number shown as a percentage
NUMBER = "number"      # a whole RATE_FIELDS number (run speed, level cap)
FLAG = "flag"          # a RATE_FIELDS 1 / 0 shown as a switch
SWITCH = "switch"      # an on / off value of the tab (attr = the tab's BooleanVar)
COUNT = "count"        # a whole number of the tab (attr = the tab's StringVar), with lo, hi, step
CHOICE = "choice"      # one of a few named values of the tab (attr = the tab's StringVar), with options

SETTINGS = []


def S(key, page, section, kind, label, tip="", note="", dev=False, attr=None, **more):
    entry = {"key": key, "keys": more.pop("keys", (key,)), "page": page, "section": section, "kind": kind, "label": label,
             "tip": tip, "note": note, "dev": dev, "attr": attr or key}
    entry.update(more)
    SETTINGS.append(entry)


# ---------------------------------------------------------------- World: who else lives in Vana'diel
S("crowds_per_zone", "world", "Town crowds", COUNT, "Adventurers per area", attr="crowds_size", lo=0, hi=40, step=5,
  tip="How many adventurers rest, shop and walk around in each town; outposts get a quarter of it. 0-40.")
S("crowds_chat", "world", "Town crowds", SWITCH, "Crowd chat",
  tip="Party-wanted shouts, people selling crafted items, and small talk near you.")
S("crowds_chat_amount", "world", "Town crowds", CHOICE, "Chat amount",
  options=(("quiet", "Quiet"), ("normal", "Normal"), ("busy", "Busy")))
S("crowd_gates", "world", "Town crowds", SWITCH, "Come and go through the gates",
  tip="Newcomers walk in from the zone lines and Mog House doors, and people leaving walk out through them or warp "
      "from the Home Point. Off = everyone appears and fades by the Home Point.")
S("crowd_meet", "world", "Town crowds", SWITCH, "Stop for each other",
  tip="Two adventurers walking past each other may stop, turn and wave before going on.")
S("crowds_field_parties", "world", "Field parties", COUNT, "Parties per area", dev=True, lo=0, hi=3, step=1,
  tip="Players get this from their world choice.")
S("bots_online", "world", "Bot players", COUNT, "Online at a time", lo=0, hi=1500, step=10,
  tip="How many bot players are logged in at once. Lower it if the game stutters. Usually 0-550; up to 1500 for strong PCs (the launcher asks first). At most 60% of the roster.")
S("bots_roster", "world", "Bot players", COUNT, "Roster size", lo=0, hi=2000, step=50,
  tip="How many bot characters exist in your world. Usually 0-600; up to 2000 for strong PCs (the launcher asks first).")
S("bots_growth", "world", "Bot players", CHOICE, "Bot growth",
  options=(("off", "Off"), ("realistic", "Realistic"), ("fast", "Fast")),
  tip="Bots level, craft and earn gil while you are not playing.")
S("bots_pass_loot", "world", "Bot players", SWITCH, "Bots pass all loot",
  tip="Bot players in your party pass every drop at once, so it comes to you without waiting for the lot timer.")
S("bot_social", "world", "Bot players", SWITCH, "Emotes and greetings",
  tip="Bot players cheer level ups, bow when they join you, wave goodbye, panic when badly hurt, and trade emotes with "
      "each other in town.")
S("bot_memory", "world", "Bot players", SWITCH, "Remember where they died",
  tip="After dying twice in an area a bot hunts somewhere else for a while, and it keeps away from the camp it died at.")
S("bot_story", "world", "Bot players", SWITCH, "Life stories",
  tip="Each bot keeps its milestones between play sessions (!bots story Name), so in a chat it still knows what it did "
      "yesterday.")
S("bot_gates", "world", "Bot players", SWITCH, "Use the town gates",
  tip="A bot going hunting runs to the town gate first, and one coming home arrives at the gate and walks in. "
      "Off = they leave from and return to their spot.")
S("bots_head_start", "world", "Bot players", SWITCH, "One-time head start",
  tip="The starting bots get a few months of history - levels 1-75 (most 10-30), subjobs, crafts, gil, gear - as if the "
      "server had been running a while. Used at your next PLAY, then this switch goes away.")
S("crowds_chat_ai", "world", "AI chat", SWITCH, "Town and bot chatter",
  tip="Your local Ollama model writes some of the small talk (runs quietly in the background).")
S("squad_chat", "world", "AI chat", SWITCH, "Squad mates talk",
  tip="Squad mates answer you in party chat with the local AI (Ollama), each with their own personality.")
S("events", "world", "Seasonal events", CHOICE, "", options=(("By date", "By date"), ("Always on", "Always on"), ("Off", "Off")),
  tip="By date = each event switched on below runs on its own dates. Always on = they run all year (for trying them out). "
      "Off = no seasonal events at all.")
S("event_harvest", "world", "Seasonal events", SWITCH, "Harvest Festival")
S("event_starlight", "world", "Seasonal events", SWITCH, "Starlight Celebration")
S("event_egg_hunt", "world", "Seasonal events", SWITCH, "Egg Hunt")
S("event_horro", "world", "Seasonal events", SWITCH, "Horro's Visit")
S("event_sunbreeze", "world", "Seasonal events", SWITCH, "Sunbreeze Festival")

# the switch beside a section's title turns the whole feature on or off
MASTERS = {"Town crowds": "crowds", "Field parties": "crowds_field", "Bot players": "bots",
           "Auction house": "ah_sim", "Conquest": "conquest_sim"}
SECTION_NOTES = {
    "Town crowds": "Adventurers resting, shopping and walking around in towns and outposts.",
    "Field parties": "Parties camping and fighting out in the field, away from you.",
    "Bot players": "Real characters with no game window: /sea them, /check them, invite them.",
    "Auction house": "Stocks the auction house and buys what you list.",
    "Conquest": "The other nations and the beastmen act while you are away, so regions can change hands.",
    "Seasonal events": "Harvest Festival, Starlight, Egg Hunt, Horro's Visit, Sunbreeze.",
    "Battle": "Out of era. 1x and half are the era's values; the lines marked experimental have not been tried much.",
    "Damage": "Out of era and experimental. 1x is the era. Plain melee hits have no line of their own: to hit harder "
              "across the board, lower the monster HP under Battle (half the HP is double the damage).",
}

# ---------------------------------------------------------------- Rules: how fast and how forgiving
S("map.EXP_RATE", "rules", "Experience and fame", RATE, "From monsters",
  tip="Keep this at 1 with the era experience tables: they already carry the era's pace.")
S("main.EXP_RATE", "rules", "Experience and fame", RATE, "From quests", tip="Experience from quests and scripts.")
S("main.BOOK_EXP_RATE", "rules", "Experience and fame", RATE, "From FoV/GoV pages", step=0.125,
  tip="Experience from Fields of Valor and Grounds of Valor pages.")
S("map.EXP_LOSS_RATE", "rules", "Experience and fame", RATE, "Lost on death", tip="0 = none.")
S("main.FAME_RATE", "rules", "Experience and fame", RATE, "Fame from quests", tip="1 = retail.")
S("main.EXP_CHAIN_TIME_MULTIPLIER", "rules", "Experience and fame", RATE, "Experience chain time", step=0.5,
  tip="How long you have to reach the next monster and keep an experience chain going. 1x = the era: against monsters "
      "below level 10 that is 50 seconds for the first chain, shrinking to 10 seconds for chain 5; from level 60 it is "
      "350 seconds down to 70. 2x = twice as long. (Gilder)")
S("main.NM_LOTTERY_CHANCE", "rules", "Notorious monsters", RATE, "Lottery spawn chance", special={-1: "always"},
  tip="Leaping Lizzy, Valkurm Emperor and the like. 1 = retail. One step below 0 is 'always': the NM always comes next.")
S("main.NM_LOTTERY_COOLDOWN", "rules", "Notorious monsters", RATE, "Wait after a kill",
  tip="The time after a kill before the NM can be rolled again. 1 = retail, 0 = none.")
# (2026-11-22, suggestions: Hexblood, Poptart) out of era and not tried much: the section says so
S("map.SUBJOB_RATIO", "rules", "Battle", RATE, "Support job level (experimental)", step=1,
  special={1: "half", 2: "two thirds", 3: "equal"},
  tip="How high your support job goes next to your main job. Half = the era (75/37). Two thirds = 75/50. "
      "Equal = 75/75. Your squad mates follow it too. Experimental: the game was never balanced for it. (Hexblood)")
S("map.PLAYER_HP_MULTIPLIER", "rules", "Battle", RATE, "Your HP (experimental)",
  tip="Your own HP and your squad mates', before gear, food and traits are added. 1x = the era, 0.5x = half, "
      "up to 3x. Bot players and monsters keep theirs. Experimental. (delukard)")
S("map.PLAYER_MP_MULTIPLIER", "rules", "Battle", RATE, "Your MP (experimental)",
  tip="Your own MP and your squad mates', before gear, food and traits are added. 1x = the era, up to 3x. "
      "A job without MP still has none. Experimental. (delukard)")
S("map.MOB_HP_MULTIPLIER", "rules", "Battle", RATE, "Monster HP (experimental)",
  tip="The HP of ordinary monsters. 1x = the era, 0.5x = half, 2x = double (the most the server takes). "
      "Experimental. (Poptart)")
S("map.NM_HP_MULTIPLIER", "rules", "Battle", RATE, "Notorious monster HP (experimental)",
  tip="The HP of notorious monsters. 1x = the era. Experimental.")
S("map.MOB_MP_MULTIPLIER", "rules", "Battle", RATE, "Monster MP (experimental)",
  tip="The MP of ordinary monsters. 1x = the era. Experimental.")
S("map.NM_MP_MULTIPLIER", "rules", "Battle", RATE, "Notorious monster MP (experimental)",
  tip="The MP of notorious monsters. 1x = the era. Experimental.")
S("map.PLAYER_TP_MULTIPLIER", "rules", "Battle", RATE, "TP gain: you and your squad",
  tip="How fast you, your squad mates and pets gain TP. 1x = the era.")
S("map.MOB_TP_MULTIPLIER", "rules", "Battle", RATE, "TP gain: monsters",
  tip="How fast monsters gain TP, so how often they use their special attacks. 1x = the era.")
# (2026-11-22, Poptart; the user: the one "damage taken" rule and the per-type ones as well) Damage: what you take, and
# what each kind of attack of yours deals. A monster's own spells and special attacks are not touched by the "you deal"
# lines (server: scripts/globals/spells/damage_spell.lua, calculateSkillTypeMultiplier).
S("main.PLAYER_DAMAGE_TAKEN_MULTIPLIER", "rules", "Damage", RATE, "Damage you and your squad take",
  tip="Every hit, spell and breath that lands on you or a squad mate. 1x = the era, 0.5x = half, 2x = double. It sits "
      "apart from the damage reduction on gear, so gear still counts in full. Bot players and trusts are not changed. (Poptart)")
S("main.WEAPON_SKILL_POWER", "rules", "Damage", RATE, "You deal: weapon skills",
  tip="Damage of your and your squad's weapon skills. 1x = the era.")
S("main.ELEMENTAL_POWER", "rules", "Damage", RATE, "You deal: elemental magic",
  tip="Damage of elemental magic (Fire, Stone, Thunder and the like) cast by you, your squad, trusts and pets. 1x = the era.")
S("main.DARK_POWER", "rules", "Damage", RATE, "You deal: dark magic",
  tip="Damage of dark magic (Bio, Drain and the like) cast by you, your squad, trusts and pets. 1x = the era.")
S("main.DIVINE_POWER", "rules", "Damage", RATE, "You deal: divine magic",
  tip="Damage of divine magic (Banish, Holy) cast by you, your squad, trusts and pets. 1x = the era.")
S("main.NINJUTSU_POWER", "rules", "Damage", RATE, "You deal: ninjutsu",
  tip="Damage of ninjutsu (Katon, Hyoton and the like) cast by you, your squad and trusts. 1x = the era.")
S("main.BLUE_POWER", "rules", "Damage", RATE, "You deal: blue magic",
  tip="Damage of blue magic. 1x = the era.")
S("main.ENABLE_COP", "rules", "Expansions", FLAG, "Chains of Promathia")
S("main.ENABLE_TOAU", "rules", "Expansions", FLAG, "Treasures of Aht Urhgan")
S("main.ENABLE_WOTG", "rules", "Expansions", FLAG, "Wings of the Goddess",
  tip="Cavernous Maws and the past zones, the WotG missions and quests, Dancer and Scholar, and the new spells and "
      "abilities for every job. The level cap stays as set. Your game needs the Wings of the Goddess data files.")
S("main.ERA_RULES_WOTG", "rules", "Expansions", FLAG, "Keep Aht Urhgan-era balance",
  tip="With Wings of the Goddess on: weapon skills, damage caps, job and pet numbers and experience stay as they were "
      "before WotG's updates (modules/custom/lua/era_rules.lua). Off = the later retail numbers.")
S("map.DROP_RATE_MULTIPLIER", "rules", "Loot and gil", RATE, "Monster item drops")
S("map.MOB_GIL_MULTIPLIER", "rules", "Loot and gil", RATE, "Gil from monsters")
S("main.GIL_RATE", "rules", "Loot and gil", RATE, "Gil from quests")
S("map.ALL_MOBS_GIL_BONUS", "rules", "Loot and gil", NUMBER, "Gil from every monster", step=1,
  tip="Every monster drops this much gil for each of its levels, on top of what it carries anyway: at 5, a level 30 "
      "monster drops 150 gil more. 0 = off, the era: only beastmen and a few others carry gil. (VRTRA)")
S("main.SEAL_DROP_MINUTES", "rules", "Loot and gil", NUMBER, "Wait between seals (minutes)", step=1,
  tip="After a Beastmen's or Kindred's Seal drops, your party gets no other for this many minutes. 5 = as it has "
      "been here, 0 = no wait: every monster that can drop one may. Made for worlds without an auction house, "
      "where seals are the way to spells and gear. (delukard)")
S("main.AH_PRICE_RATE", "rules", "Loot and gil", RATE, "Auction house prices",
  tip="What things cost on the auction house: the simulator's listings and the bot players' own sales. 1x = the "
      "prices as they are, lower is cheaper, higher is dearer. A change restocks the auction house at your next PLAY.")
S("main.CASKET_DROP_RATE", "rules", "Loot and gil", PERCENT, "Treasure casket chance", step=0.05)
S("main.TABS_RATE", "rules", "Loot and gil", RATE, "Tabs from Fields of Valor")
S("fast_travel", "rules", "Travel", SWITCH, "Fast travel", keys=("main.HOMEPOINT_TELEPORT", "main.ENABLE_SURVIVAL_GUIDE"),
  command="set_fast_travel",
  tip="Home Point and Survival Guide teleports (touch one once, then teleport to it for a fee). "
      "Off = classic travel: walk, chocobos, airships and Teleport spells.")
S("map.BASE_SPEED", "rules", "Travel", NUMBER, "Run speed", step=5, tip="50 = retail.")
S("map.MOUNT_SPEED", "rules", "Travel", NUMBER, "Mount speed", step=5, tip="Chocobos and other mounts. 80 = retail.")
S("main.SNEAK_INVIS_DURATION_MULTIPLIER", "rules", "Travel", RATE, "Sneak and Invisible duration",
  tip="How long Sneak, Invisible and Deodorize last. 1x = the era's (a random 30 seconds to 5 minutes), "
      "2x = twice as long. (Yache)")
S("map.SKILLUP_CHANCE_MULTIPLIER", "rules", "Skills and crafting", RATE, "Combat and magic skills",
  tip="How often combat and magic skills go up.")
S("map.BLUE_LEARN_MULTIPLIER", "rules", "Skills and crafting", RATE, "Learning blue magic",
  tip="How often a Blue Mage learns a spell from a monster it defeats. 1x = retail (about 1 in 3 when your skill is close enough), "
      "2x = about 2 in 3, 3x = nearly every time. Your blue magic skill still has to be close enough to the spell's level.")
S("map.CRAFT_CHANCE_MULTIPLIER", "rules", "Skills and crafting", RATE, "Crafting skill-ups")
S("map.CRAFT_HQ_CHANCE_MULTIPLIER", "rules", "Skills and crafting", RATE, "High-quality crafts")
S("map.FISHING_SKILL_MULTIPLIER", "rules", "Skills and crafting", RATE, "Fishing skill-ups")
S("main.DIG_SKILL_RATE", "rules", "Skills and crafting", RATE, "Chocobo digging skill",
  tip="How much each find while chocobo digging counts toward your digging skill. 1x = the era (months to reach 100), "
      "2x = twice as fast. There is no daily digging limit on your own world. (delukard)")
S("map.FISHING_MINIGAME", "rules", "Skills and crafting", FLAG, "Fishing minigame",
  tip="On = today's fishing, where you fight the fish on screen. Off = era fishing: the bite line tells you what is on "
      "the hook, then you reel in (confirm) or let it go (cancel). The fishing screen still opens, but there is nothing "
      "to win in it: your skill decides the catch, lost catches and broken lines or rods.")
S("all_crafts", "rules", "Skills and crafting", SWITCH, "Every craft can reach 100",
  tip="Off = only one craft can reach 100, like the retail rule.")
S("full_bags", "rules", "Comforts", SWITCH, "Full bags from the start",
  tip="Inventory, Mog Safe, Mog Satchel, Mog Sack, Mog Case and every Mog Wardrobe open at 80. Off = the classic way: "
      "30 slots, and the Gobbiebag quests (and Phoenix's wardrobe rewards) add space. Bags never shrink.")
S("modern_stacks", "rules", "Comforts", SWITCH, "Modern item stacks",
  tip="Items stack as in today's game (sheepskin, goblin helms and the like to 12, and some to 99). "
      "Off = the era: most of those don't stack at all.",
  note="Before switching this off, empty or split your stacks of those items.")
S("short_quest_waits", "rules", "Comforts", SWITCH, "Short quest waits",
  tip="Chocobo's Wounds 1 minute between feedings (era: a game day each), Forge Your Destiny 1 hour at the forge "
      "(era: three game days), Aht Urhgan missions about 1 minute between missions (era: a game day or Japanese "
      "midnight). Off = the era waits.")
S("main.NEW_CHARACTER_CUTSCENE", "rules", "Comforts", FLAG, "New-character cutscenes")
# (2026-11-22, suggestions) out of era, so off by default
S("main.CASKET_SHOW_CODE", "rules", "Comforts", FLAG, "Caskets tell you the code",
  tip="A locked treasure casket tells your party its two-digit combination when you touch it; enter it to open. "
      "Off = the era's guessing game.")
S("main.GUILD_SHOPS_ALWAYS_OPEN", "rules", "Comforts", FLAG, "Guild shops always open",
  tip="Guild shops have no closing hours and no weekly holiday. On by default. Off = the era: each guild shop keeps "
      "its opening hours. (Dugahst)")
S("main.GUILD_SHOPS_ALWAYS_STOCKED", "rules", "Comforts", FLAG, "Guild shops never run out",
  tip="Everything a guild shop stocks is back to its usual amount whenever you shop there, even right after you bought "
      "it out. Prices stay the game's own. Off = the era: stock refills a little each day.")
S("map.FULL_MERITS", "rules", "Comforts", FLAG, "Full merits",
  tip="Every merit can be raised to its own maximum. Off = the era's group limits (for example only one attribute "
      "to 5/5, and only a few combat skills to 8/8).")
S("map.AH_ANYWHERE", "rules", "Comforts", FLAG, "Auction house from anywhere",
  tip="For the ahgo add-on (OPTIONS > Addons): its /ah command opens the auction house wherever you stand, and with "
      "this on you can bid and sell there from any area. Off = the era: the auction house only answers in areas "
      "that have one, so /ah works in the cities and nowhere else. (Velderen)")
S("main.LAND_KINGS_TIMED", "rules", "Comforts", FLAG, "Land kings on a timer",
  tip="Fafnir, Adamantoise and Behemoth. Off = as it has been here: you call one at its ??? with the item "
      "(Honey Wine, Blue Pondweed, Beastly Shank). On = the era: the ??? is gone, a king appears by itself 21 to 24 "
      "hours after the last one fell, and from the fourth kill in a row Nidhogg, Aspidochelone or King Behemoth "
      "can come in its place. The hours count while the servers are off too. (sparkiie)")
S("main.EPHEMERAL_MOOGLES", "rules", "Comforts", FLAG, "Ephemeral Moogles",
  tip="The crafting guilds' Ephemeral Moogles (from Seekers of Adoulin) are there and keep your crystals for you. "
      "On by default. (Gilder, stanky kong)")
S("main.ANCESTRY_MOOGLES", "rules", "Comforts", FLAG, "Ancestry Moogles",
  tip="The Ancestry Moogles in Port San d'Oria, Port Bastok and Windurst Walls (from Seekers of Adoulin) change your "
      "race, face, hair and size, free and as often as you like. On for a new install. (Yenkei)")
S("main.TREASURE_WAIT_MULTIPLIER", "rules", "Comforts", RATE, "Chest and coffer wait", step=0.25,
  tip="After a treasure chest or coffer is opened, the next one in that area is an illusion (no loot) for 15 to 60 "
      "minutes. 1x = the era, 0.5x = half as long, 0 = every chest and coffer gives its loot. (Rysan, Frost)")
S("map.MAX_MERIT_POINTS", "rules", "Comforts", NUMBER, "Merit points you can hold", step=5,
  tip="30 = the default here (the earliest era held 10). Up to 99.")

# ---------------------------------------------------------------- Rules > Tetra Master (2026-11-21)
S("main.TM_CARD_DROP_RATE", "rules", "Tetra Master", RATE, "Cards from monsters",
  tip="How often monsters and notorious monsters drop their Tetra Master card. 1x = about 1 in 50 kills for a common "
      "card, 0x = no cards from monsters.")
S("main.TM_CASKET_CARD_RATE", "rules", "Tetra Master", RATE, "Cards from caskets",
  tip="How often a treasure casket holds a Tetra Master card. 1x = about 1 in 7 caskets, 0x = none.")
S("main.TM_GIL_RATE", "rules", "Tetra Master", RATE, "Gil for a win",
  tip="Gil for beating the computer. 1x = 100 / 300 / 800 gil on Easy / Normal / Hard (double for a perfect game).")
S("main.TM_PRICE_RATE", "rules", "Tetra Master", RATE, "Card prices",
  tip="What card traders like Luto Mewrilah charge. 1x = 150 to about 1,100 gil a card.")

# ---------------------------------------------------------------- Rules > Squad: rules for the whole squad
# (2026-11-21, Hurami: moved from the Squad page's top line to the Rules page, in a Squad section)
S("squad_call_cooldown", "rules", "Squad", COUNT, "Call timer (min)", lo=0, hi=30, step=1,
  tip="Minutes before a squad mate can be called again. 0-30.")
S("spell_scrolls", "rules", "Squad", SWITCH, "Spells from scrolls",
  tip="Spells of level 18 and up must be bought and given to your squad once (trade the scroll to a mate, or "
      "!squad give). Blue magic from 18 is learned from monsters you defeat with a squad Blue Mage out. "
      "Below 18 everything stays automatic.")
S("squad_keep_gear", "rules", "Squad", SWITCH, "Keep gear you give",
  tip="Trading a piece to a mate (or !squad give) unlocks it for the whole squad and you keep yours. "
      "Off = the squad takes the piece (one-of-a-kind gear is always kept).")
S("squad_all_gear", "rules", "Squad", SWITCH, "Squad gets all gear",
  tip="Every piece of gear counts as given to your squad: mates can wear anything their job and level allow, "
      "without trading it to them first. With Auto-equip on (the Squads menu in game) they then put on the best of "
      "all of it for their job. Off = gear has to be given once (trade it, or !squad give).")
S("main.SQUAD_MATES_RAISABLE", "rules", "Squad", FLAG, "Fallen mates can be Raised",
  tip="A squad mate that falls stays where it fell for 5 minutes; Raise, Raise II, Raise III or Arise brings it back. "
      "Off = it is sent home at once. On by default. (Meli)")
S("main.SQUAD_UNLIMITED_JUICE", "rules", "Squad", FLAG, "Unlimited juice",
  tip="A squad mate with none of the juices you gave it drinks one for its level, free, when its MP runs low. Off = "
      "only the juices you trade to it. (Frost)")
S("training_dummies", "rules", "Squad", SWITCH, "Training dummies",
  tip="For testing: !sandbox puts dummies of level 1 to 99 in Rolanberry Fields that never die and never attack. "
      "Off for a new install; on = the dummies are there.")

# ---------------------------------------------------------------- Rules > Party buffs (2026-11-23)
BUFF_RANGE_WARNING = ("Extended keeps the old party-wide reach: buffs land on every party member and squad mate at any distance. "
                      "Some add-ons that move your party automatically (positioning, songs, rolls, healer placement) may not "
                      "work with Retail, and that is the reason to pick Extended. Retail is recommended.")
BUFF_RANGE_NOTE = ("Retail: a buff lands only on mates standing inside the effect's radius, like real players, so positioning "
                   "matters. Extended: it lands on everyone in the party, wherever they stand, so placement has no effect.")
S("buff_range", "rules", "Party buffs", CHOICE, "Buff range",
  options=(("retail", "Retail (recommended)"), ("extended", "Extended")),
  tip="Retail: trusts, squad mates and pets are covered by party buffs (Protectra, Curaga, songs, rolls, Warcry) only inside "
      "the effect's radius, like real players, and cast at the normal spell range. Gambits and Squads Revamped movement is "
      "designed for Retail range. Extended is supported for buffs only; positioning is not tuned for it."
      "\n\n" + BUFF_RANGE_WARNING + "\n\n" + BUFF_RANGE_NOTE)

# ---------------------------------------------------------------- Era: the dev PC only (players are locked to the era values)
S("main.MAX_LEVEL", "era", "Era", NUMBER, "Level cap", dev=True, step=1)
S("era_exp", "era", "Era", SWITCH, "Aht Urhgan-era experience tables", dev=True,
  tip="Kill exp and the per-monster cap. Keep 'From monsters' at 1 with this on.")
S("main.RESTRICT_CONTENT", "era", "Era", FLAG, "Hide switched-off content", dev=True)
S("main.HALLOWEEN_2005", "era", "Era", FLAG, "Harvest Festival", dev=True, tip="Oct 20 - Nov 1.")
S("main.ENABLE_ACP", "era", "Later expansions", FLAG, "A Crystalline Prophecy", dev=True)
S("main.ENABLE_AMK", "era", "Later expansions", FLAG, "A Moogle Kupo d'Etat", dev=True)
S("main.ENABLE_ASA", "era", "Later expansions", FLAG, "A Shantotto Ascension", dev=True)
S("main.ENABLE_ABYSSEA", "era", "Later expansions", FLAG, "Abyssea", dev=True)
S("main.ENABLE_SOA", "era", "Later expansions", FLAG, "Seekers of Adoulin", dev=True)
S("main.ENABLE_ROV", "era", "Later expansions", FLAG, "Rhapsodies of Vana'diel", dev=True)
S("main.ENABLE_TVR", "era", "Later expansions", FLAG, "Voracious Resurgence", dev=True)
S("main.ENABLE_VOIDWATCH", "era", "Out-of-era content", FLAG, "Voidwatch NPCs", dev=True)
S("main.ENABLE_TRUST_QUESTS", "era", "Out-of-era content", FLAG, "Trust quest NPCs", dev=True)
S("main.ENABLE_DAILY_TALLY", "era", "Out-of-era content", FLAG, "Gobbie Mystery Box", dev=True)
S("main.ROE_EXP_RATE", "era", "Out-of-era content", RATE, "RoE experience", dev=True,
  tip="Experience from Records of Eminence.")
S("map.CAPACITY_RATE", "era", "Out-of-era content", RATE, "Capacity points", dev=True)
S("main.SPARKS_RATE", "era", "Out-of-era content", RATE, "RoE sparks", dev=True, tip="Sparks from Records of Eminence.")

# which sections sit in which column of a page, left to right
LAYOUT = {
    "world": (("Town crowds", "Field parties"), ("Bot players", "Auction house", "Conquest"), ("AI chat", "Seasonal events")),
    "rules": (("Experience and fame", "Notorious monsters", "Battle", "Damage"), ("Loot and gil", "Travel", "Squad", "Expansions"),
              ("Skills and crafting", "Comforts", "Tetra Master", "Party buffs")),
    "squad": (("Squad rules",),),
    "era": (("Era",), ("Later expansions",), ("Out-of-era content",)),
}

# keys collect() returns that are not settings a person picks
INTERNAL = {"bots_head_start_done", "claim_shield", "defaults_version", "training_dummies_explicit"}


def covered_keys():
    """Every rates.json key that has a place on the new pages (a line above, or a section's own switch)."""
    keys = set(MASTERS.values())
    for entry in SETTINGS:
        keys.update(entry["keys"])
    return keys


def missing_keys(rates):
    """Keys of a collected set of rates that the new pages do not show (should be empty)."""
    return sorted(set(rates) - covered_keys() - INTERNAL)


def section_entries(page, section, player=False):
    return [e for e in SETTINGS if e["page"] == page and e["section"] == section and not (player and e["dev"])]


def sections(page, player=False):
    """The page's columns, each a list of (section title, entries); sections with nothing to show are left out,
    except those that are only a switch beside the title."""
    columns = []
    for names in LAYOUT[page]:
        column = []
        for name in names:
            entries = section_entries(page, name, player)
            if entries or name in MASTERS:
                column.append((name, entries))
        columns.append(column)
    return columns


def preset_now(core, rates, names, player=False):
    """Which of the named rate presets the rates match exactly (the first one), or None.
    player: a player install keeps the hidden options at their era values (core.lock_player_rates), so its rates are
    compared with the preset after the same lock. (2026-11-22, EyalRA: Relaxed solo and Fast were never shown as
    SELECTED there, and counted as "your own rates", because both presets set hidden options.)"""
    for name in names:
        want = core.apply_preset(rates, name)
        if (core.lock_player_rates(want) if player else want) == rates:
            return name
    return None
