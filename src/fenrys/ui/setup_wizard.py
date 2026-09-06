"""Fenrys setup wizard — Hermes-style sequential prompts.

Plain input()/getpass, no TUI screens. Writes config.yaml / providers.yaml /
agents.yaml / policy.yaml / scope.yaml via ConfigManager plus user_dir/.env
for API keys (providers read keys from env at runtime).
"""

from __future__ import annotations

import os
import sys
from getpass import getpass

from rich.console import Console

from fenrys.config import ConfigManager

console = Console()

MODES = ["NORMAL", "CTF", "LAB", "AUTHORIZED_PENTEST"]
MODEL_DEFAULTS = {
    "openrouter": "minimax/minimax-m3:free",
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o-mini",
    "local_ollama": "llama3.1",
}


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"  {prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return value or default


def _ask_choice(title: str, options: list[str], default: str) -> str:
    console.print(f"[bold]{title}[/bold]")
    for i, opt in enumerate(options, 1):
        mark = " (default)" if opt == default else ""
        console.print(f"    [cyan]{i}[/cyan]. {opt}{mark}")
    while True:
        try:
            raw = input(f"  pilih [1-{len(options)}]: ").strip()
        except EOFError:
            return default
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        console.print("[yellow]Pilihan tidak dikenal, coba lagi.[/yellow]")


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {prompt} [{hint}]: ").strip().lower()
    except EOFError:
        return default
    if not raw:
        return default
    return raw in {"y", "yes", "ya", "1"}


def _write_env(config: ConfigManager, key: str, value: str) -> None:
    path = config.user_dir / ".env"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    os.environ[key] = value


def run_setup_wizard(config: ConfigManager, reconfigure: bool = False) -> bool:
    """Run the wizard. Returns True when configuration is complete."""
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        console.print("[yellow]Setup butuh terminal interaktif.[/yellow]")
        console.print("[dim]Jalankan manual: fenrys model set <agent> <provider> <model> "
                      "lalu export API key env.[/dim]")
        return False
    if config.is_configured() and not reconfigure:
        console.print("[green]Fenrys sudah dikonfigurasi.[/green] "
                      "[dim](pakai --reconfigure untuk ubah)[/dim]")
        return True

    console.print()
    console.print("[bold magenta]FENRYS SETUP[/bold magenta]  [dim]·  beberapa pertanyaan singkat[/dim]")
    providers = config.load("providers.yaml").get("providers", {})
    agents_cfg = config.load("agents.yaml")
    current_model = ""
    try:
        current_model = config.resolve_agent("orchestrator").get("model", "")
    except ValueError:
        pass

    provider = _ask_choice("Provider LLM", list(providers), "openrouter")
    pinfo = providers.get(provider, {})
    api_key_env = pinfo.get("api_key_env")
    model = _ask("Model", MODEL_DEFAULTS.get(provider, current_model or ""))
    if api_key_env:
        existing = os.environ.get(api_key_env, "")
        if existing:
            console.print(f"  [dim]{api_key_env} sudah ada di environment — dipakai.[/dim]")
        else:
            try:
                secret = getpass(f"  API key ({api_key_env}, kosongkan untuk skip): ").strip()
            except (EOFError, KeyboardInterrupt):
                secret = ""
            if secret:
                _write_env(config, api_key_env, secret)
                console.print(f"  [dim]disimpan di {config.user_dir / '.env'}[/dim]")
            else:
                console.print(f"  [yellow]dilewati — export {api_key_env} manual nanti.[/yellow]")
    else:
        console.print("  [dim]provider lokal — tanpa API key.[/dim]")

    mode = _ask_choice("Mode operasi", MODES, config.load("config.yaml").get("mode", "CTF"))
    target = _ask("Target awal (opsional, kosongkan untuk nanti)", "")
    hexstrike = _ask("HexStrike URL", config.load("config.yaml").get("hexstrike_url", "http://127.0.0.1:8888"))

    console.print()
    console.print("[bold]Ringkasan:[/bold]")
    console.print(f"  provider : {provider}")
    console.print(f"  model    : {model or '(default)'}")
    console.print(f"  mode     : {mode}")
    console.print(f"  target   : {target or '-'}")
    console.print(f"  hexstrike: {hexstrike}")
    if not _ask_yes_no("Simpan?", True):
        console.print("[yellow]Dibatalkan.[/yellow]")
        return False

    cfg = config.load("config.yaml")
    cfg["mode"] = mode
    cfg["hexstrike_url"] = hexstrike
    config.save("config.yaml", cfg, backup=False)
    scope = config.load("scope.yaml")
    if target and target not in scope.get("targets", []):
        scope["targets"].append(target)
        config.save("scope.yaml", scope, backup=False)
    config.save("providers.yaml", config.load("providers.yaml"), backup=False)
    config.save("policy.yaml", config.load("policy.yaml"), backup=False)
    if model:
        if _ask_yes_no(f"Terapkan model ke semua agent ({len(agents_cfg.get('agents', {}))})?", True):
            for agent in agents_cfg.get("agents", {}):
                try:
                    config.set_agent_model(agent, provider, model)
                except ValueError:
                    pass
        else:
            try:
                config.set_agent_model("orchestrator", provider, model)
            except ValueError:
                pass
    else:
        config.save("agents.yaml", config.load("agents.yaml"), backup=False)

    console.print()
    console.print("[bold green]✓ Setup selesai.[/bold green]")
    if api_key_env and not os.environ.get(api_key_env):
        console.print(f"[yellow]Ingat:[/yellow] export {api_key_env}=... sebelum jalan.")
    console.print("[dim]Jalankan: fenrys[/dim]")
    return True
