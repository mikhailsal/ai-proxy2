from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from ai_proxy.adapters.registry import build_registry, get_adapter_registry
from ai_proxy.api import deps
from ai_proxy.config import loader
from ai_proxy.config.settings import (
    AccessRule,
    AppConfig,
    ModificationRule,
    ProviderConfig,
    get_settings,
    reset_settings,
)
from ai_proxy.core import access, modification, routing
from ai_proxy.core.access import check_model_access
from ai_proxy.core.modification import apply_modifications
from ai_proxy.core.routing import _parse_mapping, resolve_model
from ai_proxy.db import engine
from ai_proxy.security.auth import hash_api_key, mask_api_key, validate_proxy_api_key, validate_ui_api_key

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path


def test_settings_cache_and_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reset_settings()
    monkeypatch.setenv("API_KEYS", " one , two ,, three ")
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "config.yml"))

    settings = get_settings()

    assert settings.get_api_keys() == ["one", "two", "three"]
    assert settings.get_config_path() == tmp_path / "config.yml"
    assert str(settings.get_secrets_path()) == "config.secrets.yml"

    reset_settings()
    assert get_settings() is not settings


def test_loader_reads_yaml_and_supports_reload(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
providers:
  primary:
    endpoint: https://provider.example
model_mappings:
  gpt-4o-mini: primary:mapped-model
access_rules:
  abc123:
    allow: [gpt-*]
modification_rules:
  - action: add_header
    key: X-Test
    value: enabled
logging:
  batch_size: 10
grouping:
  default_field: client
""".strip()
    )

    config = loader.load_config(str(config_path))

    assert config.providers["primary"].endpoint == "https://provider.example"
    assert config.model_mappings["gpt-4o-mini"] == "primary:mapped-model"
    assert loader.get_app_config() == config
    assert loader.reload_config(str(config_path)).logging.batch_size == 10

    loader.reset_config()
    with pytest.raises(RuntimeError):
        loader.get_app_config()


def test_loader_handles_missing_config_file(tmp_path: Path) -> None:
    config = loader.load_config(str(tmp_path / "does-not-exist.yml"))
    assert config == AppConfig()


def test_loader_merges_secrets_file(tmp_path: Path) -> None:
    import hashlib

    config_path = tmp_path / "config.yml"
    config_path.write_text(
        """
providers:
  primary:
    endpoint: https://provider.example
bypass:
  enabled: false
""".strip()
    )

    secrets_path = tmp_path / "config.secrets.yml"
    secrets_path.write_text(
        """
api_keys:
  - "proxy-key-1"
  - "proxy-key-2"
ui_api_key: "ui-secret"
key_mappings:
  "proxy-key-1":
    provider_keys:
      primary: "sk-provider-key-for-client-1"
""".strip()
    )

    config = loader.load_config(str(config_path), secrets_path=str(secrets_path))

    assert config.api_keys == ["proxy-key-1", "proxy-key-2"]
    assert config.ui_api_key == "ui-secret"

    expected_hash = hashlib.sha256(b"proxy-key-1").hexdigest()
    assert expected_hash in config.key_mappings
    assert config.key_mappings[expected_hash].provider_keys["primary"] == "sk-provider-key-for-client-1"


def test_loader_auto_hashes_plaintext_keys_and_passes_hashed_through(tmp_path: Path) -> None:
    import hashlib

    pre_hashed = hashlib.sha256(b"already-hashed-input").hexdigest()

    secrets_path = tmp_path / "config.secrets.yml"
    secrets_path.write_text(
        f"""
key_mappings:
  "plaintext-client-key":
    provider_keys:
      openrouter: "sk-or-v1-key"
  "{pre_hashed}":
    provider_keys:
      openrouter: "sk-or-v1-other-key"
""".strip()
    )

    config_path = tmp_path / "config.yml"
    config_path.write_text("providers: {}")

    config = loader.load_config(str(config_path), secrets_path=str(secrets_path))

    plaintext_hash = hashlib.sha256(b"plaintext-client-key").hexdigest()
    assert plaintext_hash in config.key_mappings
    assert pre_hashed in config.key_mappings
    assert config.key_mappings[plaintext_hash].provider_keys["openrouter"] == "sk-or-v1-key"
    assert config.key_mappings[pre_hashed].provider_keys["openrouter"] == "sk-or-v1-other-key"


def test_loader_works_without_secrets_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("providers: {}")

    config = loader.load_config(str(config_path), secrets_path=str(tmp_path / "nonexistent.yml"))

    assert config.api_keys == []
    assert config.ui_api_key == ""
    assert config.key_mappings == {}


def test_access_rules_and_modifications(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AppConfig(
        access_rules={
            "blocked": AccessRule(block=["gpt-4*"]),
            "allowed": AccessRule(allow=["gpt-4o-mini"]),
        },
        modification_rules=[
            ModificationRule(action="add_header", key="X-Test", value="enabled"),
            ModificationRule(action="remove_header", key="Remove-Me"),
            ModificationRule(action="set_field", key="temperature", value="0.1"),
            ModificationRule(action="remove_field", key="remove_me"),
        ],
    )
    monkeypatch.setattr(access, "get_app_config", lambda: config)
    monkeypatch.setattr(modification, "get_app_config", lambda: config)

    assert check_model_access("unknown", "gpt-4o") == (True, "")
    assert check_model_access("blocked", "gpt-4o") == (False, "Model gpt-4o is blocked for this API key")
    assert check_model_access("allowed", "gpt-4o-mini") == (True, "")
    assert check_model_access("allowed", "gpt-4o") == (
        False,
        "Model gpt-4o is not in the allowlist for this API key",
    )

    body, headers = apply_modifications(
        {"remove_me": "value", "stream": False},
        {"Remove-Me": "gone"},
        "primary",
        "gpt-4o-mini",
    )

    assert headers == {"X-Test": "enabled"}
    assert body == {"stream": False, "temperature": "0.1"}


def test_registry_and_routing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIMARY_API_KEY", "secret-key")
    config = AppConfig(
        providers={
            "primary": ProviderConfig(endpoint="https://primary.example"),
            "secondary": ProviderConfig(endpoint="https://secondary.example", fallback_for="primary"),
            "unknown": ProviderConfig(endpoint="https://unknown.example", type="other"),
        },
        model_mappings={
            "gpt-4o-mini": "primary:mapped-model",
            "gpt-*": "secondary:*",
        },
    )

    registry = build_registry(config)
    assert set(registry) == {"primary", "secondary"}
    assert registry["primary"].api_key == "secret-key"
    assert get_adapter_registry() == registry
    assert _parse_mapping("provider:model") == ("provider", "model")
    assert _parse_mapping("provider") == ("provider", "provider")

    monkeypatch.setattr(routing, "get_app_config", lambda: config)
    monkeypatch.setattr(routing, "get_adapter_registry", lambda: registry)

    exact = resolve_model("gpt-4o-mini")
    wildcard = resolve_model("gpt-4o")

    assert exact.provider_name == "primary"
    assert exact.mapped_model == "mapped-model"
    assert wildcard.provider_name == "secondary"
    assert wildcard.mapped_model == "gpt-4o"

    with pytest.raises(ValueError, match="No route found"):
        resolve_model("unknown-model")


def test_proxy_and_ui_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    config = AppConfig(api_keys=["proxy-secret"], ui_api_key="ui-secret")
    monkeypatch.setattr(loader, "_app_config", config)

    settings = SimpleNamespace(get_api_keys=lambda: [], ui_api_key="")
    monkeypatch.setattr("ai_proxy.security.auth.get_settings", lambda: settings)

    assert len(hash_api_key("proxy-secret")) == 64
    assert mask_api_key("short") == "***"
    assert mask_api_key("abcdefghijk") == "abc*****ijk"
    assert validate_proxy_api_key("proxy-secret")[0] is True
    assert validate_proxy_api_key("proxy-secret")[2] is True
    ok, key_hash, is_known = validate_proxy_api_key("wrong")
    assert (ok, is_known) == (False, False)
    assert validate_ui_api_key("ui-secret") is True
    assert validate_ui_api_key("wrong") is False


def test_validate_proxy_api_key_bypass_mode() -> None:
    ok, key_hash, is_known = validate_proxy_api_key("any-random-key", bypass_enabled=True)
    assert ok is True
    assert key_hash == hash_api_key("any-random-key")
    assert is_known is False

    ok, key_hash, is_known = validate_proxy_api_key(None, bypass_enabled=True)
    assert ok is False
    assert key_hash == ""
    assert is_known is False


def test_adapter_build_headers_with_override() -> None:
    from ai_proxy.adapters.openai_compat import OpenAICompatAdapter

    adapter = OpenAICompatAdapter(
        provider_name="test",
        endpoint_url="https://example.com/v1",
        api_key="default-key",
    )

    headers_default = adapter._build_headers({})
    assert headers_default["Authorization"] == "Bearer default-key"

    headers_override = adapter._build_headers({}, override_api_key="override-key")
    assert headers_override["Authorization"] == "Bearer override-key"

    headers_none = adapter._build_headers({}, override_api_key=None)
    assert headers_none["Authorization"] == "Bearer default-key"


@pytest.mark.asyncio
async def test_deps_get_session_and_require_ui_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    yielded_sessions: list[str] = []
    valid_ui_token = "ui-secret"  # noqa: S105

    async def fake_get_db_session() -> AsyncGenerator[str, None]:
        yielded_sessions.append("session")
        yield "session"

    monkeypatch.setattr(deps, "get_db_session", fake_get_db_session)
    monkeypatch.setattr(deps, "validate_ui_api_key", lambda token: token == valid_ui_token)

    sessions = [session async for session in deps.get_session()]
    assert sessions == ["session"]
    assert yielded_sessions == ["session"]

    await deps.require_ui_auth("Bearer ui-secret")

    with pytest.raises(HTTPException, match="Invalid UI API key"):
        await deps.require_ui_auth("Bearer wrong")


@pytest.mark.asyncio
async def test_engine_init_dispose_and_session_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    created = {}

    class FakeSessionContext:
        async def __aenter__(self) -> str:
            return "session"

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeEngine:
        async def dispose(self) -> None:
            created["disposed"] = True

    def fake_create_async_engine(database_url: str, **kwargs: object) -> FakeEngine:
        created["database_url"] = database_url
        created["kwargs"] = kwargs
        return FakeEngine()

    def fake_async_sessionmaker(fake_engine: FakeEngine, **kwargs: object):
        created["session_kwargs"] = kwargs

        def factory() -> FakeSessionContext:
            return FakeSessionContext()

        return factory

    monkeypatch.setattr(engine, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(engine, "async_sessionmaker", fake_async_sessionmaker)

    await engine.dispose_engine()
    with pytest.raises(RuntimeError, match="Database not initialized"):
        [session async for session in engine.get_db_session()]

    engine.init_engine("postgresql+asyncpg://example")

    assert created["database_url"] == "postgresql+asyncpg://example"
    assert engine.get_engine() is not None
    assert [session async for session in engine.get_db_session()] == ["session"]

    await engine.dispose_engine()
    assert created["disposed"] is True
    assert engine.get_engine() is None
