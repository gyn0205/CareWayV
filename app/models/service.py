from sqlalchemy import ForeignKeyConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class Service(SiteRecord):
    __tablename__ = "services"
    __table_args__ = (
        ForeignKeyConstraint(["site_id"], ["hospital_sites.id"]),
        UniqueConstraint("site_id", "id"),
        UniqueConstraint("site_id", "code"),
        Index(None, "site_id", "normalized_name"),
    )

    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(160))
