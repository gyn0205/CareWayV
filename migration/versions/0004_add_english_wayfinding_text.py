"""Add English labels and directions alongside the primary wayfinding text."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("departments", sa.Column("name_en", sa.String(length=160), nullable=True))
    op.add_column("navigation_edges", sa.Column("instruction_en", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("navigation_edges", "instruction_en")
    op.drop_column("departments", "name_en")
