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

  G3-08 Phase 2 補強（2026-04-26）：
  - 內建 ``_h1_local_stats`` 計數器：H1 自記 budget/complexity/cooldown skip
    + 通過次數，與 caller 注入的 ``stats`` dict 同步遞增（caller stats 仍為
    StrategistAgent 拼裝的 telemetry，本地 stats 是 H 狀態 cache 暴露專用）。
  - 新增 ``get_h1_snapshot()``：純讀取本地計數器與 cooldown 字典大小，
    供 ``h_state_query_handler.build_h_state_full_response`` 透過
    ``STRATEGIST_AGENT._h1_gate`` 拉取真實 H1 視圖（PA design §5.1 + §7.1）。
  - 在 budget/complexity/cooldown skip 與通過路徑 fire-and-forget
    ``invalidate_async("h1.<reason>")``，提早 Rust ``h_state_cache`` poller
    觸發 ad-hoc poll。``h_state_invalidator`` 內部已 env-gated；env=0 為
    module-level no-op，零負擔。
  - 純 Python，不影響業務邏輯：``check()`` 對 caller 仍以 True/False 回應，
    skip 計數路徑與既往一致；只是多走一條本地計數 + 一通 fire-and-forget。

MODULE_NOTE (English):
  H1 ThoughtGate — deterministic pre-AI gate for signal evaluation.
  Extracted from strategist_agent.py (§14.1 line limit compliance).
  Responsibilities:
  1. Budget check (cost_tracker.check_daily_budget)
  2. Complexity scoring (relevance_score + multi-symbol/urgency boost)
  3. Cooldown check (same symbol 30s dedup)
  4. should_call_ai final decision logic
  Zero circular imports: only depends on stdlib + typing, no same-directory imports.

  G3-08 Phase 2 augmentation (2026-04-26):
  - Built-in ``_h1_local_stats`` counters: H1 tracks its own
    budget/complexity/cooldown skip + pass counts in addition to whatever
    caller-supplied ``stats`` dict StrategistAgent threads through. Caller
    stats remain Strategist-shaped telemetry; local stats are dedicated to
    H-state cache exposure.
  - New ``get_h1_snapshot()``: pure-read accessor for local counters and
    cooldown dict size, consumed by
    ``h_state_query_handler.build_h_state_full_response`` via
    ``STRATEGIST_AGENT._h1_gate`` for the real H1 view (PA design §5.1 + §7.1).
  - Fire-and-forget ``invalidate_async("h1.<reason>")`` on skip and pass
    paths to nudge the Rust ``h_state_cache`` poller into an ad-hoc poll
    sooner than its 10s scheduled cycle. ``h_state_invalidator`` is
    env-gated internally; when env=0 the call is a module-level no-op
    with zero overhead.
  - Pure Python, business logic unchanged: ``check()`` still returns
    True/False to the caller, skip-counter paths behave identically; we
    only add a local counter increment and one fire-and-forget hint.

  Allowed imports: stdlib only (time, logging, typing) + sibling
  ``h_state_invalidator`` (whose ``invalidate_async`` is itself a no-op when
  the gateway env-gate is disabled). NO cross-module business imports.
  Forbidden imports: strategist_agent / model_router / any agent module
  (to prevent circular dependency).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

# Sibling import — ``invalidate_async`` is itself env-gated; on disabled
# gateway it's a cheap no-op (singleton stays None → early return). Importing
# at module top-level is safe: ``h_state_invalidator`` only depends on
# stdlib + lazy ``ipc_client``.
# 同目錄匯入 —— ``invalidate_async`` 自身已 env-gated；gateway 關閉時為廉價
# no-op（singleton 為 None 直接 return）。模組頂層匯入安全：
# ``h_state_invalidator`` 僅依賴 stdlib + 延遲 ``ipc_client``。
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async

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

        # G3-08 Phase 2: H1-local stats counter for h_state_cache exposure.
        # Mirrors the skip counters threaded via caller's ``stats`` dict but
        # owned by H1ThoughtGate so the snapshot stays self-contained
        # (caller-supplied dicts are StrategistAgent telemetry; this one
        # belongs to the H1 surface).
        # G3-08 Phase 2：H1 本地統計計數器，供 h_state_cache 暴露使用。
        # 與 caller 透過 ``stats`` dict 同步的 skip 計數鏡射，但歸 H1ThoughtGate
        # 自身擁有；caller 注入的 dict 屬 StrategistAgent telemetry，本地 dict
        # 專供 H1 表面用。
        self._h1_local_lock: threading.Lock = threading.Lock()
        self._h1_local_stats: Dict[str, int] = {
            "total_decisions": 0,    # check() invocations / check() 呼叫次數
            "ai_calls_allowed": 0,   # check() returned True / 通過 (True)
            "budget_skip": 0,        # _check_budget() denied / 預算被拒
            "complexity_skip": 0,    # complexity_score below threshold / 複雜度未達標
            "cooldown_skip": 0,      # cooldown window active / 冷卻期內
        }

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

        G3-08 Phase 2: each branch increments H1-local stats and emits a
        fire-and-forget invalidation hint to Rust ``h_state_cache``. The hint
        is env-gated inside ``h_state_invalidator`` (no-op when
        ``OPENCLAW_H_STATE_GATEWAY != "1"``) — never blocks H1's hot path.
        G3-08 Phase 2：每個分支同步遞增 H1 本地 stats 並 fire-and-forget
        ``invalidate_async`` 提示給 Rust ``h_state_cache``；提示在
        ``h_state_invalidator`` 內 env-gated（``OPENCLAW_H_STATE_GATEWAY != "1"``
        時為 no-op），永不阻塞 H1 hot-path。
        """
        with self._h1_local_lock:
            self._h1_local_stats["total_decisions"] += 1

        if not self._check_budget():
            stats["h1_budget_skip"] = stats.get("h1_budget_skip", 0) + 1
            with self._h1_local_lock:
                self._h1_local_stats["budget_skip"] += 1
            # Fire-and-forget invalidation hint (env-gated no-op when off).
            # fire-and-forget 失效提示（env 關閉時為 no-op）。
            _invalidate_h_state_async("h1.budget_skip")
            return False

        if self.complexity_score(intel) < self._COMPLEXITY_THRESHOLD:
            stats["h1_complexity_skip"] = stats.get("h1_complexity_skip", 0) + 1
            with self._h1_local_lock:
                self._h1_local_stats["complexity_skip"] += 1
            _invalidate_h_state_async("h1.complexity_skip")
            return False

        if not self._check_cooldown(intel):
            stats["h1_cooldown_skip"] = stats.get("h1_cooldown_skip", 0) + 1
            with self._h1_local_lock:
                self._h1_local_stats["cooldown_skip"] += 1
            _invalidate_h_state_async("h1.cooldown_skip")
            return False

        # All gates passed — AI call warranted. Counter + hint mirror skip paths.
        # 全閘通過 — AI 調用通過。計數與提示與 skip 路徑對稱。
        with self._h1_local_lock:
            self._h1_local_stats["ai_calls_allowed"] += 1
        _invalidate_h_state_async("h1.ai_call_allowed")
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

    def complexity_score(self, intel: Any) -> float:
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

    # ── G3-08 Phase 2: H state snapshot accessor ──
    # G3-08 Phase 2：H 狀態 snapshot 存取器

    def get_h1_snapshot(self) -> Dict[str, Any]:
        """Return a thread-safe snapshot of H1 stats for h_state_cache exposure.
        回傳 H1 狀態的線程安全 snapshot，供 h_state_cache 暴露使用。

        Schema (PA design §5.2 H1Stats parity):
          - ``total_decisions``      : int — ``check()`` invocations since boot
          - ``ai_calls_allowed``     : int — branches where ``check()`` returned True
          - ``budget_skip``          : int — denied by ``_check_budget()``
          - ``complexity_skip``      : int — below ``_COMPLEXITY_THRESHOLD``
          - ``cooldown_skip``        : int — within ``_COOLDOWN_WINDOW_S``
          - ``cooldown_dict_size``   : int — current ``_h1_cooldown`` cardinality
          - ``budget_remaining_pct`` : Optional[float] — ``cost_tracker``-derived
            daily remaining budget percentage (0.0-100.0); ``None`` when no
            tracker injected or tracker raises (fail-open per
            ``_check_budget()``).

        Schema 對齊 PA design §5.2 H1Stats：
          - ``total_decisions``      : int — 啟動以來 ``check()`` 呼叫次數
          - ``ai_calls_allowed``     : int — ``check()`` 回 True 的次數
          - ``budget_skip``          : int — 被 ``_check_budget()`` 拒絕
          - ``complexity_skip``      : int — 低於 ``_COMPLEXITY_THRESHOLD``
          - ``cooldown_skip``        : int — 在 ``_COOLDOWN_WINDOW_S`` 內
          - ``cooldown_dict_size``   : int — 當前 ``_h1_cooldown`` 大小
          - ``budget_remaining_pct`` : Optional[float] — 由 cost_tracker
            導出的日預算剩餘百分比（0.0-100.0）；無 tracker 或 tracker
            拋例外（``_check_budget()`` fail-open）時為 ``None``。

        Pure-read: NO side effects, NO state mutation, NO IPC. Caller may
        call this from any thread (acquires only the local stats lock).
        純讀取：無副作用、無狀態修改、無 IPC。任何線程皆可呼叫
        （僅取本地 stats 鎖）。
        """
        with self._h1_local_lock:
            stats_copy = dict(self._h1_local_stats)

        # Cooldown dict is owned exclusively by this instance; reading len()
        # is atomic in CPython but we copy size into a local immediately to
        # avoid TOCTOU surprises in the response dict.
        # cooldown 字典歸本實例獨有；CPython 下 len() 為原子讀，但仍立即
        # 拷貝到區域變數避免回應 dict 中的 TOCTOU 意外。
        cooldown_size = len(self._h1_cooldown)

        # Best-effort budget snapshot. ``cost_tracker.check_daily_budget()``
        # historically returns ``(allowed: bool, remaining: float)``; we expose
        # remaining as a percentage of hard cap when both fields available, else
        # ``None``. Fails silently to None on any tracker error (fail-open
        # mirrors ``_check_budget()``).
        # 預算 snapshot 盡力而為。``cost_tracker.check_daily_budget()`` 歷史上
        # 回 ``(allowed, remaining)``；當兩欄位皆可用時換算為硬頂的百分比，
        # 否則 ``None``。tracker 任何錯誤視為 None（與 ``_check_budget()``
        # fail-open 對齊）。
        budget_remaining_pct: Optional[float] = None
        if self.cost_tracker is not None:
            try:
                budget_call = self.cost_tracker.check_daily_budget()
                if isinstance(budget_call, tuple) and len(budget_call) >= 2:
                    _allowed, remaining = budget_call[0], budget_call[1]
                    hard_cap = getattr(
                        getattr(self.cost_tracker, "_config", None),
                        "daily_hard_cap_usd",
                        None,
                    )
                    if (
                        isinstance(remaining, (int, float))
                        and isinstance(hard_cap, (int, float))
                        and hard_cap > 0
                    ):
                        budget_remaining_pct = max(
                            0.0, min(100.0, float(remaining) / float(hard_cap) * 100.0)
                        )
            except Exception:  # noqa: BLE001 — fail-open
                # Per ``_check_budget()`` fail-open: tracker error must NOT
                # propagate; snapshot field stays None.
                # 與 ``_check_budget()`` fail-open 對齊：tracker 錯誤不向上
                # 傳播；snapshot 欄位保持 None。
                budget_remaining_pct = None

        snapshot: Dict[str, Any] = {
            "total_decisions": stats_copy["total_decisions"],
            "ai_calls_allowed": stats_copy["ai_calls_allowed"],
            "budget_skip": stats_copy["budget_skip"],
            "complexity_skip": stats_copy["complexity_skip"],
            "cooldown_skip": stats_copy["cooldown_skip"],
            "cooldown_dict_size": cooldown_size,
            "budget_remaining_pct": budget_remaining_pct,
        }
        return snapshot
