from __future__ import annotations

import sys
from pathlib import Path


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app.openclaw_authority_contracts import (  # noqa: E402
    OPENCLAW_ACTIVE_ROUTES,
    OPENCLAW_FORBIDDEN_SIDE_EFFECT_FRAGMENTS,
    OPENCLAW_LEDGER_WRITE_CLASSES,
    OPENCLAW_SAFE_APPROVAL_RISK_CLASSES,
    OPENCLAW_SAFE_APPROVAL_TYPES,
    build_openclaw_authority_posture,
)


def test_openclaw_authority_posture_has_only_ledger_writes() -> None:
    posture = build_openclaw_authority_posture()

    assert posture["enabled_write_classes"] == list(OPENCLAW_LEDGER_WRITE_CLASSES)
    assert posture["can_submit_orders"] is False
    assert posture["can_cancel_orders"] is False
    assert posture["can_close_positions"] is False
    assert posture["can_mutate_live_config"] is False
    assert posture["can_mutate_risk_config"] is False
    assert posture["can_read_secrets"] is False
    assert posture["can_restart_or_deploy"] is False
    assert posture["requires_governance_hub_for_side_effects"] is True
    assert posture["requires_decision_lease_for_execution"] is True


def test_openclaw_route_contract_has_no_forbidden_side_effect_paths() -> None:
    forbidden = OPENCLAW_FORBIDDEN_SIDE_EFFECT_FRAGMENTS

    for _method, path, _label in OPENCLAW_ACTIVE_ROUTES:
        lowered = path.lower()
        assert not any(fragment in lowered for fragment in forbidden)


def test_openclaw_safe_approval_contract_is_offline_only() -> None:
    assert OPENCLAW_SAFE_APPROVAL_TYPES == frozenset({
        "read_only_report",
        "diagnosis_followup",
        "offline_replay",
    })
    assert OPENCLAW_SAFE_APPROVAL_RISK_CLASSES == frozenset({
        "read_only",
        "offline",
    })

