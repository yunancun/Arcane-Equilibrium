"""
Strategy Promotion Pipeline — LEARNING -> PAPER_SHADOW -> DEMO_ACTIVE -> LIVE_PENDING -> LIVE_ACTIVE
策略漸進放權管線 — 學習 -> 紙盤觀察 -> Demo 激活 -> Live 待審 -> Live 激活

MODULE_NOTE (English):
  Implements 6-01~03 progressive authorization for strategy/model deployment.
  Each strategy starts at LEARNING, graduates to PAPER_SHADOW when metrics pass,
  then DEMO_ACTIVE after paper stability, then LIVE_PENDING for operator review,
  and finally LIVE_ACTIVE upon operator approval.

  Core safety invariants:
  - Promotion is unidirectional (LEARNING -> ... -> LIVE_ACTIVE)
  - LIVE_ACTIVE requires explicit operator approval (no auto-promotion)
  - All transitions emit audit records to learning.promotion_pipeline DB table
  - Thread-safe with lock-protected state transitions
  - Demotion only via operator command (not automatic)

MODULE_NOTE (中文):
  實現 6-01~03 漸進放權：策略/模型部署管線。
  每個策略從 LEARNING 開始，指標達標後畢業至 PAPER_SHADOW，
  紙盤穩定後進入 DEMO_ACTIVE，然後 LIVE_PENDING 等待 operator 審查，
  最終 operator 批准後進入 LIVE_ACTIVE。

  核心安全不變量：
  - 晉升是單向的（LEARNING -> ... -> LIVE_ACTIVE）
  - LIVE_ACTIVE 需要 operator 顯式批准（不可自動晉升）
  - 所有轉換寫入 learning.promotion_pipeline 審計記錄
  - 線程安全，鎖保護狀態轉換
  - 降級僅 operator 可觸發（不自動）
"""

from __future__ import annotations

import logging
import threading
import time
import copy
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any, Callable, Optional, Sequence

logger = logging.getLogger(__name__)


def _timestamp_seconds(value: Any) -> Any:
    """Normalize DB timestamptz values to the in-memory epoch-seconds shape."""
    if isinstance(value, datetime):
        return value.timestamp()
    return value


def _selection_bias_gate_cls():
    """Load SelectionBiasPromotionGate across repo-root and app-runtime paths."""
    try:
        from program_code.learning_engine.promotion_gate import SelectionBiasPromotionGate

        return SelectionBiasPromotionGate
    except ModuleNotFoundError as exc:
        if exc.name != "program_code":
            raise
        try:
            from . import _path_setup  # noqa: F401
        except Exception:  # noqa: BLE001
            pass
        from learning_engine.promotion_gate import SelectionBiasPromotionGate

        return SelectionBiasPromotionGate


def _portfolio_tail_risk_classes():
    """Load PortfolioTailRiskGate/Limits across repo-root and app-runtime paths."""
    try:
        from program_code.learning_engine.portfolio_var import (
            PortfolioTailRiskGate,
            PortfolioTailRiskLimits,
        )

        return PortfolioTailRiskGate, PortfolioTailRiskLimits
    except ModuleNotFoundError as exc:
        if exc.name != "program_code":
            raise
        try:
            from . import _path_setup  # noqa: F401
        except Exception:  # noqa: BLE001
            pass
        from learning_engine.portfolio_var import (
            PortfolioTailRiskGate,
            PortfolioTailRiskLimits,
        )

        return PortfolioTailRiskGate, PortfolioTailRiskLimits


# ═══════════════════════════════════════════════════════════════════════════════
# Promotion Stages / 晉升階段
# ═══════════════════════════════════════════════════════════════════════════════

class PromotionStage(IntEnum):
    """
    Five-stage progressive authorization scale.
    五階段漸進放權等級。
    """
    LEARNING = 0        # Training/evaluation only / 僅訓練/評估
    PAPER_SHADOW = 1    # Paper trading with shadow signals / 紙盤交易（影子信號）
    DEMO_ACTIVE = 2     # Active demo trading on exchange / 交易所 Demo 主動交易
    LIVE_PENDING = 3    # Awaiting operator approval for live / 等待 operator 批准上線
    LIVE_ACTIVE = 4     # Full live trading authorized / 已授權正式實盤交易


# ═══════════════════════════════════════════════════════════════════════════════
# Graduation Gates / 畢業門檻
# ═══════════════════════════════════════════════════════════════════════════════

# 6-02: Thresholds for automatic graduation between stages.
# 6-02：各階段自動畢業門檻。

PAPER_GRADUATION_GATES = {
    "min_duration_days": 14,
    "min_trade_count": 100,
    "min_pnl_pct": 0.0,         # net PnL >= 0 (not losing money)
    "max_drawdown_pct": 10.0,
    "min_sharpe": 0.5,
}

DEMO_GRADUATION_GATES = {
    "min_duration_days": 21,
    "min_trade_count": 200,
    "max_drawdown_pct": 8.0,
    "min_sharpe": 0.8,
    "max_avg_slippage_bps": 15.0,   # slippage acceptable
    "min_api_reliability": 0.95,    # 95% API success rate
}

# LIVE gate: no auto-promotion, requires operator + optional AI evaluation.
# LIVE 門檻：不可自動晉升，需 operator 批准 + 可選 AI 評估。
LIVE_GRADUATION_GATES = {
    "requires_operator_approval": True,
    "requires_ai_evaluation": True,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline Entry / 管線條目
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineEntry:
    """
    Tracks a single strategy/model through the promotion pipeline.
    追蹤單個策略/模型在晉升管線中的狀態。
    """
    pipeline_id: Optional[int] = None
    strategy_name: str = ""
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    current_stage: PromotionStage = PromotionStage.LEARNING

    # Paper metrics / 紙盤指標
    paper_start_ts: Optional[float] = None
    paper_trades: int = 0
    paper_win_rate: Optional[float] = None
    paper_net_pnl_pct: Optional[float] = None
    paper_max_drawdown_pct: Optional[float] = None
    paper_sharpe: Optional[float] = None

    # Demo metrics / Demo 指標
    demo_start_ts: Optional[float] = None
    demo_trades: int = 0
    demo_win_rate: Optional[float] = None
    demo_net_pnl_pct: Optional[float] = None
    demo_max_drawdown_pct: Optional[float] = None
    demo_sharpe: Optional[float] = None
    demo_avg_slippage_bps: Optional[float] = None
    demo_api_reliability: Optional[float] = None
    demo_selection_bias_report: Optional[dict] = None
    demo_tail_risk_report: Optional[dict] = None

    # Live approval / Live 審批
    evaluation_report: Optional[dict] = None
    operator_decision: Optional[str] = None   # APPROVED / REJECTED / EXTEND
    approved_capital_pct: Optional[float] = None
    approved_max_leverage: Optional[float] = None

    created_ts: Optional[float] = None
    updated_ts: Optional[float] = None


# ═══════════════════════════════════════════════════════════════════════════════
# PromotionGate / 晉升門控
# ═══════════════════════════════════════════════════════════════════════════════

class PromotionGate:
    """
    Stateful gate managing strategy promotion through stages.
    管理策略在各階段間晉升的有狀態門控。

    Thread-safe: all mutations protected by a lock.
    線程安全：所有變更受鎖保護。
    """

    def __init__(
        self,
        audit_callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._lock = threading.Lock()
        # Map: strategy_name -> PipelineEntry
        self._entries: dict[str, PipelineEntry] = {}
        self._audit_callback = audit_callback

    # ------------------------------------------------------------------
    # Read state / 讀取狀態
    # ------------------------------------------------------------------

    def get_entry(self, strategy_name: str) -> Optional[PipelineEntry]:
        """Get pipeline entry for a strategy (thread-safe copy).
        獲取策略的管線條目（線程安全副本）。"""
        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return None
            # Return a shallow copy to avoid external mutation.
            import copy
            return copy.copy(entry)

    def get_all_entries(self) -> dict[str, PipelineEntry]:
        """Get all pipeline entries (thread-safe copies).
        獲取所有管線條目（線程安全副本）。"""
        import copy
        with self._lock:
            return {k: copy.copy(v) for k, v in self._entries.items()}

    def get_stage(self, strategy_name: str) -> PromotionStage:
        """Get current stage for a strategy. Returns LEARNING if not registered.
        獲取策略當前階段。未註冊則返回 LEARNING。"""
        with self._lock:
            entry = self._entries.get(strategy_name)
            return entry.current_stage if entry else PromotionStage.LEARNING

    # ------------------------------------------------------------------
    # Register / 註冊
    # ------------------------------------------------------------------

    def register_strategy(
        self,
        strategy_name: str,
        model_name: Optional[str] = None,
        model_version: Optional[str] = None,
        initial_stage: PromotionStage = PromotionStage.LEARNING,
    ) -> PipelineEntry:
        """Register a strategy in the promotion pipeline.
        在晉升管線中註冊策略。"""
        with self._lock:
            if strategy_name in self._entries:
                return copy.copy(self._entries[strategy_name])
            entry = PipelineEntry(
                strategy_name=strategy_name,
                model_name=model_name,
                model_version=model_version,
                current_stage=initial_stage,
                created_ts=time.time(),
                updated_ts=time.time(),
            )
            self._entries[strategy_name] = entry
            self._emit_audit("register", strategy_name, None, initial_stage)
            return copy.copy(entry)

    # ------------------------------------------------------------------
    # Update metrics / 更新指標
    # ------------------------------------------------------------------

    def update_paper_metrics(
        self,
        strategy_name: str,
        trades: int,
        win_rate: float,
        net_pnl_pct: float,
        max_drawdown_pct: float,
        sharpe: float,
    ) -> None:
        """Update paper trading metrics for a strategy.
        更新策略的紙盤交易指標。"""
        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return
            if entry.paper_start_ts is None:
                entry.paper_start_ts = time.time()
            entry.paper_trades = trades
            entry.paper_win_rate = win_rate
            entry.paper_net_pnl_pct = net_pnl_pct
            entry.paper_max_drawdown_pct = max_drawdown_pct
            entry.paper_sharpe = sharpe
            entry.updated_ts = time.time()

    def update_demo_metrics(
        self,
        strategy_name: str,
        trades: int,
        win_rate: float,
        net_pnl_pct: float,
        max_drawdown_pct: float,
        sharpe: float,
        avg_slippage_bps: float = 0.0,
        api_reliability: float = 1.0,
    ) -> None:
        """Update demo trading metrics for a strategy.
        更新策略的 Demo 交易指標。"""
        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return
            if entry.demo_start_ts is None:
                entry.demo_start_ts = time.time()
            entry.demo_trades = trades
            entry.demo_win_rate = win_rate
            entry.demo_net_pnl_pct = net_pnl_pct
            entry.demo_max_drawdown_pct = max_drawdown_pct
            entry.demo_sharpe = sharpe
            entry.demo_avg_slippage_bps = avg_slippage_bps
            entry.demo_api_reliability = api_reliability
            entry.updated_ts = time.time()

    def update_demo_selection_bias_evidence(
        self,
        strategy_name: str,
        *,
        observed_sharpe: float,
        n_trials: int,
        n_observations: int,
        candidate_oos_returns: Optional[Sequence[Sequence[float]]] = None,
        trial_sharpes: Optional[Sequence[float]] = None,
    ) -> tuple[bool, dict]:
        """Update fail-closed DSR/PBO evidence for DEMO_ACTIVE graduation.

        更新 DEMO_ACTIVE 畢業用的 fail-closed DSR/PBO 證據。
        """
        with self._lock:
            if strategy_name not in self._entries:
                return False, {
                    "verdict": "block",
                    "passes": False,
                    "reasons": ["not_registered"],
                }

        gate_cls = _selection_bias_gate_cls()
        try:
            result = gate_cls().evaluate(
                observed_sharpe=observed_sharpe,
                n_trials=n_trials,
                n_observations=n_observations,
                candidate_oos_returns=candidate_oos_returns,
                trial_sharpes=trial_sharpes,
            )
            report = result.to_dict()
        except Exception as exc:  # noqa: BLE001 - promotion evidence must fail closed.
            report = {
                "verdict": "block",
                "passes": False,
                "reasons": [f"selection_bias_invalid:{exc}"],
                "dsr": None,
                "dsr_verdict": "block",
                "pbo": None,
                "pbo_verdict": "missing_cpcv_returns",
                "cpcv_protocol": "cscv",
            }

        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return False, {
                    "verdict": "block",
                    "passes": False,
                    "reasons": ["not_registered"],
                }
            entry.demo_selection_bias_report = report
            entry.updated_ts = time.time()

        return bool(report.get("passes")), report

    def update_demo_tail_risk_evidence(
        self,
        strategy_name: str,
        *,
        portfolio_returns: Sequence[float],
        stress_exposures: Optional[dict[str, float]] = None,
        confidence: float = 0.99,
        max_var_loss: float = 0.05,
        max_cvar_loss: float = 0.08,
        max_evt_cvar_loss: float = 0.12,
        max_stress_loss: float = 0.20,
        min_observations: int = 200,
        evt_threshold_quantile: float = 0.95,
        min_evt_excesses: int = 10,
        n_bootstrap: int = 1000,
        seed: Optional[int] = None,
    ) -> tuple[bool, dict]:
        """Update fail-closed portfolio VaR/CVaR/EVT evidence.

        更新 DEMO_ACTIVE 畢業用的 portfolio tail-risk 證據。
        """
        with self._lock:
            if strategy_name not in self._entries:
                return False, {
                    "verdict": "block",
                    "passes": False,
                    "reasons": ["not_registered"],
                }

        gate_cls, limits_cls = _portfolio_tail_risk_classes()
        try:
            limits = limits_cls(
                confidence=confidence,
                max_var_loss=max_var_loss,
                max_cvar_loss=max_cvar_loss,
                max_evt_cvar_loss=max_evt_cvar_loss,
                max_stress_loss=max_stress_loss,
                min_observations=min_observations,
                evt_threshold_quantile=evt_threshold_quantile,
                min_evt_excesses=min_evt_excesses,
            )
            result = gate_cls(limits).evaluate(
                portfolio_returns,
                stress_exposures=stress_exposures,
                n_bootstrap=n_bootstrap,
                seed=seed,
            )
            report = result.to_dict()
        except Exception as exc:  # noqa: BLE001 - promotion evidence must fail closed.
            report = {
                "verdict": "block",
                "passes": False,
                "reasons": [f"tail_risk_invalid:{exc}"],
            }

        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return False, {
                    "verdict": "block",
                    "passes": False,
                    "reasons": ["not_registered"],
                }
            entry.demo_tail_risk_report = report
            entry.updated_ts = time.time()

        return bool(report.get("passes")), report

    # ------------------------------------------------------------------
    # Graduation checks / 畢業檢查
    # ------------------------------------------------------------------

    def check_paper_graduation(
        self, strategy_name: str
    ) -> tuple[bool, list[str]]:
        """Check if a strategy qualifies for PAPER_SHADOW -> DEMO_ACTIVE.
        檢查策略是否達到 PAPER_SHADOW -> DEMO_ACTIVE 的畢業條件。

        Returns (eligible, list_of_failing_reasons).
        返回 (是否達標, 未達標原因列表)。
        """
        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return False, ["not_registered"]
            if entry.current_stage != PromotionStage.PAPER_SHADOW:
                return False, [f"wrong_stage:{entry.current_stage.name}"]
            return self._check_paper_gates(entry)

    def check_demo_graduation(
        self, strategy_name: str
    ) -> tuple[bool, list[str]]:
        """Check if a strategy qualifies for DEMO_ACTIVE -> LIVE_PENDING.
        檢查策略是否達到 DEMO_ACTIVE -> LIVE_PENDING 的畢業條件。"""
        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return False, ["not_registered"]
            if entry.current_stage != PromotionStage.DEMO_ACTIVE:
                return False, [f"wrong_stage:{entry.current_stage.name}"]
            return self._check_demo_gates(entry)

    # ------------------------------------------------------------------
    # Promote / 晉升
    # ------------------------------------------------------------------

    def promote(
        self,
        strategy_name: str,
        target_stage: PromotionStage,
        initiator: str = "system",
        reason: str = "",
    ) -> tuple[bool, str]:
        """Attempt to promote a strategy to the target stage.
        嘗試將策略晉升到目標階段。

        Returns (success, message).
        返回 (是否成功, 訊息)。
        """
        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return False, "not_registered"

            current = entry.current_stage

            # Must be exactly one step up (no skipping).
            # 必須恰好晉升一級（不可跳級）。
            if target_stage.value != current.value + 1:
                return False, f"invalid_transition:{current.name}->{target_stage.name}"

            # Gate checks for automatic promotions.
            # 自動晉升的門檻檢查。
            if target_stage == PromotionStage.PAPER_SHADOW:
                # LEARNING -> PAPER_SHADOW: always allowed (just register).
                pass
            elif target_stage == PromotionStage.DEMO_ACTIVE:
                eligible, reasons = self._check_paper_gates(entry)
                if not eligible:
                    return False, f"gates_not_met:{','.join(reasons)}"
            elif target_stage == PromotionStage.LIVE_PENDING:
                eligible, reasons = self._check_demo_gates(entry)
                if not eligible:
                    return False, f"gates_not_met:{','.join(reasons)}"
            elif target_stage == PromotionStage.LIVE_ACTIVE:
                # 6-03: Requires operator approval — checked via operator_decision.
                # 6-03：需要 operator 批准 — 通過 operator_decision 檢查。
                if entry.operator_decision != "APPROVED":
                    return False, "operator_approval_required"

            # Apply promotion / 執行晉升
            old_stage = entry.current_stage
            entry.current_stage = target_stage
            entry.updated_ts = time.time()

            self._emit_audit(
                "promote", strategy_name, old_stage, target_stage,
                initiator=initiator, reason=reason,
            )

            logger.info(
                "Strategy %s promoted: %s -> %s (initiator=%s, reason=%s) "
                "/ 策略 %s 晉升：%s -> %s",
                strategy_name, old_stage.name, target_stage.name,
                initiator, reason,
                strategy_name, old_stage.name, target_stage.name,
            )

            return True, f"promoted:{old_stage.name}->{target_stage.name}"

    # ------------------------------------------------------------------
    # Live approval / Live 審批 (6-03)
    # ------------------------------------------------------------------

    def set_operator_decision(
        self,
        strategy_name: str,
        decision: str,
        capital_pct: Optional[float] = None,
        max_leverage: Optional[float] = None,
        evaluation_report: Optional[dict] = None,
    ) -> tuple[bool, str]:
        """Set operator decision for LIVE_PENDING -> LIVE_ACTIVE.
        設置 operator 對 LIVE_PENDING -> LIVE_ACTIVE 的決策。

        decision: APPROVED / REJECTED / EXTEND
        """
        if decision not in ("APPROVED", "REJECTED", "EXTEND"):
            return False, f"invalid_decision:{decision}"

        with self._lock:
            entry = self._entries.get(strategy_name)
            if entry is None:
                return False, "not_registered"
            if entry.current_stage != PromotionStage.LIVE_PENDING:
                return False, f"wrong_stage:{entry.current_stage.name}"

            entry.operator_decision = decision
            entry.approved_capital_pct = capital_pct
            entry.approved_max_leverage = max_leverage
            if evaluation_report:
                entry.evaluation_report = evaluation_report
            entry.updated_ts = time.time()

            self._emit_audit(
                "operator_decision", strategy_name,
                entry.current_stage, entry.current_stage,
                initiator="operator",
                reason=f"decision={decision}",
            )

            logger.info(
                "Operator decision for %s: %s (capital=%.1f%%, leverage=%.0f) "
                "/ Operator 決策：%s（資金=%s%%，槓桿=%s）",
                strategy_name, decision,
                capital_pct or 0.0, max_leverage or 0.0,
                decision, capital_pct, max_leverage,
            )

            return True, f"decision_recorded:{decision}"

    # ------------------------------------------------------------------
    # Internal gate checks / 內部門檻檢查
    # ------------------------------------------------------------------

    @staticmethod
    def _check_paper_gates(entry: PipelineEntry) -> tuple[bool, list[str]]:
        """Check paper graduation gates. Not locked — caller holds lock.
        檢查紙盤畢業門檻。未加鎖 — 調用方持鎖。"""
        gates = PAPER_GRADUATION_GATES
        failures: list[str] = []

        # Duration check / 時長檢查
        if entry.paper_start_ts is not None:
            days = (time.time() - entry.paper_start_ts) / 86400.0
            if days < gates["min_duration_days"]:
                failures.append(f"duration:{days:.1f}d<{gates['min_duration_days']}d")
        else:
            failures.append("no_paper_start_ts")

        if entry.paper_trades < gates["min_trade_count"]:
            failures.append(
                f"trades:{entry.paper_trades}<{gates['min_trade_count']}"
            )

        if entry.paper_net_pnl_pct is not None:
            if entry.paper_net_pnl_pct < gates["min_pnl_pct"]:
                failures.append(
                    f"pnl:{entry.paper_net_pnl_pct:.2f}%<{gates['min_pnl_pct']}%"
                )
        else:
            failures.append("no_pnl_data")

        if entry.paper_max_drawdown_pct is not None:
            if entry.paper_max_drawdown_pct > gates["max_drawdown_pct"]:
                failures.append(
                    f"drawdown:{entry.paper_max_drawdown_pct:.1f}%>"
                    f"{gates['max_drawdown_pct']}%"
                )
        else:
            failures.append("no_drawdown_data")

        if entry.paper_sharpe is not None:
            if entry.paper_sharpe < gates["min_sharpe"]:
                failures.append(
                    f"sharpe:{entry.paper_sharpe:.2f}<{gates['min_sharpe']}"
                )
        else:
            failures.append("no_sharpe_data")

        return len(failures) == 0, failures

    @staticmethod
    def _check_demo_gates(entry: PipelineEntry) -> tuple[bool, list[str]]:
        """Check demo graduation gates. Not locked — caller holds lock.
        檢查 Demo 畢業門檻。未加鎖 — 調用方持鎖。"""
        gates = DEMO_GRADUATION_GATES
        failures: list[str] = []

        # Duration check / 時長檢查
        if entry.demo_start_ts is not None:
            days = (time.time() - entry.demo_start_ts) / 86400.0
            if days < gates["min_duration_days"]:
                failures.append(f"duration:{days:.1f}d<{gates['min_duration_days']}d")
        else:
            failures.append("no_demo_start_ts")

        if entry.demo_trades < gates["min_trade_count"]:
            failures.append(
                f"trades:{entry.demo_trades}<{gates['min_trade_count']}"
            )

        if entry.demo_max_drawdown_pct is not None:
            if entry.demo_max_drawdown_pct > gates["max_drawdown_pct"]:
                failures.append(
                    f"drawdown:{entry.demo_max_drawdown_pct:.1f}%>"
                    f"{gates['max_drawdown_pct']}%"
                )
        else:
            failures.append("no_drawdown_data")

        if entry.demo_sharpe is not None:
            if entry.demo_sharpe < gates["min_sharpe"]:
                failures.append(
                    f"sharpe:{entry.demo_sharpe:.2f}<{gates['min_sharpe']}"
                )
        else:
            failures.append("no_sharpe_data")

        if entry.demo_avg_slippage_bps is not None:
            if entry.demo_avg_slippage_bps > gates["max_avg_slippage_bps"]:
                failures.append(
                    f"slippage:{entry.demo_avg_slippage_bps:.1f}bps>"
                    f"{gates['max_avg_slippage_bps']}bps"
                )

        if entry.demo_api_reliability is not None:
            if entry.demo_api_reliability < gates["min_api_reliability"]:
                failures.append(
                    f"reliability:{entry.demo_api_reliability:.2f}<"
                    f"{gates['min_api_reliability']}"
                )

        selection_report = entry.demo_selection_bias_report
        if not isinstance(selection_report, dict):
            failures.append("selection_bias:no_evidence")
        elif not bool(selection_report.get("passes")):
            verdict = str(selection_report.get("verdict") or "unknown")
            raw_reasons = selection_report.get("reasons") or []
            if isinstance(raw_reasons, (list, tuple)):
                reason_suffix = ",".join(str(reason) for reason in raw_reasons)
            else:
                reason_suffix = str(raw_reasons)
            if reason_suffix:
                failures.append(f"selection_bias:{verdict}:{reason_suffix}")
            else:
                failures.append(f"selection_bias:{verdict}")

        tail_risk_report = entry.demo_tail_risk_report
        if not isinstance(tail_risk_report, dict):
            failures.append("tail_risk:no_evidence")
        elif not bool(tail_risk_report.get("passes")):
            verdict = str(tail_risk_report.get("verdict") or "unknown")
            raw_reasons = tail_risk_report.get("reasons") or []
            if isinstance(raw_reasons, (list, tuple)):
                reason_suffix = ",".join(str(reason) for reason in raw_reasons)
            else:
                reason_suffix = str(raw_reasons)
            if reason_suffix:
                failures.append(f"tail_risk:{verdict}:{reason_suffix}")
            else:
                failures.append(f"tail_risk:{verdict}")

        return len(failures) == 0, failures

    # ------------------------------------------------------------------
    # Audit / 審計
    # ------------------------------------------------------------------

    def _emit_audit(
        self,
        action: str,
        strategy_name: str,
        from_stage: Optional[PromotionStage],
        to_stage: Optional[PromotionStage],
        initiator: str = "system",
        reason: str = "",
    ) -> None:
        """Emit audit record via callback.
        通過回調發出審計記錄。"""
        if self._audit_callback is None:
            return
        record = {
            "audit_id": str(uuid.uuid4()),
            "ts": time.time(),
            "action": action,
            "strategy_name": strategy_name,
            "from_stage": from_stage.name if from_stage is not None else None,
            "to_stage": to_stage.name if to_stage is not None else None,
            "initiator": initiator,
            "reason": reason,
        }
        try:
            self._audit_callback(record)
        except Exception as e:
            logger.warning(
                "Audit callback failed for %s: %s / 審計回調失敗：%s",
                action, e, e,
            )

    # ------------------------------------------------------------------
    # Serialization / 序列化 (for DB persistence)
    # ------------------------------------------------------------------

    def to_db_rows(self) -> list[dict[str, Any]]:
        """Export all entries as DB-compatible dicts.
        將所有條目導出為 DB 兼容的字典。"""
        with self._lock:
            rows = []
            for entry in self._entries.values():
                rows.append({
                    "pipeline_id": entry.pipeline_id,
                    "strategy_name": entry.strategy_name,
                    "model_name": entry.model_name,
                    "model_version": entry.model_version,
                    "current_stage": entry.current_stage.name,
                    "paper_start_ts": entry.paper_start_ts,
                    "paper_trades": entry.paper_trades,
                    "paper_win_rate": entry.paper_win_rate,
                    "paper_net_pnl_pct": entry.paper_net_pnl_pct,
                    "paper_max_drawdown_pct": entry.paper_max_drawdown_pct,
                    "paper_sharpe": entry.paper_sharpe,
                    "demo_start_ts": entry.demo_start_ts,
                    "demo_trades": entry.demo_trades,
                    "demo_win_rate": entry.demo_win_rate,
                    "demo_net_pnl_pct": entry.demo_net_pnl_pct,
                    "demo_max_drawdown_pct": entry.demo_max_drawdown_pct,
                    "demo_sharpe": entry.demo_sharpe,
                    "demo_avg_slippage_bps": entry.demo_avg_slippage_bps,
                    "demo_api_reliability": entry.demo_api_reliability,
                    "demo_selection_bias_report": entry.demo_selection_bias_report,
                    "demo_tail_risk_report": entry.demo_tail_risk_report,
                    "evaluation_report": entry.evaluation_report,
                    "operator_decision": entry.operator_decision,
                    "approved_capital_pct": entry.approved_capital_pct,
                    "approved_max_leverage": entry.approved_max_leverage,
                })
            return rows

    def load_from_db_rows(self, rows: list[dict[str, Any]]) -> None:
        """Load entries from DB rows (startup restore).
        從 DB 行加載條目（啟動恢復）。"""
        stage_map = {s.name: s for s in PromotionStage}
        with self._lock:
            for row in rows:
                stage_name = row.get("current_stage", "LEARNING")
                stage = stage_map.get(stage_name, PromotionStage.LEARNING)
                entry = PipelineEntry(
                    pipeline_id=row.get("pipeline_id"),
                    strategy_name=row.get("strategy_name", ""),
                    model_name=row.get("model_name"),
                    model_version=row.get("model_version"),
                    current_stage=stage,
                    paper_start_ts=_timestamp_seconds(row.get("paper_start_ts")),
                    paper_trades=row.get("paper_trades", 0),
                    paper_win_rate=row.get("paper_win_rate"),
                    paper_net_pnl_pct=row.get("paper_net_pnl_pct"),
                    paper_max_drawdown_pct=row.get("paper_max_drawdown_pct"),
                    paper_sharpe=row.get("paper_sharpe"),
                    demo_start_ts=_timestamp_seconds(row.get("demo_start_ts")),
                    demo_trades=row.get("demo_trades", 0),
                    demo_win_rate=row.get("demo_win_rate"),
                    demo_net_pnl_pct=row.get("demo_net_pnl_pct"),
                    demo_max_drawdown_pct=row.get("demo_max_drawdown_pct"),
                    demo_sharpe=row.get("demo_sharpe"),
                    demo_avg_slippage_bps=row.get("demo_avg_slippage_bps"),
                    demo_api_reliability=row.get("demo_api_reliability"),
                    demo_selection_bias_report=row.get("demo_selection_bias_report"),
                    demo_tail_risk_report=row.get("demo_tail_risk_report"),
                    evaluation_report=row.get("evaluation_report"),
                    operator_decision=row.get("operator_decision"),
                    approved_capital_pct=row.get("approved_capital_pct"),
                    approved_max_leverage=row.get("approved_max_leverage"),
                )
                if entry.strategy_name:
                    self._entries[entry.strategy_name] = entry
