from __future__ import annotations

from abc import ABC, abstractmethod

from fenrys.models import Message, ModelResponse, ProviderHealth, ToolSpec


class ModelProvider(ABC):
    name: str
    supports_tools: bool = False
    supports_streaming: bool = False
    max_context_tokens: int = 128_000

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> ModelResponse:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        raise NotImplementedError
