"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ai_proxy.types import JsonArray, JsonObject


class Base(DeclarativeBase):
    pass


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False, default="openai_compatible")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings_json: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    requests: Mapped[list["ProxyRequest"]] = relationship(back_populates="provider")


class ProxyRequest(Base):
    __tablename__ = "proxy_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    client_api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False, default="POST")
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    request_headers: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    request_body: Mapped[JsonObject | JsonArray | None] = mapped_column(JSONB, nullable=True)
    client_request_body: Mapped[JsonObject | JsonArray | None] = mapped_column(JSONB, nullable=True)
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    response_headers: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    response_body: Mapped[JsonObject | JsonArray | None] = mapped_column(JSONB, nullable=True)
    client_response_body: Mapped[JsonObject | JsonArray | None] = mapped_column(JSONB, nullable=True)
    stream_chunks: Mapped[JsonArray | None] = mapped_column(JSONB, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(request_body::text, '') || ' ' || coalesce(response_body::text, ''))",
            persisted=True,
        ),
        nullable=True,
    )
    model_requested: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    model_resolved: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    provider_id: Mapped[int | None] = mapped_column(ForeignKey("providers.id"), nullable=True, index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[JsonObject | None] = mapped_column("metadata", JSONB, nullable=True)

    provider: Mapped[Provider | None] = relationship(back_populates="requests")
    debug_logs: Mapped[list["ProviderDebugLog"]] = relationship(back_populates="proxy_request")

    __table_args__ = (
        Index("ix_request_body_gin", "request_body", postgresql_using="gin"),
        Index("ix_response_body_gin", "response_body", postgresql_using="gin"),
        Index("ix_proxy_requests_search_vector", "search_vector", postgresql_using="gin"),
    )


class ProviderDebugLog(Base):
    __tablename__ = "provider_debug_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("proxy_requests.id"), nullable=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)

    proxy_request: Mapped[ProxyRequest | None] = relationship(back_populates="debug_logs")
