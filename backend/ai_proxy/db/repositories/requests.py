"""Request repository — CRUD for ProxyRequest."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.db.models import Provider, ProxyRequest

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult


def encode_cursor(timestamp: datetime, request_id: uuid.UUID) -> str:
    return f"{timestamp.isoformat()}|{request_id}"


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw_timestamp, raw_request_id = cursor.split("|", 1)
    return datetime.fromisoformat(raw_timestamp), uuid.UUID(raw_request_id)


async def create_request(session: AsyncSession, **kwargs: Any) -> ProxyRequest:
    req = ProxyRequest(**kwargs)
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


async def get_request(session: AsyncSession, request_id: uuid.UUID) -> ProxyRequest | None:
    result = await session.execute(select(ProxyRequest).where(ProxyRequest.id == request_id))
    return result.scalar_one_or_none()


async def list_requests(
    session: AsyncSession,
    *,
    cursor: tuple[datetime, uuid.UUID] | None = None,
    limit: int = 50,
    model: str | None = None,
    client_hash: str | None = None,
    status_code: int | None = None,
    provider_name: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ProxyRequest]:
    query = select(ProxyRequest).order_by(desc(ProxyRequest.timestamp), desc(ProxyRequest.id))

    if cursor:
        cursor_timestamp, cursor_id = cursor
        query = query.where(
            or_(
                ProxyRequest.timestamp < cursor_timestamp,
                and_(ProxyRequest.timestamp == cursor_timestamp, ProxyRequest.id < cursor_id),
            )
        )
    if model:
        query = query.where(ProxyRequest.model_requested == model)
    if client_hash:
        query = query.where(ProxyRequest.client_api_key_hash == client_hash)
    if status_code:
        query = query.where(ProxyRequest.response_status_code == status_code)
    if provider_name:
        query = query.join(Provider, ProxyRequest.provider_id == Provider.id).where(Provider.name == provider_name)
    if since:
        query = query.where(ProxyRequest.timestamp >= since)
    if until:
        query = query.where(ProxyRequest.timestamp <= until)

    query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def search_requests(
    session: AsyncSession,
    query_text: str,
    limit: int = 50,
) -> list[ProxyRequest]:
    search_query = func.plainto_tsquery("english", query_text)
    rank = func.ts_rank_cd(ProxyRequest.search_vector, search_query)
    query = (
        select(ProxyRequest)
        .where(ProxyRequest.search_vector.op("@@")(search_query))
        .order_by(desc(rank), desc(ProxyRequest.timestamp), desc(ProxyRequest.id))
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_request_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(ProxyRequest.id)))
    return result.scalar_one()


async def get_stats(session: AsyncSession) -> dict[str, float | int]:
    result = await session.execute(
        select(
            func.count(ProxyRequest.id).label("total_requests"),
            func.avg(ProxyRequest.latency_ms).label("avg_latency"),
            func.sum(ProxyRequest.total_tokens).label("total_tokens"),
            func.sum(ProxyRequest.cost).label("total_cost"),
        )
    )
    row = result.one()
    return {
        "total_requests": row.total_requests or 0,
        "avg_latency_ms": round(float(row.avg_latency or 0), 2),
        "total_tokens": row.total_tokens or 0,
        "total_cost": round(float(row.total_cost or 0), 6),
    }


async def delete_old_requests(session: AsyncSession, before: datetime) -> int:
    from sqlalchemy import delete as sql_delete

    result = cast(
        "CursorResult[Any]",
        await session.execute(sql_delete(ProxyRequest).where(ProxyRequest.timestamp < before)),
    )
    await session.commit()
    return int(result.rowcount or 0)
