from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from fenrys.models import Message, ModelResponse, ModelStreamChunk, ProviderHealth, ToolSpec
from .base import ModelProvider


class OpenAICompatibleProvider(ModelProvider):
    supports_tools = True
    supports_streaming = True

    def __init__(self, name: str, config: dict[str, Any], model: str | None = None):
        self.name = name
        self.base_url = str(config.get("base_url", "https://api.openai.com/v1")).strip().rstrip("/")
        self.model = model or str(config.get("model", ""))
        self.api_key_env = str(config.get("api_key_env") or "")
        self.api_key = os.environ.get(self.api_key_env) if self.api_key_env else None
        self.headers = {
            str(k): str(v)
            for k, v in (config.get("default_headers") or {}).items()
            if v is not None
        }

    def _headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
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
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            converted = []
            for t in tools:
                schema = t.output_schema or {}
                if not isinstance(schema, dict) or schema.get("type") != "object":
                    schema = {"type": "object", "properties": {}, "additionalProperties": True}
                converted.append({
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": schema},
                })
            payload["tools"] = converted
            payload["tool_choice"] = "auto"
        return payload

    def _convert_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        return [
            {
                **{"role": m.role, "content": m.content},
                **({"tool_call_id": m.tool_call_id} if m.tool_call_id else {}),
                **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
            }
            for m in messages
        ]

    async def complete(self, messages, tools=None, max_tokens=1024, temperature=None):
        if self.api_key_env and not self.api_key:
            raise RuntimeError(f"API key environment variable is not set: {self.api_key_env}")
        if not self.model:
            raise ValueError(f"model is required for provider {self.name}")
        payload = self._build_payload(messages, tools, max_tokens, temperature, stream=False)
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

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        """Stream chat completion via SSE. Yields content deltas and tool call deltas."""
        if self.api_key_env and not self.api_key:
            raise RuntimeError(f"API key environment variable is not set: {self.api_key_env}")
        if not self.model:
            raise ValueError(f"model is required for provider {self.name}")

        payload = self._build_payload(messages, tools, max_tokens, temperature, stream=True)

        tool_calls_acc: dict[int, dict[str, Any]] = {}
        accumulated_content = ""

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, read=300.0)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}

                    # Content delta
                    content = delta.get("content")
                    if content:
                        accumulated_content += content
                        yield ModelStreamChunk(content=content, finished=False)

                    # Tool call deltas
                    for tc_delta in delta.get("tool_calls") or []:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        entry = tool_calls_acc[idx]
                        if tc_delta.get("id"):
                            entry["id"] = tc_delta["id"]
                        fn = tc_delta.get("function", {})
                        if fn.get("name"):
                            entry["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            entry["function"]["arguments"] += fn["arguments"]

                    # Usage info (from stream_options)
                    usage = chunk.get("usage") or {}

                # Final chunk with assembled tool calls
                assembled = list(tool_calls_acc.values())
                yield ModelStreamChunk(
                    content="",
                    tool_calls=assembled,
                    finished=True,
                    usage=usage,
                )

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        if self.api_key_env and not self.api_key:
            return ProviderHealth(
                False,
                self.name,
                reason=f"API key environment variable is not set: {self.api_key_env}",
            )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
                response.raise_for_status()
            return ProviderHealth(True, self.name, round((time.perf_counter() - started) * 1000),
                                  self.supports_tools, "models endpoint reachable")
        except Exception as exc:
            return ProviderHealth(False, self.name, round((time.perf_counter() - started) * 1000),
                                  self.supports_tools, type(exc).__name__ + ": " + str(exc)[:180])
