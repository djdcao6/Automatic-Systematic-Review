"""create subscriptions table

Revision ID: a3f7c9d2b1e4
Revises: 6666bde34b60
Create Date: 2026-09-15 22:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f7c9d2b1e4'
down_revision: str | Sequence[str] | None = '6666bde34b60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('reviewer_id', sa.Uuid(), nullable=False),
        sa.Column('stripe_customer_id', sa.String(), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reviewer_id'], ['reviewers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reviewer_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('subscriptions')
