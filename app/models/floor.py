from sqlalchemy import ForeignKeyConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class Floor(SiteRecord):
    __tablename__ = "floors"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "building_id"], ["buildings.site_id", "buildings.id"]),
        UniqueConstraint("site_id", "id"),
        UniqueConstraint("site_id", "building_id", "level"),
    )

    building_id: Mapped[int]
    level: Mapped[int]
    label: Mapped[str] = mapped_column(String(40))
    map_asset_url: Mapped[str | None] = mapped_column(Text)
