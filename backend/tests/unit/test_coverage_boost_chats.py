"""Tests to boost coverage for chat repository and streaming modules."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from ai_proxy.db.repositories import chats as chat_repo


def _make_record(**overrides):
    payload = {
        "id": uuid.uuid4(),
        "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "client_ip": "127.0.0.1",
        "client_api_key_hash": "hash",
        "method": "POST",
        "path": "/v1/chat/completions",
        "model_requested": "gpt-4o-mini",
        "model_resolved": "mapped-model",
        "response_status_code": 200,
        "latency_ms": 100.0,
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "cost": None,
        "cache_status": None,
        "error_message": None,
        "request_headers": {},
        "client_request_headers": {},
        "request_body": None,
        "client_request_body": None,
        "response_body": None,
        "client_response_body": None,
        "stream_chunks": None,
        "reasoning_tokens": None,
        "metadata_": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_content_text_with_string_in_list():
    result = chat_repo._content_text(["hello", "world"])
    assert "hello" in result
    assert "world" in result


def test_content_text_with_non_text_dict_items():
    result = chat_repo._content_text([{"type": "image"}])
    assert "[image]" in result


def test_content_text_with_non_dict_non_string_items():
    result = chat_repo._content_text([42])
    assert "42" in result


def test_content_text_none():
    assert chat_repo._content_text(None) == ""


def test_content_text_arbitrary_value():
    result = chat_repo._content_text({"key": "value"})
    assert "key" in result


def test_message_tool_names_non_dict_tool_call():
    result = chat_repo._message_tool_names({"tool_calls": ["not-dict", {"name": "direct_name"}]})
    assert result == ["direct_name"]


def test_message_display_text_tool_role():
    result = chat_repo._message_display_text({"role": "tool", "name": "search_tool", "content": ""})
    assert "search_tool" in result


def test_message_display_text_empty():
    result = chat_repo._message_display_text({"role": "user"})
    assert result == "(empty message)"


def test_group_identity_client_mode():
    record = _make_record(client_api_key_hash="abc123")
    key, label = chat_repo._group_identity(record, "client")
    assert key == "abc123"


def test_group_identity_model_mode():
    record = _make_record(model_requested="gpt-4o")
    key, label = chat_repo._group_identity(record, "model")
    assert key == "gpt-4o"


def test_group_identity_system_prompt_first_user_with_system_only():
    record = _make_record(
        request_body={"messages": [{"role": "system", "content": "be helpful"}]},
    )
    key, label = chat_repo._group_identity(record, "system_prompt_first_user")
    assert "System:" in label
    assert "User:" not in label


def test_group_identity_system_prompt_first_user_with_user_only():
    record = _make_record(
        request_body={"messages": [{"role": "user", "content": "hello"}]},
    )
    key, label = chat_repo._group_identity(record, "system_prompt_first_user")
    assert "User:" in label
    assert "System:" not in label


def test_group_identity_system_prompt_first_user_empty():
    record = _make_record(request_body={"messages": []})
    key, label = chat_repo._group_identity(record, "system_prompt_first_user")
    assert label == "unknown"


def test_group_identity_default_fallback():
    record = _make_record(request_body={"messages": []})
    key, label = chat_repo._group_identity(record, "system_prompt")
    assert label == "unknown"


def test_assistant_response_message_non_dict_choice():
    assert chat_repo._assistant_response_message({"choices": ["not-dict"]}) is None


def test_assistant_response_message_non_dict_message_inside_choice():
    assert chat_repo._assistant_response_message({"choices": [{"message": "not-dict"}]}) is None


def test_build_conversation_messages_repeated_assistant():
    r1 = _make_record(
        id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        request_body={"messages": [{"role": "user", "content": "hi"}]},
        response_body={"choices": [{"message": {"role": "assistant", "content": "hello"}}]},
    )
    r2 = _make_record(
        id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
        request_body={
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
                {"role": "user", "content": "bye"},
            ]
        },
        response_body={"choices": [{"message": {"role": "assistant", "content": "goodbye"}}]},
    )
    messages = chat_repo.build_conversation_messages([r1, r2])
    contents = [m["content"] for m in messages]
    assert "goodbye" in contents
    assert "bye" in contents


@pytest.mark.asyncio
async def test_relay_stream_chunks_httpx_timeout():
    from ai_proxy.api.proxy.streaming import StreamState, relay_stream_chunks

    async def timeout_body():
        raise httpx.ReadTimeout("timed out")
        yield b""  # pragma: no cover

    state = StreamState()
    chunks = [chunk async for chunk in relay_stream_chunks(SimpleNamespace(body=timeout_body()), state)]
    assert state.response_status_code == 504
    assert "timed out" in (state.stream_error_message or "")
    assert len(chunks) == 1
