# Builds "XI Forever Offline.exe" in this folder: the launcher with Python inside, so players need no Python.
# The kit's scripts (the AH and conquest simulators, squad chat, the bot chat helper, the tools) stay as .py files next
# to it and run through the exe ("XI Forever Offline.exe --run script.py"). Your own launcher_gui.pyw keeps working.
# Run in PowerShell:  cd C:\FFXISOLO ; Set-ExecutionPolicy -Scope Process Bypass ; .\build_release.ps1
# It builds in its own Python environment (build\venv), so it never changes the Python your launcher uses.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# A private Python for the build (build\venv), so your own Python and the running launcher are never touched.
$venv = Join-Path $PSScriptRoot "build\venv"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
  python -m venv $venv
  if ($LASTEXITCODE -ne 0) { throw "Could not make the build environment (python -m venv)" }
}
$py = Join-Path $venv "Scripts\python.exe"
# Pinned to the versions the last release was built with (datadecay, 2026-11-18: a new upload of any of these can't
# change a build without us choosing to). Raise a pin on purpose, test, then release.
& $py -m pip install --disable-pip-version-check `
    "pyinstaller==6.22.3" "pyinstaller-hooks-contrib==2026.10" "altgraph==0.17.5" "pefile==2024.8.26" `
    "pywin32-ctypes==0.2.3" "packaging==26.3" "setuptools==84.2.1" `
    "mariadb==1.1.15" "bcrypt==5.0.0" "pillow==13.0.0" "certifi==2026.10.23"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# The kit's scripts run inside the exe but are not part of it, so PyInstaller cannot see what they import:
# bundle the whole standard library (minus its tests and tools), the database drivers and the launcher's modules.
$skip = "idlelib test lib2to3 ensurepip turtledemo turtle pydoc_data venv distutils msilib"
$std = & $py -c "import sys; skip=set('$skip'.split()); print('\n'.join(sorted(n for n in sys.stdlib_module_names if not n.startswith('_') and n not in skip)))"
$hidden = @($std -split "`r?`n" | Where-Object { $_ }) + @("bcrypt", "certifi", "mariadb", "PIL.Image", "PIL.ImageTk",
            "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageFilter", "PIL.ImageChops", "PIL.ImageStat",   # forever_beta_shirt.py
            "launcher_core", "launcher_squad", "launcher_rules", "launcher_icons", "launcher_personality",
            "launcher_thirdparty", "launcher_revamped", "launcher_setup", "launcher_game", "launcher_gamefiles", "launcher_client",
            "launcher_passport", "launcher_coop", "launcher_coop_gui", "launcher_contrib",
            "launcher_pages", "launcher_widgets", "launcher_settings", "launcher_gamepad", "launcher_theme", "launcher_hood",
            "launcher_hd", "launcher_hd_gui", "launcher_stinkshell", "launcher_hardcore", "launcher_hardcore_gui", "launcher_linux", "launcher_armory", "launcher_armory_gui", "launcher_ventures" <# (2026-11-25) Ventures #>, "launcher_vanasync" <# (2026-11-25) VanaSync #>, "launcher_charcards", "launcher_charcards_gui" <# (2026-11-25) character cards #>, "launcher_squad_backup")
$opts = @("--noconfirm", "--onefile", "--windowed", "--name", "XI Forever Offline",
          "--icon", (Join-Path $PSScriptRoot "assets\ui\icon.ico"),
          "--distpath", $PSScriptRoot, "--workpath", (Join-Path $PSScriptRoot "build\pyinstaller"),
          "--specpath", (Join-Path $PSScriptRoot "build\pyinstaller"), "--collect-all", "mariadb", "--collect-data", "certifi")
foreach ($m in $hidden) { $opts += @("--hidden-import", $m) }

& $py -m PyInstaller @opts (Join-Path $PSScriptRoot "launcher_gui.pyw")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$exe = Join-Path $PSScriptRoot "XI Forever Offline.exe"
Write-Host "`nBuilt: $exe" -ForegroundColor Green
Write-Host "Quick check (runs the personality tests through the exe):" -ForegroundColor DarkGray
& $exe --run (Join-Path $PSScriptRoot "dev\personality-tests\test_personality.py") | Out-Host
