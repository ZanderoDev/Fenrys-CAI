import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .hypotheses import Hypothesis, HypothesisEngine, Verification
from .models import Attempt, DeadEnd, ToolResult
from .security import DEFAULT_REDACTOR
from .targets import Endpoint, Host, Service, upsert_by_identity


@dataclass
class CyberState:
    session_id: str
    goal: str
    scope: str = "authorized CTF/lab only"
    phase: str = "RECON"
    findings: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    verifications: list[Verification] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    completed: bool = False
    dead_ends: list[DeadEnd] = field(default_factory=list)
    iteration_count: int = 0
    tool_call_count: int = 0
    started_at: float = field(default_factory=__import__("time").time)
    progress_markers: list[str] = field(default_factory=list)
    anti_loop_reconsiderations: int = 0
    provider_retry_count: int = 0
    last_provider_error: str = ""
    hosts: list[Host] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.hypotheses = [item if isinstance(item, Hypothesis) else Hypothesis.from_dict(item) for item in self.hypotheses]
        self.verifications = [item if isinstance(item, Verification) else Verification.from_dict(item) for item in self.verifications]
        self.dead_ends = [item if isinstance(item, DeadEnd) else DeadEnd(**item) for item in self.dead_ends]
        self.hosts = [item if isinstance(item, Host) else Host(**item) for item in self.hosts]
        self.services = [item if isinstance(item, Service) else Service(**item) for item in self.services]
        self.endpoints = [item if isinstance(item, Endpoint) else Endpoint(**item) for item in self.endpoints]

    def can_attempt(self, attempt: Attempt, new_evidence: bool = False) -> bool:
        if new_evidence or (attempt.progress_token and attempt.progress_token not in {item.progress_token for item in self.attempts}):
            return True
        return not any(item.fingerprint == attempt.fingerprint for item in self.attempts)

    def observe(self, result: ToolResult) -> None:
        digest = hashlib.sha256(json.dumps(result.to_dict(), sort_keys=True).encode()).hexdigest()
        self.evidence.append({"id": digest, "tool": result.tool, "status": result.status, "provenance": result.provenance})
        self.artifacts.extend(result.artifacts)
        self.history.append(f"{result.tool}: {result.status}")

    def progress_signature(self) -> str:
        data = {
            "evidence": sorted({(item.get("tool"), item.get("status"), (item.get("provenance") or {}).get("provider")) for item in self.evidence}), "artifacts": sorted(set(self.artifacts)),
            "findings": self.findings, "hypotheses": [(item.id, item.status.value) for item in self.hypotheses],
            "verifications": [(item.id, item.status.value) for item in self.verifications],
            "hosts": [(item.address, item.status) for item in self.hosts],
            "services": [(item.host_id, item.port, item.protocol, item.service) for item in self.services],
            "endpoints": [(item.url, item.method) for item in self.endpoints], "technologies": sorted(self.technologies),
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def upsert_host(self, host: Host) -> None: upsert_by_identity(self.hosts, host, lambda item: item.address)
    def upsert_service(self, service: Service) -> None: upsert_by_identity(self.services, service, lambda item: (item.host_id, item.port, item.protocol))
    def upsert_endpoint(self, endpoint: Endpoint) -> None: upsert_by_identity(self.endpoints, endpoint, lambda item: (item.method, item.url))

    def add_hypothesis(self, hypothesis: Hypothesis, limit: int = 100) -> None:
        if any(item.id == hypothesis.id for item in self.hypotheses):
            raise ValueError(f"Duplicate hypothesis ID: {hypothesis.id}")
        self.hypotheses.append(hypothesis)
        del self.hypotheses[:-limit]

    def add_verification(self, verification: Verification, limit: int = 100) -> None:
        if not any(item.id == verification.hypothesis_id for item in self.hypotheses):
            raise ValueError(f"Unknown hypothesis ID: {verification.hypothesis_id}")
        self.verifications.append(verification)
        del self.verifications[:-limit]

    def hypothesis(self, hypothesis_id: str) -> Hypothesis:
        try:
            return next(item for item in self.hypotheses if item.id == hypothesis_id)
        except StopIteration as exc:
            raise ValueError(f"Unknown hypothesis ID: {hypothesis_id}") from exc

    def export(self) -> dict[str, Any]:
        output = asdict(self)
        output["attempts"] = [asdict(item) for item in self.attempts]
        output["hypotheses"] = [item.to_dict() for item in self.hypotheses]
        output["verifications"] = [item.to_dict() for item in self.verifications]
        output["dead_ends"] = [asdict(item) for item in self.dead_ends]
        return DEFAULT_REDACTOR.redact_mapping(output)


class CheckpointStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
    def save(self, state: CyberState) -> Path:
        path = self.directory / f"{state.session_id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state.export(), indent=2), encoding="utf-8")
        temporary.replace(path)
        return path
    def load(self, session_id: str) -> CyberState:
        data = json.loads((self.directory / f"{session_id}.json").read_text(encoding="utf-8"))
        data["attempts"] = [Attempt(**item) for item in data.get("attempts", [])]
        return CyberState(**data)
