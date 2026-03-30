"""UI API — Chat/conversation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.api.deps import get_session, require_ui_auth
from ai_proxy.db.repositories import chats as chat_repo

router = APIRouter(dependencies=[Depends(require_ui_auth)])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/ui/v1/conversations")
async def list_conversations(
    session: SessionDep,
    group_by: str = Query("system_prompt"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    conversations = await chat_repo.get_conversations(session, group_by=group_by, limit=limit, offset=offset)
    return JSONResponse({"items": conversations})


@router.post("/ui/v1/conversations/messages")
async def get_conversation_messages(
    request: Request,
    session: SessionDep,
    group_by: str = Query("system_prompt"),
) -> JSONResponse:
    body = await request.json()
    group_key = body.get("group_key", "")
    if not group_key:
        return JSONResponse({"error": "group_key is required"}, status_code=400)
    messages = await chat_repo.get_conversation_messages(session, group_key, group_by)
    return JSONResponse({"items": messages})
