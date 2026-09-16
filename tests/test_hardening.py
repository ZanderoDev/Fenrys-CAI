from pathlib import Path
import json
import os
import time
import zipfile

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from fenrys_cai.archives import safe_extract_zip
from fenrys_cai.artifacts import LocalArtifactStore
from fenrys_cai.config import LoopConfig, RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.llm.provider import LLMError
from fenrys_cai.llm.verification import LLMVerifier
from fenrys_cai.models import Attempt, ToolResult
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.security import DEFAULT_REDACTOR
from fenrys_cai.state import CyberState
from fenrys_cai.targets import Endpoint, Host, Service
from fenrys_cai.tools import LocalProvider, ToolRegistry


def test_artifact_store_metadata_digest_bounded_read_and_traversal(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts", max_artifact_bytes=1024)
    artifact = store.save(b"hello world", kind="test", name="result.txt", content_type="text/plain", tool="test")
    assert store.exists(artifact.id)
    assert artifact.sha256 == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert store.read(artifact.id, 6, 5) == b"world"
    assert store.metadata(artifact.id).size == 11
    with pytest.raises(ValueError): store.read("../../etc/passwd")
    with pytest.raises(ValueError): store.read(artifact.id, limit=2 * 1024 * 1024)


def test_runtime_large_output_spills_to_artifact(tmp_path: Path) -> None:
    runtime = LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace", max_output_bytes=1024, artifact_threshold_bytes=32))
    result = runtime.execute("printf '%0100d' 0", "spill")
    assert result.status == "success"
    assert result.artifacts and result.artifact_metadata
    artifact_id = result.artifacts[0]
    assert runtime.artifact_store.exists(artifact_id)
    assert len(runtime.artifact_store.read(artifact_id, limit=200)) == 100


def test_artifact_reference_survives_checkpoint(tmp_path: Path) -> None:
    state = CyberState("artifact", "persist", artifacts=["art_" + "a" * 32], completed=True)
    database = tmp_path / "state.sqlite"
    class Stop: 
        def decide(self, state, tools): return Decision("stop", "done", complete=True)
    with SqliteSaver.from_conn_string(str(database)) as saver:
        FenrysGraph(ToolRegistry(), Stop(), saver).run(state)
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restored = FenrysGraph(ToolRegistry(), Stop(), saver).resume("artifact")
    assert restored.artifacts == state.artifacts


def test_redactor_text_nested_mapping_environment_and_exception() -> None:
    secret = "synthetic-secret-123"
    assert secret not in DEFAULT_REDACTOR.redact_text(f"Authorization: Bearer {secret}")
    redacted = DEFAULT_REDACTOR.redact_mapping({"password": secret, "nested": {"api_key": secret}, "safe": "ok"})
    assert secret not in json.dumps(redacted)
    assert "SAFE_VALUE" in DEFAULT_REDACTOR.redact_environment({"PASSWORD": secret, "SAFE": "SAFE_VALUE"}).values()
    assert secret not in DEFAULT_REDACTOR.redact_exception(RuntimeError(f"token={secret}"))


def test_state_and_tool_result_serialization_redacts_secrets() -> None:
    secret = "synthetic-secret-456"
    result = ToolResult(status="error", tool="x", stderr=f"password={secret}", provenance={"Authorization": secret})
    assert secret not in json.dumps(result.to_dict())
    state = CyberState("redact", "goal", evidence=[{"id": "e", "provenance": {"token": secret}}])
    assert secret not in json.dumps(state.export())


def test_background_process_identity_recovery_and_stale_pid(tmp_path: Path) -> None:
    runtime = LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))
    started = runtime.execute("sleep 5", "recovery", background=True)
    record = runtime.process_record(started.process_id)
    assert runtime.recover_process(record) == "running"
    stale = dict(record, pid=99999999)
    assert runtime.recover_process(stale) == "disappeared"
    unrelated = dict(record, pid=os.getpid())
    assert runtime.recover_process(unrelated) == "disappeared"
    runtime.terminate(started.process_id)


def test_typed_target_upserts_preserve_evidence_and_checkpoint(tmp_path: Path) -> None:
    state = CyberState("targets", "map local")
    host = Host("127.0.0.1", evidence=["ev1"])
    state.upsert_host(host)
    state.upsert_host(Host("127.0.0.1", hostname="localhost", evidence=["ev2"]))
    state.upsert_service(Service(host.id, 8080, service="http", evidence=["ev3"]))
    state.upsert_service(Service(host.id, 8080, version="test", evidence=["ev4"]))
    state.upsert_endpoint(Endpoint("http://127.0.0.1:8080/", host_id=host.id, evidence=["ev5"]))
    state.upsert_endpoint(Endpoint("http://127.0.0.1:8080/", status_observation=200, evidence=["ev6"]))
    assert len(state.hosts) == len(state.services) == len(state.endpoints) == 1
    assert state.hosts[0].evidence == ["ev1", "ev2"]
    assert state.services[0].evidence == ["ev3", "ev4"]
    restored = CyberState(**state.export())
    assert restored.services[0].version == "test"
    assert restored.endpoints[0].status_observation == 200


class FakeVerifierProvider:
    def __init__(self, response=None, error=None): self.response, self.error = response, error
    def complete_json(self, system, user, *, max_tokens=1024):
        if self.error: raise self.error
        return self.response


def test_llm_verification_fallback_and_guardrails() -> None:
    verifier = LLMVerifier(FakeVerifierProvider({"decision": "inconclusive", "confidence": 0.4, "rationale": "ambiguous"}))
    decision = verifier.verify(hypothesis={"statement": "x"}, expected="semantic claim", actual="bounded evidence",
                               evidence_ids=["ev1"], existing_evidence_ids={"ev1"})
    assert decision.decision == "inconclusive"
    with pytest.raises(LLMError, match="nonexistent"):
        verifier.verify(hypothesis={}, expected="x", actual="y", evidence_ids=["fake"], existing_evidence_ids=set())
    malformed = LLMVerifier(FakeVerifierProvider({"decision": "yes", "confidence": 1, "rationale": "bad"}))
    with pytest.raises(LLMError, match="Invalid"):
        malformed.verify(hypothesis={}, expected="x", actual="y", evidence_ids=[], existing_evidence_ids=set())


@pytest.mark.parametrize("executions", [1, 2, 3])
def test_repeated_actions_are_not_limited(tmp_path: Path, executions: int) -> None:
    class Repeat:
        def __init__(self): self.calls = 0
        def decide(self, state, tools):
            self.calls += 1
            if self.calls > executions:
                return Decision("stop", "done", complete=True)
            return Decision("execute", {"command": "pwd", "session_id": f"repeat-{executions}"}, "same strategy")
    reasoner = Repeat()
    registry = ToolRegistry()
    registry.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / f"workspace-{executions}"))))
    state = FenrysGraph(registry, reasoner).run(CyberState(f"repeat-{executions}", "goal"))
    assert len(state.attempts) == executions
    assert not state.dead_ends


def test_safe_archive_rejects_traversal_symlink_and_limits(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive: archive.writestr("../escape", "bad")
    with pytest.raises(ValueError, match="Unsafe"): safe_extract_zip(traversal, tmp_path / "out")
    oversized = tmp_path / "oversized.zip"
    with zipfile.ZipFile(oversized, "w") as archive: archive.writestr("large", "x" * 100)
    with pytest.raises(ValueError, match="limits"): safe_extract_zip(oversized, tmp_path / "out2", max_bytes=10)


def test_workspace_symlink_escape_rejected(tmp_path: Path) -> None:
    runtime = LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))
    provider = LocalProvider(runtime)
    session = runtime.session("symlink")
    (session.cwd / "escape").symlink_to(tmp_path)
    result = provider.invoke("read_file", {"path": "escape/outside", "session_id": "symlink"})
    assert result.status == "error"
    assert "outside" in result.error.lower()
