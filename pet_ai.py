#!/usr/bin/env python3
"""
DeepSeek-powered pet designer for Desktop Pets.

Asks the DeepSeek chat API to invent a pet and returns a plain dict that
desktop_pets.py knows how to draw. No third-party packages needed - this
uses only the standard library.

The API key is read from (in order):
  1. the DEEPSEEK_API_KEY environment variable
  2. %LOCALAPPDATA%\\Desktop Pets\\api_key.txt
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
TIMEOUT = 45

# Fields every pet must have, with safe fallbacks if the model misbehaves.
DEFAULT_PET = {
    "name": "Mystery Bird",
    "shape": "bird",
    "body": "#e23b3b",
    "belly": "#f6b8b8",
    "beak": "#ff9f1a",
    "cheek": "#ff8fa3",
    "eye": "#141414",
    "size": 1.0,
    "speed": 1.0,
    "flap": 4,
    "bob": 0.8,
    "wander": 0.25,
    "trail": False,
    "sparkle": False,
    "sound": "chirp",
    "personality": "A cheerful little bird who loves to explore.",
}

SHAPES = ("bird", "fish", "cat", "blob", "bug", "ghost")

SYSTEM_PROMPT = """You design tiny desktop pets for a Windows app.
Each pet is drawn from a fixed set of shapes, so you must pick one of
these "shape" values - you cannot invent new ones:

  "bird"  - round body, beak, flapping wing, tail feathers
  "fish"  - oval body, tail fin, side fin, no beak
  "cat"   - round head with two pointy ears, whiskers, small body
  "blob"  - soft rounded blob with big eyes, no limbs
  "bug"   - small round body, antennae, several little legs
  "ghost" - wavy-bottomed ghost with two arms, no legs

Pick the shape that best matches what the user asked for. If they ask
for something with no close match, choose the closest one.

Reply with ONLY a JSON object, no markdown, no commentary, using exactly
these keys:

{
  "name": "short pet name, max 20 characters",
  "shape": one of "bird", "fish", "cat", "blob", "bug", "ghost",
  "body": "#rrggbb main body colour",
  "belly": "#rrggbb lighter belly/wing/fin colour",
  "beak": "#rrggbb beak, nose or mouth colour",
  "cheek": "#rrggbb cheek colour",
  "eye": "#rrggbb eye colour",
  "size": 0.7 to 1.4, how big the pet is,
  "speed": 0.5 to 2.0, how fast it flies,
  "flap": 2 to 10, ticks between wing flaps (lower = faster flapping),
  "bob": 0.0 to 2.5, how much it bobs up and down,
  "wander": 0.05 to 0.6, how erratically it turns,
  "trail": true or false, leaves a fading trail behind it,
  "sparkle": true or false, twinkles as it flies,
  "sound": "chirp", "hoot", "beep" or "none",
  "personality": "one short sentence describing the pet"
}

Colours must be valid 6-digit hex and must NOT be #ff00ff (that colour is
transparent). Keep colours bright and readable on a desktop."""


def api_key_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Desktop Pets" / "api_key.txt"


def load_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        return api_key_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_api_key(key):
    path = api_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key.strip(), encoding="utf-8")
    return path


def _hex_or(value, fallback):
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 7 and text.startswith("#"):
            try:
                int(text[1:], 16)
            except ValueError:
                return fallback
            if text.lower() != "#ff00ff":
                return text.lower()
    return fallback


def _number(value, low, high, fallback):
    if type(value) in (int, float):
        return max(low, min(high, float(value)))
    return fallback


def _clean(raw):
    """Coerce whatever the model returned into a safe, complete pet dict."""
    pet = dict(DEFAULT_PET)
    if not isinstance(raw, dict):
        return pet

    name = raw.get("name")
    if isinstance(name, str) and name.strip():
        pet["name"] = name.strip()[:20]

    shape = raw.get("shape")
    if isinstance(shape, str) and shape.strip().lower() in SHAPES:
        pet["shape"] = shape.strip().lower()

    for field in ("body", "belly", "beak", "cheek", "eye"):
        pet[field] = _hex_or(raw.get(field), DEFAULT_PET[field])

    pet["size"] = _number(raw.get("size"), 0.7, 1.4, DEFAULT_PET["size"])
    pet["speed"] = _number(raw.get("speed"), 0.5, 2.0, DEFAULT_PET["speed"])
    pet["flap"] = int(_number(raw.get("flap"), 2, 10, DEFAULT_PET["flap"]))
    pet["bob"] = _number(raw.get("bob"), 0.0, 2.5, DEFAULT_PET["bob"])
    pet["wander"] = _number(raw.get("wander"), 0.05, 0.6, DEFAULT_PET["wander"])
    pet["trail"] = raw.get("trail") is True
    pet["sparkle"] = raw.get("sparkle") is True

    sound = raw.get("sound")
    pet["sound"] = sound if sound in ("chirp", "hoot", "beep", "none") else "chirp"

    personality = raw.get("personality")
    if isinstance(personality, str) and personality.strip():
        pet["personality"] = personality.strip()[:160]

    return pet


def _extract_json(text):
    """Pull the first JSON object out of a model reply."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("The model did not return JSON.")
    return json.loads(text[start:end + 1])


def design_pet(idea="", api_key=None, model=MODEL):
    """Ask DeepSeek for a pet. Returns a cleaned pet dict.

    Raises RuntimeError with a friendly message on any failure.
    """
    key = (api_key or load_api_key()).strip()
    if not key:
        raise RuntimeError(
            "No DeepSeek API key found.\n\n"
            "Get one at https://platform.deepseek.com/api_keys then either set the "
            "DEEPSEEK_API_KEY environment variable or paste it into the app."
        )

    prompt = idea.strip() or "Surprise me with something delightful."
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Design a desktop pet: {prompt}"},
        ],
        "temperature": 1.3,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except OSError:
            pass
        if exc.code == 401:
            raise RuntimeError("DeepSeek rejected the API key (401). Check the key and try again.") from exc
        if exc.code == 402:
            raise RuntimeError("DeepSeek says your account is out of credit (402).") from exc
        if exc.code == 429:
            raise RuntimeError("DeepSeek is rate limiting you (429). Wait a moment and retry.") from exc
        raise RuntimeError(f"DeepSeek error {exc.code}.\n{detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach DeepSeek. Check your internet connection.\n{exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError(f"The DeepSeek request timed out or failed.\n{exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("DeepSeek returned an unexpected response.") from exc

    try:
        return _clean(_extract_json(content))
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not understand the pet DeepSeek designed.\n{exc}") from exc


if __name__ == "__main__":
    import sys
    try:
        pet = design_pet(" ".join(sys.argv[1:]))
    except RuntimeError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    print(json.dumps(pet, indent=2))
