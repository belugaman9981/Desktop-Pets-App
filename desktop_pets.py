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
import queue
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from acumen_client import AcumenClient, normalize_base_url
from acumen_bridge import LocalBridge

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
    defaults = {"count": START_PETS, "speed": 1.0, "topmost": True, "pets": [],
                "spontaneous": True, "sound": False, "draft": "", "idea": "",
                "acumen_url": "http://127.0.0.1:8765"}
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
        for field in ("spontaneous", "sound"):
            if type(data.get(field)) is bool:
                defaults[field] = data[field]
        for field in ("draft", "idea"):
            if isinstance(data.get(field), str):
                defaults[field] = data[field][:12000]
        if isinstance(data.get("acumen_url"), str):
            try:
                defaults["acumen_url"] = normalize_base_url(data["acumen_url"])
            except RuntimeError:
                pass
    except (OSError, ValueError, OverflowError):
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
        if pet_ai is not None:
            if design is None and hasattr(pet_ai, "random_pet"):
                design = pet_ai.random_pet()
            clean = getattr(pet_ai, "clean_design", None) or pet_ai._clean
            design = clean(design)
        else:
            # Keep the basic pets usable if the optional designer is missing.
            design = {}
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

        self.accessory = design.get("accessory", "none")
        self.temperament = design.get("temperament", "playful")
        self.sound_enabled = False
        self.action = "wander"
        self.action_ticks = 0
        self.caption = ""
        self.caption_ticks = 0
        self.idle_ticks = random.randint(350, 750)
        self.size = max(60, int(PET_SIZE * self.scale))
        self.ghosts = []  # recent screen positions, for the trail effect

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
        self.canvas.bind("<Button-3>", self._show_menu)
        self.menu = tk.Menu(self.win, tearoff=False)
        self.menu.add_command(label=self.name, state="disabled")
        self.menu.add_separator()
        for label, action in (("Give a treat", "treat"), ("Dance", "dance"),
                              ("Take a nap", "nap"), ("Zoom around", "zoom"),
                              ("Follow my cursor for 15s", "follow"),
                              ("Wander", "wander")):
            self.menu.add_command(label=label, command=lambda a=action: self.set_action(a))
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

    def _show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def set_action(self, action):
        """Start a short activity. Cursor following only starts on request."""
        durations = {"wander": 0, "dance": 5, "nap": 12, "zoom": 4,
                     "follow": 15, "treat": 3}
        if action not in durations:
            return False
        self.action = action
        self.action_ticks = int(durations[action] * 1000 / TICK_MS)
        self.boost = 0
        self.idle_ticks = random.randint(350, 750)
        self.caption = {"wander": "Off we go", "dance": "Let's dance!",
                        "nap": "Zzz...", "zoom": "Wheee!",
                        "follow": "Following you", "treat": "Yum! Thank you"}[action]
        self.caption_ticks = self.action_ticks or 50
        if action == "zoom":
            self.angle = random.uniform(0, 2 * math.pi)
        if action in ("nap", "dance", "treat"):
            self.ghosts.clear()
        self.draw()
        return True

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
            self.ghosts.clear()
            self._clamp()
            self._place()
            self.draw()

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
        if self.action == "dance":
            cx += math.sin(self.tick * 0.45) * 7 * k
            cy -= abs(math.sin(self.tick * 0.3)) * 7 * k
        elif self.action == "nap":
            cy += math.sin(self.tick * 0.06) * 2 * k

        # fading trail behind the pet
        if self.trail and self.ghosts:
            for index, (gx, gy) in enumerate(self.ghosts):
                fade = (index + 1) / (len(self.ghosts) + 1)
                radius = 10 * k * (0.4 + fade)
                gx, gy = gx - self.x + s / 2, gy - self.y + s / 2
                c.create_oval(gx - radius, gy - radius, gx + radius, gy + radius,
                              fill=self.belly, outline="", stipple="gray50", tags="trail")

        background_items = set(c.find_all())
        drawer = {
            "bird": self._draw_bird,
            "fish": self._draw_fish,
            "cat": self._draw_cat,
            "blob": self._draw_blob,
            "bug": self._draw_bug,
            "ghost": self._draw_ghost,
        }.get(self.shape, self._draw_bird)
        drawer(c, cx, cy, k)
        self._draw_accessory(c, cx, cy, k)

        # Mirror only the animal: captions and the world-space trail stay put.
        if math.cos(self.angle) < 0:
            for item in set(c.find_all()) - background_items:
                coords = c.coords(item)
                for i in range(0, len(coords), 2):
                    coords[i] = s - coords[i]
                c.coords(item, *coords)

        # sparkles twinkling around the pet
        if self.sparkle:
            for index in range(3):
                phase = self.tick * 0.15 + index * 2.1
                sx = cx + math.cos(phase) * 40 * k
                sy = cy + math.sin(phase * 1.3) * 34 * k
                r = 2.5 * k * (0.6 + 0.4 * math.sin(phase * 2))
                c.create_oval(sx - r, sy - r, sx + r, sy + r,
                              fill="#fff6c2", outline="")

        if self.action == "treat":
            for index in range(3):
                hx = s / 2 + (index - 1) * 23 * k
                hy = (30 - (self.tick * 0.8 + index * 9) % 24) * k
                r = 5 * k
                c.create_polygon(hx, hy + r, hx - r, hy, hx - r, hy - r,
                                 hx, hy - r / 2, hx + r, hy - r,
                                 hx + r, hy, fill=self.cheek, outline="",
                                 smooth=True, tags="reaction")

        if self.caption and self.caption_ticks > 0:
            text = c.create_text(s / 2, s - 11 * k, text=self.caption,
                                 font=("Segoe UI", max(7, int(8 * k))),
                                 fill="#f9fafb", width=s - 10 * k, tags="caption")
            box = c.bbox(text)
            if box:
                plate = c.create_rectangle(box[0] - 4 * k, box[1] - 2 * k,
                                           box[2] + 4 * k, box[3] + 2 * k,
                                           fill="#27313f", outline="", tags="caption")
                c.tag_lower(plate, text)

    def _draw_accessory(self, c, cx, cy, k):
        top = cy - (39 if self.shape in ("cat", "bug") else 30) * k
        if self.accessory == "bow":
            y = cy + 21 * k
            c.create_polygon(cx, y, cx - 13 * k, y - 7 * k,
                             cx - 13 * k, y + 7 * k, fill=self.cheek,
                             outline=self.eye, tags="accessory")
            c.create_polygon(cx, y, cx + 13 * k, y - 7 * k,
                             cx + 13 * k, y + 7 * k, fill=self.cheek,
                             outline=self.eye, tags="accessory")
            c.create_oval(cx - 3 * k, y - 3 * k, cx + 3 * k, y + 3 * k,
                          fill=self.beak, outline="", tags="accessory")
        elif self.accessory == "hat":
            c.create_rectangle(cx - 11 * k, top - 13 * k,
                               cx + 11 * k, top + 2 * k,
                               fill=self.eye, outline="", tags="accessory")
            c.create_rectangle(cx - 11 * k, top - 3 * k,
                               cx + 11 * k, top + 1 * k,
                               fill=self.cheek, outline="", tags="accessory")
            c.create_line(cx - 19 * k, top + 2 * k, cx + 19 * k, top + 2 * k,
                          fill=self.eye, width=max(2, int(4 * k)), tags="accessory")
        elif self.accessory == "crown":
            c.create_polygon(cx - 17 * k, top - 11 * k, cx - 10 * k, top - 4 * k,
                             cx, top - 17 * k, cx + 10 * k, top - 4 * k,
                             cx + 17 * k, top - 11 * k, cx + 14 * k, top + 4 * k,
                             cx - 14 * k, top + 4 * k,
                             fill="#f3c851", outline="#b98523", tags="accessory")
        elif self.accessory == "glasses":
            eyes = {"bird": [(17, -8)], "fish": [(16, -6)],
                    "cat": [(-12, -8), (12, -8)],
                    "blob": [(-11, -8), (11, -8)],
                    "bug": [(-9, -6), (9, -6)],
                    "ghost": [(-10, -10), (10, -10)]}.get(self.shape, [(17, -8)])
            radius = 9 if self.shape == "blob" else 7
            for ex, ey in eyes:
                c.create_oval(cx + (ex - radius) * k, cy + (ey - radius) * k,
                              cx + (ex + radius) * k, cy + (ey + radius) * k,
                              outline=self.eye, width=max(1, int(2 * k)), tags="accessory")
            if len(eyes) == 2:
                c.create_line(cx + (eyes[0][0] + radius) * k, cy + eyes[0][1] * k,
                              cx + (eyes[1][0] - radius) * k, cy + eyes[1][1] * k,
                              fill=self.eye, width=max(1, int(2 * k)), tags="accessory")
            else:
                c.create_line(cx - 8 * k, cy - 12 * k, cx + 10 * k, cy - 8 * k,
                              fill=self.eye, width=max(1, int(2 * k)), tags="accessory")

    def _eye(self, c, x, y, r, k):
        """A round eye with a highlight, centred on (x, y)."""
        if self.action == "nap" or self.tick % 115 < 4:
            c.create_line(x - r, y, x, y + 2 * k, x + r, y,
                          smooth=True, fill=self.eye, width=max(1, int(2 * k)),
                          tags="eyes-closed")
            return
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
        self.win.geometry(f"{self.size}x{self.size}{int(self.x):+d}{int(self.y):+d}")

    def update(self, multiplier=1.0, cursor=None, spontaneous=True):
        if self.drag_origin is not None:
            return
        self.tick += 1
        if self.caption_ticks > 0:
            self.caption_ticks -= 1
        if self.action_ticks > 0:
            self.action_ticks -= 1
            if self.action_ticks == 0:
                self.action = "wander"
                self.caption = ""
                self.ghosts.clear()
        self.idle_ticks = max(0, self.idle_ticks - 1)
        if spontaneous and self.action == "wander" and self.idle_ticks == 0:
            choices = {"calm": ("nap", "nap", "dance"),
                       "curious": ("dance", "zoom", "nap"),
                       "playful": ("dance", "zoom", "zoom")}
            self.set_action(random.choice(choices.get(self.temperament, choices["playful"])))
        if self.action != "nap" and self.tick % self.flap_every == 0:
            self.wing_up = not self.wing_up

        moving = self.action not in ("nap", "dance", "treat")
        speed = self.speed * multiplier * (2.6 if self.boost > 0 or self.action == "zoom" else 1.0)
        if self.boost > 0:
            self.boost -= 1

        if self.action == "follow" and cursor is not None:
            dx = cursor[0] - (self.x + self.size / 2)
            dy = cursor[1] - (self.y + self.size / 2)
            distance = math.hypot(dx, dy)
            if distance > 45:
                self.angle = math.atan2(dy, dx)
                speed = min(speed * 1.5, distance - 45)
            else:
                moving = False
        else:
            self.angle += random.uniform(-self.wander, self.wander)

        if moving:
            if self.trail and self.tick % 2 == 0:
                self.ghosts.append((self.x, self.y))
                del self.ghosts[:-TRAIL_LENGTH]
            self.x += math.cos(self.angle) * speed
            self.y += math.sin(self.angle) * speed
            if self.action != "follow":
                self.y += math.sin(self.tick * 0.08) * self.bob
        elif self.ghosts:
            self.ghosts.pop(0)

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

        self._place()
        self.draw()

    def boop(self):
        """A click gives the pet a happy burst of speed in a new direction."""
        self.action = "wander"
        self.action_ticks = 0
        self.caption, self.caption_ticks = "Boop!", 45
        self.idle_ticks = random.randint(350, 750)
        self.boost = 25
        self.angle = random.uniform(0, 2 * math.pi)
        self.draw()
        if self.sound_enabled and self.sound != "none":
            tone = {"chirp": 1400, "hoot": 500, "beep": 900}.get(self.sound, 1200)

            def play():
                try:
                    import winsound
                    winsound.Beep(tone, 60)
                except (ImportError, RuntimeError):
                    pass

            threading.Thread(target=play, daemon=True).start()

    def destroy(self):
        self.win.destroy()


class App:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else settings_path()
        self.settings = load_settings(self.config_path)
        self.root = tk.Tk()
        self.root.report_callback_exception = self._callback_error
        self.bounds = work_area(self.root)
        self.pets = []
        self.paused = self.hidden = self.closed = False
        self.timer = None
        self.frame = 0
        self.results = queue.Queue()
        self.busy = False
        self.request_id = 0
        self.client = None
        self.bridge = LocalBridge()
        self.last_question = ""
        self.speed = tk.DoubleVar(value=self.settings["speed"])
        self.topmost = tk.BooleanVar(value=self.settings["topmost"])
        self.spontaneous = tk.BooleanVar(value=self.settings["spontaneous"])
        self.sound = tk.BooleanVar(value=self.settings["sound"])
        self.idea = tk.StringVar(value=self.settings["idea"])
        self.acumen_url = tk.StringVar(value=os.environ.get("ACUMEN_BRIDGE_URL") or self.settings["acumen_url"])
        self.token = tk.StringVar(value=os.environ.get("ACUMEN_TOKEN", ""))
        self.panel = self.root
        self.panel.title("Desktop Pets")
        self.panel.geometry("620x740")
        self.panel.minsize(590, 710)
        self.panel.protocol("WM_DELETE_WINDOW", self.quit_all)
        icon = Path(__file__).with_name("pets.ico")
        if icon.exists():
            self.panel.iconbitmap(str(icon))
        style = ttk.Style(self.root)
        style.theme_use("vista" if "vista" in style.theme_names() else "clam")
        style.configure("TButton", padding=(8, 5), font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        content = ttk.Frame(self.panel, padding=16)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="A little company for your desktop",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.count_label = ttk.Label(content)
        self.count_label.pack(anchor="w", pady=(6, 12))
        footer = ttk.Frame(content)
        footer.pack(side="bottom", fill="x", pady=(6, 0))
        ttk.Label(footer, text="Minimize to keep pets flying. Close to quit.",
                  foreground="#555555").pack(side="left")
        ttk.Button(footer, text="Quit", command=self.quit_all).pack(side="right")
        self.save_status = ttk.Label(content, foreground="#9c321a", wraplength=550)
        self.tabs = ttk.Notebook(content)
        self.tabs.pack(fill="both", expand=True)
        play = ttk.Frame(self.tabs, padding=14)
        chat = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(play, text="Pets & play")
        self.tabs.add(chat, text="Ask Acumen")
        self._build_play(play)
        self._build_chat(chat)
        self._speed_changed()
        for design in self.settings["pets"]:
            self.add_pet(design)
        while len(self.pets) < self.settings["count"]:
            self.add_pet()
        self._refresh_label()
        self._loop()

    def _build_play(self, content):
        row = ttk.Frame(content)
        row.pack(fill="x")
        self.add_button = ttk.Button(row, text="Surprise pet", command=self.add_pet)
        self.add_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.remove_button = ttk.Button(row, text="Remove last pet", command=self.remove_pet)
        self.remove_button.pack(side="left", expand=True, fill="x")
        ttk.Label(content, text="Make a pet", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(10, 4))
        ttk.Label(content, text="Try a sleepy purple cat with a crown. Made locally, instantly.",
                  foreground="#555555").pack(anchor="w")
        row = ttk.Frame(content)
        row.pack(fill="x", pady=(6, 10))
        self.idea_entry = ttk.Entry(row, textvariable=self.idea)
        self.idea_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.idea_entry.bind("<Return>", lambda _event: self.design_pet())
        self.design_button = ttk.Button(row, text="Create", command=self.design_pet)
        self.design_button.pack(side="right")
        ttk.Label(content, text="Play with everyone", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 4))
        actions = ttk.Frame(content)
        actions.pack(fill="x")
        for index, (label, action) in enumerate((("Give treats", "treat"), ("Dance", "dance"),
                ("Nap", "nap"), ("Zoomies", "zoom"), ("Follow cursor", "follow"), ("Wander", "wander"))):
            ttk.Button(actions, text=label, command=lambda a=action: self.play(a)).grid(
                row=index // 3, column=index % 3, sticky="ew", padx=2, pady=3)
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        self.play_status = ttk.Label(content, text="Right-click any pet to play with just that pet.",
                                     foreground="#555555", wraplength=510)
        self.play_status.pack(anchor="w", pady=(6, 6))
        row = ttk.Frame(content)
        row.pack(fill="x")
        self.pause_button = ttk.Button(row, text="Pause", command=self.toggle_pause)
        self.pause_button.pack(side="left", expand=True, fill="x", padx=(0, 6))
        self.hide_button = ttk.Button(row, text="Hide pets", command=self.toggle_hidden)
        self.hide_button.pack(side="left", expand=True, fill="x")
        self.speed_label = ttk.Label(content)
        self.speed_label.pack(anchor="w", pady=(8, 0))
        ttk.Scale(content, from_=0.25, to=2.0, variable=self.speed,
                  command=self._speed_changed).pack(fill="x", pady=(4, 8))
        for label, variable in (("Little surprises while pets wander", self.spontaneous),
                                ("Pet sounds", self.sound),
                                ("Keep pets above other windows", self.topmost)):
            ttk.Checkbutton(content, text=label, variable=variable,
                            command=self._preferences_changed).pack(anchor="w", pady=2)
        ttk.Label(content, text="Click to boop. Drag to move. Follow cursor lasts 15 seconds.",
                  foreground="#555555", wraplength=510).pack(anchor="w", pady=(10, 0))

    def _build_chat(self, content):
        ttk.Label(content, text="Your pets, with AcumenAI", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(content, text="Questions go to your local Acumen bridge. Pet creation stays local.",
                  foreground="#555555", wraplength=510).pack(anchor="w", pady=(4, 8))
        fields = ttk.Frame(content)
        fields.pack(fill="x")
        fields.columnconfigure(1, weight=1)
        ttk.Label(fields, text="Address").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.url_entry = ttk.Entry(fields, textvariable=self.acumen_url)
        self.url_entry.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(fields, text="Pairing token").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.token_entry = ttk.Entry(fields, textvariable=self.token, show="*")
        self.token_entry.grid(row=1, column=1, sticky="ew", pady=3)
        self.token_entry.bind("<Return>", lambda _event: self.connect_acumen())
        buttons = ttk.Frame(content)
        buttons.pack(fill="x", pady=(6, 4))
        self.connect_button = ttk.Button(buttons, text="Connect", command=self.connect_acumen)
        self.connect_button.pack(side="left")
        self.start_button = ttk.Button(buttons, text="Start Acumen", command=self.start_acumen)
        self.start_button.pack(side="left", padx=6)
        ttk.Button(buttons, text="Open Acumen", command=self.open_acumen).pack(side="left")
        self.ai_status = ttk.Label(content, text="Start Acumen here, or paste a running bridge's token and connect.",
                                   wraplength=510, foreground="#555555")
        self.ai_status.pack(anchor="w", pady=(4, 6))
        self.transcript = ScrolledText(content, height=9, wrap="word", font=("Segoe UI", 10),
                                      relief="solid", borderwidth=1, padx=10, pady=8, state="disabled")
        self.transcript.pack(fill="both", expand=True)
        self.transcript.tag_configure("You", foreground="#555555")
        self.transcript.tag_configure("Acumen", foreground="#176648")
        self.transcript.tag_configure("Connection", foreground="#9c321a")
        ttk.Label(content, text="Ask a question · Ctrl+Enter to send").pack(anchor="w", pady=(8, 4))
        self.draft = tk.Text(content, height=3, wrap="word", font=("Segoe UI", 10), undo=True)
        self.draft.pack(fill="x")
        self.draft.insert("1.0", self.settings["draft"])
        self.draft.bind("<Control-Return>", self._send_shortcut)
        row = ttk.Frame(content)
        row.pack(fill="x", pady=(6, 0))
        self.send_button = ttk.Button(row, text="Send", command=self.ask_acumen)
        self.send_button.pack(side="left")
        self.retry_button = ttk.Button(row, text="Retry last", command=self.retry_question, state="disabled")
        self.retry_button.pack(side="left", padx=6)
        ttk.Button(row, text="Copy answers", command=self.copy_answers).pack(side="right")

    def design_pet(self):
        if len(self.pets) >= MAX_PETS:
            return
        if pet_ai is None:
            self.play_status.config(text="pet_ai.py is missing. Restore it to create custom pets.")
            return
        design = pet_ai.design_pet(self.idea.get())
        self.add_pet(design)
        self.play_status.config(text=f"Welcome, {design['name']}. {design['personality']}")
        self.save_settings()

    def play(self, action):
        if not self.pets:
            self.play_status.config(text="Add a pet first, then choose something to play.")
            return
        for pet in self.pets:
            pet.set_action(action)
        labels = {"treat": "Treat time!", "dance": "A tiny desktop dance party.", "nap": "A moment of peace and quiet.",
                  "zoom": "Here come the zoomies.", "follow": "Move the cursor. Your pets will follow for 15 seconds.",
                  "wander": "Back to exploring."}
        suffix = " Press Resume to watch." if self.paused else " Show pets to watch." if self.hidden else ""
        self.play_status.config(text=labels.get(action, action) + suffix)

    def _set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        for widget in (self.connect_button, self.start_button, self.send_button, self.url_entry, self.token_entry):
            widget.config(state=state)
        self.retry_button.config(state="normal" if self.last_question and not busy else "disabled")
        self.send_button.config(text="Waiting…" if busy else "Send")

    def _launch_request(self, kind, work, question=""):
        if self.busy or self.closed:
            return
        self.request_id += 1
        request_id = self.request_id
        self._set_busy(True)

        def worker():
            try:
                value = work()
            except Exception as exc:
                self.results.put((request_id, kind, None, str(exc), question))
            else:
                self.results.put((request_id, kind, value, None, question))

        threading.Thread(target=worker, daemon=True).start()

    def _configured_client(self):
        return AcumenClient(self.acumen_url.get(), self.token.get())

    def connect_acumen(self):
        if self.busy:
            return
        try:
            client = self._configured_client()
        except RuntimeError as exc:
            self.ai_status.config(text=str(exc))
            return
        self.client = None
        self.ai_status.config(text="Checking the Acumen connection…")

        def connect():
            client.check_connection()
            return client

        self._launch_request("connect", connect)

    def start_acumen(self):
        if self.busy:
            return
        address = self.acumen_url.get()
        self.ai_status.config(text="Starting your local Acumen installation…")
        self._launch_request("start", lambda: self.bridge.start(address))

    def open_acumen(self):
        try:
            url = normalize_base_url(self.acumen_url.get())
        except RuntimeError as exc:
            self.ai_status.config(text=str(exc))
            return
        webbrowser.open(url)

    def _send_shortcut(self, _event):
        self.ask_acumen()
        return "break"

    def ask_acumen(self, question=None):
        if self.busy:
            return
        question = self.draft.get("1.0", "end-1c") if question is None else question
        if not question.strip():
            self.ai_status.config(text="Type a question first.")
            self.draft.focus_set()
            return
        try:
            client = self._configured_client()
        except RuntimeError as exc:
            self.ai_status.config(text=str(exc))
            return
        self.last_question = question
        self._append_message("You", question)
        self.ai_status.config(text="Acumen is answering. Your pets can keep playing.")
        self._launch_request("ask", lambda: client.ask(question), question)

    def retry_question(self):
        if self.last_question:
            self.ask_acumen(self.last_question)

    def _append_message(self, speaker, text):
        at_bottom = self.transcript.yview()[1] >= 0.98
        self.transcript.config(state="normal")
        self.transcript.insert("end", speaker + "\n", speaker)
        self.transcript.insert("end", text + "\n\n")
        self.transcript.config(state="disabled")
        if at_bottom:
            self.transcript.see("end")

    def copy_answers(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.transcript.get("1.0", "end-1c"))

    def _drain_results(self):
        while True:
            try:
                request_id, kind, value, error, question = self.results.get_nowait()
            except queue.Empty:
                return
            if request_id != self.request_id or self.closed:
                continue
            self._set_busy(False)
            if error:
                self.ai_status.config(text=error)
                if kind == "ask":
                    self._append_message("Connection", error)
                continue
            if kind in ("start", "connect"):
                self.client = value
                self.acumen_url.set(value.base_url)
                self.token.set(value.token)
                self.ai_status.config(text="Connected to Acumen. Pairing token is kept only for this session.")
            else:
                self._append_message("Acumen", value["text"])
                self.ai_status.config(text="Answer received from Acumen.")
                # A new draft typed while waiting must never be erased.
                if self.draft.get("1.0", "end-1c") == question:
                    self.draft.delete("1.0", "end")
                if self.pets:
                    random.choice(self.pets).set_action("treat")

    def add_pet(self, design=None):
        if len(self.pets) >= MAX_PETS:
            return
        pet = Pet(self.root, self.bounds, self.topmost.get(), design)
        pet.sound_enabled = self.sound.get()
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
        self.count_label.config(text=f"{n} of {MAX_PETS} pets" +
                                (" · hidden" if self.hidden else " · paused" if self.paused else " · exploring"))
        self.add_button.config(state="disabled" if n >= MAX_PETS else "normal")
        self.design_button.config(state="disabled" if n >= MAX_PETS else "normal")
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

    def _preferences_changed(self):
        for pet in self.pets:
            pet.win.attributes("-topmost", self.topmost.get())
            pet.sound_enabled = self.sound.get()
        self.save_settings()

    def save_settings(self):
        try:
            address = normalize_base_url(self.acumen_url.get())
        except RuntimeError:
            address = self.settings["acumen_url"]
        data = {"count": len(self.pets), "speed": self.speed.get(), "topmost": self.topmost.get(),
                "pets": [pet.design for pet in self.pets], "spontaneous": self.spontaneous.get(),
                "sound": self.sound.get(), "draft": self.draft.get("1.0", "end-1c")[:12000],
                "idea": self.idea.get()[:12000], "acumen_url": address}
        temporary = self.config_path.with_suffix(f".{os.getpid()}.tmp")
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
            temporary.replace(self.config_path)
        except OSError:
            logging.exception("Could not save settings")
            self.save_status.config(text="Settings could not be saved. Changes apply for this session.")
            self.save_status.pack(side="bottom", anchor="w", pady=(6, 0), before=self.tabs)
        else:
            self.save_status.config(text="")
            self.save_status.pack_forget()

    def _callback_error(self, exc_type, exc, tb):
        logging.error("App error", exc_info=(exc_type, exc, tb))
        messagebox.showerror("Desktop Pets", f"Something went wrong: {exc}\n\nPlease restart Desktop Pets.", parent=self.root)

    def _loop(self):
        if self.closed:
            return
        self._drain_results()
        self.frame += 1
        if self.frame % 50 == 0:
            self.bounds = work_area(self.root)
            for pet in self.pets:
                pet.bounds = self.bounds
                pet._clamp()
                pet._place()
        if not self.paused and not self.hidden:
            cursor = self.root.winfo_pointerxy() if any(pet.action == "follow" for pet in self.pets) else None
            for pet in self.pets:
                pet.update(self.speed.get(), cursor=cursor, spontaneous=self.spontaneous.get())
        if self.frame % 125 == 0:
            self.save_settings()
        self.timer = self.root.after(TICK_MS, self._loop)

    def quit_all(self):
        if self.closed:
            return
        self.save_settings()
        self.closed = True
        self.request_id += 1
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        for pet in self.pets:
            pet.destroy()
        self.pets = []
        self.root.destroy()
        self.bridge.close()

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
