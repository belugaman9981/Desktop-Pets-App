"""Start an installed local Acumen bridge without exposing its pairing token."""

import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

from acumen_client import AcumenClient, normalize_base_url


class LocalBridge:
    def __init__(self, storage_root=None):
        self.process = None
        self.client = None
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.stop_lock = threading.Lock()
        self.storage_root = Path(storage_root).resolve() if storage_root else None

    def start(self, base_url):
        base_url = normalize_base_url(base_url)
        parts = urlsplit(base_url)
        if parts.scheme != "http" or parts.hostname != "127.0.0.1":
            raise RuntimeError("Start Acumen uses http://127.0.0.1 with a local port. Use Connect for other loopback addresses.")
        if self.closed.is_set():
            raise RuntimeError("Desktop Pets is closing.")
        if self.process is not None and self.process.poll() is None:
            if self.client and self.client.base_url == base_url:
                self.client.check_connection()
                return self.client
            raise RuntimeError("Acumen is already starting or running here. Use its original address to reconnect.")
        port = parts.port or 80
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError("A server is already using this port. If it is Acumen, paste its pairing token and click Connect. Otherwise choose another port.")
        project = Path(os.environ.get("ACUMEN_HOME", str(Path(__file__).resolve().parent.parent / "AcumenAI-2.0")))
        if not (project / "acumen" / "bridge.py").is_file():
            raise RuntimeError("Could not find AcumenAI-2.0 beside Desktop Pets. Set ACUMEN_HOME to its folder, or start Acumen yourself and use Connect.")
        candidates = [project / folder / "Scripts" / "python.exe" for folder in (".worker-venv", ".venv", "venv")]
        interpreter = next((p for p in candidates if p.is_file()), Path(sys.executable))
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError("Desktop Pets is closing.")
            command = [str(interpreter), "-u", str(Path(__file__).resolve()), "--serve", str(project.resolve()), str(port)]
            if self.storage_root is not None:
                command.append(str(self.storage_root))
            self.process = subprocess.Popen(
                command,
                cwd=project, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            process = self.process
        output = queue.Queue()

        def read_output():
            try:
                for line in process.stdout:
                    # Never put server output, questions, or secrets in the app log.
                    if line.startswith("DESKTOP_PETS_TOKEN="):
                        output.put(line.partition("=")[2].strip())
            except (OSError, ValueError):
                pass  # Closing during startup also closes the output pipe.

        threading.Thread(target=read_output, daemon=True).start()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and not self.closed.is_set():
            try:
                token = output.get(timeout=0.1)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            client = AcumenClient(base_url, token)
            try:
                client.check_connection()
            except RuntimeError:
                self._stop_process(process)
                raise
            self.client = client
            return client
        self._stop_process(process)
        raise RuntimeError("Acumen could not start. Check its Python environment and config.yaml, or run its bridge.py manually to see the error.")

    def _stop_process(self, process):
        with self.stop_lock:
            self._stop_locked(process)

    @staticmethod
    def _stop_locked(process):
        if process.poll() is None:
            try:
                process.stdin.write("stop\n")
                process.stdin.flush()
                process.wait(timeout=5)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=3)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()

    def close(self):
        self.closed.set()
        with self.lock:
            process = self.process
        if process is not None:
            self._stop_process(process)


def _serve(project, port, storage_root=None):
    """Dedicated owned server; stdin closure gracefully releases its worker."""
    sys.path.insert(0, project)
    os.chdir(project)
    from acumen.config import load_config
    from acumen.bridge import make_app
    from werkzeug.serving import make_server

    cfg = load_config("config.yaml")
    root = Path(storage_root or cfg["storage"]["root"]).expanduser().resolve()
    app = make_app(root, cfg)
    server = make_server("127.0.0.1", int(port), app, threaded=True)

    def stop_on_input():
        sys.stdin.readline()
        server.shutdown()

    threading.Thread(target=stop_on_input, daemon=True).start()
    print("DESKTOP_PETS_TOKEN=" + app.config["ACUMEN_PAIRING_TOKEN"], flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.extensions["acumen_client"].local_processor.close()


if __name__ == "__main__" and len(sys.argv) in (4, 5) and sys.argv[1] == "--serve":
    _serve(*sys.argv[2:])
