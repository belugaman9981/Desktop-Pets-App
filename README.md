DESKTOP PETS - tiny flying pets for your Windows desktop
========================================================

WHAT IT IS
A little Windows program that fills your screen with tiny colorful
pets. They flap their wings, wander around, and bounce off the edges
of your screen. Each pet floats in its own little window above your
other windows.

WHAT YOU NEED
- Windows 10 or 11
- Python 3 (free) from https://www.python.org/downloads/
  During install, tick "Add python.exe to PATH".

HOW TO RUN
1. Unzip this folder anywhere you like.
2. Double-click run_pets.bat
   (or right-click desktop_pets.py -> Open with -> Python)

INSTALL IT AS A REAL APP (RECOMMENDED)
1. Double-click install_app.py (or run: py -3 install_app.py)
2. Answer the question about a desktop shortcut.
3. Press the Windows key and type "Desktop Pets" - it is now in your
   Start Menu with its own bird icon, and it launches with no black
   console window.

To remove the shortcuts later, use "Uninstall Desktop Pets" in the
Start Menu (or run uninstall_app.py). Your settings are kept.

WHAT IT DOES
- 3 little pets start flying around your screen right away.
- The "Desktop Pets" control panel lets you add more (up to 12)
  or remove pets.
- Click a pet to boop it - it zooms off in a new direction, happily.
- Close the control panel (or press "Close all") to say goodbye.

The pets stay on top of your other windows, but only the pet itself
takes up space - the rest of your screen works normally.

FILES
- desktop_pets.py  the app itself
- launch_pets.pyw  silent launcher used by the shortcuts
- install_app.py   adds Start Menu / desktop shortcuts
- uninstall_app.py removes those shortcuts
- make_icon.py     regenerates pets.ico (the app icon)
- run_pets.bat     quick launch without installing

Have fun!
- Fawkes
