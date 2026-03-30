from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from ai_proxy.api.ui import chats, export, requests
from ai_proxy.db.repositories import chats as chat_repo
from ai_proxy.db.repositories import requests as request_repo
from ai_proxy.logging import service
from ai_proxy.logging.masking import mask_api_key, mask_headers, mask_sensitive_fields
from ai_proxy.logging.models import LogEntry


def make_request_record(**overrides: object) -> SimpleNamespace:
    payload = {
        "id": uuid.uuid4(),
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "client_ip": "127.0.0.1",
        "client_api_key_hash": "hash",
        "method": "POST",
        "path": "/v1/chat/completions",
        "model_requested": "gpt-4o-mini",
        "model_resolved": "mapped-model",
        "response_status_code": 200,
        "latency_ms": 123.4,
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
        "cost": 0.01,
        "cache_status": "miss",
        "error_message": None,
        "request_headers": {"Authorization": "Bearer secret-token"},
        "request_body": {"messages": [{"role": "system", "content": "hello"}]},
        "response_headers": {"x-upstream": "1"},
        "response_body": {"choices": [{"message": {"content": "world"}}]},
        "stream_chunks": [{"choices": [{"delta": {"content": "world"}}]}],
        "reasoning_tokens": 0,
        "metadata_": {"trace": "abc"},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class QueryResult:
    def __init__(self, data, *, rowcount: int = 3) -> None:
        self.data = data
        self.rowcount = rowcount

    def all(self):
        return self.data

    def one(self):
        return self.data

    def scalar_one(self):
        return self.data

    def scalar_one_or_none(self):
        return self.data

    def scalars(self):
        return SimpleNamespace(all=lambda: self.data)


class RequestRepoSession:
    def __init__(self, record: SimpleNamespace) -> None:
        self.record = record
        self.executed_queries: list[tuple[str, object]] = []
        self.committed = False
        self.refreshed = False

    def add(self, value) -> None:
        self.executed_queries.append(("add", value))

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, value) -> None:
        self.refreshed = True

    async def execute(self, query):
        sql = str(query)
        self.executed_queries.append(("execute", sql))
        if "avg" in sql:
            return QueryResult(
                SimpleNamespace(total_requests=2, avg_latency=12.34, total_tokens=42, total_cost=0.456789)
            )
        if "count" in sql:
            return QueryResult(7)
        if "WHERE proxy_requests.id" in sql:
            return QueryResult(self.record)
        return QueryResult([self.record])


class ChatRepoSession:
    def __init__(self, record: SimpleNamespace) -> None:
        self.record = record
        self.rows = [
            SimpleNamespace(
                group_key="hello",
                message_count=2,
                first_message=record.timestamp,
                last_message=record.timestamp,
                models_used=["gpt-4o-mini"],
            )
        ]

    async def execute(self, query):
        if "group_key" in str(query):
            return QueryResult(self.rows)
        return QueryResult([self.record])


class ProviderLookupResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class LoggingSession:
    def __init__(self, provider_value=None) -> None:
        self.provider_value = provider_value
        self.added = []
        self.flushed = False
        self.committed = False

    async def execute(self, query):
        return ProviderLookupResult(self.provider_value)

    def add(self, value) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True
        self.added[-1].id = 12

    async def commit(self) -> None:
        self.committed = True


class SessionContext:
    def __init__(self, session: LoggingSession) -> None:
        self.session = session

    async def __aenter__(self) -> LoggingSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_request_route_helpers_and_export(monkeypatch: pytest.MonkeyPatch) -> None:
    record = make_request_record(id=uuid.UUID("11111111-1111-1111-1111-111111111111"))
    missing = uuid.UUID("22222222-2222-2222-2222-222222222222")

    async def list_requests_stub(*args, **kwargs):
        return [record]

    async def get_request_stub(_session, request_id):
        return record if request_id == record.id else None

    async def search_requests_stub(*args, **kwargs):
        return [record]

    async def get_stats_stub(*args, **kwargs):
        return {"total_requests": 1}

    monkeypatch.setattr(requests.req_repo, "decode_cursor", lambda _cursor: None)
    monkeypatch.setattr(requests.req_repo, "list_requests", list_requests_stub)
    monkeypatch.setattr(requests.req_repo, "get_request", get_request_stub)
    monkeypatch.setattr(requests.req_repo, "search_requests", search_requests_stub)
    monkeypatch.setattr(requests.req_repo, "get_stats", get_stats_stub)
    monkeypatch.setattr(export.req_repo, "get_request", get_request_stub)

    list_response = await requests.list_requests(
        session=object(),
        cursor=None,
        limit=50,
        model=None,
        client_hash=None,
        status_code=None,
        since=None,
        until=None,
    )
    detail_response = await requests.get_request(str(record.id), session=object())
    missing_response = await requests.get_request(str(missing), session=object())
    search_response = await requests.search(q="hello", limit=10, session=object())
    stats_response = await requests.get_stats(session=object())
    export_json_response = await export.export_request(str(record.id), format="json", session=object())
    export_markdown_response = await export.export_request(str(record.id), format="markdown", session=object())
    export_missing_response = await export.export_request(str(missing), format="json", session=object())

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert missing_response.status_code == 404
    assert search_response.status_code == 200
    assert stats_response.body == b'{"total_requests":1}'
    assert export_json_response.status_code == 200
    assert export_markdown_response.media_type == "text/markdown"
    assert b"# Request" in export_markdown_response.body
    assert export_missing_response.status_code == 404


@pytest.mark.asyncio
async def test_chat_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    record = make_request_record()

    async def get_conversations_stub(*args, **kwargs):
        return [{"group_key": "hello"}]

    async def get_messages_stub(*args, **kwargs):
        return [record]

    monkeypatch.setattr(chat_repo, "get_conversations", get_conversations_stub)
    monkeypatch.setattr(chat_repo, "get_conversation_messages", get_messages_stub)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/ui/v1/conversations/messages",
        "headers": [],
        "query_string": b"",
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b'{"group_key":"hello"}', "more_body": False}

    async def receive_missing() -> dict[str, object]:
        return {"type": "http.request", "body": b"{}", "more_body": False}

    list_response = await chats.list_conversations(session=object(), group_by="system_prompt", limit=10, offset=0)
    messages_response = await chats.get_conversation_messages(
        Request(scope, receive),
        session=object(),
        group_by="client",
    )
    missing_response = await chats.get_conversation_messages(
        Request(scope, receive_missing),
        session=object(),
        group_by="client",
    )

    assert list_response.status_code == 200
    assert messages_response.status_code == 200
    assert missing_response.status_code == 400


@pytest.mark.asyncio
async def test_request_repository_create_fetch_list_and_search() -> None:
    record = make_request_record()
    session = RequestRepoSession(record)

    created = await request_repo.create_request(session, id=record.id, path="/v1/chat/completions", method="POST")
    fetched = await request_repo.get_request(session, record.id)
    listed = await request_repo.list_requests(
        session,
        cursor=(record.timestamp, record.id),
        limit=1,
        model="gpt-4o-mini",
        client_hash="hash",
        status_code=200,
        since=record.timestamp,
        until=record.timestamp,
    )
    searched = await request_repo.search_requests(session, "hello", limit=1)

    assert created.id == record.id
    assert fetched == record
    assert listed == [record]
    assert searched == [record]
    assert session.committed is True
    assert session.refreshed is True
    assert session.executed_queries


@pytest.mark.asyncio
async def test_request_repository_count_stats_and_delete() -> None:
    record = make_request_record()
    session = RequestRepoSession(record)

    counted = await request_repo.get_request_count(session)
    stats = await request_repo.get_stats(session)
    deleted = await request_repo.delete_old_requests(session, before=record.timestamp)

    assert counted == 7
    assert stats == {"total_requests": 2, "avg_latency_ms": 12.34, "total_tokens": 42, "total_cost": 0.456789}
    assert deleted == 3


@pytest.mark.asyncio
async def test_chat_repository_functions() -> None:
    record = make_request_record()
    session = ChatRepoSession(record)

    conversations = await chat_repo.get_conversations(session, group_by="system_prompt", limit=10, offset=0)
    client_messages = await chat_repo.get_conversation_messages(session, "hello", group_by="client")
    model_messages = await chat_repo.get_conversation_messages(session, "hello", group_by="model")
    fallback_messages = await chat_repo.get_conversation_messages(session, "hello", group_by="other")

    assert conversations == [
        {
            "group_key": "hello",
            "message_count": 2,
            "first_message": record.timestamp.isoformat(),
            "last_message": record.timestamp.isoformat(),
            "models_used": ["gpt-4o-mini"],
        }
    ]
    assert client_messages == [record]
    assert model_messages == [record]
    assert fallback_messages == [record]


def test_masking_helpers_and_log_entry_factory() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/chat/completions",
            "headers": [(b"authorization", b"Bearer sk-secret-token")],
            "client": ("127.0.0.1", 1234),
            "scheme": "http",
            "server": ("test", 80),
            "query_string": b"",
        }
    )

    assert mask_api_key("short") == "***"
    assert mask_api_key("abcdefghijk") == "abc***hijk"
    assert mask_headers({"Authorization": "Bearer secret", "X-Test": "ok"}) == {
        "Authorization": "Bea***cret",
        "X-Test": "ok",
    }
    assert mask_sensitive_fields({"token": "secret-token", "nested": [{"password": "p4ssw0rd"}]}) == {
        "token": "sec***oken",
        "nested": [{"password": "***"}],
    }
    assert mask_sensitive_fields(None) is None
    assert mask_sensitive_fields("value") == "value"

    entry = LogEntry.from_proxy_context(
        entry_id=uuid.uuid4(),
        request=request,
        client_api_key_hash="hash",
        request_body={"model": "gpt-4o-mini"},
        model_requested="gpt-4o-mini",
        model_resolved="mapped-model",
        provider_name="provider",
        latency_ms=12.3,
        response_status_code=200,
        response_body={"ok": True},
    )

    assert entry.client_ip == "127.0.0.1"
    assert entry.path == "/v1/chat/completions"
    assert entry.response_body == {"ok": True}


@pytest.mark.asyncio
async def test_logging_service_enqueue_and_flush_without_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    original_queue = service._queue
    service._queue = asyncio.Queue(maxsize=1)

    try:
        await service.enqueue_log(LogEntry(provider_name="provider"))
        await service.enqueue_log(LogEntry(provider_name="provider"))
        assert service._queue.qsize() == 1
    finally:
        service._queue = original_queue

    monkeypatch.setattr(service, "get_engine", lambda: None)
    await service._flush_loop(batch_size=1, flush_interval=0.01)


@pytest.mark.asyncio
async def test_logging_service_provider_resolution_and_batch_write(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = SimpleNamespace(id=7)
    existing_session = LoggingSession(provider_value=provider)
    missing_session = LoggingSession(provider_value=None)
    monkeypatch.setattr(
        service,
        "get_app_config",
        lambda: SimpleNamespace(
            providers={
                "provider": SimpleNamespace(
                    endpoint="https://provider.example",
                    type="openai_compatible",
                    headers={"X-Test": "1"},
                    timeout=15,
                    fallback_for="primary",
                )
            }
        ),
    )

    assert await service._resolve_provider_id(existing_session, "provider") == 7
    assert await service._resolve_provider_id(missing_session, None) is None
    assert await service._resolve_provider_id(missing_session, "provider") == 12
    assert missing_session.flushed is True

    session_for_batch = LoggingSession(provider_value=provider)

    def session_factory() -> SessionContext:
        return SessionContext(session_for_batch)

    entry = LogEntry(
        provider_name="provider",
        request_body={"token": "secret-token"},
        request_headers={"Authorization": "Bearer secret"},
    )
    await service._write_batch(session_factory, [entry])

    assert session_for_batch.committed is True
    assert session_for_batch.added


@pytest.mark.asyncio
async def test_logging_service_start_and_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_flush_loop(batch_size: int = 50, flush_interval: float = 5.0) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(service, "_flush_loop", fake_flush_loop)
    task = service.start_logging_service(batch_size=1, flush_interval=0.01)
    assert task is service._flush_task
    await service.stop_logging_service()
    assert service._flush_task is None
