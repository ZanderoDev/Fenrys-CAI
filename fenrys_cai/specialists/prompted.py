from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import SpecialistDecision, SpecialistRequest, SpecialistResponse

DecisionBuilder = Callable[[SpecialistRequest, str], SpecialistDecision]


class PromptedSpecialist:
    """A lightweight specialist that combines a Fenrys prompt with an injected reasoner."""
    def __init__(self, domain: str, prompt_root: Path, decide: DecisionBuilder) -> None:
        self.domain = domain
        self.prompt_root = prompt_root
        self._decide = decide

    @property
    def prompt(self) -> str:
        path = self.prompt_root / f"{self.domain}.md"
        return path.read_text(encoding="utf-8")

    def reason(self, request: SpecialistRequest) -> SpecialistResponse:
        try:
            decision = self._decide(request, self.prompt)
        except Exception as exc:
            code = getattr(exc, "code", "unknown")
            return SpecialistResponse(self.domain, SpecialistDecision("stop", f"Specialist LLM failure: {code}", confidence=0.0), evidence_requirements=("provider recovery",))
        if not decision.kind or not decision.rationale:
            return SpecialistResponse(self.domain, SpecialistDecision("stop", "Malformed specialist decision", confidence=0.0), evidence_requirements=("valid rationale",))
        return SpecialistResponse(self.domain, decision, evidence_requirements=("bounded observation",) if decision.verification_needed else ())
