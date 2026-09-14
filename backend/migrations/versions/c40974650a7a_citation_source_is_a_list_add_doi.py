"""citation source is a list, add doi

Revision ID: c40974650a7a
Revises: 29779a714e20
Create Date: 2026-09-14 19:30:38.504548

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c40974650a7a'
down_revision: str | Sequence[str] | None = '29779a714e20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('citations', sa.Column('doi', sa.String(), nullable=True))
    op.alter_column(
        'citations',
        'source',
        existing_type=sa.String(),
        type_=postgresql.ARRAY(sa.String()),
        nullable=False,
        postgresql_using="CASE WHEN source IS NULL THEN ARRAY[]::varchar[] ELSE ARRAY[source] END",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'citations',
        'source',
        existing_type=postgresql.ARRAY(sa.String()),
        type_=sa.String(),
        nullable=True,
        postgresql_using="array_to_string(source, '; ')",
    )
    op.drop_column('citations', 'doi')
