"""E2E tests for bypass and key mapping — real HTTP requests through the proxy.

These tests start the FastAPI proxy app with a mock upstream provider,
send real HTTP requests, and verify the Authorization header that
actually reaches the upstream. No monkeypatching of internal modules.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters import registry as adapter_registry
from ai_proxy.app import create_app
from ai_proxy.config import loader as config_loader
from ai_proxy.config.settings import (
    AppConfig,
    BypassConfig,
    KeyMappingEntry,
    ProviderConfig,
    get_settings,
)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


CHAT_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
).encode()


class UpstreamCapture:
    """Collects Authorization headers from requests hitting the mock upstream."""

    def __init__(self) -> None:
        self.captured_auth_headers: list[str | None] = []

    async def handler(self, request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization")
        self.captured_auth_headers.append(auth)
        return httpx.Response(200, content=CHAT_RESPONSE, headers={"content-type": "application/json"})


def _build_app_with_config(
    config: AppConfig,
    upstream_url: str,
    monkeypatch: pytest.MonkeyPatch,
    api_keys: str = "",
) -> Any:
    monkeypatch.setattr(config_loader, "_app_config", config)

    settings = get_settings()
    monkeypatch.setattr(settings, "api_keys", api_keys)

    adapter_registry.build_registry(config)
    for adapter in adapter_registry.get_adapter_registry().values():
        adapter.endpoint_url = upstream_url

    return create_app()


@pytest.mark.asyncio
async def test_e2e_bypass_forwards_client_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full E2E: client sends own key -> proxy forwards it to upstream."""
    capture = UpstreamCapture()
    mock_transport = httpx.MockTransport(capture.handler)

    config = AppConfig(
        bypass=BypassConfig(enabled=True),
        providers={"mockprovider": ProviderConfig(endpoint="https://mock.provider/v1")},
        model_mappings={"test-model": "mockprovider:test-model"},
    )
    app = _build_app_with_config(config, "https://mock.provider/v1", monkeypatch)

    for adapter in adapter_registry.get_adapter_registry().values():
        adapter._client_transport = mock_transport

    monkeypatch.setattr(httpx, "AsyncClient", _make_transport_injector(mock_transport))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-or-v1-my-own-key"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hello!"
    assert len(capture.captured_auth_headers) == 1
    assert capture.captured_auth_headers[0] == "Bearer sk-or-v1-my-own-key"


@pytest.mark.asyncio
async def test_e2e_bypass_rejects_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full E2E: bypass mode rejects requests without an API key."""
    config = AppConfig(
        bypass=BypassConfig(enabled=True),
        providers={"mockprovider": ProviderConfig(endpoint="https://mock.provider/v1")},
        model_mappings={"test-model": "mockprovider:test-model"},
    )
    app = _build_app_with_config(config, "https://mock.provider/v1", monkeypatch)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_e2e_key_mapping_selects_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full E2E: client key hash is mapped to a specific upstream key."""
    capture = UpstreamCapture()
    mock_transport = httpx.MockTransport(capture.handler)

    client_key = "my-proxy-client-key"
    client_hash = _sha256(client_key)
    mapped_upstream_key = "sk-or-v1-mapped-upstream"

    config = AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"mockprovider": mapped_upstream_key}),
        },
        providers={"mockprovider": ProviderConfig(endpoint="https://mock.provider/v1")},
        model_mappings={"test-model": "mockprovider:test-model"},
    )
    app = _build_app_with_config(config, "https://mock.provider/v1", monkeypatch, api_keys=client_key)

    monkeypatch.setattr(httpx, "AsyncClient", _make_transport_injector(mock_transport))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert len(capture.captured_auth_headers) == 1
    assert capture.captured_auth_headers[0] == f"Bearer {mapped_upstream_key}"


@pytest.mark.asyncio
async def test_e2e_no_mapping_uses_default_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full E2E: client with no mapping -> adapter's default key is used."""
    capture = UpstreamCapture()
    mock_transport = httpx.MockTransport(capture.handler)

    client_key = "unmapped-client"
    default_provider_key = "sk-default-provider"

    config = AppConfig(
        providers={
            "mockprovider": ProviderConfig(
                endpoint="https://mock.provider/v1",
                api_key_env="MOCK_PROVIDER_KEY",
            ),
        },
        model_mappings={"test-model": "mockprovider:test-model"},
    )
    monkeypatch.setenv("MOCK_PROVIDER_KEY", default_provider_key)
    app = _build_app_with_config(config, "https://mock.provider/v1", monkeypatch, api_keys=client_key)

    monkeypatch.setattr(httpx, "AsyncClient", _make_transport_injector(mock_transport))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert len(capture.captured_auth_headers) == 1
    assert capture.captured_auth_headers[0] == f"Bearer {default_provider_key}"


@pytest.mark.asyncio
async def test_e2e_key_mapping_multi_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full E2E: same client mapped to different keys for different providers."""
    captured_requests: list[tuple[str, str | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, content=CHAT_RESPONSE, headers={"content-type": "application/json"})

    mock_transport = httpx.MockTransport(handler)
    client_key = "multi-prov-client"
    client_hash = _sha256(client_key)

    config = AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"provider_a": "sk-key-for-a", "provider_b": "sk-key-for-b"}),
        },
        providers={
            "provider_a": ProviderConfig(endpoint="https://a.provider/v1"),
            "provider_b": ProviderConfig(endpoint="https://b.provider/v1"),
        },
        model_mappings={"model-a": "provider_a:model-a", "model-b": "provider_b:model-b"},
    )
    monkeypatch.setattr(config_loader, "_app_config", config)
    settings = get_settings()
    monkeypatch.setattr(settings, "api_keys", client_key)
    adapter_registry.build_registry(config)
    app = create_app()
    monkeypatch.setattr(httpx, "AsyncClient", _make_transport_injector(mock_transport))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp_a = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "model-a", "messages": [{"role": "user", "content": "hi"}]},
        )
        resp_b = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "model-b", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    assert len(captured_requests) == 2
    assert captured_requests[0][1] == "Bearer sk-key-for-a"
    assert captured_requests[1][1] == "Bearer sk-key-for-b"
    assert "a.provider" in captured_requests[0][0]
    assert "b.provider" in captured_requests[1][0]


def _make_transport_injector(mock_transport: httpx.MockTransport):
    """Return a patched AsyncClient class that injects mock transport."""

    class PatchedAsyncClient(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            kwargs["transport"] = mock_transport
            super().__init__(**kwargs)

    return PatchedAsyncClient
