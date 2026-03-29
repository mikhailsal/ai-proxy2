import pytest

from ai_proxy.app import create_app, lifespan


def test_create_app_returns_fastapi_instance() -> None:
    app = create_app()
    assert app.title == "AI Proxy v2"
    assert app.version == "2.0.0"


def test_create_app_has_health_route() -> None:
    app = create_app()
    route_paths = [route.path for route in app.routes]
    assert "/health" in route_paths


@pytest.mark.asyncio
async def test_lifespan_runs_without_error() -> None:
    app = create_app()
    async with lifespan(app):
        pass
