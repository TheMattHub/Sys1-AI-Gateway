"""The contract every provider adapter implements. The gateway only ever talks to this."""

from abc import ABC, abstractmethod


class ProviderError(Exception):
    """The provider failed: unreachable, HTTP error, crashed."""


class MalformedResponse(ProviderError):
    """The provider answered, but not in a shape we can trust."""


class System1Provider(ABC):
    """Adapter from the neutral DecideRequest to one engine's native API.

    Constructor raises ValueError for unusable settings (reported as config_error).
    decide() returns {"decision", "confidence", "rationale"} or {"abstain": True, "rationale"};
    the gateway validates that shape, so adapters just map native fields and let errors raise.
    Adapters must pass timeout_s down to their own I/O so abandoned calls still end.
    """

    name = ""

    def __init__(self, settings: dict):
        self.settings = dict(settings)

    @abstractmethod
    def decide(self, request, timeout_s: float) -> dict: ...

    @abstractmethod
    def health(self, timeout_s: float) -> dict:
        """Return {"ok": bool, "detail": str}, or raise."""

    def capabilities(self) -> dict:
        return {"name": self.name}


def as_bool(value) -> bool:
    """Settings may come from TOML (bool) or env vars (str)."""
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
