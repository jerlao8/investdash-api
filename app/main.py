from __future__ import annotations

import logging
import threading

from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_current_user, require_admin
from app.api.routes import admin, auth, backtest, companies, favorites, feed, health, indicators, summary, system
from app.config import get_settings
from app.db import models  # noqa: F401 - ensures all models are registered on Base.metadata
from app.db.migrate import ensure_column
from app.db.session import Base, engine
from app.jobs.scheduler import create_scheduler, run_catchup_if_needed


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


# Naive DB datetimes are UTC — emit them with a Z so clients convert to local time correctly.
ENCODERS_BY_TYPE[datetime] = _utc_iso

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("investdash")

settings = get_settings()
app = FastAPI(title="InvestDash API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(indicators.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(favorites.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(feed.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(companies.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(admin.router, prefix="/api", dependencies=[Depends(require_admin)])
app.include_router(system.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(backtest.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(summary.router, prefix="/api", dependencies=[Depends(get_current_user)])

_scheduler = None


_NEW_COLUMNS = [
    ("users", "language", "VARCHAR(10) DEFAULT 'en'"),
    ("users", "language_confirmed", "BOOLEAN DEFAULT FALSE"),
    ("users", "collapsed_sections", "TEXT DEFAULT '[]'"),
    ("indicator_definitions", "name_zh", "VARCHAR(200) DEFAULT ''"),
    ("indicator_definitions", "info_text_zh", "TEXT DEFAULT ''"),
    ("indicator_definitions", "reading_guide_zh", "TEXT DEFAULT ''"),
    ("alert_events", "headline_zh", "VARCHAR(300) DEFAULT ''"),
    ("alert_events", "summary_zh", "TEXT DEFAULT ''"),
    ("alert_events", "equity_implication_zh", "TEXT DEFAULT ''"),
    ("feed_items", "category_zh", "VARCHAR(40) DEFAULT ''"),
    ("feed_items", "headline_zh", "VARCHAR(300) DEFAULT ''"),
    ("feed_items", "summary_zh", "TEXT DEFAULT ''"),
    ("crisis_events", "name_zh", "VARCHAR(120) DEFAULT ''"),
    ("crisis_events", "description_zh", "TEXT DEFAULT ''"),
]


def _run_wake_catchup() -> None:
    """If the host slept through a cron slot, run the pipeline once on wake."""
    run_catchup_if_needed()


@app.on_event("startup")
def on_startup() -> None:
    global _scheduler
    for table, column, ddl_type in _NEW_COLUMNS:
        ensure_column(engine, table, column, ddl_type)
    Base.metadata.create_all(bind=engine)

    # Do not block uvicorn readiness / Render port detection on the full pipeline.
    threading.Thread(target=_run_wake_catchup, name="wake-catchup", daemon=True).start()

    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("scheduler started (mode=%s)", settings.data_source_mode)


@app.on_event("shutdown")
def on_shutdown() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)


@app.get("/api/ping")
def ping() -> dict:
    return {"status": "ok"}
