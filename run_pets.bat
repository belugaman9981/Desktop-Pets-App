@echo off
rem Double-click to launch Desktop Pets (needs Python 3 for Windows)
title Desktop Pets
start "" pythonw "%~dp0launch_pets.pyw"
if errorlevel 1 (
    echo.
    echo Desktop Pets needs Python 3 for Windows.
    echo Get it free at https://www.python.org/downloads/
    echo During install, tick "Add python.exe to PATH", then try again.
    pause
)
