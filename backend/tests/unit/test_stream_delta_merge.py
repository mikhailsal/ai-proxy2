"""Tests for the generic delta merge in streaming capture.

Verifies that capture_stream_chunk + assembled_stream_response
preserve *all* fields from SSE stream deltas, not just content.
"""

from __future__ import annotations

import json

from ai_proxy.api.proxy import streaming


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _chunk(
    delta: dict,
    *,
    index: int = 0,
    finish: str | None = None,
) -> bytes:
    choice: dict = {"index": index, "delta": delta}
    if finish is not None:
        choice["finish_reason"] = finish
    return _sse({"choices": [choice]})


def _msg(state: streaming.StreamState, idx: int = 0) -> dict:
    resp = streaming.assembled_stream_response(state)
    assert resp is not None
    return resp["choices"][idx]["message"]


def test_all_fields_captured() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "role": "assistant",
                "content": "He",
                "reasoning": "Step ",
                "reasoning_content": "Think ",
            }
        ),
    )
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "content": "llo",
                "reasoning": "1",
                "reasoning_content": "hard",
            }
        ),
    )
    streaming.capture_stream_chunk(state, _chunk({"content": ""}, finish="stop"))
    usage = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "completion_tokens_details": {"reasoning_tokens": 3},
    }
    streaming.capture_stream_chunk(state, _sse({"usage": usage}))

    assert state.full_content == "Hello"
    assert state.full_reasoning == "Think hard"

    msg = _msg(state)
    assert msg["role"] == "assistant"
    assert msg["content"] == "Hello"
    assert msg["reasoning"] == "Step 1"
    assert msg["reasoning_content"] == "Think hard"

    resp = streaming.assembled_stream_response(state)
    assert resp["choices"][0]["finish_reason"] == "stop"
    assert resp["usage"]["prompt_tokens"] == 10
    assert streaming._extract_reasoning_tokens(state.usage_data) == 3


def test_tool_calls_merged_by_index() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"ci',
                        },
                    }
                ],
            }
        ),
    )
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "function": {"arguments": 'ty":"NYC"}'},
                    }
                ],
            }
        ),
    )
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "tool_calls": [
                    {
                        "index": 1,
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"q":"hi"}',
                        },
                    }
                ],
            }
        ),
    )
    streaming.capture_stream_chunk(state, _chunk({}, finish="tool_calls"))

    msg = _msg(state)
    tc = msg["tool_calls"]
    assert len(tc) == 2
    assert tc[0]["function"]["name"] == "get_weather"
    assert tc[0]["function"]["arguments"] == '{"city":"NYC"}'
    assert tc[1]["id"] == "call_2"


def test_reasoning_details_merged_by_index() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "role": "assistant",
                "content": "",
                "reasoning": "First",
                "reasoning_details": [
                    {
                        "type": "reasoning.summary",
                        "index": 0,
                        "summary": "First",
                    }
                ],
            }
        ),
    )
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "content": "",
                "reasoning": " step",
                "reasoning_details": [
                    {
                        "type": "reasoning.summary",
                        "index": 0,
                        "summary": " step",
                    }
                ],
            }
        ),
    )

    msg = _msg(state)
    assert msg["reasoning"] == "First step"
    details = msg["reasoning_details"]
    assert len(details) == 1
    assert details[0]["summary"] == "First step"
    assert details[0]["type"] == "reasoning.summary"


def test_refusal_concatenated() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _chunk({"role": "assistant", "refusal": "I cannot "}),
    )
    streaming.capture_stream_chunk(
        state,
        _chunk({"refusal": "help with that."}),
    )

    assert _msg(state)["refusal"] == "I cannot help with that."


def test_unknown_fields_preserved() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "role": "assistant",
                "content": "ok",
                "custom_score": 0.5,
                "annotations": [{"type": "cite", "text": "src"}],
            }
        ),
    )
    streaming.capture_stream_chunk(
        state,
        _chunk(
            {
                "custom_score": 0.9,
                "annotations": [{"type": "cite", "text": "more"}],
            }
        ),
    )

    msg = _msg(state)
    assert msg["content"] == "ok"
    assert msg["custom_score"] == 0.9
    assert len(msg["annotations"]) == 2


def test_multiple_choices_tracked() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _sse(
            {
                "choices": [
                    {"index": 0, "delta": {"role": "assistant", "content": "A"}},
                    {"index": 1, "delta": {"role": "assistant", "content": "B"}},
                ],
            }
        ),
    )
    streaming.capture_stream_chunk(
        state,
        _sse(
            {
                "choices": [
                    {"index": 0, "delta": {"content": "1"}},
                    {"index": 1, "delta": {"content": "2"}},
                ],
            }
        ),
    )

    resp = streaming.assembled_stream_response(state)
    assert len(resp["choices"]) == 2
    assert resp["choices"][0]["message"]["content"] == "A1"
    assert resp["choices"][1]["message"]["content"] == "B2"


def test_role_not_concatenated() -> None:
    state = streaming.StreamState()
    streaming.capture_stream_chunk(
        state,
        _chunk({"role": "assistant", "content": "Hi"}),
    )
    streaming.capture_stream_chunk(state, _chunk({"content": " there"}))

    msg = _msg(state)
    assert msg["role"] == "assistant"
    assert msg["content"] == "Hi there"
