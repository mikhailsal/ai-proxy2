"""Tests for client disconnect during streaming — partial response must be saved."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from starlette.requests import Request

from ai_proxy.api.proxy import streaming

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [(b"authorization", b"Bearer proxy-secret")],
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
        "server": ("test", 80),
        "query_string": b"",
    }
    return Request(scope)


async def _stalling_body(*chunks: bytes) -> AsyncGenerator[bytes, None]:
    for chunk in chunks:
        yield chunk
    await asyncio.sleep(100)
    yield b"data: [DONE]\n\n"  # pragma: no cover


@pytest.mark.asyncio
async def test_relay_stream_chunks_records_client_disconnect() -> None:
    """CancelledError from client disconnect is recorded in StreamState."""
    gate = asyncio.Event()

    async def body() -> AsyncGenerator[bytes, None]:
        yield b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        yield b'data: {"choices":[{"delta":{"content":"b"}}]}\n\n'
        gate.set()
        await asyncio.sleep(100)
        yield b"data: [DONE]\n\n"  # pragma: no cover

    state = streaming.StreamState()
    received: list[bytes] = []

    async def consume():
        async for chunk in streaming.relay_stream_chunks(SimpleNamespace(body=body()), state):
            received.append(chunk)

    task = asyncio.create_task(consume())
    await gate.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert state.response_status_code == 499
    assert state.stream_error_message == "Client disconnected"
    assert len(received) == 2
    assert len(state.chunks_collected) == 2


@pytest.mark.asyncio
async def test_build_streaming_response_logs_on_client_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When client disconnects mid-stream, partial response must still be logged."""
    logged: list[object] = []
    monkeypatch.setattr(streaming, "enqueue_log", lambda entry: logged.append(entry) or asyncio.sleep(0))

    gate = asyncio.Event()
    body = _stalling_body(
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
        b'data: {"choices":[{"delta":{"content":" World"}}]}\n\n',
    )

    async def gated_body() -> AsyncGenerator[bytes, None]:
        count = 0
        async for chunk in body:
            yield chunk
            count += 1
            if count == 2:
                gate.set()

    upstream = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream"},
        content_type="text/event-stream",
        body=gated_body(),
        error_body=None,
        sent_request_body={"model": "provider-model"},
    )
    response = streaming.build_streaming_response(
        request=_make_request(),
        request_id=uuid.uuid4(),
        key_hash="hash",
        sent_request_headers=None,
        forward_body={"model": "provider-model"},
        forward_body_raw='{"model":"provider-model"}',
        route=SimpleNamespace(provider_name="provider", mapped_model="mapped-model"),
        model_requested="gpt-4o-mini",
        start_time=0.0,
        upstream_stream=upstream,
        proxy_response_headers=lambda h: dict(h),
    )

    task = asyncio.create_task(_exhaust(response.body_iterator))
    await gate.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert len(logged) == 1, "Partial response must be logged even on disconnect"
    entry = logged[0]
    assert entry.error_message == "Client disconnected"
    assert len(entry.stream_chunks) == 2
    assert entry.response_body["choices"][0]["message"]["content"] == "Hello World"


async def _exhaust(iterator):
    async for _ in iterator:
        pass
