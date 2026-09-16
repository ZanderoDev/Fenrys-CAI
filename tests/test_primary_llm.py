from pathlib import Path

import pytest

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.graph import FenrysGraph
from fenrys_cai.llm.primary import PrimaryDecision, PrimaryReasoner, validate_primary_decision
from fenrys_cai.llm.provider import LLMError, LLMProvider
from fenrys_cai.models import ToolSpec
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


class FakeLLMProvider:
    """Deterministic fake LLM provider for primary reasoning tests."""
    def __init__(self, responses: list[dict] | None = None, error: LLMError | None = None) -> None:
        self._responses = list(responses or [])
        self._error = error
        self.calls: list[dict] = []

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict:
        self.calls.append({"system_length": len(system), "user_length": len(user)})
        if self._error:
            raise self._error
        if self._responses:
            return self._responses.pop(0)
        return {"decision": "stop", "rationale": "default stop"}


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


TOOLS = [ToolSpec("execute", "Run commands", {}, ("terminal",), provider="local"),
         ToolSpec("read_file", "Read files", {}, ("filesystem",), provider="local"),
         ToolSpec("write_file", "Write files", {}, ("filesystem",), provider="local")]


def test_validate_tool_decision() -> None:
    d = validate_primary_decision({"decision": "tool", "tool": "execute", "arguments": {"command": "pwd"}, "rationale": "check", "confidence": 0.8}, {"execute", "read_file"})
    assert d.kind == "tool"
    assert d.tool == "execute"
    assert d.arguments["command"] == "pwd"


def test_validate_specialist_decision() -> None:
    d = validate_primary_decision({"decision": "specialist", "specialist": "web", "rationale": "needs web review"}, set())
    assert d.kind == "specialist"
    assert d.specialist == "web"


def test_validate_stop_decision() -> None:
    d = validate_primary_decision({"decision": "stop", "rationale": "done"}, set())
    assert d.kind == "stop"
    assert d.complete


def test_validate_continue_decision() -> None:
    d = validate_primary_decision({"decision": "continue", "rationale": "reviewing"}, set())
    assert d.kind == "continue"
    assert not d.complete


def test_validate_missing_decision() -> None:
    with pytest.raises(LLMError, match="missing.*decision"):
        validate_primary_decision({"rationale": "no decision"}, set())


def test_validate_invalid_decision_type() -> None:
    with pytest.raises(LLMError, match="Invalid primary decision"):
        validate_primary_decision({"decision": "explode", "rationale": "bad"}, set())


def test_validate_invalid_tool() -> None:
    with pytest.raises(LLMError, match="not in available tools"):
        validate_primary_decision({"decision": "tool", "tool": "nmap", "arguments": {}, "rationale": "bad"}, {"execute"})


def test_validate_invalid_specialist() -> None:
    with pytest.raises(LLMError, match="Invalid specialist domain"):
        validate_primary_decision({"decision": "specialist", "specialist": "hacking", "rationale": "bad"}, set())


def test_validate_arguments_not_dict() -> None:
    with pytest.raises(LLMError, match="arguments must be a JSON object"):
        validate_primary_decision({"decision": "tool", "tool": "execute", "arguments": "bad", "rationale": "x"}, {"execute"})


def test_primary_reasoner_with_fake_provider() -> None:
    fake = FakeLLMProvider([{"decision": "tool", "tool": "execute", "arguments": {"command": "pwd", "session_id": "test"}, "rationale": "baseline", "confidence": 0.7}])
    reasoner = PrimaryReasoner(fake)
    decision = reasoner.decide(CyberState("test", "baseline"), TOOLS)
    assert decision.kind == "tool"
    assert decision.tool == "execute"
    assert fake.calls[0]["system_length"] > 100


def test_primary_reasoner_provider_error() -> None:
    fake = FakeLLMProvider(error=LLMError("timeout", "timed out"))
    reasoner = PrimaryReasoner(fake)
    with pytest.raises(LLMError, match="timed out"):
        reasoner.decide(CyberState("test", "test"), TOOLS)


def test_graph_primary_tool_decision(tmp_path: Path) -> None:
    fake = FakeLLMProvider([
        {"decision": "tool", "tool": "execute", "arguments": {"command": "pwd", "session_id": "primary"}, "rationale": "baseline"},
        {"decision": "stop", "rationale": "observed baseline"},
    ])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(fake)).run(CyberState("primary", "test primary"))
    assert state.completed
    assert state.attempts[-1].tool == "execute"
    assert state.evidence[-1]["status"] == "success"


def test_graph_primary_specialist_decision(tmp_path: Path) -> None:
    from fenrys_cai.specialists.fake_llm import FakeSpecialistLLM, TOOL_RESPONSE
    from fenrys_cai.specialists.registry import build_router
    fake_primary = FakeLLMProvider([
        {"decision": "specialist", "specialist": "recon", "rationale": "needs recon"},
        {"decision": "stop", "rationale": "specialist observed"},
    ])
    fake_specialist = FakeSpecialistLLM([TOOL_RESPONSE])
    router = build_router(Path("prompts/specialists"), decide=fake_specialist)
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(fake_primary), specialist_router=router).run(CyberState("spec", "test specialist routing"))
    assert state.completed
    assert any("specialist:" in item for item in state.history)


def test_graph_primary_malformed_output_no_execution(tmp_path: Path) -> None:
    fake = FakeLLMProvider([{"decision": "tool", "tool": "nmap", "arguments": {}, "rationale": "bad tool"}])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(fake)).run(CyberState("malformed", "test malformed"))
    assert state.completed
    assert not state.attempts
    assert "Reasoner failure" in state.history[-1]


def test_graph_checkpoint_resume_with_primary_llm(tmp_path: Path) -> None:
    from langgraph.checkpoint.sqlite import SqliteSaver
    fake = FakeLLMProvider([
        {"decision": "tool", "tool": "execute", "arguments": {"command": "pwd", "session_id": "resume"}, "rationale": "baseline"},
        {"decision": "stop", "rationale": "done"},
    ])
    database = tmp_path / "checkpoints.sqlite"
    with SqliteSaver.from_conn_string(str(database)) as saver:
        state = FenrysGraph(registry(tmp_path), PrimaryReasoner(fake), saver).run(CyberState("resume", "test resume"))
        assert state.completed
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(registry(tmp_path), PrimaryReasoner(fake), saver).resume("resume")
        assert restored.completed
        assert len(restored.attempts) == 1
