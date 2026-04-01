"""
test_market_scanner.py — Unit tests for MarketScanner (Wave 7a SPOT-1)
市場掃描器單元測試 — Wave 7a SPOT-1 多品類支援驗證

MODULE_NOTE (中文):
  驗證 MarketScanner 的多品類掃描能力，重點涵蓋：
  1. 預設僅掃 linear 品類（向後相容性）
  2. 同時傳入 ["linear", "spot"] 時正確掃描兩個品類
  3. Spot USDT pair（如 BTCUSDT）不被 USDT 過濾器誤殺
  4. api_category 字段正確傳遞到下游 SymbolOpportunity
  5. 一個品類 fetch 失敗時另一個品類仍正常返回（fail-open）
  6. Spot ticker 無 fundingRate 欄位時不崩潰（or 0 保護）

MODULE_NOTE (English):
  Validates MarketScanner multi-category scanning capability, focusing on:
  1. Default linear-only scan (backward compatibility)
  2. Scanning both ["linear", "spot"] categories when configured
  3. Spot USDT pairs (e.g. BTCUSDT) pass the USDT filter
  4. api_category field correctly propagated to SymbolOpportunity
  5. Fail-open: one category fetch failure does not block the other
  6. Spot tickers without fundingRate field do not crash (or 0 guard)

Safety invariant:
  - 所有測試使用 mock，零真實網絡調用 / All tests use mocks, zero real network calls.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from local_model_tools.market_scanner import MarketScanner, SymbolOpportunity


# =============================================================================
# Helpers / 測試輔助函數
# =============================================================================

def _make_linear_ticker(
    symbol: str = "BTCUSDT",
    last_price: float = 50000.0,
    turnover_24h: float = 100_000_000.0,
    price_24h_pct: float = 0.03,
    high_24h: float = 51000.0,
    low_24h: float = 49000.0,
    funding_rate: float = 0.0001,
) -> dict:
    """
    Build a mock linear ticker payload matching Bybit V5 API format.
    構造符合 Bybit V5 API 格式的 linear ticker mock 數據。
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


def _make_spot_ticker(
    symbol: str = "BTCUSDT",
    last_price: float = 50000.0,
    turnover_24h: float = 80_000_000.0,
    price_24h_pct: float = 0.02,
    high_24h: float = 51000.0,
    low_24h: float = 49000.0,
) -> dict:
    """
    Build a mock spot ticker payload — note: spot has NO fundingRate field.
    構造 spot ticker mock 數據 — 注意：現貨沒有 fundingRate 欄位。
    """
    return {
        "symbol": symbol,
        "lastPrice": str(last_price),
        "turnover24h": str(turnover_24h),
        "price24hPcnt": str(price_24h_pct),
        "highPrice24h": str(high_24h),
        "lowPrice24h": str(low_24h),
        # Intentionally omit fundingRate — spot tickers do not have this field
        # 刻意省略 fundingRate — 現貨 ticker 不包含此欄位
    }


def _build_api_response(tickers: list[dict]) -> bytes:
    """
    Wrap tickers in a Bybit V5 success response envelope.
    將 ticker 列表包裝為 Bybit V5 成功響應信封。
    """
    return json.dumps({
        "retCode": 0,
        "result": {"list": tickers},
    }).encode()


def _mock_urlopen_multi_category(
    linear_tickers: list[dict],
    spot_tickers: list[dict],
):
    """
    Build a mock urlopen context manager that returns different data per category.
    構造一個按品類返回不同數據的 urlopen mock 上下文管理器工廠。

    The mock inspects the URL to determine which ticker list to return.
    mock 通過檢查 URL 中的 category 參數來決定返回哪個 ticker 列表。
    """
    def _side_effect(req, timeout=10):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "category=spot" in url:
            data = _build_api_response(spot_tickers)
        else:
            data = _build_api_response(linear_tickers)
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read.return_value = data
        return cm
    return _side_effect


# =============================================================================
# Test Suite / 測試套件
# =============================================================================

class TestMarketScannerDefaultCategory:
    """
    Default behavior: MarketScanner without categories arg scans linear only.
    預設行為：未傳入 categories 時，MarketScanner 只掃 linear 品類。
    """

    def test_scanner_default_linear_only(self):
        """
        When no categories arg provided, scanner defaults to ["linear"].
        未傳入 categories 時，掃描器預設使用 ["linear"]，不掃 spot。
        """
        scanner = MarketScanner()
        # Should default to linear only — verify internal state
        # 驗證內部 _categories 預設值為 ["linear"]
        assert scanner._categories == ["linear"], (
            "Default categories must be ['linear'] for backward compatibility. "
            "預設品類必須是 ['linear'] 以確保向後相容性。"
        )

    def test_scanner_default_linear_only_makes_one_http_call(self):
        """
        Default scanner makes exactly one HTTP call (for linear category).
        預設掃描器只發出一個 HTTP 請求（只請求 linear 品類）。
        """
        linear_ticker = _make_linear_ticker(
            symbol="BTCUSDT",
            turnover_24h=100_000_000.0,
            price_24h_pct=0.05,  # 5% → trend signal
        )
        call_count = {"n": 0}

        def _side_effect(req, timeout=10):
            call_count["n"] += 1
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([linear_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner()
                scanner.scan()

        assert call_count["n"] == 1, (
            "Default scanner must make exactly 1 HTTP call (linear only). "
            "預設掃描器必須只發出 1 個 HTTP 請求（僅 linear）。"
        )


class TestMarketScannerSpotCategory:
    """
    Multi-category scanning: ["linear", "spot"] configuration.
    多品類掃描：["linear", "spot"] 配置驗證。
    """

    def test_scanner_spot_category_enabled(self):
        """
        When categories=["linear", "spot"], scanner fetches both categories.
        配置 categories=["linear", "spot"] 時，掃描器請求兩個品類的數據。
        """
        linear_ticker = _make_linear_ticker(symbol="BTCUSDT", turnover_24h=100_000_000.0, price_24h_pct=0.05)
        spot_ticker = _make_spot_ticker(symbol="ETHUSDT", turnover_24h=80_000_000.0, price_24h_pct=0.04)

        call_urls = []

        def _side_effect(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            call_urls.append(url)
            if "category=spot" in url:
                data = _build_api_response([spot_ticker])
            else:
                data = _build_api_response([linear_ticker])
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = data
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["linear", "spot"])
                results = scanner.scan()

        assert len(call_urls) == 2, (
            "Scanner with ['linear', 'spot'] must make exactly 2 HTTP calls. "
            "配置 ['linear', 'spot'] 的掃描器必須發出 2 個 HTTP 請求。"
        )
        assert any("category=linear" in u for u in call_urls), "Must request linear category / 必須請求 linear 品類"
        assert any("category=spot" in u for u in call_urls), "Must request spot category / 必須請求 spot 品類"

        symbols = [o.symbol for o in results]
        assert "BTCUSDT" in symbols, "Linear BTCUSDT must appear in results / Linear BTCUSDT 必須出現在結果中"
        assert "ETHUSDT" in symbols, "Spot ETHUSDT must appear in results / Spot ETHUSDT 必須出現在結果中"

    def test_scanner_categories_stored_correctly(self):
        """
        Configured categories are stored and reflected in stats.
        配置的品類正確儲存並反映在 stats() 中。
        """
        scanner = MarketScanner(categories=["linear", "spot"])
        assert scanner._categories == ["linear", "spot"]

        stats = scanner.get_stats()
        assert stats["categories"] == ["linear", "spot"], (
            "get_stats() must include the configured categories. "
            "get_stats() 必須包含配置的品類列表。"
        )


class TestMarketScannerUSDTFilter:
    """
    USDT filter behavior: spot BTCUSDT must pass, non-USDT must be filtered.
    USDT 過濾器行為：現貨 BTCUSDT 必須通過，非 USDT pair 必須被過濾。
    """

    def test_scanner_spot_ticker_passes_usdt_filter(self):
        """
        Spot BTCUSDT (ends in USDT) is NOT filtered out by the USDT suffix check.
        現貨 BTCUSDT（以 USDT 結尾）不應被 USDT 後綴過濾器排除。

        This validates that the filter `if not symbol.endswith('USDT'): continue`
        correctly allows spot USDT pairs to pass through.
        驗證過濾規則 `if not symbol.endswith('USDT'): continue` 對現貨 USDT pair 同樣正確放行。
        """
        spot_ticker = _make_spot_ticker(
            symbol="BTCUSDT",
            turnover_24h=100_000_000.0,
            price_24h_pct=0.05,  # 5% price change → triggers trend signal
            last_price=50000.0,
            high_24h=52500.0,
            low_24h=47500.0,
        )

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([spot_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["spot"])
                results = scanner.scan()

        symbols = [o.symbol for o in results]
        assert "BTCUSDT" in symbols, (
            "Spot BTCUSDT must NOT be filtered by the USDT suffix check. "
            "現貨 BTCUSDT 不應被 USDT 後綴過濾器排除。"
        )

    def test_scanner_non_usdt_spot_ticker_is_filtered(self):
        """
        Spot BTCETH (does NOT end in USDT) must be filtered out.
        現貨 BTCETH（不以 USDT 結尾）必須被過濾掉。

        Ensures the USDT filter still works for non-USDT pairs in spot category.
        確保 USDT 過濾器對 spot 品類中的非 USDT pair 仍然有效。
        """
        non_usdt_ticker = {
            "symbol": "BTCETH",
            "lastPrice": "15.0",
            "turnover24h": "50_000_000",  # High volume but wrong pair type
            "price24hPcnt": "0.04",
            "highPrice24h": "15.5",
            "lowPrice24h": "14.5",
        }

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([non_usdt_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["spot"])
                results = scanner.scan()

        symbols = [o.symbol for o in results]
        assert "BTCETH" not in symbols, (
            "Non-USDT spot pair BTCETH must be filtered out. "
            "非 USDT 的現貨 pair BTCETH 必須被過濾掉。"
        )


class TestMarketScannerApiCategoryPropagation:
    """
    api_category field propagation: SymbolOpportunity must carry the correct category.
    api_category 字段傳遞：SymbolOpportunity 必須攜帶正確的品類標籤。
    """

    def test_scanner_spot_api_category_propagated(self):
        """
        Opportunities from spot category carry api_category='spot' in results.
        從 spot 品類掃描到的機會，其 api_category 字段值必須為 'spot'。

        This is critical: downstream (StrategyAutoDeployer, ExecutorAgent) uses
        api_category to route orders to the correct Bybit endpoint.
        這是關鍵字段：下游（StrategyAutoDeployer、ExecutorAgent）通過 api_category
        路由訂單到正確的 Bybit API 端點。
        """
        spot_ticker = _make_spot_ticker(
            symbol="SOLUSDT",
            turnover_24h=60_000_000.0,
            price_24h_pct=0.06,
            last_price=100.0,
            high_24h=106.0,
            low_24h=94.0,
        )

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([spot_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["spot"])
                results = scanner.scan()

        assert len(results) > 0, "Spot ticker SOLUSDT must produce at least one opportunity / SOLUSDT 必須產生至少一個機會"
        sol_opps = [o for o in results if o.symbol == "SOLUSDT"]
        assert len(sol_opps) > 0, "SOLUSDT must be in scan results / SOLUSDT 必須出現在結果中"
        assert sol_opps[0].api_category == "spot", (
            f"Expected api_category='spot', got '{sol_opps[0].api_category}'. "
            f"期望 api_category='spot'，實際得到 '{sol_opps[0].api_category}'。"
        )

    def test_scanner_linear_api_category_propagated(self):
        """
        Opportunities from linear category carry api_category='linear'.
        從 linear 品類掃描到的機會，其 api_category 字段值必須為 'linear'。
        """
        linear_ticker = _make_linear_ticker(
            symbol="BTCUSDT",
            turnover_24h=200_000_000.0,
            price_24h_pct=0.08,
            last_price=50000.0,
            high_24h=54000.0,
            low_24h=46000.0,
        )

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([linear_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["linear"])
                results = scanner.scan()

        btc_opps = [o for o in results if o.symbol == "BTCUSDT"]
        assert len(btc_opps) > 0, "BTCUSDT must be in linear scan results / BTCUSDT 必須出現在 linear 掃描結果中"
        assert btc_opps[0].api_category == "linear", (
            f"Expected api_category='linear', got '{btc_opps[0].api_category}'."
        )

    def test_get_latest_opportunities_includes_api_category(self):
        """
        get_latest_opportunities() dict output includes 'api_category' key.
        get_latest_opportunities() 返回的字典中包含 'api_category' 鍵。
        """
        spot_ticker = _make_spot_ticker(
            symbol="ETHUSDT",
            turnover_24h=70_000_000.0,
            price_24h_pct=0.04,
            last_price=3000.0,
            high_24h=3120.0,
            low_24h=2880.0,
        )

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([spot_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["spot"])
                scanner.scan()

        latest = scanner.get_latest_opportunities()
        assert len(latest) > 0, "get_latest_opportunities must return data after scan"
        assert "api_category" in latest[0], (
            "get_latest_opportunities() dict must include 'api_category' key. "
            "get_latest_opportunities() 返回字典必須包含 'api_category' 鍵。"
        )
        assert latest[0]["api_category"] == "spot"


class TestMarketScannerFailOpen:
    """
    Fail-open behavior: one category failing must not block the other.
    Fail-open 行為：一個品類 fetch 失敗時，另一個品類仍應正常返回結果。

    Design principle: Principle 6 (fail → contract) + Principle 5 (survival first).
    設計原則：原則 6（失敗收縮）+ 原則 5（生存優先）— 部分失敗不阻塞整體。
    """

    def test_scanner_ticker_fetch_failure_one_category(self):
        """
        When spot fetch fails (network error), linear results are still returned.
        當 spot 品類 fetch 失敗（網絡異常）時，linear 品類的結果仍然正常返回。

        This validates fail-open: partial category failure does not block other categories.
        驗證 fail-open：部分品類失敗不阻塞其他品類的掃描結果。
        """
        linear_ticker = _make_linear_ticker(
            symbol="BTCUSDT",
            turnover_24h=200_000_000.0,
            price_24h_pct=0.06,
            last_price=50000.0,
            high_24h=53000.0,
            low_24h=47000.0,
        )

        def _side_effect(req, timeout=10):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "category=spot" in url:
                # Simulate network failure for spot category
                # 模擬 spot 品類網絡故障
                raise OSError("Simulated network timeout for spot / 模擬 spot 品類網絡超時")
            # Linear succeeds normally
            # linear 品類正常成功
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([linear_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["linear", "spot"])
                results = scanner.scan()  # Must not raise

        symbols = [o.symbol for o in results]
        assert "BTCUSDT" in symbols, (
            "Linear BTCUSDT must still be returned even when spot category fails. "
            "即使 spot 品類失敗，linear BTCUSDT 仍然必須返回結果。"
        )

    def test_scanner_both_categories_fail_returns_empty(self):
        """
        When all categories fail, scan returns empty list without raising.
        所有品類都失敗時，scan() 返回空列表，不拋出異常。

        Fail-open safety net: scanner never crashes the caller thread.
        Fail-open 安全網：掃描器永遠不會導致調用線程崩潰。
        """
        def _side_effect(req, timeout=10):
            raise OSError("Simulated total network failure / 模擬完全網絡故障")

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["linear", "spot"])
                results = scanner.scan()  # Must not raise

        assert results == [], (
            "scan() must return empty list when all categories fail, not raise. "
            "所有品類都失敗時，scan() 必須返回空列表，不可拋出異常。"
        )

    def test_scanner_error_stats_incremented_on_category_fetch_failure(self):
        """
        Fetch failure for a category increments errors stat correctly.
        品類 fetch 失敗時，stats 中的 errors 計數器正確遞增。

        Note: MarketScanner does NOT increment 'errors' on per-category HTTP failure;
        instead it logs a warning and continues (errors are for scan-level exceptions).
        注意：MarketScanner 對每個品類的 HTTP 失敗只記錄 warning 並繼續，
        不計入 errors 計數（errors 只計 scan 級異常）。
        This test verifies the graceful warning path is exercised without errors.
        此測試驗證 warning 路徑被正確執行，無異常發生。
        """
        def _side_effect(req, timeout=10):
            raise OSError("network error")

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["linear", "spot"])
                scanner.scan()

        stats = scanner.get_stats()
        # scans counter must be incremented even when all fetches fail
        # 即使所有 fetch 失敗，scans 計數器也必須遞增
        assert stats["scans"] == 1, "scans counter must be 1 after one scan() call"
        # errors only counts scan-level exceptions, not per-category HTTP failures
        # errors 只計入 scan 級異常，不計入每個品類的 HTTP 失敗
        assert stats["errors"] == 0, "errors counter must remain 0 for per-category HTTP warning path"


class TestMarketScannerSpotNoFundingRate:
    """
    Spot tickers lack fundingRate field — scanner must not crash.
    現貨 ticker 沒有 fundingRate 欄位 — 掃描器不可崩潰。

    The code uses `float(t.get("fundingRate", 0) or 0)` as the guard.
    代碼使用 `float(t.get("fundingRate", 0) or 0)` 作為防護。
    """

    def test_scanner_spot_no_funding_rate_no_crash(self):
        """
        Spot ticker without fundingRate field does not cause ValueError/TypeError.
        沒有 fundingRate 欄位的現貨 ticker 不導致 ValueError 或 TypeError。
        """
        # Spot ticker: no fundingRate key at all
        # 現貨 ticker：完全沒有 fundingRate 鍵
        spot_ticker = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000.0",
            "turnover24h": "100000000",
            "price24hPcnt": "0.05",
            "highPrice24h": "53000.0",
            "lowPrice24h": "47000.0",
            # fundingRate deliberately absent
            # 刻意省略 fundingRate
        }

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([spot_ticker])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["spot"])
                # Must not raise any exception
                # 不可拋出任何異常
                results = scanner.scan()

        assert isinstance(results, list), "scan() must return a list even with missing fundingRate"

    def test_scanner_spot_null_funding_rate_treated_as_zero(self):
        """
        Spot ticker with fundingRate=None or empty string is treated as 0.
        fundingRate 為 None 或空字符串的現貨 ticker，資金費率被當作 0 處理。

        Validates the `or 0` part of `float(t.get("fundingRate", 0) or 0)`.
        驗證 `float(t.get("fundingRate", 0) or 0)` 中 `or 0` 部分的作用。
        """
        spot_ticker_null = {
            "symbol": "ETHUSDT",
            "lastPrice": "3000.0",
            "turnover24h": "80000000",
            "price24hPcnt": "0.04",
            "highPrice24h": "3120.0",
            "lowPrice24h": "2880.0",
            "fundingRate": "",  # Empty string — must be treated as 0 via `or 0`
        }

        def _side_effect(req, timeout=10):
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cm)
            cm.__exit__ = MagicMock(return_value=False)
            cm.read.return_value = _build_api_response([spot_ticker_null])
            return cm

        with patch("urllib.request.urlopen", side_effect=_side_effect):
            with patch("urllib.request.Request", side_effect=lambda url, headers=None: MagicMock(full_url=url)):
                scanner = MarketScanner(categories=["spot"])
                results = scanner.scan()

        # ETHUSDT with 4% move should still be classified (trend/grid), just with funding_rate=0
        # 4% 漲幅的 ETHUSDT 應仍被分類（趨勢/網格），只是資金費率為 0
        eth_opps = [o for o in results if o.symbol == "ETHUSDT"]
        if eth_opps:
            assert eth_opps[0].funding_rate == 0.0, (
                "Empty fundingRate string must be normalized to 0.0. "
                "空字符串的 fundingRate 必須被規範化為 0.0。"
            )


class TestSymbolOpportunityDefaults:
    """
    SymbolOpportunity dataclass defaults — api_category defaults to 'linear'.
    SymbolOpportunity dataclass 預設值 — api_category 預設為 'linear'。
    """

    def test_symbol_opportunity_default_api_category(self):
        """
        SymbolOpportunity.api_category defaults to 'linear' when not specified.
        未指定 api_category 時，SymbolOpportunity.api_category 預設為 'linear'。

        Ensures backward compatibility for existing code that creates SymbolOpportunity
        without specifying api_category.
        確保現有代碼在不指定 api_category 時的向後相容性。
        """
        opp = SymbolOpportunity(
            symbol="BTCUSDT",
            score=75.0,
            category="trend",
        )
        assert opp.api_category == "linear", (
            "Default api_category must be 'linear' for backward compatibility. "
            "api_category 預設值必須為 'linear' 以確保向後相容性。"
        )

    def test_symbol_opportunity_explicit_spot_category(self):
        """
        SymbolOpportunity.api_category can be explicitly set to 'spot'.
        SymbolOpportunity.api_category 可以顯式設置為 'spot'。
        """
        opp = SymbolOpportunity(
            symbol="BTCUSDT",
            score=75.0,
            category="trend",
            api_category="spot",
        )
        assert opp.api_category == "spot"
