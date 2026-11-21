#!/usr/bin/env bash
# Builds "XI-Forever-Offline" in this folder: the Linux launcher with Python inside, so players need no Python.
# The Linux twin of build_release.ps1 (same contents: the kit's scripts stay .py files next to it and run through it,
# "XI-Forever-Offline --run script.py"). Used by the GitHub workflow .github/workflows/linux-release.yml; it also works
# on any Linux PC with Python 3.10+, Tk and the MariaDB client library (Ubuntu/Debian: python3-tk libmariadb-dev).
#   ./build_release.sh            build
#   PYTHON=python3.12 ./build_release.sh
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"

# A private Python for the build (build/venv), so the system's Python is never touched.
if [ ! -x build/venv/bin/python ]; then
  "$PYTHON" -m venv build/venv
fi
py=build/venv/bin/python
"$py" -m pip install --disable-pip-version-check pyinstaller "mariadb<2" bcrypt pillow certifi

# The kit's scripts run inside the launcher but are not part of it, so PyInstaller cannot see what they import:
# bundle the whole standard library (minus its tests and tools), the database driver and the launcher's modules.
skip="idlelib test lib2to3 ensurepip turtledemo turtle pydoc_data venv distutils msilib winreg winsound msvcrt nt _winapi nis spwd ossaudiodev"
mapfile -t std < <("$py" -c "import sys; skip=set('$skip'.split()); print('\n'.join(sorted(n for n in sys.stdlib_module_names if not n.startswith('_') and n not in skip)))")
hidden=("${std[@]}" bcrypt certifi mariadb PIL.Image PIL.ImageTk PIL._tkinter_finder
        launcher_core launcher_squad launcher_rules launcher_icons launcher_personality
        launcher_thirdparty launcher_setup launcher_game launcher_client launcher_update launcher_linux
        launcher_passport launcher_coop launcher_coop_gui launcher_contrib
        launcher_pages launcher_widgets launcher_settings)
opts=(--noconfirm --onefile --name XI-Forever-Offline
      --distpath "$PWD" --workpath "$PWD/build/pyinstaller" --specpath "$PWD/build/pyinstaller"
      --collect-all mariadb --collect-data certifi)
for m in "${hidden[@]}"; do opts+=(--hidden-import "$m"); done

"$py" -m PyInstaller "${opts[@]}" launcher_gui.pyw

echo
echo "Built: $PWD/XI-Forever-Offline"
echo "Quick check (runs the personality tests through it):"
chmod +x XI-Forever-Offline
./XI-Forever-Offline --run "$PWD/dev/personality-tests/test_personality.py"
