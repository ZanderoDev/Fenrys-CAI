from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from fenrys.models import Message, ModelResponse, ModelStreamChunk, ProviderHealth, ToolSpec


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

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        """Streaming variant of complete(). Yields partial content and tool call deltas.

        Default implementation falls back to complete() for providers without native streaming.
        """
        response = await self.complete(messages, tools, max_tokens, temperature)
        yield ModelStreamChunk(content=response.content, tool_calls=response.tool_calls, finished=True)

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        raise NotImplementedError
