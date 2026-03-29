"""OpenAI-compatible adapter for any provider."""

import json
from collections.abc import AsyncGenerator

import httpx
import structlog

from ai_proxy.adapters.base import BaseAdapter

logger = structlog.get_logger()


class OpenAICompatAdapter(BaseAdapter):
    def _build_headers(self, headers: dict[str, str]) -> dict[str, str]:
        out = {"Content-Type": "application/json"}
        if self.api_key:
            out["Authorization"] = f"Bearer {self.api_key}"
        out.update(self.extra_headers)
        # Forward select client headers
        for h in ("X-Request-ID", "X-Session-ID"):
            if h in headers:
                out[h] = headers[h]
        return out

    async def chat_completions(self, request_body: dict, headers: dict[str, str]) -> dict:
        url = f"{self.endpoint_url}/chat/completions"
        req_headers = self._build_headers(headers)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=request_body, headers=req_headers)
            resp.raise_for_status()
            return resp.json()

    async def stream_chat_completions(self, request_body: dict, headers: dict[str, str]) -> AsyncGenerator[bytes, None]:
        url = f"{self.endpoint_url}/chat/completions"
        req_headers = self._build_headers(headers)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=request_body, headers=req_headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        yield (line + "\n\n").encode()
                    if line.strip() == "data: [DONE]":
                        break

    async def list_models(self) -> list[dict]:
        url = f"{self.endpoint_url}/models"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        headers.update(self.extra_headers)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
        except Exception:
            logger.warning("list_models_failed", provider=self.provider_name)
            return []


def parse_sse_chunk(chunk_bytes: bytes) -> dict | None:
    text = chunk_bytes.decode("utf-8", errors="replace").strip()
    if not text or text == "data: [DONE]":
        return None
    if text.startswith("data: "):
        text = text[6:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
