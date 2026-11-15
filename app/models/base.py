"""Shared audit fields and soft-delete behavior for mapped records."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_easy_softdelete.mixin import generate_soft_delete_mixin_class

from app.db.base import Base


class SoftDeleteMixin(generate_soft_delete_mixin_class()):  # type: ignore[misc]
    deleted_at: Mapped[datetime | None]

    def soft_delete(self) -> None:
        if self.deleted_at is None:
            self.delete()

    def restore(self) -> None:
        self.undelete()


class BaseModel(SoftDeleteMixin, Base):
    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SiteRecord(BaseModel):
    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)
    site_id: Mapped[int]
