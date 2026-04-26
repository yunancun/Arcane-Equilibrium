"""
G3-08 Phase 2 — H3 ModelRouter unit tests.

Coverage matrix (12 cases):
  1. ``route()`` baseline tier dispatch preserved (l1_9b / l1_27b / l2 paths).
  2. ``route()`` budget-denied fallback path counts as l1_27b + budget_denied.
  3. Local routing stats counter increments per ``route()`` exit branch.
  4. ``route()`` with context-driven L1.5 / L2 escalation.
  5. ``check_l2_cache`` hit / expired / no-entry — local counters update.
  6. ``_store_l2_result`` increments ``l2_cache_stored``.
  7. ``get_h3_snapshot()`` returns canonical schema.
  8. ``get_h3_snapshot()`` initial values are zero / cache_size 0.
  9. env=1 + invalidate_async wired → ``invalidate_async`` called per branch.
 10. env=0 → ``invalidate_async`` stays module-level no-op.
 11. Snapshot is a copy (mutating it does not affect internal state).
 12. Cache size reflects ``_l2_result_cache`` real size.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.model_router import ModelRouter  # noqa: E402


# ── Helpers / 輔助 ──


def _make_intel(symbols=None):
    return SimpleNamespace(
        symbols=symbols if symbols is not None else ["BTCUSDT"],
        intel_id="test-intel-001",
    )


def _make_evaluation(has_edge=True, confidence=0.7):
    return SimpleNamespace(has_edge=has_edge, confidence=confidence)


# ── 1. Baseline tier dispatch ──


class TestRouteBaseline(unittest.TestCase):
    """1. ``route()`` tier dispatch preserved per existing complexity rules."""

    def test_low_complexity_routes_l1_9b(self):
        r = ModelRouter()
        self.assertEqual(r.route(0.3), "l1_9b")

    def test_moderate_complexity_routes_l1_27b(self):
        r = ModelRouter()
        self.assertEqual(r.route(0.6), "l1_27b")

    def test_high_complexity_no_context_routes_l2(self):
        r = ModelRouter()
        self.assertEqual(r.route(0.9), "l2")

    def test_high_complexity_with_no_upgrade_context_routes_l1_27b(self):
        r = ModelRouter()
        # Context with no L1.5 trigger conditions → fall back to l1_27b.
        ctx = {"confidence": 0.9, "amount_pct": 1.0}
        self.assertEqual(r.route(0.9, context=ctx), "l1_27b")


# ── 2. Budget-denied fallback ──


class TestRouteBudgetDenied(unittest.TestCase):
    """2. budget_checker returns False ⇒ fallback to l1_27b + counter."""

    def test_budget_denied_falls_back_l1_27b(self):
        r = ModelRouter()
        r.set_budget_checker(lambda tier: False)  # always deny
        # Trigger L1.5 escalation context.
        ctx = {"confidence": 0.4, "amount_pct": 6.0}
        result = r.route(0.9, context=ctx)
        self.assertEqual(result, "l1_27b")
        self.assertEqual(r._routing_stats["budget_denied_count"], 1)
        self.assertEqual(r._routing_stats["l1_27b_count"], 1)


# ── 3. Local routing stats per branch ──


class TestRoutingStats(unittest.TestCase):
    """3. ``_routing_stats`` counters increment per ``route()`` branch."""

    def test_total_routes_increments(self):
        r = ModelRouter()
        for _ in range(7):
            r.route(0.3)
        self.assertEqual(r._routing_stats["total_routes"], 7)

    def test_l1_9b_counter(self):
        r = ModelRouter()
        r.route(0.3)
        r.route(0.4)
        self.assertEqual(r._routing_stats["l1_9b_count"], 2)
        self.assertEqual(r._routing_stats["l1_27b_count"], 0)

    def test_l1_27b_counter(self):
        r = ModelRouter()
        r.route(0.5)
        r.route(0.7)
        self.assertEqual(r._routing_stats["l1_27b_count"], 2)

    def test_l2_counter_no_context(self):
        r = ModelRouter()
        r.route(0.9)  # high + no context → l2
        self.assertEqual(r._routing_stats["l2_count"], 1)

    def test_l1_5_counter_with_context(self):
        r = ModelRouter()
        ctx = {"confidence": 0.4, "amount_pct": 6.0}  # triggers L1.5
        result = r.route(0.9, context=ctx)
        self.assertEqual(result, "l1_5")
        self.assertEqual(r._routing_stats["l1_5_count"], 1)


# ── 4. Context-driven escalation ──


class TestContextEscalation(unittest.TestCase):
    """4. ``route()`` with context triggers L1.5 / L2 paths."""

    def test_cusum_triggers_l1_5(self):
        r = ModelRouter()
        ctx = {"cusum_triggered": True}
        self.assertEqual(r.route(0.9, context=ctx), "l1_5")

    def test_high_vol_triggers_l1_5(self):
        r = ModelRouter()
        ctx = {"daily_vol_pct": 10.0}
        self.assertEqual(r.route(0.9, context=ctx), "l1_5")

    def test_negative_pnl_escalates_to_l2(self):
        r = ModelRouter()
        # L1.5 trigger via new symbol + L2 escalation via weekly PnL drop.
        ctx = {"is_new_symbol": True, "weekly_pnl_pct": -10.0}
        self.assertEqual(r.route(0.9, context=ctx), "l2")
        self.assertEqual(r._routing_stats["l2_count"], 1)


# ── 5. check_l2_cache hit / expired / no-entry ──


class TestCheckL2Cache(unittest.TestCase):
    """5. Cache lookup branches update local + caller stats."""

    def test_hit_updates_local_counter(self):
        r = ModelRouter()
        intel = _make_intel(symbols=["AAA"])
        r._store_l2_result(intel, _make_evaluation(), None)
        caller_stats: dict = {}
        result = r.check_l2_cache("AAA", caller_stats)
        self.assertIsNotNone(result)
        self.assertEqual(r._routing_stats["l2_cache_hit"], 1)
        self.assertEqual(caller_stats.get("l2_cache_hit"), 1)

    def test_expired_evicts_and_counts(self):
        r = ModelRouter()
        # Manually inject an expired entry.
        r._l2_result_cache["BBB"] = {
            "evaluation": _make_evaluation(),
            "timestamp": time.time() - 9999,  # > TTL
            "intel_id": "old",
        }
        caller_stats: dict = {}
        result = r.check_l2_cache("BBB", caller_stats)
        self.assertIsNone(result)
        self.assertEqual(r._routing_stats["l2_cache_expired"], 1)
        self.assertNotIn("BBB", r._l2_result_cache)

    def test_no_entry_no_counter_change(self):
        r = ModelRouter()
        caller_stats: dict = {}
        result = r.check_l2_cache("UNKNOWN", caller_stats)
        self.assertIsNone(result)
        # Neither hit nor expired counter touched.
        self.assertEqual(r._routing_stats["l2_cache_hit"], 0)
        self.assertEqual(r._routing_stats["l2_cache_expired"], 0)


# ── 6. _store_l2_result counter ──


class TestStoreL2Result(unittest.TestCase):
    """6. ``_store_l2_result`` increments the local stored counter."""

    def test_store_increments_counter(self):
        r = ModelRouter()
        intel = _make_intel(symbols=["CCC", "DDD"])
        r._store_l2_result(intel, _make_evaluation(), None)
        # Two symbols → cache populated; counter incremented once per call.
        self.assertEqual(r._routing_stats["l2_cache_stored"], 1)
        self.assertEqual(r.cache_size, 2)


# ── 7-8. get_h3_snapshot schema ──


class TestSnapshotSchema(unittest.TestCase):
    """7-8. ``get_h3_snapshot()`` returns canonical schema."""

    def test_snapshot_has_all_keys(self):
        r = ModelRouter()
        snap = r.get_h3_snapshot()
        for key in (
            "total_routes",
            "l1_9b_count",
            "l1_27b_count",
            "l1_5_count",
            "l2_count",
            "budget_denied_count",
            "l2_cache_hit",
            "l2_cache_expired",
            "l2_cache_stored",
            "cache_size",
        ):
            self.assertIn(key, snap, f"missing snapshot key: {key}")

    def test_snapshot_initial_values_zero(self):
        r = ModelRouter()
        snap = r.get_h3_snapshot()
        for key in (
            "total_routes",
            "l1_9b_count",
            "l1_27b_count",
            "l1_5_count",
            "l2_count",
            "budget_denied_count",
            "l2_cache_hit",
            "l2_cache_expired",
            "l2_cache_stored",
            "cache_size",
        ):
            self.assertEqual(snap[key], 0)

    def test_snapshot_reflects_routing_activity(self):
        r = ModelRouter()
        r.route(0.3)
        r.route(0.6)
        r.route(0.9)
        snap = r.get_h3_snapshot()
        self.assertEqual(snap["total_routes"], 3)
        self.assertEqual(snap["l1_9b_count"], 1)
        self.assertEqual(snap["l1_27b_count"], 1)
        self.assertEqual(snap["l2_count"], 1)


# ── 9. env=1 invalidate_async per branch ──


class TestInvalidateAsyncCalls(unittest.TestCase):
    """9. ``invalidate_async`` invoked per H3 branch when env=1.

    We patch the module-level ``_invalidate_h_state_async`` in
    ``app.model_router`` so we can count calls without IPC traffic.
    """

    def test_route_branches_emit_one_invalidate_each(self):
        with patch("app.model_router._invalidate_h_state_async") as mock_inv:
            r = ModelRouter()
            r.route(0.3)  # h3.l1_9b
            r.route(0.6)  # h3.l1_27b
            r.route(0.9)  # h3.l2 (no context)
            ctx = {"confidence": 0.4, "amount_pct": 6.0}
            r.route(0.9, context=ctx)  # h3.l1_5

            # Each route call → one invalidate.
            self.assertEqual(mock_inv.call_count, 4)
            reasons = [c.args[0] for c in mock_inv.call_args_list]
            self.assertIn("h3.l1_9b", reasons)
            self.assertIn("h3.l1_27b", reasons)
            self.assertIn("h3.l2", reasons)
            self.assertIn("h3.l1_5", reasons)

    def test_cache_hit_emits_invalidate(self):
        with patch("app.model_router._invalidate_h_state_async") as mock_inv:
            r = ModelRouter()
            intel = _make_intel(symbols=["EEE"])
            r._store_l2_result(intel, _make_evaluation(), None)
            mock_inv.reset_mock()
            r.check_l2_cache("EEE", {})
            mock_inv.assert_called()
            reasons = [c.args[0] for c in mock_inv.call_args_list]
            self.assertIn("h3.l2_cache_hit", reasons)

    def test_budget_denied_emits_invalidate_with_correct_reason(self):
        with patch("app.model_router._invalidate_h_state_async") as mock_inv:
            r = ModelRouter()
            r.set_budget_checker(lambda tier: False)
            ctx = {"confidence": 0.4, "amount_pct": 6.0}
            r.route(0.9, context=ctx)
            reasons = [c.args[0] for c in mock_inv.call_args_list]
            self.assertIn("h3.budget_denied", reasons)


# ── 10. env=0 → no-op singleton ──


class TestEnvOffNoOp(unittest.TestCase):
    """10. env=0 ⇒ invalidate_async stays a module-level no-op."""

    def test_env_off_no_singleton_constructed(self):
        prev_env = os.environ.pop("OPENCLAW_H_STATE_GATEWAY", None)
        try:
            from app import h_state_invalidator as inv_mod

            inv_mod._reset_for_tests()
            inv_mod.init_h_state_invalidator()
            self.assertIsNone(inv_mod.get_invalidator())
            r = ModelRouter()
            r.route(0.3)
            self.assertIsNone(inv_mod.get_invalidator())
            # Local counter still updates regardless of env.
            self.assertEqual(r._routing_stats["l1_9b_count"], 1)
        finally:
            if prev_env is not None:
                os.environ["OPENCLAW_H_STATE_GATEWAY"] = prev_env


# ── 11. Snapshot isolation ──


class TestSnapshotIsolation(unittest.TestCase):
    """11. Mutating the returned snapshot does not affect internal state."""

    def test_snapshot_mutation_isolated(self):
        r = ModelRouter()
        r.route(0.3)
        snap = r.get_h3_snapshot()
        snap["total_routes"] = 9999
        snap["l1_9b_count"] = 9999
        # Refetch — counters intact.
        snap2 = r.get_h3_snapshot()
        self.assertEqual(snap2["total_routes"], 1)
        self.assertEqual(snap2["l1_9b_count"], 1)


# ── 12. Cache size accuracy ──


class TestCacheSizeAccuracy(unittest.TestCase):
    """12. ``cache_size`` in snapshot reflects real ``_l2_result_cache`` size."""

    def test_cache_size_matches_after_store(self):
        r = ModelRouter()
        intel = _make_intel(symbols=["X", "Y", "Z"])
        r._store_l2_result(intel, _make_evaluation(), None)
        snap = r.get_h3_snapshot()
        self.assertEqual(snap["cache_size"], 3)


if __name__ == "__main__":
    unittest.main()
