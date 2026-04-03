"""
MODULE_NOTE (中文):
  H3 ModelRouter — 根據信號複雜度選擇 AI 模型層。
  從 strategist_agent.py 拆分而來（§14.1 行數約定）。
  職責：
  1. complexity -> model tier 路由（l1_9b / l1_27b / l2）
  2. L2 後台線程評估邏輯
  3. _l2_result_cache 快取管理（TTL 1h / 容量 200 / 過期清理）
  4. L2 高信心結果 -> 策略偏好權重回饋
  零循環依賴：只依賴標準庫 + typing，不 import strategist_agent。

MODULE_NOTE (English):
  H3 ModelRouter — routes signal complexity to appropriate AI model tier.
  Extracted from strategist_agent.py (§14.1 line limit compliance).
  Responsibilities:
  1. Complexity -> model tier routing (l1_9b / l1_27b / l2)
  2. L2 background thread evaluation
  3. _l2_result_cache management (TTL 1h / cap 200 / expiry cleanup)
  4. L2 high-confidence results -> strategy preference weight feedback
  Zero circular imports: only depends on stdlib + typing.

  Allowed imports: stdlib only (time, logging, threading, typing).
  Forbidden imports: any app.* module (to prevent circular dependency).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ModelRouter:
    """H3 ModelRouter: select model tier based on signal complexity.

    H3 模型路由：根據信號複雜度選擇模型層，平衡速度與精度。

    Tiers:
    - l1_9b  -> complexity < 0.5  (fast, simple signals)
    - l1_27b -> 0.5 <= complexity < 0.8 (moderate complexity)
    - l2     -> complexity >= 0.8  (high complexity, runs in background thread)

    L2 MUST be dispatched in threading.Thread to avoid blocking on_tick.
    L2 必須在 threading.Thread 中執行，不可阻塞 on_tick 主線程。
    """

    def __init__(self):
        # L2 result cache: stores background L2 evaluation results.
        # L2 結果快取：儲存後台 L2 評估結果，供下次決策週期使用。
        # Key: symbol string; Value: dict with "evaluation", "timestamp", "intel_id".
        # TTL: 3600s (1 hour). Cap: 200 entries.
        self._l2_result_cache: Dict[str, Dict[str, Any]] = {}
        self._l2_cache_lock = threading.Lock()
        self._L2_CACHE_TTL_S: float = 3600.0
        self._L2_CACHE_MAX_SIZE: int = 200

        # Budget checker callback — injected externally to avoid circular imports.
        # 預算檢查回調 — 外部注入以避免循環 import。
        # Signature: (tier: str) -> bool, returns True if call is allowed.
        self._budget_checker: Optional[Callable[[str], bool]] = None

    def set_budget_checker(self, checker: Callable[[str], bool]) -> None:
        """
        Inject a budget checker callback for L1.5/L2 tier gating.
        注入預算檢查回調，用於 L1.5/L2 tier 閘控。

        The checker receives a tier string ('l1_5' or 'l2') and returns
        True if the call is budget-allowed, False otherwise.
        回調接收 tier 字串（'l1_5' 或 'l2'），返回 True 表示預算允許。

        Args:
            checker: callable (tier: str) -> bool
        """
        self._budget_checker = checker

    def route(
        self,
        complexity: float,
        urgency: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Route complexity score to model tier (4-tier with L1.5/L2 upgrade logic).
        根據複雜度分數路由到模型層（四級路由，含 L1.5/L2 升級邏輯）。

        Backward compatible: when context is None, behaves as the original 3-tier router.
        向後兼容：context 為 None 時，行為與原始三級路由完全一致。

        Args:
            complexity: 0.0-1.0 complexity score from H1 / H1 產生的複雜度分數
            urgency: optional urgency hint (reserved for future use) / 可選緊急度提示
            context: optional dict with upgrade decision fields / 可選升級判斷上下文
                - confidence (float): signal confidence / 信號信心度
                - amount_pct (float): position size as % of portfolio / 倉位佔組合百分比
                - cusum_triggered (bool): CUSUM regime change detected / CUSUM 偵測到體制變化
                - daily_vol_pct (float): daily volatility % / 日波動率百分比
                - is_new_symbol (bool): first time trading this symbol / 首次交易此幣種
                - weekly_pnl_pct (float): trailing weekly PnL % / 過去一週 PnL 百分比
                - param_sharpe_change_pct (float): Sharpe ratio param drift % / Sharpe 比率參數漂移百分比

        Returns: 'l1_9b' | 'l1_27b' | 'l1_5' | 'l2'
        """
        # Base routing: low and moderate complexity / 基礎路由：低與中複雜度
        if complexity < 0.5:
            return "l1_9b"
        if complexity < 0.8:
            return "l1_27b"

        # High complexity (>= 0.8): attempt upgrade to L1.5 or L2
        # 高複雜度（>= 0.8）：嘗試升級到 L1.5 或 L2

        # No context provided — backward compatible: return "l2" directly
        # 未提供 context — 向後兼容：直接返回 "l2"
        if context is None:
            return "l2"

        # ── Determine upgrade tier from context / 根據 context 判斷升級 tier ──
        ctx = context

        # L1.5 upgrade conditions (any one triggers) / L1.5 升級條件（任一觸發）
        l1_5_triggered = (
            (ctx.get("confidence", 1.0) < 0.5 and ctx.get("amount_pct", 0.0) > 5.0)
            or ctx.get("cusum_triggered", False) is True
            or ctx.get("daily_vol_pct", 0.0) > 8.0
            or ctx.get("is_new_symbol", False) is True
        )

        if not l1_5_triggered:
            # No upgrade condition met — stay at l1_27b
            # 無升級條件滿足 — 留在 l1_27b
            return "l1_27b"

        # L2 escalation conditions (on top of L1.5) / L2 升級條件（在 L1.5 基礎上）
        l2_triggered = (
            ctx.get("weekly_pnl_pct", 0.0) < -5.0
            or ctx.get("param_sharpe_change_pct", 0.0) > 20.0
        )

        target_tier = "l2" if l2_triggered else "l1_5"

        # Budget gating / 預算閘控
        if self._budget_checker is not None:
            if not self._budget_checker(target_tier):
                # Budget denied — fallback to l1_27b (fail-closed, principle 6)
                # 預算拒絕 — 降級到 l1_27b（失敗時收縮，根原則 6）
                logger.info(
                    "ModelRouter: budget denied for tier '%s', fallback to l1_27b / "
                    "預算拒絕 tier '%s'，降級到 l1_27b",
                    target_tier, target_tier,
                )
                return "l1_27b"

        return target_tier

    # ── L2 Background Evaluation / L2 後台評估 ──

    def run_l2_background(
        self,
        intel: Any,
        evaluate_fn: Callable,
        weight_update_fn: Optional[Callable] = None,
    ) -> None:
        """
        Launch L2 evaluation in a background daemon thread.
        在後台 daemon 線程中執行 L2 評估。

        Args:
            intel: IntelObject to evaluate
            evaluate_fn: callable that takes intel and returns EdgeEvaluation
            weight_update_fn: optional callable(intel, evaluation) for weight updates
        """
        threading.Thread(
            target=self._evaluate_edge_l2,
            args=(intel, evaluate_fn, weight_update_fn),
            daemon=True,
        ).start()

    def _evaluate_edge_l2(
        self,
        intel: Any,
        evaluate_fn: Callable,
        weight_update_fn: Optional[Callable],
    ) -> None:
        """
        Async L2 evaluation executed in a background daemon thread.
        Results are cached per-symbol so the next decision cycle can benefit.
        在後台 daemon 線程執行的 L2 深度評估。結果按幣種快取。

        This method must NEVER be called from the main on_tick callback path.
        此方法絕對不能從 on_tick 主回調路徑直接調用。
        """
        try:
            result = evaluate_fn(intel)
            logger.info(
                "L2 async result for %s: has_edge=%s confidence=%.2f / L2 異步結果",
                intel.symbols, result.has_edge, result.confidence,
            )
            self._store_l2_result(intel, result, weight_update_fn)
        except Exception as e:
            logger.warning("L2 async evaluation failed: %s", type(e).__name__)

    def _store_l2_result(
        self,
        intel: Any,
        evaluation: Any,
        weight_update_fn: Optional[Callable],
    ) -> None:
        """
        Store L2 background evaluation result in per-symbol cache.
        將 L2 後台評估結果存入按幣種的快取。

        Thread-safe: uses dedicated _l2_cache_lock.
        線程安全：使用專用 _l2_cache_lock。
        """
        try:
            now = time.time()
            cache_entry = {
                "evaluation": evaluation,
                "timestamp": now,
                "intel_id": getattr(intel, "intel_id", "unknown"),
            }

            with self._l2_cache_lock:
                # Capacity guard: evict expired entries when at cap
                # 容量守衛：超過上限時清理過期條目
                if len(self._l2_result_cache) >= self._L2_CACHE_MAX_SIZE:
                    expired = [
                        k for k, v in self._l2_result_cache.items()
                        if now - v["timestamp"] >= self._L2_CACHE_TTL_S
                    ]
                    for k in expired:
                        del self._l2_result_cache[k]

                for symbol in getattr(intel, "symbols", []):
                    self._l2_result_cache[symbol] = cache_entry

            # High-confidence L2 results update strategy preference weights
            # 高信心 L2 結果更新策略偏好權重
            if (
                weight_update_fn is not None
                and evaluation.has_edge
                and evaluation.confidence >= 0.6
            ):
                weight_update_fn(intel, evaluation)

            logger.debug(
                "L2 result cached for %s (confidence=%.2f, has_edge=%s) / "
                "L2 結果已快取",
                getattr(intel, "symbols", []),
                evaluation.confidence,
                evaluation.has_edge,
            )
        except Exception as e:
            logger.warning("_store_l2_result failed (fail-open): %s", e)

    def check_l2_cache(self, symbol: str, stats: Dict[str, int]) -> Optional[Any]:
        """
        Check if a valid (non-expired) L2 result exists for this symbol.
        檢查此幣種是否有尚未過期的 L2 快取結果。

        Returns the cached EdgeEvaluation if found and within TTL, else None.
        若找到且在 TTL 內則返回快取的 EdgeEvaluation，否則返回 None。

        Args:
            symbol: trading pair symbol
            stats: mutable stats dict for cache hit/expired counters
        """
        try:
            now = time.time()
            with self._l2_cache_lock:
                entry = self._l2_result_cache.get(symbol)
                if entry is None:
                    return None
                age = now - entry["timestamp"]
                if age >= self._L2_CACHE_TTL_S:
                    del self._l2_result_cache[symbol]
                    stats["l2_cache_expired"] = stats.get("l2_cache_expired", 0) + 1
                    return None
                stats["l2_cache_hit"] = stats.get("l2_cache_hit", 0) + 1
                return entry["evaluation"]
        except Exception as e:
            logger.warning("check_l2_cache failed (fail-open): %s", e)
            return None

    @property
    def cache_size(self) -> int:
        """Current L2 cache size / 當前 L2 快取大小"""
        with self._l2_cache_lock:
            return len(self._l2_result_cache)
