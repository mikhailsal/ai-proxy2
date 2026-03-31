"""OpenAI-compatible adapter for any provider."""

import json
from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
import structlog

from ai_proxy.adapters.base import BaseAdapter, ProviderResponse, ProviderStreamResponse
from ai_proxy.types import JsonObject

logger = structlog.get_logger()


class OpenAICompatAdapter(BaseAdapter):
    def _build_headers(self, headers: dict[str, str], *, override_api_key: str | None = None) -> dict[str, str]:
        out = {"Content-Type": "application/json"}
        effective_key = override_api_key if override_api_key is not None else self.api_key
        if effective_key:
            out["Authorization"] = f"Bearer {effective_key}"
        out.update(self.extra_headers)
        for h in ("X-Request-ID", "X-Session-ID"):
            if h in headers:
                out[h] = headers[h]
        return out

    async def chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderResponse:
        url = f"{self.endpoint_url}/chat/completions"
        req_headers = self._build_headers(headers, override_api_key=override_api_key)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=request_body, headers=req_headers)
            return ProviderResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                body=resp.content,
                content_type=resp.headers.get("content-type"),
                sent_request_headers=req_headers,
            )

    async def stream_chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderStreamResponse:
        url = f"{self.endpoint_url}/chat/completions"
        req_headers = self._build_headers(headers, override_api_key=override_api_key)
        client = httpx.AsyncClient(timeout=self.timeout)
        response_context = client.stream("POST", url, json=request_body, headers=req_headers)

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
