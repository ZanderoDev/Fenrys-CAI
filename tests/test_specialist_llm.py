from pathlib import Path

import pytest

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.models import ToolSpec
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.specialists.base import SpecialistDecision, SpecialistRequest, SpecialistResponse, bounded_context
from fenrys_cai.specialists.fake_llm import (
    CONTINUE_RESPONSE, DELEGATE_RESPONSE, INVALID_DOMAIN_RESPONSE, INVALID_TOOL_RESPONSE,
    MALFORMED_RESPONSE, MISSING_DECISION_RESPONSE, STOP_RESPONSE, TOOL_RESPONSE,
    FakeSpecialistLLM, FakeSpecialistLLMError,
)
from fenrys_cai.specialists.llm_decision import SpecialistLLMError, _validate_decision, _VALID_DOMAINS
from fenrys_cai.specialists.prompted import PromptedSpecialist
from fenrys_cai.specialists.registry import DOMAINS, build_router
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


def test_fake_llm_tool_decision() -> None:
    fake = FakeSpecialistLLM([TOOL_RESPONSE])
    tools = (ToolSpec("execute", "Run commands", {}, ("terminal",), provider="local"),)
    request = SpecialistRequest("recon", "baseline check", "lab", "RECON", {}, tools)
    decision = fake(request, "prompt")
    assert decision.kind == "tool"
    assert decision.tool == "execute"
    assert decision.arguments["command"] == "pwd"
    assert fake.calls[0]["domain"] == "recon"


def test_fake_llm_delegate_decision() -> None:
    fake = FakeSpecialistLLM([DELEGATE_RESPONSE])
    request = SpecialistRequest("recon", "check cipher", "lab", "RECON", {})
    decision = fake(request, "prompt")
    assert decision.kind == "delegate"
    assert decision.delegate_to == "crypto"


def test_fake_llm_stop_decision() -> None:
    fake = FakeSpecialistLLM([STOP_RESPONSE])
    request = SpecialistRequest("verification", "verify claim", "lab", "VERIFY", {})
    decision = fake(request, "prompt")
    assert decision.kind == "stop"
    assert decision.confidence == 0.9


def test_fake_llm_continue_decision() -> None:
    fake = FakeSpecialistLLM([CONTINUE_RESPONSE])
    request = SpecialistRequest("web", "review endpoint", "lab", "ENUM", {})
    decision = fake(request, "prompt")
    assert decision.kind == "continue"


def test_validation_malformed_json() -> None:
    with pytest.raises(SpecialistLLMError, match="not a JSON object"):
        _validate_decision("not json", set())


def test_validation_missing_decision() -> None:
    with pytest.raises(SpecialistLLMError, match="missing.*decision"):
        _validate_decision(MISSING_DECISION_RESPONSE, set())


def test_validation_invalid_decision_type() -> None:
    with pytest.raises(SpecialistLLMError, match="Invalid decision type"):
        _validate_decision(MALFORMED_RESPONSE, set())


def test_validation_invalid_tool() -> None:
    with pytest.raises(SpecialistLLMError, match="not in available tools"):
        _validate_decision(INVALID_TOOL_RESPONSE, {"execute", "read_file"})


def test_validation_invalid_domain() -> None:
    with pytest.raises(SpecialistLLMError, match="Invalid specialist domain"):
        _validate_decision(INVALID_DOMAIN_RESPONSE, set())


def test_validation_tool_arguments_not_dict() -> None:
    with pytest.raises(SpecialistLLMError, match="arguments must be a JSON object"):
        _validate_decision({"decision": "tool", "rationale": "x", "tool": "execute", "arguments": "bad"}, {"execute"})


def test_provider_timeout_error() -> None:
    fake = FakeSpecialistLLMError("timeout", "LLM request timed out")
    request = SpecialistRequest("recon", "test", "lab", "RECON", {})
    with pytest.raises(SpecialistLLMError, match="timed out"):
        fake(request, "prompt")


def test_provider_auth_failure() -> None:
    fake = FakeSpecialistLLMError("auth_failure", "authentication failed")
    request = SpecialistRequest("recon", "test", "lab", "RECON", {})
    with pytest.raises(SpecialistLLMError, match="authentication"):
        fake(request, "prompt")


def test_malformed_output_never_executes_tool() -> None:
    fake = FakeSpecialistLLM([INVALID_TOOL_RESPONSE])
    request = SpecialistRequest("recon", "test", "lab", "RECON", {}, (ToolSpec("execute", "Run", {}, ("terminal",), provider="local"),))
    with pytest.raises(SpecialistLLMError, match="not in available tools"):
        fake(request, "prompt")


def test_llm_router_uses_fake_provider(tmp_path: Path) -> None:
    fake = FakeSpecialistLLM([TOOL_RESPONSE])
    router = build_router(Path("prompts/specialists"), decide=fake)
    assert set(router.specialists) == set(DOMAINS)
    request = SpecialistRequest("recon", "baseline", "lab", "RECON", {}, (ToolSpec("execute", "Run", {}, ("terminal",), provider="local"),))
    response = router.reason(request)
    assert response.decision.kind == "tool"
    assert response.decision.tool == "execute"


def test_llm_router_handles_provider_error_gracefully(tmp_path: Path) -> None:
    fake = FakeSpecialistLLMError("provider_error", "server error")
    router = build_router(Path("prompts/specialists"), decide=fake)
    request = SpecialistRequest("recon", "test", "lab", "RECON", {})
    response = router.reason(request)
    assert response.decision.kind == "stop"
    assert "LLM failure" in response.decision.rationale


def test_graph_specialist_llm_tool_reaches_registry(tmp_path: Path) -> None:
    fake = FakeSpecialistLLM([TOOL_RESPONSE])
    router = build_router(Path("prompts/specialists"), decide=fake)

    class LLMRequestingReasoner:
        def decide(self, state, tools):
            if not state.attempts and not any(item.startswith("specialist:") for item in state.history):
                return Decision("__specialist__", {"domain": "recon"}, "request LLM specialist")
            if state.attempts:
                return Decision(complete=True, rationale="LLM specialist tool observed")
            if any("specialist:" in item for item in state.history):
                return Decision("execute", {"command": "pwd", "session_id": state.session_id}, "act after specialist")
            return Decision(complete=True, rationale="done")

    state = FenrysGraph(registry(tmp_path), LLMRequestingReasoner(), specialist_router=router).run(CyberState("llm-spec", "test LLM specialist"))
    assert state.completed
    assert state.attempts[-1].tool == "execute"
    assert any("specialist:" in item for item in state.history)


def test_graph_specialist_llm_delegation(tmp_path: Path) -> None:
    fake = FakeSpecialistLLM([DELEGATE_RESPONSE, STOP_RESPONSE])
    router = build_router(Path("prompts/specialists"), decide=fake)

    class DelegatingReasoner:
        def decide(self, state, tools):
            if not any(item.startswith("specialist:") for item in state.history):
                return Decision("__specialist__", {"domain": "recon"}, "request specialist")
            if any("specialist:crypto:stop" in item for item in state.history):
                return Decision(complete=True, rationale="delegation completed")
            if any("specialist:recon:delegate" in item for item in state.history):
                return Decision("__specialist__", {"domain": "crypto"}, "follow delegation")
            return Decision(complete=True, rationale="done")

    state = FenrysGraph(registry(tmp_path), DelegatingReasoner(), specialist_router=router).run(CyberState("delegate", "test delegation"))
    assert state.completed
    assert any("specialist:recon:delegate" in item for item in state.history)
    assert any("specialist:crypto:stop" in item for item in state.history)


def test_graph_checkpoint_with_llm_specialist(tmp_path: Path) -> None:
    from langgraph.checkpoint.sqlite import SqliteSaver
    fake = FakeSpecialistLLM([TOOL_RESPONSE])
    router = build_router(Path("prompts/specialists"), decide=fake)

    class CheckpointReasoner:
        def decide(self, state, tools):
            if not state.attempts and not any(item.startswith("specialist:") for item in state.history):
                return Decision("__specialist__", {"domain": "recon"}, "request specialist")
            if state.attempts:
                return Decision(complete=True, rationale="done")
            if any("specialist:" in item for item in state.history):
                return Decision("execute", {"command": "pwd", "session_id": state.session_id}, "act after specialist")
            return Decision(complete=True, rationale="done")

    database = tmp_path / "checkpoints.sqlite"
    with SqliteSaver.from_conn_string(str(database)) as saver:
        state = FenrysGraph(registry(tmp_path), CheckpointReasoner(), saver, specialist_router=router).run(CyberState("checkpoint", "test"))
        assert state.completed
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(registry(tmp_path), CheckpointReasoner(), saver, specialist_router=router).resume("checkpoint")
        assert restored.completed
