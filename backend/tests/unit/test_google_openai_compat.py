from __future__ import annotations

import json
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

        async def post(self, url: str, content: bytes, headers: dict[str, str]) -> FakeResponse:
            request = {"url": url, "json": json.loads(content), "raw": content.decode("utf-8"), "headers": headers}
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
        "repetition_penalty": 1.15,
        "min_p": 0.05,
    }
    _install_fake_async_client(monkeypatch, calls)

    response = await _google_adapter().chat_completions(request_body, {})

    assert calls["requests"][0]["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert calls["requests"][0]["headers"] == {
        "Accept-Encoding": "identity",
        "Authorization": "Bearer provider-secret",
        "Content-Type": "application/json",
    }
    assert calls["requests"][0]["json"] == {
        "model": "gemma-4-31b-it",
        "messages": [{"role": "user", "content": "hi"}],
        "extra_body": {"google": {"thinking_config": {"thinking_level": "minimal"}}},
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": 1.2,
    }
    assert response.sent_request_body == calls["requests"][0]["json"]
    assert response.sent_request_body_raw == calls["requests"][0]["raw"]
    assert request_body["provider"]["order"] == ["ai-studio"]
    assert request_body["include"] == ["usage"]
    assert request_body["reasoning"] == {"effort": "none"}
    assert request_body["repetition_penalty"] == 1.15
    assert request_body["min_p"] == 0.05


@pytest.mark.asyncio
async def test_google_chat_completions_strip_unsupported_sampling_params(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    request_body = {
        "model": "gemini-2.5-flash-lite",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.8,
        "top_p": 0.9,
        "max_tokens": 100,
        "stop": ["bye"],
        "n": 1,
        "user": "tester",
        "response_format": {"type": "json_object"},
        "repetition_penalty": 1.2,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.3,
        "min_p": 0.1,
        "top_k": 40,
        "top_a": 0.5,
        "logit_bias": {123: 1.0},
        "logprobs": True,
        "top_logprobs": 3,
        "seed": 42,
    }
    _install_fake_async_client(monkeypatch, calls)

    response = await _google_adapter().chat_completions(request_body, {})

    sent_json = calls["requests"][0]["json"]
    assert sent_json == {
        "model": "gemini-2.5-flash-lite",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.8,
        "top_p": 0.9,
        "max_tokens": 100,
        "stop": ["bye"],
        "n": 1,
        "user": "tester",
        "response_format": {"type": "json_object"},
    }
    assert response.sent_request_body == sent_json
    assert request_body["repetition_penalty"] == 1.2
    assert request_body["frequency_penalty"] == 0.3
    assert request_body["min_p"] == 0.1
    assert request_body["top_k"] == 40
    assert request_body["top_a"] == 0.5
    assert request_body["logprobs"] is True
    assert request_body["top_logprobs"] == 3
    assert request_body["seed"] == 42


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
