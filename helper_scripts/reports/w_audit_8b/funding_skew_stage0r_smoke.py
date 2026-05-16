#!/usr/bin/env python3
"""Smoke test for W-AUDIT-8b Stage 0R pure metrics."""

from __future__ import annotations

import sys
import json
from typing import Any

try:
    from .funding_skew_stage0r_metrics import (
        CandidateKey,
        _signal_rows,
        compute_stage0r,
        compute_stage0r_sweep,
        grid_cell_count,
        wilson_ci_95,
    )
    from .funding_skew_stage0r_report import fetch_k_prior
except ImportError:
    from funding_skew_stage0r_metrics import (  # type: ignore
        CandidateKey,
        _signal_rows,
        compute_stage0r,
        compute_stage0r_sweep,
        grid_cell_count,
        wilson_ci_95,
    )
    from funding_skew_stage0r_report import fetch_k_prior  # type: ignore


def _row(
    symbol: str,
    ts: int,
    *,
    funding_z: float,
    pct: float,
    oi: float,
    prior: float,
    fwd30: float,
    next_funding_ms: int,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "signal_ts_ms": ts,
        "prior_5m_return_bps": prior,
        "funding_snapshot_ts_ms": ts - 10_000,
        "funding_age_ms": 10_000,
        "funding_rate_bps": funding_z,
        "funding_zscore_25sym": funding_z,
        "funding_percentile_25sym": pct,
        "funding_spread_to_median_bps": funding_z,
        "funding_cohort_n": 3,
        "next_funding_ms": next_funding_ms,
        "funding_source_tier": "bybit_v5_ws_ticker",
        "oi_snapshot_ts_ms": ts - 10_000,
        "oi_age_ms": 10_000,
        "oi_delta_15m_pct": oi,
        "oi_delta_1h_pct": oi,
        "oi_source_tier": "bybit_v5_ws_open_interest",
        "fwd_return_15m_bps": fwd30 / 2.0,
        "fwd_return_30m_bps": fwd30,
        "fwd_return_60m_bps": fwd30 * 1.5,
    }


def build_fixture() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    symbols = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    base = 1_765_000_000_000
    for i in range(360):
        ts = base + i * 300_000
        cycle = base + ((i // 96) + 1) * 28_800_000
        rows.append(
            _row(
                "BTCUSDT",
                ts,
                funding_z=2.2,
                pct=0.95,
                oi=2.5,
                prior=-1.0,
                fwd30=-35.0,
                next_funding_ms=cycle,
            )
        )
        rows.append(
            _row(
                "ETHUSDT",
                ts,
                funding_z=-2.2,
                pct=0.05,
                oi=2.5,
                prior=1.0,
                fwd30=35.0,
                next_funding_ms=cycle,
            )
        )
        rows.append(
            _row(
                "SOLUSDT",
                ts,
                funding_z=0.1,
                pct=0.5,
                oi=0.2,
                prior=0.0,
                fwd30=0.0,
                next_funding_ms=cycle,
            )
        )
    return rows


class _FakeCursor:
    def __init__(self) -> None:
        self.query = ""

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str) -> None:
        self.query = " ".join(query.split())

    def fetchone(self) -> tuple[int | bool]:
        if "to_regclass" in self.query:
            return (True,)
        if "strategy_name = 'funding_skew_directional'" in self.query:
            return (0,)
        if "strategy_name ILIKE 'funding%%'" in self.query:
            return (9,)
        return (69,)


class _FakeConn:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()


def _check_k_prior_modes(failures: list[str]) -> None:
    strict_value, strict_meta = fetch_k_prior(_FakeConn(), mode="strict-funding-skew")
    funding_value, funding_meta = fetch_k_prior(_FakeConn(), mode="funding-related")
    all_value, all_meta = fetch_k_prior(_FakeConn(), mode="all")
    if strict_value != 0 or strict_meta.get("mode") != "strict-funding-skew":
        failures.append(f"strict K_prior mode mismatch: {strict_value} {strict_meta}")
    if funding_value != 9 or funding_meta.get("mode") != "funding-related":
        failures.append(f"funding-related K_prior mode mismatch: {funding_value} {funding_meta}")
    if all_value != 69 or all_meta.get("mode") != "all":
        failures.append(f"all K_prior mode mismatch: {all_value} {all_meta}")


def _check_settlement_previous_boundary(failures: list[str]) -> None:
    funding_ts = 1_765_000_000_000
    row = _row(
        "BTCUSDT",
        funding_ts + 5 * 60_000,
        funding_z=2.2,
        pct=0.95,
        oi=2.5,
        prior=-1.0,
        fwd30=-35.0,
        next_funding_ms=funding_ts + 480 * 60_000,
    )
    sigs = _signal_rows(
        [row],
        key=CandidateKey("BTCUSDT", "crowded_long_fade", 2.0, 0.90, 0.10, 2.0, 30),
        cost_bps=12.0,
        funding_interval_min=480,
    )
    if not sigs or not sigs[0].get("settlement_window"):
        failures.append("previous funding settlement boundary was not marked")


def _check_mixed_source_fail_closed(failures: list[str]) -> None:
    rows = build_fixture()
    rows[0]["funding_source_tier"] = "bybit_v5_rest_settled_history"
    packet = compute_stage0r(rows, k_prior=69, cost_bps=12.0)
    if packet["source_mode"] != "mixed":
        failures.append(f"mixed source_mode mismatch: {packet['source_mode']}")
    if "mixed funding source modes" not in packet["eligibility_fail_reasons"]:
        failures.append("mixed source mode did not fail closed")


def _check_single_z_backward_compat(failures: list[str]) -> None:
    rows = build_fixture()
    default_packet = compute_stage0r(rows, k_prior=69, cost_bps=12.0)
    explicit_none_packet = compute_stage0r(rows, k_prior=69, cost_bps=12.0, z_grid=None)
    if default_packet != explicit_none_packet:
        failures.append("compute_stage0r(z_grid=None) changed default v0.2 packet")
    if default_packet.get("strategy_variant") != "funding_skew_directional.v0_2":
        failures.append(f"non-sweep strategy variant changed: {default_packet.get('strategy_variant')}")
    if default_packet.get("k_new_min") != 4050:
        failures.append(f"non-sweep K_NEW_MIN changed: {default_packet.get('k_new_min')}")
    for key in (
        "sweep_per_z_cell",
        "sweep_per_symbol",
        "best_primary_cell_per_z_branch",
        "sweep_cross_z_comparison",
    ):
        if key in default_packet:
            failures.append(f"non-sweep packet unexpectedly contains sweep key: {key}")


def _check_wilson_ci_bench(failures: list[str]) -> None:
    cases = (
        (20, 4, 0.082, 0.422, 0.010),
        (100, 50, 0.404, 0.596, 0.005),
        (10, 2, 0.057, 0.510, 0.010),
    )
    for n, n_eff, exp_lower, exp_upper, tol in cases:
        ci = wilson_ci_95(n, n_eff)
        if ci is None:
            failures.append(f"wilson_ci_95({n}, {n_eff}) returned None")
            continue
        lower, upper = ci
        if abs(lower - exp_lower) > tol or abs(upper - exp_upper) > tol:
            failures.append(
                f"wilson_ci_95({n}, {n_eff})=({lower:.4f}, {upper:.4f}) "
                f"expected ({exp_lower}, {exp_upper}) tol={tol}"
            )
    if wilson_ci_95(0, 0) is not None:
        failures.append("wilson_ci_95(0, 0) should be None")
    zero_eff = wilson_ci_95(10, 0)
    if zero_eff is None:
        failures.append("wilson_ci_95(10, 0) should not be None")
    elif zero_eff[0] != 0.0:
        failures.append(f"wilson_ci_95(10, 0) lower should clamp to 0.0, got {zero_eff[0]}")


def _check_sweep_mode(failures: list[str]) -> None:
    rows = build_fixture()
    packet = compute_stage0r_sweep(rows, k_prior=0, cost_bps=12.0, z_cells=(1.0, 1.2, 1.5, 2.0))
    meta = packet.get("sweep_meta") or {}
    if meta.get("z_cells") != [1.0, 1.2, 1.5, 2.0]:
        failures.append(f"sweep z_cells mismatch: {meta}")
    if meta.get("k_new_min_v0_3") != 5400 or packet.get("k_new_min") != 5400:
        failures.append(f"sweep K_NEW_MIN mismatch: packet={packet.get('k_new_min')} meta={meta}")
    if packet.get("k_total") != 5400:
        failures.append(f"sweep k_total mismatch: {packet.get('k_total')}")
    if packet.get("strategy_variant") != "funding_skew_directional.v0_3":
        failures.append(f"sweep strategy_variant mismatch: {packet.get('strategy_variant')}")
    if len(packet.get("sweep_per_z_cell", {})) != 4:
        failures.append(f"sweep_per_z_cell len mismatch: {len(packet.get('sweep_per_z_cell', {}))}")
    if len(packet.get("sweep_per_symbol", [])) != 4 * 2 * 3:
        failures.append(f"sweep_per_symbol len mismatch: {len(packet.get('sweep_per_symbol', []))}")
    if len(packet.get("best_primary_cell_per_z_branch", [])) != 4 * 2:
        failures.append(
            "best_primary_cell_per_z_branch len mismatch: "
            f"{len(packet.get('best_primary_cell_per_z_branch', []))}"
        )
    if len(packet.get("sweep_cross_z_comparison", [])) != 2 * 3:
        failures.append(
            f"sweep_cross_z_comparison len mismatch: {len(packet.get('sweep_cross_z_comparison', []))}"
        )
    for key in ("alpha_source_id", "pooled_primary", "best_primary_cell", "panel_metadata"):
        if key not in packet:
            failures.append(f"missing v0.2 compatibility key in sweep packet: {key}")
    try:
        decoded = json.loads(json.dumps(packet, sort_keys=True))
    except TypeError as exc:
        failures.append(f"sweep packet JSON round-trip failed: {exc}")
        return
    for key in (
        "sweep_per_z_cell",
        "sweep_per_symbol",
        "best_primary_cell_per_z_branch",
        "sweep_cross_z_comparison",
    ):
        if key not in decoded:
            failures.append(f"JSON round-trip missing sweep key: {key}")
    try:
        relaxed_long = packet["sweep_per_z_cell"]["z_relaxed_z_eq_1_0"]["by_branch"]["crowded_long_fade"]
    except (KeyError, TypeError):
        failures.append("missing relaxed crowded_long_fade branch sweep summary")
        return
    if relaxed_long.get("funding_cycles_distinct") is None:
        failures.append("sweep_per_z_cell missing real funding_cycles_distinct")
    if relaxed_long.get("max_day_share") is None:
        failures.append("sweep_per_z_cell missing real max_day_share")
    if relaxed_long.get("max_funding_cycle_share") is None:
        failures.append("sweep_per_z_cell missing real max_funding_cycle_share")
    reasons = relaxed_long.get("eligibility_fail_reasons") or []
    expected_reasons = {
        "per-symbol n_eff floor failed",
        "funding cycles < 14",
        "single-day share > 25%",
        "single funding-cycle share > 25%",
    }
    missing_reasons = expected_reasons.difference(set(reasons))
    if missing_reasons:
        failures.append(f"sweep branch missing expected fail reasons: {sorted(missing_reasons)}")
    symbol_gate = relaxed_long.get("symbol_gate") or {}
    if int(symbol_gate.get("symbol_n_eff_floor_fail_count") or 0) <= 0:
        failures.append(f"per-symbol n_eff floor did not feed sweep branch gate: {symbol_gate}")
    if relaxed_long.get("promotion_ready"):
        failures.append("promotion_ready stayed true despite per-symbol/cycle/day floor failures")
    per_symbol_rows = packet.get("sweep_per_symbol", [])
    if not per_symbol_rows or not all("symbol_n_eff_floor_pass" in row for row in per_symbol_rows):
        failures.append("sweep_per_symbol missing symbol_n_eff_floor_pass fields")
    if not any(not row.get("symbol_n_eff_floor_pass") for row in per_symbol_rows):
        failures.append("sweep_per_symbol did not expose any symbol floor failure in smoke fixture")
    equal_n_eff_row = next(
        (
            row
            for row in packet.get("sweep_cross_z_comparison", [])
            if row.get("branch") == "crowded_long_fade" and row.get("symbol") == "BTCUSDT"
        ),
        None,
    )
    if not isinstance(equal_n_eff_row, dict):
        failures.append("missing cross-z row for BTCUSDT crowded_long_fade")
    elif equal_n_eff_row.get("monotonic_drop_in_n_eff") is not False:
        failures.append("strict monotonic check did not return false for equal adjacent n_eff")
    best_rows = packet.get("best_primary_cell_per_z_branch", [])
    if not best_rows or not all("branch_funding_cycles_distinct" in row for row in best_rows):
        failures.append("best_primary_cell_per_z_branch missing branch-specific cycle fields")


def _check_4z_fixture(failures: list[str]) -> None:
    rows = build_fixture()
    for row in rows:
        if row["symbol"] == "SOLUSDT":
            row["funding_zscore_25sym"] = 1.1
            row["funding_percentile_25sym"] = 0.95
            row["oi_delta_15m_pct"] = 2.5
            row["prior_5m_return_bps"] = -1.0
            row["fwd_return_30m_bps"] = -25.0
    packet = compute_stage0r_sweep(rows, k_prior=0, cost_bps=12.0, z_cells=(1.0, 1.2, 1.5, 2.0))
    per_z = packet.get("sweep_per_z_cell", {})
    required = (
        "z_relaxed_z_eq_1_0",
        "z_moderate_z_eq_1_2",
        "z_baseline_z_eq_1_5",
        "z_strict_z_eq_2_0",
    )
    for z_cell_id in required:
        if z_cell_id not in per_z:
            failures.append(f"missing z cell in 4-z fixture: {z_cell_id}")
    try:
        relaxed_long = per_z["z_relaxed_z_eq_1_0"]["by_branch"]["crowded_long_fade"]["n_total"]
        moderate_long = per_z["z_moderate_z_eq_1_2"]["by_branch"]["crowded_long_fade"]["n_total"]
    except (KeyError, TypeError):
        failures.append("4-z fixture missing branch n_total")
        return
    if not int(relaxed_long) > int(moderate_long):
        failures.append(
            f"expected z=1.0 relaxed long triggers > z=1.2, got {relaxed_long} <= {moderate_long}"
        )


def main() -> int:
    packet = compute_stage0r(build_fixture(), k_prior=69, cost_bps=12.0)
    failures: list[str] = []
    if packet["k_new_actual"] != grid_cell_count(3):
        failures.append(f"k_new_actual mismatch: {packet['k_new_actual']}")
    if packet["k_new"] != packet["k_new_min"]:
        failures.append(f"k_new floor mismatch: {packet['k_new']} min={packet['k_new_min']}")
    if not packet["k_new_floor_applied"]:
        failures.append("k_new floor was not applied for undersized smoke panel")
    if packet["k_total"] != packet["k_new"] + 69:
        failures.append(f"k_total mismatch: {packet['k_total']}")
    best = packet.get("best_primary_cell") or {}
    if best.get("branch") not in {"crowded_long_fade", "crowded_short_squeeze"}:
        failures.append("best primary branch missing")
    if not packet["pooled_primary"]["n"]:
        failures.append("pooled primary has no signals")
    if packet["funding_attribution_mode"] != "excluded":
        failures.append("funding attribution mode is not excluded")
    if packet["source_mode"] != "ws_current":
        failures.append(f"source_mode mismatch: {packet['source_mode']}")
    required_top_fields = (
        "panel_metadata",
        "per_symbol_breakdown",
        "settlement_window",
        "baseline_lift",
        "execution_cost_model",
        "pbo_metadata",
        "plateau_check",
    )
    for field in required_top_fields:
        if field not in packet:
            failures.append(f"missing top-level field: {field}")
    pooled = packet["pooled_primary"]
    for field in ("bootstrap_ci_95_60m", "bootstrap_ci_95_8h", "bootstrap_block_minutes"):
        if field not in pooled:
            failures.append(f"missing pooled field: {field}")
    exclusions = packet["exclusions"]
    for field in ("funding_missing", "funding_stale_excluded", "oi_missing", "oi_stale_excluded"):
        if field not in exclusions:
            failures.append(f"missing exclusion field: {field}")
    if packet["execution_cost_model"].get("cost_edge_ratio") is None:
        failures.append("cost_edge_ratio missing")
    if not packet["per_symbol_breakdown"]:
        failures.append("per_symbol_breakdown empty")
    _check_k_prior_modes(failures)
    _check_settlement_previous_boundary(failures)
    _check_mixed_source_fail_closed(failures)
    _check_single_z_backward_compat(failures)
    _check_wilson_ci_bench(failures)
    _check_sweep_mode(failures)
    _check_4z_fixture(failures)
    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("PASS W-AUDIT-8b Stage 0R metrics smoke")
    print(f"eligible_for_demo_canary={packet['eligible_for_demo_canary']}")
    print(f"k_total={packet['k_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
