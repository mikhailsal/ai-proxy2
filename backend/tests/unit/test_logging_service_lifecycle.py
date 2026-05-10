import asyncio

import pytest

from ai_proxy.logging import service


@pytest.mark.asyncio
async def test_logging_service_start_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_flush_loop(batch_size: int = 50, flush_interval: float = 5.0) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(service, "_flush_loop", fake_flush_loop)
    task = service.start_logging_service(batch_size=1, flush_interval=0.01)
    assert task is service._flush_task
    await service.stop_logging_service()
    assert service._flush_task is None
