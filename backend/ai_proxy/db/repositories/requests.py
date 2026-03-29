"""Request repository — CRUD for ProxyRequest."""

import uuid
from datetime import datetime

from sqlalchemy import Text, cast, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.db.models import ProxyRequest


async def create_request(session: AsyncSession, **kwargs) -> ProxyRequest:  # noqa: ANN003
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
    cursor: datetime | None = None,
    limit: int = 50,
    model: str | None = None,
    client_hash: str | None = None,
    status_code: int | None = None,
    provider_name: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[ProxyRequest]:
    query = select(ProxyRequest).order_by(desc(ProxyRequest.timestamp))

    if cursor:
        query = query.where(ProxyRequest.timestamp < cursor)
    if model:
        query = query.where(ProxyRequest.model_requested == model)
    if client_hash:
        query = query.where(ProxyRequest.client_api_key_hash == client_hash)
    if status_code:
        query = query.where(ProxyRequest.response_status_code == status_code)
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
    # Simple JSONB text search using cast to TEXT + ILIKE
    query = (
        select(ProxyRequest)
        .where(
            cast(ProxyRequest.request_body, Text).ilike(f"%{query_text}%")
            | cast(ProxyRequest.response_body, Text).ilike(f"%{query_text}%")
        )
        .order_by(desc(ProxyRequest.timestamp))
        .limit(limit)
    )
    result = await session.execute(query)
    return list(result.scalars().all())


async def get_request_count(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(ProxyRequest.id)))
    return result.scalar_one()


async def get_stats(session: AsyncSession) -> dict:
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
    result = await session.execute(
        sql_delete(ProxyRequest).where(ProxyRequest.timestamp < before)
    )
    await session.commit()
    return result.rowcount  # type: ignore[return-value]
