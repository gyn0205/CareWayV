from sqlalchemy import CheckConstraint, Float, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class NavigationNode(SiteRecord):
    __tablename__ = "navigation_nodes"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "floor_id"], ["floors.site_id", "floors.id"]),
        UniqueConstraint("site_id", "id"),
        UniqueConstraint("site_id", "floor_id", "code"),
        CheckConstraint(
            "(x IS NULL AND y IS NULL) OR "
            "(x IS NOT NULL AND y IS NOT NULL AND x BETWEEN 0 AND 1 AND y BETWEEN 0 AND 1)",
            name="map_coordinates",
        ),
    )

    floor_id: Mapped[int]
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str | None] = mapped_column(String(160))
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
