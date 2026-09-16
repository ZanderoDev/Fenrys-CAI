from dataclasses import asdict, dataclass, field
from typing import Any, Literal
import time
import uuid

Status = Literal["success", "error", "timeout", "running", "terminated"]


@dataclass
class ToolResult:
    status: Status
    tool: str
    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex}")
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    cwd: str = ""
    duration_ms: int = 0
    process_id: str | None = None
    artifacts: list[str] = field(default_factory=list)
    artifact_metadata: list[dict[str, Any]] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    error: str | None = None
    provenance: dict[str, Any] = field(default_factory=lambda: {"timestamp": time.time()})

    def to_dict(self) -> dict[str, Any]:
        from .security import DEFAULT_REDACTOR
        return DEFAULT_REDACTOR.redact_mapping(asdict(self))


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    capabilities: tuple[str, ...] = ()
    target_types: tuple[str, ...] = ()
    provider: str = "local"
    execution_mode: str = "sync"
    risk: str = "operator-controlled"


@dataclass
class Attempt:
    objective: str
    target: str
    tool: str
    parameters: dict[str, Any]
    strategy: str
    result: str
    timestamp: float = field(default_factory=time.time)
    hypothesis_id: str | None = None
    id: str = field(default_factory=lambda: f"att_{uuid.uuid4().hex}")
    evidence_references: list[str] = field(default_factory=list)
    progress_token: str = ""

    @property
    def fingerprint(self) -> str:
        import hashlib
        import json
        data = {"objective": self.objective.strip().lower(), "target": self.target.strip().lower(), "tool": self.tool,
                "parameters": self._normalize(self.parameters), "strategy": " ".join(self.strategy.lower().split()),
                "hypothesis_id": self.hypothesis_id}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def _normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: Attempt._normalize(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [Attempt._normalize(item) for item in value]
        if isinstance(value, str):
            return " ".join(value.split())
        return value


@dataclass
class DeadEnd:
    objective: str
    target: str
    reason: str
    blocked_attempts: list[str]
    relevant_evidence: list[str]
    hypotheses: list[str]
    suggested_alternatives: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: f"dead_{uuid.uuid4().hex}")
    timestamp: float = field(default_factory=time.time)
