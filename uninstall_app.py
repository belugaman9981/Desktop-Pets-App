#!/usr/bin/env python3
"""
Remove the Desktop Pets shortcuts created by install_app.py.

Your settings in %LOCALAPPDATA%\\Desktop Pets are left alone.
"""

import os
import sys
from pathlib import Path

APP_NAME = "Desktop Pets"


def main():
    if sys.platform != "win32":
        print("Desktop Pets is a Windows app.", file=sys.stderr)
        return 1

    targets = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        targets += [menu / f"{APP_NAME}.lnk", menu / f"Uninstall {APP_NAME}.lnk"]
    profile = os.environ.get("USERPROFILE")
    if profile:
        targets.append(Path(profile) / "Desktop" / f"{APP_NAME}.lnk")

    removed = 0
    for link in targets:
        try:
            link.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            print(f"Could not remove {link}: {exc}", file=sys.stderr)
            continue
        print(f"Removed {link}")
        removed += 1

    print(f"Done. {removed} shortcut(s) removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
