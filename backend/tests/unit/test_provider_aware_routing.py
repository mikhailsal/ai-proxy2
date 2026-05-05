"""Tests for provider-aware routing: choosing gateway based on sub-provider."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters.base import ProviderResponse
from ai_proxy.api.proxy import router as proxy_router
from ai_proxy.app import create_app
from ai_proxy.config.loader import _detect_provider_routing_conflicts
from ai_proxy.config.settings import AppConfig
from ai_proxy.core.model_mappings import (
    build_provider_qualified_key,
    extract_body_provider_slugs,
)
from ai_proxy.core.routing import (
    _resolve_provider_aware,
)

# ── Helper utilities ──────────────────────────────────────────────────


class FakeAdapter:
    def __init__(self) -> None:
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


# ── extract_body_provider_slugs unit tests ────────────────────────────


class TestExtractBodyProviderSlugs:
    def test_no_provider_field(self):
        assert extract_body_provider_slugs({"model": "gpt-4o"}) is None

    def test_provider_not_dict(self):
        assert extract_body_provider_slugs({"provider": "string"}) is None

    def test_no_order_field(self):
        assert extract_body_provider_slugs({"provider": {"data_collection": "deny"}}) is None

    def test_empty_order(self):
        assert extract_body_provider_slugs({"provider": {"order": []}}) is None

    def test_single_provider(self):
        assert extract_body_provider_slugs({"provider": {"order": ["DeepInfra"]}}) == ["DeepInfra"]

    def test_multiple_providers(self):
        result = extract_body_provider_slugs({"provider": {"order": ["bedrock", "deepinfra"]}})
        assert result == ["bedrock", "deepinfra"]

    def test_non_string_entries_filtered(self):
        assert extract_body_provider_slugs({"provider": {"order": [123, "deepinfra", None]}}) == ["deepinfra"]

    def test_empty_strings_filtered(self):
        assert extract_body_provider_slugs({"provider": {"order": ["", "deepinfra"]}}) == ["deepinfra"]

    def test_all_empty_returns_none(self):
        assert extract_body_provider_slugs({"provider": {"order": ["", ""]}}) is None


# ── build_provider_qualified_key unit tests ───────────────────────────


class TestBuildProviderQualifiedKey:
    def test_basic(self):
        assert build_provider_qualified_key("openai/gpt-oss-120b", "bedrock") == "openai/gpt-oss-120b+bedrock"

    def test_with_slash_slug(self):
        assert build_provider_qualified_key("model/name", "prov/sub") == "model/name+prov/sub"


# ── _resolve_provider_aware unit tests ────────────────────────────────


class TestResolveProviderAware:
    def _make_registry(self, *names: str) -> dict[str, Any]:
        return {name: SimpleNamespace() for name in names}

    def test_no_providers_returns_none(self):
        registry = self._make_registry("kilocode", "openrouter")
        mappings = {"openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b"}
        result = _resolve_provider_aware("openai/gpt-oss-120b", None, None, mappings, registry)
        assert result is None

    def test_client_pinned_matches_qualified_entry(self):
        registry = self._make_registry("kilocode", "openrouter")
        mappings = {
            "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
            "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        result = _resolve_provider_aware("openai/gpt-oss-120b", ["deepinfra"], None, mappings, registry)
        assert result is not None
        assert result.provider_name == "openrouter"
        assert result.pinned_providers == ["deepinfra"]
        assert result.provider_aware_match is True

    def test_body_provider_matches_qualified_entry(self):
        registry = self._make_registry("kilocode", "openrouter")
        mappings = {
            "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
            "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        result = _resolve_provider_aware("openai/gpt-oss-120b", None, ["deepinfra"], mappings, registry)
        assert result is not None
        assert result.provider_name == "openrouter"
        assert result.provider_aware_match is True

    def test_client_pinned_takes_priority_over_body(self):
        """When both +suffix and body provider are present, +suffix wins."""
        registry = self._make_registry("kilocode", "openrouter")
        mappings = {
            "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        result = _resolve_provider_aware("openai/gpt-oss-120b", ["bedrock"], ["deepinfra"], mappings, registry)
        assert result is not None
        assert result.provider_name == "kilocode"

    def test_case_insensitive_matching(self):
        registry = self._make_registry("openrouter")
        mappings = {
            "google/gemma-4-26b-a4b-it+Google": "openrouter:google/gemma-4-26b-a4b-it+google-ai-studio",
        }
        result = _resolve_provider_aware("google/gemma-4-26b-a4b-it", None, ["google"], mappings, registry)
        assert result is not None
        assert result.provider_name == "openrouter"
        assert result.pinned_providers == ["google-ai-studio"]

    def test_no_matching_qualified_entry_returns_none(self):
        registry = self._make_registry("kilocode")
        mappings = {"openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b"}
        result = _resolve_provider_aware("openai/gpt-oss-120b", ["unknown-provider"], None, mappings, registry)
        assert result is None

    def test_multiple_body_providers_first_match_wins(self):
        registry = self._make_registry("kilocode", "openrouter")
        mappings = {
            "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        result = _resolve_provider_aware("openai/gpt-oss-120b", None, ["deepinfra", "bedrock"], mappings, registry)
        assert result is not None
        assert result.provider_name == "openrouter"

    def test_provider_slug_rename(self):
        """Config entry renames the provider slug (Google -> google-ai-studio)."""
        registry = self._make_registry("openrouter")
        mappings = {
            "google/gemma-4-26b-a4b-it+Google": "openrouter:google/gemma-4-26b-a4b-it+google-ai-studio",
        }
        result = _resolve_provider_aware("google/gemma-4-26b-a4b-it", ["Google"], None, mappings, registry)
        assert result is not None
        assert result.pinned_providers == ["google-ai-studio"]
        assert result.provider_aware_match is True

    def test_direct_google_alias_routes_without_pinning(self):
        registry = self._make_registry("google", "openrouter")
        mappings = {
            "google/gemma-4-31b-it+google-direct": "google:gemma-4-31b-it",
        }
        result = _resolve_provider_aware("google/gemma-4-31b-it", ["google-direct"], None, mappings, registry)
        assert result is not None
        assert result.provider_name == "google"
        assert result.mapped_model == "gemma-4-31b-it"
        assert result.pinned_providers is None
        assert result.provider_aware_match is True

    def test_same_source_lists_not_duplicated(self):
        """When client_pinned == body_provider_slugs, only one pass is done."""
        registry = self._make_registry("openrouter")
        mappings = {
            "model+prov": "openrouter:model+prov",
        }
        result = _resolve_provider_aware("model", ["prov"], ["prov"], mappings, registry)
        assert result is not None
        assert result.provider_name == "openrouter"

    def test_missing_adapter_returns_none(self):
        registry: dict[str, Any] = {}
        mappings = {
            "model+prov": "missing_provider:model+prov",
        }
        result = _resolve_provider_aware("model", ["prov"], None, mappings, registry)
        assert result is None


# ── _detect_provider_routing_conflicts unit tests ─────────────────────


class TestDetectProviderRoutingConflicts:
    def test_no_conflicts_for_clean_config(self):
        mappings = {
            "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
            "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        assert _detect_provider_routing_conflicts(mappings) == []

    def test_base_pin_conflicts_with_qualified_entry(self):
        mappings = {
            "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b+deepinfra",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        conflicts = _detect_provider_routing_conflicts(mappings)
        assert len(conflicts) == 1
        assert "kilocode" in conflicts[0]
        assert "openrouter" in conflicts[0]

    def test_no_conflict_when_gateways_match(self):
        mappings = {
            "openai/gpt-oss-120b": "openrouter:openai/gpt-oss-120b+deepinfra",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        assert _detect_provider_routing_conflicts(mappings) == []

    def test_duplicate_qualified_entries_different_gateways(self):
        mappings = {
            "openai/gpt-oss-120b+DeepInfra": "kilocode:openai/gpt-oss-120b+deepinfra",
            "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
        }
        conflicts = _detect_provider_routing_conflicts(mappings)
        assert len(conflicts) == 1
        assert "different gateways" in conflicts[0]

    def test_empty_mappings_no_conflicts(self):
        assert _detect_provider_routing_conflicts({}) == []

    def test_base_only_no_conflicts(self):
        mappings = {
            "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
            "openai/gpt-oss-20b": "kilocode:openai/gpt-oss-20b",
        }
        assert _detect_provider_routing_conflicts(mappings) == []


# ── Integration: full request flow with provider-aware routing ────────


def _setup_integration_test(monkeypatch, mappings, registry):
    """Common setup for integration tests: patches both router and routing modules."""
    config = AppConfig(model_mappings=mappings)
    monkeypatch.setattr(proxy_router, "get_app_config", lambda: config)
    monkeypatch.setattr("ai_proxy.core.routing.get_app_config", lambda: config)
    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key, **kw: (True, "hash", True))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr("ai_proxy.core.routing.get_adapter_registry", lambda: registry)

    async def noop_log(entry):
        pass

    monkeypatch.setattr(proxy_router, "enqueue_log", noop_log)
    monkeypatch.setattr(proxy_router, "resolve_provider_key", lambda *_args, **_kw: None)


@pytest.mark.asyncio
async def test_body_provider_order_selects_qualified_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """Client sends provider.order and the proxy picks the matching config entry."""
    app = create_app()
    transport = ASGITransport(app=app)

    kilocode_adapter = FakeAdapter()
    openrouter_adapter = FakeAdapter()

    mappings = {
        "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
        "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
        "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
    }
    registry = {"kilocode": kilocode_adapter, "openrouter": openrouter_adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"order": ["deepinfra"]},
            },
        )

    assert resp.status_code == 200
    assert openrouter_adapter.last_request_body is not None
    assert kilocode_adapter.last_request_body is None
    assert openrouter_adapter.last_request_body["provider"]["order"] == ["deepinfra"]


@pytest.mark.asyncio
async def test_provider_slug_renamed_in_forwarded_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config renames provider slug (Google -> google-ai-studio), forwarded body gets the new slug."""
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakeAdapter()
    mappings = {
        "google/gemma-4-26b-a4b-it+Google": "openrouter:google/gemma-4-26b-a4b-it+google-ai-studio",
    }
    registry = {"openrouter": adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "google/gemma-4-26b-a4b-it",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"order": ["Google"]},
            },
        )

    assert resp.status_code == 200
    assert adapter.last_request_body is not None
    assert adapter.last_request_body["provider"]["order"] == ["google-ai-studio"]


@pytest.mark.asyncio
async def test_direct_google_alias_routes_without_provider_order(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    google_adapter = FakeAdapter()
    openrouter_adapter = FakeAdapter()
    mappings = {
        "google/gemma-4-31b-it": "openrouter:google/gemma-4-31b-it",
        "google/gemma-4-31b-it+google-direct": "google:gemma-4-31b-it",
    }
    registry = {"google": google_adapter, "openrouter": openrouter_adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "google/gemma-4-31b-it+google-direct",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert resp.status_code == 200
    assert google_adapter.last_request_body is not None
    assert google_adapter.last_request_body["model"] == "gemma-4-31b-it"
    assert "provider" not in google_adapter.last_request_body
    assert openrouter_adapter.last_request_body is None


@pytest.mark.asyncio
async def test_plus_suffix_takes_priority_over_body_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """+suffix on model name wins over body provider.order."""
    app = create_app()
    transport = ASGITransport(app=app)

    kilocode_adapter = FakeAdapter()
    openrouter_adapter = FakeAdapter()

    mappings = {
        "openai/gpt-oss-120b+bedrock": "kilocode:openai/gpt-oss-120b+bedrock",
        "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
    }
    registry = {"kilocode": kilocode_adapter, "openrouter": openrouter_adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "openai/gpt-oss-120b+bedrock",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"order": ["deepinfra"]},
            },
        )

    assert resp.status_code == 200
    assert kilocode_adapter.last_request_body is not None
    assert openrouter_adapter.last_request_body is None


@pytest.mark.asyncio
async def test_no_qualified_entry_falls_back_to_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """When no provider-qualified entry matches, fall back to the base mapping."""
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakeAdapter()
    mappings = {
        "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
    }
    registry = {"kilocode": adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"order": ["some-unknown-provider"]},
            },
        )

    assert resp.status_code == 200
    assert adapter.last_request_body is not None


@pytest.mark.asyncio
async def test_route_label_reflects_provider_aware_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    """ai_proxy_route in the response reflects the provider-aware route."""
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakeAdapter()
    mappings = {
        "openai/gpt-oss-120b": "kilocode:openai/gpt-oss-120b",
        "openai/gpt-oss-120b+deepinfra": "openrouter:openai/gpt-oss-120b+deepinfra",
    }
    registry = {"kilocode": adapter, "openrouter": adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"order": ["deepinfra"]},
            },
        )

    assert resp.status_code == 200
    assert resp.json()["ai_proxy_route"] == "openrouter:openai/gpt-oss-120b+deepinfra"
