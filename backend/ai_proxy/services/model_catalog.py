"""Provider model catalog caching and proxy model expansion."""

from __future__ import annotations

import asyncio
import fnmatch
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from ai_proxy.adapters.registry import get_adapter_registry
from ai_proxy.config.loader import get_app_config
from ai_proxy.core.model_mappings import has_glob, parse_mapping

if TYPE_CHECKING:
    from ai_proxy.adapters.base import BaseAdapter
    from ai_proxy.config.settings import AppConfig
    from ai_proxy.types import JsonObject

logger = structlog.get_logger()

_PROVIDER_MODELS_TTL_SECONDS = 300.0
_NVIDIA_MIN_REASONABLE_CREATED = 946684800


@dataclass(frozen=True)
class CatalogModel:
    client_model: str
    provider_name: str
    mapped_model: str
    pinned_providers: list[str] | None = None
    metadata: JsonObject | None = None


@dataclass(frozen=True)
class _ProviderModelsCacheEntry:
    expires_at: float
    models: tuple[JsonObject, ...]
    models_by_id: dict[str, JsonObject]


_provider_models_cache: dict[str, _ProviderModelsCacheEntry] = {}
_provider_model_locks: dict[str, asyncio.Lock] = {}


def invalidate_model_catalog(provider_name: str | None = None) -> None:
    if provider_name is None:
        _provider_models_cache.clear()
        _provider_model_locks.clear()
        return

    _provider_models_cache.pop(provider_name, None)
    _provider_model_locks.pop(provider_name, None)


def serialize_catalog_model(entry: CatalogModel) -> JsonObject:
    if entry.metadata is None:
        return {"id": entry.client_model, "object": "model", "owned_by": "ai-proxy"}

    payload = dict(entry.metadata)
    payload["id"] = entry.client_model
    payload.setdefault("object", "model")
    payload.setdefault("owned_by", entry.provider_name)
    return payload


def _normalize_provider_model(provider_name: str, model_payload: JsonObject) -> JsonObject:
    normalized = dict(model_payload)
    created = normalized.get("created")
    if provider_name == "nvidia" and isinstance(created, int) and created < _NVIDIA_MIN_REASONABLE_CREATED:
        normalized.pop("created", None)
    return normalized


async def get_proxy_model_catalog(
    config: AppConfig | None = None,
    registry: dict[str, BaseAdapter] | None = None,
) -> dict[str, CatalogModel]:
    config = config or get_app_config()
    registry = registry or get_adapter_registry()
    provider_models = await _get_provider_models_for_mappings(config, registry)
    catalog: dict[str, CatalogModel] = {}

    for client_model, mapping in config.model_mappings.items():
        if has_glob(client_model):
            continue

        provider_name, mapped_model_pattern, pinned = parse_mapping(mapping)
        if not has_glob(mapped_model_pattern):
            continue

        cache_entry = provider_models.get(provider_name)
        if cache_entry is None:
            continue

        for upstream_model in cache_entry.models:
            upstream_id = upstream_model.get("id")
            if not isinstance(upstream_id, str) or not fnmatch.fnmatch(upstream_id, mapped_model_pattern):
                continue

            catalog.setdefault(
                upstream_id,
                CatalogModel(
                    client_model=upstream_id,
                    provider_name=provider_name,
                    mapped_model=upstream_id,
                    pinned_providers=pinned,
                    metadata=dict(upstream_model),
                ),
            )

    for client_model, mapping in config.model_mappings.items():
        if has_glob(client_model):
            continue

        provider_name, mapped_model_pattern, pinned = parse_mapping(mapping)
        concrete_mapped_model = _resolve_catalog_model_name(client_model, mapped_model_pattern)
        metadata: JsonObject | None = None

        cache_entry = provider_models.get(provider_name)
        if cache_entry is not None and concrete_mapped_model is not None:
            exact_upstream_model = cache_entry.models_by_id.get(concrete_mapped_model)
            if exact_upstream_model is not None:
                metadata = dict(exact_upstream_model)

        catalog[client_model] = CatalogModel(
            client_model=client_model,
            provider_name=provider_name,
            mapped_model=concrete_mapped_model or mapped_model_pattern,
            pinned_providers=pinned,
            metadata=metadata,
        )

    return catalog


async def _get_provider_models_for_mappings(
    config: AppConfig,
    registry: dict[str, BaseAdapter],
) -> dict[str, _ProviderModelsCacheEntry]:
    provider_names: list[str] = []
    seen: set[str] = set()

    for mapping in config.model_mappings.values():
        provider_name, _mapped_model, _pinned = parse_mapping(mapping)
        if provider_name in registry and provider_name not in seen:
            seen.add(provider_name)
            provider_names.append(provider_name)

    tasks = {
        provider_name: asyncio.create_task(_get_cached_provider_models(provider_name, registry[provider_name]))
        for provider_name in provider_names
    }

    results: dict[str, _ProviderModelsCacheEntry] = {}
    for provider_name, task in tasks.items():
        results[provider_name] = await task
    return results


async def _get_cached_provider_models(
    provider_name: str,
    adapter: BaseAdapter,
) -> _ProviderModelsCacheEntry:
    now = time.monotonic()
    cached = _provider_models_cache.get(provider_name)
    if cached is not None and cached.expires_at > now:
        return cached

    lock = _provider_model_locks.setdefault(provider_name, asyncio.Lock())
    async with lock:
        now = time.monotonic()
        cached = _provider_models_cache.get(provider_name)
        if cached is not None and cached.expires_at > now:
            return cached

        try:
            raw_models = await adapter.list_models()
        except Exception:
            logger.exception("provider_models_fetch_failed", provider=provider_name)
            raw_models = []

        sanitized_models: list[JsonObject] = []
        models_by_id: dict[str, JsonObject] = {}
        for model in raw_models:
            model_id = model.get("id")
            if not isinstance(model_id, str) or not model_id:
                continue

            model_payload = _normalize_provider_model(provider_name, model)
            sanitized_models.append(model_payload)
            models_by_id[model_id] = model_payload

        cache_entry = _ProviderModelsCacheEntry(
            expires_at=time.monotonic() + _PROVIDER_MODELS_TTL_SECONDS,
            models=tuple(sanitized_models),
            models_by_id=models_by_id,
        )
        _provider_models_cache[provider_name] = cache_entry
        return cache_entry


def _resolve_catalog_model_name(client_model: str, mapped_model_pattern: str) -> str | None:
    if mapped_model_pattern == "*":
        return client_model
    if has_glob(mapped_model_pattern):
        if fnmatch.fnmatch(client_model, mapped_model_pattern):
            return client_model
        return None
    return mapped_model_pattern
