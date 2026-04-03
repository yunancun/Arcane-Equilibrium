from __future__ import annotations

"""
test_paper_trading_engine_inverse.py — Inverse (coin-margined) contract end-to-end tests
幣本位合約端到端測試

MODULE_NOTE (中文):
  本測試文件涵蓋 Wave 7b Inverse 品類支援的四個核心修復：
    INV-1: _compute_close_pnl() 幣本位 PnL 公式正確性（數值驗證 + 邊界保護）
    INV-1: update_unrealized_pnl() 幣本位未實現盈虧公式正確性
    INV-3: round_qty_for_exchange() inverse 合約整數張數取整
    INV-4: RiskManager 自動注入 inverse 品類配置（max_leverage=50.0）
    INV-2: MarketScanner inverse 品類過濾邏輯（USD 後綴 + volume 跳過）

  所有測試均不依賴真實網絡或 DB，使用純函數或 mock 隔離測試。

MODULE_NOTE (English):
  Test coverage for Wave 7b Inverse category support across four critical fixes:
    INV-1: _compute_close_pnl() coin-margined PnL formula correctness (numerical + guard)
    INV-1: update_unrealized_pnl() coin-margined unrealized PnL formula correctness
    INV-3: round_qty_for_exchange() inverse contracts round to integer contracts
    INV-4: RiskManager auto-injects inverse category config (max_leverage=50.0)
    INV-2: MarketScanner inverse category filter logic (USD suffix + volume bypass)

  All tests are network/DB-free; pure-function or mock-isolated.

Safety invariant:
  - 無真實 Bybit API 調用 / No real Bybit API calls.
  - 不修改任何全局狀態 / No global state mutation.
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# sys.path setup — control_api_v1 project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# local_model_tools path (for MarketScanner)
# ---------------------------------------------------------------------------
LOCAL_MODEL_TOOLS_ROOT = Path(__file__).resolve().parents[4] / "local_model_tools"
if str(LOCAL_MODEL_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(LOCAL_MODEL_TOOLS_ROOT.parent))


# =============================================================================
# Helpers / 測試輔助函數
# =============================================================================

def _make_pos(
    side: str,
    avg_entry_price: float,
    qty: float,
    category: str = "inverse",
) -> dict:
    """
    Build a minimal position dict for PnL function testing.
    構造最小化持倉字典，用於 PnL 函數測試。
    """
    return {
        "side": side,
        "avg_entry_price": avg_entry_price,
        "qty": qty,
        "category": category,
    }


def _make_inverse_ticker(
    symbol: str = "BTCUSD",
    last_price: float = 50000.0,
    turnover_24h: float = 500.0,   # In BTC, not USDT — intentionally small
    price_24h_pct: float = 0.02,
    high_24h: float = 51000.0,
    low_24h: float = 49000.0,
    funding_rate: float = 0.0001,
) -> dict:
    """
    Build a mock inverse (coin-margined) ticker payload matching Bybit V5 API format.
    構造 Bybit V5 API 格式的 inverse ticker mock 數據。
    Note: turnover24h is in base currency (BTC), NOT USDT.
    注意：turnover24h 以基礎幣（BTC）計，而非 USDT。
    """
    return {
        "symbol": symbol,
        "lastPrice": str(last_price),
        "turnover24h": str(turnover_24h),
        "price24hPcnt": str(price_24h_pct),
        "highPrice24h": str(high_24h),
        "lowPrice24h": str(low_24h),
        "fundingRate": str(funding_rate),
    }


def _mock_urlopen_side_effect(data: dict):
    """
    Return a side_effect function for urllib.request.urlopen that yields a context-manager mock.
    返回 urllib.request.urlopen 的 side_effect 函數，模擬 context manager。

    Uses side_effect (not return_value) so that __enter__/__exit__ work correctly
    regardless of how MagicMock handles dunder methods.
    使用 side_effect 而非 return_value，確保 dunder method 行為一致。
    """
    response_body = json.dumps(data).encode()

    def _side_effect(req, timeout=10):
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read.return_value = response_body
        return cm

    return _side_effect


# Keep a convenience alias used in some tests
def _mock_urlopen_response(data: dict):
    """
    Legacy helper: returns a single context-manager mock suitable for return_value patching.
    向後兼容輔助函數：返回一個 context manager mock，用於 return_value 設置。
    Note: Prefer _mock_urlopen_side_effect for side_effect-based patching.
    """
    response_body = json.dumps(data).encode()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__ = MagicMock(return_value=False)
    cm.read.return_value = response_body
    return cm


# =============================================================================
# Class 1: TestInverseClosePnL — INV-1 PnL 公式數值驗證
# =============================================================================

class TestInverseClosePnL:
    """
    Numerical and guard tests for _compute_close_pnl() with inverse positions.
    幣本位 _compute_close_pnl() 函數的數值驗證與邊界保護測試。

    Formula verified:
      Long  PnL = qty * (1/entry - 1/close)
      Short PnL = qty * (1/close - 1/entry)
    """

    def test_inverse_long_close_pnl_numerical(self):
        """
        INV-1 numerical: long qty=100, entry=50000, close=55000
        → pnl = 100 * (1/50000 - 1/55000) ≈ 0.0001818... BTC
        幣本位多頭平倉 PnL 數值驗證。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=100.0)
        expected = 100.0 * (1.0 / 50000.0 - 1.0 / 55000.0)
        result = _compute_close_pnl(pos, close_qty=100.0, close_price=55000.0)
        assert abs(result - expected) < 1e-9, (
            f"Long PnL mismatch: got {result}, expected {expected}"
        )

    def test_inverse_short_close_pnl_numerical(self):
        """
        INV-1 numerical: short qty=100, entry=50000, close=45000
        → pnl = 100 * (1/45000 - 1/50000) ≈ 0.0002222... BTC
        幣本位空頭平倉 PnL 數值驗證。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_SELL
        pos = _make_pos(side=SIDE_SELL, avg_entry_price=50000.0, qty=100.0)
        expected = 100.0 * (1.0 / 45000.0 - 1.0 / 50000.0)
        result = _compute_close_pnl(pos, close_qty=100.0, close_price=45000.0)
        assert abs(result - expected) < 1e-9, (
            f"Short PnL mismatch: got {result}, expected {expected}"
        )

    def test_inverse_long_close_pnl_positive_when_price_rises(self):
        """
        Inverse long: closing at higher price → positive PnL (profit).
        幣本位多頭：收益應為正（價格上漲時平倉）。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=40000.0, qty=200.0)
        result = _compute_close_pnl(pos, close_qty=200.0, close_price=44000.0)
        assert result > 0.0, f"Expected positive PnL for long, got {result}"

    def test_inverse_short_close_pnl_positive_when_price_falls(self):
        """
        Inverse short: closing at lower price → positive PnL (profit).
        幣本位空頭：收益應為正（價格下跌時平倉）。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_SELL
        pos = _make_pos(side=SIDE_SELL, avg_entry_price=40000.0, qty=200.0)
        result = _compute_close_pnl(pos, close_qty=200.0, close_price=36000.0)
        assert result > 0.0, f"Expected positive PnL for short, got {result}"

    def test_inverse_close_pnl_zero_entry_guard(self):
        """
        INV-1 guard: entry=0 → pnl=0.0 (no ZeroDivisionError).
        除零保護：entry 為 0 時返回 0.0，不拋 ZeroDivisionError。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=0.0, qty=100.0)
        result = _compute_close_pnl(pos, close_qty=100.0, close_price=55000.0)
        assert result == 0.0, f"Expected 0.0 for zero entry, got {result}"

    def test_inverse_close_pnl_zero_close_guard(self):
        """
        INV-1 guard: close_price=0 → pnl=0.0 (no ZeroDivisionError).
        除零保護：close_price 為 0 時返回 0.0，不拋 ZeroDivisionError。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=100.0)
        result = _compute_close_pnl(pos, close_qty=100.0, close_price=0.0)
        assert result == 0.0, f"Expected 0.0 for zero close_price, got {result}"

    def test_inverse_close_pnl_negative_entry_guard(self):
        """
        INV-1 guard: entry<0 → pnl=0.0 (no ZeroDivisionError).
        除零保護：entry 為負時返回 0.0，防止非法輸入。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=-1.0, qty=100.0)
        result = _compute_close_pnl(pos, close_qty=100.0, close_price=50000.0)
        assert result == 0.0, f"Expected 0.0 for negative entry, got {result}"

    def test_inverse_linear_unaffected(self):
        """
        Regression: linear PnL formula uses (close-entry)*qty — unaffected by inverse changes.
        回歸測試：linear 合約 PnL 公式未受影響，仍為 (close-entry)*qty。
        """
        from app.paper_trading_engine import _compute_close_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=0.1, category="linear")
        result = _compute_close_pnl(pos, close_qty=0.1, close_price=55000.0)
        expected = (55000.0 - 50000.0) * 0.1  # = 500.0 USDT
        assert abs(result - expected) < 1e-9, (
            f"Linear PnL mismatch: got {result}, expected {expected}"
        )


# =============================================================================
# Class 2: TestInverseUnrealizedPnL — INV-1 未實現盈虧公式
# =============================================================================

class TestInverseUnrealizedPnL:
    """
    Tests for update_unrealized_pnl() with inverse category positions.
    幣本位持倉 update_unrealized_pnl() 函數測試。
    """

    def test_inverse_long_unrealized_pnl_positive(self):
        """
        Long inverse position: mark price above entry → positive unrealized PnL.
        幣本位多頭：mark_price 高於 entry → unrealized_pnl > 0。
        qty=100, entry=50000, mark=52000 → unrealized > 0
        """
        from app.paper_trading_engine import update_unrealized_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=100.0)
        positions = {"BTCUSD": pos}
        result = update_unrealized_pnl(positions, {"BTCUSD": 52000.0})
        assert result["BTCUSD"]["unrealized_pnl"] > 0.0, (
            f"Expected positive unrealized PnL for long, got {result['BTCUSD']['unrealized_pnl']}"
        )

    def test_inverse_short_unrealized_pnl_positive(self):
        """
        Short inverse position: mark price below entry → positive unrealized PnL.
        幣本位空頭：mark_price 低於 entry → unrealized_pnl > 0。
        qty=100, entry=50000, mark=48000 → unrealized > 0
        """
        from app.paper_trading_engine import update_unrealized_pnl, SIDE_SELL
        pos = _make_pos(side=SIDE_SELL, avg_entry_price=50000.0, qty=100.0)
        positions = {"BTCUSD": pos}
        result = update_unrealized_pnl(positions, {"BTCUSD": 48000.0})
        assert result["BTCUSD"]["unrealized_pnl"] > 0.0, (
            f"Expected positive unrealized PnL for short, got {result['BTCUSD']['unrealized_pnl']}"
        )

    def test_inverse_unrealized_zero_entry_guard(self):
        """
        INV-1 guard: entry=0 → unrealized_pnl=0.0 (no ZeroDivisionError).
        除零保護：entry 為 0 時未實現 PnL 設為 0.0，不拋異常。
        """
        from app.paper_trading_engine import update_unrealized_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=0.0, qty=100.0)
        positions = {"BTCUSD": pos}
        result = update_unrealized_pnl(positions, {"BTCUSD": 50000.0})
        assert result["BTCUSD"]["unrealized_pnl"] == 0.0, (
            f"Expected 0.0 for zero entry, got {result['BTCUSD']['unrealized_pnl']}"
        )

    def test_inverse_unrealized_zero_mark_guard(self):
        """
        INV-1 guard: mark_price=0 → unrealized_pnl=0.0 (no ZeroDivisionError).
        除零保護：mark_price 為 0 時未實現 PnL 設為 0.0。
        """
        from app.paper_trading_engine import update_unrealized_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=100.0)
        positions = {"BTCUSD": pos}
        result = update_unrealized_pnl(positions, {"BTCUSD": 0.0})
        assert result["BTCUSD"]["unrealized_pnl"] == 0.0, (
            f"Expected 0.0 for zero mark price, got {result['BTCUSD']['unrealized_pnl']}"
        )

    def test_inverse_unrealized_numerical_long(self):
        """
        Numerical validation: long qty=100, entry=50000, mark=52000
        → expected = 100 * (1/50000 - 1/52000)
        數值精度驗證：幣本位多頭未實現 PnL 公式。
        """
        from app.paper_trading_engine import update_unrealized_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=100.0)
        positions = {"BTCUSD": pos}
        result = update_unrealized_pnl(positions, {"BTCUSD": 52000.0})
        expected = 100.0 * (1.0 / 50000.0 - 1.0 / 52000.0)
        assert abs(result["BTCUSD"]["unrealized_pnl"] - expected) < 1e-9, (
            f"Unrealized PnL mismatch: got {result['BTCUSD']['unrealized_pnl']}, expected {expected}"
        )

    def test_inverse_unrealized_symbol_not_in_prices_skipped(self):
        """
        Symbol missing from market_prices dict → position unrealized_pnl untouched.
        市場價格字典中無該 symbol → 持倉未實現 PnL 不更新。
        """
        from app.paper_trading_engine import update_unrealized_pnl, SIDE_BUY
        pos = _make_pos(side=SIDE_BUY, avg_entry_price=50000.0, qty=100.0)
        pos["unrealized_pnl"] = 42.0  # sentinel value
        positions = {"BTCUSD": pos}
        result = update_unrealized_pnl(positions, {})  # empty market prices
        assert result["BTCUSD"]["unrealized_pnl"] == 42.0, (
            "unrealized_pnl should not be updated when symbol absent from market prices"
        )


# =============================================================================
# Class 3: TestInverseRoundQty — INV-3 整數張數取整
# =============================================================================

class TestInverseRoundQty:
    """
    Tests for round_qty_for_exchange() with inverse category.
    幣本位合約 round_qty_for_exchange() 整數取整測試。

    Inverse contracts use integer contract size (e.g. BTCUSD step=1).
    INV-3：Inverse 合約使用整數張數（如 BTCUSD 最小 1 張），強制取整。
    """

    def test_inverse_round_qty_integer_from_float(self):
        """
        INV-3: inverse qty=99.9999999 → rounds to 100.0 (integer).
        Inverse 合約：99.9999999 應取整為 100.0。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(99.9999999, "inverse")
        assert result == 100.0, f"Expected 100.0, got {result}"

    def test_inverse_round_qty_already_integer(self):
        """
        INV-3: inverse qty=100.0 (already integer) → 100.0.
        Inverse 合約：已經是整數 100.0 → 保持 100.0。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(100.0, "inverse")
        assert result == 100.0, f"Expected 100.0, got {result}"

    def test_inverse_round_qty_rounds_down(self):
        """
        INV-3: inverse qty=100.4 → rounds to 100.0 (nearest integer).
        Inverse 合約：100.4 取整為 100.0。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(100.4, "inverse")
        assert result == 100.0, f"Expected 100.0, got {result}"

    def test_inverse_round_qty_rounds_up(self):
        """
        INV-3: inverse qty=100.6 → rounds to 101.0 (nearest integer).
        Inverse 合約：100.6 取整為 101.0。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(100.6, "inverse")
        assert result == 101.0, f"Expected 101.0, got {result}"

    def test_linear_round_qty_small_unaffected(self):
        """
        Regression: linear qty=0.001 (small BTC) → 0.001 (3dp, not rounded to int).
        回歸測試：linear 合約 qty=0.001 不受 inverse 取整影響，保留 3 位小數。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(0.001, "linear")
        assert result == 0.001, f"Expected 0.001, got {result}"

    def test_linear_round_qty_ge_one_rounds_to_int(self):
        """
        Linear qty>=1 heuristic: qty=1.0056 → 1.0 (integer, because qty>=1).
        Linear 合約 qty>=1 時啟發式取整：1.0056 → 1.0。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(1.0056, "linear")
        assert result == 1.0, f"Expected 1.0, got {result}"

    def test_round_qty_default_category_linear(self):
        """
        Default category (no arg) behaves like linear.
        預設不傳 category 時行為與 linear 相同（向後兼容）。
        """
        from app.bybit_demo_connector import round_qty_for_exchange
        result = round_qty_for_exchange(0.005)
        assert result == 0.005, f"Expected 0.005, got {result}"


# =============================================================================
# Class 4: TestInverseRiskConfig — INV-4 風控配置自動注入
# =============================================================================

class TestInverseRiskConfig:
    """
    Tests for RiskManager auto-injecting inverse category config (INV-4).
    RiskManager 自動注入 inverse 品類配置測試（INV-4）。

    When no inverse config is provided, RiskManager must auto-inject
    CategoryRiskConfig(category="inverse", max_leverage=50.0).
    未提供 inverse 配置時，RiskManager 應自動注入 max_leverage=50.0 的配置。
    """

    def test_inverse_category_config_auto_injected(self):
        """
        INV-4: RiskManager() with no args → inverse config auto-injected with max_leverage=50.0.
        未提供配置時，inverse 品類配置應自動注入，max_leverage=50.0。
        """
        from app.risk_manager import RiskManager
        rm = RiskManager()
        inverse_cfg = rm._category_configs.get("inverse")
        assert inverse_cfg is not None, "inverse category config should be auto-injected"
        assert inverse_cfg.max_leverage == 50.0, (
            f"Expected max_leverage=50.0 for inverse, got {inverse_cfg.max_leverage}"
        )

    def test_inverse_config_not_overwritten_by_auto_inject_when_no_operator_file(self):
        """
        INV-4: When no operator JSON file exists, the auto-inject code-default must NOT
        overwrite a user-supplied inverse config.
        不存在 Operator JSON 配置文件時，自動注入的代碼默認值不應覆蓋調用者提供的 inverse 配置。

        NOTE: If an operator config JSON file exists and has "inverse" config,
        _load_operator_config() will overwrite the caller-provided config. That is
        the intended behavior (operator JSON is authoritative).
        注意：若 Operator JSON 文件存在且包含 inverse 配置，_load_operator_config() 會覆蓋
        調用者提供的配置，這是設計預期（Operator JSON 配置具有最高權威性）。
        """
        import app.risk_manager as rm_mod
        from app.risk_manager import RiskManager, CategoryRiskConfig
        custom_cfg = CategoryRiskConfig(category="inverse", max_leverage=25.0)
        # Bypass operator config file to test the auto-inject guard in isolation
        with patch.object(rm_mod, "_OPERATOR_CONFIG_PATH", "/dev/null"):
            rm = RiskManager(category_configs={"inverse": custom_cfg})
        inverse_cfg = rm._category_configs.get("inverse")
        assert inverse_cfg is not None
        assert inverse_cfg.max_leverage == 25.0, (
            f"Auto-inject should NOT overwrite caller-provided config, got {inverse_cfg.max_leverage}"
        )

    def test_spot_config_still_injected_as_regression(self):
        """
        Regression (SPOT-3): spot config is still auto-injected alongside inverse.
        回歸測試（SPOT-3）：spot 配置仍然自動注入，與 inverse 注入邏輯共存。
        """
        from app.risk_manager import RiskManager
        rm = RiskManager()
        spot_cfg = rm._category_configs.get("spot")
        assert spot_cfg is not None, "spot category config should still be auto-injected (SPOT-3 regression)"
        assert spot_cfg.max_leverage == 1.0, (
            f"Expected spot max_leverage=1.0, got {spot_cfg.max_leverage}"
        )

    def test_inverse_category_in_allowed_list(self):
        """
        INV-4: "inverse" must be in RiskManager code-default allowed_categories list.
        代碼默認 allowed_categories 必須包含 "inverse"，否則 inverse 訂單無法通過風控。

        Patches the module-level _OPERATOR_CONFIG_PATH to "/dev/null" so that
        no operator config file is loaded, exposing the pure code defaults.
        通過 patch 模塊級別的配置路徑為 "/dev/null"，隔離 Operator 配置文件影響。
        """
        import app.risk_manager as rm_mod
        from app.risk_manager import RiskManager
        with patch.object(rm_mod, "_OPERATOR_CONFIG_PATH", "/dev/null"):
            rm = RiskManager()
        allowed = rm._config.allowed_categories
        assert "inverse" in allowed, (
            f"'inverse' should be in default allowed_categories, got {allowed}"
        )

    def test_get_category_config_inverse_returns_config(self):
        """
        INV-4: rm.get_category_config("inverse") returns a CategoryRiskConfig object.
        get_category_config("inverse") 應返回 CategoryRiskConfig 對象，不為 None。
        """
        from app.risk_manager import RiskManager, CategoryRiskConfig
        rm = RiskManager()
        cfg = rm.get_category_config("inverse")
        assert cfg is not None, "get_category_config('inverse') should not return None"
        assert isinstance(cfg, CategoryRiskConfig)

    def test_inverse_effective_max_leverage(self):
        """
        INV-4: effective_max_leverage("inverse") uses resolve_effective_limit = min(category, global).
        effective_max_leverage("inverse") 使用 resolve_effective_limit = min(category, global)。

        inverse CategoryRiskConfig.max_leverage = 50.0 (allows up to 50x)
        GlobalRiskConfig.max_leverage = 50.0 (operator config loaded at runtime)
        → effective = min(50.0, 50.0) = 50.0

        Note: env var OPENCLAW_RISK_CONFIG_PATH is evaluated at module import time,
        so setting it in the test body does not prevent loading the operator config.
        The actual loaded global max_leverage is 50.0 from operator_risk_config.json.
        注意：OPENCLAW_RISK_CONFIG_PATH 在模組匯入時已求值，測試中設定不影響載入。
        實際載入的全局 max_leverage 為 operator_risk_config.json 中的 50.0。
        """
        from app.risk_manager import RiskManager
        import os
        old_path = os.environ.get("OPENCLAW_RISK_CONFIG_PATH")
        try:
            os.environ["OPENCLAW_RISK_CONFIG_PATH"] = "/dev/null"
            rm = RiskManager()
            # inverse category config max_leverage = 50.0
            assert rm._category_configs["inverse"].max_leverage == 50.0
            # Global max_leverage = 50.0 (from operator_risk_config.json)
            assert rm._config.max_leverage == 50.0
            # Effective = min(50.0, 50.0) = 50.0 — both agree
            lev = rm.effective_max_leverage("inverse")
            assert lev == 50.0, (
                f"Expected effective_max_leverage('inverse')=min(50.0,50.0)=50.0, got {lev}"
            )
        finally:
            if old_path is None:
                os.environ.pop("OPENCLAW_RISK_CONFIG_PATH", None)
            else:
                os.environ["OPENCLAW_RISK_CONFIG_PATH"] = old_path


# =============================================================================
# Class 5: TestInverseMarketScanner — INV-2 掃描器品類過濾
# =============================================================================

class TestInverseMarketScanner:
    """
    Tests for MarketScanner inverse category filter behavior (INV-2).
    MarketScanner inverse 品類過濾邏輯測試（INV-2）。

    Key invariants:
      - Inverse tickers with "USD" suffix pass symbol filter
      - Inverse volume filter is bypassed (turnover24h is in BTC, not USDT)
      - Non-"USD"-suffix inverse symbols are rejected
      - Linear BTCUSDT scan unaffected (regression)
    主要不變量：
      - USD 後綴的 inverse ticker 通過符號過濾
      - Inverse volume 過濾跳過（turnover24h 以 BTC 計）
      - 非 USD 後綴的 inverse ticker 被過濾
      - Linear BTCUSDT 仍然正常通過（回歸）
    """

    def _make_api_response(self, tickers: list[dict]) -> dict:
        return {"retCode": 0, "result": {"list": tickers}}

    def test_inverse_btcusd_passes_filter(self):
        """
        INV-2: BTCUSD (inverse, USD suffix) passes symbol filter → included in opportunities.
        BTCUSD inverse 合約通過符號過濾，出現在掃描結果中。
        """
        from local_model_tools.market_scanner import MarketScanner
        scanner = MarketScanner(categories=["inverse"])
        ticker = _make_inverse_ticker(symbol="BTCUSD", last_price=50000.0)
        resp = self._make_api_response([ticker])

        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_side_effect(resp)):
            opps = scanner.scan()

        symbols = [o.symbol for o in opps]
        assert "BTCUSD" in symbols, (
            f"BTCUSD should appear in opportunities, got symbols: {symbols}"
        )

    def test_inverse_volume_filter_bypassed(self):
        """
        INV-2: Inverse contracts bypass min_volume check (turnover24h in BTC, not USDT).
        Inverse 合約跳過最低交易量過濾，防止以 BTC 計的 turnover 誤判低流動性。
        Even with turnover24h=1.0 (1 BTC), inverse symbol should pass.
        """
        from local_model_tools.market_scanner import MarketScanner
        scanner = MarketScanner(categories=["inverse"], min_volume=1_000_000.0)
        # Deliberately tiny BTC volume — would fail USDT threshold.
        # Must supply ETHUSD-appropriate high/low to get volatility_pct in grid range (2-10%).
        # 必須提供 ETHUSD 對應的 high/low，使 volatility_pct 落在 grid 範圍（2-10%）。
        ticker = _make_inverse_ticker(
            symbol="ETHUSD",
            last_price=3000.0,
            turnover_24h=1.0,
            high_24h=3100.0,    # vol = (3100-2900)/3000*100 = 6.7% → grid eligible
            low_24h=2900.0,
        )
        resp = self._make_api_response([ticker])

        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_side_effect(resp)):
            opps = scanner.scan()

        symbols = [o.symbol for o in opps]
        assert "ETHUSD" in symbols, (
            f"ETHUSD should bypass volume filter for inverse, got symbols: {symbols}"
        )

    def test_linear_btcusdt_still_passes(self):
        """
        Regression: linear BTCUSDT scan unaffected by inverse filter changes.
        回歸測試：linear BTCUSDT 掃描不受 inverse 過濾邏輯變更影響。
        """
        from local_model_tools.market_scanner import MarketScanner
        scanner = MarketScanner(categories=["linear"])

        linear_ticker = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000.0",
            "turnover24h": "200000000.0",
            "price24hPcnt": "0.02",
            "highPrice24h": "51000.0",
            "lowPrice24h": "49000.0",
            "fundingRate": "0.0001",
        }
        resp = self._make_api_response([linear_ticker])

        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_side_effect(resp)):
            opps = scanner.scan()

        symbols = [o.symbol for o in opps]
        assert "BTCUSDT" in symbols, (
            f"BTCUSDT linear should still pass, got symbols: {symbols}"
        )

    def test_inverse_non_usd_suffix_filtered(self):
        """
        INV-2: Inverse symbol without "USD" suffix (e.g. "BTCBTC") → filtered out.
        Inverse 合約中非 "USD" 後綴的 symbol（如 "BTCBTC"）應被過濾掉。
        """
        from local_model_tools.market_scanner import MarketScanner
        scanner = MarketScanner(categories=["inverse"])
        # Malformed ticker with non-USD suffix
        bad_ticker = _make_inverse_ticker(symbol="BTCBTC", last_price=50000.0, turnover_24h=1000.0)
        resp = self._make_api_response([bad_ticker])

        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_side_effect(resp)):
            opps = scanner.scan()

        symbols = [o.symbol for o in opps]
        assert "BTCBTC" not in symbols, (
            f"BTCBTC should be filtered (no USD suffix), but appeared in: {symbols}"
        )

    def test_inverse_api_category_propagated(self):
        """
        INV-2: SymbolOpportunity.api_category should be "inverse" for inverse tickers.
        Inverse ticker 的 api_category 字段應正確傳遞為 "inverse"。
        """
        from local_model_tools.market_scanner import MarketScanner
        scanner = MarketScanner(categories=["inverse"])
        ticker = _make_inverse_ticker(symbol="BTCUSD", last_price=50000.0)
        resp = self._make_api_response([ticker])

        with patch("urllib.request.urlopen", side_effect=_mock_urlopen_side_effect(resp)):
            opps = scanner.scan()

        btcusd_opps = [o for o in opps if o.symbol == "BTCUSD"]
        assert len(btcusd_opps) >= 1, "BTCUSD opportunity should be in results"
        assert btcusd_opps[0].api_category == "inverse", (
            f"Expected api_category='inverse', got {btcusd_opps[0].api_category}"
        )
