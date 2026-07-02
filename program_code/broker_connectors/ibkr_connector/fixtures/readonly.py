"""Blocked, secret-free IBKR read-only connector fixture."""

from __future__ import annotations

from ..models import (
    IbkrReadOnlyEndpointConfig,
    blocked_api_action_matrix_preview,
    blocked_paper_attestation_preview,
    blocked_readonly_probe_result_import_preview,
    blocked_readonly_status,
    blocked_session_attestation_preview,
)


def blocked_readonly_fixture() -> dict[str, object]:
    config = IbkrReadOnlyEndpointConfig()
    return blocked_readonly_status(config=config).to_dict()


def blocked_api_action_matrix_fixture() -> dict[str, object]:
    config = IbkrReadOnlyEndpointConfig()
    return blocked_api_action_matrix_preview(config=config).to_dict()


def blocked_session_attestation_fixture() -> dict[str, object]:
    config = IbkrReadOnlyEndpointConfig()
    return blocked_session_attestation_preview(config=config).to_dict()


def blocked_readonly_probe_result_import_fixture() -> dict[str, object]:
    config = IbkrReadOnlyEndpointConfig()
    return blocked_readonly_probe_result_import_preview(config=config).to_dict()


def blocked_paper_attestation_fixture() -> dict[str, object]:
    config = IbkrReadOnlyEndpointConfig()
    return blocked_paper_attestation_preview(config=config).to_dict()
