"""
Four-Stage Delegation Framework / 四階段放權框架

MODULE_NOTE (中文):
  四階段放權框架 — 管理 Agent 從完全人工控制到完全自主的遞進放權。
  原則 11（Agent 最大自主權）與原則 5（生存 > 利潤）的平衡。
  四個階段：
    Stage 1: Full Human Control — 所有交易由人工執行
    Stage 2: AI Suggests, Human Approves — AI 提建議，人工批准後執行
    Stage 3: AI Acts, Human Can Veto — AI 自主行動，人工可在窗口期否決
    Stage 4: Full AI Autonomy — 完全 AI 自主（需 Operator 明確批准升級）
  每次升級需滿足升級條件，降級可自動觸發（原則 6：失敗默認收縮）。

MODULE_NOTE (English):
  Four-stage delegation framework — manages progressive delegation from
  full human control to full AI autonomy.
  Balance between Principle 11 (max agent autonomy) and Principle 5 (survival > profit).
  Stages:
    Stage 1: Full Human Control — all trades executed by human
    Stage 2: AI Suggests, Human Approves — AI proposes, human approves before execution
    Stage 3: AI Acts, Human Can Veto — AI acts autonomously, human can veto in window
    Stage 4: Full AI Autonomy — full AI autonomy (requires explicit operator approval)
  Each upgrade requires meeting conditions; downgrades can auto-trigger (Principle 6).

Governance references:
  Principle 5: Survival > Profit — downgrades always available
  Principle 6: Fail-closed contraction — uncertain → default conservative
  Principle 11: Max agent autonomy — within P0/P1 hard boundaries
  CLAUDE.md §四: system_mode=demo_only, execution_authority=not_granted
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums / 枚舉
# ═══════════════════════════════════════════════════════════════════════════════

class DelegationStage(str, Enum):
    """
    Four stages of delegation / 四階段放權等級

    FULL_HUMAN:   Stage 1 — Human executes all trades / 人工執行所有交易
    AI_SUGGEST:   Stage 2 — AI suggests, human approves / AI 建議，人工批准
    AI_ACT_VETO:  Stage 3 — AI acts, human can veto / AI 行動，人工可否決
    FULL_AI:      Stage 4 — Full AI autonomy / 完全 AI 自主
    """
    FULL_HUMAN = "full_human"
    AI_SUGGEST = "ai_suggest"
    AI_ACT_VETO = "ai_act_veto"
    FULL_AI = "full_ai"


# Ordered list for upgrade/downgrade logic / 排序列表用於升降級邏輯
_STAGE_ORDER: list[DelegationStage] = [
    DelegationStage.FULL_HUMAN,
    DelegationStage.AI_SUGGEST,
    DelegationStage.AI_ACT_VETO,
    DelegationStage.FULL_AI,
]

_STAGE_INDEX: dict[DelegationStage, int] = {s: i for i, s in enumerate(_STAGE_ORDER)}


# ═══════════════════════════════════════════════════════════════════════════════
# Upgrade conditions / 升級條件定義
# ═══════════════════════════════════════════════════════════════════════════════

# Each condition: (metric_key, comparator, threshold, description_en, description_zh)
# 每個條件：(指標鍵, 比較器, 閾值, 英文描述, 中文描述)
_UPGRADE_CONDITIONS: dict[DelegationStage, list[tuple[str, str, Any, str, str]]] = {
    # Stage 1 → 2: paper trading 7+ days, zero critical incidents
    # 階段 1 → 2：紙盤交易 7+ 天，零嚴重事件
    DelegationStage.AI_SUGGEST: [
        ("paper_trading_days", ">=", 7,
         "Paper trading for at least 7 days",
         "紙盤交易至少 7 天"),
        ("critical_incidents", "==", 0,
         "Zero critical incidents",
         "零嚴重事件"),
    ],
    # Stage 2 → 3: paper 14+ days, approval rate >= 95%, avg response < 2s
    # 階段 2 → 3：紙盤 14+ 天，批准率 >= 95%，平均回應 < 2s
    DelegationStage.AI_ACT_VETO: [
        ("paper_trading_days", ">=", 14,
         "Paper trading for at least 14 days",
         "紙盤交易至少 14 天"),
        ("approval_rate", ">=", 95.0,
         "Approval rate >= 95%",
         "批准率 >= 95%"),
        ("avg_response_time_s", "<", 2.0,
         "Average response time < 2 seconds",
         "平均回應時間 < 2 秒"),
    ],
    # Stage 3 → 4: paper 21+ days, no veto in 7 days, positive PnL
    # 階段 3 → 4：紙盤 21+ 天，7 天內無否決，正 PnL
    DelegationStage.FULL_AI: [
        ("paper_trading_days", ">=", 21,
         "Paper trading for at least 21 days",
         "紙盤交易至少 21 天"),
        ("days_since_last_veto", ">=", 7,
         "No veto in the last 7 days",
         "7 天內無否決"),
        ("pnl_positive", "==", True,
         "Cumulative PnL is positive",
         "累計 PnL 為正"),
    ],
}


def _check_condition(value: Any, comparator: str, threshold: Any) -> bool:
    """
    Evaluate a single condition against a metric value.
    評估單個條件是否滿足。

    Returns True if condition is met, False otherwise.
    返回 True 表示條件滿足，False 表示不滿足。
    """
    if value is None:
        return False  # Missing metric = condition not met / 缺失指標 = 條件不滿足
    if comparator == ">=":
        return value >= threshold
    if comparator == "==":
        return value == threshold
    if comparator == "<":
        return value < threshold
    if comparator == ">":
        return value > threshold
    if comparator == "<=":
        return value <= threshold
    logger.warning("Unknown comparator '%s', failing closed / 未知比較器，fail-closed", comparator)
    return False  # Fail-closed: unknown comparator → not met / 未知比較器 → 不滿足


# ═══════════════════════════════════════════════════════════════════════════════
# DelegationFramework / 放權框架主類
# ═══════════════════════════════════════════════════════════════════════════════

class DelegationFramework:
    """
    Four-stage progressive delegation manager.
    四階段遞進式放權管理器。

    Thread-safe. Persists state to JSON file.
    線程安全。狀態持久化到 JSON 文件。

    Usage / 使用方式:
        fw = DelegationFramework()
        fw.update_metrics({"paper_trading_days": 10, "critical_incidents": 0})
        can, unmet = fw.can_upgrade()
        if can:
            result = fw.request_upgrade()
    """

    # Default veto window for Stage 3 (ms) / 階段 3 默認否決窗口（毫秒）
    VETO_WINDOW_MS: int = 30_000

    def __init__(
        self,
        initial_stage: str = "full_human",
        state_dir: Optional[str] = None,
    ) -> None:
        """
        Initialize the delegation framework.
        初始化放權框架。

        Args:
            initial_stage: Starting stage (default: full_human).
                           Only used if no persisted state exists.
                           初始階段（默認：full_human），僅在無持久化狀態時使用。
            state_dir: Directory for state persistence; uses OPENCLAW_RUNTIME_DIR
                       env var if None. 狀態持久化目錄；為 None 時使用環境變量。
        """
        self._lock = threading.Lock()
        self._metrics: dict[str, Any] = {}
        self._stage_history: list[dict[str, Any]] = []

        # State file path — no hardcoded paths (cross-platform rule)
        # 狀態文件路徑 — 不硬編碼路徑（跨平台規則）
        if state_dir is None:
            state_dir = os.environ.get(
                "OPENCLAW_RUNTIME_DIR",
                os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime")),
            )
        self._state_dir = Path(state_dir)
        self._state_path = self._state_dir / "delegation_state.json"

        # Load persisted state or initialize / 載入持久化狀態或初始化
        loaded = self._load()
        if not loaded:
            try:
                self._stage = DelegationStage(initial_stage)
            except ValueError:
                logger.warning(
                    "Invalid initial_stage '%s', defaulting to full_human / "
                    "無效初始階段，默認 full_human",
                    initial_stage,
                )
                self._stage = DelegationStage.FULL_HUMAN
            self._save()

        logger.info(
            "DelegationFramework initialized at stage=%s / 放權框架初始化，階段=%s",
            self._stage.value, self._stage.value,
        )

    # ───────────────────────────────────────────────────────────────────────
    # Properties / 屬性
    # ───────────────────────────────────────────────────────────────────────

    @property
    def current_stage(self) -> DelegationStage:
        """Current delegation stage / 當前放權階段"""
        with self._lock:
            return self._stage

    # ───────────────────────────────────────────────────────────────────────
    # Upgrade logic / 升級邏輯
    # ───────────────────────────────────────────────────────────────────────

    def can_upgrade(self) -> tuple[bool, list[str]]:
        """
        Check if current stage can be upgraded.
        檢查當前階段是否可升級。

        Returns:
            (can_upgrade: bool, unmet_conditions: list[str])
            (是否可升級, 不滿足條件的描述列表)
        """
        with self._lock:
            return self._can_upgrade_locked()

    def _can_upgrade_locked(self) -> tuple[bool, list[str]]:
        """Internal upgrade check (caller must hold lock). / 內部升級檢查（調用者需持鎖）。"""
        idx = _STAGE_INDEX[self._stage]
        if idx >= len(_STAGE_ORDER) - 1:
            return False, ["Already at maximum stage (FULL_AI) / 已在最高階段"]

        next_stage = _STAGE_ORDER[idx + 1]
        conditions = _UPGRADE_CONDITIONS.get(next_stage, [])
        unmet: list[str] = []

        for metric_key, comparator, threshold, desc_en, desc_zh in conditions:
            value = self._metrics.get(metric_key)
            if not _check_condition(value, comparator, threshold):
                current_val = value if value is not None else "N/A"
                unmet.append(f"{desc_en} / {desc_zh} (current={current_val}, need {comparator} {threshold})")

        return len(unmet) == 0, unmet

    def request_upgrade(self, operator_approved: bool = False) -> dict[str, Any]:
        """
        Request an upgrade to the next delegation stage.
        請求升級到下一個放權階段。

        Stage 3→4 (FULL_AI) requires operator_approved=True.
        階段 3→4（完全自主）必須 operator_approved=True。

        Args:
            operator_approved: Whether the operator has explicitly approved.
                               Operator 是否已明確批准。

        Returns:
            {"success": bool, "new_stage": str, ...} or
            {"success": False, "reason": str, "unmet_conditions": [...]}
        """
        with self._lock:
            can, unmet = self._can_upgrade_locked()

            if not can:
                return {
                    "success": False,
                    "reason": "Upgrade conditions not met / 升級條件不滿足",
                    "current_stage": self._stage.value,
                    "unmet_conditions": unmet,
                }

            idx = _STAGE_INDEX[self._stage]
            next_stage = _STAGE_ORDER[idx + 1]

            # Stage 3→4 requires explicit operator approval (Principle 11 + safety)
            # 階段 3→4 需要 Operator 明確批准（原則 11 + 安全性）
            if next_stage == DelegationStage.FULL_AI and not operator_approved:
                return {
                    "success": False,
                    "reason": "Upgrade to FULL_AI requires explicit operator approval / "
                              "升級到完全自主需要 Operator 明確批准",
                    "current_stage": self._stage.value,
                    "unmet_conditions": [],
                }

            old_stage = self._stage
            self._stage = next_stage
            ts = datetime.now(timezone.utc).isoformat()

            history_entry = {
                "timestamp": ts,
                "old_stage": old_stage.value,
                "new_stage": next_stage.value,
                "reason": f"Upgrade approved (operator_approved={operator_approved})",
                "direction": "upgrade",
            }
            self._stage_history.append(history_entry)
            self._save()

            logger.info(
                "Delegation upgraded: %s → %s / 放權升級：%s → %s",
                old_stage.value, next_stage.value,
                old_stage.value, next_stage.value,
            )

            return {
                "success": True,
                "old_stage": old_stage.value,
                "new_stage": next_stage.value,
                "timestamp": ts,
                "operator_approved": operator_approved,
            }

    # ───────────────────────────────────────────────────────────────────────
    # Downgrade logic / 降級邏輯
    # ───────────────────────────────────────────────────────────────────────

    def auto_downgrade(self, reason: str) -> dict[str, Any]:
        """
        Auto-downgrade to Stage 1 (FULL_HUMAN). Principle 6: fail-closed contraction.
        自動降級到階段 1（完全人工控制）。原則 6：失敗默認收縮。

        Triggered by external callers on: critical risk events, system failures,
        significant losses.
        由外部調用觸發：嚴重風控事件、系統故障、大幅虧損。

        Args:
            reason: Reason for downgrade / 降級原因

        Returns:
            {"success": True, "old_stage": ..., "new_stage": "full_human", ...}
        """
        with self._lock:
            old_stage = self._stage

            if old_stage == DelegationStage.FULL_HUMAN:
                return {
                    "success": True,
                    "old_stage": old_stage.value,
                    "new_stage": old_stage.value,
                    "reason": "Already at FULL_HUMAN, no downgrade needed / 已在最低階段",
                    "was_downgraded": False,
                }

            self._stage = DelegationStage.FULL_HUMAN
            ts = datetime.now(timezone.utc).isoformat()

            history_entry = {
                "timestamp": ts,
                "old_stage": old_stage.value,
                "new_stage": DelegationStage.FULL_HUMAN.value,
                "reason": f"Auto-downgrade: {reason}",
                "direction": "downgrade",
            }
            self._stage_history.append(history_entry)
            self._save()

            logger.warning(
                "Delegation auto-downgraded: %s → FULL_HUMAN reason='%s' / "
                "放權自動降級：%s → FULL_HUMAN 原因='%s'",
                old_stage.value, reason, old_stage.value, reason,
            )

            return {
                "success": True,
                "old_stage": old_stage.value,
                "new_stage": DelegationStage.FULL_HUMAN.value,
                "reason": reason,
                "timestamp": ts,
                "was_downgraded": True,
            }

    # ───────────────────────────────────────────────────────────────────────
    # Permission check / 權限檢查
    # ───────────────────────────────────────────────────────────────────────

    def check_action_permission(self, action_type: str) -> dict[str, Any]:
        """
        Check if an action is permitted under the current delegation stage.
        根據當前放權階段判斷動作是否允許。

        Args:
            action_type: Type of action being requested (e.g. "open_position",
                         "close_position", "modify_stop"). 請求的動作類型。

        Returns:
            Stage 1: {"allowed": False, "requires": "human_execution"}
            Stage 2: {"allowed": False, "requires": "human_approval", "suggestion": True}
            Stage 3: {"allowed": True, "veto_window_ms": 30000}
            Stage 4: {"allowed": True}
        """
        with self._lock:
            stage = self._stage

        base = {"stage": stage.value, "action_type": action_type}

        if stage == DelegationStage.FULL_HUMAN:
            # Stage 1: AI cannot act; human must execute / AI 不能行動，人工必須執行
            return {**base, "allowed": False, "requires": "human_execution"}

        if stage == DelegationStage.AI_SUGGEST:
            # Stage 2: AI can suggest, human must approve / AI 可建議，人工必須批准
            return {**base, "allowed": False, "requires": "human_approval", "suggestion": True}

        if stage == DelegationStage.AI_ACT_VETO:
            # Stage 3: AI can act, human has veto window / AI 可行動，人工有否決窗口
            return {**base, "allowed": True, "veto_window_ms": self.VETO_WINDOW_MS}

        if stage == DelegationStage.FULL_AI:
            # Stage 4: Full autonomy / 完全自主
            return {**base, "allowed": True}

        # Fail-closed: unknown stage → deny / 未知階段 → 拒絕
        logger.error("Unknown stage '%s', denying action (fail-closed) / 未知階段，拒絕動作", stage)
        return {**base, "allowed": False, "requires": "human_execution", "error": "unknown_stage"}

    # ───────────────────────────────────────────────────────────────────────
    # Metrics / 指標更新
    # ───────────────────────────────────────────────────────────────────────

    def update_metrics(self, metrics: dict[str, Any]) -> None:
        """
        Update tracked metrics used for upgrade condition evaluation.
        更新用於升級條件評估的追蹤指標。

        Supported keys / 支持的指標鍵:
          paper_trading_days (int), critical_incidents (int),
          approval_rate (float, 0-100), avg_response_time_s (float),
          days_since_last_veto (int), pnl_positive (bool)

        Args:
            metrics: Dict of metric key-value pairs / 指標鍵值對字典
        """
        with self._lock:
            self._metrics.update(metrics)
            self._save()
            logger.debug(
                "Delegation metrics updated: %s / 放權指標已更新",
                list(metrics.keys()),
            )

    # ───────────────────────────────────────────────────────────────────────
    # Status / 狀態查詢
    # ───────────────────────────────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """
        Get complete framework status.
        獲取完整框架狀態。

        Returns dict with stage, metrics, can_upgrade info, and recent history.
        返回包含階段、指標、可升級信息和近期歷史的字典。
        """
        with self._lock:
            can, unmet = self._can_upgrade_locked()
            idx = _STAGE_INDEX[self._stage]
            next_stage = _STAGE_ORDER[idx + 1].value if idx < len(_STAGE_ORDER) - 1 else None

            return {
                "current_stage": self._stage.value,
                "stage_index": idx,
                "stage_label": {
                    DelegationStage.FULL_HUMAN: "Full Human Control / 完全人工控制",
                    DelegationStage.AI_SUGGEST: "AI Suggests, Human Approves / AI 建議，人工批准",
                    DelegationStage.AI_ACT_VETO: "AI Acts, Human Can Veto / AI 行動，人工可否決",
                    DelegationStage.FULL_AI: "Full AI Autonomy / 完全 AI 自主",
                }.get(self._stage, "Unknown"),
                "next_stage": next_stage,
                "can_upgrade": can,
                "unmet_conditions": unmet,
                "requires_operator_approval": next_stage == DelegationStage.FULL_AI.value,
                "metrics": dict(self._metrics),
                "history_count": len(self._stage_history),
                "recent_history": self._stage_history[-5:] if self._stage_history else [],
            }

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        Get delegation stage transition history.
        獲取放權階段轉換歷史。

        Args:
            limit: Maximum number of entries to return (newest first).
                   最多返回的條目數（最新在前）。

        Returns:
            List of history entries / 歷史條目列表
        """
        with self._lock:
            return list(reversed(self._stage_history[-limit:]))

    # ───────────────────────────────────────────────────────────────────────
    # Persistence / 持久化
    # ───────────────────────────────────────────────────────────────────────

    def _load(self) -> bool:
        """
        Load state from JSON file. Returns True if loaded successfully.
        從 JSON 文件載入狀態。成功返回 True。
        """
        try:
            if not self._state_path.exists():
                return False
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            self._stage = DelegationStage(data.get("stage", "full_human"))
            self._metrics = data.get("metrics", {})
            self._stage_history = data.get("history", [])
            logger.info(
                "Delegation state loaded: stage=%s / 放權狀態已載入：階段=%s",
                self._stage.value, self._stage.value,
            )
            return True
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            logger.warning(
                "Failed to load delegation state (%s), starting fresh / "
                "載入放權狀態失敗，重新開始: %s",
                type(exc).__name__, exc,
            )
            self._stage = DelegationStage.FULL_HUMAN
            self._metrics = {}
            self._stage_history = []
            return False

    def _save(self) -> None:
        """
        Save state to JSON file. Fail-safe: log warning on error, do not raise.
        保存狀態到 JSON 文件。容錯：出錯時記錄警告，不拋異常。
        """
        data = {
            "stage": self._stage.value,
            "metrics": self._metrics,
            "history": self._stage_history,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self._state_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            tmp_path.replace(self._state_path)
        except OSError as exc:
            logger.warning(
                "Failed to save delegation state: %s / 保存放權狀態失敗: %s",
                exc, exc,
            )
