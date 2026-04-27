"""
Batch 7 — StrategistAgent Weight Management Sibling
====================================================
Governance refs: EX-06 §4 / CLAUDE.md §九 file-size discipline / G3-08 Phase 4

MODULE_NOTE (中文):
  本模組是 StrategistAgent 的 sibling，承載「策略偏好權重」與「外部依賴注入」
  相關的 6 個方法，從 strategist_agent.py 拆出以維持主檔在 §九 800 行警告線之下。
  函數一律接受 ``agent: StrategistAgent`` 作為第一個參數。

  涵蓋方法：
  1. set_budget_manager — APIBudgetManager 注入 + ModelRouter budget_checker wiring
  2. set_truth_registry — TruthSourceRegistry 注入（原則 7：知識隔離）
  3. _apply_pattern_insight — 模式洞察 → 策略權重微調（±0.1×conf, clamp [0.2, 2.0]）
  4. get_strategy_weight — 0A-1 接口：策略名 → 偏好權重（normalize + variants 查找）
  5. _apply_regime_weights — C4 regime 感知策略偏好倍率（reset+apply 防漂移）
  6. _apply_l2_weight_update — L2 評估完成後權重更新（±0.15×conf, clamp [0.2, 2.0]）

MODULE_NOTE (English):
  StrategistAgent sibling carrying 6 methods around "strategy preference weights"
  and "external dependency injection". Extracted from strategist_agent.py so the
  main file stays under the §九 800-line warning threshold.
  Functions take ``agent: StrategistAgent`` as the first parameter.

  Covered methods:
  1. set_budget_manager — inject APIBudgetManager + wire ModelRouter budget_checker
  2. set_truth_registry — inject TruthSourceRegistry (principle 7: knowledge isolation)
  3. _apply_pattern_insight — pattern insight → weight tweak (±0.1×conf, clamp [0.2, 2.0])
  4. get_strategy_weight — 0A-1 API: strategy name → preference weight
                           (normalize + variants lookup)
  5. _apply_regime_weights — C4 regime-aware preference multipliers
                             (reset+apply to prevent drift)
  6. _apply_l2_weight_update — weight update after L2 evaluation
                                (±0.15×conf, clamp [0.2, 2.0])

Hard boundaries (CLAUDE.md §四):
  - Weight clamp [0.2, 2.0] 不變 (unchanged); fail-open semantics 保留 (preserved).
  - 不變動業務邏輯，只搬位置 (no business-logic change, location-only refactor).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .strategist_models import EdgeEvaluation

if TYPE_CHECKING:  # pragma: no cover — type-checker only / 僅型別檢查
    from .strategist_agent import StrategistAgent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# External dependency injection / 外部依賴注入
# ─────────────────────────────────────────────────────────────────────────────

def set_budget_manager(agent: "StrategistAgent", budget_manager: Any) -> None:
    """
    Inject APIBudgetManager for L1.5/L2 budget checking.
    注入 APIBudgetManager 用於 L1.5/L2 預算檢查。

    Wires up a lambda budget_checker into ModelRouter so that route() can gate
    L1.5/L2 upgrades based on remaining API budget.
    將 lambda 預算檢查器接入 ModelRouter，使 route() 可根據剩餘
    API 預算閘控 L1.5/L2 升級。
    """
    agent._budget_manager = budget_manager
    agent._model_router.set_budget_checker(
        lambda tier: budget_manager.can_call(tier)
    )
    logger.info("APIBudgetManager injected into StrategistAgent / API 預算管理器已注入")


def set_truth_registry(agent: "StrategistAgent", registry: Any) -> None:
    """
    Inject TruthSourceRegistry for pattern-driven strategy weight updates.
    注入知識登記表，供模式洞察更新策略偏好權重使用。

    Principle 7: registry only influences recommendation weights, never modifies
    strategy parameters or risk thresholds directly.
    原則 7：登記表只影響建議權重，不直接修改策略參數或風控閾值。
    """
    agent._truth_registry = registry


# ─────────────────────────────────────────────────────────────────────────────
# Pattern insight → weight update / 模式洞察 → 權重更新
# ─────────────────────────────────────────────────────────────────────────────

def _apply_pattern_insight(agent: "StrategistAgent", insight_payload: dict) -> None:
    """
    Apply pattern insight to update strategy preference weights.
    將模式洞察應用到策略偏好權重更新。

    Queries active claims from registry, adjusts weights by ±0.1 × confidence,
    clamped to [0.2, 2.0]. Fail-open: any error → log warning, leave weights unchanged.
    從登記表查詢有效聲明，按 ±0.1×信度調整權重，限幅 [0.2, 2.0]。
    失敗開放：任何異常 → 記錄警告，不改變現有權重。
    """
    if agent._truth_registry is None:
        return
    try:
        claims = agent._truth_registry.get_active_claims(
            regime=None, min_confidence=0.5
        )
        for claim in claims:
            strategy = claim.applies_to_strategy
            if strategy == "all":
                continue
            current = agent._strategy_preference_weights.get(strategy, 1.0)
            delta = 0.1 * claim.confidence
            if "losing" in claim.pattern_text.lower():
                delta = -delta
            new_weight = max(0.2, min(2.0, current + delta))
            agent._strategy_preference_weights[strategy] = new_weight
    except Exception as e:
        logger.warning("_apply_pattern_insight failed (fail-open): %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# Strategy weight lookup / 策略權重查找
# ─────────────────────────────────────────────────────────────────────────────

def get_strategy_weight(agent: "StrategistAgent", strategy_name: str) -> float:
    """
    0A-1: Return the current preference weight for a strategy.
    返回某策略的當前偏好權重。

    Used by PipelineBridge to apply learning feedback to strategy signals.
    Normalizes strategy name for lookup (strips symbol suffix, lowercases).
    供 PipelineBridge 在策略信號上應用學習反饋。
    對策略名稱標準化（去除 symbol 後綴，小寫化）。

    Args:
        strategy_name: Strategy identifier (e.g. "MACrossover_BTCUSDT" or "ma_crossover").

    Returns:
        Weight in [0.2, 2.0]. Default 1.0 (neutral) if no pattern data.
    """
    # Normalize: strip symbol suffix (e.g. "MACrossover_BTCUSDT" → "macrossover")
    # 標準化：去除 symbol 後綴
    base_name = strategy_name.split("_")[0].lower() if strategy_name else ""
    # Also try common name mappings / 嘗試常見名稱映射
    name_variants = [
        strategy_name,
        base_name,
        strategy_name.lower(),
    ]
    with agent._lock:
        for variant in name_variants:
            w = agent._strategy_preference_weights.get(variant)
            if w is not None:
                return w
    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Regime-aware weight reset / Regime 感知權重重置
# ─────────────────────────────────────────────────────────────────────────────

def _apply_regime_weights(agent: "StrategistAgent", regime: str) -> None:
    """
    C4: Apply regime-aware strategy preference multipliers.
    C4: 應用 regime 感知策略偏好倍率。

    Resets all weights to 1.0 then applies new regime multipliers to prevent
    oscillation drift from repeated multiply→clamp cycles.
    重置所有權重為 1.0 再應用新 regime 倍率，防止反覆 multiply→clamp 漂移。
    """
    agent._current_regime = regime
    prefs = agent._REGIME_STRATEGY_PREFERENCES.get(regime, {})
    if not prefs:
        return

    try:
        with agent._lock:
            for key in agent._strategy_preference_weights:
                agent._strategy_preference_weights[key] = 1.0
            for strategy_name, multiplier in prefs.items():
                new_weight = max(0.2, min(2.0, multiplier))
                agent._strategy_preference_weights[strategy_name] = new_weight
        logger.debug(
            "C4: Regime weights applied for regime=%s: %s / "
            "Regime 權重已應用：regime=%s",
            regime, prefs, regime,
        )
    except Exception as e:
        logger.warning("_apply_regime_weights failed (fail-open): %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# L2 callback weight update / L2 回調權重更新
# ─────────────────────────────────────────────────────────────────────────────

def _apply_l2_weight_update(
    agent: "StrategistAgent",
    intel: Any,
    evaluation: EdgeEvaluation,
) -> None:
    """
    Update strategy preference weights based on high-confidence L2 evaluation.
    根據高信心 L2 評估更新策略偏好權重。

    Called by ModelRouter as weight_update_fn callback when L2 result has
    has_edge=True and confidence >= 0.6. Weight adjustment ±0.15, clamped [0.2, 2.0].
    由 ModelRouter 作為 weight_update_fn 回調調用。權重調整 ±0.15，限幅 [0.2, 2.0]。
    """
    try:
        for symbol in getattr(intel, "symbols", []):
            strategy_key = f"ai_{symbol}"
            with agent._lock:
                current = agent._strategy_preference_weights.get(strategy_key, 1.0)
                delta = 0.15 * evaluation.confidence if evaluation.has_edge else -0.1
                new_weight = max(0.2, min(2.0, current + delta))
                agent._strategy_preference_weights[strategy_key] = new_weight
                agent._stats["l2_cache_weight_applied"] += 1
            logger.debug(
                "L2 weight update for %s: %.2f → %.2f (delta=%.3f) / "
                "L2 權重更新：%.2f → %.2f",
                strategy_key, current, new_weight, delta, current, new_weight,
            )
    except Exception as e:
        logger.warning("_apply_l2_weight_update failed (fail-open): %s", e)
