from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class Building(SiteRecord):
    __tablename__ = "buildings"
    __table_args__ = (
        ForeignKeyConstraint(["site_id"], ["hospital_sites.id"]),
        UniqueConstraint("site_id", "id"),
        UniqueConstraint("site_id", "code"),
    )

    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
