"""Tiny column-adding migration helper.

This codebase has no Alembic - `Base.metadata.create_all()` (called at startup) only creates
tables that don't exist yet, it never alters an existing table to add a new column. Any model
change that adds a column to an already-existing table needs an explicit, idempotent
ALTER TABLE, or an existing database (like local dev's smoke.db) would crash on the first
query that references the new column. Mirrors the "never wipe the DB for a config/schema
correction" philosophy already used by `seed_and_sync()`'s upsert-by-slug.
"""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text


def ensure_column(engine: Engine, table: str, column: str, ddl_type: str) -> None:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return  # table doesn't exist yet - create_all() will create it with every column
    existing = {c["name"] for c in inspector.get_columns(table)}
    if column in existing:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
