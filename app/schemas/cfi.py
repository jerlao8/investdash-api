from __future__ import annotations

from pydantic import BaseModel


class CfiCompanyOut(BaseModel):
    ticker: str
    name: str
    health: float
    capex_latest: float
    capex_qoq_growth_pct: float
    fcf_latest: float | None
    as_of: str


class CfiTrackedCompanyOut(BaseModel):
    """Which companies a lock's company_count refers to - populated for every lock,
    independent of whether that lock has a per-company score (only L6 does; L3's health is
    one macro-level credit-spread proxy shared across all of its tracked companies, not an
    individual score per company)."""

    ticker: str
    name: str
    cfi_role: str


class CfiLockOut(BaseModel):
    lock_id: str
    name: str
    weight: float
    company_count: int
    coverage: float
    health: float | None
    damage: float | None
    breadth: float | None
    legitimacy: float | None = None
    idiosyncratic: bool | None = None
    companies: list[CfiCompanyOut] = []
    tracked_companies: list[CfiTrackedCompanyOut] = []


class CfiOverviewOut(BaseModel):
    cfi: float
    state: str
    demand_gate_active: bool
    note: str
    locks: list[CfiLockOut]


class CfiSnapshotOut(BaseModel):
    snapshot_date: str
    cfi: float
    state: str
