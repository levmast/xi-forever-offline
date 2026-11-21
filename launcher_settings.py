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
S("crowds_field_parties", "world", "Field parties", COUNT, "Parties per area", dev=True, lo=0, hi=3, step=1,
  tip="Players get this from their world choice.")
S("bots_online", "world", "Bot players", COUNT, "Online at a time", lo=0, hi=550, step=10,
  tip="How many bot players are logged in at once. Lower it if the game stutters. 0-550.")
S("bots_roster", "world", "Bot players", COUNT, "Roster size", lo=0, hi=600, step=50,
  tip="How many bot characters exist in your world. 0-600.")
S("bots_growth", "world", "Bot players", CHOICE, "Bot growth",
  options=(("off", "Off"), ("realistic", "Realistic"), ("fast", "Fast")),
  tip="Bots level, craft and earn gil while you are not playing.")
S("bots_pass_loot", "world", "Bot players", SWITCH, "Bots pass all loot",
  tip="Bot players in your party pass every drop at once, so it comes to you without waiting for the lot timer.")
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
}

# ---------------------------------------------------------------- Rules: how fast and how forgiving
S("map.EXP_RATE", "rules", "Experience and fame", RATE, "From monsters",
  tip="Keep this at 1 with the era experience tables: they already carry the era's pace.")
S("main.EXP_RATE", "rules", "Experience and fame", RATE, "From quests", tip="Experience from quests and scripts.")
S("main.BOOK_EXP_RATE", "rules", "Experience and fame", RATE, "From FoV/GoV pages", step=0.125,
  tip="Experience from Fields of Valor and Grounds of Valor pages.")
S("map.EXP_LOSS_RATE", "rules", "Experience and fame", RATE, "Lost on death", tip="0 = none.")
S("main.FAME_RATE", "rules", "Experience and fame", RATE, "Fame from quests", tip="1 = retail.")
S("main.NM_LOTTERY_CHANCE", "rules", "Notorious monsters", RATE, "Lottery spawn chance", special={-1: "always"},
  tip="Leaping Lizzy, Valkurm Emperor and the like. 1 = retail. One step below 0 is 'always': the NM always comes next.")
S("main.NM_LOTTERY_COOLDOWN", "rules", "Notorious monsters", RATE, "Wait after a kill",
  tip="The time after a kill before the NM can be rolled again. 1 = retail, 0 = none.")
S("main.ENABLE_COP", "rules", "Expansions", FLAG, "Chains of Promathia")
S("main.ENABLE_TOAU", "rules", "Expansions", FLAG, "Treasures of Aht Urhgan")
S("map.DROP_RATE_MULTIPLIER", "rules", "Loot and gil", RATE, "Monster item drops")
S("map.MOB_GIL_MULTIPLIER", "rules", "Loot and gil", RATE, "Gil from monsters")
S("main.GIL_RATE", "rules", "Loot and gil", RATE, "Gil from quests")
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
S("map.SKILLUP_CHANCE_MULTIPLIER", "rules", "Skills and crafting", RATE, "Combat and magic skills",
  tip="How often combat and magic skills go up.")
S("map.BLUE_LEARN_MULTIPLIER", "rules", "Skills and crafting", RATE, "Learning blue magic",
  tip="How often a Blue Mage learns a spell from a monster it defeats. 1x = retail (about 1 in 3 when your skill is close enough), "
      "2x = about 2 in 3, 3x = nearly every time. Your blue magic skill still has to be close enough to the spell's level.")
S("map.CRAFT_CHANCE_MULTIPLIER", "rules", "Skills and crafting", RATE, "Crafting skill-ups")
S("map.CRAFT_HQ_CHANCE_MULTIPLIER", "rules", "Skills and crafting", RATE, "High-quality crafts")
S("map.FISHING_SKILL_MULTIPLIER", "rules", "Skills and crafting", RATE, "Fishing skill-ups")
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
      "without trading it to them first. Off = gear has to be given once (trade it, or !squad give).")
S("training_dummies", "rules", "Squad", SWITCH, "Training dummies",
  tip="For testing: !sandbox puts dummies of level 1 to 99 in Rolanberry Fields that never die and never attack. "
      "Off = no dummies.")

# ---------------------------------------------------------------- Era: the dev PC only (players are locked to the era values)
S("main.MAX_LEVEL", "era", "Era", NUMBER, "Level cap", dev=True, step=1)
S("era_exp", "era", "Era", SWITCH, "Aht Urhgan-era experience tables", dev=True,
  tip="Kill exp and the per-monster cap. Keep 'From monsters' at 1 with this on.")
S("main.RESTRICT_CONTENT", "era", "Era", FLAG, "Hide switched-off content", dev=True)
S("main.HALLOWEEN_2005", "era", "Era", FLAG, "Harvest Festival", dev=True, tip="Oct 20 - Nov 1.")
S("main.ENABLE_WOTG", "era", "Later expansions", FLAG, "Wings of the Goddess", dev=True)
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
    "rules": (("Experience and fame", "Notorious monsters", "Expansions"), ("Loot and gil", "Travel", "Squad"),
              ("Skills and crafting", "Comforts")),
    "squad": (("Squad rules",),),
    "era": (("Era",), ("Later expansions",), ("Out-of-era content",)),
}

# keys collect() returns that are not settings a person picks
INTERNAL = {"bots_head_start_done", "claim_shield", "defaults_version"}


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


def preset_now(core, rates, names):
    """Which of the named rate presets the rates match exactly (the first one), or None."""
    for name in names:
        if core.apply_preset(rates, name) == rates:
            return name
    return None
