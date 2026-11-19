Voice layer for the Vana'diel Living World pack. One record per distinct pack line ("template"), numbered in pack
order after stock endings are cut and zone/job names become {zone}/{job}. build_dialogue.py checks that every template
has exactly one record.

  num|tags|casual line|polite line (optional: default is the pack's own wording)
  num|x|why it is left out
  num|npc                         kept as written, for the NPC phase
  num|emote:wave                  a real game emote instead of a "*waves*" text line
  num|pair|first line|>answer     two bots in town
  +id|tags|casual|polite          a new line of ours (id becomes fo_<id>)

scenes.txt:  Sxx|tags  then  role|casual|polite (optional)   or  Sxx|x|why

Tags (where a line may be used):
  ls, say, party, pair
  r.<kind>     answers: greet bye thanks yw yes no maybe unsure agree alt congrats sympathy encourage help newbie
               question calm where doing job misc laugh back
  e.<event>    only after the real event: login logout wb (you log in) wb_long (after 3+ days) join levelup
               levelup_react death death_react win win_react wipe rankup rankup_react gear gear_react jobchange craft
               quest bcnm_start lfp lfm party_end raised loot_react
  @<cond>      only when true for the speaker: town field hunt craft mage morning night busy quiet endgame exp
               leader rival gossip party lowlevel
Slots (filled with real values, or the line is not used): {camp} {here} {job} {lvl} {sub} {member} {player} {doing}
Lines must be plain ASCII, at most about 110 characters once filled, with no '*' and no '|'.

squad.txt (the pack's squad section, used by squad_pack.lua):
  Qnn|tags|text override (optional: default is the pack's wording)    Qnn|x|why
  QSn|tags                                                            QSn|x|why
  tags: s.recruit s.ack_hold s.ack_follow s.ack_pull s.battle s.lowhp s.lowmp s.after s.reply s.down s.wipe s.idle_town
        s.idle_field s.banter s.bond s.jobchange s.jobchange_whm s.bench s.reunion s.race s.gender
        scenes: s.scene_first s.scene_lowhp s.scene_wipe s.scene_rest s.scene_return
  Who may say a line (role, race, gender, familiarity) comes from the pack's own tags. Only {name} may be used.

squad_more.txt (our own squad lines and scenes, on top of the pack's; same tags):
  +id|tags|who|text          who: empty (any mate) or key=a/b;key=c   keys: role (tank healer hybrid support damage),
                             voice (bold calm cheerful gruff: the mate's voice from squad_dialogue.lua), fam (new steady
                             trusted), race (Hume Elvaan Tarutaru Mithra Galka), gender (male female)
  +scene:id|tag|cooldown     then one  role|text  per line (roles tank healer damage support; support = any non-healer)
  Written without contractions, like the rest of the squad's lines (the builder warns on "I'll", "don't" ...).

voice_d.txt: our second batch of bot lines (+id records): answers players hear most when the AI is off, and lines for
  the linkshell events that come up often. Reactions (*_react) must not use {lvl} {job} {sub} {doing}: those would be
  the speaker's own, not the member's (the builder refuses it), and answers (r.*) have no {member}.

crowd.txt (the pack's crowd section, used by crowds_pack.lua through crowds_chat.lua):
  Cnnn|ok                                        used as written
  Cnnn|ok|opts|casual override|polite override   opts: place=..., lvl=a-b, jobs=A/B, when=night|evening|morning
     places: any jeuno upper_jeuno notjeuno sandoria bastok windurst nation whitegate small_town ferry outpost
  Cnnn|x|why                                     left out
  Pnn|ok|opts|A override|B override   /   Pnn|x|why        (two-line exchanges, said in town)
  Fields: {job} {lvl} {sub} {sublvl} {camp} {range} {need} {item} {price} {ls} {nation} {mission} {endgame} {self}
          and {name} (the player, react/greet only).
