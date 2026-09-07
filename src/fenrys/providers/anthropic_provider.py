from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from fenrys.models import Message, ModelResponse, ModelStreamChunk, ProviderHealth, ToolSpec
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

    def _convert_messages(self, messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
        """Convert fenrys messages to Anthropic format. Returns (system, body_messages)."""
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
        return system, body_messages

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
        stream: bool = False,
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
        system, body_messages = self._convert_messages(messages)
        payload: dict[str, Any] = {"model": self.model, "messages": body_messages, "max_tokens": max_tokens}
        if system:
            # Prompt caching: system block is re-sent identically every agent turn,
            # so mark a cache breakpoint (behavior-identical, cheaper/faster on hits).
            payload["system"] = [{"type": "text", "text": system,
                                  "cache_control": {"type": "ephemeral"}}]
        if stream:
            payload["stream"] = True
        if temperature is not None:
            payload["temperature"] = temperature
        if tools:
            converted = []
            for t in tools:
                # Sumber utama: output_schema (registry hanya mengisi ini;
                # required_parameters selalu [] demi kompat API).
                schema = t.output_schema
                if schema:
                    if not isinstance(schema, dict) or schema.get("type") != "object":
                        schema = {"type": "object", "properties": {}, "additionalProperties": True}
                elif t.required_parameters:
                    schema = {"type": "object",
                              "properties": {p: {"type": "string"} for p in t.required_parameters},
                              "required": list(t.required_parameters)}
                else:
                    schema = {"type": "object", "properties": {}, "additionalProperties": True}
                converted.append({"name": t.name, "description": t.description,
                                  "input_schema": schema})
            # Second breakpoint: tool schemas are also stable across turns.
            converted[-1] = {**converted[-1], "cache_control": {"type": "ephemeral"}}
            payload["tools"] = converted
        return payload, system, body_messages

    async def complete(self, messages, tools=None, max_tokens=1024, temperature=None):
        payload, _, _ = self._build_payload(messages, tools, max_tokens, temperature, stream=False)
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        blocks = data.get("content", [])
        content = "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
        tool_calls = [
            {"id": block.get("id", ""), "name": block.get("name", ""),
             "arguments": block.get("input", {})}
            for block in blocks if block.get("type") == "tool_use"
        ]
        return ModelResponse(content, self.model, self.name, tool_calls, raw={"usage": data.get("usage")})

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        """Stream chat completion via Anthropic SSE. Yields content and tool call deltas."""
        if not self.api_key:
            raise RuntimeError("API key environment variable is not set: ANTHROPIC_API_KEY")

        payload, _, _ = self._build_payload(messages, tools, max_tokens, temperature, stream=True)

        # Anthropic streaming accumulates tool_use blocks by index
        tool_blocks: dict[int, dict[str, Any]] = {}
        current_text = ""

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, read=300.0)) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=self._headers(),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    event_type = event.get("type", "")

                    # Content block delta (text)
                    if event_type == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            text = delta.get("text", "")
                            if text:
                                current_text += text
                                yield ModelStreamChunk(content=text, finished=False)

                        # Tool use input delta
                        elif delta.get("type") == "input_json_delta":
                            idx = event.get("index", 0)
                            if idx not in tool_blocks:
                                tool_blocks[idx] = {"id": "", "name": "", "arguments": ""}
                            tool_blocks[idx]["arguments"] += delta.get("partial_json", "")

                    # Content block start (tool_use)
                    elif event_type == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            idx = event.get("index", 0)
                            tool_blocks[idx] = {
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "arguments": "",
                            }

                    # Message stop — done
                    elif event_type == "message_stop":
                        break

                    # Usage
                    elif event_type == "message_delta":
                        usage = event.get("usage", {})

        # Yield final assembled tool calls (toleran: argumen korup -> {}).
        assembled = []
        for tb in tool_blocks.values():
            if not tb["name"]:
                continue
            try:
                args = json.loads(tb["arguments"]) if tb["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            assembled.append({"id": tb.get("id", ""), "name": tb["name"], "arguments": args})
        yield ModelStreamChunk(content="", tool_calls=assembled, finished=True, usage=usage if "usage" in dir() else {})

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
