"""Typed inert models for the IBKR Stock/ETF connector boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


IBKR_CONNECTOR_SURFACE_ID = "ibkr_stock_etf_readonly_connector_skeleton_v1"
IBKR_PAPER_ATTESTATION_CONTRACT_ID = "ibkr_paper_attestation_v1"
IBKR_SESSION_ATTESTATION_CONTRACT_ID = "ibkr_session_attestation_v1"


@dataclass(frozen=True)
class IbkrReadOnlyEndpointConfig:
    """Non-secret connection descriptor for future loopback paper readiness."""

    asset_lane: str = "stock_etf_cash"
    broker: str = "ibkr"
    environment: str = "read_only"
    transport: str = "tws_api_loopback_paper_reserved"
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 0
    account_fingerprint_hash: str = ""
    secret_fingerprint_hash: str = ""
    allow_network_contact: bool = False
    allow_secret_material: bool = False
    allow_paper_channel: bool = False
    allow_live_channel: bool = False
    bybit_path_reused: bool = False

    def validate_source_boundary(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.asset_lane != "stock_etf_cash":
            blockers.append("asset_lane_mismatch")
        if self.broker != "ibkr":
            blockers.append("broker_mismatch")
        if self.environment != "read_only":
            blockers.append("environment_not_read_only")
        if self.host != "127.0.0.1":
            blockers.append("host_not_loopback")
        if self.port not in (4001, 4002):
            blockers.append("port_not_reserved_paper_tws")
        if self.client_id < 0:
            blockers.append("client_id_negative")
        if self.allow_network_contact:
            blockers.append("network_contact_requested")
        if self.allow_secret_material:
            blockers.append("secret_material_requested")
        if self.allow_paper_channel:
            blockers.append("paper_channel_requested")
        if self.allow_live_channel:
            blockers.append("live_channel_requested")
        if self.bybit_path_reused:
            blockers.append("bybit_path_reused")
        if self.account_fingerprint_hash:
            blockers.append("account_fingerprint_present_before_phase2")
        if self.secret_fingerprint_hash:
            blockers.append("secret_fingerprint_present_before_phase2")
        return tuple(blockers)


@dataclass(frozen=True)
class IbkrReadOnlySurfaceStatus:
    """Display/readiness payload; every runtime-sensitive field is blocked."""

    surface_id: str = IBKR_CONNECTOR_SURFACE_ID
    accepted: bool = False
    status: str = "blocked_source_only"
    asset_lane: str = "stock_etf_cash"
    broker: str = "ibkr"
    environment: str = "read_only"
    blockers: tuple[str, ...] = field(default_factory=lambda: ("phase2_gate_not_accepted",))
    network_contact_performed: bool = False
    secret_content_loaded: bool = False
    account_snapshot_loaded: bool = False
    market_data_loaded: bool = False
    contract_details_loaded: bool = False
    paper_channel_exposed: bool = False
    live_channel_exposed: bool = False
    order_write_method_present: bool = False
    bybit_path_reused: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True)
class IbkrSessionAttestationPreview:
    """Secret-free placeholder for the future broker session attestation."""

    expected_contract_id: str = IBKR_SESSION_ATTESTATION_CONTRACT_ID
    contract_id: str = ""
    source_version: int = 0
    status: str = "BLOCKED"
    attestation_accepted: bool = False
    blockers: tuple[str, ...] = field(
        default_factory=lambda: (
            "phase2_gate_not_accepted",
            "session_attestation_blocked_source_only",
        )
    )
    environment: str = "read_only"
    account_fingerprint_present: bool = False
    account_fingerprint_is_live: bool = False
    secret_slot_fingerprint_present: bool = False
    api_server_version_present: bool = False
    data_tier: str = "unknown"
    entitlements_fingerprint_present: bool = False
    market_data_entitlement_purchase_denied: bool = False
    gateway_started_at_ms: int = 0
    raw_artifact_hash_present: bool = False
    network_contact_performed: bool = False
    secret_content_loaded: bool = False
    bybit_path_reused: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


@dataclass(frozen=True)
class IbkrPaperAttestationPreview:
    """Secret-free placeholder for future paper account/channel attestation."""

    expected_contract_id: str = IBKR_PAPER_ATTESTATION_CONTRACT_ID
    contract_id: str = ""
    source_version: int = 0
    accepted: bool = False
    blockers: tuple[str, ...] = field(
        default_factory=lambda: (
            "phase2_gate_not_accepted",
            "paper_attestation_blocked_source_only",
            "paper_session_attestation_missing",
        )
    )
    environment: str = "paper"
    paper_account_attestation_present: bool = False
    session_attestation_present: bool = False
    paper_order_channel_attested: bool = False
    account_fingerprint_present: bool = False
    secret_slot_fingerprint_present: bool = False
    network_contact_performed: bool = False
    secret_content_loaded: bool = False
    paper_channel_exposed: bool = False
    live_channel_exposed: bool = False
    bybit_path_reused: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        return payload


def _dedupe_blockers(blockers: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(blockers))


def blocked_readonly_status(
    *extra_blockers: str,
    config: IbkrReadOnlyEndpointConfig | None = None,
) -> IbkrReadOnlySurfaceStatus:
    blockers = ["phase2_gate_not_accepted", *extra_blockers]
    if config is not None:
        blockers.extend(config.validate_source_boundary())
    return IbkrReadOnlySurfaceStatus(blockers=_dedupe_blockers(blockers))


def blocked_session_attestation_preview(
    *extra_blockers: str,
    config: IbkrReadOnlyEndpointConfig | None = None,
) -> IbkrSessionAttestationPreview:
    blockers = [
        "phase2_gate_not_accepted",
        "session_attestation_blocked_source_only",
        *extra_blockers,
    ]
    if config is not None:
        blockers.extend(config.validate_source_boundary())
    return IbkrSessionAttestationPreview(blockers=_dedupe_blockers(blockers))


def blocked_paper_attestation_preview(
    *extra_blockers: str,
    config: IbkrReadOnlyEndpointConfig | None = None,
) -> IbkrPaperAttestationPreview:
    blockers = [
        "phase2_gate_not_accepted",
        "paper_attestation_blocked_source_only",
        "paper_session_attestation_missing",
        *extra_blockers,
    ]
    if config is not None:
        blockers.extend(config.validate_source_boundary())
    return IbkrPaperAttestationPreview(blockers=_dedupe_blockers(blockers))
