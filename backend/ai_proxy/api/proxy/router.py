"""Proxy API router — /v1/chat/completions, /v1/models."""

import json
import time
import uuid
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ai_proxy.api.proxy.request_flow import (
    apply_rate_limit,
    authenticate_proxy_request,
    extract_api_key,
    validate_and_route_request,
)
from ai_proxy.api.proxy.response_utils import (
    extract_cost,
    extract_error_message,
    extract_usage,
    normalize_error_response_body,
    proxy_response_headers,
)
from ai_proxy.api.proxy.response_utils import (
    inject_ai_proxy_route as apply_ai_proxy_route,
)
from ai_proxy.api.proxy.streaming import build_streaming_response, stream_error_response
from ai_proxy.config.loader import get_app_config
from ai_proxy.core.access import check_model_access
from ai_proxy.core.json_ordering import parse_json_text, serialize_json_value
from ai_proxy.core.key_resolution import resolve_provider_key
from ai_proxy.core.modification import apply_modifications
from ai_proxy.core.routing import RouteResult
from ai_proxy.core.routing import resolve_model as _resolve_model
from ai_proxy.logging.models import LogEntry
from ai_proxy.logging.service import enqueue_log
from ai_proxy.security.auth import validate_proxy_api_key
from ai_proxy.services.model_catalog import get_proxy_model_catalog, serialize_catalog_model
from ai_proxy.types import JsonObject

logger = structlog.get_logger()
router = APIRouter()
_extract_api_key = extract_api_key
resolve_model = _resolve_model


def _transport_error_status(error: httpx.RequestError) -> int:
    if isinstance(error, httpx.TimeoutException):
        return 504
    return 502


def _inject_ai_proxy_route(response_body: Any, route: RouteResult) -> Any:
    return apply_ai_proxy_route(response_body, route, config=get_app_config())


def _resolve_sent_request_payload(adapter: Any, forward_body: JsonObject) -> tuple[JsonObject, str]:
    prepare_fn = getattr(adapter, "_prepare_request_body", None)
    prepared = prepare_fn(forward_body) if callable(prepare_fn) else None
    sent_body = prepared if isinstance(prepared, dict) else forward_body
    return sent_body, serialize_json_value(sent_body)


def _apply_provider_pinning(body: JsonObject, route: RouteResult) -> None:
    """Inject pinned provider slugs into ``provider.order`` when needed."""
    if not getattr(route, "pinned_providers", None):
        return

    provider_aware = getattr(route, "provider_aware_match", False)
    existing = body.get("provider")
    if provider_aware and isinstance(existing, dict):
        only_filter = isinstance(existing.get("only"), list) and existing["only"]
        existing["only" if only_filter else "order"] = route.pinned_providers
        if only_filter:
            existing.pop("order", None)
        existing.setdefault("allow_fallbacks", False)
        return
    if provider_aware or not isinstance(existing, dict):
        body["provider"] = {"order": route.pinned_providers, "allow_fallbacks": False}
        return
    if "order" not in existing:
        existing["order"] = route.pinned_providers
        existing.setdefault("allow_fallbacks", False)


def _prepare_forward_request(
    request: Request,
    body: JsonObject,
    route: RouteResult,
) -> tuple[JsonObject, JsonObject, dict[str, str]]:
    client_request_body: JsonObject = dict(body)
    forward_body: JsonObject = {**body, "model": route.mapped_model}
    _apply_provider_pinning(forward_body, route)
    forward_body, forward_headers = apply_modifications(
        forward_body,
        dict(request.headers),
        route.provider_name,
        route.mapped_model,
    )
    return client_request_body, forward_body, forward_headers


async def _parse_request_body(request: Request) -> tuple[JsonObject, str] | JSONResponse:
    try:
        raw_body = await request.body()
        raw_text = raw_body.decode("utf-8")
        body = parse_json_text(raw_text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return JSONResponse({"error": {"message": "Invalid JSON body"}}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"error": {"message": "JSON body must be an object"}}, status_code=400)

    return body, raw_text


@router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    start_time = time.monotonic()
    request_id = uuid.uuid4()

    parsed_request = await _parse_request_body(request)
    if isinstance(parsed_request, JSONResponse):
        return parsed_request
    body, client_request_body_raw = parsed_request

    auth = authenticate_proxy_request(request)
    if isinstance(auth, JSONResponse):
        return auth
    client_api_key, key_hash, is_known_key = auth

    request_validation = await validate_and_route_request(body, key_hash)
    if isinstance(request_validation, JSONResponse):
        return request_validation
    model_requested, route = request_validation

    override_api_key: str | None = None
    if client_api_key:
        override_api_key = resolve_provider_key(client_api_key, route.provider_name, is_known_key=is_known_key)

    rate_limit_response = await apply_rate_limit(route.provider_name)
    if rate_limit_response is not None:
        return rate_limit_response

    client_request_body, forward_body, forward_headers = _prepare_forward_request(request, body, route)
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
            client_request_body_raw=client_request_body_raw,
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
        client_request_body_raw=client_request_body_raw,
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
    client_request_body_raw: str | None = None,
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
            client_request_body_raw=client_request_body_raw,
        )

    return await _finalize_non_streaming_response(
        request=request,
        request_id=request_id,
        key_hash=key_hash,
        forward_body=forward_body,
        route=route,
        model_requested=model_requested,
        start_time=start_time,
        upstream_response=upstream_response,
        client_request_body=client_request_body,
        client_request_body_raw=client_request_body_raw,
    )


async def _finalize_non_streaming_response(
    *,
    request: Request,
    request_id: uuid.UUID,
    key_hash: str,
    forward_body: JsonObject,
    route: RouteResult,
    model_requested: str,
    start_time: float,
    upstream_response: Any,
    client_request_body: JsonObject | None,
    client_request_body_raw: str | None,
) -> Response:
    response_body = upstream_response.parsed_body()
    client_body_source = response_body
    if upstream_response.status_code >= 400:
        client_body_source = normalize_error_response_body(response_body)

    client_response_body = _inject_ai_proxy_route(client_body_source, route)
    is_json = isinstance(client_response_body, dict) and "raw_text" not in client_response_body
    client_response_headers = proxy_response_headers(upstream_response.headers, json_body=is_json)
    sent_request_body = upstream_response.sent_request_body or forward_body
    sent_request_body_raw = upstream_response.sent_request_body_raw or serialize_json_value(sent_request_body)
    input_tokens, output_tokens, total_tokens = extract_usage(response_body)
    await _enqueue_non_streaming_log(
        request=request,
        request_id=request_id,
        key_hash=key_hash,
        sent_request_headers=upstream_response.sent_request_headers,
        forward_body=sent_request_body,
        request_body_raw=sent_request_body_raw,
        route=route,
        model_requested=model_requested,
        latency=(time.monotonic() - start_time) * 1000,
        upstream_response=upstream_response,
        response_body=response_body,
        client_response_body=client_response_body,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost=extract_cost(response_body),
        client_request_body=client_request_body,
        client_request_body_raw=client_request_body_raw,
        client_response_headers=client_response_headers,
    )
    if is_json:
        return Response(
            content=json.dumps(client_response_body).encode("utf-8"),
            status_code=upstream_response.status_code,
            headers=client_response_headers,
        )
    status = upstream_response.status_code
    return Response(content=upstream_response.body, status_code=status, headers=client_response_headers)


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
    client_request_body_raw: str | None = None,
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
            client_request_body_raw=client_request_body_raw,
        )

    return await _finalize_stream(
        request,
        request_id,
        key_hash,
        upstream_stream,
        upstream_stream.sent_request_body or forward_body,
        route,
        model_requested,
        start_time,
        client_request_body,
        client_request_body_raw,
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
    client_request_body_raw: str | None,
) -> Response | StreamingResponse:
    sent_request_body = upstream_stream.sent_request_body or forward_body
    sent_request_body_raw = upstream_stream.sent_request_body_raw or serialize_json_value(sent_request_body)
    if upstream_stream.error_body is not None:
        return await stream_error_response(
            request=request,
            request_id=request_id,
            key_hash=key_hash,
            sent_request_headers=upstream_stream.sent_request_headers,
            forward_body=sent_request_body,
            forward_body_raw=sent_request_body_raw,
            route=route,
            model_requested=model_requested,
            start_time=start_time,
            upstream_stream=upstream_stream,
            extract_error_message=extract_error_message,
            inject_ai_proxy_route=_inject_ai_proxy_route,
            proxy_response_headers=proxy_response_headers,
            client_request_body=client_request_body,
            client_request_body_raw=client_request_body_raw,
        )
    return build_streaming_response(
        request=request,
        request_id=request_id,
        key_hash=key_hash,
        sent_request_headers=upstream_stream.sent_request_headers,
        forward_body=sent_request_body,
        forward_body_raw=sent_request_body_raw,
        route=route,
        model_requested=model_requested,
        start_time=start_time,
        upstream_stream=upstream_stream,
        proxy_response_headers=proxy_response_headers,
        client_request_body=client_request_body,
        client_request_body_raw=client_request_body_raw,
    )


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    api_key = extract_api_key(request)
    config = get_app_config()
    is_valid, key_hash, _is_known = validate_proxy_api_key(api_key, bypass_enabled=config.bypass.enabled)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

    models: list[JsonObject] = []
    catalog = await get_proxy_model_catalog(config=config)
    for model_name, entry in catalog.items():
        allowed, _ = check_model_access(key_hash, model_name)
        if not allowed:
            continue
        models.append(serialize_catalog_model(entry))

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
    client_request_body_raw: str | None = None,
) -> JSONResponse:
    latency = (time.monotonic() - start_time) * 1000
    response_status_code = _transport_error_status(error)
    error_message = str(error)
    logger.error(log_event, error=error_message, provider=route.provider_name)
    build_fn = getattr(route.adapter, "_build_headers", None)
    sent_headers = build_fn(forward_headers, override_api_key=override_api_key) if build_fn else forward_headers
    sent_body, sent_body_raw = _resolve_sent_request_payload(route.adapter, forward_body)
    client_body: JsonObject = {"error": {"message": f"Provider transport error: {error_message}"}}
    client_body = _inject_ai_proxy_route(client_body, route)
    client_headers = {"content-type": "application/json"}
    await enqueue_log(
        LogEntry.from_proxy_context(
            entry_id=request_id,
            request=request,
            client_api_key_hash=key_hash,
            request_headers=sent_headers,
            request_body=sent_body,
            request_body_raw=sent_body_raw,
            client_request_body=client_request_body,
            client_request_body_raw=client_request_body_raw,
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
    request_body_raw: str | None,
    route: RouteResult,
    model_requested: str,
    latency: float,
    upstream_response: Any,
    response_body: Any,
    client_response_body: Any,
    input_tokens: int | None,
    output_tokens: int | None,
    total_tokens: int | None,
    cost: float | None = None,
    client_request_body: JsonObject | None = None,
    client_request_body_raw: str | None = None,
    client_response_headers: dict[str, str] | None = None,
) -> None:
    entry = LogEntry.from_proxy_context(
        entry_id=request_id,
        request=request,
        client_api_key_hash=key_hash,
        request_headers=sent_request_headers,
        request_body=forward_body,
        request_body_raw=request_body_raw,
        client_request_body=client_request_body,
        client_request_body_raw=client_request_body_raw,
        model_requested=model_requested,
        model_resolved=route.mapped_model,
        provider_name=route.provider_name,
        latency_ms=latency,
        ttft_ms=None,
        response_status_code=upstream_response.status_code,
        response_headers=upstream_response.headers,
        client_response_headers=client_response_headers,
        response_body=response_body,
        client_response_body=client_response_body,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        error_message=extract_error_message(response_body),
    )
    entry.cost = cost
    await enqueue_log(entry)
