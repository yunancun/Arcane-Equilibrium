"""
E4 Edge Case Tests: PaperTradingEngine Boundary Conditions
纸上交易引擎边界条件测试

MODULE_NOTE (中文):
  测试 PaperTradingEngine 在边界/异常输入下的行为。
  覆盖：余额不足、损坏的 JSON 状态文件、qty=0 提交、
  balance 过低无法开仓。

MODULE_NOTE (English):
  Tests PaperTradingEngine under boundary/anomalous inputs.
  Covers: insufficient balance, corrupt JSON state file, qty=0 submit,
  balance too low to open position.

作者: E4 (Test Engineer)
日期: 2026-04-01
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.paper_trading_engine import (
    PaperStateStore,
    PaperTradingEngine,
    SIDE_BUY,
    SIDE_SELL,
)

# Import shared fixtures from conftest (includes proper risk_manager setup)
from conftest import (
    tmp_state_file,
    paper_state_store,
    paper_engine,
    active_paper_engine,
)


class TestPaperEngineEdgeCases:
    """Edge case tests for PaperTradingEngine.
    PaperTradingEngine 边界条件测试。"""

    def test_submit_order_qty_zero_raises_value_error(self, active_paper_engine):
        """submit_order with qty=0 should raise ValueError from create_paper_order.
        qty=0 的 submit_order 应从 create_paper_order 抛出 ValueError。"""
        with pytest.raises(ValueError, match="Quantity must be positive"):
            active_paper_engine.submit_order(
                symbol="BTCUSDT", side="Buy", order_type="market",
                qty=0, price=60000.0,
            )

    def test_submit_order_insufficient_balance_rejected(self, active_paper_engine):
        """Order exceeding available balance should be rejected with reason.
        超出可用余额的订单应被拒绝并给出原因。"""
        result = active_paper_engine.submit_order(
            symbol="BTCUSDT", side="Buy", order_type="market",
            qty=100, price=60000.0,  # notional = 6,000,000 >> 10,000
        )
        assert result["rejected_reason"] == "insufficient_margin"

    def test_malformed_json_state_file_raises_on_read(self):
        """PaperStateStore reading corrupt JSON should raise JSONDecodeError.
        PaperStateStore 读取损坏的 JSON 应抛出 JSONDecodeError。"""
        tmpdir = tempfile.mkdtemp(prefix="openclaw_json_test_")
        fpath = os.path.join(tmpdir, "paper_state.json")
        # Write valid state first (PaperStateStore constructor writes default)
        store = PaperStateStore(fpath)
        # Now corrupt the file
        with open(fpath, "w") as f:
            f.write("{broken json!}")
        # Invalidate cache so next read hits disk
        store._cache = None
        with pytest.raises(json.JSONDecodeError):
            store.read()

    def test_start_session_with_zero_balance(self, paper_engine):
        """Starting a session with 0 balance should still create valid state.
        0 余额启动 session 应创建有效状态。"""
        paper_engine.start_session(initial_balance=0.0)
        state = paper_engine.store.read()
        assert state["session"]["current_paper_balance_usdt"] == 0.0
        assert state["session"]["session_state"] == "active"
