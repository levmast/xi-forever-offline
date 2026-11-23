@echo off
rem XI: Forever Offline - takes the AI hood away again (removes ai-hood.on; the log stays until you delete it).
setlocal EnableExtensions
set "GAME="
for %%D in ("%~1" "%~dp0." "%~dp0.." "%~dp0..\.." "%CD%") do if not defined GAME if exist "%%~fD\squad-chat\squad_chat.py" set "GAME=%%~fD"
if not defined GAME (
    echo I could not find your XI: Forever Offline folder. Just delete the file ai-hood.on in that folder.
    pause
    exit /b 1
)
if exist "%GAME%\ai-hood.on" (
    del "%GAME%\ai-hood.on"
    echo The AI hood is off for: %GAME% ^(restart the launcher^).
) else (
    echo The AI hood was not on for: %GAME%
)
pause
