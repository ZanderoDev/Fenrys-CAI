from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BudgetController:
    limits: dict[str, int]
    tool_calls: int = 0
    agent_turns: int = 0
    consecutive_failures: int = 0
    started_at: float = 0.0
    attempts: dict[tuple[str, str], int] | None = None
    lock: Any = field(default=None, compare=False, repr=False)

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

    def _ensure_lock(self) -> Any:
        # Lazy: asyncio.Lock hanya dibuat di dalam event loop yang memakai.
        if self.lock is None:
            self.lock = asyncio.Lock()
        return self.lock

    async def claim(self, tool: str = "", target: str = "") -> tuple[bool, str]:
        """Cek-dan-catat atomik untuk jalur async (anti-TOCTOU asyncio.gather).

        Berbeda dari pasangan allow+record: klaim menaikkan tool_calls dan
        attempts SEBELUM tool dieksekusi, sehingga N klaim paralel tidak bisa
        semuanya lolos di bawah cap. Panggil note_result() setelah eksekusi
        untuk memperbarui consecutive_failures (agar tidak double-count).
        """
        lock = self._ensure_lock()
        async with lock:
            allowed, reason = self.allow_tool_call(tool, target)
            if not allowed:
                return False, reason
            self.tool_calls += 1
            key = (tool, target)
            self.attempts[key] = self.attempts.get(key, 0) + 1
            return True, ""

    def note_result(self, success: bool) -> None:
        """Lanjutan claim(): hanya perbarui consecutive_failures (sinkron,
        atomik terhadap event loop karena tanpa await di dalamnya)."""
        self.consecutive_failures = 0 if success else self.consecutive_failures + 1

    def allow_agent_turn(self) -> tuple[bool, str]:
        if self.agent_turns >= self.limits.get("max_agent_turns_per_task", 10):
            return False, "max_agent_turns_per_task reached"
        if self.consecutive_failures >= self.limits.get("max_consecutive_failures_before_escalation", 3):
            return False, "consecutive failure escalation threshold reached"
        self.agent_turns += 1
        return True, ""
