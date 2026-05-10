from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ai_proxy.api.ui import export, requests
from ai_proxy.logging.masking import mask_sensitive_fields

_SECRET_TOKEN = "secret" + "-token"
_REQUEST_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_REQUEST_BODY_RAW = (
    '{"marker":"ORDER_PROBE_20260510_A","token":"secret-token","stream":false,'
    '"tools":[{"type":"function","function":{"name":"tool_second","parameters":'
    '{"type":"object","properties":{"zeta_nested":{"type":"string"},"alpha_nested":{"type":"string"}},'
    '"required":["zeta_required","alpha_required"]}}},'
    '{"type":"function","function":{"name":"tool_first","parameters":'
    '{"type":"object","properties":{"gamma_nested":{"type":"string"},"beta_nested":{"type":"string"}},'
    '"required":["gamma_required","beta_required"]}}}],'
    '"messages":[{"role":"user","content":"ORDER_PROBE_20260510_A"}],"model":"mapped-model"}'
)
_CLIENT_REQUEST_BODY_RAW = (
    '{"messages":[{"role":"user","content":"ORDER_PROBE_20260510_A"}],'
    '"marker":"ORDER_PROBE_20260510_A","model":"gpt-4o-mini",'
    '"tools":[{"type":"function","function":{"name":"tool_second","parameters":'
    '{"type":"object","properties":{"zeta_nested":{"type":"string"},"alpha_nested":{"type":"string"}},'
    '"required":["zeta_required","alpha_required"]}}},'
    '{"type":"function","function":{"name":"tool_first","parameters":'
    '{"type":"object","properties":{"gamma_nested":{"type":"string"},"beta_nested":{"type":"string"}},'
    '"required":["gamma_required","beta_required"]}}}],"stream":false}'
)


def _make_record() -> SimpleNamespace:
    return SimpleNamespace(
        id=_REQUEST_ID,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        client_ip="127.0.0.1",
        client_api_key_hash="hash",
        method="POST",
        path="/v1/chat/completions",
        model_requested="gpt-4o-mini",
        model_resolved="mapped-model",
        response_status_code=200,
        latency_ms=123.4,
        ttft_ms=50.2,
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        cost=0.01,
        cache_status="miss",
        error_message=None,
        request_headers={"Authorization": "Bearer secret-token"},
        client_request_headers={"Authorization": "Bearer secret-token", "content-type": "application/json"},
        request_body={
            "model": "mapped-model",
            "messages": [{"role": "user", "content": "ORDER_PROBE_20260510_A"}],
            "tools": [
                {"type": "function", "function": {"name": "tool_first", "parameters": {}}},
                {"type": "function", "function": {"name": "tool_second", "parameters": {}}},
            ],
            "stream": False,
            "marker": "ORDER_PROBE_20260510_A",
            "token": "sec******ken",
        },
        request_body_raw=_REQUEST_BODY_RAW,
        client_request_body={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "ORDER_PROBE_20260510_A"}],
            "tools": [
                {"type": "function", "function": {"name": "tool_first", "parameters": {}}},
                {"type": "function", "function": {"name": "tool_second", "parameters": {}}},
            ],
            "stream": False,
            "marker": "ORDER_PROBE_20260510_A",
        },
        client_request_body_raw=_CLIENT_REQUEST_BODY_RAW,
        response_headers={"x-upstream": "1"},
        client_response_headers={"x-upstream": "1"},
        response_body={"choices": [{"message": {"content": "world"}}]},
        client_response_body=None,
        stream_chunks=[{"choices": [{"delta": {"content": "world"}}]}],
        reasoning_tokens=0,
        metadata_={"trace": "abc"},
        system_prompt_text="hello",
        first_user_message_text=None,
    )


@pytest.mark.asyncio
async def test_request_detail_and_export_prefer_ordered_raw_request_bodies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _make_record()

    async def get_req_stub(_session: object, request_id: uuid.UUID) -> SimpleNamespace | None:
        return record if request_id == record.id else None

    monkeypatch.setattr(requests.req_repo, "get_request", get_req_stub)
    monkeypatch.setattr(export.req_repo, "get_request", get_req_stub)

    detail_response = await requests.get_request(str(record.id), session=object())
    json_export = await export.export_request(str(record.id), format="json", session=object())
    markdown_export = await export.export_request(str(record.id), format="markdown", session=object())

    detail = json.loads(detail_response.body)
    exported = json.loads(json_export.body)
    markdown = markdown_export.body.decode("utf-8")
    masked_token = mask_sensitive_fields({"token": _SECRET_TOKEN})["token"]

    assert list(detail["request_body"].keys()) == ["marker", "token", "stream", "tools", "messages", "model"]
    assert list(detail["client_request_body"].keys()) == ["messages", "marker", "model", "tools", "stream"]
    assert detail["request_body"]["token"] == masked_token
    assert [tool["function"]["name"] for tool in detail["request_body"]["tools"]] == ["tool_second", "tool_first"]
    assert list(detail["request_body"]["tools"][0]["function"]["parameters"]["properties"].keys()) == [
        "zeta_nested",
        "alpha_nested",
    ]
    assert detail["request_body"]["tools"][0]["function"]["parameters"]["required"] == [
        "zeta_required",
        "alpha_required",
    ]
    assert list(exported["request_body"].keys()) == ["marker", "token", "stream", "tools", "messages", "model"]
    assert markdown.index('"marker"') < markdown.index('"token"') < markdown.index('"stream"')
    assert markdown.index('"stream"') < markdown.index('"tools"') < markdown.index('"messages"')
    assert markdown.index('"messages"') < markdown.index('"model"')
