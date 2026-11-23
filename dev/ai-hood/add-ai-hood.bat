@echo off
rem XI: Forever Offline - "Peek under the AI hood" (made for Sunie, 2026-11-22)
rem Switches the AI hood on for THIS install only: it adds one small file (ai-hood.on) to the game's folder.
rem Nothing is downloaded and no game file is changed. remove-ai-hood.bat takes it away again.
setlocal EnableExtensions
title XI: Forever Offline - AI hood
set "GAME="
for %%D in ("%~1" "%~dp0." "%~dp0.." "%~dp0..\.." "%CD%") do if not defined GAME if exist "%%~fD\squad-chat\squad_chat.py" set "GAME=%%~fD"
:ask
if defined GAME goto found
echo I could not find your XI: Forever Offline folder (the one with the launcher and squad-chat in it).
set /p "GAME=Drag that folder into this window, then press Enter: "
if not defined GAME goto ask
set "GAME=%GAME:"=%"
if exist "%GAME%\squad-chat\squad_chat.py" goto found
echo That folder has no squad-chat\squad_chat.py in it.
set "GAME="
goto ask
:found
findstr /c:"ai-hood.on" "%GAME%\squad-chat\squad_chat.py" >nul
if errorlevel 1 (
    echo.
    echo This install is older than v0.1.60, the first version with the AI hood in it.
    echo Update first ^(launcher: SYSTEM ^> Settings ^> Check for updates^), then run this again.
    pause
    exit /b 1
)
> "%GAME%\ai-hood.on" echo Peek under the AI hood: switched on %DATE% %TIME%. Delete this file to switch it off.
if not exist "%GAME%\ai-hood.on" (
    echo Could not write to "%GAME%". Right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
echo.
echo The AI hood is on for: %GAME%
echo.
echo 1. Close the launcher and open it again.
echo 2. SYSTEM ^> Settings has a new box, "AI hood": press "Open the AI hood".
echo 3. Play with AI chat on and talk to a squad mate: every prompt and reply shows up in that window.
echo.
echo The same text is kept in logs\ai-hood.log.
pause
