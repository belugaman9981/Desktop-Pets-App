import math
import random
import unittest
from unittest.mock import patch

import pet_ai


class PetDesignTests(unittest.TestCase):
    def test_description_matches_visible_properties_and_is_repeatable(self):
        idea = "a tiny sleepy purple cat with a crown and sparkles without a trail"
        pet = pet_ai.design_pet(idea)
        self.assertEqual(pet, pet_ai.design_pet(idea.upper()))
        self.assertEqual((pet["shape"], pet["accessory"], pet["temperament"]), ("cat", "crown", "calm"))
        self.assertEqual(pet["body"], "#9b7bda")
        self.assertEqual(pet["size"], 0.7)
        self.assertTrue(pet["sparkle"])
        self.assertFalse(pet["trail"])

    def test_species_motion_and_explicit_negative_effects(self):
        pet = pet_ai.design_pet("fast golden koi with glasses no sparkles with a trail")
        self.assertEqual(pet["shape"], "fish")
        self.assertEqual(pet["accessory"], "glasses")
        self.assertEqual(pet["speed"], 1.9)
        self.assertFalse(pet["sparkle"])
        self.assertTrue(pet["trail"])
        self.assertEqual(pet_ai.design_pet("silent owl")["sound"], "none")

    def test_random_designs_cover_shapes_and_accessories(self):
        with patch.object(pet_ai, "random", random.Random(12)):
            pets = [pet_ai.random_pet() for _ in range(200)]
        self.assertEqual({p["shape"] for p in pets}, set(pet_ai.SHAPES))
        self.assertEqual({p["accessory"] for p in pets}, set(pet_ai.ACCESSORIES))
        self.assertGreater(len({p["body"] for p in pets}), 8)
        self.assertTrue(all(pet_ai.clean_design(p) == p for p in pets))

    def test_corrupt_persisted_designs_are_finite_drawable_and_bounded(self):
        for value in (None, [], {}, {"shape": [], "sound": {}, "body": "#ff00ff", "eye": "#-00001",
                "size": float("nan"), "flap": float("inf"), "speed": 10 ** 1000,
                "bob": True, "wander": -99, "accessory": "invalid", "name": "a\n" * 200}):
            pet = pet_ai.clean_design(value)
            self.assertIn(pet["shape"], pet_ai.SHAPES)
            self.assertNotEqual(pet["body"], "#ff00ff")
            self.assertEqual(pet, pet_ai.clean_design(pet))
            self.assertTrue(all(math.isfinite(pet[k]) for k in ("size", "speed", "flap", "bob", "wander")))
            self.assertLessEqual(len(pet["name"]), 20)


if __name__ == "__main__":
    unittest.main()
