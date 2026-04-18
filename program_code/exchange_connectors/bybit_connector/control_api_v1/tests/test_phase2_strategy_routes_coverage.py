"""
E4 B10 -- Phase 2 Strategy Routes Coverage Tests
E4 B10 -- Phase 2 策略路由覆蓋率測試

MODULE_NOTE (中文):
  本模組針對 phase2_strategy_routes.py 的路由邏輯進行覆蓋率測試。
  不啟動真實伺服器，直接 mock 依賴項並呼叫路由 handler 函數。
  涵蓋：策略管理（activate/pause/stop/create/delete）、
  kline/indicator/signal 路由、error 路徑、H0Gate 注入、
  PipelineBridge 接線、輸入驗證。

MODULE_NOTE (English):
  Coverage tests for phase2_strategy_routes.py route logic.
  Does NOT start a real server -- mocks dependencies and calls route
  handler functions directly.
  Covers: strategy management (activate/pause/stop/create/delete),
  kline/indicator/signal routes, error paths, H0Gate injection,
  PipelineBridge wiring, input validation.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── PATH SETUP ──
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Import production helpers that do NOT trigger heavy module-level side effects ──
from app.phase2_strategy_routes import (
    _validate_symbol,
    _validate_strategy_name,
    _envelope,
    _VALID_TIMEFRAMES,
    _SYMBOL_PATTERN,
    _STRATEGY_NAME_PATTERN,
)

# We import route handlers lazily (they need mocked singletons).
# Route handler functions will be tested through their module-level references
# with singletons patched.

# ── Helpers ──

def _run(coro):
    """Run an async function synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeActor:
    """Minimal AuthenticatedActor stand-in."""
    role = "operator"
    token = "test-token"


# ═════════════════════════════════════════════════════════════════════════════
# Group 1: Input Validation Functions (pure, no I/O)
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateSymbol:
    def test_valid_symbol(self):
        assert _validate_symbol("BTCUSDT") == "BTCUSDT"

    def test_lowercase_normalised(self):
        assert _validate_symbol("ethusdt") == "ETHUSDT"

    def test_whitespace_stripped(self):
        assert _validate_symbol("  BTCUSDT  ") == "BTCUSDT"

    def test_empty_string(self):
        assert _validate_symbol("") is None

    def test_special_chars_rejected(self):
        assert _validate_symbol("BTC/USDT") is None

    def test_too_long_rejected(self):
        assert _validate_symbol("A" * 21) is None

    def test_unicode_rejected(self):
        assert _validate_symbol("BTC\u00e9") is None


class TestValidateStrategyName:
    def test_valid_name(self):
        assert _validate_strategy_name("ma_crossover") == "ma_crossover"

    def test_dash_allowed(self):
        assert _validate_strategy_name("my-strat-1") == "my-strat-1"

    def test_empty_rejected(self):
        assert _validate_strategy_name("") is None

    def test_special_chars_rejected(self):
        assert _validate_strategy_name("strat!@#") is None

    def test_too_long_rejected(self):
        assert _validate_strategy_name("x" * 51) is None

    def test_spaces_rejected(self):
        assert _validate_strategy_name("my strat") is None


class TestEnvelope:
    def test_basic_envelope(self):
        result = _envelope({"key": "val"})
        assert result["action_result"] == "success"
        assert result["data"] == {"key": "val"}
        assert result["is_simulated"] is True
        assert result["data_category"] == "paper_simulated"

    def test_custom_action(self):
        result = _envelope({}, action="error")
        assert result["action_result"] == "error"


# ═════════════════════════════════════════════════════════════════════════════
# Group 2: Route Handler Tests (mock singletons)
# ═════════════════════════════════════════════════════════════════════════════

# To avoid heavy module imports, we patch the module-level singletons.
# TD-02: Routes were split into sub-modules; patches must target where the name is looked up.
# TD-02：路由已拆分到子模組；patch 目標必須是名稱實際查找的模組。

_MOD = "app.phase2_strategy_routes"  # kept for backward compat reference
_MOD_READ = "app.strategy_read_routes"
_MOD_WRITE = "app.strategy_write_routes"
_MOD_AI = "app.strategy_ai_routes"


class TestGetKlinesRoute:
    @patch(f"{_MOD_READ}.get_rust_reader")
    @patch(f"{_MOD_READ}.KLINE_MANAGER")
    def test_happy_path(self, mock_km, mock_rust):
        # Disable Rust-first path to test Python fallback / 禁用 Rust 優先路徑以測試 Python 回退
        mock_rust.return_value.is_available.return_value = False
        from app.phase2_strategy_routes import get_klines
        mock_km.get_latest_klines.return_value = [{"o": 1, "h": 2}]
        mock_km.get_current_bar.return_value = None
        result = _run(get_klines("BTCUSDT", "1m", n=10, actor=_FakeActor()))
        assert result["action_result"] == "success"
        assert result["data"]["symbol"] == "BTCUSDT"
        assert result["data"]["count"] == 1

    def test_invalid_symbol_400(self):
        from app.phase2_strategy_routes import get_klines
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _run(get_klines("INVALID!", "1m", n=10, actor=_FakeActor()))
        assert exc.value.status_code == 400

    def test_invalid_timeframe_400(self):
        from app.phase2_strategy_routes import get_klines
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _run(get_klines("BTCUSDT", "99z", n=10, actor=_FakeActor()))
        assert exc.value.status_code == 400

    @patch(f"{_MOD_READ}.get_rust_reader")
    @patch(f"{_MOD_READ}.KLINE_MANAGER")
    def test_exception_500(self, mock_km, mock_rust):
        # Disable Rust-first to test Python error path / 禁用 Rust 以測試 Python 錯誤路徑
        mock_rust.return_value.is_available.return_value = False
        from app.phase2_strategy_routes import get_klines
        from fastapi import HTTPException
        mock_km.get_latest_klines.side_effect = RuntimeError("boom")
        with pytest.raises(HTTPException) as exc:
            _run(get_klines("BTCUSDT", "1m", n=10, actor=_FakeActor()))
        assert exc.value.status_code == 500


class TestGetIndicatorsRoute:
    @patch(f"{_MOD_READ}.get_rust_reader")
    @patch(f"{_MOD_READ}.INDICATOR_ENGINE")
    def test_happy_path(self, mock_ie, mock_rr):
        # Mock Rust reader unavailable so Python fallback is tested
        # Mock Rust reader 不可用，測試 Python 降級路徑
        mock_rr.return_value.is_available.return_value = False
        from app.phase2_strategy_routes import get_indicators
        mock_ie.get_indicators.return_value = {"rsi": 50}
        result = _run(get_indicators("ETHUSDT", "5m", actor=_FakeActor()))
        assert result["data"]["indicators"] == {"rsi": 50}

    def test_invalid_symbol(self):
        from app.phase2_strategy_routes import get_indicators
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _run(get_indicators("!!", "5m", actor=_FakeActor()))
        assert exc.value.status_code == 400


class TestGetSignalsRoute:
    @patch(f"{_MOD_READ}.get_rust_reader")
    @patch(f"{_MOD_READ}.SIGNAL_ENGINE")
    def test_happy_path(self, mock_se, mock_rr):
        # Mock Rust reader unavailable so Python fallback is tested
        # Mock Rust reader 不可用，測試 Python 降級路徑
        mock_rr.return_value.is_available.return_value = False
        from app.phase2_strategy_routes import get_signals
        mock_se.get_latest_signals.return_value = [{"sig": "buy"}]
        result = _run(get_signals(symbol=None, n=10, actor=_FakeActor()))
        assert result["data"]["count"] == 1

    def test_invalid_filter_symbol(self):
        from app.phase2_strategy_routes import get_signals
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _run(get_signals(symbol="!!!", n=10, actor=_FakeActor()))
        assert exc.value.status_code == 400


class TestStrategyLifecycleRoutes:
    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_activate_happy(self, mock_orch):
        from app.phase2_strategy_routes import activate_strategy
        mock_orch.activate_strategy.return_value = True
        result = _run(activate_strategy("ma_crossover", actor=_FakeActor()))
        assert result["data"]["action"] == "activated"

    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_activate_not_found(self, mock_orch):
        from app.phase2_strategy_routes import activate_strategy
        from fastapi import HTTPException
        mock_orch.activate_strategy.return_value = False
        with pytest.raises(HTTPException) as exc:
            _run(activate_strategy("nonexistent", actor=_FakeActor()))
        assert exc.value.status_code == 404

    def test_activate_invalid_name(self):
        from app.phase2_strategy_routes import activate_strategy
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _run(activate_strategy("bad name!!", actor=_FakeActor()))
        assert exc.value.status_code == 400

    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_pause_happy(self, mock_orch):
        from app.phase2_strategy_routes import pause_strategy
        mock_orch.pause_strategy.return_value = True
        result = _run(pause_strategy("ma_crossover", actor=_FakeActor()))
        assert result["data"]["action"] == "paused"

    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_stop_happy(self, mock_orch):
        from app.phase2_strategy_routes import stop_strategy
        mock_orch.stop_strategy.return_value = True
        result = _run(stop_strategy("ma_crossover", actor=_FakeActor()))
        assert result["data"]["action"] == "stopped"

    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_stop_not_found(self, mock_orch):
        from app.phase2_strategy_routes import stop_strategy
        from fastapi import HTTPException
        mock_orch.stop_strategy.return_value = False
        with pytest.raises(HTTPException) as exc:
            _run(stop_strategy("nonexist", actor=_FakeActor()))
        assert exc.value.status_code == 404


class TestDeleteRoute:
    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_delete_happy(self, mock_orch):
        from app.phase2_strategy_routes import delete_strategy
        mock_orch.remove_strategy.return_value = True
        result = _run(delete_strategy("ma_crossover", actor=_FakeActor()))
        assert result["data"]["action"] == "deleted"

    @patch(f"{_MOD_WRITE}.ORCHESTRATOR")
    def test_delete_not_found(self, mock_orch):
        from app.phase2_strategy_routes import delete_strategy
        from fastapi import HTTPException
        mock_orch.remove_strategy.return_value = False
        with pytest.raises(HTTPException) as exc:
            _run(delete_strategy("nope", actor=_FakeActor()))
        assert exc.value.status_code == 404

    def test_delete_invalid_name(self):
        from app.phase2_strategy_routes import delete_strategy
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _run(delete_strategy("bad name!!", actor=_FakeActor()))
        assert exc.value.status_code == 400


class TestGetStrategyStatusRoute:
    @patch(f"{_MOD_READ}.get_rust_reader")
    @patch(f"{_MOD_READ}.ORCHESTRATOR")
    def test_happy(self, mock_orch, mock_rr):
        # Mock Rust reader unavailable so Python fallback is tested
        # Mock Rust reader 不可用，測試 Python 降級路徑
        mock_rr.return_value.is_available.return_value = False
        from app.phase2_strategy_routes import get_strategy_status
        mock_orch.get_strategy_status.return_value = {"name": "x", "state": "active"}
        result = _run(get_strategy_status("ma_crossover", actor=_FakeActor()))
        assert result["data"]["state"] == "active"

    @patch(f"{_MOD_READ}.get_rust_reader")
    @patch(f"{_MOD_READ}.ORCHESTRATOR")
    def test_not_found(self, mock_orch, mock_rr):
        mock_rr.return_value.is_available.return_value = False
        from app.phase2_strategy_routes import get_strategy_status
        from fastapi import HTTPException
        mock_orch.get_strategy_status.return_value = None
        with pytest.raises(HTTPException) as exc:
            _run(get_strategy_status("no_such", actor=_FakeActor()))
        assert exc.value.status_code == 404


class TestPipelineAndScannerRoutes:
    @patch(f"{_MOD_READ}.PIPELINE_BRIDGE", None)
    def test_pipeline_stats_unavailable(self):
        from app.phase2_strategy_routes import get_pipeline_stats
        import app.ipc_state_reader as _ipc
        _orig = _ipc._READER
        # Force Rust reader unavailable so fallback to PIPELINE_BRIDGE=None → available=False
        from app.ipc_state_reader import RustSnapshotReader
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _ipc._READER = RustSnapshotReader(data_dir=d)
            result = _run(get_pipeline_stats(actor=_FakeActor()))
            _ipc._READER = _orig
        assert result["data"]["available"] is False

    def test_pipeline_stats_happy(self):
        """DEAD-PY-2: PIPELINE_BRIDGE permanently None — Rust engine is sole source.
        When Rust reader has no data, endpoint returns available=False.
        DEAD-PY-2：PIPELINE_BRIDGE 永久 None — Rust 引擎為唯一數據源。
        當 Rust reader 無數據時，端點返回 available=False。"""
        from app.phase2_strategy_routes import get_pipeline_stats
        import app.ipc_state_reader as _ipc
        _orig = _ipc._READER
        from app.ipc_state_reader import RustSnapshotReader
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            _ipc._READER = RustSnapshotReader(data_dir=d)
            result = _run(get_pipeline_stats(actor=_FakeActor()))
            _ipc._READER = _orig
        assert result["data"]["available"] is False

    def test_scanner_ipc_unavailable_returns_empty(self):
        """IPC-SCAN-1c: Python MARKET_SCANNER stub removed; endpoint now forwards to
        Rust IPC `get_scanner_status`. When IPC fails, fail-soft to empty list.
        IPC-SCAN-1c：Python stub 已移除，路由透過 IPC 讀 Rust；IPC 失敗時降級為空列。"""
        from app.phase2_strategy_routes import get_scanner_opportunities

        class _BrokenClient:
            async def connect(self): raise RuntimeError("ipc down")
            async def call(self, *a, **kw): pass
            async def disconnect(self): pass

        with patch("app.ipc_client.EngineIPCClient", _BrokenClient):
            result = _run(get_scanner_opportunities(actor=_FakeActor()))
        assert result["data"]["opportunities"] == []
        assert result["data"]["source"] == "unavailable"


class TestTelegramStatusRoute:
    @patch(f"{_MOD_AI}.TELEGRAM", None)
    def test_telegram_not_loaded(self):
        from app.phase2_strategy_routes import get_telegram_status
        result = _run(get_telegram_status(actor=_FakeActor()))
        assert result["data"]["enabled"] is False

    @patch(f"{_MOD_AI}.TELEGRAM")
    def test_telegram_available(self, mock_tg):
        from app.phase2_strategy_routes import get_telegram_status
        mock_tg.get_stats.return_value = {"enabled": True, "sent": 5}
        result = _run(get_telegram_status(actor=_FakeActor()))
        assert result["data"]["sent"] == 5


class TestDynamicRiskRoutes:
    @patch(f"{_MOD_READ}.AUTO_DEPLOYER", None)
    def test_status_no_deployer(self):
        from app.phase2_strategy_routes import get_dynamic_risk_status
        result = _run(get_dynamic_risk_status(actor=_FakeActor()))
        assert result["data"]["available"] is False

    @patch(f"{_MOD_READ}.AUTO_DEPLOYER")
    def test_status_happy(self, mock_ad):
        from app.phase2_strategy_routes import get_dynamic_risk_status
        mock_ad.get_dynamic_risk_status.return_value = {"enabled": True}
        result = _run(get_dynamic_risk_status(actor=_FakeActor()))
        assert result["data"]["enabled"] is True


class TestValidTimeframes:
    def test_known_timeframes(self):
        for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]:
            assert tf in _VALID_TIMEFRAMES

    def test_unknown_timeframe(self):
        assert "2h" not in _VALID_TIMEFRAMES
