from __future__ import annotations

import json
from typing import Any

from .base import SpecialistDecision, SpecialistRequest
from fenrys_cai.llm.provider import LLMError, LLMProvider

_VALID_DOMAINS = frozenset({"recon", "network", "web", "api", "credentials", "pwn", "reverse", "crypto", "forensics", "privesc", "verification"})
_VALID_KINDS = frozenset({"continue", "tool", "delegate", "stop"})


class SpecialistLLMError(LLMError):
    """Backward-compatible structured specialist LLM failure."""


def _bounded_tools(tools: tuple, limit: int = 15) -> list[dict[str, Any]]:
    """Bounded capability representation for specialist prompts."""
    result: list[dict[str, Any]] = []
    for tool in tools[:limit]:
        schema_summary = ""
        if isinstance(tool.input_schema, dict):
            props = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            schema_summary = f"required={required} props={list(props)[:8]}"
        result.append({"name": tool.name, "description": tool.description[:200], "provider": tool.provider, "capabilities": list(tool.capabilities), "schema_summary": schema_summary})
    return result


def _build_messages(request: SpecialistRequest, prompt: str) -> list[dict[str, str]]:
    """Build ChatRequest-compatible messages from specialist context."""
    system = (
        f"{prompt}\n\n"
        "You must respond with ONLY valid JSON matching this schema:\n"
        '{"decision": "continue"|"tool"|"delegate"|"stop", "rationale": "...", "confidence": 0.0-1.0}\n'
        "For tool: add \"tool\": \"name\" and \"arguments\": {...} — tool name must be from the available tools list.\n"
        "For delegate: add \"delegate_to\": \"domain\" — must be one of the 11 specialist domains.\n"
        "For stop: no additional fields needed.\n"
        "For continue: no additional fields needed.\n"
        "Do not include markdown fences or extra text."
    )
    context = {
        "domain": request.domain,
        "objective": request.objective,
        "scope": request.scope,
        "phase": request.phase,
        "depth": request.depth,
        "context": request.context,
        "available_tools": _bounded_tools(request.tools),
        "valid_domains": sorted(_VALID_DOMAINS),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(context, default=str, ensure_ascii=False)},
    ]


def _validate_decision(data: dict[str, Any], available_tools: set[str]) -> SpecialistDecision:
    """Strictly validate LLM response into SpecialistDecision. Raises SpecialistLLMError on any issue."""
    if not isinstance(data, dict):
        raise SpecialistLLMError("malformed_response", "LLM response is not a JSON object")
    decision_type = data.get("decision")
    if not decision_type or not isinstance(decision_type, str):
        raise SpecialistLLMError("missing_decision", "LLM response missing 'decision' field")
    if decision_type not in _VALID_KINDS:
        raise SpecialistLLMError("invalid_decision", f"Invalid decision type: {decision_type!r}")
    rationale = data.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = str(rationale)
    confidence = data.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    if decision_type == "tool":
        tool = data.get("tool")
        if not tool or not isinstance(tool, str):
            raise SpecialistLLMError("invalid_tool_call", "Tool decision missing 'tool' name")
        if available_tools and tool not in available_tools:
            raise SpecialistLLMError("invalid_tool_call", f"Tool {tool!r} not in available tools")
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            raise SpecialistLLMError("invalid_tool_call", "Tool arguments must be a JSON object")
        return SpecialistDecision("tool", rationale, tool, arguments, confidence=confidence)

    if decision_type == "delegate":
        delegate_to = data.get("delegate_to")
        if not delegate_to or not isinstance(delegate_to, str):
            raise SpecialistLLMError("invalid_delegation", "Delegate decision missing 'delegate_to'")
        if delegate_to not in _VALID_DOMAINS:
            raise SpecialistLLMError("invalid_delegation", f"Invalid specialist domain: {delegate_to!r}")
        return SpecialistDecision("delegate", rationale, delegate_to=delegate_to, confidence=confidence)

    if decision_type == "stop":
        return SpecialistDecision("stop", rationale, confidence=confidence, verification_needed=bool(data.get("verification_needed", False)))

    return SpecialistDecision("continue", rationale, confidence=confidence)


class LLMSpecialistDecisionBuilder:
    """Uses the existing provider-neutral LLM interface for specialist reasoning."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None, model: str | None = None, timeout: float = 30.0, provider: LLMProvider | None = None) -> None:
        self.provider = provider or LLMProvider(endpoint, api_key, model, timeout)

    def __call__(self, request: SpecialistRequest, prompt: str) -> SpecialistDecision:
        messages = _build_messages(request, prompt)
        try:
            data = self.provider.complete_json(messages[0]["content"], messages[1]["content"])
        except LLMError as exc:
            raise SpecialistLLMError(exc.code, str(exc)) from exc

        available = {tool.name for tool in request.tools}
        return _validate_decision(data, available)
