"""Source-only IBKR connector skeleton for the ADR-0048 Stock/ETF lane.

The package is intentionally inert: it imports no IBKR SDK, reads no secrets,
opens no sockets, and exposes no broker write methods. Runtime authority remains
in Rust gates before any future read-only or paper capability can be enabled.
"""

from .models import (
    IBKR_CONNECTOR_SURFACE_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID,
    IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    IbkrPaperAttestationPreview,
    IbkrReadOnlyEndpointConfig,
    IbkrReadOnlyProbeResultImportPreview,
    IbkrReadOnlySurfaceStatus,
    IbkrSessionAttestationPreview,
)
from .paper_client import IbkrPaperClientBoundary
from .readonly_client import IbkrReadOnlyClient

__all__ = [
    "IBKR_CONNECTOR_SURFACE_ID",
    "IBKR_PAPER_ATTESTATION_CONTRACT_ID",
    "IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "IbkrPaperAttestationPreview",
    "IbkrPaperClientBoundary",
    "IbkrReadOnlyClient",
    "IbkrReadOnlyEndpointConfig",
    "IbkrReadOnlyProbeResultImportPreview",
    "IbkrReadOnlySurfaceStatus",
    "IbkrSessionAttestationPreview",
]
