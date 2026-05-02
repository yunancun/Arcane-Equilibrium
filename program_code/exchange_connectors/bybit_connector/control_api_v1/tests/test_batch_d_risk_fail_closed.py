"""Batch D risk/config fail-closed static regression tests.
Batch D 風控/配置 fail-closed 靜態回歸測試。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)


def _repo_root() -> Path:
    return Path(_control_api_dir).parents[3]


def _read(rel_path: str) -> str:
    return (_repo_root() / rel_path).read_text(encoding="utf-8")


def test_lp_002_restart_scripts_use_openclaw_engine_pkgid() -> None:
    """clean/fresh restart must validate/build using openclaw_engine package id."""
    clean = _read("helper_scripts/clean_restart.sh")
    fresh = _read("helper_scripts/fresh_start.sh")

    for body in (clean, fresh):
        assert "cargo pkgid -p openclaw_engine" in body
        assert "cargo build --release -p openclaw_engine" in body
        assert "-p openclaw-engine" not in body


def test_rc_002_h0_status_refresh_preserves_cooldown_and_kill_switch() -> None:
    """Periodic status refresh must merge with previous cooldown/kill-switch state.

    NOTE 2026-05-02 (CC AUDIT-2026-05-02-P1-2): the assertions used to grep
    `event_consumer/loop_handlers.rs`, but commit `c6ec664`
    (refactor: complete maintenance splits) extracted the status-refresh path
    into `event_consumer/status_report.rs`. Repointed to the post-split file.
    """
    h0_gate = _read("rust/openclaw_core/src/h0_gate.rs")
    status_report = _read("rust/openclaw_engine/src/event_consumer/status_report.rs")

    assert "pub fn risk_snapshot(&self) -> H0GateRiskSnapshot" in h0_gate
    assert "fn build_status_risk_snapshot(" in status_report
    assert "cooldown_until_ts_ms: if prev.cooldown_until_ts_ms > now_ms" in status_report
    assert "kill_switch_active: prev.kill_switch_active" in status_report
    assert "status_risk_snapshot_preserves_active_cooldown_and_kill_switch" in status_report


def test_rc_004_missing_demo_live_risk_configs_fail_closed() -> None:
    """Startup must error when demo/live risk config files are missing."""
    startup = _read("rust/openclaw_engine/src/startup/mod.rs")
    assert "risk_demo config missing" in startup
    assert "risk_live config missing" in startup
    assert "missing demo/live configs must fail closed" in startup


def test_rc_005_governor_constraints_enforced_in_router() -> None:
    """Router must enforce governor constraints for new entries consistently."""
    router = _read("rust/openclaw_engine/src/intent_processor/router.rs")
    tests = _read("rust/openclaw_engine/src/intent_processor/tests.rs")

    assert "fn apply_governor_order_constraints(" in router
    assert "constraints.new_entries_allowed" in router
    assert "constraints.reduce_only" in router
    assert "constraints.requires_operator" in router
    assert "requested_qty.min(qty)" in router
    assert "test_governor_cautious_scales_new_entry_qty" in tests
    assert "test_governor_reduced_blocks_new_entries" in tests
    assert "test_governor_reduced_caps_opposite_order_to_existing_qty" in tests
    assert "test_governor_reduced_caps_exchange_opposite_order_to_existing_qty" in tests
    dispatch = _read("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs")
    assert "let is_reducing_order = self" in dispatch
    assert "is_close: is_reducing_order" in dispatch
    assert "if !is_reducing_order" in dispatch


def test_rc_006_update_risk_config_no_longer_claims_applied_and_handles_send_fail() -> None:
    """Legacy update_risk_config must not claim immediate apply and must fail on send error."""
    handler = _read("rust/openclaw_engine/src/ipc_server/handlers/risk.rs")
    tests = _read("rust/openclaw_engine/src/ipc_server/tests/risk_update.rs")
    event_handler = _read("rust/openclaw_engine/src/event_consumer/handlers/risk.rs")

    assert "response_rx" in handler
    assert '"updated": true,' in event_handler
    assert '"queued": false,' in event_handler
    assert '"applied": true' in event_handler
    assert "channel send failed" in handler
    assert "test_e4_5_handle_update_risk_config_send_failure_returns_internal_error" in tests


def test_sadf_002_strategy_param_update_is_atomic_for_conf_scale() -> None:
    """Mixed strategy param payload must not partially apply conf_scale on validation failure."""
    strategy_handler = _read("rust/openclaw_engine/src/event_consumer/handlers/strategy_params.rs")
    handler_tests = _read("rust/openclaw_engine/src/event_consumer/handlers/tests.rs")

    assert "if need_typed_update" in strategy_handler
    assert "validation failed" in strategy_handler
    assert "strategy.set_conf_scale(scale);" in strategy_handler
    assert "test_conf_scale_not_partially_applied_when_typed_validation_fails" in handler_tests


def test_sadf_003_demo_live_strategy_param_load_fail_closed() -> None:
    """Demo/live strategy param load errors must fall back to all-inactive config."""
    params = _read("rust/openclaw_engine/src/strategies/params.rs")
    tests = _read("rust/openclaw_engine/src/strategies/tests.rs")

    assert "fn fail_closed_inactive_config()" in params
    assert "if kind.is_exchange()" in params
    assert "using fail-closed inactive config" in params
    assert "test_load_strategy_params_missing_file_demo_is_fail_closed_inactive" in tests
    assert "test_load_strategy_params_invalid_toml_live_is_fail_closed_inactive" in tests


def test_oe_006_close_retry_budget_has_real_timeout_guard() -> None:
    """Close retry path must include explicit per-attempt timeout budget guard."""
    dispatch = _read("rust/openclaw_engine/src/event_consumer/dispatch.rs")
    assert "pub(super) const CLOSE_ATTEMPT_TIMEOUT_MS: u64 = 500;" in dispatch
    assert "tokio::time::timeout" in dispatch
    assert "close dispatch timed out" in dispatch
    assert "test_close_attempt_timeout_constant_is_500ms" in dispatch
