#!/usr/bin/env python3
"""Unit tests for LG-5-IMPL-3 governance healthchecks `[42]` + `[42b]`
+ LG5-W3-FUP-2 Fix 1 healthcheck `[43]` + LG5-W3-FUP-2 Fix 2 healthcheck
`[42c]`.

LG-5-IMPL-3 治理 healthcheck `[42]` + `[42b]` + LG5-W3-FUP-2 Fix 1
healthcheck `[43]` + LG5-W3-FUP-2 Fix 2 healthcheck `[42c]` 單元測試。

Mocks `psycopg2`-style cursor with deterministic ``fetchone`` /
``fetchall`` return values per RFC v2 §6 IMPL-3 SLA + §3 R-meta band
+ LG5-W3-FUP-2 cron freshness threshold contract + Fix 2 RFC §5
Plan B gate-aligned 3d window contract.
模擬 psycopg2 cursor，按 RFC v2 §6 IMPL-3 SLA + §3 R-meta band +
LG5-W3-FUP-2 cron 新鮮度閾值合約 + Fix 2 RFC §5 方案 B gate-aligned
3d window 合約提供 deterministic fixture，驗證 PASS/WARN/FAIL 各條
path 各自正確。

Round 2 (2026-05-02) 新增 `test_fail_when_worst_in_standard_fail_band`
覆蓋 RFC v2 §6 IMPL-3 line 451 三段中的 [0.10, 0.30) standard FAIL band；
原 `test_warn_when_worst_in_warn_band` fixture 從 0.30 改 0.40 以嚴格
落在 [0.30, 0.50) WARN band 內，避 boundary 歧義。

LG5-W3-FUP-2 Fix 1 (2026-05-02) 新增 `[43]` healthcheck 5 個 tests
覆蓋 PASS / WARN / FAIL by age / FAIL by no rows / FAIL by V017 missing。

LG5-W3-FUP-2 Fix 2 (2026-05-02 RFC §5 Plan B) 新增 `[42c]` healthcheck
6 個 tests 鏡 `[42b]` 同 6 case：PASS / WARN / FAIL standard / FAIL
pipeline-alert / missing-strategy → 0.0 fallback / V031 missing fail-closed。
total = 25 tests (19 prior + 6 new for `[42c]`).
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# srv root on sys.path (mirror test_mlde_healthchecks.py).
# 加 srv root 到 sys.path（鏡像 test_mlde_healthchecks.py）。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_governance import (  # noqa: E402
    LABEL_BACKFILL_PASS_MAX_SECONDS,
    LABEL_BACKFILL_WARN_MAX_SECONDS,
    LG5_STRATEGIES,
    check_42_live_candidate_eval_contract,
    check_42b_live_candidate_attribution_drift,
    check_42c_live_candidate_attribution_drift_3d,
    check_43_label_backfill_freshness,
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

    def test_missing_strategy_treated_as_low_sample_warn(self) -> None:
        """Missing settled strategy sample → WARN, not ratio failure.
        缺 settled strategy sample → WARN，不當作 ratio failure。"""
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
        self.assertEqual(status, "WARN")
        self.assertIn("funding_arb=LOW_SAMPLE(n=0, need=10)", msg)
        self.assertIn("sample-maturity watch only", msg)
        self.assertIn("not attribution drift", msg)

    def test_warn_when_all_strategies_silent(self) -> None:
        """All 5 strategies have 0 rows in 7d → WARN (greenfield deploy).
        全 5 strategy 0 row → WARN（首次部署 / 全靜默）。"""
        cur = _cursor_for_42b(exists=True, rows=[])  # no rows at all
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("no settled MLDE training rows", msg)
        self.assertIn("first-deploy", msg)

    def test_fail_when_view_missing(self) -> None:
        """V031 not applied → FAIL / V031 未部署即直接 FAIL。"""
        cur = _cursor_for_42b(exists=False, rows=None)
        status, msg = check_42b_live_candidate_attribution_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V031 not applied", msg)


# ---------------------------------------------------------------------------
# `[43]` label_backfill_freshness — 5 verdict paths.
# `[43]` label_backfill_freshness — 5 條 verdict path。
#
# Production [43] reads max(label_filled_at) + extracts age in seconds
# directly from Postgres (`extract(epoch from now() - max(...))`). Fixture
# emulates that by returning a `(timestamp, age_seconds)` tuple from
# fetchone after the existence pre-check.
# 生產代碼讀 max(label_filled_at) + Postgres 內直接 extract age；
# fixture 模擬 fetchone 在表存在檢查後回 (timestamp, age_seconds) tuple。
# ---------------------------------------------------------------------------


def _cursor_for_43(
    table_exists: bool,
    age_row: tuple | None,
) -> MagicMock:
    """Build cursor for `[43]`. First fetchone returns existence row,
    second fetchone returns age_row = (latest_fill_ts, age_seconds) or
    None / (None, None) for "no rows".
    建 [43] 用 cursor。fetchone 先回 (table_exists,)，再回
    age_row = (latest_fill_ts, age_seconds) 或 None / (None, None)。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = [(table_exists,), age_row]
    return cur


class TestCheck43LabelBackfillFreshness(unittest.TestCase):
    def test_pass_when_fill_recent(self) -> None:
        """latest fill 30 min ago → PASS / 30 分鐘前剛跑 → PASS。"""
        # 30 min = 1800 seconds, well below PASS threshold (7200s = 2h).
        # 30 分鐘 = 1800s，遠低於 PASS 閾值（7200s = 2h）。
        latest_fill = datetime.now(timezone.utc) - timedelta(minutes=30)
        cur = _cursor_for_43(table_exists=True, age_row=(latest_fill, 1800.0))
        status, msg = check_43_label_backfill_freshness(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("age=0.50h", msg)
        self.assertIn("alive (within 2h)", msg)

    def test_warn_when_fill_in_warn_band(self) -> None:
        """latest fill 4h ago → WARN / 4 小時前 → WARN（2-6h band）。"""
        # 4h = 14400 seconds, strictly inside [PASS_MAX, WARN_MAX) = [7200, 21600).
        # 4h = 14400s，嚴格在 [PASS_MAX, WARN_MAX) = [7200, 21600) 區間內。
        self.assertGreater(14400, LABEL_BACKFILL_PASS_MAX_SECONDS)
        self.assertLess(14400, LABEL_BACKFILL_WARN_MAX_SECONDS)
        latest_fill = datetime.now(timezone.utc) - timedelta(hours=4)
        cur = _cursor_for_43(table_exists=True, age_row=(latest_fill, 14400.0))
        status, msg = check_43_label_backfill_freshness(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("age=4.00h", msg)
        self.assertIn("2-6h ago", msg)

    def test_fail_when_fill_too_old(self) -> None:
        """latest fill 8h ago → FAIL / 8 小時前 → FAIL（cron likely dead）。"""
        # 8h = 28800 seconds, well above WARN_MAX (21600s = 6h).
        # 8h = 28800s，遠超 WARN_MAX（21600s = 6h）。
        latest_fill = datetime.now(timezone.utc) - timedelta(hours=8)
        cur = _cursor_for_43(table_exists=True, age_row=(latest_fill, 28800.0))
        status, msg = check_43_label_backfill_freshness(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("age=8.00h", msg)
        self.assertIn("≥6h ago", msg)
        self.assertIn("cron likely not running", msg)
        self.assertIn("crontab -l", msg)
        self.assertIn("edge_label_backfill_cron", msg)

    def test_fail_when_no_rows(self) -> None:
        """No rows / fill never run → FAIL / 無 row → FAIL（從未跑過）。"""
        # Postgres returns (None, None) when max(...) over empty set.
        # Postgres 對空集合 max(...) 回 (None, None)。
        cur = _cursor_for_43(table_exists=True, age_row=(None, None))
        status, msg = check_43_label_backfill_freshness(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("no decision_features rows", msg)
        self.assertIn("backfill never ran", msg)

    def test_fail_when_v017_missing(self) -> None:
        """V017 not applied → FAIL fast / V017 未部署即 FAIL。"""
        # to_regclass returns NULL when table absent; existence row = (False,)
        # to_regclass 在表缺時回 NULL；existence row = (False,)。
        cur = _cursor_for_43(table_exists=False, age_row=None)
        status, msg = check_43_label_backfill_freshness(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V017 not applied", msg)

    def test_thresholds_match_module_constants(self) -> None:
        """Threshold contract — 2h PASS / 6h WARN per module constants.
        閾值合約 — PASS 2h / WARN 6h（模組常量驗證）。"""
        self.assertEqual(LABEL_BACKFILL_PASS_MAX_SECONDS, 2 * 3600)
        self.assertEqual(LABEL_BACKFILL_WARN_MAX_SECONDS, 6 * 3600)


# ---------------------------------------------------------------------------
# `[42c]` live_candidate_attribution_drift_3d — 4 verdict bands + 2 edge paths.
# RFC v2 §6 IMPL-3 line 451 三段 floor (0.50/0.30/0.10) 產生 4 區間，
# 鏡 `[42b]` 但 window 改 3d (LG5-W3-FUP-2 Fix 2 RFC §5 方案 B)。
# `[42c]` live_candidate_attribution_drift_3d — 4 段 verdict + 2 條 edge case。
#
# 共 6 case 鏡 [42b] 完全對齊：PASS / WARN / FAIL standard / FAIL pipeline-alert
# / missing-strategy → 0.0 fallback / V031 missing fail-closed。Fixture 結構
# 完全鏡 _cursor_for_42b（先 fetchone 表存在，再 fetchall per-strategy rows）。
# ---------------------------------------------------------------------------
class TestCheck42cLiveCandidateAttributionDrift3d(unittest.TestCase):
    def test_pass_when_all_strategies_above_floor(self) -> None:
        """All 5 strategies ≥ 0.50 → PASS / 全 5 個 strategy ≥ 0.50 即 PASS。

        Fixture identical in shape to [42b] PASS test; the production code
        path differs only in SQL window (3d vs 7d), so verdict logic on
        the same ratio dict must yield the same band.
        Fixture 結構與 [42b] PASS 測試一致；生產代碼僅 window 不同，故
        相同 ratio dict 的 verdict 邏輯必須產生相同 band。
        """
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 60, 0.60),
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 50, 0.50),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42c_live_candidate_attribution_drift_3d(cur)
        self.assertEqual(status, "PASS")
        # `[42c]` msg must explicitly flag the 3d window so operator can tell
        # which sentinel emitted (vs `[42b]` 7d).
        # `[42c]` msg 必須明示 3d window 以區別 `[42b]` 7d。
        self.assertIn("R-meta floor", msg)
        self.assertIn("3d", msg)

    def test_warn_when_worst_in_warn_band(self) -> None:
        """0.30 ≤ worst < 0.50 → WARN / 最差落在 [0.30, 0.50) 即 WARN。

        Mirrors [42b] WARN test (ratio 0.40 strictly inside [0.30, 0.50));
        `[42c]` adds a `(check [42b] 7d ratio for long-window context)`
        suffix to msg per docstring operator interpretation matrix —
        verify it surfaces.
        鏡 [42b] WARN 測試（ratio 0.40 嚴格在 [0.30, 0.50) 內）；
        `[42c]` msg 多 `(check [42b] 7d ratio for long-window context)`
        後綴對應 operator 對照矩陣，驗證該字串浮現。
        """
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 40, 0.40),  # worst, strictly in WARN band [0.30, 0.50)
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 60, 0.60),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42c_live_candidate_attribution_drift_3d(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("ma_crossover", msg)
        self.assertIn("0.400", msg)
        self.assertIn("review_live_candidate will defer", msg)
        # `[42c]`-specific suffix per operator interpretation matrix.
        # `[42c]` 專屬後綴對應 operator 對照矩陣。
        self.assertIn("[42b]", msg)

    def test_fail_when_worst_in_standard_fail_band(self) -> None:
        """0.10 ≤ worst < 0.30 → FAIL standard band / [0.10, 0.30) 即標準 FAIL。

        Mirrors [42b] standard FAIL test; `[42c]` msg references [43]
        cron healthcheck per docstring (label backfill cron is the
        producer-side liveness sentinel for the same ratio data).
        鏡 [42b] standard FAIL 測試；`[42c]` msg 引用 [43] cron healthcheck
        對應 docstring（label backfill cron 是同 ratio 資料的 producer-side
        liveness 哨兵）。
        """
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 20, 0.20),  # worst, in standard FAIL band [0.10, 0.30)
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 60, 0.60),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42c_live_candidate_attribution_drift_3d(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("ma_crossover", msg)
        self.assertIn("standard FAIL floor", msg)
        # standard FAIL band must NOT trigger pipeline-alert / lease_revoke wording.
        # standard FAIL band 不可觸發 pipeline-alert / lease_revoke 字樣。
        self.assertNotIn("pipeline-alert floor", msg)
        self.assertNotIn("lease_revoke_trigger", msg)
        # `[42c]`-specific cross-ref to label backfill cron sentinel.
        # `[42c]` 專屬 cross-ref label backfill cron 哨兵。
        self.assertIn("[43]", msg)

    def test_fail_when_worst_below_pipeline_floor(self) -> None:
        """worst < 0.10 → FAIL pipeline-level alert / 最差 < 0.10 即 FAIL。

        Mirrors [42b] pipeline-alert escalation; lease_revoke_trigger
        wording must be present (RFC §4 line 405).
        鏡 [42b] pipeline-alert 升級；lease_revoke_trigger 字樣必出現
        （RFC §4 line 405）。
        """
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 5, 0.05),  # worst, below 0.10 floor
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
            ("funding_arb", 100, 60, 0.60),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42c_live_candidate_attribution_drift_3d(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("ma_crossover", msg)
        self.assertIn("pipeline-alert floor", msg)
        self.assertIn("lease_revoke_trigger", msg)
        # `[42c]` msg must explicitly flag 3d window even at FAIL-pipeline.
        # `[42c]` msg 必須明示 3d window，即使在 FAIL-pipeline 段。
        self.assertIn("3d", msg)

    def test_missing_strategy_treated_as_low_sample_warn(self) -> None:
        """Missing settled strategy sample → WARN, not ratio failure.
        缺 settled strategy sample → WARN，不當作 ratio failure。"""
        rows = [
            ("grid_trading", 100, 80, 0.80),
            ("ma_crossover", 100, 60, 0.60),
            ("bb_breakout", 100, 70, 0.70),
            ("bb_reversion", 100, 55, 0.55),
        ]
        cur = _cursor_for_42b(exists=True, rows=rows)
        status, msg = check_42c_live_candidate_attribution_drift_3d(cur)
        self.assertEqual(status, "WARN")
        self.assertIn("funding_arb=LOW_SAMPLE(n=0, need=10)", msg)
        self.assertIn("sample-maturity watch only", msg)
        self.assertIn("not attribution drift", msg)

    def test_fail_when_view_missing(self) -> None:
        """V031 not applied → FAIL fast / V031 未部署即直接 FAIL。

        Mirrors [42b] V031 missing fail-closed; `[42c]` msg must reference
        `[42c]` prefix (not `[42b]`) so operator can disambiguate which
        sentinel reported the missing view.
        鏡 [42b] V031 missing fail-closed；`[42c]` msg 必須帶 `[42c]` 前綴
        (非 `[42b]`)，以便 operator 區分哪個 sentinel 回報。
        """
        cur = _cursor_for_42b(exists=False, rows=None)
        status, msg = check_42c_live_candidate_attribution_drift_3d(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V031 not applied", msg)
        # Must carry [42c] prefix not [42b] so operator can disambiguate.
        # 必須帶 [42c] 前綴非 [42b]，方便 operator 區分。
        self.assertIn("[42c]", msg)


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
