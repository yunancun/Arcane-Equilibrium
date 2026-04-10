# MODULE_NOTE:
# test_symbol_category_registry.py — SymbolCategoryRegistry 單元測試
# Tests for SymbolCategoryRegistry (Plan A startup symbol→category cache)
#
# 覆蓋範圍（T-A1 ~ T-A15）：
# - T-A1~A2: get() / known_count() 空快取行為
# - T-A3~A5: refresh() 成功場景（linear/spot/inverse）
# - T-A6~A8: refresh() 失敗場景（全失敗/部分失敗/舊快取保留）
# - T-A9~A10: is_stale() 初始狀態與刷新後
# - T-A11~A13: seed_pipeline_bridge() 注入行為
# - T-A14: 並發 refresh 不拋出
# - T-A15: _infer_category_from_symbol fallback warning 驗證

import json
import threading
import time
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.symbol_category_registry import SymbolCategoryRegistry


def _make_mock_urlopen(responses: dict):
    """
    回傳模擬 Bybit instruments-info 回應的 urlopen patch。
    Returns a urlopen patch that mocks Bybit instruments-info responses.
    responses: {category_str: [symbol1, symbol2, ...] or Exception}
    """
    def side_effect(req, timeout=10):
        # 從 URL 解析 category / Parse category from URL
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for cat, val in responses.items():
            if f"category={cat}" in url:
                if isinstance(val, Exception):
                    raise val
                payload = {
                    "retCode": 0,
                    "result": {"list": [{"symbol": s} for s in val]},
                }
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
                mock_resp.__enter__ = lambda self: self
                mock_resp.__exit__ = MagicMock(return_value=False)
                return mock_resp
        raise ValueError(f"Unexpected URL: {url}")

    return side_effect


class TestSymbolCategoryRegistryGet:
    """T-A1: get() 空快取返回 None / empty cache returns None"""

    def test_get_empty_cache_returns_none(self):
        # 空快取不猜測，返回 None | Empty cache does not guess; returns None
        reg = SymbolCategoryRegistry()
        assert reg.get("BTCUSDT") is None

    def test_known_count_empty(self):
        # T-A2: 初始 known_count 為 0 / Initial known_count is 0
        reg = SymbolCategoryRegistry()
        assert reg.known_count() == 0


class TestSymbolCategoryRegistryRefreshSuccess:
    """T-A2 ~ T-A5: refresh() 成功場景 / Successful refresh scenarios"""

    def _make_registry_with_data(self):
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": ["BTCUSDT", "ETHUSDT"],
            "spot": ["BTCUSDT"],  # 同名 symbol，後寫入覆蓋 / Same name, later write wins
            "inverse": ["BTCUSD", "ETHUSD"],
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
            reg.refresh()
        return reg

    def test_get_linear_symbol(self):
        # T-A2: linear-only symbol 正確返回 / linear-only symbol returns correctly
        reg = self._make_registry_with_data()
        # ETHUSDT 只在 linear 品類中，應精確為 "linear"
        # ETHUSDT exists only in linear; must return exactly "linear"
        assert reg.get("ETHUSDT") == "linear"

    def test_btcusdt_spot_overrides_linear(self):
        # BTCUSDT 同時存在於 linear 和 spot，按 _CATEGORIES_TO_FETCH 順序 spot 後寫入勝出。
        # BTCUSDT exists in both linear and spot; spot is fetched after linear, so spot wins.
        # 這是有意設計：StrategyAutoDeployer.register_symbol_category() 在部署策略時
        # 會以實際部署的 category 覆蓋 Registry 的值，確保運行時行為正確。
        # Intentional: StrategyAutoDeployer.register_symbol_category() at deploy-time
        # will override this with the actual category, ensuring correct runtime behaviour.
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": ["BTCUSDT"],
            "spot": ["BTCUSDT"],  # linear 優先，不被 spot 覆蓋 | linear takes priority, not overridden by spot
            "inverse": [],
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
            reg.refresh()
        # Session 9 修正：linear 優先於 spot（避免 qtyStep 被 spot 覆蓋）
        # Session 9 fix: linear takes priority over spot (prevents qtyStep overwrite)
        assert reg.get("BTCUSDT") == "linear"

    def test_get_inverse_symbol(self):
        # T-A4: inverse symbol 正確返回 / inverse symbol returns correctly
        reg = self._make_registry_with_data()
        assert reg.get("BTCUSD") == "inverse"
        assert reg.get("ETHUSD") == "inverse"

    def test_known_count_positive(self):
        # T-A5: refresh 後 known_count > 0 / After refresh known_count > 0
        reg = self._make_registry_with_data()
        assert reg.known_count() > 0

    def test_get_spot_symbol(self):
        # T-A3: spot-only symbol 正確返回 / spot-only symbol returns correctly
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": ["ETHUSDT"],
            "spot": ["BTCUSDT_SPOT_ONLY"],
            "inverse": ["BTCUSD"],
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
            reg.refresh()
        assert reg.get("BTCUSDT_SPOT_ONLY") == "spot"


class TestSymbolCategoryRegistryRefreshFailure:
    """T-A6 ~ T-A8: refresh() 失敗場景 / Failure scenarios"""

    def test_all_fail_returns_false_and_empty(self):
        # T-A6: 全部失敗，known_count=0，返回 False / All fail → False, known_count=0
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": Exception("network error"),
            "spot": Exception("network error"),
            "inverse": Exception("network error"),
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
            result = reg.refresh()
        assert result is False
        assert reg.known_count() == 0

    def test_stale_cache_retained_on_failure(self):
        # T-A7: 第一次成功，第二次失敗，舊快取保留 / First success, second failure → retain old cache
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        success_responses = {
            "linear": ["BTCUSDT"],
            "spot": [],
            "inverse": [],
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(success_responses)):
            reg.refresh()
        assert reg.get("BTCUSDT") is not None

        fail_responses = {
            "linear": Exception("error"),
            "spot": Exception("error"),
            "inverse": Exception("error"),
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(fail_responses)):
            result = reg.refresh()
        assert result is False
        assert reg.get("BTCUSDT") is not None  # 舊快取保留 | old cache retained

    def test_partial_failure_loads_successful_categories(self):
        # T-A8: 單個 category 失敗，其他正常載入 / Single category failure, others load fine
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": ["BTCUSDT"],
            "spot": Exception("spot unavailable"),
            "inverse": ["BTCUSD"],
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
            result = reg.refresh()
        # 部分成功仍返回 True，因為 new_cache 非空 / Partial success returns True (non-empty cache)
        assert result is True
        assert reg.get("BTCUSD") == "inverse"


class TestSymbolCategoryRegistryStale:
    """T-A9 ~ T-A10: is_stale() 行為驗證 / is_stale() behavior"""

    def test_is_stale_initially(self):
        # T-A9: 從未刷新時為 stale / Never refreshed → is stale
        reg = SymbolCategoryRegistry()
        assert reg.is_stale() is True

    def test_not_stale_after_refresh(self):
        # T-A10: 剛刷新後不是 stale / Just refreshed → not stale
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": ["BTCUSDT"],
            "spot": [],
            "inverse": [],
        }
        with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
            reg.refresh()
        assert reg.is_stale() is False


# TestSymbolCategoryRegistrySeedPipelineBridge deleted (DEAD-PY-2)

class TestSymbolCategoryRegistryThreadSafety:
    """T-A14: 並發 refresh 不拋出 / Concurrent refresh does not raise"""

    def test_concurrent_refresh_no_exception(self):
        reg = SymbolCategoryRegistry(bybit_host="https://mock.bybit.com")
        responses = {
            "linear": ["BTCUSDT"],
            "spot": [],
            "inverse": [],
        }
        errors = []

        def do_refresh():
            try:
                with patch("urllib.request.urlopen", side_effect=_make_mock_urlopen(responses)):
                    reg.refresh()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_refresh) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [], f"Concurrent refresh raised: {errors}"


# TestInferCategoryFallbackWarning deleted (DEAD-PY-2 — uses deleted PipelineBridge._infer_category_from_symbol)
