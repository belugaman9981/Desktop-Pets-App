#!/usr/bin/env python3
"""
Desktop Pets - tiny flying pets that live on your Windows desktop.

Windows only. Requires Python 3 (https://www.python.org/downloads/).
Run with:  py -3 desktop_pets.py   (or double-click run_pets.bat)

Each pet gets its own little borderless window that floats above your other
windows. Click a pet to boop it and watch it dart off happily.
"""

import math
import random
import sys
import ctypes
import json
import logging
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

# This color becomes see-through on Windows. Nothing drawn may use it.
TRANSPARENT = "#ff00ff"

PET_SIZE = 130          # pixel size of each pet's window
TICK_MS = 40            # movement timer interval
FLAP_EVERY = 4          # ticks between wing flaps
MAX_PETS = 12
START_PETS = 3


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Desktop Pets" / "settings.json"


def load_settings(path):
    defaults = {"count": START_PETS, "speed": 1.0, "topmost": True}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return defaults
        if type(data.get("count")) is int:
            defaults["count"] = max(0, min(MAX_PETS, data["count"]))
        if type(data.get("speed")) in (int, float) and math.isfinite(data["speed"]):
            defaults["speed"] = max(0.25, min(2.0, data["speed"]))
        if type(data.get("topmost")) is bool:
            defaults["topmost"] = data["topmost"]
    except (OSError, ValueError):
        pass
    return defaults


def work_area(root):
    """Primary monitor's usable area, excluding the Windows taskbar."""
    from ctypes import wintypes
    rect = wintypes.RECT()
    if sys.platform == "win32" and ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
        return rect.left, rect.top, rect.right, rect.bottom
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()

# (body color, belly color) pairs
PALETTES = [
    ("#e23b3b", "#f6b8b8"),  # cardinal red
    ("#3b82e2", "#b8d4f6"),  # bluebird
    ("#e2a93b", "#f6e3b8"),  # goldfinch
    ("#8b5cf6", "#d9c9fb"),  # violet
    ("#22b573", "#b8eccf"),  # leaf green
    ("#e267b0", "#f6c9e2"),  # blossom pink
    ("#ff7f2a", "#ffd9b8"),  # tangerine
]


class Pet:
    """One flying pet living in its own borderless window."""

    def __init__(self, master, bounds, topmost=True):
        self.bounds = bounds
        self.body, self.belly = random.choice(PALETTES)

        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.title("Desktop Pets - bird")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", topmost)
        self.win.attributes("-transparentcolor", TRANSPARENT)

        self.canvas = tk.Canvas(
            self.win,
            width=PET_SIZE,
            height=PET_SIZE,
            bg=TRANSPARENT,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.drag_origin = None
        self.dragged = False

        # flight state
        left, top, right, bottom = bounds
        self.x = random.uniform(left, max(left, right - PET_SIZE))
        self.y = random.uniform(top, max(top, bottom - PET_SIZE))
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = random.uniform(2.0, 3.5)
        self.tick = random.randrange(0, 1000)
        self.wing_up = True
        self.boost = 0  # boop speed-burst timer, in ticks

        self._place()
        self.draw()
        self.win.deiconify()

    def _press(self, event):
        self.drag_origin = (event.x_root, event.y_root, self.x, self.y)
        self.dragged = False

    def _drag(self, event):
        if self.drag_origin is None:
            return
        px, py, x, y = self.drag_origin
        dx, dy = event.x_root - px, event.y_root - py
        if abs(dx) + abs(dy) > 4:
            self.dragged = True
        if self.dragged:
            self.x, self.y = x + dx, y + dy
            self._clamp()
            self._place()

    def _release(self, event):
        if self.drag_origin is not None and not self.dragged:
            self.boop()
        self.drag_origin = None

    def _clamp(self):
        left, top, right, bottom = self.bounds
        self.x = max(left, min(self.x, max(left, right - PET_SIZE)))
        self.y = max(top, min(self.y, max(top, bottom - PET_SIZE)))

    # -- drawing ------------------------------------------------------
    def draw(self):
        c = self.canvas
        c.delete("all")
        cx, cy = PET_SIZE // 2, PET_SIZE // 2

        # tail feathers
        c.create_polygon(
            cx - 28, cy - 4,
            cx - 48, cy - 14,
            cx - 44, cy + 2,
            cx - 48, cy + 12,
            cx - 28, cy + 8,
            fill=self.body, outline="",
        )
        # body
        c.create_oval(cx - 28, cy - 20, cx + 28, cy + 22,
                      fill=self.body, outline="")
        # belly
        c.create_oval(cx - 16, cy - 4, cx + 20, cy + 20,
                      fill=self.belly, outline="")
        # wing: two flap states
        if self.wing_up:
            c.create_polygon(cx - 8, cy - 2, cx - 34, cy - 30, cx - 20, cy + 2,
                             fill=self.belly, outline="")
        else:
            c.create_polygon(cx - 8, cy + 2, cx - 30, cy + 30, cx - 18, cy + 6,
                             fill=self.belly, outline="")
        # eye
        c.create_oval(cx + 12, cy - 14, cx + 24, cy - 2,
                      fill="white", outline="")
        c.create_oval(cx + 16, cy - 10, cx + 22, cy - 4,
                      fill="black", outline="")
        # beak
        c.create_polygon(cx + 26, cy - 8, cx + 36, cy - 4, cx + 26, cy,
                         fill="#ff9f1a", outline="")
        # rosy cheek
        c.create_oval(cx + 8, cy - 2, cx + 14, cy + 4,
                      fill="#ff8fa3", outline="")
        if math.cos(self.angle) < 0:
            for item in c.find_all():
                coords = c.coords(item)
                for i in range(0, len(coords), 2):
                    coords[i] = PET_SIZE - coords[i]
                c.coords(item, *coords)

    # -- movement -----------------------------------------------------
    def _place(self):
        self.win.geometry(f"{PET_SIZE}x{PET_SIZE}+{int(self.x)}+{int(self.y)}")

    def update(self, multiplier=1.0):
        if self.drag_origin is not None:
            return
        self.tick += 1
        if self.tick % FLAP_EVERY == 0:
            self.wing_up = not self.wing_up

        # wander a little
        self.angle += random.uniform(-0.25, 0.25)

        speed = self.speed * multiplier * (2.6 if self.boost > 0 else 1.0)
        if self.boost > 0:
            self.boost -= 1

        self.x += math.cos(self.angle) * speed
        self.y += math.sin(self.angle) * speed + math.sin(self.tick * 0.08) * 0.8

        # bounce off the screen edges
        left, top, right, bottom = self.bounds
        max_x, max_y = max(left, right - PET_SIZE), max(top, bottom - PET_SIZE)
        if self.x < left:
            self.x = left
            self.angle = math.pi - self.angle
        elif self.x > max_x:
            self.x = max_x
            self.angle = math.pi - self.angle
        if self.y < top:
            self.y = top
            self.angle = -self.angle
        elif self.y > max_y:
            self.y = max_y
            self.angle = -self.angle

        self._place()
        self.draw()

    def boop(self):
        """A click gives the pet a happy burst of speed in a new direction."""
        self.boost = 25
        self.angle = random.uniform(0, 2 * math.pi)

    def destroy(self):
        self.win.destroy()


class App:
    def __init__(self, config_path=None):
        self.config_path = config_path or settings_path()
        self.settings = load_settings(self.config_path)
        self.root = tk.Tk()
        self.root.report_callback_exception = self._callback_error
        self.bounds = work_area(self.root)
        self.pets = []
        self.paused = False
        self.hidden = False
        self.closed = False
        self.timer = None
        self.frame = 0
        self.speed = tk.DoubleVar(value=self.settings["speed"])
        self.topmost = tk.BooleanVar(value=self.settings["topmost"])

        # The main window stays in the taskbar, including when minimized.
        self.panel = self.root
        self.panel.title("Desktop Pets")
        self.panel.resizable(False, False)
        self.panel.protocol("WM_DELETE_WINDOW", self.quit_all)
        style = ttk.Style(self.root)
        style.theme_use("vista" if "vista" in style.theme_names() else "clam")
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        content = ttk.Frame(self.panel, padding=22)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="A little company for your desktop",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.count_label = ttk.Label(content)
        self.count_label.pack(anchor="w", pady=(8, 18))
        buttons = ttk.Frame(content)
        buttons.pack(fill="x")
        self.add_button = ttk.Button(buttons, text="Add pet", command=self.add_pet)
        self.add_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.remove_button = ttk.Button(buttons, text="Remove pet", command=self.remove_pet)
        self.remove_button.pack(side="left", expand=True, fill="x", padx=(6, 0))
        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(10, 18))
        self.pause_button = ttk.Button(actions, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.hide_button = ttk.Button(actions, text="Hide pets", command=self.toggle_hidden)
        self.hide_button.pack(side="left", expand=True, fill="x", padx=(6, 0))
        self.speed_label = ttk.Label(content)
        self.speed_label.pack(anchor="w")
        ttk.Scale(content, from_=0.25, to=2.0, variable=self.speed,
                  command=self._speed_changed).pack(fill="x", pady=(6, 10))
        ttk.Checkbutton(content, text="Keep pets above other windows", variable=self.topmost,
                        command=self._topmost_changed).pack(anchor="w")
        ttk.Separator(content).pack(fill="x", pady=18)
        ttk.Label(content, text="Click a bird to boop it. Drag to move it.\n"
                  "Minimize this panel to keep your pets flying.\n"
                  "Closing the panel quits the app.", foreground="#555555").pack(anchor="w")
        self.save_status = ttk.Label(content, foreground="#9c321a", wraplength=390)
        self.save_status.pack(anchor="w", pady=(6, 0))
        ttk.Button(content, text="Quit Desktop Pets", command=self.quit_all).pack(anchor="e", pady=(8, 0))
        self._speed_changed()
        for _ in range(self.settings["count"]):
            self.add_pet()
        self._refresh_label()
        self._loop()

    def add_pet(self):
        if len(self.pets) >= MAX_PETS:
            return
        pet = Pet(self.root, self.bounds, self.topmost.get())
        if self.hidden:
            pet.win.withdraw()
        self.pets.append(pet)
        self._refresh_label()

    def remove_pet(self):
        if self.pets:
            self.pets.pop().destroy()
            self._refresh_label()

    def _refresh_label(self):
        n = len(self.pets)
        self.count_label.config(
            text=f"{n} pet{'s' if n != 1 else ''} on your desktop" +
                 (" · hidden" if self.hidden else " · paused" if self.paused else ""))
        self.add_button.config(state="disabled" if n >= MAX_PETS else "normal")
        self.remove_button.config(state="disabled" if not n else "normal")

    def toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.config(text="Resume" if self.paused else "Pause")
        self._refresh_label()

    def toggle_hidden(self):
        self.hidden = not self.hidden
        for pet in self.pets:
            pet.win.withdraw() if self.hidden else pet.win.deiconify()
        self.hide_button.config(text="Show pets" if self.hidden else "Hide pets")
        self._refresh_label()

    def _speed_changed(self, _value=None):
        self.speed_label.config(text=f"Flight speed: {self.speed.get():.2f}×")

    def _topmost_changed(self):
        for pet in self.pets:
            pet.win.attributes("-topmost", self.topmost.get())

    def save_settings(self):
        data = {"count": len(self.pets), "speed": self.speed.get(), "topmost": self.topmost.get()}
        temporary = self.config_path.with_suffix(f".{os.getpid()}.tmp")
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temporary.replace(self.config_path)
        except OSError:
            logging.exception("Could not save settings")
            self.save_status.config(text="Settings could not be saved. Changes apply for this session.")
        else:
            self.save_status.config(text="")

    def _callback_error(self, exc_type, exc, tb):
        logging.error("App error", exc_info=(exc_type, exc, tb))
        messagebox.showerror("Desktop Pets", f"Something went wrong: {exc}\n\nPlease restart Desktop Pets.", parent=self.root)

    def _loop(self):
        if self.closed:
            return
        self.frame += 1
        if self.frame % 50 == 0:
            self.bounds = work_area(self.root)
            for pet in self.pets:
                pet.bounds = self.bounds
                pet._clamp()
                pet._place()
        if not self.paused and not self.hidden:
            for pet in self.pets:
                pet.update(self.speed.get())
        if self.frame % 125 == 0:
            self.save_settings()
        self.timer = self.root.after(TICK_MS, self._loop)

    def quit_all(self):
        if self.closed:
            return
        self.save_settings()
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        for pet in self.pets:
            pet.destroy()
        self.pets = []
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    if sys.platform != "win32":
        print("Desktop Pets requires Windows 10 or 11.", file=sys.stderr)
        return 1
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    try:
        folder = settings_path().parent
        folder.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=folder / "app.log", level=logging.WARNING,
                            format="%(asctime)s %(levelname)s %(message)s")
    except OSError:
        logging.basicConfig(handlers=[logging.NullHandler()])
    try:
        App().run()
    except Exception:
        logging.exception("Startup failed")
        ctypes.windll.user32.MessageBoxW(None,
            "Desktop Pets could not start.\nSee %LOCALAPPDATA%\\Desktop Pets\\app.log for details.",
            "Desktop Pets", 16)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
