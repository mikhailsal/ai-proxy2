"""YAML config loader with hot-reload support."""

import structlog
import yaml

from ai_proxy.config.settings import AppConfig, KeyMappingEntry, ProviderConfig

logger = structlog.get_logger()

_app_config: AppConfig | None = None


def load_config(config_path: str) -> AppConfig:
    global _app_config
    try:
        with open(config_path) as f:  # noqa: PTH123
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("config_file_not_found", path=config_path)
        raw = {}

    providers = {}
    for name, prov_data in raw.get("providers", {}).items():
        providers[name] = ProviderConfig(**prov_data)

    key_mappings: dict[str, KeyMappingEntry] = {}
    for client_key, mapping_data in raw.get("key_mappings", {}).items():
        if isinstance(mapping_data, dict):
            key_mappings[client_key] = KeyMappingEntry(**mapping_data)

    _app_config = AppConfig(
        providers=providers,
        model_mappings=raw.get("model_mappings", {}),
        access_rules=raw.get("access_rules", {}),
        modification_rules=raw.get("modification_rules", []),
        bypass=raw.get("bypass", {}),
        key_mappings=key_mappings,
        logging=raw.get("logging", {}),
        grouping=raw.get("grouping", {}),
    )
    logger.info(
        "config_loaded",
        providers=list(providers.keys()),
        mappings=len(_app_config.model_mappings),
        bypass_enabled=_app_config.bypass.enabled,
        key_mappings_count=len(_app_config.key_mappings),
    )
    return _app_config


def get_app_config() -> AppConfig:
    if _app_config is None:
        msg = "Config not loaded. Call load_config() first."
        raise RuntimeError(msg)
    return _app_config


def reload_config(config_path: str) -> AppConfig:
    logger.info("config_reloading", path=config_path)
    return load_config(config_path)


def reset_config() -> None:
    global _app_config
    _app_config = None
