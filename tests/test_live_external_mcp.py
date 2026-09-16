import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from fenrys_cai.mcp import MCPServerConfig, MCPProvider
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.state import CyberState
from fenrys_cai.tools import ToolRegistry


def _server_available() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8888/health", timeout=2) as response:
            data = json.loads(response.read().decode())
            return data.get("status") == "healthy"
    except (OSError, ValueError, urllib.error.URLError):
        return False


@pytest.mark.skipif(not _server_available(), reason="external MCP-backed security server is not available")
def test_external_security_mcp_safe_live_invocation() -> None:
    bridge = Path("references/nyxstrike-master/nyxstrike-master/nyxstrike_mcp.py").resolve()
    config = MCPServerConfig(
        "external-security-mcp",
        "stdio",
        command="/tmp/fenrys-nyxstrike-venv/bin/python",
        args=(str(bridge), "--server", "http://127.0.0.1:8888", "--compact"),
        cwd=bridge.parent,
        startup_timeout=20,
        request_timeout=30,
    )
    provider = MCPProvider(config)
    registry = ToolRegistry()
    try:
        specs = provider.discover()
        names = {spec.name for spec in specs}
        assert {"classify_task", "run_tool"}.issubset(names)
        registry.register_provider(provider)
        result = registry.invoke("run_tool", {"tool_name": "hashid", "params": '{"hash_value":"5d41402abc4b2a76b9719d911017c592"}'})
        assert result.status == "success"
        assert "MD5" in result.stdout
        assert result.provenance["provider"] == "external-security-mcp"
    finally:
        provider.close()
