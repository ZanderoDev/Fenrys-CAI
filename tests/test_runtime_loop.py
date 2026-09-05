from fenrys.agents import InvestigationRuntime
from fenrys.models import ModelResponse, NormalizedToolResult
from fenrys.state import StateStore


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self):
        self.calls = 0

    async def complete(self, messages, tools=None, max_tokens=0, temperature=None):
        self.calls += 1
        if self.calls == 1:
            return ModelResponse("", self.model, self.name, [
                {"function": {"name": "nmap_scan", "arguments": '{"target":"challenge.local"}'}}
            ])
        return ModelResponse("Observed a service and stored the evidence.", self.model, self.name)


async def test_runtime_connects_provider_tool_evidence_and_state(temp_config, tmp_path):
    temp_config.save("config.yaml", {
        "database_path": str(tmp_path / "state.db"),
        "raw_output_dir": str(tmp_path / "raw"),
        "mode": "CTF",
    })
    temp_config.save("scope.yaml", {"targets": ["challenge.local"], "cidrs": [], "hostnames": [], "urls": []})
    store = StateStore(tmp_path / "state.db")
    session = store.create_session("CTF", "challenge.local", temp_config.load("scope.yaml"))
    runtime = InvestigationRuntime(temp_config, store)
    provider = FakeProvider()
    runtime.router.for_agent = lambda agent: provider
    runtime.adapter.sync_registry = lambda: _async_value(["nmap_scan"])
    runtime.adapter.invoke = lambda tool, args, session_id: _async_value(
        NormalizedToolResult(tool, True, 4, "port 80 open")
    )

    result = await runtime.run_task(session, "recon", "enumerate the challenge")

    assert result.tool_calls == 1
    assert provider.calls == 2
    assert store.list_tasks(session)[0]["status"] == "completed"
    assert store.list_sessions()[0]["state_json"].find("Observed a service") >= 0


async def test_investigation_auto_delegates_recon_and_specialist(temp_config, tmp_path):
    temp_config.save("config.yaml", {
        "database_path": str(tmp_path / "state.db"),
        "raw_output_dir": str(tmp_path / "raw"),
    })
    temp_config.save("scope.yaml", {"targets": ["challenge.local"], "cidrs": [], "hostnames": [], "urls": []})
    store = StateStore(tmp_path / "state.db")
    session = store.create_session("CTF", "challenge.local", temp_config.load("scope.yaml"))
    runtime = InvestigationRuntime(temp_config, store)
    runtime.router.for_agent = lambda agent: FakeProvider()
    runtime.adapter.sync_registry = lambda: _async_value(["nmap_scan", "sqlmap_scan"])
    runtime.adapter.invoke = lambda tool, args, session_id: _async_value(
        NormalizedToolResult(tool, True, 4, "evidence")
    )

    results = await runtime.run_investigation(session, "web challenge enumeration")

    assert len(results) == 2
    assert [task["agent"] for task in store.list_tasks(session)] == ["recon", "web"]
    assert store.get_session(session)["state_json"].find("completed_tasks") >= 0


async def _async_value(value):
    return value
