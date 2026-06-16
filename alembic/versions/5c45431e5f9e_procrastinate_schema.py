"""procrastinate schema

Revision ID: 5c45431e5f9e
Revises: 435e3987290d
Create Date: 2026-06-15 12:02:23.994202

Installs the Procrastinate job-queue schema (the broker lives in Postgres).
"""
from collections.abc import Sequence

from procrastinate.schema import SchemaManager

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5c45431e5f9e'
down_revision: str | None = '435e3987290d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(SchemaManager.get_schema())


def downgrade() -> None:
    # Tear down the Procrastinate objects (tables, types, functions) this schema
    # created. Cascade because the functions/triggers depend on the tables.
    op.execute("DROP SCHEMA IF EXISTS procrastinate CASCADE")
    for table in (
        "procrastinate_events",
        "procrastinate_periodic_defers",
        "procrastinate_jobs",
        "procrastinate_workers",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_status CASCADE")
    op.execute("DROP TYPE IF EXISTS procrastinate_job_event_type CASCADE")
