"""create search terms table

Revision ID: 6666bde34b60
Revises: 892fbdb69aff
Create Date: 2026-09-15 21:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6666bde34b60'
down_revision: str | Sequence[str] | None = '892fbdb69aff'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('search_terms',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('review_project_id', sa.Uuid(), nullable=False),
    sa.Column('population_terms', postgresql.ARRAY(sa.String()), nullable=False),
    sa.Column('intervention_terms', postgresql.ARRAY(sa.String()), nullable=False),
    sa.Column('comparison_terms', postgresql.ARRAY(sa.String()), nullable=False),
    sa.Column('outcome_terms', postgresql.ARRAY(sa.String()), nullable=False),
    sa.ForeignKeyConstraint(['review_project_id'], ['review_projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('review_project_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('search_terms')
