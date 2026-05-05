from __future__ import annotations

from typing import ClassVar

import pytest

from ai_proxy.adapters.openai_compat import OpenAICompatAdapter


def _google_adapter() -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        provider_name="google",
        endpoint_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="provider-secret",
    )


def _install_fake_async_client(monkeypatch: pytest.MonkeyPatch, calls: dict) -> None:
    class FakeResponse:
        status_code: ClassVar[int] = 200
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}
        content: ClassVar[bytes] = b'{"id":"resp"}'

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            calls["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, json: dict, headers: dict[str, str]) -> FakeResponse:
            request = {"url": url, "json": json, "headers": headers}
            calls.setdefault("requests", []).append(request)
            return FakeResponse()

    monkeypatch.setattr("ai_proxy.adapters.openai_compat.httpx.AsyncClient", FakeAsyncClient)


@pytest.mark.asyncio
async def test_google_chat_completions_strip_openrouter_only_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    request_body = {
        "model": "gemma-4-31b-it",
        "messages": [{"role": "user", "content": "hi"}],
        "include": ["usage"],
        "provider": {"order": ["ai-studio"], "allow_fallbacks": False},
        "reasoning": {"effort": "none"},
        "stream": True,
        "temperature": 1.2,
    }
    _install_fake_async_client(monkeypatch, calls)

    response = await _google_adapter().chat_completions(request_body, {})

    assert calls["requests"] == [
        {
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "headers": {
                "Accept-Encoding": "identity",
                "Authorization": "Bearer provider-secret",
                "Content-Type": "application/json",
            },
            "json": {
                "model": "gemma-4-31b-it",
                "messages": [{"role": "user", "content": "hi"}],
                "extra_body": {"google": {"thinking_config": {"thinking_level": "minimal"}}},
                "stream": True,
                "stream_options": {"include_usage": True},
                "temperature": 1.2,
            },
        }
    ]
    assert response.sent_request_body == calls["requests"][0]["json"]
    assert request_body["provider"]["order"] == ["ai-studio"]
    assert request_body["include"] == ["usage"]
    assert request_body["reasoning"] == {"effort": "none"}


@pytest.mark.asyncio
async def test_google_chat_completions_preserve_explicit_stream_usage_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    response = await _google_adapter().chat_completions(
        {
            "model": "gemma-4-31b-it",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
            "stream_options": {"include_usage": False},
        },
        {},
    )

    assert calls["requests"][0]["json"] == {
        "model": "gemma-4-31b-it",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
        "stream_options": {"include_usage": False},
    }
    assert response.sent_request_body == calls["requests"][0]["json"]


@pytest.mark.asyncio
async def test_google_chat_completions_translate_reasoning_and_thought_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    response = await _google_adapter().chat_completions(
        {
            "model": "gemini-2.5-flash-lite",
            "messages": [{"role": "user", "content": "hi"}],
            "include": ["reasoning.encrypted_content"],
            "reasoning": {"effort": "low"},
        },
        {},
    )

    assert calls["requests"][0]["json"] == {
        "model": "gemini-2.5-flash-lite",
        "messages": [{"role": "user", "content": "hi"}],
        "reasoning_effort": "low",
        "extra_body": {"google": {"thinking_config": {"include_thoughts": True}}},
    }
    assert response.sent_request_body == calls["requests"][0]["json"]


@pytest.mark.asyncio
async def test_google_gemma_chat_completions_translate_reasoning_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)
    adapter = _google_adapter()

    for payload in (
        {"model": "gemma-4-31b-it", "messages": [{"role": "user", "content": "hi"}], "reasoning": {"effort": "low"}},
        {"model": "gemma-4-31b-it", "messages": [{"role": "user", "content": "hi"}], "reasoning_effort": "none"},
    ):
        await adapter.chat_completions(payload, {})

    assert [request["json"] for request in calls["requests"]] == [
        {
            "model": "gemma-4-31b-it",
            "messages": [{"role": "user", "content": "hi"}],
            "extra_body": {"google": {"thinking_config": {"thinking_level": "high"}}},
        },
        {
            "model": "gemma-4-31b-it",
            "messages": [{"role": "user", "content": "hi"}],
            "extra_body": {"google": {"thinking_config": {"thinking_level": "minimal"}}},
        },
    ]


@pytest.mark.asyncio
async def test_google_gemma_chat_completions_preserve_explicit_thinking_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _google_adapter().chat_completions(
        {
            "model": "gemma-4-31b-it",
            "messages": [{"role": "user", "content": "hi"}],
            "reasoning": {"effort": "none"},
            "reasoning_effort": "high",
            "extra_body": {"google": {"thinking_config": {"thinking_level": "high", "include_thoughts": True}}},
        },
        {},
    )

    assert calls["requests"][0]["json"] == {
        "model": "gemma-4-31b-it",
        "messages": [{"role": "user", "content": "hi"}],
        "extra_body": {"google": {"thinking_config": {"thinking_level": "high", "include_thoughts": True}}},
    }
