from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    severity: Mapped[str] = mapped_column(String(20))  # info|warning|red|emergency
    event_type: Mapped[str] = mapped_column(String(60))
    cluster: Mapped[str] = mapped_column(String(60), default="")
    indicator_ids: Mapped[list] = mapped_column(JSON, default=list)
    headline: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(10), default="negative")  # positive|negative - equity-market impact
    equity_implication: Mapped[str] = mapped_column(Text, default="")
    headline_zh: Mapped[str] = mapped_column(String(300), default="")
    summary_zh: Mapped[str] = mapped_column(Text, default="")
    equity_implication_zh: Mapped[str] = mapped_column(Text, default="")
    source_urls: Mapped[list] = mapped_column(JSON, default=list)
    dedupe_key: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class FeedItem(Base):
    __tablename__ = "feed_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    category: Mapped[str] = mapped_column(String(40))
    category_zh: Mapped[str] = mapped_column(String(40), default="")
    headline: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text)
    headline_zh: Mapped[str] = mapped_column(String(300), default="")
    summary_zh: Mapped[str] = mapped_column(Text, default="")
    related_alert_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
