def test_agent_model_hot_swap(temp_config):
    temp_config.write_initial()
    temp_config.set_agent_model("web", "local_ollama", "llama3.1")
    assert temp_config.resolve_agent("web") == {"provider": "local_ollama", "model": "llama3.1"}


def test_partial_config_has_defaults(temp_config):
    temp_config.save("agents.yaml", {"agents": {"web": {"provider": "local_ollama", "model": "x"}}})
    assert temp_config.resolve_agent("web")["model"] == "x"
    assert temp_config.resolve_agent("recon")["provider"] == "anthropic"
