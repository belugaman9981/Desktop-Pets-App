import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from desktop_pets import App, MAX_PETS, load_settings


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "settings.json"
        self.path.write_text('{"count": 1}', encoding="utf-8")
        self.app = App(self.path)
        self.app.root.withdraw()
        self.app.toggle_hidden()
        self.errors = []
        self.app.root.report_callback_exception = lambda *args: self.errors.append(args)

    def tearDown(self):
        if not self.app.closed:
            self.app.quit_all()
        self.temporary.cleanup()
        self.assertEqual(self.errors, [])

    def pump(self, done, timeout=4):
        deadline = time.monotonic() + timeout
        while not done() and time.monotonic() < deadline:
            self.app.root.update()
            time.sleep(0.01)
        self.assertTrue(done(), "Background operation did not finish")

    def test_real_create_play_limit_and_settings_round_trip(self):
        app = self.app
        app.idea.set("sleepy purple cat with a crown")
        app.design_button.invoke()
        pet = app.pets[-1]
        self.assertEqual((pet.shape, pet.accessory), ("cat", "crown"))
        app.play("nap")
        self.assertTrue(all(p.action == "nap" for p in app.pets))
        before = pet.action_ticks
        app._loop()
        self.assertEqual(pet.action_ticks, before)  # Hidden pets freeze.
        while len(app.pets) < MAX_PETS:
            app.add_button.invoke()
        self.assertTrue(app.add_button.instate(["disabled"]))
        self.assertTrue(app.design_button.instate(["disabled"]))
        app.token.set("do-not-save-this-token")
        app.draft.insert("1.0", "unfinished question")
        app.save_settings()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["pets"]), MAX_PETS)
        self.assertEqual(data["draft"], "unfinished question")
        self.assertNotIn(app.token.get(), self.path.read_text(encoding="utf-8"))
        app.quit_all()
        self.app = App(self.path)
        self.app.root.withdraw()
        self.app.toggle_hidden()
        self.assertEqual([p.design for p in self.app.pets], data["pets"])
        self.assertEqual(self.app.draft.get("1.0", "end-1c"), "unfinished question")

    def test_slow_answer_keeps_new_draft_and_updates_only_on_ui_thread(self):
        app = self.app
        release = threading.Event()
        entered = threading.Event()
        def ask(question):
            self.assertEqual(question, "  Calculate 6*7  ")
            entered.set()
            release.wait(2)
            return {"text": "42"}
        with patch("desktop_pets.AcumenClient") as client:
            client.return_value.ask.side_effect = ask
            app.draft.insert("1.0", "  Calculate 6*7  ")
            app.send_button.invoke()
            self.pump(entered.is_set)
            self.assertTrue(app.busy)
            self.assertTrue(app.send_button.instate(["disabled"]))
            app.draft.delete("1.0", "end")
            app.draft.insert("1.0", "a new draft")
            release.set()
            self.pump(lambda: not app.busy)
        self.assertEqual(app.draft.get("1.0", "end-1c"), "a new draft")
        self.assertIn("42", app.transcript.get("1.0", "end-1c"))

    def test_failed_question_can_retry_without_losing_draft(self):
        app = self.app
        with patch("desktop_pets.AcumenClient") as client:
            client.return_value.ask.side_effect = [RuntimeError("Connection failed"), {"text": "42"}]
            app.draft.insert("1.0", "Calculate 6*7")
            app.send_button.invoke()
            self.pump(lambda: not app.busy)
            self.assertEqual(app.draft.get("1.0", "end-1c"), "Calculate 6*7")
            self.assertTrue(app.retry_button.instate(["!disabled"]))
            app.retry_button.invoke()
            self.pump(lambda: not app.busy)
            self.assertEqual(client.return_value.ask.call_count, 2)
            self.assertEqual(app.draft.get("1.0", "end-1c"), "")

    def test_close_during_request_does_not_call_destroyed_tk(self):
        app = self.app
        release = threading.Event()
        exited = threading.Event()
        def delayed():
            release.wait(2)
            exited.set()
            return {"text": "late answer"}
        app._launch_request("ask", delayed, "question")
        app.quit_all()
        release.set()
        self.assertTrue(exited.wait(2))
        self.assertTrue(app.closed)

    def test_invalid_persisted_values_fall_back_without_crashing(self):
        self.path.write_text(json.dumps({"speed": 10 ** 1000}), encoding="utf-8")
        self.assertEqual(load_settings(self.path)["speed"], 1.0)
        self.path.write_text(json.dumps({"count": 999, "speed": float("nan"),
            "pets": [None, {"shape": [], "body": "invalid"}], "acumen_url": "http://evil.example"}), encoding="utf-8")
        settings = load_settings(self.path)
        self.assertEqual(settings["count"], MAX_PETS)
        self.assertEqual(settings["speed"], 1.0)
        self.assertEqual(settings["acumen_url"], "http://127.0.0.1:8765")


if __name__ == "__main__":
    unittest.main()
