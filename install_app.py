#!/usr/bin/env python3
"""
Install Desktop Pets as a real Windows app.

Creates:
  * a Start Menu shortcut  (searchable as "Desktop Pets")
  * an optional desktop shortcut
  * an uninstaller shortcut in the Start Menu

Run with:  py -3 install_app.py
"""

import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "Desktop Pets"
HERE = Path(__file__).resolve().parent
LAUNCHER = HERE / "launch_pets.pyw"
ICON = HERE / "pets.ico"


def pythonw():
    """Path to pythonw.exe (runs without a console window)."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def start_menu_dir():
    base = os.environ.get("APPDATA")
    if not base:
        raise RuntimeError("APPDATA is not set; cannot find the Start Menu folder.")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def desktop_dir():
    base = os.environ.get("USERPROFILE")
    if not base:
        return None
    return Path(base) / "Desktop"


def make_shortcut(link_path, target, arguments="", working_dir=None, icon=None):
    """Create a .lnk using the Windows Script Host, no extra packages needed.

    Values are passed through the environment so paths containing quotes or
    apostrophes (for example "Matthew's Codes") cannot break the script.
    """
    link_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$s = $ws.CreateShortcut($env:DP_LINK); "
        "$s.TargetPath = $env:DP_TARGET; "
        "$s.Arguments = $env:DP_ARGS; "
        "$s.WorkingDirectory = $env:DP_WORKDIR; "
        "$s.Description = $env:DP_DESC; "
        "if ($env:DP_ICON) { $s.IconLocation = $env:DP_ICON }; "
        "$s.Save()"
    )
    env = dict(os.environ)
    env.update({
        "DP_LINK": str(link_path),
        "DP_TARGET": str(target),
        "DP_ARGS": arguments,
        "DP_WORKDIR": str(working_dir or HERE),
        "DP_DESC": APP_NAME,
        "DP_ICON": str(icon) if icon else "",
    })
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def main():
    if sys.platform != "win32":
        print("Desktop Pets is a Windows app.", file=sys.stderr)
        return 1

    if not LAUNCHER.exists():
        print(f"Missing {LAUNCHER.name}; run this from the Desktop Pets folder.", file=sys.stderr)
        return 1

    target = str(pythonw())
    icon = str(ICON) if ICON.exists() else str(pythonw())

    menu = start_menu_dir()
    links = [
        (menu / f"{APP_NAME}.lnk", target, f'"{LAUNCHER}"', icon),
        (menu / f"Uninstall {APP_NAME}.lnk", str(pythonw()), f'"{HERE / "uninstall_app.py"}"', icon),
    ]

    answer = input("Also put a shortcut on your desktop? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        desk = desktop_dir()
        if desk:
            links.append((desk / f"{APP_NAME}.lnk", target, f'"{LAUNCHER}"', icon))

    for link, tgt, args, ico in links:
        try:
            make_shortcut(link, tgt, args, icon=ico)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"Could not create {link.name}: {exc}", file=sys.stderr)
            return 1
        print(f"Created {link}")

    print()
    print(f"{APP_NAME} is installed. Press the Windows key and type \"{APP_NAME}\" to launch it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
