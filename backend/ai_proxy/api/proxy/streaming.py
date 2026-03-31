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
from ai_proxy.core.routing import RouteResult
from ai_proxy.logging.models import LogEntry
from ai_proxy.logging.service import enqueue_log
from ai_proxy.types import JsonObject

logger = structlog.get_logger()


@dataclass
class StreamState:
    chunks_collected: list[JsonObject] = field(default_factory=list)
    full_content: str = ""
    usage_data: JsonObject = field(default_factory=dict)
    response_headers: dict[str, str] = field(default_factory=dict)
    response_status_code: int = 200
    stream_error_message: str | None = None


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
    proxy_response_headers: Callable[[dict[str, str]], dict[str, str]],
    client_request_body: JsonObject | None = None,
) -> Response:
    latency = (time.monotonic() - start_time) * 1000
    response_body = upstream_stream.parsed_error_body()
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
            error_message=extract_error_message(response_body),
        )
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
        async for chunk_bytes in relay_stream_chunks(upstream_stream, state):
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
) -> AsyncGenerator[bytes, None]:
    if upstream_stream.body is None:
        state.response_status_code = 502
        state.stream_error_message = "Provider stream was not established"
        logger.error("stream_error", error=state.stream_error_message)
        yield stream_error_event(state.stream_error_message)
        return

    try:
        async for chunk_bytes in upstream_stream.body:
            yield chunk_bytes
            capture_stream_chunk(state, chunk_bytes)
    except httpx.RequestError as error:
        status_code = 504 if isinstance(error, httpx.TimeoutException) else 502
        record_stream_exception(state, str(error), status_code)
        yield stream_error_event(state.stream_error_message or "Provider stream error")
    except Exception as error:
        record_stream_exception(state, str(error), 502)
        yield stream_error_event(state.stream_error_message or "Provider stream error")


def capture_stream_chunk(state: StreamState, chunk_bytes: bytes) -> None:
    parsed = parse_sse_chunk(chunk_bytes)
    if not parsed:
        return

    state.chunks_collected.append(parsed)
    for choice in parsed.get("choices", []):
        delta = choice.get("delta", {})
        content = delta.get("content")
        if isinstance(content, str):
            state.full_content += content

    usage = parsed.get("usage")
    if isinstance(usage, dict):
        state.usage_data = usage


def record_stream_exception(state: StreamState, error_message: str, status_code: int) -> None:
    state.response_status_code = status_code
    state.stream_error_message = error_message
    logger.error("stream_error", error=error_message)


def stream_error_event(message: str) -> bytes:
    return f'data: {json.dumps({"error": {"message": message}})}\n\n'.encode()


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
    )


def assembled_stream_response(state: StreamState) -> JsonObject | None:
    if not state.full_content and not state.chunks_collected:
        return None

    return {
        "choices": [{"message": {"role": "assistant", "content": state.full_content}}],
        "usage": state.usage_data,
    }
