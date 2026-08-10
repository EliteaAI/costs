"""CostsSetting — single-row plugin settings in the shared schema.

Holds the admin-selected active price source so the daily cron and the manual
re-import both follow the same choice. One row (id=1) is expected.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from tools import db, config as c


class CostsSetting(db.Base):
    __tablename__ = 'costs_settings'
    __table_args__ = ({'schema': c.POSTGRES_SCHEMA},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_source_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
