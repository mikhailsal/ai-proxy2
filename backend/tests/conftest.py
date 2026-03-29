from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.app import create_app


@pytest.fixture
async def app():
    """Create a fresh FastAPI app for each test."""
    return create_app()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
