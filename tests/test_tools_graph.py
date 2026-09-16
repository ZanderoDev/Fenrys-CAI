from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


class SequenceReasoner:
    def decide(self, state, tools):
        if not state.attempts:
            return Decision("write_file", {"path": "proof.txt", "content": "safe", "session_id": state.session_id}, "create proof")
        if len(state.attempts) == 1:
            return Decision("read_file", {"path": "proof.txt", "session_id": state.session_id}, "verify proof")
        return Decision(complete=True, rationale="two actions observed")


class FailingReasoner:
    def decide(self, state, tools): raise RuntimeError("provider unavailable")


class MissingToolReasoner:
    def decide(self, state, tools):
        return Decision(complete=True) if state.attempts else Decision("not_installed", {"session_id": state.session_id}, "validate failure")


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


def test_stategraph_compiles_multistep_invokes_registry_and_terminates(tmp_path: Path) -> None:
    graph = FenrysGraph(registry(tmp_path), SequenceReasoner())
    assert graph.app is not None
    state = graph.run(CyberState("multi", "prove graph"))
    assert state.completed
    assert [attempt.tool for attempt in state.attempts] == ["write_file", "read_file"]
    assert [item["status"] for item in state.evidence] == ["success", "success"]
    assert state.history[-1] == "two actions observed"


def test_sqlite_checkpoint_restores_completed_graph(tmp_path: Path) -> None:
    database = tmp_path / "checkpoints.sqlite"
    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = FenrysGraph(registry(tmp_path), SequenceReasoner(), saver)
        final = graph.run(CyberState("resume", "prove persistence"))
        assert final.completed
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(registry(tmp_path), SequenceReasoner(), saver).resume("resume")
    assert restored.completed
    assert len(restored.attempts) == 2


def test_model_and_tool_failure_become_clean_terminal_state(tmp_path: Path) -> None:
    failed_model = FenrysGraph(registry(tmp_path), FailingReasoner()).run(CyberState("model", "handle model failure"))
    assert failed_model.completed
    assert failed_model.history[-1].startswith("Reasoner failure:")
    failed_tool = FenrysGraph(registry(tmp_path), MissingToolReasoner()).run(CyberState("tool", "handle tool failure"))
    assert failed_tool.completed
    assert failed_tool.attempts[-1].result == "error"
    assert failed_tool.evidence[-1]["status"] == "error"


def test_resume_requires_existing_checkpoint(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No LangGraph checkpoint"):
        FenrysGraph(registry(tmp_path), SequenceReasoner()).resume("missing")
