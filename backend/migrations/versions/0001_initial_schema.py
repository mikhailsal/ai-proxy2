"""Initial schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("endpoint_url", sa.String(length=1024), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("settings_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "proxy_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=True),
        sa.Column("client_api_key_hash", sa.String(length=64), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("request_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stream_chunks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(request_body::text, '') || ' ' || coalesce(response_body::text, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column("model_requested", sa.String(length=255), nullable=True),
        sa.Column("model_resolved", sa.String(length=255), nullable=True),
        sa.Column("provider_id", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("cache_status", sa.String(length=32), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proxy_requests_client_api_key_hash", "proxy_requests", ["client_api_key_hash"], unique=False)
    op.create_index("ix_proxy_requests_model_requested", "proxy_requests", ["model_requested"], unique=False)
    op.create_index("ix_proxy_requests_model_resolved", "proxy_requests", ["model_resolved"], unique=False)
    op.create_index("ix_proxy_requests_provider_id", "proxy_requests", ["provider_id"], unique=False)
    op.create_index("ix_proxy_requests_response_status_code", "proxy_requests", ["response_status_code"], unique=False)
    op.create_index("ix_proxy_requests_timestamp", "proxy_requests", ["timestamp"], unique=False)
    op.create_index("ix_request_body_gin", "proxy_requests", ["request_body"], unique=False, postgresql_using="gin")
    op.create_index("ix_response_body_gin", "proxy_requests", ["response_body"], unique=False, postgresql_using="gin")
    op.create_index(
        "ix_proxy_requests_search_vector",
        "proxy_requests",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_table(
        "provider_debug_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_request_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["proxy_request_id"], ["proxy_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_debug_logs_proxy_request_id",
        "provider_debug_logs",
        ["proxy_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_provider_debug_logs_proxy_request_id", table_name="provider_debug_logs")
    op.drop_table("provider_debug_logs")
    op.drop_index("ix_proxy_requests_search_vector", table_name="proxy_requests", postgresql_using="gin")
    op.drop_index("ix_response_body_gin", table_name="proxy_requests", postgresql_using="gin")
    op.drop_index("ix_request_body_gin", table_name="proxy_requests", postgresql_using="gin")
    op.drop_index("ix_proxy_requests_timestamp", table_name="proxy_requests")
    op.drop_index("ix_proxy_requests_response_status_code", table_name="proxy_requests")
    op.drop_index("ix_proxy_requests_provider_id", table_name="proxy_requests")
    op.drop_index("ix_proxy_requests_model_resolved", table_name="proxy_requests")
    op.drop_index("ix_proxy_requests_model_requested", table_name="proxy_requests")
    op.drop_index("ix_proxy_requests_client_api_key_hash", table_name="proxy_requests")
    op.drop_table("proxy_requests")
    op.drop_table("providers")
