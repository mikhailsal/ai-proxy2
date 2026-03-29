"""UI API — Chat/conversation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.api.deps import get_session, require_ui_auth
from ai_proxy.api.ui.requests import _serialize_request_full
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
    conversations = await chat_repo.get_conversations(
        session, group_by=group_by, limit=limit, offset=offset
    )
    return JSONResponse({"items": conversations})


@router.get("/ui/v1/conversations/{group_key}/messages")
async def get_conversation_messages(
    group_key: str,
    session: SessionDep,
    group_by: str = Query("system_prompt"),
) -> JSONResponse:
    messages = await chat_repo.get_conversation_messages(session, group_key, group_by)
    items = [_serialize_request_full(m) for m in messages]
    return JSONResponse({"items": items})
