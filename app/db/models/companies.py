from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    cik: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sector: Mapped[str] = mapped_column(String(80))
    subsector: Mapped[str] = mapped_column(String(80), default="")
    tier: Mapped[str] = mapped_column(String(60))  # compute_semis|networking_infra|hyperscalers|higher_risk_infra
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Capex Freeze Monitor fields - additive and independent of the AI Company Monitor fields
    # above. lock_id is null for companies seeded only for the AI Company Monitor.
    lock_id: Mapped[str | None] = mapped_column(String(4), nullable=True, index=True)  # L1..L6
    cfi_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1|2|3, drives weight
    cfi_role: Mapped[str] = mapped_column(String(120), default="")


class CompanyMetric(Base):
    __tablename__ = "company_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    metric_name: Mapped[str] = mapped_column(String(80), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(30), default="USD_millions")
    source_filing_url: Mapped[str] = mapped_column(String(500), default="")
    source_accession: Mapped[str | None] = mapped_column(String(60), nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(30), default="mock")  # xbrl|filing_text|llm|manual|mock
    confidence: Mapped[float] = mapped_column(Float, default=100.0)
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)


class CompanyFundingScore(Base):
    __tablename__ = "company_funding_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    liquidity_score: Mapped[float] = mapped_column(Float)
    debt_score: Mapped[float] = mapped_column(Float)
    fcf_score: Mapped[float] = mapped_column(Float)
    capex_score: Mapped[float] = mapped_column(Float)
    maturity_score: Mapped[float] = mapped_column(Float)
    funding_gap: Mapped[float] = mapped_column(Float)
    funding_gap_score: Mapped[float] = mapped_column(Float, default=5.0)
    overall_score: Mapped[float] = mapped_column(Float)
