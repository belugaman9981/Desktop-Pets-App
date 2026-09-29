#!/usr/bin/env python3
"""Offline desktop pet designs, with simple rules for words in a description.

This module never contacts a service and needs no API key. A nonempty description
always produces the same design; an empty description makes a random pet. The
six shapes are the ones the app actually knows how to draw.
"""

import hashlib
import json
import math
import random
import re


SHAPES = ("bird", "fish", "cat", "blob", "bug", "ghost")
ACCESSORIES = ("none", "bow", "hat", "crown", "glasses")
TEMPERAMENTS = ("playful", "calm", "curious")
DEFAULT_PET = {
    "name": "Mystery Bird", "shape": "bird",
    "body": "#e23b3b", "belly": "#f6b8b8", "beak": "#ff9f1a",
    "cheek": "#ff8fa3", "eye": "#141414",
    "size": 1.0, "speed": 1.0, "flap": 4, "bob": 0.8, "wander": 0.25,
    "trail": False, "sparkle": False, "sound": "chirp",
    "accessory": "none", "temperament": "curious",
    "personality": "A cheerful little bird who loves to explore.",
}

# label, body, belly, beak/nose, cheek; no palette uses the transparent color.
PALETTES = (
    ("Cherry", "#dc4949", "#ffcccc", "#ffd064", "#ff919c"),
    ("Blueberry", "#467fda", "#c3e2ff", "#ffd073", "#f59cbb"),
    ("Mango", "#f29a38", "#ffe3ae", "#bd6337", "#f77882"),
    ("Lavender", "#9b7bda", "#e7dcff", "#ffbf75", "#edabc8"),
    ("Mint", "#4dbb94", "#c9f6df", "#f3ba56", "#ffa2b3"),
    ("Bubblegum", "#e784b2", "#ffdaed", "#eda344", "#d95f92"),
    ("Honey", "#e9bd42", "#fff0b8", "#bc7542", "#ed9992"),
    ("Cocoa", "#957152", "#ead0b1", "#6e4942", "#dc9494"),
    ("Moonbeam", "#dddff3", "#faf7ff", "#9384d0", "#e6a9cd"),
    ("Midnight", "#49536e", "#9aa6c5", "#dfba61", "#c491b0"),
    ("Lagoon", "#45b7c6", "#c0f1f5", "#f4b458", "#f0a3bd"),
    ("Peach", "#f1a285", "#ffe4d6", "#c37756", "#ed7f97"),
)
_NAMES = {
    "bird": ("Pip", "Waffles", "Pebble", "Chirrup", "Crumpet", "Sprout"),
    "fish": ("Bubbles", "Nori", "Guppy", "Ripple", "Finn", "Puddle"),
    "cat": ("Mochi", "Mittens", "Noodle", "Biscuit", "Pounce", "Pickle"),
    "blob": ("Pudding", "Jellybean", "Squish", "Gumdrop", "Wobble", "Dumpling"),
    "bug": ("Dot", "Button", "Cricket", "Bean", "Doodle", "Clover"),
    "ghost": ("Boo", "Wisp", "Cashew", "Mallow", "Whisper", "Spook"),
}
_SOUNDS = {"bird": "chirp", "fish": "beep", "cat": "chirp",
           "blob": "beep", "bug": "beep", "ghost": "hoot"}
_HOBBIES = {
    "playful": ("chases imaginary butterflies", "collects tiny adventures", "loves a good boop"),
    "calm": ("enjoys a quiet float", "takes life one small snooze at a time", "drifts along peacefully"),
    "curious": ("inspects every corner", "wonders what is behind your windows", "always finds something interesting"),
}
_SPECIES = {
    "bird": "bird", "owl": "bird", "parrot": "bird", "penguin": "bird",
    "duck": "bird", "chicken": "bird", "chick": "bird", "sparrow": "bird",
    "pigeon": "bird", "robin": "bird", "raven": "bird", "crow": "bird",
    "fish": "fish", "goldfish": "fish", "shark": "fish", "guppy": "fish",
    "koi": "fish", "whale": "fish", "dolphin": "fish",
    "cat": "cat", "kitten": "cat", "kitty": "cat", "tiger": "cat",
    "lion": "cat", "fox": "cat",
    "blob": "blob", "slime": "blob", "jelly": "blob", "pudding": "blob",
    "bug": "bug", "beetle": "bug", "ladybug": "bug", "ladybird": "bug",
    "bee": "bug", "butterfly": "bug", "ant": "bug", "firefly": "bug",
    "ghost": "ghost", "spirit": "ghost", "phantom": "ghost", "spook": "ghost",
}
_COLORS = {
    "red": 0, "scarlet": 0, "crimson": 0,
    "blue": 1, "orange": 2, "purple": 3, "violet": 3, "lavender": 3,
    "green": 4, "mint": 4, "pink": 5, "yellow": 6, "gold": 6,
    "golden": 6, "brown": 7, "chocolate": 7, "white": 8, "silver": 8,
    "grey": 9, "gray": 9, "black": 9, "teal": 10, "cyan": 10,
    "turquoise": 10, "peach": 11,
}


def _text(value, fallback, limit):
    if not isinstance(value, str):
        return fallback
    text = " ".join("".join(c if c.isprintable() else " " for c in value).split())
    return text[:limit].rstrip() or fallback


def _hex_or(value, fallback):
    if isinstance(value, str):
        color = value.strip().lower()
        if re.fullmatch(r"#[0-9a-f]{6}", color) and color != "#ff00ff":
            return color
    return fallback


def _number(value, low, high, fallback):
    if type(value) not in (int, float):
        return fallback
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return fallback
    return max(low, min(high, number)) if math.isfinite(number) else fallback


def _choice(value, choices, fallback):
    if isinstance(value, str):
        value = value.strip().lower()
        if value in choices:
            return value
    return fallback


def _clean(raw):
    """Return a fresh safe design, including when persisted settings are corrupt."""
    pet = dict(DEFAULT_PET)
    if not isinstance(raw, dict):
        return pet
    for field, limit in (("name", 20), ("personality", 160)):
        pet[field] = _text(raw.get(field), DEFAULT_PET[field], limit)
    for field, choices in (("shape", SHAPES), ("sound", ("chirp", "hoot", "beep", "none")),
                           ("accessory", ACCESSORIES), ("temperament", TEMPERAMENTS)):
        pet[field] = _choice(raw.get(field), choices, DEFAULT_PET[field])
    for field in ("body", "belly", "beak", "cheek", "eye"):
        pet[field] = _hex_or(raw.get(field), DEFAULT_PET[field])
    for field, low, high in (("size", 0.7, 1.4), ("speed", 0.5, 2.0), ("flap", 2, 10),
                             ("bob", 0.0, 2.5), ("wander", 0.05, 0.6)):
        pet[field] = _number(raw.get(field), low, high, DEFAULT_PET[field])
    pet["flap"] = int(pet["flap"])
    pet["trail"] = raw.get("trail") is True
    pet["sparkle"] = raw.get("sparkle") is True
    return pet


clean_design = _clean


def _apply_palette(pet, palette):
    _, pet["body"], pet["belly"], pet["beak"], pet["cheek"] = palette


def _random_design(rng):
    pet = dict(DEFAULT_PET)
    pet["shape"] = rng.choice(SHAPES)
    palette = rng.choice(PALETTES)
    _apply_palette(pet, palette)
    pet["name"] = rng.choice((rng.choice(_NAMES[pet["shape"]]), f"{palette[0]} {pet['shape'].title()}"))
    pet["temperament"] = rng.choice(TEMPERAMENTS)
    pet["accessory"] = rng.choice(("none", "none", "bow", "hat", "crown", "glasses"))
    pet["size"] = round(rng.uniform(0.8, 1.3), 2)
    pet["speed"] = round(rng.uniform(0.65, 1.65), 2)
    pet["flap"] = rng.randint(3, 8)
    pet["bob"] = round(rng.uniform(0.3, 1.8), 2)
    pet["wander"] = round(rng.uniform(0.08, 0.45), 2)
    pet["trail"] = rng.random() < 0.25
    pet["sparkle"] = rng.random() < 0.3
    pet["sound"] = _SOUNDS[pet["shape"]]
    if pet["temperament"] == "calm":
        pet.update(speed=0.65, wander=0.08, bob=0.4)
    pet["personality"] = f"A {pet['temperament']} {pet['shape']} who {rng.choice(_HOBBIES[pet['temperament']])}."
    return pet


def random_pet():
    """Invent a pet using curated local palettes, names, accessories and moods."""
    return _clean(_random_design(random))


def _requested_effect(text, aliases, default=False):
    names = "|".join(re.escape(word) for word in aliases)
    if re.search(rf"\b(?:no|without|disable|remove)\s+(?:(?:a|any|the)\s+)?(?:{names})\b", text):
        return False
    return True if re.search(rf"\b(?:{names})\b", text) else default


def design_pet(idea=""):
    """Interpret a description with local keyword rules; no AI service is used.

    Recognizes species, colors, tiny/large, slow/fast, sleepy/playful/curious,
    trails, sparkles and the supported accessories. Unknown details contribute
    to the reproducible random seed, but do not create new drawable shapes.
    """
    if not isinstance(idea, str):
        raise TypeError("Describe your pet with text.")
    text = " ".join(idea.casefold().split())[:2000]
    if not text:
        return random_pet()
    rng = random.Random(int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest(), "big"))
    pet = _random_design(rng)
    words = re.findall(r"[a-z]+", text)
    species = next((word for word in words if word in _SPECIES), None)
    if species:
        pet["shape"] = _SPECIES[species]
    color = next((word for word in words if word in _COLORS), None)
    if color:
        palette = PALETTES[_COLORS[color]]
        _apply_palette(pet, palette)
        pet["name"] = f"{palette[0]} {(species or pet['shape']).title()}"
    else:
        pet["name"] = rng.choice(_NAMES[pet["shape"]])
    pet["sound"] = "hoot" if species == "owl" else _SOUNDS[pet["shape"]]
    tokens = set(words)
    if tokens & {"sleepy", "sleeping", "calm", "lazy", "gentle", "relaxed"}:
        pet.update(temperament="calm", speed=0.5, bob=0.25, wander=0.06, flap=9)
    elif tokens & {"playful", "bouncy", "energetic", "excited", "hyper"}:
        pet.update(temperament="playful", speed=1.6, bob=1.8, wander=0.4, flap=3)
    elif tokens & {"curious", "explorer", "inquisitive"}:
        pet.update(temperament="curious", wander=0.45)
    if tokens & {"slow", "sluggish"}:
        pet["speed"] = 0.5
    elif tokens & {"fast", "speedy", "quick", "zoomy"}:
        pet["speed"] = 1.9
    if tokens & {"tiny", "small", "mini", "miniature", "little"}:
        pet["size"] = 0.7
    elif tokens & {"big", "large", "giant", "huge"}:
        pet["size"] = 1.4
    pet["trail"] = _requested_effect(text, ("trail", "trails", "trailing", "comet"))
    pet["sparkle"] = _requested_effect(text, ("sparkle", "sparkles", "sparkly", "sparkling", "glitter", "twinkling"))
    pet["accessory"] = "none"
    for accessory in ACCESSORIES[1:]:
        if _requested_effect(text, (accessory,)):
            pet["accessory"] = accessory
            break
    if tokens & {"silent", "quiet", "mute", "soundless"} or re.search(r"\bno\s+sounds?\b", text):
        pet["sound"] = "none"
    pet["personality"] = f"A {pet['temperament']} {(species or pet['shape'])} who {rng.choice(_HOBBIES[pet['temperament']])}."
    return _clean(pet)


if __name__ == "__main__":
    import sys
    print(json.dumps(design_pet(" ".join(sys.argv[1:])), indent=2))
