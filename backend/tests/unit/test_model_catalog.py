from __future__ import annotations

import pytest

from ai_proxy.config.settings import AppConfig, ProviderConfig
from ai_proxy.core.routing import resolve_model
from ai_proxy.services import model_catalog
from ai_proxy.services.model_catalog import CatalogModel, get_proxy_model_catalog, invalidate_model_catalog


class CountingAdapter:
    def __init__(self, models: list[dict[str, object]]) -> None:
        self.calls = 0
        self.models = models

    async def chat_completions(self, request_body, headers, *, override_api_key=None):
        raise AssertionError("not used")

    async def stream_chat_completions(self, request_body, headers, *, override_api_key=None):
        raise AssertionError("not used")

    async def list_models(self):
        self.calls += 1
        return self.models


@pytest.mark.asyncio
async def test_proxy_model_catalog_expands_upstream_wildcards_and_exact_overrides() -> None:
    invalidate_model_catalog()
    config = AppConfig(
        providers={"kilocode": ProviderConfig(endpoint="https://kilocode.example")},
        model_mappings={
            "z-ai/glm-5.1": "kilocode:z-ai/*+z.ai",
            "z-ai/glm-4.7-flash": "kilocode:z-ai/glm-4.7-flash+novita",
            "plain-model": "kilocode:plain-model",
        },
    )
    adapter = CountingAdapter(
        [
            {"id": "z-ai/glm-5.1", "cost": {"input": 1, "output": 2}},
            {"id": "z-ai/glm-4.7-flash", "pricing": {"prompt": 3}},
            {"id": "plain-model", "context_length": 12345},
            {"id": "other/provider-model", "cost": {"input": 99}},
        ]
    )

    catalog = await get_proxy_model_catalog(config=config, registry={"kilocode": adapter})

    assert set(catalog) == {"z-ai/glm-5.1", "z-ai/glm-4.7-flash", "plain-model"}

    default_model = catalog["z-ai/glm-5.1"]
    assert default_model == CatalogModel(
        client_model="z-ai/glm-5.1",
        provider_name="kilocode",
        mapped_model="z-ai/glm-5.1",
        pinned_providers=["z.ai"],
        metadata={"id": "z-ai/glm-5.1", "cost": {"input": 1, "output": 2}},
    )

    overridden = catalog["z-ai/glm-4.7-flash"]
    assert overridden.provider_name == "kilocode"
    assert overridden.mapped_model == "z-ai/glm-4.7-flash"
    assert overridden.pinned_providers == ["novita"]
    assert overridden.metadata == {"id": "z-ai/glm-4.7-flash", "pricing": {"prompt": 3}}

    plain_model = catalog["plain-model"]
    assert plain_model.metadata == {"id": "plain-model", "context_length": 12345}


@pytest.mark.asyncio
async def test_provider_model_catalog_is_cached_until_invalidated() -> None:
    invalidate_model_catalog()
    config = AppConfig(
        providers={"kilocode": ProviderConfig(endpoint="https://kilocode.example")},
        model_mappings={"z-ai/glm-5.1": "kilocode:z-ai/*+z.ai"},
    )
    adapter = CountingAdapter([{"id": "z-ai/glm-5.1"}])
    registry = {"kilocode": adapter}

    await get_proxy_model_catalog(config=config, registry=registry)
    await get_proxy_model_catalog(config=config, registry=registry)
    assert adapter.calls == 1

    invalidate_model_catalog()
    await get_proxy_model_catalog(config=config, registry=registry)
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_resolve_model_supports_expanded_upstream_wildcards(monkeypatch: pytest.MonkeyPatch) -> None:
    invalidate_model_catalog()
    config = AppConfig(
        providers={"kilocode": ProviderConfig(endpoint="https://kilocode.example")},
        model_mappings={
            "z-ai/glm-5.1": "kilocode:z-ai/*+z.ai",
            "z-ai/glm-4.7-flash": "kilocode:z-ai/glm-4.7-flash+novita",
        },
    )
    adapter = CountingAdapter(
        [
            {"id": "z-ai/glm-5.1"},
            {"id": "z-ai/glm-4.7-flash"},
            {"id": "z-ai/glm-4.5-air:free"},
        ]
    )
    registry = {"kilocode": adapter}

    monkeypatch.setattr("ai_proxy.core.routing.get_app_config", lambda: config)
    monkeypatch.setattr("ai_proxy.core.routing.get_adapter_registry", lambda: registry)

    exact_seed = await resolve_model("z-ai/glm-5.1")
    expanded = await resolve_model("z-ai/glm-4.5-air:free")

    assert exact_seed.provider_name == "kilocode"
    assert exact_seed.mapped_model == "z-ai/glm-5.1"
    assert exact_seed.pinned_providers == ["z.ai"]

    assert expanded.provider_name == "kilocode"
    assert expanded.mapped_model == "z-ai/glm-4.5-air:free"
    assert expanded.pinned_providers == ["z.ai"]


def test_serialize_catalog_model_preserves_upstream_metadata() -> None:
    payload = model_catalog.serialize_catalog_model(
        CatalogModel(
            client_model="z-ai/glm-5.1",
            provider_name="kilocode",
            mapped_model="z-ai/glm-5.1",
            metadata={"id": "upstream-id", "pricing": {"prompt": 1}},
        )
    )

    assert payload == {
        "id": "z-ai/glm-5.1",
        "object": "model",
        "owned_by": "kilocode",
        "pricing": {"prompt": 1},
    }
