"""UI API — Request browsing endpoints."""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.api.deps import get_session, require_ui_auth
from ai_proxy.db.models import ProxyRequest
from ai_proxy.db.repositories import requests as req_repo

router = APIRouter(dependencies=[Depends(require_ui_auth)])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _serialize_request(req: ProxyRequest) -> dict[str, Any]:
    return {
        "id": str(req.id),
        "timestamp": req.timestamp.isoformat() if req.timestamp else None,
        "client_ip": req.client_ip,
        "client_api_key_hash": req.client_api_key_hash,
        "method": req.method,
        "path": req.path,
        "model_requested": req.model_requested,
        "model_resolved": req.model_resolved,
        "response_status_code": req.response_status_code,
        "latency_ms": req.latency_ms,
        "input_tokens": req.input_tokens,
        "output_tokens": req.output_tokens,
        "total_tokens": req.total_tokens,
        "cached_input_tokens": _extract_cached_tokens(req),
        "cost": req.cost if req.cost is not None else _extract_cost(req),
        "cache_status": req.cache_status,
        "error_message": req.error_message,
        "message_count": _extract_message_count(req),
        "last_user_message": _extract_last_user_message(req),
        "assistant_response": _extract_assistant_response(req),
    }


def _extract_cached_tokens(req: ProxyRequest) -> int | None:
    body = req.response_body or req.client_response_body
    if not isinstance(body, dict):
        return None
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = details.get("cached_tokens")
        if isinstance(cached, int):
            return cached
    return None


def _extract_cost(req: ProxyRequest) -> float | None:
    body = req.response_body or req.client_response_body
    if not isinstance(body, dict):
        return None
    usage = body.get("usage")
    if isinstance(usage, dict):
        cost = usage.get("cost")
        if isinstance(cost, int | float):
            return float(cost)
    cost = body.get("cost")
    if isinstance(cost, int | float):
        return float(cost)
    return None


def _extract_message_count(req: ProxyRequest) -> int | None:
    body = req.request_body or req.client_request_body
    if not isinstance(body, dict):
        return None
    messages = body.get("messages")
    if not isinstance(messages, list):
        return None
    return len(messages)


def _extract_last_user_message(req: ProxyRequest) -> str | None:
    body = req.request_body or req.client_request_body
    if not isinstance(body, dict):
        return None
    messages = body.get("messages")
    if not isinstance(messages, list):
        return None
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        if role == "assistant":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content[:200]
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str):
                        return text[:200]
    return None


def _extract_assistant_response(req: ProxyRequest) -> str | None:
    body = req.response_body or req.client_response_body
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    message = choice.get("message") or choice.get("delta")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str) and content:
        return content[:500]
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        parts = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                parts.append("tool_call")
                continue
            name = fn.get("name", "tool_call")
            args_summary = _summarize_tool_args(fn.get("arguments"))
            parts.append(f"{name}({args_summary})" if args_summary else name)
        return " | ".join(parts) if parts else None
    return None


def _summarize_tool_args(raw_args: object) -> str:
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except (json.JSONDecodeError, ValueError):
            return ""
        if not isinstance(parsed, dict):
            return ""
        raw_args = parsed
    if not isinstance(raw_args, dict) or not raw_args:
        return ""
    pairs: list[str] = []
    for key, value in raw_args.items():
        pairs.append(f"{key}={_compact_value(value)}")
    return ", ".join(pairs)


def _compact_value(value: object) -> str:
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return f"[{len(value)} items]"
    if isinstance(value, dict):
        return f"{{{len(value)} keys}}"
    if value is None:
        return "null"
    return str(value)


def _serialize_request_full(req: ProxyRequest) -> dict[str, Any]:
    data = _serialize_request(req)
    data.update(
        {
            "request_headers": req.request_headers,
            "client_request_headers": req.client_request_headers,
            "request_body": req.request_body,
            "client_request_body": req.client_request_body,
            "response_headers": req.response_headers,
            "client_response_headers": req.client_response_headers,
            "response_body": req.response_body,
            "client_response_body": req.client_response_body,
            "stream_chunks": req.stream_chunks,
            "reasoning_tokens": req.reasoning_tokens,
            "metadata": req.metadata_,
        }
    )
    return data


@router.get("/ui/v1/requests")
async def list_requests(
    session: SessionDep,
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    model: str | None = Query(None),
    client_hash: str | None = Query(None),
    status_code: int | None = Query(None),
    since: str | None = Query(None),
    until: str | None = Query(None),
) -> JSONResponse:
    cursor_dt = datetime.fromisoformat(cursor) if cursor else None
    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None

    reqs = await req_repo.list_requests(
        session,
        cursor=cursor_dt,
        limit=limit,
        model=model,
        client_hash=client_hash,
        status_code=status_code,
        since=since_dt,
        until=until_dt,
    )

    items = [_serialize_request(r) for r in reqs]
    next_cursor = items[-1]["timestamp"] if items else None

    return JSONResponse({"items": items, "next_cursor": next_cursor})


@router.get("/ui/v1/requests/{request_id}")
async def get_request(
    request_id: str,
    session: SessionDep,
) -> JSONResponse:
    req = await req_repo.get_request(session, uuid.UUID(request_id))
    if not req:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse(_serialize_request_full(req))


@router.get("/ui/v1/search")
async def search(
    session: SessionDep,
    q: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    reqs = await req_repo.search_requests(session, q, limit)
    items = [_serialize_request(r) for r in reqs]
    return JSONResponse({"items": items})


@router.get("/ui/v1/stats")
async def get_stats(
    session: SessionDep,
) -> JSONResponse:
    stats = await req_repo.get_stats(session)
    return JSONResponse(stats)
