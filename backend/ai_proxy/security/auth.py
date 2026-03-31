"""API key authentication using SHA-256 hashing.

Keys are resolved from config.secrets.yml (via AppConfig) with fallback
to the legacy environment variables (API_KEYS / UI_API_KEY in Settings).
"""

import hashlib

from ai_proxy.config.settings import get_settings


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"


def _get_configured_api_keys() -> list[str]:
    """Return proxy access keys from config secrets, falling back to env var."""
    from ai_proxy.config.loader import get_app_config

    try:
        config = get_app_config()
        if config.api_keys:
            return config.api_keys
    except RuntimeError:
        pass

    return get_settings().get_api_keys()


def _get_ui_api_key() -> str:
    """Return UI key from config secrets, falling back to env var."""
    from ai_proxy.config.loader import get_app_config

    try:
        config = get_app_config()
        if config.ui_api_key:
            return config.ui_api_key
    except RuntimeError:
        pass

    return get_settings().ui_api_key


def validate_proxy_api_key(api_key: str | None, *, bypass_enabled: bool = False) -> tuple[bool, str, bool]:
    """Validate a proxy API key.

    Returns (is_valid, key_hash, is_known_key).
    is_known_key is True when the key matched a configured api_keys entry;
    False when accepted only via bypass passthrough.
    """
    if api_key is None:
        if bypass_enabled:
            return False, "", False
        configured_keys = _get_configured_api_keys()
        if not configured_keys:
            return True, hash_api_key("anonymous"), False
        return False, "", False

    key_hash = hash_api_key(api_key)

    configured_keys = _get_configured_api_keys()
    for configured_key in configured_keys:
        if hash_api_key(configured_key) == key_hash:
            return True, key_hash, True

    if bypass_enabled:
        return True, key_hash, False

    if not configured_keys:
        return True, key_hash, False

    return False, "", False


def validate_ui_api_key(api_key: str | None) -> bool:
    ui_key = _get_ui_api_key()
    if not ui_key:
        return True
    return api_key == ui_key
