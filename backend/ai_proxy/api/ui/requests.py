"""UI API — Request browsing endpoints."""

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
        "cost": req.cost,
        "cache_status": req.cache_status,
        "error_message": req.error_message,
    }


def _serialize_request_full(req: ProxyRequest) -> dict[str, Any]:
    data = _serialize_request(req)
    data.update(
        {
            "request_headers": req.request_headers,
            "request_body": req.request_body,
            "response_headers": req.response_headers,
            "response_body": req.response_body,
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
    try:
        cursor_value = req_repo.decode_cursor(cursor) if cursor else None
    except ValueError:
        return JSONResponse({"error": "Invalid cursor"}, status_code=400)

    since_dt = datetime.fromisoformat(since) if since else None
    until_dt = datetime.fromisoformat(until) if until else None

    reqs = await req_repo.list_requests(
        session,
        cursor=cursor_value,
        limit=limit,
        model=model,
        client_hash=client_hash,
        status_code=status_code,
        since=since_dt,
        until=until_dt,
    )

    items = [_serialize_request(r) for r in reqs]
    next_cursor = req_repo.encode_cursor(reqs[-1].timestamp, reqs[-1].id) if reqs and reqs[-1].timestamp else None

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
