"""Inert read-only IBKR client boundary for ADR-0048 source work."""

from __future__ import annotations

from .models import (
    IbkrReadOnlyEndpointConfig,
    IbkrReadOnlySurfaceStatus,
    blocked_readonly_status,
)


class IbkrReadOnlyClient:
    """A no-network placeholder for future Rust-gated read-only checks."""

    def __init__(self, config: IbkrReadOnlyEndpointConfig | None = None) -> None:
        self._config = config or IbkrReadOnlyEndpointConfig()

    @property
    def config(self) -> IbkrReadOnlyEndpointConfig:
        return self._config

    def readiness(self) -> IbkrReadOnlySurfaceStatus:
        return blocked_readonly_status(config=self._config)

    def connection_plan(self) -> dict[str, object]:
        return {
            "asset_lane": self._config.asset_lane,
            "broker": self._config.broker,
            "environment": self._config.environment,
            "transport": self._config.transport,
            "host": self._config.host,
            "port": self._config.port,
            "client_id": self._config.client_id,
            "network_contact_allowed": False,
            "network_contact_performed": False,
            "secret_content_loaded": False,
            "paper_channel_exposed": False,
            "live_channel_exposed": False,
            "bybit_path_reused": False,
            "blockers": list(self._config.validate_source_boundary()),
        }

    def account_snapshot_preview(self) -> dict[str, object]:
        status = blocked_readonly_status("account_snapshot_blocked", config=self._config)
        return status.to_dict()

    def market_data_preview(self) -> dict[str, object]:
        status = blocked_readonly_status("market_data_blocked", config=self._config)
        return status.to_dict()

    def contract_details_preview(self) -> dict[str, object]:
        status = blocked_readonly_status("contract_details_blocked", config=self._config)
        return status.to_dict()
