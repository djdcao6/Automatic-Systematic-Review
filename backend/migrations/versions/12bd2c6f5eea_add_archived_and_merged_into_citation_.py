"""add archived and merged_into_citation_id to citations

Revision ID: 12bd2c6f5eea
Revises: 66058cec4263
Create Date: 2026-09-14 22:25:35.895749

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '12bd2c6f5eea'
down_revision: str | Sequence[str] | None = '66058cec4263'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'citations',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column('citations', 'archived', server_default=None)
    op.add_column(
        'citations', sa.Column('merged_into_citation_id', sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        'citations_merged_into_citation_id_fkey',
        'citations',
        'citations',
        ['merged_into_citation_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'citations_merged_into_citation_id_fkey', 'citations', type_='foreignkey'
    )
    op.drop_column('citations', 'merged_into_citation_id')
    op.drop_column('citations', 'archived')
