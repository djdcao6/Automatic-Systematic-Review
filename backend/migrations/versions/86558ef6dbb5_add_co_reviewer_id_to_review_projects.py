"""add co_reviewer_id to review projects

Revision ID: 86558ef6dbb5
Revises: b2c3d4e5f6a7
Create Date: 2026-09-15 05:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '86558ef6dbb5'
down_revision: str | Sequence[str] | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'review_projects',
        sa.Column('co_reviewer_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'review_projects_co_reviewer_id_fkey',
        'review_projects',
        'reviewers',
        ['co_reviewer_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'review_projects_co_reviewer_id_fkey', 'review_projects', type_='foreignkey'
    )
    op.drop_column('review_projects', 'co_reviewer_id')
