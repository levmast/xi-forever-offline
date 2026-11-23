#!/usr/bin/env bash
# XI: Forever Offline - takes the AI hood away again (removes ai-hood.on; the log stays until you delete it).
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for candidate in "${1:-}" "$here" "$here/.." "$here/../.." "$PWD" "$HOME/XI Forever Offline" "$HOME/Games/XI Forever Offline"; do
    if [ -n "$candidate" ] && [ -f "$candidate/squad-chat/squad_chat.py" ]; then
        game="$(cd "$candidate" && pwd)"
        if [ -f "$game/ai-hood.on" ]; then
            rm -f "$game/ai-hood.on" && echo "The AI hood is off for: $game (restart the launcher)."
        else
            echo "The AI hood was not on for: $game"
        fi
        exit 0
    fi
done
echo "I could not find your XI: Forever Offline folder. Run this as: bash remove-ai-hood.sh \"/path/to/XI Forever Offline\""
echo "(or just delete the file ai-hood.on in that folder)."
exit 1
