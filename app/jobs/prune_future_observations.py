"""Remove observation dates ahead of America/Los_Angeles today (UTC clock drift).

Render runs in UTC. Mock connectors used to end series at date.today(), so after 17:00 PT
they wrote a calendar day that is still "tomorrow" in PT. The "Updated today" badge
compares observation_date to today_pt and therefore showed nothing.

Usage (from backend/ with DATABASE_URL pointing at the target DB):
  python -m app.jobs.prune_future_observations
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.timeutil import today_pt


def prune_future_observations() -> dict[str, int | str]:
    as_of = today_pt()
    with engine.begin() as conn:
        score_n = conn.execute(
            text(
                """
                DELETE FROM indicator_scores
                WHERE observation_id IN (
                  SELECT id FROM indicator_observations WHERE observation_date > :d
                )
                """
            ),
            {"d": as_of},
        ).rowcount or 0
        obs_n = conn.execute(
            text("DELETE FROM indicator_observations WHERE observation_date > :d"),
            {"d": as_of},
        ).rowcount or 0
        snap_n = conn.execute(
            text("DELETE FROM market_snapshots WHERE snapshot_date > :d"),
            {"d": as_of},
        ).rowcount or 0
        feed_n = conn.execute(
            text("DELETE FROM feed_items WHERE date > :d"),
            {"d": as_of},
        ).rowcount or 0
        fund_n = conn.execute(
            text("DELETE FROM company_funding_scores WHERE date > :d"),
            {"d": as_of},
        ).rowcount or 0
    return {
        "as_of": as_of.isoformat(),
        "indicator_scores": score_n,
        "indicator_observations": obs_n,
        "market_snapshots": snap_n,
        "feed_items": feed_n,
        "company_funding_scores": fund_n,
    }


def main() -> None:
    SessionLocal()
    counts = prune_future_observations()
    print(f"Pruned rows with dates after PT today ({counts['as_of']}):")
    for k, n in counts.items():
        if k == "as_of":
            continue
        print(f"  {k}: {n}")


if __name__ == "__main__":
    main()
