from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class HypothesisStatus(StrEnum):
    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"
    SUPERSEDED = "superseded"


class VerificationStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class LifecycleError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class Hypothesis:
    statement: str
    domain: str
    confidence: float
    required_evidence: list[str]
    related_objective: str
    id: str = field(default_factory=lambda: f"hyp_{uuid.uuid4().hex}")
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    related_target: str = ""
    test_attempts: list[str] = field(default_factory=list)
    verification_state: VerificationStatus = VerificationStatus.PENDING
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["verification_state"] = self.verification_state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hypothesis:
        value = dict(data)
        value["status"] = HypothesisStatus(value.get("status", "proposed"))
        value["verification_state"] = VerificationStatus(value.get("verification_state", "pending"))
        return cls(**value)


@dataclass
class Verification:
    hypothesis_id: str
    method: str
    expected_observation: Any
    id: str = field(default_factory=lambda: f"ver_{uuid.uuid4().hex}")
    status: VerificationStatus = VerificationStatus.PENDING
    actual_observation: str = ""
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Verification:
        value = dict(data)
        value["status"] = VerificationStatus(value.get("status", "pending"))
        return cls(**value)


_HYPOTHESIS_TRANSITIONS = {
    HypothesisStatus.PROPOSED: {HypothesisStatus.TESTING, HypothesisStatus.SUPERSEDED},
    HypothesisStatus.TESTING: {HypothesisStatus.SUPPORTED, HypothesisStatus.REFUTED, HypothesisStatus.INCONCLUSIVE, HypothesisStatus.SUPERSEDED},
    HypothesisStatus.SUPPORTED: {HypothesisStatus.CONFIRMED, HypothesisStatus.REFUTED, HypothesisStatus.INCONCLUSIVE, HypothesisStatus.SUPERSEDED},
    HypothesisStatus.INCONCLUSIVE: {HypothesisStatus.TESTING, HypothesisStatus.SUPERSEDED},
    HypothesisStatus.CONFIRMED: {HypothesisStatus.SUPERSEDED},
    HypothesisStatus.REFUTED: {HypothesisStatus.SUPERSEDED},
    HypothesisStatus.SUPERSEDED: set(),
}

_VERIFICATION_TRANSITIONS = {
    VerificationStatus.PENDING: {VerificationStatus.IN_PROGRESS},
    VerificationStatus.IN_PROGRESS: {VerificationStatus.CONFIRMED, VerificationStatus.FAILED, VerificationStatus.INCONCLUSIVE},
    VerificationStatus.CONFIRMED: set(),
    VerificationStatus.FAILED: set(),
    VerificationStatus.INCONCLUSIVE: {VerificationStatus.IN_PROGRESS},
}


class HypothesisEngine:
    """Centralized lifecycle operations; callers cannot bypass transition checks."""

    @staticmethod
    def create(statement: str, domain: str, confidence: float, required_evidence: list[str], objective: str, **kwargs: Any) -> Hypothesis:
        if not statement.strip() or not domain.strip():
            raise LifecycleError("invalid_hypothesis", "Hypothesis statement and domain are required")
        return Hypothesis(statement, domain, max(0.0, min(1.0, confidence)), required_evidence[:20], objective, **kwargs)

    @staticmethod
    def transition(hypothesis: Hypothesis, status: HypothesisStatus) -> Hypothesis:
        if status not in _HYPOTHESIS_TRANSITIONS[hypothesis.status]:
            raise LifecycleError("invalid_transition", f"Cannot transition hypothesis from {hypothesis.status} to {status}")
        hypothesis.status = status
        hypothesis.updated_at = time.time()
        return hypothesis

    @staticmethod
    def attach_evidence(hypothesis: Hypothesis, evidence_id: str, *, supporting: bool, limit: int = 50) -> Hypothesis:
        if not evidence_id:
            raise LifecycleError("invalid_evidence", "Evidence ID is required")
        target = hypothesis.supporting_evidence if supporting else hypothesis.contradicting_evidence
        if evidence_id not in target:
            target.append(evidence_id)
            del target[:-limit]
        hypothesis.updated_at = time.time()
        return hypothesis

    @staticmethod
    def create_verification(hypothesis: Hypothesis, method: str, expected_observation: Any, provenance: dict[str, Any] | None = None) -> Verification:
        if not method.strip() or expected_observation in (None, "", {}):
            raise LifecycleError("invalid_verification", "Verification method and expected observation are required")
        return Verification(hypothesis.id, method, expected_observation, provenance=provenance or {})

    @staticmethod
    def transition_verification(verification: Verification, status: VerificationStatus, *, actual_observation: str = "", confidence: float = 0.0) -> Verification:
        if status not in _VERIFICATION_TRANSITIONS[verification.status]:
            raise LifecycleError("invalid_transition", f"Cannot transition verification from {verification.status} to {status}")
        verification.status = status
        verification.actual_observation = actual_observation[:2000]
        verification.confidence = max(0.0, min(1.0, confidence))
        verification.timestamp = time.time()
        return verification

    @staticmethod
    def conclude(hypothesis: Hypothesis, verification: Verification) -> Hypothesis:
        if verification.hypothesis_id != hypothesis.id:
            raise LifecycleError("verification_mismatch", "Verification does not belong to hypothesis")
        if verification.status == VerificationStatus.CONFIRMED:
            if not verification.supporting_evidence:
                raise LifecycleError("evidence_required", "Confirmation requires supporting evidence references")
            if hypothesis.status == HypothesisStatus.TESTING:
                HypothesisEngine.transition(hypothesis, HypothesisStatus.SUPPORTED)
            HypothesisEngine.transition(hypothesis, HypothesisStatus.CONFIRMED)
        elif verification.status == VerificationStatus.FAILED:
            HypothesisEngine.transition(hypothesis, HypothesisStatus.REFUTED)
        elif verification.status == VerificationStatus.INCONCLUSIVE:
            HypothesisEngine.transition(hypothesis, HypothesisStatus.INCONCLUSIVE)
        else:
            raise LifecycleError("verification_pending", "Verification has no conclusion")
        hypothesis.verification_state = verification.status
        return hypothesis
