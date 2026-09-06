from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fenrys.models import Message, ModelResponse, TaskStatus, ToolSpec
from fenrys.policy import BudgetController
from fenrys.state import StateStore


@dataclass(slots=True)
class Orchestrator:
    store: StateStore
    budget: BudgetController

    def plan(self, session_id: str, objective: str, agent: str = "orchestrator") -> str:
        task_id = self.store.add_task(session_id, agent, objective)
        self.store.update_state(session_id, {"objective": objective, "next_actions": [task_id]})
        return task_id

    def plan_investigation(self, session_id: str, objective: str) -> list[str]:
        """Legacy deterministic workflow kept for explicit CLI compatibility.

        The normal TUI never uses this path; autonomous chats use run_agent_loop instead.
        """
        plan = [
            ("recon", f"Establish the attack surface for: {objective}"),
            ("web", f"Analyze promising application surfaces from: {objective}"),
        ]
        ids: list[str] = []
        previous: list[str] = []
        for agent, task in plan:
            tid = self.store.add_task(session_id, agent, task, dependencies=previous)
            ids.append(tid)
            previous = [tid]
        self.store.update_state(session_id, {"objective": objective, "plan": ids, "next_actions": ids})
        return ids

    async def run_agent_loop(
        self,
        provider: Any,
        messages: list[Message],
        tools: list[ToolSpec],
        tool_handler: Callable[[str, dict[str, Any]], Awaitable[tuple[str, bool]]],
        max_turns: int = 8,
        max_tokens: int = 1400,
    ) -> ModelResponse:
        """LLM/tool loop. The model decides whether to answer, call HexStrike, or delegate."""
        response = await provider.complete(messages, tools, max_tokens=max_tokens, temperature=0)
        for _ in range(max_turns):
            if not response.tool_calls:
                return response
            messages.append(Message("assistant", response.content, tool_calls=response.tool_calls))
            for raw_call in response.tool_calls:
                name, arguments = self._parts(raw_call)
                output, ok = await tool_handler(name, arguments)
                call_id = raw_call.get("id") or (raw_call.get("function") or {}).get("id")
                messages.append(Message("tool", output, tool_call_id=call_id))
            response = await provider.complete(messages, tools, max_tokens=max_tokens, temperature=0)
        return response

    @staticmethod
    def _parts(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        function = call.get("function") or {}
        name = str(call.get("name") or function.get("name") or "")
        arguments = call.get("arguments") or function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        return name, arguments if isinstance(arguments, dict) else {}

    def block_on_budget(self, task_id: str, reason: str) -> None:
        self.store.update_task(task_id, TaskStatus.BLOCKED, reason)

    async def _collect_stream(
        self,
        provider: Any,
        messages: list[Message],
        tools: list[ToolSpec],
        on_token: Callable[[str], Awaitable[None] | None] | None,
        max_tokens: int,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """Consume a full streaming response. Returns (content, tool_calls, usage)."""
        content = ""
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}

        async for chunk in provider.stream(messages, tools, max_tokens=max_tokens, temperature=0):
            if chunk.content:
                content += chunk.content
                if on_token:
                    maybe = on_token(chunk.content)
                    if maybe is not None:
                        await maybe
            if chunk.tool_calls:
                tool_calls = chunk.tool_calls
            if chunk.usage:
                usage = chunk.usage
            if chunk.finished:
                break

        return content, tool_calls, usage

    async def _dispatch_tool_calls(
        self,
        messages: list[Message],
        content: str,
        tool_calls: list[dict[str, Any]],
        tool_handler: Callable[[str, dict[str, Any]], Awaitable[tuple[str, bool]]],
        on_tool_start: Callable[[str, dict[str, Any]], Awaitable[None] | None] | None,
        on_tool_end: Callable[[str, Any], Awaitable[None] | None] | None,
    ) -> None:
        """Append assistant message with tool calls, dispatch each, append results."""
        messages.append(Message("assistant", content, tool_calls=tool_calls))
        for raw_call in tool_calls:
            name, arguments = self._parts(raw_call)
            if on_tool_start:
                maybe_start = on_tool_start(name, arguments)
                if maybe_start is not None:
                    await maybe_start
            output, ok = await tool_handler(name, arguments)
            call_id = raw_call.get("id") or (raw_call.get("function") or {}).get("id")
            messages.append(Message("tool", output, tool_call_id=call_id))
            if on_tool_end:
                maybe_end = on_tool_end(name, {"success": ok, "output": output})
                if maybe_end is not None:
                    await maybe_end

    async def run_agent_loop_streaming(
        self,
        provider: Any,
        messages: list[Message],
        tools: list[ToolSpec],
        tool_handler: Callable[[str, dict[str, Any]], Awaitable[tuple[str, bool]]],
        on_token: Callable[[str], Awaitable[None]] | None = None,
        on_tool_start: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
        on_tool_end: Callable[[str, Any], Awaitable[None]] | None = None,
        on_usage: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        max_turns: int = 8,
        max_tokens: int = 1400,
    ) -> ModelResponse:
        """Streaming LLM/tool loop. Streams tokens via on_token, dispatches tools, repeats."""
        last_usage: dict[str, Any] = {}

        for _ in range(max_turns):
            content, tool_calls, usage = await self._collect_stream(
                provider, messages, tools, on_token, max_tokens
            )
            if usage:
                last_usage = usage

            if not tool_calls:
                # No tool calls — response complete
                if on_usage and last_usage:
                    await on_usage(last_usage)
                return ModelResponse(content, provider.model, provider.name)

            # Dispatch tool calls and continue loop
            await self._dispatch_tool_calls(
                messages, content, tool_calls, tool_handler, on_tool_start, on_tool_end
            )

        # Exhausted max turns — return whatever we have
        if on_usage and last_usage:
            await on_usage(last_usage)
        return ModelResponse("", provider.model, provider.name)
