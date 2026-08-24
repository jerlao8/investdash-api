from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class IndicatorDefinition(Base):
    __tablename__ = "indicator_definitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    connector_key: Mapped[str] = mapped_column(String(30))  # key into app.connectors.CONNECTOR_REGISTRY
    series_identifier: Mapped[str] = mapped_column(String(120))
    frequency: Mapped[str] = mapped_column(String(20))  # daily|weekly|monthly|quarterly
    units: Mapped[str] = mapped_column(String(50))
    health_polarity: Mapped[str] = mapped_column(String(20))  # higher_is_healthy|lower_is_healthy|custom
    scoring_method: Mapped[str] = mapped_column(String(50), default="percentile_default")
    importance_weight: Mapped[float] = mapped_column(Float, default=1.0)
    cluster: Mapped[str] = mapped_column(String(60), index=True)
    lead_lag: Mapped[str] = mapped_column(String(20), default="coincident")
    crisis_relevance: Mapped[str] = mapped_column(String(10), default="medium")
    info_text: Mapped[str] = mapped_column(Text, default="")
    reading_guide: Mapped[str] = mapped_column(Text, default="")
    name_zh: Mapped[str] = mapped_column(String(200), default="")
    info_text_zh: Mapped[str] = mapped_column(Text, default="")
    reading_guide_zh: Mapped[str] = mapped_column(Text, default="")
    source_url: Mapped[str] = mapped_column(String(500), default="")
    source_name: Mapped[str] = mapped_column(String(80), default="")
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    green_threshold: Mapped[float] = mapped_column(Float, default=70.0)
    yellow_threshold: Mapped[float] = mapped_column(Float, default=40.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class IndicatorObservation(Base):
    __tablename__ = "indicator_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator_definitions.id"), index=True)
    observation_date: Mapped[date] = mapped_column(Date, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    value: Mapped[float] = mapped_column(Float)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    revision_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    vintage_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), default="")
    raw_payload_hash: Mapped[str] = mapped_column(String(64), default="")
    is_preliminary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_revision: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IndicatorScore(Base):
    __tablename__ = "indicator_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator_definitions.id"), index=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("indicator_observations.id"))
    health_score_0_100: Mapped[float] = mapped_column(Float)
    stress_percentile: Mapped[float] = mapped_column(Float)
    z_score: Mapped[float] = mapped_column(Float)
    velocity_score: Mapped[float] = mapped_column(Float)
    persistence_score: Mapped[float] = mapped_column(Float)
    color_state: Mapped[str] = mapped_column(String(10))  # green|yellow|red|gray
    direction: Mapped[str] = mapped_column(String(10))  # positive|negative|flat - health-oriented, drives color
    raw_trend: Mapped[str] = mapped_column(String(10), default="flat")  # up|down|flat - literal movement, drives arrow shape
    confidence: Mapped[float] = mapped_column(Float, default=100.0)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    algorithm_version: Mapped[str] = mapped_column(String(20), default="v1")
