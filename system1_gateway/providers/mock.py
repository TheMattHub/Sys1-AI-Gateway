"""Deterministic provider for tests and for trying the gateway without a real engine.

Settings: confidence (default 0.9), delay_s (sleep before answering), fail (raise ProviderError
with this message), response (returned verbatim -- for malformed-response tests).
"""

import time

from .base import ProviderError, System1Provider


class MockProvider(System1Provider):
    name = "mock"

    def decide(self, request, timeout_s: float) -> dict:
        delay = float(self.settings.get("delay_s", 0))
        if delay:
            time.sleep(delay)
        if self.settings.get("fail"):
            raise ProviderError(str(self.settings["fail"]))
        if "response" in self.settings:
            return self.settings["response"]
        options = request.options or ["yes", "no"]
        confidence = float(self.settings.get("confidence", 0.9))
        rest = (1 - confidence) / (len(options) - 1)
        return {
            "decision": options[0],
            "confidence": confidence,
            "probabilities": {o: confidence if i == 0 else rest for i, o in enumerate(options)},
            "rationale": "mock provider: always picks the first option",
        }

    def health(self, timeout_s: float) -> dict:
        return {"ok": True, "detail": "mock provider (always healthy)"}

    def capabilities(self) -> dict:
        caps = {"name": self.name, "deterministic": True}
        if "max_options" in self.settings:
            caps["max_options"] = int(self.settings["max_options"])
        return caps
