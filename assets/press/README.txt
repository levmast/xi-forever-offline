PRESS-KIT PICTURES FOR THE LAUNCHER
===================================
Put pictures here (png or jpg) and the launcher uses them:
  * the Home page shows one of them while nothing is running (a click shows the next; it also changes by itself about every 12 seconds)
  * they join the pictures that rotate while the game loads

Any size and shape works: each picture is scaled to fill the 920 x 368 frame and the extra is trimmed off. Wide 16:9 pictures lose some of the top and
bottom, so by default the launcher keeps the part 38% of the way down. To choose what is kept, end the file name with a tag:
    castle__top.jpg       keep the top      (sky, towers, a logo across the top)
    harbour__bottom.png   keep the bottom   (people or ground at the bottom)
    plains__center.jpg    keep the middle

A one-time banner: put __once in the file name (party__once.png, or party__top__once.png) and the launcher shows that picture on ONE start
only: first thing on the Home page, until it is clicked or the launcher is closed. After that it is back to the usual pictures, and it never
joins the rotation. config.json remembers which ones have been shown ("banners_seen"); take a name out of that list to see it once more.

Limited-time banners: put __until- and a date in the file name (party__until-2026-12-02.jpg; year-month-day). Up to and including that day
those pictures take the place of the usual ones: while at least one is in date, only they are shown. The day after, the usual pictures are
back by themselves and the dated ones are simply skipped, so nothing has to be removed. The date is the one on the player's own PC.

Themes work the same way (launcher_theme.py). A theme is a .json in here with a "colours" table:
    vaporwave__until-2026-12-02.json   a limited-time theme: it turns itself on when it arrives and is gone the day after its date
    8bit.json                          (no date in the name) a theme that is always there to pick; never on unless a player picks it
    windurst.json                      an undated theme with "standard": true: what every PC wears when nothing is picked on the
                                       Theme page, ahead of any limited-time theme (only one theme should say it; Windurst from
                                       2026-11-25, Chronicle from 2026-11-24, Aero before that). The launcher's own look is then
                                       called "Classic" there and stays pickable. art-src\scripts\wind_buttons.py and
                                       wind_banners.py draw its pictures (windurst-ui, windurst_*__theme-windurst.jpg); its button
                                       labels come from chron_buttons.BUTTONS, so a new button needs no line of its own there.
    chronicle.json                     an undated theme to pick (the standard look 2026-11-24 to 25), and the source of the button
                                       list: art-src\scripts\chron_buttons.py and chron_banners.py draw its pictures.
    title__center__theme-8bit.png      a theme's own banner (__theme- and the theme's short name, here 8bit): shown only while that
                                       theme is worn, and then in place of the usual banners. art-src\scripts\bit_banners.py makes
                                       the 8-Bit theme's twelve (1056 x 424: on most screens the Play page shows them pixel for pixel)
    theme__until-2026-12-02.mp3        the limited-time theme's song: played once when the launcher opens (.mp3 or .wav); it stops
                                       when the game starts
    newer__from-2026-11-24__until-2026-12-02.mp3   a song that starts later: from that day on it takes over from the one above
                                       (of the songs in date, the one that started last plays)
    opener__plays-3__until-2026-12-02.mp3   a song for the first few times only: it opens the launcher three times on a PC,
                                       ahead of the theme's other song, and then never again there (config.json counts
                                       them in "theme_plays", under the name up to the first tag; only the play when the
                                       launcher opens counts, not "Play it now")
    default.mp3                        (or default.wav) the launcher's own opening theme: it plays with the Default look, and with
                                       any theme that has no song of its own
    music.json                         who made the songs: OPTIONS > Theme names the song that plays and its maker from it, and
                                       shows its "credit" sentence. A new song needs a line in it (file name and title), in
                                       CREDITS.md and in the patch notes
OPTIONS > Theme has a switch for Default (the launcher's own look) and one for every theme, so each player picks (it takes a
restart, which the launcher offers), plus the song on / off and its volume. With Default or another theme picked, the limited-time
banners and song rest too. A pick holds back only the limited-time theme that was in date when it was made: the next one shows by
itself again, and the pick is back once it has gone. The page is there whenever there is a theme to pick or a song to switch off. (The classic look,
"classic_ui": true, has no such page: there the same choices sit in a small strip on the banner.) config.json keeps them as "theme",
"theme_event", "theme_music" and "theme_volume".
A theme's .json holds "name" (what the page calls it), "colours" (the names at the top of launcher_widgets.py: BG, PANEL, GOLD ...;
names left out stay as usual) and, if wanted, "art", "sound" and "font". "art" may name a folder in here ("folder": "vaporwave-ui") whose
pictures stand in for the ones in assets\ui, name for name and size for size; a button the folder has no picture for stays as it
is (art-src\scripts\vice_buttons.py makes the vaporwave set, bit_buttons.py the 8-Bit one). "sound" names a .mp3 / .wav in here
as the theme's own opening song. "font" gives the launcher's text the theme's own lettering: {"family": "Galmuri11", "files":
["fonts/Galmuri11-Regular.ttf", "fonts/Galmuri11-Bold.ttf"]}, .ttf files in here that only the launcher uses (nothing is installed
on the PC). Pick a font whose letters are about as wide as the usual ones, so that no label is cut short.

This needs Pillow. If the launcher's status line says so, run once in PowerShell:
    python -m pip install pillow

Take the pictures out of this folder (or rename them to .txt) and the launcher goes back to its own banner. This file is ignored.
