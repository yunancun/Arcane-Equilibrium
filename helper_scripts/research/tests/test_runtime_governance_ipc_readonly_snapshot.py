from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import runtime_governance_ipc_readonly_snapshot as mod


NOW = dt.datetime(2026, 6, 27, 8, 0, tzinfo=dt.timezone.utc)


async def _ready_dispatcher(method: str, params: dict, timeout: float) -> dict:
    assert params == {}
    assert timeout == 5.0
    if method == "governance.get_status":
        return {
            "enabled": True,
            "mode": "Normal",
            "risk_level": "Normal",
            "auth_effective_count": 2,
            "auth_pending_approval": 0,
            "lease_live_count": 0,
            "oms_active_count": 0,
        }
    if method == "governance.list_leases":
        return {"result": []}
    if method == "governance.get_risk_state":
        return {
            "level": "NORMAL",
            "constraints": {
                "new_entries_allowed": True,
                "position_size_multiplier": 1.0,
                "reduce_only": False,
                "active_de_risking": False,
                "emergency_stops": False,
                "requires_operator": False,
            },
        }
    raise AssertionError(method)


async def _failing_dispatcher(method: str, params: dict, timeout: float) -> dict:
    if method == "governance.list_leases":
        return {"ok": False, "error": "socket_unavailable"}
    return await _ready_dispatcher(method, params, timeout)


def test_build_ready_snapshot_uses_read_only_governance_methods() -> None:
    packet = mod.build_runtime_governance_ipc_readonly_snapshot(
        now_utc=NOW,
        dispatcher=_ready_dispatcher,
        source_head="source",
        runtime_head="runtime",
    )

    assert packet["status"] == mod.READY_STATUS
    assert packet["schema_version"] == mod.SCHEMA_VERSION
    assert set(packet["methods"]) == set(mod.READ_ONLY_METHODS)
    assert packet["summary"]["risk_level"] == "NORMAL"
    assert packet["summary"]["position_size_multiplier"] == 1.0
    assert packet["summary"]["lease_count"] == 0
    assert packet["answers"]["runtime_readonly_ipc_call_performed"] is True
    assert packet["answers"]["read_only_methods_only"] is True
    assert packet["answers"]["decision_lease_acquire_performed"] is False
    assert packet["answers"]["decision_lease_release_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["runtime_mutation_performed"] is False
    assert packet["answers"]["live_authority_granted"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"


def test_build_snapshot_blocks_when_any_runtime_method_fails() -> None:
    packet = mod.build_runtime_governance_ipc_readonly_snapshot(
        now_utc=NOW,
        dispatcher=_failing_dispatcher,
    )

    assert packet["status"] == mod.BLOCKED_BY_RUNTIME_STATUS
    assert packet["summary"] is None
    assert packet["runtime_blockers"] == ["governance.list_leases_not_ok"]
    assert packet["methods"]["governance.list_leases"]["ok"] is False
