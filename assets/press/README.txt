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

This needs Pillow. If the launcher's status line says so, run once in PowerShell:
    python -m pip install pillow

Take the pictures out of this folder (or rename them to .txt) and the launcher goes back to its own banner. This file is ignored.
