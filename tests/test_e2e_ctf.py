from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from fenrys_cai.artifacts import LocalArtifactStore
from fenrys_cai.config import LoopConfig, RuntimeConfig
from fenrys_cai.graph import FenrysGraph
from fenrys_cai.hypotheses import HypothesisStatus, VerificationStatus
from fenrys_cai.llm.primary import PrimaryReasoner
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.specialists.fake_llm import CONTINUE_RESPONSE, FakeSpecialistLLM
from fenrys_cai.specialists.registry import build_router
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


FLAG = "FENRYS{LOCAL_E2E_VALIDATION}"
OBJECTIVE = "Solve the local challenge, identify relevant evidence, verify the hypothesis, and return the final flag."


def build_challenge(workspace: Path, session_id: str) -> Path:
    root = workspace / session_id
    target = root / "challenge" / "target"
    target.mkdir(parents=True)
    encoded = base64.b64encode(FLAG.encode()).decode()
    digest = hashlib.sha256(FLAG.encode()).hexdigest()
    (root / "challenge" / "README.md").write_text(
        "Local forensic challenge. Inspect target/manifest.json. The large noise file is misleading. "
        "Corroborate the encoded candidate against the expected SHA-256 before accepting a flag.\n",
        encoding="utf-8",
    )
    (target / "manifest.json").write_text(json.dumps({"candidate": "flag.b64", "sha256": digest, "noise": "noise.log"}), encoding="utf-8")
    (target / "flag.b64").write_text(encoded, encoding="utf-8")
    (target / "noise.log").write_text("DECOY-LINE\n" * 2000, encoding="utf-8")
    return root


class CTFProvider:
    """Deterministic LLM provider that reasons from bounded state, never mutating it."""
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict:
        self.calls += 1
        context = json.loads(user)["context"]
        attempts = context.get("attempts", [])
        hypotheses = context.get("hypotheses", [])
        history = context.get("history", [])

        if not attempts:
            return {"decision": "tool", "tool": "read_file", "arguments": {"path": "challenge/README.md", "session_id": "ctf"},
                    "rationale": "Inspect challenge instructions", "confidence": 0.8}
        if len(attempts) == 1:
            return {"decision": "tool", "tool": "read_file", "arguments": {"path": "challenge/target/manifest.json", "session_id": "ctf"},
                    "rationale": "Enumerate structured manifest", "confidence": 0.9}
        if len(attempts) == 2:
            return {"decision": "tool", "tool": "execute", "arguments": {"command": "cat challenge/target/noise.log", "session_id": "ctf"},
                    "rationale": "Inspect the referenced large artifact", "confidence": 0.5}
        if len(attempts) == 3 and not any(item.startswith("specialist:") for item in history):
            return {"decision": "specialist", "specialist": "forensics", "rationale": "Need forensic triage of conflicting clues", "confidence": 0.8}
        if not hypotheses:
            return {"decision": "hypothesis", "rationale": "Manifest identifies an encoded flag candidate with an independent digest", "confidence": 0.85,
                    "hypothesis": {"statement": "Decoding flag.b64 yields the final flag whose SHA-256 equals the manifest digest",
                                   "domain": "forensics", "required_evidence": ["decoded candidate", "matching SHA-256"]}}
        hypothesis_id = hypotheses[-1]["id"]
        hypothesis_attempts = [attempt for attempt in attempts if attempt.get("hypothesis_id") == hypothesis_id]
        if not hypothesis_attempts:
            return {"decision": "tool", "tool": "execute",
                    "arguments": {"command": "cat challenge/target/noise.log", "session_id": "ctf", "hypothesis_id": hypothesis_id},
                    "rationale": "Repeat prior noise inspection to ensure it was not missed", "confidence": 0.3}
        if len(hypothesis_attempts) == 1 and not any("Anti-loop blocked" in item for item in history):
            return {"decision": "tool", "tool": "execute",
                    "arguments": {"command": "cat challenge/target/noise.log", "session_id": "ctf", "hypothesis_id": hypothesis_id},
                    "rationale": "Repeat prior noise inspection to ensure it was not missed", "confidence": 0.3}
        if any("Anti-loop blocked" in item for item in history) and not any("flag.b64" in str(item.get("parameters")) for item in attempts):
            return {"decision": "tool", "tool": "read_file",
                    "arguments": {"path": "challenge/target/flag.b64", "session_id": "ctf", "hypothesis_id": hypothesis_id},
                    "rationale": "Pivot from blocked decoy repetition to the manifest candidate", "confidence": 0.9}
        if not any("python" in str(item.get("parameters")) for item in attempts):
            command = "python3 -c \"import base64,hashlib,json,pathlib; p=pathlib.Path('challenge/target'); f=base64.b64decode((p/'flag.b64').read_text()).decode(); print(json.dumps({'flag':f,'sha256':hashlib.sha256(f.encode()).hexdigest()}))\""
            return {"decision": "tool", "tool": "execute",
                    "arguments": {"command": command, "session_id": "ctf", "hypothesis_id": hypothesis_id},
                    "rationale": "Decode candidate and derive independent digest", "confidence": 0.95}
        evidence_id = context["evidence"][-1]["id"]
        if not context.get("verifications"):
            return {"decision": "verify", "rationale": "Verify exact decoded flag using tool evidence", "confidence": 1.0,
                    "verification": {"hypothesis_id": hypothesis_id, "method": "exact flag comparison",
                                     "expected_observation": {"type": "exact_text", "value": FLAG},
                                     "actual_observation": FLAG, "evidence_id": evidence_id}}
        return {"decision": "stop", "rationale": "Flag recovered and independently verified", "confidence": 1.0}


def diagnostics(state: CyberState) -> dict:
    return {
        "completed": state.completed,
        "history": state.history[-10:],
        "attempts": [(item.tool, item.result) for item in state.attempts],
        "dead_ends": [item.reason for item in state.dead_ends],
        "hypotheses": [(item.statement, item.status.value) for item in state.hypotheses],
        "verifications": [(item.status.value, item.actual_observation[:100]) for item in state.verifications],
        "evidence": [item.get("id") for item in state.evidence[-5:]],
        "artifacts": state.artifacts,
    }


def test_end_to_end_local_ctf_with_checkpoint_resume(tmp_path: Path) -> None:
    started = time.monotonic()
    workspace = tmp_path / "workspaces"
    build_challenge(workspace, "ctf")
    runtime = LocalTerminalRuntime(RuntimeConfig(workspace, max_output_bytes=2048, artifact_threshold_bytes=512))
    registry = ToolRegistry(runtime.artifact_store, spill_threshold=512)
    registry.register_provider(LocalProvider(runtime))
    provider = CTFProvider()
    specialist = FakeSpecialistLLM([CONTINUE_RESPONSE])
    router = build_router(Path("prompts/specialists"), decide=specialist)
    database = tmp_path / "ctf-checkpoint.sqlite"
    limits = LoopConfig(max_iterations=20, max_tool_calls=12, max_repeated_attempts=0,
                        max_anti_loop_reconsiderations=1, max_runtime_seconds=60)

    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = FenrysGraph(registry, PrimaryReasoner(provider), saver, router, limits)
        interrupted = graph.run(CyberState("ctf", OBJECTIVE), interrupt_after=["act"])
        assert len(interrupted.attempts) == 1, diagnostics(interrupted)
        assert not interrupted.completed

    with SqliteSaver.from_conn_string(str(database)) as saver:
        resumed_graph = FenrysGraph(registry, PrimaryReasoner(provider), saver, router, limits)
        state = resumed_graph.resume("ctf", max_steps=20)

    assert state.completed, diagnostics(state)
    assert state.verifications, diagnostics(state)
    assert FLAG in state.verifications[-1].actual_observation, diagnostics(state)
    assert state.verifications[-1].status == VerificationStatus.CONFIRMED, diagnostics(state)
    assert state.hypotheses[-1].status == HypothesisStatus.CONFIRMED, diagnostics(state)
    assert state.hypotheses[-1].test_attempts, diagnostics(state)
    assert state.hypotheses[-1].supporting_evidence or state.verifications[-1].supporting_evidence
    assert any(item.startswith("specialist:") for item in state.history), diagnostics(state)
    assert state.dead_ends and any("Anti-loop blocked" in item for item in state.history), diagnostics(state)
    noise_attempts = [item for item in state.attempts if "noise.log" in str(item.parameters)]
    assert len(noise_attempts) == 2  # first before hypothesis, second linked to a new hypothesis; third duplicate was blocked
    assert state.progress_markers, diagnostics(state)
    spilled = next(item for item in state.artifacts if item.startswith("art_"))
    assert runtime.artifact_store.exists(spilled), diagnostics(state)
    assert runtime.artifact_store.metadata(spilled).size >= 2048
    assert state.iteration_count <= limits.max_iterations
    assert state.tool_call_count <= limits.max_tool_calls
    assert time.monotonic() - started < limits.max_runtime_seconds
    checkpoint_size = database.stat().st_size
    assert checkpoint_size > 0
    serialized = json.dumps(state.export())
    assert "OPENAI_API_KEY" not in serialized and "ANTHROPIC_AUTH_TOKEN" not in serialized
