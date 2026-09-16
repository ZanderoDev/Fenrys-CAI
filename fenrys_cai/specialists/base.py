from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from fenrys_cai.models import ToolSpec
from fenrys_cai.state import CyberState


@dataclass(frozen=True)
class SpecialistRequest:
    domain: str
    objective: str
    scope: str
    phase: str
    context: dict[str, Any]
    tools: tuple[ToolSpec, ...] = ()
    depth: int = 0


@dataclass(frozen=True)
class SpecialistDecision:
    kind: str
    rationale: str
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    delegate_to: str | None = None
    confidence: float = 0.5
    verification_needed: bool = False


@dataclass(frozen=True)
class SpecialistResponse:
    domain: str
    decision: SpecialistDecision
    hypotheses: tuple[str, ...] = ()
    evidence_requirements: tuple[str, ...] = ()


class Specialist(Protocol):
    domain: str

    def reason(self, request: SpecialistRequest) -> SpecialistResponse: ...


def bounded_context(state: CyberState, *, max_evidence: int = 5, max_history: int = 10) -> dict[str, Any]:
    """Build bounded specialist context from shared CyberState without raw output."""
    return {
        "session_id": state.session_id,
        "goal": state.goal,
        "scope": state.scope,
        "phase": state.phase,
        "findings": state.findings[-max_evidence:],
        "hypotheses": [item.to_dict() for item in state.hypotheses[-max_evidence:]],
        "verifications": [item.to_dict() for item in state.verifications[-max_evidence:]],
        "attempts": [{"id": item.id, "tool": item.tool, "target": item.target, "parameters": item.parameters,
                      "result": item.result, "strategy": item.strategy, "hypothesis_id": item.hypothesis_id,
                      "evidence_references": item.evidence_references} for item in state.attempts[-max_evidence:]],
        "evidence": state.evidence[-max_evidence:],
        "artifacts": state.artifacts[-max_evidence:],
        "history": state.history[-max_history:],
    }
