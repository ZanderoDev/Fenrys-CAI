"""Fenrys REPL — scrollback chat in the Claude Code / Codex / Hermes mold
(prompt_toolkit + Rich). Turns read top-to-bottom as plain terminal text:
"› " for what you typed, "⏺" for an action Fenrys takes (tool call or
delegation), "⎿" for that action's result, indented underneath it.

Everything printed here is plain terminal scrollback, so mouse-drag +
Ctrl+Shift+C, tmux copy-mode, and terminal search all work — including flags.

Keys (Hermes reference):
  Enter            submit
  Alt+Enter / Ctrl+J   newline (multi-line)
  Ctrl+Shift+V     paste (terminal bracketed paste, native)
  Ctrl+C           cancel running turn / re-prompt when idle
  Ctrl+D           quit
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TextIO

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from fenrys.agents.runtime import InvestigationRuntime
from fenrys.config import ConfigManager
from fenrys.doctor import format_doctor, run_doctor
from fenrys.state import StateStore

FLAG_RE = re.compile(r"[A-Za-z0-9_]{1,32}\{[^{}\n]{1,300}\}")

SLASH_COMMANDS = [
    "/help", "/status", "/agents", "/doctor", "/clear", "/new", "/resume",
    "/setup", "/save", "/copy", "/quit",
]

HINTS = "Enter submit · Alt+Enter/Ctrl+J newline · Ctrl+Shift+V paste · Ctrl+C stop · /help"

LOGO = [
    "███████╗███████╗███╗   ██╗██████╗ ██╗   ██╗███████╗",
    "██╔════╝██╔════╝████╗  ██║██╔══██╗╚██╗ ██╔╝██╔════╝",
    "█████╗  █████╗  ██╔██╗ ██║██████╔╝ ╚████╔╝ ███████╗",
    "██╔══╝  ██╔══╝  ██║╚██╗██║██╔══██╗  ╚██╔╝  ╚════██║",
    "██║     ███████╗██║ ╚████║██║  ██║   ██║   ███████║",
    "╚═╝     ╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝   ╚═╝   ╚══════╝",
]

PET_ART = [
    "⢠⣤⡄          ⢤⣤⣤⣤⣤                    ⠠           ⢠⣤⣤⣤⣤⣤",
    "⢸⣿⣧   ⠈⡀     ⠈⠻⣿⣿⣿⡀  ⠰⠂ ⠙⠋⠛⠋⠉⠛⠙⠛ ⠐⠖ ⡄⡐     ⢰⡇     ⢸⣿⣿⣿⣿⣿",
    "⢸⣿⡏⡄   ⠐⣄      ⠙⠋⠁                 ⠠⡪     ⢀⣿⠁    ⠂⢸⣿⣿⣿⣿⣿",
    "⣤⣾⣿⣧⠐⡀   ⠘⢷⣄     ⠁  ⢀            ⡀     ⢄  ⢀⣾⡏      ⣿⣿⣿⣿⣿⣿",
    "⠈⠛⠿⢿⣇⢩⣄   ⠈⠻⣷⣦⠔⠁    ⠄            ⠐⡀     ⠑⢠⣿⡟       ⠋⣾⣿⣿⣿⣿",
    "   ⠸⣾⣿⣷⣄   ⠈⠋     ⢰              ⠰⠄      ⠙⢅   ⢀⣴  ⣼⣿⣿⣿⣿⣿",
    "     ⡀⠉⠻⣷⣄⡠⠁      ⡄         ⡀     ⠃          ⣠⣾⣿⡀ ⣿⣿⡇⣿⣿⣿",
    "     ⣿⣦⣀⣿⣿⠁   ⡄   ⡇    ⢰    ⡇     ⢸         ⠘⣿⡿⠋  ⣿⣿⣇⣿⣿⣿",
    "     ⣿⡟ ⠈⠁   ⢠    ⡇ ⡇   ⡄   ⠁          ⠂     ⠠    ⢿⣿⣿⣿⣿⣿",
    "    ⣸⡿  ⢠⡀   ⢸   ⢀⡇     ⠠        ⣀⣀⣄⡀  ⠈      ⠆⠁   ⠙⠿⣿⣿⣿",
    "  ⢀⢔⠟⠁  ⠈⠁   ⢸⡀  ⣼⠗  ⣆   ⠂  ⣆ ⠨⠺⠏ ⠸⢿⣄⠁ ⠄⡇     ⢠    ⣤⣤⣬⣽⣿",
    "  ⣿⣥⣤ ⠒ ⡇    ⢸⣇ ⣴⠿⠤⠤⡤⢿⣦     ⠛  ⠐  ⠂ ⠙⠢⡀⢰⡇     ⠈    ⠘⢿⣿⣿⣿",
    " ⢠⣿⣿⠟   ⡇    ⠉⣿⡾⠁    ⠘⠈⠢  ⠈⠴   ⢀⡀ ⢀⣀⡀  ⠺⠃      ⡀     ⠠⣾⣿",
    " ⣬⣅     ⡇     ⠉   ⣀⣀⣀⡀⠁        ⢠⠴⣾⢿⣿⣿⠛⠳⢶⡖⠂     ⠷⠄ ⠠⡀  ⠈⠛",
    "⢸⣿⠟⠉⠐   ⠃   ⠄⣀⣀⣠⡾⠟⠛⣿⢿⣿⣿⠂ ⠠ ⡢ ⠁   ⠳ ⣁⣹⣀ ⠈⠁    ⢐⢄⢀⠔⠁ ⡈⠻⢿⣿⣿⠁",
    "⠠⢐⣀  ⢀⣀  ⠰     ⠉⠹⠂  ⢷⣀⠁⠘  ⠈    ⠁        ⠈    ⡀ ⠙⠁ ⣼ ⠃  ⠈⠙ ⠠⣤⣤⣤",
    "⣼⣿⣿⣿⠟⠉⠈⠊⢀⢂⠄       ⠉⠉       ⠸⠆        ⢀⡆⠔⠔⠁⠠⡪⣳    ⣿⣤⡄      ⠙⠛⠁",
    "⣤⣾⣿⡿⠋⠁  ⠂⢸⠁ ⢀⣦⡀  ⠑⢤⢐⢄                   ⠠⠤⠆⠁⠘⠋⠏   ⠠⢹⣿⣄⣄⣀⣤⣀⣀⣀⣀⣀",
    "⠛⠋⠁      ⣼   ⢽⣯   ⢀⣑⡡     ⡀                  ⣼     ⠈⣿⣿⠁⠉⠙⠻⢿⣿⣿⣿⣿",
    "⣄      ⣠⣾⡿   ⢸⣿⣆  ⠈        ⠘    ⠂⠁     ⢀⡼   ⠠⠉⡀     ⢹⡇    ⣀⣀⣄⡀",
    "⠿⢿⣷⣶⣶⣶⣿⣿⣿⠇   ⣾⣿⣿⡆   ⢳⣄       ⡀       ⢀⣠⣿⡇   ⡆ ⠁      ⢲⣶⣶⣾⣿⣿⣿⠿⠃",
    " ⠈⠉⠉⣸⣿⠏   ⢠⣿⣿⣿⣿⡀⡀ ⠘⠉  ⠉⠉⠉  ⠊     ⣀⢴⣿⣿⣿⠃  ⣸⣷ ⠈       ⢻⣿⣿⣏⣁⣀⣀⣀⣀",
    "⣤⣀⣀⣠⣤⣤⣾⠏   ⢀⣾⣿⡿⠛⠉⠁ ⢤⣶⣶⣶⣷⣶⡀⠘⠦⣤⣀ ⢀⣠⡴⠚⠁⣸⣿⣿⣿  ⢠⣿⣿⣧⡀ ⢄     ⠈⢿⣿⣿⣿⣿⣿⣿⣿",
    "⠻⠿⣿⣿⣿⣿⠋  ⠂ ⠈⠙⠁       ⠉⠉⠙⠃⢿⣶⣦⣤⣭⣽⣿⣭⣤⣶⣿⠛⠻⣿⠿  ⠜⠛⠉⠉⠁  ⠈⠙⠁⠂  ⠈",
    "⣠⣿⣿⡿⠁   ⠠⠊             ⠐⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧  ⢻⣷ ⢠             ⡀ ⠺⣶⡄",
    "⡀⢻⣿⠟               ⠐⠤⡀    ⠉⠛⠿⠿⠿⠿⠿⠟⠋⠁   ⠻                ⡀ ⠙⣷⣀⣀⣀",
    "⣿⡾⠃              ⡠⠠    ⡄                ⠃⣷⡄             ⢠  ⠈⢺⣿⣿",
    "⠟   ⣾          ⠐ ⠁⢀⠟⠑⡀ ⢁             ⠠  ⠰⡿⢿⣄   ⣄         ⢀   ⠙⣿",
    "  ⣿⣦⣀⡀ ⢀⣠⣤⠢⡇   ⢀⠎     ⢱⣤⣤⣤⡀   ⣠⣤⣴⠄     ⠂⠊⢻⣆  ⣿        ⢰ ⠠   ⠈",
    "  ⣿⣿⡿⠿⠛⠻⣿⡏ ⠁   ⠌     ⠈ ⠁⠉⠛⠣   ⠛⠋⠁         ⢻⣆ ⣿        ⡀  ⠐⠄",
    "⢀⡈⣿⣿⣧⣤⣀⣠⣿⡇ ⣾⠠ ⠈                          ⠂ ⢹⣿⠏       ⢀⠁   ⠈⢦⡀",
    "⠁⠁⠈⠛⠿⠿⠿⠛⠋⠃ ⢻⠃⣀                            ⠁⠁⢿⣄       ⡌     ⠈⣿",
    "⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤",
]


def pet_art() -> str:
    width = max(len(line) for line in PET_ART)
    return "\n".join(line.ljust(width) for line in PET_ART)


def fmt_count(n) -> str:
    n = int(n or 0)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        s = f"{n / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{s}K"
    s = f"{n / 1_000_000:.2f}".rstrip("0").rstrip(".")
    return f"{s}M"


def fenrys_version() -> str:
    with suppress(Exception):
        from importlib.metadata import version
        return version("fenrys-cai")
    return "2.3.0"


def load_dotenv(config: ConfigManager) -> None:
    """Load user_dir/.env into os.environ (setdefault — real env wins)."""
    path = config.user_dir / ".env"
    if not path.exists():
        return
    with suppress(Exception):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if key and value:
                os.environ.setdefault(key, value)


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    if not text:
        return False, "nothing to copy"
    cmds: list[list[str]] = []
    if shutil.which("xclip"):
        cmds.append(["xclip", "-selection", "clipboard"])
    if shutil.which("xsel"):
        cmds.append(["xsel", "--clipboard", "--input"])
    if shutil.which("wl-copy"):
        cmds.append(["wl-copy"])
    if not cmds:
        return False, "no clipboard tool (xclip/xsel/wl-copy)"
    for cmd in cmds:
        with suppress(Exception):
            subprocess.run(cmd, input=text.encode(), timeout=3, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, cmd[0]
    return False, "clipboard copy failed"


def build_key_bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("enter")
    def _submit(event) -> None:
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _newline_alt_enter(event) -> None:
        event.current_buffer.insert_text("\n")

    @kb.add("c-j")
    def _newline_ctrl_j(event) -> None:
        event.current_buffer.insert_text("\n")

    return kb


class FenrysREPL:
    """Interactive scrollback chat. Agent/tool logic stays in InvestigationRuntime."""

    def __init__(self, config: ConfigManager | None = None):
        self.config = config or ConfigManager()
        load_dotenv(self.config)
        cfg = self.config.load("config.yaml")
        data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        self.data_dir = data_home / "fenrys-cai"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "loot").mkdir(parents=True, exist_ok=True)
        self.store = StateStore(cfg["database_path"])
        self.runtime = InvestigationRuntime(self.config, self.store)
        self.console = Console()
        self.session_id: str | None = None
        self.session: asyncio.Task | None = None
        self._hexstrike_ok = False
        self._turn_task: asyncio.Task | None = None
        self._last_flag: str | None = None
        self._last_answer: str | None = None
        self._transcript: TextIO | None = None  # opened per session
        self.title: str | None = None
        self.started_at = datetime.now()
        self.usage = {"prompt": 0, "completion": 0, "total": 0, "turns": 0, "tools": 0}
        self._turn_usage = {"prompt": 0, "completion": 0, "total": 0}
        self.kb = build_key_bindings()
        self.psession: PromptSession | None = None

    # ── session / transcript ──────────────────────────────
    async def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id
        cfg = self.config.load("config.yaml")
        scope = self.config.load("scope.yaml")
        targets = scope.get("targets", [])
        self.session_id = self.store.create_session(
            cfg.get("mode", "CTF"), targets[0] if targets else None, scope
        )
        self._open_transcript()
        return self.session_id

    def _open_transcript(self) -> None:
        with suppress(Exception):
            if self._transcript:
                self._transcript.close()
            path = self.data_dir / "transcripts" / f"{(self.session_id or 'x')[:12]}.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._transcript = open(path, "a", encoding="utf-8")
            self._transcript.write(f"--- fenrys {datetime.now().isoformat()} "
                                   f"session={self.session_id} ---\n")
            self._transcript.flush()

    @property
    def transcript_path(self) -> str:
        return str(self.data_dir / "transcripts" / f"{(self.session_id or 'x')[:12]}.log")

    @property
    def loot_path(self) -> str:
        return str(self.data_dir / "loot" / "flags.log")

    def _tlog(self, role: str, text: str) -> None:
        if self._transcript:
            with suppress(Exception):
                self._transcript.write(f"[{role}] {text}\n")
                self._transcript.flush()

    # ── output helpers ────────────────────────────────────
    def _status_line(self, text: str) -> None:
        self.console.print(f"[dim]{text}[/dim]")

    def _on_flag(self, flag: str) -> None:
        self._last_flag = flag
        with suppress(Exception):
            with open(self.loot_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().isoformat()} {self.session_id} {flag}\n")
        ok, info = copy_to_clipboard(flag)
        if ok:
            self.console.print(f"[bold green]⚑ flag → clipboard ({info}) + loot[/bold green]")
        else:
            self.console.print(f"[bold yellow]⚑ flag saved to loot ({info}). "
                               f"File: {self.loot_path}[/bold yellow]")

    def _scan_flags(self, text: str) -> None:
        for match in FLAG_RE.findall(text or ""):
            if match != self._last_flag:
                self._on_flag(match)

    # ── boot ──────────────────────────────────────────────
    def _logo_texts(self) -> list:
        return [Text(row, style="bold magenta") for row in LOGO]

    def _startup_panel(self, target: str) -> Panel:
        from fenrys.tool_registry.registry import AGENT_TOOL_NAMES
        cfg = self.config.load("config.yaml")
        try:
            orch = self.config.resolve_agent("orchestrator")
            model_line = f"{orch['provider']} · {orch['model']}"
        except ValueError:
            model_line = "-"
        grid = Table.grid(padding=(0, 3))
        grid.add_column()
        grid.add_column()
        left: list[str] = ["[bold]Available Tools[/bold]"]
        for agent, tools in AGENT_TOOL_NAMES.items():
            shown = ", ".join(tools[:3]) + (" …" if len(tools) > 3 else "")
            left.append(f"[cyan]{agent}[/cyan]: [dim]{shown}[/dim]")
        hx = "configured" if self._hexstrike_ok else "offline"
        right: list[str] = [
            "[bold]Engine[/bold]",
            f"hexstrike: {cfg.get('hexstrike_url', '-')} — {hx}",
            "",
            "[bold]Model[/bold]",
            f"orchestrator: {model_line}",
            "",
            "[bold]Session[/bold]",
            f"{(self.session_id or '-')[:8]}  ·  {cfg.get('mode', 'CTF')}  ·  {target}",
            f"{Path.cwd()}",
        ]
        grid.add_row("\n".join(left), "\n".join(right))
        n_tools = len(self.runtime.registry.specs)
        grid.add_row(
            "",
            f"[dim]{n_tools} tools · {len(AGENT_TOOL_NAMES)} specialists · "
            f"/help for commands[/dim]",
        )
        return Panel(grid, title=f"Fenrys-CAI v{fenrys_version()}",
                     border_style="magenta", expand=False)

    def _toolbar(self):
        parts = []
        if self.title:
            parts.append(self.title[:40])
        parts.append(f"sesi {(self.session_id or '-')[:8]}")
        if self.usage["total"]:
            parts.append(f"Σ {fmt_count(self.usage['total'])} token")
        parts.append("Enter kirim · Ctrl+J baris baru")
        return " · ".join(parts)

    async def _boot(self) -> None:
        await self._ensure_session()
        health, reason = await self.runtime.adapter.health()
        self._hexstrike_ok = health
        cfg = self.config.load("config.yaml")
        target = (self.store.get_session(self.session_id) or {}).get("target") or "local artifact"
        info = Text(f"mulai {self.started_at:%H:%M:%S} · sesi {self.session_id[:8]} · "
                    f"mode {cfg.get('mode', 'CTF')} · target {target} · "
                    f"hexstrike {'●' if health else '○'}", style="dim")
        width = self.console.width or 80
        if width >= 122:
            left = Group(*self._logo_texts(), Text(""), info, self._startup_panel(target))
            grid = Table.grid(padding=(0, 2))
            grid.add_column()
            grid.add_column()
            grid.add_row(left, Text(pet_art(), style="cyan", no_wrap=True,
                                    overflow="crop", justify="left"))
            self.console.print(grid)
        else:
            for t in self._logo_texts():
                self.console.print(t)
            self.console.print(info)
            self.console.print(self._startup_panel(target))
        if not health:
            self.console.print(f"[yellow]HexStrike offline:[/yellow] {reason}")
        self.console.print()
        self.console.print("Welcome to Fenrys! Type your message or /help for commands.")
        self.console.print("[dim]✦ Tip: semua output adalah scrollback — "
                           "select + Ctrl+Shift+C untuk salin flag.[/dim]")
        self.console.print(f"[dim]{HINTS}[/dim]")
        self._session_prompt()

    def _session_prompt(self) -> None:
        history = FileHistory(str(self.data_dir / "input_history"))
        completer = WordCompleter(SLASH_COMMANDS, ignore_case=True, sentence=True)
        self.psession = PromptSession(
            history=history,
            multiline=True,
            key_bindings=self.kb,
            completer=completer,
            complete_while_typing=False,
            bottom_toolbar=self._toolbar,
        )

    def _prompt_text(self) -> str:
        return "› "

    # ── main loop ─────────────────────────────────────────
    async def run(self) -> None:
        self.console.clear()
        await self._boot()
        assert self.psession is not None
        while True:
            try:
                with patch_stdout():
                    text = await self.psession.prompt_async(self._prompt_text())
            except EOFError:
                self.console.print("\n[dim]bye.[/dim]")
                break
            except KeyboardInterrupt:
                self.console.print("[dim]^C — Ctrl+D atau /quit untuk keluar[/dim]")
                continue
            text = (text or "").strip()
            if not text:
                continue
            if text.startswith("/"):
                done = await self._command(text)
                if done:
                    break
                continue
            await self._turn(text)
        with suppress(Exception):
            if self._transcript:
                self._transcript.close()
        with suppress(Exception):
            self.store.close()

    def _add_usage(self, u: dict) -> None:
        p = int(u.get("prompt_tokens", u.get("input_tokens", 0)) or 0)
        c = int(u.get("completion_tokens", u.get("output_tokens", 0)) or 0)
        t = int(u.get("total_tokens", 0) or (p + c))
        self._turn_usage = {"prompt": p, "completion": c, "total": t}
        self.usage["prompt"] += p
        self.usage["completion"] += c
        self.usage["total"] += t
        self.usage["turns"] += 1

    def _set_title(self, prompt: str) -> None:
        if self.title:
            return
        title = re.sub(r"\s+", " ", prompt).strip()[:45]
        if title:
            self.title = title
            with suppress(Exception):
                self.store.update_state(self.session_id or "", {"title": title})

    async def _turn(self, prompt: str) -> None:
        session = await self._ensure_session()
        self._set_title(prompt)
        self._tlog("user", prompt)
        self.console.print(Rule(style="dim"))
        lines = prompt.splitlines() or [""]
        head = lines[0][:120]
        extra = f" · +{len(lines) - 1} lines" if len(lines) > 1 else ""
        self.console.print(f"[bold]›[/bold] {head}{extra}")
        buf: list[str] = []
        t0 = time.monotonic()

        _mode = {"reasoning": False}

        async def on_token(chunk: str) -> None:
            if _mode["reasoning"]:
                sys.stdout.write("\n")
                _mode["reasoning"] = False
            buf.append(chunk)
            sys.stdout.write(chunk)
            sys.stdout.flush()

        async def on_reasoning(text: str) -> None:
            _mode["reasoning"] = True
            self.console.print(text, end="", style="dim", highlight=False, soft_wrap=True)

        async def on_event(kind: str, payload: str) -> None:
            if kind == "delegate":
                self.console.print(f"\n[bold magenta]⏺[/bold magenta] delegate → {payload}")
            elif kind == "tool":
                self.console.print(f"\n[bold cyan]⏺[/bold cyan] {payload}")
            elif kind == "result":
                if "failed" in payload or "blocked" in payload:
                    self.console.print(f"  [dim]⎿[/dim] [yellow]{payload}[/yellow]")
                else:
                    self.console.print(f"  [dim]⎿[/dim] [green]{payload}[/green]")
            elif kind == "error":
                self.console.print(f"  [dim]⎿[/dim] [bold red]{payload}[/bold red]")

        async def on_usage(u: dict) -> None:
            self._add_usage(u)

        self._status_line("⏺ thinking…")
        self._turn_task = asyncio.create_task(
            self.runtime.run_chat_streaming(
                session, prompt, on_token=on_token, on_event=on_event,
                on_usage=on_usage, on_reasoning=on_reasoning,
            )
        )
        try:
            result = await self._turn_task
        except asyncio.CancelledError:
            self.console.print("\n[yellow]Stopped.[/yellow]")
            return
        except KeyboardInterrupt:
            self._turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._turn_task
            self.console.print("\n[yellow]Stopped.[/yellow]")
            return
        except Exception as exc:
            self.console.print(f"\n[red]Error:[/red] {type(exc).__name__}: {exc}")
            return
        finally:
            self._turn_task = None
        sys.stdout.write("\n")
        sys.stdout.flush()
        final = (result.summary or "").strip()
        if not buf and final:
            # Nothing streamed (direct reply, empty stream) — print it,
            # otherwise the answer is invisible.
            self.console.print(final)
        self._last_answer = final or None
        self._tlog("assistant", final)
        self._scan_flags(final)
        self.usage["tools"] += result.tool_calls
        tu = self._turn_usage
        elapsed = max(time.monotonic() - t0, 0.01)
        tps = tu["completion"] / elapsed if tu["completion"] else 0.0
        self.console.print(Rule(style="dim"))
        self.console.print(
            f" ⚕ {result.provider}/{result.model} │ "
            f"▲ {fmt_count(tu['prompt'])} in · ▼ {fmt_count(tu['completion'])} out │ "
            f"◷ {elapsed:.1f}s │ ↑ {tps:.1f} t/s │ ⚙ {result.tool_calls} tool │ "
            f"Σ {fmt_count(self.usage['total'])} · {self.usage['turns']} turn"
        )

    # ── slash commands ────────────────────────────────────
    async def _command(self, command: str) -> bool:
        """Returns True when the REPL should exit."""
        parts = command.split(maxsplit=1)
        name, arg = parts[0].lower(), (parts[1] if len(parts) > 1 else "").strip()
        if name in {"/q", "/quit", "/exit"}:
            self.console.print("[dim]bye.[/dim]")
            return True
        if name in {"/help", "/h"}:
            self.console.print(
                "[dim]/help /status /agents /doctor /clear /new /resume /setup "
                "/save /copy /quit\nEverything else is a normal Fenrys request.[/dim]"
            )
        elif name == "/clear":
            self.console.print(Rule(style="dim"))
            self.console.print("[dim]scrollback milik terminal — pakai Ctrl+L terminal "
                               "untuk bersih-bersih layar.[/dim]")
        elif name == "/new":
            self.session_id = None
            self._last_flag = self._last_answer = None
            self.title = None
            self.usage = {"prompt": 0, "completion": 0, "total": 0, "turns": 0, "tools": 0}
            await self._ensure_session()
            self.console.print("[green]New session.[/green]")
        elif name == "/resume":
            await self._resume(arg)
        elif name == "/status":
            sessions = self.store.list_sessions()
            u = self.usage
            self.console.print(
                f"[dim]judul={self.title or '-'} · sessions={len(sessions)} "
                f"active={self.session_id or 'none'} "
                f"hexstrike={'up' if self._hexstrike_ok else 'down'}[/dim]"
            )
            self.console.print(
                f"[dim]pakai sesi ini: {u['turns']} turn · {u['tools']} tool · "
                f"▲ {fmt_count(u['prompt'])} in · ▼ {fmt_count(u['completion'])} out · "
                f"Σ {fmt_count(u['total'])} token[/dim]"
            )
        elif name == "/doctor":
            self.console.print(format_doctor(await run_doctor(self.config)))
        elif name == "/agents":
            self.console.print(
                "[dim]Specialists: recon · web · network · pwn · forensics · osint · "
                "vulnintel · crypto · misc\nFenrys chooses them automatically.[/dim]"
            )
        elif name == "/setup":
            from fenrys.ui.setup_wizard import run_setup_wizard
            run_setup_wizard(self.config, reconfigure=True)
        elif name == "/save":
            self.console.print(f"[dim]transcript: {self.transcript_path}[/dim]")
            self.console.print(f"[dim]loot: {self.loot_path}[/dim]")
        elif name == "/copy":
            target = self._last_flag or self._last_answer
            if not target:
                self.console.print("[yellow]Nothing to copy yet.[/yellow]")
            else:
                ok, info = copy_to_clipboard(target)
                label = "flag" if self._last_flag and target == self._last_flag else "answer"
                self.console.print(f"[green]Copied {label} ({info}).[/green]" if ok
                                   else f"[yellow]Copy failed ({info}).[/yellow]")
        else:
            self.console.print("[yellow]Unknown command.[/yellow] Try /help.")
        return False

    async def _resume(self, arg: str) -> None:
        sessions = self.store.list_sessions()[-10:]
        if not sessions:
            self.console.print("[yellow]No sessions yet.[/yellow]")
            return
        if arg:
            hit = next((s for s in sessions if s["id"].startswith(arg)), None)
            if not hit:
                self.console.print(f"[yellow]No session starting with {arg!r}.[/yellow]")
                return
            self.session_id = hit["id"]
            self.title = None
            self.usage = {"prompt": 0, "completion": 0, "total": 0, "turns": 0, "tools": 0}
            self._open_transcript()
            self.console.print(f"[green]Resumed {hit['id'][:8]}.[/green]")
            return
        for i, s in enumerate(sessions, 1):
            mark = "●" if s["id"] == self.session_id else " "
            self.console.print(f" {mark} [cyan]{i}[/cyan] {s['id'][:8]}  "
                               f"{s.get('target') or '-'}  {s.get('mode', '')}")
        self.console.print("[dim]/resume <id-prefix> untuk lanjut sesi.[/dim]")
