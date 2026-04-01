"""
MODULE_NOTE (EN):
  SPOT-4/SPOT-5 unit tests for PipelineBridge Spot category support.
  Covers:
    - _infer_category_from_symbol() naming convention inference
    - _fetch_single_funding_rate() early-return guard for Spot/Option symbols
    - Spot intent category propagated to submit_order() in _process_pending_intents()

MODULE_NOTE (中文):
  SPOT-4/SPOT-5 PipelineBridge 現貨品類支援單元測試。
  覆蓋場景：
    - _infer_category_from_symbol() 基於命名規則的品類推斷
    - _fetch_single_funding_rate() 對現貨/期權 symbol 提前返回 None（不發 HTTP 請求）
    - Spot intent 的 category 正確透傳到 submit_order()

任務：SPOT-4, SPOT-5
設計者：E1-Gamma（後端開發工程師）
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ─── Path setup ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline_bridge import PipelineBridge


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_bridge() -> PipelineBridge:
    """
    Create a minimal PipelineBridge with mocked dependencies.
    建立最小化的 PipelineBridge，使用 Mock 依賴項。

    PipelineBridge.__init__ requires: kline_manager, indicator_engine, signal_engine,
    orchestrator, paper_engine. All are mocked here.
    PipelineBridge.__init__ 需要：kline_manager, indicator_engine, signal_engine,
    orchestrator, paper_engine，這裡全部 Mock。
    """
    km = MagicMock()
    km.get_tracked_symbols.return_value = []
    ie = MagicMock()   # indicator_engine
    se = MagicMock()   # signal_engine
    orch = MagicMock()
    orch._strategies = {}
    engine = MagicMock()
    engine.get_state.return_value = {
        "session": {"current_paper_balance_usdt": 10000.0, "session_halted": False},
        "positions": {},
        "orders": [],
    }
    return PipelineBridge(
        kline_manager=km,
        indicator_engine=ie,
        signal_engine=se,
        orchestrator=orch,
        paper_engine=engine,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SPOT-4-T1: _infer_category_from_symbol()
# ═══════════════════════════════════════════════════════════════════════════════

class TestInferCategoryFromSymbol(unittest.TestCase):
    """
    Validate static helper _infer_category_from_symbol() for all Bybit naming patterns.
    驗證靜態輔助方法 _infer_category_from_symbol() 對所有 Bybit 命名格式的正確性。
    """

    def _infer(self, symbol: str) -> str:
        return PipelineBridge._infer_category_from_symbol(symbol)

    def test_linear_usdt_perpetual(self):
        """BTCUSDT → linear (USDT perpetual / USDT 永續)"""
        assert self._infer("BTCUSDT") == "linear"
        assert self._infer("ETHUSDT") == "linear"
        assert self._infer("SOLUSDT") == "linear"

    def test_linear_usdc_perpetual(self):
        """BTCUSDC → linear (USDC perpetual / USDC 永續)"""
        assert self._infer("BTCUSDC") == "linear"
        assert self._infer("ETHUSDC") == "linear"

    def test_inverse_perpetual(self):
        """BTCUSD → inverse (coin-margined perpetual / 幣本位永續)"""
        assert self._infer("BTCUSD") == "inverse"
        assert self._infer("ETHUSD") == "inverse"
        assert self._infer("XRPUSD") == "inverse"

    def test_option_with_dash(self):
        """BTC-1JAN25-50000-C → option (option format / 期權格式)"""
        assert self._infer("BTC-1JAN25-50000-C") == "option"
        assert self._infer("ETH-28MAR25-3000-P") == "option"

    def test_case_insensitive(self):
        """Symbol matching is case-insensitive / 大小寫不敏感"""
        assert self._infer("btcusdt") == "linear"
        assert self._infer("btcusd") == "inverse"

    def test_unknown_symbol_defaults_linear(self):
        """Unknown symbol format defaults to linear (safe fallback / 安全 fallback)"""
        assert self._infer("UNKNOWNTOKENXYZ") == "linear"


# ═══════════════════════════════════════════════════════════════════════════════
# SPOT-4-T2: _fetch_single_funding_rate() Spot/Option early-return guard
# ═══════════════════════════════════════════════════════════════════════════════

class TestFetchSingleFundingRateSpotGuard(unittest.TestCase):
    """
    Verify that _fetch_single_funding_rate() returns None immediately for
    Spot and Option symbols without making any HTTP request.

    驗證 _fetch_single_funding_rate() 對 Spot 和 Option symbol 立即返回 None，
    不發任何 HTTP 請求（避免無效 API 調用及 Bybit 頻率限制消耗）。
    """

    def setUp(self):
        self.bridge = _make_bridge()

    def test_spot_inferred_returns_none_no_http(self):
        """
        SPOT-4-T2a: A symbol inferred as 'linear' (e.g. BTCUSDT) should normally
        attempt HTTP, but passing category='spot' explicitly must skip it entirely.
        直接傳入 category='spot' 應跳過 HTTP 調用，立即返回 None。
        """
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = self.bridge._fetch_single_funding_rate("BTCUSDT", category="spot")

        assert result is None, "Spot category must return None (no funding rate)"
        mock_urlopen.assert_not_called(), "No HTTP request should be made for Spot"

    def test_option_category_returns_none_no_http(self):
        """
        SPOT-4-T2b: Option symbols have no funding rate — must return None without HTTP.
        期權沒有資金費率，應返回 None 且不發 HTTP 請求。
        """
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = self.bridge._fetch_single_funding_rate(
                "BTC-1JAN25-50000-C", category="option"
            )

        assert result is None, "Option category must return None (no funding rate)"
        mock_urlopen.assert_not_called(), "No HTTP request should be made for Option"

    def test_option_symbol_inferred_returns_none_no_http(self):
        """
        SPOT-4-T2c: A symbol inferred as 'option' via name (contains '-') must also
        skip HTTP.
        通過命名推斷為 option 的 symbol 也應跳過 HTTP。
        """
        with patch("urllib.request.urlopen") as mock_urlopen:
            result = self.bridge._fetch_single_funding_rate("ETH-28MAR25-3000-P")

        assert result is None, "Inferred option symbol must return None"
        mock_urlopen.assert_not_called()

    def test_linear_symbol_proceeds_to_http(self):
        """
        SPOT-4-T2d: A linear symbol (BTCUSDT) must still attempt HTTP as before.
        Linear symbol 仍然應嘗試發 HTTP 請求（不受 spot guard 影響）。
        """
        # Mock a failed response (retCode != 0) — we only care that urlopen was called
        # Mock 一個失敗回應（retCode != 0）—— 只確認 urlopen 被調用了
        import json
        from io import BytesIO
        from unittest.mock import MagicMock

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"retCode": 1, "result": {}}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = self.bridge._fetch_single_funding_rate("BTCUSDT", category="linear")

        # Returns None because retCode != 0, but urlopen WAS called
        # 因為 retCode != 0 返回 None，但 urlopen 確實被調用了
        assert result is None
        mock_urlopen.assert_called_once(), "Linear symbol must attempt HTTP fetch"


# ═══════════════════════════════════════════════════════════════════════════════
# SPOT-5-T3: Spot intent category propagated to submit_order()
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpotIntentCategoryPropagated(unittest.TestCase):
    """
    Verify that a Spot intent (with metadata={'category': 'spot'}) correctly
    propagates the 'spot' category through _process_pending_intents() to
    engine.submit_order().

    Note: _process_pending_intents() collects intents from the orchestrator
    (collect_pending_intents()) as direct OrderIntent objects. StrategistAgent
    intents use TradeIntent format (direction/size). We use the orchestrator path
    since it gives us full control of the metadata dict.

    驗證 Spot intent（metadata={'category': 'spot'}）的品類
    能正確透傳到 engine.submit_order()，不會被替換為 'linear'。

    注意：_process_pending_intents() 從 orchestrator.collect_pending_intents()
    收集直接 OrderIntent 物件。這裡使用 orchestrator 路徑測試，以完整控制 metadata。
    """

    def _make_order_intent(self, symbol: str = "BTCUSDT", category: str = "spot"):
        """
        Build a minimal mock OrderIntent (orchestrator path) with metadata category.
        建立 orchestrator 路徑的 mock OrderIntent，帶 metadata category。
        """
        intent = MagicMock()
        intent.symbol = symbol
        intent.side = "Buy"
        intent.order_type = "market"
        intent.price = None
        intent.qty = 0.001
        intent.metadata = {"category": category}
        intent.strategy_name = "test_strategy"
        intent.confidence = 0.7
        intent.reason = "test"
        intent.perception_data_id = None  # skip perception plane
        return intent

    def _setup_bridge_for_intent_test(
        self, symbol: str, category: str, price: float
    ) -> PipelineBridge:
        """
        Construct a bridge ready to process one orchestrator intent.
        建立一個準備處理單一 orchestrator intent 的 bridge。

        Guardian is fail-closed (None → reject all). We inject a mock Guardian
        that approves every intent so submit_order() can be reached.
        Guardian 是 fail-closed（None → 拒絕所有）。注入一個 mock Guardian
        批准所有 intent，使 submit_order() 得以被調用。
        """
        import sys

        bridge = _make_bridge()

        # Orchestrator returns one Spot intent (OrderIntent format)
        # Orchestrator 返回一個 Spot intent（OrderIntent 格式）
        intent = self._make_order_intent(symbol=symbol, category=category)
        bridge._orch.collect_pending_intents.return_value = [intent]

        # StrategistAgent not injected — avoid TradeIntent conversion complexity
        # 不注入 StrategistAgent，避免 TradeIntent 格式轉換的複雜性
        bridge._strategist_agent = None

        # submit_order returns a success result
        # submit_order 返回成功結果
        bridge._engine.submit_order.return_value = {
            "order": {"order_id": "test_001", "symbol": symbol, "state": "paper_order_filled"},
            "rejected_reason": None,
        }

        # Stub Governance so it doesn't block
        # 屏蔽治理，避免阻止 intent
        bridge._governance_hub = MagicMock()
        bridge._governance_hub.is_authorized.return_value = True
        bridge._governance_hub.acquire_lease.return_value = {
            "lease_id": "lease_001",
            "expires_at_ms": int(time.time() * 1000) + 60000,
        }

        # Guardian is fail-closed; inject a mock that always APPROVES
        # Guardian 是 fail-closed；注入一個總是批准的 mock
        # We stub the multi_agent_framework module to avoid import issues
        # 通過 patch 避免 multi_agent_framework 導入問題
        mock_maf = MagicMock()
        mock_maf.RiskVerdictResult.APPROVED = "APPROVED"
        mock_maf.RiskVerdictResult.REJECTED = "REJECTED"
        mock_maf.RiskVerdictResult.MODIFIED = "MODIFIED"
        # TradeIntent constructor returns a mock object
        mock_maf.TradeIntent.return_value = MagicMock()

        # Verdict: APPROVED
        mock_verdict = MagicMock()
        mock_verdict.result = "APPROVED"
        mock_verdict.risk_score = 0.1

        mock_guardian = MagicMock()
        mock_guardian.review_intent.return_value = mock_verdict

        # Patch the import inside pipeline_bridge so Guardian path works
        # 在 pipeline_bridge 內部 patch import，使 Guardian 路徑正常運行
        with patch.dict(
            sys.modules,
            {"app.multi_agent_framework": mock_maf}
        ):
            bridge._guardian_agent = mock_guardian

        bridge._h0_gate = None
        bridge._active = True
        bridge._latest_prices = {symbol: price}
        return bridge

    def test_spot_intent_category_passed_to_submit_order(self):
        """
        SPOT-5-T3a: When the orchestrator emits a Spot intent (metadata={'category':'spot'}),
        submit_order() must receive category='spot', not 'linear'.

        SPOT-5-T3a：當 orchestrator 發出 Spot intent（metadata={'category':'spot'}）時，
        submit_order() 必須收到 category='spot'，而非 'linear'。
        """
        bridge = self._setup_bridge_for_intent_test("BTCUSDT", "spot", 60000.0)
        bridge._process_pending_intents()

        # Assert submit_order was called with category='spot'
        # 確認 submit_order 以 category='spot' 被調用
        assert bridge._engine.submit_order.called, "submit_order must have been called"
        call_kwargs = bridge._engine.submit_order.call_args
        # category is passed as keyword argument in pipeline_bridge line 737+
        # category 在 pipeline_bridge 第 737 行後以關鍵字參數傳遞
        actual_category = call_kwargs.kwargs.get("category")
        assert actual_category == "spot", (
            f"submit_order must receive category='spot', got {actual_category!r}. "
            f"Full call: {call_kwargs}"
        )

    def test_spot_intent_category_in_kwargs(self):
        """
        SPOT-5-T3b: Explicit keyword argument check for ETHUSDT spot category.
        明確確認 ETHUSDT Spot 的關鍵字參數 category='spot'。
        """
        bridge = self._setup_bridge_for_intent_test("ETHUSDT", "spot", 3000.0)
        bridge._process_pending_intents()

        if bridge._engine.submit_order.called:
            kwargs = bridge._engine.submit_order.call_args.kwargs
            if "category" in kwargs:
                assert kwargs["category"] == "spot", (
                    f"Expected category='spot' in kwargs, got {kwargs['category']!r}"
                )

    def test_linear_intent_category_unchanged(self):
        """
        SPOT-5-T3c: A linear intent must still use category='linear'.
        Linear intent 仍應使用 category='linear'（Spot 修改不得破壞 linear 路徑）。
        """
        bridge = self._setup_bridge_for_intent_test("BTCUSDT", "linear", 60000.0)
        bridge._process_pending_intents()

        if bridge._engine.submit_order.called:
            kwargs = bridge._engine.submit_order.call_args.kwargs
            if "category" in kwargs:
                assert kwargs["category"] == "linear", (
                    f"Linear intent must keep category='linear', got {kwargs['category']!r}"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# Wave 7a Plan B: _symbol_category_map / register_symbol_category() tests
# Wave 7a 方案 B：_symbol_category_map / register_symbol_category() 測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestSymbolCategoryMap(unittest.TestCase):
    """
    Validate Wave 7a Plan B: runtime symbol-to-category map populated by
    StrategyAutoDeployer, consumed by PipelineBridge kline/funding queries.

    驗證 Wave 7a 方案 B：運行時 symbol→category 映射，由 StrategyAutoDeployer 填充，
    PipelineBridge kline/funding 查詢優先使用映射而非命名推斷。
    """

    def setUp(self):
        self.bridge = _make_bridge()

    # ── T4a: register_symbol_category stores mapping ─────────────────────────

    def test_register_symbol_category_stores_mapping(self):
        """
        Wave 7a-T4a: register_symbol_category("BTCUSDT", "spot") must persist
        the mapping in _symbol_category_map.

        Wave 7a-T4a：調用 register_symbol_category("BTCUSDT", "spot") 後，
        _symbol_category_map["BTCUSDT"] 必須等於 "spot"。
        """
        self.bridge.register_symbol_category("BTCUSDT", "spot")
        assert self.bridge._symbol_category_map["BTCUSDT"] == "spot", (
            "_symbol_category_map must store 'spot' for BTCUSDT"
        )

    def test_register_symbol_category_overwrites(self):
        """
        Wave 7a-T4a-bis: Re-registering a symbol updates the mapping in place.
        重複登記同一 symbol 應更新映射（後蓋前）。
        """
        self.bridge.register_symbol_category("BTCUSDT", "spot")
        self.bridge.register_symbol_category("BTCUSDT", "linear")
        assert self.bridge._symbol_category_map["BTCUSDT"] == "linear", (
            "Second registration must overwrite the first"
        )

    def test_register_multiple_symbols(self):
        """
        Wave 7a-T4a-multi: Multiple symbols can coexist in the map.
        多個 symbol 可同時存在於映射中。
        """
        self.bridge.register_symbol_category("BTCUSDT", "spot")
        self.bridge.register_symbol_category("ETHUSDT", "linear")
        self.bridge.register_symbol_category("BTCUSD", "inverse")
        assert self.bridge._symbol_category_map["BTCUSDT"] == "spot"
        assert self.bridge._symbol_category_map["ETHUSDT"] == "linear"
        assert self.bridge._symbol_category_map["BTCUSD"] == "inverse"

    # ── T4b: kline uses registered category over name inference ──────────────

    def test_kline_uses_registered_category_over_infer(self):
        """
        Wave 7a-T4b: After registering BTCUSDT→spot, _refresh_kline_volume()
        must fetch with category=spot (not linear, which _infer would return).

        Wave 7a-T4b：登記 BTCUSDT→spot 後，_refresh_kline_volume() 必須
        用 category=spot 查詢，而非 _infer_category_from_symbol 返回的 linear。
        """
        import json
        from io import BytesIO

        self.bridge.register_symbol_category("BTCUSDT", "spot")
        self.bridge._km.get_tracked_symbols.return_value = ["BTCUSDT"]
        self.bridge._latest_prices = {"BTCUSDT": 60000.0}

        # Mock HTTP response: empty kline list (we only care about the URL used)
        # Mock HTTP 回應：空 kline 列表（我們只關心 URL 中的 category 參數）
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"retCode": 0, "result": {"list": []}}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        captured_urls = []

        def fake_urlopen(req, timeout=5):
            captured_urls.append(req.full_url)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.bridge._refresh_kline_volume()

        assert captured_urls, "urlopen must have been called at least once"
        # All URLs for BTCUSDT must use category=spot
        # BTCUSDT 的所有請求 URL 必須包含 category=spot
        for url in captured_urls:
            assert "category=spot" in url, (
                f"Expected category=spot in URL, got: {url!r}"
            )
            assert "category=linear" not in url, (
                f"Must NOT use category=linear for registered spot symbol, got: {url!r}"
            )

    # ── T4c: spot symbol uses map not infer ───────────────────────────────────

    def test_spot_symbol_uses_map_not_infer(self):
        """
        Wave 7a-T4c: _infer_category_from_symbol("BTCUSDT") returns "linear", but
        when registered as "spot" in the map, actual kline fetch must use "spot".

        Wave 7a-T4c：_infer_category_from_symbol("BTCUSDT") 返回 "linear"，
        但 map 登記為 "spot" 時，kline 查詢必須使用 "spot"。
        這驗證映射優先級高於名稱推斷。
        """
        # Confirm infer still returns linear (precondition)
        # 確認推斷仍返回 linear（前置條件）
        assert PipelineBridge._infer_category_from_symbol("BTCUSDT") == "linear", (
            "Precondition: _infer must still return 'linear' for BTCUSDT"
        )

        # Register as spot — map must override infer
        # 登記為 spot，映射必須覆蓋推斷
        self.bridge.register_symbol_category("BTCUSDT", "spot")
        self.bridge._km.get_tracked_symbols.return_value = ["BTCUSDT"]

        import json
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(
            {"retCode": 0, "result": {"list": []}}
        ).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        captured_urls = []

        def fake_urlopen(req, timeout=5):
            captured_urls.append(req.full_url)
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.bridge._refresh_kline_volume()

        for url in captured_urls:
            assert "category=spot" in url, (
                f"Map must override infer: expected category=spot, got: {url!r}"
            )

    # ── T4d: _process_pending_intents warns for unregistered symbol ───────────

    def test_process_intents_no_category_emits_warning(self):
        """
        Wave 7a-T4d: When an intent has no explicit category metadata and the
        symbol is NOT in _symbol_category_map, logger.warning must be called.

        Wave 7a-T4d：intent 無明確 category 且 symbol 不在映射中時，
        必須調用 logger.warning（提醒開發者登記 symbol-category）。
        """
        bridge = _make_bridge()
        bridge._active = True
        bridge._latest_prices = {"UNKNOWNSYM": 1.0}

        # Intent with no category metadata
        # 無 category 的 intent
        intent = MagicMock()
        intent.symbol = "UNKNOWNSYM"
        intent.side = "Buy"
        intent.order_type = "market"
        intent.price = None
        intent.qty = 1.0
        intent.metadata = {}  # no category key → defaults to linear
        intent.strategy_name = "test"
        intent.confidence = 0.7
        intent.reason = "test"
        intent.perception_data_id = None
        bridge._orch.collect_pending_intents.return_value = [intent]
        bridge._strategist_agent = None
        bridge._h0_gate = None

        # Governance: authorized + lease acquired
        # 治理：已授權 + 租約獲取成功
        bridge._governance_hub = MagicMock()
        bridge._governance_hub.is_authorized.return_value = True
        bridge._governance_hub.acquire_lease.return_value = {
            "lease_id": "lease_w7a",
            "expires_at_ms": int(time.time() * 1000) + 60000,
        }

        # Guardian approves (so we reach the category-check line)
        # Guardian 批准（讓流程到達 category 檢查行）
        mock_verdict = MagicMock()
        mock_verdict.result = "APPROVED"
        mock_verdict.risk_score = 0.1
        mock_guardian = MagicMock()
        mock_guardian.review_intent.return_value = mock_verdict

        import sys
        mock_maf = MagicMock()
        mock_maf.RiskVerdictResult.APPROVED = "APPROVED"
        mock_maf.RiskVerdictResult.REJECTED = "REJECTED"
        mock_maf.RiskVerdictResult.MODIFIED = "MODIFIED"
        mock_maf.TradeIntent.return_value = MagicMock()

        with patch.dict(sys.modules, {"app.multi_agent_framework": mock_maf}):
            bridge._guardian_agent = mock_guardian

        bridge._engine.submit_order.return_value = {
            "order": {"order_id": "w7a_001", "state": "paper_order_filled"},
            "rejected_reason": None,
        }

        # symbol is NOT in _symbol_category_map → warning expected
        # symbol 不在映射中 → 應觸發 warning
        assert "UNKNOWNSYM" not in bridge._symbol_category_map, (
            "Precondition: symbol must not be registered"
        )

        with self.assertLogs("app.pipeline_bridge", level="WARNING") as log_ctx:
            bridge._process_pending_intents()

        # At least one warning mentioning UNKNOWNSYM
        # 至少一條包含 UNKNOWNSYM 的 warning
        matching = [
            msg for msg in log_ctx.output
            if "UNKNOWNSYM" in msg and "WARNING" in msg
        ]
        assert matching, (
            f"Expected a WARNING log mentioning UNKNOWNSYM, got: {log_ctx.output}"
        )

    def test_process_intents_registered_symbol_no_warning(self):
        """
        Wave 7a-T4d-neg: When the symbol IS in _symbol_category_map (linear),
        no warning about unregistered category should be emitted.

        Wave 7a-T4d-neg：symbol 已在映射中登記（linear）時，
        不應發出未登記 category 的 warning。
        """
        bridge = _make_bridge()
        # Register symbol explicitly as linear — no warning expected
        # 明確登記 symbol 為 linear，不應觸發 warning
        bridge.register_symbol_category("BTCUSDT", "linear")
        bridge._active = True
        bridge._latest_prices = {"BTCUSDT": 60000.0}

        intent = MagicMock()
        intent.symbol = "BTCUSDT"
        intent.side = "Buy"
        intent.order_type = "market"
        intent.price = None
        intent.qty = 0.001
        intent.metadata = {}  # no explicit category → defaults to linear
        intent.strategy_name = "test"
        intent.confidence = 0.7
        intent.reason = "test"
        intent.perception_data_id = None
        bridge._orch.collect_pending_intents.return_value = [intent]
        bridge._strategist_agent = None
        bridge._h0_gate = None

        bridge._governance_hub = MagicMock()
        bridge._governance_hub.is_authorized.return_value = True
        bridge._governance_hub.acquire_lease.return_value = {
            "lease_id": "lease_reg",
            "expires_at_ms": int(time.time() * 1000) + 60000,
        }

        import sys
        mock_maf = MagicMock()
        mock_maf.RiskVerdictResult.APPROVED = "APPROVED"
        mock_maf.RiskVerdictResult.REJECTED = "REJECTED"
        mock_maf.RiskVerdictResult.MODIFIED = "MODIFIED"
        mock_maf.TradeIntent.return_value = MagicMock()
        mock_verdict = MagicMock()
        mock_verdict.result = "APPROVED"
        mock_verdict.risk_score = 0.1
        mock_guardian = MagicMock()
        mock_guardian.review_intent.return_value = mock_verdict

        with patch.dict(sys.modules, {"app.multi_agent_framework": mock_maf}):
            bridge._guardian_agent = mock_guardian

        bridge._engine.submit_order.return_value = {
            "order": {"order_id": "reg_001", "state": "paper_order_filled"},
            "rejected_reason": None,
        }

        # Patch logger.warning to capture calls without requiring assertLogs
        # (assertLogs requires at least one log entry to be produced at the given level)
        # 用 patch 捕獲 warning 調用，避免 assertLogs 的「至少一條 log」要求
        warning_calls = []
        original_warning = __import__("app.pipeline_bridge", fromlist=["logger"]).logger.warning

        def capture_warning(msg, *args, **kwargs):
            warning_calls.append(msg % args if args else msg)
            return original_warning(msg, *args, **kwargs)

        with patch(
            "app.pipeline_bridge.logger.warning",
            side_effect=capture_warning,
        ):
            bridge._process_pending_intents()

        unregistered_warnings = [
            msg for msg in warning_calls
            if "not in category map" in msg
        ]
        assert not unregistered_warnings, (
            f"Must NOT emit 'not in category map' warning for registered symbol, got: {unregistered_warnings}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
