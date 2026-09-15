"""add original_source to citations

Revision ID: 892fbdb69aff
Revises: 4935bb86e77a
Create Date: 2026-09-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '892fbdb69aff'
down_revision: str | Sequence[str] | None = '4935bb86e77a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'citations',
        sa.Column(
            'original_source',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
        ),
    )
    # Backfills from the live `source` column -- the closest available
    # approximation for rows created before this migration, since their
    # true pre-merge source was never separately recorded.
    op.execute('UPDATE citations SET original_source = source')
    op.alter_column('citations', 'original_source', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('citations', 'original_source')
