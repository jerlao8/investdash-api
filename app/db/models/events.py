from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CrisisEvent(Base):
    """Historical crisis/recession events used by the simplified backtesting page (Section 41)."""

    __tablename__ = "crisis_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    event_start: Mapped[date] = mapped_column(Date)
    event_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    peak_to_trough_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    recession_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    recession_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    pre_event_window_days: Mapped[int] = mapped_column(Integer, default=180)
    description: Mapped[str] = mapped_column(Text, default="")
    name_zh: Mapped[str] = mapped_column(String(120), default="")
    description_zh: Mapped[str] = mapped_column(Text, default="")
