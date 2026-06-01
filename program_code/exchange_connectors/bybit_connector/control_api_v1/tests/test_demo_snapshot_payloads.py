"""demo_snapshot_payloads 純邏輯單元測試（P2b 抽取後模塊匹配測試）。

涵蓋：_num / _time_ms best-effort 解析、Rust snake_case → Bybit camelCase 映射
（_normalize_order / _normalize_execution，含 closedPnl 0.0 不誤落 fallback）、
paper_state → GUI 餘額/持倉形狀。快照讀路徑整合測試見 test_gui_fast_snapshot_routes.py。
"""
from __future__ import annotations

from app import demo_snapshot_payloads as dp


# ── _num ─────────────────────────────────────────────────────────────────────


def test_num_parses_and_defaults():
    assert dp._num("1.5") == 1.5
    assert dp._num(None) == 0.0
    assert dp._num("garbage", default=9.0) == 9.0


def test_num_nan_falls_back_to_default():
    assert dp._num(float("nan"), default=3.0) == 3.0


# ── _time_ms ───────────────────────────────────────────────────────────────────


def test_time_ms_prefers_first_present_key():
    assert dp._time_ms({"timestamp_ms": 111, "exec_time": 222}) == 111
    assert dp._time_ms({"execTime": "333"}) == 333


def test_time_ms_returns_zero_when_no_timestamp():
    assert dp._time_ms({"symbol": "X"}) == 0


# ── _normalize_order ───────────────────────────────────────────────────────────


def test_normalize_order_maps_snake_to_camel():
    out = dp._normalize_order({
        "order_id": "OID1",
        "order_status": "New",
        "order_type": "Limit",
        "trigger_price": "1.5",
    })
    assert out["orderId"] == "OID1"
    assert out["orderStatus"] == "New"
    assert out["orderType"] == "Limit"
    assert out["triggerPrice"] == "1.5"


def test_normalize_order_passthrough_non_dict():
    assert dp._normalize_order("not-a-dict") == "not-a-dict"


# ── _normalize_execution ───────────────────────────────────────────────────────


def test_normalize_execution_maps_fields_and_derives_side():
    out = dp._normalize_execution({
        "exec_qty": "0.01",
        "exec_price": "50000",
        "exec_fee": "0.1",
        "exec_time": "1700000000000",
        "is_long": True,
        "closed_pnl": 1.0,
    })
    assert out["execQty"] == "0.01"
    assert out["execPrice"] == "50000"
    assert out["side"] == "Buy"
    assert out["closedPnl"] == 1.0


def test_normalize_execution_zero_closed_pnl_not_lost_to_fallback():
    # closed_pnl=0.0 是常見開倉腿值；不可被 `or` 落回 None/realized_pnl
    out = dp._normalize_execution({"closed_pnl": 0.0, "is_long": False})
    assert out["closedPnl"] == 0.0
    assert out["side"] == "Sell"


def test_normalize_execution_passthrough_non_dict():
    assert dp._normalize_execution(42) == 42


# ── _paper_state_balance_payload ───────────────────────────────────────────────


def test_balance_payload_sums_unrealized_and_mirrors_equity_keys():
    state = {
        "balance": 1000.0,
        "initial_balance": 990.0,
        "peak_balance": 1010.0,
        "positions": [
            {"unrealized_pnl": 1.5},
            {"unrealized_pnl": -0.5},
            "not-a-dict",
        ],
    }
    out = dp._paper_state_balance_payload(state)
    assert out["totalEquity"] == 1000.0
    assert out["balance"] == 1000.0
    assert out["totalWalletBalance"] == 1000.0
    assert out["unrealized_pnl"] == 1.0
    assert out["engine_initial_balance"] == 990.0
    assert out["read_model"] == "rust_snapshot_fast"


def test_balance_payload_prefers_bybit_sync_balance():
    state = {"balance": 1.0, "bybit_sync_balance": 1002.5}
    out = dp._paper_state_balance_payload(state)
    assert out["totalEquity"] == 1002.5
    # engine_current_balance 仍取自原始 balance 欄
    assert out["engine_current_balance"] == 1.0


# ── _paper_state_positions_for_gui ─────────────────────────────────────────────


def test_positions_for_gui_normalizes_shape():
    state = {
        "positions": [
            {
                "symbol": "BTCUSDT",
                "qty": 0.1,
                "entry_price": 50000.0,
                "mark_price": 50100.0,
                "is_long": True,
                "owner_strategy": "ma_crossover",
            }
        ]
    }
    out = dp._paper_state_positions_for_gui(state)
    assert len(out) == 1
    row = out[0]
    assert row["side"] == "Buy"
    assert row["avgPrice"] == 50000.0
    assert row["markPrice"] == 50100.0
    assert row["category"] == "linear"
    assert row["owner_strategy"] == "ma_crossover"


def test_positions_for_gui_inverse_category_for_usd_pair():
    state = {"positions": [{"symbol": "BTCUSD", "qty": 1, "entry_price": 50000.0}]}
    out = dp._paper_state_positions_for_gui(state)
    assert out[0]["category"] == "inverse"


def test_positions_for_gui_empty_when_no_positions():
    assert dp._paper_state_positions_for_gui({}) == []
    assert dp._paper_state_positions_for_gui({"positions": "bad"}) == []
