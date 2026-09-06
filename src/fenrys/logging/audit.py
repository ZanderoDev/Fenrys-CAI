from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """Append-only JSONL audit trail with secret-safe caller supplied metadata."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, **metadata: Any) -> None:
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **metadata}
        self.path.open("a", encoding="utf-8").write(json.dumps(payload, default=str) + "\n")
