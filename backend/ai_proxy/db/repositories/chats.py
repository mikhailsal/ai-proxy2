"""Chat repository — conversation grouping."""

from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.db.models import ProxyRequest

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


async def get_conversations(
    session: AsyncSession,
    *,
    group_by: str = "system_prompt",
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Group requests into conversations based on system prompt or other fields."""
    system_prompt_expr: ColumnElement[str | None]

    # Group by system prompt extracted from JSONB
    if group_by == "system_prompt":
        # Extract system prompt from request_body -> messages[0]
        system_prompt_expr = func.jsonb_extract_path_text(
            ProxyRequest.request_body, "messages", "0", "content"
        )
    elif group_by == "client":
        system_prompt_expr = cast("ColumnElement[str | None]", ProxyRequest.client_api_key_hash)
    elif group_by == "model":
        system_prompt_expr = cast("ColumnElement[str | None]", ProxyRequest.model_requested)
    else:
        system_prompt_expr = func.jsonb_extract_path_text(
            ProxyRequest.request_body, "messages", "0", "content"
        )

    query = (
        select(
            system_prompt_expr.label("group_key"),
            func.count(ProxyRequest.id).label("message_count"),
            func.min(ProxyRequest.timestamp).label("first_message"),
            func.max(ProxyRequest.timestamp).label("last_message"),
            func.array_agg(func.distinct(ProxyRequest.model_requested)).label("models_used"),
        )
        .group_by(system_prompt_expr)
        .order_by(desc(func.max(ProxyRequest.timestamp)))
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(query)
    rows = result.all()

    conversations: list[dict[str, Any]] = []
    for row in rows:
        conversations.append({
            "group_key": row.group_key or "unknown",
            "message_count": row.message_count,
            "first_message": row.first_message.isoformat() if row.first_message else None,
            "last_message": row.last_message.isoformat() if row.last_message else None,
            "models_used": row.models_used or [],
        })

    return conversations


async def get_conversation_messages(
    session: AsyncSession,
    group_key: str,
    group_by: str = "system_prompt",
) -> list[ProxyRequest]:
    """Get all requests in a conversation."""
    if group_by == "system_prompt":
        filter_expr = func.jsonb_extract_path_text(
            ProxyRequest.request_body, "messages", "0", "content"
        ) == group_key
    elif group_by == "client":
        filter_expr = ProxyRequest.client_api_key_hash == group_key
    elif group_by == "model":
        filter_expr = ProxyRequest.model_requested == group_key
    else:
        filter_expr = func.jsonb_extract_path_text(
            ProxyRequest.request_body, "messages", "0", "content"
        ) == group_key

    query = (
        select(ProxyRequest)
        .where(filter_expr)
        .order_by(ProxyRequest.timestamp)
    )
    result = await session.execute(query)
    return list(result.scalars().all())
