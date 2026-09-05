from __future__ import annotations

import os
import time
from typing import Any

import httpx

from fenrys.models import Message, ModelResponse, ProviderHealth, ToolSpec
from .base import ModelProvider


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    supports_tools = True
    supports_streaming = True

    def __init__(self, config: dict[str, Any], model: str | None = None):
        self.model = model or "claude-sonnet-5"
        self.api_key = os.environ.get(config.get("api_key_env", "ANTHROPIC_API_KEY"))

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01", "content-type": "application/json"}

    async def complete(self, messages, tools=None, max_tokens=1024, temperature=None):
        system = "\n".join(m.content for m in messages if m.role == "system")
        body_messages = []
        for message in messages:
            if message.role == "system":
                continue
            if message.role == "assistant" and message.tool_calls:
                body_messages.append({"role": "assistant", "content": [
                    {"type": "tool_use", "id": call.get("id", "tool-call"),
                     "name": (call.get("function") or {}).get("name", call.get("name", "")),
                     "input": (call.get("function") or {}).get("arguments", call.get("arguments", {}))}
                    for call in message.tool_calls
                ]})
            elif message.role == "tool":
                body_messages.append({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": message.tool_call_id or "tool-call",
                     "content": message.content}
                ]})
            else:
                body_messages.append({"role": message.role, "content": message.content})
        payload: dict[str, Any] = {"model": self.model, "messages": body_messages, "max_tokens": max_tokens}
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [{"name": t.name, "description": t.description,
                "input_schema": {"type": "object", "properties": {p: {"type": "string"} for p in t.required_parameters},
                                 "required": t.required_parameters}} for t in tools]
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        blocks = data.get("content", [])
        content = "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        tool_calls = [
            {"name": block.get("name", ""), "arguments": block.get("input", {})}
            for block in blocks if block.get("type") == "tool_use"
        ]
        return ModelResponse(content, self.model, self.name, tool_calls, raw={"usage": data.get("usage")})

    async def health_check(self):
        if not self.api_key:
            return ProviderHealth(False, self.name, reason="API key environment variable is not set")
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json={"model": self.model, "max_tokens": 1, "messages": [{"role": "user", "content": "ping"}]},
                    headers=self._headers(),
                )
                if response.status_code >= 400:
                    return ProviderHealth(False, self.name, round((time.perf_counter() - started) * 1000),
                                          self.supports_tools, f"HTTP {response.status_code}")
            return ProviderHealth(True, self.name, round((time.perf_counter() - started) * 1000),
                                  self.supports_tools, "minimal request accepted")
        except Exception as exc:
            return ProviderHealth(False, self.name, round((time.perf_counter() - started) * 1000),
                                  self.supports_tools, type(exc).__name__ + ": " + str(exc)[:180])
