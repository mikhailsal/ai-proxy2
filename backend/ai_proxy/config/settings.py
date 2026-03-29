"""Pydantic Settings for AI Proxy."""

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ProviderConfig(BaseModel):
    type: str = "openai_compatible"
    endpoint: str
    api_key_env: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: int = 120
    fallback_for: str | None = None


class LoggingConfig(BaseModel):
    log_retention_days: int = 30
    batch_size: int = 50
    flush_interval_seconds: int = 5


class GroupingConfig(BaseModel):
    default_field: str = "system_prompt"


class AccessRule(BaseModel):
    allow: list[str] = Field(default_factory=list)
    block: list[str] = Field(default_factory=list)


class ModificationRule(BaseModel):
    match_provider: str = "*"
    match_model: str = "*"
    action: str  # add_header, remove_header, set_field, remove_field
    key: str
    value: str | None = None


class AppConfig(BaseModel):
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    model_mappings: dict[str, str] = Field(default_factory=dict)
    access_rules: dict[str, AccessRule] = Field(default_factory=dict)
    modification_rules: list[ModificationRule] = Field(default_factory=list)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    grouping: GroupingConfig = Field(default_factory=GroupingConfig)


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://ai_proxy:password@localhost:5432/ai_proxy"
    config_path: str = "config.yml"
    api_keys: str = ""
    ui_api_key: str = ""
    host: str = "0.0.0.0"  # noqa: S104
    port: int = 8000
    log_level: str = "info"
    cors_origins: str = "*"

    model_config = {"env_prefix": "", "case_sensitive": False}

    def get_api_keys(self) -> list[str]:
        if not self.api_keys:
            return []
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    def get_config_path(self) -> Path:
        return Path(self.config_path)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings  # noqa: PLW0603
    _settings = None
