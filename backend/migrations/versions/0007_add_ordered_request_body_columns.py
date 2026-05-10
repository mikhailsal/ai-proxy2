"""Add ordered request body text columns.

Keep JSONB request bodies for querying while also storing request JSON text so
the request detail and export views can preserve original object key order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_add_ordered_request_body_columns"
down_revision: str = "0006_add_ttft_ms_column"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

BACKFILL = """
UPDATE proxy_requests
SET request_body_raw = COALESCE(request_body_raw, request_body::text),
    client_request_body_raw = COALESCE(client_request_body_raw, client_request_body::text)
WHERE request_body IS NOT NULL
   OR client_request_body IS NOT NULL;
"""


def upgrade() -> None:
    op.add_column("proxy_requests", sa.Column("request_body_raw", sa.Text(), nullable=True))
    op.add_column("proxy_requests", sa.Column("client_request_body_raw", sa.Text(), nullable=True))
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_column("proxy_requests", "client_request_body_raw")
    op.drop_column("proxy_requests", "request_body_raw")
