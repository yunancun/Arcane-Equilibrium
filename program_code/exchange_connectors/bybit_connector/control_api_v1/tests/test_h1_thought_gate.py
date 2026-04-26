"""
G3-08 Phase 2 — H1 ThoughtGate unit tests.

Coverage matrix (10 cases):
  1. ``check()`` baseline pass / fail logic preserved (no business-logic change).
  2. Local stats counters increment on each branch (budget / complexity /
     cooldown skip / pass).
  3. ``get_h1_snapshot()`` returns canonical schema with all keys.
  4. ``get_h1_snapshot()`` ``cooldown_dict_size`` reflects current map size.
  5. ``get_h1_snapshot()`` ``budget_remaining_pct`` derived from cost_tracker.
  6. env=1 + invalidate_async wired → ``invalidate_async`` called per branch.
  7. env=0 → ``invalidate_async`` is module-level no-op (no thread spawn).
  8. cost_tracker absent → snapshot ``budget_remaining_pct`` is None.
  9. cost_tracker raise → snapshot ``budget_remaining_pct`` is None (fail-open).
 10. Snapshot is a copy (mutating it does not affect internal state).
"""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.h1_thought_gate import H1ThoughtGate  # noqa: E402


# ── Helpers / 輔助 ──


def _make_intel(symbols=None, relevance_score=0.8, urgency=None):
    """Construct a minimal IntelObject-like SimpleNamespace for testing."""
    return SimpleNamespace(
        symbols=symbols if symbols is not None else ["BTCUSDT"],
        relevance_score=relevance_score,
        metadata={"urgency": urgency} if urgency else {},
    )


class _AllowingTracker:
    """cost_tracker stub that always allows + reports remaining budget."""

    def __init__(self, allowed=True, remaining=1.5, hard_cap=2.0):
        self._allowed = allowed
        self._remaining = remaining
        # Mimic real cost_tracker._config.daily_hard_cap_usd
        self._config = SimpleNamespace(daily_hard_cap_usd=hard_cap)

    def check_daily_budget(self):
        return (self._allowed, self._remaining)


class _RaisingTracker:
    """cost_tracker stub that raises in check_daily_budget (fail-open)."""

    _config = SimpleNamespace(daily_hard_cap_usd=2.0)

    def check_daily_budget(self):
        raise RuntimeError("tracker boom")


# ── 1. Baseline pass/fail logic preserved ──


class TestCheckBaselineLogic(unittest.TestCase):
    """1. ``check()`` returns True/False per existing rules."""

    def test_high_relevance_returns_true(self):
        gate = H1ThoughtGate()
        intel = _make_intel(relevance_score=0.9)
        stats: dict = {}
        self.assertTrue(gate.check(intel, stats))

    def test_low_complexity_returns_false(self):
        gate = H1ThoughtGate()
        # relevance=0.1, no boost → complexity 0.1 < 0.3 threshold.
        intel = _make_intel(relevance_score=0.1)
        stats: dict = {}
        self.assertFalse(gate.check(intel, stats))

    def test_budget_skip_returns_false(self):
        gate = H1ThoughtGate(cost_tracker=_AllowingTracker(allowed=False))
        intel = _make_intel(relevance_score=0.9)
        stats: dict = {}
        self.assertFalse(gate.check(intel, stats))

    def test_cooldown_skip_returns_false(self):
        gate = H1ThoughtGate()
        intel = _make_intel(relevance_score=0.9)
        # First call passes, second within window → cooldown trip.
        gate.check(intel, {})
        stats: dict = {}
        self.assertFalse(gate.check(intel, stats))


# ── 2. Local stats counters increment on each branch ──


class TestLocalStatsCounters(unittest.TestCase):
    """2. ``_h1_local_stats`` counters track decisions per branch."""

    def test_total_decisions_increments(self):
        gate = H1ThoughtGate()
        for _ in range(5):
            gate.check(_make_intel(relevance_score=0.1), {})
        self.assertEqual(gate._h1_local_stats["total_decisions"], 5)

    def test_budget_skip_counter(self):
        gate = H1ThoughtGate(cost_tracker=_AllowingTracker(allowed=False))
        gate.check(_make_intel(relevance_score=0.9), {})
        self.assertEqual(gate._h1_local_stats["budget_skip"], 1)
        self.assertEqual(gate._h1_local_stats["complexity_skip"], 0)
        self.assertEqual(gate._h1_local_stats["cooldown_skip"], 0)

    def test_complexity_skip_counter(self):
        gate = H1ThoughtGate()
        gate.check(_make_intel(relevance_score=0.1), {})
        self.assertEqual(gate._h1_local_stats["complexity_skip"], 1)
        self.assertEqual(gate._h1_local_stats["budget_skip"], 0)

    def test_cooldown_skip_counter(self):
        gate = H1ThoughtGate()
        gate.check(_make_intel(relevance_score=0.9), {})
        gate.check(_make_intel(relevance_score=0.9), {})
        self.assertEqual(gate._h1_local_stats["cooldown_skip"], 1)

    def test_ai_calls_allowed_counter(self):
        gate = H1ThoughtGate()
        gate.check(_make_intel(symbols=["AAA"], relevance_score=0.9), {})
        gate.check(_make_intel(symbols=["BBB"], relevance_score=0.9), {})
        self.assertEqual(gate._h1_local_stats["ai_calls_allowed"], 2)


# ── 3-5. get_h1_snapshot schema ──


class TestSnapshotSchema(unittest.TestCase):
    """3-5. ``get_h1_snapshot()`` returns canonical schema."""

    def test_snapshot_has_all_keys(self):
        gate = H1ThoughtGate()
        snap = gate.get_h1_snapshot()
        for key in (
            "total_decisions",
            "ai_calls_allowed",
            "budget_skip",
            "complexity_skip",
            "cooldown_skip",
            "cooldown_dict_size",
            "budget_remaining_pct",
        ):
            self.assertIn(key, snap, f"missing snapshot key: {key}")

    def test_snapshot_initial_values_zero(self):
        gate = H1ThoughtGate()
        snap = gate.get_h1_snapshot()
        for key in (
            "total_decisions",
            "ai_calls_allowed",
            "budget_skip",
            "complexity_skip",
            "cooldown_skip",
        ):
            self.assertEqual(snap[key], 0)
        self.assertEqual(snap["cooldown_dict_size"], 0)

    def test_snapshot_reflects_cooldown_size(self):
        gate = H1ThoughtGate()
        for sym in ("AAA", "BBB", "CCC"):
            gate.check(_make_intel(symbols=[sym], relevance_score=0.9), {})
        snap = gate.get_h1_snapshot()
        self.assertEqual(snap["cooldown_dict_size"], 3)

    def test_snapshot_budget_remaining_pct_with_tracker(self):
        # remaining=1.0, hard_cap=2.0 → 50%.
        gate = H1ThoughtGate(cost_tracker=_AllowingTracker(remaining=1.0, hard_cap=2.0))
        snap = gate.get_h1_snapshot()
        self.assertIsNotNone(snap["budget_remaining_pct"])
        self.assertAlmostEqual(snap["budget_remaining_pct"], 50.0, places=2)

    def test_snapshot_budget_remaining_pct_clamped(self):
        # remaining > hard_cap → clamped to 100.
        gate = H1ThoughtGate(cost_tracker=_AllowingTracker(remaining=5.0, hard_cap=2.0))
        snap = gate.get_h1_snapshot()
        self.assertEqual(snap["budget_remaining_pct"], 100.0)


# ── 6. env=1 + invalidate_async fired per branch ──


class TestInvalidateAsyncCalls(unittest.TestCase):
    """6. ``invalidate_async`` invoked per H1 branch when env=1.

    We patch the module-level ``_invalidate_h_state_async`` in
    ``app.h1_thought_gate`` so we can count calls without actually spawning
    threads or hitting the IPC layer.
    """

    def test_invalidate_called_for_each_branch(self):
        with patch("app.h1_thought_gate._invalidate_h_state_async") as mock_inv:
            gate = H1ThoughtGate(cost_tracker=_AllowingTracker(allowed=False))
            # budget_skip
            gate.check(_make_intel(symbols=["AAA"], relevance_score=0.9), {})
            # complexity_skip
            gate2 = H1ThoughtGate()
            gate2.check(_make_intel(symbols=["BBB"], relevance_score=0.1), {})
            # ai_call_allowed (different gate to skip cooldown)
            gate3 = H1ThoughtGate()
            gate3.check(_make_intel(symbols=["CCC"], relevance_score=0.9), {})
            # cooldown_skip (re-entry on same symbol)
            gate3.check(_make_intel(symbols=["CCC"], relevance_score=0.9), {})

            # Expect 4 invalidate calls — one per branch reached.
            self.assertEqual(mock_inv.call_count, 4)
            reasons = [c.args[0] for c in mock_inv.call_args_list]
            self.assertIn("h1.budget_skip", reasons)
            self.assertIn("h1.complexity_skip", reasons)
            self.assertIn("h1.ai_call_allowed", reasons)
            self.assertIn("h1.cooldown_skip", reasons)


# ── 7. env=0 → invalidate_async stays module-level no-op ──


class TestEnvOffNoOpCall(unittest.TestCase):
    """7. env=0 ⇒ invalidate_async still callable but is itself a no-op
    inside ``h_state_invalidator`` (no singleton constructed). H1 still
    invokes it (cheap), but no thread is spawned.

    We assert by inspecting ``h_state_invalidator.get_invalidator()`` —
    when env=0 it stays None, meaning ``invalidate_async`` early-returns.
    """

    def test_env_off_no_singleton_constructed(self):
        prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        try:
            from app import h_state_invalidator as inv_mod

            inv_mod._reset_for_tests()
            # init no-op when env disabled.
            inv_mod.init_h_state_invalidator()
            self.assertIsNone(inv_mod.get_invalidator())
            # Call invalidate via H1 path — must not raise, must not spawn.
            gate = H1ThoughtGate()
            gate.check(_make_intel(relevance_score=0.9), {})
            # Singleton still None; no observable side-effects beyond H1
            # local stats increment.
            self.assertIsNone(inv_mod.get_invalidator())
            self.assertEqual(gate._h1_local_stats["ai_calls_allowed"], 1)
        finally:
            if prev_env is not None:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 8-9. Tracker error / absence handling ──


class TestTrackerErrorHandling(unittest.TestCase):
    """8-9. cost_tracker None or raise ⇒ budget_remaining_pct None."""

    def test_no_tracker_yields_none(self):
        gate = H1ThoughtGate(cost_tracker=None)
        snap = gate.get_h1_snapshot()
        self.assertIsNone(snap["budget_remaining_pct"])

    def test_tracker_raise_yields_none(self):
        gate = H1ThoughtGate(cost_tracker=_RaisingTracker())
        snap = gate.get_h1_snapshot()
        self.assertIsNone(snap["budget_remaining_pct"])

    def test_tracker_returns_non_tuple_yields_none(self):
        class _BadTracker:
            _config = SimpleNamespace(daily_hard_cap_usd=2.0)

            def check_daily_budget(self):
                return "garbage"

        gate = H1ThoughtGate(cost_tracker=_BadTracker())
        snap = gate.get_h1_snapshot()
        self.assertIsNone(snap["budget_remaining_pct"])

    def test_tracker_zero_hard_cap_yields_none(self):
        # Hard cap == 0 → division-by-zero guard returns None.
        gate = H1ThoughtGate(cost_tracker=_AllowingTracker(remaining=1.0, hard_cap=0.0))
        snap = gate.get_h1_snapshot()
        self.assertIsNone(snap["budget_remaining_pct"])


# ── 10. Snapshot is a copy ──


class TestSnapshotIsolation(unittest.TestCase):
    """10. Mutating the returned snapshot does not affect internal state."""

    def test_snapshot_mutation_isolated(self):
        gate = H1ThoughtGate()
        gate.check(_make_intel(symbols=["X"], relevance_score=0.9), {})
        snap = gate.get_h1_snapshot()
        snap["total_decisions"] = 9999
        snap["cooldown_dict_size"] = 9999
        # Refetch — counters intact.
        snap2 = gate.get_h1_snapshot()
        self.assertEqual(snap2["total_decisions"], 1)
        self.assertEqual(snap2["cooldown_dict_size"], 1)


if __name__ == "__main__":
    unittest.main()
