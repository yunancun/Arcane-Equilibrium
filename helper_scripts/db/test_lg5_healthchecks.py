#!/usr/bin/env python3
"""Unit tests for LG-5-IMPL-3 governance healthchecks `[42]` + `[42b]`.

LG-5-IMPL-3 治理 healthcheck `[42]` + `[42b]` 單元測試。

Mocks `psycopg2`-style cursor with deterministic ``fetchone`` /
``fetchall`` return values per RFC v2 §6 IMPL-3 SLA + §3 R-meta band.
模擬 psycopg2 cursor，按 RFC v2 §6 IMPL-3 SLA + §3 R-meta band 提供
deterministic fixture 驗證 PASS/WARN/FAIL 各條 path 各自正確。

Round 2 (2026-05-02) 新增 `test_fail_when_worst_in_standard_fail_band`
覆蓋 RFC v2 §6 IMPL-3 line 451 三段中的 [0.10, 0.30) standard FAIL band；
原 `test_warn_when_worst_in_warn_band` fixture 從 0.30 改 0.40 以嚴格
落在 [0.30, 0.50) WARN band 內，避 boundary 歧義。total = 13 tests。
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

# srv root on sys.path (mirror test_mlde_healthchecks.py).
# 加 srv root 到 sys.path（鏡像 test_mlde_healthchecks.py）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_governance import (  # noqa: E402
    LG5_STRATEGIES,
    check_42_live_candidate_eval_contract,
    check_42b_live_candidate_attribution_drift,
)


def _cursor_with_fetchone(fetches: list[tuple]) -> MagicMock:
    """Build a MagicMock cursor whose ``fetchone()`` returns successive
    rows from ``fetches``. ``fetchall`` separately set by callers that
    need it.
    建 fetchone 依序回 fetches 的 mock cursor；fetchall 由需要的測試獨立 set。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetches
    return cur


def _cursor_for_42b(
    exists: bool,
    rows: list[tuple] | None,
) -> MagicMock:
    """Build cursor for `[42b]`. First fetchone returns existence row,
    then fetchall returns per-strategy rows of shape
    (strategy_name, total, chain_ok, ratio).
    建 [42b] 用的 cursor。fetchone 先回存在性，再 fetchall 回 per-strategy 行。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = [(exists,)]
    cur.fetchall.return_value = rows if rows is not None else []
    return cur


# ---------------------------------------------------------------------------
# `[42]` live_candidate_eval_contract — 3 verdict bands + 2 fail-closed paths.
# `[42]` live_candidate_eval_contract — 三段 verdict + 2 條 fail-closed。
# ---------------------------------------------------------------------------
class TestCheck42LiveCandidateEvalContract(unittest.TestCase):
    def test_pass_when_no_unaudited(self) -> None:
        """unaudited == 0 → PASS / 0 個未審計即 PASS。"""
        # fetches order: existence(2-tuple), unaudited(1-tuple), recent_total(1-tuple)
        # fetches 順序：表存在(2-tuple)、未審計數(1-tuple)、24h 總數(1-tuple)
        cur = _cursor_with_fetchone([(True, True), (0,), (5,)])
        status, msg = check_42_live_candidate_eval_contract(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("unaudited_over_1h=0", msg)
        self.assertIn("recent_24h_total=5", msg)

    def test_warn_when_small_backlog(self) -> None:
        """1 ≤ unaudited ≤ 2 → WARN / 1-2 件積壓 → WARN。"""
        cur = _cursor_with_fetchone([(True, True), (2,), (10,)])
        status, msg = check_42_live_candidate_eval_contract(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("unaudited_over_1h=2", msg)
        self.assertIn("backlog", msg)

    def test_fail_when_contract_broken(self) -> None:
        """unaudited ≥ 3 → FAIL / ≥3 件未審計即 contract 系統性破裂。"""
        cur = _cursor_with_fetchone([(True, True), (5,), (10,)])
        status, msg = check_42_live_candidate_eval_contract(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("unaudited_over_1h=5", msg)
        self.assertIn("contract broken", msg)
        self.assertIn("lease_revoke_trigger", msg)

    def test_fail_when_governance_audit_log_missing(self) -> None:
        """V035 not applied → FAIL fast / V035 未部署即直接 FAIL。"""
        # mlde_param_applications exists, governance_audit_log missing.
        # mlde_param_applications 在，governance_audit_log 缺。
        cur = _cursor_with_fetchone([(True, False)])
        status, msg = check_42_live_candidate_eval_contract(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V035 not applied", msg)

    def test_fail_when_mlde_param_applications_missing(self) -> None:
        """V032 not applied → FAIL / V032 未部署即直接 FAIL。"""
        cur = _cursor_with_fetchone([(False, False)])
        status, msg = check_42_live_candidate_eval_contract(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V032 not applied", msg)


# ---------------------------------------------------------------------------
# `[42b]` live_candidate_attribution_drift — 4 verdict bands + 2 edge paths.
# RFC v2 §6 IMPL-3 line 451 三段 floor (0.50/0.30/0.10) 產生 4 區間：
# PASS / WARN / FAIL standard / FAIL pipeline-alert。
# `[42b]` live_candidate_attribution_drift — 4 段 verdict + 2 條 edge case。
# ---------------------------------------------------------------------------
class TestCheck42bAttributionDrift(unittest.TestCase):
    def test_pass_when_all_strategies_above_floor(self) -> None:
        """All 5 strategies ≥ 0.50 → PASS / 全 5 個 strategy ≥ 0.50 即 PASS。"""
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 60, 0.60),
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 50, 0.50),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("R-meta floor", msg)

    def test_warn_when_worst_in_warn_band(self) -> None:
        """0.30 ≤ worst < 0.50 → WARN / 最差落在 [0.30, 0.50) 即 WARN。

        RFC v2 §6 IMPL-3 line 451 三段：WARN band 是 [0.30, 0.50)，
        ratio 0.40 落在此區間。Round 1 fixture 0.30 改 0.40 以維持嚴格
        在 WARN band 內（0.30 為 WARN/FAIL boundary，避邊界歧義）。
        """
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 40, 0.40),  # worst, strictly in WARN band [0.30, 0.50)
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 60, 0.60),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("ma_crossover", msg)
        self.assertIn("0.400", msg)
        self.assertIn("review_live_candidate will defer", msg)

    def test_fail_when_worst_in_standard_fail_band(self) -> None:
        """0.10 ≤ worst < 0.30 → FAIL standard band / [0.10, 0.30) 即標準 FAIL。

        Round 2 新增：RFC v2 §6 IMPL-3 line 451 三段中的 standard FAIL
        band，attribution chain 系統性衰退但尚未觸發 pipeline-alert。
        ratio 0.20 嚴格在此區間中央。
        """
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 20, 0.20),  # worst, in standard FAIL band [0.10, 0.30)
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 60, 0.60),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("ma_crossover", msg)
        self.assertIn("standard FAIL floor", msg)
        # standard FAIL band must NOT trigger pipeline-alert / lease_revoke wording.
        # standard FAIL band 不可觸發 pipeline-alert / lease_revoke 字樣。
        self.assertNotIn("pipeline-alert floor", msg)
        self.assertNotIn("lease_revoke_trigger", msg)

    def test_fail_when_worst_below_pipeline_floor(self) -> None:
        """worst < 0.10 → FAIL pipeline-level alert / 最差 < 0.10 即 FAIL。"""
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 5, 0.05),  # worst, below 0.10 floor
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 60, 0.60),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("ma_crossover", msg)
        self.assertIn("pipeline-alert floor", msg)
        self.assertIn("lease_revoke_trigger", msg)

    def test_missing_strategy_treated_as_zero_ratio(self) -> None:
        """Missing strategy in DB → ratio=0.0 forces FAIL.
        某 strategy 在 DB 中缺 → 視為 ratio=0.0 強制 FAIL。"""
        # Only 4 of 5 strategies emit rows; funding_arb missing.
        # 只有 4 個 strategy 有 row；funding_arb 缺。
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 60, 0.60),
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("funding_arb=0.000", msg)
        self.assertIn("funding_arb", msg)

    def test_warn_when_all_strategies_silent(self) -> None:
        """All 5 strategies have 0 rows in 7d → WARN (greenfield deploy).
        全 5 strategy 0 row → WARN（首次部署 / 全靜默）。"""
        cur = _cursor_for_42b(exists=True, rows=[])  # no rows at all
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("no MLDE training rows", msg)
        self.assertIn("first-deploy", msg)

    def test_fail_when_view_missing(self) -> None:
        """V031 not applied → FAIL / V031 未部署即直接 FAIL。"""
        cur = _cursor_for_42b(exists=False, rows=None)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V031 not applied", msg)


# ---------------------------------------------------------------------------
# Constants sanity / 常量 sanity。
# ---------------------------------------------------------------------------
class TestConstants(unittest.TestCase):
    def test_lg5_strategies_count_is_five(self) -> None:
        """RFC v2 §3 R-meta — exactly 5 LG-5 strategies.
        RFC v2 §3 R-meta 明文 5 個 LG-5 strategy。"""
        self.assertEqual(len(LG5_STRATEGIES), 5)
        self.assertIn("grid_trading", LG5_STRATEGIES)
        self.assertIn("ma_crossover", LG5_STRATEGIES)
        self.assertIn("bb_breakout", LG5_STRATEGIES)
        self.assertIn("bb_reversion", LG5_STRATEGIES)
        self.assertIn("funding_arb", LG5_STRATEGIES)


if __name__ == "__main__":
    unittest.main()
