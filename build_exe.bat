@echo off
title Build Spicy John .exe
echo ===== Spicy John - build .exe =====
where py >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add python to PATH"^) then run this file again.
  pause & exit /b 1
)
py -m pip install --upgrade pip
py -m pip install pygame pyinstaller
py -m PyInstaller --noconfirm --clean --windowed --name SpicyJohn --icon icon.ico ^
  --add-data "assets;assets" --hidden-import mobile_controls --hidden-import netplay --hidden-import online_scenes full_game.py
if errorlevel 1 ( echo BUILD FAILED & pause & exit /b 1 )
copy /Y settings.json dist\SpicyJohn\settings.json >nul 2>nul
echo.
echo DONE!  Your game is in:  dist\SpicyJohn\SpicyJohn.exe
echo Copy the whole "SpicyJohn" folder wherever you want, or make a desktop shortcut to SpicyJohn.exe
pause
