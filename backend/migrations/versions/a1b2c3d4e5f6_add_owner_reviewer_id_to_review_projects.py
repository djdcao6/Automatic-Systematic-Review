"""add owner reviewer id to review projects

Revision ID: a1b2c3d4e5f6
Revises: 459dac2d0fa4
Create Date: 2026-09-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '459dac2d0fa4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'review_projects',
        sa.Column('owner_reviewer_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'review_projects_owner_reviewer_id_fkey',
        'review_projects',
        'reviewers',
        ['owner_reviewer_id'],
        ['id'],
    )
    # No pre-existing Review Projects have an owner to backfill (greenfield,
    # per issue #24), so this only needs to reject new rows going forward.
    op.alter_column('review_projects', 'owner_reviewer_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'review_projects_owner_reviewer_id_fkey', 'review_projects', type_='foreignkey'
    )
    op.drop_column('review_projects', 'owner_reviewer_id')
