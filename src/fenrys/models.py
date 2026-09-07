from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator


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
    finish_reason: str = ""


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


@dataclass(slots=True)
class ModelStreamChunk:
    """A single chunk from a streaming LLM response."""
    content: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


TURN_EXHAUSTED_MARKER = "[dihentikan: batas turn tercapai]"


_MALFORMED_ARGS_KEY = "__malformed_args__"


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Tolerant JSON-object parse.

    Accepts a complete object even when trailing garbage follows (some relays
    append notes after the JSON). Returns None when no valid object exists.
    """
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw.lstrip())
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Split a raw tool call into (name, arguments). Single shared helper.

    Malformed (typically output-truncated) JSON is NOT silently turned into an
    empty dict — that would make the upstream tool reply with a confusing
    "field is required" 400. Instead it is surfaced under _MALFORMED_ARGS_KEY so
    handlers can tell the model the tool-call was cut and to retry concisely.
    """
    function = call.get("function") or {}
    name = call.get("name") or function.get("name") or ""
    arguments = call.get("arguments") or function.get("arguments") or {}
    if isinstance(arguments, str):
        if arguments.strip():
            parsed = _parse_json_object(arguments)
            if parsed is not None:
                return str(name), parsed
            return str(name), {_MALFORMED_ARGS_KEY: arguments[:300]}
        arguments = {}
    return str(name), arguments if isinstance(arguments, dict) else {}
