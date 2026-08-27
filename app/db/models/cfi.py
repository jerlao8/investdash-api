from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class CfiSnapshot(Base):
    """One row per pipeline run - the Capex Freeze Index and its lock-level breakdown,
    computed fresh each time from Company/CompanyMetric/IndicatorObservation (nothing here
    is itself a primary data store, it's the scored output). Kept so the UI can show a
    history sparkline without recomputing on every request."""

    __tablename__ = "cfi_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    cfi: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(30))
    lock_health_json: Mapped[str] = mapped_column(Text)  # {lock_id: health}
    lock_damage_json: Mapped[str] = mapped_column(Text)  # {lock_id: damage}
    lock_legitimacy_json: Mapped[str] = mapped_column(Text)  # {lock_id: legitimacy}
    lock_breadth_json: Mapped[str] = mapped_column(Text)  # {lock_id: breadth}
    lock_coverage_json: Mapped[str] = mapped_column(Text)  # {lock_id: fraction of companies scored}
    drivers_json: Mapped[str] = mapped_column(Text, default="[]")
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
