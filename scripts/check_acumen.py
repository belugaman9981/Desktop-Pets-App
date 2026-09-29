"""Exercise the actual Desktop Pets UI and installed Acumen with isolated data."""

import json
from pathlib import Path
import socket
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_pets import App
from acumen_bridge import LocalBridge


def settle(app, timeout=75):
    deadline = time.monotonic() + timeout
    while app.busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.02)
    if app.busy:
        raise AssertionError("The app request did not finish")


def main():
    with tempfile.TemporaryDirectory(prefix="desktop-pets-acumen-") as temporary:
        root = Path(temporary)
        config = root / "pets.json"
        config.write_text(json.dumps({"count": 1}), encoding="utf-8")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        app = App(config)
        app.root.withdraw()
        app.toggle_hidden()
        app.bridge = LocalBridge(storage_root=root / "knowledge")
        errors = []
        app.root.report_callback_exception = lambda *args: errors.append(args)
        try:
            app.acumen_url.set(f"http://127.0.0.1:{port}")
            app.start_button.invoke()
            settle(app)
            assert app.client is not None, app.ai_status.cget("text")
            assert app.client.health()["ok"]
            print("Owned Acumen start, health, and automatic pairing: OK")
            for question, expected in (("Calculate 6*7", "42"), ("Solve 2*x + 3 = 11", "x = 4")):
                app.draft.delete("1.0", "end")
                app.draft.insert("1.0", question)
                app.send_button.invoke()
                frame = app.frame
                settle(app)
                transcript = app.transcript.get("1.0", "end-1c")
                assert expected in transcript, transcript
                assert app.frame > frame, "UI loop stopped during request"
                assert not app.draft.get("1.0", "end-1c")
                print(f"Real question through Send button: {question} -> {expected}")
            app.token.set("wrong-token")
            app.connect_button.invoke()
            settle(app)
            assert "not accepted" in app.ai_status.cget("text")
            app.start_button.invoke()  # Reuse only the server this app owns.
            settle(app)
            assert app.client is not None
            print("Rejected token recovery: OK")
            app.save_settings()
            assert app.token.get() not in config.read_text(encoding="utf-8")
            assert not errors, errors
            process = app.bridge.process
        finally:
            app.quit_all()
        assert process.poll() == 0, "Owned server did not shut down cleanly"
        print("No token saved; owned bridge and worker shut down cleanly: OK")


if __name__ == "__main__":
    main()
