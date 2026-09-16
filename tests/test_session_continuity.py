from pathlib import Path

from fenrys_cai.config import LoopConfig, RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


class SequenceReasoner:
    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.calls = 0

    def decide(self, state, tools):
        self.calls += 1
        return self.decisions.pop(0) if self.decisions else Decision("stop", "finished", complete=True)


def execute(session: str, command: str = "pwd") -> Decision:
    return Decision("execute", {"command": command, "session_id": session}, "baseline observation")


def test_new_session_starts_fresh(tmp_path: Path) -> None:
    state = FenrysGraph(registry(tmp_path), SequenceReasoner([Decision("stop", "done", complete=True)])).continue_session("new", "original objective")
    assert state.goal == "original objective"
    assert state.completed
    assert state.history[-1] == "done"


def test_second_turn_preserves_goal_and_phase(tmp_path: Path) -> None:
    reasoner = SequenceReasoner([Decision("stop", "first", complete=True), Decision("stop", "second", complete=True)])
    graph = FenrysGraph(registry(tmp_path), reasoner)
    first = graph.continue_session("session", "original objective")
    graph.app.update_state({"configurable": {"thread_id": "session"}}, {"phase": "EXPLOIT"})
    second = graph.continue_session("session", "new directive")
    assert first.goal == second.goal == "original objective"
    assert second.phase == "EXPLOIT"
    assert "user_directive: new directive" in second.history


def test_second_turn_resets_turn_counters_and_keeps_evidence(tmp_path: Path) -> None:
    reasoner = SequenceReasoner([execute("session"), Decision("stop", "first", complete=True), Decision("stop", "second", complete=True)])
    graph = FenrysGraph(registry(tmp_path), reasoner)
    first = graph.continue_session("session", "objective")
    second = graph.continue_session("session", "review evidence")
    assert first.tool_call_count == 1
    assert second.tool_call_count == 0
    assert second.iteration_count == 1
    assert second.evidence == first.evidence


def test_dead_end_blocks_repeat_across_turns(tmp_path: Path) -> None:
    reasoner = SequenceReasoner([execute("session"), Decision("stop", "first", complete=True), execute("session")])
    graph = FenrysGraph(registry(tmp_path), reasoner, loop_config=LoopConfig(max_repeated_attempts=0))
    first = graph.continue_session("session", "objective")
    second = graph.continue_session("session", "repeat it")
    assert len(first.attempts) == len(second.attempts) == 1
    assert second.completed
    assert second.dead_ends[0].blocked_attempts == [first.attempts[0].id]


def test_continue_after_completed_session_retains_evidence(tmp_path: Path) -> None:
    reasoner = SequenceReasoner([execute("session"), Decision("stop", "first", complete=True), Decision("stop", "resumed", complete=True)])
    graph = FenrysGraph(registry(tmp_path), reasoner)
    first = graph.continue_session("session", "objective")
    second = graph.continue_session("session", "next directive")
    assert first.completed and second.completed
    assert reasoner.calls == 3
    assert second.evidence == first.evidence
    assert second.history[-1] == "resumed"


def test_stream_turn_emits_incremental_events_and_matches_invoke_result(tmp_path: Path) -> None:
    stream_graph = FenrysGraph(registry(tmp_path), SequenceReasoner([execute("same"), Decision("stop", "done", complete=True)]))
    events = list(stream_graph.stream_turn("same", "objective"))
    streamed = events[-1]["state"]
    invoke_graph = FenrysGraph(registry(tmp_path), SequenceReasoner([execute("same"), Decision("stop", "done", complete=True)]))
    invoked = invoke_graph.continue_session("same", "objective")
    assert {event["node"] for event in events[:-1]} >= {"reason", "act"}
    assert [(item.tool, item.result) for item in streamed.attempts] == [(item.tool, item.result) for item in invoked.attempts]
    assert streamed.goal == invoked.goal
    assert streamed.history == invoked.history
    assert streamed.completed == invoked.completed
