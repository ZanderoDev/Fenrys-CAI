from pathlib import Path

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.models import ToolSpec
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.specialists.base import SpecialistDecision, SpecialistRequest, SpecialistResponse, bounded_context
from fenrys_cai.specialists.prompted import PromptedSpecialist
from fenrys_cai.specialists.registry import DOMAINS, build_router
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


def test_prompt_files_and_bounded_context(tmp_path: Path) -> None:
    router = build_router(Path("prompts/specialists"))
    assert set(router.specialists) == set(DOMAINS)
    state = CyberState("bounded", "investigate crypto evidence")
    state.history.extend([f"item-{index}" for index in range(30)])
    state.evidence.extend({"index": index, "payload": "x" * 10000} for index in range(10))
    context = bounded_context(state)
    assert len(context["history"]) == 10
    assert len(context["evidence"]) == 5
    assert context["goal"] == "investigate crypto evidence"


def test_routing_is_signal_based_and_not_tool_catalog_based(tmp_path: Path) -> None:
    calls: list[str] = []
    def decide(request, prompt):
        calls.append(request.domain)
        return SpecialistDecision("continue", "observed")
    router = build_router(Path("prompts/specialists"), decide)
    tool = ToolSpec("generic", "generic", {}, ("mcp",), provider="test")
    crypto = SpecialistRequest("verification", "validate JWT and cipher evidence", "lab", "ENUM", {}, (tool,))
    web = SpecialistRequest("verification", "inspect HTTP login endpoint", "lab", "ENUM", {}, (tool,))
    pwn = SpecialistRequest("verification", "test binary overflow mitigation", "lab", "ENUM", {}, (tool,))
    assert router.select(crypto) == "crypto"
    assert router.select(web) == "web"
    assert router.select(pwn) == "pwn"
    router.reason(crypto)
    assert calls == ["crypto"]


def test_malformed_specialist_decision_is_normalized(tmp_path: Path) -> None:
    specialist = PromptedSpecialist("verification", Path("prompts/specialists"), lambda request, prompt: SpecialistDecision("", ""))
    response = specialist.reason(SpecialistRequest("verification", "check", "lab", "VERIFY", {}))
    assert response.decision.kind == "stop"
    assert response.decision.rationale == "Malformed specialist decision"


class SpecialistRequestingReasoner:
    def decide(self, state, tools):
        if not state.attempts and not any(item.startswith("specialist:") for item in state.history):
            return Decision("__specialist__", {"domain": "verification"}, "request specialist")
        if state.attempts:
            return Decision(complete=True, rationale="specialist tool observed")
        if any(item.startswith("specialist:") for item in state.history):
            return Decision("execute", {"command": "pwd", "session_id": state.session_id}, "act after specialist advice")
        return Decision(complete=True, rationale="specialist completed")


def test_graph_optional_specialist_returns_tool_and_observation(tmp_path: Path) -> None:
    router = build_router(Path("prompts/specialists"))
    state = FenrysGraph(registry(tmp_path), SpecialistRequestingReasoner(), specialist_router=router).run(CyberState("spec", "verify baseline"))
    assert state.completed
    assert any(item.startswith("specialist:") for item in state.history)
    assert state.attempts[-1].tool == "execute"
    assert state.evidence[-1]["status"] == "success"


def test_specialist_depth_limit_stops_delegation(tmp_path: Path) -> None:
    def decide(request, prompt):
        return SpecialistDecision("delegate", "needs another domain", delegate_to="crypto")
    router = build_router(Path("prompts/specialists"), decide)
    response = router.reason(SpecialistRequest("verification", "delegate", "lab", "VERIFY", {}, depth=3))
    assert response.decision.kind == "stop"
    assert "depth limit" in response.decision.rationale
