"""add invited_only to reviewers

Revision ID: c7e1a94d2f30
Revises: a3f7c9d2b1e4
Create Date: 2026-09-20 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7e1a94d2f30'
down_revision: str | Sequence[str] | None = 'a3f7c9d2b1e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'reviewers',
        sa.Column('invited_only', sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reviewers', 'invited_only')
