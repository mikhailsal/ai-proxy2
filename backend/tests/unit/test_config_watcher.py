"""Tests for ai_proxy.config.watcher — automatic config hot-reload."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_proxy.config import watcher

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_watcher_state():
    """Ensure each test starts with a clean watcher state."""
    watcher._watcher_task = None
    yield
    watcher._watcher_task = None


class _FakeChangeIterator:
    """Yields one batch of changes, then blocks until cancelled."""

    def __init__(self, changes: set[tuple[int, str]]):
        self._changes = changes
        self._yielded = False

    def __aiter__(self) -> AsyncIterator[set[tuple[int, str]]]:
        return self

    async def __anext__(self) -> set[tuple[int, str]]:
        if not self._yielded:
            self._yielded = True
            return self._changes
        await asyncio.sleep(3600)
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_watch_loop_reloads_on_change(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yml"
    config_file.write_text("providers: {}")

    fake_config = SimpleNamespace(model_mappings={"m1": "p:m1"}, providers={"openrouter": None})
    mock_reload = MagicMock(return_value=fake_config)
    mock_build = MagicMock()

    fake_changes: set[tuple[int, str]] = {(1, str(config_file))}

    with (
        patch.object(watcher, "awatch", return_value=_FakeChangeIterator(fake_changes)),
        patch("ai_proxy.config.loader.reload_config", mock_reload),
        patch("ai_proxy.adapters.registry.build_registry", mock_build),
        patch.object(watcher, "_running_in_docker", return_value=False),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), None))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    mock_reload.assert_called_once_with(str(config_file), secrets_path=None)
    mock_build.assert_called_once_with(fake_config)


@pytest.mark.asyncio
async def test_watch_loop_survives_reload_error(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yml"
    config_file.write_text("providers: {}")

    mock_reload = MagicMock(side_effect=ValueError("broken yaml"))
    fake_changes: set[tuple[int, str]] = {(1, str(config_file))}

    with (
        patch.object(watcher, "awatch", return_value=_FakeChangeIterator(fake_changes)),
        patch("ai_proxy.config.loader.reload_config", mock_reload),
        patch("ai_proxy.adapters.registry.build_registry") as mock_build,
        patch.object(watcher, "_running_in_docker", return_value=False),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), None))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    mock_reload.assert_called_once()
    mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_watch_loop_watches_parent_directories(tmp_path: Path) -> None:
    """The watcher should monitor parent directories, not individual files."""
    config_file = tmp_path / "config.yml"
    secrets_file = tmp_path / "config.secrets.yml"
    config_file.write_text("providers: {}")
    secrets_file.write_text("api_keys: []")

    captured_watch_paths: list[str] = []
    captured_kwargs: dict = {}

    def fake_awatch(*paths: Path, **kwargs: object) -> _FakeChangeIterator:
        captured_watch_paths.extend(str(p) for p in paths)
        captured_kwargs.update(kwargs)
        return _FakeChangeIterator({(1, str(config_file))})

    fake_config = SimpleNamespace(model_mappings={}, providers={})

    with (
        patch.object(watcher, "awatch", side_effect=fake_awatch),
        patch("ai_proxy.config.loader.reload_config", return_value=fake_config),
        patch("ai_proxy.adapters.registry.build_registry"),
        patch.object(watcher, "_running_in_docker", return_value=False),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), str(secrets_file)))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    assert len(captured_watch_paths) == 1
    assert captured_watch_paths[0] == str(tmp_path)
    assert captured_kwargs["recursive"] is False


@pytest.mark.asyncio
async def test_watch_loop_skips_missing_secrets(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yml"
    config_file.write_text("providers: {}")

    captured_watch_paths: list[str] = []

    def fake_awatch(*paths: Path, **_kwargs: object) -> _FakeChangeIterator:
        captured_watch_paths.extend(str(p) for p in paths)
        return _FakeChangeIterator({(1, str(config_file))})

    fake_config = SimpleNamespace(model_mappings={}, providers={})

    with (
        patch.object(watcher, "awatch", side_effect=fake_awatch),
        patch("ai_proxy.config.loader.reload_config", return_value=fake_config),
        patch("ai_proxy.adapters.registry.build_registry"),
        patch.object(watcher, "_running_in_docker", return_value=False),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), str(tmp_path / "nonexistent.yml")))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    assert len(captured_watch_paths) == 1
    assert captured_watch_paths[0] == str(tmp_path)


@pytest.mark.asyncio
async def test_watch_loop_filters_irrelevant_changes(tmp_path: Path) -> None:
    """Changes to files other than config.yml / config.secrets.yml are ignored."""
    config_file = tmp_path / "config.yml"
    config_file.write_text("providers: {}")

    irrelevant_changes: set[tuple[int, str]] = {(1, str(tmp_path / "random_file.txt"))}

    with (
        patch.object(watcher, "awatch", return_value=_FakeChangeIterator(irrelevant_changes)),
        patch("ai_proxy.config.loader.reload_config") as mock_reload,
        patch("ai_proxy.adapters.registry.build_registry") as mock_build,
        patch.object(watcher, "_running_in_docker", return_value=False),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), None))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    mock_reload.assert_not_called()
    mock_build.assert_not_called()


@pytest.mark.asyncio
async def test_watch_loop_enables_polling_in_docker(tmp_path: Path) -> None:
    """When running in Docker, force_polling should be enabled."""
    config_file = tmp_path / "config.yml"
    config_file.write_text("providers: {}")

    captured_kwargs: dict = {}

    def fake_awatch(*_paths: Path, **kwargs: object) -> _FakeChangeIterator:
        captured_kwargs.update(kwargs)
        return _FakeChangeIterator({(1, str(config_file))})

    fake_config = SimpleNamespace(model_mappings={}, providers={})

    with (
        patch.object(watcher, "awatch", side_effect=fake_awatch),
        patch("ai_proxy.config.loader.reload_config", return_value=fake_config),
        patch("ai_proxy.adapters.registry.build_registry"),
        patch.object(watcher, "_running_in_docker", return_value=True),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), None))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    assert captured_kwargs["force_polling"] is True


@pytest.mark.asyncio
async def test_watch_loop_disables_polling_outside_docker(tmp_path: Path) -> None:
    """Outside Docker, force_polling should be disabled."""
    config_file = tmp_path / "config.yml"
    config_file.write_text("providers: {}")

    captured_kwargs: dict = {}

    def fake_awatch(*_paths: Path, **kwargs: object) -> _FakeChangeIterator:
        captured_kwargs.update(kwargs)
        return _FakeChangeIterator({(1, str(config_file))})

    fake_config = SimpleNamespace(model_mappings={}, providers={})

    with (
        patch.object(watcher, "awatch", side_effect=fake_awatch),
        patch("ai_proxy.config.loader.reload_config", return_value=fake_config),
        patch("ai_proxy.adapters.registry.build_registry"),
        patch.object(watcher, "_running_in_docker", return_value=False),
    ):
        task = asyncio.create_task(watcher._watch_loop(str(config_file), None))
        await asyncio.sleep(0.05)
        task.cancel()
        await task

    assert captured_kwargs["force_polling"] is False


def test_running_in_docker_detects_dockerenv(tmp_path: Path) -> None:
    dockerenv = tmp_path / ".dockerenv"
    dockerenv.touch()
    with patch("ai_proxy.config.watcher.Path") as mock_path:
        mock_path.return_value.exists.return_value = True
        assert watcher._running_in_docker() is True


def test_running_in_docker_false_without_dockerenv() -> None:
    with patch("ai_proxy.config.watcher.Path") as mock_path:
        mock_path.return_value.exists.return_value = False
        assert watcher._running_in_docker() is False


@pytest.mark.asyncio
async def test_start_and_stop_watcher() -> None:
    mock_loop = AsyncMock()

    with patch.object(watcher, "_watch_loop", mock_loop):
        task = watcher.start_watcher("config.yml", secrets_path="secrets.yml")
        assert task is not None
        assert not task.done()
        assert watcher._watcher_task is task

        await watcher.stop_watcher()
        assert watcher._watcher_task is None


@pytest.mark.asyncio
async def test_start_watcher_prevents_duplicate() -> None:
    mock_loop = AsyncMock()

    with patch.object(watcher, "_watch_loop", mock_loop):
        task1 = watcher.start_watcher("config.yml")
        task2 = watcher.start_watcher("config.yml")
        assert task1 is task2

        await watcher.stop_watcher()


@pytest.mark.asyncio
async def test_stop_watcher_noop_when_not_running() -> None:
    assert watcher._watcher_task is None
    await watcher.stop_watcher()
    assert watcher._watcher_task is None


@pytest.mark.asyncio
async def test_stop_watcher_noop_when_already_done() -> None:
    done_task: asyncio.Task[None] = asyncio.create_task(asyncio.sleep(0))
    await done_task
    watcher._watcher_task = done_task

    await watcher.stop_watcher()
