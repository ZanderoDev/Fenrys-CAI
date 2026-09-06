from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InvestigationContext:
    """Bounded, structured context assembled for an agent turn."""

    session_id: str
    mode: str
    target: str | None
    state: dict[str, Any] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)

    def compact(self, max_findings: int = 20) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "target": self.target,
            "state": self.state,
            "findings": self.findings[-max_findings:],
        }
