"""Abstract base adapter."""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, cast

from ai_proxy.types import JsonArray, JsonObject

JsonValue = JsonObject | JsonArray


def _parse_body(body: bytes, content_type: str | None) -> JsonValue | dict[str, str] | None:
    if not body:
        return None

    if content_type and "json" in content_type.lower():
        try:
            return cast("JsonValue", json.loads(body))
        except json.JSONDecodeError:
            return {"raw_text": body.decode("utf-8", errors="replace")}

    return {"raw_text": body.decode("utf-8", errors="replace")}


@dataclass(frozen=True)
class ProviderResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    content_type: str | None = None
    sent_request_headers: dict[str, str] | None = None

    def parsed_body(self) -> JsonValue | dict[str, str] | None:
        return _parse_body(self.body, self.content_type)


@dataclass(frozen=True)
class ProviderStreamResponse:
    status_code: int
    headers: dict[str, str]
    content_type: str | None = None
    body: AsyncGenerator[bytes, None] | None = None
    error_body: bytes | None = None
    sent_request_headers: dict[str, str] | None = None

    def parsed_error_body(self) -> JsonValue | dict[str, str] | None:
        if self.error_body is None:
            return None
        return _parse_body(self.error_body, self.content_type)


class BaseAdapter(ABC):
    def __init__(
        self,
        provider_name: str,
        endpoint_url: str,
        api_key: str | None,
        headers: dict[str, str] | None = None,
        timeout: int = 120,
    ) -> None:
        self.provider_name = provider_name
        self.endpoint_url = endpoint_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = headers or {}
        self.timeout = timeout

    @abstractmethod
    async def chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderResponse: ...

    @abstractmethod
    async def stream_chat_completions(
        self, request_body: dict[str, Any], headers: dict[str, str], *, override_api_key: str | None = None
    ) -> ProviderStreamResponse: ...

    @abstractmethod
    async def list_models(self) -> list[JsonObject]: ...
