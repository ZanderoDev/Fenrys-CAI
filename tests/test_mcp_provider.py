from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import time

import pytest

from fenrys_cai.config import RuntimeConfig
from fenrys_cai.graph import Decision, FenrysGraph
from fenrys_cai.mcp import MCPServerConfig, MCPProvider
from fenrys_cai.mcp.config import load_mcp_config
from fenrys_cai.mcp.provider import MCPProviderError
from fenrys_cai.runtime import LocalTerminalRuntime
from fenrys_cai.state import CyberState
from fenrys_cai.tools import LocalProvider, ToolRegistry


def provider(tmp_path: Path) -> MCPProvider:
    server = Path(__file__).with_name("mcp_test_server.py")
    return MCPProvider(MCPServerConfig("test-mcp", "stdio", command=sys.executable, args=(str(server),), startup_timeout=10, request_timeout=10), max_output_bytes=4096)


def test_stdio_discovery_multiple_tools_and_registry_integration(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    mcp = provider(tmp_path)
    registry.register_provider(mcp)
    try:
        names = {spec.name for spec in registry.discover()}
        assert {"read_file", "write_file", "execute", "echo_text", "structured_echo"}.issubset(names)
        spec = next(spec for spec in registry.discover() if spec.name == "echo_text")
        assert spec.provider == "test-mcp"
        assert spec.execution_mode == "mcp"
        assert "text" in spec.input_schema.get("properties", {})
        result = registry.invoke("echo_text", {"text": "safe"})
        assert result.status == "success"
        assert "echo:safe" in result.stdout
        assert result.provenance["provider"] == "test-mcp"
    finally:
        registry.invoke("execute", {"command": "true", "session_id": "cleanup"})
        mcp.close()


def test_stdio_connection_reused_and_clean_shutdown(tmp_path: Path) -> None:
    mcp = provider(tmp_path)
    mcp.start()
    try:
        before = len(subprocess.run(["pgrep", "-f", "mcp_test_server.py"], capture_output=True, text=True).stdout.splitlines())
        mcp.invoke("echo_text", {"text": "one"})
        mcp.invoke("structured_echo", {"text": "two"})
        after = len(subprocess.run(["pgrep", "-f", "mcp_test_server.py"], capture_output=True, text=True).stdout.splitlines())
        assert after == before
    finally:
        mcp.close()
    deadline = time.time() + 5
    while time.time() < deadline:
        if not subprocess.run(["pgrep", "-f", "mcp_test_server.py"], capture_output=True, text=True).stdout.strip():
            break
        time.sleep(0.1)
    assert not subprocess.run(["pgrep", "-f", "mcp_test_server.py"], capture_output=True, text=True).stdout.strip()


def test_startup_failure_and_tool_not_found_are_structured(tmp_path: Path) -> None:
    missing = MCPProvider(MCPServerConfig("missing", "stdio", command="/definitely/missing/mcp-server", startup_timeout=1, request_timeout=1))
    with pytest.raises(MCPProviderError, match="failed to start"):
        missing.start()
    mcp = provider(tmp_path)
    try:
        result = mcp.invoke("not_a_tool", {})
        assert result.status == "error"
        assert result.error == "tool_not_found"
    finally:
        mcp.close()


def test_timeout_is_normalized(tmp_path: Path) -> None:
    slow = tmp_path / "slow_mcp.py"
    slow.write_text("""from mcp.server.fastmcp import FastMCP
import time
server = FastMCP('slow')
@server.tool(name='slow_tool')
def slow_tool() -> str:
    time.sleep(5)
    return 'late'
server.run()
""")
    mcp = MCPProvider(MCPServerConfig("slow", "stdio", command=sys.executable, args=(str(slow),), startup_timeout=10, request_timeout=0.2))
    try:
        result = mcp.invoke("slow_tool", {})
        assert result.status == "timeout"
        assert result.error == "timeout"
    finally:
        mcp.close()


class MCPUsingReasoner:
    def decide(self, state, tools):
        if state.attempts:
            return Decision(complete=True, rationale="MCP observation received")
        return Decision("echo_text", {"text": "through-graph"}, "invoke dynamically discovered MCP tool")


def test_mcp_result_reaches_langgraph_without_mcp_graph_logic(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register_provider(LocalProvider(LocalTerminalRuntime(RuntimeConfig(tmp_path / "workspace"))))
    mcp = provider(tmp_path)
    registry.register_provider(mcp)
    try:
        state = FenrysGraph(registry, MCPUsingReasoner()).run(CyberState("mcp", "prove generic MCP"))
        assert state.completed
        assert state.attempts[-1].tool == "echo_text"
        assert state.evidence[-1]["status"] == "success"
        assert state.evidence[-1]["provenance"]["mcp"] is True
    finally:
        mcp.close()


def test_mcp_config_loader_expands_environment_without_exposing_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FENRYS_TEST_MCP_HEADER", "redacted-test-value")
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcp": {"servers": {"example": {"transport": "stdio", "command": "server", "headers": {"Authorization": "${FENRYS_TEST_MCP_HEADER}"}}}}}))
    loaded = load_mcp_config(config)[0]
    assert loaded.name == "example"
    assert loaded.headers["Authorization"] == "redacted-test-value"
    assert loaded.command == "server"


def test_malformed_schema_is_structured_error(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed_mcp.py"
    malformed.write_text("""from mcp.server.fastmcp import FastMCP
from mcp import Tool
from mcp.types import ListToolsResult
server = FastMCP('malformed')
original = server._mcp_server.list_tools()
@server._mcp_server.list_tools()
async def malformed_tools():
    return ListToolsResult(tools=[Tool(name='bad', description='bad schema', inputSchema=None)])
server.run()
""")
    mcp = MCPProvider(MCPServerConfig("malformed", "stdio", command=sys.executable, args=(str(malformed),), startup_timeout=10, request_timeout=10))
    with pytest.raises(MCPProviderError, match="malformed tool schema"):
        mcp.discover()
    mcp.close()


def test_configured_environment_secret_is_not_forwarded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "env_mcp.py"
    marker.write_text("""from mcp.server.fastmcp import FastMCP
import os
server = FastMCP('env')
@server.tool(name='secret_present')
def secret_present() -> str: return str('FENRYS_HIDDEN_TEST_SECRET' in os.environ)
server.run()
""")
    monkeypatch.setenv("FENRYS_HIDDEN_TEST_SECRET", "do-not-forward")
    mcp = MCPProvider(MCPServerConfig("env", "stdio", command=sys.executable, args=(str(marker),), startup_timeout=10, request_timeout=10))
    try:
        result = mcp.invoke("secret_present", {})
        assert result.status == "success"
        assert "False" in result.stdout
        assert "do-not-forward" not in result.stdout
    finally:
        mcp.close()


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_streamable_http_discovery_and_invocation(tmp_path: Path) -> None:
    port = _unused_port()
    http_server = tmp_path / "http_mcp.py"
    http_server.write_text(f"""from mcp.server.fastmcp import FastMCP
server = FastMCP('http-test', host='127.0.0.1', port={port})
@server.tool(name='http_echo')
def http_echo(text: str) -> str: return 'http:' + text
server.run(transport='streamable-http')
""")
    process = subprocess.Popen([sys.executable, str(http_server)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        deadline = time.time() + 10
        mcp = MCPProvider(MCPServerConfig("http-test", "http", url=url, startup_timeout=2, request_timeout=5))
        while True:
            try:
                specs = mcp.discover()
                break
            except MCPProviderError:
                if time.time() > deadline:
                    raise
                mcp = MCPProvider(MCPServerConfig("http-test", "http", url=url, startup_timeout=2, request_timeout=5))
                time.sleep(0.2)
        assert [spec.name for spec in specs] == ["http_echo"]
        result = mcp.invoke("http_echo", {"text": "safe"})
        assert result.status == "success"
        assert "http:safe" in result.stdout
        mcp.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
