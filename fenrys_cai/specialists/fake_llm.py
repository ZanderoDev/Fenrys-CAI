"""Deterministic fake LLM provider for testing specialist reasoning."""

from __future__ import annotations

import json
from typing import Any

from .base import SpecialistDecision, SpecialistRequest
from .llm_decision import _validate_decision, _VALID_DOMAINS


class FakeSpecialistLLM:
    """Deterministic specialist decision builder for tests."""

    def __init__(self, responses: list[dict[str, Any]] | None = None, default: dict[str, Any] | None = None) -> None:
        self._responses = list(responses or [])
        self._default = default or {"decision": "continue", "rationale": "fake default", "confidence": 0.5}
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: SpecialistRequest, prompt: str) -> SpecialistDecision:
        self.calls.append({
            "domain": request.domain,
            "objective": request.objective,
            "prompt_length": len(prompt),
            "tool_count": len(request.tools),
            "context_keys": sorted(request.context.keys()),
        })
        if self._responses:
            data = self._responses.pop(0)
        else:
            data = self._default
        available = {tool.name for tool in request.tools}
        return _validate_decision(data, available)


class FakeSpecialistLLMError(FakeSpecialistLLM):
    """Fake that raises structured errors."""

    def __init__(self, error_code: str, error_message: str) -> None:
        super().__init__()
        self._error_code = error_code
        self._error_message = error_message

    def __call__(self, request: SpecialistRequest, prompt: str) -> SpecialistDecision:
        from .llm_decision import SpecialistLLMError
        raise SpecialistLLMError(self._error_code, self._error_message)


# Pre-built fake responses for common test scenarios
TOOL_RESPONSE = {"decision": "tool", "rationale": "run execute for baseline", "tool": "execute", "arguments": {"command": "pwd", "session_id": "test"}, "confidence": 0.7}
DELEGATE_RESPONSE = {"decision": "delegate", "rationale": "needs crypto review", "delegate_to": "crypto", "confidence": 0.6}
STOP_RESPONSE = {"decision": "stop", "rationale": "no further action justified", "confidence": 0.9}
CONTINUE_RESPONSE = {"decision": "continue", "rationale": "reviewing evidence", "confidence": 0.5}
MALFORMED_RESPONSE = {"decision": "invalid_kind", "rationale": "bad"}
MISSING_DECISION_RESPONSE = {"rationale": "no decision field"}
INVALID_TOOL_RESPONSE = {"decision": "tool", "rationale": "bad tool", "tool": "nonexistent_tool", "arguments": {}}
INVALID_DOMAIN_RESPONSE = {"decision": "delegate", "rationale": "bad domain", "delegate_to": "not_a_domain"}
