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
    啟動時從 Bybit API 拉取全量 symbol→category 映射，TTL 6 小時自動刷新。
    Fetches the full symbol→category mapping from Bybit API at startup,
    with 6-hour TTL auto-refresh.
    """

    def __init__(self, bybit_host: str = "https://api-testnet.bybit.com"):
        self._host = bybit_host.rstrip("/")
        self._cache: dict[str, str] = {}
        self._last_refresh_ts: float = 0.0
        self._lock = threading.Lock()

    def get(self, symbol: str) -> Optional[str]:
        """
        查詢 symbol 的 category。快取命中返回字符串，未知返回 None（不猜測）。
        Look up category for symbol. Returns string if known, None if unknown (no guessing).
        """
        with self._lock:
            return self._cache.get(symbol)

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
                        new_cache[sym] = category
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
            self._last_refresh_ts = time.monotonic()

        logger.info(
            "SymbolCategoryRegistry: refreshed — %d symbols cached "
            "/ 刷新完成，共快取 %d 個 symbol",
            len(new_cache), len(new_cache),
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
