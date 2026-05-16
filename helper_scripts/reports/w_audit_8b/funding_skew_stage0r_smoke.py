#!/usr/bin/env python3
"""Smoke test for W-AUDIT-8b Stage 0R pure metrics."""

from __future__ import annotations

import sys
from typing import Any

try:
    from .funding_skew_stage0r_metrics import compute_stage0r, grid_cell_count
    from .funding_skew_stage0r_report import fetch_k_prior
except ImportError:
    from funding_skew_stage0r_metrics import compute_stage0r, grid_cell_count  # type: ignore
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


def main() -> int:
    packet = compute_stage0r(build_fixture(), k_prior=69, cost_bps=12.0)
    failures: list[str] = []
    if packet["k_new"] != grid_cell_count(3):
        failures.append(f"k_new mismatch: {packet['k_new']}")
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
