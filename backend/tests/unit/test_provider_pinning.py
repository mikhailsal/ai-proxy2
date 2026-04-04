"""Tests for provider pinning via +suffix in model mappings."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters.base import ProviderResponse
from ai_proxy.api.proxy import router as proxy_router
from ai_proxy.app import create_app
from ai_proxy.config.settings import AppConfig
from ai_proxy.core.routing import RouteResult, _parse_mapping

# ── _parse_mapping unit tests ─────────────────────────────────────────


class TestParseMapping:
    def test_plain_mapping(self):
        provider, model, pinned = _parse_mapping("openrouter:minimax/minimax-m2.7")
        assert provider == "openrouter"
        assert model == "minimax/minimax-m2.7"
        assert pinned is None

    def test_single_provider_pin(self):
        provider, model, pinned = _parse_mapping("openrouter:minimax/minimax-m2.7+minimax")
        assert provider == "openrouter"
        assert model == "minimax/minimax-m2.7"
        assert pinned == ["minimax"]

    def test_multiple_provider_pins(self):
        provider, model, pinned = _parse_mapping("openrouter:deepseek/deepseek-v3.2+deepinfra,together")
        assert provider == "openrouter"
        assert model == "deepseek/deepseek-v3.2"
        assert pinned == ["deepinfra", "together"]

    def test_pin_with_slash_slug(self):
        provider, model, pinned = _parse_mapping("openrouter:deepseek/deepseek-r1+deepinfra/turbo")
        assert provider == "openrouter"
        assert model == "deepseek/deepseek-r1"
        assert pinned == ["deepinfra/turbo"]

    def test_no_colon_mapping(self):
        provider, model, pinned = _parse_mapping("some-provider")
        assert provider == "some-provider"
        assert model == "some-provider"
        assert pinned is None

    def test_empty_pin_ignored(self):
        provider, model, pinned = _parse_mapping("openrouter:model+")
        assert provider == "openrouter"
        assert model == "model"
        assert pinned is None

    def test_whitespace_in_pins_stripped(self):
        provider, model, pinned = _parse_mapping("openrouter:model+ openai , together ")
        assert pinned == ["openai", "together"]

    def test_model_with_colon_variant(self):
        """Models like ``qwen/qwen3.6-plus-preview:free`` contain a colon
        in the model name.  The first colon splits provider from model."""
        provider, model, pinned = _parse_mapping("openrouter:qwen/qwen3.6-plus-preview:free+alibaba")
        assert provider == "openrouter"
        assert model == "qwen/qwen3.6-plus-preview:free"
        assert pinned == ["alibaba"]


# ── _apply_provider_pinning unit tests ────────────────────────────────


class TestApplyProviderPinning:
    def _make_route(self, pinned: list[str] | None = None) -> RouteResult:
        adapter = SimpleNamespace()
        return RouteResult("openrouter", "minimax/minimax-m2.7", adapter, pinned_providers=pinned)

    def test_no_pinning_when_none(self):
        body: dict[str, Any] = {"model": "minimax/minimax-m2.7", "messages": []}
        proxy_router._apply_provider_pinning(body, self._make_route(None))
        assert "provider" not in body

    def test_injects_provider_order(self):
        body: dict[str, Any] = {"model": "minimax/minimax-m2.7", "messages": []}
        proxy_router._apply_provider_pinning(body, self._make_route(["minimax"]))
        assert body["provider"] == {"order": ["minimax"]}

    def test_injects_multiple_providers(self):
        body: dict[str, Any] = {"model": "m", "messages": []}
        proxy_router._apply_provider_pinning(body, self._make_route(["deepinfra", "together"]))
        assert body["provider"]["order"] == ["deepinfra", "together"]

    def test_client_order_takes_priority(self):
        body: dict[str, Any] = {
            "model": "m",
            "messages": [],
            "provider": {"order": ["client-provider"]},
        }
        proxy_router._apply_provider_pinning(body, self._make_route(["minimax"]))
        assert body["provider"]["order"] == ["client-provider"]

    def test_client_provider_fields_preserved_order_injected(self):
        body: dict[str, Any] = {
            "model": "m",
            "messages": [],
            "provider": {"allow_fallbacks": False, "data_collection": "deny"},
        }
        proxy_router._apply_provider_pinning(body, self._make_route(["minimax"]))
        assert body["provider"]["order"] == ["minimax"]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["data_collection"] == "deny"

    def test_client_provider_not_dict_gets_overwritten(self):
        body: dict[str, Any] = {"model": "m", "messages": [], "provider": "invalid"}
        proxy_router._apply_provider_pinning(body, self._make_route(["minimax"]))
        assert body["provider"] == {"order": ["minimax"]}


# ── Integration: full request flow ────────────────────────────────────


class FakePinAdapter:
    def __init__(self):
        self.last_request_body: dict[str, Any] | None = None

    def _build_headers(self, headers, *, override_api_key=None):
        out = dict(headers)
        out["Content-Type"] = "application/json"
        return out

    async def chat_completions(self, request_body, headers, *, override_api_key=None):
        self.last_request_body = request_body
        return ProviderResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"choices":[{"message":{"role":"assistant","content":"ok"}}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}',
            content_type="application/json",
        )

    async def stream_chat_completions(self, request_body, headers, *, override_api_key=None):
        raise AssertionError("not used")

    async def list_models(self):
        return []


@pytest.mark.asyncio
async def test_pinning_injected_into_forwarded_body(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakePinAdapter()
    route = SimpleNamespace(
        provider_name="openrouter",
        mapped_model="minimax/minimax-m2.7",
        adapter=adapter,
        pinned_providers=["minimax"],
    )
    logged = []

    monkeypatch.setattr(proxy_router, "get_app_config", lambda: AppConfig())
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, "hash", True))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)

    async def capture_log(entry):
        logged.append(entry)

    monkeypatch.setattr(proxy_router, "enqueue_log", capture_log)
    monkeypatch.setattr(proxy_router, "resolve_provider_key", lambda *_args, **_kw: None)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={"model": "minimax/minimax-m2.7", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert adapter.last_request_body is not None
    assert adapter.last_request_body["provider"] == {"order": ["minimax"]}


@pytest.mark.asyncio
async def test_client_provider_order_overrides_pinning(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakePinAdapter()
    route = SimpleNamespace(
        provider_name="openrouter",
        mapped_model="minimax/minimax-m2.7",
        adapter=adapter,
        pinned_providers=["minimax"],
    )

    monkeypatch.setattr(proxy_router, "get_app_config", lambda: AppConfig())
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, "hash", True))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)

    async def noop_log(entry):
        pass

    monkeypatch.setattr(proxy_router, "enqueue_log", noop_log)
    monkeypatch.setattr(proxy_router, "resolve_provider_key", lambda *_args, **_kw: None)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "minimax/minimax-m2.7",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"order": ["client-choice"]},
            },
        )

    assert resp.status_code == 200
    assert adapter.last_request_body["provider"]["order"] == ["client-choice"]


@pytest.mark.asyncio
async def test_no_pinning_when_route_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakePinAdapter()
    route = SimpleNamespace(
        provider_name="openrouter",
        mapped_model="minimax/minimax-m2.7",
        adapter=adapter,
        pinned_providers=None,
    )

    async def noop_log2(entry):
        pass

    monkeypatch.setattr(proxy_router, "get_app_config", lambda: AppConfig())
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, "hash", True))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)
    monkeypatch.setattr(proxy_router, "enqueue_log", noop_log2)
    monkeypatch.setattr(proxy_router, "resolve_provider_key", lambda *_args, **_kw: None)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={"model": "minimax/minimax-m2.7", "messages": [{"role": "user", "content": "hi"}]},
        )

    assert resp.status_code == 200
    assert "provider" not in adapter.last_request_body
