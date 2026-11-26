"""Builds venture_data.json: the classic exp camps squad mates go to on a Venture (the XIFO app), with the real
monsters, levels, elements and drop lists from YOUR server's own data.

  python dev\\ventures\\build_venture_data.py --server C:\\ffxi-local\\server

Reads data/zones/<zone>/mobs.yaml + data/ecosystems.yaml (patched by the modules in modules/init.txt, exactly like
build_mobdb_data.py) and sql/item_basic.sql. The hub (dev/armory/ventures.py) simulates the camps from this file, and
the app gets the camp list (names, levels, scenery) from the hub. Needs PyYAML.

Camps: the real ones of the era (levels 1-9 are solo spots outside the cities; parties start at 10). Each names the
monsters people actually fought there; the builder checks every one exists in your data and keeps its level range.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, KIT)
import build_mobdb_data as B  # noqa: E402

CHANCE = {"always": 1000, "very_common": 240, "common": 150, "uncommon": 100, "rare": 50, "very_rare": 10,
          "super_rare": 5, "ultra_rare": 1}

# id, zone folder, title, spot, mate levels lo-hi, solo?, scenery key, monsters (template names)
CAMPS = [
    # ---------------------------------------------------------------- solo, levels 1-9
    ("ronfaure", "east_ronfaure", "East Ronfaure", "the woods outside San d'Oria", 1, 6, True, "ronfaure",
     ["Forest_Hare", "Carrion_Worm", "Scarab_Beetle", "Forest_Funguar", "Wild_Sheep"]),
    ("gustaberg", "north_gustaberg", "North Gustaberg", "the cliffs outside Bastok", 1, 6, True, "gustaberg",
     ["Stone_Eater", "Maneating_Hornet", "Walking_Sapling", "Rock_Lizard", "Ornery_Sheep"]),
    ("sarutabaruta", "east_sarutabaruta", "East Sarutabaruta", "the plains outside Windurst", 1, 6, True, "sarutabaruta",
     ["Savanna_Rarab", "Crawler", "Mandragora", "River_Crab", "Pug_Pugil", "Giant_Bee"]),
    ("latheine", "la_theine_plateau", "La Theine Plateau", "the crag road", 5, 10, True, "latheine",
     ["Steppe_Hare", "Strolling_Sapling_LTP_KH", "Rock_Eater", "Huge_Wasp", "Mad_Sheep", "Akbaba_LTP"]),
    ("konschtat", "konschtat_highlands", "Konschtat Highlands", "the highland meadows", 5, 10, True, "konschtat",
     ["Strolling_Sapling_LTP_KH", "Huge_Wasp", "Mist_Lizard", "Mad_Sheep", "Rock_Eater"]),
    ("tahrongi", "tahrongi_canyon", "Tahrongi Canyon", "the canyon floor", 5, 10, True, "tahrongi",
     ["Canyon_Rarab", "Pygmaioi", "Killer_Bee", "Akbaba_TC", "Canyon_Crawler", "Wild_Dhalmel"]),
    # ---------------------------------------------------------------- parties
    ("valkurm_lizards", "valkurm_dunes", "Valkurm Dunes", "the lizard camp", 10, 15, False, "valkurm",
     ["Hill_Lizard", "Sand_Hare", "Goblin_Ambusher", "Goblin_Butcher", "Goblin_Tinkerer"]),
    ("valkurm_beach", "valkurm_dunes", "Valkurm Dunes", "the beach by Selbina", 14, 19, False, "valkurm",
     ["Snipper", "Damselfly", "Brutal_Sheep", "Thread_Leech", "Beach_Pugil", "Goblin_Mugger"]),
    ("buburimu", "buburimu_peninsula", "Buburimu Peninsula", "the cliffs near Mhaura", 14, 19, False, "buburimu",
     ["Zu", "Carnivorous_Crawler", "Bull_Dhalmel", "Snipper", "Sylvestre"]),
    ("jugner", "jugner_forest", "Jugner Forest", "the lake clearing", 16, 21, False, "jugner",
     ["Brutal_Sheep", "Forest_Leech", "Stag_Beetle", "Land_Pugil", "Jugner_Funguar", "Forest_Tiger"]),
    ("qufim", "qufim_island", "Qufim Island", "the shore below Delkfutt's Tower", 20, 25, False, "qufim",
     ["Clipper", "Greater_Pugil_QI", "Giant_Ranger", "Giant_Ascetic", "Giant_Trapper", "Giant_Hunter"]),
    ("korroloka", "korroloka_tunnel", "Korroloka Tunnel", "the water caverns", 22, 27, False, "korroloka",
     ["Thread_Leech", "Huge_Spider", "Clipper", "Greater_Pugil_KT_GM", "Combat_KT"]),
    ("gusgen", "gusgen_mines", "Gusgen Mines", "the lower shafts", 22, 28, False, "gusgen",
     ["Wendigo_war", "Amphisbaena", "Sadfly", "Mauthe_Doog_GM", "Myconid"]),
    ("rolanberry", "rolanberry_fields", "Rolanberry Fields", "the berry hills", 22, 28, False, "rolanberry",
     ["Death_Wasp", "Berry_Grub", "Goobbue_Farmer", "Clipper", "Moon_Bat"]),
    ("sauromugue", "sauromugue_champaign", "Sauromugue Champaign", "the old tower ruins", 26, 31, False, "sauromugue",
     ["Sauromugue_Skink", "Diving_Beetle", "Champaign_Coeurl", "Tabar_Beak", "Hill_Lizard"]),
    ("yuhtunga", "yuhtunga_jungle", "Yuhtunga Jungle", "the river bend", 28, 34, False, "yuhtunga",
     ["Yuhtunga_Mandragora", "Ivory_Lizard", "Death_Jacket_jungle", "Young_Opo-opo", "Goblin_Smithy", "Goblin_Furrier"]),
    ("bibiki", "bibiki_bay", "Bibiki Bay", "the beach at Port Bibiki", 29, 35, False, "bibiki",
     ["Coralline_Uragnite", "Jagil", "Coastal_Opo-opo", "Alraune", "Toucan", "Eft"]),
    ("oztroja", "castle_oztroja", "Castle Oztroja", "the yagudo halls", 30, 36, False, "oztroja",
     ["Yagudo_Herald", "Yagudo_Drummer", "Yagudo_Oracle", "Yagudo_Interrogator", "Bulwark_Bat"]),
    ("attohwa", "attohwa_chasm", "Attohwa Chasm", "the miasma ridge", 33, 39, False, "attohwa",
     ["Flesh_Eater_AC", "Hecteyes_AC", "Gallinipper_AC", "Tracer_Antlion", "Doom_Scorpion"]),
    ("misareaux", "misareaux_coast", "Misareaux Coast", "the bugard cliffs", 35, 41, False, "misareaux",
     ["Gigantobugard", "Bugard", "Tavnazian_Sheep", "Death_Jacket_LM_MC", "Mantrap"]),
    ("yhoator", "yhoator_jungle", "Yhoator Jungle", "the opo-opo trees", 36, 42, False, "yhoator",
     ["Young_Opo-opo", "Yhoator_Wasp", "White_Lizard", "Worker_Crawler", "Goblin_Reaper"]),
    ("ssg", "sea_serpent_grotto", "Sea Serpent Grotto", "the sahagin pools", 38, 44, False, "ssg",
     ["Brook_Sahagin", "Rivulet_Sahagin", "Riparian_Sahagin", "Bigclaw_aggro", "Ironshell", "Royal_Leech"]),
    ("crawlers", "crawlers_nest", "Crawlers' Nest", "the nest tunnels", 38, 45, False, "crawlers",
     ["Worker_Crawler_CN", "Soldier_Crawler", "Maze_Lizard", "Nest_Beetle", "Labyrinth_Lizard_CN", "Doom_Scorpion"]),
    ("garlaige", "garlaige_citadel", "Garlaige Citadel", "the bat halls", 40, 47, False, "garlaige",
     ["Siege_Bat", "Borer_Beetle", "Citadel_Bats", "Wingrats_GC", "Demonic_Weapon"]),
    ("yhoator_tonberry", "yhoator_jungle", "Yhoator Jungle", "below the Temple of Uggalepih", 42, 48, False, "yhoator",
     ["Tonberry_Creeper", "Tonberry_Hexer", "Worker_Crawler", "Master_Coeurl", "Goblin_Poacher"]),
    ("oztroja_upper", "castle_oztroja", "Castle Oztroja", "the upper floors", 42, 48, False, "oztroja",
     ["Yagudo_Zealot", "Yagudo_Conquistador", "Yagudo_Lutenist", "Yagudo_Prior"]),
    ("gustav", "gustav_tunnel", "Gustav Tunnel", "the lizard tunnels", 43, 49, False, "gustav",
     ["Hawker", "Labyrinth_Lizard_GT", "Makara", "Greater_Gaylas", "Goblin_Robber"]),
    ("onzozo", "labyrinth_of_onzozo", "Labyrinth of Onzozo", "the cockatrice rooms", 47, 54, False, "onzozo",
     ["Cockatrice", "Mushussu_LO", "Goblin_Miner", "Goblin_Bouncer", "Flying_Manta"]),
    ("crawlers_deep", "crawlers_nest", "Crawlers' Nest", "the deep nest", 48, 54, False, "crawlers",
     ["Hornfly", "Exoray", "Blazer_Beetle", "Witch_Hazel", "Soul_Stinger"]),
    ("garlaige_upper", "garlaige_citadel", "Garlaige Citadel", "the upper citadel", 49, 56, False, "garlaige",
     ["Funnel_Bats_GC", "Droma_GC", "Fallen_Officer_war", "Explosure", "Chamber_Beetle"]),
    ("ssg_lower", "sea_serpent_grotto", "Sea Serpent Grotto", "the deep pools", 50, 57, False, "ssg",
     ["Marsh_Sahagin", "Swamp_Sahagin", "Bog_Sahagin", "Rock_Crab", "Razorjaw_Pugil"]),
    ("uleguerand", "uleguerand_range", "Uleguerand Range", "the snowfields", 55, 61, False, "uleguerand",
     ["Variable_Hare", "Snoll", "Uleguerand_Tiger", "Buffalo", "Glacier_Eater"]),
    ("kuftal", "kuftal_tunnel", "Kuftal Tunnel", "the crab tunnels", 56, 62, False, "kuftal",
     ["Robber_Crab", "Cave_Worm_KT", "Sand_Lizard", "Recluse_Spider"]),
    ("krt", "king_ranperres_tomb", "King Ranperre's Tomb", "the lower tomb", 56, 62, False, "krt",
     ["Tomb_Worm", "Dire_Bat", "Cherry_Sapling", "Armet_Beetle"]),
    ("boyahda", "the_boyahda_tree", "The Boyahda Tree", "the roots", 57, 64, False, "boyahda",
     ["Bark_Spider", "Death_Cap", "Mourioche", "Moss_Eater", "Robber_Crab"]),
    ("wajaom", "wajaom_woodlands", "Wajaom Woodlands", "the colibri trees", 58, 64, False, "wajaom",
     ["Worker_Pephredo", "Lesser_Colibri", "Aht_Urhgan_Attercop", "Wajaom_Tiger"]),
    ("ifrits", "ifrits_cauldron", "Ifrit's Cauldron", "the lava flats", 58, 64, False, "ifrits",
     ["Old_Opo-opo", "Volcano_Wasp", "Dodomeki", "Dire_Bat"]),
    ("caedarva", "caedarva_mire", "Caedarva Mire", "the murre marsh", 59, 66, False, "caedarva",
     ["Marsh_Murre", "Chigoe_Caedarva", "Puktrap", "Wild_Karakul", "Caedarva_Leech"]),
    ("den", "den_of_rancor", "Den of Rancor", "the lantern caves", 60, 68, False, "den",
     ["Tonberry_Trailer", "Tonberry_Slasher", "Mousse_DoR_PMS", "Dire_Bat", "Tonberry_Beleaguerer"]),
    ("bhaflau", "bhaflau_thickets", "Bhaflau Thickets", "the treant groves", 60, 67, False, "bhaflau",
     ["Lesser_Colibri", "Aht_Urhgan_Attercop", "Treant_Sapling_WW_BT", "Wajaom_Tiger", "Colibri"]),
    ("ssg_crabs", "sea_serpent_grotto", "Sea Serpent Grotto", "the crab grottos", 60, 69, False, "ssg",
     ["Robber_Crab_SSG", "Shore_Sahagin", "Delta_Sahagin", "Devil_Manta", "Greatclaw"]),
    ("kuftal_deep", "kuftal_tunnel", "Kuftal Tunnel", "the raptor halls", 62, 69, False, "kuftal",
     ["Recluse_Spider", "Deinonychus", "Sabotender_Sediendo", "Haunt"]),
    ("aydeewa", "aydeewa_subterrane", "Aydeewa Subterrane", "the flea caverns", 62, 69, False, "aydeewa",
     ["Fossorial_Flea", "Phlebotomic_Slug", "Slime_Mold", "Defoliator", "Mycohopper", "Mold_Eater"]),
    ("valley", "valley_of_sorrows", "Valley of Sorrows", "the raptor valley", 63, 70, False, "valley",
     ["Velociraptor", "Peryton"]),
    ("uleguerand_high", "uleguerand_range", "Uleguerand Range", "the high ridge", 64, 72, False, "uleguerand",
     ["Polar_Hare", "Nival_Raptor", "Mountain_Worm", "Giant_Buffalo", "Mindgazer"]),
    ("attohwa_high", "attohwa_chasm", "Attohwa Chasm", "the antlion pits", 64, 72, False, "attohwa",
     ["Sand_Lizard", "Monarch_Ogrefly", "Cutlass_Scorpion_AC", "Tracker_Antlion"]),
    ("zhayolm", "mount_zhayolm", "Mount Zhayolm", "the volcanic slopes", 66, 75, False, "zhayolm",
     ["Magmatic_Eruca", "Zhayolm_Apkallu", "Assassin_Fly", "Mountain_Clot", "Sicklemoon_Jagil"]),
    ("mamook", "mamook", "Mamook", "the lizard trails", 67, 75, False, "mamook",
     ["Carriage_Lizard", "Colibri", "Puk_M", "Hunting_Raptor", "Mamool_Ja_Zenist", "Mamool_Ja_Bounder"]),
    ("boyahda_top", "the_boyahda_tree", "The Boyahda Tree", "the high branches", 68, 75, False, "boyahda",
     ["Korrigan", "Processionaire", "Skimmer", "Elder_Goobbue", "Darter"]),
]

# The app's pixel look for a monster, from the server's species / family name (first match wins).
LOOKS = [
    ("mamool", "mamool"), ("sahagin", "sahagin"), ("tonberry", "tonberry"), ("yagudo", "yagudo"), ("goblin", "goblin"),
    ("orc", "goblin"), ("quadav", "goblin"), ("gigas", "gigas"), ("qiqirn", "goblin"), ("goobbue", "goobbue"),
    ("opo", "opo"), ("crab", "crab"), ("pugil", "pugil"), ("manta", "manta"), ("jagil", "manta"), ("uragnite", "uragnite"),
    ("rabbit", "rabbit"), ("rarab", "rabbit"), ("hare", "rabbit"), ("worm", "worm"), ("beetle", "beetle"),
    ("funguar", "funguar"), ("mushroom", "funguar"), ("sheep", "sheep"), ("karakul", "sheep"), ("buffalo", "buffalo"),
    ("bee", "bee"), ("wasp", "bee"), ("pephredo", "bee"), ("sapling", "sapling"), ("treant", "sapling"),
    ("mandragora", "mandragora"), ("raptor", "raptor"), ("wyvern", "raptor"), ("lizard", "lizard"), ("eft", "lizard"),
    ("crawler", "crawler"), ("eruca", "crawler"), ("bird", "bird"), ("murre", "bird"), ("colibri", "bird"),
    ("cockatrice", "cockatrice"), ("peryton", "bird"), ("apkallu", "bird"), ("dhalmel", "dhalmel"), ("fly", "fly"),
    ("leech", "leech"), ("bat", "bat"), ("skeleton", "skeleton"), ("ghoul", "skeleton"), ("corse", "skeleton"),
    ("spider", "spider"), ("hound", "hound"), ("coeurl", "coeurl"), ("tiger", "coeurl"), ("flytrap", "flytrap"),
    ("morbol", "flytrap"), ("hecteyes", "eye"), ("gazer", "eye"), ("antlion", "antlion"), ("scorpion", "scorpion"),
    ("bugard", "bugard"), ("weapon", "weapon"), ("slime", "slime"), ("flan", "slime"), ("slug", "slime"),
    ("clot", "slime"), ("snoll", "snoll"), ("chigoe", "flea"), ("flea", "flea"), ("puk", "puk"), ("bomb", "bomb"),
    ("cactuar", "cactuar"), ("ghost", "ghost"), ("doomed", "skeleton"), ("demon", "ghost"),
]
ECO_LOOK = {"beastmen": "goblin", "undead": "skeleton", "vermin": "beetle", "beast": "hound", "bird": "bird",
            "aquan": "crab", "plantoid": "sapling", "amorph": "slime", "lizard": "lizard", "arcana": "bomb",
            "demon": "ghost", "dragon": "raptor"}


def look_of(name, species, family, ecosystem):
    for key in (species, family, name):
        k = (key or "").lower()
        for part, look in LOOKS:
            if part in k:
                return look
    return ECO_LOOK.get(ecosystem, "slime")


def family_table(server):
    """species name -> (ecosystem, family, element)"""
    eco = B.load_merged(server, ["ecosystems.yaml"]).get("ecosystems", {})
    out = {}
    for eco_name, e in eco.items():
        e = e or {}
        for fam_name, f in (e.get("families") or {}).items():
            f = f or {}
            fel = ((f.get("attributes") or {}).get("element")) or ((e.get("attributes") or {}).get("element"))
            for sp_name, s in (f.get("species") or {}).items():
                s = s or {}
                el = ((s.get("attributes") or {}).get("element")) or fel or "dark"
                out[sp_name] = (eco_name, fam_name, el)
    return out


def loot_of(loot, items):
    """Plain drops as [item id, chance per 1000]; groups as {"g": chance, "of": [[item, weight], ...]}."""
    out = []
    for d in ((loot or {}).get("drops") or []):
        if not isinstance(d, dict):
            continue
        ch = d.get("chance", "common")
        ch = CHANCE.get(ch, ch) if isinstance(ch, str) else ch
        try:
            ch = max(1, min(1000, int(ch)))
        except (TypeError, ValueError):
            continue
        if isinstance(d.get("item"), str):
            iid = items.get(d["item"])
            if iid:
                out.append([iid, ch])
        elif "one_of" in d:
            one, pairs = d["one_of"], []
            if isinstance(one, dict):
                pairs = list(one.items())
            elif isinstance(one, list):
                for v in one:
                    if isinstance(v, str):
                        pairs.append((v, 1))
                    elif isinstance(v, dict) and isinstance(v.get("item"), str):
                        pairs.append((v["item"], v.get("weight", 1)))
            grp = [[items[n], int(w) if isinstance(w, (int, float)) else 1] for n, w in pairs if items.get(n)]
            if grp:
                out.append({"g": ch, "of": grp})
    return out


def item_names(server):
    names = {}
    for row in B.sql_rows(os.path.join(server, "sql", "item_basic.sql"), "item_basic"):
        try:
            names[int(row[0])] = row[2]
        except (ValueError, IndexError):
            pass
    return names


def pretty(name):
    small = {"of", "the", "a", "and"}
    return " ".join(w if (i and w in small) else w[:1].upper() + w[1:] for i, w in enumerate(name.replace("_", " ").split()))


TAGS = (" war", " blm", " LTP KH", " LTP", " TC", " KT GM", " GM", " QI", " AC", " CN", " GC", " GT", " LO", " SSG", " KT",
        " LM MC", " WW BT", " DoR PMS", " jungle", " aggro", " M")


def display(tn):
    name = tn.replace("_", " ")
    for tag in TAGS:
        if name.endswith(tag):
            name = name[: -len(tag)]
    return name.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "venture_data.json"))
    a = ap.parse_args(argv)
    fams = family_table(a.server)
    raw_items = item_names(a.server)
    by_name = {}
    for iid, n in raw_items.items():
        by_name.setdefault(n, iid)
    used, camps, zones, problems = set(), [], {}, []
    for cid, zdir, title, spot, lo, hi, solo, scene, mobs in CAMPS:
        if zdir not in zones:
            zones[zdir] = B.load_merged(a.server, ["zones", zdir, "mobs.yaml"])
        tpls, spawns = zones[zdir].get("templates") or {}, zones[zdir].get("spawns") or {}
        lv, zone_id = {}, None
        for sid, sp in spawns.items():
            tn = (sp or {}).get("template")
            if tn in mobs:
                level = sp.get("level") or [0, 0]
                cur = lv.get(tn, [99, 0, 0])
                lv[tn] = [min(cur[0], int(level[0])), max(cur[1], int(level[-1])), cur[2] + 1]
                zone_id = (int(sid) >> 12) & 0x1FF
        out_mobs = []
        for tn in mobs:
            tpl = tpls.get(tn)
            if not tpl or tn not in lv:
                problems.append(f"{cid}: {tn} not found in {zdir}")
                continue
            species = tpl.get("species") or ""
            eco, fam, el = fams.get(species, ("", "", "dark"))
            drops = loot_of(tpl.get("loot"), by_name)
            for d in drops:
                used.update([d[0]] if isinstance(d, list) else [x[0] for x in d["of"]])
            out_mobs.append({"name": display(str(tpl.get("display_name") or tn)), "t": tn, "lo": lv[tn][0], "hi": lv[tn][1],
                             "n": lv[tn][2], "eco": eco, "fam": fam, "el": el, "look": look_of(tn, species, fam, eco),
                             "beast": eco == "beastmen", "drops": drops})
        if not out_mobs:
            problems.append(f"{cid}: no monsters at all, camp left out")
            continue
        camps.append({"id": cid, "zone": zone_id, "zoneDir": zdir, "title": title, "spot": spot, "lo": lo, "hi": hi,
                      "solo": solo, "scene": scene, "mobs": out_mobs})
    used.update([1126, 1127] + list(range(4096, 4104)))
    items = {str(i): pretty(raw_items[i]) for i in sorted(used) if i in raw_items}
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"v": 1, "camps": camps, "items": items}, f, separators=(",", ":"), ensure_ascii=False)
    for p in problems:
        print("note:", p)
    print(f"{len(camps)} camps, {sum(len(c['mobs']) for c in camps)} monsters, {len(items)} items -> {a.out}")


if __name__ == "__main__":
    sys.exit(main())
