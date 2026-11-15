from sqlalchemy import Boolean, ForeignKeyConstraint, Index, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ServiceLocation(BaseModel):
    __tablename__ = "service_locations"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "service_id"], ["services.site_id", "services.id"]),
        ForeignKeyConstraint(["site_id", "room_id"], ["rooms.site_id", "rooms.id"]),
        Index(None, "site_id", "room_id"),
    )

    site_id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(primary_key=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
