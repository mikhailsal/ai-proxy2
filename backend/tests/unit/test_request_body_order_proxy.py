from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters.base import ProviderResponse
from ai_proxy.api.proxy import router as proxy_router
from ai_proxy.app import create_app
from ai_proxy.config.settings import AppConfig

_CLIENT_REQUEST_RAW = (
    '{"messages":[{"role":"user","content":"ORDER_PROBE_20260510_A"}],'
    '"marker":"ORDER_PROBE_20260510_A",'
    '"tools":[{"type":"function","function":{"name":"tool_second","parameters":'
    '{"type":"object","properties":{"zeta_nested":{"type":"string"},"alpha_nested":{"type":"string"}},'
    '"required":["zeta_required","alpha_required"]}}},'
    '{"type":"function","function":{"name":"tool_first","parameters":'
    '{"type":"object","properties":{"beta_nested":{"type":"string"},"gamma_nested":{"type":"string"}},'
    '"required":["beta_required","gamma_required"]}}}],'
    '"stream":false,"model":"gpt-4o-mini"}'
)

_PROVIDER_REQUEST_BODY: dict[str, Any] = {
    "marker": "ORDER_PROBE_20260510_A",
    "stream": False,
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "tool_second",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "zeta_nested": {"type": "string"},
                        "alpha_nested": {"type": "string"},
                    },
                    "required": ["zeta_required", "alpha_required"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tool_first",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "beta_nested": {"type": "string"},
                        "gamma_nested": {"type": "string"},
                    },
                    "required": ["beta_required", "gamma_required"],
                },
            },
        },
    ],
    "messages": [{"role": "user", "content": "ORDER_PROBE_20260510_A"}],
    "model": "provider-model",
}

_PROVIDER_REQUEST_RAW = (
    '{"marker":"ORDER_PROBE_20260510_A","stream":false,'
    '"tools":[{"type":"function","function":{"name":"tool_second","parameters":'
    '{"type":"object","properties":{"zeta_nested":{"type":"string"},"alpha_nested":{"type":"string"}},'
    '"required":["zeta_required","alpha_required"]}}},'
    '{"type":"function","function":{"name":"tool_first","parameters":'
    '{"type":"object","properties":{"beta_nested":{"type":"string"},"gamma_nested":{"type":"string"}},'
    '"required":["beta_required","gamma_required"]}}}],'
    '"messages":[{"role":"user","content":"ORDER_PROBE_20260510_A"}],"model":"provider-model"}'
)


class OrderedBodyAdapter:
    def __init__(self, response: ProviderResponse) -> None:
        self._response = response

    async def chat_completions(
        self,
        request_body: dict[str, Any],
        headers: dict[str, str],
        *,
        override_api_key: str | None = None,
    ) -> ProviderResponse:
        return self._response

    async def stream_chat_completions(
        self,
        request_body: dict[str, Any],
        headers: dict[str, str],
        *,
        override_api_key: str | None = None,
    ):
        msg = "Streaming is not used in this test"
        raise AssertionError(msg)

    async def list_models(self) -> list[dict[str, Any]]:
        return []


def _default_config() -> AppConfig:
    return AppConfig()


def _auth_stub(_request):
    return "proxy-key", "hash", False


def _route_stub(route: SimpleNamespace):
    async def stub(*_args):
        return "gpt-4o-mini", route

    return stub


@pytest.mark.asyncio
async def test_non_streaming_logs_exact_client_and_provider_request_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    route = SimpleNamespace(
        provider_name="openrouter",
        mapped_model="provider-model",
        adapter=OrderedBodyAdapter(
            ProviderResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":5,"completion_tokens":3,"total_tokens":8}}',
                content_type="application/json",
                sent_request_body=_PROVIDER_REQUEST_BODY,
                sent_request_body_raw=_PROVIDER_REQUEST_RAW,
            )
        ),
    )
    logged_entries: list[Any] = []

    async def capture_log(entry: Any) -> None:
        logged_entries.append(entry)

    monkeypatch.setattr(proxy_router, "get_app_config", _default_config)
    monkeypatch.setattr(proxy_router, "authenticate_proxy_request", _auth_stub)
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "validate_and_route_request", _route_stub(route))
    monkeypatch.setattr(proxy_router, "enqueue_log", capture_log)
    monkeypatch.setattr(proxy_router, "resolve_provider_key", lambda *_args, **_kw: None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key", "Content-Type": "application/json"},
            content=_CLIENT_REQUEST_RAW,
        )

    assert response.status_code == 200
    entry = logged_entries[0]
    assert entry.client_request_body_raw == _CLIENT_REQUEST_RAW
    assert entry.request_body_raw == _PROVIDER_REQUEST_RAW
    assert [tool["function"]["name"] for tool in entry.request_body["tools"]] == ["tool_second", "tool_first"]
    assert entry.request_body["tools"][0]["function"]["parameters"]["required"] == [
        "zeta_required",
        "alpha_required",
    ]
