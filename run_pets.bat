@echo off
rem Double-click to launch Desktop Pets (needs Python 3 for Windows)
title Desktop Pets
where pyw >nul 2>nul
if not errorlevel 1 (
    start "" pyw -3 "%~dp0launch_pets.pyw"
    exit /b
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    start "" pythonw "%~dp0launch_pets.pyw"
    exit /b
)
echo Desktop Pets needs Python 3.10 or newer for Windows.
echo Get it at https://www.python.org/downloads/
echo Include the Python launcher during installation, then try again.
pause

