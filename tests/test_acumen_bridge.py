import socket
import tempfile
import unittest
from unittest.mock import patch

from acumen_bridge import LocalBridge


class LocalBridgeTests(unittest.TestCase):
    def test_never_starts_over_an_existing_server_or_stops_it(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen()
            port = server.getsockname()[1]
            bridge = LocalBridge()
            with patch("acumen_bridge.subprocess.Popen") as start:
                with self.assertRaisesRegex(RuntimeError, "already using"):
                    bridge.start(f"http://127.0.0.1:{port}")
                bridge.close()
                start.assert_not_called()
                self.assertGreater(server.fileno(), -1)

    def test_closed_bridge_cannot_spawn_late_worker(self):
        bridge = LocalBridge()
        bridge.close()
        with patch("acumen_bridge.subprocess.Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "closing"):
                bridge.start("http://127.0.0.1:8765")
            start.assert_not_called()

    def test_missing_installation_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as empty, socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            bridge = LocalBridge()
            with patch.dict("os.environ", {"ACUMEN_HOME": empty}):
                with self.assertRaisesRegex(RuntimeError, "ACUMEN_HOME"):
                    bridge.start(f"http://127.0.0.1:{port}")
            self.assertIsNone(bridge.process)
            bridge.close()


if __name__ == "__main__":
    unittest.main()
