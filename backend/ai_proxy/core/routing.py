"""Provider selection and model mapping."""

import fnmatch

import structlog

from ai_proxy.adapters.base import BaseAdapter
from ai_proxy.adapters.registry import get_adapter_registry
from ai_proxy.config.loader import get_app_config

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


def resolve_model(model_requested: str) -> RouteResult:
    config = get_app_config()
    registry = get_adapter_registry()

    lookup_model, client_pinned = _strip_client_provider_suffix(model_requested)

    # Try exact match first
    if lookup_model in config.model_mappings:
        mapping = config.model_mappings[lookup_model]
        provider_name, mapped_model, pinned = _parse_mapping(mapping)
        pinned = _merge_pinned(pinned, client_pinned)
        adapter = registry.get(provider_name)
        if adapter:
            return RouteResult(
                provider_name,
                mapped_model,
                adapter,
                pinned_providers=pinned,
                route_label=_format_route_label(provider_name, mapped_model, pinned),
            )

    # Try wildcard match
    for pattern, mapping in config.model_mappings.items():
        if fnmatch.fnmatch(lookup_model, pattern):
            provider_name, mapped_model, pinned = _parse_mapping(mapping)
            pinned = _merge_pinned(pinned, client_pinned)
            if mapped_model == pattern or mapped_model == "*":
                mapped_model = lookup_model
            adapter = registry.get(provider_name)
            if adapter:
                return RouteResult(
                    provider_name,
                    mapped_model,
                    adapter,
                    pinned_providers=pinned,
                    route_label=_format_route_label(provider_name, mapped_model, pinned),
                )

    msg = f"No route found for model: {lookup_model}"
    raise ValueError(msg)


def _parse_mapping(mapping: str) -> tuple[str, str, list[str] | None]:
    """Parse a mapping value like ``provider:model+pin1,pin2``.

    The ``+`` suffix after the model name specifies provider slugs to pin
    via OpenRouter's ``provider.order`` field.  Multiple slugs are
    comma-separated.  Returns ``(provider, model, pinned_list | None)``.
    """
    if ":" in mapping:
        provider, model = mapping.split(":", 1)
    else:
        provider, model = mapping, mapping

    pinned: list[str] | None = None
    if "+" in model:
        model, pin_part = model.rsplit("+", 1)
        slugs = [s.strip() for s in pin_part.split(",") if s.strip()]
        if slugs:
            pinned = slugs

    return provider, model, pinned


def _strip_client_provider_suffix(model: str) -> tuple[str, list[str] | None]:
    """Extract an optional ``+provider`` suffix from the client's model name.

    Some clients cannot send the ``provider`` field in the request body, so
    they append ``+slug`` (or ``+slug1,slug2``) to the model name.  This
    function splits the suffix off and returns ``(clean_model, slugs | None)``.
    """
    if "+" not in model:
        return model, None

    base, pin_part = model.rsplit("+", 1)
    slugs = [s.strip() for s in pin_part.split(",") if s.strip()]
    if not slugs:
        return model, None
    return base, slugs


def _merge_pinned(
    config_pinned: list[str] | None,
    client_pinned: list[str] | None,
) -> list[str] | None:
    """Config-level pins take priority; client suffix is used as fallback."""
    if config_pinned:
        return config_pinned
    return client_pinned


def _format_route_label(provider_name: str, mapped_model: str, pinned: list[str] | None) -> str:
    route_label = f"{provider_name}:{mapped_model}"
    if pinned:
        route_label = f"{route_label}+{','.join(pinned)}"
    return route_label
