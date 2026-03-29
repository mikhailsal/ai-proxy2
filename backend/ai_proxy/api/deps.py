"""FastAPI dependencies."""

from collections.abc import AsyncGenerator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_proxy.db.engine import get_db_session
from ai_proxy.security.auth import validate_ui_api_key


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_db_session():
        yield session


async def require_ui_auth(authorization: str | None = Header(None)) -> None:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    if not validate_ui_api_key(token):
        raise HTTPException(status_code=401, detail="Invalid UI API key")
