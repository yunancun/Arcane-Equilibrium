"""Inert paper-lifecycle boundary for the IBKR Stock/ETF connector package."""

from __future__ import annotations

from .models import IbkrReadOnlyEndpointConfig, blocked_readonly_status


class IbkrPaperClientBoundary:
    """Paper-capability descriptor with no broker write surface."""

    def __init__(self, config: IbkrReadOnlyEndpointConfig | None = None) -> None:
        self._config = config or IbkrReadOnlyEndpointConfig()

    def lifecycle_readiness(self) -> dict[str, object]:
        status = blocked_readonly_status(
            "paper_lifecycle_runtime_blocked",
            "rust_authority_required",
            "paper_session_attestation_missing",
            config=self._config,
        )
        payload = status.to_dict()
        payload.update(
            {
                "paper_lifecycle_readiness": False,
                "rust_authority_required": True,
                "python_broker_write_authority": False,
                "paper_channel_exposed": False,
                "order_write_method_present": False,
            }
        )
        return payload

    def fill_import_readiness(self) -> dict[str, object]:
        status = blocked_readonly_status(
            "fill_import_runtime_blocked",
            "stock_etf_paper_fill_import_request_required",
            config=self._config,
        )
        payload = status.to_dict()
        payload.update(
            {
                "fill_import_readiness": False,
                "python_import_side_effects": False,
                "broker_write_authority": False,
                "db_apply_authority": False,
            }
        )
        return payload
