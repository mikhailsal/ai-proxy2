"""CLI helpers for validating AI Proxy config files before startup."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from ai_proxy.config.loader import ConfigValidationError, load_config
from ai_proxy.config.settings import AppConfig, get_settings

if TYPE_CHECKING:
    from collections.abc import Sequence


def validate_config_files(config_path: str, secrets_path: str | None = None) -> AppConfig:
    config_file = Path(config_path)
    if not config_file.is_file():
        raise ConfigValidationError(f"Config file not found: {config_path}")

    return load_config(config_path, secrets_path=secrets_path)


def main(argv: Sequence[str] | None = None) -> int:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Validate AI Proxy config files.")
    parser.add_argument("--config", default=settings.config_path, help="Path to config.yml")
    parser.add_argument("--secrets", default=settings.secrets_path, help="Path to config.secrets.yml")
    args = parser.parse_args(argv)

    try:
        validate_config_files(args.config, args.secrets)
    except ConfigValidationError as exc:
        print(f"Config validation failed: {exc}", file=sys.stderr)  # noqa: T201
        return 1

    print(f"Config validation passed: {args.config}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
