from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from fenrys.agents.roster import AGENT_PROMPTS
from fenrys.config import ConfigManager
from fenrys.evidence import EvidenceManager
from fenrys.integrations import HexStrikeAdapter, HexStrikeManager
from fenrys.models import Message, TaskStatus
from fenrys.policy import BudgetController
from fenrys.providers import ProviderRouter
from fenrys.scope import ScopeChecker
from fenrys.state import StateStore
from fenrys.tool_registry import ToolRegistry
from fenrys.orchestrator import Orchestrator


@dataclass(slots=True)
class RuntimeResult:
    task_id: str
    provider: str
    model: str
    tool_calls: int
    summary: str
    blocked_reason: str | None = None


def _tool_call_parts(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    function = call.get("function") or {}
    name = call.get("name") or function.get("name") or ""
    arguments = call.get("arguments") or function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    return str(name), arguments if isinstance(arguments, dict) else {}


class InvestigationRuntime:
    """The connected execution loop: model -> scoped tool -> evidence -> state -> model."""

    def __init__(self, config: ConfigManager, store: StateStore):
        self.config = config
        self.store = store
        self._budgets: dict[str, BudgetController] = {}
        cfg = config.load("config.yaml")
        self.evidence = EvidenceManager(store, cfg["raw_output_dir"])
        manager = HexStrikeManager(
            cfg.get("hexstrike_install_dir"),
            cfg.get("hexstrike_python"),
        )
        mcp_command = manager.mcp_command(cfg["hexstrike_url"])
        self.adapter = HexStrikeAdapter(cfg["hexstrike_url"], self.evidence, mcp_command)
        self.router = ProviderRouter(config)
        self.scope = ScopeChecker(config.load("scope.yaml"))
        self.registry = ToolRegistry()

    def _budget_for_session(self, session_id: str) -> BudgetController:
        """Return the session's BudgetController, creating it on first use.

        Session-level counters (e.g. max_total_tool_calls_per_session)
        persist across every task in the session; task-level counters are
        reset via start_task() at the beginning of each task.
        """
        limits = self.config.load("policy.yaml").get("budgets", {})
        budget = self._budgets.get(session_id)
        if budget is None:
            budget = BudgetController(limits)
            self._budgets[session_id] = budget
        else:
            budget.limits = limits
        budget.start_task()
        return budget

    async def run_task(self, session_id: str, agent: str, objective: str,
                       task_id: str | None = None) -> RuntimeResult:
        session = self.store.get_session(session_id)
        if not session:
            raise KeyError(f"unknown session: {session_id}")
        task_id = task_id or self.store.add_task(session_id, agent, objective)
        self.store.update_task(task_id, TaskStatus.RUNNING)
        budget = self._budget_for_session(session_id)
        provider = self.router.for_agent(agent)
        registry_tools = await self.adapter.sync_registry()
        self.registry.sync(registry_tools)
        tool_specs = self.registry.profile_for(agent)
        target = session.get("target")
        messages = [
            Message("system", AGENT_PROMPTS.get(agent, AGENT_PROMPTS["orchestrator"])),
            Message("user", f"Objective: {objective}\nTarget: {target or 'local artifact only'}"),
        ]
        first = await provider.complete(messages, tool_specs, max_tokens=1200, temperature=0)
        tool_count = 0
        final_text = first.content
        if first.tool_calls:
            messages.append(Message("assistant", first.content, tool_calls=first.tool_calls))
        for raw_call in first.tool_calls:
            tool, arguments = _tool_call_parts(raw_call)
            if tool not in {spec.name for spec in tool_specs}:
                continue
            call_target = str(arguments.get("target") or target or "")
            allowed, reason = budget.allow_tool_call(tool, call_target)
            if not allowed:
                self.store.update_task(task_id, TaskStatus.BLOCKED, reason)
                return RuntimeResult(task_id, provider.name, provider.model, tool_count, final_text, reason)
            if call_target:
                self.scope.require_allowed(call_target)
            result = await self.adapter.invoke(tool, arguments, session_id)
            budget.record_tool_call(result.success, tool, call_target)
            tool_count += 1
            self.store.record_invocation(session_id, tool, {
                "success": result.success, "duration_ms": result.duration_ms,
                "summary": result.summary, "findings": result.findings,
                "raw_output_path": result.raw_output_path, "error": result.error,
            }, task_id, call_target or None)
            call_id = raw_call.get("id") or (raw_call.get("function") or {}).get("id")
            messages.append(Message("tool", self.evidence.wrap_untrusted(tool, result.summary),
                                    tool_call_id=call_id))
        if tool_count:
            follow_up = await provider.complete(messages, None, max_tokens=1000, temperature=0)
            final_text = follow_up.content or final_text
        self.store.update_state(session_id, {"last_agent": agent, "last_report": final_text,
                                             "last_task_id": task_id})
        self.store.update_task(task_id, TaskStatus.COMPLETED)
        return RuntimeResult(task_id, provider.name, provider.model, tool_count, final_text)

    async def run_investigation(self, session_id: str, objective: str) -> list[RuntimeResult]:
        """Plan, delegate, and execute the specialist queue until it is exhausted."""
        orchestrator = Orchestrator(self.store)
        task_ids = orchestrator.plan_investigation(session_id, objective)
        results: list[RuntimeResult] = []
        for task_id in task_ids:
            task = next(item for item in self.store.list_tasks(session_id) if item["id"] == task_id)
            try:
                results.append(await self.run_task(session_id, task["agent"], task["objective"], task_id))
            except PermissionError as exc:
                self.store.update_task(task_id, TaskStatus.BLOCKED, str(exc))
                results.append(RuntimeResult(task_id, "", "", 0, "", str(exc)))
        self.store.update_state(session_id, {
            "completed_tasks": [result.task_id for result in results],
            "next_actions": [],
        })
        return results