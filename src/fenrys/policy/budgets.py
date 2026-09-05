from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class BudgetController:
    """Tracks budget usage for one investigation session.

    Session-level counters (``session_tool_calls``) persist across every task
    run in the session. Task-level counters (``task_tool_calls``,
    ``agent_turns``, ``consecutive_failures``, ``attempts``) are reset by
    calling :meth:`start_task` at the beginning of each task, so
    ``max_tool_calls_per_task`` and ``max_agent_turns_per_task`` are enforced
    per task while ``max_total_tool_calls_per_session`` and
    ``max_wallclock_per_task_seconds`` are enforced across the whole session
    (or per task, for wallclock) as documented in policy.example.yaml.
    """

    limits: dict[str, int]
    session_tool_calls: int = 0
    task_tool_calls: int = 0
    agent_turns: int = 0
    consecutive_failures: int = 0
    task_started_at: float = 0.0
    attempts: dict[tuple[str, str], int] = field(default_factory=dict)

    def __post_init__(self):
        if not self.task_started_at:
            self.task_started_at = time.monotonic()

    def start_task(self) -> None:
        """Reset per-task counters. Call once at the start of each task.

        Session-level counters (``session_tool_calls``) are intentionally
        left untouched.
        """
        self.task_tool_calls = 0
        self.agent_turns = 0
        self.consecutive_failures = 0
        self.attempts = {}
        self.task_started_at = time.monotonic()

    def allow_tool_call(self, tool: str = "", target: str = "") -> tuple[bool, str]:
        if self.session_tool_calls >= self.limits.get("max_total_tool_calls_per_session", 200):
            return False, "max_total_tool_calls_per_session reached"
        if time.monotonic() - self.task_started_at >= self.limits.get("max_wallclock_per_task_seconds", 900):
            return False, "max_wallclock_per_task_seconds reached"
        if self.task_tool_calls >= self.limits.get("max_tool_calls_per_task", 6):
            return False, "max_tool_calls_per_task reached"
        key = (tool, target)
        if self.attempts.get(key, 0) >= self.limits.get("max_same_tool_same_target_retries", 2):
            return False, f"max_same_tool_same_target_retries reached for {tool}/{target}"
        return True, ""

    def record_tool_call(self, success: bool, tool: str = "", target: str = "") -> None:
        self.session_tool_calls += 1
        self.task_tool_calls += 1
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
