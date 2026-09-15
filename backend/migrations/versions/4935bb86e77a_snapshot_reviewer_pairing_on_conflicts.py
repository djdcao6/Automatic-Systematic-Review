"""snapshot reviewer pairing on conflicts

Revision ID: 4935bb86e77a
Revises: 07c75a5d76c6
Create Date: 2026-09-15 09:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4935bb86e77a'
down_revision: str | Sequence[str] | None = '07c75a5d76c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conflicts', sa.Column('owner_reviewer_id', sa.Uuid(), nullable=True))
    op.add_column('conflicts', sa.Column('co_reviewer_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'conflicts_owner_reviewer_id_fkey', 'conflicts', 'reviewers', ['owner_reviewer_id'], ['id']
    )
    op.create_foreign_key(
        'conflicts_co_reviewer_id_fkey', 'conflicts', 'reviewers', ['co_reviewer_id'], ['id']
    )
    # Backfills from each Conflict's Review Project -- correct for every
    # existing row, since removal (#29) didn't exist before this migration,
    # so no Conflict yet predates a Co-Reviewer change.
    op.execute(
        """
        UPDATE conflicts
        SET owner_reviewer_id = review_projects.owner_reviewer_id,
            co_reviewer_id = review_projects.co_reviewer_id
        FROM review_projects
        WHERE conflicts.review_project_id = review_projects.id
        """
    )
    op.alter_column('conflicts', 'owner_reviewer_id', nullable=False)
    op.alter_column('conflicts', 'co_reviewer_id', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('conflicts_co_reviewer_id_fkey', 'conflicts', type_='foreignkey')
    op.drop_constraint('conflicts_owner_reviewer_id_fkey', 'conflicts', type_='foreignkey')
    op.drop_column('conflicts', 'co_reviewer_id')
    op.drop_column('conflicts', 'owner_reviewer_id')
