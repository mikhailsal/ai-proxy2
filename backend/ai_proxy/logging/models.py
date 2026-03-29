"""Log entry Pydantic models."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    client_ip: str | None = None
    client_api_key_hash: str | None = None
    method: str = "POST"
    path: str = "/v1/chat/completions"
    request_headers: dict | None = None
    request_body: dict | None = None
    response_status_code: int | None = None
    response_headers: dict | None = None
    response_body: dict | None = None
    stream_chunks: list | None = None
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
    metadata: dict | None = None
