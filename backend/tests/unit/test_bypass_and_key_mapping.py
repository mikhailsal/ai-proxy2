"""E2E tests for bypass mode and key mapping features.

Tests verify the full request lifecycle: client sends key -> proxy resolves
the correct provider API key -> adapter sends the right Authorization header.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters.base import ProviderResponse
from ai_proxy.api.proxy import router as proxy_router
from ai_proxy.app import create_app
from ai_proxy.config.settings import (
    AppConfig,
    BypassConfig,
    KeyMappingEntry,
    ProviderConfig,
)
from ai_proxy.core import key_resolution as key_resolution_mod
from ai_proxy.core.key_resolution import resolve_provider_key
from ai_proxy.services.model_catalog import CatalogModel


class CapturingAdapter:
    """Adapter that captures the override_api_key passed to it."""

    def __init__(self) -> None:
        self.last_override_key: str | None = "NOT_CALLED"

    async def chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderResponse:
        self.last_override_key = override_api_key
        return ProviderResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}',
            content_type="application/json",
        )

    async def stream_chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ):
        raise AssertionError("streaming not used in this test")

    async def list_models(self) -> list[dict[str, Any]]:
        return []


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _patch_common(monkeypatch, adapter, *, provider_name: str = "openrouter"):
    """Shared monkeypatches: access control, modifications, logging, routing."""
    route = SimpleNamespace(provider_name=provider_name, mapped_model="test-model", adapter=adapter)
    logged = []

    async def capture_log(entry):
        logged.append(entry)

    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)
    monkeypatch.setattr(proxy_router, "enqueue_log", capture_log)
    return logged


# ── Bypass mode tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bypass_forwards_client_key_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """When bypass is enabled, the client's own key is sent upstream."""
    adapter = CapturingAdapter()
    bypass_config = AppConfig(
        bypass=BypassConfig(enabled=True),
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: bypass_config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: bypass_config)
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-or-v1-my-own-openrouter-key"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key == "sk-or-v1-my-own-openrouter-key"


@pytest.mark.asyncio
async def test_bypass_rejects_empty_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass mode still requires a non-empty API key."""
    bypass_config = AppConfig(bypass=BypassConfig(enabled=True))
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: bypass_config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: bypass_config)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bypass_disabled_uses_default_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """When bypass is disabled, override_api_key is None (adapter uses its default)."""
    adapter = CapturingAdapter()
    normal_config = AppConfig(
        bypass=BypassConfig(enabled=False),
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: normal_config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: normal_config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, "hash", True))
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key is None


# ── Key mapping tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_key_mapping_routes_to_correct_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client key hash is mapped to a specific provider key."""
    adapter = CapturingAdapter()
    client_key = "my-proxy-client-key"
    client_hash = _sha256(client_key)
    mapped_provider_key = "sk-or-v1-mapped-openrouter-key"

    mapping_config = AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"openrouter": mapped_provider_key}),
        },
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: mapping_config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: mapping_config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash, True))
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key == mapped_provider_key


def _multi_provider_config(client_hash: str) -> AppConfig:
    return AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"openrouter": "sk-or-mapped", "anthropic": "sk-ant-mapped"}),
        },
        providers={
            "openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1"),
            "anthropic": ProviderConfig(endpoint="https://api.anthropic.com/v1"),
        },
        model_mappings={"or-model": "openrouter:or-model", "ant-model": "anthropic:ant-model"},
    )


@pytest.mark.asyncio
async def test_key_mapping_different_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Key mapping picks the right key based on which provider is selected."""
    adapter_or, adapter_ant = CapturingAdapter(), CapturingAdapter()
    client_key = "multi-provider-client"
    client_hash = _sha256(client_key)
    config = _multi_provider_config(client_hash)

    monkeypatch.setattr(proxy_router, "get_app_config", lambda: config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash, True))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))

    async def noop_log(entry):
        pass

    monkeypatch.setattr(proxy_router, "enqueue_log", noop_log)

    app = create_app()
    transport = ASGITransport(app=app)

    route_or = SimpleNamespace(provider_name="openrouter", mapped_model="or-model", adapter=adapter_or)
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route_or)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "or-model", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    assert adapter_or.last_override_key == "sk-or-mapped"

    route_ant = SimpleNamespace(provider_name="anthropic", mapped_model="ant-model", adapter=adapter_ant)
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route_ant)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "ant-model", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    assert adapter_ant.last_override_key == "sk-ant-mapped"


@pytest.mark.asyncio
async def test_key_mapping_no_match_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """When client key has no mapping entry, adapter default is used."""
    adapter = CapturingAdapter()
    config = AppConfig(
        key_mappings={
            _sha256("other-client"): KeyMappingEntry(provider_keys={"openrouter": "sk-or-other"}),
        },
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, _sha256("my-key"), True))
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer my-key"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key is None


@pytest.mark.asyncio
async def test_key_mapping_provider_not_in_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """When client has a mapping but not for the target provider, adapter default is used."""
    adapter = CapturingAdapter()
    client_key = "partial-mapping-client"
    client_hash = _sha256(client_key)

    config = AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"anthropic": "sk-ant-only"}),
        },
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash, True))
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key is None


# ── Known key mapping takes precedence over bypass ─────────────────────


@pytest.mark.asyncio
async def test_known_key_mapping_takes_precedence_over_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """When key is known and has a mapping, the mapped provider key is used
    even when bypass is enabled. Bypass only applies to unknown keys."""
    adapter = CapturingAdapter()
    client_key = "dual-mode-client"
    client_hash = _sha256(client_key)
    mapped_provider_key = "sk-or-mapped-for-known-client"

    config = AppConfig(
        bypass=BypassConfig(enabled=True),
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"openrouter": mapped_provider_key}),
        },
        api_keys=[client_key],
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash, True))
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key == mapped_provider_key


@pytest.mark.asyncio
async def test_unknown_key_uses_bypass_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When key is NOT known but bypass is enabled, the client's raw key
    is forwarded to the provider."""
    adapter = CapturingAdapter()
    unknown_client_key = "sk-or-v1-external-user-key"

    config = AppConfig(
        bypass=BypassConfig(enabled=True),
        providers={"openrouter": ProviderConfig(endpoint="https://openrouter.ai/api/v1")},
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: config)
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    _patch_common(monkeypatch, adapter)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {unknown_client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key == unknown_client_key


# ── Unit tests for resolve_provider_key ───────────────────────────────


def test_resolve_provider_key_known_key_with_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Known key with a mapping -> mapped provider key, even with bypass on."""
    client_hash = _sha256("client-key")
    config = AppConfig(
        bypass=BypassConfig(enabled=True),
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"openrouter": "mapped-key"}),
        },
    )
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("client-key", "openrouter", is_known_key=True) == "mapped-key"


def test_resolve_provider_key_known_key_without_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Known key without mapping -> None (adapter default), bypass not used."""
    config = AppConfig(bypass=BypassConfig(enabled=True))
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("client-key", "openrouter", is_known_key=True) is None


def test_resolve_provider_key_unknown_key_bypass_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown key + bypass enabled -> forward client key."""
    config = AppConfig(bypass=BypassConfig(enabled=True))
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("external-key", "openrouter", is_known_key=False) == "external-key"


def test_resolve_provider_key_unknown_key_bypass_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unknown key + bypass disabled -> None."""
    config = AppConfig(bypass=BypassConfig(enabled=False))
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("external-key", "openrouter", is_known_key=False) is None


def test_resolve_provider_key_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    client_hash = _sha256("client-key")
    config = AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"openrouter": "mapped-key"}),
        }
    )
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("client-key", "openrouter") == "mapped-key"


def test_resolve_provider_key_no_match(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AppConfig()
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("client-key", "openrouter") is None


def test_resolve_provider_key_mapping_wrong_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client_hash = _sha256("client-key")
    config = AppConfig(
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"anthropic": "ant-key"}),
        }
    )
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("client-key", "openrouter") is None


# ── Config loading, adapter override, and auth bypass tests are in ─────
# ── test_support_modules.py to keep this file focused on key routing. ─


@pytest.mark.asyncio
async def test_list_models_with_bypass_accepts_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /v1/models works with any key when bypass is enabled."""
    bypass_config = AppConfig(
        bypass=BypassConfig(enabled=True),
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: bypass_config)
    monkeypatch.setattr(proxy_router, "check_model_access", lambda _hash, _model: (True, ""))

    async def fake_catalog(*, config=None):
        return {
            "test-model": CatalogModel(
                client_model="test-model",
                provider_name="openrouter",
                mapped_model="test-model",
            )
        }

    monkeypatch.setattr(proxy_router, "get_proxy_model_catalog", fake_catalog)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/models",
            headers={"Authorization": "Bearer any-openrouter-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "list"
    assert any(m["id"] == "test-model" for m in data["data"])
