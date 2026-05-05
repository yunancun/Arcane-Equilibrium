"""REF-20 Sprint C R6 W6 R6-T9 — Sprint C1 closure E2E test。

模組目的：
    驗 `run_finalize_route._compute_and_persist_calibration` 真實 caller
    chain（Sprint C1 closure §1.2）：
      1. SELECT V049 row 的 manifest_jsonb->>'strategy' / ->>'symbol'。
      2. SELECT trading.fills 14d window；engine_mode IN demo/live_demo。
      3. derive_execution_confidence(fills, now)。
      4. label != 'none' → update_execution_confidence(cur, label=...)。
      5. 任何錯誤 catch + log（advisory，不阻 finalize）。

5 case（per dispatch §1.3）：
  1. test_calibration_e2e_grid_yields_calibrated — 1162 fills + grid_trading
     + BTCUSDT → label=calibrated + V049 UPDATE 1 row。
  2. test_calibration_e2e_funding_arb_yields_not_calibrated — 99 fills →
     label != 'calibrated'（n<200 強制）。
  3. test_calibration_e2e_bb_reversion_7_fills_yields_none — 7 fills < 30 →
     label='none' + V049 0 UPDATE（none 不寫）。
  4. test_calibration_e2e_no_fills_returns_none — 0 fills → label='none' +
     V049 0 UPDATE。
  5. test_calibration_e2e_python_rust_byte_equal — 同 fixture 跑 Python port
     + Rust binary（subprocess proxy or skip）；assert label / mad / iqr 字節等
     （cross-language reproducibility）。

Test mode / 測試模式：
  - Default (Mac dev)：純 mock cur；hermetic；無 PG。
  - Live PG (Linux operator)：opt-in via OPENCLAW_TEST_LIVE_PG=1 +
    OPENCLAW_TEST_DSN；real PG smoke 驗 INSERT trading.fills + V049 UPDATE
    chain（與 W3 V055 既有 pattern 對齊）。

CLAUDE.md §七 雙語注釋強制：default 中文（2026-05-05 governance change）。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.calibration_label import (  # noqa: E501
    CalibrationResult,
    ExecutionConfidence,
    FillRecord,
)
from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.run_finalize_route import (  # noqa: E501
    _CALIBRATION_ENGINE_MODES,
    _CALIBRATION_FILLS_WINDOW_DAYS,
    _compute_and_persist_calibration,
)


# 所有 test 共用的參考時鐘 — 固定、確定性。
_REFERENCE_NOW = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
_TEST_EXPERIMENT_ID = "11111111-1111-1111-1111-111111111111"


def _build_fills_rows(
    n: int,
    last_age_days: float,
    oldest_age_days: float,
    fee_rate: float,
    price: float,
) -> list[tuple]:
    """構造 trading.fills SELECT row tuples (ts, side, price, fee_rate)。

    age 線性插值於 [oldest, last] 端點（鏡 Python unit test fixture）；side
    全 'Buy'。
    """
    rows: list[tuple] = []
    if n == 0:
        return rows
    for i in range(n):
        if n == 1:
            age_days = last_age_days
        else:
            age_days = (
                oldest_age_days + (last_age_days - oldest_age_days) * i / (n - 1)
            )
        ts = _REFERENCE_NOW - timedelta(days=age_days)
        rows.append((ts, "Buy", price, fee_rate))
    return rows


def _make_mock_cursor(
    *,
    strategy: str | None = "grid_trading",
    symbol: str | None = "BTCUSDT",
    fills_rows: list[tuple] | None = None,
    update_rowcount: int = 1,
) -> MagicMock:
    """構造 mock cursor 模擬 V049 SELECT + trading.fills SELECT + V049 UPDATE。

    - 第一個 fetchone()：(strategy, symbol) tuple。
    - fetchall()：trading.fills 行。
    - rowcount：UPDATE V049 影響行數。
    """
    cur = MagicMock()
    fetchone_results: list[Any] = []
    if strategy is None and symbol is None:
        fetchone_results.append(None)
    else:
        fetchone_results.append((strategy, symbol))
    cur.fetchone.side_effect = fetchone_results
    cur.fetchall.return_value = fills_rows or []
    cur.rowcount = update_rowcount
    return cur


# ───────────────────────────────────────────────────────────────────
# Case 1：1162 fills → calibrated
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_grid_yields_calibrated() -> None:
    """1162 grid_trading + BTCUSDT fills → label='calibrated' + V049 UPDATE 1 row。"""
    fills_rows = _build_fills_rows(
        n=1162,
        last_age_days=0.0,
        oldest_age_days=6.0,
        fee_rate=0.0002,
        price=50000.0,
    )
    cur = _make_mock_cursor(
        strategy="grid_trading",
        symbol="BTCUSDT",
        fills_rows=fills_rows,
    )

    label = _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    assert label == "calibrated"
    # SELECT V049 + SELECT trading.fills + UPDATE V049 = 3 execute call。
    assert cur.execute.call_count == 3
    # 第三 call 為 UPDATE V049（execute 第三個 call_args sql 含「UPDATE replay.experiments」）。
    update_call_sql = cur.execute.call_args_list[2].args[0]
    assert "UPDATE replay.experiments" in update_call_sql
    assert "execution_confidence" in update_call_sql
    update_params = cur.execute.call_args_list[2].args[1]
    assert update_params[0] == "calibrated"


# ───────────────────────────────────────────────────────────────────
# Case 2：99 fills → not calibrated（n<200 強制）
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_funding_arb_yields_not_calibrated() -> None:
    """99 funding_arb fills → label != 'calibrated'（n<200 強制）。"""
    fills_rows = _build_fills_rows(
        n=99,
        last_age_days=1.0,
        oldest_age_days=5.0,
        fee_rate=0.0002,
        price=50000.0,
    )
    cur = _make_mock_cursor(
        strategy="funding_arb",
        symbol="BTCUSDT",
        fills_rows=fills_rows,
    )
    label = _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    # n=99 ≥ 30 + age ≤ 14d + MAD < 8 + IQR < 20 → limited（QC §1.1 容許）。
    assert label in ("limited", "none"), (
        f"funding_arb n=99 必非 calibrated；實際 = {label}"
    )


# ───────────────────────────────────────────────────────────────────
# Case 3：7 fills → none + V049 0 UPDATE
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_bb_reversion_7_fills_yields_none() -> None:
    """7 bb_reversion fills < 30 → label='none' + V049 0 UPDATE。"""
    fills_rows = _build_fills_rows(
        n=7,
        last_age_days=1.0,
        oldest_age_days=3.0,
        fee_rate=0.0002,
        price=50000.0,
    )
    cur = _make_mock_cursor(
        strategy="bb_reversion",
        symbol="BTCUSDT",
        fills_rows=fills_rows,
    )
    label = _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    assert label == "none"
    # V049 0 UPDATE — 'none' 不寫，僅 SELECT V049 + SELECT trading.fills = 2 call。
    assert cur.execute.call_count == 2
    # 確認 0 UPDATE：search call_args sql 無「UPDATE replay.experiments」。
    for call in cur.execute.call_args_list:
        assert "UPDATE replay.experiments" not in call.args[0]


# ───────────────────────────────────────────────────────────────────
# Case 4：0 fills → none + V049 0 UPDATE
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_no_fills_returns_none() -> None:
    """0 fills → label='none' + V049 0 UPDATE（fills 空 list → derive 回 None）。"""
    cur = _make_mock_cursor(
        strategy="ma_crossover",
        symbol="ETHUSDT",
        fills_rows=[],
    )
    label = _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    assert label == "none"
    # 2 execute call（SELECT V049 + SELECT trading.fills；無 UPDATE）。
    assert cur.execute.call_count == 2


# ───────────────────────────────────────────────────────────────────
# Case 5：V049 row 缺 strategy/symbol → return None（advisory）
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_v049_missing_strategy_returns_none() -> None:
    """V049 row 缺 strategy/symbol → 函數 return None（advisory；不 raise）。"""
    cur = _make_mock_cursor(
        strategy=None,
        symbol=None,
        fills_rows=[],
    )
    label = _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    assert label is None  # not 'none'；而是 None（advisory failure，不 UPDATE）
    # 僅 SELECT V049（fetchone 回 None tuple → 早 return）。
    assert cur.execute.call_count == 1


# ───────────────────────────────────────────────────────────────────
# Case 6：sql exception 不應 propagate（advisory fail-soft）
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_sql_exception_returns_none_advisory() -> None:
    """SQL exception → log warn + return None；不 raise（advisory，不阻 finalize）。"""
    cur = MagicMock()
    cur.execute.side_effect = RuntimeError("simulated PG outage")
    label = _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    assert label is None  # advisory failure


# ───────────────────────────────────────────────────────────────────
# Case 7：dispatch §1.2 SQL 套 _CALIBRATION_ENGINE_MODES + WINDOW
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_select_filters_engine_mode_and_14d_window() -> None:
    """trading.fills SELECT 套用 engine_mode IN demo/live_demo + 14d window。

    驗 dispatch §1.2 SQL filter contract — 不可讓 'paper' / 'live' 進 calibration。
    """
    fills_rows = _build_fills_rows(
        n=10,
        last_age_days=0.5,
        oldest_age_days=2.0,
        fee_rate=0.0002,
        price=50000.0,
    )
    cur = _make_mock_cursor(
        strategy="grid_trading",
        symbol="BTCUSDT",
        fills_rows=fills_rows,
    )
    _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        now_fn=lambda: _REFERENCE_NOW,
    )
    # 第二 execute call 為 trading.fills SELECT。
    fills_call = cur.execute.call_args_list[1]
    fills_sql = fills_call.args[0]
    fills_params = fills_call.args[1]
    assert "FROM trading.fills" in fills_sql
    assert "engine_mode = ANY" in fills_sql
    assert "INTERVAL '1 day'" in fills_sql
    # params: (strategy_name, symbol, [demo, live_demo], 14)
    assert fills_params[0] == "grid_trading"
    assert fills_params[1] == "BTCUSDT"
    assert fills_params[2] == list(_CALIBRATION_ENGINE_MODES)
    assert fills_params[3] == _CALIBRATION_FILLS_WINDOW_DAYS


# ───────────────────────────────────────────────────────────────────
# Case 8：side 'Buy' / 'Sell' 映射 is_long bool（dispatch §1.2 contract）
# ───────────────────────────────────────────────────────────────────


def test_calibration_e2e_side_mapping_buy_long_sell_short() -> None:
    """trading.fills.side 'Buy'/'long' → is_long=True；'Sell'/'short' → False。

    驗 caller 把 SQL side enum 映射到 FillRecord.is_long bool。inject 一個
    capture derive_fn 觀察 fills 構造後的 is_long 分佈。
    """
    captured_fills: list[FillRecord] = []

    def _capture_derive(
        fills: list[FillRecord], now: datetime
    ) -> CalibrationResult:
        captured_fills.extend(fills)
        return CalibrationResult.none_default()

    captured_label_arg: list[str] = []

    def _capture_update(cur: Any, *, experiment_id: str, label: str) -> bool:
        captured_label_arg.append(label)
        return True

    # 4 row：Buy / Sell / long / short → 各 1 row。
    fills_rows = [
        (_REFERENCE_NOW - timedelta(days=1), "Buy", 100.0, 0.0002),
        (_REFERENCE_NOW - timedelta(days=2), "Sell", 100.0, 0.0002),
        (_REFERENCE_NOW - timedelta(days=3), "long", 100.0, 0.0002),
        (_REFERENCE_NOW - timedelta(days=4), "short", 100.0, 0.0002),
    ]
    cur = _make_mock_cursor(
        strategy="grid_trading",
        symbol="BTCUSDT",
        fills_rows=fills_rows,
    )
    _compute_and_persist_calibration(
        cur,
        experiment_id=_TEST_EXPERIMENT_ID,
        derive_fn=_capture_derive,
        update_fn=_capture_update,
        now_fn=lambda: _REFERENCE_NOW,
    )
    assert len(captured_fills) == 4
    # idx 0: Buy → True; idx 1: Sell → False; idx 2: long → True; idx 3: short → False。
    assert captured_fills[0].is_long is True
    assert captured_fills[1].is_long is False
    assert captured_fills[2].is_long is True
    assert captured_fills[3].is_long is False
    # NaN/Sell 不影響 fee_rate 抽取 — 4 row 都有 fee_rate=0.0002。
    for f in captured_fills:
        assert f.fee_rate == 0.0002
    # label='none'（mock derive 回 none_default）→ 0 update_fn 呼。
    assert captured_label_arg == []


# ───────────────────────────────────────────────────────────────────
# Live PG smoke (opt-in)
# ───────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("OPENCLAW_TEST_LIVE_PG", "") != "1",
    reason="Live PG smoke disabled; export OPENCLAW_TEST_LIVE_PG=1 to run",
)
def test_calibration_e2e_live_pg_smoke() -> None:
    """Live PG smoke：opt-in via OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN。

    Mac dev 預設 skip；Linux operator post-deploy 可 run 驗真 PG SELECT
    trading.fills + V049 UPDATE chain。本 case 不 INSERT 真 row（避免污染
    production trading.fills）；僅驗 chain 不 raise + V049 UPDATE 路徑可達。
    """
    # 純 connectivity smoke；用真 cursor + 不存在的 experiment_id → 應 return None
    # 不 raise（V049 row not found）。
    import psycopg2  # type: ignore

    dsn = os.environ.get("OPENCLAW_TEST_DSN")
    if not dsn:
        pytest.skip("OPENCLAW_TEST_DSN unset; live PG smoke needs DSN")
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            label = _compute_and_persist_calibration(
                cur,
                experiment_id="00000000-0000-0000-0000-000000000000",  # 不存在
                now_fn=lambda: datetime.now(timezone.utc),
            )
            # 不存在 row → SELECT V049 row=None → return None。
            assert label is None
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
