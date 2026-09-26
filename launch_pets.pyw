#!/usr/bin/env python3
"""
Silent launcher for Desktop Pets.

Double-clicking a .pyw file runs it with pythonw.exe, so no console window
appears. This is what the Start Menu and desktop shortcuts point at.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import desktop_pets  # noqa: E402

if __name__ == "__main__":
    os.chdir(HERE)
    sys.exit(desktop_pets.main())
