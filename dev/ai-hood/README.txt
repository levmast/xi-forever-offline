XI: Forever Offline - Peek under the AI hood
============================================
Made for Sunie. It switches on a window in YOUR launcher that shows, live, every prompt the AI helpers
send to the model (squad chat, bot players, town crowd lines) and each reply. Nobody else's game has it.

It needs v0.1.60 or newer (launcher: SYSTEM > Settings > Check for updates).

Switch it on
------------
1. Unzip this anywhere. Easiest: into your XI: Forever Offline folder, so it finds the game by itself.
2. Linux:    bash add-ai-hood.sh              (or: bash add-ai-hood.sh "/path/to/XI Forever Offline")
   Windows:  double-click add-ai-hood.bat
3. Close the launcher and open it again. SYSTEM > Settings has a new box, "AI hood".
4. Press "Open the AI hood", start the game with AI chat on and talk to a squad mate in party chat.

What it does: it adds one small file, ai-hood.on, to the game's folder. Nothing is downloaded and no game
file is changed. While that file is there, the helpers also write what they send to logs/ai-hood.log
(Linux terminal: tail -f logs/ai-hood.log). The log is yours and stays on your machine.

Switch it off
-------------
Run remove-ai-hood.sh / remove-ai-hood.bat, or just delete ai-hood.on. Restart the launcher.

Files to tinker with (all in the game's folder; keep a copy before you change one)
----------------------------------------------------------------------------------
squad-chat/config.json            the model, how often they talk, crosstalk, idle chatter
squad-chat/mates/<name>.json      each mate's sheet: backstory, way of talking, example lines
squad-chat/lore/ffxi_era.md       the world knowledge every mate shares
squad-chat/README.md              how the squad chat helper works
crowds/crowd_chat_ai.py           the prompts for the town crowd's lines
crowds/bots/bots_chat_ai.py       the prompts for the bot players

An update can replace these files with the new version's, so keep your own edits somewhere safe.
Changes to a .json or .md file count the next time the game starts; the hood shows you the result.
