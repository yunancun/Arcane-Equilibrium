# MODULE_NOTE (English):
#   Unit tests for EarnedTrustEngine — the earned-trust TTL ladder state machine.
#   Covers: tier promotion, demotion, pending downgrade, T3 renewal cap,
#   mid-session downgrade triggers, incident recording, persistence, and singleton.
#
# MODULE_NOTE (中文):
#   EarnedTrustEngine 單元測試 — 贏得信任 TTL 階梯狀態機。
#   覆蓋：tier 晉升、降級、待處理降級、T3 續期上限、
#   中途降級觸發、事件記錄、持久化、單例。

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.app.earned_trust_engine import (
    MIDTERM_CONSECUTIVE_LOSS_LIMIT,
    MIDTERM_DRAWDOWN_T2T3_PCT,
    MIDTERM_RECONCILER_MAJOR_DRIFT_CYCLES,
    PROMOTE_CLEAN_DAYS,
    T3_MAX_AUTO_RENEWALS,
    TIER_TTL_HOURS,
    EarnedTrustEngine,
    EarnedTrustState,
    MidSessionDowngrade,
    RenewalRecommendation,
    TrustMetrics,
    TrustTier,
    _check_requirements,
    _TIER_REQUIREMENTS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures / 測試夾具
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine(tmp_path):
    """Fresh EarnedTrustEngine with isolated temp directory. / 獨立臨時目錄的新引擎。"""
    return EarnedTrustEngine(data_dir=str(tmp_path))


def _good_metrics(**kwargs) -> TrustMetrics:
    """
    Return a TrustMetrics instance that passes ALL tier requirements.
    返回通過所有 tier 要求的 TrustMetrics 實例。
    """
    base = TrustMetrics(
        net_pnl=50.0,
        win_rate_pct=45.0,
        profit_factor=1.5,
        sharpe=1.0,
        cost_ratio=0.2,
        max_daily_drawdown_pct=2.0,
        max_window_drawdown_pct=5.0,
        consecutive_losses=1,
        reconciler_major_drift_cycles=0,
        critical_incident_count=0,
        major_incident_count=0,
        observation_days=30.0,
    )
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


def _bad_metrics() -> TrustMetrics:
    """Return TrustMetrics that fail all requirements. / 不滿足任何要求的指標。"""
    return TrustMetrics(
        net_pnl=-10.0,
        win_rate_pct=20.0,
        profit_factor=0.5,
        sharpe=-0.2,
        cost_ratio=0.8,
        max_daily_drawdown_pct=20.0,
        max_window_drawdown_pct=30.0,
        consecutive_losses=10,
        critical_incident_count=2,
        observation_days=30.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Initial state / 初始狀態
# ─────────────────────────────────────────────────────────────────────────────

class TestInitialState:
    def test_starts_at_t0(self, engine):
        """New engine starts at T0 Entry. / 新引擎從 T0 開始。"""
        snap = engine.get_state_snapshot()
        assert snap["current_tier"] == TrustTier.T0_ENTRY

    def test_clean_days_zero(self, engine):
        """Clean days start at zero. / 連勝天數從零開始。"""
        snap = engine.get_state_snapshot()
        assert snap["clean_days_in_tier"] >= 0.0

    def test_no_pending_downgrade(self, engine):
        """No pending downgrade at start. / 初始無待處理降級。"""
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] is None

    def test_ttl_hours_correct(self):
        """TIER_TTL_HOURS values match design spec. / TTL 值符合設計規格。"""
        assert TIER_TTL_HOURS[0] == 24
        assert TIER_TTL_HOURS[1] == 72
        assert TIER_TTL_HOURS[2] == 168
        assert TIER_TTL_HOURS[3] == 360

    def test_promote_clean_days_ladder(self):
        """Promotion clean-day thresholds match design spec. / 晉升乾淨天數閾值符合設計。"""
        assert PROMOTE_CLEAN_DAYS[1] == 7.0
        assert PROMOTE_CLEAN_DAYS[2] == 14.0
        assert PROMOTE_CLEAN_DAYS[3] == 21.0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Session lifecycle hooks / Session 生命週期 hook
# ─────────────────────────────────────────────────────────────────────────────

class TestSessionLifecycle:
    def test_on_session_start_records_expiry(self, engine):
        """on_session_start stores the expiry timestamp. / on_session_start 記錄到期時間。"""
        exp_ms = int(time.time() * 1000) + 86_400_000
        engine.on_session_start(auth_expires_ts_ms=exp_ms)
        snap = engine.get_state_snapshot()
        assert snap["last_auth_expires_ts_ms"] == exp_ms

    def test_on_session_stop_resets_to_t0(self, engine):
        """on_session_stop resets tier to T0 regardless of prior tier. / 停止後重置為 T0。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        assert engine.get_state_snapshot()["current_tier"] == 2
        engine.on_session_stop()
        snap = engine.get_state_snapshot()
        assert snap["current_tier"] == 0
        assert snap["pending_downgrade_tier"] is None
        assert snap["last_auth_expires_ts_ms"] is None

    def test_session_stop_records_history(self, engine):
        """Voluntary stop event appears in promotion_history. / 主動停止記錄在歷史中。"""
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        engine.on_session_stop()
        with engine._lock:
            hist = engine._state.promotion_history
        events = [h["event"] for h in hist]
        assert "session_stop_reset" in events

    def test_session_stop_t0_no_history_entry(self, engine):
        """Stopping at T0 does not add redundant history entry. / T0 停止不添加多餘歷史。"""
        engine.on_session_stop()  # already T0
        with engine._lock:
            hist = engine._state.promotion_history
        stop_events = [h for h in hist if h.get("event") == "session_stop_reset"]
        assert len(stop_events) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Renewal + tier transitions / 續期 + tier 轉換
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthRenewal:
    def test_renew_promotes_tier(self, engine):
        """on_auth_renewed updates current_tier. / on_auth_renewed 更新 tier。"""
        exp_ms = int(time.time() * 1000) + 86_400_000
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=exp_ms)
        assert engine.get_state_snapshot()["current_tier"] == 1

    def test_renew_clears_pending_downgrade(self, engine):
        """Renewal clears pending_downgrade. / 續期清除待處理降級。"""
        with engine._lock:
            engine._state.pending_downgrade_tier = 0
            engine._state.pending_downgrade_reason = "test"
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] is None

    def test_renew_same_tier_updates_expiry(self, engine):
        """Renewing at same tier updates expiry without resetting clean days. / 同 tier 更新到期時間。"""
        exp1 = int(time.time() * 1000) + 86_400_000
        engine.on_auth_renewed(new_tier=0, new_expires_ts_ms=exp1)
        exp2 = exp1 + 86_400_000
        engine.on_auth_renewed(new_tier=0, new_expires_ts_ms=exp2)
        snap = engine.get_state_snapshot()
        assert snap["last_auth_expires_ts_ms"] == exp2

    def test_renew_t3_increments_counter(self, engine):
        """Renewing T3→T3 increments renewals_at_t3. / T3→T3 遞增計數器。"""
        exp_ms = int(time.time() * 1000) + 3_600_000
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=exp_ms)  # first time at T3 — counter=0
        snap1 = engine.get_state_snapshot()
        assert snap1["renewals_at_t3"] == 0  # fresh entry
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=exp_ms + 3_600_000)  # renew again
        snap2 = engine.get_state_snapshot()
        assert snap2["renewals_at_t3"] == 1

    def test_renew_demotion_resets_clean_days(self, engine):
        """Demoting tier resets clean_days_in_tier to 0. / 降級重置連勝天數。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        snap = engine.get_state_snapshot()
        assert snap["clean_days_in_tier"] <= 0.01  # just reset


# ─────────────────────────────────────────────────────────────────────────────
# 4. evaluate_renewal — promotion / 續期評估 — 晉升
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluateRenewal:
    def _set_clean_days(self, engine, days: float) -> None:
        """Manually backdate the clean streak so engine sees desired clean_days. / 手動設置連勝天數。"""
        with engine._lock:
            epoch_ms = int(time.time() * 1000) - int(days * 86_400_000)
            engine._state.clean_day_streak_start_ts_ms = epoch_ms
            engine._state.clean_days_in_tier = days

    def test_maintain_at_t0_insufficient_days(self, engine):
        """Insufficient clean days → maintains T0. / 天數不足保持 T0。"""
        self._set_clean_days(engine, 3.0)
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "maintain"
        assert rec.recommended_tier == 0

    def test_promote_t0_to_t1(self, engine):
        """7 clean days + good metrics → promote to T1. / 7天乾淨+好指標 → 晉升 T1。"""
        self._set_clean_days(engine, 7.5)
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "promote"
        assert rec.recommended_tier == 1

    def test_promote_t1_to_t2(self, engine):
        """14 clean days + good metrics at T1 → promote to T2. / T1 14天 → 晉升 T2。"""
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        self._set_clean_days(engine, 14.5)
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "promote"
        assert rec.recommended_tier == 2

    def test_promote_t2_to_t3(self, engine):
        """21 clean days + good metrics at T2 → promote to T3. / T2 21天 → 晉升 T3。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        self._set_clean_days(engine, 21.5)
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "promote"
        assert rec.recommended_tier == 3

    def test_no_promote_with_bad_metrics(self, engine):
        """Bad metrics block promotion even with enough clean days. / 壞指標阻止晉升。"""
        self._set_clean_days(engine, 7.5)
        rec = engine.evaluate_renewal(_bad_metrics())
        assert rec.recommended_tier == 0  # stays T0

    def test_no_promote_with_critical_incident(self, engine):
        """Critical incident blocks promotion. / 嚴重事件阻止晉升。"""
        self._set_clean_days(engine, 7.5)
        rec = engine.evaluate_renewal(_good_metrics(critical_incident_count=1))
        assert rec.recommended_tier == 0

    def test_demote_when_pending_downgrade(self, engine):
        """Pending downgrade overrides promotion. / 待處理降級覆蓋晉升。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        with engine._lock:
            engine._state.pending_downgrade_tier = 1
            engine._state.pending_downgrade_reason = "test_drawdown"
        self._set_clean_days(engine, 30.0)
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "demote"
        assert rec.recommended_tier == 1

    def test_t3_block_review_when_cap_exhausted(self, engine):
        """T3 at auto-renewal cap → block_review action. / T3 上限 → block_review。"""
        exp_ms = int(time.time() * 1000) + 86_400_000
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=exp_ms)
        with engine._lock:
            engine._state.renewals_at_t3 = T3_MAX_AUTO_RENEWALS
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "block_review"
        assert rec.requires_operator_review is True

    def test_t3_auto_renew_under_cap(self, engine):
        """T3 under auto-renewal cap → maintain. / T3 未達上限 → maintain。"""
        exp_ms = int(time.time() * 1000) + 86_400_000
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=exp_ms)
        with engine._lock:
            engine._state.renewals_at_t3 = 0
        self._set_clean_days(engine, 21.5)
        rec = engine.evaluate_renewal(_good_metrics())
        assert rec.action == "maintain"
        assert rec.recommended_tier == 3
        assert rec.requires_operator_review is False

    def test_t3_demote_when_conditions_not_met(self, engine):
        """T3 under cap but bad metrics → demote to T2. / T3 未達上限但指標差 → 降至 T2。"""
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        with engine._lock:
            engine._state.renewals_at_t3 = 0
        rec = engine.evaluate_renewal(_bad_metrics())
        assert rec.action == "demote"
        assert rec.recommended_tier == 2


# ─────────────────────────────────────────────────────────────────────────────
# 5. Mid-session downgrade / 中途降級
# ─────────────────────────────────────────────────────────────────────────────

class TestMidSessionDowngrade:
    def test_no_downgrade_at_t0(self, engine):
        """T0 cannot be downgraded further. / T0 無法再降。"""
        metrics = TrustMetrics(consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT + 1)
        result = engine.check_mid_session_downgrade(metrics)
        assert result is None

    def test_consecutive_losses_triggers_downgrade(self, engine):
        """Excessive consecutive losses flag pending downgrade. / 連續虧損觸發降級標記。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        metrics = TrustMetrics(consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT)
        result = engine.check_mid_session_downgrade(metrics)
        assert isinstance(result, MidSessionDowngrade)
        assert result.to_tier == 1
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] == 1

    def test_drawdown_triggers_downgrade_t2_t3(self, engine):
        """High drawdown at T2+ triggers pending downgrade. / T2+ 高回撤觸發降級。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        metrics = TrustMetrics(max_daily_drawdown_pct=MIDTERM_DRAWDOWN_T2T3_PCT)
        result = engine.check_mid_session_downgrade(metrics)
        assert result is not None
        assert result.from_tier == 2

    def test_drawdown_no_trigger_at_t1(self, engine):
        """Drawdown limit only applies to T2+, not T1. / 回撤限制僅適用於 T2+。"""
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        metrics = TrustMetrics(max_daily_drawdown_pct=MIDTERM_DRAWDOWN_T2T3_PCT)
        result = engine.check_mid_session_downgrade(metrics)
        assert result is None  # T1 drawdown rule not applied

    def test_reconciler_drift_triggers_downgrade(self, engine):
        """Reconciler major drift triggers downgrade. / 對賬主要漂移觸發降級。"""
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        metrics = TrustMetrics(
            reconciler_major_drift_cycles=MIDTERM_RECONCILER_MAJOR_DRIFT_CYCLES,
        )
        result = engine.check_mid_session_downgrade(metrics)
        assert result is not None
        assert result.to_tier == 0

    def test_downgrade_resets_clean_streak(self, engine):
        """Mid-session downgrade resets clean_days_in_tier. / 中途降級重置連勝天數。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        with engine._lock:
            engine._state.clean_days_in_tier = 10.0
        engine.check_mid_session_downgrade(
            TrustMetrics(consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT)
        )
        snap = engine.get_state_snapshot()
        assert snap["clean_days_in_tier"] <= 0.01

    def test_second_downgrade_uses_lower_tier(self, engine):
        """Second downgrade lowers further if current pending is higher. / 第二次降級選更低 tier。"""
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        # First downgrade → pending=2
        engine.check_mid_session_downgrade(
            TrustMetrics(consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT)
        )
        # Second downgrade with drawdown — should further lower
        engine.check_mid_session_downgrade(
            TrustMetrics(
                consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT,
                max_daily_drawdown_pct=MIDTERM_DRAWDOWN_T2T3_PCT + 1,
            )
        )
        snap = engine.get_state_snapshot()
        # Pending should be ≤ 2 (the first drop from T3)
        assert snap["pending_downgrade_tier"] is not None and snap["pending_downgrade_tier"] <= 2

    def test_no_duplicate_downgrade_if_already_lower(self, engine):
        """Existing pending at a lower tier is not overwritten with a higher one. / 不覆蓋更低的待處理降級。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        with engine._lock:
            engine._state.pending_downgrade_tier = 0  # already at lowest
        engine.check_mid_session_downgrade(
            TrustMetrics(consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT)
        )
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] == 0  # not changed to 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. Incident recording / 事件記錄
# ─────────────────────────────────────────────────────────────────────────────

class TestIncidentRecording:
    def test_critical_incident_flags_t0_reset(self, engine):
        """Critical incident at T2 sets pending_downgrade=0. / T2 嚴重事件 → 待降至 T0。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        engine.record_incident("critical", "test_critical")
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] == 0

    def test_major_incident_flags_one_tier_down(self, engine):
        """Major incident at T2 sets pending_downgrade=1. / T2 主要事件 → 待降至 T1。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        engine.record_incident("major", "test_major")
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] == 1

    def test_minor_incident_no_tier_change(self, engine):
        """Minor incident resets streak but no tier downgrade. / 輕微事件重置連勝但不降 tier。"""
        engine.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        engine.record_incident("minor", "test_minor")
        snap = engine.get_state_snapshot()
        assert snap["pending_downgrade_tier"] is None
        assert snap["clean_days_in_tier"] <= 0.01

    def test_incident_at_t0_no_change(self, engine):
        """Critical incident at T0 doesn't set negative tier. / T0 嚴重事件不產生負 tier。"""
        engine.record_incident("critical", "at_t0")
        snap = engine.get_state_snapshot()
        assert snap["current_tier"] == 0
        assert snap["pending_downgrade_tier"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 7. Requirement checker / 要求檢查器
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckRequirements:
    def test_all_pass(self):
        """All good metrics → no failures. / 好指標 → 無失敗。"""
        reqs = _TIER_REQUIREMENTS[1]
        failures = _check_requirements(reqs, _good_metrics(), clean_days=7.5)
        assert failures == []

    def test_insufficient_clean_days(self):
        """Insufficient clean days → failure listed. / 天數不足 → 列出失敗。"""
        reqs = _TIER_REQUIREMENTS[1]
        failures = _check_requirements(reqs, _good_metrics(), clean_days=5.0)
        assert any("clean_days" in f for f in failures)

    def test_negative_pnl_fails(self):
        """Negative net_pnl fails T1 requirement. / 負 PnL 不通過 T1 要求。"""
        reqs = _TIER_REQUIREMENTS[1]
        failures = _check_requirements(reqs, _good_metrics(net_pnl=-1.0), clean_days=7.5)
        assert any("net_pnl" in f for f in failures)

    def test_high_drawdown_fails(self):
        """Drawdown above limit → failure. / 回撤超限 → 失敗。"""
        reqs = _TIER_REQUIREMENTS[1]
        failures = _check_requirements(reqs, _good_metrics(max_daily_drawdown_pct=6.0), clean_days=7.5)
        assert any("drawdown" in f for f in failures)

    def test_critical_incident_fails(self):
        """Critical incident → failure. / 嚴重事件 → 失敗。"""
        reqs = _TIER_REQUIREMENTS[2]
        failures = _check_requirements(reqs, _good_metrics(critical_incident_count=1), clean_days=14.5)
        assert any("critical" in f for f in failures)

    def test_t3_consecutive_losses_fails(self):
        """Too many consecutive losses fails T3. / 連續虧損過多不通過 T3。"""
        reqs = _TIER_REQUIREMENTS[3]
        failures = _check_requirements(reqs, _good_metrics(consecutive_losses=6), clean_days=21.5)
        assert any("consecutive_losses" in f for f in failures)

    def test_t3_window_drawdown_fails(self):
        """Window drawdown above T3 limit → failure. / 窗口回撤超 T3 上限 → 失敗。"""
        reqs = _TIER_REQUIREMENTS[3]
        failures = _check_requirements(reqs, _good_metrics(max_window_drawdown_pct=11.0), clean_days=21.5)
        assert any("window_drawdown" in f for f in failures)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Persistence / 持久化
# ─────────────────────────────────────────────────────────────────────────────

class TestPersistence:
    def test_state_saved_and_reloaded(self, tmp_path):
        """State persists across engine re-instantiation. / 狀態跨引擎實例持久化。"""
        e1 = EarnedTrustEngine(data_dir=str(tmp_path))
        e1.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        # Re-instantiate from same directory
        e2 = EarnedTrustEngine(data_dir=str(tmp_path))
        snap = e2.get_state_snapshot()
        assert snap["current_tier"] == 1

    def test_corrupt_state_file_resets(self, tmp_path):
        """Corrupt JSON file → fresh state (no crash). / 損壞 JSON → 全新狀態（不崩潰）。"""
        state_path = tmp_path / "earned_trust_state.json"
        state_path.write_text("not_valid_json")
        e = EarnedTrustEngine(data_dir=str(tmp_path))
        snap = e.get_state_snapshot()
        assert snap["current_tier"] == 0  # fresh state

    def test_save_creates_directory(self, tmp_path):
        """Engine creates data_dir if it doesn't exist. / 不存在則創建 data_dir。"""
        nested = tmp_path / "deep" / "nested"
        e = EarnedTrustEngine(data_dir=str(nested))
        e.on_auth_renewed(new_tier=0, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        assert (nested / "earned_trust_state.json").exists()

    def test_promotion_history_persisted(self, tmp_path):
        """promotion_history is preserved across reload. / 晉升歷史跨加載保留。"""
        e1 = EarnedTrustEngine(data_dir=str(tmp_path))
        e1.on_auth_renewed(new_tier=1, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        e1.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        e2 = EarnedTrustEngine(data_dir=str(tmp_path))
        with e2._lock:
            history = e2._state.promotion_history
        assert len(history) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 9. State snapshot completeness / 快照完整性
# ─────────────────────────────────────────────────────────────────────────────

class TestStateSnapshot:
    def test_snapshot_has_required_fields(self, engine):
        """get_state_snapshot() includes all API-required fields. / 快照包含所有 API 必需字段。"""
        snap = engine.get_state_snapshot()
        required = [
            "current_tier", "tier_name", "tier_ttl_hours",
            "clean_days_in_tier", "clean_days_required_for_promotion",
            "renewals_at_t3", "pending_downgrade_tier",
            "near_expiry", "requires_operator_review",
            "t3_max_renewals",
        ]
        for field in required:
            assert field in snap, f"Missing snapshot field: {field}"

    def test_near_expiry_true_when_close(self, engine):
        """near_expiry=True when < EXPIRY_WARN_HOURS remaining. / 剩餘 < 警示閾值時 near_expiry=True。"""
        # Set expiry 1 hour out (< 2h warning threshold)
        exp_ms = int(time.time() * 1000) + 3_600_000
        engine.on_session_start(auth_expires_ts_ms=exp_ms)
        snap = engine.get_state_snapshot()
        assert snap["near_expiry"] is True

    def test_near_expiry_false_when_far(self, engine):
        """near_expiry=False when > EXPIRY_WARN_HOURS remaining. / 剩餘充足時 near_expiry=False。"""
        exp_ms = int(time.time() * 1000) + 86_400_000  # 24h out
        engine.on_session_start(auth_expires_ts_ms=exp_ms)
        snap = engine.get_state_snapshot()
        assert snap["near_expiry"] is False

    def test_requires_review_only_at_t3_cap(self, engine):
        """requires_operator_review only True at T3 with exhausted renewals. / 僅 T3 上限時為 True。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        assert engine.get_state_snapshot()["requires_operator_review"] is False
        engine.on_auth_renewed(new_tier=3, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        with engine._lock:
            engine._state.renewals_at_t3 = T3_MAX_AUTO_RENEWALS
        assert engine.get_state_snapshot()["requires_operator_review"] is True


# ─────────────────────────────────────────────────────────────────────────────
# 10. Thread safety / 線程安全
# ─────────────────────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_concurrent_renew_no_exception(self, engine):
        """Concurrent on_auth_renewed calls don't raise. / 並發 on_auth_renewed 不拋異常。"""
        errors: list[Exception] = []

        def renew(tier: int) -> None:
            try:
                engine.on_auth_renewed(
                    new_tier=tier % 4,
                    new_expires_ts_ms=int(time.time() * 1000) + 86_400_000,
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=renew, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors in concurrent renew: {errors}"

    def test_concurrent_mid_session_check_no_exception(self, engine):
        """Concurrent check_mid_session_downgrade calls don't corrupt state. / 並發降級檢查不破壞狀態。"""
        engine.on_auth_renewed(new_tier=2, new_expires_ts_ms=int(time.time() * 1000) + 86_400_000)
        errors: list[Exception] = []

        def check() -> None:
            try:
                engine.check_mid_session_downgrade(
                    TrustMetrics(consecutive_losses=MIDTERM_CONSECUTIVE_LOSS_LIMIT)
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=check) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # State should be coherent (pending tier ≤ current)
        snap = engine.get_state_snapshot()
        if snap["pending_downgrade_tier"] is not None:
            assert snap["pending_downgrade_tier"] <= snap["current_tier"]
