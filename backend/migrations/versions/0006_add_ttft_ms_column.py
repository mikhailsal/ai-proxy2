"""Add ttft_ms column for Time to First Token metric.

Records the elapsed time (in milliseconds) from request start to the
arrival of the first response token.  For streaming requests this is
the time until the first SSE chunk; for non-streaming requests it
equals latency_ms (the full round-trip).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_add_ttft_ms_column"
down_revision: str = "0005_add_first_assistant_response_column"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

BACKFILL = """
UPDATE proxy_requests
SET ttft_ms = latency_ms
WHERE stream_chunks IS NULL
  AND latency_ms IS NOT NULL;
"""


def upgrade() -> None:
    op.add_column("proxy_requests", sa.Column("ttft_ms", sa.Float(), nullable=True))
    op.execute(BACKFILL)


def downgrade() -> None:
    op.drop_column("proxy_requests", "ttft_ms")
