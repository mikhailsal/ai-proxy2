"""Add columns and trigger for conversation grouping.

Adds system_prompt_text and first_user_message_text as regular columns,
populated by a trigger on INSERT/UPDATE and backfilled from existing data.
These enable efficient SQL-level GROUP BY for the conversations API
instead of loading all rows into Python.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_add_conversation_group_columns"
down_revision: str = "0003_add_client_request_response_headers"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_extract_conversation_fields()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.request_body IS NOT NULL
     AND jsonb_typeof(NEW.request_body->'messages') = 'array'
     AND jsonb_array_length(NEW.request_body->'messages') > 0
  THEN
    NEW.system_prompt_text := (
      SELECT m->>'content'
      FROM jsonb_array_elements(NEW.request_body->'messages') AS m
      WHERE m->>'role' = 'system'
      LIMIT 1
    );
    NEW.first_user_message_text := (
      SELECT m->>'content'
      FROM jsonb_array_elements(NEW.request_body->'messages') AS m
      WHERE m->>'role' = 'user'
      LIMIT 1
    );
  ELSE
    NEW.system_prompt_text := NULL;
    NEW.first_user_message_text := NULL;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER trg_extract_conversation_fields
  BEFORE INSERT OR UPDATE OF request_body
  ON proxy_requests
  FOR EACH ROW
  EXECUTE FUNCTION fn_extract_conversation_fields();
"""

BACKFILL = """
UPDATE proxy_requests SET
  system_prompt_text = (
    SELECT m->>'content'
    FROM jsonb_array_elements(request_body->'messages') AS m
    WHERE m->>'role' = 'system'
    LIMIT 1
  ),
  first_user_message_text = (
    SELECT m->>'content'
    FROM jsonb_array_elements(request_body->'messages') AS m
    WHERE m->>'role' = 'user'
    LIMIT 1
  )
WHERE request_body IS NOT NULL
  AND jsonb_typeof(request_body->'messages') = 'array'
  AND jsonb_array_length(request_body->'messages') > 0;
"""


def upgrade() -> None:
    op.add_column("proxy_requests", sa.Column("system_prompt_text", sa.Text(), nullable=True))
    op.add_column("proxy_requests", sa.Column("first_user_message_text", sa.Text(), nullable=True))

    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)
    op.execute(BACKFILL)

    op.create_index(
        "ix_proxy_requests_system_prompt_text",
        "proxy_requests",
        ["system_prompt_text"],
        postgresql_using="hash",
    )
    op.create_index(
        "ix_proxy_requests_first_user_message_text",
        "proxy_requests",
        ["first_user_message_text"],
        postgresql_using="hash",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proxy_requests_first_user_message_text",
        table_name="proxy_requests",
        postgresql_using="hash",
    )
    op.drop_index(
        "ix_proxy_requests_system_prompt_text",
        table_name="proxy_requests",
        postgresql_using="hash",
    )
    op.execute("DROP TRIGGER IF EXISTS trg_extract_conversation_fields ON proxy_requests;")
    op.execute("DROP FUNCTION IF EXISTS fn_extract_conversation_fields();")
    op.drop_column("proxy_requests", "first_user_message_text")
    op.drop_column("proxy_requests", "system_prompt_text")
