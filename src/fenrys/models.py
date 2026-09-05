from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SessionMode(StrEnum):
    NORMAL = "NORMAL"
    CTF = "CTF"
    LAB = "LAB"
    AUTHORIZED_PENTEST = "AUTHORIZED_PENTEST"


class EvidenceStatus(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"
    VERIFIED = "VERIFIED"
    DISPROVED = "DISPROVED"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Message:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    required_parameters: list[str] = field(default_factory=list)
    failure_behavior: str = "return normalized failure"
    output_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelResponse:
    content: str
    model: str
    provider: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderHealth:
    ok: bool
    provider: str
    latency_ms: int | None = None
    supports_tools: bool = False
    reason: str = ""


@dataclass(slots=True)
class NormalizedToolResult:
    tool: str
    success: bool
    duration_ms: int
    summary: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    raw_output_path: str | None = None
    exit_code: int | None = None
    error: str | None = None
