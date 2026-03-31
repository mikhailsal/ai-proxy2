"""Add client_request_headers and client_response_headers columns."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_add_client_request_response_headers"
down_revision: str = "0002_add_client_request_response_body"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proxy_requests",
        sa.Column("client_request_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "proxy_requests",
        sa.Column("client_response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proxy_requests", "client_response_headers")
    op.drop_column("proxy_requests", "client_request_headers")
