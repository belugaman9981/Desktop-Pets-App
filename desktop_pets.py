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
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

try:
    import pet_ai
except ImportError:  # pet_ai.py missing - the AI button just hides itself
    pet_ai = None

# This color becomes see-through on Windows. Nothing drawn may use it.
TRANSPARENT = "#ff00ff"

PET_SIZE = 130          # pixel size of each pet's window
TICK_MS = 40            # movement timer interval
FLAP_EVERY = 4          # ticks between wing flaps
MAX_PETS = 12
START_PETS = 3
TRAIL_LENGTH = 6        # fading ghosts behind a pet with a trail


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Desktop Pets" / "settings.json"


def load_settings(path):
    defaults = {"count": START_PETS, "speed": 1.0, "topmost": True, "pets": []}
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
        if isinstance(data.get("pets"), list):
            defaults["pets"] = [p for p in data["pets"] if isinstance(p, dict)][:MAX_PETS]
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

    def __init__(self, master, bounds, topmost=True, design=None):
        self.bounds = bounds
        design = design or {}
        self.design = design
        self.name = str(design.get("name") or "bird")[:20]

        if design:
            self.shape = design.get("shape", "bird")
            self.body = design.get("body", PALETTES[0][0])
            self.belly = design.get("belly", PALETTES[0][1])
            self.beak = design.get("beak", "#ff9f1a")
            self.cheek = design.get("cheek", "#ff8fa3")
            self.eye = design.get("eye", "#141414")
            self.scale = float(design.get("size", 1.0))
            self.base_speed = float(design.get("speed", 1.0))
            self.flap_every = max(2, int(design.get("flap", FLAP_EVERY)))
            self.bob = float(design.get("bob", 0.8))
            self.wander = float(design.get("wander", 0.25))
            self.trail = bool(design.get("trail"))
            self.sparkle = bool(design.get("sparkle"))
            self.sound = design.get("sound", "chirp")
            self.personality = design.get("personality", "")
        else:
            self.shape = "bird"
            self.body, self.belly = random.choice(PALETTES)
            self.beak, self.cheek, self.eye = "#ff9f1a", "#ff8fa3", "#141414"
            self.scale, self.base_speed = 1.0, 1.0
            self.flap_every, self.bob, self.wander = FLAP_EVERY, 0.8, 0.25
            self.trail = self.sparkle = False
            self.sound, self.personality = "chirp", ""

        self.size = max(60, int(PET_SIZE * self.scale))
        self.ghosts = []  # recent positions, for the trail effect

        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.title(f"Desktop Pets - {self.name}")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", topmost)
        self.win.attributes("-transparentcolor", TRANSPARENT)

        self.canvas = tk.Canvas(
            self.win,
            width=self.size,
            height=self.size,
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
        self.x = random.uniform(left, max(left, right - self.size))
        self.y = random.uniform(top, max(top, bottom - self.size))
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = random.uniform(2.0, 3.5) * self.base_speed
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
        self.x = max(left, min(self.x, max(left, right - self.size)))
        self.y = max(top, min(self.y, max(top, bottom - self.size)))

    # -- drawing ------------------------------------------------------
    def draw(self):
        c = self.canvas
        c.delete("all")
        s = self.size
        cx, cy = s // 2, s // 2
        k = s / PET_SIZE  # scale factor for the original artwork

        # fading trail behind the pet
        if self.trail and self.ghosts:
            for index, (gx, gy) in enumerate(self.ghosts):
                fade = (index + 1) / (len(self.ghosts) + 1)
                radius = 10 * k * (0.4 + fade)
                c.create_oval(gx - radius, gy - radius, gx + radius, gy + radius,
                              fill=self.belly, outline="", stipple="gray50")

        drawer = {
            "bird": self._draw_bird,
            "fish": self._draw_fish,
            "cat": self._draw_cat,
            "blob": self._draw_blob,
            "bug": self._draw_bug,
            "ghost": self._draw_ghost,
        }.get(self.shape, self._draw_bird)
        drawer(c, cx, cy, k)

        # sparkles twinkling around the pet
        if self.sparkle:
            for index in range(3):
                phase = self.tick * 0.15 + index * 2.1
                sx = cx + math.cos(phase) * 40 * k
                sy = cy + math.sin(phase * 1.3) * 34 * k
                r = 2.5 * k * (0.6 + 0.4 * math.sin(phase * 2))
                c.create_oval(sx - r, sy - r, sx + r, sy + r,
                              fill="#fff6c2", outline="")

        if math.cos(self.angle) < 0:
            for item in c.find_all():
                coords = c.coords(item)
                for i in range(0, len(coords), 2):
                    coords[i] = s - coords[i]
                c.coords(item, *coords)

    def _eye(self, c, x, y, r, k):
        """A round eye with a highlight, centred on (x, y)."""
        c.create_oval(x - r, y - r, x + r, y + r, fill="white", outline="")
        pr = r * 0.55
        c.create_oval(x - pr + r * 0.25, y - pr + r * 0.15,
                      x + pr + r * 0.25, y + pr + r * 0.15,
                      fill=self.eye, outline="")

    def _draw_bird(self, c, cx, cy, k):
        # tail feathers, behind the body
        c.create_polygon(
            cx - 26 * k, cy - 6 * k,
            cx - 50 * k, cy - 16 * k,
            cx - 46 * k, cy,
            cx - 50 * k, cy + 14 * k,
            cx - 26 * k, cy + 8 * k,
            fill=self.body, outline="",
        )
        # body
        c.create_oval(cx - 28 * k, cy - 20 * k, cx + 28 * k, cy + 22 * k,
                      fill=self.body, outline="")
        # belly
        c.create_oval(cx - 14 * k, cy - 2 * k, cx + 22 * k, cy + 20 * k,
                      fill=self.belly, outline="")
        # wing, on the body (not over the tail), in one of two flap states
        if self.wing_up:
            c.create_polygon(cx - 4 * k, cy - 6 * k, cx - 22 * k, cy - 34 * k,
                             cx + 6 * k, cy - 12 * k,
                             fill=self.belly, outline="")
        else:
            c.create_polygon(cx - 4 * k, cy + 2 * k, cx - 20 * k, cy + 30 * k,
                             cx + 6 * k, cy + 8 * k,
                             fill=self.belly, outline="")
        # eye
        self._eye(c, cx + 17 * k, cy - 8 * k, 6 * k, k)
        # beak
        c.create_polygon(cx + 26 * k, cy - 8 * k, cx + 38 * k, cy - 3 * k,
                         cx + 26 * k, cy + 2 * k,
                         fill=self.beak, outline="")
        # rosy cheek
        c.create_oval(cx + 8 * k, cy - 2 * k, cx + 15 * k, cy + 5 * k,
                      fill=self.cheek, outline="")

    def _draw_fish(self, c, cx, cy, k):
        # tail fin, behind the body
        c.create_polygon(
            cx - 24 * k, cy,
            cx - 50 * k, cy - 20 * k,
            cx - 42 * k, cy,
            cx - 50 * k, cy + 20 * k,
            fill=self.body, outline="",
        )
        # top fin
        c.create_polygon(cx - 12 * k, cy - 18 * k, cx + 2 * k, cy - 34 * k,
                         cx + 12 * k, cy - 16 * k,
                         fill=self.belly, outline="")
        # body
        c.create_oval(cx - 26 * k, cy - 18 * k, cx + 28 * k, cy + 18 * k,
                      fill=self.body, outline="")
        # belly
        c.create_oval(cx - 14 * k, cy + 2 * k, cx + 20 * k, cy + 16 * k,
                      fill=self.belly, outline="")
        # side fin, in one of two flap states
        if self.wing_up:
            c.create_polygon(cx - 6 * k, cy + 2 * k, cx - 18 * k, cy + 22 * k,
                             cx + 4 * k, cy + 8 * k,
                             fill=self.belly, outline="")
        else:
            c.create_polygon(cx - 6 * k, cy + 2 * k, cx - 20 * k, cy + 14 * k,
                             cx + 4 * k, cy + 8 * k,
                             fill=self.belly, outline="")
        # eye
        self._eye(c, cx + 16 * k, cy - 6 * k, 6 * k, k)
        # mouth
        c.create_oval(cx + 24 * k, cy + 2 * k, cx + 32 * k, cy + 8 * k,
                      fill=self.beak, outline="")

    def _draw_cat(self, c, cx, cy, k):
        # tail, curling behind
        c.create_line(cx - 24 * k, cy + 14 * k, cx - 44 * k, cy + 6 * k,
                      cx - 46 * k, cy - 14 * k,
                      fill=self.body, width=max(2, int(7 * k)), capstyle="round")
        # ears
        c.create_polygon(cx - 24 * k, cy - 16 * k, cx - 20 * k, cy - 40 * k,
                         cx - 4 * k, cy - 24 * k,
                         fill=self.body, outline="")
        c.create_polygon(cx + 24 * k, cy - 16 * k, cx + 20 * k, cy - 40 * k,
                         cx + 4 * k, cy - 24 * k,
                         fill=self.body, outline="")
        # head
        c.create_oval(cx - 28 * k, cy - 26 * k, cx + 28 * k, cy + 22 * k,
                      fill=self.body, outline="")
        # muzzle
        c.create_oval(cx - 14 * k, cy + 2 * k, cx + 14 * k, cy + 20 * k,
                      fill=self.belly, outline="")
        # eyes
        self._eye(c, cx - 12 * k, cy - 8 * k, 6 * k, k)
        self._eye(c, cx + 12 * k, cy - 8 * k, 6 * k, k)
        # nose
        c.create_polygon(cx - 4 * k, cy + 6 * k, cx + 4 * k, cy + 6 * k,
                         cx, cy + 11 * k,
                         fill=self.beak, outline="")
        # whiskers
        for side in (-1, 1):
            for dy in (-3, 3):
                c.create_line(cx + side * 12 * k, cy + 10 * k + dy * k,
                              cx + side * 34 * k, cy + 6 * k + dy * 2 * k,
                              fill=self.cheek, width=max(1, int(1.5 * k)))
        # cheeks
        c.create_oval(cx - 24 * k, cy + 2 * k, cx - 16 * k, cy + 10 * k,
                      fill=self.cheek, outline="")
        c.create_oval(cx + 16 * k, cy + 2 * k, cx + 24 * k, cy + 10 * k,
                      fill=self.cheek, outline="")

    def _draw_blob(self, c, cx, cy, k):
        # soft rounded blob
        c.create_oval(cx - 30 * k, cy - 26 * k, cx + 30 * k, cy + 26 * k,
                      fill=self.body, outline="")
        # lighter tummy
        c.create_oval(cx - 18 * k, cy - 2 * k, cx + 18 * k, cy + 22 * k,
                      fill=self.belly, outline="")
        # big eyes
        self._eye(c, cx - 11 * k, cy - 8 * k, 8 * k, k)
        self._eye(c, cx + 11 * k, cy - 8 * k, 8 * k, k)
        # little smile
        c.create_arc(cx - 8 * k, cy + 2 * k, cx + 8 * k, cy + 14 * k,
                     start=200, extent=140, style="arc",
                     outline=self.beak, width=max(1, int(2 * k)))
        # cheeks
        c.create_oval(cx - 26 * k, cy + 2 * k, cx - 18 * k, cy + 10 * k,
                      fill=self.cheek, outline="")
        c.create_oval(cx + 18 * k, cy + 2 * k, cx + 26 * k, cy + 10 * k,
                      fill=self.cheek, outline="")

    def _draw_bug(self, c, cx, cy, k):
        # legs, behind the body
        for side in (-1, 1):
            for dy in (-10, 0, 10):
                c.create_line(cx + side * 14 * k, cy + dy * k,
                              cx + side * 34 * k, cy + (dy - 8) * k,
                              fill=self.beak, width=max(1, int(2 * k)))
        # antennae
        for side in (-1, 1):
            c.create_line(cx + side * 8 * k, cy - 18 * k,
                          cx + side * 20 * k, cy - 38 * k,
                          fill=self.beak, width=max(1, int(2 * k)))
            c.create_oval(cx + side * 20 * k - 3 * k, cy - 41 * k,
                          cx + side * 20 * k + 3 * k, cy - 35 * k,
                          fill=self.beak, outline="")
        # body
        c.create_oval(cx - 22 * k, cy - 20 * k, cx + 22 * k, cy + 22 * k,
                      fill=self.body, outline="")
        # wing cases, in one of two flap states
        if self.wing_up:
            c.create_oval(cx - 18 * k, cy - 16 * k, cx + 18 * k, cy + 2 * k,
                          fill=self.belly, outline="")
        else:
            c.create_oval(cx - 18 * k, cy - 6 * k, cx + 18 * k, cy + 16 * k,
                          fill=self.belly, outline="")
        # eyes
        self._eye(c, cx - 9 * k, cy - 6 * k, 5 * k, k)
        self._eye(c, cx + 9 * k, cy - 6 * k, 5 * k, k)

    def _draw_ghost(self, c, cx, cy, k):
        # wavy-bottomed sheet
        c.create_polygon(
            cx - 28 * k, cy + 6 * k,
            cx - 28 * k, cy - 12 * k,
            cx - 20 * k, cy - 26 * k,
            cx, cy - 32 * k,
            cx + 20 * k, cy - 26 * k,
            cx + 28 * k, cy - 12 * k,
            cx + 28 * k, cy + 6 * k,
            cx + 18 * k, cy + 20 * k,
            cx + 8 * k, cy + 6 * k,
            cx - 4 * k, cy + 20 * k,
            cx - 14 * k, cy + 6 * k,
            fill=self.body, outline="", smooth=True,
        )
        # little arms
        c.create_oval(cx - 40 * k, cy - 8 * k, cx - 24 * k, cy + 8 * k,
                      fill=self.body, outline="")
        c.create_oval(cx + 24 * k, cy - 8 * k, cx + 40 * k, cy + 8 * k,
                      fill=self.body, outline="")
        # eyes
        self._eye(c, cx - 10 * k, cy - 10 * k, 6 * k, k)
        self._eye(c, cx + 10 * k, cy - 10 * k, 6 * k, k)
        # open mouth
        c.create_oval(cx - 6 * k, cy + 2 * k, cx + 6 * k, cy + 14 * k,
                      fill=self.beak, outline="")
        # cheeks
        c.create_oval(cx - 24 * k, cy - 2 * k, cx - 16 * k, cy + 6 * k,
                      fill=self.cheek, outline="")
        c.create_oval(cx + 16 * k, cy - 2 * k, cx + 24 * k, cy + 6 * k,
                      fill=self.cheek, outline="")

    # -- movement -----------------------------------------------------
    def _place(self):
        self.win.geometry(f"{self.size}x{self.size}+{int(self.x)}+{int(self.y)}")

    def update(self, multiplier=1.0):
        if self.drag_origin is not None:
            return
        self.tick += 1
        if self.tick % self.flap_every == 0:
            self.wing_up = not self.wing_up

        # wander a little
        self.angle += random.uniform(-self.wander, self.wander)

        speed = self.speed * multiplier * (2.6 if self.boost > 0 else 1.0)
        if self.boost > 0:
            self.boost -= 1

        self.x += math.cos(self.angle) * speed
        self.y += math.sin(self.angle) * speed + math.sin(self.tick * 0.08) * self.bob

        # bounce off the screen edges
        left, top, right, bottom = self.bounds
        max_x, max_y = max(left, right - self.size), max(top, bottom - self.size)
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

        if self.trail:
            self.ghosts.append((self.size // 2, self.size // 2))
            del self.ghosts[:-TRAIL_LENGTH]

        self._place()
        self.draw()

    def boop(self):
        """A click gives the pet a happy burst of speed in a new direction."""
        self.boost = 25
        self.angle = random.uniform(0, 2 * math.pi)
        if self.sound != "none":
            try:
                import winsound
                tone = {"chirp": 1400, "hoot": 500, "beep": 900}.get(self.sound, 1200)
                winsound.Beep(tone, 60)
            except (ImportError, RuntimeError):
                pass

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
        ttk.Label(content, text="Design a pet with DeepSeek",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.ai_status = ttk.Label(content, foreground="#555555", wraplength=390)
        self.ai_status.pack(anchor="w", pady=(4, 8))
        ai_row = ttk.Frame(content)
        ai_row.pack(fill="x")
        self.ai_button = ttk.Button(ai_row, text="Design a pet with AI", command=self.design_pet_with_ai)
        self.ai_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.key_button = ttk.Button(ai_row, text="API key…", command=self.set_api_key)
        self.key_button.pack(side="left", padx=(6, 0))
        ttk.Separator(content).pack(fill="x", pady=18)
        ttk.Label(content, text="Click a bird to boop it. Drag to move it.\n"
                  "Minimize this panel to keep your pets flying.\n"
                  "Closing the panel quits the app.", foreground="#555555").pack(anchor="w")
        self.save_status = ttk.Label(content, foreground="#9c321a", wraplength=390)
        self.save_status.pack(anchor="w", pady=(6, 0))
        ttk.Button(content, text="Quit Desktop Pets", command=self.quit_all).pack(anchor="e", pady=(8, 0))
        self._speed_changed()
        self._refresh_ai_status()
        for design in self.settings["pets"]:
            self.add_pet(design)
        while len(self.pets) < self.settings["count"]:
            self.add_pet()
        self._refresh_label()
        self._loop()

    # -- DeepSeek pet designer ----------------------------------------
    def _refresh_ai_status(self):
        if pet_ai is None:
            self.ai_button.config(state="disabled")
            self.key_button.config(state="disabled")
            self.ai_status.config(text="pet_ai.py is missing, so AI pets are unavailable.")
            return
        if pet_ai.load_api_key():
            self.ai_status.config(text="Ready. Describe a pet, or leave it blank for a surprise.")
        else:
            self.ai_status.config(
                text="No API key yet. Click \"API key…\" and paste your DeepSeek key "
                     "(get one at platform.deepseek.com).")

    def set_api_key(self):
        if pet_ai is None:
            return
        current = pet_ai.load_api_key()
        key = simpledialog.askstring(
            "DeepSeek API key",
            "Paste your DeepSeek API key.\nIt is stored in %LOCALAPPDATA%\\Desktop Pets\\api_key.txt",
            initialvalue=current, show="*", parent=self.root,
        )
        if key is None:
            return
        key = key.strip()
        if not key:
            return
        try:
            pet_ai.save_api_key(key)
        except OSError as exc:
            messagebox.showerror("Desktop Pets", f"Could not save the key:\n{exc}", parent=self.root)
            return
        self._refresh_ai_status()

    def design_pet_with_ai(self):
        if pet_ai is None:
            return
        if not pet_ai.load_api_key():
            self.set_api_key()
            if not pet_ai.load_api_key():
                return
        idea = simpledialog.askstring(
            "Design a pet",
            "Describe the pet you want.\nFor example: a sleepy purple owl that leaves a trail.\n"
            "Leave blank and DeepSeek will surprise you.",
            parent=self.root,
        )
        if idea is None:
            return
        self.ai_button.config(state="disabled", text="Designing…")
        self.ai_status.config(text="Asking DeepSeek to design your pet…")
        threading.Thread(target=self._design_worker, args=(idea,), daemon=True).start()

    def _design_worker(self, idea):
        try:
            design = pet_ai.design_pet(idea)
        except RuntimeError as exc:
            self.root.after(0, self._design_failed, str(exc))
        except Exception as exc:  # noqa: BLE001 - never let the thread die silently
            logging.exception("Pet design failed")
            self.root.after(0, self._design_failed, f"Unexpected error: {exc}")
        else:
            self.root.after(0, self._design_ready, design)

    def _design_failed(self, message):
        self.ai_button.config(state="normal", text="Design a pet with AI")
        self.ai_status.config(text="Could not design a pet.")
        messagebox.showerror("Desktop Pets", message, parent=self.root)

    def _design_ready(self, design):
        self.ai_button.config(state="normal", text="Design a pet with AI")
        self.ai_status.config(text=f"Ready. Last pet: {design.get('name', 'a pet')}.")
        if len(self.pets) >= MAX_PETS:
            messagebox.showinfo("Desktop Pets",
                                f"You already have {MAX_PETS} pets. Remove one first.",
                                parent=self.root)
            return
        self.add_pet(design)
        self.save_settings()

    def add_pet(self, design=None):
        if len(self.pets) >= MAX_PETS:
            return
        pet = Pet(self.root, self.bounds, self.topmost.get(), design)
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
        data = {
            "count": len(self.pets),
            "speed": self.speed.get(),
            "topmost": self.topmost.get(),
            "pets": [pet.design for pet in self.pets if pet.design],
        }
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
