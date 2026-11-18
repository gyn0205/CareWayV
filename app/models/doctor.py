from sqlalchemy import Boolean, ForeignKeyConstraint, Index, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SiteRecord


class Doctor(SiteRecord):
    """Bác sĩ khám tại một phòng; tên có thể trùng nên định danh bằng mã."""

    __tablename__ = "doctors"
    __table_args__ = (
        ForeignKeyConstraint(["site_id", "room_id"], ["rooms.site_id", "rooms.id"]),
        UniqueConstraint("site_id", "code"),
        # Tra theo tên đã bỏ dấu (khách nói "bác sĩ Nguyễn Văn An").
        Index(None, "site_id", "normalized_name"),
        Index(None, "site_id", "room_id"),
    )

    room_id: Mapped[int]
    code: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    normalized_name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=true())
