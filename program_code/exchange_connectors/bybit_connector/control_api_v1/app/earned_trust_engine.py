# MODULE_NOTE (English):
#   Earned-Trust Authorization TTL Ladder — SM-01 TTL tiers earned through
#   real performance. The system must *prove* reliability before being granted
#   longer autonomous windows. Designed as a pure state engine; side-effects
#   (auth creation, alerts) live in live_trust_routes.py.
#
#   Tier ladder:
#     T0 Entry        24 h  — first live session / any downgrade reset
#     T1 Provisional  72 h  — 7 consecutive clean days at T0
#     T2 Established 168 h  — 14 consecutive clean days at T1
#     T3 Trusted     360 h  — 21 consecutive clean days at T2
#
#   T3 auto-renews once (30-day cap); then mandatory Operator full review.
#   Mid-session incidents set pending_downgrade immediately; current session
#   continues, but next Renew applies the lower tier.
#
# MODULE_NOTE (中文):
#   贏得信任授權 TTL 階梯 — SM-01 TTL 按真實表現贏得。系統必須透過可量化
#   表現*證明*可靠性，才能獲得更長的自主窗口。純狀態引擎設計；副作用
#   （創建授權、告警）留在 live_trust_routes.py。
#
#   T0 入門     24 h  — 首次 live / 任何降級後重置
#   T1 暫定     72 h  — T0 上連續 7 乾淨天
#   T2 成熟    168 h  — T1 上連續 14 乾淨天
#   T3 受信    360 h  — T2 上連續 21 乾淨天
#
#   T3 自動續期一次（30 天上限）；之後必須 Operator 全面審查。
#   Session 中途事件立即設置 pending_downgrade；本次 session 繼續，
#   下次 Renew 使用降級後的 tier。

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants / 常量
# ─────────────────────────────────────────────────────────────────────────────

class TrustTier(IntEnum):
    """Authorization TTL tiers / 授權 TTL 階梯"""
    T0_ENTRY        = 0   # 24 h
    T1_PROVISIONAL  = 1   # 72 h  (3 days)
    T2_ESTABLISHED  = 2   # 168 h (7 days)
    T3_TRUSTED      = 3   # 360 h (15 days)

# TTL per tier in hours / 每 tier 的 TTL（小時）
TIER_TTL_HOURS: dict[int, int] = {0: 24, 1: 72, 2: 168, 3: 360}

# Human-readable names / 可讀名稱
TIER_NAMES: dict[int, str] = {
    0: "T0 Entry",
    1: "T1 Provisional",
    2: "T2 Established",
    3: "T3 Trusted",
}

# Consecutive clean days required to promote to this tier / 晉升至此 tier 所需連續乾淨天數
# Key = target tier (the tier being promoted INTO)
PROMOTE_CLEAN_DAYS: dict[int, float] = {1: 7.0, 2: 14.0, 3: 21.0}

# T3 auto-renewal cap / T3 自動續期上限
T3_MAX_AUTO_RENEWALS: int = 1

# Expiry warning threshold (hours before expiry to trigger banner) / 到期前警示閾值（小時）
EXPIRY_WARN_HOURS: float = 2.0

# Mid-session downgrade thresholds / 中途降級觸發閾值
MIDTERM_CONSECUTIVE_LOSS_LIMIT: int = 5      # consecutive losing trades / 連續虧損交易數
MIDTERM_DRAWDOWN_T2T3_PCT: float = 8.0       # single-day drawdown for T2/T3 / T2/T3 單日回撤%
MIDTERM_RECONCILER_MAJOR_DRIFT_CYCLES: int = 3  # reconciler major drift cycles / 對賬主要漂移 cycle 數


# ─────────────────────────────────────────────────────────────────────────────
# Metrics snapshot passed to evaluators / 傳給評估器的指標快照
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrustMetrics:
    """
    All metrics needed to evaluate tier promotion / downgrade.
    評估 tier 晉升/降級所需的所有指標。
    """
    # PnL / 損益
    net_pnl: float = 0.0              # cumulative net PnL in USDT / 累計淨 PnL（USDT）
    win_rate_pct: float = 0.0         # win rate % (fee-adjusted) / 勝率%（含費後）
    profit_factor: float = 0.0        # avg_win / avg_loss / 利潤因子
    sharpe: float = 0.0               # annualized Sharpe ratio / 年化夏普比
    cost_ratio: float = 0.0           # fees / gross_pnl / 費用比

    # Drawdown / 回撤
    max_daily_drawdown_pct: float = 0.0   # worst single-day drawdown over window / 窗口內最大單日回撤
    max_window_drawdown_pct: float = 0.0  # max drawdown over entire observation window / 整個觀察窗口最大回撤
    consecutive_losses: int = 0           # current consecutive losing trades / 當前連續虧損數

    # System health / 系統健康
    reconciler_major_drift_cycles: int = 0   # reconciler major drift cycle count / 對賬主要漂移 cycle 數
    critical_incident_count: int = 0         # critical incidents in window / 窗口內嚴重事件數
    major_incident_count: int = 0            # major incidents / 主要事件數

    # Meta / 元信息
    observation_days: float = 0.0    # actual days of data available / 實際可用數據天數


# ─────────────────────────────────────────────────────────────────────────────
# Per-tier requirement sets / 每 tier 的要求集
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TierRequirements:
    """
    Minimum requirements to be promoted INTO this tier.
    晉升至此 tier 的最低要求。
    """
    target_tier: int
    min_clean_days: float
    min_net_pnl: float                        # must be > 0 / 必須 > 0
    max_daily_drawdown_pct: float
    max_cost_ratio: float
    min_win_rate_pct: Optional[float] = None
    min_profit_factor: Optional[float] = None
    min_sharpe: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    max_window_drawdown_pct: Optional[float] = None
    zero_critical_incidents: bool = True


_TIER_REQUIREMENTS: dict[int, TierRequirements] = {
    1: TierRequirements(
        target_tier=1,
        min_clean_days=7.0,
        min_net_pnl=0.0,          # net_pnl > 0
        max_daily_drawdown_pct=5.0,
        max_cost_ratio=0.50,      # fees < 50% of profit
        zero_critical_incidents=True,
    ),
    2: TierRequirements(
        target_tier=2,
        min_clean_days=14.0,
        min_net_pnl=0.0,
        max_daily_drawdown_pct=5.0,
        max_cost_ratio=0.50,
        min_win_rate_pct=35.0,
        min_profit_factor=1.2,
        min_sharpe=0.5,
        zero_critical_incidents=True,
    ),
    3: TierRequirements(
        target_tier=3,
        min_clean_days=21.0,
        min_net_pnl=0.0,
        max_daily_drawdown_pct=5.0,
        max_cost_ratio=0.50,
        min_win_rate_pct=35.0,
        min_profit_factor=1.4,
        min_sharpe=0.8,
        max_consecutive_losses=5,
        max_window_drawdown_pct=10.0,
        zero_critical_incidents=True,
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Persistent state / 持久化狀態
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EarnedTrustState:
    """
    Persisted state for the earned-trust ladder.
    贏得信任階梯的持久化狀態。
    """
    current_tier: int = 0                    # current effective tier / 當前有效 tier
    tier_start_ts_ms: int = 0                # when we entered current tier / 進入當前 tier 時間
    clean_day_streak_start_ts_ms: int = 0    # when current clean streak started / 當前乾淨連勝開始時間
    clean_days_in_tier: float = 0.0          # consecutive clean days at current tier / 當前 tier 連續乾淨天數
    renewals_at_t3: int = 0                  # how many times T3 has been auto-renewed / T3 自動續期次數
    pending_downgrade_tier: Optional[int] = None   # set on mid-session downgrade / 中途降級設置
    pending_downgrade_reason: Optional[str] = None # reason for pending downgrade / 降級原因
    last_renewal_ts_ms: Optional[int] = None       # when last renewal occurred / 上次續期時間
    last_auth_expires_ts_ms: Optional[int] = None  # when current auth expires / 當前授權到期時間
    promotion_history: list = field(default_factory=list)  # audit trail / 審計軌跡

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict / 序列化為字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EarnedTrustState":
        """Deserialize from dict / 從字典反序列化"""
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation results / 評估結果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RenewalRecommendation:
    """
    Recommendation returned at auth expiry time.
    授權到期時返回的續期建議。
    """
    recommended_tier: int
    recommended_ttl_hours: int
    current_tier: int
    action: str          # "promote" | "maintain" | "demote" | "block_review"
    reasons: list[str]   # human-readable reasons / 可讀原因
    metrics_snapshot: Optional[dict[str, Any]] = None
    requires_operator_review: bool = False  # T3 exhausted — mandatory full review


@dataclass
class MidSessionDowngrade:
    """
    Emitted when a mid-session downgrade is detected.
    檢測到中途降級時發出。
    """
    from_tier: int
    to_tier: int
    reason: str
    ts_ms: int


# ─────────────────────────────────────────────────────────────────────────────
# Core engine / 核心引擎
# ─────────────────────────────────────────────────────────────────────────────

class EarnedTrustEngine:
    """
    Thread-safe earned-trust ladder engine.
    Persists state to JSON; re-loads on process restart (no tier reset on restart).

    線程安全的贏得信任階梯引擎。
    持久化狀態到 JSON；進程重啟後從文件恢復（重啟不觸發 tier 重置）。
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self._data_dir = data_dir or os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
        self._state_path = Path(self._data_dir) / "earned_trust_state.json"
        self._lock = threading.Lock()
        self._state: EarnedTrustState = self._load_or_init()

    # ── Persistence / 持久化 ─────────────────────────────────────────────────

    def _load_or_init(self) -> EarnedTrustState:
        """Load state from disk; init fresh if missing / 從磁盤加載；不存在則初始化。"""
        try:
            if self._state_path.exists():
                raw = self._state_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                state = EarnedTrustState.from_dict(data)
                logger.info(
                    "EarnedTrustEngine: loaded state tier=%s clean_days=%.1f / "
                    "已加載狀態 tier=%s clean_days=%.1f",
                    state.current_tier, state.clean_days_in_tier,
                    state.current_tier, state.clean_days_in_tier,
                )
                return state
        except Exception as exc:
            logger.warning(
                "EarnedTrustEngine: failed to load state (%s), starting fresh / "
                "加載狀態失敗（%s），從頭開始", exc, exc,
            )
        return EarnedTrustState(
            tier_start_ts_ms=int(time.time() * 1000),
            clean_day_streak_start_ts_ms=int(time.time() * 1000),
        )

    def _save(self) -> None:
        """Persist state to disk (must be called under self._lock) / 持久化到磁盤。"""
        try:
            Path(self._data_dir).mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self._state.to_dict(), indent=2), encoding="utf-8"
            )
        except Exception as exc:
            logger.error(
                "EarnedTrustEngine: failed to save state: %s / 保存狀態失敗: %s",
                exc, exc,
            )

    # ── Public read accessors / 公開讀取訪問器 ──────────────────────────────

    def get_state_snapshot(self) -> dict[str, Any]:
        """
        Return a dict snapshot of current state for API responses.
        返回當前狀態的字典快照用於 API 響應。
        """
        with self._lock:
            s = self._state
            ttl_h = TIER_TTL_HOURS.get(s.current_tier, 24)
            expires_remaining_h: Optional[float] = None
            if s.last_auth_expires_ts_ms:
                remaining_ms = s.last_auth_expires_ts_ms - int(time.time() * 1000)
                expires_remaining_h = remaining_ms / 3_600_000.0

            return {
                "current_tier": s.current_tier,
                "tier_name": TIER_NAMES.get(s.current_tier, "T0 Entry"),
                "tier_ttl_hours": ttl_h,
                "clean_days_in_tier": round(s.clean_days_in_tier, 2),
                "clean_days_required_for_promotion": PROMOTE_CLEAN_DAYS.get(s.current_tier + 1),
                "renewals_at_t3": s.renewals_at_t3,
                "pending_downgrade_tier": s.pending_downgrade_tier,
                "pending_downgrade_reason": s.pending_downgrade_reason,
                "last_renewal_ts_ms": s.last_renewal_ts_ms,
                "last_auth_expires_ts_ms": s.last_auth_expires_ts_ms,
                "expires_remaining_hours": round(expires_remaining_h, 2) if expires_remaining_h is not None else None,
                "near_expiry": (expires_remaining_h is not None and 0 < expires_remaining_h <= EXPIRY_WARN_HOURS),
                "t3_max_renewals": T3_MAX_AUTO_RENEWALS,
                "requires_operator_review": (
                    s.current_tier == TrustTier.T3_TRUSTED
                    and s.renewals_at_t3 >= T3_MAX_AUTO_RENEWALS
                ),
            }

    # ── Auth lifecycle hooks / 授權生命週期 hook ─────────────────────────────

    def on_session_start(self, auth_expires_ts_ms: int) -> None:
        """
        Called when a live session starts (new or resumed).
        If no prior state exists, initializes at T0.
        實盤 session 啟動（新開或恢復）時調用。如無先前狀態，初始化為 T0。
        """
        with self._lock:
            now_ms = int(time.time() * 1000)
            self._state.last_renewal_ts_ms = now_ms
            self._state.last_auth_expires_ts_ms = auth_expires_ts_ms
            # Ensure streak start is set / 確保連勝開始時間已設置
            if self._state.clean_day_streak_start_ts_ms == 0:
                self._state.clean_day_streak_start_ts_ms = now_ms
            self._save()
        logger.info(
            "EarnedTrustEngine: session start recorded tier=%s / 記錄 session 啟動 tier=%s",
            self._state.current_tier, self._state.current_tier,
        )

    def on_auth_renewed(self, new_tier: int, new_expires_ts_ms: int) -> None:
        """
        Called after Operator confirms renewal at the recommended tier.
        Applies any pending downgrade, updates T3 renewal count.
        Operator 確認以建議 tier 續期後調用。應用待處理降級，更新 T3 續期計數。
        """
        with self._lock:
            now_ms = int(time.time() * 1000)
            old_tier = self._state.current_tier

            # Transition tier / 轉換 tier
            if new_tier != old_tier:
                self._state.promotion_history.append({
                    "ts_ms": now_ms,
                    "from_tier": old_tier,
                    "to_tier": new_tier,
                    "event": "promotion" if new_tier > old_tier else "demotion",
                })
                self._state.current_tier = new_tier
                self._state.tier_start_ts_ms = now_ms
                self._state.clean_days_in_tier = 0.0
                self._state.clean_day_streak_start_ts_ms = now_ms
            else:
                # Same tier — update clean days from streak so far / 同 tier 更新連勝天數
                elapsed_days = (now_ms - self._state.clean_day_streak_start_ts_ms) / 86_400_000.0
                self._state.clean_days_in_tier = elapsed_days

            # Track T3 renewals / 追蹤 T3 續期次數
            if new_tier == TrustTier.T3_TRUSTED:
                if old_tier == TrustTier.T3_TRUSTED:
                    self._state.renewals_at_t3 += 1
                else:
                    self._state.renewals_at_t3 = 0  # fresh entry into T3

            # Clear pending downgrade / 清除待處理降級
            self._state.pending_downgrade_tier = None
            self._state.pending_downgrade_reason = None
            self._state.last_renewal_ts_ms = now_ms
            self._state.last_auth_expires_ts_ms = new_expires_ts_ms
            self._save()

        logger.info(
            "EarnedTrustEngine: renewed tier=%s ttl=%dh / 已續期 tier=%s ttl=%dh",
            new_tier, TIER_TTL_HOURS.get(new_tier, 24),
            new_tier, TIER_TTL_HOURS.get(new_tier, 24),
        )

    def on_session_stop(self) -> None:
        """
        Called on voluntary session stop. Resets to T0 for next session start.
        主動 session 停止時調用。下次啟動重置為 T0。
        """
        with self._lock:
            now_ms = int(time.time() * 1000)
            if self._state.current_tier > 0:
                self._state.promotion_history.append({
                    "ts_ms": now_ms,
                    "from_tier": self._state.current_tier,
                    "to_tier": 0,
                    "event": "session_stop_reset",
                })
            self._state.current_tier = 0
            self._state.tier_start_ts_ms = now_ms
            self._state.clean_days_in_tier = 0.0
            self._state.clean_day_streak_start_ts_ms = now_ms
            self._state.renewals_at_t3 = 0
            self._state.pending_downgrade_tier = None
            self._state.pending_downgrade_reason = None
            self._state.last_auth_expires_ts_ms = None
            self._save()
        logger.info("EarnedTrustEngine: session stopped — tier reset to T0 / Session 停止，tier 重置為 T0")

    # ── Mid-session downgrade / 中途降級 ─────────────────────────────────────

    def check_mid_session_downgrade(
        self,
        metrics: TrustMetrics,
    ) -> Optional[MidSessionDowngrade]:
        """
        Check if current performance triggers an immediate downgrade flag.
        Session continues; pending_downgrade applies at next Renew.

        Returns a MidSessionDowngrade event if triggered, else None.
        檢查當前表現是否觸發立即降級標誌。
        Session 繼續；pending_downgrade 在下次 Renew 時生效。
        觸發時返回 MidSessionDowngrade 事件，否則返回 None。
        """
        with self._lock:
            current = self._state.current_tier
            already_pending = self._state.pending_downgrade_tier
            target = current  # default: no change

            reason: Optional[str] = None

            # Check consecutive losses / 連續虧損檢查
            if (
                metrics.consecutive_losses >= MIDTERM_CONSECUTIVE_LOSS_LIMIT
                and current > 0
            ):
                reason = (
                    f"consecutive_losses={metrics.consecutive_losses} "
                    f">= limit={MIDTERM_CONSECUTIVE_LOSS_LIMIT}"
                )
                target = current - 1

            # Check single-day drawdown for T2/T3 / T2/T3 單日回撤檢查
            elif (
                current >= TrustTier.T2_ESTABLISHED
                and metrics.max_daily_drawdown_pct >= MIDTERM_DRAWDOWN_T2T3_PCT
            ):
                reason = (
                    f"daily_drawdown={metrics.max_daily_drawdown_pct:.1f}% "
                    f">= T2/T3_limit={MIDTERM_DRAWDOWN_T2T3_PCT}%"
                )
                target = current - 1

            # Check reconciler major drift / 對賬主要漂移檢查
            elif (
                metrics.reconciler_major_drift_cycles >= MIDTERM_RECONCILER_MAJOR_DRIFT_CYCLES
                and current > 0
            ):
                reason = (
                    f"reconciler_major_drift_cycles={metrics.reconciler_major_drift_cycles} "
                    f">= limit={MIDTERM_RECONCILER_MAJOR_DRIFT_CYCLES}"
                )
                target = current - 1

            if reason is None or target >= current:
                return None  # no downgrade

            # Only update if not already pending to a lower or equal tier / 僅更新為更低 tier
            if already_pending is None or target < already_pending:
                now_ms = int(time.time() * 1000)
                self._state.pending_downgrade_tier = target
                self._state.pending_downgrade_reason = reason
                # Reset clean day streak immediately / 立即重置連勝天數
                self._state.clean_days_in_tier = 0.0
                self._state.clean_day_streak_start_ts_ms = now_ms
                self._save()
                logger.warning(
                    "EarnedTrustEngine: mid-session downgrade flagged %s→%s reason=%s / "
                    "中途降級標記 %s→%s 原因=%s",
                    TIER_NAMES[current], TIER_NAMES[target], reason,
                    TIER_NAMES[current], TIER_NAMES[target], reason,
                )
                return MidSessionDowngrade(
                    from_tier=current, to_tier=target,
                    reason=reason, ts_ms=now_ms,
                )

        return None

    def record_incident(self, severity: str, reason: str) -> None:
        """
        Record a governance incident; resets clean day streak.
        Severity: "critical" | "major" | "minor"
        記錄治理事件；重置連勝天數。
        """
        with self._lock:
            now_ms = int(time.time() * 1000)
            self._state.clean_days_in_tier = 0.0
            self._state.clean_day_streak_start_ts_ms = now_ms
            if severity in ("critical", "major") and self._state.current_tier > 0:
                target = 0 if severity == "critical" else max(0, self._state.current_tier - 1)
                if self._state.pending_downgrade_tier is None or target < self._state.pending_downgrade_tier:
                    self._state.pending_downgrade_tier = target
                    self._state.pending_downgrade_reason = f"{severity}_incident: {reason}"
            self._save()

    # ── Renewal evaluation / 續期評估 ────────────────────────────────────────

    def evaluate_renewal(self, metrics: TrustMetrics) -> RenewalRecommendation:
        """
        Evaluate what tier the next renewal should be at.
        Called when auth is about to expire or has expired.

        評估下次續期應在哪個 tier。在授權即將到期或已到期時調用。
        """
        with self._lock:
            current = self._state.current_tier
            pending_down = self._state.pending_downgrade_tier
            clean_days = self._compute_current_clean_days()

        reasons: list[str] = []
        proposed_tier = current

        # 1. Apply any pending downgrade first / 優先應用待處理降級
        if pending_down is not None and pending_down < current:
            proposed_tier = pending_down
            reasons.append(
                f"Pending mid-session downgrade: {TIER_NAMES[current]} → {TIER_NAMES[pending_down]} "
                f"({self._state.pending_downgrade_reason})"
            )

        # 2. Check if we qualify for promotion (only if no downgrade pending)
        #    檢查是否符合晉升條件（僅在無待處理降級時）
        elif current < TrustTier.T3_TRUSTED:
            target_tier = current + 1
            reqs = _TIER_REQUIREMENTS.get(target_tier)
            if reqs is not None:
                failures = _check_requirements(reqs, metrics, clean_days)
                if not failures:
                    proposed_tier = target_tier
                    reasons.append(
                        f"All conditions met for {TIER_NAMES[target_tier]} "
                        f"(clean_days={clean_days:.1f}/{reqs.min_clean_days})"
                    )
                else:
                    reasons.extend(failures)
                    reasons.append(f"Maintaining {TIER_NAMES[current]}")

        # 3. T3 renewal logic / T3 續期邏輯
        elif current == TrustTier.T3_TRUSTED:
            with self._lock:
                renewals = self._state.renewals_at_t3
            if renewals >= T3_MAX_AUTO_RENEWALS:
                # Mandatory operator review / 強制 Operator 審查
                proposed_tier = current
                reasons.append(
                    f"T3 has auto-renewed {renewals}x (max={T3_MAX_AUTO_RENEWALS}). "
                    "Mandatory full Operator review required before next renewal."
                )
                return RenewalRecommendation(
                    recommended_tier=proposed_tier,
                    recommended_ttl_hours=TIER_TTL_HOURS[proposed_tier],
                    current_tier=current,
                    action="block_review",
                    reasons=reasons,
                    metrics_snapshot=_metrics_to_dict(metrics),
                    requires_operator_review=True,
                )
            else:
                # Auto-renew check at T3 / T3 自動續期檢查
                reqs = _TIER_REQUIREMENTS.get(TrustTier.T3_TRUSTED)
                if reqs is not None:
                    failures = _check_requirements(reqs, metrics, clean_days)
                    if failures:
                        proposed_tier = TrustTier.T2_ESTABLISHED
                        reasons.extend(failures)
                        reasons.append("Conditions not met — demoting to T2 Established")
                    else:
                        reasons.append(f"T3 auto-renewal #{renewals + 1}/{T3_MAX_AUTO_RENEWALS}")

        # 4. Determine action / 確定操作
        if proposed_tier > current:
            action = "promote"
        elif proposed_tier < current:
            action = "demote"
        else:
            action = "maintain"

        return RenewalRecommendation(
            recommended_tier=proposed_tier,
            recommended_ttl_hours=TIER_TTL_HOURS[proposed_tier],
            current_tier=current,
            action=action,
            reasons=reasons,
            metrics_snapshot=_metrics_to_dict(metrics),
            requires_operator_review=False,
        )

    def _compute_current_clean_days(self) -> float:
        """
        Compute elapsed clean days since streak start (must be called under lock).
        計算自連勝開始以來的乾淨天數（必須在鎖下調用）。
        """
        now_ms = int(time.time() * 1000)
        streak_start = self._state.clean_day_streak_start_ts_ms or now_ms
        return max(0.0, (now_ms - streak_start) / 86_400_000.0)

    def update_clean_days(self) -> None:
        """
        Refresh clean_days_in_tier from wall clock (call periodically e.g. daily).
        從掛鐘刷新 clean_days_in_tier（定期調用，如每天一次）。
        """
        with self._lock:
            if self._state.pending_downgrade_tier is None:
                self._state.clean_days_in_tier = self._compute_current_clean_days()
                self._save()


# ─────────────────────────────────────────────────────────────────────────────
# Requirement checker / 要求檢查器
# ─────────────────────────────────────────────────────────────────────────────

def _check_requirements(
    reqs: TierRequirements,
    metrics: TrustMetrics,
    clean_days: float,
) -> list[str]:
    """
    Return list of failed condition strings; empty = all passed.
    返回未通過條件的列表；空列表 = 全部通過。
    """
    failures: list[str] = []

    if clean_days < reqs.min_clean_days:
        failures.append(
            f"clean_days={clean_days:.1f} < required={reqs.min_clean_days:.0f}"
        )
    if metrics.net_pnl <= reqs.min_net_pnl:
        failures.append(f"net_pnl={metrics.net_pnl:.2f} must be > {reqs.min_net_pnl:.2f}")
    if metrics.max_daily_drawdown_pct > reqs.max_daily_drawdown_pct:
        failures.append(
            f"max_daily_drawdown={metrics.max_daily_drawdown_pct:.1f}% > limit={reqs.max_daily_drawdown_pct:.1f}%"
        )
    if metrics.cost_ratio > reqs.max_cost_ratio:
        failures.append(
            f"cost_ratio={metrics.cost_ratio:.2f} > limit={reqs.max_cost_ratio:.2f}"
        )
    if reqs.zero_critical_incidents and metrics.critical_incident_count > 0:
        failures.append(f"critical_incidents={metrics.critical_incident_count} (must be 0)")
    if reqs.min_win_rate_pct is not None and metrics.win_rate_pct < reqs.min_win_rate_pct:
        failures.append(
            f"win_rate={metrics.win_rate_pct:.1f}% < required={reqs.min_win_rate_pct:.1f}%"
        )
    if reqs.min_profit_factor is not None and metrics.profit_factor < reqs.min_profit_factor:
        failures.append(
            f"profit_factor={metrics.profit_factor:.2f} < required={reqs.min_profit_factor:.2f}"
        )
    if reqs.min_sharpe is not None and metrics.sharpe < reqs.min_sharpe:
        failures.append(
            f"sharpe={metrics.sharpe:.2f} < required={reqs.min_sharpe:.2f}"
        )
    if (
        reqs.max_consecutive_losses is not None
        and metrics.consecutive_losses > reqs.max_consecutive_losses
    ):
        failures.append(
            f"consecutive_losses={metrics.consecutive_losses} > limit={reqs.max_consecutive_losses}"
        )
    if (
        reqs.max_window_drawdown_pct is not None
        and metrics.max_window_drawdown_pct > reqs.max_window_drawdown_pct
    ):
        failures.append(
            f"window_drawdown={metrics.max_window_drawdown_pct:.1f}% > limit={reqs.max_window_drawdown_pct:.1f}%"
        )

    return failures


def _metrics_to_dict(m: TrustMetrics) -> dict[str, Any]:
    """Convert TrustMetrics to dict for API serialization. / 轉換指標為字典。"""
    return asdict(m)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton / 模塊級單例
# ─────────────────────────────────────────────────────────────────────────────

_ENGINE: Optional[EarnedTrustEngine] = None
_ENGINE_LOCK = threading.Lock()


def get_trust_engine() -> EarnedTrustEngine:
    """
    Get or create the module-level EarnedTrustEngine singleton.
    獲取或創建模塊級 EarnedTrustEngine 單例。
    """
    global _ENGINE
    if _ENGINE is None:
        with _ENGINE_LOCK:
            if _ENGINE is None:
                _ENGINE = EarnedTrustEngine()
    return _ENGINE
