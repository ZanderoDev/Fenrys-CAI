def test_default_providers_has_openrouter_settings():
    from fenrys.config.manager import DEFAULT_PROVIDERS

    assert DEFAULT_PROVIDERS["providers"]["openrouter"] == {
        "type": "openai_compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_headers": {
            "HTTP-Referer": "https://fenrys-cai.local",
            "X-Title": "Fenrys-CAI",
        },
    }


def test_agent_model_hot_swap(temp_config):
    temp_config.write_initial()
    temp_config.set_agent_model("web", "local_ollama", "llama3.1")
    assert temp_config.resolve_agent("web") == {"provider": "local_ollama", "model": "llama3.1"}


def test_partial_config_has_defaults(temp_config):
    temp_config.save("agents.yaml", {"agents": {"web": {"provider": "local_ollama", "model": "x"}}})
    assert temp_config.resolve_agent("web")["model"] == "x"
    assert temp_config.resolve_agent("recon")["provider"] == "openrouter"


def test_write_initial_persists_initial_target(temp_config):
    temp_config.write_initial(mode="CTF", target="challenge.local")

    assert temp_config.load("config.yaml")["mode"] == "CTF"
    assert "challenge.local" in temp_config.load("scope.yaml")["targets"]


def test_project_local_config_is_detected_and_updated(tmp_path):
    from fenrys.config import ConfigManager

    project_root = tmp_path / "project"
    project_root.mkdir()
    manager = ConfigManager(project_root=project_root, home=tmp_path / "home")
    project_config = project_root / ".fenrys"
    project_config.mkdir()
    (project_config / "providers.yaml").write_text(
        "providers:\n  local:\n    type: openai_compatible\n    base_url: http://localhost:1234/v1\n",
        encoding="utf-8",
    )

    assert manager.is_configured()
    manager.save("providers.yaml", {"providers": {"local": {"type": "openai_compatible"}}})
    assert "providers:" in (project_config / "providers.yaml").read_text(encoding="utf-8")
