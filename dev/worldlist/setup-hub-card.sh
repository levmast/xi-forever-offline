#!/bin/bash
# The Hub's card in everyone's OPEN WORLDS: its banner and its description (run as root on the hub server). The Hub
# serves them itself from v0.3.5 on (the banner at once, the description after its next restart).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
KIT=/opt/xifo-world
install -o xifo -g xifo -m 644 -D "$HERE/hub-banner.png" "$KIT/coop/banner.png"
runuser -u xifo -- python3 - "$KIT/coop.json" <<'PY'
import json, sys
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
data["about"] = "The official world of XI: Forever Offline, always online. Era rates, bot players, the Forever linkshell."
data["listed"] = True
json.dump(data, open(path + ".part", "w", encoding="utf-8"), indent=2)
import os; os.replace(path + ".part", path)
print("The Hub's card: banner and description set.")
PY
