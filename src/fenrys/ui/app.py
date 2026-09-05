from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Input, Static

from fenrys.config import ConfigManager
from fenrys.doctor import format_doctor, run_doctor
from fenrys.state import StateStore
from .dashboard import Dashboard
from .theme.nightshade import NIGHTSHADE_CSS


class FenrysApp(App):
    TITLE = "Fenrys-CAI"
    CSS = NIGHTSHADE_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "setup", "Setup"),
        Binding("n", "new_session", "New session"),
    ]

    def __init__(self, config: ConfigManager | None = None):
        super().__init__()
        self.config = config or ConfigManager()
        cfg = self.config.load("config.yaml")
        self.store = StateStore(cfg["database_path"])

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Dashboard(self.config, self.store)
        yield Input(placeholder="> /help  /status  /agents  /model status  /doctor", id="command")
        yield Static("Nightshade command bar ready.", id="command-output")
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(1.0, self.action_refresh)

    def action_refresh(self) -> None:
        dashboard = self.query_one(Dashboard)
        dashboard.remove()
        self.mount(Dashboard(self.config, self.store), before=self.query_one("#command"))

    def action_setup(self) -> None:
        from .wizard import SetupScreen
        self.push_screen(SetupScreen(self.config))

    def action_new_session(self) -> None:
        cfg = self.config.load("config.yaml")
        scope = self.config.load("scope.yaml")
        targets = scope.get("targets", [])
        session_id = self.store.create_session(cfg.get("mode", "NORMAL"), targets[0] if targets else None, scope)
        self.query_one("#command-output", Static).update(f"New session: {session_id}")
        self.action_refresh()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        command = event.value.strip()
        event.input.value = ""
        output = self.query_one("#command-output", Static)
        parts = command.split()
        if not command.startswith("/"):
            output.update("Commands must start with /. Try /help.")
            return
        name = parts[0].lower()
        if name in {"/quit", "/q"}:
            self.exit()
        elif name == "/help":
            output.update("/help /agents /tools /status /plan /state /findings /model /theme /doctor /reset /quit")
        elif name == "/agents":
            output.update("Agents: " + ", ".join(agent.key for agent in __import__("fenrys.agents", fromlist=["AGENTS"]).AGENTS))
        elif name == "/tools":
            output.update("Tools are discovered once from HexStrike MCP and scoped per agent.")
        elif name == "/status":
            sessions = self.store.list_sessions()
            output.update(f"Sessions: {len(sessions)} | Active: {sessions[0]['id'] if sessions else 'none'}")
        elif name in {"/findings", "/state", "/plan"}:
            sessions = self.store.list_sessions()
            if not sessions:
                output.update("No session yet.")
            else:
                session = sessions[0]
                if name == "/findings":
                    output.update(f"Findings: {len(self.store.list_findings(session['id']))}")
                else:
                    output.update(session["state_json"][:500])
        elif name == "/model":
            if len(parts) == 2 and parts[1] == "status":
                output.update("Model mappings are live in ~/.config/fenrys-cai/agents.yaml")
            elif len(parts) == 5 and parts[1] == "set":
                self.config.set_agent_model(parts[2], parts[3], parts[4])
                output.update(f"Updated {parts[2]} → {parts[3]}/{parts[4]}")
            else:
                output.update("Usage: /model status | /model set <agent> <provider> <model>")
        elif name == "/theme":
            output.update("Theme: Nightshade")
        elif name == "/doctor":
            output.update(format_doctor(await run_doctor(self.config)).replace("\n", " | "))
        elif name == "/reset":
            output.update("Reset is session-scoped; use [n] to start a clean session.")
        else:
            output.update(f"Unknown command {name}. Try /help.")

    def on_unmount(self) -> None:
        self.store.close()
