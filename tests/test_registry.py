from fenrys.tool_registry import ToolRegistry


def test_agent_profiles_are_scoped():
    registry = ToolRegistry()
    registry.sync(["nmap_scan", "sqlmap_scan", "checksec_analyze"])
    recon = {tool.name for tool in registry.profile_for("recon")}
    web = {tool.name for tool in registry.profile_for("web")}
    assert recon == {"nmap_scan"}
    assert web == {"sqlmap_scan"}


def test_tool_availability_states_are_independent():
    registry = ToolRegistry()
    registry.sync([{
        "name": "nmap_scan",
        "mcp_registered": True,
        "backend_registered": False,
    }])
    status = registry.status()["nmap_scan"]
    assert status["mcp_registered"] is True
    assert status["backend_registered"] is False