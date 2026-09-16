from __future__ import annotations

import json
import os
from typing import Any

import httpx


class LLMError(RuntimeError):
    """Normalized LLM provider error."""
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class LLMProvider:
    """Single provider-neutral LLM interface for primary and specialist reasoning.

    Supports Anthropic-compatible and OpenAI-compatible HTTP endpoints.
    No vendor SDK is imported. Configuration comes from environment or constructor.
    """

    def __init__(self, endpoint: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float = 30.0, protocol: str | None = None) -> None:
        self.endpoint = endpoint or os.environ.get("FENRYS_LLM_ENDPOINT") or os.environ.get("ANTHROPIC_BASE_URL")
        self.api_key = api_key or os.environ.get("FENRYS_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        self.model = model or os.environ.get("FENRYS_LLM_MODEL") or os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514"
        self.timeout = timeout
        configured_protocol = os.environ.get("FENRYS_LLM_PROTOCOL", "").lower()
        self.protocol = protocol or configured_protocol or ("anthropic" if "anthropic" in (self.endpoint or "").lower() else "openai")
        if self.protocol not in {"openai", "anthropic"}:
            raise ValueError("FENRYS_LLM_PROTOCOL must be 'openai' or 'anthropic'")

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            if self.protocol == "anthropic":
                headers["x-api-key"] = self.api_key
        return headers

    def _url_and_payload(self, messages: list[dict[str, str]], max_tokens: int) -> tuple[str, dict[str, Any]]:
        base = (self.endpoint or "").rstrip("/")
        if self.protocol == "anthropic":
            url = f"{base}/v1/messages" if not base.endswith("/messages") else base
            headers_extra = {"anthropic-version": "2023-06-01"}
            payload = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        else:
            url = f"{base}/chat/completions" if not base.endswith("/completions") else base
            headers_extra = {}
            payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        return url, payload

    def complete(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        """Send a completion request and return extracted text.

        Raises LLMError with normalized codes: unavailable, timeout, auth_failure,
        rate_limited, provider_error, connection_failure, malformed_response, empty_response.
        """
        if not self.endpoint:
            raise LLMError("unavailable", "No LLM endpoint configured")
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        url, payload = self._url_and_payload(messages, max_tokens)
        headers = self._headers()
        if self.protocol == "anthropic":
            headers["anthropic-version"] = "2023-06-01"

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMError("timeout", "LLM request timed out") from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise LLMError("auth_failure", "LLM authentication failed") from exc
            if exc.response.status_code == 429:
                raise LLMError("rate_limited", "LLM rate limited") from exc
            raise LLMError("provider_error", f"LLM provider error: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise LLMError("connection_failure", "LLM connection failed") from exc

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError("malformed_response", "LLM returned non-JSON HTTP response") from exc

        text = self._extract_text(body)
        if not text:
            raise LLMError("empty_response", "LLM returned empty content")
        return text

    def complete_json(self, system: str, user: str, *, max_tokens: int = 1024) -> dict[str, Any]:
        """Send a completion request and parse the response as JSON.

        Handles markdown fences. Raises LLMError on any failure.
        """
        text = self.complete(system, user, max_tokens=max_tokens).strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMError("malformed_response", "LLM returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("malformed_response", "LLM JSON response is not an object")
        return data

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        """Extract text from Anthropic or OpenAI response format."""
        content = body.get("content")
        if isinstance(content, list) and content:
            text = "".join(block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text")
            if text:
                return text
        choices = body.get("choices", [])
        if choices and isinstance(choices, list):
            message = choices[0].get("message", {})
            return message.get("content", "") or ""
        return ""
