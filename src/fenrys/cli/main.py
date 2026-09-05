from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from fenrys.config import ConfigManager
from fenrys.doctor import format_doctor, run_doctor
from fenrys.report import build_report
from fenrys.state import StateStore
from fenrys.ui import FenrysApp, SetupWizardApp

console = Console()


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fenrys", description="Fenrys-CAI terminal cybersecurity operator")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("setup").add_argument("--reconfigure", action="store_true")
    sub.add_parser("doctor")
    model = sub.add_parser("model")
    model_sub = model.add_subparsers(dest="model_command")
    model_sub.add_parser("list")
    set_model = model_sub.add_parser("set")
    set_model.add_argument("agent"); set_model.add_argument("provider"); set_model.add_argument("model")
    test_model = model_sub.add_parser("test"); test_model.add_argument("provider")
    tools = sub.add_parser("tools"); tools.add_argument("tools_command", choices=["list", "status", "sync"], nargs="?", default="status")
    hexstrike = sub.add_parser("hexstrike")
    hexstrike_sub = hexstrike.add_subparsers(dest="hexstrike_command")
    hexstrike_sub.add_parser("start")
    hexstrike_sub.add_parser("status")
    hexstrike_sub.add_parser("stop")
    sub.add_parser("agents").add_argument("agents_command", choices=["status"], nargs="?", default="status")
    session = sub.add_parser("session")
    session_sub = session.add_subparsers(dest="session_command")
    session_sub.add_parser("list")
    new = session_sub.add_parser("new"); new.add_argument("--target"); new.add_argument("--mode", default=None)
    resume = session_sub.add_parser("resume"); resume.add_argument("session_id")
    export = session_sub.add_parser("export"); export.add_argument("session_id"); export.add_argument("--format", choices=["markdown", "json", "html"], default="markdown"); export.add_argument("--output")
    delete = session_sub.add_parser("delete"); delete.add_argument("session_id"); delete.add_argument("--yes", action="store_true")
    run = session_sub.add_parser("run")
    run.add_argument("session_id"); run.add_argument("agent"); run.add_argument("objective")
    investigate = session_sub.add_parser("investigate")
    investigate.add_argument("session_id"); investigate.add_argument("objective")
    report = sub.add_parser("report")
    report.add_argument("--format", choices=["markdown", "json", "html"], default="markdown")
    report.add_argument("--session")
    for shortcut in ("ctf", "scan", "analyze"):
        sub.add_parser(shortcut)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = make_parser().parse_args(argv)
    config = ConfigManager()
    command = args.command
    if command is None:
        if not config.is_configured():
            SetupWizardApp(config).run()
        else:
            FenrysApp(config).run()
        return
    if command == "setup":
        SetupWizardApp(config).run()
    elif command == "doctor":
        console.print(format_doctor(asyncio.run(run_doctor(config))))
    elif command == "model":
        handle_model(config, args)
    elif command == "tools":
        handle_tools(config, args)
    elif command == "hexstrike":
        handle_hexstrike(config, args)
    elif command == "agents":
        for agent, mapping in config.load("agents.yaml")["agents"].items():
            resolved = config.resolve_agent(agent)
            console.print(f"{agent:<14} {resolved['provider']} / {resolved['model']}")
    elif command == "session":
        handle_session(config, args)
    elif command == "report":
        cfg = config.load("config.yaml")
        store = StateStore(cfg["database_path"])
        print(build_report(store, args.session, args.format))
        store.close()
    elif command in {"ctf", "scan", "analyze"}:
        console.print(f"[violet]Shortcut {command}[/violet] opens the operator dashboard.")
        FenrysApp(config).run()


def handle_model(config: ConfigManager, args) -> None:
    if args.model_command == "list":
        for name in config.load("providers.yaml")["providers"]:
            console.print(name)
    elif args.model_command == "set":
        config.set_agent_model(args.agent, args.provider, args.model)
        console.print(f"[green]Updated[/green] {args.agent} → {args.provider}/{args.model}")
    elif args.model_command == "test":
        from fenrys.providers import ProviderRegistry
        provider = ProviderRegistry(config).build(args.provider)
        health = asyncio.run(provider.health_check())
        color = "green" if health.ok else "red"
        console.print(f"[{color}]{'OK' if health.ok else 'FAIL'}[/{color}] {health.provider} "
                      f"{health.latency_ms or '-'}ms — {health.reason}")


def handle_tools(config: ConfigManager, args) -> None:
    from fenrys.tool_registry import ToolRegistry
    registry = ToolRegistry()
    if args.tools_command == "list":
        from fenrys.tool_registry.registry import AGENT_TOOL_NAMES
        for agent, tools in AGENT_TOOL_NAMES.items():
            console.print(f"{agent}: {', '.join(tools)}")
    else:
        console.print("Tool registry is empty until HexStrike sync succeeds.")


def handle_hexstrike(config: ConfigManager, args) -> None:
    from fenrys.integrations.hexstrike_manager import HexStrikeManager
    cfg = config.load("config.yaml")
    manager = HexStrikeManager(cfg.get("hexstrike_install_dir"), cfg.get("hexstrike_python"))
    if args.hexstrike_command == "start":
        pid = manager.start()
        console.print(f"[green]HexStrike server running[/green] (pid {pid}, http://127.0.0.1:8888)")
    elif args.hexstrike_command == "status":
        pid = manager.status()
        console.print(f"[green]running (pid {pid})[/green]" if pid else "[yellow]not running[/yellow]")
    elif args.hexstrike_command == "stop":
        console.print("[green]stopped[/green]" if manager.stop() else "[yellow]not running[/yellow]")


def handle_session(config: ConfigManager, args) -> None:
    cfg = config.load("config.yaml")
    store = StateStore(cfg["database_path"])
    if args.session_command == "list":
        table = Table("ID", "Target", "Mode", "Status")
        for row in store.list_sessions():
            table.add_row(row["id"], row["target"] or "-", row["mode"], row["status"])
        console.print(table)
    elif args.session_command == "new":
        session_id = store.create_session(args.mode or cfg.get("mode", "NORMAL"), args.target, config.load("scope.yaml"))
        console.print(f"Created session {session_id}")
    elif args.session_command == "resume":
        session = store.get_session(args.session_id)
        if not session:
            raise SystemExit(f"Unknown session: {args.session_id}")
        console.print(f"Resuming {session['id']} — {session['target'] or 'no target'} / {session['mode']}")
        FenrysApp(config).run()
    elif args.session_command == "export":
        from fenrys.report import build_report
        output = Path(args.output or f"fenrys-{args.session_id}.{args.format}")
        output.write_text(build_report(store, args.session_id, args.format), encoding="utf-8")
        console.print(f"Exported {output}")
    elif args.session_command == "delete":
        if not args.yes:
            raise SystemExit("Deletion is irreversible; repeat with --yes")
        if not store.get_session(args.session_id):
            raise SystemExit(f"Unknown session: {args.session_id}")
        store.delete_session(args.session_id)
        console.print(f"Deleted session {args.session_id}")
    elif args.session_command == "run":
        from fenrys.agents import InvestigationRuntime
        result = asyncio.run(InvestigationRuntime(config, store).run_task(
            args.session_id, args.agent, args.objective,
        ))
        console.print(f"[green]Task {result.task_id} {result.tool_calls} tool call(s)[/green] "
                      f"via {result.provider}/{result.model}")
        if result.blocked_reason:
            console.print(f"[yellow]Blocked:[/yellow] {result.blocked_reason}")
        elif result.summary:
            console.print(result.summary[:2000])
    elif args.session_command == "investigate":
        from fenrys.agents import InvestigationRuntime
        results = asyncio.run(InvestigationRuntime(config, store).run_investigation(
            args.session_id, args.objective,
        ))
        for result in results:
            status = "BLOCKED" if result.blocked_reason else "COMPLETED"
            console.print(f"[green]{status}[/green] {result.task_id} "
                          f"{result.tool_calls} tool call(s) {result.provider}/{result.model}")
    store.close()


if __name__ == "__main__":
    main()
