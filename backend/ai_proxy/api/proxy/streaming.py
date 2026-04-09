"""Streaming helpers for proxy responses."""

import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog
from fastapi import Request
from fastapi.responses import Response, StreamingResponse

from ai_proxy.adapters.openai_compat import parse_sse_chunk
from ai_proxy.api.proxy.response_utils import client_route_identifier, normalize_error_response_body
from ai_proxy.core.routing import RouteResult
from ai_proxy.logging.models import LogEntry
from ai_proxy.logging.service import enqueue_log
from ai_proxy.types import JsonObject

logger = structlog.get_logger()


@dataclass
class StreamState:
    chunks_collected: list[JsonObject] = field(default_factory=list)
    merged_choices: dict[int, JsonObject] = field(default_factory=dict)
    usage_data: JsonObject = field(default_factory=dict)
    extra_fields: JsonObject = field(default_factory=dict)
    response_headers: dict[str, str] = field(default_factory=dict)
    response_status_code: int = 200
    stream_error_message: str | None = None

    @property
    def full_content(self) -> str:
        msg = self.merged_choices.get(0, {})
        content = msg.get("content")
        return content if isinstance(content, str) else ""

    @property
    def full_reasoning(self) -> str:
        msg = self.merged_choices.get(0, {})
        return msg.get("reasoning_content") or msg.get("reasoning") or ""


async def stream_error_response(
    *,
    request: Request,
    request_id: uuid.UUID,
    key_hash: str,
    sent_request_headers: dict[str, str] | None,
    forward_body: JsonObject,
    route: RouteResult,
    model_requested: str,
    start_time: float,
    upstream_stream: Any,
    extract_error_message: Callable[[Any], str | None],
    inject_ai_proxy_route: Callable[[Any, RouteResult], Any],
    proxy_response_headers: Callable[[dict[str, str]], dict[str, str]],
    client_request_body: JsonObject | None = None,
) -> Response:
    latency = (time.monotonic() - start_time) * 1000
    response_body = upstream_stream.parsed_error_body()
    client_response_body = inject_ai_proxy_route(normalize_error_response_body(response_body), route)
    client_resp_headers = proxy_response_headers(upstream_stream.headers)
    await enqueue_log(
        LogEntry.from_proxy_context(
            entry_id=request_id,
            request=request,
            client_api_key_hash=key_hash,
            request_headers=sent_request_headers,
            request_body=forward_body,
            client_request_body=client_request_body,
            model_requested=model_requested,
            model_resolved=route.mapped_model,
            provider_name=route.provider_name,
            latency_ms=latency,
            response_status_code=upstream_stream.status_code,
            response_headers=upstream_stream.headers,
            client_response_headers=client_resp_headers,
            response_body=response_body,
            client_response_body=client_response_body,
            error_message=extract_error_message(response_body),
        )
    )
    if isinstance(client_response_body, dict) and "raw_text" not in client_response_body:
        return Response(
            content=json.dumps(client_response_body).encode("utf-8"),
            status_code=upstream_stream.status_code,
            headers=client_resp_headers,
        )
    return Response(
        content=upstream_stream.error_body,
        status_code=upstream_stream.status_code,
        headers=client_resp_headers,
    )


def build_streaming_response(
    *,
    request: Request,
    request_id: uuid.UUID,
    key_hash: str,
    sent_request_headers: dict[str, str] | None,
    forward_body: JsonObject,
    route: RouteResult,
    model_requested: str,
    start_time: float,
    upstream_stream: Any,
    proxy_response_headers: Callable[[dict[str, str]], dict[str, str]],
    client_request_body: JsonObject | None = None,
) -> StreamingResponse:
    state = StreamState(
        response_headers=upstream_stream.headers,
        response_status_code=upstream_stream.status_code,
    )

    streaming_headers = proxy_response_headers(state.response_headers)
    streaming_headers.setdefault("Cache-Control", "no-cache")
    streaming_headers.setdefault("X-Accel-Buffering", "no")

    async def stream_generator() -> AsyncGenerator[bytes, None]:
        async for chunk_bytes in relay_stream_chunks(
            upstream_stream,
            state,
            ai_proxy_route=client_route_identifier(route),
        ):
            yield chunk_bytes
        await enqueue_stream_log(
            request=request,
            request_id=request_id,
            key_hash=key_hash,
            sent_request_headers=sent_request_headers,
            forward_body=forward_body,
            route=route,
            model_requested=model_requested,
            start_time=start_time,
            state=state,
            client_request_body=client_request_body,
            client_response_headers=streaming_headers,
        )

    return StreamingResponse(
        stream_generator(),
        status_code=upstream_stream.status_code,
        media_type=upstream_stream.content_type or "text/event-stream",
        headers=streaming_headers,
    )


async def relay_stream_chunks(
    upstream_stream: Any,
    state: StreamState,
    *,
    ai_proxy_route: str | None = None,
) -> AsyncGenerator[bytes, None]:
    if upstream_stream.body is None:
        state.response_status_code = 502
        state.stream_error_message = "Provider stream was not established"
        logger.error("stream_error", error=state.stream_error_message)
        yield stream_error_event(state.stream_error_message, ai_proxy_route=ai_proxy_route)
        return

    try:
        async for chunk_bytes in upstream_stream.body:
            client_chunk = inject_ai_proxy_route_chunk(chunk_bytes, ai_proxy_route=ai_proxy_route)
            yield client_chunk
            capture_stream_chunk(state, client_chunk)
    except httpx.RequestError as error:
        status_code = 504 if isinstance(error, httpx.TimeoutException) else 502
        record_stream_exception(state, str(error), status_code)
        yield stream_error_event(state.stream_error_message or "Provider stream error", ai_proxy_route=ai_proxy_route)
    except Exception as error:
        record_stream_exception(state, str(error), 502)
        yield stream_error_event(state.stream_error_message or "Provider stream error", ai_proxy_route=ai_proxy_route)


def inject_ai_proxy_route_chunk(chunk_bytes: bytes, *, ai_proxy_route: str | None) -> bytes:
    if not ai_proxy_route:
        return chunk_bytes

    parsed = parse_sse_chunk(chunk_bytes)
    if not parsed:
        return chunk_bytes

    client_chunk = dict(parsed)
    client_chunk["ai_proxy_route"] = ai_proxy_route
    return f"data: {json.dumps(client_chunk)}\n\n".encode()


_STRING_MERGE_KEYS = frozenset({"content", "reasoning_content", "reasoning", "refusal"})


_SPECIAL_CHUNK_KEYS = frozenset({"choices", "usage"})


def capture_stream_chunk(state: StreamState, chunk_bytes: bytes) -> None:
    parsed = parse_sse_chunk(chunk_bytes)
    if not parsed:
        return

    state.chunks_collected.append(parsed)

    for key, value in parsed.items():
        if key not in _SPECIAL_CHUNK_KEYS and value is not None:
            state.extra_fields[key] = value

    for choice in parsed.get("choices", []):
        idx = choice.get("index", 0)
        delta = choice.get("delta", {})
        _merge_delta(state, idx, delta)
        finish = choice.get("finish_reason")
        if finish is not None:
            state.merged_choices.setdefault(idx, {})["finish_reason"] = finish

    usage = parsed.get("usage")
    if isinstance(usage, dict):
        state.usage_data = usage


def _merge_delta(state: StreamState, choice_idx: int, delta: JsonObject) -> None:
    merged = state.merged_choices.setdefault(choice_idx, {})
    for key, value in delta.items():
        if value is None:
            continue
        if key in _STRING_MERGE_KEYS and isinstance(value, str):
            merged[key] = merged.get(key, "") + value
        elif isinstance(value, list):
            _merge_list_field(merged, key, value)
        else:
            merged[key] = value


_LIST_ITEM_CONCAT_KEYS = frozenset({"arguments", "summary", "text"})


def _merge_list_field(merged: JsonObject, key: str, items: list[Any]) -> None:
    existing = merged.get(key)
    if not isinstance(existing, list):
        merged[key] = list(items)
        return
    for item in items:
        if not isinstance(item, dict):
            existing.append(item)
            continue
        idx = item.get("index")
        if idx is None:
            existing.append(item)
            continue
        target = None
        for entry in existing:
            if isinstance(entry, dict) and entry.get("index") == idx:
                target = entry
                break
        if target is None:
            existing.append(dict(item))
        else:
            _deep_merge_item(target, item)


def _deep_merge_item(target: dict[str, Any], source: dict[str, Any]) -> None:
    for k, v in source.items():
        if v is None:
            continue
        existing_v = target.get(k)
        if isinstance(v, dict) and isinstance(existing_v, dict):
            _deep_merge_item(existing_v, v)
        elif k in _LIST_ITEM_CONCAT_KEYS and isinstance(v, str) and isinstance(existing_v, str):
            target[k] = existing_v + v
        else:
            target[k] = v


def _extract_reasoning_tokens(usage_data: JsonObject) -> int | None:
    details = usage_data.get("completion_tokens_details")
    if isinstance(details, dict):
        tokens = details.get("reasoning_tokens")
        if isinstance(tokens, int) and tokens > 0:
            return tokens
    return None


def record_stream_exception(state: StreamState, error_message: str, status_code: int) -> None:
    state.response_status_code = status_code
    state.stream_error_message = error_message
    logger.error("stream_error", error=error_message)


def stream_error_event(message: str, *, ai_proxy_route: str | None = None) -> bytes:
    payload: JsonObject = {"error": {"message": message}}
    if ai_proxy_route:
        payload["ai_proxy_route"] = ai_proxy_route
    return f"data: {json.dumps(payload)}\n\n".encode()


async def enqueue_stream_log(
    *,
    request: Request,
    request_id: uuid.UUID,
    key_hash: str,
    sent_request_headers: dict[str, str] | None,
    forward_body: JsonObject,
    route: RouteResult,
    model_requested: str,
    start_time: float,
    state: StreamState,
    client_request_body: JsonObject | None = None,
    client_response_headers: dict[str, str] | None = None,
) -> None:
    latency = (time.monotonic() - start_time) * 1000
    cost_raw = state.usage_data.get("cost")
    cost = float(cost_raw) if isinstance(cost_raw, int | float) else None
    reasoning_tokens = _extract_reasoning_tokens(state.usage_data)
    entry = LogEntry.from_proxy_context(
        entry_id=request_id,
        request=request,
        client_api_key_hash=key_hash,
        request_headers=sent_request_headers,
        request_body=forward_body,
        client_request_body=client_request_body,
        model_requested=model_requested,
        model_resolved=route.mapped_model,
        provider_name=route.provider_name,
        latency_ms=latency,
        response_status_code=state.response_status_code,
        response_headers=state.response_headers,
        client_response_headers=client_response_headers,
        response_body=assembled_stream_response(state),
        stream_chunks=state.chunks_collected if state.chunks_collected else None,
        input_tokens=state.usage_data.get("prompt_tokens"),
        output_tokens=state.usage_data.get("completion_tokens"),
        total_tokens=state.usage_data.get("total_tokens"),
        error_message=state.stream_error_message,
    )
    entry.cost = cost
    entry.reasoning_tokens = reasoning_tokens
    await enqueue_log(entry)


def assembled_stream_response(state: StreamState) -> JsonObject | None:
    if not state.merged_choices and not state.chunks_collected:
        return None

    choices: list[JsonObject] = []
    for idx in sorted(state.merged_choices):
        merged = state.merged_choices[idx]
        message = {k: v for k, v in merged.items() if k != "finish_reason"}
        message.setdefault("role", "assistant")
        choice: JsonObject = {"index": idx, "message": message}
        if "finish_reason" in merged:
            choice["finish_reason"] = merged["finish_reason"]
        choices.append(choice)

    if not choices:
        choices.append({"index": 0, "message": {"role": "assistant", "content": ""}})

    result: JsonObject = dict(state.extra_fields)
    result["choices"] = choices
    result["usage"] = state.usage_data
    return result
