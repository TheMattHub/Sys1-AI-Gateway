"""Anthropic adapter: a hosted Claude model (default Claude Haiku 5.5) as the engine, over HTTPS with urllib.

Contract (Messages API, `anthropic-version: 2023-06-01`):
  POST {endpoint}/v1/messages with one forced tool call `choose` whose input is
       {"ranking": [up to 3 option names, best first], "confidence": number in [0, 1]}
  GET  {endpoint}/v1/models/{model} for health.
The options go in a cached system block, so repeated questions over the same options pay for them once (the
naga bench's prompt, bench/naga/eng_anthropic.py). The API has no answer probabilities: `confidence` is the
model's own estimate, uncalibrated, and `probabilities` are left out, so a fitted temperature cannot apply.
The key comes from the ANTHROPIC_API_KEY environment variable only, never from the config file, and is never
logged or put in an error message. Every request leaves the machine and is billed per token.
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .base import MalformedResponse, ProviderError, System1Provider
from .http import is_loopback

DEFAULT_ENDPOINT = "https://api.anthropic.com"
DEFAULT_MODEL = "claude-haiku-5-5"
YES_NO = ["yes", "no"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect would resend x-api-key to wherever it points; refuse it, so the key only goes to `endpoint`."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect to {newurl!r} refused", headers, None)


class AnthropicProvider(System1Provider):
    name = "anthropic"

    def __init__(self, settings: dict):
        super().__init__(settings)
        self.endpoint = str(self.settings.get("endpoint", DEFAULT_ENDPOINT)).rstrip("/")
        parts = urlsplit(self.endpoint)
        # Plain http only to loopback (a local proxy or the tests' fake); the key must never cross a network in clear.
        if not parts.hostname or not (parts.scheme == "https" or (parts.scheme == "http" and is_loopback(parts.hostname))):
            raise ValueError(f"anthropic endpoint {self.endpoint!r} must be https (http only on loopback)")
        # Loopback is never proxied. For https a system proxy is kept on purpose: urllib tunnels https through it
        # with CONNECT, so TLS runs end to end with the API and the proxy never sees the key; without it the
        # provider would not work behind a corporate proxy.
        handlers = [_NoRedirect()] + ([urllib.request.ProxyHandler({})] if is_loopback(parts.hostname) else [])
        self._opener = urllib.request.build_opener(*handlers)
        self.model = str(self.settings.get("model", DEFAULT_MODEL)).strip()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("anthropic needs the ANTHROPIC_API_KEY environment variable")

    def _call(self, method: str, path: str, body, timeout_s: float) -> dict:
        headers = {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.endpoint + path, data=data, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=timeout_s) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read(300).decode("utf-8", "replace")  # the API explains errors; it never echoes the key
            e.close()
            raise ProviderError(f"Anthropic HTTP {e.code} {e.reason}: {detail}") from e
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError):
                raise TimeoutError(f"Anthropic did not answer within {timeout_s}s") from e
            raise ProviderError(f"Anthropic unreachable at {self.endpoint}: {e.reason}") from e
        try:
            return json.loads(raw)
        except ValueError as e:
            raise MalformedResponse(f"Anthropic returned non-JSON: {e}") from e

    def decide(self, request, timeout_s: float) -> dict:
        options = request.options or YES_NO
        tool = {"name": "choose", "description": "Give the best options, best first, and how sure you are.",
                "input_schema": {"type": "object", "required": ["ranking", "confidence"], "properties": {
                    "ranking": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string", "enum": options}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1,
                                   "description": "Probability that the first option is right."}}}}
        listing = "\n".join(f"- {o}" for o in options)
        ctx = request.context or {}
        text = ctx["task"] if set(ctx) == {"task"} and isinstance(ctx["task"], str) else json.dumps(ctx, ensure_ascii=False)
        body = {"model": self.model, "max_tokens": 200, "tools": [tool], "tool_choice": {"type": "tool", "name": "choose"},
                "system": [{"type": "text", "text": f"{request.question}\nOptions:\n{listing}",
                            "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": text or request.question}]}
        native = self._call("POST", "/v1/messages", body, timeout_s)
        use = next((b.get("input") for b in native.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_use"), None)
        ranking = [o for o in (use or {}).get("ranking") or [] if o in options]
        if not ranking:
            raise MalformedResponse("Anthropic response has no `choose` tool call with an option")
        return {"decision": ranking[0], "confidence": use.get("confidence"),
                "rationale": f"anthropic {self.model}: {', '.join(ranking)}"}

    def health(self, timeout_s: float) -> dict:
        native = self._call("GET", f"/v1/models/{self.model}", None, timeout_s)
        ok = bool(native.get("id"))  # an alias resolves to a dated id
        return {"ok": ok, "detail": f"{self.endpoint} model {self.model!r} {'available' if ok else 'not found'}"}

    def capabilities(self) -> dict:
        return {"name": self.name, "endpoint": self.endpoint, "contract": "Anthropic Messages API, forced tool call",
                "model": self.model, "supports_options": True, "hosted": True}
