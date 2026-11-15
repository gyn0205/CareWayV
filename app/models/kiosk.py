from sqlalchemy import Boolean, ForeignKeyConstraint, Index, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class Kiosk(SiteRecord):
    __tablename__ = "kiosks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["site_id", "origin_node_id"], ["navigation_nodes.site_id", "navigation_nodes.id"]
        ),
        UniqueConstraint("site_id", "code"),
        Index(None, "site_id", "origin_node_id"),
    )

    origin_node_id: Mapped[int]
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
