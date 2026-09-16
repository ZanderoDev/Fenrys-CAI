from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MatchResult:
    matched: bool | None
    observation: str


def _json_path(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def match_observation(expected: dict[str, Any], actual: Any) -> MatchResult:
    """Evaluate only explicitly configured evidence semantics."""
    kind = expected.get("type")
    try:
        if kind == "exact_text":
            return MatchResult(str(actual) == str(expected["value"]), str(actual)[:2000])
        if kind == "substring":
            return MatchResult(str(expected["value"]) in str(actual), str(actual)[:2000])
        if kind == "regex":
            return MatchResult(bool(re.search(str(expected["pattern"]), str(actual))), str(actual)[:2000])
        if kind in {"json_field_exists", "json_field_equals", "numeric_compare"}:
            value = json.loads(actual) if isinstance(actual, str) else actual
            exists, selected = _json_path(value, str(expected["path"]))
            if kind == "json_field_exists":
                return MatchResult(exists, repr(selected)[:2000])
            if not exists:
                return MatchResult(False, "field missing")
            if kind == "json_field_equals":
                return MatchResult(selected == expected.get("value"), repr(selected)[:2000])
            op, target = expected.get("operator"), float(expected["value"])
            number = float(selected)
            comparisons = {"eq": number == target, "gt": number > target, "gte": number >= target, "lt": number < target, "lte": number <= target}
            return MatchResult(comparisons.get(op), repr(selected))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, re.error):
        return MatchResult(None, "matcher could not evaluate observation")
    return MatchResult(None, "unsupported matcher")
