from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ai_proxy.db.repositories import chats as chat_repo


class QueryResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def make_request_record(**overrides):
    base = {
        "id": overrides.pop("id", uuid4()),
        "client_api_key_hash": overrides.pop("client_api_key_hash", "chat-client"),
        "model_requested": overrides.pop("model_requested", "gpt-4"),
        "model_resolved": overrides.pop("model_resolved", "gpt-4"),
        "request_body": overrides.pop(
            "request_body",
            {"messages": [{"role": "user", "content": "hello"}]},
        ),
        "response_body": overrides.pop("response_body", None),
        "created_at": overrides.pop("created_at", datetime.now(timezone.utc)),
        "system_prompt_text": overrides.pop("system_prompt_text", None),
        "first_user_message_text": overrides.pop("first_user_message_text", "hello"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_chat_repository_helper_branches() -> None:
    request_body = {
        "messages": [
            {"role": "user", "content": [{"text": "hello"}, {"type": "input_audio"}]},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {"name": "lookup_weather", "arguments": "{}"}}],
                "name": "planner",
            },
            {"role": "tool", "name": "lookup_weather", "tool_call_id": "call_1", "content": None},
        ]
    }
    record = make_request_record(
        client_api_key_hash=None,
        model_requested=None,
        model_resolved="resolved-model",
        request_body=request_body,
        response_body={"choices": [{"message": {"role": "assistant", "content": [{"text": "done"}]}}]},
        system_prompt_text=None,
        first_user_message_text=None,
    )

    assert chat_repo._request_messages(None) == []
    assert chat_repo._request_messages({"messages": [{"role": "user", "content": "ok"}, "skip"]}) == [
        {"role": "user", "content": "ok"}
    ]
    assert chat_repo._content_text([{"text": "hello"}, {"type": "input_audio"}]) == "hello\n[input_audio]"
    assert chat_repo._content_text({"alpha": 1}) == '{"alpha": 1}'
    assert chat_repo._message_tool_names(request_body["messages"][1]) == ["lookup_weather"]
    assert chat_repo._message_meta_tags(request_body["messages"][1]) == {"name": "planner"}
    assert chat_repo._message_display_text(request_body["messages"][1]) == "Tool call: lookup_weather"
    assert chat_repo._message_display_text(request_body["messages"][2]) == "Tool result: lookup_weather"
    assert chat_repo._message_display_text({"role": "assistant"}) == "(empty message)"
    assert chat_repo._first_message_by_role(request_body, "user") == request_body["messages"][0]
    assert chat_repo._first_message_by_role(request_body, "system") is None
    assert chat_repo._group_identity(record, "system_prompt_first_user") == (
        '{"first_user_message": "hello\\n[input_audio]", "system_prompt": ""}',
        "User: hello\n[input_audio]",
    )
    triple_key, triple_label = chat_repo._group_identity(record, "system_prompt_first_user_first_assistant")
    assert '"first_assistant_response": "Tool call: lookup_weather"' in triple_key
    assert '"first_user_message": "hello\\n[input_audio]"' in triple_key
    assert triple_label == "User: hello\n[input_audio]\nAssistant: Tool call: lookup_weather"
    assert chat_repo._assistant_response_message({}) is None
    assert chat_repo._assistant_response_message({"choices": ["bad"]}) is None
    assert chat_repo._assistant_response_message(record.response_body) == {
        "role": "assistant",
        "content": [{"text": "done"}],
    }


@pytest.mark.asyncio
async def test_get_conversation_messages_returns_empty_for_missing_group() -> None:
    class EmptyGroupSession:
        async def execute(self, _query):
            return QueryResult([])

    assert (
        await chat_repo.get_conversation_messages(
            EmptyGroupSession(),
            "missing",
            group_by="system_prompt_first_user",
        )
        == []
    )
