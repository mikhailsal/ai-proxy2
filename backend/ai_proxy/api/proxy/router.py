"""Proxy API router — /v1/chat/completions, /v1/models."""

import json
import time
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ai_proxy.adapters.openai_compat import parse_sse_chunk
from ai_proxy.config.loader import get_app_config
from ai_proxy.core.access import check_model_access
from ai_proxy.core.modification import apply_modifications
from ai_proxy.core.routing import resolve_model
from ai_proxy.logging.models import LogEntry
from ai_proxy.logging.service import enqueue_log
from ai_proxy.security.auth import hash_api_key, validate_proxy_api_key

logger = structlog.get_logger()

router = APIRouter()


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):  # noqa: ANN201
    start_time = time.monotonic()
    request_id = uuid.uuid4()

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": {"message": "Invalid JSON body"}}, status_code=400)

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
    forward_body = {**body, "model": route.mapped_model}
    forward_headers = dict(request.headers)
    forward_body, forward_headers = apply_modifications(
        forward_body, forward_headers, route.provider_name, route.mapped_model
    )

    is_streaming = body.get("stream", False)

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
    forward_body: dict,
    forward_headers: dict,
    route,  # noqa: ANN001
    model_requested: str,
    key_hash: str,
    start_time: float,
) -> JSONResponse:
    try:
        response_data = await route.adapter.chat_completions(forward_body, forward_headers)
    except Exception as e:
        latency = (time.monotonic() - start_time) * 1000
        logger.error("proxy_error", error=str(e), provider=route.provider_name)
        await enqueue_log(LogEntry(
            id=request_id,
            client_ip=request.client.host if request.client else None,
            client_api_key_hash=key_hash,
            path="/v1/chat/completions",
            request_body=forward_body,
            model_requested=model_requested,
            model_resolved=route.mapped_model,
            provider_name=route.provider_name,
            latency_ms=latency,
            error_message=str(e),
            response_status_code=502,
        ))
        return JSONResponse({"error": {"message": f"Provider error: {e}"}}, status_code=502)

    latency = (time.monotonic() - start_time) * 1000

    # Extract usage
    usage = response_data.get("usage", {})

    await enqueue_log(LogEntry(
        id=request_id,
        client_ip=request.client.host if request.client else None,
        client_api_key_hash=key_hash,
        path="/v1/chat/completions",
        request_body=forward_body,
        response_body=response_data,
        response_status_code=200,
        model_requested=model_requested,
        model_resolved=route.mapped_model,
        provider_name=route.provider_name,
        latency_ms=latency,
        input_tokens=usage.get("prompt_tokens"),
        output_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
    ))

    return JSONResponse(response_data)


async def _handle_streaming(
    request: Request,
    request_id: uuid.UUID,
    forward_body: dict,
    forward_headers: dict,
    route,  # noqa: ANN001
    model_requested: str,
    key_hash: str,
    start_time: float,
) -> StreamingResponse:
    chunks_collected: list[dict] = []
    full_content = ""
    usage_data: dict = {}

    async def stream_generator():  # noqa: ANN202
        nonlocal full_content, usage_data
        try:
            async for chunk_bytes in route.adapter.stream_chat_completions(forward_body, forward_headers):
                yield chunk_bytes
                parsed = parse_sse_chunk(chunk_bytes)
                if parsed:
                    chunks_collected.append(parsed)
                    # Accumulate content
                    for choice in parsed.get("choices", []):
                        delta = choice.get("delta", {})
                        if "content" in delta and delta["content"]:
                            full_content += delta["content"]
                    # Check for usage in final chunk
                    if "usage" in parsed:
                        usage_data = parsed["usage"]
        except Exception as e:
            error_event = f'data: {json.dumps({"error": {"message": str(e)}})}\n\n'
            yield error_event.encode()
            logger.error("stream_error", error=str(e))
        finally:
            latency = (time.monotonic() - start_time) * 1000
            # Build assembled response
            assembled = None
            if full_content or chunks_collected:
                assembled = {
                    "choices": [{"message": {"role": "assistant", "content": full_content}}],
                    "usage": usage_data,
                }
            await enqueue_log(LogEntry(
                id=request_id,
                client_ip=request.client.host if request.client else None,
                client_api_key_hash=key_hash,
                path="/v1/chat/completions",
                request_body=forward_body,
                response_body=assembled,
                stream_chunks=chunks_collected if chunks_collected else None,
                response_status_code=200,
                model_requested=model_requested,
                model_resolved=route.mapped_model,
                provider_name=route.provider_name,
                latency_ms=latency,
                input_tokens=usage_data.get("prompt_tokens"),
                output_tokens=usage_data.get("completion_tokens"),
                total_tokens=usage_data.get("total_tokens"),
            ))

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/v1/models")
async def list_models(request: Request):  # noqa: ANN201
    api_key = _extract_api_key(request)
    is_valid, key_hash = validate_proxy_api_key(api_key)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)

    config = get_app_config()
    models = []
    seen = set()
    for model_name in config.model_mappings:
        if model_name not in seen:
            seen.add(model_name)
            models.append({"id": model_name, "object": "model", "owned_by": "ai-proxy"})

    return JSONResponse({"object": "list", "data": models})
