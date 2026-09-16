"""Unified provider-neutral LLM interface for Fenrys-CAI."""

from .provider import LLMError, LLMProvider

__all__ = ["LLMError", "LLMProvider"]
