from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fenrys_cai.llm.provider import LLMError, LLMProvider
from fenrys_cai.models import ToolSpec
from fenrys_cai.state import CyberState

_VALID_DOMAINS = frozenset({"recon", "network", "web", "api", "credentials", "pwn", "reverse", "crypto", "forensics", "privesc", "verification"})
_VALID_DECISIONS = frozenset({"tool", "specialist", "hypothesis", "verify", "continue", "stop"})


@dataclass(frozen=True)
class PrimaryDecision:
    """Validated primary reasoning decision.

    Supports both the new kind-based API and the legacy tool/complete API:
      PrimaryDecision("tool", "rationale", tool="execute", arguments={...})
      PrimaryDecision("execute", {"command": "pwd"}, "rationale")  # legacy
      PrimaryDecision(complete=True, rationale="done")             # legacy
    """
    kind: str
    rationale: str
    confidence: float = 0.5
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    specialist: str | None = None
    complete: bool = False
    hypothesis: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None

    def __init__(self, kind_or_tool: str = "continue", rationale_or_arguments: str | dict | None = None,
                 rationale_or_confidence: str | float = 0.5, confidence: float = 0.5,
                 tool: str | None = None, arguments: dict[str, Any] | None = None,
                 specialist: str | None = None, complete: bool = False, rationale: str | None = None,
                 hypothesis: dict[str, Any] | None = None, verification: dict[str, Any] | None = None) -> None:
        # Handle explicit rationale keyword
        if rationale is not None:
            rationale_or_arguments = rationale
        # Legacy positional: Decision("execute", {"command": "pwd"}, "rationale")
        if isinstance(rationale_or_arguments, dict) and isinstance(rationale_or_confidence, str):
            object.__setattr__(self, "kind", "tool")
            object.__setattr__(self, "tool", kind_or_tool)
            object.__setattr__(self, "arguments", rationale_or_arguments)
            object.__setattr__(self, "rationale", rationale_or_confidence)
            object.__setattr__(self, "confidence", confidence)
            object.__setattr__(self, "specialist", specialist)
            object.__setattr__(self, "complete", complete)
            object.__setattr__(self, "hypothesis", hypothesis)
            object.__setattr__(self, "verification", verification)
            return
        # Legacy keyword: Decision(complete=True, rationale="done")
        if complete and kind_or_tool == "continue":
            object.__setattr__(self, "kind", "stop")
            object.__setattr__(self, "tool", tool)
            object.__setattr__(self, "arguments", arguments)
            object.__setattr__(self, "rationale", str(rationale_or_arguments or ""))
            object.__setattr__(self, "confidence", confidence)
            object.__setattr__(self, "specialist", specialist)
            object.__setattr__(self, "complete", True)
            object.__setattr__(self, "hypothesis", hypothesis)
            object.__setattr__(self, "verification", verification)
            return
        # New API: PrimaryDecision("tool", "rationale", tool="execute", arguments={...})
        object.__setattr__(self, "kind", kind_or_tool)
        object.__setattr__(self, "tool", tool)
        object.__setattr__(self, "arguments", arguments)
        object.__setattr__(self, "rationale", str(rationale_or_arguments or ""))
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "specialist", specialist)
        object.__setattr__(self, "complete", complete)
        object.__setattr__(self, "hypothesis", hypothesis)
        object.__setattr__(self, "verification", verification)


def _bounded_tools(tools: list[ToolSpec], limit: int = 15) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool in tools[:limit]:
        schema_summary = ""
        if isinstance(tool.input_schema, dict):
            props = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            schema_summary = f"required={required} props={list(props)[:8]}"
        result.append({"name": tool.name, "description": tool.description[:200], "provider": tool.provider,
                       "capabilities": list(tool.capabilities), "schema_summary": schema_summary})
    return result


def _bounded_context(state: CyberState, max_items: int = 5) -> dict[str, Any]:
    return {
        "session_id": state.session_id,
        "goal": state.goal,
        "scope": state.scope,
        "phase": state.phase,
        "findings": state.findings[-max_items:],
        "hypotheses": [item.to_dict() for item in state.hypotheses[-max_items:]],
        "verifications": [item.to_dict() for item in state.verifications[-max_items:]],
        "attempts": [{"id": a.id, "tool": a.tool, "target": a.target, "parameters": a.parameters,
                      "result": a.result, "strategy": a.strategy, "hypothesis_id": a.hypothesis_id,
                      "evidence_references": a.evidence_references} for a in state.attempts[-max_items:]],
        "evidence": state.evidence[-max_items:],
        "artifacts": state.artifacts[-max_items:],
        "history": state.history[-10:],
    }


def validate_primary_decision(data: dict[str, Any], available_tools: set[str]) -> PrimaryDecision:
    """Strictly validate LLM response into PrimaryDecision. Raises LLMError on any issue."""
    if not isinstance(data, dict):
        raise LLMError("malformed_response", "Primary LLM response is not a JSON object")
    kind = data.get("decision")
    if not kind or not isinstance(kind, str):
        raise LLMError("missing_decision", "Primary LLM response missing 'decision'")
    if kind not in _VALID_DECISIONS:
        raise LLMError("invalid_decision", f"Invalid primary decision: {kind!r}")
    rationale = str(data.get("rationale", ""))
    confidence = data.get("confidence", 0.5)
    if not isinstance(confidence, (int, float)):
        confidence = 0.5
    confidence = max(0.0, min(1.0, float(confidence)))

    if kind == "tool":
        tool = data.get("tool")
        if not tool or not isinstance(tool, str):
            raise LLMError("invalid_tool_call", "Tool decision missing 'tool' name")
        if available_tools and tool not in available_tools:
            raise LLMError("invalid_tool_call", f"Tool {tool!r} not in available tools")
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            raise LLMError("invalid_tool_call", "Tool arguments must be a JSON object")
        return PrimaryDecision("tool", rationale, confidence, tool=tool, arguments=arguments)

    if kind == "specialist":
        specialist = data.get("specialist")
        if not specialist or not isinstance(specialist, str):
            raise LLMError("invalid_specialist", "Specialist decision missing 'specialist' domain")
        if specialist not in _VALID_DOMAINS:
            raise LLMError("invalid_specialist", f"Invalid specialist domain: {specialist!r}")
        return PrimaryDecision("specialist", rationale, confidence, specialist=specialist)

    if kind == "hypothesis":
        proposal = data.get("hypothesis")
        if not isinstance(proposal, dict) or not {"statement", "domain", "required_evidence"}.issubset(proposal):
            raise LLMError("invalid_hypothesis", "Hypothesis requires statement, domain, and required_evidence")
        if not isinstance(proposal["required_evidence"], list):
            raise LLMError("invalid_hypothesis", "Hypothesis required_evidence must be a list")
        return PrimaryDecision("hypothesis", rationale, confidence, hypothesis=proposal)

    if kind == "verify":
        verification = data.get("verification")
        if not isinstance(verification, dict) or not {"hypothesis_id", "method", "expected_observation"}.issubset(verification):
            raise LLMError("invalid_verification", "Verify decision requires hypothesis_id, method, and expected_observation")
        return PrimaryDecision("verify", rationale, confidence, verification=verification)

    if kind == "stop":
        return PrimaryDecision("stop", rationale, confidence, complete=True)

    return PrimaryDecision("continue", rationale, confidence)


class PrimaryReasoner:
    """Primary LLM reasoning node using the unified LLMProvider."""

    def __init__(self, provider: LLMProvider | None = None, prompt_path: Path | None = None) -> None:
        self.provider = provider or LLMProvider()
        self.prompt_path = prompt_path or Path("prompts/primary.md")

    @property
    def prompt(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return "You are the Fenrys-CAI primary reasoning agent. Respond with ONLY valid JSON."

    def decide(self, state: CyberState, tools: list[Any]) -> PrimaryDecision:
        system = self.prompt
        context = _bounded_context(state)
        user = json.dumps({
            "context": context,
            "available_tools": _bounded_tools(tools),
            "valid_specialist_domains": sorted(_VALID_DOMAINS),
            "lifecycle_decisions": ["hypothesis", "verify"],
        }, default=str, ensure_ascii=False)
        data = self.provider.complete_json(system, user)
        available = {tool.name for tool in tools}
        return validate_primary_decision(data, available)
