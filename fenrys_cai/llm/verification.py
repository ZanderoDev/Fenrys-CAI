from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .provider import LLMError, LLMProvider


@dataclass(frozen=True)
class LLMVerificationDecision:
    decision: str
    confidence: float
    rationale: str


class LLMVerifier:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    def verify(self, *, hypothesis: dict[str, Any], expected: Any, actual: str,
               evidence_ids: list[str], existing_evidence_ids: set[str]) -> LLMVerificationDecision:
        if any(item not in existing_evidence_ids for item in evidence_ids):
            raise LLMError("invalid_evidence", "Verification references nonexistent evidence")
        system = (
            "You are Fenrys verification reasoning. Decide confirmed, refuted, or inconclusive from bounded evidence. "
            "Confidence is metadata, not proof. Return only JSON: "
            '{"decision":"confirmed|refuted|inconclusive","confidence":0.0,"rationale":"..."}'
        )
        user = json.dumps({"hypothesis": hypothesis, "expected_observation": expected,
                           "actual_observation": actual[:4000], "evidence_ids": evidence_ids}, default=str)
        data = self.provider.complete_json(system, user)
        decision = data.get("decision")
        if decision not in {"confirmed", "refuted", "inconclusive"}:
            raise LLMError("malformed_response", "Invalid LLM verification decision")
        confidence = data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            raise LLMError("malformed_response", "Invalid LLM verification confidence")
        rationale = data.get("rationale")
        if not isinstance(rationale, str):
            raise LLMError("malformed_response", "Invalid LLM verification rationale")
        return LLMVerificationDecision(decision, max(0.0, min(1.0, float(confidence))), rationale[:2000])
