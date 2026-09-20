"""add model to ai_suggestions and full_text_suggestions

Revision ID: f3c6a9e17d48
Revises: d5a1e8c47b02
Create Date: 2026-09-20 16:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3c6a9e17d48'
down_revision: str | Sequence[str] | None = 'd5a1e8c47b02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ('ai_suggestions', 'full_text_suggestions')


def upgrade() -> None:
    """Upgrade schema."""
    for table in _TABLES:
        # The model behind a suggestion saved before this column existed cannot be
        # confirmed, so those rows say so. The default is dropped straight after, so
        # every new row has to name its model instead of inheriting "unknown".
        op.add_column(
            table,
            sa.Column('model', sa.String(), server_default='unknown', nullable=False),
        )
        op.alter_column(table, 'model', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TABLES:
        op.drop_column(table, 'model')
