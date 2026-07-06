"""Source-only IBKR connector skeleton for the ADR-0048 Stock/ETF lane.

The package is intentionally inert: it imports no IBKR SDK, reads no secrets,
opens no sockets, and exposes no broker write methods. Runtime authority remains
in Rust gates before any future read-only or paper capability can be enabled.
"""

from .api_absent_engineering import (
    IBKR_API_ABSENT_ENGINEERING_PACKET_ID,
    IBKR_API_ABSENT_MODE,
    IBKR_PHASE2_GATE_CANDIDATE_STATUS,
    IbkrApiAbsentEngineeringPacket,
    IbkrApiAbsentLoopDecision,
    api_absent_engineering_fixture,
    build_api_absent_engineering_packet,
)
from .models import (
    IBKR_CONNECTOR_SURFACE_ID,
    IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID,
    IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    IbkrApiActionMatrixPreview,
    IbkrPaperAttestationPreview,
    IbkrReadOnlyEndpointConfig,
    IbkrReadOnlyProbeResultImportPreview,
    IbkrReadOnlySurfaceStatus,
    IbkrSessionAttestationPreview,
)
from .paper_client import IbkrPaperClientBoundary
from .readonly_client import IbkrReadOnlyClient

__all__ = [
    "IBKR_API_ABSENT_ENGINEERING_PACKET_ID",
    "IBKR_API_ABSENT_MODE",
    "IBKR_CONNECTOR_SURFACE_ID",
    "IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID",
    "IBKR_PAPER_ATTESTATION_CONTRACT_ID",
    "IBKR_PHASE2_GATE_CANDIDATE_STATUS",
    "IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "IbkrApiAbsentEngineeringPacket",
    "IbkrApiAbsentLoopDecision",
    "IbkrApiActionMatrixPreview",
    "IbkrPaperAttestationPreview",
    "IbkrPaperClientBoundary",
    "IbkrReadOnlyClient",
    "IbkrReadOnlyEndpointConfig",
    "IbkrReadOnlyProbeResultImportPreview",
    "IbkrReadOnlySurfaceStatus",
    "IbkrSessionAttestationPreview",
    "api_absent_engineering_fixture",
    "build_api_absent_engineering_packet",
]
