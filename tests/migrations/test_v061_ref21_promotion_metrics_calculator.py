"""Static migration tests for REF-21 V061 promotion metrics calculator.

These tests keep the non-stub SECURITY DEFINER calculator from drifting back
to producer-supplied metrics. Linux PG transaction dry-run remains the runtime
gate; this file verifies the structural SQL contract locally.
"""

from __future__ import annotations

import re
from pathlib import Path


_THIS_FILE = Path(__file__).resolve()
_SRV_ROOT = _THIS_FILE.parents[2]
V061_PATH = _SRV_ROOT / "sql" / "migrations" / "V061__replay_promotion_metrics_calculator.sql"


def _read_sql() -> str:
    assert V061_PATH.exists(), f"Migration file missing: {V061_PATH}"
    return V061_PATH.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.splitlines())


def test_v061_creates_non_stub_security_definer_calculator() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "CREATE OR REPLACE FUNCTION replay.calculate_promotion_metrics" in sql
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = pg_catalog, replay, learning, pg_temp" in sql
    assert "producer" in _read_sql().lower()
    assert "replay.simulated_fills" in sql
    assert "replay.experiments" in sql
    assert "learning.edge_estimate_snapshots" in sql
    assert "replay.tier_promotion_approval" not in sql.split(
        "CREATE OR REPLACE FUNCTION replay.calculate_promotion_metrics", 1
    )[1].split("END $$;", 1)[0]


def test_v061_includes_dsr_pbo_and_stationary_bootstrap_helpers() -> None:
    sql = _strip_sql_comments(_read_sql())
    for helper in (
        "_jsonb_double_v061",
        "_is_finite_v061",
        "_normal_inv_cdf_v061",
        "_expected_max_sharpe_v061",
        "_psr_v061",
        "_stationary_bootstrap_quantile_ci_v061",
        "_popcount_v061",
    ):
        assert f"replay.{helper}" in sql
    assert "FOR v_iter IN 1..1000 LOOP" in sql
    assert "floor(sqrt(v_n::DOUBLE PRECISION))::INTEGER" in sql
    assert "v_mask IN 0..65535" in sql
    assert "replay._popcount_v061(v_mask, 16) = 8" in sql
    assert "pbo_combinations" in sql


def test_v061_fail_closed_promotion_gates_are_encoded() -> None:
    sql = _strip_sql_comments(_read_sql())
    for transition in (
        "s2_public_replay",
        "s2_oos_replay",
        "s1_calibrated_replay",
        "verified_replay_advisory",
    ):
        assert transition in sql
    for reason in (
        "invalid_tier_transition",
        "experiment_missing",
        "manifest_hash_missing",
        "is_oos_windows_missing",
        "return_bps_missing",
        "is_returns_missing",
        "oos_returns_missing",
        "oos_net_bps_not_positive",
        "oos_gap_gt_30bps",
        "edge_snapshot_missing",
        "predicted_edge_bps_not_positive",
        "psr0_lt_0_95",
        "dsr_not_positive",
        "pbo_insufficient_power",
        "pbo_gt_0_20",
    ):
        assert reason in sql
    assert "v_predicted_edge_bps <= 0.0" in sql
    assert "v_oos_gap_bps IS NULL OR v_oos_gap_bps > 30.0" in sql
    assert "v_pbo IS NULL OR v_pbo > 0.20" in sql


def test_v061_uses_historical_edge_snapshots_without_future_leakage() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "e.asof_ts <= COALESCE(v_candidate_start, v_oos_start, now())" in sql
    assert "NOT e.is_deprecated_at_asof" in sql
    for key in (
        "predicted_edge_bps",
        "edge_bps",
        "expected_net_bps",
        "net_bps_after_fee",
    ):
        assert key in sql


def test_v061_revokes_public_execute_and_has_guard_abc() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "V061 Guard A" in sql
    assert "V061 Guard B/C" in sql
    assert (
        "REVOKE ALL ON FUNCTION replay.calculate_promotion_metrics(\n"
        "        UUID,\n"
        "        replay.replay_evidence_tier_v057,\n"
        "        replay.replay_evidence_tier_v057\n"
        "    ) FROM PUBLIC"
    ) in sql
    assert "information_schema.routine_privileges" in sql
    assert "grantee = 'PUBLIC'" in sql
    assert "privilege_type = 'EXECUTE'" in sql


def test_v061_avoids_pg_search_path_and_float_portability_traps() -> None:
    sql = _strip_sql_comments(_read_sql())
    assert "public.digest" in sql
    assert re.search(r"(?<!public[.])\bdigest\(", sql) is None
    assert "isfinite(" not in sql
    assert "_is_finite_v061" in sql
    assert "[.][0-9]" in sql
