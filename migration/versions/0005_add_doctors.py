"""Add doctors who see patients in a room."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "doctors",
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["site_id", "room_id"], ["rooms.site_id", "rooms.id"],
            name=op.f("fk_doctors_site_id_room_id_rooms"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctors")),
        sa.UniqueConstraint("site_id", "code", name=op.f("uq_doctors_site_id_code")),
    )
    op.create_index(op.f("ix_doctors_site_id_normalized_name"), "doctors", ["site_id", "normalized_name"])
    op.create_index(op.f("ix_doctors_site_id_room_id"), "doctors", ["site_id", "room_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_doctors_site_id_room_id"), table_name="doctors")
    op.drop_index(op.f("ix_doctors_site_id_normalized_name"), table_name="doctors")
    op.drop_table("doctors")
