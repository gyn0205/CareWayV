from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Index, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class NavigationEdge(BaseModel):
    __tablename__ = "navigation_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "from_node_id"], ["navigation_nodes.site_id", "navigation_nodes.id"]
        ),
        ForeignKeyConstraint(
            ["site_id", "to_node_id"], ["navigation_nodes.site_id", "navigation_nodes.id"]
        ),
        Index(None, "site_id", "to_node_id"),
        CheckConstraint("from_node_id <> to_node_id", name="distinct_nodes"),
        CheckConstraint("cost_seconds > 0", name="positive_cost"),
        CheckConstraint("kind IN ('walk', 'stairs', 'elevator')", name="valid_kind"),
        CheckConstraint(
            "kind <> 'stairs' OR NOT wheelchair_accessible", name="stairs_accessibility"
        ),
    )

    site_id: Mapped[int] = mapped_column(primary_key=True)
    from_node_id: Mapped[int] = mapped_column(primary_key=True)
    to_node_id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    cost_seconds: Mapped[int]
    wheelchair_accessible: Mapped[bool]
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
    instruction: Mapped[str | None] = mapped_column(Text)
    instruction_en: Mapped[str | None] = mapped_column(Text)
