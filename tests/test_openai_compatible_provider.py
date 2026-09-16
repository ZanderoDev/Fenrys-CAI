import json

import httpx
import pytest

from fenrys_cai.llm.primary import PrimaryReasoner
from fenrys_cai.llm.provider import LLMError, LLMProvider
from fenrys_cai.models import ToolSpec
from fenrys_cai.state import CyberState


class Response:
    def __init__(self, payload, status=200): self.payload, self.status_code = payload, status
    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.invalid")
            raise httpx.HTTPStatusError("error", request=request, response=httpx.Response(self.status_code, request=request))
    def json(self): return self.payload


def test_openai_compatible_url_model_headers_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    def post(url, *, json, headers, timeout):
        captured.update(url=url, payload=json, headers=headers, timeout=timeout)
        return Response({"choices": [{"message": {"content": '{"decision":"tool","tool":"execute","arguments":{"session_id":"s","command":"pwd"},"rationale":"safe","confidence":0.8}'}}]})
    monkeypatch.setattr(httpx, "post", post)
    secret = "synthetic-lapakvip-secret"
    provider = LLMProvider("https://router.lapakvip.com/api/v1", secret, "lv/deepseek-v4-pro-0813")
    data = provider.complete_json("system", "user")
    assert captured["url"] == "https://router.lapakvip.com/api/v1/chat/completions"
    assert captured["payload"]["model"] == "lv/deepseek-v4-pro-0813"
    assert captured["headers"]["Authorization"] == f"Bearer {secret}"
    assert "x-api-key" not in captured["headers"]
    assert data["tool"] == "execute"
    assert secret not in json.dumps({"error": "provider error", "payload": {"model": captured["payload"]["model"]}})


def test_missing_key_fails_safely_without_serialization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FENRYS_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    provider = LLMProvider("https://router.lapakvip.com/api/v1", api_key="", model="lv/deepseek-v4-pro-0813")
    assert not provider.available


@pytest.mark.parametrize(("status", "code"), [(401, "auth_failure"), (429, "rate_limited"), (500, "provider_error")])
def test_openai_compatible_error_normalization(monkeypatch: pytest.MonkeyPatch, status: int, code: str) -> None:
    def post(*args, **kwargs): return Response({}, status)
    monkeypatch.setattr(httpx, "post", post)
    provider = LLMProvider("https://router.lapakvip.com/api/v1", "synthetic-secret", "lv/deepseek-v4-pro-0813")
    with pytest.raises(LLMError) as error:
        provider.complete("system", "user")
    assert error.value.code == code
    assert "synthetic-secret" not in str(error.value)


def test_openai_compatible_primary_reasoner_structured_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*args, **kwargs):
        return Response({"choices": [{"message": {"content": '{"decision":"tool","tool":"execute","arguments":{"session_id":"local","command":"pwd"},"rationale":"inspect workspace","confidence":0.8}'}}]})
    monkeypatch.setattr(httpx, "post", post)
    provider = LLMProvider("https://router.lapakvip.com/api/v1", "synthetic-secret", "lv/deepseek-v4-pro-0813")
    decision = PrimaryReasoner(provider).decide(CyberState("local", "Inspect current workspace"), [ToolSpec("execute", "Run command", {"type": "object"}, ("terminal",))])
    assert decision.kind == "tool"
    assert decision.tool == "execute"
    assert decision.arguments == {"session_id": "local", "command": "pwd"}


def test_explicit_custom_protocol_overrides_unrelated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://unrelated.example")
    monkeypatch.setenv("FENRYS_LLM_PROTOCOL", "openai")
    provider = LLMProvider("https://custom.example/api/v1", "synthetic", "custom-model")
    url, _ = provider._url_and_payload([], 10)
    assert provider.protocol == "openai"
    assert url == "https://custom.example/api/v1/chat/completions"
