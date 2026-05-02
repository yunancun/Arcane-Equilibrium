"""
LG-5 ``review_live_candidate`` unit tests for R1-R6 + R-meta.
LG-5 ``review_live_candidate`` R1-R6 + R-meta 單元測試。

Spec source / 規格來源：
    docs/CCAgentWorkSpace/PA/workspace/reports/
        2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md §3

These tests focus on the **pure rule evaluators** (``evaluate_r1`` ..
``evaluate_r_meta``) — they are stateless, do no DB IO, and let us verify
each formula independently from the orchestration layer.

Integration tests (full ``review_live_candidate(hub, candidate_id)`` with
mocked DB) are deferred to LG-5-IMPL-4 (E4) per RFC §6 ownership split.
"""

from __future__ import annotations

import math

import pytest

from app.governance_hub_live_candidate_review import (
    R1_MAKER_FILL_FLOOR,
    R1_MAKER_FILL_RATIO,
    R2_PASS_THRESHOLD_BPS,
    R3_PSR_THRESHOLD,
    R4_TRIGGER_PENDING_COUNT,
    R5_PASS_CEIL,
    R5_WARN_CEIL,
    R6_DAILY_NEG_SNAPSHOTS_REQUIRED,
    R6_MAKER_FILL_CATASTROPHIC_FLOOR,
    R_META_RATIO_FLOOR,
    ReviewVerdict,
    _compute_bailey_ldp_sr_0,
    _compute_psr,
    _select_lease_ttl_ms,
    evaluate_r1,
    evaluate_r2,
    evaluate_r3,
    evaluate_r4,
    evaluate_r5,
    evaluate_r6,
    evaluate_r_meta,
)


# ═══════════════════════════════════════════════════════════════════════════════
# R1 — cost regime check
# ═══════════════════════════════════════════════════════════════════════════════

class TestR1:
    """R1 live cost regime / R1 live 成本制度檢查。"""

    def test_pass_above_ratio_and_floor(self) -> None:
        """Live maker (0.30) ≥ demo (0.30) × 0.85 = 0.255 AND ≥ 0.15 → pass."""
        ok, msg = evaluate_r1(live_maker_fill_rate=0.30, demo_maker_fill_rate=0.30)
        assert ok is True
        assert "pass" in msg

    def test_fail_below_floor(self) -> None:
        """Live maker 0.10 < floor 0.15 → fail (even if demo also low)."""
        ok, msg = evaluate_r1(live_maker_fill_rate=0.10, demo_maker_fill_rate=0.10)
        assert ok is False
        assert "below floor" in msg

    def test_fail_below_ratio(self) -> None:
        """Live maker 0.20 < demo 0.30 × 0.85 = 0.255 → fail."""
        ok, msg = evaluate_r1(live_maker_fill_rate=0.20, demo_maker_fill_rate=0.30)
        assert ok is False
        assert "<" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# R2 — distribution-shift haircut
# ═══════════════════════════════════════════════════════════════════════════════

class TestR2:
    """R2 distribution-shift haircut / R2 分佈漂移 haircut。"""

    def test_pass_high_demo_expected(self) -> None:
        """Demo 10bps × clamped ratio 1.0 - small slip diff → > 1.5bps pass."""
        ok, msg, ratio, ratio_clamped, adjusted = evaluate_r2(
            expected_net_bps_demo=10.0,
            live_maker_fill_rate=0.30,
            demo_maker_fill_rate=0.30,
            live_avg_fee_bps=5.0,
            demo_avg_fee_bps=5.0,
            live_avg_slippage_bps=1.0,
            demo_avg_slippage_bps=0.5,
        )
        assert ok is True
        assert adjusted >= R2_PASS_THRESHOLD_BPS
        assert ratio == pytest.approx(1.0, rel=0.01)
        assert ratio_clamped == pytest.approx(1.0, rel=0.01)

    def test_fail_low_demo_expected(self) -> None:
        """Demo 1.0bps × 1.0 - slip → below 1.5bps fail."""
        ok, msg, _r, _rc, adjusted = evaluate_r2(
            expected_net_bps_demo=1.0,
            live_maker_fill_rate=0.30,
            demo_maker_fill_rate=0.30,
            live_avg_fee_bps=5.0,
            demo_avg_fee_bps=5.0,
            live_avg_slippage_bps=0.0,
            demo_avg_slippage_bps=0.0,
        )
        assert ok is False
        assert adjusted < R2_PASS_THRESHOLD_BPS

    def test_clamp_low_protects_candidate(self) -> None:
        """Live maker 0.05 / demo 0.30 → raw ratio ~0.17, clamped to 0.3."""
        ok, msg, ratio, ratio_clamped, adjusted = evaluate_r2(
            expected_net_bps_demo=10.0,
            live_maker_fill_rate=0.05,
            demo_maker_fill_rate=0.30,
            live_avg_fee_bps=5.0,
            demo_avg_fee_bps=5.0,
            live_avg_slippage_bps=0.0,
            demo_avg_slippage_bps=0.0,
        )
        assert ratio < 0.3
        assert ratio_clamped == pytest.approx(0.3, rel=0.01)
        # 10 × 0.3 - 0 = 3.0 bps ≥ 1.5 → pass
        assert ok is True

    def test_demo_baseline_zero_fail(self) -> None:
        """demo_maker_fill_rate=0 → cannot compute → fail."""
        ok, msg, ratio, ratio_clamped, adjusted = evaluate_r2(
            expected_net_bps_demo=10.0,
            live_maker_fill_rate=0.30,
            demo_maker_fill_rate=0.0,
            live_avg_fee_bps=5.0,
            demo_avg_fee_bps=5.0,
            live_avg_slippage_bps=0.0,
            demo_avg_slippage_bps=0.0,
        )
        assert ok is False
        assert "baseline" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# R3 — PSR(0) check
# ═══════════════════════════════════════════════════════════════════════════════

class TestR3:
    """R3 PSR(0) check / R3 PSR(0) 檢查。"""

    def test_defer_low_n(self) -> None:
        """n=50 < 100 floor → defer."""
        status, msg, psr, n, _sk, _ku = evaluate_r3(
            n_strategy_fills=50,
            distribution_stats=(1.0, 0.5, 0.0, 3.0, 50),
        )
        assert status == "defer"
        assert "100" in msg

    def test_pass_strong_distribution(self) -> None:
        """Mean 1.0bps / std 0.1 with n=200 → PSR ≫ 0.95 pass."""
        status, msg, psr, n, _sk, _ku = evaluate_r3(
            n_strategy_fills=200,
            distribution_stats=(1.0, 0.1, 0.0, 3.0, 200),
        )
        assert status == "pass"
        assert psr is not None and psr >= R3_PSR_THRESHOLD

    def test_fail_negative_mean(self) -> None:
        """Mean -1.0bps / std 0.5 → PSR ~ 0 fail."""
        status, msg, psr, _n, _sk, _ku = evaluate_r3(
            n_strategy_fills=200,
            distribution_stats=(-1.0, 0.5, 0.0, 3.0, 200),
        )
        assert status == "fail"
        assert psr is not None and psr < R3_PSR_THRESHOLD


# ═══════════════════════════════════════════════════════════════════════════════
# R4 — DSR / multiple-testing deflation
# ═══════════════════════════════════════════════════════════════════════════════

class TestR4:
    """R4 DSR deflation / R4 DSR deflation。"""

    def test_skip_below_trigger(self) -> None:
        """K=3 < 5 → skip (informational)."""
        status, msg, deflated, sr_0, v_pending = evaluate_r4(
            expected_net_bps_live_adjusted=5.0,
            pending_pool=[{"id": i, "payload": {}} for i in range(3)],
            expected_net_bps_demo=10.0,
        )
        assert status == "skip"
        assert deflated == 5.0  # passthrough
        assert sr_0 is None

    def test_pass_with_low_variance_pool(self) -> None:
        """K=10 with very low cross-candidate variance → small SR_0 → pass."""
        # All pool members have similar avg_realized_net_bps → near-zero V.
        # 所有 pool 成員 avg_realized_net_bps 接近 → 近零 V_pending。
        pool = [
            {"id": i, "payload": {"demo_cost_baseline": {"avg_realized_net_bps_7d": 5.0 + (i * 0.01)}}}
            for i in range(10)
        ]
        status, msg, deflated, sr_0, v_pending = evaluate_r4(
            expected_net_bps_live_adjusted=10.0,
            pending_pool=pool,
            expected_net_bps_demo=10.0,
        )
        assert status == "pass"
        assert deflated >= R2_PASS_THRESHOLD_BPS
        assert v_pending is not None and v_pending < 0.01

    def test_fail_with_high_variance_pool(self) -> None:
        """K=10 with high variance → large SR_0 → fail."""
        pool = [
            {"id": i, "payload": {"demo_cost_baseline": {"avg_realized_net_bps_7d": v}}}
            for i, v in enumerate([-50, -40, -30, 0, 10, 30, 50, 70, 100, 200])
        ]
        status, msg, deflated, sr_0, v_pending = evaluate_r4(
            expected_net_bps_live_adjusted=2.0,
            pending_pool=pool,
            expected_net_bps_demo=2.5,
        )
        assert status == "fail"
        assert sr_0 is not None and sr_0 > 1.0  # high variance → meaningful deflation


# ═══════════════════════════════════════════════════════════════════════════════
# R5 — cost_edge_ratio gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestR5:
    """R5 cost_edge_ratio gate / R5 cost_edge_ratio 門控。"""

    def test_pass_low_ratio(self) -> None:
        """Live cost cheap relative to demo gross → pass."""
        status, msg, ratio = evaluate_r5(
            expected_net_bps_demo=20.0,
            demo_avg_fee_bps=5.0,
            demo_avg_slippage_bps=2.0,
            live_avg_fee_bps=3.0,
            live_avg_slippage_bps=1.0,
        )
        # demo_gross = 20 + 7 = 27; live_cost = 4; ratio = 0.148 < 0.5
        assert status == "pass"
        assert ratio < R5_PASS_CEIL

    def test_warn_mid_band(self) -> None:
        """Live cost in 0.5-0.8 band → warn (shorter lease downstream)."""
        status, msg, ratio = evaluate_r5(
            expected_net_bps_demo=10.0,
            demo_avg_fee_bps=2.0,
            demo_avg_slippage_bps=1.0,
            live_avg_fee_bps=7.0,
            live_avg_slippage_bps=2.0,
        )
        # demo_gross = 10 + 3 = 13; live_cost = 9; ratio = 0.69
        assert status == "warn"
        assert R5_PASS_CEIL <= ratio < R5_WARN_CEIL

    def test_fail_high_ratio(self) -> None:
        """Live cost ≥ 80% of demo gross → fail (CLAUDE.md §二 #13)."""
        status, msg, ratio = evaluate_r5(
            expected_net_bps_demo=5.0,
            demo_avg_fee_bps=2.0,
            demo_avg_slippage_bps=1.0,
            live_avg_fee_bps=8.0,
            live_avg_slippage_bps=2.0,
        )
        # demo_gross = 5 + 3 = 8; live_cost = 10; ratio = 1.25 ≥ 0.8
        assert status == "fail"
        assert ratio >= R5_WARN_CEIL


# ═══════════════════════════════════════════════════════════════════════════════
# R6 — hard veto
# ═══════════════════════════════════════════════════════════════════════════════

class TestR6:
    """R6 hard veto / R6 硬否決。"""

    def test_veto_seven_negative_days(self) -> None:
        """All 7 daily snapshots negative → veto."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 7},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is True
        assert "negative" in msg

    def test_veto_catastrophic_maker(self) -> None:
        """Live maker 0.05 < 0.10 catastrophic floor → veto."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 0},
            live_maker_fill_rate=0.05,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is True
        assert "catastrophic" in msg

    def test_veto_pipeline_gap(self) -> None:
        """[22] FAIL → veto."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 0},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=True,
            auth_effective=True,
        )
        assert vetoed is True

    def test_veto_auth_not_effective(self) -> None:
        """auth_effective=False → veto."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 0},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=False,
        )
        assert vetoed is True

    def test_pass_healthy_regime(self) -> None:
        """No veto trigger → pass."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is False


# ═══════════════════════════════════════════════════════════════════════════════
# Round 2 HIGH-1: R6 data-gap fail-closed
# Round 2 HIGH-1：R6 data-gap fail-closed
# ═══════════════════════════════════════════════════════════════════════════════

class TestR6DataGapRound2:
    """R6 data gap (n_snap < 7) must NOT silently pass evaluate_r6 — strict
    equality requires n_snap == 7 AND n_neg == 7 to veto. Caller is then
    responsible for the data-gap pre-check defer.
    R6 data gap (n_snap < 7) 不可在 evaluate_r6 silent pass — 嚴格相等
    要求 n_snap == 7 AND n_neg == 7 才 veto。Caller 負責 data-gap pre-check defer。
    """

    def test_data_gap_n_snap_5_does_not_veto(self) -> None:
        """n_snap=5 (data gap) → evaluate_r6 returns vetoed=False
        (caller must defer separately)."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 5, "n_negative": 5},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is False, "n_snap=5 must not trigger negative-day veto"

    def test_data_gap_n_snap_6_n_neg_6_does_not_veto(self) -> None:
        """n_snap=6 even with all negative still does not veto under strict eq."""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 6, "n_negative": 6},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is False, "strict equality: n_snap=6 must not veto"

    def test_data_gap_n_snap_8_n_neg_8_does_not_veto(self) -> None:
        """n_snap=8 (more than 7) does not match strict-equality veto either —
        data-collection bug should also surface as data-gap pre-check, not as
        accidental veto.
        n_snap=8 也不滿足嚴格相等 — 資料收集 bug 應由 pre-check 處理。"""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 8, "n_negative": 8},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is False

    def test_seven_days_all_negative_still_vetoes(self) -> None:
        """Sanity: real 7/7 negative still triggers hard veto under strict eq.
        合理性：真實 7/7 負日仍 veto。"""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 7},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is True
        assert "negative" in msg

    def test_seven_days_mixed_does_not_veto_negative_path(self) -> None:
        """7/3 mixed → negative-snapshot path does not fire (other R6 conditions
        unchanged); R1-R5 then evaluate downstream.
        7/3 混合 → 負日 veto 不觸發；R1-R5 在下游評估。"""
        vetoed, msg = evaluate_r6(
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            live_maker_fill_rate=0.30,
            pipeline_silent_gap_fail=False,
            auth_effective=True,
        )
        assert vetoed is False


# ═══════════════════════════════════════════════════════════════════════════════
# Round 2 HIGH-1 + HIGH-2: review_live_candidate caller integration tests
# Round 2 HIGH-1 + HIGH-2：review_live_candidate caller 整合測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestReviewLiveCandidateRound2:
    """Caller-level tests for HIGH-1 data-gap pre-check + HIGH-2 atomic commit.
    Caller 層測試：HIGH-1 data-gap pre-check + HIGH-2 atomic commit 原子性。

    These tests exercise ``review_live_candidate`` end-to-end with module-level
    function patching (DB helpers + audit emit + atomic commit + hub).
    這些測試以 module-level function patch 走完 review_live_candidate
    （DB helper + audit emit + atomic commit + hub）。
    """

    def _approve_path_payload(self) -> dict:
        """Build a payload that passes R1-R5 + R-meta + R6 (so verdict reaches
        approve path)."""
        return {
            "schema_version": "live_candidate_eval_v1",
            "demo_cost_baseline": {
                "maker_fill_rate_7d": 0.30,
                "avg_realized_fee_bps_7d": 1.0,
                "avg_realized_slippage_bps_7d": 0.5,
            },
            "demo_realized_window": {"n_strategy_fills": 200},
            "demo_attribution_chain_ratio_by_strategy": {
                "grid_trading": 0.80,
            },
        }

    def _patch_module(self, monkeypatch, *, daily_snapshots, atomic_ok=True,
                      payload=None, candidate_extra=None):
        """Apply common patches and return helpers."""
        from app import governance_hub_live_candidate_review as mod

        candidate_row = {
            "id": 99,
            "recommendation_id": 7,
            "target_name": "grid_trading",
            "payload": payload if payload is not None else self._approve_path_payload(),
        }
        if candidate_extra:
            candidate_row.update(candidate_extra)

        emitted: list[tuple[str, int, object]] = []
        atomic_calls: list[tuple[int, object, str]] = []

        monkeypatch.setattr(mod, "_fetch_candidate_row", lambda cid: candidate_row)
        monkeypatch.setattr(mod, "_fetch_source_recommendation",
                            lambda rec_id: {"strategy_name": "grid_trading",
                                            "expected_net_bps": 5.0})
        monkeypatch.setattr(mod, "_fetch_live_cost_regime", lambda: {
            "maker_fill_rate": 0.30,  # ratio 1.0 of demo 0.30
            "avg_fee_bps": 1.0,
            "avg_slippage_bps": 0.5,
        })
        monkeypatch.setattr(mod, "_fetch_r6_daily_snapshots", lambda: daily_snapshots)
        monkeypatch.setattr(mod, "_fetch_pending_candidate_pool", lambda: [])
        # PSR distribution stats tuple (mean, std, skew, kurt, n) — strong SR + large n → PSR > 0.95
        # PSR 分布 stats tuple — 強 SR + 大 n → PSR > 0.95
        monkeypatch.setattr(mod, "_fetch_strategy_return_distribution",
                            lambda strategy, window_days=7: (2.0, 1.0, 0.0, 3.0, 200))

        def fake_emit(event_type, candidate_id, verdict):
            emitted.append((event_type, candidate_id, verdict))
            return True
        monkeypatch.setattr(mod, "_emit_audit_row", fake_emit)

        def fake_atomic(candidate_id, verdict, lease_id):
            atomic_calls.append((candidate_id, verdict, lease_id))
            return atomic_ok
        monkeypatch.setattr(mod, "_emit_approve_audit_and_persist_lease_atomic",
                            fake_atomic)

        return mod, emitted, atomic_calls

    class _FakeHub:
        """Minimal hub with deterministic acquire_lease + is_authorized."""

        def __init__(self, lease_id="lease-xyz", authorized=True):
            self._lease_id = lease_id
            self._authorized = authorized
            self.acquire_calls: list[tuple] = []

        def acquire_lease(self, intent_id, scope, ttl_seconds):
            self.acquire_calls.append((intent_id, scope, ttl_seconds))
            return self._lease_id

        def is_authorized(self):
            return self._authorized

    def test_high1_data_gap_n_snap_5_defers(self, monkeypatch) -> None:
        """HIGH-1: caller pre-check sees n_snap < 7 → defer_data_insufficient
        with rule_failures=['R6_data_gap'] (no R1-R5 evaluation).
        HIGH-1：caller pre-check 看到 n_snap < 7 → defer_data_insufficient
        + rule_failures=['R6_data_gap']（不評 R1-R5）。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 5, "n_negative": 5},
        )
        hub = self._FakeHub()
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "defer"
        assert verdict.reason == "defer_data_insufficient"
        assert "R6_data_gap" in verdict.rule_failures
        # No lease acquired — pre-check returns before approve path
        # 沒有 acquire lease — pre-check 在 approve path 前就返回
        assert hub.acquire_calls == []
        assert atomic_calls == []
        # One audit row emitted (the defer)
        # 一筆 audit row（defer）
        assert len(emitted) == 1
        assert emitted[0][2].decision == "defer"

    def test_high1_data_gap_seven_days_mixed_continues_to_approve(self, monkeypatch) -> None:
        """7 days mixed (3 negative) → R6 pre-check passes → R1-R5 evaluate →
        approve path reached → atomic commit invoked.
        7 天 3 負 → R6 pre-check 通過 → R1-R5 評估 → 抵達 approve path → atomic commit。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            atomic_ok=True,
        )
        hub = self._FakeHub(lease_id="lease-approve-1")
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "approve", \
            f"expected approve, got {verdict.decision}/{verdict.reason}"
        assert verdict.reason == "approve_within_envelope"
        # Lease acquired exactly once + atomic commit invoked exactly once
        # acquire lease 與 atomic commit 各一次
        assert len(hub.acquire_calls) == 1
        assert len(atomic_calls) == 1
        atomic_cand, atomic_verdict, atomic_lease = atomic_calls[0]
        assert atomic_cand == 99
        assert atomic_lease == "lease-approve-1"
        assert atomic_verdict.decision == "approve"

    def test_high1_data_gap_seven_days_all_negative_rejects_hard_veto(self, monkeypatch) -> None:
        """7/7 negative → R6 hard veto → reject_hard_veto (NOT defer).
        7/7 負 → R6 hard veto → reject_hard_veto（不是 defer）。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 7},
        )
        hub = self._FakeHub()
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "reject"
        assert verdict.reason == "reject_hard_veto"
        assert "R6" in verdict.rule_failures
        assert hub.acquire_calls == []  # never reach approve path
        assert atomic_calls == []

    def test_high2_atomic_commit_failure_downgrades_to_defer(self, monkeypatch) -> None:
        """HIGH-2: acquire_lease succeeds + atomic commit fails (mock returns
        False) → verdict downgrades to defer_audit_write_failed.
        HIGH-2：acquire_lease 成功 + atomic commit 失敗 → verdict 降為
        defer_audit_write_failed。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            atomic_ok=False,  # ← simulate atomic commit failure
        )
        hub = self._FakeHub(lease_id="lease-orphan-1")
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "defer"
        assert verdict.reason == "defer_audit_write_failed"
        # atomic commit was attempted (and failed)
        # atomic commit 嘗試過（並失敗）
        assert len(atomic_calls) == 1
        assert atomic_calls[0][2] == "lease-orphan-1"
        # Best-effort secondary audit row emitted
        # Best-effort 二次 audit
        assert any(e[2].reason == "defer_audit_write_failed" for e in emitted)
        # Orphaned lease info surfaced in payload_snapshot
        # 失孤 lease 在 payload_snapshot 標記
        assert verdict.payload_snapshot.get("orphaned_lease_id") == "lease-orphan-1"

    def test_high2_lease_acquire_failure_defers_no_persist(self, monkeypatch) -> None:
        """acquire_lease returns None → defer_lease_acquisition_failed +
        atomic commit NEVER invoked (RFC §5.2 line 430 path).
        acquire_lease 回 None → defer_lease_acquisition_failed +
        atomic commit 不被呼叫（RFC §5.2 line 430 路徑）。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
        )
        hub = self._FakeHub(lease_id=None)
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "defer"
        assert verdict.reason == "defer_lease_acquisition_failed"
        assert atomic_calls == [], "atomic commit must not run when lease=None"


# ═══════════════════════════════════════════════════════════════════════════════
# R-meta — per-strategy attribution
# ═══════════════════════════════════════════════════════════════════════════════

class TestRMeta:
    """R-meta per-strategy attribution / R-meta per-strategy attribution。"""

    def test_pass_above_floor(self) -> None:
        status, msg, ratio = evaluate_r_meta(
            candidate_strategy="grid_trading",
            attribution_dict={"grid_trading": 0.65, "ma_crossover": 0.30},
        )
        assert status == "pass"
        assert ratio == 0.65

    def test_fail_below_floor(self) -> None:
        status, msg, ratio = evaluate_r_meta(
            candidate_strategy="ma_crossover",
            attribution_dict={"grid_trading": 0.65, "ma_crossover": 0.30},
        )
        assert status == "fail"
        assert ratio == 0.30

    def test_unknown_strategy(self) -> None:
        """Strategy not in dict → unknown (defer downstream)."""
        status, msg, ratio = evaluate_r_meta(
            candidate_strategy="new_strategy",
            attribution_dict={"grid_trading": 0.65},
        )
        assert status == "unknown"
        assert ratio is None


# ═══════════════════════════════════════════════════════════════════════════════
# R-meta sample threshold (LG5-W3-FUP-2 Fix 2 IMPL-2-consumer, PA Q3)
# R-meta sample 門檻（LG5-W3-FUP-2 Fix 2 IMPL-2-consumer，PA Q3）
# ═══════════════════════════════════════════════════════════════════════════════

class TestRMetaSampleThreshold:
    """LG5-W3-FUP-2 Fix 2 IMPL-2-consumer: low-sample defer + backward compat。

    Caller-level（``review_live_candidate``）整合測試，覆蓋 PA Q3 的
    ``defer_attribution_chain_low_sample`` 新分支與 27 pending candidates
    backward compat（payload 缺 ``demo_attribution_sample_count_by_strategy``
    時，evaluator 略過 sample check，沿用 7d ratio path）。
    """

    # 借用 Round 2 _patch_module + _FakeHub fixture pattern。
    _approve_path_payload = TestReviewLiveCandidateRound2._approve_path_payload
    _patch_module = TestReviewLiveCandidateRound2._patch_module
    _FakeHub = TestReviewLiveCandidateRound2._FakeHub

    def _payload_with_sample(self, ratio: float, sample_n: int) -> dict:
        """Build R-meta payload with explicit sample count for grid_trading.
        建構含 grid_trading sample count 的 R-meta payload。"""
        return {
            "schema_version": "live_candidate_eval_v1",
            "demo_cost_baseline": {
                "maker_fill_rate_7d": 0.30,
                "avg_realized_fee_bps_7d": 1.0,
                "avg_realized_slippage_bps_7d": 0.5,
            },
            "demo_realized_window": {"n_strategy_fills": 200},
            "demo_attribution_chain_ratio_by_strategy": {"grid_trading": ratio},
            "demo_attribution_sample_count_by_strategy": {"grid_trading": sample_n},
            "demo_attribution_window_days": 3,
        }

    def test_r_meta_defer_when_sample_below_threshold(self, monkeypatch) -> None:
        """sample=5 + ratio=0.80 → defer ``defer_attribution_chain_low_sample``
        (NOT reject_attribution_chain_too_broken — sample-fail vs ratio-fail 區分)。
        sample=5 + ratio=0.80 → defer reason 為 low_sample，不是 too_broken。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            payload=self._payload_with_sample(ratio=0.80, sample_n=5),
        )
        hub = self._FakeHub()
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "defer"
        assert verdict.reason == "defer_attribution_chain_low_sample"
        assert "R-meta" in verdict.rule_failures
        assert verdict.attribution_sample_count == 5
        # NEVER touched approve path：sample 不足 → defer 在 R6 後立即返回。
        assert hub.acquire_calls == []
        assert atomic_calls == []
        # payload_snapshot 標記 threshold + msg 含 "n=5 < 10"
        snap = verdict.payload_snapshot
        assert snap["min_sample_threshold"] == 10
        assert "n=5" in snap["r_meta_sample_msg"]

    def test_r_meta_pass_when_sample_above_threshold(self, monkeypatch) -> None:
        """sample=20 + ratio=0.80 → R-meta pass → 進 approve path 抵達 atomic commit。
        sample=20 + ratio=0.80 → R-meta pass → approve path → atomic commit invoked。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            payload=self._payload_with_sample(ratio=0.80, sample_n=20),
            atomic_ok=True,
        )
        hub = self._FakeHub(lease_id="lease-rmeta-pass")
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "approve", \
            f"expected approve, got {verdict.decision}/{verdict.reason}"
        assert verdict.reason == "approve_within_envelope"
        assert len(atomic_calls) == 1

    def test_r_meta_reject_when_ratio_low_with_sufficient_sample(self, monkeypatch) -> None:
        """sample=20 + ratio=0.20 → defer ``reject_attribution_chain_too_broken``
        （既有 RFC §3 R-meta 行為：樣本足夠但 ratio < 0.50 floor → reject_*）。
        sample=20 + ratio=0.20 → reject_attribution_chain_too_broken（既有行為不變）。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            payload=self._payload_with_sample(ratio=0.20, sample_n=20),
        )
        hub = self._FakeHub()
        verdict = review_live_candidate(hub, candidate_id=99)

        assert verdict.decision == "defer"
        assert verdict.reason == "reject_attribution_chain_too_broken"
        assert "R-meta" in verdict.rule_failures
        # sample_n 仍透過 audit，retro 校準可區分「sample 足但 ratio 差」
        assert verdict.attribution_sample_count == 20
        assert hub.acquire_calls == []

    def test_r_meta_backward_compat_no_sample_dict(self, monkeypatch) -> None:
        """payload 無 ``demo_attribution_sample_count_by_strategy`` → 視為 v1
        pre-Fix 2 candidate → 略過 sample check → 走 ratio path（preserves 27 pending）。
        Pre-Fix 2 payload 缺 sample dict → skip sample check → ratio=0.80 → pass。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        # Old-format payload（無 demo_attribution_sample_count_by_strategy）
        old_payload = {
            "schema_version": "live_candidate_eval_v1",
            "demo_cost_baseline": {
                "maker_fill_rate_7d": 0.30,
                "avg_realized_fee_bps_7d": 1.0,
                "avg_realized_slippage_bps_7d": 0.5,
            },
            "demo_realized_window": {"n_strategy_fills": 200},
            "demo_attribution_chain_ratio_by_strategy": {"grid_trading": 0.80},
            # ← demo_attribution_sample_count_by_strategy 不存在
        }
        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            payload=old_payload,
            atomic_ok=True,
        )
        hub = self._FakeHub(lease_id="lease-bc-1")
        verdict = review_live_candidate(hub, candidate_id=99)

        # ratio path 走完 → R-meta pass → approve path 抵達
        assert verdict.decision == "approve"
        assert verdict.reason == "approve_within_envelope"
        assert verdict.attribution_sample_count is None  # 沒 sample dict → 一律 None

    def test_r_meta_backward_compat_strategy_missing_in_sample_dict(self, monkeypatch) -> None:
        """sample dict 存在但不含 candidate strategy → skip sample check → ratio path。
        sample dict 有但 grid_trading 不在 dict 內 → skip sample check → 走 ratio。"""
        from app.governance_hub_live_candidate_review import review_live_candidate

        mixed_payload = {
            "schema_version": "live_candidate_eval_v1",
            "demo_cost_baseline": {
                "maker_fill_rate_7d": 0.30,
                "avg_realized_fee_bps_7d": 1.0,
                "avg_realized_slippage_bps_7d": 0.5,
            },
            "demo_realized_window": {"n_strategy_fills": 200},
            "demo_attribution_chain_ratio_by_strategy": {"grid_trading": 0.80},
            # grid_trading 在 ratio dict 但不在 sample dict
            "demo_attribution_sample_count_by_strategy": {"ma_crossover": 50},
        }
        mod, emitted, atomic_calls = self._patch_module(
            monkeypatch,
            daily_snapshots={"n_snapshots": 7, "n_negative": 3},
            payload=mixed_payload,
            atomic_ok=True,
        )
        hub = self._FakeHub(lease_id="lease-bc-2")
        verdict = review_live_candidate(hub, candidate_id=99)

        # grid_trading 缺 sample dict 鍵 → skip → ratio=0.80 ≥ floor → pass → approve
        assert verdict.decision == "approve"
        assert verdict.reason == "approve_within_envelope"
        assert verdict.attribution_sample_count is None


# ═══════════════════════════════════════════════════════════════════════════════
# Helper math: PSR + Bailey-LdP SR_0
# ═══════════════════════════════════════════════════════════════════════════════

class TestMathHelpers:
    """Pure math helper sanity / 純數學輔助合理性檢查。"""

    def test_psr_zero_sr_at_threshold(self) -> None:
        """SR=0 normal returns → PSR(0) = 0.5."""
        psr = _compute_psr(sr_observed=0.0, n=200, skew=0.0, kurt=3.0)
        assert psr == pytest.approx(0.5, abs=0.01)

    def test_psr_high_sr_pass(self) -> None:
        """Strong SR + large n → PSR ≈ 1."""
        psr = _compute_psr(sr_observed=2.0, n=200, skew=0.0, kurt=3.0)
        assert psr > 0.99

    def test_bailey_ldp_sr_0_increases_with_K(self) -> None:
        """K=20 should impose larger deflation than K=5 at same V."""
        sr_0_low = _compute_bailey_ldp_sr_0(K=5, v_pending_net_bps=4.0)
        sr_0_high = _compute_bailey_ldp_sr_0(K=20, v_pending_net_bps=4.0)
        assert sr_0_high > sr_0_low > 0

    def test_bailey_ldp_sr_0_zero_when_K_lt_2(self) -> None:
        """K<2 corner returns 0 (avoid Φ⁻¹ blow up)."""
        assert _compute_bailey_ldp_sr_0(K=1, v_pending_net_bps=4.0) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# Lease TTL band selection
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaseTTL:
    """Lease TTL band selection / Lease TTL 帶狀選擇。"""

    def test_default_6h(self) -> None:
        ttl = _select_lease_ttl_ms(r5_status="pass", r3_status="pass",
                                    psr_value=0.99, learning_period=False)
        assert ttl == 6 * 3600 * 1000

    def test_r5_warn_shortens_to_1h(self) -> None:
        ttl = _select_lease_ttl_ms(r5_status="warn", r3_status="pass",
                                    psr_value=0.99, learning_period=False)
        assert ttl == 1 * 3600 * 1000

    def test_r3_borderline_shortens_to_2h(self) -> None:
        ttl = _select_lease_ttl_ms(r5_status="pass", r3_status="pass",
                                    psr_value=0.96, learning_period=False)
        assert ttl == 2 * 3600 * 1000

    def test_learning_period_caps_to_2h(self) -> None:
        ttl = _select_lease_ttl_ms(r5_status="pass", r3_status="pass",
                                    psr_value=0.99, learning_period=True)
        assert ttl == 2 * 3600 * 1000

    def test_r5_warn_wins_over_learning_period(self) -> None:
        """r5 warn (1h) is shorter than learning cap (2h) → 1h applies."""
        ttl = _select_lease_ttl_ms(r5_status="warn", r3_status="pass",
                                    psr_value=0.99, learning_period=True)
        assert ttl == 1 * 3600 * 1000


# ═══════════════════════════════════════════════════════════════════════════════
# ReviewVerdict dataclass surface
# ═══════════════════════════════════════════════════════════════════════════════

class TestReviewVerdict:
    """ReviewVerdict frozen dataclass invariants."""

    def test_frozen(self) -> None:
        v = ReviewVerdict(
            decision="approve", reason="approve_within_envelope",
            rule_failures=[],
            expected_net_bps_demo=5.0,
            expected_net_bps_live_adjusted=2.0,
            expected_net_bps_deflated=1.5,
            cost_regime_ratio=0.8, cost_regime_ratio_clamped=0.8,
            psr_value=0.96, psr_n_samples=120,
            psr_skew=0.0, psr_kurt=3.0,
            sr_0_deflation=0.5, v_pending_net_bps=2.0,
            lease_ttl_ms=2 * 3600 * 1000,
        )
        with pytest.raises(Exception):
            v.decision = "reject"  # type: ignore[misc]
