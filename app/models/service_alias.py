from sqlalchemy import ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ServiceAlias(BaseModel):
    __tablename__ = "service_aliases"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "service_id"], ["services.site_id", "services.id"]),
        Index(None, "site_id", "normalized_alias"),
    )

    site_id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(primary_key=True)
    normalized_alias: Mapped[str] = mapped_column(String(160), primary_key=True)
    alias: Mapped[str] = mapped_column(String(160))
