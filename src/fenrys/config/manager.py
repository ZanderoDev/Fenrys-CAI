from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "NORMAL",
    "hexstrike_url": "http://127.0.0.1:8888",
    "hexstrike_install_dir": os.environ.get("HEXSTRIKE_HOME", "/root/hexstrike-ai"),
    "hexstrike_python": os.environ.get("HEXSTRIKE_PYTHON", "python3"),
    "database_path": "~/.local/share/fenrys-cai/fenrys.db",
    "raw_output_dir": "~/.local/share/fenrys-cai/raw",
}
DEFAULT_POLICY = {
    "budgets": {
        "max_tool_calls_per_task": 6,
        "max_same_tool_same_target_retries": 2,
        "max_agent_turns_per_task": 10,
        "max_total_tool_calls_per_session": 200,
        "max_wallclock_per_task_seconds": 900,
        "max_consecutive_failures_before_escalation": 3,
    }
}
DEFAULT_SCOPE = {"targets": [], "cidrs": [], "hostnames": [], "urls": []}
DEFAULT_AGENTS = {
    "model_tiers": {
        "heavy_reasoning": {"provider": "anthropic", "model": "claude-opus-5"},
        "balanced": {"provider": "anthropic", "model": "claude-sonnet-5"},
        "fast_cheap": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
    },
    "agents": {
        "orchestrator": "heavy_reasoning",
        "web": "balanced",
        "pwn": "heavy_reasoning",
        "recon": "fast_cheap",
        "network": "fast_cheap",
        "forensics": "balanced",
        "osint": "fast_cheap",
        "vulnintel": "balanced",
        "crypto": "heavy_reasoning",
        "misc": "balanced",
    },
}
DEFAULT_PROVIDERS = {
    "providers": {
        "anthropic": {"type": "anthropic", "api_key_env": "ANTHROPIC_API_KEY"},
        "openai": {"type": "openai", "api_key_env": "OPENAI_API_KEY"},
        "local_ollama": {
            "type": "openai_compatible",
            "base_url": "http://127.0.0.1:11434/v1",
            "api_key_env": None,
        },
    }
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """Loads user/project config and applies hot changes atomically."""

    filenames = ("config.yaml", "providers.yaml", "agents.yaml", "policy.yaml", "scope.yaml")

    def __init__(self, project_root: Path | None = None, home: Path | None = None):
        self.project_root = project_root or Path.cwd()
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        self.user_dir = (home or config_home) / "fenrys-cai"

    @property
    def project_dir(self) -> Path:
        return self.project_root / ".fenrys"

    def path(self, name: str) -> Path:
        return self.project_dir / name if (self.project_dir / name).exists() else self.user_dir / name

    def is_configured(self) -> bool:
        return any((self.user_dir / name).exists() for name in self.filenames)

    def load(self, name: str) -> dict[str, Any]:
        defaults = {
            "config.yaml": DEFAULT_CONFIG,
            "providers.yaml": DEFAULT_PROVIDERS,
            "agents.yaml": DEFAULT_AGENTS,
            "policy.yaml": DEFAULT_POLICY,
            "scope.yaml": DEFAULT_SCOPE,
        }[name]
        path = self.path(name)
        if not path.exists():
            return copy.deepcopy(defaults)
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return _deep_merge(defaults, data)

    def all(self) -> dict[str, dict[str, Any]]:
        return {name: self.load(name) for name in self.filenames}

    def save(self, name: str, data: dict[str, Any], backup: bool = True) -> Path:
        self.user_dir.mkdir(parents=True, exist_ok=True)
        path = self.user_dir / name
        if backup and path.exists():
            path.replace(path.with_suffix(path.suffix + ".bak"))
        temp = path.with_suffix(path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False)
        temp.replace(path)
        return path

    def set_agent_model(self, agent: str, provider: str, model: str) -> None:
        data = self.load("agents.yaml")
        if agent not in data["agents"]:
            raise ValueError(f"unknown agent: {agent}")
        data["agents"][agent] = {"provider": provider, "model": model}
        self.save("agents.yaml", data)

    def resolve_agent(self, agent: str) -> dict[str, str]:
        data = self.load("agents.yaml")
        value = data["agents"].get(agent)
        if value is None:
            raise ValueError(f"unknown agent: {agent}")
        if isinstance(value, str):
            value = data["model_tiers"].get(value)
        if not isinstance(value, dict) or not value.get("provider") or not value.get("model"):
            raise ValueError(f"invalid model mapping for agent: {agent}")
        return {"provider": value["provider"], "model": value["model"]}

    def write_initial(self, mode: str = "NORMAL", target: str | None = None) -> None:
        config = self.load("config.yaml")
        config["mode"] = mode
        scope = self.load("scope.yaml")
        if target and target not in scope["targets"]:
            scope["targets"].append(target)
        self.save("config.yaml", config, backup=False)
        for name in ("providers.yaml", "agents.yaml", "policy.yaml", "scope.yaml"):
            self.save(name, self.load(name), backup=False)
