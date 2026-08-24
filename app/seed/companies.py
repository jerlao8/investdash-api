"""AI/semiconductor company universe seed (PRD Section 24) with mock balance-sheet
profiles (Section 25) used to compute funding scores (Section 26). A handful of companies
carry real SEC CIKs so the SEC connector can demonstrate a real company-facts fetch
(Section 48's full extraction pipeline is out of scope; this is the deterministic-XBRL
proof-of-concept only).

All $ figures are USD millions.
"""

from __future__ import annotations

from typing import Any

# name, ticker, cik(10-digit, may be None), sector, subsector, tier,
# cash, short_term_inv, total_debt, short_term_debt, interest_expense,
# operating_cash_flow, capex, revenue, ebitda,
# debt_maturities_12m, debt_maturities_24m, committed_capex_24m, revolver_available
COMPANIES: list[dict[str, Any]] = [
    # Tier 1 - AI compute / semis
    dict(name="NVIDIA", ticker="NVDA", cik="0001045810", sector="Semiconductors", subsector="AI Accelerators", tier="compute_semis",
         cash=9000, sti=25000, debt=10000, st_debt=0, interest=250, ocf=32000, capex=3200, revenue=96000, ebitda=55000,
         mat12=0, mat24=0, capex24=8000, revolver=3000),
    dict(name="AMD", ticker="AMD", cik="0000002488", sector="Semiconductors", subsector="CPU/GPU", tier="compute_semis",
         cash=4200, sti=2100, debt=2500, st_debt=0, interest=60, ocf=1600, capex=500, revenue=23000, ebitda=3800,
         mat12=0, mat24=750, capex24=1200, revolver=2000),
    dict(name="Broadcom", ticker="AVGO", cik="0001730168", sector="Semiconductors", subsector="Networking/Custom Silicon", tier="compute_semis",
         cash=9700, sti=1000, debt=68000, st_debt=1500, interest=2400, ocf=18000, capex=1000, revenue=51000, ebitda=27000,
         mat12=1500, mat24=4500, capex24=2200, revolver=5000),
    dict(name="TSMC", ticker="TSM", cik=None, sector="Semiconductors", subsector="Foundry", tier="compute_semis",
         cash=32000, sti=25000, debt=25000, st_debt=3000, interest=500, ocf=48000, capex=30000, revenue=90000, ebitda=54000,
         mat12=3000, mat24=6000, capex24=65000, revolver=0),
    dict(name="ASML", ticker="ASML", cik=None, sector="Semiconductor Equipment", subsector="Lithography", tier="compute_semis",
         cash=5000, sti=1500, debt=3500, st_debt=500, interest=90, ocf=8500, capex=2000, revenue=28000, ebitda=10500,
         mat12=500, mat24=1000, capex24=4000, revolver=1500),
    dict(name="Applied Materials", ticker="AMAT", cik=None, sector="Semiconductor Equipment", subsector="Wafer Fab Equipment", tier="compute_semis",
         cash=6500, sti=1000, debt=6100, st_debt=0, interest=180, ocf=6500, capex=900, revenue=27000, ebitda=8000,
         mat12=0, mat24=1000, capex24=1800, revolver=1000),
    dict(name="Lam Research", ticker="LRCX", cik=None, sector="Semiconductor Equipment", subsector="Wafer Fab Equipment", tier="compute_semis",
         cash=5800, sti=200, debt=4000, st_debt=0, interest=120, ocf=3500, capex=350, revenue=15000, ebitda=4300,
         mat12=0, mat24=750, capex24=800, revolver=750),
    dict(name="Micron", ticker="MU", cik=None, sector="Semiconductors", subsector="Memory", tier="compute_semis",
         cash=9500, sti=2000, debt=13500, st_debt=500, interest=450, ocf=8000, capex=8500, revenue=28000, ebitda=10000,
         mat12=500, mat24=1500, capex24=17000, revolver=2500),
    dict(name="Marvell", ticker="MRVL", cik=None, sector="Semiconductors", subsector="Custom Silicon/Networking", tier="compute_semis",
         cash=800, sti=100, debt=4200, st_debt=0, interest=140, ocf=900, capex=140, revenue=5500, ebitda=1500,
         mat12=0, mat24=600, capex24=350, revolver=1500),
    dict(name="Arm Holdings", ticker="ARM", cik=None, sector="Semiconductors", subsector="IP Licensing", tier="compute_semis",
         cash=2000, sti=1200, debt=0, st_debt=0, interest=5, ocf=900, capex=60, revenue=3200, ebitda=900,
         mat12=0, mat24=0, capex24=150, revolver=0),
    dict(name="GlobalFoundries", ticker="GFS", cik=None, sector="Semiconductors", subsector="Foundry", tier="compute_semis",
         cash=2000, sti=1300, debt=1600, st_debt=100, interest=70, ocf=1200, capex=1000, revenue=6700, ebitda=1600,
         mat12=100, mat24=300, capex24=2200, revolver=500),
    dict(name="Intel", ticker="INTC", cik="0000050863", sector="Semiconductors", subsector="CPU/Foundry", tier="compute_semis",
         cash=8000, sti=13000, debt=48000, st_debt=2500, interest=1700, ocf=8000, capex=20000, revenue=53000, ebitda=11000,
         mat12=2500, mat24=5500, capex24=38000, revolver=0),

    # Tier 2 - AI networking / infrastructure
    dict(name="Arista Networks", ticker="ANET", cik="0001596532", sector="Networking", subsector="Data Center Switching", tier="networking_infra",
         cash=1900, sti=5500, debt=0, st_debt=0, interest=5, ocf=2200, capex=90, revenue=7000, ebitda=3000,
         mat12=0, mat24=0, capex24=200, revolver=0),
    dict(name="Vertiv", ticker="VRT", cik=None, sector="Data Center Infrastructure", subsector="Power/Cooling", tier="networking_infra",
         cash=900, sti=100, debt=3200, st_debt=100, interest=150, ocf=900, capex=180, revenue=8000, ebitda=1500,
         mat12=100, mat24=300, capex24=450, revolver=800),
    dict(name="Dell Technologies", ticker="DELL", cik=None, sector="Hardware", subsector="Servers/Infrastructure", tier="networking_infra",
         cash=6500, sti=200, debt=17500, st_debt=1500, interest=750, ocf=6000, capex=900, revenue=95000, ebitda=8500,
         mat12=1500, mat24=2500, capex24=2000, revolver=3000),
    dict(name="Super Micro Computer", ticker="SMCI", cik=None, sector="Hardware", subsector="AI Servers", tier="networking_infra",
         cash=700, sti=0, debt=1600, st_debt=200, interest=60, ocf=-200, capex=250, revenue=15000, ebitda=1100,
         mat12=200, mat24=500, capex24=600, revolver=1000),
    dict(name="Celestica", ticker="CLS", cik=None, sector="EMS/ODM", subsector="Data Center Manufacturing", tier="networking_infra",
         cash=250, sti=0, debt=400, st_debt=50, interest=30, ocf=350, capex=100, revenue=9500, ebitda=650,
         mat12=50, mat24=100, capex24=250, revolver=400),
    dict(name="Coherent Corp", ticker="COHR", cik=None, sector="Optical Components", subsector="Optical Interconnect", tier="networking_infra",
         cash=450, sti=0, debt=3400, st_debt=100, interest=180, ocf=500, capex=350, revenue=5300, ebitda=900,
         mat12=100, mat24=250, capex24=800, revolver=500),
    dict(name="Amphenol", ticker="APH", cik=None, sector="Connectors", subsector="Interconnect", tier="networking_infra",
         cash=1300, sti=0, debt=5500, st_debt=500, interest=180, ocf=2500, capex=450, revenue=15000, ebitda=3500,
         mat12=500, mat24=1000, capex24=1000, revolver=1500),
    dict(name="Monolithic Power Systems", ticker="MPWR", cik=None, sector="Semiconductors", subsector="Power Management", tier="networking_infra",
         cash=800, sti=400, debt=0, st_debt=0, interest=2, ocf=500, capex=60, revenue=2200, ebitda=650,
         mat12=0, mat24=0, capex24=150, revolver=0),
    dict(name="Astera Labs", ticker="ALAB", cik=None, sector="Semiconductors", subsector="Connectivity", tier="networking_infra",
         cash=900, sti=0, debt=0, st_debt=0, interest=1, ocf=60, capex=15, revenue=550, ebitda=70,
         mat12=0, mat24=0, capex24=40, revolver=0),
    dict(name="Credo Technology", ticker="CRDO", cik=None, sector="Semiconductors", subsector="Connectivity", tier="networking_infra",
         cash=350, sti=100, debt=0, st_debt=0, interest=1, ocf=90, capex=15, revenue=450, ebitda=60,
         mat12=0, mat24=0, capex24=40, revolver=0),

    # Tier 3 - hyperscale buyers
    dict(name="Microsoft", ticker="MSFT", cik="0000789019", sector="Hyperscaler", subsector="Cloud/AI Platform", tier="hyperscalers",
         cash=18000, sti=57000, debt=45000, st_debt=3000, interest=2100, ocf=110000, capex=55000, revenue=245000, ebitda=125000,
         mat12=3000, mat24=6000, capex24=130000, revolver=0),
    dict(name="Amazon", ticker="AMZN", cik="0001018724", sector="Hyperscaler", subsector="Cloud/E-commerce", tier="hyperscalers",
         cash=70000, sti=13000, debt=58000, st_debt=8000, interest=2500, ocf=100000, capex=75000, revenue=590000, ebitda=105000,
         mat12=8000, mat24=13000, capex24=160000, revolver=0),
    dict(name="Alphabet", ticker="GOOGL", cik="0001652044", sector="Hyperscaler", subsector="Cloud/AI Platform", tier="hyperscalers",
         cash=24000, sti=79000, debt=13000, st_debt=0, interest=300, ocf=115000, capex=50000, revenue=330000, ebitda=115000,
         mat12=0, mat24=0, capex24=110000, revolver=0),
    dict(name="Meta Platforms", ticker="META", cik="0001326801", sector="Hyperscaler", subsector="AI/Social", tier="hyperscalers",
         cash=32000, sti=30000, debt=28000, st_debt=0, interest=550, ocf=80000, capex=38000, revenue=150000, ebitda=75000,
         mat12=0, mat24=1500, capex24=90000, revolver=0),
    dict(name="Oracle", ticker="ORCL", cik="0001341439", sector="Hyperscaler", subsector="Cloud Infrastructure", tier="hyperscalers",
         cash=10000, sti=1000, debt=88000, st_debt=4500, interest=2900, ocf=20000, capex=17000, revenue=53000, ebitda=23000,
         mat12=4500, mat24=9000, capex24=40000, revolver=6000),
    dict(name="Apple", ticker="AAPL", cik="0000320193", sector="Hardware/Platform", subsector="Consumer/AI Silicon", tier="hyperscalers",
         cash=30000, sti=35000, debt=100000, st_debt=10000, interest=3900, ocf=115000, capex=10000, revenue=390000, ebitda=130000,
         mat12=10000, mat24=19000, capex24=22000, revolver=0),

    # Tier 4 - higher-financing-risk infrastructure (configurable list, not hard-coded)
    dict(name="Digital Realty Trust", ticker="DLR", cik=None, sector="Data Center REIT", subsector="Colocation", tier="higher_risk_infra",
         cash=200, sti=0, debt=15500, st_debt=500, interest=550, ocf=1600, capex=2500, revenue=5600, ebitda=2700,
         mat12=500, mat24=1500, capex24=5500, revolver=2000),
    dict(name="Equinix", ticker="EQIX", cik=None, sector="Data Center REIT", subsector="Colocation", tier="higher_risk_infra",
         cash=1900, sti=0, debt=17500, st_debt=0, interest=550, ocf=3300, capex=3000, revenue=8700, ebitda=4100,
         mat12=0, mat24=1500, capex24=6500, revolver=2000),
    dict(name="Nebius Group", ticker="NBIS", cik=None, sector="AI Cloud", subsector="GPU Cloud", tier="higher_risk_infra",
         cash=2200, sti=200, debt=800, st_debt=0, interest=40, ocf=-150, capex=1500, revenue=500, ebitda=-100,
         mat12=0, mat24=200, capex24=3500, revolver=0),
]
