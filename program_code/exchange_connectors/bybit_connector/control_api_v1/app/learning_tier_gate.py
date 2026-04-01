"""
Learning Capability Tiered Gating L1–L5 / 学习能力分级门控 L1–L5

MODULE_NOTE (中文):
  本模块实现 EX-05 §3 / GAP-M3 / DOC-04 §6 要求的 Analyst Agent 进化引擎 L1–L5：
  - L1 复盘 (Post-Trade Review): 被动记录交易观察和基础指标计算
  - L2 模式发现 (Pattern Discovery): 跨策略性能对比、成本归因、异常检测
  - L3 假说实验 (Hypothesis & Experiment): 从 L2 模式生成假说、设计纸上交易实验
  - L4 策略进化 (Strategy Evolution): 进化策略参数、创建新策略变体、跨策略迁移学习
  - L5 元学习 (Meta-Learning): 优化学习管线自身、发现分析方法盲点、自我校准

  核心安全不变量：
  - L1 可以被动记录观察，无费用
  - L2 需要 500+ 观察 + 胜率 > 20% 才能解锁
  - L3 需要 L2 运行 2+ 周 + 3+ 已确认模式
  - L4 需要 3+ 来自 L3 的已验证假说 + 正实验 ROI
  - L5 需要 6+ 月运营数据 + 持续正实绩 + Operator 显式批准
  - 进化是单向的：L1 → L2 → L3 → L4 → L5（可演进但不能降级）
  - 每次晋升生成 learning_tier_promotion 审计对象
  - 线程安全，审计回调，导入导出序列化

MODULE_NOTE (English):
  Implements Analyst Agent evolution engine L1–L5 per EX-05 §3 / GAP-M3 / DOC-04 §6:
  - L1 Post-Trade Review: passive observation recording and basic metrics
  - L2 Pattern Discovery: cross-strategy comparison, cost attribution, anomaly detection
  - L3 Hypothesis & Experiment: hypothesis generation from L2, paper trading experiments
  - L4 Strategy Evolution: parameter evolution, new strategy variants, cross-strategy transfer
  - L5 Meta-Learning: optimize the learning pipeline itself, identify blind spots, self-calibrate

  Core safety invariants:
  - L1 can passively record observations at zero cost
  - L2 unlocks at 500+ observations + win_rate > 20%
  - L3 unlocks after L2 running 2+ weeks + 3+ confirmed patterns
  - L4 unlocks with 3+ validated hypotheses from L3 + positive experiment ROI
  - L5 unlocks at 6+ months operational data + sustained positive live performance + explicit Operator approval
  - Evolution is unidirectional: L1 → L2 → L3 → L4 → L5 (can evolve but not downgrade)
  - Each promotion emits a learning_tier_promotion audit object
  - Thread-safe, audit callback, import/export serialization
"""

from __future__ import annotations

import copy
import hashlib
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Learning Tiers / 学习等级
# ═══════════════════════════════════════════════════════════════════════════════

class LearningTier(IntEnum):
    """
    Five-level Analyst evolution scale per EX-05 §3.
    EX-05 §3 定义的五级 Analyst 进化等级。

    L1 (Post-Trade Review):
      - Passive observation recording (fully automatic, zero cost per EX-05 §3.1)
      - Compute basic metrics: win rate, Sharpe, max drawdown, avg holding time
      - Tag observations with regime, strategy, instrument, session
      - Identify obvious patterns (time-of-day effects, strategy-instrument mismatch)

    L2 (Pattern Discovery):
      - Unlocks at: 500+ observations + win_rate > 20% (EX-05 §3.2)
      - Cross-strategy performance comparison
      - Regime-specific strategy ranking
      - Cost attribution analysis
      - Correlation discovery, anomaly detection
      - Computation: L1 (local Ollama, EX-05 §3.2 表)

    L3 (Hypothesis & Experiment):
      - Unlocks at: L2 running 2+ weeks + 3+ confirmed patterns (EX-05 §3.3)
      - Generate testable hypotheses from L2 patterns
      - Design controlled experiments in Paper Trading
      - Statistical validation
      - Experiment lifecycle: proposed → approved → running → completed → verdict

    L4 (Strategy Evolution):
      - Unlocks at: 3+ validated hypotheses from L3 + positive experiment ROI (EX-05 §3.4)
      - Evolve strategy parameters based on L3 results
      - Create new strategy variants
      - Cross-strategy transfer learning
      - Regime transition prediction
      - Strategy incubation: auto-deploy promising variants to Paper Trading

    L5 (Meta-Learning):
      - Unlocks at: 6+ months operational data + sustained positive live performance
        + explicit Operator approval (EX-05 §3.5)
      - Learn how to learn better (optimize learning pipeline parameters)
      - Identify blind spots in Analyst's analysis methodology
      - Self-calibrate confidence levels based on historical accuracy
      - Propose improvements to observation, hypothesis, experiment design
      - Meta-hypothesis: hypotheses about the learning process itself
    """
    L1 = 1  # Post-Trade Review / 复盘
    L2 = 2  # Pattern Discovery / 模式发现
    L3 = 3  # Hypothesis & Experiment / 假说实验
    L4 = 4  # Strategy Evolution / 策略进化
    L5 = 5  # Meta-Learning / 元学习


# ═══════════════════════════════════════════════════════════════════════════════
# Promotion Events / 晋升事件
# ═══════════════════════════════════════════════════════════════════════════════

class PromotionEvent(str, Enum):
    """Formal events that trigger tier promotions / 触发等级晋升的正式事件"""
    AUTO_PROMOTE_L1_TO_L2 = "auto_promote_l1_to_l2"
    AUTO_PROMOTE_L2_TO_L3 = "auto_promote_l2_to_l3"
    AUTO_PROMOTE_L3_TO_L4 = "auto_promote_l3_to_l4"
    OPERATOR_APPROVE_L4_TO_L5 = "operator_approve_l4_to_l5"
    OPERATOR_PROMOTE_OVERRIDE = "operator_promote_override"


class PromotionInitiator(str, Enum):
    """Who can initiate tier promotions / 等级晋升发起者"""
    LEARNING_GATE = "LearningGate"
    OPERATOR = "Operator"


# ═══════════════════════════════════════════════════════════════════════════════
# Tier Eligibility Criteria / 等级资格条件
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TierEligibilityCriteria:
    """Defines eligibility gates for each learning tier / 定义每个学习等级的资格门控条件"""
    # L2: Pattern Discovery unlocks at 500+ observations + win_rate > 20%
    l2_min_observations: int = 500
    l2_min_win_rate: float = 0.20

    # L3: Hypothesis & Experiment unlocks at L2 running 2+ weeks + 3+ confirmed patterns
    l3_min_l2_runtime_days: int = 14
    l3_min_confirmed_patterns: int = 3

    # L4: Strategy Evolution unlocks at 3+ validated hypotheses from L3 + positive ROI
    l4_min_validated_hypotheses: int = 3
    l4_min_experiment_roi: float = 0.0  # Must be >= 0 (net positive)

    # L5: Meta-Learning unlocks at 6+ months operational + sustained live performance + Operator approval
    l5_min_operational_days: int = 180  # 6+ months
    l5_requires_operator_approval: bool = True
    l5_min_sustained_positive_days: int = 30  # 30 days sustained positive live performance

    def to_dict(self) -> dict[str, Any]:
        d = {}
        for k, v in self.__dict__.items():
            d[k] = v
        return d


# ═══════════════════════════════════════════════════════════════════════════════
# Tier Capability Restrictions / 等级能力限制
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TierCapabilities:
    """Capabilities and restrictions for each tier / 每个等级的能力和限制"""
    can_record_observations: bool = False
    can_discover_patterns: bool = False
    can_generate_hypotheses: bool = False
    can_design_experiments: bool = False
    can_evolve_strategies: bool = False
    can_propose_strategy_variants: bool = False
    can_propose_transfers: bool = False
    can_predict_regime_transition: bool = False
    can_optimize_learning_pipeline: bool = False
    can_auto_deploy_to_paper: bool = False
    can_modify_live_config: bool = False  # ALL tiers: NO (per EX-05 §8.2)
    description: str = ""


TIER_CAPABILITIES: dict[LearningTier, TierCapabilities] = {
    LearningTier.L1: TierCapabilities(
        can_record_observations=True,
        can_auto_deploy_to_paper=True,  # L1 can paper-trade to accumulate observations.
        # Paper trading IS the mechanism for building L1 observations; blocking it at L1
        # creates a chicken-and-egg problem: no paper trades → no observations → never
        # reaches L2 → never reaches L3 where paper was previously unlocked.
        # L1 的纸盘交易是积累观察数据的前提。L3 原有的 can_auto_deploy_to_paper 语义
        # 保留为"假说驱动的 paper 实验自动部署"，L1/L2 的语义是"正常纸盘交易积累观察"。
        description="Post-Trade Review: passive observation recording, basic metrics, paper trading / 复盘：被动记录观察、计算基础指标、纸盘交易",
    ),
    LearningTier.L2: TierCapabilities(
        can_record_observations=True,
        can_discover_patterns=True,
        can_auto_deploy_to_paper=True,  # Retained from L1; L2 continues paper trading
        # L2 保留纸盘交易能力；在此基础上新增模式发现能力
        description="Pattern Discovery: cross-strategy analysis, cost attribution, anomaly detection, paper trading / 模式发现：跨策略分析、成本归因、异常检测、纸盘交易",
    ),
    LearningTier.L3: TierCapabilities(
        can_record_observations=True,
        can_discover_patterns=True,
        can_generate_hypotheses=True,
        can_design_experiments=True,
        can_auto_deploy_to_paper=True,  # L3 adds hypothesis-driven experiment deployment
        # L3 新增语义：假说驱动的 paper 实验自动部署（原始设计意图）
        description="Hypothesis & Experiment: generate hypotheses, design paper experiments / 假说实验：生成假说、设计纸上实验",
    ),
    LearningTier.L4: TierCapabilities(
        can_record_observations=True,
        can_discover_patterns=True,
        can_generate_hypotheses=True,
        can_design_experiments=True,
        can_evolve_strategies=True,
        can_propose_strategy_variants=True,
        can_propose_transfers=True,
        can_predict_regime_transition=True,
        can_auto_deploy_to_paper=True,
        description="Strategy Evolution: parameter evolution, new variants, transfer learning, regime prediction / 策略进化：参数演进、新变体、迁移学习、制度转换预测",
    ),
    LearningTier.L5: TierCapabilities(
        can_record_observations=True,
        can_discover_patterns=True,
        can_generate_hypotheses=True,
        can_design_experiments=True,
        can_evolve_strategies=True,
        can_propose_strategy_variants=True,
        can_propose_transfers=True,
        can_predict_regime_transition=True,
        can_optimize_learning_pipeline=True,
        can_auto_deploy_to_paper=True,
        description="Meta-Learning: optimize learning pipeline, identify blind spots, self-calibrate / 元学习：优化学习管线、发现盲点、自我校准",
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Tier State / 等级状态
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TierState:
    """Snapshot of the Analyst's current learning tier state / Analyst 当前学习等级状态快照"""
    current_tier: LearningTier = LearningTier.L1
    tier_promoted_at_ms: int = 0
    observation_count: int = 0
    confirmed_patterns: int = 0
    validated_hypotheses: int = 0
    experiment_roi: float = 0.0
    win_rate: float = 0.0
    days_at_tier: int = 0
    days_operational: int = 0
    sustained_positive_live_days: int = 0
    last_promotion_event: str = ""
    last_promotion_initiator: str = ""
    last_promotion_reason: str = ""
    promotions: list[dict[str, Any]] = field(default_factory=list)
    version: int = 1

    def __post_init__(self) -> None:
        if not self.tier_promoted_at_ms:
            self.tier_promoted_at_ms = int(time.time() * 1000)


# ═══════════════════════════════════════════════════════════════════════════════
# Promotion Record / 晋升记录
# ═══════════════════════════════════════════════════════════════════════════════

def _build_promotion_record(
    state: TierState,
    to_tier: LearningTier,
    event: PromotionEvent,
    initiator: PromotionInitiator,
    reason_codes: list[str] | None = None,
    approved_by: str | None = None,
    metrics_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build learning_tier_promotion audit object / 构建学习等级晋升审计对象"""
    now_ms = int(time.time() * 1000)
    pid = f"ltp:{uuid.uuid4().hex[:12]}"
    return {
        "promotion_id": pid,
        "previous_tier": state.current_tier.name,
        "next_tier": to_tier.name,
        "trigger_event": event.value,
        "trigger_event_id": f"levt:{uuid.uuid4().hex[:8]}",
        "initiated_by": initiator.value,
        "reason_codes": reason_codes or [],
        "approved_by": approved_by,
        "effective_at_ms": now_ms,
        "days_at_previous_tier": state.days_at_tier,
        "metrics_snapshot": metrics_snapshot or {
            "observation_count": state.observation_count,
            "win_rate": state.win_rate,
            "confirmed_patterns": state.confirmed_patterns,
            "validated_hypotheses": state.validated_hypotheses,
            "experiment_roi": state.experiment_roi,
            "days_operational": state.days_operational,
            "sustained_positive_live_days": state.sustained_positive_live_days,
        },
        "audit_event_ref": f"laud:{hashlib.sha256(pid.encode()).hexdigest()[:16]}",
        "version_before": state.version,
        "version_after": state.version + 1,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Learning Tier Gate Error / 学习等级门控异常
# ═══════════════════════════════════════════════════════════════════════════════

class LearningTierGateError(Exception):
    """Raised when an invalid tier promotion is attempted / 非法等级晋升"""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Learning Tier Gate Engine / 学习等级门控引擎
# ═══════════════════════════════════════════════════════════════════════════════

class LearningTierGate:
    """
    Learning Capability Tiered Gating Engine (L1–L5) per EX-05 §3.

    Manages Analyst Agent evolution through five maturity levels. Each level unlocks
    new capabilities and requires demonstrated competence at the previous level before
    promotion. Thread-safe, audit-enabled, serializable.

    EX-05 §3 / GAP-M3 / DOC-04 §6 Implementation:
      Learning Pipeline: Observation → Lesson → Hypothesis → Experiment → Verdict
      Analyst Autonomy Boundaries (EX-05 §8):
        - Can autonomously: record observations, extract lessons, generate hypotheses,
          deploy experiments to Paper Trading, evaluate experiment results, recommend
          parameter adjustments, auto-deploy validated variants to paper
        - Cannot autonomously: modify live config, promote strategies without gate criteria,
          disable P0/P1 risk controls, delete/modify historical observations, override
          Guardian rejections, access execution systems, modify evolution level
        - Requires Operator approval: first-ever live deployment of new strategy type,
          changes to Paper→Live gate criteria, L5 meta-learning proposals
    """

    def __init__(
        self,
        criteria: TierEligibilityCriteria | None = None,
        audit_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._state = TierState()
        self._criteria = criteria or TierEligibilityCriteria()
        self._audit_callback = audit_callback
        self._l2_start_time_ms: int | None = None  # Track when L2 was unlocked

    # ── Properties ──

    @property
    def current_tier(self) -> LearningTier:
        """Get current learning tier / 获取当前学习等级"""
        with self._lock:
            return self._state.current_tier

    @property
    def capabilities(self) -> TierCapabilities:
        """Get capabilities for current tier / 获取当前等级的能力"""
        return TIER_CAPABILITIES[self.current_tier]

    @property
    def state(self) -> TierState:
        """Get current state snapshot / 获取当前状态快照"""
        with self._lock:
            return copy.deepcopy(self._state)

    # ── Update Metrics ──

    def update_metrics(
        self,
        observation_count: int | None = None,
        win_rate: float | None = None,
        confirmed_patterns: int | None = None,
        validated_hypotheses: int | None = None,
        experiment_roi: float | None = None,
        sustained_positive_live_days: int | None = None,
    ) -> None:
        """
        Update Analyst metrics for tier eligibility checking.
        更新 Analyst 指标以检查等级资格。

        Args:
            observation_count: Total observations accumulated
            win_rate: Current win rate (0.0 to 1.0)
            confirmed_patterns: Count of L2 patterns confirmed by data
            validated_hypotheses: Count of L3 hypotheses validated by experiments
            experiment_roi: Average ROI of experiments (e.g., 0.15 for +15%)
            sustained_positive_live_days: Days with net positive live performance
        """
        with self._lock:
            if observation_count is not None:
                self._state.observation_count = observation_count
            if win_rate is not None:
                self._state.win_rate = win_rate
            if confirmed_patterns is not None:
                self._state.confirmed_patterns = confirmed_patterns
            if validated_hypotheses is not None:
                self._state.validated_hypotheses = validated_hypotheses
            if experiment_roi is not None:
                self._state.experiment_roi = experiment_roi
            if sustained_positive_live_days is not None:
                self._state.sustained_positive_live_days = sustained_positive_live_days

    def update_operational_time(self, days_operational: int) -> None:
        """
        Update total operational time (for L5 gate which requires 6+ months).
        更新总运营时间（用于 L5 门控，需要 6+ 月）。
        """
        with self._lock:
            self._state.days_operational = days_operational

    # ── Tier Eligibility Checking ──

    def check_tier_eligibility(self, target_tier: LearningTier | None = None) -> tuple[bool, list[str]]:
        """
        Check if the Analyst is eligible for promotion to the next tier (or target tier).
        检查 Analyst 是否有资格晋升到下一个等级（或目标等级）。

        EX-05 §3.1–§3.5 defines unlock conditions for L1–L5.

        Returns:
            (eligible: bool, reason_codes: list[str])
            reason_codes contains gate failure reasons if not eligible

        Examples:
            L2 unlock: 500+ observations AND win_rate > 20%
            L3 unlock: L2 running 2+ weeks AND 3+ confirmed patterns
            L4 unlock: 3+ validated hypotheses AND positive experiment ROI
            L5 unlock: 6+ months operational AND sustained positive live performance AND Operator approval
        """
        with self._lock:
            return self._check_eligibility_unsafe(target_tier or self._next_tier(self._state.current_tier))

    def _check_eligibility_unsafe(self, target_tier: LearningTier) -> tuple[bool, list[str]]:
        """Internal eligibility check (caller holds lock) / 内部资格检查（调用者持有锁）"""
        current = self._state.current_tier
        reasons = []

        # Must promote sequentially: no skipping levels except via Operator override
        if target_tier <= current:
            reasons.append("target_tier_not_higher_than_current")
            return False, reasons

        if target_tier == LearningTier.L2 and current == LearningTier.L1:
            # L2 Gate: 500+ observations + win_rate > 20% (EX-05 §3.2)
            if self._state.observation_count < self._criteria.l2_min_observations:
                reasons.append(f"insufficient_observations:{self._state.observation_count}/{self._criteria.l2_min_observations}")
            if self._state.win_rate < self._criteria.l2_min_win_rate:
                reasons.append(f"low_win_rate:{self._state.win_rate:.2%}/{self._criteria.l2_min_win_rate:.2%}")
            return len(reasons) == 0, reasons

        elif target_tier == LearningTier.L3 and current == LearningTier.L2:
            # L3 Gate: L2 running 2+ weeks + 3+ confirmed patterns (EX-05 §3.3)
            if self._l2_start_time_ms is None:
                self._l2_start_time_ms = int(time.time() * 1000)
            l2_age_days = (int(time.time() * 1000) - self._l2_start_time_ms) / (1000 * 60 * 60 * 24)
            if l2_age_days < self._criteria.l3_min_l2_runtime_days:
                reasons.append(f"l2_too_new:{l2_age_days:.1f}/{self._criteria.l3_min_l2_runtime_days} days")
            if self._state.confirmed_patterns < self._criteria.l3_min_confirmed_patterns:
                reasons.append(f"insufficient_patterns:{self._state.confirmed_patterns}/{self._criteria.l3_min_confirmed_patterns}")
            return len(reasons) == 0, reasons

        elif target_tier == LearningTier.L4 and current == LearningTier.L3:
            # L4 Gate: 3+ validated hypotheses from L3 + positive experiment ROI (EX-05 §3.4)
            if self._state.validated_hypotheses < self._criteria.l4_min_validated_hypotheses:
                reasons.append(f"insufficient_hypotheses:{self._state.validated_hypotheses}/{self._criteria.l4_min_validated_hypotheses}")
            if self._state.experiment_roi < self._criteria.l4_min_experiment_roi:
                reasons.append(f"negative_roi:{self._state.experiment_roi:.2%}/{self._criteria.l4_min_experiment_roi:.2%}")
            return len(reasons) == 0, reasons

        elif target_tier == LearningTier.L5 and current == LearningTier.L4:
            # L5 Gate: 6+ months operational + sustained positive live performance + Operator approval (EX-05 §3.5)
            if self._state.days_operational < self._criteria.l5_min_operational_days:
                reasons.append(f"insufficient_operational_time:{self._state.days_operational}/{self._criteria.l5_min_operational_days} days")
            if self._state.sustained_positive_live_days < self._criteria.l5_min_sustained_positive_days:
                reasons.append(f"insufficient_positive_live_days:{self._state.sustained_positive_live_days}/{self._criteria.l5_min_sustained_positive_days} days")
            # L5 requires explicit Operator approval (cannot auto-promote)
            if self._criteria.l5_requires_operator_approval:
                reasons.append("requires_operator_approval")
            return len(reasons) == 0, reasons

        # Unknown transition
        reasons.append(f"invalid_transition:{current.name}→{target_tier.name}")
        return False, reasons

    @staticmethod
    def _next_tier(current: LearningTier) -> LearningTier:
        """Get the next tier in sequence / 获取顺序中的下一个等级"""
        tier_order = [LearningTier.L1, LearningTier.L2, LearningTier.L3, LearningTier.L4, LearningTier.L5]
        idx = tier_order.index(current)
        if idx < len(tier_order) - 1:
            return tier_order[idx + 1]
        return current

    # ── Tier Promotion ──

    def promote_tier(
        self,
        target_tier: LearningTier,
        initiator: str = "LearningGate",
        reason: str = "",
        approved_by: str | None = None,
    ) -> bool:
        """
        Promote Analyst to a target tier if eligibility criteria are met.
        如果满足资格条件，则晋升 Analyst 到目标等级。

        Sequential promotion is required: must go L1 → L2 → L3 → L4 → L5.
        Operator can override sequential requirement via approved_by parameter (for L5 promotion).

        Args:
            target_tier: Target learning tier
            initiator: "LearningGate" (automatic) or "Operator" (override)
            reason: Human-readable reason for promotion
            approved_by: Operator identifier if Operator-approved promotion

        Returns:
            True if promotion succeeded, False otherwise

        Emits:
            learning_tier_promotion audit object via audit_callback
        """
        with self._lock:
            eligible, reasons = self._check_eligibility_unsafe(target_tier)

            # Special case: L5 requires explicit Operator approval (reason must be "operator_approved_l5")
            if target_tier == LearningTier.L5 and not approved_by:
                logger.warning(
                    f"L5 promotion requires Operator approval. "
                    f"Provide approved_by parameter with Operator identifier."
                )
                return False

            if not eligible and initiator != "Operator":
                logger.warning(
                    f"Analyst not eligible for promotion to {target_tier.name}. "
                    f"Reasons: {', '.join(reasons)}"
                )
                return False

            # Build promotion record BEFORE updating state (so previous_tier is correct)
            old_tier = self._state.current_tier
            now_ms = int(time.time() * 1000)

            # Determine event and initiator enum
            if target_tier == LearningTier.L2:
                event = PromotionEvent.AUTO_PROMOTE_L1_TO_L2
            elif target_tier == LearningTier.L3:
                event = PromotionEvent.AUTO_PROMOTE_L2_TO_L3
            elif target_tier == LearningTier.L4:
                event = PromotionEvent.AUTO_PROMOTE_L3_TO_L4
            elif target_tier == LearningTier.L5:
                event = PromotionEvent.OPERATOR_APPROVE_L4_TO_L5
            else:
                event = PromotionEvent.OPERATOR_PROMOTE_OVERRIDE

            initiator_enum = PromotionInitiator.OPERATOR if initiator == "Operator" else PromotionInitiator.LEARNING_GATE

            # Build promotion record (captures state before update)
            record = _build_promotion_record(
                self._state,
                target_tier,
                event,
                initiator_enum,
                reason_codes=reasons if not eligible else ["gate_met"],
                approved_by=approved_by,
            )

            # Now update state
            self._state.current_tier = target_tier
            self._state.tier_promoted_at_ms = now_ms
            self._state.days_at_tier = 0
            self._state.version += 1

            # Track L2 start time for L3 gate calculation
            if target_tier == LearningTier.L2:
                self._l2_start_time_ms = now_ms

            self._state.promotions.append(record)
            self._state.last_promotion_event = event.value
            self._state.last_promotion_initiator = initiator_enum.value
            self._state.last_promotion_reason = reason

            logger.info(
                f"Analyst promoted from {old_tier.name} to {target_tier.name}. "
                f"Event: {event.value}, Initiator: {initiator_enum.value}, Reason: {reason}"
            )

            # Emit audit callback
            if self._audit_callback:
                self._audit_callback(record)

            return True

    def get_current_tier(self) -> LearningTier:
        """Get current tier (convenience method) / 获取当前等级（便利方法）"""
        return self.current_tier

    # ── Capability Checks ──

    def can_record_observations(self) -> bool:
        """Check if current tier can record observations / 检查当前等级是否可以记录观察"""
        return TIER_CAPABILITIES[self.current_tier].can_record_observations

    def can_discover_patterns(self) -> bool:
        """Check if current tier can discover patterns (L2+) / 检查当前等级是否可以发现模式 (L2+)"""
        return TIER_CAPABILITIES[self.current_tier].can_discover_patterns

    def can_generate_hypotheses(self) -> bool:
        """Check if current tier can generate hypotheses (L3+) / 检查当前等级是否可以生成假说 (L3+)"""
        return TIER_CAPABILITIES[self.current_tier].can_generate_hypotheses

    def can_design_experiments(self) -> bool:
        """Check if current tier can design experiments (L3+) / 检查当前等级是否可以设计实验 (L3+)"""
        return TIER_CAPABILITIES[self.current_tier].can_design_experiments

    def can_evolve_strategies(self) -> bool:
        """Check if current tier can evolve strategies (L4+) / 检查当前等级是否可以演进策略 (L4+)"""
        return TIER_CAPABILITIES[self.current_tier].can_evolve_strategies

    def can_propose_strategy_variants(self) -> bool:
        """Check if current tier can propose new strategy variants (L4+) / 检查当前等级是否可以提议新策略变体 (L4+)"""
        return TIER_CAPABILITIES[self.current_tier].can_propose_strategy_variants

    def can_propose_transfers(self) -> bool:
        """Check if current tier can propose cross-strategy transfers (L4+) / 检查当前等级是否可以提议跨策略迁移 (L4+)"""
        return TIER_CAPABILITIES[self.current_tier].can_propose_transfers

    def can_predict_regime_transition(self) -> bool:
        """Check if current tier can predict regime transitions (L4+) / 检查当前等级是否可以预测制度转换 (L4+)"""
        return TIER_CAPABILITIES[self.current_tier].can_predict_regime_transition

    def can_optimize_learning_pipeline(self) -> bool:
        """Check if current tier can optimize learning pipeline (L5+) / 检查当前等级是否可以优化学习管线 (L5+)"""
        return TIER_CAPABILITIES[self.current_tier].can_optimize_learning_pipeline

    def can_auto_deploy_to_paper(self) -> bool:
        """Check if current tier can auto-deploy to paper trading (L3+) / 检查当前等级是否可以自动部署到纸上交易 (L3+)"""
        return TIER_CAPABILITIES[self.current_tier].can_auto_deploy_to_paper

    def can_modify_live_config(self) -> bool:
        """
        Check if current tier can modify live configuration.
        Per EX-05 §8.2: ALL tiers cannot autonomously modify live config.
        检查当前等级是否可以修改实时配置。
        根据 EX-05 §8.2：所有等级都不能自主修改实时配置。
        """
        return False  # Immutable across all tiers per EX-05 §8.2

    # ── Serialization ──

    def export_state(self) -> dict[str, Any]:
        """
        Export tier state for persistence / storage.
        导出等级状态以进行持久化 / 存储。
        """
        with self._lock:
            return {
                "current_tier": self._state.current_tier.name,
                "tier_promoted_at_ms": self._state.tier_promoted_at_ms,
                "observation_count": self._state.observation_count,
                "confirmed_patterns": self._state.confirmed_patterns,
                "validated_hypotheses": self._state.validated_hypotheses,
                "experiment_roi": self._state.experiment_roi,
                "win_rate": self._state.win_rate,
                "days_at_tier": self._state.days_at_tier,
                "days_operational": self._state.days_operational,
                "sustained_positive_live_days": self._state.sustained_positive_live_days,
                "last_promotion_event": self._state.last_promotion_event,
                "last_promotion_initiator": self._state.last_promotion_initiator,
                "last_promotion_reason": self._state.last_promotion_reason,
                "promotions": self._state.promotions,
                "version": self._state.version,
                "criteria": self._criteria.to_dict(),
            }

    def import_state(self, exported: dict[str, Any]) -> bool:
        """
        Import tier state from exported data.
        从导出的数据导入等级状态。

        Args:
            exported: Dictionary from export_state()

        Returns:
            True if import succeeded, False otherwise
        """
        try:
            with self._lock:
                tier_name = exported.get("current_tier", "L1")
                self._state.current_tier = LearningTier[tier_name]
                self._state.tier_promoted_at_ms = exported.get("tier_promoted_at_ms", int(time.time() * 1000))
                self._state.observation_count = exported.get("observation_count", 0)
                self._state.confirmed_patterns = exported.get("confirmed_patterns", 0)
                self._state.validated_hypotheses = exported.get("validated_hypotheses", 0)
                self._state.experiment_roi = exported.get("experiment_roi", 0.0)
                self._state.win_rate = exported.get("win_rate", 0.0)
                self._state.days_at_tier = exported.get("days_at_tier", 0)
                self._state.days_operational = exported.get("days_operational", 0)
                self._state.sustained_positive_live_days = exported.get("sustained_positive_live_days", 0)
                self._state.last_promotion_event = exported.get("last_promotion_event", "")
                self._state.last_promotion_initiator = exported.get("last_promotion_initiator", "")
                self._state.last_promotion_reason = exported.get("last_promotion_reason", "")
                self._state.promotions = exported.get("promotions", [])
                self._state.version = exported.get("version", 1)
            return True
        except (KeyError, ValueError, TypeError) as e:
            logger.error("Failed to import learning tier state: %s", e)
            return False
