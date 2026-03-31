"""Resolve which provider API key to use for a given request.

Priority: bypass (client's own key) > key_mapping > adapter default (None).
"""

import structlog

from ai_proxy.config.loader import get_app_config
from ai_proxy.security.auth import hash_api_key

logger = structlog.get_logger()


def resolve_provider_key(
    client_api_key: str,
    provider_name: str,
) -> str | None:
    config = get_app_config()

    if config.bypass.enabled:
        return client_api_key

    if config.key_mappings:
        key_hash = hash_api_key(client_api_key)
        mapping = config.key_mappings.get(key_hash)
        if mapping and provider_name in mapping.provider_keys:
            return mapping.provider_keys[provider_name]

    return None
