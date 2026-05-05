"""OpenAI-compatible adapter for any provider."""

import copy
import json
from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
import structlog

from ai_proxy.adapters.base import BaseAdapter, ProviderResponse, ProviderStreamResponse
from ai_proxy.types import JsonObject

logger = structlog.get_logger()

_GOOGLE_THOUGHT_INCLUDE_MARKERS = ("thought", "reasoning")


_STRIPPED_REQUEST_HEADERS = {
    "accept-encoding",
    "authorization",
    "content-length",
    "content-type",
    "host",
    "connection",
    "content-encoding",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "sec-fetch-mode",
    "sec-fetch-site",
    "sec-fetch-dest",
}


class OpenAICompatAdapter(BaseAdapter):
    def _prepare_request_body(self, request_body: dict[str, Any]) -> dict[str, Any]:
        if self.provider_name != "google":
            return request_body

        prepared = copy.deepcopy(request_body)
        prepared.pop("provider", None)

        include = prepared.pop("include", None)
        if _google_include_requests_thoughts(include):
            thinking_config = _ensure_google_thinking_config(prepared)
            thinking_config["include_thoughts"] = True

        reasoning = prepared.pop("reasoning", None)
        reasoning_effort = prepared.pop("reasoning_effort", None)
        standard_reasoning_effort = _extract_google_reasoning_effort(reasoning, reasoning_effort)
        if standard_reasoning_effort and not _google_has_explicit_thinking_level(prepared):
            if _google_is_gemma_thinking_toggle_model(prepared.get("model")):
                # Google-hosted Gemma 4 exposes reasoning as an on/off toggle via thinking_level.
                # `minimal` is the effective "off" position, while any enabled standard effort
                # level must be coerced to `high` because intermediate values like `low` are rejected.
                thinking_config = _ensure_google_thinking_config(prepared)
                thinking_config["thinking_level"] = _map_google_gemma_reasoning_effort(standard_reasoning_effort)
            elif _google_supports_reasoning_effort(prepared.get("model")):
                prepared["reasoning_effort"] = standard_reasoning_effort

        if prepared.get("stream"):
            stream_options = prepared.get("stream_options")
            if not isinstance(stream_options, dict):
                stream_options = {}
                prepared["stream_options"] = stream_options
            stream_options.setdefault("include_usage", True)

        return prepared

    def _build_headers(self, headers: dict[str, str], *, override_api_key: str | None = None) -> dict[str, str]:
        out = {k: v for k, v in headers.items() if k.lower() not in _STRIPPED_REQUEST_HEADERS}
        out["Accept-Encoding"] = "identity"
        out["Content-Type"] = "application/json"
        effective_key = override_api_key if override_api_key is not None else self.api_key
        if effective_key:
            out["Authorization"] = f"Bearer {effective_key}"
        out.update(self.extra_headers)
        return out

    async def chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderResponse:
        url = f"{self.endpoint_url}/chat/completions"
        req_headers = self._build_headers(headers, override_api_key=override_api_key)
        prepared_body = self._prepare_request_body(request_body)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=prepared_body, headers=req_headers)
            return ProviderResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                body=resp.content,
                content_type=resp.headers.get("content-type"),
                sent_request_headers=req_headers,
                sent_request_body=prepared_body,
            )

    async def stream_chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderStreamResponse:
        url = f"{self.endpoint_url}/chat/completions"
        req_headers = self._build_headers(headers, override_api_key=override_api_key)
        prepared_body = self._prepare_request_body(request_body)
        client = httpx.AsyncClient(timeout=self.timeout)
        response_context = client.stream("POST", url, json=prepared_body, headers=req_headers)

        try:
            resp = await response_context.__aenter__()
        except Exception:
            await client.aclose()
            raise

        if resp.is_error:
            body = await resp.aread()
            await response_context.__aexit__(None, None, None)
            await client.aclose()
            return ProviderStreamResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                content_type=resp.headers.get("content-type"),
                error_body=body,
                sent_request_headers=req_headers,
                sent_request_body=prepared_body,
            )

        async def body_iterator() -> AsyncGenerator[bytes, None]:
            try:
                async for line in resp.aiter_lines():
                    if line:
                        yield (line + "\n\n").encode()
                    if line.strip() == "data: [DONE]":
                        break
            finally:
                await response_context.__aexit__(None, None, None)
                await client.aclose()

        return ProviderStreamResponse(
            status_code=resp.status_code,
            headers=dict(resp.headers),
            content_type=resp.headers.get("content-type"),
            body=body_iterator(),
            sent_request_headers=req_headers,
            sent_request_body=prepared_body,
        )

    async def list_models(self) -> list[JsonObject]:
        url = f"{self.endpoint_url}/models"
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = cast("JsonObject", resp.json())
                return cast("list[JsonObject]", data.get("data", []))
        except Exception:
            logger.warning("list_models_failed", provider=self.provider_name)
            return []


def parse_sse_chunk(chunk_bytes: bytes) -> JsonObject | None:
    text = chunk_bytes.decode("utf-8", errors="replace").strip()
    if not text or text == "data: [DONE]":
        return None
    if text.startswith("data: "):
        text = text[6:]
    try:
        return cast("JsonObject", json.loads(text))
    except json.JSONDecodeError:
        return None


def _google_include_requests_thoughts(include_value: Any) -> bool:
    if not isinstance(include_value, list):
        return False

    for item in include_value:
        if not isinstance(item, str):
            continue
        normalized = item.lower()
        if any(marker in normalized for marker in _GOOGLE_THOUGHT_INCLUDE_MARKERS):
            return True
    return False


def _google_supports_reasoning_effort(model_name: Any) -> bool:
    return isinstance(model_name, str) and model_name.startswith("gemini-")


def _google_is_gemma_thinking_toggle_model(model_name: Any) -> bool:
    return isinstance(model_name, str) and model_name.startswith("gemma-4-")


def _extract_google_reasoning_effort(reasoning_value: Any, reasoning_effort_value: Any) -> str | None:
    if isinstance(reasoning_value, dict):
        effort = reasoning_value.get("effort")
        if isinstance(effort, str) and effort:
            return effort.lower()

    if isinstance(reasoning_effort_value, str) and reasoning_effort_value:
        return reasoning_effort_value.lower()

    return None


def _map_google_gemma_reasoning_effort(reasoning_effort: str) -> str:
    return "minimal" if reasoning_effort == "none" else "high"


def _google_has_explicit_thinking_level(request_body: dict[str, Any]) -> bool:
    extra_body = request_body.get("extra_body")
    if not isinstance(extra_body, dict):
        return False

    google_config = extra_body.get("google")
    if not isinstance(google_config, dict):
        return False

    thinking_config = google_config.get("thinking_config")
    if not isinstance(thinking_config, dict):
        return False

    return "thinking_level" in thinking_config or "thinking_budget" in thinking_config


def _ensure_google_thinking_config(request_body: dict[str, Any]) -> dict[str, Any]:
    extra_body = request_body.get("extra_body")
    if not isinstance(extra_body, dict):
        extra_body = {}
        request_body["extra_body"] = extra_body

    google_config = extra_body.get("google")
    if not isinstance(google_config, dict):
        google_config = {}
        extra_body["google"] = google_config

    thinking_config = google_config.get("thinking_config")
    if not isinstance(thinking_config, dict):
        thinking_config = {}
        google_config["thinking_config"] = thinking_config

    return thinking_config
