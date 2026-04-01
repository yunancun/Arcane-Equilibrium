"""
MODULE_NOTE (中文):
  H1 ThoughtGate — AI 調用前的確定性判斷閘門。
  從 strategist_agent.py 拆分而來（§14.1 行數約定）。
  職責：
  1. 預算檢查（cost_tracker.check_daily_budget）
  2. 複雜度評分（intel.relevance_score + 多幣種/緊迫度加分）
  3. 冷卻期檢查（同一幣種 30 秒內不重複觸發 AI）
  4. should_call_ai 最終決策邏輯
  零循環依賴：只依賴標準庫 + typing，不 import 同目錄其他模組。

MODULE_NOTE (English):
  H1 ThoughtGate — deterministic pre-AI gate for signal evaluation.
  Extracted from strategist_agent.py (§14.1 line limit compliance).
  Responsibilities:
  1. Budget check (cost_tracker.check_daily_budget)
  2. Complexity scoring (relevance_score + multi-symbol/urgency boost)
  3. Cooldown check (same symbol 30s dedup)
  4. should_call_ai final decision logic
  Zero circular imports: only depends on stdlib + typing, no same-directory imports.

  Allowed imports: stdlib only (time, logging, typing).
  Forbidden imports: any app.* module (to prevent circular dependency).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class H1ThoughtGate:
    """H1 ThoughtGate: pre-AI deterministic gate.

    Decides whether an IntelObject warrants an AI evaluation call,
    or should be handled by cheaper heuristic fallback.

    H1 思考閘門：AI 調用前的確定性判斷。
    決定 IntelObject 是否值得調用 AI 評估，
    或應由更低成本的啟發式回退處理。

    All methods are synchronous — required by MessageBus callback constraint.
    全部同步方法 — MessageBus 回調不可使用 await。
    """

    # Capacity cap for cooldown dict: prevent unbounded growth in multi-symbol scenarios.
    # 冷卻期字典容量上限：防止掃描大量幣種時無限增長（記憶體安全保護）。
    _H1_COOLDOWN_MAX_SIZE: int = 1000

    # Cooldown window in seconds / 冷卻期窗口（秒）
    _COOLDOWN_WINDOW_S: float = 30.0

    # Complexity threshold: below this, signal is too simple for AI
    # 複雜度閾值：低於此值的信號過於簡單，不值得調用 AI
    _COMPLEXITY_THRESHOLD: float = 0.3

    def __init__(
        self,
        *,
        cost_tracker: Optional[Any] = None,
    ):
        # cost_tracker: injected externally; None = no budget tracking
        # cost_tracker：外部注入；None 表示不做預算追蹤（fail-open）
        self.cost_tracker = cost_tracker

        # Per-symbol last-intel timestamp for 30-second dedup
        # 每個幣種上次情報時間戳，30 秒內重複信號跳過 AI
        self._h1_cooldown: Dict[str, float] = {}

    def check(self, intel: Any, stats: Dict[str, int]) -> bool:
        """
        Main entry point: decide whether AI should be called for this intel.
        主入口：決定是否應為此情報調用 AI。

        Args:
            intel: IntelObject with .symbols, .relevance_score, .metadata
            stats: mutable stats dict — H1 skip counters will be incremented

        Returns:
            True if AI call is warranted, False if heuristic fallback should be used.
            True 表示應調用 AI，False 表示應使用啟發式回退。
        """
        if not self._check_budget():
            stats["h1_budget_skip"] = stats.get("h1_budget_skip", 0) + 1
            return False

        if self._complexity_score(intel) < self._COMPLEXITY_THRESHOLD:
            stats["h1_complexity_skip"] = stats.get("h1_complexity_skip", 0) + 1
            return False

        if not self._check_cooldown(intel):
            stats["h1_cooldown_skip"] = stats.get("h1_cooldown_skip", 0) + 1
            return False

        return True

    # ── Budget check / 預算檢查 ──

    def _check_budget(self) -> bool:
        """
        H1 budget check: return True if AI call is affordable.
        H1 預算檢查：若 AI 調用在預算內則返回 True。

        If cost_tracker is None, fail-open and allow AI call.
        若 cost_tracker 為 None，fail-open 允許 AI 調用。
        """
        if self.cost_tracker is None:
            return True
        try:
            allowed, _ = self.cost_tracker.check_daily_budget()
            return allowed
        except Exception:
            # fail-open: tracker error must not block evaluation
            # fail-open：追蹤器異常不得阻止評估
            return True

    # ── Complexity scoring / 複雜度評分 ──

    def _complexity_score(self, intel: Any) -> float:
        """
        H1 complexity scoring: rule-based, synchronous, no AI calls.
        H1 複雜度評分：純規則，同步執行，不調用 AI。

        Returns 0.0-1.0. Score < 0.3 means signal is too simple for AI evaluation.
        返回 0.0-1.0。分數 < 0.3 表示信號過於簡單，不值得調用 AI。
        """
        score = intel.relevance_score
        if len(intel.symbols) > 3:
            score = min(1.0, score + 0.2)
        if getattr(intel, "metadata", {}).get("urgency") == "high":
            score = min(1.0, score + 0.2)
        return score

    # ── Cooldown check / 冷卻期檢查 ──

    def _check_cooldown(self, intel: Any) -> bool:
        """
        H1 cooldown check: return True if symbol is not in cooldown window.
        H1 冷卻期檢查：同一符號 30 秒內重複信號跳過 AI。

        TD-4: Capacity protection — when dict exceeds max size, evict expired entries.
        TD-4: 容量保護 — 字典超過上限時清理過期條目。
        """
        now = time.time()

        # TD-4: Capacity guard — evict expired entries before inserting new ones.
        # TD-4: 容量守衛 — 超過上限時才執行過期清理。
        if len(self._h1_cooldown) >= self._H1_COOLDOWN_MAX_SIZE:
            expired_keys = [
                sym for sym, ts in self._h1_cooldown.items()
                if now - ts >= self._COOLDOWN_WINDOW_S
            ]
            for sym in expired_keys:
                del self._h1_cooldown[sym]
            if expired_keys:
                logger.debug(
                    "TD-4 _h1_cooldown evicted %d expired entries, size now %d / "
                    "已清理 %d 個過期條目，當前大小 %d",
                    len(expired_keys), len(self._h1_cooldown),
                    len(expired_keys), len(self._h1_cooldown),
                )

        for symbol in intel.symbols:
            last = self._h1_cooldown.get(symbol, 0.0)
            if now - last < self._COOLDOWN_WINDOW_S:
                return False

        # All symbols passed cooldown — update timestamps
        # 所有幣種通過冷卻期 — 更新時間戳
        for symbol in intel.symbols:
            self._h1_cooldown[symbol] = now
        return True

    # ── Backward-compatible delegators (used by StrategistAgent) ──
    # These exist so StrategistAgent can expose the same individual methods
    # as before the refactor, preserving public API compatibility.

    @property
    def cooldown_dict(self) -> Dict[str, float]:
        """Direct access to cooldown dict for backward compatibility.
        直接訪問冷卻期字典（向後兼容）。"""
        return self._h1_cooldown
