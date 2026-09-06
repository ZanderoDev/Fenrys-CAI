from __future__ import annotations

from typing import Any

from fenrys.config import ConfigManager
from .anthropic_provider import AnthropicProvider
from .base import ModelProvider
from .openai_compatible_provider import OpenAICompatibleProvider
from .openai_provider import OpenAIProvider


class ProviderRegistry:
    def __init__(self, config: ConfigManager):
        self.config = config

    def names(self) -> list[str]:
        return sorted(self.config.load("providers.yaml").get("providers", {}))

    def build(self, name: str, model: str | None = None) -> ModelProvider:
        entry: dict[str, Any] = self.config.load("providers.yaml").get("providers", {}).get(name)
        if not entry:
            raise ValueError(f"unknown provider: {name}")
        provider_type = entry.get("type", "openai_compatible")
        if provider_type == "anthropic":
            return AnthropicProvider(entry, model)
        if provider_type == "openai":
            return OpenAIProvider(entry, model)
        if provider_type in {"openai_compatible", "custom"}:
            return OpenAICompatibleProvider(name, entry, model)
        raise ValueError(f"unsupported provider type: {provider_type}")
