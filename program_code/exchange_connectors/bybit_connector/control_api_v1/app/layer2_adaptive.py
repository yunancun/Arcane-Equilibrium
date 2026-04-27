from __future__ import annotations

"""
Layer 2 AI Reasoning Engine — Adaptive Budget Sibling / 自適應預算姊妹模組
G3-08 Phase 4 Method A 拆分（layer2_cost_tracker.py 930→~480 LOC）。

MODULE_NOTE (中文):
  本模組從 ``layer2_cost_tracker.py`` 抽出「自適應預算 + cost_edge_ratio」
  3 個方法，重構為 module-level functions，第一參數統一
  ``tracker: 'Layer2CostTracker'``。原主檔以 1-line delegator 委派至此。

  涵蓋範圍：
  - recalculate_adaptive：根據 7d ROI 動態調整 multiplier（受 hard_cap 限）
  - get_adaptive_state：回傳當前 AdaptiveBudgetState 值物件
  - get_cost_edge_ratio：paper_pnl / ai_spend ROI 比率（含原則 10
    cognitive honesty markers）

  G3-09 future hook：
  此 sibling 是 cost_edge_ratio threshold check / cap binding 演算法後續實裝
  落點 — 預期 G3-09 將在此檔加入 +50-100 LOC（threshold 檢查 + 自動關倉
  建議邏輯）。

MODULE_NOTE (English):
  This sibling extracts the "adaptive budget + cost_edge_ratio" path —
  3 methods from ``layer2_cost_tracker.py`` — and rewrites them as
  module-level functions whose first argument is uniformly
  ``tracker: 'Layer2CostTracker'``. Original methods become 1-line
  delegators forwarding to these functions.

  Scope:
  - recalculate_adaptive: dynamic multiplier from 7d ROI (clamped to
    hard_cap)
  - get_adaptive_state: snapshot of current AdaptiveBudgetState
  - get_cost_edge_ratio: paper_pnl / ai_spend ROI with principle-10
    cognitive honesty markers

  G3-09 future hook:
  This sibling is the planned landing site for the cost_edge_ratio
  threshold-check / cap-binding algorithm (G3-09); expect ~+50-100 LOC
  here when G3-09 ships (threshold gate + auto-close-position
  recommendation logic).
"""

import datetime
import time
from typing import TYPE_CHECKING

from .layer2_types import (
    ADAPTIVE_MIN_DAYS,
    ADAPTIVE_TIERS,
    AdaptiveBudgetState,
)

if TYPE_CHECKING:
    from .layer2_cost_tracker import Layer2CostTracker


# ═══════════════════════════════════════════════════════════════════════════════
# Adaptive Budget / 自適應預算
# ═══════════════════════════════════════════════════════════════════════════════

def recalculate_adaptive(tracker: "Layer2CostTracker") -> AdaptiveBudgetState:
    """
    Recalculate adaptive budget multiplier based on 7-day AI ROI.
    根據近 7 天 AI ROI 重算自適應預算倍率。

    SAFETY / 不變量：
    - 取 ``tracker._lock`` 保證 ``tracker._adaptive`` 原子性替換（atomic
      swap，非 partial mutation）。下游 ``get_h5_snapshot`` 不取鎖讀
      ``_adaptive`` 依賴此原子契約 — Sub-task 3-3 RFC §6 + §8.2 thread
      safety。
    - multiplier 受 ``adaptive_min_multiplier`` / ``adaptive_max_multiplier``
      雙端 clamp，effective_daily_budget 不可超過 ``daily_hard_cap_usd``
      （原則 #5 生存 > 利潤）。

    SAFETY: ``tracker._lock`` is held for the full window so
    ``tracker._adaptive`` is replaced atomically (no partial mutation
    visible to lock-free readers). ``get_h5_snapshot`` reads ``_adaptive``
    without taking the lock and depends on this atomicity — Sub-task 3-3
    RFC §6 + §8.2 thread safety. Multiplier is clamped to
    ``[adaptive_min_multiplier, adaptive_max_multiplier]`` and
    ``effective_daily_budget`` is capped by ``daily_hard_cap_usd``
    (principle #5 survival > profit).
    """
    with tracker._lock:
        raw = tracker._read_raw()
        daily_spend = raw.get("daily_spend", {})
        sessions = raw.get("sessions", [])

        today = datetime.date.today()
        seven_days_ago_dt = datetime.datetime.combine(
            today - datetime.timedelta(days=7),
            datetime.time(),
            tzinfo=datetime.timezone.utc,
        )
        seven_days_ago_ms = int(seven_days_ago_dt.timestamp()) * 1000

        # Sum AI spend for last 7 days
        # 累計近 7 天的 AI 花費
        ai_spend_7d = 0.0
        data_days = 0
        for i in range(7):
            day_key = (today - datetime.timedelta(days=i)).isoformat()
            day_data = daily_spend.get(day_key, {})
            day_total = day_data.get("total_usd", 0.0)
            if day_total > 0:
                data_days += 1
            ai_spend_7d += day_total

        # Sum paper PnL from sessions in last 7 days
        # 累計近 7 天 sessions 的 paper PnL
        paper_pnl_7d = 0.0
        for s in sessions:
            created = s.get("created_at_ms", 0)
            if created < seven_days_ago_ms:
                break  # sessions are sorted most-recent-first
            attr = s.get("pnl_attribution") or {}
            paper_pnl_7d += attr.get("realized_pnl_usd", 0.0)

        # Calculate ROI / 計算 ROI
        roi_7d: float | None = None
        multiplier = 1.0

        if data_days >= ADAPTIVE_MIN_DAYS and ai_spend_7d > 0:
            roi_7d = round(paper_pnl_7d / ai_spend_7d, 4)
            for threshold, mult in ADAPTIVE_TIERS:
                if roi_7d >= threshold:
                    multiplier = mult
                    break

        # Clamp multiplier / 雙端裁剪倍率
        multiplier = max(
            tracker._config.adaptive_min_multiplier,
            min(tracker._config.adaptive_max_multiplier, multiplier),
        )

        effective = round(tracker._config.adaptive_base_daily_usd * multiplier, 2)
        # Never exceed hard cap / 永不超過硬上限
        effective = min(effective, tracker._config.daily_hard_cap_usd)

        tracker._adaptive = AdaptiveBudgetState(
            multiplier=multiplier,
            effective_daily_budget_usd=effective,
            roi_7d=roi_7d,
            ai_spend_7d_usd=round(ai_spend_7d, 4),
            paper_pnl_7d_usd=round(paper_pnl_7d, 4),
            data_days=data_days,
            last_recalculated_ms=int(time.time() * 1000),
        )
        tracker._save()
        return tracker._adaptive


def get_adaptive_state(tracker: "Layer2CostTracker") -> AdaptiveBudgetState:
    """Return current AdaptiveBudgetState value object / 回傳當前自適應狀態值物件"""
    return tracker._adaptive


# ═══════════════════════════════════════════════════════════════════════════════
# Cost Edge Ratio / 成本效益比
# ═══════════════════════════════════════════════════════════════════════════════

def get_cost_edge_ratio(tracker: "Layer2CostTracker") -> dict:
    """
    Calculate AI cost-to-edge ratio for the current session.
    計算當前 session 的 AI 成本效益比（cost_edge_ratio）。

    cost_edge_ratio = paper_pnl_7d_usd / ai_spend_7d_usd (when data is available).
    cost_edge_ratio = 7 日模擬 PnL / 7 日 AI 花費（數據充足時計算）。

    All values are based on paper simulation PnL — not real trading results.
    所有數值基於模擬 PnL，非真實交易結果。原則 10：認知誠實。

    Returns dict with roi_basis marker per principle 10 (cognitive honesty).
    返回含 roi_basis 標記的字典，符合根原則 10（認知誠實）要求。

    If insufficient data (< ADAPTIVE_MIN_DAYS), ratio is None.
    若數據不足（< ADAPTIVE_MIN_DAYS 天），比率返回 None。

    G3-09 hook：本函式回傳的 ``cost_edge_ratio`` 是 G3-09 cost_edge
    threshold check / cap binding 預定 input；G3-09 將在本 sibling
    新增 ~50-100 LOC（gate logic + 自動關倉建議）。
    G3-09 hook: ``cost_edge_ratio`` returned here is the planned input
    for the G3-09 threshold check / cap binding algorithm; G3-09 will
    add ~50-100 LOC in this sibling (gate logic + auto-close
    recommendation).
    """
    state = tracker._adaptive
    ai_spend = state.ai_spend_7d_usd
    paper_pnl = state.paper_pnl_7d_usd
    data_days = state.data_days

    if data_days >= ADAPTIVE_MIN_DAYS and ai_spend > 0:
        ratio = round(paper_pnl / ai_spend, 4)
    else:
        ratio = None

    return {
        "cost_edge_ratio": ratio,
        "ai_spend_7d_usd": ai_spend,
        "paper_pnl_7d_usd": paper_pnl,
        "data_days": data_days,
        # Principle 10 (cognitive honesty): all ROI data is paper simulation only
        # 根原則 10（認知誠實）：所有 ROI 數據均基於模擬，非真實盈虧
        "roi_basis": "paper_simulation_only",
        "roi_disclaimer": "基於模擬 PnL，非真實盈虧",
    }
