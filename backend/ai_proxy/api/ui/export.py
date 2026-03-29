"""UI API — Export endpoints."""

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.api.deps import get_session, require_ui_auth
from ai_proxy.api.ui.requests import _serialize_request_full
from ai_proxy.db.repositories import requests as req_repo

router = APIRouter(dependencies=[Depends(require_ui_auth)])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/ui/v1/export/requests/{request_id}")
async def export_request(
    request_id: str,
    session: SessionDep,
    format: str = Query("json"),  # noqa: A002
) -> Response:
    req = await req_repo.get_request(session, uuid.UUID(request_id))
    if not req:
        return JSONResponse({"error": "Not found"}, status_code=404)

    data = _serialize_request_full(req)

    if format == "markdown":
        md = _to_markdown(data)
        return Response(content=md, media_type="text/markdown")

    return JSONResponse(data)


def _to_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# Request {data['id']}",
        f"**Timestamp**: {data['timestamp']}",
        f"**Model**: {data['model_requested']} → {data['model_resolved']}",
        f"**Status**: {data['response_status_code']}",
        f"**Latency**: {data['latency_ms']}ms",
        "",
        "## Request Body",
        f"```json\n{json.dumps(data.get('request_body'), indent=2)}\n```",
        "",
        "## Response Body",
        f"```json\n{json.dumps(data.get('response_body'), indent=2)}\n```",
    ]
    return "\n".join(lines)
