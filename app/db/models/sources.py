from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    base_url: Mapped[str] = mapped_column(String(500))
    provider_type: Mapped[str] = mapped_column(String(50))  # official | free_public | paid
    requires_api_key: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit: Mapped[str | None] = mapped_column(String(100), nullable=True)
    license_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commercial_display_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
