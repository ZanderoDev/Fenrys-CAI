from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Label, Static

from fenrys.agents import AGENTS
from fenrys.config import ConfigManager
from fenrys.state import StateStore
from fenrys.ui.theme.nightshade import NIGHTSHADE_CSS


class Dashboard(Static):
    DEFAULT_CSS = NIGHTSHADE_CSS

    def __init__(self, config: ConfigManager, store: StateStore):
        super().__init__()
        self.config = config
        self.store = store

    def compose(self) -> ComposeResult:
        cfg = self.config.load("config.yaml")
        sessions = self.store.list_sessions()
        latest = sessions[0] if sessions else None
        target = latest["target"] if latest else "not set"
        mode = latest["mode"] if latest else cfg.get("mode", "NORMAL")
        with Vertical():
            yield Label("F E N R Y S  —  C Y B E R S E C U R I T Y  A I", classes="title")
            yield Label(f"Target: {target}    Mode: {mode}    Phase: Ready", classes="panel")
            with Horizontal(classes="panel"):
                with Vertical():
                    yield Label("AGENTS", classes="title")
                    for agent in AGENTS:
                        yield Label(f"◆ {agent.key.upper():<10} IDLE", classes="muted")
                with Vertical():
                    yield Label("INVESTIGATION STATE", classes="title")
                    findings = self.store.list_findings(latest["id"]) if latest else []
                    yield Label(f"Sessions       {len(sessions)}")
                    yield Label(f"Findings       {len(findings)}")
                    yield Label("Tool registry  cached via MCP")
            if latest:
                yield Label("TASK QUEUE", classes="title")
                tasks = self.store.list_tasks(latest["id"])
                if tasks:
                    for task in tasks[:8]:
                        color = {"running": "title", "completed": "ok", "blocked": "warning",
                                 "failed": "danger"}.get(task["status"], "muted")
                        yield Label(f"◆ {task['agent'].upper():<10} {task['status'].upper():<10} "
                                    f"{task['objective'][:60]}", classes=color)
                else:
                    yield Label("No queued tasks.", classes="muted")
            yield Label("Shortcuts  [s] setup  [n] new session  [r] refresh  [q] quit", classes="panel muted")
