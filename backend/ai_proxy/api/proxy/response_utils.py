"""Helpers for shaping proxy responses returned to clients."""

from typing import Any

from ai_proxy.config.loader import get_app_config
from ai_proxy.core.routing import RouteResult

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


def proxy_response_headers(headers: dict[str, str], *, json_body: bool = False) -> dict[str, str]:
    out = {key: value for key, value in headers.items() if key.lower() not in HOP_BY_HOP_HEADERS}
    if json_body:
        out["content-type"] = "application/json"
    return out


def extract_usage(response_body: Any) -> tuple[int | None, int | None, int | None]:
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


def extract_cost(response_body: Any) -> float | None:
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


def extract_error_message(response_body: Any, fallback: str | None = None) -> str | None:
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


def client_route_identifier(route: RouteResult) -> str:
    route_label = getattr(route, "route_label", None)
    if isinstance(route_label, str) and route_label:
        return route_label

    route_value = f"{route.provider_name}:{route.mapped_model}"
    pinned_providers = getattr(route, "pinned_providers", None)
    if isinstance(pinned_providers, list) and pinned_providers:
        route_value = f"{route_value}+{','.join(pinned_providers)}"
    return route_value


def inject_ai_proxy_route(response_body: Any, route: RouteResult, *, config: Any | None = None) -> Any:
    if config is None:
        config = get_app_config()
    if not config.response.include_ai_proxy_route:
        return response_body
    if not isinstance(response_body, dict) or "raw_text" in response_body:
        return response_body

    client_body = dict(response_body)
    client_body["ai_proxy_route"] = client_route_identifier(route)
    return client_body
