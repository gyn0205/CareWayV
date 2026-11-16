"""Add a room description for wayfinding details."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rooms", "description")
