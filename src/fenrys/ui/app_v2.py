from __future__ import annotations

import asyncio
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Input, Static

from fenrys.agents.runtime import InvestigationRuntime
from fenrys.config import ConfigManager
from fenrys.doctor import format_doctor, run_doctor
from fenrys.state import StateStore
from .components.status_bar import StatusBar
from .components.streaming_chat import StreamingChat
from .components.tool_tree import ToolTree
from .theme.nightshade import NIGHTSHADE_CSS


class FenrysAppV2(App):
    """Fenrys operator shell v2: streaming tokens, live status, tool visualization."""

    TITLE = "Fenrys"
    CSS = NIGHTSHADE_CSS + """
    #brand {
        height: 1;
        dock: top;
        padding: 0 1;
        background: $accent;
        color: $text;
        text-style: bold;
    }
    #topbar {
        height: 1;
        dock: top;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    #command {
        dock: bottom;
        height: 3;
        padding: 0 1;
    }
    #hints {
        height: 1;
        dock: bottom;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }
    """
    BINDINGS = [
        Binding("ctrl+c", "stop_or_quit", "Stop/Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=False),
        Binding("ctrl+n", "new_session", "New", show=False),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(self, config: ConfigManager | None = None):
        super().__init__()
        self.config = config or ConfigManager()
        cfg = self.config.load("config.yaml")
        self.store = StateStore(cfg["database_path"])
        self.runtime = InvestigationRuntime(self.config, self.store)
        self.session_id: str | None = None
        self.active_job: asyncio.Task | None = None
        self._hexstrike_ok = False

    def compose(self) -> ComposeResult:
        yield Static("FENRYS \u00b7 CTF OPERATOR v2", id="brand")
        yield Static("starting\u2026", id="topbar")
        yield StreamingChat(id="chat-area")
        yield ToolTree(id="tools")
        yield Input(placeholder="\u25b8 Ask Fenrys anything\u2026", id="command")
        yield StatusBar(id="status")
        yield Footer()

    async def on_mount(self) -> None:
        self.call_after_refresh(self._boot)

    async def _boot(self) -> None:
        await self._ensure_session()
        health, reason = await self.runtime.adapter.health()
        self._hexstrike_ok = health
        cfg = self.config.load("config.yaml")
        target = (self.store.get_session(self.session_id) or {}).get("target") or "local artifact"

        status = self.query_one("#status", StatusBar)
        status.set_model(cfg.get("model", "minimax/minimax-m3:free"))

        self.query_one("#topbar", Static).update(
            f"session {self.session_id[:8]} \u00b7 mode {cfg.get('mode', 'CTF')} \u00b7 "
            f"target {target} \u00b7 hexstrike {'\u25cf' if health else '\u25cb'}"
        )

        chat = self.query_one("#chat-area", StreamingChat)
        chat.write_message("[bold]Fenrys[/bold]  Cybersecurity AI  [dim]v2 - streaming[/dim]")
        chat.write_message("[dim]One operator. Natural language. Streaming tokens. Tool visualization.[/dim]")
        if not health:
            chat.write_message(f"[yellow]HexStrike offline:[/yellow] {reason}")

        self.query_one("#command", Input).focus()

    async def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id
        cfg = self.config.load("config.yaml")
        scope = self.config.load("scope.yaml")
        targets = scope.get("targets", [])
        self.session_id = self.store.create_session(
            cfg.get("mode", "CTF"), targets[0] if targets else None, scope
        )
        return self.session_id

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        event.input.value = ""
        if not prompt or self.active_job:
            return
        if prompt.startswith("/"):
            await self._command(prompt)
            return
        self.active_job = asyncio.create_task(self._run_prompt(prompt))
        try:
            await self.active_job
        finally:
            self.active_job = None
            self.query_one("#command", Input).focus()

    async def _run_prompt(self, prompt: str) -> None:
        session = await self._ensure_session()
        chat = self.query_one("#chat-area", StreamingChat)
        tools = self.query_one("#tools", ToolTree)
        status = self.query_one("#status", StatusBar)

        chat.write_user(prompt)
        status.set_status("\u25cf thinking")
        tools.clear()

        async def on_token(delta: str):
            chat.write_token(delta)

        async def on_event(kind: str, payload: str):
            if kind == "tool":
                parts = payload.split(" ", 1)
                tool_name = parts[0] if parts else payload
                tool_target = parts[1] if len(parts) > 1 else ""
                tools.add_tool(tool_name, tool_target)
                status.set_status(f"\u2699 {payload}")
            elif kind == "result":
                if tools._tools:
                    last = tools._tools[-1]
                    last_tool = last["name"]
                    success = "\u2713" in payload or "ok" in payload.lower()
                    tools.finish_tool(last_tool, success, duration_ms=0)
                status.set_status("\u25cf reasoning")
            elif kind == "delegate":
                chat.write_tool_event("delegate", payload)
            elif kind == "error":
                chat.write_tool_event("error", payload)

        async def on_usage(usage: dict):
            if "total_tokens" in usage:
                status.update_tokens(usage["total_tokens"])

        try:
            result = await self.runtime.run_chat_streaming(
                session, prompt,
                on_token=on_token,
                on_event=on_event,
                on_usage=on_usage,
            )
            chat.flush_tokens()
            status.set_status(f"ready \u00b7 {datetime.now().strftime('%H:%M:%S')}")
        except asyncio.CancelledError:
            chat.flush_tokens()
            status.set_status("stopped")
        except Exception as exc:
            chat.flush_tokens()
            chat.write_message(f"[red]Error:[/red] {type(exc).__name__}: {exc}")
            status.set_status("error")

    async def _command(self, command: str) -> None:
        chat = self.query_one("#chat-area", StreamingChat)
        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        if name in {"/q", "/quit", "/exit"}:
            self.exit()
        elif name in {"/help", "/h"}:
            chat.write_message(
                "[dim]/help  /status  /agents  /doctor  /clear  /new  /quit\n"
                "Everything else is a normal Fenrys request.[/dim]"
            )
        elif name == "/clear":
            self.action_clear()
        elif name == "/new":
            await self._new_session()
        elif name == "/status":
            sessions = self.store.list_sessions()
            chat.write_message(f"[dim]sessions={len(sessions)} active={self.session_id or 'none'} hexstrike={'up' if self._hexstrike_ok else 'down'}[/dim]")
        elif name == "/doctor":
            chat.write_message(format_doctor(await run_doctor(self.config)))
        elif name == "/agents":
            chat.write_message(
                "[dim]Specialists: recon \u00b7 web \u00b7 network \u00b7 pwn \u00b7 forensics \u00b7 osint \u00b7 vulnintel \u00b7 crypto \u00b7 misc\n"
                "Fenrys chooses them automatically.[/dim]"
            )
        else:
            chat.write_message("[yellow]Unknown command.[/yellow] Try /help.")

    async def _new_session(self) -> None:
        chat = self.query_one("#chat-area", StreamingChat)
        self.session_id = None
        chat.clear()
        await self._ensure_session()
        chat.write_message("[green]New session.[/green]")

    def action_clear(self) -> None:
        self.query_one("#chat-area", StreamingChat).clear()

    def action_stop_or_quit(self) -> None:
        if self.active_job and not self.active_job.done():
            self.active_job.cancel()
            self.query_one("#status", StatusBar).set_status("stopped \u00b7 press Ctrl+C again to quit")
        else:
            self.exit()

    def action_new_session(self) -> None:
        asyncio.create_task(self._new_session())

    def on_unmount(self) -> None:
        self.store.close()
