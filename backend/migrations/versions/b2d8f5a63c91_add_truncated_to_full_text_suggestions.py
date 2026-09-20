"""add truncated to full text suggestions

Revision ID: b2d8f5a63c91
Revises: e4b7c2d9a1f6
Create Date: 2026-09-20 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2d8f5a63c91'
down_revision: str | Sequence[str] | None = 'e4b7c2d9a1f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Suggestions saved before the cap existed were generated from the whole text.
    op.add_column(
        'full_text_suggestions',
        sa.Column('truncated', sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('full_text_suggestions', 'truncated')
