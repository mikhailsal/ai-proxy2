from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.app import create_app
from tests.unit.test_provider_aware_routing import FakeAdapter, _setup_integration_test


@pytest.mark.asyncio
async def test_body_provider_only_selects_direct_google_route(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    google_adapter = FakeAdapter()
    openrouter_adapter = FakeAdapter()
    mappings = {
        "google/gemma-4-26b-a4b-it:free": "openrouter:google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-26b-a4b-it:free+ai-studio": "google:gemma-4-26b-a4b-it",
    }
    registry = {"google": google_adapter, "openrouter": openrouter_adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "google/gemma-4-26b-a4b-it:free",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"only": ["ai-studio"], "allow_fallbacks": False},
            },
        )

    assert resp.status_code == 200
    assert google_adapter.last_request_body is not None
    assert openrouter_adapter.last_request_body is None


@pytest.mark.asyncio
async def test_provider_only_slug_renamed_in_forwarded_body(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    transport = ASGITransport(app=app)

    adapter = FakeAdapter()
    mappings = {
        "google/gemma-4-26b-a4b-it+Google": "openrouter:google/gemma-4-26b-a4b-it+google-ai-studio",
    }
    registry = {"openrouter": adapter}
    _setup_integration_test(monkeypatch, mappings, registry)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer key"},
            json={
                "model": "google/gemma-4-26b-a4b-it",
                "messages": [{"role": "user", "content": "hi"}],
                "provider": {"only": ["Google"]},
            },
        )

    assert resp.status_code == 200
    assert adapter.last_request_body is not None
    assert adapter.last_request_body["provider"]["only"] == ["google-ai-studio"]
    assert "order" not in adapter.last_request_body["provider"]
