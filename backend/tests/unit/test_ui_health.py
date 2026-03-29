import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.app import create_app


@pytest.mark.asyncio
async def test_ui_health_returns_ok_when_auth_is_disabled() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ui/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ui_health_requires_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UI_API_KEY", "ui-secret")
    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.get("/ui/v1/health")
        authorized = await client.get(
            "/ui/v1/health",
            headers={"Authorization": "Bearer ui-secret"},
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json() == {"detail": "Invalid UI API key"}
    assert authorized.status_code == 200
    assert authorized.json() == {"status": "ok"}
