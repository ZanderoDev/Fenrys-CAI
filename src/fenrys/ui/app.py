from __future__ import annotations

import asyncio
from datetime import datetime

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Footer, RichLog, Static, TextArea

from fenrys.agents.runtime import InvestigationRuntime
from fenrys.config import ConfigManager
from fenrys.doctor import format_doctor, run_doctor
from fenrys.state import StateStore
from .theme.nightshade import NIGHTSHADE_CSS


class SubmitPrompt(Message):
    """Posted when the user presses Enter on the input."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class FenrysInput(TextArea):
    """Multi-line input that submits on Enter and inserts newline on Shift+Enter (Hermes-style).

    Paste (Ctrl+Shift+V) is handled by the terminal's bracketed-paste protocol and TextArea's
    built-in handler — no custom code needed. The entire pasted block lands at the cursor.
    """

    BINDINGS = [
        Binding("ctrl+j,ctrl+enter,shift+enter,f2", "newline", "newline", show=False),
        Binding("enter", "submit", "Submit", show=False),
    ]

    def __init__(self, **kwargs):
        kwargs.setdefault("id", "command")
        kwargs.setdefault("classes", "fenrys-input")
        super().__init__(**kwargs)
        self.show_line_numbers = False

    async def _on_key(self, event) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            await self.action_submit()
            return
        await super()._on_key(event)

    async def action_submit(self) -> None:
        text = self.text.strip()
        if not text:
            return
        self.text = ""
        self.app.post_message(SubmitPrompt(text))

    async def action_newline(self) -> None:
        self.insert("\n")


class FenrysApp(App):
    """Fenrys operator shell: one conversational agent with invisible-by-default routing."""

    TITLE = "Fenrys"
    CSS = NIGHTSHADE_CSS
    BINDINGS = [
        Binding("ctrl+c", "stop_or_quit", "Stop/Quit", show=True),
        Binding("ctrl+l", "clear", "Clear", show=False),
        Binding("ctrl+n", "new_session", "New", show=False),
        Binding("ctrl+o", "setup", "Setup", show=False),
        Binding("ctrl+d", "doctor", "Doctor", show=False),
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
        yield Static("FENRYS  ·  CTF OPERATOR", id="brand")
        yield Static("starting…", id="topbar")
        yield RichLog(id="chat", highlight=True, markup=True, wrap=True)
        yield Static("ready", id="status")
        with Vertical(id="input-wrap"):
            yield FenrysInput()
        yield Static(
            "Enter submit   Ctrl+J newline (multi-line)   Ctrl+Shift+V paste   Ctrl+C stop   /help",
            id="hints",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._boot)

    async def _boot(self) -> None:
        await self._ensure_session()
        health, reason = await self.runtime.adapter.health()
        self._hexstrike_ok = health
        cfg = self.config.load("config.yaml")
        target = (self.store.get_session(self.session_id) or {}).get("target") or "local artifact"
        self.query_one("#topbar", Static).update(
            f"session {self.session_id[:8]}  ·  mode {cfg.get('mode', 'CTF')}  ·  "
            f"target {target}  ·  hexstrike {'●' if health else '○'}"
        )
        self._log("[bold]Fenrys[/bold]  Cybersecurity AI")
        self._log(
            "[dim]One operator. Natural language. Fenrys decides when to use tools or delegate to a specialist.[/dim]"
        )
        if not health:
            self._log(f"[yellow]HexStrike offline:[/yellow] {reason}")
        self.query_one("#command", FenrysInput).focus()

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

    def _log(self, text: str) -> None:
        self.query_one("#chat", RichLog).write(text)

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    async def on_submit_prompt(self, event: SubmitPrompt) -> None:
        prompt = event.text
        if self.active_job:
            return
        if prompt.startswith("/"):
            await self._command(prompt)
            return
        self.active_job = asyncio.create_task(self._run_prompt(prompt))
        try:
            await self.active_job
        finally:
            self.active_job = None
            self.query_one("#command", FenrysInput).focus()

    async def _run_prompt(self, prompt: str) -> None:
        session = await self._ensure_session()
        self._log(f"\n[bold cyan]›[/bold cyan] {prompt}")
        self._set_status("● thinking")
        try:
            result = await self.runtime.run_chat(session, prompt, on_event=self._event)
            self._log(f"\n[bold]Fenrys[/bold]  {result.summary}")
            self._set_status(f"ready · {datetime.now().strftime('%H:%M:%S')}")
        except asyncio.CancelledError:
            self._set_status("stopped")
            self._log("[yellow]Stopped.[/yellow]")
        except Exception as exc:
            self._set_status("error")
            self._log(f"[red]Error:[/red] {type(exc).__name__}: {exc}")

    async def _event(self, kind: str, payload: str) -> None:
        if kind == "delegate":
            self._log(f"[magenta]↳ {payload}[/magenta]")
            self._set_status("↳ delegating")
        elif kind == "tool":
            self._log(f"[cyan]⚙ {payload}[/cyan]")
            self._set_status("⚙ running tool")
        elif kind == "result":
            self._log(f"[green]✓ {payload}[/green]")
            self._set_status("● reasoning")
        elif kind == "error":
            self._log(f"[red]! {payload}[/red]")

    async def _command(self, command: str) -> None:
        parts = command.split(maxsplit=1)
        name = parts[0].lower()
        if name in {"/q", "/quit", "/exit"}:
            self.exit()
        elif name in {"/help", "/h"}:
            self._log(
                "[dim]/help  /status  /agents  /doctor  /clear  /new  /setup  /quit\n"
                "Everything else is a normal Fenrys request.[/dim]"
            )
        elif name == "/clear":
            self.action_clear()
        elif name == "/new":
            await self._new_session()
        elif name == "/status":
            sessions = self.store.list_sessions()
            self._log(f"[dim]sessions={len(sessions)} active={self.session_id or 'none'} hexstrike={'up' if self._hexstrike_ok else 'down'}[/dim]")
        elif name == "/doctor":
            self._log(format_doctor(await run_doctor(self.config)))
        elif name == "/agents":
            self._log(
                "[dim]Specialists: recon · web · network · pwn · forensics · osint · vulnintel · crypto · misc\n"
                "Fenrys chooses them automatically; you do not need to select one.[/dim]"
            )
        elif name == "/setup":
            self.action_setup()
        else:
            self._log("[yellow]Unknown command.[/yellow] Try /help. Natural-language requests do not need a slash.")

    async def _new_session(self) -> None:
        self.session_id = None
        self.query_one("#chat", RichLog).clear()
        await self._ensure_session()
        self._log("[green]New session.[/green]")

    def action_clear(self) -> None:
        self.query_one("#chat", RichLog).clear()

    def action_stop_or_quit(self) -> None:
        if self.active_job and not self.active_job.done():
            self.active_job.cancel()
            self._set_status("stopped · press Ctrl+C again to quit")
        else:
            self.exit()

    def action_new_session(self) -> None:
        asyncio.create_task(self._new_session())

    def action_setup(self) -> None:
        from .wizard import SetupScreen
        self.push_screen(SetupScreen(self.config))

    def action_doctor(self) -> None:
        asyncio.create_task(self._doctor())

    async def _doctor(self) -> None:
        self._log(format_doctor(await run_doctor(self.config)))

    def on_unmount(self) -> None:
        self.store.close()
