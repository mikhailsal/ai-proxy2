"""Provider selection and model mapping."""

import fnmatch

import structlog

from ai_proxy.adapters.base import BaseAdapter
from ai_proxy.adapters.registry import get_adapter_registry
from ai_proxy.config.loader import get_app_config
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
    ) -> None:
        self.provider_name = provider_name
        self.mapped_model = mapped_model
        self.adapter = adapter
        self.pinned_providers = pinned_providers
        self.route_label = route_label or _format_route_label(provider_name, mapped_model, pinned_providers)


async def resolve_model(model_requested: str) -> RouteResult:
    config = get_app_config()
    registry = get_adapter_registry()

    lookup_model, client_pinned = _strip_client_provider_suffix(model_requested)

    route = _resolve_exact_mapping(lookup_model, client_pinned, config.model_mappings, registry)
    if route is not None:
        return route

    catalog = await get_proxy_model_catalog(config=config, registry=registry)
    expanded = catalog.get(lookup_model)
    if expanded is not None:
        pinned = _merge_pinned(expanded.pinned_providers, client_pinned)
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
