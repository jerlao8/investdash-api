from app.connectors.base import DataConnector
from app.connectors.cboe import CboeConnector
from app.connectors.fred import FredConnector
from app.connectors.mock_only import (
    BeaConnector,
    BisConnector,
    BlsConnector,
    CftcConnector,
    FinraConnector,
    SiaWstsConnector,
)
from app.connectors.nyfed import NYFedConnector
from app.connectors.sec import SecConnector
from app.connectors.treasury import TreasuryConnector

CONNECTOR_REGISTRY: dict[str, DataConnector] = {
    "fred": FredConnector(),
    "treasury": TreasuryConnector(),
    "nyfed": NYFedConnector(),
    "cboe": CboeConnector(),
    "sec": SecConnector(),
    "bis": BisConnector(),
    "bls": BlsConnector(),
    "bea": BeaConnector(),
    "sia_wsts": SiaWstsConnector(),
    "finra": FinraConnector(),
    "cftc": CftcConnector(),
}


def get_connector(key: str) -> DataConnector:
    return CONNECTOR_REGISTRY[key]
