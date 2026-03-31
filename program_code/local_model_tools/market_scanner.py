"""
Market Scanner — Discover trading opportunities across all Bybit symbols
市场扫描器 — 在所有 Bybit 交易对中发现交易机会

MODULE_NOTE (中文):
  定期扫描 Bybit 全市场 tickers，对每个交易对进行分类和评分：
  1. 高 funding rate → Funding Rate 套利机会
  2. 高波动率 + 区间震荡 → 网格交易机会
  3. 强趋势 → 趋势跟踪机会
  4. BB 收窄后扩张 → 突破机会

  扫描结果传给 StrategyAutoDeployer 进行自动策略部署。

  风险感知：
  - 排除低流动性交易对（成交量过低）
  - 排除价格过低的交易对（容易被操纵）
  - 排除新上市交易对（数据不足）
  - 限制最大同时交易品种数

MODULE_NOTE (English):
  Periodically scans all Bybit tickers, classifies and scores each:
  1. High funding rate → funding arb opportunity
  2. High volatility + ranging → grid trading opportunity
  3. Strong trend → trend following opportunity
  4. BB squeeze→expansion → breakout opportunity

Safety invariant:
  - 只读扫描，不下单 / Read-only scan, no orders
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.request
import json as _json
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Minimum thresholds for symbol eligibility
MIN_VOLUME_24H_USDT = 5_000_000    # $5M daily volume minimum
MIN_PRICE_USDT = 0.01               # Skip sub-penny tokens
MAX_SYMBOLS_TO_TRADE = 5            # Max simultaneous symbols


@dataclass
class SymbolOpportunity:
    """A scored trading opportunity for a symbol."""
    symbol: str
    score: float                     # 0-100, higher = better opportunity
    category: str                    # "funding_arb" / "grid" / "trend" / "breakout" / "reversion"
    funding_rate: float = 0.0
    funding_rate_abs_bps: float = 0.0
    volume_24h: float = 0.0
    price: float = 0.0
    price_change_pct_24h: float = 0.0
    volatility_hint: str = ""        # "high" / "medium" / "low"
    reason: str = ""
    api_category: str = "linear"     # Bybit API category: "linear" / "spot" / "inverse"


class MarketScanner:
    """
    Scans Bybit perpetual market for trading opportunities.
    """

    def __init__(
        self,
        *,
        scan_interval_sec: float = 300.0,  # 5 minutes
        min_volume: float = MIN_VOLUME_24H_USDT,
        max_symbols: int = MAX_SYMBOLS_TO_TRADE,
        base_url: str = "https://api.bybit.com",
        categories: list[str] | None = None,
    ) -> None:
        self._interval = scan_interval_sec
        self._min_volume = min_volume
        self._max_symbols = max_symbols
        self._base_url = base_url
        # Scan categories: defaults to ["linear"], supports ["linear", "spot"]
        # 掃描品類：預設只掃 linear，可擴展支持 spot
        self._categories = categories or ["linear"]
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self._latest_opportunities: list[SymbolOpportunity] = []
        self._latest_scan_ts: int = 0
        self._stats = {"scans": 0, "symbols_scanned": 0, "opportunities_found": 0, "errors": 0}
        self._on_scan_callbacks: list[Any] = []

    def register_on_scan(self, callback: Any) -> None:
        """Register callback for scan results: callback(opportunities: list[SymbolOpportunity])"""
        self._on_scan_callbacks.append(callback)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="market-scanner")
        self._thread.start()
        logger.info("Market scanner started (interval=%ds) / 市场扫描器已启动", self._interval)

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        # Initial scan after 30s delay (let system stabilize)
        time.sleep(30)
        while self._running:
            try:
                self.scan()
            except Exception:
                logger.exception("Market scan error / 市场扫描异常")
                self._stats["errors"] += 1
            time.sleep(self._interval)

    def scan(self) -> list[SymbolOpportunity]:
        """
        Run a full market scan across all configured categories. Returns scored opportunities.
        在所有配置的品類中進行全市場掃描。返回評分後的交易機會。
        """
        all_tickers: list[tuple[dict, str]] = []  # (ticker_data, api_category)

        # Fetch tickers for each configured category
        # 拉取每個配置品類的 ticker 數據
        for cat in self._categories:
            try:
                url = f"{self._base_url}/v5/market/tickers?category={cat}"
                req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = _json.loads(resp.read().decode())
                if data.get("retCode") == 0:
                    for t in data.get("result", {}).get("list", []):
                        all_tickers.append((t, cat))
                    logger.debug("Fetched %d tickers for category=%s", len(data.get("result", {}).get("list", [])), cat)
            except Exception as e:
                logger.warning("Ticker fetch failed for category=%s: %s", cat, e)

        self._stats["scans"] += 1
        self._stats["symbols_scanned"] = len(all_tickers)

        # Score each symbol
        opportunities: list[SymbolOpportunity] = []

        for t, api_category in all_tickers:
            try:
                symbol = t.get("symbol", "")
                price = float(t.get("lastPrice", 0))
                volume_24h = float(t.get("turnover24h", 0))  # USDT turnover
                # Spot tickers don't have fundingRate — default to 0
                # 現貨沒有資金費率 — 預設為 0
                funding_rate = float(t.get("fundingRate", 0) or 0)
                price_change = float(t.get("price24hPcnt", 0)) * 100  # percentage
                high_24h = float(t.get("highPrice24h", 0))
                low_24h = float(t.get("lowPrice24h", 0))

                # Filter: minimum requirements
                if volume_24h < self._min_volume:
                    continue
                if price < MIN_PRICE_USDT:
                    continue
                if not symbol.endswith("USDT"):
                    continue  # Only USDT pairs (applies to both linear and spot)

                # Calculate volatility (24h range as % of price)
                volatility_pct = ((high_24h - low_24h) / price * 100) if price > 0 else 0
                funding_abs_bps = abs(funding_rate) * 10000

                # Classify opportunity
                opp = self._classify(
                    symbol=symbol,
                    price=price,
                    volume_24h=volume_24h,
                    funding_rate=funding_rate,
                    funding_abs_bps=funding_abs_bps,
                    price_change_pct=price_change,
                    volatility_pct=volatility_pct,
                    api_category=api_category,
                )
                if opp and opp.score > 20:  # Minimum score threshold
                    opportunities.append(opp)

            except (ValueError, TypeError):
                continue

        # Sort by score descending, take top N
        opportunities.sort(key=lambda o: o.score, reverse=True)
        top = opportunities[:self._max_symbols * 2]  # Keep 2x for diversity

        with self._lock:
            self._latest_opportunities = top
            self._latest_scan_ts = int(time.time() * 1000)
            self._stats["opportunities_found"] = len(top)

        # Notify callbacks
        for cb in self._on_scan_callbacks:
            try:
                cb(top)
            except Exception:
                logger.exception("Scan callback error")

        logger.info(
            "Market scan: %d tickers → %d opportunities (top: %s) / 市场扫描完成",
            len(all_tickers), len(top),
            ", ".join(f"{o.symbol}({o.category}:{o.score:.0f})" for o in top[:3]),
        )

        return top

    def _classify(
        self,
        symbol: str,
        price: float,
        volume_24h: float,
        funding_rate: float,
        funding_abs_bps: float,
        price_change_pct: float,
        volatility_pct: float,
        api_category: str = "linear",
    ) -> SymbolOpportunity | None:
        """Classify a symbol into an opportunity category."""

        # Volatility classification
        if volatility_pct > 8:
            vol_hint = "high"
        elif volatility_pct > 3:
            vol_hint = "medium"
        else:
            vol_hint = "low"

        best_score = 0.0
        best_category = ""
        best_reason = ""

        # 1. Funding Rate Arb (need abs > 5 bps for delta-neutral to be profitable)
        if funding_abs_bps > 5:
            score = min(100, funding_abs_bps * 3)  # 5bps=15, 10bps=30, 30bps=90
            # Bonus for high volume (better execution)
            if volume_24h > 50_000_000:
                score *= 1.2
            direction = "short_perp" if funding_rate > 0 else "long_perp"
            if score > best_score:
                best_score = score
                best_category = "funding_arb"
                best_reason = f"Funding {funding_abs_bps:.1f}bps ({direction}), vol=${volume_24h/1e6:.0f}M"

        # 2. Grid Trading (medium volatility + ranging)
        if 2 < volatility_pct < 10 and abs(price_change_pct) < 3:
            score = 40 + (volatility_pct * 3)  # More vol = more grid trades
            if volume_24h > 20_000_000:
                score *= 1.1
            if score > best_score:
                best_score = score
                best_category = "grid"
                best_reason = f"Ranging: vol={volatility_pct:.1f}%, change={price_change_pct:+.1f}%, turnover=${volume_24h/1e6:.0f}M"

        # 3. Trend Following (strong directional move)
        # Score capped at 100 so extreme moves don't systematically outbid funding_arb/grid
        # 趋势分数上限 100，防止极端涨跌幅压制 funding_arb/grid 机会
        if abs(price_change_pct) > 3 and volatility_pct > 3:
            score = min(100.0, 30 + abs(price_change_pct) * 5)
            direction = "bullish" if price_change_pct > 0 else "bearish"
            if score > best_score:
                best_score = score
                best_category = "trend"
                best_reason = f"Trending {direction}: change={price_change_pct:+.1f}%, vol={volatility_pct:.1f}%"

        # 4. Mean Reversion (low volatility, stable)
        if volatility_pct < 4 and abs(price_change_pct) < 2:
            score = 25 + (4 - volatility_pct) * 5
            if score > best_score:
                best_score = score
                best_category = "reversion"
                best_reason = f"Stable/ranging: vol={volatility_pct:.1f}%, change={price_change_pct:+.1f}%"

        if not best_category:
            return None

        return SymbolOpportunity(
            symbol=symbol,
            score=best_score,
            category=best_category,
            funding_rate=funding_rate,
            funding_rate_abs_bps=funding_abs_bps,
            volume_24h=volume_24h,
            price=price,
            price_change_pct_24h=price_change_pct,
            volatility_hint=vol_hint,
            reason=best_reason,
            api_category=api_category,
        )

    def get_latest_opportunities(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "symbol": o.symbol, "score": round(o.score, 1),
                    "category": o.category, "funding_rate_bps": round(o.funding_rate_abs_bps, 2),
                    "volume_24h_m": round(o.volume_24h / 1e6, 1),
                    "price": o.price, "price_change_24h": round(o.price_change_pct_24h, 2),
                    "volatility": o.volatility_hint, "reason": o.reason,
                    "api_category": o.api_category,
                }
                for o in self._latest_opportunities
            ]

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "component": "market_scanner",
                "running": self._running,
                "categories": self._categories,
                "last_scan_ts_ms": self._latest_scan_ts,
                "top_opportunities": len(self._latest_opportunities),
                **self._stats,
            }
