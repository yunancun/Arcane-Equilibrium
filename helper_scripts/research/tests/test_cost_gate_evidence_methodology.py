"""證據方法學重設計回歸(B2-1:P1-2 / P2-8 / F7)。

MODULE_NOTE:
  模塊用途：覆蓋 QC spec §7 測試用例 1-5(P1-2)、10-13(P2-8)、14-17(F7)。
    P2-7 Rust 用例(6/9)在 rust/openclaw_engine/src/demo_learning_lane_tests.rs;
    用例 7(MC 誤殺率)、8(配對 L1)為 §3 診斷數學，此處以 UCB 純函數等價驗證(7)。
  依賴：conftest 把 research/ 加進 sys.path(以模組名 import lane package)。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sys

import pytest

_PROGRAM_CODE = Path(__file__).resolve().parents[3] / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))

from cost_gate_learning_lane import cost_model
from cost_gate_learning_lane import evidence_stats
from cost_gate_learning_lane.outcome_review import (
    BlockedOutcomeReviewConfig,
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
)
from program_code.ml_training.alr_candidate_learning_arbiter import (
    build_candidate_learning_decision,
)
from program_code.ml_training.alr_candidate_evidence_adapter import (
    load_candidate_evidence_snapshot,
)
from program_code.ml_training.alr_candidate_learning_projection import (
    build_candidate_aware_learning_projection,
)
from program_code.ml_training.alr_operational_repository import (
    build_candidate_learning_projection_plan,
)


NOW = dt.datetime(2026, 7, 4, 18, 0, 0, tzinfo=dt.timezone.utc)


def _quantile_payload(*, symbols, global_q75, asof=None, global_n=200):
    return {
        "asof": (asof or NOW.isoformat()),
        "symbols": symbols,
        "global": {"n": global_n, "q75": global_q75},
    }


def _blocked_admission_row(attempt_id, symbol, side, entry, ts_ms, horizon=60):
    return {
        "record_type": "probe_admission_decision",
        "attempt_id": attempt_id,
        "decision": "REJECT",
        "allowed_to_submit_order": False,
        "side_cell_key": f"strat|{symbol}|{side}",
        "event": {
            "strategy_name": "strat",
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "ts_ms": ts_ms,
        },
        "outcome_horizon_minutes": horizon,
    }


def _obs(symbol, ts_ms, price):
    return {"symbol": symbol, "ts_ms": ts_ms, "price": price}


# ---------------------------------------------------------------------------
# P1-2:成本模型
# ---------------------------------------------------------------------------


def test_cost_fallback_chain():
    """用例 1:symbol_q75 / global_q75 / toml_tier 三態 + 全部 ≥ 11.0 floor。"""
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(
            symbols=[{"symbol": "AAAUSDT", "n": 25, "q75": 14.0}],
            global_q75=12.0,
        )
    )
    # symbol A:n=25 ≥ 20 → symbol_q75。
    a = cost_model.conservative_cost_bps(symbol="AAAUSDT", horizon_minutes=60, table=table, now=NOW)
    assert a["cost_model_source"] == "symbol_q75"
    assert a["slippage_bps"] == 14.0
    # symbol B:n<20 → global_q75。
    table_b = cost_model.load_slippage_quantiles(
        _quantile_payload(
            symbols=[{"symbol": "BBBUSDT", "n": 5, "q75": 99.0}],
            global_q75=12.0,
        )
    )
    b = cost_model.conservative_cost_bps(symbol="BBBUSDT", horizon_minutes=60, table=table_b, now=NOW)
    assert b["cost_model_source"] == "global_q75"
    assert b["slippage_bps"] == 12.0
    # artifact 缺失 → toml_tier。
    c = cost_model.conservative_cost_bps(symbol="CCCUSDT", horizon_minutes=60, table=None, now=NOW)
    assert c["cost_model_source"] == "toml_tier"
    for out in (a, b, c):
        assert out["cost_bps"] >= cost_model.FEE_FLOOR_BPS


def test_cost_ge_realized_quantile():
    """用例 2(驗收 A1 直測):cost_bps == 2×(5.5+q75)×1.3(funding=0)。"""
    q75 = 24.97
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(symbols=[{"symbol": "DDDUSDT", "n": 50, "q75": q75}], global_q75=q75)
    )
    out = cost_model.conservative_cost_bps(symbol="DDDUSDT", horizon_minutes=60, table=table, now=NOW)
    expected = 2.0 * (5.5 + q75) * 1.3
    assert out["cost_bps"] == pytest.approx(expected, abs=1e-9)


def test_cost_floor_and_thin_sample():
    """負滑點/畸形 → 夾到 fee_floor 並改記 source。"""
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(symbols=[{"symbol": "EEEUSDT", "n": 30, "q75": -100.0}], global_q75=-100.0)
    )
    out = cost_model.conservative_cost_bps(symbol="EEEUSDT", horizon_minutes=60, table=table, now=NOW)
    assert out["cost_bps"] == cost_model.FEE_FLOOR_BPS
    assert out["cost_model_source"] == "fee_floor"


def test_stale_artifact_falls_back_to_toml():
    """artifact asof 超 48h → 視為不新鮮 → toml_tier。"""
    stale = NOW - dt.timedelta(hours=72)
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(
            symbols=[{"symbol": "FFFUSDT", "n": 30, "q75": 14.0}],
            global_q75=12.0,
            asof=stale.isoformat(),
        )
    )
    out = cost_model.conservative_cost_bps(symbol="FFFUSDT", horizon_minutes=60, table=table, now=NOW)
    assert out["cost_model_source"] == "toml_tier"


def test_funding_crossing_count():
    """用例 5:240m horizon 跨 1 個 8h 結算;60m 不跨(對齊 epoch 邊界)。"""
    # 對齊 8h 邊界的 event ts:2026-07-04T00:00:00Z。
    base = int(dt.datetime(2026, 7, 4, 0, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    # 從邊界起 240m 內下一個結算在 +8h → 不跨(240m<480m)。取 event 在 +5h 起 240m 跨 +8h。
    event_5h = base + 5 * 3_600_000
    assert cost_model.funding_crossing_count(event_ts_ms=event_5h, horizon_minutes=240) == 1
    # 60m from +5h → +6h,不跨 +8h → 0。
    assert cost_model.funding_crossing_count(event_ts_ms=event_5h, horizon_minutes=60) == 0
    # 1h fundingInterval:240m horizon 最多 4 次(addendum §C errata)。
    assert (
        cost_model.funding_crossing_count(
            event_ts_ms=base + 1, horizon_minutes=240, funding_interval_hours=1.0
        )
        == 4
    )


# ---------------------------------------------------------------------------
# P1-2c / F1(c):overlay flip + realized 矛盾
# ---------------------------------------------------------------------------


def _blocked_outcome_row(
    attempt_id, side_cell, gross, *, cost_model_version=None, entry_ts_ms=None
):
    row = {
        "record_type": "blocked_signal_outcome",
        "attempt_id": attempt_id,
        "side_cell_key": side_cell,
        "symbol": side_cell.split("|")[1],
        "strategy_name": side_cell.split("|")[0],
        "side": side_cell.split("|")[2],
        "horizon_minutes": 60,
        "gross_bps": gross,
        "realized_net_bps": gross - 4.0,
        "net_bps_optimistic": gross - 4.0,
        "cost_bps": 4.0,
    }
    if cost_model_version:
        row["cost_model_version"] = cost_model_version
    if entry_ts_ms is not None:
        row["entry_ts_ms"] = entry_ts_ms
    return row


# F1 fixture 時間軸:每日 per_day 個 entry、日內 1h 間距(≥60m horizon → 非重疊
# 窗全入選),跨日分散滿足預註冊 §3 E2(days≥5)/E3(top-day≤50%)。
_DAY_MS = 86_400_000
_HOUR_MS = 3_600_000
_ENTRY_BASE_TS_MS = 1_782_000_000_000  # 整日 UTC 邊界


def _spread_entry_ts(index: int, *, per_day: int = 5) -> int:
    return (
        _ENTRY_BASE_TS_MS
        + (index // per_day) * _DAY_MS
        + (index % per_day) * _HOUR_MS
    )


def _with_complete_candidate_lineage(
    row,
    *,
    strategy_version="v1",
    config_hash="a" * 64,
):
    complete = _with_typed_candidate_learning_context(row)
    context = dict(complete["candidate_summary"]["candidate_learning_context"])
    context["strategy_version"] = strategy_version
    context["strategy_config_hash"] = config_hash
    context["target_regime_hash"] = "b" * 64
    complete["candidate_summary"] = {"candidate_learning_context": context}
    return complete


def _with_typed_candidate_learning_context(row):
    typed = dict(row)
    daily_buckets = [
        {
            "utc_date": f"2026-{month_day}",
            "scan_complete": True,
            "distinct_entries": 5,
        }
        for month_day in (
            "06-27",
            "06-28",
            "06-29",
            "06-30",
            "07-01",
            "07-02",
            "07-03",
        )
    ]
    estimator_payload = {
        "daily_buckets": daily_buckets,
        "estimated_rows_scanned": 700,
        "predicted_canonical_bytes": 7_000,
        "zero_resource_attested": False,
    }
    resource = dict(estimator_payload)
    resource["resource_estimator_hash"] = hashlib.sha256(
        json.dumps(
            estimator_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    typed["candidate_summary"] = {
        "candidate_learning_context": {
            "strategy_version": "v3.2.1",
            "strategy_config_hash": "1" * 64,
            "target_regime_context": {
                "label": "range_low_vol",
                "utc_date": "2026-07-03",
                "point_in_time": "D-1",
            },
            "target_regime_hash": "2" * 64,
            "venue": "bybit",
            "product": "linear_perpetual",
            "evidence_engine_mode": "demo",
            "evidence_regime_label": "neutral|low_vol|liquid",
            "hidden_oos_consumed": False,
            "context_hashes": {
                "data": "3" * 64,
                "evidence": "4" * 64,
                "cost": "5" * 64,
                "portfolio": "6" * 64,
            },
            "resource": resource,
            "portfolio": {
                "sector_exposure_share": "0.10",
                "strategy_active_target_share": "0.20",
                "beta_to_portfolio": "0.30",
            },
            "proof": {
                "proof_stage": 1,
                "completed_proof_stages": [0, 1],
                "next_gap": {"kind": "NONE", "code": "DATA_GATES_READY"},
            },
        }
    }
    return typed


def test_learning_candidate_board_emits_typed_arbiter_input_with_cr1_cluster_se():
    day_effects = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    rows = []
    gross_values = []
    for index in range(30):
        gross = -20.0 + day_effects[index // 5] + (index % 5) * 0.1
        gross_values.append(gross)
        rows.append(
            _with_typed_candidate_learning_context(
                _blocked_outcome_row(
                    f"typed-{index}",
                    "strat|TYPEDUSDT|Buy",
                    gross,
                    cost_model_version="conservative_v1",
                    entry_ts_ms=_spread_entry_ts(index),
                )
            )
        )

    packet = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(mean_abs=2.0, cvar90=8.0),
        now_utc=NOW,
    )

    candidate = packet["learning_candidate_board"]["candidate_rows"][0]
    typed = candidate["arbiter_input"]
    assert candidate["arbiter_input_complete"] is True
    assert candidate["selection_eligible"] is True
    assert typed["schema_version"] == "alr_candidate_arbiter_input_v1"
    assert typed["identity"]["engine_mode"] == "shadow"
    assert typed["identity"]["evidence_engine_mode"] == "demo"
    assert typed["identity"]["config_hash"] == "1" * 64
    assert typed["context_hashes"] == {
        "data": "3" * 64,
        "evidence": "4" * 64,
        "cost": "5" * 64,
        "portfolio": "6" * 64,
    }
    assert typed["quality"]["hidden_oos_consumed"] is False
    assert typed["quality"]["replica_inconsistency_count"] == 0
    assert typed["evidence"]["n_eff"] == 30
    assert typed["evidence"]["utc_day_count"] == 6
    assert typed["evidence"]["proof_stage"] == 1
    assert typed["evidence"]["completed_proof_stages"] == [0, 1]
    assert typed["evidence"]["next_gap"] == {
        "kind": "NONE",
        "code": "DATA_GATES_READY",
    }
    expected_nets = [gross - 15.0 for gross in gross_values]
    expected_mean = sum(expected_nets) / len(expected_nets)
    cluster_sums = []
    for day in range(6):
        cluster_sums.append(
            sum(value - expected_mean for value in expected_nets[day * 5 : day * 5 + 5])
        )
    expected_variance = (
        (6.0 / 5.0)
        * sum(value * value for value in cluster_sums)
        / (len(expected_nets) ** 2)
    )
    assert typed["evidence"]["mean_net_e"] == pytest.approx(expected_mean)
    assert typed["evidence"]["day_cluster_variance"] == pytest.approx(
        expected_variance
    )
    assert typed["evidence"]["cluster_se"] == pytest.approx(
        math.sqrt(expected_variance)
    )
    resource_payload = {
        key: value
        for key, value in typed["resource"].items()
        if key != "resource_estimator_hash"
    }
    assert typed["resource"]["resource_estimator_hash"] == hashlib.sha256(
        json.dumps(
            resource_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert len(typed["resource"]["daily_buckets"]) == 7
    assert typed["portfolio"]["beta_to_portfolio"] == "0.30"
    policy_body = {
        "decision_ts_s": int(NOW.replace(hour=0).timestamp()),
        "as_of_utc_date": "2026-07-04",
        "algorithm_version": "candidate_learning_arbiter_v1",
        "tie_break_version": "candidate_learning_tie_break_v1",
        "q18_scale": 18,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }
    policy = dict(policy_body)
    stable_policy = {
        key: value
        for key, value in policy_body.items()
        if key not in {"decision_ts_s", "as_of_utc_date"}
    }
    policy["policy_config_hash"] = hashlib.sha256(
        json.dumps(
            stable_policy,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    decision = build_candidate_learning_decision(
        source_head="a" * 40,
        scanner_research_seeds=[],
        candidate_evidence_board=[typed],
        prior_decisions=[],
        policy=policy,
    )
    assert decision["decision"] == "QUALIFIED_CANDIDATE_SELECTED", decision
    assert decision["candidate_assessments"][0]["state"] == "DECISION_READY"


def test_real_board_file_flows_through_bounded_adapter_and_projection(
    tmp_path: Path,
):
    rows = []
    day_effects = (-3.0, -2.0, -1.0, 1.0, 2.0, 3.0)
    for index in range(30):
        gross = -20.0 + day_effects[index // 5] + (index % 5) * 0.1
        rows.append(
            _with_typed_candidate_learning_context(
                _blocked_outcome_row(
                    f"integration-{index}",
                    "strat|TYPEDUSDT|Buy",
                    gross,
                    cost_model_version="conservative_v1",
                    entry_ts_ms=_spread_entry_ts(index),
                )
            )
        )
    packet = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(mean_abs=2.0, cvar90=8.0),
        now_utc=NOW,
    )
    snapshot_path = tmp_path / "blocked_outcome_review_20260704T180000Z.json"
    snapshot_path.write_text(
        json.dumps(packet, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evaluated_at = "2026-07-04T18:01:00Z"
    snapshot = load_candidate_evidence_snapshot(
        tmp_path,
        evaluated_at=evaluated_at,
        max_age_seconds=3_600,
        max_files=8,
        max_bytes=2_000_000,
    )
    policy_body = {
        "decision_ts_s": int(
            dt.datetime.fromisoformat(evaluated_at.replace("Z", "+00:00")).timestamp()
        ),
        "as_of_utc_date": "2026-07-04",
        "algorithm_version": "candidate_learning_arbiter_v1",
        "tie_break_version": "candidate_learning_tie_break_v1",
        "q18_scale": 18,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }
    stable_policy = {
        key: value
        for key, value in policy_body.items()
        if key not in {"decision_ts_s", "as_of_utc_date"}
    }
    policy = {
        **policy_body,
        "policy_config_hash": hashlib.sha256(
            json.dumps(
                stable_policy,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    cycles = [
        {
            "source_hash": f"{ordinal:064x}",
            "source_key": f"scan-{ordinal}|2026-07-04T17:5{ordinal}:00Z",
            "source_ts": f"2026-07-04T17:5{ordinal}:00Z",
            "canonical_payload": {
                "candidates": [{"symbol": "TYPEDUSDT"}],
                "added": ["TYPEDUSDT"] if ordinal == 1 else [],
            },
        }
        for ordinal in range(1, 4)
    ]

    projection = build_candidate_aware_learning_projection(
        source_head="a" * 40,
        cycles=cycles,
        evidence_snapshot=snapshot,
        prior_decisions=[],
        policy=policy,
    )
    plan = build_candidate_learning_projection_plan(projection)

    assert snapshot["source_status"] == "READY"
    assert projection["decision"]["decision_code"] == "QUALIFIED_CANDIDATE_SELECTED"
    assert projection["decision"]["selected_candidate"]["identity"]["symbol"] == "TYPEDUSDT"
    assert plan["artifact"]["canonical_payload"]["decision"] == projection["decision"]
    assert plan["artifact"]["canonical_payload"]["training_run_created"] is False


def test_learning_candidate_board_aggregates_regimes_across_same_family():
    rows = []
    for index, label in enumerate(
        (
            "bull|high_vol|liquid",
            "bull|high_vol|liquid",
            "bear|low_vol|thin",
            "bear|low_vol|thin",
        )
    ):
        row = _with_typed_candidate_learning_context(
            _blocked_outcome_row(
                f"regime-{index}",
                "strat|REGIMEUSDT|Buy",
                -20.0 + index,
                cost_model_version="conservative_v1",
                entry_ts_ms=_spread_entry_ts(index, per_day=1),
            )
        )
        context = dict(row["candidate_summary"]["candidate_learning_context"])
        context["evidence_regime_label"] = label
        row["candidate_summary"] = {"candidate_learning_context": context}
        rows.append(row)

    packet = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(mean_abs=2.0, cvar90=8.0),
        now_utc=NOW,
    )

    board_rows = packet["learning_candidate_board"]["candidate_rows"]
    assert len(board_rows) == 1
    for candidate in board_rows:
        counts = candidate["regime_entry_counts"]
        assert set(counts) == {
            f"{trend}|{volatility}|{liquidity}"
            for trend in ("bear", "neutral", "bull")
            for volatility in ("low_vol", "mid_vol", "high_vol")
            for liquidity in ("liquid", "thin")
        } | {"unknown"}
        assert counts["bear|low_vol|thin"] == 2
        assert counts["bull|high_vol|liquid"] == 2
        assert sum(counts.values()) == candidate["n_eff"] == 4
        coverage = candidate["regime_coverage_inputs"]
        assert coverage["composite_bucket_universe_size"] == 18
        assert coverage["observed_composite_bucket_count"] == 2
        assert coverage["effective_entry_count"] == candidate["n_eff"]
        assert coverage["unknown_regime_share"] == 0.0


@pytest.mark.parametrize("hidden_value", (True, None))
def test_learning_candidate_board_never_synthesizes_hidden_oos_false(
    hidden_value,
):
    row = _with_typed_candidate_learning_context(
        _blocked_outcome_row(
            "hidden-oos",
            "strat|HIDDENUSDT|Buy",
            -20.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(0),
        )
    )
    context = dict(row["candidate_summary"]["candidate_learning_context"])
    if hidden_value is None:
        context.pop("hidden_oos_consumed")
    else:
        context["hidden_oos_consumed"] = hidden_value
    row["candidate_summary"] = {"candidate_learning_context": context}

    candidate = build_blocked_signal_outcome_review([row], now_utc=NOW)[
        "learning_candidate_board"
    ]["candidate_rows"][0]

    assert candidate["selection_eligible"] is False
    if hidden_value is True:
        assert candidate["arbiter_input_complete"] is True
        assert candidate["arbiter_input"]["quality"]["hidden_oos_consumed"] is True
        assert "HIDDEN_OOS_CONSUMED" in candidate["blockers"]
    else:
        assert candidate["arbiter_input_complete"] is False
        assert "HIDDEN_OOS_STATUS_MISSING_OR_INVALID" in candidate["blockers"]


def test_learning_candidate_board_accepts_finite_beta_above_one() -> None:
    row = _with_typed_candidate_learning_context(
        _blocked_outcome_row(
            "finite-beta",
            "strat|BETAUSDT|Buy",
            -20.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(0),
        )
    )
    context = dict(row["candidate_summary"]["candidate_learning_context"])
    context["portfolio"] = {
        **context["portfolio"],
        "beta_to_portfolio": "1.5",
    }
    row["candidate_summary"] = {"candidate_learning_context": context}

    candidate = build_blocked_signal_outcome_review([row], now_utc=NOW)[
        "learning_candidate_board"
    ]["candidate_rows"][0]

    assert candidate["arbiter_input_complete"] is True
    assert "PORTFOLIO_METRICS_MISSING_OR_INVALID" not in candidate["blockers"]
    assert candidate["arbiter_input"]["portfolio"]["beta_to_portfolio"] == "1.5"


def test_learning_candidate_board_uses_full_universe_not_legacy_top16():
    rows = [
        _blocked_outcome_row(
            f"full-{index:02d}",
            f"strat|S{index:02d}USDT|Buy",
            10.0 + index,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(index),
        )
        for index in range(17)
    ]

    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)

    assert len(packet["top_side_cells"]) == 16
    board = packet["learning_candidate_board"]
    assert board["schema_version"] == "cost_gate_learning_candidate_board_v1"
    assert board["candidate_universe_complete"] is True
    assert len(board["candidate_rows"]) == 17


def test_learning_candidate_board_splits_horizons_without_changing_legacy_cell():
    short = _blocked_outcome_row(
        "mixed-60",
        "strat|MIXEDUSDT|Buy",
        12.0,
        cost_model_version="conservative_v1",
        entry_ts_ms=_spread_entry_ts(0),
    )
    long = _blocked_outcome_row(
        "mixed-240",
        "strat|MIXEDUSDT|Buy",
        14.0,
        cost_model_version="conservative_v1",
        entry_ts_ms=_spread_entry_ts(1),
    )
    long["horizon_minutes"] = 240

    packet = build_blocked_signal_outcome_review([short, long], now_utc=NOW)

    legacy = packet["top_side_cells"]
    assert len(legacy) == 1
    assert legacy[0]["horizon_minutes"] == [60, 240]
    board_rows = packet["learning_candidate_board"]["candidate_rows"]
    assert [row["horizon_minutes"] for row in board_rows] == [60, 240]
    assert [row["raw_outcome_count"] for row in board_rows] == [1, 1]


def test_learning_candidate_board_keeps_legacy_row_but_blocks_incomplete_identity():
    legacy = _blocked_outcome_row(
        "legacy-lineage",
        "strat|LEGACYUSDT|Buy",
        12.0,
        cost_model_version="conservative_v1",
        entry_ts_ms=_spread_entry_ts(0),
    )

    packet = build_blocked_signal_outcome_review([legacy], now_utc=NOW)

    row = packet["learning_candidate_board"]["candidate_rows"][0]
    assert row["identity_complete"] is False
    assert row["arbiter_input_complete"] is False
    assert row["selection_eligible"] is False
    assert "IDENTITY_LINEAGE_INCOMPLETE" in row["blockers"]
    assert "CANDIDATE_LEARNING_CONTEXT_MISSING" in row["blockers"]
    assert "DATA_CONTEXT_HASH_MISSING_OR_INVALID" in row["blockers"]
    assert "RESOURCE_ESTIMATOR_HASH_MISSING_OR_INVALID" in row["blockers"]
    assert "RESOURCE_DAILY_BUCKETS_INCOMPLETE" in row["blockers"]
    assert "PORTFOLIO_METRICS_MISSING_OR_INVALID" in row["blockers"]
    assert "PROOF_PREFIX_MISSING_OR_INVALID" in row["blockers"]
    assert row["candidate_identity"]["strategy_version"] is None
    assert row["candidate_identity"]["strategy_config_hash"] is None
    assert row["candidate_identity"]["target_regime_context"] is None
    assert row["arbiter_input"]["identity"]["engine_mode"] == "shadow"
    assert row["arbiter_input"]["identity"]["evidence_engine_mode"] is None


def test_learning_candidate_board_retains_complete_identity_without_version_pooling():
    base = _blocked_outcome_row(
        "identity-v1",
        "strat|IDENTITYUSDT|Buy",
        12.0,
        cost_model_version="conservative_v1",
        entry_ts_ms=_spread_entry_ts(0),
    )
    first = _with_complete_candidate_lineage(base, strategy_version="v1")
    second = _with_complete_candidate_lineage(
        {
            **base,
            "attempt_id": "identity-v2",
            "entry_ts_ms": _spread_entry_ts(1),
        },
        strategy_version="v2",
        config_hash="c" * 64,
    )

    packet = build_blocked_signal_outcome_review([second, first], now_utc=NOW)

    board_rows = packet["learning_candidate_board"]["candidate_rows"]
    assert len(board_rows) == 2
    identities = [row["candidate_identity"] for row in board_rows]
    assert [identity["strategy_version"] for identity in identities] == ["v1", "v2"]
    assert identities[0]["strategy_config_hash"] == "a" * 64
    assert identities[1]["strategy_config_hash"] == "c" * 64
    assert all(row["identity_complete"] is True for row in board_rows)
    candidate_ids = [row["candidate_id"] for row in board_rows]
    assert len(set(candidate_ids)) == 2
    assert all(len(candidate_id) == 64 for candidate_id in candidate_ids)


def test_learning_candidate_board_splits_target_regimes_within_stable_family():
    rows = []
    regimes = (
        ("range_low_vol", "2" * 64),
        ("trend_high_vol", "7" * 64),
    )
    for regime_index, (label, regime_hash) in enumerate(regimes):
        for observation_index, gross in enumerate((-20.0, -18.0)):
            row = _with_typed_candidate_learning_context(
                _blocked_outcome_row(
                    f"regime-identity-{regime_index}-{observation_index}",
                    "strat|REGIMEIDENTITYUSDT|Buy",
                    gross,
                    cost_model_version="conservative_v1",
                    entry_ts_ms=_spread_entry_ts(
                        regime_index + observation_index * 5
                    ),
                )
            )
            context = dict(row["candidate_summary"]["candidate_learning_context"])
            context["target_regime_context"] = {
                **context["target_regime_context"],
                "label": label,
            }
            context["target_regime_hash"] = regime_hash
            row["candidate_summary"] = {"candidate_learning_context": context}
            rows.append(row)

    board = build_blocked_signal_outcome_review(rows, now_utc=NOW)[
        "learning_candidate_board"
    ]

    assert len(board["candidate_rows"]) == 2
    assert {
        row["candidate_identity"]["target_regime_context"]["label"]
        for row in board["candidate_rows"]
    } == {label for label, _ in regimes}
    assert {
        row["candidate_identity"]["target_regime_hash"]
        for row in board["candidate_rows"]
    } == {regime_hash for _, regime_hash in regimes}
    assert len({row["candidate_family_key"] for row in board["candidate_rows"]}) == 1
    assert len({row["candidate_id"] for row in board["candidate_rows"]}) == 2

    policy_body = {
        "decision_ts_s": int(NOW.replace(hour=0).timestamp()),
        "as_of_utc_date": "2026-07-04",
        "algorithm_version": "candidate_learning_arbiter_v1",
        "tie_break_version": "candidate_learning_tie_break_v1",
        "q18_scale": 18,
        "thresholds": {
            "e1_n_eff_min": 30,
            "e2_utc_days_min": 5,
            "e3_top_day_share_max": "0.5",
            "e4_censored_share_max": "0.3",
        },
        "row_budget": 10_000,
        "byte_budget": 1_000_000,
        "collection_window_days": 7,
        "max_new_entries_per_window": 70,
        "cooldown_seconds": 1_800,
        "unknown_portfolio_penalty": "1",
    }
    stable_policy = {
        key: value
        for key, value in policy_body.items()
        if key not in {"decision_ts_s", "as_of_utc_date"}
    }
    policy = {
        **policy_body,
        "policy_config_hash": hashlib.sha256(
            json.dumps(
                stable_policy,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    decision = build_candidate_learning_decision(
        source_head="a" * 40,
        scanner_research_seeds=[],
        candidate_evidence_board=[
            row["arbiter_input"] for row in board["candidate_rows"]
        ],
        prior_decisions=[],
        policy=policy,
    )
    assessments = decision["candidate_assessments"]
    assert len(assessments) == 2
    assert len({item["family_key"] for item in assessments}) == 1
    assert len({item["evaluation_id"] for item in assessments}) == 2


def test_dynamic_evaluation_context_conflict_does_not_fragment_stable_cohort():
    first = _with_typed_candidate_learning_context(
        _blocked_outcome_row(
            "cohort-first",
            "strat|COHORTUSDT|Buy",
            -20.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(0),
        )
    )
    second = _with_typed_candidate_learning_context(
        _blocked_outcome_row(
            "cohort-second",
            "strat|COHORTUSDT|Buy",
            -19.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(1),
        )
    )
    context = dict(second["candidate_summary"]["candidate_learning_context"])
    context["portfolio"] = {
        **context["portfolio"],
        "strategy_active_target_share": "0.25",
    }
    context["context_hashes"] = {
        **context["context_hashes"],
        "portfolio": "9" * 64,
    }
    second["candidate_summary"] = {"candidate_learning_context": context}

    board = build_blocked_signal_outcome_review(
        [second, first], now_utc=NOW
    )["learning_candidate_board"]

    assert len(board["candidate_rows"]) == 1
    candidate = board["candidate_rows"][0]
    assert candidate["raw_outcome_count"] == 2
    assert candidate["arbiter_input_complete"] is False
    assert candidate["selection_eligible"] is False
    assert "CANDIDATE_EVALUATION_CONTEXT_CONFLICT" in candidate["blockers"]


def test_learning_candidate_board_reports_dedup_n_eff_not_raw_rows():
    rows = []
    for index, offset_ms in enumerate((0, 5_000, 30_000)):
        row = _blocked_outcome_row(
            f"duplicate-{index}",
            "strat|DUPUSDT|Buy",
            12.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(0) + offset_ms,
        )
        rows.append(_with_complete_candidate_lineage(row))

    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)

    candidate = packet["learning_candidate_board"]["candidate_rows"][0]
    assert candidate["raw_outcome_count"] == 3
    assert candidate["distinct_entry_observation_count"] == 1
    assert candidate["duplicate_outcome_row_count"] == 2
    assert candidate["n_eff"] == 1
    assert candidate["window_overlap_excluded_entry_count"] == 0


def test_learning_candidate_board_hash_is_canonical_and_permutation_stable():
    rows = []
    for index, symbol in enumerate(("HASHBUSDT", "HASHAUSDT")):
        row = _blocked_outcome_row(
            f"hash-{index}",
            f"strat|{symbol}|Buy",
            12.0 + index,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(index),
        )
        rows.append(_with_complete_candidate_lineage(row))

    forward = build_blocked_signal_outcome_review(rows, now_utc=NOW)[
        "learning_candidate_board"
    ]
    reversed_board = build_blocked_signal_outcome_review(
        list(reversed(rows)), now_utc=NOW
    )["learning_candidate_board"]

    assert forward == reversed_board
    assert len(forward["board_hash"]) == 64
    without_hash = {key: value for key, value in forward.items() if key != "board_hash"}
    encoded = json.dumps(
        without_hash,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    assert forward["board_hash"] == hashlib.sha256(encoded).hexdigest()


def test_learning_candidate_board_exposes_cost_censoring_and_regime_inputs():
    rows = [
        _with_complete_candidate_lineage(
            _blocked_outcome_row(
                f"qualified-{index}",
                "strat|QUALIFIEDUSDT|Buy",
                -20.0 + (index % 5) - 2.0,
                cost_model_version="conservative_v1",
                entry_ts_ms=_spread_entry_ts(index),
            )
        )
        for index in range(30)
    ]
    artifact = _expected_cost_artifact(mean_abs=2.0, cvar90=8.0)

    packet = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=artifact,
        now_utc=NOW,
    )

    candidate = packet["learning_candidate_board"]["candidate_rows"][0]
    assert packet["top_side_cells"][0]["review_candidate"] is False
    assert candidate["identity_complete"] is True
    assert candidate["selection_eligible"] is False
    assert "DAY_CLUSTER_VARIANCE_DEGENERATE" in candidate["blockers"]
    assert candidate["n_eff"] == 30
    assert candidate["distinct_entry_utc_days"] == 6
    assert candidate["top_entry_day_share"] == pytest.approx(1.0 / 6.0)
    assert candidate["censored_share"] == 0.0
    assert candidate["expected_cost_recomputable_share"] == 1.0
    assert candidate["tail_cost_recomputable_share"] == 1.0
    assert candidate["regime_entry_counts"]["neutral|low_vol|liquid"] == 30
    assert sum(candidate["regime_entry_counts"].values()) == 30
    assert candidate["hidden_oos_consumed"] is False


def test_learning_candidate_board_invalid_uncensored_row_blocks_selection():
    rows = [
        _with_complete_candidate_lineage(
            _blocked_outcome_row(
                f"valid-{index}",
                "strat|INVALIDUSDT|Sell",
                -20.0 + (index % 5),
                cost_model_version="conservative_v1",
                entry_ts_ms=_spread_entry_ts(index),
            )
        )
        for index in range(30)
    ]
    invalid = _with_complete_candidate_lineage(
        {
            **rows[0],
            "attempt_id": "invalid-net",
            "entry_ts_ms": _spread_entry_ts(31),
            "realized_net_bps": None,
        }
    )
    rows.append(invalid)

    packet = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(mean_abs=2.0, cvar90=8.0),
        now_utc=NOW,
    )

    candidate = packet["learning_candidate_board"]["candidate_rows"][0]
    assert candidate["raw_outcome_count"] == 31
    assert candidate["valid_uncensored_outcome_count"] == 30
    assert candidate["invalid_outcome_row_count"] == 1
    assert "INVALID_OUTCOME_ROWS_PRESENT" in candidate["blockers"]
    assert candidate["selection_eligible"] is False


def test_learning_candidate_board_censoring_share_uses_raw_plus_censored_rows():
    rows = [
        _with_complete_candidate_lineage(
            _blocked_outcome_row(
                f"uncensored-{index}",
                "strat|CENSORUSDT|Buy",
                -20.0 + (index % 5),
                cost_model_version="conservative_v1",
                entry_ts_ms=_spread_entry_ts(index),
            )
        )
        for index in range(30)
    ]
    for index in range(14):
        rows.append(
            {
                **rows[0],
                "attempt_id": f"censored-{index}",
                "entry_ts_ms": _spread_entry_ts(40 + index),
                "censored": True,
                "gross_bps": None,
                "realized_net_bps": None,
            }
        )

    packet = build_blocked_signal_outcome_review(
        rows,
        slippage_quantiles=_expected_cost_artifact(mean_abs=2.0, cvar90=8.0),
        now_utc=NOW,
    )

    candidate = packet["learning_candidate_board"]["candidate_rows"][0]
    assert candidate["raw_outcome_count"] == 44
    assert candidate["censored_count"] == 14
    assert candidate["censored_share"] == pytest.approx(14.0 / 44.0)
    assert "CENSORING_EXCESS" in candidate["blockers"]
    assert candidate["selection_eligible"] is False


def test_backfill_overlay_flip():
    """用例 3:legacy 樂觀淨值過線,overlay cost=25.0 → candidate=False ∧ flipped=True。"""
    # 5 筆 legacy,gross 帶擾動(全同值會觸發零變異數 dedup-escape 疑點),
    # net_opt = gross−4 全正 → 樂觀下過線;跨 5 UTC 日滿足 E2/E3。
    grosses = [8.0, 9.0, 10.0, 9.5, 8.5]
    rows = [
        _blocked_outcome_row(
            f"a{i + 1}",
            "strat|GGGUSDT|Buy",
            gross,
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i, gross in enumerate(grosses)
    ]
    overlay = {
        f"a{i + 1}": {
            "attempt_id": f"a{i + 1}",
            "cost_bps_conservative": 25.0,
            "realized_net_bps_conservative": gross - 25.0,
            "cost_model_version": "conservative_v1",
            "cost_model_source": "global_q75",
        }
        for i, gross in enumerate(grosses)
    }
    # F1:n_eff=5 fixture,n_eff 門檻對齊到 5(flip 語義本測不涉 n_eff floor)。
    cfg = BlockedOutcomeReviewConfig(min_effective_entries_per_side_cell=5)
    packet = build_blocked_signal_outcome_review(
        rows, overlay=overlay, cfg=cfg, now_utc=NOW
    )
    cell = packet["top_side_cells"][0]
    assert cell["review_candidate"] is False
    assert cell["candidacy_flipped_by_cost_model"] is True
    assert packet["candidacy_flipped_by_cost_model_count"] == 1


def test_realized_contradiction_flag():
    """用例 4:edge EV=−16.76/n=18 vs counterfactual avg 高 → EXECUTION_REALISM_SUSPECT。"""
    rows = [
        _blocked_outcome_row(
            f"c{i}",
            "strat|HHHUSDT|Buy",
            gross,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i, gross in enumerate([77.0, 79.0, 81.0])
    ]
    edge = {"strat::HHHUSDT": {"realized_ev_bps": -16.76, "n": 18}}
    packet = build_blocked_signal_outcome_review(rows, edge_estimates=edge, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["realized_contradiction"] is True
    assert cell["status"] == "EXECUTION_REALISM_SUSPECT"
    assert cell["review_candidate"] is False


# ---------------------------------------------------------------------------
# P2-8:多重比較
# ---------------------------------------------------------------------------


def test_bh_fdr_vector():
    """用例 10:手算 fixture,q=0.10,m=15 → 通過集 = 兩最小 p。"""
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.5] + [0.9] * 8
    assert len(p) == 15
    passed = evidence_stats.bh_fdr_pass(p, 0.10)
    assert passed[0] is True and passed[1] is True
    assert not any(passed[2:])


def test_signflip_selection():
    """用例 11:全 null 80 cells → p 近均勻(多數 >0.05);注入強 cell → p<0.05。"""
    rng = __import__("random").Random(7)
    # 全 null:80 cells,每 cell 12 個對稱樣本。多次重複 ≥8/10 次 p>0.05。
    above = 0
    for trial in range(10):
        cells = [[rng.gauss(0.0, 50.0) for _ in range(12)] for _ in range(80)]
        out = evidence_stats.sign_flip_selection_p_value(cells, b=300, seed=1000 + trial)
        if out["p_selection"] > 0.05:
            above += 1
    assert above >= 8, f"全 null p>0.05 次數={above}"
    # 注入單一強 cell(μ≈5σ/√n)→ p 應顯著。
    strong = [[100.0] * 12] + [[rng.gauss(0.0, 20.0) for _ in range(12)] for _ in range(79)]
    strong_out = evidence_stats.sign_flip_selection_p_value(strong, b=500, seed=42)
    assert strong_out["p_selection"] < 0.05


def test_selection_universe_required():
    """用例 12:packet 必含 selection_universe(消費端 fail-closed on missing K)。"""
    rows = [_blocked_outcome_row(f"s{i}", "strat|IIIUSDT|Buy", 5.0) for i in range(3)]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    assert "selection_universe" in packet
    su = packet["selection_universe"]
    assert su["k_effective"] == su["n_side_cells"] * su["n_horizons"]
    assert "headline_selection" in packet


def test_bh_fdr_gates_review_candidate():
    """conservative 過線但 BH 未過 → 撤下候選,標 EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED。"""
    # 高變異數 cell:avg 剛過 0 但 t 檢定不顯著 → BH 不過。
    nets = [1.0, -80.0, 82.0, -78.0, 80.0, 1.0]
    rows = []
    for i, net in enumerate(nets):
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"b{i}",
                "side_cell_key": "strat|JJJUSDT|Buy",
                "symbol": "JJJUSDT",
                "strategy_name": "strat",
                "side": "Buy",
                "horizon_minutes": 60,
                # F1:6 個 distinct UTC 日各 1 entry(n_eff=6、E2/E3 過,BH 撤下
                # 路徑不因 eligibility 被搶先攔截)。
                "entry_ts_ms": _spread_entry_ts(i, per_day=1),
                "gross_bps": net + 4.0,
                "realized_net_bps": net,
                "net_bps_optimistic": net,
                "cost_bps": 4.0,
                "cost_model_version": "conservative_v1",
            }
        )
    # n_eff=6 fixture:n_eff 門檻對齊到 6,讓 cell 先成候選、再走 BH 撤下路徑
    # (門檻默認 30 下 cell 會先被 n_eff floor 攔,測不到 BH revocation 本體)。
    cfg = BlockedOutcomeReviewConfig(
        min_net_positive_pct=0.0, min_effective_entries_per_side_cell=6
    )
    packet = build_blocked_signal_outcome_review(rows, cfg=cfg, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["bh_fdr_pass"] is False
    assert cell["review_candidate"] is False
    assert cell["status"] == "EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED"


# ---------------------------------------------------------------------------
# F7:censored 出場/入場
# ---------------------------------------------------------------------------


def test_exit_censored():
    """用例 14:exit 後 40min 才有價(horizon 60m,max_exit_delay 15min)→ censored。"""
    ts = 1_782_000_000_000
    ledger = [_blocked_admission_row("e1", "KKKUSDT", "Buy", 100.0, ts, horizon=60)]
    obs = [
        _obs("KKKUSDT", ts, 100.0),  # entry
        _obs("KKKUSDT", ts + 60 * 60_000 + 40 * 60_000, 101.0),  # exit 遲 40min
    ]
    now = dt.datetime.fromtimestamp((ts + 200 * 60_000) / 1000, tz=dt.timezone.utc)
    out = build_blocked_signal_outcome_records(ledger, obs, now_utc=now)
    assert len(out) == 1
    row = out[0]
    assert row["censored"] is True
    assert row["censor_reason"] == "exit_observation_gap"
    assert row["realized_net_bps"] is None


def test_exit_within_delay():
    """用例 15:延遲 10min → 正常 row + exit_delay_ms=600000。"""
    ts = 1_782_000_000_000
    ledger = [_blocked_admission_row("e2", "LLLUSDT", "Buy", 100.0, ts, horizon=60)]
    obs = [
        _obs("LLLUSDT", ts, 100.0),
        _obs("LLLUSDT", ts + 60 * 60_000 + 10 * 60_000, 101.0),  # 遲 10min ≤ 15min
    ]
    now = dt.datetime.fromtimestamp((ts + 200 * 60_000) / 1000, tz=dt.timezone.utc)
    out = build_blocked_signal_outcome_records(ledger, obs, now_utc=now)
    assert len(out) == 1
    assert out[0]["censored"] is False
    assert out[0]["exit_delay_ms"] == 600_000


def test_entry_gap_censored():
    """用例 16:entry 觀測永缺、時限已過 → censored reason=entry_observation_gap。"""
    ts = 1_782_000_000_000
    ledger = [_blocked_admission_row("e3", "MMMUSDT", "Buy", None, ts, horizon=60)]
    # 無 entry_price、無任何觀測 → entry gap;now 遠超時限。
    obs = []
    now = dt.datetime.fromtimestamp((ts + 500 * 60_000) / 1000, tz=dt.timezone.utc)
    out = build_blocked_signal_outcome_records(ledger, obs, now_utc=now)
    assert len(out) == 1
    assert out[0]["censored"] is True
    assert out[0]["censor_reason"] == "entry_observation_gap"


def test_censored_excluded_from_stats():
    """用例 17:cell 10 row 中 4 censored → count=6、pct=40 → OBSERVATION_GAP_SUSPECT。"""
    rows = []
    for i in range(6):
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"g{i}",
                "side_cell_key": "strat|NNNUSDT|Buy",
                "symbol": "NNNUSDT",
                "strategy_name": "strat",
                "side": "Buy",
                "horizon_minutes": 60,
                "gross_bps": 20.0,
                "realized_net_bps": 5.0,
                "net_bps_optimistic": 5.0,
                "cost_bps": 15.0,
                "cost_model_version": "conservative_v1",
                "censored": False,
            }
        )
    for i in range(4):
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"gc{i}",
                "side_cell_key": "strat|NNNUSDT|Buy",
                "censored": True,
                "censor_reason": "exit_observation_gap",
                "realized_net_bps": None,
            }
        )
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["outcome_count"] == 6
    assert cell["censored_count"] == 4
    assert cell["censored_pct"] == pytest.approx(40.0)
    assert cell["status"] == "OBSERVATION_GAP_SUSPECT"
    assert cell["review_candidate"] is False


# ---------------------------------------------------------------------------
# F1(R3 charter WP-A.1;正本 = QC 預註冊 §2/§3):(cell, entry_minute, horizon)
# 分鐘量化去重 + 非重疊窗 n_eff + E2/E3 天數 eligibility + 複本一致性
# ---------------------------------------------------------------------------


def test_f1_duplicate_entry_copies_collapse_to_single_effective_observation():
    """F1 偽複製 fixture:同 entry 多副本必須壓成單一有效觀測。

    NEAR 案形狀縮小版:2 個相鄰分鐘 entry 各複製多份 → 去重 =2 個觀測,60m
    horizon 窗重疊 → 非重疊 n_eff=1;raw 行數不得再進 eligibility/t/BH
    (t/p 必須為 None,候選必須被攔)。
    """
    entry_a = 1_783_436_340_000
    entry_b = 1_783_436_400_000
    rows = []
    # entry A:+70.28 淨值 ×10 份;entry B:+59.32 淨值 ×8 份(副本值完全相同)。
    for i in range(10):
        rows.append(
            _blocked_outcome_row(
                f"dupA{i}",
                "ma_crossover|NEARUSDT|Buy",
                74.28,
                cost_model_version="conservative_v1",
                entry_ts_ms=entry_a,
            )
        )
    for i in range(8):
        rows.append(
            _blocked_outcome_row(
                f"dupB{i}",
                "ma_crossover|NEARUSDT|Buy",
                63.32,
                cost_model_version="conservative_v1",
                entry_ts_ms=entry_b,
            )
        )
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["outcome_count"] == 18
    assert cell["distinct_entry_observation_count"] == 2
    # 相鄰分鐘 × 60m horizon = 窗重疊 → 非重疊 greedy 只留最早 entry。
    assert cell["window_overlap_excluded_entry_count"] == 1
    assert cell["effective_entry_count"] == 1
    assert cell["duplicate_outcome_row_count"] == 16
    # n_eff=1 < min_outcomes(3) → 樣本不足,不得成候選、不得有 t/BH。
    assert cell["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    assert cell["review_candidate"] is False
    assert cell["one_sided_t_p_value"] is None
    assert cell["bh_fdr_pass"] is None
    assert cell["wrongful_block_score"] == 0.0
    # avg 為非重疊樣本均值(僅最早 entry A 的代表值),非 raw 行數加權。
    assert cell["avg_net_bps"] == pytest.approx(70.28)
    assert packet["blocked_signal_effective_entry_count"] == 1
    assert packet["blocked_signal_distinct_entry_observation_count"] == 2
    assert packet["blocked_signal_duplicate_outcome_row_count"] == 16
    assert packet["review_candidate_side_cell_count"] == 0


def test_f1_near_replication_distinct_ms_same_minute_single_day_blocked():
    """E2 攻擊重現:同分鐘 distinct-ms 秒級重發 ×30(全同值、單日)不得成候選。

    v4 毫秒精確去重會把這 30 行算成 30 個 distinct entry(n_eff=30 → 偽候選、
    p=0、BH pass);分鐘量化後全部落同一觀測 → n_eff=1,一切檢定不得產生。
    """
    base_ts = 1_783_436_340_000
    rows = [
        _blocked_outcome_row(
            f"ms{i}",
            "ma_crossover|NEARUSDT|Buy",
            29.0,  # net = +25(全同值)
            cost_model_version="conservative_v1",
            entry_ts_ms=base_ts + i * 997,  # 毫秒各異,同一分鐘內
        )
        for i in range(30)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["outcome_count"] == 30
    assert cell["distinct_entry_observation_count"] == 1
    assert cell["effective_entry_count"] == 1
    assert cell["duplicate_outcome_row_count"] == 29
    assert cell["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    assert cell["review_candidate"] is False
    assert cell["one_sided_t_p_value"] is None
    assert cell["bh_fdr_pass"] is None
    assert packet["review_candidate_side_cell_count"] == 0
    assert packet["status"] != "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"


def test_f1_single_day_episode_blocked_by_distinct_days_eligibility():
    """n_eff 過 floor 但 UTC 天數 < 5(預註冊 §3 E2)→ 不得成候選。

    35 個 hourly distinct entry(值帶擾動、全正)只跨 2 個 UTC 日 —— 單日/雙日
    episode regime-bet 形態必須被 E2 攔下,診斷 = 樣本不足,非 BLOCK_CONFIRMED。
    """
    rows = [
        _blocked_outcome_row(
            f"sd{i}",
            "strat|NNNUSDT|Buy",
            16.0 + [0.0, -1.0, 1.0, 0.5, -0.5][i % 5],
            cost_model_version="conservative_v1",
            entry_ts_ms=_ENTRY_BASE_TS_MS + i * _HOUR_MS,
        )
        for i in range(35)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["effective_entry_count"] == 35
    assert cell["distinct_entry_utc_days"] == 2
    assert cell["status"] == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
    assert cell["reason"] == "distinct_entry_utc_days_below_preregistered_min"
    assert cell["review_candidate"] is False
    assert cell["learning_diagnosis"] == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
    assert cell["bh_fdr_pass"] is None
    assert cell["wrongful_block_score"] == 0.0


def test_f1_top_day_concentration_blocked_by_share_eligibility():
    """名義多天、實質單日主導(top-day share > 50%,預註冊 §3 E3)→ 不得成候選。"""
    jitter = [0.0, -1.0, 1.0, 0.5, -0.5]
    rows = []
    # day0:18 個 hourly entry(60%);day1-4:各 3 個 → days=5 過 E2,share 過不了 E3。
    for i in range(18):
        rows.append(
            _blocked_outcome_row(
                f"td0-{i}",
                "strat|MMMUSDT|Buy",
                16.0 + jitter[i % 5],
                cost_model_version="conservative_v1",
                entry_ts_ms=_ENTRY_BASE_TS_MS + i * _HOUR_MS,
            )
        )
    for day in range(1, 5):
        for slot in range(3):
            rows.append(
                _blocked_outcome_row(
                    f"td{day}-{slot}",
                    "strat|MMMUSDT|Buy",
                    16.0 + jitter[(day + slot) % 5],
                    cost_model_version="conservative_v1",
                    entry_ts_ms=_ENTRY_BASE_TS_MS + day * _DAY_MS + slot * _HOUR_MS,
                )
            )
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["effective_entry_count"] == 30
    assert cell["distinct_entry_utc_days"] == 5
    assert cell["top_entry_day_share_pct"] == pytest.approx(60.0)
    assert cell["status"] == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
    assert cell["reason"] == "top_day_entry_share_above_preregistered_max"
    assert cell["review_candidate"] is False


def test_f1_window_overlap_entries_not_double_counted():
    """非重疊窗 greedy(預註冊 §2.6):30min 間距 × 60m horizon → n_eff 折半。"""
    rows = [
        _blocked_outcome_row(
            f"ov{i}",
            "strat|LLLUSDT|Buy",
            16.0 + [0.0, -1.0, 1.0, 0.5][i % 4],
            cost_model_version="conservative_v1",
            entry_ts_ms=_ENTRY_BASE_TS_MS + i * 30 * 60_000,
        )
        for i in range(10)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["distinct_entry_observation_count"] == 10
    assert cell["effective_entry_count"] == 5
    assert cell["window_overlap_excluded_entry_count"] == 5


def test_f1_replica_value_mismatch_marks_data_integrity_suspect():
    """同觀測單位複本值不一致(預註冊 §2.3)→ DATA_INTEGRITY_SUSPECT,不得平均。"""
    rows = [
        _blocked_outcome_row(
            f"rc{i}",
            "strat|KKKUSDT|Buy",
            16.0 + [0.0, -1.0, 1.0, 0.5, -0.5][i % 5],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i in range(5)
    ]
    # 同分鐘 distinct-ms 複本,gross/net 與代表行不同 → 複本不一致。
    conflict = _blocked_outcome_row(
        "rc0-conflict",
        "strat|KKKUSDT|Buy",
        40.0,
        cost_model_version="conservative_v1",
        entry_ts_ms=_spread_entry_ts(0, per_day=1) + 500,
    )
    cfg = BlockedOutcomeReviewConfig(min_effective_entries_per_side_cell=5)
    packet = build_blocked_signal_outcome_review(rows + [conflict], cfg=cfg, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["replica_inconsistent_group_count"] == 1
    assert cell["data_integrity_suspect"] is True
    assert cell["status"] == "DATA_INTEGRITY_SUSPECT"
    assert cell["learning_diagnosis"] == "DATA_INTEGRITY_SUSPECT"
    assert cell["review_candidate"] is False
    assert cell["one_sided_t_p_value"] is None
    assert cell["bh_fdr_pass"] is None
    assert packet["data_integrity_suspect_side_cell_count"] == 1


def test_f1_zero_variance_sample_marks_data_integrity_suspect():
    """跨天全同值樣本(σ=0)= 去重逃逸嫌疑(預註冊 §4 V=0)→ 不給 p、不得成候選。"""
    rows = [
        _blocked_outcome_row(
            f"zv{i}",
            "strat|IIIUSDT|Buy",
            29.0,  # 全同值 +25 淨值
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i),
        )
        for i in range(30)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["effective_entry_count"] == 30
    assert cell["zero_variance_suspect"] is True
    assert cell["status"] == "DATA_INTEGRITY_SUSPECT"
    assert cell["reason"] == "zero_variance_effective_sample_dedup_escape_suspect"
    assert cell["review_candidate"] is False
    assert cell["one_sided_t_p_value"] is None
    assert packet["review_candidate_side_cell_count"] == 0


def test_f1_effective_entry_floor_blocks_candidacy_below_preregistered_min():
    """過線但 n_eff<預註冊門檻(30,QC 預註冊 §3 E1)→ EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT。

    boundary fixture:n_eff=29=30−1,直測門檻邊界(默認 cfg,無放寬;跨 6 日
    排除 E2/E3 干擾,失敗原因必須落在 E1 floor)。
    """
    rows = [
        _blocked_outcome_row(
            f"fl{i}",
            "strat|OOOUSDT|Buy",
            16.0 + [0.0, -1.0, 1.0, 0.5, -0.5][i % 5],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i),
        )
        for i in range(29)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["effective_entry_count"] == 29
    assert cell["status"] == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
    assert cell["reason"] == "distinct_entry_effective_n_below_preregistered_threshold"
    assert cell["review_candidate"] is False
    assert cell["learning_diagnosis"] == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
    # 併入 insufficient 計數 → packet 落 continue_recording 而非誤判定案。
    assert packet["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    assert packet["insufficient_sample_side_cell_count"] == 1


def test_f1_distinct_entries_meeting_floor_can_still_be_candidate():
    """n_eff=30(= 門檻)+ 跨 6 日 + BH 過 → 候選路徑不因 F1 修復被誤殺(默認 cfg)。"""
    nets = [12.5, 11.5, 10.5, 12.0, 11.0] * 6
    rows = [
        _blocked_outcome_row(
            f"ok{i}",
            "strat|PPPUSDT|Buy",
            net + 4.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i),
        )
        for i, net in enumerate(nets)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["effective_entry_count"] == 30
    assert cell["distinct_entry_utc_days"] == 6
    assert cell["top_entry_day_share_pct"] == pytest.approx(100.0 / 6.0)
    assert cell["status"] == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    assert cell["review_candidate"] is True
    assert cell["bh_fdr_pass"] is True


def test_f1_missing_entry_ts_rows_collapse_failclosed():
    """entry_ts_ms 缺失無法證明 distinct → 不入樣本,n_eff=0(fail-closed)。"""
    rows = [
        _blocked_outcome_row(
            f"m{i}", "strat|QQQUSDT|Buy", 16.0, cost_model_version="conservative_v1"
        )
        for i in range(5)
    ]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["outcome_count"] == 5
    assert cell["effective_entry_count"] == 0
    assert cell["entry_ts_missing_row_count"] == 5
    assert cell["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    assert cell["review_candidate"] is False


def test_f1_missing_entry_ts_rows_block_candidacy_of_qualified_sample():
    """合格樣本 + 少量缺 entry_ts row → 候選被身分完整性欄攔(排除數據不得立案)。"""
    nets = [12.5, 11.5, 10.5, 12.0, 11.0] * 6
    rows = [
        _blocked_outcome_row(
            f"mx{i}",
            "strat|SSSUSDT|Buy",
            net + 4.0,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i),
        )
        for i, net in enumerate(nets)
    ]
    rows.append(
        _blocked_outcome_row(
            "mx-missing", "strat|SSSUSDT|Buy", 16.0, cost_model_version="conservative_v1"
        )
    )
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["effective_entry_count"] == 30
    assert cell["entry_ts_missing_row_count"] == 1
    assert cell["status"] == "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT"
    assert cell["reason"] == "entry_ts_missing_rows_block_candidacy"
    assert cell["review_candidate"] is False


def test_f1_t_test_n_is_effective_entry_count_not_raw_row_count():
    """t 檢定的 n 必須是 n_eff(mutation bite:改回 raw outcome_count 必紅)。

    fixture:30 個 distinct hourly entry(跨 6 UTC 日、值帶擾動)每個複製 3 份
    → outcome_count=90、n_eff=30。cell 的 p 必須等於 one_sided_t_p_value(mean,
    std, n_eff=30);若 outcome_review 的 t 檢定分母被 mutation 回 raw 行數
    (n=90),p 收縮兩個數量級以上 → approx 等值斷言必紅。效應量刻意取中等
    (mean≈0.3、std≈0.72)使兩個 p 都落在可分辨區間,不會同時 underflow 到 0。
    """
    jitter = [0.0, -1.0, 1.0, 0.5, -0.5]
    rows = []
    for i in range(30):
        for copy in range(3):
            rows.append(
                _blocked_outcome_row(
                    f"tn{i}-{copy}",
                    "strat|XXXUSDT|Buy",
                    4.3 + jitter[i % 5],
                    cost_model_version="conservative_v1",
                    entry_ts_ms=_spread_entry_ts(i),
                )
            )
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["outcome_count"] == 90
    assert cell["effective_entry_count"] == 30
    assert cell["duplicate_outcome_row_count"] == 60
    # 手算對照(獨立於 cell 欄位):net = gross − 4.0 = 0.3 + jitter。
    nets = [0.3 + jitter[i % 5] for i in range(30)]
    mean = sum(nets) / 30
    std = math.sqrt(sum((v - mean) ** 2 for v in nets) / 29)
    assert cell["avg_net_bps"] == pytest.approx(mean, abs=1e-12)
    assert cell["std_net_bps"] == pytest.approx(std, abs=1e-12)
    p_eff = evidence_stats.one_sided_t_p_value(mean, std, 30)
    p_raw = evidence_stats.one_sided_t_p_value(mean, std, 90)
    # 分離保證:raw-n(90)的 p 比 n_eff(30)的 p 小 >100×,approx 不可能誤過。
    assert p_raw < p_eff / 100.0
    assert cell["one_sided_t_p_value"] == pytest.approx(p_eff, rel=1e-9)


# ---------------------------------------------------------------------------
# WP-A.2:成本雙軌(主判=實測 E[cost];conservative tail=敏感性欄)
# ---------------------------------------------------------------------------


def _expected_cost_artifact(*, mean_abs, cvar90=None, symbol_rows=None, asof=None):
    """v2 artifact 形狀:mean_abs 為主判成分;cvar90 缺省時消費端 fallback q90。"""
    return {
        "asof": (asof or NOW.isoformat()),
        "symbols": symbol_rows or [],
        "global": {
            "n": 500,
            "mean_abs": mean_abs,
            "mean_signed": mean_abs / 2.0,
            "q50": mean_abs / 2.0,
            "q75": mean_abs * 2.0,
            "q90": mean_abs * 4.0,
            "cvar90": cvar90,
        },
    }


# 成本雙軌測試共用:n_eff=5 fixture,n_eff 門檻對齊到 5(本組測的是成本軌語義,
# 非 n_eff floor;floor 本體由 F1 測試組以默認 30 直測)。fixture 每日 1 entry
# 跨 5 UTC 日(過 E2/E3);gross 帶 ±2 對稱擾動(避免零變異數疑點)均值不變。
_COST_TRACK_CFG = BlockedOutcomeReviewConfig(min_effective_entries_per_side_cell=5)
_COST_TRACK_JITTER = [-2.0, -1.0, 0.0, 1.0, 2.0]


def test_expected_cost_main_judgment_with_artifact():
    """artifact 可用 → 主判 = gross − E[cost](mean_abs 無安全乘數);保守軌降為敏感性欄。

    fixture:gross 均值 +30,conservative cost=4.0(row 上)→ realized_net 均值 26;
    E[cost] = 2×(5.5+2.0)=15 → expected net 均值 15。門檻 0/60% 下兩軌都過,
    但主判欄位必須是 expected 軌數字。CVaR90 尾部欄並列:cvar90=8.0 →
    cost_tail = 2×(5.5+8.0)=27 → mean_net_tail=3.0。
    """
    rows = [
        _blocked_outcome_row(
            f"ec{i}",
            "strat|RRRUSDT|Buy",
            30.0 + _COST_TRACK_JITTER[i],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i in range(5)
    ]
    artifact = _expected_cost_artifact(mean_abs=2.0, cvar90=8.0)
    packet = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=artifact, cfg=_COST_TRACK_CFG, now_utc=NOW
    )
    cell = packet["top_side_cells"][0]
    assert packet["cost_basis_main"] == "expected_slippage_mean_abs_v1"
    assert packet["expected_cost_artifact"]["available"] is True
    assert packet["expected_cost_artifact"]["global_mean_abs_bps"] == pytest.approx(2.0)
    assert packet["expected_cost_artifact"]["global_tail_bps"] == pytest.approx(8.0)
    assert packet["expected_cost_artifact"]["global_tail_metric"] == "cvar90"
    assert cell["cost_basis_main"] == "expected_slippage_mean_abs_v1"
    assert cell["avg_expected_cost_bps"] == pytest.approx(15.0)
    assert cell["avg_net_bps"] == pytest.approx(30.0 - 15.0)
    assert cell["avg_net_bps_expected"] == pytest.approx(15.0)
    # 預註冊 §6.2 CVaR90 尾部欄並列輸出且不作主判。
    assert cell["mean_net_tail"] == pytest.approx(3.0)
    assert cell["net_tail_positive_pct"] == pytest.approx(100.0)
    assert cell["avg_tail_cost_bps"] == pytest.approx(27.0)
    assert cell["tail_metric"] == "cvar90"
    # conservative_v1 第三對照欄(row 上 realized_net = 30−4 = 26)且不作主判。
    assert cell["avg_net_bps_conservative"] == pytest.approx(26.0)
    assert cell["conservative_tail_would_clear_thresholds"] is True


def test_expected_cost_tail_falls_back_to_q90_when_cvar90_missing():
    """cvar90 缺欄 → 尾部 fallback q90 並記 tail_metric=q90_fallback(預註冊 §6.2)。"""
    rows = [
        _blocked_outcome_row(
            f"tq{i}",
            "strat|VVVUSDT|Buy",
            30.0 + _COST_TRACK_JITTER[i],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i in range(5)
    ]
    # mean_abs=2.0 → q90=8.0;無 cvar90 → tail 用 q90 → cost_tail=27。
    artifact = _expected_cost_artifact(mean_abs=2.0)
    packet = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=artifact, cfg=_COST_TRACK_CFG, now_utc=NOW
    )
    cell = packet["top_side_cells"][0]
    assert packet["expected_cost_artifact"]["global_tail_metric"] == "q90_fallback"
    assert cell["tail_metric"] == "q90_fallback"
    assert cell["avg_tail_cost_bps"] == pytest.approx(27.0)
    assert cell["mean_net_tail"] == pytest.approx(3.0)


def test_expected_cost_track_requires_mean_abs_column():
    """舊版 v1 artifact(只有 q50/q75/q90,無 mean_abs)→ 主判 fail-closed 回退 conservative_v1。

    為什麼:預註冊 §6.1 凍結 E[slip_leg]=mean_abs;右偏 |slip| 下 q50 < mean,
    以 q50 頂替會系統性低估成本(anti-conservative)。缺欄必須整軌拒用。
    """
    rows = [
        _blocked_outcome_row(
            f"lg{i}",
            "strat|WWWUSDT|Buy",
            30.0 + _COST_TRACK_JITTER[i],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i in range(5)
    ]
    legacy_v1 = {
        "asof": NOW.isoformat(),
        "symbols": [],
        "global": {"n": 500, "q50": 2.0, "q75": 4.0, "q90": 8.0},
    }
    packet = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=legacy_v1, cfg=_COST_TRACK_CFG, now_utc=NOW
    )
    assert packet["cost_basis_main"] == "conservative_v1"
    assert packet["expected_cost_artifact"]["available"] is False
    cell = packet["top_side_cells"][0]
    assert cell["avg_net_bps"] == pytest.approx(26.0)
    assert cell["mean_net_tail"] is None
    assert cell["tail_metric"] is None


def test_expected_cost_flips_conservative_false_negative():
    """conservative 下不過線、實測 E[cost] 下過線的 cell:主判必須用實測軌。

    gross 均值 +20,conservative cost=92.3(toml 最保守 tier 形狀)→ realized 均值
    −72.3(不過);E[cost]=2×(5.5+2)=15 → expected net 均值 +5(過)。這正是 WP-A
    「誤殺假說」要能翻出來的形狀。
    """
    rows = []
    for i in range(5):
        gross = 20.0 + _COST_TRACK_JITTER[i]
        row = _blocked_outcome_row(
            f"fn{i}",
            "strat|SSSUSDT|Buy",
            gross,
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        row["cost_bps"] = 92.3
        row["realized_net_bps"] = gross - 92.3
        rows.append(row)
    artifact = _expected_cost_artifact(mean_abs=2.0)
    packet = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=artifact, cfg=_COST_TRACK_CFG, now_utc=NOW
    )
    cell = packet["top_side_cells"][0]
    assert cell["avg_net_bps"] == pytest.approx(5.0)
    assert cell["avg_net_bps_conservative"] == pytest.approx(-72.3)
    assert cell["conservative_tail_would_clear_thresholds"] is False
    assert cell["status"] == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    assert cell["review_candidate"] is True


def test_expected_cost_track_unavailable_falls_back_conservative():
    """artifact 缺失/過期 → 主判 fail-closed 回退 conservative_v1(不放寬)。"""
    rows = [
        _blocked_outcome_row(
            f"na{i}",
            "strat|TTTUSDT|Buy",
            30.0 + _COST_TRACK_JITTER[i],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i in range(5)
    ]
    # 無 artifact。
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    assert packet["cost_basis_main"] == "conservative_v1"
    assert packet["expected_cost_artifact"]["available"] is False
    cell = packet["top_side_cells"][0]
    assert cell["avg_net_bps"] == pytest.approx(26.0)
    assert cell["avg_net_bps_expected"] is None
    # 過期 artifact(asof 超 48h)同樣回退。
    stale = _expected_cost_artifact(
        mean_abs=2.0, asof=(NOW - dt.timedelta(hours=72)).isoformat()
    )
    stale_packet = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=stale, now_utc=NOW
    )
    assert stale_packet["cost_basis_main"] == "conservative_v1"


def test_expected_cost_respects_fee_floor():
    """E[cost] 不得低於純 taker fee 雙腿 floor(11.0bps,手續費不打折)。"""
    rows = [
        _blocked_outcome_row(
            f"ff{i}",
            "strat|UUUUSDT|Buy",
            30.0 + _COST_TRACK_JITTER[i],
            cost_model_version="conservative_v1",
            entry_ts_ms=_spread_entry_ts(i, per_day=1),
        )
        for i in range(5)
    ]
    # 畸形負 mean_abs → 夾到 fee floor(尾部軌同 floor)。
    artifact = _expected_cost_artifact(mean_abs=-50.0)
    packet = build_blocked_signal_outcome_review(
        rows, slippage_quantiles=artifact, cfg=_COST_TRACK_CFG, now_utc=NOW
    )
    cell = packet["top_side_cells"][0]
    assert cell["avg_expected_cost_bps"] == pytest.approx(cost_model.FEE_FLOOR_BPS)
    assert cell["avg_tail_cost_bps"] == pytest.approx(cost_model.FEE_FLOOR_BPS)


# ---------------------------------------------------------------------------
# P2-7 用例 7 等價(UCB 純函數誤殺率;Rust 側跑 disable 規則本體)
# ---------------------------------------------------------------------------


def test_disable_ucb_false_kill_rate():
    """用例 7:μ=+30,σ=200,n=8 UCB-futility 誤殺率 ∈ [3%,6%](復算 4.4%)。"""
    import random

    rng = random.Random(20260704)
    z = 1.281_551_565_544_600_4
    kills = 0
    trials = 10000
    for _ in range(trials):
        sample = [rng.gauss(30.0, 200.0) for _ in range(8)]
        mean = sum(sample) / 8
        var = sum((v - mean) ** 2 for v in sample) / 7
        std = math.sqrt(var)
        ucb = mean + z * std / math.sqrt(8)
        if ucb < 0.0:
            kills += 1
    rate = kills / trials
    assert 0.03 <= rate <= 0.06, f"誤殺率={rate}"


# ---------------------------------------------------------------------------
# P2-7 用例 6 直測(Python 側禁用規則本體 = summarize_side_cell_runtime_state)
#
# 為什麼補此測(LOW-2):test_disable_ucb_false_kill_rate 只驗 UCB 純函數誤殺率,
# 不觸 Python 禁用規則本體;Rust ucb_futility_disable_rule_matches_spec_thresholds
# 兜住 Rust 側,但 Python-only drift(如 ddof n−1→n、嚴格 <→<=)不會被 golden 常量
# 測試抓到。此處對齊 Rust 三錨點 + n<2 pure-mean 雙向,直跑真 Python 函數,並含兩個
# mutation-敏感錨點:D(ddof)、G(嚴格 <)。
# ---------------------------------------------------------------------------

_UCB_SIDE_CELL_KEY = "ma_crossover|ETHUSDT|Sell"
_UCB_NOW_MS = 1_782_046_800_000


def _ucb_candidate(max_probe_orders: int = 100) -> dict:
    # max_probe_orders 取大值,確保 remaining>0,不被 probe_budget_exhausted 先攔,
    # 使禁用決策純由 UCB-futility 規則主導。
    return {
        "side_cell_key": _UCB_SIDE_CELL_KEY,
        "probe_proposal": {"max_probe_orders": max_probe_orders},
    }


def _ucb_outcome_rows(nets: list[float]) -> list[dict]:
    return [
        {
            "record_type": "probe_outcome",
            "side_cell_key": _UCB_SIDE_CELL_KEY,
            "realized_net_bps": net,
        }
        for net in nets
    ]


def _two_point_mean_std(mean: float, std: float, n: int = 8) -> list[float]:
    # 對稱雙點構造(對齊 Rust scale_to_mean_std):n/2 個 mean+d、n/2 個 mean−d,
    # 則 x̄=mean、s(ddof=1)=std。d=std·√((n−1)/n)。
    d = std * math.sqrt((n - 1) / n)
    half = n // 2
    return [mean + d] * half + [mean - d] * half


def _ucb_disabled(nets: list[float], *, min_failed: int) -> bool:
    from cost_gate_learning_lane.runtime_adapter import (
        RuntimeAdmissionConfig,
        summarize_side_cell_runtime_state,
    )

    state = summarize_side_cell_runtime_state(
        _ucb_candidate(),
        _ucb_outcome_rows(nets),
        now_ms=_UCB_NOW_MS,
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=min_failed),
    )
    return state["disabled"]


def test_python_ucb_futility_disable_rule_matches_spec_thresholds():
    """用例 6 Python 直測:對齊 Rust 三錨點,證 Python 禁用規則本體 = UCB-futility。"""
    # A:n=7 全負 → 未達 n≥8 門檻 → 不禁用(UCB 規則不啟動)。
    assert _ucb_disabled([-120.0] * 7, min_failed=8) is False
    # B:n=8,x̄=−120,s=200 → UCB ≈ −29.4 < 0 → 禁用。
    assert _ucb_disabled(_two_point_mean_std(-120.0, 200.0), min_failed=8) is True
    # C:n=8,x̄=−80,s=200 → UCB ≈ +10.6 > 0 → 不禁用。
    assert _ucb_disabled(_two_point_mean_std(-80.0, 200.0), min_failed=8) is False


def test_python_ucb_futility_pure_mean_fallback_both_directions():
    """n<2 無法估變異數 → 退純均值判準(對齊 Rust (true, Some(mean), None) 分支)。"""
    # n=1 mean=−10 → −10 < 0 → 禁用。
    assert _ucb_disabled([-10.0], min_failed=1) is True
    # n=1 mean=+10 → +10 < 0 False → 不禁用。
    assert _ucb_disabled([10.0], min_failed=1) is False


def test_python_ucb_ddof_and_strict_comparison_are_mutation_sensitive():
    """mutation 自證錨點:若 std 誤用 ddof=n(而非 n−1)或 <→<=,此測必紅。

    D(ddof 敏感):n=8,x̄=−87.693,s(ddof=1)=200 → UCB=+2.93>0 不禁用;若 std 誤除以
      n(ddof=0)則 s=187.08、UCB=−2.93<0 會誤禁 → 突變翻紅。此 mean 精選於兩個 ddof
      判準的翻轉窗口 (−90.62, −84.77) 正中,使唯一區別就是 n−1 vs n。
    G(嚴格 < 敏感):n=1 pure-mean,mean=0.0 → 0<0 為 False 不禁用;若 <→<= 則
      0<=0 為 True 會誤禁 → 突變翻紅。
    """
    # D:正解不禁用(ddof=1);ddof=n 突變會使其禁用。
    assert _ucb_disabled(_two_point_mean_std(-87.693_024_306_047_45, 200.0), min_failed=8) is False
    # G:正解不禁用(嚴格 <);<= 突變會使其禁用。
    assert _ucb_disabled([0.0], min_failed=1) is False
