from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fenrys.models import (
    Message, ModelResponse, TaskStatus, ToolSpec, TURN_EXHAUSTED_MARKER, parse_tool_call,
)
from fenrys.policy import BudgetController
from fenrys.state import StateStore

# finish_reason values meaning "cut off by token limit — not a real stop".
TRUNCATED_REASONS = frozenset({"length", "max_tokens"})
CONTINUE_AFTER_TRUNCATION = (
    "Outputmu terpotong batas token. Lanjutkan tepat dari titik terpotong, "
    "tanpa mengulang dari awal."
)
# Empty content + no tools = stalled turn, not an answer. Nudge, bounded.
EMPTY_NUDGE = (
    "Respon kosong tidak bisa diterima. Panggil tool/delegasi ATAU tulis "
    "jawaban final sekarang — jangan berhenti diam."
)
_MAX_EMPTY_RETRIES = 2


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
        response: ModelResponse | None = None
        empty_retries = 0
        for _ in range(max_turns):
            allowed, reason = self.budget.allow_agent_turn()
            if not allowed:
                # Gate di TOP loop: tidak ada pemakaian provider sebelum cek
                # budget (konsisten dengan varian streaming). Pertahankan konten
                # terakhir bila ada agar model tidak kehilangan konteks blok.
                prior = response.content if response and response.content else ""
                content = ((prior + f"\n[dihentikan: {reason}]").strip()
                           if prior else f"[dihentikan: {reason}]")
                if response is not None:
                    return ModelResponse(content, response.model, response.provider,
                                         response.tool_calls, response.raw)
                return ModelResponse(content, provider.model, provider.name)
            if response is None:
                response = await self._complete_with_retry(provider, messages, tools, max_tokens)
            if not response.tool_calls:
                if response.finish_reason in TRUNCATED_REASONS:
                    messages.append(Message("assistant", response.content))
                    messages.append(Message("user", CONTINUE_AFTER_TRUNCATION))
                    response = None
                    continue
                if not (response.content or "").strip() and empty_retries < _MAX_EMPTY_RETRIES:
                    empty_retries += 1
                    messages.append(Message("assistant", response.content))
                    messages.append(Message("user", EMPTY_NUDGE))
                    response = None
                    continue
                return response
            messages.append(Message("assistant", response.content, tool_calls=response.tool_calls))
            dispatches = [self._dispatch_one(tool_handler, raw_call)
                          for raw_call in response.tool_calls]
            for output, ok, call_id in await asyncio.gather(*dispatches):
                messages.append(Message("tool", output, tool_call_id=call_id))
            response = None
        content = ((response.content or "") + f"\n{TURN_EXHAUSTED_MARKER}").strip() \
            if response is not None else TURN_EXHAUSTED_MARKER
        if response is not None:
            return ModelResponse(content, response.model, response.provider,
                                 response.tool_calls, response.raw)
        return ModelResponse(content, provider.model, provider.name)

    async def _complete_with_retry(self, provider: Any, messages: list[Message], tools: list[ToolSpec], max_tokens: int) -> ModelResponse:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return await provider.complete(messages, tools, max_tokens=max_tokens, temperature=0)
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    await asyncio.sleep(1)
        assert last_error is not None
        raise last_error

    @staticmethod
    async def _dispatch_one(tool_handler, raw_call: dict[str, Any]) -> tuple[str, bool, Any]:
        """Run one tool call; isolate failures so sibling calls and loop survive."""
        name, arguments = parse_tool_call(raw_call)
        try:
            output, ok = await tool_handler(name, arguments)
        except Exception as exc:
            output, ok = f"tool {name} failed: {type(exc).__name__}: {str(exc)[:300]}", False
        call_id = raw_call.get("id") or (raw_call.get("function") or {}).get("id")
        return output, ok, call_id

    async def _collect_stream(
        self,
        provider: Any,
        messages: list[Message],
        tools: list[ToolSpec],
        on_token: Callable[[str], Awaitable[None] | None] | None,
        max_tokens: int,
        on_reasoning: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any], str]:
        """Consume a full streaming response. Returns (content, tool_calls, usage, finish_reason)."""
        content = ""
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, Any] = {}
        finish_reason = ""

        async for chunk in provider.stream(messages, tools, max_tokens=max_tokens, temperature=0):
            if chunk.content:
                content += chunk.content
                if on_token:
                    try:
                        maybe = on_token(chunk.content)
                        if maybe is not None:
                            await maybe
                    except Exception:
                        pass  # callback UI tidak boleh menggugurkan turn
            if chunk.reasoning and on_reasoning:
                try:
                    maybe_r = on_reasoning(chunk.reasoning)
                    if maybe_r is not None:
                        await maybe_r
                except Exception:
                    pass
            if chunk.tool_calls:
                tool_calls = chunk.tool_calls
            if chunk.finish_reason:
                finish_reason = chunk.finish_reason
            if chunk.usage:
                usage = chunk.usage
            if chunk.finished:
                break

        return content, tool_calls, usage, finish_reason

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

        async def one(raw_call: dict[str, Any]) -> tuple[str, Any]:
            name, arguments = parse_tool_call(raw_call)
            if on_tool_start:
                try:
                    maybe_start = on_tool_start(name, arguments)
                    if maybe_start is not None:
                        await maybe_start
                except Exception:
                    pass  # callback UI tidak boleh menggugurkan turn
            try:
                output, ok = await tool_handler(name, arguments)
            except Exception as exc:
                output, ok = f"tool {name} failed: {type(exc).__name__}: {str(exc)[:300]}", False
            call_id = raw_call.get("id") or (raw_call.get("function") or {}).get("id")
            if on_tool_end:
                try:
                    maybe_end = on_tool_end(name, {"success": ok, "output": output})
                    if maybe_end is not None:
                        await maybe_end
                except Exception:
                    pass  # callback UI tidak boleh menggugurkan turn
            return output, call_id

        for output, call_id in await asyncio.gather(
                *(one(raw_call) for raw_call in tool_calls)):
            messages.append(Message("tool", output, tool_call_id=call_id))

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
        on_reasoning: Callable[[str], Awaitable[None] | None] | None = None,
        max_turns: int = 8,
        max_tokens: int = 1400,
    ) -> ModelResponse:
        """Streaming LLM/tool loop. Streams tokens via on_token, dispatches tools, repeats."""
        last_usage: dict[str, Any] = {}
        empty_retries = 0

        async def _emit_usage() -> None:
            if on_usage and last_usage:
                try:
                    maybe = on_usage(last_usage)
                    if maybe is not None:
                        await maybe
                except Exception:
                    pass  # callback UI tidak boleh menggugurkan turn

        for _ in range(max_turns):
            allowed, reason = self.budget.allow_agent_turn()
            if not allowed:
                await _emit_usage()
                return ModelResponse(f"[dihentikan: {reason}]", provider.model, provider.name)
            content, tool_calls, usage, finish_reason = await self._collect_stream(
                provider, messages, tools, on_token, max_tokens, on_reasoning
            )
            if usage:
                last_usage = usage

            if not tool_calls:
                if finish_reason in TRUNCATED_REASONS:
                    messages.append(Message("assistant", content))
                    messages.append(Message("user", CONTINUE_AFTER_TRUNCATION))
                    continue
                if not (content or "").strip() and empty_retries < _MAX_EMPTY_RETRIES:
                    empty_retries += 1
                    messages.append(Message("assistant", content))
                    messages.append(Message("user", EMPTY_NUDGE))
                    continue
                # No tool calls — response complete
                await _emit_usage()
                return ModelResponse(content, provider.model, provider.name)

            # Dispatch tool calls and continue loop
            await self._dispatch_tool_calls(
                messages, content, tool_calls, tool_handler, on_tool_start, on_tool_end
            )

        # Exhausted max turns — say so explicitly instead of an empty "Done."
        await _emit_usage()
        return ModelResponse(TURN_EXHAUSTED_MARKER, provider.model, provider.name)
