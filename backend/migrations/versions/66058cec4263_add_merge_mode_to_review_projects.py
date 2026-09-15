"""add merge mode to review projects

Revision ID: 66058cec4263
Revises: c40974650a7a
Create Date: 2026-09-14 20:17:18.852277

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '66058cec4263'
down_revision: str | Sequence[str] | None = 'c40974650a7a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'review_projects',
        sa.Column('merge_mode', sa.String(), nullable=False, server_default='combine'),
    )
    op.alter_column('review_projects', 'merge_mode', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('review_projects', 'merge_mode')
