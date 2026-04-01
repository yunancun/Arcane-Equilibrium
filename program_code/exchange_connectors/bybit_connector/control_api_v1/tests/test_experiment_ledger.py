"""
Tests for ExperimentLedger — Phase 3 Batch 3A + APR01-P1-2 Persistence
=======================================================================
Coverage categories:
  A. TestHypothesisDataclass (8 tests)
  B. TestRecordObservation (8 tests)
  C. TestTruthRegistryInjection (6 tests)
  D. TestExpireStale (4 tests)
  E. TestQueryAndStats (4 tests)
  F. TestThreadSafety (2 tests)
  G. TestAutoSeedFromClaims (3 tests)
  H. TestSnapshotPersistence (10 tests) — APR01-P1-2

Total: 45 tests
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# ── import under test ────────────────────────────────────────────────────────
import sys
import os

# Allow running tests from project root or from this file's directory
_HERE = os.path.dirname(__file__)
_APP_DIR = os.path.join(_HERE, "..")
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from app.experiment_ledger import (
    ExperimentLedger,
    Hypothesis,
    HypothesisStatus,
)


# ─────────────────────────────────────────────────────────────────────────────
# A. TestHypothesisDataclass
# ─────────────────────────────────────────────────────────────────────────────

class TestHypothesisDataclass(unittest.TestCase):
    """Tests for the Hypothesis dataclass and ExperimentLedger.propose_hypothesis().
    测试 Hypothesis 数据类和 ExperimentLedger.propose_hypothesis()。
    """

    def setUp(self) -> None:
        self.ledger = ExperimentLedger()

    # A1: propose_hypothesis returns a non-empty ID
    def test_propose_returns_valid_id(self) -> None:
        """propose_hypothesis() must return a non-empty string ID."""
        hid = self.ledger.propose_hypothesis(
            description="MA crossover works in trending regime",
            strategy_name="ma_crossover",
        )
        self.assertIsInstance(hid, str)
        self.assertTrue(len(hid) > 0)

    # A2: initial status is PENDING
    def test_initial_status_is_pending(self) -> None:
        """Newly proposed hypotheses must start in PENDING status."""
        hid = self.ledger.propose_hypothesis(
            description="Test hypothesis",
            strategy_name="rsi",
        )
        h = self.ledger.get_hypothesis(hid)
        self.assertIsNotNone(h)
        self.assertEqual(h.status, HypothesisStatus.PENDING)

    # A3: custom TTL is applied
    def test_custom_ttl_applied(self) -> None:
        """Custom ttl_days should set expires_at_ms accordingly."""
        now_ms = int(time.time() * 1000)
        hid = self.ledger.propose_hypothesis(
            description="Short TTL test",
            strategy_name="grid",
            ttl_days=3,
        )
        h = self.ledger.get_hypothesis(hid)
        expected_ttl_ms = 3 * 86_400_000
        # Allow 1 second tolerance for test execution time
        self.assertAlmostEqual(
            h.expires_at_ms - now_ms,
            expected_ttl_ms,
            delta=1000,
        )

    # A4: to_dict contains all required fields
    def test_to_dict_contains_required_fields(self) -> None:
        """to_dict() must include all required fields."""
        hid = self.ledger.propose_hypothesis(
            description="Dict field test",
            strategy_name="trend_follow",
        )
        h = self.ledger.get_hypothesis(hid)
        d = h.to_dict()
        required_keys = [
            "hypothesis_id", "status", "description", "strategy_name",
            "supporting_count", "refuting_count", "confidence",
        ]
        for key in required_keys:
            self.assertIn(key, d, f"Missing required field: {key}")

    # A5: confidence is 0.0 with no observations
    def test_confidence_zero_with_no_observations(self) -> None:
        """confidence() must return 0.0 when no observations have been recorded."""
        hid = self.ledger.propose_hypothesis(
            description="No observations yet",
            strategy_name="ma_crossover",
        )
        h = self.ledger.get_hypothesis(hid)
        self.assertEqual(h.confidence(), 0.0)

    # A6: confidence is near 1.0 when all observations are supporting
    def test_confidence_near_one_with_all_supporting(self) -> None:
        """confidence() must approach 1.0 when all observations are supporting."""
        # Manually set supporting/refuting to test confidence formula
        hid = self.ledger.propose_hypothesis(
            description="All wins",
            strategy_name="ma_crossover",
            min_observations=5,
        )
        h = self.ledger.get_hypothesis(hid)
        h.supporting_count = 10
        h.refuting_count = 0
        self.assertAlmostEqual(h.confidence(), 1.0, places=5)

    # A7: is_expired returns False within TTL
    def test_is_expired_false_within_ttl(self) -> None:
        """is_expired() must return False when TTL has not yet elapsed."""
        hid = self.ledger.propose_hypothesis(
            description="Within TTL",
            strategy_name="rsi",
            ttl_days=7,
        )
        h = self.ledger.get_hypothesis(hid)
        # now_ms is well before expires_at_ms
        self.assertFalse(h.is_expired(int(time.time() * 1000)))

    # A8: is_expired returns True after TTL
    def test_is_expired_true_after_ttl(self) -> None:
        """is_expired() must return True when TTL has elapsed."""
        hid = self.ledger.propose_hypothesis(
            description="Past TTL",
            strategy_name="rsi",
            ttl_days=7,
        )
        h = self.ledger.get_hypothesis(hid)
        # Simulate a future timestamp well past TTL
        far_future_ms = h.expires_at_ms + 1000
        self.assertTrue(h.is_expired(far_future_ms))


# ─────────────────────────────────────────────────────────────────────────────
# B. TestRecordObservation
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordObservation(unittest.TestCase):
    """Tests for ExperimentLedger.record_observation().
    测试 ExperimentLedger.record_observation()。
    """

    def _make_ledger_with_hypothesis(
        self,
        min_observations: int = 20,
        strategy_name: str = "ma_crossover",
    ) -> tuple[ExperimentLedger, str]:
        ledger = ExperimentLedger()
        hid = ledger.propose_hypothesis(
            description="Test observation recording",
            strategy_name=strategy_name,
            min_observations=min_observations,
        )
        return ledger, hid

    # B1: supporting_count increments correctly
    def test_supporting_count_increments(self) -> None:
        """record_observation('win') must increment supporting_count."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=100)
        ledger.record_observation(hid, "win")
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.supporting_count, 1)
        self.assertEqual(h.refuting_count, 0)

    # B2: refuting_count increments correctly
    def test_refuting_count_increments(self) -> None:
        """record_observation('loss') must increment refuting_count."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=100)
        ledger.record_observation(hid, "loss")
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.refuting_count, 1)
        self.assertEqual(h.supporting_count, 0)

    # B3: unknown outcome does not crash and status unchanged
    def test_unknown_outcome_no_crash(self) -> None:
        """Unknown outcome strings must not raise exceptions and must leave status unchanged."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=100)
        # First observation to move to RUNNING
        ledger.record_observation(hid, "win")
        status_before = ledger.get_hypothesis(hid).status
        # Now send unknown outcome
        status_after = ledger.record_observation(hid, "unknown_outcome_xyz")
        self.assertEqual(status_before, status_after)

    # B4: 65% supporting + >= min_obs → CONFIRMED
    def test_65_percent_supporting_confirmed(self) -> None:
        """65% supporting observations with min_observations met must produce CONFIRMED."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=20)
        # 13 wins, 7 losses = 65% win rate = exactly at threshold
        for _ in range(13):
            ledger.record_observation(hid, "win")
        for _ in range(7):
            ledger.record_observation(hid, "loss")
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.CONFIRMED)

    # B5: 65% refuting + >= min_obs → REFUTED
    def test_65_percent_refuting_refuted(self) -> None:
        """65% refuting observations with min_observations met must produce REFUTED."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=20)
        # 7 wins, 13 losses = 65% loss rate
        for _ in range(7):
            ledger.record_observation(hid, "win")
        for _ in range(13):
            ledger.record_observation(hid, "loss")
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.REFUTED)

    # B6: insufficient observations do not trigger conclusion
    def test_insufficient_observations_no_conclusion(self) -> None:
        """Observations below min_observations must not trigger conclusion."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=20)
        # 10 wins = all supporting but < 20 observations
        for _ in range(10):
            ledger.record_observation(hid, "win")
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.RUNNING)

    # B7: already concluded hypothesis ignores new observations (no crash, returns status)
    def test_concluded_hypothesis_ignores_new_observations(self) -> None:
        """New observations on concluded hypotheses must be silently ignored."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=20)
        # Conclude the hypothesis
        for _ in range(13):
            ledger.record_observation(hid, "win")
        for _ in range(7):
            ledger.record_observation(hid, "loss")
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.CONFIRMED)

        # Now try to add more observations — must be silently ignored
        supporting_before = h.supporting_count
        status = ledger.record_observation(hid, "win")
        self.assertEqual(status, HypothesisStatus.CONFIRMED)
        # supporting_count must not have changed
        self.assertEqual(h.supporting_count, supporting_before)

    # B8: first observation transitions PENDING → RUNNING
    def test_first_observation_transitions_to_running(self) -> None:
        """First observation must transition hypothesis from PENDING to RUNNING."""
        ledger, hid = self._make_ledger_with_hypothesis(min_observations=100)
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.PENDING)
        ledger.record_observation(hid, "win")
        self.assertEqual(h.status, HypothesisStatus.RUNNING)


# ─────────────────────────────────────────────────────────────────────────────
# C. TestTruthRegistryInjection
# ─────────────────────────────────────────────────────────────────────────────

class TestTruthRegistryInjection(unittest.TestCase):
    """Tests for TruthSourceRegistry injection on hypothesis conclusion.
    测试假设结案时的 TruthSourceRegistry 注入行为。
    """

    def _make_ledger_with_mock_registry(self) -> tuple[ExperimentLedger, MagicMock, str]:
        registry = MagicMock()
        registry.register_claim.return_value = "claim_abc123"
        ledger = ExperimentLedger(truth_registry=registry, default_ttl_days=7)
        hid = ledger.propose_hypothesis(
            description="Test registry injection",
            strategy_name="rsi_divergence",
            min_observations=20,
        )
        return ledger, registry, hid

    def _confirm_hypothesis(self, ledger: ExperimentLedger, hid: str) -> None:
        """Helper: send 13 wins + 7 losses to confirm a min_obs=20 hypothesis."""
        for _ in range(13):
            ledger.record_observation(hid, "win")
        for _ in range(7):
            ledger.record_observation(hid, "loss")

    def _refute_hypothesis(self, ledger: ExperimentLedger, hid: str) -> None:
        """Helper: send 7 wins + 13 losses to refute a min_obs=20 hypothesis."""
        for _ in range(7):
            ledger.record_observation(hid, "win")
        for _ in range(13):
            ledger.record_observation(hid, "loss")

    # C1: CONFIRMED hypothesis calls registry.register_claim()
    def test_confirmed_calls_register_claim(self) -> None:
        """CONFIRMED hypothesis must call truth_registry.register_claim() once."""
        ledger, registry, hid = self._make_ledger_with_mock_registry()
        self._confirm_hypothesis(ledger, hid)
        registry.register_claim.assert_called_once()

    # C2: REFUTED hypothesis does NOT call registry.register_claim()
    def test_refuted_does_not_call_register_claim(self) -> None:
        """REFUTED hypothesis must NOT call truth_registry.register_claim()."""
        ledger, registry, hid = self._make_ledger_with_mock_registry()
        self._refute_hypothesis(ledger, hid)
        registry.register_claim.assert_not_called()

    # C3: registry=None does not crash on CONFIRMED
    def test_none_registry_no_crash_on_confirmed(self) -> None:
        """ExperimentLedger with registry=None must not crash when hypothesis is CONFIRMED."""
        ledger = ExperimentLedger(truth_registry=None)
        hid = ledger.propose_hypothesis(
            description="No registry test",
            strategy_name="grid",
            min_observations=20,
        )
        # Should not raise any exception
        self._confirm_hypothesis(ledger, hid)
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.CONFIRMED)

    # C4: registry.register_claim() raising exception does not crash (fail-open)
    def test_registry_exception_fail_open(self) -> None:
        """registry.register_claim() raising an exception must not propagate (fail-open)."""
        registry = MagicMock()
        registry.register_claim.side_effect = RuntimeError("Registry unavailable")
        ledger = ExperimentLedger(truth_registry=registry)
        hid = ledger.propose_hypothesis(
            description="Exception test",
            strategy_name="ma_crossover",
            min_observations=20,
        )
        # Must not raise — fail-open design
        self._confirm_hypothesis(ledger, hid)
        h = ledger.get_hypothesis(hid)
        # Hypothesis is still CONFIRMED despite registry failure
        self.assertEqual(h.status, HypothesisStatus.CONFIRMED)

    # C5: claim_id is set on hypothesis after successful injection
    def test_claim_id_set_after_successful_injection(self) -> None:
        """hypothesis.claim_id must be set after successful TruthSourceRegistry injection."""
        ledger, registry, hid = self._make_ledger_with_mock_registry()
        self._confirm_hypothesis(ledger, hid)
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.claim_id, "claim_abc123")

    # C6: injected evidence_source format is "statistical_N={n}"
    def test_injection_evidence_source_format(self) -> None:
        """Injected evidence_source must follow format 'statistical_N={total_observations}'."""
        ledger, registry, hid = self._make_ledger_with_mock_registry()
        self._confirm_hypothesis(ledger, hid)
        # Total observations = 13 wins + 7 losses = 20
        call_kwargs = registry.register_claim.call_args[1]
        self.assertEqual(call_kwargs["evidence_source"], "statistical_N=20")


# ─────────────────────────────────────────────────────────────────────────────
# D. TestExpireStale
# ─────────────────────────────────────────────────────────────────────────────

class TestExpireStale(unittest.TestCase):
    """Tests for ExperimentLedger.expire_stale_hypotheses().
    测试 ExperimentLedger.expire_stale_hypotheses()。
    """

    def _make_expired_hypothesis(
        self,
        ledger: ExperimentLedger,
        label: str = "Expired",
    ) -> str:
        """Create a hypothesis and manually set expires_at_ms to the past."""
        hid = ledger.propose_hypothesis(
            description=f"{label} hypothesis",
            strategy_name="ma_crossover",
        )
        h = ledger.get_hypothesis(hid)
        # Set expiry to 1 second ago
        h.expires_at_ms = int(time.time() * 1000) - 1000
        return hid

    def _make_active_hypothesis(
        self,
        ledger: ExperimentLedger,
        label: str = "Active",
    ) -> str:
        """Create a hypothesis with a future TTL."""
        return ledger.propose_hypothesis(
            description=f"{label} hypothesis",
            strategy_name="rsi",
            ttl_days=7,
        )

    # D1: expire_stale_hypotheses returns correct count
    def test_expire_stale_returns_correct_count(self) -> None:
        """expire_stale_hypotheses() must return the number of newly expired hypotheses."""
        ledger = ExperimentLedger()
        self._make_expired_hypothesis(ledger, "Exp1")
        self._make_expired_hypothesis(ledger, "Exp2")
        self._make_active_hypothesis(ledger, "Active")
        count = ledger.expire_stale_hypotheses()
        self.assertEqual(count, 2)

    # D2: expired hypotheses have status EXPIRED
    def test_expired_hypotheses_have_expired_status(self) -> None:
        """Hypotheses past their TTL must have status EXPIRED after expire_stale_hypotheses()."""
        ledger = ExperimentLedger()
        hid = self._make_expired_hypothesis(ledger, "Stale")
        ledger.expire_stale_hypotheses()
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.EXPIRED)

    # D3: already-concluded hypotheses are not re-marked EXPIRED
    def test_concluded_not_re_marked_expired(self) -> None:
        """Already-concluded (CONFIRMED/REFUTED) hypotheses must not be re-marked EXPIRED."""
        ledger = ExperimentLedger()
        hid = ledger.propose_hypothesis(
            description="To be confirmed then expired",
            strategy_name="grid",
            min_observations=20,
        )
        # Confirm the hypothesis
        for _ in range(13):
            ledger.record_observation(hid, "win")
        for _ in range(7):
            ledger.record_observation(hid, "loss")
        # Now manually set expires_at_ms to the past
        h = ledger.get_hypothesis(hid)
        h.expires_at_ms = int(time.time() * 1000) - 1000
        # expire_stale_hypotheses must not overwrite CONFIRMED status
        ledger.expire_stale_hypotheses()
        self.assertEqual(h.status, HypothesisStatus.CONFIRMED)

    # D4: active hypotheses are unaffected
    def test_active_hypotheses_not_expired(self) -> None:
        """Hypotheses within their TTL must not be marked EXPIRED."""
        ledger = ExperimentLedger()
        hid = self._make_active_hypothesis(ledger, "Active")
        ledger.expire_stale_hypotheses()
        h = ledger.get_hypothesis(hid)
        self.assertEqual(h.status, HypothesisStatus.PENDING)


# ─────────────────────────────────────────────────────────────────────────────
# E. TestQueryAndStats
# ─────────────────────────────────────────────────────────────────────────────

class TestQueryAndStats(unittest.TestCase):
    """Tests for get_all_hypotheses(), get_hypothesis(), and get_stats().
    测试 get_all_hypotheses()、get_hypothesis() 和 get_stats()。
    """

    def setUp(self) -> None:
        self.ledger = ExperimentLedger()

    # E1: get_all_hypotheses() with no filter returns all
    def test_get_all_hypotheses_no_filter_returns_all(self) -> None:
        """get_all_hypotheses() without filter must return all hypotheses."""
        self.ledger.propose_hypothesis(description="H1", strategy_name="rsi")
        self.ledger.propose_hypothesis(description="H2", strategy_name="ma_crossover")
        self.ledger.propose_hypothesis(description="H3", strategy_name="grid")
        all_hyp = self.ledger.get_all_hypotheses()
        self.assertEqual(len(all_hyp), 3)

    # E2: get_all_hypotheses(status=CONFIRMED) filters correctly
    def test_get_all_hypotheses_status_filter(self) -> None:
        """get_all_hypotheses(status=CONFIRMED) must return only CONFIRMED hypotheses."""
        hid1 = self.ledger.propose_hypothesis(
            description="To confirm", strategy_name="ma_crossover", min_observations=20
        )
        self.ledger.propose_hypothesis(description="Pending", strategy_name="rsi")

        # Confirm hid1
        for _ in range(13):
            self.ledger.record_observation(hid1, "win")
        for _ in range(7):
            self.ledger.record_observation(hid1, "loss")

        confirmed = self.ledger.get_all_hypotheses(status=HypothesisStatus.CONFIRMED)
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].hypothesis_id, hid1)

    # E3: get_hypothesis with unknown ID returns None
    def test_get_hypothesis_unknown_id_returns_none(self) -> None:
        """get_hypothesis() with an unknown ID must return None."""
        result = self.ledger.get_hypothesis("nonexistent_id_xyz")
        self.assertIsNone(result)

    # E4: get_stats returns dict with required fields
    def test_get_stats_contains_required_fields(self) -> None:
        """get_stats() must return a dict containing all required status fields."""
        self.ledger.propose_hypothesis(description="Stats test", strategy_name="rsi")
        stats = self.ledger.get_stats()
        required_keys = ["total", "pending", "running", "confirmed", "refuted", "expired"]
        for key in required_keys:
            self.assertIn(key, stats, f"Missing required stats field: {key}")
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["pending"], 1)


# ─────────────────────────────────────────────────────────────────────────────
# F. TestThreadSafety
# ─────────────────────────────────────────────────────────────────────────────

class TestThreadSafety(unittest.TestCase):
    """Thread-safety tests for ExperimentLedger.
    ExperimentLedger 的线程安全测试。
    """

    # F1: 10 threads concurrently calling record_observation do not crash
    def test_concurrent_record_observation_no_crash(self) -> None:
        """10 threads concurrently recording observations must not cause exceptions."""
        ledger = ExperimentLedger()
        hid = ledger.propose_hypothesis(
            description="Concurrent observation test",
            strategy_name="ma_crossover",
            min_observations=1000,  # High enough to avoid conclusion mid-test
        )

        errors: list[Exception] = []

        def record_many() -> None:
            try:
                for _ in range(20):
                    ledger.record_observation(hid, "win")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=record_many) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Unexpected exceptions: {errors}")
        h = ledger.get_hypothesis(hid)
        # 10 threads × 20 observations = 200 supporting
        self.assertEqual(h.supporting_count, 200)

    # F2: concurrent propose calls do not produce duplicate IDs
    def test_concurrent_propose_no_duplicate_ids(self) -> None:
        """Concurrent propose_hypothesis() calls must produce unique IDs."""
        ledger = ExperimentLedger()
        ids: list[str] = []
        lock = threading.Lock()

        def propose_one() -> None:
            hid = ledger.propose_hypothesis(
                description="Concurrent propose",
                strategy_name="rsi",
            )
            with lock:
                ids.append(hid)

        threads = [threading.Thread(target=propose_one) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(ids), 20)
        self.assertEqual(len(set(ids)), 20, "Duplicate hypothesis IDs detected")


# ─────────────────────────────────────────────────────────────────────────────
# G. TestAutoSeedFromClaims
# ─────────────────────────────────────────────────────────────────────────────

class TestAutoSeedFromClaims(unittest.TestCase):
    """
    E1-Beta Batch 3B — Tests for ExperimentLedger.auto_seed_from_claims().
    驗收標準：
      G1. 高信心 claims 自動生成 PENDING 假設
      G2. 低信心 claims 被跳過，不生成假設
      G3. applies_to_strategy="all" 的 claims 被跳過（原則 10）
    """

    def _make_claim(
        self,
        pattern_text: str = "test pattern",
        confidence: float = 0.7,
        strategy: str = "ma_crossover",
        regime: str = "trending",
    ) -> MagicMock:
        """
        Create a mock PatternClaim object for testing.
        建立用於測試的 mock PatternClaim 對象。
        """
        claim = MagicMock()
        claim.pattern_text = pattern_text
        claim.confidence = confidence
        claim.applies_to_strategy = strategy
        claim.applies_to_regime = regime
        return claim

    # ── G1: 高信心 claims 自動生成假設 ──────────────────────────────────────
    def test_auto_seed_creates_hypotheses_for_high_confidence(self):
        """
        Claims with confidence >= min_confidence (default 0.5) should generate PENDING hypotheses.
        confidence >= min_confidence 的 claims 應生成 PENDING 假設。
        """
        ledger = ExperimentLedger()

        claims = [
            self._make_claim("ma_crossover trending signal", confidence=0.7, strategy="ma_crossover"),
            self._make_claim("grid ranging profit", confidence=0.65, strategy="grid"),
        ]

        count = ledger.auto_seed_from_claims(claims, min_confidence=0.5)

        # 應成功生成 2 個假設 / Should successfully propose 2 hypotheses
        self.assertEqual(count, 2, "Should propose one hypothesis per high-confidence claim")

        # 所有假設應為 PENDING 狀態 / All hypotheses should be PENDING
        all_hyps = ledger.get_all_hypotheses(status=HypothesisStatus.PENDING)
        self.assertEqual(len(all_hyps), 2, "All auto-seeded hypotheses should be PENDING")

        # 假設描述應含 "[auto-seed]" 前綴 / Descriptions should contain "[auto-seed]" prefix
        for h in all_hyps:
            self.assertTrue(
                h.description.startswith("[auto-seed]"),
                f"Description '{h.description}' should start with '[auto-seed]'",
            )
            # proposed_by 應為 "truth_registry_autoseed" / proposed_by should be autoseed
            self.assertEqual(h.proposed_by, "truth_registry_autoseed")

    # ── G2: 低信心 claims 被跳過 ──────────────────────────────────────────────
    def test_auto_seed_skips_low_confidence(self):
        """
        Claims with confidence < min_confidence should be skipped — no hypotheses created.
        confidence < min_confidence 的 claims 應被跳過，不生成假設。
        """
        ledger = ExperimentLedger()

        claims = [
            self._make_claim("weak signal A", confidence=0.3, strategy="grid"),
            self._make_claim("weak signal B", confidence=0.49, strategy="ma_crossover"),
        ]

        count = ledger.auto_seed_from_claims(claims, min_confidence=0.5)

        # 應生成 0 個假設（全部低信心）/ Should propose 0 hypotheses (all low-confidence)
        self.assertEqual(count, 0, "Low-confidence claims should be skipped entirely")

        # 帳本應為空 / Ledger should be empty
        stats = ledger.get_stats()
        self.assertEqual(stats["total"], 0, "No hypotheses should be in ledger")

    # ── G3: applies_to_strategy="all" 的 claims 被跳過（原則 10 認知誠實）────────
    def test_auto_seed_skips_strategy_all(self):
        """
        Claims with applies_to_strategy="all" should be skipped (Principle 10: Cognitive Honesty).
        applies_to_strategy="all" 的 claims 應被跳過（原則 10：認知誠實）。
        """
        ledger = ExperimentLedger()

        claims = [
            # 這個應被跳過 / This should be skipped
            self._make_claim("generic signal", confidence=0.8, strategy="all"),
            # 這個應被保留 / This should be kept
            self._make_claim("ma_crossover specific", confidence=0.8, strategy="ma_crossover"),
        ]

        count = ledger.auto_seed_from_claims(claims, min_confidence=0.5)

        # 只有 1 個假設應被生成（strategy="all" 的被跳過）
        # Only 1 hypothesis should be proposed (strategy="all" is skipped)
        self.assertEqual(count, 1, "Claims with strategy='all' should be skipped")

        # 驗證生成的假設不是 "all" 策略 / Verify proposed hypothesis is not "all" strategy
        all_hyps = ledger.get_all_hypotheses()
        self.assertEqual(len(all_hyps), 1)
        self.assertNotEqual(all_hyps[0].strategy_name, "all",
                            "Proposed hypothesis must not have strategy_name='all'")
        self.assertEqual(all_hyps[0].strategy_name, "ma_crossover")


# ─────────────────────────────────────────────────────────────────────────────
# H. TestSnapshotPersistence — APR01-P1-2
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotPersistence(unittest.TestCase):
    """Tests for ExperimentLedger save_snapshot() / load_snapshot() persistence.
    测试 ExperimentLedger 的 save_snapshot() / load_snapshot() 持久化功能。

    APR01-P1-2: Experiment state must survive service restarts.
    APR01-P1-2：实验状态必须在服务重启后保留。
    """

    def _make_ledger_with_data(self) -> ExperimentLedger:
        """Create a ledger with 2 hypotheses (one PENDING, one CONFIRMED) for testing.
        创建一个包含 2 条假设（一条 PENDING，一条 CONFIRMED）的账本用于测试。
        """
        ledger = ExperimentLedger()
        # Hypothesis 1: PENDING
        ledger.propose_hypothesis(
            description="MA crossover trending hypothesis",
            strategy_name="ma_crossover",
            regime="trending",
            hypothesis_id="h_pending_001",
            min_observations=20,
        )
        # Hypothesis 2: will be CONFIRMED (13 wins + 7 losses = 65% win)
        ledger.propose_hypothesis(
            description="RSI divergence works in ranging",
            strategy_name="rsi_divergence",
            regime="ranging",
            hypothesis_id="h_confirmed_002",
            min_observations=20,
        )
        for _ in range(13):
            ledger.record_observation("h_confirmed_002", "win")
        for _ in range(7):
            ledger.record_observation("h_confirmed_002", "loss")
        return ledger

    # H1: save_snapshot writes valid JSON to disk
    def test_save_snapshot_writes_json(self) -> None:
        """save_snapshot() must write a valid JSON file containing all hypotheses."""
        ledger = self._make_ledger_with_data()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            result = ledger.save_snapshot(path)
            self.assertTrue(result, "save_snapshot() must return True on success")
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.assertIsInstance(data, list)
            self.assertEqual(len(data), 2)
            ids = {entry["hypothesis_id"] for entry in data}
            self.assertIn("h_pending_001", ids)
            self.assertIn("h_confirmed_002", ids)
        finally:
            import os
            os.unlink(path)

    # H2: load_snapshot restores hypotheses correctly
    def test_load_snapshot_restores_hypotheses(self) -> None:
        """load_snapshot() must restore hypotheses with correct fields and status."""
        ledger = self._make_ledger_with_data()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ledger.save_snapshot(path)

            # Create a fresh ledger and load the snapshot
            # 创建一个空账本并加载快照
            ledger2 = ExperimentLedger()
            loaded = ledger2.load_snapshot(path)
            self.assertEqual(loaded, 2, "Should load 2 hypotheses from snapshot")

            # Verify PENDING hypothesis fields
            h1 = ledger2.get_hypothesis("h_pending_001")
            self.assertIsNotNone(h1)
            self.assertEqual(h1.status, HypothesisStatus.PENDING)
            self.assertEqual(h1.strategy_name, "ma_crossover")
            self.assertEqual(h1.regime, "trending")

            # Verify CONFIRMED hypothesis fields
            h2 = ledger2.get_hypothesis("h_confirmed_002")
            self.assertIsNotNone(h2)
            self.assertEqual(h2.status, HypothesisStatus.CONFIRMED)
            self.assertEqual(h2.supporting_count, 13)
            self.assertEqual(h2.refuting_count, 7)
        finally:
            import os
            os.unlink(path)

    # H3: load_snapshot with missing file returns 0 (fail-open)
    def test_load_snapshot_missing_file_returns_zero(self) -> None:
        """load_snapshot() with a nonexistent path must return 0 (fail-open)."""
        ledger = ExperimentLedger()
        result = ledger.load_snapshot("/tmp/nonexistent_snapshot_xyz_12345.json")
        self.assertEqual(result, 0)

    # H4: load_snapshot with corrupt JSON returns 0 (fail-open)
    def test_load_snapshot_corrupt_json_returns_zero(self) -> None:
        """load_snapshot() with corrupt JSON must return 0 (fail-open, start fresh)."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            f.write("{{{invalid json ,,, !!!}")
            path = f.name
        try:
            ledger = ExperimentLedger()
            result = ledger.load_snapshot(path)
            self.assertEqual(result, 0, "Corrupt JSON should return 0 (fail-open)")
        finally:
            import os
            os.unlink(path)

    # H5: load_snapshot with non-list root returns 0 (fail-open)
    def test_load_snapshot_non_list_root_returns_zero(self) -> None:
        """load_snapshot() with a JSON dict (not list) root must return 0."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"not": "a list"}, f)
            path = f.name
        try:
            ledger = ExperimentLedger()
            result = ledger.load_snapshot(path)
            self.assertEqual(result, 0, "Non-list root should return 0 (fail-open)")
        finally:
            import os
            os.unlink(path)

    # H6: load_snapshot skips malformed entries but loads valid ones
    def test_load_snapshot_skips_malformed_entries(self) -> None:
        """load_snapshot() must skip malformed entries and still load valid ones."""
        valid_entry = {
            "hypothesis_id": "h_valid",
            "description": "valid hypothesis",
            "strategy_name": "rsi",
            "regime": "all",
            "proposed_by": "system",
            "proposed_at_ms": int(time.time() * 1000),
            "expires_at_ms": int(time.time() * 1000) + 86_400_000,
            "status": "PENDING",
            "min_observations": 20,
            "supporting_count": 0,
            "refuting_count": 0,
            "claim_id": None,
            "concluded_at_ms": None,
            "notes": "",
        }
        malformed_entry = {"hypothesis_id": "h_bad"}  # missing required fields

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([malformed_entry, valid_entry], f)
            path = f.name
        try:
            ledger = ExperimentLedger()
            loaded = ledger.load_snapshot(path)
            self.assertEqual(loaded, 1, "Should load 1 valid entry, skip 1 malformed")
            h = ledger.get_hypothesis("h_valid")
            self.assertIsNotNone(h)
            self.assertIsNone(ledger.get_hypothesis("h_bad"))
        finally:
            import os
            os.unlink(path)

    # H7: load_snapshot does not overwrite existing in-memory hypotheses
    def test_load_snapshot_no_overwrite_existing(self) -> None:
        """load_snapshot() must skip hypothesis_ids that already exist in memory."""
        ledger = ExperimentLedger()
        ledger.propose_hypothesis(
            description="In-memory version",
            strategy_name="grid",
            hypothesis_id="h_existing",
        )

        snapshot_entry = {
            "hypothesis_id": "h_existing",
            "description": "Snapshot version (should be skipped)",
            "strategy_name": "rsi",
            "regime": "all",
            "proposed_by": "snapshot",
            "proposed_at_ms": int(time.time() * 1000),
            "expires_at_ms": int(time.time() * 1000) + 86_400_000,
            "status": "RUNNING",
            "min_observations": 20,
            "supporting_count": 5,
            "refuting_count": 3,
            "claim_id": None,
            "concluded_at_ms": None,
            "notes": "",
        }

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump([snapshot_entry], f)
            path = f.name
        try:
            loaded = ledger.load_snapshot(path)
            self.assertEqual(loaded, 0, "Should skip already-existing hypothesis_id")
            h = ledger.get_hypothesis("h_existing")
            # Original in-memory version must be preserved
            self.assertEqual(h.description, "In-memory version")
            self.assertEqual(h.strategy_name, "grid")
        finally:
            import os
            os.unlink(path)

    # H8: save_snapshot to invalid path returns False (fail-open)
    def test_save_snapshot_invalid_path_returns_false(self) -> None:
        """save_snapshot() to an unwritable path must return False (fail-open)."""
        ledger = ExperimentLedger()
        ledger.propose_hypothesis(description="Test", strategy_name="rsi")
        # /proc is not writable on Linux
        result = ledger.save_snapshot("/proc/nonexistent_dir/snapshot.json")
        self.assertFalse(result, "save_snapshot to invalid path should return False")

    # H9: round-trip preserves concluded_at_ms and claim_id
    def test_round_trip_preserves_concluded_fields(self) -> None:
        """save + load round-trip must preserve concluded_at_ms and claim_id."""
        registry = MagicMock()
        registry.register_claim.return_value = "claim_rt_001"
        ledger = ExperimentLedger(truth_registry=registry)
        ledger.propose_hypothesis(
            description="Round-trip test",
            strategy_name="ma_crossover",
            hypothesis_id="h_roundtrip",
            min_observations=20,
        )
        for _ in range(13):
            ledger.record_observation("h_roundtrip", "win")
        for _ in range(7):
            ledger.record_observation("h_roundtrip", "loss")
        h_orig = ledger.get_hypothesis("h_roundtrip")
        self.assertEqual(h_orig.status, HypothesisStatus.CONFIRMED)
        self.assertEqual(h_orig.claim_id, "claim_rt_001")
        self.assertIsNotNone(h_orig.concluded_at_ms)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            ledger.save_snapshot(path)
            ledger2 = ExperimentLedger()
            ledger2.load_snapshot(path)
            h_loaded = ledger2.get_hypothesis("h_roundtrip")
            self.assertEqual(h_loaded.claim_id, "claim_rt_001")
            self.assertEqual(h_loaded.concluded_at_ms, h_orig.concluded_at_ms)
        finally:
            import os
            os.unlink(path)

    # H10: _schedule_debounced_save does not crash (fail-open smoke test)
    def test_schedule_debounced_save_no_crash(self) -> None:
        """_schedule_debounced_save() must not raise exceptions (fail-open)."""
        ledger = ExperimentLedger()
        # Force last_save_ts far in the past so debounce doesn't skip
        ledger._last_save_ts = 0.0
        # Should not raise even though snapshot dir may not exist
        try:
            ledger._schedule_debounced_save()
        except Exception as exc:
            self.fail(f"_schedule_debounced_save() raised: {exc}")
        # Clean up timer
        if ledger._save_timer is not None:
            ledger._save_timer.cancel()


# ─────────────────────────────────────────────────────────────────────────────
# I. E4 Edge Cases: ExperimentLedger Boundary Conditions / 边界条件
# ─────────────────────────────────────────────────────────────────────────────

class TestExperimentLedgerEdgeCases(unittest.TestCase):
    """Edge case tests for ExperimentLedger.
    ExperimentLedger 边界条件测试。"""

    def setUp(self) -> None:
        self.ledger = ExperimentLedger()

    def test_observe_invalid_hypothesis_id_returns_pending(self):
        """record_observation with nonexistent ID should return PENDING (no crash).
        不存在的 ID 调用 record_observation 应返回 PENDING（不崩溃）。"""
        result = self.ledger.record_observation("nonexistent_id_12345", "supporting")
        assert result == HypothesisStatus.PENDING

    def test_observe_many_observations_does_not_crash(self):
        """Recording many observations should not crash (no hard limit on obs count).
        大量记录观测不应崩溃（观测数量无硬限制）。"""
        hid = self.ledger.propose_hypothesis(
            description="Test many observations",
            strategy_name="test_strategy",
        )
        for i in range(100):
            verdict = "supporting" if i % 2 == 0 else "refuting"
            self.ledger.record_observation(hid, verdict)
        hyp = self.ledger.get_hypothesis(hid)
        assert hyp is not None
        # supporting_count + refuting_count should total 100
        assert hyp.supporting_count + hyp.refuting_count == 100

    def test_concurrent_observe_from_multiple_threads(self):
        """Concurrent record_observation calls should not corrupt state.
        并发 record_observation 调用不应损坏状态。"""
        hid = self.ledger.propose_hypothesis(
            description="Thread safety test",
            strategy_name="concurrent_strategy",
        )
        errors = []

        def observe_n(n: int) -> None:
            try:
                for _ in range(50):
                    self.ledger.record_observation(hid, "supporting")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=observe_n, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Thread errors: {errors}"
        hyp = self.ledger.get_hypothesis(hid)
        assert hyp is not None
        # Hypothesis concludes at min_observations (default 20) so count may cap.
        # Key assertion: no corruption from concurrency — count >= 1 and status valid.
        assert hyp.supporting_count >= 1
        assert hyp.status in (HypothesisStatus.RUNNING, HypothesisStatus.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
