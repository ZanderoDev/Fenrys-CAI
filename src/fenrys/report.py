from __future__ import annotations

import json
from typing import Any

from fenrys.state import StateStore


def build_report(store: StateStore, session_id: str | None = None, fmt: str = "markdown") -> str:
    sessions = store.list_sessions()
    session = store.get_session(session_id) if session_id else (sessions[0] if sessions else None)
    payload: dict[str, Any] = {
        "session": session,
        "findings": store.list_findings(session["id"] if session else None),
        "tasks": store.list_tasks(session["id"] if session else None),
    }
    if fmt == "json":
        return json.dumps(payload, indent=2, default=str)
    if fmt == "html":
        body = json.dumps(payload, indent=2, default=str).replace("&", "&amp;").replace("<", "&lt;")
        return f"<!doctype html><html><head><meta charset='utf-8'><title>Fenrys report</title></head><body><pre>{body}</pre></body></html>"
    lines = ["# Fenrys-CAI Report", ""]
    if session:
        lines += [f"- Session: `{session['id']}`", f"- Target: `{session['target'] or 'not set'}`", f"- Mode: `{session['mode']}`", ""]
    lines.append("## Findings")
    for finding in payload["findings"]:
        lines.append(f"- **[{finding['status']}]** {finding['title']} (confidence {finding['confidence']:.2f})")
    if not payload["findings"]:
        lines.append("- No findings recorded.")
    return "\n".join(lines) + "\n"
