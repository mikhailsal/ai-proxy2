from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar

import pytest
from starlette.requests import Request

from ai_proxy.adapters.base import BaseAdapter, ProviderResponse, ProviderStreamResponse, _parse_body
from ai_proxy.adapters.openai_compat import OpenAICompatAdapter, parse_sse_chunk
from ai_proxy.api.proxy import streaming

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class DummyAdapter(BaseAdapter):
    async def chat_completions(self, request_body, headers):
        return ProviderResponse(status_code=200, headers={}, body=b"{}", content_type="application/json")

    async def stream_chat_completions(self, request_body, headers):
        return ProviderStreamResponse(status_code=200, headers={})

    async def list_models(self):
        return []


def make_request() -> Request:
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


def test_parse_body_and_provider_response_helpers() -> None:
    assert _parse_body(b"", "application/json") is None
    assert _parse_body(b'{"ok":true}', "application/json") == {"ok": True}
    assert _parse_body(b"not-json", "application/json") == {"raw_text": "not-json"}
    assert _parse_body(b"plain-text", "text/plain") == {"raw_text": "plain-text"}

    response = ProviderResponse(status_code=200, headers={}, body=b'{"ok":true}', content_type="application/json")
    stream = ProviderStreamResponse(status_code=400, headers={}, error_body=b"plain", content_type="text/plain")
    adapter = DummyAdapter("provider", "https://provider.example/", None, {"X-Test": "1"}, 30)

    assert response.parsed_body() == {"ok": True}
    assert stream.parsed_error_body() == {"raw_text": "plain"}
    assert adapter.endpoint_url == "https://provider.example"
    assert adapter.extra_headers == {"X-Test": "1"}
    assert adapter.timeout == 30


@pytest.mark.asyncio
async def test_openai_compat_chat_completions_builds_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    class FakeResponse:
        status_code: ClassVar[int] = 201
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json", "x-upstream": "ok"}
        content: ClassVar[bytes] = b'{"id":"resp"}'

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict[str, str]) -> FakeResponse:
            calls["url"] = url
            calls["json"] = json
            calls["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr("ai_proxy.adapters.openai_compat.httpx.AsyncClient", FakeAsyncClient)

    adapter = OpenAICompatAdapter(
        provider_name="provider",
        endpoint_url="https://provider.example",
        api_key="provider-secret",
        headers={"X-Provider": "yes"},
        timeout=15,
    )

    response = await adapter.chat_completions(
        {"model": "gpt-4o-mini"},
        {"X-Request-ID": "req-1", "X-Session-ID": "session-1"},
    )

    assert calls["url"] == "https://provider.example/chat/completions"
    assert calls["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer provider-secret",
        "X-Provider": "yes",
        "X-Request-ID": "req-1",
        "X-Session-ID": "session-1",
    }
    assert response.parsed_body() == {"id": "resp"}


@pytest.mark.asyncio
async def test_openai_compat_streaming_success(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class FakeStreamResponse:
        def __init__(self, *, is_error: bool = False) -> None:
            self.is_error = is_error
            self.status_code = 200 if not is_error else 429
            self.headers = {"content-type": "text/event-stream"}

        async def aiter_lines(self) -> AsyncGenerator[str, None]:
            yield 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
            yield 'data: {"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}'
            yield "data: [DONE]"

        async def aread(self) -> bytes:
            return b'{"error":{"message":"rate limited"}}'

    class FakeStreamContext:
        def __init__(self, response: FakeStreamResponse) -> None:
            self.response = response

        async def __aenter__(self) -> FakeStreamResponse:
            events.append("enter")
            return self.response

        async def __aexit__(self, exc_type, exc, tb) -> None:
            events.append("exit")
            return None

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

        def stream(self, method: str, url: str, json: dict, headers: dict[str, str]) -> FakeStreamContext:
            events.append(f"stream:{method}:{url}:{json['model']}")
            return FakeStreamContext(FakeStreamResponse())

        async def aclose(self) -> None:
            events.append("close")

    monkeypatch.setattr("ai_proxy.adapters.openai_compat.httpx.AsyncClient", FakeAsyncClient)

    adapter = OpenAICompatAdapter("provider", "https://provider.example", None)
    stream_response = await adapter.stream_chat_completions({"model": "gpt-4o-mini"}, {})
    chunks = [chunk async for chunk in stream_response.body or []]

    assert chunks[-1] == b"data: [DONE]\n\n"
    assert events == [
        "stream:POST:https://provider.example/chat/completions:gpt-4o-mini",
        "enter",
        "exit",
        "close",
    ]


@pytest.mark.asyncio
async def test_openai_compat_streaming_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStreamResponse:
        is_error: ClassVar[bool] = True
        status_code: ClassVar[int] = 429
        headers: ClassVar[dict[str, str]] = {"content-type": "text/event-stream"}

        async def aread(self) -> bytes:
            return b'{"error":{"message":"rate limited"}}'

    class FakeStreamContext:
        async def __aenter__(self) -> FakeStreamResponse:
            return FakeStreamResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeErrorClient:
        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

        def stream(self, method: str, url: str, json: dict, headers: dict[str, str]) -> FakeStreamContext:
            return FakeStreamContext()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("ai_proxy.adapters.openai_compat.httpx.AsyncClient", FakeErrorClient)
    adapter = OpenAICompatAdapter("provider", "https://provider.example", None)
    error_response = await adapter.stream_chat_completions({"model": "gpt-4o-mini"}, {})

    assert error_response.error_body == b'{"error":{"message":"rate limited"}}'
    assert error_response.parsed_error_body() == {"raw_text": '{"error":{"message":"rate limited"}}'}


@pytest.mark.asyncio
async def test_openai_compat_list_models_and_parse_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self, payload: dict[str, object], should_raise: bool = False) -> None:
            self.payload = payload
            self.should_raise = should_raise

        def raise_for_status(self) -> None:
            if self.should_raise:
                raise RuntimeError("boom")

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str]) -> FakeResponse:
            return FakeResponse({"data": [{"id": "model-1"}]})

    monkeypatch.setattr("ai_proxy.adapters.openai_compat.httpx.AsyncClient", FakeAsyncClient)
    adapter = OpenAICompatAdapter("provider", "https://provider.example", "secret", {"X-Test": "1"})

    assert await adapter.list_models() == [{"id": "model-1"}]
    assert parse_sse_chunk(b'data: {"value":1}') == {"value": 1}
    assert parse_sse_chunk(b"data: [DONE]") is None
    assert parse_sse_chunk(b"not-json") is None

    class FailingAsyncClient(FakeAsyncClient):
        async def get(self, url: str, headers: dict[str, str]) -> FakeResponse:
            return FakeResponse({}, should_raise=True)

    monkeypatch.setattr("ai_proxy.adapters.openai_compat.httpx.AsyncClient", FailingAsyncClient)
    assert await adapter.list_models() == []


@pytest.mark.asyncio
async def test_streaming_helpers_success_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    logged_entries = []

    async def capture_log(entry):
        logged_entries.append(entry)

    monkeypatch.setattr(streaming, "enqueue_log", capture_log)

    async def fake_body() -> AsyncGenerator[bytes, None]:
        yield b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        yield b'data: {"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}\n\n'
        yield b"data: [DONE]\n\n"

    upstream_stream = SimpleNamespace(
        status_code=200,
        headers={"content-type": "text/event-stream", "x-upstream": "1"},
        content_type="text/event-stream",
        body=fake_body(),
        error_body=None,
    )
    route = SimpleNamespace(provider_name="provider", mapped_model="mapped-model")

    response = streaming.build_streaming_response(
        request=make_request(),
        request_id=uuid.uuid4(),
        key_hash="hash",
        forward_body={"model": "mapped-model"},
        route=route,
        model_requested="gpt-4o-mini",
        start_time=0.0,
        upstream_stream=upstream_stream,
        proxy_response_headers=lambda headers: dict(headers),
    )
    chunks = [chunk async for chunk in response.body_iterator]

    assert chunks[0].startswith(b"data: ")
    assert response.headers["cache-control"] == "no-cache"
    assert logged_entries[0].stream_chunks is not None


@pytest.mark.asyncio
async def test_streaming_helpers_error_response(monkeypatch: pytest.MonkeyPatch) -> None:
    async def capture_log(entry):
        return None

    monkeypatch.setattr(streaming, "enqueue_log", capture_log)
    route = SimpleNamespace(provider_name="provider", mapped_model="mapped-model")

    error_stream = SimpleNamespace(
        status_code=429,
        headers={"content-type": "application/json"},
        error_body=b'{"error":{"message":"rate limited"}}',
        parsed_error_body=lambda: {"error": {"message": "rate limited"}},
    )

    error_response = await streaming.stream_error_response(
        request=make_request(),
        request_id=uuid.uuid4(),
        key_hash="hash",
        forward_body={"model": "mapped-model"},
        route=route,
        model_requested="gpt-4o-mini",
        start_time=0.0,
        upstream_stream=error_stream,
        extract_error_message=lambda body: body["error"]["message"],
        proxy_response_headers=lambda headers: dict(headers),
    )

    assert error_response.status_code == 429
    assert error_response.body == b'{"error":{"message":"rate limited"}}'


@pytest.mark.asyncio
async def test_streaming_helpers_handle_missing_body_and_transport_errors() -> None:
    state = streaming.StreamState(response_headers={"content-type": "text/event-stream"}, response_status_code=200)
    chunks = [chunk async for chunk in streaming.relay_stream_chunks(SimpleNamespace(body=None), state)]

    assert chunks == [b'data: {"error": {"message": "Provider stream was not established"}}\n\n']
    assert state.response_status_code == 502

    request_error = RuntimeError("boom")

    async def broken_body() -> AsyncGenerator[bytes, None]:
        raise request_error
        yield b""  # pragma: no cover

    state = streaming.StreamState()
    error_chunks = [chunk async for chunk in streaming.relay_stream_chunks(SimpleNamespace(body=broken_body()), state)]

    assert error_chunks == [b'data: {"error": {"message": "boom"}}\n\n']
    assert state.stream_error_message == "boom"

    assert streaming.assembled_stream_response(streaming.StreamState()) is None
    assert streaming.stream_error_event("boom") == b'data: {"error": {"message": "boom"}}\n\n'
