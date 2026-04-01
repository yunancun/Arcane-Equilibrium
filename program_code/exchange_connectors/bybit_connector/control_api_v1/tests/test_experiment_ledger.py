"""
Tests for ExperimentLedger — Phase 3 Batch 3A
==============================================
Coverage categories:
  A. TestHypothesisDataclass (8 tests)
  B. TestRecordObservation (8 tests)
  C. TestTruthRegistryInjection (6 tests)
  D. TestExpireStale (4 tests)
  E. TestQueryAndStats (4 tests)
  F. TestThreadSafety (2 tests)

Total: 32 tests (>= 30 required)
"""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
