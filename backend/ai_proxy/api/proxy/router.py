"""Proxy API router — /v1/chat/completions, /v1/models."""

import time
import uuid
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ai_proxy.api.proxy.streaming import build_streaming_response, stream_error_response
from ai_proxy.config.loader import get_app_config
from ai_proxy.core.access import check_model_access
from ai_proxy.core.key_resolution import resolve_provider_key
from ai_proxy.core.modification import apply_modifications
from ai_proxy.core.rate_limiter import get_rate_limiter
from ai_proxy.core.routing import RouteResult, resolve_model
from ai_proxy.logging.models import LogEntry
from ai_proxy.logging.service import enqueue_log
from ai_proxy.security.auth import validate_proxy_api_key
from ai_proxy.types import JsonObject

logger = structlog.get_logger()

router = APIRouter()
HOP_BY_HOP_HEADERS = {
    "connection",
    "content-encoding",
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


def _proxy_response_headers(headers: dict[str, str], *, json_body: bool = False) -> dict[str, str]:
    out = {key: value for key, value in headers.items() if key.lower() not in HOP_BY_HOP_HEADERS}
    if json_body:
        out["content-type"] = "application/json"
    return out


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


def _extract_cost(response_body: Any) -> float | None:
    if not isinstance(response_body, dict):
        return None
    usage = response_body.get("usage")
    if isinstance(usage, dict):
        cost = usage.get("cost")
        if isinstance(cost, int | float):
            return float(cost)
    cost = response_body.get("cost")
    if isinstance(cost, int | float):
        return float(cost)
    return None


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


async def _parse_request_body(request: Request) -> JsonObject | JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": {"message": "Invalid JSON body"}}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"error": {"message": "JSON body must be an object"}}, status_code=400)

    return body


def _authenticate_proxy_request(request: Request) -> tuple[str, str, bool] | JSONResponse:
    api_key = _extract_api_key(request)
    config = get_app_config()
    is_valid, key_hash, is_known_key = validate_proxy_api_key(api_key, bypass_enabled=config.bypass.enabled)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

    return api_key or "", key_hash, is_known_key


def _validate_and_route_request(body: JsonObject, key_hash: str) -> tuple[str, RouteResult] | JSONResponse:
    model_requested = body.get("model", "")
    if not model_requested:
        return JSONResponse({"error": {"message": "model field is required"}}, status_code=400)

    allowed, reason = check_model_access(key_hash, model_requested)
    if not allowed:
        return JSONResponse({"error": {"message": reason}}, status_code=403)

    try:
        route = resolve_model(model_requested)
    except ValueError as error:
        return JSONResponse({"error": {"message": str(error)}}, status_code=404)

    return model_requested, route


async def _apply_rate_limit(provider_name: str) -> JSONResponse | None:
    limiter = get_rate_limiter(provider_name)
    if limiter is None:
        return None
    if limiter.is_queue_full:
        return JSONResponse(
            {"error": {"message": f"Rate limiter queue full for provider {provider_name}"}},
            status_code=429,
        )
    await limiter.acquire()
    return None


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    start_time = time.monotonic()
    request_id = uuid.uuid4()

    body = await _parse_request_body(request)
    if isinstance(body, JSONResponse):
        return body

    auth = _authenticate_proxy_request(request)
    if isinstance(auth, JSONResponse):
        return auth
    client_api_key, key_hash, is_known_key = auth

    request_validation = _validate_and_route_request(body, key_hash)
    if isinstance(request_validation, JSONResponse):
        return request_validation
    model_requested, route = request_validation

    override_api_key: str | None = None
    if client_api_key:
        override_api_key = resolve_provider_key(client_api_key, route.provider_name, is_known_key=is_known_key)

    rate_limit_response = await _apply_rate_limit(route.provider_name)
    if rate_limit_response is not None:
        return rate_limit_response

    client_request_body: JsonObject = dict(body)
    forward_body: JsonObject = {**body, "model": route.mapped_model}
    forward_headers = dict(request.headers)
    forward_body, forward_headers = apply_modifications(
        forward_body, forward_headers, route.provider_name, route.mapped_model
    )

    is_streaming = bool(body.get("stream", False))
    if is_streaming:
        return await _handle_streaming(
            request,
            request_id,
            forward_body,
            forward_headers,
            route,
            model_requested,
            key_hash,
            start_time,
            override_api_key=override_api_key,
            client_request_body=client_request_body,
        )

    return await _handle_non_streaming(
        request,
        request_id,
        forward_body,
        forward_headers,
        route,
        model_requested,
        key_hash,
        start_time,
        override_api_key=override_api_key,
        client_request_body=client_request_body,
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
    *,
    override_api_key: str | None = None,
    client_request_body: JsonObject | None = None,
) -> Response:
    try:
        upstream_response = await route.adapter.chat_completions(
            forward_body,
            forward_headers,
            override_api_key=override_api_key,
        )
    except httpx.RequestError as error:
        return await _transport_error_response(
            error=error,
            log_event="proxy_error",
            request=request,
            request_id=request_id,
            forward_body=forward_body,
            forward_headers=forward_headers,
            route=route,
            model_requested=model_requested,
            key_hash=key_hash,
            start_time=start_time,
            override_api_key=override_api_key,
            client_request_body=client_request_body,
        )

    response_body = upstream_response.parsed_body()
    is_json = isinstance(response_body, dict) and "raw_text" not in response_body
    client_response_headers = _proxy_response_headers(upstream_response.headers, json_body=is_json)
    input_tokens, output_tokens, total_tokens = _extract_usage(response_body)
    await _enqueue_non_streaming_log(
        request=request,
        request_id=request_id,
        key_hash=key_hash,
        sent_request_headers=upstream_response.sent_request_headers,
        forward_body=forward_body,
        route=route,
        model_requested=model_requested,
        latency=(time.monotonic() - start_time) * 1000,
        upstream_response=upstream_response,
        response_body=response_body,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=_extract_cost(response_body),
        client_request_body=client_request_body,
        client_response_headers=client_response_headers,
    )
    return Response(
        content=upstream_response.body, status_code=upstream_response.status_code, headers=client_response_headers
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
    *,
    override_api_key: str | None = None,
    client_request_body: JsonObject | None = None,
) -> Response | StreamingResponse:
    try:
        upstream_stream = await route.adapter.stream_chat_completions(
            forward_body,
            forward_headers,
            override_api_key=override_api_key,
        )
    except httpx.RequestError as error:
        return await _transport_error_response(
            error=error,
            log_event="stream_transport_error",
            request=request,
            request_id=request_id,
            forward_body=forward_body,
            forward_headers=forward_headers,
            route=route,
            model_requested=model_requested,
            key_hash=key_hash,
            start_time=start_time,
            override_api_key=override_api_key,
            client_request_body=client_request_body,
        )

    return await _finalize_stream(
        request,
        request_id,
        key_hash,
        upstream_stream,
        forward_body,
        route,
        model_requested,
        start_time,
        client_request_body,
    )


async def _finalize_stream(
    request: Request,
    request_id: uuid.UUID,
    key_hash: str,
    upstream_stream: Any,
    forward_body: JsonObject,
    route: RouteResult,
    model_requested: str,
    start_time: float,
    client_request_body: JsonObject | None,
) -> Response | StreamingResponse:
    if upstream_stream.error_body is not None:
        return await stream_error_response(
            request=request,
            request_id=request_id,
            key_hash=key_hash,
            sent_request_headers=upstream_stream.sent_request_headers,
            forward_body=forward_body,
            route=route,
            model_requested=model_requested,
            start_time=start_time,
            upstream_stream=upstream_stream,
            extract_error_message=_extract_error_message,
            proxy_response_headers=_proxy_response_headers,
            client_request_body=client_request_body,
        )
    return build_streaming_response(
        request=request,
        request_id=request_id,
        key_hash=key_hash,
        sent_request_headers=upstream_stream.sent_request_headers,
        forward_body=forward_body,
        route=route,
        model_requested=model_requested,
        start_time=start_time,
        upstream_stream=upstream_stream,
        proxy_response_headers=_proxy_response_headers,
        client_request_body=client_request_body,
    )


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    api_key = _extract_api_key(request)
    config = get_app_config()
    is_valid, key_hash, _is_known = validate_proxy_api_key(api_key, bypass_enabled=config.bypass.enabled)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

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


async def _transport_error_response(
    *,
    error: httpx.RequestError,
    log_event: str,
    request: Request,
    request_id: uuid.UUID,
    forward_body: JsonObject,
    forward_headers: dict[str, str],
    route: RouteResult,
    model_requested: str,
    key_hash: str,
    start_time: float,
    override_api_key: str | None = None,
    client_request_body: JsonObject | None = None,
) -> JSONResponse:
    latency = (time.monotonic() - start_time) * 1000
    response_status_code = _transport_error_status(error)
    error_message = str(error)
    logger.error(log_event, error=error_message, provider=route.provider_name)
    build_fn = getattr(route.adapter, "_build_headers", None)
    sent_headers = build_fn(forward_headers, override_api_key=override_api_key) if build_fn else forward_headers
    client_body: JsonObject = {"error": {"message": f"Provider transport error: {error_message}"}}
    client_headers = {"content-type": "application/json"}
    await enqueue_log(
        LogEntry.from_proxy_context(
            entry_id=request_id,
            request=request,
            client_api_key_hash=key_hash,
            request_headers=sent_headers,
            request_body=forward_body,
            client_request_body=client_request_body,
            model_requested=model_requested,
            model_resolved=route.mapped_model,
            provider_name=route.provider_name,
            latency_ms=latency,
            response_status_code=response_status_code,
            client_response_body=client_body,
            client_response_headers=client_headers,
            error_message=error_message,
        )
    )
    return JSONResponse(client_body, status_code=response_status_code)


async def _enqueue_non_streaming_log(
    *,
    request: Request,
    request_id: uuid.UUID,
    key_hash: str,
    sent_request_headers: dict[str, str] | None,
    forward_body: JsonObject,
    route: RouteResult,
    model_requested: str,
    latency: float,
    upstream_response: Any,
    response_body: Any,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    cost: float | None = None,
    client_request_body: JsonObject | None = None,
    client_response_headers: dict[str, str] | None = None,
) -> None:
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
        response_status_code=upstream_response.status_code,
        response_headers=upstream_response.headers,
        client_response_headers=client_response_headers,
        response_body=response_body,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        error_message=_extract_error_message(response_body),
    )
    entry.cost = cost
    await enqueue_log(entry)
