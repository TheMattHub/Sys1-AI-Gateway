"""Provider registry. Adding an adapter = one module + one line here; the MCP interface never changes."""

from .anthropic import AnthropicProvider
from .base import MalformedResponse, ProviderError, System1Provider
from .laya import LayaProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .von import SystemOneProvider, VonProvider

REGISTRY: dict[str, type[System1Provider]] = {
    "anthropic": AnthropicProvider,
    "laya": LayaProvider,
    "mock": MockProvider,
    "ollama": OllamaProvider,
    "systemone": SystemOneProvider,
    "von": VonProvider,
}

__all__ = ["REGISTRY", "MalformedResponse", "ProviderError", "System1Provider"]
