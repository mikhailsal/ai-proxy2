from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from ai_proxy.api.ui import chats, export, requests
from ai_proxy.db.repositories import chats as chat_repo
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
        "client_request_headers": {"Authorization": "Bearer secret-token", "content-type": "application/json"},
        "request_body": {"messages": [{"role": "system", "content": "hello"}]},
        "client_request_body": {"messages": [{"role": "system", "content": "hello"}], "model": "gpt-4o-mini"},
        "response_headers": {"x-upstream": "1"},
        "client_response_headers": {"x-upstream": "1"},
        "response_body": {"choices": [{"message": {"content": "world"}}]},
        "client_response_body": None,
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

    async def get_req_stub(_s, rid):
        return record if rid == record.id else None

    async def list_stub(*_a, **_k):
        return [record]

    async def stats_stub(*_a, **_k):
        return {"total_requests": 1}

    monkeypatch.setattr(requests.req_repo, "list_requests", list_stub)
    monkeypatch.setattr(requests.req_repo, "get_request", get_req_stub)
    monkeypatch.setattr(requests.req_repo, "search_requests", list_stub)
    monkeypatch.setattr(requests.req_repo, "get_stats", stats_stub)
    monkeypatch.setattr(export.req_repo, "get_request", get_req_stub)

    s = object()
    lr = await requests.list_requests(
        session=s,
        cursor=None,
        limit=50,
        model=None,
        client_hash=None,
        status_code=None,
        since=None,
        until=None,
    )
    dr = await requests.get_request(str(record.id), session=s)
    mr = await requests.get_request(str(missing), session=s)
    sr = await requests.search(q="hello", limit=10, session=s)
    st = await requests.get_stats(session=s)
    ej = await export.export_request(str(record.id), format="json", session=s)
    em = await export.export_request(str(record.id), format="markdown", session=s)
    emiss = await export.export_request(str(missing), format="json", session=s)

    assert lr.status_code == 200
    assert dr.status_code == 200
    assert mr.status_code == 404
    assert sr.status_code == 200
    assert st.body == b'{"total_requests":1}'
    assert ej.status_code == 200
    assert em.media_type == "text/markdown" and b"# Request" in em.body
    assert emiss.status_code == 404


def test_serialize_request_extracts_message_previews_and_cost() -> None:
    record = make_request_record(
        cost=None,
        request_body={
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello world"},
            ]
        },
        response_body={
            "choices": [{"message": {"role": "assistant", "content": "hi there"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.002},
        },
    )
    result = requests._serialize_request(record)
    assert result["last_user_message"] == "hello world"
    assert result["assistant_response"] == "hi there"
    assert result["cost"] == 0.002

    record_tool = make_request_record(
        cost=None,
        request_body={"messages": [{"role": "user", "content": "call tool"}]},
        response_body={
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{"function": {"name": "search"}}, {"function": {"name": "fetch"}}],
                    }
                }
            ]
        },
    )
    assert requests._serialize_request(record_tool)["assistant_response"] == "search | fetch"
    assert requests._serialize_request(record_tool)["cost"] is None

    tool_with_args = {"name": "write_message", "arguments": '{"text": "hello", "channel": "general"}'}
    record_tool_args = make_request_record(
        cost=None,
        request_body={"messages": [{"role": "user", "content": "call tool"}]},
        response_body={"choices": [{"message": {"role": "assistant", "tool_calls": [{"function": tool_with_args}]}}]},
    )
    assert requests._serialize_request(record_tool_args)["assistant_response"] == (
        "write_message(text='hello', channel='general')"
    )


def test_serialize_request_cached_tokens_and_edge_cases() -> None:
    record_cached = make_request_record(
        response_body={
            "usage": {"prompt_tokens_details": {"cached_tokens": 50}},
            "choices": [{"message": {"content": "ok"}}],
        },
    )
    assert requests._extract_cached_tokens(record_cached) == 50

    record_list_content = make_request_record(
        request_body={
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {}},
                        {"type": "text", "text": "describe image"},
                    ],
                }
            ]
        },
    )
    assert requests._extract_last_user_message(record_list_content) == "describe image"

    empty_record = make_request_record(
        cost=None,
        request_body=None,
        client_request_body=None,
        response_body=None,
        client_response_body=None,
    )
    result_empty = requests._serialize_request(empty_record)
    assert result_empty["last_user_message"] is None
    assert result_empty["assistant_response"] is None
    assert result_empty["cost"] is None
    assert result_empty["cached_input_tokens"] is None


@pytest.mark.asyncio
async def test_chat_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    record = make_request_record()

    async def get_conversations_stub(*args, **kwargs):
        return [{"group_key": "hello", "group_label": "hello", "message_count": 2, "request_count": 1}]

    async def get_messages_stub(*args, **kwargs):
        return [{"id": "msg-1", "role": "user", "content": "hello", "source_request_id": str(record.id)}]

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


def test_build_conversation_messages_merges_repeated_history() -> None:
    first = make_request_record(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        request_body={
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ]
        },
        response_body={"choices": [{"message": {"role": "assistant", "content": "first reply"}}]},
    )
    second = make_request_record(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        request_body={
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "first reply"},
                {"role": "user", "content": "follow up"},
            ]
        },
        response_body={"choices": [{"message": {"role": "assistant", "content": "second reply"}}]},
    )

    messages = chat_repo.build_conversation_messages([first, second])

    assert [message["content"] for message in messages] == [
        "second reply",
        "follow up",
        "first reply",
        "hello",
        "system prompt",
    ]
    assert messages[-1]["repeat_count"] == 2
    assert messages[-2]["repeat_count"] == 2
    assert messages[-3]["repeat_count"] == 2
    assert messages[1]["source_request_id"] == str(second.id)


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
    assert mask_api_key("abcdefghijk") == "abc*****ijk"
    assert mask_headers({"Authorization": "Bearer secret", "X-Test": "ok"}) == {
        "Authorization": "Bea*******ret",
        "X-Test": "ok",
    }
    assert mask_sensitive_fields({"token": "secret-token", "nested": [{"password": "p4ssw0rd"}]}) == {
        "token": "sec******ken",
        "nested": [{"password": "p4s**0rd"}],
    }
    assert mask_sensitive_fields(None) is None
    assert mask_sensitive_fields("value") == "value"

    sent_headers = {"Content-Type": "application/json", "Authorization": "Bearer sk-provider-key"}
    entry = LogEntry.from_proxy_context(
        entry_id=uuid.uuid4(),
        request=request,
        client_api_key_hash="hash",
        request_headers=sent_headers,
        request_body={"model": "gpt-4o-mini"},
        model_requested="gpt-4o-mini",
        model_resolved="mapped-model",
        provider_name="provider",
        latency_ms=12.3,
        response_status_code=200,
        response_headers={"content-type": "application/json", "transfer-encoding": "chunked"},
        client_response_headers={"content-type": "application/json"},
        response_body={"ok": True},
    )

    assert entry.client_ip == "127.0.0.1"
    assert entry.path == "/v1/chat/completions"
    assert entry.response_body == {"ok": True}
    assert entry.request_headers == sent_headers
    assert entry.client_request_headers == {"authorization": "Bearer sk-secret-token"}
    assert entry.response_headers == {"content-type": "application/json", "transfer-encoding": "chunked"}
    assert entry.client_response_headers == {"content-type": "application/json"}


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
