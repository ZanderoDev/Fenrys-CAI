from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fenrys.models import EvidenceStatus, TaskStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    """SQLite state layer for sessions, tasks, evidence, invocations, and chat history."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, target TEXT, mode TEXT NOT NULL, scope_json TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active', state_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, agent TEXT NOT NULL,
              objective TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 50,
              status TEXT NOT NULL, dependencies_json TEXT NOT NULL DEFAULT '[]',
              allowed_tools_json TEXT NOT NULL DEFAULT '[]', reason TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS findings (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
              category TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
              confidence REAL NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]',
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(session_id, fingerprint)
            );
            CREATE TABLE IF NOT EXISTS tool_invocations (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task_id TEXT,
              tool TEXT NOT NULL, target TEXT, success INTEGER NOT NULL,
              result_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def create_session(self, mode: str, target: str | None, scope: dict[str, Any]) -> str:
        session_id = uuid.uuid4().hex[:12]
        now = utc_now()
        self.conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, 'active', '{}', ?, ?)",
            (session_id, target, mode, json.dumps(scope), now, now),
        )
        self.conn.commit()
        return session_id

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row else None

    def delete_session(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM tool_invocations WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM findings WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM tasks WHERE session_id = ?", (session_id,))
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.commit()

    def update_state(self, session_id: str, patch: dict[str, Any]) -> None:
        row = self.get_session(session_id)
        if not row:
            raise KeyError(session_id)
        state = json.loads(row["state_json"])
        state.update(patch)
        self.conn.execute("UPDATE sessions SET state_json = ?, updated_at = ? WHERE id = ?",
                          (json.dumps(state), utc_now(), session_id))
        self.conn.commit()

    def add_task(self, session_id: str, agent: str, objective: str, priority: int = 50,
                 dependencies: list[str] | None = None, allowed_tools: list[str] | None = None) -> str:
        task_id = uuid.uuid4().hex[:12]
        now = utc_now()
        self.conn.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)",
            (task_id, session_id, agent, objective, priority, TaskStatus.QUEUED.value,
             json.dumps(dependencies or []), json.dumps(allowed_tools or []), now, now),
        )
        self.conn.commit()
        return task_id

    def update_task(self, task_id: str, status: TaskStatus, reason: str | None = None) -> None:
        self.conn.execute("UPDATE tasks SET status = ?, reason = ?, updated_at = ? WHERE id = ?",
                          (status.value, reason, utc_now(), task_id))
        self.conn.commit()

    def list_tasks(self, session_id: str | None = None) -> list[dict[str, Any]]:
        if session_id:
            rows = self.conn.execute("SELECT * FROM tasks WHERE session_id = ? ORDER BY priority DESC", (session_id,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def upsert_finding(self, session_id: str, fingerprint: str, category: str, title: str,
                       status: EvidenceStatus, confidence: float, evidence: list[dict[str, Any]]) -> str:
        finding_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{session_id}:{fingerprint}").hex[:12]
        now = utc_now()
        self.conn.execute(
            """INSERT INTO findings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, fingerprint) DO UPDATE SET
                 title=excluded.title, status=excluded.status, confidence=excluded.confidence,
                 evidence_json=excluded.evidence_json, updated_at=excluded.updated_at""",
            (finding_id, session_id, fingerprint, category, title, status.value,
             max(0.0, min(1.0, confidence)), json.dumps(evidence), now, now),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM findings WHERE session_id=? AND fingerprint=?",
                                (session_id, fingerprint)).fetchone()
        return str(row["id"])

    def list_findings(self, session_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM findings"
        params: tuple[Any, ...] = ()
        if session_id:
            query += " WHERE session_id = ?"
            params = (session_id,)
        query += " ORDER BY updated_at DESC"
        return [dict(row) for row in self.conn.execute(query, params).fetchall()]

    def append_chat(self, session_id: str, role: str, content: str, limit: int = 40) -> None:
        row = self.get_session(session_id)
        if not row:
            raise KeyError(session_id)
        state = json.loads(row["state_json"])
        history = state.get("chat_history")
        if not isinstance(history, list):
            history = []
        history.append({"role": role, "content": content})
        state["chat_history"] = history[-max(1, limit):]
        self.conn.execute("UPDATE sessions SET state_json = ?, updated_at = ? WHERE id = ?",
                          (json.dumps(state), utc_now(), session_id))
        self.conn.commit()

    def chat_history(self, session_id: str, limit: int = 24) -> list[dict[str, str]]:
        row = self.get_session(session_id)
        if not row:
            raise KeyError(session_id)
        state = json.loads(row["state_json"])
        history = state.get("chat_history")
        if not isinstance(history, list):
            return []
        return [item for item in history[-max(1, limit):]
                if isinstance(item, dict) and item.get("role") in {"user", "assistant"}
                and isinstance(item.get("content"), str)]

    def record_invocation(self, session_id: str, tool: str, result: dict[str, Any],
                          task_id: str | None = None, target: str | None = None) -> str:
        invocation_id = uuid.uuid4().hex[:12]
        self.conn.execute(
            "INSERT INTO tool_invocations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (invocation_id, session_id, task_id, tool, target, int(bool(result.get("success"))),
             json.dumps(result), utc_now()),
        )
        self.conn.commit()
        return invocation_id
