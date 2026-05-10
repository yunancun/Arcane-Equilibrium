#!/usr/bin/env python3
"""Unit tests for blocked_symbols_30d_unblock_check writer + healthcheck [64].

涵蓋：
  - 4 verdict logic（unblock_candidate / continue_freeze / dormant_no_evidence /
                     manual_review_required）
  - 30d cycle vs force_eval evaluation_path
  - yo-yo detection（spec §5.3）
  - DSR / PBO 計算邊界
  - INSERT row（mock cursor）
  - update_unblock_outcome sign-off completeness pre-check
  - render_markdown 結構
  - healthcheck [64] 4 sub-check（mock cursor）

純 mock-cursor 測試，無 PG dependency。
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_THIS_DIR = Path(os.path.abspath(__file__)).parent
_HELPER_SCRIPTS_DIR = _THIS_DIR.parent
_SRV_ROOT = _HELPER_SCRIPTS_DIR.parent
sys.path.insert(0, str(_SRV_ROOT))

from helper_scripts.db.audit.blocked_symbols_30d_unblock_check import (  # noqa: E402
    BlockedCell,
    UnblockCandidateRow,
    VERDICT_UNBLOCK_CANDIDATE,
    VERDICT_CONTINUE_FREEZE,
    VERDICT_DORMANT_NO_EVIDENCE,
    VERDICT_MANUAL_REVIEW_REQUIRED,
    EVAL_PATH_CRON,
    EVAL_PATH_FORCE,
    PAPER_FILLS_30D_MIN,
    PAPER_NET_EDGE_BPS_MIN,
    DSR_MIN,
    PBO_MAX,
    REJECTED_OUTCOME_MIN_IF_REJECTED,
    compute_dsr_pbo,
    evaluate_verdict,
    insert_unblock_candidate,
    update_unblock_outcome,
    render_markdown,
    iter_cells,
    load_registry,
    _values_sql,
    _parse_cell_arg,
)
from helper_scripts.db.passive_wait_healthcheck.checks_governance import (  # noqa: E402
    check_64_unblock_candidates_drift,
    UNBLOCK_STALE_CANDIDATE_DAYS,
)


# =============================================================================
# §1 Verdict logic tests
# =============================================================================


class TestVerdictLogic(unittest.TestCase):
    """覆蓋 4 verdict + yo-yo detection + DSR/PBO 邊界。"""

    def _cell(self) -> BlockedCell:
        return BlockedCell(strategy="grid_trading", symbol="BSBUSDT")

    def test_dormant_no_evidence_when_paper_fills_below_threshold(self) -> None:
        """paper_fills_30d < 30 → dormant_no_evidence verdict。"""
        evidence = {
            "paper_fills_30d": 5,  # < PAPER_FILLS_30D_MIN
            "paper_net_edge_bps_30d": 10.0,
            "rejected_n": 0,
            "rejected_outcome_n": 0,
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 0,
        }
        verdict, _, notes = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_DORMANT_NO_EVIDENCE)
        self.assertTrue(any(str(PAPER_FILLS_30D_MIN) in n for n in notes))

    def test_yoyo_forces_manual_review_required(self) -> None:
        """yoyo_count_30d ≥ 1 → 強制 manual_review_required（spec §5.3）。"""
        evidence = {
            "paper_fills_30d": 100,  # 充足
            "paper_net_edge_bps_30d": 20.0,  # 高 edge
            "rejected_n": 0,
            "rejected_outcome_n": 0,
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 1,  # trip yo-yo
        }
        verdict, _, notes = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_MANUAL_REVIEW_REQUIRED)
        self.assertTrue(any("yo-yo" in n for n in notes))

    def test_manual_review_when_dsr_pbo_null(self) -> None:
        """paper_fills ≥30 但 paper_net_edge_bps_30d=None → manual_review_required。"""
        evidence = {
            "paper_fills_30d": 50,  # ≥ 30
            "paper_net_edge_bps_30d": None,  # NULL → DSR/PBO 不可算
            "rejected_n": 0,
            "rejected_outcome_n": 0,
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 0,
        }
        verdict, _, notes = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_MANUAL_REVIEW_REQUIRED)
        self.assertTrue(any("NULL" in n for n in notes))

    def test_continue_freeze_when_paper_edge_below_threshold(self) -> None:
        """paper_fills ≥30 但 paper_edge < +5 bps → continue_freeze。"""
        evidence = {
            "paper_fills_30d": 100,
            "paper_net_edge_bps_30d": 2.0,  # < PAPER_NET_EDGE_BPS_MIN
            "rejected_n": 0,
            "rejected_outcome_n": 0,
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 0,
        }
        verdict, _, _ = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_CONTINUE_FREEZE)

    def test_continue_freeze_when_sm04_escalate_present(self) -> None:
        """SM-04 escalate 7d count > 0 → continue_freeze。"""
        evidence = {
            "paper_fills_30d": 100,
            "paper_net_edge_bps_30d": 20.0,
            "rejected_n": 0,
            "rejected_outcome_n": 0,
            "sm04_escalate_count_7d": 1,  # trip SM-04 condition
            "yoyo_count_30d": 0,
        }
        verdict, _, notes = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_CONTINUE_FREEZE)
        self.assertTrue(any("sm04_escalate_count_7d" in n for n in notes))

    def test_continue_freeze_when_rejected_outcome_insufficient(self) -> None:
        """rejected_n > 0 但 rejected_outcome_n < 5 → continue_freeze。"""
        evidence = {
            "paper_fills_30d": 100,
            "paper_net_edge_bps_30d": 20.0,
            "rejected_n": 100,
            "rejected_outcome_n": 2,  # < REJECTED_OUTCOME_MIN_IF_REJECTED
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 0,
        }
        verdict, _, _ = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_CONTINUE_FREEZE)

    def test_unblock_candidate_full_and_pass(self) -> None:
        """全 AND PASS → unblock_candidate verdict。"""
        evidence = {
            "paper_fills_30d": 100,  # ≥ 30
            "paper_net_edge_bps_30d": 20.0,  # ≥ +5 bps
            "rejected_n": 50,
            "rejected_outcome_n": 10,  # ≥ 5
            "sm04_escalate_count_7d": 0,
            "yoyo_count_30d": 0,
        }
        verdict, aug, _ = evaluate_verdict(self._cell(), evidence)
        self.assertEqual(verdict, VERDICT_UNBLOCK_CANDIDATE)
        # DSR / PBO 應該有值且通過閾值
        self.assertIsNotNone(aug["DSR"])
        self.assertIsNotNone(aug["PBO"])
        self.assertGreaterEqual(aug["DSR"], DSR_MIN)
        self.assertLessEqual(aug["PBO"], PBO_MAX)


# =============================================================================
# §2 DSR / PBO 計算
# =============================================================================


class TestDsrPboComputation(unittest.TestCase):
    def test_dsr_pbo_null_when_no_fills(self) -> None:
        """0 fills → (None, None) tuple。"""
        dsr, pbo = compute_dsr_pbo(0, None)
        self.assertIsNone(dsr)
        self.assertIsNone(pbo)

    def test_dsr_pbo_computed_when_sufficient(self) -> None:
        """充足 fills + edge → 有值。"""
        dsr, pbo = compute_dsr_pbo(100, 20.0)
        self.assertIsNotNone(dsr)
        self.assertIsNotNone(pbo)
        self.assertGreater(dsr, 0)
        # n=100 > 30 → PBO = 0
        self.assertEqual(pbo, 0.0)

    def test_pbo_decays_with_low_sample(self) -> None:
        """少樣本 → 高 PBO（selection-bias risk）。"""
        _, pbo_low = compute_dsr_pbo(5, 10.0)
        _, pbo_high = compute_dsr_pbo(25, 10.0)
        self.assertGreater(pbo_low, pbo_high)


# =============================================================================
# §3 PG writer tests（mock cursor）
# =============================================================================


class TestPgWriter(unittest.TestCase):
    """INSERT / UPDATE outcome 邏輯；mock _get_conn。"""

    def _row(self) -> UnblockCandidateRow:
        return UnblockCandidateRow(
            cell_strategy="grid_trading",
            cell_symbol="BSBUSDT",
            candidate_at_ms=1735689600000,  # 2025-01-01 UTC ms
            paper_evidence={"paper_fills_30d": 100, "DSR": 1.0, "PBO": 0.0},
            verdict=VERDICT_UNBLOCK_CANDIDATE,
        )

    def test_insert_returns_row_id(self) -> None:
        """INSERT 成功回 inserted id。"""
        cur = MagicMock()
        cur.fetchone.return_value = (42,)
        conn = MagicMock()
        conn.cursor.return_value = cur

        with patch(
            "helper_scripts.db.audit.blocked_symbols_30d_unblock_check._get_conn",
            return_value=conn,
        ):
            row_id = insert_unblock_candidate(self._row())
        self.assertEqual(row_id, 42)
        # INSERT SQL 必含 paper_evidence_jsonb
        executed_sqls = [c.args[0] for c in cur.execute.call_args_list if c.args]
        self.assertTrue(any("INSERT INTO governance.unblock_candidates" in s for s in executed_sqls))

    def test_insert_rejects_invalid_verdict(self) -> None:
        """不在 VALID_VERDICTS 列表的 verdict → ValueError。"""
        bad_row = UnblockCandidateRow(
            cell_strategy="grid_trading",
            cell_symbol="BSBUSDT",
            candidate_at_ms=1735689600000,
            paper_evidence={},
            verdict="invalid_verdict",
        )
        with self.assertRaises(ValueError):
            insert_unblock_candidate(bad_row)

    def test_update_unfrozen_requires_full_audit_trail(self) -> None:
        """outcome='unfrozen' 必含 pa/qc/commit_sha/unfrozen_at_ms（client-side check）。"""
        with self.assertRaises(ValueError):
            update_unblock_outcome(
                42,
                outcome="unfrozen",
                pa_report_path="docs/PA/.../report.md",
                # 缺 qc_report_path, commit_sha, unfrozen_at_ms
            )

    def test_update_unfrozen_full_audit_trail_passes(self) -> None:
        """全 4 欄齊全 → UPDATE 成功。"""
        cur = MagicMock()
        cur.rowcount = 1
        conn = MagicMock()
        conn.cursor.return_value = cur

        with patch(
            "helper_scripts.db.audit.blocked_symbols_30d_unblock_check._get_conn",
            return_value=conn,
        ):
            ok = update_unblock_outcome(
                42,
                outcome="unfrozen",
                pa_report_path="docs/PA/2026-05-10--unblock_grid_BSBUSDT.md",
                qc_report_path="docs/QC/2026-05-10--unblock_grid_BSBUSDT.md",
                commit_sha="abc12345",
                unfrozen_at_ms=1735776000000,  # 2025-01-02 UTC ms
            )
        self.assertTrue(ok)

    def test_update_re_frozen_requires_re_freeze_trail(self) -> None:
        """outcome='re_frozen' 必含 re_frozen_at_ms + re_freeze_reason。"""
        with self.assertRaises(ValueError):
            update_unblock_outcome(
                42,
                outcome="re_frozen",
                # 缺 re_frozen_at_ms 與 re_freeze_reason
            )

    def test_update_re_frozen_with_full_trail_passes(self) -> None:
        """re_frozen 完整 trail → UPDATE 成功。"""
        cur = MagicMock()
        cur.rowcount = 1
        conn = MagicMock()
        conn.cursor.return_value = cur

        with patch(
            "helper_scripts.db.audit.blocked_symbols_30d_unblock_check._get_conn",
            return_value=conn,
        ):
            ok = update_unblock_outcome(
                42,
                outcome="re_frozen",
                re_frozen_at_ms=1736000000000,
                re_freeze_reason="7d demo edge -12.5 bps fail [40] healthcheck",
            )
        self.assertTrue(ok)

    def test_update_invalid_outcome_raises(self) -> None:
        """outcome 不在 unfrozen|re_frozen|kept_frozen → ValueError。"""
        with self.assertRaises(ValueError):
            update_unblock_outcome(42, outcome="bogus")


# =============================================================================
# §4 freeze.json reuse + values_sql
# =============================================================================


class TestFreezeJsonReuse(unittest.TestCase):
    def test_load_registry_returns_dict_with_frozen_cells(self) -> None:
        """freeze.json 必含 frozen_cells dict。"""
        registry = load_registry()
        self.assertIn("frozen_cells", registry)
        self.assertIn("grid_trading", registry["frozen_cells"])

    def test_iter_cells_yields_blockedcell_objects(self) -> None:
        """iter_cells 解出 BlockedCell list。"""
        cells = iter_cells(load_registry())
        self.assertGreater(len(cells), 0)
        self.assertTrue(all(isinstance(c, BlockedCell) for c in cells))

    def test_values_sql_pattern(self) -> None:
        """values_sql 用 (%s, %s) placeholder pattern。"""
        cells = [
            BlockedCell(strategy="grid_trading", symbol="BSBUSDT"),
            BlockedCell(strategy="ma_crossover", symbol="LABUSDT"),
        ]
        sql, params = _values_sql(cells)
        self.assertEqual(sql, "(%s, %s), (%s, %s)")
        self.assertEqual(len(params), 4)

    def test_values_sql_empty_raises(self) -> None:
        """空 cells → ValueError。"""
        with self.assertRaises(ValueError):
            _values_sql([])

    def test_parse_cell_arg_valid(self) -> None:
        """格式 'strategy:symbol' 解出 BlockedCell。"""
        cell = _parse_cell_arg("grid_trading:BSBUSDT")
        self.assertEqual(cell.strategy, "grid_trading")
        self.assertEqual(cell.symbol, "BSBUSDT")

    def test_parse_cell_arg_invalid_format(self) -> None:
        """格式錯誤 → ArgumentTypeError。"""
        import argparse
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_cell_arg("grid_trading_no_colon")
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_cell_arg(":")
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_cell_arg("only_strategy:")


# =============================================================================
# §5 Markdown rendering
# =============================================================================


class TestMarkdownRendering(unittest.TestCase):
    def test_render_includes_all_4_verdicts_summary(self) -> None:
        """markdown 含 4 verdict 計數行。"""
        rows = [
            UnblockCandidateRow(
                cell_strategy="grid_trading",
                cell_symbol="BSBUSDT",
                candidate_at_ms=1735689600000,
                paper_evidence={"paper_fills_30d": 100, "DSR": 1.0, "PBO": 0.0,
                                "paper_net_edge_bps_30d": 20.0,
                                "sm04_escalate_count_7d": 0, "yoyo_count_30d": 0},
                verdict=VERDICT_UNBLOCK_CANDIDATE,
            ),
            UnblockCandidateRow(
                cell_strategy="ma_crossover",
                cell_symbol="LABUSDT",
                candidate_at_ms=1735689600000,
                paper_evidence={"paper_fills_30d": 5,
                                "paper_net_edge_bps_30d": None,
                                "DSR": None, "PBO": None,
                                "sm04_escalate_count_7d": 0, "yoyo_count_30d": 0},
                verdict=VERDICT_DORMANT_NO_EVIDENCE,
            ),
        ]
        md = render_markdown(rows, days=30)
        self.assertIn("P1-DYNAMIC-UNBLOCK-CHECK-1", md)
        self.assertIn("unblock_candidate: `1`", md)
        self.assertIn("dormant_no_evidence: `1`", md)
        self.assertIn("BSBUSDT", md)
        self.assertIn("LABUSDT", md)


# =============================================================================
# §6 Healthcheck [64] tests（mock cursor）
# =============================================================================


def _make_cur_for_64(
    fetchone_rows: list[tuple],
) -> MagicMock:
    """構造 mock cursor for [64] 4 sub-check + V090 existence 5 query 序列。

    每個 query 對應一個 fetchone_rows 元素，按順序消費。
    """
    cur = MagicMock()
    cur.connection = MagicMock()
    cur.connection.rollback = MagicMock()
    cur.fetchone.side_effect = fetchone_rows
    return cur


class TestCheck64UnblockCandidatesDrift(unittest.TestCase):
    """Healthcheck [64] 4 sub-check 邏輯驗證。

    Query 順序：
        1. V090 existence check (to_regclass)
        2. Sub-check 1: stale candidate count
        3. Sub-check 2: yo-yo count
        4. Sub-check 3: incomplete sign-off count
        5. Sub-check 4: unfrozen rows count
    """

    def test_v090_missing_returns_pass_skip(self) -> None:
        """V090 not applied → PASS-skip（pre-deploy 不阻塞）。"""
        cur = _make_cur_for_64([(False,)])  # to_regclass 回 False
        status, msg = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("V090 not applied", msg)

    def test_all_zero_counts_returns_pass(self) -> None:
        """所有 sub-check counts = 0 → PASS。"""
        cur = _make_cur_for_64([
            (True,),    # V090 exists
            (0,),       # stale_count
            (0,),       # yoyo_count
            (0,),       # incomplete_signoff_count
            (0,),       # unfrozen_count
        ])
        status, msg = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "PASS")
        self.assertIn("4 sub-check all green", msg)

    def test_stale_candidate_returns_warn(self) -> None:
        """stale_count > 0（無其他 violation）→ WARN。"""
        cur = _make_cur_for_64([
            (True,),   # V090 exists
            (3,),      # stale_count > 0
            (0,),      # yoyo_count
            (0,),      # incomplete_signoff_count
            (0,),      # unfrozen_count
        ])
        status, msg = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "WARN")
        self.assertIn(f"{UNBLOCK_STALE_CANDIDATE_DAYS}d", msg)
        self.assertIn("operator inattention", msg)

    def test_yoyo_returns_fail(self) -> None:
        """yoyo_count > 0 → FAIL（spec §5.3）。"""
        cur = _make_cur_for_64([
            (True,),   # V090 exists
            (0,),      # stale_count
            (2,),      # yoyo_count > 0
            (0,),      # incomplete_signoff_count
            (0,),      # unfrozen_count
        ])
        status, msg = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("yo-yo detection", msg)
        self.assertIn("§5.3", msg)

    def test_incomplete_signoff_returns_fail(self) -> None:
        """incomplete_signoff_count > 0 → FAIL（V090 PG CHECK sentinel of sentinel）。"""
        cur = _make_cur_for_64([
            (True,),   # V090 exists
            (0,),      # stale_count
            (0,),      # yoyo_count
            (1,),      # incomplete_signoff_count > 0
            (0,),      # unfrozen_count
        ])
        status, msg = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("sign-off completeness violation", msg)
        self.assertIn("V090 unfrozen_completeness_chk", msg)

    def test_yoyo_priority_over_stale_warn(self) -> None:
        """yoyo + stale 同時 trip → FAIL（yoyo 優先級高於 WARN）。"""
        cur = _make_cur_for_64([
            (True,),   # V090 exists
            (5,),      # stale_count > 0
            (1,),      # yoyo_count > 0
            (0,),      # incomplete_signoff_count
            (0,),      # unfrozen_count
        ])
        status, _ = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "FAIL")

    def test_v090_query_exception_returns_fail(self) -> None:
        """V090 existence query exception → FAIL（fail-closed）。"""
        cur = MagicMock()
        cur.connection = MagicMock()
        cur.connection.rollback = MagicMock()
        cur.execute.side_effect = Exception("DB unreachable")
        status, msg = check_64_unblock_candidates_drift(cur)
        self.assertEqual(status, "FAIL")
        self.assertIn("V090 table existence check failed", msg)


if __name__ == "__main__":
    unittest.main()
