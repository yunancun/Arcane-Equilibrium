"""Source-only IBKR connector skeleton for the ADR-0048 Stock/ETF lane.

The package is intentionally inert: it imports no IBKR SDK, reads no secrets,
opens no sockets, and exposes no broker write methods. Runtime authority remains
in Rust gates before any future read-only or paper capability can be enabled.
"""

from .models import (
    IBKR_CONNECTOR_SURFACE_ID,
    IbkrReadOnlyEndpointConfig,
    IbkrReadOnlySurfaceStatus,
)
from .paper_client import IbkrPaperClientBoundary
from .readonly_client import IbkrReadOnlyClient

__all__ = [
    "IBKR_CONNECTOR_SURFACE_ID",
    "IbkrPaperClientBoundary",
    "IbkrReadOnlyClient",
    "IbkrReadOnlyEndpointConfig",
    "IbkrReadOnlySurfaceStatus",
]
