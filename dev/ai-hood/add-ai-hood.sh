#!/usr/bin/env bash
# XI: Forever Offline - "Peek under the AI hood" (made for Sunie, 2026-11-22)
# Switches the AI hood on for THIS install only: it adds one small file (ai-hood.on) to the game's folder.
# Nothing is downloaded and no game file is changed. remove-ai-hood.sh takes it away again.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
is_game() { [ -f "$1/squad-chat/squad_chat.py" ]; }
game=""
for candidate in "${1:-}" "$here" "$here/.." "$here/../.." "$PWD" "$HOME/XI Forever Offline" "$HOME/Games/XI Forever Offline"; do
    if [ -n "$candidate" ] && is_game "$candidate"; then
        game="$(cd "$candidate" && pwd)"
        break
    fi
done
while [ -z "$game" ]; do
    echo "I could not find your XI: Forever Offline folder (the one with XI-Forever-Offline and squad-chat in it)."
    read -r -p "Drag that folder into this window (or type its path), then press Enter: " answer || exit 1
    answer="${answer#"${answer%%[![:space:]]*}"}"; answer="${answer%"${answer##*[![:space:]]}"}"
    answer="${answer%\"}"; answer="${answer#\"}"; answer="${answer%\'}"; answer="${answer#\'}"
    answer="${answer/#\~/$HOME}"
    [ -z "$answer" ] && continue
    if is_game "$answer"; then
        game="$(cd "$answer" && pwd)"
    else
        echo "That folder has no squad-chat/squad_chat.py in it."
    fi
done
if ! grep -q "ai-hood.on" "$game/squad-chat/squad_chat.py"; then
    echo
    echo "This install is older than v0.1.60, the first version with the AI hood in it."
    echo "Update first (launcher: SYSTEM > Settings > Check for updates), then run this again."
    exit 1
fi
if ! printf '%s\n' "Peek under the AI hood: switched on $(date)." "Delete this file to switch it off." > "$game/ai-hood.on"; then
    echo "Could not write to $game (no permission?)."
    exit 1
fi
echo
echo "The AI hood is on for: $game"
echo
echo "1. Close the launcher and open it again."
echo "2. SYSTEM > Settings has a new box, 'AI hood': press 'Open the AI hood'."
echo "3. Play with AI chat on and talk to a squad mate: every prompt and reply shows up in that window."
echo
echo "The same text is kept in logs/ai-hood.log (in a terminal: tail -f \"$game/logs/ai-hood.log\")."
