# Credits

XI: Forever Offline is an unofficial, non-commercial fan project. It is not affiliated with or endorsed by Square Enix.

## Square Enix
FINAL FANTASY is a registered trademark of Square Enix Holdings Co., Ltd.
FINAL FANTASY XI © SQUARE ENIX CO., LTD. All rights reserved.

The official illustrations in `art-src/`, the launcher pictures built from them in `assets/ui/` and `assets/press/`,
and the item icons in `assets/item-icons/` are Square Enix material, used in tribute and credited here. They are not
covered by this project's license. If Square Enix asks for any of it to be removed, it will be.

The "XI: Forever Offline" wordmark is our own lettering and contains no Square Enix artwork.

Tetra Master, its cards, characters and the Quad Mist music come from FINAL FANTASY IX, FINAL FANTASY X and the
PlayOnline Tetra Master game, (c) SQUARE ENIX CO., LTD. They are used in tribute, as above.

## Server
- [Phoenix](https://github.com/phoenixffxi/Phoenix), with its xiloader and Era-DATs: the 75-era server this project is built on (GPL v3).
- [LandSandBoat](https://github.com/LandSandBoat/server): the FFXI server emulator Phoenix is based on (GPL v3).
- [AirSkyBoat](https://github.com/AirSkyBoat/AirSkyBoat): the Starlight Celebration's Smilebringer activities (presents, greetings, Goblin Merrymakers, Boot Camp, token and vendor moogles) and the Goblin routes and Jeuno decorations, ported into modules/custom/lua/starlight_smilebringers.lua (GPL v3).

## Launcher
- [LocalXI](https://github.com/seamuswilkie31-dev/LocalXI) by seamuswilkie31-dev: the controller setup (OPTIONS > Controller, launcher_gamepad.py) is ported from its Gamepad.cs (GPL v3).

## Downloaded at install, not included here
Each comes from its official release page and keeps its own license.

| Tool | Author | License |
|---|---|---|
| [Ashita v4](https://github.com/AshitaXI/Ashita-v4beta) and its bundled addons and plugins | atom0s and the Ashita team and contributors | GPL v3 |
| [XIUI](https://github.com/tirem/XIUI) | Team XIUI | GPL v3 |
| [XIUIplus](https://github.com/Team-XIUI/xiuiplus-releases) | Team XIUI+ | see its release page |
| [AutoBot](https://github.com/Buckfutt/AutoBot-Ashita) | K0D3R | MIT |
| [mobdb](https://github.com/ThornyFFXI/mobdb) | Thorny | MIT |
| Journal ([Nexus Mods, FFXI mod 44](https://www.nexusmods.com/finalfantasy11/mods/44)) | Kxteel | MIT |
| [Chains](https://github.com/NerfOnline/Chains) | Sippius, Ivaar and NerfOnline | see its release page |
| [XISpeaks](https://github.com/lord-daeloth/XISpeaks) (optional download, NPC voices) | lord-daeloth | GPL v3; each voice has its own terms (VOICE-LICENSES.md in the download) |
| [Nameplate](https://github.com/Shirk/Nameplate) | Shirk (HealsCodes) / BunnyBox Productions | GPL v3 (0.60 build ships with the kit, unchanged; source at the link) |
| [XIPivot](https://github.com/HealsCodes/XIPivot) | Renee Koecher (HealsCodes) | BSD 3-Clause |
| [Cadence](https://github.com/KiplingFFXI/cadence) | KiplingFFXI | GPL v3 |
| [Checkmate](https://github.com/KiplingFFXI/checkmate) | KiplingFFXI | GPL v3 |
| [Momentum](https://github.com/KiplingFFXI/momentum) | KiplingFFXI | GPL v3 |
| [tCrossBar](https://github.com/ThornyFFXI/tCrossBar) (add-on download, unchanged) | Thorny | MIT |
| [FFXIPort](https://github.com/wildcabbagepatch/FFXIPort) (add-on download; its server module ships with the server, one change: follows the Fast travel switch) | wildthing | GPL v3 |
| [VanaFish](https://github.com/VanaDreams/vanadreams-launcher/tree/main/addons/vanafish) (add-on download, unchanged) | VanaDreams | used with the authors' permission |
| [VanaCam](https://github.com/VanaDreams/vanadreams-launcher/tree/main/addons/vanacam) (add-on download, unchanged; its camera core is XICamera's, BSD) | VanaDreams | used with the authors' permission |
| [charcapture](https://github.com/VanaDreams/vanadreams-launcher/tree/main/addons/charcapture) (downloaded into the other game's Ashita by the Characters page; `char_import.py` reads its snapshots) | VanaDreams | used with the authors' permission |
| [xiloader (Phoenix)](https://github.com/phoenixffxi/xiloader) | Phoenix / LandSandBoat | GPL v3 |
| Gambatte (libretro core, used by Crystal Boy) | the Gambatte and libretro authors | GPL v2 |
| dgVoodoo | Dege | see its site |
| ReShade | crosire and contributors | see its site |
| [Ollama](https://ollama.com) and the chosen AI model (optional) | Ollama; the model's authors | their own terms |

## Our own work
The launcher, tools, server modules (squad, bots, crowds, caskets, era experience, Crystal Boy questline and others)
and the Gambits, GambitsV2, Crystal Boy, followme, servermenu and squadpanel addons were written for this project.
Gambits began as the TitanGambits engine and was brought here by its author.

## Music
All of the launcher's music was made for XI: Forever Offline by **JØ (jnull)**, our Head of Music.
- "A Place to Return": the launcher's opening theme (`assets/press/default.mp3`).
- "Beyond the Veil": the 8-Bit theme's song (`assets/press/beyond_the_veil.mp3`).
- "TOMORROW.EXE": the Aero theme's song (`assets/press/tomorrow_exe.mp3`), by JØ with **Nox** (her voice, with JØ's).
- "No Signal, All Vibes": the Vaporwave theme's song.
- The Vaporwave theme's opener: a short piece that plays the first time the launcher opens, before "No Signal, All Vibes"
  takes over.

The songs were made with Suno. `assets/press/music.json` holds the same list for the launcher: OPTIONS > Theme names the
song that plays and who made it.

## Contributors
- **Levi Masterson ([levmast](https://github.com/levmast))**: the game switch fix for installs made with Square Enix's
  official installer (Windows Installer descriptors lifted while the game runs, so the copy's DLLs load).
- **[wildcabbagepatch](https://github.com/wildcabbagepatch)**: GambitsV2, the in-game Squad Rule Set editor, and its
  server side (squad Rule Sets, job ability rules for squad mates, the `!gsq` command).
- **JØ (jnull)**, Head of Music: all of the launcher's music (see Music, above), and *Living Vana'diel, Writing
  Contribution #001* (with Nox): squad mate lines for the four voices, three squad scenes, bot player and linkshell lines
  and town lines for San d'Oria, Bastok, Windurst, Jeuno, Selbina and Mhaura.
- **Records of Vana'diel** (a pack of FINAL FANTASY XI characters drawn as 8 / 16-bit sprites): the characters on the
  buttons and the title banner of the launcher's 8-Bit theme (`assets/press/8bit-ui`; the sprites used are in
  `art-src/8bit-sprites`).

## Tetra Master
- **[Nalfey](https://github.com/Nalfey/TetraMaster)**: all the card art, character portraits, board graphics, coin,
  cursor and explosion animations and the sounds in `tetramaster/assets/` (his own redrawn work), and the original
  Tetra Master add-on for FFXI, whose rules our server version follows exactly. Used with his permission.
- Cinzel font: Natanael Gama (SIL Open Font License).
- Kanit font (the lettering on the XIFO banner): Cadson Demak (SIL Open Font License).
- Righteous font (the neon sign on the XIFO banner): Astigmatic (SIL Open Font License).
- DotGothic16 font (the pixel and Japanese lettering on the vaporwave banners): Fontworks (SIL Open Font License).
- Galmuri11 font (the launcher's lettering in the 8-Bit theme; `assets/press/fonts` holds a Latin-only cut of its Regular
  and Bold, with the licence): Lee Minseo (quiple) (SIL Open Font License).
- Selawik font (the lettering on the Aero theme's buttons and banners; `art-src/fonts`, with the licence): Microsoft
  Corporation (SIL Open Font License).
- **Aero theme** pictures (`assets/press/aero-ui`, `assets/press/aero_*__theme-aero.jpg`): drawn in code by
  `art-src/scripts/aero_buttons.py` and `aero_banners.py` around official FINAL FANTASY XI art from the art pack (the 2002
  character designs, the Behemoth concept drawing, and in-game screenshots of Trion, Excenmille and two beaches),
  © SQUARE ENIX. The window frames, taskbar and orb are original drawings in the style of the time, not Microsoft's.

## Crystal Boy mini games

Free Game Boy games shipped with the kit (`crystalboy-games`):
- **Legend of Jueno**, **Legend of Jueno 2**, **Legend of Jueno 3**, **Legend of Jueno 4**: written for this project, included with the author's permission.
- **Dragonland I**, **Dragonland II**, **Dragonland III**, **Dragonland IV**, **Dragonland V**: provided by the project owner, included with the owner's permission. Only their header titles were changed (`DRAGONLAND 1`-`5`) so the addon can tell the five apart.
