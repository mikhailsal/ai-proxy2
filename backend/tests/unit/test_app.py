import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.app import create_app, lifespan


def test_create_app_returns_fastapi_instance() -> None:
    app = create_app()
    assert app.title == "AI Proxy v2"
    assert app.version == "2.0.0"


@pytest.mark.asyncio
async def test_create_app_has_health_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_API_KEY", "test-ui-key")
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        response = await client.get("/ui/v1/health", headers={"Authorization": "Bearer test-ui-key"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_lifespan_runs_without_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ai_proxy.app.init_engine", lambda _url: None)
    monkeypatch.setattr("ai_proxy.app.dispose_engine", _fake_async_noop)

    app = create_app()
    async with lifespan(app):
        pass


async def _fake_async_noop() -> None:
    pass
