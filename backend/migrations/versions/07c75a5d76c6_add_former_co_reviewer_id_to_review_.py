"""add former_co_reviewer_id to review projects

Revision ID: 07c75a5d76c6
Revises: 7faccd2378bd
Create Date: 2026-09-15 08:30:50.701155

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '07c75a5d76c6'
down_revision: str | Sequence[str] | None = '7faccd2378bd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'review_projects',
        sa.Column('former_co_reviewer_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'review_projects_former_co_reviewer_id_fkey',
        'review_projects',
        'reviewers',
        ['former_co_reviewer_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'review_projects_former_co_reviewer_id_fkey', 'review_projects', type_='foreignkey'
    )
    op.drop_column('review_projects', 'former_co_reviewer_id')
