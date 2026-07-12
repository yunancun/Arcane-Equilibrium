"""
E4：伺服器端對賬快照提供者測試（reconcile Path B §1/§2/§5）。

MODULE_NOTE (中文):
  覆蓋 governance_reconcile_snapshots 兩個提供者的「形狀轉換正確性」與「fail-closed」:
    - build_local_reconcile_snapshot：IPC 快照 → 引擎契約(positions LIST→DICT、drop size==0、
      side 由 is_long、balance SCALAR→{"USDT":...}、category 推斷、fills side 補全);引擎不可用回 None。
    - build_demo_reconcile_snapshot：只讀 httpx client → 引擎契約;任一原語 raise / client 缺
      → 拋 DemoSnapshotUnavailable,**絕不回空 {}**(空 demo 會偽造 FATAL POSITION_MISSING → 誤凍結)。
  Mock 規則：只 stub IO 邊界(Rust reader / httpx client),轉換業務邏輯真跑。

  NEEDS-LINUX-RUNTIME(非本檔可證)：真 api-demo GET 往返、真 Rust IPC 快照形狀。本檔只證
  Mac 單元/契約層的轉換與 fail-closed 分支。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.governance_reconcile_snapshots import (
    build_local_reconcile_snapshot,
    build_demo_reconcile_snapshot,
    DemoSnapshotUnavailable,
    _infer_category,
)

SNAP_MOD = "app.governance_reconcile_snapshots"


# ═══════════════════════════════════════════════════════════════════════════════
# build_local_reconcile_snapshot（2f）— IPC 快照 → 契約形狀轉換
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildLocalReconcileSnapshot:

    def _reader_with(self, paper_state, fills=None):
        reader = MagicMock()
        reader.is_engine_available.return_value = True
        reader.get_paper_state.return_value = paper_state
        reader.get_recent_fills.return_value = fills or []
        return reader

    def test_positions_list_to_dict_drop_zero_side_and_balance_transform(self):
        # positions LIST→DICT、drop size==0、side 由 is_long、avg_entry_price 回退、
        # category 推斷、balance SCALAR→{"USDT":...}、fills side 補全 —— 一次驗證所有轉換。
        paper_state = {
            "positions": [
                {"symbol": "BTCUSDT", "is_long": True, "size": 1.5, "entry_price": 50000},
                {"symbol": "ETHUSDT", "is_long": False, "qty": 2.0, "avg_entry_price": 3000},
                {"symbol": "XRPUSDT", "is_long": True, "size": 0},   # size==0 → 必須丟棄
                {"symbol": "BTCUSD", "is_long": True, "size": 10},   # inverse 品類
            ],
            "balance": 12345.67,
        }
        fills = [{"symbol": "BTCUSDT", "is_long": True, "qty": 1.0, "price": 50000}]  # 缺 side
        reader = self._reader_with(paper_state, fills)

        with patch(f"{SNAP_MOD}.get_rust_reader", return_value=reader):
            snap = build_local_reconcile_snapshot(engine="demo")

        # reader 應以指定 engine 讀取
        reader.is_engine_available.assert_called_once_with("demo")
        reader.get_paper_state.assert_called_once_with(engine="demo")

        positions = snap["positions"]
        assert isinstance(positions, dict)
        assert set(positions.keys()) == {"BTCUSDT", "ETHUSDT", "BTCUSD"}  # XRPUSDT(size 0)被丟
        assert positions["BTCUSDT"] == {
            "side": "Buy", "size": 1.5, "avg_entry_price": 50000, "category": "linear",
        }
        assert positions["ETHUSDT"]["side"] == "Sell"          # is_long False → Sell
        assert positions["ETHUSDT"]["size"] == 2.0             # size 缺 → 取 qty
        assert positions["ETHUSDT"]["avg_entry_price"] == 3000  # entry_price 缺 → 回退 avg_entry_price
        assert positions["BTCUSD"]["category"] == "inverse"    # USD 結尾 → inverse

        assert snap["balances"] == {"USDT": 12345.67}           # SCALAR → dict
        assert snap["orders"] == []                             # v1 本地訂單對賬關閉
        assert snap["fills"][0]["side"] == "Buy"               # 缺 side 由 is_long 補
        assert isinstance(snap["snapshot_ts_ms"], int)

    def test_fills_not_mutated_in_place(self):
        # 補 side 必須複製,不得原地污染 reader 的快照(避免副作用回寫 IPC 快取)。
        original_fill = {"symbol": "BTCUSDT", "is_long": True, "qty": 1.0}
        reader = self._reader_with({"positions": [], "balance": 0}, [original_fill])
        with patch(f"{SNAP_MOD}.get_rust_reader", return_value=reader):
            snap = build_local_reconcile_snapshot(engine="demo")
        assert snap["fills"][0]["side"] == "Buy"
        assert "side" not in original_fill  # 原字典未被改動

    def test_reader_none_returns_none(self):
        # reader 缺失 → fail-closed None(呼叫端短路 STALE_DATA)。
        with patch(f"{SNAP_MOD}.get_rust_reader", return_value=None):
            assert build_local_reconcile_snapshot(engine="demo") is None

    def test_engine_unavailable_returns_none(self):
        # 引擎快照過期/不可用 → None。
        reader = MagicMock()
        reader.is_engine_available.return_value = False
        with patch(f"{SNAP_MOD}.get_rust_reader", return_value=reader):
            assert build_local_reconcile_snapshot(engine="demo") is None

    def test_paper_state_none_returns_none(self):
        # 引擎可用但無 state → None。
        reader = MagicMock()
        reader.is_engine_available.return_value = True
        reader.get_paper_state.return_value = None
        with patch(f"{SNAP_MOD}.get_rust_reader", return_value=reader):
            assert build_local_reconcile_snapshot(engine="demo") is None


class TestInferCategory:
    def test_usd_suffix_is_inverse(self):
        assert _infer_category("BTCUSD") == "inverse"

    def test_usdt_suffix_is_linear(self):
        assert _infer_category("BTCUSDT") == "linear"


# ═══════════════════════════════════════════════════════════════════════════════
# build_demo_reconcile_snapshot（2g）— 只讀 client → 契約 / fail-closed 絕不回 {}
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildDemoReconcileSnapshot:

    def _client_ok(self):
        client = MagicMock()

        def pos_scan(category, settle_coin="USDT"):
            if category == "linear":
                return [
                    {"symbol": "BTCUSDT", "side": "Buy", "size": "1.5", "avgPrice": "50000"},
                    {"symbol": "ZEROUSDT", "side": "Buy", "size": "0", "avgPrice": "1"},  # drop
                ]
            return []  # inverse(幣本位,settleCoin=USDT full-scan 回空)

        client.get_positions_full_scan.side_effect = pos_scan
        client.get_active_orders_full_scan.return_value = [{"orderId": "o1"}]
        client.get_executions.return_value = [{"execId": "e1"}]
        client.refresh_balance.return_value = {
            "coins": {"USDT": {"wallet_balance": "10000.5"}, "ZEROC": {"wallet_balance": "0"}},
        }
        return client

    def test_success_transform(self):
        client = self._client_ok()
        with patch("app.strategy_ai_routes._get_rust_client", return_value=client):
            snap = build_demo_reconcile_snapshot()

        assert snap["positions"] == {
            "BTCUSDT": {"side": "Buy", "size": 1.5, "avg_entry_price": 50000.0, "category": "linear"},
        }  # ZEROUSDT(size 0)被丟棄
        assert snap["balances"] == {"USDT": 10000.5}   # ZEROC(0 餘額)被丟棄
        assert snap["orders"] == [{"orderId": "o1"}]
        assert snap["fills"] == [{"execId": "e1"}]
        assert isinstance(snap["snapshot_ts_ms"], int)

    def test_funding_exectype_filtered_out_of_fills(self):
        # v2.C：get_executions 混入的 execType=Funding/Settle 非成交列必須被濾掉,
        # 只保留 {Trade,AdlTrade,BustTrade};缺 execType 的列保守視為 Trade 保留。
        client = MagicMock()
        client.get_positions_full_scan.return_value = []
        client.get_active_orders_full_scan.return_value = []
        client.get_executions.return_value = [
            {"execId": "t1", "execType": "Trade"},
            {"execId": "f1", "execType": "Funding"},     # 資金費結算 → 丟棄
            {"execId": "a1", "execType": "AdlTrade"},
            {"execId": "s1", "execType": "Settle"},       # 非成交 → 丟棄
            {"execId": "b1", "execType": "BustTrade"},
            {"execId": "u1"},                              # 缺 execType → 保守保留
        ]
        client.refresh_balance.return_value = {"coins": {}}
        with patch("app.strategy_ai_routes._get_rust_client", return_value=client):
            snap = build_demo_reconcile_snapshot()

        kept = {f["execId"] for f in snap["fills"]}
        assert kept == {"t1", "a1", "b1", "u1"}
        assert "f1" not in kept  # Funding 已濾掉
        assert "s1" not in kept  # Settle 已濾掉

    def test_client_none_raises_unavailable(self):
        # 憑證缺 / 槽位缺 → _get_rust_client 回 None → fail-closed(絕不回 {})。
        with patch("app.strategy_ai_routes._get_rust_client", return_value=None):
            with pytest.raises(DemoSnapshotUnavailable):
                build_demo_reconcile_snapshot()

    def test_positions_primitive_raises_wrapped_never_empty(self):
        # 任一原語 raise(如 retCode≠0 的 BybitBusinessError)→ 一律包成 DemoSnapshotUnavailable,
        # **絕不吞成空 {}**。以 pytest.raises 證明沒有回傳值(不會退化為空 demo)。
        client = MagicMock()
        client.get_positions_full_scan.side_effect = RuntimeError("retCode=10001 invalid")
        with patch("app.strategy_ai_routes._get_rust_client", return_value=client):
            with pytest.raises(DemoSnapshotUnavailable) as exc:
                build_demo_reconcile_snapshot()
        assert "10001" in str(exc.value)  # 原始錯誤訊息被保留

    def test_balance_primitive_raises_wrapped(self):
        # 餘額原語 raise 同樣 fail-closed(前段 GET 成功不得掩蓋後段失敗)。
        client = MagicMock()
        client.get_positions_full_scan.return_value = []
        client.get_active_orders_full_scan.return_value = []
        client.get_executions.return_value = []
        client.refresh_balance.side_effect = RuntimeError("balance transport error")
        with patch("app.strategy_ai_routes._get_rust_client", return_value=client):
            with pytest.raises(DemoSnapshotUnavailable):
                build_demo_reconcile_snapshot()
