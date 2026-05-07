from __future__ import annotations

import os
import sys

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.openclaw_proposal_store import (  # noqa: E402
    OpenClawProposalStore,
    OpenClawProposalValidationError,
    _bounded_payload,
    _validate_side_effect_route,
)


def test_bounded_payload_redacts_sensitive_nested_values() -> None:
    payload = {
        "safe": "ok",
        "api_key": "secret-value",
        "nested": {"refresh_token": "token-value"},
    }
    redacted = _bounded_payload(payload)
    assert redacted == {
        "safe": "ok",
        "api_key": "[REDACTED]",
        "nested": {"refresh_token": "[REDACTED]"},
    }


def test_side_effect_route_allows_only_governance_paths_without_forbidden_fragments() -> None:
    assert _validate_side_effect_route("/api/v1/governance/audit/approve/x")
    with pytest.raises(OpenClawProposalValidationError):
        _validate_side_effect_route("/api/v1/orders/submit")
    with pytest.raises(OpenClawProposalValidationError):
        _validate_side_effect_route("/api/v1/governance/live-auth/renew")
    with pytest.raises(OpenClawProposalValidationError):
        _validate_side_effect_route("/api/v1/replay/run")


def test_approval_without_delegation_only_allows_readonly_offline_scope() -> None:
    store = OpenClawProposalStore()
    assert store._approval_can_complete_without_delegation(
        {
            "proposal_type": "read_only_report",
            "risk_class": "read_only",
            "required_approval_class": "operator",
            "side_effect_route": None,
        }
    )
    assert not store._approval_can_complete_without_delegation(
        {
            "proposal_type": "trade_affecting",
            "risk_class": "live_affecting",
            "required_approval_class": "operator",
            "side_effect_route": None,
        }
    )
    assert not store._approval_can_complete_without_delegation(
        {
            "proposal_type": "read_only_report",
            "risk_class": "read_only",
            "required_approval_class": "operator",
            "side_effect_route": "/api/v1/governance/audit/approve/x",
        }
    )
