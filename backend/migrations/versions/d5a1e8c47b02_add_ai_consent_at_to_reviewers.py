"""add ai_consent_at to reviewers

Revision ID: d5a1e8c47b02
Revises: b2d8f5a63c91
Create Date: 2026-09-20 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5a1e8c47b02'
down_revision: str | Sequence[str] | None = 'b2d8f5a63c91'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Null for every existing account: none of them has been shown the notice.
    op.add_column(
        'reviewers',
        sa.Column('ai_consent_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reviewers', 'ai_consent_at')
