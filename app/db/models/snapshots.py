from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    us_equity_score: Mapped[float] = mapped_column(Float)
    us_macro_score: Mapped[float] = mapped_column(Float)
    global_score: Mapped[float] = mapped_column(Float)
    liquidity_score: Mapped[float] = mapped_column(Float)
    credit_score: Mapped[float] = mapped_column(Float)
    ai_funding_score: Mapped[float] = mapped_column(Float)
    valuation_score: Mapped[float] = mapped_column(Float)
    equity_internals_score: Mapped[float] = mapped_column(Float, default=0.0)
    fear_greed_index: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0-100, Section 12
    overall_status: Mapped[str] = mapped_column(String(20))  # Healthy|Caution|Warning|Emergency
    algorithm_version: Mapped[str] = mapped_column(String(20), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
