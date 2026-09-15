"""screening decision one-per-(citation, reviewer)

Revision ID: 65c162183027
Revises: 682c16b926f7
Create Date: 2026-09-15 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '65c162183027'
down_revision: str | Sequence[str] | None = '682c16b926f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'screening_decisions',
        sa.Column('reviewer_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'screening_decisions_reviewer_id_fkey',
        'screening_decisions',
        'reviewers',
        ['reviewer_id'],
        ['id'],
    )
    # No pre-existing Screening Decisions to backfill (greenfield, per #24's
    # precedent), so this only needs to reject new rows going forward.
    op.alter_column('screening_decisions', 'reviewer_id', nullable=False)
    op.drop_constraint(
        'screening_decisions_citation_id_key', 'screening_decisions', type_='unique'
    )
    op.create_unique_constraint(
        'uq_screening_decisions_citation_id_reviewer_id',
        'screening_decisions',
        ['citation_id', 'reviewer_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_screening_decisions_citation_id_reviewer_id',
        'screening_decisions',
        type_='unique',
    )
    op.create_unique_constraint(
        'screening_decisions_citation_id_key', 'screening_decisions', ['citation_id']
    )
    op.drop_constraint(
        'screening_decisions_reviewer_id_fkey', 'screening_decisions', type_='foreignkey'
    )
    op.drop_column('screening_decisions', 'reviewer_id')
