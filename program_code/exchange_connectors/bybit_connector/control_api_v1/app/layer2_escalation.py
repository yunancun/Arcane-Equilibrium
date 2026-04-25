"""
Layer 2 Autonomous Escalation Rules — L0 → L1 → L2 escalation criteria
Layer 2 自主升級規則 — L0 → L1 → L2 升級準則

MODULE_NOTE (中文):
  G3-06 Phase A：本模組將「何時升級到更高推理層」的非正式啟發式規則正式化為
  可單元測試、可配置、預設關閉的純函數模組。

  三層推理架構（與 memory/project_layer2_agent_design.md 對齊）：
    - L0  Deterministic gate（H0 / Guardian / cost_gate）— 永遠運行，零成本
    - L1  Local LLM（Ollama / LM Studio / Haiku triage）— 快速便宜推理
    - L2  Cloud LLM（Claude Sonnet / Opus）— 重要但稀疏的高階推理

  本模組職責：
    1. 提供確定性升級決策函數 `decide_escalation_tier(context)`
    2. 提供可注入配置 dataclass `LayerEscalationConfig`（含預設閾值）
    3. 預設不接線 hot path（Phase A 純骨架，預設行為 = 全程 L0）
    4. 完整 trace：返回的 `EscalationDecision` 含 `reasons: List[str]`
       明文紀錄為什麼升級或為什麼留住

  Phase B（後續）：將本模組接入 `multi_agent_framework.py` decision dispatch。
  Phase A 不動 hot path，只提供 module + config + tests。

  根原則對應：
    - #6 失敗默認收縮 — 任一輸入缺失 → 留在 L0（最便宜）
    - #13 AI 資源成本感知 — daily L2 call cap + cost_edge_ratio gate
    - #15 多 Agent 協作 — 為 ExecutorAgent shadow→live 仲裁鋪路

MODULE_NOTE (English):
  G3-06 Phase A: codifies the previously-informal escalation heuristics
  (L0 → L1 → L2) into a pure-function, unit-testable, configurable
  module that DEFAULTS OFF (existing pass-through behavior preserved).

  Three reasoning tiers (aligned with memory/project_layer2_agent_design.md):
    - L0  Deterministic gates (H0 / Guardian / cost_gate) — always-on, zero cost
    - L1  Local LLM (Ollama / LM Studio / Haiku triage) — cheap, fast
    - L2  Cloud LLM (Claude Sonnet / Opus) — high-stakes, infrequent

  Responsibilities:
    1. Pure function `decide_escalation_tier(context)` returning a
       `EscalationDecision` with `target_tier`, `reasons`, `budget_estimate_usd`.
    2. Injectable `LayerEscalationConfig` dataclass holding all thresholds.
    3. NOT wired into hot path this commit — Phase A scaffolding only.
    4. Full trace: every escalation reason is appended to `reasons` so
       downstream audit / logging can replay the decision deterministically.

  Phase B (later): wire into `multi_agent_framework.py` decision dispatch.

  Root principle alignment:
    - #6 fail closed   — any missing input → stay at L0 (cheapest tier)
    - #13 AI cost aware — daily L2 call cap + cost_edge_ratio gate
    - #15 multi-agent  — paves the way for Executor shadow→live arbitration

  Allowed imports: stdlib only (dataclasses, enum, typing, os, logging).
  Forbidden imports: layer2_engine / strategist_agent / executor_agent /
                     multi_agent_framework (avoid circular imports — this
                     module is meant to be a pure leaf).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enum & Dataclasses / 枚舉與資料類
# ═══════════════════════════════════════════════════════════════════════════════


class EscalationTier(str, Enum):
    """
    Reasoning tier ordinal: L0 < L1 < L2.
    推理層序：L0 < L1 < L2。

    Comparable via `tier_rank()` helper.
    透過 `tier_rank()` 輔助函數可比較大小。
    """

    L0_DETERMINISTIC = "l0_deterministic"
    L1_LOCAL_LLM = "l1_local_llm"
    L2_CLOUD_LLM = "l2_cloud_llm"


def tier_rank(tier: EscalationTier) -> int:
    """Return numeric rank (0/1/2) for ordering / 返回數值排序。"""
    return {
        EscalationTier.L0_DETERMINISTIC: 0,
        EscalationTier.L1_LOCAL_LLM: 1,
        EscalationTier.L2_CLOUD_LLM: 2,
    }[tier]


@dataclass
class LayerEscalationConfig:
    """
    Thresholds for L0→L1→L2 escalation decisions.
    L0→L1→L2 升級判斷的閾值組。

    All thresholds are conservative defaults; operator can override via
    env vars (see `from_env()`) or by passing a custom instance to
    `decide_escalation_tier(context, config=...)`.

    所有閾值為保守預設值；operator 可透過 env var 覆蓋（見 `from_env()`）
    或透過 `decide_escalation_tier(context, config=...)` 傳入自訂實例。
    """

    # L1 trigger thresholds / L1 觸發閾值
    l1_signal_min: float = 0.5
    """signal_strength ≥ this → escalate to L1 / 信號強度高於此值升級到 L1"""

    l1_position_min_usdt: float = 50.0
    """position_notional_usdt ≥ this → escalate to L1 / 倉位名目額高於此值升級到 L1"""

    # L2 trigger thresholds / L2 觸發閾值
    l2_position_min_usdt: float = 500.0
    """position_notional_usdt ≥ this AND L1 uncertain → L2 / L1 不確定且倉位高於此值升級到 L2"""

    l2_cost_edge_max: float = 0.8
    """cost_edge_ratio ≥ this → L2 (DOC-01 #13 close-out trigger) / 成本邊際比高於此值升級到 L2"""

    l2_news_severity_min: float = 0.7
    """news_severity_recent ≥ this AND L1 uncertain → L2 / 新聞嚴重度高於此值且 L1 不確定升級到 L2"""

    # Hard ceilings / 硬上限
    l2_calls_24h_cap: int = 10
    """Hard cap: never escalate to L2 if 24h call count exceeds this / 24 小時 L2 調用硬上限"""

    l2_min_budget_usd: float = 0.50
    """Minimum remaining budget required for an L2 call / L2 呼叫所需最低剩餘預算"""

    # Master switch / 總開關
    enabled: bool = False
    """Phase A default: OFF — pass-through, all decisions return L0 / Phase A 預設關閉"""

    @classmethod
    def from_env(cls) -> "LayerEscalationConfig":
        """
        Build config from environment variables (operator override path).
        從環境變數建構配置（operator 覆蓋路徑）。

        Env vars (all optional, fall back to dataclass defaults):
          OPENCLAW_L2_ESCALATION_ENABLED          — "1"/"true" 啟用
          OPENCLAW_L2_ESCALATION_L1_SIGNAL_MIN    — float
          OPENCLAW_L2_ESCALATION_L1_POSITION_MIN  — float (USDT)
          OPENCLAW_L2_ESCALATION_L2_POSITION_MIN  — float (USDT)
          OPENCLAW_L2_ESCALATION_L2_COST_EDGE_MAX — float
          OPENCLAW_L2_ESCALATION_L2_NEWS_MIN      — float
          OPENCLAW_L2_ESCALATION_L2_CALLS_CAP     — int
          OPENCLAW_L2_ESCALATION_L2_MIN_BUDGET    — float (USD)
        """

        def _f(env_name: str, default: float) -> float:
            raw = os.getenv(env_name)
            if raw is None or raw == "":
                return default
            try:
                return float(raw)
            except ValueError:
                logger.warning(
                    "LayerEscalationConfig: bad float in %s=%r, using default %s / "
                    "環境變數格式錯誤，使用預設值",
                    env_name,
                    raw,
                    default,
                )
                return default

        def _i(env_name: str, default: int) -> int:
            raw = os.getenv(env_name)
            if raw is None or raw == "":
                return default
            try:
                return int(raw)
            except ValueError:
                logger.warning(
                    "LayerEscalationConfig: bad int in %s=%r, using default %s",
                    env_name,
                    raw,
                    default,
                )
                return default

        def _b(env_name: str, default: bool) -> bool:
            raw = os.getenv(env_name)
            if raw is None or raw == "":
                return default
            return raw.strip().lower() in ("1", "true", "yes", "on")

        return cls(
            enabled=_b("OPENCLAW_L2_ESCALATION_ENABLED", False),
            l1_signal_min=_f("OPENCLAW_L2_ESCALATION_L1_SIGNAL_MIN", 0.5),
            l1_position_min_usdt=_f("OPENCLAW_L2_ESCALATION_L1_POSITION_MIN", 50.0),
            l2_position_min_usdt=_f("OPENCLAW_L2_ESCALATION_L2_POSITION_MIN", 500.0),
            l2_cost_edge_max=_f("OPENCLAW_L2_ESCALATION_L2_COST_EDGE_MAX", 0.8),
            l2_news_severity_min=_f("OPENCLAW_L2_ESCALATION_L2_NEWS_MIN", 0.7),
            l2_calls_24h_cap=_i("OPENCLAW_L2_ESCALATION_L2_CALLS_CAP", 10),
            l2_min_budget_usd=_f("OPENCLAW_L2_ESCALATION_L2_MIN_BUDGET", 0.50),
        )


@dataclass
class EscalationDecision:
    """
    Output of `decide_escalation_tier`.
    `decide_escalation_tier` 的輸出結構。

    Always carries `reasons` — the audit trail of *why* this tier was chosen.
    永遠攜帶 `reasons` — 為何選此層的審計痕跡。
    """

    target_tier: EscalationTier
    reasons: List[str] = field(default_factory=list)
    budget_estimate_usd: float = 0.0
    """Estimated cost if the chosen tier actually fires / 選定層級實際觸發的預估成本"""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_tier": self.target_tier.value,
            "reasons": list(self.reasons),
            "budget_estimate_usd": self.budget_estimate_usd,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Decision function / 決策函數
# ═══════════════════════════════════════════════════════════════════════════════

# Rough budget estimates for the chosen tier — used for downstream UI / accounting.
# 各層級的粗略預算估算 — 供下游 UI / 帳務使用。
_BUDGET_ESTIMATE_L0_USD: float = 0.0
_BUDGET_ESTIMATE_L1_USD: float = 0.01  # local LLM / Haiku ~ near-zero, ~$0.01 ceiling
_BUDGET_ESTIMATE_L2_USD: float = 1.00  # Sonnet/Opus session typical ~$0.50-2.00


def decide_escalation_tier(
    context: Optional[Dict[str, Any]] = None,
    config: Optional[LayerEscalationConfig] = None,
) -> EscalationDecision:
    """
    Pure function: decide which reasoning tier the system should escalate to.
    純函數：判斷系統應升級到哪一個推理層級。

    Args:
        context: dict containing decision inputs. All keys are OPTIONAL.
                 缺值的鍵預設為 0 / False / 空字串（fail-closed → 留 L0）。
            - signal_strength (float, 0..1)        — H0/H1 信號強度
            - signal_confidence (float, 0..1)      — H1 置信度
            - position_notional_usdt (float ≥ 0)   — 當前曝險名目額
            - cost_edge_ratio (float ≥ 0)          — DOC-01 #13 cost_edge 比率
            - recent_l2_calls_24h (int ≥ 0)        — 過去 24 小時 L2 呼叫數
            - news_severity_recent (float, 0..1)   — 最近新聞嚴重度
            - agent_uncertainty_flag (bool)        — L1 是否回報「不確定」
            - l2_budget_remaining_usd (float ≥ 0)  — 今日 L2 剩餘預算
        config:  injectable thresholds; defaults via `LayerEscalationConfig()`.
                 可注入閾值；預設為 `LayerEscalationConfig()`。

    Returns:
        `EscalationDecision`. When `config.enabled=False`, ALWAYS returns L0
        with reason "escalation_disabled" — preserves current pass-through
        behavior (Phase A safety contract).

        當 `config.enabled=False`，永遠回傳 L0 + reason "escalation_disabled" —
        保留當前 pass-through 行為（Phase A 安全契約）。

    Decision rules (when enabled):
        1. Default → L0_DETERMINISTIC
        2. Escalate to L1 if any of:
             - signal_strength ≥ config.l1_signal_min
             - position_notional_usdt ≥ config.l1_position_min_usdt
        3. Escalate to L2 if all of:
             - L1 was already chosen above (uncertainty / material context)
             - agent_uncertainty_flag == True
             - at least ONE of:
                 - position_notional_usdt ≥ config.l2_position_min_usdt
                 - cost_edge_ratio ≥ config.l2_cost_edge_max
                 - news_severity_recent ≥ config.l2_news_severity_min
             - recent_l2_calls_24h < config.l2_calls_24h_cap
             - l2_budget_remaining_usd ≥ config.l2_min_budget_usd
        4. Hard ceiling: if calls_cap exceeded OR budget below min,
           DOWNGRADE the would-be-L2 to L1 with explicit "budget_cap_*" reason.

        當啟用時的決策規則（中文）：
          1. 預設 → L0
          2. 任一條件成立升級到 L1：信號強度足夠 OR 倉位曝險足夠
          3. 滿足以下全部條件升級到 L2：已升 L1 + agent 表示不確定 + 至少一
             個重大風險訊號（倉位 / cost_edge / 新聞嚴重度）+ 在預算內 + 在
             呼叫數上限內
          4. 硬上限：超過 24h 呼叫上限或預算不足 → 強降回 L1，明確記錄
             "budget_cap_*" reason（根原則 #6 失敗默認收縮 + #13 成本感知）
    """
    if config is None:
        config = LayerEscalationConfig()

    if context is None:
        context = {}

    # Phase A safety contract: when disabled, pass-through to L0.
    # Phase A 安全契約：未啟用時 pass-through 到 L0。
    if not config.enabled:
        return EscalationDecision(
            target_tier=EscalationTier.L0_DETERMINISTIC,
            reasons=["escalation_disabled"],
            budget_estimate_usd=_BUDGET_ESTIMATE_L0_USD,
        )

    reasons: List[str] = []

    # ── Pull inputs (all default-safe) / 取輸入（缺值安全） ──
    signal_strength = _safe_float(context.get("signal_strength"), default=0.0)
    position_notional = _safe_float(context.get("position_notional_usdt"), default=0.0)
    cost_edge_ratio = _safe_float(context.get("cost_edge_ratio"), default=0.0)
    recent_l2_calls = _safe_int(context.get("recent_l2_calls_24h"), default=0)
    news_severity = _safe_float(context.get("news_severity_recent"), default=0.0)
    agent_uncertainty = bool(context.get("agent_uncertainty_flag", False))
    budget_remaining = _safe_float(context.get("l2_budget_remaining_usd"), default=0.0)

    # ── Stage 1: Decide L0 vs L1 / 階段一：決定 L0 vs L1 ──
    l1_triggered = False
    if signal_strength >= config.l1_signal_min:
        l1_triggered = True
        reasons.append(
            f"signal_strength={signal_strength:.3f}>=l1_signal_min={config.l1_signal_min:.3f}"
        )
    if position_notional >= config.l1_position_min_usdt:
        l1_triggered = True
        reasons.append(
            f"position_notional={position_notional:.2f}>=l1_position_min={config.l1_position_min_usdt:.2f}"
        )

    if not l1_triggered:
        reasons.append("no_l1_trigger_default_l0")
        return EscalationDecision(
            target_tier=EscalationTier.L0_DETERMINISTIC,
            reasons=reasons,
            budget_estimate_usd=_BUDGET_ESTIMATE_L0_USD,
        )

    # ── Stage 2: Decide L1 vs L2 / 階段二：決定 L1 vs L2 ──
    # Pre-condition for L2: L1 already chosen + agent reported uncertainty.
    # L2 前置條件：已選 L1 + agent 回報不確定。
    if not agent_uncertainty:
        reasons.append("agent_uncertainty_flag=false_stay_l1")
        return EscalationDecision(
            target_tier=EscalationTier.L1_LOCAL_LLM,
            reasons=reasons,
            budget_estimate_usd=_BUDGET_ESTIMATE_L1_USD,
        )

    # Material-risk OR-gate: at least one heavy signal must fire.
    # 重大風險 OR 閘：至少一個重訊號需要觸發。
    l2_signals: List[str] = []
    if position_notional >= config.l2_position_min_usdt:
        l2_signals.append(
            f"position_notional={position_notional:.2f}>=l2_position_min={config.l2_position_min_usdt:.2f}"
        )
    if cost_edge_ratio >= config.l2_cost_edge_max:
        l2_signals.append(
            f"cost_edge_ratio={cost_edge_ratio:.3f}>=l2_cost_edge_max={config.l2_cost_edge_max:.3f}"
        )
    if news_severity >= config.l2_news_severity_min:
        l2_signals.append(
            f"news_severity={news_severity:.3f}>=l2_news_min={config.l2_news_severity_min:.3f}"
        )

    if not l2_signals:
        reasons.append("uncertain_but_no_material_risk_signal_stay_l1")
        return EscalationDecision(
            target_tier=EscalationTier.L1_LOCAL_LLM,
            reasons=reasons,
            budget_estimate_usd=_BUDGET_ESTIMATE_L1_USD,
        )

    reasons.extend(l2_signals)

    # ── Stage 3: Hard ceilings (fail-closed) / 階段三：硬上限（失敗默認收縮） ──
    if recent_l2_calls >= config.l2_calls_24h_cap:
        reasons.append(
            f"budget_cap_l2_calls_24h={recent_l2_calls}>=cap={config.l2_calls_24h_cap}_downgrade_to_l1"
        )
        return EscalationDecision(
            target_tier=EscalationTier.L1_LOCAL_LLM,
            reasons=reasons,
            budget_estimate_usd=_BUDGET_ESTIMATE_L1_USD,
        )

    if budget_remaining < config.l2_min_budget_usd:
        reasons.append(
            f"budget_cap_remaining={budget_remaining:.4f}<min={config.l2_min_budget_usd:.4f}_downgrade_to_l1"
        )
        return EscalationDecision(
            target_tier=EscalationTier.L1_LOCAL_LLM,
            reasons=reasons,
            budget_estimate_usd=_BUDGET_ESTIMATE_L1_USD,
        )

    # All gates green → escalate to L2.
    # 全閘綠 → 升級到 L2。
    reasons.append("all_l2_gates_passed")
    return EscalationDecision(
        target_tier=EscalationTier.L2_CLOUD_LLM,
        reasons=reasons,
        budget_estimate_usd=_BUDGET_ESTIMATE_L2_USD,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers / 內部輔助
# ═══════════════════════════════════════════════════════════════════════════════


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; on failure return default (fail-closed) / 安全轉 float。"""
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    # Reject NaN / Inf — they corrupt comparisons silently.
    # 拒絕 NaN / Inf — 會靜默破壞比較。
    if result != result or result in (float("inf"), float("-inf")):
        return default
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce to int; on failure return default / 安全轉 int。"""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "EscalationTier",
    "EscalationDecision",
    "LayerEscalationConfig",
    "decide_escalation_tier",
    "tier_rank",
]
