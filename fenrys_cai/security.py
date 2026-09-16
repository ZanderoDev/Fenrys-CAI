from __future__ import annotations

import re
from typing import Any


class Redactor:
    """Central secret redaction for text, mappings, environments, and errors."""

    _SECRET_KEYS = re.compile(r"(?:api[_-]?key|authorization|password|passwd|token|secret|credential|cookie)", re.I)
    _PATTERNS = (
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
        re.compile(r"(?i)((?:api[_-]?key|password|token|secret)\s*[=:]\s*)[^\s,;]+"),
    )

    def __init__(self, extra_patterns: tuple[str, ...] = ()) -> None:
        self.patterns = self._PATTERNS + tuple(re.compile(item) for item in extra_patterns)

    def redact_text(self, value: Any) -> str:
        text = "" if value is None else str(value)
        for pattern in self.patterns:
            text = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", text)
        return text

    def redact_mapping(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: "[REDACTED]" if self._SECRET_KEYS.search(str(key)) else self.redact_mapping(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_mapping(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_mapping(item) for item in value)
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def redact_environment(self, environment: dict[str, str], explicitly_allowed: set[str] | None = None) -> dict[str, str]:
        allowed = explicitly_allowed or set()
        return {key: value for key, value in environment.items() if key in allowed or not self._SECRET_KEYS.search(key)}

    def redact_exception(self, exc: BaseException) -> str:
        return self.redact_text(exc)


DEFAULT_REDACTOR = Redactor()
