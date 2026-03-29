"""Proxy API router — /v1/chat/completions, /v1/models."""

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ai_proxy.adapters.openai_compat import parse_sse_chunk
from ai_proxy.config.loader import get_app_config
from ai_proxy.core.access import check_model_access
from ai_proxy.core.modification import apply_modifications
from ai_proxy.core.routing import RouteResult, resolve_model
from ai_proxy.logging.models import LogEntry
from ai_proxy.logging.service import enqueue_log
from ai_proxy.security.auth import validate_proxy_api_key
from ai_proxy.types import JsonObject

logger = structlog.get_logger()

router = APIRouter()
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _proxy_response_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def _transport_error_status(error: httpx.RequestError) -> int:
    if isinstance(error, httpx.TimeoutException):
        return 504
    return 502


def _extract_usage(response_body: Any) -> tuple[int | None, int | None, int | None]:
    if not isinstance(response_body, dict):
        return None, None, None

    usage = response_body.get("usage")
    if not isinstance(usage, dict):
        return None, None, None

    return (
        usage.get("prompt_tokens"),
        usage.get("completion_tokens"),
        usage.get("total_tokens"),
    )


def _extract_error_message(response_body: Any, fallback: str | None = None) -> str | None:
    if isinstance(response_body, dict):
        error = response_body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message

        message = response_body.get("message")
        if isinstance(message, str):
            return message

        raw_text = response_body.get("raw_text")
        if isinstance(raw_text, str):
            return raw_text

    return fallback


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    start_time = time.monotonic()
    request_id = uuid.uuid4()

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": {"message": "Invalid JSON body"}}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": {"message": "JSON body must be an object"}}, status_code=400)

    # Auth
    api_key = _extract_api_key(request)
    is_valid, key_hash = validate_proxy_api_key(api_key)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

    # Get model
    model_requested = body.get("model", "")
    if not model_requested:
        return JSONResponse({"error": {"message": "model field is required"}}, status_code=400)

    # Access control
    allowed, reason = check_model_access(key_hash, model_requested)
    if not allowed:
        return JSONResponse({"error": {"message": reason}}, status_code=403)

    # Route
    try:
        route = resolve_model(model_requested)
    except ValueError as e:
        return JSONResponse({"error": {"message": str(e)}}, status_code=404)

    # Modify request
    forward_body: JsonObject = {**body, "model": route.mapped_model}
    forward_headers = dict(request.headers)
    forward_body, forward_headers = apply_modifications(
        forward_body, forward_headers, route.provider_name, route.mapped_model
    )

    is_streaming = bool(body.get("stream", False))

    if is_streaming:
        return await _handle_streaming(
            request, request_id, forward_body, forward_headers, route,
            model_requested, key_hash, start_time,
        )
    else:
        return await _handle_non_streaming(
            request, request_id, forward_body, forward_headers, route,
            model_requested, key_hash, start_time,
        )


async def _handle_non_streaming(
    request: Request,
    request_id: uuid.UUID,
    forward_body: JsonObject,
    forward_headers: dict[str, str],
    route: RouteResult,
    model_requested: str,
    key_hash: str,
    start_time: float,
) -> Response:
    try:
        upstream_response = await route.adapter.chat_completions(forward_body, forward_headers)
    except httpx.RequestError as e:
        latency = (time.monotonic() - start_time) * 1000
        logger.error("proxy_error", error=str(e), provider=route.provider_name)
        response_status_code = _transport_error_status(e)
        await enqueue_log(
            LogEntry.from_proxy_context(
                entry_id=request_id,
                request=request,
                client_api_key_hash=key_hash,
                request_body=forward_body,
                model_requested=model_requested,
                model_resolved=route.mapped_model,
                provider_name=route.provider_name,
                latency_ms=latency,
                response_status_code=response_status_code,
                error_message=str(e),
            )
        )
        return JSONResponse({"error": {"message": f"Provider transport error: {e}"}}, status_code=response_status_code)

    latency = (time.monotonic() - start_time) * 1000
    response_body = upstream_response.parsed_body()
    input_tokens, output_tokens, total_tokens = _extract_usage(response_body)

    await enqueue_log(
        LogEntry.from_proxy_context(
            entry_id=request_id,
            request=request,
            client_api_key_hash=key_hash,
            request_body=forward_body,
            model_requested=model_requested,
            model_resolved=route.mapped_model,
            provider_name=route.provider_name,
            latency_ms=latency,
            response_status_code=upstream_response.status_code,
            response_headers=upstream_response.headers,
            response_body=response_body,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_message=_extract_error_message(response_body),
        )
    )

    return Response(
        content=upstream_response.body,
        status_code=upstream_response.status_code,
        headers=_proxy_response_headers(upstream_response.headers),
    )


async def _handle_streaming(
    request: Request,
    request_id: uuid.UUID,
    forward_body: JsonObject,
    forward_headers: dict[str, str],
    route: RouteResult,
    model_requested: str,
    key_hash: str,
    start_time: float,
) -> Response | StreamingResponse:
    chunks_collected: list[JsonObject] = []
    full_content = ""
    usage_data: JsonObject = {}
    response_headers: dict[str, str] = {}
    response_status_code = 200
    stream_error_message: str | None = None

    try:
        upstream_stream = await route.adapter.stream_chat_completions(forward_body, forward_headers)
    except httpx.RequestError as e:
        latency = (time.monotonic() - start_time) * 1000
        response_status_code = _transport_error_status(e)
        stream_error_message = str(e)
        logger.error("stream_transport_error", error=stream_error_message, provider=route.provider_name)
        await enqueue_log(
            LogEntry.from_proxy_context(
                entry_id=request_id,
                request=request,
                client_api_key_hash=key_hash,
                request_body=forward_body,
                model_requested=model_requested,
                model_resolved=route.mapped_model,
                provider_name=route.provider_name,
                latency_ms=latency,
                response_status_code=response_status_code,
                error_message=stream_error_message,
            )
        )
        return JSONResponse(
            {"error": {"message": f"Provider transport error: {stream_error_message}"}},
            status_code=response_status_code,
        )

    response_headers = upstream_stream.headers
    response_status_code = upstream_stream.status_code

    if upstream_stream.error_body is not None:
        latency = (time.monotonic() - start_time) * 1000
        response_body = upstream_stream.parsed_error_body()
        await enqueue_log(
            LogEntry.from_proxy_context(
                entry_id=request_id,
                request=request,
                client_api_key_hash=key_hash,
                request_body=forward_body,
                model_requested=model_requested,
                model_resolved=route.mapped_model,
                provider_name=route.provider_name,
                latency_ms=latency,
                response_status_code=upstream_stream.status_code,
                response_headers=upstream_stream.headers,
                response_body=response_body,
                error_message=_extract_error_message(response_body),
            )
        )
        return Response(
            content=upstream_stream.error_body,
            status_code=upstream_stream.status_code,
            headers=_proxy_response_headers(upstream_stream.headers),
        )

    async def stream_generator() -> AsyncGenerator[bytes, None]:
        nonlocal full_content, response_status_code, stream_error_message, usage_data
        if upstream_stream.body is None:
            response_status_code = 502
            stream_error_message = "Provider stream was not established"
            logger.error("stream_error", error=stream_error_message)
            yield f'data: {json.dumps({"error": {"message": stream_error_message}})}\n\n'.encode()
            return

        try:
            async for chunk_bytes in upstream_stream.body:
                yield chunk_bytes
                parsed = parse_sse_chunk(chunk_bytes)
                if parsed:
                    chunks_collected.append(parsed)
                    # Accumulate content
                    for choice in parsed.get("choices", []):
                        delta = choice.get("delta", {})
                        content = delta.get("content")
                        if isinstance(content, str):
                            full_content += content
                    # Check for usage in final chunk
                    usage = parsed.get("usage")
                    if isinstance(usage, dict):
                        usage_data = usage
        except httpx.RequestError as e:
            response_status_code = _transport_error_status(e)
            stream_error_message = str(e)
            error_event = f'data: {json.dumps({"error": {"message": stream_error_message}})}\n\n'
            yield error_event.encode()
            logger.error("stream_error", error=stream_error_message)
        except Exception as e:
            response_status_code = 502
            stream_error_message = str(e)
            error_event = f'data: {json.dumps({"error": {"message": stream_error_message}})}\n\n'
            yield error_event.encode()
            logger.error("stream_error", error=stream_error_message)
        finally:
            latency = (time.monotonic() - start_time) * 1000
            # Build assembled response
            assembled = None
            if full_content or chunks_collected:
                assembled = {
                    "choices": [{"message": {"role": "assistant", "content": full_content}}],
                    "usage": usage_data,
                }
            await enqueue_log(
                LogEntry.from_proxy_context(
                    entry_id=request_id,
                    request=request,
                    client_api_key_hash=key_hash,
                    request_body=forward_body,
                    model_requested=model_requested,
                    model_resolved=route.mapped_model,
                    provider_name=route.provider_name,
                    latency_ms=latency,
                    response_status_code=response_status_code,
                    response_headers=response_headers,
                    response_body=assembled,
                    stream_chunks=chunks_collected if chunks_collected else None,
                    input_tokens=usage_data.get("prompt_tokens"),
                    output_tokens=usage_data.get("completion_tokens"),
                    total_tokens=usage_data.get("total_tokens"),
                    error_message=stream_error_message,
                )
            )

    streaming_headers = _proxy_response_headers(response_headers)
    streaming_headers.setdefault("Cache-Control", "no-cache")
    streaming_headers.setdefault("X-Accel-Buffering", "no")
    return StreamingResponse(
        stream_generator(),
        status_code=upstream_stream.status_code,
        media_type=upstream_stream.content_type or "text/event-stream",
        headers=streaming_headers,
    )


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    api_key = _extract_api_key(request)
    is_valid, key_hash = validate_proxy_api_key(api_key)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

    config = get_app_config()
    models: list[JsonObject] = []
    seen: set[str] = set()
    for model_name in config.model_mappings:
        if any(char in model_name for char in "*?[]"):
            continue
        allowed, _ = check_model_access(key_hash, model_name)
        if not allowed:
            continue
        if model_name not in seen:
            seen.add(model_name)
            models.append({"id": model_name, "object": "model", "owned_by": "ai-proxy"})

    return JSONResponse({"object": "list", "data": models})
