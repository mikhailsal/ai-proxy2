"""Adapter registry — maps provider name to adapter instance."""

import os

import structlog

from ai_proxy.adapters.base import BaseAdapter
from ai_proxy.adapters.openai_compat import OpenAICompatAdapter
from ai_proxy.config.settings import AppConfig

logger = structlog.get_logger()

_registry: dict[str, BaseAdapter] = {}


def build_registry(config: AppConfig) -> dict[str, BaseAdapter]:
    global _registry
    _registry = {}
    for name, prov in config.providers.items():
        api_key = None
        if prov.api_key_env:
            api_key = os.environ.get(prov.api_key_env)
        else:
            env_var = f"{name.upper()}_API_KEY"
            api_key = os.environ.get(env_var)

        if prov.type == "openai_compatible":
            _registry[name] = OpenAICompatAdapter(
                provider_name=name,
                endpoint_url=prov.endpoint,
                api_key=api_key,
                headers=prov.headers,
                timeout=prov.timeout,
            )
        else:
            logger.warning("unknown_provider_type", name=name, type=prov.type)

    logger.info("adapter_registry_built", adapters=list(_registry.keys()))
    return _registry


def get_adapter_registry() -> dict[str, BaseAdapter]:
    return _registry
