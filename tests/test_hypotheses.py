from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.graph import FenrysGraph
from fenrys_cai.hypotheses import (
    HypothesisEngine, HypothesisStatus, LifecycleError, VerificationStatus,
)
from fenrys_cai.llm.primary import PrimaryReasoner
from fenrys_cai.models import ToolResult
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


def hypothesis():
    return HypothesisEngine.create("Observed service may expose a test condition", "network", 0.5, ["specific banner"], "validate service")


def test_hypothesis_supported_confirmed_lifecycle() -> None:
    item = hypothesis()
    assert item.status == HypothesisStatus.PROPOSED
    HypothesisEngine.transition(item, HypothesisStatus.TESTING)
    HypothesisEngine.attach_evidence(item, "ev_support", supporting=True)
    HypothesisEngine.transition(item, HypothesisStatus.SUPPORTED)
    verification = HypothesisEngine.create_verification(item, "compare banner", "specific banner appears")
    HypothesisEngine.transition_verification(verification, VerificationStatus.IN_PROGRESS)
    verification.supporting_evidence.append("ev_support")
    HypothesisEngine.transition_verification(verification, VerificationStatus.CONFIRMED, actual_observation="specific banner appears", confidence=0.9)
    HypothesisEngine.conclude(item, verification)
    assert item.status == HypothesisStatus.CONFIRMED


def test_refuted_inconclusive_superseded_and_invalid_transitions() -> None:
    refuted = hypothesis()
    HypothesisEngine.transition(refuted, HypothesisStatus.TESTING)
    HypothesisEngine.transition(refuted, HypothesisStatus.REFUTED)
    assert refuted.status == HypothesisStatus.REFUTED
    inconclusive = hypothesis()
    HypothesisEngine.transition(inconclusive, HypothesisStatus.TESTING)
    HypothesisEngine.transition(inconclusive, HypothesisStatus.INCONCLUSIVE)
    HypothesisEngine.transition(inconclusive, HypothesisStatus.TESTING)
    HypothesisEngine.transition(inconclusive, HypothesisStatus.SUPERSEDED)
    assert inconclusive.status == HypothesisStatus.SUPERSEDED
    with pytest.raises(LifecycleError, match="Cannot transition"):
        HypothesisEngine.transition(refuted, HypothesisStatus.TESTING)


def test_evidence_references_are_bounded_and_not_duplicated() -> None:
    item = hypothesis()
    for index in range(60):
        HypothesisEngine.attach_evidence(item, f"ev_{index}", supporting=True, limit=10)
    HypothesisEngine.attach_evidence(item, "ev_59", supporting=True, limit=10)
    HypothesisEngine.attach_evidence(item, "ev_contra", supporting=False)
    assert len(item.supporting_evidence) == 10
    assert item.supporting_evidence.count("ev_59") == 1
    assert item.contradicting_evidence == ["ev_contra"]


def test_verification_transitions_and_evidence_requirement() -> None:
    item = hypothesis()
    HypothesisEngine.transition(item, HypothesisStatus.TESTING)
    verification = HypothesisEngine.create_verification(item, "deterministic comparison", "marker is present")
    HypothesisEngine.transition_verification(verification, VerificationStatus.IN_PROGRESS)
    with pytest.raises(LifecycleError, match="supporting evidence"):
        HypothesisEngine.transition_verification(verification, VerificationStatus.CONFIRMED)
        HypothesisEngine.conclude(item, verification)


@pytest.mark.parametrize("result", [
    ToolResult(status="success", tool="execute", exit_code=0, stdout="ok"),
    ToolResult(status="success", tool="http", stdout="HTTP 200"),
    ToolResult(status="success", tool="remote", stdout='{"success":true}'),
])
def test_success_semantics_do_not_auto_confirm(result: ToolResult) -> None:
    state = CyberState("semantics", "verify")
    item = hypothesis()
    state.add_hypothesis(item)
    state.observe(result)
    assert item.status == HypothesisStatus.PROPOSED
    assert item.verification_state == VerificationStatus.PENDING


class FakeProvider:
    def __init__(self, responses): self.responses = list(responses)
    def complete_json(self, system, user, *, max_tokens=1024): return self.responses.pop(0)


def test_graph_hypothesis_then_verification_is_conditional(tmp_path: Path) -> None:
    provider = FakeProvider([
        {"decision": "hypothesis", "rationale": "testable idea", "confidence": 0.6,
         "hypothesis": {"statement": "Local directory is writable", "domain": "verification", "required_evidence": ["write then read marker"]}},
        {"decision": "stop", "rationale": "hypothesis recorded"},
    ])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider)).run(CyberState("hyp", "test hypothesis"))
    assert len(state.hypotheses) == 1
    assert state.hypotheses[0].status == HypothesisStatus.PROPOSED


def test_graph_verify_creates_in_progress_not_confirmation(tmp_path: Path) -> None:
    item = hypothesis()
    initial = CyberState("verify", "verify hypothesis", hypotheses=[item])
    provider = FakeProvider([
        {"decision": "verify", "rationale": "define expected observation", "verification": {
            "hypothesis_id": item.id, "method": "compare marker", "expected_observation": "marker is present"}},
        {"decision": "stop", "rationale": "verification pending"},
    ])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider)).run(initial)
    assert state.hypotheses[0].status == HypothesisStatus.TESTING
    assert state.verifications[0].status == VerificationStatus.IN_PROGRESS
    assert state.hypotheses[0].status != HypothesisStatus.CONFIRMED


def test_checkpoint_restores_hypothesis_and_verification(tmp_path: Path) -> None:
    item = hypothesis()
    HypothesisEngine.transition(item, HypothesisStatus.TESTING)
    verification = HypothesisEngine.create_verification(item, "inspect", "marker")
    HypothesisEngine.transition_verification(verification, VerificationStatus.IN_PROGRESS)
    initial = CyberState("lifecycle", "persist lifecycle", hypotheses=[item], verifications=[verification], completed=True)
    database = tmp_path / "checkpoints.sqlite"
    provider = FakeProvider([{"decision": "stop", "rationale": "done"}])
    with SqliteSaver.from_conn_string(str(database)) as saver:
        FenrysGraph(registry(tmp_path), PrimaryReasoner(provider), saver).run(initial)
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider), saver).resume("lifecycle")
    assert restored.hypotheses[0].status == HypothesisStatus.TESTING
    assert restored.verifications[0].status == VerificationStatus.IN_PROGRESS


def test_supersession_preserves_history() -> None:
    state = CyberState("supersede", "pivot")
    old = hypothesis()
    state.add_hypothesis(old)
    HypothesisEngine.transition(old, HypothesisStatus.SUPERSEDED)
    new = HypothesisEngine.create("New evidence suggests another condition", "network", 0.7, ["new marker"], state.goal)
    state.add_hypothesis(new)
    assert len(state.hypotheses) == 2
    assert old.status == HypothesisStatus.SUPERSEDED
    assert new.status == HypothesisStatus.PROPOSED
