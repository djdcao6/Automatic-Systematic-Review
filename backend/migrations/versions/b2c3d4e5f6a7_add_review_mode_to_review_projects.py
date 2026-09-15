"""add review mode to review projects

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: str | Sequence[str] | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'review_projects',
        sa.Column('review_mode', sa.String(), nullable=False, server_default='solo'),
    )
    op.alter_column('review_projects', 'review_mode', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('review_projects', 'review_mode')
