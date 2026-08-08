"""Modulo Trasporto Monete — scheletro workflow (nessun invio PEC automatico)."""

from app.modules.coin_transport.module import CoinTransportModule
from app.modules.coin_transport.workflow import (
    COIN_TRANSPORT_STEPS,
    FINAL_STATUS,
    CoinTransportWorkflow,
)

__all__ = [
    "CoinTransportModule",
    "CoinTransportWorkflow",
    "COIN_TRANSPORT_STEPS",
    "FINAL_STATUS",
]
