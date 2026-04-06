"""YAML config loader with hot-reload support.

Loads public config from config.yml and merges secrets from config.secrets.yml.
Client keys in key_mappings are stored in plaintext in the secrets file and
auto-hashed (SHA-256) at load time.
"""

import hashlib

import structlog
import yaml

from ai_proxy.config.settings import AppConfig, KeyMappingEntry, ProviderConfig

logger = structlog.get_logger()

_app_config: AppConfig | None = None


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _load_yaml(path: str) -> dict:
    try:
        with open(path) as f:  # noqa: PTH123
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _load_secrets(secrets_path: str) -> dict:
    raw = _load_yaml(secrets_path)
    if not raw:
        logger.info("secrets_file_not_found_or_empty", path=secrets_path)
        return {}
    logger.info("secrets_loaded", path=secrets_path)
    return raw


def _build_key_mappings(raw_mappings: dict) -> dict[str, KeyMappingEntry]:
    """Build key mappings, auto-hashing plaintext client keys."""
    result: dict[str, KeyMappingEntry] = {}
    for client_key, mapping_data in raw_mappings.items():
        if not isinstance(mapping_data, dict):
            continue
        hashed = _hash_key(client_key) if not _looks_like_hash(client_key) else client_key
        result[hashed] = KeyMappingEntry(**mapping_data)
    return result


def _looks_like_hash(value: str) -> bool:
    """Detect if a value is already a 64-char hex SHA-256 hash."""
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def load_config(config_path: str, secrets_path: str | None = None) -> AppConfig:
    global _app_config
    raw = _load_yaml(config_path)
    if not raw:
        logger.warning("config_file_not_found", path=config_path)

    secrets: dict = {}
    if secrets_path:
        secrets = _load_secrets(secrets_path)

    providers = {}
    for name, prov_data in raw.get("providers", {}).items():
        providers[name] = ProviderConfig(**prov_data)

    raw_key_mappings = secrets.get("key_mappings", raw.get("key_mappings", {})) or {}
    key_mappings = _build_key_mappings(raw_key_mappings)

    api_keys_raw = secrets.get("api_keys", [])
    if isinstance(api_keys_raw, str):
        api_keys = [k.strip() for k in api_keys_raw.split(",") if k.strip()]
    elif isinstance(api_keys_raw, list):
        api_keys = [str(k).strip() for k in api_keys_raw if str(k).strip()]
    else:
        api_keys = []

    ui_api_key = str(secrets.get("ui_api_key", "")) or ""

    _app_config = AppConfig(
        providers=providers,
        model_mappings=raw.get("model_mappings", {}),
        response=raw.get("response", {}),
        access_rules=raw.get("access_rules", {}),
        modification_rules=raw.get("modification_rules", []),
        bypass=raw.get("bypass", {}),
        key_mappings=key_mappings,
        api_keys=api_keys,
        ui_api_key=ui_api_key,
        logging=raw.get("logging", {}),
        grouping=raw.get("grouping", {}),
    )
    logger.info(
        "config_loaded",
        providers=list(providers.keys()),
        mappings=len(_app_config.model_mappings),
        bypass_enabled=_app_config.bypass.enabled,
        key_mappings_count=len(_app_config.key_mappings),
        api_keys_count=len(_app_config.api_keys),
        ui_api_key_set=bool(_app_config.ui_api_key),
        secrets_loaded=bool(secrets),
    )
    return _app_config


def get_app_config() -> AppConfig:
    if _app_config is None:
        msg = "Config not loaded. Call load_config() first."
        raise RuntimeError(msg)
    return _app_config


def reload_config(config_path: str, secrets_path: str | None = None) -> AppConfig:
    logger.info("config_reloading", path=config_path)
    return load_config(config_path, secrets_path=secrets_path)


def reset_config() -> None:
    global _app_config
    _app_config = None
