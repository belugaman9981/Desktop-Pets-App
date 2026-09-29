"""Exercise the real Tk pets without loading or changing user settings."""

import math
import tkinter as tk
import unittest

import desktop_pets


class PetBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display unavailable: {exc}") from exc
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.pets = []

    def tearDown(self):
        for pet in self.pets:
            pet.destroy()

    def pet(self, **design):
        pet = desktop_pets.Pet(self.root, (0, 0, 1200, 900), design=design)
        pet.win.withdraw()
        pet.x, pet.y = 300, 300
        self.pets.append(pet)
        return pet

    def test_every_shape_accessory_draws_and_has_a_context_menu(self):
        for shape in ("bird", "fish", "cat", "blob", "bug", "ghost"):
            for accessory in ("none", "bow", "hat", "crown", "glasses"):
                with self.subTest(shape=shape, accessory=accessory):
                    pet = self.pet(shape=shape, accessory=accessory)
                    for direction in (0, math.pi):
                        pet.angle = direction
                        pet.draw()
                        self.assertGreater(len(pet.canvas.find_all()), 3)
                        self.assertEqual(bool(pet.canvas.find_withtag("accessory")),
                                         accessory != "none")
                    self.assertEqual(pet.menu.entrycget(0, "label"), pet.name)

    def test_nap_and_dance_stay_put_and_boop_wakes_pet(self):
        pet = self.pet(trail=True)
        for action in ("nap", "dance"):
            self.assertTrue(pet.set_action(action))
            position = (pet.x, pet.y)
            for _ in range(8):
                pet.update(spontaneous=False)
            self.assertEqual((pet.x, pet.y), position)
            if action == "nap":
                self.assertTrue(pet.canvas.find_withtag("eyes-closed"))
        pet.set_action("nap")
        pet.boop()
        self.assertEqual(pet.action, "wander")
        self.assertGreater(pet.boost, 0)
        self.assertEqual(pet.caption, "Boop!")
        self.assertFalse(pet.sound_enabled)

    def test_follow_approaches_cursor_and_finishes(self):
        pet = self.pet()
        pet.set_action("follow")
        cursor = (900, 700)
        before = math.hypot(cursor[0] - pet.x - pet.size / 2,
                            cursor[1] - pet.y - pet.size / 2)
        for _ in range(20):
            pet.update(cursor=cursor, spontaneous=False)
        after = math.hypot(cursor[0] - pet.x - pet.size / 2,
                           cursor[1] - pet.y - pet.size / 2)
        self.assertLess(after, before)
        near_cursor = (pet.x + pet.size / 2 + 20, pet.y + pet.size / 2)
        position = (pet.x, pet.y)
        pet.update(cursor=near_cursor, spontaneous=False)
        self.assertEqual((pet.x, pet.y), position)
        while pet.action_ticks:
            pet.update(cursor=cursor, spontaneous=False)
        self.assertEqual(pet.action, "wander")

    def test_trail_uses_previous_screen_positions_and_never_mirrors(self):
        pet = self.pet(trail=True, bob=0)
        pet.angle, pet.wander, pet.tick = 0, 0, 0
        for _ in range(10):
            pet.update(spontaneous=False)
        self.assertEqual(len(set(pet.ghosts)), 5)
        for angle in (0, math.pi):
            pet.angle = angle
            pet.draw()
            first = pet.canvas.find_withtag("trail")[0]
            x1, _, x2, _ = pet.canvas.coords(first)
            expected = pet.ghosts[0][0] - pet.x + pet.size / 2
            self.assertAlmostEqual((x1 + x2) / 2, expected)

    def test_treat_draws_hearts_and_caption_stays_readable(self):
        pet = self.pet()
        pet.set_action("treat")
        for angle in (0, math.pi):
            pet.angle = angle
            pet.draw()
            self.assertEqual(len(pet.canvas.find_withtag("reaction")), 3)
            caption = [item for item in pet.canvas.find_withtag("caption")
                       if pet.canvas.type(item) == "text"][0]
            self.assertEqual(pet.canvas.itemcget(caption, "text"), "Yum! Thank you")
            self.assertAlmostEqual(pet.canvas.coords(caption)[0], pet.size / 2)

    def test_spontaneous_switch_and_bounds(self):
        pet = self.pet()
        pet.idle_ticks = 0
        pet.update(spontaneous=False)
        self.assertEqual(pet.action, "wander")
        pet.update(spontaneous=True)
        self.assertIn(pet.action, ("dance", "nap", "zoom"))
        self.assertGreater(pet.idle_ticks, 0)
        self.assertFalse(pet.set_action("invalid"))
        pet.set_action("zoom")
        pet.x, pet.y, pet.angle = 0, 0, math.pi * 1.25
        pet.update(spontaneous=False)
        self.assertGreaterEqual(pet.x, 0)
        self.assertGreaterEqual(pet.y, 0)


if __name__ == "__main__":
    unittest.main()
