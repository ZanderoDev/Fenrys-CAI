from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from fenrys.models import EvidenceStatus, NormalizedToolResult
from fenrys.state.store import StateStore


DEFAULT_FLAG_PATTERNS = [r"flag\{[^}]{3,200}\}", r"FLAG\{[^}]{3,200}\}"]
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all|any|previous)\s+instructions", re.I),
    re.compile(r"system\s+message\s*:", re.I),
    re.compile(r"you\s+are\s+now\s+(an?\s+)?assistant", re.I),
    re.compile(r"execute\s+this\s+command", re.I),
]


class EvidenceManager:
    def __init__(self, store: StateStore, raw_dir: str | Path, flag_patterns: list[str] | None = None):
        self.store = store
        self.raw_dir = Path(raw_dir).expanduser()
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.flag_patterns = [re.compile(pattern) for pattern in (flag_patterns or DEFAULT_FLAG_PATTERNS)]

    def wrap_untrusted(self, tool: str, output: str) -> str:
        # Netralkan forged close tag agar output model tidak bisa mengakhiri
        # blok <tool_output> lebih awal dan menyisipkan instruksi palsu.
        safe = output.replace("</tool_output>", "[forged-close-tag removed]")
        return f'<tool_output tool="{tool}" trust="untrusted">\n{safe}\n</tool_output>'

    def detect_injection(self, output: str) -> bool:
        return any(pattern.search(output) for pattern in INJECTION_PATTERNS)

    def normalize(self, tool: str, output: str, success: bool, duration_ms: int,
                  session_id: str | None = None, exit_code: int | None = None,
                  error: str | None = None) -> NormalizedToolResult:
        raw_path = None
        if len(output.encode("utf-8")) > 4096:
            raw_name = f"{int(time.time() * 1000)}-{hashlib.sha256(output.encode()).hexdigest()[:12]}.txt"
            raw_file = self.raw_dir / raw_name
            raw_file.write_text(output, encoding="utf-8")
            raw_path = str(raw_file)
            summary = output[:1800] + "\n[raw output stored on disk]"
        else:
            summary = output
        findings: list[dict[str, Any]] = []
        for pattern in self.flag_patterns:
            for match in pattern.findall(output):
                findings.append({"category": "flag_candidate", "value": match,
                                 "status": EvidenceStatus.HYPOTHESIS.value, "confidence": 0.6})
        if self.detect_injection(output):
            findings.append({"category": "prompt_injection_attempt",
                             "title": "Untrusted tool output contains instruction-like text",
                             "status": EvidenceStatus.OBSERVED.value, "confidence": 1.0})
        result = NormalizedToolResult(tool, success, duration_ms, summary, findings, raw_path, exit_code, error)
        if session_id:
            for finding in findings:
                fingerprint = hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()[:24]
                status = EvidenceStatus(finding.get("status", EvidenceStatus.OBSERVED.value))
                self.store.upsert_finding(session_id, fingerprint, finding["category"],
                                          finding.get("title", finding.get("value", finding["category"])),
                                          status, float(finding.get("confidence", 0.5)), [finding])
        return result
