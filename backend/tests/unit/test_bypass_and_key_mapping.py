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
from ai_proxy.security.auth import hash_api_key


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
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, "hash"))
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
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash))
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
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash))
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
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, _sha256("my-key")))
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
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, client_hash))
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


# ── Bypass takes precedence over key mapping ──────────────────────────


@pytest.mark.asyncio
async def test_bypass_takes_precedence_over_key_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both bypass and key_mapping are configured, bypass wins."""
    adapter = CapturingAdapter()
    client_key = "dual-mode-client"
    client_hash = _sha256(client_key)

    config = AppConfig(
        bypass=BypassConfig(enabled=True),
        key_mappings={
            client_hash: KeyMappingEntry(provider_keys={"openrouter": "sk-or-should-not-be-used"}),
        },
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
            headers={"Authorization": f"Bearer {client_key}"},
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert response.status_code == 200
    assert adapter.last_override_key == client_key


# ── Unit tests for resolve_provider_key ───────────────────────────────


def test_resolve_provider_key_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AppConfig(bypass=BypassConfig(enabled=True))
    monkeypatch.setattr(key_resolution_mod, "get_app_config", lambda: config)
    assert resolve_provider_key("client-key", "openrouter") == "client-key"


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


# ── Config loading tests ──────────────────────────────────────────────


def test_bypass_config_loaded_from_yaml_with_secrets(tmp_path) -> None:
    from ai_proxy.config.loader import load_config

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
bypass:
  enabled: true
""".strip()
    )

    secrets_path = tmp_path / "config.secrets.yml"
    secrets_path.write_text(
        """
key_mappings:
  my-client-key:
    provider_keys:
      openrouter: "sk-or-v1-mapped"
      anthropic: "sk-ant-mapped"
""".strip()
    )

    config = load_config(str(config_path), secrets_path=str(secrets_path))
    assert config.bypass.enabled is True
    client_hash = _sha256("my-client-key")
    assert client_hash in config.key_mappings
    assert config.key_mappings[client_hash].provider_keys["openrouter"] == "sk-or-v1-mapped"
    assert config.key_mappings[client_hash].provider_keys["anthropic"] == "sk-ant-mapped"


def test_bypass_config_defaults_when_absent(tmp_path) -> None:
    from ai_proxy.config.loader import load_config

    config_path = tmp_path / "config.yml"
    config_path.write_text("providers: {}")
    config = load_config(str(config_path))
    assert config.bypass.enabled is False
    assert config.key_mappings == {}


# ── Adapter override tests ────────────────────────────────────────────


def test_adapter_build_headers_with_override() -> None:
    from ai_proxy.adapters.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        provider_name="test",
        endpoint_url="https://example.com/v1",
        api_key="default-key",
    )

    headers_default = adapter._build_headers({})
    assert headers_default["Authorization"] == "Bearer default-key"

    headers_override = adapter._build_headers({}, override_api_key="override-key")
    assert headers_override["Authorization"] == "Bearer override-key"

    headers_none = adapter._build_headers({}, override_api_key=None)
    assert headers_none["Authorization"] == "Bearer default-key"


# ── Auth bypass tests ─────────────────────────────────────────────────


def test_validate_proxy_api_key_bypass_mode() -> None:
    from ai_proxy.security.auth import validate_proxy_api_key

    ok, key_hash = validate_proxy_api_key("any-random-key", bypass_enabled=True)
    assert ok is True
    assert key_hash == hash_api_key("any-random-key")

    ok, key_hash = validate_proxy_api_key(None, bypass_enabled=True)
    assert ok is False
    assert key_hash == ""


# ── /v1/models with bypass ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_models_with_bypass_accepts_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /v1/models works with any key when bypass is enabled."""
    bypass_config = AppConfig(
        bypass=BypassConfig(enabled=True),
        model_mappings={"test-model": "openrouter:test-model"},
    )
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: bypass_config)
    monkeypatch.setattr(proxy_router, "check_model_access", lambda _hash, _model: (True, ""))

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
