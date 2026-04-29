"""Tests for stop-path cancel-all + verify pipeline (live / demo / paper).

驗收測試：停止路徑「先取消掛單 → 平倉 → 輪詢確認 Bybit 完全乾淨」鏈條：
- cancel-all REST 在 close_all_positions IPC **之前**被呼叫（順序保證）
- verify 輪詢正確識別 clean / residual 狀態
- 殘留時 errors 欄位顯式記載 residual_positions / residual_orders

These guarantee the user-observable bug ("stopping live/demo doesn't clear
open orders or positions") is fixed AND stays fixed.
"""

from __future__ import annotations

import os

# Required before importing app modules / 導入前必須設置
os.environ.setdefault("OPENCLAW_API_TOKEN", "test-token")
# Speed up tests — keep verify polling tight / 加速測試 — 縮短輪詢
os.environ.setdefault("OPENCLAW_STOP_VERIFY_MAX_ATTEMPTS", "3")
os.environ.setdefault("OPENCLAW_STOP_VERIFY_INTERVAL_SEC", "0.05")

from types import SimpleNamespace

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (
    live_session_account_routes as lsa,
    live_session_endpoints as lse,
    live_session_routes as lsr,
    paper_trading_routes as ptr,
    strategy_ai_routes as sar,
)


class _FakeRC:
    """Fake BybitClient capturing call order / 假 BybitClient 記錄呼叫順序。"""

    def __init__(self, *, positions=None, orders=None, cancel_clears=True):
        self._initial_positions = list(positions or [])
        self._initial_orders = list(orders or [])
        self._positions = list(self._initial_positions)
        self._orders = list(self._initial_orders)
        self._cancel_clears = cancel_clears
        self.calls: list[str] = []

    def get_positions(self, category="linear"):
        self.calls.append(f"get_positions:{category}")
        return list(self._positions)

    def get_active_orders(self, category="linear", symbol=None, settle_coin="USDT"):
        self.calls.append(f"get_active_orders:{category}")
        return list(self._orders)

    def cancel_all_orders(self, category="linear", symbol=None, settle_coin="USDT", base_coin=None):
        self.calls.append(f"cancel_all_orders:{category}:{settle_coin}")
        cancelled = list(self._orders)
        if self._cancel_clears:
            self._orders = []
        return cancelled

    def clear_positions(self):
        """Simulate close-orders filling on Bybit / 模擬平倉成交。"""
        self._positions = []


def _operator_actor(*scopes: str):
    return SimpleNamespace(
        actor_id="op-test",
        roles={"operator"},
        scopes=set(scopes),
    )


# ───────────────────────────────────────────────────────────────────────────────
# verify helper unit tests / verify 輔助函數單元測試
# ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_account_clean_returns_clean_when_empty():
    rc = _FakeRC(positions=[], orders=[])
    result = await sar._verify_account_clean(rc, env_label="demo")
    assert result["clean"] is True
    assert result["attempts"] == 1
    # Both REST endpoints queried at least once / 兩個 REST 端點都至少查過一次
    assert any(c.startswith("get_positions") for c in rc.calls)
    assert any(c.startswith("get_active_orders") for c in rc.calls)


@pytest.mark.asyncio
async def test_verify_account_clean_returns_residual_when_orders_remain():
    rc = _FakeRC(
        positions=[],
        orders=[{"symbol": "BTCUSDT", "orderId": "abc"}],
    )
    # Use minimum attempts / 用最小輪詢次數加速
    result = await sar._verify_account_clean(
        rc, env_label="demo", max_attempts=2, interval_sec=0.01,
    )
    assert result["clean"] is False
    assert result["residual_orders"] == 1
    assert "BTCUSDT" in result["residual_order_symbols"]


@pytest.mark.asyncio
async def test_verify_account_clean_returns_residual_when_positions_remain():
    rc = _FakeRC(
        positions=[{"symbol": "ETHUSDT", "size": "0.5", "side": "Buy"}],
        orders=[],
    )
    result = await sar._verify_account_clean(
        rc, env_label="live", max_attempts=2, interval_sec=0.01,
    )
    assert result["clean"] is False
    assert result["residual_positions"] == 1
    assert "ETHUSDT" in result["residual_position_symbols"]


@pytest.mark.asyncio
async def test_verify_account_clean_skipped_when_rc_none():
    result = await sar._verify_account_clean(None, env_label="demo")
    assert result.get("skipped") is True
    assert result["clean"] is False


# ───────────────────────────────────────────────────────────────────────────────
# Order sweep helpers / cancel-all 包裝函數
# ───────────────────────────────────────────────────────────────────────────────


def test_sweep_orphan_orders_calls_cancel_all_with_settle_coin():
    rc = _FakeRC(orders=[
        {"symbol": "BTCUSDT", "orderId": "1"},
        {"symbol": "ETHUSDT", "orderId": "2"},
    ])
    errors: list[str] = []
    result = sar._sweep_orphan_orders(rc, "demo", errors)
    assert result["cancelled"] == 2
    assert result["found"] == 2
    assert "BTCUSDT" in result["symbols"]
    assert "ETHUSDT" in result["symbols"]
    # cancel_all_orders 必使用 settleCoin=USDT 全帳戶清掃
    assert "cancel_all_orders:linear:USDT" in rc.calls
    assert errors == []


def test_sweep_orphan_orders_handles_none_client():
    errors: list[str] = []
    result = sar._sweep_orphan_orders(None, "live", errors)
    assert result == {"skipped": True, "reason": "rust_client_unavailable"}


def test_sweep_orphan_orders_handles_cancel_failure():
    class _Boom(_FakeRC):
        def cancel_all_orders(self, *a, **kw):
            self.calls.append("cancel_all_orders:RAISE")
            raise RuntimeError("bybit 503")

    rc = _Boom(orders=[{"symbol": "BTCUSDT"}])
    errors: list[str] = []
    result = sar._sweep_orphan_orders(rc, "demo", errors)
    assert result.get("skipped") is True
    assert "bybit 503" in result.get("reason", "")
    assert any("order_sweep_demo" in e for e in errors)


# ───────────────────────────────────────────────────────────────────────────────
# Live stop — order-of-operations contract
# Live 停止 — 操作順序契約：cancel-all 必須在 close_all_positions IPC 之前
# ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_live_stop_cancels_orders_before_close(monkeypatch):
    """Critical contract: cancel-all REST fires BEFORE close_all_positions IPC.

    若先 close 再 cancel，平倉途中 TP/SL 條件單可能誤觸發開新倉。順序倒置 = 設計失敗。
    """
    call_order: list[str] = []

    rc = _FakeRC(
        positions=[{"symbol": "BTCUSDT", "size": "0.1", "side": "Buy"}],
        orders=[{"symbol": "BTCUSDT", "orderId": "limit-1"}],
    )

    def _cancel_all_orders(*a, **kw):
        call_order.append("cancel_all_orders")
        rc._orders = []
        return [{"orderId": "limit-1", "orderLinkId": "link-1"}]

    rc.cancel_all_orders = _cancel_all_orders  # type: ignore[assignment]

    monkeypatch.setattr(lsr, "_require_operator", lambda actor: None)
    monkeypatch.setattr(lsr, "_set_execution_authority", lambda authority: None)
    monkeypatch.setattr(lse, "_revoke_live_governance_auth", lambda **kwargs: None)

    class _RustReader:
        def is_available(self):
            return True

    monkeypatch.setattr(lse, "get_rust_reader", lambda: _RustReader())
    monkeypatch.setattr(lsr, "_get_rust_client_safe", lambda: rc)

    async def _ipc(method, params):
        call_order.append(f"ipc:{method}")
        # After close_all_positions, simulate fills clearing positions
        # close_all_positions 後模擬成交清空持倉
        if method == "close_all_positions":
            rc.clear_positions()
        return {"ok": True}

    monkeypatch.setattr(lsr, "_ipc_command", _ipc)

    async def _orphan_positions(errors):
        call_order.append("orphan_positions")
        return {"swept": 0}

    monkeypatch.setattr(lsr, "_sweep_live_orphan_positions", _orphan_positions)

    response = await lse.post_live_session_stop(
        actor=_operator_actor("live:trade"),
    )

    # Order-of-operations contract / 順序契約
    assert call_order[0] == "cancel_all_orders", (
        f"cancel-all must run FIRST, got order: {call_order}"
    )
    assert "ipc:close_all_positions" in call_order
    assert call_order.index("cancel_all_orders") < call_order.index(
        "ipc:close_all_positions"
    )

    # Response carries new fields / 回應帶新欄位
    data = response["data"]
    assert "cancel_orders" in data
    assert "verify" in data
    assert data["cancel_orders"]["cancelled"] == 1
    assert data["verify"]["clean"] is True
    assert data["closed_all"] is True
    assert data["partial_failure"] is False


# ───────────────────────────────────────────────────────────────────────────────
# Demo stop — same order-of-operations + verify residual surfaces in errors
# Demo 停止 — 同樣順序契約 + verify 殘留須出現在 errors 欄位
# ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_demo_stop_cancels_orders_before_close_and_verifies(monkeypatch):
    call_order: list[str] = []
    rc = _FakeRC(
        positions=[{"symbol": "ETHUSDT", "size": "1.0", "side": "Sell"}],
        orders=[{"symbol": "ETHUSDT", "orderId": "tp-1"}],
    )

    def _cancel(*a, **kw):
        call_order.append("cancel_all_orders")
        rc._orders = []
        return [{"orderId": "tp-1"}]

    rc.cancel_all_orders = _cancel  # type: ignore[assignment]

    monkeypatch.setattr(sar, "_get_rust_client", lambda: rc)

    # Stub paper_trading_routes get_rust_reader / 補上 get_rust_reader stub
    class _Reader:
        def is_available(self):
            return True

    monkeypatch.setattr(ptr, "get_rust_reader", lambda: _Reader())

    async def _ipc(method, params):
        call_order.append(f"ipc:{method}")
        if method == "close_all_positions":
            rc.clear_positions()
        return {"ok": True}

    # _ipc_command lives in paper_trading_routes — demo route lazy-imports it.
    # _ipc_command 在 paper_trading_routes，demo route 懶加載。
    monkeypatch.setattr(ptr, "_ipc_command", _ipc)

    # Skip orphan position sweep noise / 跳過孤兒倉位 sweep 雜訊
    async def _orphan(errors):
        call_order.append("orphan_positions_demo")
        return {"swept": 0}

    monkeypatch.setattr(sar, "_sweep_demo_orphan_positions", _orphan)

    response = await sar.post_demo_session_stop(
        actor=_operator_actor("paper:trade"),
    )

    # cancel must run BEFORE close (Phase 1 → Phase 2 contract)
    assert "cancel_all_orders" in call_order
    assert "ipc:close_all_positions" in call_order
    assert call_order.index("cancel_all_orders") < call_order.index(
        "ipc:close_all_positions"
    )

    data = response["data"]
    assert "cancel_orders" in data
    assert "verify" in data
    assert data["verify"]["clean"] is True
    assert data["closed_all"] is True
    assert data["partial_failure"] is False


@pytest.mark.asyncio
async def test_demo_stop_surfaces_residual_in_errors(monkeypatch):
    """When verify times out with residual, errors[] must explicitly call it out.

    殘留時 errors 必須顯式記載 residual_positions / residual_orders；不能靜默回 200。
    """
    rc = _FakeRC(
        positions=[{"symbol": "BTCUSDT", "size": "0.1", "side": "Buy"}],
        orders=[],
        cancel_clears=True,
    )
    # Critical: do NOT clear positions on close — simulate stuck residual
    # 故意不清空持倉，模擬 stuck 殘留

    monkeypatch.setattr(sar, "_get_rust_client", lambda: rc)

    class _Reader:
        def is_available(self):
            return True

    monkeypatch.setattr(ptr, "get_rust_reader", lambda: _Reader())

    async def _ipc(method, params):
        return {"ok": True}  # close_all_positions does NOT clear rc._positions

    monkeypatch.setattr(ptr, "_ipc_command", _ipc)

    async def _orphan(errors):
        return {"swept": 0}

    monkeypatch.setattr(sar, "_sweep_demo_orphan_positions", _orphan)

    response = await sar.post_demo_session_stop(
        actor=_operator_actor("paper:trade"),
    )

    data = response["data"]
    assert data["verify"]["clean"] is False
    assert data["verify"]["residual_positions"] == 1
    assert "BTCUSDT" in data["verify"]["residual_position_symbols"]
    # errors 必含 verify_residual / errors must include verify_residual marker
    assert data["errors"] is not None
    assert any("demo_verify_residual" in e for e in data["errors"])
    assert data["closed_all"] is False
    assert data["partial_failure"] is True
    assert data["status"] == "partial_failure"


@pytest.mark.asyncio
async def test_demo_close_all_reports_orphan_sweep_failure(monkeypatch):
    async def _ipc(method, params):
        assert method == "close_all_positions"
        assert params == {"engine": "demo"}
        return {"ok": True}

    async def _orphan(errors):
        errors.append("orphan_BTCUSDT: bybit rejected")
        return {"swept": 0, "found": 1}

    monkeypatch.setattr(sar, "_require_demo_session_write", lambda actor: None)
    monkeypatch.setattr(ptr, "_ipc_command", _ipc)
    monkeypatch.setattr(sar, "_sweep_demo_orphan_positions", _orphan)

    response = await sar.post_demo_close_all_positions(
        actor=_operator_actor("paper:trade"),
    )

    data = response["data"]
    assert data["status"] == "partial_failure"
    assert data["closed_all"] is False
    assert data["partial_failure"] is True
    assert data["errors"] == ["orphan_BTCUSDT: bybit rejected"]


@pytest.mark.asyncio
async def test_live_close_all_reports_orphan_sweep_failure(monkeypatch):
    async def _ipc(method, params):
        assert method == "close_all_positions"
        assert params == {"engine": "live"}
        return {"ok": True}

    async def _orphan(errors):
        errors.append("orphan_ETHUSDT: live close rejected")
        return {"swept": 0, "found": 1}

    monkeypatch.setattr(lsa, "_require_live_trade", lambda actor: None)
    monkeypatch.setattr(lsa, "_phantom_view_guard_write", lambda: None)
    monkeypatch.setattr(lsr, "_ipc_command", _ipc)
    monkeypatch.setattr(lsr, "_sweep_live_orphan_positions", _orphan)

    response = await lsa.post_live_close_all_positions(
        actor=_operator_actor("live:trade"),
    )

    data = response["data"]
    assert data["status"] == "partial_failure"
    assert data["closed_all"] is False
    assert data["partial_failure"] is True
    assert data["errors"] == ["orphan_ETHUSDT: live close rejected"]
