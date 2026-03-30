from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters.base import ProviderResponse
from ai_proxy.api.proxy import router as proxy_router
from ai_proxy.app import create_app


class FakeAdapter:
    def __init__(self, response: ProviderResponse | None = None, error: httpx.RequestError | None = None) -> None:
        self._response = response
        self._error = error

    async def chat_completions(self, request_body: dict[str, Any], headers: dict[str, str]) -> ProviderResponse:
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response

    async def stream_chat_completions(self, request_body: dict[str, Any], headers: dict[str, str]):
        msg = "Streaming is not used in this test"
        raise AssertionError(msg)

    async def list_models(self) -> list[dict[str, Any]]:
        return []


@pytest.mark.asyncio
async def test_non_streaming_provider_http_error_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakeAdapter(
        response=ProviderResponse(
            status_code=429,
            headers={"content-type": "application/json", "x-upstream": "rate-limit"},
            body=b'{"error":{"message":"Too many requests"}}',
            content_type="application/json",
        )
    )
    route = SimpleNamespace(provider_name="openrouter", mapped_model="provider-model", adapter=adapter)
    logged_entries = []

    async def capture_log(entry):
        logged_entries.append(entry)

    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)
    monkeypatch.setattr(proxy_router, "enqueue_log", capture_log)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 429
    assert response.json() == {"error": {"message": "Too many requests"}}
    assert response.headers["x-upstream"] == "rate-limit"
    assert logged_entries[0].response_status_code == 429
    assert logged_entries[0].error_message == "Too many requests"


@pytest.mark.asyncio
async def test_non_streaming_transport_errors_become_gateway_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakeAdapter(error=httpx.ConnectError("boom", request=httpx.Request("POST", "https://provider.example")))
    route = SimpleNamespace(provider_name="openrouter", mapped_model="provider-model", adapter=adapter)
    logged_entries = []

    async def capture_log(entry):
        logged_entries.append(entry)

    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)
    monkeypatch.setattr(proxy_router, "enqueue_log", capture_log)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 502
    assert response.json() == {"error": {"message": "Provider transport error: boom"}}
    assert logged_entries[0].response_status_code == 502
    assert logged_entries[0].error_message == "boom"
