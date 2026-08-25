"""Clear scored/ingested time-series so mock data can be rebuilt at the correct frequency.

Usage (from backend/ with venv active):
  python -m app.jobs.clear_observations
"""
from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal, engine


# Order matters for FKs: scores reference observations.
TABLES = (
    "indicator_scores",
    "indicator_observations",
    "market_snapshots",
    "alert_events",
    "feed_items",
    "company_funding_scores",
)


def clear_observations() -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        for table in TABLES:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = int(result.scalar() or 0)
            conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
    return counts


def main() -> None:
    # Touch SessionLocal so settings/engine are loaded the same way as the app.
    SessionLocal()
    before = clear_observations()
    print("Cleared observation-derived tables:")
    for table, n in before.items():
        print(f"  {table}: {n} rows removed")


if __name__ == "__main__":
    main()
