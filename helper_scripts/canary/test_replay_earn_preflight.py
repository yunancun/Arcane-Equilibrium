#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：Stage 0R Earn variant preflight harness unit test
   per docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md §7.6 E4 regression scope。

主要類/函數：
   - TestStage0REarnPreflight: 5 sanity check + fail injection grid + verdict gate

依賴：unittest (對齊既有 test_canary.py pattern);無第三方。

硬邊界：
   - 不調 Bybit live endpoint (fetch_apr_history mocked to empty fallback)
   - 不寫 PG / 不發 stake (純 in-memory state)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from replay_earn_preflight import (
    AccrualRecord,
    GATE_FAIL_INJECTIONS,
    RECONCILIATION_SEVERITIES,
    mock_5_gate_reject_path,
    mock_daily_reconciliation_cron,
    output_preflight_verdict,
    sanity_check_1_apy_drift,
    sanity_check_2_5gate_reject,
    sanity_check_3_first_stake_lal0,
    sanity_check_4_failclosed_exitcode,
    sanity_check_5_atr_cap_drawdown,
    simulate_apy_accrual,
)


class TestStage0REarnPreflight(unittest.TestCase):
    """5 sanity check + fail injection grid + verdict gate test。"""

    def test_simulate_apy_accrual_empty_events_fallback(self):
        """空 apr_events fallback 0% APR 7d → cumulative=0。"""
        accruals, cum = simulate_apy_accrual([], stake_amount_usdt=100.0, days=7)
        self.assertEqual(len(accruals), 7)
        self.assertEqual(cum, 0.0)
        self.assertTrue(all(a.daily_accrual_usdt == 0.0 for a in accruals))

    def test_simulate_apy_accrual_constant_apr(self):
        """constant 10% APR × 7d × $100 stake → cumulative ≈ 100 * 0.10 * 7 / 365 ≈ 0.1918。"""
        events = []
        base_ts = 1_700_000_000_000
        for i in range(7 * 24):
            events.append({
                "coin": "USDT",
                "product_type": "FlexibleSaving",
                "apr": 0.10,
                "timestamp_ms": base_ts + i * 3_600_000,
            })
        accruals, cum = simulate_apy_accrual(events, stake_amount_usdt=100.0, days=7)
        self.assertEqual(len(accruals), 7)
        expected = 100.0 * 0.10 * 7 / 365.0
        self.assertAlmostEqual(cum, expected, places=4)

    def test_sanity_check_1_first_stake_vacuous_pass(self):
        """first stake (None historical) → VACUOUS_PASS。"""
        status, msg, metrics = sanity_check_1_apy_drift(
            cumulative_7d_usdt=0.0, historical_demo_accrual_usdt=None,
        )
        self.assertEqual(status, "VACUOUS_PASS")
        self.assertTrue(metrics["vacuous"])

    def test_sanity_check_1_drift_under_5pct_pass(self):
        """drift 3% < 5% → PASS。"""
        status, msg, metrics = sanity_check_1_apy_drift(
            cumulative_7d_usdt=1.0, historical_demo_accrual_usdt=0.97,
        )
        self.assertEqual(status, "PASS")
        self.assertLess(metrics["drift_pct"], 5.0)

    def test_sanity_check_1_drift_over_5pct_fail(self):
        """drift 10% > 5% → FAIL。"""
        status, _, metrics = sanity_check_1_apy_drift(
            cumulative_7d_usdt=1.0, historical_demo_accrual_usdt=0.90,
        )
        self.assertEqual(status, "FAIL")
        self.assertGreater(metrics["drift_pct"], 5.0)

    def test_mock_5_gate_reject_path_full_coverage(self):
        """5 個 fail injection 全 PASS。"""
        grid = mock_5_gate_reject_path()
        self.assertEqual(len(grid), 5)
        gates = [g["gate"] for g in grid]
        self.assertEqual(set(gates), {"a", "b", "c", "d", "e"})
        for g in grid:
            self.assertEqual(g["verdict"], "PASS")
            self.assertEqual(g["simulated_verdict"], "rejected")

    def test_sanity_check_2_5gate_all_pass(self):
        """5/5 fail injection PASS → check 2 PASS。"""
        grid = mock_5_gate_reject_path()
        status, msg, metrics = sanity_check_2_5gate_reject(grid)
        self.assertEqual(status, "PASS")
        self.assertEqual(metrics["passed_count"], 5)
        self.assertEqual(metrics["failed_count"], 0)

    def test_sanity_check_2_5gate_with_injected_fail(self):
        """注入 1 個 FAIL → check 2 FAIL。"""
        grid = mock_5_gate_reject_path()
        grid[0]["verdict"] = "FAIL"
        status, msg, metrics = sanity_check_2_5gate_reject(grid)
        self.assertEqual(status, "FAIL")
        self.assertEqual(metrics["passed_count"], 4)
        self.assertEqual(metrics["failed_count"], 1)

    def test_sanity_check_3_first_stake_deferred(self):
        """first stake (no V100 history) → DEFERRED。"""
        status, msg, metrics = sanity_check_3_first_stake_lal0(has_v100_history=False)
        self.assertEqual(status, "DEFERRED")
        self.assertIn("operator_first_stake", metrics["deferred_to"])

    def test_sanity_check_4_no_fail_expected_exit_0(self):
        """0 FAIL → expected_exit_code=0。"""
        results = [("PASS", "ok"), ("VACUOUS_PASS", "ok"), ("DEFERRED", "ok"), ("PASS", "ok")]
        status, msg, metrics = sanity_check_4_failclosed_exitcode(results)
        self.assertEqual(status, "PASS")
        self.assertEqual(metrics["expected_exit_code"], 0)
        self.assertEqual(metrics["fail_count"], 0)

    def test_sanity_check_4_one_fail_expected_exit_1(self):
        """1 FAIL → expected_exit_code=1。"""
        results = [("PASS", "ok"), ("FAIL", "bad"), ("PASS", "ok"), ("PASS", "ok")]
        status, msg, metrics = sanity_check_4_failclosed_exitcode(results)
        self.assertEqual(status, "PASS")  # meta-check 自身 PASS
        self.assertEqual(metrics["expected_exit_code"], 1)
        self.assertEqual(metrics["fail_count"], 1)

    def test_sanity_check_5_atr_cap_constant(self):
        """ATR cap 不適用 + drawdown gate partial_post_sprint5。"""
        status, msg, metrics = sanity_check_5_atr_cap_drawdown()
        self.assertEqual(status, "PASS")
        self.assertFalse(metrics["atr_cap_applicable"])
        self.assertEqual(metrics["drawdown_gate_applicable"], "partial_post_sprint5")

    def test_mock_daily_reconciliation_3_severity(self):
        """3 階 cascade (Notice/Warn/Degraded) 各 1 次。"""
        grid = mock_daily_reconciliation_cron()
        self.assertEqual(len(grid), 3)
        sevs = [r["severity"] for r in grid]
        self.assertEqual(sevs, ["Notice", "Warn", "Degraded"])
        for r in grid:
            self.assertEqual(r["verdict"], "PASS")

    def test_output_preflight_verdict_schema_first_stake(self):
        """first stake verdict JSON schema 對齊 spec §4 AC-5。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            accruals = [
                AccrualRecord(day_index=i, apr=0.0, daily_accrual_usdt=0.0, cumulative_accrual_usdt=0.0)
                for i in range(7)
            ]
            verdict = output_preflight_verdict(
                coin="USDT",
                amount_usd=100.0,
                days=7,
                accruals=accruals,
                cumulative_7d_usdt=0.0,
                apr_events=[],
                fail_injection_grid=mock_5_gate_reject_path(),
                reconciliation_grid=mock_daily_reconciliation_cron(),
                output_dir=tmpdir,
            )

            # spec §4 AC-5 JSON schema 必含 field
            self.assertEqual(verdict["coin"], "USDT")
            self.assertEqual(verdict["amount_usd"], 100.0)
            self.assertEqual(verdict["days"], 7)
            self.assertIn("sanity_checks", verdict)
            self.assertIn("apy_drift_check", verdict["sanity_checks"])
            self.assertIn("5gate_reject_check", verdict["sanity_checks"])
            self.assertIn("first_stake_lal0_check", verdict["sanity_checks"])
            self.assertIn("failclosed_exitcode_check", verdict["sanity_checks"])
            self.assertIn("atr_cap_drawdown_check", verdict["sanity_checks"])
            self.assertTrue(verdict["eligible_for_first_stake"])
            self.assertEqual(verdict["verdict"], "PASS")
            # spec §3.5 dry-run invariants 5 條全 True
            self.assertTrue(all(verdict["dry_run_invariants"].values()))


if __name__ == "__main__":
    unittest.main()
