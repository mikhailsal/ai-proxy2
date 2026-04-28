"""Helpers for parsing and formatting model mappings."""

from __future__ import annotations

from typing import Any


def has_glob(value: str) -> bool:
    return any(char in value for char in "*?[]")


def parse_mapping(mapping: str) -> tuple[str, str, list[str] | None]:
    """Parse a mapping value like ``provider:model+pin1,pin2``.

    The ``+`` suffix after the model name specifies provider slugs to pin
    via OpenRouter's ``provider.order`` field. Multiple slugs are
    comma-separated. Returns ``(provider, model, pinned_list | None)``.
    """
    if ":" in mapping:
        provider, model = mapping.split(":", 1)
    else:
        provider, model = mapping, mapping

    pinned: list[str] | None = None
    if "+" in model:
        model, pin_part = model.rsplit("+", 1)
        slugs = [slug.strip() for slug in pin_part.split(",") if slug.strip()]
        if slugs:
            pinned = slugs

    return provider, model, pinned


def strip_client_provider_suffix(model: str) -> tuple[str, list[str] | None]:
    """Extract an optional ``+provider`` suffix from the client's model name."""
    if "+" not in model:
        return model, None

    base, pin_part = model.rsplit("+", 1)
    slugs = [slug.strip() for slug in pin_part.split(",") if slug.strip()]
    if not slugs:
        return model, None
    return base, slugs


def merge_pinned(
    config_pinned: list[str] | None,
    client_pinned: list[str] | None,
) -> list[str] | None:
    """Config-level pins take priority; client suffix is used as fallback."""
    if config_pinned:
        return config_pinned
    return client_pinned


def format_route_label(provider_name: str, mapped_model: str, pinned: list[str] | None) -> str:
    route_label = f"{provider_name}:{mapped_model}"
    if pinned:
        route_label = f"{route_label}+{','.join(pinned)}"
    return route_label


def extract_body_provider_slugs(body: dict[str, Any]) -> list[str] | None:
    """Extract provider slugs from the OpenRouter-style ``provider.order`` body field.

    Returns the list of provider slugs if present, otherwise ``None``.
    """
    provider_field = body.get("provider")
    if not isinstance(provider_field, dict):
        return None
    order = provider_field.get("order")
    if not isinstance(order, list) or not order:
        return None
    slugs = [slug for slug in order if isinstance(slug, str) and slug]
    return slugs or None


def build_provider_qualified_key(model: str, provider_slug: str) -> str:
    """Build a ``model+provider`` lookup key for provider-aware routing."""
    return f"{model}+{provider_slug}"
