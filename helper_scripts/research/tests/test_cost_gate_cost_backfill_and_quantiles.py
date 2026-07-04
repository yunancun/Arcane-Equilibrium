"""分位 artifact(P1-2b)與回填 overlay(P1-2c)回歸。

MODULE_NOTE:
  模塊用途：覆蓋驗收 A2/A6(overlay lineage union 覆蓋率 + per-file 統計)與分位
    artifact 純函數(ROLLUP → symbols[]/global 投影、thin_sample 標記)。
  依賴：conftest 把 research/ 加進 sys.path。
"""

from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import slippage_quantile_artifact as sqa
from cost_gate_learning_lane import cost_backfill_overlay as cbo


NOW = dt.datetime(2026, 7, 4, 18, 0, 0, tzinfo=dt.timezone.utc)


def test_quantile_artifact_rollup_projection():
    """ROLLUP 行(symbol=None)→ global;per-symbol 排序 + thin_sample(n<100)。"""
    rows = [
        {"symbol": "ETHUSDT", "n": 213, "q50": 2.0, "q75": 2.23, "q90": 5.0},
        {"symbol": "ATOMUSDT", "n": 66, "q50": 3.0, "q75": 13.18, "q90": 20.0},
        {"symbol": None, "n": 178, "q50": 4.28, "q75": 24.97, "q90": 54.08},
    ]
    artifact = sqa.build_slippage_quantile_artifact(rows, now_utc=NOW)
    assert artifact["global"]["q75"] == 24.97
    assert artifact["n_total_global"] == 178
    syms = {s["symbol"]: s for s in artifact["symbols"]}
    assert syms["ETHUSDT"]["thin_sample"] is False  # n=213 ≥ 100
    assert syms["ATOMUSDT"]["thin_sample"] is True  # n=66 < 100
    # 產出可被 cost_model.load_slippage_quantiles 讀回。
    from cost_gate_learning_lane.cost_model import load_slippage_quantiles

    table = load_slippage_quantiles(artifact)
    assert table.global_q75_bps == 24.97
    assert table.per_symbol["ETHUSDT"].q75_bps == 2.23


def _legacy_row(attempt_id, symbol, gross):
    return {
        "record_type": "blocked_signal_outcome",
        "attempt_id": attempt_id,
        "side_cell_key": f"strat|{symbol}|Buy",
        "symbol": symbol,
        "horizon_minutes": 60,
        "event_ts_ms": 1_782_000_000_000,
        "gross_bps": gross,
        "realized_net_bps": gross - 4.0,
        "cost_bps": 4.0,
        # 無 cost_model_version → legacy_optimistic,需回填。
    }


def test_overlay_lineage_union_dedup():
    """A6:兩檔互有獨占行 → union 去重、per-file 統計、獨占行標 lineage_source。"""
    file_a = [
        _legacy_row("shared1", "PPPUSDT", 30.0),
        _legacy_row("onlyA", "PPPUSDT", 20.0),
    ]
    file_b = [
        _legacy_row("shared1", "PPPUSDT", 30.0),  # 與 A 交集
        _legacy_row("onlyB", "QQQUSDT", 10.0),
    ]
    batch = cbo.build_cost_backfill_overlay(
        [("fileA", file_a), ("fileB", file_b)],
        now_utc=NOW,
    )
    # union = shared1 + onlyA + onlyB = 3。
    assert batch["union_backfilled_count"] == 3
    assert batch["intersection_count"] == 1
    ids = {r["attempt_id"]: r for r in batch["overlay_rows"]}
    assert set(ids) == {"shared1", "onlyA", "onlyB"}
    # 獨占行標對應 lineage_source(先見者贏:onlyB 來自 fileB)。
    assert ids["onlyB"]["lineage_source"] == "fileB"
    # overstated_bps = cost_cons − 4.0 > 0(保守成本必高於樂觀常數)。
    assert ids["shared1"]["overstated_bps"] > 0.0


def test_overlay_skips_already_conservative():
    """已含 conservative_v1 的 row 不重複回填(避免雙重覆蓋)。"""
    row = _legacy_row("x1", "RRRUSDT", 30.0)
    row["cost_model_version"] = "conservative_v1"
    batch = cbo.build_cost_backfill_overlay([("f", [row])], now_utc=NOW)
    assert batch["union_backfilled_count"] == 0


def test_overlay_load_roundtrip(tmp_path):
    """overlay 寫 JSONL → load_overlay 讀回為 attempt_id→row。"""
    batch = cbo.build_cost_backfill_overlay(
        [("f", [_legacy_row("y1", "SSSUSDT", 30.0)])], now_utc=NOW
    )
    path = tmp_path / cbo.OVERLAY_FILENAME
    cbo._write_overlay_jsonl(path, batch)
    loaded = cbo.load_overlay(path)
    assert "y1" in loaded
    assert loaded["y1"]["cost_model_version"] == "conservative_v1"
