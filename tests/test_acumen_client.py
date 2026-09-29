"""HTTP contract and pairing protections, using only local test servers."""

import json
import os
import socket
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from acumen_client import (
    AcumenClient, AcumenConfigurationError, AcumenConnectionError,
    AcumenPairingError, AcumenResponseError, AcumenTimeoutError,
    MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, normalize_base_url,
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.respond()

    def do_POST(self):
        self.respond()

    def respond(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append({"path": self.path, "method": self.command,
                                     "token": self.headers.get("X-Acumen-Token"), "body": data})
        if self.server.override is not None:
            status, payload, headers = self.server.override
        elif self.path == "/health":
            status, payload, headers = 200, {"ok": True, "name": "AcumenAI local bridge"}, {}
        elif self.headers.get("X-Acumen-Token") != "test-token":
            status, payload, headers = 401, {"error": "bad pairing token"}, {}
        elif self.path == "/api/session":
            status, payload, headers = 200, {"candidates": [], "show_sources": True}, {}
        else:
            status, payload, headers = 200, {"reply": self.server.reply}, {}
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class AcumenClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.server.override = None
        self.server.requests = []
        self.server.reply = "42"
        self.client = AcumenClient(self.url, "test-token")

    def test_session_uses_authentication_and_real_contract(self):
        self.assertEqual(self.client.check_connection(), {"candidates": [], "show_sources": True})
        self.assertEqual(self.server.requests[0]["method"], "GET")
        self.assertEqual(self.server.requests[0]["token"], "test-token")

    def test_health_does_not_send_token(self):
        self.assertTrue(self.client.health()["ok"])
        self.assertIsNone(self.server.requests[0]["token"])

    def test_questions_pass_through_unchanged(self):
        question = "  Solve 2*x + 3 = 11\nKeep café spelling.  "
        self.assertEqual(self.client.ask(question)["text"], "42")
        self.assertEqual(json.loads(self.server.requests[0]["body"]), {"message": question})
        self.assertEqual(self.server.requests[0]["path"], "/api/chat")
        self.assertEqual(self.server.requests[0]["method"], "POST")

    def test_sources_are_kept_in_text_and_extracted(self):
        self.server.reply = ("An answer.\n\nSources:\n"
                             "- A: useful page: https://example.com/a\n"
                             "- Duplicate: https://example.com/a\n"
                             "- Local file: file:///private.txt\n"
                             "- Credentials: https://secret@example.com/b\n"
                             "- Second page: http://example.org/b")
        result = self.client.ask("research a thing")
        self.assertEqual(result["text"], self.server.reply)
        self.assertEqual(result["sources"], [
            {"title": "A: useful page", "url": "https://example.com/a"},
            {"title": "Second page", "url": "http://example.org/b"},
        ])

    def test_rejected_token_has_typed_friendly_error(self):
        with self.assertRaisesRegex(AcumenPairingError, "current AcumenAI terminal"):
            AcumenClient(self.url, "wrong-secret-token").check_connection()

    def test_missing_token_and_empty_question_make_no_requests(self):
        with self.assertRaises(AcumenPairingError):
            AcumenClient(self.url, "").ask("hello")
        for message in ("", " \n ", None, 42):
            with self.subTest(message=message), self.assertRaises(AcumenConfigurationError):
                self.client.ask(message)
        self.assertEqual(self.server.requests, [])

    def test_oversized_utf8_question_is_rejected_before_request(self):
        with self.assertRaisesRegex(AcumenConfigurationError, "too long"):
            self.client.ask("猫" * (MAX_REQUEST_BYTES // 2))
        self.assertEqual(self.server.requests, [])

    def test_invalid_json_and_reply_shapes(self):
        for payload in (b"<html>wrong server</html>", b"\xff", [], {"reply": None}, {"reply": "  "}):
            with self.subTest(payload=payload):
                self.server.override = 200, payload, {}
                with self.assertRaises(AcumenResponseError):
                    self.client.ask("hello")

    def test_invalid_session_and_health(self):
        self.server.override = 200, {"ok": True}, {}
        with self.assertRaises(AcumenResponseError):
            self.client.check_connection()
        with self.assertRaises(AcumenResponseError):
            self.client.health()

    def test_large_response_is_bounded(self):
        self.server.override = 200, b"x" * (MAX_RESPONSE_BYTES + 1), {}
        with self.assertRaisesRegex(AcumenResponseError, "too large"):
            self.client.ask("hello")

    def test_server_errors_are_friendly_and_do_not_reflect_secrets(self):
        for status in (400, 413, 429, 500, 503):
            with self.subTest(status=status):
                self.server.override = status, {"error": "test-token internal exception"}, {}
                with self.assertRaises(AcumenResponseError) as raised:
                    self.client.ask("hello")
                self.assertNotIn("test-token", str(raised.exception))
                self.assertNotIn("internal exception", str(raised.exception))

    def test_redirects_are_not_followed(self):
        self.server.override = 302, {}, {"Location": self.url + "/capture-token"}
        with self.assertRaisesRegex(AcumenResponseError, "redirected"):
            self.client.check_connection()
        self.assertEqual(len(self.server.requests), 1)
        self.assertEqual(self.server.requests[0]["path"], "/api/session")

    def test_environment_proxies_cannot_capture_requests(self):
        with patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "http_proxy": "http://127.0.0.1:1",
                                     "NO_PROXY": "", "no_proxy": ""}):
            self.assertEqual(AcumenClient(self.url, "test-token").ask("hello")["text"], "42")

    def test_timeout_is_finite_and_typed(self):
        for error in (TimeoutError(), urllib.error.URLError(socket.timeout())):
            with self.subTest(error=type(error)), patch.object(self.client._opener, "open", side_effect=error) as opened:
                with self.assertRaises(AcumenTimeoutError):
                    self.client.ask("hello")
                self.assertEqual(opened.call_args.kwargs["timeout"], 60)

    def test_health_and_pairing_use_shorter_timeouts(self):
        with patch.object(self.client._opener, "open", side_effect=TimeoutError()) as opened:
            with self.assertRaises(AcumenTimeoutError):
                self.client.health()
            self.assertEqual(opened.call_args.kwargs["timeout"], 3)
            with self.assertRaises(AcumenTimeoutError):
                self.client.check_connection()
            self.assertEqual(opened.call_args.kwargs["timeout"], 8)

    def test_disconnected_server_has_typed_error(self):
        error = urllib.error.URLError(ConnectionRefusedError("connection refused"))
        with patch.object(self.client._opener, "open", side_effect=error):
            with self.assertRaises(AcumenConnectionError):
                self.client.check_connection()


class AcumenConfigurationTests(unittest.TestCase):
    def test_only_loopback_roots_are_accepted(self):
        expected = {
            "http://localhost:8765/": "http://127.0.0.1:8765",
            " http://127.0.0.1:8888 ": "http://127.0.0.1:8888",
            "https://[::1]:8765/": "https://[::1]:8765",
        }
        for value, normalized in expected.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_base_url(value), normalized)
        for value in ("http://example.com", "http://192.168.1.5:8765", "http://localhost.evil.test", "file:///tmp/test",
                      "http://user:secret@127.0.0.1", "http://127.0.0.1/api", "http://127.0.0.1?secret=x",
                      "http://127.0.0.1#x", "http://127.0.0.1:0", "http://127.0.0.1:99999",
                      "http://[::ffff:192.168.1.1]", "http://[::1%zone]", "http://local\nhost", "", None):
            with self.subTest(value=value), self.assertRaises(AcumenConfigurationError):
                normalize_base_url(value)

    def test_environment_defaults_and_explicit_values(self):
        with patch.dict(os.environ, {"ACUMEN_BRIDGE_URL": "http://localhost:8888", "ACUMEN_TOKEN": "env-token"}):
            client = AcumenClient()
            self.assertEqual(client.base_url, "http://127.0.0.1:8888")
            self.assertEqual(client.token, "env-token")
            explicit = AcumenClient("http://127.0.0.1:8765", "")
            self.assertEqual(explicit.token, "")

    def test_header_injection_and_unbounded_timeouts_are_rejected(self):
        for token in ("abc\r\nX-Injected: yes", "a b", "猫"):
            with self.subTest(token=token), self.assertRaises(AcumenConfigurationError):
                AcumenClient(token=token)
        for timeout in (0, -1, float("inf"), float("nan"), 181, None, True):
            with self.subTest(timeout=timeout), self.assertRaises(AcumenConfigurationError):
                AcumenClient(timeout=timeout)


if __name__ == "__main__":
    unittest.main()
