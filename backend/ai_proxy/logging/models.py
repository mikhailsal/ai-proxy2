"""Log entry Pydantic models."""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    client_ip: str | None = None
    client_api_key_hash: str | None = None
    method: str = "POST"
    path: str = "/v1/chat/completions"
    request_headers: dict[str, Any] | None = None
    request_body: dict[str, Any] | list[Any] | None = None
    response_status_code: int | None = None
    response_headers: dict[str, Any] | None = None
    response_body: dict[str, Any] | list[Any] | None = None
    stream_chunks: list[Any] | None = None
    model_requested: str | None = None
    model_resolved: str | None = None
    provider_name: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None
    cache_status: str | None = None
    reasoning_tokens: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def from_proxy_context(
        cls,
        *,
        entry_id: uuid.UUID,
        request: Request,
        client_api_key_hash: str,
        request_body: dict[str, Any] | list[Any] | None,
        model_requested: str,
        model_resolved: str,
        provider_name: str,
        latency_ms: float,
        response_status_code: int,
        response_headers: dict[str, Any] | None = None,
        response_body: dict[str, Any] | list[Any] | None = None,
        stream_chunks: list[Any] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "LogEntry":
        return cls(
            id=entry_id,
            client_ip=request.client.host if request.client else None,
            client_api_key_hash=client_api_key_hash,
            method=request.method,
            path=request.url.path,
            request_headers=dict(request.headers),
            request_body=request_body,
            response_status_code=response_status_code,
            response_headers=response_headers,
            response_body=response_body,
            stream_chunks=stream_chunks,
            model_requested=model_requested,
            model_resolved=model_resolved,
            provider_name=provider_name,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_message=error_message,
            metadata=metadata,
        )
