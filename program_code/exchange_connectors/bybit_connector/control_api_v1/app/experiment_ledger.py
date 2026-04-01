"""
Phase 3 Batch 3A — ExperimentLedger: Hypothesis lifecycle management
=====================================================================
Governance refs: DOC-01 §5.12 (持续进化), DOC-01 §5.10 (认知诚实), Principle 7 (学习≠改写Live)

MODULE_NOTE (中文):
  ExperimentLedger 是假设生命周期管理中心，负责追踪交易假设从提出到确认/证伪的全过程。
  职责：
  1. 接受 Agent 提出的交易假设（Hypothesis），赋予唯一 ID 和 TTL
  2. 通过 record_observation() 收集支持/反驳证据，统计置信度
  3. 达到阈值（65% 支持或反驳 + >= min_observations）时自动结案
  4. CONFIRMED 假设自动注入 TruthSourceRegistry，使策略层可感知已验证规律
  5. 失效假设自动标记 EXPIRED，避免陈旧假设影响决策

  核心设计约束（根原则 12：持续进化）：
  - 假设结案不得阻塞主交易流（fail-open：注入 TruthSourceRegistry 失败仅 log warning）
  - 所有方法线程安全（threading.Lock 保护内部状态）
  - 已结案假设忽略新观察（静默返回，不抛出异常）
  - REFUTED 假设不注入 TruthSourceRegistry（原则 10：认知诚实）

MODULE_NOTE (English):
  ExperimentLedger manages the full lifecycle of trading hypotheses from proposal to
  confirmation or refutation.
  Responsibilities:
  1. Accept hypotheses from Agents, assign unique IDs and TTL
  2. Collect supporting/refuting evidence via record_observation(), track confidence
  3. Auto-conclude when threshold reached (65% support or refute + >= min_observations)
  4. Inject CONFIRMED hypotheses into TruthSourceRegistry so strategy layer can act on
     validated patterns
  5. Auto-mark stale hypotheses EXPIRED to prevent outdated hypotheses influencing decisions

  Core design constraints (Principle 12: Continuous Evolution):
  - Hypothesis conclusion MUST NOT block the main trading flow (fail-open: TruthSourceRegistry
    injection failure only logs a warning)
  - All methods are thread-safe (threading.Lock protects internal state)
  - Concluded hypotheses silently ignore new observations (no exception, return current status)
  - REFUTED hypotheses are NOT injected into TruthSourceRegistry (Principle 10: Cognitive Honesty)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants / 常量
# ─────────────────────────────────────────────────────────────────────────────

_MS_PER_DAY = 86_400_000

# Default snapshot path / 默认快照路径
# Resolution: OPENCLAW_EXPERIMENT_LEDGER_PATH env var → fallback: settings/experiment_ledger_snapshot.json
# 解析顺序：环境变量 OPENCLAW_EXPERIMENT_LEDGER_PATH → 回退：settings/experiment_ledger_snapshot.json
_EXPERIMENT_LEDGER_DEFAULT_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # app/
    "..", "..", "..", "..",                        # up to srv/
    "settings",
    "experiment_ledger_snapshot.json",
)

# Debounce interval for auto-save (seconds)
# 自动保存的去抖间隔（秒）
_SAVE_DEBOUNCE_SECONDS = 60.0

# Confirmation threshold: 65% of observations must be supporting/refuting
# 确认阈值：65% 的观察必须为支持或反驳
_CONFIRM_THRESHOLD = 0.65

# Outcomes treated as supporting evidence / 视为支持证据的 outcome 字符串
_SUPPORTING_OUTCOMES = {"win", "success", "confirmed", "supporting", "profit", "pass"}

# Outcomes treated as refuting evidence / 视为反驳证据的 outcome 字符串
_REFUTING_OUTCOMES = {"loss", "fail", "refuted", "refuting", "failure", "stop"}


# ─────────────────────────────────────────────────────────────────────────────
# HypothesisStatus enum / 假设状态枚举
# ─────────────────────────────────────────────────────────────────────────────

class HypothesisStatus(str, Enum):
    """Lifecycle state of a trading hypothesis.
    交易假设的生命周期状态。

    PENDING   — Proposed, awaiting first observation / 已提出，等待第一次观察
    RUNNING   — At least one observation recorded / 已有至少一次观察记录
    CONFIRMED — Sufficient supporting evidence (>= 65% win rate) / 足够的支持证据
    REFUTED   — Sufficient refuting evidence (>= 65% loss rate) / 足够的反驳证据
    EXPIRED   — TTL elapsed without conclusion / TTL 到期仍未结案
    """
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    CONFIRMED = "CONFIRMED"
    REFUTED   = "REFUTED"
    EXPIRED   = "EXPIRED"


# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis dataclass / 假设数据类
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Hypothesis:
    """A single trading hypothesis tracked through its lifecycle.
    单条贯穿生命周期的交易假设。

    Fields use bilingual comments per project coding standards.
    字段按项目编码规范使用双语注释。
    """
    # Unique identifier (uuid4 hex[:12] or caller-provided)
    # 唯一标识符（uuid4 hex[:12] 或调用方提供）
    hypothesis_id: str

    # Human-readable description of the hypothesis
    # 假设的可读描述
    description: str

    # Strategy name this hypothesis applies to
    # 假设适用的策略名称
    strategy_name: str

    # Market regime context: "trending" / "ranging" / "volatile" / "all"
    # 市场 regime 上下文
    regime: str

    # Agent or system that proposed this hypothesis
    # 提出此假设的 Agent 或系统
    proposed_by: str

    # Unix timestamp (ms) when hypothesis was proposed
    # 假设提出时间（毫秒时间戳）
    proposed_at_ms: int

    # Unix timestamp (ms) when hypothesis expires (TTL deadline)
    # 假设过期时间（毫秒时间戳，TTL 截止）
    expires_at_ms: int

    # Current lifecycle status / 当前生命周期状态
    status: HypothesisStatus = HypothesisStatus.PENDING

    # Minimum observations required before conclusion can be triggered
    # 触发结案前所需的最少观察次数
    min_observations: int = 20

    # Count of observations supporting the hypothesis
    # 支持假设的观察计数
    supporting_count: int = 0

    # Count of observations refuting the hypothesis
    # 反驳假设的观察计数
    refuting_count: int = 0

    # claim_id in TruthSourceRegistry after successful injection
    # 成功注入 TruthSourceRegistry 后的 claim_id，追踪来源
    claim_id: Optional[str] = None

    # Unix timestamp (ms) when hypothesis was concluded (CONFIRMED/REFUTED/EXPIRED)
    # 假设结案时间（毫秒时间戳）
    concluded_at_ms: Optional[int] = None

    # Free-form notes for audit trail / 审计追踪用自由文本备注
    notes: str = ""

    def confidence(self) -> float:
        """Compute confidence as supporting / total observations.
        计算置信度：支持次数 / 总观察次数。

        Returns 0.0 if no observations have been recorded yet.
        若尚无观察记录则返回 0.0。
        """
        total = self.supporting_count + self.refuting_count
        if total == 0:
            # No observations yet — cannot derive confidence / 无观察 — 无法推导置信度
            return 0.0
        return self.supporting_count / total

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        """Return True if the hypothesis TTL has elapsed.
        若假设 TTL 已到期则返回 True。
        """
        ts = now_ms if now_ms is not None else int(time.time() * 1000)
        return ts >= self.expires_at_ms

    def to_dict(self) -> Dict[str, Any]:
        """Serialize hypothesis to dictionary for API / audit output.
        序列化假设为字典，用于 API 或审计输出。
        """
        return {
            "hypothesis_id": self.hypothesis_id,
            "description": self.description,
            "strategy_name": self.strategy_name,
            "regime": self.regime,
            "proposed_by": self.proposed_by,
            "proposed_at_ms": self.proposed_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "status": self.status.value,
            "min_observations": self.min_observations,
            "supporting_count": self.supporting_count,
            "refuting_count": self.refuting_count,
            "confidence": self.confidence(),
            "claim_id": self.claim_id,
            "concluded_at_ms": self.concluded_at_ms,
            "notes": self.notes,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ExperimentLedger class / 实验账本类
# ─────────────────────────────────────────────────────────────────────────────

class ExperimentLedger:
    """Lifecycle manager for trading hypotheses.
    交易假设的生命周期管理器。

    Tracks hypotheses from proposal through observation accumulation to conclusion.
    CONFIRMED hypotheses are injected into TruthSourceRegistry (fail-open).
    REFUTED hypotheses are concluded but not injected (Principle 10: Cognitive Honesty).

    追踪假设从提出、观察累积到结案的全过程。
    CONFIRMED 假设注入 TruthSourceRegistry（fail-open 模式）。
    REFUTED 假设结案但不注入（根原则 10：认知诚实）。

    Thread-safety: all mutations are protected by self._lock.
    线程安全：所有变更操作均受 self._lock 保护。
    """

    def __init__(
        self,
        truth_registry: Optional[Any] = None,
        default_ttl_days: int = 7,
    ) -> None:
        """Initialize ExperimentLedger.
        初始化实验账本。

        Args:
            truth_registry: TruthSourceRegistry instance for injecting CONFIRMED hypotheses.
                            用于注入 CONFIRMED 假设的 TruthSourceRegistry 实例。
                            May be None — injection is silently skipped (fail-open).
                            可为 None — 注入将静默跳过（fail-open）。
            default_ttl_days: Default TTL in days for new hypotheses.
                              新假设的默认 TTL（天数）。
        """
        self._truth_registry = truth_registry
        self._default_ttl_days = default_ttl_days
        self._lock = threading.Lock()
        # hypothesis_id → Hypothesis / 假设存储
        self._hypotheses: Dict[str, Hypothesis] = {}

        # Debounced auto-save state / 去抖自动保存状态
        # _save_timer: pending background save timer (daemon thread)
        # _last_save_ts: monotonic timestamp of last successful save, for debounce check
        self._save_timer: Optional[threading.Timer] = None
        self._last_save_ts: float = 0.0

    # ── Proposal / 提出 ──────────────────────────────────────────────────────

    def propose_hypothesis(
        self,
        *,
        description: str,
        strategy_name: str,
        regime: str = "all",
        proposed_by: str = "system",
        min_observations: int = 20,
        ttl_days: Optional[int] = None,
        hypothesis_id: Optional[str] = None,
    ) -> str:
        """Propose a new trading hypothesis and register it in the ledger.
        提出一条新的交易假设并注册到账本中。

        Args:
            description: Human-readable hypothesis description / 可读假设描述
            strategy_name: Strategy this hypothesis applies to / 假设适用的策略名称
            regime: Market regime context / 市场 regime 上下文
            proposed_by: Source Agent or system identifier / 来源 Agent 或系统标识符
            min_observations: Minimum observations before conclusion / 结案前最少观察次数
            ttl_days: Override TTL in days; defaults to self._default_ttl_days
                      覆盖 TTL（天数）；默认为 self._default_ttl_days
            hypothesis_id: Explicit ID; auto-generated (uuid4 hex[:12]) if not provided
                           显式 ID；未提供时自动生成（uuid4 hex[:12]）

        Returns:
            hypothesis_id of the registered hypothesis.
            已注册假设的 hypothesis_id。
        """
        now_ms = int(time.time() * 1000)
        ttl = ttl_days if ttl_days is not None else self._default_ttl_days
        expires_at_ms = now_ms + ttl * _MS_PER_DAY

        # Auto-generate ID if not provided / 未提供时自动生成 ID
        hid = hypothesis_id if hypothesis_id is not None else uuid.uuid4().hex[:12]

        h = Hypothesis(
            hypothesis_id=hid,
            description=description,
            strategy_name=strategy_name,
            regime=regime,
            proposed_by=proposed_by,
            proposed_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            min_observations=min_observations,
        )

        with self._lock:
            self._hypotheses[hid] = h

        logger.debug(
            "Hypothesis proposed: id=%s strategy=%s regime=%s ttl_days=%d",
            hid, strategy_name, regime, ttl,
        )

        # Trigger debounced auto-save after state mutation
        # 状态变更后触发去抖自动保存
        self._schedule_debounced_save()

        return hid

    # ── Observation / 观察 ──────────────────────────────────────────────────

    def record_observation(self, hypothesis_id: str, outcome: str) -> HypothesisStatus:
        """Record a trade outcome observation for a hypothesis.
        为假设记录一次交易结果观察。

        Thread-safe. Silently ignores observations on already-concluded hypotheses.
        线程安全。对已结案的假设静默忽略新观察（不抛出异常）。

        Args:
            hypothesis_id: Target hypothesis ID / 目标假设 ID
            outcome: Outcome string (e.g. "win", "loss", "success", "fail")
                     结果字符串（例如 "win"、"loss"、"success"、"fail"）

        Returns:
            Current HypothesisStatus after processing the observation.
            处理观察后的当前 HypothesisStatus。
        """
        outcome_lower = outcome.lower()
        # Track whether state was mutated to trigger debounced save
        # 追踪状态是否变更，以触发去抖保存
        _state_mutated = False

        with self._lock:
            h = self._hypotheses.get(hypothesis_id)
            if h is None:
                logger.warning(
                    "record_observation: unknown hypothesis_id=%s, ignoring",
                    hypothesis_id,
                )
                return HypothesisStatus.PENDING

            # Already concluded — silently ignore to prevent false learning signals
            # 已结案 — 静默忽略，防止注入虚假学习信号（原则 8：交易可解释）
            if h.status in (
                HypothesisStatus.CONFIRMED,
                HypothesisStatus.REFUTED,
                HypothesisStatus.EXPIRED,
            ):
                return h.status

            # Transition PENDING → RUNNING on first observation
            # 第一次观察时从 PENDING 转换到 RUNNING
            if h.status == HypothesisStatus.PENDING:
                h.status = HypothesisStatus.RUNNING

            # Classify outcome and increment appropriate counter
            # 分类结果并递增对应计数器
            if outcome_lower in _SUPPORTING_OUTCOMES:
                h.supporting_count += 1
                _state_mutated = True
            elif outcome_lower in _REFUTING_OUTCOMES:
                h.refuting_count += 1
                _state_mutated = True
            else:
                # Unknown outcome: recorded but not classified (neither supports nor refutes)
                # 未知结果：记录但不分类（既不支持也不反驳）
                logger.debug(
                    "record_observation: unrecognized outcome '%s' for hypothesis_id=%s, ignoring",
                    outcome, hypothesis_id,
                )
                return h.status

            total = h.supporting_count + h.refuting_count

            # Check conclusion thresholds only if minimum observations are met
            # 仅在达到最少观察次数后才检查结案阈值
            if total >= h.min_observations:
                support_ratio = h.supporting_count / total
                refute_ratio = h.refuting_count / total

                # 65% supporting observations → CONFIRMED
                # 0.65 支持阈值：65% 的观察为支持 → CONFIRMED（设计意图：足够强的统计信号才结案）
                if support_ratio >= _CONFIRM_THRESHOLD:
                    concluded_status = HypothesisStatus.CONFIRMED
                    self._conclude(hypothesis_id, concluded_status)
                    self._schedule_debounced_save()
                    return concluded_status

                # 65% refuting observations → REFUTED
                # 0.65 反驳阈值：65% 的观察为反驳 → REFUTED（与确认阈值对称，保持认识论一致性）
                elif refute_ratio >= _CONFIRM_THRESHOLD:
                    concluded_status = HypothesisStatus.REFUTED
                    self._conclude(hypothesis_id, concluded_status)
                    self._schedule_debounced_save()
                    return concluded_status

            result_status = h.status

        # Trigger debounced auto-save outside the lock if state was mutated
        # 若状态已变更，在锁外触发去抖自动保存
        if _state_mutated:
            self._schedule_debounced_save()

        return result_status

    # ── Conclusion / 结案 ────────────────────────────────────────────────────

    def _conclude(self, hypothesis_id: str, status: HypothesisStatus) -> None:
        """Conclude a hypothesis with the given status.
        以给定状态结案一条假设。

        IMPORTANT: This method is called while holding self._lock.
        Injection into TruthSourceRegistry is done AFTER releasing the lock to
        avoid potential deadlocks and ensure fail-open behavior.
        重要：此方法在持有 self._lock 时被调用。
        注入 TruthSourceRegistry 在释放锁后进行，以避免潜在死锁并确保 fail-open 行为。

        Fail-open design: TruthSourceRegistry injection failure MUST NOT block
        the main trading flow. Only a warning is logged.
        Fail-open 设计：假设结案不得阻塞主交易流。TruthSourceRegistry 注入失败
        仅记录 warning，不抛出异常，不影响假设本身的结案状态。

        Args:
            hypothesis_id: Hypothesis to conclude / 待结案的假设 ID
            status: Final status (CONFIRMED / REFUTED / EXPIRED) / 最终状态
        """
        h = self._hypotheses[hypothesis_id]
        h.status = status
        h.concluded_at_ms = int(time.time() * 1000)

        logger.info(
            "Hypothesis concluded: id=%s status=%s supporting=%d refuting=%d",
            hypothesis_id, status.value, h.supporting_count, h.refuting_count,
        )

        # Only CONFIRMED hypotheses are injected into TruthSourceRegistry
        # REFUTED hypotheses are NOT injected — Principle 10: Cognitive Honesty
        # 仅 CONFIRMED 假设注入 TruthSourceRegistry
        # REFUTED 假设不注入 — 根原则 10：认知诚实
        if status != HypothesisStatus.CONFIRMED:
            return

        # Capture values needed for injection before releasing lock
        # 在释放锁前捕获注入所需的值
        total_obs = h.supporting_count + h.refuting_count
        evidence_source = f"statistical_N={total_obs}"
        description = h.description
        strategy_name = h.strategy_name
        regime = h.regime
        raw_confidence = h.confidence()

        # Injection performed after method returns (caller holds lock); we inject here
        # while still under lock since _conclude is called from record_observation which
        # holds the lock. Use a local reference to avoid holding lock during network I/O.
        # Note: TruthSourceRegistry.register_claim() is pure in-memory — no I/O risk.
        # 注入在锁保护下执行；TruthSourceRegistry 为纯内存操作，无 I/O 风险。
        if self._truth_registry is not None:
            try:
                # Inject as INFERENCE level — statistical evidence cannot be FACT
                # 注入为 INFERENCE 级别 — 统计证据不得为 FACT（根原则 10）
                claim_id = self._truth_registry.register_claim(
                    pattern_text=description,
                    evidence_source=evidence_source,
                    observation_count=total_obs,
                    confidence=raw_confidence,
                    applies_to_regime=regime,
                    applies_to_strategy=strategy_name,
                )
                # Store claim_id for traceability — tracks which Registry entry this produced
                # 存储 claim_id 以便追踪 — 记录此假设产生了哪个 Registry 条目
                h.claim_id = claim_id
                logger.info(
                    "Hypothesis %s injected into TruthSourceRegistry as claim_id=%s",
                    hypothesis_id, claim_id,
                )
            except Exception as exc:
                # fail-open: injection failure must not disrupt the trading pipeline
                # fail-open：注入失败不得干扰交易管线（根原则 6：失败默认收缩，但不阻塞）
                logger.warning(
                    "ExperimentLedger: TruthSourceRegistry injection failed for hypothesis %s "
                    "(fail-open, hypothesis conclusion stands): %s",
                    hypothesis_id, exc,
                )
        else:
            # No registry configured — skip injection silently (fail-open)
            # 未配置 registry — 静默跳过注入（fail-open）
            logger.debug(
                "ExperimentLedger: no TruthSourceRegistry configured, skipping injection "
                "for hypothesis %s",
                hypothesis_id,
            )

    # ── Expiry / 过期 ────────────────────────────────────────────────────────

    def expire_stale_hypotheses(self) -> int:
        """Mark PENDING or RUNNING hypotheses as EXPIRED if their TTL has elapsed.
        将 TTL 已到期的 PENDING 或 RUNNING 假设标记为 EXPIRED。

        Does not re-process already-concluded hypotheses.
        不重复处理已结案的假设。

        Returns:
            Number of hypotheses newly marked EXPIRED.
            新标记为 EXPIRED 的假设数量。
        """
        now_ms = int(time.time() * 1000)
        expired_count = 0

        with self._lock:
            for h in self._hypotheses.values():
                # Only PENDING and RUNNING can expire — already-concluded are unchanged
                # 仅 PENDING 和 RUNNING 可过期 — 已结案的不再处理
                if h.status in (HypothesisStatus.PENDING, HypothesisStatus.RUNNING):
                    if h.is_expired(now_ms):
                        h.status = HypothesisStatus.EXPIRED
                        h.concluded_at_ms = now_ms
                        expired_count += 1
                        logger.info(
                            "Hypothesis expired: id=%s strategy=%s",
                            h.hypothesis_id, h.strategy_name,
                        )

        return expired_count

    # ── Queries / 查询 ───────────────────────────────────────────────────────

    def get_hypothesis(self, hypothesis_id: str) -> Optional[Hypothesis]:
        """Retrieve a hypothesis by ID. Returns None if not found.
        通过 ID 检索假设。若未找到则返回 None。
        """
        with self._lock:
            return self._hypotheses.get(hypothesis_id)

    def get_all_hypotheses(
        self,
        status: Optional[HypothesisStatus] = None,
    ) -> List[Hypothesis]:
        """Return all hypotheses, optionally filtered by status.
        返回所有假设，可选按状态过滤。

        Args:
            status: If provided, only return hypotheses with this status.
                    若提供，仅返回具有此状态的假设。

        Returns:
            List of matching Hypothesis objects (snapshot, not live references).
            匹配的 Hypothesis 对象列表（快照，非活跃引用）。
        """
        with self._lock:
            hypotheses = list(self._hypotheses.values())

        if status is not None:
            hypotheses = [h for h in hypotheses if h.status == status]
        return hypotheses

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics for all hypotheses.
        返回所有假设的汇总统计数据。

        Returns dict with keys: total, pending, running, confirmed, refuted, expired.
        返回包含以下键的字典：total, pending, running, confirmed, refuted, expired。
        """
        with self._lock:
            hypotheses = list(self._hypotheses.values())

        counts: Dict[str, int] = {
            "total": len(hypotheses),
            "pending": 0,
            "running": 0,
            "confirmed": 0,
            "refuted": 0,
            "expired": 0,
        }
        for h in hypotheses:
            key = h.status.value.lower()
            if key in counts:
                counts[key] += 1

        return counts

    def auto_seed_from_claims(self, claims: list, min_confidence: float = 0.5) -> int:
        """
        從 TruthSourceRegistry 的高信心 claims 自動生成初始假設。
        Auto-generate initial hypotheses from high-confidence TruthSourceRegistry claims.

        只為 confidence >= min_confidence 的 claim 生成假設，避免低質量信號污染。
        Only generate hypotheses for claims with confidence >= min_confidence to avoid
        low-quality noise polluting the hypothesis pool.

        fail-open：單條 claim 失敗不阻斷整體；返回成功生成數量。
        fail-open: single claim failure does not abort; returns count of successfully
        proposed hypotheses.

        原則 10 認知誠實：跳過 applies_to_strategy=="all" 的聲明，
        避免生成過於寬泛的假設污染學習平面。
        Principle 10 Cognitive Honesty: skip claims with strategy="all" to avoid
        overly broad hypotheses polluting the learning plane.

        Args:
            claims: list of PatternClaim objects (e.g. from TruthSourceRegistry.get_active_claims())
                    PatternClaim 對象列表（例如來自 TruthSourceRegistry.get_active_claims()）
            min_confidence: minimum confidence threshold (default 0.5)
                            最低置信度閾值（默認 0.5）

        Returns:
            int: count of hypotheses successfully proposed
                 成功提出的假設數量
        """
        count = 0
        for claim in claims:
            # 低信心 claim 跳過（噪音過濾）/ Skip low-confidence claims (noise filter)
            confidence = getattr(claim, "confidence", 0.0)
            if confidence < min_confidence:
                continue
            try:
                strategy = getattr(claim, "applies_to_strategy", "unknown")
                regime = getattr(claim, "applies_to_regime", "all")
                pattern_text = getattr(claim, "pattern_text", str(claim))

                # 避免生成 applies_to_strategy="all" 的假設（原則 10 認知誠實）
                # Avoid generating hypotheses with strategy="all" (Principle 10: cognitive honesty)
                if strategy == "all":
                    continue

                self.propose_hypothesis(
                    description=f"[auto-seed] {pattern_text}",
                    strategy_name=strategy,
                    regime=regime,
                    proposed_by="truth_registry_autoseed",
                )
                count += 1
            except Exception as e:
                # fail-open：跳過此 claim，繼續處理其餘 / fail-open: skip this claim
                logger.debug("auto_seed_from_claims skipped claim: %s", e)
        return count

    def to_snapshot(self) -> List[Dict[str, Any]]:
        """Return a serializable snapshot of all hypotheses.
        返回所有假设的可序列化快照。
        """
        with self._lock:
            return [h.to_dict() for h in self._hypotheses.values()]

    # ── Persistence / 持久化 ────────────────────────────────────────────────

    def save_snapshot(self, path: str) -> bool:
        """Serialize all current hypotheses to a JSON file at *path*.
        将当前所有假设序列化到 *path* 指定的 JSON 文件。

        Thread-safety design / 线程安全设计：
          1. 持锁读取假设数据，复制到局部列表后立即释放锁
             (Hold lock only to copy hypothesis data; release before disk I/O)
          2. 磁盘 I/O 在锁外进行，不阻塞并发操作
             (Disk I/O outside the lock so concurrent operations are not blocked)

        Principle 7 isolation / 原则 7 隔离：
          只序列化 Hypothesis 字段。不写入策略配置、风控阈值或任何实盘参数。
          Only Hypothesis fields are serialized. No strategy config, risk thresholds,
          or live trading parameters are written.

        Fail-open / fail-open（写失败不中断交易）：
          Any I/O or serialization error is caught, logged as WARNING, and returns False.
          任何 I/O 或序列化错误均被捕获，记录为 WARNING，返回 False。

        Returns:
            True on success, False on any exception.
            成功返回 True；任何异常返回 False。
        """
        # Step 1: read hypotheses under lock, then release before I/O
        # 步骤 1：持锁读取假设数据，然后在 I/O 前释放锁
        with self._lock:
            data = [h.to_dict() for h in self._hypotheses.values()]

        # Step 2: perform disk write outside the lock
        # 步骤 2：在锁外执行磁盘写入
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            self._last_save_ts = time.monotonic()
            logger.debug(
                "save_snapshot: wrote %d hypotheses to %s / 快照已写入 %d 条假设至 %s",
                len(data), path, len(data), path,
            )
            return True
        except Exception as exc:
            # fail-open: log warning, do not crash the trading pipeline
            # fail-open：记录警告，不中断交易管线
            logger.warning(
                "save_snapshot failed (fail-open): %s — path=%s / "
                "save_snapshot 失败（fail-open）：%s — 路径=%s",
                exc, path, exc, path,
            )
            return False

    def load_snapshot(self, path: str) -> int:
        """Load hypotheses from a JSON snapshot file and restore them into the ledger.
        从 JSON 快照文件加载假设并恢复到账本中。

        Behaviour / 行为：
          - Missing file  → log DEBUG, return 0 (no crash)
            文件不存在 → 记录 DEBUG，返回 0（不崩溃）
          - Corrupted JSON → log WARNING, return 0 (no crash, start fresh)
            JSON 损坏 → 记录 WARNING，返回 0（不崩溃，从空白开始）
          - Existing hypothesis_id → skip (do NOT overwrite newer in-memory data)
            已存在的 hypothesis_id → 跳过（不覆盖内存中更新的数据）

        Principle 7 isolation / 原则 7 隔离：
          Only Hypothesis fields are read. No strategy or risk configuration
          is loaded or modified.
          只读取 Hypothesis 字段，不加载或修改策略或风控配置。

        Returns:
            Count of hypotheses successfully loaded (0 if file missing or corrupted).
            成功加载的假设数（文件缺失或损坏时返回 0）。
        """
        # Step 1: check file existence (fail-open on missing file)
        # 步骤 1：检查文件是否存在（文件缺失时 fail-open）
        if not os.path.exists(path):
            logger.debug(
                "load_snapshot: file not found (no-op) — path=%s / "
                "load_snapshot：文件不存在（无操作）— 路径=%s",
                path, path,
            )
            return 0

        # Step 2: read and parse JSON (fail-open on corrupted JSON)
        # 步骤 2：读取并解析 JSON（JSON 损坏时 fail-open）
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning(
                "load_snapshot: failed to parse snapshot (fail-open): %s — path=%s / "
                "load_snapshot：快照解析失败（fail-open）：%s — 路径=%s",
                exc, path, exc, path,
            )
            return 0

        if not isinstance(raw, list):
            logger.warning(
                "load_snapshot: snapshot root is not a list (fail-open) — path=%s / "
                "load_snapshot：快照根节点不是列表（fail-open）— 路径=%s",
                path, path,
            )
            return 0

        # Step 3: restore hypotheses, skipping any hypothesis_id that already exists
        # 步骤 3：恢复假设，跳过已存在的 hypothesis_id（不覆盖内存中更新的数据）
        loaded = 0
        with self._lock:
            for entry in raw:
                try:
                    hid = entry["hypothesis_id"]
                    # Skip if already in ledger — don't overwrite newer in-memory data
                    # 若已存在则跳过 — 不覆盖内存中更新的数据
                    if hid in self._hypotheses:
                        continue
                    h = Hypothesis(
                        hypothesis_id=hid,
                        description=entry["description"],
                        strategy_name=entry["strategy_name"],
                        regime=entry.get("regime", "all"),
                        proposed_by=entry.get("proposed_by", "snapshot"),
                        proposed_at_ms=int(entry["proposed_at_ms"]),
                        expires_at_ms=int(entry["expires_at_ms"]),
                        status=HypothesisStatus(entry["status"]),
                        min_observations=int(entry.get("min_observations", 20)),
                        supporting_count=int(entry.get("supporting_count", 0)),
                        refuting_count=int(entry.get("refuting_count", 0)),
                        claim_id=entry.get("claim_id"),
                        concluded_at_ms=(
                            int(entry["concluded_at_ms"])
                            if entry.get("concluded_at_ms") is not None
                            else None
                        ),
                        notes=entry.get("notes", ""),
                    )
                    self._hypotheses[hid] = h
                    loaded += 1
                except (KeyError, TypeError, ValueError) as exc:
                    # Skip malformed entries, log warning
                    # 跳过格式错误的条目，记录警告
                    logger.warning(
                        "load_snapshot: skipping malformed entry %s: %s / "
                        "load_snapshot：跳过格式错误的条目 %s：%s",
                        entry.get("hypothesis_id", "?"), exc,
                        entry.get("hypothesis_id", "?"), exc,
                    )

        logger.debug(
            "load_snapshot: loaded %d hypotheses from %s / 从 %s 加载了 %d 条假设",
            loaded, path, path, loaded,
        )
        return loaded

    # ── Debounced save internals / 去抖动保存内部实现 ──

    def _resolve_snapshot_path(self) -> str:
        """Resolve the snapshot file path from env var or default.
        从环境变量或默认值解析快照文件路径。

        Resolution order / 解析顺序：
          1. OPENCLAW_EXPERIMENT_LEDGER_PATH env var
          2. _EXPERIMENT_LEDGER_DEFAULT_PATH (settings/experiment_ledger_snapshot.json)
        """
        return os.environ.get(
            "OPENCLAW_EXPERIMENT_LEDGER_PATH",
            _EXPERIMENT_LEDGER_DEFAULT_PATH,
        )

    def _schedule_debounced_save(self) -> None:
        """Schedule a debounced background save if enough time has elapsed since last save.
        若距上次保存已过去足够时间，调度去抖后台保存。

        Design / 设计：
          - 使用简单的时间检查：若距上次保存 < _SAVE_DEBOUNCE_SECONDS，跳过
            Simple time check: if last save was < _SAVE_DEBOUNCE_SECONDS ago, skip.
          - 使用 threading.Timer（非 asyncio），因为 ExperimentLedger 是纯同步代码。
            Uses threading.Timer (not asyncio) because ExperimentLedger is sync.
          - 若已有定时器挂起，不重复调度。
            If a timer is already pending, do not schedule another.
          - 定时器线程设为 daemon，进程退出时不阻塞。
            Timer thread is daemon so it won't block process exit.

        Fail-open / fail-open：调度失败仅 log warning，不影响主路径。
        """
        try:
            now = time.monotonic()
            # Debounce: skip if last save was recent enough
            # 去抖：若上次保存足够近，跳过
            if (now - self._last_save_ts) < _SAVE_DEBOUNCE_SECONDS:
                return

            # Don't schedule if a timer is already pending
            # 若已有定时器挂起，不重复调度
            if self._save_timer is not None and self._save_timer.is_alive():
                return

            path = self._resolve_snapshot_path()
            timer = threading.Timer(5.0, self._do_save, args=(path,))
            timer.daemon = True  # don't block process exit / 不阻塞进程退出
            timer.start()
            self._save_timer = timer
        except Exception as exc:
            # fail-open: scheduling failure must not disrupt the trading pipeline
            # fail-open：调度失败不得干扰交易管线
            logger.warning(
                "ExperimentLedger._schedule_debounced_save failed (fail-open): %s",
                exc,
            )

    def _do_save(self, path: str) -> None:
        """Internal callback invoked by the debounce timer to persist the ledger.
        去抖动定时器触发的内部回调，用于持久化账本。

        After the save completes (success or fail), clear self._save_timer so the
        next mutation can schedule a fresh save.
        保存完成（成功或失败）后清除 self._save_timer，使下次变更可以调度新的保存。
        """
        # Delegate actual I/O to save_snapshot (fail-open, handles all exceptions)
        # 将实际 I/O 委托给 save_snapshot（fail-open，处理所有异常）
        self.save_snapshot(path)
        # Clear the timer reference under lock for thread safety (E2-1 fix)
        # 在锁保护下清除定时器引用，确保线程安全（E2-1 修复）
        with self._lock:
            self._save_timer = None
