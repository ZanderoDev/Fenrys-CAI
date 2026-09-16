from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .provider import MCPServerConfig


def _scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        return value


def load_mcp_config(path: Path) -> list[MCPServerConfig]:
    """Load MCP servers from JSON or a minimal Fenrys-native YAML subset.

    Environment placeholders use ${VARIABLE}; missing values become an empty string.
    The provider core never interprets server names or embeds credentials.
    """
    raw = path.read_text(encoding="utf-8")
    for key, value in os.environ.items():
        raw = raw.replace("${" + key + "}", value)
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
    else:
        import yaml  # type: ignore[import-untyped]
        data = yaml.safe_load(raw)
    servers = (data or {}).get("mcp", {}).get("servers", {})
    configs: list[MCPServerConfig] = []
    for name, item in servers.items():
        configs.append(MCPServerConfig(
            name=name,
            transport=item["transport"],
            command=item.get("command"),
            args=tuple(item.get("args", [])),
            env=dict(item.get("env", {})),
            cwd=Path(item["cwd"]).expanduser() if item.get("cwd") else None,
            url=item.get("url"),
            headers=dict(item.get("headers", {})),
            startup_timeout=float(item.get("startup_timeout", 15.0)),
            request_timeout=float(item.get("request_timeout", 30.0)),
        ))
    return configs
