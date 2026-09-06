from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class BudgetController:
    limits: dict[str, int]
    tool_calls: int = 0
    agent_turns: int = 0
    consecutive_failures: int = 0
    started_at: float = 0.0
    attempts: dict[tuple[str, str], int] | None = None

    def __post_init__(self):
        if not self.started_at:
            self.started_at = time.monotonic()
        if self.attempts is None:
            self.attempts = {}

    def allow_tool_call(self, tool: str = "", target: str = "") -> tuple[bool, str]:
        if self.tool_calls >= self.limits.get("max_total_tool_calls_per_session", 200):
            return False, "max_total_tool_calls_per_session reached"
        if time.monotonic() - self.started_at >= self.limits.get("max_wallclock_per_task_seconds", 900):
            return False, "max_wallclock_per_task_seconds reached"
        if self.tool_calls >= self.limits.get("max_tool_calls_per_task", 6):
            return False, "max_tool_calls_per_task reached"
        key = (tool, target)
        if self.attempts.get(key, 0) >= self.limits.get("max_same_tool_same_target_retries", 2):
            return False, f"max_same_tool_same_target_retries reached for {tool}/{target}"
        return True, ""

    def record_tool_call(self, success: bool, tool: str = "", target: str = "") -> None:
        self.tool_calls += 1
        key = (tool, target)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        self.consecutive_failures = 0 if success else self.consecutive_failures + 1

    def allow_agent_turn(self) -> tuple[bool, str]:
        if self.agent_turns >= self.limits.get("max_agent_turns_per_task", 10):
            return False, "max_agent_turns_per_task reached"
        if self.consecutive_failures >= self.limits.get("max_consecutive_failures_before_escalation", 3):
            return False, "consecutive failure escalation threshold reached"
        self.agent_turns += 1
        return True, ""
