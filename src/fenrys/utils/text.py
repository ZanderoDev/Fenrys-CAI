def bounded_text(value: str, limit: int = 4096) -> str:
    """Keep model-facing text bounded while preserving an explicit truncation marker."""
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[truncated; raw output remains on disk]"
