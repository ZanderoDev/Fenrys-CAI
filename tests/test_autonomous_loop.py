from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from fenrys_cai.config import LoopConfig, RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.hypotheses import HypothesisEngine, HypothesisStatus, VerificationStatus
from fenrys_cai.models import Attempt
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry
from fenrys_cai.verification import match_observation


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


class SequenceReasoner:
    def __init__(self, decisions): self.decisions, self.calls = list(decisions), 0
    def decide(self, state, tools):
        self.calls += 1
        return self.decisions.pop(0) if self.decisions else Decision("stop", "finished", complete=True)


def test_continue_loops_to_reason_multiple_times(tmp_path: Path) -> None:
    reasoner = SequenceReasoner([Decision("continue", "think again"), Decision("continue", "one more"), Decision("stop", "done", complete=True)])
    state = FenrysGraph(registry(tmp_path), reasoner).run(CyberState("continue", "think"))
    assert state.completed
    assert reasoner.calls == 3
    assert state.iteration_count == 3


def test_iteration_limit_terminates_continue_loop(tmp_path: Path) -> None:
    reasoner = SequenceReasoner([Decision("continue", "again")] * 20)
    state = FenrysGraph(registry(tmp_path), reasoner, loop_config=LoopConfig(max_iterations=3)).run(CyberState("limit", "bounded"))
    assert state.completed
    assert state.history[-1] == "Iteration limit reached"


def make_attempt(**overrides) -> Attempt:
    data = dict(objective="goal", target="local", tool="execute", parameters={"command": "pwd"}, strategy="baseline observation", result="success")
    data.update(overrides)
    return Attempt(**data)


def test_attempt_identity_and_meaningful_retries() -> None:
    original = make_attempt(progress_token="state-a")
    state = CyberState("anti", "goal", attempts=[original])
    assert not state.can_attempt(make_attempt(progress_token="state-a"))
    assert state.can_attempt(make_attempt(parameters={"command": "id"}, progress_token="state-a"))
    assert state.can_attempt(make_attempt(strategy="different validation strategy", progress_token="state-a"))
    assert state.can_attempt(make_attempt(target="other", progress_token="state-a"))
    assert state.can_attempt(make_attempt(hypothesis_id="hyp_new", progress_token="state-a"))
    assert state.can_attempt(make_attempt(progress_token="state-b"))


def test_duplicate_graph_attempt_records_dead_end(tmp_path: Path) -> None:
    decisions = [
        Decision("execute", {"command": "pwd", "session_id": "duplicate"}, "same strategy"),
        Decision("execute", {"command": "pwd", "session_id": "duplicate"}, "same strategy"),
    ]
    state = FenrysGraph(registry(tmp_path), SequenceReasoner(decisions)).run(CyberState("duplicate", "goal"))
    assert state.completed
    assert len(state.attempts) == 1
    assert len(state.dead_ends) == 1
    assert state.dead_ends[0].blocked_attempts == [state.attempts[0].id]


def test_hypothesis_attempt_link_and_identical_retest_blocked(tmp_path: Path) -> None:
    hypothesis = HypothesisEngine.create("Local cwd is stable", "verification", 0.5, ["same path"], "goal")
    decisions = [
        Decision("execute", {"command": "pwd", "session_id": "hyp", "hypothesis_id": hypothesis.id}, "test cwd"),
        Decision("execute", {"command": "pwd", "session_id": "hyp", "hypothesis_id": hypothesis.id}, "test cwd"),
    ]
    state = FenrysGraph(registry(tmp_path), SequenceReasoner(decisions)).run(CyberState("hyp", "goal", hypotheses=[hypothesis]))
    assert state.attempts[0].hypothesis_id == hypothesis.id
    assert state.hypotheses[0].test_attempts == [state.attempts[0].id]
    assert state.dead_ends


@pytest.mark.parametrize(("expected", "actual", "matched"), [
    ({"type": "exact_text", "value": "hello"}, "hello", True),
    ({"type": "substring", "value": "ell"}, "hello", True),
    ({"type": "regex", "pattern": r"h.*o"}, "hello", True),
    ({"type": "json_field_exists", "path": "result.marker"}, '{"result":{"marker":true}}', True),
    ({"type": "json_field_equals", "path": "status", "value": "authenticated"}, '{"status":"authenticated"}', True),
    ({"type": "numeric_compare", "path": "count", "operator": "gte", "value": 3}, '{"count":4}', True),
])
def test_deterministic_verification_matchers(expected, actual, matched) -> None:
    assert match_observation(expected, actual).matched is matched


def test_generic_success_is_not_implicit_match() -> None:
    assert match_observation({}, '{"success":true}').matched is None
    assert match_observation({}, "HTTP 200").matched is None
    assert match_observation({}, "exit_code=0").matched is None


def test_graph_verification_confirmed_and_refuted(tmp_path: Path) -> None:
    confirmed = HypothesisEngine.create("Marker exists", "verification", 0.5, ["marker"], "goal")
    reasoner = SequenceReasoner([
        Decision("verify", "check", verification={"hypothesis_id": confirmed.id, "method": "json compare",
            "expected_observation": {"type": "json_field_equals", "path": "status", "value": "ok"},
            "actual_observation": '{"status":"ok"}', "evidence_id": "ev_ok"}),
        Decision("stop", "verified", complete=True),
    ])
    state = FenrysGraph(registry(tmp_path), reasoner).run(CyberState("confirmed", "goal", hypotheses=[confirmed]))
    assert state.hypotheses[0].status == HypothesisStatus.CONFIRMED
    assert state.verifications[0].status == VerificationStatus.CONFIRMED

    refuted = HypothesisEngine.create("Marker exists", "verification", 0.5, ["marker"], "goal")
    reasoner = SequenceReasoner([
        Decision("verify", "check", verification={"hypothesis_id": refuted.id, "method": "exact",
            "expected_observation": {"type": "exact_text", "value": "yes"}, "actual_observation": "no", "evidence_id": "ev_no"}),
        Decision("stop", "refuted", complete=True),
    ])
    state = FenrysGraph(registry(tmp_path), reasoner).run(CyberState("refuted", "goal", hypotheses=[refuted]))
    assert state.hypotheses[0].status == HypothesisStatus.REFUTED
    assert state.verifications[0].status == VerificationStatus.FAILED


def test_dead_end_and_loop_counters_survive_checkpoint(tmp_path: Path) -> None:
    database = tmp_path / "loop.sqlite"
    decisions = [Decision("execute", {"command": "pwd", "session_id": "resume"}, "same"),
                 Decision("execute", {"command": "pwd", "session_id": "resume"}, "same")]
    with SqliteSaver.from_conn_string(str(database)) as saver:
        state = FenrysGraph(registry(tmp_path), SequenceReasoner(decisions), saver).run(CyberState("resume", "goal"))
        assert state.dead_ends
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(registry(tmp_path), SequenceReasoner([]), saver).resume("resume")
    assert restored.dead_ends[0].reason.startswith("Repeated attempt")
    assert restored.iteration_count >= 2
    assert restored.tool_call_count == 1
