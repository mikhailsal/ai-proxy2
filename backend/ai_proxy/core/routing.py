"""Provider selection and model mapping."""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Any

import structlog

from ai_proxy.adapters.registry import get_adapter_registry

if TYPE_CHECKING:
    from ai_proxy.adapters.base import BaseAdapter
from ai_proxy.config.loader import get_app_config
from ai_proxy.core.model_mappings import (
    build_provider_qualified_key as _build_qualified_key,
)
from ai_proxy.core.model_mappings import (
    extract_body_provider_slugs as _extract_body_provider_slugs,
)
from ai_proxy.core.model_mappings import (
    format_route_label as _format_route_label,
)
from ai_proxy.core.model_mappings import (
    has_glob as _has_glob,
)
from ai_proxy.core.model_mappings import (
    merge_pinned as _merge_pinned,
)
from ai_proxy.core.model_mappings import (
    parse_mapping as _parse_mapping,
)
from ai_proxy.core.model_mappings import (
    strip_client_provider_suffix as _strip_client_provider_suffix,
)
from ai_proxy.services.model_catalog import get_proxy_model_catalog

logger = structlog.get_logger()


class RouteResult:
    def __init__(
        self,
        provider_name: str,
        mapped_model: str,
        adapter: BaseAdapter,
        pinned_providers: list[str] | None = None,
        route_label: str | None = None,
        provider_aware_match: bool = False,
    ) -> None:
        self.provider_name = provider_name
        self.mapped_model = mapped_model
        self.adapter = adapter
        self.pinned_providers = pinned_providers
        self.route_label = route_label or _format_route_label(provider_name, mapped_model, pinned_providers)
        self.provider_aware_match = provider_aware_match


async def resolve_model(model_requested: str, body: dict[str, Any] | None = None) -> RouteResult:
    config = get_app_config()
    registry = get_adapter_registry()

    lookup_model, client_pinned = _strip_client_provider_suffix(model_requested)

    body_provider_slugs = _extract_body_provider_slugs(body) if body else None

    route = _resolve_provider_aware(lookup_model, client_pinned, body_provider_slugs, config.model_mappings, registry)
    if route is not None:
        return route

    route = _resolve_exact_mapping(lookup_model, client_pinned, config.model_mappings, registry)
    if route is not None:
        return route

    catalog = await get_proxy_model_catalog(config=config, registry=registry)
    expanded = catalog.get(lookup_model)
    if expanded is not None:
        pinned = _merge_pinned(expanded.pinned_providers, client_pinned)
        if not pinned and body_provider_slugs:
            pinned = body_provider_slugs
        adapter = registry.get(expanded.provider_name)
        if adapter:
            return RouteResult(
                expanded.provider_name,
                expanded.mapped_model,
                adapter,
                pinned_providers=pinned,
                route_label=_format_route_label(expanded.provider_name, expanded.mapped_model, pinned),
            )

    route = _resolve_wildcard_mapping(lookup_model, client_pinned, config.model_mappings, registry)
    if route is not None:
        return route

    msg = f"No route found for model: {lookup_model}"
    raise ValueError(msg)


def _resolve_provider_aware(
    lookup_model: str,
    client_pinned: list[str] | None,
    body_provider_slugs: list[str] | None,
    model_mappings: dict[str, str],
    registry: dict[str, BaseAdapter],
) -> RouteResult | None:
    """Try provider-qualified config keys before generic model lookup.

    When the client requests a sub-provider — via the ``+suffix`` on
    the model name **or** via ``provider.order`` in the body — we look
    for a config entry like ``model+provider``.  The ``+suffix`` format
    takes priority over ``provider.order`` when both are present.

    Provider names are compared case-insensitively.
    """
    provider_sources: list[list[str]] = []
    if client_pinned:
        provider_sources.append(client_pinned)
    if body_provider_slugs and body_provider_slugs != client_pinned:
        provider_sources.append(body_provider_slugs)

    if not provider_sources:
        return None

    ci_mapping_keys = {key.lower(): key for key in model_mappings}

    for slug_list in provider_sources:
        for slug in slug_list:
            qualified_key = _build_qualified_key(lookup_model, slug)
            actual_key = ci_mapping_keys.get(qualified_key.lower())
            if actual_key is None:
                continue

            mapping = model_mappings[actual_key]
            route = _build_route_result(lookup_model, actual_key, mapping, None, registry)
            if route is not None:
                route.provider_aware_match = True
                return route

    return None


def _resolve_exact_mapping(
    lookup_model: str,
    client_pinned: list[str] | None,
    model_mappings: dict[str, str],
    registry: dict[str, BaseAdapter],
) -> RouteResult | None:
    mapping = model_mappings.get(lookup_model)
    if mapping is None:
        return None
    return _build_route_result(lookup_model, lookup_model, mapping, client_pinned, registry)


def _resolve_wildcard_mapping(
    lookup_model: str,
    client_pinned: list[str] | None,
    model_mappings: dict[str, str],
    registry: dict[str, BaseAdapter],
) -> RouteResult | None:
    for pattern, mapping in model_mappings.items():
        if not fnmatch.fnmatch(lookup_model, pattern):
            continue

        route = _build_route_result(lookup_model, pattern, mapping, client_pinned, registry)
        if route is not None:
            return route
    return None


def _build_route_result(
    lookup_model: str,
    client_pattern: str,
    mapping: str,
    client_pinned: list[str] | None,
    registry: dict[str, BaseAdapter],
) -> RouteResult | None:
    provider_name, mapped_model_pattern, pinned = _parse_mapping(mapping)
    mapped_model = _resolve_mapped_model_name(lookup_model, client_pattern, mapped_model_pattern)
    if mapped_model is None:
        return None

    pinned = _merge_pinned(pinned, client_pinned)
    adapter = registry.get(provider_name)
    if adapter is None:
        return None

    return RouteResult(
        provider_name,
        mapped_model,
        adapter,
        pinned_providers=pinned,
        route_label=_format_route_label(provider_name, mapped_model, pinned),
    )


def _resolve_mapped_model_name(lookup_model: str, client_pattern: str, mapped_model_pattern: str) -> str | None:
    if mapped_model_pattern == client_pattern or mapped_model_pattern == "*":
        return lookup_model
    if _has_glob(mapped_model_pattern):
        if fnmatch.fnmatch(lookup_model, mapped_model_pattern):
            return lookup_model
        return None
    return mapped_model_pattern
