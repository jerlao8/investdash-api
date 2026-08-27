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
