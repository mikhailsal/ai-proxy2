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

    usage = response_body.get("usage") if isinstance(response_body.get("usage"), dict) else None
    usage_cost_details = (
        usage.get("cost_details") if isinstance(usage, dict) and isinstance(usage.get("cost_details"), dict) else None
    )
    body_cost_details = (
        response_body.get("cost_details") if isinstance(response_body.get("cost_details"), dict) else None
    )
    containers = (usage, usage_cost_details, response_body, body_cost_details)

    base_cost = _first_numeric_value(containers, "cost", "router_cost")
    inference_cost = _first_numeric_value(
        containers,
        "upstream_inference_cost",
        "inference_cost",
        "market_cost",
    )

    if base_cost is None and inference_cost is None:
        return None
    return (base_cost or 0.0) + (inference_cost or 0.0)


def _first_numeric_value(containers: tuple[dict[str, Any] | None, ...], *keys: str) -> float | None:
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in keys:
            parsed = _parse_cost_value(container.get(key))
            if parsed is not None:
                return parsed
    return None


def _parse_cost_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
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


def normalize_error_response_body(response_body: Any) -> Any:
    if not isinstance(response_body, dict) or "raw_text" in response_body:
        return response_body

    error = response_body.get("error")
    message = extract_error_message(response_body)
    if not isinstance(message, str) or not message:
        return response_body

    normalized_body = dict(response_body)
    if isinstance(error, dict):
        normalized_error = dict(error)
        normalized_error.setdefault("message", message)
        normalized_body["error"] = normalized_error
        return normalized_body

    normalized_body["error"] = {"message": message}
    return normalized_body


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
