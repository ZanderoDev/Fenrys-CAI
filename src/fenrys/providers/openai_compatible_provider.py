from __future__ import annotations

import os
import time
from typing import Any

import httpx

from fenrys.models import Message, ModelResponse, ProviderHealth, ToolSpec
from .base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    supports_tools = True
    supports_streaming = True

    def __init__(self, name: str, config: dict[str, Any], model: str | None = None):
        self.name = name
        self.base_url = str(config.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or str(config.get("model", ""))
        self.api_key = os.environ.get(config.get("api_key_env", "")) if config.get("api_key_env") else None
        self.headers = {str(k): str(v) for k, v in (config.get("default_headers") or {}).items()}

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def complete(self, messages, tools=None, max_tokens=1024, temperature=None):
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    **{"role": m.role, "content": m.content},
                    **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {}),
                    **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
                }
                for m in messages
            ],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                "parameters": {"type": "object", "properties": {p: {"type": "string"} for p in t.required_parameters},
                              "required": t.required_parameters}}} for t in tools]
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return ModelResponse(
            content=str(message.get("content") or ""),
            model=self.model,
            provider=self.name,
            tool_calls=message.get("tool_calls") or [],
            raw={"id": data.get("id"), "usage": data.get("usage")},
        )

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
                response.raise_for_status()
            return ProviderHealth(True, self.name, round((time.perf_counter() - started) * 1000),
                                  self.supports_tools, "models endpoint reachable")
        except Exception as exc:
            return ProviderHealth(False, self.name, round((time.perf_counter() - started) * 1000),
                                  self.supports_tools, type(exc).__name__ + ": " + str(exc)[:180])
