from __future__ import annotations

from fenrys.config import ConfigManager
from .registry import ProviderRegistry


class ProviderRouter:
    """Resolves the current agent mapping on every task, enabling hot swap."""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.registry = ProviderRegistry(config)

    def for_agent(self, agent: str):
        mapping = self.config.resolve_agent(agent)
        return self.registry.build(mapping["provider"], mapping["model"])
