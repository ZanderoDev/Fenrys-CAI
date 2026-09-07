"""Fenrys setup wizard — Hermes-style sequential prompts.

Plain input(), no TUI screens. Writes config.yaml / providers.yaml /
agents.yaml / policy.yaml / scope.yaml via ConfigManager plus user_dir/.env
for API keys (providers read keys from env at runtime). API keys are pasted
VISIBLY then the line is wiped after Enter.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

from rich.console import Console

from fenrys.config import ConfigManager

console = Console()

CUSTOM_LABEL = "+ Custom manual (isi URL sendiri)..."

# Preset provider: dari NAMA saja semua terisi otomatis (URL + env key +
# model default). User tidak pernah ditanya soal env/URL untuk provider ini.
PRESETS = {
    "openrouter": {"type": "openai_compatible", "base_url": "https://openrouter.ai/api/v1",
                   "api_key_env": "OPENROUTER_API_KEY", "model": "minimax/minimax-m3:free"},
    "anthropic": {"type": "anthropic", "base_url": None,
                  "api_key_env": "ANTHROPIC_API_KEY", "model": "claude-sonnet-4-5"},
    "openai": {"type": "openai", "base_url": None,
               "api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"},
    "deepseek": {"type": "openai_compatible", "base_url": "https://api.deepseek.com/v1",
                 "api_key_env": "DEEPSEEK_API_KEY", "model": "deepseek-chat"},
    "vexacode": {"type": "custom", "base_url": "https://ai.vexacode.id/v1",
                 "api_key_env": "VEXACODE_API_KEY", "model": ""},
    "lapakvip": {"type": "openai_compatible", "base_url": "https://router.lapakvip.com/api/v1",
                 "api_key_env": "LAPAKVIP_API_KEY", "model": "lv/claude-sonnet-4.5"},
    "local_ollama": {"type": "openai_compatible", "base_url": "http://127.0.0.1:11434/v1",
                     "api_key_env": None, "model": "llama3.1"},
}

# Prefix kredensial umum (dicek case-insensitive, hanya bila panjang curiga).
_KEYLIKE_PREFIXES = ("sk-or-", "sk-ant-", "sk-", "ghp_", "gsk_", "AIza",
                     "nvapi-", "xoxb-", "xoxp-", "xox-", "relay_")


def _looks_like_key(value: str) -> bool:
    """True bila value lebih mirip API key daripada nama env/provider."""
    v = (value or "").strip()
    if not v:
        return False
    if len(v) > 40:
        return True
    if any(c.islower() for c in v) and any(c.isupper() for c in v) and len(v) > 24:
        return True
    low = v.lower()
    return len(v) > 16 and any(low.startswith(p) for p in _KEYLIKE_PREFIXES)

MODES = ["NORMAL", "CTF", "LAB", "AUTHORIZED_PENTEST"]


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


def _ask_key(prompt: str) -> str:
    """Paste API key secara TERLIHAT (permintaan user), lalu hapus barisnya
    dari layar setelah Enter — tidak nangkring di scrollback."""
    try:
        secret = input(f"  {prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    if secret and sys.stdin.isatty() and sys.stdout.isatty():
        try:
            width = shutil.get_terminal_size().columns or 80
            rows = (len(prompt) + 4 + len(secret)) // width + 1
            sys.stdout.write(f"\033[{rows}A")
            for _ in range(rows):
                sys.stdout.write("\033[2K\033[1B")
            sys.stdout.flush()
        except Exception:
            pass
    return secret


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


def _ensure_provider_entry(config: ConfigManager, name: str) -> dict:
    """Pastikan entry provider benar dari NAMA saja: isi preset + sembuhkan
    api_key_env yang ketempelan key asli (pindahkan ke .env otomatis)."""
    providers = config.load("providers.yaml")
    table = providers.setdefault("providers", {})
    preset = PRESETS.get(name, PRESETS.get(name.lower(), {}))
    entry = dict(table.get(name) or {})
    for key in ("type", "base_url"):
        if preset.get(key):
            entry[key] = preset[key]
    if not entry.get("api_key_env"):
        entry["api_key_env"] = preset.get("api_key_env")
    env = entry.get("api_key_env")
    if env and _looks_like_key(str(env)):
        secret = str(env)
        fixed = preset.get("api_key_env") or (
            f"{re.sub(r'[^A-Za-z0-9_]', '_', name).upper()}_API_KEY")
        entry["api_key_env"] = fixed
        _write_env(config, fixed, secret)
        console.print("  [green]✓ Key yang nyangkut di config diperbaiki otomatis.[/green]")
    table[name] = entry
    config.save("providers.yaml", providers)
    return entry


def _maybe_override_url(config: ConfigManager, provider: str, current_url: str) -> str:
    """Tanya Base URL; Enter = pakai preset, paste URL lain = override."""
    if not current_url:
        return ""
    url = _ask("Base URL (Enter = preset, atau paste bila beda)", current_url)
    if url == current_url:
        return current_url
    if not url.startswith(("http://", "https://")):
        console.print("  [yellow]URL tidak valid — tetap pakai preset.[/yellow]")
        return current_url
    full = config.load("providers.yaml")
    full["providers"][provider]["base_url"] = url.rstrip("/")
    config.save("providers.yaml", full)
    console.print("  [dim]URL custom tersimpan.[/dim]")
    return url.rstrip("/")


def _provider_choices(providers: dict) -> list[str]:
    """Daftar provider: entry yang ada menang (nama persis), preset mengisi
    sisanya tanpa duplikat case-insensitive (vexacode vs VEXACODE)."""
    names = list(providers)
    seen_lower = {n.lower() for n in providers}
    for n in PRESETS:
        if n.lower() not in seen_lower:
            names.append(n)
            seen_lower.add(n.lower())
    return names


def _setup_custom_provider(config: ConfigManager) -> str:
    """Alur paste-key langsung: nama + URL + key. Nama env dibuat otomatis."""
    console.print("[bold]Provider custom[/bold] [dim](OpenAI-compatible: /chat/completions)[/dim]")
    while True:
        name = _ask("Nama provider (cth: VEXACODE)", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            console.print("[yellow]Nama: huruf, angka, _ dan - saja.[/yellow]")
        elif len(name) > 24 or _looks_like_key(name):
            console.print("[yellow]Itu kelihatannya API key, bukan NAMA. "
                          "Isi nama pendek dulu — key-nya ditempel di langkah berikut.[/yellow]")
        else:
            break
    while True:
        base_url = _ask("Base URL (berakhiran /v1)", "")
        if base_url.startswith(("http://", "https://")):
            break
        console.print("[yellow]Harus diawali http:// atau https://.[/yellow]")
    secret = _ask_key("Paste API key (kosongkan bila tanpa key)")
    env_name = f"{re.sub(r'[^A-Za-z0-9_]', '_', name).upper()}_API_KEY"
    providers = config.load("providers.yaml")
    providers.setdefault("providers", {})[name] = {
        "type": "custom",
        "base_url": base_url.rstrip("/"),
        "api_key_env": env_name,
    }
    config.save("providers.yaml", providers)
    if secret:
        _write_env(config, env_name, secret)
        console.print(f"  [green]✓ Provider {name} + key ({len(secret)} karakter) tersimpan.[/green]")
    else:
        console.print(f"  [yellow]Provider {name} tersimpan tanpa key — "
                      f"export {env_name}=... nanti.[/yellow]")
    return name


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

    all_names = _provider_choices(providers)
    default_provider = "openrouter" if "openrouter" in all_names else (all_names[0] if all_names else "")
    picked = _ask_choice("Provider LLM (URL + key otomatis dari nama)", all_names + [CUSTOM_LABEL],
                         default_provider)
    if picked == CUSTOM_LABEL:
        provider = _setup_custom_provider(config)
    else:
        provider = picked
        _ensure_provider_entry(config, provider)
    providers = config.load("providers.yaml").get("providers", {})
    pinfo = providers.get(provider, {})
    current_url = _maybe_override_url(config, provider, pinfo.get("base_url") or "")
    if current_url:
        pinfo = {**pinfo, "base_url": current_url}
    api_key_env = pinfo.get("api_key_env")
    preset_model = PRESETS.get(provider, {}).get("model", "")
    model = _ask("Model", preset_model or current_model or "")
    if api_key_env:
        existing = os.environ.get(api_key_env, "")
        if existing:
            console.print(f"  [dim]{api_key_env} sudah ada di environment — dipakai.[/dim]")
        else:
            secret = _ask_key(f"Paste API key untuk {api_key_env} (kosongkan untuk skip)")
            if secret:
                _write_env(config, api_key_env, secret)
                console.print(f"  [green]✓ Key diterima ({len(secret)} karakter), "
                              f"disimpan di {config.user_dir / '.env'}[/green]")
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
