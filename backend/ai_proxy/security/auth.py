"""API key authentication using SHA-256 hashing."""

import hashlib

from ai_proxy.config.settings import get_settings


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"


def validate_proxy_api_key(api_key: str | None) -> tuple[bool, str]:
    settings = get_settings()
    configured_keys = settings.get_api_keys()
    if not configured_keys:
        return True, hash_api_key("anonymous") if api_key is None else hash_api_key(api_key)
    if api_key is None:
        return False, ""
    key_hash = hash_api_key(api_key)
    for configured_key in configured_keys:
        if hash_api_key(configured_key) == key_hash:
            return True, key_hash
    return False, ""


def validate_ui_api_key(api_key: str | None) -> bool:
    settings = get_settings()
    if not settings.ui_api_key:
        return True
    return api_key == settings.ui_api_key
