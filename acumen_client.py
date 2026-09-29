"""Small, local-only HTTP client for the AcumenAI bridge.

The bridge is a question-answering service, not a general JSON pet generator.
Questions are passed through unchanged so its commands and task router work.
Pairing tokens live only in this object's memory (or ACUMEN_TOKEN).
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT = 60.0
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class AcumenError(RuntimeError):
    """A displayable error that never contains a pairing token."""

    code = "acumen_error"


class AcumenConfigurationError(AcumenError):
    code = "configuration"


class AcumenPairingError(AcumenError):
    code = "pairing"


class AcumenConnectionError(AcumenError):
    code = "connection"


class AcumenTimeoutError(AcumenError):
    code = "timeout"


class AcumenResponseError(AcumenError):
    code = "response"


def normalize_base_url(value: str) -> str:
    """Validate an HTTP bridge root and restrict it to this computer.

    Canonicalizing localhost avoids DNS/proxy configuration sending a token to
    a different machine. Other hostnames, credentials, and API paths are refused.
    """
    message = "Use a local bridge URL such as http://127.0.0.1:8765."
    if not isinstance(value, str) or not value.strip():
        raise AcumenConfigurationError(message)
    value = value.strip()
    if any(character.isspace() or ord(character) < 32 for character in value):
        raise AcumenConfigurationError(message)
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname
        port = parsed.port
        if (parsed.scheme not in {"http", "https"} or not host
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
                or "?" in value or "#" in value or "%" in host
                or port == 0):
            raise ValueError
        if host.lower() == "localhost":
            host = "127.0.0.1"
        address = ipaddress.ip_address(host)
        if not address.is_loopback:
            raise ValueError
    except (ValueError, TypeError):
        raise AcumenConfigurationError(message) from None
    hostname = f"[{address.compressed}]" if address.version == 6 else str(address)
    return f"{parsed.scheme}://{hostname}" + (f":{port}" if port is not None else "")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def _sources_from_reply(reply: str) -> list[dict[str, str]]:
    """Read Acumen's source footer while preserving the full original reply."""
    _, separator, footer = reply.rpartition("\n\nSources:\n")
    if not separator:
        return []
    sources = []
    seen = set()
    for line in footer.splitlines():
        match = re.fullmatch(r"- (.+): (https?://\S+)", line.strip())
        if not match:
            continue
        title, url = match.groups()
        try:
            parsed = urllib.parse.urlsplit(url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname
                     and parsed.username is None and parsed.password is None)
        except ValueError:
            valid = False
        if valid and url not in seen:
            seen.add(url)
            sources.append({"title": title, "url": url})
    return sources


class AcumenClient:
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 timeout: float = DEFAULT_TIMEOUT):
        self.base_url = normalize_base_url(
            base_url if base_url is not None else os.environ.get("ACUMEN_BRIDGE_URL", DEFAULT_BASE_URL)
        )
        token = os.environ.get("ACUMEN_TOKEN", "") if token is None else token
        if not isinstance(token, str):
            raise AcumenConfigurationError("Paste the pairing token from the AcumenAI terminal.")
        token = token.strip()
        if any(ord(character) < 33 or ord(character) > 126 for character in token):
            raise AcumenConfigurationError("The pairing token contains invalid characters. Paste it again.")
        self.token = token
        if (isinstance(timeout, bool) or not isinstance(timeout, (float, int))
                or not math.isfinite(timeout) or not 0 < timeout <= 180):
            raise AcumenConfigurationError("The AcumenAI timeout must be between 0 and 180 seconds.")
        self.timeout = float(timeout)
        # Ignore environment/system HTTP proxies and never follow redirects with
        # the X-Acumen-Token header, even to another port on this computer.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())

    def _request(self, path: str, payload: dict | None = None, *,
                 authenticated: bool = True, timeout: float | None = None) -> dict:
        if authenticated and not self.token:
            raise AcumenPairingError("Paste the pairing token from the AcumenAI terminal, then connect.")
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["X-Acumen-Token"] = self.token
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if len(body) > MAX_REQUEST_BYTES:
                raise AcumenConfigurationError("This question is too long. Shorten it and try again.")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers,
                                         method="POST" if payload is not None else "GET")
        try:
            with self._opener.open(request, timeout=timeout or self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            if status in {401, 403}:
                raise AcumenPairingError(
                    "Pairing token not accepted. Paste the token from the current AcumenAI terminal and reconnect."
                ) from None
            if 300 <= status < 400:
                raise AcumenResponseError("The bridge redirected the request. Check the local bridge URL.") from None
            if status == 413:
                raise AcumenResponseError("This question is too long. Shorten it and try again.") from None
            if status == 429:
                raise AcumenResponseError("AcumenAI is busy. Wait a moment and retry.") from None
            raise AcumenResponseError(
                f"AcumenAI could not complete the request (HTTP {status}). Check its terminal and try again."
            ) from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise AcumenTimeoutError("AcumenAI took too long to reply. Wait a moment and retry.") from None
            raise AcumenConnectionError(
                "Could not reach AcumenAI. Start its local bridge and check the bridge URL."
            ) from None
        except (TimeoutError, socket.timeout):
            raise AcumenTimeoutError("AcumenAI took too long to reply. Wait a moment and retry.") from None
        except OSError:
            raise AcumenConnectionError("The AcumenAI connection was interrupted. Reconnect and try again.") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AcumenResponseError("AcumenAI returned an answer that is too large to display.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AcumenResponseError("AcumenAI returned an unreadable response. Check the bridge URL and retry.") from None
        if not isinstance(result, dict):
            raise AcumenResponseError("AcumenAI returned an unexpected response. Check the bridge URL and retry.")
        return result

    def health(self) -> dict:
        """Identify a running Acumen bridge without sending a pairing token."""
        result = self._request("/health", authenticated=False, timeout=min(self.timeout, 3))
        if result.get("ok") is not True or result.get("name") != "AcumenAI local bridge":
            raise AcumenResponseError("This local server does not identify itself as the AcumenAI bridge.")
        return result

    def check_connection(self) -> dict:
        """Verify the token and return the bridge's current session metadata."""
        result = self._request("/api/session", timeout=min(self.timeout, 8))
        if not isinstance(result.get("candidates"), list) or not isinstance(result.get("show_sources"), bool):
            raise AcumenResponseError("AcumenAI returned invalid session information. Check the bridge URL.")
        return result

    def ask(self, message: str) -> dict:
        if not isinstance(message, str) or not message.strip():
            raise AcumenConfigurationError("Type a question for AcumenAI first.")
        result = self._request("/api/chat", {"message": message})
        reply = result.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            raise AcumenResponseError("AcumenAI returned an empty or invalid answer. Try again.")
        return {"text": reply, "sources": _sources_from_reply(reply), "reply": reply}
