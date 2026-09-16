from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from fenrys_cai.config import LoopConfig, RuntimeConfig
from fenrys_cai.graph import FenrysGraph
from fenrys_cai.llm.primary import PrimaryReasoner
from fenrys_cai.llm.provider import LLMError
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


def registry(tmp_path: Path) -> ToolRegistry:
    result = ToolRegistry()
    result.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    return result


class SequenceProvider:
    def __init__(self, values): self.values, self.calls = list(values), 0
    def complete_json(self, system, user, *, max_tokens=1024):
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, Exception): raise value
        return value


def test_core_tool_specs_are_json_schema(tmp_path: Path) -> None:
    specs = {spec.name: spec for spec in registry(tmp_path).discover()}
    for name in ("read_file", "write_file", "execute"):
        assert specs[name].input_schema["type"] == "object"
        assert specs[name].input_schema["additionalProperties"] is False
        assert "properties" in specs[name].input_schema
    assert specs["read_file"].input_schema["required"] == ["path", "session_id"]
    assert specs["write_file"].input_schema["required"] == ["path", "content", "session_id"]
    assert "background" in specs["execute"].input_schema["properties"]
    assert "pty" in specs["execute"].input_schema["properties"]
    assert "timeout" in specs["execute"].input_schema["properties"]


def test_timeout_then_success_retries_reason(tmp_path: Path) -> None:
    provider = SequenceProvider([
        LLMError("timeout", "synthetic timeout"),
        {"decision": "stop", "rationale": "recovered"},
    ])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider)).run(CyberState("retry", "test"))
    assert state.completed
    assert provider.calls == 2
    assert state.provider_retry_count == 0
    assert any("Provider retry scheduled: timeout" in item for item in state.history)


def test_timeout_retries_until_success(tmp_path: Path) -> None:
    provider = SequenceProvider([LLMError("timeout", "one"), LLMError("timeout", "two"), {"decision": "stop", "rationale": "recovered"}])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider)).run(CyberState("exhaust", "test"))
    assert state.completed
    assert provider.calls == 3
    assert state.last_provider_error == ""


def test_auth_and_malformed_output_do_not_retry(tmp_path: Path) -> None:
    auth = SequenceProvider([LLMError("auth_failure", "bad key")])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(auth)).run(CyberState("auth", "test"))
    assert auth.calls == 1 and state.completed
    malformed = SequenceProvider([{"decision": "not-real", "rationale": "bad"}])
    state = FenrysGraph(registry(tmp_path), PrimaryReasoner(malformed)).run(CyberState("bad", "test"))
    assert malformed.calls == 1 and state.completed


def test_retry_state_is_checkpoint_safe(tmp_path: Path) -> None:
    database = tmp_path / "retry.sqlite"
    provider = SequenceProvider([LLMError("connection_failure", "down")])
    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider), saver)
        interrupted = graph.run(CyberState("checkpoint-retry", "test"), interrupt_after=["reason"])
        assert interrupted.provider_retry_count == 1
        assert interrupted.last_provider_error == "connection_failure"
    provider = SequenceProvider([{ "decision": "stop", "rationale": "recovered after resume" }])
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(registry(tmp_path), PrimaryReasoner(provider), saver).resume("checkpoint-retry")
    assert restored.completed and restored.provider_retry_count == 0
