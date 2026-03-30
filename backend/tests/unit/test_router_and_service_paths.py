from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.adapters.base import ProviderResponse, ProviderStreamResponse
from ai_proxy.api.proxy import router as proxy_router
from ai_proxy.app import create_app
from ai_proxy.logging import service


class FakeSuccessAdapter:
    async def chat_completions(self, request_body, headers):
        return ProviderResponse(
            status_code=201,
            headers={
                "content-type": "application/json",
                "x-upstream": "ok",
                "connection": "keep-alive",
            },
            body=b'{"usage":{"prompt_tokens":1,"completion_tokens":2,"total_tokens":3}}',
            content_type="application/json",
        )

    async def stream_chat_completions(self, request_body, headers):
        return ProviderStreamResponse(status_code=200, headers={})

    async def list_models(self):
        return []


class FakeErrorStreamAdapter:
    async def chat_completions(self, request_body, headers):
        raise AssertionError("non-stream path not used")

    async def stream_chat_completions(self, request_body, headers):
        return ProviderStreamResponse(
            status_code=429,
            headers={"content-type": "application/json", "connection": "close"},
            error_body=b'{"error":{"message":"rate limited"}}',
            content_type="application/json",
        )

    async def list_models(self):
        return []


@pytest.mark.asyncio
async def test_chat_completions_validation_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key: (False, ""))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        invalid_json = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            content="not-json",
        )
        not_object = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json=["not", "an", "object"],
        )
        invalid_key = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer bad-key"},
            json={"model": "gpt-4o-mini"},
        )

    assert invalid_json.status_code == 400
    assert not_object.status_code == 400
    assert invalid_key.status_code == 401


@pytest.mark.asyncio
async def test_chat_completions_route_and_access_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key: (True, "hash"))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing_model = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"messages": []},
        )

        monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (False, "blocked"))
        blocked = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"model": "gpt-4o-mini", "messages": []},
        )

        monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
        monkeypatch.setattr(
            proxy_router,
            "resolve_model",
            lambda _model: (_ for _ in ()).throw(ValueError("missing route")),
        )
        not_found = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"model": "gpt-4o-mini", "messages": []},
        )

    assert missing_model.status_code == 400
    assert blocked.status_code == 403
    assert not_found.status_code == 404


@pytest.mark.asyncio
async def test_non_streaming_and_streaming_success_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    logged_entries = []

    async def capture_log(entry):
        logged_entries.append(entry)

    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda _key: (True, "hash"))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda *_args: (True, ""))
    monkeypatch.setattr(proxy_router, "apply_modifications", lambda body, headers, *_args: (body, headers))
    monkeypatch.setattr(proxy_router, "enqueue_log", capture_log)

    route = SimpleNamespace(provider_name="provider", mapped_model="mapped-model", adapter=FakeSuccessAdapter())
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key", "X-Request-ID": "req-1"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]},
        )

    assert response.status_code == 201
    assert response.headers["x-upstream"] == "ok"
    assert "connection" not in response.headers
    assert logged_entries[0].total_tokens == 3
    assert logged_entries[0].error_message is None

    route = SimpleNamespace(provider_name="provider", mapped_model="mapped-model", adapter=FakeErrorStreamAdapter())
    monkeypatch.setattr(proxy_router, "resolve_model", lambda _model: route)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        stream_response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer proxy-key"},
            json={"model": "gpt-4o-mini", "messages": [], "stream": True},
        )

    assert stream_response.status_code == 429
    assert stream_response.headers["content-type"].startswith("application/json")
    assert stream_response.json() == {"error": {"message": "rate limited"}}


@pytest.mark.asyncio
async def test_list_models_and_transport_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    monkeypatch.setattr(proxy_router, "validate_proxy_api_key", lambda key: (bool(key), "hash"))
    monkeypatch.setattr(proxy_router, "check_model_access", lambda _hash, model: (model != "blocked-model", "blocked"))
    monkeypatch.setattr(
        proxy_router,
        "get_app_config",
        lambda: SimpleNamespace(
            model_mappings={
                "gpt-4o-mini": "provider:model",
                "gpt-*": "provider:*",
                "blocked-model": "provider:blocked",
            }
        ),
    )

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/v1/models")
        authorized = await client.get("/v1/models", headers={"Authorization": "Bearer proxy-key"})

    assert unauthorized.status_code == 401
    assert authorized.json() == {
        "object": "list",
        "data": [{"id": "gpt-4o-mini", "object": "model", "owned_by": "ai-proxy"}],
    }
    assert proxy_router._extract_api_key(SimpleNamespace(headers={"Authorization": "Basic nope"})) is None
    assert proxy_router._transport_error_status(httpx.TimeoutException("boom")) == 504
    connect_error = httpx.ConnectError("boom", request=httpx.Request("GET", "https://example.com"))
    assert proxy_router._transport_error_status(connect_error) == 502
    assert proxy_router._extract_usage({}) == (None, None, None)
    usage_payload = {"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}
    assert proxy_router._extract_usage(usage_payload) == (1, 2, 3)
    assert proxy_router._extract_error_message({"error": {"message": "broken"}}) == "broken"
    assert proxy_router._extract_error_message({"message": "broken"}) == "broken"
    assert proxy_router._extract_error_message({"raw_text": "broken"}) == "broken"
    assert proxy_router._extract_error_message(None, "fallback") == "fallback"


@pytest.mark.asyncio
async def test_logging_flush_loop_and_reload_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    original_queue = service._queue
    service._queue = asyncio.Queue()
    writes = []

    async def fake_write_batch(_session_factory, entries):
        writes.append(len(entries))

    monkeypatch.setattr(service, "get_engine", lambda: object())
    monkeypatch.setattr(service, "async_sessionmaker", lambda *args, **kwargs: object())
    monkeypatch.setattr(service, "_write_batch", fake_write_batch)

    await service._queue.put(service.LogEntry(provider_name="provider"))
    await service._queue.put(service.LogEntry(provider_name="provider"))
    await service._queue.put(service.LogEntry(provider_name="provider"))

    task = asyncio.create_task(service._flush_loop(batch_size=2, flush_interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert writes[:2] == [2, 1]

    async def raise_on_write(_session_factory, _entries):
        raise RuntimeError("boom")

    service._queue = asyncio.Queue()
    await service._queue.put(service.LogEntry(provider_name="provider"))
    monkeypatch.setattr(service, "_write_batch", raise_on_write)
    task = asyncio.create_task(service._flush_loop(batch_size=1, flush_interval=0.01))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    monkeypatch.setattr("ai_proxy.app.build_registry", lambda _config: None)
    monkeypatch.setattr("ai_proxy.config.loader.reload_config", lambda _path: SimpleNamespace())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reload_response = await client.post("/admin/reload-config")

    assert reload_response.json() == {"status": "reloaded"}
    service._queue = original_queue


@pytest.mark.asyncio
async def test_chat_repository_grouping_branches() -> None:
    record = SimpleNamespace(id=uuid.uuid4(), timestamp=None)

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

        def scalars(self):
            return SimpleNamespace(all=lambda: self.rows)

    rows = [SimpleNamespace(group_key=None, message_count=1, first_message=None, last_message=None, models_used=None)]

    class FakeSession:
        async def execute(self, query):
            if "GROUP BY" in str(query):
                return Result(rows)
            return Result([record])

    from ai_proxy.db.repositories import chats as chats_repo

    session = FakeSession()
    assert await chats_repo.get_conversations(session, group_by="client", limit=10, offset=0) == [
        {
            "group_key": "unknown",
            "message_count": 1,
            "first_message": None,
            "last_message": None,
            "models_used": [],
        }
    ]
    assert await chats_repo.get_conversations(session, group_by="model", limit=10, offset=0)
    assert await chats_repo.get_conversations(session, group_by="other", limit=10, offset=0)
