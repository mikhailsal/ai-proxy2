"""YAML config loader with hot-reload support.

Loads public config from config.yml and merges secrets from config.secrets.yml.
Client keys in key_mappings are stored in plaintext in the secrets file and
auto-hashed (SHA-256) at load time.
"""

import hashlib
from collections.abc import Mapping
from typing import Any

import structlog
import yaml
from pydantic import ValidationError

from ai_proxy.config.settings import AppConfig, KeyMappingEntry, ProviderConfig
from ai_proxy.core.model_mappings import parse_mapping

logger = structlog.get_logger()

_app_config: AppConfig | None = None


class ConfigValidationError(ValueError):
    """Raised when config files are syntactically or structurally invalid."""


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _format_yaml_error(path: str, exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None)
    problem = getattr(exc, "problem", None) or str(exc)
    if mark is None:
        return f"Invalid YAML in {path}: {problem}"
    return f"Invalid YAML in {path}:{mark.line + 1}:{mark.column + 1}: {problem}"


def _format_validation_error(source: str, exc: ValidationError) -> str:
    details = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "root"
        details.append(f"{location}: {error['msg']}")
    detail_text = "; ".join(details) if details else str(exc)
    return f"Invalid configuration in {source}: {detail_text}"


def _expect_mapping(value: object, *, field_name: str, source: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    raise ConfigValidationError(f"Invalid configuration in {source}: {field_name} must be a mapping")


def _load_providers(raw: Mapping[str, Any], *, source: str) -> dict[str, ProviderConfig]:
    raw_providers = _expect_mapping(raw.get("providers", {}), field_name="providers", source=source)
    providers: dict[str, ProviderConfig] = {}
    try:
        for name, prov_data in raw_providers.items():
            provider_data = _expect_mapping(prov_data, field_name=f"providers.{name}", source=source)
            providers[name] = ProviderConfig(**provider_data)
    except ValidationError as exc:
        raise ConfigValidationError(_format_validation_error(source, exc)) from exc
    return providers


def _load_key_mappings(raw_mappings: Mapping[str, Any], *, source: str) -> dict[str, KeyMappingEntry]:
    result: dict[str, KeyMappingEntry] = {}
    for client_key, mapping_data in raw_mappings.items():
        if not isinstance(mapping_data, Mapping):
            continue
        entry_data = {str(key): item for key, item in mapping_data.items()}
        hashed = _hash_key(client_key) if not _looks_like_hash(client_key) else client_key
        try:
            result[hashed] = KeyMappingEntry(**entry_data)
        except ValidationError as exc:
            raise ConfigValidationError(_format_validation_error(source, exc)) from exc
    return result


def _load_api_keys(secrets: Mapping[str, Any]) -> list[str]:
    api_keys_raw = secrets.get("api_keys", [])
    if isinstance(api_keys_raw, str):
        return [key.strip() for key in api_keys_raw.split(",") if key.strip()]
    if isinstance(api_keys_raw, list):
        return [str(key).strip() for key in api_keys_raw if str(key).strip()]
    return []


def _load_model_mappings(raw: Mapping[str, Any], *, source: str) -> dict[str, str]:
    raw_model_mappings = _expect_mapping(raw.get("model_mappings", {}), field_name="model_mappings", source=source)
    model_mappings: dict[str, str] = {}
    for client_model, mapping in raw_model_mappings.items():
        if not isinstance(mapping, str):
            raise ConfigValidationError(
                f"Invalid configuration in {source}: model_mappings.{client_model} must map to a string"
            )
        model_mappings[client_model] = mapping
    return model_mappings


def _build_app_config(
    raw: Mapping[str, Any],
    *,
    config_path: str,
    providers: dict[str, ProviderConfig],
    model_mappings: dict[str, str],
    key_mappings: dict[str, KeyMappingEntry],
    api_keys: list[str],
    ui_api_key: str,
) -> AppConfig:
    try:
        return AppConfig(
            providers=providers,
            model_mappings=model_mappings,
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
    except ValidationError as exc:
        raise ConfigValidationError(_format_validation_error(config_path, exc)) from exc


def _load_yaml(path: str) -> dict[str, Any]:
    try:
        with open(path) as f:  # noqa: PTH123
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        raise ConfigValidationError(_format_yaml_error(path, exc)) from exc


def _load_secrets(secrets_path: str) -> dict[str, Any]:
    raw = _load_yaml(secrets_path)
    if not raw:
        logger.info("secrets_file_not_found_or_empty", path=secrets_path)
        return {}
    logger.info("secrets_loaded", path=secrets_path)
    return raw


def _looks_like_hash(value: str) -> bool:
    """Detect if a value is already a 64-char hex SHA-256 hash."""
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_model_mappings(model_mappings: Mapping[str, str], provider_names: set[str], *, source: str) -> None:
    for client_model, mapping in model_mappings.items():
        provider_name, _, _ = parse_mapping(mapping)
        if provider_name not in provider_names:
            raise ConfigValidationError(
                "Invalid configuration in "
                f"{source}: model_mappings.{client_model} "
                f"references unknown provider '{provider_name}'"
            )


def load_config(config_path: str, secrets_path: str | None = None) -> AppConfig:
    global _app_config
    raw = _load_yaml(config_path)
    if not raw:
        logger.warning("config_file_not_found", path=config_path)

    secrets: dict[str, Any] = {}
    if secrets_path:
        secrets = _load_secrets(secrets_path)

    providers = _load_providers(raw, source=config_path)

    raw_key_mappings = _expect_mapping(
        secrets.get("key_mappings", raw.get("key_mappings", {})) or {},
        field_name="key_mappings",
        source=secrets_path or config_path,
    )
    key_mappings = _load_key_mappings(raw_key_mappings, source=secrets_path or config_path)
    api_keys = _load_api_keys(secrets)
    ui_api_key = str(secrets.get("ui_api_key", "")) or ""
    model_mappings = _load_model_mappings(raw, source=config_path)

    _app_config = _build_app_config(
        raw,
        config_path=config_path,
        providers=providers,
        model_mappings=model_mappings,
        key_mappings=key_mappings,
        api_keys=api_keys,
        ui_api_key=ui_api_key,
    )

    _validate_model_mappings(_app_config.model_mappings, set(providers), source=config_path)

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
