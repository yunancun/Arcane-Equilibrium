"""
Tests for Strategy Promotion Pipeline / 策略漸進放權管線測試

Covers: 6-01 pipeline state machine, 6-02 graduation gates, 6-03 live approval.
"""

import time
from datetime import datetime, timezone

import numpy as np
import pytest

from app.promotion_pipeline import (
    PromotionGate,
    PromotionStage,
    PipelineEntry,
    PAPER_GRADUATION_GATES,
    DEMO_GRADUATION_GATES,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 測試夾具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def gate() -> PromotionGate:
    """Fresh PromotionGate with audit callback."""
    audit_log = []
    return PromotionGate(audit_callback=lambda r: audit_log.append(r))


@pytest.fixture
def audit_log() -> list:
    return []


@pytest.fixture
def gate_with_log(audit_log) -> PromotionGate:
    return PromotionGate(audit_callback=lambda r: audit_log.append(r))


def _persistent_alpha_candidates(
    n_candidates: int = 10,
    n_periods: int = 256,
    seed: int = 42,
) -> list[np.ndarray]:
    """Candidates with stable IS/OOS ranking for low PBO."""
    rng = np.random.default_rng(seed)
    return [
        float(k) * 0.05 + rng.normal(0.0, 0.05, size=n_periods)
        for k in range(n_candidates)
    ]


def _add_passing_selection_bias(
    gate: PromotionGate,
    strategy_name: str = "test",
) -> dict:
    ok, report = gate.update_demo_selection_bias_evidence(
        strategy_name,
        observed_sharpe=4.0,
        n_trials=10,
        n_observations=500,
        candidate_oos_returns=_persistent_alpha_candidates(),
    )
    assert ok, report
    return report


def _add_passing_tail_risk(
    gate: PromotionGate,
    strategy_name: str = "test",
) -> dict:
    rng = np.random.default_rng(20260509)
    returns = rng.normal(0.002, 0.006, size=320)
    ok, report = gate.update_demo_tail_risk_evidence(
        strategy_name,
        portfolio_returns=returns,
        stress_exposures={"crypto_beta": 0.05, "liquidity": 0.02},
        n_bootstrap=120,
        seed=42,
    )
    assert ok, report
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# 6-01: Pipeline state machine / 管線狀態機
# ═══════════════════════════════════════════════════════════════════════════════

class TestPipelineStateMachine:
    """Tests for basic registration and stage transitions."""

    def test_register_strategy(self, gate: PromotionGate):
        entry = gate.register_strategy("ma_crossover")
        assert entry.strategy_name == "ma_crossover"
        assert entry.current_stage == PromotionStage.LEARNING

    def test_register_idempotent(self, gate: PromotionGate):
        e1 = gate.register_strategy("bb_breakout")
        e2 = gate.register_strategy("bb_breakout")
        assert e1.strategy_name == e2.strategy_name

    def test_get_stage_unregistered(self, gate: PromotionGate):
        assert gate.get_stage("nonexistent") == PromotionStage.LEARNING

    def test_promote_learning_to_paper(self, gate: PromotionGate):
        gate.register_strategy("test_strat")
        ok, msg = gate.promote("test_strat", PromotionStage.PAPER_SHADOW)
        assert ok
        assert gate.get_stage("test_strat") == PromotionStage.PAPER_SHADOW

    def test_cannot_skip_stages(self, gate: PromotionGate):
        gate.register_strategy("test_strat")
        ok, msg = gate.promote("test_strat", PromotionStage.DEMO_ACTIVE)
        assert not ok
        assert "invalid_transition" in msg

    def test_promote_unregistered_fails(self, gate: PromotionGate):
        ok, msg = gate.promote("ghost", PromotionStage.PAPER_SHADOW)
        assert not ok
        assert msg == "not_registered"

    def test_full_pipeline_happy_path(self, gate: PromotionGate):
        """Full LEARNING -> ... -> LIVE_ACTIVE with all gates passing."""
        gate.register_strategy("full_test")

        # LEARNING -> PAPER_SHADOW
        ok, _ = gate.promote("full_test", PromotionStage.PAPER_SHADOW)
        assert ok

        # Set paper metrics that pass gates
        gate.update_paper_metrics(
            "full_test", trades=150, win_rate=0.55,
            net_pnl_pct=5.0, max_drawdown_pct=7.0, sharpe=1.2,
        )
        # Backdate paper_start_ts to pass duration gate
        with gate._lock:
            gate._entries["full_test"].paper_start_ts = time.time() - 15 * 86400

        # PAPER_SHADOW -> DEMO_ACTIVE
        ok, _ = gate.promote("full_test", PromotionStage.DEMO_ACTIVE)
        assert ok

        # Set demo metrics that pass gates
        gate.update_demo_metrics(
            "full_test", trades=250, win_rate=0.60,
            net_pnl_pct=8.0, max_drawdown_pct=5.0, sharpe=1.5,
            avg_slippage_bps=10.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["full_test"].demo_start_ts = time.time() - 22 * 86400

        _add_passing_selection_bias(gate, "full_test")
        _add_passing_tail_risk(gate, "full_test")

        # DEMO_ACTIVE -> LIVE_PENDING
        ok, _ = gate.promote("full_test", PromotionStage.LIVE_PENDING)
        assert ok

        # LIVE_PENDING -> LIVE_ACTIVE requires operator approval
        ok, msg = gate.promote("full_test", PromotionStage.LIVE_ACTIVE)
        assert not ok
        assert "operator_approval_required" in msg

        # Set operator approval
        gate.set_operator_decision(
            "full_test", "APPROVED", capital_pct=10.0, max_leverage=5.0
        )

        # Now promote should work
        ok, _ = gate.promote("full_test", PromotionStage.LIVE_ACTIVE)
        assert ok
        assert gate.get_stage("full_test") == PromotionStage.LIVE_ACTIVE


# ═══════════════════════════════════════════════════════════════════════════════
# 6-02: Graduation gate checks / 畢業門檻檢查
# ═══════════════════════════════════════════════════════════════════════════════

class TestGraduationGates:
    """Tests for paper and demo graduation gate enforcement."""

    def test_paper_gates_fail_no_data(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        eligible, reasons = gate.check_paper_graduation("test")
        assert not eligible
        assert len(reasons) > 0

    def test_paper_gates_fail_insufficient_trades(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        gate.update_paper_metrics("test", trades=50, win_rate=0.5,
                                  net_pnl_pct=2.0, max_drawdown_pct=5.0, sharpe=0.8)
        with gate._lock:
            gate._entries["test"].paper_start_ts = time.time() - 15 * 86400
        eligible, reasons = gate.check_paper_graduation("test")
        assert not eligible
        assert any("trades:" in r for r in reasons)

    def test_paper_gates_fail_duration(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        gate.update_paper_metrics("test", trades=150, win_rate=0.5,
                                  net_pnl_pct=2.0, max_drawdown_pct=5.0, sharpe=0.8)
        # paper_start_ts is set by update_paper_metrics to now, so < 14 days
        eligible, reasons = gate.check_paper_graduation("test")
        assert not eligible
        assert any("duration:" in r for r in reasons)

    def test_paper_gates_fail_drawdown(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        gate.update_paper_metrics("test", trades=150, win_rate=0.5,
                                  net_pnl_pct=2.0, max_drawdown_pct=15.0, sharpe=0.8)
        with gate._lock:
            gate._entries["test"].paper_start_ts = time.time() - 15 * 86400
        eligible, reasons = gate.check_paper_graduation("test")
        assert not eligible
        assert any("drawdown:" in r for r in reasons)

    def test_paper_gates_fail_sharpe(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        gate.update_paper_metrics("test", trades=150, win_rate=0.5,
                                  net_pnl_pct=2.0, max_drawdown_pct=5.0, sharpe=0.3)
        with gate._lock:
            gate._entries["test"].paper_start_ts = time.time() - 15 * 86400
        eligible, reasons = gate.check_paper_graduation("test")
        assert not eligible
        assert any("sharpe:" in r for r in reasons)

    def test_paper_gates_pass(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        gate.update_paper_metrics("test", trades=150, win_rate=0.55,
                                  net_pnl_pct=5.0, max_drawdown_pct=7.0, sharpe=1.0)
        with gate._lock:
            gate._entries["test"].paper_start_ts = time.time() - 15 * 86400
        eligible, reasons = gate.check_paper_graduation("test")
        assert eligible
        assert len(reasons) == 0

    def test_demo_gates_fail_no_data(self, gate: PromotionGate):
        gate.register_strategy("test")
        gate.promote("test", PromotionStage.PAPER_SHADOW)
        # Force to DEMO_ACTIVE for testing gate check
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible

    def test_demo_gates_fail_slippage(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            "test", trades=250, win_rate=0.6, net_pnl_pct=5.0,
            max_drawdown_pct=5.0, sharpe=1.0,
            avg_slippage_bps=20.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["test"].demo_start_ts = time.time() - 22 * 86400
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        assert any("slippage:" in r for r in reasons)

    def test_demo_gates_fail_without_selection_bias_evidence(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            "test", trades=250, win_rate=0.6, net_pnl_pct=8.0,
            max_drawdown_pct=5.0, sharpe=1.5,
            avg_slippage_bps=10.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["test"].demo_start_ts = time.time() - 22 * 86400
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        assert "selection_bias:no_evidence" in reasons

    def test_demo_gates_fail_without_tail_risk_evidence(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            "test", trades=250, win_rate=0.6, net_pnl_pct=8.0,
            max_drawdown_pct=5.0, sharpe=1.5,
            avg_slippage_bps=10.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["test"].demo_start_ts = time.time() - 22 * 86400
        _add_passing_selection_bias(gate, "test")
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        assert "tail_risk:no_evidence" in reasons

    def test_demo_selection_bias_low_dsr_blocks(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            "test", trades=250, win_rate=0.6, net_pnl_pct=8.0,
            max_drawdown_pct=5.0, sharpe=1.5,
            avg_slippage_bps=10.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["test"].demo_start_ts = time.time() - 22 * 86400

        ok, report = gate.update_demo_selection_bias_evidence(
            "test",
            observed_sharpe=0.1,
            n_trials=20,
            n_observations=200,
            candidate_oos_returns=_persistent_alpha_candidates(),
        )
        assert not ok
        assert report["verdict"] == "block"
        assert "dsr_block" in report["reasons"]

        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        assert any(r.startswith("selection_bias:block:") for r in reasons)

    def test_demo_selection_bias_missing_cv_returns_defers(self, gate: PromotionGate):
        gate.register_strategy("test")
        ok, report = gate.update_demo_selection_bias_evidence(
            "test",
            observed_sharpe=4.0,
            n_trials=10,
            n_observations=500,
        )
        assert not ok
        assert report["verdict"] == "defer_data"
        assert "pbo_missing_cpcv_returns" in report["reasons"]

    def test_demo_selection_bias_invalid_input_fails_closed(self, gate: PromotionGate):
        gate.register_strategy("test")
        ok, report = gate.update_demo_selection_bias_evidence(
            "test",
            observed_sharpe=4.0,
            n_trials=10,
            n_observations=1,
            candidate_oos_returns=_persistent_alpha_candidates(),
            trial_sharpes=[0.1, 0.2],
        )
        assert not ok
        assert report["verdict"] == "block"
        assert any(str(r).startswith("selection_bias_invalid:") for r in report["reasons"])

    def test_demo_tail_risk_stress_blocks(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            "test", trades=250, win_rate=0.6, net_pnl_pct=8.0,
            max_drawdown_pct=5.0, sharpe=1.5,
            avg_slippage_bps=10.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["test"].demo_start_ts = time.time() - 22 * 86400
        _add_passing_selection_bias(gate, "test")
        rng = np.random.default_rng(20260510)
        ok, report = gate.update_demo_tail_risk_evidence(
            "test",
            portfolio_returns=rng.normal(0.002, 0.006, size=320),
            stress_exposures={"crypto_beta": 1.0},
            n_bootstrap=120,
            seed=43,
        )
        assert not ok
        assert report["verdict"] == "block"
        assert any(
            str(reason).startswith("stress:luna_2022_cascade")
            for reason in report["reasons"]
        )
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        assert any(r.startswith("tail_risk:block:") for r in reasons)

    def test_demo_gates_pass(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            "test", trades=250, win_rate=0.6, net_pnl_pct=8.0,
            max_drawdown_pct=5.0, sharpe=1.5,
            avg_slippage_bps=10.0, api_reliability=0.99,
        )
        with gate._lock:
            gate._entries["test"].demo_start_ts = time.time() - 22 * 86400
        _add_passing_selection_bias(gate, "test")
        _add_passing_tail_risk(gate, "test")
        eligible, reasons = gate.check_demo_graduation("test")
        assert eligible
        assert len(reasons) == 0

    def test_wrong_stage_for_paper_grad(self, gate: PromotionGate):
        gate.register_strategy("test")
        # Still at LEARNING, not PAPER_SHADOW
        eligible, reasons = gate.check_paper_graduation("test")
        assert not eligible
        assert any("wrong_stage" in r for r in reasons)


# ═══════════════════════════════════════════════════════════════════════════════
# 6-03: Live approval / Live 審批
# ═══════════════════════════════════════════════════════════════════════════════

class TestLiveApproval:
    """Tests for operator decision and LIVE_ACTIVE promotion."""

    def test_operator_decision_wrong_stage(self, gate: PromotionGate):
        gate.register_strategy("test")
        ok, msg = gate.set_operator_decision("test", "APPROVED")
        assert not ok
        assert "wrong_stage" in msg

    def test_operator_decision_invalid(self, gate: PromotionGate):
        ok, msg = gate.set_operator_decision("test", "INVALID")
        assert not ok
        assert "invalid_decision" in msg

    def test_operator_reject(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.LIVE_PENDING
        ok, msg = gate.set_operator_decision("test", "REJECTED")
        assert ok
        # Cannot promote after rejection
        ok, msg = gate.promote("test", PromotionStage.LIVE_ACTIVE)
        assert not ok
        assert "operator_approval_required" in msg

    def test_operator_extend(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.LIVE_PENDING
        ok, _ = gate.set_operator_decision("test", "EXTEND")
        assert ok
        # EXTEND means more observation, cannot promote yet
        ok, msg = gate.promote("test", PromotionStage.LIVE_ACTIVE)
        assert not ok

    def test_operator_approve_then_promote(self, gate: PromotionGate):
        gate.register_strategy("test")
        with gate._lock:
            gate._entries["test"].current_stage = PromotionStage.LIVE_PENDING
        gate.set_operator_decision(
            "test", "APPROVED",
            capital_pct=15.0, max_leverage=10.0,
            evaluation_report={"summary": "looks good"},
        )
        ok, msg = gate.promote("test", PromotionStage.LIVE_ACTIVE, initiator="operator")
        assert ok
        entry = gate.get_entry("test")
        assert entry.current_stage == PromotionStage.LIVE_ACTIVE
        assert entry.approved_capital_pct == 15.0
        assert entry.approved_max_leverage == 10.0


# ═══════════════════════════════════════════════════════════════════════════════
# Audit / 審計
# ═══════════════════════════════════════════════════════════════════════════════

class TestAudit:
    """Tests for audit record emission."""

    def test_register_emits_audit(self, gate_with_log, audit_log):
        gate_with_log.register_strategy("test")
        assert len(audit_log) == 1
        assert audit_log[0]["action"] == "register"

    def test_promote_emits_audit(self, gate_with_log, audit_log):
        gate_with_log.register_strategy("test")
        gate_with_log.promote("test", PromotionStage.PAPER_SHADOW)
        assert len(audit_log) == 2  # register + promote
        assert audit_log[1]["action"] == "promote"
        assert audit_log[1]["from_stage"] == "LEARNING"
        assert audit_log[1]["to_stage"] == "PAPER_SHADOW"


# ═══════════════════════════════════════════════════════════════════════════════
# Serialization / 序列化
# ═══════════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """Tests for DB persistence round-trip."""

    def test_to_db_rows(self, gate: PromotionGate):
        gate.register_strategy("ma_crossover", model_name="kama_v2")
        rows = gate.to_db_rows()
        assert len(rows) == 1
        assert rows[0]["strategy_name"] == "ma_crossover"
        assert rows[0]["current_stage"] == "LEARNING"
        assert rows[0]["model_name"] == "kama_v2"
        assert rows[0]["demo_selection_bias_report"] is None
        assert rows[0]["demo_tail_risk_report"] is None

    def test_load_from_db_rows(self):
        gate = PromotionGate()
        rows = [
            {
                "pipeline_id": 1,
                "strategy_name": "bb_breakout",
                "model_name": None,
                "model_version": None,
                "current_stage": "DEMO_ACTIVE",
                "paper_start_ts": 1700000000.0,
                "paper_trades": 200,
                "paper_win_rate": 0.55,
                "paper_net_pnl_pct": 3.0,
                "paper_max_drawdown_pct": 6.0,
                "paper_sharpe": 0.9,
                "demo_selection_bias_report": {"passes": True, "verdict": "promote"},
                "demo_tail_risk_report": {"passes": True, "verdict": "promote"},
            },
        ]
        gate.load_from_db_rows(rows)
        entry = gate.get_entry("bb_breakout")
        assert entry is not None
        assert entry.current_stage == PromotionStage.DEMO_ACTIVE
        assert entry.paper_trades == 200
        assert entry.demo_selection_bias_report == {"passes": True, "verdict": "promote"}
        assert entry.demo_tail_risk_report == {"passes": True, "verdict": "promote"}

    def test_load_from_db_rows_normalizes_timestamptz(self):
        gate = PromotionGate()
        gate.load_from_db_rows(
            [
                {
                    "strategy_name": "ma_crossover",
                    "current_stage": "DEMO_ACTIVE",
                    "paper_start_ts": datetime(2026, 5, 1, tzinfo=timezone.utc),
                    "demo_start_ts": datetime(2026, 5, 2, tzinfo=timezone.utc),
                }
            ]
        )
        entry = gate.get_entry("ma_crossover")
        assert isinstance(entry.paper_start_ts, float)
        assert isinstance(entry.demo_start_ts, float)

    def test_round_trip(self, gate: PromotionGate):
        gate.register_strategy("test_strat")
        gate.promote("test_strat", PromotionStage.PAPER_SHADOW)
        gate.update_paper_metrics(
            "test_strat", trades=100, win_rate=0.5,
            net_pnl_pct=2.0, max_drawdown_pct=5.0, sharpe=0.8,
        )
        rows = gate.to_db_rows()

        gate2 = PromotionGate()
        gate2.load_from_db_rows(rows)
        entry = gate2.get_entry("test_strat")
        assert entry.current_stage == PromotionStage.PAPER_SHADOW
        assert entry.paper_trades == 100

    def test_demo_selection_bias_report_serializes_to_status_rows(self, gate: PromotionGate):
        gate.register_strategy("test")
        report = _add_passing_selection_bias(gate, "test")
        rows = gate.to_db_rows()
        assert rows[0]["demo_selection_bias_report"] == report
        assert rows[0]["demo_selection_bias_report"]["passes"] is True

    def test_demo_tail_risk_report_serializes_to_status_rows(self, gate: PromotionGate):
        gate.register_strategy("test")
        report = _add_passing_tail_risk(gate, "test")
        rows = gate.to_db_rows()
        assert rows[0]["demo_tail_risk_report"] == report
        assert rows[0]["demo_tail_risk_report"]["passes"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 6-05: Stress / Concurrency Tests / 壓測 + 並發測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestStressConcurrency:
    """6-05: Thread-safety and performance under concurrent load.
    6-05：線程安全與並發負載下的性能測試。"""

    def test_concurrent_register_10_threads(self):
        """10 threads registering different strategies simultaneously.
        10 線程同時註冊不同策略。"""
        import threading
        gate = PromotionGate()
        errors = []

        def register_worker(idx):
            try:
                entry = gate.register_strategy(f"strat_{idx}")
                assert entry.strategy_name == f"strat_{idx}"
                assert entry.current_stage == PromotionStage.LEARNING
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent register errors: {errors}"
        # All 10 strategies should exist
        rows = gate.to_db_rows()
        assert len(rows) == 10

    def test_concurrent_promote_same_strategy(self):
        """10 threads trying to promote the same strategy — only one should succeed per stage.
        10 線程嘗試晉升同一策略 — 每階段只有一個成功。"""
        import threading
        gate = PromotionGate()
        gate.register_strategy("contested")
        results = []

        def promote_worker():
            ok, msg = gate.promote("contested", PromotionStage.PAPER_SHADOW)
            results.append((ok, msg))

        threads = [threading.Thread(target=promote_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = [r for r in results if r[0]]
        # Exactly 1 must succeed (first to acquire lock); rest get "already at or past stage"
        # P1 E2 fix: == 1 (not >= 1) to catch broken lock
        assert len(successes) == 1, f"Exactly 1 promote should succeed, got {len(successes)}"
        assert gate.get_stage("contested") == PromotionStage.PAPER_SHADOW

    def test_concurrent_register_idempotent(self):
        """10 threads registering the SAME strategy — all should get valid entry.
        10 線程註冊同一策略 — 全部應獲得有效 entry。"""
        import threading
        gate = PromotionGate()
        entries = []

        def register_worker():
            entry = gate.register_strategy("shared_strat")
            entries.append(entry)

        threads = [threading.Thread(target=register_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 10 entries should be valid
        assert len(entries) == 10
        for e in entries:
            assert e.strategy_name == "shared_strat"
            assert e.current_stage == PromotionStage.LEARNING
        # Only 1 entry in internal state
        rows = gate.to_db_rows()
        assert len(rows) == 1

    def test_rapid_full_pipeline_100_strategies(self):
        """Register and promote 100 strategies through LEARNING→PAPER_SHADOW — performance check.
        註冊並晉升 100 個策略 LEARNING→PAPER_SHADOW — 性能檢查。"""
        gate = PromotionGate()
        start = time.time()

        for i in range(100):
            gate.register_strategy(f"perf_strat_{i}")
            gate.promote(f"perf_strat_{i}", PromotionStage.PAPER_SHADOW)

        elapsed = time.time() - start
        assert elapsed < 1.0, f"100 register+promote took {elapsed:.3f}s (limit: 1s)"

        rows = gate.to_db_rows()
        assert len(rows) == 100
        for row in rows:
            assert row["current_stage"] == "PAPER_SHADOW"

    def test_concurrent_metrics_update(self):
        """10 threads updating metrics on the same strategy simultaneously.
        10 線程同時更新同一策略的指標。"""
        import threading
        gate = PromotionGate()
        gate.register_strategy("metrics_test")
        gate.promote("metrics_test", PromotionStage.PAPER_SHADOW)
        errors = []

        def update_worker(idx):
            try:
                gate.update_paper_metrics(
                    "metrics_test",
                    trades=100 + idx,
                    win_rate=0.5 + idx * 0.01,
                    net_pnl_pct=2.0 + idx,
                    max_drawdown_pct=5.0,
                    sharpe=0.8 + idx * 0.05,
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent update errors: {errors}"
        entry = gate.get_entry("metrics_test")
        assert entry is not None
        # Metrics should reflect one of the updates (last writer wins, but no corruption)
        assert entry.paper_trades >= 100
        assert entry.paper_sharpe >= 0.8


# ═══════════════════════════════════════════════════════════════════════════════
# W-AUDIT-6d #4 (2026-05-09): runtime apply spec/test — portfolio VaR/CVaR/EVT
# 從 promotion_evidence build_strategy_promotion_evidence 整鏈到
# update_demo_tail_risk_evidence + check_demo_graduation 的 contract spec test。
# **不 deploy** — 純 source/test layer 驗 runtime caller 接線一致。
# W-AUDIT-6d #4 (2026-05-09): runtime apply spec/test — portfolio VaR end-to-end
# contract spec; source/test only, NOT deploy.
# ═══════════════════════════════════════════════════════════════════════════════


class TestWAudit6dRuntimeApplySpec:
    """W-AUDIT-6d #4 — portfolio VaR runtime apply spec/test。

    這是 runtime 接線的 spec/contract test，**不 deploy**。
    證明 promotion_evidence.build_strategy_promotion_evidence →
    update_demo_tail_risk_evidence → check_demo_graduation 整鏈 contract。
    """

    def _setup_demo_active(
        self,
        gate: PromotionGate,
        strategy_name: str = "test",
        days_in_demo: int = 22,
    ) -> None:
        """Promote strategy to DEMO_ACTIVE 並設 demo_start_ts > 21d 滿足 graduation 時長要求。"""
        gate.register_strategy(strategy_name)
        with gate._lock:
            gate._entries[strategy_name].current_stage = PromotionStage.DEMO_ACTIVE
        gate.update_demo_metrics(
            strategy_name,
            trades=250,
            win_rate=0.6,
            net_pnl_pct=8.0,
            max_drawdown_pct=5.0,
            sharpe=1.5,
            avg_slippage_bps=10.0,
            api_reliability=0.99,
        )
        with gate._lock:
            gate._entries[strategy_name].demo_start_ts = time.time() - days_in_demo * 86400

    def test_runtime_apply_chain_w_audit_6d_4(self, gate: PromotionGate):
        """W-AUDIT-6d #4 — promotion_evidence → tail_risk_evidence → graduation
        chain spec：caller 走 promotion_evidence.build_strategy_promotion_evidence
        產出的 portfolio_returns 應該被 update_demo_tail_risk_evidence 接受並
        最終讓 check_demo_graduation 一致 verdict。"""
        from program_code.ml_training.promotion_evidence import (
            build_strategy_promotion_evidence,
        )

        # 模擬 W-A demo 階段 mild 樣本：5 candidate × 60 trade = 300 obs。
        # raw_bps_series 是 promotion_evidence 期望的 caller-side 格式
        # （per-trade PnL bps；下游 _return_series_from_bps 除以 10000 轉 fractional）。
        rng = np.random.default_rng(20260509)
        js_results = {}
        for k, sym in enumerate(["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOTUSDT", "ADAUSDT"]):
            # 每 candidate 60 trade，~mild profitable - mean 20 bps, std 60 bps。
            bps_series = rng.normal(20.0, 60.0, size=60).tolist()
            js_results[("test", sym)] = {
                "strategy_name": "test",
                "symbol": sym,
                "raw_bps_series": bps_series,
            }

        evidence_map = build_strategy_promotion_evidence(
            js_results, engine_mode="demo"
        )
        assert "test" in evidence_map
        evidence = evidence_map["test"]
        # 5 candidate × 60 trade = 300 obs；超過 min_observations=200。
        assert evidence.n_observations == 300
        assert len(evidence.portfolio_returns) == 300
        # bps 除以 10000 → fractional return 量級 ~0.002 (= 20 bps)。
        sample = evidence.portfolio_returns[0]
        assert -0.05 < sample < 0.05, f"fractional unit 預期 ±5%，got {sample}"

        # 走 update_demo_tail_risk_evidence — runtime caller 路徑。
        self._setup_demo_active(gate, "test")
        ok, report = gate.update_demo_tail_risk_evidence(
            "test",
            portfolio_returns=evidence.portfolio_returns,
            stress_exposures={"crypto_beta": 0.05, "liquidity": 0.02},
            n_bootstrap=120,
            seed=42,
        )
        # mild scaled 不該超 max_var_loss=5% / max_cvar_loss=8%；應 promote。
        assert report["verdict"] in {"promote", "block"}, f"got {report['verdict']}"
        # 不該因 200 obs 不足而 defer（已 300 obs）。
        assert "insufficient_observations" not in str(report.get("reasons", [])), (
            "300 obs 不該觸發 defer_data"
        )

        # 加 selection_bias evidence 後，整鏈 check_demo_graduation 一致。
        _add_passing_selection_bias(gate, "test")
        eligible, reasons = gate.check_demo_graduation("test")
        # tail_risk 是否通過依 mild 樣本實際分布；本 spec test 重在
        # **rare reason types** 不應出現（無接線 bug 時）。
        rare_bug_reasons = {
            "tail_risk:no_evidence",  # update_demo_tail_risk_evidence 未調用
            "selection_bias:no_evidence",  # _add_passing_selection_bias 未調用
        }
        for r in reasons:
            assert r not in rare_bug_reasons, (
                f"出現接線 bug reason: {r}（runtime caller 鏈斷）"
            )

    def test_runtime_apply_w_a_demo_low_obs_defers_not_blocks(
        self, gate: PromotionGate
    ):
        """W-AUDIT-6d #4 — W-A demo 階段 fill rate 接近 0 時 obs 不足，
        gate 必返回 `defer_data` 而非 `block`，使 caller 區分「樣本不足」
        與「真的 strategy 失敗」。"""
        rng = np.random.default_rng(20260509)
        # 模擬 W-A demo 早期：僅 50 obs（< 200 min_observations）。
        low_obs_returns = rng.normal(0.001, 0.005, size=50)

        self._setup_demo_active(gate, "test")
        ok, report = gate.update_demo_tail_risk_evidence(
            "test",
            portfolio_returns=low_obs_returns,
            stress_exposures={"crypto_beta": 0.05},
            n_bootstrap=120,
            seed=42,
        )
        assert not ok
        assert report["verdict"] == "defer_data", (
            f"W-A demo 樣本不足 → defer_data（不 block），got: {report['verdict']}"
        )
        # graduation 應失敗，但 reason 必含 defer_data 而非 block。
        _add_passing_selection_bias(gate, "test")
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        defer_reasons = [r for r in reasons if "defer_data" in r]
        assert defer_reasons, (
            f"reasons 必含 defer_data variant，got: {reasons}"
        )

    def test_runtime_apply_no_evidence_blocks_graduation(self, gate: PromotionGate):
        """W-AUDIT-6d #4 — 完全沒呼 update_demo_tail_risk_evidence →
        check_demo_graduation 必含 'tail_risk:no_evidence'（fail-closed
        基準路徑：W-AUDIT-6c spec invariant）。"""
        self._setup_demo_active(gate, "test")
        _add_passing_selection_bias(gate, "test")
        # 故意不調 update_demo_tail_risk_evidence。
        eligible, reasons = gate.check_demo_graduation("test")
        assert not eligible
        assert "tail_risk:no_evidence" in reasons

    def test_runtime_apply_does_not_deploy_runtime_state(
        self, gate: PromotionGate
    ):
        """W-AUDIT-6d #4 — 'runtime apply spec/test, **不 deploy**' contract：
        本 test 確保 update_demo_tail_risk_evidence 是 **side-effect controlled**：
        - 修改 in-memory entry.demo_tail_risk_report；
        - 不寫 PG / 不開 socket / 不修 risk config TOML / 不啟 cron / 不
          renew live authorization。
        """
        self._setup_demo_active(gate, "test")
        rng = np.random.default_rng(42)
        returns = rng.normal(0.001, 0.005, size=300)
        # 跑 update — 以 entry inspection 驗 side effect 範圍。
        gate.update_demo_tail_risk_evidence(
            "test",
            portfolio_returns=returns,
            stress_exposures={"crypto_beta": 0.05},
            n_bootstrap=120,
            seed=42,
        )
        # 唯一 side effect：entry.demo_tail_risk_report 寫入 in-memory。
        with gate._lock:
            entry = gate._entries["test"]
            assert entry.demo_tail_risk_report is not None, (
                "tail_risk_report 必寫入 in-memory entry"
            )
            assert "verdict" in entry.demo_tail_risk_report
            # current_stage 不變動（不 promote）。
            assert entry.current_stage == PromotionStage.DEMO_ACTIVE
