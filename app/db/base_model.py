"""Import all mapped tables and expose metadata for Alembic."""

import app.models  # noqa: F401 -- register tables on Base.metadata
from app.db.base import Base

target_metadata = Base.metadata
