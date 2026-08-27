"""Capex Freeze Monitor company registry (build spec §4), v1 scope.

Listed companies only - private entities (OpenAI, Anthropic, most of L1) need the event
track (manual entries) from the spec's later build steps and are deliberately left out
rather than faked. Ticker is the join key against the existing `companies` table used by
the AI Company Monitor: where a ticker already exists there (NVDA, MSFT, AMZN, ...), this
registry only adds the lock_id/cfi_tier/cfi_role tags via upsert - see
app/jobs/cfi_pipeline.sync_cfi_companies - it never overwrites that table's own sector/
subsector/tier fields.

L1 (Unit economics) has zero listed constituents in this registry: per the spec itself,
"L1 is the origin and has the worst data... almost entirely private." Faking coverage there
would be exactly the failure mode the spec warns against in its coverage-requirement note -
a lock that looks scored because inputs were imputed. It shows as no-coverage until the
event track exists.
"""

from __future__ import annotations

from typing import Any

# ticker, name, cik (10-digit zero-padded, None if not an SEC filer we can XBRL-fetch),
# lock_id (L1..L6), cfi_tier (1|2|3), cfi_role
CFI_COMPANIES: list[dict[str, Any]] = [
    # ---- L2: Utilisation ----
    dict(ticker="CRWV", name="CoreWeave", cik="0001769628", lock_id="L2", cfi_tier=1, cfi_role="listed neocloud benchmark"),
    dict(ticker="NBIS", name="Nebius Group", cik=None, lock_id="L2", cfi_tier=1, cfi_role="listed neocloud"),
    dict(ticker="IREN", name="IREN", cik="0001878848", lock_id="L2", cfi_tier=2, cfi_role="converted miner"),
    dict(ticker="APLD", name="Applied Digital", cik="0001144879", lock_id="L2", cfi_tier=2, cfi_role="neocloud + colo"),
    dict(ticker="CIFR", name="Cipher Mining", cik="0001819989", lock_id="L2", cfi_tier=3, cfi_role="converted miner"),
    dict(ticker="CORZ", name="Core Scientific", cik="0001839341", lock_id="L2", cfi_tier=3, cfi_role="converted miner"),
    dict(ticker="GDS", name="GDS Holdings", cik="0001526125", lock_id="L2", cfi_tier=3, cfi_role="China DC"),

    # ---- L3: Financing ----
    dict(ticker="BX", name="Blackstone", cik="0001393818", lock_id="L3", cfi_tier=1, cfi_role="private credit + QTS/AirTrunk owner"),
    dict(ticker="OWL", name="Blue Owl Capital", cik="0001823945", lock_id="L3", cfi_tier=1, cfi_role="private credit, DC financing"),
    dict(ticker="ARES", name="Ares Management", cik="0001176948", lock_id="L3", cfi_tier=2, cfi_role="private credit"),
    dict(ticker="APO", name="Apollo Global", cik="0001858681", lock_id="L3", cfi_tier=2, cfi_role="private credit"),
    dict(ticker="KKR", name="KKR", cik="0001404912", lock_id="L3", cfi_tier=2, cfi_role="infra + CyrusOne"),
    dict(ticker="MCO", name="Moody's", cik="0001059556", lock_id="L3", cfi_tier=2, cfi_role="rating agency"),
    dict(ticker="SPGI", name="S&P Global", cik="0000064040", lock_id="L3", cfi_tier=2, cfi_role="rating agency"),
    dict(ticker="DLR", name="Digital Realty", cik=None, lock_id="L3", cfi_tier=1, cfi_role="colo REIT"),
    dict(ticker="EQIX", name="Equinix", cik=None, lock_id="L3", cfi_tier=1, cfi_role="colo REIT"),

    # ---- L4: Order book ----
    dict(ticker="NVDA", name="NVIDIA", cik="0001045810", lock_id="L4", cfi_tier=1, cfi_role="accelerators"),
    dict(ticker="AMD", name="AMD", cik="0000002488", lock_id="L4", cfi_tier=1, cfi_role="accelerators"),
    dict(ticker="AVGO", name="Broadcom", cik="0001730168", lock_id="L4", cfi_tier=1, cfi_role="custom silicon/networking"),
    dict(ticker="MRVL", name="Marvell Technology", cik=None, lock_id="L4", cfi_tier=1, cfi_role="custom silicon"),
    dict(ticker="INTC", name="Intel", cik="0000050863", lock_id="L4", cfi_tier=2, cfi_role="accelerators/foundry"),
    dict(ticker="TSM", name="TSMC", cik=None, lock_id="L4", cfi_tier=1, cfi_role="foundry"),
    dict(ticker="ASML", name="ASML", cik=None, lock_id="L4", cfi_tier=1, cfi_role="semicap equipment"),
    dict(ticker="AMAT", name="Applied Materials", cik=None, lock_id="L4", cfi_tier=2, cfi_role="semicap equipment"),
    dict(ticker="LRCX", name="Lam Research", cik=None, lock_id="L4", cfi_tier=2, cfi_role="semicap equipment"),
    dict(ticker="MU", name="Micron Technology", cik=None, lock_id="L4", cfi_tier=1, cfi_role="HBM/memory"),
    dict(ticker="ANET", name="Arista Networks", cik="0001596532", lock_id="L4", cfi_tier=1, cfi_role="networking"),
    dict(ticker="ALAB", name="Astera Labs", cik=None, lock_id="L4", cfi_tier=1, cfi_role="optics/connectivity"),
    dict(ticker="CRDO", name="Credo Technology", cik=None, lock_id="L4", cfi_tier=1, cfi_role="optics/connectivity"),
    dict(ticker="COHR", name="Coherent Corp", cik=None, lock_id="L4", cfi_tier=1, cfi_role="optics"),
    dict(ticker="SMCI", name="Super Micro Computer", cik=None, lock_id="L4", cfi_tier=1, cfi_role="ODM/server"),
    dict(ticker="CLS", name="Celestica", cik=None, lock_id="L4", cfi_tier=1, cfi_role="ODM/EMS"),
    dict(ticker="APH", name="Amphenol", cik=None, lock_id="L4", cfi_tier=2, cfi_role="connectors"),
    dict(ticker="MPWR", name="Monolithic Power Systems", cik=None, lock_id="L4", cfi_tier=2, cfi_role="power semis"),

    # ---- L5: Physical build ----
    dict(ticker="VRT", name="Vertiv Holdings", cik=None, lock_id="L5", cfi_tier=1, cfi_role="power/cooling"),
    dict(ticker="ETN", name="Eaton", cik="0001551182", lock_id="L5", cfi_tier=1, cfi_role="electrical equipment"),
    dict(ticker="GEV", name="GE Vernova", cik="0001996810", lock_id="L5", cfi_tier=1, cfi_role="generation/electrical"),
    dict(ticker="CEG", name="Constellation Energy", cik="0001868275", lock_id="L5", cfi_tier=1, cfi_role="power producer"),
    dict(ticker="VST", name="Vistra", cik="0001692819", lock_id="L5", cfi_tier=1, cfi_role="power producer"),
    dict(ticker="PWR", name="Quanta Services", cik="0001050915", lock_id="L5", cfi_tier=1, cfi_role="construction/EPC"),

    # ---- L6: Capex freeze (the end-users - the lock the whole dashboard is about) ----
    dict(ticker="AMZN", name="Amazon", cik="0001018724", lock_id="L6", cfi_tier=1, cfi_role="end-user, ~$200bn 2026 guide"),
    dict(ticker="MSFT", name="Microsoft", cik="0000789019", lock_id="L6", cfi_tier=1, cfi_role="end-user, ~$190bn 2026 guide"),
    dict(ticker="GOOGL", name="Alphabet", cik="0001652044", lock_id="L6", cfi_tier=1, cfi_role="end-user, $175-205bn 2026 guide"),
    dict(ticker="META", name="Meta Platforms", cik="0001326801", lock_id="L6", cfi_tier=1, cfi_role="end-user, $125-145bn 2026 guide"),
    dict(ticker="ORCL", name="Oracle", cik="0001341439", lock_id="L6", cfi_tier=1, cfi_role="end-user, levered buildout"),
    dict(ticker="AAPL", name="Apple", cik="0000320193", lock_id="L6", cfi_tier=3, cfi_role="end-user, modest capex"),
]
