from collections.abc import AsyncGenerator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.app import create_app
from ai_proxy.config.loader import reset_config
from ai_proxy.config.settings import reset_settings


@pytest.fixture(autouse=True)
def reset_cached_state() -> Iterator[None]:
    reset_settings()
    reset_config()
    yield
    reset_settings()
    reset_config()


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
