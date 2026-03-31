from __future__ import annotations

"""
啟動完整性驗證測試 / Startup integrity check tests

驗證 main.py 的 _startup_integrity_check 事件處理器在：
  1. 所有硬性依賴均已注入時 — 正常啟動（不 raise）
  2. 缺少 governance_hub (GOV_HUB) 時 — RuntimeError 含 "governance_hub"
  3. 缺少 paper_engine (ENGINE) 時 — RuntimeError 含 "paper_engine"
  4. 缺少 risk_manager (RISK_MANAGER) 時 — RuntimeError 含 "risk_manager"
  5. PIPELINE_BRIDGE = None 時 — 警告但正常啟動（降級模式允許）
  6. H0_GATE = None 時 — 警告但正常啟動（降級模式允許）

Validates that main.py's _startup_integrity_check event handler:
  1. Passes when all hard-required deps are injected
  2. Raises RuntimeError mentioning "governance_hub" when GOV_HUB is None
  3. Raises RuntimeError mentioning "paper_engine" when ENGINE is None
  4. Raises RuntimeError mentioning "risk_manager" when RISK_MANAGER is None
  5. Starts with only a warning when PIPELINE_BRIDGE is None (degraded mode)
  6. Starts with only a warning when H0_GATE is None (degraded mode)
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helper: directly invoke the startup coroutine with controlled dep values
# 直接調用 startup 協程，透過 mock 控制依賴注入值
# ---------------------------------------------------------------------------

def _run_startup(*, gov_hub, engine, risk_manager, pipeline_bridge, h0_gate):
    """Patch the module-level names imported inside _startup_integrity_check and run it.
    在 _startup_integrity_check 內部 import 目標進行 patch，然後執行協程。
    """
    # _startup_integrity_check imports from paper_trading_routes and phase2_strategy_routes
    # at call time; we patch the source modules' attributes so the locals are controlled.
    # startup 事件在調用時才 import 依賴模塊的屬性，直接 patch 源模塊屬性即可控制值。
    with (
        patch("app.paper_trading_routes.GOV_HUB", gov_hub),
        patch("app.paper_trading_routes.ENGINE", engine),
        patch("app.paper_trading_routes.RISK_MANAGER", risk_manager),
        patch("app.paper_trading_routes.H0_GATE", h0_gate),
        patch("app.phase2_strategy_routes.PIPELINE_BRIDGE", pipeline_bridge),
    ):
        # Import here so the patches above are already in place when the
        # function is fetched.  Re-import each call to pick up the patches.
        # 在 patch 生效後才 import，確保取到 patched 的屬性值。
        import importlib
        main_mod = importlib.import_module("app.main")
        coro = main_mod._startup_integrity_check()
        # asyncio.run() is the correct API for Python 3.10+
        # asyncio.run() 是 Python 3.10+ 的正確呼叫方式（get_event_loop 已棄用）
        return asyncio.run(coro)


def _make_stub() -> MagicMock:
    """Return a non-None stub object representing an injected dependency.
    返回代表已注入依賴的非 None stub 對象。
    """
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests / 測試用例
# ---------------------------------------------------------------------------

class TestStartupIntegrityCheck:
    """
    Startup integrity check unit tests.
    啟動完整性驗證單元測試。
    """

    def test_all_hard_deps_present_startup_passes(self):
        """All hard-required deps injected — startup must not raise.
        所有硬性依賴均已注入 — 啟動不應 raise。
        """
        # Should complete without raising
        _run_startup(
            gov_hub=_make_stub(),
            engine=_make_stub(),
            risk_manager=_make_stub(),
            pipeline_bridge=_make_stub(),
            h0_gate=_make_stub(),
        )

    def test_missing_governance_hub_raises_runtime_error(self):
        """GOV_HUB = None → RuntimeError must mention 'governance_hub'.
        GOV_HUB 為 None → RuntimeError 必須包含 'governance_hub'。
        """
        with pytest.raises(RuntimeError) as exc_info:
            _run_startup(
                gov_hub=None,
                engine=_make_stub(),
                risk_manager=_make_stub(),
                pipeline_bridge=_make_stub(),
                h0_gate=_make_stub(),
            )
        assert "governance_hub" in str(exc_info.value)

    def test_missing_paper_engine_raises_runtime_error(self):
        """ENGINE = None → RuntimeError must mention 'paper_engine'.
        ENGINE 為 None → RuntimeError 必須包含 'paper_engine'。
        """
        with pytest.raises(RuntimeError) as exc_info:
            _run_startup(
                gov_hub=_make_stub(),
                engine=None,
                risk_manager=_make_stub(),
                pipeline_bridge=_make_stub(),
                h0_gate=_make_stub(),
            )
        assert "paper_engine" in str(exc_info.value)

    def test_missing_risk_manager_raises_runtime_error(self):
        """RISK_MANAGER = None → RuntimeError must mention 'risk_manager'.
        RISK_MANAGER 為 None → RuntimeError 必須包含 'risk_manager'。
        """
        with pytest.raises(RuntimeError) as exc_info:
            _run_startup(
                gov_hub=_make_stub(),
                engine=_make_stub(),
                risk_manager=None,
                pipeline_bridge=_make_stub(),
                h0_gate=_make_stub(),
            )
        assert "risk_manager" in str(exc_info.value)

    def test_pipeline_bridge_none_startup_passes_with_warning(self, caplog):
        """PIPELINE_BRIDGE = None → degraded mode; startup passes, warning logged.
        PIPELINE_BRIDGE 為 None → 降級模式；啟動成功，記錄警告。
        """
        import logging
        with caplog.at_level(logging.WARNING):
            _run_startup(
                gov_hub=_make_stub(),
                engine=_make_stub(),
                risk_manager=_make_stub(),
                pipeline_bridge=None,
                h0_gate=_make_stub(),
            )
        assert any("pipeline_bridge" in r.message.lower() or "PIPELINE_BRIDGE" in r.message for r in caplog.records)

    def test_h0_gate_none_startup_passes_with_warning(self, caplog):
        """H0_GATE = None → degraded mode; startup passes, warning logged.
        H0_GATE 為 None → 降級模式；啟動成功，記錄警告。
        """
        import logging
        with caplog.at_level(logging.WARNING):
            _run_startup(
                gov_hub=_make_stub(),
                engine=_make_stub(),
                risk_manager=_make_stub(),
                pipeline_bridge=_make_stub(),
                h0_gate=None,
            )
        assert any("h0_gate" in r.message.lower() or "H0_GATE" in r.message for r in caplog.records)
