"""
Batch 2A — TruthSourceRegistry: Epistemically-governed pattern claim repository
=================================================================================
Governance refs: DOC-01 §5.10 (认知诚实), DOC-01 §5.7 (学习≠改写Live), Principle 12 (持续进化)

MODULE_NOTE (中文):
  TruthSourceRegistry 是模式声明（PatternClaim）的权威存储中心。
  职责：
  1. 登记 Analyst 发现的模式声明，强制认识论级别（FACT/INFERENCE/HYPOTHESIS）
  2. 根据证据来源（statistical/ai/manual）自动设定认知级别上限和信度上限
  3. 通过 TTL 机制自动过期陈旧声明，通过 falsification_count 降级反驳声明
  4. 向 StrategistAgent 提供可查询的高信度声明，用于策略权重更新

  认识论约束（根原则 10：认知诚实）：
  - AI 输出永远不得标记为 FACT（仅 manual 来源可达 FACT）
  - statistical(N<30) → INFERENCE，信度上限 0.5
  - statistical(N≥30) → INFERENCE，信度上限 0.7
  - ai → INFERENCE，信度上限 0.85
  - manual → FACT，信度上限 1.0

  原则 7 隔离：本模块不修改任何策略配置或风控阈值。
  只读提供声明查询，写入路径仅限 register_claim() 和 record_falsification()。

MODULE_NOTE (English):
  TruthSourceRegistry is the authoritative store for pattern claims (PatternClaim).
  Responsibilities:
  1. Register pattern claims discovered by Analyst with forced epistemic levels
  2. Automatically cap cognitive level and confidence based on evidence source
  3. Auto-expire stale claims via TTL; downgrade refuted claims via falsification_count
  4. Provide queryable high-confidence claims to StrategistAgent for weight updates

  Epistemological constraints (Principle 10: Cognitive Honesty):
  - AI output MUST NEVER be labeled FACT (only 'manual' source may reach FACT)
  - statistical(N<30) → INFERENCE, confidence cap 0.5
  - statistical(N≥30) → INFERENCE, confidence cap 0.7
  - ai → INFERENCE, confidence cap 0.85
  - manual → FACT, confidence cap 1.0

  Principle 7 isolation: This module MUST NOT modify any strategy config or risk thresholds.
  Read-only claim queries; write path limited to register_claim() and record_falsification().
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default snapshot path / 默认快照路径
#
# 优先读取环境变量 OPENCLAW_TRUTH_REGISTRY_PATH；
# 若未设置，则使用项目根目录下的 settings/ 文件夹。
#
# Resolution order (priority high → low):
#   1. OPENCLAW_TRUTH_REGISTRY_PATH env var
#   2. <this_file>/../../../../settings/truth_registry_snapshot.json
#      (i.e.  app/ → control_api_v1/ → bybit_connector/ → exchange_connectors/ → settings/)
# ─────────────────────────────────────────────────────────────────────────────
_TRUTH_REGISTRY_DEFAULT_PATH: str = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # app/
    "..", "..", "..", "..",                        # up to srv/
    "settings",
    "truth_registry_snapshot.json",
)

# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚举
# ═══════════════════════════════════════════════════════════════════════════════

class CognitiveLevel(str, Enum):
    """Epistemological certainty level for a pattern claim.
    模式声明的认识论确定性级别。

    FACT       — Verified by human operator or proven statistical regularity.
                 由人类操作员验证或经证实的统计规律。
    INFERENCE  — Strong statistical evidence or AI-derived analysis.
                 强统计证据或 AI 推导的分析。
    HYPOTHESIS — Weak evidence; requires more observations before acting.
                 证据较弱；需要更多观察才能据此行动。
    """
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"


# ═══════════════════════════════════════════════════════════════════════════════
# PatternClaim dataclass / 模式声明数据类
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PatternClaim:
    """A single epistemically-governed pattern claim.
    单条经认识论约束的模式声明。

    Fields are documented in both Chinese and English to comply with bilingual comment rules.
    字段使用中英双语文档以符合双语注释规范。
    """
    # Unique identifier / 唯一标识符
    claim_id: str

    # Human-readable description of the pattern / 模式的人类可读描述
    pattern_text: str

    # Epistemological certainty level — enforced by registry on registration
    # 认识论确定性级别 — 由 registry 在登记时强制执行
    cognitive_level: CognitiveLevel

    # Evidence source string: "statistical_N=XX" / "ai" / "manual"
    # 证据来源字符串
    evidence_source: str

    # Number of observations supporting this claim / 支持此声明的观察次数
    observation_count: int

    # Confidence score in [0.0, 1.0]; capped by evidence_source
    # 信度分数 [0.0, 1.0]；由 evidence_source 决定上限
    confidence: float

    # Market regime this applies to: "trending"/"ranging"/"volatile"/"all"
    # 适用的市场 regime
    applies_to_regime: str

    # Specific strategy name or "all"
    # 具体策略名或 "all"
    applies_to_strategy: str

    # Unix timestamp in ms when the claim was created / 声明创建时间（毫秒）
    created_at_ms: int

    # Unix timestamp in ms when the claim expires (0 = never) / 声明过期时间（毫秒），0表示永不过期
    expires_at_ms: int

    # Whether the claim is currently active / 声明当前是否有效
    is_active: bool = True

    # claim_id of the claim that superseded this one, if any / 替代本声明的 claim_id
    superseded_by: Optional[str] = None

    # Number of times this claim has been falsified by contradicting evidence
    # 此声明被矛盾证据证伪的次数
    falsification_count: int = 0

    # Number of falsifications before automatic downgrade / 自动降级前的证伪次数阈值
    falsification_threshold: int = 5

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        """Return True if this claim has passed its TTL.
        若声明已超过其 TTL，返回 True。
        """
        if self.expires_at_ms == 0:
            # 0 = never expires / 0 = 永不过期
            return False
        ts = now_ms if now_ms is not None else int(time.time() * 1000)
        return ts >= self.expires_at_ms

    def to_dict(self) -> Dict[str, Any]:
        """Serialize claim to dictionary for audit / JSON output.
        序列化声明为字典，用于审计或 JSON 输出。
        """
        return {
            "claim_id": self.claim_id,
            "pattern_text": self.pattern_text,
            "cognitive_level": self.cognitive_level.value,
            "evidence_source": self.evidence_source,
            "observation_count": self.observation_count,
            "confidence": self.confidence,
            "applies_to_regime": self.applies_to_regime,
            "applies_to_strategy": self.applies_to_strategy,
            "created_at_ms": self.created_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "is_active": self.is_active,
            "superseded_by": self.superseded_by,
            "falsification_count": self.falsification_count,
            "falsification_threshold": self.falsification_threshold,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Constants: evidence source → TTL and confidence caps
# 常量：证据来源 → TTL 和信度上限
# ═══════════════════════════════════════════════════════════════════════════════

_MS_PER_DAY = 86_400_000

# Confidence upper bounds per source / 各来源的信度上限
_CONFIDENCE_CAP: Dict[str, float] = {
    "statistical_low": 0.5,   # N < 30
    "statistical_high": 0.7,  # N >= 30
    "ai": 0.85,
    "manual": 1.0,
}

# TTL in milliseconds / 各来源的 TTL（毫秒）
_TTL_MS: Dict[str, int] = {
    "statistical_low": 7 * _MS_PER_DAY,    # N < 50 → 7 days
    "statistical_high": 30 * _MS_PER_DAY,  # N >= 50 → 30 days
    "ai": 14 * _MS_PER_DAY,                # ai → 14 days
    "manual": 0,                            # manual → never expires
}

_N_THRESHOLD_CONFIDENCE = 30  # N threshold for confidence cap
_N_THRESHOLD_TTL = 50         # N threshold for TTL selection


def _parse_evidence_source(evidence_source: str) -> tuple[str, int]:
    """Parse evidence_source string to (source_type, observation_N).
    解析 evidence_source 字符串为 (来源类型, 观察次数 N)。

    Returns:
        (source_type, n) where source_type is one of: "statistical", "ai", "manual"
        and n is the observation count (0 for non-statistical sources).
    """
    if evidence_source.startswith("statistical"):
        # Expected format: "statistical_N=XX" / 期望格式: "statistical_N=XX"
        match = re.search(r"N=(\d+)", evidence_source)
        n = int(match.group(1)) if match else 0
        return "statistical", n
    elif evidence_source == "ai":
        return "ai", 0
    elif evidence_source == "manual":
        return "manual", 0
    else:
        # Unknown source treated as weakest statistical with N=0
        # 未知来源按最弱的统计证据处理
        logger.warning("Unknown evidence_source '%s', treating as statistical_N=0", evidence_source)
        return "statistical", 0


def _cap_confidence(confidence: float, evidence_source: str) -> float:
    """Enforce confidence upper bound based on evidence source.
    根据证据来源强制执行信度上限。

    This is a core epistemic constraint (Principle 10).
    这是核心认识论约束（根原则 10）。
    """
    source_type, n = _parse_evidence_source(evidence_source)
    if source_type == "statistical":
        cap = _CONFIDENCE_CAP["statistical_high"] if n >= _N_THRESHOLD_CONFIDENCE else _CONFIDENCE_CAP["statistical_low"]
    elif source_type == "ai":
        cap = _CONFIDENCE_CAP["ai"]
    else:
        cap = _CONFIDENCE_CAP["manual"]
    return min(float(confidence), cap)


def _derive_cognitive_level(evidence_source: str, confidence: float) -> CognitiveLevel:
    """Derive the CognitiveLevel from evidence_source.
    从证据来源推导 CognitiveLevel。

    Epistemic rules:
    - "manual" → FACT is allowed
    - "ai" → maximum INFERENCE (never FACT — Principle 10)
    - "statistical" → INFERENCE if N >= 30 and confidence > 0.5, else HYPOTHESIS
    认识论规则：
    - "manual" → 允许 FACT
    - "ai" → 最高 INFERENCE（永远不得为 FACT — 根原则 10）
    - "statistical" → N >= 30 且 confidence > 0.5 时为 INFERENCE，否则 HYPOTHESIS
    """
    source_type, n = _parse_evidence_source(evidence_source)
    if source_type == "manual":
        # manual is the only source that can produce FACT / manual 是唯一可产出 FACT 的来源
        return CognitiveLevel.FACT
    elif source_type == "ai":
        # AI output MUST NEVER be FACT — Principle 10: Cognitive Honesty
        # AI 输出永远不得为 FACT — 根原则 10：认知诚实
        return CognitiveLevel.INFERENCE
    else:
        # statistical: INFERENCE if N >= 30 and confidence passes threshold
        # 统计：N >= 30 且信度通过阈值时为 INFERENCE
        if n >= _N_THRESHOLD_CONFIDENCE and confidence > 0.5:
            return CognitiveLevel.INFERENCE
        return CognitiveLevel.HYPOTHESIS


def _compute_ttl_ms(evidence_source: str) -> int:
    """Compute TTL in milliseconds from evidence_source.
    根据证据来源计算 TTL（毫秒）。

    TTL rules:
    - statistical N < 50  → 7 days
    - statistical N >= 50 → 30 days
    - ai                  → 14 days
    - manual              → 0 (never expires)
    """
    source_type, n = _parse_evidence_source(evidence_source)
    if source_type == "statistical":
        ttl = _TTL_MS["statistical_high"] if n >= _N_THRESHOLD_TTL else _TTL_MS["statistical_low"]
    elif source_type == "ai":
        ttl = _TTL_MS["ai"]
    else:
        # manual: never expires
        return 0
    now_ms = int(time.time() * 1000)
    return now_ms + ttl


# ═══════════════════════════════════════════════════════════════════════════════
# TruthSourceRegistry class
# ═══════════════════════════════════════════════════════════════════════════════

class TruthSourceRegistry:
    """Epistemically-governed repository for pattern claims.
    经认识论约束的模式声明存储中心。

    PRINCIPLE 7 ISOLATION NOTE:
    This class is a pure knowledge store. It MUST NOT modify any strategy config,
    risk thresholds, or live trading parameters. Its only outputs are:
    - Claim registration confirmation (claim_id)
    - Read-only claim queries
    - Falsification/expiry side effects on its own internal state only
    原则 7 隔离说明：
    本类是纯粹的知识存储。不得修改任何策略配置、风控阈值或实盘交易参数。
    其唯一输出为声明登记确认、只读声明查询、以及仅对自身内部状态的证伪/过期副作用。

    Thread-safety: all mutations are protected by self._lock.
    线程安全：所有变更操作均受 self._lock 保护。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # claim_id → PatternClaim / 声明存储
        self._claims: Dict[str, PatternClaim] = {}
        # Stats for get_stats() / 统计数据
        self._stats = {
            "total_registered": 0,
            "total_expired": 0,
            "total_falsified": 0,
            "total_superseded": 0,
        }
        # Debounced save timer — None means no save is currently scheduled
        # 去抖动保存定时器 — None 表示当前没有计划保存
        self._save_timer: Optional[threading.Timer] = None

    # ── Registration / 登记 ──

    def register_claim(
        self,
        *,
        pattern_text: str,
        evidence_source: str,
        observation_count: int,
        confidence: float,
        applies_to_regime: str = "all",
        applies_to_strategy: str = "all",
        claim_id: Optional[str] = None,
    ) -> str:
        """Register a new pattern claim, enforcing epistemic constraints.
        登记一条新的模式声明，强制执行认识论约束。

        Epistemic enforcement:
        1. Confidence is capped based on evidence_source
        2. CognitiveLevel is derived from evidence_source (AI → never FACT)
        3. TTL is computed from evidence_source
        4. If a higher-confidence active claim for the same (regime, strategy) exists,
           the new claim supersedes it if its capped confidence is higher.
        认识论强制执行：
        1. 根据 evidence_source 限制信度上限
        2. 从 evidence_source 推导 CognitiveLevel（AI → 永不为 FACT）
        3. 从 evidence_source 计算 TTL
        4. 若相同 (regime, strategy) 下存在更高信度的活跃声明，
           仅当新声明的有上限信度更高时才替代旧声明。

        Args:
            pattern_text: Human-readable pattern description / 模式描述文字
            evidence_source: "statistical_N=XX" | "ai" | "manual"
            observation_count: Supporting observation count / 支持观察次数
            confidence: Raw confidence before capping / 截断前的原始信度
            applies_to_regime: Market regime scope / 适用 regime
            applies_to_strategy: Strategy scope / 适用策略
            claim_id: Optional explicit claim_id; auto-generated if not provided

        Returns:
            The claim_id of the registered claim.
            返回已登记声明的 claim_id。
        """
        # Step 1: Apply epistemic constraints / 应用认识论约束
        capped_confidence = _cap_confidence(confidence, evidence_source)
        cognitive_level = _derive_cognitive_level(evidence_source, capped_confidence)
        expires_at_ms = _compute_ttl_ms(evidence_source)
        now_ms = int(time.time() * 1000)
        cid = claim_id or f"claim_{uuid.uuid4().hex[:16]}"

        new_claim = PatternClaim(
            claim_id=cid,
            pattern_text=pattern_text,
            cognitive_level=cognitive_level,
            evidence_source=evidence_source,
            observation_count=observation_count,
            confidence=capped_confidence,
            applies_to_regime=applies_to_regime,
            applies_to_strategy=applies_to_strategy,
            created_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
        )

        with self._lock:
            # Step 2: Check for supersession — same (regime, strategy) slot
            # 步骤 2：检查替代 — 相同 (regime, strategy) 槽位
            supersede_id: Optional[str] = None
            for existing_id, existing_claim in self._claims.items():
                if (
                    existing_claim.is_active
                    and not existing_claim.is_expired(now_ms)
                    and existing_claim.applies_to_regime == applies_to_regime
                    and existing_claim.applies_to_strategy == applies_to_strategy
                    and existing_claim.confidence < capped_confidence
                ):
                    # New claim has higher confidence — supersede the existing one
                    # 新声明信度更高 — 替代现有声明
                    supersede_id = existing_id
                    break

            if supersede_id:
                # Mark old claim as superseded / 将旧声明标记为已替代
                self._claims[supersede_id].is_active = False
                self._claims[supersede_id].superseded_by = cid
                self._stats["total_superseded"] += 1
                logger.info(
                    "Claim %s superseded by %s (confidence %.3f → %.3f) / "
                    "声明 %s 被 %s 替代 (信度 %.3f → %.3f)",
                    supersede_id, cid,
                    self._claims[supersede_id].confidence, capped_confidence,
                    supersede_id, cid,
                    self._claims[supersede_id].confidence, capped_confidence,
                )

            self._claims[cid] = new_claim
            self._stats["total_registered"] += 1

        logger.debug(
            "Registered claim %s: level=%s confidence=%.3f regime=%s strategy=%s / "
            "已登记声明 %s：级别=%s 信度=%.3f regime=%s 策略=%s",
            cid, cognitive_level.value, capped_confidence, applies_to_regime, applies_to_strategy,
            cid, cognitive_level.value, capped_confidence, applies_to_regime, applies_to_strategy,
        )
        # Schedule debounced persistence so the new claim survives restarts
        # 调度去抖动持久化，确保新声明在重启后仍可恢复
        self._schedule_debounced_save()
        return cid

    # ── Query / 查询 ──

    def get_active_claims(
        self,
        regime: Optional[str] = None,
        strategy: Optional[str] = None,
        min_confidence: float = 0.0,
        cognitive_level: Optional[CognitiveLevel] = None,
    ) -> List[PatternClaim]:
        """Return active, non-expired claims matching the filters.
        返回符合过滤条件的活跃、未过期声明。

        Args:
            regime: Filter by regime ("all" matches everything) / 按 regime 过滤
            strategy: Filter by strategy ("all" matches everything) / 按策略过滤
            min_confidence: Minimum confidence threshold / 最低信度阈值
            cognitive_level: Exact CognitiveLevel match / 精确 CognitiveLevel 匹配

        Returns:
            Sorted list of matching PatternClaim objects (highest confidence first).
            按信度降序排列的匹配声明列表。
        """
        now_ms = int(time.time() * 1000)
        results: List[PatternClaim] = []

        with self._lock:
            for claim in self._claims.values():
                if not claim.is_active:
                    continue
                if claim.is_expired(now_ms):
                    continue
                if claim.confidence < min_confidence:
                    continue
                if cognitive_level is not None and claim.cognitive_level != cognitive_level:
                    continue
                # regime filter: "all" in stored claim or query matches stored value
                # regime 过滤：存储声明中的 "all" 或查询匹配存储值
                if regime is not None:
                    if claim.applies_to_regime != "all" and claim.applies_to_regime != regime:
                        continue
                # strategy filter: "all" in stored claim or query matches stored value
                # 策略过滤：存储声明中的 "all" 或查询匹配存储值
                if strategy is not None:
                    if claim.applies_to_strategy != "all" and claim.applies_to_strategy != strategy:
                        continue
                results.append(claim)

        # Sort by confidence descending / 按信度降序排列
        results.sort(key=lambda c: c.confidence, reverse=True)
        return results

    # ── Falsification / 证伪 ──

    def record_falsification(self, claim_id: str) -> None:
        """Record a contradicting observation against a claim.
        对一条声明记录一次矛盾观察（证伪）。

        If falsification_count reaches falsification_threshold:
        - INFERENCE claims are downgraded to HYPOTHESIS
        - HYPOTHESIS claims are deactivated
        若证伪次数达到 falsification_threshold：
        - INFERENCE 声明降级为 HYPOTHESIS
        - HYPOTHESIS 声明被停用

        Fail-closed: if claim_id not found, log and return silently.
        fail-closed：若 claim_id 未找到，记录日志后静默返回。
        """
        with self._lock:
            claim = self._claims.get(claim_id)
            if claim is None:
                # fail-closed: unknown claim → do nothing / fail-closed：未知声明 → 不做任何操作
                logger.debug("record_falsification: claim_id %s not found / 声明 %s 未找到", claim_id, claim_id)
                return

            claim.falsification_count += 1

            if claim.falsification_count >= claim.falsification_threshold:
                if claim.cognitive_level == CognitiveLevel.INFERENCE:
                    # Downgrade INFERENCE → HYPOTHESIS when threshold reached
                    # 达到阈值时将 INFERENCE 降级为 HYPOTHESIS
                    claim.cognitive_level = CognitiveLevel.HYPOTHESIS
                    self._stats["total_falsified"] += 1
                    logger.info(
                        "Claim %s downgraded INFERENCE→HYPOTHESIS (falsified %d times) / "
                        "声明 %s 降级 INFERENCE→HYPOTHESIS（已证伪 %d 次）",
                        claim_id, claim.falsification_count,
                        claim_id, claim.falsification_count,
                    )
                elif claim.cognitive_level == CognitiveLevel.HYPOTHESIS:
                    # Deactivate HYPOTHESIS claims that keep being falsified
                    # 停用持续被证伪的 HYPOTHESIS 声明
                    claim.is_active = False
                    self._stats["total_falsified"] += 1
                    logger.info(
                        "Claim %s deactivated (HYPOTHESIS falsified %d times) / "
                        "声明 %s 已停用（HYPOTHESIS 已证伪 %d 次）",
                        claim_id, claim.falsification_count,
                        claim_id, claim.falsification_count,
                    )
                # FACT claims are never downgraded automatically — human review required
                # FACT 声明不会自动降级 — 需要人工审查

    # ── Expiry cleanup / 过期清理 ──

    def expire_stale_claims(self) -> int:
        """Deactivate all claims that have passed their TTL.
        停用所有已超过 TTL 的声明。

        Returns:
            Number of claims expired in this call.
            本次调用中过期的声明数量。
        """
        now_ms = int(time.time() * 1000)
        expired_count = 0

        with self._lock:
            for claim in self._claims.values():
                if claim.is_active and claim.is_expired(now_ms):
                    claim.is_active = False
                    expired_count += 1
                    self._stats["total_expired"] += 1
                    logger.debug(
                        "Claim %s expired (TTL passed) / 声明 %s 已过期（TTL 已过）",
                        claim.claim_id, claim.claim_id,
                    )

        if expired_count > 0:
            logger.info(
                "expire_stale_claims: %d claims expired / 过期清理：%d 条声明已过期",
                expired_count, expired_count,
            )
        return expired_count

    # ── Stats / 统计 ──

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate statistics for the registry.
        返回存储中心的汇总统计数据。
        """
        with self._lock:
            active_count = sum(
                1 for c in self._claims.values()
                if c.is_active and not c.is_expired()
            )
            level_dist: Dict[str, int] = {}
            for c in self._claims.values():
                if c.is_active and not c.is_expired():
                    key = c.cognitive_level.value
                    level_dist[key] = level_dist.get(key, 0) + 1

            return {
                "total_claims": len(self._claims),
                "active_claims": active_count,
                "level_distribution": level_dist,
                **dict(self._stats),
            }

    # ── Serialization / 序列化 ──

    def to_snapshot(self) -> List[Dict[str, Any]]:
        """Serialize all claims to a list of dicts for persistence or audit.
        序列化所有声明为字典列表，用于持久化或审计。

        Returns all claims including inactive ones for full audit trail.
        返回所有声明（包括已停用的），以提供完整的审计追踪。
        """
        with self._lock:
            return [claim.to_dict() for claim in self._claims.values()]

    # ── Persistence / 持久化 ──

    def save_snapshot(self, path: str) -> bool:
        """Serialize all current claims to a JSON file at *path*.
        将当前所有声明序列化到 *path* 指定的 JSON 文件。

        Thread-safety design / 线程安全设计：
          1. 持锁读取声明数据，复制到局部列表后立即释放锁
             (Hold lock only to copy claim data; release before disk I/O)
          2. 磁盘 I/O 在锁外进行，不阻塞并发注册操作
             (Disk I/O outside the lock so concurrent register_claim() is not blocked)

        Principle 7 isolation / 原则 7 隔离：
          只序列化 PatternClaim 字段。不写入策略配置、风控阈值或任何实盘参数。
          Only PatternClaim fields are serialized. No strategy config, risk thresholds,
          or live trading parameters are written.

        Fail-open / fail-open（写失败不中断交易）：
          Any I/O or serialization error is caught, logged as WARNING, and returns False.
          任何 I/O 或序列化错误均被捕获，记录为 WARNING，返回 False。

        Returns:
            True on success, False on any exception.
            成功返回 True；任何异常返回 False。
        """
        # Step 1: read claims under lock, then release before I/O
        # 步骤 1：持锁读取声明数据，然后在 I/O 前释放锁
        with self._lock:
            data = [claim.to_dict() for claim in self._claims.values()]

        # Step 2: perform disk write outside the lock
        # 步骤 2：在锁外执行磁盘写入
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            logger.debug(
                "save_snapshot: wrote %d claims to %s / 快照已写入 %d 条声明至 %s",
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
        """Load claims from a JSON snapshot file and restore them into the registry.
        从 JSON 快照文件加载声明并恢复到存储中心。

        Behaviour / 行为：
          - Missing file  → log DEBUG, return 0 (no crash)
            文件不存在 → 记录 DEBUG，返回 0（不崩溃）
          - Corrupted JSON → log WARNING, return 0 (no crash)
            JSON 损坏 → 记录 WARNING，返回 0（不崩溃）
          - Existing claim_id → skip (do NOT overwrite newer in-memory data)
            已存在的 claim_id → 跳过（不覆盖内存中更新的数据）

        Principle 7 isolation / 原则 7 隔离：
          Only PatternClaim fields are read. No strategy or risk configuration
          is loaded or modified. Only PatternClaim 字段被读取，不加载或修改策略或风控配置。

        Returns:
            Count of claims successfully loaded (0 if file missing or corrupted).
            成功加载的声明数（文件缺失或损坏时返回 0）。
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

        # Step 3: restore claims, skipping any claim_id that already exists
        # 步骤 3：恢复声明，跳过已存在的 claim_id（不覆盖内存中更新的数据）
        loaded = 0
        with self._lock:
            for entry in raw:
                try:
                    cid = entry["claim_id"]
                    # Skip if already in registry — don't overwrite newer in-memory data
                    # 若已存在则跳过 — 不覆盖内存中更新的数据
                    if cid in self._claims:
                        continue
                    claim = PatternClaim(
                        claim_id=cid,
                        pattern_text=entry["pattern_text"],
                        cognitive_level=CognitiveLevel(entry["cognitive_level"]),
                        evidence_source=entry["evidence_source"],
                        observation_count=int(entry["observation_count"]),
                        confidence=float(entry["confidence"]),
                        applies_to_regime=entry["applies_to_regime"],
                        applies_to_strategy=entry["applies_to_strategy"],
                        created_at_ms=int(entry["created_at_ms"]),
                        expires_at_ms=int(entry["expires_at_ms"]),
                        is_active=bool(entry.get("is_active", True)),
                        superseded_by=entry.get("superseded_by"),
                        falsification_count=int(entry.get("falsification_count", 0)),
                        falsification_threshold=int(entry.get("falsification_threshold", 5)),
                    )
                    self._claims[cid] = claim
                    loaded += 1
                except (KeyError, TypeError, ValueError) as exc:
                    # Skip malformed entries, log warning
                    # 跳过格式错误的条目，记录警告
                    logger.warning(
                        "load_snapshot: skipping malformed entry %s: %s / "
                        "load_snapshot：跳过格式错误的条目 %s：%s",
                        entry.get("claim_id", "?"), exc,
                        entry.get("claim_id", "?"), exc,
                    )

        logger.debug(
            "load_snapshot: loaded %d claims from %s / 从 %s 加载了 %d 条声明",
            loaded, path, path, loaded,
        )
        return loaded

    # ── Debounced save internals / 去抖动保存内部实现 ──

    def _schedule_debounced_save(self) -> None:
        """Schedule a debounced background save, resetting the window on each call.
        调度去抖动后台保存；每次调用都重置防抖窗口。

        Design / 设计：
          - 使用 threading.Timer（非 asyncio），因为 TruthSourceRegistry 是纯同步代码。
            Uses threading.Timer (not asyncio) because TruthSourceRegistry is sync.
          - 若已有定时器挂起，先取消再重新调度（重置 30s 窗口）。
            If a timer is already pending, cancel it and reschedule (reset 30s window).
          - 定时器线程设为 daemon，进程退出时不阻塞。
            Timer thread is daemon so it won't block process exit.
          - 此方法本身非阻塞，不影响 register_claim() 主路径延迟。
            This method is non-blocking; it does not add latency to register_claim().

        Path for save file / 保存路径：
          OPENCLAW_TRUTH_REGISTRY_PATH env var → fallback: "settings/truth_registry_snapshot.json"
          环境变量 OPENCLAW_TRUTH_REGISTRY_PATH → 回退：相对路径
        """
        with self._lock:
            # Cancel any previously scheduled save (reset debounce window)
            # 取消之前已调度的保存（重置防抖窗口）
            if self._save_timer is not None:
                self._save_timer.cancel()

            # Resolve path at schedule time so env var changes are picked up
            # 在调度时解析路径，以便环境变量更改生效
            path = os.environ.get(
                "OPENCLAW_TRUTH_REGISTRY_PATH",
                "settings/truth_registry_snapshot.json",
            )
            # 30s debounce window: if many claims are registered quickly, only one save fires
            # 30s 防抖窗口：若快速注册多条声明，只触发一次保存
            timer = threading.Timer(30.0, self._do_save, args=(path,))
            timer.daemon = True  # don't block process exit / 不阻塞进程退出
            timer.start()
            self._save_timer = timer

    def _do_save(self, path: str) -> None:
        """Internal callback invoked by the debounce timer to persist the registry.
        去抖动定时器触发的内部回调，用于持久化存储。

        After the save completes (success or fail), clear self._save_timer so the
        next register_claim() call can schedule a fresh save.
        保存完成（成功或失败）后清除 self._save_timer，使下次 register_claim()
        可以调度新的保存。
        """
        # Delegate actual I/O to save_snapshot (fail-open, handles all exceptions)
        # 将实际 I/O 委托给 save_snapshot（fail-open，处理所有异常）
        self.save_snapshot(path)
        # Clear the timer reference after save completes
        # 保存完成后清除定时器引用
        with self._lock:
            self._save_timer = None
