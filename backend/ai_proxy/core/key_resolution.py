"""Resolve which provider API key to use for a given request.

Priority:
  1. Known key + key_mapping match  -> mapped provider key
  2. Known key without mapping      -> adapter default (None)
  3. Unknown key + bypass enabled   -> forward client key as-is
  4. Otherwise                      -> adapter default (None)
"""

import structlog

from ai_proxy.config.loader import get_app_config
from ai_proxy.security.auth import hash_api_key

logger = structlog.get_logger()


def resolve_provider_key(
    client_api_key: str,
    provider_name: str,
    *,
    is_known_key: bool = False,
) -> str | None:
    config = get_app_config()

    if config.key_mappings:
        key_hash = hash_api_key(client_api_key)
        mapping = config.key_mappings.get(key_hash)
        if mapping and provider_name in mapping.provider_keys:
            return mapping.provider_keys[provider_name]

    if is_known_key:
        return None

    if config.bypass.enabled:
        return client_api_key

    return None
