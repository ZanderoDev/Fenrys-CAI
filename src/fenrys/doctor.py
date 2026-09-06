from __future__ import annotations

import asyncio
import importlib.util
import platform
import shutil
import sys
from dataclasses import dataclass

from fenrys.config import ConfigManager
from fenrys.evidence import EvidenceManager
from fenrys.integrations import HexStrikeAdapter, HexStrikeManager
from fenrys.state import StateStore


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str


async def run_doctor(config: ConfigManager | None = None) -> list[Check]:
    config = config or ConfigManager()
    cfg = config.load("config.yaml")
    checks = [
        Check("Python", sys.version_info[:2] == (3, 13), platform.python_version()),
        Check("uv", bool(shutil.which("uv")), shutil.which("uv") or "not found"),
        Check("PyYAML", importlib.util.find_spec("yaml") is not None, "importable"),
        Check("Textual", importlib.util.find_spec("textual") is not None, "importable"),
    ]
    try:
        store = StateStore(cfg["database_path"])
        store.close()
        checks.append(Check("SQLite", True, str(cfg["database_path"])))
    except Exception as exc:
        checks.append(Check("SQLite", False, type(exc).__name__))
    manager = HexStrikeManager(
        cfg.get("hexstrike_install_dir"),
        cfg.get("hexstrike_python"),
    )
    installation = manager.installation
    try:
        mcp_available = installation.mcp.is_file() and installation.python.is_file()
    except OSError:
        mcp_available = False
    checks.append(Check(
        "HexStrike MCP",
        mcp_available,
        f"{installation.mcp} via {installation.python}" if mcp_available
        else f"not found; expected existing install under {installation.path}",
    ))
    adapter = HexStrikeAdapter(cfg["hexstrike_url"])
    ok, detail = await adapter.health()
    checks.append(Check("HexStrike", ok, detail))
    for name, entry in config.load("providers.yaml").get("providers", {}).items():
        checks.append(Check(f"Provider {name}", True, f"configured ({entry.get('type', 'unknown')})"))
    return checks


def format_doctor(checks: list[Check]) -> str:
    return "\n".join(f"{'✓' if item.ok else '✗'} {item.name:<18} {item.detail}" for item in checks)
