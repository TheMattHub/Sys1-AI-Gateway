"""Provider registry. Adding an adapter = one module + one line here; the MCP interface never changes."""

from .base import MalformedResponse, ProviderError, System1Provider
from .laya import LayaProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .von import VonProvider

REGISTRY: dict[str, type[System1Provider]] = {
    "laya": LayaProvider,
    "mock": MockProvider,
    "ollama": OllamaProvider,
    "von": VonProvider,
}

__all__ = ["REGISTRY", "MalformedResponse", "ProviderError", "System1Provider"]
