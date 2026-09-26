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
import tkinter as tk
from tkinter import messagebox

# This color becomes see-through on Windows. Nothing drawn may use it.
TRANSPARENT = "black"

PET_SIZE = 130          # pixel size of each pet's window
TICK_MS = 40            # movement timer interval
FLAP_EVERY = 4          # ticks between wing flaps
MAX_PETS = 12
START_PETS = 3

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

    def __init__(self, master, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.body, self.belly = random.choice(PALETTES)

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
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
        self.canvas.bind("<Button-1>", lambda _event: self.boop())

        # flight state
        self.x = random.uniform(0, screen_w - PET_SIZE)
        self.y = random.uniform(0, screen_h - PET_SIZE)
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = random.uniform(2.0, 3.5)
        self.tick = random.randrange(0, 1000)
        self.wing_up = True
        self.boost = 0  # boop speed-burst timer, in ticks

        self._place()
        self.draw()

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

    # -- movement -----------------------------------------------------
    def _place(self):
        self.win.geometry(f"{PET_SIZE}x{PET_SIZE}+{int(self.x)}+{int(self.y)}")

    def update(self):
        self.tick += 1
        if self.tick % FLAP_EVERY == 0:
            self.wing_up = not self.wing_up

        # wander a little
        self.angle += random.uniform(-0.25, 0.25)

        speed = self.speed * (2.6 if self.boost > 0 else 1.0)
        if self.boost > 0:
            self.boost -= 1

        self.x += math.cos(self.angle) * speed
        self.y += math.sin(self.angle) * speed + math.sin(self.tick * 0.08) * 0.8

        # bounce off the screen edges
        margin = 10
        if self.x < margin:
            self.x = margin
            self.angle = math.pi - self.angle
        elif self.x > self.screen_w - PET_SIZE - margin:
            self.x = self.screen_w - PET_SIZE - margin
            self.angle = math.pi - self.angle
        if self.y < margin:
            self.y = margin
            self.angle = -self.angle
        elif self.y > self.screen_h - PET_SIZE - margin:
            self.y = self.screen_h - PET_SIZE - margin
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
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        self.pets = []

        # control panel
        self.panel = tk.Toplevel(self.root)
        self.panel.title("Desktop Pets")
        self.panel.resizable(False, False)
        self.panel.protocol("WM_DELETE_WINDOW", self.quit_all)

        tk.Label(self.panel, text="Your tiny flying pets",
                 font=("Segoe UI", 12, "bold")).pack(padx=16, pady=(12, 2))
        self.count_label = tk.Label(self.panel, text="", font=("Segoe UI", 10))
        self.count_label.pack(padx=16, pady=2)
        tk.Label(self.panel, text="Tip: click a pet to boop it!",
                 font=("Segoe UI", 9), fg="gray").pack(padx=16, pady=(0, 8))

        buttons = tk.Frame(self.panel)
        buttons.pack(padx=12, pady=(0, 12))
        tk.Button(buttons, text="Add pet", width=10,
                  command=self.add_pet).pack(side="left", padx=4)
        tk.Button(buttons, text="Remove pet", width=10,
                  command=self.remove_pet).pack(side="left", padx=4)
        tk.Button(buttons, text="Close all", width=10,
                  command=self.quit_all).pack(side="left", padx=4)

        for _ in range(START_PETS):
            self.add_pet()
        self._refresh_label()
        self._loop()

    def add_pet(self):
        if len(self.pets) >= MAX_PETS:
            return
        self.pets.append(Pet(self.root, self.screen_w, self.screen_h))
        self._refresh_label()

    def remove_pet(self):
        if self.pets:
            self.pets.pop().destroy()
            self._refresh_label()

    def _refresh_label(self):
        n = len(self.pets)
        self.count_label.config(
            text=f"{n} pet{'s' if n != 1 else ''} on your desktop")

    def _loop(self):
        for pet in self.pets:
            pet.update()
        self.root.after(TICK_MS, self._loop)

    def quit_all(self):
        for pet in self.pets:
            pet.destroy()
        self.pets = []
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if sys.platform != "win32":
        messagebox.showerror(
            "Desktop Pets",
            "Desktop Pets needs Windows to run.\n\n"
            "Please copy these files to a Windows 10/11 PC with "
            "Python 3 installed and run run_pets.bat there.",
        )
        sys.exit(1)
    App().run()
