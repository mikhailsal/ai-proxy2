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
    ) -> None:
        self.provider_name = provider_name
        self.mapped_model = mapped_model
        self.adapter = adapter
        self.pinned_providers = pinned_providers


def resolve_model(model_requested: str) -> RouteResult:
    config = get_app_config()
    registry = get_adapter_registry()

    # Try exact match first
    if model_requested in config.model_mappings:
        mapping = config.model_mappings[model_requested]
        provider_name, mapped_model, pinned = _parse_mapping(mapping)
        adapter = registry.get(provider_name)
        if adapter:
            return RouteResult(provider_name, mapped_model, adapter, pinned_providers=pinned)

    # Try wildcard match
    for pattern, mapping in config.model_mappings.items():
        if fnmatch.fnmatch(model_requested, pattern):
            provider_name, mapped_model, pinned = _parse_mapping(mapping)
            # If mapped_model is the same as the pattern, use the actual requested model
            if mapped_model == pattern or mapped_model == "*":
                mapped_model = model_requested
            adapter = registry.get(provider_name)
            if adapter:
                return RouteResult(provider_name, mapped_model, adapter, pinned_providers=pinned)

    msg = f"No route found for model: {model_requested}"
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
