from .openai_compatible_provider import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    """Official OpenAI uses the same Chat Completions contract."""

    def __init__(self, config, model=None):
        config = dict(config)
        config.setdefault("base_url", "https://api.openai.com/v1")
        super().__init__("openai", config, model or "gpt-4o-mini")
