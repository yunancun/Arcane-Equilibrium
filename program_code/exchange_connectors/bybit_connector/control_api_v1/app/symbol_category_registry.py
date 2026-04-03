# MODULE_NOTE:
# SymbolCategoryRegistry — Bybit symbol→category 啟動快取（方案 A）
# SymbolCategoryRegistry — startup cache for symbol→category mapping (Plan A)
#
# 職責：啟動時從 Bybit /v5/market/instruments-info 批量拉取 linear/spot/inverse
#       完整 symbol 列表，提供 O(1) 查詢，填充 PipelineBridge._symbol_category_map。
# Role: at startup, bulk-fetch linear/spot/inverse symbol lists from Bybit
#       /v5/market/instruments-info and provide O(1) lookup to seed
#       PipelineBridge._symbol_category_map.
#
# 原則 10 對齊：用確定性知識取代 _infer_category_from_symbol 的猜測。
# Principle 10 alignment: replaces heuristic guessing with deterministic knowledge.
# 原則 6 對齊：refresh() 失敗不阻啟動（soft dep），快取保持上次已知值。
# Principle 6 alignment: refresh() failure does not block startup; stale cache retained.

import logging
import threading
import time
import urllib.request
import json
from typing import Optional

logger = logging.getLogger(__name__)

_REGISTRY_TTL_SECONDS = 6 * 3600
_INSTRUMENTS_PATH = "/v5/market/instruments-info?category={category}&limit=1000"
_CATEGORIES_TO_FETCH = ("linear", "spot", "inverse")


class SymbolCategoryRegistry:
    """
    啟動時從 Bybit API 拉取全量 symbol→category 映射 + tickSize/qtyStep，TTL 6 小時自動刷新。
    Fetches the full symbol→category mapping plus tickSize/qtyStep from Bybit API at startup,
    with 6-hour TTL auto-refresh.
    """

    def __init__(self, bybit_host: str = "https://api-testnet.bybit.com"):
        self._host = bybit_host.rstrip("/")
        self._cache: dict[str, str] = {}
        # tick_size / qty_step 快取：symbol → {"tick_size": float, "qty_step": float}
        # Used for round_price_for_exchange / round_qty_for_exchange precision
        self._instrument_cache: dict[str, dict[str, float]] = {}
        self._last_refresh_ts: float = 0.0
        self._lock = threading.Lock()

    def get(self, symbol: str) -> Optional[str]:
        """
        查詢 symbol 的 category。快取命中返回字符串，未知返回 None（不猜測）。
        Look up category for symbol. Returns string if known, None if unknown (no guessing).
        """
        with self._lock:
            return self._cache.get(symbol)

    def get_tick_size(self, symbol: str) -> Optional[float]:
        """
        取得 symbol 的 tickSize（最小價格步長）。未知返回 None。
        Get the tickSize (minimum price step) for a symbol. Returns None if unknown.
        """
        with self._lock:
            info = self._instrument_cache.get(symbol)
            return info["tick_size"] if info else None

    def get_qty_step(self, symbol: str) -> Optional[float]:
        """
        取得 symbol 的 qtyStep（最小數量步長）。未知返回 None。
        Get the qtyStep (minimum qty step) for a symbol. Returns None if unknown.
        """
        with self._lock:
            info = self._instrument_cache.get(symbol)
            return info["qty_step"] if info else None

    def get_min_order_qty(self, symbol: str) -> Optional[float]:
        """取得 symbol 的最小下單量。Get minimum order qty for a symbol."""
        with self._lock:
            info = self._instrument_cache.get(symbol)
            return info.get("min_order_qty") if info else None

    def get_max_order_qty(self, symbol: str) -> Optional[float]:
        """取得 symbol 的最大下單量。Get maximum order qty for a symbol."""
        with self._lock:
            info = self._instrument_cache.get(symbol)
            return info.get("max_order_qty") if info else None

    def get_min_notional(self, symbol: str) -> Optional[float]:
        """取得 symbol 的最小名義價值。Get minimum notional value for a symbol."""
        with self._lock:
            info = self._instrument_cache.get(symbol)
            return info.get("min_notional") if info else None

    def validate_order_params(self, symbol: str, qty: float, price: float = 0.0) -> tuple[bool, str]:
        """
        驗證下單參數是否滿足交易所限制。
        Validate order params against exchange limits.
        Returns (is_valid, reason).
        """
        with self._lock:
            info = self._instrument_cache.get(symbol)
        if not info:
            return True, "no_instrument_info"  # fail-open / 無信息時放行

        min_qty = info.get("min_order_qty", 0)
        max_qty = info.get("max_order_qty", float("inf"))
        min_notional = info.get("min_notional", 0)

        if min_qty > 0 and qty < min_qty:
            return False, f"qty {qty} < minOrderQty {min_qty}"
        if max_qty > 0 and qty > max_qty:
            return False, f"qty {qty} > maxOrderQty {max_qty}"
        if min_notional > 0 and price > 0 and qty * price < min_notional:
            return False, f"notional {qty * price:.2f} < minNotional {min_notional}"
        return True, "ok"

    def known_count(self) -> int:
        """返回快取中已知 symbol 的數量。Returns number of known symbols in cache."""
        with self._lock:
            return len(self._cache)

    def is_stale(self) -> bool:
        """快取是否超過 TTL（6 小時）。Returns True if cache has exceeded TTL."""
        return (time.monotonic() - self._last_refresh_ts) > _REGISTRY_TTL_SECONDS

    def refresh(self) -> bool:
        """
        從 Bybit API 拉取三個品類的完整 symbol 列表，更新快取。
        Fetch full symbol list for linear/spot/inverse from Bybit API and update cache.

        成功返回 True，任何錯誤返回 False（不拋出）。失敗時保留舊快取。
        Returns True on success, False on any error (no raise). Retains old cache on failure.
        # TODO: pagination for spot (>1000 symbols when Bybit expands beyond limit)
        """
        new_cache: dict[str, str] = {}
        new_instruments: dict[str, dict[str, float]] = {}
        for category in _CATEGORIES_TO_FETCH:
            url = self._host + _INSTRUMENTS_PATH.format(category=category)
            try:
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                items = data.get("result", {}).get("list", [])
                for item in items:
                    sym = item.get("symbol")
                    if sym:
                        # Don't overwrite linear with spot — linear takes priority
                        # 不用 spot 覆蓋 linear — linear 優先
                        if sym not in new_cache or category == "linear":
                            new_cache[sym] = category
                        # Extract tickSize + qtyStep from filters for price/qty rounding
                        # 從 priceFilter/lotSizeFilter 提取 tickSize/qtyStep 用於精度取整
                        price_filter = item.get("priceFilter", {})
                        lot_filter = item.get("lotSizeFilter", {})
                        try:
                            tick_size = float(price_filter.get("tickSize", 0))
                            qty_step = float(lot_filter.get("qtyStep", 0))
                            min_order_qty = float(lot_filter.get("minOrderQty", 0))
                            max_order_qty = float(lot_filter.get("maxOrderQty", 0))
                            # minNotionalValue location varies by category
                            # minNotionalValue 在不同品類的位置不同
                            min_notional = float(lot_filter.get("minNotionalValue", 0))
                            if min_notional == 0:
                                min_notional = float(item.get("minNotionalValue", 0))
                            inst_info: dict[str, float] = {
                                "tick_size": tick_size if tick_size > 0 else 0.01,
                                "qty_step": qty_step if qty_step > 0 else 1.0,
                                "min_order_qty": min_order_qty,
                                "max_order_qty": max_order_qty,
                                "min_notional": min_notional,
                            }
                            # Linear takes priority over spot for shared symbols
                            # 共享符號中 linear 優先於 spot
                            if sym not in new_instruments or category == "linear":
                                new_instruments[sym] = inst_info
                        except (ValueError, TypeError):
                            pass  # skip invalid filter data
                logger.debug(
                    "SymbolCategoryRegistry: loaded %d symbols for category=%s "
                    "/ 已載入 %d 個 symbol（品類：%s）",
                    len(items), category, len(items), category,
                )
            except Exception as exc:
                # 單個 category 失敗不阻止其他 category 繼續拉取
                # A single category failure does not block other categories
                logger.warning(
                    "SymbolCategoryRegistry: failed to fetch category=%s from %s: %s "
                    "/ 拉取品類 %s 失敗：%s",
                    category, url, exc, category, exc,
                )

        if not new_cache:
            logger.warning(
                "SymbolCategoryRegistry: all category fetches failed; "
                "retaining stale cache (%d entries) "
                "/ 所有品類拉取均失敗，保留舊快取（%d 條）",
                len(self._cache), len(self._cache),
            )
            return False

        with self._lock:
            self._cache = new_cache
            self._instrument_cache = new_instruments
            self._last_refresh_ts = time.monotonic()

        logger.info(
            "SymbolCategoryRegistry: refreshed — %d symbols cached (%d with tick_size) "
            "/ 刷新完成，共快取 %d 個 symbol（%d 有 tickSize）",
            len(new_cache), len(new_instruments), len(new_cache), len(new_instruments),
        )
        return True

    def seed_pipeline_bridge(self, bridge: object) -> int:
        """
        將快取中的所有映射注入 PipelineBridge._symbol_category_map。
        Inject all cached mappings into PipelineBridge via register_symbol_category().

        返回注入的條目數。Returns number of entries injected.
        """
        if not hasattr(bridge, "register_symbol_category"):
            logger.warning(
                "SymbolCategoryRegistry.seed_pipeline_bridge: bridge has no "
                "register_symbol_category method; skipping "
                "/ bridge 無 register_symbol_category 方法，跳過注入"
            )
            return 0

        with self._lock:
            snapshot = dict(self._cache)

        count = 0
        for symbol, category in snapshot.items():
            try:
                bridge.register_symbol_category(symbol, category)
                count += 1
            except Exception as exc:
                # 單條注入失敗不阻止其餘 symbol
                # A single injection failure does not block remaining symbols
                logger.warning(
                    "SymbolCategoryRegistry: failed to register %s→%s: %s "
                    "/ 注入 %s→%s 失敗：%s",
                    symbol, category, exc, symbol, category, exc,
                )

        logger.info(
            "SymbolCategoryRegistry: seeded %d entries into PipelineBridge "
            "/ 已注入 %d 條映射到 PipelineBridge",
            count, count,
        )
        return count
