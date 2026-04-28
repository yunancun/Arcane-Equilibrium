"""
Analyst Pattern Claims — Pattern claim registration helpers
============================================================
Sibling extracted from ``analyst_agent.py`` (G3-08-FUP-ANALYST-SPLIT P2,
2026-04-28) to keep ``analyst_agent.py`` under §九 800 LOC warning line.

MODULE_NOTE (中文):
  本模組存放 AnalystAgent 用於將模式洞察登記到 TruthSourceRegistry 與
  ExperimentLedger 的純函式 helpers，原 ``_register_pattern_claims`` /
  ``_record_pattern_observations`` / ``_extract_strategy_from_pattern`` 邏輯
  100% 搬遷，無行為變更。

  關鍵設計（與原 instance method 對齊）：
  - ``KNOWN_STRATEGIES``：已知策略名 frozenset，原 ``_KNOWN_STRATEGIES``
  - ``extract_strategy_from_pattern(pattern_text)``：從文本提取策略 key，
    永不返回 ``"all"``（避免 StrategistAgent 靜默跳過）
  - ``register_pattern_claims(...)``：登記贏/輸模式到 truth_registry +
    向 experiment_ledger 記錄觀測；fail-open（log 警告不向上拋）
  - ``record_pattern_observations(...)``：對每個活躍假設記錄
    supporting/refuting outcome；fail-open

  AnalystAgent.__init__ 中保留：``_KNOWN_STRATEGIES = KNOWN_STRATEGIES`` 別名
  以維持 class-level 屬性 BWD-compat（原始程式 frozenset 為 class attr）。

  原則 7 不變：所有操作僅及學習平面（TruthSourceRegistry + ExperimentLedger），
  不影響 live 交易決策。

MODULE_NOTE (English):
  Pattern claim registration helpers extracted from ``analyst_agent.py``
  (G3-08-FUP-ANALYST-SPLIT P2, 2026-04-28). The original
  ``_register_pattern_claims`` / ``_record_pattern_observations`` /
  ``_extract_strategy_from_pattern`` logic is migrated 1:1 with zero
  behaviour change.

  Key design (mirrors original instance methods):
  - ``KNOWN_STRATEGIES``: frozenset of recognised strategy names (was
    class-level ``_KNOWN_STRATEGIES``)
  - ``extract_strategy_from_pattern(pattern_text)``: extract strategy key
    from pattern text, never returning ``"all"`` (which StrategistAgent
    silently skips)
  - ``register_pattern_claims(...)``: register winning/losing patterns to
    truth_registry + record observations to experiment_ledger; fail-open
    (logs warnings, never raises)
  - ``record_pattern_observations(...)``: record supporting/refuting
    outcome for every active hypothesis; fail-open

  AnalystAgent retains ``_KNOWN_STRATEGIES = KNOWN_STRATEGIES`` class-level
  alias to preserve attribute BWD-compat (original code exposed it as a
  class attribute).

  Principle 7 invariant: all operations touch the learning plane only
  (TruthSourceRegistry + ExperimentLedger); live trading decisions
  unaffected.
"""

from __future__ import annotations

import logging
import re as _re
from typing import Any, Optional


_default_logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy extraction / 策略名提取
# ═══════════════════════════════════════════════════════════════════════════════

# 已知策略名稱清單，供從 pattern_text 中提取策略名使用
# Known strategy names used to extract applies_to_strategy from pattern_text
KNOWN_STRATEGIES = frozenset([
    "ma_crossover", "grid", "bb_reversion", "bb_breakout", "funding_arb",
])


def extract_strategy_from_pattern(pattern_text: str) -> str:
    """
    Extract a strategy key from pattern text for use as applies_to_strategy.
    從 pattern 文字中提取策略 key，作為 applies_to_strategy 使用。

    Priority:
      1. If a known strategy name appears in the text, return it directly.
      2. Otherwise, derive a stable slug from the first 40 chars of pattern_text.
         This ensures registration still happens (total_registered > 0) while
         never injecting "all" which is silently skipped by StrategistAgent.

    優先順序：
      1. 如果文字包含已知策略名，直接返回。
      2. 否則，從 pattern_text 前 40 字元衍生穩定 slug，確保聲明能被登記。
         絕不回退到 "all"，因為 StrategistAgent._apply_pattern_insight() 明確跳過
         applies_to_strategy=="all" 的聲明，會導致所有聲明靜默丟失。

    StrategistAgent._strategy_preference_weights 使用 .get(strategy, 1.0) 回退，
    因此未知的 slug key 完全安全，不會崩潰。
    StrategistAgent uses .get(strategy, 1.0) fallback, so an unknown slug key
    is completely safe and won't cause any errors.
    """
    lower = pattern_text.lower()
    # 優先：從已知策略名中匹配 / Priority: match against known strategy names
    for strategy in KNOWN_STRATEGIES:
        if strategy in lower:
            return strategy
    # 回退：從前 40 字元衍生穩定 slug（去掉空格/特殊字元，轉小寫）
    # Fallback: derive a stable slug from first 40 chars (strip spaces/special chars, lowercase)
    slug = _re.sub(r"[^a-z0-9_]", "_", lower[:40]).strip("_")
    # 確保 slug 非空且不等於 "all" / Ensure slug is non-empty and not "all"
    return slug if slug and slug != "all" else "generic_pattern"


# ═══════════════════════════════════════════════════════════════════════════════
# Pattern claim registration / 模式聲明登記
# ═══════════════════════════════════════════════════════════════════════════════

def register_pattern_claims(
    *,
    insight: Any,
    n_obs: int,
    truth_registry: Optional[Any],
    experiment_ledger: Optional[Any],
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Register winning/losing patterns from insight into TruthSourceRegistry.
    將洞察中的贏/輸模式登記到知識登記表。

    - winning_patterns: registered with confidence derived from observation count.
      贏模式：置信度由觀察數推算。
    - losing_patterns: registered with inverted confidence (fixed 0.4) and
      "losing: " prefix so StrategistAgent can identify them as negative signals.
      輸模式：反轉置信度（固定 0.4），加 "losing: " 前綴，讓 StrategistAgent 識別為負向信號。
    - applies_to_strategy is extracted via extract_strategy_from_pattern(); this fn
      never returns "all" to avoid silent skip in StrategistAgent._apply_pattern_insight().
      applies_to_strategy 通過 extract_strategy_from_pattern() 提取，
      該函式永不返回 "all"，避免 StrategistAgent 靜默跳過所有聲明。

    Fail-open: any error → log warning, never raises.
    失敗開放：任何異常 → 記錄警告，不向上拋出。

    Args:
        insight: PatternInsight with .winning_patterns / .losing_patterns lists
        n_obs: Total observation count (used to derive winning confidence)
        truth_registry: TruthSourceRegistry instance or None (skip registry path)
        experiment_ledger: ExperimentLedger instance or None (skip ledger path)
        logger: optional logger; falls back to module logger when None
    """
    log = logger or _default_logger
    try:
        # 置信度上限 0.85（原則 7：AI 輸出永遠不是 FACT）
        # Confidence capped at 0.85 (Principle 7: AI output is never FACT)
        win_confidence = min(0.85, 0.5 + n_obs * 0.001)

        # ── 贏模式登記到 TruthSourceRegistry / Register winning patterns to TruthSourceRegistry ──
        # registry 未注入時跳過此區塊，但後面的 ExperimentLedger 記錄仍會執行
        # Skip this block when registry is not injected; ExperimentLedger recording still runs
        if truth_registry is not None:
            for pattern_text in (getattr(insight, "winning_patterns", None) or []):
                pt_str = str(pattern_text)
                # 提取策略 key；extract_strategy_from_pattern 永不返回 "all"
                # Extract strategy key; extract_strategy_from_pattern never returns "all"
                strategy = extract_strategy_from_pattern(pt_str)
                truth_registry.register_claim(
                    pattern_text=pt_str,
                    evidence_source="ai",
                    observation_count=n_obs,
                    confidence=win_confidence,
                    applies_to_regime="all",
                    applies_to_strategy=strategy,
                )

        # 向 ExperimentLedger 記錄贏模式觀測（fail-open，獨立於 truth_registry）
        # Record winning pattern observations to ExperimentLedger (fail-open, independent of truth_registry)
        if experiment_ledger is not None:
            record_pattern_observations(
                experiment_ledger=experiment_ledger,
                insight=insight,
                is_winning=True,
                logger=log,
            )

        # ── 輸模式登記到 TruthSourceRegistry / Register losing patterns to TruthSourceRegistry ──
        # 置信度反轉：輸模式固定使用低置信度 0.4，讓 StrategistAgent 降低對應策略偏好
        # Confidence inverted: losing patterns use fixed low confidence 0.4
        # so StrategistAgent reduces preference for those strategies
        losing_confidence = 0.4
        if truth_registry is not None:
            for pattern_text in (getattr(insight, "losing_patterns", None) or []):
                pt_str = str(pattern_text)
                # 提取策略 key，不使用 "all"
                # Extract strategy key, never "all"
                strategy = extract_strategy_from_pattern(pt_str)
                # 加 "losing: " 前綴，讓 StrategistAgent._apply_pattern_insight() 識別為負向信號
                # Prefix with "losing: " so StrategistAgent identifies it as a negative signal
                truth_registry.register_claim(
                    pattern_text=f"losing: {pt_str}",
                    evidence_source="ai",
                    observation_count=n_obs,
                    confidence=losing_confidence,
                    applies_to_regime="all",
                    applies_to_strategy=strategy,
                )

        # 向 ExperimentLedger 記錄輸模式觀測（fail-open，獨立於 truth_registry）
        # Record losing pattern observations to ExperimentLedger (fail-open, independent of truth_registry)
        if experiment_ledger is not None:
            record_pattern_observations(
                experiment_ledger=experiment_ledger,
                insight=insight,
                is_winning=False,
                logger=log,
            )

    except Exception as e:
        log.warning("register_pattern_claims failed (fail-open): %s", e)


def record_pattern_observations(
    *,
    experiment_ledger: Any,
    insight: Any,
    is_winning: bool,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    根據分析結果向 ExperimentLedger 記錄觀測。
    Record pattern analysis observations to ExperimentLedger.

    winning patterns → outcome="supporting"
    losing patterns  → outcome="refuting"

    fail-open：單條失敗不傳播，繼續記錄其餘假設。
    fail-open: single failure does not propagate; continue recording other hypotheses.

    原則 7：本方法僅操作學習平面（ExperimentLedger），不影響交易決策。
    Principle 7: This function only operates on the learning plane (ExperimentLedger),
    and does not affect trading decisions.

    Args:
        experiment_ledger: ExperimentLedger instance (caller has verified non-None)
        insight: PatternInsight object from L2 analysis / L2 分析產生的模式洞察對象
        is_winning: True for winning patterns (supporting), False for losing (refuting)
                    True 表示贏模式（支持），False 表示輸模式（反駁）
        logger: optional logger; falls back to module logger when None
    """
    log = logger or _default_logger
    # 根據贏/輸確定 outcome 字串 / Determine outcome string based on win/loss
    outcome = "supporting" if is_winning else "refuting"
    try:
        # 取所有活躍假設（PENDING / RUNNING 狀態）/ Get all active (non-concluded) hypotheses
        all_hyps = experiment_ledger.get_all_hypotheses()
        for hyp in all_hyps:
            # 只對尚未結案的假設記錄觀測 / Only record for non-concluded hypotheses
            if hyp.status.value in ("PENDING", "RUNNING"):
                try:
                    experiment_ledger.record_observation(hyp.hypothesis_id, outcome)
                except Exception as e:
                    # fail-open：跳過此假設，繼續處理其餘 / fail-open: skip this hypothesis
                    log.debug(
                        "ExperimentLedger record_observation skipped hyp=%s: %s",
                        hyp.hypothesis_id, e,
                    )
    except Exception as e:
        # fail-open：不阻塞分析路徑 / fail-open: do not block the analysis path
        log.warning("record_pattern_observations failed (fail-open): %s", e)
