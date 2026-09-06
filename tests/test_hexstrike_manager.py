import sys
from pathlib import Path

from fenrys.integrations.hexstrike_manager import HexStrikeManager


def test_manager_discovers_existing_install_without_installing(tmp_path):
    (tmp_path / "hexstrike_mcp.py").write_text("# existing MCP entrypoint\n", encoding="utf-8")
    (tmp_path / "hexstrike_server.py").write_text("# existing REST entrypoint\n", encoding="utf-8")

    manager = HexStrikeManager(tmp_path, sys.executable)
    installation = manager.installation

    assert installation.path == tmp_path
    assert installation.python == Path(sys.executable)
    assert manager.mcp_command("http://127.0.0.1:8888") == [
        str(sys.executable),
        str(tmp_path / "hexstrike_mcp.py"),
        "--server",
        "http://127.0.0.1:8888",
    ]