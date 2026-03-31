from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_proxy.db.models import ProxyRequest
from ai_proxy.db.repositories import requests as req_repo


class QueryResult:
    def __init__(
        self,
        *,
        rows=None,
        scalar_one_value=None,
        scalar_one_or_none_value=None,
        one_value=None,
        rowcount=0,
    ):
        self._rows = rows or []
        self._scalar_one_value = scalar_one_value
        self._scalar_one_or_none_value = scalar_one_or_none_value
        self._one_value = one_value
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar_one_value

    def scalar_one_or_none(self):
        return self._scalar_one_or_none_value

    def one(self):
        return self._one_value


class FakeSession:
    def __init__(self, *results: QueryResult):
        self.results = list(results)
        self.queries = []
        self.added = []
        self.refreshed = []
        self.commit_calls = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_calls += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)

    async def execute(self, query):
        self.queries.append(query)
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_create_request_and_get_request() -> None:
    existing = SimpleNamespace(id=uuid4())
    session = FakeSession(QueryResult(scalar_one_or_none_value=existing))

    created = await req_repo.create_request(
        session,
        path="/v1/chat/completions",
        method="POST",
        request_body={"messages": []},
    )
    found = await req_repo.get_request(session, existing.id)

    assert isinstance(created, ProxyRequest)
    assert created.path == "/v1/chat/completions"
    assert session.added == [created]
    assert session.commit_calls == 1
    assert session.refreshed == [created]
    assert found is existing
    assert "WHERE proxy_requests.id =" in str(session.queries[0])


@pytest.mark.asyncio
async def test_list_requests_and_search_requests_apply_filters() -> None:
    listed_record = SimpleNamespace(id=uuid4())
    searched_record = SimpleNamespace(id=uuid4())
    session = FakeSession(
        QueryResult(rows=[listed_record]),
        QueryResult(rows=[searched_record]),
    )
    cursor = datetime(2024, 1, 5, tzinfo=timezone.utc)
    since = datetime(2024, 1, 1, tzinfo=timezone.utc)
    until = datetime(2024, 1, 10, tzinfo=timezone.utc)

    listed = await req_repo.list_requests(
        session,
        cursor=cursor,
        limit=10,
        model="gpt-4o-mini",
        client_hash="client-hash",
        status_code=200,
        since=since,
        until=until,
    )
    searched = await req_repo.search_requests(session, "needle", limit=5)

    assert listed == [listed_record]
    assert searched == [searched_record]

    list_query = str(session.queries[0])
    search_query = str(session.queries[1])
    assert "proxy_requests.timestamp <" in list_query
    assert "proxy_requests.model_requested =" in list_query
    assert "proxy_requests.client_api_key_hash =" in list_query
    assert "proxy_requests.response_status_code =" in list_query
    assert "proxy_requests.timestamp >=" in list_query
    assert "proxy_requests.timestamp <=" in list_query
    assert "LIMIT" in list_query
    assert "like" in search_query.lower()
    assert "cast" in search_query.lower()


@pytest.mark.asyncio
async def test_get_request_count_get_stats_and_delete_old_requests() -> None:
    zero_stats = SimpleNamespace(total_requests=None, avg_latency=None, total_tokens=None, total_cost=None)
    populated_stats = SimpleNamespace(total_requests=3, avg_latency=12.3456, total_tokens=99, total_cost=0.1234567)
    session = FakeSession(
        QueryResult(scalar_one_value=7),
        QueryResult(one_value=zero_stats),
        QueryResult(one_value=populated_stats),
        QueryResult(rowcount=4),
    )
    before = datetime(2024, 1, 1, tzinfo=timezone.utc)

    total = await req_repo.get_request_count(session)
    empty_result = await req_repo.get_stats(session)
    populated_result = await req_repo.get_stats(session)
    deleted = await req_repo.delete_old_requests(session, before)

    assert total == 7
    assert empty_result == {
        "total_requests": 0,
        "avg_latency_ms": 0.0,
        "total_tokens": 0,
        "total_cost": 0.0,
    }
    assert populated_result == {
        "total_requests": 3,
        "avg_latency_ms": 12.35,
        "total_tokens": 99,
        "total_cost": 0.123457,
    }
    assert deleted == 4
    assert session.commit_calls == 1
    assert "count(proxy_requests.id)" in str(session.queries[0])
    assert "avg(proxy_requests.latency_ms)" in str(session.queries[1])
    assert "DELETE FROM proxy_requests" in str(session.queries[3])
