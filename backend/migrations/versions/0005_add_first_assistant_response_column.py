"""Add first_assistant_response_text column for conversation grouping.

Extracts the first assistant response text and stores it as a materialised
column.  The value is taken from request_body.messages (the first message
with role='assistant'), which represents the conversation history that
the client already has.  For single-turn requests where no assistant
message exists in the request yet, the trigger falls back to the current
response (response_body.choices[0].message.content).

This ensures that every request belonging to the same multi-turn
conversation gets the SAME first_assistant_response_text, enabling
correct GROUP BY for the conversations API.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_add_first_assistant_response_column"
down_revision: str = "0004_add_conversation_group_columns"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION fn_extract_first_assistant_response()
RETURNS TRIGGER AS $$
DECLARE
  _text TEXT;
BEGIN
  _text := NULL;

  -- Primary: first assistant message in request_body.messages (conversation history)
  IF NEW.request_body IS NOT NULL
     AND jsonb_typeof(NEW.request_body->'messages') = 'array'
     AND jsonb_array_length(NEW.request_body->'messages') > 0
  THEN
    _text := (
      SELECT m->>'content'
      FROM jsonb_array_elements(NEW.request_body->'messages') AS m
      WHERE m->>'role' = 'assistant'
      LIMIT 1
    );
  END IF;

  -- Fallback: response_body (first turn — no assistant in history yet)
  IF _text IS NULL
     AND NEW.response_body IS NOT NULL
     AND jsonb_typeof(NEW.response_body->'choices') = 'array'
     AND jsonb_array_length(NEW.response_body->'choices') > 0
  THEN
    _text := NEW.response_body->'choices'->0->'message'->>'content';
  END IF;

  NEW.first_assistant_response_text := _text;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER = """
CREATE TRIGGER trg_extract_first_assistant_response
  BEFORE INSERT OR UPDATE OF request_body, response_body
  ON proxy_requests
  FOR EACH ROW
  EXECUTE FUNCTION fn_extract_first_assistant_response();
"""

BACKFILL = """
UPDATE proxy_requests SET
  first_assistant_response_text = COALESCE(
    (
      SELECT m->>'content'
      FROM jsonb_array_elements(request_body->'messages') AS m
      WHERE m->>'role' = 'assistant'
      LIMIT 1
    ),
    response_body->'choices'->0->'message'->>'content'
  )
WHERE (
  (request_body IS NOT NULL
   AND jsonb_typeof(request_body->'messages') = 'array'
   AND jsonb_array_length(request_body->'messages') > 0)
  OR
  (response_body IS NOT NULL
   AND jsonb_typeof(response_body->'choices') = 'array'
   AND jsonb_array_length(response_body->'choices') > 0)
);
"""


def upgrade() -> None:
    op.add_column("proxy_requests", sa.Column("first_assistant_response_text", sa.Text(), nullable=True))

    op.execute(TRIGGER_FUNCTION)
    op.execute(TRIGGER)
    op.execute(BACKFILL)

    op.create_index(
        "ix_proxy_requests_first_assistant_response_text",
        "proxy_requests",
        ["first_assistant_response_text"],
        postgresql_using="hash",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proxy_requests_first_assistant_response_text",
        table_name="proxy_requests",
        postgresql_using="hash",
    )
    op.execute("DROP TRIGGER IF EXISTS trg_extract_first_assistant_response ON proxy_requests;")
    op.execute("DROP FUNCTION IF EXISTS fn_extract_first_assistant_response();")
    op.drop_column("proxy_requests", "first_assistant_response_text")
