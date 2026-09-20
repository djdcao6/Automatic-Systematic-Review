"""unique active extraction field names

Revision ID: e4b7c2d9a1f6
Revises: c7e1a94d2f30
Create Date: 2026-09-20 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4b7c2d9a1f6'
down_revision: str | Sequence[str] | None = 'c7e1a94d2f30'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = 'uq_extraction_fields_active_name'


def upgrade() -> None:
    """Upgrade schema."""
    # Names match ignoring case and surrounding whitespace, as in the index below.
    duplicates = op.get_bind().execute(
        sa.text(
            "SELECT review_project_id, array_agg(name ORDER BY created_at) AS names "
            "FROM extraction_fields WHERE NOT archived "
            "GROUP BY review_project_id, lower(btrim(name)) HAVING count(*) > 1 "
            "ORDER BY review_project_id, min(created_at)"
        )
    ).all()
    if duplicates:
        # Refuse before touching anything, with the list, rather than let the index
        # build fail partway with an error that names one row.
        listing = "\n".join(
            f"  Review Project {project_id}: " + ", ".join(repr(name) for name in names)
            for project_id, names in duplicates
        )
        raise RuntimeError(
            "Cannot make active Extraction Field names unique: these Review Projects have "
            "active fields whose names match, ignoring case and surrounding spaces. Rename "
            "or archive all but one of each group, then run the migration again.\n" + listing
        )
    op.create_index(
        INDEX_NAME,
        'extraction_fields',
        ['review_project_id', sa.text('lower(btrim(name))')],
        unique=True,
        postgresql_where=sa.text('NOT archived'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(INDEX_NAME, table_name='extraction_fields')
