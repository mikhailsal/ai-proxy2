"""Authentication, routing, and rate-limit helpers for proxy requests."""

import inspect
import sys

from fastapi import Request
from fastapi.responses import JSONResponse

from ai_proxy.config.loader import get_app_config
from ai_proxy.core.access import check_model_access
from ai_proxy.core.rate_limiter import get_rate_limiter
from ai_proxy.core.routing import RouteResult, resolve_model
from ai_proxy.security.auth import validate_proxy_api_key
from ai_proxy.types import JsonObject


def _router_override(name: str, default):
    router = sys.modules.get("ai_proxy.api.proxy.router")
    return getattr(router, name, default) if router is not None else default


def extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def authenticate_proxy_request(request: Request) -> tuple[str, str, bool] | JSONResponse:
    api_key = extract_api_key(request)
    config = _router_override("get_app_config", get_app_config)()
    validate_key = _router_override("validate_proxy_api_key", validate_proxy_api_key)
    is_valid, key_hash, is_known_key = validate_key(api_key, bypass_enabled=config.bypass.enabled)
    if not is_valid:
        return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=401)
    return api_key or "", key_hash, is_known_key


async def validate_and_route_request(body: JsonObject, key_hash: str) -> tuple[str, RouteResult] | JSONResponse:
    model_requested = body.get("model", "")
    if not model_requested:
        return JSONResponse({"error": {"message": "model field is required"}}, status_code=400)

    check_access = _router_override("check_model_access", check_model_access)
    allowed, reason = check_access(key_hash, model_requested)
    if not allowed:
        return JSONResponse({"error": {"message": reason}}, status_code=403)

    try:
        resolve_route = _router_override("resolve_model", resolve_model)
        resolved = resolve_route(model_requested, body=body)
        route = await resolved if inspect.isawaitable(resolved) else resolved
    except ValueError as error:
        return JSONResponse({"error": {"message": str(error)}}, status_code=404)

    return model_requested, route


async def apply_rate_limit(provider_name: str) -> JSONResponse | None:
    limiter = _router_override("get_rate_limiter", get_rate_limiter)(provider_name)
    if limiter is None:
        return None
    if limiter.is_queue_full:
        return JSONResponse(
            {"error": {"message": f"Rate limiter queue full for provider {provider_name}"}},
            status_code=429,
        )
    await limiter.acquire()
    return None
