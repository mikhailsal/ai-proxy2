from __future__ import annotations

import json
from typing import ClassVar

import pytest

from ai_proxy.adapters.openai_compat import OpenAICompatAdapter


def _fireworks_adapter() -> OpenAICompatAdapter:
    return OpenAICompatAdapter(
        provider_name="fireworks",
        endpoint_url="https://api.fireworks.ai/inference/v1",
        api_key="fw_test_key",
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
async def test_fireworks_strips_openrouter_only_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    request_body = {
        "model": "deepseek-v3p1",
        "messages": [{"role": "user", "content": "hi"}],
        "include": ["usage"],
        "provider": {"order": ["fireworks"], "allow_fallbacks": False},
        "temperature": 0.7,
    }

    response = await _fireworks_adapter().chat_completions(request_body, {})

    assert calls["requests"][0]["url"] == "https://api.fireworks.ai/inference/v1/chat/completions"
    assert calls["requests"][0]["headers"] == {
        "Accept-Encoding": "identity",
        "Authorization": "Bearer fw_test_key",
        "Content-Type": "application/json",
    }
    assert calls["requests"][0]["json"] == {
        "model": "accounts/fireworks/models/deepseek-v3p1",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.7,
    }
    assert response.sent_request_body == calls["requests"][0]["json"]
    assert response.sent_request_body_raw == calls["requests"][0]["raw"]
    assert request_body["provider"]["order"] == ["fireworks"]
    assert request_body["include"] == ["usage"]


@pytest.mark.asyncio
async def test_fireworks_prefixes_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "qwen3-235b-a22b",
            "messages": [{"role": "user", "content": "hi"}],
        },
        {},
    )

    assert calls["requests"][0]["json"]["model"] == "accounts/fireworks/models/qwen3-235b-a22b"


@pytest.mark.asyncio
async def test_fireworks_preserves_already_prefixed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "accounts/fireworks/models/deepseek-r1",
            "messages": [{"role": "user", "content": "hi"}],
        },
        {},
    )

    assert calls["requests"][0]["json"]["model"] == "accounts/fireworks/models/deepseek-r1"


@pytest.mark.asyncio
async def test_fireworks_strips_unsupported_params(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    request_body = {
        "model": "deepseek-v3p1",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.8,
        "top_p": 0.9,
        "top_k": 50,
        "min_p": 0.05,
        "max_tokens": 100,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.3,
        "repetition_penalty": 1.1,
        "seed": 42,
        "logprobs": 5,
        "top_logprobs": 3,
        "stop": ["bye"],
        "top_a": 0.5,
    }

    response = await _fireworks_adapter().chat_completions(request_body, {})

    sent_json = calls["requests"][0]["json"]
    assert sent_json == {
        "model": "accounts/fireworks/models/deepseek-v3p1",
        "messages": [{"role": "user", "content": "hi"}],
        "temperature": 0.8,
        "top_p": 0.9,
        "top_k": 50,
        "min_p": 0.05,
        "max_tokens": 100,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.3,
        "repetition_penalty": 1.1,
        "seed": 42,
        "logprobs": 5,
        "top_logprobs": 3,
        "stop": ["bye"],
    }
    assert response.sent_request_body == sent_json
    assert request_body["top_a"] == 0.5


@pytest.mark.asyncio
async def test_fireworks_translates_reasoning_object(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "deepseek-r1",
            "messages": [{"role": "user", "content": "think step by step"}],
            "reasoning": {"effort": "high"},
        },
        {},
    )

    assert calls["requests"][0]["json"] == {
        "model": "accounts/fireworks/models/deepseek-r1",
        "messages": [{"role": "user", "content": "think step by step"}],
        "reasoning_effort": "high",
    }


@pytest.mark.asyncio
async def test_fireworks_preserves_explicit_reasoning_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "deepseek-r1",
            "messages": [{"role": "user", "content": "hi"}],
            "reasoning": {"effort": "low"},
            "reasoning_effort": "high",
        },
        {},
    )

    sent = calls["requests"][0]["json"]
    assert sent["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_fireworks_preserves_thinking_config(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "deepseek-r1",
            "messages": [{"role": "user", "content": "hi"}],
            "thinking": {"type": "enabled", "budget_tokens": 4096},
        },
        {},
    )

    assert calls["requests"][0]["json"] == {
        "model": "accounts/fireworks/models/deepseek-r1",
        "messages": [{"role": "user", "content": "hi"}],
        "thinking": {"type": "enabled", "budget_tokens": 4096},
    }


@pytest.mark.asyncio
async def test_fireworks_preserves_stream_and_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "qwen3-32b",
            "messages": [{"role": "user", "content": "what's the weather?"}],
            "stream": True,
            "tools": [
                {
                    "type": "function",
                    "function": {"name": "get_weather", "description": "Get the weather", "parameters": {}},
                }
            ],
            "tool_choice": "auto",
        },
        {},
    )

    sent = calls["requests"][0]["json"]
    assert sent["stream"] is True
    assert sent["tools"] == [
        {
            "type": "function",
            "function": {"name": "get_weather", "description": "Get the weather", "parameters": {}},
        }
    ]
    assert sent["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_fireworks_does_not_mutate_original_body(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    request_body = {
        "model": "deepseek-v3p1",
        "messages": [{"role": "user", "content": "hi"}],
        "provider": {"order": ["fireworks"]},
        "include": ["usage"],
        "top_a": 0.5,
        "reasoning": {"effort": "medium"},
    }

    await _fireworks_adapter().chat_completions(request_body, {})

    assert request_body["model"] == "deepseek-v3p1"
    assert request_body["provider"] == {"order": ["fireworks"]}
    assert request_body["include"] == ["usage"]
    assert request_body["top_a"] == 0.5
    assert request_body["reasoning"] == {"effort": "medium"}


@pytest.mark.asyncio
async def test_fireworks_response_format_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}
    _install_fake_async_client(monkeypatch, calls)

    await _fireworks_adapter().chat_completions(
        {
            "model": "qwen3-8b",
            "messages": [{"role": "user", "content": "respond in JSON"}],
            "response_format": {"type": "json_object"},
        },
        {},
    )

    sent = calls["requests"][0]["json"]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["model"] == "accounts/fireworks/models/qwen3-8b"
