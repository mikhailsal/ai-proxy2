"""File-system watcher for automatic config hot-reload.

Monitors config.yml and config.secrets.yml for changes and reloads the
application configuration + adapter registry automatically.  Uses
``watchfiles`` (bundled with uvicorn[standard]) for efficient, OS-level
file-change notifications.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from watchfiles import awatch

if TYPE_CHECKING:
    from asyncio import Task

logger = structlog.get_logger()

_watcher_task: Task[None] | None = None


async def _watch_loop(config_path: str, secrets_path: str | None) -> None:
    """Watch config files and reload on change.

    Runs indefinitely until cancelled.  Parse / reload errors are logged
    but never propagate — the last-known-good config stays active.
    """
    from ai_proxy.adapters.registry import build_registry
    from ai_proxy.config.loader import reload_config

    watch_paths: list[Path] = [Path(config_path).resolve()]
    if secrets_path:
        secrets = Path(secrets_path).resolve()
        if secrets.exists():
            watch_paths.append(secrets)

    logger.info(
        "config_watcher_started",
        watching=[str(p) for p in watch_paths],
    )

    try:
        async for changes in awatch(*watch_paths):
            changed_files = [str(path) for _change_type, path in changes]
            logger.info("config_file_changed", files=changed_files)
            try:
                config = reload_config(config_path, secrets_path=secrets_path)
                build_registry(config)
                logger.info(
                    "config_hot_reloaded",
                    mappings=len(config.model_mappings),
                    providers=list(config.providers.keys()),
                )
            except Exception:
                logger.exception("config_hot_reload_failed")
    except asyncio.CancelledError:
        logger.info("config_watcher_stopped")


def start_watcher(config_path: str, secrets_path: str | None = None) -> Task[None]:
    """Launch the config file watcher as a background asyncio task."""
    global _watcher_task
    if _watcher_task is not None and not _watcher_task.done():
        logger.warning("config_watcher_already_running")
        return _watcher_task

    _watcher_task = asyncio.create_task(
        _watch_loop(config_path, secrets_path),
        name="config-file-watcher",
    )
    return _watcher_task


async def stop_watcher() -> None:
    """Cancel the watcher task and wait for it to finish."""
    global _watcher_task
    if _watcher_task is None or _watcher_task.done():
        return
    _watcher_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _watcher_task
    _watcher_task = None
