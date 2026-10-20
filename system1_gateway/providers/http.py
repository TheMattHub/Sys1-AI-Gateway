"""HTTP plumbing shared by the local-engine adapters: loopback guard, no proxy, JSON in and out, typed errors."""

import ipaddress
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .base import MalformedResponse, ProviderError, as_bool


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalHTTP:
    def __init__(self, label: str, endpoint, allow_remote=False, api_key=""):
        self.label = label
        self.endpoint = str(endpoint).rstrip("/")
        parts = urlsplit(self.endpoint)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError(f"invalid {label.lower()} endpoint {self.endpoint!r}")
        local = is_loopback(parts.hostname)
        if not local and not as_bool(allow_remote):
            raise ValueError(f"{label.lower()} endpoint {self.endpoint!r} is not local; "
                             "set allow_remote = true to permit it")
        self.api_key = str(api_key or "").strip()
        # Local calls must never be routed through a system/corporate proxy.
        self._opener = urllib.request.build_opener(*([urllib.request.ProxyHandler({})] if local else []))

    def call(self, method: str, path: str, body, timeout_s: float) -> dict:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.endpoint + path, data=data, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read(300).decode("utf-8", "replace")  # engines explain 4xx errors in the body
            e.close()
            raise ProviderError(f"{self.label} HTTP {e.code} {e.reason}: {detail}") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise TimeoutError(f"{self.label} did not answer within {timeout_s}s") from e
            raise ProviderError(f"{self.label} unreachable at {self.endpoint}: {e.reason}") from e
        try:
            native = json.loads(raw)
        except ValueError as e:
            raise MalformedResponse(f"{self.label} returned non-JSON: {e}") from e
        if not isinstance(native, dict):
            raise MalformedResponse(f"{self.label} returned {type(native).__name__}, expected an object")
        return native
