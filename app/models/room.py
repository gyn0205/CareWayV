from sqlalchemy import Boolean, ForeignKeyConstraint, Index, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class Room(SiteRecord):
    __tablename__ = "rooms"
    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "entrance_node_id"], ["navigation_nodes.site_id", "navigation_nodes.id"]
        ),
        ForeignKeyConstraint(["site_id", "department_id"], ["departments.site_id", "departments.id"]),
        UniqueConstraint("site_id", "id"),
        UniqueConstraint("site_id", "code"),
        Index(None, "site_id", "entrance_node_id"),
        Index(None, "site_id", "department_id"),
    )

    entrance_node_id: Mapped[int]
    department_id: Mapped[int | None]
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
